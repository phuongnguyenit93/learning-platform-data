# Kiểm tra khác biệt giữa các phiên bản Spring Boot

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Xác định những khác biệt của Spring Boot ảnh hưởng đến documentation test và quá trình sinh snippet.
- Phân biệt phiên bản Spring Boot, Spring Framework, Spring REST Docs, JUnit, Java và plugin Asciidoctor.
- Kiểm tra dependency management qua BOM, Gradle/Maven dependency report và xác minh thư viện thực tế được resolve.
- Nhận diện các thay đổi quan trọng khi nâng từ Spring Boot 2 lên Spring Boot 3, đặc biệt Java baseline và namespace javax/jakarta.
- Chọn đúng test context như @WebMvcTest hoặc @SpringBootTest, cấu hình @AutoConfigureRestDocs và kiểm tra snippet trên phiên bản mới.
- Lập checklist nâng cấp để phát hiện lỗi compile, runtime, test, Asciidoctor và thay đổi nội dung tài liệu.

## 1. Vì sao cần kiểm tra khác biệt giữa các phiên bản Spring Boot?

Spring REST Docs thường được tích hợp vào dự án Spring Boot thông qua dependency test, cấu hình test context và plugin kết xuất tài liệu. Khi thay đổi phiên bản Spring Boot, nền tảng bên dưới cũng có thể đổi: Spring Framework, Spring Test, Spring Security, Jakarta API, Java baseline, dependency management và cấu hình build.

Một documentation test chạy được trên dự án cũ chưa chắc chạy nguyên vẹn trên dự án mới. Chẳng hạn:

- Một import javax.servlet.* có thể không còn phù hợp khi dự án chuyển sang hệ Jakarta.
- Phiên bản Spring Framework mới có thể yêu cầu cách cấu hình test hoặc API tương thích khác.
- Dependency cũ được khai báo trực tiếp có thể xung đột với phiên bản mà Spring Boot BOM quản lý.
- Jackson hoặc cấu hình serialization thay đổi có thể làm HTTP body/snippet khác trước.
- Test slice không tải cùng các bean/filter như full application context, nên hành vi quan sát được có thể thay đổi theo test configuration.
- Plugin Asciidoctor hoặc cấu hình Gradle/Maven có thể cần cập nhật độc lập với Spring Boot.

Mục tiêu của việc kiểm tra version không chỉ là làm build xanh. Cần xác nhận test vẫn chạy đúng thành phần ứng dụng, tài liệu được tạo từ response đúng và các snippet vẫn mô tả hợp đồng API mà nhóm muốn công bố.

## 2. Phân biệt các phiên bản trong một dự án

Khi đọc build.gradle, pom.xml hoặc dependency report, đừng coi tất cả thư viện thuộc một phiên bản duy nhất.

| Thành phần | Vai trò | Cần kiểm tra khi nâng cấp |
| --- | --- | --- |
| Spring Boot | Nền tảng quản lý auto-configuration, dependency management và build conventions | Phiên bản plugin/BOM, Java baseline, migration guide |
| Spring Framework | Spring MVC, WebFlux, Spring Test và core container | Tương thích với Boot; thay đổi API/configuration |
| Spring REST Docs | Ghi nhận HTTP exchange và sinh snippet | Integration module đúng với test client; tương thích với Spring/Test |
| JUnit | Test engine và lifecycle | JUnit 4 hay Jupiter, extension/rule và dependency engine |
| Spring Security | Filter, authentication và authorization | Cấu hình test security, matcher, request post-processor |
| Jackson | Serialize/deserialize JSON | Tên field, null/default, date format, module và ObjectMapper |
| Asciidoctor plugin/toolchain | Kết xuất tài liệu từ AsciiDoc | Plugin ID/version, task, attribute và môi trường Java/Gradle |
| Java | Runtime và compiler cho ứng dụng/test/build | Toolchain, source/target compatibility, API namespace |

Ví dụ, spring-restdocs-mockmvc là integration module dùng với MockMvc; spring-restdocs-webtestclient dành cho WebTestClient; spring-restdocs-restassured dành cho REST Assured. Một dự án chỉ nên khai báo module thực sự sử dụng.

### 2.1. Không nhầm version Spring Boot với version REST Docs

Spring Boot version và Spring REST Docs version có vòng đời phát hành riêng. Dependency management của dự án có thể quản lý một số version thông qua Boot BOM, nhưng không nên mặc định mọi plugin hoặc thư viện ngoài BOM đều được quản lý.

