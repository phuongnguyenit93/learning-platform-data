# Phân biệt kiểm thử controller độc lập, kiểm thử hạ tầng và HTTP qua máy chủ thật

Khi kiểm thử một endpoint Spring Web, câu hỏi đầu tiên là **đang muốn chứng minh điều gì?** Một lời gọi phương thức Java thành công chưa chứng minh rằng URL, JSON, bộ lọc hay HTTP thực sự hoạt động. Ngược lại, khởi động cả ứng dụng để thử một nhánh tính toán nhỏ có thể làm bài kiểm thử chậm và khó xác định nguyên nhân lỗi.

Bài này dùng Spring MVC (Servlet) làm ví dụ chính, phân biệt ba ranh giới: **controller độc lập**, **hạ tầng Spring MVC trong bộ nhớ**, và **HTTP đến máy chủ thật**. Các tiện ích Spring Boot 3.3 được trình bày như cách cấu hình thuận tiện; khái niệm của Spring Framework không phụ thuộc vào việc có dùng Spring Boot hay không.

## 1. Hiểu đúng các ranh giới kiểm thử

Một HTTP request thật đi qua nhiều lớp, thường theo luồng:

```text
HTTP client → cổng TCP của embedded server → Servlet filters
            → DispatcherServlet → handler mapping / argument resolver
            → Controller → Service → các dependency khác
            → message converter / exception handler → HTTP response
```

Có thể kiểm thử ở những điểm khác nhau của luồng này:

| Phương án | Cách thực thi | Nạp Spring context? | Mở cổng HTTP? | Chứng minh tốt nhất |
| --- | --- | --- | --- | --- |
| Gọi phương thức controller trực tiếp | Tự tạo object, gọi method như Java thông thường | Không | Không | Nhánh xử lý và tương tác dependency của controller |
| `MockMvcBuilders.standaloneSetup(...)` | Tạo controller thủ công, dựng bộ phận MVC mặc định/cấu hình tường minh quanh controller | Không cần | Không | Request mapping, binding, JSON, status và advice mà bài test đã cấu hình |
| `MockMvcBuilders.webAppContextSetup(...)` | Dùng `WebApplicationContext` thật cùng hệ thống cấu hình Spring MVC | Có | Không | Tích hợp controller với cấu hình MVC, bean, resolver, converter, interceptor/filter được đưa vào |
| Spring Boot `@WebMvcTest` + `MockMvc` | Nạp lát cắt ứng dụng phục vụ Spring MVC, mock collaborator cần thiết | Có, giới hạn ở web slice | Không | Web layer với cấu hình mà slice thực sự nạp |
| Spring Boot `@SpringBootTest` + `@AutoConfigureMockMvc` | Nạp application context rộng hơn; gửi request mô phỏng qua MVC | Có, gần/toàn bộ ứng dụng theo cấu hình | Không | Tương tác nhiều bean thật, MVC và cấu hình ứng dụng, nhưng không kiểm tra mạng |
| `@SpringBootTest(webEnvironment = RANDOM_PORT)` + HTTP client | Khởi động embedded server, gửi request đến địa chỉ localhost/cổng thật | Có | **Có** | Đường truyền HTTP thật, container/Servlet integration, serialization và cấu hình runtime |

**Điểm quyết định:** `MockMvc` mô phỏng request/response Servlet và thực thi nhiều bước xử lý MVC, nhưng **không mở socket**. Vì vậy status 200 từ `MockMvc` không tương đương với chứng cứ rằng server có thể nhận một HTTP request qua mạng.

Cụm từ **“kiểm thử hạ tầng”** ở đây chủ yếu nói đến hạ tầng *web* (Spring MVC configuration, filter, converter, exception resolver, dependency injection), không tự động có nghĩa là kiểm thử PostgreSQL, Redis hoặc dịch vụ bên ngoài. Những dependency ấy chỉ được kiểm thử thật khi bài test thực sự khởi động/kết nối chúng.

## 2. Mẫu ứng dụng chung cho các cấp kiểm thử

