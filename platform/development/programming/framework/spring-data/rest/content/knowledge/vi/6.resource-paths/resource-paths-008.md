# Chuyển đổi ID bằng BackendIdConverter, mã hóa URL và xử lý ID không hợp lệ

## Mục tiêu

Spring Data REST tạo item resource theo dạng một đường dẫn có ID ở cuối, ví dụ /customers/1001. ID trong URL là biểu diễn công khai của định danh backend. Với ID đơn giản như Long hoặc UUID, biểu diễn mặc định thường đã đủ. Với khóa ghép, ID cần định dạng riêng hoặc yêu cầu không để lộ trực tiếp kiểu ID nội bộ, có thể dùng BackendIdConverter để chuyển đổi qua lại giữa ID trong URI và ID mà repository sử dụng.

Khi thiết kế đường dẫn tài nguyên, cần tách biệt bốn việc:

1. Xác định base path và collection path của repository.
2. Tạo URI item từ một ID dưới dạng đúng một path segment.
3. Chuyển ID công khai trong request thành kiểu ID backend bằng BackendIdConverter.
4. Trả lỗi rõ ràng khi ID sai định dạng hoặc không trỏ tới entity tồn tại.

Đường dẫn, mã hóa URI và chuyển đổi ID liên quan với nhau nhưng là các lớp riêng. BackendIdConverter không đổi tên collection path; nó chỉ kiểm soát cách ID được biểu diễn trong URI và cách khôi phục ID để tra cứu.

## 1. Cấu trúc đường dẫn tài nguyên

Một item resource của Spring Data REST thường có dạng:

    https://example.test/<context-path>/<base-path>/<repository-path>/<id>

Các phần có ý nghĩa khác nhau:

| Thành phần | Ví dụ | Nguồn cấu hình |
|---|---|---|
| Host và port | https://example.test | Máy chủ ứng dụng |
| Context path | /app | Cấu hình servlet hoặc Spring Boot |
| Spring Data REST base path | /api | spring.data.rest.base-path hoặc RepositoryRestConfiguration |
| Repository path | /customers | Domain type hoặc @RepositoryRestResource |
| Item ID | /1001 | ID được chuyển thành chuỗi URI |

Ví dụ, khi ứng dụng chạy dưới context path /app, Spring Data REST base path /api và repository path /customers, item resource có thể là:

    https://example.test/app/api/customers/1001

### 1.1. Repository path mặc định

Spring Data REST xuất bản collection resource dựa trên tên đơn giản của domain class. Tên được chuyển thành chữ thường và số nhiều bằng quy tắc pluralization của framework.

Ví dụ:

    public interface CustomerRepository
            extends CrudRepository<Customer, Long> {
    }

Repository này thường được export tại /customers và mỗi item có URI theo mẫu /customers/{id}.

Đừng suy luận URL từ tên interface nếu dự án có cấu hình tùy chỉnh. Hãy gửi GET đến root resource và theo các link HAL trong _links để tìm đường dẫn thực tế.

### 1.2. Đổi repository path và relation

Dùng @RepositoryRestResource để đổi path của collection và relation name của link:

    @RepositoryRestResource(
        path = "customers",
        collectionResourceRel = "customers"
    )
    public interface CustomerRepository
            extends CrudRepository<Customer, Long> {
    }

Trong đó:

- path = "customers" đổi URI collection thành /customers.
- collectionResourceRel = "customers" đổi tên relation trong _links.
- Item resource được đặt dưới collection path, ví dụ /customers/{id}.

Path và rel không đồng nghĩa. Path ảnh hưởng đến URL; rel ảnh hưởng đến tên link mà client nhìn thấy trong HAL.

### 1.3. Đổi path của query method và association

Dùng @RestResource ở cấp phương thức để đổi đường dẫn của query method:

    @RepositoryRestResource(path = "customers")
    public interface CustomerRepository
            extends CrudRepository<Customer, Long> {

        @RestResource(path = "by-email", rel = "byEmail")
        Optional<Customer> findByEmailAddress(
                @Param("email") String email);
    }

Query method được đặt dưới search resource:

    GET /customers/search/by-email?email=an@example.test

path = "by-email" đổi URL; rel = "byEmail" đổi tên relation trong danh sách link của search resource.

Tương tự, có thể đặt @RestResource trên thuộc tính association để đổi path và relation của association resource. Association resource thường nằm dưới item resource:

    /customers/{id}/orders

### 1.4. Đổi base path

Có thể đặt base path trong Spring Boot:

    spring.data.rest.base-path=/api

