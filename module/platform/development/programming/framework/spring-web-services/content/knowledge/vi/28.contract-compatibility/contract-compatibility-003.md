# Thay đổi kiểu, thứ tự, số lần xuất hiện và trường bắt buộc

> **Chương:** Tương thích hợp đồng  
> **Module:** SPRING_WEB_SERVICES — phát triển dịch vụ SOAP contract-first với Spring Web Services, thiết kế XSD/WSDL, ánh xạ JAXB, endpoint và SOAP client; xử lý SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích cho tích hợp doanh nghiệp.

## 1. Vì sao thay đổi XSD nhỏ có thể phá vỡ tích hợp?

Trong SOAP contract-first, XSD là một phần của giao diện công khai. Client và server có thể được phát triển, biên dịch và phát hành độc lập. Một phía có thể vẫn chạy bình thường với model cũ trong khi phía kia bắt đầu phát XML theo schema mới. Những thay đổi tưởng đơn giản như đổi kiểu dữ liệu, chuyển vị trí element, cho phép nhiều occurrences hoặc làm một field trở thành bắt buộc có thể gây lỗi ở parser, XSD validator, JAXB hoặc business logic.

Ví dụ contract ban đầu:

~~~xml
<xs:complexType name="SubmitOrderRequest">
  <xs:sequence>
    <xs:element name="orderId" type="xs:string"/>
    <xs:element name="quantity" type="xs:int"/>
    <xs:element name="note" type="xs:string" minOccurs="0"/>
  </xs:sequence>
</xs:complexType>
~~~

Một phiên bản sau chuyển quantity thành xs:long, đưa note lên trước orderId, thêm currency bắt buộc và cho phép quantity lặp lại. Client đã generate JAXB classes từ XSD cũ có thể không marshal/unmarshal được message mới. Ngay cả khi XML parser chấp nhận, business code có thể chỉ đọc một quantity trong khi producer gửi nhiều giá trị.

Đánh giá phải dựa trên cặp producer-consumer và chiều truyền message:

- Request: client là producer, SOAP server là consumer.
- Response: SOAP server là producer, client là consumer.
- Fault cũng là một message contract.
- Khi rollout, có thể cùng lúc tồn tại client cũ, client mới, server cũ và server mới.

Sau bài này, bạn có thể dự đoán ảnh hưởng của thay đổi XSD, phân biệt backward/forward compatibility, hiểu JAXB và Spring-WS validation, lên kế hoạch version hóa, và viết tests chứng minh tương thích giữa các thế hệ producer/consumer.

**Nguyên tắc:** XSD mới compile hoặc Java code mới build thành công không chứng minh SOAP wire compatibility. Phải kiểm tra XML thực tế do producer cũ/mới tạo ra có được consumer cũ/mới chấp nhận và hiểu đúng hay không.

## 2. Bốn trục thay đổi và mô hình tương thích

| Trục | Thay đổi điển hình | Tác động |
|---|---|---|
| Kiểu dữ liệu | xs:string sang xs:int, xs:int sang xs:long, đổi facets | Value space, lexical form, JAXB Java type |
| Thứ tự | Đổi vị trí element trong xs:sequence | XML wire order và validation |
| Số lần xuất hiện | minOccurs, maxOccurs, unbounded | Absent, scalar hay collection |
| Tính bắt buộc | Optional sang required, thêm field bắt buộc | Producer cũ có thể không gửi field |

Còn phải xét nillable, default, fixed, enumeration, pattern, min/max facets, namespace, element name, choice, substitution groups và SOAP action.

- **Backward compatibility:** consumer mới đọc được message do producer cũ gửi.
- **Forward compatibility:** consumer cũ đọc được message do producer mới gửi.
- **Wire compatibility:** XML trên wire vẫn phù hợp grammar và semantics mà hai bên kỳ vọng.

