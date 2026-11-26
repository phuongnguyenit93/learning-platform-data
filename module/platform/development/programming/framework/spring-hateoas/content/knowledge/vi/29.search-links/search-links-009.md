# Search suggestion với Spring HATEOAS

## Mục tiêu bài học

Sau bài học này, bạn có thể:

- Phân biệt link tìm kiếm với link lấy gợi ý tìm kiếm.
- Công bố endpoint search và suggestions dưới dạng URI template trong representation.
- Dùng `methodOn` và `linkTo` để Spring HATEOAS tạo link từ mapping của controller.
- Trả về gợi ý có link dẫn đến kết quả tìm kiếm tương ứng.
- Kiểm thử hợp đồng hypermedia và thiết kế endpoint gợi ý an toàn, dễ mở rộng.

## 1. Search suggestion trong API hypermedia

Một giao diện tìm kiếm thường có hai bước. Người dùng nhập một phần từ khóa, hệ thống đưa ra một số gợi ý phù hợp; sau đó người dùng chọn một gợi ý hoặc gửi từ khóa để xem kết quả đầy đủ.

API có thể cung cấp hai khả năng riêng:

- **Search:** thực hiện truy vấn và trả về tập kết quả phù hợp với từ khóa.
- **Suggestions:** nhận một phần từ khóa và trả về các cụm từ hoặc mục phù hợp để người dùng lựa chọn.

Trong Spring HATEOAS, server có thể công bố cả hai khả năng bằng các link trong representation. Client khám phá link, đọc URI template và điền tham số cần thiết. Client không cần tự đoán rằng endpoint tìm kiếm luôn nằm ở `/api/products/search` hoặc endpoint gợi ý luôn nằm ở `/api/products/suggestions`.

Một luồng điển hình:

~~~mermaid
flowchart TD
    A[Client đọc representation danh mục] --> B[Khám phá link suggestions]
    B --> C[Mở rộng URI template với q và limit]
    C --> D[Gửi yêu cầu lấy gợi ý]
    D --> E[Nhận danh sách gợi ý]
    E --> F[Chọn một gợi ý]
    F --> G[Theo link search có sẵn từ gợi ý]
    G --> H[Nhận kết quả tìm kiếm]
~~~

Hai link có mục đích khác nhau. Link `search` dẫn đến thao tác tìm kiếm đầy đủ. Link gợi ý dẫn đến tài nguyên cung cấp các lựa chọn dựa trên một phần từ khóa. Khi một gợi ý được chọn, representation của gợi ý có thể cung cấp link `search` đã chứa từ khóa tương ứng.

## 2. URI template cho tham số tìm kiếm

Một link tìm kiếm thường cần tham số như `q`, `category`, `page` hoặc `size`. Spring HATEOAS có thể tạo URI template từ mapping của controller. Client nhận được link có `templated: true`, sau đó mở rộng các biến theo nhu cầu.

Ví dụ một link tìm kiếm có thể được tuần tự hóa thành:

~~~json
{
  "_links": {
    "search": {
      "href": "https://api.example.test/api/products/search{?q}",
      "templated": true
    }
  }
}
~~~

Phần `{?q}` biểu thị biến query parameter có tên `q`. Khi client cung cấp từ khóa `laptop`, URI được mở rộng thành dạng `/api/products/search?q=laptop`. Thư viện xử lý URI template cần mã hóa giá trị đúng quy tắc; client không nên nối chuỗi thủ công để tạo query string.

Khi controller khai báo rõ tên tham số bằng `@RequestParam("q")`, Spring HATEOAS có thông tin cần thiết để xây dựng template ổn định. Việc khai báo tên tường minh cũng tránh phụ thuộc vào tên tham số được giữ lại trong quá trình biên dịch.

## 3. Khai báo search link và suggestion link

Giả sử API quản lý danh mục sản phẩm có hai endpoint:

- `GET /api/products/search?q=...` trả về sản phẩm phù hợp.
- `GET /api/products/suggestions?q=...&limit=...` trả về một số gợi ý cho phần từ khóa đã nhập.

Controller có thể công bố hai link này trong representation danh mục:

~~~java
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.stream.Collectors;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/api/products")
class ProductSearchController {

    private static final LinkRelation SUGGESTIONS =
        LinkRelation.of("https://api.example.com/rels/suggestions");

    private final ProductSearchService searchService;
    private final ProductModelAssembler productAssembler;

    ProductSearchController(
            ProductSearchService searchService,
            ProductModelAssembler productAssembler) {
        this.searchService = searchService;
        this.productAssembler = productAssembler;
    }

