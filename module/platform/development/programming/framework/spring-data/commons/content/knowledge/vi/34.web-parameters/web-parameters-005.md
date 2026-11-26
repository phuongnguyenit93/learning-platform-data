# Giới hạn page size, quy ước chỉ số trang và tham số không hợp lệ

## 1. Mục tiêu của bài học

Trong chương **Tham số web** của module **Spring Data Commons**, các tham số như `page` và `size` là đầu vào để tạo một `Pageable`. Chúng quyết định phần dữ liệu được yêu cầu, đồng thời ảnh hưởng trực tiếp đến chi phí truy vấn và hợp đồng HTTP của ứng dụng.

Sau bài này, bạn cần có khả năng:

- Đặt kích thước trang mặc định và giới hạn tối đa một cách tường minh.
- Phân biệt số trang client gửi với chỉ số trang nội bộ.
- Giải thích vì sao một tham số sai không nhất thiết tạo HTTP 400.
- Chọn giữa chuẩn hóa đầu vào và từ chối đầu vào không hợp lệ.
- Kiểm tra giới hạn trước khi tạo `PageRequest` và trước khi gọi tầng dữ liệu.
- Giữ metadata phản hồi nhất quán với trang thực sự đã thực thi.

Spring Data Commons cung cấp các abstraction như `Pageable`, `PageRequest`, `Page`, `Slice` và hạ tầng tích hợp web. Khả năng thực thi truy vấn, phân trang hiệu quả và truy vấn đếm vẫn thuộc mô-đun lưu trữ cụ thể. Việc một controller nhận được `Pageable` không bảo đảm mọi store đều hỗ trợ mọi hình thức phân trang.

Các ví dụ web dưới đây dùng **Spring MVC**, tích hợp Spring Data Web và Java 17 trở lên. Ví dụ cấu hình bằng properties giả định Spring Boot đang tự cấu hình tích hợp này.

## 2. Xác định hợp đồng trước khi cấu hình

Giả sử API tìm sách chọn chính sách:

| Quy tắc | Giá trị của ví dụ |
| --- | --- |
| Tham số trang | `page` |
| Tham số kích thước | `size` |
| Quy ước chỉ số trang | Bắt đầu từ 0 |
| Trang mặc định | 0 |
| Kích thước mặc định | 20 |
| Kích thước tối đa | 100 |
| Thứ tự mặc định | `id` tăng dần |

Khi đó:

~~~http
GET /books
GET /books?page=0&size=20
GET /books?page=2&size=20
~~~

Hai request đầu yêu cầu cùng một cửa sổ dữ liệu. Request thứ ba yêu cầu cửa sổ bắt đầu ở offset 40.

Tuy nhiên, bảng trên chưa trả lời câu hỏi: nếu client gửi `size=1000`, server sẽ cắt xuống 100 hay trả lỗi? Cũng chưa xác định `size=abc` sẽ dùng mặc định hay bị từ chối. Đây là các quyết định phải được ghi vào hợp đồng API.

Không dùng từ “có giới hạn” để ngầm đồng nghĩa với “mọi đầu vào vượt giới hạn đều bị từ chối”.

## 3. Pageable bên trong luôn dùng chỉ số trang bắt đầu từ 0

Với một `PageRequest`:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;

Pageable first = PageRequest.of(0, 20);
Pageable third = PageRequest.of(2, 20);

long firstOffset = first.getOffset(); // 0
long thirdOffset = third.getOffset(); // 40
~~~

Các ràng buộc cơ bản khi tạo `PageRequest` là:

- Chỉ số trang không âm.
- Kích thước trang lớn hơn 0.

~~~java
PageRequest.of(-1, 20); // IllegalArgumentException
PageRequest.of(0, 0);   // IllegalArgumentException
~~~

Hai ràng buộc này chưa tạo một chính sách bảo vệ tài nguyên. Một kích thước rất lớn nhưng vẫn là số nguyên dương có thể được truyền vào `PageRequest.of`. Giới hạn tối đa phải do cấu hình hoặc logic ứng dụng áp dụng.

Offset của kiểu phân trang này được tính theo:

~~~text
offset = pageNumber × pageSize
~~~

Khi tự tính offset, cần nhân theo kiểu `long`:

~~~java
long offset = (long) pageNumber * pageSize;
~~~

Nếu dùng hai biến `int` trong phép nhân rồi mới gán vào `long`, phép nhân có thể đã tràn trước thời điểm gán.

Không dùng `size=0` hay `size=-1` như một lối tắt lấy toàn bộ dữ liệu. Nếu nghiệp vụ cần xuất toàn bộ kết quả, hãy thiết kế luồng xuất dữ liệu có cơ chế giới hạn tài nguyên riêng.

## 4. Cấu hình giới hạn và mặc định qua Spring Boot

Với ứng dụng Spring Boot đang sử dụng auto-configuration cho Spring Data Web, có thể khai báo:

~~~yaml
spring:
  data:
    web:
      pageable:
        page-parameter: page
        size-parameter: size
        default-page-size: 20
        max-page-size: 100
        one-indexed-parameters: false
~~~

Cấu hình này chọn rõ hợp đồng thay vì để ứng dụng phụ thuộc vào giá trị mặc định mà người đọc phải tự nhớ.

Ý nghĩa của hai thuộc tính dễ bị nhầm:

| Thuộc tính | Vai trò |
| --- | --- |
| `default-page-size` | Kích thước được dùng khi cần giá trị mặc định |
| `max-page-size` | Trần kích thước resolver cho phép tạo từ tham số web |

Kích thước mặc định nên nằm trong giới hạn tối đa. Tránh cấu hình mặc định lớn hơn trần rồi để hành vi cắt giảm trở thành điều bất ngờ.

Các properties này điều khiển đường phân giải tham số web tương ứng; chúng không tạo một giới hạn toàn cục cho mọi lời gọi `PageRequest.of` trong code.

Ví dụ, một tác vụ nội bộ vẫn cần kiểm soát đầu vào riêng nếu tự làm:

~~~java
PageRequest.of(0, requestedBatchSize);
~~~

Nếu ứng dụng chủ động thay thế hạ tầng Spring Data Web hoặc bật cấu hình thủ công, không mặc định rằng toàn bộ properties của Boot vẫn được áp dụng. Cần xác nhận resolver thực sự được đăng ký trong ứng dụng.

## 5. Tùy biến resolver bằng code

Trong ứng dụng có hỗ trợ bean customizer của Spring Data Web, có thể dùng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.web.config
    .PageableHandlerMethodArgumentResolverCustomizer;

@Configuration
class PagingWebConfiguration {

    @Bean
    PageableHandlerMethodArgumentResolverCustomizer pagingCustomizer() {
        return resolver -> {
            resolver.setPageParameterName("page");
            resolver.setSizeParameterName("size");
            resolver.setOneIndexedParameters(false);
            resolver.setFallbackPageable(PageRequest.of(0, 20));
            resolver.setMaxPageSize(100);
        };
    }
}
~~~

Đây là cách biểu diễn chính sách tương đương bằng code khi hạ tầng đang dùng áp dụng customizer đó. Không cần sao chép đồng thời cả cách này và properties cho cùng một mục đích.

Nếu dự án tự tạo resolver và đăng ký nó bằng cấu hình MVC riêng, phải áp dụng chính sách lên chính instance được đăng ký. Chỉ khai báo một bean có tên gợi ý “paging configuration” không chứng minh request đã đi qua resolver đó.

`setMaxPageSize(100)` giới hạn kích thước được phân giải. Nó không yêu cầu resolver trả HTTP 400 cho `size=101`. Đường xử lý thông thường của resolver là chuẩn hóa kích thước xuống trần.

## 6. Mặc định tại từng endpoint với @PageableDefault

Một endpoint có thể khai báo mặc định riêng:

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/books")
class BookController {

    private final BookSearchService service;

    BookController(BookSearchService service) {
        this.service = service;
    }

    @GetMapping
    PageEnvelope<BookSummary> list(
            @PageableDefault(size = 20, sort = "id") Pageable pageable) {

        return PageEnvelope.from(service.find(pageable));
    }
}
~~~

`@PageableDefault` cung cấp giá trị mặc định cho tham số endpoint. Nó không định nghĩa một page size tối đa dành riêng cho endpoint đó.

Client vẫn có thể yêu cầu một kích thước khác nằm trong chính sách resolver:

~~~http
GET /books?size=50
~~~

Không dùng `@PageableDefault(size = 20)` với kỳ vọng mọi request đều có size 20.

Nếu có nhiều nguồn cấu hình, cần phân biệt:

- Mặc định toàn cục của resolver.
- Mặc định gắn với tham số controller.
- Giá trị client gửi.
- Trần kích thước cuối cùng mà resolver áp dụng.

Một mặc định khác 20 tại endpoint sẽ làm các ví dụ fallback tương ứng thay đổi. Khi kiểm tra, phải dùng đúng annotation và resolver của endpoint đó.

## 7. Resolver chuẩn thường dung thứ tham số không hợp lệ

Hãy xét endpoint ở trên với trang mặc định 0, size mặc định 20, trần 100 và chỉ số đầu vào bắt đầu từ 0.

Với resolver Spring MVC chuẩn của Spring Data Web theo đường xử lý thông thường, những tình huống sau không tự trở thành HTTP 400 chỉ vì chúng xuất hiện:

| Query | Pageable thường được phân giải |
| --- | --- |
| Không có `page`, `size` | `page=0, size=20` |
| `page=2&size=50` | `page=2, size=50` |
| `page=-3&size=20` | Trang được đưa về 0 |
| `page=abc&size=20` | Trang được đưa về 0 |
| `page=0&size=0` | Size quay về giá trị mặc định 20 |
| `page=0&size=-5` | Size quay về giá trị mặc định 20 |
| `page=0&size=abc` | Size quay về giá trị mặc định 20 |
| `page=0&size=101` | Size bị giới hạn thành 100 |

Bảng mô tả chính sách dung thứ của resolver, không phải một cam kết rằng mọi request cuối cùng đều thành công. Authorization, điều kiện nghiệp vụ hoặc truy vấn store vẫn có thể tạo lỗi riêng.

Một chuỗi số vượt miền `int` cũng không nên được coi đơn giản là “một số rất lớn sẽ luôn bị cắt về trần”. Bước chuyển chuỗi thành số có thể thất bại trước khi áp dụng trần và đi vào nhánh fallback của resolver.

Hành vi còn phụ thuộc resolver, annotation và cấu hình thực tế của phiên bản ứng dụng. Khi hợp đồng HTTP cần chính xác, hãy kiểm tra ở tầng MVC thay vì suy luận từ tên properties.

Đặt:

~~~java
PageRequest.of(-3, 20);
~~~

sẽ ném exception, trong khi request `?page=-3` đi qua resolver có thể được chuẩn hóa trước khi tạo `PageRequest`. Đây là hai đường đi khác nhau.

## 8. Khi cần HTTP 400, phải kiểm tra đầu vào trước khi nó bị chuẩn hóa

Một API quản trị có thể chấp nhận fallback. Một API công khai yêu cầu client gửi đúng hợp đồng có thể chọn từ chối:

- Giá trị không phải số nguyên thập phân.
- `page < 0`.
- `size < 1` hoặc `size > 100`.
- Tham số xuất hiện nhiều lần.
- Trang quá sâu hoặc offset vượt giới hạn.
- Tham số không thuộc hợp đồng endpoint.

Không thể phục hồi chính xác chuỗi gốc từ một `Pageable` đã được chuẩn hóa. Ví dụ, cả `size=abc` và việc không gửi size đều có thể dẫn đến size 20.

Do đó, nếu muốn phân biệt hai request này, cần kiểm tra raw query parameters trước hoặc dùng một argument resolver riêng có hợp đồng nghiêm ngặt.

Đặt `@Valid` lên `Pageable` không tự tạo tất cả những kiểm tra đó. Validation bean cũng không tự biết kích thước 20 đến từ client hay từ fallback.

## 9. Ví dụ parser nghiêm ngặt cho page và size

Ví dụ sau chọn hợp đồng riêng cho endpoint `/strict-books`:

| Quy tắc | Chính sách |
| --- | --- |
| Chỉ số trang | Bắt đầu từ 0 |
| Thiếu page | Dùng 0 |
| Thiếu size | Dùng 20 |
| Miền page | Từ 0 đến 10.000 |
| Miền size | Từ 1 đến 100 |
| Offset tối đa | 100.000 |
| Cú pháp số | Chỉ chữ số ASCII, không dấu, không khoảng trắng |
| Tham số lặp | Từ chối |
| Tham số khác | Từ chối |
| Sorting | Cố định theo `id` tăng dần |

