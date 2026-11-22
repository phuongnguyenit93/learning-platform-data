# Công bố truy vấn @Query và giữ logic truy vấn trong tầng repository

## 1. Mục tiêu

Spring Data REST có thể công bố query method của Spring Data repository thành search resource. Client gọi endpoint tìm kiếm bằng HTTP GET và truyền các tham số cần thiết. Khi muốn viết câu truy vấn rõ ràng hoặc phức tạp, ta có thể đặt logic truy vấn trong repository bằng annotation @Query.

Cách tổ chức này giữ truy vấn gần tầng truy cập dữ liệu:

- Repository định nghĩa truy vấn và kiểu kết quả.
- Spring Data thực thi truy vấn thông qua cơ chế repository.
- Spring Data REST công bố query method thành liên kết tìm kiếm nếu method được export.
- Client khám phá liên kết trong HAL và gửi GET với query parameter.

Bài này dùng Spring Data JPA để minh họa @Query. Với Spring Data module khác, annotation và ngôn ngữ truy vấn có thể khác, nhưng Spring Data REST vẫn dựa trên repository metadata và cấu hình export để công bố query method.

## 2. Query method được công bố như search resource

Giả sử ứng dụng có repository:

    public interface CustomerRepository
            extends JpaRepository<Customer, Long> {

        List<Customer> findByCity(String city);
    }

Spring Data REST có thể công bố query method dưới search resource của collection. Luồng khám phá thông thường:

1. GET API root để tìm link collection.
2. Theo link collection, ví dụ rel customers.
3. Đọc link search của collection.
4. GET search resource để xem các finder được công bố.
5. Theo link finder và truyền query parameter.

Ví dụ minh họa search resource:

    {
      "_links": {
        "self": {
          "href": "http://localhost:8080/customers/search"
        },
        "findByCity": {
          "href": "http://localhost:8080/customers/search/findByCity{?city}",
          "templated": true
        }
      }
    }

Trong ví dụ, findByCity là relation của finder. templated=true cho biết href là URI template có tham số city.

Tên path và rel mặc định thường được suy ra từ tên method. Có thể tùy chỉnh bằng @RestResource(path = ..., rel = ...). Luôn kiểm tra search resource thực tế thay vì giả định URL hoặc relation.

## 3. Đặt câu truy vấn trong repository bằng @Query

@Query cho phép khai báo câu truy vấn ngay trên method. Với Spring Data JPA, giá trị mặc định là JPQL.

Ví dụ entity:

    @Entity
    public class Customer {

        @Id
        @GeneratedValue
        private Long id;

        private String name;
        private String email;
        private String city;
    }

Repository định nghĩa truy vấn tìm khách hàng theo một phần tên:

    public interface CustomerRepository
            extends JpaRepository<Customer, Long> {

        @Query("""
            select c
            from Customer c
            where lower(c.name) like lower(concat('%', :keyword, '%'))
            """)
        List<Customer> searchByName(
            @Param("keyword") String keyword
        );
    }

Trong truy vấn:

- Customer là entity name trong JPQL, không nhất thiết là tên bảng.
- c.name là thuộc tính Java của entity.
- :keyword là named parameter.
- @Param("keyword") liên kết tham số method với tên parameter trong query.

JPQL làm việc với entity và thuộc tính, không trực tiếp với tên bảng và cột như SQL. Nếu viết SQL native, cần chỉ rõ nativeQuery = true.

