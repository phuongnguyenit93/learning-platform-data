# Kiểm thử thông điệp yêu cầu, phản hồi và lỗi hợp đồng

Trong tích hợp SOAP của Spring Boot, một lời gọi HTTP trả về mã 200 chưa đủ chứng minh hai hệ thống hiểu đúng nhau. Ứng dụng có thể gửi sai tên phần tử XML, dùng nhầm namespace, đọc nhầm trường trong phản hồi hoặc bỏ sót một SOAP Fault có ý nghĩa nghiệp vụ. Ngay cả khi XML hợp lệ về cú pháp, thông điệp vẫn có thể vi phạm **hợp đồng WSDL/XSD** hoặc quy tắc xử lý của đối tác.

Bài học thuộc chương **SOAP và XML** của mô-đun **SPRING_BOOT_INTEGRATION**. Trong phạm vi tích hợp hệ thống bằng HTTP client, cơ sở dữ liệu, cache, broker thông điệp và adapter của Spring Integration, kiểm thử SOAP giúp bảo đảm hợp đồng dữ liệu, phân loại lỗi, giao dịch, chống xử lý trùng lặp và khả năng quan sát của luồng thực tế.

## 1. Mục tiêu và ranh giới kiểm thử

Sau bài này, bạn có thể:

- Xác định những gì cần kiểm tra ở tầng XML, WSDL/XSD, SOAP và HTTP.
- Xây dựng bộ mẫu (fixture) cho yêu cầu, phản hồi thành công và SOAP Fault.
- Kiểm thử SOAP client bằng **MockWebServiceServer**, kiểm thử SOAP endpoint bằng **MockWebServiceClient**.
- Phát hiện thay đổi hợp đồng gây lỗi tương thích và phân biệt SOAP Fault với lỗi kết nối.
- Thiết kế kiểm thử lỗi, retry, idempotency và quan sát phù hợp với luồng tích hợp Spring Boot.

Một bộ kiểm thử tốt trả lời ít nhất ba câu hỏi độc lập:

| Câu hỏi | Kiểm tra cụ thể | Rủi ro nếu bỏ qua |
| --- | --- | --- |
| **Thông điệp đúng hợp đồng chưa?** | XML well-formed, QName/namespace, kiểu dữ liệu, thứ tự, ràng buộc XSD, operation và fault khai báo trong WSDL | Đối tác từ chối thông điệp; hai bên hiểu khác cấu trúc |
| **Ứng dụng xử lý đúng chưa?** | Tạo request, ánh xạ response, diễn giải mã lỗi, xác định retry và dữ liệu trả về cho nghiệp vụ | Lưu trạng thái sai, bỏ sót lỗi nghiệp vụ, retry không cần thiết |
| **Trao đổi qua ranh giới hệ thống đúng chưa?** | URL, phiên bản SOAP, Content-Type, SOAPAction, header, mã HTTP, timeout, TLS, logging và correlation ID | Chạy qua mock nhưng thất bại khi kết nối thật |

Một số khái niệm dễ nhầm:

- **Well-formed XML**: thẻ mở/đóng đúng, không sai cú pháp; chưa nói gì về nghiệp vụ.
- **Valid XML theo XSD**: phần tử, namespace, kiểu và ràng buộc tuân theo schema tương ứng.
- **WSDL**: mô tả operation, các message/binding, endpoint và có thể khai báo fault; một payload hợp lệ theo XSD vẫn có thể dùng sai operation hoặc SOAPAction.
- **SOAP Fault**: thông điệp lỗi theo giao thức SOAP. Một fault được khai báo trong WSDL có thể là kết quả nghiệp vụ hợp lệ về mặt hợp đồng.
- **Lỗi hợp đồng**: request/response sai cấu trúc, sai namespace, sai kiểu hoặc thay đổi tương thích không được kiểm soát; không đồng nhất với mọi SOAP Fault.

## 2. Một hợp đồng minh họa xuyên suốt

Giả sử Spring Boot gọi dịch vụ lấy trạng thái đơn hàng, với operation **GetOrder**, namespace ứng dụng **urn:demo:orders:v1** và SOAP 1.1. Đây là ví dụ học tập; khi triển khai, phải dùng WSDL/XSD do hệ thống đối tác cung cấp làm nguồn chuẩn.