Giới hạn page và offset ở đây là lựa chọn minh họa của ứng dụng, không phải giới hạn mặc định do Spring Data áp đặt.

~~~java
import java.util.List;
import java.util.Set;

import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.util.MultiValueMap;
import org.springframework.web.server.ResponseStatusException;

final class StrictPaging {

    private static final int DEFAULT_SIZE = 20;
    private static final int MAX_SIZE = 100;
    private static final int MAX_PAGE = 10_000;
    private static final long MAX_OFFSET = 100_000L;

    private static final Set<String> ALLOWED_PARAMETERS =
            Set.of("page", "size");

    private StrictPaging() {
    }

    static Pageable parse(MultiValueMap<String, String> parameters) {
        for (String name : parameters.keySet()) {
            if (!ALLOWED_PARAMETERS.contains(name)) {
                throw badRequest("Tham số không được hỗ trợ: " + name);
            }
        }

        int page = parseUnsignedInt(
                "page", single(parameters, "page"), 0);
        int size = parseUnsignedInt(
                "size", single(parameters, "size"), DEFAULT_SIZE);

        if (page > MAX_PAGE) {
            throw badRequest("page phải nằm trong khoảng 0..10000");
        }

        if (size < 1 || size > MAX_SIZE) {
            throw badRequest("size phải nằm trong khoảng 1..100");
        }

        long offset = (long) page * size;
        if (offset > MAX_OFFSET) {
            throw badRequest("Offset yêu cầu vượt giới hạn cho phép");
        }

        return PageRequest.of(
                page, size, Sort.by("id").ascending());
    }

    private static String single(
            MultiValueMap<String, String> parameters, String name) {

        List<String> values = parameters.get(name);
        if (values == null) {
            return null;
        }

        if (values.size() != 1 || values.get(0) == null) {
            throw badRequest(
                    "Tham số " + name + " phải xuất hiện đúng một lần");
        }

        return values.get(0);
    }

    private static int parseUnsignedInt(
            String name, String raw, int fallback) {

        if (raw == null) {
            return fallback;
        }

        if (!raw.matches("[0-9]+")) {
            throw badRequest(
                    "Tham số " + name + " phải là số nguyên không âm");
        }

        try {
            return Integer.parseInt(raw);
        } catch (NumberFormatException exception) {
            throw badRequest(
                    "Tham số " + name + " vượt miền số nguyên hỗ trợ");
        }
    }

    private static ResponseStatusException badRequest(String message) {
        return new ResponseStatusException(
                HttpStatus.BAD_REQUEST, message);
    }
}
~~~

Parser không âm thầm trim chuỗi và không nhận `+1`. Đây là quyết định về cú pháp HTTP của ví dụ. Một hợp đồng khác có thể cho phép các dạng đó, nhưng cần thực hiện và kiểm tra nhất quán.

Chữ số 0 đứng đầu vẫn được chấp nhận nếu cả chuỗi chuyển đổi được thành `int`. Không quảng bá đây là một parser chỉ chấp nhận biểu diễn số theo một dạng duy nhất.

Nhánh kiểm tra cú pháp và nhánh kiểm tra miền số có vai trò khác nhau. Một chuỗi chỉ gồm chữ số vẫn có thể quá lớn để chuyển thành `int`.

### 9.1. Controller dùng parser

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.util.MultiValueMap;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class StrictBookController {

    private final BookSearchService service;

    StrictBookController(BookSearchService service) {
        this.service = service;
    }

    @GetMapping("/strict-books")
    PageEnvelope<BookSummary> list(
            @RequestParam MultiValueMap<String, String> parameters) {

        Pageable pageable = StrictPaging.parse(parameters);
        return PageEnvelope.from(service.find(pageable));
    }
}
~~~

Dùng `MultiValueMap` giữ được các giá trị lặp của cùng một query parameter để kiểm tra:

~~~http
GET /strict-books?page=0&page=1
~~~

