# Kiểm thử JSON module graph

## 1. Vì sao cần kiểm thử JSON module graph?

Trong ứng dụng Spring Boot sử dụng **Spring Modulith**, module graph mô tả các application module và quan hệ phụ thuộc giữa chúng. Ví dụ, module **orders** có thể gọi component công khai của **inventory**, còn **notifications** có thể lắng nghe domain event được phát từ **orders**. Khi ứng dụng phát triển, package được di chuyển, module mới được thêm hoặc một lời gọi trực tiếp được thay bằng event, graph có thể thay đổi.

Spring Modulith cung cấp endpoint Actuator để xuất cấu trúc module thành JSON tại **GET /actuator/modulith**. JSON này có thể được dùng bởi công cụ vận hành, dashboard hoặc pipeline kiểm tra kiến trúc. Kiểm thử endpoint giúp phát hiện sớm khi module bị thiếu, dependency target sai, metadata thay đổi ngoài dự kiến hoặc cấu hình Actuator không còn expose endpoint.

Bài **“Kiểm thử JSON module graph”** thuộc chương **Kiểm thử** của module **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Module này dùng Spring Modulith để sinh tài liệu ranh giới application module và quan sát tương tác giữa các phần trong ứng dụng Spring Boot. Vì vậy, bài học tập trung vào việc kiểm tra hợp đồng JSON của module graph và liên hệ kết quả với kiểm tra kiến trúc ở thời điểm build.

Sau bài học, bạn có thể:

- Giải thích JSON module graph được tạo và expose qua Actuator như thế nào.
- Đọc cấu trúc module metadata, package, nested module và dependency.
- Viết kiểm thử HTTP endpoint bằng Spring Boot Test và MockMvc.
- Dùng Jackson JsonNode để xác nhận module và dependency mà không phụ thuộc thứ tự JSON.
- Kiểm tra mọi dependency target đều trỏ tới module có trong graph.
- Phân biệt kiểm thử JSON endpoint với kiểm tra quy tắc kiến trúc bằng ApplicationModules.verify().
- Cấu hình endpoint trong test và bảo vệ thông tin kiến trúc ở production.
- Đưa kiểm thử graph vào CI để phát hiện thay đổi cấu trúc ngoài dự kiến.

## 2. JSON module graph được expose ở đâu?

Spring Modulith có module Actuator endpoint với ID **modulith**. Để bật endpoint, ứng dụng cần Spring Boot Actuator và Spring Modulith Actuator support. Có thể khai báo trực tiếp hai dependency runtime:

~~~groovy
dependencies {
    runtimeOnly 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'org.springframework.modulith:spring-modulith-actuator'
}
~~~

Nếu dự án đã dùng **Spring Modulith Insight starter**, starter này đã bao gồm hỗ trợ Actuator và observability; không cần khai báo thêm module Actuator riêng trừ khi cấu hình dependency của dự án yêu cầu.

Sau khi ứng dụng khởi động, Actuator root có thể quảng bá link tới tài nguyên modulith:

~~~http
GET /actuator
~~~

Phần response liên quan:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/actuator",
      "templated": false
    },
    "modulith": {
      "href": "http://localhost:8080/actuator/modulith",
      "templated": false
    }
  }
}
~~~

Lấy module graph bằng request:

~~~http
GET /actuator/modulith
Accept: application/json
~~~

Endpoint trả về JSON object. Mỗi property ở root là technical name của một application module. Tên này cũng là giá trị được tham chiếu trong dependency target.

## 3. Hiểu cấu trúc JSON của module graph

Theo cấu trúc endpoint của Spring Modulith, các trường chính gồm:

| JSON path | Ý nghĩa |
| --- | --- |
| $.{moduleName} | Object mô tả một application module, với moduleName là technical name. |
| $.{moduleName}.displayName | Tên hiển thị của module. |
| $.{moduleName}.basePackage | Base package của module. |
| $.{moduleName}.parent | Tên parent module nếu đây là nested module; trường tùy chọn. |
| $.{moduleName}.nested | Danh sách nested module nếu có; trường tùy chọn. |
| $.{moduleName}.dependencies[] | Danh sách outgoing dependencies của module. |
| $.{moduleName}.dependencies[].target | Technical name của module được phụ thuộc. |
| $.{moduleName}.dependencies[].types[] | Các loại dependency tới target module. |

