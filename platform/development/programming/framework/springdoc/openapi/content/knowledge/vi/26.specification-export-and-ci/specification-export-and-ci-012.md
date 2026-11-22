# Dừng CI khi không lấy được đặc tả hoặc tài liệu không hợp lệ

## 1. Vì sao pipeline phải dừng khi OpenAPI không đáng tin cậy?

OpenAPI document thường được dùng để sinh client SDK, kiểm thử contract, tạo developer portal và làm đầu vào cho API gateway. Nếu pipeline không lấy được document hoặc nhận nhầm một response lỗi thành tài liệu, các bước phía sau có thể tiếp tục với file rỗng, file cũ hoặc nội dung không hợp lệ.

Ví dụ, ứng dụng Spring Boot chưa sẵn sàng nhưng pipeline đã gọi /v3/api-docs. Request có thể thất bại vì connection refused. Một trường hợp khác là Spring Security chuyển request sang trang đăng nhập HTML và trả status 200; bước tải file vẫn tạo ra một file nhưng nội dung không phải OpenAPI. Nếu pipeline chỉ kiểm tra file tồn tại, tài liệu sai vẫn có thể được publish.

Một pipeline đáng tin cậy cần dừng khi xảy ra một trong các tình huống:

- Không kết nối được endpoint OpenAPI.
- Endpoint trả HTTP status không thành công.
- Request bị redirect tới login page hoặc trang lỗi.
- Response rỗng, bị cắt hoặc không phải JSON/YAML.
- Document không tuân theo OpenAPI Specification đã khai báo.
- Reference hoặc schema không hợp lệ.
- Document vi phạm quy ước chất lượng của tổ chức.
- Có breaking change chưa được chấp thuận.
- Document được sinh từ sai build, sai profile hoặc sai document group.

Nguyên tắc là không cho phép publish một OpenAPI artifact mà pipeline chưa chứng minh được nguồn gốc và tính hợp lệ.

## 2. Luồng CI cần có các cổng kiểm tra rõ ràng

Một pipeline Springdoc có thể chia thành các giai đoạn:

~~~text
Checkout source revision
          |
          v
Build application artifact
          |
          v
Run unit / integration tests
          |
          v
Start the exact artifact
          |
          v
Wait for readiness
          |
          v
Fetch OpenAPI JSON/YAML
          |
          v
Check HTTP result and file content
          |
          v
Parse and validate OpenAPI
          |
          v
Lint and compatibility checks
          |
          v
Create manifest / checksum
          |
          v
Publish immutable artifacts
~~~

Mỗi bước là một gate. Nếu một gate thất bại, pipeline phải trả exit code khác 0 và không chạy bước publish.

Không nên gộp mọi thao tác vào một lệnh dài khó xác định nguyên nhân. Các bước tách biệt giúp log chỉ ra lỗi nằm ở build, startup, endpoint, document parser, governance rule hay compatibility diff.

## 3. Xác định endpoint OpenAPI mà pipeline cần lấy

Với cấu hình Springdoc mặc định, endpoint thường dùng là:

~~~http
GET /v3/api-docs
GET /v3/api-docs.yaml
~~~

Nếu đã cấu hình path khác, pipeline phải dùng đúng giá trị đó:

~~~yaml
springdoc:
  api-docs:
    enabled: true
    path: /openapi
~~~

Khi đó JSON document được lấy ở /openapi và YAML endpoint phụ thuộc path/extension theo cấu hình Springdoc đang sử dụng. Hãy xác minh URL thực tế bằng integration test thay vì giả định endpoint mặc định vẫn còn.

Nếu có document group:

~~~java
@Bean
GroupedOpenApi partnerApi() {
    return GroupedOpenApi.builder()
        .group("partner")
        .pathsToMatch("/api/partner/**")
        .build();
}
~~~

Document của group thường được lấy qua /v3/api-docs/partner. Một pipeline cần export nhiều group phải kiểm tra từng endpoint và ghi từng file riêng. Không dùng cùng output filename cho public, partner và internal document.

Cần phân biệt endpoint OpenAPI với Swagger UI URL. Tải trang Swagger UI HTML không đồng nghĩa đã tải được OpenAPI JSON.

## 4. Bật API docs trong profile dùng cho CI

