# Xác định phạm vi mix-in để không làm thay đổi nơi dùng khác

Jackson mix-in là cơ chế bổ sung hoặc điều chỉnh annotation cho một kiểu Java mà không cần sửa trực tiếp mã nguồn của kiểu đó. Cách này đặc biệt hữu ích khi làm việc với thư viện bên thứ ba, lớp domain không thể thay đổi hoặc một hợp đồng JSON cần cấu hình riêng.

Tuy nhiên, mix-in không tự giới hạn tác động vào một lần serialize. Khi đăng ký mix-in trên ObjectMapper, cấu hình đó thuộc về mapper và được dùng ở mọi nơi mapper xử lý kiểu đích tương ứng: root value, property lồng nhau, phần tử collection, dữ liệu đọc vào và dữ liệu ghi ra. Nếu nhiều endpoint hoặc module dùng chung mapper, một thay đổi mix-in có thể làm thay đổi JSON ở tất cả các nơi đó.

Muốn dùng mix-in an toàn, cần xác định rõ mapper nào sở hữu cấu hình, nơi nào được phép dùng mapper đó và cách kiểm tra phạm vi ảnh hưởng. Khi chỉ một luồng tích hợp cần cách biểu diễn đặc biệt, nên cô lập mix-in bằng mapper chuyên biệt hoặc một bản sao mapper có cấu hình riêng, thay vì âm thầm thay đổi mapper toàn ứng dụng.

## 1. Mix-in dùng để làm gì?

Giả sử ứng dụng sử dụng một lớp thư viện mà không thể sửa:

~~~java
public class ExternalUser {
    private String username;
    private String password;

    public String getUsername() {
        return username;
    }

    public String getPassword() {
        return password;
    }
}
~~~

Ứng dụng muốn bỏ password khỏi JSON đầu ra. Có thể tạo một mix-in:

~~~java
public abstract class ExternalUserMixin {

    @JsonIgnore
    abstract String getPassword();
}
~~~

Đăng ký mix-in:

~~~java
ObjectMapper mapper = new ObjectMapper();
mapper.addMixIn(ExternalUser.class, ExternalUserMixin.class);
~~~

Khi mapper serialize ExternalUser, Jackson kết hợp metadata annotation của mix-in với metadata của kiểu đích. Password có thể bị bỏ qua mà không cần thay đổi class ExternalUser.

Mix-in không phải subclass thay thế ExternalUser. Nó không được tạo instance để chứa dữ liệu và không thay đổi quan hệ kế thừa Java. Nó cung cấp annotation mà Jackson dùng khi introspect kiểu đích.

## 2. Phạm vi đăng ký mix-in nằm ở đâu?

Phương thức addMixIn(targetType, mixinSource) được gọi trên ObjectMapper. Vì vậy, đăng ký thuộc cấu hình của mapper đó.

~~~java
ObjectMapper mapper = new ObjectMapper();
mapper.addMixIn(ExternalUser.class, ExternalUserMixin.class);
~~~

Mọi thao tác dùng mapper này để xử lý ExternalUser đều có thể nhận tác động của mix-in:

- Serialize một ExternalUser làm root value.
- Serialize một DTO có property kiểu ExternalUser.
- Serialize List<ExternalUser> hoặc Map<String, ExternalUser>.
- Deserialize JSON vào ExternalUser.
- Deserialize DTO có property hoặc phần tử kiểu ExternalUser.

Mix-in không chỉ có hiệu lực ở dòng code gọi addMixIn. Nó trở thành một phần cấu hình của mapper và ảnh hưởng đến các thao tác về sau.

Sơ đồ phạm vi:

~~~text
ObjectMapper dùng chung
        |
        +-- Endpoint A
        |      |
        |      +-- ExternalUser
        |
        +-- Endpoint B
        |      |
        |      +-- Profile.externalUser
        |
        +-- Job nền
               |
               +-- List<ExternalUser>

Mix-in đăng ký trên mapper có thể tác động đến
tất cả các nhánh sử dụng kiểu đích tương ứng.
~~~

Do đó, câu hỏi quan trọng trước khi đăng ký không chỉ là "mix-in có hoạt động không?" mà còn là "những nơi nào đang dùng mapper này?".

## 3. Mapper dùng chung khiến thay đổi có phạm vi rộng

Trong ứng dụng web, một ObjectMapper thường được cấu hình ở tầng ứng dụng rồi dùng bởi nhiều controller, message converter, service hoặc job. Nếu đăng ký mix-in lên mapper đó, mọi thành phần dùng chung mapper có thể thấy hành vi mới.

Ví dụ:

~~~java
@Configuration
public class JacksonConfiguration {

    @Bean
    ObjectMapper objectMapper() {
        ObjectMapper mapper = new ObjectMapper();
        mapper.addMixIn(ExternalUser.class, ExternalUserMixin.class);
        return mapper;
    }
}
~~~

Nếu bean này là mapper chính của ứng dụng, mix-in có thể ảnh hưởng tất cả nơi Spring dùng bean đó để serialize hoặc deserialize. Một endpoint không trực tiếp biết về mix-in vẫn có thể nhận output đã bị thay đổi.

Điều này dễ tạo lỗi hồi quy:

1. Một tích hợp với hệ thống đối tác cần bỏ một field.
2. Mix-in được đăng ký vào mapper toàn cục để xử lý tích hợp đó.
3. Endpoint nội bộ cũng dùng cùng mapper.
4. Endpoint nội bộ bất ngờ mất field mà trước đây vẫn trả về.

Lỗi không nằm ở endpoint nội bộ. Phạm vi cấu hình đã rộng hơn nhu cầu ban đầu.

## 4. Một mapper riêng cho một hợp đồng riêng

Khi chỉ một tích hợp cần cách serialize đặc biệt, cách đơn giản nhất là tạo mapper riêng cho hợp đồng đó:

~~~java
ObjectMapper defaultMapper = createApplicationMapper();

ObjectMapper partnerMapper = createPartnerMapper();
partnerMapper.addMixIn(
    ExternalUser.class,
    PartnerExternalUserMixin.class
);
~~~

