# Lỗi validation, SOAP Fault và nội dung phản hồi có thể công bố

Trong một dịch vụ **Spring Web Services (Spring-WS)** theo hướng **contract-first**, XSD/WSDL giúp client biết phải gửi XML nào, còn server cần xác minh request trước khi xử lý nghiệp vụ. Khi dữ liệu không hợp lệ, dịch vụ không chỉ cần **phát hiện lỗi** mà còn phải trả về **SOAP Fault phù hợp giao thức, ổn định theo hợp đồng và an toàn để công bố cho đối tác**.

Đây là ba công việc khác nhau. Bộ kiểm tra XSD có thể biết một phần tử XML xuất hiện sai vị trí hoặc thiếu dữ liệu; application service có thể biết mã hàng không còn bán; thành phần WS-Security có thể biết chữ ký sai. **Không phải toàn bộ thông tin kỹ thuật của các lỗi đó đều được phép đưa vào SOAP Fault**. Việc phát tán stack trace, tên bảng, nội dung token, dữ liệu người dùng hoặc thông báo nội bộ của parser có thể làm lộ hệ thống mà không giúp client xử lý đúng.

Bài này thuộc chương **Kiểm tra dữ liệu** của module `SPRING_WEB_SERVICES`. Ta kết nối thiết kế XSD/WSDL, JAXB/OXM, endpoint, `PayloadValidatingInterceptor`, `EndpointExceptionResolver`, SOAP Fault 1.1/1.2, XML security, WS-Security, chứng chỉ và kiểm thử tương thích. Các ví dụ dùng Spring-WS 4.x và Java 17+/Jakarta JAXB; mã minh họa được ghi rõ ở những chỗ cần thêm application types hoặc cấu hình dự án.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân loại lỗi **XML parse**, **XSD schema validation**, **JAXB binding**, **business validation**, **authorization**, **WS-Security** và **server failure**.
2. Giải thích cấu trúc SOAP Fault 1.1 so với SOAP Fault 1.2, đặc biệt mã `Client/Sender` và `Server/Receiver`.
3. Cấu hình `PayloadValidatingInterceptor` để từ chối request không hợp lệ nhưng **không công bố raw validation errors**.
4. Thiết kế nội dung lỗi công khai theo **mã ổn định, thông điệp an toàn, correlation ID và danh sách vi phạm có kiểm soát**.
5. Dùng `SoapFaultMappingExceptionResolver` và cơ chế tùy biến fault detail cho lỗi nghiệp vụ.
6. Phân biệt một **WSDL fault được khai báo** với lỗi runtime hoặc fault do interceptor tự phát; không giả định tất cả tự động khớp nhau.
7. Thiết kế retry/không retry cho SOAP client dựa trên loại lỗi mà không suy luận sai về trạng thái transaction.
8. Kiểm thử fault body, detail, namespace, khả năng công bố, bảo mật và tương thích giữa Java/.NET client.

## 1. Tình huống: SubmitOrder sai dữ liệu

Giả sử dịch vụ mua hàng tiếp nhận đơn qua operation `SubmitOrder`. Client gửi:

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
  <soapenv:Body>
    <ord:SubmitOrderRequest>
      <ord:requestId>REQ-2026-0042</ord:requestId>
      <ord:buyerId>BUYER-21</ord:buyerId>
      <ord:items>
        <ord:item>
          <ord:sku>SKU-RED</ord:sku>
          <ord:quantity>0</ord:quantity>
        </ord:item>
      </ord:items>
    </ord:SubmitOrderRequest>
  </soapenv:Body>
</soapenv:Envelope>
~~~

Nếu XSD quy định `quantity` phải từ 1 đến 999, số `0` là lỗi **schema validation**. Không cần truy cập database để biết XML sai hợp đồng.

Bây giờ đổi `quantity` thành `3`, XML hợp XSD, nhưng `SKU-RED` không tồn tại. Đó là **lỗi nghiệp vụ** mà schema cơ bản không thể xác định. Nếu buyer không có quyền đặt hàng, đó là **authorization failure**. Nếu chữ ký SOAP bị sửa, đó là **WS-Security failure**. Nếu database mất kết nối trong lúc ghi đơn, đó là **lỗi hạ tầng**.

Tất cả có thể dẫn tới phản hồi lỗi, nhưng mã, thông điệp, chi tiết công bố và hành động của client phải khác nhau.

### 1.1. Một lỗi cần trả lời ba câu hỏi

| Câu hỏi | Ví dụ | Nơi quyết định |
| --- | --- | --- |
| **Có được xử lý nghiệp vụ không?** | `quantity=0` → không | XSD validator/interceptor |
| **SOAP Fault nên nói gì?** | `INVALID_REQUEST`, “Dữ liệu yêu cầu không hợp lệ” | Error contract và fault handler |
| **Client nên làm gì?** | Sửa quantity, không retry nguyên request vô hạn | Client recovery policy |

Đừng đánh đồng ba câu hỏi. Một bộ validator có thể phát hiện lỗi chính xác nhưng vẫn cần **quy tắc xuất bản thông tin** để không lộ chi tiết nội bộ.

## 2. Các lớp validation và nơi lỗi xuất hiện

Một đường xử lý Spring-WS điển hình:

~~~mermaid
flowchart TD
    A["HTTP/TLS, SOAP message"] --> B{"XML well-formed và SOAP hợp lệ?"}
    B -- "Không" --> X["Parse/transport/protocol error"]
    B -- "Có" --> C["MessageDispatcher: endpoint mapping"]
    C --> D{"Tìm được endpoint?"}
    D -- "Không" --> Y["No endpoint / dispatch error"]
    D -- "Có" --> E["EndpointInterceptor: WS-Security + XSD validation"]
    E --> F{"Thông điệp đủ điều kiện?"}
    F -- "Không" --> Z["Security/validation SOAP Fault"]
    F -- "Có" --> G["EndpointAdapter / JAXB"]
    G --> H["Application service: business rules + authorization"]
    H --> I{"Use case thành công?"}
    I -- "Không" --> J["Exception resolver → SOAP Fault"]
    I -- "Có" --> K["JAXB response / response validation"]
    K --> L["SOAP response qua transport"]
~~~

Đây là sơ đồ phân lớp, không khẳng định **tất cả** lỗi phát sinh đều đi qua cùng `EndpointExceptionResolver` hoặc luôn tạo được một SOAP Fault. Parse/transport lỗi sớm có thể xảy ra **trước khi có endpoint**; lỗi sau khi response đã bắt đầu ghi không phải lúc nào cũng chuyển được thành một fault hoàn chỉnh.

| Loại lỗi | Ví dụ | Thành phần nhận biết | Nhận xét về công bố |
| --- | --- | --- | --- |
| XML không well-formed | Thẻ đóng thiếu, namespace declaration lỗi | XML parser/message factory | Thường chỉ công bố lỗi XML tổng quát |
| SOAP protocol | Envelope namespace sai, Header `mustUnderstand` không được xử lý | SOAP infrastructure | SOAP Fault/protocol error tùy phiên bản |
| XSD schema validation | Thiếu `buyerId`, `quantity=0`, sai `xs:sequence` | `PayloadValidatingInterceptor`/schema validator | Lỗi request; không nên echo raw parser diagnostics |
| JAXB/OXM | Không có root QName, unmarshal/marshal không hỗ trợ | Adapter/JAXB/OXM | Có thể là request sai hoặc lỗi cấu hình server; phải phân loại, không suy từ tên exception |
| Business validation | SKU không tồn tại, quantity vượt hạn mức nội bộ | Application/domain service | Mã nghiệp vụ ổn định, không lộ dữ liệu nhạy cảm |
| Authorization | Buyer không sở hữu đơn | Security policy/application service | Không tiết lộ tài nguyên của người khác |
| WS-Security | Timestamp hết hạn, token/chữ ký sai | Security interceptor | Lý do công khai thường nên tối giản |
| Database/remote service | Timeout, deadlock, downstream unavailable | Application/infrastructure | Lỗi server hoặc kết quả chưa rõ; policy retry riêng |
| Response validation | Server sinh XML trả về sai XSD | Response validator/test | **Lỗi phía server**, không đổ lỗi cho request hợp lệ |
| Network delivery | Client timeout sau commit | Transport/network | Có thể không có SOAP Fault để đọc; cần idempotency |

