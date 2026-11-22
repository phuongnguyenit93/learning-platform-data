# Áp dụng annotation cho lớp không sửa được bằng mix-in

Trong nhiều dự án, kiểu Java cần serialize/deserialize không thuộc quyền sở hữu của ứng dụng. Nó có thể đến từ thư viện bên thứ ba, SDK, generated code, legacy module hoặc một dependency không thể chỉnh sửa. Tuy nhiên, API vẫn cần đổi tên property JSON, bỏ field nhạy cảm, chỉ định constructor creator, chọn serializer/deserializer hoặc thêm metadata đa hình.

Jackson Mix-in cho phép gắn annotation Jackson vào một kiểu đích mà không sửa source của kiểu đó. Ứng dụng tạo một lớp abstract hoặc interface chỉ chứa annotation, sau đó đăng ký lớp này làm mix-in cho kiểu cần cấu hình. Khi Jackson introspect target, metadata từ mix-in được xem như metadata gắn trên target tương ứng.

Mix-in không tạo subclass runtime, không thay đổi bytecode của thư viện và không bổ sung hành vi Java. Nó chỉ thay đổi cách Jackson nhìn nhận annotation trong quá trình data binding. Vì vậy, mix-in rất hữu ích khi cần điều khiển JSON mapping của class bên ngoài nhưng vẫn giữ source dependency nguyên vẹn.

Các ví dụ dùng Jackson 2.x với package `com.fasterxml.jackson`. Hãy đăng ký mix-in trên đúng `ObjectMapper` mà ứng dụng thực sự dùng cho HTTP, file, message hoặc integration tương ứng.

## 1. Khi nào cần dùng Mix-in?

Giả sử một thư viện bên ngoài cung cấp lớp:

```java
package vendor.sdk;

public class VendorAccount {
    private String userName;
    private String accessToken;

    public VendorAccount() {
    }

    public String getUserName() {
        return userName;
    }

    public void setUserName(String userName) {
        this.userName = userName;
    }

    public String getAccessToken() {
        return accessToken;
    }

    public void setAccessToken(String accessToken) {
        this.accessToken = accessToken;
    }
}
```

Ứng dụng cần các thay đổi JSON sau:

- Property `userName` phải xuất hiện trong JSON dưới tên `user_name`.
- `accessToken` được phép nhận từ một payload tích hợp, nhưng không được ghi lại trong JSON output.
- Source của `VendorAccount` không thể sửa.

Không cần fork thư viện hoặc tạo một subclass chỉ để thêm annotation. Có thể tạo mix-in:

```java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

@JsonIgnoreProperties(value = "accessToken", allowSetters = true)
abstract class VendorAccountMixin {
    @JsonProperty("user_name")
    abstract String getUserName();

    @JsonProperty("user_name")
    abstract void setUserName(String userName);
}
```

Đăng ký mix-in:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.addMixIn(VendorAccount.class, VendorAccountMixin.class);
```

Từ thời điểm đó, Jackson dùng annotation trên `VendorAccountMixin` khi xử lý `VendorAccount` qua mapper này. Lớp `VendorAccount` gốc vẫn giữ nguyên.

## 2. Mix-in hoạt động như thế nào?

Mix-in là một nguồn annotation bổ sung cho một kiểu đích. Có thể hình dung:

```text
Kiểu gốc từ thư viện
VendorAccount
  - getUserName()
  - setUserName(...)
  - getAccessToken()
  - setAccessToken(...)
          |
          | Jackson ghép metadata
          v
Mix-in do ứng dụng định nghĩa
VendorAccountMixin
  - @JsonProperty("user_name")
  - @JsonIgnoreProperties(...)
          |
          v
ObjectMapper introspect target
          |
          v
