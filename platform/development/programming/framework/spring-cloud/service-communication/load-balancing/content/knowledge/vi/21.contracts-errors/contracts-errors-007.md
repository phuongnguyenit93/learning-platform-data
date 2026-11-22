# Header nhiều giá trị, ký tự đặc biệt và mã hóa URI

Trong hệ thống microservices dùng **Spring Cloud LoadBalancer**, caller có thể gọi `inventory-service` qua RestClient, WebClient hoặc OpenFeign bằng URI logic như `http://inventory-service/api/items/{sku}`. LoadBalancer chọn một `ServiceInstance` dựa trên service ID, discovery, health check và chính sách định tuyến. Nhưng việc chọn đúng instance **không bảo đảm HTTP request đã đúng hợp đồng**: nhiều lỗi 400, 401, 404, 414 hoặc 431 xuất phát từ header nhiều giá trị bị ghép sai, dấu đặc biệt trong SKU/query bị hiểu thành cấu trúc URI, hoặc các proxy và HTTP client không thống nhất cách mã hóa.

Bài thuộc chương **Hợp đồng và lỗi** này tập trung vào ba phần liên hệ chặt chẽ:

1. **Header nhiều giá trị:** khi nào một field có nhiều giá trị, khi nào được phép gom bằng dấu phẩy, và ngoại lệ `Set-Cookie`.
2. **Ký tự đặc biệt:** ranh giới giữa dữ liệu và cú pháp; kiểm soát CR/LF, dấu phẩy, dấu chấm phẩy, Unicode, kích thước header và thông tin nhạy cảm.
3. **Mã hóa URI:** phân biệt path, path segment, query, reserved characters, UTF-8 percent-encoding và encode một lần ở đúng tầng.

Mục tiêu không phải thuộc lòng một hàm `encode`, mà là xây dựng **hợp đồng trên đường truyền** mà caller, proxy, LoadBalancer và downstream hiểu giống nhau; khi xảy ra lỗi, biết cách xác định lỗi ở component nào.

## 1. Hợp đồng HTTP gồm nhiều tầng

~~~mermaid
flowchart LR
    A["Business code"] --> B["RestClient / WebClient / OpenFeign"]
    B --> C["Header & URI builder"]
    C --> L["Spring Cloud LoadBalancer"]
    D["Discovery / ServiceInstance"] --> L
    L --> E["HTTP transport"]
    E --> P["Gateway / proxy (nếu có)"]
    P --> S["Inventory endpoint"]
~~~

Trong một request, có những lớp dữ liệu độc lập:

| Lớp | Ví dụ | Ai quyết định? |
|---|---|---|
| Service ID | `inventory-service` | Tên logic trong URI hoặc `@FeignClient(name)` |
| Địa chỉ vật lý | `localhost:8082` | LoadBalancer sau khi chọn instance |
| Path template | `/api/items/{sku}` | Hợp đồng API |
| Path variable | `SKU/A&B` | Dữ liệu caller, phải mã hóa theo ngữ nghĩa path segment |
| Query key/value | `tag=red blue` | Hợp đồng search/filter, cần encode theo thành phần query |
| Request headers | `Accept`, `Authorization`, `X-Correlation-Id` | HTTP protocol + chính sách ứng dụng |
| Response headers | `Cache-Control`, `Set-Cookie`, `Vary` | Downstream/gateway |
| Body | JSON UTF-8 | Content-Type, codec, DTO/validation |

Đổi hostname từ `inventory-service` sang host/port instance chỉ giải quyết **định tuyến**. Nó không tự sửa request sai header hoặc request-target. Mọi tầng HTTP trong chuỗi phải thống nhất cách đọc những giá trị có thể chứa dấu phân cách.

## 2. HTTP field có thể xuất hiện nhiều dòng hoặc chứa danh sách

Theo **RFC 9110, mục 5.2–5.3**, một tên field có thể xuất hiện ở nhiều field lines. Với những field *cho phép cú pháp danh sách*, nhiều dòng có thể được diễn giải tương đương một dòng có các giá trị phân tách bằng dấu phẩy, giữ nguyên thứ tự giá trị.

Ví dụ hai cách viết có thể tương đương đối với header có list grammar:

~~~http
Accept: application/json
Accept: application/problem+json
~~~

~~~http
Accept: application/json, application/problem+json
~~~

Tuy nhiên, quy tắc **không đúng cho mọi header**. Gộp bằng dấu phẩy chỉ an toàn khi định nghĩa field cho phép list syntax và parser hiểu dấu phẩy nằm trong quoted string hoặc cấu trúc tương ứng.

| Header | Ý nghĩa/kiểu | Lưu ý |
|---|---|---|
| `Accept` | Danh sách media ranges | Có thể diễn giải nhiều phần tử, xét `q` và thứ tự |
| `Accept-Language` | Danh sách ngôn ngữ có trọng số | Không tự chia bằng dấu phẩy nếu parser không xử lý quoted/quality syntax |
| `Cache-Control` | Danh sách directives | Phân tích cú pháp theo định nghĩa field, không xử lý chuỗi tùy tiện |
| `Vary` | Danh sách tên headers ảnh hưởng cache | Quan trọng với content negotiation |
| `X-Request-Tag` | Field do ứng dụng định nghĩa | Phải **quy định rõ** lặp dòng hay CSV, có escape/quote hay không |
| `Authorization` | Credential, thường chỉ một giá trị có hiệu lực | Duplicate hoặc giá trị không nhất quán phải được xử lý an toàn |
| `Content-Type` | Một media type | Không diễn giải nhiều Content-Type tùy ý |
| `Set-Cookie` | Nhiều lệnh đặt cookie độc lập | **Không nối thành một header dấu phẩy** |
| `Cookie` (request) | Cú pháp cookie đặc thù, thường phân cách bằng `;` | Không dùng quy tắc chung của list field cho cookie |

**Không đồng nhất** “hai dòng cùng tên”, “một dòng chứa hai phần tử” và “một giá trị chứa ký tự dấu phẩy”. Cả ba có thể xuất hiện ở lớp HTTP library dưới dạng `List<String>` nhưng không có cùng nghĩa.

### Tại sao dấu phẩy dễ gây hiểu sai?

Ví dụ ứng dụng tự định nghĩa:

~~~http
X-Display-Name: Nguyen, An
~~~

Đây có thể là **một tên đầy đủ** hoặc **hai thành viên danh sách** nếu không có contract rõ ràng. Nếu truyền dữ liệu tự do chứa dấu phẩy, tốt hơn dùng JSON body, một field có quy tắc quoted/escaping được chuẩn hóa, hoặc một scheme định dạng rõ ràng.

Đối với dữ liệu nhiều phần tử, đừng tự đoán `split(",")` sẽ an toàn. Những cú pháp như `Accept: application/json;q=0.9, text/plain;q=0.7` hoặc chuỗi quoted có thể cần parser theo đúng RFC/field definition.

## 3. Set-Cookie là ngoại lệ phải xử lý riêng

Một response có thể có:

~~~http
HTTP/1.1 200 OK
Set-Cookie: session=abc; Path=/; HttpOnly; Secure; SameSite=Lax
Set-Cookie: theme=dark; Path=/; Max-Age=3600
~~~

Hai dòng `Set-Cookie` đại diện **hai cookie khác nhau**. Không biến thành:

~~~http
Set-Cookie: session=abc; Path=/; HttpOnly, theme=dark; Path=/
~~~

Dấu phẩy còn có thể xuất hiện trong thuộc tính `Expires` của cookie, ví dụ tên ngày và dấu phẩy, nên parser chia bằng `,` sẽ đặc biệt dễ sai.

