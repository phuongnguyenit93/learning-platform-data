# Kiểm tra tương thích Spring Boot, Spring Data REST, Spring HATEOAS và Jackson

Một ứng dụng Spring Data REST không chỉ phụ thuộc vào một thư viện. Luồng export repository thành REST API đi qua Spring Boot, Spring Framework, Spring Data REST, Spring HATEOAS và thư viện JSON như Jackson. Các thành phần này liên kết với nhau qua API, auto-configuration, message converter và dependency transitive.

Vì vậy, kiểm tra tương thích phải thực hiện trên toàn bộ dependency graph và response chạy thực tế. Chỉ thấy Gradle/Maven build thành công chưa đủ để kết luận HAL representation, serialization hoặc các endpoint Spring Data REST hoạt động đúng.

## 1. Hiểu vai trò và mối liên hệ giữa các thành phần

| Thành phần | Vai trò | Điểm cần kiểm tra |
|---|---|---|
| Spring Boot | Quản lý cấu hình ứng dụng, starter và dependency versions | Phiên bản Boot, Java baseline, BOM và auto-configuration |
| Spring Framework | Nền tảng container, MVC, converter và transaction | Phiên bản tương ứng với dòng Spring Boot |
| Spring Data REST | Export Spring Data repository thành REST resource qua WebMVC | REST module tương thích với Spring Data release train và Boot |
| Spring HATEOAS | Xây dựng hypermedia, HAL links, EntityModel và CollectionModel | API HATEOAS và HAL serializer tương thích với Spring Data REST |
| Jackson | Serialize/deserialize JSON representation | Phiên bản, package, mapper, module và custom serializer |

Luồng response có thể hình dung như sau:

~~~text
Spring Boot
    |
    +-- Spring Framework / Spring MVC
    |
    +-- Spring Data REST
    |       |
    |       +-- Spring Data repository
    |       |
    |       +-- Spring HATEOAS / HAL
    |
    +-- JSON integration
            |
            +-- Jackson
                    |
                    +-- JSON serialization/deserialization
~~~

Spring Data REST export repository thành REST resource qua Spring WebMVC. HATEOAS cung cấp các abstraction hypermedia và representation mà REST API sử dụng. Jackson đảm nhiệm chuyển object thành JSON và đọc JSON thành object theo cấu hình của ứng dụng.

Một lỗi tương thích ở bất kỳ tầng nào cũng có thể khiến ứng dụng không khởi động, request bị lỗi hoặc response JSON/HAL thay đổi ngoài dự kiến.

## 2. Chọn Spring Boot làm điểm bắt đầu

Khi dùng Spring Boot, hãy chọn một phiên bản Boot cụ thể trước. Sau đó dùng dependency management do chính phiên bản đó cung cấp để chọn các phiên bản Spring Framework, Spring Data REST, Spring HATEOAS và Jackson.

Spring Boot phát hành BOM spring-boot-dependencies. BOM này khai báo các phiên bản dependency đã được lựa chọn và kiểm thử cùng một bản phát hành Boot. Khi dependency được BOM quản lý, ứng dụng thường chỉ cần khai báo group/artifact mà không cần chỉ định version riêng.

Nguyên tắc:

1. Chốt dòng Spring Boot và patch version đang dùng.
2. Đọc bảng managed dependency versions của đúng dòng Boot đó.
3. Để BOM quản lý các dependency Spring và Jackson nếu chúng đã nằm trong BOM.
4. Chỉ override version khi có lý do tương thích rõ ràng, đã kiểm chứng và có test.
5. Không ghép ngẫu nhiên phiên bản mới nhất của từng thư viện.

Không có một cặp version “mới nhất” nào tự động tương thích với mọi ứng dụng. Một bản Spring Data REST mới có thể yêu cầu API của Spring Framework hoặc Spring HATEOAS mới hơn phiên bản mà Boot cũ đang quản lý.

### Vì sao không nên tự chọn từng version?

Giả sử dự án dùng Spring Boot 3.x nhưng khai báo riêng một phiên bản Spring HATEOAS thuộc dòng mới hơn. Build có thể vẫn resolve được dependency, nhưng khi chạy có thể xuất hiện:

- NoSuchMethodError: code đã biên dịch gọi method không tồn tại trong class được nạp lúc runtime.
- NoClassDefFoundError hoặc ClassNotFoundException: class mà một thành phần cần không có trong runtime classpath.
- ClassCastException: các kiểu hoặc class loader không tương thích.
- Lỗi khởi tạo bean hoặc auto-configuration.
- HAL link, JSON field hoặc content negotiation khác với hợp đồng mà client đang sử dụng.

Các lỗi này không nhất thiết xuất hiện ở compile time. Chúng có thể chỉ xảy ra khi application context khởi động hoặc khi gọi một endpoint cụ thể.

## 3. Dùng Spring Boot BOM trong Gradle

Với Gradle Groovy DSL, có thể để Spring Boot plugin tích hợp dependency management:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-rest'

    // Chỉ thêm khi ứng dụng trực tiếp xây dựng hypermedia
    // representation ngoài phần được Spring Data REST cung cấp.
    implementation 'org.springframework.boot:spring-boot-starter-hateoas'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Các version trong ví dụ chỉ minh họa cách khai báo cho một dự án thuộc dòng Boot 3.3. Hãy dùng patch version và plugin version đã được tổ chức dự án lựa chọn; không sao chép nguyên version ví dụ vào một dự án Boot khác.

Khi plugin dependency management được áp dụng, Spring Boot tự import BOM tương ứng. Vì vậy không cần khai báo version riêng cho spring-data-rest-webmvc, spring-hateoas hoặc Jackson nếu BOM đã quản lý chúng.

Có thể dùng Gradle native BOM support thay cho plugin dependency management:

~~~groovy
plugins {
    id 'java'
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )

    implementation 'org.springframework.boot:spring-boot-starter-data-rest'
    implementation 'org.springframework.boot:spring-boot-starter-hateoas'
}
~~~

Chỉ chọn một chiến lược dependency management nhất quán cho project. Nếu build đã import Boot BOM ở root hoặc convention plugin, không import lại một BOM khác với version không đồng nhất ở subproject.

Spring Data REST đã kéo theo các dependency cần thiết cho chức năng export repository. Chỉ khai báo starter HATEOAS riêng khi code ứng dụng thực sự dùng trực tiếp API HATEOAS hoặc cần cấu hình tích hợp riêng; tránh thêm dependency chỉ vì thấy tên thư viện trong dependency tree.

## 4. Dùng Spring Boot BOM trong Maven

Nếu dùng spring-boot-starter-parent, dependency management được kế thừa từ parent:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
</parent>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-rest</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-hateoas</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Nếu không thể dùng Boot parent, import spring-boot-dependencies trong dependencyManagement:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.13</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Sau khi import BOM, các dependency được quản lý có thể bỏ version. Nếu có nhiều BOM hoặc dependency management ở parent khác, hãy kiểm tra quy tắc precedence và effective POM để biết version cuối cùng được chọn.

## 5. Kiểm tra phiên bản thực tế trong dependency graph

File build chỉ cho biết dependency được khai báo. Dependency graph mới cho biết phiên bản nào thực sự được resolve sau khi xét BOM, constraint, transitive dependency, resolution strategy và override.

### Với Gradle

Xem toàn bộ runtime classpath:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Xem dependency cụ thể được resolve từ đâu:

~~~bash
./gradlew dependencyInsight --dependency spring-data-rest-webmvc --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-hateoas --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

Trên Windows có thể dùng gradlew.bat thay cho ./gradlew.

Kết quả dependencyInsight giúp xác định:

- Version được chọn cuối cùng.
- Dependency nào kéo thư viện vào graph.
- Version nào bị loại hoặc conflict.
- Constraint, platform hay rule nào quyết định version.

Đối với Jackson 3, cần tìm thêm các artifact thuộc group tools.jackson; không chỉ kiểm tra com.fasterxml.jackson.core:jackson-databind.

### Với Maven

Xem dependency tree:

~~~bash
mvn dependency:tree -Dverbose
~~~

Có thể giới hạn output vào các nhóm dependency cần xem:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.data:*,org.springframework.hateoas:*,com.fasterxml.jackson.core:*,tools.jackson.core:*
~~~

Kiểm tra effective POM khi dự án có parent hoặc nhiều BOM:

~~~bash
mvn help:effective-pom
~~~

Không chỉ nhìn version trong file pom.xml. Version được resolve có thể đến từ parent POM, BOM import hoặc dependency management ở cấp cao hơn.

### Lập bảng kiểm kê

Sau khi lấy kết quả dependency tree, ghi nhận tối thiểu:

| Artifact | Version mong đợi | Version runtime | Nguồn quản lý |
|---|---|---|---|
| Spring Boot | Theo baseline dự án | Theo dependency graph | Boot plugin / BOM |
| Spring Framework | Theo Boot BOM | Theo dependency graph | Boot BOM |
| Spring Data REST | Theo Boot BOM | Theo dependency graph | Boot BOM |
| Spring HATEOAS | Theo Boot BOM | Theo dependency graph | Boot BOM |
| Jackson core/databind | Theo dòng Jackson của Boot | Theo dependency graph | Boot BOM hoặc cấu hình migration |

Nếu version runtime khác với version được quản lý, phải xác định rõ dependency nào gây ra khác biệt và lý do tại sao. Không bỏ qua chỉ vì build vẫn thành công.

## 6. Hiểu khác biệt Jackson giữa Spring Boot 3 và Spring Boot 4

Đây là một điểm nâng cấp quan trọng vì thay đổi không chỉ nằm ở số version. Spring Boot 4 chuyển sang Jackson 3 làm thư viện JSON mặc định; Spring Boot 3 dùng Jackson 2 làm lựa chọn mặc định.

| Nội dung | Spring Boot 3.x | Spring Boot 4.x |
|---|---|---|
| JSON mapper mặc định | Jackson 2 | Jackson 3 |
| Mapper chính | ObjectMapper | JsonMapper |
| Package core/databind | com.fasterxml.jackson.* | tools.jackson.* |
| Annotation package | com.fasterxml.jackson.annotation | Vẫn dùng com.fasterxml.jackson.annotation |
| Auto-configuration | Jackson 2 | Jackson 3 |
| Cấu hình Jackson | spring.jackson.* | Các property mới theo Jackson 3, ví dụ spring.jackson.* và nhóm JSON tương ứng theo tài liệu Boot 4 |
| Component annotation | @JsonComponent, @JsonMixin | @JacksonComponent, @JacksonMixin |

Một số thay đổi quan trọng khi chuyển sang Boot 4:

- Group ID và package của phần lớn Jackson 2 chuyển từ com.fasterxml.jackson sang tools.jackson.
- Ngoại lệ đáng chú ý là Jackson annotations vẫn dùng group/package com.fasterxml.jackson.core và com.fasterxml.jackson.annotation.
- ObjectMapper trong hệ Jackson 2 được thay bằng JsonMapper trong tích hợp Jackson 3.
- Một số lớp serializer/deserializer và customizer được đổi tên.
- @JsonComponent và @JsonMixin được đổi thành @JacksonComponent và @JacksonMixin.
- Một số property JSON được chuyển sang namespace mới.

Boot 4 vẫn cung cấp module tương thích Jackson 2 cho giai đoạn chuyển đổi, nhưng module này được đánh dấu deprecated và không nên coi là giải pháp lâu dài. Nếu một thư viện bên thứ ba chưa hỗ trợ Jackson 3, hãy kiểm tra rõ yêu cầu của thư viện và kế hoạch nâng cấp trước khi quyết định giữ Jackson 2.

Không trộn class từ hai hệ Jackson trong cùng một API tùy tiện. Ví dụ, một method nhận com.fasterxml.jackson.databind.ObjectMapper không thể thay trực tiếp bằng tools.jackson.databind.json.JsonMapper chỉ bằng cách đổi version dependency; đây là thay đổi package và kiểu dữ liệu cần sửa code.

## 7. Kiểm tra Spring Data REST và Spring HATEOAS

Spring Data REST xuất repository resource qua Spring WebMVC. Các response hypermedia thường sử dụng HAL và các kiểu representation từ Spring HATEOAS.

Khi nâng cấp version, cần xác nhận:

- Application context khởi động được với auto-configuration hiện tại.
- Repository được export đúng base path và collection/item resource.
- HAL response vẫn có _links, _embedded và các relation mà client cần.
- Content negotiation vẫn trả representation theo Accept header.
- Pagination và sorting vẫn giữ đúng metadata, link và query parameter.
- Projection, excerpt và association link vẫn được serialize đúng.
- Custom controller, assembler, EntityModel, CollectionModel và RepresentationModel vẫn compile và hoạt động.
- Jackson module, mixin và custom serializer vẫn được đăng ký với mapper đang thực sự dùng.

Ví dụ request smoke test:

~~~http
GET /api/products
Accept: application/hal+json
~~~

Response nên được kiểm tra theo hợp đồng thực tế, ví dụ:

~~~json
{
  "_embedded": {
    "products": [
      {
        "id": 1,
        "name": "Keyboard"
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/products"
    }
  }
}
~~~

Ví dụ trên chỉ là representation rút gọn để minh họa. Nội dung, relation name và link thực tế phụ thuộc repository, configuration và entity model.

Spring Boot có auto-configuration cho Spring HATEOAS trong các ứng dụng phù hợp. Nếu tự bật @EnableHypermediaSupport, cần đọc kỹ tác động lên auto-configuration và mapper customization. Trong cấu hình Spring Boot hiện đại, không nên thêm annotation này theo thói quen nếu auto-configuration đã đáp ứng yêu cầu.

Lưu ý starter HATEOAS dành cho Spring MVC; không ghép nó với WebFlux như thể hai stack có cùng cách cấu hình. Với WebFlux, cần dùng dependency HATEOAS phù hợp theo hướng dẫn của Boot.

## 8. Những lỗi tương thích thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| NoSuchMethodError trong Spring Data hoặc HATEOAS | Các module Spring khác generation hoặc version | dependencyInsight / dependency:tree |
| ClassNotFoundException với Jackson | Code import package Jackson khác thế hệ | Kiểm tra imports và runtime classpath |
| App khởi động lỗi do bean mapper | Auto-configuration hoặc customizer không tương thích | Đọc condition report và kiểm tra mapper bean |
| Response không còn HAL như mong đợi | Content negotiation, media type hoặc HATEOAS config đổi | Test với Accept: application/hal+json |
| Custom serializer không được gọi | Module/annotation registration hoặc mapper khác được dùng | Kiểm tra mapper thực tế và serialization test |
| JSON date/time khác format | Jackson module hoặc property thay đổi | Contract test cho date/time |
| Field bất ngờ xuất hiện hoặc biến mất | Visibility, mixin, naming strategy hoặc annotation thay đổi | Snapshot/JSON path test |
| Link hoặc relation bị đổi | HATEOAS model, assembler hoặc configuration thay đổi | Kiểm tra HAL links và relation names |
| Chỉ lỗi khi chạy, compile vẫn thành công | Transitive dependency conflict | Kiểm tra runtimeClasspath, không chỉ compileClasspath |

Không sửa lỗi bằng cách thêm ngẫu nhiên một version Jackson hoặc HATEOAS mới nhất. Trước hết tìm dependency nào kéo version gây conflict, xác định BOM đang được áp dụng và so sánh với dependency management chính thức của Boot.

## 9. Quy trình nâng cấp an toàn

Nâng cấp nên được thực hiện theo từng bước để biết thay đổi nào gây ra lỗi:

1. Ghi nhận baseline: phiên bản Java, Spring Boot, Spring Framework, Spring Data REST, HATEOAS và Jackson hiện tại.
2. Chọn target Boot: xác định dòng Boot mục tiêu và yêu cầu JDK của dòng đó.
3. Đọc migration guide: đọc hướng dẫn nâng cấp cho từng major/minor có thay đổi liên quan.
4. So sánh BOM: so sánh managed dependency versions giữa baseline và target; xác định các thư viện thay đổi generation.
5. Gỡ version override không cần thiết: để BOM quản lý dependency Spring và Jackson khi có thể.
6. Resolve lại dependency: chạy dependency tree/insight để phát hiện conflict và version bị ép.
7. Sửa code migration: xử lý API bị deprecated/removed, thay đổi package và mapper, đặc biệt khi chuyển Jackson 2 sang Jackson 3.
8. Build và test: chạy compile, unit test, integration test và kiểm tra application context.
9. Kiểm tra API contract: gọi các endpoint repository, HAL, pagination, association, projection và JSON custom type.
10. Triển khai thử: kiểm tra log, error rate và response trên môi trường gần production trước khi rollout.

Không nâng cấp Boot, Spring Data REST, HATEOAS và Jackson thành bốn thay đổi độc lập trong một lượt nếu chưa có lý do. Nâng cấp Boot trước thường giúp lấy được bộ dependency đã được kiểm thử cùng nhau; sau đó xử lý các thư viện ngoài BOM riêng.

## 10. Bộ kiểm thử tối thiểu sau nâng cấp

Một bộ kiểm thử tương thích nên có các nhóm sau:

**Khởi động và dependency**

- Application context khởi động thành công.
- Không có bean bị thiếu hoặc bean mapper bị trùng ngoài dự kiến.
- Runtime dependency tree không chứa version Spring/Jackson bị override ngoài ý muốn.

**Spring Data REST**

- Collection GET trả đúng resource.
- Item GET, POST, PUT/PATCH và DELETE hoạt động theo cấu hình.
- Search/finder resource được export đúng.
- Association link có thể đọc và cập nhật.
- Pagination, sorting và projection vẫn đúng.

**Spring HATEOAS/HAL**

- Response có media type đúng.
- _links và _embedded tồn tại đúng relation.
- Link tự tham chiếu, next/prev và association link hợp lệ.
- Custom assembler không bị lỗi khi tạo representation.

**Jackson**

- Serialize và deserialize các entity/DTO quan trọng.
- Date, time, enum, UUID, number và null giữ đúng format.
- Custom serializer/deserializer và mixin vẫn được đăng ký.
- Quan hệ entity không tạo vòng lặp serialization ngoài ý muốn.
- Field nhạy cảm vẫn bị ẩn theo hợp đồng API.

**Tương thích client**

- Kiểm tra response JSON/HAL so với contract hiện tại.
- Kiểm tra client sử dụng Accept và Content-Type đúng.
- Nếu API có thay đổi representation, đánh giá ảnh hưởng tới client cũ trước khi phát hành.

Có thể dùng @SpringBootTest để kiểm tra auto-configuration và MockMvc hoặc HTTP integration test để kiểm tra endpoint. Test serialization trực tiếp bằng mapper không thay thế được test HTTP, vì request pipeline còn có content negotiation, message converter và Spring Data REST representation processing.

## 11. Checklist chốt tương thích

- [ ] Đã chốt Spring Boot version và Java baseline.
- [ ] Spring Framework thuộc generation do Boot quản lý.
- [ ] Spring Data REST lấy từ đúng BOM/release train.
- [ ] Spring HATEOAS lấy từ đúng BOM, không override tùy tiện.
- [ ] Jackson group/package phù hợp với Boot major đang dùng.
- [ ] Không có hai mapper hoặc hai hệ Jackson được sử dụng ngoài chủ đích.
- [ ] Đã xem runtime dependency tree, không chỉ file khai báo.
- [ ] Application context khởi động thành công.
- [ ] Repository REST endpoint hoạt động qua HTTP.
- [ ] HAL links, embedded resources và content negotiation được kiểm tra.
- [ ] Jackson custom module, mixin và date/time serialization được kiểm thử.
- [ ] API contract của client được xác nhận sau nâng cấp.
- [ ] Migration guide và release notes đã được đọc cho major/minor target.

## 12. Nguồn tra cứu chính thức

Không dùng một bảng version tĩnh từ blog hoặc câu trả lời cũ để quyết định dependency. Hãy tra theo đúng patch version của Spring Boot đang chọn:

- Spring Boot — Managed Dependency Versions: https://docs.spring.io/spring-boot/appendix/dependency-versions/
- Spring Boot — Gradle Dependency Management: https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html
- Spring Data REST Reference: https://docs.spring.io/spring-data/rest/reference/
- Spring Boot 3.3 — JSON and Jackson: https://docs.spring.io/spring-boot/3.3/reference/features/json.html
- Spring Boot 4.0 — JSON and Jackson: https://docs.spring.io/spring-boot/4.0/reference/features/json.html
- Spring Boot 4.0 Migration Guide: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide
- Spring Boot Supported Versions: https://github.com/spring-projects/spring-boot/wiki/Supported-Versions

