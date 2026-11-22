# Giá trị null, Optional và phân biệt đầu vào thiếu với đầu vào rỗng trong Spring MVC

## Mục tiêu

Trong Spring MVC, **không có đầu vào**, **đầu vào hiện diện nhưng rỗng**, **đầu vào chứa khoảng trắng**, **giá trị JSON null** và **giá trị đã bị chuyển kiểu thành null** có thể dẫn đến hành vi khác nhau. Bài này giúp bạn:

- Chọn đúng cách nhận giá trị qua `@RequestParam`, `@RequestHeader`, `@PathVariable`, `@RequestBody`, `@ModelAttribute`.
- Dùng `required=false`, `Optional<T>`, `defaultValue` và `@Nullable` mà không đánh mất các trạng thái quan trọng.
- Phân biệt `?name`, `?name=`, không có `name` và `?name=%20` ở mức Servlet request parameter.
- Phân biệt JSON **thiếu field**, field mang `null`, chuỗi `""`, chuỗi chỉ có khoảng trắng, mảng `[]` và object `{}`.
- Thiết kế kiểm tra đầu vào và mã lỗi HTTP phù hợp; tránh ghi đè dữ liệu khi xử lý cập nhật từng phần (PATCH).

Phạm vi: **Spring MVC (Servlet stack)**, Java 17+, Spring Framework 6.x/Spring Boot 3.x; nhiều nguyên lý tương tự ở phiên bản mới nhưng phải kiểm tra thay đổi cấu hình thực tế. Đây không phải bài về Java `Optional` nói chung hay Spring WebFlux (WebFlux có quy tắc lấy request parameter khác).

## 1. Bảng thuật ngữ: “thiếu” khác “rỗng” thế nào?

Xét một đầu vào tên `name`:

| Tình huống | Ví dụ HTTP/JSON | Ý nghĩa ban đầu |
| --- | --- | --- |
| Thiếu (missing/absent) | `GET /items`, không có tham số `name` | Client **không gửi tên tham số** |
| Có tên, giá trị rỗng | `GET /items?name=` hoặc `?name` | Tham số hiện diện, giá trị chuỗi có độ dài 0 |
| Có tên, chỉ có khoảng trắng | `GET /items?name=%20` | Giá trị là `" "`: **khác chuỗi rỗng** |
| Giá trị thường | `GET /items?name=An` | Giá trị là `"An"` |
| JSON field thiếu | `{}` | Object không có khóa `name` |
| JSON field explicit null | `{"name":null}` | Object **có khóa** nhưng giá trị là JSON `null` |
| JSON field chuỗi rỗng | `{"name":""}` | Object có khóa, giá trị là chuỗi rỗng |
| JSON field chuỗi trắng | `{"name":"   "}` | Object có khóa, giá trị là chuỗi chứa khoảng trắng |
| JSON collection rỗng | `{"tags":[]}` | Mảng tồn tại, có 0 phần tử |
| JSON object rỗng | `{"settings":{}}` | Object tồn tại, có 0 field |

**Java `null` không phải là JSON `null` theo nghĩa “đã nhận được”.** JSON field không tồn tại và JSON field hiện diện có giá trị `null` đều có thể đi vào một thuộc tính Java `String name` dưới dạng `null` sau deserialize. Nếu yêu cầu nghiệp vụ cần biết *client có gửi field hay không*, kiểu Java `String` đơn lẻ thường không đủ.

Một request parameter không thể tự có giá trị “JSON null”. Chuỗi ký tự `null` trong `?name=null` chỉ là chuỗi `"null"`, hoàn toàn không tự chuyển thành `null` cho `String`.

## 2. `@RequestParam`: required, null, chuỗi rỗng và defaultValue

`@RequestParam` nhận Servlet request parameter. Trên Spring MVC, các parameter có thể đến từ **query string hoặc dữ liệu form được Servlet container parse**; không nên mặc định mọi `@RequestParam` đều chỉ lấy URL query.

### 2.1. Mặc định là bắt buộc

```java
@GetMapping("/required")
public String required(@RequestParam("name") String name) {
    return "Hello " + name;
}
```

Với cấu hình thông thường:

- `GET /required` → thiếu `name` → Spring trả `400 Bad Request` trước khi chạy method.
- `GET /required?name=` → `name` là `""`; annotation **không mặc định từ chối chuỗi rỗng**.
- `GET /required?name=%20` → `name` chứa một khoảng trắng; nó không tự biến thành chuỗi rỗng.
- `GET /required?name=An` → `name` là `"An"`.

`required=true` nói về **sự hiện diện/có thể resolve được của tham số**, không đồng nghĩa ràng buộc “phải có ký tự hữu ích”. Để kiểm tra văn bản bắt buộc không được rỗng hoặc chỉ có khoảng trắng, dùng quy tắc nghiệp vụ hay Jakarta Bean Validation (`@NotBlank`) khi đã thiết lập validation.

### 2.2. Cho phép thiếu bằng `required=false`

```java
@GetMapping("/optional-string")
public String optionalString(
        @RequestParam(name = "name", required = false) String name) {
    return name == null ? "MISSING" :
            name.isEmpty() ? "EMPTY" :
            name.isBlank() ? "BLANK" : "VALUE";
}
```