Các thuật ngữ backward/forward đôi khi được định nghĩa theo sản phẩm. Vì vậy hãy luôn ghi rõ cặp version, ví dụ client-v1 → server-v2, thay vì chỉ ghi “compatible”.

## 3. Ma trận producer và consumer

| Producer | Consumer | Câu hỏi |
|---|---|---|
| Client v1 | Server v2 | Server mới có đọc request cũ? |
| Client v2 | Server v1 | Server cũ có đọc request mới? |
| Server v1 | Client v2 | Client mới có đọc response cũ? |
| Server v2 | Client v1 | Client cũ có đọc response mới? |

Một thay đổi có thể backward-compatible với server mới nhưng không forward-compatible với server cũ. Trước rollout phải xác định phiên bản nào được nâng trước và thời gian coexistence.

## 4. Thay đổi simple type

### 4.1. xs:string sang xs:int

~~~xml
<!-- Contract cũ -->
<xs:element name="quantity" type="xs:string"/>
<!-- Contract mới -->
<xs:element name="quantity" type="xs:int"/>
~~~

Producer cũ có thể gửi 0012 hoặc chuỗi như 12 boxes. Schema mới chỉ nhận lexical values hợp lệ của xs:int. JAXB field có thể đổi từ String sang int/Integer. Đây thường là breaking change nếu field trước đây chứa code, formatting hoặc nội dung tự do.

### 4.2. xs:int sang xs:long

~~~xml
<xs:element name="quantity" type="xs:long"/>
~~~

xs:long có value range rộng hơn xs:int. Consumer mới thường đọc được giá trị cũ nằm trong miền int, nhưng producer mới gửi giá trị vượt miền cũ có thể làm client cũ fail hoặc overflow. Đây là mở rộng có điều kiện, không tương thích hai chiều vô điều kiện.

### 4.3. xs:decimal sang xs:double

Với tiền tệ, xs:decimal thường được JAXB ánh xạ thành BigDecimal; xs:double thành floating-point. Binary floating point không biểu diễn chính xác mọi phân số thập phân. Đổi kiểu có thể tạo rounding, làm sai phép so sánh hoặc reconciliation dù XML vẫn validate.

~~~java
BigDecimal exact = new BigDecimal("19.90");
double approximate = 19.90d;
~~~

Không đổi decimal sang double cho tiền tệ nếu chưa có thiết kế precision và business semantics rõ ràng.

### 4.4. Facets thay đổi value space

~~~xml
<xs:simpleType name="OrderCode">
  <xs:restriction base="xs:string">
    <xs:minLength value="1"/>
    <xs:maxLength value="20"/>
    <xs:pattern value="[A-Z0-9-]+"/>
  </xs:restriction>
</xs:simpleType>
~~~

Java field vẫn có thể là String, nhưng giá trị lowercase, rỗng hoặc dài hơn 20 ký tự trước đây hợp lệ nay bị reject. Review compatibility phải so sánh value space, không chỉ Java type.

### 4.5. Phân loại thay đổi kiểu

| Thay đổi | Rủi ro | Đánh giá |
|---|---|---|
| xs:int → xs:long | Consumer cũ không chứa được giá trị lớn | Mở rộng có điều kiện |
| xs:long → xs:int | Giá trị lớn bị từ chối | Breaking |
| xs:string → xs:int | Lexical values cũ không còn hợp lệ | Breaking |
| xs:decimal → xs:double | Precision và Java type thay đổi | Semantic breaking |
| Nới maxLength | Consumer cũ có thể giới hạn độ dài | Forward risk |
| Siết maxLength | Payload hiện có bị reject | Breaking |
| Thêm enum value | Consumer cũ có thể không hiểu | Forward risk |
| Xóa enum value | Producer cũ còn phát giá trị cũ | Breaking |

## 5. Thứ tự element trong xs:sequence

### 5.1. Sequence yêu cầu thứ tự

~~~xml
<xs:complexType name="Address">
  <xs:sequence>
    <xs:element name="street" type="xs:string"/>
    <xs:element name="city" type="xs:string"/>
    <xs:element name="postalCode" type="xs:string"/>
  </xs:sequence>