Nếu ứng dụng có cấu hình profile riêng, hãy bảo đảm profile dùng trong pipeline cho phép tạo document:

~~~yaml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: false
~~~

Swagger UI không bắt buộc để export OpenAPI. Có thể tắt giao diện trong profile CI và vẫn giữ api-docs endpoint bật.

Một lỗi phổ biến là profile production hoặc test vô tình đặt springdoc.api-docs.enabled=false. Khi đó ứng dụng vẫn khởi động bình thường nhưng endpoint tài liệu trả 404 hoặc không được đăng ký.

Pipeline nên ghi rõ profile đã kích hoạt và kiểm tra endpoint sau startup. Không tự động chuyển sang profile khác khi endpoint lỗi, vì profile fallback có thể sinh document khác với cấu hình dự kiến của release.

## 5. Khởi chạy đúng artifact trước khi export

OpenAPI cần được sinh từ chính phiên bản ứng dụng mà pipeline đang kiểm tra. Không nên build một artifact, export document từ một ứng dụng local khác rồi publish cả hai như cùng một release.

Ví dụ với Maven:

~~~bash
./mvnw -B clean verify
~~~

Sau khi build thành công, chạy đúng JAR vừa tạo:

~~~bash
java -jar target/catalog-api.jar \
  --spring.profiles.active=contract \
  --server.port=8080
~~~

Đường dẫn JAR cần khớp tên artifact thực tế trong dự án. Nếu dùng Gradle, container image hoặc Docker Compose, nguyên tắc vẫn giống nhau: khởi chạy đúng artifact được tạo từ source revision hiện tại.

Nếu Springdoc Maven Plugin được dùng để tải document, cần nhớ plugin này lấy OpenAPI từ một ứng dụng đang chạy theo URL cấu hình; pipeline vẫn phải đảm bảo server đã được khởi động và sẵn sàng. Không coi goal generate là bằng chứng ứng dụng đã tự khởi động thành công.

## 6. Chờ readiness thay vì chờ một khoảng thời gian cố định

Một lệnh sleep 10 có thể chạy nhanh ở máy local nhưng thất bại trong CI khi JVM khởi động chậm. Ngược lại, thời gian chờ cố định quá dài làm pipeline chậm dù ứng dụng đã sẵn sàng.

Nếu ứng dụng có Spring Boot Actuator readiness endpoint, có thể chờ endpoint đó:

~~~bash
HEALTH_URL="http://localhost:8080/actuator/health/readiness"
READY=false

for attempt in $(seq 1 30); do
  if curl --silent --show-error --fail \
      --connect-timeout 2 --max-time 5 \
      "$HEALTH_URL" >/dev/null; then
    READY=true
    break
  fi

  sleep 2
done

if [ "$READY" != "true" ]; then
  echo "Application did not become ready"
  exit 1
fi
~~~

Ví dụ giả định Actuator readiness endpoint đã được bật và được phép truy cập trong môi trường CI. Nếu dự án không dùng Actuator, có thể chờ một health endpoint khác hoặc chính endpoint OpenAPI.

Không thêm endpoint readiness giả chỉ để pipeline xanh. Readiness nên phản ánh khả năng phục vụ request thực tế và các dependency bắt buộc của ứng dụng.

## 7. Retry có giới hạn cho lỗi tạm thời

Ngay sau khi readiness thành công, một request OpenAPI vẫn có thể gặp lỗi tạm thời do proxy, connection pool hoặc startup race. Retry có giới hạn giúp xử lý lỗi transient.

Ví dụ curl:

~~~bash
curl \
  --silent \
  --show-error \
  --fail \
  --location \
  --connect-timeout 5 \
  --max-time 60 \
  --retry 5 \
  --retry-connrefused \
  --retry-delay 2 \
  --retry-max-time 60 \
  "http://localhost:8080/v3/api-docs" \
  --output target/openapi/openapi.json
~~~

Các tùy chọn retry cần được hỗ trợ bởi phiên bản curl trên runner. Pipeline nên pin hoặc xác minh toolchain nếu dựa vào option mới.

Retry chỉ dành cho lỗi có khả năng tạm thời. Không retry vô hạn với 401, 403, 404 hoặc document sai schema. Các lỗi này thường cần sửa cấu hình hoặc quyền truy cập, không cần chờ thêm.

