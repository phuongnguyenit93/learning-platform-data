# Kiểm tra API gốc, đường dẫn tài nguyên, rel và cấu trúc HAL trong Spring Data REST

Spring Data REST xuất bản repository thành các tài nguyên HTTP và dùng hypermedia để mô tả cách client khám phá, điều hướng API. Một bài kiểm thử tốt cần xác nhận điểm vào API, các liên kết mà server công bố, URI đích của từng liên kết và cấu trúc HAL mà client nhận được.

Không nên suy đoán endpoint chỉ từ tên entity hoặc tên repository. API root và các quan hệ `rel` trong HAL là hợp đồng khám phá của API. Client và test nên bắt đầu từ những liên kết server trả về, sau đó kiểm tra các URI và representation mà chúng dẫn tới.

## 1. Phân biệt API root, resource path và link relation

Ba khái niệm này liên quan với nhau nhưng có vai trò riêng:

- **API root** là điểm vào của Spring Data REST. Từ đây client khám phá các repository resource được xuất bản.
- **Resource path** là đường dẫn HTTP dùng để truy cập một collection, một item, association hoặc search resource.
- **Link relation (rel)** là tên quan hệ mô tả ý nghĩa của liên kết trong tài liệu hypermedia. Client dùng rel để tìm đúng liên kết mà không cần biết trước path cụ thể.

Ví dụ API root có thể trả về:

    {
      "_links": {
        "orders": {
          "href": "https://api.example.com/api/orders"
        },
        "customers": {
          "href": "https://api.example.com/api/customers"
        },
        "profile": {
          "href": "https://api.example.com/api/profile"
        }
      }
    }

Trong ví dụ này, `orders` và `customers` là rel; các giá trị `href` là resource path/URI mà client có thể truy cập. `profile` dẫn đến metadata mô tả API.

Nếu ứng dụng cấu hình `spring.data.rest.base-path=/api`, API root nằm dưới base path đó. Khi không cấu hình base path, điểm vào thường ở root của ứng dụng. Hãy kiểm tra cấu hình môi trường và dùng đúng base path khi viết integration test.

Đừng giả định rel luôn trùng với tên class, tên repository hoặc đoạn cuối của URL. Chúng có thể được tùy chỉnh độc lập.

## 2. Khám phá API từ root

Một client hypermedia bắt đầu bằng request đến API root và đọc các link được công bố:

    GET /api
    Accept: application/hal+json

Phản hồi HAL thường có object `_links`. Mỗi quan hệ có một `href`; một số link có thể có thuộc tính `templated: true` khi URI chứa biến cần thay thế.

Ví dụ một root response:

    {
      "_links": {
        "orders": {
          "href": "http://localhost:8080/api/orders"
        },
        "customers": {
          "href": "http://localhost:8080/api/customers"
        },
        "profile": {
          "href": "http://localhost:8080/api/profile"
        }
      }
    }

Quy trình khám phá nên là:

1. Gọi API root theo base path đã cấu hình.
2. Tìm rel của repository cần dùng, ví dụ `orders`.
3. Lấy `href` từ link đó.
4. Gọi URI vừa nhận để đọc collection.
5. Từ collection, theo các link đến item, search hoặc profile resource nếu cần.

Nếu một repository không xuất hiện ở root, kiểm tra repository có được Spring Data REST xuất bản hay không, có bị đặt `exported = false` hay không và có bị cấu hình giới hạn exposure hay không. Đừng tự tạo URL thay thế trước khi xác định repository có chủ đích được công khai hay không.

## 3. Tùy chỉnh rel và path

Spring Data REST cho phép tùy chỉnh collection rel và resource path bằng `@RepositoryRestResource`:

    @RepositoryRestResource(
        path = "customer-records",
        collectionResourceRel = "customers"
    )
    public interface CustomerRepository
            extends JpaRepository<Customer, Long> {
    }

Với cấu hình này, path collection là `customer-records`, trong khi rel mà client dùng để tìm liên kết trên API root là `customers`.

Ví dụ root có thể trả:

    {
      "_links": {
        "customers": {
          "href": "http://localhost:8080/api/customer-records"
        }
      }
    }

Tên quan hệ và URI có thể khác nhau mà vẫn đúng hợp đồng. Vì vậy test cần kiểm tra cả hai điều:

- Root có công bố rel mà API cam kết cung cấp không?
- `href` của rel đó dẫn đến đúng endpoint và endpoint trả về representation mong đợi không?

