# Nhận diện N+1 khi đọc quan hệ, projection và excerpt

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích hiện tượng N+1 query trong ứng dụng Spring Data REST dùng JPA/Hibernate.
- Nhận diện cách lazy association bị truy cập khi tạo HAL representation.
- Hiểu vì sao projection và excerpt có thể làm phát sinh truy vấn bổ sung.
- Phân biệt projection ở tầng representation với projection ở tầng truy vấn SQL.
- Đọc SQL log và Hibernate statistics để tìm N+1.
- Chọn fetch join, EntityGraph, batch fetching hoặc DTO projection phù hợp.
- Tránh lỗi pagination khi fetch collection và kiểm tra số lượng query bằng integration test.

## 1. N+1 query là gì?

N+1 là mẫu truy vấn trong đó ứng dụng chạy một truy vấn để lấy danh sách N entity, sau đó chạy thêm một truy vấn cho mỗi entity để tải dữ liệu quan hệ.

Giả sử API trả về 50 Person, mỗi Person có một Address:

1. Query đầu tiên lấy 50 Person.
2. Khi response được serialize, ứng dụng đọc address của Person thứ nhất và chạy query lấy Address.
3. Lặp lại cho Person thứ hai, thứ ba và các Person còn lại.
4. Tổng số query có thể là 1 + 50 = 51.

SQL minh họa:

~~~sql
select p.id, p.name, p.address_id
from person p
order by p.id;

select a.id, a.city, a.street
from address a
where a.id = ?;
~~~

Query thứ hai có thể được thực hiện lặp lại với từng address_id. Nếu quan hệ là collection như Person có nhiều Order, Hibernate cũng có thể chạy một query riêng cho mỗi Person để tải các Order.

N+1 làm tăng số lần round-trip giữa ứng dụng và database. Dù mỗi query riêng lẻ rất nhanh, tổng latency có thể tăng đáng kể do network, connection pool, database scheduling và chi phí hydrate entity.

N+1 không có nghĩa là database luôn trả về N+1 hàng. Đây là cách đếm số lần thực thi query: một query ban đầu cộng thêm nhiều query phát sinh khi truy cập quan hệ.

## 2. Vì sao Spring Data REST dễ bộc lộ N+1?

Spring Data REST chuyển repository result thành representation, thường là HAL JSON. Quá trình tạo representation có thể truy cập getter của entity, projection hoặc association.

Một entity JPA có thể khai báo quan hệ lazy:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @ManyToOne(fetch = FetchType.LAZY)
    private Address address;
}
~~~

Repository:

~~~java
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

Khi gọi collection endpoint:

~~~http
GET /api/people
Accept: application/hal+json
~~~

Repository có thể chỉ tải Person trước. Nếu representation chỉ cung cấp link tới association và không đọc dữ liệu Address, association đó có thể chưa cần được tải.

Nhưng nếu projection hoặc serializer gọi getter của quan hệ, ví dụ getAddress().getCity(), Hibernate cần lấy Address. Nếu việc này xảy ra cho từng Person, N+1 xuất hiện.

Vì vậy, không nên kết luận rằng mọi collection endpoint Spring Data REST đều luôn có N+1. Kết quả phụ thuộc vào:

- Quan hệ là LAZY hay EAGER.
- Representation có truy cập association hay không.
- Projection có getter quan hệ hay không.
- Excerpt projection có đọc thuộc tính liên quan hay không.
- Persistence context còn mở hay đã đóng.
- Hibernate fetch plan, batch size và cache đang được cấu hình như thế nào.

## 3. Lazy loading và thời điểm query được thực thi

JPA thường dùng LAZY cho quan hệ to-many và có thể dùng LAZY cho nhiều quan hệ to-one. Lazy association chỉ được tải khi code thực sự truy cập dữ liệu của nó.

Ví dụ:

~~~java
Person person = personRepository.findById(1L).orElseThrow();

// Có thể chưa query Address.
Address address = person.getAddress();

// Khi truy cập thuộc tính, Hibernate có thể query Address.
String city = address.getCity();
~~~

Với một collection:

~~~java
Person person = personRepository.findById(1L).orElseThrow();

// Có thể chưa query Order.
List<Order> orders = person.getOrders();

// Khi duyệt collection, Hibernate có thể query các Order.
for (Order order : orders) {
    System.out.println(order.getOrderNumber());
}
~~~

