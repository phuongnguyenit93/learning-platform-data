# Tách lỗi tương thích thư viện khỏi thay đổi hợp đồng API có chủ ý

Khi nâng cấp Spring Boot, Spring Framework, springdoc-openapi hoặc một thư viện nền tảng khác, ứng dụng có thể xuất hiện lỗi build, lỗi khởi động, lỗi runtime hoặc thay đổi OpenAPI document. Không phải mọi khác biệt đều có cùng nguyên nhân. Một lỗi do dependency không tương thích là vấn đề của nền tảng triển khai; một thay đổi hợp đồng API có chủ ý là quyết định sản phẩm ảnh hưởng đến consumer.

Hai nhóm vấn đề cần được kiểm tra độc lập. Dependency có thể không tương thích dù HTTP contract không đổi, ví dụ ứng dụng không khởi động vì NoSuchMethodError. Ngược lại, tất cả dependency có thể tương thích và ứng dụng vẫn chạy bình thường, nhưng OpenAPI document thay đổi theo hướng breaking, ví dụ một request property từ optional thành required.

Quy trình điều tra tốt phải xác định lớp lỗi trước, so sánh dependency graph và OpenAPI contract, tái hiện hành vi runtime, rồi mới quyết định sửa dependency hay phát hành phiên bản API mới. Không nên che một lỗi linkage bằng cách đổi contract, cũng không nên xem mọi thay đổi trong OpenAPI document là lỗi thư viện.

## 1. Phân biệt hai trục tương thích

Tương thích thư viện và tương thích hợp đồng API là hai câu hỏi khác nhau:

| Trục | Câu hỏi cần trả lời | Bằng chứng chính |
|---|---|---|
| Library compatibility | Các thành phần Java/Spring có thể compile, link và chạy cùng nhau không? | Dependency graph, compiler, classpath, startup log, runtime tests |
| API contract compatibility | Client cũ có tiếp tục gửi request và hiểu response như trước không? | OpenAPI JSON/YAML, HTTP behavior, consumer contract tests |

Có thể gặp bốn tình huống:

| Thư viện | HTTP contract | Ví dụ |
|---|---|---|
| Tương thích | Không đổi | Nâng patch dependency, build và contract đều ổn |
| Không tương thích | Không đổi về thiết kế | Ứng dụng lỗi linkage trước khi phục vụ request |
| Tương thích | Có thay đổi | Controller chạy bình thường nhưng schema hoặc response thay đổi |
| Không tương thích | Có thay đổi | Nâng nền tảng gây lỗi runtime, đồng thời document mới làm client cũ không dùng được |

Đừng dùng một kết quả duy nhất để kết luận cả hai trục. Build thành công không chứng minh contract ổn định; OpenAPI diff không chứng minh dependency graph tương thích.

## 2. Phân biệt source, binary, runtime và behavioral compatibility

Từ “tương thích thư viện” có nhiều mức:

| Mức | Ý nghĩa | Dấu hiệu lỗi thường gặp |
|---|---|---|
| Source compatibility | Source cũ vẫn compile với dependency mới | Import không tồn tại, method signature thay đổi |
| Binary compatibility | Class đã biên dịch vẫn link với thư viện mới | NoSuchMethodError, NoSuchFieldError, AbstractMethodError |
| Runtime compatibility | Ứng dụng khởi động và các thành phần tích hợp hoạt động | Auto-configuration lỗi, bean thiếu, class loading failure |
| Behavioral compatibility | Hành vi khi chạy giữ được semantics mong đợi | Serialization khác, validation khác, converter chọn khác |

Một thư viện có thể giữ binary compatibility nhưng thay đổi hành vi mặc định. Ví dụ, một bản nâng Jackson vẫn có thể giữ method API nhưng cấu hình naming/serialization của ứng dụng thay đổi do module hoặc ObjectMapper khác.

Ngược lại, source code có thể phải sửa import sau một major release dù HTTP contract được giữ nguyên. Đó là migration ở lớp implementation, không nhất thiết là API version change.

## 3. Nhận diện lỗi tương thích dependency qua triệu chứng

