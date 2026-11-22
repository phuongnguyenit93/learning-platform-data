# Thay thế kiểu dùng chung bằng cấu hình SpringDocUtils phù hợp phiên bản

springdoc-openapi thường suy luận schema OpenAPI từ kiểu Java mà controller, DTO và tham số sử dụng. Cách suy luận này phù hợp với các kiểu phổ biến như String, BigDecimal, LocalDate, DTO hoặc collection. Tuy nhiên, ứng dụng có thể dùng kiểu từ thư viện bên ngoài, kiểu domain riêng hoặc kiểu có cách serialize khác với cấu trúc Java mặc định. Nếu cùng một kiểu xuất hiện ở nhiều request và response, việc thêm annotation vào từng thuộc tính có thể gây lặp cấu hình và khó duy trì.

SpringDocUtils cung cấp một cấu hình dùng chung để thay thế cách springdoc diễn giải một kiểu Java khi tạo tài liệu. Hai phương thức quan trọng là replaceWithClass và replaceWithSchema. Phương thức thứ nhất chuyển việc suy luận sang một lớp đại diện; phương thức thứ hai cung cấp trực tiếp một Schema của OpenAPI. Cấu hình này tác động trên toàn ứng dụng, vì vậy cần chọn đúng phạm vi và đặt nó trước khi springdoc phân tích các model.

## 1. Khi nào nên dùng SpringDocUtils?

Hãy cân nhắc SpringDocUtils khi một kiểu Java được dùng ở nhiều nơi và cần có cùng một cách biểu diễn trong OpenAPI. Ví dụ:

- Một kiểu tiền tệ từ thư viện bên ngoài cần được mô tả thành object gồm số tiền và mã tiền tệ.
- Một kiểu domain được serialize bằng custom Jackson serializer nhưng cấu trúc Java không phản ánh JSON trên wire.
- Một kiểu wrapper nội bộ cần được thay bằng kiểu DTO dễ hiểu với client.
- Một kiểu tham số cần được thay bằng POJO tương thích với cách Spring MVC bind query parameter.
- Một mapping mặc định của springdoc cần được vô hiệu hóa để thư viện suy luận lại kiểu nguồn.

Không cần dùng cấu hình toàn cục nếu chỉ một field hoặc một endpoint có cách biểu diễn khác. Khi phạm vi chỉ nằm ở một vị trí, annotation như @Schema, @Parameter hoặc @ApiResponse thường rõ ràng hơn. SpringDocUtils phù hợp khi quy tắc thay thế là quy ước chung cho mọi nơi sử dụng kiểu nguồn.

## 2. Phân biệt replaceWithClass và replaceWithSchema

Hai phương thức cùng nhận kiểu nguồn nhưng cách thay thế khác nhau:

| Phương thức | Tham số đích | Cách springdoc tạo schema | Trường hợp phù hợp |
| --- | --- | --- | --- |
| replaceWithClass(source, target) | Một lớp Java khác | Suy luận schema từ lớp target, bao gồm thuộc tính và annotation của lớp đó | Có thể mô tả kiểu nguồn bằng một DTO hoặc model Java đại diện |
| replaceWithSchema(source, schema) | Một đối tượng Schema của OpenAPI | Dùng schema được khai báo trực tiếp | Muốn mô tả chính xác type, format, properties, enum hoặc example mà không cần lớp đại diện |

Ví dụ, nếu kiểu nguồn MoneyAmount thực tế được serialize thành JSON object có amount và currency, có thể dùng một lớp ApiMoneyAmount với hai thuộc tính tương ứng qua replaceWithClass. Nếu chỉ cần mô tả object đó bằng OpenAPI model, có thể dùng replaceWithSchema.

Điều quan trọng là cả hai cách chỉ thay đổi cách sinh tài liệu. Chúng không thay đổi kiểu Java ở controller, không chuyển đổi object trong runtime và không cấu hình Jackson. JSON thực tế vẫn do code ứng dụng, HttpMessageConverter và serializer quyết định.

## 3. Xác định package theo phiên bản springdoc

Tên package của SpringDocUtils đã thay đổi khi chuyển từ dòng springdoc 1.x sang 2.x:

| Dòng springdoc | Spring Boot tương ứng | Import SpringDocUtils |
| --- | --- | --- |
| 1.x | Spring Boot 1.x và 2.x | org.springdoc.core.SpringDocUtils |
| 2.x | Spring Boot 3.x | org.springdoc.core.utils.SpringDocUtils |
| 3.x | Spring Boot 4.x | org.springdoc.core.utils.SpringDocUtils |

