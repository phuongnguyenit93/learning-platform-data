# Tránh trùng tên schema khi nhiều lớp có cùng tên đơn giản

Trong một ứng dụng Spring Boot lớn, nhiều module có thể định nghĩa các DTO khác nhau nhưng vô tình dùng cùng tên lớp, chẳng hạn `User`, `Address`, `Status` hoặc `ErrorResponse`. Ví dụ, module tài khoản có `com.example.account.api.UserResponse`, còn module kiểm toán có `com.example.audit.api.UserResponse`. Java phân biệt hai lớp bằng package đầy đủ, nhưng tên schema trong OpenAPI được lưu trong một không gian tên chung là `components.schemas` của từng tài liệu.

Nếu hai lớp khác nhau cùng được chuyển thành một schema có tên giống nhau, tài liệu có thể bị nhập nhằng: schema bị dùng chung ngoài ý muốn, một tham chiếu trỏ đến cấu trúc không phù hợp hoặc công cụ sinh client tạo ra kiểu dữ liệu khó phân biệt. Cách ổn định nhất là đặt tên schema rõ ràng, duy nhất và có ý nghĩa theo hợp đồng API. Với Springdoc, có thể dùng `@Schema(name = "...")` trên DTO; trong trường hợp cần quy ước toàn dự án, có thể cân nhắc tùy chọn dùng tên đầy đủ của lớp.

## 1. Vì sao package không tự tạo namespace trong `components.schemas`?

Trong mã Java, hai lớp sau là hai kiểu khác nhau:

```java
package com.example.account.api;

public record UserResponse(Long id, String displayName) {
}
```

```java
package com.example.audit.api;

public record UserResponse(String actorId, String action) {
}
```

Tên đầy đủ (fully qualified class name) của chúng khác nhau:

- `com.example.account.api.UserResponse`
- `com.example.audit.api.UserResponse`

Tuy nhiên, khi công cụ tạo OpenAPI đặt schema vào `components.schemas`, mỗi schema được tham chiếu bằng một khóa duy nhất trong cùng object. Ví dụ:

```yaml
components:
  schemas:
    UserResponse:
      type: object
      properties:
        id:
          type: integer
          format: int64
        displayName:
          type: string
```

`$ref: '#/components/schemas/UserResponse'` chỉ xác định được một schema có tên `UserResponse` trong tài liệu đó. OpenAPI không tự thêm namespace Java vào cú pháp `$ref` này. Vì vậy, hai package không tạo thành hai vùng tên riêng trong `components.schemas`.

Các phiên bản Springdoc và Swagger Core có thể có cách xử lý tên model hoặc xung đột khác nhau. Không nên dựa vào hành vi tự đổi tên của resolver như một quy ước hợp đồng. Hãy kiểm tra tài liệu được sinh ra và chủ động đặt tên cho những schema công khai có khả năng trùng nhau.

## 2. Đặt tên schema tường minh bằng `@Schema(name = ...)`

Đây là cách trực tiếp và dễ review nhất. Gắn `@Schema` ở cấp lớp hoặc record để chỉ định tên component schema mong muốn.

DTO của module tài khoản:

```java
package com.example.account.api;

import io.swagger.v3.oas.annotations.media.Schema;

@Schema(
    name = "AccountUserResponse",
    description = "Thông tin người dùng trong API tài khoản"
)
public record UserResponse(
    @Schema(description = "Mã người dùng", example = "1001")
    Long id,

    @Schema(description = "Tên hiển thị", example = "Nguyen An")
    String displayName
) {
}
```

DTO của module kiểm toán:

```java
package com.example.audit.api;

import io.swagger.v3.oas.annotations.media.Schema;

@Schema(
    name = "AuditActorResponse",
    description = "Thông tin tác nhân thực hiện một sự kiện kiểm toán"
)
public record UserResponse(
    @Schema(description = "Mã định danh tác nhân", example = "user-1001")
    String actorId,

    @Schema(description = "Hành động đã thực hiện", example = "ORDER_APPROVED")
    String action
) {
}
```

Mặc dù tên lớp Java vẫn là `UserResponse`, hai component schema được đặt tên khác nhau:

```yaml
components:
  schemas:
    AccountUserResponse:
      type: object
      properties:
        id:
          type: integer
          format: int64
        displayName:
          type: string
    AuditActorResponse:
      type: object
      properties:
        actorId:
          type: string
        action:
          type: string
```

