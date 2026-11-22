# Kiểm tra GET, POST, PUT, PATCH, DELETE cùng status và header

## Mục tiêu

Sau bài này, bạn có thể:

- Viết integration test cho các HTTP method mà Spring Data REST xuất bản.
- Kiểm tra status code, Content-Type, Location và nội dung HAL phù hợp với từng thao tác.
- Phân biệt hành vi của PUT và PATCH.
- Kiểm tra các trường hợp lỗi như 400, 401, 403, 404, 405 và 415.
- Dùng dữ liệu kiểm thử độc lập để xác nhận API thực hiện đúng hợp đồng HTTP.

## 1. Vì sao phải kiểm tra cả status và header?

Một request REST không chỉ trả về JSON. Nó còn có status code và các header mô tả kết quả, kiểu dữ liệu, vị trí tài nguyên hoặc điều kiện xử lý.

Ví dụ:

- `GET /people` có thể trả về `200 OK` cùng representation HAL.
- `POST /people` tạo tài nguyên mới, thường trả về `201 Created` và header `Location`.
- `PUT` hoặc `PATCH` cập nhật tài nguyên; response có thể là `204 No Content` hoặc `200 OK` tùy cấu hình trả body.
- `DELETE` xóa tài nguyên và thường trả về `204 No Content`.

Nếu test chỉ kiểm tra JSON, một API có thể trả đúng dữ liệu nhưng sai status hoặc thiếu header quan trọng mà test vẫn không phát hiện. Ngược lại, chỉ kiểm tra status cũng chưa đủ để biết representation có đúng media type hoặc chứa liên kết HAL cần thiết hay không.

Với Spring Data REST, các repository được xuất bản thành REST resource. Vì vậy, integration test nên gọi endpoint thực tế qua HTTP layer để kiểm tra cả Spring Security, content negotiation, repository exporter và serialization.

## 2. Các status code thường gặp

Bảng dưới đây là hợp đồng HTTP thường dùng cho collection và item resource. Cấu hình ứng dụng, repository exposure và exception handler có thể làm thay đổi một số phản hồi; test cần khớp với hợp đồng đã chọn.

| Thao tác | Request ví dụ | Kết quả thành công thường gặp | Điều cần kiểm tra |
|---|---|---|---|
| Đọc collection | `GET /people` | `200 OK` | HAL Content-Type, `_links`, dữ liệu |
| Đọc item | `GET /people/42` | `200 OK` | HAL Content-Type, nội dung item |
| Tạo mới | `POST /people` | `201 Created` | Header `Location`, representation nếu được cấu hình |
| Thay thế/cập nhật | `PUT /people/42` | `204 No Content` hoặc `200 OK` | Status theo cấu hình, body nếu có |
| Cập nhật một phần | `PATCH /people/42` | `204 No Content` hoặc `200 OK` | Status theo cấu hình, body nếu có |
| Xóa | `DELETE /people/42` | `204 No Content` | Không có response body |

Một số status lỗi thường cần kiểm thử:

| Status | Ý nghĩa | Tình huống ví dụ |
|---|---|---|
| `400 Bad Request` | Request không hợp lệ | JSON sai cấu trúc hoặc dữ liệu không vượt qua validation |
| `401 Unauthorized` | Chưa xác thực | Thiếu hoặc gửi thông tin xác thực không hợp lệ |
| `403 Forbidden` | Đã xác thực nhưng không đủ quyền | Principal thiếu authority cần thiết |
| `404 Not Found` | Không tìm thấy tài nguyên | ID không tồn tại hoặc endpoint không được xuất bản |
| `405 Method Not Allowed` | Endpoint không hỗ trợ method | Gọi `DELETE` khi thao tác xóa đã bị tắt |
| `406 Not Acceptable` | Không có representation phù hợp với `Accept` | Client yêu cầu media type server không cung cấp |
| `415 Unsupported Media Type` | Request body dùng media type không được hỗ trợ | Gửi PATCH với Content-Type không được API chấp nhận |

