# Xuất đặc tả trong CI và phát hiện thay đổi phá vỡ hợp đồng

Một pull request có thể làm ứng dụng Spring Boot vẫn build thành công nhưng khiến client cũ không gọi được API nữa. Ví dụ: xóa operation, thêm query parameter bắt buộc, thu hẹp enum của request hoặc bỏ response status mà consumer đang xử lý. Vì vậy, CI cần kiểm tra cả OpenAPI document được sinh từ ứng dụng và mức độ tương thích của document đó với hợp đồng đã phát hành.

Trong bài thực hành này, ta xây dựng pipeline cho ứng dụng Spring Boot dùng springdoc-openapi. Pipeline sẽ:

1. Build và kiểm thử ứng dụng.
2. Khởi động ứng dụng trong môi trường CI.
3. Tải OpenAPI document từ endpoint springdoc.
4. Validate và lint document.
5. So sánh candidate với baseline đã được chấp thuận.
6. Chặn pull request nếu xuất hiện breaking change theo chính sách.
7. Lưu candidate cùng báo cáo để reviewer kiểm tra.

Ví dụ sử dụng Maven, GitHub Actions và oasdiff. Nếu dự án dùng Gradle hoặc CI khác, giữ nguyên thứ tự và nguyên tắc kiểm tra rồi thay lệnh tương ứng.

## 1. Phân biệt build thành công và contract tương thích

Build/test ứng dụng trả lời câu hỏi: mã nguồn có biên dịch, khởi động và vượt qua các test hiện có không? Contract diff trả lời câu hỏi khác: document mới có còn tương thích với những client được sinh hoặc viết theo document cũ không?

Hai kiểm tra này bổ sung cho nhau:

| Kiểm tra | Phát hiện tốt | Không tự chứng minh |
|---|---|---|
| Compile/build | Lỗi mã nguồn, dependency, cấu hình build | Client cũ còn dùng được |
| Unit/integration test | Hành vi trong các kịch bản đã viết test | Mọi thay đổi contract đều an toàn |
| OpenAPI validation | Cấu trúc document, schema và reference không hợp lệ | Contract mới tương thích với baseline |
| OpenAPI lint | Quy ước thiết kế, naming, metadata và tiêu chuẩn API | Runtime thực thi đúng document |
| Semantic/compatibility diff | Thay đổi có thể ảnh hưởng consumer | Mọi hành vi runtime hoặc mọi client thực tế |

Một pipeline tốt không chọn một công cụ duy nhất để thay thế tất cả. Nó xác minh document hợp lệ, so sánh contract, rồi chạy các test runtime quan trọng.

## 2. Thiết kế nguồn candidate và baseline

Trước khi viết workflow, phải xác định rõ hai input:

- **Candidate:** OpenAPI document được sinh từ commit đang được kiểm tra trong pull request.
- **Baseline:** document của API đã được chấp thuận và phát hành, thường được lưu trong nhánh chính hoặc lấy từ artifact release.

Không tạo cả baseline và candidate từ cùng một commit rồi so sánh chúng; kết quả gần như luôn giống nhau và không phát hiện được thay đổi do pull request.

Một cách quản lý đơn giản là lưu contract đã chấp thuận trong repository:

~~~text
contracts/
└── openapi/
    └── orders-v1.json
~~~

Khi pull request chạy, CI lấy file **origin/main:contracts/openapi/orders-v1.json** làm baseline và sinh candidate từ ứng dụng trong pull request. Sau khi thay đổi được review và merge, cập nhật file baseline cùng release hoặc qua một pull request contract riêng.

Có thể dùng artifact OpenAPI từ release thay cho file trong Git. Khi đó, pipeline cần tải đúng artifact của phiên bản đang phát hành, xác minh nguồn và giữ artifact đó bất biến. Không lấy một file bất kỳ từ môi trường production đang chạy mà không ghi lại commit, cấu hình và group đã dùng để sinh file.

### Quy tắc cho baseline

- Baseline phải đại diện cho hợp đồng đã được chấp thuận, không phải một bản build tùy ý.
- Mỗi API version hoặc group cần baseline riêng.
- Lưu cùng metadata nguồn: commit, release, Spring profile, group và phiên bản công cụ sinh document.
- Khi chấp thuận breaking change, phải có quyết định versioning và cập nhật baseline theo quy trình release.
- Với API mới chưa có baseline, validate và review document đầu tiên; không giả vờ chạy compatibility diff khi không có contract cũ.