Các dependency type được tài liệu hóa gồm:

- **DEFAULT:** dependency ở mức type/reference thông thường.
- **USES_COMPONENT:** dependency thông qua Spring bean/component.
- **EVENT_LISTENER:** dependency phát sinh do module lắng nghe event của module khác.

Một module có thể có nhiều dependency tới cùng một target và dependency đó có thể mang nhiều type. Vì vậy, không nên giả định một target chỉ có một loại quan hệ.

### 3.1. Ví dụ JSON đơn giản

Giả sử ứng dụng có module orders và inventory. Module orders sử dụng component được công khai từ inventory:

~~~json
{
  "orders": {
    "basePackage": "com.acme.shop.orders",
    "displayName": "Orders",
    "dependencies": [
      {
        "target": "inventory",
        "types": [
          "USES_COMPONENT"
        ]
      }
    ]
  },
  "inventory": {
    "basePackage": "com.acme.shop.inventory",
    "displayName": "Inventory",
    "dependencies": []
  }
}
~~~

Cách đọc:

- Root key orders và inventory là tên kỹ thuật của hai module.
- basePackage cho biết package gốc dùng để nhận diện module.
- displayName là tên thân thiện để hiển thị.
- orders.dependencies có một dependency trỏ tới inventory.
- Dependency type USES_COMPONENT cho biết quan hệ được nhận diện thông qua component.

### 3.2. Ví dụ có event listener

Giả sử notifications lắng nghe event được phát từ orders. Module graph biểu diễn dependency từ module lắng nghe tới module sở hữu event:

~~~json
{
  "orders": {
    "basePackage": "com.acme.shop.orders",
    "displayName": "Orders",
    "dependencies": []
  },
  "notifications": {
    "basePackage": "com.acme.shop.notifications",
    "displayName": "Notifications",
    "dependencies": [
      {
        "target": "orders",
        "types": [
          "EVENT_LISTENER"
        ]
      }
    ]
  }
}
~~~

Điều quan trọng là đọc dependency theo hướng từ module khai báo dependency tới target. Khi kiểm thử, hãy xác nhận hướng cạnh này theo kiến trúc dự kiến thay vì suy luận ngược từ tên event.

### 3.3. Nested module

Nếu ứng dụng dùng nested application modules, JSON có thể có parent và nested:

~~~json
{
  "orders": {
    "basePackage": "com.acme.shop.orders",
    "displayName": "Orders",
    "nested": [
      "orders.internal"
    ],
    "dependencies": []
  },
  "orders.internal": {
    "basePackage": "com.acme.shop.orders.internal",
    "displayName": "Internal order processing",
    "parent": "orders",
    "dependencies": []
  }
}
~~~

parent và nested là metadata tùy chọn. Test cho ứng dụng không dùng nested module không nên bắt buộc các field này phải xuất hiện. Nếu nested module là một phần hợp đồng kiến trúc của ứng dụng, hãy kiểm thử riêng parent/nested theo đúng cấu trúc mong muốn.

## 4. Phân biệt ba lớp kiểm thử

Khi làm việc với module graph, cần xác định test đang bảo vệ điều gì:

| Loại kiểm thử | Kiểm tra điều gì? | Cách thực hiện |
| --- | --- | --- |
| JSON endpoint contract | Endpoint có trả JSON đúng cấu trúc và metadata cần thiết không? | MockMvc hoặc HTTP integration test |
| Graph consistency | Dependency target có tồn tại, type có hợp lệ và cạnh có đúng hướng không? | Duyệt JSON bằng Jackson hoặc JSONPath |
| Architecture verification | Có chu trình, truy cập package nội bộ hoặc dependency vi phạm quy tắc không? | ApplicationModules.verify() |

Ba lớp này bổ sung cho nhau:

- Endpoint JSON contract bảo vệ giao diện mà công cụ khác đọc.
- Graph consistency kiểm tra tính liên kết của response.
- Architecture verification kiểm tra cấu trúc mã nguồn theo các quy tắc Spring Modulith.

Một JSON endpoint trả HTTP 200 không chứng minh module architecture đúng theo ý định. Ngược lại, ApplicationModules.verify() thành công cũng không chứng minh endpoint Actuator đã được expose và trả đúng JSON.

