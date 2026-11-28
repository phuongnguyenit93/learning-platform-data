# Thêm phiên bản hợp đồng mới và kiểm chứng client cũ vẫn hoạt động

## Mục tiêu thực hành

Trong hệ thống doanh nghiệp dùng **Spring Web Services (Spring-WS)**, một dịch vụ SOAP có thể phục vụ nhiều ứng dụng được phát triển và triển khai độc lập. Khi muốn bổ sung trường dữ liệu hoặc quy trình mới, đội phát triển phải chứng minh rằng **client đã phát hành từ hợp đồng cũ vẫn gọi được dịch vụ sau khi nâng cấp**, không cần sinh lại mã JAXB hay cập nhật ứng dụng.

Bài thực hành thuộc chương **Thực hành tổng hợp**, kết hợp thiết kế hợp đồng theo hướng **contract-first**, XSD/WSDL, ánh xạ JAXB, endpoint Spring-WS, SOAP client, SOAP Fault, interceptor và kiểm thử tích hợp. Sau bài này, người học cần có khả năng:

1. Xác định phần nào của XSD, WSDL và hành vi dịch vụ được xem là hợp đồng với client.
2. Bổ sung hợp đồng v2 cùng tồn tại với v1 mà không phá vỡ đường đi của client cũ.
3. Tổ chức namespace, endpoint và mã JAXB để hai phiên bản không ghi đè hoặc bắt nhầm thông điệp của nhau.
4. Dùng **mã client v1 đã đóng băng trước khi nâng cấp** để kiểm thử tương thích ngược qua HTTP/SOAP thực tế.
5. Xây dựng ma trận kiểm thử và tiêu chí chấp nhận đủ rõ để đưa vào CI/CD.

> **Phạm vi bài:** ví dụ dùng SOAP 1.1, Spring-WS và Java. Tên namespace, đường dẫn và lớp nghiệp vụ chỉ nhằm minh họa; khi triển khai phải đối chiếu với WSDL đang cung cấp cho các đối tác. Một hệ thống đã có WSDL v1 được công bố thì cần giữ nguyên hợp đồng đó thay vì thay bằng WSDL v1 mẫu trong bài.

## 1. Bài toán: mở rộng API tra cứu khách hàng

Giả sử dịch vụ đã cung cấp thao tác **GetCustomer**: client gửi mã khách hàng, server trả về mã và tên hiển thị. Một đối tác đã sinh client Java/JAXB từ WSDL v1 và tích hợp ổn định. Yêu cầu mới là bổ sung **requestId** để đối soát giao dịch và **loyaltyTier** trong phản hồi.

Ta chọn chiến lược **hai hợp đồng song song**, phân biệt qua XML namespace:

| Thành phần | Hợp đồng v1 (đã phát hành) | Hợp đồng v2 (bổ sung) |
|---|---|---|
| Namespace | urn:example:customer:v1 | urn:example:customer:v2 |
| Request | customerId | customerId, requestId (tùy chọn) |
| Response | customerId, displayName | customerId, displayName, loyaltyTier (tùy chọn) |
| Tài liệu WSDL | /ws/customer-v1.wsdl | /ws/customer-v2.wsdl |
| Địa chỉ gửi SOAP | /ws | /ws |
| Mã JAXB | package riêng cho v1 | package riêng cho v2 |
| Đối tượng kiểm chứng | Client v1 đã đóng băng | Client v2 mới tạo |

Trong ví dụ, cả hai hợp đồng dùng chung địa chỉ HTTP **/ws**, còn Spring-WS định tuyến theo **QName của phần tử gốc trong SOAP Body** (gồm namespace và tên phần tử). Đây là một lựa chọn thiết kế hợp lệ; nếu hệ thống hiện hữu có địa chỉ endpoint, SOAPAction hoặc cấu hình WS-Addressing riêng thì phải bảo toàn các giá trị v1 đã công bố.

**Điều kiện thành công quan trọng nhất:** client v1 đã biên dịch từ trước vẫn gửi request có namespace v1 và nhận response chỉ gồm các trường thuộc hợp đồng v1. Việc client mới đọc được trường v2 chưa đủ để chứng minh tương thích ngược.

