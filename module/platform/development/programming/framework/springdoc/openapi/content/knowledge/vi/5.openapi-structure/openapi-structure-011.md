# Phần mở rộng x-* và mục đích sử dụng

## 1. Vì sao OpenAPI có phần mở rộng?

OpenAPI định nghĩa một cấu trúc chung để mô tả API: thông tin tổng quan, server, endpoint, request, response, schema và bảo mật. Tuy nhiên, mỗi tổ chức có thể cần thêm metadata phục vụ quy trình riêng. Ví dụ:

- Đánh dấu endpoint thuộc nhóm nội bộ hoặc nhóm public.
- Ghi tên đội phụ trách, mã hệ thống hoặc đường dẫn tài liệu nghiệp vụ.
- Cung cấp ví dụ mã nguồn, thông tin giới hạn tốc độ hoặc nhãn hiển thị cho developer portal.
- Hướng dẫn một công cụ sinh SDK, cổng API hoặc nền tảng quản trị xử lý tài liệu theo quy ước riêng.

Nếu thêm một thuộc tính tùy ý không thuộc cấu trúc chuẩn, công cụ OpenAPI có thể coi tài liệu là không hợp lệ. Để mở rộng tài liệu mà vẫn giữ được cấu trúc tương thích, OpenAPI định nghĩa cơ chế **Specification Extensions**, thường gọi là **vendor extensions** hoặc phần mở rộng **x-***.

Một extension là một trường metadata có tên bắt đầu bằng tiền tố **x-**. Giá trị của nó có thể là chuỗi, số, boolean, mảng hoặc object JSON/YAML. Công cụ hiểu extension có thể dùng dữ liệu này cho chức năng riêng; công cụ không hiểu thường có thể bỏ qua extension và tiếp tục đọc các trường OpenAPI chuẩn.

Phần mở rộng giúp tổ chức bổ sung thông tin mà không phải thay đổi cấu trúc chuẩn hoặc tạo một bản OpenAPI riêng. Tuy nhiên, extension chỉ có ý nghĩa khi bên tạo tài liệu và bên tiêu thụ thống nhất cách diễn giải.

## 2. Quy tắc cơ bản của extension x-*

Một extension cần tuân theo các nguyên tắc:

1. Tên trường phải bắt đầu bằng **x-**.
2. Tên extension phân biệt chữ hoa và chữ thường; nên thống nhất một cách viết, thường dùng chữ thường và dấu gạch nối.
3. Giá trị có thể là bất kỳ kiểu dữ liệu JSON hợp lệ nào: string, number, boolean, array, object hoặc null nếu phù hợp với cách tiêu thụ.
4. Extension chỉ nên được đặt tại những đối tượng OpenAPI cho phép specification extensions.
5. Extension không thay đổi ý nghĩa của các trường chuẩn trừ khi một công cụ riêng quy định cách diễn giải bổ sung.
6. Người dùng tài liệu cần biết extension nào là quy ước riêng và công cụ nào hỗ trợ nó.

Ví dụ một extension đơn giản:

~~~yaml
openapi: 3.1.0
info:
  title: Shop API
  version: "1.0.0"
  x-api-owner: platform-team
paths: {}
~~~

Trong ví dụ, **x-api-owner** là metadata riêng cho biết nhóm sở hữu API. OpenAPI không định nghĩa sẵn ý nghĩa của tên này. Một cổng API nội bộ có thể đọc trường đó để gắn tài liệu với nhóm phụ trách; Swagger UI thông thường có thể không hiển thị nó.

Không được đặt tên trường tùy ý như **owner** ở một vị trí mà OpenAPI không định nghĩa. Dùng tiền tố x- giúp phân biệt metadata mở rộng với các trường thuộc đặc tả.

## 3. Extension có thể xuất hiện ở đâu?

OpenAPI cho phép specification extensions tại nhiều đối tượng trong tài liệu. Những vị trí thường gặp gồm:

| Vị trí | Ví dụ mục đích |
|---|---|
| OpenAPI Object (cấp tài liệu) | Mã hệ thống, nhóm sở hữu hoặc metadata phục vụ pipeline |
| Info Object | Logo, nhóm hỗ trợ hoặc liên kết tài liệu bổ sung |
| Server Object | Metadata riêng cho môi trường hoặc gateway |
| Tag Object | Nhóm chức năng, phân loại hoặc metadata cho developer portal |
| Path Item và Operation Object | Đội phụ trách endpoint, mã nghiệp vụ, ví dụ mã nguồn |
| Parameter và Header Object | Hướng dẫn hiển thị hoặc metadata cho client generator |
| Request Body và Response Object | Quy tắc xử lý riêng hoặc liên kết ví dụ |
| Schema Object | Nhãn hiển thị, widget hoặc metadata cho công cụ sinh model |
| Security Scheme Object | Thông tin tích hợp bổ sung cho hệ thống xác thực |

Danh sách này giúp hình dung những vị trí phổ biến; khi triển khai cần kiểm tra đúng phiên bản OpenAPI và loại object cụ thể để xác nhận extension được phép ở vị trí đó.

Ví dụ extension ở cấp operation:

~~~yaml
paths:
  /products:
    get:
      summary: Tìm kiếm sản phẩm
      operationId: searchProducts
      x-internal-owner:
        team: catalog
        contact: platform-api
      responses:
        "200":
          description: Thành công
~~~

Extension **x-internal-owner** được đặt trong Operation Object nên chỉ áp dụng cho thao tác GET /products. Một operation khác có thể có đội phụ trách hoặc metadata khác.

## 4. Kiểu giá trị của extension

Extension không bị giới hạn ở chuỗi. Có thể chọn cấu trúc dữ liệu phù hợp với nhu cầu tiêu thụ.

### 4.1. Giá trị đơn giản

~~~yaml
x-api-owner: platform-team
x-internal-only: true
x-priority: 2
~~~

Các giá trị này phù hợp với metadata ngắn như tên nhóm, cờ boolean hoặc mức ưu tiên.

### 4.2. Giá trị dạng object

~~~yaml
x-governance:
  owner: catalog-team
  data-classification: internal
  review-cycle: quarterly
~~~

Object phù hợp khi một nhóm metadata có nhiều thuộc tính liên quan. Các thuộc tính con không cần tiền tố x- vì chúng nằm bên trong giá trị của extension x-governance; tuy nhiên, schema nội bộ của object vẫn cần được quy định rõ.

### 4.3. Giá trị dạng mảng

~~~yaml
x-code-samples:
  - lang: curl
    label: Gọi API bằng curl
    source: |
      curl -X GET https://api.example.com/products
  - lang: javascript
    label: Gọi API bằng fetch
    source: |
      fetch("https://api.example.com/products")
~~~

Mảng phù hợp với danh sách ví dụ, nhãn hoặc các mục cấu hình có thứ tự. Công cụ tiêu thụ cần biết tên và kiểu của từng thuộc tính trong phần tử mảng.

### 4.4. Cùng một extension trong JSON

OpenAPI JSON và YAML biểu diễn cùng một mô hình dữ liệu. Ví dụ:

~~~json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Shop API",
    "version": "1.0.0"
  },
  "x-api-owner": "platform-team",
  "paths": {}
}
~~~

Khi chuyển đổi JSON sang YAML hoặc ngược lại, extension nên được giữ nguyên về tên, kiểu và cấu trúc giá trị. Không nên biến object thành chuỗi JSON chỉ vì công cụ xuất tài liệu không hiểu extension.

## 5. Phân biệt extension với trường chuẩn và metadata thông thường

Không phải mọi thông tin bổ sung đều cần tạo extension. OpenAPI đã có nhiều trường chuẩn để mô tả API:

- **info.description** mô tả toàn bộ API.
- **operation.description** mô tả một thao tác.
- **externalDocs** liên kết đến tài liệu ngoài.
- **tags** nhóm endpoint.
- **deprecated** đánh dấu operation hoặc parameter đã lỗi thời.
- **security** và **securitySchemes** mô tả yêu cầu bảo mật.

Nên dùng trường chuẩn khi nó đã đáp ứng nhu cầu. Ví dụ, mô tả endpoint thuộc chức năng nào nên dùng tag; không cần tạo x-feature-group nếu tag đã biểu diễn đúng ý nghĩa.

Chỉ tạo extension khi cần metadata mà đặc tả chưa cung cấp hoặc khi một công cụ tích hợp yêu cầu một quy ước riêng. Việc tạo quá nhiều extension trùng lặp với trường chuẩn khiến tài liệu khó hiểu và có thể tạo ra hai nguồn dữ liệu mâu thuẫn.

