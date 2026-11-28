# Thêm phần tử tùy chọn và kiểm chứng hành vi của client cũ

Trong dịch vụ SOAP theo hướng **contract-first**, một thay đổi tưởng nhỏ — thêm một phần tử mới vào XSD — có thể ảnh hưởng đến nhiều phiên bản client đang chạy. Đặt `minOccurs="0"` không tự bảo đảm mọi client cũ tương thích; ý nghĩa thay đổi phụ thuộc **phần tử được thêm vào request hay response, schema mà từng bên dùng, cách JAXB được generate, parser strict hay không và thời điểm triển khai server/client**.

Bài học thuộc chương **Tương thích hợp đồng** của module `SPRING_WEB_SERVICES`. Module tập trung phát triển SOAP bằng Spring Web Services, thiết kế XSD/WSDL, ánh xạ JAXB, endpoint và client; đồng thời xử lý SOAP Fault, interceptor, XML security, WS-Security, TLS/chứng chỉ và kiểm thử tương thích. Việc thêm trường tùy chọn cần được xem là thay đổi của **hợp đồng giữa nhiều phiên bản producer/consumer**, không chỉ là sửa Java DTO.

**Thông điệp chính:** thêm optional element thường giúp **server mới nhận request cũ** nếu schema mới cho phép thiếu trường; nhưng **client cũ nhận response mới** có thể vẫn thất bại do XSD cũ không biết phần tử đó. Cần chứng minh hành vi bằng client artifacts cũ và wire-level SOAP tests, không suy ra tương thích chỉ từ việc schema mới compile.

Ví dụ hướng tới Java 17+, Spring-WS 4.x, Jakarta XML Binding 3.x/4.x và XSD 1.0. WSDL/XML fragments là minh họa contract-first. Các classes generated, application service và mapper cần được tạo trong dự án thực tế. Không có SPECIAL_NOTE bổ sung cho bài này.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích ý nghĩa `minOccurs`, `maxOccurs`, `nillable`, `default` và `fixed` trong XSD.
2. Phân biệt **element vắng mặt**, **element hiện diện rỗng**, **xsi:nil="true"** và giá trị mặc định do application áp dụng.
3. Đánh giá thay đổi optional element riêng cho **request** và **response**, theo chiều producer/consumer.
4. Hiểu tác động của JAXB generated classes, `null`, primitive/wrapper types, field access, schema validation và thứ tự `xs:sequence`.
5. Cập nhật WSDL/XSD theo contract-first, quản lý namespace/import và published schema versions.
6. Thiết kế default semantics ổn định khi request cũ không gửi trường mới.
7. Rollout server/client theo thứ tự an toàn, có quan sát client cũ và rollback.
8. Kiểm thử bằng schema cũ/mới, generated client cũ, raw SOAP fixtures và SOAP stacks khác nhau.
9. Nhận biết khi additive change không đủ an toàn và cần versioning hoặc extension point.

## 1. Tình huống: thêm preferredDelivery vào SubmitOrder

Giả sử dịch vụ `OrderService` có operation `SubmitOrder`. Contract cũ nhận:

~~~xml
<xs:element name="SubmitOrderRequest">
  <xs:complexType>
    <xs:sequence>
      <xs:element name="requestId" type="xs:string"/>
      <xs:element name="buyerId" type="xs:string"/>
      <xs:element name="items" type="ord:OrderItemList"/>
    </xs:sequence>
  </xs:complexType>
</xs:element>
~~~

Ứng dụng muốn thêm lựa chọn giao hàng `preferredDelivery`:

~~~xml
<xs:element name="SubmitOrderRequest">
  <xs:complexType>
    <xs:sequence>
      <xs:element name="requestId" type="xs:string"/>
      <xs:element name="buyerId" type="xs:string"/>
      <xs:element name="items" type="ord:OrderItemList"/>
      <xs:element name="preferredDelivery"
                  type="ord:DeliveryMethod"
                  minOccurs="0"/>
    </xs:sequence>
  </xs:complexType>
</xs:element>
~~~

Ví dụ thêm phần tử ở cuối sequence và cho phép vắng mặt. Giá trị enum giả định `STANDARD`, `EXPRESS`, `PICKUP`. Thêm ở cuối thường ít xáo trộn hơn thêm giữa `xs:sequence` đang có, nhưng không bảo đảm mọi parser cũ bỏ qua phần tử mới.

### 1.1. Request cũ vẫn hợp lệ theo schema mới

Client phiên bản cũ tiếp tục gửi:

~~~xml
<ord:SubmitOrderRequest xmlns:ord="urn:example:orders:v1">
  <ord:requestId>REQ-1001</ord:requestId>
  <ord:buyerId>BUYER-42</ord:buyerId>
  <ord:items>
    <ord:item>
      <ord:sku>SKU-01</ord:sku>
      <ord:quantity>2</ord:quantity>
    </ord:item>
  </ord:items>
</ord:SubmitOrderRequest>
~~~

Schema mới có `minOccurs="0"` nên `preferredDelivery` có thể vắng mặt; request vẫn hợp lệ theo XSD mới (giả sử các khai báo khác đúng). Server mới phải xác định **ngữ nghĩa khi thiếu trường**: dùng mặc định `STANDARD`, lấy preference từ profile buyer, hay để fulfillment quyết định? Đó là quyết định application contract, không phải tự động được XSD/JAXB giải quyết.

### 1.2. Request mới gửi phần tử mới

~~~xml
<ord:SubmitOrderRequest xmlns:ord="urn:example:orders:v1">
  <ord:requestId>REQ-1002</ord:requestId>
  <ord:buyerId>BUYER-42</ord:buyerId>
  <ord:items>
    <ord:item>
      <ord:sku>SKU-02</ord:sku>
      <ord:quantity>1</ord:quantity>
    </ord:item>
  </ord:items>
  <ord:preferredDelivery>EXPRESS</ord:preferredDelivery>
</ord:SubmitOrderRequest>
~~~

Client mới có thể gửi trường mới khi server đã triển khai hỗ trợ và schema/runtime công bố field này. Nếu client mới gửi `preferredDelivery` tới **server cũ** dùng schema không biết field đó, server strict validation có thể trả SOAP Fault. Vì vậy additive change phải xét cả hai chiều.

### 1.3. Ma trận tương thích sơ bộ

| Producer | Consumer | Payload | Rủi ro thường gặp |
| --- | --- | --- | --- |
| Client cũ | Server mới | Request thiếu field mới | Thường tương thích nếu schema server cho phép thiếu và default semantics rõ |
| Client mới | Server mới | Request có field mới | Tương thích nếu cùng triển khai contract |
| Client mới | Server cũ | Request có field chưa biết | Có thể fail schema validation hoặc strict unmarshal |
| Server mới | Client cũ | Response có field mới | **Có thể fail** nếu client validate bằng XSD cũ |
| Server mới | Client cũ | Response không phát field mới | Thường an toàn hơn; vẫn cần kiểm parser/client |
| Server cũ | Client mới | Response thiếu field mới | Client mới phải thực sự chấp nhận thiếu field |

Đừng gộp backward compatibility thành một câu. Phải hỏi rõ **ai phát payload, ai đọc payload, schema nào được dùng và bên nhận strict validation hay không**.

## 2. XSD: vắng mặt, rỗng và nil là ba trạng thái khác nhau

### 2.1. minOccurs="0" cho phép element vắng mặt