Quy trình an toàn:

1. Xác định phiên bản Spring Boot mục tiêu.
2. Kiểm tra BOM/dependency management thực tế đang áp dụng.
3. Kiểm tra version được resolve của Spring Framework, Spring Test và Spring REST Docs.
4. Đối chiếu yêu cầu tương thích trong tài liệu phát hành của các thư viện liên quan.
5. Tránh ép version riêng của một module Spring hoặc REST Docs nếu chưa hiểu tác động lên các module còn lại.

Không sao chép một version cụ thể từ dự án khác chỉ vì cả hai đều dùng Spring Boot. Các dự án có thể khác Java, build tool, Spring stack và dependency graph.

## 3. Những thay đổi đáng chú ý khi nâng Spring Boot 2 lên Spring Boot 3

Nâng từ Spring Boot 2 sang 3 là một ví dụ quan trọng vì thay đổi không chỉ nằm ở số version.

### 3.1. Java baseline

Spring Boot 3 yêu cầu Java 17 trở lên. Một dự án cũ đang build bằng Java 8 hoặc 11 cần nâng JDK/toolchain và kiểm tra lại compiler, test runtime, CI image cũng như IDE.

Các điểm cần rà soát:

- JDK cài trên máy phát triển và runner CI.
- java toolchain, sourceCompatibility, targetCompatibility hoặc compiler release.
- Plugin build có tương thích JDK mới không.
- Test runtime có sử dụng đúng JDK mà build kỳ vọng không.
- Dependency cũ có còn tương thích với runtime mới không.

Không chỉ đổi version Java trong file build: hãy xác minh java -version, Gradle/Maven runtime và JDK mà CI thực sự sử dụng.

### 3.2. Namespace javax.* chuyển sang jakarta.*

Spring Boot 3 đi cùng Spring Framework 6 và hệ sinh thái Jakarta EE 9+. Nhiều API Java EE trước đây thuộc namespace javax.* đã chuyển sang jakarta.*.

Ví dụ thường gặp trong ứng dụng web:

| Trước migration | Sau migration |
| --- | --- |
| javax.servlet.* | jakarta.servlet.* |
| javax.validation.* | jakarta.validation.* |
| javax.persistence.* | jakarta.persistence.* |

Lưu ý: không phải mọi package javax.* đều đổi sang jakarta.*. Một số API nền tảng Java như javax.crypto hoặc javax.net vẫn thuộc JDK. Không thực hiện thay thế chuỗi toàn dự án một cách mù quáng; kiểm tra từng package và dependency cung cấp API đó.

Đối với REST Docs:

- Test có thể import Servlet/Jakarta types qua các thư viện Spring Test.
- Validation annotation trên DTO có thể cần import Jakarta tương ứng.
- Dependency cũ dùng API Java EE đã bị thay thế có thể không còn tương thích.
- Lỗi compile trong test có thể xuất hiện trước khi REST Docs được gọi.

Chuyển namespace không đồng nghĩa phải đổi tên mọi import Spring REST Docs. Hãy để compiler và dependency tree cho biết class nào thực sự cần migration.

### 3.3. Spring Framework và test infrastructure

Spring Boot 3 đi cùng thế hệ Spring Framework 6. Các thay đổi framework, Servlet API và thư viện phụ thuộc có thể tác động đến:

- Cấu hình MVC/WebFlux test.
- Binding và validation của request.
- Exception handling.
- Security filter chain và test support.
- Serialization và response content.

Do đó, khi documentation test thất bại, hãy xác định nó thất bại ở compile, khởi tạo context, xử lý request, assertion hay tạo snippet. Mỗi giai đoạn có nguyên nhân khác nhau.

### 3.4. JUnit và test dependencies

Nhiều dự án Spring Boot sử dụng JUnit Jupiter thông qua test starter, nhưng dự án lâu đời có thể còn JUnit 4 hoặc kết hợp hai engine. Không nên suy luận chỉ từ Boot major version; đọc dependency thực tế và test annotations đang dùng.

JUnit 4 sử dụng @Rule/@ClassRule cho một số integration REST Docs; JUnit Jupiter sử dụng extension như RestDocumentationExtension. Khi migration, cần cập nhật lifecycle integration nếu test đổi framework, đồng thời bảo đảm test engine được CI phát hiện.

