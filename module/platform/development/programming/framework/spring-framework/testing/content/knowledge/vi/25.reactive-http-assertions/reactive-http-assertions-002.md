# Body dưới dạng DTO, danh sách hoặc kiểu generic

Khi kiểm thử một HTTP endpoint, ta thường cần xác nhận body response có thể được client đọc thành kiểu dữ liệu mà hợp đồng API công bố. Với JSON, body có thể biểu diễn một DTO, một object lồng nhau, một danh sách hoặc cấu trúc generic như `Page<UserResponse>` hay `Map<String, List<OrderResponse>>`. Chỉ kiểm tra status hoặc một vài chuỗi JSON chưa chắc phát hiện được lỗi về kiểu dữ liệu, cấu trúc lồng nhau hay khả năng deserialize.

`MockMvcTester` của Spring Framework 6.2+ hỗ trợ đọc body JSON và chuyển nó thành kiểu Java bằng `bodyJson().convertTo(...)`. Ta có thể chuyển thành một class cụ thể, một DTO chứa danh sách hoặc một kiểu tổng quát được mô tả bằng `ParameterizedTypeReference`. Sau đó AssertJ kiểm tra object đã chuyển đổi bằng equality, property assertion hoặc `satisfies(...)`.

## 1. Từ JSON response đến kiểu dữ liệu Java

Giả sử một endpoint trả về thông tin người dùng:

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

Response JSON có dạng:

```json
{
  "id": 42,
  "name": "Lan",
  "status": "ACTIVE"
}
```

Ở phía server, Spring MVC dùng `HttpMessageConverter` (thường là Jackson JSON converter) để serialize `UserResponse` thành JSON. Ở phía test, `convertTo(UserResponse.class)` deserialize JSON response thành một instance Java. Ta có thể so sánh instance đó với object mong đợi.

```java
assertThat(mvc.get().uri("/api/users/42"))
        .hasStatusOk()
        .bodyJson()
        .convertTo(UserResponse.class)
        .isEqualTo(new UserResponse(42L, "Lan", "ACTIVE"));
```

Đây là phép kiểm tra hợp đồng response ở mức kiểu dữ liệu. Test xác nhận JSON có thể được ánh xạ thành `UserResponse` và các trường có giá trị mong đợi. Nếu JSON thiếu một trường bắt buộc theo logic ứng dụng, sai kiểu, hoặc có cấu trúc không tương thích với DTO, quá trình chuyển đổi hoặc assertion có thể thất bại.

## 2. Chuẩn bị `MockMvcTester`

`MockMvcTester` thuộc package `org.springframework.test.web.servlet.assertj` và được giới thiệu trong Spring Framework 6.2. Nó cung cấp API request và assertion theo phong cách AssertJ cho kết quả `MockMvc`.

Có thể tạo tester từ một `MockMvc` đã được cấu hình:

```java
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.assertj.MockMvcTester;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new UserController())
        .build();

MockMvcTester mvc = MockMvcTester.create(mockMvc);
```

Nếu muốn kiểm tra cấu hình MVC đã nạp từ `WebApplicationContext`, tạo `MockMvc` bằng `webAppContextSetup(...)` rồi bọc bằng `MockMvcTester.create(...)`. Nguồn cấu hình của `MockMvc` quyết định phạm vi test; `MockMvcTester` chỉ thay đổi cách viết request và assertion.

Với Spring Boot phiên bản có hỗ trợ MockMvcTester, có thể inject tester được cấu hình tự động khi AssertJ có trên test classpath:

```java
@SpringBootTest
@AutoConfigureMockMvc
class UserControllerIntegrationTest {

    @Autowired
    private MockMvcTester mvc;
}
```

Nếu ứng dụng chưa dùng Spring Framework 6.2 hoặc phiên bản Boot chưa hỗ trợ auto-configuration này, hãy nâng phiên bản theo dependency management đang dùng hoặc tự tạo tester từ `MockMvc`. Không nên trộn các phiên bản `spring-test` khác nhau trong cùng ứng dụng.