Lazy loading giúp tránh tải dữ liệu không cần thiết. Vấn đề xuất hiện khi code truy cập cùng một association theo cách lặp lại trên nhiều entity.

Cần phân biệt:

- **Lazy loading** là cơ chế tải dữ liệu khi cần.
- **N+1** là một mẫu truy vấn phát sinh do cách truy cập dữ liệu.
- Lazy loading không tự nó là lỗi; nó trở thành vấn đề khi số query tăng theo số entity trong kết quả.

## 4. Projection có thể kích hoạt N+1 như thế nào?

Spring Data REST projection xác định các thuộc tính xuất hiện trong representation. Projection interface có thể khai báo getter cho association:

~~~java
@Projection(name = "personWithAddress", types = Person.class)
public interface PersonWithAddress {

    String getName();

    Address getAddress();
}
~~~

Projection lồng nhau có thể giới hạn các trường của Address:

~~~java
@Projection(name = "addressSummary", types = Address.class)
public interface AddressSummary {

    String getCity();
    String getStreet();
}
~~~

Hoặc khai báo projection cho Person với một view quan hệ rõ ràng:

~~~java
@Projection(name = "personWithAddressSummary", types = Person.class)
public interface PersonWithAddressSummary {

    String getName();

    AddressSummary getAddress();
}
~~~

Khi Spring Data REST tạo representation cho nhiều Person, getter getAddress() có thể được gọi trên từng Person. Nếu Address là lazy và chưa có trong persistence context, Hibernate có thể phát sinh query riêng cho từng association.

Mẫu SQL có thể là:

~~~sql
select p.id, p.name, p.address_id
from person p;

select a.id, a.city, a.street
from address a
where a.id = ?;

select a.id, a.city, a.street
from address a
where a.id = ?;

-- Tiếp tục cho các Person còn lại.
~~~

Projection làm rõ dữ liệu client muốn nhìn thấy, nhưng việc đọc getter quan hệ vẫn có thể kích hoạt lazy loading. Hãy kiểm tra SQL thực tế thay vì suy luận rằng số field ít hơn đồng nghĩa số query ít hơn.

## 5. Excerpt projection cũng cần được kiểm tra

Excerpt projection được cấu hình trên repository:

~~~java
@RepositoryRestResource(
    path = "people",
    excerptProjection = PersonExcerpt.class
)
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

Ví dụ excerpt:

~~~java
@Projection(name = "personExcerpt", types = Person.class)
public interface PersonExcerpt {

    String getName();

    AddressSummary getAddress();
}
~~~

Khi collection resource nhúng nhiều Person, excerpt được dùng để tạo representation của các item theo cấu hình. Nếu excerpt chỉ đọc name, nó có thể không cần tải Address. Nếu excerpt đọc address, việc tạo representation có thể truy cập association và kích hoạt query bổ sung.

Một điểm quan trọng: **Spring Data REST excerpt/projection là cơ chế chọn representation**. Chúng không tự bảo đảm Hibernate sẽ phát một câu SQL join duy nhất.

Cũng cần phân biệt hai loại projection:

- **Spring Data REST projection**: quyết định field nào xuất hiện trong HAL representation của entity.
- **Spring Data JPA query projection**: có thể yêu cầu query trả về interface projection hoặc DTO thay vì hydrate toàn bộ entity, tùy query và cách khai báo repository.

Hai cơ chế có tên gần giống nhau nhưng không đồng nghĩa. Projection ở tầng REST có thể đọc entity và lazy association; query projection ở tầng JPA có thể tối ưu cột được select nếu query được thiết kế phù hợp.

## 6. Excerpt mặc định không phải fetch plan

Ví dụ cấu hình excerpt:

~~~java
@Projection(name = "personExcerpt", types = Person.class)
public interface PersonExcerpt {
    String getName();
    String getEmail();
}
~~~

Excerpt trên chỉ đọc hai thuộc tính cơ bản của Person. Nếu chúng là field thông thường, representation có thể được tạo mà không truy cập association.

Nếu thêm getter:

~~~java
@Projection(name = "personExcerpt", types = Person.class)
public interface PersonExcerpt {
    String getName();
    AddressSummary getAddress();
}
~~~

thì view có thể cần dữ liệu Address. Query plan của Hibernate vẫn được quyết định bởi mapping, fetch plan, query và cache.

Đừng dùng excerpt để thay thế việc thiết kế fetch strategy. Hãy xem excerpt là hợp đồng representation và chọn fetch strategy riêng cho endpoint cần dữ liệu quan hệ.

