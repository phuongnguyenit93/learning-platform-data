# Nhóm kiểm tra và khác biệt giữa tạo mới với cập nhật

Trong một REST API Spring Boot, thao tác **tạo mới** và **cập nhật** thường dùng các quy tắc kiểm tra dữ liệu khác nhau. Khi tạo một sản phẩm, tên và giá có thể bắt buộc. Khi cập nhật từng trường, client có thể chỉ gửi giá; trường tên vắng mặt là bình thường, nhưng nếu client đã gửi tên thì tên đó không được rỗng hoặc chỉ toàn khoảng trắng. **Bean Validation groups** cho phép áp dụng tập ràng buộc khác nhau trên cùng một kiểu dữ liệu bằng cách chọn nhóm khi kiểm tra.

Bài này thuộc chủ đề **Kiểm tra dữ liệu**, tập trung vào **Spring Boot 3.x, Spring MVC, Jakarta Bean Validation và Java 17+**. Chúng ta sẽ phân biệt nhóm mặc định với nhóm tùy chỉnh; minh họa `@Validated` cho HTTP POST/PATCH; kiểm tra trường bắt buộc và tùy chọn; bàn về PUT, nested validation, thứ tự nhóm, xử lý lỗi 400, và khi nào nên dùng DTO riêng thay vì validation groups.

## 1. Vấn đề: cùng một field nhưng quy tắc thay đổi theo thao tác

Giả sử API quản lý sách có hai thao tác:

- `POST /api/books`: tạo sách mới. Client phải gửi `title` không rỗng và `priceCents` không âm.
- `PATCH /api/books/{id}`: cập nhật một phần. Client có thể chỉ gửi `title` hoặc chỉ gửi `priceCents`. Field không xuất hiện mang ý nghĩa **giữ nguyên** trong hợp đồng demo. Nhưng field có mặt vẫn phải hợp lệ.

Ví dụ:

~~~json
{
  "title": "Spring in Action",
  "priceCents": 2500
}
~~~

Đây là body tạo mới hợp lệ.

~~~json
{
  "priceCents": 1999
}
~~~

Đây là body PATCH hợp lệ theo hợp đồng cập nhật từng phần; `title` có thể vắng mặt.

~~~json
{
  "title": "   "
}
~~~

Đây là PATCH không hợp lệ: mặc dù field `title` là tùy chọn, một khi client cung cấp tên thì không thể chỉ gồm khoảng trắng.

Nếu dùng `@NotBlank` cho `title` và `@NotNull` cho `priceCents` trong mọi ngữ cảnh, một request PATCH chỉ chứa giá sẽ bị từ chối vì thiếu title. Nếu bỏ hai ràng buộc này hoàn toàn, request POST thiếu dữ liệu có thể lọt qua. Nhóm kiểm tra giúp chọn **constraint nào chạy cho thao tác nào**, không phải thay đổi kiểu Java hoặc tự động biến POST thành PATCH.

## 2. Bean Validation hoạt động ra sao trong Spring Boot?

Jakarta Bean Validation (Jakarta Validation) định nghĩa các annotation ràng buộc và hợp đồng `Validator`; Hibernate Validator thường cung cấp implementation khi thêm starter validation.

Dependencies Gradle trong một project Spring Boot 3.x:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đây là phần `dependencies` của một dự án có plugin Spring Boot, Java toolchain và Gradle wrapper; không phải toàn bộ file `build.gradle`.

Các annotation thường dùng trong Boot 3.x nằm ở namespace `jakarta.validation.*`, chẳng hạn:

- `@NotNull`: giá trị không được null.
- `@NotBlank`: với `CharSequence`, không được null/rỗng/chỉ có khoảng trắng.
- `@NotEmpty`: không được null hoặc rỗng cho kiểu hỗ trợ, nhưng không có cùng semantics whitespace như `@NotBlank`.
- `@Size(min=..., max=...)`: giới hạn kích thước chuỗi/collection/array/map; **null vẫn hợp lệ** nếu chỉ dùng `@Size`.
- `@Positive`, `@PositiveOrZero`, `@Min`, `@Max`: giới hạn miền giá trị số, thường **null hợp lệ** nếu không có `@NotNull`.
- `@Pattern`: kiểm tra regex đối với `CharSequence`; null được coi là hợp lệ.
- `@Email`: kiểm tra format email theo validator; nếu email bắt buộc, thường phải kết hợp `@NotBlank`.
- `@Valid`: kích hoạt validation/cascaded validation trong ngữ cảnh được hỗ trợ; không tự định nghĩa constraint.

Spring còn cung cấp `org.springframework.validation.annotation.Validated`. Annotation này có thể nhận **validation group hints**, vì thế rất hữu ích với `@RequestBody`, `@ModelAttribute` và các ngữ cảnh Spring tương ứng.