Ví dụ downstream Spring MVC có thể trả nhiều cookie:

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;

ResponseCookie session = ResponseCookie.from("session", "abc")
        .httpOnly(true)
        .secure(true)
        .sameSite("Lax")
        .path("/")
        .build();

ResponseCookie theme = ResponseCookie.from("theme", "dark")
        .path("/")
        .maxAge(java.time.Duration.ofHours(1))
        .build();

return ResponseEntity.ok()
        .header(HttpHeaders.SET_COOKIE, session.toString())
        .header(HttpHeaders.SET_COOKIE, theme.toString())
        .body("ok");
~~~

`ResponseEntity.HeadersBuilder.header(...)` hỗ trợ thêm các giá trị; ở tầng response kiểm tra xem kết quả thực tế bảo toàn các giá trị `Set-Cookie` riêng biệt hay không.

Khi một service đóng vai trò proxy, **không nối các Set-Cookie bằng `String.join(",")`**. Cũng không proxy mọi Set-Cookie không chọn lọc: domain/path/SameSite/Secure và phạm vi tin cậy có thể không phù hợp với domain của gateway.

## 4. HttpHeaders trong Spring: add khác set

`org.springframework.http.HttpHeaders` là abstraction dạng map nhiều giá trị. Điều này cho phép làm việc với một field có nhiều values, nhưng **không tự quyết định** field đó có được phép lặp theo RFC hay không.

~~~java
import org.springframework.http.HttpHeaders;

HttpHeaders headers = new HttpHeaders();

// Thêm vào danh sách giá trị.
headers.add(HttpHeaders.ACCEPT, "application/json");
headers.add(HttpHeaders.ACCEPT, "application/problem+json");

// Ghi đè các giá trị hiện có của field này.
headers.set("X-Correlation-Id", "2d907f2d-bf7e-447b-a35d-6db7bd0f1eae");

// Chỉ đọc phần tử đầu tiên.
String firstAccept = headers.getFirst(HttpHeaders.ACCEPT);

// Đọc các giá trị được lưu ở lớp HttpHeaders.
java.util.List<String> rawValues = headers.get(HttpHeaders.ACCEPT);
~~~

Điểm cần nhớ:

- `add(name, value)` bổ sung giá trị của field.
- `set(name, value)` thay các giá trị đã có bằng một giá trị.
- `getFirst(name)` trả phần tử đầu tiên hoặc `null`, **không có nghĩa header chỉ có một giá trị**.
- `get(name)` có thể trả các field line values ở tầng abstraction, **không bảo đảm** một server/proxy chưa gộp chúng trong quá trình truyền.
- Với header có cấu trúc và helper tương ứng, ưu tiên API typed như `setAccept`, `getAccept`, `setContentType`, `setBearerAuth` để giảm lỗi định dạng.
- Tên header **không phân biệt hoa thường** theo HTTP. Không coi `X-Trace-Id` và `x-trace-id` là hai trường độc lập.

Không sử dụng `getFirst("Authorization")` để **âm thầm chấp nhận** một request có nhiều credential không nhất quán. Ở boundary xác thực, cần kiểm soát duplicate theo contract và theo khả năng proxy đã ghép/rewrite, từ chối trường hợp mơ hồ thay vì chọn ngẫu nhiên một credential.

### Dùng MultiValueMap khi contract cần nhiều giá trị

~~~java
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;

MultiValueMap<String, String> filters = new LinkedMultiValueMap<>();
filters.add("tag", "red");
filters.add("tag", "blue");
~~~

`MultiValueMap` phù hợp làm cấu trúc nội bộ cho nhiều giá trị, nhưng **cách biểu diễn trên wire phải được chỉ định riêng**: nhiều query parameters lặp tên, CSV, JSON array hay nhiều HTTP header field lines không phải cùng một kiểu contract.

## 5. Nhận header nhiều giá trị ở Spring MVC

Ví dụ inventory nhận yêu cầu lọc dữ liệu theo một field custom:

~~~java
import java.util.List;
import org.springframework.http.HttpHeaders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CatalogController {

    @GetMapping("/api/catalog")
    String catalog(
            @RequestHeader HttpHeaders headers) {

        List<String> rawTags = headers.get("X-Item-Tag");

        // Parser và validation tùy theo contract của X-Item-Tag.
        return rawTags == null ? "no tags" : "tags received";
    }
}
~~~

Nếu contract định nghĩa `X-Item-Tag` là **một field đơn** có grammar riêng, cần kiểm tra và parse đúng grammar đó. Nếu muốn nhiều tag độc lập, cân nhắc dùng query parameters `?tag=red&tag=blue` hoặc JSON body khi thích hợp; chúng thường có cách binding rõ hơn một custom header nhiều giá trị chưa chuẩn hóa.

Với một header bắt buộc duy nhất, hãy validate count, độ dài, ký tự và giá trị sau khi được normalize; đồng thời kiểm tra duplicate ambiguity khi có proxy ở phía trước. Không coi `String[]` trong controller là hình dạng wire được bảo đảm cho mọi HTTP client/proxy.

## 6. Ký tự đặc biệt trong HTTP header: CRLF và Unicode

HTTP header name là **token theo cú pháp HTTP**, không phải một chuỗi Unicode tự do. Header value cũng có các ràng buộc về ký tự điều khiển. Đặc biệt, ký tự carriage return (`\r`) và line feed (`\n`) có thể tạo nguy cơ **HTTP response/request splitting** nếu bị xử lý sai.

Ví dụ *dữ liệu không an toàn*, chỉ minh họa để nhận diện:

~~~text
X-Display-Name = "Alice" + CR + LF + "X-Injected: yes"
~~~

Không bao giờ nối trực tiếp một giá trị do người dùng cung cấp vào raw HTTP header string. HTTP library hiện đại thường có validation và chặn newline, nhưng ứng dụng cũng phải kiểm tra dữ liệu ở boundary và không xây HTTP request bằng chuỗi thô.

Ví dụ validator cho một correlation ID theo UUID:

~~~java
import java.util.UUID;

public final class CorrelationIds {

    private CorrelationIds() {
    }

    public static String normalize(String incoming) {
        if (incoming == null || incoming.length() != 36) {
            return UUID.randomUUID().toString();
        }

        try {
            return UUID.fromString(incoming).toString();
        } catch (IllegalArgumentException ex) {
            return UUID.randomUUID().toString();
        }
    }
}
~~~

Mẫu trên chuẩn hóa/sinh ID cho **một loại header cụ thể**, không phải validator tổng quát của mọi header. UUID là cấu trúc dễ giới hạn và không chứa newline, dấu phẩy hoặc space.

### Tiếng Việt có dấu trong header?

Một giá trị như `Tên khách: Nguyễn An` không nên mặc định được đặt thẳng vào header tùy ý. Header strings đi qua các stack HTTP/1.1, HTTP/2, proxy, client libraries với quy tắc byte/encoding khác nhau. Cách an toàn và dễ tương thích hơn:

- Dữ liệu văn bản tự do: để trong JSON body, charset UTF-8.
- Giá trị là một phần URI: sử dụng URI builder và UTF-8 percent-encoding.
- Header chuẩn có hỗ trợ tham số quốc tế hóa, ví dụ `Content-Disposition`: dùng API chuẩn và quy ước encoding tương ứng như RFC 8187 cho `filename*` khi phù hợp.
- Custom header: thiết kế cấu trúc ASCII an toàn hoặc encoding được quy định rõ; không dựa vào “thử thấy chạy” của một transport.

Ví dụ `filename*=UTF-8''...` là một quy ước dành cho **tham số của những header cụ thể**, không phải lời khuyên percent-encode tùy ý toàn bộ giá trị mọi HTTP header.

