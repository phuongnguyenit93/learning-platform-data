# page, size, sort và quy ước tham số HTTP

Một màn hình danh sách thường cần ba quyết định: lấy đoạn dữ liệu nào, lấy tối đa bao nhiêu phần tử và đặt chúng theo thứ tự nào. Trong Spring Data, các quyết định đó được biểu diễn bằng `Pageable` và `Sort`. Ở biên HTTP, Spring Data Web Support có thể chuyển query parameter thành những đối tượng này để controller nhận trực tiếp.

Bài học thuộc chương **Tham số web** của module **SPRING_DATA_COMMONS**. Trọng tâm là hợp đồng HTTP dùng chung cho phân trang và sắp xếp. Commons cung cấp abstraction; khả năng thực thi trên repository, derived query, Query by Example hoặc projection còn phụ thuộc store, loại truy vấn và driver đang sử dụng. Tham số phân trang không tự tạo điều kiện lọc, quyền truy cập hay auditing.

## 1. Từ URL đến repository

Xét yêu cầu:

```http
GET /orders?page=2&size=10&sort=createdAt,desc&sort=id,asc
```

Với quy ước bắt đầu từ 0, client đang yêu cầu trang thứ ba, tối đa 10 đơn hàng, ưu tiên ngày tạo giảm dần rồi mã đơn hàng tăng dần.

Luồng xử lý điển hình:

```text
Query parameter trong HTTP
        |
        v
Argument resolver của Spring Data Web
        |
        v
Pageable chứa số trang, kích thước trang và Sort
        |
        v
Controller -> kiểm tra chính sách -> application service
        |
        v
Repository/query của store cụ thể
        |
        v
Dữ liệu và metadata trả về cho client
```

`PageableHandlerMethodArgumentResolver` xử lý thông tin phân trang; resolver dành cho `Sort` xử lý thứ tự. Với cấu hình MVC phù hợp, controller có thể nhận `Pageable` mà không cần tự tách chuỗi query. Đây là chức năng được mô tả trong [API của PageableHandlerMethodArgumentResolver](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PageableHandlerMethodArgumentResolver.html).

Có Spring Data Commons trên classpath chưa đủ để kết luận ứng dụng đã đăng ký tích hợp web. Một ứng dụng MVC phải có Spring Data Web Support được bật, chẳng hạn qua `@EnableSpringDataWebSupport`, hoặc qua cơ chế cấu hình tự động phù hợp của ứng dụng. Ví dụ dưới đây dùng Spring MVC; không chuyển nguyên cấu hình servlet này sang WebFlux rồi mặc định mọi resolver giống nhau.

## 2. Ý nghĩa của page và size

### 2.1. Số trang bắt đầu từ đâu?

Theo cấu hình web mặc định:

| Tham số | Vai trò | Khi không truyền |
| --- | --- | --- |
| `page` | Chỉ số trang, bắt đầu từ 0 | `0` |
| `size` | Kích thước trang được yêu cầu | `20` |
| `sort` | Thuộc tính và hướng sắp xếp | Không yêu cầu thứ tự cụ thể |

Các giá trị này là mặc định của resolver khi không có annotation hoặc cấu hình khác ghi đè. Chúng được công bố trong [tài liệu Spring Data Web Support](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions-web.html).

Ví dụ với `size=10`:

| URL | Trang theo cách gọi của người dùng | Offset logic |
| --- | --- | --- |
| `/orders?page=0&size=10` | Trang thứ nhất | 0 |
| `/orders?page=1&size=10` | Trang thứ hai | 10 |
| `/orders?page=2&size=10` | Trang thứ ba | 20 |

Với phân trang bằng offset:

```text
offset = pageNumber * pageSize
```

Đây là cách xác định vị trí logic, không phải lời khẳng định mọi store sẽ phát sinh một câu SQL có cú pháp giống nhau. Một store phi quan hệ có thể dùng cơ chế thực thi khác; repository không hỗ trợ dạng phân trang này cũng không tự có thêm khả năng chỉ vì controller nhận được `Pageable`.

