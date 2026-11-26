# Nhiều Pageable hoặc Sort với @Qualifier

Một trang quản trị có thể hiển thị danh sách hóa đơn và danh sách yêu cầu hỗ trợ cùng lúc. Người dùng muốn xem trang thứ ba của hóa đơn, nhưng vẫn giữ yêu cầu hỗ trợ ở trang đầu; mỗi danh sách cũng có kích thước trang và thứ tự sắp xếp riêng. Một bộ query parameter `page`, `size`, `sort` không đủ để diễn đạt hai trạng thái độc lập ấy.

Trong chương **Tham số web** của **Spring Data Commons**, `@Qualifier` giúp phân biệt các tham số `Pageable` hoặc `Sort` trên cùng phương thức controller. Bài học tập trung vào hợp đồng HTTP và quá trình phân giải đối số; repository, derived query, projection và các khả năng của từng module lưu trữ vẫn là những lớp cần được thiết kế riêng. Qualifier chọn nhóm tham số web, còn module persistence quyết định truy vấn thực tế có thể làm gì.

## 1. Vấn đề: một request có nhiều danh sách

Giả sử endpoint `/api/dashboard` trả hai vùng dữ liệu:

| Vùng dữ liệu | Trạng thái người dùng muốn chọn | Nhóm tên đề xuất |
|---|---|---|
| Hóa đơn | Trang thứ ba, 20 dòng, mới nhất trước | `invoice` |
| Yêu cầu hỗ trợ | Trang đầu, 10 dòng, ưu tiên cao trước | `ticket` |

Nếu controller nhận hai `Pageable` không được định danh rõ, các tham số HTTP không thể tự biết `page=2` dành cho danh sách nào. Tên biến Java như `invoicePage` và `ticketPage` không tự tạo thành prefix của query parameter.

Với cấu hình mặc định của bộ phân giải tham số Spring Data Web, qualifier tạo các tên:

```text
invoice_page
invoice_size
invoice_sort

ticket_page
ticket_size
ticket_sort
```

Dấu nối mặc định giữa qualifier và tên tham số là dấu gạch dưới. Đây là namespace của tham số HTTP, không phải một object JSON lồng nhau.

## 2. Điều kiện để Pageable và Sort được phân giải

Các ví dụ dưới đây dùng **Spring MVC** và hạ tầng Spring Data Web đã được cấu hình. Trong một ứng dụng Spring Boot phù hợp, auto-configuration có thể thiết lập hạ tầng này. Trong cấu hình Spring MVC chủ động, `@EnableSpringDataWebSupport` là một cách bật hỗ trợ của Spring Data Web:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.web.config.EnableSpringDataWebSupport;

@Configuration
@EnableSpringDataWebSupport
class DataWebConfiguration {
}
```

Không cần thêm cấu hình này lần nữa nếu ứng dụng đã có bộ phân giải phù hợp. Cần hiểu cách cấu hình hiện tại đăng ký resolver, tránh tự đăng ký nhiều resolver cạnh tranh cho cùng loại đối số.

Đây là các kiểu và annotation khác nhau:

| Thành phần | Nhiệm vụ |
|---|---|
| `org.springframework.data.domain.Pageable` | Mô tả vị trí trang, kích thước và sắp xếp |
| `org.springframework.data.domain.Sort` | Mô tả thứ tự sắp xếp |
| `org.springframework.beans.factory.annotation.Qualifier` | Cung cấp tên qualifier để resolver phân biệt nhóm |
| `org.springframework.data.web.PageableDefault` | Khai báo giá trị mặc định cho từng `Pageable` |
| `org.springframework.data.web.SortDefault` | Khai báo sắp xếp mặc định |

`@Qualifier` còn được dùng trong dependency injection. Tuy nhiên, khi đặt trên đối số controller trong bài này, nó được bộ phân giải tham số web đọc để tạo tên query parameter. Nó không yêu cầu tạo bean mang tên `invoice` hay `ticket`.

Không gắn `@RequestParam` lên `Pageable` với kỳ vọng Spring sẽ chuyển một chuỗi thành toàn bộ object. Resolver của Spring Data có trách nhiệm đọc các tham số liên quan và tạo đối số tương ứng.

## 3. Hai Pageable trong cùng controller

Ví dụ endpoint có hai vùng dữ liệu độc lập:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/dashboard")
class DashboardController {

    private final DashboardService service;

    DashboardController(DashboardService service) {
        this.service = service;
    }

    @GetMapping
    DashboardResponse dashboard(
            @Qualifier("invoice")
            @PageableDefault(
                    size = 20,
                    sort = {"createdAt", "id"},
                    direction = Sort.Direction.DESC)
            Pageable invoicePage,

            @Qualifier("ticket")
            @PageableDefault(
                    size = 10,
                    sort = {"priority", "id"},
                    direction = Sort.Direction.DESC)
            Pageable ticketPage) {

        return service.load(invoicePage, ticketPage);
    }
}
```

