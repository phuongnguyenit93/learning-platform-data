# UriTemplate là gì

## Mục tiêu

Một URI thông thường xác định một đích cụ thể, chẳng hạn /api/orders/42. URI template mô tả một mẫu URI có các biến chưa được thay thế, chẳng hạn /api/orders/{id} hoặc /api/orders{?status,page,size}. Client có thể đọc tên biến, cung cấp giá trị và mở rộng template thành URI cụ thể mà không phải tự đoán cấu trúc đường dẫn hay query string.

Spring HATEOAS hỗ trợ URI template theo RFC 6570. Một Link có thể chứa URI cụ thể hoặc URI template; khi template được đưa vào representation hypermedia, client có thể khám phá những tham số mà server cho phép dùng để truy vấn hoặc điều hướng.

Sau bài học, bạn có thể:

- Phân biệt URI cụ thể với URI template.
- Đọc các biểu thức biến phổ biến trong cú pháp RFC 6570.
- Tạo và mở rộng UriTemplate trong Spring HATEOAS.
- Nhận diện templated Link và các biến của link.
- Hiểu cách URI template xuất hiện trong HAL và kiểm thử hợp đồng.

## URI cụ thể và URI template

URI cụ thể đã có đủ giá trị để xác định một đích:

~~~text
/api/orders/42
/api/orders?status=PENDING&page=0
~~~

URI template chứa một hoặc nhiều biến được đặt trong dấu ngoặc nhọn:

~~~text
/api/orders/{id}
/api/orders{?status,page,size}
~~~

Trong ví dụ thứ nhất, id là biến nằm trong đường dẫn. Trong ví dụ thứ hai, status, page và size là các biến query tùy chọn được mở rộng theo biểu thức truy vấn. Template chưa phải URL cuối cùng; nó là mẫu để tạo URI khi đã có giá trị.

Ví dụ mở rộng:

| URI template | Giá trị biến | URI sau khi mở rộng |
|---|---|---|
| /api/orders/{id} | id = 42 | /api/orders/42 |
| /api/orders{?status} | status = PENDING | /api/orders?status=PENDING |
| /api/orders{?status,page,size} | status = PENDING, page = 0, size = 20 | /api/orders?status=PENDING&page=0&size=20 |

Template cho phép server công bố cấu trúc điều hướng cùng tên các biến. Client không cần tự ghép query string hoặc giả định tham số nào được hỗ trợ; client có thể đọc template và mở rộng những biến mà mình cần cung cấp.

## Cú pháp URI Template theo RFC 6570

RFC 6570 định nghĩa các biểu thức dùng để chèn biến vào những phần khác nhau của URI. Biểu thức có dạng toán tử tùy chọn theo sau là một hoặc nhiều tên biến.

