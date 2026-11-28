# Kiểm thử API Config Server bằng dữ liệu cấu hình đã biết

## 1. Mục tiêu của kiểm thử API Config Server

Config Server cung cấp cấu hình theo tên ứng dụng, profile và label. Một response HTTP `200 OK` chỉ chứng minh request đã nhận được response thành công ở tầng HTTP. Nó chưa chứng minh server trả đúng repository, đúng revision, đúng property source hoặc đúng giá trị mà ứng dụng cần.

Kiểm thử API với dữ liệu cấu hình đã biết giúp xác nhận hợp đồng giữa Config Client và Config Server:

- Đúng application name, profile và label.
- Đúng revision của Git repository.
- Có đủ property source dùng chung và property source riêng của ứng dụng.
- Thứ tự property source phản ánh đúng quy tắc ưu tiên.
- Giá trị cuối cùng của các khóa kiểm thử khớp fixture đã chuẩn bị.
- API trả đúng định dạng và bảo vệ quyền truy cập.
- Các trường hợp cấu hình thiếu, label sai hoặc backend lỗi được xử lý theo hợp đồng của phiên bản đang chạy.

Kiểm thử này đặc biệt hữu ích trong CI trước khi phát hành thay đổi repository cấu hình. Thay vì chỉ kiểm tra YAML có parse được, pipeline gọi Config Server với một fixture đã biết và so sánh response với kết quả mong đợi.

## 2. Phân biệt API test với client integration test

Config Server API test và Config Client integration test kiểm tra hai ranh giới khác nhau:

| Loại kiểm thử | Thành phần được kiểm tra | Điều có thể kết luận |
|---|---|---|
| Config Server API/contract test | HTTP endpoint của Config Server và Environment response. | Server trả đúng application/profile/label, revision, property sources và dữ liệu. |
| Config Client integration test | Ứng dụng Spring Boot có Config Client. | Client nạp property sources, bind `@ConfigurationProperties` và áp dụng các nguồn ghi đè local/remote đúng thứ tự. |
| Refresh test | Client đang chạy và cơ chế refresh. | Client lấy lại cấu hình và bean hỗ trợ refresh nhận giá trị mới. |

API test không chứng minh bean trong client đã bind thành công, không chứng minh biến môi trường hoặc command-line argument không ghi đè remote property, và không chứng minh `@RefreshScope` đã tạo target mới. Các điều đó cần được kiểm tra ở tầng client riêng.

## 3. Chuẩn bị fixture Git có dữ liệu xác định

Một test đáng tin cậy cần biết chính xác nội dung cấu hình và revision mà Config Server sẽ đọc. Nên dùng repository test riêng, branch/tag dành cho kiểm thử và dữ liệu không chứa secret thật.

Ví dụ cấu trúc repository:

```text
config-repo-test/
├── application.yml
├── application-qa.yml
├── catalog-service.yml
└── catalog-service-qa.yml
```

Nội dung `application.yml` cung cấp giá trị chung:

```yaml
platform.region: ap-southeast-1
feature.audit-enabled: false
catalog.max-page-size: 100
catalog.source: shared-default
```

`application-qa.yml` ghi đè một giá trị chung theo profile:

```yaml
feature.audit-enabled: true
```

`catalog-service.yml` cung cấp cấu hình riêng cho ứng dụng:

```yaml
catalog.max-page-size: 80
catalog.source: catalog-default
```

`catalog-service-qa.yml` ghi đè cấu hình riêng theo profile:

```yaml
catalog.max-page-size: 40
catalog.source: catalog-qa
```

Với request cho `catalog-service`, profile `qa`, kết quả mong đợi theo các property source của Config Server:

| Property | Giá trị hiệu lực dự kiến | Nguồn ưu tiên cao nhất có khóa |
|---|---:|---|
| `platform.region` | `ap-southeast-1` | `application.yml` |
| `feature.audit-enabled` | `true` | `application-qa.yml` |
| `catalog.max-page-size` | `40` | `catalog-service-qa.yml` |
| `catalog.source` | `catalog-qa` | `catalog-service-qa.yml` |

