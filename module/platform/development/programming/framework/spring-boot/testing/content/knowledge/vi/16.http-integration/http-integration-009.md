# Phân biệt kiểm thử HTTP phía backend với kiểm thử đầu cuối qua trình duyệt

## 1. Vì sao hai loại test dễ bị đánh đồng?

Một API Spring Boot có thể trả đúng mã HTTP 200 và JSON `{"sku":"SKU-7","available":5}` khi kiểm tra bằng `MockMvc`, `TestRestTemplate`, `RestAssured`, `WebTestClient`, `curl` hoặc Postman. Nhưng điều đó **chưa chứng minh người dùng có thể mở trang, nhập SKU, nhấn nút và nhìn thấy kết quả**. JavaScript trên trình duyệt vẫn có thể gọi sai URL, xử lý lỗi sai, hiển thị nhầm trường JSON hoặc bị vấn đề cookie, CORS, DOM và trạng thái UI.

Ngược lại, một bài Playwright test nhìn thấy dòng `SKU-7: 5 in stock` cũng chưa tự chứng minh API có đầy đủ ràng buộc status/header/error cho mọi input. UI có thể đang dùng dữ liệu mock; hoặc browser test chỉ đi qua một happy path mà không kiểm tra contract riêng của backend.

Trong module **Spring Boot - testing**, thuộc nhóm **HTTP tích hợp**, cần phân biệt hai câu hỏi:

- **Kiểm thử HTTP phía backend:** Khi client gửi request HTTP tới Spring Boot (hoặc khi Spring MVC được mô phỏng bởi test infrastructure), server xử lý và trả **status, headers, content type, body, error** đúng hợp đồng không?
- **Kiểm thử đầu cuối qua trình duyệt (browser E2E):** Khi một người dùng thao tác trên **giao diện thực** trong browser, JavaScript, DOM, network, backend và việc hiển thị kết quả có phối hợp đúng thành một hành trình không?

Một chiến lược có chất lượng thường dùng **cả hai ở những vị trí khác nhau**: nhiều test nhanh, đặc hiệu cho API; ít test browser E2E hơn, tập trung vào hành trình quan trọng.

## 2. Bốn mức kiểm thử nên đặt cạnh nhau

Đừng gộp mọi “test có HTTP” thành cùng một loại:

| Mức | Công cụ minh họa | Có chạy Spring context? | Có socket/server thật? | Có trình duyệt thực? | Điều được chứng minh |
| --- | --- | --- | --- | --- | --- |
| Unit test controller/service thuần | JUnit, Mockito, gọi method trực tiếp | Không bắt buộc | Không | Không | Quy tắc Java và phối hợp collaborator |
| Spring MVC HTTP boundary | `@WebMvcTest` + `MockMvc` | Có, nhưng là web slice | Không | Không | Mapping, converter, validation, response của MVC |
| HTTP integration qua server thật | `@SpringBootTest(RANDOM_PORT)` + `TestRestTemplate`/`RestAssured` | Có, thông thường rộng hơn | **Có** | Không | HTTP request qua socket, server/dispatcher/wiring và API contract |
| Browser E2E | Playwright/Selenium/Cypress | Tùy hệ thống đích | Thường có | **Có** | Render UI, tương tác DOM, JavaScript, request mạng và phản hồi nhìn thấy được |

Đây là những **cấp độ/phạm vi**, không phải nhãn thắng-thua. `@WebMvcTest` kiểm tra hợp đồng HTTP phía MVC nhưng không thực hiện network socket. `@SpringBootTest(RANDOM_PORT)` có thể kiểm thử backend bằng HTTP thật mà không chạy Chrome. Playwright có thể kiểm tra browser với backend thật **hoặc** mock network; chỉ trường hợp backend thật mới chứng minh sự phối hợp browser ↔ backend thật trong phạm vi được kết nối.

### Hai sơ đồ đường đi

Kiểm thử HTTP qua server thật:

~~~text
JUnit / TestRestTemplate
        |
        | HTTP request, host:port
        v
Embedded server của Spring Boot
        |
        v
Spring MVC / Controller / Service / Bean liên quan
        |
        v
HTTP status + headers + body
        |
        v
Assertion của test Java
~~~

Kiểm thử đầu cuối qua trình duyệt:

~~~text
Playwright / người dùng
        |
        v
Chromium (DOM + JavaScript + cookies + browser network)
        |
        | mở trang, gõ SKU, nhấn Check
        v
JavaScript fetch('/api/stock/SKU-7')
        |
        | HTTP trên socket
        v
Spring Boot backend -> JSON response
        |
        v
JavaScript cập nhật DOM
        |
        v
Playwright đợi và assert nội dung hiển thị
~~~

Hai sơ đồ có giao nhau ở backend nhưng **điểm bắt đầu, đối tượng quan sát và nhóm lỗi phát hiện được khác nhau**.

## 3. Kiểm thử HTTP backend trả lời những gì?

Bằng cách gửi request HTTP/MockMvc và kiểm tra response, ta có thể bảo vệ:

1. **Routing:** `GET /api/stock/{sku}` đi đúng controller/method.
2. **Status:** thành công là `200 OK`, không tìm thấy là `404 Not Found`, payload không hợp lệ là `400 Bad Request`, v.v. theo hợp đồng.
3. **Headers:** `Content-Type`, `Cache-Control`, `Location`, `ETag`, header tùy chỉnh.
4. **Body schema và dữ liệu:** trường `sku` là String, `available` là Number, error code đúng.
5. **Request parsing và validation:** path/query/header/body đúng kiểu; xử lý malformed JSON hoặc ràng buộc Jakarta.
6. **Authorization tại server:** nếu dùng security thật, test có thể chứng minh 401/403/200 dựa trên credential hoặc token.
7. **Integration backend:** nếu giữ service/repository/DB thật, test HTTP có thể đi xuyên các tầng đó.

**Không được tự suy ra từ một HTTP backend test** rằng button hiển thị, input có thể focus, JS không lỗi, nút disable/enable hợp lý, CSS không che thành phần, browser lưu cookie đúng hoặc người dùng thực hiện trọn hành trình thành công.