`DashboardService` và `DashboardResponse` là hợp đồng nghiệp vụ, DTO của ứng dụng. Ví dụ giả định hóa đơn có các thuộc tính `createdAt`, `id`; yêu cầu hỗ trợ có `priority`, `id`; module persistence hỗ trợ cách sắp xếp đã chọn.

Request tương ứng:

```http
GET /api/dashboard?invoice_page=2&invoice_size=20&invoice_sort=createdAt,desc&invoice_sort=id,desc&ticket_page=0&ticket_size=10&ticket_sort=priority,desc&ticket_sort=id,desc
```

Với cách đánh số trang mặc định bắt đầu từ 0:

| Đối số Java | Số trang | Kích thước | Thứ tự |
|---|---:|---:|---|
| `invoicePage` | 2 | 20 | `createdAt DESC`, rồi `id DESC` |
| `ticketPage` | 0 | 10 | `priority DESC`, rồi `id DESC` |

`invoicePage.getOffset()` là `2 × 20 = 40`. Đây là offset logic mà `Pageable` mô tả; cách module chuyển nó thành truy vấn phụ thuộc kho dữ liệu và API repository thực tế.

Một `Pageable` đã bao gồm `Sort`. Do đó, hai bảng cần phân trang và sắp xếp độc lập thường chỉ cần hai `Pageable`; mỗi bảng có sẵn nhóm `*_sort` của nó.

## 4. Quy tắc qualifier khi có nhiều Pageable

Khi một phương thức có nhiều đối số `Pageable`, cần đặt qualifier rõ ràng và khác nhau cho **tất cả** các đối số đó. Hạ tầng kiểm tra tính phân biệt của chúng; không nên kỳ vọng nó đoán theo thứ tự khai báo hoặc tên biến Java.

Mẫu không hợp lệ:

```java
@GetMapping("/ambiguous")
DashboardResponse ambiguous(
        Pageable invoicePage,
        Pageable ticketPage) {
    // ...
}
```

Chỉ định danh một đối số cũng chưa giải quyết yêu cầu phân biệt nhiều `Pageable`:

```java
@GetMapping("/partly-qualified")
DashboardResponse partlyQualified(
        @Qualifier("invoice") Pageable invoicePage,
        Pageable ticketPage) {
    // ...
}
```

Dùng cùng qualifier cho hai `Pageable` cũng không tạo hai nhóm riêng:

```java
@GetMapping("/duplicate-qualifier")
DashboardResponse duplicateQualifier(
        @Qualifier("items") Pageable invoicePage,
        @Qualifier("items") Pageable ticketPage) {
    // ...
}
```

Các đoạn trên chỉ minh họa cấu hình cần tránh; phần thân được lược bỏ. Cách đúng là chọn hai giá trị như `invoice` và `ticket`, rồi công bố chúng trong hợp đồng API.

Tên qualifier được dùng như một phần của tên tham số. Nên chọn tên ngắn, ổn định và dễ phân biệt. Việc đổi `invoice` thành `billing` có thể làm client đang gửi `invoice_page` không còn tác động đến đối số mong muốn.