Với binder mặc định và không áp dụng bộ chỉnh chuỗi riêng:

| URL | `name` nhận được | Kết quả |
| --- | --- | --- |
| `/optional-string` | Java `null` | `MISSING` |
| `/optional-string?name` | `""` | `EMPTY` |
| `/optional-string?name=` | `""` | `EMPTY` |
| `/optional-string?name=%20` | `" "` | `BLANK` |
| `/optional-string?name=An` | `"An"` | `VALUE` |

Đừng suy ra rằng `?name` và `?name=` có thể phân biệt qua `@RequestParam String`: cả hai thường được Servlet API xem là tham số hiện diện với giá trị `""`. Nếu bài toán cần phân biệt chính xác cú pháp hai cách viết này, phải phân tích raw query string theo một giao ước được kiểm soát (xem thêm vấn đề encoding, lặp tên, ký tự `+` và `%xx`); đa số API **không cần** phân biệt như vậy.

### 2.3. Giá trị mặc định thay thế *cả thiếu và rỗng*

```java
@GetMapping("/with-default")
public String withDefault(
        @RequestParam(name = "name", defaultValue = "guest") String name) {
    return name;
}
```

| Request | Kết quả |
| --- | --- |
| `/with-default` | `guest` |
| `/with-default?name=` | `guest` |
| `/with-default?name` | `guest` |
| `/with-default?name=An` | `An` |
| `/with-default?name=%20` | `" "` trong cấu hình mặc định, **không phải guest** |

`defaultValue` ngầm làm tham số không còn required, nhưng nó **xóa khác biệt giữa missing và empty**. Nếu nghiệp vụ cần “thiếu thì dùng mặc định; rỗng thì báo lỗi hoặc xóa dữ liệu”, đừng dùng `defaultValue` trực tiếp: nhận `required=false` và tự phân nhánh theo sự hiện diện/giá trị.

### 2.4. Đổi kiểu có thể làm mất trạng thái ban đầu

```java
@GetMapping("/integer")
public String integer(
        @RequestParam(name = "count", required = false) Integer count) {
    return count == null ? "NO_COUNT" : count.toString();
}
```

Với converter mặc định, tham số vắng mặt và `?count=` có thể cùng được chuyển thành Java `null`. `?count=abc` không chuyển được thành số: thường là `400 Bad Request` do lỗi chuyển kiểu; nó không tự thành `null`. Nếu dùng `@RequestParam("count") int count`, không thể gán `null` vào primitive `int`, và Spring xử lý lỗi thay vì đưa null vào method.

Tài liệu Spring nhấn mạnh: **chuỗi rỗng trở thành null sau conversion có thể bị coi là thiếu**, gây lỗi required ngay cả khi tên tham số thực sự xuất hiện. Ví dụ `@RequestParam("count") Long count` với `?count=` thường tạo lỗi 400 do “missing after conversion”. Hành vi cụ thể phụ thuộc bộ converter và `@InitBinder` custom.

## 3. Dùng `Optional<T>` trong controller

Spring MVC hỗ trợ `java.util.Optional` cho controller method argument có annotation sở hữu thuộc tính `required`, ví dụ `@RequestParam` và `@RequestHeader`. Nó tương đương cho phép thiếu giá trị.

```java
@GetMapping("/optional-count")
public String count(@RequestParam("count") Optional<Integer> count) {
    return count.map(String::valueOf).orElse("NO_COUNT");
}
```

- `/optional-count` → `Optional.empty()` → `NO_COUNT`.
- `/optional-count?count=7` → `Optional.of(7)` → `7`.
- `/optional-count?count=` → với conversion mặc định, chuỗi rỗng sang `Integer` thành null → `Optional.empty()`.
- `/optional-count?count=abc` → converter không hiểu `abc` → thường HTTP 400, **không** thành `Optional.empty()`.

Đối với `Optional<String>`, một giá trị chuỗi rỗng thường là **`Optional.of("")`** vì converter giữ chuỗi rỗng, trong khi giá trị thiếu cho `Optional.empty()`; đừng suy luận mọi `Optional<T>` đều gom chuỗi rỗng thành empty. Custom formatter/binder có thể thay đổi hành vi. `Optional` chỉ biểu diễn **có giá trị / không có giá trị sau binding**; nó không tự giữ lại toàn bộ lịch sử vì sao giá trị biến mất.

Quy tắc thực hành:

1. Nếu chỉ cần dùng giá trị hoặc mặc định khi không có: dùng `Optional<T>` hoặc `required=false`.
2. Nếu cần phân biệt query missing và empty: giữ tham số dạng `String` và kiểm tra sự hiện diện qua `HttpServletRequest.getParameterMap()` khi cần.
3. Nếu cần phân biệt số bị để trống và không gửi: nhận tham số dưới dạng `String` trước, xác định trạng thái rồi parse `Integer.parseInt`/conversion và phản hồi lỗi phù hợp.
4. Không khai báo `Optional` làm **field của DTO JSON** chỉ vì muốn biểu diễn PATCH ba trạng thái; JSON field missing và explicit null có thể cùng biến thành “empty” trong nhiều cách deserialize. Dùng biểu diễn có dấu vết hiện diện khi bài toán cần ba trạng thái.