~~~xml
<xs:element name="preferredDelivery"
            type="xs:string"
            minOccurs="0"/>
~~~

`minOccurs="0"` nghĩa là element có thể xuất hiện **0 lần** trong content model; với default `maxOccurs="1"`, nó xuất hiện tối đa một lần. Khi vắng, không có XML node tương ứng trong instance. Đây là trạng thái có ý nghĩa riêng với update/patch-like operations: “không cung cấp field” có thể là “để hệ thống tự chọn”, “giữ giá trị hiện tại” hoặc “dùng default”. Hợp đồng phải quy định cụ thể.

### 2.2. Element hiện diện nhưng rỗng

~~~xml
<ord:preferredDelivery/>
~~~

Element vẫn **có mặt**. Với `xs:string`, nó có giá trị lexical rỗng `""`, không phải element vắng mặt và cũng không phải `nil`. Với enum/simple type không cho chuỗi rỗng, nó có thể vi phạm XSD. Nếu application coi chuỗi rỗng giống vắng mặt, cần normalize có chủ đích; đừng để behavior ngẫu nhiên theo JAXB/parser.

### 2.3. xsi:nil cần nillable="true"

~~~xml
<xs:element name="preferredDelivery"
            type="xs:string"
            minOccurs="0"
            nillable="true"/>
~~~

Instance có thể gửi:

~~~xml
<ord:preferredDelivery
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:nil="true"/>
~~~

`nillable="true"` mới cho phép `xsi:nil="true"` theo XSD. `minOccurs="0"` **không tự cho phép nil**. Một field vừa optional vừa nillable có thể có ba trạng thái:

| XML | Trạng thái |
| --- | --- |
| Không có node | Absent |
| `<preferredDelivery/>` | Present, empty |
| `<preferredDelivery xsi:nil="true"/>` | Present, nil |

Nếu có `xsi:nil="true"`, element không được chứa element/text content không phù hợp. Với enum như DeliveryMethod, chỉ bật nil nếu hợp đồng thực sự cần phân biệt absent và explicit null.

### 2.4. default và fixed không phải application fallback

~~~xml
<xs:element name="preferredDelivery"
            type="xs:string"
            minOccurs="0"
            default="STANDARD"/>
~~~

Cần phân biệt default value của XSD với default do Java service áp dụng. Với **element declaration**, schema default được áp dụng khi element **xuất hiện nhưng không có content**, theo quy tắc schema validation; không nên hiểu đơn giản là “node vắng tự động sinh XML element”. Với attribute default, quy tắc bổ sung attribute khác. Hành vi quan sát qua JAXB còn phụ thuộc schema validation/unmarshal flow và binding provider. Vì vậy nếu nghiệp vụ muốn “client cũ không gửi preferredDelivery thì chọn STANDARD”, hãy triển khai và test fallback ở application boundary tường minh.

`fixed="STANDARD"` ràng buộc giá trị element khi xuất hiện; không phải cơ chế thêm lựa chọn mới và không phù hợp nếu client được phép chọn EXPRESS/PICKUP.

## 3. Vị trí phần tử và thứ tự xs:sequence

### 3.1. Thêm cuối sequence thường ít rủi ro hơn

Contract cũ:

~~~xml
<xs:sequence>
  <xs:element name="requestId" type="xs:string"/>
  <xs:element name="buyerId" type="xs:string"/>
  <xs:element name="items" type="ord:OrderItemList"/>
</xs:sequence>
~~~

Contract mới additive:

~~~xml
<xs:sequence>
  <xs:element name="requestId" type="xs:string"/>
  <xs:element name="buyerId" type="xs:string"/>
  <xs:element name="items" type="ord:OrderItemList"/>
  <xs:element name="preferredDelivery"
              type="ord:DeliveryMethod"
              minOccurs="0"/>
</xs:sequence>
~~~

Với `xs:sequence`, thứ tự child elements trong XML instance phải tuân schema. Thêm field optional **giữa** các element có thể gây khó cho client cũ, nhất là parser/serializer có giả định thứ tự cứng hoặc generated code không được cập nhật. Thêm ở cuối giúp các element cũ giữ vị trí ban đầu, nhưng không bảo đảm mọi consumer bỏ qua phần tử mới.

### 3.2. Không tùy tiện thay xs:sequence bằng xs:all

`xs:all` có quy tắc compositing và giới hạn riêng; đổi compositor có thể thay contract rộng hơn nhiều so với thêm optional element. JAXB binding, XSD processor và đối tác có thể khác về hỗ trợ. Không “sửa thứ tự” bằng cách đổi `sequence` sang `all` trong một patch nhỏ mà chưa xem xét WSDL/client artifacts.

### 3.3. Namespace là một phần của QName

Phần tử có cùng local name nhưng namespace khác là hai QName khác nhau:

~~~xml
<ord:preferredDelivery
    xmlns:ord="urn:example:orders:v1">EXPRESS</ord:preferredDelivery>
~~~

Khác với:

~~~xml
<preferredDelivery xmlns="">EXPRESS</preferredDelivery>
~~~

`elementFormDefault="qualified"` hoặc `unqualified`, prefix mapping và namespace của local element quyết định QName thực. JAXB-generated clients dựa vào QName/namespace. Đừng chỉ kiểm tên `preferredDelivery` bằng text search; hãy kiểm expanded QName `{urn:example:orders:v1}preferredDelivery`.


## 4. JAXB mapping: optional element thành Java field như thế nào?

### 4.1. String/enum thường biểu diễn absent bằng null

Với XJC/JAXB, optional element kiểu `xs:string` thường thành Java reference có thể `null`:

~~~java
@XmlElement(name = "preferredDelivery")
protected String preferredDelivery;

public String getPreferredDelivery() {
    return preferredDelivery;
}

public void setPreferredDelivery(String value) {
    this.preferredDelivery = value;
}
~~~

Đây là fragment đại diện generated JAXB class; tên field/accessors phụ thuộc binding customizations và code generator. Nếu element vắng mặt khi unmarshal, field reference thường vẫn `null`. Với collection/list và wrapper-specific mappings, cách biểu diễn có thể khác; phải kiểm generated source thực tế.

### 4.2. Primitive và wrapper khác nhau

Với XSD numeric optional:

~~~xml
<xs:element name="priority"
            type="xs:int"
            minOccurs="0"/>
~~~

JAXB thường cần wrapper `Integer` để biểu diễn absent khác với số 0. Một customization hoặc generator có thể dùng primitive kèm `isSetPriority()` hoặc presence flag. Nếu Java chỉ có `int priority`, giá trị mặc định 0 **không thể tự nói** XML có gửi element hay không.

| Java representation | Khi absent | Có phân biệt 0 với absent? |
| --- | --- | --- |
| `Integer` | `null` | Có |
| `int` thuần | `0` (default Java) | Không, trừ presence flag |
| `int` + `isSetPriority()` | `0` và presence indicator | Có |
| `JAXBElement<Integer>` | Wrapper null hoặc value null theo binding | Có thể biểu diễn presence/nil rõ hơn |

Không tự sửa generated class bằng tay; thay đổi có thể mất khi chạy XJC lại. Dùng external binding file/customization hoặc mapper ở application layer.

### 4.3. Optional không đồng nghĩa nillable trong JAXB

`minOccurs="0"` cho phép absent. `nillable="true"` cho phép `xsi:nil`. JAXB có thể ánh xạ element thành `JAXBElement<T>` (tùy schema/binding) để biểu diễn:

- Wrapper `null`: element không xuất hiện.
- `JAXBElement` tồn tại nhưng value `null`: element có thể được phát với xsi:nil nếu declaration nillable.
- `JAXBElement` value có dữ liệu: element hiện diện có nội dung.

Một số generated model dùng property đơn giản mà không giữ được tất cả khác biệt absent-vs-nil qua round trip. **Kiểm thử marshal/unmarshal generated classes** nếu distinction này quan trọng cho semantics.

### 4.4. Default ở application boundary, không rải khắp code

Không viết default ở nhiều mapper/controller/service khác nhau:

~~~java
// Không nhất quán: mỗi tầng tự diễn giải absent theo cách riêng.
if (request.getPreferredDelivery() == null) {
    // Một nơi chọn STANDARD...
}
~~~

Thay vào đó tạo một bước chuyển contract DTO thành command nghiệp vụ:

~~~java
public record SubmitOrderCommand(
    String requestId,
    String buyerId,
    List<OrderItemCommand> items,
    DeliveryMethod preferredDelivery) {}

public SubmitOrderCommand toCommand(SubmitOrderRequest request) {
    DeliveryMethod method = request.getPreferredDelivery() == null
        ? DeliveryMethod.STANDARD
        : DeliveryMethod.valueOf(request.getPreferredDelivery());

    return new SubmitOrderCommand(
        request.getRequestId(),
        request.getBuyerId(),
        mapItems(request.getItems()),
        method);
}
~~~

`DeliveryMethod`, `OrderItemCommand` và `mapItems` là application types/method giả định. Ví dụ thể hiện **một điểm duy nhất quyết định default**. Thực tế cần xử lý giá trị unknown/empty có lỗi có kiểm soát; không gọi `valueOf` với input từ wire rồi trả stack trace cho caller.

Với field optional kiểu boolean/number, giữ presence nếu nghiệp vụ phân biệt “không gửi” và “gửi false/0”. Nếu không, application có thể vô tình biến client cũ thành một yêu cầu tường minh giá trị false/zero.

### 4.5. Java initializer không phải schema contract

~~~java
private String preferredDelivery = "STANDARD";
~~~

Field initializer có thể khiến object được khởi tạo thủ công có giá trị STANDARD khi caller không set field. Nhưng JAXB provider có thể khởi tạo/unmarshal theo lifecycle riêng và ghi đè hoặc giữ initializer theo implementation. **Không dựa duy nhất vào Java field initializer** để định nghĩa default wire semantics. Hãy kiểm object sau unmarshal bằng đúng provider trong build.

## 5. WSDL và schema publishing khi thêm element

### 5.1. WSDL thường tham chiếu XSD qua wsdl:types

Contract-first service có thể nhúng schema hoặc import schema:

~~~xml
<wsdl:types>
  <xs:schema targetNamespace="urn:example:orders:v1"
      xmlns:xs="http://www.w3.org/2001/XMLSchema"
      xmlns:ord="urn:example:orders:v1"
      elementFormDefault="qualified">
    <xs:include schemaLocation="orders-types.xsd"/>
  </xs:schema>
</wsdl:types>
~~~

Đây là fragment rút gọn; WSDL thực phải định nghĩa messages, portType, binding, service và endpoint. Khi thêm field vào XSD, phải bảo đảm **WSDL được publish trỏ tới schema mới** và client tải/import được toàn bộ schema dependency. Deployment publish WSDL/XSD từ classpath hoặc endpoint WSDL definition; sửa source XSD nhưng không rebuild/redeploy artifact có thể khiến runtime vẫn phục vụ contract cũ.

### 5.2. Namespace ổn định hay version mới?

Thêm optional field không nhất thiết cần đổi namespace ngay, nhưng lựa chọn phụ thuộc mức thay đổi:

| Loại thay đổi | Hướng xử lý thường gặp |
| --- | --- |
| Thêm optional field cuối sequence, semantics additive | Có thể giữ namespace/version |
| Thêm enum value mới mà client cũ strict enum | Có thể breaking dù field cũ vẫn giữ |
| Đổi meaning của field existing | Breaking semantic change; version contract |
| Đổi type/namespace/order bắt buộc | Thường breaking; cần version |
| Bỏ field/operation | Deprecation rồi version/remove có kế hoạch |
| Thay authentication/policy | Contract/security compatibility riêng |

Không đổi `targetNamespace` vì mỗi field optional đơn giản; điều đó buộc client generate lại bindings và có thể coi mọi QName cũ là contract khác. Nhưng giữ namespace **cũng không chứng minh tương thích**; phải đánh giá schema consumers và semantics.

### 5.3. WSDL URL cần ổn định nhưng artifact phải xác định

Trong Spring-WS, WSDL có thể được publish từ `DefaultWsdl11Definition`/`SimpleWsdl11Definition` và XSD resources; tên endpoint/service/port và schema location thành một phần contract mà codegen consumers sử dụng. Với URL versionless như `/ws/orders.wsdl`, phải bảo đảm nó phục vụ đúng artifact đang chạy và có kiểm soát rollout. Nếu cần duy trì nhiều phiên bản, có thể công bố endpoint/WSDL versioned, ví dụ `/ws/v1/orders.wsdl` và `/ws/v2/orders.wsdl`, hoặc quản lý metadata/version bằng gateway/registry.

### 5.4. WSDL không thay policy tương thích response

Server mới công bố WSDL mới có optional field nghĩa là **client mới** có thể generate code hiểu field đó và biết nó được phép vắng mặt. Client cũ đã generate code từ WSDL/XSD cũ **không tự tải schema mới lúc runtime** để bỏ qua field mới. Một số parser bỏ qua unknown elements; một số validator strict từ chối. Compatibility test phải dùng **binary/generated client artifact cũ** hoặc harness schema cũ, không chỉ generate lại client từ WSDL mới.

## 6. Hai hướng tương thích cần đánh giá riêng

### 6.1. Request: old client → new server

Đây là hướng thường dễ tương thích nhất:

- Client cũ không biết trường mới và không serialize nó.
- Server mới dùng schema có `minOccurs="0"` nên request cũ có thể hợp lệ.
- JAXB property mới absent có biểu diễn null/presence phù hợp.
- Application áp default hoặc giữ behavior cũ khi thiếu field.
- SOAP headers/action/security vẫn tương thích.

Các điều kiện này phải cùng đúng. Nếu application chuyển absent thành EXPRESS, ví dụ, client cũ vẫn parse được XML nhưng **hành vi nghiệp vụ đã đổi**, có thể là semantic breaking change.

### 6.2. Response: new server → old client

Đây là hướng dễ bị đánh giá thiếu:

- Server mới có thể gửi field mới luôn, dù optional trong schema mới.
- Client cũ có thể validate bằng XSD cũ và reject unknown element.
- Generated JAXB code cũ có thể bỏ qua hoặc reject unknown element tùy annotation/event handler/provider.
- SOAP framework hoặc validation interceptor ở client có thể fail trước khi generated object nhận response.
- Enum value mới trong field hiện có cũng có thể khiến client cũ không parse được.

**Optional trong schema producer không có nghĩa optional đối với schema consumer cũ.** Khi cần đảm bảo old clients, server có thể **không phát field mới cho tới khi client được nâng cấp**, hoặc dùng response version/content negotiation/endpoint versioning. XSD mới cho phép element absent chính là điều giúp server chọn chưa gửi.

