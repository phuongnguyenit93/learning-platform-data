# Ánh xạ interface hoặc lớp trừu tượng sang kiểu triển khai

Trong domain model, một thuộc tính có thể được khai báo bằng **interface** hoặc **abstract class** để giảm phụ thuộc vào một implementation cụ thể. Khi Spring Data REST nhận JSON và nhờ Jackson tạo object, Jackson cần biết class cụ thể nào phải được khởi tạo. Nếu chỉ biết kiểu khai báo là interface hoặc lớp trừu tượng, Jackson không thể tự tạo instance.

Spring Data REST hướng dẫn giải quyết trường hợp này bằng cách đăng ký ánh xạ kiểu trong một Jackson **Module**. Với một interface có một implementation mặc định, **SimpleAbstractTypeResolver** cho phép khai báo rõ kiểu trừu tượng nào phải được chuyển thành kiểu triển khai nào.

## Mục tiêu

Sau bài này, bạn có thể:

- Hiểu vì sao Jackson không thể khởi tạo trực tiếp interface hoặc abstract class.
- Đăng ký ánh xạ interface/lớp trừu tượng sang implementation bằng **SimpleAbstractTypeResolver**.
- Cấu hình Jackson ObjectMapper mà Spring Data REST thực sự sử dụng.
- Chọn giữa ánh xạ cố định, annotation **@JsonDeserialize** và polymorphic type mapping.
- Phân biệt ánh xạ JSON với mapping persistence của JPA và cách Spring Data REST biểu diễn association.
- Kiểm tra request POST/PUT/PATCH sau khi cấu hình.

## 1. Vấn đề khi thuộc tính dùng interface

Giả sử domain model có một hợp đồng mô tả tùy chọn xử lý:

~~~java
public interface TaskOption {
    String getName();
    String getValue();
}
~~~

Implementation cụ thể:

~~~java
@Entity
public class TaskOptionEntity implements TaskOption {

    @Id
    @GeneratedValue
    private Long id;

    private String name;
    private String value;

    protected TaskOptionEntity() {
    }

    public TaskOptionEntity(String name, String value) {
        this.name = name;
        this.value = value;
    }

    @Override
    public String getName() {
        return name;
    }

    @Override
    public String getValue() {
        return value;
    }
}
~~~

Entity cha khai báo collection bằng interface:

~~~java
@Entity
public class WorkItem {

    @Id
    @GeneratedValue
    private Long id;

    private String title;