**Java `Optional` không thay thế validation.** `Optional.of("")` vẫn chứa chuỗi rỗng; nếu cần ký tự hữu ích thì phải kiểm tra hoặc validate nội dung sau khi lấy ra.

## 4. Kiểm tra *tên tham số có xuất hiện* bằng Servlet API

Khi `@RequestParam(required=false) String name` trả `null`, phần lớn ứng dụng có thể coi là thiếu. Nếu đã đăng ký formatter/binder có thể chuyển chuỗi rỗng thành null, hãy kiểm tra thêm **sự hiện diện của key**:

```java
@GetMapping("/inspect")
public String inspect(
        @RequestParam(name = "name", required = false) String name,
        jakarta.servlet.http.HttpServletRequest request) {

    boolean sent = request.getParameterMap().containsKey("name");
    if (!sent) {
        return "MISSING";
    }
    if (name == null) {
        return "PRESENT_BUT_CONVERTED_TO_NULL";
    }
    if (name.isEmpty()) {
        return "EMPTY";
    }
    return name.isBlank() ? "BLANK" : "VALUE";
}
```

`request.getParameterMap()` lấy **parameter hiện diện**, kể cả nếu chuỗi value rỗng. `request.getParameterValues("name")` hữu ích khi client gửi nhiều lần như `?name=a&name=b`; nhận một `String` đơn lẻ thường không phù hợp để quyết định ngữ nghĩa input lặp. Với API chỉ chấp nhận một giá trị, nên kiểm tra và từ chối tham số lặp khi điều đó ảnh hưởng nghiệp vụ.

Đừng parse thẳng `getQueryString()` để ra quyết định phổ thông nếu không cần: query string có phần mã hóa, lặp key và tương tác với form binding. Dùng Servlet API cho quan hệ **có tham số/không có tham số**; dùng raw query chỉ khi hợp đồng API yêu cầu cú pháp ở mức byte.

## 5. `@RequestBody` và JSON: missing field khác explicit null

`@RequestBody` đi qua `HttpMessageConverter` (thường là Jackson JSON converter khi có Jackson). Có **hai lớp vắng mặt** khác nhau:

- **Không có body HTTP**: request gửi 0 byte body.
- **Có JSON object body, nhưng không có một field**: ví dụ `{}`. Đây không phải “không có request body”.

### 5.1. Toàn bộ request body có bắt buộc không?

```java
@PostMapping(path = "/receive", consumes = "application/json")
public String receive(@RequestBody(required = false) MyDto body) {
    return body == null ? "NO_DESERIALIZED_OBJECT" : "OBJECT_RECEIVED";
}

public record MyDto(String name) {}
```

Với `@RequestBody` mặc định `required=true`, body vắng mặt thường dẫn tới **HTTP 400** trước khi chạy method. `required=false` cho phép thiếu body và có thể đưa `null` vào method. Tuy nhiên:

- JSON literal `null` cũng có thể được Jackson chuyển thành Java `null`. Ví dụ trên **không xác định chắc được** request không có byte body hay client gửi bốn ký tự `null`.
- JSON `{}` là object hợp lệ; với DTO record có `String name` thì `name` có thể bằng `null` nhưng bản thân DTO vẫn tồn tại.
- Body `{"name":null}` có thể tạo DTO với `name==null`, giống `{}`. Bạn đã mất dấu vết field có được gửi hay không.
- JSON sai cú pháp thường gây **400 Bad Request** (lỗi đọc body), không phải “body vắng mặt”.
- `required=false` không bỏ qua kiểm tra kiểu media (`Content-Type`) hoặc lỗi chuyển đổi JSON; không sử dụng nó để hợp thức hóa dữ liệu sai.

Khi cần kiểm tra **độ dài body HTTP thực sự** khác JSON literal `null`, phải chủ động thiết kế một tầng đọc raw body phù hợp với Servlet/request caching. Không đọc input stream lần hai sau khi converter đã tiêu thụ. Tránh coi `required=false` là giải pháp cho yêu cầu phân biệt mọi trạng thái.

### 5.2. Một DTO Java đơn giản thường gộp missing và null

```java
public record ProfileInput(String nickname, Integer age) {}
```

Với Jackson thông thường, nếu không có cấu hình bắt buộc đặc biệt:

| JSON gửi lên | `nickname` trong DTO | `age` trong DTO |
| --- | --- | --- |
| `{}` | `null` | `null` |
| `{"nickname":null}` | `null` | `null` |
| `{"nickname":""}` | `""` | `null` |
| `{"nickname":" "}` | `" "` | `null` |
| `{"age":0}` | `null` | `0` |

Điểm cốt lõi là DTO chỉ nắm **giá trị sau deserialization**. Jackson có các tùy chọn liên quan coercion, constructor, primitive và null-handling; kết quả có thể khác với cấu hình tùy chỉnh. Không lấy hành vi mặc định của DTO làm giao ước về PATCH nếu cần phân biệt “giữ nguyên” với “xóa”.

### 5.3. `JsonNode` giữ lại sự hiện diện của field

