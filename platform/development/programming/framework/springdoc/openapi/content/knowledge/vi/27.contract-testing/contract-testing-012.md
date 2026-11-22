# Ảnh chụp hợp đồng và so sánh ngữ nghĩa thay vì chỉ so sánh định dạng

Khi một ứng dụng Spring Boot thay đổi controller, DTO, validation hoặc cấu hình bảo mật, OpenAPI Description được springdoc sinh ra cũng có thể thay đổi. Cần biết thay đổi đó chỉ là cách trình bày tài liệu hay đã làm thay đổi hợp đồng mà client đang sử dụng. So sánh hai file JSON/YAML dưới dạng văn bản thường tạo ra nhiều nhiễu: thứ tự key, khoảng trắng, cách serialize hoặc tên component được sinh lại có thể thay đổi dù ý nghĩa API không đổi.

**Contract snapshot** là bản chụp OpenAPI Description được tạo từ một phiên bản ứng dụng và môi trường xác định. Snapshot được lưu làm baseline để so sánh với tài liệu mới. **Semantic diff** phân tích cấu trúc OpenAPI và đánh giá thay đổi theo ý nghĩa của hợp đồng: path, method, parameter, schema, response, media type và security. Mục tiêu là phát hiện thay đổi ảnh hưởng client, thay vì chỉ báo rằng hai file có byte khác nhau.

Snapshot và semantic diff bổ sung cho kiểm thử runtime. Chúng giúp phát hiện hợp đồng bị thay đổi ngoài dự kiến, nhưng không tự chứng minh server thực hiện đúng tài liệu hoặc mọi consumer đều tương thích.

## 1. Contract snapshot là gì?

Contract snapshot là một OpenAPI document được tạo tại một thời điểm cụ thể và được giữ làm mốc tham chiếu. Snapshot thường được sinh từ ứng dụng đã build, chạy với profile và cấu hình được kiểm soát.

Ví dụ:

~~~text
api/
  openapi/
    catalog-v1.yaml       # Baseline đã được review và phát hành
build/
  openapi/
    catalog-current.yaml  # Tài liệu sinh từ commit đang kiểm tra
~~~

Baseline có thể được lưu trong Git, artifact repository hoặc hệ thống quản lý hợp đồng. Lưu trong Git giúp reviewer xem được lịch sử thay đổi cùng code. Lưu như artifact gắn với release giúp tái tạo đúng hợp đồng đã phát hành. Dù chọn cách nào, cần biết snapshot thuộc commit, release, API group và môi trường nào.

Một snapshot tốt nên có:

- OpenAPI document hoàn chỉnh, không phải ảnh chụp Swagger UI.
- Phiên bản API hoặc release tương ứng.
- API group và base path được mô tả.
- Cấu hình profile dùng khi sinh tài liệu.
- Commit hoặc build identifier tạo ra snapshot.
- Quy ước về server URL, biến môi trường và dữ liệu sinh tự động.

Snapshot là hợp đồng mô tả API, không phải bản ghi response thực tế của một request. Nếu muốn kiểm tra payload runtime, cần thêm integration test hoặc contract test gửi request tới server.

## 2. Vì sao không chỉ so sánh JSON/YAML bằng Git diff?

JSON object là tập hợp cặp key/value; thứ tự key không mang ý nghĩa hợp đồng. YAML mapping cũng không nên được xem là có ý nghĩa chỉ vì serializer đổi thứ tự dòng. Do đó, hai tài liệu có thể tương đương nhưng tạo ra diff văn bản lớn.

Các nguồn nhiễu phổ biến:

- Thứ tự key trong object JSON hoặc YAML thay đổi.
- Thụt lề, xuống dòng, dấu nháy hoặc cách biểu diễn scalar khác nhau.
- Serializer thay đổi cách ghi number, boolean hoặc null.
- Thứ tự component hoặc schema được sinh ra thay đổi.
- Server URL thay đổi theo host, port hoặc reverse proxy của môi trường chạy.
- Timestamp, build metadata hoặc giá trị động bị đưa vào description/example.
- Tên component được sinh tự động thay đổi sau refactor package hoặc class.
- Group hoặc profile khác nhau làm tập hợp endpoint trong document khác nhau.