JSON mapping theo annotation đã hợp nhất
```

Mix-in không phải object được serialize thay cho target. Jackson vẫn tạo hoặc đọc `VendorAccount`; mix-in chỉ cung cấp annotation tương ứng.

Một mix-in có thể khai báo:

- Annotation ở cấp lớp, ví dụ `@JsonIgnoreProperties`, `@JsonInclude`, `@JsonNaming`, `@JsonTypeInfo`.
- Annotation trên getter/setter có tên và signature khớp với member của target.
- Annotation trên field tương ứng nếu cần điều khiển field access.
- Annotation trên constructor có signature tương ứng với constructor của target.
- Annotation cho serializer, deserializer, creator, identity hoặc property format.

Mixin thường là abstract class hoặc interface. Các method khai báo trong mix-in có thể là abstract vì chúng chỉ dùng để khớp metadata; không cần cài đặt logic getter/setter.

## 3. Đăng ký Mix-in bằng `ObjectMapper.addMixIn()`

API cơ bản:

```java
mapper.addMixIn(TargetType.class, MixInType.class);
```

Trong đó:

- `TargetType` là kiểu thực tế mà Jackson sẽ serialize/deserialize.
- `MixInType` là lớp/interface do ứng dụng tạo để mang annotation.

Ví dụ:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.addMixIn(VendorAccount.class, VendorAccountMixin.class);

String json = mapper.writeValueAsString(account);
```

`addMixIn()` đăng ký mapping trên mapper. Cần dùng mapper đã đăng ký khi thực hiện cả serialize và deserialize. Nếu controller hoặc framework sử dụng một mapper khác, cấu hình mix-in ở mapper cục bộ trong service sẽ không tự động ảnh hưởng tới HTTP response.

### 3.1. Đăng ký bằng `JsonMapper.builder()`

Với Jackson 2.x có `JsonMapper`, có thể khai báo mix-in trong giai đoạn xây dựng mapper:

```java
JsonMapper mapper = JsonMapper.builder()
        .addMixIn(VendorAccount.class, VendorAccountMixin.class)
        .build();
```

Cách builder làm rõ rằng cấu hình được hoàn tất trước khi mapper được đưa vào sử dụng. Với ứng dụng đang dùng `ObjectMapper` được framework quản lý, hãy dùng điểm cấu hình của framework thay vì tạo mapper mới không được framework sử dụng.

### 3.2. Một mix-in có thể áp dụng cho nhiều target

Nếu nhiều class bên ngoài có cùng quy ước property và accessor tương thích, có thể đăng ký cùng một mix-in cho từng target:

```java
mapper.addMixIn(VendorAccount.class, AccountNamingMixin.class);
mapper.addMixIn(PartnerAccount.class, AccountNamingMixin.class);
```

Điều kiện là các member mà mix-in khai báo phải khớp với member tương ứng của từng target. Nếu cấu trúc khác nhau, nên tạo mix-in riêng cho từng kiểu để tránh annotation không được áp dụng hoặc áp dụng sai property.

## 4. Đổi tên property bằng annotation trong Mix-in

Giả sử class ngoài có getter/setter `getUserName()` và `setUserName(String)`, nhưng JSON contract yêu cầu `user_name`:

```java
abstract class VendorAccountMixin {
    @JsonProperty("user_name")
    abstract String getUserName();

    @JsonProperty("user_name")
    abstract void setUserName(String userName);
}
```

Sau khi đăng ký, serialize có dạng:

```json
{
  "user_name": "an"
}
```

Deserialize cũng có thể nhận tên `user_name`:

```java
VendorAccount account = mapper.readValue(
        "{\"user_name\":\"an\"}",
        VendorAccount.class
);
```

Jackson vẫn gọi accessor thật trên `VendorAccount`. Các method abstract trong mix-in chỉ cung cấp metadata để Jackson liên kết với property tương ứng.

### 4.1. Khớp tên và signature

Tên method trong mix-in cần tương ứng với accessor của target. Với getter, hãy khớp tên và kiểu trả về; với setter, hãy khớp tên và kiểu tham số. Nếu target đổi tên method hoặc thay đổi kiểu, mix-in có thể không còn tác dụng như dự kiến.

Ví dụ target có:

```java
public String getDisplayName() { ... }
public void setDisplayName(String value) { ... }
```

thì mix-in nên khai báo `getDisplayName()` và `setDisplayName(String)`, không phải một method tên tùy ý như `displayName()`.

Không cần triển khai thân method. Không gọi trực tiếp method mix-in trong code ứng dụng.

### 4.2. Annotation trên field

Nếu target được Jackson phát hiện qua field thay vì getter/setter, mix-in có thể khai báo field cùng tên để cung cấp annotation:

```java
abstract class VendorConfigMixin {
    @JsonProperty("retry_count")
    Integer retryCount;
}
```

Jackson ghép field metadata theo tên field. Tuy nhiên, dùng accessor method thường dễ đọc và ít phụ thuộc visibility hơn nếu target có getter/setter công khai. Cần kiểm tra visibility rules thực tế của mapper.

## 5. Ẩn property nhạy cảm bằng Mix-in

Có thể dùng `@JsonIgnore` trên getter tương ứng:

```java
abstract class VendorAccountMixin {
    @JsonIgnore
    abstract String getAccessToken();
}
```

Khi serialize `VendorAccount`, property `accessToken` không xuất hiện. Nếu cần điều khiển riêng chiều đọc và chiều ghi, dùng `@JsonProperty(access = ...)` hoặc `@JsonIgnoreProperties` với `allowGetters`/`allowSetters`.

### 5.1. Chỉ ẩn khi serialize, vẫn nhận input

Ví dụ trước dùng:

```java
@JsonIgnoreProperties(value = "accessToken", allowSetters = true)
abstract class VendorAccountMixin {
}
```

Ý nghĩa là Jackson bỏ qua `accessToken` khi ghi object ra JSON nhưng vẫn cho phép setter nhận giá trị khi deserialize. Cách này phù hợp với một số kiểu request tích hợp, nhưng cần xem xét liệu token có nên được nhận trực tiếp vào kiểu dùng chung hay không.

Một cách khác là đặt access direction lên property:

```java
abstract class VendorAccountMixin {
    @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
    abstract String getAccessToken();
}
```

`WRITE_ONLY` cho phép nhận giá trị từ JSON vào object và không serialize property trở lại. `READ_ONLY` có chiều ngược lại: có thể xuất giá trị từ object nhưng bỏ qua giá trị client gửi vào.

### 5.2. Ẩn hoàn toàn trong cả hai chiều

Nếu property không được phép đi qua JSON ở cả hai chiều:

```java
abstract class VendorAccountMixin {
    @JsonIgnore
    abstract String getPrivateKey();
}
```

Hãy nhớ annotation này chỉ kiểm soát Jackson mapping qua mapper có đăng ký mix-in. Nó không xóa field khỏi object, không ngăn code Java truy cập giá trị, không tự che `toString()` và không bảo vệ log hoặc database.

## 6. Thêm annotation ở cấp lớp

Mix-in không cần khai báo method nếu mục tiêu là thêm annotation cho toàn bộ kiểu:

```java
@JsonIgnoreProperties({"internalNote", "debugToken"})
@JsonInclude(JsonInclude.Include.NON_NULL)
abstract class VendorAccountMixin {
}
```

Đăng ký:

```java
mapper.addMixIn(VendorAccount.class, VendorAccountMixin.class);
```

Các annotation được áp dụng như metadata của target class:

- `@JsonIgnoreProperties` bỏ qua những property đã liệt kê.
- `@JsonInclude(NON_NULL)` bỏ property có giá trị null khỏi output theo quy tắc inclusion.

`NON_NULL` không phải cơ chế bảo mật. Một property nhạy cảm có giá trị khác null vẫn được serialize nếu không có chính sách ẩn riêng.

Các annotation cấp lớp khác có thể được áp dụng tương tự, ví dụ `@JsonNaming`, `@JsonTypeInfo`, `@JsonSubTypes`, `@JsonIdentityInfo` hoặc `@JsonFilter`.

## 7. Thêm `@JsonCreator` cho class immutable bên ngoài

Một số kiểu bên ngoài chỉ có constructor tham số và không có no-argument constructor hoặc setter. Nếu Jackson không suy ra được cách tạo object từ JSON, mix-in có thể cung cấp metadata `@JsonCreator` và `@JsonProperty` cho constructor có sẵn.

Target:

```java
package vendor.geometry;

public final class ExternalPoint {
    private final int x;
    private final int y;

    public ExternalPoint(int x, int y) {
        this.x = x;
        this.y = y;
    }

    public int getX() {
        return x;
    }

    public int getY() {
        return y;
    }
}
```

Mix-in:

```java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;

abstract class ExternalPointMixin {
    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    ExternalPointMixin(
            @JsonProperty("x") int x,
            @JsonProperty("y") int y) {
    }
}
```