Các lỗi sau thường hướng đến dependency hoặc classpath:

| Triệu chứng | Ý nghĩa thường gặp | Bước kiểm tra đầu tiên |
|---|---|---|
| package ... does not exist | Source đang import package không có trong compile classpath | Dependency version và API reference |
| cannot find symbol | Class/method/field không có hoặc signature đã đổi | Javadoc và dependency đã resolve |
| ClassNotFoundException | Code yêu cầu nạp class nhưng classloader không tìm thấy | Runtime classpath và artifact đóng gói |
| NoClassDefFoundError | Class cần thiết không thể được định nghĩa/nạp lúc runtime | Dependency bị thiếu hoặc lỗi khởi tạo class trước đó |
| NoSuchMethodError | Bytecode gọi method không tồn tại trong class được nạp | Phiên bản class ở runtime |
| NoSuchFieldError | Bytecode tham chiếu field không có trong class runtime | Dependency conflict hoặc binary mismatch |
| AbstractMethodError | Implementation runtime không đáp ứng method abstract mà caller yêu cầu | Các phiên bản interface/implementation |
| IncompatibleClassChangeError | Cấu trúc class/interface thay đổi không tương thích | Major version và class origin |
| Lỗi tạo ApplicationContext | Auto-configuration hoặc bean integration không tương thích | Condition report, stack trace và dependency graph |

Tên lỗi là manh mối, không phải kết luận cuối. NoClassDefFoundError đôi khi xuất hiện sau một lỗi khởi tạo class trước đó; cần đọc nguyên nhân gốc đầu tiên trong log.

## 4. Nhận diện thay đổi hợp đồng API

Thay đổi contract thường thể hiện ở một hoặc nhiều yếu tố:

- Path hoặc HTTP method bị xóa/đổi.
- Tên, vị trí hoặc kiểu parameter thay đổi.
- Request property bắt buộc mới xuất hiện.
- Response property bị xóa hoặc đổi kiểu.
- Enum response bị loại giá trị hoặc xuất hiện giá trị mới mà client cũ không xử lý được.
- Status code hoặc media type thay đổi.
- Security requirement mới được áp dụng.
- Cách phân trang, sorting, filtering hoặc idempotency thay đổi.
- Response error chuyển sang schema khác.

Ứng dụng có thể compile và khởi động bình thường trong mọi trường hợp trên. Consumer vẫn có thể hỏng vì request cũ không còn hợp lệ hoặc parser không hiểu response mới.

## 5. Phân biệt thay đổi implementation với thay đổi contract

Không phải thay đổi source nào cũng là thay đổi API.

| Thay đổi trong source | Có thể giữ contract không? | Cần xác minh |
|---|---|---|
| Đổi tên method Java nhưng giữ mapping | Có | Path, operationId và customizer |
| Tách controller thành nhiều class | Có | Mapping, tags, groups và security |
| Đổi package DTO nhưng JSON giữ nguyên | Có | Jackson output và schema |
| Nâng springdoc nhưng giữ controller | Có, nhưng schema generation có thể đổi | OpenAPI diff |
| Đổi tên JSON property | Thường là breaking | Request/response payload |
| Đổi query parameter name | Thường là breaking | Request mapping và OpenAPI |
| Thêm response field optional | Thường additive, nhưng cần kiểm tra client strict | Consumer parser và schema |
| Thêm request field required | Breaking với client cũ | Request schema và validation |
| Thay authentication scheme | Có thể breaking | Security requirement và gateway |

Điểm quan trọng là so sánh biểu hiện trên wire: HTTP request/response và OpenAPI document. Không lấy diff source code làm đại diện cho diff contract.

## 6. Ví dụ: nâng springdoc làm thay đổi document nhưng dependency vẫn tương thích

Giả sử ứng dụng nâng springdoc trong cùng major version. Maven/Gradle resolve thành công, ứng dụng khởi động, endpoint /v3/api-docs trả 200. Hai document trong ví dụ đều dùng OpenAPI 3.0, nhưng một schema property đổi từ:

~~~yaml
status:
  type: string
  nullable: true
~~~

sang:

~~~yaml
status:
  type: string
