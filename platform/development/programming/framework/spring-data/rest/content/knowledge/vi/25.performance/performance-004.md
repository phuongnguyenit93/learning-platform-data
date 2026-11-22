# Ảnh hưởng của lazy loading và Open Session in View

## 1. Lazy loading trong JPA là gì?

Lazy loading là cách ORM trì hoãn việc tải một association hoặc thuộc tính cho đến khi ứng dụng thực sự truy cập nó. Với Spring Data JPA, Hibernate thường tạo proxy cho entity hoặc collection để đại diện cho dữ liệu chưa được tải.

Ví dụ một Person có nhiều Order:

~~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @OneToMany(mappedBy = "person", fetch = FetchType.LAZY)
    private List<Order> orders = new ArrayList<>();
}
~~~~

Khi query Person, Hibernate có thể chỉ tải hàng Person. Collection orders chưa được lấy ngay. Khi code gọi person.getOrders().size() hoặc lặp qua collection, Hibernate mới thực hiện query để lấy Order nếu persistence context còn mở.

Lazy loading giúp:

- Không tải dữ liệu liên quan khi use case không cần đến.
- Giảm lượng dữ liệu đọc và số object tạo trong bộ nhớ.
- Cho phép thiết kế fetch plan khác nhau theo từng use case.
- Tránh tải nhiều collection lớn chỉ vì entity có association.

Lazy loading cũng tạo ra một điều kiện quan trọng: proxy cần persistence context còn hoạt động khi được khởi tạo. Nếu context đã đóng và collection chưa được tải, Hibernate có thể ném LazyInitializationException.

Không phải mọi association đều mặc định LAZY. Trong JPA, ManyToOne và OneToOne mặc định EAGER, còn OneToMany và ManyToMany mặc định LAZY. Nên khai báo fetch type có chủ đích và thiết kế query theo nhu cầu của endpoint.

## 2. Persistence context và thời điểm proxy được khởi tạo

Persistence context là vùng quản lý entity của EntityManager. Hibernate dùng nó để theo dõi entity, identity, dirty checking và lazy proxy.

Một luồng xử lý đơn giản:

1. Repository chạy query và trả về Person.
2. Person có collection orders chưa được khởi tạo.
3. Transaction kết thúc.
4. EntityManager hoặc persistence context bị đóng.
5. Serializer đọc thuộc tính orders.
6. Hibernate không còn context để chạy query và có thể ném LazyInitializationException.

Ví dụ:

~~~~java
Person person = personRepository.findById(42L)
        .orElseThrow();

// Nếu orders chưa được tải và persistence context đã đóng,
// truy cập collection có thể ném LazyInitializationException.
int orderCount = person.getOrders().size();
~~~~

Điểm gây lỗi không nhất thiết nằm ở repository call. Lỗi có thể xuất hiện sau đó trong controller, mapper, logger hoặc JSON serializer khi một getter vô tình truy cập association lazy.

Vì vậy, cần biết chính xác lúc nào entity được serialize và persistence context còn tồn tại đến thời điểm nào.

## 3. Open Session in View (OSIV) là gì?

Open Session in View là mẫu giữ Hibernate Session hoặc JPA EntityManager mở trong suốt vòng đời một HTTP request. Trong Spring, cơ chế này thường được thực hiện bằng OpenEntityManagerInViewFilter hoặc interceptor tương ứng.

Luồng khái quát:

~~~~text
HTTP request bắt đầu
       |
       v
Mở EntityManager / gắn vào request thread
       |
       v
Controller gọi Spring Data repository
       |
       v
Repository query trong transaction
       |
       v
Transaction kết thúc
       |
       v
Controller trả entity hoặc representation
       |
       v
Jackson / HAL serializer đọc getter
       |
       +--> Proxy lazy được truy cập
       |        |
       |        v
       |    EntityManager vẫn còn mở
       |        |
       |        v
       |    Hibernate có thể chạy query bổ sung
       |
       v
HTTP response được ghi
       |
       v
Đóng EntityManager
~~~~

OSIV cho phép serializer khởi tạo association lazy sau khi transaction của repository đã kết thúc, miễn persistence context vẫn còn mở.

Đây là lý do một endpoint có thể chạy thành công dù controller chỉ trả entity và không có fetch query rõ ràng. OSIV có thể che khuất việc response đang kích hoạt nhiều query bổ sung.

