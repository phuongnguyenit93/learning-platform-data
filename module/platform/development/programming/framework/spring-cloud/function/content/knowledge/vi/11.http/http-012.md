# Giới hạn HTTP method bằng spring.cloud.function.http trong Spring Cloud Function

## 1. Vì sao cần giới hạn HTTP method?

Trong **Spring Cloud Function (SCF)**, logic nghiệp vụ được khai báo dưới dạng bean Java `Supplier<O>`, `Function<I, O>` và `Consumer<I>`, rồi đăng ký vào `FunctionCatalog`. Cùng một logic có thể được gọi qua HTTP, sự kiện Spring Cloud Stream hoặc môi trường serverless. HTTP adapter chịu trách nhiệm đưa dữ liệu vào hàm và biểu diễn kết quả thành HTTP response.

Khi bật `spring-cloud-starter-function-web`, SCF có những quy tắc mặc định theo loại hàm:

- `Supplier` thường dùng `GET /{supplier}`.
- `Function` thường dùng `POST`/`PUT /{function}`, hoặc `GET /{function}/{item}`.
- `Consumer` có thể dùng `POST`/`PUT`/`DELETE /{consumer}`.

Các mapping này hữu ích cho nguyên mẫu, nhưng chưa chắc phù hợp với một **HTTP API có hợp đồng cụ thể**. Ví dụ, bạn muốn:

1. Chỉ cho phép `GET` với hàm đọc trạng thái.
2. Chỉ cho phép `POST` với thao tác tạo báo giá.
3. Chỉ cho phép `PUT` với thao tác thay thế dữ liệu.
4. Chỉ cho phép `DELETE` với thao tác yêu cầu xóa.

Thay vì để cùng function được gọi từ nhiều HTTP method mặc định, SCF hỗ trợ cấu hình **method-specific function mapping**:

```properties
spring.cloud.function.http.GET=status
spring.cloud.function.http.POST=quote
spring.cloud.function.http.PUT=replaceStock
spring.cloud.function.http.DELETE=deleteById
```

Đây là nội dung trọng tâm của bài: **giới hạn những function/composition được HTTP adapter ánh xạ cho từng method**, đồng thời phân biệt giới hạn HTTP route với bảo mật và ngữ nghĩa nghiệp vụ.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích cấu trúc property `spring.cloud.function.http.<METHOD>` và cách nó khác `spring.cloud.function.definition`.
- Gán GET/POST/PUT/DELETE cho những functional bean phù hợp, bao gồm composition.
- Dùng `;` để liệt kê nhiều hàm cho cùng method và `|` để ghép hàm.
- Dự đoán URL, request body, response body và status theo loại `Supplier`/`Function`/`Consumer`.
- Kiểm thử cả method hợp lệ lẫn method không được ánh xạ, không nhầm `404` với `405`.
- Hiểu vì sao giới hạn method **không tự bảo đảm idempotency, authorization hoặc dữ liệu đã được lưu bền vững**.

## 2. Quy tắc HTTP mặc định trước khi cấu hình riêng

Theo tài liệu chính thức **Standalone Web Applications** của SCF:

| HTTP method | Đường dẫn mặc định | Bean tương ứng | Request | Status thông thường khi thành công |
| --- | --- | --- | --- | --- |
| GET | `/{supplier}` | `Supplier<O>` | Không cần body | 200 OK, dữ liệu do Supplier tạo |
| POST | `/{function}` | `Function<I,O>` | Body text/JSON | 200 OK, kết quả áp dụng hàm |
| PUT | `/{function}` | `Function<I,O>` | Body text/JSON | 200 OK |
| GET | `/{function}/{item}` | `Function<I,O>` | Một giá trị trong path | 200 OK |
| POST | `/{consumer}` | `Consumer<I>` | Body text/JSON | 202 Accepted |
| PUT | `/{consumer}` | `Consumer<I>` | Body text/JSON | 202 Accepted |
| DELETE | `/{consumer}` | `Consumer<I>` | Dữ liệu theo hợp đồng adapter | 204 No Content |

Bảng này mô tả **những phương thức adapter có thể xử lý theo mặc định**, không phải yêu cầu rằng mọi ứng dụng phải công bố tất cả. Hàm còn phải tồn tại trong `FunctionCatalog`, tên/path phải giải quyết được và request phải có media type phù hợp.

**Điểm dễ nhầm:** có HTTP method hợp lệ **không có nghĩa code nghiệp vụ thực hiện đúng ngữ nghĩa của method đó**. Ví dụ, Java `Function.apply()` có thể cập nhật database bất kể client gọi bằng POST hay PUT. SCF không tự kiểm tra quy tắc idempotent của PUT.

### Trường hợp một hoặc nhiều function

Khi chỉ có **một** functional bean trong catalog, tên trong URL có thể bỏ qua, ví dụ `POST /`. Khi có nhiều bean, URL thường gồm tên function. `spring.cloud.function.definition` có thể chọn function/composition mặc định tại root, nhưng đó là **cơ chế khác** với mapping theo HTTP method của bài này.