Đăng ký:

```java
mapper.addMixIn(ExternalPoint.class, ExternalPointMixin.class);
```

Jackson dùng metadata creator từ mix-in để gọi constructor thực của `ExternalPoint`. Constructor được khai báo trong mix-in phải tương ứng với constructor target theo số lượng và kiểu tham số; mix-in không cung cấp một constructor runtime thay thế.

### 7.1. Vì sao cần khớp constructor?

Jackson cần ghép annotation creator với constructor thực tế. Nếu target có constructor `(int x, int y)` nhưng mix-in khai báo `(long x, long y)`, đó không phải signature tương ứng. Khi thư viện đổi constructor, mix-in cũ có thể không còn được áp dụng.

Với nhiều constructor, hãy chỉ rõ constructor nào là creator. Nếu có factory method static thay vì constructor, kiểm tra khả năng gắn annotation tương ứng lên method theo cấu trúc target và version Jackson.

### 7.2. Dùng mix-in cho constructor không có tên tham số

Ngay cả khi thư viện được biên dịch mà không lưu parameter names, `@JsonProperty` trên tham số của mix-in vẫn cung cấp tên JSON rõ ràng cho Jackson. Điều này giúp không phụ thuộc compiler flag `-parameters` hoặc metadata parameter name của thư viện.

## 8. Gắn custom serializer/deserializer cho kiểu bên ngoài

Mix-in cũng có thể bổ sung `@JsonSerialize` và `@JsonDeserialize` cho class mà ứng dụng không sửa được.

Ví dụ, SDK cung cấp `VendorMoney`, nhưng API cần định dạng tiền theo chuỗi có currency:

```java
import com.fasterxml.jackson.databind.annotation.JsonSerialize;
import com.fasterxml.jackson.databind.annotation.JsonDeserialize;

@JsonSerialize(using = VendorMoneySerializer.class)
@JsonDeserialize(using = VendorMoneyDeserializer.class)
abstract class VendorMoneyMixin {
}
```

Đăng ký:

```java
mapper.addMixIn(VendorMoney.class, VendorMoneyMixin.class);
```

Serializer/deserializer là các class thật do ứng dụng cung cấp. Mix-in chỉ kết nối chúng với target type. Jackson vẫn gọi serializer/deserializer đã chỉ định khi xử lý `VendorMoney`.

### 8.1. Áp dụng custom deserializer cho một property cụ thể

Nếu chỉ một property của target cần định dạng đặc biệt, khai báo method khớp accessor:

```java
abstract class VendorEventMixin {
    @JsonDeserialize(using = LegacyTimestampDeserializer.class)
    abstract Instant getOccurredAt();
}
```

Khi Jackson đọc property tương ứng, nó sử dụng custom deserializer. Không cần sửa `VendorEvent`.

### 8.2. Serializer cho collection content hoặc map key

`@JsonSerialize` và `@JsonDeserialize` có các thuộc tính như `contentUsing` và `keyUsing` để cấu hình phần tử container hoặc map key. Có thể đặt chúng trên accessor trong mix-in nếu target có property phù hợp.

Ví dụ:

```java
abstract class VendorReportMixin {
    @JsonDeserialize(contentUsing = LegacyCodeDeserializer.class)
    abstract List<LegacyCode> getCodes();
}
```

Ở đây custom deserializer được áp dụng cho từng phần tử `codes`, không thay thế deserializer của toàn bộ `List`.

## 9. Thêm polymorphic metadata cho base class/interface bên ngoài

