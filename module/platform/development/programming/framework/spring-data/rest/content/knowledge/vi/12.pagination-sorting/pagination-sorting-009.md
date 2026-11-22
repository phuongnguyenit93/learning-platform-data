# Sắp xếp thuộc tính lồng và giới hạn với quan hệ được biểu diễn bằng liên kết

## 1. Mục tiêu

Spring Data REST hỗ trợ phân trang và sắp xếp collection resource thông qua các tham số request. Với dữ liệu đơn giản, client có thể sắp xếp theo thuộc tính trực tiếp như name hoặc createdAt. Với mô hình có association, client có thể cần sắp xếp theo thuộc tính của entity liên quan, ví dụ thành phố của địa chỉ gắn với một người.

Một điểm cần phân biệt là **association link trong HAL** và **property path dùng để sắp xếp**:

- Association link là quan hệ hypermedia trong response, có rel và href để client truy cập tài nguyên liên quan.
- Property path là đường dẫn thuộc tính trong mô hình persistent entity mà Spring Data dùng để tạo Sort.

Nếu association được biểu diễn bằng link, điều đó không có nghĩa client phải sắp xếp theo href hoặc URL của link. Client gửi tên property path mà repository có thể hiểu; server thực hiện truy vấn và trả collection đã sắp xếp.

Bài này trình bày cách sắp xếp thuộc tính lồng, cách xử lý association đơn và association tập hợp, cách giới hạn kích thước trang, cùng những lưu ý về hiệu năng và bảo mật.

## 2. Mô hình dữ liệu minh họa

Giả sử ứng dụng quản lý Person và Address:

    @Entity
    public class Person {

        @Id
        @GeneratedValue
        private Long id;

        private String firstName;
        private String lastName;

        @ManyToOne
        private Address address;
    }

    @Entity
    public class Address {

        @Id
        @GeneratedValue
        private Long id;

        private String city;
        private String postalCode;
    }

Repository:

    public interface PersonRepository
            extends JpaRepository<Person, Long> {
    }

Một Person có thể liên kết tới một Address. Khi Spring Data REST trả Person resource, association có thể được biểu diễn bằng link thay vì nhúng toàn bộ Address:

    {
      "firstName": "An",
      "lastName": "Nguyen",
      "_links": {
        "self": {
          "href": "http://localhost:8080/people/42"
        },
        "address": {
          "href": "http://localhost:8080/people/42/address"
        }
      }
    }

Client theo link address nếu muốn đọc Address. Nhưng khi muốn sắp xếp collection Person theo thành phố, property path cần phản ánh mô hình entity: address.city. Tên rel address và href của link không phải giá trị Sort.

## 3. Cú pháp sort trong Spring Data REST

Spring Data REST dùng query parameter sort theo định dạng:

    sort=property,direction

Trong đó:

- property là tên thuộc tính persistent cần sắp xếp.
- direction là asc hoặc desc.
- asc là tăng dần; desc là giảm dần.

Ví dụ sắp xếp Person theo họ tăng dần:

    GET /people?sort=lastName,asc

Sắp xếp theo thời gian tạo giảm dần:

    GET /people?sort=createdAt,desc

Nếu không chỉ rõ direction, Spring Data thường dùng thứ tự tăng dần. Để request dễ đọc và tránh phụ thuộc mặc định, nên ghi rõ asc hoặc desc.

Không nhầm sort với tên link relation. Sort nhận property path của domain model, không nhận URL association.

## 4. Sắp xếp theo thuộc tính lồng của association đơn

Với association đơn như ManyToOne hoặc OneToOne, có thể biểu diễn đường dẫn thuộc tính lồng bằng dấu chấm. Trong mô hình trên, Person có thuộc tính address và Address có thuộc tính city. Request minh họa:

    GET /people?sort=address.city,asc

Điều này yêu cầu Spring Data sắp xếp Person theo giá trị city của Address liên quan.

Có thể kết hợp với phân trang:

    GET /people?sort=address.city,asc&page=0&size=20

Một ví dụ khác, sắp xếp theo mã bưu chính giảm dần:

    GET /people?sort=address.postalCode,desc&page=0&size=20

Đường dẫn phải khớp với tên thuộc tính trong persistent model. Nếu Java property là billingAddress nhưng HAL rel được tùy chỉnh thành billing, property path vẫn là billingAddress.city. Không dùng rel billing.city chỉ vì đó là key xuất hiện trong _links.