Đừng mặc định mọi ứng dụng đều trả chính xác các status trên cho mọi lỗi. Ví dụ, exception handler tùy chỉnh có thể ánh xạ lỗi nghiệp vụ sang status khác. Điều quan trọng là xác định hợp đồng API và viết test cố định cho hợp đồng đó.

## 3. Header cần chú ý

### Accept

Header `Accept` cho server biết client muốn nhận representation ở định dạng nào. Spring Data REST thường dùng HAL JSON:

~~~http
Accept: application/hal+json
~~~

Trong MockMvc, có thể dùng `MediaTypes.HAL_JSON` để tránh gõ chuỗi media type nhiều lần.

### Content-Type

Header `Content-Type` mô tả định dạng của request body. Với thao tác tạo hoặc cập nhật JSON thông thường:

~~~http
Content-Type: application/json
~~~

Với JSON Merge Patch, media type thường dùng là:

~~~http
Content-Type: application/merge-patch+json
~~~

Hãy dùng đúng media type mà endpoint của ứng dụng hỗ trợ. Nếu API triển khai JSON Patch hoặc một định dạng khác, test phải gửi đúng Content-Type tương ứng.

### Location

Khi tạo resource thành công, response thường có header `Location` trỏ tới URI của resource mới:

~~~http
HTTP/1.1 201 Created
Location: http://localhost:8080/people/42
~~~

Client có thể dùng URI này để đọc hoặc thao tác tiếp với resource vừa tạo. Test tối thiểu nên xác nhận header tồn tại; nếu cấu trúc URI là một phần của hợp đồng API, hãy kiểm tra cả đường dẫn.

### Content-Type của response

Khi response có representation HAL, kiểm tra media type tương thích với `application/hal+json`. Với response `204 No Content`, không có body nên không nên bắt buộc server phải trả Content-Type của representation.

### Allow và các header có điều kiện

Với `405 Method Not Allowed`, HTTP cho phép server mô tả các method được hỗ trợ bằng header `Allow`. Nếu ứng dụng có công bố header này, hãy kiểm tra các method được phép và không được phép.

Các header như `ETag` và `Last-Modified` chỉ nên được kiểm tra khi ứng dụng thực sự bật hoặc tự triển khai cơ chế tương ứng. Không giả định mọi repository endpoint đều tự động có ETag hay hỗ trợ `If-Match`.

## 4. Chuẩn bị MockMvc integration test

MockMvc gửi request qua Spring MVC trong application context, giúp kiểm tra endpoint mà không cần mở cổng HTTP thật. Với Spring Data REST, dùng integration test để exporter, security filter và cấu hình repository cùng tham gia.

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class PersonRestApiTest {

    @Autowired
    private MockMvc mockMvc;

    // Mỗi test chuẩn bị dữ liệu độc lập, ví dụ một Person có ID 42.
}
~~~

Các import thường dùng:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
~~~

Ví dụ sử dụng endpoint `/people`. Tên endpoint thực tế phụ thuộc vào repository và cấu hình `@RepositoryRestResource`. Nếu ứng dụng yêu cầu authentication, test cần cung cấp principal hoặc token phù hợp; phần ví dụ dưới đây tập trung vào HTTP contract.

## 5. Kiểm tra GET collection và GET item

### GET collection