Giao diện hiển thị “trang 1” có thể gửi `page=0`. Việc cộng hoặc trừ 1 phải được thống nhất tại ranh giới giao tiếp, tránh frontend và backend cùng chuyển đổi khiến lệch hai lần.

### 2.2. size là giới hạn yêu cầu, không phải số phần tử chắc chắn nhận được

Giả sử có 23 đơn hàng thỏa điều kiện, `size=10` thì một trang cuối có thể chỉ có 3 phần tử. Vì vậy:

- `pageSize` diễn tả kích thước trang.
- Số phần tử thực tế là độ dài danh sách trả về.
- Tổng số phần tử là số bản ghi thỏa toàn bộ điều kiện truy vấn, nếu loại kết quả có cung cấp thông tin đó.

Không dùng `items.length == size` làm bằng chứng chắc chắn còn trang tiếp theo. Đúng 10 phần tử có thể là trang cuối của một tập dữ liệu có đúng 10 phần tử. Cần dựa vào hợp đồng metadata như `hasNext`, `totalPages` hoặc cơ chế lấy thêm dữ liệu mà endpoint đã chọn.

### 2.3. Không nhầm quy tắc của PageRequest với xử lý đầu vào HTTP

Khi tự tạo `PageRequest`, số trang phải không âm và kích thước trang phải lớn hơn 0. Ví dụ sau yêu cầu trang đầu có 25 phần tử:

```java
Pageable pageable = PageRequest.of(0, 25);
```

Đây là ràng buộc của [PageRequest API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/PageRequest.html). Nó không có nghĩa mọi query parameter sai đều làm HTTP trả 400, vì resolver có thể chuẩn hóa đầu vào trước khi gọi constructor.

## 3. sort mô tả thứ tự như thế nào?

### 3.1. Một thuộc tính và một hướng

```http
GET /orders?sort=createdAt,desc
GET /orders?sort=id,asc
GET /orders?sort=customerName
```

Khi không chỉ định hướng, quy ước mặc định là tăng dần. Không truyền sort có nghĩa không yêu cầu một thứ tự cụ thể, trừ khi endpoint đã đặt sort mặc định. Thứ tự quan sát được từ cơ sở dữ liệu trong vài lần thử không thay thế cho một hợp đồng sắp xếp.

Tránh tự thêm khoảng trắng vào biểu thức như `sort=createdAt, desc`. Client nên sinh giá trị chuẩn `createdAt,desc` và dùng thư viện xây dựng URL để encode các ký tự cần thiết.

### 3.2. Nhiều thuộc tính và thứ tự ưu tiên

Hai thuộc tính có cùng hướng có thể biểu diễn:

```http
GET /orders?sort=customerName,id,asc
```

Nếu mỗi thuộc tính cần một hướng riêng, lặp lại tham số:

```http
GET /orders?sort=createdAt,desc&sort=id,asc
```

Trong hợp đồng này, `createdAt` có ưu tiên cao hơn; `id` phân định khi giá trị ngày tạo bằng nhau. Không diễn đạt hai hướng riêng bằng `sort=createdAt,desc,id,asc` rồi kỳ vọng parser hiểu thành hai cặp.

Frontend phải giữ các giá trị lặp. Ví dụ với API URL của JavaScript:

```javascript
const params = new URLSearchParams();
params.set("page", "0");
params.set("size", "20");
params.append("sort", "createdAt,desc");
params.append("sort", "id,asc");

const url = "/orders?" + params.toString();
```

Gọi `set("sort", ...)` hai lần sẽ thay giá trị trước đó. Với công cụ kiểm thử HTTP, cũng cần kiểm tra client có giữ nguyên query parameter trùng tên hay không.

### 3.3. IgnoreCase là yêu cầu sắp xếp

Một biểu thức có thể mang tùy chọn không phân biệt hoa thường:

```http
GET /customers?sort=name,asc,ignorecase
```

