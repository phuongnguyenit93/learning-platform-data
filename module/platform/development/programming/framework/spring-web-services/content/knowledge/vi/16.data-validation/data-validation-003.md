# Kiểm tra yêu cầu, phản hồi và lựa chọn phạm vi áp dụng

## 1. Validation trong SOAP contract-first nhằm bảo vệ điều gì?

Trong Spring Web Services (Spring-WS), quy trình phát triển **contract-first** lấy XSD/WSDL làm hợp đồng giữa bên cung cấp dịch vụ và bên gọi SOAP. XSD xác định QName của các phần tử XML, kiểu dữ liệu, thứ tự, sự xuất hiện, giá trị hợp lệ; WSDL mô tả operation, input/output message, SOAP binding và endpoint address.

Khi triển khai `@Endpoint`, có hai hướng dữ liệu cần kiểm tra:

1. **Request validation**: XML payload do SOAP client gửi đến có đúng XSD hay không, trước khi dữ liệu được xử lý nghiệp vụ.
2. **Response validation**: XML payload mà server tạo ra có đúng XSD đã công bố hay không, trước khi gửi trở lại đối tác.

Hai hướng này có mục tiêu khác nhau. Request validation bảo vệ hệ thống khỏi đầu vào không tuân hợp đồng. Response validation phát hiện server hoặc bộ chuyển đổi Java–XML tạo ra dữ liệu sai hợp đồng, ngăn regression làm hỏng SOAP client đã sinh mã từ WSDL.

Bài thuộc chương **Kiểm tra dữ liệu** của module **SPRING_WEB_SERVICES**. Ta sẽ tập trung vào **kiểm tra yêu cầu, phản hồi và lựa chọn phạm vi áp dụng**, sử dụng `PayloadValidatingInterceptor`, XSD, JAXB/OXM, SOAP Fault và kiểm thử tương thích. Nội dung cũng giải thích vì sao XML Schema validation **không thay thế** WS-Security, xác thực chứng chỉ, phân quyền, kiểm tra nghiệp vụ hoặc chính sách bảo mật XML parser.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích khác biệt giữa kiểm tra request, response và toàn bộ SOAP Envelope.
- Tạo một XSD có ràng buộc và cấu hình Spring-WS kiểm tra dữ liệu XML.
- Hiểu vai trò `PayloadValidatingInterceptor`, `validateRequest` và `validateResponse`.
- Lựa chọn phạm vi validation cho một endpoint, một namespace/version, một ứng dụng hoặc một giai đoạn triển khai.
- Phân biệt lỗi XSD với lỗi SOAP version, SOAP Header, JAXB binding và nghiệp vụ.
- Xây dựng test hợp lệ/không hợp lệ cho cả chiều request lẫn response.
- Thiết kế SOAP Fault, quan sát và xử lý lỗi mà không làm lộ dữ liệu nhạy cảm.
- Đánh giá tác động hiệu năng và tương thích trước khi bật response validation trên hệ thống cũ.

## 2. Validation nằm ở vị trí nào trong Spring-WS?

Một luồng request/response được tổ chức khái quát:

~~~mermaid
flowchart TD
    A["SOAP client"] --> B["HTTP/SOAP transport"]
    B --> C["MessageDispatcherServlet"]
    C --> D["SOAP Envelope, headers, endpoint mapping"]
    D --> E{"Request payload hợp XSD?"}
    E -->|"Không"| F["Chính sách lỗi: SOAP Fault / từ chối"]
    E -->|"Có"| G["JAXB / DOM / XPath"]
    G --> H["@Endpoint"]
    H --> I["Domain service và nghiệp vụ"]
    I --> J["XML response payload"]
    J --> K{"Response payload hợp XSD?"}
    K -->|"Không"| L["Xử lý lỗi server, không âm thầm trả thành công"]
    K -->|"Có"| M["SOAP response"]
~~~

Sơ đồ minh họa **lớp trách nhiệm**, không khẳng định thứ tự tuyệt đối giữa mọi endpoint mapping, interceptor, security handler và marshalling adapter. Thứ tự thật phụ thuộc phiên bản Spring-WS và các interceptor đã đăng ký.

Phân biệt:

| Lớp kiểm tra | Kiểm tra điều gì? | Có phải XSD validation không? |
|---|---|---|
| HTTP/SOAP transport | Content-Type, HTTP method, kích thước request, SOAP version | Không |
| SOAP header / WS-Security | Chữ ký, token, timestamp, chứng chỉ, quyền | Không |
| Payload root mapping | QName để chọn `@Endpoint` | Không |
| **XSD validation** | Cấu trúc/kiểu/constraint của XML payload | **Có** |
| JAXB/OXM | Ánh xạ XML sang Java và ngược lại | Không tự bảo đảm toàn bộ XSD |
| Domain validation | Order có tồn tại, người gọi có quyền, trạng thái hợp lệ | Không |
| Response XSD validation | XML server tạo ra có đúng schema hay không | **Có** |

**Điểm then chốt:** Một endpoint được gọi thành công không chứng minh request hợp XSD. Tương tự, JAXB marshal được một object không chứng minh response XML đúng ràng buộc của hợp đồng.

## 3. Hợp đồng XSD xuyên suốt: GetOrder

Giả sử dịch vụ tra cứu đơn hàng có global elements `GetOrderRequest` và `GetOrderResponse` trong namespace `urn:example:orders:v1`.

File `src/main/resources/xsd/orders-v1.xsd` minh họa:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:ord="urn:example:orders:v1"
    targetNamespace="urn:example:orders:v1"
    elementFormDefault="qualified">

    <xs:simpleType name="OrderIdType">
        <xs:restriction base="xs:string">
            <xs:minLength value="1"/>
            <xs:maxLength value="30"/>
            <xs:pattern value="ORD-[0-9]+"/>
        </xs:restriction>
    </xs:simpleType>

    <xs:simpleType name="OrderStatusType">
        <xs:restriction base="xs:string">
            <xs:enumeration value="PENDING"/>
            <xs:enumeration value="PAID"/>
            <xs:enumeration value="CANCELLED"/>
        </xs:restriction>
    </xs:simpleType>

    <xs:element name="GetOrderRequest">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="orderId"
                            type="ord:OrderIdType"/>
                <xs:element name="includeHistory"
                            type="xs:boolean"
                            minOccurs="0"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>

    <xs:element name="GetOrderResponse">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="orderId"
                            type="ord:OrderIdType"/>
                <xs:element name="status"
                            type="ord:OrderStatusType"/>
                <xs:element name="note"
                            type="xs:string"
                            minOccurs="0"
                            nillable="true"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
~~~

Hợp đồng này chứa các dạng ràng buộc thường gặp:

- **QName** root và children: `urn:example:orders:v1`.
- **`xs:sequence`**: phần tử phải đúng thứ tự.
- **`minOccurs="0"`**: `includeHistory` và `note` là optional.
- **`nillable="true"`**: chỉ `note` cho phép dạng `xsi:nil="true"`.
- **`pattern`**: `orderId` phải bắt đầu bằng `ORD-` và theo sau bởi ít nhất một chữ số.
- **`enumeration`**: `status` chỉ nhận PENDING, PAID hoặc CANCELLED.
- **`xs:boolean`**: `true`, `false`, `1`, `0` là những lexical forms phù hợp.

XSD không kiểm tra xem `ORD-2048` có tồn tại trong cơ sở dữ liệu, người gọi có được phép xem nó không, hoặc response có đúng trạng thái giao dịch thực tế hay không. Đó là công việc của domain service và chính sách bảo mật.

### 3.1. Request hợp lệ

~~~xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
    <ord:orderId>ORD-2048</ord:orderId>
    <ord:includeHistory>true</ord:includeHistory>
</ord:GetOrderRequest>
~~~

Dù client dùng prefix khác hoặc default namespace, message vẫn hợp lệ nếu QName và cấu trúc không thay đổi.

### 3.2. Response hợp lệ

~~~xml
<ord:GetOrderResponse xmlns:ord="urn:example:orders:v1">
    <ord:orderId>ORD-2048</ord:orderId>
    <ord:status>PAID</ord:status>
</ord:GetOrderResponse>
~~~

`note` có thể vắng mặt. Response này vẫn phải theo thứ tự `orderId` trước `status`.

### 3.3. Request sai: cần bị chặn

~~~xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
    <ord:orderId>ABC</ord:orderId>
</ord:GetOrderRequest>
~~~