Với `MockMvc`, request được đưa qua Spring MVC infrastructure trên các mock servlet objects; đây **không phải một TCP request thật**. Với `@SpringBootTest(webEnvironment = RANDOM_PORT)`, embedded server thực sự lắng nghe cổng và một client HTTP gọi qua socket. Hai cách đều là test backend, nhưng phạm vi khác.

### Chọn công cụ cho backend

- **`MockMvc` + `@WebMvcTest`** nếu mục tiêu chủ yếu là controller, conversion, status/body và kiểm tra nhanh.
- **`MockMvc` + `@SpringBootTest` + `@AutoConfigureMockMvc`** nếu cần context rộng hơn nhưng vẫn không mở cổng HTTP thật.
- **`TestRestTemplate`, RestAssured, Java HttpClient hoặc WebTestClient bind tới server** cùng `RANDOM_PORT` nếu muốn kiểm tra request HTTP thực qua network socket.
- **`WebTestClient`** là lựa chọn tự nhiên cho Spring WebFlux; có thể bind vào mock WebFlux context hoặc HTTP server thật tùy thiết lập.
- **Contract tests** với schema/OpenAPI hoặc consumer-driven contract có thể bổ sung để kiểm tra tương thích giữa các dịch vụ mà không cần duyệt UI.

**Một HTTP test có thể là integration test**, dù hoàn toàn không sử dụng browser. Từ “end-to-end” nên đi kèm **ranh giới cụ thể**: end-to-end của một service/backend chưa chắc là end-to-end của người dùng trên UI.

## 4. Browser E2E kiểm tra thêm những gì?

Browser E2E thường dùng Playwright, Selenium hoặc Cypress để chạy một browser engine thực, tải page, thực thi JavaScript, tương tác DOM và quan sát trạng thái người dùng thấy.

Các lỗi mà HTTP backend test dễ bỏ sót:

| Lỗi | API test vẫn có thể PASS? | Browser test phù hợp? |
| --- | --- | --- |
| Nút “Check” không gắn event listener | Có | Có: click và assert UI |
| Frontend gọi `/api/stocks` thay vì `/api/stock` | Có | Có: đi qua network thật |
| JS đọc `data.count` trong khi API trả `available` | Có | Có: assert nội dung hiển thị |
| UI không xử lý `404` và cứ hiện Loading | Có | Có: test nhánh missing |
| Trình duyệt không gửi cookie vì SameSite/CORS/credentials | Có khi API test inject header trực tiếp | Có, nếu chạy đúng origin và cơ chế auth |
| UI bị overlay che nút | Có | Có: click/actionability có thể thất bại |
| CSS responsive hoặc layout bị tràn | Có | Có khi có visual/viewport assertions phù hợp |
| Một API trả sai JSON contract | Thường test API sẽ phát hiện | Browser test cũng có thể thất bại, nhưng chẩn đoán kém đặc hiệu |
| Bug trong transaction/repository | Có thể được phát hiện nếu HTTP integration dùng DB thật | Chỉ phát hiện nếu browser thực sự đi qua DB thật và kịch bản chạm bug |

**Browser E2E không phải phép màu:** nếu test gọi `page.route(...)` để mock mọi API response, nó đang kiểm tra frontend với **mock backend**, không thể tuyên bố đã kiểm tra tích hợp backend thật. Nếu database cũng được fake, không thể kết luận query production đã được chứng minh.

Có hai hướng browser test khác nhau, cả hai đều hữu ích:

- **Frontend-focused browser test:** dùng mock network để kiểm tra DOM/JS, nhiều edge cases, không phụ thuộc backend.
- **Full-flow browser E2E:** dùng UI và HTTP backend thật (cùng database/test dependencies phù hợp) để kiểm tra hành trình xuyên hệ thống.

Nêu rõ hướng nào đang được chạy và không trộn chúng trong báo cáo.

## 5. Ma trận quyết định: nên đặt assertion ở đâu?

| Yêu cầu | Ưu tiên cấp độ nào? | Vì sao? |
| --- | --- | --- |
| GET trả 200 và body `available = 5` | HTTP backend | Đặc hiệu, rẻ, dễ phân tích lỗi |
| Error JSON có mã `NOT_FOUND` | HTTP backend | Hợp đồng mà mọi client dùng |
| Cấu hình MVC validation 400 | `MockMvc`/HTTP backend | Phát hiện lỗi handler/validation |
| Response có `Cache-Control: no-store` | HTTP backend | Hợp đồng HTTP rõ ràng |
| Người dùng nhập SKU rồi nhận kết quả trên trang | Browser E2E | Cần DOM, JS và user interaction |
| UI thông báo “Not found” khi server trả 404 | Browser E2E | Logic error handling phía frontend |
| Login, cookie, redirect, logout qua browser | Browser E2E + HTTP/security tests | Cần kết hợp browser state và server authorization |
| Repository lưu/đọc dữ liệu đúng | Data slice / HTTP integration với DB thật | Browser thường chậm và khó phân biệt lỗi DB |
| Form yêu cầu field và hiển thị lỗi | Browser E2E; unit/component frontend | JavaScript, HTML validation và UX |
| Ứng dụng hoạt động qua reverse proxy/TLS thực | Environment integration/E2E tại đúng hạ tầng | Random port local không có đủ proxy/TLS |
| Tương thích API cho mobile/third-party client | Contract + HTTP backend | Không cần browser UI |
| Hành trình mua hàng quan trọng | Vài browser E2E chọn lọc + backend/data tests | Phủ cả đường đi và lỗi từng tầng |

Nếu một quy tắc có thể được chứng minh rõ ràng bằng unit/API test, **không nên chỉ test nó ở browser**. Browser E2E chậm, nhiều moving parts và khó định vị lỗi; hãy dùng nó để bảo vệ giá trị tích hợp của hành trình.

## 6. Ví dụ nhất quán: một ứng dụng cho cả hai loại test

Ta xây dựng **Stock Lookup**:

- Backend Spring Boot 3.5 / Java 17 trả thông tin số lượng tồn kho.
- Trang `index.html` tải từ static resources của chính ứng dụng.
- Người dùng nhập SKU, nhấn Check; JS gọi API và cập nhật text.
- Backend có **một SKU cố định** để kết quả deterministic; không phụ thuộc database, OAuth server hay mạng ngoài.
- Cùng một backend được kiểm tra bằng `MockMvc`, `TestRestTemplate` và trình duyệt Chromium với Playwright Java.

