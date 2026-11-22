# Xác nhận body JSON và chuyển thành kiểu dữ liệu

Khi kiểm thử REST API bằng Spring MVC, việc kiểm tra status HTTP là chưa đủ. Một endpoint có thể trả về `200 OK` nhưng body JSON vẫn thiếu trường, sai giá trị, sai cấu trúc hoặc không tương thích với DTO mà client mong đợi. Bài kiểm thử tầng web cần xác nhận nội dung JSON và, khi phù hợp, thử chuyển body đó thành kiểu dữ liệu Java.

Spring Framework 6.2 giới thiệu `MockMvcTester`, một API kiểm thử dựa trên AssertJ dành cho `MockMvc`. Thay vì kết hợp nhiều `ResultMatcher` riêng lẻ, ta có thể viết assertion theo chuỗi: kiểm tra status, đọc body JSON, trích xuất giá trị theo JSONPath hoặc chuyển toàn bộ body thành một class Java rồi kiểm tra đối tượng đó.

`MockMvcTester` vẫn dùng hạ tầng `MockMvc` và Spring MVC Test. Nó không khởi động HTTP server thật. Giá trị chính của API này là cách diễn đạt assertion gọn và tập trung vào kết quả mà client nhận được.

## 1. Vì sao cần kiểm tra body JSON?

Giả sử endpoint trả về thông tin người dùng:

```java
@RestController
@RequestMapping("/api/users")
class UserController {

    @GetMapping("/{id}")
    UserResponse findById(@PathVariable long id) {
        return new UserResponse(id, "Lan", "ACTIVE");
    }
}

record UserResponse(long id, String name, String status) {
}
```

Một test chỉ kiểm tra status:

```java
mockMvc.perform(get("/api/users/42"))
        .andExpect(status().isOk());
```

chỉ xác nhận request được xử lý thành công theo mã HTTP. Test chưa xác nhận body có `id`, `name` và `status` đúng hay không. Nếu quá trình serialize bỏ sót trường hoặc controller trả nhầm dữ liệu, assertion status vẫn có thể thành công.

Kiểm tra JSON giúp xác nhận hợp đồng response ở mức mà client tiêu thụ. Có hai hướng thường dùng:

- Kiểm tra một số giá trị cụ thể bằng JSONPath khi chỉ một vài trường là trọng tâm.
- Chuyển toàn bộ JSON thành DTO hoặc kiểu dữ liệu Java khi muốn xác nhận cấu trúc và giá trị của đối tượng response.

## 2. `MockMvcTester` là gì?

`MockMvcTester` thuộc package `org.springframework.test.web.servlet.assertj`. API này cung cấp các request builder và assertion theo phong cách AssertJ cho kết quả `MockMvc`.

Các thành phần liên quan:

| Thành phần | Vai trò |
| --- | --- |
| `MockMvc` | Gửi request giả lập qua `DispatcherServlet` và Spring MVC. |
| `MockMvcTester` | Cung cấp cách tạo request và kiểm tra kết quả bằng AssertJ. |
| `assertThat(...)` | Bắt đầu chuỗi assertion AssertJ. |
| `bodyJson()` | Truy cập body dưới dạng JSON để kiểm tra hoặc chuyển đổi. |
| `extractingPath(...)` | Trích xuất một giá trị từ JSON bằng biểu thức JSONPath. |
| `convertTo(...)` | Chuyển body JSON thành kiểu dữ liệu Java được chỉ định. |

`MockMvcTester` có từ Spring Framework 6.2. Để sử dụng, project cần phiên bản Spring Test tương ứng và AssertJ trên test classpath. Nếu dùng Spring Boot, hãy dùng phiên bản Boot có hỗ trợ Spring Framework 6.2 trở lên và dependency kiểm thử phù hợp.

## 3. Khởi tạo `MockMvcTester`

Có thể tạo `MockMvc` từ một controller được chọn rồi bọc bằng `MockMvcTester`:

```java
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.assertj.MockMvcTester;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new UserController())
        .build();

MockMvcTester mvc = MockMvcTester.create(mockMvc);
```

Nếu muốn kiểm tra cấu hình MVC đã nạp từ `WebApplicationContext`, có thể tạo `MockMvc` bằng `webAppContextSetup(...)` rồi truyền vào `MockMvcTester.create(...)`:

```java
MockMvc mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .build();

MockMvcTester mvc = MockMvcTester.create(mockMvc);
```

Nguồn cấu hình của `MockMvc` vẫn quyết định phạm vi tích hợp. `MockMvcTester` chỉ thay đổi cách tạo request và viết assertion; nó không tự biến một standalone test thành test nạp toàn bộ application context.