## 5. Không có tham số, hoặc chỉ gửi một nhóm

Với controller ở phần 3:

```http
GET /api/dashboard
```

Hai đối số vẫn được phân giải bằng giá trị mặc định của từng đối số: hóa đơn có kích thước 20, yêu cầu hỗ trợ có kích thước 10; cả hai bắt đầu ở trang mặc định.

Nếu chỉ gửi:

```http
GET /api/dashboard?invoice_page=4&invoice_size=30
```

Nhóm hóa đơn được thay đổi, còn nhóm yêu cầu hỗ trợ tiếp tục dùng mặc định. `@Qualifier` không làm mọi tham số trong nhóm trở thành bắt buộc.

Ngược lại, request sau không nhắm đến hai nhóm đã định danh theo quy ước mặc định:

```http
GET /api/dashboard?page=4&size=30&sort=createdAt,desc
```

Resolver đang chờ `invoice_page` hoặc `ticket_page`, nên bộ tên không có qualifier không tự trở thành một cấu hình chung áp dụng cho cả hai bảng. Nếu ứng dụng muốn hỗ trợ cú pháp khác, phải thiết kế và xử lý nó rõ ràng.

Có qualifier không đồng nghĩa có kiểm tra chặt mọi query parameter. Những tham số không được resolver sử dụng có thể không gây lỗi tự động. Một client gửi sai prefix có thể nhận response dùng mặc định thay vì nhận HTTP 400.

## 6. Hai Sort độc lập, không cần phân trang

