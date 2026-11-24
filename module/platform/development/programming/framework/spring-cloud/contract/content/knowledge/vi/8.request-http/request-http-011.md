# Phân biệt trường không có với trường có giá trị null trong HTTP request

Khi hai dịch vụ trao đổi dữ liệu JSON, **trường không xuất hiện** và **trường xuất hiện với giá trị `null`** là hai trạng thái khác nhau. Nhầm lẫn chúng có thể tạo ra lỗi nghiêm trọng: consumer chỉ định cập nhật một thuộc tính nhưng producer lại xóa giá trị đang có; hoặc consumer muốn xóa một thuộc tính nhưng producer bỏ qua thao tác. Trong **Spring Cloud Contract**, sự khác biệt này cần được diễn đạt rõ ở **hợp đồng request HTTP**, được kiểm tra trên mã producer và được mô phỏng đúng bởi stub cho consumer.

Bài thuộc chương **Request HTTP** của mô-đun **SPRING_CLOUD_CONTRACT**. Spring Cloud Contract cho phép định nghĩa hành vi HTTP hoặc thông điệp bằng **Groovy/YAML DSL**, sinh kiểm thử xác minh producer, đóng gói stub và chạy **Stub Runner** cho consumer trong quy trình CI. Trọng tâm ở đây là phần request JSON: khi nào một thuộc tính *không tồn tại*, khi nào nó *tồn tại nhưng mang giá trị null*, cách không làm mất thông tin đó trong Java/Jackson và cách phát hiện các trường hợp bị đánh đồng khi kiểm thử hợp đồng.

## 1. Bốn trạng thái dễ bị nhầm khi nhận JSON

Xét trường `phone` trong request cập nhật thông tin khách hàng. Những body dưới đây có ý nghĩa khác nhau:

| JSON request body | Trạng thái của `phone` | Ý nghĩa có thể quy định trong API |
| --- | --- | --- |
| `{}` | **Không có trường `phone`** | Không cập nhật số điện thoại hiện tại. |
| `{"phone":null}` | **Có trường `phone`, giá trị JSON null** | Chủ động xóa số điện thoại hiện tại. |
| `{"phone":""}` | Có trường `phone`, chuỗi rỗng | Yêu cầu đặt số điện thoại thành chuỗi rỗng hoặc báo lỗi validation. |
| `{"phone":"null"}` | Có trường `phone`, chuỗi ký tự `null` | Chuỗi thông thường, không phải JSON null. |
| `{"phone":"+84901234567"}` | Có trường `phone`, chuỗi có dữ liệu | Yêu cầu cập nhật số điện thoại cụ thể. |

Ví dụ này sử dụng **quy ước nghiệp vụ của một API giả định**: **vắng mặt = giữ nguyên**, **null = xóa**. HTTP không tự quy định quy tắc này chỉ từ phương thức hoặc kiểu `application/json`. Đội producer và consumer phải **thống nhất, ghi vào tài liệu API và hợp đồng**. Với `application/merge-patch+json` theo JSON Merge Patch, `null` có ngữ nghĩa loại bỏ thành viên của đối tượng theo đặc tả; với JSON thông thường, bạn cần tự định nghĩa và thực thi ý nghĩa của nó.

Về mặt dữ liệu, hai cấu trúc sau **không bằng nhau**:

```json
{}
```

```json
{"phone": null}
```

Trong trường hợp thứ hai, khóa `phone` thực sự có trong object; chỉ có **giá trị** của khóa là `null`. Khi một công cụ hoặc lớp DTO biến cả hai thành một giá trị Java `null` mà không lưu dấu vết sự hiện diện của khóa, thông tin đã bị mất.

## 2. Tại sao đây là một vấn đề của hợp đồng giữa producer và consumer?

Giả sử **Customer Service** là producer của endpoint:

```http
PATCH /api/customers/42
Content-Type: application/json
```

**Billing Service** là consumer gọi endpoint để thay đổi thông tin khách hàng trong quá trình xử lý hóa đơn. Trước khi cập nhật, khách hàng `42` có số `+84901234567`. Hai tình huống được hai nhóm thống nhất:

**Tình huống A — không gửi `phone`, giữ nguyên:**

```http
PATCH /api/customers/42
Content-Type: application/json

{}
```

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"customerId":42,"phone":"+84901234567"}
```

**Tình huống B — gửi `phone: null`, xóa số:**

```http
PATCH /api/customers/42
Content-Type: application/json

{"phone":null}
```

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"customerId":42,"phone":null}
```

Phản hồi khác nhau giúp **generated producer tests** quan sát được liệu mã producer có thật sự phân biệt hai request hay không. Với stub, hai ánh xạ cũng phải phân biệt được request `{}` và `{"phone":null}`, dù cả hai dùng cùng phương thức, path và Content-Type.

