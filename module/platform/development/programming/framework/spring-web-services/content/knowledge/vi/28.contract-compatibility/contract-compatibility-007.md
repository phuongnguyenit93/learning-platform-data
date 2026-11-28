# Chuyển đổi bằng XSLT và xác định giới hạn chuyển đổi hai chiều

Khi một dịch vụ SOAP phát hành phiên bản hợp đồng mới, đối tác cũ không thể lập tức thay client, JAXB model và WSDL. Một **lớp chuyển đổi XML** giúp server nhận payload cũ, chuyển nó sang cấu trúc nội bộ mới, rồi biến response mới về dạng mà client cũ hiểu. Trong Spring Web Services (Spring-WS), **PayloadTransformingInterceptor** dùng XSLT stylesheet riêng cho request và response để hỗ trợ nhiều phiên bản message.

Nhưng **chuyển đổi được theo hai chiều không đồng nghĩa chuyển đổi đảo ngược được**. Nếu schema mới có trường bắt buộc mà schema cũ không biểu diễn, hoặc schema cũ chứa thông tin không có chỗ lưu trong schema mới, một chiều chuyển đổi phải thêm mặc định, bỏ dữ liệu hoặc lưu metadata phụ. Khi dữ liệu đã mất, stylesheet chiều ngược không thể tự khôi phục chính xác giá trị ban đầu.

Bài thuộc chương **Tương thích hợp đồng** của module **SPRING_WEB_SERVICES**: phát triển SOAP contract-first với XSD/WSDL, JAXB/OXM, endpoint và SOAP client, đồng thời xử lý SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích doanh nghiệp. Trọng tâm là thiết kế chuyển đổi bằng **XSLT có kiểm soát**, tích hợp vào request/response pipeline và xác định rõ **miền dữ liệu mà phép chuyển đổi hai chiều có thể bảo toàn**.

## 1. Vì sao cần chuyển đổi hợp đồng?

Phiên bản đầu của dịch vụ Orders dùng namespace urn:example:orders:v1:

~~~xml
<v1:CreateOrderRequest xmlns:v1="urn:example:orders:v1">
    <v1:customerId>C-42</v1:customerId>
    <v1:amount>125.00</v1:amount>
</v1:CreateOrderRequest>
~~~

Phiên bản mới dùng namespace urn:example:orders:v2, tách tiền và tiền tệ, bổ sung kênh tạo đơn:

~~~xml
<v2:CreateOrderRequest xmlns:v2="urn:example:orders:v2">
    <v2:customer>
        <v2:id>C-42</v2:id>
    </v2:customer>
    <v2:total>
        <v2:value>125.00</v2:value>
        <v2:currency>VND</v2:currency>
    </v2:total>
    <v2:channel>LEGACY_API</v2:channel>
</v2:CreateOrderRequest>
~~~

Luồng tương thích:

~~~text
V1 request  --request XSLT-->   V2 request
V2 response --response XSLT--> V1 response
~~~

Spring-WS có PayloadTransformingInterceptor cho mục tiêu hỗ trợ **nhiều phiên bản của cùng một web service**: cấu hình requestXslt để đổi request cũ sang dạng mới và responseXslt để đổi response mới về dạng cũ. [Spring-WS Reference 4.1.4 — Using PayloadTransformingInterceptor](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/)

### 1.1. Các lớp không nên trộn lẫn

| Lớp | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| **WSDL/XSD contract** | Công bố message, operation, namespace, type, binding | Request V1 |
| **XSLT compatibility mapping** | Đổi cấu trúc XML giữa hai contract | customerId → customer/id |
| **JAXB/OXM** | Ánh xạ XML đang xử lý thành Java object | V2 XML → V2 DTO |
| **Domain/application** | Quy tắc nghiệp vụ và authorization | Kiểm tra khách hàng, tạo đơn |
| **Transport/security** | SOAP version, HTTP/JMS, TLS, WS-Security | Signature, Fault, timeout |

XSLT không tự nâng cấp WSDL, không thay thế schema validation và không giải quyết quy tắc nghiệp vụ. Nó biến đổi **XML payload** theo stylesheet; contract/version selection và mapping ownership vẫn phải được thiết kế riêng.

## 2. Mô hình toán học: hai chiều không có nghĩa là nghịch đảo

Gọi A là tập payload hợp lệ theo schema V1, B là tập payload hợp lệ theo schema V2, F: A → B là stylesheet chuyển V1 sang V2 và G: B → A là stylesheet chuyển V2 sang V1.

Có hai stylesheet mới chỉ chứng minh **có hai phép biến đổi theo hai hướng**. Nó chưa chứng minh:

\[
G(F(x)) = x \quad \forall x \in A
\]

hoặc:

\[
F(G(y)) = y \quad \forall y \in B
\]

Muốn G khôi phục chính xác mọi x, F phải **không làm hai input khác nhau trở thành cùng một output** (injective trên miền cần bảo toàn), hoặc phải mang thêm metadata để phân biệt chúng.

### 2.1. Ví dụ mất thông tin

V1 có amount nhưng không có currency:

~~~xml
<v1:amount>125.00</v1:amount>
~~~

V2 yêu cầu currency. Nếu F tự gán VND:

~~~xml
<v2:total>
    <v2:value>125.00</v2:value>
    <v2:currency>VND</v2:currency>
</v2:total>
~~~

Khi G bỏ currency để quay về V1, nó không biết VND ban đầu là **giá trị suy ra** hay currency do client V2 gửi thật. Nếu V1 không thể chứa currency, cả hai thông tin cùng bị ép về một amount.

Điều ngược lại cũng có thể xảy ra: V1 có legacyCustomerCode, nhưng V2 bỏ trường này. Hai V1 payload chỉ khác mã cũ sẽ cùng trở thành một V2 payload. G không thể suy ra mã ban đầu.