**Điều kiện quan trọng:** Bean Validation chỉ hoạt động như mong đợi nếu có implementation và pipeline validation được cấu hình. Spring Boot 3.x không nên bị giả định rằng cứ có starter web là mọi annotation validation đã hoạt động; thêm `spring-boot-starter-validation` để có cơ chế Jakarta Bean Validation phù hợp.

## 3. Validation group thực chất là gì?

Một group là một **kiểu marker**, thường là interface không có method:

~~~java
interface OnCreate {}
interface OnUpdate {}
~~~

Những interface này **không có phép kiểm tra riêng**, không chứa logic và không biết HTTP method. Chúng chỉ làm nhãn để constraint khai báo:

~~~java
@NotNull(groups = OnCreate.class)
String requiredOnlyWhenCreating;
~~~

Khi validator được yêu cầu chạy nhóm `OnCreate`, constraint thuộc nhóm đó được xét. Khi chỉ chạy nhóm `OnUpdate`, constraint chỉ thuộc nhóm `OnCreate` sẽ không được xét, trừ khi có quan hệ nhóm hoặc quy tắc sequence được khai báo tương ứng.

Một constraint có thể thuộc nhiều nhóm:

~~~java
@Size(max = 120, groups = {OnCreate.class, OnUpdate.class})
String title;
~~~

Như vậy giới hạn độ dài tiêu đề được áp dụng cho cả hai thao tác.

Các nhóm nên được đặt tên theo **ngữ cảnh kiểm tra** hoặc **use case**, ví dụ `OnCreate`, `OnUpdate`, `OnPublish`, `OnSubmit`. Không nên tạo quá nhiều nhóm chỉ để né thiết kế DTO khi các request đã khác nhau đáng kể.

## 4. Default group là bẫy phổ biến nhất

Nếu không chỉ định `groups` trong một constraint:

~~~java
@NotBlank
String title;
~~~

thì constraint mặc định thuộc `jakarta.validation.groups.Default`.

Cách kiểm tra thường gặp:

~~~java
@Valid @RequestBody BookRequest request
~~~

sẽ yêu cầu validation theo nhóm mặc định (`Default`) khi dùng trong luồng request body tiêu chuẩn. Nhưng:

~~~java
@Validated(OnCreate.class) @RequestBody BookRequest request
~~~

yêu cầu kiểm tra nhóm `OnCreate`. **Không được suy luận các constraint thuộc Default luôn tự động được chạy cùng OnCreate.**

Bảng:

| Constraint khai báo | Chạy `Default` | Chạy `OnCreate` | Chạy `OnUpdate` |
|---|---:|---:|---:|
| `@NotBlank String name` | Có | Không mặc định | Không mặc định |
| `@NotNull(groups=OnCreate.class)` | Không | Có | Không |
| `@PositiveOrZero(groups={OnCreate.class,OnUpdate.class})` | Không | Có | Có |
| `@Size(groups=OnUpdate.class)` | Không | Không | Có |

Có ba cách giữ các ràng buộc chung:
1. Ghi rõ `groups = {OnCreate.class, OnUpdate.class}` cho constraint áp dụng cả hai.
2. Tạo nhóm `Common` và yêu cầu validate `@Validated({Common.class, OnCreate.class})` hoặc `@Validated({Common.class, OnUpdate.class})`.
3. Có chủ đích đưa `Default` vào lời gọi, ví dụ `@Validated({Default.class, OnCreate.class})`.

Cách 2 và 3 không cam kết **thứ tự** chạy các group. Nếu cần thứ tự, dùng `@GroupSequence` (phần sau). Đừng cấu hình nhóm bằng một tên interface rồi nghĩ framework tự biết các nhóm liên quan.

## 5. Cùng DTO, quy tắc riêng cho tạo mới và cập nhật từng phần

Với ví dụ cập nhật một phần, ta thiết kế:

~~~java
interface OnCreate {}
interface OnUpdate {}

record BookInput(
    @NotBlank(groups = OnCreate.class)
    @Pattern(regexp = "(?s).*\\S.*", groups = OnUpdate.class)
    @Size(max = 120, groups = {OnCreate.class, OnUpdate.class})
    String title,

    @NotNull(groups = OnCreate.class)
    @PositiveOrZero(groups = {OnCreate.class, OnUpdate.class})
    Integer priceCents
) {}
~~~

Giải thích từng field:

| Field | Khi POST / OnCreate | Khi PATCH / OnUpdate |
|---|---|---|
| `title` | `@NotBlank` bắt buộc có text có nghĩa | `@Pattern` cho phép null nhưng nếu có giá trị thì phải chứa ít nhất một ký tự không trắng |
| `title` max 120 | Áp dụng | Áp dụng |
| `priceCents` | `@NotNull` bắt buộc gửi | Có thể null/vắng mặt |
| `priceCents` không âm | Áp dụng khi có số | Áp dụng khi có số |