### 2.1. Schema validation không tương đương business validation

`xs:minInclusive` có thể cấm `quantity=0`, nhưng không biết còn 3 sản phẩm trong kho hay không. `xs:pattern` có thể yêu cầu định dạng `requestId`, nhưng không phát hiện requestId đã dùng với payload khác.

Nên phân trách nhiệm:

- **XSD:** các giới hạn có thể biểu diễn ổn định qua XML type/sequence/cardinality/namespace.
- **Application service:** các bất biến nghiệp vụ theo trạng thái, database và giao dịch.
- **Security:** danh tính, chữ ký, chứng chỉ, quyền thực hiện thao tác.
- **Fault publisher:** chuyển kết quả thất bại thành **một hợp đồng lỗi được phép công bố**, không bê nguyên exception nội bộ.

### 2.2. Validation request và validation response khác nhau

Request sai XSD là điều **client có thể sửa**. Response sai XSD thường là **lỗi triển khai phía server**, vì server đang gửi dữ liệu không đúng hợp đồng. Việc bật validation cho response giúp phát hiện lỗi, nhưng **không mặc định đảm bảo** một SOAP Fault được sinh khi response sai.

Với Spring-WS `PayloadValidatingInterceptor`, request không hợp lệ thường bị dừng và tạo client/sender fault; response không hợp lệ **không tự sinh fault** theo hành vi của interceptor này. Phải có logging, test và chính sách xử lý thích hợp để không trả dữ liệu sai một cách thầm lặng.

## 3. Thiết kế XSD từ đầu: lỗi nào schema có thể phát hiện?

File minh họa `src/main/resources/xsd/orders-v1.xsd`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:ord="urn:example:orders:v1"
    targetNamespace="urn:example:orders:v1"
    elementFormDefault="qualified">

  <xs:simpleType name="RequestIdType">
    <xs:restriction base="xs:string">
      <xs:minLength value="8"/>
      <xs:maxLength value="64"/>
      <xs:pattern value="[A-Za-z0-9._-]+"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:simpleType name="QuantityType">
    <xs:restriction base="xs:positiveInteger">
      <xs:maxInclusive value="999"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:complexType name="ItemType">
    <xs:sequence>
      <xs:element name="sku" type="xs:string"/>
      <xs:element name="quantity" type="ord:QuantityType"/>
    </xs:sequence>
  </xs:complexType>

  <xs:complexType name="ItemsType">
    <xs:sequence>
      <xs:element name="item" type="ord:ItemType"
                  minOccurs="1" maxOccurs="100"/>
    </xs:sequence>
  </xs:complexType>

  <xs:element name="SubmitOrderRequest">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="requestId" type="ord:RequestIdType"/>
        <xs:element name="buyerId" type="xs:string"/>
        <xs:element name="items" type="ord:ItemsType"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <xs:element name="SubmitOrderResponse">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="orderId" type="xs:string"/>
        <xs:element name="status" type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <!-- Chi tiết lỗi công khai dùng trong ví dụ SOAP Fault. -->
  <xs:complexType name="ViolationType">
    <xs:sequence>
      <xs:element name="field" type="xs:string"/>
      <xs:element name="rule" type="xs:string"/>
      <xs:element name="message" type="xs:string"/>
    </xs:sequence>
  </xs:complexType>

  <xs:complexType name="ViolationsType">
    <xs:sequence>
      <xs:element name="violation" type="ord:ViolationType"
                  minOccurs="1" maxOccurs="10"/>
    </xs:sequence>
  </xs:complexType>

  <xs:element name="OrderFault">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="code" type="xs:string"/>
        <xs:element name="message" type="xs:string"/>
        <xs:element name="correlationId" type="xs:string"
                    minOccurs="0"/>
        <xs:element name="violations" type="ord:ViolationsType"
                    minOccurs="0"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

</xs:schema>
~~~

Đây là XSD **học tập**, không phải hợp đồng production đã hoàn thiện. Trong hệ thống thật nên giới hạn `sku`, `buyerId`, mã lỗi và `field` bằng các quy tắc phù hợp; có thể quy định enum cho `code`/`rule` hoặc version lỗi mở rộng. Ví dụ đã giới hạn **số `violation` xuất bản tối đa 10**, nhưng app vẫn phải giới hạn độ dài các chuỗi lỗi và số lượng raw validation errors được xử lý ở nội bộ.

Các yêu cầu được XSD phát hiện:

| XML request | Kết quả |
| --- | --- |
| Có đúng một `SubmitOrderRequest`, một `items` với 1..100 `item`, quantity 1..999 | Hợp lệ về cấu trúc |
| Thiếu `buyerId` | Không hợp lệ vì `xs:sequence` yêu cầu field |
| `quantity=0` | Không hợp lệ vì `xs:positiveInteger` |
| `quantity=1000` | Không hợp lệ vì `maxInclusive=999` |
| `items` rỗng | Không hợp lệ vì `item minOccurs=1` |
| `items` có 101 `item` | Không hợp lệ vì `maxOccurs=100` |
| `buyerId` đứng trước `requestId` | Không hợp lệ vì `xs:sequence` |
| Prefix XML thay đổi nhưng namespace URI giữ nguyên | Có thể vẫn hợp lệ |
| Root `SubmitOrderRequest` mang namespace v2 | Không hợp lệ theo hợp đồng v1 |
| SKU hợp XSD nhưng không tồn tại trong kho | XSD **không biết**; kiểm ở application service |

**Lưu ý:** Việc XSD khai báo `OrderFault` không làm các ngoại lệ Java tự trở thành chi tiết lỗi theo schema này. Hợp đồng fault còn cần WSDL phù hợp và mã tạo `SoapFaultDetail` ở runtime.

## 4. SOAP Fault là gì và khác response thành công ra sao?

Một operation SOAP request-response có hai kết quả quan sát phổ biến:

- **Response thành công**: SOAP Body chứa `SubmitOrderResponse`, khớp global element output trong WSDL.
- **SOAP Fault**: SOAP Body chứa `Fault` của SOAP Envelope namespace, với mã, lý do và có thể có **detail** kiểu ứng dụng.

Đừng ngụy trang lỗi thành `SubmitOrderResponse(status="ERROR")` nếu XSD/WSDL không công bố trạng thái đó. Một client sinh stub từ WSDL có thể coi message ấy là success dù nghiệp vụ thất bại.

### 4.1. SOAP 1.1 Fault

Ví dụ lỗi schema được chuyển thành fault với chi tiết **được lọc**:

~~~xml
<env:Envelope
    xmlns:env="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
  <env:Body>
    <env:Fault>
      <faultcode>env:Client</faultcode>
      <faultstring>Dữ liệu yêu cầu không hợp lệ</faultstring>
      <detail>
        <ord:OrderFault>
          <ord:code>INVALID_REQUEST</ord:code>
          <ord:message>Vui lòng kiểm tra thông tin đơn hàng</ord:message>
          <ord:correlationId>c-6e9f1a</ord:correlationId>
          <ord:violations>
            <ord:violation>
              <ord:field>items.item.quantity</ord:field>
              <ord:rule>MIN_VALUE</ord:rule>
              <ord:message>Số lượng phải lớn hơn 0</ord:message>
            </ord:violation>
          </ord:violations>
        </ord:OrderFault>
      </detail>
    </env:Fault>
  </env:Body>
</env:Envelope>
~~~

`faultcode=Client` là mã **ở tầng SOAP 1.1**, thể hiện loại lỗi gắn với thông điệp bên gửi. `INVALID_REQUEST` là mã **nghiệp vụ/ứng dụng** trong fault detail. Hai thứ có thể cùng xuất hiện và **không được trộn lẫn**.

Đoạn minh họa không có nghĩa `PayloadValidatingInterceptor` mặc định tạo detail như trên. Interceptor mặc định có dạng error detail riêng khi cho phép; muốn đúng `ord:OrderFault` phải triển khai policy/fault builder hoặc resolver tùy chỉnh.

### 4.2. SOAP 1.2 Fault

SOAP 1.2 có Envelope namespace khác và cấu trúc Fault khác:

~~~xml
<env:Envelope
    xmlns:env="http://www.w3.org/2003/05/soap-envelope"
    xmlns:ord="urn:example:orders:v1">
  <env:Body>
    <env:Fault>
      <env:Code>
        <env:Value>env:Sender</env:Value>
      </env:Code>
      <env:Reason>
        <env:Text xml:lang="vi">
          Dữ liệu yêu cầu không hợp lệ
        </env:Text>
      </env:Reason>
      <env:Detail>
        <ord:OrderFault>
          <ord:code>INVALID_REQUEST</ord:code>
          <ord:message>Vui lòng kiểm tra thông tin đơn hàng</ord:message>
        </ord:OrderFault>
      </env:Detail>
    </env:Fault>
  </env:Body>
</env:Envelope>
~~~

SOAP 1.1 dùng `Client/Server`, SOAP 1.2 dùng `Sender/Receiver` tương ứng về mặt phân loại chung, nhưng cấu trúc `Fault`, namespace, cách biểu diễn reason và quy định HTTP media type không giống nhau. **Không copy nguyên fragment 1.1 vào Envelope 1.2**. Hãy kiểm tra SOAP factory, WSDL binding và client version đang sử dụng.

### 4.3. Cần công bố bao nhiêu thông tin?

| Trường | Nên công bố gì? | Tránh |
| --- | --- | --- |
| SOAP Fault code | `Client/Sender` hoặc `Server/Receiver` theo loại lỗi/giao thức | Gắn mọi lỗi thành `Server` hoặc `Client` bất kể nguyên nhân |
| Fault reason | Câu ngắn, dễ hiểu, không chứa dữ liệu nhạy cảm | `exception.getMessage()` nguyên bản |
| Application error `code` | Mã máy đọc được, ổn định như `INVALID_REQUEST` | Tên Java exception/package |
| `message` trong detail | Hướng dẫn sửa lỗi an toàn | SQL, filesystem path, secret, stack trace |
| `field` | Tên logical field được whitelist | XPath/XSD diagnostics thô, dữ liệu nhập, index nhạy cảm |
| `rule` | Mã constraint đã định nghĩa | Nội dung regex/private rule bí mật |
| `correlationId` | ID không chứa PII, dùng để liên hệ hỗ trợ | Access token, account ID hoặc ID tùy ý chưa validate |
| Danh sách `violations` | Có giới hạn số lượng và độ dài | Hàng nghìn lỗi parser hoặc phản chiếu payload |

`OrderFault` là **hợp đồng public**: thay tên phần tử, namespace, field bắt buộc hoặc mã lỗi có thể phá vỡ client giống như thay request/response.

## 5. Cấu hình `PayloadValidatingInterceptor` an toàn

Spring-WS cung cấp `org.springframework.ws.soap.server.endpoint.interceptor.PayloadValidatingInterceptor` để kiểm tra payload bằng XSD. Theo API Spring-WS 4.1.4:

- Mặc định validator kiểm tra **request**; bật `validateResponse` nếu muốn kiểm tra response.
- Request sai schema làm interceptor **dừng xử lý** và tạo SOAP `Client/Sender` fault khi thông điệp là SOAP.
- **Response sai schema không tự được biến thành SOAP Fault** bởi interceptor này; fault responses không được validator kiểm tra như response success.
- Ở `AbstractFaultCreatingValidatingInterceptor`, cấu hình `addValidationErrorDetail` mặc định **true**, có thể đưa các lỗi validator chính xác vào `detail`.

Vì vậy, với dịch vụ production có đối tác bên ngoài, hãy cân nhắc **tắt raw validation detail** nếu chưa có quy trình xét duyệt rõ dữ liệu nào được phép công bố.

### 5.1. Bean cấu hình Spring-WS

~~~java
import java.util.List;
import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.config.annotation.WsConfigurer;
import org.springframework.ws.server.EndpointInterceptor;
import org.springframework.ws.soap.server.endpoint.interceptor.PayloadValidatingInterceptor;

@Configuration
@EnableWs
public class OrdersValidationConfiguration implements WsConfigurer {

    @Bean
    public PayloadValidatingInterceptor ordersValidator() {
        PayloadValidatingInterceptor validator =
            new PayloadValidatingInterceptor();

        validator.setSchema(
            new ClassPathResource("xsd/orders-v1.xsd"));

        validator.setValidateRequest(true);
        validator.setValidateResponse(true);

        // Không gửi nguyên văn SAXParseException/XML diagnostics.
        validator.setAddValidationErrorDetail(false);

        // Câu chữ an toàn, ổn định ở tầng public.
        validator.setFaultStringOrReason("Dữ liệu yêu cầu không hợp lệ");
        validator.setFaultStringOrReasonLocale(
            Locale.forLanguageTag("vi"));

        return validator;
    }

    @Override
    public void addInterceptors(List<EndpointInterceptor> interceptors) {
        interceptors.add(ordersValidator());
    }
}
~~~

Khi sử dụng đoạn mã trên, cần bảo đảm `@EnableWs`, servlet mapping và các bean Spring-WS không bị khai báo trùng với cấu hình Boot hiện có.

Có thể dùng `setXsdSchema(XsdSchema)` nếu dự án đã có bean XSD, hoặc `setSchemas(Resource...)`/schema collection cho hợp đồng nhiều tệp. Đường dẫn `ClassPathResource` phải có trong JAR/WAR runtime.

### 5.2. Vì sao `setAddValidationErrorDetail(false)` quan trọng?

Nếu bật raw detail, validator có thể đưa **nội dung chẩn đoán chính xác** từ `SAXParseException` vào SOAP Fault, chẳng hạn thông báo chứa tên element/type, phần XML không hợp lệ hoặc các chi tiết đặc thù của parser.

Ngay cả khi một thông báo parser **không chứa credential**, public API vẫn không nên phụ thuộc vào câu chữ đó vì:

1. Nội dung phụ thuộc parser/provider/version; client khó xử lý ổn định.
2. Nó có thể tiết lộ cấu trúc schema, tên trường nội bộ hoặc giá trị dữ liệu.
3. Số lượng lỗi và kích thước thông báo có thể không phù hợp policy.
4. Khi schema thay đổi, cùng một request lỗi có thể tạo thông điệp khác nhau.
5. Việc dịch/làm rõ cho người dùng khó hơn so với mã lỗi máy đọc được.

Tắt raw detail cho một mức an toàn **mặc định**. Nếu client cần biết cụ thể trường nào sai, hãy **xây một cơ chế lọc có whitelist**: ánh xạ lỗi sang `field`/`rule`/`message` đã phê duyệt và giới hạn số phần tử, thay vì phát nguyên `SAXParseException.getMessage()`.

### 5.3. Response validation không phải sanitizer

Bật `validator.setValidateResponse(true)` giúp phát hiện server tạo XML response sai XSD trong quá trình phát triển và kiểm thử. Nhưng điều đó **không thay thế**:

- Kiểm tra dữ liệu nào được phép gửi cho caller.
- Kiểm tra quyền đối với field nhạy cảm.
- Đảm bảo mã lỗi không chứa giá trị nội bộ.
- Kiểm tra response fault detail theo schema.
- Bảo vệ HTTP response khi client đang đọc dữ liệu.

Trong API mặc định, validator log và dừng chuỗi response interceptor khi response sai; **không tự tạo SOAP Fault tương ứng**. Hãy thiết kế test bắt lỗi và sửa mapping/XSD. Với sản phẩm quan trọng, bổ sung cơ chế quan sát và kiểm thử response schema, không hy vọng validator sẽ “tự sửa” dữ liệu đã marshal.

## 6. Business validation: lỗi sau khi XML đã hợp XSD

Giả sử request có `quantity=3` và SKU hợp định dạng, nhưng hệ thống không bán `SKU-RED` hoặc buyer vượt hạn mức đặt hàng. Đây không phải `SAXParseException` và không nên ép XSD trở thành nơi kiểm tra state database.

### 6.1. Đường gọi nghiệp vụ

