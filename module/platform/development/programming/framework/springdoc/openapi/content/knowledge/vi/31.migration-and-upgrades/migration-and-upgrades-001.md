# Lập đặc tả đối chiếu trước khi đổi thư viện hoặc nâng phiên bản

Nâng cấp springdoc-openapi hoặc các thư viện nền có thể làm OpenAPI document thay đổi dù controller và logic nghiệp vụ không đổi. Phiên bản Spring Boot, swagger-core, Jackson, Java và cách tích hợp MVC/WebFlux đều có thể ảnh hưởng đến handler được phát hiện, schema được sinh, annotation được diễn giải hoặc endpoint tài liệu.

Trước khi nâng cấp, hãy lưu một bản OpenAPI baseline từ phiên bản đang phát hành. Sau khi thay dependency và cấu hình, sinh tài liệu mới trong cùng điều kiện, so sánh hai bản và xác định thay đổi nào là do hợp đồng API, thay đổi nào chỉ do cách thư viện sinh tài liệu. Baseline cần gắn với release đã biết, không phải một file tùy ý trên máy phát triển.

Bài này hướng dẫn lập đặc tả đối chiếu trước khi thay đổi thư viện hoặc nâng phiên bản: kiểm kê môi trường và dependency, xuất baseline JSON/YAML, chuẩn hóa cách so sánh, phân loại diff, kiểm tra tương thích, xây dựng kế hoạch migration và đưa các bước xác minh vào CI.

## 1. Vì sao cần baseline trước khi nâng cấp?

springdoc-openapi tạo tài liệu từ Spring application context, handler mapping, annotation, kiểu request/response và cấu hình OpenAPI. Khi nâng springdoc hoặc Spring Boot, kết quả có thể thay đổi ở nhiều lớp:

- Một handler được phát hiện hoặc bị bỏ qua do thay đổi mapping, package scan hoặc điều kiện bean.
- Tên schema, component reference hoặc cách xử lý generic thay đổi.
- Annotation từ swagger-core được diễn giải khác.
- Jackson module, naming strategy hoặc visibility làm thay đổi property trong schema.
- Phiên bản OpenAPI output đổi từ 3.0 sang 3.1 hoặc ngược lại.
- Security scheme, server URL, response content type hoặc operation metadata thay đổi.
- Swagger UI, endpoint JSON/YAML hoặc cấu hình group hoạt động khác.

Nếu không có baseline, nhóm khó biết tài liệu mới có làm mất endpoint hoặc thay đổi hợp đồng đã phát hành hay không. Một file OpenAPI được tạo thành công chỉ chứng minh quá trình export chạy được; nó không chứng minh contract vẫn tương thích.

Baseline giúp trả lời ba câu hỏi:
1. Tài liệu trước nâng cấp đã công bố những gì?
2. Tài liệu sau nâng cấp thay đổi chính xác ở đâu?
3. Mỗi thay đổi có ảnh hưởng tới consumer, generated SDK hoặc runtime behavior không?

## 2. Xác định phạm vi nâng cấp trước khi thay đổi

Trước tiên, ghi rõ mục tiêu migration. Không gộp nhiều thay đổi độc lập vào một lần nâng cấp nếu không cần thiết.

Ví dụ các phạm vi thường gặp:

| Phạm vi | Thành phần thay đổi | Rủi ro cần kiểm tra |
|---|---|---|
| Nâng springdoc patch | Dependency springdoc cùng major line | Bug fix, cấu hình và output thay đổi |
| Nâng springdoc major | Artifact, API cấu hình hoặc swagger-core đi kèm | Breaking API, annotation và schema generation |
| Nâng Spring Boot | Framework, auto-configuration, Spring MVC/WebFlux | Handler mapping, security, Jackson và Jakarta |
| Nâng Java | JDK, compiler và runtime | Source compatibility, reflection, build plugin |
| Chuyển MVC sang WebFlux hoặc ngược lại | Web stack và starter | Handler discovery, functional routes, runtime behavior |
| Đổi OpenAPI 3.0 sang 3.1 | Phiên bản đặc tả và schema dialect | nullable, JSON Schema keywords và toolchain |
| Nâng Swagger UI | UI assets và configuration | URL document, authorize, rendering và Try it out |

Hãy ghi rõ thành phần nào được phép thay đổi và thành phần nào cần giữ nguyên. Nếu cùng lúc nâng Java, Spring Boot, springdoc, Jackson và OpenAPI version, khi diff xuất hiện thay đổi sẽ khó xác định nguyên nhân.