    @OneToMany(
        targetEntity = TaskOptionEntity.class,
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<TaskOption> options = new ArrayList<>();
}
~~~

Khai báo interface giúp domain code phụ thuộc vào hợp đồng TaskOption. Implementation được chọn là TaskOptionEntity.

Khi Jackson đọc JSON để tạo một WorkItem mới, nó gặp thuộc tính có kiểu khai báo List<TaskOption>. Jackson biết phần tử phải tuân theo interface TaskOption, nhưng interface không phải class có thể khởi tạo. Nếu không có thêm thông tin, quá trình deserialize có thể thất bại với lỗi kiểu không thể tạo instance cho abstract type.

Spring Data REST mô tả đúng trường hợp này trong phần **Abstract Class Registration**: một entity có thuộc tính collection kiểu interface có thể được serialize, nhưng khi POST dữ liệu mới, Jackson không biết implementation nào cần tạo. Ta phải cung cấp type mapping bằng annotation hoặc Jackson Module.

> Ví dụ có quan hệ JPA nên implementation cụ thể vẫn phải đáp ứng quy tắc mapping của JPA. Thuộc tính targetEntity trong ví dụ chỉ rõ entity class dùng cho quan hệ persistence; nó không thay thế cấu hình deserialize của Jackson.

## 2. Dùng SimpleAbstractTypeResolver

Jackson cung cấp **SimpleAbstractTypeResolver** để ánh xạ một kiểu abstract sang một subtype cụ thể.

Với ví dụ trên, ánh xạ cần đăng ký là:

~~~java
new SimpleAbstractTypeResolver()
    .addMapping(TaskOption.class, TaskOptionEntity.class);
~~~

Ý nghĩa:

- Khi Jackson cần deserialize một giá trị được khai báo là TaskOption, resolver chọn TaskOptionEntity.
- TaskOptionEntity phải implement TaskOption hoặc kế thừa kiểu abstract được ánh xạ.
- Jackson tiếp tục dùng các quy tắc binding thông thường để gán các thuộc tính JSON vào implementation.
- Không cần thêm trường discriminator vào JSON khi chỉ có một implementation cố định cho interface đó.

Resolver này chỉ xử lý việc chọn kiểu cụ thể cho abstract type. Nó không tự định nghĩa tên JSON field, không tạo entity trong database và không thay thế constructor, setter, creator hoặc validation cần thiết của implementation.

## 3. Đăng ký Jackson Module với Spring Data REST

Spring Data REST sử dụng một ObjectMapper đã được cấu hình riêng để xử lý domain object và các persistent entity. Vì vậy, hãy đăng ký type mapping vào ObjectMapper mà exporter sử dụng.

Trong Spring Data REST 5.1, có thể override **configureJacksonObjectMapper** trên **RepositoryRestConfigurer** và thêm một module:

~~~java
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.stereotype.Component;

import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.cfg.MapperBuilder;
import tools.jackson.databind.module.SimpleAbstractTypeResolver;
import tools.jackson.databind.module.SimpleModule;

@Component
public class RestJacksonConfiguration
        implements RepositoryRestConfigurer {

    @Override
    public void configureJacksonObjectMapper(
            MapperBuilder<? extends ObjectMapper,
                    ? extends MapperBuilder<?, ?>> mapperBuilder) {

        mapperBuilder.addModule(new SimpleModule("DomainAbstractTypes") {

            @Override
            public void setupModule(SetupContext context) {
                super.setupModule(context);

                context.addAbstractTypeResolver(
                    new SimpleAbstractTypeResolver()
                        .addMapping(
                            TaskOption.class,
                            TaskOptionEntity.class
                        )
                );
            }
        });
    }
}
~~~

Các phần quan trọng:

1. **RepositoryRestConfigurer** là điểm mở rộng để tùy chỉnh cấu hình Spring Data REST.
2. **configureJacksonObjectMapper** nhận MapperBuilder mà exporter dùng để tạo ObjectMapper.
3. **mapperBuilder.addModule(…)** đăng ký module tùy chỉnh vào mapper đó.
4. **setupModule(…)** được gọi khi module được cài đặt.
5. **context.addAbstractTypeResolver(…)** đưa resolver vào Jackson.
6. **addMapping(TaskOption.class, TaskOptionEntity.class)** khai báo implementation cho interface.

Trong Jackson 3, SetupContext nằm trong hệ kiểu JacksonModule; ví dụ override ở trên dùng tên SetupContext được kế thừa trong SimpleModule. Việc gọi super.setupModule(context) giữ lại quá trình đăng ký nội bộ của SimpleModule trước khi bổ sung resolver.

### Lưu ý về phiên bản Jackson

Spring Data REST 5.1 dùng API Jackson 3, vì vậy các package trong ví dụ có tiền tố **tools.jackson**. Các phiên bản Spring Data REST cũ hơn thường dùng Jackson 2 với package **com.fasterxml.jackson** và API Module tương ứng.

Với Jackson 2, phần đăng ký resolver có cùng ý tưởng:

~~~java
public class MyCustomModule extends SimpleModule {

    public MyCustomModule() {
        super("MyCustomModule");
    }