Mapper mặc định tiếp tục phục vụ hợp đồng hiện tại. Mapper partner chịu trách nhiệm cho JSON của đối tác.

Có thể đóng gói mapper vào một service chuyên biệt:

~~~java
public final class PartnerJsonCodec {

    private final ObjectMapper mapper;

    public PartnerJsonCodec(ObjectMapper baseMapper) {
        this.mapper = baseMapper.copy();
        this.mapper.addMixIn(
            ExternalUser.class,
            PartnerExternalUserMixin.class
        );
    }

    public String write(Object value) throws JsonProcessingException {
        return mapper.writeValueAsString(value);
    }

    public <T> T read(String json, Class<T> type)
            throws JsonProcessingException {
        return mapper.readValue(json, type);
    }
}
~~~

Ví dụ này dùng copy() để tạo mapper riêng dựa trên cấu hình nền. Mapper được giữ private trong codec, nên các thành phần khác không cần truy cập hoặc thay đổi mix-in của nó.

## 5. Dùng ObjectMapper.copy() để cô lập cấu hình

ObjectMapper.copy() tạo một mapper mới với cấu hình tương ứng từ mapper gốc, bao gồm các thiết lập annotation introspection, module, serializer/deserializer đã đăng ký và mix-in hiện có tại thời điểm sao chép.

~~~java
ObjectMapper applicationMapper = createApplicationMapper();

ObjectMapper exportMapper = applicationMapper.copy();
exportMapper.addMixIn(
    ExternalUser.class,
    ExportUserMixin.class
);
~~~

Mix-in mới được thêm vào exportMapper. Nó không được thêm vào applicationMapper.

~~~text
applicationMapper
      |
      +-- Cấu hình chung của ứng dụng
      |
      +-- Không có ExportUserMixin

exportMapper = applicationMapper.copy()
      |
      +-- Cấu hình nền được sao chép
      |
      +-- Có ExportUserMixin
~~~

Đây là cách hữu ích khi mapper riêng cần giữ phần lớn cấu hình nền như JavaTimeModule, naming strategy, date format hoặc serializer tùy biến đã có.

Tạo bản sao có chi phí vì Jackson phải tạo cấu hình và cache riêng. Không nên gọi copy() cho từng object hoặc từng field. Hãy tạo mapper chuyên biệt một lần khi khởi tạo ứng dụng, sau đó tái sử dụng mapper đó cho đúng hợp đồng.

## 6. Thời điểm copy và cấu hình mapper

Nên hoàn tất cấu hình mapper nền trước khi sử dụng nó trong ứng dụng:

~~~java
ObjectMapper baseMapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .build();

ObjectMapper partnerMapper = baseMapper.copy();
partnerMapper.addMixIn(
    ExternalUser.class,
    PartnerExternalUserMixin.class
);
~~~

Mapper chuyên biệt được tạo sau khi mapper nền đã có các module và feature cần thiết. Sau đó, cả hai mapper được tái sử dụng mà không tiếp tục sửa cấu hình trong lúc request đang chạy.

Không nên thay đổi mix-in trên mapper đã được chia sẻ giữa các thread như một cách cấu hình theo request. ObjectMapper được thiết kế để dùng đồng thời sau khi cấu hình xong; việc thay đổi cấu hình runtime có thể tạo hành vi khó dự đoán, đặc biệt khi serializer/deserializer đã được cache.

Nếu cần hai hợp đồng JSON đồng thời, tạo hai mapper trước rồi dùng mỗi mapper cho đúng luồng.

## 7. ObjectWriter và ObjectReader không tự cô lập mix-in

ObjectWriter và ObjectReader là cách tạo cấu hình riêng cho một lần ghi hoặc đọc, nhưng chúng vẫn dựa trên cấu hình của ObjectMapper gốc.

~~~java
ObjectWriter writer = mapper.writer()
    .with(SerializationFeature.INDENT_OUTPUT);

ObjectReader reader = mapper.readerFor(ExternalUser.class);
~~~

Các đối tượng này có thể giữ các tùy chọn thao tác như pretty printing, root type, view hoặc attribute. Tuy nhiên, chúng không phải cơ chế tổng quát để đăng ký một mix-in riêng cho một lần ghi.

Nếu mapper đã có:

~~~java
mapper.addMixIn(ExternalUser.class, ExternalUserMixin.class);
~~~

thì writer và reader tạo từ mapper đó vẫn dùng cấu hình mix-in của mapper.

Không nên nhầm:

| Cơ chế | Phạm vi |
|---|---|
| ObjectMapper.addMixIn() | Cấu hình mix-in của mapper |
| ObjectMapper.copy() rồi addMixIn() | Cấu hình mix-in riêng của mapper bản sao |
| ObjectWriter | Tùy chọn cho thao tác ghi, dựa trên mapper gốc |
| ObjectReader | Tùy chọn cho thao tác đọc, dựa trên mapper gốc |

Nếu yêu cầu là một mix-in chỉ có hiệu lực ở một luồng tích hợp, hãy cô lập mapper thay vì tìm cách biến ObjectWriter thành nơi đăng ký mix-in.

## 8. Mix-in có thể tác động cả serialization và deserialization

Annotation mix-in không chỉ dành cho đầu ra. Tùy annotation, nó có thể ảnh hưởng cách Jackson phát hiện property, chọn constructor, bỏ qua field, đổi tên property hoặc chuyển đổi kiểu ở cả hai chiều.

Ví dụ:

~~~java
public abstract class ExternalUserMixin {

    @JsonProperty("user_name")
    abstract String getUsername();

    @JsonIgnore
    abstract String getPassword();
}
~~~

Khi serialize, username có thể được ghi thành user_name và password bị bỏ qua. Khi deserialize, cùng metadata cũng có thể ảnh hưởng tên property được nhận và property bị bỏ qua.

Vì vậy, trước khi thêm mix-in vào mapper dùng chung, cần xác định luồng nào dùng mapper để đọc JSON. Một thay đổi tưởng như chỉ phục vụ response có thể ảnh hưởng request body hoặc message consumer.

Nếu chỉ muốn thay đổi serialization mà không muốn thay đổi deserialization, cần chọn annotation/cấu hình phù hợp hoặc tạo mapper riêng cho chiều ghi. Không nên giả định mọi annotation đều chỉ tác động một chiều.

