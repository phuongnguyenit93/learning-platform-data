# Paged repository response

Spring Data REST có thể tự xuất bản repository thành REST endpoint. Khi repository hỗ trợ phân trang và phương thức truy vấn trả về `Page<T>`, Spring Data REST tạo response dạng collection có các item, page metadata và hypermedia link để client điều hướng giữa các trang. Controller không cần tự viết vòng lặp lấy dữ liệu, tính tổng số trang hoặc ghép URL `next`.

Ví dụ, client gọi `GET /orders?page=0&size=20&sort=createdAt,desc`. Server trả một HAL document chứa `_embedded.orders`, `_links` và object `page`. Client đọc các link `next`, `prev`, `first`, `last` khi có, rồi theo link tương ứng để tiếp tục duyệt dữ liệu. Đây là cách Spring Data REST kết hợp Spring Data pagination với Spring HATEOAS.

## Repository được xuất bản thành collection endpoint

Spring Data REST phát hiện repository trong ứng dụng và có thể tự tạo endpoint cho collection cùng từng item. Repository thường kế thừa `JpaRepository` hoặc một interface Spring Data phù hợp:

```java
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(
        path = "orders",
        collectionResourceRel = "orders")
public interface OrderRepository extends JpaRepository<Order, UUID> {
}
```

Với cấu hình mặc định và repository được export, collection endpoint có thể truy cập tại `/orders`; item endpoint có dạng `/orders/{id}`. `path` xác định segment URL công khai, còn `collectionResourceRel` xác định relation dùng cho collection trong HAL, thường là tên khóa trong `_embedded`.

`Order` là entity của ứng dụng, ở đây giả định đã có các trường như `id`, `status`, `createdAt` và mapping persistence phù hợp. Không nên để tên bảng hoặc tên class persistence tự quyết định hợp đồng URL; dùng annotation để đặt path và relation có ý nghĩa ổn định.

Repository cần có khả năng phân trang. `JpaRepository` cung cấp các phương thức paging như `findAll(Pageable)` thông qua các interface Spring Data mà nó mở rộng. Nếu chỉ trả `List<T>` từ một phương thức tùy chỉnh, response không có đầy đủ tổng số phần tử và tổng số trang như `Page<T>`.

## Gửi yêu cầu phân trang

Spring Data REST nhận các query parameter phân trang và sắp xếp. Theo quy ước mặc định phổ biến, client dùng:

| Parameter | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `page` | Chỉ số trang, bắt đầu từ 0. | `page=0` là trang đầu. |
| `size` | Số phần tử tối đa trong một trang. | `size=20` |
| `sort` | Tên thuộc tính và hướng sắp xếp. | `sort=createdAt,desc` |

Request ví dụ:

```http
GET /orders?page=0&size=2&sort=createdAt,desc HTTP/1.1
Host: shop.example
Accept: application/hal+json
```

Trong đó, `page=0` yêu cầu trang đầu tiên, `size=2` yêu cầu tối đa hai order, và `sort=createdAt,desc` sắp xếp theo thời điểm tạo giảm dần. Nếu bỏ qua `page`, `size` hoặc `sort`, resolver sử dụng mặc định đang cấu hình trong ứng dụng.

Có thể gửi nhiều tiêu chí sort bằng cách lặp parameter:

```http
GET /orders?page=0&size=20&sort=status,asc&sort=createdAt,desc
```

Client không nên giả định mọi repository đều cho phép sort theo mọi property. Tên property phải hợp lệ với domain/query model và ứng dụng nên giới hạn các trường sort được hỗ trợ nếu cần bảo vệ hiệu năng hoặc giữ ổn định hợp đồng.

## Cấu trúc paged HAL response

Spring Data REST thường trả collection dưới HAL JSON. Một response trang đầu có thể có hình dạng như sau:

```json
{
  "_embedded": {
    "orders": [
      {
        "id": "o-42",
        "status": "PAID",
        "createdAt": "2026-11-20T10:15:30Z",
        "_links": {
          "self": {
            "href": "https://shop.example/orders/o-42"
          },
          "order": {
            "href": "https://shop.example/orders/o-42"
          }
        }
      },
      {
        "id": "o-43",
        "status": "PENDING",
        "createdAt": "2026-11-19T08:00:00Z",
        "_links": {
          "self": {
            "href": "https://shop.example/orders/o-43"
          },
          "order": {
            "href": "https://shop.example/orders/o-43"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://shop.example/orders?page=0&size=2&sort=createdAt,desc"
    },
    "first": {
      "href": "https://shop.example/orders?page=0&size=2&sort=createdAt,desc"
    },
    "next": {
      "href": "https://shop.example/orders?page=1&size=2&sort=createdAt,desc"
    },
    "last": {
      "href": "https://shop.example/orders?page=4&size=2&sort=createdAt,desc"
    },
    "profile": {
      "href": "https://shop.example/profile/orders"
    }
  },
  "page": {
    "size": 2,
    "totalElements": 10,
    "totalPages": 5,
    "number": 0
  }
}
```

Đây là ví dụ minh họa cấu trúc; link `profile`, item relation và các relation điều hướng cụ thể phụ thuộc cấu hình, metadata repository và phiên bản Spring Data REST.

### Embedded collection

`_embedded.orders` chứa các order của trang hiện tại. Tên `orders` đến từ collection relation mà repository công bố. Mỗi item có thể có self link để client mở representation chi tiết. Client nên theo link item thay vì tự ghép URL từ ID.

### Page metadata

Object `page` cung cấp thông tin tổng hợp:

| Field | Ý nghĩa |
| --- | --- |
| `size` | Kích thước trang được áp dụng. |
| `totalElements` | Tổng số phần tử phù hợp với truy vấn. |
| `totalPages` | Tổng số trang. |
| `number` | Chỉ số trang hiện tại, thường bắt đầu từ 0. |

Metadata giúp client hiển thị số trang, số kết quả và trạng thái điều hướng. `totalElements` và `totalPages` thường cần thông tin đếm từ repository/database; với truy vấn lớn, count query có thể tốn chi phí đáng kể.

### Navigation links

`_links` công bố các đường đi mà client có thể theo:

| Relation | Vai trò |
| --- | --- |
| `self` | Trang hiện tại. |
| `first` | Trang đầu tiên. |
| `prev` | Trang ngay trước nếu tồn tại. |
| `next` | Trang ngay sau nếu tồn tại. |
| `last` | Trang cuối cùng. |
| `search` | Điểm khám phá các finder/search resource nếu repository có khai báo. |
| `profile` | Tài liệu profile mô tả cấu trúc resource khi được công bố. |

Không phải mọi relation đều xuất hiện trong mọi response. Ví dụ, trang đầu không có `prev`; trang cuối không có `next`. Nếu chỉ có một trang, các link điều hướng biên có thể trỏ về cùng trang hoặc được lược bỏ theo representation mà framework tạo.

## Theo link thay vì tự tính URL trang tiếp theo

Client có thể dùng page metadata để hiển thị trạng thái, nhưng nên theo `next` và `prev` để điều hướng. Cách đó giữ client tách khỏi chi tiết query parameter và route của server.

Ví dụ response trang đầu có:

```json
{
  "_links": {
    "next": {
      "href": "https://shop.example/orders?page=1&size=2&sort=createdAt,desc"
    }
  }
}
```

Client đọc `href` và gửi request mới đến URI đó. Nếu server thay đổi base path, đổi tên query parameter hoặc thêm token điều hướng, client vẫn có thể theo link do server công bố. Tránh tạo URL bằng phép cộng `page + 1` rồi tự nối `size` và `sort`.

Khi theo `next`, các filter và sort đang áp dụng cần được giữ trong href. Client không nên bỏ các tham số này khi điều hướng, vì kết quả của trang tiếp theo phải thuộc cùng một truy vấn logic.

## Finder method cũng có thể trả Page

Ngoài collection root, Spring Data REST có thể xuất bản query method trong repository dưới search resource. Một finder trả `Page<T>` sẽ nhận `Pageable` và tạo paged response tương tự:

```java
import java.util.UUID;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

@RepositoryRestResource(
        path = "orders",
        collectionResourceRel = "orders")
public interface OrderRepository extends JpaRepository<Order, UUID> {

    @RestResource(path = "by-status", rel = "byStatus")
    Page<Order> findByStatus(
            @Param("status") OrderStatus status,
            Pageable pageable);
}
```

Spring Data REST có thể công bố finder tại search resource, ví dụ:

```http
GET /orders/search/by-status?status=PAID&page=0&size=20
Accept: application/hal+json
```

Vì method trả `Page<Order>`, response chứa các item phù hợp với trạng thái `PAID`, page metadata và các link điều hướng. `@RestResource(path = "by-status", rel = "byStatus")` đặt path và relation công khai cho finder. `@Param("status")` xác định tên query parameter.

Link search của repository giúp client khám phá finder mà không phải biết tên method Java. Client nên lấy link từ collection/search representation khi nó được công bố, sau đó sử dụng query parameter được mô tả trong hợp đồng.

## Cấu hình phân trang trong Spring Data REST

Có thể cấu hình page size mặc định, giới hạn tối đa và tên query parameter bằng `RepositoryRestConfiguration`. Cách thường dùng là triển khai `RepositoryRestConfigurer`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
class DataRestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.setDefaultPageSize(25);
        config.setMaxPageSize(100);
        config.setPageParamName("page");
        config.setLimitParamName("size");
        config.setSortParamName("sort");
    }
}
```

Trong ví dụ, server dùng 25 phần tử làm kích thước trang mặc định và giới hạn tối đa 100. Nếu client yêu cầu `size=500`, resolver áp dụng giới hạn theo cấu hình thay vì cho phép tải tùy ý. Hành vi cụ thể khi vượt giới hạn cần được kiểm thử trên phiên bản Spring Data REST đang dùng.

Tên `page`, `size`, `sort` có thể được đổi để phù hợp hợp đồng API, nhưng nên giữ quy ước phổ biến nếu không có lý do tương thích rõ ràng. Khi đổi tên, client phải theo link server tạo và tài liệu API phải cập nhật cùng lúc.

`@PageableDefault` thường được dùng cho tham số `Pageable` trong controller Spring MVC do ứng dụng tự viết. Với repository endpoint do Spring Data REST tự xuất bản, cấu hình phân trang thuộc `RepositoryRestConfiguration`; không nên kỳ vọng annotation trên một controller tùy chỉnh sẽ thay đổi resolver của repository endpoint.

## Khác biệt với PagedResourcesAssembler trong Spring MVC

Hai cách đều có thể tạo paged hypermedia response nhưng được dùng ở hai kiểu endpoint khác nhau:

| Spring Data REST repository endpoint | Spring MVC custom controller |
| --- | --- |
| Framework tự xuất bản repository. | Developer tự định nghĩa controller và route. |
| Repository method nhận `Pageable` và trả `Page<T>`. | Controller gọi service/repository, sau đó chuyển `Page<T>` bằng `PagedResourcesAssembler`. |
| Cấu hình paging qua `RepositoryRestConfiguration`. | Cấu hình `PageableHandlerMethodArgumentResolver` và annotation/controller. |
| HAL collection, metadata và link được Spring Data REST tạo tự động. | Developer kiểm soát `PagedModel`, item assembler và link bổ sung. |

Nếu cần endpoint CRUD/search trực tiếp từ repository, Spring Data REST giảm lượng code controller. Nếu cần quy trình nghiệp vụ phức tạp, response tổng hợp nhiều nguồn hoặc hợp đồng tùy biến sâu, custom controller cùng Spring HATEOAS có thể phù hợp hơn.

Không cần tự inject `PagedResourcesAssembler` vào repository interface. Repository chỉ khai báo kiểu truy vấn; Spring Data REST xử lý việc chuyển kết quả `Page` thành response hypermedia.

## Collection rỗng và trang ngoài phạm vi

Nếu truy vấn không có kết quả, response vẫn có thể mang page metadata và self link để mô tả truy vấn đã thực hiện. `_embedded` có thể không xuất hiện hoặc chứa collection rỗng tùy representation và phiên bản; client nên xử lý cả hai trường hợp thay vì giả định luôn có phần tử đầu tiên.

Nếu client yêu cầu `page` vượt quá tổng số trang, framework có thể trả trang rỗng với metadata tương ứng. Đây không nhất thiết là lỗi cú pháp request. Hãy quyết định hợp đồng có chấp nhận trang rỗng ngoài phạm vi hay chuẩn hóa hành vi khác, rồi kiểm thử nhất quán.

Kích thước trang bằng 0 hoặc âm không phải request hợp lệ theo quy tắc phân trang thông thường. Server nên áp dụng resolver/configuration để chuẩn hóa hoặc từ chối giá trị không hợp lệ và công bố hành vi.

## Hiệu năng và tính ổn định của pagination

Phân trang giúp tránh trả toàn bộ dữ liệu trong một response, nhưng `Page<T>` có thể cần count query để tính `totalElements` và `totalPages`. Với bảng lớn hoặc filter phức tạp, count query có thể trở thành chi phí đáng kể.

Offset pagination cũng có thể tạo kết quả trùng hoặc bỏ sót khi dữ liệu thay đổi giữa hai request. Ví dụ, client đọc trang 0 rồi một order mới được chèn vào đầu danh sách trước khi client đọc trang 1; item ở ranh giới trang có thể bị lặp.

Các thực hành hữu ích:

- Giới hạn page size tối đa và chọn default hợp lý.
- Dùng sort ổn định; thêm khóa duy nhất làm tie-breaker nếu nhiều record có cùng giá trị sort.
- Tạo index phù hợp với filter và sort thường dùng.
- Kiểm tra execution plan của query và count query với dữ liệu gần quy mô production.
- Cân nhắc Slice hoặc keyset/cursor pagination khi không cần tổng số trang hoặc dữ liệu quá lớn.

Spring Data REST paged repository response dựa trên `Page` để công bố tổng số phần tử/trang. Nếu nghiệp vụ chuyển sang cursor pagination, không nên giả lập `totalPages` không có thật; cần thiết kế response và link điều hướng phù hợp với cursor.

## Projection và payload của từng item

Collection response có thể lớn dù đã phân trang nếu mỗi item chứa quá nhiều trường hoặc quan hệ. Spring Data REST hỗ trợ projection/excerpt projection để điều chỉnh dữ liệu được hiển thị trong collection và item representation. Chọn projection theo nhu cầu của client để giảm payload, nhưng giữ link điều hướng cần thiết.

Projection thay đổi representation data; nó không thay đổi ý nghĩa của page metadata. Client vẫn có thể dùng `page` và `_links` để duyệt collection. Nếu thay đổi projection làm thay đổi field mà client phụ thuộc, cần xem đó là thay đổi hợp đồng và kiểm thử tương thích.

## Kiểm thử paged repository response bằng MockMvc

Kiểm thử nên xác nhận media type, embedded relation, page metadata và link điều hướng. Ví dụ dưới đây giả định fixture có năm order và repository được export tại `/orders`:

```java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderRepositoryPagingTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsPageMetadataAndNextLink() throws Exception {
        mockMvc.perform(get("/orders")
                        .param("page", "0")
                        .param("size", "2")
                        .param("sort", "createdAt,desc")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$.page.size").value(2))
                .andExpect(jsonPath("$.page.totalElements").value(5))
                .andExpect(jsonPath("$.page.totalPages").value(3))
                .andExpect(jsonPath("$.page.number").value(0))
                .andExpect(jsonPath("$._embedded.orders").isArray())
                .andExpect(jsonPath("$._links.self.href").exists())
                .andExpect(jsonPath("$._links.next.href")
                        .value(containsString("page=1")));
    }

    @Test
    void lastPageHasNoNextLink() throws Exception {
        mockMvc.perform(get("/orders")
                        .param("page", "2")
                        .param("size", "2")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.page.number").value(2))
                .andExpect(jsonPath("$._links.prev.href").exists())
                .andExpect(jsonPath("$._links.next").doesNotExist());
    }
}
```

Fixture cần có đúng năm order và sort order xác định để `totalPages=3` với `size=2`. Nếu collection relation được cấu hình khác `orders`, cập nhật JSONPath theo relation thực tế. Test cho trang cuối giả định chỉ có ba trang.

Nên bổ sung kiểm thử cho finder trả `Page`, filter được giữ trong link `next`, page size vượt giới hạn, collection rỗng và sort parameter không hợp lệ. Các test này bảo vệ cả dữ liệu lẫn hợp đồng điều hướng mà client sử dụng.

## Bảo mật và giới hạn truy vấn

Repository được export không có nghĩa mọi client đều được phép đọc mọi trang. Cấu hình Spring Security và repository exposure phải giới hạn endpoint theo vai trò, tenant và chính sách dữ liệu. Không dựa vào việc client không biết URI để bảo vệ repository.

Query parameter cũng là đầu vào không đáng tin cậy. Cần:

- Giới hạn `size` tối đa.
- Chỉ hỗ trợ sort field phù hợp với API và hiệu năng database.
- Áp dụng tenant/security filter cho mọi trang và finder.
- Tránh trả entity có dữ liệu nhạy cảm qua collection representation.
- Theo dõi truy vấn có offset lớn và count query tốn kém.

Các link `next` và `last` chỉ là hướng dẫn điều hướng. Server vẫn phải xác thực và phân quyền lại trên từng request được theo.

## Lỗi thường gặp

| Vấn đề | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Repository method trả `List<T>` khi cần page metadata | Client không biết tổng số trang và số phần tử. | Dùng phương thức trả `Page<T>` và nhận `Pageable`. |
| Tự ghép URL trang tiếp theo | Dễ mất sort/filter hoặc sai khi đổi tên parameter. | Theo `_links.next` do server tạo. |
| Nhầm `page` bắt đầu từ 1 | Client yêu cầu sai trang đầu. | Mặc định Spring Data dùng chỉ số từ 0; kiểm tra cấu hình cụ thể. |
| Không giới hạn `size` | Request có thể gây tải lớn cho database và bộ nhớ. | Cấu hình default và max page size. |
| Finder trả `Page` nhưng không tài liệu hóa query parameter | Client không biết filter và paging được kết hợp thế nào. | Đặt path/relation rõ và mô tả `@Param`, `Pageable`. |
| Cho rằng `_embedded` luôn có phần tử | Client lỗi khi collection rỗng. | Xử lý cả `_embedded` vắng mặt và collection rỗng. |
| Sort không ổn định | Có thể lặp hoặc bỏ sót item giữa các trang khi dữ liệu thay đổi. | Dùng thứ tự có tie-breaker duy nhất. |
| Dùng `@PageableDefault` để cấu hình repository endpoint | Cấu hình không áp dụng vào resolver Spring Data REST. | Dùng `RepositoryRestConfiguration`. |

## Nguyên tắc thiết kế

- Dùng repository trả `Page<T>` để Spring Data REST tạo paged collection response.
- Đặt path và collection relation rõ bằng `@RepositoryRestResource`.
- Dùng `page`, `size`, `sort` theo hợp đồng được công bố.
- Đọc `_embedded`, `page` metadata và `_links` thay vì tự dựng URL.
- Dùng finder method trả `Page<T>` khi cần collection search có phân trang.
- Cấu hình default/max page size và tên query parameter qua `RepositoryRestConfiguration`.
- Phân biệt repository endpoint tự xuất bản với custom MVC controller dùng `PagedResourcesAssembler`.
- Kiểm tra count query, sort ổn định, projection và giới hạn truy vấn.
- Kiểm thử page metadata, embedded relation, navigation links và trường hợp rỗng.
- Bảo vệ repository và từng request bằng authorization/filter ở server.

Paged repository response là cách Spring Data REST công bố một collection lớn theo từng trang với hypermedia. Repository cung cấp `Page<T>`; Spring Data REST tạo embedded items, page metadata và các link điều hướng trong HAL. Client có thể hiển thị trạng thái phân trang và theo link `next`/`prev` mà không phụ thuộc vào cách server xây query string. Khi page size, sort, filter và quyền truy cập được cấu hình rõ, repository endpoint vừa giảm mã tích hợp vừa tạo hợp đồng REST có thể khám phá.
