# Xác định giá trị mặc định và thời điểm áp dụng trong đối tượng đầu vào Spring

## 1. Giá trị mặc định là gì và vì sao “thời điểm” quan trọng?

Trong Spring Framework, **giá trị mặc định** (*default value*) là giá trị hệ thống chọn cho một trường hoặc tham số khi phía gọi không cung cấp giá trị theo một quy ước đã xác định. Đây là một phần của **hợp đồng đầu vào**, không đơn thuần là cách tránh `null`.

Ví dụ API tìm kiếm cho phép client bỏ qua `limit`; ứng dụng chọn mặc định `20`. Cần trả lời đồng thời:

1. **Giá trị nào được mặc định?** `limit=20`, `sort=newest`, `notificationsEnabled=true`...
2. **Điều kiện nào kích hoạt mặc định?** Tham số không xuất hiện, chuỗi rỗng, JSON property không xuất hiện, JSON `null` hay giá trị không hợp lệ?
3. **Ai quyết định?** Spring argument resolver, Java constructor/field initializer, Jackson, application service hay cơ sở dữ liệu?
4. **Áp dụng vào lúc nào?** Trước chuyển kiểu, khi tạo đối tượng, trong data binding, sau validation, khi xử lý nghiệp vụ hay khi ghi xuống DB?
5. **Giá trị mặc định có qua validation không?** Giá trị mặc định sai cũng là dữ liệu đầu vào của use case và cần tuân theo các ràng buộc tương ứng.

Nếu không phân biệt các bước này, API có thể lặng lẽ biến giá trị client cố tình gửi thành mặc định, kiểm tra dữ liệu sai thời điểm hoặc để những lối vào khác (job/message consumer) có hành vi không nhất quán.

## 2. Phân biệt “thiếu”, “rỗng”, “null”, “0” và “false”

Các trạng thái sau không có cùng ý nghĩa:

| Tình huống | Ví dụ | Ý nghĩa thông thường |
| --- | --- | --- |
| Không gửi tham số URL | `GET /items` | `limit` **vắng mặt** |
| Gửi tham số URL không có nội dung | `GET /items?limit=` | `limit` **có mặt nhưng rỗng** |
| Gửi khoảng trắng | `GET /items?sort=%20` | Có giá trị chứa khoảng trắng; xử lý còn tùy binder/converter |
| Giá trị số 0 | `GET /items?limit=0` | Client đã cung cấp số `0`; không đồng nghĩa với thiếu |
| Giá trị boolean false | `{"notificationsEnabled":false}` | Client chọn `false` rõ ràng |
| Property JSON vắng mặt | `{}` | Chưa cung cấp thuộc tính đó |
| Property JSON là null | `{"notificationsEnabled":null}` | Client gửi `null` tường minh |
| Chuỗi JSON rỗng | `{"locale":""}` | Chuỗi rỗng, không phải JSON `null` |
| JSON sai kiểu hoặc cú pháp | `{"limit":"abc"}` khi DTO yêu cầu số | Lỗi đọc/chuyển đổi, không nên tự đổi thành mặc định |

**Quy tắc an toàn:** đừng dùng biểu thức kiểu “nếu false, 0 hoặc chuỗi rỗng thì lấy default” một cách chung chung. `false` và `0` có thể là lựa chọn hợp lệ của client. Với thao tác cập nhật một phần (*PATCH*), “không gửi” còn có thể mang nghĩa “giữ nguyên”, khác hẳn “khôi phục về mặc định”.

## 3. Bản đồ cơ chế mặc định trong Spring