### 2.1. Yêu cầu SOAP hợp lệ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:demo:orders:v1">
  <soap:Header/>
  <soap:Body>
    <ord:GetOrderRequest>
      <ord:orderId>ORD-1024</ord:orderId>
    </ord:GetOrderRequest>
  </soap:Body>
</soap:Envelope>
~~~

Cần kiểm tra: đúng phần tử gốc **GetOrderRequest**, namespace chính xác, có **orderId** và giá trị tuân theo ràng buộc hợp đồng. Nếu đối tác yêu cầu header xác thực, timestamp hoặc mã tương quan, kiểm tra cả header đó và quy tắc bảo vệ dữ liệu nhạy cảm.

### 2.2. Phản hồi thành công

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:demo:orders:v1">
  <soap:Body>
    <ord:GetOrderResponse>
      <ord:orderId>ORD-1024</ord:orderId>
      <ord:status>CONFIRMED</ord:status>
    </ord:GetOrderResponse>
  </soap:Body>
</soap:Envelope>
~~~

Không chỉ khẳng định HTTP 200. Bài test cần xác nhận body thuộc đúng operation, đọc được **orderId** và **status**, trạng thái thuộc tập giá trị hợp lệ và ứng dụng chuyển đổi chính xác sang mô hình nội bộ.

### 2.3. Phản hồi lỗi SOAP 1.1

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:demo:orders:v1">
  <soap:Body>
    <soap:Fault>
      <faultcode>soap:Client</faultcode>
      <faultstring>Không tìm thấy đơn hàng</faultstring>
      <detail>
        <ord:OrderNotFoundFault>
          <ord:errorCode>ORDER_NOT_FOUND</ord:errorCode>
          <ord:orderId>ORD-1024</ord:orderId>
        </ord:OrderNotFoundFault>
      </detail>
    </soap:Fault>
  </soap:Body>
</soap:Envelope>
~~~

Ở đây cần xác nhận **faultcode**, **faultstring**, cấu trúc **detail** và mã **ORDER_NOT_FOUND** theo hợp đồng. Ứng dụng nên ánh xạ thành lỗi nghiệp vụ xác định được, thay vì mặc định coi mọi HTTP 500 là sự cố có thể retry.

**Lưu ý phiên bản:** SOAP 1.1 dùng namespace envelope ở trên, thường đi cùng Content-Type **text/xml** và header **SOAPAction**. SOAP 1.2 dùng namespace **http://www.w3.org/2003/05/soap-envelope**, thường dùng **application/soap+xml** và cấu trúc Fault khác (**Code/Reason/Detail**, các mã **Sender/Receiver**). Không trộn fixture hoặc khẳng định hỗ trợ cả hai phiên bản nếu endpoint chỉ công bố một phiên bản.

## 3. Chuẩn hóa hợp đồng và bộ mẫu kiểm thử

Nên lưu hợp đồng được chấp nhận vào source control, có phiên bản và quy trình cập nhật rõ ràng. Một bố cục ví dụ:

~~~text
src/test/resources/
  contracts/
    orders.wsdl
    orders.xsd
  soap/
    request-get-order.xml
    response-get-order.xml
    fault-order-not-found.xml
    invalid-missing-order-id.xml
    invalid-wrong-namespace.xml
~~~

Hợp đồng và fixture có nguồn gốc khác nhau: **WSDL/XSD** đến từ chủ sở hữu dịch vụ hoặc hợp đồng đã thống nhất; **fixture** do nhóm tích hợp tạo để tái hiện các tình huống. Tránh chỉnh fixture cho vừa với code đang lỗi mà không đối chiếu hợp đồng chuẩn.

Ví dụ một phần XSD cho *payload* trong SOAP Body:

~~~xml
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:ord="urn:demo:orders:v1"
           targetNamespace="urn:demo:orders:v1"
           elementFormDefault="qualified">

  <xs:simpleType name="OrderId">
    <xs:restriction base="xs:string">
      <xs:pattern value="ORD-[0-9]{4}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:simpleType name="OrderStatus">
    <xs:restriction base="xs:string">
      <xs:enumeration value="PENDING"/>
      <xs:enumeration value="CONFIRMED"/>
      <xs:enumeration value="CANCELLED"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="GetOrderRequest">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="orderId" type="ord:OrderId"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <xs:element name="GetOrderResponse">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="orderId" type="ord:OrderId"/>
        <xs:element name="status" type="ord:OrderStatus"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <xs:element name="OrderNotFoundFault">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="errorCode" type="xs:string"/>
        <xs:element name="orderId" type="ord:OrderId"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
