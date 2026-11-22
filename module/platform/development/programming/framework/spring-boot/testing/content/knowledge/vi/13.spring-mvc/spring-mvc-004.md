# Kiểm tra status, header, content type và nội dung phản hồi

## 1. Bốn mặt của hợp đồng HTTP trong Spring MVC

Một endpoint Spring MVC đúng nghiệp vụ nhưng trả sai **HTTP status**, thiếu **header**, sai **Content-Type** hoặc trả **body JSON** không đúng vẫn có thể làm client hoạt động sai. Vì vậy test controller không nên chỉ kiểm tra “không có exception”; cần chứng minh những gì client thực sự nhận được.

Bốn câu hỏi chính:

1. **Status:** yêu cầu thành công, tạo tài nguyên, không có body, lỗi đầu vào hay không tìm thấy sẽ trả mã HTTP nào?
2. **Header:** các metadata quan trọng như `Location`, `Cache-Control`, `ETag`, `X-Request-Id` có đúng hợp đồng không?
3. **Content-Type:** response thực sự mang media type nào, ví dụ `application/json` hay `text/plain`? Có sai charset hoặc bị thương lượng nội dung không?
4. **Response body:** JSON có field, giá trị, kiểu dữ liệu, array, object lồng nhau, lỗi nghiệp vụ hoặc body rỗng đúng không?

Trong Spring Boot dùng **Spring MVC**, `MockMvc` là công cụ phổ biến: thực hiện xử lý request bằng Spring MVC infrastructure với mock request/response, **không cần chạy HTTP server trên cổng thật**. Một `@WebMvcTest` chuyên biệt thường đủ để kiểm tra web boundary; dùng `@SpringBootTest` nếu mục tiêu là wiring nhiều tầng hoặc server end-to-end.

Một yêu cầu có thể cần kiểm tra cả bốn phần:

~~~http
HTTP/1.1 201 Created
Location: /api/items/SKU-7
X-Catalog-Version: v1
Content-Type: application/json

{"sku":"SKU-7","name":"Notebook","quantity":2}
~~~

Đây là **hợp đồng phản hồi minh họa**. Header như `X-Catalog-Version` do ứng dụng chủ động quy định; không phải Spring tự tạo cho mọi controller. Body thực tế có thể thay đổi thứ tự các key JSON vì JSON object không có ý nghĩa thứ tự field.

**Mục tiêu kiểm thử:** chọn một hành vi cụ thể, viết request với input/headers chính xác, rồi kiểm tra HTTP output đúng contract. Không khóa test vào metadata như timestamp ngẫu nhiên, header của container hoặc chuỗi lỗi không thuộc hợp đồng.

## 2. Bộ matcher của MockMvc: kiểm tra ở đâu?

Luồng thường dùng:

~~~java
mvc.perform(get("/api/items/{sku}", "SKU-7")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(header().string("X-Catalog-Version", "v1"))
    .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.sku").value("SKU-7"));
~~~

Đoạn code là **một phần của test có bean `MockMvc mvc`**. Các builder/matcher thường được static import từ:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
~~~

Có thể dùng `.andExpect(...)` nối tiếp hoặc `.andExpectAll(...)` để gom nhiều kỳ vọng. Khi cần xem request/response đang thất bại:

~~~java
mvc.perform(get("/api/items/SKU-7"))
   .andDo(print())
   .andExpect(status().isOk());
~~~

`print()` cần static import từ `MockMvcResultHandlers.print`. Đây là công cụ **chẩn đoán cục bộ**, không nên cố định mọi stdout test theo output của logger hoặc lạm dụng in body chứa secret.

Phân biệt hai chiều:

| Thành phần | Cấu hình request | Kiểm tra response |
| --- | --- | --- |
| HTTP method/path | `get(...)`, `post(...)`, `delete(...)` | `status()`, `handler()` nếu cần |
| Request body media type | `.contentType(MediaType.APPLICATION_JSON)` | `content().contentTypeCompatibleWith(...)` |
| Response format client mong muốn | `.accept(MediaType.APPLICATION_JSON)` | `content().contentType(...)` hoặc compatible |
| Header gửi tới server | `.header("X-Trace-Id", "...")` | `header().string(...)` cho header server trả |
| Body gửi đi | `.content(json)` | `jsonPath(...)`, `content().json(...)`, `content().string(...)` |

`contentType(...)` gắn lên **request builder** không đồng nghĩa response sẽ có Content-Type đó; response do controller và message converters quyết định. `accept(...)` là tín hiệu thương lượng format mà client chấp nhận, **không phải** khẳng định response tự động đúng.

## 3. Kiểm tra HTTP status: mã và ý nghĩa phải theo tình huống

Status phản ánh ý nghĩa xử lý, không phải chỉ “bằng 200” trong mọi trường hợp.

| Tình huống | Mã phổ biến | Matcher trong MockMvc |
| --- | --- | --- |
| GET lấy dữ liệu thành công | 200 OK | `status().isOk()` |
| POST tạo tài nguyên | 201 Created | `status().isCreated()` |
| DELETE thành công không có body | 204 No Content | `status().isNoContent()` |
| DTO vi phạm validation | 400 Bad Request | `status().isBadRequest()` |
| Chưa xác thực | 401 Unauthorized | `status().isUnauthorized()` |
| Không đủ quyền | 403 Forbidden | `status().isForbidden()` |
| Tài nguyên không tồn tại | 404 Not Found | `status().isNotFound()` |
| Method không được hỗ trợ ở route | 405 Method Not Allowed | `status().isMethodNotAllowed()` |
| Client yêu cầu media type response không thể sinh | 406 Not Acceptable | `status().isNotAcceptable()` |
| Request gửi media type không được controller hỗ trợ | 415 Unsupported Media Type | `status().isUnsupportedMediaType()` |
| Xung đột trạng thái tài nguyên | 409 Conflict | `status().isConflict()` |

Một số phản hồi như 202 Accepted, 206 Partial Content, 304 Not Modified có ý nghĩa riêng; test phải đi từ hợp đồng API, không tự nâng/mặc định mã. Nếu muốn kiểm tra số cụ thể ngoài các matcher tên gọi, dùng `status().is(422)` (khi API thật sự quy định 422) hoặc matcher tương ứng được hỗ trợ.

### Các bẫy khi chỉ test status

- `status().isOk()` **không chứng minh body đúng**. Controller trả 200 với body thiếu `sku` vẫn có thể PASS.
- `status().isNotFound()` **không chứng minh error JSON đúng**. Tùy controller/advice, response 404 có thể rỗng hoặc có error body.
- `status().isCreated()` không chứng minh có `Location`; nếu hợp đồng yêu cầu Location phải assert riêng.
- `status().isNoContent()` không đủ để khẳng định body trống; nên assert `content().string("")` khi bảo vệ quy tắc 204.
- Status 400 do validation khác status 400 do JSON sai cú pháp; tùy mục tiêu có thể cần test hai nguyên nhân riêng.

Không tạo test “GET không tồn tại” bằng cách gọi **một path hoàn toàn không khai báo** nếu mục tiêu là nhánh service trả empty. Path 404 do router không biết endpoint là một hợp đồng khác với `GET /api/items/{sku}` trả 404 vì SKU không tồn tại.

## 4. Header: metadata cũng là một phần contract

HTTP header có thể điều khiển redirect, cache, auth, ETag, cookie, encoding và trace. Spring MVC cho phép trả header bằng `ResponseEntity` hoặc API của response.

| Header | Khi nào kiểm tra | Ví dụ matcher |
| --- | --- | --- |
| `Location` | POST tạo tài nguyên, redirect | `header().string(HttpHeaders.LOCATION, "/api/items/SKU-7")` |
| `Cache-Control` | API không được cache hoặc cache theo TTL | `header().string(HttpHeaders.CACHE_CONTROL, "no-store")` |
| `ETag` | Cache validation/optimistic representation | `header().string(HttpHeaders.ETAG, "\"v1\"")` |
| `X-Catalog-Version` | Header ứng dụng định nghĩa | `header().string("X-Catalog-Version", "v1")` |
| `Vary` | Response phụ thuộc `Accept`/`Origin` | Assert những giá trị hợp đồng; chú ý nhiều token |
| `Content-Type` | Kiểu body response | Ưu tiên `content().contentType...` |
| `Content-Disposition` | Download file, filename | Kiểm tra khi controller chủ động tạo |
| `Set-Cookie` | Session/auth/cookie riêng | `cookie()` matchers hoặc header phù hợp |

Các matcher thường dùng:

~~~java
.andExpect(header().exists(HttpHeaders.LOCATION))
.andExpect(header().string(HttpHeaders.LOCATION, "/api/items/SKU-7"))
.andExpect(header().doesNotExist("X-Deprecated-Flag"))
~~~

Đây là **đoạn chuỗi `andExpect` minh họa**. `header().string(...)` kiểm tra giá trị của một header; `header().exists(...)` chứng minh header có mặt. Nếu header có nhiều giá trị, dùng matcher nhiều giá trị thích hợp, không tự nối chuỗi bằng dấu phẩy rồi so sánh khi parser có thể xử lý token/casing khác.

### Không dùng exact string cho header động

`Date`, correlation ID, token hay ETag sinh động không nên assert với một giá trị ngẫu nhiên cố định. Thay vào đó:

- Assert header **tồn tại** nếu hợp đồng chỉ yêu cầu hiện diện.
- Assert **đúng format** bằng Hamcrest matcher/regex hoặc parse thành kiểu có ý nghĩa.
- Nếu giá trị phải được phản chiếu từ request, cung cấp một ID cố định rồi assert chính giá trị đó.
- Chỉ kiểm tra exact `Location` khi path/URI có hợp đồng ổn định; với host/port ngẫu nhiên, parse URI và so sánh `path`/`scheme` theo yêu cầu.

Tên header HTTP **không phân biệt hoa/thường** theo giao thức, nhưng ký tự và spacing trong **giá trị** có thể quan trọng. Không viết test đòi `Content-Type` phải được lưu bằng casing `Content-Type` thay vì `content-type` nếu đó không phải hợp đồng.

## 5. Content-Type: JSON đúng không chỉ ở tên media type

`Content-Type` trong **response** nói body được biểu diễn theo kiểu nào. Với JSON API thường là `application/json`, nhưng framework/converter có thể thêm tham số như `charset=UTF-8` hoặc trả một media type chuyên biệt như `application/problem+json`.

Hai kiểu matcher quan trọng:

~~~java
.andExpect(content().contentType(MediaType.APPLICATION_JSON))
~~~

Matcher trên so sánh đầy đủ media type (bao gồm tham số). Nếu response là `application/json;charset=UTF-8` thì **không nhất thiết bằng** `MediaType.APPLICATION_JSON`.

~~~java
.andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON))
~~~

Matcher này kiểm tra tính **tương thích media type** và thường tốt khi hợp đồng chỉ là “response là JSON”, không cố định tham số charset. Nếu hợp đồng thật sự đòi cụ thể `charset`, dùng `content().encoding(...)` hoặc kiểm tra media type đã parse theo nhu cầu.

### Request Content-Type và Accept không đồng nghĩa

~~~http
POST /api/items
Content-Type: application/json
Accept: application/json

{"sku":"SKU-7","name":"Notebook","quantity":2}
~~~

