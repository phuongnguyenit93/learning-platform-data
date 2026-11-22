# Contact, license, termsOfService và thông tin sở hữu API

Một OpenAPI document cần cho người tích hợp biết ai chịu trách nhiệm hỗ trợ API, điều kiện pháp lý nào áp dụng và tổ chức nào công bố dịch vụ. Trong OpenAPI, các thông tin này nằm trong đối tượng `info` thông qua `contact`, `license` và `termsOfService`. springdoc-openapi có thể sinh chúng từ annotation Swagger hoặc từ một bean `OpenAPI` do ứng dụng cấu hình.

Ba trường này có vai trò khác nhau:

- `contact` cho biết người hoặc nhóm mà consumer có thể liên hệ khi cần hỗ trợ API.
- `license` công bố giấy phép áp dụng cho API.
- `termsOfService` trỏ đến điều khoản sử dụng dịch vụ.

Thông tin chủ sở hữu API cũng cần được thể hiện rõ, nhưng OpenAPI không có một trường chuẩn tên là `owner`. Có thể công bố tổ chức sở hữu qua `contact.name` khi phù hợp, hoặc dùng vendor extension như `x-api-owner` để biểu diễn metadata riêng. Cần phân biệt chủ sở hữu pháp lý, nhóm vận hành và đầu mối hỗ trợ; ba vai trò này có thể là các tổ chức khác nhau.

## 1. Vị trí của metadata trong OpenAPI document

Các trường `contact`, `license` và `termsOfService` là thành phần của `info` ở cấp cao nhất:

~~~yaml
openapi: 3.1.1
info:
  title: Orders API
  version: 2.4.0
  description: API quản lý đơn hàng cho ứng dụng thương mại điện tử.
  termsOfService: https://api.example.com/terms
  contact:
    name: Example Platform API Support
    url: https://support.example.com/api
    email: api-support@example.com
  license:
    name: Apache 2.0
    identifier: Apache-2.0
  x-api-owner:
    organization: Example Corporation
    team: Commerce Platform
servers:
  - url: https://api.example.com/v2
paths: {}
~~~

`info` mô tả API trong toàn bộ document. Nó không nằm trong từng path hay operation. Nếu ứng dụng tạo nhiều document bằng group, mỗi document có thể mang metadata riêng phù hợp với API hoặc nhóm consumer đó.

Hai trường `title` và `version` là bắt buộc trong Info Object. `version` là phiên bản của OpenAPI document; nó không tự động đồng nghĩa với phiên bản OpenAPI Specification ở trường `openapi` hoặc phiên bản API trong URL server.

Metadata giúp người và công cụ hiểu nguồn gốc tài liệu, nhưng không tự tạo ra quyền truy cập, không xác thực người liên hệ và không thi hành điều khoản pháp lý. Các quy tắc vận hành và pháp lý vẫn phải được công bố, quản trị ở hệ thống tương ứng.

## 2. Phân biệt contact, license và termsOfService

| Trường | Câu hỏi mà trường trả lời | Ví dụ nội dung |
|---|---|---|
| `contact` | Liên hệ ai khi cần hỗ trợ API? | Nhóm API Support, email hỗ trợ, trang ticket |
| `license` | Giấy phép nào được công bố cho API? | Apache-2.0, MIT hoặc URL đến văn bản giấy phép |
| `termsOfService` | Người dùng phải tuân theo điều khoản sử dụng nào? | URL đến điều khoản dịch vụ |
| `x-api-owner` | Tổ chức/đơn vị nào sở hữu API theo quy ước nội bộ? | Tên công ty hoặc nhóm chịu trách nhiệm |

Không dùng một URL cho cả ba trường chỉ vì URL đó chứa thông tin pháp lý. Trang hỗ trợ không phải giấy phép; giấy phép mã nguồn không nhất thiết là điều khoản sử dụng API; điều khoản sử dụng cũng không phải thông tin liên hệ.