| Cơ chế | Dùng cho | Khi nào áp dụng | Lưu ý chính |
| --- | --- | --- | --- |
| `@RequestParam(defaultValue = "...")` | Tham số query/form được resolve trực tiếp thành method argument | Khi Spring giải quyết tham số controller, trước khi gọi method | Áp dụng khi thiếu hoặc có giá trị rỗng; mặc định là chuỗi rồi mới được chuyển sang kiểu đích |
| `@RequestHeader(defaultValue = "...")`, `@CookieValue(defaultValue = "...")` | Header/cookie được resolve vào tham số | Trong bước argument resolution tương ứng | Phụ thuộc chính nguồn input; không áp dụng cho trường JSON |
| Field initializer hoặc constructor của JavaBean | `@ModelAttribute` và đối tượng Java | Khi đối tượng được tạo, **trước** khi binder gán dữ liệu được gửi | Trường được bind có thể ghi đè mặc định, kể cả bằng chuỗi rỗng hoặc `null` sau conversion |
| Field initializer / constructor khi Jackson tạo DTO | `@RequestBody` JSON | Khi Jackson khởi tạo object, trước khi điền property JSON | Property thiếu thường giữ giá trị ban đầu; property `null` thường ghi đè bằng `null` |
| Constructor/normalization của immutable DTO | Record, DTO bất biến | Lúc constructor được gọi trong deserialization/binding | Phải viết quy tắc mặc định chủ động; cần quyết định riêng ý nghĩa của thiếu so với `null` |
| Application/domain service | Mặc định phụ thuộc use case, cấu hình, user, thời gian | Sau khi nhận dữ liệu, tại điểm thực hiện chính sách | Cần kiểm tra giá trị kết quả và thống nhất giữa HTTP/job/message |
| `DEFAULT` trong SQL schema | Cột database | Khi DB thực thi `INSERT` phù hợp | Không tự thêm giá trị vào request DTO; thường chỉ có tác dụng nếu cột bị bỏ khỏi lệnh `INSERT` |

**Không có một cơ chế “default” toàn cục của Spring** tự áp dụng như nhau cho query parameter, form object, JSON body, record và database.

## 4. Luồng thời điểm: trước, trong và sau data binding

Với một request HTTP điển hình:

```text
Request đến
  |
  +--> Đọc nguồn dữ liệu (query/form/JSON/header)
  |
  +--> Khởi tạo đối tượng hoặc resolve tham số
  |       - Java field initializer / constructor default
  |       - @RequestParam defaultValue nếu thiếu/rỗng
  |
  +--> Data binding / deserialization / type conversion
  |       - Giá trị có mặt có thể ghi đè field initializer
  |       - Sai kiểu có thể bị từ chối ngay ở bước này
  |
  +--> Bean Validation (khi được kích hoạt)
  |       - Kiểm tra giá trị CUỐI CÙNG sau khi bind/default
  |
  +--> Controller -> application/domain service
  |       - Xác định mặc định phụ thuộc chính sách/ngữ cảnh
  |       - Kiểm tra bất biến nghiệp vụ sau khi đã quyết định giá trị
  |
  +--> Repository/SQL -> database
          - DB default/constraints/transaction
```

Đây là sơ đồ khái niệm; đường đi chính xác khác nhau giữa `@RequestParam`, `@ModelAttribute` và `@RequestBody`. Những điều chắc chắn cần ghi nhớ:

- **Java field initializer chạy khi object được khởi tạo**. Nó không “chạy lại” sau khi một setter hay Jackson đã ghi đè property.
- **Spring binding không tự coi mọi input không hợp lệ là thiếu.** `limit=abc` phải được xử lý như lỗi chuyển kiểu thay vì biến thành `limit=20`.
- **Bean Validation không tự sinh giá trị mặc định.** `@NotNull`, `@NotBlank`, `@Min` hoặc `@Valid` chỉ kiểm tra; chúng không chọn giá trị mới.
- **Default của nghiệp vụ phải được quyết định trước bước kiểm tra những bất biến nghiệp vụ cần đến nó.** Nếu chính sách cần biết user/tenant/time, constructor của DTO thường không đủ ngữ cảnh.

## 5. Tham số trực tiếp: `@RequestParam(defaultValue)`

Ví dụ:

```java
@GetMapping("/items")
public Map<String, Object> items(
        @RequestParam(defaultValue = "20") int limit,
        @RequestParam(defaultValue = "newest") String sort) {
    return Map.of("limit", limit, "sort", sort);
}
```

Spring áp dụng `defaultValue` trong lúc resolve method argument:

| Request | `limit` | `sort` | Giải thích |
| --- | ---: | --- | --- |
| `GET /items` | `20` | `newest` | Cả hai không xuất hiện |
| `GET /items?limit=` | `20` | `newest` | `limit` xuất hiện nhưng rỗng |
| `GET /items?limit=5&sort=price` | `5` | `price` | Client ghi đè mặc định |
| `GET /items?limit=0` | `0` | `newest` | `0` là giá trị thực, cần quy tắc riêng nếu muốn từ chối |
| `GET /items?limit=abc` | Không chạy thành công | — | Chuỗi không chuyển thành `int` hợp lệ |

Đặc điểm quan trọng:

- `defaultValue` nhận một **chuỗi** trong annotation; với `int`/`long`/`enum`, Spring còn phải chuyển chuỗi đó sang kiểu đích. Nếu khai báo default không chuyển được, request cũng có thể lỗi.
- Khai báo `defaultValue` ngầm làm tham số không còn bắt buộc (`required=false`). Đừng đồng thời diễn giải `required=true` là “chắc chắn client đã gửi”.
- `@RequestParam(required = false) Integer limit` khi thiếu có thể nhận `null` để code tự quyết định. Dùng wrapper `Integer` nếu cần biểu diễn “chưa có giá trị”; tránh dựa vào primitive `int` để biểu diễn sự vắng mặt.
- Nếu nghiệp vụ yêu cầu **thiếu thì 20 nhưng gửi rỗng phải báo lỗi**, `defaultValue` không phù hợp vì cơ chế này coi chuỗi rỗng là điều kiện nhận default. Thiết kế contract/parser phân biệt sự hiện diện của tham số.
- `@RequestParam` điều khiển tham số URL/form (theo cơ chế resolver), **không gán mặc định cho trường trong JSON body**.

`@PathVariable` là dữ liệu trong route. Không dùng `@RequestParam(defaultValue)` như giải pháp cho một path segment vắng mặt; thay vào đó thiết kế route riêng hoặc tham số query tùy ý nghĩa của API.

## 6. Đối tượng `@ModelAttribute`: mặc định trước khi Spring gán property

Với form/query được bind vào JavaBean, giá trị khởi tạo của trường thường là cách rõ ràng để xác định default. Ví dụ:

```java
package demo.defaults;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class SearchForm {
    @NotNull
    @Min(1)
    @Max(100)
    private Integer limit = 20;

    @NotBlank
    private String sort = "newest";

    public SearchForm() {}

    public Integer getLimit() { return limit; }
    public void setLimit(Integer limit) { this.limit = limit; }

    public String getSort() { return sort; }
    public void setSort(String sort) { this.sort = sort; }
}
```

Ví dụ controller trong cùng project:

```java
@GetMapping("/form")
public Map<String, Object> form(
        @Valid @ModelAttribute SearchForm form) {
    return Map.of(
            "limit", form.getLimit(),
            "sort", form.getSort());
}
```

Trong trường hợp JavaBean trên, trình tự có thể hiểu như sau:

1. Spring tạo `SearchForm`; lúc này `limit=20` và `sort="newest"`.
2. Spring bind các tham số đã gửi. Nếu client gửi `limit=5`, setter nhận giá trị đã chuyển kiểu và ghi đè `20`. Nếu không gửi `limit`, field giữ `20`.
3. Bean Validation được kích hoạt bởi `@Valid` và kiểm tra **giá trị sau binding**. `limit=0` vi phạm `@Min(1)`; `sort=` vi phạm `@NotBlank`.
4. Controller chỉ được gọi theo đường đi thành công của binding/validation (trừ các cơ chế bắt và xử lý lỗi riêng như `BindingResult`).

**Điểm dễ nhầm:** `?sort=` là một giá trị đã được cung cấp, nên setter có thể thay `"newest"` bằng chuỗi rỗng rồi validation từ chối. Đó là hành vi khác `@RequestParam(defaultValue="newest")`, nơi chuỗi rỗng kích hoạt default.

Với `Integer limit`, giá trị form rỗng thường được converter chuyển thành `null`; `@NotNull` giúp phát hiện trường hợp này. `@Min` tự nó không coi `null` là vi phạm. Với `limit=abc`, binding báo lỗi kiểu dữ liệu, không giữ mặc định cũ như một đường hồi phục âm thầm.

`@ModelAttribute` cũng hỗ trợ nhiều kiểu khởi tạo và constructor binding tùy cấu trúc đối tượng. Với DTO JavaBean có constructor rỗng và setter như ví dụ, quy tắc **khởi tạo trước, bind giá trị có mặt, rồi validate** đặc biệt dễ kiểm soát. Nếu dùng constructor có tham số hoặc record, cần xác định rõ constructor nào nhận dữ liệu và khi nào mặc định được áp dụng.

## 7. JSON `@RequestBody`: Jackson và sự khác biệt giữa property thiếu và `null`

Trong Spring MVC với Jackson JSON converter, `@RequestBody` đi theo đường deserialization thay vì `@ModelAttribute` property binding. Một JavaBean request có thể đặt mặc định ban đầu:

```java
package demo.defaults;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class PreferenceRequest {
    @NotNull
    private Boolean notificationsEnabled = Boolean.TRUE;

    @NotBlank
    private String locale = "vi-VN";

    public PreferenceRequest() {}

    public Boolean getNotificationsEnabled() {
        return notificationsEnabled;
    }
    public void setNotificationsEnabled(Boolean value) {
        this.notificationsEnabled = value;
    }

    public String getLocale() { return locale; }
    public void setLocale(String locale) { this.locale = locale; }
}
```

Controller:

```java
@PostMapping("/request-body")
public Map<String, Object> requestBody(
        @Valid @RequestBody PreferenceRequest request) {
    return Map.of(
            "notificationsEnabled", request.getNotificationsEnabled(),
            "locale", request.getLocale());
}
```

Hành vi điển hình với JavaBean và cấu hình Jackson mặc định:

| JSON gửi lên | `notificationsEnabled` | `locale` | Kết quả |
| --- | --- | --- | --- |
| `{}` | `true` | `vi-VN` | Không có property nào ghi đè initializer |
| `{"notificationsEnabled":false}` | `false` | `vi-VN` | `false` được giữ nguyên |
| `{"notificationsEnabled":null}` | `null` | `vi-VN` | `@NotNull` từ chối, không tự lấy lại `true` |
| `{"locale":""}` | `true` | `""` | `@NotBlank` từ chối |
| `{"locale":"en-US"}` | `true` | `en-US` | Giá trị do client cung cấp ghi đè default |

**JSON property vắng mặt** thường không gọi setter cho property đó, nên field initializer được giữ lại. **JSON property có giá trị `null`** thường ghi đè field kiểu object thành `null`. Vì vậy, JavaBean có giá trị mặc định vẫn phải có validator và chính sách về explicit null.

Tránh dùng primitive `boolean` hoặc `int` nếu contract cần phân biệt “không gửi” và “client cố tình gửi `false`/`0`”. Chúng có giá trị mặc định theo ngôn ngữ Java ngay từ khi object được tạo; một số chuyển đổi với JSON `null` cũng có semantics riêng tùy cấu hình Jackson. Dùng wrapper `Boolean`/`Integer` hoặc thiết kế loại dữ liệu thể hiện sự hiện diện để tránh đánh mất ý nghĩa.

### Khi muốn JSON `null` cũng giữ mặc định

Nếu contract xác định cả property thiếu **và explicit null** đều có nghĩa “lấy giá trị mặc định”, Jackson hỗ trợ cho property JavaBean:

```java
import com.fasterxml.jackson.annotation.JsonSetter;
import com.fasterxml.jackson.annotation.Nulls;

@JsonSetter(nulls = Nulls.SKIP)
private Boolean notificationsEnabled = Boolean.TRUE;
```

Với cách này, Jackson có thể bỏ qua lần gán `null` cho property đó, để giá trị khởi tạo còn nguyên. Chỉ dùng khi **đã quyết định rõ semantics của null**; nếu client gửi null phải bị từ chối, giữ `@NotNull` mà không cấu hình `Nulls.SKIP` như ví dụ trước.

Lưu ý các annotation dễ bị hiểu nhầm:

- `@JsonProperty(defaultValue = "...")` của Jackson cung cấp metadata về giá trị mặc định, **không tự động bắt Jackson gán giá trị đó khi property thiếu** trong cơ chế databinding tiêu chuẩn.
- `@Schema(defaultValue = "...")` dùng để mô tả hợp đồng OpenAPI; nó **không tự thực thi** default khi nhận request.
- Annotation validation như `@NotNull`, `@Min`, `@Size` không có chức năng tự điền default.
- `@RequestParam(defaultValue)` không áp dụng vào các field trong `@RequestBody`.

## 8. Ví dụ Spring Boot 3.x có thể chạy

Để chạy ví dụ Java 17 ở trên, tạo một Spring Boot 3.x project có dependencies **Spring Web** và **Validation**, rồi đặt những lớp sau trong package `demo.defaults`:

- `DefaultsApplication.java`: lớp khởi động ở dưới.
- `DefaultsController.java`: controller ở dưới.
- `SearchForm.java` và `PreferenceRequest.java`: giữ nguyên hai lớp đã trình bày ở phần 6–7.

```java
// src/main/java/demo/defaults/DefaultsApplication.java
package demo.defaults;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DefaultsApplication {
    public static void main(String[] args) {
        SpringApplication.run(DefaultsApplication.class, args);
    }
}
```

