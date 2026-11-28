# Lỗi adapter: chữ ký phương thức và kiểu tham số không được hỗ trợ

## 1. Nhận diện lỗi adapter

Một SOAP request có thể đúng HTTP, có Envelope hợp lệ và payload đúng QName nhưng vẫn không gọi được endpoint. Một nguyên nhân thường gặp là method trong class `@Endpoint` có chữ ký mà Spring-WS không biết cách cung cấp tham số hoặc xử lý giá trị trả về.

~~~java
@Endpoint
public class ShipmentEndpoint {
    @PayloadRoot(
        namespace = "urn:example:shipment:v1",
        localPart = "GetShipmentStatusRequest")
    @ResponsePayload
    public GetShipmentStatusResponse getStatus(
            GetShipmentStatusRequest request,
            String partnerCode) {
        // ...
    }
}
~~~

Java reflection chỉ cho biết method nhận các kiểu nào; nó không tự suy ra nguồn dữ liệu cho từng tham số. Framework cần biết request lấy từ SOAP Body, partnerCode lấy từ SOAP Header hay nguồn khác, và resolver nào chuyển message context thành đúng kiểu.

Bài thuộc chương **Quan sát và chẩn đoán** của **SPRING_WEB_SERVICES**. Module học SOAP contract-first với XSD/WSDL, JAXB, endpoint, client, SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích.

Sau bài này, bạn có thể phân biệt EndpointMapping/EndpointAdapter/resolvers/return handlers, đọc stack trace, viết signature được hỗ trợ, phân biệt resolver với JAXB errors, mở rộng resolver có kiểm soát và kiểm thử qua Spring-WS context.

## 2. Endpoint invocation gồm nhiều bước

~~~mermaid
flowchart TD
    A[HTTP SOAP request] --> B[MessageDispatcherServlet]
    B --> C[EndpointMapping]
    C --> D[EndpointInvocationChain]
    D --> E[EndpointInterceptor]
    E --> F[EndpointAdapter]
    F --> G[MethodEndpoint]
    G --> H[MethodArgumentResolver list]
    H --> I[Invoke method]
    I --> J[MethodReturnValueHandler list]
    J --> K[SOAP response or Fault]
~~~

| Thành phần | Trách nhiệm |
| --- | --- |
| EndpointMapping | Tìm endpoint cho message |
| EndpointAdapter | Gọi loại endpoint đã tìm được |
| DefaultMethodEndpointAdapter | Gọi annotated method endpoint |
| MethodArgumentResolver | Tạo giá trị cho từng tham số |
| MethodReturnValueHandler | Xử lý giá trị trả về |
| Marshaller/Unmarshaller | Chuyển object và XML |

Mapping thường xảy ra trước khi method được chọn. Resolver lỗi khi framework không thể tạo argument. JAXB lỗi thường xảy ra sau khi resolver đã chọn cách đọc payload nhưng quá trình chuyển đổi XML thất bại.

## 3. EndpointMapping không phải EndpointAdapter

`@PayloadRoot` ánh xạ payload root QName sang method:

~~~java
@PayloadRoot(
    namespace = "urn:example:shipment:v1",
    localPart = "GetShipmentStatusRequest")
@ResponsePayload
public GetShipmentStatusResponse getStatus(
        @RequestPayload GetShipmentStatusRequest request) {
    // ...
}
~~~

Sai namespace/local name có thể khiến Spring-WS không tìm được endpoint method: đây là mapping issue. Nếu QName match nhưng adapter không resolve được tham số hoặc return value, đây là invocation/signature issue.

Không sửa @PayloadRoot để chữa lỗi kiểu tham số; cũng không thay JAXB class khi nguyên nhân thật là thiếu resolver.

## 4. DefaultMethodEndpointAdapter hoạt động thế nào?

`DefaultMethodEndpointAdapter` là adapter mặc định dành cho annotated method endpoints. Nó dùng `MethodArgumentResolver` để tạo argument và `MethodReturnValueHandler` để xử lý kết quả.