Text block """ trong ví dụ yêu cầu Java 15 trở lên. Với phiên bản Java cũ hơn, có thể dùng chuỗi một dòng hoặc nối chuỗi thông thường.

## 4. Truyền tham số bằng @Param

Nên khai báo @Param tường minh khi query dùng named parameter. Ví dụ:

    @Query("select c from Customer c where c.city = :city")
    List<Customer> searchByCity(
        @Param("city") String city
    );

Method parameter city được bind vào :city trong JPQL.

Spring Data JPA cũng có thể suy ra tên tham số từ metadata biên dịch trong một số cấu hình, nhưng @Param làm rõ hợp đồng giữa method và query, tránh phụ thuộc vào việc compiler có giữ tên parameter hay không.

Khi gọi qua REST, tên query parameter thường tương ứng với tên được khai báo bằng @Param:

    GET /customers/search/searchByCity?city=Hanoi

Nếu method dùng @RestResource(path = "by-city"), path finder thay đổi thành /customers/search/by-city?city=Hanoi trong ví dụ. Tên parameter vẫn là city.

Giá trị có dấu cách, dấu &, dấu ? hoặc ký tự Unicode cần được URL-encode. Client nên dùng thư viện URL hoặc URI template để mã hóa tham số, không nối chuỗi query bằng tay.

## 5. Tùy chỉnh rel và path của query method

Có thể dùng @RestResource trên method để đặt tên relation và path dễ hiểu hơn:

    public interface CustomerRepository
            extends JpaRepository<Customer, Long> {

        @Query("""
            select c
            from Customer c
            where lower(c.name) like lower(concat('%', :keyword, '%'))
            """)
        @RestResource(
            path = "by-name",
            rel = "byName"
        )
        List<Customer> searchByName(
            @Param("keyword") String keyword
        );
    }

Search resource có thể công bố link theo rel byName, với href template chứa parameter keyword. Client nên đọc link đó từ response:

    {
      "_links": {
        "byName": {
          "href": "http://localhost:8080/customers/search/by-name{?keyword}",
          "templated": true
        }
      }
    }

Để gọi finder, mở rộng URI template với giá trị cần tìm. Ví dụ URL sau minh họa kết quả đã mở rộng:

    GET /customers/search/by-name?keyword=an

path điều khiển segment URL của finder; rel điều khiển tên quan hệ trong HAL. Hai giá trị phục vụ mục đích khác nhau.

## 6. Phân trang cho truy vấn trả về nhiều kết quả

Nếu query có thể trả về nhiều bản ghi, có thể dùng Page<T> và nhận Pageable:

    public interface CustomerRepository
            extends JpaRepository<Customer, Long> {

        @Query("""
            select c
            from Customer c
            where c.city = :city
            """)
        Page<Customer> searchByCity(
            @Param("city") String city,
            Pageable pageable
        );
    }

Spring Data REST hỗ trợ các tham số phân trang cho query method phù hợp. Request minh họa:

    GET /customers/search/searchByCity?city=Hanoi&page=0&size=10

Response collection thường có thông tin trong page và các link điều hướng như next khi còn trang tiếp theo.

Không nên tự tăng page number nếu server đã cung cấp link next. Client có thể theo href của link đó để tiếp tục lấy trang.

Kiểu trả về và chữ ký method quyết định khả năng phân trang. Nếu dùng List<T> thay cho Page<T>, client không nhận được đầy đủ metadata tổng số trang theo cách tương tự. Hãy chọn kiểu kết quả phù hợp với nhu cầu API.

## 7. Dùng native SQL khi thật sự cần

@Query của Spring Data JPA cũng hỗ trợ SQL native bằng nativeQuery = true:

    @Query(
        value = "select * from customers where city = :city",
        countQuery = "select count(*) from customers where city = :city",
        nativeQuery = true
    )
    Page<Customer> searchByCityNative(
        @Param("city") String city,
        Pageable pageable
    );

Trong native query, customers là tên bảng và city phải là tên cột trong schema thực tế. countQuery cung cấp truy vấn đếm để Spring Data tính tổng số phần tử khi trả về Page.

Native SQL hữu ích khi cần tính năng riêng của database hoặc câu truy vấn không phù hợp với JPQL. Tuy nhiên, nó gắn repository với schema và dialect cụ thể hơn. Ưu tiên JPQL khi truy vấn có thể biểu diễn rõ ràng qua entity model.

## 8. Ẩn một query method khỏi REST API

Không phải query method nội bộ nào cũng nên trở thành endpoint công khai. Có thể đặt @RestResource(exported = false) trên method:

    public interface CustomerRepository
            extends JpaRepository<Customer, Long> {

        @Query("select c from Customer c where c.email = :email")
        @RestResource(exported = false)
        List<Customer> findInternalByEmail(
            @Param("email") String email
        );
    }

Method vẫn có thể được sử dụng bên trong ứng dụng thông qua repository, nhưng Spring Data REST không công bố finder đó như search resource.

Cần phân biệt:

- @RestResource(exported = false) trên method ẩn query method hoặc association tương ứng.
- @RepositoryRestResource(exported = false) trên repository ẩn repository resource theo cấu hình export.
- @Query chỉ định nghĩa truy vấn; nó không tự thay thế cơ chế xác thực hoặc phân quyền.

Ẩn một finder không đồng nghĩa với bảo vệ toàn bộ API. Những repository method khác vẫn có thể được công bố. Hãy cấu hình Spring Security cho endpoint và dữ liệu nhạy cảm theo yêu cầu ứng dụng.

## 9. Khám phá và gọi query resource từ client

Client nên khám phá finder qua HAL thay vì ghép URL. Ví dụ, đọc collection response, sau đó theo link search:

    const collection = await fetch(collectionUrl, {
      headers: { Accept: "application/hal+json" }
    }).then(response => response.json());

    const searchHref = collection._links?.search?.href;

    if (!searchHref) {
      throw new Error("Collection không công bố search resource");
    }

    const searchUrl = new URL(searchHref, collectionUrl);

    const searchResponse = await fetch(searchUrl, {
      headers: { Accept: "application/hal+json" }
    });

    if (!searchResponse.ok) {
      throw new Error("Không thể đọc search resource");
    }

    const searchResource = await searchResponse.json();

Search resource có thể trả về:

    {
      "_links": {
        "byName": {
          "href": "http://localhost:8080/customers/search/by-name{?keyword}",
          "templated": true
        }
      }
    }

Nếu link là URI template, hãy mở rộng template bằng thư viện URI template hoặc hypermedia phù hợp. Ví dụ URL đã mở rộng:

    GET /customers/search/by-name?keyword=An

Client không nên tự tạo path /customers/search/by-name nếu server đã cung cấp href. Việc dùng rel giúp client tiếp tục hoạt động khi server đổi path nhưng vẫn giữ relation trong hợp đồng hypermedia.

## 10. Kiểm tra query method bằng curl

Có thể xem search resource:

    curl -i \
      -H "Accept: application/hal+json" \
      http://localhost:8080/customers/search

Sau khi đọc href của finder từ response, gọi URL finder với tham số hợp lệ. Ví dụ:

    curl -i \
      -H "Accept: application/hal+json" \
      "http://localhost:8080/customers/search/by-name?keyword=An"

Các URL trên chỉ minh họa theo cấu hình path = "by-name". Khi kiểm tra ứng dụng thật, dùng href từ search resource và mã hóa query parameter đúng cách.

Kiểm tra các điểm sau:

1. Search resource có công bố rel của finder mong muốn hay không.
2. Href có đúng path và có đánh dấu templated khi chứa URI template hay không.
3. Query parameter có tên khớp với @Param hay không.
4. Kết quả có đúng entity hoặc collection mong đợi hay không.
5. Nếu method trả Page, response có metadata và link phân trang phù hợp hay không.
6. Method được đánh dấu exported = false có vắng mặt trong search resource hay không.

## 11. Lỗi thường gặp

**Nhầm JPQL với SQL**

JPQL dùng entity và thuộc tính Java; native SQL dùng bảng và cột của database. Dùng sai tên có thể làm truy vấn thất bại khi chạy.

**Tên parameter không khớp**

Nếu query dùng :keyword nhưng method bind @Param("name"), Spring Data không thể bind đúng tham số. Tên trong @Param phải khớp placeholder của query.

**Finder không xuất hiện**

Kiểm tra method có nằm trong repository được export không, có bị đánh dấu exported = false không, và Spring Data REST có công bố query methods cho repository đó không. Dùng search resource để xem danh sách finder thực tế.

**Path hoặc rel không như dự kiến**

@RestResource(path = ..., rel = ...) có thể tùy chỉnh hai giá trị. Đừng suy ra rel từ path hoặc ngược lại; đọc _links trong HAL.

**Native query phân trang thiếu count query**

Với native query trả Page, cần đảm bảo Spring Data có thể xác định tổng số bản ghi. Cung cấp countQuery tường minh khi cần, đặc biệt với truy vấn phức tạp.

**Công bố dữ liệu nhạy cảm**

Query method được export có thể trở thành endpoint có thể gọi từ bên ngoài. Không đưa dữ liệu nhạy cảm vào response và không dựa vào việc khó đoán URL để bảo vệ endpoint. Dùng exported = false khi finder không nên được công bố và cấu hình authorization phù hợp.

## 12. Bài tập thực hành

Với Customer entity có name, email và city:

1. Tạo CustomerRepository kế thừa JpaRepository<Customer, Long>.
2. Viết query JPQL tìm khách hàng theo một phần name bằng @Query.
3. Dùng @Param("keyword") để bind named parameter.
4. Tùy chỉnh finder path thành by-name và rel thành byName.
5. Khởi động ứng dụng, theo search link từ collection và xác nhận finder được công bố.
6. Gọi finder với keyword có dấu cách hoặc ký tự đặc biệt để kiểm tra URL encoding.
7. Tạo một query method khác với @RestResource(exported = false) và xác nhận method không xuất hiện trong search resource.
8. Tạo một finder trả Page<Customer>, truyền Pageable và theo link next nếu có.

Câu hỏi tự kiểm tra:

- @Query giữ logic truy vấn ở tầng nào?
- JPQL khác native SQL ở cách tham chiếu entity và bảng ra sao?
- @Param liên kết method argument với placeholder nào?
- path và rel khác nhau thế nào?
- Làm sao ẩn một query method khỏi Spring Data REST?
- Vì sao query method công bố ra REST API vẫn cần authorization?

## 13. Ghi nhớ

- Query method của repository có thể được Spring Data REST công bố dưới search resource.
- @Query đặt câu truy vấn trong repository; JPQL là mặc định của Spring Data JPA.
- @Param bind named parameter rõ ràng giữa method và query.
- @RestResource(path, rel) tùy chỉnh finder path và relation trong HAL.
- Page<T> cùng Pageable hỗ trợ truy vấn phân trang.
- nativeQuery = true dùng SQL của database; cân nhắc count query khi trả Page.
- @RestResource(exported = false) ẩn query method khỏi REST export.
- Công bố finder không thay thế xác thực và phân quyền.

## Tài liệu tham khảo

- Spring Data JPA Reference — Declaring query methods: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
- Spring Data REST Reference — Exposing repository resources: https://docs.spring.io/spring-data/rest/reference/
- Spring Data Commons — Query method and repository abstractions: https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html