```java
// src/main/java/demo/defaults/DefaultsController.java
package demo.defaults;

import jakarta.validation.Valid;
import java.util.Map;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/demo")
public class DefaultsController {

    @GetMapping("/items")
    public Map<String, Object> items(
            @RequestParam(defaultValue = "20") int limit,
            @RequestParam(defaultValue = "newest") String sort) {
        return Map.of("limit", limit, "sort", sort);
    }

    @GetMapping("/form")
    public Map<String, Object> form(
            @Valid @ModelAttribute SearchForm form) {
        return Map.of(
                "limit", form.getLimit(),
                "sort", form.getSort());
    }

    @PostMapping("/request-body")
    public Map<String, Object> requestBody(
            @Valid @RequestBody PreferenceRequest request) {
        return Map.of(
                "notificationsEnabled", request.getNotificationsEnabled(),
                "locale", request.getLocale());
    }
}
```

Chạy project bằng Maven wrapper (giả sử dự án đã tạo cấu hình Maven từ Spring Initializr):

```bash
./mvnw spring-boot:run
```

Trên Windows Command Prompt/PowerShell, dùng `mvnw.cmd spring-boot:run`.

Các lệnh thử:

```bash
curl "http://localhost:8080/demo/items"
curl "http://localhost:8080/demo/items?limit=&sort="
curl "http://localhost:8080/demo/form"
curl "http://localhost:8080/demo/form?limit=0"
curl -X POST "http://localhost:8080/demo/request-body" -H "Content-Type: application/json" -d '{}'
curl -X POST "http://localhost:8080/demo/request-body" -H "Content-Type: application/json" -d '{"notificationsEnabled":null}'
```

Kết quả mong đợi:

- Hai request `/demo/items` đầu trả JSON có `limit: 20` và `sort: "newest"`.
- `/demo/form` không truyền tham số trả giá trị `20` và `"newest"` từ initializer của JavaBean.
- `/demo/form?limit=0` bị validation từ chối với lỗi HTTP 400 trong cấu hình MVC thông thường.
- POST `{}` trả JSON có `notificationsEnabled: true` và `locale: "vi-VN"`.
- POST explicit `null` cho `notificationsEnabled` bị `@NotNull` từ chối, thường là HTTP 400.

Thứ tự property JSON và định dạng response lỗi phụ thuộc serializer/Spring Boot error handling, nên **đừng viết test so sánh nguyên chuỗi JSON theo thứ tự property**. Test các giá trị và HTTP status thay vì ràng buộc message lỗi mặc định của framework.

### Ví dụ Java thuần minh họa thứ tự khởi tạo và ghi đè

Nếu chỉ muốn kiểm tra cơ chế JavaBean mà không chạy Spring, lưu thành `DefaultsTimingDemo.java`:

```java
public class DefaultsTimingDemo {
    static class Filter {
        String sort = "newest";

        void setSort(String value) {
            sort = value;
        }
    }

    public static void main(String[] args) {
        Filter missing = new Filter();

        Filter empty = new Filter();
        empty.setSort("");

        Filter explicitNull = new Filter();
        explicitNull.setSort(null);

        System.out.println("missing = " + missing.sort);
        System.out.println("empty = '" + empty.sort + "'");
        System.out.println("explicit null = " + explicitNull.sort);
    }
}
```

Chạy với JDK 17+:

```bash
javac DefaultsTimingDemo.java
java DefaultsTimingDemo
```

Stdout chính xác:

```text
missing = newest
empty = ''
explicit null = null
```

Đoạn này minh họa Java initializer và setter; Spring MVC/Jackson sẽ quyết định **khi nào setter được gọi và giá trị nào được truyền**.

## 9. Thời điểm mặc định hóa so với validation

Giả sử `limit` cần nằm trong khoảng 1–100, mặc định 20. Có ba quyết định khác nhau:

1. **Chọn default trước khi validate:** với `@ModelAttribute SearchForm` có initializer `20`, validation cuối cùng thấy `20` nếu field thiếu; nếu client gửi `0`, validation thấy `0` và từ chối.
2. **Không chữa dữ liệu sai bằng default:** nếu `limit=abc` lỗi chuyển kiểu, trả lỗi. Nếu `limit=0` vi phạm nghiệp vụ/constraint, trả lỗi. Việc âm thầm đổi chúng thành `20` che giấu sai sót từ client.
3. **Dùng default sau bước nhận DTO khi cần ngữ cảnh:** ví dụ giới hạn mặc định thay đổi theo gói dịch vụ, tenant hoặc cấu hình runtime. DTO chỉ nhận ý định “không chỉ định”, service dùng policy/config để chọn, **sau đó kiểm tra giá trị đã được chọn** theo bất biến nghiệp vụ.