Khi nâng từ springdoc 1.x lên 2.x, cần cập nhật import theo package mới. Không sao chép import từ ví dụ cũ nếu dự án đang dùng starter của dòng 2.x hoặc 3.x. Hãy kiểm tra phiên bản dependency thực tế và Javadoc tương ứng nếu IDE không tìm thấy lớp hoặc phương thức.

Các ví dụ Java trong bài dùng import của springdoc 2.x/3.x:

~~~java
import org.springdoc.core.utils.SpringDocUtils;
~~~

Với springdoc 1.x, đổi import thành:

~~~java
import org.springdoc.core.SpringDocUtils;
~~~

## 4. Cấu hình replaceWithClass

replaceWithClass nhận lớp nguồn và lớp đích. Khi springdoc gặp kiểu nguồn trong quá trình tạo schema, nó sử dụng lớp đích để suy luận cấu trúc. Lớp đích nên là một model dễ hiểu và phản ánh đúng JSON mà API thực sự trao đổi.

Giả sử hệ thống dùng kiểu MoneyAmount từ thư viện tài chính. Jackson đã được cấu hình để serialize nó thành object gồm số tiền và mã tiền tệ. Ta tạo một lớp đại diện:

~~~java
import java.math.BigDecimal;

public class ApiMoneyAmount {

    private BigDecimal amount;
    private String currency;

    public BigDecimal getAmount() {
        return amount;
    }

    public void setAmount(BigDecimal amount) {
        this.amount = amount;
    }

    public String getCurrency() {
        return currency;
    }

    public void setCurrency(String currency) {
        this.currency = currency;
    }
}
~~~

Đăng ký thay thế một lần trong cấu hình:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springdoc.core.utils.SpringDocUtils;

@Configuration
public class OpenApiTypeConfiguration {

    static {
        SpringDocUtils.getConfig()
            .replaceWithClass(MoneyAmount.class, ApiMoneyAmount.class);
    }
}
~~~

Sau cấu hình, các thuộc tính hoặc tham số có kiểu MoneyAmount sẽ được mô tả theo cấu trúc ApiMoneyAmount. Ví dụ, nếu DTO có trường:

~~~java
public class InvoiceResponse {
    private Long id;
    private MoneyAmount total;
}
~~~

schema InvoiceResponse có thể tham chiếu đến schema đại diện cho ApiMoneyAmount. Cấu trúc mong đợi có dạng:

~~~yaml
InvoiceResponse:
  type: object
  properties:
    id:
      type: integer
      format: int64
    total:
      $ref: '#/components/schemas/ApiMoneyAmount'

ApiMoneyAmount:
  type: object
  properties:
    amount:
      type: number
    currency:
      type: string
~~~

Tên component cuối cùng có thể phụ thuộc tên lớp, annotation và cấu hình model converter. Hãy kiểm tra JSON được sinh thay vì giả định mọi phiên bản đều đặt tên component giống ví dụ.

springdoc FAQ cũng minh họa việc thay thế kiểu MonetaryAmount bằng model có sẵn của springdoc:

~~~java
SpringDocUtils.getConfig()
    .replaceWithClass(
        MonetaryAmount.class,
        org.springdoc.core.converters.models.MonetaryAmount.class
    );
~~~

Đây là lựa chọn thuận tiện khi model đích do springdoc cung cấp đã phản ánh đúng cách biểu diễn mà ứng dụng muốn công bố.

## 5. Cấu hình replaceWithSchema

Nếu không muốn tạo lớp Java trung gian, có thể truyền trực tiếp Schema từ swagger-models. Ví dụ mô tả MoneyAmount thành object có amount và currency:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springdoc.core.utils.SpringDocUtils;

import io.swagger.v3.oas.models.media.NumberSchema;
import io.swagger.v3.oas.models.media.ObjectSchema;
import io.swagger.v3.oas.models.media.StringSchema;

@Configuration
public class OpenApiTypeConfiguration {

    static {
        SpringDocUtils.getConfig()
            .replaceWithSchema(
                MoneyAmount.class,
                new ObjectSchema()
                    .description("Số tiền kèm mã tiền tệ")
                    .addProperties(
                        "amount",
                        new NumberSchema().example(99.96)
                    )
                    .addProperties(
                        "currency",
                        new StringSchema().example("USD")
                    )
            );
    }
}
~~~

Schema thay thế có thể khai báo các thuộc tính OpenAPI cần thiết:

- description để giải thích ý nghĩa kiểu.
- type để xác định kiểu dữ liệu tổng quát.
- format để mô tả định dạng cụ thể nếu phù hợp.
- properties để định nghĩa object.
- items để mô tả phần tử array.
- enum để giới hạn các giá trị hợp lệ.
- example hoặc examples để cung cấp dữ liệu mẫu.
- required để nêu các thuộc tính bắt buộc của object.