| Cú pháp | Mục đích | Ví dụ |
|---|---|---|
| {id} | Chèn giá trị biến theo cách đơn giản. | /orders/{id} |
| {/id} | Chèn biến thành một path segment. | /orders{/id} |
| {?status,page} | Tạo query string từ các biến. | /orders{?status,page} |
| {&sort} | Bổ sung biến vào query string đã có. | /orders{?status}{&sort} |
| {#section} | Chèn biến vào fragment. | /docs{#section} |
| {+path} | Mở rộng biến có thể giữ lại các ký tự reserved theo quy tắc RFC. | /files/{+path} |

Trong API REST, hai dạng thường gặp nhất là biến path và biến query:

- Biến path thường xác định tài nguyên cụ thể, ví dụ id trong /orders/{id}.
- Biến query thường lọc, sắp xếp hoặc phân trang collection, ví dụ /orders{?status,page,size,sort}.

Một biểu thức có thể chứa nhiều biến. Ví dụ /orders{?status,page,size,sort} cho biết endpoint collection có thể nhận các tham số status, page, size và sort. Việc một biến xuất hiện trong template không có nghĩa mọi giá trị đều hợp lệ; server vẫn kiểm tra kiểu dữ liệu, giới hạn và quy tắc nghiệp vụ khi nhận request.

## UriTemplate trong Spring HATEOAS

Spring HATEOAS có kiểu org.springframework.hateoas.UriTemplate để biểu diễn và thao tác với URI template. Kiểu này hỗ trợ tạo template, đọc danh sách biến và mở rộng template bằng giá trị được cung cấp.

~~~java
import java.net.URI;
import java.util.List;
import java.util.Map;

import org.springframework.hateoas.UriTemplate;

UriTemplate template = UriTemplate.of("/api/orders/{id}{?projection}");

List<String> variableNames = template.getVariableNames();
// ["id", "projection"]

URI uri = template.expand(Map.of(
        "id", 42,
        "projection", "summary"));

// /api/orders/42?projection=summary
~~~

Các API quan trọng:

| API | Vai trò |
|---|---|
| UriTemplate.of(String) | Tạo template từ chuỗi URI template. |
| UriTemplate.isTemplate(String) | Kiểm tra chuỗi có chứa biểu thức template hay không. |
| getVariableNames() | Lấy danh sách tên biến được phát hiện trong template. |
| getVariables() | Lấy thông tin chi tiết các TemplateVariable. |
| expand(Map<String, ?>) | Mở rộng template bằng map tên biến và giá trị. |
| expand(Object...) | Mở rộng template bằng các giá trị theo thứ tự biến được phát hiện. |
| with(...) | Bổ sung metadata kiểu biến vào template. |

Khi dùng Map để mở rộng, tên khóa tương ứng với tên biến trong template. Cách này dễ đọc và ít phụ thuộc thứ tự hơn so với truyền các giá trị dạng varargs. Nếu dùng varargs, thứ tự giá trị phải khớp thứ tự biến trong template.

Spring HATEOAS cũng có các kiểu TemplateVariable và TemplateVariables để mô tả loại biến, chẳng hạn biến query parameter hoặc fragment. Điều này hữu ích khi tạo template từ một URI cơ sở rồi bổ sung biến theo từng bước:

~~~java
import org.springframework.hateoas.TemplateVariable;
import org.springframework.hateoas.UriTemplate;

import static org.springframework.hateoas.TemplateVariable.VariableType.REQUEST_PARAM;

UriTemplate template = UriTemplate.of("/api/orders")
        .with(new TemplateVariable("status", REQUEST_PARAM))
        .with(new TemplateVariable("page", REQUEST_PARAM));

// /api/orders{?status,page}
~~~

Spring HATEOAS có UriTemplate riêng trong package org.springframework.hateoas. Không nhầm kiểu này với org.springframework.web.util.UriTemplate của Spring Framework; chúng thuộc hai package và có mục tiêu API khác nhau. Khi làm việc với Link của Spring HATEOAS, hãy dùng UriTemplate của Spring HATEOAS.

## URI template bên trong Link

Trong Spring HATEOAS, Link có thể chứa một URI template. Khi tạo link:

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.hateoas.Link;

Link searchLink = Link.of(
        "/api/orders{?status,page,size}",
        "search");

boolean templated = searchLink.isTemplated();
// true

List<String> variables = searchLink.getVariableNames();
// ["status", "page", "size"]

Link expandedLink = searchLink.expand(Map.of(
        "status", "PENDING",
        "page", 0,
        "size", 20));

// href: /api/orders?status=PENDING&page=0&size=20
~~~

Các phương thức thường dùng trên Link:

- isTemplated() cho biết href có phải template hay không.
- getVariableNames() trả về tên các biến trong href.
- getTemplate() trả về UriTemplate tương ứng.
- expand(Map<String, ?>) tạo Link mới với các biến được mở rộng.

Link vẫn có relation như self, search hoặc orders. Relation mô tả mục đích của link; template mô tả các tham số mà client có thể cung cấp để tạo URI cụ thể. Hai khái niệm này bổ sung cho nhau.

Ví dụ, relation search nói rằng link dùng để tìm kiếm collection đơn hàng. Template cho biết tìm kiếm có thể nhận status, page và size. Client không phải suy luận rằng endpoint chắc chắn có query parameter tên q hoặc tự tạo đường dẫn tìm kiếm riêng.

## Templated Link trong HAL

Khi trả một Link có URI template trong HAL JSON, serializer đánh dấu link bằng thuộc tính templated:

~~~json
{
  "_links": {
    "self": {
      "href": "/api/orders"
    },
    "search": {
      "href": "/api/orders{?status,page,size}",
      "templated": true
    }
  }
}
~~~

Client đọc relation search, nhận biết link là templated và xem các biến trong href. Khi cần lọc đơn hàng đang chờ, client mở rộng template với status=PENDING; khi cần trang tiếp theo, client có thể cung cấp page và size theo hợp đồng.

Thuộc tính templated không phải một endpoint khác. Nó báo cho client rằng href chứa biến cần được mở rộng trước khi gửi request. Nếu link không có biến, serializer thường không cần đánh dấu templated.

Không nên loại bỏ dấu ngoặc nhọn hoặc thay template bằng một URI ví dụ có giá trị giả. Việc đó khiến client mất khả năng khám phá các tham số mà server công bố.

## Tạo template cho endpoint collection

Một API có thể trả link tìm kiếm cùng link self của collection. Ví dụ, controller trả collection model và bổ sung link template cho bộ lọc:

~~~java
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.Link;
import org.springframework.data.domain.Pageable;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler assembler;

    OrderController(OrderService orderService, OrderModelAssembler assembler) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping("/api/orders")
    CollectionModel<OrderModel> findAll(
            @RequestParam(required = false) String status,
            Pageable pageable) {
        CollectionModel<OrderModel> model = assembler.toCollectionModel(
                orderService.findAll(status, pageable));

        Link search = Link.of(
                "/api/orders{?status,page,size,sort}",
                "search");

        return model.add(search);
    }
}
~~~