~~~java
@Test
void getPeopleReturnsHalCollection() throws Exception {
    mockMvc.perform(get("/people")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(content()
            .contentTypeCompatibleWith(MediaTypes.HAL_JSON))
        .andExpect(jsonPath("$._links.self.href").exists());
}
~~~

Các assertion kiểm tra:

- Status là `200 OK`.
- Response có media type tương thích với HAL JSON.
- Representation có liên kết `self`.

Nếu cần xác nhận dữ liệu, có thể thêm assertion vào đường dẫn JSON tương ứng. Với collection HAL, phần tử thường nằm trong `_embedded`; tên khóa phụ thuộc vào relation được xuất bản cho repository. Không nên hard-code `_embedded.people` nếu relation của ứng dụng có tên khác.

### GET item

~~~java
@Test
void getPersonReturnsHalResource() throws Exception {
    long existingId = 42L; // Fixture được tạo trước test.

    mockMvc.perform(get("/people/{id}", existingId)
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(content()
            .contentTypeCompatibleWith(MediaTypes.HAL_JSON))
        .andExpect(jsonPath("$._links.self.href").exists());
}
~~~

Nếu item không tồn tại, kiểm tra response theo hợp đồng lỗi của ứng dụng, thường là `404 Not Found`:

~~~java
mockMvc.perform(get("/people/{id}", 999999L)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isNotFound());
~~~

## 6. Kiểm tra POST tạo resource

POST trên collection endpoint thường tạo một resource mới. Request gửi JSON qua `Content-Type`, đồng thời khai báo định dạng response mong muốn qua `Accept`.

~~~java
@Test
void postPeopleCreatesResourceAndReturnsLocation() throws Exception {
    String requestBody = """
        {
            "name": "Ada Lovelace"
        }
        """;

    MvcResult result = mockMvc.perform(post("/people")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaTypes.HAL_JSON)
            .content(requestBody))
        .andExpect(status().isCreated())
        .andExpect(header().exists(HttpHeaders.LOCATION))
        .andReturn();

    String location = result.getResponse()
        .getHeader(HttpHeaders.LOCATION);

    assertThat(location).isNotBlank();
}
~~~

Điểm quan trọng là:

- `201 Created` xác nhận thao tác tạo resource thành công.
- `Location` cho biết URI của resource mới.
- Nếu cấu hình trả representation sau khi tạo, có thể kiểm tra thêm Content-Type và body. Nếu cấu hình không trả body, đừng bắt buộc response phải có HAL representation.

Nếu muốn kiểm tra URI cụ thể, hãy phân tích `Location` bằng `URI` hoặc assertion trên path thay vì phụ thuộc vào host, port ngẫu nhiên hay địa chỉ tuyệt đối của môi trường test.

## 7. Kiểm tra PUT cập nhật toàn bộ resource

PUT thường được dùng để thay thế hoặc cập nhật representation của resource tại URI đã có. Body cần tuân theo các trường mà resource cho phép ghi.

~~~java
@Test
void putPersonUpdatesResource() throws Exception {
    long existingId = 42L; // Fixture được tạo trước test.

    String requestBody = """
        {
            "name": "Ada Byron"
        }
        """;

    mockMvc.perform(put("/people/{id}", existingId)
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaTypes.HAL_JSON)
            .content(requestBody))
        .andExpect(status().isNoContent());
}
~~~

Trong cấu hình Spring Data REST mặc định thường gặp, `returnBodyOnUpdate` là false, vì vậy PUT/PATCH thành công trả `204 No Content`. Nếu ứng dụng bật trả body sau cập nhật bằng `RepositoryRestConfiguration.setReturnBodyOnUpdate(true)`, hãy điều chỉnh test để mong đợi `200 OK` và kiểm tra representation HAL.

Ví dụ khi bật trả body:

~~~java
mockMvc.perform(put("/people/{id}", existingId)
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaTypes.HAL_JSON)
        .content(requestBody))
    .andExpect(status().isOk())
    .andExpect(content()
        .contentTypeCompatibleWith(MediaTypes.HAL_JSON));
~~~

Không nên viết test vừa chấp nhận `200` vừa chấp nhận `204` chỉ để test luôn xanh. Hãy chọn một cấu hình response rõ ràng và assert đúng hợp đồng mà ứng dụng đang công bố.

## 8. Kiểm tra PATCH cập nhật một phần

PATCH dùng để thay đổi một phần resource. JSON Merge Patch là một định dạng thường gặp; trong trường hợp đó request dùng `application/merge-patch+json`.

~~~java
@Test
void patchPersonUpdatesSelectedFields() throws Exception {
    long existingId = 42L; // Fixture được tạo trước test.

    String patchBody = """
        {
            "name": "Ada King"
        }
        """;

    MediaType mergePatch = MediaType.valueOf(
        "application/merge-patch+json"
    );

    mockMvc.perform(patch("/people/{id}", existingId)
            .contentType(mergePatch)
            .accept(MediaTypes.HAL_JSON)
            .content(patchBody))
        .andExpect(status().isNoContent());
}
~~~

