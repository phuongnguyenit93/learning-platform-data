# Mô tả `@RequestHeader` và `@CookieValue`

REST API thường nhận dữ liệu ngoài path và query parameter. Client còn có thể gửi thông tin trong HTTP header hoặc cookie. Trong Spring MVC, `@RequestHeader` đọc một header của request và `@CookieValue` đọc một cookie theo tên. Springdoc nhận biết hai annotation này để tạo parameter tương ứng trong đặc tả OpenAPI; `@Parameter` giúp bổ sung mô tả, ví dụ và các thông tin mà kiểu Java chưa thể hiện.

Hai loại dữ liệu này có vai trò khác nhau. Header thường mang metadata của request như phiên bản client, ngôn ngữ hoặc mã tương quan. Cookie thường được trình duyệt lưu và gửi tự động theo domain, path và chính sách cookie. Khi mô tả API, cần ghi rõ tên, mục đích, tính bắt buộc và định dạng của từng giá trị để người tích hợp biết cách gửi request.

## 1. HTTP header và cookie trong một request

Một request HTTP có thể chứa method, URL, header, cookie và body. Ví dụ:

```http
GET /api/preferences HTTP/1.1
Host: api.example.com
X-Client-Version: 2.4.0
Accept-Language: vi
Cookie: theme=dark; locale=vi
Accept: application/json
```

Trong ví dụ:

- `X-Client-Version` là header tùy chỉnh do ứng dụng quy định.
- `Accept-Language` là header tiêu chuẩn biểu thị ngôn ngữ client ưu tiên.
- `theme` và `locale` là các cookie được gửi trong header `Cookie` của HTTP request.
- `Accept` mô tả định dạng response mà client có thể nhận.

Header field name không phân biệt chữ hoa và chữ thường theo HTTP. Vì vậy `X-Client-Version` và `x-client-version` là cùng một tên header. Tuy nhiên, nhóm phát triển nên thống nhất cách viết trong tài liệu để người đọc dễ nhận diện.

Cookie không phải một loại header parameter thông thường trong hợp đồng OpenAPI. Khi biểu diễn theo OpenAPI 3, cookie parameter có vị trí `in: cookie`; Springdoc có thể suy ra vị trí này từ `@CookieValue`.

## 2. Đọc header bằng `@RequestHeader`

`@RequestHeader` của Spring MVC liên kết một tham số method với giá trị header trong HTTP request. Có thể chỉ định tên header bằng thuộc tính `name` hoặc `value`:

```java
@GetMapping("/client-info")
public String getClientInfo(
        @RequestHeader(name = "X-Client-Version") String clientVersion) {
    return "Client version: " + clientVersion;
}
```

Nếu không chỉ định `required`, Spring mặc định coi header là bắt buộc. Khi request thiếu header, Spring MVC thường trả về lỗi `400 Bad Request` do không thể bind tham số bắt buộc.

### Header tùy chọn

Để header không bắt buộc, đặt `required = false` và xử lý trường hợp không có giá trị:

```java
@GetMapping("/client-info")
public String getClientInfo(
        @RequestHeader(name = "X-Client-Version", required = false)
        String clientVersion) {

    String effectiveVersion = clientVersion == null
        ? "unknown"
        : clientVersion;

    return "Client version: " + effectiveVersion;
}
```

Khi header không được gửi, giá trị tham số có thể là `null`. Nếu có logic mặc định, hãy thể hiện rõ trong code và trong mô tả API để client hiểu hành vi khi bỏ qua header.

### Header có giá trị mặc định

Spring cho phép khai báo `defaultValue`:

```java
@GetMapping("/client-info")
public String getClientInfo(
        @RequestHeader(
            name = "X-Client-Version",
            defaultValue = "unknown"
        ) String clientVersion) {
    return "Client version: " + clientVersion;
}
```