## 3. Xác định endpoint springdoc cần export

Với cấu hình mặc định, springdoc cung cấp:

| Document | Endpoint mặc định |
|---|---|
| OpenAPI JSON | /v3/api-docs |
| OpenAPI YAML | /v3/api-docs.yaml |
| OpenAPI JSON theo group | /v3/api-docs/{groupName} |

Ví dụ ứng dụng có group orders-v1:

~~~bash
curl -fsS http://127.0.0.1:8080/v3/api-docs/orders-v1 \
  -H "Accept: application/json" \
  -o build/openapi/orders-v1.json
~~~

Nếu không dùng group, tải /v3/api-docs. Nếu đã đổi springdoc.api-docs.path, server.servlet.context-path, port hoặc reverse-proxy prefix, dùng URL thực tế của ứng dụng.

Các property như springdoc.api-docs.path, springdoc.api-docs.enabled và springdoc.group-configs được mô tả trong trang configuration properties của springdoc. Không hard-code endpoint mặc định trong pipeline nếu dự án đã cấu hình endpoint khác.

### Tạo document từ ứng dụng trong CI

Ưu tiên sinh document từ đúng artifact vừa build, dùng profile và cấu hình gần với môi trường triển khai. Cách này giúp CI kiểm tra kết quả mà consumer sẽ nhận được từ ứng dụng.

Ví dụ:

~~~bash
./mvnw -B clean verify
java -jar target/orders-api.jar \
  --spring.profiles.active=ci \
  --server.port=8080
~~~

Lệnh khởi động cần chạy ở background trong CI để bước tiếp theo tải được document. Chờ ứng dụng sẵn sàng bằng health endpoint hoặc retry request /v3/api-docs; không giả định process đã sẵn sàng ngay sau khi lệnh java -jar được gọi.

Nếu endpoint tài liệu được bảo vệ, dùng credential riêng của CI với quyền chỉ đọc tài liệu. Truyền token qua secret/environment variable, không ghi token vào command log, artifact hoặc file OpenAPI. Một lựa chọn khác là cấu hình profile CI để chỉ mở endpoint docs trong môi trường runner cô lập.

## 4. Bảo đảm document được tải thực sự là OpenAPI

Một lệnh curl có thể trả HTTP 200 nhưng body lại là HTML trang đăng nhập, trang reverse proxy hoặc JSON lỗi của ứng dụng. Vì vậy, sau khi tải cần kiểm tra:

- File tồn tại và không rỗng.
- Body parse được thành JSON/YAML.
- Có trường openapi, info.title, info.version và paths.
- Đúng group và đúng phạm vi API.
- Không chứa server URL, host hoặc metadata của môi trường không mong muốn.

Ví dụ kiểm tra JSON bằng jq:

~~~bash
test -s build/openapi/orders-v1.json
jq -e '.openapi and .info.title and .info.version and (.paths | type == "object")' \
  build/openapi/orders-v1.json
~~~

Nếu dùng JSON endpoint, giữ phần mở rộng .json. Nếu tải YAML, dùng phần mở rộng .yaml và validator hỗ trợ YAML. Không đổi đuôi file để đánh lừa công cụ.

### Kiểm tra tính tái lập

Candidate nên được sinh với cùng điều kiện mỗi lần chạy:

- Cùng Spring profile và các property ảnh hưởng controller mapping.
- Cùng group, package/path filters và customizer.
- Cùng biến cấu hình server URL phù hợp với contract.
- Không phụ thuộc dữ liệu ngẫu nhiên hoặc timestamp trong document.
- Không gọi production để lấy schema hoặc token thật.

Nếu URL server thay đổi theo môi trường, cân nhắc cấu hình một public server URL ổn định cho document phát hành hoặc loại phần khác biệt môi trường khỏi chính sách diff theo cách có kiểm soát. Không loại bỏ toàn bộ servers chỉ để làm báo cáo sạch.

## 5. Validate document trước khi diff