- `Content-Type` đầu vào: server cần hiểu **dữ liệu client gửi**, ví dụ JSON.
- `Accept` đầu vào: client nói nó **muốn nhận** loại media type nào.
- `Content-Type` đầu ra: server thực tế đã **chọn và sinh** loại response nào.

Nếu method có `@PostMapping(consumes = "application/json")` mà client gửi `text/plain`, thường nhận **415**. Nếu `@GetMapping(produces = "application/json")` nhưng client chỉ chấp nhận `application/xml`, thường nhận **406**. Những test này phải kiểm tra rằng controller/request mapping thật được cấu hình đúng và không có converter khác đáp ứng media type.

### Không ép Content-Type vào phản hồi không có body

`204 No Content` không có response body. Không nên assert rằng mọi phản hồi 204/304/404 rỗng **phải có** `application/json`: nếu code không viết body, message converter có thể không đặt Content-Type. Tương tự, không mặc định mọi exception trong một `@WebMvcTest` đều có error JSON định dạng giống server production; cấu hình `@ControllerAdvice` và error handling quyết định điều đó.

## 6. Response body: so sánh đúng dạng dữ liệu

### JSONPath cho trường quan trọng

~~~java
.andExpect(jsonPath("$.sku").value("SKU-7"))
.andExpect(jsonPath("$.quantity").value(2))
.andExpect(jsonPath("$.name").value("Notebook"))
~~~

JSONPath đi vào **cấu trúc JSON đã parse**, không phụ thuộc khoảng trắng hay thứ tự key. Với nested object, dùng `$.customer.id`; với array, dùng `$[0].sku` hoặc `$.items[0].sku`. Các matcher `exists()`, `doesNotExist()`, `isArray()`, `isNotEmpty()` hữu ích nhưng phải chọn đúng ý nghĩa.

**Phân biệt tồn tại và null:** `jsonPath("$.middleName").doesNotExist()` thể hiện yêu cầu key vắng mặt theo cách matcher xử lý; nó không cùng nghĩa với “key có mặt với value `null`”. Khi yêu cầu phân biệt cả ba trạng thái **vắng mặt / JSON null / chuỗi rỗng**, parse response JSON thành `JsonNode` và kiểm tra `has`/`isNull`/`asText`.

### content().json cho object hoặc array

Với Spring Framework 6.2+:

~~~java
.andExpect(content().json(
        """
        {"sku":"SKU-7","name":"Notebook","quantity":2}
        """,
        JsonCompareMode.STRICT
))
~~~

`JsonCompareMode` là `org.springframework.test.json.JsonCompareMode`. `STRICT` không cho field thừa và yêu cầu đúng thứ tự của array, nhưng **không buộc thứ tự các field của JSON object**. `LENIENT` cho phép JSON object có field bổ sung và có thể không cần giữ thứ tự array theo luật comparator. Nếu API có hợp đồng kín về schema, `STRICT` có thể giúp phát hiện field thừa; nếu API chủ đích bổ sung field theo thời gian mà test không quan tâm, JSONPath cho field quan trọng thường bền hơn.

Các helper so sánh JSON có thể cần thư viện JSONassert trên classpath; với Spring Boot 3.5 `spring-boot-starter-test` thông thường đã có test dependencies phù hợp.

### content().string cho text và body rỗng

Nếu endpoint trả text rõ ràng:

~~~java
.andExpect(content().string("ready"))
~~~

Nếu hợp đồng yêu cầu không trả body:

~~~java
.andExpect(content().string(""))
~~~

**Không so sánh JSON như chuỗi thô** nếu thứ tự property hoặc spacing không phải một phần hợp đồng. Ví dụ `{"a":1,"b":2}` và `{"b":2,"a":1}` là cùng một JSON object theo ý nghĩa dữ liệu nhưng khác raw string.

## 7. Ví dụ chạy được: Spring Boot 3.5, Java 17, @WebMvcTest và MockMvc

Ta xây dựng một API `/api/items`. Theo hợp đồng:

- `GET /api/items/{sku}`: trả **200**, header `X-Catalog-Version: v1`, `Cache-Control: no-store`, `Content-Type: application/json` và body mặt hàng nếu tìm thấy; trả **404** và body rỗng nếu SKU không có.
- `POST /api/items` nhận JSON chứa SKU, name, quantity hợp lệ: trả **201**, header `Location` trỏ đến URI tài nguyên, header version và JSON body đã tạo. Với dữ liệu vi phạm validation, trả **400** trước khi gọi catalog.
- `DELETE /api/items/{sku}`: trả **204** và body rỗng khi xóa thành công, hoặc **404** nếu không có.

Tất cả tệp cùng package `com.example.mvctest`, Java 17+, JUnit Jupiter. Bài test dùng một **controller thật**, mock `ItemCatalog` ở Spring context. Không mở HTTP port, không gọi database.

### 7.1. Ứng dụng mẫu

**Tệp `src/main/java/com/example/mvctest/MvcTestApplication.java`:**

~~~java
package com.example.mvctest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcTestApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcTestApplication.class, args);
    }
}
~~~

Đây là lớp cấu hình gốc để Spring Boot test phát hiện. `@WebMvcTest` vẫn chỉ khởi tạo một **web slice**, không chạy `main` và không tự scan mọi service/repository của ứng dụng.

**Tệp `src/main/java/com/example/mvctest/ItemView.java`:**

~~~java
package com.example.mvctest;

public record ItemView(String sku, String name, int quantity) {
}
~~~

**Tệp `src/main/java/com/example/mvctest/CreateItemRequest.java`:**

~~~java
package com.example.mvctest;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record CreateItemRequest(
        @NotBlank String sku,
        @NotBlank String name,
        @Min(1) int quantity
) {
}
~~~