Đây là một ví dụ minh họa hai hành vi **độc lập trên dữ liệu mẫu**, không có nghĩa HTTP stub tự giữ trạng thái khách hàng qua nhiều lần gọi. Trong ứng dụng thật, thao tác `PATCH` cập nhật dữ liệu ở phía producer; stub thường trả về phản hồi cố định theo request matcher và **không tự mô phỏng đầy đủ vòng đời trạng thái**.

## 3. Quy ước diễn đạt trong Spring Cloud Contract

Trong Groovy và YAML DSL, khi biểu diễn JSON, phải phân biệt ba việc:

1. **Khóa xuất hiện trong body**: biểu diễn trường mà request gửi.
2. **Giá trị của khóa**: `null`, `""`, `false`, `0` hay một giá trị thực.
3. **Quy tắc khớp request được sinh cho stub**: cần đủ chặt để không nhận nhầm request của tình huống khác.

Nếu một hợp đồng chỉ mô tả `{"customerId":42}`, điều đó có nghĩa **body ví dụ không có trường `phone`**. Nhưng **việc bỏ `phone` khỏi ví dụ không tự bảo đảm** stub được sinh sẽ *từ chối mọi request bổ sung trường `phone`*; điều này phụ thuộc matcher thực sự được sinh và cấu hình so khớp JSON. Vì vậy, khi **sự vắng mặt của trường là điều kiện nghiệp vụ**, cần kiểm tra mapping thực tế và có bài test **âm tính** để xác minh request chứa trường không khớp nhầm.

Tương tự, khi một hợp đồng chứa `phone: null`, phải kiểm tra công cụ bảo toàn **JSON null** trong request gửi tới producer và request matcher của stub, thay vì bỏ trường hoặc đổi thành chuỗi `"null"`.

### 3.1. YAML null khác chuỗi "null"

Trong YAML, các cách ghi dưới đây không có cùng kiểu dữ liệu:

```yaml
phone: null      # YAML null -> giá trị null
phone2: ~        # YAML null
phone3: "null"    # Chuỗi có bốn ký tự n-u-l-l
phone4: ""        # Chuỗi rỗng
```

Khi dùng YAML làm Spring Cloud Contract DSL, nên chọn một cách ghi **nhất quán**, chẳng hạn `phone: null`, để reviewer dễ nhận biết. Hãy xác nhận quá trình parser/serializer của **phiên bản Spring Cloud Contract đang dùng** giữ lại trường mang giá trị null trong JSON request. Một tệp YAML parse được chưa đồng nghĩa với một request matcher đáp ứng đúng điều kiện vắng mặt/giá trị null.

### 3.2. Groovy null khác chuỗi "null"

Trong Groovy:

```groovy
def withoutPhone = [:]
def withExplicitNull = [phone: null]
def withStringNull = [phone: 'null']

assert !withoutPhone.containsKey('phone')
assert withExplicitNull.containsKey('phone')
assert withExplicitNull.phone == null
assert withStringNull.phone == 'null'
```

Hai map đầu đều có thể trả về `null` khi truy cập `map.phone`, nhưng `containsKey` cho biết một map có chứa khóa `phone` hay không. Nguyên tắc này cũng xuất hiện khi producer đọc request bằng `Map<String, Object>` hoặc Jackson `JsonNode`.

## 4. Ví dụ Groovy DSL: hai contract cho hai body khác nhau

Tệp ví dụ `src/test/resources/contracts/customers/patch_phone.groovy` định nghĩa hai tình huống trong cùng một danh sách `Contract.make`:

```groovy
import org.springframework.cloud.contract.spec.Contract

[
    Contract.make {
        name 'shouldKeepPhoneWhenFieldMissing'
        description 'Không gửi phone thì giữ nguyên số điện thoại'

        request {
            method 'PATCH'
            url '/api/customers/42'
            headers {
                contentType(applicationJson())
            }
            body('{}')
        }

        response {
            status 200
            headers {
                contentType(applicationJson())
            }
            body('{"customerId":42,"phone":"+84901234567"}')
        }
    },
    Contract.make {
        name 'shouldClearPhoneWhenExplicitNull'
        description 'Gửi phone là JSON null thì xóa số điện thoại'

        request {
            method 'PATCH'
            url '/api/customers/42'
            headers {
                contentType(applicationJson())
            }
            body('{"phone":null}')
        }

        response {
            status 200
            headers {
                contentType(applicationJson())
            }
            body('{"customerId":42,"phone":null}')
        }
    }
]
```

Hai lời gọi `Contract.make` nằm trong **một list Groovy trả về ở cuối script**. Mỗi hợp đồng có `name`, `request`, `response` riêng. Việc sử dụng **chuỗi JSON trực tiếp** trong `body(...)` làm rõ khác biệt giữa `{}` và `{"phone":null}`, đồng thời tránh trường hợp một phép biến đổi map tự ý loại trường null trong mã chuẩn bị dữ liệu.

