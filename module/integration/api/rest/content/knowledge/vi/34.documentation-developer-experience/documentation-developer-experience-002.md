# Hướng dẫn bắt đầu với yêu cầu và phản hồi có thể chạy lại

Một tài liệu REST API tốt phải trả lời được câu hỏi: **“Tôi có thể gửi yêu cầu đầu tiên và biết chắc kết quả đúng là gì không?”**. Một trang chỉ liệt kê endpoint mà không nêu môi trường, cách xác thực, request copy được và response mẫu sẽ khiến người tích hợp phải đoán. Ngược lại, một hướng dẫn bắt đầu (*quickstart*) có thể chạy lại cho phép người học tự xác nhận kết nối, hiểu hợp đồng dữ liệu, phân biệt lỗi client/server và phát hiện thay đổi API sớm.

Bài học thuộc chương **Tài liệu và trải nghiệm** của module `INTEGRATION_API_REST`. Ta sử dụng resource, URI, phương thức/mã trạng thái HTTP và hợp đồng request/response với ví dụ Java/Spring Boot. Các nguyên tắc áp dụng được cho framework REST khác.

Sau bài học, bạn có thể:

- Nhận diện các thành phần cần có trong quickstart tự chứa và kiểm chứng được.
- Chạy request `GET`/`POST` bằng `curl`, đối chiếu status, header và JSON body; tái hiện các lỗi `400`, `404`, `409` và cache `304`.
- Dùng fixture, idempotency key và script để tái chạy ví dụ mà không tạo tác dụng phụ không kiểm soát.
- Gắn ví dụ với OpenAPI, kiểm thử API và quy trình cập nhật tài liệu.

## 1. Thế nào là yêu cầu và phản hồi “có thể chạy lại”?

Ba tính chất cần phân biệt:

- **Chạy được (runnable):** có server hoặc sandbox truy cập được và lệnh HTTP có thể thực thi.
- **Lặp lại được (reproducible):** biết trạng thái đầu vào; cùng điều kiện dẫn đến kết quả có thể đối chiếu.
- **Kiểm chứng được (verifiable):** xác định rõ status, header và trường JSON nào là hợp đồng cần kiểm tra.

| Thành phần quickstart | Thông tin cần có | Thiếu sẽ gây ra |
| --- | --- | --- |
| Môi trường | Base URL, version, cách khởi động server, dữ liệu mẫu | Request gửi sai host, route hoặc gọi dữ liệu không tồn tại |
| Công cụ | Java/Maven cho demo; `curl`, bash hoặc PowerShell | Copy lệnh nhưng shell không hiểu cú pháp |
| Auth | Demo có cần token không; ở production lấy quyền gì | `401/403` hoặc rò rỉ secret trong tài liệu |
| Request | Method, URI, query, header, body, loại nội dung | `400/415` vì sai dữ liệu hoặc `Content-Type` |
| Response | Status, header quan trọng, body, nghĩa từng trường | Không biết thành công có đúng hợp đồng không |
| Lỗi | Ví dụ `4xx` với cách xử lý | Client không phân biệt lỗi hợp đồng và lỗi dịch vụ |
| Chạy lại | Fixture, ID/key, cách reset state, script test | Chạy lần hai ra kết quả khác không giải thích được |

**Không nên so từng byte của response**: `Date`, `traceId`, ID sinh ngẫu nhiên, thứ tự JSON property hay header do proxy thêm có thể thay đổi. Chỉ so giá trị động nếu chúng thuộc fixture hoặc hợp đồng được cố định có chủ ý.

## 2. Hợp đồng của API demo

Ta xây dựng API cục bộ ở `http://127.0.0.1:8080`. Fixture duy nhất là sản phẩm `42`: “Bình giữ nhiệt”, giá `190000` VND. Các endpoint:

| Method | URI | Thành công / lỗi | Ý nghĩa |
| --- | --- | --- | --- |
| `GET` | `/v1/products/42` | `200`; `304` nếu có ETag phù hợp | Đọc sản phẩm và cache có điều kiện |
| `POST` | `/v1/orders` | `201`; `400` dữ liệu sai; `409` key xung đột | Tạo đơn có chống tạo trùng |
| `GET` | `/v1/orders/{id}` | `200` hoặc `404` | Xem đơn vừa tạo |
| `GET` | `/v1/products/999` | `404` | Resource không tồn tại |