~~~mermaid
sequenceDiagram
    autonumber
    participant C as SOAP client
    participant I as PayloadValidatingInterceptor
    participant E as @Endpoint
    participant A as Application service
    participant R as Fault resolver
    C->>I: SubmitOrderRequest hợp XSD
    I-->>E: Tiếp tục
    E->>A: submit(command)
    A->>A: Kiểm tra SKU / quyền / trạng thái
    A-->>E: OrderRuleViolationException
    E-->>R: Exception nổi lên
    R-->>C: SOAP Fault theo public error policy
~~~

Đường lỗi này khác interceptor phát fault trực tiếp ở giai đoạn validation. Điều quan trọng là **một policy công bố thống nhất** cho mã lỗi, namespace detail và mức thông tin, dù lỗi được tạo ở interceptor hay service.

### 6.2. Public error code không phải tên exception

Một catalog mã lỗi có thể là:

| Mã công khai | Nhóm | Ý nghĩa/khả năng xử lý |
| --- | --- | --- |
| `INVALID_REQUEST` | Validation | XML/payload không đáp ứng hợp đồng; cần sửa |
| `SKU_NOT_AVAILABLE` | Business rule | Hàng không khả dụng; chọn SKU khác hoặc liên hệ hỗ trợ |
| `ORDER_LIMIT_EXCEEDED` | Business rule | Vượt giới hạn nghiệp vụ; sửa đơn |
| `REQUEST_ID_CONFLICT` | Idempotency | Cùng khóa gửi nội dung khác; không tạo lệnh mới |
| `NOT_AUTHORIZED` | Security/authorization | Caller không được phép; không tiết lộ tài nguyên |
| `SERVICE_TEMPORARILY_UNAVAILABLE` | Server | Hệ thống tạm thời lỗi; retry theo chính sách |
| `UNEXPECTED_ERROR` | Server | Lỗi không dự kiến; hỗ trợ tra cứu qua correlation ID |

Không trả tên như `org.hibernate.exception.ConstraintViolationException` hoặc `SqlIntegrityConstraintViolationException` cho client. Ngay cả với lỗi database unique constraint, ứng dụng cần phân tích ngữ nghĩa nó đại diện cho `REQUEST_ID_CONFLICT` hay lỗi dữ liệu nội bộ, rồi chỉ công bố mã đã định nghĩa.

### 6.3. Lỗi XSD và lỗi nghiệp vụ không nên vô tình phụ thuộc nhau

Nếu application cần phân biệt “SKU không tồn tại” với “SKU có thật nhưng hết hàng”, đó là rule có thể công bố hoặc phải che bớt theo policy. Nếu việc biết SKU tồn tại là dữ liệu nhạy cảm, có thể gom vào mã `SKU_NOT_AVAILABLE` để tránh enumeration.

Cách phân loại lỗi phụ thuộc **bề mặt API và nhóm caller**. Một thông tin an toàn cho đối tác logistics được xác thực chưa chắc an toàn cho một endpoint public không xác thực. Catalog lỗi phải được review như một phần của giao diện tích hợp.


## 7. `EndpointExceptionResolver` và chính sách ánh xạ lỗi

Spring-WS dùng `EndpointExceptionResolver` để xử lý exception trong luồng endpoint phù hợp. Với SOAP có các lựa chọn phổ biến:

| Cơ chế | Vai trò | Cảnh báo |
| --- | --- | --- |
| `SimpleSoapExceptionResolver` | Tạo SOAP Server/Receiver fault cho exception | Theo mặc định có thể dùng **exception message** làm reason |
| `SoapFaultMappingExceptionResolver` | Ánh xạ loại exception sang mã/chuỗi lỗi theo cấu hình | Cần mapping rõ và default fault an toàn |
| `SoapFaultAnnotationExceptionResolver` | Dùng `@SoapFault` trên exception class | Không tự tạo detail schema phức tạp |
| Custom `EndpointExceptionResolver` hoặc subclass | Tạo detail/application code, correlation ID và policy riêng | Phải bảo đảm serializer không công bố dữ liệu nhạy cảm |

**Lưu ý:** `PayloadValidatingInterceptor` có thể **tự tạo fault** trong `handleRequestValidationErrors` mà không cần application service ném exception; không phải mọi lỗi XSD đều tự đi qua fault mapper của endpoint. Nếu muốn mọi lỗi dùng cùng `OrderFault` schema, cần xây một tuyến tạo lỗi nhất quán cho cả interceptor và business exceptions.

### 7.1. Cấu hình mapping không làm lộ exception message

Một bean minh họa theo API Spring-WS:

~~~java
import java.util.Properties;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.soap.server.endpoint.SoapFaultDefinition;
import org.springframework.ws.soap.server.endpoint.SoapFaultMappingExceptionResolver;

@Configuration
public class OrdersFaultConfiguration {

    @Bean
    public SoapFaultMappingExceptionResolver ordersFaultResolver() {
        SoapFaultMappingExceptionResolver resolver =
            new SoapFaultMappingExceptionResolver();

        Properties mappings = new Properties();

        // Exception của application layer do dự án định nghĩa.
        mappings.setProperty(
            OrderRuleViolationException.class.getName(),
            "CLIENT,Dữ liệu đơn hàng không hợp lệ");

        mappings.setProperty(
            RequestIdConflictException.class.getName(),
            "CLIENT,Request identifier conflict");

        resolver.setExceptionMappings(mappings);

        // Không phát thẳng ex.getMessage() khi server lỗi.
        SoapFaultDefinition defaultFault = new SoapFaultDefinition();
        defaultFault.setFaultCode(SoapFaultDefinition.SERVER);
        defaultFault.setFaultStringOrReason(
            "Dịch vụ tạm thời không thể xử lý yêu cầu");
        resolver.setDefaultFault(defaultFault);

        // Chọn thứ tự theo resolver chain thực tế của dự án.
        resolver.setOrder(-1);
        return resolver;
    }
}
~~~

Các `import` bị xuống dòng ở code block cần viết lại thành **một dòng** khi áp dụng. `OrderRuleViolationException` và `RequestIdConflictException` là lớp do ứng dụng định nghĩa. `CLIENT`/`SERVER` trong mapping được Spring-WS chuyển thành Client/Server hoặc Sender/Receiver tùy SOAP version; hãy kiểm tra kết quả trên đường truyền ở cả hai phiên bản nếu dịch vụ hỗ trợ chúng.

**Tại sao đặt default fault an toàn?** Nếu không thiết kế fallback, một exception kỹ thuật có thể bị ánh xạ bằng text từ message nội bộ, chẳng hạn có hostname, SQL, file path hoặc dữ liệu nhạy cảm. Default reason phải là câu thông báo tổng quát; chi tiết chẩn đoán nằm trong logs/metrics bảo vệ bởi quyền truy cập.

### 7.2. Kết nối Java exception với `OrderFault`

Để trả detail có cấu trúc, có thể subclass `SoapFaultMappingExceptionResolver` rồi override:

~~~java
@Override
protected void customizeFault(
        Object endpoint, Exception ex, SoapFault fault) {
    // 1. Chỉ nhận loại exception nghiệp vụ được duyệt.
    // 2. Tạo DTO OrderFault chứa mã/chuỗi công khai.
    // 3. Marshal DTO thành XML trong fault.addFaultDetail().
    // 4. Không đưa exception message nội bộ vào detail.
}
~~~

Đây là **khung extension point**: API `AbstractSoapFaultDefinitionExceptionResolver.customizeFault(Object, Exception, SoapFault)` nhận một fault đã tạo. Có thể dùng `SoapFaultDetail.addFaultDetailElement(QName)` để tạo element, hoặc dùng `fault.addFaultDetail().getResult()` và JAXB marshaller để ghi một `OrderFault` root có đúng namespace/XSD.

Ví dụ về dữ liệu được xuất bản, **không** lộ raw exception:

~~~java
if (ex instanceof OrderRuleViolationException rule) {
    OrderFault publicFault = new OrderFault();
    publicFault.setCode(rule.publicCode());       // Whitelisted
    publicFault.setMessage(rule.publicMessage()); // Safe, stable
    // JAXB marshaller viết publicFault vào SoapFaultDetail Result.
}
~~~