Khi đặt `defaultValue`, Spring tự coi tham số là không bắt buộc. Nếu header vắng mặt hoặc có giá trị rỗng, Spring sử dụng giá trị mặc định. Khi tài liệu được sinh ra, hãy kiểm tra cả `required` và `schema.default` trong OpenAPI JSON vì chi tiết thể hiện có thể phụ thuộc phiên bản Springdoc.

## 3. Mô tả header bằng `@Parameter`

Springdoc thường suy ra tên, vị trí và tính bắt buộc từ `@RequestHeader`. Dùng `@Parameter` để bổ sung thông tin dành cho người đọc tài liệu:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;

@GetMapping("/api/client-settings")
@Operation(summary = "Lấy cấu hình dành cho client")
public String getClientSettings(
        @Parameter(
            description = "Phiên bản ứng dụng client đang sử dụng",
            example = "2.4.0"
        )
        @RequestHeader(name = "X-Client-Version", required = false)
        String clientVersion) {
    return clientVersion == null ? "default settings" : clientVersion;
}
```

`description` giải thích ý nghĩa header; `example` cho thấy một giá trị hợp lệ. Với header có định dạng cụ thể, nên mô tả thêm quy tắc như phiên bản theo SemVer, mã tenant, ngôn ngữ BCP 47 hoặc mã trace theo quy ước nội bộ.

Nếu cần tùy chỉnh sâu hơn, `@Parameter` hỗ trợ các thuộc tính như `name`, `required`, `deprecated`, `allowEmptyValue`, `schema`, `example` và `examples`. Không nên khai báo `required` mâu thuẫn với `@RequestHeader(required = ...)`; Spring annotation vẫn quyết định cách Spring MVC bind request, còn metadata OpenAPI cần phản ánh cùng hành vi đó.

### Header nhiều giá trị

Một số header có thể mang nhiều giá trị hoặc xuất hiện nhiều lần. Có thể dùng kiểu collection phù hợp để nhận các giá trị đó, tùy cách Spring MVC chuyển đổi header:

```java
@GetMapping("/api/search")
public String search(
        @RequestHeader(name = "X-Feature", required = false)
        List<String> features) {
    return String.valueOf(features);
}
```

Nếu hợp đồng cho phép nhiều giá trị, hãy kiểm tra schema và cách serialize parameter mà Springdoc sinh ra. Cần thống nhất client gửi nhiều giá trị bằng cách lặp header hay dùng cú pháp phân tách theo dấu phẩy, vì cách biểu diễn phụ thuộc định nghĩa của từng header.

## 4. Đọc cookie bằng `@CookieValue`

`@CookieValue` liên kết một tham số method với cookie có tên cụ thể. Ví dụ đọc cookie `theme`:

```java
@GetMapping("/api/preferences/theme")
public String getTheme(
        @CookieValue(name = "theme") String theme) {
    return "Current theme: " + theme;
}
```

Nếu cookie `theme` không có trong request, Spring mặc định coi cookie là bắt buộc và việc bind có thể thất bại với `400 Bad Request`.

### Cookie tùy chọn

Cookie thường được tạo sau khi người dùng truy cập lần đầu, nên API có thể cần chấp nhận trường hợp cookie chưa tồn tại:

```java
@GetMapping("/api/preferences/theme")
public String getTheme(
        @CookieValue(name = "theme", required = false) String theme) {

    String effectiveTheme = theme == null ? "light" : theme;
    return "Current theme: " + effectiveTheme;
}
```

Trong trường hợp này, `theme` là cookie tùy chọn và ứng dụng dùng `light` khi client chưa có cookie. Cần mô tả giá trị mặc định trong tài liệu để người tích hợp hiểu kết quả.

### Cookie có giá trị mặc định

Có thể dùng `defaultValue` tương tự `@RequestHeader`:

```java
@GetMapping("/api/preferences/locale")
public String getLocale(
        @CookieValue(name = "locale", defaultValue = "vi") String locale) {
    return locale;
}
```

Khi cookie vắng mặt hoặc rỗng, Spring dùng giá trị `vi`. Việc đặt `defaultValue` cũng làm cookie trở thành tùy chọn trong quá trình bind.

## 5. Mô tả cookie bằng `@Parameter`

Springdoc nhận biết `@CookieValue` để tạo cookie parameter. Có thể bổ sung mô tả và ví dụ như sau:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping("/api/preferences")
@Operation(summary = "Đọc tùy chọn giao diện")
public String getPreferences(
        @Parameter(
            description = "Cookie lưu chủ đề giao diện người dùng",
            example = "dark"
        )
        @CookieValue(name = "theme", required = false)
        String theme) {
    return theme == null ? "light" : theme;
}
```