Nếu nghiệp vụ yêu cầu phân biệt missing/null/empty, có thể nhận object JSON bằng `JsonNode`:

```java
@PostMapping(path = "/field", consumes = "application/json")
public String field(@RequestBody com.fasterxml.jackson.databind.JsonNode root) {
    if (!root.isObject()) {
        throw new org.springframework.web.server.ResponseStatusException(
                org.springframework.http.HttpStatus.BAD_REQUEST,
                "JSON object required");
    }

    com.fasterxml.jackson.databind.JsonNode field = root.get("nickname");

    if (field == null) {
        return "MISSING";              // không có key "nickname"
    }
    if (field.isNull()) {
        return "NULL";                 // {"nickname":null}
    }
    if (field.isTextual() && field.textValue().isEmpty()) {
        return "EMPTY";                // {"nickname":""}
    }
    if (field.isTextual() && field.textValue().isBlank()) {
        return "BLANK";                // {"nickname":"   "}
    }
    return "PRESENT_NONEMPTY";
}
```

`JsonNode.get("nickname") == null` thể hiện field vắng mặt. `root.has("nickname")` đúng nếu key tồn tại **kể cả khi value là explicit JSON null**. `root.hasNonNull("nickname")` chỉ đúng khi field tồn tại và value khác JSON null. `root.path("nickname")` trả `MissingNode` nếu vắng mặt, còn explicit `null` là `NullNode`; nếu dùng `path` phải kiểm tra `isMissingNode()` và `isNull()` riêng. Không nên gọi `asText()` vô điều kiện rồi dùng chuỗi trả về để suy ra key có tồn tại.

Với PATCH phức tạp, dùng DTO có cơ chế ghi nhận field nào xuất hiện (custom Jackson setter, presence flag hoặc JSON Merge Patch/JSON Patch theo hợp đồng riêng). Dùng `JsonNode` là một lựa chọn dễ hiểu cho ví dụ, nhưng trong hệ thống lớn cần validation, giới hạn field hợp lệ và tránh cập nhật trực tiếp entity bằng JSON tùy ý.

## 6. Validation: `@NotNull`, `@NotEmpty`, `@NotBlank` khác nhau

Dùng Jakarta Bean Validation với Spring Boot 3 và dependency `spring-boot-starter-validation`. Khi dùng `@Valid @RequestBody` cho DTO phù hợp, lỗi validation thường thành **HTTP 400** thông qua `MethodArgumentNotValidException` theo cấu hình MVC mặc định.

| Annotation | Kiểm tra ý nghĩa | `null` | `""` | `"   "` |
| --- | --- | --- | --- | --- |
| `@NotNull` | Giá trị không phải null | Không hợp lệ | Hợp lệ | Hợp lệ |
| `@NotEmpty` | Không null và không rỗng; áp dụng chuỗi/collection/array/map được hỗ trợ | Không hợp lệ | Không hợp lệ | Hợp lệ |
| `@NotBlank` | Không null và chuỗi có ít nhất một ký tự không phải khoảng trắng | Không hợp lệ | Không hợp lệ | Không hợp lệ |

Ví dụ DTO tạo mới:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

public record CreateProfile(
        @NotBlank String nickname,
        @NotNull @Positive Integer age) {}
```

- `nickname` thiếu, explicit null, `""` hoặc `"   "` đều không hợp lệ theo `@NotBlank`.
- `age` thiếu/null bị `@NotNull` từ chối; `0` hoặc số âm bị `@Positive` từ chối.
- `Integer` cho phép biểu diễn thiếu/null trước validation. Với primitive `int`, Jackson có thể gán mặc định `0` (tùy coercion) và làm mất dấu vết null, nên cân nhắc wrapper khi cần quy tắc “bắt buộc”.
- `@Size(min=1)` không đồng nghĩa `@NotNull`: với nhiều constraint như `@Size`, `null` được xem là hợp lệ để tách kiểm tra tồn tại khỏi giới hạn độ dài.

Nếu ràng buộc đặt trực tiếp trên controller method parameter (ví dụ `@RequestParam @NotBlank String name`), đó có thể là **method validation** với đường xử lý ngoại lệ khác (`HandlerMethodValidationException` trong Spring MVC 6.1+). Cần kiểm tra cấu hình Spring thực tế; bài này sử dụng `@Valid` với DTO để có kiểm thử ổn định hơn.

## 7. Ví dụ ứng dụng đầy đủ: Java 17+ và Spring Boot 3.x

Đoạn dưới là một controller **biên dịch trong dự án Spring Boot có Spring MVC, Jackson, Jakarta Validation**. Đặt ở `src/main/java/com/example/demo/InputController.java`. Để có một ứng dụng chạy, lớp `@SpringBootApplication` ở cùng package hoặc package cha và dependency Web/Validation là cần thiết.

```java
package com.example.demo;

import com.fasterxml.jackson.databind.JsonNode;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import java.util.Map;
import java.util.Optional;

@RestController
@RequestMapping("/inputs")
public class InputController {