### 6.3. Forward compatibility và unknown elements

Một số JAXB unmarshallers có thể ignore unknown child elements nếu không validate với schema hoặc không có handler strict. Nhưng không nên dựa vào behavior mặc định như contract guarantee:

- `Unmarshaller` có thể có `ValidationEventHandler` quyết định event không nhận diện.
- Schema validation được bật có thể reject element không có trong schema cũ.
- Parser và codegen khác nhau có behavior khác.
- Custom XML-to-object mapper có thể reject unknown QName.
- Khi old client **marshal** request, nó không tự tạo field mới; đây lại là lợi thế khi server mới cho phép absent.

Đặt test riêng cho cả **schema validation on/off** và JAXB provider/version nếu dự án có các cấu hình đó.

### 6.4. Consumer-driven compatibility matrix

| Schema/runtime consumer | Payload phát ra | Kỳ vọng cần kiểm |
| --- | --- | --- |
| Server mới | Request từ client cũ | Accept absent optional field, default semantics |
| Server mới | Request client mới | Accept field hợp lệ và unknown values có policy |
| Client cũ | Response server mới không có field | Accept như hành vi cũ |
| Client cũ strict XSD | Response có field mới | Có thể reject; phải prove bằng test |
| Client cũ lenient JAXB | Response có field mới | Có thể ignore; không mặc định |
| Client mới | Response từ server cũ thiếu field | Unmarshal thành absent/null và áp default |
| Client mới | Response server mới có field | Map field mới đúng |
| Partner .NET/Java khác provider | Cả hai dạng | Kiểm QName/order/nil/unknown-element thực tế |


## 7. Thiết kế fallback và rollout không đổi semantics của client cũ

### 7.1. Định nghĩa hành vi khi field absent

Trước khi viết code, cần trả lời các câu hỏi trong contract/API documentation:

| Câu hỏi | Ví dụ lựa chọn | Lưu ý tương thích |
| --- | --- | --- |
| Client không gửi trường | Dùng `STANDARD` | Giữ behavior cũ |
| Client gửi `STANDARD` rõ ràng | Thực hiện STANDARD | Có thể tương đương absent nếu contract nói vậy |
| Client gửi empty string | Reject validation | Không âm thầm coi là STANDARD trừ khi quy định |
| Client gửi nil | Không cho phép | `nillable=false` |
| Client gửi enum không biết | Reject Sender/Client Fault | Không fallback tùy tiện sang STANDARD |
| Client không biết feature | Không gửi field mới | Server không bắt buộc trường |
| Client biết feature nhưng chưa enabled | Reject có mã lỗi hoặc ignore theo contract | Tránh silently claim đã áp dụng |

Nếu thiếu trường mới làm thay đổi **business result**, đây là thay đổi semantic dù XML hợp lệ. Ví dụ trước đây server luôn giao STANDARD, bây giờ vắng field lại lấy preference EXPRESS từ buyer profile có thể khiến client cũ thấy kết quả khác mà không hề yêu cầu. Nếu behavior mới cần opt-in, hãy để absence giữ behavior cũ và chỉ áp dụng behavior mới khi field hiện diện, được xác thực và feature được bật.

### 7.2. Explicit mapping contract DTO → command

Một cách đơn giản là chuyển SOAP request thành command đã chuẩn hóa:

~~~java
public SubmitOrderCommand map(SubmitOrderRequest request) {
    String raw = request.getPreferredDelivery();

    DeliveryMethod delivery;
    if (raw == null) {
        delivery = DeliveryMethod.STANDARD; // Legacy behavior
    } else {
        delivery = switch (raw) {
            case "STANDARD" -> DeliveryMethod.STANDARD;
            case "EXPRESS" -> DeliveryMethod.EXPRESS;
            case "PICKUP" -> DeliveryMethod.PICKUP;
            default -> throw new UnsupportedDeliveryMethodException(raw);
        };
    }

    return new SubmitOrderCommand(
        request.getRequestId(),
        request.getBuyerId(),
        mapItems(request.getItems()),
        delivery);
}
~~~

`SubmitOrderRequest`, `SubmitOrderCommand`, `DeliveryMethod`, `mapItems` và exception là application/generated code giả định. Ví dụ thể hiện **một điểm duy nhất quyết định default**. Thực tế cần xử lý giá trị unknown/empty có lỗi có kiểm soát; không gọi `valueOf` với input từ wire rồi trả stack trace cho caller.

Với field optional kiểu boolean/number, giữ presence nếu nghiệp vụ phân biệt “không gửi” và “gửi false/0”. Nếu không, application có thể vô tình biến client cũ thành một yêu cầu tường minh giá trị false/zero.

### 7.3. Đừng trả field mới cho mọi client ngay lập tức

Nếu response field mới có thể phá client cũ:

- Chỉ emit field mới khi caller đã được xác định là phiên bản hỗ trợ field (client registration/capability đã xác minh).
- Giữ response contract v1 và publish operation/endpoint v2 riêng.
- Dùng response extension point đã có trong contract nếu hai phía được thiết kế để hỗ trợ wildcard.
- Chỉ cân nhắc lenient parsing ở consumer sau khi đã review parser behavior; không dùng đó làm giải pháp mù.

Không suy client version từ User-Agent hoặc một field SOAP Body do caller tự khai nếu nó quyết định release capability. Dùng partner registry/API identity đã xác thực hoặc endpoint version rõ.

### 7.4. Triển khai producer trước consumer khi request field mới

Một rollout request-field thường an toàn hơn theo thứ tự:

~~~mermaid
sequenceDiagram
    autonumber
    participant S as SOAP Server
    participant C0 as Client cũ
    participant C1 as Client mới
    S->>S: Deploy schema optional + default giữ behavior cũ
    C0->>S: Request không có preferredDelivery
    S-->>C0: Response v1 tương thích
    C1->>S: Request có preferredDelivery sau khi capability bật
    S-->>C1: Response đã thỏa contract
~~~

Server phải deploy và kiểm chứng trước khi client mới gửi field. Nếu server cũ strict XSD, client mới gửi field trước có thể bị reject. Feature flag có thể ngăn client mới gửi trường cho tới khi server/capability sẵn sàng.

### 7.5. Rollout response field mới là quyết định khác

Nếu server muốn gửi response field mới:

1. Kiểm kê clients/partners đang gọi operation và versions/schema artifacts của họ.
2. Test với **client binary cũ** để quan sát unknown-element behavior.
3. Nếu client cũ reject, publish v2 hoặc gate response field theo capability đã xác thực.
4. Deploy client mới và cho chúng opt-in nhận field.
5. Chỉ khi client cũ đã drain/được chứng minh lenient, mới cân nhắc phát rộng field.
6. Giữ rollback path có thể tắt response field mới mà không làm sai dữ liệu đã commit.

Optional response element có thể an toàn nếu consumer cũ có wildcard/lenient parser, nhưng đó là **behavior đã được đo và cam kết**, không tự động từ schema mới.

## 8. Extension point và lựa chọn versioning

### 8.1. xs:any chỉ hữu ích nếu contract đã thiết kế extension

XSD có thể khai báo vùng mở rộng:

~~~xml
<xs:complexType name="SubmitOrderRequestType">
  <xs:sequence>
    <xs:element name="requestId" type="xs:string"/>
    <xs:element name="buyerId" type="xs:string"/>
    <xs:element name="items" type="ord:OrderItemList"/>
    <xs:any namespace="##other"
             minOccurs="0"
             maxOccurs="unbounded"
             processContents="lax"/>
  </xs:sequence>
