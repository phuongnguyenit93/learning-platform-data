# Thiết kế tiền tố và hậu tố cho cấu trúc nhúng

Một DTO thường chứa các object con để mô hình hóa dữ liệu theo nhóm. Ví dụ, Invoice có BillingAddress và ShippingAddress; Customer có ContactInfo; một response có thể chứa thông tin người tạo và người cập nhật. Cấu trúc Java này dễ tổ chức, nhưng đôi khi hợp đồng JSON cần các field của object con xuất hiện trực tiếp ở cấp cha.

Jackson hỗ trợ việc làm phẳng object con bằng annotation **@JsonUnwrapped**. Khi dùng annotation này, Jackson không ghi tên property bao quanh; thay vào đó, nó đưa các property của object con lên cùng cấp với property của object cha.

Việc làm phẳng có thể tạo ra xung đột tên. Nếu hai object con đều có field city, JSON có thể chứa hai key city. Thuộc tính prefix và suffix của @JsonUnwrapped cho phép thêm tiền tố và hậu tố vào tên property được nhúng, tạo namespace rõ ràng cho từng nhóm dữ liệu.

Ví dụ, thay vì JSON lồng nhau:

~~~json
{
  "invoiceId": "INV-100",
  "billingAddress": {
    "city": "Hanoi",
    "postalCode": "100000"
  },
  "shippingAddress": {
    "city": "Da Nang",
    "postalCode": "550000"
  }
}
~~~

có thể thiết kế JSON phẳng:

~~~json
{
  "invoiceId": "INV-100",
  "billing_city": "Hanoi",
  "billing_postalCode": "100000",
  "shipping_city": "Da Nang",
  "shipping_postalCode": "550000"
}
~~~

Các field vẫn được tổ chức thành object riêng trong Java; prefix giúp chúng có tên duy nhất trong JSON.

## 1. Cấu trúc nhúng và vấn đề trùng tên

Giả sử mô hình Java:

~~~java
public class Address {
    private String city;
    private String postalCode;

    // Constructors, getters and setters
}

public class Invoice {
    private String invoiceId;
    private Address billingAddress;
    private Address shippingAddress;

    // Constructors, getters and setters
}
~~~

Theo cách serialize mặc định, Jackson giữ cấu trúc object lồng nhau:

~~~json
{
  "invoiceId": "INV-100",
  "billingAddress": {
    "city": "Hanoi",
    "postalCode": "100000"
  },
  "shippingAddress": {
    "city": "Da Nang",
    "postalCode": "550000"
  }
}
~~~

Cấu trúc này rõ ràng và thường là lựa chọn tốt cho API. Tuy nhiên, một số hợp đồng yêu cầu field nằm cùng cấp, ví dụ để tương thích với hệ thống cũ, định dạng biểu mẫu phẳng hoặc schema của một message broker.

Nếu chỉ làm phẳng hai object con mà không đổi tên property, kết quả có thể có key trùng:

~~~json
{
  "invoiceId": "INV-100",
  "city": "Hanoi",
  "postalCode": "100000",
  "city": "Da Nang",
  "postalCode": "550000"
}
~~~

JSON object không nên chứa các key trùng nhau. Một số parser giữ giá trị xuất hiện sau, một số công cụ có thể xử lý khác nhau; consumer có thể mất dữ liệu hoặc tạo kết quả không nhất quán.

Prefix và suffix giải quyết vấn đề bằng cách biến tên property thành một tên có namespace:

~~~text
billingAddress.city       -> billing_city
billingAddress.postalCode -> billing_postalCode

shippingAddress.city       -> shipping_city
shippingAddress.postalCode -> shipping_postalCode
~~~

## 2. @JsonUnwrapped là gì?

@JsonUnwrapped là annotation của Jackson Databind, thuộc package com.fasterxml.jackson.annotation. Annotation này yêu cầu Jackson đưa các property của một POJO lồng nhau lên object JSON bao quanh.

Ví dụ:

~~~java
public class UserResponse {

    private String username;

    @JsonUnwrapped
    private ContactInfo contactInfo;
}
~~~

Nếu ContactInfo có email và phone, JSON sẽ có dạng:

~~~json
{
  "username": "an",
  "email": "an@example.com",
  "phone": "0900000000"
}
~~~

Property contactInfo không xuất hiện như một object lồng. Các field của nó được ghi trực tiếp ở cấp UserResponse.