## 3. Cú pháp spring.cloud.function.http.<METHOD>

Cấu hình có dạng:

```properties
spring.cloud.function.http.GET=foo;bar;normalize|uppercase
spring.cloud.function.http.POST=quote
spring.cloud.function.http.PUT=replaceStock
spring.cloud.function.http.DELETE=deleteById
```

Tài liệu SCF gọi đây là **CRUD REST with Spring Cloud Function**. Giá trị của mỗi property là tên function hoặc danh sách function/composition được phép ánh xạ cho **method được nêu ở key**.

### 3.1. Ý nghĩa của key

- `spring.cloud.function.http.GET`: lựa chọn function/composition được ánh xạ khi request dùng GET.
- `spring.cloud.function.http.POST`: danh sách được ánh xạ khi dùng POST.
- `spring.cloud.function.http.PUT`: danh sách được ánh xạ khi dùng PUT.
- `spring.cloud.function.http.DELETE`: danh sách được ánh xạ khi dùng DELETE.

Tên method ở ví dụ là **chữ hoa**, đúng kiểu cú pháp được tài liệu chính thức dùng. Không tự giả định rằng mọi HTTP method ít gặp như PATCH, HEAD hay OPTIONS đều được áp dụng theo cùng một cách ở mọi phiên bản SCF; nếu cần, hãy kiểm tra module web đang chạy hoặc xây dựng controller/router.

### 3.2. Ý nghĩa của chuỗi value

| Value | Số mục được liệt kê | Ý nghĩa |
| --- | ---: | --- |
| `quote` | 1 | Chọn một function |
| `quote;reverse` | 2 | Chọn hai function độc lập |
| `normalize\|uppercase` | 1 | Chọn một composition chạy normalize rồi uppercase |
| `normalize\|uppercase;quote` | 2 | Một composition và một function |
| `status;uppercase;normalize\|uppercase` | 3 | Hai function độc lập và một composition |

Trong bảng:

- **Dấu chấm phẩy** (`;`) liệt kê những mục cùng được ánh xạ cho method.
- **Dấu pipe** (`|`) ghép các hàm **từ trái sang phải** trong cùng một mục.
- **Dấu phẩy** (`,`) thường thuận tiện khi gọi composition qua URL, ví dụ `/normalize,uppercase`.

Các ký tự phân cách thuộc **giá trị cấu hình**, không phải một cơ chế phân quyền người dùng.

### 3.3. Ví dụ từ tài liệu chính thức

Tài liệu SCF đưa ví dụ:

```properties
spring.cloud.function.http.GET=uppercase;reverse;foo|bar
spring.cloud.function.http.POST=reverse
spring.cloud.function.http.DELETE=deleteById
```

Ở đây `reverse` được phép xuất hiện trong danh sách của **cả GET và POST**; mỗi phương thức có mapping riêng. `foo|bar` là composition được ánh xạ cho GET. Nếu code của `foo` và `bar` không tương thích kiểu hoặc không phù hợp với nguồn input của GET, cấu hình có thể tồn tại nhưng khi gọi sẽ lỗi; **không phải tên method tự làm function hợp lệ về mặt nghiệp vụ**.

## 4. Một ví dụ hoàn chỉnh để thực hành

Chúng ta sẽ xây dựng một ứng dụng gồm nhiều functional bean, sau đó dùng property theo method để **chỉ công bố những thao tác cần thiết**.

### 4.1. Dependency

Dự án Spring Boot cần dùng Spring Cloud dependencies BOM tương thích. Với SCF HTTP adapter dựa trên Spring MVC:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-function-web</artifactId>
</dependency>
```

Không tự ghép các phiên bản Spring Boot, Spring Cloud Function và Reactor không tương thích. Nếu ứng dụng chủ động dùng WebFlux, phải chọn web adapter phù hợp với release train và chạy test trên runtime thực tế.

### 4.2. Bean Java

Tạo `src/main/java/demo/MethodMappingApplication.java` (Java 17+):

```java
package demo;