`OrderFault` được giả định là JAXB class sinh từ XSD `OrderFault` mục 3; `rule.publicCode()` và `rule.publicMessage()` là API do application thiết kế, không nên sao chép `getMessage()` hoặc bất kỳ dữ liệu chưa xét duyệt. Khi viết code thật, xử lý lỗi marshalling cẩn thận để một lỗi trong quá trình tạo fault **không biến thành chuỗi rò rỉ thông tin mới**.

Một vấn đề khó: interceptor validation và resolver đều có thể muốn viết `SoapFaultDetail`. Không nên **thêm hai detail root khác contract**, hoặc vừa bật raw detail từ validator vừa thêm `OrderFault` đã lọc một cách lẫn lộn. Hãy quy định **một chủ sở hữu fault detail** cho từng nhánh lỗi.

### 7.3. `@SoapFault` giải quyết phần nào?

Có thể gắn annotation trên exception:

~~~java
@SoapFault(
    faultCode = FaultCode.CLIENT,
    faultStringOrReason = "Dữ liệu yêu cầu không hợp lệ")
public class InvalidOrderException extends RuntimeException {
    // ...
}
~~~

Ví dụ cần import `org.springframework.ws.soap.server.endpoint.annotation.SoapFault` và enum `FaultCode`; đồng thời phải có `SoapFaultAnnotationExceptionResolver` được cấu hình để annotation được dùng. Cơ chế này hữu ích cho fault code/reason, nhưng **không thay thế việc thiết kế/serialize detail có cấu trúc**. Việc để mặc định fault reason là exception message là một lựa chọn có nguy cơ rò rỉ nếu exception chứa dữ liệu nhạy cảm.

Trong Spring-WS, nhiều resolvers có thể cùng tồn tại. Review **order/precedence và phạm vi exception**; một resolver chạy trước có thể xử lý exception khiến resolver sau không còn cơ hội tạo custom fault detail.

## 8. WSDL có phải khai báo `OrderFault`?

Với contract-first, câu trả lời phụ thuộc loại lỗi và kỳ vọng của đối tác. Một fault **nghiệp vụ có cấu trúc** thường nên được khai báo tường minh trong WSDL để công cụ sinh client biết message lỗi và các kiểu XSD.

### 8.1. WSDL 1.1 fault được khai báo

Ví dụ **các fragment rút gọn** trong tài liệu WSDL 1.1 có namespace `ord=urn:example:orders:v1`, đã định nghĩa input/output message tương ứng:

~~~xml
<wsdl:message name="OrderFaultMessage">
  <wsdl:part name="fault" element="ord:OrderFault"/>
</wsdl:message>

<wsdl:portType name="OrdersPort">
  <wsdl:operation name="SubmitOrder">
    <wsdl:input message="ord:SubmitOrderRequestMessage"/>
    <wsdl:output message="ord:SubmitOrderResponseMessage"/>
    <wsdl:fault name="OrderFault"
                message="ord:OrderFaultMessage"/>
  </wsdl:operation>
</wsdl:portType>

<wsdl:binding name="OrdersSoapBinding" type="ord:OrdersPort">
  <!-- soap:binding / input / output được lược bớt -->
  <wsdl:operation name="SubmitOrder">
    <wsdl:fault name="OrderFault">
      <soap:fault name="OrderFault" use="literal"/>
    </wsdl:fault>
  </wsdl:operation>
</wsdl:binding>
~~~

Trong WSDL hoàn chỉnh, cần khai báo namespace `wsdl`/`soap`, tất cả message types, `soap:binding`, các `wsdl:input`/`wsdl:output` của binding và `wsdl:service` phù hợp. Fragment chỉ nhấn mạnh mối liên hệ:

~~~text
SOAP Fault detail
    ↓ QName
{urn:example:orders:v1}OrderFault
    ↓ WSDL part/@element
OrderFaultMessage
    ↓ wsdl:portType/wsdl:fault
SubmitOrder operation
    ↓ binding wsdl:fault + soap:fault
SOAP 1.1 document/literal fault contract
~~~

Không phải một SOAP Fault được tuyên bố trong WSDL thì **runtime tự biết** phải ánh xạ `OrderRuleViolationException` vào fault ấy. Vẫn cần resolver và serializer đúng QName/type.

### 8.2. Không phải mọi fault đều có thể hoặc nên mô tả thành một business fault duy nhất

Một số lỗi xảy ra **trước khi xác định endpoint/operation**: XML không parse được, SOAP version sai, request không match mapping, một số lỗi WS-Security. Với các lỗi đó, hạ tầng có thể tạo fault ở tầng SOAP mà không có `OrderFault` detail.

Ngược lại, `INVALID_REQUEST` do business rule có thể được chuẩn hóa thành `OrderFault` theo WSDL nếu service contract đã định nghĩa. Không nên yêu cầu mọi lỗi protocol/security sớm phải tự đi qua một business resolver mà framework không bảo đảm chạy.

### 8.3. WSDL sinh động và WSDL tĩnh

`DefaultWsdl11Definition` thường suy ra operation từ XSD global elements với suffix `Request`/`Response`. Việc **thêm một `OrderFault` global element** trong XSD không phải bảo đảm bộ sinh tự xây đầy đủ mọi `wsdl:fault` theo semantics nghiệp vụ mong muốn.

Nếu nhiều đối tác sinh client và yêu cầu fault detail mạnh về tương thích, hãy xem xét **công bố WSDL tĩnh** có fault message/binding đã review; hoặc xác minh chính xác WSDL sinh động có các phần cần thiết bằng test tự động. Chỉ nhìn XSD là chưa đủ.

### 8.4. Versioning lỗi giống versioning response

Các thay đổi có thể phá vỡ tương thích:

- Đổi namespace hoặc local name `OrderFault`.
- Đổi mã lỗi đang được client xử lý.
- Biến một field detail từ tùy chọn thành bắt buộc.
- Chuyển `violations` từ 0..n sang cách biểu diễn khác.
- Đổi `faultCode` từ Client thành Server làm client thay retry policy.
- Đổi SOAP version từ 1.1 sang 1.2 mà không có binding/client support.

Nên kiểm thử **client cũ → server mới** và **client mới → server cũ**, đồng thời có chính sách mã lỗi không biết trước (unknown future error codes) để tránh client crash vì một giá trị mới.

## 9. Chính sách nội dung lỗi có thể công bố

“Có thể công bố” không có nghĩa **cứ server biết gì là gửi hết**. Đây là quyết định bảo mật và sản phẩm, cần cân bằng giữa thông tin đủ để đối tác tự sửa và giới hạn tiết lộ dữ liệu.

### 9.1. Ba cấp thông tin

| Cấp | Thông tin | Được phép xuất hiện ở đâu? |
| --- | --- | --- |
| **Public contract** | Mã lỗi, lý do chung, field/rule đã whitelist, correlation ID | SOAP Fault gửi đối tác |
| **Internal diagnostic** | Validation trace đã được che, exception type, request context, bounded metrics | Logs/traces được phân quyền |
| **Secret/sensitive** | Password, access token, private key, dữ liệu thanh toán, PII không cần thiết | Không đưa vào Fault; logs cũng phải che/bảo vệ |

Ví dụ `SAXParseException` có thể mang một thông báo kỹ thuật:

~~~text
cvc-minInclusive-valid: Value '0' is not facet-valid
with respect to minInclusive '1' for type 'QuantityType'.
~~~

Trong internal logs đã kiểm soát, có thể cần biết nguyên nhân này. Trong SOAP Fault public, chỉ cần:

~~~text
code: INVALID_REQUEST
field: items.item.quantity
rule: MIN_VALUE
message: Số lượng phải lớn hơn 0
~~~

Tên `field` ở đây là **định danh logical** do hệ thống xác nhận và whitelist, không phải đường XPath do người dùng tự gửi hoặc stack trace parser.

### 9.2. Chỉ xuất bản những lỗi client có thể tự sửa

Một policy thực tế:

- **Client có thể sửa đầu vào:** dùng mô tả rõ nhưng không phản chiếu dữ liệu nhạy cảm.
- **Client cần xác thực lại:** thông báo chung về credentials/signature, không tiết lộ token validity detail để hỗ trợ tấn công đoán khóa.
- **Client không có quyền:** tùy threat model, tránh để lộ tài nguyên có tồn tại hay không.
- **Lỗi server:** thông báo “Không thể xử lý yêu cầu” cùng correlation ID; không đưa endpoint nội bộ hay SQL.
- **Lỗi phụ thuộc đối tác:** nên báo lỗi loại tương ứng và hướng retry, nhưng không tiết lộ topology backend.
- **Validation dạng phức tạp:** giới hạn tối đa số violations, hợp nhất lỗi lặp và xử lý trường hợp nhiều lỗi vượt hạn.

### 9.3. Những giá trị đặc biệt phải bảo vệ

1. **Dữ liệu đầu vào:** không echo tên khách hàng, email, ngày sinh, token, mã xác thực hoặc toàn bộ giá trị invalid field.
2. **Đường dẫn:** tránh filesystem path, classpath, JDBC URL, internal hostname hoặc topic name.
3. **Stack trace:** không phát Java frames hoặc tên package nội bộ.
4. **Parser errors:** không phụ thuộc raw diagnostics `cvc-*` trong public API.
5. **Regex/business policy:** tránh công bố constraint nội bộ có thể bị lợi dụng, trừ các rule đã nằm trong hợp đồng.
6. **Mã tương quan:** UUID/correlationId phải không chứa bí mật; nếu nhận từ client, giới hạn format/length và tránh log injection.
7. **Thông báo đa ngôn ngữ:** client nên xử lý theo **`code`**, không parsing chuỗi dịch.
8. **Số lượng và kích thước:** cả Fault và logs cần giới hạn để tránh amplification/DoS.

### 9.4. Không lộ thông tin qua sự khác biệt lỗi

Một API tra cứu đơn có thể trả `ORDER_NOT_FOUND` khi không tồn tại và `ACCESS_DENIED` khi có nhưng caller không được quyền. Điều này có thể tiết lộ sự tồn tại của đơn hàng. Trong một threat model cần chống enumeration, hãy cân nhắc thông điệp công khai thống nhất (ví dụ “Đơn hàng không khả dụng”) còn nội bộ vẫn phân biệt nguyên nhân.

Tương tự, lỗi xác thực chữ ký nên tối giản: nếu public API nói “chứng chỉ X tồn tại nhưng đã gần đúng”, kẻ tấn công có thể dùng thông tin đó để tối ưu thử sai. **An toàn thông tin phải được review trên từng nhóm caller, không chỉ trên một hàm map exception.**

## 10. SOAP Fault, transaction và retry policy

### 10.1. SOAP code không quyết định tất cả

Một Client/Sender fault thường chỉ ra vấn đề phía request, nhưng **không phải mọi Client fault đều không thể retry**. Ví dụ authorization hết hạn có thể yêu cầu refresh credential, còn business rate limit có thể yêu cầu chờ theo policy. Ngược lại, Server/Receiver fault có thể phát sinh **sau khi giao dịch đã commit**, nên retry một thao tác tạo đơn mà không có idempotency có thể tạo trùng.

| Nhóm kết quả | Client nên làm | Rủi ro cần xét |
| --- | --- | --- |
| `INVALID_REQUEST` | Sửa XML/giá trị rồi gửi lệnh đã thay đổi | Không retry nguyên payload sai vô hạn |
| `REQUEST_ID_CONFLICT` | Tra cứu/điều chỉnh intent, không đổi requestId chỉ để vượt khóa | Có thể tạo tác dụng phụ trùng |
| `NOT_AUTHORIZED` | Xác thực/phân quyền theo policy | Không gửi credential trong log/Fault |
| `SKU_NOT_AVAILABLE` | Đổi SKU hoặc xử lý nghiệp vụ | Không làm lộ catalog riêng |
| `SERVICE_TEMPORARILY_UNAVAILABLE` | Backoff/jitter và retry có giới hạn khi an toàn | Lệnh trước có thể đã commit |
| Timeout/connection reset | Query status hoặc retry **cùng idempotency key** | Không thể suy ra server rollback |
| SOAP Fault ở nhánh WS-Security | Sửa policy/chứng chỉ/token; không brute-force | Có thể cần vận hành/cấu hình lại |

### 10.2. “Fault” không đồng nghĩa “DB rollback”

Có những thời điểm lỗi:

~~~mermaid
flowchart TD
    A["SOAP request"] --> B["XSD + Security validation"]
    B --> C{"Hợp lệ?"}
    C -- "Không" --> D["Fault trước nghiệp vụ"]
    C -- "Có" --> E["@Transactional application service"]
    E --> F{"Commit thành công?"}
    F -- "Không" --> G["Fault/lỗi transport: xác minh kết quả"]
    F -- "Có" --> H["JAXB marshal SOAP response"]
    H --> I{"Response được gửi/nhận?"}
    I -- "Có" --> J["Client nhận success"]
    I -- "Không" --> K["Server đã commit nhưng client có thể không biết"]
    K --> L["Idempotent retry / GetStatus"]
~~~

Một lỗi XSD thường từ chối **trước use case**; một lỗi response marshalling hoặc network **có thể xảy ra sau commit**. Vì thế client không thể suy luận transaction chỉ bằng HTTP status hoặc sự tồn tại của SOAP Fault.

Với command có side effect, quy định `requestId`, khóa duy nhất và cách đọc kết quả bền vững khi retry. Đừng đưa lời khuyên “nếu lỗi Server thì gửi requestId mới” nếu thao tác trước có thể đã tạo đơn.

## 11. WS-Security, XML security và fault disclosure

### 11.1. Chữ ký, token và XSD giải quyết các câu hỏi khác nhau

- **XSD validation:** XML thuộc đúng schema, kiểu, cardinality và thứ tự không?
- **WS-Security:** chữ ký, timestamp, token, mã hóa có hợp chính sách không?
- **TLS/mTLS:** kết nối được bảo vệ và chứng chỉ có chain/hostname/client identity hợp lệ không?
- **Authorization:** principal đã xác thực có được thực hiện nghiệp vụ với dữ liệu cụ thể không?

Một request hợp XSD **vẫn có thể bị giả mạo**. Một request đã có signature hợp lệ **vẫn có thể vi phạm nghiệp vụ**. Không dùng kết quả của lớp này để bỏ qua lớp khác.

### 11.2. Không công bố raw security exception

`Wss4jSecurityInterceptor` và security stack có thể xử lý các tình huống token sai, timestamp quá hạn, chữ ký không khớp hoặc certificate không tin cậy. Chúng có thể tạo fault theo chính sách riêng và không nhất thiết đi qua cùng application exception resolver.

Khi thiết kế nội dung lỗi:

- Trả lý do chung “Yêu cầu không đáp ứng chính sách bảo mật” nếu đủ cho hợp đồng.
- Không echo token, certificate private material, decoded credentials hoặc raw signed fragments.
- Không công bố kết quả kiểm tra quá chi tiết giúp brute-force.
- Ghi logs được phân quyền với correlation ID, loại lỗi đã chuẩn hóa và thông tin cần thiết đã che.
- Cấu hình certificate trust, hostname validation và rotation riêng tại transport/security layer.

### 11.3. XML parser an toàn trước khi validation

XML không tin cậy có thể gây XXE, external entity resolution, mở rộng thực thể hoặc tài liệu quá lớn. Cần cấu hình parser/message factory an toàn, hạn chế DTD/external entities và giới hạn kích thước request, số node, độ sâu, thời gian.

Đừng cố giải quyết XXE bằng cách “trả SOAP Fault an toàn” sau khi parser đã đọc file nội bộ. **Bảo vệ parser phải có hiệu lực trước khi dữ liệu được xử lý.** Đối với SOAP có chữ ký, cần đảm bảo node đã được xác minh là đúng node được JAXB/endpoint dùng; tránh XPath rộng theo local name khiến XML signature wrapping thành rủi ro.

### 11.4. Những lỗi chưa có `@Endpoint` thì sao?

`PayloadValidatingInterceptor` là endpoint interceptor chạy trong invocation chain **sau khi mapping tìm được endpoint**. Nếu XML không parse được, HTTP path sai, TLS handshake thất bại hoặc không có mapping, interceptor đó không chắc được gọi.

