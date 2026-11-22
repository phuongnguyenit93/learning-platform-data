# Sắp xếp đầu ra ổn định và xử lý metadata biến động

Khi xuất OpenAPI để đưa vào Git, phát hành SDK hoặc chạy contract test trong CI, tài liệu cần ổn định giữa những lần build không làm thay đổi hợp đồng API. Nếu chỉ đổi thứ tự key, diff có thể rất lớn dù nội dung không đổi. Nếu metadata như server URL, API version hoặc locale thay đổi ngoài dự kiến, pipeline có thể báo sai rằng hợp đồng đã thay đổi.

Với springdoc-openapi, cần phân biệt ba việc:

1. **Sắp xếp cấu trúc đầu ra:** giữ thứ tự key trong JSON/YAML ổn định để diff dễ đọc.
2. **Sắp xếp cách hiển thị:** điều khiển thứ tự tag và operation trong Swagger UI.
3. **Kiểm soát metadata biến động:** chuẩn hóa version, server URL, locale, group và dữ liệu được thêm bởi customizer.

Ba việc này có liên quan nhưng không thay thế nhau. Bật sắp xếp key không cố định được host của request; sắp xếp operation trong Swagger UI không làm file OpenAPI JSON ổn định; cache cũng không sửa được metadata đã được tạo từ nguồn không nhất quán.

## 1. Đầu ra ổn định có ý nghĩa gì?

Đầu ra ổn định (deterministic output) nghĩa là cùng một source code, dependency, cấu hình, locale và đầu vào tạo ra cùng một tài liệu OpenAPI về mặt nội dung và thứ tự biểu diễn mà dự án đã chọn.

Ví dụ hai tài liệu dưới đây tương đương về cấu trúc JSON vì thứ tự key trong object không làm thay đổi ý nghĩa:

~~~json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Order API",
    "version": "1.4.0"
  }
}
~~~

~~~json
{
  "info": {
    "version": "1.4.0",
    "title": "Order API"
  },
  "openapi": "3.1.0"
}
~~~

Nhưng khi lưu trong Git, hai cách sắp xếp tạo ra diff khác nhau. Một lần đổi thứ tự key có thể làm file thay đổi nhiều dòng dù hợp đồng không đổi.

Đầu ra ổn định giúp:

- Review được thay đổi API thực sự.
- Giảm diff nhiễu trong pull request.
- Tạo checksum có thể tái lập.
- So sánh spec giữa các build.
- Phát hiện breaking change đáng tin cậy hơn.
- Sinh SDK nhất quán.
- Tránh phát hành tài liệu chỉ khác nhau do môi trường chạy.

Tính ổn định không có nghĩa mọi giá trị trong spec phải giống nhau mãi mãi. Khi API version, schema hoặc server public thực sự thay đổi, tài liệu phải thay đổi theo. Mục tiêu là mỗi thay đổi đều có nguyên nhân rõ ràng.

## 2. Phân biệt key order và array order

OpenAPI được biểu diễn bằng JSON hoặc YAML. Cần phân biệt object và array:

- Object là tập hợp các cặp key/value; thứ tự key không mang ý nghĩa theo JSON.
- Array có thứ tự phần tử; thứ tự có thể ảnh hưởng cách hiển thị hoặc cách công cụ diễn giải.

Ví dụ paths và components.schemas là object. Việc sắp xếp key theo alphabet giúp diff ổn định mà không đổi ý nghĩa.

Ngược lại, servers, tags, security và một số danh sách khác là array. Thứ tự có thể được người dùng nhìn thấy hoặc có ý nghĩa trong cách chọn lựa của công cụ. Không nên áp dụng một bộ sắp xếp tổng quát cho mọi array.

| Cấu trúc | Dạng dữ liệu | Cách xử lý |
|---|---|---|
| paths | Object | Có thể sắp xếp key |
| components.schemas | Object | Có thể sắp xếp key |
| components.responses | Object | Có thể sắp xếp key |
| components.securitySchemes | Object | Có thể sắp xếp key |
| tags | Array | Chọn thứ tự hiển thị có chủ đích |
| servers | Array | Giữ thứ tự lựa chọn có ý nghĩa |
| security requirements | Array | Giữ đúng logic OR/AND và thứ tự mong muốn |
| examples | Object hoặc array tùy vị trí | Không tự ý đảo thứ tự ví dụ |
| enum | Array | Có thể mang thứ tự trình bày; giữ quy ước của API |

Sắp xếp key là thao tác trình bày. Sắp xếp array cần dựa trên ý nghĩa của từng trường.

## 3. Bật sắp xếp key ổn định trong springdoc

springdoc cung cấp thuộc tính springdoc.writer-with-order-by-keys. Thuộc tính này bật thứ tự key mang tính xác định và theo alphabet khi ghi tài liệu.