~~~text
MethodEndpoint
  parameter 0 -> resolver supports? -> resolve
  parameter 1 -> resolver supports? -> resolve
  invoke Java method
    return value -> handler supports? -> write response
~~~

Nếu không resolver nào hỗ trợ một parameter, framework không thể cung cấp argument. Nếu không handler nào hỗ trợ return value, response không thể được xử lý như mong muốn.

Đừng nhầm adapter với MessageDispatcherServlet, PayloadRootAnnotationMethodEndpointMapping, Jaxb2Marshaller hoặc WebServiceTemplate.

## 5. Chữ ký endpoint tối giản

Với contract-first JAXB, dạng dễ kiểm soát là một payload request và một response object:

~~~java
@Endpoint
public class ShipmentEndpoint {
    private static final String NS = "urn:example:shipment:v1";
    private final ShipmentApplicationService service;

    public ShipmentEndpoint(ShipmentApplicationService service) {
        this.service = service;
    }

    @PayloadRoot(namespace = NS,
        localPart = "GetShipmentStatusRequest")
    @ResponsePayload
    public GetShipmentStatusResponse getStatus(
            @RequestPayload GetShipmentStatusRequest request) {
        ShipmentStatusView view =
                service.getStatus(request.getShipmentId());
        return toResponse(view);
    }
}
~~~

Request/response thường là JAXB types generate từ XSD hoặc class có JAXB annotations. Service, view và mapper là types do ứng dụng định nghĩa. Chữ ký làm rõ nguồn và đích serialization: payload được bind vào request object, method trả object được serialize thành response payload.

## 6. Các nguồn tham số phổ biến

### 6.1. SOAP Body

`@RequestPayload` đánh dấu tham số được bind từ payload trong SOAP Body. Kiểu cần resolver tương ứng, ví dụ JAXB object, XML `Source` hoặc DOM theo cấu hình.

~~~java
@ResponsePayload
@PayloadRoot(namespace = "urn:example:shipment:v1",
    localPart = "CreateShipmentRequest")
public CreateShipmentResponse create(
        @RequestPayload CreateShipmentRequest request) {
    // ...
}
~~~

`Source` trong Java 17 thuộc `javax.xml.transform.Source`; nó không phải toàn bộ SOAP Envelope. Đối chiếu resolver list của Spring-WS/JAXB version.

### 6.2. SOAP Header

Không thêm tham số `String partnerCode` rồi kỳ vọng framework tự đọc header. Nếu cần SOAP header, dùng `SoapHeader` hoặc header element qua resolver phù hợp:

~~~java
import org.springframework.ws.soap.SoapHeader;

@ResponsePayload
@PayloadRoot(namespace = "urn:example:shipment:v1",
    localPart = "GetShipmentStatusRequest")
public GetShipmentStatusResponse getStatus(
        @RequestPayload GetShipmentStatusRequest request,
        SoapHeader soapHeader) {
    return serviceResponse(request, soapHeader);
}
~~~

Chữ ký cụ thể phải được kiểm với SOAP version và resolver thực tế. Header không tự động đáng tin: tenant, partner, role hoặc user ID phải được xác thực/ủy quyền theo security policy.

### 6.3. MessageContext

~~~java
import org.springframework.ws.context.MessageContext;

@PayloadRoot(namespace = "urn:example:shipment:v1",
    localPart = "InspectRequest")
public void inspect(
        @RequestPayload InspectRequest request,
        MessageContext messageContext) {
    // Truy cập request/response message qua API.
}
~~~

MessageContext cho phép endpoint làm việc với context của message. Chỉ nhận raw message khi thực sự cần SOAP-specific facilities; không đẩy transport internals vào business service.

### 6.4. XPath

`@XPathParam` bind giá trị từ XPath expression:

~~~java
@PayloadRoot(namespace = "urn:example:shipment:v1",
    localPart = "FindShipmentRequest")
