# Serialize resource model

Trong Spring HATEOAS, các lớp RepresentationModel, EntityModel, CollectionModel và PagedModel là những đối tượng Java dùng để xây dựng representation có hypermedia. Khi controller trả một model, Spring không đơn giản chuyển mọi thuộc tính Java thành JSON theo hình dạng mặc định. Kết quả tuần tự hóa còn phụ thuộc vào media type mà client yêu cầu và Jackson module tương ứng được đăng ký trong ứng dụng.

Với HAL JSON, các Link được biểu diễn trong thuộc tính _links, nội dung collection có thể xuất hiện dưới _embedded, còn metadata phân trang được chuyển thành cấu trúc HAL tương ứng. Spring HATEOAS cung cấp serializer, deserializer và cấu hình tích hợp để thực hiện việc chuyển đổi đó. Nhờ vậy, controller có thể trả representation model mà không cần tự tạo JSON hoặc tự viết serializer cho Link.

Bài học này giải thích luồng serialize resource model, vai trò của Jackson module và HTTP message converter, cách cấu hình HAL, cách Jackson xử lý các trường dữ liệu của model, cách kiểm thử response và cách xử lý khi cần ObjectMapper tùy chỉnh hoặc media type riêng.

## 1. Resource model là đối tượng Java, representation là dữ liệu gửi cho client

Một resource model là cấu trúc Java chứa dữ liệu và các liên kết hypermedia. Ví dụ:

~~~java
import java.util.UUID;

import org.springframework.hateoas.RepresentationModel;

public class EmployeeModel extends RepresentationModel<EmployeeModel> {

    private UUID id;
    private String name;
    private String department;

    public EmployeeModel(UUID id, String name, String department) {
        this.id = id;
        this.name = name;
        this.department = department;
    }

    public UUID getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getDepartment() {
        return department;
    }
}
~~~

Model có hai nhóm thông tin:

- Dữ liệu nghiệp vụ mà client cần đọc, ví dụ id, name và department.
- Link mà Spring HATEOAS quản lý qua RepresentationModel, ví dụ self, manager hoặc projects.

Khi ứng dụng dùng HAL JSON, client có thể nhận response:

~~~json
{
  "id": "EMP-42",
  "name": "An Nguyen",
  "department": "Engineering",
  "_links": {
    "self": {
      "href": "/employees/EMP-42"
    },
    "projects": {
      "href": "/employees/EMP-42/projects"
    }
  }
}
~~~

Đây là representation HAL của model Java. Tên trường dữ liệu vẫn theo cấu hình Jackson, còn link được chuyển thành cấu trúc HAL do module hypermedia đảm nhiệm.

Không nên nhầm resource model với entity của database. Model là hợp đồng representation mà API công bố. Nó có thể chứa DTO, dữ liệu tổng hợp và link, trong khi entity persistence có cấu trúc và quan hệ riêng.

## 2. Luồng serialize trong Spring MVC

Khi một controller trả representation model, Spring MVC chọn HttpMessageConverter phù hợp với kiểu dữ liệu và media type của response. Converter dùng Jackson để serialize object thành byte JSON. Với Spring WebFlux, vai trò tương ứng thuộc về encoder và HttpMessageWriter trong hệ thống codec reactive.

Luồng xử lý tổng quát:

~~~text
Controller
    |
    v
RepresentationModel / EntityModel / CollectionModel
    |
    v
Spring MVC return-value handling
    |
    v
HttpMessageConverter phù hợp
    |
    v
Jackson mapper + hypermedia module
    |
    v
HAL JSON hoặc media type được chọn
    |
    v
HTTP response
~~~

Có ba yếu tố quan trọng:

1. **Kiểu model:** Spring HATEOAS nhận diện RepresentationModel và các kiểu con như EntityModel, CollectionModel, PagedModel.
2. **Media type:** header Accept của client và cấu hình produces của endpoint tham gia quyết định định dạng response.
3. **Jackson configuration:** module hypermedia cung cấp serializer và mixin để chuyển model và Link sang cấu trúc của media type.

