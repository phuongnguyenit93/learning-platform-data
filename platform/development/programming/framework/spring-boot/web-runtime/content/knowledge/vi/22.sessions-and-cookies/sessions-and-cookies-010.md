# Phân biệt trạng thái phiên với dữ liệu gắn riêng cho từng yêu cầu trong Spring Boot

## 1. Mục tiêu

HTTP là giao thức **không tự lưu trạng thái ứng dụng giữa các request**. Tuy vậy, một ứng dụng web thường cần nhớ người dùng đã đăng nhập, ngôn ngữ giao diện hay một bước trong quy trình đang thực hiện. Đồng thời, mỗi request lại có dữ liệu tạm thời riêng như request ID, kết quả validation, tham số tìm kiếm, thông tin tracing hay dữ liệu trung gian của handler.

Hai loại dữ liệu này có **vòng đời, phạm vi chia sẻ và rủi ro khác nhau**:

- **Trạng thái phiên (session state):** liên quan đến một phiên HTTP, có thể được dùng qua *nhiều request* mang cùng session identifier, cho tới khi phiên hết hạn/bị vô hiệu hóa hoặc bị hệ thống thay đổi.
- **Dữ liệu gắn với một request (request-local state):** chỉ thuộc một *HTTP request* và thường không tồn tại sang request tiếp theo. Nó có thể được truyền giữa filter, interceptor, controller và các thành phần tham gia xử lý cùng request.

Bài học tập trung vào **Spring Boot 3.x, Spring MVC/Servlet và Java 17+**, gồm `HttpSession`, `HttpServletRequest`, request/session scoped beans, cookie phiên và cách kiểm thử. Phần cuối có đối chiếu với Spring WebFlux.

Sau bài, bạn sẽ biết đặt **đúng loại dữ liệu vào đúng scope**, tránh lưu dữ liệu tạm vào session, tránh chia sẻ state giữa người dùng và tránh tin rằng HTTP keep-alive hoặc một Java thread có thể đại diện cho phiên đăng nhập.

## 2. Một ví dụ trực quan: hai request, một session

Giả sử người dùng chọn ngôn ngữ `vi` ở request thứ nhất, sau đó mở trang khác bằng cùng trình duyệt:

```text
Browser A                                     Spring Boot
    |                                             |
    | POST /lab/language value=vi                |
    |-------------------------------------------->|
    |                                       Tạo HttpSession S1
    |                                       Session attribute:
    |                                         uiLanguage = "vi"
    |                                       Request attribute:
    |                                         requestTraceId = "R1"
    |<--------------------------------------------|
    | Set-Cookie: JSESSIONID=<id-được-server-tạo> |
    |                                             |
    | GET /lab/state                             |
    | Cookie: JSESSIONID=<cùng-id>               |
    |-------------------------------------------->|
    |                                       Tìm HttpSession S1
    |                                       uiLanguage = "vi"
    |                                       requestTraceId = "R2"
    |<--------------------------------------------|
    |                                             |
    | GET /lab/state (không gửi cookie)           |
    |-------------------------------------------->|
    |                                       Không tìm được S1
    |                                       requestTraceId = "R3"
    |<--------------------------------------------|
```

`R1`, `R2`, `R3` chỉ là nhãn tượng trưng. Điểm cốt lõi: **giá trị session được giữ khi client gửi lại session ID hợp lệ**, nhưng request ID mới được tạo cho từng request. HTTP request thứ hai không phải là “cùng request” với request thứ nhất.

**Cookie `JSESSIONID` thường chỉ chứa mã nhận diện phiên**, không chứa nguyên đối tượng Java lưu trên server. Trong cấu hình Servlet container truyền thống, dữ liệu session nằm ở server/container; nếu dùng Spring Session, dữ liệu có thể được lưu qua kho chung như Redis hoặc JDBC. Không nhầm cookie phiên với “nơi lưu mọi giá trị trong session”.

## 3. Phạm vi và vòng đời: bảng so sánh

| Tiêu chí | Request state | Session state |
| --- | --- | --- |
| Đối tượng Servlet trực tiếp | `HttpServletRequest` và request attributes | `HttpSession` và session attributes |
| Spring bean scope | `@RequestScope` | `@SessionScope` |
| Thời gian tồn tại | Trong quá trình xử lý một request; có nuance khi async dispatch | Qua các request dùng cùng session, tới timeout/invalidate/rotation |
| Người dùng nào nhìn thấy? | Thành phần xử lý **request hiện tại** | Các request truy cập **cùng session** |
| Ví dụ phù hợp | Request ID, kết quả parse, validation, dữ liệu tracing, thông tin trung gian | Ngôn ngữ giao diện tạm, một ít trạng thái quy trình, xác thực qua cơ chế framework |
| Giá trị có tự truyền sang request kế tiếp? | **Không** | **Có**, nếu session còn hợp lệ và được xác định |
| Rủi ro thường gặp | Nhầm state với thread, để lộ vào singleton | Dữ liệu cũ, hai tab ghi đè, session fixation/hijacking, memory, phân tán nhiều server |
| Có cần cookie? | Không | Thường dùng cookie session ID, nhưng container có thể hỗ trợ cơ chế tracking khác |
| Là kho dữ liệu vĩnh viễn? | Không | **Không** |