## 4. Chọn test context phù hợp với ứng dụng Boot

Spring Boot cung cấp nhiều cách dựng test context. Cách chọn ảnh hưởng đến thành phần được nạp và hành vi HTTP mà REST Docs ghi lại.

| Kiểu test | Mục đích | Cân nhắc khi dùng với REST Docs |
| --- | --- | --- |
| @WebMvcTest | Test lát cắt Spring MVC, thường tập trung controller và web components | Nhẹ; cần mock service dependency và xác định security/filter nào được nạp |
| @SpringBootTest + @AutoConfigureMockMvc | Dựng application context rộng hơn và dùng MockMvc | Bao phủ nhiều cấu hình thực của ứng dụng; tốn thời gian hơn |
| WebFlux test context | Test handler/controller reactive | Dùng WebTestClient integration phù hợp với cấu hình WebFlux |
| Test kết nối server đang chạy | Test qua HTTP endpoint thực | Có thể dùng WebTestClient hoặc REST Assured theo cách khởi tạo server |

Nếu tài liệu mô tả status 401 do security filter trả về, một test slice không nạp filter đó sẽ không chứng minh được hành vi. Nếu tài liệu mô tả định dạng ngày do Jackson module cấu hình toàn ứng dụng, hãy bảo đảm test context sử dụng đúng ObjectMapper/module tương ứng.

## 5. Cấu hình Spring Boot để tạo snippet

### 5.1. Dependencies