## 3. Chuyển body thành một DTO cụ thể

Đối với JSON object ở cấp gốc, truyền class đích cho `convertTo(...)`:

```java
public record UserResponse(long id, String name, String status) {
}

@Test
void shouldReturnUserAsTypedResponse() {
    assertThat(mvc.get().uri("/api/users/42"))
            .hasStatusOk()
            .bodyJson()
            .convertTo(UserResponse.class)
            .isEqualTo(new UserResponse(42L, "Lan", "ACTIVE"));
}
```

Các bước trong chuỗi assertion:

1. `mvc.get().uri(...)` gửi request GET qua `MockMvc`.
2. `hasStatusOk()` xác nhận response có status 200.
3. `bodyJson()` yêu cầu đọc body như JSON.
4. `convertTo(UserResponse.class)` deserialize body thành kiểu `UserResponse`.
5. `isEqualTo(...)` so sánh object kết quả với object mong đợi.

Record phù hợp với DTO response vì constructor và component được khai báo rõ, đồng thời record tự cung cấp `equals()` và `hashCode()`. Với class thông thường, có thể dùng constructor hoặc getter/setter mà JSON mapper hỗ trợ.

Ví dụ class mutable:

```java
public class UserResponse {

    private long id;
    private String name;
    private String status;

    public UserResponse() {
    }

    public long getId() {
        return id;
    }

    public void setId(long id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }
}
```

Với class này, test có thể dùng `satisfies(...)` để kiểm tra từng thuộc tính:

```java
assertThat(mvc.get().uri("/api/users/42"))
        .hasStatusOk()
        .bodyJson()
        .convertTo(UserResponse.class)
        .satisfies(user -> {
            assertThat(user.getId()).isEqualTo(42L);
            assertThat(user.getName()).isEqualTo("Lan");
            assertThat(user.getStatus()).isEqualTo("ACTIVE");
        });
```

`isEqualTo(...)` phù hợp khi DTO có equality theo giá trị. `satisfies(...)` linh hoạt hơn khi class không override `equals()`, khi chỉ muốn kiểm tra một số thuộc tính hoặc khi cần xác nhận quan hệ giữa nhiều trường.

## 4. Chuyển object có cấu trúc lồng nhau

Response API thường chứa các object lồng nhau. Ví dụ một người dùng có địa chỉ:

```java
public record AddressResponse(String city, String country) {
}

public record UserDetailResponse(
        long id,
        String name,
        AddressResponse address
) {
}
```

JSON response:

```json
{
  "id": 42,
  "name": "Lan",
  "address": {
    "city": "Ho Chi Minh City",
    "country": "Vietnam"
  }
}
```

Chuyển toàn bộ body thành `UserDetailResponse`:

```java
assertThat(mvc.get().uri("/api/users/42/detail"))
        .hasStatusOk()
        .bodyJson()
        .convertTo(UserDetailResponse.class)
        .isEqualTo(new UserDetailResponse(
                42L,
                "Lan",
                new AddressResponse("Ho Chi Minh City", "Vietnam")
        ));
```

JSON mapper đọc object `address` thành `AddressResponse` vì kiểu của component đó được khai báo trong DTO. Cách này kiểm tra cả cấu trúc lồng nhau và giá trị của các trường. Nếu chỉ quan tâm một trường sâu bên trong, JSONPath vẫn là lựa chọn ngắn gọn:

```java
assertThat(mvc.get().uri("/api/users/42/detail"))
        .hasStatusOk()
        .bodyJson()
        .extractingPath("$.address.city")
        .isEqualTo("Ho Chi Minh City");
```

## 5. Chuyển JSON array thành danh sách có kiểu phần tử

Một endpoint có thể trả về một JSON array:

```json
[
  {"id": 1, "name": "Lan", "status": "ACTIVE"},
  {"id": 2, "name": "Minh", "status": "INACTIVE"}
]
```

Nếu chỉ truyền `List.class`, Java không giữ được kiểu phần tử `UserResponse` do type erasure. Kết quả chuyển đổi có thể là một `List` chứa các map thay vì danh sách DTO có kiểu cụ thể.