**Cần phân biệt thêm:**

- **Java local variable:** thuộc lời gọi method, thích hợp nhất cho dữ liệu dùng trong một bước xử lý; nhiều trường hợp không cần request attribute.
- **`@RequestParam`, `@PathVariable`, `@RequestBody`:** dữ liệu *đầu vào* của request hiện tại, không tự trở thành session state.
- **`Model` của Spring MVC:** chủ yếu dùng để đưa dữ liệu tới view khi render request; không mặc nhiên là session.
- **`RedirectAttributes.addFlashAttribute`:** dữ liệu tạm chuyển qua một redirect, thường được giữ tạm trong session rồi dùng ở request đích; **khác cả request attribute thông thường lẫn session state dài hơn**.
- **`@SessionAttributes` trên controller:** một cơ chế của Spring MVC để lưu **một số model attributes** trong session cho luồng xử lý controller, thường là form nhiều bước; không đồng nghĩa với `@SessionScope` bean và không nên dùng như kho session dùng chung của mọi component.
- **Singleton bean:** scope mặc định của Spring, dùng chung giữa nhiều request và người dùng. Không đặt biến instance mutable của controller/singleton để lưu dữ liệu người dùng.

## 4. `HttpServletRequest`: dữ liệu chỉ gắn với request hiện tại

Servlet API cho phép lưu thuộc tính bằng:

```java
request.setAttribute("traceId", "some-request-id");
Object trace = request.getAttribute("traceId");
request.removeAttribute("traceId");
```

Đoạn trên minh họa API; cần biến `request` kiểu `jakarta.servlet.http.HttpServletRequest`. Một filter có thể đặt `traceId` để controller cùng request đọc được. Khi browser phát ra HTTP request mới, controller nhận một request mới; thuộc tính cũ **không được tự sao chép sang request mới**.

Các trường hợp nên dùng request attribute:

- Filter tính correlation/request ID; controller và interceptor cùng lấy trong vòng đời request.
- Middleware ghi lại thời điểm bắt đầu hoặc số liệu tạm để tính duration.
- Kết quả validation/parse được chia sẻ với các thành phần cùng request.
- Một flag nội bộ cho quá trình render hiện tại, không mang ý nghĩa qua nhiều lần truy cập.

**Không lạm dụng:** nếu dữ liệu chỉ cần ở một method, dùng local variable hoặc tham số method. Request attribute có tên dạng chuỗi, dễ va chạm key; nên đặt key có namespace, ví dụ `"demo.requestTraceId"`.

### Request scope không bằng thread scope

Một servlet request thường được thực thi trên worker thread, nhưng **thread không phải request**:

- Một platform thread trong pool có thể phục vụ request A xong rồi phục vụ request B.
- Virtual threads trong Spring Boot có thể tạo thread khác nhau cho các tác vụ/request, nhưng chúng cũng không phải session.
- Async servlet dispatch hoặc cơ chế xử lý bất đồng bộ có thể làm luồng thực thi chuyển thread trong vòng đời logic của request.

Vì vậy, **không dùng `ThreadLocal` như một kho thay thế `HttpSession` hoặc `HttpServletRequest`**. Nếu tự đặt ThreadLocal, phải xử lý scope, cleanup `finally`, context propagation và async boundary thật cẩn thận. Với tracing, ưu tiên thư viện observability/context propagation phù hợp.

## 5. `HttpSession`: trạng thái có thể truy cập qua nhiều request

Một servlet controller có thể lấy session:

```java
// Tạo session mới nếu chưa có.
HttpSession session = request.getSession(true);

// Chỉ lấy session hiện có; trả null nếu không có.
HttpSession existing = request.getSession(false);

session.setAttribute("uiLanguage", "vi");
String language = (String) session.getAttribute("uiLanguage");

// Xóa riêng một giá trị:
session.removeAttribute("uiLanguage");

// Vô hiệu hóa toàn bộ phiên (ví dụ khi kết thúc phiên):
session.invalidate();
```

Đây là đoạn minh họa trong servlet web context, chưa phải ứng dụng độc lập. Tên lớp Java nằm trong package `jakarta.servlet.http` với Spring Boot 3.x.

**Sự khác biệt quan trọng giữa `getSession(true)` và `getSession(false)`:**

- `getSession(true)`: nếu không tồn tại session hợp lệ, yêu cầu tạo session; server có thể gửi session cookie để browser giữ ID.
- `getSession(false)`: chỉ lấy session đang tồn tại; nếu không có thì trả `null`. Dùng cách này cho endpoint **chỉ quan sát trạng thái** để tránh vô tình tạo session cho mọi request ẩn danh.

Trong Spring MVC, khai báo trực tiếp `HttpSession` làm tham số controller cũng tiện, nhưng thường dẫn đến việc container giải quyết một session cho tham số đó. Khi muốn kiểm tra mà **không tạo** session, lấy `HttpServletRequest` rồi gọi `getSession(false)` tường minh.

### Session timeout và cookie expiry không phải một thứ

Session có thể bị invalidate/logout, hết hạn do không hoạt động, bị dọn khi server thay đổi hoặc bị mất khi lưu trữ không bền vững. Cookie browser có thể còn nhưng server **không còn session tương ứng**.