</xs:complexType>
~~~

`xs:any namespace="##other"` cho phép element từ namespace khác theo wildcard namespace constraint; `processContents="lax"` có thể validate nếu schema declaration tìm thấy, nếu không thì không bắt buộc strict validation. **Đây là extension point cần có ngay trong version đầu**, không thể thêm wildcard vào schema cũ rồi giả định client đã biết để chấp nhận. JAXB generators có thể ánh xạ wildcard thành `List<Object>`/`@XmlAnyElement`; cần test.

Không dùng `xs:any processContents="skip"` để né validation cho dữ liệu không tin cậy. Wildcard mở rộng surface area; cần namespace allowlist, size limits, parser safety và authorization rõ.

### 8.2. Versioning theo namespace hoặc endpoint

Ví dụ v1 và v2:

~~~text
v1 namespace: urn:example:orders:v1
v2 namespace: urn:example:orders:v2

WSDL:
  /ws/v1/orders.wsdl
  /ws/v2/orders.wsdl

SOAP operation QName:
  {urn:example:orders:v1}SubmitOrderRequest
  {urn:example:orders:v2}SubmitOrderRequest
~~~

Hai phiên bản có thể dùng chung business service phía trong qua mappers khác nhau. Contract v1 giữ behavior cũ; v2 mang semantics mới. Versioning tăng chi phí maintain/test, nhưng rõ ràng hơn khi thay đổi ảnh hưởng type, thứ tự, security policy hoặc business meaning.

### 8.3. Namespace và schemaLocation là hai thông tin riêng

- `targetNamespace` tạo QName cho schema components.
- `schemaLocation` chỉ vị trí resolver tìm schema resource được include/import.
- Đổi URL schema file không tự đổi QName.
- Đổi namespace làm QName thay đổi, generated clients cần binding mới.
- Có thể phục vụ schema từ URL mới với cùng namespace khi contract không đổi QName, nhưng phải giữ artifact ổn định và tránh versionless URL trả nội dung khác bất ngờ.

Không dùng `xsi:schemaLocation` do SOAP caller tự gửi làm nguồn trust để tải XSD/network resources. Server dùng schema local/trusted và parser policy.

## 9. Kiểm thử contract bằng schema và client cũ

### 9.1. Bốn fixture tối thiểu

Duy trì các file XML version-control:

| Fixture | Mục đích |
| --- | --- |
| `submit-order-v1-request.xml` | Request client cũ, không có preferredDelivery |
| `submit-order-v2-request.xml` | Request mới có preferredDelivery |
| `submit-order-v1-response.xml` | Response cũ không có trường mới |
| `submit-order-v2-response.xml` | Response mới có trường mới |

Golden fixture nên gồm **toàn bộ SOAP Envelope/Header/Body**, không chỉ payload root, khi compatibility phụ thuộc SOAPAction, WS-Addressing, security, namespaces hoặc SOAP 1.1/1.2. Che credential/X.509 test material/PII; fixture không chứa token thật.

### 9.2. Validate theo cả schema cũ và mới

Trong CI, giữ cả `orders-v1.xsd` và `orders-v2.xsd` hoặc artifacts schema immutable đã publish. Chạy các cặp:

- Request cũ → schema mới: **phải pass** nếu đây là mục tiêu.
- Request mới → schema mới: pass.
- Request mới → schema cũ: ghi rõ **có thể fail** nếu element chưa biết; test chứng minh gate/version strategy.
- Response cũ → client mới/schema mới: pass nếu new client thiết kế optional.
- Response mới → client cũ/schema cũ: **phải test thật**, không giả định pass.
- Response mới nhưng không phát field → client cũ: thường cần pass nếu XML cũ giữ nguyên.

Ví dụ XSD validator Java:

~~~java
import java.io.InputStream;
import javax.xml.XMLConstants;
import javax.xml.validation.SchemaFactory;
import javax.xml.transform.stream.StreamSource;

SchemaFactory factory =
    SchemaFactory.newInstance(XMLConstants.W3C_XML_SCHEMA_NS_URI);

// Chặn external access; cung cấp XSD từ trusted local resources.
factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
factory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

var schema = factory.newSchema(localSchemaFile);
var validator = schema.newValidator();

try (InputStream xml = getClass().getResourceAsStream(
        "/fixtures/submit-order-v1-request.xml")) {
    validator.validate(new StreamSource(xml));
}
~~~

`localSchemaFile` cần là File/Source đã provision; `getResourceAsStream` cần kiểm null và lỗi I/O. Đoạn này minh họa validator dùng **trusted local XSD**, không tải schema từ URL trong XML input. Project code cần resource path và error assertions thực tế.


### 9.3. Dùng generated client cũ, không regenerate trong test

Một lỗi CI phổ biến là mỗi lần build đều generate JAXB classes từ **WSDL mới**, sau đó dùng classes mới để test response mới. Như vậy không kiểm tra client cũ. Cần giữ artifact contract/client cũ, ví dụ:

~~~text
compatibility-tests/
  old-client/
    generated-sources/        # JAXB classes từ WSDL v1 đã release
    schema/orders-v1.xsd
  new-server/
    schema/orders-v2.xsd
    endpoint-under-test/
  fixtures/
    old-request.xml
    new-request.xml
    old-response.xml
    response-with-new-element.xml
~~~

Trong pipeline, compile module `old-client` từ generated sources đã phát hành hoặc dependency artifact version bất biến. Đừng chạy XJC trên WSDL mới trong module đó. Sau đó cho **client cũ thực sự** nhận response do server mới tạo qua serializer/HTTP SOAP stack, với schema validation đúng như production.

### 9.4. Test XSD cũ từ chối unknown element là tín hiệu cần quản trị

Một validation test tối thiểu:

~~~java
@Test
void oldSchemaRejectsResponseWithNewElement() throws Exception {
    var validator = oldSchema.newValidator();

    try (var xml = resource("/fixtures/response-with-new-element.xml")) {
        assertThrows(SAXException.class,
            () -> validator.validate(new StreamSource(xml)));
    }
}
~~~

Ví dụ kỳ vọng reject chỉ đúng khi old XSD không khai báo element mới và fixture đặt element ở vị trí schema strict. Dùng test này để **chứng minh cần response gating/version**, không phải xem reject là lỗi của old client. Nếu old client production không bật XSD validation và JAXB parser bỏ qua unknown field, cần kiểm bằng runtime/artifact đó.

### 9.5. Test client mới xử lý response cũ thiếu field

Nếu XSD mới khai báo field optional, client mới nên đọc response cũ:

~~~java
SubmitOrderResponseV2 response =
    unmarshaller.unmarshal(oldResponseSource,
                           SubmitOrderResponseV2.class)
        .getValue();

assertNull(response.getEstimatedDeliveryDate());
assertEquals(
    DeliveryMethod.STANDARD,
    responseMapper.toResult(response).preferredDelivery());
~~~

`SubmitOrderResponseV2`, mapper và factories là generated/application types giả định; nếu JAXB result là `JAXBElement` khác thì điều chỉnh theo generated API. Assertion default nên ở application mapper, còn JAXB DTO phản ánh đúng absent state nếu schema/binding không áp schema defaults.

### 9.6. Test Spring-WS server nhận request cũ