Một extension không phải là cách khai báo một trường mới trong request hoặc response. Nếu client phải gửi trường dữ liệu nghiệp vụ, hãy mô tả trường đó trong Schema Object. Nếu muốn thêm metadata cho Schema Object, mới dùng extension tại schema.

## 6. Ví dụ extension dành cho công cụ tài liệu

Một số công cụ tài liệu định nghĩa extension riêng để điều khiển giao diện. Ví dụ, ReDoc hỗ trợ extension **x-logo** trong Info Object để hiển thị logo:

~~~yaml
openapi: 3.1.0
info:
  title: Shop API
  version: "1.0.0"
  x-logo:
    url: https://example.com/assets/shop-api-logo.png
    altText: Shop API
paths: {}
~~~

Extension này có ý nghĩa với công cụ hỗ trợ x-logo. Một trình đọc OpenAPI khác có thể bỏ qua nó và vẫn hiển thị tài liệu dựa trên title, description và paths.

Một ví dụ khác là extension x-codeSamples được một số nền tảng tài liệu hỗ trợ để trình bày các ví dụ request bằng nhiều ngôn ngữ. Cấu trúc cụ thể cần theo tài liệu của công cụ tiêu thụ; không có một schema x-codeSamples chung bắt buộc cho mọi công cụ OpenAPI.

Khi dùng extension của bên thứ ba, hãy ghi lại:

- Tên chính xác và kiểu dữ liệu của extension.
- Phiên bản công cụ hỗ trợ extension.
- Đối tượng OpenAPI mà extension được đặt vào.
- Hành vi dự kiến khi công cụ không nhận diện extension.

Không nên giả định extension của một công cụ sẽ hoạt động giống nhau trên Swagger UI, ReDoc, cổng API hoặc SDK generator khác.

## 7. Khai báo extension bằng Springdoc OpenAPI

Springdoc sử dụng các annotation của thư viện Swagger/OpenAPI để mô tả API. Annotation **@Extension** và **@ExtensionProperty** cho phép khai báo metadata mở rộng tại các annotation hỗ trợ extension, chẳng hạn **@Operation** hoặc **@Schema**.

Ví dụ gắn metadata cho operation:

~~~java
@RestController
@RequestMapping("/api/products")
public class ProductController {

    @GetMapping
    @Operation(
        summary = "Tìm kiếm sản phẩm",
        extensions = {
            @Extension(
                name = "x-internal-owner",
                properties = {
                    @ExtensionProperty(
                        name = "team",
                        value = "catalog"
                    ),
                    @ExtensionProperty(
                        name = "contact",
                        value = "platform-api"
                    )
                }
            )
        }
    )
    public List<ProductResponse> search() {
        return productService.search();
    }
}
~~~

Kết quả OpenAPI có thể chứa phần tương tự:

~~~yaml
paths:
  /api/products:
    get:
      summary: Tìm kiếm sản phẩm
      x-internal-owner:
        team: catalog
        contact: platform-api
      responses:
        "200":
          description: Thành công
~~~

Trong đó, tên extension là **x-internal-owner**; các thuộc tính team và contact tạo thành object value của extension. Tên extension phải có tiền tố x-.

Có thể khai báo extension cho schema nếu annotation tương ứng hỗ trợ:

~~~java
@Schema(
    description = "Thông tin sản phẩm",
    extensions = {
        @Extension(
            name = "x-ui-hint",
            properties = {
                @ExtensionProperty(
                    name = "component",
                    value = "product-card"
                )
            }
        )
    }
)
public record ProductResponse(
    Long id,
    String name
) {}
~~~

Extension x-ui-hint là gợi ý riêng cho một công cụ giao diện có hiểu quy ước này. Nó không làm thay đổi kiểu dữ liệu hoặc validation của ProductResponse.

Các annotation trên cần import từ gói **io.swagger.v3.oas.annotations** và **io.swagger.v3.oas.annotations.extensions**. Tên thuộc tính hoặc khả năng hỗ trợ có thể khác theo phiên bản thư viện swagger-annotations được Springdoc sử dụng; hãy đối chiếu API của phiên bản dự án trước khi áp dụng.