@ResponsePayload
public FindShipmentResponse find(
        @XPathParam("/sh:FindShipmentRequest/sh:shipmentId")
        String shipmentId) {
    return service.find(shipmentId);
}
~~~

Prefix trong XPath phải được map đến URI namespace đúng theo cấu hình. Prefix trong XPath không tự lấy từ prefix bất kỳ trong XML instance. Kiểm expression và namespace context trước khi kết luận resolver lỗi kiểu.

## 7. Những kiểu tham số thường gây lỗi

| Chữ ký | Vấn đề | Cách sửa |
| --- | --- | --- |
| String không annotation | Không rõ nguồn payload/header | Dùng JAXB + @RequestPayload hoặc resolver |
| Custom DTO không binding | Không unmarshal được payload | Generate JAXB type/cấu hình marshalling |
| HttpServletRequest | Không phải SOAP endpoint argument mặc định | Đưa HTTP logic ra filter/transport |
| Map<String,Object> | Không có resolver tương ứng | Dùng DTO/custom resolver |
| Object làm request | Không rõ payload representation | Dùng concrete JAXB/XML type |
| InputStream cho Body | Không có binding tùy ý mặc định | Dùng Source/DOM/attachment API |
| byte[] cho MTOM | Không tự động là attachment resolver | Cấu hình attachment mapping |
| ResponseEntity | Spring MVC type, không phải SOAP return handler mặc định | Trả SOAP DTO/XML |
| CompletableFuture | Không mặc định là SOAP async response | Thiết kế async transport riêng |
| Domain DTO chưa marshal được | JAXB không hỗ trợ object graph | Map sang SOAP response DTO |

Các kiểu này không bị cấm tuyệt đối: ứng dụng có thể thêm resolver/handler. Điều quan trọng là runtime phải thực sự hỗ trợ chúng.

## 8. Resolver failure khác JAXB unmarshalling

**Không có resolver hỗ trợ parameter:** adapter không biết cách tạo argument; thường liên quan type, annotation hoặc registration. Method có thể chưa được gọi.

**Resolver đã chạy nhưng unmarshalling lỗi:** JAXB/marshaller không map được XML vào type. Nguyên nhân có thể là root QName, JAXB annotations, JAXBElement, context path, schema/type mismatch hoặc XML invalid.

`UnmarshalException` không giống “no suitable argument resolver”. Đừng đổi parameter type nếu nguyên nhân là JAXB context không biết root element.

## 9. Return value cũng là một nửa chữ ký

Method có thể resolve hết tham số nhưng thất bại khi xử lý return value.

~~~java
@ResponsePayload
@PayloadRoot(namespace = "urn:example:shipment:v1",
    localPart = "GetShipmentStatusRequest")
public ShipmentStatusView getStatus(
        @RequestPayload GetShipmentStatusRequest request) {
    return service.getStatus(request.getShipmentId());
}
~~~

`ShipmentStatusView` có thể là domain projection không được JAXB marshaller hỗ trợ. Map sang generated response type:

~~~java
@ResponsePayload
@PayloadRoot(namespace = "urn:example:shipment:v1",
    localPart = "GetShipmentStatusRequest")
public GetShipmentStatusResponse getStatus(
        @RequestPayload GetShipmentStatusRequest request) {
    ShipmentStatusView view =
            service.getStatus(request.getShipmentId());
    return responseMapper.toSoapResponse(view);
}
~~~

Phân biệt không có return handler với marshalling thất bại sau khi handler chọn marshaller. `void` chỉ phù hợp flow one-way/message-context được thiết kế rõ; không mặc định mọi void là response hợp lệ.

## 10. Annotation phải khớp contract

| Annotation | Vai trò |
| --- | --- |
| @Endpoint | Đánh dấu endpoint component |
| @PayloadRoot | Map payload QName |
| @RequestPayload | Payload-bound argument |
| @ResponsePayload | Response payload return |
| @SoapAction | Map theo SOAPAction khi hỗ trợ |
| @XPathParam | Bind giá trị XPath |
| @Namespace | Khai báo namespace context theo usage |