**Lưu ý về matcher:** ví dụ mô tả **đầu vào và kết quả kỳ vọng**, nhưng không nên mặc nhiên kết luận hai stub mapping tạo ra sẽ khớp loại trừ hoàn toàn chỉ từ việc đọc mã Groovy. Hãy xem JSON mapping được sinh trong artifact `stubs` và chạy phép thử cố tình gửi request của tình huống còn lại. Nếu cấu hình so khớp body không kiểm sự hiện diện/vắng mặt như mong muốn, cần dùng cơ chế request matcher thích hợp **được phiên bản công cụ hỗ trợ**, sau đó xác minh lại cả producer test và stub test. Không dựa vào thứ tự mapping để quyết định response cho hai request có khả năng trùng điều kiện khớp.

## 5. Ví dụ YAML DSL: tách thành hai file dễ đọc

Nhóm chọn YAML có thể đặt mỗi tình huống ở một file. Với `patch_phone_missing.yml`:

```yaml
description: Không gửi phone thì giữ nguyên số điện thoại
request:
  method: PATCH
  url: /api/customers/42
  headers:
    Content-Type: application/json
  body: '{}'
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    customerId: 42
    phone: "+84901234567"
```

Và `patch_phone_null.yml`:

```yaml
description: Gửi JSON null thì xóa số điện thoại
request:
  method: PATCH
  url: /api/customers/42
  headers:
    Content-Type: application/json
  body:
    phone: null
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    customerId: 42
    phone: null
```

Hai dạng `body` ở đây được chọn để cho thấy **body JSON rỗng** và **body có khóa null**. Có thể viết trường hợp null bằng chuỗi JSON:

```yaml
body: '{"phone":null}'
```

Tuy nhiên, không phải mọi cách viết dữ liệu YAML/Groovy đều tạo **chính xác cùng một stub request matcher** trong mọi phiên bản plugin. Với bài học này, điều cần xác nhận qua build là:

- Generated producer test trường hợp vắng mặt **gửi một JSON object không có `phone`**.
- Generated producer test trường hợp null **gửi một JSON object có `phone` mang giá trị null**.
- Stub server phân biệt hai request, không trả nhầm response của tình huống khác.
- Khi consumer gửi `{"phone":""}` hoặc `{"phone":"null"}`, chúng **không được vô tình nhận hành vi xóa số** nếu API không quy định như vậy.

Quy ước an toàn là **chỉ một DSL có hiệu lực cho mỗi tập hợp tình huống** trong repository. Đừng đồng thời đưa cả các file YAML ở mục này và tệp Groovy ở mục trước vào đường dẫn build đang quét nếu chúng cùng biểu diễn một nhóm request; như vậy có thể tạo test/mapping trùng lặp và khó kiểm soát.

## 6. Đọc HTTP request trong Java mà không làm mất thông tin

Đây là phần quan trọng nhất phía producer: nếu mã Java đã đánh đồng hai trạng thái trước khi xử lý nghiệp vụ, hợp đồng có mô tả đúng cũng không giúp API thực thi đúng. Xét ba cách đọc request phổ biến.

### 6.1. DTO với thuộc tính nullable có thể không đủ

Giả sử controller dùng:

```java
public record PhonePatch(String phone) {}
```

Với cấu hình Jackson phổ biến, cả hai body:

```json
{}
```

và:

```json
{"phone":null}
```

đều có thể tạo ra `PhonePatch` với `phone() == null`. Khi đó biểu thức `phone() == null` **không phân biệt được** consumer không gửi trường hay chủ động gửi null. Cách ánh xạ có thể khác nếu dự án dùng deserializer/validation đặc biệt, nhưng không nên xem DTO chỉ có một `String` là giải pháp ba trạng thái mặc định.

Nếu cần phân biệt, hãy dùng cơ chế lưu được **sự hiện diện của trường** như `JsonNode`, `Map` cùng `containsKey` hoặc một kiểu dữ liệu ba trạng thái/deserializer được thiết kế riêng.

### 6.2. Dùng Jackson JsonNode: has khác hasNonNull

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper();

JsonNode missing = mapper.readTree("{}");
JsonNode explicitNull = mapper.readTree("{\"phone\":null}");
JsonNode emptyString = mapper.readTree("{\"phone\":\"\"}");

assert !missing.has("phone");
assert missing.get("phone") == null;

assert explicitNull.has("phone");
assert explicitNull.get("phone").isNull();