Có thể dùng `MockWebServiceClient` để gửi payload Body tới dispatcher trong application context:

~~~java
MockWebServiceClient client =
    MockWebServiceClient.createClient(applicationContext);

Source request = new StringSource("""
    <ord:SubmitOrderRequest xmlns:ord="urn:example:orders:v1">
      <ord:requestId>REQ-1001</ord:requestId>
      <ord:buyerId>BUYER-42</ord:buyerId>
      <ord:items/>
    </ord:SubmitOrderRequest>
    """);

client.sendRequest(withPayload(request))
      .andExpect(noFault());
~~~

Đây là skeleton cần imports và context có endpoint/marshaller/resolvers. Nếu production dùng `PayloadValidatingInterceptor`, bảo đảm test config cũng đăng ký XSD mới; `MockWebServiceClient` không tự xác minh HTTP Servlet Security, SOAP transport headers hay partner WS-Security chỉ vì payload đã tới dispatcher.

### 9.7. Test wire response với old client trên HTTP thật

Đối với response backward compatibility, ưu tiên integration test:

~~~mermaid
sequenceDiagram
    participant T as Compatibility test
    participant S as Spring-WS server mới
    participant C as Generated client v1 cũ
    T->>S: SubmitOrder request hợp lệ
    S-->>T: SOAP response từ server mới
    T->>C: Chuyển đúng bytes response v1/v2
    C->>C: XSD v1 validation + JAXB v1 unmarshal
    alt Response không có field mới
        C-->>T: Pass
    else Response có field mới
        C-->>T: Pass hoặc fail theo parser thực tế
    end
~~~

Dùng response **đúng serializer/message factory production** ít nhất một lần. Một test “unmarshal bằng JAXB v1 không bật schema validation” chỉ trả lời hành vi parser đó, không chứng minh SOAP client production có cùng behavior.

## 10. Contract compatibility trong Spring-WS configuration

### 10.1. Publish XSD mới từ artifact đúng

Ví dụ config contract-first rút gọn:

~~~java
@EnableWs
@Configuration
public class SoapContractConfig extends WsConfigurerAdapter {

    @Bean
    XsdSchema ordersSchema() {
        return new SimpleXsdSchema(
            new ClassPathResource("xsd/orders-v2.xsd"));
    }

    @Bean(name = "orders")
    DefaultWsdl11Definition ordersWsdl(XsdSchema ordersSchema) {
        var wsdl = new DefaultWsdl11Definition();
        wsdl.setPortTypeName("OrdersPort");
        wsdl.setLocationUri("/ws");
        wsdl.setTargetNamespace("urn:example:orders:v1");
        wsdl.setSchema(ordersSchema);
        return wsdl;
    }
}
~~~

Đây là config rút gọn theo kiểu Spring-WS legacy. `WsConfigurerAdapter` có thể deprecated/đổi cách khuyến nghị theo version; với code mới, dùng configuration API tương thích dependency đang dùng (ví dụ implement `WsConfigurer` nếu có). Kiểm endpoint thực sự publish `orders.wsdl` với schema `orders-v2.xsd`; không chỉ assert bean tồn tại.

Ví dụ giữ `targetNamespace` v1 khi additive field còn backward-compatible cho consumer đã kiểm chứng. Nếu cần contract v2, namespace nên đổi đồng bộ theo request/response types, QName, WSDL messages, marshaller context và endpoint mapping; đừng đổi mỗi tên file XSD.

### 10.2. Endpoint DTO không tự quyết response version

Một endpoint có thể trả JAXB response DTO:

~~~java
@Endpoint
public class OrdersEndpoint {

    private final OrderService service;

    public OrdersEndpoint(OrderService service) {
        this.service = service;
    }

    @PayloadRoot(
        namespace = "urn:example:orders:v1",
        localPart = "SubmitOrderRequest")
    @ResponsePayload
    public SubmitOrderResponse submit(
            @RequestPayload SubmitOrderRequest request) {
        var command = requestMapper.toCommand(request);
        var result = service.submit(command);
        return responseMapper.toV1Response(result);
    }
}
~~~

Generated DTO/mapper/service là types giả định. Một lựa chọn an toàn là `toV1Response` **không phát field mới** cho contract v1, dù domain result đã có estimated delivery. Endpoint v2 dùng mapper riêng hoặc capability policy xác minh để emit field. Không để Java response DTO shared giữa versions tự marshal mọi field chỉ vì JAXB annotation có mặt.

### 10.3. Schema validation trên server

`PayloadValidatingInterceptor` có thể validate request và/hoặc response theo schema. Khi thêm field optional:

- Server-side request validator dùng schema mới để chấp nhận client cũ thiếu trường.
- Response validator dùng schema tương ứng với **response contract thực sự phát**.
- Nếu server phục vụ v1 và v2, đừng validate mọi response theo cùng một XSD bất kể operation/endpoint version.
- Validator nên fail trong CI khi response mapper phát field sai order/namespace/type.
- Security parser settings vẫn phải chặn external schema/DTD, không tải schema tự do từ payload.

### 10.4. WSDL import/include phải được đóng gói nhất quán

`xs:include` và `xs:import` có quy tắc targetNamespace khác nhau; khi module dùng nhiều schema, kiểm tất cả referenced resources được publish/có thể resolve. WSDL trả 200 nhưng import trỏ path 404 là contract deployment bị lỗi. Golden test có thể fetch WSDL rồi resolve mọi `schemaLocation`/`wsdl:import` từ trusted server, assert tất cả có version/hash mong muốn.

## 11. Tự động phát hiện contract drift

### 11.1. Diff XSD/WSDL như API surface

Diff văn bản thường báo quá nhiều thay đổi format và bỏ qua semantics; cần schema-aware diff hoặc ruleset review. Ví dụ checklist cho CI:

| Change | Mức rủi ro thường gặp | Gợi ý gate |
| --- | --- | --- |
| Thêm optional element cuối sequence | Có thể backward-compatible theo hướng nhận request | Pass sau tests hai chiều |
| Thêm required element | Breaking cho old producers | Fail |
| Đổi `minOccurs=0` thành 1 | Breaking | Fail |
| Đổi type `xs:string` sang numeric/date | Breaking | Fail |
| Giảm maxLength/numeric range | Có thể reject payload hợp lệ cũ | Fail/manual review |
| Thêm enum value | Có thể break strict generated consumers | Manual/compat test |
| Bỏ element/operation | Breaking | Fail/version |
| Đổi namespace/QName | Breaking | Fail/version |
| Thêm response optional element | Rủi ro với old strict consumers | Require old-client proof/gating |
| Đổi SOAPAction/WS-Addressing Action | Có thể route sai | Fail nếu chưa version/test |
| Đổi fault detail/type | Client exception mapping có thể vỡ | Require fault contract tests |
| Đổi WS-SecurityPolicy | Có thể mất interop/security | Security review + partner test |

### 11.2. Build manifest của contract

Có thể lưu manifest trong release pipeline (bên ngoài bài này trong dự án thật):

~~~yaml
contract:
  service: Orders
  namespace: urn:example:orders:v1
  wsdlSha256: "<hash-of-published-wsdl>"
  schemas:
    - path: orders-types.xsd
      sha256: "<hash-of-published-xsd>"
  clientsTested:
    - partner-java-v1
    - partner-dotnet-v1
    - internal-java-v2
  compatibility:
    oldRequestToNewServer: verified
    newResponseToOldClient: gated
~~~

