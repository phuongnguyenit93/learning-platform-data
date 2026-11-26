# Tham số size

## Mục tiêu

Khi API trả về một collection lớn, client thường yêu cầu dữ liệu theo từng trang. Tham số query size cho biết số phần tử tối đa client muốn nhận trong một trang. Trong Spring Data, tham số này được phân giải thành thuộc tính page size của Pageable; repository dùng Pageable để truy vấn Page<T>; Spring HATEOAS dùng Page cùng PagedResourcesAssembler để tạo PagedModel có metadata và các links điều hướng.

Hiểu đúng size giúp API kiểm soát kích thước response, hạn chế truy vấn quá lớn và giữ các link phân trang nhất quán. Size cũng cần được giới hạn ở server vì client có thể gửi bất kỳ giá trị nào trong query string.

Sau bài học, bạn có thể:

- Giải thích ý nghĩa của query parameter size trong phân trang.
- Phân biệt page size với số phần tử thực tế và tổng số kết quả.
- Cấu hình giá trị size mặc định và giới hạn tối đa.
- Dùng Pageable và @PageableDefault trong controller.
- Hiểu cách PagedResourcesAssembler giữ size trong links HAL.
- Kiểm thử size, metadata và links điều hướng.

## Tham số size có ý nghĩa gì?

Một request phân trang có thể có dạng:

~~~http
GET /api/orders?page=0&size=20
Accept: application/hal+json
~~~

Trong ví dụ:

- page=0 yêu cầu trang đầu tiên theo cách đánh số mặc định của Spring Data.
- size=20 yêu cầu tối đa 20 đơn hàng trong trang.

Size không phải tổng số bản ghi của collection và cũng không phải số trang. Nó là giới hạn số phần tử trong một trang. Nếu trang cuối chỉ còn 3 kết quả, request size=20 vẫn có thể trả về 3 phần tử.

Hãy phân biệt các giá trị:

| Giá trị | Ý nghĩa | Ví dụ |
|---|---|---|
| Pageable.getPageSize() | Kích thước trang được áp dụng cho truy vấn. | 20 |
| Page.getNumberOfElements() | Số phần tử thực tế trong content của trang hiện tại. | 3 |
| Page.getTotalElements() | Tổng số kết quả sau khi áp dụng điều kiện lọc. | 43 |
| Page.getTotalPages() | Tổng số trang theo kích thước trang hiện tại. | 3 |

Với 43 kết quả và size=20, các trang lần lượt có 20, 20 và 3 phần tử. Trang cuối vẫn có page size là 20 trong metadata, nhưng content chỉ chứa 3 phần tử.

## Spring MVC phân giải size thành Pageable

Spring Data Web cung cấp cơ chế phân giải query parameters thành Pageable. Controller không cần tự đọc chuỗi page và size rồi tạo PageRequest:

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    @GetMapping("/api/orders")
    OrderPageResponse findAll(Pageable pageable) {
        return orderService.findAll(pageable);
    }
}
~~~

Với cấu hình mặc định, Spring Data nhận các tham số page, size và sort. Request sau:

~~~http
GET /api/orders?page=2&size=15&sort=createdAt,desc
~~~

được chuyển thành Pageable có page number 2, page size 15 và sort theo createdAt giảm dần. Page number mặc định bắt đầu từ 0.

Trong ứng dụng Spring Boot, Spring Data Web thường được cấu hình tự động khi dependency Spring Data phù hợp có mặt. Nếu cấu hình Spring MVC thủ công, bật hỗ trợ bằng @EnableSpringDataWebSupport:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.web.config.EnableSpringDataWebSupport;

@Configuration
@EnableSpringDataWebSupport
class SpringDataWebConfiguration {
}
~~~

Không nên tự phân tích size bằng request.getParameter() nếu controller đã có thể nhận Pageable. Dùng resolver chuẩn giúp các endpoint chia sẻ cùng quy tắc mặc định, giới hạn và tên tham số.

## Giá trị size mặc định

Nếu client không gửi size, Spring Data dùng page size mặc định. Giá trị mặc định có thể được cấu hình toàn ứng dụng hoặc chỉ định cho một tham số Pageable.