Một kế hoạch dễ kiểm soát thường chia migration lớn thành các bước nhỏ: trước tiên nâng dependency tương thích trong stack hiện tại, sau đó nâng Spring Boot hoặc Java, cuối cùng mới thay đổi OpenAPI dialect nếu có yêu cầu.

## 3. Kiểm kê môi trường và dependency hiện tại

Baseline phải đi kèm thông tin về môi trường đã tạo ra nó. Tối thiểu cần ghi:

| Nhóm | Thông tin cần lưu |
|---|---|
| Runtime | Java vendor/version, JVM options, OS hoặc container image |
| Framework | Spring Boot, Spring Framework, Spring Security |
| Web stack | Spring MVC hoặc WebFlux |
| OpenAPI | springdoc artifact/version, OpenAPI output version |
| Swagger | swagger-core/annotations và Swagger UI version gián tiếp |
| Serialization | Jackson core/databind/module và cấu hình liên quan |
| Build | Maven/Gradle wrapper và plugin version |
| Configuration | Active Spring profiles, context path, API-docs path |
| Application | Git commit, release tag, service build/version |
| Documents | Default document và từng GroupedOpenApi |

Không chỉ ghi version trong build file. Dependency transitive có thể khác với version được khai báo trực tiếp. Hãy lưu dependency tree hoặc dependency lock để có thể giải thích thay đổi sau này.

Với Maven:

~~~bash
mvn -version
mvn dependency:tree -Dincludes=org.springdoc,io.swagger.core.v3
~~~

Với Gradle:

~~~bash
./gradlew --version
./gradlew dependencyInsight --dependency springdoc --configuration runtimeClasspath
./gradlew dependencyInsight --dependency swagger-core --configuration runtimeClasspath
~~~

Nếu dự án có nhiều module, chạy lệnh trong đúng module tạo OpenAPI document. Dependency tree của module gốc có thể không phản ánh runtime classpath của service.

## 4. Kiểm tra ma trận tương thích trước khi chọn version đích

Không chọn version springdoc chỉ dựa vào số version mới nhất. Hãy đối chiếu release notes và compatibility matrix của phiên bản cụ thể.

Các điều kiện cần kiểm tra:

- Spring Boot version được hỗ trợ.
- Java baseline và JDK dùng để build.
- MVC hay WebFlux.
- Spring Framework và Spring Security được quản lý theo Spring Boot BOM.
- Jakarta namespace hay javax namespace.
- swagger-core và swagger-annotations đi kèm.
- Jackson version và module tương thích.
- Maven/Gradle plugin và native/AOT support nếu ứng dụng dùng.
- Các starter hoặc module bổ sung mà dự án đang sử dụng.

Một số major migration có thay đổi artifact coordinates. Ví dụ, trong migration từ springdoc 1.x sang 2.x cho Spring Boot 3, starter thường dùng tên riêng cho MVC hoặc WebFlux:

| Web stack | Artifact starter của springdoc 2.x |
|---|---|
| Spring MVC | org.springdoc:springdoc-openapi-starter-webmvc-ui |
| Spring WebFlux | org.springdoc:springdoc-openapi-starter-webflux-ui |

Dự án cũ có thể dùng artifact như `springdoc-openapi-ui`. Không giữ đồng thời starter mới và artifact cũ nếu chúng cung cấp các thành phần cấu hình trùng nhau. Chọn đúng starter theo web stack và kiểm tra hướng dẫn migration của target release.

Spring Boot 3 cũng là migration lớn của hệ sinh thái Jakarta, không chỉ là đổi springdoc dependency. Các API Java EE chuyển từ namespace `javax.*` sang `jakarta.*` ở nhiều vùng, và Spring Boot 3 yêu cầu Java baseline mới hơn Spring Boot 2. Nếu ứng dụng đang ở Spring Boot 2, hãy lập riêng checklist cho Boot migration, source imports, validation, servlet container, security và thư viện bên thứ ba.

Không tự ép một version swagger-core hoặc Jackson riêng để xử lý lỗi compile trước khi kiểm tra dependency management. Spring Boot BOM và springdoc starter thường cần một tập version tương thích. Override một dependency transitive có thể làm schema generation hoặc serialization lỗi ở runtime.

## 5. Chụp baseline từ phiên bản đang phát hành