Hoặc cấu hình qua RepositoryRestConfigurer:

    @Component
    public class RestConfiguration implements RepositoryRestConfigurer {

        @Override
        public void configureRepositoryRestConfiguration(
                RepositoryRestConfiguration config,
                CorsRegistry cors) {
            config.setBasePath("/api");
        }
    }

Base path chỉ thêm tiền tố cho các resource Spring Data REST. Nó khác context path của toàn bộ ứng dụng và khác path riêng của từng repository.

## 2. ID trong URI là một path segment

Item resource có dạng:

    /customers/{id}

ID chiếm một path segment. Nó không phải query parameter và không được chứa ký tự làm thay đổi cấu trúc đường dẫn.

Ví dụ, nếu ID thô là A+B/42 thì không nên ghép trực tiếp thành:

    /customers/A+B/42

Dấu gạch chéo sẽ tạo thêm segment. Dấu hỏi bắt đầu query string; dấu thăng bắt đầu fragment. Khoảng trắng và nhiều ký tự khác cũng cần percent-encoding trước khi gửi qua HTTP.

Một số ví dụ mã hóa cho một path segment:

| Giá trị gốc | Dạng percent-encoded |
|---|---|
| A B | A%20B |
| A+B | A%2BB |
| A/B | A%2FB |
| A?B | A%3FB |
| A#B | A%23B |
| A%B | A%25B |
| Nguyễn | Mã hóa theo từng byte UTF-8 rồi percent-encode |

Percent-encoding áp dụng cho từng byte UTF-8 của ký tự không ASCII. Vì vậy một ký tự Unicode có thể tạo ra nhiều nhóm %HH.

### 2.1. Tạo URI bằng Spring UriComponentsBuilder

Khi client tự tạo URI, dùng URI builder để mã hóa giá trị như một biến path segment:

    URI uri = UriComponentsBuilder
            .fromUriString("https://example.test")
            .pathSegment("api", "customers", "{id}")
            .encode()
            .buildAndExpand("A+B/42")
            .toUri();

Giá trị ID được coi là dữ liệu của một segment. Spring sẽ mã hóa ký tự có ý nghĩa đặc biệt trong giá trị biến khi mở rộng URI template.

Nếu xây dựng link thủ công cho một segment đơn, Spring cũng cung cấp UriUtils.encodePathSegment. Trong hầu hết trường hợp, UriComponentsBuilder giúp quản lý cả cấu trúc URI và encoding rõ ràng hơn.

### 2.2. Không dùng URLEncoder cho path segment

java.net.URLEncoder được thiết kế cho dữ liệu form application/x-www-form-urlencoded, thường dùng trong query hoặc form body. Quy tắc của nó biến dấu cách thành dấu cộng (+). Đây không phải quy tắc tổng quát để mã hóa một path segment.

Trong path:

- Dấu cộng có thể là ký tự cộng thực sự.
- Dấu cách được biểu diễn bằng %20.
- Nếu cần biểu diễn dấu cộng trong một giá trị, nó thường được percent-encode thành %2B.

Dùng sai bộ mã hóa có thể khiến server nhận một ID khác với ID ban đầu.

### 2.3. Tránh mã hóa hai lần

Chỉ mã hóa giá trị một lần ở ranh giới tạo URI. Ví dụ:

- Dấu % trong ID thô được mã hóa thành %25.
- Nếu chuỗi đã có %2F lại bị mã hóa lần nữa, dấu % trở thành %25 và server nhận chuỗi %2F thay vì dấu gạch chéo đã giải mã.
- Mã hóa hai lần khiến ID được tạo ra không còn khớp với ID ban đầu.

BackendIdConverter nhận ID đã được phân tích từ request path. Không gọi URLDecoder một cách mặc định trong fromRequestId. Hãy kiểm tra chính xác giá trị mà ứng dụng nhận được trước khi thêm bất kỳ bước decode nào.

URLDecoder cũng dùng quy tắc form, trong đó dấu cộng có thể được hiểu thành dấu cách. Không dùng nó như một bộ giải mã path segment chung.

### 2.4. Cẩn thận với dấu gạch chéo trong ID

UriComponentsBuilder có thể mã hóa dấu gạch chéo trong một path segment thành %2F. Tuy nhiên, reverse proxy, web server hoặc servlet container có thể từ chối hoặc chuẩn hóa encoded slash trước khi Spring nhận request.

Vì vậy, không nên phụ thuộc vào ID có dấu / trong URL nếu hạ tầng triển khai không kiểm soát được cách xử lý encoded slash. Hãy dùng định dạng URL-safe như UUID hoặc Base64 URL-safe để ID luôn nằm trong một segment.

