# HTTP method, tính an toàn và tính lặp lại không đổi kết quả

## 1. HTTP method là gì và vì sao cần hiểu đúng?

HTTP là giao thức request/response giữa client và server. Một **HTTP request method** (còn gọi là HTTP verb) diễn đạt *hành động mà client muốn thực hiện đối với tài nguyên đích* (target resource). Trong request sau, method là `GET`, đường dẫn là `/api/books/42`:

```http
GET /api/books/42 HTTP/1.1
Host: example.com
Accept: application/json
```

Trong ứng dụng Spring Web, server có thể ánh xạ method và đường dẫn tới một phương thức controller. Tuy nhiên, ý nghĩa chuẩn của method là một **hợp đồng HTTP** giữa client, server, browser, proxy, cache và các công cụ mạng, không chỉ là lựa chọn annotation cho controller.

Ba câu hỏi cần tách biệt:

1. **Method này định yêu cầu làm gì?** Ví dụ `GET` đọc một biểu diễn của tài nguyên, `PUT` tạo/thay thế trạng thái của tài nguyên đích, `DELETE` yêu cầu loại bỏ các biểu diễn hiện tại của tài nguyên.
2. **Method này có an toàn (safe) không?** Client có đang *yêu cầu* thay đổi trạng thái hay không?
3. **Method này có tính idempotent không?** Lặp lại nhiều request giống hệt nhau có cùng *tác động dự kiến* như gửi một request hay không?

Những câu hỏi này ảnh hưởng trực tiếp đến thiết kế API, retry khi lỗi mạng, cache, crawler, bảo mật và trải nghiệm người dùng.

## 2. Các HTTP method thông dụng

| Method | Ý nghĩa chính | Ví dụ | Safe theo ngữ nghĩa chuẩn? | Idempotent theo ngữ nghĩa chuẩn? |
|---|---|---|---|---|
| `GET` | Lấy biểu diễn hiện tại của tài nguyên | `GET /products/42` | Có | Có |
| `HEAD` | Giống yêu cầu lấy metadata tương ứng với GET nhưng response không chứa body | `HEAD /products/42` | Có | Có |
| `OPTIONS` | Hỏi các tùy chọn giao tiếp được hỗ trợ | `OPTIONS /products/42` | Có | Có |
| `TRACE` | Kiểm tra vòng lặp phản chiếu request dọc đường truyền | `TRACE /diagnostic` | Có | Có |
| `POST` | Yêu cầu tài nguyên đích xử lý dữ liệu theo ngữ nghĩa của chính nó | `POST /orders` | Không | Không được bảo đảm |
| `PUT` | Tạo hoặc thay thế trạng thái tài nguyên ở URI đích bằng biểu diễn gửi lên | `PUT /products/42` | Không | Có |
| `PATCH` | Áp dụng một tập thay đổi lên tài nguyên | `PATCH /products/42` | Không | Không được bảo đảm |
| `DELETE` | Yêu cầu loại bỏ các biểu diễn hiện tại của tài nguyên đích | `DELETE /products/42` | Không | Có |
| `CONNECT` | Thiết lập tunnel tới server đích qua proxy | `CONNECT example.com:443` | Không | Không |

**Lưu ý về phạm vi:** `GET`, `HEAD`, `POST`, `PUT`, `DELETE`, `OPTIONS`, `TRACE`, `CONNECT` được định nghĩa trong RFC 9110; `PATCH` được định nghĩa riêng trong RFC 5789. Phần lớn lập trình ứng dụng Spring Web tập trung vào `GET`, `POST`, `PUT`, `PATCH`, `DELETE`. `OPTIONS` thường xuất hiện khi tìm hiểu CORS. `HEAD` hữu ích để kiểm tra metadata. `TRACE` và `CONNECT` không phải các thao tác CRUD thông thường; nhiều server hạn chế hoặc vô hiệu hóa TRACE vì lý do bảo mật.

Method là **case-sensitive** ở tầng HTTP: `GET` là dạng chuẩn; không giả định `get` tương đương `GET`. Các method cũng không tự quyết định định dạng phản hồi: cùng `GET` có thể nhận HTML, JSON, hình ảnh hoặc một kiểu biểu diễn khác tùy tài nguyên và content negotiation.

## 3. Tính an toàn (safe): client không yêu cầu thay đổi trạng thái

### 3.1. Định nghĩa

Một HTTP method là **safe** khi ngữ nghĩa được định nghĩa cho method đó về bản chất là chỉ đọc: client không yêu cầu và không mong đợi việc áp dụng request sẽ làm thay đổi trạng thái trên origin server. Các method safe được chuẩn HTTP chỉ ra gồm **GET, HEAD, OPTIONS, TRACE**.