## 7. Header do proxy chuyển tiếp: danh tính và ranh giới tin cậy

Các header `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Host`, `X-Forwarded-Proto` có thể ảnh hưởng cách ứng dụng suy ra địa chỉ client hoặc URL public.

~~~mermaid
flowchart LR
    C["Internet client"] --> P["Trusted gateway"]
    P --> O["order-service"]
    O --> L["LoadBalancer"]
    L --> I["inventory-service"]
~~~

Sai lầm nguy hiểm: tin trực tiếp `X-Forwarded-Host` do client ngoài gửi để dựng URL redirect hoặc gọi downstream. Nếu gateway không xóa/ghi đè header không đáng tin, ứng dụng có thể bị **host header injection, open redirect hoặc SSRF**.

Trong Spring, `ForwardedHeaderFilter` hoặc cấu hình forward-headers của Boot có thể giúp framework hiểu header do proxy cấp. Nhưng framework không tự chứng minh nguồn header đáng tin: cần cấu hình proxy/ingress loại bỏ các header do client giả mạo trước khi áp dụng.

Không relay `Authorization`, `Cookie`, `Host`, `Content-Length`, `Connection` hoặc toàn bộ inbound headers sang service đích. Chỉ truyền context trong allowlist đã được chuẩn hóa; header về tenant/role phải dựa trên authentication và downstream vẫn phải phân quyền.

### Hạn chế kích thước và số lượng header

HTTP không có một giới hạn kích thước field áp dụng chung cho mọi hệ thống; server, proxy và client có giới hạn riêng. Header quá lớn có thể bị chặn với `431 Request Header Fields Too Large` hoặc một 4xx phù hợp. URI quá dài có thể dẫn đến `414 URI Too Long`.

Không chuyển hàng trăm item IDs, payload hoặc JSON blob lớn qua custom header. Sử dụng body hoặc tài nguyên/filter API có schema rõ. Khi đo lỗi, xem log server/proxy trước khi tăng hạn mức: request quá lớn còn có thể là dấu hiệu input không kiểm soát.


## 8. URI gồm các thành phần khác nhau, không phải một chuỗi tùy ý

URI dạng tổng quát:

~~~text
scheme://authority/path?query#fragment

http://inventory-service/api/items/SKU-001?tag=red&tag=blue
  |           |                |                |
 scheme   host/service ID     path            query
~~~

Những ký tự `/`, `?`, `&`, `=`, `#` và `%` có **vai trò cú pháp** tùy thành phần:

- `/` phân chia các **path segments**.
- `?` ngăn path với query.
- `&` và `=` thường được dùng để tách query parameters theo convention.
- `#` bắt đầu fragment; fragment **không** được gửi trong HTTP request-target tới backend.
- `%` bắt đầu chuỗi percent-encoded octet.
- `+` là một ký tự có thể mang nghĩa đặc biệt với **form-style query decoding** (có stack diễn giải dấu cộng thành dấu cách).
- `;` có thể mang ý nghĩa matrix/path parameters trong một số routing convention.

Ví dụ:

~~~text
Giá trị sku thật:      SKU/A&B
Đặt trực tiếp vào path: /api/items/SKU/A&B
                       -> slash có thể tạo thêm path segment

Giá trị q thật:        red & blue
Nối trực tiếp:         ?q=red & blue
                       -> dấu & có thể bị hiểu là query separator

Giá trị note thật:     a#b
Nối trực tiếp:         ?note=a#b
                       -> phần #b là fragment, không tới server
~~~

**Đừng xây URI bằng nối chuỗi** như `baseUrl + "/items/" + sku + "?q=" + q` nếu các biến có thể chứa ký tự tùy ý. Sử dụng `UriBuilder`/`UriComponentsBuilder` và khai báo biến là dữ liệu, không phải một phần cú pháp URI.

## 9. Percent-encoding: mã hóa octet UTF-8 đúng component

Percent-encoding diễn tả octet bằng `%HH` (hai chữ số hex). Với dữ liệu Unicode trong URI, cách thông dụng là chuyển chuỗi sang UTF-8 rồi mã hóa các octets cần escape.

| Giá trị dữ liệu | Khi là biến được strict-encode | Tình huống |
|---|---|---|
| Khoảng trắng | `%20` | `Nón xanh` có dấu cách |
| Ký tự `+` | `%2B` | Query muốn tìm literal `C++` |
| Ký tự `&` | `%26` | Query value `red&blue` |
| Ký tự `=` | `%3D` | Query value `a=b` |
| Ký tự `/` | `%2F` | Một mã item chứa slash nhưng được định nghĩa là một path segment |
| Ký tự `?` | `%3F` | Dấu hỏi là dữ liệu, không mở query |
| Ký tự `#` | `%23` | Dấu thăng là dữ liệu |
| Ký tự `%` | `%25` | Dấu phần trăm literal |
| Ký tự `;` | `%3B` | Semicolon là dữ liệu trong path variable |

Các kết quả trên minh họa **URI variable được strict-encode**, không phải lời khẳng định mọi ký tự này đều buộc phải escape trong mọi vị trí của một URI đã hoàn chỉnh.

Ví dụ chuỗi `Nón xanh` khi được encode UTF-8 cho URI variable có dạng:

~~~text
N%C3%B3n%20xanh
~~~

Một dấu tiếng Việt không được encode thành một `%xx` duy nhất tùy ý; kết quả phụ thuộc các byte UTF-8 của ký tự đó.

### Plus và space không tương đương

Với dữ liệu tìm kiếm `C++`:

~~~text
Ý nghĩa mong muốn: q = "C++"

Nếu gửi ?q=C++
  -> có server/form decoder hiểu thành "C  "

Nếu gửi ?q=C%2B%2B
  -> thể hiện rõ literal dấu cộng
~~~

Vì vậy, đặt `q` thành URI variable và dùng strict encoding thay vì gắn chuỗi trực tiếp. Với dấu cách, `%20` phù hợp cho URI component; `+` thường được dùng trong `application/x-www-form-urlencoded` để biểu thị space. Hai chuẩn mã hóa có mục đích khác nhau.

## 10. Spring URI encoding: TEMPLATE_AND_VALUES và URI_COMPONENT

Spring Framework cung cấp `DefaultUriBuilderFactory` và `UriComponentsBuilder` với các chế độ mã hóa:

| EncodingMode | Cách xử lý | Khi nào cần |
|---|---|---|
| `TEMPLATE_AND_VALUES` | Encode template, **strict-encode URI variables** khi expand | Lựa chọn thích hợp cho phần lớn dữ liệu đầu vào |
| `VALUES_ONLY` | Chỉ strict-encode các URI variables trước khi expand | Khi template được kiểm soát và đã sẵn sàng |
| `URI_COMPONENT` | Expand rồi encode theo từng URI component; có thể giữ reserved chars hợp lệ trong component | Khi cố ý giữ reserved chars có nghĩa |
| `NONE` | Không encode | Chỉ khi input đã chuẩn hóa đầy đủ và được kiểm soát |

Ví dụ Spring:

~~~java
import java.net.URI;
import java.util.Map;
import org.springframework.web.util.UriComponentsBuilder;

String sku = "SKU/A&B";
String q = "C++";

URI uri = UriComponentsBuilder
        .fromUriString("http://inventory-service")
        .pathSegment("api", "items", "{sku}")
        .queryParam("q", "{q}")
        .encode()
        .buildAndExpand(Map.of("sku", sku, "q", q))
        .toUri();

System.out.println(uri);
~~~

Kết quả URI dự kiến:

~~~text
http://inventory-service/api/items/SKU%2FA%26B?q=C%2B%2B
~~~