Một endpoint xem trước thứ tự xuất báo cáo có thể nhận hai `Sort` riêng:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.SortDefault;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ExportPreviewController {

    private final ExportPreviewService service;

    ExportPreviewController(ExportPreviewService service) {
        this.service = service;
    }

    @GetMapping("/api/export-preview")
    ExportPreviewResponse preview(
            @Qualifier("invoice")
            @SortDefault(
                    sort = {"createdAt", "id"},
                    direction = Sort.Direction.DESC)
            Sort invoiceSort,

            @Qualifier("customer")
            @SortDefault(
                    sort = {"name", "id"},
                    direction = Sort.Direction.ASC)
            Sort customerSort) {

        return service.preview(invoiceSort, customerSort);
    }
}
```

Các lớp service và response tiếp tục là thành phần do ứng dụng định nghĩa. Request có thể là:

```http
GET /api/export-preview?invoice_sort=createdAt,desc&invoice_sort=id,desc&customer_sort=name,asc&customer_sort=id,asc
```

Các nhóm lúc này chỉ chứa tham số sắp xếp. Gửi `invoice_page` không khiến đối số `Sort` tự biến thành `Pageable`.

Nếu không có `@SortDefault` và không có sort từ request, cần xử lý khả năng `Sort` không có thứ tự chỉ định, thường được biểu diễn bằng `Sort.unsorted()`. Trạng thái này không bảo đảm cơ sở dữ liệu trả về theo thứ tự ổn định.

Dù nhiều `Sort` có cơ chế phân giải riêng, vẫn nên dùng các qualifier khác nhau để chúng đọc các nhóm độc lập. Không dựa vào tên biến Java để tạo ra sự phân biệt.

## 7. Kết hợp Pageable với Sort riêng

Có những request cần một danh sách phân trang và một cấu hình sắp xếp cho một tập dữ liệu khác:

```java
@GetMapping("/api/customer-overview")
CustomerOverviewResponse overview(
        @Qualifier("invoice")
        @PageableDefault(size = 20)
        Pageable invoicePage,

        @Qualifier("customer")
        @SortDefault(sort = "name")
        Sort customerSort) {

    return service.loadOverview(invoicePage, customerSort);
}
```

Đây là phần phương thức thuộc một controller đã có service và DTO thích hợp. Request:

```http
GET /api/customer-overview?invoice_page=1&invoice_size=20&invoice_sort=createdAt,desc&customer_sort=name,asc
```

Bốn tên tham số có ý nghĩa:

| Tên | Đích |
|---|---|
| `invoice_page` | Chỉ số trang của hóa đơn |
| `invoice_size` | Kích thước trang của hóa đơn |
| `invoice_sort` | `Sort` nằm bên trong `invoicePage` |
| `customer_sort` | Đối số `customerSort` độc lập |

Nếu đặt một `Pageable` và một `Sort` riêng cùng qualifier `invoice`, cả hai có thể đọc cùng `invoice_sort`. Điều đó không tạo hai cấu hình sắp xếp độc lập. Chỉ dùng cách này khi sự chia sẻ là một chủ đích đã được xác định; thông thường lấy `invoicePage.getSort()` là đủ cho chính danh sách hóa đơn.

## 8. Nhiều tiêu chí sort và giá trị mặc định

### 8.1. Lặp lại tên tham số để chỉ định thứ tự ưu tiên

Cú pháp rõ ràng cho nhiều tiêu chí:

```text
invoice_sort=createdAt,desc
invoice_sort=id,desc
```

Trong URL thực tế, hai cặp được nối bằng `&`. Thứ tự các tiêu chí có ý nghĩa: sắp xếp theo `createdAt` trước, dùng `id` để phân biệt khi thời điểm bằng nhau.

Với cú pháp mặc định, một biểu thức như `createdAt,id,desc` có thể diễn tả nhiều thuộc tính cùng chiều. Tuy nhiên, khi mỗi thuộc tính có chiều riêng, nên lặp lại tham số:

```text
invoice_sort=status,asc&invoice_sort=createdAt,desc&invoice_sort=id,desc
```

`invoice_sort[0]` hoặc `invoice.sort` không phải cách thay thế mặc định cho cú pháp trên.

### 8.2. Mặc định riêng cho từng đối số

`@PageableDefault` trên hóa đơn không làm thay đổi mặc định của yêu cầu hỗ trợ. Nếu cần các chiều mặc định khác nhau trên cùng đối số, có thể dùng `@SortDefault.SortDefaults`:

```java
@Qualifier("invoice")
@PageableDefault(size = 20)
@SortDefault.SortDefaults({
        @SortDefault(sort = "status", direction = Sort.Direction.ASC),
        @SortDefault(sort = {"createdAt", "id"},
                direction = Sort.Direction.DESC)
})
Pageable invoicePage
```

Đoạn này là khai báo đối số phương thức. `@PageableDefault` cung cấp phần phân trang; `@SortDefault` diễn đạt mặc định sắp xếp.

Mặc định là giá trị dự phòng, không phải quy tắc bắt buộc. Khi client cung cấp sort được resolver phân giải, không nên kỳ vọng tất cả tiêu chí mặc định vẫn tự được nối vào sort của client. Nếu `id` là điều kiện cần để phân trang ổn định, ứng dụng phải bảo đảm điều đó trong bước chuẩn hóa phía server.

## 9. Giới hạn và cách đánh số trang

Qualifier không thay đổi bản chất của `Pageable`. Với cấu hình mặc định thường gặp, chỉ số trang bắt đầu từ 0. Nếu ứng dụng đã bật `oneIndexedParameters`, cách biểu diễn số trang trên HTTP có thể bắt đầu từ 1, trong khi mô hình `Pageable` bên trong vẫn dùng chỉ số bắt đầu từ 0.

Ví dụ khi cấu hình nhận trang HTTP từ 1:

```text
invoice_page=1  → Pageable có pageNumber = 0
invoice_page=3  → Pageable có pageNumber = 2
```

Cần công bố rõ quy ước cho client; tránh để một bảng dùng số trang của giao diện còn bảng khác dùng chỉ số nội bộ rồi gửi trực tiếp cả hai.

Các giá trị như trang âm, size không hợp lệ hoặc size quá lớn được xử lý theo resolver và cấu hình đang dùng. Không giả định rằng mọi giá trị sai đều tự gây HTTP 400. Resolver có thể áp dụng fallback hoặc giới hạn giá trị. Nếu hợp đồng API yêu cầu từ chối rõ ràng, cần thiết kế bước kiểm tra tương ứng.

Có thể cấu hình giới hạn chung bằng customizer khi hạ tầng Spring Data Web của ứng dụng hỗ trợ và sử dụng các bean này:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.web.config.PageableHandlerMethodArgumentResolverCustomizer;

@Configuration
class PagingPolicyConfiguration {

    @Bean
    PageableHandlerMethodArgumentResolverCustomizer pagingPolicy() {
        return resolver -> {
            resolver.setMaxPageSize(100);
            resolver.setOneIndexedParameters(false);
        };
    }
}
```