Ví dụ, một API có thể do Example Corporation sở hữu, do Commerce Platform vận hành, có email hỗ trợ api-support@example.com, phát hành theo giấy phép Apache-2.0 và áp dụng điều khoản dịch vụ riêng. Mỗi thông tin cần đặt vào đúng trường để consumer và công cụ đọc document không hiểu sai.

## 3. Contact Object gồm những gì?

Theo OpenAPI Specification, Contact Object có ba trường:

| Field | Ý nghĩa | Quy tắc |
|---|---|---|
| `name` | Tên người hoặc tổ chức liên hệ | Chuỗi mô tả |
| `url` | Trang thông tin liên hệ | Phải là URI hợp lệ |
| `email` | Địa chỉ email liên hệ | Phải có định dạng email |

Các trường này không bắt buộc phải có đủ cả ba. Tuy nhiên, document công khai nên có ít nhất một kênh liên hệ có người chịu trách nhiệm theo dõi. Nếu email hỗ trợ thay đổi theo thời gian, nên dùng mailing list hoặc hệ thống ticket do tổ chức quản lý thay vì email cá nhân của một nhân viên.

Ví dụ:

~~~yaml
info:
  contact:
    name: API Platform Support
    url: https://support.example.com/api
    email: api-support@example.com
~~~

`contact.name` có thể là tên nhóm, phòng ban hoặc tổ chức. Không nên ghi một cá nhân nếu vai trò hỗ trợ cần tồn tại lâu hơn thời gian người đó làm việc với dự án.

`contact.url` nên trỏ đến trang hỗ trợ hoặc trang liên hệ mà consumer có thể truy cập. Không dùng URL nội bộ như trang quản trị chỉ dành cho nhân viên nếu document được phát hành cho đối tác.

`contact.email` nên là mailbox có kiểm soát quyền truy cập và quy trình tiếp nhận yêu cầu. Nếu API không có kênh hỗ trợ email, có thể chỉ công bố URL liên hệ.

## 4. License Object và lựa chọn URL hoặc SPDX identifier

License Object có trường `name` bắt buộc. OpenAPI 3.1 trở lên hỗ trợ thêm `identifier` là biểu thức giấy phép SPDX. Trường `identifier` và `url` loại trừ lẫn nhau; chỉ chọn một trong hai.

### Dùng URL giấy phép

Đây là cách tương thích với OpenAPI 3.0:

~~~yaml
info:
  license:
    name: Apache 2.0
    url: https://www.apache.org/licenses/LICENSE-2.0.html
~~~

`name` là tên giấy phép hiển thị. `url` dẫn đến văn bản giấy phép chính thức.

### Dùng SPDX identifier trong OpenAPI 3.1+

~~~yaml
openapi: 3.1.1
info:
  title: Catalog API
  version: 1.6.0
  license:
    name: Apache 2.0
    identifier: Apache-2.0
~~~

`identifier` nên dùng giá trị SPDX chính xác, ví dụ `Apache-2.0` hoặc `MIT`. Không tự rút gọn tên giấy phép thành một chuỗi không có trong SPDX License List.

### Lưu ý khi dùng OpenAPI 3.0

OpenAPI 3.0 không định nghĩa trường `identifier` trong License Object. Nếu document được xuất theo 3.0, dùng `name` và `url`. Không thêm `identifier` vào tài liệu 3.0 rồi kỳ vọng mọi validator hoặc tool cũ hiểu trường đó.

Trường license chỉ công bố giấy phép liên quan đến API. Nó không tự chứng minh tổ chức có quyền cấp phép cho dữ liệu, nội dung của bên thứ ba hoặc hệ thống upstream. Cần xác định rõ đối tượng được cấp phép trước khi công bố.

## 5. TermsOfService là URI đến điều khoản sử dụng

`termsOfService` là một URI trỏ đến điều khoản sử dụng API. Giá trị cần là URI hợp lệ; với API công khai, nên dùng HTTPS và bảo đảm trang có thể truy cập từ bên ngoài.

~~~yaml
info:
  termsOfService: https://api.example.com/legal/terms-of-service
~~~

Điều khoản sử dụng có thể quy định:

- Ai được phép đăng ký và sử dụng API.
- Giới hạn lưu lượng, quota và rate limit.
- Quy định bảo vệ thông tin xác thực và dữ liệu.
- Hành vi bị cấm và quy trình xử lý lạm dụng.
- Trách nhiệm của nhà cung cấp và consumer.
- Quy trình thay đổi điều khoản, chấm dứt hoặc tạm ngừng dịch vụ.

OpenAPI chỉ lưu URL. Nó không nhúng toàn bộ văn bản pháp lý, không ghi nhận người dùng đã chấp thuận và không thay thế cơ chế consent hoặc hợp đồng trong hệ thống đăng ký.

Không dùng trang Privacy Policy thay cho Terms of Service nếu trang đó chỉ mô tả quyền riêng tư. Hai tài liệu có thể liên kết với nhau nhưng có mục đích khác nhau.

## 6. Thông tin sở hữu API không có field chuẩn riêng

OpenAPI không định nghĩa một field cố định tên `owner` hoặc `copyrightHolder` trong Info Object. Vì vậy, cần chọn cách công bố theo nhu cầu:

1. Dùng `contact.name` để chỉ ra nhóm/tổ chức liên hệ khi tổ chức đó cũng là đầu mối hỗ trợ.
2. Dùng `info.description` để ghi một câu giới thiệu đơn vị sở hữu hoặc đơn vị cung cấp dịch vụ nếu thông tin này cần hiển thị cho mọi consumer.
3. Dùng vendor extension bắt đầu bằng `x-` khi cần metadata có cấu trúc để portal hoặc pipeline nội bộ đọc.
4. Dùng trang điều khoản hoặc trang pháp lý chính thức để công bố quyền sở hữu, bản quyền và phạm vi cấp phép.

Ví dụ extension:

~~~yaml
info:
  title: Partner API
  version: 1.3.0
  contact:
    name: Partner API Support
    url: https://partners.example.com/support
  x-api-owner:
    legal-entity: Example Corporation
    product: Partner Platform
    accountable-team: API Governance
    support-channel: https://partners.example.com/support
~~~

Tên `x-api-owner` là quy ước riêng của tổ chức, không phải field chuẩn được mọi OpenAPI consumer hiểu. Công cụ không biết extension này có thể bỏ qua nó. Nếu hệ thống khác cần xử lý extension, hãy mô tả schema, giá trị hợp lệ và cách versioning trong tài liệu nội bộ.

Không đưa thông tin nhạy cảm như tên tài khoản nội bộ, số điện thoại cá nhân, địa chỉ nhà hoặc đường dẫn intranet vào document public. Nên dùng tên pháp nhân, nhóm chức năng và kênh liên hệ chính thức.

## 7. Khai báo metadata bằng annotation Swagger

springdoc-openapi hỗ trợ các annotation từ Swagger Core. Có thể đặt `@OpenAPIDefinition` trên một class cấu hình Spring được quản lý:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Contact;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.info.License;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Orders API",
        version = "2.4.0",
        description = "API quản lý đơn hàng và trạng thái giao nhận.",
        termsOfService = "https://api.example.com/terms",
        contact = @Contact(
            name = "Example Platform API Support",
            url = "https://support.example.com/api",
            email = "api-support@example.com"
        ),
        license = @License(
            name = "Apache 2.0",
            url = "https://www.apache.org/licenses/LICENSE-2.0.html"
        )
    )
)
public class OpenApiMetadataConfiguration {
}
~~~

Annotation giúp khai báo metadata tĩnh gần cấu hình API. `@Info` ánh xạ sang Info Object; `@Contact` ánh xạ sang Contact Object; `@License` ánh xạ sang License Object.

Đặt class cấu hình trong package được Spring component scan để springdoc nhận diện. Tài liệu springdoc khuyến nghị khai báo `@OpenAPIDefinition` trong Spring-managed bean để việc quét metadata hoạt động ổn định và hiệu quả.

Với annotation `@License`, ví dụ dùng `name` và `url` để tương thích cả document OpenAPI 3.0. Nếu cần SPDX `identifier` của OpenAPI 3.1+, cách cấu hình bằng model object ở phần sau phù hợp hơn.