Trong tài liệu OpenAPI 3, parameter tương ứng có dạng khái quát:

```yaml
parameters:
  - name: theme
    in: cookie
    required: false
    description: Cookie lưu chủ đề giao diện người dùng
    schema:
      type: string
    example: dark
```

`in: cookie` phân biệt cookie với header parameter có `in: header`. Không tự khai báo một header tên `Cookie` để thay cho `@CookieValue`; Spring MVC đã cung cấp abstraction đọc cookie theo tên.

## 6. Ví dụ kết hợp header và cookie trong một controller

Ví dụ sau mô tả một endpoint trả về tùy chọn hiển thị của client. Phiên bản client và ngôn ngữ được gửi qua header; chủ đề giao diện được lưu trong cookie:

```java
package com.example.preferences;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/preferences")
@Tag(name = "Preferences", description = "Tùy chọn hiển thị của client")
public class PreferenceController {

    @GetMapping
    @Operation(summary = "Lấy tùy chọn hiển thị")
    public PreferenceResponse getPreferences(
            @Parameter(
                description = "Phiên bản ứng dụng client",
                example = "2.4.0"
            )
            @RequestHeader(name = "X-Client-Version", required = false)
            String clientVersion,

            @Parameter(
                description = "Ngôn ngữ ưu tiên của client",
                example = "vi"
            )
            @RequestHeader(name = "Accept-Language", required = false)
            String acceptLanguage,

            @Parameter(
                description = "Cookie lưu chủ đề giao diện",
                example = "dark"
            )
            @CookieValue(name = "theme", required = false)
            String theme) {

        return new PreferenceResponse(
            clientVersion == null ? "unknown" : clientVersion,
            acceptLanguage == null ? "vi" : acceptLanguage,
            theme == null ? "light" : theme
        );
    }

    public record PreferenceResponse(
        String clientVersion,
        String language,
        String theme
    ) {}
}
```

Request minh họa bằng curl:

```bash
curl -i http://localhost:8080/api/preferences \
  -H "X-Client-Version: 2.4.0" \
  -H "Accept-Language: vi" \
  --cookie "theme=dark"
```

Response có thể như sau:

```json
{
  "clientVersion": "2.4.0",
  "language": "vi",
  "theme": "dark"
}
```

Khi bỏ header hoặc cookie tùy chọn, controller sử dụng giá trị fallback đã viết trong code. Tài liệu OpenAPI nên thể hiện đúng tính tùy chọn và giải thích hành vi fallback này.

## 7. Những header không nên mô tả như parameter thông thường

Không phải header nào cũng nên khai báo bằng `@RequestHeader` để Springdoc đưa vào danh sách parameter.

- **`Authorization`:** nếu header dùng cho Bearer token, OAuth2 hoặc API key, nên mô tả bằng `@SecurityScheme` và `@SecurityRequirement`. Cách này tạo đúng mô hình bảo mật trong OpenAPI và hỗ trợ nút Authorize của Swagger UI.
- **`Accept`:** thường được thể hiện qua các media type response (`responses.content`) và cơ chế content negotiation.
- **`Content-Type`:** thường được thể hiện qua media type của request body (`requestBody.content`).
- **`Cookie`:** là header tổng hợp chứa các cookie request; nếu muốn mô tả một cookie theo tên, dùng `@CookieValue` để thể hiện `in: cookie`.
- **`Set-Cookie`:** là response header dùng để gửi cookie về trình duyệt; nó không phải input parameter và không được đọc bằng `@CookieValue`.

