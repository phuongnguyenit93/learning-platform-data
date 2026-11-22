# Thay @ApiModel và @ApiModelProperty bằng mô tả @Schema

Springfox Swagger 2 và springdoc-openapi dùng hai thế hệ annotation khác nhau để mô tả model API. Khi chuyển dự án sang springdoc-openapi, các annotation @ApiModel và @ApiModelProperty thuộc package io.swagger.annotations cần được thay bằng @Schema thuộc package io.swagger.v3.oas.annotations.media.

@ApiModel thường mô tả tên và ý nghĩa của một model; @ApiModelProperty mô tả từng thuộc tính như nội dung, ví dụ, kiểu, giá trị cho phép, trạng thái bắt buộc hoặc khả năng đọc/ghi. Trong OpenAPI 3, @Schema đảm nhiệm phần lớn những vai trò này và cung cấp thêm các metadata phù hợp với Schema Object.

Việc thay annotation không nên chỉ là đổi tên import. Cần rà soát ngữ nghĩa của từng thuộc tính, phân biệt validation runtime với mô tả tài liệu, kiểm tra request/response DTO và xác nhận OpenAPI document sau khi migration.

## 1. Nhận diện annotation cũ và mới

| Mục đích | Springfox / Swagger 2 | Swagger Core / OpenAPI 3 |
|---|---|---|
| Mô tả model class | @ApiModel | @Schema |
| Mô tả property/field | @ApiModelProperty | @Schema |
| Tên model | @ApiModel(value = ...) | @Schema(name = ...) |
| Mô tả model | @ApiModel(description = ...) | @Schema(description = ...) |
| Mô tả property | @ApiModelProperty(value = ...) | @Schema(description = ...) |
| Ví dụ | @ApiModelProperty(example = ...) | @Schema(example = ...) |
| Field bắt buộc | @ApiModelProperty(required = true) | @Schema(requiredMode = Schema.RequiredMode.REQUIRED) |
| Ẩn field | @ApiModelProperty(hidden = true) | @Schema(hidden = true) |
| Chỉ đọc | @ApiModelProperty(readOnly = true) | @Schema(accessMode = Schema.AccessMode.READ_ONLY) |
| Chỉ ghi | Cấu hình access tương ứng | @Schema(accessMode = Schema.AccessMode.WRITE_ONLY) |

Annotation mới thuộc Swagger Core v3, thường được springdoc-openapi sử dụng để sinh OpenAPI document. Import đúng package là bước đầu tiên:

~~~java
// Swagger 2 / Springfox
import io.swagger.annotations.ApiModel;
import io.swagger.annotations.ApiModelProperty;

// OpenAPI 3 / springdoc-openapi
import io.swagger.v3.oas.annotations.media.Schema;
~~~

Không giữ đồng thời annotation cũ và mới trên cùng một DTO với kỳ vọng springdoc sẽ hiểu cả hai. Springdoc tập trung vào annotation OpenAPI 3; annotation Springfox có thể bị bỏ qua.

## 2. Thay @ApiModel ở cấp class

Ví dụ model cũ:

~~~java
import io.swagger.annotations.ApiModel;

@ApiModel(
        value = "Customer",
        description = "Thông tin khách hàng"
)
public class Customer {
    private String code;
    private String name;
}
~~~

Sau khi chuyển sang @Schema:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(
        name = "Customer",
        description = "Thông tin khách hàng"
)
public class Customer {
    private String code;
    private String name;
}
~~~

Các thuộc tính thường dùng:

| @ApiModel | @Schema | Ghi chú |
|---|---|---|
| value | name | Tên schema trong components.schemas |
| description | description | Mô tả model |
| discriminator | discriminatorProperty | Tên property dùng phân biệt subtype |
| subTypes | oneOf hoặc subTypes | Chọn cách mô tả polymorphism phù hợp |

Không phải mọi thuộc tính của @ApiModel đều có phép thay thế trực tiếp. Ví dụ, nếu model dùng discriminator và subtype, hãy thiết kế lại schema theo OpenAPI 3 với oneOf/allOf và discriminator mapping thay vì chỉ đổi tên annotation.

## 3. Thay @ApiModelProperty mô tả thông thường

Model cũ:

~~~java
import io.swagger.annotations.ApiModel;
import io.swagger.annotations.ApiModelProperty;

@ApiModel(value = "CreateCustomerRequest")
public class CreateCustomerRequest {

    @ApiModelProperty(
            value = "Mã khách hàng",
            example = "CUS-100",
            required = true
    )
    private String code;

    @ApiModelProperty(
            value = "Tên hiển thị của khách hàng",
            example = "Nguyen Van An"
    )
    private String displayName;
}
~~~

Model sau migration:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(
        name = "CreateCustomerRequest",
        description = "Dữ liệu dùng để tạo khách hàng"
)
public class CreateCustomerRequest {

    @Schema(
            description = "Mã khách hàng",
            example = "CUS-100",
            requiredMode = Schema.RequiredMode.REQUIRED
    )
    private String code;

    @Schema(
            description = "Tên hiển thị của khách hàng",
            example = "Nguyen Van An"
    )
    private String displayName;
}
~~~

Trong @ApiModelProperty, thuộc tính value thường được dùng làm mô tả. Với @Schema, dùng description để diễn đạt ý nghĩa của property. Không nhầm name với description: name đổi tên property trong schema, còn description chỉ bổ sung nội dung giải thích.

## 4. Phân biệt name và description

name dùng khi tên property trong OpenAPI cần khác tên Java hoặc cần cố định tên schema. Ví dụ:

~~~java
@Schema(
        name = "customerName",
        description = "Tên hiển thị của khách hàng"
)
private String displayName;
~~~

Nếu Jackson đã đổi tên JSON property bằng @JsonProperty, cần kiểm tra tên cuối cùng mà springdoc sinh ra. Không đặt @Schema(name = ...) chỉ để lặp lại tên Java trong khi Jackson đã cung cấp tên wire-format chính xác.

Nên giữ tên property nhất quán với JSON request/response thực tế. Nếu tài liệu mô tả customerName nhưng server nhận displayName, client được sinh từ OpenAPI có thể gửi sai payload.

## 5. Thay required bằng requiredMode

Springfox thường dùng:

~~~java
@ApiModelProperty(required = true)
private String email;
~~~

Trong Swagger Core v3, nên dùng:

~~~java
@Schema(requiredMode = Schema.RequiredMode.REQUIRED)
private String email;
~~~

Các giá trị chính của RequiredMode:

| Giá trị | Ý nghĩa |
|---|---|
| REQUIRED | Đánh dấu property bắt buộc trong schema |
| NOT_REQUIRED | Đánh dấu property không bắt buộc |
| AUTO | Để thư viện suy luận theo metadata và cấu hình |

Required chỉ trả lời property có phải xuất hiện trong object hay không. Nó không có nghĩa giá trị được phép null hay không. Ví dụ, property có thể bắt buộc xuất hiện nhưng schema vẫn cho phép null nếu được mô tả như vậy.

Để validation runtime có hiệu lực, dùng Bean Validation như @NotNull, @NotBlank hoặc @NotEmpty và cấu hình validation cho ứng dụng. @Schema(requiredMode = REQUIRED) chỉ mô tả hợp đồng OpenAPI; nó không tự kiểm tra request khi chạy.

## 6. Kết hợp @Schema với Bean Validation

Một DTO thường cần cả metadata OpenAPI và constraint runtime:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

@Schema(name = "CreateCustomerRequest")
public record CreateCustomerRequest(
        @Schema(
                description = "Địa chỉ email khách hàng",
                example = "an@example.com",
                requiredMode = Schema.RequiredMode.REQUIRED
        )
        @NotBlank
        @Email
        @Size(max = 254)
        String email,

        @Schema(
                description = "Tên hiển thị",
                example = "Nguyen Van An"
        )
        @Size(max = 120)
        String displayName
) {}
~~~

Trong ví dụ:

- @Schema bổ sung mô tả và example cho OpenAPI.
- @NotBlank yêu cầu chuỗi không null và có ít nhất một ký tự không phải khoảng trắng khi validation chạy.
- @Email kiểm tra định dạng email theo validator đang dùng.
- @Size giới hạn độ dài.