~~~

Đây có thể là thay đổi do cách thư viện suy luận nullability hoặc Jackson metadata. Dependency vẫn có thể tương thích về source/binary/runtime, nhưng contract được sinh ra đã thay đổi. Nếu đồng thời đổi OpenAPI dialect từ 3.0 sang 3.1, cần dùng cách biểu diễn null tương ứng của từng dialect trước khi kết luận hai schema khác semantics.

Các bước điều tra:

1. So sánh OpenAPI document trước và sau nâng cấp.
2. Kiểm tra kiểu Java, annotation Schema, Jackson và validation của property.
3. Xác nhận JSON runtime có thực sự cho phép null không.
4. Đọc release notes của springdoc, Swagger Core, Jackson và Spring Boot được nâng.
5. Chạy consumer test với payload null và payload thiếu property.
6. Chỉ chấp nhận thay đổi nếu semantics mới là quyết định có chủ ý và được công bố.

Không sửa dependency graph nếu dependency đã resolve đúng và lỗi thực chất nằm ở schema semantics. Cũng không ép schema cũ bằng customizer nếu runtime đã thay đổi mà chưa xác định contract mong muốn.

## 7. Ví dụ: dependency không tương thích nhưng contract không có chủ ý thay đổi

Giả sử ứng dụng đang dùng Spring Boot và một module Springdoc tương thích. Một dependency override làm swagger-core hoặc module Spring Framework được nạp ở version không phù hợp. Ứng dụng khởi động thất bại với NoSuchMethodError.

Trong tình huống này:

- Consumer chưa thể gửi request vì server không chạy.
- Chưa có bằng chứng rằng API contract được thay đổi.
- OpenAPI document có thể không được sinh ra.
- Lỗi cần xử lý ở dependency management/classpath.

Quy trình:

1. Lấy stack trace đầu tiên và xác định class/method lỗi.
2. Xem dependency tree hoặc dependencyInsight.
3. Tìm version bị override trực tiếp hoặc bắc cầu.
4. Khôi phục bộ dependency được Spring Boot BOM và Springdoc compatibility matrix hỗ trợ.
5. Build, startup và tải OpenAPI document.
6. So sánh document với baseline để xác nhận contract không đổi ngoài ý muốn.

Không tạo API v2 chỉ để phản ứng với một lỗi classpath. Đổi API version không sửa được NoSuchMethodError.

## 8. Kiểm tra dependency graph trong Maven

Xem các dependency liên quan:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework,org.springframework.boot,org.springdoc,io.swagger.core.v3,com.fasterxml.jackson.core
~~~

Xem cấu hình POM sau khi áp dụng parent, profile và dependency management:

~~~bash
./mvnw help:effective-pom
~~~

Tìm các dấu hiệu:

- Nhiều major version của Springdoc cùng tồn tại.
- Swagger Core bị ép version khác với version starter quản lý.
- Spring Framework modules không đồng bộ.
- Jackson core/databind/annotations lệch version.
- Thư viện cũ kéo theo namespace javax trong ứng dụng Boot 3/4.
- Exclusion làm mất một dependency runtime cần thiết.

Ưu tiên Spring Boot parent/BOM và dependency management của project. Chỉ override một dependency khi có lý do cụ thể, biết rõ compatibility range và có test xác nhận.

## 9. Kiểm tra dependency graph trong Gradle

Dùng dependencyInsight để xem lý do Gradle chọn một version:

~~~bash
./gradlew dependencyInsight --dependency springdoc-openapi --configuration runtimeClasspath
./gradlew dependencyInsight --dependency swagger-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath
~~~

Xem runtime graph:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Nếu project có nhiều module, chạy lệnh ở module chứa ứng dụng hoặc cấu hình thực sự resolve dependency. CompileClasspath có thể khác runtimeClasspath; testRuntimeClasspath cũng có thể chứa dependency không có trong production.

Khi dùng version catalog hoặc platform, phân biệt version được yêu cầu với version được chọn cuối cùng. Không chỉ nhìn libs.versions.toml rồi kết luận classpath đã dùng đúng version.