Phải validate candidate trước khi so sánh. Nếu document không parse được hoặc chứa schema/reference sai, báo cáo compatibility không đáng tin cậy.

Với oasdiff:

~~~bash
oasdiff validate build/openapi/orders-v1.json
~~~

Lệnh validate kiểm tra một OpenAPI document theo các quy tắc OpenAPI và JSON Schema mà công cụ hỗ trợ. Nó không so sánh với baseline.

Có thể bổ sung Redocly CLI để áp dụng quy ước thiết kế:

~~~bash
redocly lint build/openapi/orders-v1.json --config redocly.yaml
~~~

Ví dụ redocly.yaml:

~~~yaml
extends:
  - recommended
rules:
  operation-operationId: error
  operation-summary: warn
  no-unused-components: warn
~~~

Chọn ruleset và severity phù hợp với chuẩn của nhóm. Lint có thể báo lỗi style hoặc governance ngay cả khi document vẫn hợp lệ theo OpenAPI. Vì vậy, phân biệt rõ lỗi schema/parse với lỗi quy ước thiết kế để reviewer hiểu vì sao pipeline thất bại.

## 6. Chọn đúng lệnh so sánh của oasdiff

oasdiff có các lệnh trả lời những câu hỏi khác nhau:

| Lệnh | Nội dung | Mục đích trong CI |
|---|---|---|
| oasdiff validate spec.json | Validate một document | Xác nhận candidate hợp lệ |
| oasdiff diff base revision | Diff đầy đủ, kể cả thay đổi tài liệu | Điều tra mọi khác biệt |
| oasdiff changelog base revision | Thay đổi có thể ảnh hưởng consumer, breaking và non-breaking | Tạo báo cáo cho reviewer |
| oasdiff breaking base revision | Thay đổi được phân loại là có khả năng phá client | Làm compatibility gate |

Ví dụ tạo báo cáo:

~~~bash
oasdiff diff contracts/openapi/orders-v1.json \
  build/openapi/orders-v1.json \
  --format markdown \
  > build/openapi/full-diff.md

oasdiff changelog contracts/openapi/orders-v1.json \
  build/openapi/orders-v1.json \
  --format markdown \
  > build/openapi/changelog.md

oasdiff breaking contracts/openapi/orders-v1.json \
  build/openapi/orders-v1.json
~~~

diff có ích khi muốn xem cả thay đổi description, example hoặc metadata. changelog tập trung vào thay đổi có thể ảnh hưởng consumer. breaking dùng để quyết định có chặn pipeline hay không.

## 7. Hiểu ERR, WARN và INFO trước khi đặt gate

oasdiff phân loại kết quả theo mức:

| Mức | Ý nghĩa | Cách xử lý thường dùng |
|---|---|---|
| ERR | Breaking change chắc chắn theo contract được khai báo | Chặn merge nếu chưa được phê duyệt |
| WARN | Có khả năng phá client nhưng công cụ không thể kết luận chắc chắn | Yêu cầu reviewer điều tra |
| INFO | Thay đổi không bị phân loại là breaking | Đưa vào changelog nếu hữu ích |

Lệnh breaking phát hiện các thay đổi mức ERR và WARN. Có thể điều chỉnh mức làm pipeline thất bại:

~~~bash
# Chỉ chặn breaking change mức chắc chắn.
oasdiff breaking base.json revision.json --fail-on ERR

# Chặn cả thay đổi có khả năng phá client.
oasdiff breaking base.json revision.json --fail-on WARN
~~~

Chọn ERR khi nhóm muốn tự động chặn các trường hợp chắc chắn và yêu cầu con người xem xét WARN. Chọn WARN khi API có cam kết tương thích nghiêm ngặt và mọi cảnh báo đều phải được giải quyết trước khi merge.

Không nên hạ severity chỉ để CI xanh. Nếu một rule tạo false positive, đọc chi tiết thay đổi, xác định nguyên nhân và ghi ngoại lệ có phạm vi hẹp trong cấu hình được review. Ngoại lệ cần có người chịu trách nhiệm và thời hạn xem xét.

Exit code của lệnh là tín hiệu cho CI. Exit code khác 0 do breaking change phải được phân biệt với lỗi không tải được baseline, file candidate hỏng, thiếu binary hoặc lỗi cấu hình runner. Log cần giữ lại để xác định đúng nguyên nhân.