## 2. Xác định ranh giới tương thích trước khi sửa

Khả năng tương thích không chỉ phụ thuộc vào việc Java có biên dịch được hay không. Một thay đổi có thể làm client cũ lỗi ở nhiều tầng:

| Thay đổi | Rủi ro đối với client v1 |
|---|---|
| Xóa/đổi tên phần tử hoặc thay namespace | JAXB cũ không còn nhận dạng được XML |
| Thêm phần tử bắt buộc vào request v1 | Client cũ không thể tạo request hợp lệ |
| Chèn trường mới vào response v1 | Client cũ có thể từ chối XML nếu bật XSD validation hoặc xử lý nghiêm ngặt |
| Đổi thứ tự trường trong xs:sequence | Thông điệp cũ có thể bị coi là sai schema |
| Đổi SOAPAction, binding hoặc SOAP 1.1 sang 1.2 | Client có thể bị lỗi định tuyến hoặc xử lý thông điệp |
| Đổi URL, service/port QName, cơ chế xác thực | Client có thể không kết nối hoặc không xác thực được |
| Đổi mã lỗi, SOAP Fault hoặc ý nghĩa trường | Client vẫn parse được nhưng xử lý nghiệp vụ sai |

**Nguyên tắc:** đã công bố v1 thì xem QName của phần tử, XSD v1, thông tin WSDL/binding, địa chỉ mà client thực sự sử dụng, chính sách bảo mật và hành vi nghiệp vụ là một cam kết tương thích. Đặt trường mới là **minOccurs="0"** có thể giúp mở rộng trong một số tình huống, nhưng không tự động bảo đảm mọi client cũ chấp nhận response có trường mới.

Trước khi bắt tay vào v2, lưu bộ mốc kiểm chứng gồm WSDL v1 và mọi XSD được import/include, một request/response SOAP v1 hợp lệ, cách tạo client v1, thông số kết nối và kết quả chạy client v1 trên bản server hiện tại. Giữ mã client đã sinh từ bộ WSDL này trong một module hoặc test fixture riêng; **không sinh lại client v1 từ source mới trong lúc kiểm thử tương thích**.

## 3. Thiết kế XSD v1 và v2

### 3.1. Đóng băng schema v1

Ví dụ dưới đây minh họa hình dạng XSD v1 đã phát hành, không phải chỉ thị sửa schema đang chạy:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    targetNamespace="urn:example:customer:v1"
    xmlns:tns="urn:example:customer:v1"
    elementFormDefault="qualified">

  <xs:element name="GetCustomerRequest">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="customerId" type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <xs:element name="GetCustomerResponse">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="customerId" type="xs:string"/>
        <xs:element name="displayName" type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
~~~

Giả sử file đã được công bố là **xsd/customer-v1.xsd**. Sau nâng cấp, giữ nguyên schema này, kể cả namespace, tên phần tử, kiểu dữ liệu, thứ tự trong xs:sequence và yêu cầu minOccurs/maxOccurs.

### 3.2. Tạo schema mới cho v2

Tạo **xsd/customer-v2.xsd** với namespace mới. Ta giữ ý nghĩa của các trường cũ, thêm trường mở rộng ở cuối mỗi chuỗi và cho phép bỏ qua khi không dùng:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    targetNamespace="urn:example:customer:v2"
    xmlns:tns="urn:example:customer:v2"
    elementFormDefault="qualified">

  <xs:element name="GetCustomerRequest">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="customerId" type="xs:string"/>
        <xs:element name="requestId" type="xs:string"
                    minOccurs="0"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <xs:element name="GetCustomerResponse">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="customerId" type="xs:string"/>
        <xs:element name="displayName" type="xs:string"/>
        <xs:element name="loyaltyTier" type="xs:string"
                    minOccurs="0"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
~~~