Cú pháp nhiều thuộc tính, hướng và `IgnoreCase` được mô tả trong [quy ước sort của Spring Data Web](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions-web.html). Resolver diễn đạt yêu cầu; store quyết định khả năng áp dụng.

Không suy ra rằng tùy chọn này tự bỏ dấu tiếng Việt, thay collation của database hoặc làm bộ lọc tìm kiếm trở thành không phân biệt hoa thường. Những hành vi đó phải có thiết kế và hỗ trợ riêng.

## 4. Ví dụ controller có hợp đồng đầu ra rõ ràng

Ví dụ sau dùng Java 17 trở lên, Spring MVC và Spring Data Web Support đã được đăng ký. `OrderQueryService` là cổng truy vấn do ứng dụng tự cài đặt bằng store phù hợp; đoạn mã không giả định Commons tự cung cấp implementation.

```java
import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderQueryService queries;

    OrderController(OrderQueryService queries) {
        this.queries = queries;
    }

    @GetMapping
    PageResponse<OrderSummary> list(
            @PageableDefault(page = 0, size = 20, sort = "id")
            Pageable pageable) {

        Page<OrderSummary> result = queries.find(pageable);
        return PageResponse.from(result);
    }
}

interface OrderQueryService {
    Page<OrderSummary> find(Pageable pageable);
}

record OrderSummary(Long id, String customerName) {
}

record PageResponse<T>(
        List<T> items,
        int page,
        int size,
        long totalElements,
        int totalPages) {

    static <T> PageResponse<T> from(Page<T> result) {
        return new PageResponse<>(
                result.getContent(),
                result.getNumber(),
                result.getSize(),
                result.getTotalElements(),
                result.getTotalPages());
    }
}
```

Đoạn controller minh họa binding và biểu diễn kết quả; ứng dụng thực tế cần bổ sung chính sách kiểm tra sort như phần 7 trước khi gọi repository.

Một phản hồi hợp lệ theo DTO trên có thể là:

```json
{
  "items": [
    {"id": 51, "customerName": "Lan"},
    {"id": 52, "customerName": "Minh"}
  ],
  "page": 0,
  "size": 20,
  "totalElements": 2,
  "totalPages": 1
}
```

Trường `page` trong DTO này vẫn bắt đầu từ 0. Hai phần tử thực tế không làm `size` đổi thành 2.

`Page` cung cấp thông tin tổng phần tử và tổng trang; xem [Page API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Page.html). DTO trên là hợp đồng do ứng dụng chủ động định nghĩa, tránh buộc client phụ thuộc vào toàn bộ cấu trúc serialize của implementation phân trang.

Nếu endpoint chỉ cần biết còn trang tiếp hay không, có thể thiết kế kết quả theo `Slice`. Khi đó cần đổi cả cổng truy vấn và metadata phản hồi; không tự điền tổng số phần tử khi chưa thực sự có dữ liệu đó. Cách lấy tổng số bản ghi và chi phí truy vấn phụ thuộc store, không phải hệ quả miễn phí của việc thêm `size` vào URL.

## 5. Giá trị mặc định, giá trị client và giới hạn tối đa

### 5.1. Annotation là fallback, không phải khóa cố định

Trong ví dụ controller:

```java
@PageableDefault(page = 0, size = 20, sort = "id")
Pageable pageable
```

Client không truyền thông tin tương ứng thì endpoint có mặc định rõ ràng. Khi client gửi `size=5`, annotation không buộc kích thước phải luôn là 20.