import java.math.BigDecimal;
import java.util.Locale;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class MethodMappingApplication {

    public static void main(String[] args) {
        SpringApplication.run(MethodMappingApplication.class, args);
    }

    // Chỉ đọc trạng thái; thích hợp với GET.
    @Bean
    public Supplier<ServiceStatus> status() {
        return () -> new ServiceStatus("READY", "SCF-DEMO");
    }

    // Function một đầu vào String, có thể gọi qua GET /uppercase/{item}.
    @Bean
    public Function<String, String> uppercase() {
        return text -> text.toUpperCase(Locale.ROOT);
    }

    // Thành phần của pipeline POST normalize|uppercase.
    @Bean
    public Function<String, String> normalize() {
        return String::trim;
    }

    // POST: nhận JSON và trả JSON.
    @Bean
    public Function<QuoteRequest, QuoteResponse> quote() {
        return request -> {
            if (request == null || request.sku() == null
                    || request.sku().isBlank()
                    || request.quantity() <= 0) {
                throw new IllegalArgumentException(
                        "Invalid quote request");
            }

            BigDecimal unitPrice = new BigDecimal("120000");
            BigDecimal total = unitPrice.multiply(
                    BigDecimal.valueOf(request.quantity()));

            return new QuoteResponse(
                    request.sku(), request.quantity(), total);
        };
    }

    // PUT: minh họa kết quả của một yêu cầu thay thế tồn kho.
    // Đây là mô phỏng, KHÔNG ghi database.
    @Bean
    public Function<StockChange, StockReceipt> replaceStock() {
        return request -> {
            if (request == null || request.sku() == null
                    || request.sku().isBlank()
                    || request.quantity() < 0) {
                throw new IllegalArgumentException(
                        "Invalid stock replacement");
            }

            return new StockReceipt(
                    request.sku(), request.quantity(), "SIMULATED");
        };
    }

    // DELETE: Consumer xử lý lệnh, KHÔNG tự xóa bản ghi nào.
    @Bean
    public Consumer<String> deleteById() {
        return sku -> System.out.println(
                "Simulated delete request for SKU: " + sku);
    }

    // Bean có trong catalog nhưng không muốn xuất qua HTTP.
    @Bean
    public Function<String, String> internalEcho() {
        return input -> "[internal] " + input;
    }

    public record ServiceStatus(String state, String service) {}
    public record QuoteRequest(String sku, int quantity) {}
    public record QuoteResponse(
            String sku, int quantity, BigDecimal totalPrice) {}
    public record StockChange(String sku, int quantity) {}
    public record StockReceipt(
            String sku, int quantity, String result) {}
}
```

Ứng dụng có **bảy** functional bean. Code không dùng `HttpServletRequest`, `@PostMapping` hoặc `@DeleteMapping`; đó chính là tính độc lập với HTTP mà SCF theo đuổi. Bean `internalEcho` minh họa logic nội bộ cần tránh xuất ngoài ý muốn.

**Chú ý:** `replaceStock` trả kết quả `SIMULATED`, không thay đổi dữ liệu. `deleteById` chỉ ghi log, không thực sự xóa tài nguyên. Tên hàm và HTTP method không tự tạo tính bền vững, transaction hay nghiệp vụ CRUD.

### 4.3. Cấu hình HTTP methods

Trong `src/main/resources/application.properties`:

```properties
spring.cloud.function.http.GET=status;uppercase
spring.cloud.function.http.POST=normalize|uppercase;quote
spring.cloud.function.http.PUT=replaceStock
spring.cloud.function.http.DELETE=deleteById
```

Đây là bốn danh sách riêng:

1. GET: Supplier `status` và Function `uppercase`.
2. POST: composition `normalize|uppercase` và Function `quote`.
3. PUT: Function `replaceStock`.
4. DELETE: Consumer `deleteById`.

**Không** khai báo `spring.cloud.function.definition` trong ví dụ này để tránh trộn root/fallback/function filtering với method-specific mappings. Sau khi hiểu từng cơ chế, mới kết hợp chúng và viết integration test cho tương tác thực tế.

Chạy:

```bash
mvn spring-boot:run
```

Các lệnh `curl` dưới đây dùng Bash. Trên Windows PowerShell, dùng `curl.exe` và điều chỉnh cú pháp xuống dòng. Giả định server ở `http://localhost:8080`.

## 5. Ma trận endpoint được phép theo HTTP method

Theo cấu hình mục 4, lập bảng kỳ vọng:

| Method | URL | Function/composition | Input | Kết quả thành công thông thường |
| --- | --- | --- | --- | --- |
| GET | `/status` | `status` | Không có body | 200 + JSON trạng thái |
| GET | `/uppercase/hello` | `uppercase` | Path item `hello` | 200 + `HELLO` |
| POST | `/normalize,uppercase` | `normalize\|uppercase` | Text trong body | 200 + chuỗi chuẩn hóa/in hoa |
| POST | `/quote` | `quote` | JSON DTO | 200 + JSON báo giá |
| PUT | `/replaceStock` | `replaceStock` | JSON DTO | 200 + kết quả mô phỏng |
| DELETE | `/deleteById` | `deleteById` | Body `text/plain` | 204, response không có body |

**Không suy ra:** `POST /uppercase` tự được ánh xạ chỉ vì bean `uppercase` xuất hiện ở GET. POST trong ví dụ chỉ liệt kê **composition** `normalize|uppercase` và function `quote`. Tương tự, `PUT /quote` và `POST /internalEcho` không nằm trong các danh sách mong muốn.

**Lưu ý chi tiết:** GET cho Function có pattern `/{function}/{item}`; nó không mặc nhiên đọc JSON DTO từ query string. Khi cần input DTO phức tạp, dùng POST/PUT body và ghi rõ `Content-Type`.

## 6. Thực hành GET: Supplier và Function có path item

### 6.1. GET /status

```bash
curl -i 'http://localhost:8080/status' \
  -H 'Accept: application/json'
```