Trong Spring Boot, `@AutoConfigureMockMvc` có thể tự cấu hình `MockMvcTester` khi môi trường test có AssertJ và phiên bản Boot hỗ trợ tính năng này. Khi đó có thể inject trực tiếp tester thay vì tự tạo từ `MockMvc`:

```java
@SpringBootTest
@AutoConfigureMockMvc
class UserControllerIntegrationTest {

    @Autowired
    private MockMvcTester mvc;
}
```

Nếu cấu hình Boot của project không cung cấp bean tester, có thể inject `MockMvc` rồi gọi `MockMvcTester.create(mockMvc)` trong `@BeforeEach`. Hãy chọn một cách khởi tạo phù hợp với phiên bản Spring Boot và cấu hình test đang sử dụng.

## 4. Gửi request và xác nhận body JSON bằng JSONPath

Giả sử `MockMvcTester` đã được tạo trong field `mvc`, test có thể gửi GET request và kiểm tra response:

```java
import static org.assertj.core.api.Assertions.assertThat;

@Test
void shouldReturnUserAsJson() {
    assertThat(mvc.get().uri("/api/users/42"))
            .hasStatusOk()
            .bodyJson()
            .extractingPath("$.id")
            .isEqualTo(42);
}
```

Chuỗi assertion được đọc từ trái sang phải:

1. `mvc.get().uri(...)` tạo GET request đến endpoint.
2. `assertThat(...)` bắt đầu assertion trên kết quả request.
3. `hasStatusOk()` xác nhận response có status 200.
4. `bodyJson()` chuyển trọng tâm assertion sang body JSON.
5. `extractingPath("$.id")` lấy giá trị thuộc tính `id` ở cấp gốc JSON.
6. `isEqualTo(42)` so sánh giá trị vừa trích xuất với kết quả mong đợi.

Có thể kiểm tra nhiều trường bằng các assertion riêng:

```java
@Test
void shouldExposeExpectedUserFields() {
    var result = mvc.get().uri("/api/users/42");

    assertThat(result).hasStatusOk();
    assertThat(result).bodyJson().extractingPath("$.id").isEqualTo(42);
    assertThat(result).bodyJson().extractingPath("$.name").isEqualTo("Lan");
    assertThat(result).bodyJson().extractingPath("$.status").isEqualTo("ACTIVE");
}
```

JSONPath hữu ích khi cần kiểm tra một phần response mà không phải tạo DTO chỉ để đọc vài trường. Một số biểu thức thường gặp:

| JSONPath | Giá trị được chọn |
| --- | --- |
| `$.id` | Thuộc tính `id` ở cấp gốc. |
| `$.profile.email` | Thuộc tính `email` bên trong object `profile`. |
| `$.items[0].name` | `name` của phần tử đầu tiên trong mảng `items`. |
| `$.items.length()` | Số phần tử trong mảng `items` theo cú pháp JSONPath hỗ trợ. |
| `$.items[*].id` | Các giá trị `id` trong mọi phần tử của `items`. |

Hãy dùng biểu thức phù hợp với cấu trúc response thực tế. Khi cấu trúc JSON thay đổi, JSONPath có thể không còn khớp; assertion thất bại giúp chỉ ra hợp đồng response đã thay đổi.

## 5. Chuyển body JSON thành DTO bằng `convertTo(...)`

Khi response đại diện cho một object có cấu trúc, có thể chuyển JSON thành kiểu Java rồi kiểm tra đối tượng. Điều này hữu ích khi nhiều trường có liên quan và test muốn xác nhận cả object thay vì chỉ một path.

DTO response:

```java
public record UserResponse(long id, String name, String status) {
}
```

Test chuyển body thành `UserResponse`:

```java
@Test
void shouldConvertJsonBodyToUserResponse() {
    assertThat(mvc.get().uri("/api/users/42"))
            .hasStatusOk()
            .bodyJson()
            .convertTo(UserResponse.class)
            .isEqualTo(new UserResponse(42L, "Lan", "ACTIVE"));
}
```

`convertTo(UserResponse.class)` đọc JSON response và chuyển nó thành một instance `UserResponse`. Vì record có equality dựa trên các component, `isEqualTo(...)` có thể so sánh toàn bộ giá trị của đối tượng mong đợi với kết quả chuyển đổi.

Nếu không dùng record, có thể dùng class DTO có constructor hoặc getter/setter tương thích với JSON mapper được cấu hình. Điều quan trọng là kiểu đích phải có thể được mapper tạo và gán dữ liệu.

### Kiểm tra object bằng `satisfies(...)`