Các giá trị `80` và `100` vẫn có thể xuất hiện trong các property source có độ ưu tiên thấp hơn. Test cần xác nhận giá trị hiệu lực theo thứ tự property source, không chỉ kiểm tra rằng một giá trị mong đợi xuất hiện ở đâu đó trong response.

## 4. Cố định label và revision để test lặp lại được

Không nên dùng một branch đang được developer cập nhật liên tục làm fixture duy nhất. Nếu nội dung branch đổi giữa hai lần chạy, test có thể thất bại dù code kiểm thử không thay đổi.

Quy trình tạo fixture:

1. Commit các file cấu hình test vào repository riêng.
2. Tạo tag bất biến, ví dụ `config-fixture-2026-11`.
3. Lấy commit SHA mà tag trỏ tới.
4. Cấu hình Config Server trỏ đến repository test và cho phép request dùng tag đó làm label.
5. Gọi API với label tường minh trong mọi test.
6. So sánh trường `version` trong response với commit SHA đã ghi nhận.

Lấy SHA của tag:

```bash
git rev-parse 'config-fixture-2026-11^{commit}'
```

Không giả định `main`, `master` hoặc `HEAD` là fixture ổn định. Nếu phải test branch động, pipeline cần lấy expected SHA tại cùng thời điểm và ghi rõ revision được kiểm thử trong report.

## 5. Endpoint chính cần kiểm thử

Endpoint Environment phổ biến có dạng:

```text
GET /{application}/{profile}/{label}
```

Ví dụ:

```text
GET https://config-test.internal/catalog-service/qa/config-fixture-2026-11
```

Các thành phần:

- `application`: tên ứng dụng, thường tương ứng `spring.application.name`.
- `profile`: một hoặc nhiều profile mà client yêu cầu.
- `label`: branch, tag hoặc commit được chọn trong repository backend.

Response JSON thường chứa metadata và danh sách property source:

```json
{
  "name": "catalog-service",
  "profiles": ["qa"],
  "label": "config-fixture-2026-11",
  "version": "EXPECTED_COMMIT_SHA",
  "propertySources": [
    {
      "name": ".../catalog-service-qa.yml",
      "source": {
        "catalog.max-page-size": 40,
        "catalog.source": "catalog-qa"
      }
    },
    {
      "name": ".../catalog-service.yml",
      "source": {
        "catalog.max-page-size": 80,
        "catalog.source": "catalog-default"
      }
    }
  ]
}
```

Đây là response rút gọn để minh họa cấu trúc; số lượng, tên và thứ tự property source thực tế phụ thuộc backend, profile, search path và phiên bản Spring Cloud Config. Không hardcode toàn bộ tên đường dẫn source nếu chúng chứa thư mục clone tạm hoặc thông tin môi trường thay đổi.

## 6. Kiểm tra nhanh bằng curl và jq

Gọi endpoint và yêu cầu JSON:

```bash
curl --fail-with-body \
  --header "Accept: application/json" \
  "https://config-test.internal/catalog-service/qa/config-fixture-2026-11"
```

Nếu Config Server yêu cầu Bearer token:

```bash
curl --fail-with-body \
  --header "Accept: application/json" \
  --header "Authorization: Bearer ${CONFIG_TEST_TOKEN}" \
  "https://config-test.internal/catalog-service/qa/config-fixture-2026-11"
```

Không đặt token thật trực tiếp trong command text hoặc URL. Cấp token qua secret store/CI secret và bảo đảm shell trace, process log, CI output không in giá trị đó.

Kiểm tra metadata:

```bash
curl --silent --show-error \
  --header "Accept: application/json" \
  "${CONFIG_SERVER_URL}/catalog-service/qa/config-fixture-2026-11" \
  | jq '{name, profiles, label, version}'
```

Kiểm tra các giá trị trong property sources:

```bash
curl --silent --show-error \
  --header "Accept: application/json" \
  "${CONFIG_SERVER_URL}/catalog-service/qa/config-fixture-2026-11" \
  | jq '[.propertySources[] | .source]'
```

Lệnh thứ hai hiển thị các source phục vụ debug. Trong pipeline production, nên lọc đúng các khóa không nhạy cảm thay vì in toàn bộ response; Config Server có thể trả property chứa thông tin nội bộ hoặc secret đã được giải mã.