Ví dụ, nếu currency luôn bắt buộc và amount cũng phải có mặt, có thể bổ sung required:

~~~java
ObjectSchema moneySchema = new ObjectSchema()
    .description("Số tiền kèm mã tiền tệ")
    .addProperties("amount", new NumberSchema().example(99.96))
    .addProperties("currency", new StringSchema().example("USD"))
    .addRequiredItem("amount")
    .addRequiredItem("currency");
~~~

Chỉ khai báo required khi API thực sự bắt buộc trường đó. Schema được tạo thủ công không tự áp dụng validation cho object runtime; nếu ứng dụng chấp nhận amount thiếu hoặc currency rỗng thì tài liệu không nên công bố ràng buộc chặt hơn hành vi thật.

## 6. Đặt cấu hình ở thời điểm phù hợp

SpringDocUtils.getConfig() trả về cấu hình dùng chung của thư viện. Các quy tắc thay thế cần được đăng ký trước khi springdoc xử lý model để sinh OpenAPI. Tài liệu springdoc và các ví dụ chính thức thường đặt cấu hình trong static initializer:

~~~java
@Configuration
public class OpenApiTypeConfiguration {

    static {
        SpringDocUtils.getConfig()
            .replaceWithClass(MoneyAmount.class, ApiMoneyAmount.class);
    }
}
~~~

Static block chạy khi lớp cấu hình được nạp, giúp đăng ký quy tắc sớm. Có thể gom nhiều thay thế trong cùng một chuỗi lời gọi:

~~~java
static {
    SpringDocUtils.getConfig()
        .replaceWithClass(MoneyAmount.class, ApiMoneyAmount.class)
        .replaceWithSchema(
            LegacyIdentifier.class,
            new StringSchema()
                .description("Mã định danh dạng chuỗi")
                .example("ORD-2026-001")
        );
}
~~~

Không nên đăng ký replaceWithClass hoặc replaceWithSchema trong một request handler hay trong mỗi lần gọi API. Đây là cấu hình dùng chung, không phải thao tác tạo tài liệu theo từng request. Cũng không nên đặt việc đăng ký này trong OpenApiCustomizer nếu mục tiêu là thay đổi cách model converter xử lý kiểu nguồn; customizer chạy ở giai đoạn tùy biến tài liệu, sau khi quá trình suy luận model có thể đã diễn ra.

Hãy giữ các thay thế tập trung trong một lớp cấu hình. Khi nhiều nơi cùng đăng ký thay thế cho một kiểu nguồn, kết quả có thể khó dự đoán và khó bảo trì. Một quy tắc duy nhất cho mỗi kiểu nguồn giúp người review biết model nào đang đại diện cho kiểu đó.

## 7. Phân biệt thay thế schema với thay thế parameter object

SpringDocUtils còn có phương thức replaceParameterObjectWithClass. Phương thức này phục vụ trường hợp một kiểu được dùng như parameter object, chẳng hạn object được Spring MVC bind từ nhiều query parameter. Nó không có cùng mục đích với replaceWithClass:

| Phương thức | Phạm vi |
| --- | --- |
| replaceWithClass | Thay lớp dùng để suy luận schema của kiểu nguồn nói chung |
| replaceWithSchema | Thay bằng Schema OpenAPI cho kiểu nguồn nói chung |
| replaceParameterObjectWithClass | Thay lớp đại diện khi xử lý kiểu nguồn như parameter object |

Ví dụ, ở các dự án cũ cần ánh xạ Pageable sang một lớp Pageable API để tài liệu query parameter được bung đúng:

~~~java
static {
    SpringDocUtils.getConfig()
        .replaceParameterObjectWithClass(
            Pageable.class,
            ApiPageable.class
        );
}
~~~

Đây là tình huống chuyên biệt. Các phiên bản springdoc mới đã có hỗ trợ Pageable tích hợp; hãy kiểm tra tài liệu của dòng đang dùng trước khi thêm thay thế thủ công. Nếu chỉ cần mô tả một tham số, annotation @ParameterObject và cấu hình của Spring Data Web có thể là lựa chọn phù hợp hơn.

## 8. Vô hiệu hóa một mapping thay thế có sẵn

SpringDocUtils cung cấp disableReplacement(source) để tắt một quy tắc thay thế đã được đăng ký cho kiểu nguồn. Điều này hữu ích khi springdoc hoặc module tích hợp đã cung cấp mapping mặc định nhưng ứng dụng cần để kiểu nguồn được xử lý theo cách khác.