Khi muốn kiểm tra từng trường hoặc cần assertion phức tạp, có thể dùng `satisfies(...)`:

```java
@Test
void shouldConvertAndInspectUserResponse() {
    assertThat(mvc.get().uri("/api/users/42"))
            .hasStatusOk()
            .bodyJson()
            .convertTo(UserResponse.class)
            .satisfies(user -> {
                assertThat(user.id()).isEqualTo(42L);
                assertThat(user.name()).isNotBlank();
                assertThat(user.status()).isEqualTo("ACTIVE");
            });
}
```

`convertTo(...)` trả về assertion cho đối tượng Java đã được chuyển đổi. `satisfies(...)` nhận đối tượng đó để thực hiện nhiều assertion liên quan. Cách này hữu ích khi cần kiểm tra invariant giữa các trường hoặc khi không muốn tạo một object expected đầy đủ.

## 6. Kiểm tra JSON lồng nhau và collection

Một response có thể chứa object lồng nhau:

```java
record AddressResponse(String city, String country) {
}

record CustomerResponse(long id, String name, AddressResponse address) {
}
```

JSON tương ứng:

```json
{
  "id": 7,
  "name": "Minh",
  "address": {
    "city": "Ho Chi Minh City",
    "country": "Vietnam"
  }
}
```

Có thể kiểm tra trực tiếp bằng JSONPath:

```java
assertThat(mvc.get().uri("/api/customers/7"))
        .hasStatusOk()
        .bodyJson()
        .extractingPath("$.address.city")
        .isEqualTo("Ho Chi Minh City");
```

Hoặc chuyển thành DTO:

```java
assertThat(mvc.get().uri("/api/customers/7"))
        .hasStatusOk()
        .bodyJson()
        .convertTo(CustomerResponse.class)
        .isEqualTo(new CustomerResponse(
                7L,
                "Minh",
                new AddressResponse("Ho Chi Minh City", "Vietnam")
        ));
```

Với response dạng collection, có thể dùng JSONPath để kiểm tra số phần tử và giá trị ở các vị trí cần thiết:

```java
assertThat(mvc.get().uri("/api/users"))
        .hasStatusOk()
        .bodyJson()
        .extractingPath("$[0].name")
        .isEqualTo("Lan");
```

Nếu cần chuyển JSON array thành `List<UserResponse>`, kiểu đích có generic type. Khi đó cần dùng API chuyển đổi hỗ trợ kiểu tham chiếu tổng quát và JSON mapper tương ứng, thay vì chỉ truyền `List.class` vì type erasure làm mất kiểu phần tử. Nếu test chỉ cần xác nhận vài phần tử, JSONPath thường đơn giản hơn.

## 7. Kiểm tra request POST và response JSON

`MockMvcTester` hỗ trợ các HTTP method tương tự `MockMvc`. Có thể tạo POST request với content type JSON và body JSON:

```java
@Test
void shouldCreateUserAndReturnJson() {
    String requestBody = """
            {
              "name": "Lan"
            }
            """;

    assertThat(mvc.post().uri("/api/users")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(requestBody))
            .hasStatus(201)
            .bodyJson()
            .extractingPath("$.name")
            .isEqualTo("Lan");
}
```

Ở đây, `contentType(...)` khai báo định dạng request body; `content(...)` cung cấp nội dung JSON; `hasStatus(201)` kiểm tra status Created. Có thể dùng `hasStatusCreated()` nếu muốn diễn đạt rõ status 201 theo API assertion của phiên bản đang dùng.

Khi API trả về DTO, có thể kết hợp typed conversion:

```java
assertThat(mvc.post().uri("/api/users")
                .contentType(MediaType.APPLICATION_JSON)
                .content(requestBody))
        .hasStatus(201)
        .bodyJson()
        .convertTo(UserResponse.class)
        .satisfies(user -> {
            assertThat(user.name()).isEqualTo("Lan");
            assertThat(user.status()).isEqualTo("ACTIVE");
        });
```

Test như vậy xác nhận cả request mapping, JSON request binding, logic controller và JSON response serialization trong phạm vi cấu hình `MockMvc` đã tạo.

## 8. Kiểm tra lỗi JSON và response lỗi

Body JSON có thể là một error object. Ví dụ API trả lỗi theo cấu trúc:

```java
record ApiError(String code, String message) {
}
```

Test có thể xác nhận status và từng trường lỗi:

```java
assertThat(mvc.get().uri("/api/users/999"))
        .hasStatus(404)
        .bodyJson()
        .extractingPath("$.code")
        .isEqualTo("USER_NOT_FOUND");
```

Hoặc chuyển body thành DTO lỗi:

```java
assertThat(mvc.get().uri("/api/users/999"))
        .hasStatus(404)
        .bodyJson()
        .convertTo(ApiError.class)
        .isEqualTo(new ApiError(
                "USER_NOT_FOUND",
                "User 999 was not found"
        ));
```

Nếu response không phải JSON, không nên gọi `bodyJson()` chỉ để kiểm tra text. Dùng assertion body text hoặc header phù hợp với loại response. Nếu endpoint trả về `204 No Content`, body không tồn tại nên không có JSON để chuyển đổi.

## 9. JSONPath và typed conversion: nên chọn cách nào?

Hai cách kiểm tra phục vụ những mục đích khác nhau:

| Tiêu chí | JSONPath với `extractingPath(...)` | `convertTo(...)` |
| --- | --- | --- |
| Phạm vi | Một hoặc một số trường cụ thể. | Toàn bộ body thành kiểu Java. |
| DTO expected | Không bắt buộc. | Cần kiểu đích tương thích. |
| Object lồng nhau | Trích xuất trực tiếp theo path. | Mapper tạo object lồng nhau theo cấu hình. |
| Collection | Dễ kiểm tra phần tử hoặc thuộc tính bằng path. | Cần xử lý generic type nếu muốn có kiểu phần tử cụ thể. |
| Khi phù hợp | Chỉ một vài giá trị là hợp đồng cần xác nhận. | Muốn xác nhận response tương thích với DTO client sử dụng. |

Không cần chuyển mọi response thành DTO trong mọi test. JSONPath phù hợp với assertion nhỏ, trong khi typed conversion có ý nghĩa khi response schema là một phần quan trọng của hợp đồng API.

## 10. Vai trò của JSON mapper và message converter

Spring MVC dùng `HttpMessageConverter` để chuyển đổi giữa HTTP body và đối tượng Java. Với JSON, ứng dụng thường sử dụng Jackson thông qua `MappingJackson2HttpMessageConverter` khi dependency tương ứng có mặt.

Quá trình trong một response JSON có thể biểu diễn như sau:

```text
Controller trả về object Java
          |
          v
HttpMessageConverter (ví dụ Jackson)
          |
          v
HTTP response body dạng JSON
          |
          +--> JSONPath assertion đọc giá trị trong JSON
          |
          +--> bodyJson().convertTo(Dto.class)
                    |
                    v
              JSON mapper tạo object Java
                    |
                    v
              AssertJ kiểm tra object
```

Có hai chiều chuyển đổi cần phân biệt:

- Khi controller trả object, message converter của Spring MVC serialize object thành JSON response.
- Khi test gọi `convertTo(...)`, JSON response được deserialize thành kiểu đích để assertion kiểm tra.

Hai chiều có thể dùng cấu hình mapper tương ứng, nhưng test không nên mặc định rằng mọi kiểu Java đều tự chuyển đổi được. DTO cần tương thích với mapper, module cần thiết phải có trên classpath và các custom serializer/deserializer phải được cấu hình nếu response phụ thuộc chúng.

Nếu test dùng `standaloneSetup`, message converter có thể được cung cấp hoặc tùy chỉnh trong `MockMvcBuilders`. Nếu test dùng `webAppContextSetup`, converter được lấy từ MVC configuration đã nạp. Khi dùng Spring Boot với `@AutoConfigureMockMvc`, các converter thường theo cấu hình ứng dụng.

## 11. Điều kiện và lỗi thường gặp

**Spring Framework chưa đủ phiên bản.**

`MockMvcTester` được giới thiệu trong Spring Framework 6.2. Nếu project dùng phiên bản cũ, class hoặc API tương ứng không tồn tại. Cần nâng phiên bản Spring đồng bộ với dependency management của project thay vì thêm một JAR Spring Test lệch phiên bản.

**Thiếu AssertJ trên test classpath.**

`MockMvcTester` được thiết kế quanh AssertJ. Hãy bảo đảm dependency AssertJ có mặt trong test runtime. Với Spring Boot, `spring-boot-starter-test` thường cung cấp các thư viện kiểm thử phổ biến bao gồm AssertJ.

**JSON response không hợp lệ.**

`bodyJson()` cần body có thể phân tích như JSON. Nếu controller trả text, HTML hoặc body rỗng, assertion JSON sẽ thất bại. Kiểm tra content type và response body trước khi chọn JSON assertion.

**JSONPath không khớp cấu trúc.**

Nếu path sai hoặc trường nằm trong object lồng nhau, biểu thức có thể không tìm thấy giá trị. Đối chiếu JSONPath với cấu trúc JSON thực tế, đặc biệt với array và object lồng nhau.