Nếu một interface bên thứ ba có nhiều implementation và JSON cần discriminator, mix-in có thể thêm `@JsonTypeInfo` cùng `@JsonSubTypes`:

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind"
)
@JsonSubTypes({
        @JsonSubTypes.Type(value = VendorCardEvent.class, name = "card"),
        @JsonSubTypes.Type(value = VendorBankEvent.class, name = "bank")
})
abstract class VendorPaymentEventMixin {
}
```

Đăng ký mix-in cho base type:

```java
mapper.addMixIn(VendorPaymentEvent.class, VendorPaymentEventMixin.class);
```

JSON có thể chứa:

```json
{
  "kind": "card",
  "last4": "4242"
}
```

Mix-in giúp bổ sung type metadata mà không thay đổi interface nguồn. Danh sách subtype vẫn phải được kiểm soát tường minh; không dùng type id là tên class tùy ý từ JSON không tin cậy.

## 10. Thêm object identity hoặc filter bằng Mix-in

Các annotation liên quan đến graph và output cũng có thể được gắn qua mix-in.

Object identity:

```java
@JsonIdentityInfo(
        generator = ObjectIdGenerators.PropertyGenerator.class,
        property = "id"
)
abstract class ExternalNodeMixin {
}
```

Filter:

```java
@JsonFilter("externalOutput")
abstract class ExternalReportMixin {
}
```

Sau khi đăng ký, mapper có thể áp dụng `ObjectIdResolver`/object identity hoặc `FilterProvider` cho target tương ứng. Mix-in chỉ thêm annotation; cấu hình resolver, filter provider và chính sách quyền vẫn phải được cung cấp ở mapper hoặc application layer.

## 11. Mix-in không thêm property hoặc hành vi mới

Một giới hạn quan trọng: mix-in không phải subclass và không mở rộng model target.

Ví dụ, nếu target không có property `displayLabel`, khai báo method này trong mix-in:

```java
abstract class VendorAccountMixin {
    @JsonProperty("display_label")
    abstract String getDisplayLabel();
}
```

không tạo ra `getDisplayLabel()` trên `VendorAccount`. Jackson không có implementation để gọi. Muốn thêm dữ liệu tổng hợp hoặc property mới, hãy dùng DTO/wrapper, custom serializer hoặc một model adapter có logic thực sự.

Mix-in có thể thay đổi metadata của property hiện hữu, nhưng không thể:

- Thêm field thật vào target.
- Cung cấp getter/setter runtime cho target.
- Thay đổi constructor hoặc phương thức thực thi.
- Thay đổi class thực tế được khởi tạo.
- Bổ sung logic chuyển đổi ngoài serializer/deserializer được chỉ định.

Nếu cần bổ sung field không tồn tại trong target, hãy tạo DTO riêng hoặc custom serializer để ghi field đó dựa trên dữ liệu có sẵn.

## 12. Một mix-in phải khớp đúng kiểu đích

Đăng ký:

```java
mapper.addMixIn(VendorAccount.class, VendorAccountMixin.class);
```

chỉ thiết lập metadata cho target đã chỉ định. Nếu ứng dụng serialize một subclass khác, cần kiểm tra quy tắc annotation inheritance và đăng ký mix-in cho subtype nếu subtype đó có cấu trúc hoặc policy riêng.

Ví dụ:

```java
mapper.addMixIn(VendorAccount.class, VendorAccountMixin.class);
mapper.addMixIn(SpecialVendorAccount.class, SpecialVendorAccountMixin.class);
```

Đừng giả định mix-in cho base class sẽ tự mô tả chính xác mọi property riêng của tất cả subclass. Với hierarchy đa hình, test từng concrete subtype và JSON output thực tế.

## 13. Annotation từ target và Mix-in được hợp nhất như thế nào?

Mix-in được thiết kế để bổ sung hoặc ghi đè annotation của target trong quá trình Jackson introspect. Nếu cùng một annotation được khai báo ở cả target và mix-in, annotation từ mix-in thường được xem là nguồn cấu hình ưu tiên cho target tương ứng. Tuy nhiên, kết quả cuối cùng còn phụ thuộc loại annotation, vị trí member, quy tắc hợp nhất property và version Jackson.

Ví dụ target đã có:

```java
@JsonProperty("userName")
public String getUserName() { ... }
```

Mix-in có thể chỉ định:

```java
abstract class VendorAccountMixin {
    @JsonProperty("user_name")
    abstract String getUserName();
}
```

Kết quả dự kiến là property dùng tên `user_name` theo cấu hình mix-in. Hãy xác nhận bằng test trên mapper thực tế, đặc biệt khi target có nhiều annotation hoặc accessor cùng tham gia một logical property.

Không nên đặt annotation mâu thuẫn ở field, getter, setter và constructor rồi dựa vào một quy tắc ưu tiên ngầm. Giữ mix-in đơn giản, chỉ bổ sung metadata cần thiết và test output.

## 14. Một target có nhiều chính sách JSON khác nhau

`ObjectMapper` duy trì một mapping mix-in cho mỗi target type trong cấu hình của mapper. Nếu gọi `addMixIn()` nhiều lần cho cùng target với các mix-in khác nhau, mapping cục bộ sau có thể thay thế mapping trước.

Không nên dùng một mapper rồi thay mix-in theo từng request để thay đổi chính sách output. Mapper có thể được cache và chia sẻ giữa nhiều luồng; thay đổi cấu hình sau khi bắt đầu sử dụng có thể tạo hành vi khó dự đoán.

Nếu cùng một target cần hai hợp đồng JSON khác nhau, cân nhắc:

- Tạo hai `ObjectMapper` được cấu hình riêng và dùng ở các ranh giới integration tách biệt.
- Dùng DTO riêng cho từng loại output.
- Dùng JSON Views hoặc property filters nếu sự khác nhau chỉ là tập field và có thể kiểm soát an toàn bằng `ObjectWriter`.

Ví dụ hai mapper:

```java
ObjectMapper publicMapper = new ObjectMapper();
publicMapper.addMixIn(VendorAccount.class, PublicVendorAccountMixin.class);