## 8. Những thay đổi thường phá vỡ client

Đánh giá breaking change cần xét chiều dữ liệu. Client gửi request; server trả response. Cùng một thay đổi schema có thể có tác động khác nhau ở hai chiều.

| Thay đổi | Tác động thường gặp | Đánh giá ban đầu |
|---|---|---|
| Xóa path hoặc HTTP method | Client không còn gọi được operation | Breaking |
| Thêm request parameter bắt buộc | Client cũ không gửi parameter sẽ thất bại | Breaking |
| Thu hẹp enum của request | Giá trị client từng gửi không còn hợp lệ | Breaking |
| Tăng giới hạn tối thiểu hoặc giảm giới hạn tối đa của request | Payload cũ có thể bị từ chối | Có thể breaking |
| Xóa response property | Client đang đọc property có thể lỗi | Breaking |
| Thu hẹp enum response | Client không còn nhận được giá trị đã biết | Có thể breaking |
| Xóa response status hoặc media type | Client không còn nhận nhánh response đã dựa vào | Breaking |
| Tăng security requirement hoặc scope bắt buộc | Credential cũ có thể không còn đủ quyền | Breaking |
| Đổi operationId | SDK generator có thể đổi tên method | Có thể phá source compatibility của SDK |
| Đổi servers.url | Client có thể gọi sai host hoặc prefix | Có thể phá khả năng kết nối |

Một số thay đổi thường tương thích hơn nhưng vẫn cần xem cách consumer được viết:

- Thêm request property optional thường không buộc client cũ gửi thêm dữ liệu.
- Thêm response property thường an toàn với client bỏ qua field lạ, nhưng có thể ảnh hưởng client dùng schema strict hoặc additionalProperties: false.
- Sửa description hoặc example thường không đổi wire contract, nhưng có thể ảnh hưởng quy trình sinh tài liệu hoặc code generator đặc thù.

Không dùng bảng này thay cho báo cáo công cụ và hiểu biết về consumer thực tế. Đặc tả không thể mô tả hết logic nghiệp vụ của server.

## 9. Ví dụ một thay đổi request làm CI thất bại

Baseline có operation:

~~~yaml
paths:
  /orders:
    get:
      operationId: listOrders
      parameters:
        - name: status
          in: query
          required: false
          schema:
            type: string
            enum: [OPEN, PAID, CANCELLED]
      responses:
        '200':
          description: Danh sách đơn hàng
~~~

Candidate thay status thành bắt buộc và bỏ enum CANCELLED:

~~~yaml
paths:
  /orders:
    get:
      operationId: listOrders
      parameters:
        - name: status
          in: query
          required: true
          schema:
            type: string
            enum: [OPEN, PAID]
      responses:
        '200':
          description: Danh sách đơn hàng
~~~

Client cũ có thể gọi GET /orders không kèm status hoặc gửi status=CANCELLED. Candidate không còn chấp nhận hai cách gọi đó. Semantic diff cần báo các thay đổi này và gate có thể chặn pull request.

Nếu nghiệp vụ thực sự cần thay đổi, nhóm có thể giữ operation cũ trong giai đoạn chuyển tiếp, tạo endpoint/version mới hoặc lên kế hoạch deprecation có thời hạn. Không xóa parameter cũ trước khi hiểu client nào còn sử dụng nó.

## 10. Ví dụ response thay đổi và ảnh hưởng SDK

Baseline:

~~~yaml
components:
  schemas:
    Order:
      type: object
      required: [id, status]
      properties:
        id:
          type: string
        status:
          type: string
        total:
          type: number
~~~

Candidate xóa status khỏi response:

~~~yaml
components:
  schemas:
    Order:
      type: object
      required: [id]
      properties:
        id:
          type: string
        total:
          type: number
~~~

Consumer đang đọc status có thể không còn xử lý đúng. SDK được sinh từ document mới cũng có thể xóa property tương ứng, làm mã nguồn consumer không biên dịch.

Đổi operationId hoặc tên component đôi khi không thay đổi HTTP wire format nhưng vẫn làm thay đổi public API của SDK. Nếu nhóm phát hành SDK, nên có thêm bước sinh SDK từ baseline và candidate, rồi so sánh hoặc compile một consumer mẫu.