Một điểm dễ nhầm: chỉ viết `@PageableDefault` mà không đặt `size` thì mặc định của annotation là **10**. Đây là một nguồn mặc định khác với fallback **20** của resolver. Xem khai báo [PageableDefault](https://docs.spring.io/spring-data/rest/reference/data-commons/api/java/org/springframework/data/web/PageableDefault.html).

Sort mặc định cũng không phải một danh sách luôn được nối thêm vào sort của client. Nếu bắt buộc mọi truy vấn phải có khóa phân định như `id`, hãy bổ sung bằng chính sách riêng sau khi nhận đầu vào.

### 5.2. Giới hạn size ở cấu hình dùng chung

Ví dụ cấu hình MVC độc lập:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.web.config.EnableSpringDataWebSupport;
import org.springframework.data.web.config.PageableHandlerMethodArgumentResolverCustomizer;

@Configuration
@EnableSpringDataWebSupport
class PagingWebConfiguration {

    @Bean
    PageableHandlerMethodArgumentResolverCustomizer pageableCustomizer() {
        return resolver -> {
            resolver.setFallbackPageable(PageRequest.of(0, 20));
            resolver.setMaxPageSize(100);
            resolver.setOneIndexedParameters(false);
        };
    }
}
```

Nếu ứng dụng đã có một cơ chế đăng ký Spring Data Web Support, cần tích hợp customizer vào cơ chế đó thay vì tạo thêm các cấu hình cạnh tranh. Trong ví dụ, 100 là quyết định của ứng dụng, không phải lời khẳng định đó là giới hạn mặc định của mọi phiên bản Spring Data.

Các setter cấu hình kích thước tối đa, fallback và cách đánh chỉ số được công bố trong [PageableHandlerMethodArgumentResolverSupport API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PageableHandlerMethodArgumentResolverSupport.html).

Giới hạn size bảo vệ một lần lấy dữ liệu. Nó không thay thế việc giới hạn chi phí của bộ lọc, quan hệ cần tải hoặc offset quá lớn.

### 5.3. HTTP bắt đầu từ 1 vẫn có thể dùng mô hình nội bộ bắt đầu từ 0

Nếu ứng dụng chọn:

```java
resolver.setOneIndexedParameters(true);
```

thì `page=1` trong request được hiểu là trang đầu. Điều này không đổi quy tắc của `PageRequest` thành bắt đầu từ 1. DTO phản hồi tự tạo bằng `result.getNumber()` vẫn cần chuyển đổi riêng nếu hợp đồng đầu ra cũng muốn đánh số từ 1.

Phải công bố nhất quán quy ước request, metadata và đường dẫn chuyển trang. Không để API nhận trang đầu là 1 nhưng frontend lại coi `page=0` trong phản hồi là trang không hợp lệ.

## 6. Đầu vào sai không tự động đồng nghĩa HTTP 400

Cần phân biệt **chuẩn hóa bằng resolver** với **kiểm tra hợp đồng API nghiêm ngặt**.

Với hành vi chuẩn hóa của resolver, các trường hợp như số trang âm, size bằng 0, chuỗi không phải số hoặc size vượt mức có thể được đưa về biên, fallback hoặc mức tối đa. Không giả định tất cả đều phát sinh lỗi HTTP.

[Mã nguồn của resolver support](https://raw.githubusercontent.com/spring-projects/spring-data-commons/main/src/main/java/org/springframework/data/web/PageableHandlerMethodArgumentResolverSupport.java) thể hiện việc parse và giới hạn trước khi tạo `PageRequest`. Khi xây dựng hợp đồng cho một ứng dụng cụ thể, cần đối chiếu phiên bản dependency thực tế.

Ví dụ ứng dụng có thể chọn một trong hai chính sách:

| Trường hợp | Chính sách chuẩn hóa | Chính sách từ chối |
| --- | --- | --- |
| `size=1000`, mức tối đa 100 | Xử lý với size 100 | Trả 400 và mô tả giới hạn |
| `page=-1` | Xử lý theo biên dưới | Trả 400 vì page không hợp lệ |
| `size=abc` | Xử lý theo fallback | Trả 400 vì sai kiểu |

Bảng trên mô tả hai lựa chọn thiết kế, không khẳng định cả hai đều là hành vi mặc định.

Nếu yêu cầu là từ chối giá trị thô sai, cần kiểm tra raw request hoặc dùng cơ chế binding/validation do ứng dụng kiểm soát trước khi mất thông tin ban đầu. Chỉ nhìn `Pageable` đã chuẩn hóa có thể không còn biết client đã gửi `size=1000` hay `size=100`.

Đừng trông chờ `@Valid` đặt cạnh một tham số `Pageable` sẽ tự thực thi mọi quy tắc nghiệp vụ. Khi API định nghĩa `page` và `size` là đơn trị, cũng nên quyết định cách xử lý request như `page=1&page=2`; không để các thành phần trung gian và backend chọn giá trị khác nhau ngoài ý muốn.

## 7. Tên thuộc tính sort là một phần của hợp đồng

### 7.1. Không đồng nhất tên thuộc tính với tên cột hoặc tên JSON

Giả sử domain có property `createdAt`, database có cột `created_at`, còn DTO dùng trường `createdTime`. Resolver không tự biết ba tên này tương đương.

Khi truyền sort xuống repository, cần dùng tên hoặc đường dẫn mà loại truy vấn và store đó hỗ trợ. Đổi tên trường JSON không tự đổi ngôn ngữ sort của repository. Nếu muốn công khai một tên khác, ứng dụng phải ánh xạ và kiểm tra trước khi thực thi.

Projection cũng không bảo đảm mọi field hiển thị đều có thể dùng làm khóa sort. Một giá trị tính toán trên DTO có thể không tương ứng với một thuộc tính truy vấn được.

### 7.2. Kiểm tra thuộc tính được phép và thêm khóa phân định

Chính sách ví dụ cho domain có `id` và `customerName`:

```java
import java.util.Set;

import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

// Có thể đặt trong lớp chính sách truy vấn của ứng dụng.
static Pageable checkedPageable(Pageable input) {
    Set<String> allowed = Set.of("id", "customerName");

    for (Sort.Order order : input.getSort()) {
        if (!allowed.contains(order.getProperty())) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Unsupported sort property");
        }
    }

    Sort sort = input.getSort();

    if (sort.getOrderFor("id") == null) {
        sort = sort.and(Sort.by("id").ascending());
    }

    return PageRequest.of(
            input.getPageNumber(),
            input.getPageSize(),
            sort);
}
```

Hàm này giả định nhận `Pageable` có phân trang từ cấu hình trong bài; nếu ứng dụng cho phép `unpaged`, cần xử lý nhánh đó trước khi đọc số trang và kích thước. Thay lời gọi service bằng `queries.find(checkedPageable(pageable))` để áp dụng chính sách cho controller minh họa.

Đây là kiểm tra tên thuộc tính và bổ sung thứ tự, chưa phải toàn bộ chính sách truy vấn. Ứng dụng còn cần xác định có cho phép `ignorecase`, đường dẫn lồng nhau hay những tổ hợp sort tốn kém không. Các phương thức ghép thứ tự và tra cứu order được mô tả trong [Sort API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Sort.html).

Với nhiều bản ghi có cùng `customerName`, khóa `id` duy nhất giúp phân định thứ tự. Tuy nhiên, thứ tự xác định không tạo ra một snapshot dữ liệu giữa nhiều request. Nếu bản ghi được thêm hoặc cập nhật trong lúc người dùng chuyển trang, phân trang offset vẫn có thể gặp dữ liệu dịch chuyển.

Không nối trực tiếp giá trị sort chưa kiểm tra vào SQL hoặc một ngôn ngữ truy vấn tự xây dựng. Tham số sort không cấp quyền truy cập vào mọi thuộc tính domain, và khả năng parse thành `Sort` không chứng minh truy vấn hợp lệ.

## 8. Tham số phân trang không phải điều kiện lọc hay cấu hình tính năng

Với request:

```http
GET /orders?status=PAID&page=0&size=20&sort=id,asc
```

`Pageable` chỉ mang thông tin phân trang và sắp xếp. Để lọc đơn hàng đã thanh toán, controller hoặc service phải tiếp nhận `status` và đưa nó vào derived query, Query by Example hoặc cơ chế truy vấn được store hỗ trợ.

Tương tự:

- Điều kiện tenant và quyền truy cập phải được áp dụng khi truy vấn dữ liệu.
- Chọn projection phải được endpoint và repository hỗ trợ rõ ràng.
- Đọc một trường auditing như ngày tạo để sắp xếp đòi hỏi trường đó tồn tại và truy vấn được; `sort=createdAt` không tự bật auditing.
- Không bỏ qua lỗi sort rồi trả dữ liệu không sắp xếp như thể yêu cầu đã được đáp ứng.

Tổng số phần tử trong metadata phải tương ứng với cùng phạm vi lọc và quyền truy cập của danh sách trả về. Một count trên toàn bộ bảng trong khi nội dung chỉ lấy tenant hiện tại sẽ tạo hợp đồng sai và có thể tiết lộ thông tin ngoài phạm vi.

## 9. Hai tập phân trang trong cùng một request

Một trang dashboard có thể hiển thị danh sách đơn hàng và khách hàng độc lập. Khi có nhiều tham số `Pageable`, dùng qualifier để phân biệt:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.domain.Pageable;

void loadDashboard(
        @Qualifier("orders") Pageable orders,
        @Qualifier("customers") Pageable customers) {
    // Mỗi đối tượng được chuyển đến truy vấn tương ứng.
}
```