Để giữ thông tin generic, sử dụng `ParameterizedTypeReference`:

```java
import java.util.List;

import org.springframework.core.ParameterizedTypeReference;

ParameterizedTypeReference<List<UserResponse>> userListType =
        new ParameterizedTypeReference<>() {
        };

@Test
void shouldConvertJsonArrayToTypedList() {
    assertThat(mvc.get().uri("/api/users"))
            .hasStatusOk()
            .bodyJson()
            .convertTo(userListType)
            .satisfies(users -> {
                assertThat(users).hasSize(2);
                assertThat(users.get(0))
                        .isEqualTo(new UserResponse(1L, "Lan", "ACTIVE"));
                assertThat(users.get(1))
                        .isEqualTo(new UserResponse(2L, "Minh", "INACTIVE"));
            });
}
```

`ParameterizedTypeReference<List<UserResponse>>` giữ lại cả kiểu container `List` và kiểu phần tử `UserResponse` thông qua thông tin generic tại thời điểm tạo anonymous subclass. Overload `convertTo(ParameterizedTypeReference<T>)` dùng thông tin này để deserialize array thành `List<UserResponse>`.

Nếu phiên bản Spring Test đang dùng không có overload chuyển đổi nhận `ParameterizedTypeReference`, cần kiểm tra API của đúng phiên bản hoặc dùng một DTO wrapper có field generic được khai báo cụ thể. Không thay bằng `List.class` nếu assertion cần làm việc với từng `UserResponse` có kiểu rõ ràng.

### Khi chỉ cần kiểm tra một phần danh sách

Nếu test không cần thao tác với object Java, JSONPath có thể đơn giản hơn:

```java
assertThat(mvc.get().uri("/api/users"))
        .hasStatusOk()
        .bodyJson()
        .extractingPath("$[0].name")
        .isEqualTo("Lan");
```

Có thể kết hợp JSONPath để xác nhận số phần tử, vị trí hoặc một thuộc tính cụ thể. Dùng typed list conversion khi cần kiểm tra nhiều trường của mỗi phần tử hoặc khi kiểu dữ liệu phần tử là một phần quan trọng của hợp đồng API.

## 6. Chuyển kiểu generic lồng nhau

Các API thường trả về object bao ngoài danh sách dữ liệu, ví dụ:

```json
{
  "page": 0,
  "size": 2,
  "items": [
    {"id": 1, "name": "Lan", "status": "ACTIVE"},
    {"id": 2, "name": "Minh", "status": "INACTIVE"}
  ]
}
```

Có thể mô hình hóa response bằng DTO generic:

```java
public record PageResponse<T>(
        int page,
        int size,
        List<T> items
) {
}
```

Khi chuyển body, cung cấp đầy đủ kiểu generic:

```java
ParameterizedTypeReference<PageResponse<UserResponse>> pageType =
        new ParameterizedTypeReference<>() {
        };

assertThat(mvc.get().uri("/api/users?page=0&size=2"))
        .hasStatusOk()
        .bodyJson()
        .convertTo(pageType)
        .satisfies(page -> {
            assertThat(page.page()).isZero();
            assertThat(page.size()).isEqualTo(2);
            assertThat(page.items()).hasSize(2);
            assertThat(page.items().get(0).name()).isEqualTo("Lan");
        });
```

Điểm quan trọng là kiểu đích phải là `PageResponse<UserResponse>`, không chỉ `PageResponse.class`. Nếu chỉ truyền raw class, mapper không biết kiểu phần tử của `items` và thường giải mã chúng thành map tổng quát.

Có thể áp dụng cùng nguyên tắc với các kiểu generic khác:

```java
ParameterizedTypeReference<Map<String, List<UserResponse>>> responseType =
        new ParameterizedTypeReference<>() {
        };
```

Thông tin kiểu đầy đủ giúp assertion làm việc với `Map<String, List<UserResponse>>` thay vì `Map<String, Object>` có các phần tử lồng nhau chưa được chuyển thành DTO.