    @Override
    public void setupModule(SetupContext context) {
        super.setupModule(context);

        context.addAbstractTypeResolver(
            new SimpleAbstractTypeResolver()
                .addMapping(
                    TaskOption.class,
                    TaskOptionEntity.class
                )
        );
    }
}
~~~

Trong ứng dụng dùng Jackson 2, module có thể được khai báo thành Spring bean trong ApplicationContext để Spring Data REST exporter tự nhận và đăng ký. Với phiên bản hiện tại, cách rõ ràng và trực tiếp là cấu hình module qua configureJacksonObjectMapper như ví dụ phía trên.

Không trộn package Jackson 2 và Jackson 3 trong cùng một module. Hãy dùng đúng namespace, API và phiên bản được Spring Boot/Spring Data REST quản lý trong dependency tree của ứng dụng.

## 4. Ví dụ request qua Spring Data REST

Giả sử repository công bố WorkItem:

~~~java
@RepositoryRestResource(path = "work-items")
public interface WorkItemRepository
        extends JpaRepository<WorkItem, Long> {
}
~~~

Khi client tạo một WorkItem mới, request minh họa có thể là:

~~~http
POST /work-items
Content-Type: application/json
Accept: application/hal+json

{
  "title": "Import customer data",
  "options": [
    {
      "name": "format",
      "value": "csv"
    },
    {
      "name": "delimiter",
      "value": ","
    }
  ]
}
~~~

Trong lúc deserialize, Jackson thấy collection có kiểu phần tử TaskOption. Resolver đã đăng ký chọn TaskOptionEntity để tạo từng phần tử. Các thuộc tính name và value được bind vào instance tương ứng.

Nếu request thành công, response phụ thuộc representation, association mapping, repository configuration và việc Spring Data REST công bố entity liên quan. Không giả định mọi association JPA sẽ được trả về dưới dạng object lồng nhau; Spring Data REST thường biểu diễn managed entity bằng link và association resource theo hợp đồng của exporter.

Có thể kiểm tra item resource mới bằng GET và theo các link HAL mà server trả về. Nếu ứng dụng dùng association endpoint để gắn các entity đã tồn tại, hãy dùng URI của entity theo đúng hợp đồng association thay vì gửi JSON embedded object rồi kỳ vọng resolver tự xử lý toàn bộ persistence relationship.

## 5. Ánh xạ cố định bằng @JsonDeserialize

Ngoài Jackson Module, có thể khai báo implementation trực tiếp bằng annotation **@JsonDeserialize**.

Với một thuộc tính đơn có kiểu interface:

~~~java
public class WorkItemRequest {

    @JsonDeserialize(as = TaskOptionImpl.class)
    private TaskOption option;
}
~~~

Với collection hoặc array, dùng **contentAs** để chỉ định kiểu phần tử:

~~~java
public class WorkItemRequest {

    @JsonDeserialize(contentAs = TaskOptionImpl.class)
    private List<TaskOption> options;
}
~~~

Với map, có thể dùng **contentAs** để chỉ định kiểu value và **keyAs** để chỉ định kiểu key khi cần.

So sánh hai cách:

| Cách | Phạm vi | Khi phù hợp |
| --- | --- | --- |
| @JsonDeserialize(as = ...) | Một thuộc tính hoặc kiểu được annotation | Implementation chỉ cần áp dụng ở một điểm cụ thể |
| @JsonDeserialize(contentAs = ...) | Phần tử của collection/array hoặc value của map | Kiểu khai báo của container là abstract/interface |
| SimpleAbstractTypeResolver | Ánh xạ kiểu abstract tập trung trong Jackson Module | Nhiều thuộc tính cùng dùng một implementation |
| Custom JsonDeserializer | Tự quyết định cách tạo object và đọc JSON | Cần logic tạo object, kiểm tra dữ liệu hoặc mapping phức tạp |

Annotation ở property thường có phạm vi cục bộ và dễ đọc ngay tại nơi khai báo. Module phù hợp hơn khi muốn tập trung cấu hình cho ObjectMapper của Spring Data REST, đặc biệt khi cùng một interface được dùng ở nhiều entity hoặc nhiều thuộc tính.

@JsonDeserialize(as = ...) yêu cầu implementation là subtype tương thích với kiểu khai báo. Nếu using cũng được khai báo, deserializer tùy chỉnh được chỉ định trực tiếp sẽ có ưu tiên so với thuộc tính as.

## 6. Khi có nhiều implementation khác nhau

Ánh xạ bằng SimpleAbstractTypeResolver phù hợp khi một abstract type có một implementation mặc định cố định.

Nếu một interface có nhiều implementation và JSON cần chọn loại theo từng request, một mapping cố định là chưa đủ. Ví dụ:

~~~java
public interface PaymentMethod {
    String getReference();
}

public class CardPayment implements PaymentMethod {
    private String reference;
    private String lastFourDigits;
}

public class BankTransfer implements PaymentMethod {
    private String reference;
    private String bankCode;
}
~~~

Client có thể gửi nhiều loại PaymentMethod khác nhau. Khi đó cần polymorphic type handling, thường dùng **@JsonTypeInfo** cùng **@JsonSubTypes**:

~~~java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "kind"
)
@JsonSubTypes({
    @JsonSubTypes.Type(
        value = CardPayment.class,
        name = "card"
    ),
    @JsonSubTypes.Type(
        value = BankTransfer.class,
        name = "bank-transfer"
    )
})
public interface PaymentMethod {
}
~~~