</xs:complexType>
~~~

XML phải theo thứ tự street, city, postalCode. XML có city trước street có thể well-formed nhưng không hợp lệ theo schema. Parser tạo DOM thành công không đồng nghĩa XSD validation thành công.

### 5.2. Đổi thứ tự là thay đổi wire format

JAXB marshaller thường phát element theo mapping/annotation/model order tương ứng. Đổi sequence có thể thay thứ tự XML được gửi; client cũ phát thứ tự cũ có thể bị server mới từ chối và ngược lại.

Coi việc đổi thứ tự element đã tồn tại trong sequence là breaking change, trừ khi contract và tất cả consumer đã được chứng minh không phụ thuộc thứ tự. Không dựa vào parser permissive.

### 5.3. Thêm element giữa sequence

~~~xml
<xs:sequence>
  <xs:element name="orderId" type="xs:string"/>
  <xs:element name="currency" type="xs:string" minOccurs="0"/>
  <xs:element name="amount" type="xs:decimal"/>
</xs:sequence>
~~~

Consumer mới có thể đọc request cũ do currency optional. Nhưng consumer cũ strict validation có thể reject element currency vì schema cũ không biết nó. Đặt optional element cuối sequence có thể giảm tác động cho một số parser không validate, nhưng không bảo đảm consumer strict chấp nhận.

### 5.4. xs:all và xs:choice

xs:all cho phép thứ tự linh hoạt trong các ràng buộc của phiên bản XSD/provider; xs:choice chọn một nhánh thay vì tất cả. Không thay sequence bằng all/choice giữa các version nếu chưa xét XSD version, JAXB binding và semantics. Compositor thay đổi có thể làm generated model khác hoặc schema không còn hợp lệ.

## 6. minOccurs và trường bắt buộc

### 6.1. Required sang optional

~~~xml
<!-- Required theo mặc định minOccurs=1 -->
<xs:element name="note" type="xs:string"/>
<!-- Optional -->
<xs:element name="note" type="xs:string" minOccurs="0"/>
~~~

Schema mới cho phép bỏ note; consumer mới thường vẫn đọc được message cũ có note. Nhưng producer mới có thể bỏ note và consumer cũ vẫn yêu cầu nó. Optional hóa do đó không tương thích hai chiều tự động.

### 6.2. Optional sang required

~~~xml
<!-- Cũ -->
<xs:element name="currency" type="xs:string" minOccurs="0"/>
<!-- Mới -->
<xs:element name="currency" type="xs:string"/>
~~~

Client cũ không phát currency sẽ bị server mới strict validation từ chối trước khi business logic chạy. Đây thường là breaking change. JAXB không được giả định tự điền giá trị cho field thiếu.

### 6.3. Default không phải giải pháp mặc định

Default trong XSD, schema validation/PSVI và JAXB binding có semantics phụ thuộc cách xử lý. Hãy chuẩn hóa default rõ ràng ở application mapping nếu nghiệp vụ cho phép. Không đoán currency, timezone hoặc đơn vị đo khi field vắng mặt.

## 7. maxOccurs và scalar/collection

### 7.1. Một phần tử sang nhiều phần tử

~~~xml
<!-- Cũ -->
<xs:element name="tag" type="xs:string"
            minOccurs="0" maxOccurs="1"/>
<!-- Mới -->
<xs:element name="tag" type="xs:string"
            minOccurs="0" maxOccurs="unbounded"/>
~~~

JAXB có thể đổi từ field String sang List<String>. Consumer mới đọc được payload cũ có không hoặc một item; consumer cũ không nhất thiết đọc được payload mới có nhiều item. Business code cũ có thể chỉ lưu item đầu/cuối hoặc ghi đè.

### 7.2. Nhiều phần tử sang một