Có thể đặt @JsonUnwrapped trên field hoặc getter được Jackson sử dụng. Nếu mô hình dùng visibility hoặc annotation tùy chỉnh, hãy bảo đảm annotation nằm trên member mà Jackson nhận diện cho property.

### 2.1. So sánh với serialize lồng nhau

| Cách biểu diễn | JSON |
|---|---|
| Mặc định | {"contactInfo":{"email":"an@example.com"}} |
| @JsonUnwrapped | {"email":"an@example.com"} |
| @JsonUnwrapped(prefix = "contact_") | {"contact_email":"an@example.com"} |

@JsonUnwrapped thay đổi hình dạng JSON của property. Nó không thay đổi cấu trúc Java hoặc yêu cầu phải chuyển ContactInfo thành các field riêng trong UserResponse.

### 2.2. Annotation có thể dùng cho cả đọc và ghi

@JsonUnwrapped được hỗ trợ cho serialization và deserialization trong các trường hợp POJO phù hợp. Khi ghi, Jackson làm phẳng các property con. Khi đọc, Jackson nhận các field phẳng và đưa chúng trở lại object con.

Ví dụ:

~~~java
UserResponse user = mapper.readValue(json, UserResponse.class);
~~~

Nếu JSON có email và phone ở cấp root, Jackson có thể bind chúng vào ContactInfo.

Hãy kiểm tra cả hai chiều. Một cấu trúc serialize được chưa chắc đã deserialize đúng nếu có tên field xung đột, constructor không phù hợp hoặc cấu hình visibility khác nhau.

## 3. Dùng prefix để tạo namespace

Prefix là chuỗi được thêm vào trước tên từng property của object nhúng.

~~~java
public class Invoice {

    private String invoiceId;

    @JsonUnwrapped(prefix = "billing_")
    private Address billingAddress;

    @JsonUnwrapped(prefix = "shipping_")
    private Address shippingAddress;
}
~~~

Với Address có city và postalCode, JSON:

~~~json
{
  "invoiceId": "INV-100",
  "billing_city": "Hanoi",
  "billing_postalCode": "100000",
  "shipping_city": "Da Nang",
  "shipping_postalCode": "550000"
}
~~~

Prefix thể hiện nguồn gốc của field. Người đọc payload có thể nhận biết billing_city thuộc địa chỉ thanh toán, còn shipping_city thuộc địa chỉ giao hàng.

### 3.1. Chọn prefix có ý nghĩa

Prefix nên phản ánh vai trò của object nhúng, không chỉ tên class Java.

Ví dụ:

| Property Java | Prefix phù hợp | Field JSON |
|---|---|---|
| billingAddress | billing_ | billing_city |
| shippingAddress | shipping_ | shipping_city |
| contactInfo | contact_ | contact_email |
| auditInfo | audit_ | audit_createdAt |
| sender | sender_ | sender_name |
| receiver | receiver_ | receiver_name |

Tên như billing_ và shipping_ thể hiện ngữ nghĩa nghiệp vụ. Tên như address1_ hoặc object2_ khó hiểu hơn và dễ bị thay đổi khi DTO được tổ chức lại.

Không nên dùng prefix phụ thuộc tên class nếu tên class chỉ là chi tiết triển khai. Hợp đồng JSON nên giữ ổn định khi class được đổi tên.

### 3.2. Prefix cần phân biệt chữ hoa/chữ thường

Nếu hệ thống dùng snake_case, camelCase hoặc kebab-case, hãy thống nhất quy ước:

- billing_city
- billingCity
- billing-city

Không nên trộn nhiều phong cách trong cùng một object nếu không có lý do tương thích. Prefix phải khớp chính xác với naming convention của các property được serialize.

### 3.3. Prefix rỗng

Nếu không khai báo prefix, Jackson dùng chuỗi rỗng. Điều đó có nghĩa tên property của object con được giữ nguyên.

~~~java
@JsonUnwrapped
private Address address;
~~~

Cách này phù hợp khi chỉ có một object con và không có xung đột tên. Nếu nhiều object con có các property trùng nhau, nên thêm prefix hoặc chọn một cấu trúc JSON lồng nhau.

## 4. Dùng suffix để đánh dấu nhóm field

Suffix là chuỗi được thêm vào sau tên từng property của object nhúng.

~~~java
public class Invoice {

    @JsonUnwrapped(suffix = "_billing")
    private Address billingAddress;

    @JsonUnwrapped(suffix = "_shipping")
    private Address shippingAddress;
}
~~~

JSON:

~~~json
{
  "city_billing": "Hanoi",
  "postalCode_billing": "100000",
  "city_shipping": "Da Nang",
  "postalCode_shipping": "550000"
}
~~~

Suffix hữu ích khi hợp đồng đã quy định hậu tố theo nhóm, hoặc tên field cần giữ phần gốc ở đầu để phục vụ tìm kiếm và sắp xếp.

Ví dụ:

| Property con | Suffix | Tên JSON |
|---|---|---|
| city | _billing | city_billing |
| postalCode | _billing | postalCode_billing |
| city | _shipping | city_shipping |
| postalCode | _shipping | postalCode_shipping |

Suffix không có ý nghĩa đặc biệt về kiểu dữ liệu. Nó chỉ là phần chuỗi được thêm vào tên property.

### 4.1. Khi nào prefix dễ đọc hơn suffix?

Prefix thường giúp nhóm field theo vai trò khi xem payload:

~~~text
billing_city
billing_postalCode
shipping_city
shipping_postalCode
~~~

Suffix giữ tên field ở đầu:

~~~text
city_billing
postalCode_billing
city_shipping
postalCode_shipping
~~~

Cả hai đều hợp lệ. Chọn theo quy ước của hệ thống tích hợp và khả năng đọc của consumer. Không cần dùng cả prefix và suffix nếu một phần là đủ để tránh xung đột.

## 5. Kết hợp prefix và suffix

@JsonUnwrapped cho phép khai báo đồng thời prefix và suffix:

~~~java
public class Invoice {

    @JsonUnwrapped(
        prefix = "billing_",
        suffix = "_address"
    )
    private Address billingAddress;
}
~~~

Tên property được biến đổi theo dạng:

~~~text
prefix + tên property + suffix
~~~

Ví dụ:

| Tên property trong Address | Prefix | Suffix | Tên JSON |
|---|---|---|---|
| city | billing_ | _address | billing_city_address |
| postalCode | billing_ | _address | billing_postalCode_address |

JSON:

~~~json
{
  "billing_city_address": "Hanoi",
  "billing_postalCode_address": "100000"
}
~~~

Kết hợp hai phần hữu ích khi chỉ prefix hoặc suffix vẫn có nguy cơ trùng với property khác. Tuy nhiên, tên quá dài làm payload khó đọc và khó dùng. Hãy chỉ kết hợp khi hợp đồng có nhu cầu cụ thể.

## 6. Ví dụ đầy đủ với hai địa chỉ

Mô hình:

~~~java
public class Address {

    private String street;
    private String city;
    private String postalCode;

    public Address() {
    }

    public Address(String street, String city, String postalCode) {
        this.street = street;
        this.city = city;
        this.postalCode = postalCode;
    }

    public String getStreet() {
        return street;
    }

    public void setStreet(String street) {
        this.street = street;
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }

    public String getPostalCode() {
        return postalCode;
    }

    public void setPostalCode(String postalCode) {
        this.postalCode = postalCode;
    }
}
~~~

DTO cha:

~~~java
public class InvoiceResponse {

    private String invoiceId;

    @JsonUnwrapped(prefix = "billing_")
    private Address billingAddress;

    @JsonUnwrapped(prefix = "shipping_")
    private Address shippingAddress;

    public InvoiceResponse() {
    }

    // Getters and setters
}
~~~

Tạo dữ liệu:

~~~java
InvoiceResponse response = new InvoiceResponse();
response.setInvoiceId("INV-100");
response.setBillingAddress(
    new Address("1 Main Street", "Hanoi", "100000")
);
response.setShippingAddress(
    new Address("9 River Road", "Da Nang", "550000")
);
~~~

Serialize:

~~~java
String json = mapper.writeValueAsString(response);
~~~

JSON:

~~~json
{
  "invoiceId": "INV-100",
  "billing_street": "1 Main Street",
  "billing_city": "Hanoi",
  "billing_postalCode": "100000",
  "shipping_street": "9 River Road",
  "shipping_city": "Da Nang",
  "shipping_postalCode": "550000"
}
~~~

Deserialize:

~~~java
InvoiceResponse restored =
    mapper.readValue(json, InvoiceResponse.class);

assertEquals(
    "Hanoi",
    restored.getBillingAddress().getCity()
);

assertEquals(
    "Da Nang",
    restored.getShippingAddress().getCity()
);
~~~

Jackson loại bỏ prefix khi tìm property của object con. billing_city được ánh xạ về city trong billingAddress; shipping_city được ánh xạ về city trong shippingAddress.