## 7. Xác định giá trị hiệu lực từ propertySources

Config Server trả danh sách `propertySources` theo thứ tự ưu tiên: source đứng trước có độ ưu tiên cao hơn source đứng sau. Khi nhiều source cùng chứa một khóa, source đầu tiên chứa khóa đó quyết định giá trị trong Environment của Config Server.

Với fixture trên:

- `catalog-service-qa.yml` ghi đè `catalog-service.yml`.
- File riêng của ứng dụng ghi đè file dùng chung `application-qa.yml` hoặc `application.yml` khi có khóa trùng.
- `application-qa.yml` ghi đè giá trị chung trong `application.yml`.

Để kiểm thử tổng quát, hãy viết helper tìm lần xuất hiện đầu tiên của khóa trong danh sách source:

```java
static Object effectiveValue(
        List<Map<String, Object>> sources,
        String propertyName) {

    for (Map<String, Object> source : sources) {
        if (source.containsKey(propertyName)) {
            return source.get(propertyName);
        }
    }

    throw new AssertionError(
            "Property not found in Config Server response: " + propertyName);
}
```

Helper này dùng để kiểm tra thứ tự property source do Config Server trả về. Nó không mô phỏng toàn bộ Spring Boot `Environment` của client, nơi còn có thể có system properties, environment variables, command-line arguments, local config data và các property source khác.

## 8. Viết API contract test bằng JUnit và REST Assured

REST Assured giúp gửi HTTP request và kiểm tra JSON response trong JUnit. Test nên nhận URL Config Server, token test và expected commit SHA từ cấu hình môi trường CI.

Ví dụ test:

```java
import io.restassured.http.ContentType;
import io.restassured.response.Response;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static io.restassured.RestAssured.given;
import static org.junit.jupiter.api.Assertions.*;

class ConfigServerApiTest {

    private final String baseUrl = System.getenv("CONFIG_SERVER_URL");
    private final String expectedVersion = System.getenv("EXPECTED_CONFIG_SHA");

    @Test
    void returnsExpectedEnvironmentForKnownApplicationProfileAndLabel() {
        Response response = given()
                .baseUri(baseUrl)
                .accept(ContentType.JSON)
            .when()
                .get("/catalog-service/qa/config-fixture-2026-11")
            .then()
                .statusCode(200)
                .extract()
                .response();

        assertEquals("catalog-service", response.jsonPath().getString("name"));
        assertTrue(response.jsonPath().getList("profiles", String.class).contains("qa"));
        assertEquals("config-fixture-2026-11",
                response.jsonPath().getString("label"));
        assertEquals(expectedVersion, response.jsonPath().getString("version"));

        List<Map<String, Object>> sources =
                response.jsonPath().getList("propertySources.source");

        assertEquals("ap-southeast-1",
                effectiveValue(sources, "platform.region"));
        assertEquals(true,
                effectiveValue(sources, "feature.audit-enabled"));
        assertEquals(40,
                ((Number) effectiveValue(sources, "catalog.max-page-size")).intValue());
        assertEquals("catalog-qa",
                effectiveValue(sources, "catalog.source"));
    }

    private static Object effectiveValue(
            List<Map<String, Object>> sources,
            String propertyName) {
        for (Map<String, Object> source : sources) {
            if (source.containsKey(propertyName)) {
                return source.get(propertyName);
            }
        }
        throw new AssertionError("Missing property: " + propertyName);
    }
}
```

Ví dụ giả định fixture YAML được nạp thành các key dạng dotted property và JSON parser trả `feature.audit-enabled` dưới dạng Boolean. Nếu backend hoặc phiên bản đang dùng biểu diễn dữ liệu khác, điều chỉnh assertion theo response thực tế thay vì ép kiểu không an toàn.

Trong dự án thực tế, kiểm tra `baseUrl` và `expectedVersion` không rỗng trước khi chạy test. Có thể truyền Bearer token qua request filter của REST Assured; không hardcode token vào source code.

## 9. Kiểm tra thứ tự ưu tiên, không chỉ sự tồn tại của giá trị