Regex `(?s).*\\S.*` tìm ít nhất một ký tự không thuộc nhóm whitespace, có bật dot-all. Đây là một cách minh họa quy tắc “nếu field được cung cấp thì không được chỉ chứa whitespace”. Trong ứng dụng thật cần xác định chính sách chuẩn hóa Unicode/trim và có thể thay bằng custom constraint `OptionalNotBlank` nếu yêu cầu phức tạp.

**Vì sao dùng `Integer` thay vì `int` cho body?** Vì `int` có giá trị mặc định 0 trong nhiều cơ chế tạo đối tượng, khó biểu diễn “không cung cấp”; `Integer` cho phép null. Với PATCH, null trong DTO này có nghĩa **không cập nhật trường** theo quy ước ví dụ.

**Giới hạn quan trọng của ví dụ:** khi Jackson map JSON vào record nullable, trường **vắng mặt** và trường được gửi **`null` tường minh** đều có thể thành Java null. Do đó DTO này *không phân biệt được* “không thay đổi” với “cố tình xóa giá trị”. Nếu API cần hỗ trợ việc xóa trường qua null, phải dùng thiết kế nhận biết trường có mặt như JSON Merge Patch/JSON Patch, JsonNode hoặc một kiểu wrapper theo contract, không chỉ đổi validation group.

## 6. @Validated chọn nhóm ở từng endpoint

Annotation `@Valid` thuộc Jakarta Validation nhưng **không có tham số groups**. Spring `@Validated` mới cho phép chọn group ở vị trí method parameter:

~~~java
@PostMapping("/api/books")
ResponseEntity<BookView> create(
        @Validated(OnCreate.class) @RequestBody BookInput request) {
    // ...
}

@PatchMapping("/api/books/{id}")
ResponseEntity<BookView> patch(
        @PathVariable long id,
        @Validated(OnUpdate.class) @RequestBody BookInput request) {
    // ...
}
~~~

Đây là **đoạn minh họa**; toàn bộ controller chạy được nằm ở phần sau.

Điểm chính: `@Validated(OnCreate.class)` áp dụng cho body của POST; `@Validated(OnUpdate.class)` áp dụng cho body của PATCH. Spring MVC dùng message converter để deserialize JSON, rồi thực hiện validation trên DTO bằng các group được chọn.

Không thêm `@Validated` ở cấp controller class chỉ để kiểm tra body theo group: trong Spring Framework 6.1+, class-level `@Validated` có thể kích hoạt phương pháp **AOP method validation** khác với built-in Spring MVC method validation. Hãy để annotation ngay trên tham số cần xác thực và phân biệt lỗi validation ở hai cơ chế.

Nếu đặt cả `@Valid` và `@Validated(OnCreate.class)` vào cùng một body mà không có lý do, ý định chọn group trở nên khó hiểu. Dùng annotation thích hợp nhất, rồi test rõ ràng.

## 7. Tạo mới, PUT và PATCH không nên được gom một cách máy móc

| Thao tác | Contract thường dùng | Ý nghĩa validation |
|---|---|---|
| **POST create** | Tạo mới resource, server cấp ID | Những field bắt buộc phải có; ID/owner/status nội bộ không nên cho client tự quyết |
| **PUT replace** | Thay thế representation của resource xác định bởi URI | Thường yêu cầu đầy đủ field bắt buộc của representation mới; nên dùng `OnReplace` hoặc DTO riêng |
| **PATCH partial update** | Chỉ cập nhật những field được nêu | Các field có thể vắng mặt, nhưng nếu được gửi thì vẫn phải hợp lệ; áp dụng `OnUpdate` trong demo |

`OnUpdate` **không có nghĩa “mọi update đều cho phép thiếu field”**. Đó chỉ là tên group mà **ứng dụng tự đặt**. Đối với PUT thay thế hoàn toàn, việc cho phép thiếu mọi field có thể gây xóa dữ liệu ngoài ý muốn. Hãy dựa trên semantics API, không dựa vào tên group.

POST thường trả HTTP `201 Created` kèm `Location`; PATCH thành công có thể trả `200 OK` với body mới hoặc `204 No Content` không body. Không tìm thấy ID khi cập nhật thường là `404 Not Found`. Xung đột phiên bản/dữ liệu có thể là `409 Conflict` hoặc `412 Precondition Failed` tùy chính sách `ETag`/`If-Match`.

Validation group chỉ kiểm tra constraints trên dữ liệu, **không tự quyết định HTTP status hoặc transaction semantics**.