Các constraint của `CreateItemRequest` chạy khi Spring MVC xử lý `@Valid @RequestBody` và có Jakarta validation provider phù hợp. Java record tự nó **không chạy validation** khi được tạo qua `new`.

**Tệp `src/main/java/com/example/mvctest/ItemCatalog.java`:**

~~~java
package com.example.mvctest;

import java.util.Optional;

public interface ItemCatalog {
    Optional<ItemView> findBySku(String sku);

    ItemView create(CreateItemRequest request);

    boolean remove(String sku);
}
~~~

Đây là collaborator giả lập trong web slice. Trong ứng dụng thực, interface này có thể được triển khai bằng một service gọi repository. Test controller chỉ cần thiết lập hành vi của mock và kiểm tra HTTP contract, **không kiểm thử persistence**.

### 7.2. Controller thật trả status/header/body có chủ đích

**Tệp `src/main/java/com/example/mvctest/ItemController.java`:**

~~~java
package com.example.mvctest;

import java.net.URI;

import jakarta.validation.Valid;

import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.util.UriComponentsBuilder;

@RestController
@RequestMapping("/api/items")
public class ItemController {
    private final ItemCatalog catalog;

    public ItemController(ItemCatalog catalog) {
        this.catalog = catalog;
    }

    @GetMapping(
            value = "/{sku}",
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<ItemView> findBySku(
            @PathVariable String sku
    ) {
        return catalog.findBySku(sku)
                .map(item -> ResponseEntity.ok()
                        .cacheControl(CacheControl.noStore())
                        .header("X-Catalog-Version", "v1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .body(item))
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<ItemView> create(
            @Valid @RequestBody CreateItemRequest request
    ) {
        ItemView saved = catalog.create(request);
        URI location = UriComponentsBuilder
                .fromPath("/api/items/{sku}")
                .encode()
                .buildAndExpand(saved.sku())
                .toUri();

        return ResponseEntity.created(location)
                .header("X-Catalog-Version", "v1")
                .contentType(MediaType.APPLICATION_JSON)
                .body(saved);
    }

    @DeleteMapping("/{sku}")
    public ResponseEntity<Void> delete(@PathVariable String sku) {
        if (catalog.remove(sku)) {
            return ResponseEntity.noContent().build();
        }
        return ResponseEntity.notFound().build();
    }
}
~~~

Điểm quan trọng trong controller:

- `ResponseEntity.ok()` thiết lập 200; `created(location)` thiết lập 201 + `Location`; `noContent()` thiết lập 204.
- `CacheControl.noStore()` tạo directive `Cache-Control: no-store`, có ý nghĩa “không lưu response”.
- `contentType(MediaType.APPLICATION_JSON)` chủ động xác định response JSON cho trường hợp có body.
- `UriComponentsBuilder.fromPath(...).encode().buildAndExpand(...)` tạo URI path và mã hóa biến đường dẫn thích hợp; trong test, SKU giả định là `SKU-7` nên Location ổn định.
- `@Valid` đảm bảo payload sai được xử lý tại web boundary trước khi gọi `catalog.create(...)`, nếu provider validation có trên classpath.
- GET không tìm thấy và DELETE không tìm thấy chủ động trả `ResponseEntity.notFound().build()` với body rỗng; **đừng giả định** một JSON error envelope có mặt nếu chưa được thiết kế.

### 7.3. Test kiểm tra đủ bốn mặt phản hồi

**Tệp `src/test/java/com/example/mvctest/ItemControllerTest.java`:**

~~~java
package com.example.mvctest;

import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.json.JsonCompareMode;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ItemController.class)
class ItemControllerTest {
    @Autowired
    MockMvc mvc;

    @MockitoBean
    ItemCatalog catalog;

    @Test
    void getItem_whenFound_returns200HeadersJsonAndFields()
            throws Exception {
        ItemView item = new ItemView("SKU-7", "Notebook", 2);
        when(catalog.findBySku("SKU-7"))
                .thenReturn(Optional.of(item));

        mvc.perform(get("/api/items/{sku}", "SKU-7")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "X-Catalog-Version", "v1"
                ))
                .andExpect(header().string(
                        HttpHeaders.CACHE_CONTROL, "no-store"
                ))
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON
                ))
                .andExpect(jsonPath("$.sku").value("SKU-7"))
                .andExpect(jsonPath("$.name").value("Notebook"))
                .andExpect(jsonPath("$.quantity").value(2))
                .andExpect(content().json(
                        """
                        {"sku":"SKU-7","name":"Notebook","quantity":2}
                        """,
                        JsonCompareMode.STRICT
                ));

        verify(catalog).findBySku("SKU-7");
    }

    @Test
    void getItem_whenUnknown_returns404AndEmptyBody()
            throws Exception {
        when(catalog.findBySku("MISSING"))
                .thenReturn(Optional.empty());

        mvc.perform(get("/api/items/{sku}", "MISSING")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isNotFound())
                .andExpect(content().string(""));

        verify(catalog).findBySku("MISSING");
    }