Một assertion kiểu `contains("catalog.max-page-size", 40)` chưa đủ nếu source ưu tiên thấp hơn hoặc cao hơn cũng có khóa đó. Cần kiểm tra giá trị hiệu lực bằng source đầu tiên có property, đồng thời có thể xác nhận các giá trị ở source thấp hơn vẫn hiện diện như dự kiến.

Ví dụ kiểm tra thứ tự hai source có khóa trùng:

```java
int appQaIndex = indexOfSourceContaining(sources, "catalog.max-page-size", 40);
int appDefaultIndex = indexOfSourceContaining(sources, "catalog.max-page-size", 80);

assertTrue(appQaIndex >= 0, "QA application source must be present");
assertTrue(appDefaultIndex > appQaIndex,
        "QA-specific source must have higher precedence than application default");
```

Helper minh họa:

```java
static int indexOfSourceContaining(
        List<Map<String, Object>> sources,
        String key,
        Object expectedValue) {
    for (int i = 0; i < sources.size(); i++) {
        if (expectedValue.equals(sources.get(i).get(key))) {
            return i;
        }
    }
    return -1;
}
```

Nếu nhiều source chứa cùng một giá trị, hãy xác định source bằng metadata `name` phù hợp với fixture hoặc dùng một giá trị marker riêng cho từng file. Không gắn test vào đường dẫn clone tạm của Config Server nếu đường dẫn đó thay đổi theo môi trường.

## 10. Kiểm tra application, profile và label riêng biệt

Mỗi thành phần của endpoint có thể gây ra lỗi cấu hình khác nhau. Tạo các test riêng để biết chính xác lỗi nằm ở đâu.

| Test case | Request mẫu | Assertion chính |
|---|---|---|
| Đúng application/profile/label | `/catalog-service/qa/config-fixture-2026-11` | Metadata và giá trị khớp fixture. |
| Application khác | `/billing-service/qa/config-fixture-2026-11` | Không nhận nhầm property riêng của `catalog-service`. |
| Profile khác | `/catalog-service/dev/config-fixture-2026-11` | Chỉ các property source phù hợp profile `dev` được đưa vào. |
| Label khác | `/catalog-service/qa/release-previous` | Response phản ánh revision của label cũ đã biết. |
| Default label | `/catalog-service/qa` | Server dùng default label đã cấu hình; test ghi rõ giá trị mong đợi. |
| Nhiều profile | `/catalog-service/qa,metrics/config-fixture-2026-11` | Metadata và thứ tự source phù hợp danh sách profile theo hợp đồng phiên bản. |

Đối với profile nhiều giá trị, thứ tự profile có thể ảnh hưởng kết quả. Dùng fixture có khóa trùng giữa hai profile để chứng minh profile nào có ưu tiên cao hơn theo phiên bản Spring Cloud Config đang triển khai.

Label chứa dấu `/` hoặc ký tự đặc biệt cần được URL-encode theo quy tắc của HTTP client và endpoint. Không nối chuỗi URL thủ công nếu label đến từ input bên ngoài.

## 11. Kiểm tra content type và định dạng response

Config Server có thể phục vụ Environment dưới dạng JSON và các endpoint định dạng như YAML hoặc properties. API contract test nên xác nhận đúng media type mà consumer sử dụng.

Ví dụ với JSON:

```bash
curl --silent --show-error --include \
  --header "Accept: application/json" \
  "${CONFIG_SERVER_URL}/catalog-service/qa/config-fixture-2026-11"
```

Kiểm tra:

- HTTP status đúng theo hợp đồng.
- `Content-Type` là JSON tương thích với client.
- Body parse được thành Environment response.
- Các field metadata và property source có mặt.

Nếu client dùng endpoint YAML/properties thay vì Environment JSON, cần test riêng định dạng tương ứng và parse body bằng parser thực tế mà client sử dụng. Không chỉ kiểm tra response có chứa chuỗi `catalog.max-page-size`; một response HTML từ reverse proxy hoặc trang lỗi cũng có thể chứa chuỗi tương tự.

## 12. Kiểm thử lỗi và response không hợp lệ

Test âm giúp phát hiện server trả cấu hình sai hoặc che giấu lỗi backend. Nên bao gồm:

| Trường hợp | Điều cần kiểm tra |
|---|---|
| Application không tồn tại | Status và body theo hợp đồng phiên bản; không trả nhầm cấu hình của application khác. |
| Profile không có file riêng | Cấu hình chung vẫn được trả theo quy tắc, hoặc phản hồi lỗi đúng khi nguồn bắt buộc thiếu. |
| Label không tồn tại | Server không âm thầm trả revision khác ngoài chính sách fallback đã định nghĩa. |
| Git repository unavailable | Timeout/error được quan sát; không trả fixture cũ ngoài ý muốn nếu chính sách không cho phép stale data. |
| Git authentication thất bại | Server báo lỗi backend; không trả thông tin credential trong response/log. |
| YAML sai cú pháp | Pipeline/test phát hiện lỗi parse trước khi phát hành cấu hình. |
| Property bị thiếu | Test phát hiện thiếu key bắt buộc thay vì chỉ xác nhận HTTP 200. |
| Property source trùng khóa | Test xác nhận source có độ ưu tiên cao nhất thắng. |

Status code cụ thể cho application/profile/label không tồn tại hoặc backend failure có thể khác theo endpoint, backend và phiên bản. Trước khi cố định assertion, hãy ghi nhận response thực tế của phiên bản đang triển khai và coi đó là API contract có chủ ý.

## 13. Kiểm thử bảo mật API

Nếu Config Server yêu cầu authentication, cần test cả request hợp lệ và không hợp lệ:

1. Không có credential: request bị từ chối theo policy.
2. Token sai/hết hạn: request không được trả cấu hình.
3. Token hợp lệ nhưng thiếu quyền application: chỉ được phép/không được phép đúng theo authorization policy.
4. Token đúng scope: chỉ đọc được application/profile/label được cấp.
5. Request qua HTTPS: certificate chain và hostname được xác minh.
6. Response/log: không làm lộ token, plaintext secret hoặc private key ngoài phạm vi cho phép.

Ví dụ kiểm tra request không có token:

```java
given()
    .baseUri(baseUrl)
    .accept(ContentType.JSON)
.when()
    .get("/catalog-service/qa/config-fixture-2026-11")
.then()
    .statusCode(401);
```

Ví dụ này giả định endpoint dùng HTTP Basic/Bearer authentication được cấu hình để trả `401` khi thiếu danh tính. Nếu security filter trả `403` hoặc gateway có response riêng, hãy kiểm thử theo policy thực tế. Điều quan trọng là request không được nhận property source được bảo vệ.

Không sử dụng secret production trong fixture. Test bảo mật chỉ nên dùng credential ngắn hạn, scope hẹp và dữ liệu giả lập.

## 14. Kiểm tra endpoint bằng script shell có assertion

Một script CI có thể gọi endpoint, lưu response vào file tạm và xác nhận metadata/value bằng `jq`:

```bash
#!/usr/bin/env bash
set -euo pipefail

url="${CONFIG_SERVER_URL}/catalog-service/qa/config-fixture-2026-11"
response_file="$(mktemp)"
trap 'rm -f "$response_file"' EXIT

status="$(curl --silent --show-error \
  --output "$response_file" \
  --write-out '%{http_code}' \
  --header "Accept: application/json" \
  "$url")"

test "$status" = "200"
jq -e '.name == "catalog-service"' "$response_file" >/dev/null
jq -e '.profiles | index("qa") != null' "$response_file" >/dev/null
jq -e '.label == "config-fixture-2026-11"' "$response_file" >/dev/null
jq -e '[.propertySources[].source["catalog.max-page-size"]] | any(. == 40)' \
  "$response_file" >/dev/null
```

Assertion cuối chỉ chứng minh giá trị `40` xuất hiện trong một source. Để chứng minh giá trị hiệu lực, cần kiểm tra thứ tự source hoặc dùng test Java ở phần trước để tìm source đầu tiên có khóa. Khi fixture được thay đổi, cập nhật expected value và commit SHA cùng thay đổi đó.

Nếu response có thể chứa secret đã giải mã, không upload response làm CI artifact công khai và không in body khi test thất bại. Có thể lưu file tạm với quyền hạn chế và chỉ báo tên assertion thất bại.