Git diff vẫn hữu ích để review nội dung, nhưng nó trả lời câu hỏi “dòng nào thay đổi?”. Nó không tự trả lời “client cũ có còn gọi API đúng theo hợp đồng không?”.

## 3. Chuẩn hóa định dạng và chuẩn hóa ngữ nghĩa là hai việc khác nhau

**Canonicalization** làm cho cùng một cấu trúc được serialize theo cách ổn định. Ví dụ, parse JSON rồi sắp xếp key của object trước khi ghi file giúp giảm diff do thứ tự key.

~~~bash
jq -S . build/openapi.json > build/openapi.canonical.json
~~~

Lệnh trên sắp xếp key trong object JSON. Nó không đánh giá tương thích API và không loại bỏ thay đổi ngữ nghĩa. Đây chỉ là bước giảm nhiễu định dạng.

Không được tùy tiện sắp xếp mọi array. Trong OpenAPI, thứ tự một số array có thể ảnh hưởng cách hiển thị hoặc lựa chọn, ví dụ thứ tự tag hay server. Một security requirement có semantics OR giữa các phần tử; các scheme trong cùng requirement lại có semantics AND. Sắp xếp hoặc gộp array không hiểu ngữ nghĩa có thể làm thay đổi document.

**Semantic normalization** cần parser hiểu OpenAPI để phân biệt:

- Map/object key order không quan trọng.
- Thứ tự array nào được giữ theo hợp đồng hoặc trải nghiệm người dùng.
- Reference nào trỏ tới cùng schema.
- Operation nào thuộc path và HTTP method nào.
- Security requirement hiệu lực ở cấp root và operation.
- Schema request và response cần được so sánh theo hướng dữ liệu.

Không xóa description, example, deprecated, security hoặc server URL chỉ để diff trông gọn hơn. Những trường đó có thể quan trọng với consumer, vận hành hoặc bảo mật. Nếu muốn bỏ qua một loại thay đổi trong một kiểm tra cụ thể, hãy ghi rõ policy và vẫn giữ bản diff đầy đủ cho reviewer.

## 4. Sinh snapshot từ môi trường xác định

springdoc thường phục vụ tài liệu ở endpoint **/v3/api-docs** hoặc endpoint group. Gradle plugin có thể khởi chạy Spring Boot, tải endpoint và lưu thành file. Ví dụ:

~~~bash
./gradlew clean test generateOpenApiDocs
~~~

Để snapshot có thể so sánh, hãy kiểm soát:

1. **Spring profile:** dùng profile tài liệu nhất quán và gần với cấu hình production.
2. **API group:** sinh đúng group cần so sánh; không vô tình so sánh public API với admin API.
3. **Server URL:** dùng giá trị ổn định hoặc tách cấu hình theo môi trường có chủ đích.
4. **Dữ liệu động:** không đưa timestamp, random ID hoặc dữ liệu máy build vào schema/example.
5. **Feature flag:** cố định các flag ảnh hưởng endpoint và schema.
6. **Security metadata:** sinh cùng policy bảo mật dự kiến phát hành.
7. **Dependency:** pin phiên bản springdoc và thư viện mô hình để tránh serializer đổi bất ngờ.

Nếu tài liệu có nhiều group, giữ một baseline riêng cho từng API group. Một thay đổi trong group admin không nên làm baseline public API bị ghi đè.

Không cập nhật baseline tự động mỗi khi CI sinh file mới. Baseline chỉ nên thay đổi sau khi semantic diff được review và thay đổi hợp đồng đã được chấp thuận.

## 5. Semantic diff đánh giá điều gì?

Semantic diff parse hai OpenAPI documents và so sánh các thành phần hợp đồng. Tùy công cụ, kết quả có thể chia thành:

- **Breaking:** thay đổi có thể làm client tuân thủ hợp đồng cũ ngừng hoạt động.
- **Potential breaking:** thiếu thông tin để kết luận chắc chắn hoặc cần review theo cách consumer sử dụng API.
- **Non-breaking:** thay đổi không làm mất khả năng sử dụng hợp đồng cũ theo các quy tắc của công cụ.
- **Documentation-only:** thay đổi mô tả, example hoặc metadata không ảnh hưởng wire contract.