Vì vậy cần bảo vệ ở nhiều lớp: gateway/HTTP filter, transport parser, WS-Security/endpoint interceptors và application policy. Không nên khẳng định một custom fault resolver có thể định dạng thống nhất **mọi lỗi của hệ thống** bất kể thời điểm.

## 12. Observability: lỗi công khai và thông tin nội bộ

Một chiến lược hỗ trợ đối tác tốt không cần phơi toàn bộ exception. Thay vào đó:

~~~text
SOAP Fault public
  ├── code: INVALID_REQUEST
  ├── message: Dữ liệu yêu cầu không hợp lệ
  └── correlationId: c-6e9f1a

Protected telemetry
  ├── correlationId: c-6e9f1a
  ├── operation: SubmitOrder
  ├── classification: XSD_VALIDATION
  ├── internalValidationCategory: MIN_INCLUSIVE
  ├── durationMs: ...
  └── sampled, redacted diagnostic (nếu policy cho phép)
~~~

Correlation ID **không phải secret**, nhưng cũng không nên chứa email/phone/account ID thật. Nếu do client gửi thì validate; nếu do server tạo, nên có định dạng ổn định và tránh xung đột. Đối tác có thể gửi ID này cho bộ phận hỗ trợ để truy vết ở log nội bộ theo quyền.

### 12.1. Metrics hữu ích

| Metric | Mục đích | Tránh |
| --- | --- | --- |
| Số lỗi theo operation và public code | Phát hiện contract regression | Gắn raw orderId/email làm metric label |
| Tỷ lệ `INVALID_REQUEST` | Đánh giá chất lượng client | Gộp với server error rồi đổ lỗi nhầm |
| Tỷ lệ response validation failure | Phát hiện bug serializer/server | Công bố chẩn đoán nội bộ ra ngoài |
| SOAP Fault Client/Sender vs Server/Receiver | Quan sát xu hướng lỗi | Coi Fault code là đầy đủ cho business metrics |
| Lỗi WS-Security/TLS theo loại | Theo dõi tích hợp chứng chỉ/policy | Log private key/token |
| Timeout retry/idempotency conflict | Kiểm tra độ ổn định hệ thống | Suy luận success/failure transaction từ HTTP alone |

Không cần log **toàn bộ SOAP Envelope** cho mọi request. Nếu bật logging XML để gỡ lỗi, cần sampling, redaction, retention và quyền truy cập phù hợp.

## 13. Kiểm thử lỗi validation và nội dung công bố

Một hợp đồng lỗi chỉ đáng tin khi client ngoài ứng dụng có thể nhận và diễn giải đúng **XML trên đường truyền**.

### 13.1. Ma trận kiểm thử

| Ca | Kỳ vọng SOAP | Kiểm tra công bố |
| --- | --- | --- |
| Thiếu `buyerId` | Client/Sender fault | Không có raw SAX parser text |
| `quantity=0` | Client/Sender fault | Có mã chung hoặc detail đã lọc |
| `quantity=1000` | Client/Sender fault | Không phát hiện lỗi vào application service |
| `items` rỗng | Client/Sender fault | Không tiết lộ schema path nội bộ |
| Sai namespace request | Lỗi schema/mapping theo cấu hình | Không vào nhầm version endpoint |
| XML không well-formed | Lỗi parse/protocol; có thể không có application detail | Không có stack trace |
| XML hợp XSD nhưng SKU không tồn tại | Business fault theo policy | Mã `SKU_NOT_AVAILABLE` an toàn |
| Cùng requestId, payload khác | Fault `REQUEST_ID_CONFLICT` | Không echo payload cũ |
| Principal thiếu quyền | Fault/từ chối theo security policy | Không tiết lộ sự tồn tại của order nếu policy cấm |
| Signature/timestamp sai | Security fault | Không lộ token/chứng chỉ |
| Unhandled `NullPointerException` trong server | Server/Receiver fault | Reason chung, không có stack trace |
| Response thiếu `status` | Validation/test phát hiện lỗi server | Không biến thành “client gửi sai” |
| Fault detail chứa hơn 10 violations | Không được công bố vượt policy | Giới hạn size/length |
| SOAP 1.1 client | SOAP `Client/Server` đúng cấu trúc | `detail` có QName đúng |
| SOAP 1.2 client | SOAP `Sender/Receiver` đúng cấu trúc | `env:Detail` đúng namespace |
| Java client sinh từ WSDL | Nhận fault có mã và detail phù hợp | Binding đúng kiểu |
| .NET client sinh từ WSDL | Nhận cùng semantics dù binding model khác | Interoperability |
| Lỗi sau DB commit | Client có thể thấy fault/timeout | Retry idempotent, không tạo trùng |
| Fault trước endpoint mapping | Không kỳ vọng business resolver chạy | Test gateway/transport behavior |

### 13.2. Test `PayloadValidatingInterceptor` với `MockWebServiceClient`

Spring-WS Test có matcher `clientOrSenderFault()` kiểm tra đúng fault class theo SOAP version. Khung test:

~~~java
import static org.springframework.ws.test.server.RequestCreators.withPayload;
import static org.springframework.ws.test.server.ResponseMatchers.clientOrSenderFault;

// Giả định applicationContext + Spring-WS beans đã cấu hình.
MockWebServiceClient client =
    MockWebServiceClient.createClient(applicationContext);

client.sendRequest(
        withPayload(new StringSource(invalidSubmitOrderXml)))
      .andExpect(
        clientOrSenderFault("Dữ liệu yêu cầu không hợp lệ"));
~~~

`StringSource` là utility của Spring XML. `invalidSubmitOrderXml` phải là **payload root** `SubmitOrderRequest` (không phải toàn bộ SOAP Envelope khi dùng `withPayload`). Với `validateRequest=true` và một endpoint mapping phù hợp, lỗi schema phải được chặn trước business call.

Bài test trên **chưa kiểm tra nội dung detail**. Cần thêm assertion trên SOAP Envelope hoặc custom `ResponseMatcher` để bảo đảm:

- Không có raw validation messages, Java class names, filesystem paths, SQL hoặc token.
- Namespace/detail root đúng và các trường `code`, `message`, `correlationId` theo policy.
- Nếu `setAddValidationErrorDetail(false)`, không xuất hiện raw validator detail.
- Nếu policy yêu cầu custom `OrderFault`, validator/resolver custom thực sự tạo detail theo schema.

### 13.3. Test fault nghiệp vụ và resolver

Mock application service trả `OrderRuleViolationException` và gửi request **hợp XSD**. Kỳ vọng:

1. Request qua được XSD validation và mapping.
2. Endpoint gọi service.
3. Resolver chọn `Client/Sender` fault phù hợp.
4. Detail root `{urn:example:orders:v1}OrderFault` chứa mã public được duyệt.
5. Reason/detail không phản chiếu internal exception message.
6. Correlation ID xuất hiện nếu hợp đồng yêu cầu và nhánh interceptor đã có điều kiện để gắn Header/detail.

Đồng thời cần test exception **không được map** để kiểm tra fallback `Server/Receiver` có reason chung. Không chỉ test một đường lỗi “đẹp”.

### 13.4. Response validation và lỗi serialize

Một test đặt server response có `status` sai schema; khi bật `validateResponse`, phải phát hiện lỗi theo behavior của Spring-WS, nhưng **không giả định interceptor tự tạo fault**. Thêm test marshalling, schema validation và log/metrics để ngăn phát hành response sai.

Nếu SOAP response đã bị gửi một phần hoặc client disconnect, có thể chỉ có lỗi transport. Test tích hợp cần phân biệt fault path và network path.

### 13.5. Client-side tests

Ở phía SOAP client, `MockWebServiceServer` có thể mô phỏng:

- SOAP 1.1 Client fault và Server fault.
- SOAP 1.2 Sender/Receiver fault (khi client/message factory hỗ trợ).
- Lỗi transport/timeout không có SOAP response.
- Detail thiếu field tùy chọn hoặc có một mã lỗi mới.
- Fault có UTF-8 tiếng Việt, đổi XML prefix nhưng namespace URI đúng.

Với `WebServiceTemplate`, xác minh luồng xử lý SOAP Fault khác luồng unmarshal response thành công (thông thường ném một SOAP fault client exception hoặc dùng fault resolver/handler theo cấu hình). Không ép Fault thành JAXB `SubmitOrderResponse`.