**Giá trị số có kiểu khác với expected.**

JSON number có thể được biểu diễn bằng kiểu số khác tùy parser và cách trích xuất. Chọn expected value tương thích hoặc chuyển đổi sang DTO có kiểu rõ ràng để assertion dễ hiểu.

**DTO không tương thích với JSON mapper.**

Nếu constructor, property hoặc kiểu trường không phù hợp, `convertTo(...)` có thể thất bại. Kiểm tra cấu trúc DTO, Jackson annotations và các module cần thiết.

**Dùng `List.class` rồi mong nhận được `List<UserResponse>`.**

Java generic type bị type erasure. Chỉ truyền `List.class` không giữ thông tin kiểu phần tử. Dùng hỗ trợ generic type của API chuyển đổi nếu cần deserialize collection có kiểu phần tử cụ thể, hoặc kiểm tra từng phần tử bằng JSONPath.

**Nhầm assertion JSON với kiểm tra JSON được serialize theo đúng từng ký tự.**

JSONPath kiểm tra dữ liệu theo cấu trúc. Nếu thứ tự thuộc tính hoặc khoảng trắng không phải hợp đồng, không nên kiểm tra chuỗi JSON thô một cách cứng nhắc. Nếu định dạng chuỗi chính xác là yêu cầu, hãy kiểm tra body text riêng và hiểu rằng test sẽ nhạy với cách format.

## 12. Khi nào vẫn nên dùng `MockMvc` và `ResultMatcher`?

`MockMvcTester` là API thay thế thuận tiện cho cách viết assertion, nhưng `MockMvc` và `MockMvcResultMatchers` vẫn hữu ích. Một số project có sẵn test dùng:

```java
mockMvc.perform(get("/api/users/42"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.name").value("Lan"));
```

Cách này vẫn hợp lệ. Có thể chọn `MockMvcTester` cho test mới hoặc khi muốn dùng AssertJ fluent assertions, đồng thời giữ `MockMvc` truyền thống ở những test đã rõ ràng và ổn định. Không cần chuyển đổi tất cả test chỉ vì API mới xuất hiện.

Điều quan trọng là assertion phải thể hiện đúng hợp đồng response: status, header, body JSON, kiểu dữ liệu và các giá trị mà client phụ thuộc.

## 13. Quy trình kiểm thử body JSON

Khi viết test cho endpoint trả JSON, có thể đi theo trình tự:

1. Tạo `MockMvc` theo phạm vi cần kiểm tra: standalone controller, web application context hoặc Spring Boot test.
2. Tạo `MockMvcTester` bằng `MockMvcTester.create(mockMvc)` hoặc inject tester do Spring Boot cấu hình nếu phiên bản hỗ trợ.
3. Gửi request bằng `get()`, `post()` hoặc method phù hợp và khai báo URI, header, content type, body khi cần.
4. Xác nhận HTTP status trước khi kiểm tra nội dung.
5. Gọi `bodyJson()` để khẳng định response là JSON.
6. Dùng `extractingPath(...)` cho những trường cụ thể hoặc `convertTo(Dto.class)` để kiểm tra object hoàn chỉnh.
7. Bổ sung assertion cho response lỗi, collection, object lồng nhau và trường hợp body rỗng khi đó là hành vi của endpoint.
8. Bảo đảm mapper và converter trong test tương thích với cấu hình mà endpoint cần sử dụng.

Ví dụ ngắn gọn cho một response DTO:

```java
assertThat(mvc.get().uri("/api/users/42"))
        .hasStatusOk()
        .bodyJson()
        .convertTo(UserResponse.class)
        .isEqualTo(new UserResponse(42L, "Lan", "ACTIVE"));
```

Đoạn test này xác nhận response HTTP thành công, body có thể đọc như JSON và dữ liệu JSON chuyển được thành đúng kiểu response mà client mong đợi.

## Kết luận

`MockMvcTester` trong Spring Framework 6.2+ cung cấp cách kiểm tra response MockMvc bằng AssertJ. `bodyJson()` mở phần body JSON để assertion; `extractingPath(...)` kiểm tra các giá trị cụ thể theo JSONPath; `convertTo(...)` deserialize JSON thành DTO hoặc kiểu Java để kiểm tra toàn bộ đối tượng.

Hãy chọn JSONPath khi chỉ cần xác nhận một phần hợp đồng và typed conversion khi cấu trúc DTO là điều cần kiểm tra. Kết hợp status, body JSON và kiểu dữ liệu giúp test phát hiện lỗi response mà assertion status đơn thuần không thể nhìn thấy.