Khả năng sắp xếp thuộc tính lồng còn phụ thuộc store module, mapping và cách repository tạo truy vấn. Với JPA, truy vấn có thể cần join association. Hãy thử trên repository thực tế và kiểm tra câu SQL hoặc execution plan nếu collection lớn.

## 5. Association được biểu diễn bằng link: rel/href khác property path

Ví dụ HAL có association:

    {
      "firstName": "An",
      "_links": {
        "self": {
          "href": "http://localhost:8080/people/42"
        },
        "homeAddress": {
          "href": "http://localhost:8080/people/42/address"
        }
      }
    }

Giả sử association Java trên entity vẫn tên address, nhưng relation trong HAL được tùy chỉnh thành homeAddress. Khi sắp xếp theo city, property path vẫn có thể là:

    GET /people?sort=address.city,asc

Không phải:

    GET /people?sort=homeAddress.city,asc

và cũng không phải sort theo URL trong href.

Lý do: HAL rel dùng để client khám phá liên kết; Sort dùng để server truy cập thuộc tính trong mô hình repository. Hai tên có thể trùng nhau theo mặc định, nhưng có thể khác khi dùng @RestResource(rel = ...).

Quy trình nên là:

1. Dùng HAL link để khám phá và gọi association resource khi cần đọc entity liên quan.
2. Dựa vào mô hình domain/API contract để biết thuộc tính persistent nào được phép sắp xếp.
3. Gửi property path đó trong tham số sort.
4. Để server tạo truy vấn và trả collection theo thứ tự yêu cầu.

Client không cần GET từng Address rồi tự sắp xếp toàn bộ Person ở phía client. Làm như vậy tốn request, tăng dữ liệu truyền và có thể chỉ sắp xếp được trang hiện tại thay vì toàn bộ tập kết quả.

## 6. Nhiều tiêu chí sắp xếp và thứ tự ổn định

Có thể truyền nhiều tham số sort để sắp xếp theo nhiều tiêu chí. Ví dụ, sắp xếp theo họ tăng dần, sau đó tên tăng dần:

    GET /people?sort=lastName,asc&sort=firstName,asc

Với thuộc tính lồng:

    GET /people?sort=address.city,asc&sort=lastName,asc

Thứ tự tham số sort biểu thị thứ tự ưu tiên: tiêu chí đầu tiên được áp dụng trước; tiêu chí sau dùng để phân định các bản ghi có giá trị bằng nhau ở tiêu chí trước.

Khi kết hợp phân trang, nên thêm một khóa duy nhất làm tiêu chí cuối để thứ tự ổn định:

    GET /people?sort=lastName,asc&sort=id,asc&page=0&size=20

Nếu nhiều Person có cùng lastName mà không có tie-breaker, thứ tự giữa các bản ghi đó có thể thay đổi giữa các lần truy vấn. Điều này có thể khiến người dùng thấy item lặp lại hoặc bị bỏ qua khi chuyển trang, đặc biệt khi dữ liệu được cập nhật đồng thời.

Khóa tie-breaker nên là thuộc tính duy nhất, ổn định và được repository hỗ trợ sắp xếp.

## 7. Giới hạn số bản ghi trả về

Tham số phân trang phổ biến:

- page: chỉ số trang, bắt đầu từ 0 theo mặc định.
- size: số item yêu cầu trong một trang.
- sort: tiêu chí sắp xếp.

Ví dụ:

    GET /people?page=0&size=20&sort=lastName,asc

Request này yêu cầu trang đầu tiên, tối đa 20 item, sắp xếp theo lastName tăng dần.

Client không nên yêu cầu size quá lớn để tải toàn bộ dữ liệu trong một request. Trang nhỏ giúp giới hạn bộ nhớ, thời gian xử lý, lượng dữ liệu truyền và tải lên database. Với tập dữ liệu lớn, hãy theo các link phân trang mà server trả về.

## 8. Cấu hình default page size và max page size

Có thể cấu hình kích thước trang mặc định và giới hạn tối đa bằng RepositoryRestConfigurer:

    import org.springframework.context.annotation.Configuration;
    import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
    import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
    import org.springframework.web.servlet.config.annotation.CorsRegistry;

    @Configuration
    public class RepositoryRestConfig
            implements RepositoryRestConfigurer {

        @Override
        public void configureRepositoryRestConfiguration(
                RepositoryRestConfiguration config,
                CorsRegistry cors) {

            config.setDefaultPageSize(20);
            config.setMaxPageSize(100);
        }
    }

Trong ví dụ:

- default page size là 20 nếu client không truyền size.
- max page size là 100, giới hạn kích thước client có thể yêu cầu.

Tên tham số phân trang và sắp xếp cũng có thể được tùy chỉnh qua RepositoryRestConfiguration, chẳng hạn page parameter, limit/size parameter và sort parameter. Nếu thay đổi tên, client phải dùng tên đã cấu hình và nên dựa trên hợp đồng API của môi trường đang gọi.

Cấu hình page size mặc định không thay thế giới hạn tối đa. Nếu chỉ đặt default size, client vẫn có thể gửi một size lớn hơn nếu server không có max page size phù hợp.

## 9. Khi nào sắp xếp qua collection association trở nên mơ hồ?

Thuộc tính lồng qua association đơn như address.city thường có một giá trị cho mỗi Person nên có thể tạo thứ tự rõ ràng.

Ngược lại, association tập hợp như Person có nhiều Order không có một giá trị duy nhất orders.createdAt để sắp xếp Person. Một Person có thể có nhiều ngày tạo đơn hàng. Server phải biết muốn dùng ngày nhỏ nhất, ngày lớn nhất, đơn mới nhất hay một quy tắc khác.

Không nên mặc định rằng:

    GET /people?sort=orders.createdAt,desc

sẽ có ý nghĩa thống nhất ở mọi repository hoặc database. Việc sắp xếp qua collection-valued association có thể không được hỗ trợ, tạo join phức tạp, nhân bản hàng kết quả hoặc làm phân trang không chính xác nếu query không được thiết kế phù hợp.

Nếu nghiệp vụ cần sắp xếp Person theo ngày tạo Order gần nhất, hãy định nghĩa rõ quy tắc trong repository, ví dụ truy vấn có aggregate MAX(createdAt), subquery hoặc một projection phù hợp. Khi đó kết quả sort có một giá trị xác định cho mỗi Person.

Ví dụ ý tưởng JPQL:

    @Query("""
        select p
        from Person p
        left join p.orders o
        group by p
        order by max(o.createdAt) desc
        """)
    List<Person> findPeopleByLatestOrderDate();

Đây là minh họa về ý tưởng truy vấn; query thực tế cần điều chỉnh theo entity mapping, database và kiểu trả về. Nếu cần phân trang, phải đảm bảo count query và kết quả không bị nhân bản do join.

## 10. Dùng @Query và Pageable khi cần quy tắc rõ ràng

Khi sắp xếp theo association phức tạp hoặc cần giới hạn tập thuộc tính được phép sort, có thể định nghĩa query method trong repository:

    public interface PersonRepository
            extends JpaRepository<Person, Long> {

        @Query("""
            select p
            from Person p
            left join p.address a
            where a.city = :city
            """)
        Page<Person> findByAddressCity(
            @Param("city") String city,
            Pageable pageable
        );
    }

Client truyền Pageable qua các query parameter tương ứng. Repository xử lý điều kiện nghiệp vụ và Spring Data áp dụng phân trang/sắp xếp theo khả năng của query.

Với truy vấn phức tạp, kiểm tra cách framework áp dụng dynamic Sort. Một số query có alias hoặc biểu thức khiến property sort thông thường không áp dụng được như mong đợi. Khi cần thứ tự cố định, định nghĩa ORDER BY trong query; nếu cần cho client chọn thứ tự, chỉ cho phép những trường hợp mà query hỗ trợ rõ ràng.

Không đưa tùy ý mọi property của entity ra thành tiêu chí sort nếu có thể làm lộ dữ liệu hoặc tạo truy vấn tốn kém. Có thể xây dựng endpoint hoặc repository method chuyên biệt với danh sách sort field được cho phép.

## 11. Theo link phân trang thay vì tự ghép URL

Collection response của Spring Data REST thường có các link như self, first, prev, next và last khi phù hợp. Ví dụ minh họa:

    {
      "_links": {
        "self": {
          "href": "http://localhost:8080/people?page=0&size=20&sort=lastName,asc"
        },
        "next": {
          "href": "http://localhost:8080/people?page=1&size=20&sort=lastName,asc"
        }
      },
      "page": {
        "size": 20,
        "totalElements": 45,
        "totalPages": 3,
        "number": 0
      }
    }

Client nên theo href của next để lấy trang tiếp theo. Server giữ lại các tiêu chí sort và page size trong link được công bố. Không tự tạo URL bằng cách cộng page number nếu API đã cung cấp link điều hướng.