Đặt timeout cho cả kết nối và tổng request để một endpoint treo không giữ runner vô thời hạn.

## 8. Không để file cũ che giấu lỗi fetch

Một lỗi nguy hiểm là output directory đã chứa openapi.yaml từ lần chạy trước. Lần export hiện tại thất bại nhưng bước sau vẫn thấy file cũ và tiếp tục validate/publish.

Có thể tạo thư mục output mới hoặc xóa đúng file output trước khi fetch:

~~~bash
mkdir -p target/openapi
rm -f target/openapi/openapi.json
rm -f target/openapi/openapi.yaml
~~~

Sau đó, chỉ tiếp tục nếu lệnh fetch hiện tại thành công và file được tạo trong lần chạy này.

Một cách an toàn hơn là tải vào file tạm rồi đổi tên sau khi fetch hoàn tất:

~~~bash
SPEC_TMP="target/openapi/openapi.yaml.tmp"
SPEC_FILE="target/openapi/openapi.yaml"

rm -f "$SPEC_TMP" "$SPEC_FILE"

curl --silent --show-error --fail --location \
  --connect-timeout 5 --max-time 60 \
  "http://localhost:8080/v3/api-docs.yaml" \
  --output "$SPEC_TMP"

test -s "$SPEC_TMP"
mv "$SPEC_TMP" "$SPEC_FILE"
~~~

Nếu curl thất bại, file chính thức chưa được tạo. Không dùng file từ cache của runner hoặc workspace cũ làm fallback cho release hiện tại.

## 9. Kiểm tra HTTP status và loại response

Dùng curl với --fail để lệnh thất bại khi server trả HTTP status lỗi. Có thể theo redirect bằng --location nếu kiến trúc cho phép, nhưng cần chú ý redirect tới trang đăng nhập.

Một endpoint có thể trả 200 OK nhưng body là HTML:

~~~html
<!doctype html>
<html>
  <title>Sign in</title>
</html>
~~~

Vì vậy, HTTP 200 không đủ để chứng minh response là OpenAPI. Cần kiểm tra nội dung hoặc parse document bằng validator.

Ví dụ kiểm tra nhanh HTML ở đầu file:

~~~bash
if head -c 512 target/openapi/openapi.json \
    | grep -Eiq '<!doctype html|<html'; then
  echo "Expected OpenAPI JSON but received HTML"
  exit 1
fi
~~~

Đây chỉ là bước phát hiện sớm. Validator OpenAPI vẫn là gate chính để xác minh cấu trúc và ngữ nghĩa.

Nếu API docs được bảo vệ, hãy gửi credential CI có quyền đọc tài liệu. Không tắt Spring Security trong profile chỉ để fetch được document; điều đó có thể khiến pipeline kiểm tra một cấu hình khác production.

## 10. Phân loại lỗi fetch để xử lý đúng

| Dấu hiệu | Nguyên nhân có thể | Hành động |
|---|---|---|
| Connection refused | Ứng dụng chưa listen hoặc port sai | Kiểm tra startup/readiness và port |
| Timeout | Startup chậm, thread bị treo hoặc endpoint quá nặng | Kiểm tra log, tăng timeout có giới hạn và profiling |
| HTTP 401 | Thiếu authentication | Cấu hình credential CI có quyền đọc docs |
| HTTP 403 | Credential thiếu quyền hoặc security matcher chặn | Kiểm tra role và filter chain |
| HTTP 404 | Sai path, docs bị tắt hoặc group không tồn tại | Kiểm tra springdoc path/profile/group |
| HTTP 5xx | Lỗi ứng dụng hoặc customizer | Xem log server và stack trace |
| HTTP 200 nhưng HTML | Redirect login hoặc proxy error page | Kiểm tra redirect/auth và content |
| File rỗng | Export lỗi hoặc response bị cắt | Kiểm tra curl exit code và server log |
| JSON/YAML parse lỗi | Document hỏng hoặc format không đúng | Kiểm tra response và phiên bản exporter |
| OpenAPI validation lỗi | Document không hợp lệ | Sửa schema/annotation/customizer |

Không nên chuyển tất cả lỗi thành một thông báo “OpenAPI generation failed” chung chung. Giữ lại HTTP status, endpoint, curl error và log ứng dụng để người sửa xác định nguyên nhân.

