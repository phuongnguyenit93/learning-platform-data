# Nạp trước theo nhóm hoặc ngôn ngữ khi phiên bản hỗ trợ

Springdoc tạo OpenAPI document từ controller, model, annotation, cấu hình và các customizer của ứng dụng. Nếu document lớn hoặc có nhiều nhóm API, lần gọi đầu tiên có thể tốn thời gian để quét endpoint, dựng schema và áp dụng metadata. Khi nhiều client cùng mở Swagger UI ngay sau khi service vừa khởi động, request đầu tiên có thể chịu độ trễ cao hơn những request tiếp theo.

Springdoc có cơ chế cache document và tùy chọn nạp trước khi ứng dụng khởi động. Với phiên bản hỗ trợ, có thể chỉ định các locale cần nạp trước. Khi ứng dụng có nhiều GroupedOpenApi, mỗi group có endpoint document riêng; nếu cần làm nóng chắc chắn từng group và từng ngôn ngữ, hãy kiểm tra URL tương ứng sau khi service sẵn sàng. Không nên tự đặt tên property group-preload khi phiên bản đang dùng không công bố thuộc tính đó.

## 1. Vì sao cần nạp trước OpenAPI?

Quá trình sinh document có thể gồm:

1. Phát hiện controller và endpoint theo package/path filter.
2. Đọc mapping HTTP method, path, parameter, request body và response.
3. Phân tích DTO, generic type, enum, validation và schema.
4. Áp dụng @Operation, @ApiResponse, security metadata và customizer.
5. Tạo OpenAPI model, giải quyết $ref và serialize thành JSON hoặc YAML.

Với một API nhỏ, chi phí này thường không đáng kể. Với ứng dụng có nhiều controller, schema lồng nhau, nhiều group hoặc nhiều bản dịch, lần tính toán đầu tiên có thể tạo độ trễ rõ rệt.

Springdoc mặc định cache OpenAPI description sau khi tính toán. Vì vậy, request đầu tiên thường chịu phần lớn chi phí; request sau có thể lấy document đã cache. Nạp trước chuyển một phần chi phí đó sang giai đoạn khởi động hoặc giai đoạn warm-up trước khi nhận traffic người dùng.

Nạp trước không làm schema đơn giản hơn và cũng không làm mọi request nghiệp vụ nhanh hơn. Nó chủ yếu giảm độ trễ khi client lần đầu tải /v3/api-docs/{group} hoặc document theo locale.

## 2. Bật pre-loading khi phiên bản hỗ trợ

Các property chính:

| Property | Mặc định | Ý nghĩa |
| --- | --- | --- |
| springdoc.pre-loading-enabled | false | Bật việc nạp OpenAPI document khi ứng dụng khởi động. |
| springdoc.pre-loading-locales | Locale mặc định | Danh sách locale cần nạp trước; property nhận danh sách phân tách bằng dấu phẩy. Nếu bỏ trống, springdoc dùng locale mặc định. |
| springdoc.cache.disabled | false | Tắt cache document đã tính toán. |
| springdoc.cache.max-entries | 100 ở các phiên bản có hỗ trợ | Giới hạn số description được giữ trong cache theo locale. |

Ví dụ cấu hình trong application.yml:

~~~yaml
springdoc:
  pre-loading-enabled: true
  pre-loading-locales: en,vi,fr-FR
  cache:
    disabled: false
~~~

Trong ví dụ, springdoc được yêu cầu nạp document khi khởi động cho các locale en, vi và fr-FR. Nếu cần locale mặc định của JVM, hãy thêm locale đó vào danh sách; nếu bỏ trống pre-loading-locales, springdoc dùng locale mặc định theo tài liệu của phiên bản. Giữ cache được bật để các request sau có thể sử dụng kết quả đã tính toán.

pre-loading-locales được ghi nhận trong tài liệu springdoc từ nhánh v2.2.0. Hãy kiểm tra property reference của nhánh v1, v2 hoặc v3 mà ứng dụng thực sự sử dụng; không suy luận rằng một property có trong tài liệu mới nhất thì chắc chắn tồn tại trong mọi bản cũ.

Nếu không khai báo pre-loading-locales, tài liệu chính thức mô tả rằng springdoc nạp locale mặc định. Nếu ứng dụng chỉ phát hành một ngôn ngữ, không cần thêm các locale khác vào danh sách.