application.yml:

~~~yaml
springdoc:
  writer-with-order-by-keys: true
~~~

application.properties:

~~~properties
springdoc.writer-with-order-by-keys=true
~~~

Mặc định thuộc tính này là false. Khi bật, đầu ra được ghi theo thứ tự key ổn định hơn, giúp giảm diff chỉ do thứ tự map hoặc cách ghi tài liệu.

Có thể dùng trong profile export:

~~~yaml
springdoc:
  writer-with-order-by-keys: true
  api-docs:
    enabled: true
~~~

Hãy kiểm tra JSON/YAML được tạo trên đúng phiên bản springdoc đang dùng. Nếu dự án có custom serializer, custom OpenAPI converter hoặc bước hậu xử lý riêng, các bước đó cũng phải được kiểm tra.

Thuộc tính này không tự chuẩn hóa các giá trị động như info.version, servers[].url, description theo locale hoặc extension được customizer thêm vào.

## 4. Sắp xếp operation và tag trong Swagger UI

Swagger UI có hai tùy chọn sắp xếp thường dùng:

- operationsSorter: sắp xếp operation trong từng nhóm tag.
- tagsSorter: sắp xếp tag.

Ví dụ:

~~~yaml
springdoc:
  swagger-ui:
    operations-sorter: alpha
    tags-sorter: alpha
~~~

Hoặc application.properties:

~~~properties
springdoc.swagger-ui.operationsSorter=alpha
springdoc.swagger-ui.tagsSorter=alpha
~~~

operationsSorter có thể dùng:

- alpha: sắp xếp operation theo path theo thứ tự chữ cái.
- method: sắp xếp theo HTTP method.
- Một hàm JavaScript sort tùy chỉnh theo cấu hình Swagger UI.

tagsSorter có thể dùng alpha hoặc hàm sort phù hợp. Nếu không khai báo, Swagger UI giữ thứ tự operation nhận được từ server.

Các tùy chọn này thay đổi cách hiển thị trên giao diện. Chúng không thay đổi nội dung /v3/api-docs, không sắp xếp JSON file được export và không tác động tới client generator.

Vì vậy, nếu yêu cầu là diff OpenAPI JSON ổn định, cần cấu hình writer và metadata; chỉ bật operationsSorter là chưa đủ.

## 5. Ví dụ cấu hình kết hợp cho đầu ra dễ review

Một cấu hình có thể kết hợp writer order và UI sorter:

~~~yaml
springdoc:
  writer-with-order-by-keys: true
  swagger-ui:
    operations-sorter: alpha
    tags-sorter: alpha
    display-operation-id: true
~~~

Ý nghĩa:

- Writer sắp xếp key khi tạo tài liệu.
- Swagger UI hiển thị tag theo alphabet.
- Swagger UI hiển thị operation theo path.
- Operation ID được hiển thị để developer dễ đối chiếu client method.

Đây là cấu hình phục vụ cả review file và trải nghiệm tra cứu. Nếu API cần giữ thứ tự tag nghiệp vụ riêng, không nên bật sorter chỉ vì muốn mọi thứ theo alphabet.

Hãy xác định mục tiêu cho từng môi trường. Ví dụ, CI có thể cần writer ổn định để xuất artifact; UI production có thể giữ thứ tự tag do nhóm API thiết kế.

## 6. Chuẩn hóa API metadata

Metadata của OpenAPI thường nằm trong info:

~~~yaml
info:
  title: Order API
  description: API quản lý đơn hàng
  version: 1.4.0
  termsOfService: https://example.com/terms
  contact:
    name: API Support
    email: api-support@example.com
  license:
    name: Apache 2.0
    url: https://www.apache.org/licenses/LICENSE-2.0
~~~

Cần phân biệt:

- openapi: phiên bản đặc tả OpenAPI, ví dụ 3.1.0.
- info.version: phiên bản hợp đồng API, ví dụ 1.4.0.
- Phiên bản ứng dụng Spring Boot: phiên bản artifact được triển khai.
- Phiên bản springdoc: phiên bản thư viện sinh tài liệu.

Không dùng một giá trị cho tất cả các khái niệm. Nâng springdoc từ 2.x lên 3.x không có nghĩa API nghiệp vụ tự động chuyển từ 1.4.0 lên 3.0.0.

info.version nên được lấy từ nguồn versioning có chủ đích, thường là version của API hoặc release contract đã được nhóm thống nhất.

## 7. Đặt info.version từ cấu hình build

Có thể cung cấp API version qua application.yml:

~~~yaml
api:
  release-version: 1.4.0
~~~

Sau đó dùng OpenAPI bean để thiết lập metadata:

~~~java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration
class OpenApiMetadataConfiguration {

    @Bean
    OpenAPI openApiMetadata(Environment environment) {
        String apiVersion =
            environment.getRequiredProperty("api.release-version");

        return new OpenAPI()
            .info(new Info()
                .title("Order API")
                .description("API quản lý đơn hàng")
                .version(apiVersion));
    }
}
~~~

Trong CI, có thể truyền version theo release pipeline hoặc build property đã được pin. Cùng một commit và cùng một release input cần tạo cùng giá trị info.version.

Không lấy info.version từ thời điểm chạy như LocalDateTime.now(). Nếu mỗi lần khởi động tạo version khác, spec sẽ thay đổi dù API contract không đổi.

Nếu dùng Maven hoặc Gradle để đưa project version vào cấu hình, hãy kiểm tra giá trị cuối cùng được Spring nạp và bảo đảm profile export không ghi đè ngoài ý muốn.

## 8. Không đưa timestamp biến động vào contract nếu không cần

Một lỗi thường gặp là customizer thêm thời điểm sinh tài liệu:

~~~yaml
info:
  x-generated-at: "2026-11-20T10:15:30Z"
~~~

Mỗi lần export, giá trị timestamp thay đổi và làm file OpenAPI khác nhau. Điều này tạo diff nhiễu, checksum mới và có thể kích hoạt quy trình phát hành SDK không cần thiết.

Nếu cần lưu thời điểm tạo artifact, ưu tiên lưu trong:

- Metadata của CI job.
- Tên hoặc manifest của artifact.
- Release record.
- Build provenance.
- Header hoặc log triển khai.

Nếu bắt buộc phải đưa timestamp vào OpenAPI extension, hãy xác định rõ đây là metadata biến động và loại nó khỏi phép so sánh contract hoặc chuẩn hóa về một giá trị cố định trong bước diff.

Không đưa thông tin bí mật, token, hostname nội bộ hoặc dữ liệu theo từng người dùng vào description, example hay extension.

## 9. Chuẩn hóa server URL

Server URL có thể được springdoc suy ra từ request hiện tại. Điều này thuận tiện khi ứng dụng chạy qua nhiều hostname hoặc reverse proxy, nhưng có thể làm artifact CI thay đổi theo host gọi tài liệu.

Ví dụ cùng một API được gọi qua:

~~~text
http://localhost:8080
https://api.example.com
https://partner.example.com/gateway
~~~

Nếu document dùng server URL suy ra từ request, kết quả có thể khác nhau. CI chạy ở localhost có thể export:

~~~yaml
servers:
  - url: http://localhost:8080
~~~

Trong khi artifact phát hành cần:

~~~yaml
servers:
  - url: https://api.example.com
~~~

Đối với tài liệu phát hành, nên chọn một nguồn URL ổn định:

- Khai báo server public tường minh.
- Lấy server URL từ property cố định của profile export.
- Dùng ServerBaseUrlCustomizer để chuẩn hóa URL đã suy ra.
- Kiểm tra forwarded headers nếu URL phải được suy ra từ reverse proxy.

Không export từ một request ngẫu nhiên rồi commit URL nội bộ vào spec.

## 10. Khai báo servers cố định cho profile export

Có thể dùng cấu hình OpenAPI bean để đặt server URL theo property:

~~~yaml
api:
  public-base-url: https://api.example.com/v1
  release-version: 1.4.0
~~~

Ví dụ:

~~~java
@Bean
OpenAPI openApiMetadata(Environment environment) {
    String apiVersion =
        environment.getRequiredProperty("api.release-version");
    String publicBaseUrl =
        environment.getRequiredProperty("api.public-base-url");

    return new OpenAPI()
        .info(new Info()
            .title("Order API")
            .version(apiVersion))
        .servers(List.of(
            new Server()
                .url(publicBaseUrl)
                .description("Public API")
        ));
}
~~~

Trong profile CI, đặt giá trị cố định. Profile export cần dùng cùng một giá trị cho mọi lần chạy của cùng release.

Nếu cần export spec không gắn với môi trường cụ thể, có thể cân nhắc server URL tương đối / hoặc cách phân phối artifact mà consumer tự cấu hình base URL; cần xác minh cách công cụ client xử lý server tương đối.

## 11. Khi nào cần tắt cache?

springdoc cache OpenAPI document đã tính toán. Theo mặc định, cache được bật; có thể tắt bằng:

~~~yaml
springdoc:
  cache:
    disabled: true
~~~

Trong application.properties, tên thuộc tính tương ứng là:

~~~properties
springdoc.cache.disabled=true
~~~

Tắt cache có ích khi metadata phụ thuộc request, ví dụ:

- Server URL thay đổi theo host.
- Proxy gửi forwarded headers khác nhau.
- Document được tạo theo tenant.
- Locale được lựa chọn theo Accept-Language.
- Customizer đọc dữ liệu request và cố ý tạo nội dung khác nhau.

Nếu tài liệu cần ổn định và metadata không phụ thuộc request, giữ cache bật thường hợp lý hơn.

Không tắt cache chỉ để mong source code được cập nhật trong một process đang chạy. Khi controller, DTO hoặc annotation thay đổi, cách triển khai thông thường là build và restart/redeploy ứng dụng.

Tắt cache không tự chuẩn hóa dữ liệu động. Nó chỉ khiến document được tính lại thay vì tái sử dụng bản đã cache.

## 12. Cache, locale và Accept-Language

Nếu description hoặc summary được dịch theo locale, cùng một OpenAPI endpoint có thể trả nội dung khác nhau theo Accept-Language.

Ví dụ:

~~~bash
curl -H "Accept-Language: vi-VN" \
  http://localhost:8080/v3/api-docs
~~~

~~~bash
curl -H "Accept-Language: en-US" \
  http://localhost:8080/v3/api-docs
~~~

Nếu CI export tài liệu tiếng Việt ở build này và tiếng Anh ở build sau, diff sẽ rất lớn dù API không đổi.

Để có artifact ổn định:

- Chọn một locale export cố định.
- Gửi cùng Accept-Language trong mọi lần build.
- Đảm bảo message bundle và bản dịch được version control.
- Không để locale mặc định phụ thuộc máy chạy CI.
- Nếu export nhiều ngôn ngữ, lưu mỗi locale thành artifact riêng.

Cache của springdoc có thể giữ một document cho từng locale được yêu cầu. Cấu hình preload locale không thay thế việc chọn header trong bước export.

## 13. Metadata theo group và customizer

Ứng dụng có thể sinh nhiều OpenAPI document bằng GroupedOpenApi. Mỗi group có paths, packages, tags và customizer riêng.

Cần phân biệt ba phạm vi:

| Cơ chế | Phạm vi |
|---|---|
| OpenAPI bean | Metadata nền tảng dùng chung |
| OpenApiCustomizer | Tùy biến document mặc định; theo FAQ springdoc, không tự áp dụng cho mọi group |
| GlobalOpenApiCustomizer | Tùy biến toàn cục, có thể áp dụng cả grouped documents |
| Customizer gắn trong GroupedOpenApi | Tùy biến riêng group tương ứng |

Ví dụ group:

~~~java
@Bean
GroupedOpenApi partnerApi(OpenApiCustomizer partnerCustomizer) {
    return GroupedOpenApi.builder()
        .group("partner")
        .pathsToMatch("/api/partner/**")
        .addOpenApiCustomizer(partnerCustomizer)
        .build();
}
~~~

Nếu một metadata phải xuất hiện ở tất cả group, hãy chọn OpenAPI bean hoặc GlobalOpenApiCustomizer theo mục đích. Nếu chỉ một group có server URL, contact hoặc description riêng, gắn customizer vào group đó.

Đừng giả định document mặc định và document group có cùng metadata chỉ vì chúng được tạo trong cùng ứng dụng.

## 14. Viết customizer có tính xác định

Customizer nên là hàm biến đổi có kết quả ổn định với cùng đầu vào. Tránh phụ thuộc:

- Thời gian hiện tại.
- Số ngẫu nhiên.
- Hostname của máy CI.
- Thứ tự duyệt HashMap không được chuẩn hóa.
- Dữ liệu ngoài không được version control.
- Request user hoặc tenant nếu artifact cần dùng chung.
- Kết quả truy vấn không có ORDER BY.

Ví dụ cập nhật version từ cấu hình:

~~~java
@Bean
GlobalOpenApiCustomizer releaseVersionCustomizer(
    Environment environment
) {
    return openApi -> {
        if (openApi.getInfo() != null) {
            openApi.getInfo().setVersion(
                environment.getRequiredProperty("api.release-version")
            );
        }
    };
}
~~~

Customizer này dùng một property cố định trong profile export. Cùng input tạo cùng info.version.

Nếu customizer thêm tag hoặc server, hãy xác định thứ tự rõ ràng. Tránh thêm cùng một phần tử mỗi lần customizer được gọi mà không kiểm tra phần tử đã tồn tại, đặc biệt khi cache tắt hoặc document được tạo nhiều lần.

## 15. Sắp xếp tag trong OpenAPI model

Nếu muốn tag trong document luôn có thứ tự alphabet, có thể sắp xếp danh sách tag bằng customizer:

~~~java
@Bean
GlobalOpenApiCustomizer stableTagOrder() {
    return openApi -> {
        if (openApi.getTags() != null) {
            openApi.getTags().sort(
                Comparator.comparing(
                    Tag::getName,
                    Comparator.nullsLast(String::compareTo)
                )
            );
        }
    };
}
~~~