Ngược lại, browser đóng cửa sổ hoặc xóa cookie không đảm bảo object session trên server bị dọn ngay; việc dọn phụ thuộc timeout/manager.

Ví dụ trong `application.properties`:

```properties
server.servlet.session.timeout=20m
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
```

Đây là cấu hình phổ biến cho ứng dụng Servlet dùng cookie; **chưa đủ để bảo mật production** nếu không có HTTPS, xác thực, CSRF, quản lý session và các header khác phù hợp. Khi chạy thực tế qua **HTTPS**, thường cần:

```properties
server.servlet.session.cookie.secure=true
```

Không áp dụng `secure=true` vào demo chạy thuần HTTP local rồi thắc mắc browser không gửi lại cookie; Secure cookie phải đi với HTTPS (có ngoại lệ browser cho localhost nhưng không được dựa vào ngoại lệ đó). Đảm bảo cấu hình proxy/forwarded headers, TLS termination và tên miền được thiết kế đúng; đừng hạ Secure trên production để “sửa đăng nhập”.

Cookie `HttpOnly` hạn chế JavaScript đọc trực tiếp session cookie nhưng **không tự ngăn XSS gây hành động dưới phiên đang đăng nhập**. `SameSite=Lax` giúp giảm một số kịch bản CSRF, nhưng **không thay thế CSRF token** ở ứng dụng cookie-authentication có thao tác thay đổi trạng thái.

## 6. Ví dụ chạy được: chứng minh hai scope bằng hai request

Ứng dụng ví dụ không dùng database. Một endpoint POST lưu **ngôn ngữ giao diện** vào `HttpSession`, filter đặt **requestTraceId** mới trên `HttpServletRequest`, endpoint GET trả hai giá trị này để bạn quan sát khác biệt.

### 6.1. Khởi tạo dự án

Dùng **Java 17+**, **Spring Boot 3.x** (ví dụ một bản 3.x đang được bảo trì), starter **Spring Web** (`spring-boot-starter-web`). Để chạy test dùng thêm **Spring Boot Starter Test** (`spring-boot-starter-test`).

Cấu trúc file:

```text
src/
├─ main/
│  ├─ java/com/example/demo/
│  │  ├─ SessionRequestApplication.java
│  │  ├─ RequestTraceFilter.java
│  │  └─ StateLabController.java
│  └─ resources/
│     └─ application.properties
└─ test/
   └─ java/com/example/demo/
      └─ StateLabControllerTest.java
```

Đây là **demo local chỉ tập trung minh họa vòng đời session/request**, không bật Spring Security. Các POST trong demo **chưa được bảo vệ bằng CSRF token** và **không dùng trực tiếp cho dữ liệu tài khoản hay ứng dụng public**. Phần 10 nêu các yêu cầu phải thêm trước khi triển khai thật.

### 6.2. Lớp khởi chạy

**`src/main/java/com/example/demo/SessionRequestApplication.java`**

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionRequestApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionRequestApplication.class, args);
    }
}
```

### 6.3. Filter lưu dấu vết trong request, không phải session

**`src/main/java/com/example/demo/RequestTraceFilter.java`**

```java
package com.example.demo;

import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class RequestTraceFilter extends OncePerRequestFilter {

    public static final String ATTRIBUTE_KEY = "demo.requestTraceId";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        request.setAttribute(
            ATTRIBUTE_KEY,
            UUID.randomUUID().toString()
        );
        filterChain.doFilter(request, response);
    }
}
```

`OncePerRequestFilter` hỗ trợ thực hiện filter theo quy tắc một lần trên một request dispatch phù hợp với cấu hình filter; với async/error dispatch có các quy tắc dispatch riêng. Trong demo không dùng async. Mỗi HTTP request mới đi qua filter sẽ có `UUID` mới trong attribute `demo.requestTraceId`. Filter **không ghi** vào `HttpSession`.

Trong production, request ID có thể do edge proxy/tracing framework tạo; không tự coi ID do client truyền vào là định danh đáng tin để phân quyền hay quyết định dữ liệu nhạy cảm.

### 6.4. Controller: session value sống qua các request

**`src/main/java/com/example/demo/StateLabController.java`**

```java
package com.example.demo;

import java.util.Set;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/lab")
public class StateLabController {

    private static final String LANGUAGE_KEY = "demo.uiLanguage";
    private static final Set<String> ALLOWED = Set.of("vi", "en");