## 8. Ví dụ Spring Boot hoàn chỉnh: POST tạo mới, PATCH cập nhật từng phần

Dùng Java 17+, Spring Boot 3.3.x, `spring-boot-starter-web` và `spring-boot-starter-validation`. Dữ liệu được lưu bằng `ConcurrentHashMap` chỉ để demo, không có persistence lâu dài.

Tạo file `src/main/java/com/example/demo/BookGroupApplication.java`:

~~~java
package com.example.demo;

import java.net.URI;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.PositiveOrZero;
import jakarta.validation.constraints.Size;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class BookGroupApplication {
    public static void main(String[] args) {
        SpringApplication.run(BookGroupApplication.class, args);
    }
}

interface OnCreate {}
interface OnUpdate {}

record BookInput(
    @NotBlank(groups = OnCreate.class)
    @Pattern(regexp = "(?s).*\\S.*", groups = OnUpdate.class)
    @Size(max = 120, groups = {OnCreate.class, OnUpdate.class})
    String title,

    @NotNull(groups = OnCreate.class)
    @PositiveOrZero(groups = {OnCreate.class, OnUpdate.class})
    Integer priceCents
) {}

record BookView(long id, String title, int priceCents) {}

@Service
class BookService {
    private final AtomicLong nextId = new AtomicLong();
    private final ConcurrentMap<Long, BookView> books =
        new ConcurrentHashMap<>();

    BookView create(BookInput input) {
        long id = nextId.incrementAndGet();
        BookView created =
            new BookView(id, input.title().trim(), input.priceCents());
        books.put(id, created);
        return created;
    }

    Optional<BookView> find(long id) {
        return Optional.ofNullable(books.get(id));
    }

    Optional<BookView> patch(long id, BookInput input) {
        BookView result = books.computeIfPresent(id, (key, old) ->
            new BookView(
                old.id(),
                input.title() == null
                    ? old.title() : input.title().trim(),
                input.priceCents() == null
                    ? old.priceCents() : input.priceCents()
            ));
        return Optional.ofNullable(result);
    }
}

@RestController
@RequestMapping("/api/books")
class BookController {
    private final BookService service;

    BookController(BookService service) {
        this.service = service;
    }

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<BookView> create(
            @Validated(OnCreate.class) @RequestBody BookInput input) {
        BookView created = service.create(input);
        return ResponseEntity
            .created(URI.create("/api/books/" + created.id()))
            .body(created);
    }

    @GetMapping(path = "/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<BookView> find(@PathVariable long id) {
        return service.find(id)
            .map(ResponseEntity::ok)
            .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PatchMapping(
        path = "/{id}",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<BookView> patch(
            @PathVariable long id,
            @Validated(OnUpdate.class) @RequestBody BookInput input) {
        return service.patch(id, input)
            .map(ResponseEntity::ok)
            .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
~~~

Điểm thiết kế:
- Mã ID thuộc server, nằm trong đường dẫn để cập nhật và trong response, không nằm trong request DTO.
- `BookInput` dùng chung shape nhưng chọn constraint bằng group ở từng endpoint.
- `BookService` nhận dữ liệu đã qua HTTP validation và áp dụng chính sách cập nhật. Demo dùng map atomic update trong một JVM; production cần database/transaction và điều kiện cạnh tranh phù hợp.
- Trong PATCH, field null được hiểu là không thay đổi. Gửi `{}` sẽ không thay đổi gì; nếu API không cho phép no-op, service/controller cần quy tắc từ chối riêng.
- Service không được “tin tuyệt đối” controller nếu có entry point khác. Những business invariant quan trọng vẫn phải được kiểm tra ở domain/service và persistence.
- `priceCents` là số nguyên để tránh tranh cãi biểu diễn số thập phân; production vẫn cần quy định tiền tệ, giới hạn giá và chính sách làm tròn.

### 8.1. Chạy ứng dụng

Trong project Gradle có wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

### 8.2. Tạo mới hợp lệ

~~~bash
curl -i -X POST http://localhost:8080/api/books \
  -H "Content-Type: application/json" \
  -d '{"title":"Spring in Action","priceCents":2500}'
~~~

Với ứng dụng mới chạy và request tạo sách đầu tiên:

~~~http
HTTP/1.1 201
Location: /api/books/1
Content-Type: application/json

{"id":1,"title":"Spring in Action","priceCents":2500}
~~~

Đây là các header/body quan trọng; server có thể thêm những header khác. ID có thể khác nếu request tạo mới đã xảy ra trước.

### 8.3. POST thiếu field bị từ chối

~~~bash
curl -i -X POST http://localhost:8080/api/books \
  -H "Content-Type: application/json" \
  -d '{"title":"Spring in Action"}'
~~~

Kỳ vọng **400 Bad Request** vì `priceCents` bắt buộc trong group `OnCreate`. Body lỗi mặc định phụ thuộc cấu hình Boot, Problem Details và exception handler hiện có.

POST với `"title":"   "` cũng phải bị từ chối vì `@NotBlank(groups=OnCreate.class)`.

### 8.4. PATCH chỉ gửi giá vẫn hợp lệ

Sau khi đã tạo resource ID 1:

~~~bash
curl -i -X PATCH http://localhost:8080/api/books/1 \
  -H "Content-Type: application/json" \
  -d '{"priceCents":1999}'
~~~

Kỳ vọng status **200 OK**, body:

~~~json
{"id":1,"title":"Spring in Action","priceCents":1999}
~~~

Tên cũ vẫn giữ nguyên vì `title` không được gửi.

### 8.5. PATCH gửi trường sai bị từ chối

~~~bash
curl -i -X PATCH http://localhost:8080/api/books/1 \
  -H "Content-Type: application/json" \
  -d '{"title":"   "}'
~~~

Kỳ vọng **400 Bad Request** bởi `@Pattern(groups=OnUpdate.class)`. Tương tự `{"priceCents":-10}` bị từ chối do `@PositiveOrZero` thuộc cả hai nhóm.

**Kết quả tùy thuộc đúng group được chọn.** Nếu vô tình đổi `@Validated(OnUpdate.class)` thành `@Valid`, những constraint chỉ thuộc `OnUpdate` sẽ không mặc nhiên chạy.

## 9. Kiểm thử MockMvc: chứng minh tạo mới và cập nhật khác nhau

Tạo file `src/test/java/com/example/demo/BookGroupApplicationTest.java` trong cùng package:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BookGroupApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void createRequiresPriceAndTitle() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Book\"}"))
            .andExpect(status().isBadRequest());

        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"   \",\"priceCents\":10}"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void updateCanChangeOnlyPriceButCannotUseNegativeValue()
            throws Exception {

        String location = mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Java\",\"priceCents\":1000}"))
            .andExpect(status().isCreated())
            .andExpect(header().exists("Location"))
            .andReturn().getResponse().getHeader("Location");

