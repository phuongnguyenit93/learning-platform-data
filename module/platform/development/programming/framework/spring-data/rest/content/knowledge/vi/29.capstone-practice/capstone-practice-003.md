# Thiết lập và gỡ quan hệ giữa sản phẩm, danh mục bằng URI

## 1. Mục tiêu

Trong một API Spring Data REST, một sản phẩm thường thuộc về một danh mục. Ví dụ, sản phẩm “Notebook” được gắn vào danh mục “Stationery”. Ta cần tạo hai resource độc lập, sau đó liên kết hoặc gỡ liên kết chúng qua HTTP API.

Spring Data REST cung cấp association resource cho mỗi association mà nó nhận diện trên domain resource. Với quan hệ Product.category, resource sản phẩm có một link tên category. Client dùng URI của link association để thao tác và gửi URI của resource Category trong body. Cách làm này giữ cho client làm việc với resource URI do server công bố thay vì phải gửi toàn bộ object Category hoặc tự đoán ID.

Ví dụ các URI trong tài liệu:

- Collection sản phẩm: http://localhost:8080/products
- Resource sản phẩm: http://localhost:8080/products/42
- Collection danh mục: http://localhost:8080/categories
- Resource danh mục: http://localhost:8080/categories/3
- Association resource của category trên sản phẩm 42: http://localhost:8080/products/42/category

Các ID và host chỉ là ví dụ. Trong ứng dụng thực tế, hãy khám phá URI từ HAL response và dùng đúng URI mà API trả về.

## 2. Mô hình dữ liệu Product và Category

Ví dụ dưới đây dùng Spring Data JPA. Một sản phẩm có thể chưa được phân loại hoặc thuộc một danh mục; nhiều sản phẩm có thể cùng tham chiếu một danh mục. Vì vậy Product.category là quan hệ many-to-one và là phía sở hữu liên kết trong mapping JPA.

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;

@Entity
public class Category {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Category() {
    }