Các phần tử gốc dùng **anonymous complex type** trong ví dụ, nên công cụ JAXB/XJC thông thường sinh lớp gốc tương ứng có thể marshal/unmarshal trực tiếp. Nếu schema của dự án định nghĩa global element trỏ tới named complex type, JAXB có thể sinh **JAXBElement** và **ObjectFactory**; khi đó phải điều chỉnh chữ ký endpoint/client theo kết quả sinh mã thực tế.

**Lưu ý:** minOccurs="0" chỉ cho phép *bỏ qua* trường trong v2. Việc v1 client vẫn chạy đến từ việc server tiếp tục hỗ trợ **hợp đồng v1 nguyên vẹn**, chứ không phải vì v2 có các trường tùy chọn.

## 4. Công bố hai WSDL và tách mã JAXB

Với Spring-WS, có thể dùng **DefaultWsdl11Definition** để tạo WSDL từ XSD. Ví dụ cấu hình tối giản sau giả định ứng dụng chưa đăng ký **MessageDispatcherServlet** ở nơi khác:

~~~java
@Configuration
@EnableWs
public class CustomerWsConfiguration {
    private static final String V1_NS = "urn:example:customer:v1";
    private static final String V2_NS = "urn:example:customer:v2";

    @Bean
    ServletRegistrationBean<MessageDispatcherServlet> messageDispatcherServlet(
            ApplicationContext context) {
        MessageDispatcherServlet servlet = new MessageDispatcherServlet();
        servlet.setApplicationContext(context);
        servlet.setTransformWsdlLocations(true);
        return new ServletRegistrationBean<>(servlet, "/ws/*");
    }

    @Bean("customerV1Schema")
    XsdSchema customerV1Schema() {
        return new SimpleXsdSchema(
            new ClassPathResource("xsd/customer-v1.xsd"));
    }

    @Bean("customerV2Schema")
    XsdSchema customerV2Schema() {
        return new SimpleXsdSchema(
            new ClassPathResource("xsd/customer-v2.xsd"));
    }

    @Bean(name = "customer-v1")
    DefaultWsdl11Definition customerV1Wsdl(
            @Qualifier("customerV1Schema") XsdSchema schema) {
        DefaultWsdl11Definition wsdl = new DefaultWsdl11Definition();
        wsdl.setPortTypeName("CustomerPortV1");
        wsdl.setLocationUri("/ws");
        wsdl.setTargetNamespace(V1_NS);
        wsdl.setSchema(schema);
        return wsdl;
    }

    @Bean(name = "customer-v2")
    DefaultWsdl11Definition customerV2Wsdl(
            @Qualifier("customerV2Schema") XsdSchema schema) {
        DefaultWsdl11Definition wsdl = new DefaultWsdl11Definition();
        wsdl.setPortTypeName("CustomerPortV2");
        wsdl.setLocationUri("/ws");
        wsdl.setTargetNamespace(V2_NS);
        wsdl.setSchema(schema);
        return wsdl;
    }
}
~~~

Các import thuộc Spring Framework, Spring Boot và Spring-WS được lược bỏ để tập trung vào cơ chế. Trong dự án đã dùng Spring Boot auto-configuration cho servlet, tái sử dụng cấu hình hiện có để tránh đăng ký hai servlet. Với cấu hình minh họa, WSDL thường được truy cập qua **/ws/customer-v1.wsdl** và **/ws/customer-v2.wsdl**.

Nếu WSDL v1 đang được cung cấp dưới dạng **WSDL tĩnh** hoặc được tùy biến binding, SOAPAction, service/port, địa chỉ hay policy, hãy giữ nguyên tài liệu và cách publish v1 đó; chỉ thêm cách publish v2 tương ứng. Việc tái sinh WSDL v1 bằng cấu hình mới có thể vô tình làm thay đổi hợp đồng dù XSD không đổi.

Cấu hình sinh JAXB phải dùng **hai bộ nguồn và hai package tách biệt**, ví dụ:

| Đầu vào sinh mã | Package đầu ra |
|---|---|
| customer-v1.xsd | com.example.soap.v1 |
| customer-v2.xsd | com.example.soap.v2 |