Response điển hình:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"state":"READY","service":"SCF-DEMO"}
```

Supplier không lấy input nghiệp vụ từ request body. Theo ý nghĩa HTTP, GET nên được thiết kế như thao tác đọc, không thay đổi trạng thái của server ngoài các tác dụng phụ phụ trợ như ghi log.

### 6.2. GET /uppercase/{item}

```bash
curl -i 'http://localhost:8080/uppercase/hello' \
  -H 'Accept: text/plain'
```

Response body dự kiến:

```text
HELLO
```

Input `hello` đến từ **path item**, không phải `POST` body. Nếu giá trị chứa dấu cách hoặc ký tự đặc biệt, cần percent-encode đúng path segment, ví dụ `hello%20world`. Dữ liệu tự do hoặc phức tạp nên truyền qua body của method phù hợp.

### 6.3. Những request không tương đương

```bash
# Có method GET nhưng không có item đối với Function.
curl -i 'http://localhost:8080/uppercase'

# Cùng tên uppercase nhưng POST không nằm trong method mapping.
curl -i -X POST 'http://localhost:8080/uppercase' \
  -H 'Content-Type: text/plain' --data 'hello'
```

Hai request có thể thất bại vì **những lý do khác nhau**: một request thiếu hình dạng path input, request còn lại không được lựa chọn cho POST. Status `404 Not Found` hoặc `405 Method Not Allowed` có thể khác nhau tùy adapter, route fallback và web runtime. Không nên dùng status đơn lẻ để đoán nguyên nhân.

## 7. Thực hành POST: Function đơn và composition

### 7.1. POST /quote với JSON

```bash
curl -i -X POST 'http://localhost:8080/quote' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"sku":"BOOK-001","quantity":2}'
```

Response nghiệp vụ dự kiến:

```json
{
  "sku": "BOOK-001",
  "quantity": 2,
  "totalPrice": 240000
}
```

HTTP status thành công thông thường `200 OK`. Đây là `Function<QuoteRequest, QuoteResponse>`, nên adapter dùng JSON converter để chuyển body thành input DTO rồi chuyển kết quả thành JSON.

### 7.2. POST /normalize,uppercase với text

```bash
curl -i -X POST 'http://localhost:8080/normalize,uppercase' \
  -H 'Content-Type: text/plain' \
  -H 'Accept: text/plain' \
  --data '  hello  '
```

Composition xử lý:

```text
"  hello  "
    |
normalize -> "hello"
    |
uppercase -> "HELLO"
    |
response  -> "HELLO"
```

Dấu pipe trong file cấu hình `normalize|uppercase` biểu thị **thứ tự ghép hàm**, còn dấu phẩy ở path `/normalize,uppercase` biểu thị **cùng composition**. POST chỉ nhận những mục mà ta liệt kê trong `spring.cloud.function.http.POST`.

### 7.3. Kiểm tra POST không được phép

```bash
# Không liệt kê reverse trong POST.
curl -i -X POST 'http://localhost:8080/reverse' \
  -H 'Content-Type: text/plain' --data 'hello'

# Composition khác không có trong danh sách POST.
curl -i -X POST 'http://localhost:8080/uppercase,normalize' \
  -H 'Content-Type: text/plain' --data '  hello  '

# Bean nội bộ không nằm ở bất kỳ danh sách method nào.
curl -i -X POST 'http://localhost:8080/internalEcho' \
  -H 'Content-Type: text/plain' --data 'hello'
```

Các request trên **không thuộc mapping dự kiến**. Nếu một trong chúng vẫn gọi được function, cần kiểm tra property đang hiệu lực, root/fallback, routing headers, controller khác và version thực tế, thay vì mặc định cấu hình method đã được áp dụng đúng.

## 8. Thực hành PUT: mapping không tự tạo tính idempotent

Cấu hình:

```properties
spring.cloud.function.http.PUT=replaceStock
```

Gọi:

```bash
curl -i -X PUT 'http://localhost:8080/replaceStock' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"sku":"BOOK-001","quantity":50}'
```

Phản hồi minh họa:

```json
{
  "sku": "BOOK-001",
  "quantity": 50,
  "result": "SIMULATED"
}
```

Theo ngữ nghĩa của HTTP, PUT được kỳ vọng là **idempotent**: nhiều lần gửi cùng một yêu cầu có hiệu ứng mong muốn tương đương gửi một lần. Nhưng property method mapping chỉ chọn route; nó **không kiểm tra** nội dung `replaceStock.apply()`. Nếu code ghi database, gửi sự kiện hoặc trừ tiền, ứng dụng phải tự bảo đảm quy tắc retry/idempotency tương ứng.

Trong ví dụ này function không ghi dữ liệu. Nó chỉ mô phỏng để minh họa method và DTO. Nếu muốn xây dựng API thay thế tài nguyên theo ID, URL như `PUT /stocks/{sku}`, validation, ETag hoặc `If-Match` có thể cần Spring MVC/WebFlux controller/router riêng.

## 9. Thực hành DELETE: Consumer và response 204

Cấu hình:

```properties
spring.cloud.function.http.DELETE=deleteById
```

Gửi body đơn giản:

```bash
curl -i -X DELETE 'http://localhost:8080/deleteById' \
  -H 'Content-Type: text/plain' \
  --data 'BOOK-001'