Tạo baseline từ build/release được xác nhận là đang chạy hoặc đã phát hành. Không lấy tài liệu từ một nhánh chưa merge làm chuẩn nếu mục tiêu là bảo vệ consumer production.

Với endpoint mặc định của springdoc:

~~~bash
curl -fsS https://api.example.com/v3/api-docs -o openapi-baseline.json
curl -fsS https://api.example.com/v3/api-docs.yaml -o openapi-baseline.yaml
~~~

Nếu API docs có xác thực, dùng credential được cấp cho quy trình export và không ghi token vào log. Nếu tài liệu chỉ được xuất trong pipeline, tải artifact OpenAPI của release tương ứng thay vì gọi production.

Với GroupedOpenApi, lưu từng document group riêng:

~~~bash
curl -fsS https://api.example.com/v3/api-docs/public -o openapi-public-baseline.json
curl -fsS https://api.example.com/v3/api-docs/partner -o openapi-partner-baseline.json
~~~

Không chỉ lưu document mặc định nếu consumer sử dụng các group khác nhau. Tên group, URL và artifact cần được ánh xạ rõ ràng.

Baseline nên bất biến và có provenance:
- Release tag hoặc commit đã tạo tài liệu.
- Service version và thời điểm export.
- Java, Spring Boot, springdoc và OpenAPI version.
- Active profile và cấu hình group.
- URL hoặc tên document group.
- Hash của file để xác nhận tính toàn vẹn.

Ví dụ tạo checksum:

~~~bash
sha256sum openapi-baseline.json
~~~

Có thể lưu checksum trong metadata release hoặc artifact manifest. Không chỉnh sửa baseline bằng tay sau khi phát hành; nếu cần sửa tài liệu, hãy tạo release artifact mới có lịch sử rõ ràng.

## 6. Làm cho hai lần export có thể so sánh

Để biết diff đến từ dependency, hãy giữ điều kiện export nhất quán.

Cần giữ giống nhau:
- Source code ứng dụng, ngoại trừ thay đổi migration đang kiểm tra.
- Active Spring profile.
- Các property springdoc và cấu hình OpenAPI.
- Group và endpoint được export.
- Context path và server URL.
- Jackson naming strategy, module và serializer.
- Security configuration và customizer.
- Dữ liệu cấu hình mà customizer dùng để tạo metadata.

Nếu tài liệu được tạo ở hai môi trường khác nhau, server URL hoặc info.version có thể thay đổi dù hợp đồng operation không đổi. Ghi nhận các trường có chủ đích phụ thuộc môi trường và phân biệt chúng với contract change.

Tránh để tài liệu phụ thuộc dữ liệu runtime không ổn định như timestamp hiện tại, host ngẫu nhiên, tenant đang đăng nhập hoặc thứ tự lấy dữ liệu từ collection không xác định. OpenAPI document thường nên là artifact ổn định của một build và một document group.

Nếu có customizer tạo metadata theo request hoặc profile, hãy kiểm tra nó có làm output khác nhau giữa hai lần export không. Không loại bỏ mọi khác biệt tự động; một server URL mới hoặc security scheme đổi có thể là thay đổi thực sự cần review.

## 7. Xuất tài liệu mới sau khi nâng cấp

Sau khi cập nhật dependency và cấu hình, build ứng dụng trong môi trường tương đương baseline. Khởi động application với profile export đã xác định rồi tải các document tương ứng.

Ví dụ:

Đoạn lệnh Maven dưới đây giả định lifecycle đã được cấu hình để khởi động ứng dụng, hoặc ứng dụng đã được CI khởi động ở bước trước. Lệnh build không tự mở một HTTP server nếu dự án chưa cấu hình plugin start; chỉ gọi endpoint export sau khi ứng dụng đã sẵn sàng.

~~~bash
mvn -B clean verify
curl -fsS http://localhost:8080/v3/api-docs -o openapi-current.json
curl -fsS http://localhost:8080/v3/api-docs.yaml -o openapi-current.yaml
~~~

Nếu chạy bằng Gradle:

~~~bash
./gradlew clean test bootJar
~~~

Các task Gradle trên build và kiểm thử artifact; pipeline vẫn cần một bước khởi động ứng dụng riêng trước khi gọi endpoint OpenAPI.

Khởi động ứng dụng theo profile CI, đợi endpoint docs sẵn sàng, sau đó export document. Đừng gọi endpoint trước khi application context hoàn tất khởi động.