Khi Springdoc xử lý các kiểu DTO này, annotation `@Schema(name = ...)` cung cấp tên schema rõ ràng để dùng trong tài liệu. Những response tham chiếu đến từng lớp sẽ trỏ đến component tương ứng, thay vì phụ thuộc vào tên đơn giản `UserResponse`.

### Đặt tên theo ngữ cảnh API

Tên schema nên cho biết nó đại diện cho dữ liệu gì và được dùng ở ngữ cảnh nào. Một số ví dụ:

| Tên lớp Java | Tên schema đề xuất | Lý do |
|---|---|---|
| `UserResponse` trong account | `AccountUserResponse` | Phân biệt với user trong module khác |
| `UserResponse` trong audit | `AuditActorResponse` | Thể hiện đây là tác nhân của sự kiện kiểm toán |
| `Address` trong billing | `BillingAddress` | Nêu rõ vai trò địa chỉ thanh toán |
| `Address` trong shipping | `ShippingAddress` | Phân biệt địa chỉ giao hàng |
| `ErrorResponse` của inventory | `InventoryErrorResponse` | Tránh đụng tên lỗi dùng chung |
| `Status` của payment | `PaymentStatus` | Tránh tên chung chung và dễ xung đột |

Ưu tiên tên ổn định theo miền nghiệp vụ hoặc hợp đồng API. Tránh đặt tên chỉ dựa trên tên package nội bộ nếu package có thể thay đổi thường xuyên.

## 3. Tham chiếu schema đúng từ request và response

Khi controller sử dụng DTO đã được đặt tên, Springdoc có thể tạo schema và tham chiếu từ operation. Ví dụ:

```java
package com.example.account.web;

import com.example.account.api.UserResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/accounts")
class AccountController {

    @GetMapping("/{id}")
    UserResponse getUser(@PathVariable Long id) {
        return accountService.getUser(id);
    }
}
```

Và controller kiểm toán:

```java
package com.example.audit.web;

import com.example.audit.api.UserResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/audit/actors")
class AuditActorController {

    @GetMapping("/{actorId}")
    UserResponse getActor(@PathVariable String actorId) {
        return auditService.getActor(actorId);
    }
}
```

Tài liệu OpenAPI có thể biểu diễn hai response bằng các tham chiếu độc lập:

```yaml
paths:
  /api/accounts/{id}:
    get:
      responses:
        '200':
          description: Thông tin người dùng tài khoản
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/AccountUserResponse'
  /api/audit/actors/{actorId}:
    get:
      responses:
        '200':
          description: Thông tin tác nhân kiểm toán
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/AuditActorResponse'
```

Trong ứng dụng thật, Springdoc tạo các `$ref` từ kiểu tham số, kiểu trả về và metadata annotation. Không cần tự viết JSON/YAML đầu ra chỉ để đổi tên schema; hãy đặt tên tại DTO hoặc cơ chế tùy biến mô hình được hỗ trợ.

## 4. Đặt tên schema cho DTO lồng nhau và generic type

Xung đột tên không chỉ xảy ra với DTO được controller trả về trực tiếp. Nó còn có thể xuất hiện trong cấu trúc lồng nhau hoặc kiểu generic.

Ví dụ một response dùng chung:

```java
public record ApiEnvelope<T>(
    String requestId,
    T data
) {
}
```

Các API có thể dùng envelope với kiểu dữ liệu khác nhau:

```java
ApiEnvelope<com.example.account.api.UserResponse>
ApiEnvelope<com.example.audit.api.UserResponse>
```

Tên schema của generic wrapper có thể được xử lý khác nhau theo resolver và phiên bản thư viện; phần quan trọng là schema của từng kiểu `data` phải tiếp tục tham chiếu đúng component riêng. Không cố gán cùng một tên cố định cho mọi biến thể generic nếu chúng có cấu trúc khác nhau. Sau khi thay đổi tên DTO hoặc cách biểu diễn generic, hãy kiểm tra `components.schemas` và các `$ref` được sinh ra.

Với DTO lồng nhau, cũng nên đặt tên rõ cho các kiểu được tái sử dụng:

```java
@Schema(name = "ShippingAddress")
public record Address(String street, String city, String postalCode) {
}

@Schema(name = "ShipmentResponse")
public record ShipmentResponse(
    String shipmentId,
    Address destination
) {
}
```

Nếu một lớp lồng nhau chỉ dùng nội bộ và không trở thành component riêng, không nhất thiết phải ép tên cho mọi kiểu. Hãy ưu tiên các schema được tham chiếu từ nhiều operation hoặc có ý nghĩa công khai trong hợp đồng.

