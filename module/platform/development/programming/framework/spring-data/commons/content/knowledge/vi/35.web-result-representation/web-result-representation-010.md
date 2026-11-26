# Kiểm thử serialization với phiên bản Jackson tương thích

## 1. Tương thích phiên bản phải đi cùng tương thích JSON

Trong chương **Biểu diễn kết quả web** của module **SPRING_DATA_COMMONS**, serialization là bước biến kết quả truy vấn thành dữ liệu mà client thực sự nhận được.

Một repository có thể trả đúng Page, projection hoặc DTO, nhưng response vẫn có thể sai nếu mapper, module hoặc HTTP message converter không phù hợp.

Cần phân biệt ba mức kiểm chứng:

| Mức | Câu hỏi |
| --- | --- |
| Tương thích thư viện | Các dependency có chạy cùng nhau mà không lỗi liên kết hoặc khởi tạo không? |
| Tương thích cấu hình | Mapper dùng ở endpoint có đủ module, mixin và serializer cần thiết không? |
| Tương thích hợp đồng | JSON có giữ đúng field, kiểu dữ liệu, metadata và media type mà client cần không? |

Ứng dụng khởi động thành công mới chỉ cung cấp một phần bằng chứng. Một test gọi writeValueAsString thành công cũng chưa chứng minh response HTTP có hợp đồng đúng.

Luồng cần quan sát:

~~~text
Query/repository
  → Page, projection hoặc DTO
  → representation được controller trả về
  → HTTP message converter được chọn
  → mapper, module và serializer tương ứng
  → bytes JSON và Content-Type
  → cách client diễn giải dữ liệu
~~~

Ví dụ chính trong bài chọn **Spring Boot 3.5, Spring Data Commons 3.5 và Jackson 2**, với Java 17 trở lên. Đây là baseline minh họa, không phải kết luận về dependency hiện có của một dự án cụ thể.

## 2. Không trộn mã Jackson 2 và Jackson 3