```

Đối với `Consumer<String> deleteById`, SCF HTTP adapter theo bảng mặc định thường trả:

```http
HTTP/1.1 204 No Content
```

**204 No Content không có response body.** Không cố parse JSON từ response này. Quan trọng hơn, bean của ví dụ chỉ ghi log; `204` **không chứng minh** item đã được xóa khỏi database hay transaction đã commit.

Đối với API REST thực, việc gửi DELETE với **request body** cần được cân nhắc: client/proxy/gateway có thể xử lý body của DELETE khác nhau. Nếu muốn `DELETE /stocks/{sku}` với resource ID trong path, có thể dùng controller/router nhận `@PathVariable` rồi gọi một functional bean xử lý nghiệp vụ.

### Consumer không giống Function

Một `Function<I,O>` tạo giá trị trả về, trong khi `Consumer<I>` có chữ ký `void accept(I input)`. Vì thế HTTP adapter dùng các status mặc định khác nhau: Function thường `200`, Consumer POST/PUT thường `202` và DELETE thường `204`. **Gắn Consumer vào DELETE không tự biến function thành một CRUD repository.**

## 10. Phân biệt method mapping với function filtering

Hai cơ chế có vẻ giống nhau về dấu phân cách nhưng phục vụ hai câu hỏi khác nhau.

| Cấu hình | Câu hỏi trả lời | Ví dụ |
| --- | --- | --- |
| `spring.cloud.function.definition` | Function/composition nào được chọn làm mặc định hoặc được công bố? | `foo;bar` |
| `spring.cloud.function.http.POST` | Những function/composition nào được ánh xạ **riêng cho POST**? | `foo;normalize\|uppercase` |
| `spring.cloud.function.web.path` | HTTP adapter dùng **tiền tố URL** nào? | `/api/functions` |
| `spring.cloud.function.http.ignored-headers` | Những HTTP headers nào không được sao chép qua cơ chế propagation? | `X-Internal-Token` |

**Lưu ý:** `spring.cloud.function.http.ignored-headers` nằm cùng tiền tố `spring.cloud.function.http` nhưng **không phải một HTTP method**. Không liệt kê nó trong bảng các mapping GET/POST/PUT/DELETE.

### 10.1. Không có dấu ; cũng có thể là một composition

```properties
spring.cloud.function.http.POST=normalize|uppercase
```

Dòng này chỉ liệt kê **một composition** cho POST. Nếu muốn thêm `quote`, cần dùng dấu chấm phẩy:

```properties
spring.cloud.function.http.POST=normalize|uppercase;quote
```

### 10.2. Không tự suy ra root mapping

`spring.cloud.function.definition=normalize|uppercase` có thể được dùng để chọn composition **mặc định tại root**. Còn `spring.cloud.function.http.POST=normalize|uppercase;quote` là **danh sách theo method**, không phải chỉ dẫn rằng POST root tự chọn mục đầu tiên.

Với ứng dụng có nhiều bean, hãy dùng các URL có tên tương ứng cho method-specific mapping. Nếu cần root mapping riêng cho mỗi HTTP method, cần kiểm thử khả năng phiên bản SCF đang dùng hoặc cấu hình một HTTP controller/router rõ ràng.

### 10.3. Khi cấu hình đồng thời

Một ứng dụng có thể dùng đồng thời các property trên, nhưng cần thận trọng vì `spring.cloud.function.definition` còn được dùng cho **fallback/function filtering** và bởi adapter khác như Spring Cloud Stream. Không mặc định rằng đặt method-specific mapping sẽ vô hiệu hóa mọi root/fallback hoặc routing theo header. Khi kết hợp, phải kiểm thử đúng web adapter/version và toàn bộ tuyến HTTP công bố.

## 11. Cấu hình tiền tố HTTP và các môi trường triển khai

### 11.1. spring.cloud.function.web.path

Để các endpoint nằm dưới `/api/functions`, thêm:

```properties
spring.cloud.function.web.path=/api/functions
spring.cloud.function.http.GET=status;uppercase
spring.cloud.function.http.POST=normalize|uppercase;quote
spring.cloud.function.http.PUT=replaceStock
spring.cloud.function.http.DELETE=deleteById
```

Các URL được hình dung:

```text
GET    /api/functions/status
GET    /api/functions/uppercase/hello
POST   /api/functions/normalize,uppercase
POST   /api/functions/quote
PUT    /api/functions/replaceStock
DELETE /api/functions/deleteById
```

`web.path` chỉ thay **base path**, không thay nội dung danh sách theo method hoặc kiểu Java của function.

Nếu có `server.servlet.context-path=/backend` trong Spring MVC, URL client nhìn thấy còn có thể bắt đầu bằng `/backend/api/functions`. Nếu API gateway rewrite path, phải kiểm tra **URL công khai** và **URL thực backend nhận**; tránh cộng prefix hai lần.

### 11.2. application.yml

Biểu diễn tương đương:

```yaml
spring:
  cloud:
    function:
      web:
        path: /api/functions
      http:
        GET: "status;uppercase"
        POST: "normalize|uppercase;quote"
        PUT: "replaceStock"
        DELETE: "deleteById"