Quy tắc hợp đồng:

- JSON được trao đổi qua `Content-Type: application/json` và `Accept: application/json`.
- `productId` là **chuỗi** `"42"`, `quantity` là số nguyên từ 1 đến 10.
- `POST /v1/orders` yêu cầu `Idempotency-Key`; gửi lại cùng key **và cùng payload** trả về cùng đơn hàng.
- Dùng lại key với payload khác trả `409 Conflict`; endpoint demo trả `400 Bad Request` nếu thiếu key hoặc dữ liệu không hợp lệ.
- Sau `201 Created`, header `Location` chỉ đường dẫn của resource mới.
- Các lỗi chủ động tạo dùng `application/problem+json` với các trường `type`, `title`, `status`, `detail`.

API demo không yêu cầu auth và chỉ lưu dữ liệu **trong bộ nhớ của một tiến trình**, giúp tái hiện đơn giản: restart server sẽ xóa dữ liệu đơn hàng, đồng thời reset bộ đếm ID. Đây là một fixture học tập, không phải kiến trúc lưu idempotency phù hợp production.

## 3. Dựng server Spring Boot để có mục tiêu thực sự chạy được

### 3.1. Công cụ và cấu trúc file

Cần **Java 21**, **Maven 3.9+**, `curl` và kết nối mạng để Maven tải dependency lần đầu. Ví dụ dùng Spring Boot **3.5.6**. Tạo một thư mục `rest-quickstart` với cấu trúc:

```text
rest-quickstart/
├── pom.xml
└── src/main/java/dev/example/quickstart/QuickstartApplication.java
```

Nội dung `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>
    <groupId>dev.example</groupId>
    <artifactId>rest-quickstart</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Lưu đoạn Java dưới đây ở đúng package path. Để thuận tiện, `@SpringBootApplication` và `@RestController` nằm trong cùng một file:

```java
package dev.example.quickstart;

import java.net.URI;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@SpringBootApplication
public class QuickstartApplication {
    public static void main(String[] args) {
        SpringApplication.run(QuickstartApplication.class, args);
    }
}

@RestController
@RequestMapping("/v1")
class DemoController {
    private final AtomicInteger nextId = new AtomicInteger();
    private final Map<String, Order> orders = new ConcurrentHashMap<>();
    private final Map<String, Saved> keys = new ConcurrentHashMap<>();

    record Product(String id, String name, long priceVnd) {}
    record CreateOrder(String productId, int quantity) {}
    record Order(String id, String productId, int quantity, String status) {}
    record Saved(CreateOrder input, Order order) {}

    @GetMapping("/products/{id}")
    ResponseEntity<?> product(
            @PathVariable String id,
            @RequestHeader(value = HttpHeaders.IF_NONE_MATCH, required = false)
            String ifNoneMatch) {
        if (!"42".equals(id)) {
            return error(HttpStatus.NOT_FOUND, "Product not found",
                    "No product for id " + id);
        }

        String etag = "\"product-42-v1\"";
        if (etag.equals(ifNoneMatch)) {
            return ResponseEntity.status(HttpStatus.NOT_MODIFIED)
                    .eTag(etag).build();
        }
        return ResponseEntity.ok()
                .eTag(etag)
                .body(new Product("42", "Bình giữ nhiệt", 190000));
    }

    @PostMapping("/orders")
    synchronized ResponseEntity<?> createOrder(
            @RequestHeader(value = "Idempotency-Key", required = false)
            String key,
            @RequestBody(required = false) CreateOrder input) {
        if (key == null || key.isBlank()) {
            return error(HttpStatus.BAD_REQUEST, "Missing idempotency key",
                    "Provide a non-empty Idempotency-Key header");
        }
        if (input == null || !"42".equals(input.productId())
                || input.quantity() < 1 || input.quantity() > 10) {
            return error(HttpStatus.BAD_REQUEST, "Invalid order",
                    "productId must be 42; quantity must be 1..10");
        }

        Saved old = keys.get(key);
        if (old != null) {
            if (!old.input().equals(input)) {
                return error(HttpStatus.CONFLICT, "Key reused",
                        "The same key was used with a different payload");
            }
            return created(old.order());
        }

        String id = String.format("ord-%03d", nextId.incrementAndGet());
        Order order = new Order(id, input.productId(),
                input.quantity(), "CREATED");
        orders.put(id, order);
        keys.put(key, new Saved(input, order));
        return created(order);
    }