## 3. BackendIdConverter là gì?

BackendIdConverter là SPI trong package:

    org.springframework.data.rest.webmvc.spi

Nó cho phép tùy chỉnh cách entity ID được đưa vào URI và cách ID từ request được chuyển thành giá trị backend cần tra cứu.

Interface có ba phần quan trọng:

| Thành phần | Vai trò |
|---|---|
| supports(Class<?> entityType) | Xác định converter có áp dụng cho domain type này không |
| toRequestId(Serializable id, Class<?> entityType) | Chuyển backend ID thành chuỗi ID để dùng trong URI |
| fromRequestId(String id, Class<?> entityType) | Chuyển chuỗi ID lấy từ request thành backend ID |

Luồng đi và về:

    Backend entity ID
        |
        v
    toRequestId(...)
        |
        v
    ID trong URI / HAL link
        |
        v
    HTTP request
        |
        v
    fromRequestId(...)
        |
        v
    Backend entity ID
        |
        v
    Repository lookup

BackendIdConverter.DefaultIdConverter là converter mặc định. Nó dùng ID như hiện có: toRequestId trả về biểu diễn chuỗi của ID và fromRequestId trả về chuỗi đã nhận. Nếu không cần định dạng ID riêng, không cần viết converter mới.

### 3.1. Khi nào nên dùng converter riêng?

Một converter riêng có thể hữu ích khi:

- Repository dùng composite key hoặc @EmbeddedId.
- ID backend cần có một biểu diễn URI ổn định, dễ đọc hoặc URL-safe.
- Hệ thống cần công bố một dạng ID khác với biểu diễn nội bộ, nhưng vẫn có thể chuyển đổi xác định và ngược lại.
- Nhiều domain type cần quy tắc ID khác nhau.

Không dùng converter chỉ để đổi collection path. Hãy dùng @RepositoryRestResource(path = "...") cho việc đó.

Converter cũng không thay thế xác thực hoặc phân quyền. Một ID khó đoán hay được mã hóa vẫn không chứng minh người gọi có quyền đọc hoặc sửa entity.

## 4. Cài đặt BackendIdConverter

Ví dụ sau giả định Customer có backend ID kiểu Long. ID được công bố trong URL dưới dạng Base64 URL-safe của chuỗi số thập phân.

Repository:

    public interface CustomerRepository
            extends CrudRepository<Customer, Long> {
    }

Converter:

    @Component
    public class CustomerIdConverter implements BackendIdConverter {

        @Override
        public boolean supports(Class<?> entityType) {
            return Customer.class.equals(entityType);
        }

        @Override
        public Serializable fromRequestId(
                String requestId, Class<?> entityType) {

            if (!Customer.class.equals(entityType)) {
                throw new IllegalArgumentException(
                        "Unsupported entity type");
            }

            try {
                byte[] bytes = Base64.getUrlDecoder().decode(requestId);
                String value = new String(bytes, StandardCharsets.UTF_8);

                if (!value.matches("[1-9][0-9]*")) {
                    throw new IllegalArgumentException(
                            "Invalid customer identifier");
                }

                Long backendId = Long.valueOf(value);

                String canonical = Base64.getUrlEncoder()
                        .withoutPadding()
                        .encodeToString(value.getBytes(StandardCharsets.UTF_8));

                if (!canonical.equals(requestId)) {
                    throw new IllegalArgumentException(
                            "Non-canonical customer identifier");
                }

                return backendId;

            } catch (IllegalArgumentException ex) {
                throw new IllegalArgumentException(
                        "Invalid customer identifier", ex);
            }
        }

        @Override
        public String toRequestId(
                Serializable id, Class<?> entityType) {

            if (!Customer.class.equals(entityType)
                    || !(id instanceof Long)) {
                throw new IllegalArgumentException(
                        "Expected a Long customer identifier");
            }

            String value = id.toString();

            return Base64.getUrlEncoder()
                    .withoutPadding()
                    .encodeToString(value.getBytes(StandardCharsets.UTF_8));
        }
    }

Converter được đăng ký như một Spring bean, ví dụ bằng @Component trong package được component scan. Spring Data REST xây dựng registry từ các BackendIdConverter bean và chọn converter có supports trả về true cho domain type tương ứng.

Với ID backend 1001:

- toRequestId chuyển chuỗi "1001" thành token "MTAwMQ".
- HAL link có thể chứa /customers/MTAwMQ.
- Khi request đến, fromRequestId giải mã token và trả về Long.valueOf("1001").
- Repository tiếp tục tra cứu bằng ID backend kiểu Long.