Một `Map<String, String>` chỉ biểu diễn một giá trị cho mỗi key, nên không phù hợp nếu hợp đồng cần phát hiện chắc chắn trường hợp này ở bước xử lý đó.

Endpoint nghiêm ngặt trong ví dụ chỉ hỗ trợ page và size; nó chủ động không nhận sort hoặc bộ lọc khác. Nếu mở rộng tìm kiếm, cần cập nhật danh sách tham số và validation của từng tham số, không xóa toàn bộ kiểm tra chỉ để “cho request đi qua”.

### 9.2. Dịch vụ truy vấn và metadata phản hồi

Các kiểu hỗ trợ cho hai controller:

~~~java
import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

record BookSummary(Long id, String title) {
}

interface BookSearchService {
    Page<BookSummary> find(Pageable pageable);
}

record PageEnvelope<T>(
        List<T> content,
        int page,
        int size,
        int numberOfElements,
        boolean hasNext,
        long totalElements) {

    static <T> PageEnvelope<T> from(Page<T> result) {
        return new PageEnvelope<>(
                result.getContent(),
                result.getNumber(),
                result.getSize(),
                result.getNumberOfElements(),
                result.hasNext(),
                result.getTotalElements());
    }
}
~~~

`BookSearchService` là hợp đồng ứng dụng trong bài. Implementation cần chọn repository hoặc template mà mô-đun lưu trữ thực sự hỗ trợ; đây không phải một service có sẵn của Spring Data Commons.

Envelope chọn rõ các trường HTTP, thay vì làm hợp đồng phản hồi phụ thuộc trực tiếp vào cách một implementation của `Page` được serialize.

`size` là kích thước trang của kết quả, còn `numberOfElements` là số phần tử thực sự có trong trang đó. Ở trang cuối, hai giá trị thường khác nhau.

Không lấy nguyên chuỗi `size` client gửi để trả vào metadata sau khi resolver đã cắt giảm. Ví dụ, request size 1000 bị chuẩn hóa thành 100 phải phản ánh size hiệu lực tương ứng.

Ví dụ dùng `Page` nên dịch vụ phải cung cấp được thông tin tổng số theo hợp đồng. Nếu không cần tổng và store hỗ trợ đường truy vấn phù hợp, có thể chọn `Slice` rồi thiết kế envelope tương ứng; khi đó không tự bịa `totalElements`.

## 10. Chỉ số đầu vào bắt đầu từ 1 là một phép chuyển đổi ở biên web

Một API có thể chọn cách client gửi:

~~~http
GET /books?page=1&size=20
~~~

để chỉ trang đầu tiên. Với resolver chuẩn, cấu hình tương ứng là:

~~~yaml
spring:
  data:
    web:
      pageable:
        one-indexed-parameters: true
~~~

Bảng chuyển đổi của hợp đồng đó:

| Client gửi | Chỉ số trong Pageable | Offset nếu size 20 |
| --- | --- | --- |
| `page=1` | 0 | 0 |
| `page=2` | 1 | 20 |
| `page=3` | 2 | 40 |

Thuộc tính này không biến `PageRequest` thành kiểu bắt đầu từ 1. Không trừ 1 lần nữa trong service sau khi resolver đã chuyển đổi.

Tương tự, `Page.getNumber()` vẫn phản ánh chỉ số nội bộ. Nếu phản hồi HTTP được thiết kế cũng bắt đầu từ 1, hãy chuyển đổi ở lớp DTO:

~~~java
long externalPage = (long) result.getNumber() + 1L;
~~~

Việc dùng `long` trong phép cộng tránh phụ thuộc vào phép cộng `int` ở ranh giới lớn. API vẫn nên giới hạn độ sâu trang theo nhu cầu thực tế.

Nếu dùng parser nghiêm ngặt thay vì resolver, phải tự kiểm tra `externalPage >= 1` rồi chuyển đổi đúng một lần trước khi tạo `PageRequest`. Không bật properties rồi kỳ vọng chúng thay đổi logic của parser tự viết.

Một resolver dung thứ có thể đưa các giá trị quá thấp về trang đầu. Vì vậy, bật chế độ bắt đầu từ 1 chưa đủ để bảo đảm `page=0` bị trả HTTP 400.

Cần thống nhất cùng quy ước tại request, response, liên kết điều hướng, giao diện và tài liệu API.