### Cấu hình theo controller bằng @PageableDefault

Annotation @PageableDefault đặt giá trị mặc định cho một endpoint:

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;

@GetMapping("/api/orders")
PagedModel<EntityModel<OrderResponse>> findAll(
        @PageableDefault(
                size = 25,
                sort = "createdAt",
                direction = Sort.Direction.DESC)
        Pageable pageable,
        PagedResourcesAssembler<Order> pagedAssembler) {

    Page<Order> page = orderService.findAll(pageable);
    return pagedAssembler.toModel(page, orderAssembler);
}
~~~

Khi client không gửi size, endpoint dùng 25. Nếu client gửi size=10, resolver dùng giá trị client yêu cầu, sau khi áp dụng giới hạn tối đa của server. @PageableDefault cũng có thể đặt page, sort và direction.

Đặt mặc định theo endpoint hữu ích khi collection có đặc điểm khác nhau. Ví dụ, danh sách đơn hàng có thể mặc định 25 phần tử, trong khi danh sách sự kiện có thể mặc định 50 phần tử.

### Cấu hình mặc định toàn ứng dụng trong Spring Boot

Có thể cấu hình trong application.properties:

~~~properties
spring.data.web.pageable.default-page-size=20
spring.data.web.pageable.max-page-size=100
spring.data.web.pageable.page-parameter=page
spring.data.web.pageable.size-parameter=size
spring.data.web.pageable.one-indexed-parameters=false
spring.data.web.sort.sort-parameter=sort
~~~

Trong đó:

- default-page-size là size mặc định khi request không truyền size và method parameter không đặt mặc định riêng.
- max-page-size là giới hạn trên cho size do client yêu cầu.
- page-parameter và size-parameter cho phép đổi tên query parameters.
- one-indexed-parameters điều chỉnh cách đánh số page trong request.
- sort-parameter đặt tên query parameter cho sắp xếp.

Nếu cấu hình tên size thành limit, client gửi limit=20 thay cho size=20. Các links phân trang được tạo từ resolver cần sử dụng cùng quy ước để client có thể tiếp tục điều hướng.

## Giới hạn size để bảo vệ server

Không nên tin rằng client luôn gửi một size hợp lý. Một request như:

~~~http
GET /api/orders?page=0&size=1000000
~~~

có thể buộc ứng dụng đọc và chuyển đổi một lượng dữ liệu rất lớn, làm tăng tải database, bộ nhớ, CPU và kích thước response. Server cần giới hạn page size tối đa.

Với Spring Boot, đặt max-page-size trong application.properties:

~~~properties
spring.data.web.pageable.default-page-size=20
spring.data.web.pageable.max-page-size=100
~~~

Trong cấu hình Spring Data Web, có thể dùng PageableHandlerMethodArgumentResolverCustomizer để điều chỉnh resolver:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.web.PageableHandlerMethodArgumentResolverCustomizer;

@Configuration
class PageableConfiguration {

    @Bean
    PageableHandlerMethodArgumentResolverCustomizer pageableCustomizer() {
        return resolver -> {
            resolver.setMaxPageSize(100);
            resolver.setFallbackPageable(PageRequest.of(0, 20));
        };
    }
}
~~~

Customizer cho phép cấu hình giới hạn và fallback Pageable trong ứng dụng dùng resolver được Spring Data Web quản lý. Nếu đã cấu hình cùng thuộc tính qua Spring Boot properties, tránh khai báo nhiều nơi với giá trị mâu thuẫn.

Giới hạn size là một phần của chính sách API. Hãy chọn max phù hợp với chi phí truy vấn, kích thước DTO, số lượng links và độ trễ mà client có thể chấp nhận. Với endpoint trả về dữ liệu nặng, max size có thể cần thấp hơn endpoint chỉ trả DTO tóm tắt.

## Size ảnh hưởng tới Page và PagedModel

Service hoặc repository nhận Pageable và trả Page<T>. PagedResourcesAssembler chuyển Page thành PagedModel để response chứa item representations, page metadata và links.

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.PagedModel;