Tạo cùng danh sách artifact như baseline:
- Default document.
- Public/partner/internal groups nếu có.
- JSON hoặc YAML theo định dạng được phát hành.
- OpenAPI 3.0 hoặc 3.1 theo chính sách hiện tại.

Nếu target migration chủ đích đổi OpenAPI dialect, lưu rõ đó là một thay đổi riêng. Diff giữa 3.0 và 3.1 có thể chứa nhiều thay đổi cú pháp như nullable và exclusive bounds; đừng trộn chúng với thay đổi endpoint trong một báo cáo không phân loại.

## 8. Chuẩn hóa trước khi so sánh

JSON object không phụ thuộc thứ tự key, vì vậy hai file có thể khác textual diff nhưng biểu diễn cùng dữ liệu. Có thể sắp xếp key để giảm nhiễu:

~~~bash
jq -S . openapi-baseline.json > openapi-baseline.sorted.json
jq -S . openapi-current.json > openapi-current.sorted.json
diff -u openapi-baseline.sorted.json openapi-current.sorted.json
~~~

Không tự sắp xếp mọi array. Thứ tự trong servers, tags, security, oneOf, anyOf, examples hoặc các danh sách khác có thể có ý nghĩa đối với cách hiển thị, lựa chọn hoặc generator. Chỉ chuẩn hóa array khi đã hiểu semantics và có quy ước rõ.

Một số trường có thể biến động giữa môi trường như server URL hoặc metadata build. Nếu cần bỏ chúng khỏi so sánh, hãy tạo một bản normalized để phân tích, đồng thời vẫn giữ artifact gốc. Quy tắc normalization phải:
- Được review và lưu trong repository.
- Chỉ loại trường đã xác định là không thuộc contract cần kiểm tra.
- Không xóa path, method, schema, security hoặc response để làm diff sạch hơn.
- Không ghi đè baseline hay current artifact gốc.

Raw diff hữu ích để tìm thay đổi cụ thể, nhưng không thay thế semantic OpenAPI diff. Hãy dùng validator để xác nhận tài liệu hợp lệ và công cụ diff để phân loại thay đổi theo cấu trúc OpenAPI.

## 9. So sánh semantic bằng công cụ OpenAPI diff

Có thể dùng oasdiff để phát hiện thay đổi hợp đồng giữa baseline và current:

~~~bash
oasdiff diff openapi-baseline.json openapi-current.json
oasdiff breaking openapi-baseline.json openapi-current.json
~~~

Thứ tự đối số phải nhất quán: tài liệu đã phát hành trước, tài liệu sau nâng cấp ở vị trí current. Pin version của công cụ trong CI vì rule set có thể thay đổi theo phiên bản.

Một công cụ diff có thể phát hiện nhiều thay đổi cấu trúc như:
- Xóa path hoặc operation.
- Đổi parameter hoặc thêm required parameter.
- Thay request/response schema.
- Đổi kiểu, required, enum hoặc constraint.
- Xóa response code hoặc media type.
- Thay đổi security requirement.
- Đổi operationId hoặc component reference tùy rule set.

Hãy đọc report thay vì chỉ nhìn exit code. Tool có thể phân loại một thay đổi là breaking theo quy tắc chung, trong khi dự án có bằng chứng consumer không dùng phần đó; hoặc tool không biết behavioral change do code runtime tạo ra.

Không tắt toàn bộ rule vì một khác biệt không liên quan. Nếu cần ngoại lệ, ghi rõ path, operation, rule và lý do, giới hạn theo thời gian và yêu cầu review.

## 10. Kiểm tra những vùng contract quan trọng

Khi review diff, đi theo các vùng sau:

| Vùng | Nội dung cần đối chiếu |
|---|---|
| Paths | Path cũ có còn không? Có đổi base path hoặc version prefix không? |
| Operations | HTTP method, operationId, tags và deprecation có đổi không? |
| Parameters | Tên, location, required, type, style, explode và constraints |
| Request body | Required, media type, schema, nullable và additionalProperties |
| Responses | Status code, content type, headers và response schema |
| Components | Schema name, $ref, enum, discriminator và composition |
| Security | Scheme, scopes, operation-level requirements |
| Servers | Base URL, server variables và môi trường |
| Metadata | OpenAPI version, info.version, external docs và license |