## 7. DTO wrapper cho collection

Không phải lúc nào cũng cần `ParameterizedTypeReference`. Nếu API trả về object JSON có field danh sách, có thể khai báo DTO wrapper cụ thể:

```java
public record UserListResponse(List<UserResponse> users, int total) {
}
```

Sau đó chuyển bằng class thông thường:

```java
assertThat(mvc.get().uri("/api/users/summary"))
        .hasStatusOk()
        .bodyJson()
        .convertTo(UserListResponse.class)
        .satisfies(response -> {
            assertThat(response.total()).isEqualTo(2);
            assertThat(response.users()).hasSize(2);
            assertThat(response.users().get(0).name()).isEqualTo("Lan");
        });
```

JSON mapper đọc thông tin generic của component `List<UserResponse>` trong record và chuyển từng phần tử thành `UserResponse`. Wrapper giúp response có cấu trúc rõ ràng và thuận tiện cho client, đồng thời giúp test không phải tạo generic type reference riêng cho một kiểu response cố định.

## 8. Chuyển đổi map, enum và kiểu dữ liệu đặc biệt

JSON object có thể được chuyển thành `Map` nếu cấu trúc động hoặc không có DTO ổn định. Tuy nhiên, nếu schema đã biết, DTO thường giúp kiểm tra hợp đồng rõ hơn.

Ví dụ với map có kiểu giá trị:

```java
ParameterizedTypeReference<Map<String, UserResponse>> mapType =
        new ParameterizedTypeReference<>() {
        };

assertThat(mvc.get().uri("/api/users/by-key"))
        .hasStatusOk()
        .bodyJson()
        .convertTo(mapType)
        .satisfies(users -> {
            assertThat(users).containsKey("primary");
            assertThat(users.get("primary").name()).isEqualTo("Lan");
        });
```

Với enum, DTO có thể khai báo kiểu enum trực tiếp:

```java
public enum UserStatus {
    ACTIVE,
    INACTIVE
}

public record UserResponse(long id, String name, UserStatus status) {
}
```

Nếu JSON chứa chuỗi `"ACTIVE"` và mapper dùng cấu hình enum mặc định, trường `status` có thể được chuyển thành `UserStatus.ACTIVE`. Nếu ứng dụng dùng custom enum deserializer hoặc biểu diễn enum bằng mã khác, test cần dùng đúng mapper configuration để xác nhận hành vi đó.

Với kiểu ngày giờ, số tiền hoặc kiểu tùy chỉnh, hãy khai báo DTO theo kiểu miền phù hợp và bảo đảm JSON mapper đã đăng ký module/serializer cần thiết. Ví dụ, `LocalDate` thường cần Java Time module của Jackson. Test typed conversion sẽ phát hiện trường hợp module thiếu hoặc định dạng ngày không tương thích.

## 9. Kiểm tra body sau request POST

Typed conversion cũng hữu ích với response của POST, PUT hoặc PATCH. Giả sử endpoint tạo người dùng nhận JSON và trả về `UserResponse`:

```java
@PostMapping
@ResponseStatus(HttpStatus.CREATED)
UserResponse create(@RequestBody CreateUserRequest request) {
    return new UserResponse(42L, request.name(), "ACTIVE");
}

record CreateUserRequest(String name) {
}
```

Test gửi JSON body rồi chuyển response:

```java
String requestBody = """
        {"name":"Lan"}
        """;

assertThat(mvc.post().uri("/api/users")
                .contentType(MediaType.APPLICATION_JSON)
                .content(requestBody))
        .hasStatus(201)
        .bodyJson()
        .convertTo(UserResponse.class)
        .isEqualTo(new UserResponse(42L, "Lan", "ACTIVE"));
```

Test này kiểm tra request body được bind, controller xử lý và response được serialize rồi deserialize về đúng DTO. Khi muốn xác nhận chính xác HTTP status, dùng `hasStatus(201)` hoặc matcher status cụ thể được hỗ trợ thay vì chỉ kiểm tra request không thất bại.