Siết unbounded về 1 làm producer cũ gửi nhiều values bị reject; nếu consumer không validate mà chỉ đọc một item thì có nguy cơ mất dữ liệu. Đánh giá cả validation và business behavior.

| Thay đổi | Producer cũ → consumer mới | Producer mới → consumer cũ |
|---|---|---|
| maxOccurs 1 → unbounded | Thường đọc được 0/1 | Có thể fail khi gửi >1 |
| unbounded → 1 | Có thể fail với payload nhiều item | Producer mới gửi 1 thường phù hợp |
| minOccurs 1 → 0 | Consumer mới có thể nhận | Consumer cũ có thể fail khi field vắng |
| minOccurs 0 → 1 | Consumer mới có thể reject producer cũ | Field mới có thể unknown với consumer cũ |

Kết quả còn phụ thuộc strict validation, JAXB unknown-element policy và semantics của business.

## 8. Absent, empty, nil, default và fixed

Các trạng thái này không đồng nghĩa.

Absent: element không xuất hiện. Empty: element có mặt nhưng nội dung rỗng. Nil: element có mặt và có xsi:nil="true". Với xs:string, empty có thể hợp lệ; type khác có thể không cho phép.

~~~xml
<!-- Empty -->
<note/>
<!-- Nil -->
<note xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:nil="true"/>
~~~

| Declaration | Absent | xsi:nil=true | Empty |
|---|---|---|---|
| Required, nillable=false | Reject | Reject | Tùy type |
| Optional, nillable=false | Accept | Reject | Tùy type |
| Required, nillable=true | Reject | Accept | Tùy type |
| Optional, nillable=true | Accept | Accept | Tùy type |

minOccurs điều khiển sự có mặt; nillable điều khiển nil value cho element hiện diện. default/fixed còn có semantics riêng; test trên provider JAXB/XSD thật thay vì giả định.

## 9. Enumeration và facets

Thêm enum ON_HOLD vào OrderStatus có thể khiến client cũ với generated Java enum chỉ biết NEW/PAID/CANCELLED lỗi khi unmarshal hoặc xử lý không xác định tùy binding. Đây là forward compatibility risk. Xóa enum cũ có thể khiến producer cũ bị reject.

Tương tự, giảm maxLength hoặc tăng minInclusive siết value space; nới pattern/enumeration cho producer mới gửi giá trị consumer cũ không hiểu. Hãy test unknown enum và các giá trị biên, không chỉ test các values phổ biến hiện tại.

## 10. Tác động tới JAXB-generated classes và OXM

XSD có thể tạo Java types như String, Integer, Long, BigDecimal, XMLGregorianCalendar, collection, enum hoặc JAXBElement<T>. Required/optional, nillable, occurrence và binding customizations ảnh hưởng annotations, getter/setter, propOrder và null semantics.

Ví dụ scalar:

~~~java
protected String phone;
public String getPhone() { return phone; }
public void setPhone(String value) { this.phone = value; }
~~~

Sau khi maxOccurs thành unbounded:

~~~java
protected List<String> phone;
public List<String> getPhone() {
    if (phone == null) {
        phone = new ArrayList<>();
    }
    return this.phone;
}
~~~

Generated API đã đổi. Downstream Java modules có thể bị source/binary compatibility break. Không sửa generated source bằng tay; dùng binding customization hoặc mapper/domain DTO riêng.

### 10.1. propOrder và marshal

JAXB generated model có thể dùng @XmlType(propOrder=...). Đổi sequence có thể đổi thứ tự XML marshal. Không sửa annotation thủ công để làm request qua một schema khác; cần schema/model cùng version.

### 10.2. JAXB không tự đảm bảo XSD validation

Unmarshaller có thể đọc XML well-formed thành object mà không validate toàn schema. Cấu hình validation rõ ràng bằng schema hoặc Spring-WS PayloadValidatingInterceptor. XSD validation cũng không thay authentication, WS-Security hay authorization.

### 10.3. Jaxb2Marshaller minh họa