## 7. Tên property sau khi áp dụng naming strategy

Một ứng dụng có thể cấu hình PropertyNamingStrategy hoặc PropertyNamingStrategies để đổi tên Java property khi serialize.

Ví dụ Java field postalCode có thể được ghi thành postal_code theo snake_case. Khi kết hợp với @JsonUnwrapped, cần xác nhận tên cuối cùng mà Jackson phát ra và tên mà deserializer mong đợi.

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
    .build();
~~~

Với prefix:

~~~java
@JsonUnwrapped(prefix = "billing_")
private Address billingAddress;
~~~

Tên JSON cuối cùng phụ thuộc vào cách property name được chuẩn hóa và name transformer được áp dụng trong phiên bản/cấu hình Jackson đang dùng. Không nên đoán bằng cách nối chuỗi thủ công trong code nghiệp vụ.

Hãy viết test output literal để xác nhận:

- Prefix có giữ đúng casing và dấu phân cách không.
- Tên property con có được chuyển sang snake_case không.
- Deserialization có nhận đúng các tên đó không.
- @JsonProperty trên property con có ảnh hưởng đến tên cuối cùng như mong đợi không.

Nếu hợp đồng cần tên cố định bất kể global naming strategy, có thể khai báo tên property tường minh bằng @JsonProperty trên member con và kiểm thử kết quả kết hợp.

## 8. Kết hợp với @JsonProperty

@JsonProperty đặt tên JSON cho property riêng lẻ. @JsonUnwrapped prefix/suffix biến đổi tên các property của object nhúng.

Ví dụ:

~~~java
public class Address {

    @JsonProperty("postal_code")
    private String postalCode;

    private String city;
}
~~~

~~~java
public class Invoice {

    @JsonUnwrapped(prefix = "billing_")
    private Address billingAddress;
}
~~~

Hợp đồng mong muốn có thể chứa:

~~~json
{
  "billing_postal_code": "100000",
  "billing_city": "Hanoi"
}
~~~

Hãy kiểm tra kết quả thực tế vì tên cuối cùng được hình thành từ tên property Jackson nhìn thấy và name transformer của unwrapped property. Không viết logic phía service để tự ghép tên field; hãy để Jackson thực hiện transformation và khóa hành vi bằng test.

@JsonProperty vẫn hữu ích để đặt tên ổn định cho property con khi Java field được đổi tên. Prefix/suffix chỉ thêm namespace theo vị trí nhúng.

## 9. Nhúng nhiều object con trong cùng một DTO

Một DTO có thể chứa nhiều nhóm thông tin:

~~~java
public class CustomerExport {

    private String customerId;

    @JsonUnwrapped(prefix = "profile_")
    private Profile profile;

    @JsonUnwrapped(prefix = "contact_")
    private ContactInfo contactInfo;

    @JsonUnwrapped(prefix = "audit_")
    private AuditInfo auditInfo;
}
~~~

JSON có thể có dạng:

~~~json
{
  "customerId": "C-100",
  "profile_displayName": "An Nguyen",
  "profile_birthDate": "1995-01-10",
  "contact_email": "an@example.com",
  "contact_phone": "0900000000",
  "audit_createdBy": "system",
  "audit_createdAt": "2026-11-12T08:00:00Z"
}
~~~

Mỗi nhóm có prefix riêng nên field không xung đột. Cấu trúc Java vẫn thể hiện các nhóm domain tách biệt.

Tuy nhiên, càng nhiều nhóm được làm phẳng, JSON càng khó đọc và dễ có tên dài. Nếu payload có nhiều cấu trúc phức tạp, object lồng nhau thường dễ bảo trì hơn.

## 10. Nhúng nhiều cấp

Có thể một object con lại chứa object khác. Nếu cả hai cấp đều dùng @JsonUnwrapped, tên property có thể nhận nhiều transformation.

Ví dụ:

~~~java
public class ContactInfo {

    private String email;

    @JsonUnwrapped(prefix = "emergency_")
    private EmergencyContact emergencyContact;
}
~~~

~~~java
public class CustomerExport {

    @JsonUnwrapped(prefix = "contact_")
    private ContactInfo contactInfo;
}
~~~

Về ý tưởng, tên của property nhúng sâu có thể kết hợp namespace của từng cấp, chẳng hạn:

~~~text
contact_email
contact_emergency_name
contact_emergency_phone
~~~