Dùng annotations từ `org.springframework.ws.server.endpoint.annotation` và kiểm imports theo version. Thiếu namespace URI hoặc annotation không được resolver hỗ trợ đều có thể tạo lỗi.

## 11. Khi nào cần custom MethodArgumentResolver?

Cần resolver riêng khi endpoint muốn nhận abstraction không được resolver mặc định hỗ trợ và giá trị đó có nguồn rõ trong message/request context.

Ví dụ annotation:

~~~java
@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
public @interface PartnerContext {
}

public record VerifiedPartnerContext(
        String partnerId,
        Set<String> authorities) {
}
~~~

Resolver phải match annotation và type cụ thể:

~~~java
public final class PartnerContextArgumentResolver
        implements MethodArgumentResolver {

    @Override
    public boolean supportsParameter(MethodParameter parameter) {
        return parameter.hasParameterAnnotation(PartnerContext.class)
                && parameter.getParameterType()
                    .equals(VerifiedPartnerContext.class);
    }

    @Override
    public Object resolveArgument(
            MessageContext messageContext,
            MethodParameter parameter) {
        return verifiedContextProvider.currentContext();
    }
}
~~~

Đây là skeleton; imports, interface signatures và provider cần khớp Spring-WS version. Context phải đến từ authentication đã xác minh, không parse raw partnerId/role trong SOAP Body rồi tin là identity.

Resolver phải fail closed: hỗ trợ đúng annotation/type, không tạo giá trị giả khi context thiếu, ném exception phù hợp, không log dữ liệu nhạy cảm và có tests cho context hiện tại/request lifecycle. Không viết resolver nhận mọi Object hoặc String vì dễ bắt nhầm parameter.

## 12. Đăng ký resolver và giữ default behavior

Spring-WS configuration có hook thêm argument resolvers. Ví dụ theo API version cung cấp `WsConfigurerAdapter`:

~~~java
@Configuration
@EnableWs
public class SoapConfiguration extends WsConfigurerAdapter {
    private final PartnerContextArgumentResolver partnerResolver;

    public SoapConfiguration(PartnerContextArgumentResolver partnerResolver) {
        this.partnerResolver = partnerResolver;
    }

    @Override
    public void addArgumentResolvers(
            List<MethodArgumentResolver> resolvers) {
        resolvers.add(partnerResolver);
    }
}
~~~

Kiểm Javadoc trước khi dùng class adapter; configuration API có thể thay đổi/deprecate. Các version có `WsConfigurationSupport` cung cấp hook `addArgumentResolvers(List)`.

Không tự tạo `DefaultMethodEndpointAdapter` thứ hai nếu framework đã đăng ký adapter mặc định, trừ khi kiểm soát rõ bean override và toàn bộ default resolvers. Adapter thay thế thiếu JAXB/header resolvers có thể làm hỏng endpoint khác.

## 13. Version differences và custom return handler

`DefaultMethodEndpointAdapter` có lists `setMethodArgumentResolvers(...)` và `setMethodReturnValueHandlers(...)`. Hook cấu hình qua `WsConfigurationSupport` cho phép thêm resolver/handler. Một số legacy custom-resolver accessors bị deprecated trong version mới.

Không copy blog sample Spring-WS 2.x sang project 4.x/5.x mà không kiểm compile/Javadoc. Đối chiếu dependency, Java baseline, class cấu hình và resolver runtime.

Nếu cần custom `MethodReturnValueHandler`, match type/annotation cụ thể, chuyển object thành response theo contract, kiểm null/empty, tránh ghi response hai lần và test SOAP versions. Thường map wrapper sang JAXB response ở endpoint dễ duy trì hơn. Không tạo handler bắt mọi return type rồi serialize toString().

## 14. Chẩn đoán theo stack trace và runtime context