    @Test
    void postItem_whenValid_returns201LocationHeadersAndJson()
            throws Exception {
        CreateItemRequest request =
                new CreateItemRequest("SKU-7", "Notebook", 2);
        ItemView saved = new ItemView("SKU-7", "Notebook", 2);
        when(catalog.create(request)).thenReturn(saved);

        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "sku":"SKU-7",
                                  "name":"Notebook",
                                  "quantity":2
                                }
                                """))
                .andExpect(status().isCreated())
                .andExpect(header().string(
                        HttpHeaders.LOCATION, "/api/items/SKU-7"
                ))
                .andExpect(header().string(
                        "X-Catalog-Version", "v1"
                ))
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON
                ))
                .andExpect(jsonPath("$.sku").value("SKU-7"))
                .andExpect(jsonPath("$.quantity").value(2));

        verify(catalog).create(request);
    }

    @Test
    void postItem_whenInvalid_returns400BeforeCallingCatalog()
            throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "sku":" ",
                                  "name":"Notebook",
                                  "quantity":0
                                }
                                """))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(catalog);
    }

    @Test
    void postItem_whenRequestIsText_returns415()
            throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.TEXT_PLAIN)
                        .content("not-json"))
                .andExpect(status().isUnsupportedMediaType());

        verifyNoInteractions(catalog);
    }

    @Test
    void getItem_whenClientAcceptsOnlyXml_returns406()
            throws Exception {
        mvc.perform(get("/api/items/{sku}", "SKU-7")
                        .accept(MediaType.APPLICATION_XML))
                .andExpect(status().isNotAcceptable());

        verifyNoInteractions(catalog);
    }

    @Test
    void deleteItem_whenRemoved_returns204AndEmptyBody()
            throws Exception {
        when(catalog.remove("SKU-7")).thenReturn(true);

        mvc.perform(delete("/api/items/{sku}", "SKU-7"))
                .andExpect(status().isNoContent())
                .andExpect(content().string(""));

        verify(catalog).remove("SKU-7");
    }

    @Test
    void deleteItem_whenMissing_returns404()
            throws Exception {
        when(catalog.remove("MISSING")).thenReturn(false);

        mvc.perform(delete("/api/items/{sku}", "MISSING"))
                .andExpect(status().isNotFound())
                .andExpect(content().string(""));

        verify(catalog).remove("MISSING");
    }
}
~~~

### Giải thích từng nhóm assertion

1. **GET 200:** kết hợp `status`, hai response header, Content-Type, JSONPath của ba field và so sánh JSON nghiêm ngặt. Kiểm tra bổ sung `verify` cho biết controller dùng đúng SKU.
2. **GET 404:** test cùng route `/api/items/{sku}` với dependency trả `Optional.empty()`. Đây là **nhánh nghiệp vụ thiếu tài nguyên**, không phải chỉ 404 do URL sai.
3. **POST 201:** kiểm tra status, `Location` tương ứng tài nguyên đã tạo, header tùy chỉnh, JSON media type và body được trả.
4. **POST 400:** `@Valid` từ chối SKU blank và quantity bằng 0; mock catalog không được gọi. Test chủ động **không assert error JSON body** vì ví dụ không định nghĩa error handler/body chung.
5. **POST 415:** controller chỉ `consumes = application/json`, nhưng request là `text/plain`.
6. **GET 406:** method chỉ `produces = application/json`, nhưng client chỉ `Accept: application/xml`.
7. **DELETE 204/404:** chứng minh mã status và body rỗng theo đúng kết quả của collaborator.

### Vì sao không cần @SpringBootTest?

`@WebMvcTest(ItemController.class)` nạp MVC controller, converter, validation, advice/filter nằm trong phạm vi slice và `MockMvc`. `ItemCatalog` là collaborator ngoài slice nên dùng `@MockitoBean` tạo bean mock trong context. Cách này kiểm thử **HTTP contract của controller** mà không cần service/repository thật.

Trong Spring Boot 3.4/3.5, `@MockitoBean` đến từ Spring Framework 6.2. Nếu dự án Boot 3.3 trở về trước, API phù hợp có thể là `@MockBean` của Spring Boot; phải chọn annotation đúng version. Không dùng `@Mock` thuần với kỳ vọng nó thay Spring bean.

Nếu ứng dụng có Spring Security, filter chain có thể làm test trả 401/403 trước controller. Ví dụ giả định **không cài security**; trong dự án có security, dùng spring-security-test và thiết lập auth/CSRF đúng hợp đồng thay vì vô điều kiện tắt filter.

## 8. Phụ thuộc, cấu trúc dự án và lệnh chạy

Trong dự án **Spring Boot 3.5.x, Java 17**, sử dụng Gradle Groovy DSL, phần dependency/test task liên quan:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đây là **đoạn `build.gradle`**, giả định project đã có plugin Spring Boot 3.5.x, repositories, dependency management và Java toolchain/JDK 17+.

- `spring-boot-starter-web` cung cấp Spring MVC, Jackson và servlet web infrastructure.
- `spring-boot-starter-validation` cung cấp Jakarta validation API/provider để `@Valid` + `@NotBlank`/`@Min` thực thi.
- `spring-boot-starter-test` cung cấp JUnit Jupiter, MockMvc, Mockito và các test helpers, trong đó có JSON comparison support.

Đặt đúng 6 tệp (application, 3 model/interface/controller và test; đếm đủ các tệp `MvcTestApplication`, `ItemView`, `CreateItemRequest`, `ItemCatalog`, `ItemController`, `ItemControllerTest`) vào đường dẫn ở phần 7.

Chạy từ thư mục có Gradle Wrapper:

~~~bash
./gradlew test --tests "com.example.mvctest.ItemControllerTest"
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "com.example.mvctest.ItemControllerTest"
~~~

Khi dependency và cấu hình phù hợp, bộ tám test sẽ PASS. Các test không chủ động in `System.out.println` nên **không có stdout cố định** từ mã ứng dụng; output của Gradle/JUnit thay đổi theo mức logging và phiên bản. Đây là code có dependency Spring/Mockito/JUnit, không chạy bằng `javac ItemControllerTest.java` thuần nếu chưa tạo classpath tương ứng.

## 9. Khi cần kiểm tra body lỗi JSON thống nhất

Nhiều API không muốn trả response body rỗng cho các lỗi 400/404, mà áp dụng error envelope:

~~~json
{
  "code": "ITEM_NOT_FOUND",
  "message": "Item does not exist"
}
~~~