Giả sử project Spring Boot 3.3, Java 17+, có `spring-boot-starter-web` và `spring-boot-starter-test`, dùng JUnit Jupiter. Đặt các lớp sau trong package `com.example.demo`. Dùng cùng một endpoint `GET /api/greetings/{name}` để thấy chính xác lớp nào đã được kiểm tra.

Tệp `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Tệp `src/main/java/com/example/demo/GreetingService.java`:

```java
package com.example.demo;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String name) {
        return "Xin chào, " + name;
    }
}
```

Tệp `src/main/java/com/example/demo/GreetingController.java`:

```java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/greetings")
public class GreetingController {
    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/{name}")
    public GreetingDto greet(@PathVariable String name) {
        return new GreetingDto(greetingService.greet(name));
    }

    public record GreetingDto(String message) {}
}
```

Khi ứng dụng chạy, request `GET /api/greetings/An` trả HTTP 200 với JSON có trường `message` là `"Xin chào, An"`. Record giúp mô tả dữ liệu response rõ ràng; việc chuyển nó thành JSON do MVC/Jackson thực hiện, **không phải** do phương thức `greet` tự tạo chuỗi JSON.

## 3. Cấp 1 — kiểm thử controller độc lập như một object Java

Tệp `src/test/java/com/example/demo/GreetingControllerUnitTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class GreetingControllerUnitTest {
    @Test
    void delegatesNameToService() {
        GreetingService service = mock(GreetingService.class);
        when(service.greet("An")).thenReturn("Xin chào, An");

        GreetingController controller = new GreetingController(service);
        GreetingController.GreetingDto result = controller.greet("An");

        assertEquals("Xin chào, An", result.message());
        verify(service).greet("An");
    }
}
```

Bài test tạo controller với `new`, cung cấp mock service và gọi method trực tiếp. Nó chứng minh controller truyền tên vào service và trả kết quả mong muốn. Không có Spring context, `DispatcherServlet`, URL matching, JSON converter hoặc filter nào chạy. Nếu gõ sai `@GetMapping("/...")`, bài test này vẫn có thể xanh.

**Khi dùng:** kiểm tra nhánh quyết định, logic điều phối hoặc tương tác collaborator. Với controller chỉ ủy quyền một dòng, giá trị tăng thêm của unit test thường nhỏ; hãy ưu tiên kiểm tra behavior có rủi ro thật và bổ sung một test kiểm chứng HTTP contract ở cấp MVC.

## 4. Cấp 2a — MockMvc standalone: chạy Spring MVC trong bộ nhớ nhưng tự chọn cấu hình

Tệp `src/test/java/com/example/demo/GreetingControllerStandaloneTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class GreetingControllerStandaloneTest {
    @Test
    void mapsHttpRequestAndSerializesResponse() throws Exception {
        GreetingService service = mock(GreetingService.class);
        when(service.greet("An")).thenReturn("Xin chào, An");

        MockMvc mvc = MockMvcBuilders
                .standaloneSetup(new GreetingController(service))
                .build();

        mvc.perform(get("/api/greetings/An"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Xin chào, An"));
    }
}
```

`standaloneSetup` không nạp application context. Nó dựng đủ thành phần MVC để xử lý một mock request, vì vậy kiểm tra được mapping từ đường dẫn sang handler, giá trị `@PathVariable` và phản hồi JSON trong cấu hình test. Tuy nhiên, custom `@ControllerAdvice`, `WebMvcConfigurer`, converter, validator, filter hoặc bảo mật của ứng dụng **không tự nhiên xuất hiện**: hãy đăng ký chúng trong builder khi chính chúng thuộc phạm vi cần kiểm thử.

Đây không đơn thuần là unit test gọi method, cũng chưa phải test ứng dụng thật. Nó là kiểm thử web behavior có phạm vi được dựng bằng tay, thường chạy nhanh và giúp cô lập controller.

## 5. Cấp 2b — kiểm thử cấu hình MVC/ứng dụng: context thật nhưng request giả

### 5.1. Spring Framework: webAppContextSetup

Khi đã có `WebApplicationContext` do Spring TestContext nạp, có thể tạo:

```java
// Đoạn trích dùng bên trong bài test đã được cấu hình WebApplicationContext.
MockMvc mvc = MockMvcBuilders.webAppContextSetup(webApplicationContext).build();
```

Ở đây `webApplicationContext` phải là context được tạo từ cấu hình MVC mong muốn. `webAppContextSetup` lấy mapping, resolver, converter và nhiều thành phần đã đăng ký từ chính context đó, nhờ vậy phát hiện lỗi tích hợp mà standalone thiếu. Dù vậy, test vẫn chạy request mô phỏng, **không** kết nối TCP tới embedded server. Có thể dùng Spring TestContext với `@WebAppConfiguration`, `@ContextConfiguration` hoặc các annotation cấu hình tương đương trong ứng dụng Spring Framework thuần.

### 5.2. Spring Boot: @WebMvcTest là một lát cắt web

Tệp `src/test/java/com/example/demo/GreetingControllerWebSliceTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(GreetingController.class)
class GreetingControllerWebSliceTest {
    @Autowired
    MockMvc mvc;

    @MockBean
    GreetingService service;

    @Test
    void returnsGreetingThroughWebLayer() throws Exception {
        when(service.greet("An")).thenReturn("Xin chào, An");

        mvc.perform(get("/api/greetings/An"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Xin chào, An"));
    }
}
```

`@WebMvcTest` là tiện ích **Spring Boot**, không phải annotation cốt lõi của Spring Framework. Nó tạo một context giới hạn vào web layer, tự cấu hình `MockMvc`, và thường dùng mock để thay collaborator bên ngoài slice. Trong **Spring Boot 3.3**, `@MockBean` thuộc `org.springframework.boot.test.mock.mockito`; ở các phiên bản Spring/Boot mới hơn có API `@MockitoBean` khác, nên phải đối chiếu version trước khi sao chép import.

Bài test kiểm tra MVC được nạp trong slice, nhưng không chứng minh service/repository thật được nối đúng. Nếu thêm security vào classpath, hãy xác định filter chain, user/role/CSRF dự kiến trong test thay vì tắt filter chỉ để được mã 200; slice có thể nạp các cấu phần bảo mật phù hợp.

### 5.3. @SpringBootTest + @AutoConfigureMockMvc: context rộng, request vẫn mock

Tệp `src/test/java/com/example/demo/GreetingControllerContextTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class GreetingControllerContextTest {
    @Autowired
    MockMvc mvc;

    @Test
    void usesRealServiceBeanThroughMvc() throws Exception {
        mvc.perform(get("/api/greetings/An"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Xin chào, An"));
    }
}
```

`@SpringBootTest` mặc định có `webEnvironment = MOCK`: tạo application context với web environment mô phỏng mà **không khởi động embedded server**. `@AutoConfigureMockMvc` cho phép kiểm thử `DispatcherServlet` dựa vào bean, MVC mapping, converter và các cấu hình được nạp. Khác với ví dụ slice, service ở đây là bean thật; nếu ứng dụng có datasource/messaging/bean khởi tạo khó khăn, việc nạp context đầy đủ cũng mang theo chi phí và phụ thuộc đó. Chỉ coi database hoặc dịch vụ ngoài là đã được kiểm thử khi test dùng hệ thống đó thật sự.

**So sánh hai cách dùng MockMvc:** standalone là hạ tầng được dựng bằng tay; `@WebMvcTest` là web slice từ Spring context; `@SpringBootTest` là context rộng hơn. Chúng đều có thể trả cùng JSON trong ví dụ, nhưng **ý nghĩa bằng chứng và nguyên nhân thất bại khác nhau**.

## 6. Cấp 3 — HTTP thật qua embedded server

Tệp `src/test/java/com/example/demo/GreetingControllerLiveHttpTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT;

@SpringBootTest(webEnvironment = RANDOM_PORT)
class GreetingControllerLiveHttpTest {
    @Autowired
    TestRestTemplate client;

    @Test
    void answersActualHttpRequest() {
        ResponseEntity<GreetingController.GreetingDto> response =
                client.getForEntity(
                        "/api/greetings/An",
                        GreetingController.GreetingDto.class
                );

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals("Xin chào, An", response.getBody().message());
    }
}
```

Spring Boot khởi động embedded server trên một cổng khả dụng ngẫu nhiên. `TestRestTemplate` do môi trường kiểm thử cung cấp gửi request HTTP đến server đó và biết cổng đang chạy. Do đó bài test đi qua client HTTP, kết nối mạng loopback, servlet container, filter chain, MVC và các bean ứng dụng. Muốn tự tạo client khác (ví dụ `RestClient` hoặc `WebTestClient.bindToServer()`), hãy dùng base URL trỏ đến localhost và cổng được cấp; cấu hình client quyết định có thực sự gửi request mạng hay không.

**Một sai lầm dễ gặp:** khai báo `@SpringBootTest(webEnvironment = RANDOM_PORT)` nhưng chỉ gọi `mockMvc.perform(...)` rồi tuyên bố “đã kiểm thử HTTP thật”. Chỉ việc khởi động server không chứng minh request được gửi đến socket; chính **client/đường thực thi của lời gọi** mới xác định ranh giới được kiểm thử.

Máy chủ thật giúp kiểm tra những vấn đề khó tái hiện với mock Servlet, chẳng hạn behavior phụ thuộc container, error page, cấu hình cổng và một phần HTTP transport. Nó vẫn **không tự động** kiểm tra reverse proxy, TLS termination, DNS, load balancer, firewall, production database hoặc hạ tầng cloud. Các phần đó cần môi trường kiểm thử tích hợp riêng.

Lưu ý transaction: nếu test method đánh dấu `@Transactional` khi dùng server thật, client và server chạy ở các thread/transaction khác nhau; rollback transaction của test **không tự rollback** thay đổi dữ liệu đã commit trong request phía server. Hãy dùng cơ chế dọn dữ liệu, database dùng riêng cho test hoặc transaction phù hợp phía ứng dụng.

## 7. So sánh cùng một lỗi và cách chọn cấp kiểm thử

Giả sử developer vô tình đổi `@GetMapping("/{name}")` thành `@GetMapping("/fixed")` nhưng giữ nguyên nội dung phương thức:

- **Gọi controller trực tiếp** có thể vẫn xanh vì không nhìn annotation định tuyến.
- **MockMvc standalone**, **web slice** và **full-context MockMvc** sẽ phát hiện `GET /api/greetings/An` không còn đi đến đúng handler.
- **HTTP thật** cũng phát hiện lỗi; thêm nữa có thể bắt lỗi do server/container/transport mà MockMvc không tái hiện.

Giả sử một global `@ControllerAdvice` được đăng ký qua cấu hình ứng dụng nhưng test standalone quên thêm vào builder. Test standalone có thể không chứng minh error body/status giống runtime; context-based test sẽ có cơ hội kiểm tra đúng advice **nếu advice thực sự được nạp**. Nếu dùng security filter trong production, phải xét filter chain của chính mỗi chế độ; không mặc nhiên suy ra “MockMvc kiểm thử security” chỉ vì dùng `mockMvc.perform`.

| Câu hỏi cần trả lời | Điểm bắt đầu phù hợp | Test bổ sung khi cần |
| --- | --- | --- |
| Controller truyền argument và chọn nhánh đúng không? | Gọi method trực tiếp với mock/stub | MockMvc nếu URL và contract quan trọng |
| Path, query, header, validation, converter, JSON, status có đúng không? | MockMvc standalone hoặc `@WebMvcTest` | Context-based MockMvc khi phụ thuộc cấu hình thực tế |
| `@ControllerAdvice`, filters, interceptors, WebMvcConfigurer, Security hoạt động cùng nhau không? | `webAppContextSetup` / `@WebMvcTest` với cấu hình phù hợp | `@SpringBootTest + @AutoConfigureMockMvc` nếu cần bean rộng hơn |
| Controller kết nối service/repository/config thực của ứng dụng không? | `@SpringBootTest + @AutoConfigureMockMvc` | HTTP thật nếu transport/container cũng quan trọng |
| Endpoint thực sự nhận HTTP qua port và trả response được không? | `@SpringBootTest(RANDOM_PORT)` + HTTP client | Kiểm thử môi trường triển khai cho proxy/TLS/infra thật |

Không có “cấp càng cao càng tốt” cho mọi test. Một bộ test hợp lý thường nhiều test nhanh ở ranh giới nhỏ để chỉ ra lỗi rõ ràng, thêm test context kiểm chứng wiring và số ít test HTTP thật cho những luồng đại diện hoặc rủi ro cao. Cân nhắc chi phí khởi tạo Spring context, container và dependency bên ngoài. Spring TestContext có cache context dùng lại giữa các bài test có cấu hình tương đương, nhưng không loại bỏ hoàn toàn chi phí tích hợp.

## 8. Chạy và đọc kết quả

Với project Spring Boot 3.3 đã khai báo `spring-boot-starter-web` và `spring-boot-starter-test`, đặt mỗi class vào đúng package/tệp như trên rồi chạy:

```bash
./gradlew test
```

Trên Windows PowerShell có thể dùng `.\gradlew.bat test`. Các kiểm thử mẫu khẳng định:

1. Unit: method trả chuỗi mong đợi và đã gọi service với đối số đúng.
2. Standalone: mock MVC request khớp đường dẫn và JSON response.
3. Web slice: MVC slice dùng mock service, trả status/JSON đúng.
4. Full context: bean service thật được wiring qua MVC và trả response đúng.
5. Live HTTP: HTTP client nhận status 200 và giải mã JSON do embedded server trả về.

Đó là **kỳ vọng từ source ví dụ**, không phải log thực thi được cung cấp sẵn. Nếu test không chạy, kiểm tra dependency/version, cấu hình security hoặc context trước khi kết luận chức năng controller sai. Khi bài học dùng Spring Framework thuần không có Spring Boot, thay các annotation Boot (`@WebMvcTest`, `@SpringBootTest`) bằng cấu hình Spring TestContext phù hợp.

## 9. Lỗi phổ biến và checklist kiểm chứng

- **Nhầm unit test với HTTP test:** gọi trực tiếp `controller.greet(...)` không xác minh route annotation, binding hay serialization.
- **Nhầm MockMvc với server thật:** MockMvc xử lý request Servlet giả trong bộ nhớ; không chứng minh cổng mạng mở.
- **Nhầm context đầy đủ với integration đầy đủ:** một context có thể chứa bean/mock hoặc datasource giả; hãy kiểm tra dependency đang thật hay giả.
- **Standalone bỏ sót cấu hình:** nếu behavior phụ thuộc exception handler, custom JSON module, interceptor hoặc security filter, cần tự cấu hình builder hoặc chuyển sang context-based test.
- **Lạm dụng @WebMvcTest cho business logic:** collaborator thường mock nên bài test không chứng minh business/service thật đúng.
- **Dùng RANDOM_PORT nhưng không gửi request mạng:** chọn HTTP client thực sự hướng về server, không gọi MockMvc để đại diện cho transport.
- **Test lỗi quá phụ thuộc vào JSON string nguyên văn:** nếu thứ tự trường/format không là hợp đồng công khai, dùng JSONPath hay parse body để kiểm tra giá trị có ý nghĩa.
- **Test HTTP thật dùng dữ liệu lâu dài:** cô lập state, quản lý fixture và dọn dữ liệu; đặc biệt cẩn trọng với transaction rollback khi client/server ở thread riêng.

Trước khi xem một test là đủ, hãy hỏi: **(1)** request đã đi qua lớp nào? **(2)** Spring context có được nạp không và gồm những bean nào? **(3)** dependency nào là mock? **(4)** TCP/HTTP thật có xảy ra không? **(5)** assertion đang chứng minh status, body, authorization, validation hay business outcome nào? Câu trả lời phải dựa trên setup và lời gọi thực tế của test, không chỉ tên annotation.

### Tài liệu tham khảo

- Spring Framework — MockMvc overview: https://docs.spring.io/spring-framework/reference/testing/mockmvc/overview.html
- Spring Framework — MockMvc setup options: https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/setup-options.html
- Spring Framework — WebTestClient setup (mock hoặc live server): https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Boot 3.3 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