        mvc.perform(patch(location)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"priceCents\":800}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("Java"))
            .andExpect(jsonPath("$.priceCents").value(800));

        mvc.perform(patch(location)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"priceCents\":-1}"))
            .andExpect(status().isBadRequest());

        mvc.perform(patch(location)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"   \"}"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void unknownIdReturnsNotFound() throws Exception {
        mvc.perform(get("/api/books/999999"))
            .andExpect(status().isNotFound());
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Test dùng `@SpringBootTest` với `@AutoConfigureMockMvc` để thực thi cả JSON deserialization, validation group selection, routing và response status mà không phải mở socket HTTP thật. `location` được lấy từ kết quả POST thay vì giả định ID cố định; nhờ vậy test ít phụ thuộc trạng thái của những test khác.

Nếu ứng dụng sử dụng Spring Security, cần cấu hình security test hoặc xác thực trong các request tương ứng. Ví dụ này không thêm security starter, chỉ tập trung vào validation groups.

## 10. Kiểm tra group trực tiếp qua Jakarta Validator

Nếu không cần HTTP, Bean Validation hỗ trợ API:

~~~java
Set<ConstraintViolation<BookInput>> errors =
    validator.validate(input, OnCreate.class);
~~~

`validator` là một instance `jakarta.validation.Validator`, `input` là DTO của ứng dụng. Khi không truyền group, `validator.validate(input)` kiểm tra nhóm `Default`. Có thể truyền nhiều nhóm, ví dụ `validator.validate(input, Default.class, OnUpdate.class)`.

Ví dụ trong `BookInput` phía trên, **mọi constraint đều khai báo group cụ thể**, nên kiểm tra chỉ với `Default` sẽ không phát hiện các điều kiện của `OnCreate`/`OnUpdate`. Điều này minh họa lý do phải kiểm tra đúng group được chọn, không có nghĩa bỏ Default ở mọi dự án là hướng thiết kế bắt buộc.

Khi test group trực tiếp, chỉ assert tập field/constraint thất bại, không nên phụ thuộc **thứ tự** các violation được trả về. Jakarta Bean Validation không hứa một thứ tự tổng quát cho những constraint trong cùng group.

## 11. Group chung, kế thừa và @GroupSequence

### 11.1. Nhóm chung

Nếu nhiều thao tác dùng cùng một ràng buộc, bạn có thể:
- Gán constraint vào cả `OnCreate` và `OnUpdate`.
- Hoặc tạo `interface CommonChecks {}` rồi yêu cầu `@Validated({CommonChecks.class, OnCreate.class})`.

Lưu ý: chỉ truyền `OnCreate.class` thì **không tự động chạy CommonChecks** trừ khi quan hệ kế thừa/sequence được khai báo hoặc danh sách group được cung cấp.

Group inheritance là một tính năng của Bean Validation: nếu `OnCreate` kế thừa một interface group khác, kiểm tra `OnCreate` có thể bao gồm constraint thuộc group cha. Tuy vậy, một sơ đồ inheritance phức tạp khó đọc hơn khai báo group tường minh; chỉ nên dùng khi thực sự có cấu trúc reuse rõ.

### 11.2. Kiểm tra theo thứ tự với @GroupSequence

Mặc định Bean Validation **không đảm bảo thứ tự** giữa các nhóm hoặc constraint khi validate nhiều group trong một lần gọi. Khi có kiểm tra cơ bản và kiểm tra tốn kém, bạn có thể dùng group sequence:

~~~java
import jakarta.validation.GroupSequence;
import jakarta.validation.groups.Default;

interface ExpensiveChecks {}

@GroupSequence({Default.class, ExpensiveChecks.class})
interface OrderedChecks {}
~~~

Đây là snippet minh họa ý tưởng nhóm, không phải cấu hình được sử dụng bởi controller demo ở trên. Khi validate `OrderedChecks.class`, validator chạy `Default` trước; nếu nhóm đầu có violation thì bỏ qua nhóm sau. Trong **một group**, thứ tự constraint vẫn không có bảo đảm chung.

Không tạo vòng lặp giữa các group sequence; cấu hình chu kỳ có thể gây `GroupDefinitionException`. Khi muốn định nghĩa lại **default group sequence của một class**, quy tắc khác với việc khai báo một interface sequence độc lập: phải có chính class đó trong sequence theo Jakarta Validation specification.

Group sequence không tự thay transaction hoặc thay việc kiểm tra trạng thái database.

## 12. Nested DTO: @Valid và group propagation

Nếu request chứa object con:

~~~java
record AddressInput(
    @NotBlank(groups = OnCreate.class)
    String street
) {}

record CustomerInput(
    @Valid AddressInput address
) {}
~~~

Đây là snippet minh họa; cần import `jakarta.validation.Valid` và các annotation khác, đồng thời đặt chung phạm vi type phù hợp.

`@Valid` trên field `address` cho phép **cascaded validation** vào object con. Khi validate `CustomerInput` với nhóm `OnCreate`, nhóm đó thường được truyền tiếp vào validation của `AddressInput`. Nếu thiếu `@Valid` ở quan hệ tương ứng, không nên mặc định các constraint ở object con đã chạy.

Khi cần thay group đang truyền vào object con, Jakarta Validation hỗ trợ `@ConvertGroup` tại vị trí cascaded validation, ví dụ chuyển một group cấp cha sang group cấp con. Đây là extension point nâng cao, chỉ nên dùng khi nested DTO thật sự cần quy tắc khác với group của cha.

Một group được chọn **không tự động khởi tạo object con còn null**. Nếu object con bắt buộc, thêm `@NotNull` đúng group cùng `@Valid` để vừa kiểm tra tồn tại vừa kiểm tra các field bên trong.

## 13. Vấn đề null, vắng mặt và JSON PATCH

Đây là điểm dễ gây lỗi dữ liệu nhất trong update API.

| JSON PATCH input | Java record nullable của demo | Behavior trong demo |
|---|---|---|
| `{"title":"Java 21"}` | title có text, price null | Chỉ đổi title |
| `{"priceCents":800}` | title null, price có số | Chỉ đổi price |
| `{}` | cả hai null | Giữ nguyên, không báo lỗi |
| `{"title":null}` | title null | Giữ nguyên, **không xóa title** |
| `{"title":""}` | title có chuỗi rỗng | `@Pattern` từ chối |
| `{"priceCents":-1}` | price có số âm | `@PositiveOrZero` từ chối |

Nếu hệ thống cần phân biệt:
- **Không gửi field:** giữ nguyên.
- **Gửi field null:** xóa giá trị.

thì record với nullable field là **không đủ**. Có thể dùng JSON Merge Patch, JSON Patch, `JsonNode` + schema/field-presence handling hoặc một abstraction cho ba trạng thái absent/null/value, tùy hợp đồng. Sau khi xác định field hiện diện, mới validate giá trị mới và quyết định domain rule.

PATCH cũng không tự giải quyết concurrency. Nếu hai client update một resource cùng lúc, cần cân nhắc version check, `ETag`/`If-Match` hoặc optimistic locking (ví dụ JPA `@Version`) khi dữ liệu cần bảo toàn.

## 14. Thay vì group, khi nào nên dùng DTO riêng?

Validation groups hữu ích khi:
- Phần lớn shape request giống nhau.
- Khác biệt giữa các thao tác tương đối ít.
- Quy tắc chung/riêng có thể đọc ngay trên field.
- Test đã bao phủ từng group và mọi trường hợp null/vắng mặt.

DTO riêng thường tốt hơn khi:
- POST và PATCH khác field rất nhiều.
- Tạo mới không có ID nhưng update có path ID, status hoặc version.
- Quyền chỉnh sửa từng field khác quyền tạo.
- Một số field không bao giờ được phép update, ví dụ `createdAt`, `ownerId` hoặc trạng thái được hệ thống quản lý.
- API phải phân biệt absent và explicit null.
- Group trên cùng DTO ngày càng nhiều, tạo annotation quá dài và khó chứng minh không bỏ sót.

Ví dụ thiết kế tách kiểu:

~~~java
record CreateBookRequest(
    @NotBlank String title,
    @NotNull @PositiveOrZero Integer priceCents
) {}

record PatchBookRequest(
    String title,
    Integer priceCents
) {}
~~~

Đây là **mã minh họa**; `PatchBookRequest` vẫn cần một custom constraint hoặc xử lý service để từ chối title rỗng nếu được cung cấp. Việc dùng DTO riêng **không tự giải quyết** missing/null ambiguity. Bù lại, API contract và model cập nhật được tách rõ.

Không nên cho client bind trực tiếp JPA entity chứa trường nội bộ rồi dùng groups để cố kiểm soát tất cả quyền ghi. Dùng DTO và service vẫn là ranh giới tốt hơn để chống mass assignment.

## 15. Lỗi validation ở Spring MVC

Khi `@RequestBody` đã được deserialize thành DTO và validation bean thất bại, Spring MVC thường ném `MethodArgumentNotValidException`, được framework chuyển thành **400 Bad Request**.

Với Spring Framework 6.1+, nếu controller method có **constraint trực tiếp trên method parameter** (ví dụ `@Min` ngay trên `@RequestParam`) hoặc return value, MVC có cơ chế **method validation** riêng và có thể phát sinh `HandlerMethodValidationException`. Nó khác với bean validation của một `@RequestBody` riêng lẻ; nếu xây error handler thống nhất, hãy xử lý cả hai trường hợp phù hợp.

Một controller class có `@Validated` cấp class có thể đi qua AOP method validation theo cấu hình và thay đổi loại exception. Không mặc định mọi lỗi validation luôn cùng một exception class.

Nếu có `BindingResult` hoặc `Errors` **ngay sau** tham số DTO, controller có thể tự xử lý field errors; khi đó phải chủ động chọn status/response, không nên bỏ qua lỗi rồi trả 200.

Một REST API cần lỗi ổn định có thể chuẩn hóa body bằng `@RestControllerAdvice`, `ResponseEntityExceptionHandler` hoặc `ProblemDetail`. Trả thông tin field và loại lỗi hợp lý, tránh trả lại password, token, stack trace hoặc giá trị nhạy cảm nguyên bản.

| Trường hợp | Status thường gặp | Tầng chịu trách nhiệm |
|---|---|---|
| JSON sai cú pháp | 400 | Jackson/message converter |
| Request body không đạt group constraint | 400 | Bean Validation/MVC |
| Missing required `@RequestParam` | 400 | MVC argument resolution |
| Không khớp Content-Type với consumes | 415 | Handler mapping/message conversion |
| Không hỗ trợ Accept/produces | 406 | Content negotiation |
| Resource update không tồn tại | 404 | Controller/service mapping |
| Trùng mã/vi phạm business invariant | 409 hoặc status theo contract | Service/domain/persistence |
| Không đủ quyền update | 403 hoặc status security phù hợp | Authorization |

**Validation group không thay authorization.** Client gửi request hợp lệ về shape vẫn có thể không được phép sửa resource. ID lấy từ path phải được service kiểm tra ownership và trạng thái nghiệp vụ.

## 16. Kiểm thử những trường hợp dễ bị bỏ sót

Ngoài ví dụ MockMvc, nên có test cho:
- POST thiếu `title`.
- POST thiếu `priceCents`.
- POST title chỉ có whitespace.
- POST giá âm, title quá 120 ký tự.
- PATCH chỉ có price.
- PATCH chỉ có title hợp lệ.
- PATCH gửi title whitespace hoặc giá âm.
- PATCH body rỗng `{}` theo chính sách hệ thống.
- PATCH field null tường minh theo contract.
- PUT nếu có phải yêu cầu các field bắt buộc cho full replacement.
- Nested object cần `@Valid` và nhóm được truyền đúng.
- Các constraint thuộc `Default` phải được chọn nếu dự án định dùng chúng.
- Exception handler phản hồi 400 cho Bean Validation failure, không nhầm với 409 business conflict.

Test ở service/domain còn phải kiểm tra invariant không phụ thuộc HTTP: trùng mã trong database, ownership, trạng thái không thể chuyển, kiểm soát optimistic version và transaction consistency. Một request vượt qua Bean Validation không có nghĩa toàn bộ nghiệp vụ đã hợp lệ.

## 17. Những lỗi thường gặp với validation groups

1. **Dùng `@Valid` rồi nghĩ nó đã chạy OnCreate.** `@Valid` không chọn custom group; muốn group cụ thể dùng `@Validated(OnCreate.class)` tại điểm thích hợp.
2. **Đặt một constraint không khai báo group rồi chờ nó chạy trong OnUpdate.** Mặc định nó thuộc `Default`.
3. **Dùng `@NotBlank` cho field PATCH tùy chọn.** Null bị từ chối, trái ý định update từng phần; dùng constraint “null hoặc hợp lệ” hoặc DTO riêng.
4. **Chỉ dùng `@Size` rồi nghĩ field là bắt buộc.** Với null, `@Size` thường coi là hợp lệ; cần `@NotNull`/`@NotBlank` theo group.
5. **Dùng `int` cho field tùy chọn.** Primitive không biểu diễn null rõ ràng, có thể nhầm vắng mặt với 0.
6. **Đặt `@Validated` cấp class controller không cần thiết.** Có thể thay đổi mechanism method validation và exception handling.
7. **Tin rằng tất cả group đều chạy theo thứ tự được truyền.** Muốn thứ tự thì dùng `@GroupSequence`; trong mỗi group không có thứ tự tổng quát.
8. **Quên cascade `@Valid` ở object con.** Constraints nested có thể không chạy theo kỳ vọng.
9. **Gộp DTO PUT/PATCH mà không mô tả semantics.** Full replacement và partial update không giống nhau.
10. **Dùng group để thay nghiệp vụ hoặc phân quyền.** Bean Validation không tự check uniqueness trong DB, owner, transaction hay state machine.
11. **Không test cả create và update.** Một constraint vô tình chỉ thuộc Default có thể khiến endpoint sử dụng custom group nhận dữ liệu sai.
12. **Trả 200 khi validation lỗi do tự bắt lỗi quá rộng.** HTTP status cần phản ánh contract.

## 18. Checklist triển khai

- [ ] Đã xác định POST create, PUT replace và PATCH partial update là các hợp đồng khác nhau.
- [ ] Có implementation Jakarta Bean Validation, ví dụ `spring-boot-starter-validation`.
- [ ] Định nghĩa group marker và gán đúng constraint cho mỗi nhóm.
- [ ] Hiểu rõ nhóm `Default` không tự chạy cùng custom group.
- [ ] Dùng `@Validated(OnCreate.class)` và `@Validated(OnUpdate.class)` tại các request DTO phù hợp.
- [ ] Với PATCH, cho phép field thiếu nhưng từ chối field được gửi sai.
- [ ] Đã quyết định semantics của missing, explicit null và empty string.
- [ ] Dùng DTO để tránh cho client tự ghi field nội bộ.
- [ ] Đã kiểm tra nested `@Valid`, group propagation/`@ConvertGroup` nếu cần.
- [ ] Có test MockMvc cho cả PASS và 400 ở create/update.
- [ ] Phân biệt bean validation với kiểm tra resource tồn tại, ownership và business invariant.
- [ ] Không tự động dùng class-level `@Validated` trên controller nếu chỉ cần request-body groups.

## 19. Tài liệu tham khảo

- [Spring Framework — Spring MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): `@Valid`, `@Validated`, `MethodArgumentNotValidException` và `HandlerMethodValidationException`.
- [Spring Framework — @RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html): deserialization và validation của request body.
- [Spring Boot — Validation](https://docs.spring.io/spring-boot/3.3/reference/io/validation.html): integration Jakarta Bean Validation và method validation.
- [Hibernate Validator — Reference Guide](https://docs.jboss.org/hibernate/validator/8.0/reference/en-US/html_single/): constraint groups, group sequence, group inheritance và group conversion.
- [Jakarta Validation Specification](https://jakarta.ee/specifications/bean-validation/3.0/): hợp đồng và semantics chuẩn của constraints/groups.

**Ghi nhớ:** Validation groups cho phép cùng một DTO được kiểm tra khác nhau giữa **tạo mới** và **cập nhật**, nhưng nhóm chỉ là nhãn constraint, không thay đổi HTTP method hay tự giải quyết missing/null, bảo mật và business logic. Chọn group rõ bằng `@Validated`, hiểu `Default`, giữ ranh giới DTO/service, và kiểm thử cả request hợp lệ lẫn không hợp lệ để API không vô tình chấp nhận dữ liệu sai.