assert emptyString.has("phone");
assert emptyString.get("phone").isTextual();
assert emptyString.get("phone").asText().isEmpty();
```

Một số phương thức Jackson cần phân biệt:

| Phương thức | Với `{}` | Với `{"phone":null}` | Ý nghĩa |
| --- | --- | --- | --- |
| `node.has("phone")` | `false` | `true` | Kiểm tra có **khóa** hay không. |
| `node.get("phone")` | Java `null` | Jackson `NullNode` | Trả về node tương ứng, hoặc Java null khi không có khóa. |
| `node.hasNonNull("phone")` | `false` | `false` | Chỉ đúng khi khóa tồn tại và có giá trị khác JSON null. |
| `node.path("phone")` | `MissingNode` | `NullNode` | Không ném lỗi vì khóa thiếu; có thể dùng `isMissingNode()` hoặc `isNull()`. |

**Sai lầm phổ biến:** dùng `!node.hasNonNull("phone")` để suy ra trường **không xuất hiện**. Biểu thức đó đúng cho **cả missing và explicit null**. Muốn biết trường không có, dùng `!node.has("phone")`; muốn biết trường có và là null, dùng `node.has("phone") && node.get("phone").isNull()`.

### 6.3. Dùng Map: containsKey khác get

```java
Map<String, Object> missing = new HashMap<>();
Map<String, Object> explicitNull = new HashMap<>();
explicitNull.put("phone", null);

assert !missing.containsKey("phone");
assert explicitNull.containsKey("phone");
assert missing.get("phone") == null;
assert explicitNull.get("phone") == null;
```

`map.get("phone") == null` vẫn đánh đồng hai trạng thái. `containsKey` mới cho phép phát hiện khóa có tồn tại. Lưu ý `Map.of("phone", null)` trong Java **không hợp lệ** vì `Map.of` không chấp nhận null; ví dụ dùng `HashMap`.

## 7. Triển khai producer nhận đúng hai trạng thái

Đoạn controller Spring MVC sau mô phỏng hành vi đã định nghĩa trong hai hợp đồng. Nó không sử dụng cơ sở dữ liệu; số điện thoại mẫu được coi là trạng thái ban đầu của khách hàng `42`, và response của mỗi request được tính **độc lập**.

```java
package com.acme.customers;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/customers")
public class CustomerController {

    private final ObjectMapper mapper;

    public CustomerController(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    @PatchMapping(
        value = "/{id}",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<JsonNode> patchCustomer(
            @PathVariable long id, @RequestBody JsonNode input) {

        if (id != 42L) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).build();
        }
        if (!input.isObject()) {
            return ResponseEntity.badRequest().build();
        }

        ObjectNode result = mapper.createObjectNode();
        result.put("customerId", 42);

        if (!input.has("phone")) {
            // Trường không có: giữ giá trị giả định đang lưu.
            result.put("phone", "+84901234567");
        } else if (input.get("phone").isNull()) {
            // Trường có mặt và là JSON null: xóa giá trị.
            result.putNull("phone");
        } else if (input.get("phone").isTextual()) {
            // Trường có chuỗi: thay bằng chuỗi yêu cầu.
            result.put("phone", input.get("phone").asText());
        } else {
            return ResponseEntity.badRequest().build();
        }

        return ResponseEntity.ok(result);
    }
}
```

**Hành vi quan trọng:** `input.has("phone")` xác nhận sự hiện diện của thuộc tính; `input.get("phone").isNull()` xác nhận kiểu JSON null. `result.putNull("phone")` chủ động đặt một JSON `null` trong response, tránh làm mất khóa nếu lớp DTO hoặc serializer có cấu hình loại bỏ các giá trị Java null.

Đoạn mã chỉ là **fixture phục vụ học contract testing**. Trong dịch vụ thật, logic cập nhật phải truy cập dữ liệu tồn tại, kiểm phân quyền, validation, giao dịch và lưu trữ. Với API cập nhật, việc response phản ánh trạng thái thực sau khi ghi là một yêu cầu nghiệp vụ riêng cần có test tương ứng.

Generated producer tests từ Groovy/YAML DSL sẽ phát huy giá trị nếu hành vi thực khác hợp đồng. Ví dụ, nếu implementation thay `if (!input.has("phone"))` bằng `if (!input.hasNonNull("phone"))`, request `{"phone":null}` có thể bị hiểu nhầm là vắng mặt, tạo response có số điện thoại cũ. Khi cả hai hợp đồng được nạp và thực thi, test cho trường hợp null sẽ phát hiện khác biệt kỳ vọng này.

## 8. Kiểm tra producer test được sinh có phân biệt thật không?

Trong producer đã cấu hình Spring Cloud Contract Verifier, chạy bước build phù hợp, ví dụ Maven:

```shell
mvn clean verify
```

Điều cần xem sau build:

1. Plugin **đọc được cả hai hợp đồng** và tạo các tình huống kiểm thử tương ứng.
2. Generated test của `shouldKeepPhoneWhenFieldMissing` gửi request có object JSON **không chứa `phone`**, kiểm response `phone: "+84901234567"`.
3. Generated test của `shouldClearPhoneWhenExplicitNull` gửi request có `phone: null`, kiểm response **có** khóa `phone` và giá trị JSON null.
4. Nếu đổi code producer để đánh đồng hai trạng thái, **ít nhất một test liên quan phải thất bại**.

Tên lớp và phương thức được sinh phụ thuộc phiên bản plugin và cấu hình base test; không suy số tình huống chỉ từ số file Groovy/YAML. Nếu một tệp Groovy trả về danh sách hai hợp đồng, cần chắc chắn **cả hai đối tượng Contract** được plugin nạp, chứ không chỉ kiểm tra build có `BUILD SUCCESS`.

### 8.1. Thêm kiểm thử âm tính để kiểm chứng ý nghĩa thiếu/null

Bên cạnh generated producer tests, một bài kiểm thử thủ công nhỏ có thể giúp tìm lỗi deserialize hoặc serialization. Ví dụ hai request tới controller:

```java
mockMvc.perform(patch("/api/customers/42")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{}"))
    .andExpect(status().isOk())
    .andExpect(content().json(
        "{\"customerId\":42,\"phone\":\"+84901234567\"}", true));

mockMvc.perform(patch("/api/customers/42")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"phone\":null}"))
    .andExpect(status().isOk())
    .andExpect(content().json(
        "{\"customerId\":42,\"phone\":null}", true));