~~~java
@Bean
Jaxb2Marshaller orderMarshaller() {
    Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
    marshaller.setContextPath("com.example.orders.schema");
    marshaller.setSchemas(
            new ClassPathResource("xsd/orders/orders.xsd"));
    marshaller.setValidationEventHandler(event -> false);
    return marshaller;
}
~~~

Cần kiểm tra Spring OXM version, schema imports và XML parser security. Không chuyển validation errors thành ignore chỉ để duy trì tương thích giả.

## 11. Wire, source, binary và semantic compatibility

| Loại | Ví dụ |
|---|---|
| Wire | Đổi sequence, namespace, type hoặc thêm required element |
| Source | Getter đổi String thành List<String> |
| Binary | Method descriptor generated thay đổi |
| Semantic | Decimal sang double; enum mới được hiểu sai |
| Operational | Payload lớn hơn, occurrences nhiều hơn, action/endpoint đổi |
| Validation | Client/server dùng XSD version khác nhau |

Maven compile thành công không chứng minh wire compatibility. Nếu generated models là artifact downstream modules sử dụng, cần API diff/compilation tests cho consumer được hỗ trợ.

## 12. Mở rộng an toàn hơn: optional, normalize và deprecate

### 12.1. Add optional element

~~~xml
<xs:sequence>
  <xs:element name="orderId" type="xs:string"/>
  <xs:element name="amount" type="xs:decimal"/>
  <xs:element name="deliveryNote" type="xs:string"
              minOccurs="0"/>
</xs:sequence>
~~~

Đây thường là cách mở rộng ít rủi ro hơn cho consumer mới, nhưng consumer cũ strict vẫn có thể reject unknown element. Producer mới chỉ nên gửi field sau khi biết consumer hỗ trợ version/capability đó.

### 12.2. Chuyển field sang required theo giai đoạn

1. Phát hành schema chuyển tiếp cho phép optional.
2. Server chấp nhận thiếu và chỉ chuẩn hóa default khi semantics đã rõ.
3. Thu telemetry theo client đã xác thực.
4. Nâng cấp producers và xác nhận không còn request thiếu field.
5. Ra contract version strict mới, có migration window.
6. Ngừng client cũ theo thông báo và policy.

Không tự đoán currency hoặc đơn vị nếu thiếu field có thể thay đổi kết quả nghiệp vụ.

### 12.3. Deprecation và precedence

Thông báo deprecated, giữ đọc field cũ trong thời gian chuyển đổi, quy định precedence nếu cả cũ và mới cùng xuất hiện, ghi telemetry theo identity đã xác thực. Chỉ removal khi usage đạt tiêu chí và consumer owners xác nhận.

### 12.4. Version namespace/endpoint

~~~text
/v1/orders  → WSDL/XSD v1
/v2/orders  → WSDL/XSD v2

urn:example:orders:v1
urn:example:orders:v2
~~~

Chọn URL version, namespace version hoặc endpoint version theo governance/routing. Không thay schema tại cùng URL/WSDL một cách bất ngờ.

## 13. Spring-WS endpoint mapping và contract version

~~~java
@Endpoint
public class OrdersEndpoint {
    private static final String NS = "urn:example:orders:v1";

    @PayloadRoot(namespace = NS,
                 localPart = "SubmitOrderRequest")
    @ResponsePayload
    public SubmitOrderResponse submit(
            @RequestPayload SubmitOrderRequest request) {
        return service.submit(request);
    }
}
~~~

QName gồm namespace URI và local part. Namespace v2 tạo QName khác. Có thể tạo endpoint/adapter v2 rồi map JAXB v2 DTO sang internal command, tránh để business domain phụ thuộc trực tiếp generated classes của từng schema.

~~~text
SOAP v1 XML → JAXB v1 DTO → V1 mapper ─┐
                                       ├→ Internal command/domain
SOAP v2 XML → JAXB v2 DTO → V2 mapper ─┘
~~~