    public Category(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;

@Entity
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    @ManyToOne(fetch = FetchType.LAZY, optional = true)
    @JoinColumn(name = "category_id", nullable = true)
    private Category category;

    protected Product() {
    }

    public Product(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public Category getCategory() {
        return category;
    }
}
~~~

Trong ví dụ này:

- @ManyToOne thể hiện nhiều Product có thể cùng tham chiếu một Category.
- optional = true cho phép sản phẩm không có danh mục.
- nullable = true cho phép cột category_id trong database nhận NULL. Schema migration thực tế cũng phải cho phép giá trị NULL nếu muốn hỗ trợ unlink.
- Product là phía sở hữu quan hệ vì @JoinColumn nằm trên Product.category. Khi thay đổi liên kết qua association resource của Product, Spring Data REST cập nhật thuộc tính này.
- Category không cần có collection products để thực hiện luồng link/unlink này. Nếu bổ sung quan hệ hai chiều bằng @OneToMany(mappedBy = "category"), đó là phía inverse; code nghiệp vụ tự cập nhật hai phía trong bộ nhớ khi cần.

Không thêm CascadeType.REMOVE từ Product sang Category chỉ để hỗ trợ link/unlink. Một Category có thể được nhiều Product dùng chung; gỡ liên kết một sản phẩm không có nghĩa là xóa Category. Tương tự, xóa một Product không nên tự động xóa Category đang được dùng bởi sản phẩm khác.

Nếu muốn Product bắt buộc phải thuộc một Category, cấu hình optional = false và cột database NOT NULL. Trong trường hợp đó, thao tác DELETE association để gỡ category không phù hợp và Spring Data REST có thể từ chối vì association không optional.

## 3. Export repository để Spring Data REST công bố resource

Tạo repository cho hai loại domain object:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(path = "products")
public interface ProductRepository extends JpaRepository<Product, Long> {
}
~~~

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(path = "categories")
public interface CategoryRepository extends JpaRepository<Category, Long> {
}
~~~

Spring Data REST export repository thành collection resource và item resource. Với cấu hình mặc định, các repository public phù hợp sẽ được phát hiện; @RepositoryRestResource ở đây làm rõ tên path mà ví dụ sử dụng. Nếu ứng dụng đặt detection strategy chỉ export repository có annotation, hai repository này đã có annotation tương ứng.

Một association chỉ có thể được thao tác như resource link khi association được Spring Data REST nhận diện và resource đích có thể được truy cập qua repository đã export. Nếu association không xuất hiện trong HAL, kiểm tra mapping domain, repository của kiểu đích, detection strategy và cấu hình exported của property.

Có thể đổi tên path hoặc relation bằng @RestResource trên property association. Nếu không tùy biến, tên association resource mặc định theo tên property, ở ví dụ này là category.

## 4. Khám phá URI bằng HAL trước khi cập nhật

Bắt đầu từ root API:

~~~bash
curl -i -H 'Accept: application/hal+json' \
  http://localhost:8080/
~~~

Root response công bố các collection link, ví dụ:

~~~json
{
  "_links": {
    "products": {
      "href": "http://localhost:8080/products"
    },
    "categories": {
      "href": "http://localhost:8080/categories"
    }
  }
}
~~~

Tạo hoặc tìm một Category, sau đó lấy URI của resource từ response Location hoặc link self:

~~~bash
curl -i -X POST http://localhost:8080/categories \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/hal+json' \
  --data '{"name":"Stationery"}'
~~~

Response tạo resource thường có status 201 Created và header Location trỏ đến resource vừa tạo. Nếu response có HAL body, dùng link self trong body. Ví dụ minh họa:

    Location: http://localhost:8080/categories/3

Tạo một Product chưa có category:

~~~bash
curl -i -X POST http://localhost:8080/products \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/hal+json' \
  --data '{"name":"Notebook"}'
~~~

Giả sử server trả về:

    Location: http://localhost:8080/products/42

Đọc resource sản phẩm:

~~~bash
curl -i -H 'Accept: application/hal+json' \
  http://localhost:8080/products/42
~~~

HAL representation của Product có thể công bố link association:

~~~json
{
  "name": "Notebook",
  "_links": {
    "self": {
      "href": "http://localhost:8080/products/42"
    },
    "category": {
      "href": "http://localhost:8080/products/42/category"
    }
  }
}
~~~

Link category ở đây là URI của association resource, không phải URI của Category. Client cần lưu cả hai URI:

- URI association: nơi gửi PUT hoặc DELETE để thay đổi liên kết.
- URI Category: URI resource đích được gửi trong body của PUT.

Không hard-code đường dẫn association trong frontend nếu có thể follow link từ HAL. Khi server đổi base path hoặc tên association qua @RestResource, client dựa vào link được công bố sẽ ít bị ảnh hưởng hơn.

## 5. Gắn Product vào Category bằng PUT và text/uri-list

Để gắn sản phẩm 42 vào danh mục 3, gửi PUT đến association URI của sản phẩm. Body chứa URI của Category và Content-Type là text/uri-list:

~~~bash
curl -i -X PUT \
  http://localhost:8080/products/42/category \
  -H 'Content-Type: text/uri-list' \
  --data-binary 'http://localhost:8080/categories/3'
~~~

Ý nghĩa của request:

- PUT target là association resource /products/42/category.
- Body là URI resource đích /categories/3.
- Content-Type phải là text/uri-list.
- Với quan hệ to-one như Product.category, chỉ gửi một URI.

Spring Data REST dùng URI trong body để tìm resource Category và gắn resource đó vào association. Khi association đang trỏ đến một Category khác, PUT cập nhật liên kết sang Category được chỉ định.

Một association to-one không thể nhận nhiều URI. Nếu body chứa nhiều URI cho Product.category, Spring Data REST trả 400 Bad Request. Nếu cần nhiều resource liên kết, domain property phải là collection association và cách gọi API phải phù hợp với collection semantics.

Sau khi PUT thành công, đọc lại sản phẩm hoặc association resource:

~~~bash
curl -i -H 'Accept: application/hal+json' \
  http://localhost:8080/products/42/category
~~~

Hoặc đọc item resource:

~~~bash
curl -i -H 'Accept: application/hal+json' \
  http://localhost:8080/products/42
~~~

Xác nhận association trỏ đến URI Category mong muốn. Không chỉ dựa vào status code; đọc lại resource giúp xác nhận quan hệ đã được lưu trong persistence layer.

Nếu client dùng thư viện HTTP, thiết lập header và body tương đương:

~~~text
Method: PUT
URL: <association href lấy từ HAL>
Content-Type: text/uri-list
Body: <category self href lấy từ HAL>
~~~

Không gửi JSON object như {"id":3} đến association resource. Endpoint association nhận URI list, không nhận một object JSON Category.

## 6. Gỡ liên kết Product khỏi Category bằng DELETE

Với Product.category là association optional, gửi DELETE tới đúng association resource:

~~~bash
curl -i -X DELETE \
  http://localhost:8080/products/42/category
~~~

DELETE gỡ liên kết giữa Product và Category. Nó không xóa resource Category khỏi repository và không xóa các sản phẩm khác đang dùng cùng Category.

Sau thao tác, GET lại Product và kiểm tra trạng thái category. Ứng dụng có thể biểu diễn association không còn được gắn tùy theo representation và cấu hình; điều quan trọng là Product.category đã rỗng trong persistence layer.

Nếu quan hệ là bắt buộc, thao tác DELETE không thể làm cho property thành null. Spring Data REST ghi nhận 405 Method Not Allowed khi association không optional. Trong trường hợp đó, client cần gắn sang Category hợp lệ khác bằng PUT hoặc dùng quy trình nghiệp vụ riêng để thay đổi dữ liệu bắt buộc.

Nếu schema database đặt category_id NOT NULL nhưng entity khai báo optional = true, request unlink có thể vượt qua validation ở tầng object rồi thất bại khi ghi database. Annotation và schema migration phải nhất quán.

## 7. Phân biệt PUT, POST và DELETE trên association resource

Spring Data REST hỗ trợ GET, PUT, POST và DELETE trên association resource:

| Method | Mục đích | Content-Type | Phạm vi |
|---|---|---|---|
| GET | Đọc trạng thái liên kết | application/hal+json hoặc application/json | To-one và collection |
| PUT | Gắn URI resource vào association | text/uri-list | Một URI cho to-one; URI list cho association phù hợp |
| POST | Thêm một phần tử mới vào collection association | text/uri-list | Chỉ collection association |
| DELETE | Gỡ association | Không cần body | Association resource |

Các quy tắc cần nhớ:

- PUT là lựa chọn cho Product.category vì đây là to-one association.
- POST chỉ được hỗ trợ với collection association và thêm một phần tử vào collection.
- PUT với nhiều URI cho to-one association trả về 400 Bad Request.
- DELETE gỡ association; nếu association là non-optional, Spring Data REST có thể trả 405 Method Not Allowed.
- GET association resource hỗ trợ application/hal+json và application/json.
- PUT và POST association resource nhận text/uri-list, không nhận JSON object.

Nếu Category có collection association products, POST lên URI association của collection có thể thêm một Product bằng URI của Product. Tuy nhiên, với JPA mapping hai chiều, phải chú ý owning side. Trong ví dụ Product.category, Product là owning side. Việc sửa riêng collection inverse Category.products trong bộ nhớ không tự động bảo đảm khóa ngoại category_id được cập nhật. Thiết kế API và mapping nên cập nhật đúng phía sở hữu hoặc đồng bộ hai phía trong logic nghiệp vụ.

DELETE trên association resource là thao tác unbind theo contract của Spring Data REST. Nếu ứng dụng cần xóa riêng một phần tử trong một collection association, hãy thiết kế và kiểm thử semantics cụ thể của collection trong model; đừng giả định rằng DELETE item resource sẽ tự động xóa quan hệ mà không xóa entity đích.

## 8. Kiểm thử tích hợp

Nên kiểm tra qua HTTP endpoint thực của Spring Data REST để xác nhận association resource được export và URI binding hoạt động. Ví dụ các ca kiểm thử cho model Product.category:

| Ca kiểm thử | Request | Kết quả cần xác nhận |
|---|---|---|
| Khám phá link | GET /products/{id} | HAL có link category trỏ tới association resource |
| Đọc liên kết | GET /products/{id}/category | Trả trạng thái association hiện tại |
| Gắn category | PUT association với một URI Category và text/uri-list | Request thành công; Product tham chiếu đúng Category |
| Đổi category | PUT association với URI Category khác | Product tham chiếu Category mới |
| Gỡ category optional | DELETE association | Product.category trở thành null; Category vẫn tồn tại |
| Nhiều URI cho to-one | PUT body có hai URI | 400 Bad Request |
| Gỡ category bắt buộc | DELETE association non-optional | Bị từ chối, thường là 405 theo contract |
| Sai media type | PUT gửi JSON object thay vì text/uri-list | Request bị từ chối do media type/body không phù hợp |

Ví dụ integration test dưới đây giả định ứng dụng đã có ProductRepository và CategoryRepository. Dùng repository để tạo dữ liệu kiểm thử, gọi HTTP association endpoint, rồi đọc lại dữ liệu đã lưu.

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ProductCategoryAssociationTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ProductRepository products;

    @Autowired
    CategoryRepository categories;

    @Test
    void bindsAndUnbindsCategoryByUri() throws Exception {
        Category category = categories.save(new Category("Stationery"));
        Product product = products.save(new Product("Notebook"));

        String associationPath =
                "/products/" + product.getId() + "/category";
        String categoryUri =
                "http://localhost/categories/" + category.getId();

        mockMvc.perform(put(associationPath)
                .contentType("text/uri-list")
                .content(categoryUri))
            .andExpect(status().is2xxSuccessful());

        Product linked = products.findById(product.getId()).orElseThrow();
        assertThat(linked.getCategory().getId()).isEqualTo(category.getId());

        mockMvc.perform(delete(associationPath))
            .andExpect(status().is2xxSuccessful());

        Product unlinked = products.findById(product.getId()).orElseThrow();
        assertThat(unlinked.getCategory()).isNull();

        assertThat(categories.findById(category.getId())).isPresent();
    }
}
~~~

Trong một dự án thực tế, hãy cấu hình test database cô lập và kiểm tra transaction boundary. Nếu entity relation được lazy-load, thực hiện assertion trong transaction hoặc dùng query/projection phù hợp. Ví dụ test giả định property category có thể null và schema test cho phép category_id NULL.

Nên bổ sung test cho association bắt buộc, nhiều URI trong to-one association và authorization. Nếu dùng Spring Security, gọi endpoint bằng principal có quyền và kiểm tra cả trường hợp 401/403. Không để việc export association resource vô tình cho phép người dùng gắn sản phẩm vào danh mục mà họ không được phép sử dụng.

## 9. Troubleshooting

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra và xử lý |
|---|---|---|
| GET Product không có link category | Association không được Spring Data REST nhận diện hoặc bị ẩn | Kiểm tra mapping JPA, repository Category đã export, detection strategy và @RestResource(exported = false). |
| PUT trả 415 Unsupported Media Type | Dùng application/json thay vì text/uri-list | Đặt Content-Type: text/uri-list và gửi URI thuần trong body. |
| PUT trả 400 Bad Request | Gửi nhiều URI cho association to-one hoặc body URI list không hợp lệ | Gửi đúng một URI Category cho Product.category; kiểm tra newline và cú pháp URI. |
| PUT không tìm thấy Category | URI đích sai, resource chưa tồn tại hoặc repository không export | GET URI Category trước, dùng self href do HAL công bố và kiểm tra repository mapping. |
| PUT thành công nhưng dữ liệu không đổi | Gửi nhầm URI association, kiểm tra sai database hoặc mapping không phải owning side | Đọc lại association resource, kiểm tra Product.category và khóa ngoại trong database test. |
| DELETE trả 405 | Association được khai báo non-optional hoặc thao tác không được export | Kiểm tra optional, nullable, schema constraint và contract của association resource. |
| DELETE gây lỗi constraint ở database | Entity cho phép null nhưng cột category_id vẫn NOT NULL | Đồng bộ JPA mapping và schema migration; chỉ cho unlink nếu nghiệp vụ cho phép null. |
| Product bị xóa kéo theo Category | Cascade REMOVE được cấu hình trên quan hệ nhiều sản phẩm dùng chung | Xem lại cascade; không cascade remove từ Product sang Category dùng chung. |
| Association link không có trong HAL | Repository đích không export, property bị ẩn hoặc mapping không phải association linkable | Kiểm tra repository và property mapping; xem response HAL của item resource. |
| Frontend gửi id thay vì URI | Client coi association như foreign-key JSON field | Lấy Category self href từ HAL và gửi URI đó bằng text/uri-list. |
| Product và Category hiển thị không đồng bộ trong JPA | Quan hệ hai chiều chỉ cập nhật một phía trong bộ nhớ | Cập nhật owning side Product.category; nếu có collection inverse, đồng bộ hai phía trong domain helper/service. |

## 10. Checklist triển khai

- [ ] ProductRepository và CategoryRepository được export đúng path.
- [ ] Product.category được Spring Data REST công bố như association link.
- [ ] Client khám phá association href và Category self href từ HAL.
- [ ] Request PUT dùng Content-Type text/uri-list.
- [ ] To-one association chỉ nhận đúng một URI.
- [ ] Product.category optional và cột category_id nullable nếu nghiệp vụ cho phép unlink.
- [ ] DELETE association chỉ gỡ liên kết, không xóa Category.
- [ ] Mapping JPA cập nhật owning side.
- [ ] Không dùng cascade remove để xóa Category dùng chung.
- [ ] Authorization kiểm tra quyền trên cả Product và Category đích.
- [ ] Integration test bao gồm link, đổi link, unlink và trường hợp lỗi.
- [ ] Client đọc lại resource sau thao tác để xác nhận trạng thái liên kết.

## 11. Tài liệu tham khảo chính thức

- [Spring Data REST — Repository resources / The Association Resource](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): các association sub-resource, method GET/PUT/POST/DELETE, media type text/uri-list và hành vi bind/unbind.
- [Spring Data REST — Getting Started](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html): repository detection, export resource và cấu hình base path.
- [Jakarta Persistence — ManyToOne](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/manytoone): mapping quan hệ many-to-one và thuộc tính optional.
- [Jakarta Persistence — JoinColumn](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/joincolumn): mapping foreign-key column và nullable constraint.
- [Spring Data REST — Customizing](https://docs.spring.io/spring-data/rest/reference/customizing/index.html): tùy biến cách Spring Data REST export repository, resource và association.