Ví dụ JavaScript:

    const nextHref = collection._links?.next?.href;

    if (nextHref) {
      const nextUrl = new URL(nextHref, collectionResponse.url);
      const nextResponse = await fetch(nextUrl, {
        headers: { Accept: "application/hal+json" }
      });

      if (!nextResponse.ok) {
        throw new Error("Không thể tải trang tiếp theo");
      }

      const nextPage = await nextResponse.json();
    }

Nếu không có next link, coi như response không công bố trang tiếp theo. Không suy đoán rằng có thêm dữ liệu chỉ từ số item của trang hiện tại.

## 12. Hiệu năng, bảo mật và tính đúng đắn

**Sắp xếp thuộc tính lồng có thể cần JOIN**

Khi sort theo address.city, database có thể phải join bảng Address. Kiểm tra index trên các cột được lọc và sắp xếp, đồng thời xem execution plan nếu dữ liệu lớn.

**Không phải mọi property đều nên được sort công khai**

Sort theo trường nhạy cảm có thể làm lộ thông tin gián tiếp qua thứ tự kết quả. Chỉ công bố những trường phù hợp với API và quyền của caller.

**Collection association có thể gây query đắt**

Sắp xếp theo thuộc tính của quan hệ nhiều phần tử cần quy tắc aggregate rõ ràng. Tránh để client gửi property path tùy ý gây truy vấn lớn hoặc khó kiểm soát.

**Phân trang cần thứ tự ổn định**

Thêm một khóa duy nhất làm tiêu chí cuối để giảm việc bản ghi đổi vị trí giữa các trang khi các giá trị sort trùng nhau.

**Dữ liệu thay đổi trong lúc duyệt trang**

Offset pagination có thể xuất hiện item lặp hoặc thiếu nếu dữ liệu được thêm/xóa giữa các request. Tie-breaker giúp thứ tự xác định hơn nhưng không tạo snapshot nhất quán. Nếu nghiệp vụ cần duyệt dữ liệu lớn trong lúc có cập nhật liên tục, cân nhắc cursor/keyset pagination trong endpoint chuyên biệt.

## 13. Bài tập thực hành

Với Person có firstName, lastName và association Address có city, postalCode:

1. Gọi collection endpoint với page=0 và size=10.
2. Sắp xếp theo lastName tăng dần.
3. Thêm tiêu chí firstName và id để có thứ tự ổn định.
4. Thử sort theo address.city và quan sát kết quả.
5. Xem Person HAL response; xác định link address và phân biệt link đó với property path address.city.
6. Tùy chỉnh rel của association thành homeAddress, sau đó xác định property path cần dùng để sort vẫn dựa trên tên thuộc tính persistent.
7. Đặt default page size là 20 và max page size là 100; thử request với size lớn hơn giới hạn và quan sát hành vi thực tế.
8. Thử sắp xếp theo association tập hợp như orders.createdAt; xác định vì sao cần quy tắc nghiệp vụ rõ ràng thay vì giả định một giá trị duy nhất.
9. Theo link next để chuyển trang và xác nhận server giữ lại sort cùng size.

Câu hỏi tự kiểm tra:

- sort=address.city,asc tham chiếu tới rel, href hay property path?
- Vì sao rel tùy chỉnh trong HAL không nhất thiết làm thay đổi tên thuộc tính dùng trong Sort?
- Tại sao sort theo một association đơn dễ xác định hơn sort theo collection association?
- Vì sao nên thêm id làm tiêu chí sort cuối khi phân trang?
- defaultPageSize và maxPageSize giải quyết hai vấn đề khác nhau nào?

## 14. Ghi nhớ

- Spring Data REST nhận sort theo property path của persistent model.
- Thuộc tính lồng qua association đơn có thể được biểu diễn bằng dấu chấm, ví dụ address.city.
- HAL rel/href dùng để khám phá association; chúng không phải property path của Sort.
- Có thể truyền nhiều sort parameter để xác định thứ tự ưu tiên.
- Thêm khóa duy nhất làm tie-breaker để phân trang ổn định hơn.
- Dùng page và size để phân trang; cấu hình default page size và max page size ở server.
- Sắp xếp qua association tập hợp cần quy tắc aggregate rõ ràng.
- Kiểm soát các trường được phép sort và theo link phân trang do server cung cấp.

## Tài liệu tham khảo

- Spring Data REST Reference — Paging and sorting: https://docs.spring.io/spring-data/rest/reference/
- Spring Data Commons Reference — Paging and sorting: https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html
- Spring Data JPA Reference — Query methods: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