~~~

Với schema này, request thiếu **orderId**, mã **1024** hoặc response chứa **UNKNOWN** ở trường **status** phải bị phát hiện. Riêng SOAP Fault, XSD của phần tử **OrderNotFoundFault** chưa chứng minh operation có khai báo fault đó: cần kiểm tra thêm message/fault/binding tương ứng trong WSDL.

Khi so XML, ưu tiên kiểm tra theo **namespace URI + local name** hoặc đối chiếu cấu trúc XML. Tiền tố **ord** và **o** có thể cùng trỏ đến một namespace; test so chuỗi nguyên văn thường báo sai khác giả vì khoảng trắng, thứ tự thuộc tính hoặc tên tiền tố.

Các trường hợp cần quyết định rõ từ hợp đồng:

- **Vắng mặt**, **phần tử rỗng** và **xsi:nil="true"** không mặc nhiên tương đương; kiểm tra **minOccurs**, **nillable**, default/fixed value.
- **xs:sequence** ràng buộc thứ tự các phần tử; serializer có thể làm sai thứ tự dù các trường đều xuất hiện.
- Date/time phải thống nhất kiểu, múi giờ và cách biểu diễn; decimal không được mất độ chính xác khi chuyển sang kiểu số nội bộ.
- Với SOAP Header, kiểm tra namespace, dữ liệu bắt buộc và hành vi khi thiếu/sai header. Nếu dùng WS-Security, cần kiểm thử chữ ký, timestamp và cấu hình xác thực ở đúng lớp thực thi.

## 4. Kiểm thử schema: phát hiện sai hợp đồng trước khi gọi mạng

Một kiểm thử XSD có thể chạy nhanh trong CI, không cần nhà cung cấp SOAP hoạt động. Ví dụ JUnit 5 dùng JAXP của Java; file **/contracts/orders.xsd** nằm trong test resources ở cấu trúc trên.

~~~java
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.io.InputStream;
import java.io.StringReader;
import javax.xml.XMLConstants;
import javax.xml.transform.stream.StreamSource;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;
import javax.xml.validation.Validator;
import org.junit.jupiter.api.Test;

class OrderSchemaTest {
    @Test
    void responsePayloadMustMatchXsd() throws Exception {
        String responsePayload = """
            <ord:GetOrderResponse xmlns:ord="urn:demo:orders:v1">
              <ord:orderId>ORD-1024</ord:orderId>
              <ord:status>CONFIRMED</ord:status>
            </ord:GetOrderResponse>
            """;

        SchemaFactory factory = SchemaFactory.newInstance(
                XMLConstants.W3C_XML_SCHEMA_NS_URI);
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        try (InputStream xsd = getClass()
                .getResourceAsStream("/contracts/orders.xsd")) {
            assertNotNull(xsd, "Thiếu contract orders.xsd");

            Schema schema = factory.newSchema(new StreamSource(xsd));
            Validator validator = schema.newValidator();
            validator.validate(new StreamSource(
                    new StringReader(responsePayload)));
        }
    }
}
~~~

**Điểm quan trọng:** XSD nghiệp vụ phía trên khai báo phần tử trong **SOAP Body**, vì vậy mã đang validate **responsePayload**, không phải toàn bộ SOAP Envelope. Nếu đọc XML envelope nguyên vẹn từ HTTP, phải parse an toàn rồi trích phần tử payload trước khi áp XSD nghiệp vụ; việc kiểm tra cấu trúc SOAP là một bước riêng. Khi schema có **xs:include/xs:import**, cấu hình system ID và resolver nội bộ phù hợp, không để validator tự tải tài nguyên không tin cậy qua mạng.

Bổ sung các ca âm để khẳng định validator *thực sự* phát hiện sai: thay **CONFIRMED** bằng **UNKNOWN**, xóa **orderId**, đổi namespace, đổi thứ tự phần tử. Trong JUnit có thể dùng **assertThrows(SAXException.class, ...)** cho mỗi payload không hợp lệ. Một test chỉ đưa dữ liệu đúng vào validator chưa đủ chứng minh luật ràng buộc được áp dụng chính xác.

## 5. Kiểm thử SOAP client trong Spring Boot

Với ứng dụng dùng **WebServiceTemplate**, Spring Web Services cung cấp **MockWebServiceServer** để giả lập hệ thống SOAP ở ranh giới client. Bài test xác minh request client phát ra và định nghĩa response/fault mà client nhận về, không cần gọi ra mạng.