XML well-formed nhưng `orderId` không khớp `ORD-[0-9]+`. Nếu chỉ gọi `getOrderId()` từ JAXB object, endpoint vẫn có thể nhận chuỗi `ABC` trừ khi validation được cấu hình.

### 3.4. Response sai: cũng phải được phát hiện

~~~xml
<ord:GetOrderResponse xmlns:ord="urn:example:orders:v1">
    <ord:orderId>ORD-2048</ord:orderId>
    <ord:status>DELIVERED</ord:status>
</ord:GetOrderResponse>
~~~

`DELIVERED` không thuộc enumeration của `OrderStatusType`. Server tạo ra response này nghĩa là chính server đang vi phạm contract đã công bố. Client sinh mã theo enum v1 có thể thất bại khi unmarshal hoặc xử lý không đúng.

## 4. Request validation: từ chối dữ liệu không hợp XSD trước nghiệp vụ

Request validation là hàng rào ở ranh giới XML của dịch vụ. Với `GetOrderRequest`, nó có thể phát hiện:

| Dữ liệu gửi đến | Theo XSD v1 | Lý do |
|---|---|---|
| `orderId = ORD-2048` | Hợp lệ | Đúng pattern |
| Không có `orderId` | Không hợp lệ | `minOccurs` mặc định là 1 |
| `orderId = ABC` | Không hợp lệ | Sai pattern |
| `orderId = ""` | Không hợp lệ | Sai minLength và pattern |
| Có `includeHistory = 1` | Hợp lệ | Lexical form của `xs:boolean` |
| Có `includeHistory = maybe` | Không hợp lệ | Sai `xs:boolean` |
| `includeHistory` đứng trước `orderId` | Không hợp lệ | Sai `xs:sequence` |
| Root namespace v2 | Không hợp lệ với contract v1 | QName khác |
| Đổi prefix `ord` thành `x` nhưng giữ URI | Hợp lệ | Prefix không thuộc QName |
| `orderId xsi:nil="true"` | Không hợp lệ | `orderId` không nillable |

Một điều dễ bỏ sót: JAXB generated classes có thể cho phép code Java gán `orderId = null` hoặc `status = "DELIVERED"` tùy binding. Việc class được sinh từ XSD không tự động khiến mọi thao tác Java tuân thủ XSD.

### 4.1. Điều gì xảy ra khi request bị từ chối?

Khi `PayloadValidatingInterceptor` phát hiện payload sai, hành vi mong muốn là:

1. Không cho request sai tiếp tục đến logic nghiệp vụ tạo side effect.
2. Trả lỗi SOAP theo chính sách của server/binding.
3. Ghi log/metric đủ để vận hành, nhưng không lộ XML nhạy cảm, token hoặc stack trace.
4. Cho phép client phân biệt “request sai hợp đồng” với “lỗi tạm thời của server” nếu chính sách Fault cho phép.

Cách Spring-WS tạo SOAP Fault, fault code, detail và HTTP response phụ thuộc implementation/phiên bản và cấu hình interceptor. Hãy kiểm thử bằng SOAP request thực tế, không đoán từ tên exception.

## 5. Response validation: bảo vệ client trước lỗi từ server

Response validation kiểm tra **payload đi ra**. Nó có giá trị đặc biệt khi:

- Có nhiều developer cùng sửa endpoint hoặc mapper.
- Server dùng JAXB, DOM, XPath và custom `XmlAdapter`.
- Thêm field/enum mới có nguy cơ phá vỡ SOAP client cũ.
- Hệ thống có hợp đồng WSDL/XSD được đối tác sinh code và sử dụng lâu dài.
- Có nhiều response path: thành công, nhánh business, cache, legacy adapter.
- Thay đổi version Java, Spring-WS, JAXB runtime hoặc cấu hình marshal.

Những lỗi response validation có thể phát hiện:

| Response XML | Vi phạm |
|---|---|
| Thiếu `status` | Required element bị thiếu |
| `status = DELIVERED` | Enumeration chưa được contract v1 chấp nhận |
| `orderId` sai pattern | Type constraint |
| `status` xuất hiện trước `orderId` | Sai sequence |
| Root `GetOrderResult` | Sai global element QName |
| Child `status` không namespace | Sai namespace |
| `note xsi:nil="true"` | Hợp lệ nếu nil đúng kiểu và element không chứa nội dung |
| Thêm `debugInfo` ngoài schema | Element không được khai báo |

**Cảnh báo:** Response validation không đảm bảo rằng `status=PAID` phản ánh đúng trạng thái trong database. Nó chỉ kiểm tra giá trị **nằm trong tập cho phép của XSD**. Domain assertions cần được kiểm thử riêng.

### 5.1. Có nên bật response validation mọi lúc?

Không có một câu trả lời cho mọi dịch vụ. Việc validate response thêm chi phí CPU/bộ nhớ và có thể làm lộ những lỗi tương thích chưa từng được phát hiện ở hệ thống cũ. Với hệ thống cần tính toàn vẹn hợp đồng cao, bật response validation ở runtime có thể đáng giá. Với hệ thống có tải rất lớn, có thể chọn:

- Bật đầy đủ ở development, CI và staging.
- Bật trong production cho nhóm operation quan trọng hoặc có rủi ro cao.
- Dùng smoke/contract tests bắt buộc trước deploy và metric quan sát sau deploy.
- Dùng response validation trực tiếp ở layer OXM đối với các component sinh XML ngoài endpoint.

Một khi đã quyết định phạm vi, cần **ghi rõ chính sách** chứ không để cấu hình default tình cờ quyết định hành vi.

## 6. PayloadValidatingInterceptor và ranh giới kiểm tra

Spring-WS cung cấp `PayloadValidatingInterceptor` để kiểm tra **payload** của SOAP message theo XSD.

Nó không tự làm những việc sau:

- Xác thực toàn bộ SOAP Envelope và Header theo quy tắc WS-Security.
- Kiểm tra tính hợp lệ của certificate, chữ ký XML hoặc thời hạn token.
- Kiểm tra mọi HTTP header và SOAPAction/action.
- Thay thế `@PayloadRoot` định tuyến endpoint.
- Thay thế domain validation, authentication và authorization.
- Thay thế cả hai bước JAXB marshal/unmarshal.

Nó hoạt động tại tầng `EndpointInterceptor` của Spring-WS; khi được đăng ký đúng, framework gọi nó quanh việc xử lý endpoint tương ứng.

### 6.1. Hai cờ phải khai báo tường minh

| Cấu hình | Ý nghĩa |
|---|---|
| `setValidateRequest(true)` | Kiểm tra request payload nhận vào |
| `setValidateRequest(false)` | Không kiểm tra request payload qua interceptor này |
| `setValidateResponse(true)` | Kiểm tra response payload do endpoint tạo |
| `setValidateResponse(false)` | Không kiểm tra response payload qua interceptor này |

Nên chỉ rõ cả hai cờ thay vì dựa vào giá trị mặc định của phiên bản framework.

Ví dụ:

~~~java
PayloadValidatingInterceptor validator =
    new PayloadValidatingInterceptor();

validator.setXsdSchema(ordersSchema);
validator.setValidateRequest(true);
validator.setValidateResponse(true);
~~~

Đoạn code chưa hoàn chỉnh nếu chưa đăng ký `validator` vào interceptor chain được `MessageDispatcherServlet` sử dụng.

### 6.2. Khi một request bị từ chối trước endpoint

Về trách nhiệm, request validation phải ngăn dữ liệu sai chạy vào domain service. Nhưng hệ thống có nhiều interceptor, security policies hoặc endpoint mappings có thể xử lý lỗi theo những cách khác nhau. Test nên assert trực tiếp:

- SOAP request sai XSD bị từ chối.
- Domain service/mock **không được gọi**.
- Không có database write hoặc queue publish.
- SOAP Fault và HTTP response khớp chính sách đã thiết kế.

Không kết luận “validator chạy” chỉ vì log có một dòng liên quan XSD.

## 7. Cấu hình Java: kiểm tra cả request và response

Giả định ứng dụng dùng Spring Boot/Spring-WS, có dependency Spring XML và file `xsd/orders-v1.xsd` trong classpath.

Khai báo bean schema:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.xml.xsd.SimpleXsdSchema;
import org.springframework.xml.xsd.XsdSchema;

@Configuration
public class OrdersSchemaConfiguration {

    @Bean(name = "ordersSchema")
    public XsdSchema ordersSchema() {
        return new SimpleXsdSchema(
            new ClassPathResource("xsd/orders-v1.xsd")
        );
    }
}
~~~