Không sinh v2 vào package v1, vì hai schema đều có phần tử **GetCustomerRequest** và **GetCustomerResponse**. Đối với kiểm thử tương thích, giữ thêm artifact client cũ riêng (ví dụ package **legacy.v1**) được tạo từ WSDL v1 trước khi sửa server; đây mới là phép kiểm chứng độc lập với mã mới.

## 5. Xây dựng endpoint phục vụ đồng thời hai phiên bản

Spring-WS có thể chọn phương thức xử lý dựa trên **@PayloadRoot**. Hai phương thức có cùng localPart vẫn khác nhau vì namespace:

~~~java
@Endpoint
public class CustomerEndpoint {
    private static final String V1_NS = "urn:example:customer:v1";
    private static final String V2_NS = "urn:example:customer:v2";

    private final CustomerRepository repository;

    public CustomerEndpoint(CustomerRepository repository) {
        this.repository = repository;
    }

    @PayloadRoot(namespace = V1_NS, localPart = "GetCustomerRequest")
    @ResponsePayload
    public com.example.soap.v1.GetCustomerResponse getCustomerV1(
            @RequestPayload com.example.soap.v1.GetCustomerRequest request) {
        Customer customer = repository.findById(request.getCustomerId());

        var response = new com.example.soap.v1.GetCustomerResponse();
        response.setCustomerId(customer.id());
        response.setDisplayName(customer.displayName());
        return response;
    }

    @PayloadRoot(namespace = V2_NS, localPart = "GetCustomerRequest")
    @ResponsePayload
    public com.example.soap.v2.GetCustomerResponse getCustomerV2(
            @RequestPayload com.example.soap.v2.GetCustomerRequest request) {
        Customer customer = repository.findById(request.getCustomerId());

        var response = new com.example.soap.v2.GetCustomerResponse();
        response.setCustomerId(customer.id());
        response.setDisplayName(customer.displayName());
        response.setLoyaltyTier(customer.loyaltyTier());
        // requestId có thể được ghi vào log tương quan theo chính sách hệ thống.
        return response;
    }
}

// Ví dụ mô hình nghiệp vụ chung cho hai phiên bản:
record Customer(String id, String displayName, String loyaltyTier) {}
interface CustomerRepository {
    Customer findById(String customerId);
}
~~~

Đoạn mã giả định ứng dụng đã cung cấp bean triển khai CustomerRepository và đã cấu hình marshaller/unmarshaller JAXB cho hai namespace; tên package cần khớp với kết quả XJC thực tế.

Hai endpoint dùng chung tầng nghiệp vụ, nhưng **mỗi phiên bản tự xây response từ lớp JAXB riêng**. Vì vậy response v1 không chứa trường loyaltyTier, trong khi response v2 có thể chứa trường đó. Không trả thẳng đối tượng v2 rồi hy vọng JAXB cũ bỏ qua phần XML mở rộng.

Khi dùng schema validation interceptor, phải bảo đảm thông điệp v1 được kiểm tra bằng schema v1 và thông điệp v2 bằng schema v2. Nếu cấu hình một interceptor validate mọi request bằng XSD v1, request v2 sẽ bị từ chối dù endpoint v2 đã đăng ký. Hãy định tuyến validation theo phiên bản hoặc kiểm tra cả hai QName/schema theo thiết kế của dự án.

## 6. Kiểm tra bằng SOAP request/response thực tế

### 6.1. Request của client cũ

Client v1 tiếp tục gửi phần tử gốc thuộc namespace v1:

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:c="urn:example:customer:v1">
  <soapenv:Header/>
  <soapenv:Body>
    <c:GetCustomerRequest>
      <c:customerId>C-001</c:customerId>
    </c:GetCustomerRequest>
  </soapenv:Body>
</soapenv:Envelope>
~~~

Response mà client v1 nhận được phải tiếp tục khớp với schema v1:

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:c="urn:example:customer:v1">
  <soapenv:Body>
    <c:GetCustomerResponse>
      <c:customerId>C-001</c:customerId>
      <c:displayName>An Nguyen</c:displayName>
    </c:GetCustomerResponse>
  </soapenv:Body>
</soapenv:Envelope>
~~~

### 6.2. Request của client mới