ObjectMapper partnerMapper = new ObjectMapper();
partnerMapper.addMixIn(VendorAccount.class, PartnerVendorAccountMixin.class);
```

Mỗi mapper có policy độc lập. Không đăng ký một mix-in thay thế qua lại trên mapper đang phục vụ request.

## 15. Kết hợp Mix-in với `SimpleModule`

Mix-in và module phục vụ hai phần cấu hình bổ sung nhau:

- Mix-in cung cấp annotation metadata cho target type.
- `SimpleModule` đăng ký serializer, deserializer, key serializer, key deserializer, subtype hoặc các thành phần Databind khác.

Ví dụ:

```java
SimpleModule module = new SimpleModule("vendor-json");
module.addSerializer(VendorMoney.class, new VendorMoneySerializer());
module.addDeserializer(VendorMoney.class, new VendorMoneyDeserializer());

ObjectMapper mapper = new ObjectMapper();
mapper.addMixIn(VendorAccount.class, VendorAccountMixin.class);
mapper.registerModule(module);
```

Có thể gom cấu hình vào một phương thức khởi tạo mapper để mọi integration dùng cùng một quy tắc:

```java
public ObjectMapper createVendorMapper() {
    ObjectMapper mapper = new ObjectMapper();
    mapper.addMixIn(VendorAccount.class, VendorAccountMixin.class);
    mapper.addMixIn(ExternalPoint.class, ExternalPointMixin.class);
    mapper.registerModule(new VendorJsonModule());
    return mapper;
}
```

Hoàn tất mọi cấu hình trước khi chia sẻ mapper. Nếu framework quản lý mapper, hãy đăng ký mix-in và module trong builder/configuration của framework.

## 16. Tích hợp với Spring hoặc framework quản lý ObjectMapper

Trong ứng dụng Spring, Jackson thường được cấu hình bởi framework và mapper đó được dùng trong HTTP message converter. Nếu tạo `new ObjectMapper()` riêng bên trong service, mix-in chỉ có hiệu lực với mapper riêng đó.

Có thể đăng ký mix-in trong cấu hình `Jackson2ObjectMapperBuilder`:

```java
@Configuration
public class JacksonConfiguration {
    @Bean
    public Jackson2ObjectMapperBuilderCustomizer vendorMixIns() {
        return builder -> {
            builder.mixIn(VendorAccount.class, VendorAccountMixin.class);
            builder.mixIn(ExternalPoint.class, ExternalPointMixin.class);
        };
    }
}
```

Tên class và cách cấu hình cụ thể phụ thuộc phiên bản Spring Boot/Spring Framework. Trong một số phiên bản, có thể cấu hình qua bean `Jackson2ObjectMapperBuilder`, customizer hoặc trực tiếp trên `ObjectMapper` bean. Điều quan trọng là đăng ký trên mapper được HTTP converter sử dụng.

Sau khi cấu hình, kiểm tra endpoint thực tế hoặc message converter thay vì chỉ test một mapper tự tạo trong unit test. Nếu ứng dụng có nhiều mapper/qualifier, ghi rõ mapper nào dành cho public API và mapper nào dành cho đối tác.

## 17. Tổ chức package và đặt tên Mix-in

Mix-in nên nằm trong package cấu hình JSON của ứng dụng, không đặt trong package của dependency bên ngoài. Ví dụ:

```text
com.example.integration.vendor
  ├── VendorClient.java
  ├── VendorAccountMapper.java
  └── jackson
      ├── VendorAccountMixin.java
      ├── ExternalPointMixin.java
      └── VendorJsonModule.java