## 11. Xác minh file đã được tạo và không rỗng

Sau khi fetch thành công:

~~~bash
SPEC_FILE="target/openapi/openapi.yaml"

if [ ! -f "$SPEC_FILE" ]; then
  echo "OpenAPI file was not created"
  exit 1
fi

if [ ! -s "$SPEC_FILE" ]; then
  echo "OpenAPI file is empty"
  exit 1
fi
~~~

Không dùng điều kiện chỉ kiểm tra file tồn tại. File zero bytes vẫn có thể tồn tại sau một lần ghi lỗi.

Nếu cần lưu cả JSON và YAML, kiểm tra từng file riêng. Không coi việc tải JSON thành công là bằng chứng YAML endpoint cũng hoạt động.

Tên file output phải cố định trong job và không trùng giữa các group. Nếu export group partner và public, hãy tạo partner.yaml và public.yaml hoặc thư mục riêng cho từng group.

## 12. Parse và validate theo OpenAPI Specification

Document phải được parse bằng công cụ hiểu OpenAPI, không chỉ bằng JSON/YAML parser tổng quát.

Một YAML có thể parse thành map nhưng thiếu trường bắt buộc hoặc dùng sai cấu trúc OpenAPI. Một JSON hợp lệ về cú pháp cũng có thể chứa operation thiếu response hoặc reference không resolve.

Có thể dùng Redocly CLI để lint document:

~~~bash
npx redocly lint target/openapi/openapi.yaml
~~~

Trong pipeline production, cài và pin version Redocly CLI qua package manifest/lockfile hoặc tool container đã cố định. Không tải version mới nhất ở mỗi lần chạy nếu muốn kết quả CI có thể tái lập.

Lệnh lint có thể áp dụng rule set mặc định hoặc cấu hình của repository. Phân biệt lỗi cấu trúc/spec với warning theo governance policy của dự án.

Nếu dùng OpenAPI 3.1, bảo đảm validator hỗ trợ 3.1 và các JSON Schema feature mà document sử dụng. Validator cũ có thể báo sai hoặc bỏ qua một số cấu trúc mới.

## 13. Kiểm tra phiên bản và các trường nền tảng

Pipeline có thể kiểm tra các trường nền tảng trước khi chạy các bước nâng cao:

- Trường openapi có mặt và thuộc version được dự án cho phép.
- info có title và version hợp lệ.
- paths tồn tại theo cấu trúc của document.
- Các operation có response được mô tả.
- components và references hợp lệ.
- Server URL phù hợp với profile CI.
- Document group đúng audience.

Ví dụ với document JSON và jq:

~~~bash
jq -e '
  (.openapi | type == "string") and
  (.info.title | type == "string" and length > 0) and
  (.info.version | type == "string" and length > 0) and
  (.paths | type == "object")
' target/openapi/openapi.json >/dev/null
~~~

Đoạn kiểm tra này chỉ phù hợp với JSON. Với YAML, dùng validator OpenAPI hoặc công cụ đọc YAML đã pin. Không chuyển YAML sang JSON bằng cách thay ký tự hoặc xử lý text đơn giản.

Kiểm tra thủ công bổ sung không thay thế OpenAPI validator; nó giúp phát hiện các trường quan trọng của service mà tổ chức muốn bắt buộc.

## 14. Validate references và schema

Một document có thể parse được nhưng chứa $ref không tồn tại:

~~~yaml
schema:
  $ref: '#/components/schemas/UnknownModel'
~~~

Validator cần kiểm tra local reference và các external reference theo policy. Nếu external reference được tải từ URL, pipeline có thể phụ thuộc mạng hoặc nội dung bên ngoài thay đổi.

Để build có thể tái lập:

- Ưu tiên local references được version hóa cùng contract.
- Pin nội dung external reference bằng version hoặc commit.
- Hạn chế truy cập mạng ngoài trong validation nếu không cần.
- Lưu log rõ ràng khi resolver không tải được reference.
- Không bỏ qua unresolved reference để pipeline tiếp tục publish.

Schema validation cũng cần xem type, format, required, enum, nullable và composition như allOf/oneOf/anyOf. Với OpenAPI 3.1, cần hiểu JSON Schema dialect được khai báo.