## 11. Cấu hình chính sách compatibility trong repository

Giữ chính sách diff trong version control để local và CI dùng cùng quy tắc. oasdiff hỗ trợ file cấu hình .oasdiff.yaml ở root repository.

Ví dụ cấu hình gate:

~~~yaml
fail-on: ERR
~~~

Có thể cấu hình thêm ignore hoặc severity level cho trường hợp đã được điều tra. Mỗi ngoại lệ nên:

- Chỉ nhắm đến rule hoặc element cụ thể.
- Có lý do và liên kết đến quyết định review.
- Có người chịu trách nhiệm.
- Có thời điểm xem xét lại hoặc xóa ngoại lệ.

Tránh loại bỏ hàng loạt paths, parameters hoặc schemas khỏi diff. Làm như vậy có thể che mất chính thay đổi mà pipeline cần phát hiện.

## 12. Đưa version bump vào chính sách phát hành

Khi một breaking change được chấp thuận, API cần có kế hoạch versioning rõ ràng. Tùy chính sách, nhóm có thể:

- Tạo major version mới trong URL, ví dụ /v2 thành /v3.
- Duy trì version route cũ trong thời gian deprecation.
- Công bố migration guide và thời hạn ngừng hỗ trợ.
- Sinh SDK mới từ document của version mới.

Trường info.version là phiên bản của API/document theo quy ước dự án; trường openapi cho biết phiên bản OpenAPI Specification. Hai giá trị này không thay thế nhau.

Từ oasdiff v1.38.0, có thể dùng mức fail MISSING-VERSION-BUMP để chỉ thất bại khi có breaking change mà info.version không tăng major. Ví dụ:

~~~bash
oasdiff breaking base.json revision.json --fail-on MISSING-VERSION-BUMP
~~~

Khác với --fail-on ERR hoặc WARN, chính sách này cho phép breaking change đi cùng major version bump theo SemVer của info.version. Chỉ bật khi dự án thực sự dùng info.version theo quy tắc major/minor/patch và đã pin CLI có hỗ trợ mức fail này. Không xem việc tăng số version là đủ để thay thế review compatibility.

## 13. Pipeline GitHub Actions hoàn chỉnh

Ví dụ dưới đây giả định:

- Dự án Maven có wrapper mvnw.
- Spring Boot Maven plugin tạo target/orders-api.jar.
- Ứng dụng có group orders-v1.
- Baseline được lưu tại contracts/openapi/orders-v1.json trên nhánh main.
- Runner dùng Java 21 và có thể tải dependency từ repository đã cấu hình.

Điều chỉnh JDK, tên JAR, profile, endpoint, group và phiên bản action theo dự án. Pin phiên bản tool/action đã được nhóm kiểm tra; cập nhật pin qua pull request riêng.

~~~yaml
name: OpenAPI contract

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  openapi-contract:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up Java
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven

      - name: Set up Go
        uses: actions/setup-go@v5
        with:
          go-version: '1.24'

      - name: Install pinned oasdiff
        run: |
          go install github.com/oasdiff/oasdiff@v1.39.0
          echo "$(go env GOPATH)/bin" >> "$GITHUB_PATH"

      - name: Build and test
        run: ./mvnw -B clean verify

      - name: Export, validate and compare OpenAPI
        shell: bash
        run: |
          set -euo pipefail
          mkdir -p build/openapi

          java -jar target/orders-api.jar \
            --spring.profiles.active=ci \
            --server.address=127.0.0.1 \
            --server.port=8080 \
            > build/openapi/app.log 2>&1 &
          app_pid=$!
          trap 'kill "$app_pid" 2>/dev/null || true' EXIT

          for attempt in $(seq 1 60); do
            if curl -fsS \
              http://127.0.0.1:8080/v3/api-docs/orders-v1 \
              -H "Accept: application/json" \
              -o build/openapi/orders-v1.json; then
              break
            fi
            sleep 2
          done

          test -s build/openapi/orders-v1.json
          jq -e '.openapi and .info.title and .info.version and (.paths | type == "object")' \
            build/openapi/orders-v1.json

          oasdiff validate build/openapi/orders-v1.json

          if git cat-file -e \
            "origin/main:contracts/openapi/orders-v1.json" 2>/dev/null; then
            oasdiff changelog \
              origin/main:contracts/openapi/orders-v1.json \
              build/openapi/orders-v1.json \
              --format markdown \
              > build/openapi/changelog.md

            oasdiff diff \
              origin/main:contracts/openapi/orders-v1.json \
              build/openapi/orders-v1.json \
              --format markdown \
              > build/openapi/full-diff.md

            oasdiff breaking \
              origin/main:contracts/openapi/orders-v1.json \
              build/openapi/orders-v1.json \
              --fail-on ERR
          else
            echo "No approved baseline exists; review this new API contract."
          fi

      - name: Upload OpenAPI review artifacts
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: openapi-contract
          path: |
            build/openapi/orders-v1.json
            build/openapi/changelog.md
            build/openapi/full-diff.md
          if-no-files-found: warn