Đây chỉ là **đặc tả minh họa**, không phải JSON tự động của mọi `@WebMvcTest`. Muốn test body lỗi một cách có nghĩa, controller hoặc `@ControllerAdvice` phải thực sự trả object đó, và test slice phải nạp advice tương ứng.

Một cách viết riêng ở controller:

~~~java
record ApiError(String code, String message) {
}

@GetMapping("/{sku}")
public ResponseEntity<?> findBySku(@PathVariable String sku) {
    return catalog.findBySku(sku)
            .<ResponseEntity<?>>map(item -> ResponseEntity.ok(item))
            .orElseGet(() -> ResponseEntity.status(404)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(new ApiError(
                            "ITEM_NOT_FOUND", "Item does not exist"
                    )));
}
~~~

**Đoạn code này là một phương án thay thế**, không phải một method được dán thêm vào `ItemController` ở phần 7 (vì trùng `@GetMapping`). Nó cần các import/record cùng class. Khi chọn phương án đó, test lỗi mới có cơ sở để kiểm tra:

~~~java
.andExpect(status().isNotFound())
.andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON))
.andExpect(jsonPath("$.code").value("ITEM_NOT_FOUND"))
.andExpect(jsonPath("$.message").value("Item does not exist"))
~~~

Đừng trộn expected error body của phương án thay thế vào test của controller ban đầu, nơi nhánh `notFound().build()` chủ động không trả body.

### @ControllerAdvice và handler exception

Nếu sử dụng `@RestControllerAdvice` để map exception thành body (hoặc `ProblemDetail`), test nên kiểm tra **status + Content-Type + các field ổn định** như `code`/`type`/`title`/`status` theo API. Tránh assert nguyên văn timestamp, detail được quốc tế hóa hoặc đường dẫn server tự thêm nếu chúng không phải hợp đồng.

Spring Framework có `ProblemDetail`/RFC Problem Details và media type thường là `application/problem+json`. Nếu ứng dụng thực sự trả `application/problem+json`, so sánh theo đúng contract đó; **không ép bằng `MediaType.APPLICATION_JSON`** khi media type đã được chọn riêng cho Problem Details.

## 10. Kiểm tra array, nested object, null và trường thiếu

Với một API liệt kê mặt hàng:

~~~json
{
  "items": [
    {"sku":"A-1","quantity":2},
    {"sku":"B-2","quantity":5}
  ],
  "total": 2,
  "nextPage": null
}
~~~

Ta có thể kiểm tra cấu trúc bằng JSONPath:

~~~java
.andExpect(jsonPath("$.items").isArray())
.andExpect(jsonPath("$.items[0].sku").value("A-1"))
.andExpect(jsonPath("$.items[1].quantity").value(5))
.andExpect(jsonPath("$.total").value(2))
~~~

Đây là **đoạn matcher minh họa** cho endpoint thực sự trả JSON trên, không phải method mới trong bộ test phần 7. Những assertion này kiểm tra array order nếu API quy định sort; nếu danh sách không bảo đảm thứ tự, không nên assert cứng index mà hãy so sánh nội dung theo tập hoặc sắp xếp/ổn định dữ liệu đầu vào.

Nếu muốn phân biệt key `nextPage` **có mặt và null** với key bị loại bỏ, có thể parse JSON bằng Jackson:

~~~java
MvcResult result = mvc.perform(get("/api/items"))
        .andExpect(status().isOk())
        .andReturn();

JsonNode body = objectMapper.readTree(
        result.getResponse().getContentAsString()
);

assertTrue(body.has("nextPage"));
assertTrue(body.get("nextPage").isNull());
~~~

Đây là **đoạn mã trong test giả định có endpoint `GET /api/items`**, bean `ObjectMapper objectMapper`, import `MvcResult`, `JsonNode` và `assertTrue`; không chạy độc lập. `has(...)` cho biết field hiện diện ngay cả khi giá trị JSON null, còn `isNull()` xác định field đó thực sự chứa JSON null.

Đối với object có trường phụ, `content().json(..., JsonCompareMode.STRICT)` có thể hữu ích nếu API công bố schema cố định. Với API mở rộng được, chỉ assert các field contract cần thiết; không test sự vắng mặt của tất cả field khác trừ khi bảo mật/compatibility yêu cầu.

## 11. Ảnh hưởng của Content Negotiation, MessageConverter và encoding

Khi controller trả object Java, Spring MVC dùng `HttpMessageConverter` để biến object thành byte response. Jackson JSON converter thường tạo body JSON nếu Jackson trên classpath, endpoint hỗ trợ JSON và client chấp nhận media type.

Quy trình khái quát:

~~~text
MockMvc.perform(request)
    -> HandlerMapping: tìm route
    -> ArgumentResolver: bind input, @RequestBody
    -> Validation (nếu @Valid và provider)
    -> Controller gọi collaborator
    -> ReturnValueHandler xử lý ResponseEntity
    -> HttpMessageConverter serialize body
    -> MockHttpServletResponse
    -> status / headers / content type / body
~~~

Sơ đồ không bao gồm mọi filter, interceptor, advice và proxy, nhưng đủ giải thích **vì sao test phải đi qua MockMvc** thay vì chỉ gọi `controller.findBySku("SKU-7")` nếu mục tiêu là HTTP response.

- Gọi controller trực tiếp có thể chứng minh `ResponseEntity.getStatusCode()` và một số header tự tạo, nhưng **không chứng minh JSON serialization, request mapping hoặc media negotiation**.
- `.accept(MediaType.APPLICATION_JSON)` chỉ khai báo khả năng nhận JSON; nếu controller cấu hình `produces` sai hoặc thiếu converter, response có thể fail 406/500.
- `.contentType(MediaType.APPLICATION_JSON)` trên request nói parser dùng JSON; nếu body sai cú pháp, Spring có thể báo 400 trước khi gọi method.
- Với text response, charset có thể ảnh hưởng `getContentAsString()`. Nếu test cần kiểm tra Unicode chính xác, cấu hình encoding rõ và dùng `content().encoding(StandardCharsets.UTF_8)` khi đó là hợp đồng.