```

Tên mix-in nên thể hiện target hoặc mục đích, chẳng hạn `VendorAccountMixin`, `ExternalPointMixin`, `PublicVendorEventMixin`. Nếu có nhiều hợp đồng cho cùng target, tên nên phân biệt rõ `Public...Mixin` và `Partner...Mixin`.

Đặt mix-in gần cấu hình integration giúp reviewer thấy được target, annotation và mapper đăng ký nó ở cùng một vùng code. Tránh rải các lời gọi `addMixIn()` ở nhiều service không liên quan.

## 18. Kiểm thử Mix-in bằng JSON thực tế

Với ví dụ `VendorAccountMixin`, cần kiểm tra cả chiều ghi và chiều đọc.

```java
class VendorAccountJsonTest {
    private final ObjectMapper mapper = new ObjectMapper()
            .addMixIn(VendorAccount.class, VendorAccountMixin.class);

    @Test
    void renamesUserNameAndHidesTokenOnSerialization() throws Exception {
        VendorAccount account = new VendorAccount();
        account.setUserName("an");
        account.setAccessToken("secret-value");

        String json = mapper.writeValueAsString(account);
        JsonNode node = mapper.readTree(json);

        assertEquals("an", node.path("user_name").asText());
        assertFalse(node.has("userName"));
        assertFalse(node.has("accessToken"));
        assertFalse(json.contains("secret-value"));
    }

    @Test
    void acceptsTokenOnInputWhenAllowSettersIsEnabled() throws Exception {
        String json = """
                {
                  "user_name": "an",
                  "accessToken": "incoming-secret"
                }
                """;

        VendorAccount account = mapper.readValue(json, VendorAccount.class);

        assertEquals("an", account.getUserName());
        assertEquals("incoming-secret", account.getAccessToken());
    }
}
```

Ví dụ giả định `VendorAccountMixin` dùng `@JsonIgnoreProperties(value = "accessToken", allowSetters = true)` như phần 1. Nếu chính sách yêu cầu từ chối hoàn toàn token đầu vào, hãy bỏ `allowSetters` hoặc dùng DTO request phù hợp và cập nhật test.

### 18.1. Kiểm thử creator constructor

Với kiểu immutable, kiểm tra JSON có thể tạo đúng target:

```java
ExternalPoint point = mapper.readValue(
        "{\"x\":10,\"y\":20}",
        ExternalPoint.class
);