## 11. Giới hạn size không giải quyết toàn bộ chi phí phân trang

Request sau chỉ yêu cầu 20 phần tử:

~~~http
GET /books?page=500000&size=20
~~~

Nhưng với phân trang dựa trên offset, store có thể phải xử lý một khoảng dữ liệu rất sâu trước khi trả kết quả.

Các giới hạn bổ sung có thể cần thiết:

- Trần page hoặc offset phù hợp với nghiệp vụ.
- Bộ lọc có chọn lọc và chỉ mục thích hợp của store.
- Danh sách thuộc tính sort được cho phép.
- Giới hạn thời gian truy vấn và khả năng sử dụng endpoint.
- Cách lấy tổng số khi API yêu cầu `Page`.
- API cuộn hoặc cursor nếu mô-đun và mô hình dữ liệu hỗ trợ.

Các lựa chọn này cần được đánh giá theo store. Không khẳng định mọi repository đều có keyset pagination chỉ vì Commons có abstraction liên quan đến scrolling.

Một thứ tự ổn định giúp cửa sổ dữ liệu có ý nghĩa. Ví dụ, sort theo title nên cân nhắc thêm id làm tiêu chí phân biệt khi title trùng nhau. Điều đó vẫn không tạo một snapshot cố định nếu dữ liệu thay đổi giữa hai request.

Giới hạn đầu vào ở HTTP cũng không thay thế ràng buộc tại tầng ứng dụng nếu dịch vụ được gọi từ nhiều đường khác như tác vụ nền hoặc một API khác.

## 12. Phân biệt trang không có dữ liệu với tham số không hợp lệ

Hai request có thể cần cách xử lý khác nhau:

~~~http
GET /books?page=3&size=20
GET /books?page=abc&size=20
~~~

Nếu page 3 hợp lệ nhưng chưa có dữ liệu trong cửa sổ đó, API thường có thể trả một trang rỗng theo hợp đồng. Đây không tự động là lỗi cú pháp.

Nếu API chọn parser nghiêm ngặt, `page=abc` là HTTP 400 trước khi gọi dịch vụ.

Không dùng số lượng kết quả trả về để kết luận tham số đúng hay sai. Ngược lại, không áp dụng HTTP 404 cho mọi trang rỗng nếu hợp đồng của API chưa quy định như vậy.

Nếu cần một định dạng lỗi ổn định, hãy chuẩn hóa bằng cơ chế xử lý exception của ứng dụng. `ResponseStatusException` trong ví dụ xác lập mã trạng thái; hình dạng body và việc công khai reason còn phụ thuộc cấu hình xử lý lỗi. Không yêu cầu client dựa vào một chuỗi thông báo tự do chưa được cam kết.

## 13. Ma trận kiểm tra cần có

Với endpoint dung thứ, kiểm tra `Pageable` thực sự được truyền vào service. Chỉ kiểm tra HTTP 200 không chứng minh size đã bị giới hạn.

| Đầu vào | Điều cần xác minh với cấu hình của ví dụ |
| --- | --- |
| Không có tham số | Page 0, size 20 |
| `page=2&size=50` | Page 2, size 50, offset 100 |
| `size=101` | Size hiệu lực bằng 100 |
| `size=0`, `size=-1`, `size=abc` | Fallback đúng chính sách resolver |
| `page=-1`, `page=abc` | Không suy đoán HTTP 400; xác minh page hiệu lực |
| Trang cuối chỉ có vài phần tử | Size khác numberOfElements một cách hợp lệ |
| Chế độ đầu vào bắt đầu từ 1 | Client page 1 thành Pageable page 0 |

Với endpoint `/strict-books`:

| Đầu vào | Kết quả kỳ vọng |
| --- | --- |
| Không có tham số | Page 0, size 20 |
| `page=2&size=50` | Chấp nhận |
| `size=100` | Chấp nhận |
| `size=101` | HTTP 400 |
| `size=0` | HTTP 400 |
| `page=-1` | HTTP 400 |
| `page=abc` | HTTP 400 |
| `page=` | HTTP 400 |
| `page=2147483648` | HTTP 400 vì vượt miền int |
| `page=10001&size=1` | HTTP 400 vì vượt trần page |
| `page=2000&size=100` | HTTP 400 vì offset 200.000 |
| `page=0&page=1` | HTTP 400 vì tham số lặp |
| `limit=20` | HTTP 400 vì tham số ngoài hợp đồng |
| Trang hợp lệ nhưng không có kết quả | Phản hồi trang rỗng theo hợp đồng |