## 8. Dùng Spring property để quản lý metadata theo môi trường

Thông tin liên hệ và điều khoản có thể khác giữa môi trường staging và production. Không nên sửa source code mỗi lần đổi URL hỗ trợ. springdoc hỗ trợ Spring property resolver cho một số thuộc tính của Swagger annotation.

Ví dụ `application.yml`:

~~~yaml
api:
  info:
    title: Orders API
    description: API quản lý đơn hàng.
    version: 2.4.0
    terms-of-service: https://api.example.com/terms
    contact:
      name: Example API Support
      url: https://support.example.com/api
      email: api-support@example.com
    license:
      name: Apache 2.0
      url: https://www.apache.org/licenses/LICENSE-2.0.html
~~~

Dùng placeholder trong annotation:

~~~java
@OpenAPIDefinition(
    info = @Info(
        title = "${api.info.title}",
        description = "${api.info.description}",
        version = "${api.info.version}",
        termsOfService = "${api.info.terms-of-service}",
        contact = @Contact(
            name = "${api.info.contact.name}",
            url = "${api.info.contact.url}",
            email = "${api.info.contact.email}"
        ),
        license = @License(
            name = "${api.info.license.name}",
            url = "${api.info.license.url}"
        )
    )
)
~~~

Theo tài liệu springdoc hiện hành, property resolver hỗ trợ các thuộc tính `@Info.title`, `description`, `version`, `termsOfService`; `@Info.license.name/url`; và `@Info.contact.name/email/url`. Không giả định mọi annotation attribute đều tự resolve placeholder.

Nếu dùng nhiều profile, giữ giá trị pháp lý chính thức và metadata public ở cấu hình production có kiểm soát. Không trỏ Terms of Service của production sang trang nội bộ hoặc URL thử nghiệm chỉ có thể truy cập qua VPN.

## 9. Cấu hình metadata bằng OpenAPI bean

Khi cần giá trị động, SPDX identifier, hoặc kết hợp metadata với cấu hình khác, tạo bean `OpenAPI`:

~~~java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.info.License;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiBeanConfiguration {

    @Bean
    OpenAPI customOpenAPI() {
        Info info = new Info()
            .title("Orders API")
            .version("2.4.0")
            .description("API quản lý đơn hàng và trạng thái giao nhận.")
            .termsOfService("https://api.example.com/terms")
            .contact(new Contact()
                .name("Example Platform API Support")
                .url("https://support.example.com/api")
                .email("api-support@example.com"))
            .license(new License()
                .name("Apache 2.0")
                .url("https://www.apache.org/licenses/LICENSE-2.0.html"));

        return new OpenAPI().info(info);
    }
}
~~~

Đối với OpenAPI 3.1+, nếu dùng SPDX identifier:

~~~java
License license = new License()
    .name("Apache 2.0")
    .identifier("Apache-2.0");
~~~

Không gọi đồng thời `url` và `identifier` trên cùng License Object. Nếu output vẫn là OpenAPI 3.0, dùng `url` thay cho `identifier`.

`OpenAPI` bean là cách phù hợp khi cần lấy metadata từ Spring configuration, biến môi trường hoặc cấu hình triển khai. Có thể inject giá trị bằng `@Value` hoặc dùng một bean properties đã bind bằng `@ConfigurationProperties`.

## 10. Chọn annotation hay OpenAPI bean?

| Tiêu chí | Annotation `@OpenAPIDefinition` | OpenAPI bean |
|---|---|---|
| Metadata tĩnh | Gọn, dễ đọc | Dài hơn |
| Property placeholder được hỗ trợ | Có, với các thuộc tính được springdoc liệt kê | Dùng trực tiếp Spring injection |
| Metadata động hoặc logic điều kiện | Hạn chế | Linh hoạt |
| SPDX license identifier | Dễ cấu hình hơn bằng model object | Có thể gọi `License.identifier` khi dùng OAS 3.1+ |
| Vendor extension | Có thể khai báo annotation extension | Có thể gọi `addExtension` |
| Tích hợp nhiều cấu hình runtime | Không thuận tiện bằng | Phù hợp |