    @PostMapping("/language")
    public StateView setLanguage(
            @RequestParam String value,
            HttpServletRequest request) {

        if (!ALLOWED.contains(value)) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Only vi or en is allowed"
            );
        }

        HttpSession session = request.getSession(true);
        session.setAttribute(LANGUAGE_KEY, value);
        return snapshot(request, session);
    }

    @GetMapping("/state")
    public StateView state(HttpServletRequest request) {
        // Không tạo session chỉ để đọc trạng thái.
        HttpSession session = request.getSession(false);
        return snapshot(request, session);
    }

    @PostMapping("/end")
    public ResponseEntity<Void> end(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session != null) {
            session.invalidate();
        }
        return ResponseEntity.noContent().build();
    }

    private StateView snapshot(
            HttpServletRequest request,
            HttpSession session) {

        String requestTraceId = (String) request.getAttribute(
            RequestTraceFilter.ATTRIBUTE_KEY
        );

        String language = session == null
            ? null
            : (String) session.getAttribute(LANGUAGE_KEY);

        // Không đưa session.getId() vào API response.
        return new StateView(
            requestTraceId,
            language,
            session != null
        );
    }

    public record StateView(
        String requestTraceId,
        String language,
        boolean sessionPresent
    ) {}
}
```

Điểm cần hiểu:

- `POST /lab/language` kiểm tra `value` chỉ là `vi` hoặc `en` rồi tạo/lấy session và lưu `demo.uiLanguage`. Đây là **state của phiên**, không phải property của bean singleton `StateLabController`.
- `GET /lab/state` dùng `request.getSession(false)` để không tạo phiên chỉ nhằm đọc. Nếu không có cookie/session hợp lệ, response có `sessionPresent=false`, `language=null`.
- `requestTraceId` đến từ **request attribute** được filter đặt trên request đang xử lý. Request tiếp theo nhận một UUID mới, dù vẫn mang cookie của cùng session.
- `POST /lab/end` gọi `session.invalidate()`; request dùng ID cũ sau đó không còn lấy được session cũ. Đây là demo kết thúc session, **không thay thế đầy đủ logout của Spring Security** khi ứng dụng có xác thực thật.
- Không trả `session.getId()` trong JSON hay log dạng rõ. Session ID là một credential nhạy cảm: ai có ID hợp lệ có thể có cơ hội chiếm phiên nếu hệ thống không có biện pháp khác.

### 6.5. Cấu hình cho demo

**`src/main/resources/application.properties`**

```properties
server.port=8080
server.servlet.session.timeout=20m
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
```

**Không đặt `server.servlet.session.cookie.secure=true` khi chạy ví dụ bằng HTTP localhost**. Trong production phải chạy HTTPS và bật Secure cookie đúng ngữ cảnh triển khai.

### 6.6. Thử bằng curl: duy trì cookie qua request

Khởi chạy từ thư mục dự án có Maven Wrapper:

```bash
java -version
./mvnw spring-boot:run
```

Windows: `mvnw.cmd spring-boot:run`. Mở terminal khác. Các ví dụ sau dùng Bash/Unix; trên Windows có thể dùng `curl.exe` và sửa đường dẫn file cookie phù hợp.

**Bước 1 — không có cookie:**

```bash
curl -s http://localhost:8080/lab/state
```

Kết quả JSON dạng:

```json
{"requestTraceId":"RANDOM-UUID-1","language":null,"sessionPresent":false}
```

`RANDOM-UUID-1` là placeholder diễn giải cho UUID thật, không phải literal stdout cố định. Nếu muốn xác nhận status, dùng `curl -i`.

**Bước 2 — gửi POST và lưu cookie vào cookie jar:**

```bash
curl -i -c session-cookies.txt \
  -X POST "http://localhost:8080/lab/language" \
  --data-urlencode "value=vi"
```

Khi session được tạo, response thường có header `Set-Cookie: JSESSIONID=...` và JSON:

```json
{"requestTraceId":"RANDOM-UUID-2","language":"vi","sessionPresent":true}
```

Đây là response **minh họa**. Nội dung ID, thứ tự header, các thuộc tính cookie và JSON formatting phụ thuộc runtime. **Đừng đăng session cookie thực lên issue tracker, chat hay log.**

**Bước 3 — gửi lại cookie jar trong các request khác:**

```bash
curl -s -b session-cookies.txt http://localhost:8080/lab/state
curl -s -b session-cookies.txt http://localhost:8080/lab/state
```

Hai response phải cùng `"language":"vi"` và `"sessionPresent":true`, còn `requestTraceId` thường là **hai UUID khác nhau** vì filter chạy cho mỗi request mới.

**Bước 4 — một client khác không gửi cookie:**

```bash
curl -s http://localhost:8080/lab/state
```

Kỳ vọng `"sessionPresent":false` và `"language":null`. Điều này mô phỏng client khác **chưa mang cùng session identifier**, không chứng minh hệ thống đã xác thực hai người dùng khác nhau.

**Bước 5 — invalidate session:**

```bash
curl -i -b session-cookies.txt \
  -X POST http://localhost:8080/lab/end