## 5. Dùng `springdoc.use-fqn` khi cần quy ước toàn dự án

Springdoc có thuộc tính `springdoc.use-fqn` để sử dụng fully qualified name của lớp khi đặt tên schema. Có thể cấu hình:

```yaml
springdoc:
  use-fqn: true
```

Hoặc:

```properties
springdoc.use-fqn=true
```

Khi bật, tên schema được xây dựng từ tên đầy đủ của lớp thay vì chỉ dựa trên tên đơn giản, qua đó giảm nguy cơ hai lớp ở package khác nhau bị trùng tên. Ví dụ, các kiểu `com.example.account.api.UserResponse` và `com.example.audit.api.UserResponse` có thể được biểu diễn bằng tên gắn với package đầy đủ trong tài liệu.

Đây là tùy chọn cấp ứng dụng, vì vậy có thể ảnh hưởng đến nhiều schema trong tài liệu. Trước khi bật trong một API đã phát hành, cần kiểm tra:

- Tên component thực tế mà phiên bản Springdoc đang dùng sinh ra.
- Cú pháp `$ref` và khả năng đọc của validator, Swagger UI, client generator.
- Tên class được sinh trong SDK và tác động đến mã nguồn client hiện tại.
- Các tài liệu group và file OpenAPI đã lưu có cần cập nhật đồng bộ không.

Tên đầy đủ thường dài hơn và làm lộ cấu trúc package nội bộ. Một số công cụ sinh mã có thể chuyển dấu chấm hoặc ký tự đặc biệt theo quy tắc riêng. Vì vậy, `springdoc.use-fqn` phù hợp khi nhóm muốn một chính sách đặt tên tự động trên diện rộng và đã kiểm chứng công cụ tiếp nhận. Với hợp đồng công khai cần tên ổn định, `@Schema(name = ...)` thường dễ kiểm soát hơn.

Tùy chọn này cũng cần được đối chiếu với đúng phiên bản Springdoc trong dự án. Nếu thuộc tính không được phiên bản đang dùng hỗ trợ, cấu hình có thể không tạo ra hiệu quả mong đợi; hãy kiểm tra tài liệu và kết quả thực tế.

## 6. Chọn giữa tên tường minh và fully qualified name

| Tiêu chí | `@Schema(name = ...)` | `springdoc.use-fqn: true` |
|---|---|---|
| Phạm vi | Từng schema cụ thể | Quy ước cấp ứng dụng |
| Tên trong hợp đồng | Ngắn, có ý nghĩa nghiệp vụ | Gắn với package/lớp Java |
| Kiểm soát tên | Chủ động từng DTO | Tự động theo tên đầy đủ |
| Tác động khi refactor package | Tên schema có thể giữ nguyên | Tên schema có thể đổi theo package |
| Phù hợp | API công khai, tên schema cần ổn định | Dự án lớn muốn tránh xung đột tự động trên diện rộng |

Có thể kết hợp hai cách theo nhu cầu, nhưng phải kiểm tra cách phiên bản Springdoc ưu tiên tên tường minh so với chính sách FQN. Không nên giả định mọi phiên bản đều xử lý hai cấu hình theo cùng một thứ tự. Nếu hợp đồng cần ổn định, hãy đặt tên tường minh cho schema công khai và xác minh kết quả khi bật tùy chọn toàn cục.

## 7. Không dùng một tên schema cho hai cấu trúc khác nhau

`components.schemas` là nơi lưu các schema được tham chiếu trong cùng một OpenAPI document. Một khóa component chỉ nên đại diện cho một cấu trúc và ý nghĩa nhất quán.

Ví dụ không nên đặt cả hai lớp khác nhau thành `UserResponse`:

```java
@Schema(name = "UserResponse")
public record AccountUserResponse(Long id, String displayName) {
}

@Schema(name = "UserResponse")
public record AuditActorResponse(String actorId, String action) {
}
```

Hai lớp có ý nghĩa và thuộc tính khác nhau nhưng cùng yêu cầu một component name. Kết quả có thể phụ thuộc thứ tự resolver hoặc cách thư viện xử lý trùng tên; tài liệu có nguy cơ không còn phản ánh đúng kiểu của một operation. Hãy đổi thành hai tên riêng:

```java
@Schema(name = "AccountUserResponse")
public record AccountUserResponse(Long id, String displayName) {
}

@Schema(name = "AuditActorResponse")
public record AuditActorResponse(String actorId, String action) {
}
```

Nếu hai lớp thực sự có cùng cấu trúc và ý nghĩa, cân nhắc dùng chung một DTO ở module API phù hợp để tránh định nghĩa trùng lặp. Nếu chúng có cùng cấu trúc nhưng khác ngữ nghĩa hoặc có khả năng tiến hóa độc lập, giữ kiểu riêng và đặt schema name riêng. Đừng gộp hai kiểu chỉ vì hiện tại chúng có cùng danh sách field.

## 8. Tên schema là một phần của hợp đồng dành cho công cụ

Một số client generator sử dụng tên trong `components.schemas` để đặt tên class/model trong SDK. Ví dụ, schema `AccountUserResponse` có thể sinh thành lớp `AccountUserResponse` trong Java hoặc tên tương ứng theo ngôn ngữ đích.

Vì vậy, đổi schema name có thể không làm thay đổi JSON payload trên HTTP nhưng vẫn tác động đến mã nguồn client được sinh lại. Nếu client đang tham chiếu model cũ, việc đổi tên có thể tạo thay đổi source-level hoặc buộc client cập nhật import/type name.

Khi API đã phát hành:

1. Chọn quy ước tên component trước khi công bố tài liệu.
2. Giữ tên schema ổn định qua các lần refactor package Java.
3. Nếu phải đổi tên, kiểm tra diff OpenAPI và mã nguồn SDK được sinh.
4. Ghi nhận tác động trong release note và phối hợp với nhóm client.
5. Không xem đổi schema name là thay đổi vô hại chỉ vì JSON runtime không đổi.

Tên lớp Java là chi tiết triển khai có thể refactor; tên component OpenAPI có thể đã trở thành tên công khai mà công cụ và nhóm tích hợp phụ thuộc.

## 9. Nhiều OpenAPI group có namespace schema riêng

Springdoc có thể tạo nhiều tài liệu thông qua `GroupedOpenApi`, ví dụ group cho account và audit. Mỗi tài liệu OpenAPI là một document riêng, vì vậy mỗi document có object `components.schemas` riêng.

Ví dụ:

```java
@Bean
GroupedOpenApi accountApi() {
    return GroupedOpenApi.builder()
        .group("account")
        .pathsToMatch("/api/accounts/**")
        .build();
}

@Bean
GroupedOpenApi auditApi() {
    return GroupedOpenApi.builder()
        .group("audit")
        .pathsToMatch("/api/audit/**")
        .build();
}
```

Hai URL tài liệu thường có dạng `/v3/api-docs/account` và `/v3/api-docs/audit`. Một schema có tên `UserResponse` trong tài liệu account không xung đột trực tiếp với một schema cùng tên trong tài liệu audit vì chúng thuộc hai document khác nhau.

Tuy nhiên, nếu một group chứa cả hai controller và cả hai DTO cùng tên đơn giản, xung đột vẫn có thể xảy ra trong document đó. Việc tách group chỉ giải quyết phạm vi namespace khi các kiểu được đưa vào các tài liệu độc lập; nó không thay thế quy ước đặt tên schema.

## 10. Xử lý schema từ thư viện ngoài hoặc lớp không thể sửa annotation

Không phải lúc nào cũng có thể gắn `@Schema(name = ...)` lên lớp. Một DTO có thể đến từ thư viện bên thứ ba, module dùng chung không thuộc quyền sửa hoặc lớp sinh tự động.

Một số hướng xử lý:

- Tạo API DTO/wrapper riêng trong module của ứng dụng, rồi ánh xạ từ kiểu thư viện sang DTO đó.
- Dùng cấu hình hoặc cơ chế model converter mà phiên bản Swagger Core/Springdoc hỗ trợ để kiểm soát schema resolution.
- Dùng `OpenApiCustomizer` để điều chỉnh mô hình sau khi sinh khi cần thay đổi metadata hoặc tham chiếu có kiểm soát.
- Cân nhắc `springdoc.use-fqn` nếu chính sách tên đầy đủ phù hợp với toàn ứng dụng.

Wrapper DTO thường dễ bảo trì nhất khi kiểu thư viện không nên trở thành một phần của hợp đồng công khai. Customizer có thể sửa tên component nhưng cần đồng bộ mọi `$ref` trỏ đến tên cũ; nếu chỉ đổi khóa mà quên cập nhật tham chiếu, tài liệu sẽ không hợp lệ. Với thay đổi sâu vào model resolution, hãy ưu tiên cơ chế chính thức của đúng phiên bản thư viện và kiểm thử bằng validator.