@GetMapping("/api/orders")
PagedModel<EntityModel<OrderResponse>> findAll(
        Pageable pageable,
        PagedResourcesAssembler<Order> pagedAssembler) {

    Page<Order> page = orderService.findAll(pageable);
    return pagedAssembler.toModel(page, orderAssembler);
}
~~~

Ví dụ request:

~~~http
GET /api/orders?page=1&size=10
Accept: application/hal+json
~~~

Nếu có 23 kết quả, page hiện tại có 10 phần tử và còn một trang tiếp theo với 3 phần tử. PagedModel có metadata tương tự:

~~~json
{
  "_embedded": {
    "orderResponseList": [
      {
        "id": "order-11",
        "status": "PAID"
      }
    ]
  },
  "_links": {
    "first": {
      "href": "/api/orders?page=0&size=10"
    },
    "prev": {
      "href": "/api/orders?page=0&size=10"
    },
    "self": {
      "href": "/api/orders?page=1&size=10"
    },
    "next": {
      "href": "/api/orders?page=2&size=10"
    },
    "last": {
      "href": "/api/orders?page=2&size=10"
    }
  },
  "page": {
    "size": 10,
    "totalElements": 23,
    "totalPages": 3,
    "number": 1
  }
}
~~~

Ví dụ rút gọn chỉ hiển thị một item để minh họa. Response thật có thể chứa đủ 10 item trong trang. Điểm quan trọng là các page links giữ size=10 để client tiếp tục điều hướng với cùng kích thước trang.

Khi client đi theo link next, không cần tự tăng page hoặc tự nối size. Client chỉ cần theo href do server cung cấp. Điều này cũng giúp server thay đổi tên tham số hoặc quy tắc phân trang mà client không cần biết chi tiết.

## Đổi tên tham số size

Một số API muốn dùng limit thay cho size để thống nhất với quy ước hiện có. Có thể cấu hình:

~~~properties
spring.data.web.pageable.size-parameter=limit
spring.data.web.pageable.page-parameter=page
~~~

Request sẽ có dạng:

~~~http
GET /api/orders?page=0&limit=25
~~~

Resolver tạo Pageable từ limit. PagedResourcesAssembler sử dụng cấu hình resolver để xây links tương ứng. Vì vậy, link next/prev cũng cần có limit=25 thay vì size=25.

Không nên hỗ trợ đồng thời nhiều tên tham số size nếu không có lý do tương thích rõ ràng. Nhiều quy ước đầu vào làm tài liệu và test phức tạp hơn. Nếu cần đổi tên, hãy thực hiện như thay đổi hợp đồng API và cập nhật client.

## Nhiều tham số Pageable trong một endpoint

Một endpoint đôi khi cần phân trang cho hai collection độc lập. Spring Data Web hỗ trợ @Qualifier để phân biệt các Pageable:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.domain.Pageable;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping("/api/dashboard")
DashboardResponse dashboard(
        @Qualifier("orders") Pageable ordersPageable,
        @Qualifier("payments") Pageable paymentsPageable) {

    Page<Order> orders = orderService.findAll(ordersPageable);
    Page<Payment> payments = paymentService.findAll(paymentsPageable);

    return DashboardResponse.from(orders, payments);
}
~~~

Với qualifier delimiter mặc định là dấu gạch dưới, request có thể dùng:

~~~http
GET /api/dashboard?orders_page=0&orders_size=10&payments_page=0&payments_size=5
~~~

Ở đây, orders_size và payments_size điều khiển hai collection khác nhau. Hãy đặt tên qualifier rõ nghĩa và kiểm thử riêng từng Pageable để tránh nhầm kích thước trang giữa các tập dữ liệu.

## Chọn size phù hợp với loại endpoint

Không có một size tối ưu cho mọi API. Khi chọn default và max, cân nhắc:

- **Kích thước mỗi item:** DTO lớn hoặc có nhiều embedded resources cần size nhỏ hơn.
- **Chi phí truy vấn:** join, sort và filter phức tạp có thể khiến size lớn rất tốn kém.
- **Tần suất điều hướng:** size quá nhỏ khiến client phải gọi nhiều lần; size quá lớn tăng latency và payload.
- **Nhu cầu hiển thị:** màn hình nhỏ có thể chỉ cần 10–20 item; tác vụ export có thể cần cơ chế riêng.
- **Tính nhất quán:** giữ size trong links để client tiếp tục cùng cách phân trang.