Ví dụ đúng với tính safe:

```http
GET /api/products/42 HTTP/1.1
Host: shop.example
```

Client yêu cầu đọc sản phẩm số 42. Tải lại trang, mở liên kết, crawler truy cập hoặc browser prefetch URL này không nên trở thành thao tác mua hàng, trừ tiền, xóa sản phẩm hay gửi email.

Ví dụ **sai về ngữ nghĩa**:

```http
GET /api/orders/42/cancel HTTP/1.1
Host: shop.example
```

Nếu việc đọc URL thực sự hủy đơn, request này đang thực hiện hành động thay đổi nghiệp vụ dù mang method `GET`. Thiết kế đúng hơn là một thao tác không an toàn có xác thực/phân quyền thích hợp, chẳng hạn `POST /api/orders/42/cancellation` hoặc một cập nhật trạng thái được mô hình hóa rõ ràng bằng method phù hợp.

### 3.2. “Safe” không có nghĩa tuyệt đối không phát sinh bất kỳ side effect nào

Server có thể ghi access log, tăng chỉ số giám sát, lưu telemetry hoặc ghi thống kê kỹ thuật khi xử lý `GET`. Điều đó không tự động khiến method trở thành unsafe theo định nghĩa: client **không hề yêu cầu** các side effect nội bộ đó và chúng không nên được coi như một giao dịch nghiệp vụ do người dùng chủ động kích hoạt.

Phân biệt:

- `GET /products/42` ghi log truy cập: thường vẫn hợp với ngữ nghĩa safe.
- `GET /products/42` tự động trừ số lượng tồn kho, thu phí hoặc xóa sản phẩm: vi phạm kỳ vọng safe.
- `GET /products/42?operation=delete` thực sự xóa sản phẩm: tham số query không “biến GET thành POST”; phía server phải ngăn hành động unsafe qua safe method.

**Safe không đồng nghĩa với không cần bảo mật.** `GET` vẫn có thể đọc dữ liệu cá nhân, bí mật hoặc tài nguyên chỉ người có quyền mới được xem. Server phải kiểm tra authentication/authorization tương ứng. URL và query string có thể bị lưu trong lịch sử trình duyệt, log và hệ thống quan sát; không nên đưa token hay mật khẩu vào URL.

### 3.3. Tại sao safe lại quan trọng?

Trình duyệt, công cụ tìm kiếm, proxy và bộ kiểm tra liên kết có thể truy cập `GET` mà không diễn tả ý định làm phát sinh giao dịch. Safe method tạo kỳ vọng để các hệ thống đó truy xuất tài nguyên mà không vô tình gây hại.

Vì vậy, một liên kết HTML như `<a href="/delete-account">...</a>` không được để yêu cầu GET của nó thực sự xóa tài khoản. Thao tác thay đổi trạng thái cần được kích hoạt có chủ đích bằng method phù hợp và cơ chế bảo vệ, đặc biệt khi liên quan đến phiên đăng nhập bằng cookie.

## 4. Tính idempotent: lặp lại cùng request vẫn có cùng tác động dự kiến

### 4.1. Định nghĩa và công thức trực quan

Một method có tính **idempotent** khi *tác động dự kiến trên server* của việc gửi nhiều request giống hệt nhau là như tác động của việc gửi một request. Có thể hình dung phép biến đổi trạng thái là `f`:

```text
f(f(state)) = f(state)
```

Công thức là mô hình khái niệm về tác động dự kiến, **không** có nghĩa mọi byte HTTP response hoặc mọi dòng log sẽ giống nhau, và không bảo đảm các request đồng thời với client khác được cách ly.

Ví dụ một sản phẩm có trạng thái `published=false`:

```http
PUT /api/products/42 HTTP/1.1
Host: shop.example
Content-Type: application/json

{"name":"Java","published":true}
```

Nếu API định nghĩa đây là biểu diễn thay thế đầy đủ và server áp dụng đúng ngữ nghĩa PUT, lặp lại cùng request hai hoặc ba lần đều có kết quả nghiệp vụ sau cùng là sản phẩm 42 có `name="Java"` và `published=true`. Request có thể cập nhật dữ liệu một lần hoặc nhiều lần ở hạ tầng; **tác động người dùng yêu cầu** là giống nhau.

Ngược lại, thao tác tăng số lượng:

```http
POST /api/counters/visits/increment HTTP/1.1
Host: shop.example
```