Springdoc có thể đọc các constraint Bean Validation để bổ sung required hoặc giới hạn tương ứng vào schema. Tuy nhiên, cách suy luận phụ thuộc phiên bản, annotation đặt ở đâu và cấu hình dự án. Hãy kiểm tra document được sinh thay vì giả định mọi constraint đều được phản ánh.

## 7. Thay example và allowableValues

Springfox:

~~~java
@ApiModelProperty(
        value = "Trạng thái tài khoản",
        example = "ACTIVE",
        allowableValues = "ACTIVE,INACTIVE,SUSPENDED"
)
private String status;
~~~

OpenAPI 3:

~~~java
@Schema(
        description = "Trạng thái tài khoản",
        example = "ACTIVE",
        allowableValues = {
                "ACTIVE",
                "INACTIVE",
                "SUSPENDED"
        }
)
private String status;
~~~

Nếu tập giá trị là một miền cố định trong Java, nên cân nhắc dùng enum:

~~~java
public enum AccountStatus {
    ACTIVE,
    INACTIVE,
    SUSPENDED
}
~~~

Sau đó dùng AccountStatus làm kiểu property. Cách này giúp kiểu dữ liệu trong code và enum trong OpenAPI có cùng nguồn định nghĩa. Nếu cần mô tả riêng từng enum value, bổ sung schema metadata hoặc mô tả enum theo khả năng của phiên bản Swagger Core đang dùng.

allowableValues trong annotation là metadata tài liệu. Nó không tự từ chối giá trị ngoài danh sách ở runtime; dùng enum, Bean Validation hoặc logic nghiệp vụ để thực thi.

## 8. Thay dataType bằng kiểu Java thực

Một số model cũ dùng dataType để ép kiểu tài liệu:

~~~java
@ApiModelProperty(dataType = "java.lang.Long")
private String customerId;
~~~

Đây thường là dấu hiệu kiểu Java và tài liệu đang không thống nhất. Ưu tiên sửa kiểu thuộc tính thành Long nếu giá trị thực sự là số:

~~~java
@Schema(
        description = "Mã khách hàng",
        format = "int64",
        example = "10001"
)
private Long customerId;
~~~

Nếu không thể đổi kiểu Java vì hợp đồng wire-format hoặc tương thích ngược, chỉ override schema sau khi xác định rõ JSON thực tế được serialize thành kiểu gì. Có thể dùng type, format hoặc implementation của @Schema khi cần, nhưng không ép schema thành integer nếu Jackson vẫn gửi chuỗi.

Nguyên tắc là kiểu trong OpenAPI phải phản ánh dữ liệu thực tế trên HTTP, không chỉ phản ánh ý định của developer.

## 9. Thay hidden

Springfox:

~~~java
@ApiModelProperty(hidden = true)
private String internalNote;
~~~

OpenAPI 3:

~~~java
@Schema(hidden = true)
private String internalNote;
~~~

hidden yêu cầu springdoc không đưa property vào schema được sinh theo cấu hình tương ứng. Đây là lựa chọn trình bày tài liệu, không phải cơ chế bảo vệ dữ liệu.

Nếu field chứa thông tin bí mật, cần loại bỏ nó khỏi response DTO hoặc cấu hình serialization và authorization phù hợp. Không dựa vào hidden để ngăn server trả dữ liệu nhạy cảm.

## 10. Thay readOnly và writeOnly

Springfox có thể dùng thuộc tính readOnly để mô tả field chỉ đọc. OpenAPI 3 dùng accessMode:

~~~java
@Schema(
        description = "Mã khách hàng do hệ thống cấp",
        accessMode = Schema.AccessMode.READ_ONLY
)
private UUID id;
~~~

Field chỉ ghi:

~~~java
@Schema(
        description = "Mật khẩu dùng khi tạo tài khoản",
        accessMode = Schema.AccessMode.WRITE_ONLY
)
private String password;
~~~

Các chế độ:

| AccessMode | Ý nghĩa |
|---|---|
| READ_ONLY | Chỉ đọc, thường được gửi trong response |
| WRITE_ONLY | Chỉ ghi, thường được nhận trong request |
| READ_WRITE | Có thể đọc và ghi |
| AUTO | Để thư viện suy luận |