Nếu ứng dụng bật `returnBodyOnUpdate`, status có thể là `200 OK` và response chứa representation. Nếu API dùng JSON Patch thay vì JSON Merge Patch, body và Content-Type sẽ khác. Test phải khớp với định dạng PATCH thực tế, không chỉ đổi HTTP method từ PUT sang PATCH mà giữ nguyên mọi thứ.

Nên kiểm tra dữ liệu sau cập nhật để chắc chắn PATCH chỉ thay đổi trường được gửi và giữ nguyên các trường khác. Ví dụ, nếu request chỉ thay `name`, test cần xác nhận `email` hoặc trường không có trong patch vẫn giữ giá trị cũ theo semantics mà ứng dụng lựa chọn.

## 9. Kiểm tra DELETE xóa resource

DELETE trên item endpoint thường trả `204 No Content`. Vì không có representation trong response, assertion nên tập trung vào status và việc resource không còn truy cập được.

~~~java
@Test
void deletePersonRemovesResource() throws Exception {
    long existingId = 42L; // Fixture được tạo trước test.

    mockMvc.perform(delete("/people/{id}", existingId))
        .andExpect(status().isNoContent())
        .andExpect(content().string(""));

    mockMvc.perform(get("/people/{id}", existingId)
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isNotFound());
}
~~~

Test này xác nhận cả hai điều:

1. DELETE trả status thành công theo hợp đồng.
2. GET sau đó không còn tìm thấy resource.

Nếu ứng dụng dùng soft delete, hoặc endpoint có semantics lưu trữ thay vì xóa vật lý, hãy kiểm tra trạng thái nghiệp vụ tương ứng. Không nên giả định mọi thao tác DELETE đều xóa vĩnh viễn hàng dữ liệu khỏi database.

## 10. Kiểm tra lỗi và quyền truy cập

Các trường hợp lỗi giúp phát hiện API vô tình cho phép thao tác sai hoặc trả phản hồi không nhất quán.

### Dữ liệu không hợp lệ

~~~java
mockMvc.perform(post("/people")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaTypes.HAL_JSON)
        .content("{ invalid json"))
    .andExpect(status().isBadRequest());
~~~

Có thể bổ sung test validation, ví dụ trường bắt buộc bị thiếu hoặc giá trị không hợp lệ. Status và cấu trúc lỗi nên theo exception handling của ứng dụng.

### Chưa xác thực và thiếu quyền

Nếu API được bảo vệ bằng Spring Security, kiểm tra riêng:

- Không có thông tin xác thực: thường là `401 Unauthorized`.
- Đã xác thực nhưng thiếu authority: thường là `403 Forbidden`.

Với MockMvc, có thể dùng các request post-processor của Spring Security để tạo principal có quyền khác nhau. Ví dụ:

~~~java
mockMvc.perform(delete("/people/{id}", 42L)
        .with(user("reader").authorities(
            new SimpleGrantedAuthority("people:read")
        )))
    .andExpect(status().isForbidden());
~~~

Để đoạn test hoạt động, project cần dependency test support của Spring Security và cấu hình security tương ứng. Nếu ứng dụng dùng JWT hoặc OAuth2 Resource Server, hãy dùng test support phù hợp với loại authentication đang triển khai.

### Method không được hỗ trợ

Nếu repository không xuất bản một method hoặc ứng dụng chặn method đó, test có thể xác nhận `405 Method Not Allowed`:

~~~java
mockMvc.perform(delete("/people")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isMethodNotAllowed());
~~~

Nếu response có header `Allow`, kiểm tra danh sách method được công bố. Một số endpoint có thể trả lỗi khác theo cấu hình; hãy căn cứ vào response contract thực tế.

### Media type không được hỗ trợ

Gửi Content-Type không được endpoint chấp nhận có thể dẫn đến `415 Unsupported Media Type`. Trường hợp này hữu ích để xác nhận API từ chối định dạng request không hợp lệ thay vì xử lý sai payload.

## 11. Tổ chức dữ liệu và assertion trong test