## 9. Mix-in với kiểu thư viện bên thứ ba

Một use case phổ biến là thêm annotation cho class không thuộc quyền sở hữu của ứng dụng:

~~~java
public class LibraryCoordinates {
    public double latitude;
    public double longitude;
}
~~~

Giả sử JSON cần dùng tên lat và lon:

~~~java
public abstract class CoordinatesMixin {

    @JsonProperty("lat")
    abstract double getLatitude();

    @JsonProperty("lon")
    abstract double getLongitude();
}
~~~

Đăng ký:

~~~java
mapper.addMixIn(
    LibraryCoordinates.class,
    CoordinatesMixin.class
);
~~~

Nếu mapper được dùng cho nhiều tích hợp, tất cả nơi xử lý LibraryCoordinates qua mapper này có thể nhận tên field mới. Nếu chỉ một đối tác yêu cầu lat/lon, hãy đăng ký mix-in trên mapper của đối tác.

Mix-in đặc biệt hữu ích khi:

- Không thể sửa class của thư viện.
- Không muốn fork thư viện chỉ để thêm annotation.
- Cần ánh xạ tên field theo một hợp đồng JSON cụ thể.
- Cần thêm JsonCreator, JsonIgnore, JsonFormat hoặc JsonTypeInfo mà không thay đổi dependency.

## 10. Mix-in với model nội bộ do ứng dụng sở hữu

Nếu ứng dụng kiểm soát class, cần cân nhắc liệu annotation trực tiếp hoặc DTO riêng có rõ ràng hơn mix-in hay không.

Ví dụ:

~~~java
public class Customer {
    private String name;
    private String internalCode;
}
~~~

Nếu mọi API của ứng dụng đều cần cùng một quy tắc, annotation trực tiếp có thể dễ hiểu:

~~~java
public class Customer {
    private String name;

    @JsonIgnore
    private String internalCode;
}
~~~

Nếu chỉ một endpoint cần ẩn internalCode, DTO response riêng có thể làm hợp đồng rõ hơn:

~~~java
public record PublicCustomerResponse(String name) {
}
~~~

Mix-in phù hợp khi cần cấu hình Jackson tách khỏi class hoặc khi class không thể sửa. Không nên dùng mix-in toàn cục để mô phỏng nhiều hợp đồng API khác nhau trên cùng một mapper.

## 11. Mix-in có thể gắn nhiều loại annotation

Mix-in không chỉ dùng cho JsonIgnore. Có thể bổ sung nhiều annotation Jackson:

~~~java
public abstract class ExternalEventMixin {

    @JsonProperty("event_id")
    abstract String getEventId();

    @JsonFormat(shape = JsonFormat.Shape.STRING)
    abstract Instant getCreatedAt();

    @JsonIgnore
    abstract String getDebugPayload();
}
~~~

Một mix-in có thể thay đổi:

- Tên property bằng JsonProperty.
- Field bị bỏ qua bằng JsonIgnore.
- Định dạng ngày giờ bằng JsonFormat.
- Constructor hoặc factory được dùng bằng JsonCreator.
- Thông tin kiểu đa hình bằng JsonTypeInfo và JsonSubTypes.
- Serializer hoặc deserializer bằng JsonSerialize và JsonDeserialize.
- Các quy tắc bỏ qua property bằng JsonIgnoreProperties.

Do mix-in có thể tác động sâu đến metadata, cần xem nó như một phần của hợp đồng serialization chứ không phải một tùy chọn nhỏ chỉ ảnh hưởng tên field.

## 12. Quan hệ giữa annotation trên target và mix-in

Jackson kết hợp annotation tìm thấy trên kiểu đích với annotation từ mix-in. Mục tiêu của mix-in là bổ sung hoặc điều chỉnh metadata mà không sửa target class.

Khi cả target và mix-in cùng khai báo annotation cho một property, kết quả phụ thuộc quy tắc hợp nhất annotation của Jackson và loại annotation cụ thể. Với các annotation có giá trị xung đột, annotation từ mix-in thường được dùng để ghi đè hoặc điều chỉnh metadata của target theo cơ chế mix-in.

Ví dụ target:

~~~java
public class ExternalUser {
    @JsonProperty("login")
    public String username;
}
~~~

Mix-in:

~~~java
public abstract class ExternalUserMixin {
    @JsonProperty("user_name")
    public String username;
}
~~~

Không nên suy đoán kết quả chỉ từ việc annotation nào nằm trong source code. Hãy xác nhận JSON thực tế bằng một test nhỏ trên đúng phiên bản Jackson của dự án.

Khi có xung đột, hãy giữ mix-in đơn giản và chỉ khai báo metadata cần thay đổi. Tránh tạo một mix-in lớn sao chép toàn bộ cấu trúc target vì nó dễ lỗi khi thư viện nâng cấp.

## 13. Cấu trúc mix-in nên bám theo cấu trúc target

Mix-in thường dùng abstract class hoặc interface với method signature tương ứng target. Jackson sử dụng tên và chữ ký method để ghép metadata vào property tương ứng.

Target:

~~~java
public class ExternalAccount {
    public String getAccountName() {
        return "demo";
    }

    public String getSecret() {
        return "hidden";
    }
}
~~~

Mix-in:

~~~java
public abstract class ExternalAccountMixin {

    @JsonProperty("account_name")
    abstract String getAccountName();

    @JsonIgnore
    abstract String getSecret();
}
~~~

Method trong mix-in không cần triển khai vì Jackson chỉ cần annotation metadata. Tên method, kiểu trả về và tham số phải tương thích với member mục tiêu mà Jackson cần ghép.

Với constructor, mix-in có thể khai báo constructor tương ứng và gắn JsonCreator/JsonProperty cho tham số:

~~~java
public abstract class ExternalPointMixin {

    @JsonCreator
    ExternalPointMixin(
        @JsonProperty("x") double x,
        @JsonProperty("y") double y
    ) {
    }
}
~~~