| Dấu hiệu | Giai đoạn | Điều cần kiểm |
| --- | --- | --- |
| No endpoint found | Mapping | QName, namespace, SOAPAction |
| No adapter for endpoint | Adapter selection | Endpoint type, adapter beans |
| Unsupported parameter/cannot resolve | Argument resolution | Type, annotation, resolver list |
| JAXB UnmarshalException | Payload conversion | JAXB context, root QName, XSD |
| MarshallingException | Return serialization | Return type, marshaller |
| SOAP Fault từ interceptor | Security/validation | WSS4J/XSD/interceptor |
| Method invocation target exception | Java method đã chạy | Root cause business method |

Tên exception có thể đổi theo version/wrapping layer. Đọc root cause và stack position, không suy đoán từ message tổng quát.

Kiểm application context: adapter có tồn tại không, configuration `@EnableWs` đã load chưa, resolver có trong list không, profile condition có bỏ bean không, thứ tự resolver có bắt nhầm parameter không và marshaller có nằm trong chain không.

Log endpoint/method, parameter index/type, selected resolver class và correlation ID; không log raw SOAP body, UsernameToken, Authorization, private key hoặc PII.

## 15. Quy trình debug từng tham số

1. Ghi index, Java type và annotations từng parameter.
2. Xác định nguồn mong muốn: Body, Header, XPath, context hay verified actor.
3. Chọn resolver hỗ trợ type/annotation.
4. Kiểm resolver có trong runtime adapter.
5. Nếu payload, kiểm XSD/JAXB context/root QName.
6. Nếu header, kiểm QName/namespace và SOAP version.
7. Nếu XPath, kiểm namespace map/expression.
8. Nếu custom type, unit test supports/resolve.
9. Kiểm return handler sau khi arguments resolve.
10. Gửi fixture qua integration endpoint và assert response/Fault.

Thay một tham số mỗi lần giúp xác định nguyên nhân. Đừng thêm Object/Map/String tạm để xem có chạy không.

## 16. Unit và integration tests

Test `supportsParameter` cho custom resolver cả positive lẫn negative case: đúng annotation/type được hỗ trợ; unannotated String bị từ chối. Test `resolveArgument` trả verified context, thiếu context thì fail closed và không reuse context giữa messages.

Integration test phải dùng application context thật có `@EnableWs`, endpoint và `MockWebServiceClient`:

~~~java
@SpringBootTest
class ShipmentEndpointAdapterTest {
    @Autowired
    ApplicationContext applicationContext;
    private MockWebServiceClient client;

    @BeforeEach
    void setUp() {
        client = MockWebServiceClient.createClient(applicationContext);
    }

    @Test
    void mapsRequestAndReturnsSoapResponse() {
        client.sendRequest(withPayload(new ClassPathResource(
                "soap/get-status-request.xml")))
            .andExpect(noFault())
            .andExpect(payload(new ClassPathResource(
                "soap/get-status-response.xml")));
    }
}
~~~

Imports, test dependencies và fixture resources cần khai báo trong project. Test này kiểm dispatch/adapter trong context; muốn kiểm HTTP headers, TLS hoặc WS-Security transport thật cần integration qua HTTP/TLS server.

Test marshaller riêng: marshal response, kiểm root QName, validate XSD, unmarshal lại và so business fields. Sau đó test endpoint để xác minh return handler được chọn.

## 17. Các lỗi cấu hình thường gặp

- Thay toàn resolver list bằng list chỉ có custom resolver.
- Tạo adapter mới thiếu default JAXB/Source/header resolvers.
- Custom resolver nhận mọi String/Object.
- Không bật @EnableWs hoặc configuration sai profile.
- Marshaller được cấu hình ở bean khác nhưng adapter không dùng.
- Annotation/type không khớp resolver.
- Dùng API deprecated/đổi version.
- Nhiều adapter khiến thứ tự lựa chọn khác dự tính.

Ưu tiên thêm resolver qua default configuration hook thay vì thay cả adapter. Nếu phải tự tạo adapter, khôi phục default behavior theo version và integration test.

Đổi signature đơn giản hơn khi business string có thể là field JAXB request, context lấy từ trusted security context, return type là domain view map sang JAXB response, hoặc servlet details không thuộc SOAP contract. Chỉ viết resolver khi type có ý nghĩa ở boundary và được tái sử dụng.