**Kết luận toán học:** khi F không injective, không tồn tại G có thể khôi phục chính xác mọi input. Không thể sửa giới hạn này bằng một XSLT ngược thông minh hơn.

### 2.2. Ba cấp độ round-trip

| Cấp độ | Điều được yêu cầu | Ví dụ |
| --- | --- | --- |
| **Structural round-trip** | XML hợp schema sau khi đổi về | G(F(x)) validate với XSD V1 |
| **Semantic round-trip** | Ý nghĩa nghiệp vụ được bảo toàn | Tổng tiền, currency, customer, status không đổi |
| **Lexical/byte round-trip** | Chuỗi XML/byte giống hệt | Giữ whitespace, prefix, quotes và serialization |

XSLT thường hướng tới **semantic/structural mapping**, không bảo đảm byte-for-byte. XML Infoset tương đương không có nghĩa serialization giống nhau về prefix, whitespace hay thứ tự attributes.

Chỉ nên tuyên bố reversible trên **tập subset được định nghĩa**, với bất biến cụ thể. Ví dụ: V2 payload chỉ reversible về V1 khi currency là VND, channel là giá trị mặc định và không có extension fields.

## 3. Thiết kế contract V1/V2

### 3.1. V1 request/response (trích đoạn XSD)

~~~xml
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           targetNamespace="urn:example:orders:v1"
           elementFormDefault="qualified">
  <xs:element name="CreateOrderRequest">
    <xs:complexType><xs:sequence>
      <xs:element name="customerId" type="xs:string"/>
      <xs:element name="amount" type="xs:decimal"/>
    </xs:sequence></xs:complexType>
  </xs:element>
  <xs:element name="CreateOrderResponse">
    <xs:complexType><xs:sequence>
      <xs:element name="orderId" type="xs:string"/>
      <xs:element name="accepted" type="xs:boolean"/>
    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>
~~~

### 3.2. V2 request/response (trích đoạn XSD)

~~~xml
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           targetNamespace="urn:example:orders:v2"
           elementFormDefault="qualified">
  <xs:element name="CreateOrderRequest">
    <xs:complexType><xs:sequence>
      <xs:element name="customer">
        <xs:complexType><xs:sequence>
          <xs:element name="id" type="xs:string"/>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="total">
        <xs:complexType><xs:sequence>
          <xs:element name="value" type="xs:decimal"/>
          <xs:element name="currency" type="xs:string"/>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="channel" type="xs:string"/>
    </xs:sequence></xs:complexType>
  </xs:element>
  <xs:element name="CreateOrderResponse">
    <xs:complexType><xs:sequence>
      <xs:element name="order">
        <xs:complexType><xs:sequence>
          <xs:element name="id" type="xs:string"/>
          <xs:element name="status" type="xs:string"/>
        </xs:sequence></xs:complexType>
      </xs:element>
    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>
~~~

Đây là schema rút gọn cho ví dụ. Khi dùng thật cần định nghĩa pattern/length cho IDs, currency code, decimal scale và status enumeration, sau đó generate JAXB classes từ đúng schema.

### 3.3. Bảng mapping

| V1 | V2 | Quy tắc |
| --- | --- | --- |
| customerId | customer/id | Copy sau validation |
| amount | total/value | Chuyển decimal, không dùng float |
| Không có currency | total/currency | Default VND theo legacy agreement hoặc reject |
| Không có channel | channel | Default LEGACY_API theo policy |
| orderId | order/id | Copy identifier |
| accepted | order/status | Mapping boolean ↔ enum chỉ trên subset được định nghĩa |

Mọi default là một **quyết định nghiệp vụ có chủ sở hữu**, không chỉ là chi tiết XSLT. Phải ghi rõ vì sao client legacy có thể nhận currency/channel/status nào.

## 4. XSLT request: chuyển V1 sang V2

Ví dụ dùng XSLT 1.0 syntax để phù hợp với nhiều JAXP TransformerFactory mặc định trong Java:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:v1="urn:example:orders:v1"
    xmlns:v2="urn:example:orders:v2"
    exclude-result-prefixes="v1">
  <xsl:output method="xml" encoding="UTF-8"
              omit-xml-declaration="yes"/>
  <xsl:template match="/">
    <v2:CreateOrderRequest>
      <v2:customer>
        <v2:id>
          <xsl:value-of select="/v1:CreateOrderRequest/v1:customerId"/>
        </v2:id>
      </v2:customer>
      <v2:total>
        <v2:value>
          <xsl:value-of select="/v1:CreateOrderRequest/v1:amount"/>
        </v2:value>
        <v2:currency>VND</v2:currency>
      </v2:total>
      <v2:channel>LEGACY_API</v2:channel>
    </v2:CreateOrderRequest>
  </xsl:template>
</xsl:stylesheet>
~~~

Các điểm quan trọng:

- Prefix trong source và stylesheet phải ánh xạ tới đúng namespace URI. **Prefix không phải identity**; old và v1 có thể cùng namespace.
- XPath chọn theo **QName**, không theo chuỗi prefix nhìn thấy trên wire.
- xsl:value-of tạo text node; nó không xác minh decimal lexical value hoặc currency code.
- Stylesheet tạo currency/channel cố định, vì thế output chỉ phù hợp với policy legacy đã xác định.
- XSLT không tự kiểm tra XSD. Validate payload nguồn và payload kết quả theo schema/policy ở vị trí được thiết kế.

### 4.1. Không dùng local-name() bừa bãi

Một shortcut nguy hiểm:

~~~xml
<xsl:value-of select="//*[local-name()='customerId']"/>
~~~