Ví dụ dependency Gradle (dùng phiên bản do Spring Boot quản lý):

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-webservices'
testImplementation 'org.springframework.boot:spring-boot-starter-test'
testImplementation 'org.springframework.ws:spring-ws-test'
~~~

### 5.1. Request đúng và response thành công

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.ws.test.client.RequestMatchers.payload;
import static org.springframework.ws.test.client.ResponseCreators.withClientOrSenderFault;
import static org.springframework.ws.test.client.ResponseCreators.withPayload;

import java.util.Locale;
import org.junit.jupiter.api.Test;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.soap.client.SoapFaultClientException;
import org.springframework.ws.test.client.MockWebServiceServer;
import org.springframework.xml.transform.StringResult;
import org.springframework.xml.transform.StringSource;

class OrderSoapClientContractTest {
    private static final String REQUEST = """
        <ord:GetOrderRequest xmlns:ord="urn:demo:orders:v1">
          <ord:orderId>ORD-1024</ord:orderId>
        </ord:GetOrderRequest>
        """;

    private static final String RESPONSE = """
        <ord:GetOrderResponse xmlns:ord="urn:demo:orders:v1">
          <ord:orderId>ORD-1024</ord:orderId>
          <ord:status>CONFIRMED</ord:status>
        </ord:GetOrderResponse>
        """;

    private final WebServiceTemplate template = createTemplate();
    private final MockWebServiceServer server =
            MockWebServiceServer.createServer(template);

    private static WebServiceTemplate createTemplate() {
        WebServiceTemplate template = new WebServiceTemplate();
        template.setDefaultUri("http://example.test/soap/orders");
        return template;
    }

    @Test
    void sendsCorrectPayloadAndReadsResponse() {
        server.expect(payload(new StringSource(REQUEST)))
              .andRespond(withPayload(new StringSource(RESPONSE)));

        StringResult actual = new StringResult();
        boolean received = template.sendSourceAndReceiveToResult(
                new StringSource(REQUEST), actual);

        assertThat(received).isTrue();
        assertThat(actual.toString()).contains("CONFIRMED");
        server.verify();
    }

    @Test
    void exposesSoapFaultToErrorHandler() {
        server.expect(payload(new StringSource(REQUEST)))
              .andRespond(withClientOrSenderFault(
                      "Không tìm thấy đơn hàng",
                      Locale.forLanguageTag("vi-VN")));

        SoapFaultClientException exception = assertThrows(
                SoapFaultClientException.class,
                () -> template.sendSourceAndReceiveToResult(
                        new StringSource(REQUEST), new StringResult()));

        assertThat(exception.getFaultStringOrReason())
                .contains("Không tìm thấy đơn hàng");
        server.verify();
    }
}
~~~

Trong đoạn mẫu, **REQUEST** và **RESPONSE** là *phần tử payload nằm trong SOAP Body*. Spring Web Services tạo envelope cho lời gọi. **MockWebServiceServer** kiểm tra payload và mô phỏng phản hồi; test fault xác nhận cơ chế ném exception. Các đối tượng **REQUEST/RESPONSE** nên được chuyển thành fixture dùng chung để tránh mỗi test tự định nghĩa một hợp đồng khác nhau.

Đoạn test trên kiểm tra tầng SOAP client cơ bản; kiểm thử nghiệp vụ hoàn chỉnh cần thực sự gọi **client adapter của ứng dụng**, xác minh giá trị đã ánh xạ và kiểu lỗi miền nhận được. Nếu client tạo SOAPAction, WS-Addressing hoặc header bảo mật, cần thêm matcher/kiểm tra tương ứng. Kiểm tra chuỗi **CONFIRMED** chỉ để minh họa; trong bộ test chính thức nên parse XML và assert từng trường theo namespace/XPath, đồng thời validate response theo XSD.

### 5.2. Kiểm thử endpoint do ứng dụng cung cấp

Khi chính Spring Boot là SOAP provider với **@Endpoint**, dùng **MockWebServiceClient** để gửi request vào endpoint trong application context rồi kiểm tra payload trả về, không cần mở cổng HTTP.

~~~java
import static org.springframework.ws.test.server.RequestCreators.withPayload;
import static org.springframework.ws.test.server.ResponseMatchers.payload;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.ws.test.server.MockWebServiceClient;
import org.springframework.xml.transform.StringSource;