OpenAPI quy định cách xử lý riêng đối với một số header như `Accept`, `Content-Type` và `Authorization` khi chúng được khai báo dưới dạng header parameter. Vì vậy, hãy dùng cấu trúc OpenAPI đúng với ý nghĩa của header thay vì mô tả mọi thứ như một chuỗi tùy ý.

## 8. Phân biệt cookie request với việc tạo cookie response

`@CookieValue` chỉ đọc cookie client đã gửi lên. Nếu server cần tạo hoặc cập nhật cookie, server phải gửi response header `Set-Cookie`. Ví dụ:

```java
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;

@PostMapping("/api/preferences/theme")
public ResponseEntity<Void> saveTheme() {
    ResponseCookie cookie = ResponseCookie.from("theme", "dark")
        .httpOnly(true)
        .secure(true)
        .sameSite("Lax")
        .path("/")
        .maxAge(60 * 60 * 24 * 30)
        .build();

    return ResponseEntity.noContent()
        .header(HttpHeaders.SET_COOKIE, cookie.toString())
        .build();
}
```

`HttpOnly`, `Secure`, `SameSite`, `Path`, `Domain` và thời hạn cookie là các thuộc tính ảnh hưởng đến cách trình duyệt lưu và gửi cookie. Chọn giá trị phù hợp với yêu cầu bảo mật và phạm vi sử dụng. Ví dụ trên minh họa cách gửi cookie; giá trị và chính sách thực tế cần được xác định theo ứng dụng.

Đối với cookie phiên đăng nhập, không đưa giá trị session hoặc token thật vào ví dụ OpenAPI. Nếu cookie đóng vai trò xác thực, hãy mô tả nó bằng security scheme kiểu API key với vị trí `cookie` khi phù hợp với hợp đồng, đồng thời triển khai bảo mật thật ở server.

## 9. Lưu ý khi dùng cookie từ trình duyệt và CORS

Trình duyệt tự quản lý cookie dựa trên domain, path, thời hạn, `Secure`, `SameSite` và các chính sách quyền riêng tư. JavaScript không được tự đặt header `Cookie` trong `fetch`; trình duyệt quyết định cookie nào được gửi.

Khi gọi API khác origin, cần chú ý:

- Request phía trình duyệt phải bật chế độ gửi credentials, ví dụ `credentials: "include"` với Fetch khi phù hợp.
- Server phải cấu hình CORS cho phép credentials và khai báo origin cụ thể; không dùng wildcard `*` cùng `Access-Control-Allow-Credentials: true`.
- Cookie cross-site thường cần `SameSite=None; Secure`; chính sách trình duyệt có thể tiếp tục giới hạn cookie bên thứ ba.
- Cookie `HttpOnly` vẫn được trình duyệt gửi tự động khi đủ điều kiện, nhưng JavaScript không đọc được giá trị cookie đó.

Swagger UI có thể hiển thị cookie parameter trong tài liệu, nhưng khả năng nhập và gửi cookie khi bấm **Try it out** còn phụ thuộc phiên bản Swagger UI, origin và chính sách trình duyệt. Với cookie được trình duyệt quản lý, hãy kiểm tra request thực tế trong Network thay vì giả định UI có thể ghi đè header `Cookie`.

## 10. Cách kiểm tra OpenAPI do Springdoc sinh ra

Sau khi khởi chạy ứng dụng, mở `/v3/api-docs` và tìm operation tương ứng. Header và cookie thường được biểu diễn như sau:

```json
{
  "parameters": [
    {
      "name": "X-Client-Version",
      "in": "header",
      "required": false,
      "schema": {
        "type": "string"
      },
      "example": "2.4.0"
    },
    {
      "name": "theme",
      "in": "cookie",
      "required": false,
      "schema": {
        "type": "string"
      },
      "example": "dark"
    }
  ]
}
```