JSON có discriminator để chỉ định loại:

~~~json
{
  "kind": "card",
  "reference": "PAY-1001",
  "lastFourDigits": "4242"
}
~~~

Hoặc:

~~~json
{
  "kind": "bank-transfer",
  "reference": "PAY-1002",
  "bankCode": "ABC"
}
~~~

Jackson đọc trường kind và chọn subtype đã đăng ký. Tên logical type như card và bank-transfer ổn định hơn việc đưa tên class Java đầy đủ vào payload.

Không dùng polymorphic type metadata một cách thiếu kiểm soát. Chỉ cho phép các subtype đã biết và được ứng dụng chấp nhận. Tránh cấu hình để client tùy ý chỉ định class name có thể được nạp hoặc khởi tạo; việc lựa chọn implementation từ dữ liệu không tin cậy phải có allowlist rõ ràng.

## 7. Phân biệt ba cơ chế ánh xạ

Các cơ chế có liên quan nhưng giải quyết những bài toán khác nhau:

| Cơ chế | Câu hỏi được giải quyết |
| --- | --- |
| SimpleAbstractTypeResolver | Với interface/abstract type này, Jackson nên tạo implementation mặc định nào? |
| @JsonDeserialize | Thuộc tính hoặc kiểu này cần dùng concrete type hay custom deserializer nào? |
| @JsonTypeInfo + @JsonSubTypes | Khi có nhiều subtype, JSON cho biết mỗi object thuộc subtype nào? |
| JPA targetEntity | Persistence provider dùng entity class nào cho quan hệ được khai báo bằng kiểu trừu tượng? |
| Spring Data repository metadata | Entity và repository nào được quản lý/công bố thành REST resource? |

Cấu hình Jackson không tự thay đổi mapping JPA. Ngược lại, khai báo targetEntity trong JPA không tự cho Jackson biết cách deserialize JSON.

Nếu cùng một thuộc tính được dùng trong JSON binding và persistence mapping, cả hai tầng phải thống nhất về subtype hợp lệ. Nếu implementation là entity được quản lý, cần kiểm tra constructor, ID, owning side, cascade, orphan removal và vòng đời entity theo mapping persistence thực tế.

## 8. Khi nào cần custom serializer hoặc deserializer?

Ánh xạ abstract type chỉ giải quyết việc chọn class để khởi tạo. Nó không đủ nếu JSON có cấu trúc khác với thuộc tính Java hoặc cần logic đặc biệt.

Ví dụ nên cân nhắc custom deserializer khi:

- JSON dùng một cấu trúc khác hẳn object model.
- Một giá trị JSON cần được chuyển thành nhiều field hoặc object con.
- Cần tra cứu reference qua repository/service.
- Cần xác thực một discriminator hoặc trạng thái trước khi tạo implementation.
- Việc khởi tạo phụ thuộc vào ngữ cảnh request hoặc dữ liệu khác.
- Cần xử lý nhiều dạng payload cũ trong thời gian chuyển đổi API.