@SpringBootTest
class OrderSoapEndpointTest {
    @Autowired
    private ApplicationContext context;

    @Test
    void returnsOrderStatusFromEndpoint() {
        String request = """
            <ord:GetOrderRequest xmlns:ord="urn:demo:orders:v1">
              <ord:orderId>ORD-1024</ord:orderId>
            </ord:GetOrderRequest>
            """;
        String expected = """
            <ord:GetOrderResponse xmlns:ord="urn:demo:orders:v1">
              <ord:orderId>ORD-1024</ord:orderId>
              <ord:status>CONFIRMED</ord:status>
            </ord:GetOrderResponse>
            """;

        MockWebServiceClient client =
                MockWebServiceClient.createClient(context);
        client.sendRequest(withPayload(new StringSource(request)))
              .andExpect(payload(new StringSource(expected)));
    }
}
~~~

Ví dụ cần ứng dụng đã cấu hình **@Endpoint** và message dispatcher của Spring WS; dữ liệu đơn hàng phải được chuẩn bị qua mock repository hoặc dữ liệu test có kiểm soát. Bổ sung bài test endpoint trả SOAP Fault cho input không hợp lệ hoặc khi service nội bộ báo lỗi được hợp đồng hóa.

### 5.3. Khi ứng dụng dùng JAXB hoặc client sinh từ WSDL

Nếu adapter dùng **marshalSendAndReceive**, cần test qua đường đi thật của adapter: đối tượng domain → mapper → JAXB marshaller → SOAP request → unmarshaller → đối tượng miền. Đừng chỉ kiểm thử XML cố định vì lỗi phổ biến nằm ở annotation JAXB, thứ tự trường, enum, định dạng thời gian hoặc ánh xạ exception.

Quy trình phù hợp:

1. Khởi tạo client adapter với **WebServiceTemplate** và marshaller giống production.
2. Dùng **MockWebServiceServer** để bắt yêu cầu được marshal và gửi fixture response/fault.
3. So khớp cấu trúc/namespace của request, kiểm tra mô hình miền nhận được và quy tắc xử lý lỗi.
4. Kiểm tra mã sinh từ WSDL/XSD có được cập nhật có kiểm soát khi hợp đồng đổi phiên bản.

Nếu dữ liệu trả về được ghi cơ sở dữ liệu, phát sự kiện broker hoặc chuyển qua Spring Integration flow, cần thêm bài test xác minh tác động đó, đặc biệt với giao dịch, retry và chống xử lý trùng.

## 6. Kiểm thử lỗi hợp đồng và SOAP Fault có hệ thống

Không gom mọi tình huống lỗi thành một ca **throws Exception**. Bộ dữ liệu âm cần tách lỗi cấu trúc, lỗi giao thức, lỗi nghiệp vụ và lỗi hạ tầng.

| Tình huống | Kỳ vọng kiểm thử |
| --- | --- |
| XML thiếu **orderId**, giá trị sai pattern hoặc sai thứ tự | Bị XSD từ chối; không gọi/không ghi nghiệp vụ tiếp |
| Namespace hoặc tên operation sai | Bị phát hiện bởi XSD/WSDL hoặc tầng dispatch; có thông tin chẩn đoán rõ |
| SOAPAction hoặc Content-Type không đúng binding | Bị phát hiện ở lớp HTTP/SOAP; không ngầm coi là thành công |
| Response thiếu trường bắt buộc hoặc có enum lạ | Client không cập nhật trạng thái thành công; tạo lỗi tích hợp được phân loại |
| SOAP Fault **Client/Sender** chứa mã nghiệp vụ đã khai báo | Ánh xạ sang lỗi nghiệp vụ xác định; thông thường không retry cùng request |
| SOAP Fault **Server/Receiver** do lỗi tạm thời | Phân loại và cân nhắc retry có giới hạn khi thao tác an toàn |
| HTTP 500 không có SOAP Fault hợp lệ | Phân loại là lỗi giao thức/transport, không cố parse thành fault nghiệp vụ |
| Timeout, reset kết nối, TLS/DNS lỗi | Ném lỗi kết nối có ngữ cảnh; không giả định server chưa xử lý request |
| Đối tác đổi WSDL/XSD làm thay QName, kiểu, bắt buộc thêm field | Test tương thích fail và chặn triển khai trước khi có phương án chuyển đổi |
| XML chứa DTD, entity ngoài hoặc payload quá lớn | Parser từ chối nguồn nguy hiểm/không phù hợp giới hạn; không rò dữ liệu hoặc cạn tài nguyên |