## 4. OSIV trong Spring Boot

Với ứng dụng web dùng Spring Boot và JPA, Open EntityManager in View thường được bật mặc định nếu không cấu hình khác. Có thể điều khiển bằng property:

~~~~properties
spring.jpa.open-in-view=true
~~~~

Để tắt OSIV:

~~~~properties
spring.jpa.open-in-view=false
~~~~

Khi tắt, EntityManager theo request không được giữ mở cho phần render response. Entity hoặc proxy chưa được tải cần được xử lý trong transaction/service boundary hoặc bằng query fetch phù hợp.

Với REST API, tắt OSIV thường giúp lộ rõ fetch plan thực sự của từng endpoint. Khi đó ứng dụng phải chủ động tải dữ liệu cần serialize thay vì dựa vào getter lazy trong giai đoạn render.

Việc tắt OSIV có thể làm lộ LazyInitializationException ở các endpoint đang phụ thuộc vào lazy loading ngầm. Hãy kiểm tra các response có embedded association, projection hoặc custom serializer trước khi triển khai thay đổi cấu hình.

## 5. OSIV ảnh hưởng thế nào tới Spring Data REST?

Spring Data REST tạo representation từ repository resource và dùng message converter/serializer để tạo response HAL hoặc JSON. Representation có thể gồm:

- Thuộc tính scalar của entity.
- Link tới association resource.
- Embedded resource theo projection hoặc excerpt.
- Các field được custom controller hoặc serializer bổ sung.

Khi serializer hoặc projection đọc một thuộc tính lazy, Hibernate có thể chạy query bổ sung nếu OSIV vẫn giữ EntityManager mở.

Ví dụ một collection resource trả danh sách Person. Nếu mỗi Person được embed một danh sách Order, serializer có thể truy cập orders của từng Person. Với N người, hệ thống có thể chạy một query lấy Person và thêm N query lấy Order.

Không phải mọi association link đều tự động tải toàn bộ entity liên quan. Spring Data REST thường biểu diễn association bằng hypermedia link; query bổ sung phát sinh khi representation, projection, custom code hoặc serializer thực sự truy cập dữ liệu lazy.

Vì vậy, cần phân biệt:

- Link association chỉ công bố URI để client điều hướng.
- Embedded association yêu cầu dữ liệu liên quan xuất hiện trong response.
- Projection có thể gọi getter của association và kích hoạt lazy loading.
- Custom serializer có thể vô tình duyệt qua collection lớn.

## 6. N+1 query và chi phí ẩn của OSIV

N+1 query xảy ra khi ứng dụng tải N entity bằng một query, rồi chạy thêm một query cho mỗi entity để lấy association.

Ví dụ:

~~~~java
List<Person> people = personRepository.findAll();

for (Person person : people) {
    int count = person.getOrders().size();
}
~~~~

Nếu có 100 Person và orders là lazy, ứng dụng có thể chạy:

- 1 query lấy 100 Person.
- 100 query riêng để lấy orders cho từng Person.

Tổng cộng 101 query thay vì một số lượng query được kiểm soát.

Khi OSIV bật, lỗi lazy initialization có thể không xuất hiện, nhưng N+1 vẫn xảy ra. Response có thể trả thành công trong khi thời gian truy vấn tăng theo số lượng entity.

Dấu hiệu thường gặp:

- Endpoint nhanh với vài record nhưng chậm khi page size tăng.
- SQL log có nhiều câu SELECT giống nhau với ID khác nhau.
- Số query tăng tuyến tính theo số phần tử trong response.
- Serializer mất nhiều thời gian dù repository method có vẻ đơn giản.
- Connection/database load tăng trong lúc render response.

Không đánh giá hiệu năng chỉ bằng thời gian repository method. Hãy đo toàn bộ request, bao gồm serialize HAL/JSON và ghi response.

## 7. LazyInitializationException khi tắt OSIV

Khi OSIV tắt, nếu code truy cập proxy chưa được khởi tạo sau khi transaction kết thúc, Hibernate có thể ném:

~~~~text
org.hibernate.LazyInitializationException:
failed to lazily initialize a collection of role:
Person.orders: could not initialize proxy - no Session
~~~~