Hash giúp xác nhận artifact được kiểm đúng phiên bản. Nó **không tự chứng minh** schema semantically compatible; client tests/consumer inventory vẫn cần. Không đưa secrets/cert private material vào manifest.


## 12. Bốn cấp độ tương thích cần đánh giá

Một contract change có thể **schema-compatible** nhưng không **behavior-compatible**. Review nên tách ít nhất bốn lớp:

| Cấp | Câu hỏi | Ví dụ lỗi |
| --- | --- | --- |
| XML/schema compatibility | Instance có validate theo XSD mà consumer dùng không? | Client v1 reject unknown element |
| Binding/runtime compatibility | JAXB/SAAJ/Axiom/serializer có parse/marshal đúng không? | Primitive field không phân biệt absent với 0 |
| Semantic compatibility | Cùng request cũ có còn cùng ý nghĩa/kết quả không? | Absent đổi từ STANDARD sang EXPRESS |
| Operational/security compatibility | WSDL, endpoint, TLS, WS-Security, timeout còn hoạt động không? | WSDL import 404, Action thay đổi, signature coverage lệch |

### 12.1. Schema-compatible không có nghĩa semantic-compatible

Thêm `preferredDelivery` optional có thể giữ mọi XML request cũ validate được, nhưng nếu application đổi default thì request cũ không đổi bytes nhưng đổi kết quả. Đó là **semantic breaking change**.

### 12.2. Semantic-compatible không có nghĩa runtime-compatible

Nghiệp vụ có thể giữ behavior STANDARD, nhưng server response thêm element mà client cũ schema-validating không nhận; contract runtime vẫn break. Cũng có thể WSDL types đúng nhưng JAXB generator tạo property numeric/presence khác.

### 12.3. Runtime-compatible không có nghĩa operational-compatible

Một JAXB client có thể parse response mới trong local test, nhưng khi deploy có gateway enforce schema cũ, WS-Security signature trên Body hoặc SOAPAction mapping khác. Production vẫn có thể lỗi.

## 13. Quy trình release additive change

~~~mermaid
flowchart TD
    A["Đề xuất field + semantics"] --> B["Review XSD/WSDL diff"]
    B --> C{"Request, response hay cả hai?"}
    C --> D["Phân tích old/new producer-consumer"]
    D --> E["Update schema + JAXB + mapper"]
    E --> F["Test old fixtures, schemas và generated client"]
    F --> G{"Old client tương thích?"}
    G -- "Không" --> H["Gate field / version contract"]
    G -- "Có" --> I["Deploy server hỗ trợ optional field"]
    H --> I
    I --> J["Quan sát old client và lỗi SOAP"]
    J --> K["Opt-in client mới"]
    K --> L["Mở rộng phát/nhận field theo capability"]
    L --> M["Deprecation, rollback hoặc v2 nếu cần"]
~~~

### 13.1. Cổng review trước khi merge

- Định nghĩa field name, QName, type, cardinality, nillable, enum và max length.
- Nêu rõ absent/empty/nil/unknown-value semantics.
- Nêu thay đổi nằm trong request, response hay cả hai.
- Xác định client/server versions đang hỗ trợ, gồm third-party consumers.
- Chạy schema diff và test matrix với schema/client cũ.
- Kiểm WSDL/schema artifacts thực publish, không chỉ source files.
- Review default mapping, database migration và side effects.
- Review WS-Security signatures, SOAPAction/WS-Addressing, fault contract nếu thay Header/operation.

### 13.2. Cổng deploy

1. Deploy server hỗ trợ optional request field nhưng vẫn chấp nhận absent.
2. Giữ behavior mặc định cho client cũ.
3. Kiểm metrics: validation faults, unknown values, operation failures theo partner/client version.
4. Bật feature/capability cho nhóm client mới sau khi server ready.
5. Nếu response field mới có rủi ro, mặc định **chưa emit** cho client chưa xác minh.
6. Mở rộng từng nhóm partner và có ngưỡng dừng/rollback.
7. Ghi rõ hạn hỗ trợ contract v1; chỉ ngừng v1 khi consumer inventory xác nhận.

### 13.3. Rollback

Với additive optional request field, server thường có thể tắt xử lý field hoặc bỏ qua capability để trở về legacy behavior; tuy nhiên request mới đã gửi field có thể bị server rollback cũ reject. Không rollback server về schema cũ trong khi client mới đã phát payload mới trừ khi client được tắt tính năng trước.

Nếu server đã gửi response field mới rồi rollback sang response cũ, client mới phải thiết kế chấp nhận absent. Đây là lý do client mới luôn nên coi field optional thực sự là optional, không giả định server luôn gửi.

## 14. Chỉ số vận hành khi chuyển phiên bản

Đừng chỉ quan sát HTTP 200. Theo dõi các chỉ số không lộ dữ liệu nhạy cảm:

| Metric | Ý nghĩa |
| --- | --- |
| `soap_requests_total` theo operation/partner/version | Phân bố client versions |
| `xsd_validation_failures_total` theo schema version | Phát hiện payload không phù hợp |
| `unknown_element_events_total` | Client/parser gặp field chưa biết |
| `missing_optional_field_total` | Đo client chưa phát field mới |
| `unsupported_enum_value_total` | Client phát value mới/không hợp đồng |
| `soap_fault_total` theo fault code | Phân biệt lỗi contract/business/security |
| `wsdl_schema_resolution_failures_total` | Import/include bị lỗi |
| `client_version_capability_total` | Client đã opt-in field |
| `old_client_response_parse_failures_total` | Tín hiệu break backward compatibility |

Metric labels phải có cardinality giới hạn. Dùng partner/version đã đăng ký, không dùng raw user ID, payload field hoặc request content làm label. Không log toàn SOAP Envelope để tìm unknown element nếu Header chứa token/PII.

## 15. Những thay đổi nên tránh khi chỉ muốn thêm optional field

| Anti-pattern | Tác động | Cách làm an toàn hơn |
| --- | --- | --- |
| Thêm required element | Client cũ không gửi và schema mới reject | Optional + fallback được định nghĩa hoặc version |
| Thêm field response và phát cho tất cả client ngay | Strict client cũ reject | Test old client, gate field |
| Chỉ kiểm schema mới | Bỏ qua consumer XSD cũ | Giữ old schemas/generated artifacts |
| Regenerate old client trong CI bằng WSDL mới | Không còn test client cũ | Pin artifact đã release |
| Chèn field giữa xs:sequence | Có thể phá positional/parser assumptions | Thường thêm cuối và kiểm order |
| Đổi `minOccurs=0` thành required | Breaking | Fail/version |
| Coi nillable=true là optional | Nhầm absent với nil | Xác định từng trạng thái |
| Coi schema default là business default | Hành vi phụ thuộc parser/validator | Application mapper có test |
| Dùng Java field initializer làm default | Provider/binding có thể khác | Set default tại boundary sau unmarshal |
| Thêm enum constant và giả định client cũ hiểu | Strict enum mapping có thể fail | Unknown enum policy/versioning |
| Sửa source XSD nhưng quên WSDL/artifact | Runtime publish schema cũ | Inspect deployed WSDL/imports |
| Chỉ dùng MockWebServiceClient | Không kiểm HTTP/old SOAP client behavior | Real HTTP integration |
| Coi JAXB lenient là bảo đảm tương thích | Config/provider đổi sẽ break | Consumer artifact test |
| Để v1 mapper tự emit mọi field domain | Lộ response additions bất ngờ | Mapper riêng theo contract |
| Default absent theo profile mà không review | Thay semantic behavior client cũ | Giữ legacy default hoặc opt-in |
| Dùng body clientVersion không xác thực để gate | Caller giả capability | Trusted partner registry/identity |
| Bỏ kiểm WSDL imports | Partner codegen không tải schema | Resolve imports trong CI |