```

Đây là **đoạn thân test minh họa**, giả định đã có `MockMvc`, static imports từ `MockMvcRequestBuilders` và `MockMvcResultMatchers`, cùng Spring Test/JUnit. Đối số `true` của `content().json(..., true)` yêu cầu so sánh JSON nghiêm ngặt, giúp quan sát khác biệt của trường null và trường bị bỏ. Trong các bộ test lớn, nên dùng cùng fixture để tránh kiểm thử hợp đồng và kiểm thử riêng ngầm dựa vào hai trạng thái ban đầu khác nhau.

## 9. Kiểm tra stub và mã gọi thật của consumer

Sau khi producer verification đạt, build tạo artifact `stubs` theo version, ví dụ `com.acme:customer-service:1.0.0:stubs`. Stub Runner tìm và chạy mapping trong artifact đó. Consumer phải kiểm **đúng body mình thực sự gửi**, bởi thư viện JSON có thể thay đổi request trước khi nó đến stub.

### 9.1. Tạo body trong consumer không làm mất null

Jackson `ObjectNode` có hai thao tác rất rõ:

```java
ObjectNode omitted = objectMapper.createObjectNode();
ObjectNode explicitNull = objectMapper.createObjectNode().putNull("phone");

assert !omitted.has("phone");
assert explicitNull.has("phone");
assert explicitNull.get("phone").isNull();
```

Nếu consumer tạo một DTO có `phone == null` rồi serializer được cấu hình `@JsonInclude(Include.NON_NULL)`, trường null **có thể bị bỏ khỏi JSON hoàn toàn**. Khi đó consumer tưởng đã gửi yêu cầu xóa nhưng trên đường truyền lại là `{}`. Đối với API cần phân biệt ba trạng thái, dùng `ObjectNode`, kiểu patch chuyên dụng hoặc serializer giữ được sự hiện diện của trường.

### 9.2. Mã client thật và kiểm thử qua Stub Runner

Ví dụ dưới dùng `RestClient` của Spring Framework 6.1 trở lên. `JdkClientHttpRequestFactory` được khai báo rõ để gửi HTTP `PATCH` bằng `java.net.http.HttpClient` của JDK; cách cấu hình request factory có thể khác ở ứng dụng đã dùng một HTTP client hỗ trợ PATCH sẵn.

```java
package com.acme.billing;