Chữ ký constructor trong mix-in phải khớp constructor target mà Jackson cần mô tả. Cần kiểm thử việc deserialize vì sai chữ ký hoặc thiếu metadata tham số có thể khiến Jackson không chọn được creator mong muốn.

## 14. Mix-in và kế thừa

Một kiểu Java có thể kế thừa property từ lớp cha hoặc interface. Jackson introspect cấu trúc kiểu theo quy tắc của nó, vì vậy mix-in cần được đăng ký trên đúng kiểu mà metadata cần tác động.

Ví dụ:

~~~java
public class BaseMessage {
    public String getId() {
        return "m-1";
    }
}

public class EmailMessage extends BaseMessage {
    public String getSubject() {
        return "Hello";
    }
}
~~~

Nếu đăng ký mix-in cho BaseMessage:

~~~java
mapper.addMixIn(BaseMessage.class, BaseMessageMixin.class);
~~~

thì metadata nhắm đến BaseMessage và các property được Jackson phát hiện từ hierarchy theo cơ chế introspection. Tuy nhiên, không nên giả định mix-in đăng ký cho một class sẽ tự động áp dụng giống nhau cho mọi subtype trong mọi trường hợp.

Nếu cần quy tắc cụ thể cho EmailMessage, có thể đăng ký mix-in trực tiếp cho EmailMessage. Nếu cần một quy tắc chung cho nhiều subtype, hãy kiểm tra từng subtype thực tế hoặc tổ chức một hierarchy mix-in phù hợp.

Điểm cần nhớ là mix-in không phải cơ chế quét toàn bộ package. Nó được gắn với target type được đăng ký và được Jackson áp dụng trong quá trình introspect target đó.

## 15. Đăng ký mix-in qua JsonMapper builder

Trong các phiên bản Jackson có JsonMapper builder, có thể đăng ký mix-in khi xây dựng mapper:

~~~java
ObjectMapper partnerMapper = JsonMapper.builder()
    .addMixIn(
        ExternalUser.class,
        PartnerExternalUserMixin.class
    )
    .build();
~~~

Cách này giúp cấu hình mapper tại một nơi trước khi đưa vào sử dụng. Có thể kết hợp với module:

~~~java
ObjectMapper partnerMapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .addMixIn(
        ExternalUser.class,
        PartnerExternalUserMixin.class
    )
    .build();
~~~

Builder là lựa chọn tốt khi tạo mapper mới từ đầu. Nếu cần kế thừa một cấu hình ứng dụng phức tạp, copy mapper nền rồi thêm mix-in có thể ít bỏ sót cấu hình hơn.

API builder cụ thể phụ thuộc phiên bản Jackson. Nếu phiên bản dự án không có overload mong muốn, có thể tạo mapper rồi gọi addMixIn trước khi sử dụng.

## 16. Tạo một factory cho mapper chuyên biệt

Để tránh đăng ký mix-in rải rác ở nhiều nơi, hãy gom việc tạo mapper vào một factory hoặc cấu hình có tên rõ ràng:

~~~java
public final class JsonMapperFactory {

    private JsonMapperFactory() {
    }

    public static ObjectMapper createPartnerMapper(
            ObjectMapper applicationMapper) {

        ObjectMapper mapper = applicationMapper.copy();
        mapper.addMixIn(
            ExternalUser.class,
            PartnerExternalUserMixin.class
        );
        mapper.addMixIn(
            ExternalEvent.class,
            PartnerExternalEventMixin.class
        );
        return mapper;
    }
}
~~~

Khởi tạo một lần:

~~~java
ObjectMapper partnerMapper =
    JsonMapperFactory.createPartnerMapper(applicationMapper);

PartnerJsonCodec partnerCodec = new PartnerJsonCodec(partnerMapper);
~~~

Factory làm rõ mục đích của mapper và tập mix-in được áp dụng. Khi cần thay đổi hợp đồng partner, developer có thể tìm đúng nơi cấu hình mà không phải dò nhiều controller.

Không nên tạo mapper mới trong từng phương thức controller. Mapper có cache và cấu hình tương đối nặng; tạo một lần và tái sử dụng thường hợp lý hơn.

## 17. Đặt tên mapper theo hợp đồng, không theo nơi gọi

Một mapper chuyên biệt nên được đặt tên theo schema hoặc hệ thống mà nó phục vụ:

- partnerApiMapper
- legacyImportMapper
- auditExportMapper
- publicFeedMapper

Tên như temporaryMapper hoặc mapper2 không cho biết lý do tồn tại và dễ bị dùng nhầm.

Nếu mapper chỉ phục vụ một định dạng dữ liệu, có thể đóng gói trong codec:

~~~java
public interface PartnerJsonCodec {
    String encode(PartnerMessage message);
    PartnerMessage decode(String json);
}
~~~

Controller/service sử dụng codec theo hợp đồng thay vì nhận một ObjectMapper chung rồi tự chọn cấu hình. Cách này giới hạn nơi có thể gọi mapper đặc biệt và làm ranh giới tích hợp rõ hơn.

## 18. Không đăng ký mix-in theo request

Một cách làm sai là thêm hoặc thay mix-in trước mỗi request:

~~~java
// Không nên:
mapper.addMixIn(ExternalUser.class, PublicUserMixin.class);
String publicJson = mapper.writeValueAsString(user);

mapper.addMixIn(ExternalUser.class, InternalUserMixin.class);
String internalJson = mapper.writeValueAsString(user);
~~~

Nếu hai request chạy đồng thời, một request có thể thay đổi cấu hình khi request kia đang serialize. Ngoài ra, Jackson có thể đã cache serializer theo cấu hình cũ, khiến việc thay đổi runtime không có kết quả nhất quán như mong đợi.

Đừng dùng addMixIn/remove mix-in như một công tắc cho từng request. Nếu có hai hợp đồng đồng thời, tạo hai mapper chuyên biệt và chọn mapper tương ứng:

~~~java
String publicJson = publicMapper.writeValueAsString(user);
String internalJson = internalMapper.writeValueAsString(user);
~~~

Hai mapper có cấu hình ổn định và cache riêng. Mỗi request chỉ chọn đúng mapper cần dùng.

## 19. Không dùng một mix-in để ẩn field tạm thời