~~~

actions/checkout dùng fetch-depth: 0 để lấy được baseline từ origin/main. Cú pháp origin/main:path/to/spec.json cho phép oasdiff đọc file ở Git ref mà không cần tự copy baseline sang một thư mục tạm.

Trong ví dụ, --fail-on ERR chỉ chặn các thay đổi mức chắc chắn. Nếu nhóm muốn chặn cả WARN, đổi thành --fail-on WARN. Nếu API mới chưa có baseline, pipeline vẫn validate candidate và yêu cầu reviewer duyệt contract đầu tiên.

Lệnh java -jar phải chạy với cấu hình CI đã chuẩn bị. Nếu ứng dụng cần database, message broker hoặc biến môi trường khác, cung cấp service container/fixture phù hợp; không trỏ pipeline vào hệ thống production.

Artifact upload được cấu hình if: always() để reviewer còn xem được candidate và báo cáo khi bước compatibility gate thất bại. Không upload app.log nếu log có thể chứa token, thông tin cá nhân hoặc cấu hình nhạy cảm.

## 14. Nếu API có nhiều group hoặc nhiều document

Mỗi group springdoc có thể đại diện cho một hợp đồng khác nhau. Không so sánh orders-v1 với orders-v2, hoặc document public với internal.

Ví dụ:

| Group | Candidate | Baseline |
|---|---|---|
| orders-v1 | /v3/api-docs/orders-v1 | contracts/openapi/orders-v1.json |
| partners-v1 | /v3/api-docs/partners-v1 | contracts/openapi/partners-v1.json |
| admin-v1 | /v3/api-docs/admin-v1 | contracts/openapi/admin-v1.json |

Với nhiều file, cách dễ kiểm soát nhất là chạy một cặp oasdiff breaking cho từng group và lưu report riêng. Có thể dùng oasdiff breaking-files khi các candidate được lưu ở những path ổn định trùng với path baseline trong Git ref; lệnh này suy ra baseline từ cùng path ở revision được chỉ định. Nếu candidate được sinh vào thư mục build khác với vị trí baseline, dùng từng cặp breaking với đường dẫn baseline rõ ràng.

Nếu group được thêm mới, chưa có baseline là trạng thái bình thường. Cần validate, lint và review nội dung trước khi tạo baseline đầu tiên.

## 15. Bảo vệ pipeline khi xử lý external references

OpenAPI document có thể chứa $ref trỏ tới file hoặc URL bên ngoài. Khi CI resolve reference từ pull request không đáng tin cậy, công cụ có thể truy cập tài nguyên ngoài ngoài dự kiến.

oasdiff GitHub Action mặc định tắt external reference resolution để giảm nguy cơ SSRF. Với CLI, hãy ưu tiên document tự chứa hoặc reference nội bộ được checkout trong workspace. Chỉ bật khả năng resolve external refs khi nguồn đã được kiểm soát, pinned và được nhóm bảo mật chấp thuận.

Không cho phép pull request tùy ý thay URL $ref để khiến runner truy cập metadata endpoint, mạng nội bộ hoặc dịch vụ chỉ có thể truy cập từ runner.

## 16. Kiểm tra runtime contract song song với diff

Semantic diff chỉ so sánh những gì document khai báo. Nó không chứng minh controller thật sự trả đúng status, header, content type hoặc payload đã mô tả.