    @GetMapping("/orders/{id}")
    ResponseEntity<?> order(@PathVariable String id) {
        Order found = orders.get(id);
        return found == null
                ? error(HttpStatus.NOT_FOUND, "Order not found",
                        "No order for id " + id)
                : ResponseEntity.ok(found);
    }

    private ResponseEntity<Order> created(Order order) {
        return ResponseEntity.created(
                URI.create("/v1/orders/" + order.id())).body(order);
    }

    private ResponseEntity<ProblemDetail> error(
            HttpStatus status, String title, String detail) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(status, detail);
        problem.setTitle(title);
        return ResponseEntity.status(status)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(problem);
    }
}
```

Đây là implementation tối giản để người học kiểm tra **hợp đồng HTTP**. `synchronized` chỉ điều phối thao tác tạo đơn trong một JVM; `Map` mất dữ liệu khi restart. Đoạn so sánh `If-None-Match` đơn giản, chưa hỗ trợ toàn bộ cú pháp và ngữ nghĩa ETag. Production cần transaction, unique constraint, khóa idempotency bền vững qua nhiều replica, xác thực/phân quyền, validation và cache semantics đầy đủ.

Khởi động trong thư mục `rest-quickstart`:

```bash
mvn spring-boot:run -Dspring-boot.run.arguments=--server.address=127.0.0.1
```

Khi log báo server nghe trên cổng `8080`, giữ terminal đó mở. Tham số địa chỉ loopback giới hạn API demo không bảo vệ bởi auth chỉ truy cập từ máy hiện tại. Nếu cổng `8080` bận, chạy với `--server.port=8081` và thay base URL ở các ví dụ tiếp theo.

## 4. Gửi yêu cầu GET và kiểm tra ETag

Kiểm tra công cụ:

```bash
java -version
mvn -version
curl --version
```

Trên bash (Linux/macOS, Git Bash, WSL):

```bash
BASE_URL=http://127.0.0.1:8080
curl -i -sS -H 'Accept: application/json' "$BASE_URL/v1/products/42"
```

Trên PowerShell, dùng `curl.exe` để tránh khác biệt với bí danh `curl` trên một số phiên bản Windows:

```powershell
$baseUrl = "http://127.0.0.1:8080"
curl.exe -i -sS -H "Accept: application/json" "$baseUrl/v1/products/42"
```

Response minh họa (các header không liên quan được lược bớt):

```http
HTTP/1.1 200
Content-Type: application/json
ETag: "product-42-v1"

{"id":"42","name":"Bình giữ nhiệt","priceVnd":190000}
```

Hãy kiểm tra status `200`, `Content-Type`, `id` là chuỗi, `priceVnd` là số và `ETag`. Không yêu cầu thứ tự property/header giống hệt ví dụ.

Tiếp tục thử cache có điều kiện:

```bash
curl -i -sS -H 'If-None-Match: "product-42-v1"' \
  "$BASE_URL/v1/products/42"
```

Kỳ vọng status `304 Not Modified`, header `ETag: "product-42-v1"` và **không có response body**. Trên API thực, client nên dùng ETag đã đọc từ response trước, không hardcode khi dữ liệu có thể thay đổi. Quy tắc cache còn chịu ảnh hưởng bởi `Cache-Control` và middleware.

## 5. POST tạo đơn và GET đọc lại resource

Để quan sát chính xác ID `ord-001`, khởi động lại server trước bước POST đầu tiên nếu đã tạo đơn ở những lần thử trước:

```bash
curl -i -sS -X POST "$BASE_URL/v1/orders" \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -H 'Idempotency-Key: quickstart-order-001' \
  --data-raw '{"productId":"42","quantity":2}'
```

Kỳ vọng khi đây là đơn đầu tiên:

```http
HTTP/1.1 201
Location: /v1/orders/ord-001
Content-Type: application/json