Client v2 dùng namespace mới và có thể cung cấp requestId:

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:c="urn:example:customer:v2">
  <soapenv:Body>
    <c:GetCustomerRequest>
      <c:customerId>C-001</c:customerId>
      <c:requestId>REQ-2026-001</c:requestId>
    </c:GetCustomerRequest>
  </soapenv:Body>
</soapenv:Envelope>
~~~

Phản hồi v2 có thể chứa loyaltyTier:

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:c="urn:example:customer:v2">
  <soapenv:Body>
    <c:GetCustomerResponse>
      <c:customerId>C-001</c:customerId>
      <c:displayName>An Nguyen</c:displayName>
      <c:loyaltyTier>GOLD</c:loyaltyTier>
    </c:GetCustomerResponse>
  </soapenv:Body>
</soapenv:Envelope>
~~~

Trong ví dụ, phần Body là yếu tố Spring-WS dùng để ánh xạ endpoint. Nếu client tích hợp thực tế yêu cầu SOAPAction, WS-Addressing, token bảo mật hoặc chữ ký số thì phải đưa các header tương ứng vào bộ fixture, không chỉ so sánh SOAP Body.

## 7. Viết kiểm thử chứng minh client v1 thực sự còn hoạt động

### 7.1. Phép kiểm chứng quyết định: chạy binary/client v1 đã đóng băng

Một bài test chỉ tạo request bằng lớp **com.example.soap.v1** mới sinh từ source hiện tại có thể bỏ sót lỗi tương thích, bởi cả server lẫn client đều vô tình thay đổi cùng lúc. Hãy dùng thư viện **legacy.v1** được biên dịch trước khi phát triển v2 và triển khai test qua HTTP với server mới.

Ví dụ JUnit 5 và Spring Boot 3 (giả định dữ liệu thử nghiệm **C-001** luôn tồn tại):

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CustomerContractCompatibilityIT {

    @LocalServerPort
    private int port;

    private WebServiceTemplate templateFor(Class<?>... boundTypes)
            throws Exception {
        Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
        marshaller.setClassesToBeBound(boundTypes);
        marshaller.afterPropertiesSet();

        WebServiceTemplate template = new WebServiceTemplate();
        template.setMarshaller(marshaller);
        template.setUnmarshaller(marshaller);
        return template;
    }

    @Test
    void frozenV1ClientStillWorksAfterServerUpgrade() throws Exception {
        WebServiceTemplate client = templateFor(
            legacy.v1.GetCustomerRequest.class,
            legacy.v1.GetCustomerResponse.class);

        var request = new legacy.v1.GetCustomerRequest();
        request.setCustomerId("C-001");

        Object raw = client.marshalSendAndReceive(
            "http://localhost:" + port + "/ws", request);

        var response = assertInstanceOf(
            legacy.v1.GetCustomerResponse.class, raw);
        assertEquals("C-001", response.getCustomerId());
        assertEquals("An Nguyen", response.getDisplayName());
    }

    @Test
    void newV2ClientReceivesNewField() throws Exception {
        WebServiceTemplate client = templateFor(
            com.example.soap.v2.GetCustomerRequest.class,
            com.example.soap.v2.GetCustomerResponse.class);

        var request = new com.example.soap.v2.GetCustomerRequest();
        request.setCustomerId("C-001");
        request.setRequestId("REQ-2026-001");

        Object raw = client.marshalSendAndReceive(
            "http://localhost:" + port + "/ws", request);

        var response = assertInstanceOf(
            com.example.soap.v2.GetCustomerResponse.class, raw);
        assertEquals("C-001", response.getCustomerId());
        assertEquals("GOLD", response.getLoyaltyTier());
    }
}
~~~

Ví dụ lược bỏ import. Sử dụng **org.springframework.boot.test.web.server.LocalServerPort** trên Spring Boot 3; điều chỉnh namespace/import khi dự án dùng phiên bản khác. Đối với JAXB schema thực tế sinh JAXBElement thay vì @XmlRootElement, hãy dùng ObjectFactory để bọc request và unwrap response. Artifact legacy.v1 phải được tạo từ **WSDL v1 cũ đã lưu**, không phụ thuộc kết quả sinh mã từ v2.