## 7. Phân biệt link association và inline association

Spring Data REST thường biểu diễn association bằng hypermedia link. Ví dụ Person có thể trả về:

~~~json
{
  "name": "Lan",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/people/1"
    },
    "address": {
      "href": "http://localhost:8080/api/people/1/address"
    }
  }
}
~~~

Trong representation này, Address không nhất thiết phải được serialize thành object lồng nhau. Client có thể gọi association link khi thực sự cần dữ liệu Address.

Nếu projection đưa Address vào body:

~~~json
{
  "name": "Lan",
  "address": {
    "city": "Ho Chi Minh City",
    "street": "Le Loi"
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/people/1"
    },
    "address": {
      "href": "http://localhost:8080/api/people/1/address"
    }
  }
}
~~~

thì server cần lấy dữ liệu Address để tạo phần inline đó.

Hai cách có trade-off khác nhau:

| Cách biểu diễn | Ưu điểm | Chi phí cần cân nhắc |
|---|---|---|
| Association link | Representation gọn; client chỉ tải quan hệ khi cần | Client có thể phải gọi thêm endpoint |
| Inline projection | Một response chứa dữ liệu quan hệ cần cho màn hình | Server có thể phải fetch nhiều association và phát sinh N+1 |
| DTO/query projection | Có thể tối ưu field và query theo use case | Cần định nghĩa query/endpoint riêng và giữ representation nhất quán |

Không phải cứ dùng link là luôn nhanh hơn; nếu client luôn gọi từng association cho từng item, N+1 có thể chuyển thành nhiều HTTP request. Cần cân nhắc cách client sử dụng API và fetch plan ở server.

## 8. Nhận diện N+1 qua SQL log

Bật SQL log ở môi trường phát triển:

~~~properties
spring.jpa.show-sql=true
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Logger bind parameter thay đổi theo phiên bản Hibernate. Với Hibernate 5, tên logger thường dùng khác Hibernate 6; kiểm tra đúng version trong ứng dụng.

Gọi collection endpoint với số lượng item đủ lớn:

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  "http://localhost:8080/api/people?page=0&size=20"
~~~

Quan sát log:

~~~text
select ... from person ... limit ...;
select ... from address where id=?;
select ... from address where id=?;
select ... from address where id=?;
...
~~~

Dấu hiệu N+1:

- Một query lấy danh sách entity.
- Nhiều query cùng một cấu trúc SQL cho association.
- Số query phụ tăng gần tuyến tính theo số item được serialize.
- Khi tăng page size từ 10 lên 30, số query quan hệ cũng tăng rõ rệt.

Không phải mọi chuỗi query lặp lại đều là N+1. Hãy xác định query nào lấy association và nó được kích hoạt bởi getter/representation nào.

Tránh bật SQL bind logging trong production nếu log có thể chứa dữ liệu cá nhân, token hoặc giá trị nhạy cảm. SQL logging có thể tạo lượng log lớn và ảnh hưởng hiệu năng.

## 9. Dùng Hibernate statistics để đo số query

Hibernate statistics giúp quan sát số lần query, entity load, collection fetch và cache hit.

Có thể bật trong cấu hình:

~~~properties
spring.jpa.properties.hibernate.generate_statistics=true
logging.level.org.hibernate.stat=DEBUG
~~~

Hoặc cấu hình SessionFactory statistics trong test:

~~~java
SessionFactory sessionFactory =
    entityManagerFactory.unwrap(SessionFactory.class);

Statistics statistics = sessionFactory.getStatistics();
statistics.setStatisticsEnabled(true);
statistics.clear();

personRepository.findAll(PageRequest.of(0, 20));

// Đọc các metric sau khi operation hoàn tất.
long queryCount = statistics.getQueryExecutionCount();
long entityFetches = statistics.getEntityFetchCount();
long collectionFetches = statistics.getCollectionFetchCount();
~~~

Các metric hữu ích:

- **QueryExecutionCount**: số lần query được thực thi qua Hibernate query statistics.
- **EntityFetchCount**: số lần entity được fetch thông qua cơ chế fetch.
- **CollectionFetchCount**: số lần collection được fetch.
- **SecondLevelCacheHitCount**: số lần lấy dữ liệu từ second-level cache.