Không có một phân loại duy nhất phù hợp mọi tổ chức. Ví dụ, thêm property response thường được xem là tương thích theo hợp đồng, nhưng một client generator hoặc deserializer strict có thể từ chối field chưa biết. Ngược lại, thay đổi mô tả có thể không ảnh hưởng máy nhưng lại thay đổi hướng dẫn nghiệp vụ cho người tích hợp.

Vì vậy, semantic diff nên được xem như bộ phân tích có quy tắc, không phải phán quyết tuyệt đối. Cần đọc report, hiểu consumer và áp dụng policy của API.

## 6. Những thay đổi thường là breaking

Một thay đổi có xu hướng breaking khi request hợp lệ theo baseline cũ không còn hợp lệ theo tài liệu mới, hoặc response mới có thể khiến client cũ không xử lý được.

| Thành phần | Thay đổi | Vì sao có thể breaking |
|---|---|---|
| Path/method | Xóa path hoặc HTTP method | Client gọi operation cũ nhận 404/405 |
| Parameter | Xóa parameter đang được client dùng | Request cũ mất một phần hợp đồng |
| Required request parameter | Thêm parameter bắt buộc | Client cũ không gửi parameter mới |
| Request body | Chuyển body từ optional thành required | Request cũ không có body trở thành không hợp lệ |
| Request schema | Thêm property vào required | Client cũ có thể không gửi property mới |
| Request schema | Thu hẹp enum, min/max, pattern hoặc độ dài | Giá trị từng hợp lệ bị từ chối theo hợp đồng mới |
| Request content | Bỏ media type đang được hỗ trợ | Client cũ gửi content type không còn được chấp nhận |
| Response | Xóa response code hoặc response body schema | Client mất một kết quả đã được công bố |
| Response schema | Xóa property hoặc mở rộng kiểu dữ liệu theo hướng client không xử lý được | Client có thể mất field đang dùng hoặc nhận giá trị ngoài miền cũ |
| Response enum | Thêm giá trị mới | Client dùng enum exhaustive có thể không xử lý được giá trị mới |
| Security | Thêm yêu cầu xác thực hoặc scope | Client cũ không có credential/scope mới sẽ bị từ chối |
| Serialization | Đổi style, explode hoặc format parameter | Client gửi request theo cách cũ có thể bị hiểu khác |

Ví dụ thêm một required request property:

~~~yaml
components:
  schemas:
    CreateOrderRequest:
      type: object
      required:
        - productId
        - quantity
      properties:
        productId:
          type: string
        quantity:
          type: integer
~~~

Nếu baseline chỉ yêu cầu productId nhưng revision thêm quantity vào required, client cũ chỉ gửi productId không còn tuân thủ hợp đồng mới. Server có thể vẫn tự gán quantity mặc định trong implementation, nhưng tài liệu mới đã tuyên bố property là bắt buộc. Gateway, validator hoặc SDK được sinh từ schema mới có thể từ chối request đó.

## 7. Thay đổi thường tương thích nhưng vẫn cần review

Các thay đổi sau thường có thể tương thích, nhưng còn tùy cách consumer và tooling hoạt động:

| Thay đổi | Đánh giá thường gặp | Lý do vẫn cần xem xét |
|---|---|---|
| Thêm path/method mới | Additive | Có thể va chạm operationId hoặc quyền truy cập |
| Thêm query parameter optional | Additive | Một số gateway hoặc client wrapper có quy tắc riêng |
| Thêm optional request property | Additive | Cần xác minh server cũ/mới và serializer |
| Thêm optional response property | Thường additive | Client strict có thể từ chối field lạ |
| Sửa description | Documentation change | Có thể thay đổi hướng dẫn hoặc cam kết nghiệp vụ |
| Thêm example | Documentation change | Có thể làm consumer hiểu sai nếu example không hợp lệ |
| Đổi tag | Thường không đổi wire contract | Làm thay đổi nhóm và thứ tự hiển thị trong UI |
| Đổi operationId | Thường không đổi HTTP behavior | Có thể đổi tên method trong SDK được generate |
| Đổi component schema name | Có thể giữ wire schema | SDK generator có thể đổi tên model công khai |
| Thay server URL | Không đổi schema | Client có thể gọi nhầm host hoặc môi trường |
| Bỏ security requirement | Có thể không chặn client cũ | Có thể làm yếu bảo mật, cần security review |