Cần xác định chính sách retry theo **ý nghĩa của operation**. Với thao tác ghi như tạo thanh toán hay tạo đơn, timeout có thể xuất hiện *sau khi đối tác đã xử lý thành công*. Retry mù có thể tạo trùng; hãy dùng idempotency key nếu hợp đồng hỗ trợ, đối chiếu trạng thái hoặc cơ chế khử trùng lặp ở phía nhận. Với luồng có broker thông điệp, phải kiểm thử redelivery và việc ghi trạng thái/checkpoint để không phát lại tác vụ đã hoàn tất.

### SOAP Fault và thông tin cần assert

Một bài test fault đáng tin cậy kiểm tra đồng thời:

- Giao thức và phiên bản SOAP, **faultcode** hoặc **Code**, thông điệp lỗi, và XML **detail** nếu hợp đồng khai báo.
- Mã lỗi của đối tác, khả năng ánh xạ sang kiểu lỗi miền và hành vi API hoặc luồng xử lý phía trên.
- Quy tắc retry/no-retry, logging an toàn và correlation ID phục vụ truy vết.
- Tình huống detail bị thiếu hoặc sai schema: ứng dụng phải xử lý có kiểm soát, không làm mất nguyên nhân gốc.

Với SOAP 1.1, không nên buộc **HTTP 500 = lỗi kỹ thuật có thể retry**; cùng mã trạng thái này có thể mang SOAP Fault nghiệp vụ. Với SOAP 1.2, tên mã và cấu trúc fault khác. Hãy kiểm tra theo hợp đồng thực tế và quy tắc của adapter thay vì theo mỗi HTTP status.

## 7. Kiểm thử ranh giới HTTP và hệ thống thật

Mock của Spring WS kiểm tra tốt lớp message/client hoặc endpoint, nhưng không bao phủ đầy đủ TLS, kết nối HTTP, proxy, cấu hình timeout và tương tác với hệ thống đối tác. Thêm các cấp kiểm thử sau:

~~~mermaid
flowchart LR
    A["Fixture WSDL/XSD"] --> B["XSD và kiểm thử serializer"]
    B --> C["MockWebServiceServer hoặc MockWebServiceClient"]
    C --> D["HTTP mock server với envelope và header thật"]
    D --> E["Sandbox/contract test cùng đối tác"]
    E --> F["Quan sát sau triển khai"]
~~~

**HTTP mock server** (ví dụ WireMock hoặc MockWebServer) cho phép kiểm tra request envelope thực tế, đường dẫn, SOAPAction, Content-Type, response HTTP 200/500, timeout và XML lỗi được trả qua transport. Dùng fixture đủ cả **Envelope/Body/Header** tại lớp này. Một HTTP mock chỉ khớp chuỗi cũng không tự xác nhận tính hợp lệ XSD; nên ghép với schema validation.

**Sandbox/contract test** chạy trên môi trường kiểm soát của đối tác giúp phát hiện lệch phiên bản WSDL, certificate, routing, header bắt buộc và tập dữ liệu. Các ca test này cần dữ liệu không nhạy cảm, timeout rõ ràng, cleanup nếu có ghi dữ liệu, và không nên thay thế các test chạy nhanh trong CI.

Trước khi cho phép thay đổi hợp đồng, nên so sánh:

| Thay đổi từ provider | Đánh giá thường gặp |
| --- | --- |
| Thêm phần tử **optional** với minOccurs=0 | Có thể tương thích; vẫn test client cũ và parser có chấp nhận phần tử mới |
| Đổi namespace hoặc QName của operation | Thường là thay đổi phá vỡ tương thích |
| Chuyển phần tử optional thành bắt buộc | Có nguy cơ phá vỡ request cũ |
| Xóa trường hoặc đổi kiểu/enum | Có nguy cơ phá vỡ client hiện có |
| Đổi SOAP 1.1 thành SOAP 1.2, action hoặc binding | Cần kiểm chứng lại message factory, header và fault |
| Chỉ đổi tên tiền tố XML nhưng giữ namespace URI | Không nhất thiết thay đổi ngữ nghĩa; tránh test so chuỗi cứng |