Ví dụ Gradle Groovy DSL cho một dự án Spring MVC dùng MockMvc và JUnit Jupiter:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
```

Không gắn version vào mỗi dòng nếu dự án đang dùng Spring Boot dependency management và version đó được BOM quản lý. Nếu version REST Docs không được quản lý bởi dependency management đang dùng, hãy khai báo version rõ ràng, nhất quán và đã kiểm tra tương thích.

Với các test client khác, dependency integration tương ứng là:

```groovy
dependencies {
    testImplementation 'org.springframework.restdocs:spring-restdocs-webtestclient'
    // Hoặc module REST Assured nếu dự án sử dụng REST Assured:
    testImplementation 'org.springframework.restdocs:spring-restdocs-restassured'
}
```

Đây là các lựa chọn thay thế theo test client; không cần thêm cả ba module nếu không sử dụng. Dependency REST Assured và server/test fixture cần được khai báo riêng theo setup của dự án.

### 5.2. Dùng @AutoConfigureRestDocs trong Spring Boot test

Spring Boot cung cấp annotation @AutoConfigureRestDocs để cấu hình REST Docs trong test context. Ví dụ với JUnit Jupiter và MockMvc:

```java
@WebMvcTest(OrderController.class)
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class OrderControllerDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @Test
    void getOrder() throws Exception {
        given(orderService.findById(42L))
                .willReturn(new OrderResponse(42L, "PAID"));

        mockMvc.perform(get("/api/orders/{id}", 42)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(42))
                .andDo(document("orders-get",
                        pathParameters(
                                parameterWithName("id")
                                        .description("Mã đơn hàng")
                        ),
                        responseFields(
                                fieldWithPath("id")
                                        .description("Mã đơn hàng"),
                                fieldWithPath("status")
                                        .description("Trạng thái đơn hàng")
                        )
                ));
    }
}
```

Đây là mẫu minh họa cho Boot test slice. Cần khai báo static import và test fixtures tương ứng, chẳng hạn given, get, status, jsonPath, document, pathParameters, parameterWithName, responseFields và fieldWithPath. @MockBean là cách thường gặp trong các thế hệ Spring Boot trước; ở các dòng Spring mới, hãy kiểm tra API thay thế được khuyến nghị cho version dự án, ví dụ bean override/test mock support hiện hành. Không sao chép annotation mock cũ mà không kiểm tra deprecation của phiên bản đang dùng.

@AutoConfigureRestDocs cấu hình integration với test; document(...) vẫn chỉ định snippet và descriptor cần tạo. Annotation không tự viết mô tả field hoặc tự kiểm tra ý nghĩa nghiệp vụ.

### 5.3. @WebMvcTest hay @SpringBootTest?

Chọn @WebMvcTest khi cần test nhanh MVC layer và có thể cung cấp dependency bằng mock/fake. Chọn @SpringBootTest kết hợp @AutoConfigureMockMvc khi cần cấu hình ứng dụng rộng hơn, như converter, advice, security hoặc bean wiring.

Ví dụ dạng full context:

```java
@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class OrderApiDocumentationTest {
    @Autowired
    MockMvc mockMvc;

    // Các test HTTP và document(...) được đặt tại đây.
}
```

Full context không tự bảo đảm test giống production hoàn toàn: profile, database, external service, gateway và môi trường runtime vẫn có thể khác. Ghi rõ phạm vi test để người đọc biết snippet được tạo từ tầng nào.

## 6. Kiểm tra dependency đã resolve

Khi nâng Boot, đừng chỉ đọc version viết trong build.gradle; hãy xem version thực sự được resolve sau dependency management và conflict resolution.

### 6.1. Gradle

Các lệnh hữu ích:

```bash
./gradlew dependencies --configuration testRuntimeClasspath
```

Để xem lý do một dependency cụ thể được chọn:

```bash
./gradlew dependencyInsight --dependency spring-restdocs --configuration testRuntimeClasspath
```

Trên Windows có thể dùng gradlew.bat thay cho ./gradlew.

Tập trung kiểm tra:

- Chỉ có một phiên bản phù hợp của từng module Spring Framework.
- Spring Test tương thích với Spring Framework/Boot đang dùng.
- Module REST Docs đúng loại và được resolve về version mong muốn.
- JUnit engine đang được đưa vào test runtime.
- Không còn dependency cũ kéo Servlet/Validation API không tương thích.

### 6.2. Maven

Có thể xem dependency tree:

```bash
mvn dependency:tree -Dscope=test
```

Nếu cần, lọc kết quả theo org.springframework, spring-restdocs, junit hoặc jakarta. Hãy phân biệt dependency trực tiếp với dependency bắc cầu; một thư viện cũ có thể được kéo vào bởi starter hoặc plugin khác.

### 6.3. Đọc cảnh báo dependency

| Dấu hiệu | Ý nghĩa có thể |
| --- | --- |
| Dependency bị đổi version ngoài ý muốn | BOM, plugin hoặc dependency khác đang override |
| Hai nhánh Spring Framework khác major/minor | Có nguy cơ classpath không nhất quán |
| Có cả API javax và jakarta cho cùng mục đích | Có thể còn dependency cũ hoặc migration chưa hoàn tất |
| JUnit test compile được nhưng không chạy | Test engine/platform hoặc cấu hình discovery chưa đúng |
| REST Docs class không tìm thấy | Thiếu module integration hoặc version/classpath sai |

Không xử lý conflict bằng cách loại trừ dependency ngay lập tức. Xác định thư viện nào yêu cầu nó, API nào đang dùng và liệu version được resolve có tương thích.

## 7. Kiểm tra snippet sau khi nâng cấp

Build xanh mới chỉ là bước đầu. Hãy so sánh snippet trước và sau:

| Thành phần | Điều cần xác minh |
| --- | --- |
| http-request | Method, URI, query string và request header có còn đúng? |
| request-fields | Field path, tên field, kiểu và cấu trúc payload có thay đổi? |
| http-response | Status, response header, JSON body có giữ đúng hợp đồng? |
| response-fields | Descriptor strict có bao phủ đúng field mới/đã đổi? |
| Error snippets | Exception handler, validation và security vẫn trả đúng status/body? |
| Asciidoctor output | Include, attribute, heading và HTML render có thành công? |

Một phiên bản Boot/Spring mới có thể thay đổi serialization hoặc thứ tự output trong ví dụ. Không phải mọi diff đều là breaking change, nhưng mọi khác biệt cần được giải thích trước khi phát hành.

### 7.1. Không nhầm diff do format với thay đổi contract

Ví dụ hai JSON sau có cùng cấu trúc và giá trị nhưng khác khoảng trắng:

```json
{"id":42,"status":"PAID"}
```

```json
{
  "id": 42,
  "status": "PAID"
}
```

Một diff formatting không nhất thiết là thay đổi contract. Ngược lại, đổi status thành paymentStatus là thay đổi cấu trúc mà client quan sát được. Khi review, phân biệt:

- Thay đổi định dạng hiển thị snippet.
- Thay đổi thứ tự field hoặc header nếu consumer có phụ thuộc không hợp lệ vào thứ tự.
- Thay đổi tên, kiểu, giá trị, status hoặc header thực tế.
- Thay đổi error mapping và validation behavior.

## 8. Cấu hình Asciidoctor và build sau migration

Spring Boot quản lý application/test dependencies, nhưng plugin Asciidoctor là thành phần build riêng. Kiểm tra plugin version và Gradle/Maven version độc lập; không suy ra plugin phải cùng số phiên bản với Spring Boot.

Ví dụ Gradle Groovy DSL với plugin Asciidoctor đã được khai báo trong phần plugins:

```groovy
configurations {
    asciidoctorExt
}