Một thay đổi không breaking theo wire contract vẫn có thể là breaking đối với SDK, tài liệu vận hành, quy trình deployment hoặc policy bảo mật. Hãy phân biệt compatibility của HTTP contract với compatibility của generated client surface.

## 8. Hướng request và response cần được đánh giá riêng

Schema không chỉ có kiểu dữ liệu; cần xem dữ liệu đi theo hướng nào.

### Request schema

Client gửi request. Khi server thu hẹp tập dữ liệu được chấp nhận, thay đổi có xu hướng breaking:

- Thêm field vào required.
- Bỏ enum value cũ.
- Thêm minimum, maximum, minLength, maxLength hoặc pattern chặt hơn.
- Bỏ media type cũ.
- Đổi nullable thành non-nullable.

Ngược lại, nới constraint hoặc thêm optional property thường mở rộng tập request hợp lệ.

### Response schema

Server gửi response. Khi server thu hẹp tập giá trị có thể trả, thay đổi có thể an toàn cho client cũ, nhưng khi server mở rộng tập giá trị, client cũ có thể gặp dữ liệu chưa xử lý:

- Xóa response property mà client đang đọc: thường breaking.
- Thay response type thành kiểu rộng hơn: client có thể nhận giá trị ngoài khả năng cũ.
- Thêm giá trị enum hoặc nhánh union mới: client exhaustive có thể lỗi.
- Thêm optional response property: thường tương thích, nhưng client strict có thể bị ảnh hưởng.
- Xóa response schema: client mất mô tả payload đã dựa vào.

Đừng chỉ nhìn tên type “rộng” hay “hẹp”. Hãy hỏi: tập request hợp lệ thay đổi theo hướng nào, và tập response server có thể trả thay đổi theo hướng nào? Hai hướng có thể có kết luận compatibility ngược nhau.

## 9. Security, operationId và server URL không phải chi tiết phụ

### Security

Thêm security requirement, thêm OAuth2 scope hoặc đổi scheme có thể làm client cũ không còn gọi được API. Việc bỏ security requirement thường không làm client cũ hỏng, nhưng là thay đổi bảo mật cần được review riêng. Không để một kết quả “non-breaking” che khuất việc endpoint vô tình trở thành public.

### operationId

operationId thường được dùng làm tên method khi sinh SDK. Đổi operationId không nhất thiết thay đổi HTTP request, nhưng có thể làm source code consumer không biên dịch sau khi nâng SDK. Nếu API công bố SDK, hãy coi operationId là một phần của public developer surface.

### Server URL

Đổi servers có thể chuyển client sang host, base path hoặc môi trường khác. Một semantic diff có thể báo server URL thay đổi, nhưng mức độ ảnh hưởng phụ thuộc cách client sử dụng servers và cách cấu hình endpoint. Không loại server URL khỏi snapshot chỉ vì nó khác giữa local và production; hãy chuẩn hóa môi trường hoặc so sánh baseline cùng môi trường.

## 10. Công cụ semantic diff với oasdiff

oasdiff là công cụ dòng lệnh để so sánh OpenAPI documents và phát hiện thay đổi ảnh hưởng consumer. Các lệnh chính có mục đích khác nhau:

| Lệnh | Phạm vi |
|---|---|
| **oasdiff breaking** | Chỉ báo thay đổi có khả năng phá vỡ client cũ |
| **oasdiff changelog** | Báo các thay đổi có thể ảnh hưởng consumer, gồm breaking và non-breaking |
| **oasdiff diff** | Diff đầy đủ của định nghĩa API, kể cả thay đổi documentation-only |
| **oasdiff validate** | Kiểm tra một document theo quy tắc OpenAPI và JSON Schema mà công cụ hỗ trợ |

So sánh baseline và revision:

~~~bash
oasdiff breaking api/openapi-baseline.yaml build/openapi.yaml
oasdiff changelog api/openapi-baseline.yaml build/openapi.yaml
oasdiff diff api/openapi-baseline.yaml build/openapi.yaml
~~~

Lệnh breaking thích hợp để chặn thay đổi không tương thích. Changelog giúp reviewer hiểu toàn bộ thay đổi có thể ảnh hưởng consumer. Diff hữu ích khi cần xem cả mô tả và example.

Để CI thất bại khi có breaking change ở mức ERR:

~~~bash
oasdiff breaking --fail-on ERR api/openapi-baseline.yaml build/openapi.yaml
~~~

Công cụ cũng có thể cấu hình ngưỡng WARN nếu tổ chức muốn chặn cả thay đổi có nguy cơ cần review. Không nên nâng mọi WARN thành lỗi mà chưa hiểu quy tắc và false positive; cũng không nên bỏ qua WARN hàng loạt để pipeline luôn xanh.

## 11. Đọc severity và áp dụng policy

oasdiff phân loại kết quả theo mức độ:

- **ERR:** breaking change rõ ràng theo hợp đồng mà tài liệu khai báo.
- **WARN:** có khả năng breaking nhưng cần thêm ngữ cảnh hoặc thông tin.
- **INFO:** thay đổi được ghi nhận nhưng không bị phân loại là breaking theo rule hiện hành.

Lệnh breaking mặc định tập trung vào ERR và WARN. Có thể dùng **--fail-on ERR** để chỉ chặn lỗi rõ ràng, hoặc **--fail-on WARN** để chặn cả cảnh báo.

Severity là policy của công cụ và cấu hình hiện tại. Nó không thay thế review. Nếu một WARN lặp lại và được xác định an toàn trong kiến trúc của tổ chức, có thể điều chỉnh severity cho rule cụ thể bằng cấu hình công cụ. Hãy ghi lý do và chủ sở hữu quyết định; không hạ mức toàn cục chỉ để bỏ qua một PR.

Tương tự, nếu công cụ báo INFO nhưng thay đổi ảnh hưởng generated SDK hoặc bảo mật, đội API vẫn có thể yêu cầu review thủ công.

## 12. Pipeline CI với snapshot và semantic diff

Một pipeline cơ bản:

~~~bash
# 1. Build, test và sinh OpenAPI từ ứng dụng hiện tại
./gradlew clean test generateOpenApiDocs

# 2. Kiểm tra tài liệu hiện tại
oasdiff validate build/openapi.json

# 3. So sánh với snapshot đã được chấp thuận
oasdiff breaking --fail-on ERR api/openapi-baseline.yaml build/openapi.json

# 4. Xuất changelog cho reviewer
oasdiff changelog api/openapi-baseline.yaml build/openapi.json
~~~

Ví dụ dùng tên file JSON mặc định của Gradle plugin. Nếu cấu hình plugin xuất YAML, đổi đường dẫn theo output thực tế; không đổi đuôi file để giả định định dạng.

Trong pull request, CI nên:

1. Sinh tài liệu từ commit đang kiểm tra.
2. Validate document.
3. So sánh với baseline của nhánh đích hoặc release gần nhất.
4. Lưu report semantic diff làm artifact hoặc PR annotation.
5. Chặn merge khi policy phát hiện breaking change chưa được chấp thuận.
6. Yêu cầu reviewer cập nhật baseline cùng thay đổi có chủ đích.

Đừng so sánh revision với snapshot sinh từ một profile khác. Nếu baseline là public API production, revision cũng cần sinh public API với cấu hình tương đương.

## 13. So sánh trực tiếp với phiên bản trong Git

Một số công cụ semantic diff cho phép dùng Git revision làm một phía của phép so sánh. Với oasdiff, ví dụ:

~~~bash
oasdiff breaking origin/main:api/openapi.yaml build/openapi.yaml
~~~

Cách này tiện cho CI vì baseline được lấy từ nhánh đích, còn revision được sinh từ commit hiện tại. Đảm bảo file ở origin/main là snapshot đã được review, không phải tài liệu được cập nhật tùy tiện.

Nếu nhiều file OpenAPI tương ứng nhiều API độc lập, có thể dùng chế độ so sánh nhiều file của công cụ. Nếu một API được chia thành nhiều file tham chiếu với nhau, phải chọn chế độ compose/resolve phù hợp thay vì coi từng file như một API độc lập.

## 14. Snapshot baseline được cập nhật khi nào?

Baseline là hợp đồng đã được chấp thuận. Không cập nhật chỉ vì build tạo ra diff.

Quy trình cập nhật:

1. Sinh snapshot mới từ cấu hình runtime được thống nhất.
2. Chạy validate và semantic diff.
3. Đọc từng breaking, warning và non-breaking change.
4. Xác nhận thay đổi phản ánh chủ đích API.
5. Kiểm tra consumer, SDK, gateway và tài liệu tích hợp.
6. Nếu breaking, lên kế hoạch versioning, migration hoặc deprecation.
7. Cập nhật baseline trong cùng thay đổi code sau khi review.
8. Ghi release/commit tạo snapshot để có thể truy nguyên.

Không chấp nhận snapshot mới chỉ để làm CI xanh. Nếu cập nhật baseline mà không hiểu diff, pipeline sẽ mất khả năng phát hiện contract regression.

## 15. Versioning và chính sách breaking change

Nếu API dùng Semantic Versioning:

| Loại thay đổi | Cách tăng version thường dùng |
|---|---|
| Breaking change được chấp thuận | Tăng major |
| Tính năng tương thích, thêm operation hoặc optional field | Tăng minor |
| Sửa mô tả hoặc metadata không đổi contract | Tăng patch hoặc chỉ cập nhật tài liệu theo policy |

Đây là quy ước quản lý API, không phải điều OpenAPI tự thực thi. Field info.version là metadata của document; đổi số version không làm thay đổi wire contract. Ngược lại, giữ nguyên info.version không làm một breaking change trở nên an toàn.

Một số công cụ có rule kiểm tra version bump khi phát hiện breaking change. Dù có dùng rule này, đội API vẫn phải review tính tương thích và cách consumer nâng cấp.

## 16. Semantic diff không thay thế contract test runtime

Semantic diff so sánh những gì hai tài liệu công bố. Nó không gửi request tới server và không chứng minh implementation tuân thủ OpenAPI.

Ví dụ:

- Document nói property quantity là integer nhưng controller trả chuỗi.
- OpenAPI khai báo response 404 nhưng runtime luôn trả 200 với body lỗi.
- Tài liệu yêu cầu bearer token nhưng một route bị cấu hình permitAll.
- Server thực tế từ chối một request hợp lệ theo schema do business rule hoặc bug.
- Endpoint tồn tại trong runtime nhưng bị bỏ sót khỏi document.

Kết hợp các lớp kiểm tra:

| Kiểm tra | Câu hỏi |
|---|---|
| OpenAPI validation | Document có hợp lệ theo đặc tả không? |
| Snapshot/semantic diff | Hợp đồng có thay đổi so với baseline không? |
| Provider contract/runtime test | Server có trả request/response phù hợp hợp đồng không? |
| Consumer-driven contract test | Các tương tác mà consumer thực sự cần có được provider đáp ứng không? |
| Integration/security test | Authentication, authorization, error handling và middleware có đúng không? |

OpenAPI semantic diff là kiểm tra provider contract ở cấp tài liệu. Với hệ thống nhiều consumer, consumer-driven contract test có thể bổ sung bằng chứng về các interaction cụ thể mà từng consumer sử dụng.

## 17. Những giới hạn và false positive cần nhận biết

- **Code generation:** thay đổi operationId hoặc component name có thể làm SDK đổi API công khai dù wire contract không đổi.
- **Strict deserializer:** thêm response field có thể ảnh hưởng client từ chối unknown property.
- **Gateway policy:** API gateway có thể validate chặt hơn server, nên thay đổi schema có tác động trước khi request tới controller.
- **Security:** bỏ security requirement có thể được phân loại là không breaking với client, nhưng lại là rủi ro bảo mật.
- **Server URL:** thay host có thể làm consumer gọi sai môi trường.
- **References:** external $ref hoặc schema composition có thể khiến kết quả diff phụ thuộc khả năng resolve và flatten của công cụ.
- **Custom extensions:** vendor extension có thể ảnh hưởng gateway hoặc generator nhưng bị bỏ qua bởi tool không hiểu extension đó.
- **Runtime drift:** document không được sinh từ đúng profile hoặc code có thể không phản ánh endpoint thực tế.

Khi report có cảnh báo do thiếu thông tin, hãy kiểm tra document gốc, resolve reference và thử bằng consumer thật. Đừng chỉ dựa vào nhãn breaking/non-breaking.

## 18. Ví dụ review một thay đổi

Giả sử revision có ba thay đổi:

1. Thêm GET /orders/{id}/events.
2. Thêm required property customerId vào request POST /orders.
3. Sửa description của response 200.

Có thể đánh giá:

| Thay đổi | Phân loại dự kiến | Hành động |
|---|---|---|
| Thêm GET /orders/{id}/events | Additive | Review auth, operationId và response |
| Thêm required customerId | Breaking | Cập nhật client hoặc thiết kế giai đoạn chuyển tiếp |
| Sửa description | Documentation-only | Review nội dung hướng dẫn |

Không nên gom cả ba thành một kết luận “có diff”. Semantic diff giúp reviewer tập trung vào thay đổi hợp đồng có tác động, trong khi full diff vẫn giữ lại các chỉnh sửa mô tả.

## 19. Quy trình thực hành cho nhóm API

Khi thay đổi controller hoặc DTO:

1. Chạy test ứng dụng.
2. Sinh OpenAPI từ profile và group đã thống nhất.
3. Validate document.
4. Chuẩn hóa định dạng nếu cần để giảm nhiễu snapshot.
5. Chạy semantic diff với baseline đã phát hành.
6. Phân loại từng thay đổi theo request, response, security và generated SDK.
7. Chạy runtime/consumer contract tests cho các operation bị ảnh hưởng.
8. Cập nhật version và migration guide nếu cần.
9. Review rồi mới cập nhật baseline.
10. Lưu snapshot cùng report làm artifact của release.

Hãy giữ snapshot nhỏ gọn theo API group và đặt tên rõ release. Một baseline không có nguồn gốc, profile hoặc group xác định sẽ khó dùng để so sánh đáng tin cậy.

## 20. Checklist snapshot và semantic diff

- [ ] Snapshot được sinh từ commit và profile xác định.
- [ ] API group và server URL khớp baseline.
- [ ] Tài liệu được validate trước khi diff.
- [ ] Đã phân biệt canonicalization với semantic comparison.
- [ ] Không sắp xếp hoặc xóa array/field mà không hiểu ngữ nghĩa.
- [ ] Breaking change được phân loại theo hướng request và response.
- [ ] Security requirement và server URL được review riêng.
- [ ] operationId/component name được kiểm tra nếu phát hành SDK.
- [ ] CI so sánh revision với baseline đã review.
- [ ] Ngưỡng ERR/WARN được chọn theo policy rõ ràng.
- [ ] Report được lưu để reviewer kiểm tra.
- [ ] Baseline chỉ cập nhật sau khi diff được chấp thuận.
- [ ] Có runtime/consumer tests bổ sung cho các thay đổi quan trọng.
- [ ] Version bump và migration plan phù hợp nếu có breaking change.

## 21. Tài liệu tham khảo

- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html): cấu trúc và ngữ nghĩa của OpenAPI Description.
- [oasdiff – CLI Quick Start](https://www.oasdiff.com/docs/getting-started): cài đặt, lệnh breaking/changelog/diff/validate và mã thoát dùng trong CI.
- [oasdiff – Breaking Changes](https://github.com/oasdiff/oasdiff/blob/main/docs/BREAKING-CHANGES.md): cách phân loại thay đổi, severity ERR/WARN/INFO và ngưỡng fail-on.
- [oasdiff – Usage Examples](https://github.com/oasdiff/oasdiff/blob/main/docs/USAGE_EXAMPLES.md): ví dụ so sánh file, Git revision, output format và cấu hình.
- [oasdiff – Checking Many Specs Against a Git Ref](https://github.com/oasdiff/oasdiff/blob/main/docs/BREAKING-FILES.md): kiểm tra nhiều tài liệu OpenAPI trong pre-commit/CI.

## Kết luận

Contract snapshot lưu lại OpenAPI Description đã được chấp thuận để làm baseline. Canonicalization giảm nhiễu do cách serialize, còn semantic diff phân tích thay đổi theo path, method, parameter, schema, response và security. Dùng diff văn bản đơn thuần không đủ để kết luận tương thích; cũng không nên tin tuyệt đối một nhãn breaking/non-breaking mà bỏ qua consumer và runtime. Trong CI, hãy sinh tài liệu từ môi trường xác định, validate, chạy semantic diff với baseline đã review, lưu report và chỉ cập nhật snapshot sau khi thay đổi được chấp thuận. Kết hợp kiểm tra tài liệu với provider/consumer contract tests để phát hiện cả contract drift lẫn lỗi implementation.