Hợp đồng:

| Request/hành động | Kỳ vọng |
| --- | --- |
| HTTP `GET /api/stock/SKU-7` | 200 JSON `{"sku":"SKU-7","available":5}` và `Cache-Control: no-store` |
| HTTP `GET /api/stock/UNKNOWN` | 404 JSON `{"code":"NOT_FOUND"}` |
| Browser mở `/`, nhập `SKU-7`, bấm Check | Trang hiển thị `SKU-7: 5 in stock` |
| Browser nhập `UNKNOWN` và bấm Check | Trang hiển thị `Not found: UNKNOWN` |
| Browser bấm Check khi input trống/khoảng trắng | Hiển thị `Enter a SKU.`, không gọi API |

**Giới hạn cố ý:** ví dụ có backend thật và browser thật nhưng dữ liệu ở dạng in-memory cố định. Nó chứng minh **browser → HTML/JS → HTTP → controller → UI**, **không chứng minh database hoặc các hệ thống ngoài**. Nếu hệ thống thật dùng PostgreSQL, message queue hoặc OAuth, phải bổ sung test tích hợp các thành phần đó riêng.

Cây tệp:

~~~text
src/main/java/com/example/httptesting/
  StockApplication.java
  StockView.java
  ApiError.java
  StockController.java
src/main/resources/static/
  index.html
src/test/java/com/example/httptesting/
  StockMvcSliceTest.java
  StockHttpIntegrationTest.java
  StockBrowserE2ETest.java
build.gradle
~~~

Tất cả Java file dùng package `com.example.httptesting`. Các đoạn dưới đây đủ để xây dựng ví dụ bằng Spring Boot 3.5.x; cần một Gradle Wrapper được tạo cho project và JDK 17+.

## 7. Backend Java đầy đủ: app, DTO và controller

### 7.1. Entry point Spring Boot

**`src/main/java/com/example/httptesting/StockApplication.java`:**

~~~java
package com.example.httptesting;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StockApplication {
    public static void main(String[] args) {
        SpringApplication.run(StockApplication.class, args);
    }
}
~~~

### 7.2. Hai record JSON

**`src/main/java/com/example/httptesting/StockView.java`:**

~~~java
package com.example.httptesting;

public record StockView(String sku, int available) {
}
~~~

**`src/main/java/com/example/httptesting/ApiError.java`:**

~~~java
package com.example.httptesting;

public record ApiError(String code) {
}
~~~

Spring Boot 3.5 với `spring-boot-starter-web` và Jackson có thể serialize/deserialize các Java record này. `equals` của record so sánh theo từng component, hữu ích cho HTTP integration assertions.

### 7.3. REST controller có hai nhánh rõ ràng

**`src/main/java/com/example/httptesting/StockController.java`:**

~~~java
package com.example.httptesting;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/stock")
public class StockController {

    @GetMapping(
            value = "/{sku}",
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<?> getStock(@PathVariable String sku) {
        if ("SKU-7".equals(sku)) {
            return ResponseEntity.ok()
                    .cacheControl(CacheControl.noStore())
                    .body(new StockView("SKU-7", 5));
        }

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError("NOT_FOUND"));
    }
}
~~~

Controller này không gọi database và không có service/repository cần mock. Để học rõ ranh giới test, ta giữ mã tối giản: kết quả thành công có `Cache-Control: no-store`, kết quả thiếu SKU có status 404 và một JSON error body đã chủ động thiết kế.

**Không mặc định** mọi Spring Boot application tự trả `{"code":"NOT_FOUND"}`. Đây là hợp đồng do code ví dụ tạo ra. Với hệ thống có `@ControllerAdvice`, `ProblemDetail` hoặc error envelope khác, test phải assert đúng định dạng mà ứng dụng công bố.

### 7.4. Chạy thủ công để quan sát API

Nếu chạy ứng dụng qua Gradle task:

~~~bash
./gradlew bootRun
~~~

Khi không override `server.port`, Boot servlet server thường lắng nghe `http://localhost:8080`. Có thể kiểm tra:

~~~bash
curl -i http://localhost:8080/api/stock/SKU-7
curl -i http://localhost:8080/api/stock/UNKNOWN
~~~

Tùy server, client và cấu hình, các header như `Date`, `Transfer-Encoding`, `Connection` hoặc thứ tự header có thể khác. Những điểm **bắt buộc theo ví dụ** là status 200/404, JSON body tương ứng và Cache-Control `no-store` trên response thành công; không chép một stdout/curl transcript có header ngẫu nhiên như kết quả tuyệt đối.

Khi chạy test với `RANDOM_PORT`, **không dùng cố định 8080**: test nhận cổng ngẫu nhiên qua Spring Boot, như phần 10/11.

## 8. Frontend HTML + JavaScript: phần chỉ browser mới chạy đầy đủ

**Tệp `src/main/resources/static/index.html`:**

~~~html
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Stock Lookup</title>
</head>
<body>
  <h1>Stock Lookup</h1>

  <form id="stock-form">
    <label for="sku">SKU</label>
    <input id="sku" type="text" data-testid="sku-input">
    <button type="submit" data-testid="lookup-button">Check</button>
  </form>

  <p role="status" aria-live="polite"
     data-testid="stock-result"></p>

  <script>
    const form = document.getElementById("stock-form");
    const output = document.querySelector(
      '[data-testid="stock-result"]'
    );

    form.addEventListener("submit", async function (event) {
      event.preventDefault();

      const sku = document.getElementById("sku").value.trim();
      if (!sku) {
        output.textContent = "Enter a SKU.";
        return;
      }

      output.textContent = "Loading...";

      try {
        const response = await fetch(
          "/api/stock/" + encodeURIComponent(sku),
          { headers: { "Accept": "application/json" } }
        );

        if (response.status === 404) {
          output.textContent = "Not found: " + sku;
          return;
        }

        if (!response.ok) {
          throw new Error("HTTP " + response.status);
        }

        const stock = await response.json();
        output.textContent =
          stock.sku + ": " + stock.available + " in stock";
      } catch (error) {
        output.textContent = "Request failed.";
      }
    });
  </script>