`100` là giới hạn minh họa của ứng dụng, không phải giá trị mặc định được bảo đảm cho mọi phiên bản. Cấu hình này tác động đến các `Pageable` mà resolver quản lý, không chỉ một qualifier.

Giới hạn 100 cho mỗi nhóm cũng không giới hạn tổng chi phí của request ở mức 100 bản ghi. Hai nhóm có thể cùng yêu cầu 100 bản ghi, cộng thêm chi phí đếm và các truy vấn liên quan.

## 10. Khi thay đổi tên tham số hoặc dấu nối qualifier

Các ví dụ `invoice_page` và `invoice_sort` dựa trên tên tham số và dấu nối mặc định. Nếu ứng dụng đổi delimiter thành dấu chấm, cần đồng bộ bộ phân giải `Pageable` và bộ phân giải `Sort`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.web.config.PageableHandlerMethodArgumentResolverCustomizer;
import org.springframework.data.web.config.SortHandlerMethodArgumentResolverCustomizer;

@Configuration
class QualifiedParameterConfiguration {

    @Bean
    PageableHandlerMethodArgumentResolverCustomizer pageableNames() {
        return resolver -> resolver.setQualifierDelimiter(".");
    }

    @Bean
    SortHandlerMethodArgumentResolverCustomizer sortNames() {
        return resolver -> resolver.setQualifierDelimiter(".");
    }
}
```

Khi giữ nguyên các tên gốc `page`, `size`, `sort`, hợp đồng sẽ có dạng:

```http
GET /api/dashboard?invoice.page=2&invoice.size=20&invoice.sort=createdAt,desc&ticket.page=0&ticket.size=10&ticket.sort=priority,desc
```

Cấu hình trên là một phương án thay thế về quy ước tên. Không sao chép nhiều cấu hình customizer cùng loại vào ứng dụng rồi kỳ vọng chúng luôn được ghép theo ý muốn. Khi cần vừa đặt giới hạn vừa đổi delimiter, hãy tổng hợp các chính sách trong cấu hình có chủ đích.

Phần phân trang và phần sắp xếp có resolver liên quan nhưng riêng biệt. Chỉ thay delimiter cho `Pageable` có thể làm tên `page`/`size` và tên `sort` không còn thống nhất. Cần kiểm chứng hợp đồng HTTP đầy đủ sau khi tùy biến.

Đổi tên gốc bằng các API cấu hình như `setPageParameterName`, `setSizeParameterName`, `setSortParameter` cũng ảnh hưởng tên sau khi ghép qualifier. Dấu nối qualifier khác với dấu phân cách các thành phần trong một biểu thức sort.

## 11. Kiểm soát thuộc tính sort theo từng nhóm

Resolver biết cách tạo `Sort`, nhưng không tự biết thuộc tính nào nên được công khai trên API hóa đơn. Một query parameter hợp lệ về cú pháp có thể trỏ tới trường không tồn tại, đường dẫn không được hỗ trợ hoặc cột nhạy cảm.

Mỗi nhóm cần chính sách riêng:

| Nhóm | Khóa API có thể cho phép | Chính sách |
|---|---|---|
| `invoice` | `createdAt`, `total`, `id` | Ánh xạ đến thuộc tính của mô hình hóa đơn |
| `ticket` | `priority`, `openedAt`, `id` | Ánh xạ theo mô hình yêu cầu hỗ trợ |
| `customer` | `name`, `id` | Không tự dùng whitelist của hóa đơn |

Ví dụ chuẩn hóa nhóm hóa đơn, giả định repository dùng thuộc tính `amount` cho khóa API `total`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

final class InvoicePagingPolicy {

    private static final Map<String, String> SORT_PROPERTIES = Map.of(
            "createdAt", "createdAt",
            "total", "amount",
            "id", "id");

    static Pageable normalize(Pageable input) {
        if (input.isUnpaged()) {
            throw badRequest("Endpoint này yêu cầu phân trang");
        }

        List<Sort.Order> orders = new ArrayList<>();

        for (Sort.Order order : input.getSort()) {
            String property = SORT_PROPERTIES.get(order.getProperty());
            if (property == null) {
                throw badRequest("Thuộc tính sắp xếp hóa đơn không được hỗ trợ");
            }
            orders.add(order.withProperty(property));
        }

        if (orders.isEmpty()) {
            orders.add(Sort.Order.desc("createdAt"));
        }

        boolean hasId = orders.stream()
                .anyMatch(order -> order.getProperty().equals("id"));
        if (!hasId) {
            orders.add(Sort.Order.desc("id"));
        }

        return PageRequest.of(
                input.getPageNumber(),
                Math.min(input.getPageSize(), 100),
                Sort.by(orders));
    }

    private static ResponseStatusException badRequest(String reason) {
        return new ResponseStatusException(HttpStatus.BAD_REQUEST, reason);
    }
}
```