## 15. Tách validation chuẩn khỏi lint policy

Có hai loại kiểm tra khác nhau:

**Validation theo OpenAPI Specification**

- Cấu trúc document đúng.
- Object nằm đúng vị trí.
- Reference và schema được xử lý đúng.
- Phiên bản document và feature tương thích.

**Lint theo quy ước tổ chức**

- Operation có summary và operationId.
- Tag theo naming convention.
- Error response dùng schema chuẩn.
- Security requirement có mặt ở operation cần bảo vệ.
- Không công bố hostname nội bộ.
- Schema có description và example theo yêu cầu.

Một document có thể hợp lệ theo OpenAPI nhưng fail lint vì thiếu operationId. Ngược lại, document có thể tuân thủ naming convention nhưng vẫn sai cấu trúc chuẩn.

Hãy báo riêng hai nhóm lỗi để nhóm phát triển biết cần sửa contract hay cần bổ sung metadata theo governance rule.

## 16. Chạy contract diff sau khi document hợp lệ

Chỉ chạy breaking-change diff khi candidate và baseline đều là OpenAPI document hợp lệ.

Ví dụ với oasdiff:

~~~bash
oasdiff breaking previous/openapi.yaml target/openapi/openapi.yaml
~~~

Nếu document không lấy được hoặc không validate, không chạy diff với file cũ còn sót lại. Kết quả diff khi một đầu vào thiếu hoặc stale không có giá trị.

Baseline phải thuộc cùng service, API audience và document group. Không so public API với internal API hoặc so một group khác chỉ vì file có tên tương tự.

Breaking change cần được review theo policy. Nếu công cụ phát hiện thay đổi có ảnh hưởng client, pipeline nên fail hoặc yêu cầu approval được ghi nhận. Không dùng || true để bỏ qua exit code của validator/diff trong release job.

## 17. Pipeline GitHub Actions mẫu

Ví dụ dưới đây minh họa một job Maven, khởi chạy JAR, chờ readiness, export document và lint bằng Redocly. Repository cần có package.json/package-lock.json chứa version Redocly đã pin và artifact JAR đúng tên.

~~~yaml
name: OpenAPI contract gate

on:
  pull_request:
  push:
    branches: [main]

jobs:
  openapi:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven

      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: npm

      - name: Install pinned OpenAPI tooling
        run: npm ci

      - name: Build and test
        run: ./mvnw -B clean verify

      - name: Start application artifact
        run: |
          nohup java -jar target/catalog-api.jar \
            --spring.profiles.active=contract \
            --server.port=8080 > app.log 2>&1 &
          echo $! > app.pid

      - name: Wait for readiness and export
        run: |
          set -euo pipefail
          ready=false
          for attempt in $(seq 1 30); do
            if curl --silent --show-error --fail \
                http://localhost:8080/actuator/health/readiness \
                >/dev/null; then
              ready=true
              break
            fi
            sleep 2
          done

          if [ "$ready" != "true" ]; then
            cat app.log
            echo "Application did not become ready"
            exit 1
          fi

          mkdir -p target/openapi
          rm -f target/openapi/openapi.yaml

          curl --silent --show-error --fail --location \
            --connect-timeout 5 --max-time 60 \
            --retry 5 --retry-connrefused --retry-delay 2 \
            http://localhost:8080/v3/api-docs.yaml \
            --output target/openapi/openapi.yaml

          test -s target/openapi/openapi.yaml

      - name: Validate and lint OpenAPI
        run: npx redocly lint target/openapi/openapi.yaml

      - name: Upload validated contract
        uses: actions/upload-artifact@v4
        with:
          name: catalog-api-openapi
          path: target/openapi/openapi.yaml
~~~

Đây là mẫu cần điều chỉnh theo tên JAR, Java version, readiness endpoint, port và cấu hình Springdoc của dự án. Nếu không bật Actuator readiness, thay bằng health endpoint thực tế.

GitHub Actions không tự biết ứng dụng đã sẵn sàng chỉ vì tiến trình Java được tạo. Vòng lặp readiness là gate riêng trước bước fetch.

## 18. Bảo đảm publish chỉ chạy sau tất cả gate

Trong workflow, bước publish phải phụ thuộc job hoặc step validation thành công. Không cấu hình publish bằng điều kiện luôn chạy như always() nếu không có kiểm tra kết quả thành công.