## 10. Vai trò của JSON mapper và message converter

Có hai quá trình chuyển đổi khác nhau trong test:

```text
                SERVER SIDE
Controller trả về DTO Java
          |
          v
HttpMessageConverter (Jackson)
          |
          v
HTTP response body (JSON)
          |
          v
MockMvcTester.bodyJson()
          |
          v
JSON mapper dùng cho convertTo(...)
          |
          v
DTO / List<DTO> / kiểu generic Java
          |
          v
AssertJ kiểm tra giá trị
```

`HttpMessageConverter` thuộc Spring MVC và chịu trách nhiệm tạo HTTP response body. `convertTo(...)` thuộc giai đoạn assertion và chịu trách nhiệm deserialize body JSON thành kiểu đích. Hai quá trình có liên quan đến JSON mapper, nhưng không nên mặc định mọi cấu hình tùy chỉnh của ứng dụng đều tự động áp dụng cho bước chuyển đổi trong assertion.

Để kết quả phản ánh đúng hợp đồng ứng dụng:

- Bảo đảm converter tạo response sử dụng cấu hình JSON mong đợi.
- Bảo đảm kiểu đích có constructor, property hoặc record component tương thích với mapper.
- Đăng ký module cần thiết cho `JavaTime`, kiểu tiền tệ hoặc kiểu miền tùy chỉnh.
- Dùng cùng naming strategy và annotation mapping mà client dự kiến nhận.
- Khi cần xác nhận custom serializer/deserializer, hãy cấu hình chúng rõ ràng trong test và kiểm tra output lẫn conversion.

Nếu test dùng `webAppContextSetup`, converter của MVC configuration đã nạp có thể được kiểm tra trực tiếp. Nếu dùng `standaloneSetup`, hãy đăng ký converter cần thiết qua builder. Cấu hình Boot thường cung cấp Jackson converter theo các dependency và property của ứng dụng.

## 11. So sánh typed conversion và JSONPath

Hai cách kiểm tra body JSON có thể dùng bổ sung cho nhau:

| Nhu cầu | Cách phù hợp |
| --- | --- |
| Kiểm tra một trường cụ thể | `bodyJson().extractingPath("$.name")` |
| Kiểm tra object có nhiều trường | `bodyJson().convertTo(UserResponse.class)` |
| Kiểm tra danh sách DTO | `convertTo(ParameterizedTypeReference<List<UserResponse>>)` |
| Kiểm tra wrapper có field danh sách | `convertTo(UserListResponse.class)` |
| Kiểm tra kiểu generic lồng nhau | `convertTo(ParameterizedTypeReference<PageResponse<UserResponse>>)` |
| Kiểm tra cấu trúc động chưa có DTO ổn định | JSONPath hoặc `Map` có generic type phù hợp |

JSONPath thường ngắn gọn khi chỉ một phần body là trọng tâm. Typed conversion phù hợp khi cấu trúc response là hợp đồng có kiểu rõ ràng và nhiều trường cần được xác nhận cùng nhau.

Không cần tạo DTO chỉ để kiểm tra một giá trị đơn giản. Ngược lại, nếu client thực tế deserialize response thành một DTO hoặc generic type, kiểm tra chuyển đổi trong test giúp phát hiện lỗi tương thích sớm hơn.

## 12. Những lỗi thường gặp khi chuyển body thành kiểu dữ liệu

**Dùng `List.class` cho danh sách DTO.**

Java type erasure làm mất kiểu phần tử khi chỉ truyền raw `List.class`. Dùng `ParameterizedTypeReference<List<UserResponse>>` hoặc một wrapper DTO có field `List<UserResponse>`.

**Dùng raw class cho DTO generic.**

`PageResponse.class` không giữ thông tin `T`. Nếu cần `PageResponse<UserResponse>`, hãy cung cấp đầy đủ kiểu generic bằng `ParameterizedTypeReference`.

**DTO không phù hợp với JSON.**