Hàm này minh họa ba quyết định: chỉ nhận khóa công khai đã cho phép, chuyển sang tên thuộc tính persistence, và bổ sung khóa duy nhất để phá hòa nếu client chưa chỉ định. Nó xử lý `Pageable` đã được resolver tạo, không kiểm tra lại nguyên văn mọi query parameter HTTP.

`order.withProperty(...)` giữ các đặc tính khác của order. Nếu API muốn hạn chế ignore-case, null handling hoặc tùy chọn khác, cần kiểm tra chúng theo khả năng module. Chỉ whitelist tên trường không làm mọi tùy chọn sắp xếp trở nên tương thích với mọi kho dữ liệu.

Không ghép trực tiếp các chuỗi sort của request vào SQL, JPQL hay một câu lệnh riêng của kho dữ liệu. Việc nhận `Sort` cần đi cùng API truy vấn phù hợp và chính sách thuộc tính được kiểm soát.

## 12. Chuyển đúng Pageable đến đúng repository

Một lỗi khó thấy là phân giải đúng nhưng truyền nhầm đối số ở service:

```java
// Sai về ý nghĩa: hai nhóm bị tráo cho nhau.
var invoices = invoiceRepository.findAll(ticketPage);
var tickets = ticketRepository.findAll(invoicePage);
```

Cú pháp vẫn có thể biên dịch vì cả hai đều là `Pageable`. Cách đặt tên và phân tách chính sách giúp giảm nhầm lẫn:

```java
var safeInvoicePage = InvoicePagingPolicy.normalize(invoicePage);
var safeTicketPage = ticketPagingPolicy.normalize(ticketPage);

var invoices = invoiceRepository.findAll(safeInvoicePage);
var tickets = ticketRepository.findAll(safeTicketPage);
```

Đoạn mã giả định repository cung cấp phương thức phân trang tương ứng. Không suy ra rằng mọi module đều hỗ trợ `Page`, mọi kiểu projection hoặc mọi đường dẫn sort giống nhau chỉ vì cùng nhận abstraction của Spring Data Commons.

Nếu truy vấn cần điều kiện nghiệp vụ, hãy dùng phương thức repository, fragment hoặc truy vấn của module phù hợp. Qualifier không tự thêm điều kiện tenant, trạng thái hay quyền truy cập.

Với ứng dụng nhiều tenant, cả hai truy vấn đều phải nhận phạm vi tenant từ nguồn danh tính được ứng dụng xác định. `@Qualifier("invoice")` chỉ định danh nhóm tham số; nó không xác thực người dùng, không chọn tenant và không bảo đảm hai danh sách đã được lọc quyền giống nhau.