Một thay đổi có thể chỉ tác động generated SDK chứ không đổi wire format. Ví dụ đổi operationId có thể làm tên method trong SDK thay đổi. Vì vậy, nếu dự án phân phối SDK, cần chạy generator và compile consumer fixture để kiểm tra source compatibility.

Nếu chỉ nhìn số path hoặc dung lượng file, có thể bỏ sót thay đổi lớn. Một response property bị đổi kiểu có thể không làm kích thước tài liệu thay đổi đáng kể nhưng vẫn phá client.

## 11. Phân loại khác biệt do thư viện và khác biệt do hợp đồng

Sau khi nâng springdoc, có thể gặp diff dù code controller không thay đổi. Hãy điều tra nguyên nhân trước khi sửa annotation hoặc chấp nhận diff.

Các nguồn thay đổi thường gặp:

| Dấu hiệu | Nguyên nhân có thể | Cách xác minh |
|---|---|---|
| Schema name thay đổi | swagger-core naming/resolution thay đổi | So sánh component key và $ref |
| Property bị thêm/bớt | Jackson version, visibility hoặc annotation | Kiểm tra JSON serialization và DTO |
| Response code khác | Annotation resolution hoặc Spring mapping | Kiểm tra controller annotation và runtime response |
| Operation biến mất | Package/path scan hoặc handler mapping | Kiểm tra Spring handler mapping và springdoc filter |
| Security thay đổi | Security configuration hoặc annotation processing | So sánh SecurityFilterChain và OpenAPI security |
| OpenAPI dialect đổi | Cấu hình version hoặc default mới | Kiểm tra trường openapi và property |
| Server URL đổi | Proxy, forwarded header hoặc profile | So sánh environment và forwarded headers |
| UI không tải document | UI config, path hoặc reverse proxy | Kiểm tra Network và endpoint docs |

Không nên sửa diff bằng cách thêm annotation hàng loạt trước khi xác định nguyên nhân. Một số thay đổi có thể là bug fix của thư viện hoặc sửa lỗi hợp đồng cũ. Hãy so sánh output, source mapping và response runtime để chọn cách xử lý.

## 12. Kiểm tra dependency và loại bỏ xung đột

Sau khi đổi starter, kiểm tra runtime classpath để chắc chắn chỉ có một bộ dependency phù hợp.

Với Maven:

~~~bash
mvn dependency:tree -Dverbose -Dincludes=org.springdoc,io.swagger.core.v3
~~~

Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency swagger-annotations --configuration runtimeClasspath
~~~

Kiểm tra:
- Không còn artifact cũ trùng chức năng với starter mới.
- Không có hai web stack starter ngoài ý muốn.
- swagger-core và swagger-annotations được resolve theo dependency management phù hợp.
- Không có version override cũ được giữ lại chỉ để build pass.
- Jackson module và Spring Boot BOM nhất quán.
- Không có dependency bị loại bởi exclusion khiến class thiếu ở runtime.

Nếu ứng dụng dùng cả MVC và WebFlux dependency vì một thư viện khác, xác định stack nào thực sự phục vụ endpoint. Chọn starter springdoc phù hợp với runtime web application; không thêm cả hai starter để thử xem cái nào hoạt động.

Sau khi dependency tree ổn định, chạy compile, test và khởi động ứng dụng thật. Compile pass chưa đủ để xác nhận Swagger UI và /v3/api-docs hoạt động.

## 13. Kiểm tra hành vi runtime sau nâng cấp

Bên cạnh diff, chạy một bộ kiểm tra trực tiếp trên ứng dụng:

1. Application context khởi động thành công.
2. /v3/api-docs trả JSON OpenAPI hợp lệ.
3. /v3/api-docs.yaml trả YAML nếu dự án công bố YAML.
4. Mỗi document group được tải đúng.
5. Swagger UI tải đúng document và render operation.
6. Try it out gọi đúng server trong môi trường test.
7. Authentication và authorization giữ nguyên hành vi.
8. Controller/functional route quan trọng vẫn được đăng ký.
9. Request/response serialization thực tế khớp schema.
10. Native image/AOT test pass nếu ứng dụng có phát hành native executable.

Kiểm tra một số operation đại diện:
- Một GET có path parameter.
- Một POST có request body và validation.
- Một endpoint có security requirement.
- Một response có enum hoặc generic wrapper.
- Một error response như 400, 401, 403 hoặc 404.
- Một route thuộc từng document group.

