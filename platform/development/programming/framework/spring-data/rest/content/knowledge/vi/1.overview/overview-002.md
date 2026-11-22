# Vai trò của tài nguyên, biểu diễn, liên kết và phương thức HTTP trong Spring Data REST

Spring Data REST biến các Spring Data repository thành một API REST có khả năng khám phá bằng hypermedia. Repository cung cấp các thao tác dữ liệu; Spring Data REST công bố những thao tác phù hợp dưới dạng tài nguyên, tạo biểu diễn JSON cho tài nguyên và thêm liên kết để client tìm đường đi tiếp. Vì vậy, khi đọc một phản hồi Spring Data REST, cần hiểu đồng thời **tài nguyên nào đang được truy cập**, **biểu diễn đang mô tả điều gì**, **các liên kết dẫn tới đâu** và **phương thức HTTP đang yêu cầu hành động nào**.

## 1. Bốn khái niệm cốt lõi

| Khái niệm | Ý nghĩa | Câu hỏi cần trả lời |
|---|---|---|
| Tài nguyên (resource) | Một đối tượng hoặc tập đối tượng được định danh bằng URI và có thể được truy cập qua HTTP | Client đang làm việc với collection, item, association hay search resource nào? |
| Biểu diễn (representation) | Dữ liệu mô tả trạng thái của tài nguyên tại thời điểm phản hồi, thường ở dạng JSON/HAL | Trường dữ liệu, liên kết và metadata nào đang được trả về? |
| Liên kết (link) | Một URI được gắn với quan hệ (relation) để client khám phá tài nguyên hoặc hành động liên quan | Client nên đi tới URI nào tiếp theo và URI đó có ý nghĩa gì? |
| Phương thức HTTP | Ngữ nghĩa của thao tác client gửi tới tài nguyên | Client muốn đọc, tạo, thay thế, cập nhật một phần, xóa hay thay đổi quan hệ? |

Các khái niệm này liên quan nhưng không thay thế nhau. Ví dụ, tài nguyên sản phẩm có URI /products/1; biểu diễn của nó có thể chứa tên và giá; liên kết category dẫn tới tài nguyên quan hệ danh mục; GET đọc biểu diễn đó còn PATCH thay đổi một phần trạng thái.

## 2. Repository được công bố thành tài nguyên như thế nào?

Spring Data REST phát hiện các repository được phép export và ánh xạ chúng thành các endpoint. Một repository thường kế thừa CrudRepository, PagingAndSortingRepository hoặc JpaRepository. Các phương thức repository hiện có quyết định những thao tác HTTP nào có thể được công bố.

Giả sử ứng dụng có entity Product và repository sau:

~~~java
import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

@RepositoryRestResource(
    path = "products",
    collectionResourceRel = "products",
    itemResourceRel = "product"
)
public interface ProductRepository extends JpaRepository<Product, Long> {

    @RestResource(path = "by-name", rel = "by-name")
    List<Product> findByNameContainingIgnoreCase(@Param("name") String name);
}
~~~

Đây là phần khai báo repository, không phải chương trình độc lập: entity Product, cấu hình Spring Boot và dependency Spring Data REST phải tồn tại trong ứng dụng. Repository trên cho phép Spring Data REST công bố collection sản phẩm, từng sản phẩm và query method tìm theo tên. Annotation RepositoryRestResource tùy chỉnh đường dẫn và tên relation; RestResource tùy chỉnh đường dẫn và relation của query method.

Nếu không chỉ định đường dẫn, Spring Data REST thường tạo đường dẫn collection từ tên đơn giản của domain class sau khi chuyển chữ thường và số nhiều hóa. Có thể đặt base path, chẳng hạn spring.data.rest.base-path=/api; khi đó root và các endpoint nằm dưới /api.

Các loại tài nguyên thường gặp:

- **Root resource**: điểm bắt đầu của API, thường là / hoặc base path đã cấu hình. Nó trả về các liên kết tới repository được export.
- **Collection resource**: đại diện cho một tập entity, ví dụ /products.
- **Item resource**: đại diện cho một entity cụ thể, ví dụ /products/1.
- **Association resource**: đại diện cho quan hệ của một item, ví dụ /products/1/category.
- **Search resource**: công bố các query method của repository, ví dụ /products/search; mỗi query method có endpoint riêng.

Đường dẫn trên là ví dụ. Tên repository, annotation, base path và cấu hình ứng dụng quyết định URI thực tế. Client nên khám phá link do server trả về thay vì tự suy ra mọi đường dẫn.