Không chỉ assert chuỗi URL cố định nếu ứng dụng có thể chạy ở host, port hoặc base path khác nhau. Nên kiểm tra path tương đối với cấu hình test hoặc theo URI được server trả về.

## 4. Kiểm tra collection resource và HAL

Khi client theo link collection, Spring Data REST thường trả về HAL collection. Với repository có dữ liệu và phân trang được bật, cấu trúc điển hình gồm:

- `_embedded`: chứa các item, được nhóm dưới collection rel.
- `_links`: chứa link self, profile, search và các link điều hướng phân trang khi có.
- `page`: chứa thông tin phân trang như size, totalElements, totalPages và number.

Ví dụ:

    {
      "_embedded": {
        "orders": [
          {
            "id": 42,
            "description": "Order example",
            "_links": {
              "self": {
                "href": "http://localhost:8080/api/orders/42"
              }
            }
          }
        ]
      },
      "_links": {
        "self": {
          "href": "http://localhost:8080/api/orders"
        },
        "profile": {
          "href": "http://localhost:8080/api/profile/orders"
        },
        "next": {
          "href": "http://localhost:8080/api/orders?page=1&size=20"
        }
      },
      "page": {
        "size": 20,
        "totalElements": 21,
        "totalPages": 2,
        "number": 0
      }
    }

Đây là ví dụ minh họa cho collection có nhiều trang; các link phân trang chỉ xuất hiện khi phù hợp với kết quả. Collection rỗng có thể không có mảng item như ví dụ, vì vậy test cấu trúc item nên chuẩn bị fixture để bảo đảm có ít nhất một bản ghi.

Tên key bên trong `_embedded` thường gắn với collection rel. Nếu rel được tùy chỉnh, key embedded cũng cần được kiểm tra theo rel đã cấu hình, không theo tên entity mặc định mà test tự đoán.

### Kiểm tra item resource

Một item resource thường có dữ liệu entity và `_links` riêng. Link `self` chỉ đến chính item; association link có thể dẫn đến tài nguyên liên quan:

    {
      "id": 42,
      "description": "Order example",
      "_links": {
        "self": {
          "href": "http://localhost:8080/api/orders/42"
        },
        "customer": {
          "href": "http://localhost:8080/api/orders/42/customer"
        }
      }
    }

Test nên xác nhận link self tồn tại, URI có thể truy cập và các association rel cần thiết được công bố. Việc association có xuất hiện hay không phụ thuộc mapping, cấu hình xuất bản và quyền truy cập.

## 5. Kiểm tra association và search links

Association link cho phép client đi từ một item đến quan hệ của nó mà không phải tự ghép URL:

    GET /api/orders/42
    Accept: application/hal+json

Từ response, client đọc rel `customer`, lấy `href`, rồi gọi URI đó để đọc Customer liên quan. Path association có thể được tùy chỉnh; rel cũng có thể được tùy chỉnh bằng `@RestResource` trên association.

Search resource thường được khám phá qua rel `search` ở collection:

    GET /api/orders

Client theo link `search`, rồi đọc các query link được công bố tại search resource. Ví dụ một query method có thể được định nghĩa:

    public interface OrderRepository
            extends JpaRepository<Order, Long> {

        @RestResource(path = "by-status", rel = "byStatus")
        List<Order> findByStatus(@Param("status") OrderStatus status);
    }

Search resource có thể công bố rel `byStatus` cùng URI template cho tham số `status`. Test nên xác nhận search link tồn tại và URI template chứa tham số mà API công bố; sau đó gọi endpoint với một giá trị hợp lệ và kiểm tra kết quả.

Không nhầm rel `search` với rel của một query method. `search` dẫn đến search resource; các rel như `byStatus` được công bố bên trong search resource để mô tả từng truy vấn.

## 6. Media type và cấu trúc HAL

Khi muốn kiểm tra HAL, gửi rõ header:

    Accept: application/hal+json

Media type HAL JSON là `application/hal+json`. Header Accept giúp test xác nhận representation hypermedia mà client thực sự yêu cầu. Nếu test chỉ kiểm tra JSON thông thường, có thể bỏ lỡ lỗi thiếu `_links` hoặc `_embedded`.

Các thành phần HAL quan trọng:

| Thành phần | Ý nghĩa | Điều cần kiểm tra |
|---|---|---|
| `_links` | Các liên kết hypermedia của resource | Rel cần thiết và href hợp lệ |
| `_embedded` | Các resource được nhúng trong representation | Collection rel và item structure |
| `self` | Link đến chính resource hiện tại | URI trỏ về đúng resource |
| `profile` | Link đến mô tả profile/metadata | Có thể theo link khi cần khám phá metadata |
| `search` | Link đến search resource | Các query rel được công bố |
| `page` | Metadata phân trang của collection | number, size và tổng số phần tử khi phân trang được bật |
| `templated` | Cho biết href là URI template | Client điền các biến theo quy ước URI template |

Một HAL document có thể chứa các thuộc tính dữ liệu nghiệp vụ bên cạnh các thành phần hypermedia. Không nên chỉ kiểm tra một field entity rồi kết luận representation HAL đã đúng. Hãy kiểm tra cả media type, link relations và cấu trúc embedded phù hợp với endpoint.

## 7. Viết integration test với MockMvc

Ví dụ sau minh họa cách kiểm tra API root và collection. Giả sử repository được công bố với rel `orders` và collection path mặc định là `orders`; nếu dự án tùy chỉnh, thay các giá trị mong đợi theo hợp đồng thật:

    import org.junit.jupiter.api.Test;
    import org.springframework.beans.factory.annotation.Autowired;
    import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
    import org.springframework.boot.test.context.SpringBootTest;
    import org.springframework.hateoas.MediaTypes;
    import org.springframework.test.web.servlet.MockMvc;

    import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
    import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
    import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
    import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

    @SpringBootTest
    @AutoConfigureMockMvc
    class SpringDataRestHypermediaTest {

        @Autowired
        MockMvc mockMvc;

        @Test
        void apiRootPublishesOrdersRelation() throws Exception {
            mockMvc.perform(get("/api")
                    .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content()
                    .contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$._links.orders.href").exists());
        }

        @Test
        void ordersCollectionHasHalStructure() throws Exception {
            mockMvc.perform(get("/api/orders")
                    .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content()
                    .contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$._links.self.href").exists())
                .andExpect(jsonPath("$._embedded.orders").isArray())
                .andExpect(jsonPath("$.page.size").exists());
        }
    }

Nếu không cấu hình base path, thay `/api` bằng API root thực tế. Nếu collection rel tùy chỉnh, thay `orders` trong JSONPath bằng rel tương ứng. Test collection cần dữ liệu fixture nếu muốn kiểm tra cấu trúc item bên trong `_embedded`; test page metadata chỉ phù hợp khi repository đang sử dụng phân trang.

### Kiểm tra item và association

Có thể kiểm tra item theo URI cố định trong fixture:

    @Test
    void orderItemPublishesSelfAndCustomerLinks() throws Exception {
        mockMvc.perform(get("/api/orders/42")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content()
                .contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._links.customer.href").exists());
    }

Trong ứng dụng thật, hãy tạo fixture có ID xác định hoặc lấy ID từ dữ liệu test. Nếu API tùy chỉnh rel association, dùng rel tùy chỉnh trong JSONPath. Để tránh khóa test vào ID sinh tự động, có thể đọc URI từ response collection hoặc root rồi follow link đó trong bước test tiếp theo.

## 8. Kiểm tra rel và href mà không phụ thuộc host

Một test dễ vỡ thường so sánh toàn bộ URL với chuỗi chứa host hoặc port cố định:

    assertEquals(
        "http://localhost:8080/api/orders",
        actualHref
    );

Cách này có thể thất bại khi test chạy trên random port, reverse proxy hoặc base path khác. Nếu host không phải một phần của hợp đồng, kiểm tra:

- Rel cần thiết có tồn tại.
- Href có scheme/host hợp lệ nếu là absolute URI, hoặc là URI tương đối có thể resolve từ API root.
- Path của href khớp resource path được cấu hình.
- Theo href đó nhận được status và media type mong đợi.

Ví dụ đọc một link từ response:

    MvcResult result = mockMvc.perform(get("/api")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andReturn();

    String body = result.getResponse().getContentAsString();
    String ordersHref = JsonPath.read(
        body, "$._links.orders.href"
    );

Trong test nhiều bước, dùng `ordersHref` lấy từ response để gọi collection thay vì tự tạo lại URL. Với MockMvc, chuyển phần path và query của URI đó thành request URI phù hợp với test context; với `TestRestTemplate` hoặc `WebTestClient`, có thể follow URI theo base URL thực tế.

Nếu API trả URI template, kiểm tra cờ `templated` và điền biến bằng URI template builder phù hợp. Không gửi nguyên template có dấu ngoặc nhọn như thể đó là URL hoàn chỉnh.

## 9. Kiểm tra cấu hình tùy chỉnh

Khi API dùng các annotation hoặc cấu hình sau, test cần phản ánh đúng hợp đồng đã khai báo:

- `@RepositoryRestResource(path = ..., collectionResourceRel = ...)`: kiểm tra collection path và root rel riêng biệt.
- `@RestResource(path = ..., rel = ...)`: kiểm tra path và rel của association hoặc query resource tương ứng.
- `spring.data.rest.base-path`: gửi request đến đúng API root dưới base path.
- `exported = false`: xác nhận repository hoặc association không được công bố nếu đó là chủ đích.
- Projection và excerpt projection: representation có thể bổ sung hoặc thay đổi các thuộc tính hiển thị; vẫn cần xác nhận link hypermedia quan trọng.
- Cấu hình phân trang: kiểm tra link điều hướng và object `page` khi endpoint trả paginated collection.

Khi một link biến mất hoặc path thay đổi, đối chiếu annotation, cấu hình Spring Data REST và response thực tế. Đừng sửa test bằng cách đổi rel/path theo phỏng đoán nếu chưa xác định thay đổi đó có phải hợp đồng mong muốn hay không.

## 10. Các lỗi thường gặp khi kiểm thử hypermedia

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| API root không có rel mong đợi | Repository không được export, rel tùy chỉnh hoặc base path sai | Kiểm tra repository annotation và root response |
| Rel tồn tại nhưng href khác path dự kiến | Path được tùy chỉnh hoặc ứng dụng chạy dưới base path/proxy | Follow href và kiểm tra endpoint thực tế |
| Collection không có key `_embedded` như test mong đợi | Collection rel khác, dữ liệu rỗng hoặc representation khác | Kiểm tra rel và fixture, yêu cầu HAL rõ ràng |
| Response thiếu `_links` | Request không yêu cầu HAL hoặc endpoint không trả hypermedia như dự kiến | Gửi `Accept: application/hal+json` và kiểm tra Content-Type |
| Link association không xuất hiện | Association không được export hoặc mapping không công bố link | Kiểm tra mapping và `@RestResource` |
| Search link không có query rel | Query method không được export hoặc tên rel/path tùy chỉnh | Kiểm tra repository method và search resource |
| Test fail khi đổi port | Test khóa vào absolute URL | Đọc href từ response hoặc so sánh URI path |
| Page metadata không xuất hiện | Endpoint không dùng paginated collection | Kiểm tra cấu hình repository và kiểu kết quả |

## 11. Quy trình kiểm thử đề xuất

Một integration test cho Spring Data REST nên đi theo hành trình mà client thực tế sử dụng:

1. Gọi API root với `Accept: application/hal+json`; xác nhận status, media type và các rel quan trọng.
2. Theo rel repository để lấy collection URI; xác nhận href và collection response.
3. Kiểm tra `_embedded`, `_links.self` và page metadata nếu phân trang được bật.
4. Theo self link của một item; kiểm tra dữ liệu và các association rel.
5. Theo association link để xác nhận quan hệ dẫn đến đúng resource.
6. Theo search link nếu API công bố query methods; xác nhận query rel và kết quả.
7. Chạy test với base path, rel và path tùy chỉnh để bảo đảm client không phụ thuộc tên mặc định.
8. Kiểm tra các repository/association không được export để bảo đảm chúng không vô tình xuất hiện trong API root.

Các test nên dùng fixture ổn định, xác nhận cả HTTP status, Content-Type, JSON structure và khả năng follow link. Với các link có URI động, kiểm tra quan hệ và đích theo cấu hình thay vì hard-code toàn bộ URL.

## 12. Nguyên tắc cần nhớ

API root là điểm bắt đầu để khám phá tài nguyên. Rel cho biết ý nghĩa của liên kết; href cung cấp URI cần follow; path có thể được tùy chỉnh độc lập với rel. HAL thể hiện các liên kết trong `_links`, tài nguyên nhúng trong `_embedded` và metadata phân trang trong `page` khi phù hợp.

Khi test bắt đầu từ API root, follow các link server công bố và xác nhận đúng media type cùng cấu trúc HAL, bài kiểm thử sẽ bảo vệ hợp đồng hypermedia mà client thực sự sử dụng.