## 8. Thêm extension bằng OpenApiCustomizer

Khi metadata cần được tạo bằng code, có thể dùng customizer của Springdoc để bổ sung extension vào OpenAPI model.

Ví dụ thêm extension ở cấp tài liệu:

~~~java
@Configuration
public class OpenApiExtensionConfiguration {

    @Bean
    public OpenApiCustomizer apiOwnerExtension() {
        return openApi ->
            openApi.addExtension("x-api-owner", "platform-team");
    }
}
~~~

Customizer nhận OpenAPI model và thêm một trường mở rộng vào tài liệu. Cách này hữu ích khi giá trị lấy từ cấu hình hoặc cần được tính toán lúc ứng dụng khởi động.

Có thể thêm object thay vì chuỗi:

~~~java
Map<String, Object> governance = new LinkedHashMap<>();
governance.put("owner", "catalog-team");
governance.put("classification", "internal");

openApi.addExtension("x-governance", governance);
~~~

Đoạn thứ hai minh họa phần thân cần đặt bên trong lambda customizer hoặc phương thức cấu hình phù hợp; cần khai báo import Map và LinkedHashMap. Giá trị object được serialize thành object JSON/YAML.

Trong ứng dụng có nhiều nhóm tài liệu, cần xác minh customizer áp dụng cho nhóm nào. Springdoc cung cấp cơ chế customizer theo phạm vi khác nhau; nếu cần extension xuất hiện ở mọi nhóm, hãy chọn loại customizer toàn cục phù hợp với phiên bản đang dùng và kiểm tra từng endpoint tài liệu nhóm.

Không nên tạo cùng một extension từ nhiều nguồn nếu các nguồn có thể ghi đè nhau. Chọn một nơi chịu trách nhiệm tạo metadata để tránh kết quả không nhất quán.

## 9. Thiết kế quy ước extension cho tổ chức

Extension riêng cần có quy ước rõ ràng. Một quy ước tốt nên mô tả:

| Nội dung | Câu hỏi cần trả lời |
|---|---|
| Tên | Tên extension bắt đầu bằng x- là gì? |
| Vị trí | Được phép xuất hiện ở cấp tài liệu, operation hay schema? |
| Kiểu | Giá trị là string, boolean, object hay array? |
| Ý nghĩa | Mỗi thuộc tính có ý nghĩa nghiệp vụ nào? |
| Chủ sở hữu | Nhóm nào định nghĩa và duy trì extension? |
| Người tiêu thụ | Công cụ nào đọc và thực thi hành vi từ extension? |
| Phiên bản | Thay đổi cấu trúc extension được quản lý ra sao? |
| Mặc định | Hành vi khi thiếu extension hoặc thiếu thuộc tính là gì? |

Ví dụ, tổ chức có thể định nghĩa x-internal-owner như sau:

~~~yaml
x-internal-owner:
  team: catalog
  contact: platform-api
  visibility: internal
~~~

Quy ước đi kèm cần giải thích rằng team là mã nhóm được quản lý tập trung, contact là kênh hỗ trợ và visibility xác định phạm vi công bố trong portal nội bộ. Nếu công cụ tiêu thụ dùng visibility để lọc tài liệu, phải bảo đảm metadata được kiểm tra trước khi công bố.

Nên dùng namespace có ý nghĩa để giảm nguy cơ trùng tên với extension của bên thứ ba. Chẳng hạn, tổ chức có thể dùng tiền tố x-company- hoặc x-platform- cho extension nội bộ. Không nên đặt extension tên chung chung như x-config nếu nhiều hệ thống cùng phát triển tài liệu.

## 10. Tác động đến khả năng tương thích

Một trong những lợi ích của extension là công cụ không hiểu extension thường có thể bỏ qua nó và tiếp tục xử lý phần OpenAPI chuẩn. Điều này giúp tài liệu có thể được dùng ở nhiều công cụ khác nhau.

Tuy nhiên, không nên mặc định mọi công cụ đều giữ extension khi đọc rồi ghi lại tài liệu. Một số công cụ có thể loại bỏ trường không nhận diện, chuẩn hóa kiểu dữ liệu hoặc chỉ hỗ trợ extension tại một số vị trí.

Khi thiết kế extension:

- Không đặt thông tin bắt buộc để gọi API chỉ trong extension.
- Không dùng extension để thay thế path, method, parameter, requestBody, responses hoặc security chuẩn.
- Không để client cần hiểu extension mới có thể thực hiện một request hợp lệ, trừ khi đó là một hợp đồng riêng đã được công bố rõ.
- Kiểm tra extension có còn nguyên sau khi tài liệu đi qua generator, formatter, converter hoặc developer portal.
- Quản lý thay đổi cấu trúc extension để tránh phá vỡ công cụ nội bộ đang tiêu thụ nó.

Ví dụ, nếu endpoint yêu cầu JWT, hãy khai báo security scheme và security requirement theo OpenAPI. Thêm x-auth-mode: jwt chỉ có thể bổ sung metadata cho một hệ thống riêng; nó không thay thế security chuẩn và không khiến Spring Security tự xác thực token.

## 11. Kiểm tra và xác thực extension

Sau khi tạo tài liệu, cần kiểm tra cả tính hợp lệ của OpenAPI document và quy ước extension.

Có thể xác minh bằng cách:

1. Tải OpenAPI JSON hoặc YAML từ endpoint Springdoc.
2. Kiểm tra tên extension bắt đầu bằng x- và đặt đúng object.
3. Kiểm tra kiểu dữ liệu và cấu trúc value theo quy ước nội bộ.
4. Dùng validator OpenAPI để xác nhận tài liệu vẫn hợp lệ.
5. Chạy công cụ tiêu thụ extension và xác nhận hành vi mong đợi.
6. Kiểm tra tài liệu sau khi chuyển đổi hoặc phân phối có giữ lại extension hay không.

Một số lỗi thường gặp:

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Validator báo thuộc tính không hợp lệ | Tên extension thiếu tiền tố x- hoặc được đặt tại object không hỗ trợ extension |
| Extension xuất hiện thành chuỗi thay vì object | Giá trị được tạo hoặc serialize sai kiểu |
| Swagger UI không hiển thị metadata | UI không hỗ trợ extension đó hoặc không có plugin xử lý |
| Extension biến mất sau bước build | Generator, formatter hoặc converter đã loại bỏ trường chưa biết |
| Metadata khác nhau giữa các nhóm API | Customizer chỉ áp dụng cho một phạm vi hoặc các nguồn cấu hình ghi đè nhau |
| Công cụ nội bộ không xử lý extension | Tên, vị trí, kiểu hoặc phiên bản quy ước không khớp |

OpenAPI validator chủ yếu xác nhận cấu trúc theo đặc tả. Nó không tự hiểu quy tắc nghiệp vụ riêng của x-internal-owner hoặc x-governance. Nếu extension có schema nội bộ, cần thêm kiểm tra riêng trong CI hoặc công cụ quản trị tài liệu.

## 12. Nguyên tắc sử dụng x-* trong dự án Springdoc

Khi dùng extension trong dự án Spring Boot, nên áp dụng các nguyên tắc sau:

1. Ưu tiên trường OpenAPI chuẩn trước khi tạo extension mới.
2. Đặt tên extension có tiền tố x- và thống nhất cách viết.
3. Chọn kiểu dữ liệu có cấu trúc rõ ràng, tránh nhét object thành chuỗi.
4. Ghi tài liệu cho ý nghĩa, vị trí, chủ sở hữu và công cụ tiêu thụ extension.
5. Dùng @Extension/@ExtensionProperty khi metadata gắn với operation hoặc schema.
6. Dùng OpenApiCustomizer khi cần bổ sung metadata bằng code ở cấp tài liệu hoặc theo phạm vi phù hợp.
7. Không đặt thông tin bí mật hoặc dữ liệu nhạy cảm vào extension vì OpenAPI document có thể được phân phối rộng.
8. Kiểm tra validator, kết quả JSON/YAML và công cụ thực sự đọc extension.
9. Quản lý thay đổi extension cùng quá trình review và phát hành hợp đồng API.

Specification Extensions cho phép OpenAPI thích ứng với nhu cầu riêng của tổ chức mà vẫn giữ được cấu trúc chuẩn. Khi được thiết kế có quy ước, các trường x-* có thể hỗ trợ developer portal, code generator, quy trình quản trị và tài liệu nội bộ mà không làm mờ hợp đồng HTTP cốt lõi.