Ví dụ controller:

~~~~java
@GetMapping("/people/{id}")
public Person getPerson(@PathVariable Long id) {
    return personRepository.findById(id).orElseThrow();
}
~~~~

Nếu response serializer cố đọc orders mà repository đã trả entity sau khi persistence context đóng, response có thể thất bại.

Cách xử lý đúng là quyết định endpoint cần dữ liệu nào và tải dữ liệu đó trong transaction. Không nên bật lại OSIV hoặc đổi mọi association thành EAGER chỉ để che lỗi.

## 8. Tải dữ liệu có chủ đích bằng EntityGraph

Spring Data JPA hỗ trợ EntityGraph để chỉ định association cần tải cho một repository method.

Ví dụ:

~~~~java
public interface PersonRepository
        extends JpaRepository<Person, Long> {

    @EntityGraph(attributePaths = {"orders"})
    Optional<Person> findWithOrdersById(Long id);
}
~~~~

Service có thể gọi method này trong transaction rồi ánh xạ kết quả sang DTO:

~~~~java
@Service
public class PersonQueryService {

    private final PersonRepository people;

    public PersonQueryService(PersonRepository people) {
        this.people = people;
    }

    @Transactional(readOnly = true)
    public PersonDetails getDetails(Long id) {
        Person person = people.findWithOrdersById(id)
                .orElseThrow(() -> new PersonNotFoundException(id));

        return PersonDetails.from(person);
    }
}
~~~~

EntityGraph giúp thể hiện fetch plan ngay tại method query. Dùng nó cho association thực sự cần trong use case, không tải mọi quan hệ chỉ vì entity có thể có chúng.

Với collection lớn, hãy cân nhắc phân trang riêng cho association thay vì embed toàn bộ.

## 9. Fetch join và query tùy chỉnh

Một lựa chọn khác là dùng JPQL fetch join:

~~~~java
@Query("""
    select distinct p
    from Person p
    left join fetch p.orders
    where p.id = :id
    """)
Optional<Person> findByIdWithOrders(@Param("id") Long id);
~~~~

Fetch join tải association trong query chính. Từ đó mapper có thể truy cập orders trong transaction mà không tạo query lazy bổ sung.

Cần cẩn thận với collection fetch join kết hợp pagination. Một parent có nhiều child tạo nhiều dòng SQL cho cùng parent; database paging trên các dòng join có thể không tương ứng với paging trên entity gốc. Hibernate có thể phải xử lý phân trang trong bộ nhớ hoặc phát cảnh báo tùy cấu hình.

Với collection và page lớn, thường nên:

1. Query page ID hoặc parent entity trước.
2. Query association cho tập ID của page bằng một query IN.
3. Ghép dữ liệu trong service/mapper.
4. Hoặc dùng batch fetching để giảm số query.

Không fetch join nhiều collection lớn trong một query nếu điều đó tạo Cartesian product hoặc dữ liệu trùng lặp rất lớn.

## 10. DTO và projection cho response API

REST response không nhất thiết phải serialize trực tiếp JPA entity. DTO cho phép định nghĩa chính xác field mà endpoint cần trả.

Ví dụ:

~~~~java
public record PersonSummary(
        Long id,
        String name,
        int orderCount
) {
}
~~~~

Service tạo DTO trong transaction:

~~~~java
@Transactional(readOnly = true)
public PersonSummary getSummary(Long id) {
    Person person = personRepository.findById(id)
            .orElseThrow(() -> new PersonNotFoundException(id));

    return new PersonSummary(
            person.getId(),
            person.getName(),
            person.getOrders().size()
    );
}
~~~~

Ví dụ này vẫn cần orders được tải hiệu quả. Có thể dùng query count riêng hoặc projection query để lấy orderCount mà không tải toàn bộ Order entity.

DTO giúp:

- Kiểm soát dữ liệu công bố.
- Tránh serialize proxy và collection không cần thiết.
- Tách API contract khỏi cấu trúc persistence.
- Thực hiện mapping trong transaction rõ ràng.
- Giảm nguy cơ vòng tham chiếu khi entity có association hai chiều.

Spring Data REST cũng hỗ trợ projection và excerpt projection. Projection có thể giới hạn field được hiển thị, nhưng nếu getter trong projection truy cập association lazy, nó vẫn có thể kích hoạt query. Projection không tự động giải quyết N+1; cần kiểm tra fetch plan của từng representation.