    @GetMapping
    CollectionModel<EntityModel<Product>> catalog() {
        List<EntityModel<Product>> featured = searchService.featured()
            .stream()
            .map(productAssembler::toModel)
            .collect(Collectors.toList());

        Link search = linkTo(
            methodOn(ProductSearchController.class).search(null)
        ).withRel(IanaLinkRelations.SEARCH);

        Link suggestions = linkTo(
            methodOn(ProductSearchController.class).suggestions(null, null)
        ).withRel(SUGGESTIONS);

        return CollectionModel.of(featured, search, suggestions);
    }

    @GetMapping("/search")
    CollectionModel<EntityModel<Product>> search(
            @RequestParam("q") String query) {

        return CollectionModel.of(
            searchService.search(query)
                .stream()
                .map(productAssembler::toModel)
                .collect(Collectors.toList())
        );
    }

    @GetMapping("/suggestions")
    CollectionModel<EntityModel<SearchSuggestion>> suggestions(
            @RequestParam("q") String partialQuery,
            @RequestParam(name = "limit", required = false) Integer requestedLimit) {

        int limit = requestedLimit == null
            ? 5
            : Math.min(Math.max(requestedLimit, 1), 10);

        List<EntityModel<SearchSuggestion>> models =
            searchService.suggest(partialQuery, limit)
                .stream()
                .map(suggestion -> {
                    Link search = linkTo(
                        methodOn(ProductSearchController.class)
                            .search(suggestion.query())
                    ).withRel(IanaLinkRelations.SEARCH);

                    return EntityModel.of(suggestion, search);
                })
                .collect(Collectors.toList());

        return CollectionModel.of(models);
    }
}
~~~

Đây là ví dụ minh họa cách tổ chức controller; `Product`, `SearchSuggestion`, `ProductSearchService` và `ProductModelAssembler` là các kiểu của ứng dụng.

Điểm quan trọng nằm ở hai lời gọi:

~~~java
linkTo(methodOn(ProductSearchController.class).search(null))
    .withRel(IanaLinkRelations.SEARCH);

linkTo(methodOn(ProductSearchController.class).suggestions(null, null))
    .withRel(SUGGESTIONS);
~~~

`methodOn` tạo proxy để ghi nhận phương thức và đối số. Spring HATEOAS dựa trên mapping cùng các annotation của controller để tạo URI template. Những giá trị `null` trong lời gọi này được dùng để biểu diễn các tham số chưa được điền vào template; phương thức xử lý request không được gọi như một request thực.

Với các khai báo `@RequestParam` trong ví dụ, link được tạo có dạng khái quát:

~~~json
{
  "_links": {
    "search": {
      "href": "https://api.example.test/api/products/search{?q}",
      "templated": true
    },
    "https://api.example.com/rels/suggestions": {
      "href": "https://api.example.test/api/products/suggestions{?q,limit}",
      "templated": true
    }
  }
}
~~~

Tên biến trong URI template đến từ mapping và khai báo tham số của controller. Nếu đổi tên tham số công khai, hợp đồng hypermedia cũng có thể thay đổi; vì vậy nên đặt tên query parameter rõ ràng và xem việc đổi tên là một thay đổi API cần đánh giá tương thích.

## 4. Quan hệ link cho chức năng search và suggestions

`search` là một link relation đã được đăng ký trong bộ quan hệ IANA. Spring HATEOAS cung cấp hằng `IanaLinkRelations.SEARCH`, giúp tránh gõ tên relation tùy ý.

Quan hệ dành riêng cho gợi ý là một phần mở rộng của API. Trong ví dụ, relation được khai báo bằng URI:

~~~java
private static final LinkRelation SUGGESTIONS =
    LinkRelation.of("https://api.example.com/rels/suggestions");
~~~

Dùng URI làm extension relation giúp client nhận diện ý nghĩa của relation theo một định danh ổn định. Nếu API cấu hình CURIE cho HAL, relation này có thể được biểu diễn bằng tên rút gọn như `ex:suggestions`; client tra cứu CURIE để biết URI đầy đủ. Với API công khai, tài liệu của relation nên mô tả phương thức HTTP, tham số, kiểu kết quả và ý nghĩa của gợi ý.

Không nên dùng một relation tùy ý mà không định nghĩa ý nghĩa của nó. Nếu client không biết link đó cung cấp gợi ý, client khó có thể sử dụng nó một cách tổng quát.

## 5. Gắn link tìm kiếm vào từng gợi ý

Một gợi ý nên mang dữ liệu đủ để client hiển thị lựa chọn, ví dụ nhãn và từ khóa dùng để tìm kiếm:

~~~java
public record SearchSuggestion(
    String label,
    String query
) {}
~~~

Ví dụ một kết quả gợi ý:

~~~json
{
  "label": "Laptop gaming",
  "query": "laptop gaming",
  "_links": {
    "search": {
      "href": "https://api.example.test/api/products/search?q=laptop%20gaming"
    }
  }
}
~~~

Trong controller ở phần trước, link được tạo bằng lời gọi:

~~~java
Link search = linkTo(
    methodOn(ProductSearchController.class).search(suggestion.query())
).withRel(IanaLinkRelations.SEARCH);
~~~

Ở đây `suggestion.query()` là giá trị cụ thể, nên link dẫn đến một truy vấn đã được điền sẵn. Client có thể theo link đó ngay sau khi người dùng chọn gợi ý. Client không cần tự lấy `query`, tự ghép URL hoặc phải biết cấu trúc route của server.

Có thể mở rộng representation của gợi ý bằng link đến tài nguyên tương ứng nếu gợi ý đại diện cho một sản phẩm, thương hiệu hoặc danh mục đã tồn tại. Khi đó, cần phân biệt rõ link `search` dùng để thực hiện truy vấn với link `item` hoặc relation riêng dùng để mở tài nguyên được gợi ý.

## 6. Xử lý tham số và kết quả gợi ý

Endpoint suggestions cần có quy tắc rõ ràng cho đầu vào và số lượng kết quả. Một số quyết định thường gặp:

- Từ khóa rỗng hoặc chỉ có khoảng trắng: trả về danh sách rỗng hoặc lỗi validation theo hợp đồng đã chọn.
- Từ khóa quá ngắn: có thể trả về danh sách rỗng để tránh truy vấn quá rộng.
- `limit` không được gửi: dùng giá trị mặc định hợp lý.
- `limit` nhỏ hơn 1 hoặc vượt giới hạn: chuẩn hóa hoặc từ chối theo chính sách API.
- Không có kết quả: trả về collection rỗng, giữ cấu trúc representation ổn định.

Trong ví dụ, `limit` được giới hạn trong khoảng 1 đến 10. Việc giới hạn này bảo vệ tài nguyên server và giúp client nhận được danh sách gợi ý ngắn, dễ hiển thị. Ngưỡng tối thiểu của từ khóa và thuật toán xếp hạng phụ thuộc nghiệp vụ; chúng nên được xử lý ở service tìm kiếm thay vì đặt rải rác trong assembler.

Gợi ý có thể đến từ tên sản phẩm, danh mục, thương hiệu hoặc lịch sử tìm kiếm. Hãy giữ mô hình response nhất quán và chỉ đưa ra những trường mà client cần để hiển thị và theo link tiếp theo.

## 7. Kiểm thử hợp đồng hypermedia

Kiểm thử chức năng tìm kiếm chỉ xác nhận rằng endpoint trả về kết quả phù hợp. Với search suggestion, cần kiểm tra cả các link được công bố và khả năng điều hướng từ link đó.

Các kiểm tra nên có:

1. Representation danh mục chứa relation `search`.
2. Link `search` có `templated: true` và template chứa biến `q`.
3. Representation danh mục có relation extension dành cho suggestions.
4. Link suggestions chứa các biến cần thiết, chẳng hạn `q` và `limit`.
5. Gọi endpoint suggestions với một phần từ khóa trả về các gợi ý phù hợp.
6. Mỗi gợi ý có link `search` với từ khóa tương ứng đã được điền và mã hóa đúng.
7. Khi không có gợi ý, API vẫn trả về representation collection hợp lệ.
8. Giới hạn `limit`, quyền truy cập và quy tắc validation được áp dụng đúng.

Ví dụ kiểm tra link tìm kiếm bằng MockMvc:

~~~java
mockMvc.perform(get("/api/products"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.search.templated").value(true))
    .andExpect(jsonPath("$._links.search.href")
        .value(containsString("{?q}")));
~~~

Với relation extension, có thể phân tích JSON response rồi xác nhận key relation đã khai báo có tồn tại và link có `templated: true`. Khi kiểm thử, tránh phụ thuộc vào host hoặc port tuyệt đối của môi trường chạy; tập trung vào relation, đường dẫn và các biến template thuộc hợp đồng.

Cũng nên kiểm tra link của một gợi ý với từ khóa có dấu cách, ký tự Unicode hoặc ký tự đặc biệt. URI phải được mã hóa đúng; kiểm thử này giúp phát hiện lỗi khi ứng dụng tự nối chuỗi hoặc xử lý query parameter không đúng cách.

## 8. Bảo mật, quyền truy cập và cache

Gợi ý tìm kiếm có thể làm lộ dữ liệu nếu service trả về những mục mà người dùng hiện tại không được phép xem. Vì vậy, endpoint suggestions cần áp dụng cùng chính sách phân quyền và phạm vi dữ liệu như endpoint search. Không nên cho rằng dữ liệu chỉ là gợi ý nên có thể bỏ qua kiểm tra quyền.

Một số điểm cần lưu ý:

- Không đưa thông tin bí mật hoặc dữ liệu cá nhân nhạy cảm vào query parameter. URL có thể xuất hiện trong access log, lịch sử trình duyệt, proxy và hệ thống giám sát.
- Giới hạn độ dài từ khóa, số lượng kết quả và tần suất gọi để giảm nguy cơ lạm dụng.
- Nếu gợi ý phụ thuộc vào người dùng hoặc lịch sử tìm kiếm riêng, cấu hình cache phải ngăn response riêng tư bị dùng chung cho người khác.
- Nếu nội dung gợi ý công khai và ổn định, có thể cân nhắc cache HTTP, ETag hoặc thời gian sống ngắn.
- Không để response tiết lộ sự tồn tại của tài nguyên mà người gọi không có quyền truy cập.

Link hypermedia chỉ mô tả khả năng điều hướng. Việc client nhìn thấy link không thay thế kiểm tra xác thực và phân quyền ở endpoint đích. Server vẫn phải xác minh quyền trên mỗi request.

## 9. Những lỗi thiết kế thường gặp

| Cách làm | Vấn đề | Cách xử lý |
|---|---|---|
| Client tự ghép `/search?q=...` | Client phụ thuộc vào cấu trúc URL nội bộ | Công bố relation `search` và URI template |
| Chỉ trả về text gợi ý, không có link | Client phải tự đoán bước tiếp theo | Thêm link `search` đã điền từ khóa cho từng gợi ý |
| Dùng cùng một relation cho search và suggestions | Client không phân biệt được hai khả năng | Dùng `search` cho truy vấn và extension relation được định nghĩa cho suggestions |
| Không giới hạn `limit` | Request có thể tạo ra quá nhiều kết quả | Đặt giá trị mặc định và giới hạn tối đa |
| Truy vấn suggestions không kiểm tra quyền | Có thể tiết lộ dữ liệu ngoài phạm vi người dùng | Áp dụng chính sách truy cập như endpoint search |
| Ghép query string bằng nối chuỗi | Có thể mã hóa sai ký tự và tạo URL không hợp lệ | Dùng URI template và link builder của Spring HATEOAS |

## 10. Bài tập vận dụng

Một API bán hàng có endpoint danh mục sản phẩm. Giao diện cần gợi ý tên sản phẩm khi người dùng nhập từ khóa. API hiện có endpoint tìm kiếm nhưng client đang tự ghép URL.

Hãy thiết kế hợp đồng hypermedia cho yêu cầu này:

1. Chọn relation cho chức năng tìm kiếm và relation cho chức năng gợi ý.
2. Xác định query parameter của hai endpoint và biểu diễn chúng bằng URI template.
3. Thiết kế representation của một gợi ý sao cho client có thể theo link để thực hiện tìm kiếm.
4. Đề xuất quy tắc xử lý từ khóa rỗng, từ khóa ngắn và `limit`.
5. Viết các kiểm tra xác nhận relation, template và link tìm kiếm của một gợi ý.

Khi hoàn thành, client chỉ cần khám phá representation, mở rộng template và theo các link được cung cấp để thực hiện luồng tìm kiếm. Nếu đường dẫn endpoint thay đổi, server có thể cập nhật link builder trong khi client tiếp tục dựa trên relation đã được công bố.

## Kết luận

Search suggestion là một khả năng điều hướng hữu ích trong API hypermedia. Spring HATEOAS cho phép server công bố link `search` và link suggestions dưới dạng URI template, sau đó gắn link tìm kiếm đã điền sẵn vào từng gợi ý.

Hãy đặt tên relation rõ ràng, khai báo query parameter tường minh, dùng `methodOn` và `linkTo` để tạo link từ mapping, kiểm thử hợp đồng hypermedia và áp dụng chính sách giới hạn, phân quyền, cache phù hợp. Client nhờ đó có thể khám phá chức năng tìm kiếm và tiếp tục điều hướng mà không phải phụ thuộc vào cấu trúc URL do server triển khai.