Cấu hình PayloadValidatingInterceptor với schema đúng version. Kiểm tra request, response và Fault theo đúng contract. SOAPAction và WS-Addressing Action cũng là metadata của binding, không được quên khi schema thay đổi.

## 14. Ma trận kiểm thử compatibility

Giữ fixtures của client v1/v2, gồm payload hợp lệ, absent/nil/empty, numeric boundaries, enum values, occurrences lặp, thứ tự và response/Fault. Chạy các cặp producer/consumer trong rollout window:

| Producer | Consumer | Mục tiêu |
|---|---|---|
| Client v1 | Server v1 | Baseline |
| Client v1 | Server v2 | Backward request |
| Client v2 | Server v1 | Forward request |
| Server v1 | Client v2 | Client mới đọc response cũ |
| Server v2 | Client v1 | Client cũ đọc response mới |
| Client/server v2 | Endpoint v2 | Contract mới |
| Payload invalid | Protected endpoint | Reject, no side effects |

### 14.1. JUnit schema validation mẫu

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.io.StringReader;
import javax.xml.XMLConstants;
import javax.xml.transform.stream.StreamSource;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;
import org.junit.jupiter.api.Test;

class ContractSchemaTest {

    private Schema loadSchema(String resource) throws Exception {
        var factory = SchemaFactory.newInstance(
                XMLConstants.W3C_XML_SCHEMA_NS_URI);
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        try (var input = getClass().getResourceAsStream(resource)) {
            assertNotNull(input);
            return factory.newSchema(new StreamSource(input));
        }
    }

    @Test
    void validatesFixtureAgainstItsOwnContractVersion()
            throws Exception {
        Schema v1 = loadSchema("/xsd/v1/orders.xsd");
        String requestV1 = """
            <ord:SubmitOrderRequest
                xmlns:ord="urn:example:orders:v1">
              <ord:orderId>ORD-1</ord:orderId>
              <ord:amount>10.00</ord:amount>
            </ord:SubmitOrderRequest>
            """;

        var validator = v1.newValidator();
        validator.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        validator.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        assertDoesNotThrow(() ->
                validator.validate(
                    new StreamSource(new StringReader(requestV1))));
    }
}
~~~

Fixture phải đúng QName/namespace/version. Không validate payload v1 bằng schema v2 chỉ vì hai file gần giống nhau. Với nested imports, cấu hình resolver whitelist và test offline.

### 14.2. JAXB round-trip

~~~text
XML fixture
  → Unmarshal bằng JAXB context đúng version
  → Assert type, collection, absent/nil semantics
  → Marshal object trở lại XML
  → Validate output bằng XSD cùng version
~~~

Assert cả XML order nếu contract cần, decimal precision, enum unknown behavior và occurrences. Object equality không đủ chứng minh wire XML không mất thông tin.

### 14.3. Spring-WS HTTP tests

Kiểm thử qua MessageDispatcherServlet/WebServiceTemplate hoặc SOAP client độc lập để xác minh QName, namespace, action, SOAP version, request/response validation, endpoint v1/v2, Fault và WS-Security/TLS nếu contract yêu cầu. MockWebServiceClient hữu ích cho endpoint-level tests; dùng HTTP integration tests khi transport/content type/TLS/servlet config ảnh hưởng.

## 15. Quy trình review thay đổi schema

1. Xác định QName, namespace, simple/complex type và facets.
2. So sánh root XSD cùng imports/includes.
3. Đánh giá min/maxOccurs, sequence/choice và thứ tự wire.
4. Phân biệt absent, empty, nil, default và fixed.
5. Xác định producer/consumer version cho request, response và Fault.
6. Kiểm tra JAXB Java types, API signatures, collections, enum và propOrder.
7. Chạy ma trận old/new payload trên schema/runtime được hỗ trợ.
8. Kiểm thử semantics: decimal precision, enum, nil, absent, boundaries và repeated values.
9. Lập rollout, deprecation, namespace/endpoint version.
10. Ghi kết luận compatible, conditional hoặc breaking, cùng các cặp version hỗ trợ.