{"id":"ord-001","productId":"42","quantity":2,"status":"CREATED"}
```

`201 Created` có nghĩa server đã tạo resource; `Location` cung cấp URI của resource. `Idempotency-Key` là header do **API demo yêu cầu**, không phải header tự động áp dụng cho mọi REST API. Request chứa `productId`/`quantity`; response bổ sung `id`/`status`.

Xác minh đơn đã được tạo:

```bash
curl -i -sS "$BASE_URL/v1/orders/ord-001"
```

Kỳ vọng `200 OK` với cùng đơn hàng. Với hệ thống thực có DB và replica, cần mô tả tính nhất quán đọc sau ghi theo hợp đồng.

Gửi lại đúng request và khóa:

```bash
curl -i -sS -X POST "$BASE_URL/v1/orders" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: quickstart-order-001' \
  --data-raw '{"productId":"42","quantity":2}'
```

Demo trả cùng `201`, cùng `Location` và body đơn cũ; **không tạo thêm đơn**. API khác có thể quy định `200` hoặc trả nguyên phản hồi trước đó; hãy tài liệu hóa nhất quán lựa chọn của mình. Với production, idempotency cần có phạm vi theo tenant/người gọi, so khớp payload, xử lý đồng thời, lưu trữ bền vững và chính sách TTL.

## 6. Phản hồi lỗi có thể tái hiện

Tài liệu nên hướng dẫn tạo lỗi có chủ đích để người tích hợp biết phân biệt sai URI, sai payload và xung đột nghiệp vụ.

### 6.1. Resource không tồn tại: 404

```bash
curl -i -sS "$BASE_URL/v1/products/999"
```

Response minh họa:

```http
HTTP/1.1 404
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Product not found",
  "status": 404,
  "detail": "No product for id 999"
}
```

### 6.2. Payload không hợp lệ: 400

```bash
curl -i -sS -X POST "$BASE_URL/v1/orders" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: bad-quantity-001' \
  --data-raw '{"productId":"42","quantity":0}'
```

Kỳ vọng `400 Bad Request`, `Content-Type: application/problem+json` và `title` là `"Invalid order"`. Một API khác có thể chọn `422 Unprocessable Content` cho lỗi ngữ nghĩa nếu hợp đồng quy định rõ.

### 6.3. Cùng key nhưng payload khác: 409

Sau khi đã tạo đơn ở mục 5, chạy:

```bash
curl -i -sS -X POST "$BASE_URL/v1/orders" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: quickstart-order-001' \
  --data-raw '{"productId":"42","quantity":3}'
```

Kỳ vọng `409 Conflict`, `title` là `"Key reused"`. **Điều kiện trước** là key đã được dùng để tạo đơn với `quantity: 2`. Nếu khởi động lại server và chạy riêng request này, nó sẽ trả `201`. Việc nêu thứ tự thực hiện hoặc setup fixture là yếu tố quan trọng để ví dụ thực sự lặp lại được.

Problem Details theo RFC 9457 dùng các trường thông dụng `type`, `title`, `status`, `detail` và có thể thêm `instance`. Khi kiểm thử, so sánh các giá trị thuộc hợp đồng; không dựa vào thứ tự JSON hoặc giá trị động như `traceId`. Với API có xác thực, cũng cần minh họa `401 Unauthorized` (chưa xác thực hợp lệ) và `403 Forbidden` (đã xác thực nhưng không đủ quyền).

| Tình huống | Cách xử lý cho client |
| --- | --- |
| `400` body sai | Sửa request trước khi gửi lại |
| `404` | Kiểm tra URI/resource và tính nhất quán dữ liệu |
| `409` idempotency key sai | Giữ payload ban đầu hoặc dùng key mới cho ý định mới |
| `429`/`503` | Retry có giới hạn, backoff + jitter và tôn trọng `Retry-After` khi có |
| Timeout/reset khi `POST` | Chỉ retry an toàn nếu API thiết kế idempotency; server có thể đã commit |

## 7. Smoke test kiểm tra nhanh hợp đồng

Sau khi server đang hoạt động, lưu đoạn dưới đây thành `smoke.sh`. Script dùng bash + curl, kiểm tra status và tính ổn định của response khi replay. Nó dùng key riêng `smoke-order-001` nên không phụ thuộc việc đã chạy mục 5 hay chưa.

```bash
#!/usr/bin/env bash
set -eu