Một integration test đáng tin cậy cần dữ liệu đầu vào xác định và không phụ thuộc thứ tự chạy:

1. Tạo fixture cho mỗi test hoặc dùng dữ liệu test có ID được kiểm soát.
2. Không dùng chung một bản ghi nếu một test đã cập nhật hoặc xóa bản ghi đó.
3. Dọn dữ liệu sau test, hoặc dùng transaction/fixture strategy phù hợp với cách request được thực thi trong test context.
4. Assert status trước, sau đó kiểm tra các header và body liên quan.
5. Khi kiểm tra collection, tránh phụ thuộc vào thứ tự phần tử nếu API không cam kết sort mặc định.
6. Kiểm tra Content-Type tương thích thay vì so sánh chuỗi header quá cứng khi tham số charset có thể khác nhau.

Với các request tạo/cập nhật, nên xác nhận dữ liệu đã được lưu bằng repository hoặc một GET tiếp theo. Điều đó giúp phân biệt response thành công với thao tác thực sự thay đổi trạng thái.

Nếu test cần authentication, hãy tạo principal theo từng vai trò: reader, creator, editor và administrator. Mỗi role nên có cả test thành công lẫn test bị từ chối để xác nhận chính sách không cấp nhầm quyền.

## 12. Ma trận kiểm thử tối thiểu

| HTTP method | Ca thành công | Status cần kiểm tra | Header/body chính |
|---|---|---|---|
| GET | Đọc collection/item | 200 | Accept, Content-Type, HAL links |
| POST | Tạo resource | 201 | Content-Type request, Location |
| PUT | Cập nhật resource | 204 hoặc 200 theo cấu hình | Content-Type request; body nếu bật |
| PATCH | Cập nhật một phần | 204 hoặc 200 theo cấu hình | Patch Content-Type; body nếu bật |
| DELETE | Xóa resource | 204 | Response không có body |

Ngoài ca thành công, thêm các ca sai dữ liệu, chưa xác thực, thiếu quyền, resource không tồn tại, method không được hỗ trợ và media type không hợp lệ. Với mỗi ca, hãy ghi rõ request nào được gửi và status/header nào là kết quả mong đợi.

## 13. Bài tập tự kiểm tra

Một repository `PersonRepository` được xuất bản tại `/people`. Ứng dụng dùng HAL JSON và không bật trả body sau cập nhật.

1. GET collection thành công nên trả status nào và Content-Type nào?
2. POST tạo mới thành công nên có header nào để client biết URI resource vừa tạo?
3. Với cấu hình không trả body sau cập nhật, PUT và PATCH thành công thường trả status nào?
4. DELETE thành công thường có body hay không?
5. Người dùng đã đăng nhập nhưng thiếu authority để xóa resource thường nhận status nào?
6. Client gửi Content-Type không được endpoint hỗ trợ có thể nhận status nào?
7. Vì sao test PATCH cần kiểm tra cả dữ liệu sau cập nhật chứ không chỉ status?

**Đáp án:**

1. `200 OK` và Content-Type tương thích `application/hal+json`.
2. `Location`.
3. `204 No Content`.
4. Không có body, thường là `204 No Content`.
5. `403 Forbidden`.
6. `415 Unsupported Media Type`.
7. Vì status chỉ xác nhận request được xử lý; cần xác nhận đúng trường được cập nhật và các trường khác được giữ nguyên theo semantics PATCH.

## Ghi nhớ

- GET thường trả `200 OK` và representation HAL.
- POST tạo resource thường trả `201 Created` cùng `Location`.
- PUT/PATCH có thể trả `204` hoặc `200` tùy cấu hình trả body sau cập nhật.
- DELETE thường trả `204 No Content`.
- Kiểm tra `Accept`, `Content-Type`, `Location` và các header có điều kiện theo hợp đồng API.
- Dùng integration test để xác nhận status, header, representation và trạng thái dữ liệu sau thao tác.

Tham khảo:

- [Spring Data REST — Reference Documentation](https://docs.spring.io/spring-data/rest/reference/)
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)
- [Spring Security — Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html)