Nếu mỗi request làm giá trị tăng một đơn vị, thực hiện hai lần sẽ tăng hai đơn vị. Đây là hành động **không idempotent**.

### 4.2. Idempotent không phải “response giống hệt”

Giả sử lần DELETE đầu tiên xóa thành công:

```http
DELETE /api/products/42 HTTP/1.1
Host: shop.example
```

Server có thể trả `204 No Content` cho lần đầu và `404 Not Found` cho lần thứ hai, hoặc trả `204` ở cả hai lần tùy hợp đồng API. Trạng thái đích vẫn là “sản phẩm không còn tồn tại”. Do đó, **DELETE vẫn được chuẩn HTTP định nghĩa là idempotent** dù status code qua mỗi lần gửi có thể khác.

Tương tự, `PUT` có thể trả `201 Created` lần đầu khi tạo tài nguyên và `200 OK` hoặc `204 No Content` ở lần thay thế sau. Không cần ép tất cả response giống nhau để có tính idempotent.

Giống như safe, tính idempotent nói về **tác động dự kiến mà client yêu cầu**. Log, revision history, request counter của hạ tầng hoặc việc theo dõi retry vẫn có thể thay đổi mỗi lần nhận request. Tuy nhiên, nếu endpoint `PUT` bị thiết kế để *mỗi lần gửi đều cộng thêm tiền vào tài khoản* thì nó không đáp ứng ngữ nghĩa idempotent của PUT dù controller vẫn dùng `@PutMapping`.

### 4.3. Safe và idempotent liên hệ thế nào?

- Safe method theo ngữ nghĩa chuẩn cũng idempotent: lặp lại một hành động chỉ đọc không yêu cầu thay đổi trạng thái nghiệp vụ.
- Idempotent **không có nghĩa** safe: `PUT` và `DELETE` làm thay đổi tài nguyên, nhưng lặp lại cùng yêu cầu vẫn đạt cùng tác động dự kiến.
- Unsafe và không được bảo đảm idempotent: `POST`, `PATCH`. Một API cụ thể vẫn **có thể** thiết kế một thao tác POST hoặc PATCH mang tính idempotent với điều kiện/logic rõ ràng, nhưng client không được tự giả định chỉ dựa vào method.
- Idempotency không đồng nghĩa với transaction, exactly-once delivery, atomicity, tránh race condition, hoặc tự động chống ghi đè cập nhật của người khác.

## 5. Phân tích riêng các method quan trọng

### 5.1. GET và HEAD

`GET` lấy biểu diễn tài nguyên hiện tại, không phải lệnh tạo hay thay đổi tài nguyên. Khi API trả JSON, response thành công thường là `200 OK`; tài nguyên không tìm thấy thường là `404 Not Found`. `GET` và `HEAD` có thể tham gia cơ chế HTTP caching theo điều kiện của response và cache policy.

`HEAD` yêu cầu metadata tương ứng với GET nhưng **không có response body**. Header như `Content-Type`, `ETag`, `Last-Modified` có thể giúp client kiểm tra tình trạng tài nguyên mà không tải nội dung. Không nên kỳ vọng mọi header tạo ra bằng GET nhất thiết đều xuất hiện giống hệt trong HEAD; HTTP có ngoại lệ cho một số trường mà giá trị chỉ xác định khi sinh body.

```bash
curl -i http://localhost:8080/api/counters/demo
curl -I http://localhost:8080/api/counters/demo
```

Trong Spring MVC, một mapping `@GetMapping` thông thường cũng hỗ trợ xử lý HEAD thích hợp; khả năng chính xác còn phụ thuộc cấu hình và handler của ứng dụng.

### 5.2. POST

`POST` gửi nội dung để tài nguyên đích xử lý theo ngữ nghĩa của riêng nó. Thường dùng để tạo tài nguyên có ID do server cấp, gửi form, kích hoạt nghiệp vụ, hoặc thêm một sự kiện mới:

```http
POST /api/orders HTTP/1.1
Host: shop.example
Content-Type: application/json

{"productId":42,"quantity":1}
```

Nếu mỗi lần gửi tạo một đơn hàng mới, gửi hai lần có thể tạo **hai đơn**. Khi tạo thành công, server thường phản hồi `201 Created` và `Location: /api/orders/<id>`. Việc một API POST có hỗ trợ chống trùng lặp không phải thuộc tính mặc định của POST.

POST cũng có thể được thiết kế idempotent trong một nghiệp vụ cụ thể, ví dụ bằng mã yêu cầu duy nhất hoặc `Idempotency-Key`; đó là **cam kết triển khai riêng** cần ghi rõ trong tài liệu API.