Nhúng nhiều cấp làm hợp đồng khó theo dõi và có thể gặp giới hạn theo loại serializer/deserializer hoặc cách Jackson xử lý unwrapping lồng nhau. Không nên giả định mọi tổ hợp đều hoạt động giống nhau giữa các phiên bản.

Nếu cần nested unwrapped, hãy tạo test cho đúng DTO, annotation, naming strategy và version Jackson. Với cấu trúc sâu, cân nhắc giữ một cấp object lồng nhau để schema dễ hiểu hơn.

## 11. Tránh xung đột với property ở object cha

Prefix/suffix cần được thiết kế không chỉ để tránh xung đột giữa các object con mà còn tránh property của object cha.

Ví dụ:

~~~java
public class Invoice {

    private String billing_city;

    @JsonUnwrapped(prefix = "billing_")
    private Address billingAddress;
}
~~~

Nếu Address cũng có property city, cả hai cùng có thể tạo key billing_city.

Một schema tốt cần bảo đảm tên sau transformation là duy nhất trong toàn bộ JSON object:

~~~text
parent property names
        +
first unwrapped property's transformed names
        +
second unwrapped property's transformed names
        +
other unwrapped properties
        =
unique JSON property names
~~~

Hãy lập danh sách tên JSON cuối cùng khi thiết kế DTO. Nếu có collision, đổi prefix/suffix hoặc giữ một nhóm ở dạng nested object.

Không nên dựa vào thứ tự serialization để giải quyết duplicate key. JSON consumer không nên phải đoán giá trị nào thắng.

## 12. Null và object nhúng rỗng

Khi một property được unwrapped, wrapper property không còn tên riêng trong JSON. Điều này có ảnh hưởng đến cách biểu diễn null và object rỗng.

Ví dụ:

~~~java
public class UserResponse {

    @JsonUnwrapped(prefix = "contact_")
    private ContactInfo contactInfo;
}
~~~

Nếu contactInfo là null, không có các field contact_email hoặc contact_phone để ghi. Payload có thể trông giống trường hợp contactInfo bị thiếu hoàn toàn.

Nếu ContactInfo tồn tại nhưng mọi property đều null hoặc bị bỏ qua bởi inclusion rule, kết quả cũng có thể không có field contact_ nào.

Vì vậy, flat representation thường không thể phân biệt rõ các trạng thái:

- Object con bị null.
- Object con không được cung cấp.
- Object con tồn tại nhưng rỗng.
- Các property con đều bị loại khỏi output do @JsonInclude.

Nếu hợp đồng cần phân biệt các trạng thái này, hãy giữ wrapper property hoặc thêm một marker rõ ràng như contact_present. Marker cần có semantics cụ thể và được xử lý nhất quán ở chiều đọc.

Đừng thêm marker chỉ để bù cho một cấu trúc phẳng khó hiểu nếu giữ object lồng nhau đơn giản hơn.

## 13. Deserialization và việc tạo object con

Khi đọc JSON phẳng, Jackson phải gom các field có prefix/suffix vào property tương ứng.

Ví dụ:

~~~json
{
  "invoiceId": "INV-100",
  "billing_city": "Hanoi",
  "billing_postalCode": "100000"
}
~~~

Jackson cần tạo Address cho billingAddress rồi bind:

- billing_city → Address.city.
- billing_postalCode → Address.postalCode.

Điều này hoạt động tốt nhất khi kiểu nhúng là POJO có cơ chế tạo object mà Jackson hỗ trợ, chẳng hạn constructor mặc định và setter/field binding.

Nếu Address là immutable class chỉ có constructor nhiều tham số, record hoặc builder, cần xác minh hỗ trợ unwrapped creator/deserialization trong phiên bản Jackson đang dùng. Các trường hợp property-based creator có thể có ràng buộc khác với POJO mutable. Hãy test constructor thực tế; nếu binding không phù hợp, có thể dùng DTO trung gian hoặc custom deserializer.

### 13.1. Unknown property

Nếu JSON chứa billing_region nhưng Address không có property region, hành vi phụ thuộc cấu hình unknown property và các annotation liên quan.

Với FAIL_ON_UNKNOWN_PROPERTIES bật, Jackson có thể báo lỗi nếu field không được nhận diện. Khi dùng @JsonUnwrapped, cần kiểm thử chính xác field lạ được phân loại và xử lý như thế nào trong hierarchy.