## 11. Kiểm tra `components.schemas` và `$ref` sau khi sinh tài liệu

Sau khi đặt tên, mở endpoint OpenAPI, thường là `/v3/api-docs`, và kiểm tra object `components.schemas`. Có thể dùng `curl` cùng `jq`:

```bash
curl -s http://localhost:8080/v3/api-docs | jq '.components.schemas | keys'
```

Kiểm tra schema cụ thể:

```bash
curl -s http://localhost:8080/v3/api-docs | jq '.components.schemas.AccountUserResponse'
curl -s http://localhost:8080/v3/api-docs | jq '.components.schemas.AuditActorResponse'
```

Kiểm tra operation có tham chiếu đúng schema:

```bash
curl -s http://localhost:8080/v3/api-docs | jq '.paths["/api/accounts/{id}"].get.responses["200"].content["application/json"].schema'
```

Đầu ra mong đợi có `$ref` tương ứng:

```json
{
  "$ref": "#/components/schemas/AccountUserResponse"
}
```

Với tài liệu group, gọi đúng URL của từng group. Nếu chỉ kiểm tra tài liệu mặc định, có thể bỏ sót xung đột chỉ xuất hiện khi một group bao gồm nhiều package.

## 12. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Hai DTO khác package có schema cùng tên | Resolver dùng tên đơn giản hoặc metadata đặt trùng | Đặt `@Schema(name = ...)` riêng cho từng DTO |
| Response của controller trỏ đến schema không đúng | Schema name bị trùng hoặc resolver chọn model không như dự kiến | Kiểm tra kiểu Java, `components.schemas` và `$ref` |
| Bật `use-fqn` làm tên model SDK thay đổi | Component name giờ phụ thuộc tên đầy đủ/package | Review diff OpenAPI và kiểm tra client generator trước khi phát hành |
| Đổi package làm tên schema thay đổi | Hợp đồng đang phụ thuộc FQN | Đặt tên tường minh để tách tên công khai khỏi package nội bộ |
| Customizer đổi tên schema nhưng tài liệu báo unresolved reference | Một số `$ref` vẫn dùng tên cũ | Cập nhật đồng bộ component key và mọi tham chiếu; chạy validator |
| Một group hoạt động nhưng group khác có schema sai | Group sau chứa thêm kiểu cùng tên | Kiểm tra từng group và đặt tên duy nhất trong mỗi document |
| Schema từ thư viện ngoài khó đổi tên | Không thể gắn annotation lên lớp nguồn | Dùng wrapper DTO hoặc model converter phù hợp |

## 13. Checklist đặt tên schema an toàn

- [ ] Đã xác định các DTO có cùng tên đơn giản trong những package/module khác nhau.
- [ ] Mỗi schema công khai có tên duy nhất trong `components.schemas` của document.
- [ ] Đã dùng `@Schema(name = ...)` cho các kiểu dễ xung đột.
- [ ] Tên schema phản ánh ngữ nghĩa API thay vì phụ thuộc hoàn toàn vào package Java.
- [ ] Không gán cùng một schema name cho hai cấu trúc hoặc ý nghĩa khác nhau.
- [ ] Đã đánh giá `springdoc.use-fqn` nếu muốn áp dụng quy ước toàn cục.
- [ ] Đã kiểm tra generic wrapper và DTO lồng nhau.
- [ ] Đã kiểm tra các group document có chứa nhiều kiểu trùng tên.
- [ ] Mọi `$ref` đều trỏ đến schema tồn tại và đúng cấu trúc.
- [ ] Đã xem xét tác động của việc đổi schema name đến client generator/SDK.
- [ ] Đã chạy validator OpenAPI hoặc kiểm tra tài liệu bằng công cụ tương thích.

Tên schema trong OpenAPI là khóa tham chiếu của hợp đồng, không phải namespace Java. Khi nhiều lớp có cùng tên đơn giản, hãy đặt tên component theo ngữ nghĩa API bằng `@Schema(name = ...)`, hoặc áp dụng quy ước FQN sau khi kiểm tra tác động toàn dự án. Đảm bảo tên duy nhất, ổn định và mọi `$ref` trỏ đúng schema sẽ giúp tài liệu Springdoc rõ ràng, tránh nhầm lẫn và giữ client SDK nhất quán.