Giải thích:

- `pathSegment("api", "items", "{sku}")` biểu diễn các **segments** thay vì nối `/` bằng tay.
- `{sku}` và `{q}` là placeholders; giá trị được expand như dữ liệu.
- `encode()` ở `UriComponentsBuilder` được gọi **trước** `buildAndExpand(...)` để áp dụng strict encoding cho variables.
- `toUri()` tạo `java.net.URI` đã được mã hóa. Nếu đưa URI này cho HTTP client, **không encode lại** trước khi gửi.

### Vì sao không luôn dùng URI_COMPONENT?

Trong component path, `;` có thể là ký tự hợp lệ nhưng mang nghĩa matrix parameter. Chế độ `URI_COMPONENT` có thể giữ `;` của URI variable thay vì escape; trong khi `TEMPLATE_AND_VALUES` coi variable là dữ liệu opaque nên encode cả những reserved chars như `;`. Cách thứ hai thường phù hợp hơn nếu dữ liệu do caller nhận từ user hoặc chứa mã hàng tùy ý.

Tương tự, dấu cộng trong query có thể hợp lệ theo RFC 3986 nhưng bị hiểu thành space khi server dùng form decoding. Strict-encode biến thường ít gây bất ngờ hơn.

## 11. RestClient: dùng URI builder trước khi LoadBalancer chọn instance

Ví dụ caller tạo RestClient được load balance và thiết lập encoding rõ ràng:

~~~java
package com.example.order.http;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;
import org.springframework.web.util.DefaultUriBuilderFactory;

@Configuration(proxyBeanMethods = false)
public class InventoryRestClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean
    RestClient inventoryRestClient(
            @LoadBalanced RestClient.Builder builder) {

        DefaultUriBuilderFactory uriFactory =
                new DefaultUriBuilderFactory(
                        "http://inventory-service"
                );
        uriFactory.setEncodingMode(
                DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES
        );

        return builder.clone()
                .uriBuilderFactory(uriFactory)
                .build();
    }
}
~~~

Gọi bằng URI template với biến:

~~~java
import java.util.Map;
import org.springframework.http.HttpHeaders;

String sku = "SKU/A&B";
String query = "C++";

ItemResponse item = inventoryRestClient.get()
        .uri(uriBuilder -> uriBuilder
                .pathSegment("api", "items", "{sku}")
                .queryParam("q", "{q}")
                .build(Map.of("sku", sku, "q", query)))
        .headers(headers -> {
            headers.set("X-Correlation-Id", correlationId);
            headers.setAccept(java.util.List.of(
                    org.springframework.http.MediaType.APPLICATION_JSON));
        })
        .retrieve()
        .body(ItemResponse.class);
~~~

`ItemResponse` và `correlationId` là DTO/giá trị của ứng dụng. `DefaultUriBuilderFactory` áp dụng strict encoding cho URI variables; các HTTP headers vẫn phải theo schema riêng, **không đi qua URI encoder**.

Nếu đã có một `java.net.URI` được dựng và mã hóa đúng, có thể gọi `.uri(uri)`. Với các API nhận `URI`, Spring thường dùng URI đã cho mà **không tự mã hóa lại**. Vì vậy, một URI đã chứa `%2F` không được encode thêm thành `%252F`.

### Header nhiều giá trị khi dùng RestClient

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;

inventoryRestClient.get()
        .uri("/api/catalog")
        .headers(headers -> {
            headers.setAccept(java.util.List.of(
                    MediaType.APPLICATION_JSON,
                    MediaType.valueOf("application/problem+json")
            ));

            headers.set("X-Correlation-Id", correlationId);

            // Chỉ minh họa khi contract X-Item-Tag cho phép lặp.
            headers.add("X-Item-Tag", "red");
            headers.add("X-Item-Tag", "blue");
        })
        .retrieve()
        .body(String.class);
~~~

`setAccept(...)` ưu tiên cách viết có cấu trúc, `set(...)` cho field logic một giá trị, `add(...)` chỉ dùng khi contract cho phép nhiều giá trị. Các client/proxy có thể chuyển đổi dạng một dòng/multiple lines đối với list-based field; **hãy kiểm tra giá trị thực ở backend thay vì so sánh text HTTP thô**.

## 12. WebClient: URI và headers trong chuỗi reactive

WebClient dùng `UriBuilderFactory` tương tự, còn việc thực thi chỉ xảy ra khi publisher được subscribe. Có thể tạo builder load-balanced và cấu hình encoding:

~~~java
package com.example.order.http;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.util.DefaultUriBuilderFactory;

@Configuration(proxyBeanMethods = false)
public class InventoryWebClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }

    @Bean
    WebClient inventoryWebClient(
            @LoadBalanced WebClient.Builder builder) {

        DefaultUriBuilderFactory uriFactory =
                new DefaultUriBuilderFactory(
                        "http://inventory-service"
                );
        uriFactory.setEncodingMode(
                DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES
        );

        return builder.clone()
                .uriBuilderFactory(uriFactory)
                .build();
    }
}
~~~

Gọi API:

~~~java
import java.util.Map;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import reactor.core.publisher.Mono;

Mono<ItemResponse> result = inventoryWebClient.get()
        .uri(builder -> builder
                .pathSegment("api", "items", "{sku}")
                .queryParam("q", "{q}")
                .build(Map.of("sku", "SKU/A&B", "q", "C++")))
        .headers(headers -> {
            headers.set("X-Correlation-Id", correlationId);
            headers.setAccept(java.util.List.of(
                    MediaType.APPLICATION_JSON
            ));
        })
        .retrieve()
        .bodyToMono(ItemResponse.class);
~~~

`result` là một `Mono<ItemResponse>`; chưa có HTTP request nếu không có subscriber. Với Spring Cloud, `@LoadBalanced WebClient.Builder` có thể tích hợp `ReactorLoadBalancerExchangeFilterFunction`; filter LoadBalancer giải quyết **hostname logic** sau khi URI được dựng.

### Quan sát response header nhiều giá trị

Đôi khi caller cần đọc `Set-Cookie` để kiểm tra hành vi của downstream trong lab:

~~~java
Mono<java.util.List<String>> cookieHeaders =
        inventoryWebClient.get()
                .uri("/demo/cookies")
                .exchangeToMono(response -> {
                    java.util.List<String> values =
                            response.headers()
                                    .header(HttpHeaders.SET_COOKIE);
                    return response.releaseBody()
                            .thenReturn(java.util.List.copyOf(values));
                });
~~~

`response.headers().header(...)` trả các giá trị mà HTTP client expose; không dùng `String.join(",")` hay `split(",")` cho `Set-Cookie`. Trong API production, nhiều khi không cần chuyển Set-Cookie của service nội bộ ra ngoài; tốt hơn để gateway quản lý session/cookie contract ở một trust boundary nhất quán.

Khi dùng `exchangeToMono`, phải tiêu thụ hoặc giải phóng response body đúng quy tắc để tránh rò tài nguyên; ví dụ `releaseBody()` ở trên dành cho trường hợp không cần body.


## 13. OpenFeign: @RequestParam, @PathVariable và CollectionFormat

OpenFeign là HTTP client khai báo bằng interface. Khi dùng Spring Cloud OpenFeign và `@FeignClient(name = "inventory-service")`, hostname/service ID được giải quyết qua LoadBalancer nếu không cấu hình URL tĩnh.

Ví dụ:

~~~java
package com.example.order.inventory;

import java.util.List;
import org.springframework.cloud.openfeign.CollectionFormat;
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;

@FeignClient(name = "inventory-service")
public interface InventoryFeignClient {