Statistics không phải phép đo duy nhất. Một số query có thể được thực hiện qua JDBC hoặc đường đi không được phản ánh giống Hibernate query statistics. Hãy kết hợp statistics với SQL log và datasource instrumentation nếu cần.

## 10. Giải pháp 1: Fetch join

JPQL fetch join yêu cầu tải association cùng query chính:

~~~java
public interface PersonRepository extends JpaRepository<Person, Long> {

    @Query("""
        select p
        from Person p
        left join fetch p.address
        where p.active = true
        """)
    List<Person> findActiveWithAddress();
}
~~~

SQL có thể trở thành một query join:

~~~sql
select p.*, a.*
from person p
left join address a on a.id = p.address_id
where p.active = true;
~~~

Khi tạo representation cho Person, Address đã được tải nên getter không cần query riêng.

Fetch join phù hợp với quan hệ to-one như ManyToOne hoặc OneToOne trong nhiều trường hợp. Tuy nhiên, cần kiểm tra số hàng trả về và các quan hệ được fetch.

### Cẩn thận với collection fetch join và pagination

Nếu fetch join một collection to-many cùng pagination, kết quả SQL có thể nhân bản hàng Person theo số Order. Hibernate có thể phải xử lý pagination ở bộ nhớ hoặc cảnh báo/đưa ra lỗi tùy phiên bản và cấu hình.

Ví dụ:

~~~java
@Query("""
    select distinct p
    from Person p
    left join fetch p.orders
    """)
Page<Person> findAllWithOrders(Pageable pageable);
~~~

Đây là mẫu cần đặc biệt thận trọng. Fetch collection cùng Page có thể làm mất hiệu quả phân trang và tạo dữ liệu trung gian rất lớn. Không áp dụng mù quáng cho collection endpoint.

Với to-many và pagination, thường nên phân trang ID/root entity trước, rồi tải association cho tập ID của trang bằng query thứ hai. Cách này tạo số query cố định theo page thay vì một query cho mỗi item.

## 11. Giải pháp 2: @EntityGraph

Spring Data JPA hỗ trợ **@EntityGraph** để khai báo association cần tải cho một repository query.

Ví dụ:

~~~java
public interface PersonRepository extends JpaRepository<Person, Long> {

    @EntityGraph(attributePaths = {"address"})
    Optional<Person> findWithAddressById(Long id);

    @EntityGraph(attributePaths = {"address"})
    List<Person> findByActiveTrue();
}
~~~

EntityGraph có thể dùng fetch graph hoặc load graph theo thuộc tính được khai báo và mapping hiện tại. Nó giúp fetch plan rõ ràng mà không phải viết JPQL join fetch cho mọi method.

Named entity graph có thể khai báo trên entity:

~~~java
@Entity
@NamedEntityGraph(
    name = "Person.withAddress",
    attributeNodes = @NamedAttributeNode("address")
)
public class Person {
    // Fields and relationships.
}
~~~

Dùng graph:

~~~java
@EntityGraph(value = "Person.withAddress")
Optional<Person> findById(Long id);
~~~

Ví dụ minh họa; trong repository thật, tránh khai báo method trùng chữ ký kế thừa một cách thiếu chủ đích. Hãy kiểm tra method nào REST exporter thực sự gọi.

Một điểm quan trọng với Spring Data REST: thêm một finder method có @EntityGraph không tự thay đổi query mà endpoint collection mặc định findAll(Pageable) đang gọi. Muốn áp dụng fetch plan cho endpoint đó, phải thiết kế đường truy cập tương ứng, ví dụ custom repository method/resource, repository fragment, controller/service riêng hoặc cấu hình repository phù hợp đã được kiểm chứng.

## 12. Giải pháp 3: Batch fetching

Batch fetching cho phép Hibernate tải nhiều association cùng một query bằng danh sách ID thay vì một query cho từng entity.

Có thể cấu hình global:

~~~properties
spring.jpa.properties.hibernate.default_batch_fetch_size=32
~~~

Hoặc trên association/entity bằng @BatchSize:

~~~java
@Entity
@BatchSize(size = 32)
public class Address {
    // Fields.
}
~~~

Khi nhiều Person tham chiếu các Address lazy, Hibernate có thể tải một nhóm Address bằng query dạng IN:

~~~sql
select a.id, a.city, a.street
from address a
where a.id in (?, ?, ?, ...);
~~~

Nếu có 50 Person và batch size là 32, số query lấy Address có thể giảm từ khoảng 50 xuống còn khoảng 2, tùy mapping, cache và cách truy cập.