dependencies {
    asciidoctorExt 'org.springframework.restdocs:spring-restdocs-asciidoctor'
}

def snippetsDir = file("$buildDir/generated-snippets")

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    configurations 'asciidoctorExt'
    inputs.dir snippetsDir
    dependsOn tasks.named('test')
}
```

Đây là phần cấu hình phụ thuộc task, không phải build file đầy đủ. Cần bảo đảm:

1. Test output directory trùng với nơi Asciidoctor đọc snippet.
2. Thuộc tính snippets được gán đúng cho task render.
3. Test chạy trước Asciidoctor.
4. Build sạch không còn snippet cũ của test đã xóa hoặc đổi tên.
5. Plugin Asciidoctor tương thích với Gradle/JDK đang dùng.
6. Thiếu include hoặc render error được cấu hình thành lỗi CI nếu tài liệu cần đầy đủ.

Lệnh minh họa:

```bash
./gradlew clean test asciidoctor
```

Với Maven, kiểm tra lifecycle/plugin execution để chắc chắn test sinh snippet trước goal Asciidoctor. Không giả định cấu hình Gradle và Maven có đường dẫn hoặc thứ tự mặc định giống nhau.

## 9. Quy trình kiểm tra khi nâng phiên bản Spring Boot

Thực hiện theo các bước có thứ tự:

**Bước 1 — Ghi nhận baseline.** Lưu version Boot, Java, Spring REST Docs, JUnit, test client, plugin Asciidoctor và các lệnh build đang chạy. Ghi nhận output snippet hiện tại của một số endpoint quan trọng.

**Bước 2 — Đọc hướng dẫn migration.** Đối chiếu release notes/migration guide của Spring Boot và Spring Framework cho khoảng version đang nâng. Xác định Java baseline, Jakarta changes, deprecated API và thay đổi test configuration.

**Bước 3 — Nâng dependency management.** Cập nhật Boot plugin/BOM, toolchain và dependency trực tiếp; loại bỏ version override không cần thiết. Kiểm tra dependency tree trước khi xử lý conflict.

**Bước 4 — Sửa source và test.** Migration import, annotation hoặc test API theo compiler error và migration guide. Bảo đảm JUnit engine discovery và REST Docs integration tương ứng vẫn hoạt động.

**Bước 5 — Chạy test theo tầng.** Chạy unit test, MVC/WebFlux documentation test và integration test quan trọng. Khi có lỗi, xác định nó ở compile, context startup, request handling, assertion hay snippet generation.

**Bước 6 — Sinh lại và review snippet.** Dùng output sạch, so sánh HTTP request/response, payload, parameter và header. Xác minh mọi diff có chủ đích và phù hợp contract.

**Bước 7 — Render và kiểm tra tài liệu.** Chạy Asciidoctor/Markdown renderer, kiểm tra include và mở HTML đầu ra để xác minh nội dung.

**Bước 8 — Chạy CI trên đúng JDK/build image.** Chỉ phát hành khi build và tài liệu được tạo từ cùng commit/phiên bản ứng dụng.

## 10. Lỗi thường gặp khi nâng cấp

| Lỗi | Nguyên nhân thường gặp | Cách điều tra |
| --- | --- | --- |
| ClassNotFoundException/NoClassDefFoundError cho javax.* | Dependency Java EE cũ còn trên classpath sau migration | Tìm dependency kéo API cũ; thay dependency phù hợp, không đổi mọi javax một cách hàng loạt |
| Test compile lỗi ở Servlet/Validation import | Source còn namespace cũ | Kiểm tra API tương ứng và migration guide |
| @AutoConfigureRestDocs không resolve | Thiếu Boot test auto-configuration dependency hoặc classpath sai | Kiểm tra test starter và version dependency |
| Test context không khởi tạo | Bean, profile, security hoặc API framework thay đổi | Đọc root cause trong stack trace; xác minh test slice/full context |
| Documentation test chạy nhưng không có snippet | Test không gọi document, filter/configuration chưa gắn hoặc test chưa thực thi | Kiểm tra test discovery, cấu hình integration và output directory |
| JSON snippet thay đổi sau nâng cấp | Jackson/module/configuration hoặc DTO serialization thay đổi | So sánh HTTP response thực và ObjectMapper configuration |
| requestFields/responseFields thất bại | Payload thay đổi hoặc strict descriptor chưa cập nhật | Đọc body thực, kiểm tra field path và quyết định contract |
| Asciidoctor không tìm thấy snippet | Task chạy sai thứ tự hoặc đường dẫn khác nhau | Kiểm tra task dependency, snippets attribute và output |
| CI xanh nhưng local thất bại hoặc ngược lại | JDK, profile, environment variable hoặc cache khác nhau | Chuẩn hóa toolchain và chạy build sạch trên môi trường tương đương |

## 11. Checklist kiểm tra khác biệt version

- [ ] Spring Boot plugin/BOM và Java toolchain được cập nhật có chủ đích.
- [ ] Spring Framework và Spring Test version được resolve nhất quán.
- [ ] Spring REST Docs integration module đúng với MockMvc, WebTestClient hoặc REST Assured đang dùng.
- [ ] JUnit engine, extension/rule và test discovery vẫn hoạt động.
- [ ] Jakarta migration đã được xử lý cho các API thực sự thay namespace.
- [ ] Spring Security, validation, serializer và exception handler được kiểm thử ở đúng test context.
- [ ] Documentation tests chạy và sinh lại snippet trong output sạch.
- [ ] Strict descriptors phản ánh request/response hiện tại.
- [ ] Asciidoctor plugin/task/attribute tương thích với build tool và JDK.
- [ ] CI dùng cùng Java/build configuration với môi trường phát hành.
- [ ] Mọi thay đổi quan sát được trong HTTP contract đã được review và ghi nhận.

## 12. Bài tập thực hành

Một dự án Spring Boot cũ đang dùng Java 11, Spring MVC, MockMvc, JUnit 5 và Spring REST Docs. Nhóm muốn nâng lên Spring Boot 3 nhưng sau khi đổi version, test không compile vì một số import Servlet/Validation và snippet response cũng có khác biệt.

Hãy lập kế hoạch:

1. Ghi lại version Boot, Java, Spring REST Docs, Spring Test, JUnit và plugin Asciidoctor trước khi nâng.
2. Xác minh dependency version thực tế qua Gradle dependencyInsight hoặc Maven dependency:tree.
3. Xác định import thuộc API đã chuyển sang Jakarta; chỉ migration những package đúng đối tượng.
4. Chạy documentation test trong test context phù hợp và xác minh @AutoConfigureRestDocs/MockMvc configuration.
5. So sánh response JSON trước/sau để phân biệt format diff với thay đổi contract.
6. Chạy build sạch, sinh snippet, render Asciidoctor và kiểm tra HTML.
7. Viết ghi chú migration cho các thay đổi cần client chú ý.

**Câu hỏi tự kiểm tra:** Khi nâng Spring Boot, có nên đổi version của spring-restdocs-mockmvc thành cùng số với Spring Boot không? Không nên dựa vào cách ghép số version như vậy. Hai dự án có chu kỳ version riêng; hãy kiểm tra BOM, dependency resolution và yêu cầu tương thích của các thư viện.

## Kết luận

Kiểm tra khác biệt giữa các phiên bản Spring Boot cần xem toàn bộ chuỗi phụ thuộc từ Java và Boot BOM đến Spring Framework, Spring Test, Spring REST Docs, JUnit và Asciidoctor. Khi nâng từ Boot 2 lên Boot 3, Java baseline và Jakarta namespace là những điểm cần rà soát nổi bật; các thay đổi test context, security và serialization cũng có thể ảnh hưởng HTTP snippet. Hãy kiểm tra dependency đã resolve, chạy documentation test ở đúng phạm vi, sinh snippet từ output sạch và render lại tài liệu. Chỉ sau khi phân biệt được thay đổi kỹ thuật với thay đổi hợp đồng HTTP, nhóm mới có thể phát hành tài liệu tương ứng với phiên bản API mới một cách đáng tin cậy.