Spring Data REST cho phép đăng ký serializer và deserializer trong Jackson Module thông qua SetupContext. Module có thể thêm SimpleSerializers và SimpleDeserializers hoặc các implementation tùy chỉnh.

Ví dụ cấu trúc đăng ký:

~~~java
@Override
public void setupModule(SetupContext context) {
    super.setupModule(context);

    SimpleSerializers serializers = new SimpleSerializers();
    SimpleDeserializers deserializers = new SimpleDeserializers();

    serializers.addSerializer(
        TaskOptionEntity.class,
        new TaskOptionSerializer()
    );

    deserializers.addDeserializer(
        TaskOption.class,
        new TaskOptionDeserializer()
    );

    context.addSerializers(serializers);
    context.addDeserializers(deserializers);
}
~~~

Tên class và chữ ký serializer/deserializer cụ thể phải theo Jackson version đang dùng. Với Jackson 3, API serializer/deserializer đã thay đổi so với Jackson 2; không sao chép nguyên import hoặc class signature của ví dụ Jackson 2 vào project Jackson 3.

Nếu custom deserializer cần gọi repository hoặc service, tránh tự tạo dependency vòng giữa Jackson Module và Spring Data REST. Cân nhắc chuyển logic tra cứu sang application service hoặc dùng request DTO rồi xử lý ở tầng service sau khi deserialize.

## 9. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Cannot construct instance of interface hoặc abstract class | Jackson chưa có implementation mapping | Đăng ký SimpleAbstractTypeResolver, @JsonDeserialize hoặc polymorphic type metadata |
| Mapping được khai báo nhưng vẫn không có tác dụng trong Spring Data REST | Module được đăng ký vào ObjectMapper khác với mapper exporter sử dụng | Cấu hình qua RepositoryRestConfigurer.configureJacksonObjectMapper hoặc cơ chế module bean đúng phiên bản |
| Abstract type được ánh xạ nhưng báo lỗi subtype không hợp lệ | Implementation không implement/kế thừa đúng kiểu khai báo | Kiểm tra quan hệ subtype và generic type |
| Collection vẫn không deserialize được | Ánh xạ ở property không áp dụng cho phần tử collection hoặc generic type không đúng | Dùng contentAs hoặc resolver cho đúng abstract element type |
| Field JSON không được gán | Implementation thiếu setter, constructor/creator hoặc property visibility phù hợp | Kiểm tra JavaBean accessors, constructor và cấu hình Jackson |
| POST tạo object được nhưng persistence thất bại | Jackson mapping đúng nhưng entity mapping, owning side hoặc constraint không hợp lệ | Kiểm tra JPA targetEntity, ID, cascade, transaction và validation |
| Có nhiều implementation nhưng luôn tạo cùng một class | Đã đăng ký mapping cố định cho abstract type | Dùng @JsonTypeInfo/@JsonSubTypes hoặc custom deserializer để chọn subtype |
| JSON chứa class name không mong muốn | Cho phép polymorphic type selection quá rộng | Dùng logical type name và allowlist subtype |
| API trả representation không như JSON embedded object | Spring Data REST đang biểu diễn managed entity qua association link | Theo HAL link và dùng association resource đúng hợp đồng |

## 10. Quy trình triển khai và kiểm tra

1. Xác định thuộc tính nào trong domain model được khai báo bằng interface hoặc abstract class.
2. Xác định implementation cụ thể mà persistence layer cho phép.
3. Chọn một implementation cố định hay nhiều subtype có discriminator.
4. Với một implementation cố định, đăng ký mapping bằng SimpleAbstractTypeResolver hoặc annotation @JsonDeserialize.
5. Đưa module vào ObjectMapper mà Spring Data REST exporter sử dụng.
6. Kiểm tra package/API theo phiên bản Jackson và Spring Data REST trong dependency tree.
7. Gửi POST với JSON chứa thuộc tính interface và xác nhận Jackson tạo đúng implementation.
8. Gửi PUT/PATCH nếu ứng dụng hỗ trợ cập nhật representation đó và xác nhận binding đúng.
9. Đọc lại item resource, association link và dữ liệu persistence để xác nhận trạng thái đã lưu.
10. Kiểm tra payload không hợp lệ, subtype không được phép và trường hợp implementation không thể khởi tạo.
11. Nếu có nhiều subtype, kiểm tra discriminator thiếu, sai hoặc không nằm trong allowlist.