### 5.3. PUT

`PUT` yêu cầu tạo hoặc **thay thế trạng thái tài nguyên ở URI đích** bằng biểu diễn mà client gửi:

```http
PUT /api/users/42 HTTP/1.1
Host: shop.example
Content-Type: application/json

{"name":"Lan","active":true}
```

Một ứng dụng có thể chỉ cho phép PUT lên tài nguyên đã tồn tại và trả `404` nếu chưa tồn tại; ứng dụng khác có thể cho phép tạo mới ở URI đó theo quy tắc của nó. Nếu đã tạo mới thì `201` là mã thành công thích hợp; nếu thay thế, có thể là `200` hoặc `204`.

Tránh nhầm PUT với phép tăng/lũy kế (`balance += amount`, `stock--`). Gửi lại payload giống hệt phải giữ đúng tác động dự kiến. Nếu API dùng PUT nhưng chỉ cập nhật một vài field, phải tài liệu hóa hợp đồng rõ ràng; về mặt ngữ nghĩa chuẩn PUT là tạo/thay thế biểu diễn đích, còn cập nhật từng phần thường phù hợp với PATCH hơn.

### 5.4. PATCH

`PATCH` gửi **tập chỉ dẫn thay đổi một phần** của tài nguyên. Nội dung thay đổi phụ thuộc media type và hợp đồng API, ví dụ JSON Patch (`application/json-patch+json`) hoặc JSON Merge Patch (`application/merge-patch+json`); một DTO JSON đơn giản dùng trong API riêng không tự động tuân theo hai định dạng chuẩn đó.

Hai kiểu PATCH có tác động khác nhau:

```text
A. Gán giá trị cố định: set active = true
   Gửi hai lần thường vẫn là active = true → có thể idempotent.

B. Tăng số dư: balance = balance + 100
   Gửi hai lần cộng thêm 200 → không idempotent.
```

PATCH **không được bảo đảm idempotent theo định nghĩa chung**; muốn an toàn khi retry phải biết cụ thể thao tác có idempotent không và cần cân nhắc điều kiện phiên bản để tránh xung đột.

### 5.5. DELETE

`DELETE` yêu cầu loại bỏ các biểu diễn hiện tại của tài nguyên đích; ví dụ:

```http
DELETE /api/users/42 HTTP/1.1
Host: shop.example
```

Xóa cùng một tài nguyên nhiều lần vẫn có cùng tác động mong muốn: tài nguyên không còn xuất hiện theo hợp đồng của ứng dụng. DELETE idempotent **không buộc hệ thống phải xóa vật lý ngay lập tức**; soft delete, xử lý bất đồng bộ, audit hoặc ràng buộc nghiệp vụ đều cần được mô tả rõ.

Nếu server chỉ nhận công việc để xử lý về sau, response `202 Accepted` có thể phù hợp. Nếu xóa hoàn tất và không trả body, `204 No Content` thường được dùng.

### 5.6. OPTIONS, TRACE và CONNECT

`OPTIONS` cho biết các lựa chọn giao tiếp được hỗ trợ. Một ứng dụng có thể trả header `Allow` hoặc các header khác. **CORS preflight** là một trường hợp đặc biệt dùng OPTIONS, thường có `Origin` và `Access-Control-Request-Method`, nhưng không phải mọi OPTIONS đều là CORS preflight.

`TRACE` dùng kiểm tra đường truyền theo cơ chế loop-back; nhiều server không bật nó vì rủi ro lộ thông tin request. `CONNECT` chủ yếu dành cho proxy tạo tunnel, không dùng làm phương thức CRUD của controller bình thường.

## 6. Thiết kế API theo resource và method

Một API quản lý sản phẩm có thể có thiết kế sau:

| Nhu cầu nghiệp vụ | Method và URI | Tác động dự kiến |
|---|---|---|
| Xem danh sách sản phẩm | `GET /api/products` | Đọc danh sách |
| Xem sản phẩm cụ thể | `GET /api/products/42` | Đọc sản phẩm 42 |
| Tạo sản phẩm để server cấp ID | `POST /api/products` | Có thể tạo một sản phẩm mới mỗi lần |
| Tạo/thay thế sản phẩm theo ID xác định | `PUT /api/products/42` | Trạng thái đích tương ứng payload |
| Sửa một phần thông tin | `PATCH /api/products/42` | Áp dụng tập thay đổi được mô tả |
| Xóa sản phẩm | `DELETE /api/products/42` | Không còn biểu diễn hiện tại của sản phẩm theo API |