readOnly/writeOnly là metadata trong schema. Chúng không tự thay đổi Jackson serialization, không xóa field khỏi object và không thay thế kiểm soát quyền truy cập. Với API có request/response khác nhau, tách CreateRequest và Response DTO thường rõ ràng và an toàn hơn việc dùng chung một class.

## 11. Thay notes và mô tả dài

Springfox:

~~~java
@ApiModelProperty(
        value = "Số điện thoại",
        notes = "Sử dụng mã quốc gia, ví dụ +84901234567"
)
private String phone;
~~~

OpenAPI 3:

~~~java
@Schema(
        description = "Số điện thoại. Sử dụng mã quốc gia, ví dụ +84901234567",
        example = "+84901234567"
)
private String phone;
~~~

@Schema dùng description làm nội dung giải thích. Nếu mô tả dài, có thể viết rõ quy tắc định dạng, đơn vị, múi giờ hoặc điều kiện nghiệp vụ. Không đưa thông tin bí mật, dữ liệu cá nhân thật hoặc nội dung không phù hợp để công bố vào example.

## 12. Thay position và thứ tự property

@ApiModelProperty có thuộc tính position trong một số phiên bản Springfox. @Schema không có thuộc tính position tương đương để bảo đảm thứ tự hiển thị property.

Không nên xem thứ tự field trong Swagger UI là một phần hợp đồng API. Client phải dựa vào tên và schema property, không dựa vào vị trí hiển thị.

Nếu cần kiểm soát thứ tự JSON thực tế, đó là vấn đề serialization của Jackson, ví dụ @JsonPropertyOrder. Hãy phân biệt:

- Thứ tự property trong JSON serialization.
- Thứ tự hiển thị trong tài liệu.
- Ngữ nghĩa schema mà client sử dụng.

Không thêm annotation chỉ để giữ một thứ tự hiển thị cũ nếu thứ tự đó không có ý nghĩa với consumer.

## 13. Thay discriminator và subtype của model

Với model đa hình, @ApiModel có thể khai báo discriminator và subtype. OpenAPI 3 mô tả quan hệ này bằng discriminator, oneOf, anyOf hoặc allOf.

Ví dụ model thanh toán:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(
        name = "Payment",
        description = "Thông tin thanh toán",
        discriminatorProperty = "kind",
        oneOf = {
                CardPayment.class,
                BankTransferPayment.class
        }
)
public interface Payment {
}
~~~

Các subtype:

~~~java
@Schema(name = "CardPayment")
public record CardPayment(
        @Schema(example = "card")
        String kind,
        String last4
) implements Payment {}

@Schema(name = "BankTransferPayment")
public record BankTransferPayment(
        @Schema(example = "bank")
        String kind,
        String bankCode
) implements Payment {}
~~~

Ví dụ trên mô tả hai nhánh của Payment. Với hợp đồng production, cần kiểm tra discriminator mapping và cách Jackson chọn subtype khi deserialize. Có thể cần @JsonTypeInfo/@JsonSubTypes hoặc cấu hình polymorphic serialization tương ứng.

Không giả định discriminator trong OpenAPI tự làm Jackson nhận diện subtype. Hai phần phải được cấu hình đồng bộ.

## 14. Tách request DTO và response DTO

Một số model Springfox cũ dùng chung một class cho cả request và response, sau đó đánh dấu field bằng readOnly hoặc writeOnly. Khi chuyển sang OpenAPI 3, đây là dịp rà soát xem có nên tách DTO hay không.

Ví dụ:

~~~java
@Schema(name = "CreateCustomerRequest")
public record CreateCustomerRequest(
        @Schema(description = "Tên khách hàng", requiredMode = Schema.RequiredMode.REQUIRED)
        String name,
        @Schema(description = "Email", requiredMode = Schema.RequiredMode.REQUIRED)
        String email
) {}

@Schema(name = "CustomerResponse")
public record CustomerResponse(
        @Schema(description = "Mã khách hàng", format = "uuid")
        UUID id,
        String name,
        String email,
        Instant createdAt
) {}
~~~

Request chỉ chứa dữ liệu client được phép gửi. Response chỉ chứa dữ liệu server được phép trả. Cách tách này làm schema dễ hiểu hơn, giảm nguy cơ lộ field nội bộ và hạn chế các annotation readOnly/writeOnly phức tạp.