Đăng ký interceptor:

~~~java
import java.util.List;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.config.annotation.WsConfigurer;
import org.springframework.ws.server.EndpointInterceptor;
import org.springframework.ws.soap.server.endpoint.interceptor.PayloadValidatingInterceptor;
import org.springframework.xml.xsd.XsdSchema;

@Configuration
@EnableWs
public class OrdersValidationConfiguration implements WsConfigurer {

    private final XsdSchema ordersSchema;

    public OrdersValidationConfiguration(
            @Qualifier("ordersSchema") XsdSchema ordersSchema) {
        this.ordersSchema = ordersSchema;
    }

    @Override
    public void addInterceptors(
            List<EndpointInterceptor> interceptors) {

        PayloadValidatingInterceptor validator =
            new PayloadValidatingInterceptor();

        validator.setXsdSchema(ordersSchema);

        // Đặt tường minh chính sách của dịch vụ.
        validator.setValidateRequest(true);
        validator.setValidateResponse(true);

        interceptors.add(validator);
    }
}
~~~

Giải thích:

1. `SimpleXsdSchema` cung cấp XML Schema cho validator.
2. `@EnableWs` kích hoạt annotation-based Spring-WS infrastructure khi dùng cách cấu hình này.
3. `WsConfigurer.addInterceptors` đăng ký validator vào endpoint interceptor chain.
4. `validateRequest=true` kiểm tra XML trước khi nghiệp vụ xử lý.
5. `validateResponse=true` kiểm tra XML tạo ra trước khi response được gửi.

Đây là cấu hình **dành cho một vùng endpoint mà mọi request/response được định nghĩa trong orders-v1.xsd**. Nếu cùng context còn chứa những dịch vụ khác không thuộc XSD orders, đăng ký global interceptor như trên có thể khiến các endpoint khác bị từ chối do không có global element tương ứng. Đây chính là lý do cần thiết kế **phạm vi áp dụng**, sẽ bàn kỹ ở phần sau.

### 7.1. Không tạo hai hạ tầng annotation endpoint vô tình

Nếu ứng dụng đã có `@EnableWs`/cấu hình XML annotation-driven hoặc Spring Boot auto-configuration liên quan, cần biết bean nào đang chịu trách nhiệm cho endpoint adapters, mappings và interceptors. Không copy thêm một bộ cấu hình chỉ vì muốn validation nếu nó dẫn đến duplicate registrations.

Cũng không nên tạo một `PayloadValidatingInterceptor` trong method rồi nghĩ rằng nó sẽ tự chạy mà không được gắn vào chain. Trong startup/integration test, xác nhận interceptor thật sự được đăng ký.

### 7.2. XSD bean không tự bật validation

Việc chỉ có bean `XsdSchema` hoặc `DefaultWsdl11Definition` phục vụ công bố WSDL/XSD **không làm Spring-WS tự kiểm tra request và response**. Hệ thống cần một interceptor hoặc validation pipeline tương đương đã kết nối vào endpoint.

Ngoài ra, chỉ vì WSDL được tải thành công không có nghĩa mọi import/include XSD đều được phân giải khi server validate. Cần kiểm tra cả đồ thị schema dependencies ở đúng môi trường.

## 8. Cấu hình XML cho hệ thống hiện hữu

Một ứng dụng Spring-WS WAR cũ có thể dùng `web.xml` và `spring-ws-servlet.xml`. Nếu endpoint infrastructure được bật bằng `<sws:annotation-driven/>`, interceptor có thể được đăng ký bằng XML namespace của Spring-WS.

Ví dụ:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans
    xmlns="http://www.springframework.org/schema/beans"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:context="http://www.springframework.org/schema/context"
    xmlns:sws="http://www.springframework.org/schema/web-services"
    xsi:schemaLocation="
        http://www.springframework.org/schema/beans
        https://www.springframework.org/schema/beans/spring-beans.xsd
        http://www.springframework.org/schema/context
        https://www.springframework.org/schema/context/spring-context.xsd
        http://www.springframework.org/schema/web-services
        https://www.springframework.org/schema/web-services/web-services.xsd">

    <context:component-scan
        base-package="com.example.orders.soap"/>

    <sws:annotation-driven/>

    <bean id="ordersSchema"
          class="org.springframework.xml.xsd.SimpleXsdSchema">
        <constructor-arg value="classpath:xsd/orders-v1.xsd"/>
    </bean>

    <sws:interceptors>
        <bean
            class="org.springframework.ws.soap.server.endpoint.interceptor.PayloadValidatingInterceptor">
            <property name="xsdSchema" ref="ordersSchema"/>
            <property name="validateRequest" value="true"/>
            <property name="validateResponse" value="true"/>
        </bean>
    </sws:interceptors>
</beans>
~~~

Các class FQCN, XSD namespace schema locations và cấu hình thực tế có thể cần điều chỉnh theo dòng Spring-WS đang dùng; đừng trộn package Jakarta/Javax hoặc schema config đời cũ một cách máy móc.

**Kiểm tra context:** Bean `ordersSchema`, validator và endpoint mapping phải nằm trong vùng application context mà SOAP servlet nhìn thấy. Với ứng dụng có root context và servlet child context, bean ở một context không nhất thiết tự hiển thị theo cả hai hướng.

## 9. Validation scope: một khái niệm, nhiều lựa chọn

“Phạm vi áp dụng” có ít nhất **bốn chiều** cần được quyết định:

1. **Chiều dữ liệu:** kiểm tra request, response hay cả hai?
2. **Phạm vi endpoint:** áp dụng cho một operation, một contract namespace, một nhóm endpoint hay tất cả SOAP endpoints?
3. **Phiên bản hợp đồng:** v1, v2 hoặc các schema khác nhau đang chạy song song?
4. **Môi trường và giai đoạn:** development/CI/staging/production, hoặc rollout từng bước.

Khi chọn scope, mục tiêu là **không bỏ sót thông điệp cần kiểm tra và không ép một schema sai lên thông điệp của dịch vụ khác**.

### 9.1. Ma trận chiến lược

| Tình huống | Request | Response | Scope gợi ý |
|---|---|---|---|
| SOAP service nhỏ chỉ có một XSD | Bật | Bật nếu khả thi | Toàn bộ endpoint group |
| API nhận dữ liệu từ nhiều đối tác | Bật | Tùy tải và chính sách | Theo namespace/contract |
| Service nhiều logic biến đổi response | Bật | Ưu tiên bật | Theo operation rủi ro |
| Đang migrate từ legacy XML | Bật sau khi kiểm chứng | Bật ở test/staging trước | Rollout từng nhóm endpoint |
| SOAP server có nhiều phiên bản contract | Bật theo phiên bản | Bật theo phiên bản | Tách v1/v2 rõ ràng |
| Service rất tải cao | Bật hoặc đánh giá risk policy | Cân nhắc cost, có CI contract tests | Đo đạc và chọn nhóm |
| Dịch vụ ký/encrypt SOAP | Bật theo pipeline an toàn | Bật theo vị trí phù hợp | Cân nhắc bảo mật và transport |
| Client SOAP của chính tổ chức | Validate outbound khi cần | Validate inbound khi cần | Ranh giới client/OXM |

Bảng là khung **để ra quyết định**, không phải quy tắc bắt buộc áp dụng một cặp cờ cho tất cả hệ thống. Nếu tắt runtime validation ở một nơi, cần có cơ chế kiểm soát rủi ro và regression tests bù đắp.

## 10. Không áp dụng nhầm schema cho mọi endpoint

Giả sử một ứng dụng có hai namespace:

~~~text
urn:example:orders:v1
urn:example:billing:v1
~~~

Endpoint thứ nhất xử lý `GetOrderRequest`; endpoint thứ hai xử lý `GetInvoiceRequest`. Nếu đăng ký một `PayloadValidatingInterceptor` với **chỉ orders-v1.xsd** cho toàn bộ endpoint chain, request billing hợp lệ theo schema của billing vẫn có thể bị báo invalid do schema orders không khai báo `GetInvoiceRequest`.

Đây là lỗi **phạm vi áp dụng**, không phải lỗi của request billing.

Cách tổ chức an toàn:

- **Tách SOAP servlet context/endpoint group** theo hợp đồng nếu kiến trúc cho phép. Mỗi nhóm có XSD và interceptor đúng.
- **Lọc interceptor theo endpoint/payload** bằng cơ chế interceptor có điều kiện của Spring-WS, ví dụ `SmartEndpointInterceptor` hoặc cấu hình endpoint mapping tương ứng, nếu framework version hỗ trợ.
- **Dùng tập schema phù hợp** nếu nhiều payload thực sự thuộc cùng một contract và cùng chính sách validation, nhưng phải kiểm tra version/namespace và tránh chồng lấn định nghĩa.
- **Đặt validation gần nơi boundary message được tiếp nhận**, không dựa vào việc tự chọn schema qua một field không đáng tin rồi vô tình bỏ qua schema thật của request.

Nếu dùng một interceptor “thông minh”, cần chắc chắn predicate chọn endpoint dựa trên **QName đã được phân giải từ XML** hoặc thông tin endpoint mapping đáng tin, thay vì chỉ nhìn tên prefix hay một header do client tự khai báo.

### 10.1. Một sơ đồ phân nhóm schema

~~~mermaid
flowchart TD
    A["SOAP inbound"] --> B["Endpoint mapping"]
    B --> C{"Contract nào?"}
    C -->|"orders:v1"| D["orders-v1.xsd validator"]
    C -->|"billing:v1"| E["billing-v1.xsd validator"]
    C -->|"không khớp"| F["Không có endpoint / xử lý lỗi"]
    D --> G["Order endpoint"]
    E --> H["Billing endpoint"]
~~~

Sơ đồ mô tả **chính sách mong muốn**. Cần xác minh thứ tự endpoint mapping và interceptor/filter cụ thể với Spring-WS phiên bản đang dùng.

### 10.2. Tại sao không chỉ gộp mọi XSD cho tiện?

Một tập nhiều XSD có thể hợp lệ nếu chúng thuộc cùng phạm vi, nhưng việc đưa mọi version hoặc mọi miền nghiệp vụ vào một validator global có các rủi ro:

1. Một root message v2 có thể được coi là hợp lệ dù endpoint đang phục vụ v1, nếu thiếu kiểm tra định tuyến/contract version phù hợp.
2. Hai schema cùng khai báo global QName nhưng khác cấu trúc có thể xung đột.
3. Một thay đổi của miền billing làm ảnh hưởng startup/validator của miền orders.
4. Log validation không chỉ rõ client đang cố gọi hợp đồng nào.
5. Mọi endpoint phải chịu chi phí/cấu hình không liên quan đến message của mình.

Hãy xem **phạm vi nghiệp vụ và vòng đời contract** trước khi chọn cách gom schema.

## 11. Lựa chọn scope theo phiên bản contract v1/v2

Giả sử v1 có namespace `urn:example:orders:v1` còn v2 dùng `urn:example:orders:v2`. Một kiến trúc cho phép hai phiên bản tồn tại song song có thể dùng:

~~~text
/orders/v1/ws       -> WSDL/XSD v1 -> @PayloadRoot(namespace=v1)
/orders/v2/ws       -> WSDL/XSD v2 -> @PayloadRoot(namespace=v2)
~~~

Đây là đường dẫn ví dụ; có thể có một SOAP endpoint URL chung với các QName khác nhau nếu kiến trúc hiện hữu thiết kế như vậy. Quan trọng là contract, XSD validator, QName mapping và WSDL metadata **nhất quán**.

Các tình huống cần thử:

- Client v1 gửi request v1 → được xử lý/validate theo v1.
- Client v2 gửi request v2 → được xử lý/validate theo v2.
- Client v2 gửi QName v2 vào service chỉ nhận v1 → không được định tuyến nhầm thành v1.
- Server v2 tạo response v2 → không gửi response mang QName v1 ngoài ý muốn.
- Các imports/includes của từng XSD version đều được giải đúng và không bị gộp sai.

Không đổi namespace chỉ vì URL triển khai thay đổi. Namespace URI là một phần giao diện XML, còn endpoint URL là vị trí vận hành. Việc đổi URI cần được quản lý như thay đổi hợp đồng, không phải cấu hình proxy đơn thuần.

## 12. Schema gồm nhiều XSD: kiểm tra đầy đủ dependency

Hợp đồng doanh nghiệp hiếm khi chỉ có một file đơn lẻ. Ví dụ:

~~~text
orders-v1.xsd
├── xs:include orders-model-v1.xsd
└── xs:import common-types-v1.xsd
~~~

Trong đó:

- `xs:include` dùng cho tài liệu cùng target namespace (hoặc trường hợp chameleon schema theo quy tắc XSD).
- `xs:import` dùng để tham chiếu một namespace khác.
- `schemaLocation` là gợi ý vị trí tài liệu; không thay thế việc so khớp `targetNamespace`.

Khi đăng ký validation, điều quan trọng là **bộ schema được biên dịch phải chứa những type/global elements mà request và response thực sự sử dụng**.

### 12.1. Dùng schema root khi dependencies giải được

Nếu `orders-v1.xsd` include/import các schema có `schemaLocation` tương đối và resolver của Spring/XML provider giải được từ classpath resources, một schema root có thể đủ.

Tuy nhiên, không được suy ra rằng URL metadata công khai `/ws/orders-v1.xsd` hoạt động thì validator nội bộ đã giải được mọi schema. Hai đường phân giải khác nhau có thể dùng những root URI/resource resolver khác nhau.

### 12.2. Dùng nhiều schema resources khi cần

Một số version API của `PayloadValidatingInterceptor` và các lớp cơ sở hỗ trợ khai báo tập schema resources để biên dịch các tài liệu liên quan. Cấu hình kiểu:

~~~java
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.ws.soap.server.endpoint.interceptor.PayloadValidatingInterceptor;

PayloadValidatingInterceptor validator =
    new PayloadValidatingInterceptor();

validator.setSchemas(new Resource[] {
    new ClassPathResource("xsd/orders-v1.xsd"),
    new ClassPathResource("xsd/common-types-v1.xsd")
});

validator.setValidateRequest(true);
validator.setValidateResponse(true);
~~~

Đây là **minh họa một phương án cấu hình nếu phiên bản Spring-WS đang dùng có `setSchemas(Resource[])`**. Không liệt kê tùy tiện cả schema root và mọi file đã được include nếu việc đó khiến bộ compiler báo khai báo trùng hoặc resolver phân giải hai lần một thành phần không tương thích. Phải thử compile XSD cụ thể của dự án.

Khi hệ thống dùng `CommonsXsdSchemaCollection` để sinh WSDL, đừng mặc định có thể đưa cùng bean collection trực tiếp cho mọi validation interceptor. WSDL generation và schema validation có thể có API cấu hình khác nhau. Luôn kiểm tra **validator thật sự nhận được bộ XSD nào**.

### 12.3. Kiểm tra lỗi import/include từ sớm

Các lỗi thường gặp:

| Triệu chứng | Khả năng |
|---|---|
| Server fail khi khởi tạo schema | XSD sai, import/include không giải được, định nghĩa trùng |
| Server khởi động nhưng request bị từ chối | Validator không thấy global element/type |
| Client tải WSDL được nhưng sinh mã thất bại | URL XSD được tham chiếu không truy cập được |
| Payload dùng kiểu common nhưng báo không thấy type | `xs:import` sai namespace hoặc location |
| Test pass trên IDE nhưng fail sau deploy | Tài nguyên XML Schema không nằm đúng trong JAR/WAR hoặc resolver dùng đường dẫn máy phát triển |

Với ứng dụng production, nên kiểm tra schema compilation ở startup hoặc CI để tránh chỉ phát hiện hợp đồng lỗi sau khi nhận request đầu tiên. Không phụ thuộc vào các XSD URL bên ngoài không đáng tin nếu có thể đóng gói schema và resolver cục bộ.

## 13. Phân biệt payload validation và toàn bộ SOAP message

`PayloadValidatingInterceptor` tập trung vào **payload** của SOAP Body. Nó không xác nhận:

- SOAP Header đã được xử lý theo `mustUnderstand`, actor/role và relay.
- WS-Security Timestamp nằm trong giới hạn thời gian, token hợp lệ hay chữ ký đúng.
- Client sử dụng đúng certificate/trust anchor.
- HTTP path, phương thức, SOAPAction/action và Content-Type tuân thủ binding.
- SOAP Envelope là phiên bản 1.1 hay 1.2 mà server chấp nhận, nếu lỗi xảy ra ở message factory trước interceptor.
- Các giá trị nghiệp vụ trong payload đúng với database và quyền truy cập.