BASE_URL="$1"
get_status() {
  curl -sS -o /dev/null -w '%{http_code}' "$@"
}

test "$(get_status "$BASE_URL/v1/products/42")" = "200"
test "$(get_status -H 'If-None-Match: "product-42-v1"' \
  "$BASE_URL/v1/products/42")" = "304"
test "$(get_status "$BASE_URL/v1/products/999")" = "404"

order1=$(curl -fsS -X POST "$BASE_URL/v1/orders" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: smoke-order-001' \
  --data-raw '{"productId":"42","quantity":2}')
order2=$(curl -fsS -X POST "$BASE_URL/v1/orders" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: smoke-order-001' \
  --data-raw '{"productId":"42","quantity":2}')
test "$order1" = "$order2"

test "$(get_status -X POST "$BASE_URL/v1/orders" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: smoke-invalid-001' \
  --data-raw '{"productId":"42","quantity":0}')" = "400"
test "$(get_status -X POST "$BASE_URL/v1/orders" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: smoke-order-001' \
  --data-raw '{"productId":"42","quantity":3}')" = "409"

printf 'Smoke test PASS\n'
```

Chạy trong bash:

```bash
bash smoke.sh http://127.0.0.1:8080
```

Khi assertion `test` sai, `set -e` làm script dừng với exit code khác 0. `curl -f` khiến hai POST thành công thất bại nếu server trả HTTP 4xx/5xx. Chạy lại script trên cùng server không tạo thêm đơn: key và payload giữ nguyên. Sau restart, ID reset nhưng script vẫn kiểm tra được hợp đồng.

**Giới hạn:** so sánh nguyên chuỗi body chỉ hợp lý cho demo đã cố định cách serialize. Trong CI production, dùng JSON parser/JSON Schema hoặc contract-testing tool để xác nhận `Content-Type`, `Location`, schema, status và field quan trọng, thay vì yêu cầu toàn bộ response trùng nhau từng byte. Không chạy script ghi dữ liệu trên production trừ khi có sandbox/fixture được cấp riêng và quyền thích hợp.

## 8. Liên kết quickstart với OpenAPI

Quickstart mô tả hành trình tối thiểu của người sử dụng; **OpenAPI** mô tả hợp đồng máy đọc được. Hai phần phải nhất quán về URI, method, schema và response. Trích đoạn OpenAPI 3.1 cho GET sản phẩm:

```yaml
openapi: 3.1.0
info:
  title: REST Quickstart Demo
  version: 1.0.0
servers:
  - url: http://127.0.0.1:8080
paths:
  /v1/products/{id}:
    get:
      summary: Đọc sản phẩm
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
          example: "42"
        - name: If-None-Match
          in: header
          required: false
          schema:
            type: string
      responses:
        "200":
          description: Sản phẩm tìm thấy
          content:
            application/json:
              schema:
                type: object
                required: [id, name, priceVnd]
                properties:
                  id: { type: string }
                  name: { type: string }
                  priceVnd: { type: integer, format: int64 }
              example:
                id: "42"
                name: Bình giữ nhiệt
                priceVnd: 190000
        "304":
          description: Representation không đổi theo ETag
        "404":
          description: Không tìm thấy sản phẩm
          content:
            application/problem+json:
              schema:
                type: object
                properties:
                  type: { type: string }
                  title: { type: string }
                  status: { type: integer }
                  detail: { type: string }
```

Trong OpenAPI chính thức còn cần mô tả `POST /v1/orders`: header `Idempotency-Key` bắt buộc, body `CreateOrder`, `201` có `Location`, `400`/`409` dạng Problem Details. Khi bổ sung phân trang, cần chỉ rõ `limit`, `cursor`, `nextCursor` hoặc `Link` và cách đi sang trang kế tiếp. Khi bổ sung auth, khai báo `securitySchemes` cùng scope/quyền của operation.

Để tài liệu không lệch code, mỗi thay đổi API nên cập nhật **implementation, OpenAPI, request mẫu, response mẫu và test** trong cùng một PR. CI có thể sinh client từ spec, chạy contract test, chạy smoke test trên server staging rồi kiểm tra thay đổi không tương thích trước khi phát hành version mới.

### API cần xác thực

Ví dụ local không bật auth để tập trung vào HTTP. Tài liệu production phải hướng dẫn lấy token sandbox, yêu cầu quyền tối thiểu, thời gian hết hạn và cách xử lý `401/403`. Khi đã có token qua cách cấp phát được cho phép:

```bash
# API_BASE_URL và API_TOKEN được khai báo trong môi trường thử nghiệm.
curl -i -sS "$API_BASE_URL/v1/products/42" \
  -H "Authorization: Bearer $API_TOKEN" \
  -H 'Accept: application/json'
```

Không commit token thật vào source, request mẫu, ảnh chụp hay log. Trong trình duyệt, CORS, cookie/SameSite và CSRF còn có thể ảnh hưởng việc gọi API; ví dụ `curl` thành công chưa chứng minh frontend đã được cấu hình CORS đúng.

## 9. Khi ví dụ không chạy: quy trình chẩn đoán

| Triệu chứng | Kiểm tra | Cách khắc phục |
| --- | --- | --- |
| `curl: (7) Failed to connect` | Server, cổng, host, log startup | Chạy server và sửa base URL |
| `404` ngoài dự kiến | `/v1`, route, ID fixture | Dùng đúng URI và dữ liệu mẫu |
| `400` với POST | JSON, `Content-Type`, kiểu và giá trị field | So với hợp đồng request |
| `401`/`403` trong API có auth | Token, scope, quyền resource | Kiểm tra auth và phân quyền |
| `409` khi replay | Key đã dùng với payload khác | Chỉ replay cùng payload hoặc dùng key mới |
| Không nhận `304` | ETag hoặc proxy thay đổi | Lấy ETag từ GET đầu tiên |
| `429`/`503` | Rate limit, quá tải, bảo trì | Đợi và retry có giới hạn nếu an toàn |
| Body khác hình minh họa | Version, fixture, dữ liệu động | So schema và trường ổn định |

Trước khi xuất bản quickstart, người biên tập nên thử từ môi trường sạch: cài đúng công cụ, khởi động server, gửi yêu cầu theo đúng thứ tự, kiểm tra response, lặp lại key, chạy smoke test và mô tả lỗi gặp phải. Ví dụ chỉ đáng tin khi **một người khác có thể copy lệnh, dự đoán kết quả và xác định sai ở đâu**.

## 10. Bài tập thực hành

**Bài tập 1 — Viết quickstart đầy đủ.** Một trang chỉ có câu “POST /v1/orders, body `{"productId":42}`”. Hãy bổ sung base URL, method, header, schema, JSON đúng kiểu, response `201`, `Location` và request GET để xác minh đơn mới.

**Bài tập 2 — Lặp lại có kiểm soát.** Chạy mục 5 hai lần với cùng key/payload, sau đó thay quantity thành 3 nhưng giữ key. Ghi status, body và số đơn đã tạo; giải thích vì sao production cần lưu idempotency key bền vững giữa nhiều Pod.

**Bài tập 3 — Negative tests.** Dùng curl tái hiện `400`, `404`, `409` và viết assertion đối chiếu status, `Content-Type` cùng các trường ổn định trong Problem Details. Không so trace ID hay thứ tự JSON.

**Bài tập 4 — OpenAPI.** Mở rộng mục 8 cho `POST /v1/orders`, mô tả `requestBody`, `Idempotency-Key`, quantity min/max, `201`/`400`/`409` và ví dụ response. Đề xuất bước CI để phát hiện spec lệch implementation.

**Bài tập 5 — Hai shell.** Gọi GET/POST bằng bash/curl và PowerShell/`curl.exe`. Ghi khác biệt về dấu nháy JSON, biến URL và cách đọc header/status; viết chỉ dẫn để người dùng hai hệ điều hành đều copy được.

**Tiêu chí hoàn thành:** người học có thể tự dựng API demo, gửi và chạy lại request, kiểm chứng status/header/body, giải thích các lỗi và idempotency, chạy smoke test lặp lại an toàn, đồng thời liên kết ví dụ với hợp đồng OpenAPI và bộ kiểm thử API.