## 15. Test client binding sau khi API contract đã đạt

Sau khi API test xác nhận Config Server trả đúng Environment, hãy kiểm tra một ứng dụng Config Client thực tế.

Ví dụ client properties:

```java
@ConfigurationProperties(prefix = "catalog")
public record CatalogProperties(int maxPageSize, String source) {
}
```

Integration test của client nên xác nhận:

- `spring.application.name` đúng với application mà API test đã gọi.
- Active profile và label đúng fixture.
- Config Client kết nối đúng Config Server test.
- `CatalogProperties.maxPageSize()` bằng `40`.
- `CatalogProperties.source()` bằng `catalog-qa`.
- Các local/environment/command-line property source không ghi đè fixture ngoài dự kiến.
- Validation thất bại nếu property bắt buộc thiếu hoặc sai kiểu.

Đây là test ở phía client. Không nên cố kết luận binding thành công chỉ từ response JSON của Config Server.

## 16. Tổ chức test trong CI/CD

Một pipeline cấu hình có thể chia thành các bước:

1. **Static validation**: parse YAML/Properties, kiểm tra schema và quy tắc tên file.
2. **Fixture validation**: xác nhận branch/tag fixture và commit SHA mong đợi.
3. **Config Server API test**: gọi endpoint theo application/profile/label, kiểm tra metadata, property sources và effective values.
4. **Negative/security test**: kiểm tra label sai, application sai, token thiếu quyền và response không hợp lệ.
5. **Client integration test**: khởi chạy client thử nghiệm với Config Server fixture và kiểm tra binding.
6. **Promotion gate**: chỉ cho phép phát hành repository cấu hình khi các assertion bắt buộc đạt.
7. **Post-deploy smoke test**: sau khi phát hành, gọi endpoint của môi trường đích và so sánh revision/label với release record.

Giữ fixture test tách biệt với production config repository nếu có thể. Nếu dùng cùng repository, dùng tag bất biến, không chứa secret thật và phân quyền để pipeline chỉ đọc.

## 17. Những lỗi kiểm thử thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Test pass dù giá trị ưu tiên sai | Chỉ kiểm tra một giá trị xuất hiện trong bất kỳ source nào. | Tìm source đầu tiên chứa khóa và assert effective value. |
| Test thay đổi kết quả giữa các lần chạy | Dùng branch/tag mutable hoặc repository fixture bị cập nhật. | Ghim immutable tag và expected commit SHA. |
| Test đọc nhầm profile | Active profile hoặc URL path không đúng. | Assert `profiles` trong response và dùng URL tường minh. |
| Test nhận source chung nhưng thiếu source riêng | Sai application name hoặc file naming. | Kiểm tra `spring.application.name` và tên file theo convention. |
| API trả 200 nhưng body không phải JSON | Reverse proxy/login page/error handler trả HTML. | Assert Content-Type và parse body trước khi kiểm tra field. |
| `version` không khớp | Label trỏ đến commit khác hoặc server clone/cache chưa cập nhật. | Xác minh tag SHA, backend refresh và response metadata. |
| Test security pass sai | Assertion status code không khớp gateway/security chain. | Kiểm tra body không chứa property được bảo vệ và dùng status contract của môi trường. |
| CI log lộ secret | Test in toàn bộ response hoặc request headers. | Lọc output, dùng fixture giả và che credential. |
| API test pass nhưng client bind sai | Local property source hoặc kiểu dữ liệu khác ghi đè. | Bổ sung Config Client integration test. |

## 18. Checklist kiểm thử API Config Server

- [ ] Fixture chứa dữ liệu xác định, không có secret production.
- [ ] Repository/branch/tag được cố định và có expected commit SHA.
- [ ] Test gọi đúng application, profile và label.
- [ ] Response metadata `name`, `profiles`, `label` và `version` được kiểm tra.
- [ ] `propertySources` có các source chung và source riêng dự kiến.
- [ ] Effective value được tính theo thứ tự ưu tiên, không chỉ kiểm tra sự tồn tại.
- [ ] Content-Type và định dạng body được xác nhận.
- [ ] Test profile khác, label khác và application khác.
- [ ] Test missing config, invalid YAML và Git backend failure theo contract.
- [ ] Test authentication, authorization và TLS nếu môi trường bật bảo vệ.
- [ ] Response/log không làm lộ token hoặc secret.
- [ ] Có client integration test riêng cho binding và property source precedence.
- [ ] Có smoke test sau khi promote cấu hình.