Không được dựa vào validation để nhận diện sự vắng mặt nếu trước đó đã gán default. Khi JavaBean đã được khởi tạo `limit=20`, một validator `@NotNull` không còn biết client có thực sự cung cấp giá trị hay không. Nếu cần audit “client đã gửi limit hay hệ thống tự chọn”, phải lưu dấu hiệu presence riêng trước/bên cạnh defaulting.

Khi dùng wrapper kiểu nullable:

```java
Integer effectiveLimit =
        requestedLimit != null ? requestedLimit : 20;
```

Biểu thức trên giữ `0` nếu client chọn `0`, còn ràng buộc `1..100` phải kiểm tra ở bước kế tiếp. Ngược lại, kiểm tra `requestedLimit == 0` như dấu hiệu thiếu sẽ làm mất một trường hợp đầu vào thực sự cần được xử lý.

## 10. Mặc định động, thời gian và quyền phải đặt ở đúng tầng

Không phải default nào cũng là hằng số. Ví dụ:

- `pageSize` mặc định dựa trên tier của user.
- `currency` mặc định dựa trên market/tenant.
- `createdAt` lấy thời điểm server tạo đối tượng.
- `ownerId` lấy từ danh tính đã xác thực.
- `status` của đơn mới luôn là `PENDING` theo workflow.

Các giá trị phụ thuộc **ngữ cảnh nghiệp vụ hoặc quyền truy cập** nên được quyết định tại service/domain, thay vì để client điều khiển trực tiếp hoặc chèn một mặc định tĩnh vào DTO.

Ví dụ khái niệm:

```java
// Đoạn service minh họa: tierPolicy và clock là dependency đã inject.
int effectiveLimit = requestedLimit != null
        ? requestedLimit
        : tierPolicy.defaultPageSizeFor(currentUser);

if (effectiveLimit < 1 || effectiveLimit > tierPolicy.maxPageSizeFor(currentUser)) {
    throw new IllegalArgumentException("Invalid page size");
}

java.time.Instant createdAt = clock.instant();
```

Với thời gian, lựa chọn **thời điểm** là một phần của yêu cầu:

- `Instant.now()` ở field initializer chạy lúc DTO được tạo/deserialized, có thể sớm hơn lúc nghiệp vụ thật sự tạo bản ghi.
- `clock.instant()` trong service biểu thị thời điểm use case xử lý (với `Clock` được inject để test ổn định).
- `DEFAULT CURRENT_TIMESTAMP` trong database gắn với semantics thời gian của DB/giao dịch, không nhất thiết bằng thời điểm request được nhận.

Nếu cần “thời điểm đơn hàng được xác nhận”, hãy lấy thời gian tại hành động xác nhận và ghi lại. Nếu cần “thời điểm DB tạo hàng”, cân nhắc cơ chế DB. Không chọn ngẫu nhiên giữa hai nơi vì chúng có thể tạo giá trị khác nhau.

Không nhận `role=ADMIN` hay `ownerId` do client tự khai báo rồi xem một default `USER` là cơ chế bảo vệ. Các thuộc tính quyền/sở hữu phải được quyết định từ authenticated principal và business policy; đồng thời kiểm soát trường có thể bind để tránh sửa thuộc tính nội bộ.

## 11. Default của database khác default của DTO

Ví dụ DDL:

```sql
CREATE TABLE tasks (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Cơ sở dữ liệu có thể dùng default nếu câu `INSERT` không cung cấp giá trị cho cột:

```sql
INSERT INTO tasks DEFAULT VALUES;
```

Nhưng nếu SQL gửi **`status = NULL`**, ràng buộc `NOT NULL` có thể từ chối thay vì tự thay bằng `PENDING`. Với JPA/Hibernate, entity có field `status = null` không đồng nghĩa ORM sẽ bỏ cột khỏi câu `INSERT`; nhiều cấu hình gửi rõ `NULL`. Vì vậy không nên kỳ vọng DB default tự bù tất cả field thiếu trên request.

Một số điểm cần kiểm tra:

- `@ColumnDefault` của Hibernate liên quan khai báo schema/DDL; nó **không tự đặt giá trị vào Java request DTO**.
- `@Column(nullable = false)` mô tả mapping/nullability, **không khởi tạo giá trị Java**.
- Java initializer ở entity và DB default có thể đặt hai giá trị khác nhau, khiến hành vi khác giữa JPA và SQL trực tiếp. Hãy chọn chính sách thống nhất.
- Không để default DB bí mật thay thế một rule nghiệp vụ quan trọng. Nếu default phụ thuộc người dùng hay trạng thái use case, xử lý trong domain/service trước khi persist.

## 12. DTO bất biến, record và khả năng phân biệt missing với explicit null

Với Java record, không có setter hay field initializer kiểu JavaBean cho từng record component. Có thể dùng compact constructor:

```java
public record SearchJson(Integer limit, String sort) {
    public SearchJson {
        if (limit == null) {
            limit = 20;
        }
        if (sort == null) {
            sort = "newest";
        }
    }
}
```

Ví dụ này hợp lệ trong Java 17; sau khi gọi `new SearchJson(null, null)`, record chứa `20` và `"newest"`. Khi dùng Jackson để deserialize record, cả property **thiếu** và property **explicit null** có thể dẫn đến argument `null` và cùng đi qua constructor. Đây là lựa chọn hợp lý **chỉ nếu hợp đồng muốn hai trường hợp có cùng nghĩa**.

Nếu sản phẩm quy định:
- Không gửi `limit` → dùng `20`;
- Gửi `"limit": null` → báo lỗi;
- Gửi `"limit": 0` → báo lỗi giới hạn;

thì constructor đơn giản như trên **không đủ thông tin** để tách trường hợp thứ nhất khỏi thứ hai. Có thể dùng một lớp input có khả năng ghi nhận presence, custom deserializer hoặc kiểm tra cấu trúc JSON trước khi chuyển thành domain command. Đừng mặc định null là “không gửi” nếu API cần phân biệt.

Tương tự, Lombok `@Builder.Default` chỉ có semantics liên quan quá trình tạo qua builder; không nên tự giả định Jackson hoặc Spring binder luôn dùng builder đó.

## 13. Tạo mới và cập nhật một phần có semantics khác nhau

Với request **tạo mới**, property thiếu thường được hiểu là “dùng default” nếu hợp đồng quy định. Với request **PATCH**, property thiếu thường có nghĩa “không thay đổi dữ liệu hiện có”.

Giả sử tài khoản đang có `displayName = "Linh"`:

| JSON PATCH | Ý nghĩa có thể mong muốn |
| --- | --- |
| `{}` | Giữ nguyên `"Linh"` |
| `{"displayName":"An"}` | Đổi thành `"An"` |
| `{"displayName":null}` | Xóa giá trị, nếu được phép; hoặc từ chối |
| `{"displayName":""}` | Đổi thành chuỗi rỗng nếu được phép; hoặc lỗi validation |

Nếu định nghĩa `displayName = "Guest"` ngay khi tạo PATCH DTO rồi map tất cả field vào entity, request `{}` có nguy cơ đổi tên từ `"Linh"` thành `"Guest"` ngoài ý muốn.

Đối với PATCH, nên giữ thông tin **field có xuất hiện hay không** (ví dụ bằng một kiểu dữ liệu biểu diễn ba trạng thái, hoặc kiểm tra presence trong JSON tree) và chỉ cập nhật field client đã gửi. Validation và default theo ngữ cảnh cập nhật phải được thiết kế riêng; không tái dùng máy móc DTO tạo mới.

## 14. Kiểm thử thời điểm áp dụng mặc định

Tối thiểu phải kiểm tra cả đường đi hợp lệ và sai:

| Test case | Kết quả mong đợi |
| --- | --- |
| `GET /demo/items` | `limit=20`, `sort=newest` |
| `GET /demo/items?limit=` | `limit=20` do `@RequestParam(defaultValue)` |
| `GET /demo/items?limit=abc` | Lỗi conversion, không fallback về `20` |
| `GET /demo/items?limit=0` | Giá trị `0` được truyền vào controller; endpoint phải thêm validation nếu muốn cấm |
| `GET /demo/form` | JavaBean initializer cho `limit=20` |
| `GET /demo/form?sort=` | Lỗi `@NotBlank` sau binding |
| `GET /demo/form?limit=0` | Lỗi `@Min(1)` sau binding |
| POST JSON `{}` | Giữ mặc định ở `PreferenceRequest` |
| POST JSON `{"notificationsEnabled":false}` | Giữ `false` |
| POST JSON `{"notificationsEnabled":null}` | `@NotNull` từ chối |
| Service với tier khác nhau | Chọn đúng dynamic default cho từng tier |
| PATCH JSON `{}` | Không thay đổi field hiện tại |
| DB `INSERT` bỏ cột có default | Nhận giá trị DB theo schema |
| DB `INSERT` cố gán `NULL` vào cột `NOT NULL` | Bị từ chối |

Với Spring, có thể dùng `MockMvc`/`@WebMvcTest` để kiểm tra controller binding và validation; dùng unit test cho chính sách chọn default trong service; integration test cho hành vi JPA và database. Không nên chỉ kiểm tra object được khởi tạo bằng `new` rồi kết luận request HTTP sẽ có hành vi như vậy, vì binder và JSON deserializer có thể ghi đè initializer.

## 15. Những sai lầm phổ biến

**Sai lầm 1: Cho rằng property thiếu và property null luôn giống nhau.** Chúng là hai trạng thái khác nhau ở JSON; JavaBean, record, Jackson config và hợp đồng API quyết định có gộp chúng hay không.

**Sai lầm 2: Dùng default để che lỗi.** Client gửi `limit=abc` hoặc `limit=0` không đồng nghĩa “không gửi”. Chuyển thành mặc định sẽ che lỗi đầu vào.

**Sai lầm 3: Cho rằng `@RequestParam(defaultValue)` có tác dụng trên `@RequestBody`.** Hai bộ giải quyết dữ liệu khác nhau; JSON DTO cần mặc định trong deserialization/constructor/normalization riêng.

**Sai lầm 4: Đặt giá trị mặc định quá sớm.** Gán default thuộc tenant/user/tier ở constructor DTO khi chưa có ngữ cảnh có thể cho kết quả sai. Chọn ở service và kiểm tra lại.

**Sai lầm 5: Dùng primitive để suy ra có gửi dữ liệu.** `0` và `false` có thể là giá trị thật, không phải sentinel an toàn cho trường “vắng mặt”.

**Sai lầm 6: Tin annotation mô tả sẽ tự thực thi.** `@JsonProperty(defaultValue)`, OpenAPI `@Schema(defaultValue)` và một số annotation mapping DB không thay thế logic cấp giá trị thực tế.

**Sai lầm 7: Dùng DTO tạo mới cho PATCH rồi áp dụng default lên entity hiện có.** Một field vắng mặt có thể làm mất dữ liệu; PATCH cần giữ thông tin presence.

**Sai lầm 8: Không validate lại sau khi áp dụng default nghiệp vụ.** Giá trị lấy từ cấu hình/policy cũng có thể sai hoặc vượt giới hạn. Hãy đảm bảo trạng thái cuối cùng thỏa bất biến domain.

## 16. Cách quyết định nhanh nên đặt default ở đâu

1. **Giá trị mặc định cố định cho một tham số URL/header/cookie?** Dùng `defaultValue` của argument resolver phù hợp nếu **thiếu và rỗng được phép có cùng nghĩa**.
2. **Một JavaBean nhận form/query, thiếu field thì giữ giá trị ban đầu?** Khởi tạo field/constructor cho `@ModelAttribute` và xem rõ hành vi ghi đè khi client có gửi giá trị.
3. **Một JSON request body, property thiếu thì dùng mặc định?** Chọn initializer/constructor hoặc cấu hình Jackson có chủ đích; quyết định riêng explicit `null`.
4. **Mặc định phụ thuộc user, tier, tenant, policy hoặc thời điểm use case?** Chọn trong application/domain service, sau đó kiểm tra giá trị hiệu lực.
5. **Mặc định chỉ thuộc cách lưu bản ghi?** Cân nhắc DB default, kiểm tra SQL do ORM sinh ra và không dùng DB default thay cho business rule.
6. **Đây là PATCH?** Giữ sự khác biệt giữa không gửi, gửi null và gửi giá trị; mặc định tạo mới thường không áp dụng nguyên xi.

Một thiết kế rõ ràng luôn trả lời được: **đầu vào nào kích hoạt mặc định, nơi nào gán giá trị, gán trước hay sau binding/validation, và liệu giá trị client gửi tường minh có bị ghi đè hay không**. Khi các câu trả lời đó nhất quán, đối tượng đầu vào của Spring dễ kiểm thử, dễ giải thích và ít tạo lỗi dữ liệu bất ngờ.