## 18. Anti-pattern và quy trình triển khai

Anti-pattern:
- Tham số không annotation/không resolver: không rõ nguồn.
- String làm payload object: thiếu binding.
- HttpServletRequest trong endpoint: trộn transport với SOAP.
- Trả domain entity: lộ persistence model và có thể không marshal được.
- Tạo adapter mới tùy tiện: mất default resolvers.
- Resolver hỗ trợ mọi Object: nhận nhầm parameter.
- Tin tenant/role từ SOAP Header: header chưa chứng minh identity.
- Chữa JAXB error bằng đổi adapter: sai boundary.
- Chỉ unit test supportsParameter: chưa chứng minh registration.
- Copy sample cũ: API có thể đổi.
- Nuốt resolver exception: che lỗi.

Quy trình:
1. Xác định request QName và method được mapping.
2. Đọc signature, parameter annotations và return type.
3. Phân loại mapping, adapter selection, argument resolution, JAXB, return handling hoặc business error.
4. Kiểm Spring-WS version và runtime DefaultMethodEndpointAdapter.
5. Xác định resolver/handler cho từng parameter/return.
6. Dùng JAXB DTO ở contract boundary.
7. Bind Header/XPath/context bằng cơ chế rõ ràng.
8. Thêm custom resolver qua hook đúng version nếu cần.
9. Giữ default resolver/handler lists.
10. Unit test support/resolve/return.
11. Integration test qua MessageDispatcher/adapter.
12. Kiểm WSDL/XSD, SOAP 1.1/1.2, Fault và WS-Security.
13. Bật diagnostics có giới hạn, không log credentials/PII.
14. Chạy regression suite sau thay đổi.

## 19. Bài tập thực hành

1. **Signature không hợp lệ:** thêm String partnerCode không annotation, quan sát lỗi và sửa bằng resolver rõ ràng.
2. **JAXB root mismatch:** sai @XmlRootElement/namespace, phân biệt unmarshalling với unsupported parameter.
3. **Return type không marshal:** trả ShipmentStatusView, sau đó map sang JAXB response và validate XSD.
4. **Custom resolver:** tạo @PartnerContext, test annotation/type, verified context và fail closed.
5. **Registration:** thêm resolver qua WsConfigurer hook và chứng minh default JAXB resolver vẫn chạy.
6. **XPath:** cấu hình prefix sai rồi sửa namespace context.
7. **SOAP Header:** test missing, duplicate, wrong QName và tenant value không đáng tin.
8. **Version compatibility:** chạy signature/resolver tests trên các Spring-WS versions được hỗ trợ.
9. **Fault behavior:** thiếu security context thì map Fault an toàn.
10. **Regression corpus:** gửi SOAP fixtures hợp lệ/không hợp lệ qua adapter trong CI.

## 20. Checklist trước production

- [ ] @PayloadRoot QName đúng namespace URI/local name.
- [ ] Phân biệt EndpointMapping và EndpointAdapter.
- [ ] DefaultMethodEndpointAdapter tồn tại/cấu hình đúng.
- [ ] Mọi parameter có nguồn dữ liệu và resolver rõ.
- [ ] Payload dùng type/annotation được hỗ trợ.
- [ ] Header dùng SOAP header resolver đúng version.
- [ ] XPath có namespace context chính xác.
- [ ] Không thêm String/Object/Map/servlet request/stream tùy tiện.
- [ ] Custom types có resolver đăng ký.
- [ ] Resolver match annotation + exact type.
- [ ] Return type được handler/marshaller hỗ trợ.
- [ ] Domain result map sang SOAP DTO theo contract.
- [ ] JAXB UnmarshalException phân biệt resolver failure.
- [ ] MarshallingException phân biệt unsupported return handler.
- [ ] Không vô tình thay default resolver/handler lists.
- [ ] Configuration API khớp version, không dựa accessor deprecated.
- [ ] Security context đến từ verified identity, không raw SOAP Header.
- [ ] Unit tests support/resolve và integration tests adapter có.
- [ ] Fixtures validate bằng đúng WSDL/XSD.
- [ ] SOAP 1.1/1.2 và Fault mapping được kiểm.
- [ ] Logs không chứa credentials, PII hay SOAP body nhạy cảm.