Ví dụ cần import GlobalOpenApiCustomizer, Tag và Comparator theo phiên bản springdoc/swagger-models của dự án.

Chỉ sắp xếp khi thứ tự tag không phải thứ tự nghiệp vụ được nhóm chủ ý thiết kế. Nếu nhóm muốn tag quan trọng xuất hiện trước, hãy khai báo thứ tự tường minh thay vì alphabet.

Đây là thay đổi trong OpenAPI model và có thể ảnh hưởng document được export. Khác với tagsSorter, vốn chỉ thay đổi cách Swagger UI hiển thị.

## 16. Thứ tự customizer và tính lặp lại

Một ứng dụng có thể có nhiều customizer:

- Customizer thêm server.
- Customizer cập nhật Info.
- Customizer thêm security scheme.
- Customizer gắn response chung.
- Customizer sắp xếp tag.

Nếu customizer phụ thuộc kết quả của customizer trước, thứ tự thực thi cần được kiểm soát. Không nên để một customizer ghi đè metadata do customizer khác vừa thêm.

Một số nguyên tắc:

1. Mỗi customizer có một trách nhiệm rõ ràng.
2. Tránh thay toàn bộ Info nếu chỉ cần đổi version.
3. Kiểm tra null trước khi sửa model.
4. Tránh thêm phần tử trùng khi customizer chạy nhiều lần.
5. Dùng cùng thứ tự bean/configuration giữa các profile.
6. Viết test cho kết quả cuối cùng thay vì giả định thứ tự từ tên method.

Nếu dùng @Order hoặc cơ chế ordering của Spring, hãy xác minh extension point cụ thể có tôn trọng thứ tự đó trong phiên bản đang dùng. Không suy ra thứ tự chỉ từ cách các bean được khai báo trong file Java.

## 17. Sắp xếp key bằng bước hậu xử lý JSON

Nếu cần chuẩn hóa JSON artifact sau khi tải, có thể dùng công cụ JSON sắp xếp key. Ví dụ jq -S sắp xếp key của object:

~~~bash
jq -S . target/openapi.json > target/openapi.sorted.json
~~~

jq -S không tự sắp xếp array. Đây là điều tốt vì array có thể mang ý nghĩa hoặc thứ tự hiển thị cần giữ.

Nếu dùng bước hậu xử lý:

- Không thay đổi giá trị schema.
- Không đổi kiểu number/string/null.
- Không loại bỏ extension.
- Không sort array một cách tổng quát.
- Chạy validator sau bước chuẩn hóa.
- Giữ file raw để so sánh khi điều tra vấn đề serializer.

Không nên dùng một lệnh sort text đơn giản cho JSON hoặc YAML vì có thể làm hỏng cấu trúc lồng nhau.

## 18. Chuẩn hóa metadata build

Một số metadata thường được đưa vào OpenAPI:

- info.version.
- info.description.
- info.contact.
- servers.
- externalDocs.
- Extension bắt đầu bằng x-.

Cần phân loại chúng:

| Metadata | Nguồn ổn định gợi ý | Có nên biến động mỗi build? |
|---|---|---|
| info.title | Cấu hình module | Không |
| info.version | API release version | Chỉ khi release contract đổi |
| info.description | Source/config version control | Không |
| contact/license | Cấu hình đã review | Không |
| servers | Public base URL theo profile | Chỉ khi môi trường hoặc endpoint public đổi có chủ đích |
| x-build-revision | Commit SHA | Có chủ đích theo commit |
| x-generated-at | Thời điểm build | Thường nên để ngoài spec |

Nếu cần truy vết build, x-build-revision có thể hữu ích vì commit SHA ổn định cho cùng một source revision. Nhưng không nên đưa toàn bộ environment variable, hostname nội bộ hoặc secret vào extension.

## 19. Tạo profile export riêng cho CI

Có thể tạo application-ci.yml để cố định metadata:

~~~yaml
springdoc:
  writer-with-order-by-keys: true
  cache:
    disabled: false
  swagger-ui:
    enabled: false

api:
  release-version: 1.4.0
  public-base-url: https://api.example.com/v1
~~~

Profile này có thể:

- Bật OpenAPI endpoint để export.
- Tắt Swagger UI nếu CI chỉ cần JSON/YAML.
- Bật writer key ordering.
- Giữ cache bật khi metadata ổn định.
- Dùng API version và public base URL cố định.

Nếu export document có server URL phụ thuộc request, hãy dùng explicit server trong profile hoặc cố định request URL/forwarded headers. Đừng để CI export theo localhost rồi commit artifact dành cho public API.