Thêm integration test cho các hành vi quan trọng:

- Endpoint public/secured trả đúng status.
- Request body hợp lệ và không hợp lệ được xử lý đúng.
- Response success/error đúng schema và media type.
- Parameter required, enum và boundary validation khớp document.
- /v3/api-docs/{group} chứa operation và schema mong đợi.

Ví dụ kiểm tra document bằng MockMvc:

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
class OpenApiContractTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void ordersGroupContainsListOperation() throws Exception {
        mockMvc.perform(get("/v3/api-docs/orders-v1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.paths['/orders'].get").exists())
            .andExpect(jsonPath(
                "$.paths['/orders'].get.operationId"
            ).value("listOrders"));
    }
}
~~~

Test này kiểm tra document được sinh ra. Nó cần đi cùng test gọi endpoint /orders với request/response thật để xác nhận runtime behavior.

## 17. Đọc kết quả CI và xử lý khi gate thất bại

| Kết quả | Điều cần kiểm tra | Hành động |
|---|---|---|
| Build thất bại | Compile, test, dependency, profile | Sửa lỗi ứng dụng trước khi đọc compatibility |
| Không tải được /v3/api-docs | Port, readiness, context path, auth, group | Xem app log và URL thực tế |
| Candidate rỗng hoặc không parse được | Body HTML/lỗi, serialization, endpoint sai | Kiểm tra HTTP response và file |
| oasdiff validate thất bại | Schema, $ref, required field, cấu trúc OAS | Sửa document hoặc cách sinh document |
| Lint thất bại | Quy ước thiết kế hoặc metadata | Sửa rule violation hoặc xin ngoại lệ có lý do |
| ERR breaking change | Contract cũ không còn tương thích | Giữ hành vi cũ, thiết kế migration hoặc tạo version mới |
| Chỉ có WARN | Công cụ chưa thể kết luận chắc chắn | Reviewer kiểm tra consumer, schema composition và runtime |
| Diff chỉ thay đổi mô tả | Tài liệu được chỉnh sửa | Review nội dung, không nhầm với wire-level breaking |
| Baseline không tồn tại | API/group mới hoặc chưa lưu contract release | Review document đầu tiên và tạo baseline sau khi duyệt |
| CI local và remote khác nhau | Khác tool version, profile, config hoặc baseline | Pin tool, ghi lại nguồn và tái lập cùng điều kiện |

Không xóa baseline để làm gate pass. Không thêm ignore rule chung cho cả schema hoặc path. Mọi thay đổi contract có chủ đích phải được giải thích trong pull request và gắn với kế hoạch phát hành.

## 18. Lưu artifact và cập nhật baseline sau khi merge

Khi pull request được duyệt:

1. Reviewer kiểm tra candidate, changelog và full diff.
2. Xác nhận các breaking change đã được xử lý hoặc có kế hoạch versioning.
3. Merge thay đổi code và contract đã chấp thuận theo quy trình repository.
4. Lưu OpenAPI document cùng release artifact, kèm commit/release identifier.
5. Cập nhật baseline của group nếu hợp đồng mới được chấp thuận.
6. Giữ baseline cũ trong lịch sử Git hoặc release storage để có thể so sánh các phiên bản sau.

Không tự động ghi đè baseline trước khi review hoàn tất. Baseline chính là mốc để các pull request tiếp theo đo compatibility.

## 19. Lỗi thường gặp khi tích hợp CI