Mix-in thường mô tả quy tắc metadata ổn định của một hợp đồng. Nếu nhu cầu là cùng một response nhưng ẩn field tùy quyền hoặc tùy người dùng, tạo mix-in riêng cho từng request sẽ không phù hợp.

Ví dụ không nên:

~~~java
if (currentUser.isAdmin()) {
    mapper.addMixIn(User.class, AdminUserMixin.class);
} else {
    mapper.addMixIn(User.class, PublicUserMixin.class);
}
~~~

Cấu hình mapper bị thay đổi theo request và có thể ảnh hưởng người dùng khác. Thay vào đó:

- Kiểm tra quyền trong tầng ứng dụng.
- Tạo DTO response phù hợp với người dùng.
- Hoặc dùng một cơ chế theo-operation được thiết kế cho mục đích đó như JsonView/Filter khi phù hợp, đồng thời vẫn kiểm tra quyền.

Mix-in phù hợp với khác biệt schema cố định, không phải trạng thái bảo mật thay đổi theo từng request.

## 20. Mix-in trong Spring Boot

Spring Boot thường cung cấp ObjectMapper được cấu hình qua Jackson auto-configuration. Ứng dụng có thể thêm module hoặc customizer để cấu hình mapper.

Ví dụ dùng Jackson2ObjectMapperBuilderCustomizer:

~~~java
@Bean
Jackson2ObjectMapperBuilderCustomizer jacksonCustomizer() {
    return builder -> builder.mixIn(
        ExternalUser.class,
        ExternalUserMixin.class
    );
}
~~~

Customizer kiểu này tác động đến mapper được xây dựng từ builder mà Spring sử dụng. Nếu builder đó tạo mapper chính của ứng dụng, mix-in có thể có phạm vi toàn ứng dụng.

Nếu mix-in chỉ dành cho một tích hợp, không nên đăng ký nó vào customizer toàn cục. Hãy tạo mapper riêng và cấu hình một message converter hoặc codec riêng cho luồng tích hợp đó.

## 21. Dùng message converter riêng khi cần hợp đồng HTTP riêng

Trong Spring MVC, một HttpMessageConverter có thể sử dụng ObjectMapper riêng. Đây là lựa chọn khi một nhóm endpoint cần JSON khác với phần còn lại.

Ví dụ khung cấu hình:

~~~java
MappingJackson2HttpMessageConverter partnerConverter =
    new MappingJackson2HttpMessageConverter(partnerMapper);
~~~

Converter này có thể được đăng ký cho một luồng hoặc một tập media type cụ thể. Cần cấu hình thứ tự và điều kiện hỗ trợ để Spring chọn đúng converter.

Không nên thêm một converter mới mà không xác định rõ endpoint/media type của nó, vì converter selection có thể khiến nhiều request vô tình dùng mapper chuyên biệt.

Nếu chỉ một hoặc hai endpoint cần schema khác, việc serialize thành String hoặc dùng response DTO chuyên biệt đôi khi đơn giản hơn cấu hình converter toàn cục. Chọn cơ chế theo phạm vi thực tế của hợp đồng.

## 22. Mix-in trên kiểu target không thay đổi class Java

Mix-in chỉ cung cấp metadata cho Jackson. Nó không:

- Thêm field thật vào target class.
- Thêm getter/setter thật vào target class.
- Thay đổi bytecode hoặc quan hệ kế thừa Java.
- Thay đổi cách code nghiệp vụ truy cập object.
- Tự động áp dụng cho thư viện JSON khác.

Ví dụ, nếu mix-in gắn JsonProperty("user_name") lên getUsername(), code Java vẫn gọi getUsername(). Chỉ cách Jackson ánh xạ tên JSON thay đổi trong mapper có mix-in.

Một thư viện khác như Gson hoặc một serializer không dùng Jackson sẽ không tự động hiểu mix-in này.

## 23. Mix-in và nhiều ObjectMapper trong cùng ứng dụng

Có thể có nhiều mapper phục vụ các hợp đồng khác nhau:

~~~text
                         +----------------------+
                         | Domain / DTO objects |
                         +----------+-----------+
                                    |
                    +---------------+---------------+
                    |                               |
                    v                               v
          +-------------------+           +-------------------+
          | ApplicationMapper |           | PartnerMapper     |
          |                   |           |                   |
          | Common modules    |           | Common modules    |
          | Default metadata  |           | Partner mix-ins   |
          +-------------------+           +-------------------+
                    |                               |
                    v                               v
             Internal APIs                  Partner contract
~~~

Nhiều mapper không có nghĩa là tạo mapper mới tùy tiện ở khắp nơi. Mỗi mapper nên có một mục đích, cấu hình rõ và vòng đời ổn định. Nếu có nhiều mapper, nên gom việc tạo và quản lý chúng vào configuration/factory.

Không nên inject mapper partner vào mọi service chỉ vì nó có sẵn. Chỉ thành phần chịu trách nhiệm cho hợp đồng partner mới nên phụ thuộc vào codec hoặc mapper đó.

## 24. Đặt tên mix-in theo target và mục đích

Tên mix-in nên giúp người đọc biết nó áp dụng cho kiểu nào và hợp đồng nào:

~~~java
ExternalUserPartnerMixin
ExternalUserAuditExportMixin
LegacyEventImportMixin
~~~

Tránh tên quá chung như UserMixin nếu có nhiều target User hoặc nhiều biến thể hợp đồng.

Nếu có nhiều mix-in cho cùng một target:

~~~java
mapperA.addMixIn(User.class, PublicUserMixin.class);
mapperB.addMixIn(User.class, InternalUserMixin.class);
~~~

Hãy bảo đảm mapperA và mapperB được sử dụng đúng mục đích. Không đăng ký cả hai mix-in thay phiên trên cùng một mapper dùng chung.

## 25. Ghi chú về mix-in cho serializer và deserializer tùy biến

Mix-in có thể gắn JsonSerialize hoặc JsonDeserialize lên target mà không sửa target:

~~~java
public abstract class LegacyDateMixin {

    @JsonSerialize(using = LegacyDateSerializer.class)
    @JsonDeserialize(using = LegacyDateDeserializer.class)
    abstract LocalDate getDate();
}
~~~