## 15. Những thuộc tính không có ánh xạ một-một

Không nên chuyển cơ học tất cả thuộc tính của @ApiModelProperty sang @Schema. Một số thuộc tính cũ cần được diễn giải lại:

| Thuộc tính cũ | Hướng xử lý khi migration |
|---|---|
| value | Chuyển sang description |
| name | Chuyển sang name nếu thực sự cần đổi tên trong schema |
| dataType | Ưu tiên sửa kiểu Java; chỉ override type/format/implementation khi có lý do |
| required | Dùng requiredMode và/hoặc Bean Validation |
| allowableValues | Dùng enum hoặc allowableValues; thêm runtime validation |
| readOnly | Dùng accessMode READ_ONLY |
| hidden | Dùng hidden, nhưng kiểm soát dữ liệu bằng DTO/serialization |
| position | Không có tương đương trực tiếp trong @Schema |
| notes | Gộp nội dung phù hợp vào description |
| allowEmptyValue | Đây thường là metadata của parameter; xem lại bằng @Parameter hoặc schema phù hợp |
| reference | Rà soát cách dùng $ref trong OpenAPI 3 thay vì giữ nguyên chuỗi tham chiếu cũ |

Nếu một thuộc tính cũ không còn tương đương, hãy xác định mục đích ban đầu rồi chọn cấu trúc OpenAPI phù hợp. Không tự tạo annotation giả hoặc dùng description để mô phỏng constraint.

## 16. Những annotation Swagger 2 liên quan cần rà soát

Khi chuyển từ Springfox sang springdoc, DTO không phải nơi duy nhất có annotation cũ. Một số annotation thường gặp có thế hệ OpenAPI 3 tương ứng:

| Springfox / Swagger 2 | OpenAPI 3 |
|---|---|
| @Api | @Tag |
| @ApiOperation | @Operation |
| @ApiParam | @Parameter |
| @ApiImplicitParam | @Parameter |
| @ApiResponse | @ApiResponse |
| @ApiResponses | @ApiResponses |
| @ApiModel | @Schema |
| @ApiModelProperty | @Schema |

Lưu ý @ApiResponse của Swagger 2 và OpenAPI 3 có cùng tên đơn giản nhưng khác package và cấu trúc thuộc tính. OpenAPI 3 thường đặt responseCode, description và content rõ ràng hơn.

Không import nhầm:

~~~java
// Swagger 2
import io.swagger.annotations.ApiResponse;

// OpenAPI 3
import io.swagger.v3.oas.annotations.responses.ApiResponse;
~~~

Sau migration, tìm toàn bộ import io.swagger.annotations trong source và quyết định thay thế từng annotation. Không xóa dependency cũ trước khi xử lý hết các tham chiếu còn dùng.

## 17. Ví dụ chuyển đổi một DTO hoàn chỉnh

Trước migration:

~~~java
import io.swagger.annotations.ApiModel;
import io.swagger.annotations.ApiModelProperty;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import java.util.UUID;

@ApiModel(value = "UserProfile", description = "Hồ sơ người dùng")
public class UserProfile {

    @ApiModelProperty(
            value = "Mã người dùng",
            readOnly = true,
            example = "d290f1ee-6c54-4b01-90e6-d701748f0851"
    )
    private UUID id;

    @ApiModelProperty(
            value = "Email đăng nhập",
            required = true,
            example = "user@example.com"
    )
    @NotBlank
    @Email
    private String email;

    @ApiModelProperty(
            value = "Tên hiển thị",
            example = "Minh Anh",
            allowableValues = "Minh Anh,Thanh Ha"
    )
    private String displayName;
}
~~~

Sau migration:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import java.util.UUID;

@Schema(
        name = "UserProfile",
        description = "Hồ sơ người dùng"
)
public class UserProfile {

    @Schema(
            description = "Mã người dùng",
            accessMode = Schema.AccessMode.READ_ONLY,
            example = "d290f1ee-6c54-4b01-90e6-d701748f0851"
    )
    private UUID id;

    @Schema(
            description = "Email đăng nhập",
            requiredMode = Schema.RequiredMode.REQUIRED,
            example = "user@example.com"
    )
    @NotBlank
    @Email
    private String email;