Đây là ví dụ rút gọn minh họa cách công bố URI template. Trong ứng dụng thực tế, nên tạo href từ mapping hoặc cơ chế link builder phù hợp với cấu hình ứng dụng để tránh lặp lại đường dẫn. Các biến được công bố phải tương ứng với tham số endpoint thực sự hỗ trợ. Nếu endpoint không nhận sort, không đưa sort vào template.

Một template có thể biểu diễn tham số tùy chọn. Client có thể mở rộng chỉ những biến cần dùng theo cú pháp URI Template. Hãy giữ tên biến, kiểu giá trị và ngữ nghĩa của chúng nhất quán giữa các phiên bản API.

## Encoding và dữ liệu đầu vào

Giá trị biến có thể chứa dấu cách, dấu &, dấu / hoặc ký tự ngoài ASCII. Khi mở rộng template, thư viện áp dụng quy tắc encoding theo biểu thức URI Template. Không nên tự nối chuỗi query hoặc encode giá trị nhiều lần vì có thể tạo URI sai.

Ví dụ, giá trị tìm kiếm Bắc & Nam được đưa vào query parameter phải được encode để dấu & bên trong giá trị không bị hiểu nhầm là dấu phân cách giữa hai tham số. Dùng API expansion của UriTemplate hoặc Link để giảm lỗi ghép chuỗi và encoding thủ công.

Các lưu ý:

- Chọn đúng toán tử cho path segment hoặc query parameter.
- Dùng Map với đúng tên biến để tránh gán nhầm giá trị.
- Không encode trước rồi lại đưa giá trị đã encode vào expansion, trừ khi hợp đồng yêu cầu rõ cách xử lý đó.
- Không đưa thông tin bí mật vào query string chỉ vì template cho phép biến đó; URL có thể xuất hiện trong log, lịch sử trình duyệt hoặc hệ thống quan sát.
- Template không thay thế validation, authorization hoặc giới hạn truy vấn ở server.

## Kiểm thử URI template

Có thể kiểm thử trực tiếp UriTemplate để xác nhận tên biến và URI được mở rộng:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;

import org.springframework.hateoas.UriTemplate;

UriTemplate template = UriTemplate.of("/api/orders{?status,page,size}");

assertThat(template.getVariableNames())
        .containsExactly("status", "page", "size");

assertThat(template.expand(Map.of(
        "status", "PENDING",
        "page", 0,
        "size", 20)).toString())
        .isEqualTo("/api/orders?status=PENDING&page=0&size=20");
~~~

Với controller trả HAL, kiểm thử thêm href và thuộc tính templated:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api/orders")
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.search.templated").value(true))
        .andExpect(jsonPath("$._links.search.href")
                .value("/api/orders{?status,page,size,sort}"));
~~~

Ngoài việc kiểm tra chuỗi href, hãy kiểm thử endpoint khi nhận các giá trị được mở rộng: bộ lọc hợp lệ, page và size hợp lệ, giá trị không hợp lệ và ký tự đặc biệt. Điều này xác nhận template mà server công bố khớp với hành vi thật của endpoint.

## Những lỗi thường gặp

- **Nhầm URI template với URI hoàn chỉnh:** template vẫn còn biến; client cần mở rộng trước khi gửi request.
- **Coi tên biến là tên relation:** relation mô tả mục đích link, còn biến mô tả giá trị cần cung cấp.
- **Ghép query string bằng chuỗi:** dễ sai dấu phân cách và encoding. Dùng UriTemplate hoặc Link.expand.
- **Công bố biến endpoint không hỗ trợ:** template phải khớp tham số thực tế của handler.
- **Dùng sai toán tử:** biến path và query có cú pháp khác nhau. Chọn biểu thức phù hợp với vị trí của biến.
- **Dựa vào thứ tự biến khi dùng varargs:** truyền Map theo tên biến sẽ rõ ràng hơn và tránh gán nhầm.
- **Quên kiểm thử thuộc tính templated trong HAL:** href có biến cần được nhận diện là template để client xử lý đúng.
- **Cho rằng template đảm bảo request hợp lệ:** server vẫn phải kiểm tra kiểu, quyền và giới hạn dữ liệu.

## Quy trình làm việc với UriTemplate

1. Xác định URI cụ thể hay URI template phù hợp với mục đích điều hướng.
2. Chọn biến path, query hoặc fragment theo cấu trúc URI cần công bố.
3. Tạo UriTemplate hoặc Link bằng API Spring HATEOAS và đặt relation có ý nghĩa.
4. Kiểm tra tên biến bằng getVariableNames và mở rộng bằng Map khi cần URI cụ thể.
5. Trả templated Link trong representation hypermedia; kiểm tra HAL có templated=true.
6. Kiểm thử expansion, encoding và hành vi endpoint với các giá trị hợp lệ lẫn không hợp lệ.

UriTemplate giúp server công bố cách tạo URI có tham số mà không buộc client phải biết trước cấu trúc URL. Khi Spring HATEOAS kết hợp template với Link relation, client có thể khám phá mục đích của liên kết, tên biến được hỗ trợ và cách tạo request tiếp theo theo hợp đồng hypermedia.