</body>
</html>
~~~

Spring Boot phục vụ tệp `static/index.html` tại đường dẫn gốc `/` theo quy tắc static welcome page của Spring MVC auto-configuration. Trình duyệt tải trang, tạo DOM, thực thi script, rồi `fetch(...)` gửi request cùng origin tới API.

Các chi tiết có chủ đích:

- Dùng `data-testid` cho locator test bền với chỉnh sửa CSS.
- `event.preventDefault()` không để submit form tải lại trang.
- `trim()` xử lý khoảng trắng ở input.
- `encodeURIComponent(sku)` mã hóa SKU thành một path segment trong URL theo cú pháp JS; backend vẫn phải validate dữ liệu khi triển khai thực tế.
- `response.status === 404` tạo thông báo không tìm thấy, thay vì để JSON parse hoặc network exception bị hiểu nhầm.
- `response.ok` xử lý các mã thất bại còn lại.
- `output.textContent` tránh nhúng dữ liệu phản hồi thành HTML chưa escape; trong demo không dùng `innerHTML`.
- `role="status"` và `aria-live="polite"` thể hiện vùng cập nhật thông tin, nhưng riêng chúng **không thay thế kiểm thử khả năng tiếp cận đầy đủ**.

Một HTTP test chỉ gọi `GET /api/stock/SKU-7` **không chạy** đoạn JavaScript này. Ngay cả HTTP test gọi `GET /` và nhận đúng HTML vẫn không chứng minh event listener hoạt động, dữ liệu được fetch hay text DOM đổi đúng.

## 9. Test thứ nhất: @WebMvcTest + MockMvc, không có socket

**Tệp `src/test/java/com/example/httptesting/StockMvcSliceTest.java`:**

~~~java
package com.example.httptesting;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(StockController.class)
class StockMvcSliceTest {
    @Autowired
    MockMvc mvc;

    @Test
    void knownSku_returns200JsonAndCacheControl() throws Exception {
        mvc.perform(get("/api/stock/SKU-7")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        HttpHeaders.CACHE_CONTROL, "no-store"
                ))
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON
                ))
                .andExpect(jsonPath("$.sku").value("SKU-7"))
                .andExpect(jsonPath("$.available").value(5));
    }

    @Test
    void unknownSku_returns404ErrorJson() throws Exception {
        mvc.perform(get("/api/stock/UNKNOWN")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isNotFound())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON
                ))
                .andExpect(jsonPath("$.code").value("NOT_FOUND"));
    }
}
~~~

**Hai điều được chứng minh:** Spring MVC route đúng, controller thật trả status/header/body; Jackson message converter xuất JSON phù hợp. Nó không khởi động socket HTTP thật, không mở browser và không chạy JS từ `index.html`.

Nếu controller phụ thuộc `@Service` bị loại khỏi web slice, ta có thể dùng `@MockitoBean` đúng phiên bản Spring Framework để tạo mock bean bên trong context; **không mock chính controller đang kiểm tra**. Trong ví dụ này controller không có dependency nên không cần mock.

## 10. Test thứ hai: backend HTTP integration qua cổng thật

**Tệp `src/test/java/com/example/httptesting/StockHttpIntegrationTest.java`:**

~~~java
package com.example.httptesting;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class StockHttpIntegrationTest {

    @Autowired
    TestRestTemplate http;

    @Test
    void knownSku_overHttp_returns200TypedJsonAndCacheHeader() {
        ResponseEntity<StockView> response = http.getForEntity(
                "/api/stock/SKU-7",
                StockView.class
        );

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals(
                new StockView("SKU-7", 5),
                response.getBody()
        );

        MediaType contentType = response.getHeaders().getContentType();
        assertNotNull(contentType);
        assertTrue(contentType.isCompatibleWith(MediaType.APPLICATION_JSON));

        assertEquals(
                "no-store",
                response.getHeaders().getFirst(HttpHeaders.CACHE_CONTROL)
        );
    }

    @Test
    void unknownSku_overHttp_returns404TypedError() {
        ResponseEntity<ApiError> response = http.getForEntity(
                "/api/stock/UNKNOWN",
                ApiError.class
        );

        assertEquals(HttpStatus.NOT_FOUND, response.getStatusCode());
        assertEquals(
                new ApiError("NOT_FOUND"),
                response.getBody()
        );
    }

    @Test
    void homepageOverHttp_returnsHtmlButDoesNotExecuteScript() {
        ResponseEntity<String> response = http.getForEntity(
                "/", String.class
        );

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertNotNull(response.getBody());
        assertTrue(response.getBody().contains(
                "data-testid=\"sku-input\""
        ));

        MediaType contentType = response.getHeaders().getContentType();
        assertNotNull(contentType);
        assertTrue(contentType.isCompatibleWith(MediaType.TEXT_HTML));
    }
}
~~~

### Vì sao đây là HTTP integration test thật?

- `@SpringBootTest(webEnvironment = RANDOM_PORT)` khởi động embedded servlet HTTP server trên một cổng khả dụng.
- Trong Spring Boot **3.5**, một `TestRestTemplate` được cấu hình cho embedded server có thể `@Autowired` vào test. URL tương đối `"/api/stock/SKU-7"` được gửi đến server test, không phải một mock `MockHttpServletRequest`.
- `ResponseEntity<T>` cho phép assert cả **status, headers và body đã deserialize**.
- `TestRestTemplate` là client phù hợp để kiểm tra 4xx/5xx: nó không mặc định ném exception cho mỗi HTTP 404 như một số cấu hình `RestTemplate` khác.
- Kiểm tra `GET /` trả HTML chỉ chứng minh **server phục vụ tệp HTML**, không chứng minh browser đã thực thi script.

**Kết luận của test thứ ba rất quan trọng:** `response.getBody().contains("data-testid=...")` chứng minh HTML source có marker. Nhưng Java HTTP client không tạo DOM, không chạy event listener và không kích hoạt `fetch` sau khi nhấn nút. Đây chính là khoảng trống mà browser E2E giải quyết.

Nếu đang dùng Spring Boot **4.x**, module/package test REST client đã thay đổi; hãy đối chiếu reference theo phiên bản. Mã trong bài cố định ở **Spring Boot 3.5.16** để có imports nhất quán.