**Không mặc định có `charset=UTF-8` trong mọi `application/json`**. Theo chuẩn JSON hiện đại, UTF-8 là lựa chọn thông dụng nhưng Spring/Jackson thường không thêm charset vào Content-Type JSON. `contentTypeCompatibleWith` phù hợp khi chỉ cần media type, còn `encoding(...)` phù hợp khi encoding thật sự là yêu cầu.

## 12. Khi nào nên dùng matcher linh hoạt thay vì so khớp tuyệt đối?

| Loại kiểm tra | Chính xác tuyệt đối khi | Linh hoạt hơn khi |
| --- | --- | --- |
| HTTP status | Mã cụ thể là hợp đồng, ví dụ POST phải 201 | Chỉ test nhóm 2xx ít khi đủ cho API công khai |
| Header Location | Đường dẫn cố định và được yêu cầu | Host/port dynamic: parse URI, kiểm tra path |
| Header Cache-Control | Chuỗi directive được API quy định | Có thêm directive hợp lệ, nên parse token theo hợp đồng |
| Content-Type | Giao thức quy định đầy đủ media type/params | JSON có thể kèm charset: compatible |
| JSON body | API schema cố định, không cho field thừa | API extensible: JSONPath các trường thiết yếu |
| Text body | Chuỗi nguyên văn là contract | Thông điệp localized/log thông thường không ổn định |
| Array order | API có sort rõ ràng | Không có sort: so sánh không phụ thuộc thứ tự |
| Timestamp | Input dùng Clock cố định | Dữ liệu thời gian thực: kiểm tra format/range hợp lý |

### Các matcher hữu ích ngoài ví dụ

~~~java
.andExpect(header().exists("X-Trace-Id"))
.andExpect(header().doesNotExist("X-Deprecated-Flag"))
.andExpect(content().string(""))
.andExpect(jsonPath("$.items").isArray())
.andExpect(jsonPath("$.items[0].sku").exists())
~~~

Đây là **đoạn matcher minh họa**. Không áp dụng đồng thời cho một endpoint không có array/items. Viết assertion theo output **thực sự được thiết kế**, không dựa vào những thành phần có vẻ “nên có”.

Đối với `ETag`, giá trị thường được đặt trong dấu nháy kép theo giao thức; nếu controller cấu hình `eTag("v1")`, có thể kỳ vọng header kiểu `ETag: "v1"`. Nếu API hỗ trợ điều kiện `If-None-Match`/304, kiểm tra cả behavior conditional GET riêng; chỉ test header ETag hiện diện chưa chứng minh cơ chế cache validation đầy đủ.

## 13. Response status khác với resolved exception và handler

MockMvc còn có matcher kiểm tra Spring MVC nội bộ:

~~~java
.andExpect(handler().handlerType(ItemController.class))
.andExpect(handler().methodName("findBySku"))
~~~

Đây là **đoạn matcher bổ sung**, cần static import `MockMvcResultMatchers.handler`. Nó hữu ích nếu test cần chắc chắn route được map đến method cụ thể, nhưng có thể khiến test gãy khi refactor controller mà HTTP contract vẫn đúng.

Với lỗi HTTP, có thể kiểm tra exception đã được `@ControllerAdvice`/resolver xử lý bằng `result.getResolvedException()` (sau `andReturn()`). Tuy nhiên, client **không nhìn thấy** Java exception; chúng nhìn thấy status/header/body. Vì thế **ưu tiên assert HTTP contract**; chỉ assert exception class khi đó là mục tiêu đặc biệt của test framework.