Đừng đánh đồng HTTP verb với CRUD một cách cứng nhắc: `POST` có thể kích hoạt xử lý nghiệp vụ; `GET` có thể trả biểu diễn được tổng hợp từ nhiều nguồn; `PATCH` có thể là một tập thao tác phức tạp. Method nói lên **ý định giao tiếp**, còn URI và tài liệu API nói lên **tài nguyên, quyền, payload và kết quả cụ thể**.

Các quy ước hữu ích:

- URI nên mô tả tài nguyên bằng danh từ khi phù hợp (`/orders/42`), còn method mô tả hành động theo giao ước HTTP.
- Đừng dùng `GET /delete?id=42` hay `GET /pay?id=42` để kích hoạt thay đổi nghiệp vụ.
- Chọn mã trạng thái phản ánh thực tế: `200 OK`, `201 Created`, `202 Accepted`, `204 No Content`, `400 Bad Request`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`, `409 Conflict`, `412 Precondition Failed`, `405 Method Not Allowed`.
- Khi method được server nhận biết nhưng không được cho phép trên tài nguyên, `405` thường đi kèm `Allow`; khi server không nhận biết/không triển khai method, `501 Not Implemented` là tình huống khác.
- Authentication, authorization, validation và bảo vệ chống CSRF (khi ứng dụng dùng cơ chế cookie/session và có nguy cơ CSRF) cần dựa trên bối cảnh; lựa chọn method đúng không tự động giải quyết vấn đề bảo mật.

## 7. Thực hành với Spring Web MVC

Ví dụ dưới đây là một **ứng dụng Spring Boot MVC tối giản** để quan sát rõ sự khác nhau giữa `GET`, `PUT`, `POST` và `DELETE`. Nó sử dụng Java record (Java 17+) và bộ nhớ RAM, phù hợp cho học tập. Khi chạy cần dự án Spring Boot có dependency web MVC và bộ chuyển JSON, ví dụ một dự án tạo bằng Spring Initializr với dependency **Spring Web**, cùng JDK tương thích với phiên bản Boot được chọn.

Tạo tệp `src/main/java/com/example/http/HttpMethodsApplication.java`:

```java
package com.example.http;

import java.util.concurrent.ConcurrentHashMap;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class HttpMethodsApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpMethodsApplication.class, args);
    }
}

@RestController
@RequestMapping("/api/counters")
class CounterController {
    private final ConcurrentHashMap<String, Integer> counters =
            new ConcurrentHashMap<>();

    public record CounterValue(int value) {}