## 5. Chuẩn bị dependency và cấu hình cho test

Ví dụ Gradle cho một ứng dụng có Spring MVC:

~~~groovy
dependencies {
    runtimeOnly 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'org.springframework.modulith:spring-modulith-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Các version nên được quản lý bằng Spring Boot và Spring Modulith BOM tương thích. Nếu ứng dụng đã có Insight starter thì không cần thêm lại các thành phần đã được starter cung cấp.

Trong test profile, expose endpoint modulith:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,modulith
~~~

Spring Boot không mặc định expose mọi Actuator endpoint qua HTTP. Việc thêm dependency chỉ đăng ký endpoint; cấu hình exposure quyết định endpoint có xuất hiện trên web hay không.

Có thể đặt property này trong application-test.yml hoặc trong annotation của test:

~~~java
@TestPropertySource(properties =
    "management.endpoints.web.exposure.include=health,modulith")
~~~

Không nên thay cấu hình bảo mật production chỉ để test endpoint dễ hơn. Nếu ứng dụng dùng Spring Security, test cần gửi thông tin xác thực phù hợp hoặc dùng cấu hình security dành riêng cho test.

## 6. Kiểm thử endpoint bằng MockMvc và Jackson

Với Spring Boot Test, có thể khởi động ApplicationContext và dùng MockMvc để gọi endpoint trong cùng test context. Jackson JsonNode giúp kiểm tra cấu trúc JSON mà không phụ thuộc thứ tự property.

Ví dụ dưới đây giả định ứng dụng có module orders phụ thuộc module inventory qua một Spring component:

~~~java
package com.acme.shop;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.ArrayList;
import java.util.List;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class ModulithJsonEndpointTests {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void exposesModuleGraphAsJson() throws Exception {
        MvcResult result = mockMvc.perform(get("/actuator/modulith"))
            .andExpect(status().isOk())
            .andReturn();

        assertThat(result.getResponse().getContentType())
            .contains("json");

        JsonNode graph = objectMapper.readTree(
            result.getResponse().getContentAsString()
        );

        assertThat(graph.isObject()).isTrue();
        assertThat(graph.has("orders")).isTrue();
        assertThat(graph.has("inventory")).isTrue();

        JsonNode orders = graph.path("orders");

        assertThat(orders.path("displayName").asText())
            .isEqualTo("Orders");

        assertThat(orders.path("basePackage").asText())
            .isEqualTo("com.acme.shop.orders");

        assertThat(orders.path("dependencies").isArray())
            .isTrue();

        JsonNode inventoryDependency = null;

        for (JsonNode dependency : orders.path("dependencies")) {
            if ("inventory".equals(dependency.path("target").asText())) {
                inventoryDependency = dependency;
                break;
            }
        }

        assertThat(inventoryDependency).isNotNull();

        List<String> types = new ArrayList<>();
        inventoryDependency.path("types")
            .forEach(type -> types.add(type.asText()));

        assertThat(types).contains("USES_COMPONENT");
    }
}
~~~

Test trên xác nhận:
1. Endpoint có thể được gọi và trả HTTP 200.
2. Response có content type JSON.
3. Graph có các module orders và inventory.
4. Metadata của orders đúng với package và display name dự kiến.
5. Dependency từ orders tới inventory tồn tại.
6. Loại dependency có USES_COMPONENT.

Tên package và module trong ví dụ cần thay bằng cấu trúc thật của ứng dụng. Không copy nguyên các giá trị ví dụ vào dự án rồi kỳ vọng test chạy nếu module graph không có các module tương ứng.

## 7. Kiểm thử link discovery ở Actuator root

Ngoài endpoint JSON, có thể xác nhận Actuator root quảng bá link modulith. Điều này giúp phát hiện trường hợp endpoint có thể tồn tại trong ứng dụng nhưng không được expose đúng cách:

~~~java
@Test
void actuatorRootAdvertisesModulithEndpoint() throws Exception {
    MvcResult result = mockMvc.perform(get("/actuator"))
        .andExpect(status().isOk())
        .andReturn();

    JsonNode root = objectMapper.readTree(
        result.getResponse().getContentAsString()
    );

    assertThat(root.path("_links").has("modulith")).isTrue();

    String href = root.path("_links")
        .path("modulith")
        .path("href")
        .asText();

    assertThat(href).endsWith("/actuator/modulith");
}
~~~

Test này kiểm tra khả năng discovery của endpoint qua Actuator hypermedia response. Nếu ứng dụng tùy chỉnh base path, context path hoặc management port, hãy điều chỉnh assertion theo URL thực tế hoặc chỉ kiểm tra link relation tồn tại.

## 8. Kiểm tra mọi dependency target đều tồn tại

Một kiểm thử tổng quát hữu ích là duyệt toàn bộ graph và xác nhận mọi dependency target đều trỏ tới một module được khai báo ở root.

~~~java
@Test
void everyDependencyTargetReferencesAnExistingModule() throws Exception {
    MvcResult result = mockMvc.perform(get("/actuator/modulith"))
        .andExpect(status().isOk())
        .andReturn();

    JsonNode graph = objectMapper.readTree(
        result.getResponse().getContentAsString()
    );

    var modules = graph.fields();

    while (modules.hasNext()) {
        var entry = modules.next();
        String moduleName = entry.getKey();
        JsonNode module = entry.getValue();
        JsonNode dependencies = module.path("dependencies");

        assertThat(dependencies.isArray())
            .as("dependencies of module " + moduleName)
            .isTrue();

        for (JsonNode dependency : dependencies) {
            String target = dependency.path("target").asText();

            assertThat(target).isNotBlank();
            assertThat(graph.has(target))
                .as("target " + target + " referenced by " + moduleName)
                .isTrue();

            assertThat(dependency.path("types").isArray())
                .isTrue();

            List<String> types = new ArrayList<>();
            dependency.path("types")
                .forEach(type -> types.add(type.asText()));

            assertThat(types).isNotEmpty();
        }
    }
}
~~~

Kiểm thử này không hard-code mọi cạnh của graph. Nó bảo vệ tính nhất quán cơ bản của JSON response: mỗi dependency phải có target và target phải tồn tại trong graph. Nó hữu ích khi ứng dụng thường xuyên thêm module mới.

Nếu cần bảo vệ một quan hệ quan trọng, vẫn nên có test cụ thể như orders phụ thuộc inventory. Test tổng quát không thể biết quan hệ nào là đúng theo nghiệp vụ.

## 9. Kiểm tra dependency type

Dependency type cho biết bản chất của cạnh trong module graph. Có thể xác nhận các type thuộc tập mà Spring Modulith tài liệu hóa:

~~~java
@Test
void dependencyTypesUseSupportedValues() throws Exception {
    MvcResult result = mockMvc.perform(get("/actuator/modulith"))
        .andExpect(status().isOk())
        .andReturn();

    JsonNode graph = objectMapper.readTree(
        result.getResponse().getContentAsString()
    );

    List<String> allowedTypes = List.of(
        "DEFAULT",
        "USES_COMPONENT",
        "EVENT_LISTENER"
    );

    graph.fields().forEachRemaining(entry -> {
        JsonNode dependencies = entry.getValue().path("dependencies");

        dependencies.forEach(dependency ->
            dependency.path("types").forEach(type ->
                assertThat(allowedTypes).contains(type.asText())
            )
        );
    });
}
~~~

Test này kiểm tra giá trị enum của dependency type. Nếu nâng cấp Spring Modulith và phiên bản mới bổ sung type, test sẽ báo thay đổi contract để nhóm chủ động xem xét. Nếu mục tiêu là cho phép enum mới mà không cần sửa test ngay, có thể bỏ assertion allowlist và chỉ kiểm tra types là array không rỗng.

## 10. Không phụ thuộc thứ tự JSON

JSON object không nên được kiểm thử theo vị trí property. Thứ tự module ở root hoặc thứ tự dependency trong array có thể thay đổi theo quá trình phát hiện module hoặc cách serializer tạo response.

Nên:

- Dùng JsonNode.path("orders") hoặc JSONPath theo tên module.
- Tìm dependency theo giá trị target thay vì giả định dependency đầu tiên là inventory.
- Kiểm tra types theo tập giá trị thay vì so sánh chuỗi JSON nguyên vẹn.
- Chỉ assert parent/nested khi ứng dụng thực sự sử dụng nested module.
- Tránh snapshot toàn bộ JSON nếu thay đổi displayName hoặc thêm module hợp lệ sẽ làm test thất bại không cần thiết.

Snapshot có thể hữu ích khi JSON là public contract được version hóa, nhưng cần review có chủ đích mỗi khi module graph thay đổi. Với kiểm thử nội bộ, assertion theo trường có ý nghĩa thường dễ bảo trì hơn.

## 11. Kiểm tra kiến trúc bằng ApplicationModules.verify()

JSON endpoint phản ánh graph mà ứng dụng expose. Để kiểm tra các quy tắc kiến trúc ở thời điểm build, dùng API ApplicationModules:

~~~java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ApplicationModuleStructureTests {

    @Test
    void verifiesModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Phương thức verify() thực hiện các kiểm tra kiến trúc mặc định, bao gồm:

- Không có dependency cycle ở cấp application module.
- Module khác chỉ truy cập API package được công khai, không truy cập package nội bộ của module đóng.
- Nếu khai báo allowedDependencies, các dependency phải tuân thủ danh sách cho phép.
- Các kiểm tra bổ sung có thể được áp dụng tùy dependency và VerificationOptions.

Đây là test kiến trúc chạy trên codebase, không gọi endpoint Actuator và không kiểm tra serialization JSON. Nên giữ cả hai loại test nếu ứng dụng dùng JSON module graph làm giao diện cho công cụ runtime.

## 12. Xử lý các tình huống test thất bại

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| GET /actuator/modulith trả 404 | Thiếu Spring Modulith Actuator dependency hoặc endpoint chưa được expose | Kiểm tra dependency và management.endpoints.web.exposure.include |
| Actuator root không có link modulith | Endpoint chưa đăng ký hoặc không được expose qua web | Kiểm tra Actuator discovery response và cấu hình endpoint |
| GET trả 401/403 | Spring Security chặn management endpoint | Gửi thông tin xác thực trong test và kiểm tra policy management |
| JSON không có module mong đợi | Sai base package, module không được phát hiện hoặc test đang khởi động application class khác | Kiểm tra application root package và module detection |
| basePackage thay đổi | Refactor package hoặc module boundary đã thay đổi | Review thay đổi kiến trúc và cập nhật expectation nếu đúng chủ đích |
| dependencies rỗng | Module không có dependency được nhận diện hoặc test đang kỳ vọng sai hướng | Kiểm tra code reference, bean dependency và event listener |
| Target không tồn tại trong root | Response không đúng contract hoặc graph có dữ liệu không như mong đợi | In response trong test failure và xác minh module metadata |
| Dependency type khác kỳ vọng | Quan hệ đã đổi từ bean reference sang event listener hoặc ngược lại | Review kiến trúc và loại dependency được tạo |
| MockMvc không gọi được endpoint trên management port riêng | Management server chạy port/context khác với mock web context | Dùng RANDOM_PORT và HTTP client test tới management port |
| Test pass nhưng kiến trúc vẫn sai | Chỉ kiểm tra endpoint response, chưa kiểm tra quy tắc source architecture | Bổ sung ApplicationModules.verify() |

Khi test thất bại, nên đọc response JSON thực tế và kiểm tra cấu hình Actuator trước khi sửa assertion. Không nên thay assertion bằng điều kiện lỏng hơn chỉ để test xanh nếu dependency thay đổi chưa được review.

## 13. Bảo mật endpoint và dữ liệu kiến trúc

JSON module graph có thể tiết lộ:
- Tên module và package nội bộ.
- Ranh giới thành phần và các quan hệ phụ thuộc.
- Những module đang sử dụng component hoặc lắng nghe event từ module khác.
- Cấu trúc nested module.

Thông tin này hữu ích cho vận hành, nhưng không nhất thiết phải public ra Internet. Trong production:

- Chỉ expose endpoint modulith trên management interface/mạng quản trị cần thiết.
- Áp dụng authentication và authorization cho Actuator endpoint.
- Nếu dùng management port riêng, cấu hình firewall/network policy phù hợp.
- Không dựa vào việc URL khó đoán để bảo vệ endpoint.
- Chỉ cấp quyền đọc module graph cho công cụ và người cần sử dụng.
- Dùng profile test để expose endpoint phục vụ kiểm thử mà không mở rộng exposure của production.

Kiểm thử nên xác nhận endpoint có thể truy cập trong test context. Chính sách security production cần được kiểm tra riêng theo cấu hình thật của ứng dụng.

## 14. Đưa kiểm thử module graph vào CI

Một pipeline CI có thể chạy theo thứ tự:

1. Compile và chạy unit tests.
2. Chạy ApplicationModules.verify() để kiểm tra ranh giới code.
3. Khởi động Spring Boot test context và kiểm tra GET /actuator/modulith.
4. Kiểm tra module bắt buộc, dependency target và dependency type.
5. Lưu response JSON khi test thất bại để hỗ trợ review thay đổi.
6. Review diff module graph khi pull request thay đổi package hoặc dependency.
7. Chỉ chấp nhận thay đổi graph khi nó phản ánh kiến trúc dự kiến và đã được người phụ trách module xem xét.

Có thể giữ một tập expectation nhỏ cho các module cốt lõi. Không nhất thiết phải hard-code toàn bộ graph nếu module được thêm thường xuyên; test invariant tổng quát sẽ giảm chi phí cập nhật.

Một thay đổi dependency có thể hợp lệ, ví dụ module notifications bắt đầu lắng nghe event OrderPlaced. Nhưng nếu một module bất ngờ truy cập package nội bộ của module khác, ApplicationModules.verify() nên phát hiện vi phạm ở bước build.

## 15. Checklist kiểm thử JSON module graph

| Hạng mục | Điều kiện đạt |
| --- | --- |
| Dependency | Có Actuator và Spring Modulith Actuator support hoặc Insight starter |
| Exposure | Test profile expose endpoint modulith |
| HTTP response | GET /actuator/modulith trả 2xx |
| Content type | Response được nhận diện là JSON |
| Root object | Mỗi property tương ứng một module technical name |
| Module metadata | displayName và basePackage đúng với expectation |
| Dependency array | Mỗi module có dependencies dạng array |
| Dependency target | Target trỏ tới module có trong root graph |
| Dependency types | Types là array và chứa type phù hợp |
| Nested modules | parent/nested được kiểm tra nếu ứng dụng sử dụng |
| JSON ordering | Test không phụ thuộc thứ tự property hoặc dependency |
| Architecture | ApplicationModules.verify() chạy riêng ở build/test |
| Security | Endpoint được giới hạn ở management interface phù hợp |
| CI | Graph contract được kiểm tra và thay đổi được review |

## 16. Ghi nhớ

**GET /actuator/modulith cung cấp JSON mô tả application modules và outgoing dependencies.** Root key là technical name của module; metadata gồm displayName, basePackage và các trường nested tùy chọn; mỗi dependency có target và types như DEFAULT, USES_COMPONENT hoặc EVENT_LISTENER.

Dùng MockMvc và Jackson để kiểm tra HTTP contract, module bắt buộc, dependency quan trọng và tính nhất quán của mọi target. Tránh so sánh toàn bộ JSON theo thứ tự hoặc yêu cầu các field tùy chọn phải xuất hiện khi ứng dụng không sử dụng nested module.

Kết hợp kiểm thử endpoint với ApplicationModules.verify() để bảo vệ cả giao diện JSON lẫn quy tắc kiến trúc source code. Đưa hai lớp kiểm tra vào CI giúp phát hiện sớm khi module graph thay đổi và buộc thay đổi đó được review trước khi triển khai.

## Tài liệu tham khảo

- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): Application Module Actuator, đường dẫn /actuator/modulith và cấu trúc JSON của module graph.
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): ApplicationModules.verify(), dependency cycles, API package access và allowed dependencies.
- [Spring Modulith — Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html): test support cho application module và cách bootstrap test.
- [Spring Boot — Actuator API](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): endpoint exposure, web endpoint và cấu hình quản trị.
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): Spring Boot test support, application context và MockMvc integration.
- [Jackson — Tree Model](https://github.com/FasterXML/jackson-databind): đọc JSON thành JsonNode để kiểm tra cấu trúc response.

> **Giới hạn phiên bản:** JSON field và dependency types trong bài dựa trên tài liệu Spring Modulith hiện hành. Hãy đối chiếu tài liệu của version đang được quản lý bởi BOM trong dự án khi nâng cấp. Nếu ứng dụng dùng management port riêng hoặc security tùy chỉnh, thay MockMvc bằng HTTP integration test phù hợp với topology thực tế.