Batch fetching không đảm bảo chỉ còn một query. Nó giảm số query bằng cách gom nhiều lazy load vào một batch.

Batch fetching đặc biệt hữu ích khi:

- Association vẫn cần lazy loading.
- Không muốn join quá nhiều bảng vào query chính.
- Có nhiều quan hệ to-one hoặc collection được truy cập theo nhóm.
- Endpoint không dễ thay đổi sang DTO hoặc custom query.

Đo bằng SQL log sau khi thay đổi batch size để xác nhận Hibernate thực sự gom query.

## 13. Giải pháp 4: DTO hoặc query projection

Nếu endpoint chỉ cần một tập field cố định, DTO projection có thể giảm dữ liệu hydrate và tránh việc serializer truy cập lazy association.

Ví dụ:

~~~java
public record PersonSummary(
    Long id,
    String name,
    String city
) {
}
~~~

Repository query:

~~~java
public interface PersonRepository extends JpaRepository<Person, Long> {

    @Query("""
        select new com.example.api.PersonSummary(
            p.id,
            p.name,
            a.city
        )
        from Person p
        left join p.address a
        where p.active = true
        """)
    List<PersonSummary> findActiveSummaries();
}
~~~

Query lấy Person và City trong một lần join. DTO không giữ proxy JPA hoặc lazy collection, nên serialization không kích hoạt truy vấn association bổ sung.

DTO projection phù hợp khi:

- Màn hình cần một view cụ thể, ổn định.
- Chỉ cần một số field và quan hệ xác định.
- Muốn kiểm soát SQL và shape response.
- Cần tránh entity graph phức tạp trong quá trình serialize.

Nếu dùng DTO endpoint riêng, cần quyết định cách công bố resource: custom controller, custom repository endpoint hoặc một API layer khác. Spring Data REST projection và JPA DTO projection là hai cơ chế riêng; không tự động chuyển đổi qua lại.

## 14. Tách pagination và tải association theo page

Với collection to-many, một chiến lược thường an toàn là:

1. Query Page<Person> chỉ lấy root entity hoặc ID cần thiết.
2. Lấy danh sách ID trong page.
3. Chạy một query lấy toàn bộ dữ liệu liên quan cho các ID đó.
4. Ghép dữ liệu vào DTO theo ID.
5. Trả page representation có metadata phân trang.

Ví dụ query thứ hai:

~~~java
@Query("""
    select p
    from Person p
    left join fetch p.address
    where p.id in :ids
    """)
List<Person> findAllWithAddressByIdIn(@Param("ids") Collection<Long> ids);
~~~

Với collection Order, có thể tải tất cả Order thuộc các Person trong trang bằng một query:

~~~java
@Query("""
    select o
    from Order o
    where o.person.id in :personIds
    """)
List<Order> findOrdersForPeople(
    @Param("personIds") Collection<Long> personIds
);
~~~

Sau đó nhóm Order theo person ID trong service và dựng DTO.

Cách này thường có số query cố định nhỏ cho mỗi page: một query lấy page, có thể một count query và một query lấy association. Nó tránh query riêng cho từng Person.

Khi xử lý danh sách ID lớn, lưu ý giới hạn số bind parameter của database. Với page size nhỏ, một query IN thường phù hợp; với tập ID lớn, chia batch hoặc dùng chiến lược khác.

## 15. EAGER không phải cách sửa N+1 mặc định

Đổi LAZY thành EAGER có thể làm dữ liệu được tải sớm hơn, nhưng không bảo đảm Hibernate dùng một JOIN. Persistence provider vẫn có thể chạy nhiều query để đáp ứng eager association.

EAGER còn có thể tải dữ liệu mà endpoint không cần, làm tăng memory, số hàng join hoặc phát sinh N+1 khác ở quan hệ lồng nhau.

Ví dụ không nên tùy tiện đổi:

~~~java
@ManyToOne(fetch = FetchType.EAGER)
private Address address;
~~~

Hãy chọn fetch plan theo use case thay vì biến mọi association thành EAGER.

Một chiến lược thường tốt hơn:

- Mapping entity giữ LAZY cho association không cần mặc định.
- Query cụ thể dùng EntityGraph hoặc fetch join cho dữ liệu cần thiết.
- DTO projection cho response cố định.
- Batch fetching khi cần lazy loading theo nhóm.
- API representation chỉ inline những association client thực sự cần.