## 3. Biểu diễn tài nguyên: JSON và HAL

Spring Data REST mặc định sử dụng HAL (Hypertext Application Language) để biểu diễn tài nguyên. Client thường yêu cầu HAL bằng header Accept: application/hal+json. Các endpoint cũng hỗ trợ application/json ở những thao tác được tài liệu Spring Data REST công bố.

Một tài liệu HAL thường có ba phần:

- _links: các liên kết được đặt tên theo relation. Mỗi link có href; link có thể là URI template và khi đó có thêm templated: true.
- _embedded: các tài nguyên liên quan được nhúng trực tiếp trong biểu diễn, thường dùng cho phần tử của collection.
- page: metadata phân trang như kích thước trang, tổng số phần tử, tổng số trang và chỉ số trang hiện tại.

Ví dụ phản hồi ở root:

~~~json
{
  "_links": {
    "products": {
      "href": "http://localhost:8080/products"
    }
  }
}
~~~

Client biết collection sản phẩm qua relation products. Nó không cần tự tạo URI từ một quy tắc đặt tên.

Ví dụ phản hồi collection:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/products"
    },
    "search": {
      "href": "http://localhost:8080/products/search"
    }
  },
  "_embedded": {
    "products": [
      {
        "name": "Keyboard",
        "price": 1290000,
        "_links": {
          "self": {
            "href": "http://localhost:8080/products/1"
          },
          "category": {
            "href": "http://localhost:8080/products/1/category"
          }
        }
      }
    ]
  },
  "page": {
    "size": 20,
    "totalElements": 1,
    "totalPages": 1,
    "number": 0
  }
}
~~~

Đây là ví dụ minh họa hình dạng dữ liệu; link category chỉ xuất hiện nếu domain model có association tương ứng được Spring Data REST công bố. Relation trong _embedded thường lấy từ collectionResourceRel hoặc quy ước tên của repository.

Ví dụ biểu diễn một item:

~~~json
{
  "name": "Keyboard",
  "price": 1290000,
  "_links": {
    "self": {
      "href": "http://localhost:8080/products/1"
    },
    "category": {
      "href": "http://localhost:8080/products/1/category"
    }
  }
}
~~~

Mặc định, ID của entity không được đưa vào như một thuộc tính JSON thông thường. Link self đã cung cấp URI định danh tài nguyên. Nếu hợp đồng API cần ID xuất hiện trong payload, có thể cấu hình RepositoryRestConfiguration.exposeIdsFor(Product.class). Chỉ bật việc này khi client thực sự cần; ID trong payload và URI của tài nguyên là hai cách biểu diễn khác nhau.

Biểu diễn không nhất thiết là bản sao nguyên trạng của entity hoặc cấu trúc bảng. Nó có thể thay đổi theo projection, excerpt, cấu hình Jackson và các tùy biến của ứng dụng. Vì thế, không nên xem mọi thuộc tính Java là cam kết rằng thuộc tính đó luôn xuất hiện trong JSON.

## 4. Liên kết và cách client khám phá API

Spring Data REST áp dụng tư tưởng HATEOAS: phản hồi cung cấp liên kết để client khám phá tài nguyên kế tiếp. Client bắt đầu ở root, đọc relation cần dùng, gọi URI trong href, rồi tiếp tục theo các liên kết mới nhận được.

Một luồng điển hình:

1. Gửi GET tới root để tìm relation products.
2. Theo products.href để lấy collection.
3. Đọc các phần tử trong _embedded.products; theo self.href của một phần tử để lấy item.
4. Theo relation category để truy cập association.
5. Theo relation search để tìm các query method; theo link của query method để thực thi tìm kiếm.
6. Khi phản hồi có next, prev hoặc URI template, dùng chính link đó để chuyển trang hoặc điền tham số.

Một link gồm hai phần quan trọng: **relation** mô tả vai trò của link, còn **href** cho biết URI đích. Relation self trỏ tới chính tài nguyên hiện tại. Relation products có thể trỏ tới collection; relation category có thể trỏ tới association. Tên relation có thể tùy chỉnh bằng annotation.

Với association, cách biểu diễn phụ thuộc vào việc đối tượng liên quan có repository được export hay không. Nếu có repository, quan hệ thường được biểu diễn bằng link để client truy cập tài nguyên liên quan. Nếu không, dữ liệu của đối tượng liên quan có thể được nhúng trực tiếp. Vì vậy, không nên mặc định mọi quan hệ đều là một object lồng trong JSON hoặc mọi quan hệ đều là một endpoint riêng.