**Consumer-driven contract** có ích khi nhóm tiêu thụ công bố các giả định quan trọng của mình cho provider. Tuy nhiên với SOAP, nguồn hợp đồng chính vẫn cần đối chiếu WSDL/XSD và những quy tắc nghiệp vụ đã thỏa thuận; bộ mẫu của consumer không thể thay thế toàn bộ hợp đồng provider.

## 8. Tích hợp vào quy trình phát triển và vận hành

Trong dự án Spring Boot có nhiều adapter, test SOAP nên đặt sát adapter ở module tích hợp và tiếp tục xác minh khi dữ liệu đi qua các tầng sau:

1. **Pull request:** chạy test parser/schema với cả fixture hợp lệ và không hợp lệ, unit test mapper/JAXB, **MockWebServiceServer** hoặc **MockWebServiceClient**.
2. **Integration test:** chạy HTTP mock để kiểm tra binding, header, TLS cấu hình, timeout, fault và retry; nếu flow ghi database hoặc phát message, kiểm tra transaction/idempotency.
3. **Trước triển khai:** đối chiếu WSDL/XSD đang dùng với phiên bản do đối tác công bố và chạy một số ca sandbox quan trọng.
4. **Sau triển khai:** theo dõi tỷ lệ SOAP Fault theo mã, lỗi validate/unmarshal, timeout, số lần retry, độ trễ và lượng message vào hàng chờ lỗi.

Các nguyên tắc thiết kế test và quan sát:

- **Phân loại lỗi ngay tại adapter**: contract violation, SOAP business fault, SOAP server fault, timeout/transport và lỗi mapping cần có kiểu hoặc mã lỗi riêng.
- **Giữ dữ liệu chẩn đoán vừa đủ**: operation, contract version, endpoint alias, correlation ID, fault code, latency, retry count. Che/loại bỏ token, chữ ký, dữ liệu định danh và nội dung nhạy cảm trước khi log.
- **Giới hạn nguồn XML không tin cậy**: cấu hình parser/validator chống DTD và external entity, giới hạn kích thước/độ sâu khi phù hợp. Test bảo mật độc lập với test XSD vì XML hợp lệ theo schema chưa đồng nghĩa an toàn.
- **Không phụ thuộc trạng thái ngoài ý muốn**: sử dụng fixture có phiên bản, thời gian cố định, dữ liệu khởi tạo/cleanup; không để test chạy theo thứ tự ngầm.
- **Giữ vết hợp đồng**: khi cập nhật WSDL/XSD, ghi rõ phiên bản, nguồn thay đổi, đánh giá tương thích và test nào chứng minh client cũ vẫn hoạt động.

## 9. Bài thực hành gợi ý

Dùng operation **GetOrder** và hợp đồng minh họa ở trên để xây một bộ kiểm thử nhỏ:

1. Viết một fixture request hợp lệ, response **CONFIRMED** và SOAP Fault **ORDER_NOT_FOUND**.
2. Viết ít nhất ba fixture sai: thiếu **orderId**, sai namespace, response có **status=UNKNOWN**. Validate mỗi fixture bằng XSD và xác nhận ba lỗi thực sự bị bắt.
3. Tạo một SOAP client adapter dùng **WebServiceTemplate**; kiểm tra request và kết quả ánh xạ với **MockWebServiceServer**.
4. Kiểm tra fault: adapter phải trả lỗi miền **OrderNotFound** (hoặc kiểu tương đương) và không retry lỗi nghiệp vụ đó.
5. Dùng HTTP mock gửi lại SOAP Fault hợp lệ với HTTP 500 và một HTTP 500 có body không phải SOAP. Chứng minh hai trường hợp được phân loại khác nhau.
6. Thay namespace hoặc đổi **orderId** thành trường bắt buộc mới trong bản hợp đồng thử nghiệm. Quan sát test nào thất bại và mô tả phương án giữ tương thích.

**Tiêu chí hoàn thành:** các request/response đúng được chấp nhận và ánh xạ chính xác; payload sai bị chặn; fault được phân loại theo hợp đồng; timeout/retry không dẫn tới xử lý trùng; sự thay đổi WSDL/XSD có khả năng phá vỡ tương thích bị phát hiện trước khi tích hợp với đối tác.

Một luồng SOAP đáng tin cậy không dừng ở việc “gửi được XML”. Nó cần chứng minh **đúng hợp đồng**, **đúng hành vi khi thành công hoặc thất bại**, và **đúng tác động lên phần còn lại của hệ thống Spring Boot**.