    @CollectionFormat(feign.CollectionFormat.EXPLODED)
    @GetMapping("/api/items/{sku}")
    ItemResponse search(
            @PathVariable("sku") String sku,
            @RequestParam("q") String query,
            @RequestParam("tag") List<String> tags
    );
}
~~~

Spring Cloud OpenFeign hỗ trợ `@CollectionFormat` nhận một giá trị từ `feign.CollectionFormat`. Theo tài liệu, `EXPLODED` là định dạng mặc định trong nhiều tình huống, trong khi `CSV` biểu diễn nhiều phần tử thành một chuỗi ngăn cách bằng dấu phẩy.

Với hợp đồng lặp query keys, ý định là:

~~~http
GET /api/items/SKU-001?q=C%2B%2B&tag=red&tag=blue HTTP/1.1
Host: inventory-service
~~~

Nếu chuyển sang CSV, một server có thể thấy `tag=red,blue` thay vì hai occurrences `tag=red&tag=blue`. Hai cách **không tự tương đương** khi giá trị thực chứa dấu phẩy hoặc server binding xử lý khác nhau.

| Input | Contract mong muốn | Kiểm tra |
|---|---|---|
| `tags = ["red","blue"]` | `tag=red&tag=blue` | Dùng `EXPLODED` và kiểm tra URL thực |
| `tags = ["red,blue"]` | Một phần tử có dấu phẩy | Đừng tự split thành hai tag |
| `query = "C++"` | Ký tự cộng literal | Kiểm tra nhận được `C++` ở backend |
| `sku = "SKU/A"` | Một item ID chứa dấu slash | Kiểm tra encoding/định tuyến của Feign + server, không giả định |
| `tags = []` | Không có tag | Định nghĩa vắng field hay giá trị rỗng trong contract |

**Lưu ý phiên bản:** encoding `@PathVariable` có thể khác theo Spring Cloud OpenFeign, Feign core, HTTP client và cấu hình encode/decode slash. Không mặc định rằng `/` trong một path variable tùy ý sẽ luôn thành `%2F` được chấp nhận ở server. Nếu ID cần chứa slash hoặc phần lớn ký tự reserved, hãy cân nhắc thay contract sang query parameter, body hoặc opaque identifier an toàn.

### Feign @SpringQueryMap

Với nhiều bộ lọc, Spring Cloud OpenFeign hỗ trợ `@SpringQueryMap`:

~~~java
import org.springframework.cloud.openfeign.SpringQueryMap;

public record SearchFilter(String q, Integer page) {}

@GetMapping("/api/search")
SearchResult search(@SpringQueryMap SearchFilter filter);
~~~

Đoạn code là method minh họa bên trong một Feign client interface; `SearchResult` do ứng dụng định nghĩa. Khi cần cách encode query map đặc biệt hoặc nhiều occurrences cùng key, có thể cấu hình `QueryMapEncoder` được kiểm thử; đừng dựa vào một `Map<String, String>` để đại diện nhiều giá trị cho cùng tên khóa.

### Header trong OpenFeign cũng cần contract rõ

~~~java
@GetMapping("/api/items/{sku}")
ItemResponse getItem(
        @PathVariable("sku") String sku,
        @org.springframework.web.bind.annotation.RequestHeader(
                "X-Correlation-Id") String correlationId
);
~~~

Một correlation ID nên có một giá trị được kiểm tra. Những field nghiệp vụ nhiều giá trị nên được thiết kế trong API contract; không giả định một tham số `List<String>` ở `@RequestHeader` sẽ giữ nguyên **số dòng vật lý** sau proxy/load balancing.

`feign.RequestInterceptor` có thể bổ sung header vào `RequestTemplate`, nhưng hãy giới hạn các header riêng cho client đó, không chuyển toàn bộ inbound header hoặc tự percent-encode header values. Cần lưu ý Feign logging `FULL` có thể in Authorization, cookie và query nhạy cảm; chỉ bật trong môi trường được kiểm soát và có redaction.

## 14. Một query key nhiều giá trị không giống một string CSV

Một endpoint lọc nhiều tag có thể quy định một trong các hợp đồng sau:

| Kiểu | Ví dụ | Đặc điểm |
|---|---|---|
| **Exploded / repeated key** | `?tag=red&tag=blue` | Mỗi item là một occurrence |
| **CSV** | `?tag=red,blue` | Phải quy định escape/quote nếu item có dấu phẩy |
| **Indexed** | `?tag[0]=red&tag[1]=blue` | Phụ thuộc cách framework/server bind tên khóa |
| **JSON body** | `{"tags":["red","blue"]}` | Phù hợp khi filter phức tạp hoặc dài |

Chọn một kiểu và cố định trong API contract/OpenAPI. Đặc biệt:

- `?tag`, `?tag=` và **không có tham số `tag`** có thể mang nghĩa khác nhau.
- Hai tham số cùng tên có thể được server trả về theo thứ tự, nhưng nếu nghiệp vụ coi tag là set thì không nên dựa vào thứ tự để phân quyền hoặc tính cache key.
- Nếu giá trị chứa dấu phẩy, dấu bằng hoặc dấu cộng, caller phải encode **giá trị**, không đổi separator của contract.
- Trước khi nâng cấp Spring/Feign hoặc thay HTTP client, test raw query từ một server thực/MockWebServer; không chỉ assert một `List` được tạo ở Java.
- Với rất nhiều phần tử, query string có thể vượt giới hạn URI của server/proxy; dùng body/filter resource phù hợp.

## 15. Double encoding và double decoding

Một lỗi phổ biến là **mã hóa hai lần**:

~~~text
Dữ liệu gốc:          SKU/A
Encode một lần:       SKU%2FA
Encode lại dấu %:     SKU%252FA

Server decode một lần:
    SKU%252FA -> SKU%2FA
    => không phải SKU/A
~~~

Ngược lại, nếu server/proxy **decode hai lần**, một giá trị tưởng như chỉ là dữ liệu `%2F` có thể biến thành slash thật. Điều này có thể gây sai routing hoặc nguy cơ bypass validation khi các tầng giải mã không nhất quán.

Quy tắc cần thực hiện:

1. Xác định **dữ liệu gốc chưa mã hóa** ở biên ứng dụng.
2. Chọn đúng component (path segment hay query value).
3. Encode một lần khi dựng URI bằng builder.
4. Không truyền giá trị `%2F` đã encode như một biến có mục tiêu đại diện slash nếu builder sẽ encode nó lần nữa.
5. Không lấy URI đã encode rồi gọi thêm một hàm encoder dành cho raw data.
6. Tại server, validate **giá trị đã được giải mã theo contract**; không tự decode thêm các vòng tùy tiện.
7. Kiểm thử qua proxy, vì reverse proxy và servlet container có thể có chính sách riêng với encoded slash.

### Đường dẫn có slash trong một ID là hợp đồng rủi ro

Ngay cả khi caller tạo `/api/items/SKU%2FA` chuẩn, một proxy có thể chặn encoded slash hoặc một tầng routing giải mã thành hai path segments. Nếu user-controlled ID có thể chứa `/`, `..`, `%2e%2e`, dấu chấm phẩy hoặc Unicode tương đương, hãy cân nhắc:

- Dùng ID an toàn ở path, ví dụ UUID, ULID hoặc opaque key theo alphabet hạn chế.
- Chuyển giá trị phức tạp sang query parameter hoặc JSON body theo API design.
- Từ chối dữ liệu không hợp lệ ở boundary sau khi normalize, thay vì cố “né” routing bằng nhiều lần encode.
- Kiểm tra path traversal/dot-segment normalization của gateway và downstream.
- Không biến absolute URL do người dùng nhập thành đích HTTP outbound để tránh SSRF.