Không chỉ kiểm tra tài liệu có chứa path. Gọi endpoint trong môi trường test để xác nhận runtime mapping và response thực tế.

## 14. Kiểm tra OpenAPI 3.0/3.1 nếu migration thay đổi dialect

Nếu nâng cấp đồng thời chuyển OpenAPI version, review riêng các khác biệt schema:

| Nội dung | OpenAPI 3.0 | OpenAPI 3.1 |
|---|---|---|
| Nullability | nullable: true | type có thể chứa null |
| exclusiveMinimum | Boolean kết hợp với minimum | Giá trị ngưỡng số |
| exclusiveMaximum | Boolean kết hợp với maximum | Giá trị ngưỡng số |
| Schema dialect | Tập Schema Object riêng | Tích hợp JSON Schema 2020-12 |
| Keyword mới | Giới hạn theo OAS 3.0 | Nhiều JSON Schema keyword hơn |

Ví dụ cùng một property nullable:

~~~yaml
# OpenAPI 3.0
description:
  type: string
  nullable: true
~~~

~~~yaml
# OpenAPI 3.1
description:
  type: [string, 'null']
~~~

Không chuyển đổi tự động bằng cách chỉ đổi trường openapi. Hãy kiểm tra schema, validator, API gateway, documentation portal và code generator có hỗ trợ dialect mới không.

Nếu chỉ nâng springdoc mà chưa muốn đổi dialect, giữ cấu hình OpenAPI version rõ ràng và xác nhận output sau upgrade. Điều này giúp tách tác động của thư viện khỏi tác động của chuẩn đặc tả.

## 15. Lập bảng đối chiếu và quyết định migration

Một bảng migration giúp review có căn cứ:

| Thành phần | Baseline | Sau nâng cấp | Phân loại | Hành động |
|---|---|---|---|---|
| GET /api/orders/{id} | Có | Có | Không đổi | Giữ |
| POST /api/orders request | customerId required | Thêm source required | Breaking | Sửa contract hoặc version |
| OrderResponse.total | number | string | Breaking | Khôi phục type hoặc major |
| OrderStatus response enum | NEW, PAID | Thêm REFUNDED | Có thể breaking | Kiểm tra consumer strict |
| Security scope | orders:read | orders:read | Không đổi | Giữ |
| Swagger UI URL | /swagger-ui.html | /swagger-ui/index.html | Deployment/UI change | Cập nhật link nếu chủ đích |
| OpenAPI dialect | 3.0.3 | 3.1.0 | Specification migration | Validate toolchain |

Phân loại nên có ít nhất:
- **No change:** không khác biệt có ý nghĩa.
- **Documentation-only:** description, summary hoặc example thay đổi.
- **Additive:** thêm operation hoặc optional input, cần xét client strict.
- **Potentially breaking:** response enum, unknown property, operationId hoặc behavior phụ thuộc generator.
- **Breaking:** request cũ không còn hợp lệ, response cũ không còn được bảo đảm hoặc route/security cũ bị thay.
- **Runtime-only:** code behavior đổi nhưng OpenAPI document không thể hiện.

Mỗi dòng cần có người review và quyết định. Không để một diff report lớn mà không có mapping từ rule sang hành động.

## 16. Tổ chức migration theo từng bước và có rollback

Một quy trình nâng cấp có thể chia thành các giai đoạn:

1. **Freeze baseline:** lưu OpenAPI artifact và dependency inventory của release hiện tại.
2. **Review compatibility:** kiểm tra release notes, Spring Boot/Java matrix và artifact coordinates.
3. **Update dependencies:** đổi starter và loại dependency trùng lặp.
4. **Build and start:** chạy compile, test và khởi động ứng dụng bằng profile chuẩn.
5. **Export current docs:** xuất JSON/YAML cho tất cả group.
6. **Diff and classify:** semantic diff, raw diff và review thủ công.
7. **Runtime validation:** smoke test Swagger UI, API operation và security.
8. **Consumer validation:** chạy contract test và compile SDK fixture nếu có.
9. **Release decision:** phê duyệt breaking changes, version và migration plan.
10. **Deploy and monitor:** theo dõi lỗi client, 4xx/5xx, usage endpoint cũ và tài liệu được phân phối.

Giữ artifact cũ, dependency lock và build configuration của release trước để rollback có thể tái lập. Nếu migration có database hoặc API behavior change đi kèm, rollback cần xem xét cả dữ liệu và consumer traffic; đổi lại dependency không tự hoàn tác những thay đổi runtime khác.