| Biểu hiện | Nguyên nhân | Cách xử lý |
|---|---|---|
| Pipeline luôn báo không có breaking change | So sánh candidate với chính nó hoặc baseline lấy từ commit PR | Lấy baseline từ origin/main hoặc release đã phát hành |
| Pipeline không tìm thấy baseline | Checkout thiếu Git history/ref hoặc sai path | Dùng full history và kiểm tra file trong main |
| Document khác nhau giữa local và CI | Khác profile, env, group hoặc server URL | Chuẩn hóa cấu hình export |
| /v3/api-docs trả 401/403 | Docs endpoint được bảo vệ | Cấp token CI có scope phù hợp hoặc dùng CI profile cô lập |
| /v3/api-docs trả 404 | Sai group, path hoặc context path | Đọc springdoc properties và endpoint thực tế |
| Candidate là HTML nhưng file tên .json | Redirect đến login/proxy hoặc lỗi HTTP không được kiểm tra | Dùng curl -f, kiểm tra body bằng jq |
| Diff báo nhiều thay đổi không liên quan | Generator/config/tool version thay đổi | Pin tool, ổn định cấu hình và review full diff |
| CI thất bại dù chỉ có WARN | Gate dùng --fail-on WARN | Xem lại chính sách severity, không hạ mức tùy tiện |
| CI không fail với WARN | Gate dùng --fail-on ERR | Đổi sang WARN nếu nhóm yêu cầu nghiêm ngặt hơn |
| External $ref không resolve | Tài liệu phụ thuộc file/URL ngoài | Đóng gói reference hoặc cho phép nguồn tin cậy có kiểm soát |
| Artifact không có khi gate fail | Upload chỉ chạy khi job thành công | Dùng if: always() và chỉ upload file an toàn |
| Document mới có servers sai | URL lấy từ profile hoặc host runner | Cấu hình server URL public ổn định cho contract |

## 20. Checklist hoàn thành pipeline

- [ ] Xác định candidate được sinh từ commit đang kiểm tra.
- [ ] Baseline đến từ contract đã được chấp thuận hoặc release artifact.
- [ ] Baseline và candidate thuộc cùng API version và group.
- [ ] Ứng dụng build và test thành công trước khi export.
- [ ] CI khởi động ứng dụng với profile xác định.
- [ ] Endpoint springdoc đúng path và group.
- [ ] Request export kiểm tra HTTP status và file không rỗng.
- [ ] Candidate được parse/validate thành công.
- [ ] Lint áp dụng ruleset đã được nhóm thống nhất.
- [ ] oasdiff changelog và oasdiff diff được lưu để review.
- [ ] oasdiff breaking dùng severity gate phù hợp.
- [ ] Tool version và config được pin trong repository.
- [ ] External $ref được xử lý an toàn.
- [ ] Runtime integration test xác minh các contract quan trọng.
- [ ] Artifact upload không chứa token hoặc log nhạy cảm.
- [ ] Breaking change có quyết định versioning và migration.
- [ ] Baseline chỉ cập nhật sau khi contract mới được chấp thuận.

## 21. Tài liệu tham khảo chính thức

- [springdoc-openapi — Configuration Properties](https://springdoc.org/properties.html) — endpoint API docs, group configs, path filters và các property liên quan.
- [oasdiff — CLI Quick Start](https://www.oasdiff.com/docs/getting-started) — cài đặt, validate, diff, changelog, breaking, output format và exit code.
- [oasdiff — Breaking Changes and Changelog](https://github.com/oasdiff/oasdiff/blob/main/docs/BREAKING-CHANGES.md) — phân loại ERR, WARN, INFO và --fail-on.
- [oasdiff — Diff](https://github.com/oasdiff/oasdiff/blob/main/docs/DIFF.md) — hành vi so sánh và các tùy chọn semantic diff.
- [oasdiff — Checking Many Specs Against a Git Ref](https://github.com/oasdiff/oasdiff/blob/main/docs/BREAKING-FILES.md) — so sánh baseline từ Git ref và kiểm tra nhiều spec.
- [oasdiff — GitHub Action](https://www.oasdiff.com/docs/github-action) — tích hợp compatibility gate, artifact report và bảo vệ external references.
- [oasdiff — Releases](https://github.com/oasdiff/oasdiff/releases) — ghi chú phát hành, gồm mức fail MISSING-VERSION-BUMP từ v1.38.0.
- [Redocly CLI — lint](https://redocly.com/docs/cli/commands/lint) — lint OpenAPI và cấu hình ruleset.
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html) — cấu trúc document và ngữ nghĩa contract.

CI chỉ có thể bảo vệ API khi nó so sánh candidate với baseline thực sự đã được phát hành. Hãy sinh document từ ứng dụng springdoc, validate trước khi diff, dùng severity gate có chủ đích, lưu báo cáo và kiểm tra thêm runtime bằng integration test. Khi breaking change được chấp thuận, cập nhật version và baseline theo quy trình release để các lần so sánh tiếp theo luôn có mốc đáng tin cậy.