Profile export nên được version control. Không đưa secret vào profile; nếu cần authentication để tải docs, lấy credential từ secret store của CI.

## 20. Export OpenAPI JSON trong CI

Một quy trình đơn giản là khởi động ứng dụng với profile export rồi tải spec:

~~~bash
java -jar app.jar --spring.profiles.active=ci
~~~

Sau khi ứng dụng sẵn sàng:

~~~bash
curl -fsS -H "Accept-Language: en-US" http://localhost:8080/v3/api-docs -o target/openapi.json
~~~

Nếu dùng nhiều group:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs/public -o target/openapi-public.json
curl -fsS http://localhost:8080/v3/api-docs/partner -o target/openapi-partner.json
~~~

Mỗi group nên có file artifact riêng và được kiểm tra độc lập. Không gộp nhiều group bằng cách nối chuỗi JSON.

Sau khi tải:

1. Kiểm tra file không rỗng.
2. Kiểm tra trường openapi.
3. Kiểm tra metadata info.
4. Kiểm tra servers.
5. Kiểm tra path và schema quan trọng.
6. Chạy parser/validator.
7. So sánh với artifact của release trước.

## 21. Export YAML nếu pipeline cần

Nếu ứng dụng cung cấp endpoint YAML mặc định:

~~~bash
curl -fsS -H "Accept-Language: en-US" http://localhost:8080/v3/api-docs.yaml -o target/openapi.yaml
~~~

JSON thường thuận tiện cho xử lý bằng jq, parser và generator. YAML thuận tiện cho review thủ công và các hệ thống quản lý cấu hình.

Dù chọn định dạng nào, cần giữ cùng profile, API version, locale, server URL, group, dependency versions và customizer configuration.

Không so sánh trực tiếp YAML và JSON bằng text diff rồi kết luận contract khác nhau. Nếu hai định dạng cần được đối chiếu, parse về cùng một OpenAPI model hoặc chuẩn hóa về cùng representation trước khi so sánh.

## 22. Kiểm tra artifact trước khi commit

Có thể kiểm tra nhanh JSON:

~~~bash
jq -e '.openapi and .info.title and .info.version and .paths' target/openapi.json
~~~

Kiểm tra server URL:

~~~bash
jq '.servers' target/openapi.json
~~~

Kiểm tra danh sách path:

~~~bash
jq -r '.paths | keys[]' target/openapi.json
~~~

Kiểm tra schema:

~~~bash
jq '.components.schemas | keys' target/openapi.json
~~~

Kiểm tra không có URL nội bộ ngoài dự kiến bằng PowerShell:

~~~powershell
Select-String -Path target/openapi.json -Pattern 'localhost|127\.0\.0\.1|10\.[0-9]+\.[0-9]+\.[0-9]+'
~~~

Lệnh cuối là bước kiểm tra gợi ý trên Windows. Điều chỉnh pattern theo dải mạng và hostname nội bộ của hệ thống; không coi một regex đơn giản là kiểm tra bảo mật đầy đủ.

## 23. So sánh spec với phiên bản trước

Sau khi export, so sánh artifact mới với phiên bản đã phát hành:

~~~bash
git diff --no-index contracts/released/openapi.json target/openapi.json
~~~

Nếu dùng công cụ OpenAPI diff chuyên dụng, có thể phân loại thay đổi:

- Path hoặc method bị xóa.
- Required parameter mới.
- Request body đổi schema.
- Response status bị xóa.
- Field đổi type hoặc format.
- Enum bị thu hẹp.
- Security requirement thay đổi.
- Server URL hoặc media type thay đổi.

Trước khi review, hãy loại bỏ hoặc chuẩn hóa metadata không thuộc contract nếu chúng được sinh từ build hoặc request. Không loại bỏ metadata chỉ vì diff gây phiền; hãy xác định xem thay đổi đó có ý nghĩa với consumer không.

Một thay đổi info.version có thể là release bump có chủ đích. Một thay đổi timestamp không cần thiết có thể là noise. Cả hai đều tạo diff nhưng cần cách review khác nhau.

## 24. Phân biệt diff byte-for-byte và diff ngữ nghĩa

Có hai loại so sánh:

- **Byte diff:** so sánh từng ký tự của hai file.
- **Semantic diff:** parse hai tài liệu và so sánh các thành phần OpenAPI theo ý nghĩa.

Ví dụ:

- Đổi thứ tự key object: byte diff khác, semantic diff thường không khác.
- Đổi thứ tự tag: byte diff khác và UI có thể hiển thị khác, dù operation contract không đổi.
- Đổi response schema từ string sang integer: byte diff và semantic diff đều khác.
- Đổi server URL: có thể không đổi schema operation nhưng ảnh hưởng client request.
- Đổi info.version: metadata contract thay đổi, cần review theo release policy.