HATEOAS giúp client ít phụ thuộc vào cấu trúc URL cụ thể. Nếu server đổi base path hoặc tùy chỉnh đường dẫn repository nhưng vẫn công bố các relation phù hợp, client biết cách tiếp tục bằng cách đọc link mới. Điều đó chỉ có tác dụng khi client thực sự theo link thay vì hard-code URI.

## 5. Vai trò của các phương thức HTTP

Phương thức HTTP được áp dụng theo loại tài nguyên. Bảng sau mô tả hành vi mặc định thường gặp; thao tác thực tế còn phụ thuộc các phương thức repository có được export hay không và cấu hình của ứng dụng.

| Tài nguyên | Phương thức | Vai trò |
|---|---|---|
| Collection /products | GET | Đọc danh sách; có thể kèm phân trang và sắp xếp |
| Collection /products | POST | Tạo entity mới từ request body |
| Item /products/{id} | GET | Đọc một entity |
| Item /products/{id} | PUT | Thay thế trạng thái tài nguyên bằng request body |
| Item /products/{id} | PATCH | Cập nhật một phần trạng thái |
| Item /products/{id} | DELETE | Xóa entity được định danh bởi URI |
| Association /products/{id}/category | GET | Đọc trạng thái quan hệ |
| Association /products/{id}/category | PUT | Gắn URI của tài nguyên liên quan vào association |
| Association dạng collection | POST | Thêm một phần tử vào association |
| Association | DELETE | Gỡ liên kết association |
| Search/query resource | GET | Thực thi query method đã được export |

### GET

GET đọc tài nguyên và không nên làm thay đổi trạng thái nghiệp vụ. Với collection, kết quả có thể là một trang thay vì toàn bộ dữ liệu. Với item, kết quả là biểu diễn của một entity. Với search resource, GET trả về các link tới query method; GET trên query method thực thi truy vấn.

### POST

POST trên collection tạo entity mới từ request body. Khi tạo thành công, server thường trả 201 Created và header Location trỏ tới URI của tài nguyên mới. Body phản hồi có thể được trả về hoặc để trống tùy Accept và cấu hình trả body khi tạo. Nếu không có body, client có thể theo Location để đọc biểu diễn mới.

POST trên association dạng collection có ý nghĩa khác: nó thêm một URI liên quan vào collection association. Không nhầm thao tác này với việc tạo một entity mới trong repository.

### PUT

PUT trên item thay thế trạng thái tài nguyên bằng dữ liệu gửi lên. Client nên gửi biểu diễn đầy đủ theo hợp đồng API; thuộc tính bị bỏ khỏi request có thể được xử lý như giá trị không có trong trạng thái mới. PUT thường phù hợp khi client biết toàn bộ trạng thái cần ghi. Spring Data REST cũng có thể trả 201 Created nếu một luồng PUT tạo tài nguyên mới; hãy kiểm tra status và Location thực tế.

PUT trên association dùng để gắn URI của tài nguyên liên quan. Association dạng một-một hoặc nhiều-một thường nhận một URI; gửi nhiều URI cho quan hệ to-one có thể dẫn tới 400 Bad Request. Media type của request association là text/uri-list, khác với JSON body dùng để cập nhật entity.

### PATCH

PATCH cập nhật một phần trạng thái của item. Những thuộc tính không có trong request thường được giữ nguyên. Spring Data REST hỗ trợ các media type như application/merge-patch+json và application/patch+json bên cạnh các dạng JSON được hỗ trợ. Hãy gửi Content-Type phù hợp với định dạng patch mà client sử dụng.

### DELETE

DELETE trên item xóa entity. DELETE trên association gỡ quan hệ giữa hai tài nguyên; nó không đồng nghĩa với xóa entity ở đầu kia của quan hệ. Việc xóa entity có kéo theo xóa dữ liệu liên quan hay không còn phụ thuộc mapping, cascade và quy tắc nghiệp vụ của ứng dụng.

### HEAD và các mã phản hồi

HEAD có thể được dùng để kiểm tra tài nguyên có sẵn mà không lấy body. Phương thức được phép không chỉ phụ thuộc HTTP nói chung mà còn phụ thuộc tài nguyên và các phương thức repository đã export. Nếu repository thiếu phương thức tương ứng hoặc phương thức bị ẩn, Spring Data REST có thể trả 405 Method Not Allowed.