Tên property, kiểu trường, constructor và setter phải tương thích với mapper. Kiểm tra JSON naming strategy, annotation và cấu trúc lồng nhau khi conversion thất bại.

**Thiếu module cho kiểu đặc biệt.**

Các kiểu như `LocalDate`, `LocalDateTime` hoặc kiểu miền tùy chỉnh có thể cần module hoặc serializer/deserializer riêng. Bảo đảm mapper trong test có cấu hình cần thiết.

**Body không phải JSON hoặc rỗng.**

`bodyJson()` và `convertTo(...)` cần body JSON hợp lệ. Với response text, file, XML hoặc `204 No Content`, dùng assertion phù hợp với loại body.

**Chỉ kiểm tra DTO bằng identity.**

Nếu DTO là class thông thường không override `equals()`, hai instance có cùng dữ liệu vẫn có thể không bằng nhau theo `isEqualTo(...)`. Dùng record, triển khai equality theo giá trị hoặc dùng `satisfies(...)` để kiểm tra thuộc tính.

**Quên kiểm tra status trước body.**

Nếu request trả về lỗi HTML hoặc body lỗi khác schema, conversion sang DTO thành công có thể không phải điều cần kiểm tra. Xác nhận status và content type trước, rồi chuyển body theo schema của response tương ứng.

**Cho rằng conversion chứng minh server serialize đúng trong mọi môi trường.**

Conversion chỉ xác nhận body cụ thể trong test có thể được mapper sử dụng để tạo kiểu đích. Nếu mapper test khác cấu hình client hoặc server, kết quả có thể không phản ánh chính xác production. Dùng cấu hình mapper tương ứng khi schema phụ thuộc serializer hoặc module riêng.

## 13. Quy trình kiểm thử body dưới dạng DTO hoặc generic type

Khi cần xác nhận response có thể được client đọc thành kiểu Java, thực hiện theo trình tự:

1. Xác định schema response: object đơn, object lồng nhau, JSON array hay object generic.
2. Khai báo DTO phản ánh schema, ưu tiên record hoặc class có mapping rõ ràng.
3. Với collection hoặc kiểu generic, giữ thông tin tham số kiểu bằng `ParameterizedTypeReference` hoặc dùng wrapper DTO cụ thể.
4. Tạo `MockMvcTester` từ `MockMvc` đã cấu hình cho phạm vi test.
5. Gửi request và xác nhận status HTTP.
6. Gọi `bodyJson().convertTo(...)` để chuyển body thành kiểu đích.
7. Dùng equality hoặc `satisfies(...)` để kiểm tra dữ liệu; dùng JSONPath cho những trường riêng lẻ khi phù hợp.
8. Bảo đảm JSON mapper và message converter tương thích với cấu hình mà hợp đồng API yêu cầu.

Ví dụ cho danh sách generic:

```java
ParameterizedTypeReference<List<UserResponse>> userListType =
        new ParameterizedTypeReference<>() {
        };

assertThat(mvc.get().uri("/api/users"))
        .hasStatusOk()
        .bodyJson()
        .convertTo(userListType)
        .satisfies(users -> {
            assertThat(users).hasSize(2);
            assertThat(users).extracting(UserResponse::status)
                    .containsOnly("ACTIVE", "INACTIVE");
        });
```

## Kết luận

`MockMvcTester.bodyJson().convertTo(...)` giúp kiểm tra body HTTP bằng kiểu dữ liệu Java mà client mong đợi. Với DTO đơn, truyền `Class`; với danh sách hoặc kiểu generic, dùng `ParameterizedTypeReference` để giữ thông tin phần tử và tham số kiểu. DTO wrapper là lựa chọn phù hợp khi API trả object có field collection cố định.

Kết hợp kiểm tra status, typed conversion và assertion trên object giúp xác nhận hợp đồng response ở mức dữ liệu. Hãy dùng JSONPath khi chỉ cần một vài trường, và typed conversion khi khả năng ánh xạ toàn bộ response thành DTO hoặc generic type là điều cần kiểm chứng.