Một kiểm tra MVC cho nhánh từ chối có hình dạng:

~~~java
mockMvc.perform(get("/strict-books")
        .param("size", "101"))
    .andExpect(status().isBadRequest());

verifyNoInteractions(service);
~~~

Snippet giả định test đã tạo controller, MockMvc và mock `service`, cùng các static import từ thư viện kiểm tra tương ứng. Đây là minh họa cách chứng minh lỗi bị chặn trước truy vấn; không phải toàn bộ test class.

Khi kiểm tra resolver tự động, cần dùng cấu hình MVC có đăng ký đúng Spring Data argument resolver. Một test standalone thiếu resolver có thể không đại diện cho ứng dụng thật.

Kiểm tra parser chứng minh quy tắc chuyển đổi; kiểm tra MVC chứng minh đường HTTP dùng quy tắc đó; kiểm tra tích hợp store chứng minh truy vấn hỗ trợ đúng `Pageable`. Không dùng một loại kiểm tra để suy ra mọi lớp còn lại.

## 14. Lỗi thường gặp

| Cách làm | Hệ quả | Hướng xử lý |
| --- | --- | --- |
| Chỉ đặt default size | Client vẫn yêu cầu size lớn hơn | Đặt trần hoặc validation rõ ràng |
| Nghĩ max size đồng nghĩa HTTP 400 | Client nhận thành công với size bị cắt | Ghi rõ chính sách chuẩn hóa hoặc viết validation nghiêm ngặt |
| Validate sau khi chỉ còn Pageable | Mất dấu chuỗi sai ban đầu | Kiểm tra query gốc trước chuẩn hóa |
| Trừ 1 ở cả resolver và service | Lấy sai trang | Chuyển đổi chỉ số đúng một lần |
| Trả chỉ số nội bộ cho API cam kết bắt đầu từ 1 | Request và response không thống nhất | Chuyển đổi ở DTO biên web |
| Coi size 0 hoặc -1 là lấy hết | Chính sách không rõ hoặc lỗi tạo PageRequest | Thiết kế luồng xuất dữ liệu riêng |
| Nhân page và size bằng int | Có thể tràn số | Chuyển sang long trước phép nhân |
| Giới hạn size nhưng cho page rất sâu | Truy vấn vẫn tốn kém | Cân nhắc trần offset và API cuộn phù hợp |
| Dùng Map một giá trị để phát hiện query lặp | Không giữ đầy đủ đầu vào | Dùng MultiValueMap hoặc request API tương đương |
| Trả nguyên size client gửi | Metadata không phản ánh giới hạn đã áp dụng | Trả thông tin từ kết quả hiệu lực |

## 15. Bài thực hành

1. Chọn một endpoint tìm sách của ứng dụng và mô tả rõ page, size, quy ước chỉ số cùng thứ tự mặc định.
2. Cấu hình size mặc định 20 và trần 100 trên resolver thực sự được ứng dụng dùng.
3. Quan sát size hiệu lực khi gửi 101, 0, chuỗi rỗng và một chuỗi không phải số.
4. Tạo một endpoint nghiêm ngặt, trả HTTP 400 cho đầu vào sai trước khi gọi service.
5. Thêm kiểm tra tham số lặp và chuỗi số vượt miền int.
6. Đặt giới hạn độ sâu có ý nghĩa cho ứng dụng, đồng thời tính offset bằng long.
7. Kiểm tra metadata trên trang đầu, trang cuối và trang rỗng.
8. Nếu chuyển hợp đồng sang bắt đầu từ 1, cập nhật đồng bộ request, response và liên kết điều hướng.

Bài thực hành đạt yêu cầu khi bạn giải thích được **mặc định**, **trần kích thước**, **chuẩn hóa**, **từ chối đầu vào** và **quy đổi chỉ số trang** là những quyết định riêng; đồng thời chứng minh được endpoint thực thi đúng chính sách đã công bố.