import com.fasterxml.jackson.databind.node.ObjectNode;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class CustomerClient {

    private final RestClient http;

    public CustomerClient(RestClient.Builder builder,
                          @Value("${customers.base-url}") String baseUrl) {
        this.http = builder
                .baseUrl(baseUrl)
                .requestFactory(new JdkClientHttpRequestFactory())
                .build();
    }

    public String patchPhone(long id, ObjectNode patchBody) {
        return http.method(HttpMethod.PATCH)
                .uri("/api/customers/{id}", id)
                .contentType(MediaType.APPLICATION_JSON)
                .body(patchBody)
                .retrieve()
                .body(String.class);
    }
}
```

Giả sử ứng dụng consumer có cấu hình Spring Boot để inject `ObjectMapper`, `CustomerClient` và đã khai báo test dependency `spring-cloud-starter-contract-stub-runner`. Bài test:

```java
package com.acme.billing;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = "customers.base-url=http://localhost:8089")
@AutoConfigureStubRunner(
    ids = "com.acme:customer-service:1.0.0:stubs:8089",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class CustomerClientContractTest {

    @Autowired CustomerClient customerClient;
    @Autowired ObjectMapper mapper;

    @Test
    void missingPhoneLeavesExistingValue() throws Exception {
        ObjectNode request = mapper.createObjectNode();
        String json = customerClient.patchPhone(42L, request);
        JsonNode response = mapper.readTree(json);

        assertThat(response.get("phone").asText())
            .isEqualTo("+84901234567");
    }

    @Test
    void explicitNullClearsPhone() throws Exception {
        ObjectNode request = mapper.createObjectNode();
        request.putNull("phone");
        String json = customerClient.patchPhone(42L, request);
        JsonNode response = mapper.readTree(json);

        assertThat(response.has("phone")).isTrue();
        assertThat(response.get("phone").isNull()).isTrue();
    }
}
```

Ví dụ dùng `LOCAL` vì artifact phải đã được cài vào Maven local bằng build producer. Khi sử dụng artifact **đã phát hành** trên Maven repository chung, đổi sang `REMOTE` và cấu hình `repositoryRoot` cùng quyền đọc phù hợp. Phiên bản, classifier và port trong `ids` phải khớp với artifact và địa chỉ HTTP client.

**Quan trọng:** hai test có thể vượt qua hoặc thất bại theo mapping thực sự sinh ra. Đừng tự tin vào kết quả chỉ vì một test nhận `200`: cả hai tình huống đều trả `200`, nên cần assert **giá trị khác nhau** và trường `phone` có mặt khi response quy định JSON null. Hãy thử hoán đổi body giữa hai test hoặc gửi `{"phone":""}` để kiểm tra stub không khớp nhầm một mapping rộng.

## 10. Kiểm soát request matcher và nguy cơ hai mapping chồng lấn

Hai hợp đồng ở trên có cùng:

```text
method = PATCH
url = /api/customers/42
Content-Type = application/json
```

Chỉ **body** phân biệt chúng. Nếu một mapping được sinh ra không kiểm body hoặc cấu hình bỏ qua những thành phần JSON bổ sung, request `{"phone":null}` có thể khớp cả mapping dành cho `{}`. Khi ấy thứ tự/độ ưu tiên mapping quyết định phản hồi, nhưng điều đó không phải sự khác biệt nghiệp vụ có chủ đích.

Khi kiểm tra artifact `stubs`, hãy xem request body matcher mà Spring Cloud Contract đã sinh cho **từng** trường hợp. Trong WireMock, một kiểu biểu đạt so sánh JSON là `equalToJson`; ví dụ minh họa ý tưởng của một matcher nghiêm ngặt:

```json
{
  "request": {
    "method": "PATCH",
    "url": "/api/customers/42",
    "bodyPatterns": [
      {
        "equalToJson": "{}",
        "ignoreExtraElements": false
      }
    ]
  }
}
```

Ở đây `ignoreExtraElements: false` biểu thị matcher JSON không chủ ý bỏ qua thuộc tính thêm vào. Đây là **một đoạn JSON minh họa cách kiểm request trong WireMock**, **không cam kết** Spring Cloud Contract sẽ sinh ra chính xác mapping này từ đoạn Groovy/YAML phía trên. Bạn phải đối chiếu file được sinh và hành vi thật của Stub Runner trong phiên bản dự án; nếu muốn áp dụng matcher chuyên biệt để phát hiện trường vắng mặt, hãy chọn khả năng DSL/request matching mà phiên bản đang dùng hỗ trợ và test cả trường hợp không được phép khớp.

Một kế hoạch kiểm matcher nên gồm:

| Request gửi đến stub | Kỳ vọng theo API ví dụ | Kiểm gì? |
| --- | --- | --- |
| `{}` | Giữ `phone` cũ | Trả `200` và số điện thoại cũ. |
| `{"phone":null}` | Xóa `phone` | Trả `200`, có trường `phone` bằng JSON null. |
| `{"phone":""}` | Không trùng hai trường hợp trên nếu chưa có hợp đồng | Không được âm thầm trả hành vi “giữ nguyên” hoặc “xóa” do match quá rộng. |
| `{"phone":"null"}` | Là chuỗi, không phải null | Không được khớp nhầm trường hợp null. |
| Body không phải JSON hợp lệ | Tùy quy định API | Không được coi là request hợp lệ chỉ vì method/path khớp. |

Với trường hợp **không có mapping**, WireMock thường trả 404. Đây là **404 do request không khớp stub**, không nhất thiết là lỗi nghiệp vụ của producer. Nếu muốn test lỗi nghiệp vụ 404, cần hợp đồng mô tả 404 đó cùng body/mã lỗi đặc thù để tránh kết quả test đạt giả.

## 11. Dễ nhầm khi sử dụng matcher, JSONPath và schema

Các API kiểm tra sự tồn tại của đường dẫn và giá trị thường có ngữ nghĩa khác nhau:

- **Sự hiện diện của khóa**: `phone` có được gửi không?
- **Giá trị khác null**: `phone` có dữ liệu cụ thể không?
- **Khớp JSONPath**: biểu thức có trả về node/giá trị thỏa điều kiện hay không? Matcher JSONPath của thư viện có thể coi kết quả null là không khớp, tùy cách gọi và phiên bản.
- **Khớp schema**: trường bắt buộc phải tồn tại hay chỉ được phép có null? Đây là hai ràng buộc riêng.

Với JSON Schema, ví dụ:

```json
{
  "type": "object",
  "properties": {
    "phone": { "type": ["string", "null"] }
  },
  "additionalProperties": false
}
```

`phone` có thể **vắng mặt** hoặc có kiểu `string`/`null` vì không nằm trong danh sách `required`. Nếu thêm:

```json
"required": ["phone"]
```

vào schema object tương ứng, trường phải **có mặt**, dù giá trị vẫn có thể là `null`. Đây là nguyên tắc chung của JSON Schema, **không phải** lời khẳng định Spring Cloud Contract tự sử dụng mẫu schema này làm request matcher; muốn kiểm schema cần kết nối cơ chế validation phù hợp.

Với OpenAPI, khái niệm **optional** (có bắt buộc xuất hiện không) và **nullable** (có chấp nhận JSON null không) cũng phải được quy định độc lập. Không nên đọc mô tả `nullable` rồi suy ra trường luôn có mặt, hoặc đọc `required` rồi suy ra giá trị không được null. Cú pháp nullable phụ thuộc phiên bản đặc tả: OpenAPI 3.0 thường sử dụng `nullable`, còn OpenAPI 3.1 theo JSON Schema có thể dùng hợp kiểu gồm `null`.

## 12. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Request `{}` và `{"phone":null}` được xử lý giống nhau. | DTO `String phone`, kiểm `== null` hoặc dùng `hasNonNull` thay cho `has`. | Ghi nhận object request sau deserialize; dùng `JsonNode.has`/`isNull` hoặc `Map.containsKey`. |
| Consumer muốn xóa số nhưng server giữ nguyên. | Serializer bỏ thuộc tính null (`NON_NULL`), request trên mạng trở thành `{}`. | Log/test **JSON đã serialize**, không chỉ nhìn DTO trước khi gọi HTTP. |
| Producer test chỉ kiểm tình huống thiếu, bỏ sót tình huống null. | Chỉ có một hợp đồng hoặc plugin không nạp đủ contract. | Kiểm số tình huống và tên test được sinh, report test, đường dẫn contract. |
| Stub luôn trả cùng response cho cả hai body. | Body matcher quá rộng, request mapping trùng hoặc thiếu điều kiện phân biệt. | Mở mapping trong JAR `stubs`, thực thi ma trận request tại mục 10. |
| YAML `phone: "null"` nhưng producer nhận chuỗi. | Đã đặt dấu nháy quanh null. | Dùng `phone: null` hoặc JSON có `null` không có dấu nháy. |
| `Map.of("phone", null)` gây lỗi ở consumer test. | `Map.of` không cho phép null. | Dùng `ObjectNode.putNull` hoặc `HashMap` có `containsKey`. |
| Response `phone: null` trở thành body không có `phone`. | Serializer đang bỏ giá trị Java null. | Dùng `NullNode`/cấu hình serialization thích hợp và assert sự hiện diện trường. |
| Consumer test tại local đạt nhưng CI thất bại. | CI dùng artifact stub phiên bản khác, chưa publish hoặc repository/credential sai. | Ghim version, kiểm classifier `stubs`, repo truy cập và generated mapping. |
| Chỉ sửa stub để test xanh sau thay đổi. | Hợp đồng, producer và stub bị lệch nguồn sự thật. | Đưa thay đổi vào contract, chạy lại generated producer tests rồi phát hành stub mới. |

Khi lỗi xuất hiện, truy vết lần lượt qua **JSON gửi thực tế → biểu diễn sau deserialize ở producer → hợp đồng được plugin nạp → generated producer test → stub mapping → consumer assertion**. Đây là đường đi có thể xác định được điểm đánh mất thông tin missing/null.

## 13. Đưa tình huống thiếu/null vào CI mà không bỏ qua tương thích

Một pipeline hữu ích cần bảo đảm:

1. **Producer CI** nạp đủ các hợp đồng cho trường hợp vắng mặt và null, sinh test, chạy với mã producer, kiểm trạng thái và body có trường null đúng như đã cam kết.
2. Chỉ khi producer verification đạt, build **đóng gói và phát hành** artifact `stubs` theo version có thể truy nguyên.
3. **Consumer CI** sử dụng Stub Runner với version stub đã chọn, chạy mã client thực và assert cả hai trường hợp; có test âm tính cho `""`, chuỗi `"null"` hoặc trường bổ sung nếu cần phân biệt chặt.
4. Với thay đổi API từ “null nghĩa là giữ nguyên” sang “null nghĩa là xóa”, xem đó là một thay đổi hành vi **có thể phá tương thích**. Cần xem consumer nào đang dùng quy tắc cũ và kế hoạch chuyển đổi, thay vì chỉ cập nhật hợp đồng cho khớp producer mới.
5. Không coi generated producer test xanh với bộ hợp đồng **vừa thay toàn bộ** là bằng chứng tự động tương thích với consumer cũ; phải tiếp tục kiểm những hợp đồng còn hiệu lực hoặc các consumer được hỗ trợ.

Nếu project sử dụng messaging thay HTTP, nguyên tắc **khóa vắng mặt khác khóa có giá trị JSON null** vẫn có thể áp dụng cho payload JSON của thông điệp, nhưng cấu hình kích hoạt/kiểm thử phát nhận, broker và Stub Runner messaging khác HTTP WireMock; không sao chép nguyên cấu hình `PATCH` sang luồng thông điệp.

## 14. Bài thực hành: tìm lỗi chỉ xuất hiện khi gửi null

Trên một dự án Spring Boot đã cấu hình Spring Cloud Contract Verifier và một consumer có Stub Runner, thực hiện:

1. **Tạo hai hợp đồng** như mục 4 (hoặc hai file YAML ở mục 5) cho cùng endpoint `PATCH /api/customers/42`, lần lượt với body `{}` và `{"phone":null}`.
2. **Viết producer controller** dùng `JsonNode.has` và `isNull`; chạy generated producer tests, xác nhận **hai tình huống đều thực sự chạy** và PASS.
3. **Gây lỗi cố ý:** đổi điều kiện `!input.has("phone")` thành `!input.hasNonNull("phone")` trong controller. Chạy lại producer test và ghi nhận test nào thất bại, response thực tế khác kỳ vọng ra sao.
4. **Hoàn nguyên** controller, build artifact stub, dùng Stub Runner chạy consumer test với `ObjectNode.createObjectNode()` và `putNull("phone")`.
5. **Thử tình huống âm tính:** gửi `{"phone":""}` và `{"phone":"null"}`; quan sát stub có khớp nhầm mapping nào hay không. Nếu có, kiểm tra body matcher được sinh, điều chỉnh hợp đồng/cấu hình matcher cho rõ và xác minh lại hai phía.
6. **Thử serializer consumer:** dùng DTO có `phone=null` và bật chế độ bỏ giá trị null, kiểm body thực tế được gửi. Giải thích vì sao `putNull` hoặc kiểu dữ liệu ba trạng thái cần thiết nếu null mang ý nghĩa “xóa”.
7. **Nâng cấp CI:** ghim version stub, đặt producer tests trước publish, kiểm consumer tests với cả hai request; mô tả tác động nếu nhóm thay đổi ý nghĩa của null ở API phiên bản mới.

Kết quả mong đợi không chỉ là build xanh. Người học cần **chỉ ra bằng JSON trên đường truyền** trường nào vắng mặt, trường nào thực sự mang null; **chỉ ra trong mã producer** điều kiện phân biệt; và **chứng minh bằng test** rằng hai request không bị stub hoặc consumer đánh đồng.

## 15. Câu hỏi tự kiểm tra

- Với hai body `{}` và `{"phone":null}`, điều kiện `node.get("phone") == null` có phân biệt được không? Vì sao?
- Với Jackson `JsonNode`, `has` khác `hasNonNull` như thế nào?
- Nếu consumer có `@JsonInclude(NON_NULL)`, request mong đợi `{"phone":null}` có thể biến thành gì trên đường truyền?
- Vì sao hai contract cùng method, URL và Content-Type phải có request body matcher đủ chặt để phân biệt?
- Trong YAML, `phone: null` khác `phone: "null"` như thế nào?
- Nếu producer test đạt nhưng stub consumer trả cùng một response cho cả hai body, nên kiểm tra đầu ra nào trước?
- Vì sao một test chỉ assert HTTP 200 ở cả hai tình huống là chưa đủ?
- Nếu hợp đồng mới định nghĩa null nghĩa là “xóa”, bạn cần làm gì để bảo vệ consumer đang hiểu null theo quy tắc cũ?

**Ghi nhớ:** **trường không có** và **trường có mặt với JSON null** khác nhau cả ở dữ liệu lẫn ý nghĩa nghiệp vụ. Trong Spring Cloud Contract, hãy viết hợp đồng request biểu đạt rõ hai tình huống, dùng mã producer giữ được thông tin hiện diện của khóa, kiểm producer test được sinh, xác minh stub body matcher và chạy consumer test qua Stub Runner. Khi một trong các khâu làm mất khác biệt missing/null, CI phải có đủ tình huống và assertion để phát hiện trước khi thay đổi API được phát hành.