Điều này có nghĩa mix-in có thể thay đổi logic chuyển đổi giá trị chứ không chỉ tên field. Serializer/deserializer tùy biến cũng có vòng đời và yêu cầu an toàn luồng riêng.

Nếu chỉ một tích hợp cần format ngày giờ đặc biệt, mapper riêng giúp giới hạn cả annotation lẫn serializer/deserializer được áp dụng. Nếu đăng ký trên mapper toàn cục, các nơi khác dùng target type có thể nhận format mới.

## 26. Kiểm tra phạm vi ảnh hưởng bằng hai mapper

Một test quan trọng là xác nhận cùng target type cho ra kết quả khác nhau ở mapper chuyên biệt, trong khi mapper nền giữ nguyên:

~~~java
class MixInScopeTest {

    @Test
    void partnerMixinDoesNotChangeBaseMapper() throws Exception {
        ObjectMapper baseMapper = new ObjectMapper();

        ObjectMapper partnerMapper = baseMapper.copy();
        partnerMapper.addMixIn(
            ExternalUser.class,
            ExternalUserMixin.class
        );

        ExternalUser user = createUser();

        JsonNode baseJson = baseMapper.readTree(
            baseMapper.writeValueAsString(user)
        );
        JsonNode partnerJson = partnerMapper.readTree(
            partnerMapper.writeValueAsString(user)
        );

        assertTrue(baseJson.has("password"));
        assertFalse(partnerJson.has("password"));
    }
}
~~~

Test trên kiểm tra một điều quan trọng: đăng ký mix-in trên mapper copy không làm thay đổi mapper gốc. Trong ứng dụng thật, nên dùng fixture có cấu hình giống mapper nền và assertion phản ánh hợp đồng mong muốn.

## 27. Kiểm tra cả root và property lồng nhau

Mix-in có thể được áp dụng khi target type xuất hiện ở nhiều vị trí. Vì vậy, chỉ kiểm tra serialize root object có thể chưa đủ.

~~~java
public class UserEnvelope {
    private ExternalUser user;

    public ExternalUser getUser() {
        return user;
    }

    public void setUser(ExternalUser user) {
        this.user = user;
    }
}
~~~

Test:

~~~java
String rootJson = partnerMapper.writeValueAsString(user);
String nestedJson = partnerMapper.writeValueAsString(
    new UserEnvelope(user)
);
~~~

Kiểm tra rằng mix-in có hiệu lực đúng trong cả hai dạng nếu đó là yêu cầu của mapper chuyên biệt. Đồng thời kiểm tra baseMapper vẫn giữ hợp đồng ban đầu ở cả root và nested object.

Với collection:

~~~java
String listJson = partnerMapper.writeValueAsString(List.of(user));
~~~

Nếu mục tiêu là một mix-in áp dụng cho target type bất kể vị trí, collection test giúp xác nhận phạm vi thực tế.

## 28. Kiểm tra deserialization để tránh thay đổi đầu vào ngoài dự kiến

Mix-in có thể ảnh hưởng cách đọc. Nên kiểm tra riêng:

~~~java
String json = """
    {
      "username": "mai",
      "password": "secret"
    }
    """;

ExternalUser baseUser =
    baseMapper.readValue(json, ExternalUser.class);

ExternalUser partnerUser =
    partnerMapper.readValue(json, ExternalUser.class);
~~~

Nếu mix-in chỉ intended để bỏ password khỏi output, hãy xác định rõ việc nó có ảnh hưởng chiều đọc hay không. Một JsonIgnore có thể làm property bị bỏ qua trong cả hai chiều, tùy metadata và cấu hình Jackson.

Nếu cần chỉ bỏ field khi serialize, có thể dùng annotation/cấu hình định hướng serialization phù hợp, hoặc tách mapper chỉ dùng cho output. Đừng giả định JsonIgnore chỉ áp dụng cho ghi JSON.

## 29. Kiểm tra bằng JsonNode thay vì so sánh nguyên chuỗi

Thứ tự field JSON object không nên là điều kiện kiểm tra chính. Hãy parse output thành JsonNode:

~~~java
JsonNode node = mapper.readTree(json);

assertTrue(node.has("user_name"));
assertFalse(node.has("username"));
~~~

Với nested object:

~~~java
JsonNode userNode = node.path("user");
assertTrue(userNode.has("user_name"));
assertFalse(userNode.has("password"));
~~~

So sánh cấu trúc giúp test ít phụ thuộc thứ tự property và khoảng trắng. Nếu hợp đồng yêu cầu chính xác chuỗi hoặc canonical JSON, có thể có test riêng cho quy tắc đó.

## 30. Tránh đăng ký mix-in trùng hoặc xung đột

Nếu cùng một mapper được cấu hình nhiều lần cho cùng target type:

~~~java
mapper.addMixIn(User.class, PublicUserMixin.class);
mapper.addMixIn(User.class, InternalUserMixin.class);
~~~

Lần đăng ký sau có thể thay thế mapping trước cho target tương ứng. Không nên dựa vào thứ tự cấu hình rải rác để tạo ra một tổ hợp mix-in không rõ ràng.

Nếu cần kết hợp metadata, tạo một mix-in tổng hợp kế thừa mix-in nền hoặc khai báo đầy đủ annotation cần thiết theo cách Jackson hỗ trợ. Sau đó đăng ký duy nhất một mix-in cho target trên mapper đó.

~~~java
public abstract class PartnerUserMixin extends CommonUserMixin {

    @JsonProperty("partner_name")
    abstract String getDisplayName();
}
~~~

Việc kế thừa mix-in cần được kiểm tra trên phiên bản Jackson đang dùng, nhất là khi annotation có xung đột. Cách dễ dự đoán nhất vẫn là một mix-in rõ ràng cho mỗi target trên mỗi mapper.

## 31. Mix-in và module

Có thể đóng gói cấu hình mix-in trong một Jackson Module để module tự đăng ký metadata khi được thêm vào mapper:

~~~java
public class PartnerJacksonModule extends SimpleModule {