Một số status thường gặp:

- 200 OK: đọc thành công; cũng có thể được dùng cho cập nhật khi server trả body.
- 201 Created: tạo tài nguyên thành công, thường đi kèm Location.
- 204 No Content: cập nhật hoặc xóa thành công nhưng server không trả body.
- 400 Bad Request: request body, URI association hoặc dữ liệu đầu vào không hợp lệ.
- 404 Not Found: URI không trỏ tới tài nguyên hiện có.
- 405 Method Not Allowed: tài nguyên không hỗ trợ phương thức đó hoặc thao tác repository tương ứng không được export.

Với PUT, PATCH và DELETE, việc trả 200 hay 204 phụ thuộc cấu hình trả body và header Accept. Không nên viết client chỉ dựa vào giả định rằng mọi lần cập nhật đều trả JSON.

## 6. Gửi request và đọc phản hồi

Các ví dụ sau giả sử ứng dụng chạy tại http://localhost:8080, repository đã export thành collection /products, và entity có các thuộc tính name, price.

Đọc root và collection:

~~~bash
curl -i -H 'Accept: application/hal+json' http://localhost:8080/
curl -i -H 'Accept: application/hal+json' http://localhost:8080/products
~~~

Tạo một sản phẩm:

~~~bash
curl -i -X POST http://localhost:8080/products -H 'Content-Type: application/json' -H 'Accept: application/hal+json' -d '{"name":"Keyboard","price":1290000}'
~~~

Đọc, thay thế, cập nhật một phần và xóa item:

~~~bash
curl -i -H 'Accept: application/hal+json' http://localhost:8080/products/1
curl -i -X PUT http://localhost:8080/products/1 -H 'Content-Type: application/json' -H 'Accept: application/hal+json' -d '{"name":"Keyboard Pro","price":1590000}'
curl -i -X PATCH http://localhost:8080/products/1 -H 'Content-Type: application/merge-patch+json' -H 'Accept: application/hal+json' -d '{"price":1490000}'
curl -i -X DELETE http://localhost:8080/products/1
~~~

Thay URI và dữ liệu theo ứng dụng thực tế. Request PUT ở ví dụ gửi cả name và price; request PATCH chỉ gửi price, vì vậy minh họa ý nghĩa cập nhật một phần. Kết quả cụ thể còn phụ thuộc validation, security, cấu hình trả body và trạng thái dữ liệu.

Gắn một category có sẵn vào sản phẩm qua association:

~~~bash
curl -i -X PUT http://localhost:8080/products/1/category -H 'Content-Type: text/uri-list' --data 'http://localhost:8080/categories/3'
~~~

Đường dẫn association lấy từ link category trong biểu diễn item. URI đích phải là URI của tài nguyên liên quan đã được export. Với association dạng collection, POST cùng media type text/uri-list có thể thêm một URI vào collection; DELETE trên association dùng để gỡ liên kết.

## 7. Phân trang, sắp xếp và tìm kiếm

Nếu repository hỗ trợ Pageable hoặc Sort, collection resource nhận các tham số:

- page: số trang, bắt đầu từ 0.
- size: số phần tử yêu cầu trong một trang; mặc định thường là 20.
- sort: thuộc tính và hướng sắp xếp, ví dụ name,asc hoặc price,desc.

Ví dụ:

~~~bash
curl -i -H 'Accept: application/hal+json' 'http://localhost:8080/products?page=0&size=10&sort=name,asc'
~~~

Phản hồi collection có metadata page và các link như next, prev khi phù hợp. Theo link được trả về để chuyển trang; điều này giúp giữ đúng các tham số phân trang và sắp xếp. Giới hạn kích thước trang và giá trị mặc định có thể được cấu hình.

Query method được công bố dưới /search. Với repository ví dụ ở trên, client có thể khám phá link by-name trong phản hồi search resource rồi gọi endpoint truy vấn với tham số name. Query method được export là tài nguyên chỉ đọc và thường được gọi bằng GET.

## 8. Projection, excerpt và dữ liệu được nhúng

Projection cho phép định nghĩa một góc nhìn của entity bằng interface có các getter được chọn. Nó giúp API chỉ trả các thuộc tính cần thiết cho một trường hợp sử dụng. Projection có thể được đăng ký tự động khi đặt cùng package entity hoặc package con, hoặc đăng ký qua cấu hình.