Base64 URL-safe dùng bảng ký tự phù hợp với URL path và bỏ padding cuối chuỗi. Đây chỉ là mã hóa có thể đảo ngược, không phải mã hóa bảo mật. Người dùng có thể giải mã token để biết giá trị ban đầu. Nếu cần ID công khai không tiết lộ ID tuần tự, hãy cân nhắc UUID ngẫu nhiên được lưu làm định danh công khai hoặc một cơ chế token có khóa và kiểm soát vòng đời rõ ràng.

### 4.1. Hỗ trợ composite ID

Với composite key, fromRequestId có thể giải mã token rồi tạo lại một value object triển khai Serializable, ví dụ OrderId chứa tenantId và orderNumber. toRequestId thực hiện chiều ngược lại.

Cần bảo đảm:

- OrderId có equals và hashCode nhất quán.
- Cách ghép hai thành phần không gây nhập nhằng. Có thể dùng cấu trúc JSON có schema hoặc delimiter được escape đúng cách.
- Chuỗi sau mã hóa luôn nằm trong một path segment.
- Hai composite ID khác nhau không được tạo cùng một request ID.
- Phiên bản format ID được quản lý nếu API cần hỗ trợ thay đổi format trong tương lai.

BackendIdConverter không tự tạo composite key cho entity. Nó chỉ chuyển đổi biểu diễn URI và đối tượng ID mà repository cần nhận.

### 4.2. Quy tắc triển khai converter

Một converter ổn định cần tuân theo các quy tắc sau:

1. supports chỉ trả true cho domain type mà converter thực sự xử lý.
2. toRequestId và fromRequestId phải là hai chiều tương ứng.
3. Kết quả toRequestId phải ổn định và duy nhất cho mỗi backend ID.
4. fromRequestId phải trả về một Serializable không null theo hợp đồng của interface.
5. Không trả null để báo ID sai. Hãy ném exception có ý nghĩa để lớp xử lý HTTP biến nó thành phản hồi lỗi phù hợp.
6. Kiểm tra giới hạn độ dài, bảng ký tự, overflow và định dạng canonical trước khi tra cứu.
7. Không để converter áp dụng cho entity khác chỉ vì entity đó có cùng kiểu ID.

## 5. Xử lý ID không hợp lệ

Có hai trường hợp cần phân biệt: ID không thể chuyển đổi và ID hợp lệ nhưng không tìm thấy entity.

| Trường hợp | Ví dụ | Phản hồi API nên có |
|---|---|---|
| ID sai định dạng | Token không phải Base64 URL-safe hoặc giải mã thành chuỗi không phải số | 400 Bad Request |
| ID vượt phạm vi backend | Số giải mã lớn hơn giới hạn Long | 400 Bad Request |
| ID hợp lệ nhưng không có entity | Token giải mã thành 1002, nhưng repository không có Customer 1002 | 404 Not Found |
| Resource không hỗ trợ HTTP method | Gửi POST tới item resource | 405 Method Not Allowed |
| Người gọi không có quyền | ID tồn tại nhưng người gọi không được truy cập | 401 hoặc 403 tùy cơ chế bảo mật |

### 5.1. Xác thực cú pháp trước khi truy vấn

fromRequestId nên kiểm tra token trước khi trả về backend ID:

- Token không rỗng.
- Độ dài nằm trong giới hạn hợp lý.
- Chỉ chấp nhận bảng ký tự mà format đã định nghĩa.
- Dữ liệu sau decode đúng cấu trúc.
- Số nằm trong phạm vi kiểu ID.
- Nếu format yêu cầu canonical, token được tạo lại phải khớp chính xác token đầu vào.

Không nên chuyển token sai định dạng thành 0, null hoặc một ID mặc định. Làm vậy có thể khiến request sai vô tình trỏ đến một entity thật.

### 5.2. Phân biệt 400 và 404

400 Bad Request phù hợp khi client gửi một giá trị ID không thể phân tích hoặc không tuân theo format API. Đây là lỗi đầu vào.

404 Not Found phù hợp khi ID đã được phân tích thành công nhưng không có entity tương ứng. Không nên biến một lỗi parse thành 404 chỉ để che giấu lỗi định dạng, cũng không nên trả 500 cho lỗi đầu vào thông thường.

Spring Data REST có cơ chế xử lý exception riêng. Cách một exception cụ thể được ánh xạ thành status code có thể phụ thuộc phiên bản và exception handler của ứng dụng. Hãy kiểm tra phản hồi thực tế của phiên bản đang dùng. Nếu converter ném exception tùy chỉnh mà mặc định không ánh xạ thành 400, hãy cấu hình exception handler cho loại exception đó và giữ response body ngắn gọn, không tiết lộ chi tiết nội bộ.