    @Override
    public void setupModule(SetupContext context) {
        super.setupModule(context);
        context.setMixInAnnotations(
            ExternalUser.class,
            PartnerExternalUserMixin.class
        );
    }
}
~~~

Sau đó:

~~~java
ObjectMapper partnerMapper = baseMapper.copy();
partnerMapper.registerModule(new PartnerJacksonModule());
~~~

Module giúp đóng gói các quy tắc của một tích hợp và đăng ký chúng như một đơn vị. Nhưng module không tự giới hạn phạm vi nếu được đăng ký vào mapper toàn cục. Nó vẫn tác động đến mapper nhận module.

Vì vậy, nếu PartnerJacksonModule chứa mix-in chỉ dành cho partner, hãy đăng ký module trên partnerMapper. Không thêm nó vào mapper chính của ứng dụng trừ khi toàn bộ ứng dụng thực sự cần cùng hợp đồng.

## 32. Quản lý nhiều mapper trong Spring

Có thể khai báo bean mapper riêng với qualifier:

~~~java
@Configuration
public class PartnerJsonConfiguration {

    @Bean
    @Qualifier("partnerObjectMapper")
    ObjectMapper partnerObjectMapper(
            ObjectMapper applicationObjectMapper) {

        ObjectMapper mapper = applicationObjectMapper.copy();
        mapper.addMixIn(
            ExternalUser.class,
            PartnerExternalUserMixin.class
        );
        return mapper;
    }
}
~~~

Service tích hợp inject đúng mapper:

~~~java
@Service
public class PartnerClient {

    private final ObjectMapper mapper;

    public PartnerClient(
            @Qualifier("partnerObjectMapper")
            ObjectMapper mapper) {
        this.mapper = mapper;
    }
}
~~~

Trong cấu hình Spring thực tế, cần tránh inject nhầm bean mặc định khi có nhiều ObjectMapper. Dùng qualifier rõ ràng hoặc tốt hơn là inject một codec/service đóng gói mapper.

Một lựa chọn khác là không expose mapper trực tiếp:

~~~java
@Bean
PartnerJsonCodec partnerJsonCodec(ObjectMapper applicationObjectMapper) {
    ObjectMapper mapper = applicationObjectMapper.copy();
    mapper.addMixIn(
        ExternalUser.class,
        PartnerExternalUserMixin.class
    );
    return new PartnerJsonCodec(mapper);
}
~~~

Service khác chỉ thấy PartnerJsonCodec, nên không thể vô tình dùng mapper partner cho JSON nội bộ.

## 33. Lựa chọn giữa mapper copy và mapper xây dựng riêng

| Tình huống | Cách phù hợp |
|---|---|
| Cần giữ tất cả module và cấu hình của mapper ứng dụng, chỉ thêm vài mix-in | copy() rồi cấu hình thêm |
| Hợp đồng tích hợp độc lập, có module và feature riêng | Xây mapper riêng bằng builder/factory |
| Chỉ thay đổi tùy chọn ghi như pretty print | ObjectWriter |
| Chỉ thay đổi cách đọc/ghi một kiểu nhưng không cần annotation mix-in | Xem xét serializer/deserializer hoặc DTO |
| Cần field khác nhau theo người dùng/request | DTO hoặc cơ chế theo-operation, không đổi mix-in toàn cục |
| Cần một mapper chuyên biệt được dùng ở nhiều nơi trong tích hợp | Mapper/codec riêng được tạo một lần |

Mapper copy giúp giảm việc lặp cấu hình nền. Mapper xây dựng riêng làm ranh giới độc lập hơn nhưng cần khai báo đầy đủ module, naming strategy, date/time handling và các feature cần thiết.

## 34. Cẩn trọng với cache serializer và thay đổi mix-in runtime

Jackson có thể cache serializer/deserializer đã tạo dựa trên cấu hình mapper. Khi mix-in được đăng ký sau khi mapper đã xử lý một kiểu, việc thay đổi runtime không phải cách đáng tin cậy để điều khiển metadata cho lần gọi tiếp theo.

Ví dụ không nên:

~~~java
String before = mapper.writeValueAsString(user);
mapper.addMixIn(User.class, UserMixin.class);
String after = mapper.writeValueAsString(user);
~~~

Không nên dựa vào việc cache sẽ tự làm mới theo đúng ý muốn sau khi cấu hình đã được sử dụng. Hãy hoàn tất mix-in trước khi mapper được dùng và tạo mapper khác nếu cần hợp đồng khác.

Nếu ứng dụng cần thay đổi cấu hình động, hãy tạo một mapper mới theo một vòng đời rõ ràng thay vì sửa mapper đang hoạt động.

## 35. Ghi chú về phiên bản Jackson

Mix-in đã là một phần lâu đời của Jackson Databind, nhưng API builder, module setup và một số chi tiết introspection có thể khác theo phiên bản.

Khi triển khai:

- Kiểm tra phiên bản jackson-databind và jackson-annotations đang được dùng.
- Dùng API addMixIn hoặc builder được hỗ trợ trong phiên bản đó.
- Đảm bảo các artifact Jackson có phiên bản tương thích với nhau.
- Viết test trên mapper thực tế thay vì chỉ kiểm tra bằng một ObjectMapper mới không có cấu hình framework.
- Khi nâng Jackson, chạy lại test hợp đồng JSON cho các mix-in quan trọng.

Không nên nâng riêng jackson-annotations hoặc jackson-databind sang phiên bản không tương thích chỉ để dùng một API mix-in mới.

## 36. Ví dụ tổng hợp: cùng một target, hai hợp đồng JSON

Giả sử thư viện cung cấp:

~~~java
public class LegacyCustomer {
    private String name;
    private String taxNumber;
    private String internalMemo;

    public String getName() {
        return name;
    }

    public String getTaxNumber() {
        return taxNumber;
    }

    public String getInternalMemo() {
        return internalMemo;
    }
}
~~~

Hợp đồng nội bộ cần cả ba field. Hợp đồng partner chỉ cần name và taxNumber:

~~~java
public abstract class PartnerCustomerMixin {

    @JsonProperty("customer_name")
    abstract String getName();

    @JsonProperty("tax_id")
    abstract String getTaxNumber();