Không nên tắt FAIL_ON_UNKNOWN_PROPERTIES toàn cục chỉ để bỏ qua một field không mong đợi. Nếu hợp đồng cho phép extension field, hãy quy định rõ cách lưu hoặc bỏ qua chúng.

### 13.2. Field thiếu trong object con

Nếu JSON chỉ có billing_city mà không có billing_postalCode, property còn thiếu sẽ tuân theo cách tạo Address và default Java của nó.

Ví dụ Address có postalCode initializer, constructor hoặc validation riêng. Đừng giả định unwrapped binding tự tạo default nghiệp vụ. Hãy thiết kế default trong model hoặc tầng mapping và test payload thiếu field.

## 14. Giới hạn của @JsonUnwrapped

@JsonUnwrapped được thiết kế cho POJO. Không nên áp dụng trực tiếp như một cách làm phẳng tùy ý cho mọi kiểu dữ liệu.

Các giới hạn quan trọng:

- Không phù hợp với array, List, Set hoặc các collection khác.
- Không phải cơ chế để flatten Map key/value tùy ý.
- Không dùng để biến JsonNode tree thành một tập property theo ý muốn.
- Không tương thích với mọi cách xử lý polymorphic type metadata như @JsonTypeInfo.
- Không tự giải quyết collision giữa tên property.
- Không tự bảo toàn sự phân biệt giữa null wrapper và wrapper bị thiếu.
- Có thể gặp giới hạn khi kết hợp creator, builder, immutable object hoặc nested unwrapping tùy phiên bản.

Nếu cần làm phẳng collection, Map hoặc cấu trúc polymorphic, hãy cân nhắc DTO trung gian, custom serializer/deserializer hoặc thiết kế schema khác. Đừng cố ép @JsonUnwrapped làm việc ngoài phạm vi mà nó hỗ trợ.

## 15. Khi nào giữ object lồng nhau tốt hơn?

Làm phẳng không phải lúc nào cũng là lựa chọn tốt. JSON lồng nhau có một số lợi ích:

~~~json
{
  "invoiceId": "INV-100",
  "billingAddress": {
    "city": "Hanoi",
    "postalCode": "100000"
  },
  "shippingAddress": {
    "city": "Da Nang",
    "postalCode": "550000"
  }
}
~~~

Cấu trúc này:

- Giữ namespace tự nhiên.
- Tránh prefix/suffix dài.
- Dễ biểu diễn object null hoặc rỗng.
- Dễ mở rộng object con với field mới.
- Dễ dùng schema và validation theo nhóm.
- Hạn chế xung đột tên.

Flat representation có thể phù hợp khi:

- Hệ thống đích yêu cầu một object phẳng.
- Tích hợp với format cũ hoặc schema bên ngoài cố định.
- Consumer cần truy cập field trực tiếp ở cấp root.
- Object con chỉ là nhóm field mang tính tổ chức, không phải resource độc lập.

Nếu không có ràng buộc hợp đồng, giữ cấu trúc lồng nhau thường là thiết kế rõ ràng hơn.

## 16. Alternative: DTO phẳng và mapping thủ công

Nếu API yêu cầu field phẳng nhưng domain model cần cấu trúc lồng nhau, có thể dùng hai DTO riêng:

~~~java
public record Address(
    String city,
    String postalCode
) {}

public record Invoice(
    String invoiceId,
    Address billingAddress,
    Address shippingAddress
) {}

public record InvoiceFlatResponse(
    String invoiceId,
    String billing_city,
    String billing_postalCode,
    String shipping_city,
    String shipping_postalCode
) {}
~~~

Service mapper chuyển từ domain DTO sang response DTO:

~~~java
InvoiceFlatResponse toFlat(Invoice invoice) {
    return new InvoiceFlatResponse(
        invoice.invoiceId(),
        invoice.billingAddress().city(),
        invoice.billingAddress().postalCode(),
        invoice.shippingAddress().city(),
        invoice.shippingAddress().postalCode()
    );
}
~~~

Ưu điểm:

- Hợp đồng flat hiển thị rõ ngay trong kiểu response.
- Không phụ thuộc vào unwrapping behavior.
- Dễ validate và versioning.
- Có thể kiểm soát null và default một cách tường minh.

Nhược điểm là có thêm mapping code và các field phẳng có thể lặp lại giữa DTO.

Hãy chọn @JsonUnwrapped khi việc làm phẳng là một quy tắc biểu diễn đơn giản của property. Chọn DTO riêng khi cấu trúc API khác đáng kể so với domain model hoặc cần kiểm soát nhiều logic chuyển đổi.