Chọn một nguồn cấu hình chính cho Info Object. Nếu đồng thời khai báo annotation và bean với cùng trường, cần kiểm tra kết quả document thực tế để tránh metadata bị ghi đè hoặc khó xác định nguồn giá trị.

## 11. Metadata riêng cho từng OpenAPI group

Một ứng dụng có thể công bố nhiều document, ví dụ `public`, `partner` và `internal`. Khi đó, mỗi document có thể cần đầu mối liên hệ, license hoặc terms khác nhau.

| Group | Contact | License/Terms |
|---|---|---|
| `public` | Kênh hỗ trợ công khai | Điều khoản dịch vụ public |
| `partner` | Nhóm Partner Engineering | Điều khoản tích hợp đối tác |
| `internal` | Nhóm Platform Engineering | Chính sách sử dụng nội bộ |

Không nên gắn một địa chỉ email nội bộ vào document public chỉ vì dùng chung một cấu hình global. Nếu metadata khác nhau theo group, gắn customizer vào đúng `GroupedOpenApi`:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;

@Bean
GroupedOpenApi partnerApi() {
    return GroupedOpenApi.builder()
        .group("partner")
        .pathsToMatch("/partner/**")
        .addOpenApiCustomizer(openApi -> {
            if (openApi.getInfo() != null) {
                openApi.getInfo().setContact(
                    new io.swagger.v3.oas.models.info.Contact()
                        .name("Partner API Support")
                        .url("https://partners.example.com/support")
                        .email("partner-api@example.com")
                );
                openApi.getInfo().setTermsOfService(
                    "https://partners.example.com/legal/terms"
                );
            }
        })
        .build();
}
~~~

`OpenApiCustomizer` gắn với một `GroupedOpenApi` chỉ tác động document của group đó. Tài liệu springdoc cũng phân biệt customizer cho document mặc định với customizer cần áp dụng cho mọi group; nếu muốn dùng chung toàn bộ group, xem `GlobalOpenApiCustomizer`. Hãy kiểm tra đúng phạm vi trước khi thay metadata.

## 12. Kiểm tra metadata trong JSON và YAML được sinh ra

Sau khi chạy ứng dụng, kiểm tra Info Object từ endpoint OpenAPI:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs | jq '.info'
~~~

Kiểm tra từng trường:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs | jq '.info.contact'
curl -fsS http://localhost:8080/v3/api-docs | jq '.info.license'
curl -fsS http://localhost:8080/v3/api-docs | jq -r '.info.termsOfService'
curl -fsS http://localhost:8080/v3/api-docs | jq '.info["x-api-owner"]'
~~~

Nếu ứng dụng có group:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs/partner | jq '.info'
~~~

Để kiểm tra YAML:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs.yaml
~~~

Đối chiếu output với cấu hình mong đợi:

- `info.title` và `info.version` không rỗng.
- `contact.url` là URI public hợp lệ; `contact.email` đúng định dạng.
- `license.name` có giá trị; chỉ có `url` hoặc `identifier` theo OpenAPI version.
- `termsOfService` trỏ đến đúng điều khoản hiện hành.
- `x-api-owner` chỉ chứa metadata mà tổ chức cho phép công khai.

Đừng chỉ nhìn trang Swagger UI. Một số UI có thể không hiển thị mọi vendor extension hoặc không làm nổi bật điều khoản; JSON/YAML mới là output cần kiểm tra khi xác nhận document.

## 13. Kiểm thử metadata bằng MockMvc

Có thể khóa các trường quan trọng bằng integration test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OpenApiMetadataTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentContainsPublicOwnershipAndLegalMetadata() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.info.title").value("Orders API"))
            .andExpect(jsonPath("$.info.version").value("2.4.0"))
            .andExpect(jsonPath("$.info.contact.name")
                .value("Example Platform API Support"))
            .andExpect(jsonPath("$.info.contact.email")
                .value("api-support@example.com"))
            .andExpect(jsonPath("$.info.termsOfService")
                .value("https://api.example.com/terms"))
            .andExpect(jsonPath("$.info.license.name")
                .value("Apache 2.0"));
    }
}
~~~