    @JsonIgnore
    abstract String getInternalMemo();
}
~~~

Tạo hai mapper:

~~~java
ObjectMapper internalMapper = new ObjectMapper();

ObjectMapper partnerMapper = internalMapper.copy();
partnerMapper.addMixIn(
    LegacyCustomer.class,
    PartnerCustomerMixin.class
);
~~~

Dùng đúng mapper:

~~~java
String internalJson =
    internalMapper.writeValueAsString(customer);

String partnerJson =
    partnerMapper.writeValueAsString(customer);
~~~

Output nội bộ theo metadata mặc định của target có thể là:

~~~json
{
  "name": "Mai",
  "taxNumber": "TAX-123",
  "internalMemo": "Review required"
}
~~~

Output partner theo mix-in:

~~~json
{
  "customer_name": "Mai",
  "tax_id": "TAX-123"
}
~~~

Mapper partner tạo ra một hợp đồng riêng mà không thay đổi cấu hình của internalMapper. Cả hai mapper có thể được dùng đồng thời vì mỗi mapper giữ cấu hình riêng và được cấu hình trước khi chia sẻ.

## 37. Những lỗi thường gặp khi khoanh vùng mix-in

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Endpoint khác bất ngờ mất field | Mix-in đăng ký trên mapper toàn cục | Dùng mapper chuyên biệt |
| Request body thay đổi sau khi thêm mix-in | Annotation ảnh hưởng cả deserialization | Kiểm tra chiều đọc và tách mapper nếu cần |
| Writer riêng vẫn chịu tác động của mix-in | ObjectWriter dùng cấu hình mapper gốc | Tạo mapper riêng rồi tạo writer từ mapper đó |
| Mix-in chỉ hoạt động ở một số nơi | Đăng ký trên mapper khác với mapper thực tế của framework | Xác định ObjectMapper được inject vào converter |
| Cấu hình thay đổi thất thường | Thêm/thay mix-in sau khi mapper đã hoạt động | Cấu hình trước khi dùng, không đổi runtime |
| Mix-in không ghép được method | Signature hoặc tên member không khớp target | Kiểm tra target và method/constructor tương ứng |
| Hai mix-in ghi đè lẫn nhau | Nhiều nơi đăng ký cho cùng target trên một mapper | Dùng một mix-in tổng hợp hoặc mapper riêng |
| Mapper chuyên biệt thiếu module | Tạo mapper mới mà không sao chép/cấu hình nền | Dùng factory hoặc copy mapper nền |
| Tích hợp partner làm đổi JSON job nền | Dùng chung mapper cho nhiều hợp đồng | Đóng gói codec và mapper riêng |
| Test đơn vị đúng nhưng ứng dụng sai | Test dùng mapper mới, ứng dụng dùng mapper auto-configured | Test với cấu hình mapper thực tế |

## 38. Quy trình xác định phạm vi trước khi thêm mix-in

Trước khi đăng ký một mix-in, hãy xác định:

1. Target type chính xác là class nào?
2. Mix-in thay đổi serialization, deserialization hay cả hai?
3. Những endpoint, job và message consumer nào dùng target type?
4. Các luồng đó dùng chung ObjectMapper nào?
5. Mix-in là quy tắc toàn ứng dụng hay chỉ dành cho một hợp đồng?
6. Có thể dùng DTO hoặc annotation trực tiếp thay cho mix-in không?
7. Nếu cần riêng, nên copy mapper nền hay xây mapper độc lập?
8. Mapper chuyên biệt được tạo một lần và inject ở đâu?
9. Test nào xác nhận mapper gốc không đổi?
10. Test nào xác nhận mapper chuyên biệt đúng ở root, nested object, collection và deserialize?

Sơ đồ quyết định:

~~~text
Cần thêm annotation cho target type?
              |
              v
        Mix-in phù hợp?
              |
        +-----+------+
        |            |
       Không        Có
        |            |
   Dùng DTO hoặc     v
   annotation   Phạm vi cần áp dụng?
   trực tiếp          |
                 +----+----------------+
                 |                     |
             Toàn ứng dụng       Chỉ một hợp đồng
                 |                     |
          Mapper ứng dụng        Mapper riêng/copy
                 |                     |
          Test hồi quy           Test cô lập phạm vi
~~~

## 39. Nguyên tắc thực hành

- Xem mix-in là cấu hình của ObjectMapper, không phải cấu hình của một lời gọi serialize.
- Xác định mọi nơi dùng mapper trước khi đăng ký mix-in.
- Không thêm hoặc thay mix-in theo từng request.
- Hoàn tất cấu hình mapper trước khi chia sẻ giữa nhiều thread.
- Dùng mapper riêng hoặc mapper copy khi một hợp đồng cần metadata khác.
- Tạo mapper chuyên biệt một lần, không tạo cho từng object.
- Dùng ObjectWriter/ObjectReader cho tùy chọn thao tác; không coi chúng là nơi cô lập mix-in.
- Kiểm tra cả serialization và deserialization.
- Kiểm tra target ở root, nested property, collection và Map.
- Giữ mix-in nhỏ, bám sát target và chỉ khai báo annotation cần thiết.
- Dùng tên mix-in thể hiện target và hợp đồng.
- Gom đăng ký mix-in vào factory, configuration hoặc module có phạm vi rõ.
- Không dùng mix-in để thay đổi field theo quyền hoặc trạng thái request.
- Khi dùng Spring, xác định chính xác mapper mà message converter đang sử dụng.
- Kiểm thử mapper nền và mapper chuyên biệt bằng các assertion cấu trúc JSON.

Mix-in là cách mạnh để điều chỉnh annotation mà không sửa class đích, nhưng phạm vi của nó gắn với ObjectMapper đã đăng ký. Khi mapper được dùng chung, mix-in có thể ảnh hưởng nhiều endpoint và cả hai chiều đọc/ghi. Cô lập cấu hình bằng mapper riêng hoặc mapper copy, tạo chúng trước khi sử dụng và kiểm tra mapper nền vẫn giữ hợp đồng cũ sẽ giúp thay đổi chỉ tác động đến nơi thực sự cần nó.