```

Mỗi dòng là một **chuỗi**. Không biến giá trị của POST thành YAML list nếu chưa kiểm tra binder; cú pháp tài liệu SCF được mô tả qua chuỗi definition với dấu `;` và `|`.

### 11.3. Biến môi trường và command line

Trong Bash có thể đặt:

```bash
export SPRING_CLOUD_FUNCTION_HTTP_GET='status;uppercase'
export SPRING_CLOUD_FUNCTION_HTTP_POST='normalize|uppercase;quote'
export SPRING_CLOUD_FUNCTION_HTTP_PUT='replaceStock'
export SPRING_CLOUD_FUNCTION_HTTP_DELETE='deleteById'
mvn spring-boot:run
```

Hoặc truyền property khi chạy artifact:

```bash
java -jar app.jar \
  '--spring.cloud.function.http.GET=status;uppercase' \
  '--spring.cloud.function.http.POST=normalize|uppercase;quote' \
  '--spring.cloud.function.http.PUT=replaceStock' \
  '--spring.cloud.function.http.DELETE=deleteById'
```

`app.jar` là tên file minh họa. Trong shell, `;` có thể tách lệnh và `|` có thể tạo pipe, nên **quote toàn bộ đối số**. Với biến môi trường, Spring Boot thường áp dụng relaxed binding; xác nhận property hiệu lực bằng test thay vì mặc định mọi hình thức viết hoa/thường được xử lý giống nhau trên mọi phiên bản.

## 12. Điều gì xảy ra khi gọi sai HTTP method?

Có hai trường hợp:

1. **Sai method với một URL đã được đăng ký**: tầng HTTP có thể trả `405 Method Not Allowed`.
2. **Không tìm thấy URL/route nào tương ứng**, ví dụ composition không được công bố: có thể trả `404 Not Found`.

Trong SCF, handler mapping, function filtering, root/fallback, web path và version cụ thể có thể ảnh hưởng status. **Không tự cam kết** rằng tất cả request không được liệt kê sẽ có đúng 404 hoặc 405. Điều cần chứng minh là: **function không bị thực thi qua method/route bị cấm**.

Ví dụ cần thử:

```bash
# quote được liệt kê cho POST, không phải PUT.
curl -i -X PUT 'http://localhost:8080/quote' \
  -H 'Content-Type: application/json' \
  --data '{"sku":"BOOK-001","quantity":2}'

# replaceStock được liệt kê cho PUT, không phải POST.
curl -i -X POST 'http://localhost:8080/replaceStock' \
  -H 'Content-Type: application/json' \
  --data '{"sku":"BOOK-001","quantity":50}'

# deleteById được liệt kê cho DELETE, không phải POST.
curl -i -X POST 'http://localhost:8080/deleteById' \
  -H 'Content-Type: text/plain' --data 'BOOK-001'

# Một bean nội bộ không được đưa vào bất kỳ danh sách method nào.
curl -i -X POST 'http://localhost:8080/internalEcho' \
  -H 'Content-Type: text/plain' --data 'hello'