Đây là đoạn trích minh họa, không phải toàn bộ tài liệu của một ứng dụng. Khi kiểm tra, xác nhận:

1. Tên parameter khớp chính xác với `name` trong `@RequestHeader` hoặc `@CookieValue`.
2. Header có `in: header`; cookie có `in: cookie`.
3. `required` phản ánh `required` và `defaultValue` của Spring annotation.
4. Description, example và schema thể hiện đúng định dạng giá trị.
5. Các operation vẫn có response và schema đúng.

Swagger UI có thể trình bày các parameter này trong phần Parameters. Hãy thử request với giá trị hợp lệ và request thiếu các parameter tùy chọn để xác minh hành vi server. Đối với cookie, kiểm tra tab Network để biết trình duyệt thực sự gửi cookie nào.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Request thiếu header trả về `400` | `@RequestHeader` đang để `required = true` | Đặt `required = false` hoặc gửi header bắt buộc |
| Request thiếu cookie trả về `400` | `@CookieValue` đang để `required = true` | Đặt `required = false` hoặc cấu hình `defaultValue` |
| Parameter không xuất hiện trong OpenAPI | Controller chưa được Spring quét, mapping không hợp lệ hoặc annotation không được Springdoc nhận diện | Kiểm tra controller và `/v3/api-docs` |
| Cookie xuất hiện như header thay vì cookie | Khai báo nhầm `@RequestHeader("Cookie")` | Dùng `@CookieValue(name = "...")` |
| Mô tả hoặc ví dụ không đúng | `@Parameter` thiếu hoặc có metadata mâu thuẫn | Kiểm tra annotation và JSON OpenAPI được sinh ra |
| Browser không gửi cookie | Domain, path, SameSite, Secure, credentials hoặc CORS không phù hợp | Kiểm tra thuộc tính cookie và request trong Network |
| Cookie không được tạo sau khi gọi API | Đang dùng `@CookieValue` để kỳ vọng server ghi cookie | Trả response header `Set-Cookie` |
| Token không hiển thị nút Authorize | Token được mô tả như header parameter thông thường | Khai báo security scheme và security requirement |

## 12. Checklist mô tả header và cookie

- [ ] Mỗi header được khai báo bằng `@RequestHeader` với tên rõ ràng.
- [ ] Mỗi cookie đầu vào được đọc bằng `@CookieValue` theo đúng tên cookie.
- [ ] `required` phản ánh đúng hành vi khi thiếu giá trị.
- [ ] `defaultValue` và logic fallback được mô tả rõ.
- [ ] `@Parameter` có description và example hữu ích.
- [ ] Không mô tả `Authorization`, `Accept` hoặc `Content-Type` như parameter tùy ý khi OpenAPI có cấu trúc chuyên biệt.
- [ ] Cookie xác thực được mô tả bằng security scheme phù hợp và không đưa bí mật vào ví dụ.
- [ ] Cookie response được gửi bằng `Set-Cookie` với thuộc tính phù hợp.
- [ ] Đã kiểm tra `in: header` và `in: cookie` trong `/v3/api-docs`.
- [ ] Đã thử request thực tế, bao gồm trường hợp thiếu header/cookie tùy chọn và trường hợp CORS nếu gọi từ browser.

`@RequestHeader` và `@CookieValue` giúp controller nhận metadata và trạng thái phía client theo đúng cơ chế HTTP. Springdoc chuyển các khai báo đó thành header/cookie parameter trong OpenAPI, còn `@Parameter` làm rõ cách sử dụng. Khi tài liệu phản ánh đúng tính bắt buộc, ví dụ và chính sách cookie, client có thể tích hợp API dễ dàng và tránh nhầm lẫn giữa header, cookie đầu vào, cookie response và thông tin xác thực.