    @GetMapping("/{key}")
    public ResponseEntity<CounterValue> get(@PathVariable String key) {
        Integer value = counters.get(key);
        if (value == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(new CounterValue(value));
    }

    @PutMapping("/{key}")
    public ResponseEntity<CounterValue> replace(
            @PathVariable String key,
            @RequestBody CounterValue body) {
        Integer previous = counters.put(key, body.value());
        HttpStatus status = previous == null
                ? HttpStatus.CREATED
                : HttpStatus.OK;
        return ResponseEntity.status(status).body(body);
    }

    @PostMapping("/{key}/increment")
    public ResponseEntity<CounterValue> increment(
            @PathVariable String key) {
        Integer value = counters.compute(
                key, (ignored, oldValue) ->
                        oldValue == null ? 1 : oldValue + 1);
        return ResponseEntity.ok(new CounterValue(value));
    }

    @DeleteMapping("/{key}")
    public ResponseEntity<Void> delete(@PathVariable String key) {
        counters.remove(key);
        return ResponseEntity.noContent().build();
    }
}
```

**Tại sao code minh họa đúng trọng tâm?**

- `GET` chỉ đọc trạng thái; giá trị `null` dẫn đến `404`.
- `PUT` gán một giá trị cụ thể bằng `counters.put(key, body.value())`. Gửi `{"value":5}` bao nhiêu lần thì trạng thái cuối cùng vẫn là 5, nếu không có thao tác khác chen vào.
- `POST /increment` dùng `compute` để tăng giá trị hiện tại mỗi lần nhận request; `ConcurrentHashMap.compute` làm phép cập nhật tại một key theo cách atomic trong map. Hai POST làm tăng hai lần.
- `DELETE` dùng `remove`; gọi lại vẫn giữ key ở trạng thái không tồn tại.
- `ResponseEntity` thể hiện được status khác nhau (`201` khi PUT tạo key mới, `200` khi thay thế) mà không làm mất idempotency.

Đây là dữ liệu **in-memory**, không lưu sau khi khởi động lại và không thể hiện xử lý giao dịch, bảo mật, validation hoặc persistence của hệ thống thật. `Integer` cũng có nguy cơ overflow nếu liên tục tăng đến giới hạn; tình huống production cần lựa chọn miền dữ liệu và quy tắc kiểm tra phù hợp.

### Chạy và gửi request

Với dự án Gradle có Spring Boot plugin, chạy `./gradlew bootRun` (hoặc `gradlew.bat bootRun` trên Windows). Nếu dùng Maven Wrapper, chạy `./mvnw spring-boot:run` (hoặc `mvnw.cmd spring-boot:run` trên Windows). Không thể chạy riêng source này bằng lệnh `javac` thuần vì nó cần thư viện Spring Boot và Spring MVC.

Giả sử server đang chạy tại `http://localhost:8080`, lần lượt thực hiện:

**Bước 1 — Đọc trước khi tạo**

```bash
curl -i http://localhost:8080/api/counters/demo
```

Status dự kiến: `404 Not Found`.

**Bước 2 — Gửi PUT lần thứ nhất**

```bash
curl -i -X PUT "http://localhost:8080/api/counters/demo" -H "Content-Type: application/json" -d '{"value":5}'
```

Status dự kiến: `201 Created`; body JSON có giá trị `{"value":5}`.

**Bước 3 — Lặp lại cùng PUT**

```bash
curl -i -X PUT "http://localhost:8080/api/counters/demo" -H "Content-Type: application/json" -d '{"value":5}'
```

Status dự kiến lần này: `200 OK`, nhưng body và giá trị trong map vẫn tương ứng với `{"value":5}`. Status khác nhau **không phủ nhận tính idempotent**.

**Bước 4 — Gửi POST tăng giá trị hai lần**

```bash
curl -i -X POST http://localhost:8080/api/counters/demo/increment
curl -i -X POST http://localhost:8080/api/counters/demo/increment
```

Body JSON dự kiến lần lượt chứa `{"value":6}` và `{"value":7}`. Cùng một request POST làm thay đổi trạng thái thêm mỗi lần: không idempotent.

**Bước 5 — Gửi DELETE hai lần**

```bash
curl -i -X DELETE http://localhost:8080/api/counters/demo
curl -i -X DELETE http://localhost:8080/api/counters/demo
```

Hai response đều là `204 No Content`, không có body. Sau đó GET trả `404 Not Found`.

**Lưu ý về shell:** cú pháp dùng dấu nháy đơn cho JSON trong ví dụ `curl` phù hợp với Bash, zsh hoặc PowerShell hiện đại tùy phiên bản. Trong Windows PowerShell 5.1, `curl` thường là alias của `Invoke-WebRequest`; để chạy cú pháp kiểu curl, gọi `curl.exe` và điều chỉnh cách quote JSON của PowerShell, hoặc dùng `Invoke-RestMethod`.

### Liên hệ với annotation Spring MVC

| Annotation Spring MVC | Method HTTP | Điều cần giữ đúng |
|---|---|---|
| `@GetMapping` | GET | Không dùng để gây ra thay đổi nghiệp vụ do client yêu cầu |
| `@PostMapping` | POST | Xử lý tác vụ có side effect; retry phải có chiến lược |
| `@PutMapping` | PUT | Gán/thay thế tài nguyên theo hợp đồng; cùng request giữ tác động dự kiến |
| `@PatchMapping` | PATCH | Xác định rõ semantics của patch và khả năng retry |
| `@DeleteMapping` | DELETE | Lặp lại cùng yêu cầu giữ cùng trạng thái đã xóa |
| `@RequestMapping(method = RequestMethod.OPTIONS)` | OPTIONS | Chỉ tùy biến khi cần, vì framework/server có thể tự xử lý |

Annotation chỉ đăng ký handler; nó **không thể tự biến một thao tác tăng số dư thành idempotent** hoặc biến hành động xóa thành safe nếu logic bên trong vi phạm ngữ nghĩa method.

## 8. Retry: vì sao idempotency có giá trị trong hệ phân tán?

Giả sử client gửi request đến server. Server **đã xử lý thành công**, nhưng kết nối đứt trước khi client nhận response:

```text
Client                          Server
  | -------- PUT --------------> |
  |                              | cập nhật tài nguyên xong
  |       X response mất         |
  |                              |
  | -------- PUT (retry) ------> |
  |                              | áp dụng lại cùng trạng thái
  | <------- response ---------  |
```

Client không biết lần đầu server đã xử lý hay chưa. Nếu PUT tuân thủ idempotency, retry cùng request có thể đạt cùng tác động mong muốn. Nếu request là POST tạo đơn và cứ gửi lại mà không có cơ chế chống trùng, client có nguy cơ tạo **hai đơn hàng**.

Các nguyên tắc thực hành:

1. Chỉ retry tự động khi thực sự hiểu ngữ nghĩa thao tác. HTTP coi các method idempotent là ứng viên phù hợp để retry khi lỗi giao tiếp; còn với method không idempotent, không tự retry chỉ vì chưa thấy response.
2. Retry cần timeout, giới hạn số lần thử, backoff và xử lý mã lỗi phù hợp. Idempotency không có nghĩa retry vô hạn; retry cũng không tự khắc phục dữ liệu sai hoặc lỗi validation.
3. Với giao dịch có nguy cơ trùng lặp (đặt đơn, thanh toán, gửi lệnh), cân nhắc **idempotency key**: client tạo một mã duy nhất cho *một ý định nghiệp vụ*, gửi lại cùng key khi retry; server lưu trạng thái xử lý/kết quả theo key và trả lại hoặc xử lý nhất quán. Đây là hợp đồng ứng dụng cần thiết kế rõ: phạm vi key, thời hạn lưu, cùng key nhưng payload khác, lỗi giữa các bước, và đồng thời nhiều request. Không nên chỉ dựa vào một map RAM cho nghiệp vụ tài chính.
4. Idempotency key giúp chống thực hiện lặp của **cùng một yêu cầu có định danh**, nhưng không tự bảo đảm mọi hành vi trong hệ thống phân tán là “exactly once”.
5. GET/HEAD và các phương thức an toàn còn có thể chịu tác động của cache. **Safe, idempotent và cacheable là ba thuộc tính khác nhau**: ví dụ PUT idempotent nhưng response của PUT không mặc nhiên cacheable; GET có thể cache theo các quy tắc HTTP; cache không tự thay thế cơ chế chống request trùng.

Ví dụ minh họa một hợp đồng tùy ứng dụng, không phải lời cam kết tất cả API đều hỗ trợ header này:

```http
POST /api/orders HTTP/1.1
Host: shop.example
Idempotency-Key: order-request-abc123
Content-Type: application/json

{"productId":42,"quantity":1}
```

Một server có hỗ trợ có thể phát hiện retry cùng key và cùng nội dung theo quy tắc đã công bố, tránh tạo đơn thứ hai. Nếu đổi payload nhưng giữ key, server phải có quy tắc xử lý xung đột rõ ràng.

## 9. Idempotency không giải quyết việc ghi đè cập nhật đồng thời

Giả sử Lan và Minh cùng đọc một sản phẩm ở phiên bản 7. Lan đổi tên sản phẩm; sau đó Minh dùng dữ liệu cũ để PUT trạng thái đầy đủ. Dù cả hai PUT đều idempotent, update của Minh vẫn có thể **ghi đè** thay đổi của Lan.

HTTP hỗ trợ conditional request bằng `ETag` và `If-Match`. Một quy trình minh họa:

```http
GET /api/products/42 HTTP/1.1
Host: shop.example
```

Server trả một ETag, chẳng hạn `"v7"`. Client gửi cập nhật:

```http
PUT /api/products/42 HTTP/1.1
Host: shop.example
If-Match: "v7"
Content-Type: application/json

{"name":"Tên mới","active":true}
```

Nếu biểu diễn hiện tại đã thay đổi và điều kiện không còn đúng, server nên trả `412 Precondition Failed` (theo semantics của If-Match) thay vì âm thầm ghi đè. Ứng dụng phải thực sự triển khai và kiểm tra precondition; thêm header ở phía client không làm server tự động xử lý đúng trong mọi thiết kế controller. Conditional request bổ sung kiểm soát concurrency, còn idempotency giải quyết hành vi lặp lại.

## 10. Những nhầm lẫn thường gặp

**Nhầm 1 — “Idempotent nghĩa là chỉ đọc.”** Không đúng. PUT và DELETE đều có thể làm thay đổi trạng thái nhưng vẫn idempotent.

**Nhầm 2 — “Idempotent nghĩa là mỗi lần đều có response 200 và body giống nhau.”** Không đúng. PUT tạo mới có thể trả 201, lần thay thế tiếp theo trả 200; DELETE lần sau có thể trả 404 thay vì 204.

**Nhầm 3 — “POST luôn tạo mới, PUT luôn cập nhật, PATCH chắc chắn idempotent.”** Không đúng. POST yêu cầu tài nguyên xử lý theo semantics của nó; PUT có thể tạo hoặc thay thế; PATCH không được bảo đảm idempotent.

**Nhầm 4 — “GET chỉ gọi server một lần nên có thể dùng để trừ tiền.”** Không đúng. Trình duyệt, crawler, cache validator hoặc cơ chế prefetch có thể tạo thêm GET. Nghiệp vụ trừ tiền cần một hành động unsafe được xác thực và bảo vệ thích hợp.

**Nhầm 5 — “Dùng `@PutMapping` là logic Java tự động idempotent.”** Không đúng. Nếu controller tăng biến đếm hoặc tạo bản ghi mới mỗi lần gọi, behavior không tuân thủ kỳ vọng PUT.

**Nhầm 6 — “Idempotency giúp ngăn mọi lỗi do concurrent requests.”** Không đúng. Thao tác cạnh tranh giữa nhiều người dùng cần optimistic locking, conditional request hoặc đồng bộ phù hợp. Idempotency của một request đơn lẻ không đảm bảo tính tuần tự cho toàn hệ thống.

**Nhầm 7 — “Method GET an toàn nên API công khai cho mọi người được.”** Không đúng. Safety là semantics về thay đổi trạng thái; quyền truy cập dữ liệu là trách nhiệm riêng.

**Nhầm 8 — “Retry POST chỉ cần đặt cùng ID trong body.”** Chưa đủ nếu backend không có cơ chế nhận dạng, lưu trữ và đảm bảo xử lý request trùng theo hợp đồng. Việc phân biệt một retry với một hành động mới phải được thiết kế rõ ràng.

## 11. Bài tập tự kiểm tra

**Câu 1.** Endpoint `PUT /api/settings/theme` luôn đặt theme là `dark`. Gửi hai lần có idempotent không?  
**Giải thích:** Có, nếu server thực hiện đúng phép gán trạng thái theme=dark; gửi thêm cùng yêu cầu không làm thay đổi tác động nghiệp vụ mong muốn.

**Câu 2.** Endpoint `PATCH /api/users/42` luôn đặt `active=true` có thể idempotent không?  
**Giải thích:** Có thể, theo semantics cụ thể của phép patch. Tuy vậy PATCH không được chuẩn bảo đảm idempotent cho mọi loại thay đổi.

**Câu 3.** DELETE lần đầu trả 204, lần hai trả 404: có vi phạm idempotency không?  
**Giải thích:** Không. Mục tiêu sau cả hai lần vẫn là tài nguyên đã bị xóa/không còn tồn tại.

**Câu 4.** Một GET trả 200 nhưng cũng gửi email xác nhận mua hàng. GET này có tuân thủ safety không?  
**Giải thích:** Không, nếu email xác nhận là hành động nghiệp vụ phát sinh do việc gọi GET và client không chỉ yêu cầu đọc.

**Câu 5.** Có thể tự động retry một POST thanh toán ngay khi timeout không?  
**Giải thích:** Không nên nếu chưa biết request trước đã được xử lý hay chưa và chưa có hợp đồng chống trùng; có thể gây giao dịch lặp. Cần cơ chế idempotency, truy vấn trạng thái hoặc cách phục hồi nghiệp vụ do hệ thống hỗ trợ.

**Câu 6.** Hai PUT cùng idempotent có chắc không ghi đè dữ liệu của nhau không?  
**Giải thích:** Không. Xét dùng ETag/If-Match, optimistic locking hoặc chiến lược concurrency tương ứng.

## 12. Tài liệu chuẩn để tra cứu

- [RFC 9110 – HTTP Semantics, Section 9: Methods](https://www.rfc-editor.org/rfc/rfc9110.html#section-9): đặc biệt Section 9.2.1 (Safe Methods), 9.2.2 (Idempotent Methods), 9.3 (Method Definitions).
- [RFC 5789 – PATCH Method for HTTP](https://www.rfc-editor.org/rfc/rfc5789.html): ngữ nghĩa PATCH và lý do PATCH không mặc định idempotent.
- [Spring Framework Reference – Spring Web MVC](https://docs.spring.io/spring-framework/reference/web/webmvc.html): controller, request mapping và cách Spring MVC xử lý HTTP.

**Ghi nhớ:** *Safe* nói về việc client có yêu cầu thay đổi trạng thái hay không; *idempotent* nói về tác động dự kiến khi lặp lại cùng request. GET/HEAD/OPTIONS/TRACE safe và idempotent; PUT/DELETE không safe nhưng idempotent; POST/PATCH không được bảo đảm idempotent. Thiết kế controller, retry và xử lý đồng thời phải tôn trọng những ngữ nghĩa này.