## 16. Unicode normalization và hợp đồng so sánh dữ liệu

Hai chuỗi tiếng Việt có thể nhìn giống nhau nhưng có biểu diễn code points khác nhau: một ký tự có dấu tổ hợp sẵn với một chữ cơ sở + dấu kết hợp. Khi percent-encode UTF-8, **các byte có thể khác** dù hình thức hiển thị gần như giống hệt.

Nếu dùng các giá trị này làm khóa cache, chữ ký hoặc ID cần so sánh chính xác, các bên phải thống nhất chính sách Unicode normalization, thường là NFC nếu nghiệp vụ phù hợp.

Ví dụ Java:

~~~java
import java.text.Normalizer;

String normalized = Normalizer.normalize(
        userInput,
        Normalizer.Form.NFC
);

// Sau khi normalize và validate, mới dùng làm URI variable.
~~~

Đừng normalize một cách tùy tiện **sau khi đã ký** request hoặc thay đổi chuỗi đã ký trước khi kiểm tra chữ ký. Với signed URLs hoặc request signing, phải thống nhất cách biểu diễn path/query, percent-encoding, thứ tự tham số và Unicode normalization. Nếu gateway và backend canonicalize khác nhau, một request có thể bị từ chối sai hoặc tạo rủi ro an ninh.

Một hệ thống không nên mặc định coi việc encode khác nhau là hai sản phẩm khác nhau chỉ vì raw URI khác; ngược lại, nếu ID được định nghĩa theo byte exact, tuyệt đối không tự normalize làm thay đổi danh tính. **Hợp đồng nghiệp vụ quyết định**, HTTP encoder chỉ thực thi.

## 17. Mã hóa URI không thay đổi service ID của LoadBalancer

Khi dùng `@LoadBalanced RestClient.Builder`, `@LoadBalanced WebClient.Builder` hoặc `@FeignClient(name="inventory-service")`, Spring Cloud LoadBalancer dựa trên **tên service logic** để lấy danh sách `ServiceInstance`.

~~~mermaid
sequenceDiagram
    participant O as Order Service
    participant C as HTTP Client
    participant L as Spring Cloud LoadBalancer
    participant S as Inventory replica

    O->>C: sku = "SKU/A&B", query = "C++"
    Note over C: Encode path/query variables
    C->>L: URI host = inventory-service
    L-->>C: ServiceInstance localhost:8082
    C->>S: GET /api/items/SKU%2FA%26B?q=C%2B%2B
    S-->>C: HTTP response
~~~

**Không encode service ID như một path variable** và cũng không lấy SKU làm host đích. LoadBalancer sẽ đổi authority thành host/port instance theo cơ chế của Spring Cloud; **path và query cần giữ nguyên ý nghĩa dữ liệu** qua bước đó.

Những lỗi có thể gặp:

- URI được dựng thành `http://inventory-service%2Fapi/...`: host sai vì dấu slash bị encode nhầm vào authority.
- Client gửi URL absolute `https://external.example/api` thay vì URL theo service ID: có thể **bỏ qua LoadBalancer** hoặc làm request đến destination ngoài dự kiến.
- Feign có `url=...` cố định: Spring Cloud OpenFeign có thể gọi URL trực tiếp, không dùng discovery dù `name` vẫn được khai báo.
- URI sau LoadBalancer đúng instance nhưng path bị double-encoded: backend vẫn trả 404/400; không phải lỗi thuật toán Round Robin/Random.

Nếu có gateway/reverse proxy giữa caller và backend, hãy kiểm tra contract **ở từng hop** vì proxy có thể normalize path, decode, rewrite route hoặc thay header trước khi request tới inventory.

## 18. HTTP errors: đọc đúng tín hiệu trước khi retry

Các tình huống header/URI sai thường biểu hiện bằng những status khác nhau:

| Status / lỗi | Nguyên nhân khả dĩ | Nên làm gì |
|---|---|---|
| `400 Bad Request` | URI percent-encoding sai, header value không hợp lệ, query binding lỗi | Kiểm tra raw request-target, schema và parser logs |
| `401 Unauthorized` | Thiếu/sai credential, duplicate Authorization gây mơ hồ | Kiểm tra token source, không log token |
| `403 Forbidden` | Credential đúng nhưng không đủ quyền hoặc policy chặn | Kiểm tra scope/audience/authorization |
| `404 Not Found` | Path segment bị tách/giải mã khác, route không tồn tại hoặc dữ liệu không tồn tại | So sánh raw URI với route và contract |
| `414 URI Too Long` | Query quá dài hoặc URL ghép sai | Chuyển filter lớn sang body hoặc rút gọn URI |
| `431 Request Header Fields Too Large` | Quá nhiều/lớn headers | Kiểm tra whitelist và proxy/server size limits |
| `502 Bad Gateway` | Gateway/proxy không nhận upstream response hợp lệ | Xem gateway logs và request/response thực |
| `503 Service Unavailable` | Không có ServiceInstance, backend/proxy quá tải hoặc ngừng phục vụ | Kiểm tra discovery, LoadBalancer và status origin |
| `504 Gateway Timeout` | Proxy chờ upstream quá lâu | Kiểm tra timeout từng hop |
| HTTP client encode exception | Dữ liệu có ký tự không hợp lệ, URI builder fail | Kiểm tra dữ liệu *trước khi gửi* và stack trace đã redact |

**Không retry vô điều kiện** những lỗi 400/414/431. Nếu caller liên tục gửi URL hoặc header sai, retry sang instance khác chỉ làm tăng tải mà không sửa contract. Retry 503 hoặc timeout cũng cần giới hạn, idempotency và ngân sách thời gian; không đồng nghĩa mọi 503 đều do một replica mất sức khỏe.

Khi OpenFeign ném `FeignException`, RestClient ném `RestClientResponseException` hoặc WebClient ném `WebClientResponseException`, tầng adapter cần ánh xạ lỗi thành cấu trúc thống nhất nhưng **không xóa mất status/cause gốc** dùng cho chẩn đoán.

## 19. Thiết kế response lỗi có cấu trúc

Một lỗi HTTP contract nên có status chính xác và nội dung dễ tìm nguyên nhân, không trả 200 cùng message chung chung. Spring Framework hỗ trợ `ProblemDetail` theo cách biểu diễn Problem Details (RFC 9457).

Ví dụ endpoint từ chối giá trị filter sai:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.server.ResponseStatusException;

// Trong một service method / controller validation:
if (query != null && query.length() > 200) {
    ProblemDetail problem = ProblemDetail.forStatus(
            HttpStatus.BAD_REQUEST
    );
    problem.setTitle("Invalid search query");
    problem.setDetail("Query parameter q is too long");
    problem.setProperty("errorCode", "INVALID_QUERY");
    throw new org.springframework.web.ErrorResponseException(
            HttpStatus.BAD_REQUEST,
            problem,
            null
    );
}
~~~

Đoạn mã minh họa sử dụng `ErrorResponseException` trong Spring Framework, behavior serialize phụ thuộc cấu hình exception handling của ứng dụng. Hoặc có thể dùng `@RestControllerAdvice` để trả `ResponseEntity<ProblemDetail>`.

**Không trả raw URI, Authorization, query chứa PII hay toàn bộ header values trong error detail**. Dùng mã lỗi ổn định, correlation ID được chuẩn hóa và message an toàn cho client. Phân biệt lỗi đầu vào với lỗi phụ thuộc để circuit breaker và metrics không đánh đồng 400 với lỗi hạ tầng.


## 20. Bài thực hành: kiểm chứng đường truyền qua hai replica

Xây môi trường local:

~~~text
order-service :8080
    |
    | RestClient / WebClient / OpenFeign
    | URI logic: http://inventory-service/debug/echo
    v
Spring Cloud LoadBalancer
    +--- inventory :8081
    +--- inventory :8082
~~~

### 20.1. Khai báo instance ở order-service

~~~yaml
server:
  port: 8080

spring:
  application:
    name: order-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
~~~

Caller cần có `spring-cloud-starter-loadbalancer` và builder hoặc Feign client có tích hợp LoadBalancer. Chạy hai tiến trình inventory ở cổng 8081 và 8082, mỗi instance cung cấp một endpoint echo nhằm quan sát query và header **đã được giải mã**.

### 20.2. Endpoint echo ở inventory-service

~~~java
package com.example.inventory;

import jakarta.servlet.http.HttpServletRequest;
import java.util.List;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class EchoController {

    private final Environment environment;

    public EchoController(Environment environment) {
        this.environment = environment;
    }

    @GetMapping("/debug/echo")
    public EchoResult echo(
            HttpServletRequest request,
            @RequestParam("q") String query,
            @RequestParam(name = "tag", required = false)
                    List<String> tags,
            @RequestHeader(name = "X-Correlation-Id", required = false)
                    String correlationId) {

        return new EchoResult(
                environment.getProperty("server.port", "unknown"),
                request.getQueryString(),
                query,
                tags == null ? List.of() : tags,
                correlationId
        );
    }

    public record EchoResult(
            String instancePort,
            String rawQuery,
            String query,
            List<String> tags,
            String correlationId
    ) {}
}
~~~

Endpoint echo dùng cho **local lab**, không xuất bản công khai request metadata trên production. Cố ý không phản hồi Authorization, Cookie hay bất kỳ secret nào.

### 20.3. Controller proxy ở order-service

Sử dụng bean `inventoryRestClient` đã khai báo với `@LoadBalanced RestClient.Builder` và `DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES`.

~~~java
package com.example.order.web;

import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class EchoProxyController {

    private final RestClient inventory;

    public EchoProxyController(
            @Qualifier("inventoryRestClient") RestClient inventory) {
        this.inventory = inventory;
    }

    @GetMapping("/proxy/echo")
    public EchoResult echo(
            @RequestParam("q") String query,
            @RequestParam("tag") List<String> tags) {

        if (tags.size() != 2) {
            throw new IllegalArgumentException(
                    "Lab requires exactly two tag values"
            );
        }

        return inventory.get()
                .uri(b -> b.path("/debug/echo")
                        .queryParam("q", "{q}")
                        .queryParam("tag", "{tag1}")
                        .queryParam("tag", "{tag2}")
                        .build(Map.of(
                                "q", query,
                                "tag1", tags.get(0),
                                "tag2", tags.get(1)
                        )))
                .headers(h -> h.set(
                        "X-Correlation-Id",
                        "e41c139f-8057-4e88-84bc-af4fc1c414a2"
                ))
                .retrieve()
                .body(EchoResult.class);
    }

    public record EchoResult(
            String instancePort,
            String rawQuery,
            String query,
            List<String> tags,
            String correlationId
    ) {}
}
~~~

Correlation ID cố định chỉ dùng cho lab; trong production hãy tạo hoặc chuẩn hóa ID ở ingress rồi propagate qua context an toàn. Controller trên giản lược exception handler để tập trung vào URI encoding.

Gọi nhiều lần từ PowerShell:

~~~powershell
1..8 | ForEach-Object {
    Invoke-RestMethod -Uri "http://localhost:8080/proxy/echo?q=C%2B%2B&tag=red&tag=blue"
}
~~~

Kiểm chứng:

- `query` mà backend thấy là `C++`, **không** là `C  `.
- `tags` chứa hai giá trị `red` và `blue`.
- `rawQuery` thường chứa `q=C%2B%2B&tag=red&tag=blue`; chi tiết có thể được proxy chuẩn hóa.
- `instancePort` cho thấy request được gửi tới `8081` hoặc `8082` qua LoadBalancer.
- `correlationId` khớp với UUID đã gắn, không phụ thuộc query.
- Thứ tự các replica phụ thuộc thuật toán, concurrency và retry, không phải bằng chứng duy nhất về encoding.

Sau đó thử giá trị `Nón xanh`, `red&blue` và literal `100%`. Dùng URI builder cho từng value và đối chiếu **giá trị gốc** với giá trị đã decode ở backend, không chỉ so text raw query.

### 20.4. Thử response có hai Set-Cookie

Tạo một endpoint thử nghiệm trả hai `Set-Cookie` qua hai lần `ResponseEntity.header(HttpHeaders.SET_COOKIE, ...)`. Dùng một HTTP test client để đọc từng cookie; không dùng `String.split(",")` vì thuộc tính `Expires` có thể chứa dấu phẩy. Với reverse proxy, kiểm tra cookie attributes, domain/path và chính sách có được phép forward cookies ra ngoài không.

## 21. Unit test và integration test cho hợp đồng URI/header

Phần mã hóa URI có thể test độc lập mà không cần khởi tạo service discovery:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.URI;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.web.util.UriComponentsBuilder;

class UriAndHeaderContractTest {

    @Test
    void encodesVariablesStrictly() {
        URI uri = UriComponentsBuilder
                .fromUriString("http://inventory-service")
                .pathSegment("api", "items", "{sku}")
                .queryParam("q", "{q}")
                .encode()
                .buildAndExpand(Map.of(
                        "sku", "SKU/A&B",
                        "q", "C++"
                ))
                .toUri();

        assertEquals(
                "/api/items/SKU%2FA%26B",
                uri.getRawPath()
        );
        assertEquals("q=C%2B%2B", uri.getRawQuery());
        assertEquals("inventory-service", uri.getHost());
    }

    @Test
    void keepsSetCookieValuesSeparateInMemory() {
        HttpHeaders headers = new HttpHeaders();
        headers.add(HttpHeaders.SET_COOKIE, "session=abc; Path=/");
        headers.add(HttpHeaders.SET_COOKIE, "theme=dark; Path=/");

        assertEquals(
                2,
                headers.get(HttpHeaders.SET_COOKIE).size()
        );
        assertTrue(
                headers.get(HttpHeaders.SET_COOKIE)
                        .get(1)
                        .startsWith("theme=")
        );
    }
}
~~~

Test URI trên kiểm tra riêng builder; test `HttpHeaders` chỉ kiểm tra dữ liệu trong bộ nhớ Java. Cả hai **không chứng minh** proxy, connector, servlet container và backend nhận đúng ở wire-level. Cần integration tests với MockWebServer, WireMock hoặc hai server thật, rồi so raw query, decoded values và các HTTP header field lines thực tế.

| Tình huống test | Input | Kỳ vọng |
|---|---|---|
| Unicode/space | `Nón xanh` | UTF-8 percent-encoding, decode nhất quán |
| Plus literal | `C++` | Không biến thành hai spaces |
| Reserved in path | `SKU/A&B` | URI builder encode, proxy có chính sách encoded slash rõ |
| Raw percent | `100%` | `100%25`, không double encode |
| Hash in query | `a#b` | `#` là dữ liệu, không thành fragment |
| Repeated query | `["red","blue"]` | Hai occurrences hoặc contract đã chọn |
| Comma in one value | `"red,blue"` | Không tự tách thành hai phần tử |
| Empty vs absent | `tag=` vs không có `tag` | Phân biệt theo API contract |
| Two Set-Cookie | Hai cookies | Không nối thành một comma-separated value |
| Duplicate Authorization | Hai credentials | Bị từ chối hoặc xử lý theo chính sách bảo mật |
| CR/LF in header | Chứa control chars | Bị reject/normalize an toàn |
| Encoded slash | `%2F` | Proxy/server phản ứng rõ ràng |
| Oversized URI/header | Vượt giới hạn | Lỗi phù hợp, không retry vòng lặp |
| Two ServiceInstances | 8081/8082 | Cùng contract encoding qua hai backend |
| Feign format | `EXPLODED` vs `CSV` | Raw query đúng định nghĩa của từng kiểu |