### LocalServerPort có bắt buộc với TestRestTemplate không?

Không trong cách dùng URL tương đối phía trên: test client được Boot cấu hình với cổng server. Nhưng một công cụ ngoài như Playwright cần biết URL đầy đủ; khi đó dùng `@LocalServerPort` và ghép host/port tại runtime.

### Giao dịch khi test HTTP thật

Nếu backend test ghi dữ liệu qua request tới server trong một thread khác, `@Transactional` gắn trên test method **không tự rollback** transaction mà server tạo. Trong ví dụ chỉ GET và dùng dữ liệu bất biến nên không cần reset. Trong ứng dụng có POST/PUT/DELETE, hãy tạo dữ liệu riêng cho test rồi cleanup đáng tin cậy, chạy transaction qua đúng boundary hoặc khôi phục DB giữa các ca.

## 11. Test thứ ba: Playwright Java với browser Chromium thật

Đây là tầng kiểm thử mà HTTP client không thay thế được: khởi động browser, mở trang, nhập liệu, click, để JavaScript gọi HTTP backend và đợi DOM cập nhật.

### 11.1. Test browser end-to-end

**Tệp `src/test/java/com/example/httptesting/StockBrowserE2ETest.java`:**

~~~java
package com.example.httptesting;

import com.microsoft.playwright.Browser;
import com.microsoft.playwright.BrowserType;
import com.microsoft.playwright.Page;
import com.microsoft.playwright.Playwright;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static com.microsoft.playwright.assertions.PlaywrightAssertions.assertThat;

@Tag("browser-e2e")
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class StockBrowserE2ETest {

    @LocalServerPort
    int port;

    private void withPage(java.util.function.Consumer<Page> scenario) {
        try (Playwright playwright = Playwright.create()) {
            Browser browser = playwright.chromium().launch(
                    new BrowserType.LaunchOptions().setHeadless(true)
            );

            try {
                Page page = browser.newPage();
                page.navigate("http://127.0.0.1:" + port + "/");
                scenario.accept(page);
            } finally {
                browser.close();
            }
        }
    }

    @Test
    void userCanLookUpKnownSkuAndSeeStock() {
        withPage(page -> {
            page.getByTestId("sku-input").fill("SKU-7");
            page.getByTestId("lookup-button").click();

            assertThat(page.getByTestId("stock-result"))
                    .hasText("SKU-7: 5 in stock");
        });
    }

    @Test
    void userSeesNotFoundForUnknownSku() {
        withPage(page -> {
            page.getByTestId("sku-input").fill("UNKNOWN");
            page.getByTestId("lookup-button").click();

            assertThat(page.getByTestId("stock-result"))
                    .hasText("Not found: UNKNOWN");
        });
    }

    @Test
    void blankSkuShowsValidationMessageBeforeFetch() {
        withPage(page -> {
            page.getByTestId("sku-input").fill("   ");
            page.getByTestId("lookup-button").click();

            assertThat(page.getByTestId("stock-result"))
                    .hasText("Enter a SKU.");
        });
    }
}
~~~

Trong mỗi test, `withPage` tạo một browser Chromium headless và trang mới, dùng URL động từ `@LocalServerPort`. `page.navigate(...)` tải **HTML thực** của Spring Boot; `fill` nhập liệu; `click` kích hoạt sự kiện form; JavaScript `fetch` gọi API; `assertThat(locator).hasText(...)` từ Playwright đợi tự động cho đến khi DOM có text mong đợi hoặc timeout.

**Không dùng `Thread.sleep(2000)`** để chờ network. Playwright có auto-wait cho actionability và assertion có retry, giúp test ít phụ thuộc tốc độ máy hơn. Nếu yêu cầu khác cần đợi cụ thể, chọn trạng thái DOM/network có ý nghĩa, không ngủ tùy ý.

### 11.2. Phân tích ba ca

| Ca | Browser làm gì? | Backend tham gia? | Điều browser test chứng minh |
| --- | --- | --- | --- |
| SKU hợp lệ | Gõ `SKU-7`, click Check | Có, GET 200 và JSON | Giao diện gọi API đúng, parse `available` và render kết quả |
| SKU không tồn tại | Gõ `UNKNOWN`, click | Có, GET 404 | JS xử lý error status và render thông báo |
| Input trống | Gõ toàn khoảng trắng, click | Không cần gọi API theo JS | Client-side validation hiển thị thông báo |

Ca thứ ba **không thể tự chứng minh backend không nhận request** chỉ bằng text UI; code JavaScript cho thấy early return, nhưng nếu muốn assertion bảo vệ việc không có network call, cần quan sát request bằng Playwright route/request events hoặc test JavaScript/component tương ứng. Đừng suy rộng hơn điều assertion hiện tại đo lường.

### 11.3. Vì sao browser E2E có thể phát hiện lỗi không thấy ở HTTP test?

Giả sử frontend nhầm:

~~~javascript
output.textContent =
  stock.sku + ": " + stock.count + " in stock";
~~~

Backend vẫn trả đúng `available: 5`, nên `StockHttpIntegrationTest` tiếp tục PASS. Nhưng browser sẽ hiển thị `SKU-7: undefined in stock`, làm `userCanLookUpKnownSkuAndSeeStock` FAIL. Đó là bằng chứng rõ ràng cho giá trị của một browser E2E test.

Nếu ai đó xóa event listener ở `index.html`, HTTP GET trang và API vẫn có thể PASS; browser test click sẽ không thấy output đúng. Nếu nút bị overlay che hoặc không nhận click, Playwright có thể phát hiện lỗi interaction mà `TestRestTemplate` không thể.

### 11.4. Browser test này có chứng minh database không?

**Không.** Cả backend và HTML là thật trong demo, nhưng backend đọc dữ liệu cố định ở controller. Để chứng minh một luồng production xuyên database, cần thay dữ liệu demo bằng repository/DB test thực sự, seed dữ liệu riêng rồi cleanup. Gọi test này là “browser-to-backend E2E cho Stock Lookup demo” chính xác hơn “toàn bộ hệ thống production E2E”.

## 12. Gradle đầy đủ: tách test nhanh và test browser