Excerpt là projection được áp dụng tự động cho phần tử được nhúng trong collection hoặc tài nguyên liên quan khi repository khai báo excerptProjection. Excerpt không tự động áp dụng cho item resource đơn lẻ; muốn dùng projection cho item, client cần yêu cầu projection tương ứng qua tham số projection nếu endpoint đã công bố nó.

Projection thay đổi dữ liệu trong representation, còn link vẫn có thể tồn tại để client điều hướng tới tài nguyên liên quan. Không nên xem việc nhúng một phần dữ liệu là bằng chứng rằng association đã mất endpoint riêng.

## 9. Kiểm soát endpoint và bảo mật

Spring Data REST tự động công bố nhiều thao tác từ repository, nhưng điều đó không có nghĩa mọi thao tác luôn phải mở cho mọi client.

- Dùng RepositoryRestResource(exported = false) để không export một repository.
- Dùng RestResource(exported = false) trên phương thức hoặc association để ẩn endpoint tương ứng.
- Dùng cấu hình Spring Data REST để tùy chỉnh base path, relation, media type và các phương thức HTTP được hỗ trợ.
- Dùng Spring Security để xác thực và phân quyền theo tài nguyên, phương thức hoặc nghiệp vụ.
- Dùng validation và quy tắc domain để bảo vệ dữ liệu; việc request có JSON hợp lệ không có nghĩa dữ liệu hợp lệ về nghiệp vụ.

Nếu một thao tác là quy trình nghiệp vụ nhiều bước, cần điều phối nhiều aggregate, hoặc không thể diễn đạt rõ bằng CRUD và association, hãy cân nhắc một controller/endpoint nghiệp vụ riêng. Không nên ép mọi hành động thành một thao tác repository chỉ vì Spring Data REST có thể export repository đó.

## 10. Lỗi hiểu thường gặp

- **Xem URI là cấu trúc cố định:** client hard-code /products/1 thay vì theo href. Hãy bắt đầu từ root và theo relation.
- **Đồng nhất entity với representation:** giả định mọi field trong entity, đặc biệt ID, luôn có mặt trong JSON. Representation có thể bị ảnh hưởng bởi cấu hình và projection.
- **Nhầm collection với item:** POST thường tạo phần tử trên collection; PUT, PATCH, DELETE thường tác động lên item.
- **Dùng PUT khi chỉ muốn đổi một field:** PUT mang ý nghĩa thay thế; dùng PATCH cho cập nhật một phần.
- **Nhầm xóa association với xóa entity:** DELETE trên association gỡ liên kết; DELETE trên item xóa tài nguyên được định danh.
- **Giả định mọi repository đều hỗ trợ đủ CRUD:** phương thức bị thiếu hoặc bị ẩn có thể làm endpoint không được công bố và trả 405.
- **Bỏ qua content negotiation:** thiếu hoặc sai Accept/Content-Type có thể làm body hoặc status khác kỳ vọng.
- **Bỏ qua phân trang:** collection lớn cần dùng page, size, sort và link điều hướng thay vì giả định một response chứa mọi phần tử.
- **Cho rằng tự động export đồng nghĩa an toàn:** endpoint cần được bảo vệ bằng xác thực, phân quyền và validation phù hợp.

## 11. Quy trình đọc một phản hồi Spring Data REST

Khi debug hoặc tích hợp API, lần lượt trả lời các câu hỏi sau:

1. URI hiện tại là root, collection, item, association hay search resource?
2. Content-Type cho biết server đang trả định dạng nào?
3. Các thuộc tính trong body mô tả trạng thái nào? Có projection hoặc excerpt không?
4. _links có relation nào? self, search, next, prev hoặc link association đang dẫn tới đâu?
5. Client định thực hiện thao tác nào? Phương thức HTTP có đúng với loại tài nguyên và ý nghĩa nghiệp vụ không?
6. Repository có export phương thức tương ứng không? Security, validation và cấu hình có cho phép thao tác không?
7. Status code và Location có phù hợp với kết quả mong đợi không?

Nếu hiểu được bảy điểm này, có thể đọc và sử dụng API Spring Data REST mà không cần đoán cấu trúc URL hoặc nhầm lẫn giữa dữ liệu, quan hệ và hành động.

## Tài liệu tham khảo

- [Spring Data REST Reference — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST Reference — Projections and excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Spring Data REST Reference — Paging and sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html)
- [Spring Data REST Reference — Customizing JSON output](https://docs.spring.io/spring-data/rest/reference/customizing/customizing-json-output.html)