Ví dụ, một request có `orderId=ORD-2048` hợp XSD vẫn phải được từ chối nếu người gọi không có quyền xem đơn hàng. Ngược lại, một SOAP Header có chữ ký hợp lệ không biến payload thiếu `orderId` thành hợp lệ theo XSD.

Với SOAP 1.1, Envelope namespace:

~~~text
http://schemas.xmlsoap.org/soap/envelope/
~~~

Với SOAP 1.2:

~~~text
http://www.w3.org/2003/05/soap-envelope
~~~

Nếu factory chỉ hỗ trợ SOAP 1.1 mà nhận Envelope 1.2, request có thể thất bại **trước khi đạt tới bước XSD payload validation**. Vì vậy test lỗi version/media type phải được phân loại riêng với test request sai schema.

## 14. JAXB/OXM và validation: không dùng phép round-trip làm bằng chứng đủ

Spring-WS có thể dùng JAXB sinh từ XSD để nhận/trả payload. Ví dụ một endpoint:

~~~java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

@Endpoint
public class GetOrderEndpoint {

    private static final String NS = "urn:example:orders:v1";

    private final OrderApplicationService service;

    public GetOrderEndpoint(OrderApplicationService service) {
        this.service = service;
    }

    @PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
    @ResponsePayload
    public GetOrderResponse handle(
            @RequestPayload GetOrderRequest request) {

        String status =
            service.statusOf(request.getOrderId());

        GetOrderResponse response = new GetOrderResponse();
        response.setOrderId(request.getOrderId());
        response.setStatus(status);

        return response;
    }
}
~~~

Ví dụ giả định XJC sinh `GetOrderRequest`/`GetOrderResponse` với `@XmlRootElement` phù hợp từ anonymous complex types trong XSD ở phần 3 và Spring-WS đã đăng ký JAXB argument/return value processors. Với schema dùng named complex types, XJC có thể yêu cầu `ObjectFactory` và `JAXBElement<T>`; phải điều chỉnh chữ ký theo binding thực tế.

Nếu `service.statusOf(...)` trả `DELIVERED` trong khi XSD chỉ có PENDING/PAID/CANCELLED, code Java hoàn toàn có thể chạy đến cuối method. **Response validation mới phát hiện dữ liệu trả về không thuộc enum của hợp đồng**, trừ khi ứng dụng đã có kiểm tra tương đương.

### 14.1. Jaxb2Marshaller#setSchema ở tầng OXM

Nếu ứng dụng dùng `Jaxb2Marshaller` để marshal/unmarshal trực tiếp, có thể gắn XSD ở tầng OXM:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;

@Configuration
public class OrdersOxMConfiguration {

    @Bean
    public Jaxb2Marshaller ordersMarshaller() {
        Jaxb2Marshaller marshaller =
            new Jaxb2Marshaller();

        marshaller.setContextPath(
            "com.example.orders.contract.v1"
        );

        marshaller.setSchema(
            new ClassPathResource("xsd/orders-v1.xsd")
        );

        return marshaller;
    }
}
~~~

Cấu hình này kiểm tra XML ở **đường đi đi qua marshaller đó**. Không tự bảo đảm mọi Spring-WS endpoint sẽ dùng đúng bean `ordersMarshaller` nếu argument/return value processors được cấu hình khác.

Phân biệt:

| Cơ chế | Vị trí |
|---|---|
| `PayloadValidatingInterceptor` | SOAP endpoint interceptor chain |
| `Jaxb2Marshaller#setSchema` | Những lời gọi marshal/unmarshal đi qua marshaller đó |
| `SchemaFactory`/`Validator` | Kiểm tra XML độc lập bằng JAXP |
| Domain Bean Validation/logic nghiệp vụ | Kiểm tra quy tắc của application, không thay XSD |

Cùng một request có thể được kiểm tra ở nhiều tầng, nhưng không nên bật lặp lại vô thức gây tốn CPU mà không thêm giá trị. Lựa chọn phụ thuộc ranh giới tin cậy, khả năng tái sử dụng marshaller và tiêu chí an toàn.

### 14.2. JAXB unmarshalling thành công chưa chắc XML hợp XSD

Một số JAXB runtimes có thể gán giá trị field nhưng không tự thực thi mọi `xs:pattern`, `xs:enumeration`, cardinality hoặc thứ tự element nếu schema validation chưa được bật. Một đối tượng Java được sinh từ XSD không đủ để chứng minh XML đầu vào đúng contract.

Tương tự, `marshaller.marshal(value, target)` không ném exception chưa chắc XML đầu ra đúng XSD, đặc biệt khi Java có nullable fields, list rỗng và custom adapters.

## 15. SOAP Fault cho lỗi request và lỗi response

Validation có thể thất bại ở hai điểm rất khác nhau:

- **Request invalid**: client gửi XML không hợp contract.
- **Response invalid**: server tạo XML không hợp contract hoặc mapper/server code đã hỏng.

Hai tình huống không nên bị gộp vào cùng một thông điệp lỗi mơ hồ.

### 15.1. Request invalid: lỗi phía gửi

Một SOAP 1.1 Fault có thể trông như:

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
    <soap:Body>
        <soap:Fault>
            <faultcode>soap:Client</faultcode>
            <faultstring>Request payload không đúng hợp đồng</faultstring>
        </soap:Fault>
    </soap:Body>
</soap:Envelope>
~~~

SOAP 1.2 có `Code`/`Reason` và mã nhóm `Sender` thay cho `Client`. Đây là **mẫu minh họa về hướng phân loại lỗi**, không phải cam kết output mặc định chính xác của mọi phiên bản Spring-WS. Cần kiểm tra Fault thực tế do interceptor/resolver tạo và HTTP binding tương ứng.

### 15.2. Response invalid: lỗi phía server

Nếu server tạo response sai, không được âm thầm gửi một SOAP success payload vi phạm XSD rồi bắt client tự xử lý. Tùy chính sách và khả năng xử lý của pipeline, có thể tạo SOAP Fault phía server/receiver, ghi metric và cảnh báo. Cần tránh response validation gây ra một Fault mới không thể xử lý do response đã commit hoặc do các interceptor khác đã thay message.

Trong kiểm thử, cần xác minh **hành vi thực tế** thay vì giả định response validation luôn tự tạo đúng một kiểu Fault. Đặc biệt, SOAP Fault được sinh bởi exception resolver thường **không phải global success response element** trong XSD nghiệp vụ; không nên cấu hình validator buộc Fault body phải khớp `GetOrderResponse`.

### 15.3. Thiết kế Fault không lộ thông tin nội bộ

Một Fault có thể chứa thông tin tối thiểu:

- Loại lỗi hợp đồng hay lỗi hệ thống.
- Mã lỗi ổn định theo chính sách.
- Correlation ID nếu được tạo/kiểm soát an toàn.
- Message có thể sử dụng bởi client và không để lộ dữ liệu nhạy cảm.

Tránh đưa vào Fault chi tiết:

- SQL query, stack trace, đường dẫn hệ thống.
- Access token, mật khẩu, certificate private data.
- Nguyên văn SOAP payload chứa dữ liệu khách hàng.
- Thông tin nội bộ về schema resolver hoặc file location nếu có rủi ro bảo mật.

Với dịch vụ có WSDL fault messages được thiết kế riêng, cần kiểm tra SOAP Fault detail và QName/namespace của fault theo contract; validation của success payload không tự bao phủ điều này.

## 16. Request validation không thay thế domain validation

XSD minh họa cho phép `ORD-[0-9]+`. Nhưng nghiệp vụ có thể thêm quy tắc:

- `ORD-2048` phải tồn tại.
- Người dùng phải thuộc tenant được phép xem đơn.
- Order bị khóa không được sửa.
- Một số trạng thái không được chuyển sang trạng thái khác.
- Số tiền phải được phép theo chính sách thanh toán.
- Idempotency/correlation ID phải được xử lý chống lặp.

Những quy tắc đó không thể kiểm tra chỉ bằng `xs:pattern` hoặc `xs:enumeration`.

Một phân chia trách nhiệm tốt:

~~~mermaid
flowchart LR
    A["SOAP XML"] --> B["XSD validation"]
    B --> C["Mapping XML -> domain command"]
    C --> D["Authentication / authorization"]
    D --> E["Domain invariants"]
    E --> F["Business operation"]
~~~

Vị trí authentication/authorization cụ thể có thể trước mapping hoặc trước một số phần khác tùy chính sách WS-Security và interceptor. Sơ đồ nhằm nêu rõ rằng **tất cả lớp trách nhiệm đều phải được giải quyết**, không ngụ ý một thứ tự security cứng nhắc.