Nó có thể chọn nhầm element customerId trong namespace khác hoặc node lồng bên trong. Với contract versioning, dùng namespace-aware QName rõ ràng. Nếu hỗ trợ nhiều source namespaces, khai báo mappings tường minh và test collision.

## 5. XSLT response: chuyển V2 về V1

Response mapping là stylesheet khác, không tự đảo ngược stylesheet request:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:v1="urn:example:orders:v1"
    xmlns:v2="urn:example:orders:v2"
    exclude-result-prefixes="v2">
  <xsl:output method="xml" encoding="UTF-8"
              omit-xml-declaration="yes"/>
  <xsl:template match="/">
    <v1:CreateOrderResponse>
      <v1:orderId>
        <xsl:value-of select="/v2:CreateOrderResponse/v2:order/v2:id"/>
      </v1:orderId>
      <v1:accepted>
        <xsl:choose>
          <xsl:when
              test="/v2:CreateOrderResponse/v2:order/v2:status = 'ACCEPTED'
                    or /v2:CreateOrderResponse/v2:order/v2:status = 'COMPLETED'">
            <xsl:text>true</xsl:text>
          </xsl:when>
          <xsl:otherwise><xsl:text>false</xsl:text></xsl:otherwise>
        </xsl:choose>
      </v1:accepted>
    </v1:CreateOrderResponse>
  </xsl:template>
</xsl:stylesheet>
~~~

Mapping trên định nghĩa accepted=true cho hai status cụ thể, còn lại false. Nó **không giữ được** sự phân biệt giữa REJECTED, FAILED, CANCELLED, PENDING_REVIEW nếu V1 chỉ có boolean. Nếu V1 client cần status chi tiết, phải mở rộng contract V1 hoặc trả compatibility fault rõ ràng; không giả vờ boolean truyền đủ semantics.

## 6. Tích hợp PayloadTransformingInterceptor

Class thuộc package:

~~~java
org.springframework.ws.server.endpoint.interceptor.PayloadTransformingInterceptor
~~~