Nếu repository trả `Page`, tổng số phần tử có thể đòi hỏi công việc đếm bổ sung tùy cách module thực hiện truy vấn. Hai vùng dữ liệu độc lập có thể tạo nhiều truy vấn hơn số vùng hiển thị. Khi không cần tổng số, cân nhắc hợp đồng `Slice` hoặc cách đọc khác mà module hỗ trợ.

## 13. Tính ổn định và nhất quán của hai vùng dữ liệu

Hai `Pageable` chỉ tạo hai mô tả phân trang. Chúng không tạo một snapshot chung cho toàn bộ dashboard.

Nếu hai truy vấn chạy ở những thời điểm khác nhau, một hóa đơn hoặc yêu cầu hỗ trợ có thể được thêm vào giữa hai lần đọc. Nhu cầu snapshot nhất quán phải được xử lý bằng transaction, isolation hoặc cơ chế đọc thích hợp với kho dữ liệu và yêu cầu nghiệp vụ.

Trong từng nhóm, khóa phá hòa như `id` giúp thứ tự xác định hơn khi nhiều bản ghi có cùng `createdAt` hay `priority`. Tuy nhiên, offset pagination vẫn có thể bị dịch chuyển khi dữ liệu thay đổi giữa các request. Bổ sung `id` không biến nó thành cơ chế snapshot hoặc keyset scrolling.

Nếu sau này chuyển một nhóm sang scrolling hoặc cursor, cần thiết kế hợp đồng mới cho nhóm đó. Không giả định rằng prefix `invoice_` tự làm `Pageable` hiểu một cursor bất kỳ.

## 14. Client cần giữ trạng thái riêng cho từng nhóm

Một request mẫu khi chỉ đổi trang hóa đơn:

```text
Trước:
invoice_page=0&invoice_size=20&ticket_page=2&ticket_size=10

Sau:
invoice_page=1&invoice_size=20&ticket_page=2&ticket_size=10
```

Nếu client dựng lại URL và vô tình bỏ `ticket_page`, nhóm ticket có thể quay về trang mặc định. Đây là lỗi quản lý trạng thái phía client, dù resolver phía server vẫn hoạt động đúng.

Client nên duy trì mỗi nhóm với các thành phần độc lập:

```text
invoice: page, size, sort[]
ticket:  page, size, sort[]
```

Khi đổi bộ lọc hoặc kích thước trang của một nhóm, thường cần đưa số trang của chính nhóm ấy về trang đầu theo hợp đồng đã chọn. Không tự reset mọi nhóm nếu nghiệp vụ không yêu cầu.

Khi tạo URL, cần bảo toàn các lần lặp của cùng khóa sort. Một cấu trúc map chỉ giữ một giá trị cho mỗi tên có thể làm mất tiêu chí `id` khi thêm tiêu chí `createdAt`. Dùng cơ chế query parameter hỗ trợ nhiều giá trị thay vì nối chuỗi thiếu kiểm soát.

## 15. Những tình huống cần kiểm tra khi tích hợp

Bảng dưới mô tả các tình huống kiểm chứng hợp đồng, không yêu cầu viết thêm file cho bài học:

| Tình huống | Kết quả cần quan sát |
|---|---|
| Không gửi query parameter | Mỗi nhóm nhận mặc định của chính nó |
| Chỉ gửi `invoice_page` và `invoice_size` | Ticket không đổi sang cấu hình hóa đơn |
| Gửi đầy đủ cả hai nhóm | Hai đối số có số trang, size và sort đúng riêng |
| Gửi `page` không qualifier | Không tự điều khiển nhóm đã định danh |
| Gửi lặp lại `invoice_sort` | Bảo toàn thứ tự các tiêu chí |
| Gửi trường sort ngoài whitelist | Nhận phản hồi theo chính sách từ chối của ứng dụng |
| Gửi size vượt giới hạn | Quan sát giới hạn hiệu lực hoặc cơ chế từ chối đã thiết kế |
| Đổi sang delimiter dấu chấm | Cả phân trang lẫn sort đọc đúng tên mới |
| Đổi `oneIndexedParameters` | HTTP và chỉ số nội bộ được chuyển đổi như hợp đồng |
| Hai `Pageable` thiếu hoặc trùng qualifier | Phát hiện cấu hình đối số mơ hồ |
| Truy vấn hai tenant khác nhau | Mọi nhóm đều giữ đúng phạm vi truy cập |