## 3. Locale ảnh hưởng đến document như thế nào?

Springdoc có thể giữ một OpenAPI description theo locale của request, được xác định qua header Accept-Language. Ví dụ:

~~~http
GET /v3/api-docs HTTP/1.1
Accept-Language: vi
~~~

Request khác có thể yêu cầu tiếng Anh:

~~~http
GET /v3/api-docs HTTP/1.1
Accept-Language: en
~~~

Nếu ứng dụng có metadata được bản địa hóa, hai request có thể nhận summary, description hoặc nội dung mô tả theo ngôn ngữ khác nhau. Việc nạp trước locale giúp tạo sẵn các biến thể được sử dụng thường xuyên thay vì để người dùng đầu tiên của mỗi ngôn ngữ chịu chi phí tính toán.

Header Accept-Language chỉ chọn locale cho cơ chế xử lý; nó không tự dịch mọi chuỗi Java hoặc annotation. Nếu @Operation(summary = "Create order") chứa chuỗi cố định, gửi Accept-Language: vi không tự biến nó thành tiếng Việt. Muốn có document đa ngôn ngữ, ứng dụng phải cung cấp nội dung dịch bằng cơ chế message/property localization được phiên bản springdoc hỗ trợ.

Ví dụ kiểm tra hai locale:

~~~bash
curl -fsS -H 'Accept-Language: vi' http://localhost:8080/v3/api-docs -o openapi-vi.json
curl -fsS -H 'Accept-Language: en' http://localhost:8080/v3/api-docs -o openapi-en.json
~~~

So sánh các trường info, tags, summary và description để xác nhận nội dung có thực sự thay đổi. Nếu hai file giống nhau vì metadata chưa được dịch, nạp trước nhiều locale có thể chỉ làm tăng chi phí khởi động và bộ nhớ mà không đem lại lợi ích.

## 4. Nạp trước document cho nhiều group

GroupedOpenApi chia API thành các document độc lập. Ví dụ:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiGroupConfiguration {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public-v1")
            .pathsToMatch("/api/public/**")
            .build();
    }

    @Bean
    GroupedOpenApi internalApi() {
        return GroupedOpenApi.builder()
            .group("internal-v1")
            .pathsToMatch("/api/internal/**")
            .build();
    }
}
~~~

Với base path mặc định, document được truy cập tại:

| Group | OpenAPI JSON | OpenAPI YAML |
| --- | --- | --- |
| Mặc định | /v3/api-docs | /v3/api-docs.yaml |
| public-v1 | /v3/api-docs/public-v1 | /v3/api-docs/public-v1.yaml |
| internal-v1 | /v3/api-docs/internal-v1 | /v3/api-docs/internal-v1.yaml |

Các group có thể chứa tập operation và customizer khác nhau. Nếu muốn làm nóng document của group cụ thể, cần gọi đúng URL của group đó. Đừng chỉ gọi /v3/api-docs rồi giả định mọi group đã được làm nóng.

Trong property reference hiện hành, springdoc công bố pre-loading-enabled và pre-loading-locales, nhưng không công bố một property riêng như springdoc.pre-loading-groups để chọn danh sách group. Cách cấu hình group vẫn là GroupedOpenApi hoặc springdoc.group-configs; việc warm-up group cụ thể có thể thực hiện bằng request đến endpoint của group sau khi ứng dụng sẵn sàng.

## 5. Warm-up theo từng group và locale

Một job triển khai có thể gọi từng cặp group/locale mà hệ thống thường sử dụng. Ví dụ Bash:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

: "$DOCS_BASE_URL"
BASE_URL="$DOCS_BASE_URL"

for group in public-v1 internal-v1; do
  for locale in en vi; do
    echo "Warming $group ($locale)"
    curl --fail --silent --show-error \
      -H "Accept-Language: $locale" \
      "$BASE_URL/v3/api-docs/$group" \
      -o /dev/null
  done
done
~~~

Đặt DOCS_BASE_URL không có dấu gạch chéo ở cuối. Script này gửi request đến từng URL group với Accept-Language tương ứng. Khi endpoint trả thành công, springdoc có cơ hội tạo và cache document cho request đó. Hãy chạy warm-up sau khi service đã sẵn sàng nhận request.