Một cách tổ chức an toàn:

~~~yaml
jobs:
  validate-openapi:
    runs-on: ubuntu-latest
    steps:
      - name: Fetch
        run: ./ci/fetch-openapi.sh
      - name: Validate
        run: ./ci/validate-openapi.sh
      - name: Upload validated contract
        uses: actions/upload-artifact@v4
        with:
          name: catalog-api-openapi
          path: target/openapi/openapi.yaml

  publish-openapi:
    needs: validate-openapi
    if: success()
    runs-on: ubuntu-latest
    steps:
      - name: Download validated artifact
        uses: actions/download-artifact@v4
        with:
          name: catalog-api-openapi
      - name: Publish
        run: ./ci/publish-openapi.sh
~~~

Artifact được publish phải là chính file đã validate, không fetch lại từ một endpoint khác trong publish job. Nếu fetch lại, nội dung có thể khác candidate đã được kiểm tra.

Trong pipeline nhiều job, upload/download artifact phải giữ đúng run ID và tên artifact. Không tải một artifact cùng tên từ lần chạy trước hoặc từ branch khác.

## 19. Không dùng fallback tài liệu cũ khi fetch thất bại

Không nên viết logic:

~~~bash
curl ... || cp previous/openapi.yaml target/openapi/openapi.yaml
~~~

Cách này khiến pipeline xanh với tài liệu cũ trong khi application artifact mới không tạo được contract. Người dùng có thể tưởng document đã được kiểm tra cho release mới.

Baseline cũ chỉ dùng để so sánh compatibility, không dùng làm candidate thay thế khi export thất bại.

Nếu muốn lưu document cuối cùng để hỗ trợ chẩn đoán, hãy phân biệt rõ failure artifact và release artifact. Failure artifact không được publish vào catalog hoặc đường dẫn contract chính thức.

## 20. Thu thập log khi gate thất bại

Khi fetch hoặc validation thất bại, cần giữ thông tin đủ để debug:

- Commit SHA và pipeline run ID.
- Active Spring profile.
- Artifact name/version.
- OpenAPI URL và document group.
- HTTP status hoặc curl exit code.
- Response Content-Type.
- Kích thước file nhận được.
- Log startup của ứng dụng.
- Validator/linter version.
- Lỗi validation hoặc lint cụ thể.

Không upload file chứa token, cookie, secret hoặc dữ liệu nhạy cảm. Nếu response body là trang login hoặc error page, có thể lưu bản đã loại bỏ thông tin nhạy cảm làm diagnostic artifact, nhưng không được coi đó là OpenAPI release.

Trong GitHub Actions, có thể upload app.log khi job thất bại bằng điều kiện failure() và retention ngắn. Chỉ lưu những log cần thiết và áp dụng chính sách bảo vệ dữ liệu của tổ chức.

## 21. Kiểm tra document group riêng biệt

Nếu ứng dụng có nhiều GroupedOpenApi, một endpoint group có thể hoạt động trong khi group khác bị cấu hình sai.

Ví dụ cần export:

~~~text
/v3/api-docs/public
/v3/api-docs/partner
/v3/api-docs/internal
~~~

Pipeline nên khai báo danh sách group mong đợi và lặp qua từng group. Nếu group bắt buộc trả 404, document rỗng hoặc thiếu operation, job phải fail.

Không bỏ qua group chỉ vì nó không có thay đổi trong pull request. Một lỗi filter hoặc security matcher có thể làm tài liệu group biến mất sau thay đổi cấu hình.

Tên file nên giữ group identity:

~~~text
target/openapi/public.yaml
target/openapi/partner.yaml
target/openapi/internal.yaml
~~~

Mỗi file cần được validate riêng và publish theo đúng audience. Tài liệu internal không được đưa vào artifact public do glob upload quá rộng.

## 22. Xử lý authentication khi tải API docs

Nếu OpenAPI endpoint được bảo vệ, pipeline cần credential chỉ có quyền đọc tài liệu. Ví dụ:

~~~bash
curl --silent --show-error --fail \
  --header "Authorization: Bearer $DOCS_TOKEN" \
  "http://localhost:8080/v3/api-docs" \
  --output target/openapi/openapi.json
~~~