Nếu client gửi Accept: application/hal+json, ứng dụng có cấu hình HAL phù hợp có thể trả Content-Type: application/hal+json. Nếu client yêu cầu application/json thông thường, response có thể dùng cách serialize JSON mặc định tùy cấu hình và converter được đăng ký.

## 3. Jackson module của Spring HATEOAS

Jackson module là nơi đăng ký serializer, deserializer, mixin và các quy tắc chuyển đổi cho kiểu dữ liệu cụ thể. Spring HATEOAS cung cấp module dành cho hypermedia media type.

Với HAL, module đảm nhiệm những việc như:

- Serialize Link thành object có href và các metadata liên quan.
- Chuyển links của RepresentationModel thành thuộc tính _links.
- Serialize nội dung EntityModel cùng các link của nó.
- Chuyển nội dung CollectionModel thành collection representation và relation phù hợp dưới _embedded.
- Xử lý các trường hợp nhiều link cùng relation, URI template và CURIE.
- Hỗ trợ deserialize representation hypermedia khi client đọc response.

Trong API Spring HATEOAS hiện hành, lớp HAL module là HalJacksonModule trong package org.springframework.hateoas.mediatype.hal. Các phiên bản cũ hơn có thể dùng tên Jackson2HalModule. Package Jackson cũng thay đổi theo thế hệ Jackson: dòng Jackson 2 dùng com.fasterxml.jackson, trong khi dòng Jackson 3 dùng tools.jackson. Hãy đối chiếu phiên bản Spring HATEOAS và Jackson của dự án trước khi sao chép import hoặc tự đăng ký module.

Trong ứng dụng thông thường, không cần tự khởi tạo HAL module. Cấu hình hypermedia của Spring HATEOAS sẽ đăng ký các thành phần cần thiết cho media type được bật.

## 4. Bật hỗ trợ hypermedia để serialize model

Có thể bật HAL bằng EnableHypermediaSupport:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;

@Configuration
@EnableHypermediaSupport(
    type = EnableHypermediaSupport.HypermediaType.HAL
)
public class HypermediaConfiguration {
}
~~~

Cấu hình này yêu cầu Spring HATEOAS kích hoạt hạ tầng cho HAL, bao gồm các Jackson module cần thiết để serialize EntityModel và CollectionModel theo cấu trúc hypermedia.

Khi dùng Spring Boot và starter Spring HATEOAS, auto-configuration có thể đã thiết lập hỗ trợ hypermedia. Hãy kiểm tra cấu hình thực tế của ứng dụng trước khi thêm EnableHypermediaSupport thủ công. Tránh đăng ký lặp các converter hoặc module vì có thể khiến content negotiation và serializer trở nên khó dự đoán.

Có thể giới hạn web stack nếu ứng dụng kết hợp nhiều stack nhưng chỉ muốn kích hoạt hypermedia cho một stack cụ thể. Ví dụ, một ứng dụng MVC có thể dùng WebClient cho outbound request nhưng không muốn áp dụng cấu hình hypermedia cho mọi thành phần client.

## 5. Content negotiation quyết định cách model được serialize

Cùng một kiểu Java có thể được biểu diễn bằng nhiều media type. Client thể hiện định dạng mong muốn qua Accept.

Ví dụ request HAL:

~~~http
GET /employees/EMP-42 HTTP/1.1
Accept: application/hal+json
~~~

Controller có thể công bố rõ media type:

~~~java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

public record EmployeeRepresentation(
    UUID id,
    String name,
    String department
) {}

@GetMapping(
    value = "/employees/{id}",
    produces = MediaTypes.HAL_JSON_VALUE
)
public EntityModel<EmployeeRepresentation> one(@PathVariable UUID id) {
    Employee employee = service.findById(id);

    return EntityModel.of(
        new EmployeeRepresentation(
            employee.getId(), employee.getName(), employee.getDepartment()
        ),
        linkTo(methodOn(EmployeeController.class).one(id))
            .withSelfRel()
    );
}
~~~

Nếu controller trả EntityModel và converter HAL được cấu hình, Spring có thể serialize response theo HAL. Header response tương ứng:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
~~~