## 21. Tài liệu tham khảo

- [Spring Web Services — Reference Documentation](https://docs.spring.io/spring-ws/reference/): annotated endpoints, method signatures, payload/header binding và XPath.
- [DefaultMethodEndpointAdapter — Spring-WS 4.1.2 Javadoc](https://www.springframework.org/spring-ws/docs/4.1.2/api/org/springframework/ws/server/endpoint/adapter/DefaultMethodEndpointAdapter.html): resolver/return handler lists.
- [MethodArgumentResolver — Spring-WS API](https://docs.spring.io/spring-ws/docs/current/api/org/springframework/ws/server/endpoint/adapter/method/MethodArgumentResolver.html): strategy resolve endpoint parameters.
- [WsConfigurationSupport — Spring-WS 4.0.x Javadoc](https://docs.spring.io/spring-ws/docs/4.0.x/api/org/springframework/ws/config/annotation/WsConfigurationSupport.html): addArgumentResolvers/default adapter configuration.
- [Spring-WS endpoint adapter package](https://docs.spring.io/spring-ws/docs/4.0.9/api/org/springframework/ws/server/endpoint/adapter/package-summary.html): adapter classes và legacy adapters.
- [Spring Web Services — Testing](https://docs.spring.io/spring-ws/reference/testing.html): MockWebServiceClient/MockWebServiceServer.
- [Jakarta XML Binding — Specification](https://jakarta.ee/specifications/xml-binding/): binding và XML/Java mapping; đối chiếu javax/jakarta namespace.
- [W3C — XML Schema](https://www.w3.org/TR/xmlschema11-1/): element/type/cardinality/nillable.
- [W3C — Namespaces in XML](https://www.w3.org/TR/xml-names/): namespace URI và expanded QName.
- [OASIS — WS-Security 1.1.1](https://docs.oasis-open.org/wss-m/wss/v1.1.1/os/wss-SOAPMessageSecurity-v1.1.1-os.html): security headers, tokens và integrity.

Ví dụ là patterns/khung code; custom resolver imports/configuration hooks cần đối chiếu đúng Spring-WS/JDK/JAXB versions. Không phải mọi parameter/return type đều bị cấm tuyệt đối: ứng dụng có thể bổ sung resolver/handler, nhưng runtime phải đăng ký chúng.

## 22. Tổng kết

**Lỗi adapter về chữ ký method xảy ra khi Spring-WS không thể cung cấp argument hoặc xử lý return value bằng resolver/handler đã đăng ký.** EndpointMapping chọn method theo QName/SOAPAction; DefaultMethodEndpointAdapter gọi method; MethodArgumentResolver bind parameter; MethodReturnValueHandler chuyển kết quả thành SOAP response. Xác định đúng boundary tránh sửa nhầm WSDL, JAXB hoặc routing.

Với contract-first **SPRING_WEB_SERVICES**, ưu tiên signature rõ: JAXB request qua @RequestPayload, SOAP Header/XPath/message context qua resolver tương ứng, response DTO được marshal theo XSD. Khi cần kiểu riêng, thêm custom resolver/handler có matching annotation/type chính xác qua configuration hook của Spring-WS version đang dùng; giữ default resolvers và viết integration tests. Không coi Java type là được hỗ trợ chỉ vì compile.

Đọc stack trace để phân biệt resolver failure, JAXB unmarshal/marshal failure và exception từ business method; kiểm signature, runtime resolver list, return handler và application context. Khi mỗi tham số có nguồn rõ và mỗi return value có handler, adapter error sẽ dễ tái hiện, chẩn đoán và sửa có kiểm soát.