Một test tập trung cho resolver có thể kiểm tra trực tiếp ObjectMapper tương ứng:

~~~java
assertThat(objectMapper.readValue(
        """
        {"name":"format","value":"csv"}
        """,
        TaskOption.class
    ))
    .isInstanceOf(TaskOptionEntity.class);
~~~

Đây là test minh họa cho Jackson mapping. Ngoài test mapper, cần có integration test qua endpoint Spring Data REST vì exporter dùng ObjectMapper đã được cấu hình cùng các serializer đặc biệt cho PersistentEntity và association.

## 11. Checklist nhanh

- [ ] Đã xác định interface hoặc abstract type mà Jackson cần deserialize.
- [ ] Implementation là subtype hợp lệ và có thể được khởi tạo.
- [ ] Đã chọn mapping cố định hay polymorphic mapping.
- [ ] SimpleAbstractTypeResolver được đăng ký vào đúng ObjectMapper của Spring Data REST.
- [ ] Hoặc @JsonDeserialize được đặt đúng trên type/property/container content.
- [ ] Không trộn Jackson 2 và Jackson 3 package/API.
- [ ] JPA targetEntity và Jackson implementation mapping thống nhất.
- [ ] Association được kiểm tra theo HAL link và hợp đồng REST thực tế.
- [ ] Subtype được allowlist nếu JSON có discriminator.
- [ ] Đã kiểm thử POST/PUT/PATCH và persistence bằng integration test.

## 12. Ghi nhớ

Khi Jackson gặp một thuộc tính kiểu interface hoặc abstract class, nó cần biết concrete implementation để tạo object. Trong Spring Data REST, cách cấu hình tập trung là đăng ký một Jackson Module vào ObjectMapper của exporter:

~~~java
context.addAbstractTypeResolver(
    new SimpleAbstractTypeResolver()
        .addMapping(TaskOption.class, TaskOptionEntity.class)
);
~~~

Dùng **SimpleAbstractTypeResolver** khi một abstract type có một implementation mặc định. Dùng **@JsonDeserialize** khi chỉ một property cần concrete type cụ thể. Nếu JSON có thể đại diện cho nhiều implementation, dùng **@JsonTypeInfo** và **@JsonSubTypes** hoặc custom deserializer với danh sách subtype được cho phép.

Jackson mapping chỉ giải quyết chuyển đổi JSON thành object. Persistence mapping, association exposure, validation và quyền truy cập vẫn phải được cấu hình ở các tầng tương ứng.

## Tài liệu tham khảo

- Spring Data REST Reference — Domain Object Representations, Abstract Class Registration: https://docs.spring.io/spring-data/rest/reference/representations.html
- Spring Data REST Reference — Adding Custom Serializers and Deserializers to Jackson's ObjectMapper: https://docs.spring.io/spring-data/rest/reference/customizing/custom-jackson-deserialization.html
- Spring Data REST API — RepositoryRestConfigurer.configureJacksonObjectMapper: https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/config/RepositoryRestConfigurer.html
- Jackson Databind — SimpleAbstractTypeResolver: https://javadoc.io/doc/tools.jackson.core/jackson-databind/latest/tools.jackson.databind/module/SimpleAbstractTypeResolver.html
- Jackson Databind — JsonDeserialize: https://javadoc.io/doc/tools.jackson.core/jackson-databind/latest/tools.jackson.databind/annotation/JsonDeserialize.html
- Jackson Annotations — JsonTypeInfo and JsonSubTypes: https://github.com/FasterXML/jackson-annotations