## 10. Dùng BOM và constraints để quản lý một bộ dependency nhất quán

Spring Boot BOM quản lý một tập phiên bản đã được kiểm thử cùng nhau. Với Maven, thường dùng Spring Boot parent hoặc import spring-boot-dependencies. Với Gradle, dùng Spring Boot plugin và dependency management/platform theo cấu trúc project.

Nguyên tắc:

- Để Spring Boot quản lý các module Spring Framework.
- Chọn springdoc theo compatibility matrix của Boot minor version.
- Tránh tự nâng riêng Swagger Core nếu springdoc starter đã quản lý dependency đó.
- Tránh ghép Jackson modules từ các release train khác nhau.
- Ghi lại lý do nếu phải dùng constraint hoặc force version.

BOM không bảo đảm mọi thư viện bên thứ ba đều tương thích. Nó chỉ quản lý những dependency nằm trong phạm vi của BOM. Vẫn phải kiểm tra add-on, plugin và thư viện nội bộ.

## 11. Xác định class thực sự được nạp lúc runtime

Dependency tree cho biết resolution của build, nhưng production có thể chạy một JAR hoặc container image được tạo từ commit khác.

Với executable JAR:

~~~bash
jar tf application.jar
~~~

Kiểm tra thư viện lồng trong BOOT-INF/lib. Nếu nghi ngờ class trùng hoặc nạp từ vị trí không mong muốn, có thể ghi nhận nguồn class trong Java:

~~~java
System.out.println(
        OrderController.class
                .getProtectionDomain()
                .getCodeSource()
                .getLocation()
);
~~~

Thay class ví dụ bằng class đang gây lỗi. Trên JDK hỗ trợ, có thể bật class loading log để xem nguồn nạp class:

~~~bash
java -Xlog:class+load=info -jar application.jar
~~~

Không chỉ kiểm tra source workspace. Bằng chứng quan trọng là class được nạp trong tiến trình đang lỗi.

## 12. Tạo baseline OpenAPI trước khi nâng thư viện

Trước khi thay dependency, lưu OpenAPI JSON/YAML của bản đang chạy:

~~~bash
curl -fS http://localhost:8080/v3/api-docs -o openapi-before.json
~~~

Sau khi nâng dependency và khởi động bản mới:

~~~bash
curl -fS http://localhost:8080/v3/api-docs -o openapi-after.json
~~~

Đưa hai file vào công cụ diff OpenAPI để phát hiện thay đổi ở:

- Paths và HTTP methods.
- Parameter name, location, required và schema.
- Request body, media type và encoding.
- Response status, headers, media type và schema.
- Required properties, nullable, enum và format.
- Security schemes và requirements.
- Servers, tags và operationId.

Diff văn bản thuần có thể báo khác biệt do thứ tự key hoặc formatting. Công cụ hiểu OpenAPI giúp phân biệt thay đổi cấu trúc với thay đổi thực sự của contract.

## 13. Phân loại thay đổi OpenAPI theo mức ảnh hưởng

Một số thay đổi thường được xem là breaking đối với consumer:

| Thay đổi | Rủi ro với client cũ |
|---|---|
| Xóa path hoặc HTTP method | Client không gọi được operation |
| Đổi path hoặc parameter name | Request cũ không match |
| Đổi query parameter thành header | Client gửi sai vị trí |
| Thêm request property bắt buộc | Request cũ không còn hợp lệ |
| Đổi request property sang kiểu không tương thích | Server có thể từ chối payload |
| Xóa response property | Client phụ thuộc field có thể lỗi |
| Đổi response property type | Parser hoặc logic client có thể lỗi |
| Thu hẹp enum được chấp nhận | Request cũ có thể bị từ chối |
| Thay response media type | Client không parse được body |
| Tăng security requirement | Client cũ không có credential phù hợp |

Một số thay đổi có vẻ additive nhưng vẫn có thể làm hỏng consumer:

- Thêm giá trị enum vào response có thể làm client dùng exhaustive switch lỗi.
- Thêm field response có thể làm parser strict từ chối JSON.
- Đổi default page size có thể thay đổi kết quả client nhìn thấy.
- Đổi thứ tự sorting mặc định có thể làm luồng xử lý sai dù schema không đổi.