```

Nếu những request này vẫn chạy, phải tìm **route khác hoặc cấu hình không đúng**. Đặc biệt, không dựa vào một body lỗi HTTP để suy ra có hay không có side effect; với thao tác ghi/xóa, cần quan sát log/test double/database trong môi trường kiểm thử.

## 13. HTTP method không tự thực thi ngữ nghĩa REST

Việc đặt tên property `POST`, `PUT`, `DELETE` giúp route theo method, nhưng **không biến function thành một REST controller đầy đủ**.

| Ngữ nghĩa HTTP | Điều mong đợi ở thiết kế API | Điều SCF method mapping thực hiện |
| --- | --- | --- |
| GET | Đọc dữ liệu, không thay đổi trạng thái theo ý nghĩa safe | Chọn function cho GET; không kiểm tra code có side effect hay không |
| POST | Xử lý/tạo thao tác theo hợp đồng API | Gọi function được ánh xạ cho POST |
| PUT | Thay thế theo quy tắc idempotent | Gọi function được ánh xạ cho PUT; không tự tạo idempotency |
| DELETE | Xóa hoặc yêu cầu xóa tài nguyên | Chọn Consumer/function cho DELETE; không tự xóa database |
| OPTIONS/HEAD | Metadata về endpoint, giao thức hoặc behavior HTTP | Phụ thuộc handler web; không nên tự coi tất cả đều được cấu hình qua cùng property |
| PATCH | Cập nhật từng phần | Cần kiểm tra khả năng SCF adapter hoặc dùng controller/router phù hợp |

Nếu API cần `201 Created`, `409 Conflict`, `ETag`, `If-Match`, kiểm tra quyền theo path resource và JSON error response riêng, có thể giữ logic trong functional bean nhưng dùng Spring MVC/WebFlux làm HTTP boundary.

### Tính idempotent và retry

Chẳng hạn `PUT /replaceStock` bị client gửi hai lần sau timeout. Property GET/POST/PUT không tự ngăn xử lý hai lần, không cung cấp **idempotency key** và cũng không bảo đảm transaction đã commit. Cần thiết kế layer nghiệp vụ phù hợp, kiểm thử cùng database/broker và xử lý retry rõ ràng.

### Authorization là chuyện khác

Method-specific mapping **không** phải quy tắc phân quyền. Nó không chứng minh user có quyền gọi `DELETE /deleteById`, cũng không bảo vệ bean được gọi qua controller khác, FunctionCatalog hoặc adapter sự kiện. Với production, cần authentication, authorization, kiểm soát header routing và giới hạn payload tại Spring Security/API gateway.

## 14. Bảo mật khi có functionRouter và routing headers

SCF còn có `functionRouter`, cho phép chọn hàm đích theo application property hoặc message headers trong những tình huống được hỗ trợ. Tài liệu SCF nêu rằng web adapter có thể chuyển HTTP headers thành Spring `MessageHeaders`, bao gồm header routing như `spring.cloud.function.definition` nếu được cung cấp.

Vì vậy cần phân biệt:

- **Method mapping:** `spring.cloud.function.http.POST=quote` lựa chọn những function được HTTP adapter ánh xạ theo POST.
- **Message routing:** `functionRouter` có thể quyết định hàm đích bên trong một message.
- **Authorization:** Spring Security hoặc gateway xác định **ai** được gọi route nào.

Khi cho phép request bên ngoài đi tới router động, cần thiết kế allowlist đích, loại bỏ/tin cậy đúng những routing headers được phép, và kiểm thử request cố ý chọn một function nội bộ. **Không coi danh sách property HTTP method là hệ thống kiểm soát quyền**.

## 15. Bộ kiểm thử tích hợp đề xuất

### 15.1. Kiểm thử các method hợp lệ

```bash
# GET Supplier.
curl -i 'http://localhost:8080/status' \
  -H 'Accept: application/json'

# GET Function với path item.
curl -i 'http://localhost:8080/uppercase/hello' \
  -H 'Accept: text/plain'

# POST composition.
curl -i -X POST 'http://localhost:8080/normalize,uppercase' \
  -H 'Content-Type: text/plain' \
  -H 'Accept: text/plain' --data '  hello  '

# POST DTO.
curl -i -X POST 'http://localhost:8080/quote' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"sku":"BOOK-001","quantity":2}'

# PUT DTO.
curl -i -X PUT 'http://localhost:8080/replaceStock' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"sku":"BOOK-001","quantity":50}'

# DELETE Consumer (body text/plain).
curl -i -X DELETE 'http://localhost:8080/deleteById' \
  -H 'Content-Type: text/plain' --data 'BOOK-001'