### 5.3. URI sai encoding có thể bị chặn trước converter

Nếu request chứa percent escape không hợp lệ như %ZZ, hoặc encoded slash bị proxy/container từ chối, request có thể bị chặn trước khi Spring Data REST phân tích path variable. Khi đó fromRequestId không được gọi.

Khi điều tra lỗi, hãy kiểm tra theo thứ tự:

1. Client đã tạo URI đúng chưa?
2. Reverse proxy hoặc gateway có thay đổi path không?
3. Servlet container có chấp nhận encoded path segment đó không?
4. Spring MVC có phân tích được path variable không?
5. BackendIdConverter có nhận đúng chuỗi ID không?
6. Repository có entity mang backend ID đó không?

Thứ tự này giúp xác định lỗi xảy ra ở tầng URI, tầng chuyển đổi ID hay tầng dữ liệu.

## 6. Kiểm tra converter và đường dẫn bằng test

### 6.1. Unit test round-trip

Với một backend ID hợp lệ, kết quả chuyển đổi phải khôi phục chính xác giá trị ban đầu:

    Long backendId = 1001L;

    String requestId = converter.toRequestId(
            backendId, Customer.class);

    Serializable restoredId = converter.fromRequestId(
            requestId, Customer.class);

    assertEquals(backendId, restoredId);

Nên kiểm tra thêm nhiều giá trị biên: ID nhỏ nhất được hỗ trợ, ID lớn nhất, token rỗng, token sai alphabet, dữ liệu giải mã không phải số và số vượt giới hạn Long.

### 6.2. Integration test HTTP

Dùng MockMvc hoặc test HTTP tương đương để xác minh toàn bộ đường đi:

- GET root và collection để xác nhận link HAL.
- GET item bằng ID token hợp lệ và entity tồn tại.
- GET item bằng ID token hợp lệ nhưng entity không tồn tại.
- GET item bằng token sai định dạng.
- Kiểm tra ID chứa ký tự đặc biệt được encode đúng trong URI.
- Xác nhận converter không được áp dụng cho domain type khác.
- Xác nhận route có base path và repository path đúng như cấu hình.

Các kỳ vọng cơ bản:

| Request | Kết quả mong đợi |
|---|---|
| GET /api/customers/MTAwMQ, Customer 1001 tồn tại | 200 OK |
| GET /api/customers/MTAwMg, Customer 1002 không tồn tại | 404 Not Found |
| GET /api/customers/not-a-valid-token | 400 Bad Request |
| POST /api/customers/MTAwMQ khi item không hỗ trợ POST | 405 Method Not Allowed |

Nếu dự án dùng exception handler riêng, test phải xác nhận đúng status code và cấu trúc lỗi mà API cam kết.

## 7. Checklist điều tra lỗi đường dẫn và ID

Khi một item URL không hoạt động, kiểm tra lần lượt:

1. Root HAL resource có link tới đúng repository không?
2. Repository có path được tùy chỉnh bằng @RepositoryRestResource không?
3. Base path và context path có bị ghép thiếu hoặc lặp không?
4. ID được đặt trong đúng một path segment chưa?
5. Client có percent-encode giá trị path variable đúng cách không?
6. Có dùng URLEncoder hoặc URLDecoder sai ngữ cảnh không?
7. Có mã hóa hai lần hoặc giải mã hai lần không?
8. BackendIdConverter.supports có chọn đúng domain type không?
9. fromRequestId có tạo đúng kiểu backend ID và không trả null không?
10. Entity có tồn tại với backend ID sau chuyển đổi không?
11. Proxy, gateway và servlet container có thay đổi hoặc chặn encoded path không?
12. Status code và response body có phản ánh đúng lỗi parse, không tìm thấy, method không hỗ trợ hay lỗi quyền truy cập không?

Ưu tiên theo link HAL do server trả về. Link đó phản ánh base path, repository path, relation và ID representation mà server hiện đang sử dụng.

## Tài liệu tham khảo

- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Configuring the REST URL Path](https://docs.spring.io/spring-data/rest/reference/customizing/configuring-the-rest-url-path.html)
- [Spring Data REST — BackendIdConverter API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/spi/BackendIdConverter.html)
- [Spring Data REST — BackendIdHandlerMethodArgumentResolver API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/support/BackendIdHandlerMethodArgumentResolver.html)
- [Spring Framework — URI Links and URI Encoding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-uri-building.html)