Đây là chữ ký minh họa cho một handler; cần thêm mapping và kiểu trả về thích hợp trong ứng dụng thực tế.

Với quy ước qualifier mặc định, client có thể gửi:

```http
GET /dashboard?orders_page=0&orders_size=10&orders_sort=id,desc&customers_page=1&customers_size=5
```

Tiền tố qualifier phải được frontend, tài liệu API và backend thống nhất. Chỉ đổi tên biến Java từ `orders` thành tên khác không thay thế cho annotation phân biệt hai đối tượng. Nếu đổi dấu phân cách hay tên tham số ở cấu hình, các ví dụ URL cũng phải theo cấu hình đó.

## 10. Các tình huống cần xác nhận trong ứng dụng

Một hợp đồng HTTP có thể được mô tả bằng những trường hợp sau:

| Tình huống | Điều cần quan sát |
| --- | --- |
| Không truyền query parameter | Trang, size và sort mặc định của endpoint |
| `page=0&size=5` | Trang đầu với giới hạn 5 |
| `page=1&size=5` | Trang tiếp theo theo quy ước bắt đầu từ 0 |
| Hai tham số sort | Giữ đủ khóa và đúng thứ tự ưu tiên |
| Không truyền hướng sort | Áp dụng quy ước hướng mặc định |
| Size vượt mức | Chuẩn hóa hoặc trả lỗi đúng hợp đồng đã công bố |
| Property sort không được phép | Từ chối có kiểm soát trước khi gọi query |
| Nhiều bản ghi có cùng giá trị ở khóa sort đầu tiên | Có khóa phụ duy nhất để phân định |
| Không có bản ghi phù hợp | Danh sách rỗng và metadata nhất quán |
| Thay đổi dữ liệu giữa hai request | Nhận biết giới hạn nhất quán của offset |
| Store không hỗ trợ yêu cầu | Thể hiện giới hạn thay vì hứa cùng hành vi ở mọi store |

Có thể thử trực tiếp cách truyền nhiều sort:

```bash
curl --get "http://localhost:8080/orders" \
  --data-urlencode "page=0" \
  --data-urlencode "size=5" \
  --data-urlencode "sort=customerName,asc" \
  --data-urlencode "sort=id,asc"
```

Khi hoàn thiện một endpoint, hãy công bố rõ điểm bắt đầu của page, size mặc định và tối đa, danh sách sort được phép, thứ tự mặc định, cách xử lý đầu vào sai và ý nghĩa metadata. Những quyết định này giúp client sử dụng abstraction phân trang của Spring Data mà vẫn tôn trọng giới hạn của repository và kho dữ liệu thực tế.