## 16. Checklist review cho phần tử tùy chọn

### XSD và XML shape

- Tên element/QName và namespace chính xác?
- `minOccurs="0"` có default `maxOccurs` phù hợp?
- Có thực sự cần `nillable="true"` không?
- Empty string, whitespace, absent, nil và unknown enum được xử lý thế nào?
- Field thêm đúng vị trí sequence và không đổi element cũ?
- Type/range/length có limit phù hợp?

### JAXB và application

- Generated source biểu diễn absent bằng `null`, wrapper hay `isSet`?
- Có phân biệt numeric zero/false với absent nếu nghiệp vụ cần?
- `JAXBElement<T>` có cần để giữ nil/presence?
- Default chỉ áp dụng tại một application boundary?
- Client mới có chấp nhận response từ server cũ?
- Generated old client vẫn là artifact riêng trong CI?

### WSDL và Spring-WS

- WSDL publish đúng schema mới và imports/includes resolve?
- `PayloadValidatingInterceptor` dùng schema đúng cho request/response version?
- `@PayloadRoot`, SOAPAction và WS-Addressing Action không đổi ngoài dự kiến?
- SOAP Fault detail/namespace có bị ảnh hưởng?
- `WebServiceTemplate` clients parse bằng đúng JAXB/schema artifacts đã phát hành?
- Server v1 response mapper tránh emit field mới cho old clients?

### Rollout và production

- Server mới đã deploy trước khi client mới gửi field?
- Response field mới có được gate theo capability xác minh không?
- Legacy default giữ behavior cũ?
- Có metrics theo contract/client version và fault code?
- Có rollback plan cho client request mới và server response mới?
- Có kiểm thử Java/.NET hoặc SOAP stack thực của đối tác?

## 17. Bài tập vận dụng

**Bài 1.** Thêm `preferredDelivery` kiểu `xs:string` vào cuối `xs:sequence` với `minOccurs="0"`. Vì sao request client cũ có thể vẫn hợp lệ trên server mới?

**Bài 2.** Server mới phát response có `preferredDelivery`, trong khi client cũ validate bằng XSD cũ. Vì sao `minOccurs="0"` ở schema server không giúp client cũ hiểu element mới?

**Bài 3.** Phân biệt ba instance: element absent, element empty và `xsi:nil="true"`. Điều kiện XSD để cho phép từng dạng là gì?

**Bài 4.** Một optional `xs:int` được JAXB map sang `int`. Vì sao application khó phân biệt client cũ không gửi field với client mới gửi số 0? Nêu hai cách mapping bảo toàn presence.

**Bài 5.** Một XSD element có `default="STANDARD"`, client cũ không gửi element. Vì sao không nên dựa vào XSD default thay business fallback?

**Bài 6.** Vì sao thêm enum value `SAME_DAY` có thể phá generated client cũ dù không thêm element?

**Bài 7.** WSDL source tham chiếu `orders-v2.xsd`, nhưng endpoint production vẫn trả schema cũ. Hãy liệt kê các bước kiểm artifact, resource packaging và deployment.

**Bài 8.** Thiết kế cách server giữ response v1 trong khi thêm field cho client v2. Có thể gate theo capability nào đáng tin?

**Bài 9.** Vì sao CI phải giữ generated client v1 thay vì chạy XJC lại từ WSDL hiện tại?

**Bài 10.** Một client JAXB cũ bỏ qua unknown element khi không bật schema validation. Điều đó đủ để công bố response mới cho mọi partner không?

**Bài 11.** Đề xuất ma trận test có request v1/v2, response v1/v2, old/new XSD và SOAP 1.1/1.2.

**Bài 12.** Khi nào nên dùng `xs:any` extension point, khi nào nên tạo namespace/endpoint v2?

**Bài 13.** Nếu absent preferredDelivery được map sang EXPRESS thay vì STANDARD, đây là breaking change ở lớp nào dù XSD validation vẫn pass?

**Bài 14.** Mô tả rollout server trước client cho request field mới và trình tự deploy khi thêm response field mới.

**Bài 15.** Viết test chứng minh generated client cũ nhận response server mới **không có** element mới, rồi thử response có element mới để ghi behavior.

### Gợi ý trả lời cốt lõi

- **1–2:** Server mới có schema chấp nhận absent; consumer cũ vẫn dùng schema cũ nên unknown element có thể bị reject.
- **3:** Absent cần minOccurs=0; nil cần nillable=true; empty là element có mặt với lexical content rỗng và phải hợp type.
- **4:** Dùng wrapper Integer hoặc primitive kèm presence indicator/isSet.
- **5:** Schema default áp dụng theo schema processing khi element hiện diện rỗng; business fallback cho absent nên được định nghĩa/test ở application.
- **6:** Enum consumer strict có thể reject literal mới.
- **7:** Kiểm packaged classpath resource, WSDL bean, servlet URL, build artifact và cache/proxy.
- **8–10:** Capability gắn với identity/registry tin cậy; lenient JAXB phải được chứng minh trên artifact/runtime production.
- **11–12:** Kiểm cả hai chiều producer-consumer; wildcard cần được thiết kế từ đầu, còn thay type/semantics lớn thường cần version.
- **13–15:** Semantic breaking; deploy server hỗ trợ absent trước client phát field; pin old generated client và test wire response.

## Tài liệu tham khảo

- [W3C — XML Schema Part 1: Structures](https://www.w3.org/TR/xmlschema-1/) — minOccurs, maxOccurs, nillable, element declaration và schema validation.
- [W3C — XML Schema Part 2: Datatypes](https://www.w3.org/TR/xmlschema-2/) — simple types, lexical/value spaces và facets.
- [Jakarta XML Binding Specification](https://jakarta.ee/specifications/xml-binding/) — JAXB binding, marshalling/unmarshalling và generated model.
- [Spring Web Services Reference 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/) — contract-first, XSD/WSDL publishing, endpoint mapping, PayloadValidatingInterceptor và client/server tests.
- [Spring-WS API — DefaultWsdl11Definition](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/wsdl/wsdl11/DefaultWsdl11Definition.html) — publish WSDL từ schema và WSDL 1.1 definition.
- [JAXB Unmarshaller API](https://jakarta.ee/specifications/xml-binding/4.0/apidocs/jakarta.xml.bind/jakarta/xml/bind/unmarshaller) — unmarshal, schema association và validation event handler.
- [W3C — Web Services Description Language (WSDL) 1.1](https://www.w3.org/TR/wsdl.html) — messages, portType, binding, service và types.

**Ghi nhớ:** thêm một phần tử optional chỉ là thay đổi schema theo một chiều. Hãy kiểm riêng **client cũ → server mới** và **server mới → client cũ**; hiểu absent/empty/nil/default; giữ namespace, sequence và generated artifacts; đặt business default ở một boundary; publish đúng WSDL/XSD; và dùng **client cũ thật** để chứng minh response mới không phá consumer. Nếu không chứng minh được response compatibility, hãy giữ response cũ, gate field hoặc phát hành contract version mới.