Không dùng một phép so sánh duy nhất cho mọi mục tiêu. CI có thể chạy cả reproducibility check và OpenAPI breaking-change check.

## 25. Giữ ổn định dependency và môi trường export

Đầu ra có thể thay đổi khi dependency hoặc môi trường thay đổi, ngay cả khi controller không đổi.

Cần pin hoặc quản lý tập trung:

- Spring Boot version.
- springdoc-openapi version.
- swagger-core/swagger-models version được resolve.
- Jackson version.
- Plugin export hoặc generator.
- Java runtime version nếu ảnh hưởng serialization.
- Profile và property source.
- Locale và timezone.
- Customizer configuration.

Không dùng dependency range hoặc latest trong pipeline phát hành nếu cần artifact tái lập.

Nếu nâng springdoc, có thể có thay đổi về schema inference, component naming hoặc writer behavior. Hãy xem OpenAPI diff như một phần của quá trình nâng cấp dependency, không tự động chấp nhận file mới chỉ vì build thành công.

## 26. Xử lý metadata theo request hoặc tenant

Một số hệ thống tạo tài liệu theo tenant hoặc hostname. Đây là trường hợp cần phân biệt tài liệu dùng chung với tài liệu thực sự cá nhân hóa.

Nếu metadata phụ thuộc request:

- Xác định chính xác trường nào thay đổi.
- Xác minh forwarded headers hoặc tenant context đến từ nguồn tin cậy.
- Tắt cache nếu cần tính lại document theo request.
- Kiểm tra cache key có phân biệt locale/tenant/host cần thiết không.
- Tránh đưa dữ liệu người dùng hoặc bí mật vào spec.
- Không commit một document tenant-specific như hợp đồng chung.

Nếu tài liệu chỉ khác server URL theo domain, cân nhắc dùng servers tường minh hoặc server variables để tránh tạo nhiều bản sao gần giống nhau.

Nếu tài liệu có schema khác nhau theo tenant, hãy cân nhắc công bố group hoặc artifact riêng có version và quyền truy cập rõ ràng. Không dựa vào một customizer đọc request tùy tiện để thay đổi hợp đồng không có kiểm soát.

## 27. Cache và tính ổn định

springdoc mặc định cache OpenAPI description đã tính toán. Có thể tắt bằng:

~~~yaml
springdoc:
  cache:
    disabled: true
~~~

Giữ cache bật khi document ổn định theo request. Tắt cache khi server URL hoặc metadata thực sự phụ thuộc request hiện tại.

Nếu tắt cache, customizer có thể được thực thi nhiều lần. Vì vậy, customizer phải có tính lặp lại: cùng input cho cùng output, không thêm phần tử trùng và không tạo timestamp/random value ngoài ý muốn.

Cache không thay thế việc cố định metadata trong CI. Nếu profile export dùng server URL động, cache chỉ có thể giữ một giá trị không mong muốn lâu hơn.

## 28. Kiểm tra đầu ra ổn định bằng test

Có thể viết integration test kiểm tra metadata và thứ tự đầu ra cơ bản:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class StableOpenApiExportTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void publishesStableApiMetadata() {
        webTestClient.get()
            .uri("/v3/api-docs")
            .header(HttpHeaders.ACCEPT_LANGUAGE, "en-US")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.info.title").isEqualTo("Order API")
            .jsonPath("$.info.version").isEqualTo("1.4.0")
            .jsonPath("$.servers[0].url")
                .isEqualTo("https://api.example.com/v1");
    }
}
~~~

Test này giả định profile test cố định server URL và version. Nếu document được suy ra từ request, hãy kiểm tra URL theo forwarded headers mà test gửi vào.

Có thể tải document hai lần trong cùng cấu hình và so sánh JSON đã chuẩn hóa. Khi so sánh, cần loại trừ hoặc cố định metadata biến động có chủ đích.

Không chỉ kiểm tra một request. Nếu ứng dụng phục vụ nhiều group hoặc locale, test từng biến thể cần được export.

## 29. Kiểm tra customizer áp dụng cho group

Nếu dùng OpenApiCustomizer mặc định, cần xác minh nó có áp dụng cho group hay không. FAQ springdoc nêu rằng OpenApiCustomizer thông thường áp dụng cho document mặc định; muốn áp dụng cả GroupedOpenApi thì dùng GlobalOpenApiCustomizer.

Có thể viết test:

~~~java
@Test
void appliesGlobalMetadataToGroupedDocument() {
    webTestClient.get()
        .uri("/v3/api-docs/partner")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.info.version").isEqualTo("1.4.0");
}
~~~

Nếu metadata chỉ dành cho group partner, test group khác để bảo đảm customizer không làm lộ thông tin hoặc thêm server không phù hợp.