Nếu mục tiêu là kiểm chứng tương thích nhị phân, chạy thêm **ứng dụng client v1 đã build trước nâng cấp** với classpath cũ, không build lại; test dùng source cũ nhưng biên dịch mới vẫn chưa kiểm soát được mọi lỗi tương thích ở mức binary và cấu hình runtime.

### 7.2. Kiểm tra WSDL/schema và các trường hợp âm

Cần kết hợp test client ở trên với kiểm tra hợp đồng XML:

- **WSDL v1:** so sánh với bản gốc đã lưu các QName của service, port, portType, operation, message, binding, SOAPAction, location URI và XSD import. Nếu WSDL động viết lại host theo môi trường, chuẩn hóa phần host trước khi so sánh; không bỏ qua thay đổi thực sự của contract.
- **XSD v1:** xác nhận QName, kiểu, số lần xuất hiện và thứ tự phần tử không đổi; validate request và response v1 mẫu bằng schema v1.
- **XSD v2:** validate request v2 cả khi có và khi không có requestId; validate response v2 cả khi có và khi không có loyaltyTier.
- **Client v1:** gọi qua transport và middleware thực tế (proxy, authentication, WS-Security nếu có); xác nhận dữ liệu nghiệp vụ và SOAP Fault quan trọng có cùng ý nghĩa như trước.
- **Client v2:** xác nhận trường mới được marshal/unmarshal đúng, dữ liệu chung nhất quán với v1.
- **Thông điệp lỗi:** gửi phần tử gốc với namespace không được khai báo hoặc payload sai schema, xác nhận dịch vụ trả lỗi có kiểm soát thay vì định tuyến nhầm. Tình huống chỉ phát sinh SOAP Fault khi ứng dụng/interceptor được cấu hình xử lý tương ứng; không giả định mọi lỗi đều tự động thành SOAP Fault.

Có thể dùng **MockWebServiceClient** để test mapping/validation ở tầng Spring-WS, đồng thời duy trì test qua HTTP với client v1 thật. Mock test đơn lẻ không chứng minh WSDL được publish đúng URL, cấu hình transport, chứng chỉ hay WS-Security tương thích.

### 7.3. Ma trận kiểm thử tối thiểu

| Trường hợp | Client và payload | Kết quả cần đạt |
|---|---|---|
| C1 | Client v1 đóng băng → server đã nâng cấp, namespace v1 | PASS; phản hồi đúng XSD v1, không cần thay thư viện client |
| C2 | Client v2 → server đã nâng cấp, namespace v2 | PASS; đọc được loyaltyTier |
| C3 | Client v2 không gửi requestId | PASS nếu phù hợp với XSD v2; requestId là tùy chọn |
| C4 | Request v1 thiếu customerId | Bị phát hiện bởi bước validation theo schema v1 |
| C5 | Request có namespace không hỗ trợ | Không được chuyển nhầm vào endpoint v1/v2; có phản hồi lỗi nhất quán |
| C6 | Client v1 bật strict XSD validation với response v1 | PASS; response không bị trộn trường của v2 |
| C7 | Client v1 gọi qua cấu hình auth/WS-Security đã dùng trước nâng cấp | PASS; chữ ký, token, chứng chỉ và policy phù hợp |
| C8 | WSDL v1 và XSD v1 trước/sau nâng cấp | Không có thay đổi phá hợp đồng |

Nếu dịch vụ cung cấp nhiều thao tác hoặc nhiều đối tác, mở rộng ma trận cho **mọi operation v1** và ít nhất một bộ fixture đặc trưng cho từng client, gồm cả tình huống lỗi nghiệp vụ. Một test GetCustomer thành công không đại diện cho toàn bộ hợp đồng.