    @GetMapping("/query")
    public QueryView query(
            @RequestParam(name = "q", required = false) String q,
            @RequestParam(name = "count") Optional<Integer> count,
            HttpServletRequest request) {

        boolean supplied = request.getParameterMap().containsKey("q");
        String state;
        if (!supplied) {
            state = "MISSING";
        } else if (q == null) {
            state = "CONVERTED_TO_NULL";
        } else if (q.isEmpty()) {
            state = "EMPTY";
        } else if (q.isBlank()) {
            state = "BLANK";
        } else {
            state = "VALUE";
        }

        return new QueryView(state, q,
                count.map(String::valueOf).orElse("NO_COUNT"));
    }

    @GetMapping("/default")
    public Map<String, String> defaultQuery(
            @RequestParam(name = "q", defaultValue = "guest") String q) {
        return Map.of("q", q);
    }

    @GetMapping("/required")
    public Map<String, Long> required(@RequestParam("id") Long id) {
        return Map.of("id", id);
    }

    @PostMapping(path = "/json",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public FieldView inspectJson(@RequestBody JsonNode root) {
        if (!root.isObject()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "JSON object required");
        }

        JsonNode nickname = root.get("nickname");
        String state;
        if (nickname == null) {
            state = "MISSING";
        } else if (nickname.isNull()) {
            state = "NULL";
        } else if (nickname.isTextual() && nickname.textValue().isEmpty()) {
            state = "EMPTY";
        } else if (nickname.isTextual() && nickname.textValue().isBlank()) {
            state = "BLANK";
        } else {
            state = "PRESENT_NONEMPTY";
        }

        String textValue = (nickname != null && nickname.isTextual())
                ? nickname.textValue() : null;
        return new FieldView(state, textValue);
    }