Nếu group internal được bảo vệ, job cần credential có quyền đọc document đó. Ví dụ bổ sung header bearer:

~~~bash
curl --fail --silent --show-error \
  -H "Authorization: Bearer $DOCS_TOKEN" \
  -H 'Accept-Language: vi' \
  "$DOCS_BASE_URL/v3/api-docs/internal-v1" \
  -o /dev/null
~~~

Token phải lấy từ secret store của pipeline; không commit vào script hoặc bật shell tracing khi token tồn tại. Nếu warm-up chạy qua gateway, dùng base URL và prefix mà runner thực sự truy cập.

Warm-up bằng HTTP là cách kiểm tra được cả routing, security, locale và nội dung document. Nó cũng giúp phát hiện group id sai hoặc endpoint chưa sẵn sàng. Nếu warm-up cần áp dụng cho tất cả replica, cần bảo đảm request chạm đến từng instance; gọi một URL load-balanced nhiều lần không bảo đảm mọi replica đều nhận được request.

## 6. Cấu hình group bằng YAML

Ngoài Java bean, có thể định nghĩa group trong cấu hình:

~~~yaml
springdoc:
  group-configs:
    - group: public-v1
      paths-to-match:
        - /api/public/**
    - group: internal-v1
      paths-to-match:
        - /api/internal/**
~~~

Khi dùng springdoc.group-configs, không cần khai báo thêm GroupedOpenApi bean cho chính các group đó. Tránh định nghĩa cùng group ở cả YAML và Java nếu không có chủ đích rõ ràng, vì cấu hình trùng có thể gây khó hiểu khi kiểm tra resource được đăng ký.

Kết hợp với pre-loading:

~~~yaml
springdoc:
  pre-loading-enabled: true
  pre-loading-locales: en,vi
  group-configs:
    - group: public-v1
      paths-to-match: /api/public/**
    - group: internal-v1
      paths-to-match: /api/internal/**
~~~

Cấu hình này bật pre-loading và đăng ký hai group. Nếu yêu cầu vận hành là phải chắc chắn cả hai group đã được tạo cho cả hai locale trước khi nhận traffic, hãy chạy bước warm-up từng URL như mục trước và kiểm tra status/content. Không dựa vào một property group-preload không có trong tài liệu phiên bản.

## 7. Giới hạn số locale được giữ trong cache

Mỗi locale được request có thể tạo một OpenAPI description riêng trong cache. Ứng dụng hỗ trợ nhiều ngôn ngữ, nhiều group hoặc có header Accept-Language đa dạng cần tính đến bộ nhớ dùng cho các document.

Từ springdoc v2.9.1, springdoc.cache.max-entries giới hạn số description được giữ trong cache; tài liệu v2 ghi mặc định là 100. Ở nhánh v3, giới hạn cache được bổ sung từ v3.1.1, cũng với mặc định 100.

Ví dụ với phiên bản hỗ trợ:

~~~yaml
springdoc:
  cache:
    disabled: false
    max-entries: 32
~~~

Khi vượt quá giới hạn, entry cũ nhất/ít được dùng gần đây sẽ bị loại bỏ theo chính sách cache của phiên bản. Request tiếp theo cho locale đã bị loại bỏ có thể phải tính toán lại document.

Chọn max-entries dựa trên số locale thực sự được sử dụng và kích thước document. Đặt giới hạn quá thấp có thể làm cache liên tục bị eviction; đặt quá cao có thể giữ nhiều document lớn trong heap. Đừng mặc định rằng 100 entry luôn phù hợp với mọi ứng dụng.

Ở phiên bản chưa có giới hạn cache, tránh để endpoint docs công khai chấp nhận số lượng Accept-Language tùy ý. Nên nâng cấp lên bản đã giới hạn cache, đồng thời giới hạn locale được chấp nhận ở lớp ứng dụng/gateway theo khả năng của stack. Danh sách pre-loading-locales chỉ nói locale cần nạp trước; không nên coi nó là allowlist bảo mật cho mọi request đến.

## 8. Khi nào nên tắt cache?

Property:

~~~yaml
springdoc:
  cache:
    disabled: true
~~~

Tắt cache có thể hữu ích trong một số trường hợp đặc biệt, ví dụ server URL phải được tính lại theo từng request vì ứng dụng phục vụ qua nhiều proxy hoặc host công khai khác nhau. FAQ của springdoc nêu đây là một lý do để tắt cache.

Tuy nhiên, nếu mục tiêu là giảm cold latency bằng pre-loading, tắt cache thường đi ngược mục tiêu: document có thể phải được tính lại cho request tiếp theo. Chỉ tắt cache khi có yêu cầu động cụ thể và đã đo được trade-off.

Không dùng cache.disabled=true như cách refresh document sau khi thay đổi annotation hoặc controller trong production. Phần lớn thay đổi code/cấu hình cần triển khai lại hoặc cơ chế refresh được hỗ trợ; tắt cache không thay thế quy trình deploy.

## 9. Cân bằng thời gian khởi động, độ trễ và bộ nhớ

Nạp trước là chuyển chi phí tính toán từ thời điểm có request sang giai đoạn khởi động hoặc warm-up. Nó không làm biến mất chi phí đó.

| Chiến lược | Thời gian khởi động | Request đầu tiên | Bộ nhớ/cache |
| --- | --- | --- | --- |
| Không pre-load, cache bật | Thường thấp hơn | Có thể chậm do phải tạo document | Tăng khi từng locale/group được request. |
| Pre-load locale mặc định | Có thêm chi phí lúc khởi động | Locale mặc định có thể sẵn sàng sớm hơn | Giữ document mặc định trong cache. |
| Pre-load nhiều locale | Tăng theo số biến thể được tạo | Giảm cold hit cho locale đã nạp | Có thể giữ nhiều description hơn. |
| Warm-up từng group/locale | Thêm thời gian ở bước warm-up sau readiness | Các cặp đã warm có thể tránh cold hit | Tăng theo số document thực sự được cache. |
| Tắt cache | Ít chi phí warm-up có ích | Mỗi request có thể phải tính lại | Giảm cache nhưng tăng CPU/latency khi tải docs. |

Không cần nạp mọi locale và mọi group nếu phần lớn không có người dùng. Chọn những biến thể có traffic thực tế, chẳng hạn public-v1 bằng tiếng Việt và tiếng Anh. Group quản trị ít được truy cập có thể để sinh document khi cần.

Đo riêng:

- Thời gian khởi động đến trạng thái readiness.
- Thời gian request OpenAPI đầu tiên sau readiness.
- Thời gian request thứ hai cùng group/locale.
- Thời gian request khi đổi locale.
- Heap sau khi warm-up các biến thể dự kiến.

Đặt ngưỡng theo số liệu của ứng dụng thay vì bật tất cả tùy chọn mặc định cho mọi môi trường.

## 10. Kiểm tra locale và group bằng HTTP

Có thể đo thời gian tải document bằng curl:

~~~bash
curl -sS -o /dev/null \
  -H 'Accept-Language: vi' \
  -w 'status=%{http_code} total=%{time_total}s\n' \
  http://localhost:8080/v3/api-docs/public-v1
~~~

Chạy lặp lại cùng URL để so sánh cold request và cached request. Sau đó đổi Accept-Language:

~~~bash
curl -sS -o /dev/null \
  -H 'Accept-Language: en' \
  -w 'status=%{http_code} total=%{time_total}s\n' \
  http://localhost:8080/v3/api-docs/public-v1
~~~

Và đổi group:

~~~bash
curl -sS -o /dev/null \
  -H 'Accept-Language: vi' \
  -w 'status=%{http_code} total=%{time_total}s\n' \
  http://localhost:8080/v3/api-docs/internal-v1
~~~

Để kiểm tra nội dung thay vì chỉ đo thời gian, lưu JSON của từng cặp group/locale rồi so sánh các path và text đã dịch. Xác nhận response là OpenAPI document hợp lệ, không phải trang login hoặc lỗi từ gateway.

Nếu có nhiều replica, thực hiện kiểm tra ở từng instance hoặc dùng telemetry để biết instance nào đã nhận warm-up. Một lần gọi qua load balancer không chứng minh mọi replica đều có cache nóng.

## 11. Lưu ý khi chạy sau reverse proxy hoặc cache HTTP

OpenAPI document theo locale có thể khác nhau dù URL giống nhau. Nếu reverse proxy, CDN hoặc HTTP cache lưu response, cần bảo đảm cache ngoài phân biệt request theo Accept-Language khi nội dung thực sự phụ thuộc header này. Nếu không, client tiếng Việt có thể nhận document tiếng Anh đã được proxy cache trước đó.

Đồng thời, nếu server URL được suy ra từ forwarded headers và ứng dụng phục vụ cùng document qua nhiều host, cache nội bộ có thể giữ server URL từ request đầu tiên. FAQ springdoc nêu trường hợp này là lý do có thể cần springdoc.cache.disabled=true. Trước khi tắt cache, hãy cân nhắc cấu hình servers tường minh hoặc chuẩn hóa forwarded headers tại proxy để tránh tạo document khác nhau theo host không cần thiết.

Không để header Accept-Language hoặc forwarded host do client tùy ý gửi tạo vô số biến thể không kiểm soát. Giới hạn locale và chỉ tin forwarded headers từ proxy đáng tin cậy.

## 12. Kiểm thử cấu hình pre-loading

Có thể xác nhận các property được bind trong Spring Boot test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class OpenApiPreloadingConfigurationTest {

    @Autowired
    Environment environment;

    @Test
    void enablesPreloadingForConfiguredLocales() {
        assertThat(environment.getProperty(
            "springdoc.pre-loading-enabled", Boolean.class
        )).isTrue();

        assertThat(environment.getProperty("springdoc.pre-loading-locales"))
            .contains("en")
            .contains("vi");
    }
}
~~~

Test này xác nhận cấu hình property được nạp. Nó chưa chứng minh document đã được tạo trước request đầu tiên. Để xác minh hành vi, hãy chạy integration test hoặc smoke test sau startup, gọi đúng group/locale, so sánh nội dung và đo thời gian request.

Nếu dùng springdoc.group-configs, có thể kiểm tra URL từng group trong test:

Method dưới đây là phần bổ sung cho test class có sẵn MockMvc và các static import tương ứng.

~~~java
@Test
void publicGroupDocumentIsAvailable() throws Exception {
    mockMvc.perform(get("/v3/api-docs/public-v1")
            .header("Accept-Language", "vi"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.openapi").exists())
        .andExpect(jsonPath("$.paths['/api/public/catalog']").exists());
}
~~~

Test này chứng minh endpoint group trả document phù hợp trong test context. Nó không tự chứng minh preloading đã xảy ra ở startup; để kiểm tra preloading, so sánh thời điểm request đầu và log/metric khởi động trên phiên bản đang dùng.

## 13. Lưu ý với GraalVM Native Image

Springdoc hỗ trợ native image trong hệ sinh thái Spring Boot 3 trở lên, nhưng cần kiểm tra ứng dụng đã biên dịch native thực tế. Pre-loading là thao tác runtime lúc ứng dụng khởi động; nó không có nghĩa OpenAPI đã được tạo ở build time.

Nếu dùng @OpenAPIDefinition hoặc @SecurityScheme trên một class chỉ chứa annotation, FAQ springdoc lưu ý class đó có thể bị loại khi native compile. Đặt annotation trên class cấu hình Spring, ví dụ:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    info = @Info(title = "Store API", version = "1.0.0")
)
class OpenApiNativeConfiguration {
}
~~~

Sau khi build native image, kiểm tra:

- Ứng dụng khởi động và hoàn tất pre-loading.
- Từng group URL trả OpenAPI document.
- Các locale được cấu hình vẫn tạo document đúng.
- Schema, annotation và customizer xuất hiện như bản JVM.
- Thời gian khởi động và request docs đạt mục tiêu thực tế.

Không chỉ kiểm tra JVM rồi suy luận native image có cùng hành vi. Test native executable trong pipeline hoặc môi trường staging nếu native image là artifact được triển khai.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Property pre-loading không có tác dụng | Phiên bản springdoc chưa hỗ trợ hoặc tên property sai | Kiểm tra core properties của đúng nhánh và phiên bản. |
| Locale thứ hai vẫn trả nội dung ngôn ngữ mặc định | Annotation/description chưa có bản dịch hoặc locale không được nhận diện | Kiểm tra Accept-Language, locale tag và cơ chế i18n của ứng dụng. |
| Chỉ group mặc định được warm-up | Job chỉ gọi /v3/api-docs | Gọi URL /v3/api-docs/{group} cho từng group cần dùng. |
| Group warm-up trả 404 | Group id sai, group không được đăng ký hoặc base path tùy chỉnh | Kiểm tra GroupedOpenApi, springdoc.group-configs và springdoc.api-docs.path. |
| Warm-up nội bộ nhận 401/403 | Endpoint group được bảo vệ | Cấp credential phù hợp cho job; không mở public group nội bộ chỉ để warm-up. |
| Khởi động chậm sau khi bật nhiều locale | Mỗi locale làm phát sinh công việc tạo document | Chỉ pre-load locale có traffic; đo lại thời gian readiness. |
| Heap tăng sau warm-up | Nhiều group/locale tạo nhiều cache entry hoặc document lớn | Giảm số locale, điều chỉnh cache.max-entries nếu phiên bản hỗ trợ. |
| Locale bị tính lại liên tục | Cache entry bị eviction hoặc cache bị tắt | Kiểm tra springdoc.cache.disabled, cache.max-entries và traffic locale. |
| Pre-loading bật nhưng request nào cũng chậm | Cache bị tắt, request đi qua instance khác hoặc document vẫn được tạo lại | Kiểm tra cấu hình cache, load balancing và telemetry từng replica. |
| JVM chạy được nhưng native image thiếu metadata | Annotation class bị loại hoặc native behavior khác | Đặt annotation trên @Configuration và test native executable. |
| Proxy trả nhầm ngôn ngữ | Cache HTTP ngoài không phân biệt Accept-Language | Cấu hình cache theo header hoặc không cache response đa ngôn ngữ ở proxy. |
| Tắt cache làm CPU tăng | Document bị tính lại cho từng request | Chỉ tắt khi cần server URL động; nếu không, giữ cache và warm-up. |

## 15. Nguyên tắc áp dụng

- Bật springdoc.pre-loading-enabled khi muốn chuyển chi phí tạo OpenAPI sang lúc khởi động.
- Dùng springdoc.pre-loading-locales cho các locale thực sự được sử dụng và được phiên bản hỗ trợ.
- Nhớ rằng pre-loading không tự dịch annotation hoặc nội dung mô tả.
- Dùng Accept-Language để kiểm tra document theo locale.
- Với nhiều group, gọi URL của từng group; property reference hiện hành không có property chọn danh sách group-preload riêng.
- Chạy warm-up sau readiness nếu cần bảo đảm từng cặp group/locale đã được tạo.
- Giữ cache bật khi mục tiêu là giảm độ trễ request đầu; chỉ tắt khi cần tính server URL động hoặc hành vi tương tự.
- Giới hạn số cache entry bằng springdoc.cache.max-entries từ v2.9.1 hoặc v3.1.1 trở lên.
- Chọn số locale/group dựa trên traffic và ngân sách heap.
- Bảo đảm HTTP cache bên ngoài xử lý Accept-Language đúng khi nội dung phụ thuộc locale.
- Kiểm thử cả JVM và native image nếu triển khai GraalVM.

Nạp trước giúp giảm cold latency khi client tải OpenAPI, nhưng cần chọn đúng biến thể tài liệu sẽ được sử dụng. springdoc.pre-loading-enabled và springdoc.pre-loading-locales hỗ trợ nạp trước khi khởi động theo khả năng của phiên bản; cache lưu description theo locale và các group có endpoint riêng. Khi cần bảo đảm một group/ngôn ngữ cụ thể đã sẵn sàng, hãy warm-up URL tương ứng sau readiness, kiểm tra nội dung và đo cả startup time, request latency lẫn bộ nhớ.

## Tài liệu tham khảo

- [Springdoc OpenAPI FAQ – cache và locale](https://springdoc.org/faq.html)
- [Springdoc OpenAPI v2 – Core Properties](https://springdoc.org/v2/core-properties.html)
- [Springdoc OpenAPI – Core Properties](https://springdoc.org/core-properties.html)
- [Springdoc OpenAPI v2.2.0 release notes – locale pre-loading](https://github.com/springdoc/springdoc-openapi/releases/tag/v2.2.0)
- [Springdoc OpenAPI v2.9.1 release notes – bounded locale cache](https://github.com/springdoc/springdoc-openapi/releases/tag/v2.9.1)
- [Springdoc OpenAPI v3.1.1 release notes – bounded locale cache](https://github.com/springdoc/springdoc-openapi/releases/tag/v3.1.1)