API có setRequestXslt(Resource) cho request, setResponseXslt(Resource) cho response, handleRequest(...) và handleResponse(...). Hai stylesheet optional riêng lẻ, nhưng **ít nhất một trong hai phải được cấu hình**. Interceptor thuộc endpoint mapping chain; chỉ gắn nó vào mapping phục vụ legacy endpoint để không áp dụng nhầm cho V2 traffic. [PayloadTransformingInterceptor API 4.1.1](https://docs.spring.io/spring-ws/docs/4.1.1/api/org/springframework/ws/server/endpoint/interceptor/PayloadTransformingInterceptor.html)

### 6.1. Khai báo interceptor bằng Java

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.ws.server.endpoint.interceptor.PayloadTransformingInterceptor;

@Configuration
public class LegacyOrderTransformationConfiguration {
    @Bean
    public PayloadTransformingInterceptor legacyOrderTransformer() {
        PayloadTransformingInterceptor interceptor =
                new PayloadTransformingInterceptor();
        interceptor.setRequestXslt(
                new ClassPathResource("xslt/v1-to-v2.xsl"));
        interceptor.setResponseXslt(
                new ClassPathResource("xslt/v2-to-v1.xsl"));
        return interceptor;
    }
}
~~~

Bean này tạo interceptor; **chưa tự thêm interceptor vào endpoint mapping nào**. Cần đăng ký trong đúng EndpointMapping/WsConfigurer chain dành cho V1.

~~~java
import java.util.List;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.config.annotation.WsConfigurer;
import org.springframework.ws.server.EndpointInterceptor;

@EnableWs
@Configuration
public class LegacyEndpointMappingConfiguration implements WsConfigurer {
    private final PayloadTransformingInterceptor transformer;

    public LegacyEndpointMappingConfiguration(
            PayloadTransformingInterceptor transformer) {
        this.transformer = transformer;
    }

    @Override
    public void addInterceptors(List<EndpointInterceptor> interceptors) {
        interceptors.add(transformer);
    }
}
~~~

Đoạn WsConfigurer minh họa cách đăng ký vào Spring-WS infrastructure chung. Nếu ứng dụng đồng thời phục vụ V1 và V2, **không áp dụng interceptor global cho mọi mapping**; tạo mapping có phạm vi rõ ràng hoặc cấu hình riêng theo Spring-WS version hiện tại. Tài liệu Spring-WS cho biết có thể tạo mapping dành cho message format cũ rồi gắn transformer vào mapping đó.

### 6.2. Endpoint nhận V2 sau khi request đã transform

~~~java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

@Endpoint
public class OrderV2Endpoint {
    private static final String V2_NS = "urn:example:orders:v2";
    private final OrderApplicationService orders;

    public OrderV2Endpoint(OrderApplicationService orders) {
        this.orders = orders;
    }

    @PayloadRoot(namespace = V2_NS, localPart = "CreateOrderRequest")
    @ResponsePayload
    public CreateOrderResponseV2 create(
            @RequestPayload CreateOrderRequestV2 request) {
        return orders.create(request);
    }
}
~~~

**Lưu ý quan trọng:** endpoint mapping được dùng để chọn endpoint/interceptor chain dựa trên thông điệp ban đầu. Với legacy request có root QName V1, kiến trúc phải có **mapping nhận biết V1** áp dụng transformer rồi chuyển tới xử lý V2; chỉ thêm @PayloadRoot V2 endpoint không tự bảo đảm V1 được dispatch đến đó. Tùy cấu hình mapping, cần endpoint mapping/interceptor cụ thể hoặc adapter phù hợp. Hãy integration test dispatch thật, không chỉ test stylesheet độc lập.

### 6.3. Luồng request/response

~~~mermaid
sequenceDiagram
    participant C as Legacy SOAP client V1
    participant M as Endpoint mapping V1
    participant X as PayloadTransformingInterceptor
    participant E as V2 endpoint
    participant D as Domain service
    C->>M: SOAP Body QName V1
    M->>X: Chọn legacy mapping
    X->>X: requestXslt V1 → V2
    X->>E: Dispatch theo flow compatibility
    E->>D: JAXB V2 request
    D-->>E: V2 response
    E-->>X: V2 SOAP response payload
    X->>X: responseXslt V2 → V1
    X-->>C: Response V1
~~~

Sơ đồ nêu mục tiêu kiến trúc, không thay thế kiểm chứng endpoint mapping và interceptor lifecycle. PayloadTransformer xử lý **payload**, không tự chuyển SOAP Header, HTTP headers, SOAPAction, WS-Addressing Action hay security tokens.

## 7. Không phải mọi phần SOAP contract đều nằm trong payload XSLT

~~~text
HTTP headers / transport metadata
  └── SOAP Envelope
       ├── SOAP Header
       │    ├── WS-Addressing Action / To / MessageID
       │    ├── WS-Security Timestamp / Signature / tokens
       │    └── Custom partner headers
       └── SOAP Body (payload XML)
            └── Request/Response element được XSLT chuyển đổi
~~~

| Thành phần | Tự đổi bằng payload XSLT? | Cách xử lý |
| --- | --- | --- |
| SOAP Body payload | **Có** | requestXslt/responseXslt |
| SOAP Header custom | Không | Interceptor/header mapper riêng, test QName |
| WS-Addressing Action | Không | Action mapping/callback hoặc header interceptor |
| HTTP SOAPAction/Content-Type | Không | Transport/binding configuration |
| WS-Security Signature | Không thể tùy tiện sửa | Verify nguồn trước transform; bảo vệ message cuối sau transform |
| MTOM attachment | Không nên giả định | Attachment-aware processing riêng, test MIME/wire |
| SOAP Fault detail | Không tự áp response XSLT | Fault mapping/resolver riêng |

### 7.1. XSLT và WS-Security signature

Nếu XML payload đã được ký và stylesheet thay đổi node, signature references/digest có thể không còn hợp lệ. Pipeline cần quy định:

1. Parse SOAP/XML an toàn.
2. **Xác minh WS-Security** theo policy đối với đúng message được gửi.
3. Chuyển payload XML bằng XSLT sau khi nội dung nguồn được xác thực.
4. Validate payload kết quả với contract đích.
5. Xử lý endpoint/domain.
6. Transform response rồi tạo WS-Security protection trên dữ liệu cuối cùng theo outbound policy.

Đây là nguyên tắc, không phải cam kết interceptor order mặc định của mọi Spring-WS configuration. Phải đăng ký và integration test thứ tự thật. Không transform signed Body trước khi verify nếu policy yêu cầu signature bảo vệ XML gốc; không sửa signed Header mà không có cơ chế xác thực/re-sign.

## 8. Đánh giá khả năng đảo ngược

| Câu hỏi | Nếu câu trả lời là “không” | Hệ quả |
| --- | --- | --- |
| Mỗi trường source có nơi chứa trong đích không? | Bị bỏ hoặc cần extension metadata | Không thể khôi phục source đầy đủ |
| Một giá trị source ánh xạ duy nhất sang một giá trị đích? | Nhiều giá trị gộp vào một | Mất injectivity |
| Miền kiểu dữ liệu có tương đương? | Destination hẹp hơn | Overflow, truncation hoặc reject |
| Cardinality có tương thích? | Một thành nhiều/ nhiều thành một | Cần aggregation/splitting |
| Optional/nil/default có phân biệt? | Nhiều trạng thái thành một | Mất distinction |
| Enum có bao phủ đầy đủ? | Giá trị mới không biểu diễn ở schema cũ | Reject hoặc lossy fallback |
| Namespace/extension có giữ? | Bị flatten/strip | Mất provenance/version |
| Date/time/decimal giữ precision/zone? | Làm tròn hoặc đổi timezone | Semantic drift |

### 8.1. Optional, absent, empty và nil

~~~xml
<!-- Element bị thiếu -->
<v1:Customer/>

<!-- Element có nội dung rỗng -->
<v1:middleName></v1:middleName>

<!-- Element nil nếu XSD cho phép nillable -->
<v1:middleName xsi:nil="true"
               xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>
~~~

Nếu XSLT dùng xsl:value-of rồi sinh element rỗng cho cả ba trường hợp, nó có thể làm **mất distinction** giữa “không cung cấp”, “rỗng có chủ đích” và “nil”. Điều này ảnh hưởng PATCH-like semantics, defaults và validation.

### 8.2. Decimal, precision và rounding

xs:decimal không nên chuyển qua floating point binary nếu cần bảo toàn chính xác tiền tệ:

~~~xml
<v1:amount>12.3400</v1:amount>
~~~

Giá trị số có thể bằng 12.34, nhưng lexical form/scale 12.3400 có thể mang ý nghĩa accounting/reporting. Nếu V2 dùng decimal scale 2, cần quy định làm tròn hay reject; đừng để serializer tự mất scale mà không có policy.

### 8.3. Date/time và timezone

xs:dateTime có thể có hoặc không có timezone. Nếu transform chuẩn hóa mọi giá trị về UTC, round-trip có thể không giữ lexical form ban đầu. Nếu semantics là instant toàn cầu, chuẩn hóa có thể đúng; nếu semantics là local appointment time, offset/timezone có thể quan trọng.

### 8.4. Enumeration evolution

V1 có NEW, ACCEPTED, REJECTED; V2 thêm ON_HOLD, CANCELLED, PARTIALLY_FULFILLED. V1 client không biết các giá trị mới. Lựa chọn gồm:

- Map một tập status mới về status cũ gần nghĩa nhất, chấp nhận mất phân biệt.
- Reject với compatibility fault nếu không thể biểu diễn.
- Mở rộng V1 bằng optional extension trước khi phát thêm status.
- Cung cấp status detail qua operation/version mới.

Không map mọi giá trị chưa biết về REJECTED; điều đó biến trạng thái chờ review thành business rejection giả.

## 9. Bảo toàn thông tin bằng extension hoặc sidecar

| Chiến lược | Cách hoạt động | Đánh đổi |
| --- | --- | --- |
| **Reject unsupported input** | Không chấp nhận giá trị không biểu diễn được | An toàn, rõ nghĩa, giảm compatibility |
| **Extension element** | Giữ dữ liệu trong namespace extension/versioned bag | Cần contract cho phép extension, validation và trust |
| **Sidecar metadata** | Lưu raw legacy fields/version/source payload cạnh model canonical | Cần storage, provenance, retention và access policy |

Ví dụ extension:

~~~xml
<v2:CreateOrderRequest
    xmlns:v2="urn:example:orders:v2"
    xmlns:legacy="urn:example:orders:legacy-extension">
    <v2:customer>...</v2:customer>
    <v2:total>...</v2:total>
    <v2:extensions>
        <legacy:originalCustomerCode>OLD-42</legacy:originalCustomerCode>
    </v2:extensions>
</v2:CreateOrderRequest>
~~~

Đây là minh họa contract; XSD V2 phải khai báo extension structure tương ứng. Nếu giữ raw XML/extension content, xác định namespace allowlist, kích thước, schema validation, bảo vệ dữ liệu và không cho nhúng cấu hình/command không tin cậy.

Sidecar chỉ giúp round-trip nếu metadata không bị mất khi lưu/queue/retry, gắn đúng request/version/caller, không bị ghi đè, có retention đủ lâu và được kiểm soát integrity/authorization. Nếu sidecar không được lưu hoặc response tạo từ context khác, không có gì bảo đảm khôi phục giá trị cũ.

## 10. Kiểm thử round-trip có ý nghĩa

Đừng chỉ viết test V1 → V2 → V1 rồi so XML string. Test nên tách:

1. **Schema validation:** input hợp XSD V1, output F(x) hợp XSD V2, output G(y) hợp XSD V1.
2. **Field-level mapping:** từng QName/value ánh xạ đúng bảng mapping.
3. **Semantic invariant:** customer, amount/currency, status và identifiers giữ đúng nghĩa trong subset.
4. **Loss-boundary tests:** giá trị không biểu diễn được bị reject hoặc được giữ có chủ ý, không biến mất im lặng.

### 10.1. Round-trip trong subset reversible

Định nghĩa miền \(A_r \subseteq A\) là V1 inputs thỏa:

- Amount là decimal hợp lệ.
- Currency policy luôn là VND.
- Không có legacy extension fields phải giữ ngoài V2.
- Giá trị customerId có thể ánh xạ nguyên vẹn.

Khi đó mới kiểm tra:

\[
G(F(x)) \equiv x \quad \forall x \in A_r
\]

Ký hiệu tương đương là **semantic equivalence theo các fields contract bảo đảm**, không bắt buộc XML bytes giống nhau. Ghi rõ field nào thuộc equivalence relation.

### 10.2. Test chứng minh không thể đảo ngược

~~~text
x1 = (customerId=C42, amount=100, legacyCode=L-A)
x2 = (customerId=C42, amount=100, legacyCode=L-B)

F(x1) = (customerId=C42, amount=100, currency=VND)
F(x2) = (customerId=C42, amount=100, currency=VND)

F(x1) = F(x2), while x1 != x2
=> F is not injective on this domain
=> no inverse can restore both x1 and x2 exactly
~~~

Đây là **test chứng minh information loss**, không phải lỗi XSLT engine. Nó cần xuất hiện như boundary/acceptance test khi kiến trúc tuyên bố round-trip chỉ hỗ trợ subset.

## 11. Test XSLT trong Java và Spring

| Test | Chứng minh |
| --- | --- |
| **XSLT unit test** | XPath/QName, mapping fields, defaults và output XML |
| **XSD validation test** | Kết quả stylesheet phù hợp schema đích |
| **Round-trip semantic test** | Invariants được bảo toàn trong subset |
| **Loss-boundary test** | Trường không biểu diễn được bị xử lý rõ |
| **Spring endpoint integration** | Đúng mapping/interceptor, request và response được transform |
| **Cross-version compatibility** | Legacy client thực tế hiểu response và V2 handler nhận đúng request |

### 11.1. XSLT unit test bằng JAXP

~~~java
import java.io.StringReader;
import java.io.StringWriter;
import javax.xml.transform.Source;
import javax.xml.transform.Templates;
import javax.xml.transform.Transformer;
import javax.xml.transform.TransformerFactory;
import javax.xml.transform.stream.StreamResult;
import javax.xml.transform.stream.StreamSource;

static String transform(Source stylesheet, String xml)
        throws Exception {
    TransformerFactory factory = TransformerFactory.newInstance();
    Templates templates = factory.newTemplates(stylesheet);
    Transformer transformer = templates.newTransformer();

    StringWriter output = new StringWriter();
    transformer.transform(
            new StreamSource(new StringReader(xml)),
            new StreamResult(output));
    return output.toString();
}
~~~

Đây là helper test minh họa; test thật phải quản lý đúng lifecycle của Source và dùng namespace-aware XML parser cho assertions. Không assert prefix substring; parse output rồi assert namespace URI/local name.

### 11.2. Validate output bằng schema

~~~java
import java.io.StringReader;
import javax.xml.XMLConstants;
import javax.xml.transform.stream.StreamSource;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;

static void validateXml(String xml, Schema schema) throws Exception {
    var validator = schema.newValidator();
    validator.validate(new StreamSource(new StringReader(xml)));
}

SchemaFactory schemaFactory = SchemaFactory.newInstance(
        XMLConstants.W3C_XML_SCHEMA_NS_URI);
schemaFactory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
schemaFactory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
~~~

Ví dụ này chỉ là kiểm tra schema cơ bản. Nếu schema có xs:include/xs:import, cấu hình LSResourceResolver/catalog để resolve **local trusted schemas** thay vì mở quyền fetch URL tùy ý. Kiểm tra properties với XML provider thật.

### 11.3. Spring-WS integration test

MockWebServiceClient có thể gửi SOAP request vào server application context. Để test transformer:

1. Gửi Body V1 với QName cũ.
2. Xác minh endpoint V2 nhận cấu trúc V2 hoặc domain service nhận đúng V2 DTO.
3. Cho endpoint trả V2 response.
4. Xác minh SOAP Body client nhận có QName/cấu trúc V1.
5. Gửi request không hỗ trợ và kiểm tra Fault/validation policy.

Test phải đảm bảo request đi đúng endpoint mapping chứa interceptor. MockWebServiceClient kiểm message pipeline Spring-WS; cross-platform test vẫn cần client legacy thật hoặc fixture từ toolchain đối tác.

## 12. Namespace, QName và routing

~~~text
V1: {urn:example:orders:v1}CreateOrderRequest
V2: {urn:example:orders:v2}CreateOrderRequest
~~~

Hai element có local name giống nhau nhưng **khác QName**. Nếu mapping chọn version dựa trên QName, không chỉ đổi xmlns trong serializer mà bỏ kiểm tra contract.

### 12.1. Namespace collision

~~~xml
<a:CreateOrderRequest xmlns:a="urn:example:orders:v1">
    <b:customerId xmlns:b="urn:example:identity:v1">C-42</b:customerId>
</a:CreateOrderRequest>
~~~

XPath chọn v1:customerId theo namespace orders:v1 sẽ không match identity:v1, dù local name giống nhau. Đây là hành vi đúng. Khi mapping, xác định QName của từng field.

### 12.2. Routing phải xác định version trước transformation

Có thể chọn version qua root payload QName, SOAPAction/WS-Addressing Action, endpoint URI riêng hoặc version header được công bố/xác thực. Không để client gửi Header Version=2 nhưng payload V1 rồi server âm thầm chọn mapping V2. Cần policy ưu tiên rõ ràng khi QName, Action và version header mâu thuẫn; test mismatch phải trả lỗi, không chọn mapping ngẫu nhiên.

## 13. Thứ tự validation và transformation

~~~mermaid
flowchart TD
    A["SOAP request V1"] --> B["Safe XML/SOAP parsing"]
    B --> C["Transport + WS-Security validation"]
    C --> D["Validate source schema/policy V1"]
    D --> E["Select V1 mapping"]
    E --> F["XSLT request: V1 → V2"]
    F --> G["Validate destination schema/policy V2"]
    G --> H["V2 JAXB / @Endpoint"]
    H --> I["Domain service"]
    I --> J["V2 response"]
    J --> K["Validate V2 response"]
    K --> L["XSLT response: V2 → V1"]
    L --> M["Validate V1 response"]
    M --> N["Outbound WS-Security / SOAP response"]
~~~

Đây là logic kiểm soát, không mặc định Spring-WS tự có đủ ba bước validation. Có thể dùng PayloadValidatingInterceptor, custom validation hoặc pipeline riêng; cấu hình scope/ordering phải được kiểm tra. PayloadTransformingInterceptor không tự bảo đảm schema validation trước/sau transform.

### 13.1. Fault mapping

Nếu request V1 không thể chuyển sang V2 vì currency/status không hỗ trợ:

- Không tạo payload V2 nửa vời rồi để lỗi sâu trong service.
- Không đổi giá trị không nhận diện thành status hợp lệ tùy tiện.
- Trả SOAP Fault code/detail theo contract V1, không rò stack trace/stylesheet path.
- Log version, QName, mapping ID, correlation và error category đã lọc.

handleFault của PayloadTransformingInterceptor không có nghĩa mọi SOAP Fault detail tự được map từ V2 sang V1. Nếu Fault contract/version khác nhau, cần fault transformation/resolver riêng và test độc lập.

## 14. XSLT performance và quản lý stylesheet

XSLT có thể tạo DOM/result tree lớn tùy transformer/provider. Với payload nhỏ thường chấp nhận được; với SOAP payload vài chục MB cần đo memory/time và kiểm tra có materialize toàn bộ payload hay không.

### 14.1. Compile stylesheet và reuse

Trong JAXP, Templates là representation đã chuẩn bị để tạo Transformer; Transformer có trạng thái theo lần transform và không nên chia sẻ đồng thời giữa thread. PayloadTransformingInterceptor quản lý transformation theo API Spring-WS; custom transformer nên compile templates một lần và tạo transformer phù hợp cho từng invocation.

### 14.2. XSLT version và TransformerFactory

XSLT 1.0 được hỗ trợ rộng trong JAXP mặc định; **không mặc định JVM TransformerFactory hỗ trợ XSLT 2.0/3.0**. XSLT 3.0 là W3C Recommendation và có khả năng streaming, nhưng cần processor hỗ trợ tương ứng. [W3C XSLT 3.0 Recommendation](https://www.w3.org/TR/xslt-30/)

Nếu stylesheet dùng xsl:for-each-group, map/array hoặc streaming constructs, phải chọn/version hóa processor và test runtime. Không phát triển theo XSLT 3.0 rồi deploy vào runtime chỉ có XSLT 1.0.

### 14.3. Quản lý stylesheet

Stylesheet nên là resource tin cậy, đóng gói/versioned cùng deployment hoặc quản lý qua artifact pipeline. Không cho client truyền URI/path stylesheet để server tải file hoặc URL; điều đó có thể mở đường truy cập local files/SSRF.

## 15. An toàn XML và XSLT

XSLT xử lý XML từ client nên có các rủi ro:

- **XXE/DTD:** parser có thể truy cập external entities nếu không harden.
- **External document access:** XSLT document() có thể đọc file hoặc fetch URL nếu processor cho phép.
- **External stylesheet import/include:** xsl:include/xsl:import có thể nạp resource không tin cậy.
- **Resource exhaustion:** recursive templates, huge input, large intermediate trees hoặc pathological XPath.
- **Data leakage:** stylesheet copy trường bí mật sang response legacy hoặc log.
- **Signature invalidation:** thay payload sau khi ký làm digest/signature không còn đúng.

Biện pháp:

1. Hardening parser/TransformerFactory theo provider: chặn external DTD, external stylesheet, external schema và document() khi không cần.
2. Dùng classpath/local allowlisted resources cho stylesheets và schema imports.
3. Giới hạn payload size/depth, execution time và concurrency.
4. Validate source và target schemas; reject unknown fields/values theo policy.
5. Tách quyền truy cập stylesheet/transform configuration khỏi dữ liệu request.
6. Không log raw XML có PII/credentials; audit version/mapping ID và result category.
7. Đặt thứ tự WS-Security verification → transformation → outbound signing theo policy.

JAXP security attributes khác nhau giữa implementations. Kiểm tra đúng TransformerFactory provider/class/version trong integration test; đừng giả định một property được mọi provider hỗ trợ.

## 16. Khi nào dùng XSLT, khi nào dùng adapter code?

| Dấu hiệu | XSLT phù hợp | Adapter Java/domain mapper phù hợp |
| --- | --- | --- |
| XML tree mapping rõ, nhiều field rename/move | Có | Có thể, nhưng dài dòng |
| Chỉ đổi namespace/nesting và giữ semantics | Rất phù hợp | Phù hợp |
| Cần tra database hoặc gọi service | Không nên làm trong stylesheet | Phù hợp qua application service |
| Cần business rule/authorization phức tạp | Không | Bắt buộc ở domain/application |
| Mapping cần review/version độc lập | Phù hợp | Phù hợp nếu mapper modular |
| Payload lớn/streaming | Phải xác minh processor/memory | Có thể dùng streaming XML API |
| Cần giữ source provenance/unknown extensions | Cần mapping tường minh | Model + metadata thường rõ hơn |

Không đặt business decisions vào XSLT chỉ vì nó có thể dùng XPath/conditional logic. Currency default, risk classification hoặc authorization nên do **domain policy/application service** quyết định; stylesheet tập trung cấu trúc và mapping thuần.

## 17. Versioning strategy và vòng đời tương thích

| Thành phần | Nên version hóa |
| --- | --- |
| WSDL/XSD | Namespace/version, schema artifact và compatibility notes |
| XSLT request | Source version → target canonical version |
| XSLT response | Canonical version → client version |
| Mapping rules | Mapping ID, owner, defaults, lossy fields |
| Test fixtures | Payload hợp lệ, biên, malformed, unknown enum |
| Metrics | Request counts theo contract/mapping version |
| Deprecation | Ngày ngừng hỗ trợ client version cũ và migration guide |

### 17.1. Mapping graph

~~~mermaid
flowchart LR
    V1["Client V1"] --> A["V1 → Canonical V3"]
    V2["Client V2"] --> B["V2 → Canonical V3"]
    A --> C["Canonical V3 endpoint/domain"]
    B --> C
    C --> D["V1 response mapper"]
    C --> E["V2 response mapper"]
    D --> V1
    E --> V2
~~~

Canonical model có thể giảm số mapping pair so với viết V1↔V2, V2↔V3, V1↔V3. Nhưng nó cũng có thể thành schema mẫu số chung làm mất semantics độc lập. Canonical model cần ownership, invariants và extension policy như public contract.

### 17.2. Deprecation và telemetry

Theo dõi số request theo V1/V2, partner, operation và mapping ID. Khi V1 không còn dùng:

1. Thông báo deprecation và thời hạn.
2. Cung cấp WSDL/XSD mới và fixtures.
3. Quan sát traffic thật, tìm client còn V1.
4. Chuyển client theo partner, có rollback.
5. Ngừng mapping V1 khi usage và thỏa thuận đối tác cho phép.

Không xóa stylesheet chỉ dựa vào ngày trong tài liệu mà chưa có bằng chứng usage.

## 18. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| No endpoint found với request V1 | Mapping không nhận QName cũ | Endpoint mapping selection/interceptor scope |
| XSLT chạy nhưng endpoint không thấy V2 | Chain/dispatch không chuyển tới handler | Thứ tự mapping/adapter |
| customerId thành rỗng | XPath namespace/prefix sai | Namespace URI/QName source |
| Field cùng local name bị lấy nhầm | Dùng local-name() không có namespace filter | Namespace-aware XPath |
| Response vẫn là V2 | responseXslt chưa cấu hình/không nằm đúng chain | Interceptor response phase |
| V1 client nhận SOAP Fault V2 | Fault mapping chưa thiết kế | Resolver/fault contract riêng |
| Currency bị gán sai | Default hardcode trong XSLT | Versioned business policy |
| Status mới thành false | Enum V2 không ánh xạ được boolean V1 | Unknown enum policy/reject |
| Round-trip test thất bại | Mapping lossy, precision/time/status distinctions | Semantic invariants |
| Round-trip string khác dù nghĩa giống | Prefix/whitespace/serialization khác | Compare parsed XML/semantic values |
| Signature invalid sau transform | Signed node bị thay đổi | Verify trước, re-sign sau |
| Schema validation thất bại | Output không hợp XSD đích | Validate destination |
| Deploy lỗi XSLT feature | Runtime không hỗ trợ stylesheet version | TransformerFactory/processor |
| CPU/RAM tăng theo payload | DOM/XSLT tree lớn, recursion | Bounds, profiler, processor |
| External URL được truy cập | document() hoặc resolver mở network | Disable external access, catalog |

## 19. Bài tập thực hành

1. Viết v1-to-v2.xsl ánh xạ customerId sang customer/id, amount sang total/value, thêm currency/channel theo policy. Validate output bằng XSD V2.
2. Viết response stylesheet đổi order ID/status về V1; liệt kê V2 statuses không biểu diễn đầy đủ bằng boolean.
3. Tạo hai V1 documents chỉ khác legacy code bị bỏ; xác minh chúng tạo cùng V2 result và giải thích vì sao không có inverse tổng quát.
4. Định nghĩa subset V1 (currency VND, không extension, status mapping xác định). Test semantic equivalence G(F(x)) ≡ x cho fixtures và edge values.
5. Tạo hai child elements cùng local name nhưng khác namespace URI; chứng minh XPath namespace-aware chọn đúng node.
6. Chuyển đổi absent/empty/xsi:nil; quy định mapping không làm mất distinction trái contract.
7. Thêm V2 status ON_HOLD; chọn reject, extension hoặc lossy mapping có chủ ý và viết test.
8. Tích hợp interceptor vào legacy mapping; gửi V1 request và xác minh endpoint V2 xử lý, response trở về V1.
9. Gửi signed V1 SOAP Body; verify trước transform và ký response trên payload V1 cuối cùng; tamper source phải bị từ chối.
10. Thử external entity, document() URL và stylesheet import không allowlist trong lab; xác minh chúng bị chặn.
11. Đưa stylesheet dùng XSLT 2.0/3.0 vào runtime chỉ hỗ trợ XSLT 1.0; chọn processor đúng.
12. Thiết lập metrics theo namespace/mapping ID và lập kế hoạch ngừng hỗ trợ V1.

## 20. Checklist trước khi phát hành stylesheet

| Hạng mục | Điều kiện đạt |
| --- | --- |
| **Contract source/target** | WSDL/XSD, namespace, QName và schema version xác định |
| **Mapping direction** | Request và response có stylesheet/quy tắc riêng |
| **Mapping ownership** | Mỗi field rename/drop/default/derive có lý do và owner |
| **Loss analysis** | Optional/nil/enum/precision/timezone và fields bị bỏ được liệt kê |
| **Reversibility** | Nêu subset reversible và semantic invariants; không tuyên bố đảo ngược toàn phần nếu không injective |
| **Schema validation** | Validate source và target ở đúng pipeline stage |
| **Endpoint routing** | V1 mapping chọn đúng legacy chain; V2 traffic không bị transform nhầm |
| **Fault handling** | Fault contract V1/V2 và transform path được test |
| **WS-Security** | Verify trước khi biến đổi signed payload; outbound security trên message cuối |
| **Headers/transport** | Action, SOAPAction, custom headers, MTOM, HTTP metadata có mapping riêng nếu cần |
| **Namespace handling** | XPath chọn QName, không dựa prefix hoặc local-name tùy tiện |
| **XSLT processor** | Version/TransformerFactory được pin và test runtime |
| **Resource/security** | XXE, document(), include/import, payload size/depth/time được giới hạn |
| **Round-trip** | Structural/semantic tests, loss-boundary tests và fixtures edge cases |
| **Operations** | Mapping version metrics, redacted logs, deprecation/rollback plan |

## 21. Tài liệu tham khảo

- [Spring Web Services Reference 4.1.4 — Using PayloadTransformingInterceptor](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/): chuyển request/response XML bằng XSLT và áp dụng theo endpoint mapping phục vụ contract version cũ.
- [Spring-WS PayloadTransformingInterceptor API 4.1.1](https://docs.spring.io/spring-ws/docs/4.1.1/api/org/springframework/ws/server/endpoint/interceptor/PayloadTransformingInterceptor.html): setRequestXslt, setResponseXslt, handleRequest và handleResponse.
- [W3C XSL Transformations (XSLT) Version 3.0](https://www.w3.org/TR/xslt-30/): XSLT, streaming và modular stylesheet; cần processor hỗ trợ để dùng XSLT 3.0.
- [W3C XPath 3.1](https://www.w3.org/TR/xpath-31/): biểu thức chọn node và XML data model.
- [W3C XML Schema 1.1](https://www.w3.org/TR/xmlschema11-1/): cấu trúc, kiểu dữ liệu và validation cho XML contracts.
- [Java JAXP — TransformerFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/transform/TransformerFactory.html): tạo Templates/Transformer và thuộc tính truy cập external resources.

**Kết luận:** PayloadTransformingInterceptor giúp **SPRING_WEB_SERVICES** duy trì tương thích nhiều phiên bản SOAP contract bằng cách chuyển request và response XML qua hai stylesheet XSLT. Nhưng có V1 → V2 và V2 → V1 chỉ chứng minh hai chiều mapping tồn tại; phép biến đổi chỉ đảo ngược chính xác trên miền dữ liệu mà nó **không làm mất distinction** hoặc có lưu đủ metadata để khôi phục. Muốn phát hành an toàn, phải có bảng mapping theo QName, phân tích optional/nil/enum/precision/timezone, validate schema nguồn và đích, kiểm tra endpoint mapping, SOAP Header/security riêng, round-trip semantic trên subset và negative tests cho thông tin không biểu diễn được. Khi giới hạn được công bố rõ, XSLT trở thành lớp compatibility có thể version hóa, đo lường và loại bỏ có kế hoạch thay vì một nơi âm thầm làm mất dữ liệu.