## 16. Case study: thêm currency và đổi amount

### 16.1. Contract v1

~~~xml
<xs:complexType name="SubmitOrderRequest">
  <xs:sequence>
    <xs:element name="orderId" type="xs:string"/>
    <xs:element name="amount" type="xs:decimal"/>
  </xs:sequence>
</xs:complexType>
~~~

Client v1 gửi orderId và amount. Đề xuất v2 ban đầu:

~~~xml
<xs:complexType name="SubmitOrderRequest">
  <xs:sequence>
    <xs:element name="orderId" type="xs:string"/>
    <xs:element name="currency" type="xs:string"/>
    <xs:element name="amount" type="xs:double"/>
  </xs:sequence>
</xs:complexType>
~~~

Đây là hai breaking changes: currency required khiến client v1 không gửi bị reject; decimal sang double đổi precision/JAXB type.

### 16.2. Giai đoạn chuyển tiếp

Giữ amount là decimal và currency optional ở cuối sequence:

~~~xml
<xs:complexType name="SubmitOrderRequest">
  <xs:sequence>
    <xs:element name="orderId" type="xs:string"/>
    <xs:element name="amount" type="xs:decimal"/>
    <xs:element name="currency" type="xs:string"
                minOccurs="0"/>
  </xs:sequence>
</xs:complexType>
~~~

Server mới dùng currency nếu có. Nếu thiếu, chỉ dùng default khi partner/operation có business configuration rõ; nếu không thì trả lỗi nghiệp vụ có kiểm soát. Không suy currency từ locale hoặc IP.

Sau khi client migrate và telemetry xác nhận không còn request thiếu field, phát hành strict v2 contract với currency required, giữ decimal, có namespace/endpoint version và migration window.

### 16.3. Tiêu chí nghiệm thu

| Kiểm tra | Kết quả |
|---|---|
| Client v1 → server chuyển tiếp | Request cũ vẫn hoạt động |
| Client v2 có currency | Validate và xử lý đúng |
| Client thiếu currency ở strict v2 | Reject rõ, không đoán |
| Amount precision | Không mất decimal precision |
| JAXB model | Type/optional mapping đúng |
| Response/Fault | Client tương ứng đọc đúng |
| Version routing | Không validate payload vào nhầm schema |
| Telemetry | Nhận diện client còn dùng v1 |

## 17. Bài tập tự luyện kèm đáp án

**Bài 1 — xs:int sang xs:long:** Client cũ dùng Java int. Thay đổi luôn tương thích?

**Đáp án:** Không. Giá trị cũ thường nằm trong miền long, nhưng producer mới có thể gửi giá trị vượt miền int của consumer cũ.

**Bài 2 — Required sang optional:** Schema mới cho phép bỏ field. Consumer cũ có đọc được message không còn field?

**Đáp án:** Không nếu schema cũ yêu cầu field và validation strict.

**Bài 3 — Optional sang required:** JAXB tự điền field thiếu?

**Đáp án:** Không được giả định; validator có thể reject trước JAXB.

**Bài 4 — Đổi sequence:** XML well-formed nhưng sai thứ tự có hợp lệ XSD?

**Đáp án:** Không nếu xs:sequence quy định thứ tự cũ.

**Bài 5 — Optional element giữa sequence:** Consumer cũ không biết element mới có thể reject?

**Đáp án:** Có, nhất là khi validation strict. Đặt cuối sequence không tự bảo đảm compatibility.

**Bài 6 — maxOccurs unbounded:** Getter đổi scalar sang list có phải chỉ là API detail?

**Đáp án:** Không. Wire contract, generated API và business semantics đều đổi.

**Bài 7 — Optional nhưng nillable=false:** xsi:nil có hợp lệ?

**Đáp án:** Không. Optional cho phép absent, không có nghĩa cho phép nil.