Jackson 3 là thay đổi major version, không tương thích API trực tiếp với Jackson 2. Việc chuyển major cần kiểm tra dependency, import, module và hành vi, không chỉ sửa số version. [Jackson 3.0: thay đổi tương thích](https://github.com/FasterXML/jackson/wiki/Jackson-Release-3.0)

| Thành phần | Baseline ví dụ Jackson 2 | Khi chuyển sang hệ hỗ trợ Jackson 3 |
| --- | --- | --- |
| Databind API | com.fasterxml.jackson.databind | tools.jackson.databind |
| Mapper thường gặp trong Boot | ObjectMapper | JsonMapper trong cấu hình JSON của Boot 4 |
| Custom serializer | API JsonSerializer của Jackson 2 | API serializer tương ứng của Jackson 3 |
| Module | Module và artifact của dòng 2 | Module hoặc chức năng tích hợp của dòng 3 |
| Spring Data integration | Bản Spring Data có hỗ trợ dòng 2 | Bản Spring Data và web integration hỗ trợ dòng 3 |

Spring Boot 3.5 cung cấp cấu hình tự động cho ObjectMapper khi Jackson có trên classpath. Spring Boot 4.0 ưu tiên Jackson 3; hỗ trợ Jackson 2 trong dòng này phục vụ chuyển đổi và đã được đánh dấu deprecated trong tài liệu. Không suy rằng chỉ thay một dependency trong Boot 3.5 là có toàn bộ tích hợp của Boot 4. [JSON trong Boot 3.5](https://docs.spring.io/spring-boot/3.5/reference/features/json.html), [JSON trong Boot 4.0](https://docs.spring.io/spring-boot/4.0/reference/features/json.html)

Một ngoại lệ quan trọng: Jackson 3 tiếp tục dùng dòng jackson-annotations 2.x cho các annotation thuộc com.fasterxml.jackson.annotation. Vì vậy, không thay hàng loạt mọi import com.fasterxml.jackson thành tools.jackson. Phải đối chiếu từng API theo hướng dẫn migration của phiên bản đích. [Quy tắc package và annotations](https://github.com/FasterXML/jackson/wiki/Jackson-Release-3.0)

Việc hai major có thể xuất hiện đồng thời trên classpath không chứng minh endpoint đang dùng mapper mong muốn. Cần kiểm tra converter thực sự xử lý response và kiểm thử qua HTTP.

## 3. Quản lý dependency theo một bộ tương thích

Trong ứng dụng Spring Boot, nên bắt đầu từ bộ dependency mà phiên bản Boot quản lý. Không mặc định jackson-core, jackson-databind và mọi module có cùng một version chỉ vì chúng cùng mang tên Jackson.

Nếu có lý do override, phải đánh giá cả bộ liên quan:

- Core, databind và annotations.
- Module cho Java time, Optional, Kotlin hoặc kiểu dữ liệu ứng dụng thực sự dùng.
- Spring Data Web và các module hỗ trợ serialization.
- Spring HATEOAS nếu response có hypermedia.
- Custom serializer, mixin và tích hợp của thư viện khác.

Boot công bố các dependency được quản lý; Jackson BOM cung cấp một tập phiên bản phối hợp cho các artifact Jackson. BOM giúp quản lý phiên bản nhưng không thay thế kiểm thử với Spring và ứng dụng của bạn. [Dependency management của Boot](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/index.html), [Jackson BOM](https://github.com/FasterXML/jackson-bom)

Không nên giải quyết một lỗi NoSuchMethodError bằng cách nâng riêng một artifact rồi dừng khi ứng dụng khởi động lại được. Cần xác định artifact nào cung cấp class đang được nạp và phiên bản nào được chọn trong runtime, sau đó kiểm tra lại hợp đồng JSON.

Không có quy tắc “Spring Data minor bao nhiêu thì Jackson minor phải giống số đó”. Hai dự án có hệ đánh số và ma trận tích hợp riêng.

## 4. Chọn representation có chủ đích trước khi viết assertion

Không nên dùng JSON mặc định của implementation PageImpl như một hợp đồng công khai lâu dài. Cấu trúc serialization của implementation có thể thay đổi khi thư viện thay đổi.

Spring Data cung cấp org.springframework.data.web.PagedModel từ dòng 3.3 để tạo biểu diễn JSON ổn định hơn cho Page. Có thể bọc tường minh bằng new PagedModel<>(page), hoặc dùng cấu hình VIA_DTO cho đường serialization tương ứng. [API PagedModel của Spring Data](https://docs.spring.io/spring-data/commons/docs/3.5.1/api/org/springframework/data/web/PagedModel.html)

Cần phân biệt:

| Representation | Hợp đồng cần kiểm thử |
| --- | --- |
| DTO do ứng dụng định nghĩa | Field, kiểu, null policy, ngày giờ và số |
| org.springframework.data.web.PagedModel | Content và metadata page |
| org.springframework.hateoas.PagedModel | Nội dung, metadata và hypermedia theo media type |
| Page được chuyển qua VIA_DTO | Cả việc cấu hình chuyển đổi thực sự có hiệu lực |
| Entity hoặc projection trực tiếp | Những property thực sự xuất hiện và nguy cơ kéo theo dữ liệu không dự định |

Ví dụ bên dưới dùng **org.springframework.data.web.PagedModel**, không dùng lớp cùng tên của Spring HATEOAS.

Một projection giới hạn dữ liệu đọc từ store không tự bảo đảm JSON đúng hợp đồng. Ngược lại, DTO chỉ có vài field cũng không tự chứng minh query chỉ đọc vài column.

## 5. Xây dựng fixture có khả năng phát hiện lỗi

Fixture kiểm thử nên chứa những giá trị dễ bị serialization làm thay đổi:

- ID lớn hơn miền số nguyên an toàn của một số client JavaScript.
- BigDecimal có nhiều chữ số.
- Instant xác định, không dùng thời gian hiện tại.
- Chuỗi Unicode tiếng Việt.
- Field null và field có giá trị.
- Trang có metadata khác số phần tử hiện tại.
- Trang rỗng.

Chính sách minh họa của API:

| Dữ liệu | Hình thức JSON đã chọn |
| --- | --- |
| ID | String để client giữ nguyên biểu diễn định danh |
| Total | Number, giữ giá trị thập phân chính xác |
| CreatedAt | String ISO-8601 thể hiện thời điểm UTC |
| Note null | Không xuất hiện field note |
| Nội dung trang | Mảng content |
| Metadata | Object page có size, number, totalElements, totalPages |

Đây là quyết định của ví dụ, không phải định dạng bắt buộc của mọi API.

### 5.1. DTO minh họa cho Jackson 2

~~~java
package com.example.serialization;

import java.math.BigDecimal;
import java.time.Instant;

import com.fasterxml.jackson.annotation.JsonFormat;
import com.fasterxml.jackson.annotation.JsonInclude;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record OrderSummary(
    @JsonFormat(shape = JsonFormat.Shape.STRING) Long id,
    String reference,
    BigDecimal total,
    @JsonFormat(shape = JsonFormat.Shape.STRING) Instant createdAt,
    String note) {
}
~~~

JsonFormat thể hiện lựa chọn về ID và thời gian ở DTO này. Nó không áp đặt chính sách cho mọi Long hay Instant trong toàn ứng dụng.

Với Jackson 2, hỗ trợ java.time thường đến từ module JavaTimeModule phù hợp. Jackson 3 tích hợp các chức năng Java time, JDK8 datatype và parameter names vào databind; không sao chép nguyên danh sách module của dòng 2 sang dòng 3. [Các module Java 8 của Jackson](https://github.com/FasterXML/jackson-modules-java8)

### 5.2. Endpoint fixture dành cho test

Controller sau trả dữ liệu cố định để tách kiểm thử representation khỏi database. Có thể đặt nó trong test source và import vào test context; không cần công bố endpoint này trong ứng dụng triển khai.

~~~java
package com.example.serialization;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.web.PagedModel;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SerializationProbeController {

  @GetMapping(
      value = "/serialization-probe/orders",
      produces = MediaType.APPLICATION_JSON_VALUE)
  public PagedModel<OrderSummary> orders() {
    var first = new OrderSummary(
        9007199254740993L,
        "Đơn hàng thử nghiệm",
        new BigDecimal("12345678901234567890.12"),
        Instant.parse("2026-01-02T03:04:05Z"),
        null);

    var second = new OrderSummary(
        9007199254740994L,
        "Đơn hàng tiếp theo",
        BigDecimal.ZERO,
        Instant.parse("2026-01-03T00:00:00Z"),
        "Đã xác nhận");

    Page<OrderSummary> page = new PageImpl<>(
        List.of(first, second),
        PageRequest.of(0, 2),
        3);

    return new PagedModel<>(page);
  }

  @GetMapping(
      value = "/serialization-probe/orders/empty",
      produces = MediaType.APPLICATION_JSON_VALUE)
  public PagedModel<OrderSummary> empty() {
    return new PagedModel<>(
        Page.<OrderSummary>empty(PageRequest.of(0, 2)));
  }
}
~~~

Mỗi public type được hiểu là một type riêng trong cùng package. Fixture tạo hai item nhưng totalElements bằng 3, nhờ đó test phát hiện việc vô tình dựng metadata từ riêng content của trang.

Đối với JSON đã chọn, field total của item đầu phải là một number có giá trị 12345678901234567890.12; id phải là string "9007199254740993". Chỉ so nội dung ký tự mà không kiểm tra kiểu có thể bỏ sót việc hai field bị đổi hình thức.

## 6. Test mapper để chẩn đoán lỗi ở DTO

Một JSON test tập trung có thể dùng JsonTest và mapper do test context cung cấp:

~~~java
package com.example.serialization;

import java.math.BigDecimal;
import java.time.Instant;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.json.JsonTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@JsonTest
class OrderSummaryJsonTest {

  @Autowired
  ObjectMapper mapper;

  @Test
  void serializesIdentifierTimeAndNullPolicy() throws Exception {
    var value = new OrderSummary(
        9007199254740993L,
        "Đơn hàng thử nghiệm",
        new BigDecimal("12.50"),
        Instant.parse("2026-01-02T03:04:05Z"),
        null);

    String json = mapper.writeValueAsString(value);
    JsonNode root = mapper.readTree(json);

    assertTrue(root.get("id").isTextual());
    assertEquals("9007199254740993",
        root.get("id").textValue());

    assertTrue(root.get("createdAt").isTextual());
    assertEquals("2026-01-02T03:04:05Z",
        root.get("createdAt").textValue());

    assertEquals("Đơn hàng thử nghiệm",
        root.get("reference").textValue());
    assertFalse(root.has("note"));
  }
}
~~~

JsonTest cấu hình các thành phần JSON phù hợp trong phạm vi test slice. Nếu ứng dụng có cấu hình serializer hoặc customizer nằm ngoài slice, cần đưa đúng cấu hình cần thiết vào test; không tạo một cấu hình giả chỉ để assertion đi qua. [JSON test slice của Boot 3.5](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html#testing.spring-boot-applications.json-tests)

Tránh dùng new ObjectMapper() trong test rồi suy rằng kết quả đại diện cho endpoint. Mapper tự tạo có thể thiếu module, naming strategy, mixin hoặc tùy biến mà ứng dụng đang dùng.

Test DTO này giúp thu hẹp nguyên nhân khi lỗi phát sinh. Nó chưa kiểm tra được việc Spring MVC chọn đúng HTTP message converter.

## 7. Test response HTTP với cấu hình ứng dụng

HTTP test đi qua đường trả response của Spring MVC, nơi HTTP message converter lựa chọn mapper và ghi body. Đây là phần không được thay thế chỉ bằng việc serialize trực tiếp một object trong test. [HTTP message conversion của Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html)

Ví dụ dưới đây dùng SpringBootTest và AutoConfigureMockMvc của Boot 3.5. Test context phải khởi tạo được cấu hình ứng dụng cùng hạ tầng test cần thiết. Nếu endpoint chịu bảo mật, hãy cung cấp ngữ cảnh xác thực phù hợp với ứng dụng.

~~~java
package com.example.serialization;

import java.math.BigDecimal;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet
    .AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Import(SerializationProbeController.class)
class PageSerializationContractTest {

  @Autowired
  MockMvc mvc;

  @Autowired
  ObjectMapper mapper;

  @Test
  void serializesPageContractThroughHttp() throws Exception {
    byte[] body = mvc.perform(
            get("/serialization-probe/orders")
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_JSON))
        .andReturn()
        .getResponse()
        .getContentAsByteArray();

    JsonNode root = readResponse(body);

    assertTrue(root.isObject());
    assertEquals(Set.of("content", "page"), fields(root));

    JsonNode rows = root.get("content");
    assertTrue(rows.isArray());
    assertEquals(2, rows.size());

    JsonNode first = rows.get(0);
    assertEquals(
        Set.of("id", "reference", "total", "createdAt"),
        fields(first));

    assertTrue(first.get("id").isTextual());
    assertEquals("9007199254740993",
        first.get("id").textValue());

    assertTrue(first.get("total").isNumber());
    assertEquals(0,
        new BigDecimal("12345678901234567890.12")
            .compareTo(first.get("total").decimalValue()));

    assertTrue(first.get("createdAt").isTextual());
    assertEquals("2026-01-02T03:04:05Z",
        first.get("createdAt").textValue());

    assertEquals("Đơn hàng thử nghiệm",
        first.get("reference").textValue());
    assertFalse(first.has("note"));
    assertEquals("Đã xác nhận",
        rows.get(1).get("note").textValue());

    JsonNode page = root.get("page");
    assertTrue(page.isObject());
    assertEquals(
        Set.of("size", "number", "totalElements", "totalPages"),
        fields(page));

    for (String name : List.of(
        "size", "number", "totalElements", "totalPages")) {
      assertTrue(page.get(name).isIntegralNumber());
    }

    assertEquals(2, page.get("size").intValue());
    assertEquals(0, page.get("number").intValue());
    assertEquals(3L, page.get("totalElements").longValue());
    assertEquals(2, page.get("totalPages").intValue());
  }

  @Test
  void emptyPageKeepsArrayAndMetadata() throws Exception {
    byte[] body = mvc.perform(
            get("/serialization-probe/orders/empty")
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_JSON))
        .andReturn()
        .getResponse()
        .getContentAsByteArray();

    JsonNode root = readResponse(body);

    assertTrue(root.get("content").isArray());
    assertEquals(0, root.get("content").size());
    assertEquals(2, root.get("page").get("size").intValue());
    assertEquals(0L,
        root.get("page").get("totalElements").longValue());
    assertEquals(0, root.get("page").get("totalPages").intValue());
  }

  private JsonNode readResponse(byte[] body) throws Exception {
    return mapper.reader()
        .with(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS)
        .readTree(body);
  }

  private static Set<String> fields(JsonNode node) {
    Set<String> result = new HashSet<>();
    node.fieldNames().forEachRemaining(result::add);
    return result;
  }
}
~~~

Điểm cần chú ý trong test:

- Response được lấy sau khi MVC hoàn tất serialization.
- Parse trực tiếp bytes giúp tránh lỗi decode Unicode do chọn charset không phù hợp khi đọc response.
- Reader dùng BigDecimal cho số thập phân để không đưa mất mát độ chính xác của double vào chính assertion.
- Cấu hình reader chỉ phục vụ phân tích response; test không sửa mapper toàn cục.
- Metadata phân biệt số item của trang hiện tại với tổng kết quả.
- Tập field chính xác là một lựa chọn nghiêm ngặt của hợp đồng minh họa.

SpringBootTest kết hợp AutoConfigureMockMvc kiểm thử trong web context mà không nhất thiết khởi động một HTTP server thật. Nếu cần kiểm tra đóng gói, reverse proxy hoặc hành vi qua mạng thật, cần lớp kiểm thử phù hợp bổ sung. [Kiểm thử ứng dụng Spring Boot](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)

Các đoạn code trong bài là ví dụ thiết kế kiểm thử; chúng không xác nhận một môi trường cụ thể đã chạy test thành công.

## 8. Không để expected JSON được sinh bằng cùng lỗi với actual

Một assertion yếu có dạng:

~~~java
String expected = mapper.writeValueAsString(expectedObject);
String actual = mapper.writeValueAsString(actualObject);

assertEquals(expected, actual);
~~~

Nếu mapper đổi tên field hoặc đổi Instant sang một hình thức không mong muốn ở cả hai phía, phép so sánh vẫn có thể qua.

Expected cần thể hiện hợp đồng độc lập:

- Tên field được ghi tường minh.
- Kiểu JSON được kiểm tra trước giá trị.
- Fixture kỳ vọng hoặc schema được quản lý như một hợp đồng.
- Giá trị quan trọng được chọn để phân biệt cách biểu diễn đúng và sai.

Đừng dùng asText để so ID rồi bỏ qua việc actual là number hay string. Một phép chuyển đổi trong assertion có thể che chính thay đổi mà test cần phát hiện.

### 8.1. So sánh cấu trúc thay vì thứ tự field

Thứ tự key trong JSON object thường không phải một phần của hợp đồng nghiệp vụ. So toàn bộ chuỗi có thể thất bại chỉ vì indentation hoặc thứ tự key đổi.

Nên so cấu trúc, kiểu và giá trị. Tuy nhiên, thứ tự phần tử trong mảng kết quả có thể là một phần của hợp đồng sort, nên không tùy tiện biến mọi array thành tập hợp để so.

Với BigDecimal, cần xác định đang kiểm tra giá trị số hay cách trình bày ký tự. Ví dụ 12.5 và 12.50 có cùng giá trị số nhưng khác representation văn bản. Nếu API yêu cầu đúng chuỗi hai chữ số thập phân, hãy thiết kế hợp đồng tương ứng rồi kiểm tra nó, không dựa vào scale hiển thị ngẫu nhiên của một JSON number.

### 8.2. Snapshot phải có chính sách thay đổi

Snapshot hữu ích khi response có nhiều field, nhưng cần tránh:

- Tự động cập nhật snapshot sau mỗi lần nâng dependency.
- Xóa mọi field khác biệt trước khi so.
- Chuẩn hóa number thành string khiến thay đổi kiểu bị bỏ qua.
- Bỏ qua toàn bộ metadata chỉ vì có một thay đổi không mong muốn.
- Giữ dữ liệu động như thời gian hiện tại khiến test thiếu ổn định.

Một snapshot thay đổi phải được đánh giá theo ảnh hưởng với client. Với response cho phép thêm field tùy chọn, có thể kiểm tra tập field bắt buộc và field cấm thay vì yêu cầu toàn bộ tập key phải bằng nhau. Chọn mức nghiêm ngặt trước khi nâng phiên bản.

## 9. Kiểm tra riêng cơ chế VIA_DTO và HAL

### 9.1. Explicit wrapper khác tự chuyển Page

Endpoint fixture trong bài trả new PagedModel<>(page). Test của nó chứng minh biểu diễn wrapper đó qua HTTP, nhưng không chứng minh cấu hình tự chuyển mọi PageImpl sang DTO đã hoạt động.

Nếu ứng dụng dựa vào VIA_DTO, cần một test của endpoint thực sự trả Page và dùng cấu hình:

~~~java
@Configuration
@EnableSpringDataWebSupport(
    pageSerializationMode =
        EnableSpringDataWebSupport.PageSerializationMode.VIA_DTO)
class DataWebSerializationConfiguration {
}
~~~

Configuration thuộc org.springframework.context.annotation; EnableSpringDataWebSupport thuộc org.springframework.data.web.config.

Test phải xác nhận response của chính đường Page đó có cấu trúc theo hợp đồng. Việc có một bean ObjectMapper không đủ chứng minh module hoặc cấu hình chuyển Page đã áp dụng.

Metadata content/page của wrapper được xác định bởi representation công khai của Spring Data, không nên thay bằng một snapshot của toàn bộ getter nội bộ PageImpl. [PagedModel và chế độ VIA_DTO](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.1/src/main/java/org/springframework/data/web/PagedModel.java)

### 9.2. HAL cần đúng converter và media type

Nếu endpoint dùng PagedResourcesAssembler và org.springframework.hateoas.PagedModel:

- Gửi Accept tương ứng, chẳng hạn application/hal+json.
- Kiểm tra Content-Type thực tế.
- Kiểm tra _embedded cùng collection relation đã chọn.
- Kiểm tra _links của trang và, nếu hợp đồng có, link của từng item.
- Kiểm thử riêng collection rỗng.
- Parse URI để kiểm tra bộ lọc và tham số phân trang trong link.

Một test dùng mapper JSON thông thường có thể serialize được object nhưng thiếu hình thức hypermedia mà client mong đợi. Với nhiều mapper hoặc converter chuyên biệt, mapper bean được inject vào test DTO chưa chắc là mapper đã ghi mọi response.

## 10. Ma trận dữ liệu giúp phát hiện thay đổi sau nâng cấp

| Trục dữ liệu | Ví dụ | Điều cần phát hiện |
| --- | --- | --- |
| Kiểu định danh | Long lớn, UUID | Đổi kiểu number/string hoặc mất biểu diễn |
| Số thập phân | Giá trị lớn, 0, số âm hợp lệ | Làm tròn, đổi kiểu, thay quy tắc hiển thị |
| Thời gian | Instant UTC, thời gian có phần lẻ | Đổi sang timestamp, mất độ chính xác |
| Null | Field null, field có giá trị | Null bị đổi thành vắng field hoặc ngược lại |
| Collection | Rỗng, một phần tử, nhiều phần tử | Mảng bị đổi thành null/object hoặc mất thứ tự |
| Unicode | Tiếng Việt và ký tự hợp lệ khác | Sai decode hoặc thay đổi nội dung |
| Page | Trang đầu, giữa, cuối và rỗng | Metadata không nhất quán |
| HAL | Có item và không có item | Mất relation hoặc link |
| Projection/DTO | Chỉ field được công bố | Xuất hiện getter hoặc thuộc tính ngoài hợp đồng |
| Kiểu đặc thù store | Kiểu thật mà API sử dụng | Thiếu module hoặc biểu diễn sai ý nghĩa |

Chỉ đưa các kiểu thực sự xuất hiện trong API vào bộ kiểm thử cần duy trì. Không cần biến test ứng dụng thành một bản kiểm thử lại toàn bộ thư viện Jackson.

Đối với LocalDateTime, không tự suy rằng nó mang timezone hoặc biểu diễn cùng ý nghĩa với Instant. Fixture và assertion phải phản ánh miền dữ liệu thực sự của DTO.

Đối với auditing, kiểm tra hình thức công bố createdAt/modifiedAt trong DTO riêng với việc auditing của store đã gán đúng thời gian hay chưa. Serialization đúng không chứng minh auditing hoạt động.

## 11. Khi chuyển từ Jackson 2 sang Jackson 3

Một quy trình có thể kiểm chứng:

1. Xác định platform Spring/Boot/Spring Data hỗ trợ major đích.
2. Ghi nhận dependency được resolve và hợp đồng JSON của phiên bản hiện tại.
3. Chuẩn bị một môi trường kiểm thử riêng với bộ dependency đích.
4. Chuyển API, custom serializer, module và cấu hình theo hướng dẫn của major đích.
5. Chạy cùng các fixture hợp đồng trên cả hai môi trường.
6. So các khác biệt về field, kiểu, metadata, media type và lỗi.
7. Quyết định khác biệt nào phải giữ tương thích, khác biệt nào cần thay đổi hợp đồng có chủ đích.

Không cố nạp hai bộ API không tương thích vào cùng một test rồi dùng mapper do test tự dựng để thay cho đường HTTP của cả hai ứng dụng.

Trong Jackson 3, nhiều API và default đã thay đổi. Không chỉ đổi import của ObjectMapper rồi cho rằng custom serializer, cấu hình module hoặc helper test sẽ biên dịch và hoạt động nguyên vẹn. Tài liệu Boot 4 dùng JsonMapper và API serializer của Jackson 3 cho cấu hình JSON tương ứng. [Tích hợp Jackson 3 của Boot](https://docs.spring.io/spring-boot/4.0/reference/features/json.html)

Các bản Spring Data mới có hạ tầng Jackson 3 riêng. Khi chuyển phiên bản, kiểm tra đúng tài liệu của dòng Spring Data được chọn; không lấy tên module từ một ví dụ Jackson 2 rồi ép vào major mới. [Spring Data Jackson modules](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html#core.web)

Mục tiêu là cùng một hợp đồng được kiểm tra qua các runtime phù hợp. Không yêu cầu mọi chi tiết implementation của mapper phải giống nhau.

## 12. Chẩn đoán lỗi theo lớp

| Biểu hiện | Khả năng cần xem xét | Bước kiểm chứng hữu ích |
| --- | --- | --- |
| NoSuchMethodError hoặc NoClassDefFoundError | Dependency hoặc module không tương thích | Xác định class/artifact thực tế trong runtime |
| Test DTO lỗi với Instant | Thiếu hỗ trợ kiểu hoặc cấu hình thời gian | Kiểm tra module và fixture bằng mapper của context |
| DTO test qua nhưng HTTP test sai | Converter, media type hoặc mapper khác nhau | Quan sát endpoint qua MVC context thật |
| Một số field biến mất sau nâng cấp | Naming, visibility hoặc annotation thay đổi | So tập property và kiểu DTO cụ thể |
| Total sai trong assertion | Mất precision khi parse hoặc mapper đổi hình thức số | Đọc bằng reader phù hợp và kiểm tra kiểu |
| Unicode sai chỉ trong test | Đọc bytes bằng charset không phù hợp | Parse bytes JSON hoặc decode UTF-8 tường minh |
| Page trả thêm field nội bộ | Dùng implementation làm hợp đồng | Dùng representation ổn định và test đúng đường |
| HAL thiếu _embedded hoặc _links | Serializer/converter hypermedia chưa phù hợp | Kiểm tra cấu hình media type và HTTP response |
| Entity phát sinh truy vấn khi ghi JSON | Getter hoặc quan hệ được truy cập muộn | Dùng DTO phù hợp và quan sát I/O toàn response |

Có thể ghi nhận class và version của mapper trong thông tin chẩn đoán test. Tuy nhiên, kiểm tra một danh sách module ID hoặc chuỗi version không thay thế assertion về hành vi.

Không xử lý lỗi bằng cách tắt một loạt tính năng kiểm tra, cho serializer trả object rỗng hoặc catch mọi lỗi rồi trả danh sách rỗng. Những thay đổi đó có thể che sai lệch hợp đồng.

## 13. Giới hạn của từng lớp bằng chứng

| Bằng chứng | Chứng minh được | Chưa chứng minh được |
| --- | --- | --- |
| Unit test của DTO | Annotation/serializer với mapper được dùng trong test | Mapper của endpoint thực tế |
| JsonTest | Cấu hình JSON trong phạm vi slice | Mọi cấu hình và converter của toàn ứng dụng |
| MockMvc trong context ứng dụng | Response qua đường MVC được khởi tạo | Hành vi proxy/mạng hoặc mọi khác biệt đóng gói |
| Test HTTP trên bản đóng gói | Response của runtime được triển khai để thử | Tính đúng đắn của mọi query nghiệp vụ |
| Test client tiêu thụ fixture | Cách client diễn giải hợp đồng | Việc server đã tải đúng dữ liệu nguồn |

Test serialization không xác nhận derived query đúng predicate, phân trang đúng ở database hoặc quyền truy cập đã được giới hạn. Những hành vi đó cần bằng chứng ở tầng tương ứng.

Ngược lại, một repository integration test trả đúng DTO cũng không chứng minh null policy, định dạng thời gian và metadata qua HTTP vẫn giữ nguyên sau nâng dependency.

## 14. Tự kiểm tra

1. Vì sao ứng dụng khởi động thành công chưa đủ kết luận Jackson tương thích với hợp đồng API?
2. new ObjectMapper() trong test có thể bỏ sót cấu hình nào của ứng dụng?
3. Vì sao cần kiểm tra id là string trước khi so giá trị?
4. Reader của test có thể làm mất độ chính xác BigDecimal như thế nào?
5. Test explicit PagedModel khác test VIA_DTO ở điểm nào?
6. Vì sao HAL cần kiểm thử media type và converter riêng?
7. Khi nâng major Jackson, vì sao không đổi mọi import bằng tìm-thay thế toàn cục?
8. Snapshot thay đổi sau nâng dependency cần được đánh giá theo tiêu chí nào?
9. Các test nào giúp phân biệt lỗi mapper, lỗi MVC và lỗi query?

Một bộ kiểm thử serialization hữu ích gắn bộ phiên bản được hỗ trợ với dữ liệu và representation thực sự được công bố. Mapper test giúp tìm nguyên nhân, còn kiểm thử HTTP giữ cho field, kiểu, metadata và media type tiếp tục phục vụ đúng client sau khi cấu hình hoặc thư viện thay đổi.