curl -s -b session-cookies.txt http://localhost:8080/lab/state
```

Kỳ vọng request cuối không truy cập được `demo.uiLanguage` của session cũ. Cookie jar có thể vẫn chứa ID cũ, nhưng server xem session ấy không còn hợp lệ.

**Ghi nhớ:** nếu mở lại terminal/curl mà không dùng `-b session-cookies.txt` thì không có căn cứ để server biết client muốn tiếp tục session nào; cùng địa chỉ IP **không** đồng nghĩa cùng session.

## 7. Kiểm thử bằng MockMvc để tránh kết luận chỉ từ JSON thủ công

Với dependency `spring-boot-starter-test` trong test scope, viết test chứng minh request-local ID thay đổi và session value giữ lại:

**`src/test/java/com/example/demo/StateLabControllerTest.java`**

```java
package com.example.demo;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class StateLabControllerTest {

    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;

    @Test
    void sessionValueSurvivesButRequestIdChanges() throws Exception {
        MvcResult first = mvc.perform(
                post("/lab/language").param("value", "vi"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.language").value("vi"))
            .andExpect(jsonPath("$.sessionPresent").value(true))
            .andReturn();

        MockHttpSession session = (MockHttpSession)
            first.getRequest().getSession(false);
        assertNotNull(session);

        String idA = mapper.readTree(
            first.getResponse().getContentAsString()
        ).get("requestTraceId").asText();

        MvcResult second = mvc.perform(
                get("/lab/state").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.language").value("vi"))
            .andExpect(jsonPath("$.sessionPresent").value(true))
            .andReturn();

        String idB = mapper.readTree(
            second.getResponse().getContentAsString()
        ).get("requestTraceId").asText();

        assertNotEquals(idA, idB);
    }

    @Test
    void readOnlyRequestDoesNotCreateSession() throws Exception {
        MvcResult result = mvc.perform(get("/lab/state"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.sessionPresent").value(false))
            .andReturn();

        assertNull(result.getRequest().getSession(false));
    }

    @Test
    void stateIsNotSharedWithoutSameSession() throws Exception {
        MvcResult first = mvc.perform(
                post("/lab/language").param("value", "en"))
            .andExpect(status().isOk())
            .andReturn();

        MockHttpSession session = (MockHttpSession)
            first.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/lab/state").session(session))
            .andExpect(jsonPath("$.language").value("en"));

        mvc.perform(get("/lab/state"))
            .andExpect(jsonPath("$.sessionPresent").value(false));
    }

    @Test
    void invalidLanguageIsRejectedBeforeSessionCreation()
            throws Exception {
        MvcResult result = mvc.perform(
                post("/lab/language").param("value", "unknown"))
            .andExpect(status().isBadRequest())
            .andReturn();

        assertNull(result.getRequest().getSession(false));
    }
}
```

Chạy:

```bash
./mvnw test
```

Với đúng Spring Boot 3.x, Spring Web/Starter Test và các file ở trên, **bốn test được kỳ vọng pass**. Đây là **kết quả thiết kế để người học tự chạy**, không phải tuyên bố đã chạy test trên một repository thật. Nếu gặp lỗi, kiểm tra đã bật Spring MVC chứ không phải WebFlux, package test đúng, class filter được component scan và test đã dùng lại **cùng `MockHttpSession`** ở request thứ hai.

Khi muốn test `POST /lab/end`, có thể thêm kiểm tra rằng session bị invalidate và request sau không thấy giá trị cũ; chú ý trong MockMvc một `MockHttpSession` đã invalidate không được tùy tiện tái sử dụng như session hợp lệ.

## 8. `@RequestScope` và `@SessionScope` trong Spring IoC

Ngoài Servlet attributes, Spring cho phép **bean scope** theo vòng đời request và session:

```java
// Snippet minh họa; mỗi class phải đặt trong file tương ứng.
@Component
@RequestScope
public class RequestContext {
    private final String traceId =
        java.util.UUID.randomUUID().toString();

    public String traceId() {
        return traceId;
    }
}

@Component
@SessionScope
public class SessionPreferences {
    private String language = "vi";

    public String language() {
        return language;
    }

    public void language(String language) {
        this.language = language;
    }
}
```

Đây là **snippet**, không phải hai class top-level đặt chung trong một file `.java`. Cần import `org.springframework.stereotype.Component`, `org.springframework.web.context.annotation.RequestScope` và `SessionScope`.

- **`@RequestScope`**: một bean instance cho request hiện tại; request khác nhận instance khác. Phù hợp dữ liệu cùng xử lý request.
- **`@SessionScope`**: một bean instance gắn với HTTP session, được dùng lại trong các request cùng phiên cho tới khi phiên kết thúc.
- Các annotation scope tiện ích này mặc định tạo **scoped proxy** theo chế độ phù hợp, cho phép một singleton khác inject bean và mỗi lần gọi proxy sẽ chuyển đến instance của request/session hiện tại.
- Không xem `@SessionScope` là thread-safe mặc định; **các request của cùng session vẫn có thể chạy đồng thời**. Nếu mutable state bị hai request cùng đọc–ghi, cần thiết kế đồng bộ hoặc dùng thao tác atomic ở store phù hợp.
- Lỗi **“Scope 'request' is not active”** có thể xảy ra khi gọi request-scoped bean ngoài một web request, ví dụ ở background job hoặc khi tự tạo thread mà không truyền context. Không lưu proxy/request object để chạy sau khi HTTP request kết thúc.

Trong nhiều API, dùng local variables và immutable DTO là đủ; đừng tạo request/session-scoped bean chỉ vì Spring cung cấp annotation.

## 9. `Model`, `@SessionAttributes` và flash attributes có khác không?

### 9.1. `Model` dùng cho request render hiện tại

`@Controller` thường đặt dữ liệu vào `Model`:

```java
@GetMapping("/hello")
public String show(Model model) {
    model.addAttribute("message", "Hello");
    return "hello";
}
```

Đoạn này **chỉ là snippet** vì thiếu class controller và template. Model data giúp view render **request hiện tại**, không tự lưu sang các request sau. Nếu browser tải lại, controller tạo/đọc model mới.

### 9.2. `@SessionAttributes` dùng cho flow có chủ đích

Spring MVC `@SessionAttributes("draft")` ở class controller cho phép các model attributes được chỉ định **lưu tạm trong HTTP session** giữa nhiều request, thường để giữ draft của một workflow. Khi hoàn thành flow, gọi `SessionStatus.setComplete()` để Spring kết thúc quản lý attributes ấy. Nó **không giống** `@SessionScope` bean:

- `@SessionAttributes` gắn với **model attributes của controller**, thường phục vụ một quy trình form.
- `@SessionScope` gắn với **bean lifecycle** của Spring IoC.
- `HttpSession` cho phép đọc/ghi attributes trực tiếp theo tên.

Không đưa toàn bộ entity hay dữ liệu bí mật vào `@SessionAttributes` mặc định; session có thể sống lâu, serialized hoặc bị thay đổi bởi hai tab.

### 9.3. Flash attributes: tồn tại tạm qua redirect

Ví dụ sau POST thành công:

```java
@PostMapping("/save")
public String save(RedirectAttributes redirect) {
    redirect.addFlashAttribute("notice", "Lưu thành công");
    return "redirect:/result";
}
```

Đây là snippet minh họa, không phải endpoint có nghiệp vụ lưu dữ liệu. `addFlashAttribute` cho phép truyền thông báo sang request đích trong mẫu **Post/Redirect/Get**. Spring MVC thường lưu flash data tạm **trong session** nhưng tự quản lý vòng đời và chọn request đích, không coi đó là session preference dài hạn.

Phân biệt rõ:

- **Request attribute:** phục vụ đúng request hiện tại.
- **Flash attribute:** thông điệp ngắn qua redirect, thường dành cho request kế tiếp **đúng đích**.
- **Session attribute:** còn tồn tại cho đến khi bị thay đổi/xóa/hết hạn.
- **Database record:** bền vững theo nghiệp vụ, không phụ thuộc session/cookie.

Flash attributes có thể gặp vấn đề khi nhiều request cùng diễn ra (polling, tải asset, redirect đồng thời), nên không dùng để lưu trạng thái giao dịch quan trọng hay dữ liệu nhiều bước.

## 10. Đưa gì vào request, session hay database?

| Dữ liệu | Nơi ưu tiên | Lý do |
| --- | --- | --- |
| Request/correlation ID | Request context hoặc tracing context | Mỗi request riêng; không mang sang request sau như dữ liệu người dùng |
| Kết quả validation và biến trung gian | Local variable, `Model`/request attribute | Chỉ cần trong quá trình xử lý hiện tại |
| Ngôn ngữ/đơn vị hiển thị tạm | Session (hoặc preference lâu dài trong DB) | Có thể cần dùng qua nhiều request |
| Xác thực phiên | Spring Security + session management chuẩn | Không tự phát minh cơ chế lưu password/token ở session |
| Giỏ hàng hoặc wizard nhiều bước nhỏ | Session có kiểm soát, hoặc database nếu cần bền vững | Cân nhắc size, đồng thời, timeout và multi-device |
| Đơn hàng, số dư, quyền truy cập, giá tiền chuẩn | Database/service nguồn sự thật | Không được tin vào session mutable như dữ liệu bền vững/đã cấp quyền |
| Thông báo “đã lưu” qua PRG | Flash attribute | Dùng một lần sau redirect |
| Dữ liệu định danh chỉ dùng trong một request | Request-scoped context, immutable security principal | Không dùng static field hoặc mutable controller instance |

**Giảm dữ liệu trong session**: nhiều session chứa object lớn gây áp lực bộ nhớ hoặc kho phân tán; không lưu file upload, response body lớn hay database connection trong session. Không lưu các đối tượng không serializable nếu dùng backend session yêu cầu serialization. Không đưa password, access token có giá trị lớn hoặc thông tin nhạy cảm vào session khi không thật sự cần; ưu tiên cơ chế security framework.

## 11. Các lỗi phổ biến và rủi ro khó thấy

### 11.1. Lưu người dùng hiện tại vào field của singleton controller

```java
// ANTI-PATTERN: Spring @RestController thường là singleton.
@RestController
class BadController {
    private String currentUser;

    @GetMapping("/set-user")
    String setUser(@RequestParam String name) {
        currentUser = name;
        return currentUser;
    }
}
```

Đây là ví dụ rủi ro, **không sử dụng thực tế**. Field `currentUser` được chia sẻ giữa nhiều request/user và có thể bị ghi đè đồng thời. Thay thế bằng method parameter, local variable, request scope hoặc truy vấn principal/session theo đúng nghiệp vụ. **Một controller singleton không phải một controller cho mỗi session.**

### 11.2. Đếm request trên session không có đồng bộ

Hai tab trong cùng browser thường dùng chung session cookie. Cả hai có thể gửi request đồng thời:

```text
Session: counter = 4
Request A đọc counter = 4
Request B đọc counter = 4
Request A ghi counter = 5
Request B ghi counter = 5
Kết quả mong muốn 6 nhưng thực tế là 5
```

Dù container cung cấp API truy cập session, điều đó **không khiến chuỗi đọc–sửa–ghi của một attribute tự động atomic**. Tránh dùng `Integer` mutable counter trong session như một số đếm giao dịch; dùng lưu trữ có concurrency control hoặc primitive atomic phù hợp với môi trường và giới hạn phân tán. Với multi-node session store, chỉ dùng synchronized/AtomicInteger trong một JVM có thể vẫn không đủ.

### 11.3. Nhầm browser tab, HTTP connection và session

- **Tab A và tab B** của cùng browser profile thường chia sẻ cookie session trên cùng site; không có session riêng mặc định cho từng tab.
- **HTTP keep-alive** giữ kết nối mạng để truyền nhiều request; nó không mang ý nghĩa “cùng user session”.
- **Thay IP** không nhất thiết thay session; **cùng IP** không đảm bảo chung session.
- **Request ID** dùng cho tracing không phải session ID hoặc authentication credential.
- **Load balancer connection** đến các node không tự đồng bộ session state.

### 11.4. Đăng nhập và session fixation

Khi người dùng đăng nhập, ứng dụng cần chống **session fixation** (kẻ tấn công cố định trước ID rồi dụ user dùng ID ấy). Spring Security có cơ chế session fixation protection: thay session ID trên Servlet container hiện đại (chẳng hạn `changeSessionId`) hoặc chính sách tương ứng. Đừng tự tắt cơ chế này. Khi logout, sử dụng cơ chế chuẩn của Spring Security để vô hiệu hóa session, xóa authentication/security context và cookie theo cấu hình.

Phiên đăng nhập không chỉ là một string `"loggedIn"` do code tự đặt vào session. Quyền truy cập cần do hệ thống xác thực/ủy quyền quyết định; mỗi tài nguyên cần kiểm tra phân quyền, không dựa vào session ID “khó đoán” là đủ.

### 11.5. Session hijacking, cookie và CSRF

Cookie phiên là credential: dùng **HTTPS + Secure + HttpOnly + SameSite phù hợp**, giới hạn domain/path, tránh gửi session ID lên URL, referrer, analytics hoặc logs. Nếu app dùng cookie-based authentication, request POST/PUT/PATCH/DELETE cần bảo vệ CSRF theo threat model (thường dùng Spring Security CSRF). XSS có thể gây thao tác dưới phiên, ngay cả khi HttpOnly chặn đọc cookie; cần output encoding và CSP phù hợp.

**Demo ở phần 6 không cấu hình Spring Security**, do đó không được triển khai công khai như endpoint thay đổi dữ liệu thật. Với production, dùng security filter chain, authentication/authorization, CSRF token và kiểm thử riêng cho các POST thao tác session.

### 11.6. Session timeout và phân tán nhiều instance

Khi chạy một instance, embedded servlet container thường quản lý session tại local process. Khi chạy nhiều replicas:

```text
Request 1 -> Node A (session chỉ ở A)
Request 2 -> Node B (không thấy session nếu B không chia sẻ store)
```

Có thể dùng load balancer **sticky sessions**, nhưng đó không phải sự thay thế hoàn hảo cho chia sẻ session (node chết hoặc tái cân bằng vẫn mất state). Với Spring Session, có thể cấu hình repository như Redis/JDBC để nhiều node truy cập cùng session. Khi đó cần xem:

- TTL/timeout và cơ chế xóa dữ liệu.
- Serialization, kích thước payload và khả năng tương thích khi nâng cấp class.
- Concurrent updates, lost update và session save policy.
- Bảo mật store, kết nối TLS, authentication và kế hoạch khi store không sẵn sàng.
- Tránh session trở thành nguồn chân lý của dữ liệu nghiệp vụ cần transaction.

**Session không phải database**: đừng tăng độ bền dữ liệu bằng cách kéo timeout lên nhiều ngày rồi lưu toàn bộ công việc/đơn hàng vào session.

## 12. Ghi chú khi ứng dụng dùng WebFlux

Ví dụ Java ở phần 6 dùng **Servlet stack**. Spring WebFlux có abstraction **`WebSession`** và request context của reactive stack (`ServerWebExchange`), không phải `jakarta.servlet.http.HttpSession`.

Khái niệm vẫn tương tự:

- Request hiện tại có attributes trên `ServerWebExchange`.
- Web session có thể được truy cập bất đồng bộ qua `exchange.getSession()`, với semantics quản lý session theo reactive runtime.
- Spring WebFlux có request/session-scoped components ở các khu vực hỗ trợ theo framework, nhưng **không trộn API Servlet với Netty WebFlux**.
- Reactor có context propagation riêng; đừng giả định `ThreadLocal` gắn với một HTTP request sẽ tiếp tục ở mọi operator/scheduler.
- Nếu dùng Spring Session reactive, repository và cấu hình khác Servlet; luôn dùng hướng dẫn riêng của Spring Session cho reactive stack.

Snippet khái niệm (trong WebFlux handler):

```java
// Trong reactive handler, không phải controller MVC ở phần 6.
Mono<String> result = exchange.getSession()
    .map(session -> {
        session.getAttributes().put("uiLanguage", "vi");
        return session.getId();
    });
```

Đoạn này chỉ minh họa API, thiếu biến `exchange` và import; **không biên dịch độc lập**. Ứng dụng thật không nên trả session ID ra client qua JSON; ở đây chỉ cho thấy `WebSession` có ID và attributes, nên thay `return session.getId()` bằng giá trị không nhạy cảm khi viết code production.

## 13. Checklist chọn scope và kiểm tra hành vi

- [ ] Giá trị có thật sự cần dùng qua **nhiều request** không? Nếu không, giữ ở local variable/request attribute.
- [ ] Có gọi `getSession(true)` khi chỉ cần đọc? Nếu có, cân nhắc `getSession(false)` để tránh session không cần thiết.
- [ ] Session có lưu giá trị nhỏ, đúng scope, không chứa credential thô/file lớn/DB connection không?
- [ ] Có request-scoped bean bị truy cập ngoài request context hoặc từ background thread không?
- [ ] Singleton/controller có field mutable chứa user-specific state không?
- [ ] Hai tab/cùng session có thể ghi đè state hoặc gây race không?
- [ ] Session timeout, invalidate, cookie Secure/HttpOnly/SameSite và session fixation đã được thiết kế không?
- [ ] POST dựa trên cookie-auth được bảo vệ CSRF và kiểm tra authorization chưa?
- [ ] Có dùng flash attribute cho thông báo một lần sau redirect, thay vì session value tồn tại quá lâu không?
- [ ] Khi nhiều node, session store chia sẻ/TTL/serialization/lost updates đã được xét chưa?
- [ ] Test có dùng cùng session ở request A/B và bỏ session ở request C để xác nhận chính xác boundary không?
- [ ] Log/tracing có request ID nhưng không làm lộ session ID hay session cookie không?

## 14. Câu hỏi tự kiểm tra

**Câu 1:** `request.setAttribute("traceId", "R1")` ở request đầu tiên có làm request thứ hai thấy `"R1"` không?  
**Đáp:** Không; mỗi request có request attributes riêng. Nếu muốn một correlation chain qua các request, phải truyền/thiết kế định danh ở tầng tracing hợp lệ, không trông chờ request attribute tự tồn tại.

**Câu 2:** Vì sao `request.getSession(false)` quan trọng ở endpoint GET chỉ đọc?  
**Đáp:** Nó trả session hiện có hoặc `null`, không tạo session mới cho client chưa có phiên.

**Câu 3:** Cookie `JSESSIONID` có chứa object `Cart` hay `UserPreferences` được set vào `HttpSession` không?  
**Đáp:** Thông thường cookie giữ session identifier; dữ liệu session được quản lý phía server hoặc qua session repository.

**Câu 4:** Hai tab cùng trình duyệt có hai `@SessionScope` bean khác nhau không?  
**Đáp:** Thường không nếu hai tab dùng cùng session cookie; chúng truy cập cùng session bean instance và có thể chạy đồng thời.

**Câu 5:** Có thể dùng biến instance `private String currentUser` trong `@RestController` để nhớ user hiện tại không?  
**Đáp:** Không; controller mặc định là singleton, dữ liệu dễ bị chia sẻ giữa các user/request.

**Câu 6:** Khi người dùng reload trang, `Model.addAttribute("message", "...")` từ request trước có tự tồn tại không?  
**Đáp:** Không; model dùng cho render request hiện tại, trừ khi có cơ chế rõ như `@SessionAttributes` hoặc flash attributes.

**Câu 7:** Logout bằng cách xóa cookie trên browser có tức thì xóa dữ liệu session trên server không?  
**Đáp:** Không đảm bảo. Server phải invalidate phiên/xử lý logout chuẩn; cookie và server-side session có vòng đời khác nhau.

**Câu 8:** Nếu load balancer chuyển request sang node khác, session có luôn đọc được không?  
**Đáp:** Không. Cần thiết kế sticky sessions hoặc shared store như Spring Session Redis/JDBC, cùng các biện pháp phục hồi.

**Câu 9:** HTTP keep-alive và session authentication có cùng nghĩa không?  
**Đáp:** Không. Keep-alive tái sử dụng TCP/HTTP connection; session gắn nhiều request qua ID/cookie.

**Câu 10:** Đưa session ID vào JSON để debug có nên không?  
**Đáp:** Không. Session ID là dữ liệu nhạy cảm, có thể dẫn tới chiếm phiên nếu bị lộ; nên dùng request ID ngẫu nhiên riêng cho tracing.

## 15. Tài liệu chính thức

- Spring Framework — **Bean Scopes** (request/session scope và scoped proxy): https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html
- Spring Framework — **@SessionAttributes**: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/sessionattributes.html
- Spring Framework — **Flash Attributes**: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/flash-attributes.html
- Spring Boot — **Common Application Properties** (session timeout, cookie flags): https://docs.spring.io/spring-boot/appendix/application-properties/
- Spring Security — **Session Management and Session Fixation Protection**: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — **CSRF Protection**: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Session — **HttpSession backed by Redis**: https://docs.spring.io/spring-session/reference/guides/java-redis.html
- Jakarta Servlet API — **HttpServletRequest** và **HttpSession**: https://jakarta.ee/specifications/servlet/

**Kết luận:** Hãy dùng **request-local state** cho dữ liệu chỉ có nghĩa trong quá trình xử lý một request, dùng **HTTP session** khi giá trị thực sự cần sống qua nhiều request của cùng phiên, và dùng **database/service** cho dữ liệu nghiệp vụ bền vững. Cookie chỉ giúp định danh phiên; nó không biến request thành session, cũng không thay thế xác thực/phân quyền. Kiểm thử ở ranh giới request–session–client và bảo vệ phiên như một thông tin xác thực nhạy cảm.