**Bài 8 — Thêm enum:** Client cũ có thể lỗi khi nhận enum value mới?

**Đáp án:** Có; unknown value behavior tùy JAXB binding/runtime và phải test.

**Bài 9 — decimal sang double:** Có phù hợp cho tiền tệ?

**Đáp án:** Thường không, vì binary floating point không giữ chính xác mọi decimal fractions.

**Bài 10 — JAXB unmarshal pass:** Có chứng minh XSD facets đều hợp lệ?

**Đáp án:** Không. Phải bật schema validation rõ ràng.

**Bài 11 — Namespace đổi:** Element thêm optional nhưng chuyển namespace. Client cũ tự hiểu?

**Đáp án:** Không. QName thay đổi, cần version-aware mapping.

**Bài 12 — XSD compile pass:** Đã đủ phát hành?

**Đáp án:** Chưa. Cần producer/consumer matrix, JAXB, validation, endpoint/action và tests thực tế.

## 18. Checklist review thay đổi XSD

### Kiểu và value space
- [ ] So sánh base type, range, lexical representation.
- [ ] Kiểm tra decimal precision và numeric boundaries.
- [ ] So min/max length, pattern, enumeration và numeric facets.
- [ ] Đánh giá dữ liệu thực đang tồn tại.
- [ ] Có chiến lược unknown enum values.
- [ ] Không đổi tiền tệ sang floating point thiếu đánh giá.

### Cấu trúc và occurrence
- [ ] So sequence, choice, all và XML order.
- [ ] Xác định element thêm/bỏ/chuyển vị trí.
- [ ] So minOccurs/maxOccurs và scalar/collection.
- [ ] Kiểm tra optional/required.
- [ ] Phân biệt absent, empty, nil, default và fixed.
- [ ] Kiểm nested types, attributes, imports/includes.

### JAXB và Spring-WS
- [ ] Generate model từ schema đúng version.
- [ ] Review Java type, getter/setter, collection, enum, JAXBElement và propOrder.
- [ ] Không sửa generated source bằng tay.
- [ ] Validate request/response ở đúng direction.
- [ ] Endpoint mapping theo QName/version rõ.
- [ ] SOAPAction/WS-Addressing Action và SOAP version được kiểm.
- [ ] JAXB round-trip giữ precision và nil/absence semantics.

### Producer/consumer rollout
- [ ] Có ma trận client/server v1/v2.
- [ ] Ghi backward/forward compatibility theo từng hướng.
- [ ] Có version/namespace/endpoint strategy khi breaking.
- [ ] Có deprecation, telemetry và owner của client cũ.
- [ ] Không đổi schema tại contract URL bất ngờ.
- [ ] Default có semantics nghiệp vụ rõ.

### Kiểm thử
- [ ] Fixtures v1/v2 validate bằng schema phù hợp.
- [ ] Test old producer→new consumer và new producer→old consumer khi cần.
- [ ] Test sequence, boundary, nil, absent, enum và repeated values.
- [ ] Test response, Fault và actions.
- [ ] Test HTTP SOAP thật ngoài mock khi transport ảnh hưởng.
- [ ] Validation fail không tạo business side effects.
- [ ] CI giữ compatibility report và generated API diff.

**Ghi nhớ:** Một thay đổi XSD chỉ an toàn khi producer và consumer của mọi phiên bản còn được hỗ trợ vẫn trao đổi đúng nội dung, kiểu và ngữ nghĩa. Thay kiểu dữ liệu, thứ tự sequence, minOccurs/maxOccurs, nillable, enum hay trường bắt buộc phải được đánh giá ở wire XML, JAXB-generated Java API và business behavior. Với Spring Web Services, hãy version hóa contract khi cần, giữ mapper/domain độc lập generated DTO, validate đúng schema tại đúng endpoint và chứng minh compatibility bằng ma trận producer/consumer cùng payload fixtures thực tế.