Một cách dễ duy trì là cho `./gradlew test` chạy backend slice + HTTP integration test, còn browser E2E chạy qua task riêng (ví dụ `browserE2eTest`). Tách này giúp CI thường xuyên chạy test nhanh và chạy browser test ở một stage có browser binary đầy đủ.

**`build.gradle` (Groovy DSL, ví dụ độc lập):**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'com.microsoft.playwright:playwright:1.64.0'
}

tasks.named('test', Test) {
    useJUnitPlatform {
        excludeTags 'browser-e2e'
    }
}

tasks.register('installChromium', JavaExec) {
    group = 'verification'
    description = 'Install Chromium expected by Playwright Java'
    classpath = sourceSets.test.runtimeClasspath
    mainClass = 'com.microsoft.playwright.CLI'
    args 'install', 'chromium'
}

tasks.register('browserE2eTest', Test) {
    group = 'verification'
    description = 'Run browser E2E scenarios using Chromium'
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    useJUnitPlatform {
        includeTags 'browser-e2e'
    }
    shouldRunAfter tasks.named('test')
}
~~~

Đây là **một tệp build hoàn chỉnh cho các phần phụ thuộc chính của ví dụ**. Dự án vẫn cần có Gradle Wrapper hoạt động, settings Gradle phù hợp và quyền tải dependencies từ Maven Central. Spring Boot `3.5.16` và Playwright Java `1.64.0` là các phiên bản cụ thể, giúp tương ứng với API/import trong bài.

**Cài browser binary một lần cho phiên bản Playwright đang dùng:**

~~~bash
./gradlew installChromium
~~~

**Chạy hai nhóm:**

~~~bash
./gradlew test
./gradlew browserE2eTest
~~~

**Chạy một lớp cụ thể khi gỡ lỗi:**

~~~bash
./gradlew test --tests "com.example.httptesting.StockHttpIntegrationTest"
./gradlew browserE2eTest --tests "com.example.httptesting.StockBrowserE2ETest"
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat installChromium
.\gradlew.bat test
.\gradlew.bat browserE2eTest
~~~

### Điều kiện chạy E2E không được bỏ qua

- Có **Java 17+**, Gradle tương thích với Spring Boot plugin 3.5, dependencies và browser binary Chromium do **cùng phiên bản Playwright** quản lý.
- Máy CI Linux có thể cần thêm thư viện hệ điều hành cho browser. Tham khảo tài liệu Playwright `install --with-deps chromium` hoặc image CI phù hợp; một task `installChromium` chỉ cài browser binary, **không bảo đảm mọi OS dependency có sẵn**.
- Không chạy browser trên production. Sử dụng ứng dụng test và dữ liệu giả; bảo đảm test không gửi email/thanh toán thật.
- Với UI E2E có tài khoản, dùng test account hạn chế quyền, quản lý secret qua CI, tránh log token hoặc ghi credential vào repo.
- Khi test chạy song song, không dùng chung account/data gây tranh chấp. Cổng `RANDOM_PORT` giúp giảm xung đột port nhưng **không** giải quyết va chạm database hoặc test tenant.

Các test trong ví dụ không gọi `System.out.println` nên **không có stdout cố định** do ứng dụng chủ động in. Gradle/JUnit và Playwright có thể phát log khác nhau. Vì đây là code Spring Boot + Playwright/JUnit, không thể chạy chỉ bằng `javac StockBrowserE2ETest.java` mà không cung cấp các dependency và browser binary.

## 13. Phân biệt kết quả một cách chính xác

Có nhiều tình huống dễ suy luận quá mức:

### 13.1. HTTP 200 không đồng nghĩa UI thành công

Nếu `StockHttpIntegrationTest` PASS nhưng Playwright FAIL, điều đó có thể chỉ ra lỗi frontend như selector, JS fetch, render, browser state hoặc network policy. **Không sửa backend API để làm test UI xanh** khi contract API vẫn đúng mà frontend đang đọc sai.

### 13.2. Browser E2E PASS không đồng nghĩa API đầy đủ

Một happy path browser chỉ chứng minh “hành trình này chạy được với tập dữ liệu này”. Nó không tự bao phủ mọi status code, phân trang, ETag, authentication, validation hoặc trạng thái database. Dùng API tests để bao phủ contract rộng hơn.

### 13.3. MockMvc không dùng socket

`MockMvc` vẫn chạy mapping, filter, converter và handler của MVC trong test infrastructure, nhưng không đi qua TCP/network stack, không chứng minh TLS hay cấu hình proxy ngoài ứng dụng. Muốn test qua socket, dùng `RANDOM_PORT` với HTTP client; muốn test browser, dùng browser automation.

### 13.4. Browser test có mock network chưa chắc là full E2E

Playwright có `page.route(...)` để chặn và trả response giả. Test như vậy rất tốt cho frontend isolation, nhưng **API server thật có thể không được gọi**. Ghi rõ tên/phạm vi test như `frontend-browser-with-mocks` thay vì tuyên bố đã xác nhận tích hợp toàn hệ thống.

### 13.5. E2E phụ thuộc môi trường thực đang chạy

Dự án thật có thể dùng frontend dev server riêng, reverse proxy, auth cookie, SameSite, CORS và HTTPS. Bài demo dùng **same-origin** vì HTML và API cùng được Boot phục vụ. Điều đó không tự chứng minh một deployment cross-origin thực tế đã cấu hình CORS/cookie đúng. Nếu deployment có domain khác, phải test ở môi trường tương đương.

### 13.6. @Transactional trên test client không rollback server request

Với `@SpringBootTest(RANDOM_PORT)`, các HTTP request tới server được xử lý ở thread/transaction khác với test method. Dù test method dùng `@Transactional`, transaction trên server không tự rollback theo transaction của test client. Nên seed/cleanup qua API phù hợp, DB test, fixture isolation hoặc khôi phục database có chủ đích.

## 14. Tổ chức bộ test để vừa nhanh vừa đáng tin

Một chiến lược hiệu quả là chia test theo **mục tiêu thất bại**:

| Nhóm | Mục tiêu chính | Chạy bao lâu/lúc nào? |
| --- | --- | --- |
| Unit test | Quy tắc dữ liệu/business thuần Java | Mỗi lần build/commit |
| MVC slice / JSON / validation | HTTP contract ngay tại web boundary | Mỗi lần build/commit |
| HTTP integration với server thật | Server startup, wiring, API contract qua socket | CI thường xuyên |
| Browser component/DOM với mock API | UI render, tương tác, xử lý các response giả | CI frontend theo mức cần |
| Browser full-flow E2E | Hành trình người dùng xuyên những dịch vụ thật đã chọn | Smoke test, PR quan trọng, trước phát hành |
| Staging/proxy/network E2E | TLS, gateway, cross-origin, cookie và tích hợp deploy | Môi trường staging được quản lý |

Không có tỷ lệ số lượng cố định phù hợp mọi nhóm. **Phủ rộng với test rẻ và đặc hiệu; chọn lọc với test E2E tốn tài nguyên**. Khi một lỗi chỉ xảy ra ở browser, hãy thêm test browser theo đúng user journey; khi lỗi ở JSON schema, ưu tiên một test HTTP chẩn đoán được ngay.

### Chọn data test độc lập

- Dữ liệu determinisitic: tạo SKU/test user có tên riêng, seed rõ ràng, tránh phụ thuộc data của test khác.
- Nếu test tạo dữ liệu, có teardown; cleanup nên chạy cả khi assertion thất bại.
- Không phụ thuộc thứ tự chạy lớp test; mỗi test là một kịch bản độc lập.
- Khi dùng database/container, xác định readiness bằng health check thay vì cố định `Thread.sleep`.
- Nếu dùng máy nhiều worker chạy song song, gắn test ID/namespace vào dữ liệu để tránh va chạm.

### Browser flakiness: cách giảm đúng nguyên nhân

- Dùng locator mang ý nghĩa (`getByRole`, `getByLabel`, `getByTestId`) thay vì CSS selector theo thứ tự DOM hoặc tọa độ pixel.
- Đợi trạng thái cần thiết bằng auto-retrying assertions; tránh sleep cố định.
- Tách network timeout khỏi assertion timeout; đặt ngưỡng có chủ đích theo CI.
- Khi fail, lưu screenshot/trace/video **nếu workflow CI cho phép**; tránh lưu dữ liệu nhạy cảm trong trace.
- Không tái sử dụng cùng browser page/session giữa các test thiếu kiểm soát.
- Tách test visual screenshot khỏi functional E2E nếu snapshot nhạy với font, OS và viewport.
- Dùng browser version được pin qua Playwright; re-install browser khi đổi phiên bản dependency.
- Giữ số test E2E ở mức hữu ích và phát hiện các lỗi tuyến người dùng quan trọng nhất.

## 15. Mở rộng sang đăng nhập, session, cookie, CSRF và bảo mật

Đối với hệ thống có Spring Security, hai lớp kiểm thử bổ sung cho nhau:

**Backend HTTP security tests** có thể chứng minh:

- Request không có token/cookie hợp lệ bị từ chối 401 hoặc 403 theo cấu hình.
- Role không đủ quyền bị từ chối dù API được gọi trực tiếp không qua UI.
- CSRF protection hoạt động ở HTTP boundary.
- Cookie attributes, redirect `Location`, cache headers đúng contract.
- Server không rò dữ liệu giữa tài khoản/tenant.

**Browser E2E security tests** có thể chứng minh:

- Người dùng đăng nhập bằng form hoặc provider test và được chuyển tới trang phù hợp.
- Session/cookie tồn tại qua navigation trong browser theo chính sách trình duyệt.
- Logout xóa trạng thái phiên trong giao diện và không thể dùng chức năng yêu cầu auth.
- Login redirect và protected routes hoạt động qua JS/router thật.
- CORS/preflight, `SameSite`, `Secure`, mixed content hoặc third-party cookie policy không chặn một luồng được hỗ trợ.

**Không dùng browser E2E làm thay thế duy nhất cho security tests.** UI có thể ẩn nút nhưng backend vẫn để lộ API trực tiếp; phải kiểm tra authorization ở server. Ngược lại, backend chấp nhận token không bảo đảm browser gửi cookie/token đúng theo ngữ cảnh trang.

Khi dùng `page.route` để fake authentication response hoặc bypass auth trong browser tests, ghi rõ đây là test UI isolation; không gọi nó là bài xác nhận login/security E2E đầy đủ.

## 16. Một tình huống gỡ lỗi theo dấu hiệu

Giả sử CI báo:

~~~text
StockMvcSliceTest              PASS
StockHttpIntegrationTest       PASS
StockBrowserE2ETest            FAIL
Expected: SKU-7: 5 in stock
Actual:   Request failed.
~~~

Đây là **ví dụ chẩn đoán minh họa**, không phải stdout thực tế đã chạy trong phiên làm bài.

Cách tìm nguyên nhân:

1. **Backend contract:** HTTP test đã chứng minh API chạy trên server test với dữ liệu đúng. Đừng mặc định API hoàn toàn không có bug, nhưng ưu tiên xem thêm tầng UI.
2. **URL/browser origin:** xem browser có tới đúng `http://127.0.0.1:<port>/` và JS gọi `/api/stock/SKU-7` không.
3. **Network response:** xem browser request nào thất bại, status, redirect, CORS hoặc exception JavaScript.
4. **JS parsing/render:** kiểm tra frontend đọc `stock.available` hay nhầm `stock.count`; xem console error.
5. **Selector và timing:** xác nhận locator `data-testid="stock-result"` tồn tại; auto-wait đang đợi điều kiện nào.
6. **Môi trường:** browser binary/OS libraries, port, proxy hay config CI có khác local không.
7. **Tăng độ hẹp của test:** nếu lỗi do rendering thuần, thêm frontend/component test; nếu do HTTP negotiation, thêm backend test cụ thể.

Nếu kết quả ngược lại — browser test PASS nhưng một backend test 404 error JSON FAIL — kiểm tra hợp đồng API và endpoint mà browser có thật sự truy cập nhánh lỗi hay không. Một test không tự bao phủ các tình huống nó chưa chạy.

## 17. Các nhầm lẫn và lỗi thường gặp