DOCS_TOKEN phải được cấp từ secret store của CI, không lưu trong source, YAML workflow dạng literal hoặc log.

Không tắt security trong profile CI để tránh 401. Điều đó làm pipeline kiểm tra một bề mặt truy cập khác với ứng dụng đã phát hành.

Nếu dùng cookie/session hoặc OAuth2 client credentials, hãy cấu hình luồng cấp token riêng cho CI và giới hạn audience/scope. Khi token hết hạn hoặc thiếu quyền, pipeline cần fail với thông báo authentication rõ ràng.

## 23. Kiểm tra server URL và metadata môi trường

Một document hợp lệ về cấu trúc vẫn có thể sai môi trường. Ví dụ contract profile vô tình sinh:

~~~yaml
servers:
  - url: https://staging-api.example.com
~~~

trong khi artifact dự kiến phát hành cho production.

Có thể thêm policy check cho danh sách host được phép theo profile. Không nên kiểm tra bằng cách tìm chuỗi toàn file nếu hostname có thể xuất hiện trong description hoặc example; hãy parse trường servers.

Nếu pipeline tạo document canonical không phụ thuộc môi trường, server URL có thể được chuẩn hóa theo policy. Nếu document được sinh theo từng môi trường, profile và expected base URL cần được khai báo rõ.

Không dùng Host header tùy ý từ request CI để quyết định server URL. Dùng cấu hình đã kiểm soát trong profile hoặc environment variables.

## 24. Lỗi thường gặp khi CI không dừng đúng lúc

| Hiện tượng | Nguyên nhân |
|---|---|
| Fetch thất bại nhưng job vẫn xanh | Lệnh curl bị che bằng || true hoặc script không bật fail-fast |
| Pipeline validate file cũ | Output directory không được làm sạch trước export |
| File JSON chứa HTML | Redirect login hoặc proxy trả trang lỗi status 200 |
| File rỗng vẫn được publish | Chỉ kiểm tra file tồn tại, không kiểm tra size |
| Validator chạy trên sai document | Sai path hoặc group URL |
| Document invalid nhưng lint không fail | Dùng rule set quá lỏng hoặc tool không hỗ trợ OpenAPI version |
| 401/403 bị retry liên tục | Retry policy không phân biệt lỗi transient và authorization |
| Startup timeout ngẫu nhiên | Dùng sleep cố định thay readiness check |
| Publish artifact khác candidate | Publish job fetch lại document hoặc tải nhầm artifact |
| Breaking change bị bỏ qua | Exit code diff bị nuốt hoặc baseline sai |
| CI profile khác production | Metadata, security hoặc handler mapping khác cấu hình |
| Internal document lọt ra public | Upload glob lấy tất cả group artifacts |

Khi sửa pipeline, hãy tạo test cố ý làm endpoint trả 404, HTML, file rỗng hoặc schema lỗi để xác minh gate thực sự fail. Không chỉ kiểm tra đường chạy thành công.

## 25. Checklist fail-fast trước khi publish

Trước khi cho phép phát hành OpenAPI artifact:

1. Checkout đúng source revision.
2. Build và test application artifact.
3. Khởi chạy chính artifact vừa build.
4. Chờ readiness bằng health endpoint có giới hạn timeout.
5. Fetch đúng JSON/YAML endpoint và đúng document group.
6. Dùng retry có giới hạn cho lỗi transient.
7. Fail khi HTTP status không thành công.
8. Fail khi response là HTML, file rỗng hoặc file không được tạo mới.
9. Parse và validate theo OpenAPI Specification version.
10. Resolve local/external references theo policy.
11. Chạy lint theo governance rules.
12. Kiểm tra server URL và metadata môi trường.
13. So sánh baseline để phát hiện breaking change.
14. Không dùng tài liệu cũ làm fallback candidate.
15. Publish chính artifact đã validate, không fetch lại.
16. Giữ log chẩn đoán an toàn khi gate thất bại.

Một pipeline chỉ đáng tin khi nó dừng đúng lúc. Với Springdoc, hãy coi việc lấy được OpenAPI document là một điều kiện bắt buộc của release: ứng dụng phải sẵn sàng, endpoint phải trả đúng nội dung, document phải hợp lệ và mọi policy gate phải đạt trước khi artifact được công bố.