`MockMvc` chạy qua Spring MVC request handling trên mock servlet objects, **không qua một servlet container thật**. Những hành vi phụ thuộc error page mapping của container, compression ở reverse proxy, TLS hay header do gateway thêm **không được chứng minh** bằng web slice. Muốn test end-to-end socket thật, dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` với client phù hợp và môi trường kiểm thử thật.

## 14. Những lỗi thường gặp khi test status/header/content/body

1. **Chỉ assert 200.** Test xanh dù response JSON sai field hoặc thiếu header. **Cách sửa:** kiểm tra những phần contract thiết yếu.
2. **Nhầm request `Content-Type` với response `Content-Type`.** `.contentType(...)` trước `perform` không chứng minh đầu ra. **Cách sửa:** dùng `content().contentType...` sau perform.
3. **Nhầm `Accept` với loại body request.** Client nhận JSON không có nghĩa payload nó gửi là JSON. **Cách sửa:** dùng cả hai đúng vai trò.
4. **Dùng `content().string(exactJson)` với JSON.** Thứ tự field/whitespace không ổn định theo contract. **Cách sửa:** `jsonPath` hoặc `content().json`.
5. **So sánh `application/json` tuyệt đối khi server thêm charset.** Test gãy vì tham số không phải contract. **Cách sửa:** `contentTypeCompatibleWith(MediaType.APPLICATION_JSON)`.
6. **Đòi Content-Type JSON trên 204/404 body rỗng.** Converter có thể không chạy. **Cách sửa:** assert status và empty body; chỉ assert Content-Type nếu API quy định.
7. **Test 404 bằng URL sai thay vì nhánh service không tìm thấy.** Không chứng minh controller xử lý missing record. **Cách sửa:** stub collaborator trả empty trên route đúng.
8. **POST 201 nhưng quên Location.** Client không biết URI tài nguyên mới theo hợp đồng API. **Cách sửa:** assert `HttpHeaders.LOCATION`.
9. **Đặt mock Mockito `@Mock` và tưởng controller Spring nhận nó.** Bean controller có thể vẫn dùng dependency khác/không tạo được. **Cách sửa:** `@MockitoBean` theo version trong Spring TestContext.
10. **Assert nguyên văn error JSON chưa được thiết kế.** Body Boot/resolver có thể rỗng hoặc khác cấu hình. **Cách sửa:** tạo error contract qua advice/controller rồi assert field ổn định.
11. **Bỏ qua security filter.** Test nhận 401/403 do request chưa auth/CSRF và bị hiểu sai là lỗi controller. **Cách sửa:** cấu hình spring-security-test đúng mục tiêu.
12. **Đóng đinh header/time/ID động.** Test fail ngẫu nhiên khi timestamp hoặc cổng thay đổi. **Cách sửa:** cố định input hoặc assert cấu trúc/format.
13. **Không kiểm tra 415/406.** Định nghĩa `consumes`/`produces` có thể bị sửa sai mà test happy path không phát hiện. **Cách sửa:** thêm negative tests cho content negotiation nếu thuộc contract.
14. **Gọi controller trực tiếp rồi nhận là đã test HTTP.** Message converters và request mapping không được thực thi. **Cách sửa:** dùng MockMvc.
15. **Dùng @SpringBootTest cho mọi phép so sánh JSON.** Khởi động toàn bộ hệ thống không cần thiết. **Cách sửa:** `@WebMvcTest` cho MVC boundary hoặc `@JsonTest` nếu chỉ kiểm tra serialization.
16. **Dùng regex/substring thay JSON parser cho field nested.** Dễ nhận sai nếu body thay formatting. **Cách sửa:** JSONPath/Jackson JsonNode.
17. **Kiểm tra mọi header mặc định/stack trace.** Làm test phụ thuộc implementation của container/framework. **Cách sửa:** chỉ assert header do hợp đồng yêu cầu.
18. **Không test trường hợp thiếu body.** DELETE trả 204 nhưng vô tình gửi JSON vẫn có thể lọt. **Cách sửa:** thêm `content().string("")`.

## 15. Quy trình thực hành và checklist cho code review

Khi nhận yêu cầu kiểm tra một endpoint Spring MVC:

1. **Viết bảng HTTP contract:** method + path, request headers/body, status, response headers/body cho mỗi tình huống.
2. **Chọn tầng test:** `@WebMvcTest` nếu chỉ web boundary, `@JsonTest` nếu chỉ mapper JSON, `@SpringBootTest` nếu cần toàn hệ thống hoặc server thật.
3. **Giữ controller thật:** mock collaborator ngoài slice bằng `@MockitoBean`, nhưng không mock đối tượng cần kiểm tra.
4. **Arrange:** stub input/output của catalog/service, cố định IDs và dữ liệu.
5. **Act:** dùng `mvc.perform(...)` cùng HTTP method, path, request `Content-Type`, `Accept` và body đúng.
6. **Assert:** kiểm tra **status → headers → response Content-Type → body**, chỉ những điều là hợp đồng của tình huống.
7. **Xác nhận phối hợp:** `verify` khi một lời gọi collaborator là một phần quan trọng của hành vi; test validation không được gọi dependency.
8. **Thêm negative cases:** missing entity, invalid payload, unsupported request media type, unacceptable response media type, không có body.
9. **Chạy độc lập và cả suite:** không phụ thuộc trạng thái Mockito từ test trước hoặc thứ tự test class.
10. **Kiểm tra tính ổn định:** không so khớp metadata động, không phụ thuộc servlet container trong mock MVC test.

Checklist:

- [ ] HTTP method/path và tình huống hợp lệ/lỗi đã được phân loại.
- [ ] 200, 201, 204, 400, 404 (và 406/415 nếu cần) được kiểm tra đúng tình huống, không phải gán tùy ý.
- [ ] `Location`, cache, version/correlation header hoặc ETag chỉ được assert khi thuộc contract.
- [ ] Phân biệt `Content-Type` request, `Accept` request và `Content-Type` response.
- [ ] Response JSON được so sánh theo cấu trúc/field, không theo thứ tự ký tự.
- [ ] 204 và các trường hợp body rỗng có assertion empty body.
- [ ] Lỗi validation không gọi collaborator khi request đã bị từ chối tại MVC boundary.
- [ ] Error JSON được kiểm tra chỉ khi có handler/controller định nghĩa rõ.
- [ ] Spring Security, filter, custom advice được thiết lập phù hợp với mục tiêu.
- [ ] Test không tự nhận đã chứng minh TLS, proxy, container error page hoặc toàn bộ persistence.
- [ ] Đúng import của Spring Boot/Spring Framework/JUnit dùng trong dự án thực tế.

**Ghi nhớ:** Một bài test Spring MVC đáng tin cậy không chỉ hỏi “request có đi qua controller không?”, mà hỏi **“client nhận chính xác mã trạng thái, header, kiểu dữ liệu và body nào?”**. `MockMvc` + `@WebMvcTest` giúp kiểm tra hợp đồng đó nhanh, độc lập với service/database thật, miễn là các assertion dựa trên behavior đã được thiết kế.

### Tài liệu tham khảo

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)
- [Spring Framework 6.2 — Defining Expectations](https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/hamcrest/expectations.html)
- [Spring Framework 6.2 — ContentResultMatchers API](https://docs.spring.io/spring-framework/docs/6.2.17/javadoc-api/org/springframework/test/web/servlet/result/ContentResultMatchers.html)
- [Spring Framework — HTTP Content Negotiation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/content-negotiation.html)