Nếu dùng `license.identifier`, kiểm tra đúng field đó và xác nhận `license.url` không xuất hiện. Nếu dùng vendor extension, kiểm tra JSONPath tương ứng. Với group có metadata riêng, viết test riêng cho endpoint group thay vì chỉ test document mặc định.

## 14. Quản lý metadata qua môi trường và release

Thông tin pháp lý và liên hệ có vòng đời riêng với phiên bản API. Nên quản lý chúng như cấu hình được review:

1. Lưu Terms of Service và license text tại URL ổn định do tổ chức quản lý.
2. Dùng mailbox hoặc support portal có người chịu trách nhiệm.
3. Đặt metadata public trong cấu hình version-controlled hoặc configuration store được quản trị.
4. Kiểm tra URL từ mạng ngoài trước khi release.
5. Khi thay đổi pháp nhân, contact hoặc điều khoản, cập nhật document và quy trình thông báo tương ứng.
6. Lưu artifact OpenAPI cùng release để biết document tại thời điểm phát hành đã công bố metadata nào.

Không tự động thay đổi `termsOfService` theo từng deployment nếu nội dung điều khoản thực tế không thay đổi. Staging và production có thể khác base URL của API nhưng vẫn dùng cùng điều khoản pháp lý; điều này cần được quyết định bởi chủ sở hữu dịch vụ.

## 15. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Swagger UI không hiện contact | Annotation nằm ngoài Spring component scan hoặc Info chưa được tạo | Đặt cấu hình trong Spring-managed bean và kiểm tra JSON |
| Contact email sai | Dùng mailbox cá nhân cũ hoặc chuỗi không đúng định dạng | Dùng mailbox hỗ trợ có vòng đời ổn định |
| Contact URL trỏ vào intranet | Copy URL nội bộ sang document public | Thay bằng trang hỗ trợ public |
| License không xuất hiện | Chỉ ghi tên giấy phép trong description | Đưa vào `info.license` |
| Validator báo lỗi license | Thiếu `name` hoặc dùng `identifier` với OpenAPI 3.0 | Bổ sung name; dùng URL cho OAS 3.0 hoặc identifier cho OAS 3.1+ |
| Có cả license url và identifier | Cấu hình đồng thời hai trường loại trừ nhau | Chỉ chọn một |
| TermsOfService trỏ nhầm Privacy Policy | Nhầm điều khoản sử dụng với chính sách quyền riêng tư | Dùng URL Terms of Service đúng nghĩa |
| Placeholder vẫn còn nguyên trong JSON | Dùng property resolver trên thuộc tính không được hỗ trợ hoặc cấu hình sai | Kiểm tra danh sách thuộc tính springdoc hỗ trợ và output |
| Metadata group bị giống nhau ngoài dự kiến | Dùng OpenAPI bean global hoặc customizer sai phạm vi | Gắn customizer vào group tương ứng và kiểm tra từng endpoint |
| Owner extension không hiển thị trên UI | UI không render vendor extension | Kiểm tra JSON/YAML hoặc cấu hình portal đọc extension |
| Metadata bị ghi đè | Khai báo đồng thời annotation và OpenAPI bean | Chọn nguồn cấu hình chính, kiểm tra output sau cùng |
| Thông tin pháp lý đã cũ | URL bị thay đổi hoặc nội dung điều khoản đã được cập nhật | Dùng URL ổn định và quy trình review trước release |

## 16. Quy trình hoàn thiện thông tin sở hữu API

Thực hiện theo thứ tự:

1. Xác định pháp nhân sở hữu hoặc cung cấp API.
2. Xác định nhóm vận hành và kênh hỗ trợ mà consumer có thể liên hệ.
3. Xác định giấy phép thực sự áp dụng cho API; kiểm tra với chủ sở hữu pháp lý.
4. Xác định URL Terms of Service và bảo đảm nội dung phù hợp với dịch vụ.
5. Chọn field chuẩn: `contact`, `license`, `termsOfService`.
6. Nếu cần thông tin owner có cấu trúc, định nghĩa vendor extension `x-api-owner` và tài liệu hóa schema của extension.
7. Chọn annotation hoặc OpenAPI bean để cấu hình metadata.
8. Nếu có nhiều group, xác định metadata chung và metadata riêng của từng group.
9. Lấy JSON/YAML từ `/v3/api-docs` và kiểm tra tất cả trường.
10. Chạy integration test để tránh metadata bị mất khi nâng springdoc hoặc thay cấu hình.
11. Lưu document cùng release và cập nhật URL pháp lý khi có thay đổi.

## 17. Checklist trước khi công bố

- [ ] `info.title` và `info.version` có giá trị rõ ràng.
- [ ] `contact.name` chỉ đúng đầu mối hoặc tổ chức liên hệ.
- [ ] `contact.url` là URI public hợp lệ nếu được khai báo.
- [ ] `contact.email` là mailbox có người hoặc quy trình theo dõi.
- [ ] `license.name` mô tả đúng giấy phép áp dụng cho API.
- [ ] Chỉ dùng `license.url` hoặc `license.identifier`, không dùng đồng thời.
- [ ] `license.identifier` chỉ dùng khi output OpenAPI 3.1 trở lên.
- [ ] `termsOfService` trỏ đến điều khoản sử dụng thực tế.
- [ ] Không nhầm Terms of Service với Privacy Policy hoặc trang hỗ trợ.
- [ ] Thông tin sở hữu không bị nhầm với đầu mối hỗ trợ.
- [ ] Vendor extension bắt đầu bằng `x-` và có quy ước được tài liệu hóa.
- [ ] Không công khai thông tin cá nhân hoặc đường dẫn nội bộ.
- [ ] Metadata từng group được kiểm tra riêng.
- [ ] JSON/YAML được kiểm tra sau khi springdoc sinh ra.
- [ ] Có integration test bảo vệ các trường metadata quan trọng.
- [ ] URL pháp lý và support được kiểm tra trước mỗi release.

## 18. Tài liệu tham khảo chính thức

- [OpenAPI Specification 3.2.1 — Info Object](https://spec.openapis.org/oas/latest.html#info-object) — các trường title, summary, description, termsOfService, contact, license và version.
- [OpenAPI Specification 3.2.1 — Contact Object](https://spec.openapis.org/oas/latest.html#contact-object) — name, url và email của đầu mối liên hệ.
- [OpenAPI Specification 3.2.1 — License Object](https://spec.openapis.org/oas/latest.html#license-object) — name, SPDX identifier và URL giấy phép; identifier và url loại trừ lẫn nhau.
- [OpenAPI Specification 3.0.4 — License Object](https://spec.openapis.org/oas/v3.0.4.html#license-object) — cấu trúc License Object trong OAS 3.0.
- [springdoc-openapi — Adding API Information](https://springdoc.org/#adding-api-information-and-security-documentation) — khai báo metadata bằng Swagger annotation.
- [springdoc-openapi — Spring property resolver for annotations](https://springdoc.org/#can-i-use-spring-property-with-swagger-annotations) — các thuộc tính @Info, contact và license hỗ trợ placeholder.
- [springdoc-openapi — Customizing the OpenAPI object](https://springdoc.org/#can-i-customize-openapi-object-programmatically) — cấu hình OpenAPI bean và customizer.
- [SPDX License List](https://spdx.org/licenses/) — danh sách định danh SPDX hợp lệ.

`contact`, `license` và `termsOfService` làm rõ ai hỗ trợ API, giấy phép nào được công bố và điều khoản nào áp dụng. Thông tin sở hữu có thể được bổ sung bằng vendor extension khi cần, nhưng phải phân biệt rõ metadata chuẩn với quy ước riêng của tổ chức. Hãy xác minh JSON/YAML mà springdoc sinh ra, kiểm tra từng group và giữ các URL pháp lý, liên hệ ổn định trong suốt vòng đời release.