    @Schema(
            description = "Tên hiển thị",
            example = "Minh Anh"
    )
    private String displayName;
}
~~~

Trong ví dụ, allowableValues được bỏ khỏi displayName vì danh sách tên mẫu không phải miền giá trị hợp lệ cố định. Nếu nghiệp vụ thực sự giới hạn tên trong một tập enum, hãy mô hình hóa thành enum hoặc constraint rõ ràng.

## 18. Cập nhật dependency và package import

Springfox và springdoc có dependency và auto-configuration khác nhau. Khi migration hoàn chỉnh:

- Loại bỏ starter Springfox nếu không còn thành phần nào dùng nó.
- Thêm starter springdoc phù hợp với Spring MVC hoặc WebFlux.
- Thay import io.swagger.annotations bằng io.swagger.v3.oas.annotations.
- Kiểm tra không còn dependency Swagger 2 kéo theo phiên bản swagger-model cũ gây xung đột.
- Dùng một thế hệ annotation thống nhất trong DTO và controller.

Với Spring Boot 3, springdoc 2.x là dòng starter tương ứng. Spring Boot 2 thường dùng dòng springdoc 1.x. Cần chọn phiên bản cụ thể theo ma trận tương thích chính thức của springdoc và Spring Boot trong dự án.

Không chỉ thêm springdoc starter rồi để nguyên toàn bộ cấu hình Springfox. Hai thư viện có cách tích hợp và cách tạo document khác nhau; giữ cả hai có thể gây endpoint trùng, cấu hình khó đoán hoặc dependency conflict.

## 19. Kiểm tra OpenAPI document sau migration

Sau khi thay annotation, khởi động ứng dụng và tải:

~~~bash
curl -fS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Kiểm tra schema:

~~~bash
jq '.components.schemas.UserProfile' openapi.json
~~~

Kiểm tra các điểm quan trọng:

- Schema name còn đúng là UserProfile.
- Description của model và property đã được giữ.
- Field id có readOnly/accessMode đúng.
- Field email có required và constraint phù hợp.
- Example không bị mất hoặc trở thành dữ liệu không hợp lệ.
- Property name khớp JSON thực tế sau Jackson serialization.
- Không còn schema trùng tên hoặc component tham chiếu bị hỏng.
- Request và response của operation tham chiếu đúng schema.

Nếu dùng Swagger UI, kiểm tra model hiển thị và thử request mẫu. Nhưng UI chỉ là một consumer; vẫn nên parse và validate document bằng công cụ OpenAPI.

## 20. Kiểm thử runtime song song với tài liệu

Annotation @Schema không thay thế validation và serialization. Sau khi migration, chạy test cho payload thật:

~~~java
@Test
void createUserRejectsMissingEmail() {
    webTestClient.post()
            .uri("/api/users")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("""
                    {
                      "displayName": "Minh Anh"
                    }
                    """)
            .exchange()
            .expectStatus().isBadRequest();
}
~~~

Đồng thời kiểm tra response không chứa field write-only hoặc dữ liệu nội bộ. Nếu DTO dùng chung request/response, hãy xác nhận Jackson và validation hoạt động đúng ở cả hai chiều.

Một migration annotation có thể làm tài liệu thay đổi nhưng không làm runtime thay đổi. Dù vậy, client generator đọc document mới có thể sinh kiểu hoặc method khác, nên cần kiểm tra compatibility của SDK.