Nếu truy vấn không cần tổng số kết quả, cân nhắc Slice hoặc cursor/keyset pagination thay cho Page. Page thường cần biết totalElements và totalPages, có thể phát sinh count query. Slice tập trung vào content và việc có trang tiếp theo; cursor pagination có thể phù hợp hơn với collection rất lớn hoặc dữ liệu thay đổi liên tục. Các cách này có hợp đồng metadata và links khác với PagedModel dựa trên Page.

Không dùng size lớn như một cách thay thế cho endpoint export. Nếu client cần tải toàn bộ dữ liệu, hãy thiết kế luồng export có giới hạn, bất đồng bộ hoặc streaming phù hợp với quy mô.

## Kiểm thử tham số size

MockMvc có thể xác minh size client yêu cầu được phản ánh trong metadata PagedModel:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api/orders")
                .param("page", "0")
                .param("size", "5")
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.page.size").value(5))
        .andExpect(jsonPath("$._links.self.href").value(
                org.hamcrest.Matchers.containsString("size=5")));
~~~

Để kiểm tra giới hạn tối đa, gửi size lớn hơn max-page-size đã cấu hình và xác minh metadata cùng links phản ánh size hiệu lực theo chính sách resolver. Ví dụ max là 100, request size=500 không được tạo page có 500 phần tử.

Nên kiểm thử:

- Không gửi size: dùng fallback hoặc @PageableDefault đúng.
- Gửi size nhỏ hơn max: giữ size client yêu cầu.
- Gửi size lớn hơn max: áp dụng giới hạn server.
- Trang cuối có ít item hơn size nhưng metadata size vẫn đúng.
- Link next/prev giữ size và sort hiện tại.
- Đổi tên tham số thành limit: request và links đều dùng limit.
- Có nhiều Pageable: qualifier phân tách đúng các tham số.

## Những lỗi thường gặp

- **Coi size là tổng số bản ghi:** size chỉ là số phần tử tối đa của một trang.
- **Nhầm size với số phần tử thực tế:** trang cuối có thể ít item hơn size; xem Page.getNumberOfElements() để biết số item hiện tại.
- **Không đặt max page size:** client có thể yêu cầu payload rất lớn và làm tăng tải database.
- **Đặt default ở nhiều nơi:** application properties, resolver customizer và @PageableDefault có thể tạo chính sách khó hiểu nếu không thống nhất.
- **Tự ghép link phân trang:** PagedResourcesAssembler có thể tạo links từ Pageable và resolver; client nên theo href server cung cấp.
- **Đổi tên size nhưng quên links:** resolver và PagedResourcesAssembler phải dùng cùng cấu hình để link next/prev có đúng tên tham số.
- **Dùng Page cho mọi truy vấn:** nếu không cần total count, Slice hoặc cursor pagination có thể hiệu quả hơn.
- **Dùng size lớn để export:** export toàn bộ dữ liệu cần một luồng riêng với giới hạn và kiểm soát tài nguyên.

## Quy trình thiết kế size

1. Chọn default size phù hợp với payload và chi phí truy vấn.
2. Đặt max page size để bảo vệ database và ứng dụng.
3. Dùng Pageable ở controller để Spring Data Web phân giải page, size và sort.
4. Dùng @PageableDefault khi một endpoint cần mặc định riêng.
5. Trả Page<T> từ service/repository và chuyển thành PagedModel bằng PagedResourcesAssembler.
6. Xác minh page metadata và các links giữ size hiệu lực.
7. Kiểm thử giá trị mặc định, giá trị client gửi, giới hạn max và trường hợp trang cuối.

Tham số size cho client quyền chọn kích thước trang trong phạm vi server cho phép. Khi cấu hình default và max rõ ràng, dùng Pageable nhất quán và để PagedResourcesAssembler tạo links điều hướng, API Spring HATEOAS có thể phân trang dễ khám phá mà vẫn kiểm soát được tài nguyên hệ thống.