## 17. Alternative: custom serializer/deserializer

Khi quy tắc flatten phức tạp, custom serializer có thể ghi các field theo ý muốn:

~~~java
public class InvoiceSerializer extends StdSerializer<Invoice> {

    public InvoiceSerializer() {
        super(Invoice.class);
    }

    @Override
    public void serialize(
        Invoice value,
        JsonGenerator generator,
        SerializerProvider provider
    ) throws IOException {

        generator.writeStartObject();
        generator.writeStringField("invoiceId", value.getInvoiceId());

        if (value.getBillingAddress() != null) {
            generator.writeStringField(
                "billing_city",
                value.getBillingAddress().getCity()
            );
        }

        generator.writeEndObject();
    }
}
~~~

Deserializer tương ứng phải đọc các field phẳng và tạo lại object con. Cách này linh hoạt nhưng cần tự xử lý:

- Field missing và null.
- Kiểu dữ liệu sai.
- Unknown property.
- Collision và duplicate key.
- Constructor/default của object con.
- Schema version và backward compatibility.

Không nên viết custom serializer/deserializer nếu @JsonUnwrapped đã đáp ứng đầy đủ yêu cầu. Custom code làm tăng trách nhiệm bảo trì và kiểm thử.

## 18. Kết hợp với @JsonInclude

@JsonInclude quyết định khi nào property được đưa vào JSON, còn @JsonUnwrapped quyết định property con được biểu diễn ở cấp nào.

Ví dụ:

~~~java
public class UserResponse {

    @JsonUnwrapped(prefix = "contact_")
    @JsonInclude(JsonInclude.Include.NON_NULL)
    private ContactInfo contactInfo;
}
~~~

Cần hiểu rằng inclusion có thể được áp dụng ở property wrapper và/hoặc property con theo cách Jackson xử lý serializer. Nếu muốn bỏ từng field null trong ContactInfo, có thể đặt inclusion trên ContactInfo hoặc các property con theo hợp đồng.

Đừng giả định @JsonInclude trên wrapper luôn tạo ra một marker cho object con null. Khi wrapper bị unwrapped, nó không có key riêng để ghi null như một object lồng.

Hãy kiểm thử các trường hợp:

- contactInfo là null.
- contactInfo tồn tại nhưng email null.
- contactInfo tồn tại nhưng mọi field null.
- contactInfo tồn tại với giá trị rỗng.
- Include.ALWAYS, NON_NULL hoặc NON_EMPTY theo cấu hình.

## 19. Kiểm thử prefix/suffix ở cả hai chiều

Một test cần xác nhận tên JSON cuối cùng, không chỉ kiểm tra serializer chạy thành công.

Ví dụ:

~~~java
@Test
void serializesAddressesWithDistinctPrefixes() throws Exception {
    InvoiceResponse invoice = sampleInvoice();

    JsonNode json = mapper.readTree(
        mapper.writeValueAsString(invoice)
    );

    assertEquals("Hanoi", json.path("billing_city").asText());
    assertEquals("Da Nang", json.path("shipping_city").asText());

    assertFalse(json.has("billingAddress"));
    assertFalse(json.has("shippingAddress"));
}
~~~

Test deserialize:

~~~java
@Test
void deserializesPrefixedAddressFields() throws Exception {
    String json = """
        {
          "invoiceId": "INV-100",
          "billing_city": "Hanoi",
          "billing_postalCode": "100000",
          "shipping_city": "Da Nang",
          "shipping_postalCode": "550000"
        }
        """;

    InvoiceResponse invoice =
        mapper.readValue(json, InvoiceResponse.class);

    assertEquals("Hanoi", invoice.getBillingAddress().getCity());
    assertEquals("Da Nang", invoice.getShippingAddress().getCity());
}
~~~

### 19.1. Test suffix và prefix kết hợp

Nếu hợp đồng dùng cả hai:

~~~java
@JsonUnwrapped(prefix = "billing_", suffix = "_address")
private Address billingAddress;
~~~

Hãy assert đúng tên như billing_city_address. Test nên kiểm tra cả việc deserialize từ chính các tên đó.

### 19.2. Test collision

Tạo DTO có property cha và property con có thể tạo cùng tên. Xác nhận schema đã chọn không sinh duplicate key. Nếu có collision, thay đổi prefix/suffix hoặc đổi cấu trúc DTO.

### 19.3. Test null, empty và unknown

Bổ sung test cho:

- Object con null.
- Object con rỗng.
- Field con bị thiếu.
- Field con explicit null.
- Field phẳng không nhận diện.
- Property con có tên được @JsonProperty đổi.
- Naming strategy như SNAKE_CASE.
- Nested unwrapped nếu dự án sử dụng.
- Immutable/creator-based DTO.
- Serialization qua root và khi object được lồng trong một DTO khác.

## 20. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Hai object con tạo key trùng | Làm phẳng nhưng không có namespace | Thêm prefix hoặc suffix |
| Prefix không khớp JSON input | Producer và consumer dùng quy ước tên khác nhau | Khóa tên bằng test contract |
| Dùng @JsonUnwrapped cho List/Map | Annotation không dành cho collection/map | Dùng DTO, custom serializer hoặc schema khác |
| Object con null không thể phân biệt với missing | Wrapper key đã bị bỏ khi flatten | Giữ wrapper hoặc thêm marker có semantics |
| Creator không bind được field phẳng | Cơ chế tạo object không phù hợp với unwrapped property | Test phiên bản, dùng DTO trung gian hoặc custom deserializer |
| Field cha trùng tên field con sau transform | Namespace chưa được thiết kế toàn cục | Đổi prefix/suffix |
| Tên bị đổi ngoài dự kiến | Naming strategy và name transformer cùng tác động | Assert JSON literal với cấu hình mapper thật |
| Unknown property bị lỗi | Field phẳng không khớp property con | Kiểm tra prefix, suffix và policy unknown |
| Payload quá khó đọc | Quá nhiều cấp unwrapped hoặc tên quá dài | Giữ một số object lồng nhau |
| Dùng unwrapped cho polymorphic subtype | Type metadata và flatten không tương thích trong một số cấu hình | Dùng discriminator/object lồng hoặc custom mapping |

## 21. Quy trình thiết kế prefix và suffix

1. Xác định hợp đồng thực sự cần object phẳng hay có thể giữ nested object.
2. Liệt kê các object con sẽ được nhúng.
3. Liệt kê property JSON cuối cùng của từng object con.
4. So sánh tên đó với property của object cha và các object con khác.
5. Chọn prefix hoặc suffix thể hiện vai trò nghiệp vụ.
6. Chỉ kết hợp cả hai khi cần thêm namespace.
7. Kiểm tra tên sau @JsonProperty và naming strategy.
8. Đánh giá trường hợp object con null, empty và field thiếu.
9. Xác nhận kiểu con là POJO phù hợp với @JsonUnwrapped.
10. Kiểm tra creator, builder, polymorphism và collection limitations.
11. Viết test serialize/deserialize với JSON literal.
12. Xem thay đổi prefix/suffix là thay đổi hợp đồng và quản lý version tương ứng.

## 22. Nguyên tắc nên giữ

- Dùng @JsonUnwrapped khi cần đưa property của POJO con lên cùng cấp với object cha.
- Prefix được thêm trước tên property con; suffix được thêm sau tên property con.
- Prefix/suffix tạo namespace, giúp tránh collision giữa nhiều object con.
- Chọn tên theo vai trò nghiệp vụ, không phụ thuộc tên class nội bộ.
- Kiểm tra cả tên property cha và tất cả tên sau transformation.
- Kiểm tra tương tác với @JsonProperty và naming strategy.
- Không dùng @JsonUnwrapped cho List, array, Map hoặc cấu trúc không được hỗ trợ.
- Không giả định null wrapper có thể phân biệt với missing sau khi flatten.
- Giữ nested JSON khi cấu trúc nhóm có ý nghĩa hoặc cần mở rộng độc lập.
- Dùng DTO phẳng hoặc custom serializer khi quy tắc biến đổi vượt quá khả năng của annotation.
- Test cả serialization và deserialization, bao gồm collision, null, empty và unknown field.
- Xem prefix/suffix là một phần schema JSON mà consumer phụ thuộc.

@JsonUnwrapped cùng prefix và suffix giúp giữ mô hình Java có các object con rõ ràng trong khi tạo JSON phẳng theo hợp đồng bên ngoài. Prefix/suffix biến đổi tên property để phân biệt các nhóm field, nhưng không tự giải quyết mọi vấn đề của cấu trúc mở. Hãy thiết kế namespace không trùng, hiểu giới hạn của unwrapping, quyết định rõ semantics của null/empty và kiểm thử hai chiều với đúng cấu hình Jackson của ứng dụng.