## 16. Projection và fetch plan phải được thiết kế cùng nhau

Khi thiết kế Spring Data REST projection, hãy liệt kê các getter có thể truy cập association:

~~~java
@Projection(name = "personDetail", types = Person.class)
public interface PersonDetail {

    String getName();

    AddressSummary getAddress();

    List<OrderSummary> getOrders();
}
~~~

Projection trên có thể cần cả Address lẫn Orders. Nếu collection có 30 Person, serializer có thể truy cập 30 Address và 30 collection Order. Chỉ tối ưu Address mà bỏ qua Orders thì N+1 vẫn có thể còn.

Một bảng kiểm kê hữu ích:

| Getter trong projection | Quan hệ | Fetch risk |
|---|---|---|
| getName() | Field cơ bản | Thường không tạo query quan hệ |
| getAddress() | To-one | Có thể tạo query cho từng Person |
| getOrders() | To-many | Có thể tạo query collection cho từng Person |
| getOrders().getProduct() | Quan hệ lồng nhau | Có thể tạo thêm một lớp N+1 nữa |

Với projection lồng nhau, số query có thể tăng theo nhiều cấp. Ví dụ tải Person, rồi Orders của từng Person, rồi Product của từng Order.

Hãy kiểm tra toàn bộ cây projection, không chỉ getter cấp đầu tiên.

## 17. Count query không phải N+1

Collection có pagination thường chạy:

- Một query lấy page content.
- Một query COUNT để xác định totalElements/totalPages khi cần.
- Có thể thêm query lấy quan hệ do projection hoặc serializer truy cập.

Count query là chi phí phân trang bình thường, không phải N+1. N+1 thường có dấu hiệu cùng một query association được lặp lại theo từng item.

Ví dụ:

~~~sql
select count(p.id) from person p;

select p.id, p.name from person p
order by p.id
offset ? rows fetch first ? rows only;

select a.id, a.city from address a where a.id = ?;
select a.id, a.city from address a where a.id = ?;
select a.id, a.city from address a where a.id = ?;
~~~

Hai query đầu có thể là pagination bình thường. Các query Address lặp lại mới là dấu hiệu cần điều tra N+1.

Không nên loại bỏ count query chỉ vì thấy số query lớn. Trước hết hãy phân loại từng query theo mục đích.

## 18. Kiểm thử để ngăn N+1 quay lại

Có thể viết integration test gọi đúng repository/service hoặc endpoint mà ứng dụng sử dụng.

Ví dụ với Hibernate statistics:

~~~java
@SpringBootTest
class PersonQueryPerformanceTest {

    @Autowired
    PersonRepository repository;

    @Autowired
    EntityManagerFactory entityManagerFactory;

    @Test
    void loadsAddressesInBatches() {
        SessionFactory sessionFactory =
            entityManagerFactory.unwrap(SessionFactory.class);

        Statistics statistics = sessionFactory.getStatistics();
        statistics.setStatisticsEnabled(true);
        statistics.clear();

        repository.findByActiveTrue();

        long entityFetches = statistics.getEntityFetchCount();
        long collectionFetches = statistics.getCollectionFetchCount();

        assertThat(entityFetches).isLessThanOrEqualTo(2);
        assertThat(collectionFetches).isLessThanOrEqualTo(2);
    }
}
~~~

Đây là skeleton minh họa; dữ liệu test, fetch access và cache phải được chuẩn bị để test thực sự kích hoạt đường code đang muốn đo. Chỉ gọi repository rồi không truy cập association có thể không tái hiện N+1 của response serialization.

Để kiểm tra Spring Data REST đầy đủ:

1. Tạo một tập Person đủ lớn, mỗi Person có Address/Orders.
2. Xóa hoặc tắt cache liên quan để tránh cache che mất query.
3. Gọi collection endpoint bằng MockMvc hoặc HTTP integration test.
4. Dùng projection/excerpt thực tế mà client yêu cầu.
5. Đếm query trong lúc response được serialize.
6. So sánh số query ở page size 10 và 30.
7. Đặt ngưỡng query hợp lý để test phát hiện số query tăng tuyến tính theo số item.

Có thể dùng datasource proxy hoặc query-counting test utility nếu cần đếm mọi JDBC statement, kể cả query không xuất hiện trong Hibernate query statistics.