### 16.1. Một trường rỗng có thể hợp XSD nhưng không hợp nghiệp vụ

Nếu XSD dùng `xs:string` mà không có `minLength`, chuỗi rỗng có thể hợp lệ về XSD. Domain có thể yêu cầu mã không rỗng.

Do đó, test phải biết đang kiểm tra **ràng buộc nào ở lớp nào**. Không thay đổi kỳ vọng XSD vì business code từ chối một giá trị chưa bị XSD cấm.

### 16.2. Optional, empty và xsi:nil

Với:

~~~xml
<xs:element name="note"
            type="xs:string"
            minOccurs="0"
            nillable="true"/>
~~~

ba trạng thái:

~~~xml
<!-- Không gửi note -->
~~~

~~~xml
<ord:note xmlns:ord="urn:example:orders:v1"/>
~~~

~~~xml
<ord:note
    xmlns:ord="urn:example:orders:v1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:nil="true"/>
~~~

có thể đều hợp XSD, nhưng nghiệp vụ cập nhật có thể quy định absent = giữ nguyên, nil = xóa, empty = chuỗi rỗng. Để giữ phân biệt, cần thiết kế JAXB binding/`JAXBElement` hoặc parser/mapper phù hợp.

`PayloadValidatingInterceptor` bảo đảm những trạng thái này hợp **cấu trúc schema**, không tự quyết định nghĩa “xóa” hay “giữ nguyên”.

## 17. Thiết kế bộ test request và response tách biệt

Đừng chỉ tạo một test “gọi SOAP thành công” rồi coi như đã kiểm chứng validation. Bảng test nên có ca biên và ca negative cho **cả hai hướng**.

### 17.1. Ma trận request

| Test | XML client gửi | Kỳ vọng |
|---|---|---|
| R1 | `orderId=ORD-2048` | Hợp XSD; endpoint được phép xử lý |
| R2 | Không có `orderId` | Từ chối trước nghiệp vụ |
| R3 | `orderId=ABC` | Từ chối do pattern |
| R4 | `orderId` rỗng | Từ chối |
| R5 | `includeHistory=1` | Hợp lệ theo `xs:boolean` |
| R6 | `includeHistory=maybe` | Từ chối |
| R7 | Đảo thứ tự `includeHistory` và `orderId` | Từ chối theo sequence |
| R8 | Dùng prefix khác, URI v1 giữ nguyên | Hợp lệ |
| R9 | Dùng default namespace v1 | Hợp lệ |
| R10 | Dùng namespace v2 | Không dispatch như v1 |
| R11 | XML không well-formed | Lỗi parser/SOAP processing, không xử lý nghiệp vụ |
| R12 | SOAP Envelope 1.2 trong factory chỉ hỗ trợ SOAP 1.1 | Lỗi version/transport, không được nhầm với XSD violation |

### 17.2. Ma trận response

| Test | Response server tạo | Kỳ vọng |
|---|---|---|
| S1 | `status=PAID` và đủ field | Hợp lệ |
| S2 | `status=DELIVERED` | Từ chối/báo lỗi do enum |
| S3 | Thiếu `status` | Từ chối/báo lỗi |
| S4 | `status` trước `orderId` | Từ chối/báo lỗi |
| S5 | Child `status` không namespace | Từ chối/báo lỗi |
| S6 | `note` vắng mặt | Hợp lệ |
| S7 | `note xsi:nil="true"` | Hợp lệ nếu đúng nillable semantics |
| S8 | Thêm `debugInfo` ngoài schema | Từ chối/báo lỗi |
| S9 | Response dùng default namespace thay prefix `ord` | Hợp lệ |
| S10 | SOAP Fault phát sinh từ lỗi nghiệp vụ | Kiểm tra theo Fault contract, không buộc khớp success response XSD |

**Kiểm thử response quan trọng cho cả các đường lỗi và nhánh ít chạy**, bởi nhiều regression chỉ xuất hiện ở những nhánh response đặc biệt.

### 17.3. Mỗi ca negative nên chỉ sai một điều

Khi tạo XML nhằm kiểm tra pattern, giữ các field còn lại hợp lệ. Nếu đồng thời thiếu root element và sai namespace, test có thể thất bại vì nguyên nhân khác với chủ đích. Điều này làm người học khó biết validator đang thực thi constraint nào.

Trong test tích hợp tổng hợp, có thể cố tình đưa nhiều lỗi để xem server từ chối an toàn; nhưng với test từng ràng buộc cần mô tả rõ kỳ vọng.

## 18. Kiểm tra XML trực tiếp với SchemaFactory trước khi gửi SOAP

Có thể tách kiểm thử XML Schema khỏi Spring-WS để xác nhận một fixture hợp hay không hợp contract. Dùng JAXP `SchemaFactory`, `Schema` và `Validator`:

~~~java
import java.io.StringReader;

import javax.xml.XMLConstants;
import javax.xml.transform.stream.StreamSource;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;
import javax.xml.validation.Validator;

import org.springframework.core.io.ClassPathResource;

SchemaFactory factory = SchemaFactory.newInstance(
    XMLConstants.W3C_XML_SCHEMA_NS_URI
);

factory.setFeature(
    XMLConstants.FEATURE_SECURE_PROCESSING,
    true
);

factory.setProperty(
    XMLConstants.ACCESS_EXTERNAL_DTD,
    ""
);

factory.setProperty(
    XMLConstants.ACCESS_EXTERNAL_SCHEMA,
    ""
);

ClassPathResource xsd =
    new ClassPathResource("xsd/orders-v1.xsd");

Schema schema = factory.newSchema(xsd.getURL());
Validator validator = schema.newValidator();

String xml = """
    <ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
        <ord:orderId>ORD-2048</ord:orderId>
    </ord:GetOrderRequest>
    """;

validator.validate(
    new StreamSource(new StringReader(xml))
);
~~~

Đoạn code minh họa cách dùng JAXP trong test. Với XSD import/include nhiều tài liệu, cần giải quyết qua resolver cục bộ tin cậy, tránh phụ thuộc vào mạng không kiểm soát. Với input không tin cậy, ngoài property trên cần bảo đảm XML parser và validator đang dùng bị hạn chế DTD/external access theo chính sách. Cũng cần giới hạn kích thước và độ phức tạp của XML.

`Schema` thường có thể tái sử dụng, còn `Validator` là object mutable và **không nên chia sẻ giữa nhiều thread cùng lúc** nếu không có bảo đảm thread-safety từ implementation.

### 18.1. XML well-formed không đồng nghĩa schema-valid

Document có tag đóng đúng và namespace declaration hợp cú pháp có thể vẫn sai:

~~~xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
    <ord:orderId>INVALID</ord:orderId>
</ord:GetOrderRequest>
~~~

Parser XML có thể đọc được; XSD validator phải từ chối vì `pattern`. Đó là lý do cần test cả parser và schema validation, không gộp chúng vào một khẳng định “XML đọc được”.

## 19. Kiểm thử endpoint với MockWebServiceClient

Spring-WS cung cấp `MockWebServiceClient` trong thư viện `spring-ws-test` để gửi payload qua endpoint infrastructure mà không cần HTTP server thật.

Ví dụ một kiểm thử happy path:

~~~java
import static org.springframework.ws.test.server.RequestCreators.withPayload;
import static org.springframework.ws.test.server.ResponseMatchers.payload;

import org.junit.jupiter.api.Test;
import org.springframework.context.ApplicationContext;
import org.springframework.ws.test.server.MockWebServiceClient;
import org.springframework.xml.transform.StringSource;

class OrderValidationEndpointTest {

    private final MockWebServiceClient client;

    OrderValidationEndpointTest(ApplicationContext context) {
        client = MockWebServiceClient.createClient(context);
    }

    @Test
    void acceptsValidRequestAndReturnsValidResponse() {
        String request = """
            <ord:GetOrderRequest
                xmlns:ord="urn:example:orders:v1">
                <ord:orderId>ORD-2048</ord:orderId>
            </ord:GetOrderRequest>
            """;

        String expected = """
            <ord:GetOrderResponse
                xmlns:ord="urn:example:orders:v1">
                <ord:orderId>ORD-2048</ord:orderId>
                <ord:status>PAID</ord:status>
            </ord:GetOrderResponse>
            """;

        client.sendRequest(
                withPayload(new StringSource(request))
            )
            .andExpect(
                payload(new StringSource(expected))
            );
    }
}
~~~