Không publish tài liệu mới cho consumer trước khi review hoàn tất. Artifact mới cần gắn với cùng release của server để client không sinh SDK từ hợp đồng chưa được triển khai.

## 17. Đưa baseline và diff vào CI

CI nên tạo tài liệu cho mỗi build và so sánh với baseline được chọn theo policy. Ví dụ:

~~~mermaid
flowchart TD
    A[Checkout release baseline] --> B[Build current application]
    B --> C[Start with export profile]
    C --> D[Export JSON/YAML per group]
    D --> E[Validate OpenAPI documents]
    E --> F[Compare semantic diff]
    F --> G[Review breaking and potential changes]
    G --> H[Run API and SDK contract tests]
    H --> I[Store artifacts and report]
    I --> J[Approve release]
~~~

Một đoạn lệnh tối giản:

~~~bash
# Export tài liệu hiện tại
curl -fsS http://localhost:8080/v3/api-docs -o openapi-current.json

# Kiểm tra khác biệt với artifact đã phát hành
oasdiff breaking openapi-baseline.json openapi-current.json

# Lưu diff để reviewer kiểm tra
oasdiff diff openapi-baseline.json openapi-current.json > openapi-diff.txt
~~~

Pipeline thực tế cần:
- Pin version validator và diff tool.
- Tải baseline theo release tag hoặc artifact ID đã xác định.
- Không dùng file baseline được tạo từ chính build hiện tại.
- Kiểm tra tất cả document group.
- Giữ file OpenAPI current, baseline và diff report như build artifacts.
- Fail khi có breaking change chưa được phê duyệt.
- Cho phép ngoại lệ hẹp, có lý do, người phê duyệt và thời hạn.
- Chạy contract tests sau khi diff được đánh giá.

Nếu baseline chưa tồn tại cho một service mới, tạo baseline đầu tiên từ release được phê duyệt và lưu provenance. Không âm thầm coi tài liệu của pull request đầu tiên là chuẩn đã phát hành.

## 18. Checklist trước khi hoàn tất nâng cấp

- [ ] Đã ghi rõ phạm vi migration và thành phần thay đổi.
- [ ] Đã lưu dependency inventory, Java và Spring Boot version.
- [ ] Đã xác minh compatibility matrix của springdoc target.
- [ ] Đã chọn đúng MVC hoặc WebFlux starter.
- [ ] Đã loại dependency cũ hoặc trùng lặp.
- [ ] Đã lưu OpenAPI baseline từ release đã phát hành.
- [ ] Đã lưu tất cả document group đang được consumer sử dụng.
- [ ] Đã ghi provenance và checksum của baseline.
- [ ] Hai lần export dùng cùng profile và cấu hình.
- [ ] Đã xuất OpenAPI JSON/YAML sau nâng cấp.
- [ ] Đã validate document và so sánh semantic diff.
- [ ] Đã review path, method, parameter, request/response schema và security.
- [ ] Đã kiểm tra operationId/schema name nếu có generated SDK.
- [ ] Đã kiểm tra Swagger UI và endpoint tài liệu.
- [ ] Đã chạy API smoke test, contract test và SDK compile test phù hợp.
- [ ] Đã tách thay đổi OpenAPI 3.0/3.1 khỏi thay đổi thư viện nếu có thể.
- [ ] Mọi breaking change có version plan, migration và phê duyệt.
- [ ] Baseline, current document và diff report được lưu cùng build.
- [ ] Có phương án rollback và theo dõi sau deploy.

## Tài liệu tham khảo

- [springdoc-openapi – Documentation](https://springdoc.org/): cấu hình, starter, OpenAPI endpoint và hướng dẫn theo phiên bản.
- [springdoc-openapi – Migration guide](https://springdoc.org/): hướng dẫn chuyển đổi artifact và cấu hình giữa các major release.
- [Spring Boot – Dependency Management](https://docs.spring.io/spring-boot/reference/using/build-systems.html): quản lý dependency và build system.
- [Spring Boot – Supported Versions](https://spring.io/projects/spring-boot#support): thông tin vòng đời và các dòng Spring Boot.
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html): cấu trúc hợp đồng OpenAPI.
- [oasdiff](https://github.com/Tufin/oasdiff): semantic diff và phát hiện breaking changes.
- [Semantic Versioning](https://semver.org/): quy ước major, minor và patch version.