## 21. Lỗi thường gặp khi thay annotation

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| @Schema không được nhận diện | Import nhầm package hoặc thiếu Swagger Core qua springdoc starter | Dùng io.swagger.v3.oas.annotations.media.Schema và kiểm tra dependency |
| Schema vẫn không có description | Annotation cũ còn sót hoặc @Schema đặt ở vị trí không được introspect | Kiểm tra field/getter/record component và OpenAPI output |
| Field bắt buộc biến mất | Chỉ đổi required sang annotation sai hoặc validation không được nhận | Dùng requiredMode và kiểm tra Bean Validation |
| Field null bị coi là optional | Nhầm required với nullable | Xác minh riêng required và nullability |
| Tên property bị đổi ngoài ý muốn | Dùng @Schema(name) không khớp Jackson | Đồng bộ @JsonProperty và schema name |
| Kiểu dữ liệu trong docs sai runtime | Ép dataType/type nhưng Java/Jackson vẫn serialize kiểu khác | Dùng kiểu Java thực hoặc override có kiểm chứng |
| Field hidden vẫn xuất hiện trong JSON runtime | Nhầm hidden với serialization/security | Dùng DTO hoặc Jackson để loại bỏ dữ liệu |
| readOnly không ngăn client gửi field | readOnly chỉ là metadata OpenAPI | Validation và xử lý request ở server |
| Enum không phản ánh allowableValues | Giá trị cũ là chuỗi mô tả, không phải tập enum thật | Dùng enum hoặc constraint chính xác |
| Discriminator không deserialize đúng | Chỉ cấu hình OpenAPI, chưa cấu hình Jackson polymorphism | Đồng bộ @JsonTypeInfo/@JsonSubTypes |
| Annotation trùng package | Cùng tên @ApiResponse từ Swagger 2 và OpenAPI 3 | Xóa import cũ và dùng package v3 |
| Springfox và springdoc cùng tạo docs | Dependency cũ chưa được loại bỏ | Gỡ starter/config Springfox sau khi migration annotation |

## 22. Checklist migration

- [ ] Đã xác định toàn bộ class dùng @ApiModel.
- [ ] Đã xác định toàn bộ field/getter dùng @ApiModelProperty.
- [ ] Đã thay package import sang Swagger Core v3.
- [ ] Đã đổi value thành description và value/name theo đúng mục đích.
- [ ] Đã rà soát required, nullable và Bean Validation riêng biệt.
- [ ] Đã chuyển example và allowableValues có ý nghĩa.
- [ ] Đã chuyển hidden và readOnly/writeOnly với hiểu biết về giới hạn runtime.
- [ ] Đã xử lý dataType và kiểu Java/Jackson thực tế.
- [ ] Đã rà soát discriminator và subtype.
- [ ] Đã quyết định cách xử lý position và các thuộc tính không có tương đương.
- [ ] Đã tìm các annotation Swagger 2 liên quan còn sót.
- [ ] Đã loại dependency Springfox khi không còn sử dụng.
- [ ] Đã kiểm tra /v3/api-docs và components.schemas.
- [ ] Đã chạy runtime test và contract test.

## 23. Nguyên tắc thiết kế

- Dùng @Schema ở cấp class để đặt tên và mô tả model.
- Dùng @Schema ở field, getter hoặc record component để mô tả property.
- Dùng description cho nội dung giải thích, name cho tên schema/property.
- Dùng requiredMode để diễn đạt field bắt buộc và Bean Validation để thực thi runtime.
- Dùng enum hoặc constraint thực tế thay cho allowableValues chỉ mang tính trang trí.
- Dùng accessMode cho readOnly/writeOnly nhưng không xem đó là security control.
- Không ép kiểu tài liệu khác với kiểu JSON được serialize.
- Rà soát discriminator và Jackson polymorphism cùng nhau.
- Tách request/response DTO khi chúng có trách nhiệm hoặc field khác nhau.
- Kiểm tra OpenAPI document và runtime payload sau khi migration.

## Kết luận

Khi chuyển từ Springfox Swagger 2 sang springdoc-openapi, thay @ApiModel bằng @Schema ở cấp class và @ApiModelProperty bằng @Schema ở cấp property. Các thuộc tính phổ biến như tên, mô tả, ví dụ, required, hidden và readOnly có cách diễn đạt tương ứng, nhưng không phải mọi thuộc tính cũ đều có ánh xạ một-một. Đặc biệt, required khác nullable, hidden/readOnly không bảo vệ dữ liệu runtime, còn dataType phải phản ánh đúng JSON được Jackson serialize. Hoàn tất migration bằng cách loại import/dependency Springfox không còn dùng, kiểm tra /v3/api-docs và chạy test cho cả hợp đồng lẫn API thực tế.

## Tài liệu tham khảo

- [springdoc-openapi documentation](https://springdoc.org/)
- [Swagger Core Annotations](https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations)
- [OpenAPI Specification: Schema Object](https://spec.openapis.org/oas/latest.html#schema-object)
- [Spring Boot Validation](https://docs.spring.io/spring-boot/reference/io/validation.html)