1. **Gọi mọi `@WebMvcTest` là end-to-end test.** Nó không mở browser hay socket. **Sửa:** ghi rõ web slice/MockMvc.
2. **Gọi mọi `@SpringBootTest(RANDOM_PORT)` là browser E2E.** Nó mở server thật nhưng test Java HTTP client vẫn không có DOM/JS. **Sửa:** phân biệt backend HTTP integration.
3. **Chỉ test status 200 rồi nói API đúng.** Không chứng minh body/header/error. **Sửa:** assert contract thiết yếu.
4. **Chỉ test browser happy path rồi tuyên bố backend đầy đủ.** Không bao phủ mọi nhánh API. **Sửa:** bổ sung HTTP contract tests.
5. **Browser E2E mock hết network nhưng báo full-stack PASS.** Backend không được kiểm tra. **Sửa:** ghi rõ mocked-network E2E/frontend test.
6. **Gọi controller trực tiếp nhưng tuyên bố đã test HTTP serialization.** Không chạy message converter/request mapping. **Sửa:** dùng MockMvc hoặc real HTTP client.
7. **Lấy URL `localhost:8080` cố định trong RANDOM_PORT test.** CI có cổng khác. **Sửa:** `@LocalServerPort` hoặc TestRestTemplate relative URL.
8. **Dùng `Thread.sleep` trong browser test.** Thời gian không ổn định. **Sửa:** Playwright auto-wait, locator assertions.
9. **Locator phụ thuộc DOM/CSS dễ đổi.** Refactor style làm test hỏng. **Sửa:** ưu tiên role/label/test ID ổn định.
10. **Không cài browser binary cho đúng Playwright version.** Test không khởi động browser. **Sửa:** chạy install task tương ứng sau khi thay dependency.
11. **Chạy test đối với production.** Có thể tạo dữ liệu, gửi email, thanh toán thật. **Sửa:** môi trường/test accounts riêng, giới hạn side effect.
12. **Chạy nhiều browser test dùng chung account/dữ liệu mutable.** Test flaky do va chạm. **Sửa:** isolation và cleanup.
13. **Giả định test client @Transactional rollback server thật.** Transaction ở thread khác. **Sửa:** reset dữ liệu qua đúng boundary.
14. **Không test CSRF/cookie ở browser khi triển khai cross-origin.** HTTP client có thể không tái hiện browser restrictions. **Sửa:** browser E2E ở origin/môi trường phù hợp.
15. **Chỉ nhìn giao diện thấy lỗi rồi sửa backend ngay.** Có thể chỉ là JS parse/render sai. **Sửa:** phân tầng chẩn đoán từ API contract đến browser network/DOM.
16. **Đòi visual layout từ HTTP test.** JSON/HTML source không chứng minh CSS render. **Sửa:** dùng browser functional/visual tests.
17. **Giả định dùng Playwright nghĩa là kiểm tra accessibility toàn diện.** DOM interaction không tự thay audit A11y. **Sửa:** thêm a11y assertions/audit riêng khi yêu cầu.
18. **Test browser pass vì mock response trùng kỳ vọng nhưng route backend đã đổi.** UI bị cô lập khỏi API thật. **Sửa:** ít nhất một full-flow smoke test không fake API.
19. **Đặt mọi test browser vào mỗi unit test task.** CI nặng và khó quản lý browsers. **Sửa:** tách tags/tasks/stages.
20. **Quên điều kiện triển khai:** reverse proxy, TLS hoặc CDN khác localhost. **Sửa:** test staging riêng cho hạ tầng deploy cần bảo vệ.

## 18. Checklist lựa chọn đúng mức và viết assertion

Trước khi viết một test, hãy trả lời:

- [ ] Mục tiêu là **Java logic**, **HTTP response**, **wiring/network backend** hay **user journey qua browser**?
- [ ] Có cần Spring context không? Nếu không, dùng JUnit thuần.
- [ ] Có cần HTTP socket thật không? Nếu không, cân nhắc `MockMvc`/slice.
- [ ] Có cần DOM/JavaScript/cookie/viewport không? Nếu có, dùng browser test.
- [ ] Test có mock API/database không? Nếu có, tên và kết luận phản ánh phần bị fake.
- [ ] Backend HTTP test có assert **status, headers, content type, body**, lỗi nghiệp vụ và validation cần thiết?
- [ ] Browser E2E có tương tác qua locator ổn định và assert nội dung người dùng thấy?
- [ ] Browser test có chờ bằng assertion retry, tránh `Thread.sleep`?
- [ ] Môi trường test có database, test account, cleanup và secret management phù hợp?
- [ ] `RANDOM_PORT` được dùng bằng port động; không hard-code 8080 trong test?
- [ ] Security được test ở cả server boundary và browser khi hành trình liên quan?
- [ ] Có bước smoke E2E kết nối frontend và backend thật cho hành trình quan trọng?
- [ ] Khi fail, có đủ log HTTP/browser trace để định vị lớp gây lỗi?
- [ ] Các test chạy độc lập, không phụ thuộc thứ tự hoặc trạng thái từ test trước?
- [ ] CI đã cài browser binary/OS dependencies và pin Playwright version?

### Kết luận

**Kiểm thử HTTP phía backend** trả lời: *“Khi gọi API, Spring Boot phản hồi đúng hợp đồng và tích hợp backend trong phạm vi đã nạp không?”* **Browser E2E** trả lời: *“Người dùng có thực hiện được hành trình trên giao diện với browser, JavaScript và những backend đã kết nối không?”*

Đừng thay thế một nhóm bằng nhóm còn lại. Viết **nhiều unit/API tests cho các quy tắc chi tiết**, bổ sung **HTTP integration tests qua server thật** khi cần network/wiring, và chọn **một tập browser E2E nhỏ nhưng có ý nghĩa** cho những trải nghiệm mà client thực sự phụ thuộc.

### Tài liệu tham khảo

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — TestRestTemplate API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/web/client/TestRestTemplate.html)
- [Spring Boot — Embedded Web Servers và @LocalServerPort](https://docs.spring.io/spring-boot/how-to/webserver.html)
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)
- [Playwright Java — Installation](https://playwright.dev/java/docs/intro)
- [Playwright Java — Assertions và auto-retrying](https://playwright.dev/java/docs/test-assertions)
- [Playwright Java — Browser installation](https://playwright.dev/java/docs/browsers)
- [Playwright Java — Locators](https://playwright.dev/java/docs/locators)