Ví dụ, một ứng dụng có thể muốn bỏ mapping mặc định cho Pageable để tự mô tả kiểu này:

~~~java
@Configuration
public class OpenApiTypeConfiguration {

    static {
        SpringDocUtils.getConfig()
            .disableReplacement(Pageable.class);
    }
}
~~~

Sau khi tắt thay thế, springdoc sẽ không dùng mapping bị vô hiệu hóa cho kiểu nguồn đó. Điều này không tự tạo ra schema thay thế mới. Nếu kiểu nguồn không thể được suy luận thành schema hữu ích, cần bổ sung cấu hình phù hợp hoặc dùng annotation/customizer khác.

Không gọi disableReplacement chỉ để thử nghiệm nếu chưa xác định mapping nào đang được áp dụng. Hãy kiểm tra tài liệu của module tích hợp và output hiện tại trước khi vô hiệu hóa, vì mapping mặc định có thể đang giúp biểu diễn kiểu framework đúng với hợp đồng API.

## 9. Phạm vi ảnh hưởng và giới hạn

SpringDocUtils là cấu hình dùng chung trong ứng dụng. Khi thay thế một kiểu nguồn, mọi nơi springdoc gặp kiểu đó có thể chịu ảnh hưởng: thuộc tính DTO, request body, response body, phần tử collection hoặc tham số tùy theo cơ chế suy luận tương ứng.

Vì vậy:

- Không dùng thay thế toàn cục nếu chỉ một endpoint cần cấu trúc khác.
- Không chọn lớp đích chỉ vì nó có tên hoặc thuộc tính gần giống; phải khớp JSON thực tế.
- Không dùng schema thay thế để mô tả một kiểu mà runtime serialize theo hình dạng khác.
- Không giả định thay thế schema sẽ thay đổi Jackson, validation hoặc cách Spring bind request.
- Không đăng ký nhiều mapping mâu thuẫn cho cùng một kiểu nguồn.
- Không bỏ qua generic hoặc nested type trong lớp đích; hãy kiểm tra các schema phụ được sinh và tham chiếu.

Nếu cùng một kiểu Java có nhiều cách biểu diễn tùy ngữ cảnh, thay thế toàn cục không phù hợp. Ví dụ, MoneyAmount trong response công khai có thể cần object amount/currency, trong khi một query parameter chỉ nhận chuỗi "99.96 USD". Hãy mô tả riêng ở từng operation bằng @Schema, @Parameter hoặc customizer thay vì ép toàn bộ kiểu nguồn dùng chung một schema.

## 10. Kiểm tra kết quả trong OpenAPI

Sau khi đăng ký cấu hình, khởi động ứng dụng và tải đặc tả tại endpoint mặc định /v3/api-docs hoặc endpoint đã tùy chỉnh. Kiểm tra:

1. Kiểu nguồn đã được thay bằng lớp hoặc schema mong muốn.
2. Các thuộc tính của lớp đại diện xuất hiện đầy đủ và đúng kiểu.
3. Schema của kiểu lồng nhau được đăng ký trong components.schemas.
4. Các operation dùng kiểu nguồn đều tham chiếu schema hợp lệ.
5. Không còn schema cũ hoặc schema mặc định mâu thuẫn với mapping mới.
6. Request và response JSON thực tế có cùng cấu trúc được mô tả.
7. Các nhóm tài liệu riêng cũng nhận đúng cấu hình thay thế.

Có thể tải tài liệu bằng curl:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

Nếu ứng dụng có nhiều nhóm, kiểm tra từng URL /v3/api-docs/{group}. Đừng chỉ xác nhận component xuất hiện trong một tài liệu mặc định rồi suy ra tất cả nhóm đều giống nhau.

Sau khi xem schema, gọi endpoint thực tế và kiểm tra JSON response hoặc request payload. Ví dụ, nếu schema công bố MoneyAmount là object:

~~~json
{
  "amount": 99.96,
  "currency": "USD"
}
~~~

thì serializer runtime cũng cần tạo object cùng cấu trúc. Nếu API thực tế chỉ trả về chuỗi "USD 99.96", schema object là sai dù Swagger UI hiển thị đẹp.

Nên có kiểm thử hợp đồng hoặc kiểm thử tích hợp xác nhận cả schema OpenAPI lẫn JSON thực tế. Khi nâng springdoc, swagger-core hoặc Spring Boot, hãy chạy lại kiểm tra vì converter và cơ chế suy luận có thể thay đổi giữa các phiên bản.