assertEquals(10, point.getX());
assertEquals(20, point.getY());
```

Đồng thời kiểm tra serialize để bảo đảm property name vẫn đúng hợp đồng. Nếu target thay đổi constructor, test này sẽ phát hiện mix-in không còn khớp.

### 18.2. Kiểm thử mapper thật của ứng dụng

Nếu ứng dụng có mapper do Spring hoặc framework khác quản lý, test cấu hình bean thực tế hoặc endpoint integration. Test một `new ObjectMapper()` riêng không chứng minh framework đã dùng cùng mix-in.

## 19. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Annotation trong mix-in không có tác dụng | Chưa đăng ký mix-in hoặc dùng mapper khác | Đăng ký trên mapper thực sự thực hiện binding |
| Property không được đổi tên | Method mix-in không khớp getter/setter của target | Khớp tên, kiểu trả về và kiểu tham số |
| Constructor creator không được nhận diện | Signature mix-in không tương ứng constructor target | Khớp số lượng/thứ tự/kiểu tham số và gắn `@JsonCreator`/`@JsonProperty` |
| Mix-in tạo ra field không tồn tại | Hiểu nhầm mix-in là subclass | Dùng DTO hoặc custom serializer để thêm dữ liệu mới |
| Secret vẫn xuất hiện trong log | Mix-in chỉ điều khiển Jackson mapper đó | Tạo chính sách log riêng và không log object nhạy cảm |
| Một subtype không nhận annotation mong muốn | Chỉ đăng ký mix-in trên base type hoặc target khác | Kiểm tra concrete type và đăng ký mix-in phù hợp |
| Hai chính sách ghi đè nhau | Nhiều lần `addMixIn()` cho cùng target trên cùng mapper | Hợp nhất annotation hoặc dùng mapper riêng |
| Test đúng nhưng API thật sai | Test mapper tự tạo, framework dùng mapper khác | Kiểm thử mapper bean/message converter thực tế |
| Annotation target và mix-in mâu thuẫn | Metadata được hợp nhất theo quy tắc introspection | Giữ một nguồn cấu hình rõ ràng và kiểm tra JSON output |
| Mix-in không thay đổi hành vi của method | Mix-in chỉ thêm annotation, không cung cấp implementation | Viết serializer/deserializer hoặc adapter có logic thực tế |

## 20. Khi nào nên dùng Mix-in, DTO hay custom serializer?

| Nhu cầu | Cách phù hợp |
|---|---|
| Thêm `@JsonProperty`, `@JsonIgnore`, `@JsonFormat` cho class bên ngoài | Mix-in |
| Thêm `@JsonCreator` cho constructor hiện có | Mix-in khớp constructor |
| Bổ sung `@JsonTypeInfo`/`@JsonSubTypes` cho interface ngoài | Mix-in hoặc subtype registration trong module |
| Chọn serializer/deserializer cho toàn bộ kiểu ngoài | Mix-in với `@JsonSerialize`/`@JsonDeserialize` hoặc đăng ký module |
| Chỉ thay đổi danh sách field public/admin | DTO riêng, JSON View hoặc property filter |
| Thêm field tổng hợp không tồn tại trong target | DTO hoặc custom serializer |
| Thay đổi cấu trúc JSON phức tạp | Custom serializer/deserializer hoặc adapter |
| Hai hệ thống cần hợp đồng hoàn toàn khác nhau | DTO/mapper riêng cho từng integration |

Mix-in phù hợp nhất khi cấu trúc object hiện tại đã đủ dùng và ứng dụng chỉ cần thay đổi cách Jackson nhìn nhận annotation. Khi cần biến đổi dữ liệu hoặc thêm logic, hãy chọn một lớp adapter thực sự có hành vi.

## 21. Checklist triển khai

Trước khi đưa mix-in vào ứng dụng, hãy xác nhận:

1. Target class thực sự là kiểu Jackson serialize/deserialize.
2. Mapper dùng ở ranh giới tích hợp đã đăng ký đúng mix-in.
3. Method/field/constructor trong mix-in khớp member của target.
4. Annotation được đặt đúng phạm vi: class, property hay creator parameter.
5. Chính sách input và output đã được phân biệt rõ.
6. Không nhầm mix-in với cơ chế thêm property hoặc logic Java.
7. Không có mix-in khác ghi đè mapping của cùng target ngoài dự kiến.
8. Mapper được cấu hình hoàn tất trước khi dùng đồng thời.
9. Test cả serialize, deserialize, nested property và constructor nếu có.
10. Kiểm tra log, export, cache và các đường dữ liệu khác ngoài mapper.

## 22. Kết luận

Jackson Mix-in cho phép bổ sung hoặc điều chỉnh annotation của một class bên ngoài mà không sửa source của class đó. Tạo abstract class/interface chứa annotation, khai báo member tương ứng với getter/setter/constructor của target rồi đăng ký bằng `ObjectMapper.addMixIn()` hoặc builder. Mix-in có thể đổi tên property, ẩn field, thêm creator metadata, chọn serializer/deserializer, cấu hình polymorphism hoặc object identity.

Mix-in chỉ thay đổi metadata Jackson nhìn thấy; nó không thêm field, không cung cấp implementation và không thay đổi runtime type. Hãy đăng ký trên đúng mapper, giữ signature khớp target, hoàn tất cấu hình trước khi dùng và kiểm thử JSON thực tế. Khi cần dữ liệu hoặc logic mới, dùng DTO hay custom serializer thay vì kỳ vọng mix-in mở rộng class.