## 8. Phân tích lỗi thường gặp khi triển khai song song

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Client v1 bị lỗi unmarshal sau nâng cấp | Server trả response v2 cho request v1; QName/schema bị đổi | Capture SOAP Body và đối chiếu namespace, XSD v1 |
| Nhận lỗi không tìm thấy endpoint | @PayloadRoot sai namespace/localPart; interceptor xử lý sai | In QName thực tế của payload và kiểm tra mapping |
| Client v2 gọi được endpoint nhưng bị lỗi validation | Cấu hình XSD interceptor chỉ chấp nhận v1 | Kiểm tra schema áp dụng theo phiên bản |
| JAXB sinh trùng lớp hoặc ghi đè | Cùng package/output directory cho v1 và v2 | Tách tác vụ sinh mã và package |
| /ws/customer-v1.wsdl thay đổi sau nâng cấp | Vô tình tái sinh WSDL v1 với port/binding mới | So sánh snapshot WSDL v1 đã đóng băng |
| SOAP Body đúng nhưng client cũ vẫn lỗi | SOAPAction, auth, WS-Security, certificate hoặc HTTP endpoint đã đổi | Kiểm thử qua đường kết nối thực tế và đối chiếu header/policy |
| Client parse được nhưng dữ liệu sai | v1 và v2 dùng quy tắc nghiệp vụ không nhất quán | So sánh bất biến nghiệp vụ và test dữ liệu biên |

Nếu hệ thống ký XML bằng WS-Security, cần kiểm tra chữ ký trên thông điệp thực tế, namespace, thuật toán được chấp nhận, timestamp và chuỗi chứng chỉ. Thay đổi cấu trúc Body hoặc policy có thể làm chữ ký xác minh thất bại ngay cả khi schema mới hợp lệ. Với SOAP Fault, hãy giữ nguyên các fault code/detail mà client cũ đang dựa vào, hoặc bổ sung ánh xạ tương thích có chủ đích.

## 9. Quy trình phát hành và tiêu chí nghiệm thu

Áp dụng trình tự sau cho một thay đổi contract-first:

1. **Chụp baseline v1:** lưu WSDL/XSD, request/response và bản client v1 đang hoạt động; ghi nhận điểm kết nối, SOAPAction, security policy.
2. **Thêm v2 độc lập:** tạo XSD/WSDL v2, package JAXB mới và endpoint mapping theo QName; giữ nguyên cấu hình phục vụ v1.
3. **Chạy kiểm thử cục bộ:** validate XSD, test endpoint và chạy client v1 cũ trên server mới trước khi đưa phiên bản mới cho đối tác.
4. **Kiểm thử trên môi trường tích hợp:** xác minh địa chỉ publish, proxy, xác thực, SOAP Fault, logging và WS-Security với cấu hình gần production.
5. **Triển khai và giám sát:** theo dõi lưu lượng v1/v2, tỷ lệ lỗi SOAP Fault, lỗi unmarshal, độ trễ và tình trạng kết nối của các client cũ. Chỉ lên kế hoạch ngừng v1 sau khi có thỏa thuận di chuyển rõ ràng với từng đối tác.

Một đợt nâng cấp được xem là **đạt** khi đáp ứng đồng thời:

- WSDL/XSD v1 và những đặc tính kết nối đã cam kết với đối tác vẫn tương thích.
- Binary/client v1 cũ gọi được bản server mới qua đường kết nối thực tế, nhận đúng response v1 và xử lý lỗi như trước.
- Client v2 dùng được phần mở rộng và không ảnh hưởng định tuyến, validation hay bảo mật của v1.
- Ma trận C1–C8 chạy đạt, được tự động hóa trong pipeline phù hợp với dự án.
- Có thể quay về bản triển khai trước hoặc tắt endpoint v2 mà không phải thay đổi client v1.

**Bài tập mở rộng:** bổ sung thao tác cập nhật khách hàng vào cả hai WSDL, giữ chính sách SOAP Fault v1 ổn định, rồi chạy cùng ma trận với client v1 được sinh trước khi bổ sung thao tác. Thử cố ý đổi namespace v1 hoặc thêm trường bắt buộc vào request v1 để quan sát test nào phát hiện lỗi, sau đó khôi phục hợp đồng và xác nhận toàn bộ bộ kiểm thử trở lại trạng thái đạt.