Đây là **skeleton minh họa**: để chạy cần Spring test extension và ApplicationContext cấu hình endpoint/validation phù hợp, cùng một `OrderApplicationService` test trả `PAID`. Trong dự án thật, người học cần cài dependency và tạo fixture/stub nghiệp vụ, không coi snippet là lớp JUnit chạy độc lập nguyên xi.

### 19.1. Test request sai và không gọi nghiệp vụ

Một test request invalid nên:

1. Gửi payload thiếu `orderId`.
2. Kiểm tra SOAP Fault theo đúng cấu hình (ví dụ có thể dùng matcher `clientOrSenderFault()` của `ResponseMatchers` khi phù hợp).
3. Verify mock domain service không được gọi.
4. Kiểm tra không có side effect.

Skeleton ý tưởng:

~~~java
String invalid = """
    <ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
        <ord:includeHistory>true</ord:includeHistory>
    </ord:GetOrderRequest>
    """;

// Với cấu hình interceptor mặc định tương thích và SOAP Fault
// policy của ứng dụng, ví dụ:
client.sendRequest(withPayload(new StringSource(invalid)))
      .andExpect(
          org.springframework.ws.test.server.ResponseMatchers
              .clientOrSenderFault()
      );

// Với mock dịch vụ nghiệp vụ, bổ sung verifyNoInteractions(...)
// hoặc verify(mock, never()) cho operation tương ứng.
~~~

Vì hành vi Fault có thể được customize, test thật nên kiểm tra loại fault, detail và các điều kiện nghiệp vụ theo policy của chính dịch vụ. Không nên để một test chỉ assert “có lỗi bất kỳ” mà không bảo vệ ý nghĩa của lỗi.

### 19.2. Test response sai

Để kiểm tra response validation, cấu hình test `OrderApplicationService` hoặc endpoint mapper cố tình tạo `status=DELIVERED`, sau đó:

1. Gửi request hợp lệ.
2. Xác nhận response validator phát hiện violation.
3. Xác nhận server **không phát một success response XML sai** theo chính sách.
4. Kiểm tra SOAP Fault/error/result callback thực tế của framework.
5. Kiểm tra metric/log nhưng không lộ dữ liệu nhạy cảm.

Không giả định response invalid luôn được chuyển thành một `serverOrReceiverFault()` với detail cố định; cần kiểm tra cấu hình Spring-WS và cách lỗi được xử lý khi response đang hình thành.

### 19.3. Cần kiểm tra qua HTTP SOAP thật

`MockWebServiceClient` không thể thay thế hết:

- Servlet URL mapping và context path.
- SOAP 1.1/1.2 Content-Type, SOAPAction/action.
- Reverse proxy, TLS, timeout và HTTP status.
- WSDL/XSD public URLs và những import/include.
- WS-Security transport/message integration.
- Client sinh từ WSDL của Java/.NET/ESB độc lập.

Một số smoke tests qua HTTP thực là cần thiết để chứng minh request/response validation hoạt động đúng trong cấu hình triển khai.

## 20. Đo hiệu năng trước khi bật trên lưu lượng lớn

XSD validation cần đọc và kiểm tra cây/sự kiện XML. Chi phí phụ thuộc:

- Kích thước payload.
- Số lượng element và các cấu trúc phức tạp (`xs:choice`, pattern, lists...).
- Việc schema đã được compile/reuse hay bị compile mỗi request.
- SOAP message factory, DOM/SAX/StAX/JAXB pipeline.
- Số tầng validation trùng lặp.
- Số lượng request đồng thời và giới hạn bộ nhớ.

Một kế hoạch đo có ý nghĩa:

| Chỉ số | Quan sát |
|---|---|
| Latency p50, p95, p99 | So sánh trước/sau bật validation |
| CPU / GC | Phát hiện cost của XML parsing và validation |
| Throughput | Đo request/second bền vững |
| Lỗi schema theo QName/operation | Theo dõi client nào sai hợp đồng |
| Response invalid events | Cảnh báo regression phía server |
| Memory và payload size | Giới hạn rủi ro với XML lớn |
| Fault rate theo client | Phát hiện vấn đề khi rollout |

Không chọn scope chỉ bằng cảm giác “validation chậm”; hãy benchmark trên fixture và traffic đại diện.

### 20.1. Không compile XSD mỗi request

Schema compilation có chi phí đáng kể. Nên cấu hình `XsdSchema`/interceptor/validator ở mức component được quản lý và tái sử dụng những đối tượng an toàn theo lifecycle thay vì tạo `SchemaFactory.newSchema(...)` cho mỗi SOAP request.

Vẫn cần kiểm tra thread-safety của các đối tượng runtime: `Validator` riêng lẻ thường không được chia sẻ giữa threads, trong khi framework-managed interceptor thường quản lý việc xử lý thích hợp. Không tự cache mọi loại parser/validator mà không hiểu thread-safety.

### 20.2. Response validation trong production cần chính sách lỗi

Một service đang chạy lâu năm có thể trước đây trả XML sai XSD mà một số client vẫn chấp nhận. Khi bật strict response validation, những đường response đó có thể bắt đầu phát lỗi. Đây không phải lý do để bỏ validation vĩnh viễn; nó là tín hiệu cần phân loại và xử lý **tương thích thực tế** trước rollout.

Nên chốt acceptance criteria, kiểm thử staging và rollback, đo tác động trước khi mở trên tất cả operation production.

## 21. Một lộ trình rollout hợp lý

Giả sử hệ thống có 30 SOAP operations và nhiều đối tác đang tích hợp. Tránh bật validation global mà không biết operation nào thuộc schema nào.

Quy trình có kiểm soát:

1. **Lập bản đồ contract:** WSDL, XSD, namespace, versions, endpoint mappings và schema dependency.
2. **Tạo ma trận scope:** operation nào validate request, operation nào validate response, môi trường nào bật.
3. **Chốt XML fixtures:** request/response hợp lệ và negative cases theo từng global element QName.
4. **Kiểm tra CI:** compile XSD, run unit round-trip, schema validation và SOAP endpoint tests.
5. **Bật ở staging:** chạy với traffic mô phỏng, SOAP client độc lập và cases của đối tác.
6. **Đo performance:** latency, CPU, memory, throughput và error/Fault rate.
7. **Rollout production theo nhóm:** ưu tiên request validation ở ranh giới vào; response validation theo rủi ro và kết quả kiểm thử.
8. **Theo dõi vi phạm có phân loại:** contract version, QName, client/operation; không log raw sensitive XML.
9. **Có phương án rollback:** nếu validator mới làm gián đoạn clients hợp lệ do schema/config lỗi.
10. **Chuẩn hóa lâu dài:** mọi thay đổi XSD/JAXB/endpoint đều chạy contract regression trước phát hành.

Không chuyển nghĩa của một trường XSD cho tiện xử lý dữ liệu thực tế mà chưa đánh giá ảnh hưởng đối tác. Nếu contract cần thay đổi phá vỡ, quản lý bằng version v2 và giai đoạn hỗ trợ song song thay vì tắt validator để client không gặp lỗi.

## 22. Security: bảo vệ XML trước khi validate và khi báo lỗi

XSD validation là một lớp phòng vệ cấu trúc; nó cũng cần được vận hành an toàn.

### 22.1. XXE và external schema resolution

XML parsing và schema compilation có thể liên quan DTD, external entities, `xs:import`/`xs:include`. Khi dữ liệu hoặc đường dẫn có nguồn không tin cậy, cần cấu hình:

- Chặn DTD/external entities không cần thiết.
- Giới hạn `ACCESS_EXTERNAL_DTD` và `ACCESS_EXTERNAL_SCHEMA`.
- Dùng tài nguyên schema đã đóng gói, resolver được tin cậy.
- Giới hạn độ sâu/kích thước XML và số lần xuất hiện.
- Tránh URL schema động đến nguồn client tự chọn nếu không có whitelist và kiểm soát phù hợp.

Không cho parser bỏ qua các lỗi không hỗ trợ secure-processing rồi dùng default không an toàn. Cần kiểm thử security trên đúng XML parser/SOAP factory ở runtime.

### 22.2. WS-Security là lớp khác

SOAP message có chữ ký hoặc mã hóa có thể yêu cầu:

- Xác minh signature và chứng chỉ.
- Kiểm tra token, timestamp, replay protection.
- Xác thực người gọi và phân quyền.
- Quản lý thứ tự các bước bảo mật, decrypt và validation theo architecture.