Không đặt assertion quá cứng vào số query nếu implementation có count query hoặc query metadata khác nhau giữa phiên bản Hibernate/database. Hãy kiểm tra xu hướng và giới hạn hợp lý của endpoint.

## 19. Quy trình chẩn đoán thực tế

Khi nghi ngờ N+1 ở Spring Data REST:

1. Xác định endpoint, page size, projection và excerpt projection đang được dùng.
2. Bật SQL log ở môi trường phát triển.
3. Gọi endpoint với page nhỏ và ghi lại query đầu tiên.
4. Tìm các query lặp lại có cùng cấu trúc và khác bind ID.
5. Xác định getter hoặc association nào bị truy cập trong representation.
6. Thử bỏ getter quan hệ khỏi projection để xác nhận nguồn query.
7. Chọn fetch join, EntityGraph, batch fetching hoặc DTO projection.
8. Gọi lại endpoint và đo số query.
9. Kiểm tra pagination, memory và response body vẫn đúng.
10. Thêm integration test để giữ giới hạn query.

Không tối ưu bằng cách đoán. Một endpoint có nhiều query chưa chắc là N+1; có thể có count query, query phân trang, query audit hoặc logic nghiệp vụ khác. Cần đối chiếu SQL và request path.

## 20. Những lỗi thường gặp

### Nghĩ projection luôn giảm số query

Projection giảm field trong representation nhưng có thể đọc lazy association. Nếu getter quan hệ được gọi cho từng item, N+1 vẫn xảy ra.

### Nghĩ excerpt tự động tạo SQL join

Excerpt chọn representation mặc định cho item được nhúng. Nó không phải fetch plan và không tự bảo đảm một query join.

### Chỉ kiểm tra query đầu tiên

N+1 thường xuất hiện sau query lấy collection, trong lúc serialize HAL response. Cần đo toàn bộ request đến khi response hoàn tất.

### Chuyển mọi quan hệ sang EAGER

EAGER có thể tải thừa dữ liệu và vẫn tạo nhiều query. Dùng fetch plan theo use case.

### Fetch join collection cùng Page

To-many fetch join có thể nhân bản root row và làm pagination kém hiệu quả hoặc không an toàn. Tách page query và query lấy association theo ID khi phù hợp.

### Thêm EntityGraph nhưng endpoint mặc định không đổi

EntityGraph chỉ áp dụng cho method query tương ứng. Spring Data REST collection mặc định có thể gọi findAll(Pageable) khác với finder method bạn đã annotate.

### Cache làm che mất N+1

Second-level cache hoặc application cache có thể khiến query count thấp trong test nhưng production cache cold lại phát sinh nhiều query. Kiểm tra cả cache cold và warm.

### Chỉ tối ưu một quan hệ trong projection lồng nhau

Projection có thể truy cập nhiều cấp association. Phải xem toàn bộ cây getter và fetch strategy tương ứng.

### Dùng DTO nhưng vẫn trả entity lazy trong một field

DTO có thể vô tình chứa entity hoặc proxy. Dùng scalar/value DTO rõ ràng và hoàn tất việc map trong transaction phù hợp.

## 21. Ghi nhớ

- N+1 là một query lấy danh sách cộng thêm query quan hệ lặp lại theo từng entity.
- Spring Data REST có thể bộc lộ N+1 khi projection, excerpt hoặc serializer truy cập lazy association.
- Projection/excerpt ở tầng REST quyết định representation; chúng không tự bảo đảm SQL được join hoặc chỉ chạy một query.
- Phân biệt Spring Data REST projection với Spring Data JPA query projection/DTO projection.
- Dùng SQL log và Hibernate statistics để xác định query lặp lại.
- Fetch join và EntityGraph phù hợp với fetch plan cụ thể; cẩn thận khi fetch collection cùng pagination.
- Batch fetching giảm số query lazy bằng cách gom nhiều ID vào một batch.
- DTO projection và page-ID-then-fetch strategy phù hợp khi cần response cố định hoặc quan hệ to-many.
- Count query của pagination không tự nó là N+1.
- Kiểm thử endpoint với projection/excerpt thật, cache cold và page size khác nhau để ngăn N+1 quay lại.

## Tài liệu tham khảo

- [Spring Data REST Reference — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Spring Data JPA Reference — Query Methods and Entity Graphs](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Spring Data JPA Reference — Projections](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html)
- [Hibernate ORM User Guide — Fetching](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#fetching)
- [Hibernate ORM User Guide — Batch Fetching](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#batch-fetching)