```

### 15.2. Ma trận test

| Trường hợp | Kỳ vọng cần xác minh |
| --- | --- |
| `GET /status` | Status 200, JSON có `state=READY` |
| `GET /uppercase/hello` | Status 200, body `HELLO` |
| `POST /normalize,uppercase` | Status 200, body `HELLO` |
| `POST /quote` | Status 200, JSON có `totalPrice=240000` |
| `PUT /replaceStock` | Status 200, kết quả mô phỏng đúng |
| `DELETE /deleteById` | Status 204, response không có body; console ghi lệnh mô phỏng |
| `PUT /quote` | Không thực thi quote qua PUT |
| `POST /replaceStock` | Không thực thi replaceStock qua POST |
| `POST /deleteById` | Không thực thi deleteById qua POST |
| `POST /internalEcho` | Không thực thi bean nội bộ qua HTTP |

Với request sai method, **ghi lại status thực tế** thay vì cố định trước `404` hay `405`. Nếu có side effect, dùng spy/mock hoặc dữ liệu thử nghiệm để xác minh function bị cấm **không chạy**.

### 15.3. Vì sao cần test HTTP thực?

Test trực tiếp:

```java
String result = uppercase().apply("hello");
```

chỉ chứng minh logic Java trả `HELLO`, **không chứng minh POST bị hạn chế hay GET được ánh xạ**. Cần integration test qua `MockMvc` (MVC), `WebTestClient` (WebFlux) hoặc HTTP client thích hợp với runtime của dự án, bao gồm cả thử qua API gateway nếu có.

## 16. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `POST /quote` không chạy | Config method chưa có hiệu lực hoặc tên bean sai | Xác nhận `spring.cloud.function.http.POST` và catalog |
| `POST /uppercase` không chạy | POST chỉ công bố composition `normalize\|uppercase`, không phải uppercase đơn | Gọi `/normalize,uppercase` hoặc thêm uppercase nếu muốn xuất |
| `GET /uppercase` thất bại | Function GET cần path item | Gọi `GET /uppercase/{item}` |
| DELETE không có response body | Adapter trả `204 No Content` | Không parse body JSON khi nhận 204 |
| DELETE với body bị gateway chặn | Gateway/client không xử lý body DELETE như dự kiến | Thiết kế controller/resource path riêng |
| PUT được gọi nhiều lần và tạo side effect trùng | Code không idempotent | Thiết kế nghiệp vụ, retry và idempotency |
| Property không có hiệu lực | Environment/profile/CLI ghi đè hoặc cấu hình sai tên | Kiểm tra property source hiệu lực |
| Chuỗi `normalize\|uppercase;quote` bị shell tách | Chưa quote dấu pipe/chấm phẩy | Quote toàn bộ đối số |
| `404` hay `405` không đúng dự kiến | Cách route được Spring web adapter thực thi khác hoặc có handler khác | Kiểm tra endpoint mappings, log và runtime |
| Composition vẫn gọi được ngoài method mong muốn | Có definition fallback, header router hoặc controller khác | Test route thực, kiểm soát routing, security |
| Sai `Content-Type` | Body JSON nhưng khai báo text hoặc ngược lại | Gửi `application/json` / `text/plain` đúng kiểu |
| API cần `201`, `409`, `PATCH` | SCF web adapter quá đơn giản cho HTTP contract | Dùng MVC/WebFlux controller/router gọi function |

### Quy trình chẩn đoán

1. Kiểm tra functional bean được đăng ký trong `FunctionCatalog` với tên và kiểu input/output đúng.
2. Đọc **giá trị hiệu lực** của các property `spring.cloud.function.http.GET`, `POST`, `PUT`, `DELETE`.
3. Xác định có `spring.cloud.function.definition`, `web.path`, controller hoặc gateway rewrite nào ảnh hưởng route không.
4. Đối chiếu method + path + `Content-Type` + `Accept`.
5. Gọi `curl -i` tới cả trường hợp cho phép và không cho phép.
6. Kiểm tra side effect/log; xác minh method sai không kích hoạt logic.
7. Áp dụng security/authorization độc lập với phương thức lọc route.

## 17. Bài tập tự luyện

1. Với `spring.cloud.function.http.POST=foo;bar`, có bao nhiêu function được liệt kê cho POST? Dấu `;` có ghép chúng không?
2. Viết cấu hình để GET chỉ gọi `status`, POST chỉ gọi `quote`, PUT chỉ gọi `replaceStock` và DELETE chỉ gọi `deleteById`.
3. Giải thích vì sao `spring.cloud.function.http.POST=normalize|uppercase;quote` có **hai mục** chứ không phải ba function độc lập.
4. So sánh `POST /normalize,uppercase` với `POST /uppercase` trong cấu hình mục 4.
5. Vì sao GET cho `uppercase` dùng `/uppercase/{item}` thay vì tự bind một JSON DTO từ query?
6. Khi `PUT /replaceStock` trả 200, có thể kết luận đã cập nhật database không? Vì sao?
7. Nếu client gửi DELETE với body và nhận 204, response body có thể parse JSON không? Những vấn đề tương thích nào cần xét?
8. Phân biệt `spring.cloud.function.http.POST`, `spring.cloud.function.definition` và `spring.cloud.function.web.path`.
9. Tại sao 404 và 405 có thể đều xuất hiện trong các ca sai method/route? Bạn nên kiểm tra thêm điều gì?
10. Đề xuất một bộ test để chứng minh `quote` **không bị gọi qua PUT**, kể cả khi request có JSON hợp lệ.
11. Cấu hình API sau gateway tại `/api/functions`: viết lại những URL cho GET, POST, PUT, DELETE.
12. Một ứng dụng dùng `functionRouter` cùng HTTP headers routing. Cần thêm lớp bảo vệ gì ngoài method-specific mapping?
13. Nếu product API yêu cầu `PATCH /stocks/{sku}` và `409 Conflict`, tại sao một controller/router riêng có thể phù hợp hơn?

## Tài liệu tham khảo chính thức

- [Spring Cloud Function — Standalone Web Applications](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/standalone-web-applications.html): bảng HTTP method, mục **CRUD REST with Spring Cloud Function**, ví dụ `spring.cloud.function.http.GET`/`POST`/`DELETE`, dấu `;` và `|`.
- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): `Supplier`, `Function`, `Consumer`, `FunctionCatalog`, composition và function routing.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): properties, YAML, biến môi trường và command-line arguments.
- [Spring Framework — Mapping Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html): dùng HTTP controller khi cần route/method/status code phức tạp.
- [HTTP Semantics — RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html): ngữ nghĩa GET/POST/PUT/DELETE, idempotency và các status HTTP.

> **Ghi nhớ:** `spring.cloud.function.http.<METHOD>` chọn những hàm hoặc composition được **SCF HTTP adapter ánh xạ cho từng HTTP method**. Dấu `;` liệt kê các mục; `|` ghép các hàm theo thứ tự; URL có thể gọi composition bằng dấu phẩy. Cấu hình này giúp xây dựng HTTP contract rõ ràng hơn nhưng **không thay thế validation, authorization, idempotency hoặc REST controller khi cần hợp đồng phức tạp**.