Nếu client không gửi Accept phù hợp hoặc endpoint không công bố media type đó, Spring có thể chọn converter khác hoặc trả lỗi content negotiation. Vì vậy, kiểm thử cần xác nhận cả body và Content-Type, không chỉ kiểm tra status 200.

## 6. EntityModel được serialize như thế nào?

EntityModel<T> bọc một nội dung và một tập hợp link. Ví dụ:

~~~java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

Employee employee = service.findById(id);

EmployeeRepresentation body = new EmployeeRepresentation(
    employee.getId(),
    employee.getName(),
    employee.getDepartment()
);

EntityModel<EmployeeRepresentation> model = EntityModel.of(
    body,
    linkTo(methodOn(EmployeeController.class).one(id)).withSelfRel(),
    linkTo(methodOn(EmployeeProjectController.class).all(id))
        .withRel("projects")
);
~~~

Với HAL JSON, nội dung được biểu diễn như các thuộc tính của resource và link được đưa vào _links:

~~~json
{
  "id": "EMP-42",
  "name": "An Nguyen",
  "department": "Engineering",
  "_links": {
    "self": {
      "href": "/employees/EMP-42"
    },
    "projects": {
      "href": "/employees/EMP-42/projects"
    }
  }
}
~~~

EntityModel không tạo một trường JSON có tên content để bọc toàn bộ DTO trong HAL. Serializer HAL trình bày nội dung như một resource và đặt link trong _links theo quy ước media type.

Nếu chỉ serialize DTO EmployeeRepresentation mà không bọc trong EntityModel hoặc model kế thừa RepresentationModel, response không tự có link hypermedia. Việc tạo link và lựa chọn model là trách nhiệm của ứng dụng.

## 7. CollectionModel và _embedded

CollectionModel<T> biểu diễn một tập hợp tài nguyên. Với HAL, các phần tử thường được đặt dưới _embedded theo collection relation.

Ví dụ Java:

~~~java
import java.util.List;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

List<EntityModel<EmployeeListItem>> employees =
    service.findAll().stream()
        .map(assembler::toModel)
        .toList();

CollectionModel<EntityModel<EmployeeListItem>> model =
    CollectionModel.of(
        employees,
        linkTo(methodOn(EmployeeController.class).all())
            .withSelfRel()
    );
~~~

Response HAL minh họa:

~~~json
{
  "_links": {
    "self": {
      "href": "/employees"
    }
  },
  "_embedded": {
    "employees": [
      {
        "id": "EMP-42",
        "name": "An Nguyen",
        "_links": {
          "self": {
            "href": "/employees/EMP-42"
          }
        }
      },
      {
        "id": "EMP-43",
        "name": "Binh Tran",
        "_links": {
          "self": {
            "href": "/employees/EMP-43"
          }
        }
      }
    ]
  }
}
~~~

Tên relation collection có thể được xác định qua LinkRelationProvider hoặc annotation Relation:

~~~java
import java.util.UUID;

import org.springframework.hateoas.server.core.Relation;

@Relation(
    itemRelation = "employee",
    collectionRelation = "employees"
)
public record EmployeeListItem(
    UUID id,
    String name,
    String department
) {}
~~~

Nếu không khai báo relation tường minh, provider mặc định có thể suy ra tên từ kiểu representation. Khi tên class Java thay đổi nhưng relation công khai cần giữ ổn định, hãy khai báo relation rõ ràng và kiểm thử JSON sau serialize.

## 8. Serialize PagedModel và metadata phân trang

PagedModel<T> biểu diễn một collection có metadata phân trang. Khi serialize theo HAL, response có thể chứa _embedded, _links và page metadata.

Ví dụ response:

~~~json
{
  "_embedded": {
    "employees": [
      {
        "id": "EMP-42",
        "name": "An Nguyen",
        "_links": {
          "self": {
            "href": "/employees/EMP-42"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "/employees?page=0&size=20"
    },
    "next": {
      "href": "/employees?page=1&size=20"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 51,
    "totalPages": 3,
    "number": 0
  }
}
~~~

Hình dạng cụ thể phụ thuộc cấu hình media type và relation provider. Điểm quan trọng là PagedModel giữ cả collection content lẫn metadata điều hướng. Không nên tự tạo object JSON page bên trong DTO nếu Spring HATEOAS đã cung cấp PagedModel phù hợp với hợp đồng.

Khi collection rỗng, cần giữ thông tin kiểu phần tử bằng fallback type nếu hạ tầng cần nhận diện generic payload. Việc này đặc biệt quan trọng với các RepresentationModelProcessor nhắm đến collection.

## 9. Jackson annotation áp dụng cho dữ liệu của model

Các trường dữ liệu thông thường của representation model vẫn tuân theo Jackson property model. Có thể dùng annotation để kiểm soát tên trường, quyền đọc/ghi và việc bỏ qua thuộc tính.

Ví dụ:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;

public class EmployeeModel extends RepresentationModel<EmployeeModel> {

    private UUID id;

    @JsonProperty("displayName")
    private String name;

    private String department;

    @JsonIgnore
    private String internalNote;

    // constructors, getters and setters
}
~~~

Kết quả có thể công bố displayName thay vì name và bỏ internalNote khỏi JSON. Link hypermedia vẫn được serializer HAL xử lý theo cấu trúc _links.

Các annotation hữu ích:

| Annotation | Tác dụng thường dùng |
|---|---|
| JsonProperty | Đặt tên property hoặc điều chỉnh quyền truy cập |
| JsonIgnore | Bỏ property khỏi serialization/deserialization |
| JsonInclude | Điều khiển điều kiện đưa property vào JSON, ví dụ bỏ null |
| JsonPropertyOrder | Điều khiển thứ tự property dữ liệu trong JSON |
| JsonFormat | Định dạng ngày giờ hoặc kiểu dữ liệu được hỗ trợ |
| JsonAlias | Khai báo tên thay thế khi deserialize |

Các annotation ở trên thuộc package com.fasterxml.jackson.annotation và vẫn được giữ nguyên khi chuyển từ Jackson 2 sang Jackson 3. Phần databind của Jackson 3 chuyển sang package tools.jackson; vì vậy, hãy phân biệt package annotation với package mapper, serializer và deserializer.

Hãy áp dụng annotation cho dữ liệu representation mà ứng dụng sở hữu. Tránh gắn annotation tùy tiện lên cấu trúc nội bộ của Link hoặc RepresentationModel để cố thay đổi hình dạng hypermedia; phần đó thuộc serializer và module của media type.

## 10. Kiểm soát null và trường dữ liệu không cần công bố

Một model có thể có thuộc tính null. Jackson có thể serialize null hoặc bỏ qua tùy cấu hình và annotation.

Ví dụ:

~~~java
import java.util.UUID;

import com.fasterxml.jackson.annotation.JsonInclude;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record EmployeeSummary(
    UUID id,
    String name,
    String middleName
) {}
~~~

Nếu middleName null, property đó có thể không xuất hiện trong JSON. Đây là quyết định ở tầng dữ liệu của representation; nó không có nghĩa relation tương ứng trong _links cũng tự động bị bỏ.

Đối với link tùy chọn, hãy quyết định thêm hoặc không thêm link ngay khi xây model:

~~~java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

Link selfLink = linkTo(
    methodOn(EmployeeController.class).one(employee.getId())
).withSelfRel();

EntityModel<EmployeeRepresentation> model =
    EntityModel.of(body, selfLink);

if (employee.hasManager()) {
    model.add(
        linkTo(methodOn(EmployeeController.class).manager(employee.getId()))
            .withRel("manager")
    );
}
~~~

Không nên dùng null để biểu diễn link không khả dụng. Một relation không được công bố nên được bỏ khỏi tập hợp link, giúp client phân biệt rõ giữa link hiện có và link không có trong response.

## 11. Không serialize trực tiếp JPA entity thay cho representation model

JPA entity có thể chứa lazy association, quan hệ hai chiều, proxy persistence và trường nội bộ. Serialize trực tiếp entity có thể gây:

- Vòng lặp giữa quan hệ hai chiều.
- Lazy loading và truy vấn N+1 trong lúc serialize.
- Lộ trường nội bộ không thuộc hợp đồng API.
- Response phụ thuộc vào cấu trúc persistence.
- Lỗi khi session hoặc persistence context đã đóng.

Nên ánh xạ entity sang DTO hoặc representation model trước khi serialize:

~~~java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

public record EmployeeDetail(
    UUID id,
    String name,
    String department
) {}

public EntityModel<EmployeeDetail> toModel(Employee employee) {
    EmployeeDetail body = new EmployeeDetail(
        employee.getId(),
        employee.getName(),
        employee.getDepartment().getName()
    );

    Link self = linkTo(
        methodOn(EmployeeController.class).one(employee.getId())
    ).withSelfRel();
    return EntityModel.of(body, self);
}
~~~

Ví dụ giả định department đã được tải hoặc query đã chọn sẵn department name. DTO giúp kiểm soát trường dữ liệu, nhưng chiến lược fetch vẫn phải được thiết kế ở service/repository.

## 12. Jackson mapper tùy chỉnh và rủi ro mất hypermedia module

Trong ứng dụng Spring, mapper được quản lý bởi cấu hình Jackson và các message converter. Với Jackson 2, kiểu mapper thường dùng là ObjectMapper; với Jackson 3, JsonMapper là mapper dành cho JSON và kế thừa ObjectMapper trong namespace tools.jackson. Nếu tự tạo mapper bằng constructor hoặc builder mặc định rồi gọi writeValueAsString(model), mapper đó có thể không có các module hypermedia cần thiết.

Kết quả có thể là:

- Link bị serialize như object Java thông thường.
- RepresentationModel xuất hiện với hình dạng không phải HAL.
- _links hoặc _embedded không được tạo đúng.
- Deserialization của EntityModel hoặc CollectionModel không hoạt động.

Ví dụ cách dễ gây lỗi:

~~~java
// Jackson 2
com.fasterxml.jackson.databind.ObjectMapper mapper2 =
    new com.fasterxml.jackson.databind.ObjectMapper();

// Jackson 3
tools.jackson.databind.json.JsonMapper mapper3 =
    tools.jackson.databind.json.JsonMapper.builder().build();
~~~

Hai đoạn trên tạo mapper độc lập, không kế thừa cấu hình từ Spring ApplicationContext. Không nên dùng chúng để kiểm tra hoặc tạo HAL response trong ứng dụng nếu chưa đăng ký đúng module và cấu hình hypermedia.

Trong controller, hãy để Spring MVC/WebFlux sử dụng converter hoặc codec đã được cấu hình. Nếu cần serialize thủ công, hãy dùng mapper đã được cấu hình đầy đủ cho media type tương ứng hoặc đăng ký Jackson module hypermedia thích hợp theo phiên bản Spring HATEOAS đang dùng.

## 13. Tùy chỉnh JsonMapper hoặc ObjectMapper trong Spring Boot

Nếu cần tùy chỉnh Jackson cho trường dữ liệu riêng, ưu tiên bổ sung cấu hình vào mapper do Spring Boot quản lý thay vì thay thế mapper bằng một instance mới.

Với Spring Boot 4 và Jackson 3, có thể dùng JsonMapperBuilderCustomizer để bổ sung cấu hình cho builder mà Boot đang quản lý:

~~~java
import org.springframework.boot.jackson.autoconfigure.JsonMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import tools.jackson.databind.SerializationFeature;

@Configuration
public class JacksonConfiguration {

    @Bean
    JsonMapperBuilderCustomizer employeeJacksonCustomizer() {
        return builder -> builder.enable(
            SerializationFeature.INDENT_OUTPUT
        );
    }
}
~~~

Nếu chỉ cần bật pretty print, có thể cấu hình bằng property thay vì viết customizer:

~~~properties
spring.jackson.serialization.indent-output=true
~~~

Với Spring Boot 3 và Jackson 2, API tương ứng là Jackson2ObjectMapperBuilderCustomizer cùng ObjectMapper của package com.fasterxml.jackson. Hãy giữ ví dụ cấu hình theo đúng thế hệ đang dùng; không trộn builder Jackson 2 với JsonMapper của Jackson 3.

Không đăng ký lại HAL module chỉ vì muốn đổi định dạng ngày hoặc tên một property. Cấu hình hypermedia của Spring HATEOAS và cấu hình Jackson chung cần được phối hợp; việc thay toàn bộ mapper có thể làm mất module đã được auto-configuration đăng ký.

## 14. Khi nào cần custom serializer?

Custom serializer phù hợp khi một kiểu dữ liệu nghiệp vụ cần một representation JSON đặc biệt mà annotation hoặc cấu hình chuẩn không đủ diễn đạt.

Ví dụ, kiểu Money có thể cần biểu diễn thành object gồm amount và currency:

~~~java
import java.math.BigDecimal;

public record Money(
    BigDecimal amount,
    String currency
) {}
~~~

Một custom serializer có thể chuyển Money thành:

~~~json
{
  "amount": 125000,
  "currency": "VND"
}
~~~

Nên đăng ký serializer cho kiểu Money thay vì viết serializer thay thế toàn bộ RepresentationModel. Khi đó, serializer hypermedia vẫn xử lý Link và cấu trúc model; custom serializer chỉ phụ trách property nghiệp vụ.

Nếu custom serializer thay thế serializer của RepresentationModel, EntityModel hoặc CollectionModel, ứng dụng phải chịu trách nhiệm tái tạo đúng cấu trúc media type. Đây là phạm vi phức tạp hơn nhiều và thường chỉ cần khi phát triển một media type riêng.

## 15. Tích hợp custom media type qua HypermediaMappingInformation

Spring HATEOAS cung cấp SPI HypermediaMappingInformation để đăng ký một media type hypermedia riêng. Một cấu hình custom thường cung cấp:

- Danh sách media type được hỗ trợ.
- Jackson module cho serializer/deserializer của representation model.
- LinkDiscoverer để client tìm link theo relation.
- Cấu hình JsonMapper nâng cao nếu cần handler instantiator hoặc thành phần khác.

Ví dụ skeleton:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.client.LinkDiscoverer;
import org.springframework.hateoas.config.HypermediaMappingInformation;
import org.springframework.http.MediaType;
import tools.jackson.databind.JacksonModule;

@Configuration
public class VendorMediaTypeConfiguration
        implements HypermediaMappingInformation {

    @Override
    public List<MediaType> getMediaTypes() {
        return List.of(
            MediaType.parseMediaType("application/vnd.acme.resource+json")
        );
    }

    @Override
    public JacksonModule getJacksonModule() {
        return new AcmeHypermediaModule();
    }

    @Bean
    LinkDiscoverer acmeLinkDiscoverer() {
        return new AcmeLinkDiscoverer();
    }
}
~~~

Tên JacksonModule và package cụ thể phải khớp với thế hệ Jackson mà Spring HATEOAS đang dùng. Trong API hiện hành của Spring HATEOAS 3.x, Jackson 3 sử dụng package tools.jackson; các phiên bản cũ hơn dùng Jackson 2 với com.fasterxml.jackson.

Custom module thường cần xử lý các kiểu RepresentationModel, EntityModel, CollectionModel và PagedModel. Serializer chuyển các model Java sang kiểu dữ liệu đặc thù của media type; deserializer thực hiện chiều ngược lại nếu client cần đọc representation đó.

Spring HATEOAS quét ApplicationContext để tìm bean triển khai HypermediaMappingInformation. Không cần tự đăng ký SPI cũ qua spring.factories nếu phiên bản hiện hành đã dùng cơ chế bean này.

## 16. Phân biệt serializer của media type và serializer của domain

Có hai phạm vi tùy chỉnh khác nhau:

| Loại serializer | Đối tượng xử lý | Mục tiêu |
|---|---|---|
| Serializer domain | Kiểu nghiệp vụ như Money, Address, Identifier | Quy định cách serialize một property |
| Serializer hypermedia | RepresentationModel, EntityModel, CollectionModel, PagedModel, Link | Tạo cấu trúc của media type |
| Deserializer domain | Kiểu nghiệp vụ nhận từ JSON | Chuyển JSON thành kiểu Java |
| Deserializer hypermedia | Resource model và link | Đọc representation hypermedia thành model Java |

Nếu chỉ cần đổi định dạng ngày, số tiền hoặc identifier, hãy dùng serializer domain. Nếu cần thay cấu trúc _links, _embedded hoặc metadata media type, đó là trách nhiệm của serializer hypermedia.

Trộn hai phạm vi này có thể khiến thay đổi nhỏ ở một trường nghiệp vụ làm hỏng toàn bộ response hypermedia.

## 17. Deserialize resource model ở phía client

Jackson module không chỉ phục vụ serialize response phía server. Khi client muốn đọc HAL thành EntityModel hoặc CollectionModel, nó cũng cần cấu hình hypermedia decoder phù hợp.

Với WebTestClient, có thể áp dụng HypermediaWebTestClientConfigurer. Khi dùng WebClient, có HypermediaWebClientConfigurer để đăng ký encoder và decoder cho media type hypermedia. Với RestTemplate, có HypermediaRestTemplateConfigurer để đăng ký message converter tương ứng.

Ví dụ giải mã response thành EntityModel:

~~~java
client.get()
    .uri("/employees/{id}", employeeId)
    .accept(MediaTypes.HAL_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectBody(
        new TypeReferences.EntityModelType<EmployeeRepresentation>() {}
    )
    .consumeWith(result -> {
        EntityModel<EmployeeRepresentation> model =
            result.getResponseBody();

        assertThat(model).isNotNull();
        assertThat(model.hasLink(IanaLinkRelations.SELF)).isTrue();
    });
~~~

TypeReferences giữ thông tin generic để decoder biết kiểu content. Nếu dùng mapper không có module hypermedia hoặc không đăng ký decoder cho media type, việc deserialize có thể thất bại hoặc mất thông tin link.

## 18. Kiểm thử serialization bằng MockMvc

Kiểm thử HTTP là cách đáng tin cậy để xác nhận controller, message converter, Jackson module và content negotiation phối hợp đúng.

~~~java
mockMvc.perform(get("/employees/{id}", employeeId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$.id").value(employeeId.toString()))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.projects.href").exists());
~~~

Với collection:

~~~java
mockMvc.perform(get("/employees")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._embedded.employees").isArray());
~~~

Nên kiểm tra cả trường dữ liệu và hypermedia. Một response có thể serialize đúng DTO nhưng thiếu _links nếu mapper hoặc converter không có cấu hình hypermedia.

## 19. Kiểm thử serializer khi dùng mapper trực tiếp

Nếu ứng dụng có lý do phải serialize thủ công, hãy lấy mapper đã được Spring cấu hình và kiểm tra kết quả thực tế. Không tạo một mapper mới trong test rồi kết luận module Spring HATEOAS bị lỗi.

Có thể viết integration test để lấy mapper bean:

~~~java
import java.util.UUID;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class HypermediaSerializationTest {

    @Autowired
    JsonMapper jsonMapper;

    private final UUID employeeId = UUID.randomUUID();

    @Test
    void serializesRepresentationModelWithLinks() throws Exception {
        EmployeeRepresentation body =
            new EmployeeRepresentation(
                employeeId, "An Nguyen", "Engineering"
            );

        EntityModel<EmployeeRepresentation> model =
            EntityModel.of(
                body,
                Link.of("/employees/" + employeeId, IanaLinkRelations.SELF)
            );

        String json = jsonMapper.writeValueAsString(model);

        JsonNode root = jsonMapper.readTree(json);

        assertThat(root.path("_links").path("self").path("href").asText())
            .isEqualTo("/employees/" + employeeId);
    }
}
~~~

Ví dụ trên giả định JsonMapper được Spring HATEOAS cấu hình cho HAL trong ứng dụng Spring Boot 4/Jackson 3. Với Spring Boot 3/Jackson 2, hãy inject ObjectMapper của com.fasterxml.jackson.databind. Nếu ứng dụng bật nhiều media type hoặc dùng mapper chung cho JSON mặc định, kết quả phụ thuộc mapper và module được đăng ký. Khi cần xác nhận chính xác media type HAL, test MockMvc với Accept HAL JSON vẫn là kiểm thử quan trọng hơn vì nó đi qua converter thực tế.

## 20. Những lỗi thường gặp khi serialize resource model

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng ObjectMapper mới không có module hypermedia | Link bị serialize như object Java thông thường | Dùng mapper/converter đã cấu hình hoặc đăng ký module phù hợp |
| Trả DTO thuần thay vì RepresentationModel | Response không có _links | Bọc bằng EntityModel hoặc kế thừa RepresentationModel |
| Client gửi Accept sai media type | Converter khác được chọn hoặc content negotiation thất bại | Kiểm tra Accept và produces |
| Thay toàn bộ ObjectMapper của Boot | Mất module và customizer đã được cấu hình | Bổ sung cấu hình vào mapper do Spring quản lý |
| Tự viết serializer cho RepresentationModel không đầy đủ | Mất _links, _embedded hoặc metadata | Dùng module hypermedia hoặc triển khai đúng SPI |
| Serialize trực tiếp JPA entity | Vòng tham chiếu, lazy loading hoặc lộ trường nội bộ | Ánh xạ sang DTO/representation model |
| Không khai báo relation collection ổn định | Tên _embedded thay đổi khi kiểu Java đổi | Dùng @Relation và kiểm thử response |
| Không kiểm thử Content-Type | Response có thể là JSON thường thay vì HAL | Assert contentTypeCompatibleWith |
| Chỉ kiểm thử ObjectMapper đơn lẻ | Không phát hiện converter hoặc content negotiation sai | Bổ sung MockMvc/WebTestClient integration test |
| Sao chép import Jackson từ phiên bản khác | Lỗi biên dịch hoặc xung đột module | Kiểm tra thế hệ Jackson và Spring HATEOAS của dự án |

## 21. Quy trình serialize resource model

Khi triển khai endpoint trả representation model, hãy thực hiện theo trình tự:

1. Chọn RepresentationModel, EntityModel, CollectionModel hoặc PagedModel theo loại tài nguyên.
2. Ánh xạ entity sang DTO/model để kiểm soát trường dữ liệu công khai.
3. Thêm Link bằng API Spring HATEOAS và chọn relation ổn định.
4. Bật hypermedia support phù hợp, ví dụ HAL.
5. Để Spring MVC hoặc WebFlux sử dụng message converter/writer đã được cấu hình.
6. Xác định media type endpoint công bố và kiểm tra content negotiation.
7. Chỉ tùy chỉnh ObjectMapper khi có nhu cầu thực tế, giữ nguyên module hypermedia.
8. Dùng custom serializer cho kiểu nghiệp vụ riêng; dùng custom hypermedia module khi phát triển media type riêng.
9. Kiểm thử dữ liệu, _links, _embedded, Content-Type và trường hợp collection rỗng.
10. Nếu client cần deserialize, cấu hình decoder hypermedia và giữ generic type bằng TypeReferences.

Serialize resource model là bước chuyển đổi representation Java thành định dạng mà client hiểu được. Spring HATEOAS kết hợp Jackson module và HTTP message converter để chuyển Link cùng các model tài nguyên thành cấu trúc hypermedia theo media type. Khi cấu hình đúng, ứng dụng có thể tập trung vào dữ liệu, relation và affordance; serializer đảm nhiệm cách những thành phần đó xuất hiện trong response. Việc giữ ObjectMapper nhất quán, tách DTO khỏi entity và kiểm thử qua HTTP giúp hợp đồng hypermedia ổn định khi ứng dụng phát triển.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation – Representation Models](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [RepresentationModel API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/RepresentationModel.html)
- [HalJacksonModule API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/hal/HalJacksonModule.html)
- [HypermediaMappingInformation API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/config/HypermediaMappingInformation.html)
- [EnableHypermediaSupport API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/config/EnableHypermediaSupport.html)
- [Spring Boot JSON support and Jackson 3](https://docs.spring.io/spring-boot/reference/features/json.html)
- [Customizing the Spring Boot JsonMapper](https://docs.spring.io/spring-boot/how-to/spring-mvc.html)
- [Spring Framework HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html)