## 11. Lỗi thường gặp và cách xử lý

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Import SpringDocUtils không tồn tại | Dùng package của dòng phiên bản khác | Kiểm tra dependency và dùng package đúng với v1 hoặc v2/v3 |
| Thay thế không có tác dụng | Cấu hình được đăng ký sau khi springdoc đã phân tích model hoặc lớp cấu hình chưa được nạp | Đặt đăng ký trong static initializer của cấu hình được Spring nạp sớm |
| Schema hiển thị đúng nhưng JSON runtime khác | Nhầm thay thế tài liệu với chuyển đổi dữ liệu | Đồng bộ Jackson serializer/deserializer hoặc sửa schema cho đúng JSON thực tế |
| Một kiểu thay đổi ở nhiều endpoint ngoài dự kiến | Dùng SpringDocUtils cho một trường hợp chỉ thuộc một endpoint | Chuyển sang @Schema, @Parameter hoặc customizer theo operation |
| Lớp đại diện thiếu thuộc tính | Model đích không phản ánh đầy đủ payload | Bổ sung getter/field và kiểm tra Jackson property thực tế |
| Component lồng nhau bị thiếu | Model đích có kiểu tham chiếu phức tạp hoặc converter không xử lý như dự kiến | Kiểm tra components.schemas, generic type và phiên bản swagger-core |
| Schema object không có required như mong đợi | Schema thủ công chưa khai báo required | Thêm required cho thuộc tính thực sự bắt buộc và kiểm tra validation runtime |
| Pageable hiển thị khác sau khi vô hiệu hóa replacement | Mapping mặc định của Spring Data đã bị tắt | Khôi phục mapping hoặc khai báo parameter object phù hợp với phiên bản |
| Cùng kiểu nguồn có nhiều schema theo ngữ cảnh | Thay thế toàn cục không thể biểu diễn khác biệt từng operation | Dùng schema riêng ở thuộc tính hoặc operation cần khác biệt |

## 12. Quy trình áp dụng an toàn

Khi cần thay thế một kiểu dùng chung, hãy làm theo trình tự:

1. Xác định kiểu nguồn và mọi nơi kiểu đó xuất hiện trong API.
2. Kiểm tra JSON thực tế được Jackson serialize hoặc deserialize.
3. Quyết định thay thế toàn cục có phù hợp hay chỉ cần tùy chỉnh một field/operation.
4. Chọn replaceWithClass nếu có một model Java đại diện chính xác; chọn replaceWithSchema nếu muốn khai báo trực tiếp cấu trúc OpenAPI.
5. Kiểm tra package SpringDocUtils theo dòng springdoc đang dùng.
6. Đăng ký quy tắc sớm trong static initializer và tập trung cấu hình tại một nơi.
7. Tải OpenAPI JSON, kiểm tra component, reference và từng operation liên quan.
8. Gọi endpoint thật để đối chiếu request/response với schema.
9. Chạy lại kiểm thử khi nâng phiên bản thư viện hoặc thay đổi serializer.

## 13. Tài liệu tham khảo chính thức

- [springdoc-openapi FAQ](https://springdoc.org/faq.html) — ví dụ replaceWithClass và replaceWithSchema cho MonetaryAmount.
- [springdoc-openapi v2 FAQ](https://springdoc.org/v2/faq.html) — cấu hình SpringDocUtils và các ví dụ tương thích Spring Boot 3.
- [springdoc-openapi v2 — Migration from v1](https://springdoc.org/v2/#migrating-from-springdoc-openapi-v1) — thay đổi package SpringDocUtils từ org.springdoc.core sang org.springdoc.core.utils.
- [SpringDocUtils Javadoc v1.8.0](https://javadoc.io/static/org.springdoc/springdoc-openapi-common/1.8.0/org/springdoc/core/SpringDocUtils.html) — API replaceWithClass, replaceWithSchema, replaceParameterObjectWithClass và disableReplacement của dòng 1.x.
- [SpringDocConfiguration source](https://github.com/springdoc/springdoc-openapi/blob/main/springdoc-openapi-starter-common/src/main/java/org/springdoc/core/configuration/SpringDocConfiguration.java) — cách cấu hình hiện hành sử dụng SpringDocUtils trong quá trình khởi tạo.

SpringDocUtils giúp thống nhất cách springdoc diễn giải một kiểu Java được dùng ở nhiều nơi. Chọn giữa lớp đại diện và schema trực tiếp, dùng đúng package theo phiên bản, đăng ký cấu hình trước khi sinh tài liệu và đối chiếu với JSON runtime sẽ giúp hợp đồng OpenAPI chính xác mà không phải lặp annotation trên mọi DTO.