Đừng coi message hợp XSD là message đáng tin. Cũng đừng thay đổi XML được ký sau bước xác minh mà không hiểu tác động lên chữ ký và audit.

### 22.3. Logging validation failures có thể lộ dữ liệu

Một lỗi schema có thể chỉ ra vị trí element/attribute, đôi khi kèm value. Trong log hoặc SOAP Fault, tránh ghi toàn bộ thông điệp chứa dữ liệu cá nhân, token, account numbers và internal stack traces.

Nên có correlation ID an toàn, mã lỗi phân loại và metric theo QName, còn chi tiết nhạy cảm chỉ lưu theo chính sách xử lý sự cố có giới hạn quyền truy cập.

## 23. Bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra ưu tiên |
|---|---|---|
| Request sai XSD vẫn tới nghiệp vụ | Interceptor chưa đăng ký hoặc request validation tắt | `WsConfigurer`, chain, `validateRequest` |
| Request hợp lệ bị từ chối khi gọi service khác | Validator global dùng schema của service không liên quan | Scope theo endpoint/namespace |
| Response thiếu field vẫn trả thành công | Response validation chưa bật/không chạy | `validateResponse`, endpoint adapter, schema |
| Validator báo type không tồn tại | XSD import/include không resolve | Namespace, schemaLocation, resources |
| WSDL tải được nhưng client thiếu XSD | Public XSD location sai | GET toàn bộ schema từ ngoài |
| SOAP request lỗi trước validator | Sai Content-Type/Envelope version | SOAP message factory và binding |
| JAXB parse được request sai | Không bật XSD validation hoặc binding không ép facet | XSD validator/OXM/interceptor |
| Response fail chỉ ở một nhánh code | Mapper/enum/DOM tạo sai XML | Test response branch, QName, sequence |
| Fault không như mong đợi | Exception resolver/interceptor policy khác | SOAP 1.1/1.2 Fault runtime |
| Triển khai mới chậm | Validation lặp lại hoặc schema bị compile quá thường | Performance metrics, lifecycle |
| Client v2 bị v1 validator báo lỗi | Chọn sai scope/version | Namespace/version, endpoint mapping |
| Dữ liệu đúng XSD nhưng sai quyền | XSD không kiểm tra authorization | WS-Security/identity/domain validation |

### 23.1. Checklist điều tra khi request bị từ chối

Nếu nhận SOAP Fault báo schema invalid:

1. Xác định request thực tế và SOAP version (đã che dữ liệu nhạy cảm).
2. Đọc QName root payload; so với `@PayloadRoot`.
3. Đọc XSD version mà validator đang sử dụng.
4. Kiểm tra `xs:include`/`xs:import` và nguồn schema.
5. Xem đúng interceptor đã được chọn cho endpoint hay chưa.
6. Kiểm tra constraint được báo: missing element, type, namespace, sequence, facet...
7. Chạy XML fixture đó qua JAXP validator độc lập.
8. Kiểm tra client có dùng WSDL/XSD đúng phiên bản hay chưa.
9. Đánh giá lỗi do client sai contract, server cấu hình scope sai hay contract mới phá vỡ tương thích.

Không “chữa” bằng cách đổi namespace hoặc tắt tất cả validation nếu chưa xác định nguyên nhân.

## 24. Bài thực hành tự làm

Một hệ thống SOAP có:

~~~text
orders:v1:
  GetOrderRequest -> GetOrderResponse
  UpdateOrderRequest -> UpdateOrderResponse

billing:v1:
  GetInvoiceRequest -> GetInvoiceResponse
~~~

Yêu cầu:

- Request từ đối tác phải hợp XSD.
- Response từ `UpdateOrder` phải được kiểm tra nghiêm ngặt vì dữ liệu ghi quan trọng.
- Response từ `GetOrder` cũng được kiểm tra trong CI/staging, production theo kết quả đo.
- Không dùng schema orders để validate billing.
- SOAP v1/v2 cần phân biệt rõ contract.
- Những lỗi validation không được đưa stack trace hoặc dữ liệu nhạy cảm đến đối tác.

Hãy thực hiện:

1. Vẽ sơ đồ servlet/endpoint mappings và các `XsdSchema` tương ứng.
2. Lập bảng scope cho từng request/response operation.
3. Viết XSD cho ít nhất `GetOrderRequest`/`GetOrderResponse`, có pattern và enum.
4. Đăng ký `PayloadValidatingInterceptor` với hai cờ tường minh ở group orders.
5. Thiết kế cách lọc scope cho group billing (theo endpoint mapping/filter hay servlet context riêng).
6. Viết fixture request hợp lệ, thiếu required field, sai namespace, sai `xs:sequence`.
7. Cố tình tạo response có enum sai, xác nhận response validation phát hiện lỗi.
8. Kiểm tra SOAP Fault request-side và server-side theo chính sách.
9. Chạy SOAP integration test và generated client độc lập.
10. Đo latency/CPU trước và sau khi bật validation ở production-like staging.
11. Mô tả cách rollback nếu bật response validation làm phát hiện một nhánh XML legacy đang sai.
12. Đề xuất cách version contract v2 mà client v1 không bị ảnh hưởng.

**Tiêu chí đạt:** Hợp đồng được kiểm tra ở đúng chiều và đúng endpoint; request sai không gây side effect; response sai không bị coi là thành công; Fault, performance và versioning được kiểm soát.

## 25. Checklist trước khi phát hành

- [ ] Đã xác định rõ contract XSD/WSDL và namespace cho từng endpoint.
- [ ] `PayloadValidatingInterceptor` được đăng ký trong đúng Spring-WS interceptor chain.
- [ ] `validateRequest`/`validateResponse` được đặt tường minh theo chính sách.
- [ ] Schema XSD bao gồm cả request và response cần kiểm tra.
- [ ] `xs:include`/`xs:import` được phân giải và kiểm chứng.
- [ ] Không áp dụng schema của service khác cho một endpoint không liên quan.
- [ ] Contract version v1/v2 được tách đúng theo QName và đường vận hành.
- [ ] Có positive/negative tests cho request và response.
- [ ] Request invalid không chạy nghiệp vụ hoặc gây side effect.
- [ ] Response invalid được phát hiện và xử lý theo policy, không âm thầm trả success XML sai.
- [ ] SOAP Fault không tiết lộ stack trace, token hoặc dữ liệu nhạy cảm.
- [ ] WS-Security, authorization và XML parser security được kiểm tra tách biệt.
- [ ] Đã đo hiệu năng khi bật validation trên traffic đại diện.
- [ ] Đã kiểm thử SOAP 1.1/1.2, WSDL/XSD public URL và client độc lập.
- [ ] Có regression fixtures và rollback plan cho migration/rollout.

## 26. Ghi nhớ

- **Request validation bảo vệ dữ liệu đi vào; response validation bảo vệ hợp đồng server công bố cho client.**
- **`PayloadValidatingInterceptor` kiểm tra payload XML theo XSD**, không kiểm tra toàn bộ SOAP Header, WS-Security hoặc nghiệp vụ.
- **Phạm vi áp dụng** cần xét đồng thời chiều request/response, nhóm endpoint, namespace/version và môi trường.
- **Một validator global không phù hợp cho mọi contract khác nhau** nếu schema không bao phủ đúng message của từng endpoint.
- **JAXB parse/marshal thành công chưa đủ chứng minh XML đúng schema**; cần validation và negative tests độc lập.
- **SOAP Fault phải phân loại lỗi và bảo vệ thông tin nhạy cảm**; lỗi request và response có trách nhiệm khác nhau.
- **Contract-first gắn với kiểm thử tương thích:** kiểm tra cả XSD, WSDL, SOAP runtime và generated client sau mỗi thay đổi.

**Câu hỏi tự kiểm tra:** Một ứng dụng Spring-WS có hai namespace `urn:example:orders:v1` và `urn:example:billing:v1`. Bạn đăng ký một `PayloadValidatingInterceptor` global với `orders-v1.xsd`, bật cả request/response validation. Client billing gửi XML hoàn toàn hợp `billing-v1.xsd` nhưng nhận SOAP Fault. Vì sao đây có thể là lỗi **phạm vi áp dụng** thay vì lỗi payload của client? Hãy đề xuất hai cách cấu hình để mỗi endpoint dùng đúng schema, cùng một bộ test chứng minh request sai bị từ chối nhưng request hợp lệ của cả hai miền vẫn được xử lý.