## 19. Bài thực hành

### Bước 1: Tạo fixture repository

Tạo repository test với `application.yml`, `application-qa.yml`, `catalog-service.yml` và `catalog-service-qa.yml` theo ví dụ trong bài. Commit và tạo tag bất biến `config-fixture-2026-11`.

**Kết quả cần đạt:** ghi nhận commit SHA và bốn giá trị mong đợi.

### Bước 2: Gọi Environment endpoint

Gọi `GET /catalog-service/qa/config-fixture-2026-11` bằng curl. Kiểm tra metadata và property sources.

**Kết quả cần đạt:** xác nhận server đang đọc đúng application/profile/label/revision.

### Bước 3: Kiểm tra precedence

Đổi riêng `catalog.max-page-size` trong file chung, file ứng dụng và file profile. Gọi API sau mỗi commit test mới và kiểm tra source đầu tiên có khóa.

**Kết quả cần đạt:** chứng minh file theo application/profile ghi đè file chung theo quy tắc đang dùng.

### Bước 4: Viết JUnit/REST Assured test

Tạo test gọi endpoint, assert metadata, revision và effective values bằng helper. Chạy test trong CI với `CONFIG_SERVER_URL` và `EXPECTED_CONFIG_SHA`.

**Kết quả cần đạt:** test thất bại khi sai profile, label, revision hoặc giá trị hiệu lực.

### Bước 5: Thử negative và security cases

Gọi application không tồn tại, label sai, token thiếu quyền và endpoint HTTPS với certificate không đúng trong môi trường lab.

**Kết quả cần đạt:** response phù hợp contract, không rò rỉ property được bảo vệ hoặc secret.

### Bước 6: Tạo client integration test

Khởi chạy Config Client thử nghiệm với application name `catalog-service`, profile `qa` và label fixture. Kiểm tra `CatalogProperties` sau binding.

**Kết quả cần đạt:** phân biệt API response đúng với client thực sự sử dụng giá trị đúng.

## 20. Tự kiểm tra

1. Vì sao HTTP 200 chưa đủ để kết luận Config Server trả cấu hình đúng?
2. API Environment endpoint nhận những tham số nào?
3. Vì sao test nên dùng immutable label và expected commit SHA?
4. `propertySources` giúp kiểm tra thứ tự ưu tiên như thế nào?
5. Vì sao kiểm tra giá trị xuất hiện trong một source chưa chứng minh đó là giá trị hiệu lực?
6. Config Server API test khác Config Client integration test ở đâu?
7. Cần xác nhận metadata nào trong response?
8. Làm thế nào kiểm tra nhiều profile và label?
9. Vì sao cần assert Content-Type trước khi parse body?
10. Những negative test nào nên có cho application/profile/label và Git backend?
11. Làm thế nào kiểm tra authorization mà không đưa secret production vào fixture?
12. Vì sao CI không nên lưu toàn bộ response Config Server thành artifact công khai?
13. Khi nào cần test client binding và refresh riêng?

Khi hoàn thành bài thực hành, người học có thể tạo fixture cấu hình xác định, kiểm thử API Config Server theo application/profile/label, xác nhận revision và property precedence, đồng thời phân biệt lỗi của server API với lỗi binding hoặc refresh ở Config Client.

## Tài liệu tham khảo

- [Spring Cloud Config – Serving Configuration](https://docs.spring.io/spring-cloud-config/reference/server/serving-configuration.html): Environment endpoint, application/profile/label và các định dạng response.
- [Spring Cloud Config – Environment Repository](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository.html): property sources, repository backend và cách tạo Environment.
- [Spring Cloud Config – Git Backend](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/git-backend.html): branch, tag, commit label và Git repository behavior.
- [REST Assured – Usage](https://github.com/rest-assured/rest-assured/wiki/Usage): HTTP request, response extraction và JSON assertions.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): tổ chức test và assertions.