### 13.6. Kiểm thử WSDL fault thật

Không chỉ nhìn Java class. Hãy:

1. Tải WSDL từ endpoint công bố thực tế.
2. Theo `wsdl:operation/wsdl:fault` đến `wsdl:message/part` rồi đến global element `OrderFault`.
3. Kiểm tra `soap:fault use="literal"` trong binding liên quan.
4. Sinh thử Java/.NET client từ WSDL.
5. Gửi lỗi thực để so XML fault detail/QName/namespace với WSDL.
6. Thử client cũ với phiên bản WSDL/XSD mới theo chính sách tương thích.

Một file XSD chứa `OrderFault` mà WSDL hoặc resolver không dùng nó là **một hợp đồng lỗi chưa hoàn thành**, không phải thành công chỉ vì build xanh.

## 14. Các anti-pattern cần tránh

| Anti-pattern | Rủi ro | Thay bằng |
| --- | --- | --- |
| Echo `SAXParseException.getMessage()` trong Fault | Lộ chi tiết schema/giá trị và phụ thuộc parser | Fault reason chung + optional safe violations |
| Dùng `exception.getMessage()` cho mọi fault | Lộ SQL, path, token hoặc trạng thái nội bộ | Public error catalog |
| Trả HTTP 200 + `status="ERROR"` ngoài XSD | Client coi là success; sai schema | SOAP Fault đúng contract |
| Gắn lỗi XSD thành Server fault | Đổ lỗi nhầm và client retry sai | Client/Sender fault theo chính sách |
| Gắn response validation failure thành Client fault | Che lỗi server | Server-side incident + recovery |
| Thêm `OrderFault` vào XSD rồi tưởng runtime tự tạo | Client nhận detail không như WSDL | Resolver/serializer có test |
| Bật raw validation detail và custom fault cùng lúc | Hai nguồn detail không nhất quán, có thể lộ raw errors | Một chủ sở hữu detail |
| Chỉ so `faultstring` ở client | Dễ vỡ khi localization | Stable `code`/QName |
| Đưa `requestId` hoặc tên khách hàng vào metric label | Lộ PII, bùng nổ cardinality | Operation + public code |
| Trả lỗi “order tồn tại nhưng bạn không sở hữu” cho caller không được phép | Lộ sự tồn tại của tài nguyên | Error disclosure policy theo threat model |
| Kết luận Server fault nghĩa là DB rollback | Có thể lỗi sau commit | Idempotency + query status |
| Retry command bằng requestId mới sau timeout | Có thể tạo trùng side effect | Cùng key cho cùng intent |
| Coi SOAP Header `wsse:Security` hiện diện là đã xác thực | Có thể giả mạo | WSS4J validation |
| Chọn XML node chỉ bằng local name | XML signature wrapping/nhầm version | QName + security-aware parsing |
| Test Java method trực tiếp rồi kết luận SOAP Fault đúng | Bỏ qua dispatcher/interceptor/resolver | `MockWebServiceClient` và wire tests |
| Không giới hạn số lỗi trả ra | Amplification/DoS | Cap số violation/bytes và sanitize |

## 15. Quy trình thiết kế một error contract

~~~mermaid
flowchart TD
    A["Liệt kê các failure modes"] --> B["Phân loại: schema / business / security / server"]
    B --> C["Chọn SOAP Fault code theo version"]
    C --> D["Định nghĩa public error codes và thông điệp an toàn"]
    D --> E["XSD OrderFault + WSDL binding khi cần"]
    E --> F["Validator policy: tắt raw detail"]
    F --> G["Exception resolver / custom detail mapping"]
    G --> H["Security review: PII, token, stack trace"]
    H --> I["Test SOAP 1.1/1.2 + Java/.NET"]
    I --> J["Monitor, versioning và client recovery"]
~~~

Một checklist review tối thiểu:

1. Các lỗi XSD, business, authorization, WS-Security và infrastructure đã được phân biệt chưa?
2. Với mỗi lỗi, client có hành động cụ thể nào và retry có an toàn không?
3. Public reason và detail có lấy trực tiếp từ exception message không?
4. Có bao nhiêu violations tối đa, độ dài mỗi trường bao nhiêu?
5. Field path có phải **logical field name** được whitelist không?
6. Có correlation ID do server kiểm soát và cách tra log phân quyền không?
7. SOAP 1.1 và 1.2 có dùng đúng Fault code/structure không?
8. WSDL có mô tả fault detail khi đối tác cần sinh typed fault không?
9. Có test lỗi trước mapping, lỗi ở interceptor và lỗi sau commit không?
10. Client cũ có thể xử lý mã lỗi mới/field tùy chọn không?
11. Security interceptor đã xác minh đúng XML node/identity trước khi cho nghiệp vụ chạy chưa?
12. Tài liệu lỗi có khớp response thực tế từ Spring-WS không?

### Câu hỏi tự kiểm tra

1. `quantity=0` và `SKU_NOT_AVAILABLE` khác nhau ở tầng validation nào? Có cùng retry policy không?
2. Vì sao `PayloadValidatingInterceptor` có thể dừng request trước khi method `@Endpoint` chạy?
3. Vì sao nên chú ý `setAddValidationErrorDetail(false)` trên một API SOAP công bố cho bên ngoài?
4. `getResponse()`/fault response của interceptor có tự động đi qua `SoapFaultMappingExceptionResolver` không?
5. SOAP 1.1 `Client` và SOAP 1.2 `Sender` khác gì về cấu trúc biểu diễn trong XML?
6. Có thể thêm `OrderFault` vào XSD rồi bỏ qua `wsdl:fault` và exception resolver không? Vì sao?
7. Vì sao `OrderFault.code` ổn định hơn việc client phân tích `faultstring`?
8. Nếu một request đã commit DB nhưng SOAP response marshal lỗi, client có thể kết luận transaction rollback không?
9. Những dạng dữ liệu nào tuyệt đối không nên nằm trong public fault detail?
10. Khi client không có quyền xem một đơn, làm sao tránh lộ việc đơn đó có tồn tại?
11. Response validation bị lỗi có nghĩa request từ client sai hay server đã sinh dữ liệu sai?
12. Muốn test fault XML thật, `MockWebServiceClient` khác test gọi trực tiếp method Java ở điểm nào?
13. Nếu WSDL đổi namespace của `OrderFault`, các client sinh từ bản cũ có thể gặp lỗi nào?
14. Tại sao raw parser diagnostics và rule whitelist có tác dụng bảo mật/ổn định khác nhau?

## Tài liệu tham khảo

- [Spring Web Services Reference 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/) — endpoint validation, exception handling, SOAP Fault và test hỗ trợ.
- [Spring-WS API — PayloadValidatingInterceptor](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/soap/server/endpoint/interceptor/PayloadValidatingInterceptor.html) — validate request/response và hành vi lỗi.
- [Spring-WS API — AbstractFaultCreatingValidatingInterceptor](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/soap/server/endpoint/interceptor/AbstractFaultCreatingValidatingInterceptor.html) — `setAddValidationErrorDetail` và custom fault string/detail.
- [Spring-WS API — SoapFaultMappingExceptionResolver](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/soap/server/endpoint/SoapFaultMappingExceptionResolver.html) — ánh xạ exception thành fault.
- [Spring-WS API — AbstractSoapFaultDefinitionExceptionResolver](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/soap/server/endpoint/AbstractSoapFaultDefinitionExceptionResolver.html) — `customizeFault` cho detail.
- [Spring-WS API — ResponseMatchers](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/test/server/ResponseMatchers.html) — `clientOrSenderFault` và matcher test.

**Ghi nhớ:** **Validation quyết định request có được xử lý; SOAP Fault là cách truyền lỗi đúng giao thức; public error contract quyết định thông tin nào được phép gửi cho đối tác.** Hãy kiểm XSD ở ranh giới, tách lỗi nghiệp vụ/authorization/security, tắt raw validation detail khi chưa có lý do công bố, dùng mã lỗi ổn định và schema fault được review. Kiểm tra cả nhánh thành công lẫn fault, SOAP 1.1/1.2 và retry sau timeout để dịch vụ Spring-WS tích hợp an toàn, ổn định.