Mỗi group là một contract artifact riêng. Hãy kiểm tra title, version, server, security, paths và schema của từng group.

## 30. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Diff lớn dù API không đổi | Key order hoặc serializer order không ổn định |
| Swagger UI đã sort nhưng JSON vẫn khác | operationsSorter/tagsSorter chỉ ảnh hưởng UI |
| Server URL đổi giữa local và CI | Document được suy ra từ request khác nhau |
| Info version thay đổi mỗi lần build | Đang dùng timestamp hoặc version nguồn không cố định |
| Tài liệu khác ngôn ngữ | Accept-Language hoặc default Locale khác |
| Group thiếu metadata chung | Dùng OpenApiCustomizer thay vì GlobalOpenApiCustomizer |
| Cache giữ server URL cũ | Metadata phụ thuộc request nhưng cache đang bật |
| Tắt cache làm CPU tăng | Document được tính lại cho mỗi request |
| Tag đổi thứ tự ngoài ý muốn | Array bị sort hoặc customizer không xác định thứ tự |
| Enum/examples bị đảo | Bước hậu xử lý đã sort mọi array |
| CI export localhost | Dùng request nội bộ mà không đặt server public cố định |
| Spec chứa timestamp không cần thiết | Customizer thêm dữ liệu thời điểm chạy |
| Client SDK thay đổi nhiều sau nâng dependency | Component name hoặc schema inference thay đổi |
| Artifact YAML và JSON khác nhau | Khác profile, locale, group hoặc thời điểm export |

## 31. Quy trình chuẩn hóa đầu ra cho CI

Một quy trình có thể áp dụng:

1. Pin phiên bản Spring Boot, springdoc và các dependency liên quan.
2. Dùng profile export cố định.
3. Cố định info.version theo release contract.
4. Cố định server URL hoặc forwarded headers.
5. Cố định Accept-Language.
6. Chọn group cần export.
7. Bật springdoc.writer-with-order-by-keys.
8. Quyết định thứ tự tag/operation cho UI riêng.
9. Kiểm tra customizer có áp dụng đúng default document và groups.
10. Export JSON/YAML.
11. Validate cấu trúc và $ref.
12. So sánh byte diff và semantic diff.
13. Review thay đổi schema, status, security và servers.
14. Lưu artifact cùng build provenance.
15. Chỉ publish khi contract checks đạt yêu cầu.

Nếu metadata phụ thuộc request, tắt cache chỉ khi cần; nếu không, giữ cache để tránh tính lại document không cần thiết.

## 32. Checklist

- [ ] Đã bật writer-with-order-by-keys khi cần JSON/YAML có key order ổn định.
- [ ] Đã phân biệt object key order với array order.
- [ ] Không sort mọi array bằng một bước hậu xử lý tổng quát.
- [ ] Đã phân biệt operationsSorter/tagsSorter với thứ tự file OpenAPI.
- [ ] info.version lấy từ release contract ổn định.
- [ ] Không đưa timestamp biến động vào spec nếu không cần.
- [ ] Server URL được cố định hoặc suy ra từ proxy đáng tin cậy.
- [ ] Locale và Accept-Language được cố định trong CI.
- [ ] Đã xác định group nào cần export.
- [ ] Customizer có kết quả xác định và không thêm phần tử trùng.
- [ ] OpenApiCustomizer và GlobalOpenApiCustomizer được dùng đúng phạm vi.
- [ ] Cache chỉ tắt khi metadata phụ thuộc request.
- [ ] Dependency và toolchain được pin.
- [ ] Artifact JSON/YAML được validate.
- [ ] Đã review cả byte diff và semantic diff.
- [ ] CI lưu spec cùng build provenance.
- [ ] Không có secret, hostname nội bộ hoặc dữ liệu tenant ngoài ý muốn.

## 33. Nguồn tra cứu

- [springdoc-openapi – Configuration Properties](https://springdoc.org/properties.html)
- [springdoc-openapi – Core Properties](https://springdoc.org/core-properties.html)
- [springdoc-openapi FAQ – Customizing OpenAPI and grouped documents](https://springdoc.org/faq.html)
- [Swagger UI – Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)
- [jq manual – Sorting object keys](https://jqlang.org/manual/)

Đầu ra ổn định cần cả thứ tự ghi nhất quán lẫn metadata có nguồn rõ ràng. Dùng springdoc.writer-with-order-by-keys để giảm diff do key order, dùng Swagger UI sorter cho trải nghiệm hiển thị, và cố định version, locale, server URL cùng group khi export CI. Với metadata thực sự phụ thuộc request, chỉ tắt cache khi cần tính lại theo request và phải kiểm soát nguồn dữ liệu.