Khi chẩn đoán, nên quan sát giá trị đã phân giải ở ranh giới controller/service, rồi mới đối chiếu với query của module. Nếu `invoicePage` đã đúng nhưng kết quả hóa đơn sai, nguyên nhân có thể nằm ở bước chuẩn hóa, truyền nhầm đối số hoặc truy vấn repository.

## 16. Bài tập tự kiểm tra

### Tình huống 1: Hai Pageable nhưng chỉ một @Qualifier

Controller khai báo `@Qualifier("invoice") Pageable invoicePage` và một `Pageable ticketPage` không qualifier.

**Phân tích:** tên biến Java không cung cấp namespace thay thế. Khi có nhiều `Pageable`, cần qualifier rõ ràng và riêng biệt cho tất cả đối số, chẳng hạn `invoice` và `ticket`.

### Tình huống 2: Gửi sort không có prefix

Client gọi `/api/dashboard?sort=createdAt,desc`, nhưng controller dùng hai qualifier `invoice` và `ticket`.

**Phân tích:** tham số đó không nhắm đến `invoice_sort` hoặc `ticket_sort` theo cấu hình mặc định. Hai nhóm có thể tiếp tục dùng sắp xếp mặc định; không được kết luận rằng resolver đã áp dụng sort cho cả hai.

### Tình huống 3: Muốn hai thứ tự riêng nhưng dùng cùng qualifier

Một đối số `Pageable` và một đối số `Sort` đều được gắn `@Qualifier("invoice")`.

**Phân tích:** cả hai cùng hướng đến nhóm sort của hóa đơn. Nếu muốn hai thứ tự độc lập, hãy dùng hai nhóm khác nhau; nếu cùng danh sách, thường chỉ cần `Pageable.getSort()`.

### Tình huống 4: Client thay sort và mất khóa id

Controller có mặc định `createdAt DESC, id DESC`; client chỉ gửi `invoice_sort=total,asc`.

**Phân tích:** không coi mặc định là danh sách tiêu chí luôn được nối vào yêu cầu của client. Chính sách server cần bổ sung khóa phá hòa nếu hợp đồng yêu cầu thứ tự xác định.

### Tình huống 5: Một nhóm có size 100, nhóm còn lại cũng có size 100

Ứng dụng đã đặt giới hạn kích thước trang là 100 và cho rằng một request chỉ có thể đọc tối đa 100 phần tử.

**Phân tích:** giới hạn áp dụng cho từng `Pageable`. Tổng số phần tử, công việc đếm và chi phí truy vấn của cả request cần có ngân sách riêng.

### Tình huống 6: Đổi delimiter của Pageable nhưng quên Sort

Ứng dụng muốn nhận `invoice.page` và `invoice.sort`, nhưng chỉ tùy biến resolver phân trang.

**Phân tích:** cần kiểm tra cấu hình resolver sort tương ứng. Tên phân trang và tên sắp xếp có thể không được đổi đồng bộ chỉ bằng một lời gọi cấu hình trên resolver của `Pageable`.

Dùng `@Qualifier` hiệu quả cần giữ ba ánh xạ rõ ràng: nhóm tên trên HTTP, đối số controller và truy vấn nghiệp vụ tương ứng. Mỗi nhóm có mặc định, giới hạn và chính sách sort riêng; quyền truy cập, tính nhất quán và khả năng kho dữ liệu vẫn phải được bảo đảm ở các lớp thích hợp.