Vì vậy, compatibility không chỉ là so sánh schema. Cần xét semantics và cách consumer thực sự sử dụng API.

## 14. Phân biệt breaking change với additive change

Các thay đổi sau thường có khả năng tương thích tốt hơn, nhưng vẫn cần kiểm tra client thực tế:

- Thêm endpoint mới mà không đổi endpoint cũ.
- Thêm query parameter optional có default an toàn.
- Thêm response property optional.
- Thêm response status mới cho một nhánh lỗi đã được consumer cho phép xử lý.
- Bổ sung description hoặc example không đổi semantics.

Không có quy tắc “mọi field mới đều an toàn”. Với response JSON, client có parser strict có thể không chấp nhận field lạ. Với enum, client có thể giả định tập giá trị đóng. Với query parameter, thay đổi default có thể làm thay đổi behavior dù parameter vẫn optional.

Hãy xác định chính sách compatibility của consumer: tolerant reader, strict schema validation, generated client hay integration trực tiếp.

## 15. Xác định thay đổi có chủ ý hay vô tình

Một thay đổi contract được xem là có chủ ý khi có bằng chứng quyết định:

- Yêu cầu sản phẩm hoặc ADR mô tả lý do.
- Chủ sở hữu API xác nhận semantics mới.
- Consumer bị ảnh hưởng được xác định.
- Kế hoạch versioning/deprecation được chọn.
- OpenAPI diff được review.
- Migration guide hoặc thông báo consumer có nội dung rõ.
- Test xác nhận behavior mới và behavior cũ trong giai đoạn chuyển tiếp nếu cần.

Nếu không có các bằng chứng trên, hãy coi khác biệt là thay đổi ngoài ý muốn cần điều tra. Không tự gắn nhãn “breaking change có chủ ý” chỉ vì code mới đã được merge.

## 16. Khi nào cần tăng phiên bản API?

Nếu thay đổi là breaking và consumer không thể chuyển ngay, cần chính sách versioning rõ ràng. Tùy sản phẩm, có thể:

- Phát hành major API version mới.
- Duy trì endpoint cũ song song trong thời gian migration.
- Thêm endpoint mới rồi deprecate endpoint cũ.
- Dùng version trong path, header hoặc media type theo quy ước đã công bố.

Không có một chiến lược versioning duy nhất phù hợp cho mọi hệ thống. Quan trọng là consumer có thể xác định hợp đồng nào đang dùng và thời gian hỗ trợ của hợp đồng đó.

Thay version info.version trong OpenAPI không tự tạo route mới hoặc tách behavior ở runtime. Nếu API versioning dùng path /v1 và /v2, ứng dụng phải thực sự triển khai hai route/contract tương ứng.

## 17. Deprecation cần có lộ trình

Khi thay operation cũ bằng operation mới:

1. Công bố operation mới và ví dụ migration.
2. Đánh dấu operation cũ deprecated trong OpenAPI.
3. Thông báo consumer, owner và thời hạn chuyển đổi.
4. Theo dõi traffic còn dùng operation cũ nếu hệ thống có telemetry.
5. Chỉ xóa operation cũ sau khi đạt điều kiện sunset đã công bố.

Ví dụ:

~~~java
@Operation(
        summary = "Tra cứu đơn hàng theo mã cũ",
        deprecated = true,
        description = "Sử dụng GET /api/v2/orders/{orderId} cho tích hợp mới."
)
~~~

Annotation chỉ đánh dấu metadata. Việc ngừng phục vụ endpoint cần được thực hiện riêng theo lịch và chính sách đã thông báo.

## 18. Kiểm tra hành vi JSON thay vì chỉ đọc schema

Một dependency update có thể làm thay đổi serialization dù DTO source không đổi. Hãy serialize representative object bằng ObjectMapper thực tế của ứng dụng:

~~~java
String json = objectMapper.writeValueAsString(orderResponse);
System.out.println(json);
~~~

Đối chiếu JSON với:

- Property name.
- Property bị bỏ qua hoặc chỉ đọc.
- Null inclusion.
- Date/time format.
- Enum serialization.
- Polymorphic type metadata.
- Custom serializer/deserializer.

Với request, test deserialize payload cũ để biết server mới còn nhận được không. Với response, test serialize để biết client cũ còn hiểu được không.

OpenAPI schema và Jackson output phải nhất quán. Một schema diff không giải thích được nếu chưa kiểm tra JSON thực tế.

## 19. Dùng consumer contract test để xác nhận tác động

Contract test cần kiểm tra những điều consumer phụ thuộc, ví dụ:

- Client cũ gửi request cũ vẫn nhận response mong đợi.
- Required field và enum value được xử lý đúng.
- Authentication flow vẫn hoạt động.
- Error response giữ schema và status cần thiết.
- Pagination, sorting và default behavior không thay đổi ngoài dự kiến.

Ví dụ kiểm tra một request cũ bằng MockMvc:

~~~java
@Test
void legacyCreateOrderRequestRemainsAccepted() throws Exception {
    mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "customerCode": "CUS-10025",
                              "items": [
                                {"productCode": "P-01", "quantity": 2}
                              ]
                            }
                            """))
            .andExpect(status().isCreated());
}
~~~

Đây chỉ là ví dụ; điều chỉnh endpoint và payload theo contract thật. Nếu thay đổi có chủ ý làm request cũ không còn hợp lệ, test cần được cập nhật cùng với migration/versioning plan, không đơn giản xóa test mà không ghi nhận tác động.

## 20. Kiểm tra OpenAPI contract trong CI

CI có thể lưu document được sinh từ commit hiện tại và so sánh với baseline của nhánh phát hành:

1. Build ứng dụng bằng dependency đã khóa.
2. Khởi động test application.
3. Tải /v3/api-docs.
4. Validate document theo OpenAPI version tương ứng.
5. Chạy OpenAPI diff với baseline.
6. Phân loại breaking/additive changes.
7. Yêu cầu API owner review breaking change.
8. Chạy consumer contract tests.

Có thể dùng công cụ OpenAPI diff/lint phù hợp với quy trình của tổ chức. Không xem exit code của một công cụ diff là quyết định sản phẩm cuối cùng nếu công cụ không hiểu được semantics như default, enum handling hoặc strict client behavior.

## 21. Ma trận chẩn đoán theo loại lỗi

| Build | Startup/runtime | OpenAPI diff | Kết luận ban đầu |
|---|---|---|---|
| Fail | Chưa chạy được | Không có | Ưu tiên source/dependency compatibility |
| Pass | Fail khi startup | Không có | Ưu tiên runtime classpath/auto-configuration |
| Pass | Pass | Không đổi | Dependency update có vẻ ổn; tiếp tục test behavior |
| Pass | Pass | Có thay đổi | Điều tra schema/contract drift |
| Pass | Pass | Có breaking change đã được phê duyệt | Thực hiện versioning và migration plan |
| Pass | Pass | Có breaking change chưa được phê duyệt | Xử lý như regression ngoài ý muốn |
| Pass | Pass | Không đổi nhưng consumer fail | Kiểm tra semantics, serialization và runtime behavior |

Ma trận này giúp chọn hướng điều tra. Kết luận cuối phải dựa trên stack trace, dependency graph, document và request/response thực tế.

## 22. Quy trình điều tra từ đầu đến cuối

1. Ghi lại commit, Spring Boot, Java, springdoc và các dependency liên quan trước/sau thay đổi.
2. Phân loại lỗi ở compile, startup, runtime hay consumer behavior.
3. Nếu có lỗi linkage, xác định class/method và class origin.
4. So sánh dependency tree hoặc dependencyInsight với baseline.
5. Xác minh BOM, constraints, exclusions và artifact thực sự được đóng gói.
6. Nếu ứng dụng chạy, tải OpenAPI JSON trước/sau và tạo semantic diff.
7. Đối chiếu schema với JSON runtime và request binding.
8. Chạy consumer contract tests.
9. Xác định thay đổi contract là intentional hay accidental dựa trên ADR/approval.
10. Nếu accidental, sửa dependency hoặc khôi phục contract.
11. Nếu intentional và breaking, phát hành version/migration/deprecation plan.
12. Ghi lại bằng chứng và kết quả test trong change review.

## 23. Những cách xử lý dễ làm vấn đề khó hơn

- Nâng đồng thời Spring Boot, springdoc, Jackson và Swagger Core mà không lưu baseline.
- Thêm một dependency cũ để che NoSuchMethodError.
- Ép version transitive mà không kiểm tra BOM và classpath runtime.
- Sửa schema bằng customizer trước khi xác nhận JSON runtime.
- Đổi API path/version để né lỗi startup do dependency.
- Coi mọi OpenAPI diff là breaking mà không xét semantics.
- Coi mọi field mới là additive mà không kiểm tra strict consumer.
- Xóa consumer test vì nó fail sau migration nhưng chưa phân loại nguyên nhân.
- Đánh dấu operation deprecated nhưng không có thời hạn hoặc migration path.

Mỗi thay đổi nên giải quyết đúng lớp vấn đề và có test chứng minh.

## 24. Checklist trước khi kết luận migration thành công

- [ ] Source compile với dependency mới.
- [ ] Spring Boot và springdoc nằm trong dải tương thích đã công bố.
- [ ] Không trộn major version của Springdoc, Spring Framework hoặc Swagger Core.
- [ ] Runtime classpath khớp với dependency graph đã review.
- [ ] Ứng dụng khởi động và endpoint OpenAPI trả về bình thường.
- [ ] OpenAPI document đã được diff với baseline.
- [ ] Mọi breaking change đều có owner và quyết định rõ ràng.
- [ ] JSON serialization/deserialization được kiểm tra.
- [ ] Request cũ và response cũ được kiểm tra bằng consumer tests.
- [ ] Security, error response và pagination semantics được xác minh.
- [ ] API versioning/deprecation plan được công bố nếu cần.
- [ ] CI lưu document và kiểm tra contract ở các lần thay đổi sau.

## 25. Nguyên tắc thiết kế

- Tách library compatibility khỏi API contract compatibility.
- Phân loại source, binary, runtime và behavioral compatibility.
- Dùng dependency graph và class origin để chứng minh lỗi thư viện.
- Dùng OpenAPI diff và HTTP tests để chứng minh thay đổi contract.
- Lưu OpenAPI baseline trước mỗi lần nâng dependency có ảnh hưởng tới generation hoặc serialization.
- Quản lý Spring Framework qua Spring Boot BOM khi phù hợp.
- Chọn springdoc theo compatibility matrix của Spring Boot minor version.
- Không override dependency chỉ để làm mất lỗi linkage.
- Chỉ coi breaking change là intentional khi có quyết định, owner và consumer migration plan.
- Dùng versioning/deprecation để quản lý thay đổi có chủ ý.
- Đưa dependency checks và contract tests vào CI.

## Kết luận

Lỗi tương thích thư viện và thay đổi hợp đồng API có thể xuất hiện cùng lúc nhưng cần được chẩn đoán riêng. Dependency lỗi thường để lại bằng chứng trong compiler, classpath, stack trace hoặc startup; contract drift thể hiện trong OpenAPI diff và request/response runtime. Hãy kiểm tra dependency graph và class thực sự được nạp, đồng thời lưu và so sánh OpenAPI document trước/sau nâng cấp. Nếu khác biệt không được phê duyệt, xử lý như regression. Nếu thay đổi là chủ ý và có ảnh hưởng breaking, công bố version mới hoặc lộ trình deprecation phù hợp. Chỉ kết luận migration thành công khi build, runtime, OpenAPI contract và consumer tests đều đạt yêu cầu.

## Tài liệu tham khảo

- [Spring Boot Dependency Management](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
- [Springdoc-openapi documentation and compatibility matrix](https://springdoc.org/)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)
- [Maven Dependency Plugin](https://maven.apache.org/plugins/maven-dependency-plugin/)
- [Gradle dependencyInsight](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html)
- [Java binary compatibility and linkage errors](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/LinkageError.html)