## 22. Bảng chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân hay gặp | Cách xử lý |
|---|---|---|
| `C++` thành `C  ` | Query literal plus chưa được percent-encode | Dùng strict URI variable encoding (`C%2B%2B`) |
| Search `red&blue` thành hai query params | Ghép query string bằng `&` | Dùng `queryParam("q", "{q}")` và expand |
| SKU `SKU/A` trả 404 | Slash bị xem là path separator hoặc encoded slash bị proxy chặn | Đổi API contract/ID hoặc quy tắc routing có kiểm soát |
| Backend nhận `SKU%2FA` thay vì `SKU/A` | Double encoding `%252F` | Chỉ encode URI variable một lần |
| `tag=red,blue` bị coi là một tag | Caller CSV nhưng server đợi repeated keys | Dùng `EXPLODED` và test wire-level |
| Client mất một cookie | Ghép `Set-Cookie` bằng dấu phẩy | Giữ hai giá trị Set-Cookie riêng |
| Header correlation bị lặp | Dùng `add` cho field chỉ cần một giá trị | Dùng `set` và chuẩn hóa ID |
| 400 xảy ra trước backend | Ký tự control hoặc URI parser/proxy chặn request | Xem log client/gateway, validate input |
| 431 liên tục | Header quá dài hoặc có quá nhiều custom fields | Dùng body/filter resource, kiểm tra giới hạn |
| 414 khi gửi danh sách ID | Query dài vượt giới hạn | Thiết kế POST search/body khi hợp đồng cho phép |
| 401 dù đã gắn bearer token | Authorization trùng, sai scope/audience hoặc proxy rewrite | Kiểm tra boundary, không in token vào logs |
| Host sai sau khi encode | Encode cả authority thay vì URI variable | Tách scheme/host/path/query bằng URI builder |
| `UnknownHostException` cho `inventory-service` | Chưa cấu hình HTTP client load-balanced | Xem `@LoadBalanced`, Feign và discovery |
| Một replica trả 400, replica khác 200 | Version schema/parser không đồng nhất | Consumer-driven contract test, triển khai tương thích |
| Cache key khác dù cùng SKU hiển thị | Unicode normalization/URI canonicalization khác | Thống nhất cách normalize và key generation |
| Retry vẫn nhận 400 | Sai contract không phải lỗi transient | Fail fast, sửa caller, không retry |

### Quy trình khoanh vùng trên đường truyền

Khi gặp lỗi, theo dõi cùng một correlation ID và đối chiếu:

1. **Input tại caller:** dữ liệu raw trước URI encoding có đúng contract không?
2. **HTTP client:** URL đã encode, header values và request method có đúng không? Không log secret/full URI chứa PII.
3. **LoadBalancer:** host logic có đúng service ID và có `ServiceInstance` được chọn không?
4. **Proxy/gateway:** request-target và header fields có bị rewrite, decode, gộp hoặc chặn không?
5. **Backend:** route, query binder, HTTP decoder và validation có hiểu đúng giá trị không?
6. **Error mapping:** status gốc 400/404/414/431/503 có được giữ lại thay vì biến thành 200 hoặc “timeout” chung chung không?

Không phụ thuộc vào việc so sánh header casing hay thứ tự các header không liên quan. Điều cần so là **ngữ nghĩa** của từng field/query/path, và thứ tự ở những field lists mà chuẩn yêu cầu bảo toàn.

## 23. Checklist trước khi đưa hợp đồng vào production

- [ ] Định nghĩa rõ mỗi header là singleton, list field hay special case như `Set-Cookie`.
- [ ] Dùng `HttpHeaders.set` cho một giá trị và `add` khi field/contract cho phép nhiều giá trị.
- [ ] Không dùng `getFirst` để âm thầm chấp nhận duplicate credentials.
- [ ] Ưu tiên typed APIs cho `Accept`, `Content-Type`, `Authorization`.
- [ ] Không parse `Set-Cookie` bằng `split(",")`; kiểm tra domain/path/SameSite/Secure.
- [ ] Chặn/chuẩn hóa CRLF, control chars và header values quá lớn.
- [ ] Không gửi Unicode tùy ý trong custom headers nếu thiếu encoding contract.
- [ ] Không relay `Host`, `Cookie`, `Authorization` và mọi inbound headers sang downstream.
- [ ] Chỉ tin forwarded headers từ proxy đáng tin cậy sau khi loại bỏ header do client giả mạo.
- [ ] Dùng URI builder, phân biệt path segment và query value.
- [ ] Encode URI variables bằng cơ chế strict encoding phù hợp, đúng một lần.
- [ ] Phân biệt URI percent-encoding với `application/x-www-form-urlencoded`.
- [ ] Không cho rằng encoded slash được mọi gateway/backend cho phép.
- [ ] Thống nhất repeated query keys, CSV hay JSON arrays trong OpenAPI/API contract.
- [ ] Với OpenFeign, test `@CollectionFormat` và `@PathVariable` ở HTTP request thực.
- [ ] Không dùng URL động chưa kiểm soát để gọi downstream, tránh SSRF và bỏ qua LoadBalancer.
- [ ] Không tự retry 400, 414, 431 như lỗi tạm thời.
- [ ] Trả lỗi có cấu trúc, status đúng, message không lộ token, query nhạy cảm.
- [ ] Thống nhất Unicode normalization khi so sánh IDs/cache keys/signatures.
- [ ] Có unit tests cho encoding và integration tests qua gateway, LoadBalancer, ít nhất hai replica.
- [ ] Kiểm thử contract khi nâng cấp Spring Framework, OpenFeign hoặc đổi HTTP connector/proxy.

## Tài liệu tham khảo

- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html#section-5.3): ngữ nghĩa HTTP fields, điều kiện kết hợp field lines và ngoại lệ `Set-Cookie`.
- [RFC 3986 — URI Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986): reserved characters, URI components và percent-encoding.
- [RFC 8187 — HTTP Header Field Parameters](https://www.rfc-editor.org/rfc/rfc8187): character encoding và language trong một số HTTP header parameters.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): mô hình lỗi HTTP có cấu trúc.
- [Spring Framework — URI Links](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-uri-building.html): `UriComponentsBuilder`, `DefaultUriBuilderFactory` và encoding modes.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): RestClient, URI templates và HTTP headers.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): xây dựng URI, xử lý response và HTTP client reactive.
- [Spring Cloud OpenFeign — Reference](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html): `@CollectionFormat`, `@SpringQueryMap`, Feign clients và LoadBalancer.
- [Spring Cloud Commons — LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): discovery, `ServiceInstance`, selection, health checks và retry.

**Kết luận:** chọn đúng service ID và `ServiceInstance` chỉ trả lời câu hỏi **gửi request tới đâu**. Một hợp đồng HTTP đáng tin cậy còn phải định nghĩa **header có bao nhiêu giá trị, ký tự nào là cú pháp hay dữ liệu, URI được encode theo component nào và xử lý lỗi ra sao**. Khi RestClient, WebClient, OpenFeign, proxy và backend cùng tuân theo một contract được kiểm thử, hệ thống giảm được lỗi 400/404/431, tránh rò rỉ header nhạy cảm, hạn chế retry vô ích và dễ truy vết sự cố hơn.