    @PostMapping(path = "/optional-body",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, String> optionalBody(
            @RequestBody(required = false) JsonNode root) {
        return Map.of("state",
                root == null ? "NO_BODY_OR_JSON_NULL" : "HAS_JSON_VALUE");
    }

    @PostMapping(path = "/profiles",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Map<String, String>> createProfile(
            @Valid @RequestBody CreateProfile body) {
        // Demo xác nhận dữ liệu hợp lệ, chưa lưu vào database.
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of("status", "ACCEPTED"));
    }

    public record QueryView(String state, String q, String count) {}
    public record FieldView(String state, String value) {}

    public record CreateProfile(
            @NotBlank String nickname,
            @NotNull @Positive Integer age) {}
}
```

Cần dependency `spring-boot-starter-web` (cung cấp Web MVC và Jackson trong cấu hình Boot phổ biến) và `spring-boot-starter-validation` (cho Jakarta Bean Validation). Tạo lớp khởi động nếu dự án chưa có:

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

Tệp thứ hai: `src/main/java/com/example/demo/DemoApplication.java`. Chạy dự án Maven đã cấu hình Spring Boot:

```bash
./mvnw spring-boot:run
```

Trên Windows PowerShell: `.\mvnw.cmd spring-boot:run`. Vì controller dùng Spring, Jackson và Jakarta Validation, **không thể chạy chỉ bằng `javac InputController.java` thiếu thư viện**; lệnh trên áp dụng cho một dự án Boot có `pom.xml` và Maven Wrapper phù hợp. Cấu hình mặc định chạy trên cổng 8080 nếu không đổi `server.port`.

## 8. Thực hành curl và kết quả có thể kiểm tra

Các lệnh dưới dùng `curl` trên bash/zsh; Windows PowerShell có thể dùng `curl.exe` và viết trên một dòng.

### 8.1. Query parameter

**Không truyền `q`:**

```bash
curl -s "http://localhost:8080/inputs/query"
```

JSON dự kiến theo Jackson mặc định:

```json
{"state":"MISSING","q":null,"count":"NO_COUNT"}
```

**Truyền chuỗi rỗng `q=`:**

```bash
curl -s "http://localhost:8080/inputs/query?q="
```

```json
{"state":"EMPTY","q":"","count":"NO_COUNT"}
```

**Truyền một dấu cách đã URL encode:**

```bash
curl -s "http://localhost:8080/inputs/query?q=%20"
```

```json
{"state":"BLANK","q":" ","count":"NO_COUNT"}
```

**Giá trị thường và số hợp lệ:**

```bash
curl -s "http://localhost:8080/inputs/query?q=Lan&count=3"
```

```json
{"state":"VALUE","q":"Lan","count":"3"}
```

Các JSON trên thể hiện **giá trị trường**, không cam kết thứ tự key theo bộ serializer. Nếu ứng dụng đổi cấu hình Jackson để bỏ field null, `"q":null` có thể không xuất hiện; trường `state` vẫn minh họa phân biệt.

**Tham số số rỗng:** `GET /inputs/query?count=` → `count` là `Optional.empty()` theo converter mặc định, nên body `count` là `"NO_COUNT"`. **Tham số số sai định dạng:** `GET /inputs/query?count=abc` → thường HTTP 400 do không chuyển thành Integer.

### 8.2. Giá trị mặc định

```bash
curl -s "http://localhost:8080/inputs/default"
curl -s "http://localhost:8080/inputs/default?q="
curl -s "http://localhost:8080/inputs/default?q=Lan"
```

Theo thứ tự, `q` trong JSON là `"guest"`, `"guest"`, `"Lan"`. Đây là ví dụ cho thấy `defaultValue` đã cố ý gộp missing và empty.

### 8.3. Trường JSON: missing, null, empty, blank

```bash
curl -s http://localhost:8080/inputs/json \
  -H "Content-Type: application/json" \
  --data '{}'
```

`state` dự kiến: `MISSING`.

```bash
curl -s http://localhost:8080/inputs/json \
  -H "Content-Type: application/json" \
  --data '{"nickname":null}'
```

`state` dự kiến: `NULL`.

```bash
curl -s http://localhost:8080/inputs/json \
  -H "Content-Type: application/json" \
  --data '{"nickname":""}'
```

`state` dự kiến: `EMPTY`.

```bash
curl -s http://localhost:8080/inputs/json \
  -H "Content-Type: application/json" \
  --data '{"nickname":"   "}'
```

`state` dự kiến: `BLANK`.

Ở đây `JsonNode` bảo toàn sự hiện diện của key: `get` trả Java null khi **không có key**, còn `{"nickname":null}` tạo node có `isNull() == true`.

### 8.4. Body bắt buộc và validation

```bash
curl -i http://localhost:8080/inputs/profiles \
  -H "Content-Type: application/json" \
  --data '{"nickname":"","age":18}'
```

Dự kiến **400** do `@NotBlank` từ chối nickname rỗng. Với input hợp lệ:

```bash
curl -i http://localhost:8080/inputs/profiles \
  -H "Content-Type: application/json" \
  --data '{"nickname":"Lan","age":18}'
```

Dự kiến **201 Created** và body JSON chứa `"status":"ACCEPTED"`.

`POST /inputs/optional-body` với `Content-Type: application/json` nhưng không có body được nhận vì `required=false`. Nếu gửi body JSON literal `null`, converter cũng có thể cho ra Java `null`; endpoint sẽ trả cùng trạng thái `NO_BODY_OR_JSON_NULL`. Đây là **giới hạn chủ ý** của kiểu đã giải mã, không phải bằng chứng HTTP body giống nhau.

## 9. Test bằng MockMvc: xác minh từng trạng thái

Thêm `spring-boot-starter-test` làm dependency test. Ví dụ sau đặt tại `src/test/java/com/example/demo/InputControllerTest.java`, chạy với Boot 3.x và không thêm custom security/filter vào môi trường test:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(InputController.class)
class InputControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void distinguishesMissingEmptyAndBlankQuery() throws Exception {
        mvc.perform(get("/inputs/query"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state").value("MISSING"));

        mvc.perform(get("/inputs/query").param("q", ""))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state").value("EMPTY"));

        mvc.perform(get("/inputs/query").param("q", " "))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state").value("BLANK"));
    }

    @Test
    void optionalNumberKeepsValidValueButAllowsMissing() throws Exception {
        mvc.perform(get("/inputs/query").param("count", "3"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.count").value("3"));

        mvc.perform(get("/inputs/query").param("count", ""))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.count").value("NO_COUNT"));

        mvc.perform(get("/inputs/query").param("count", "abc"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void defaultValueCollapsesMissingAndEmpty() throws Exception {
        mvc.perform(get("/inputs/default"))
                .andExpect(jsonPath("$.q").value("guest"));

        mvc.perform(get("/inputs/default").param("q", ""))
                .andExpect(jsonPath("$.q").value("guest"));
    }

    @Test
    void missingOrBlankRequiredNumberIsRejected() throws Exception {
        mvc.perform(get("/inputs/required"))
                .andExpect(status().isBadRequest());

        mvc.perform(get("/inputs/required").param("id", ""))
                .andExpect(status().isBadRequest());
    }

    @Test
    void jsonFieldPresenceIsPreservedByJsonNode() throws Exception {
        mvc.perform(post("/inputs/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state").value("MISSING"));

        mvc.perform(post("/inputs/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"nickname\":null}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state").value("NULL"));

        mvc.perform(post("/inputs/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"nickname\":\"\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state").value("EMPTY"));

        mvc.perform(post("/inputs/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"nickname\":\" \"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state").value("BLANK"));
    }

    @Test
    void validatesProfileOnCreate() throws Exception {
        mvc.perform(post("/inputs/profiles")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"nickname\":\" \",\"age\":18}"))
                .andExpect(status().isBadRequest());

        mvc.perform(post("/inputs/profiles")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"nickname\":\"Lan\",\"age\":18}"))
                .andExpect(status().isCreated());
    }

    @Test
    void optionalBodyAllowsNoBody() throws Exception {
        mvc.perform(post("/inputs/optional-body")
                .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state")
                        .value("NO_BODY_OR_JSON_NULL"));
    }
}
```

Dùng `./mvnw test` hoặc Windows `.\mvnw.cmd test`. Đây là **bộ test có thể chạy trong dự án Boot đủ dependency**, không phải kết quả đã thực thi ở mọi môi trường. Nếu có security hoặc Jackson tùy chỉnh, cấu hình MockMvc tương ứng. Test cố ý kiểm tra field `state` thay vì giả định thứ tự JSON hoặc body lỗi Spring Boot cố định.

## 10. Các loại đầu vào controller khác

### `@RequestHeader` và `@CookieValue`

`@RequestHeader("X-Trace-Id")` mặc định required. Dùng `@RequestHeader(name = "X-Trace-Id", required = false) String traceId` nếu muốn cho phép thiếu; `Optional<String>` cũng được hỗ trợ. Header không có và header tồn tại với giá trị rỗng là hai trường hợp khái niệm khác nhau, nhưng proxy, browser và HTTP library có thể chuẩn hóa, loại bỏ hoặc từ chối header trống. Nếu dùng `defaultValue`, kiểu annotation tương ứng có thể gộp missing với empty tương tự request parameter.

`@CookieValue` có cơ chế required/default/Optional liên quan; cookie vắng mặt không đồng nghĩa cookie có nội dung rỗng. Cần chú ý decode, xác thực và giá trị mặc định theo giao ước cookie.

### `@PathVariable`

`@PathVariable("id") Long id` gắn với **URL pattern đã match**, ví dụ `/items/{id}`. URL `/items` không tự mang một `id=null` tới mapping chỉ nhận `/items/{id}`; thông thường đó là **path không match (404)**, chứ không nhất thiết là lời gọi method với id thiếu. Nếu muốn hỗ trợ cả hai dạng URL, hãy khai báo mapping tương ứng rõ ràng và cân nhắc xử lý `required=false`/`Optional`.

Giá trị `/items/abc` với `Long id` có thể dẫn đến 400 vì lỗi chuyển kiểu, trong khi `/items/` có thể không match path pattern. Đây là lỗi khác nhau: **không có route** và **có route nhưng input không chuyển kiểu được**.

### `@ModelAttribute` và form data

Đối tượng `@ModelAttribute` có thể nhận dữ liệu từ form/query và qua data binding. Field không được gửi có thể giữ `null` hoặc giá trị khởi tạo; field gửi rỗng thường là `""` với `String` (trừ custom binder), còn trường số có thể trở thành null hoặc lỗi conversion. Khi cần đánh dấu field nào thực sự có mặt trong form, hãy kiểm tra tham số request hay thiết kế DTO có cơ chế lưu thông tin hiện diện. Dùng `@Valid` và `BindingResult` nếu cần xử lý lỗi binding/validation trong method.

Trong Spring MVC, dữ liệu form `application/x-www-form-urlencoded` thường dùng `@RequestParam`/`@ModelAttribute`. Đừng kỳ vọng `@RequestBody` đọc form qua Servlet API giống đọc JSON trong mọi môi trường.

### Multipart file

`@RequestParam(name="file", required=false) MultipartFile file`: nếu không có part, thường nhận `null`; nếu có part chứa file kích thước 0, có thể nhận đối tượng `MultipartFile` với `file.isEmpty() == true`. `MultipartFile.isEmpty()` cũng có thể đúng trong những trường hợp không chọn file cho form; vì vậy khi nghiệp vụ cần phân biệt “không upload” và “upload file 0 byte”, cần xét **sự tồn tại part**, `getSize()`, filename và quy tắc HTTP/form thực tế, không chỉ gọi `isEmpty()`. Đối với upload thực, còn cần giới hạn kích thước và kiểm tra loại file.

## 11. Áp dụng cho CREATE, UPDATE và PATCH

Một hợp đồng cập nhật từng phần hay dùng ba trạng thái:

| JSON request field | Ý định ví dụ khi PATCH profile |
| --- | --- |
| Không có `nickname` | **Giữ nguyên** nickname đang lưu |
| Có `"nickname":null` | **Xóa** nickname, nếu nghiệp vụ cho phép nullable |
| Có `"nickname":""` | **Đặt thành chuỗi rỗng** hoặc báo validation error, theo quy tắc API |
| Có `"nickname":"Lan"` | **Đổi** nickname thành `Lan` |

Nếu deserialize thẳng ba request đầu vào DTO `record PatchProfile(String nickname)`, hai trường hợp missing và explicit null có thể cùng đưa ra Java null. Code như `if (nickname == null) skip` sẽ không thể thực hiện yêu cầu “explicit null nghĩa là xóa”.

Giải pháp phù hợp tùy dự án:

- **Đơn giản, ít field:** nhận `JsonNode` và kiểm tra `has`/`isNull`/`isTextual`, sau đó chuyển sang command/DTO đã validate.
- **DTO rõ kiểu và nhiều field:** dùng Jackson setter/presence flags hoặc cấu trúc wrapper ba trạng thái (`ABSENT`/`EXPLICIT_NULL`/`VALUE`) và converter có kiểm thử.
- **Theo chuẩn cập nhật:** dùng JSON Merge Patch (RFC 7396) hoặc JSON Patch (RFC 6902), khai báo `Content-Type` và ngữ nghĩa riêng. Theo JSON Merge Patch, null trong patch **xóa member**; cần đọc đúng chuẩn trước khi chọn.
- **PUT toàn phần:** hợp đồng thường yêu cầu representation đầy đủ; quy tắc field missing/null nên được chỉ rõ và validate theo yêu cầu resource, tránh tự áp nghĩa PATCH vào PUT.

Validation cho CREATE có thể nghiêm ngặt hơn PATCH. Ví dụ `@NotBlank` phù hợp nickname bắt buộc khi tạo mới; PATCH cần cho phép **vắng mặt** để không sửa, nhưng khi field đã có mặt thì vẫn kiểm tra điều kiện (trừ khi explicit null được phép để xóa). Đừng tùy tiện áp dụng cùng DTO/ràng buộc cho cả hai nghiệp vụ.

## 12. Checklist chẩn đoán sai dữ liệu đầu vào

1. **Ghi lại request chính xác**: method, URL đã được encode, `Content-Type`, raw body, tên parameter lặp. Đừng suy luận từ object Java sau binding rằng client đã gửi gì.
2. **Xác định nguồn**: query/form dùng `@RequestParam`; JSON body dùng `@RequestBody`; path dùng `@PathVariable`; header dùng `@RequestHeader`. Việc thiếu ở mỗi nguồn dẫn đến khác nhau.
3. **Phân biệt hai bước**: “có field/parameter trong request” và “giá trị còn lại sau conversion/deserialization”. Khi convert chuỗi rỗng thành null, thông tin đã biến mất.
4. **Kiểm tra default và binder**: `defaultValue` gộp missing/empty; `StringTrimmerEditor` hoặc `@InitBinder` có thể đổi `""` hay chuỗi khoảng trắng thành null; custom Jackson coercion có thể đổi giá trị JSON.
5. **Nhìn status 400 và exception cụ thể**: `MissingServletRequestParameterException` thường là thiếu required param; lỗi chuyển kiểu có thể là `MethodArgumentTypeMismatchException`; lỗi JSON parse thường liên quan `HttpMessageNotReadableException`; validation DTO thường là `MethodArgumentNotValidException`. Handler tùy chỉnh có thể đổi body/status.
6. **Không lạm dụng primitive**: `int age` có thể không thể hiện null; dùng `Integer` + `@NotNull` khi thực sự cần kiểm tra bắt buộc, đồng thời lưu ý Jackson coercion.
7. **Không coi Optional là bộ xác thực**: Optional thể hiện presence sau binding, vẫn phải validate dữ liệu bên trong.
8. **Không coi empty là null theo mặc định**: chuỗi `""`, chuỗi trắng, `[]`, `{}`, `null` và field vắng mặt là các trường hợp khác nhau. Chỉ chuẩn hóa khi hợp đồng nghiệp vụ cho phép.
9. **Không đưa giá trị null vào `Map.of`**: Java `Map.of` không chấp nhận null key/value; nếu cần response chứa field null, dùng DTO/record (như demo) hoặc `LinkedHashMap`/`HashMap` hỗ trợ null.
10. **Kiểm thử theo ma trận rõ ràng**: ít nhất missing, empty, blank, null (nếu JSON), valid, malformed và multi-value (nếu query cho phép lặp). Kiểm tra trạng thái trả về lẫn tác dụng nghiệp vụ.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** `@RequestParam(required=false) String q` nhận gì khi không có `q` và khi `?q=`?

**Đáp án:** Với binder mặc định: `null` khi thiếu; `""` khi có tham số nhưng không có ký tự.

**Câu 2.** `@RequestParam(defaultValue="all")` có giữ được khác biệt giữa thiếu và chuỗi rỗng không?

**Đáp án:** Không. Cả hai thường nhận `"all"`.

**Câu 3.** `Optional<Integer> count` có biến `?count=abc` thành `Optional.empty()` không?

**Đáp án:** Không. Chuỗi không phải số thường gây lỗi conversion HTTP 400; Optional chỉ đại diện thiếu giá trị hợp lệ sau binding.

**Câu 4.** `record Patch(String name)` có phân biệt JSON `{}` và `{"name":null}` không?

**Đáp án:** Với deserialization thông thường, không: `name` đều null. Dùng `JsonNode` hoặc cơ chế theo dõi field hiện diện.

**Câu 5.** `@NotNull String name` có từ chối chuỗi `""` hoặc `"   "` không?

**Đáp án:** Không. Dùng `@NotBlank` nếu muốn từ chối null, empty và chỉ-khoảng-trắng.

**Câu 6.** Nếu mapping `/items/{id}` không có đường dẫn `/items`, `@PathVariable(required=false)` có bảo đảm GET `/items` chạy method không?

**Đáp án:** Không. URL phải khớp mapping trước khi method parameter được resolve; hãy khai báo đường dẫn `/items` riêng hoặc mapping hỗ trợ cả hai.

## Tài liệu tham khảo

- Spring Framework — `@RequestParam`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html
- Spring Framework — Controller Method Arguments và `Optional`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html
- Spring Framework — Type Conversion (empty String → null sau conversion): https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/typeconversion.html
- Spring Framework — `@RequestBody` và Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring Framework — `@ModelAttribute`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework — `@RequestHeader`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestheader.html
- Jackson Databind `JsonNode` API: https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/JsonNode.html
- Jakarta Bean Validation `@NotNull`, `@NotBlank`, `@NotEmpty`: https://jakarta.ee/specifications/bean-validation/
- JSON Merge Patch (RFC 7396): https://www.rfc-editor.org/rfc/rfc7396