## 11. Batch fetching để giảm N+1

Nếu endpoint thực sự cần association lazy của nhiều entity, batch fetching có thể gom việc tải thành các nhóm thay vì một query cho mỗi parent.

Với Hibernate, có thể dùng @BatchSize:

~~~~java
@OneToMany(mappedBy = "person", fetch = FetchType.LAZY)
@org.hibernate.annotations.BatchSize(size = 50)
private List<Order> orders = new ArrayList<>();
~~~~

Hoặc cấu hình mặc định:

~~~~properties
spring.jpa.properties.hibernate.default_batch_fetch_size=50
~~~~

Batch fetching có thể giảm số query đáng kể. Tuy nhiên, nó không thay thế việc chọn đúng dữ liệu response. Nếu endpoint chỉ cần orderCount, query COUNT hoặc projection thường hiệu quả hơn tải toàn bộ collection.

Kiểm tra SQL thực tế để xác nhận batch size có tác dụng với association và Hibernate version đang dùng.

## 12. EAGER không phải cách sửa tổng quát

Khi gặp LazyInitializationException, đổi FetchType.LAZY thành FetchType.EAGER có thể làm một endpoint hoạt động, nhưng thường tạo tác dụng phụ:

- Mọi query lấy entity đều có thể tải association dù use case không cần.
- Các association lồng nhau có thể kéo theo nhiều dữ liệu ngoài dự kiến.
- Số query và lượng dữ liệu có thể tăng.
- Collection EAGER có thể tạo N+1 tùy query plan.
- Khó kiểm soát representation và hiệu năng giữa các endpoint.

Nên giữ mapping association theo nhu cầu domain và định nghĩa fetch plan cho từng use case bằng EntityGraph, fetch join, projection hoặc DTO.

## 13. OSIV và transaction boundary

OSIV giữ persistence context mở trong request, nhưng không có nghĩa toàn bộ request chạy trong một transaction duy nhất.

Một repository method có thể mở transaction, thực hiện query rồi kết thúc transaction. Sau đó serializer vẫn truy cập proxy trong cùng EntityManager còn mở do OSIV. Query lazy bổ sung có thể diễn ra ngoài transaction nghiệp vụ ban đầu hoặc trong transaction khác tùy transaction manager và provider.

Điều này có thể dẫn đến:

- Response đọc các association ở những thời điểm khác nhau.
- Các query trong lúc serialize không nằm trong cùng transaction nghiệp vụ.
- Logic database bị kích hoạt từ getter hoặc serializer thay vì từ service.
- Thời gian sống của persistence context dài hơn phần nghiệp vụ cần thiết.
- Hành vi response phụ thuộc vào việc serializer truy cập field nào.

OSIV không đảm bảo snapshot nhất quán cho toàn bộ response. Nếu endpoint cần dữ liệu nhất quán trong một use case, hãy tải dữ liệu trong transaction phù hợp và tạo DTO trước khi transaction kết thúc.

## 14. Cấu hình tắt OSIV cho REST API

Có thể đặt trong application.properties:

~~~~properties
spring.jpa.open-in-view=false
~~~~

Sau khi tắt, kiểm tra các nhóm endpoint:

- Item resource có association được embed.
- Collection resource dùng excerpt projection.
- Custom repository controller trả entity trực tiếp.
- Custom serializer hoặc Jackson getter truy cập association.
- Logging/toString/equals/hashCode có duyệt collection lazy.
- API trả nested DTO được map sau khi transaction kết thúc.

Một số endpoint có thể tiếp tục hoạt động vì chỉ trả scalar field hoặc association link. Endpoint khác có thể phát sinh LazyInitializationException nếu serializer cần dữ liệu chưa tải.

Nên bật SQL logging hoặc Hibernate statistics trong môi trường test để quan sát số query và vị trí query được phát.

## 15. Tránh kích hoạt lazy loading ngoài ý muốn

Lazy loading không chỉ xảy ra trong controller hoặc serializer. Các thao tác sau cũng có thể truy cập proxy:

- Gọi toString() trên entity có association.
- Gọi equals() hoặc hashCode() dựa trên collection hoặc association.
- Log toàn bộ entity bằng logger.
- Debugger mở rộng object trong IDE.
- Mapper tự động đọc tất cả getter.
- JSON serializer duyệt mọi thuộc tính.
- Template engine hoặc view renderer truy cập property.

Không nên viết toString() tự động bao gồm mọi association. Dùng ID và các scalar field an toàn. Với Lombok, kiểm tra @ToString, @EqualsAndHashCode và exclude các association không phù hợp.

## 16. Kiểm thử khi OSIV tắt

Integration test nên chạy với cùng cấu hình production:

~~~~properties
spring.jpa.open-in-view=false
~~~~

Kiểm tra:

1. GET item trả đúng các field đã định nghĩa.
2. Collection resource không tạo N+1 query ngoài dự kiến.
3. Association được embed có fetch plan rõ ràng.
4. Projection không truy cập proxy đã đóng.
5. Custom controller map DTO trong transaction.
6. Không có LazyInitializationException khi serialize response.
7. Page size tăng không làm số query tăng tuyến tính ngoài dự kiến.
8. Các endpoint chỉ cần association link không tải toàn bộ collection.
9. Response không chứa field persistence không được công bố.

Có thể dùng Hibernate statistics, datasource proxy hoặc SQL logging trong integration test để đếm query. Với N+1, hãy kiểm tra số query ở nhiều kích thước dữ liệu, chẳng hạn 1, 10 và 50 parent, thay vì chỉ chạy một fixture nhỏ.

Ngoài test chức năng, nên đo request duration và query count ở môi trường gần production để xác nhận thay đổi fetch plan thực sự cải thiện hiệu năng.

## 17. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| LazyInitializationException khi serialize | OSIV tắt và response truy cập proxy chưa khởi tạo | Fetch association trong transaction hoặc map DTO |
| Endpoint chạy được khi OSIV bật nhưng rất chậm | Serializer gây N+1 query | Đo query count và khai báo fetch plan |
| Chuyển sang EAGER làm query nặng | Tải association ở mọi use case | Dùng LAZY và EntityGraph/query riêng |
| Collection fetch join làm paging sai/chậm | Join nhân bản dòng parent | Page parent trước rồi tải child theo ID |
| Projection vẫn gây N+1 | Getter trong projection truy cập association lazy | Tối ưu query/fetch plan của projection |
| Log entity làm phát sinh query | toString hoặc logger duyệt association | Log ID/scalar field, loại association khỏi toString |
| JSON response có vòng tham chiếu | Entity hai chiều được serialize trực tiếp | Dùng projection/DTO hoặc hypermedia link |
| Response đọc dữ liệu không đồng nhất | Lazy query chạy sau transaction nghiệp vụ | Tải dữ liệu trong transaction và map DTO |
| OSIV bật nhưng vẫn lỗi lazy | EntityManager không còn gắn với request hoặc proxy thuộc context khác | Kiểm tra transaction, filter và nguồn entity |
| Số query tăng theo số record | N+1 từ association lazy | Batch fetch, projection hoặc query phù hợp |

## 18. Kết luận

Lazy loading giúp trì hoãn việc tải association cho đến khi cần, còn Open Session in View giữ EntityManager/Session mở trong suốt request để serializer có thể khởi tạo proxy sau khi repository transaction kết thúc. Cách này có thể làm response hoạt động thuận tiện, nhưng cũng che khuất query phát sinh trong giai đoạn serialize và tạo N+1.

Với Spring Data REST, HAL/JSON representation, embedded association, projection và custom serializer có thể truy cập thuộc tính lazy. Khi tắt OSIV bằng spring.jpa.open-in-view=false, các endpoint phải tải dữ liệu cần thiết trong transaction hoặc map sang DTO trước khi context đóng. Dùng EntityGraph, fetch join có kiểm soát, projection, batch fetching và query count riêng theo nhu cầu. Tránh đổi mọi association sang EAGER để chữa lỗi. Kiểm thử với OSIV tắt, đo query count và xác nhận response serialization không gây lazy load ngoài dự kiến.

## Tài liệu tham khảo

- [Spring Boot — Data Access and Open EntityManager in View](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Spring Data JPA — Entity Graphs](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Hibernate ORM — Fetching](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#fetching)
- [Spring Data REST — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/)
