# @XPathParam và khai báo namespace cho biểu thức XPath

## 1. Vì sao Spring-WS hỗ trợ lấy dữ liệu trực tiếp bằng XPath?

Trong dịch vụ SOAP theo hướng **contract-first**, XSD/WSDL mô tả rõ cấu trúc thông điệp XML, còn Spring Web Services (Spring-WS) định tuyến request đến endpoint dựa trên QName của phần tử gốc trong SOAP Body. Khi xử lý một request đơn giản, đôi khi endpoint chỉ cần lấy một vài thông tin nhỏ, chẳng hạn `orderId`, `correlationId` hoặc một node XML, mà không cần ánh xạ toàn bộ payload thành các Java object bằng JAXB.

Spring-WS cung cấp annotation **`@XPathParam`** để gán kết quả biểu thức XPath vào tham số phương thức endpoint. Các prefix xuất hiện trong XPath được khai báo bằng **`@Namespace`** hoặc **`@Namespaces`**.

Ví dụ ý tưởng:

~~~java
@PayloadRoot(
    namespace = "urn:example:orders:v1",
    localPart = "GetOrderRequest"
)
@Namespace(prefix = "ord", uri = "urn:example:orders:v1")
public void handle(
        @XPathParam("string(/ord:GetOrderRequest/ord:orderId)")
        String orderId) {
    // orderId lấy từ XML payload của SOAP request.
}
~~~

**Điều quan trọng:** XPath không chỉ dựa vào tên `orderId` hiển thị trên XML. Với XML sử dụng namespace, XPath cần định danh đúng **namespace URI và local name**. Nếu quên khai báo prefix hoặc nhầm URI, XPath có thể không chọn được node nào dù SOAP request vẫn hợp lệ theo XSD.

Bài thuộc chương **Xây dựng endpoint** của module **SPRING_WEB_SERVICES**. Sau bài học, bạn sẽ hiểu cách `@XPathParam` hoạt động, cách khai báo namespace ở nhiều phạm vi, cách xử lý kết quả XPath an toàn, cách kết hợp schema validation, JAXB/OXM và cách kiểm thử tương thích SOAP.

### Mục tiêu học tập

- Phân biệt vai trò `@PayloadRoot`, `@XPathParam` và `@Namespace`.
- Viết XPath đúng cho XML có default namespace, nhiều prefix và attribute.
- Dùng `@Namespace` hoặc `@Namespaces` ở method, class và package.
- Nhận dữ liệu vào `String`, `boolean`, `double`, `Node` hoặc `NodeList`; hiểu giới hạn của conversion.
- Tránh nhầm XML payload với toàn bộ SOAP Envelope trong biểu thức XPath.
- Phát hiện các tình huống không tìm thấy node, node rỗng, XPath chọn nhiều node, giá trị sai XSD và đổi namespace.
- Kiểm thử endpoint với `MockWebServiceClient` và XML fixtures độc lập với Java binding.
- Biết khi nào nên dùng XPath và khi nào nên dùng JAXB để giữ hợp đồng dễ bảo trì.

## 2. Nền tảng: QName, namespace và SOAP payload

### 2.1. SOAP Envelope bao bọc payload nghiệp vụ

Xét SOAP 1.1 request:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">

    <soap:Header/>

    <soap:Body>
        <ord:GetOrderRequest correlationId="REQ-1001">
            <ord:orderId>ORD-2048</ord:orderId>
            <ord:includeHistory>true</ord:includeHistory>
        </ord:GetOrderRequest>
    </soap:Body>
</soap:Envelope>
~~~

Có hai namespace với hai nhiệm vụ riêng:

| Namespace | Ý nghĩa |
|---|---|
| `http://schemas.xmlsoap.org/soap/envelope/` | Cấu trúc `Envelope`, `Header`, `Body` của SOAP 1.1 |
| `urn:example:orders:v1` | Các element nghiệp vụ `GetOrderRequest`, `orderId`, `includeHistory` |

Root payload trong SOAP Body có QName:

~~~text
{urn:example:orders:v1}GetOrderRequest
~~~

Trong Spring-WS, `@PayloadRoot(namespace=..., localPart=...)` được dùng để chọn method có trách nhiệm xử lý QName này.

### 2.2. @XPathParam được đánh giá trên request payload

Với `@XPathParam`, điểm bắt đầu XPath ở ví dụ endpoint thông thường là tài liệu/cây **payload** được Spring-WS cung cấp, không phải cả `soap:Envelope` như trong HTTP message nguyên bản.

Vì vậy, XPath đúng để lấy order ID là:

~~~xpath
/ord:GetOrderRequest/ord:orderId
~~~

hoặc nếu muốn kết quả chuỗi:

~~~xpath
string(/ord:GetOrderRequest/ord:orderId)
~~~

Đừng viết biểu thức dựa trên toàn bộ Envelope như:

~~~xpath
/soap:Envelope/soap:Body/ord:GetOrderRequest/ord:orderId
~~~

rồi mong `@XPathParam` luôn tìm thấy dữ liệu. XPath này chỉ phù hợp nếu đầu vào mà XPath đánh giá thật sự là cây XML có `soap:Envelope` ở root. Với argument resolver của Spring-WS, hãy xây biểu thức theo **payload root**.

**Không nhầm:** `@XPathParam` đọc XML thuộc phần payload. Nếu cần lấy dữ liệu trong SOAP Header như security token, correlation ID ở header hoặc actor/role, sử dụng API SOAP Header, `MessageContext` hay interceptor thích hợp; không giả định XPath đang đọc được mọi node của Envelope.

### 2.3. Prefix khác nhau nhưng QName có thể giống nhau

Hai XML sau biểu diễn cùng phần tử nghiệp vụ:

~~~xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
    <ord:orderId>ORD-2048</ord:orderId>
</ord:GetOrderRequest>
~~~

~~~xml
<x:GetOrderRequest xmlns:x="urn:example:orders:v1">
    <x:orderId>ORD-2048</x:orderId>
</x:GetOrderRequest>
~~~

Trong XPath Java, ta có thể dùng prefix `ord` cho cả hai nếu `ord` được ánh xạ đến URI `urn:example:orders:v1`. Prefix trong biểu thức XPath **không cần trùng** với prefix trong XML request. Điều cần trùng là **namespace URI**.

Ngược lại, nếu đổi namespace thành `urn:example:orders:v2`, QName đã khác và biểu thức XPath cho v1 sẽ không còn chọn các element đó một cách chính xác.

## 3. Viết XSD nhỏ để có hợp đồng kiểm thử rõ ràng

XSD minh họa cho `GetOrderRequest`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:ord="urn:example:orders:v1"
    targetNamespace="urn:example:orders:v1"
    elementFormDefault="qualified"
    attributeFormDefault="unqualified">

    <xs:element name="GetOrderRequest">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="orderId" type="xs:string"/>
                <xs:element name="includeHistory"
                            type="xs:boolean"
                            minOccurs="0"/>
            </xs:sequence>
            <xs:attribute name="correlationId"
                          type="xs:string"
                          use="required"/>
        </xs:complexType>
    </xs:element>

    <xs:element name="GetOrderResponse">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="orderId" type="xs:string"/>
                <xs:element name="status" type="xs:string"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
~~~

Những thông tin ảnh hưởng trực tiếp đến XPath:

1. `elementFormDefault="qualified"`: các local elements `orderId` và `includeHistory` thuộc namespace `urn:example:orders:v1`.
2. `attributeFormDefault="unqualified"`: attribute `correlationId` không có namespace trừ khi khai báo form riêng.
3. `includeHistory` có thể vắng mặt, do `minOccurs="0"`.
4. `orderId` bắt buộc có element, nhưng `xs:string` chưa cấm chuỗi rỗng. Muốn cấm rỗng thì cần facet như `xs:minLength` hoặc business validation.
5. Root request và root response là **global elements**; endpoint phải dùng đúng QName.

### 3.1. XPath tương ứng từng trường

| Muốn lấy | XPath | Kết quả mong đợi |
|---|---|---|
| Mã đơn | `string(/ord:GetOrderRequest/ord:orderId)` | `ORD-2048` |
| Attribute correlation | `string(/ord:GetOrderRequest/@correlationId)` | `REQ-1001` |
| Có phần tử `includeHistory` hay không | `boolean(/ord:GetOrderRequest/ord:includeHistory)` | `true` nếu node tồn tại |
| Giá trị `includeHistory` có bằng `true` hay không | `boolean(/ord:GetOrderRequest/ord:includeHistory = 'true')` | `true` nếu chuỗi giá trị đúng `true` |
| Lấy element `orderId` | `/ord:GetOrderRequest/ord:orderId` | Node/NodeList theo kiểu tham số |
| Lấy text node của `orderId` | `/ord:GetOrderRequest/ord:orderId/text()` | Text node |

**Chú ý:** XPath 1.0 có quy tắc riêng về kiểu kết quả và ép kiểu. Biểu thức `boolean(node-set)` cho biết **node có tồn tại**, không phải đang mang giá trị true/false. Với XML:

~~~xml
<ord:includeHistory xmlns:ord="urn:example:orders:v1">false</ord:includeHistory>
~~~

biểu thức:

~~~xpath
boolean(/ord:GetOrderRequest/ord:includeHistory)
~~~

vẫn trả **true**, vì element có tồn tại. Muốn kiểm tra giá trị, cần biểu thức so sánh hoặc nhận string rồi parse/validate ở tầng phù hợp.

## 4. @Namespace: khai báo prefix cho XPath

Spring-WS cung cấp annotation:

~~~java
import org.springframework.ws.server.endpoint.annotation.Namespace;
~~~

Một ví dụ khai báo ở method:

~~~java
@PayloadRoot(
    namespace = "urn:example:orders:v1",
    localPart = "GetOrderRequest"
)
@Namespace(
    prefix = "ord",
    uri = "urn:example:orders:v1"
)
public void handle(
        @XPathParam("string(/ord:GetOrderRequest/ord:orderId)")
        String orderId) {
    // ...
}
~~~

Ở đây:

- `@PayloadRoot` quyết định **request nào được dispatch** vào method.
- `@Namespace` định nghĩa prefix `ord` sẽ được XPath resolver hiểu là URI nào.
- `@XPathParam` định nghĩa **trường dữ liệu nào** cần lấy từ payload.

Nếu chỉ có `@PayloadRoot(namespace=...)` mà thiếu `@Namespace`, đừng mặc định resolver tự biết prefix `ord` trong XPath. Hai annotation phục vụ hai mục đích khác nhau.

### 4.1. Khai báo ở method, class hoặc package

`@Namespace` có thể đặt ở ba phạm vi:

| Phạm vi | Cách dùng | Phù hợp khi |
|---|---|---|
| Method | Ngay trên method `@PayloadRoot` | Một operation có namespace hoặc prefix riêng |
| Class | Ngay trên class `@Endpoint` | Nhiều operation cùng dùng một bộ namespace |
| Package | Trong `package-info.java` | Nhiều endpoint thuộc cùng contract namespace |

Ví dụ ở class:

~~~java
@Endpoint
@Namespace(prefix = "ord", uri = "urn:example:orders:v1")
public class OrderEndpoint {

    @PayloadRoot(
        namespace = "urn:example:orders:v1",
        localPart = "GetOrderRequest"
    )
    public void getOrder(
            @XPathParam("string(/ord:GetOrderRequest/ord:orderId)")
            String orderId) {
        // ...
    }

    @PayloadRoot(
        namespace = "urn:example:orders:v1",
        localPart = "CancelOrderRequest"
    )
    public void cancelOrder(
            @XPathParam("string(/ord:CancelOrderRequest/ord:orderId)")
            String orderId) {
        // ...
    }
}
~~~

Ví dụ ở package, tệp `package-info.java`:

~~~java
@org.springframework.ws.server.endpoint.annotation.Namespace(
    prefix = "ord",
    uri = "urn:example:orders:v1"
)
package com.example.orders.soap;
~~~

Khi dùng package annotation, cần đảm bảo file này được biên dịch đúng package chứa các endpoint. Nó khác với JAXB `package-info.java` dùng `@XmlSchema`; một package có thể cần nhiều annotation phục vụ mục đích khác nhau.

### 4.2. Quy tắc ưu tiên phạm vi

Trong Spring-WS, các annotation namespace được tìm từ package, class và method; **khai báo ở method có thể ghi đè mapping cùng prefix ở class, và class có thể ghi đè package**.

Ví dụ giả sử package khai báo:

~~~java
@Namespace(prefix = "ord", uri = "urn:example:orders:v1")
~~~

nhưng method được đánh dấu:

~~~java
@Namespace(prefix = "ord", uri = "urn:example:orders:v2")
~~~

thì những XPath chạy trong method này dùng mapping hiệu lực tại method. Điều đó có thể dẫn tới lỗi khó thấy khi `@PayloadRoot` vẫn nhận QName v1. Khi quản lý v1/v2, nên đặt namespace annotation tường minh và nhất quán, tránh ghi đè prefix âm thầm.

### 4.3. Tên prefix là lựa chọn của code, không phải API public

Bạn có thể chọn:

~~~java
@Namespace(prefix = "o", uri = "urn:example:orders:v1")
~~~

và dùng:

~~~xpath
/o:GetOrderRequest/o:orderId
~~~

dù request XML sử dụng prefix `ord`. Tuy nhiên, nên chọn prefix rõ nghĩa và nhất quán trong code để dễ bảo trì. Điều không được tự ý thay là **URI namespace của contract**.

## 5. @Namespaces: nhiều namespace trong cùng biểu thức XPath

Trong hợp đồng doanh nghiệp, request có thể sử dụng kiểu dùng chung từ một namespace khác.

Ví dụ payload:

~~~xml
<ord:GetOrderRequest
    xmlns:ord="urn:example:orders:v1"
    xmlns:com="urn:example:common:v1"
    correlationId="REQ-1001">

    <ord:meta>
        <com:tenantId>TENANT-A</com:tenantId>
        <com:requestId>REQ-1001</com:requestId>
    </ord:meta>

    <ord:orderId>ORD-2048</ord:orderId>
</ord:GetOrderRequest>
~~~

Đây là biến thể **mở rộng XSD** so với schema đơn giản ở phần 3: để hợp lệ, XSD phải khai báo `meta` và import kiểu `common` tương ứng. Payload này chỉ minh họa cách biểu thức XPath xử lý nhiều namespace, không được tự coi là hợp lệ với XSD ban đầu.

Spring-WS có `@Namespaces` để khai báo nhiều mapping:

~~~java
import org.springframework.ws.server.endpoint.annotation.Namespace;
import org.springframework.ws.server.endpoint.annotation.Namespaces;
import org.springframework.ws.server.endpoint.annotation.XPathParam;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.Endpoint;

@Endpoint
@Namespaces({
    @Namespace(
        prefix = "ord",
        uri = "urn:example:orders:v1"
    ),
    @Namespace(
        prefix = "com",
        uri = "urn:example:common:v1"
    )
})
public class MultiNamespaceEndpoint {

    @PayloadRoot(
        namespace = "urn:example:orders:v1",
        localPart = "GetOrderRequest"
    )
    public void getOrder(
            @XPathParam(
                "string(/ord:GetOrderRequest/ord:orderId)"
            ) String orderId,
            @XPathParam(
                "string(/ord:GetOrderRequest/ord:meta/com:tenantId)"
            ) String tenantId) {

        // Dùng dữ liệu sau khi kiểm tra hợp đồng và quyền truy cập.
    }
}
~~~

Hai đường XPath khác nhau được giải qua **hai namespace URI**. Đừng gắn `com:` vào `meta` chỉ vì các phần tử con bên trong có prefix `com:`: QName của `meta` phụ thuộc vào vị trí khai báo element trong XSD.

### 5.1. Phạm vi package cho nhiều namespace

Ví dụ `package-info.java`:

~~~java
@org.springframework.ws.server.endpoint.annotation.Namespaces({
    @org.springframework.ws.server.endpoint.annotation.Namespace(
        prefix = "ord",
        uri = "urn:example:orders:v1"
    ),
    @org.springframework.ws.server.endpoint.annotation.Namespace(
        prefix = "com",
        uri = "urn:example:common:v1"
    )
})
package com.example.orders.soap;
~~~

Khi package chứa nhiều class `@Endpoint` đều cần hai prefix này, cấu hình chung có thể giảm lặp lại. Nhưng việc khai báo ở package quá rộng cũng có thể làm người đọc khó thấy namespace thật của một operation; nên thiết kế theo ranh giới contract rõ ràng.

### 5.2. Khi nào cần nhiều namespace?

Không phải mọi SOAP request đều cần `@Namespaces`. Dùng khi biểu thức thực sự tham chiếu các element/attribute thuộc nhiều namespace, chẳng hạn một payload orders có child elements từ schema common. Nếu XPath chỉ truy cập `/ord:GetOrderRequest/@correlationId`, chỉ một mapping `ord` là đủ vì attribute `correlationId` không có namespace trong XSD minh họa.

## 6. Bẫy lớn nhất: default namespace của XML không áp dụng cho XPath

Xét XML dùng default namespace, không có prefix trong văn bản:

~~~xml
<GetOrderRequest xmlns="urn:example:orders:v1"
                 correlationId="REQ-1001">
    <orderId>ORD-2048</orderId>
    <includeHistory>true</includeHistory>
</GetOrderRequest>
~~~

Các element `GetOrderRequest`, `orderId`, `includeHistory` **vẫn thuộc namespace `urn:example:orders:v1`**.

Trong XPath 1.0, tên element không có prefix trong biểu thức như:

~~~xpath
/GetOrderRequest/orderId
~~~

thường được hiểu là các tên **không có namespace**. Vì vậy, biểu thức trên không chọn được các element XML trong ví dụ.

Cách đúng:

~~~xpath
/ord:GetOrderRequest/ord:orderId
~~~

với:

~~~java
@Namespace(prefix = "ord", uri = "urn:example:orders:v1")
~~~

**Không suy luận rằng XML không viết prefix thì XPath cũng không cần prefix.** XML namespace default là một phần của XML instance, còn namespace context của XPath là hệ ánh xạ prefix riêng.

### 6.1. Phân biệt element và attribute không có prefix

Xét:

~~~xml
<GetOrderRequest xmlns="urn:example:orders:v1"
                 correlationId="REQ-1001"/>
~~~

Ở đây:

- `GetOrderRequest` có QName `{urn:example:orders:v1}GetOrderRequest`.
- `correlationId` là **unqualified attribute** vì default namespace không tự áp dụng cho attribute không có prefix.

XPath đúng để đọc attribute:

~~~xpath
string(/ord:GetOrderRequest/@correlationId)
~~~

Không dùng:

~~~xpath
string(/ord:GetOrderRequest/@ord:correlationId)
~~~

trừ khi XSD thực sự khai báo attribute qualified và request XML cũng dùng namespace đó.

Một trường hợp attribute qualified có dạng:

~~~xml
<ord:GetOrderRequest
    xmlns:ord="urn:example:orders:v1"
    ord:correlationId="REQ-1001"/>
~~~

Khi đó XPath `@ord:correlationId` mới phù hợp. Hai attribute cùng local name nhưng một cái có namespace và một cái không có namespace là **hai QName khác nhau**.

### 6.2. Không nên sửa XPath bằng local-name() tùy tiện

Một cách né namespace thường thấy:

~~~xpath
/*[local-name()='GetOrderRequest']
  /*[local-name()='orderId']
~~~

Biểu thức này bỏ qua URI namespace nên có thể nhận nhầm payload v2 hoặc phần tử của miền nghiệp vụ khác có cùng local name. Trong SOAP contract-first, namespace chính là ranh giới tương thích.

Chỉ cân nhắc `local-name()` trong một thao tác chẩn đoán hoặc bài toán thật sự cần xử lý nhiều namespace theo chính sách được kiểm soát. Không dùng nó làm giải pháp mặc định để “chữa lỗi” quên `@Namespace`.

## 7. Một endpoint thực hành có @XPathParam và trả về XML

Giả sử service nghiệp vụ có interface:

~~~java
public interface OrderLookupService {
    String statusOf(String orderId);
}
~~~

Một endpoint có thể lấy hai giá trị XPath và xây XML response bằng DOM. Ví dụ sau chủ ý dùng `Source` thay vì JAXB để người học thấy rõ hoạt động của `@XPathParam`.

~~~java
package com.example.orders.soap;

import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.parsers.ParserConfigurationException;
import javax.xml.transform.dom.DOMSource;

import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.Namespace;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;
import org.springframework.ws.server.endpoint.annotation.XPathParam;

import org.w3c.dom.Document;
import org.w3c.dom.Element;

@Endpoint
@Namespace(prefix = "ord", uri = "urn:example:orders:v1")
public class GetOrderEndpoint {

    private static final String NS = "urn:example:orders:v1";

    private final OrderLookupService service;

    public GetOrderEndpoint(OrderLookupService service) {
        this.service = service;
    }

    @PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
    @ResponsePayload
    public DOMSource getOrder(
            @XPathParam(
                "string(/ord:GetOrderRequest/ord:orderId)"
            ) String orderId,

            @XPathParam(
                "string(/ord:GetOrderRequest/@correlationId)"
            ) String correlationId)
            throws ParserConfigurationException {

        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException(
                "orderId không được rỗng"
            );
        }

        String status = service.statusOf(orderId);

        DocumentBuilderFactory factory =
            DocumentBuilderFactory.newInstance();
        factory.setNamespaceAware(true);

        // Chỉ tạo Document mới, không parse XML không tin cậy tại đây.
        Document document =
            factory.newDocumentBuilder().newDocument();

        Element response = document.createElementNS(
            NS,
            "ord:GetOrderResponse"
        );
        document.appendChild(response);

        Element id = document.createElementNS(
            NS,
            "ord:orderId"
        );
        id.setTextContent(orderId);
        response.appendChild(id);

        Element state = document.createElementNS(
            NS,
            "ord:status"
        );
        state.setTextContent(status);
        response.appendChild(state);

        return new DOMSource(document);
    }
}
~~~

Giải thích điểm chính:

1. `@Endpoint` đánh dấu Spring-WS endpoint.
2. `@Namespace` cho phép các biểu thức `ord:` được giải đến namespace URI v1.
3. `@PayloadRoot` định tuyến request có QName `GetOrderRequest`.
4. Mỗi `@XPathParam` đánh giá một biểu thức trên payload đầu vào.
5. Kết quả XPath được đưa vào `String` tương ứng.
6. Response được xây bằng DOM namespace-aware và trả dưới dạng `DOMSource` để Spring-WS tạo payload response.

Biến `correlationId` có trong chữ ký để minh họa chọn attribute; endpoint hiện chưa sử dụng nó. Trong ứng dụng thật, nên dùng để logging/correlation theo chính sách hoặc bỏ hẳn tham số nếu không cần.

Cách tạo response bằng DOM ở đây có lợi khi học namespace và XPath, nhưng trong dự án lớn **thường nên tạo JAXB response theo XSD** vì JAXB có cấu trúc type rõ ràng, tránh viết tay nhiều element. Bất kể dùng DOM hay JAXB, response phải được kiểm tra với XSD và WSDL đã công bố.

### 7.1. Vì sao dùng setTextContent, không nối chuỗi XML?

Không nên làm:

~~~java
String xml =
    "<ord:status>" + status + "</ord:status>";
~~~

Nếu status hoặc dữ liệu khác chứa `&`, `<` hay ký tự đặc biệt, chuỗi XML có thể không well-formed. Dùng DOM `setTextContent` hoặc JAXB marshaller giúp escaping đúng và tránh lỗi injection dạng tạo XML bằng string concatenation.

Bảo vệ này không có nghĩa tất cả XML parser đều an toàn: những nơi **parse XML từ nguồn không tin cậy** vẫn cần cấu hình chống XXE, external entity và resource exhaustion.

### 7.2. Không dùng @XPathParam làm validator nghiệp vụ

Trong ví dụ, `orderId.isBlank()` chỉ là kiểm tra cơ bản. XSD có thể quy định `minLength`, `pattern`, `maxLength` và kiểu dữ liệu khác. Phần kiểm tra có thể triển khai bằng `PayloadValidatingInterceptor`.

Sau khi XSD hợp lệ, domain service vẫn có thể cần kiểm tra orderId tồn tại, người gọi có quyền truy cập hay không và trạng thái đơn hàng có được phép truy vấn không. `@XPathParam` không tự thực hiện những kiểm tra đó.

### 7.3. Trả JAXB response thay vì DOM

Với dự án đã sinh JAXB classes từ XSD, một method có thể nhận tham số qua `@XPathParam` nhưng **trả về JAXB object**:

~~~java
@PayloadRoot(
    namespace = "urn:example:orders:v1",
    localPart = "GetOrderRequest"
)
@Namespace(prefix = "ord", uri = "urn:example:orders:v1")
@ResponsePayload
public GetOrderResponse getOrder(
        @XPathParam(
            "string(/ord:GetOrderRequest/ord:orderId)"
        ) String orderId) {

    GetOrderResponse response = new GetOrderResponse();
    response.setOrderId(orderId);
    response.setStatus(service.statusOf(orderId));

    return response;
}
~~~

Đoạn trên giả định XJC sinh class `GetOrderResponse` có `@XmlRootElement` đúng QName và Spring-WS có return value processor JAXB phù hợp. Nếu schema sinh `GetOrderResponseType` với global element declaration, hãy dùng `ObjectFactory.createGetOrderResponse(...)` để trả `JAXBElement<...>`.

**Bài học quan trọng:** Sử dụng XPath ở **chiều request** không bắt buộc phải dùng XPath/DOM ở **chiều response**.

## 8. Kiểu dữ liệu mà @XPathParam hỗ trợ

Trong Spring-WS, các kiểu được hỗ trợ trực tiếp từ kết quả XPath gồm:

- `boolean` hoặc `Boolean`.
- `double` hoặc `Double`.
- `String`.
- `org.w3c.dom.Node`.
- `org.w3c.dom.NodeList`.

Ngoài ra, một số kiểu có thể được nhận thông qua **Spring ConversionService** chuyển từ kết quả kiểu chuỗi, tùy cấu hình và khả năng converter của runtime. Ví dụ tài liệu Spring-WS có minh họa tham số số nguyên `int` khi converter phù hợp.

| Mục tiêu | Ví dụ biểu thức | Kiểu Java thường phù hợp | Lưu ý |
|---|---|---|---|
| Giá trị text | `string(/ord:GetOrderRequest/ord:orderId)` | `String` | Missing node thường cho `""` theo hàm `string()` XPath 1.0 |
| Có node hay không | `boolean(/ord:GetOrderRequest/ord:note)` | `boolean` | Kiểm tra presence, không phải nội dung `true` |
| So sánh boolean | `boolean(/ord:GetOrderRequest/ord:includeHistory = 'true')` | `boolean` | Không tự coi `1` là `true` như kiểu `xs:boolean` |
| Số XPath | `number(/ord:GetOrderRequest/ord:quantity)` | `double` | XPath 1.0 dùng số dấu chấm động, không dùng cho tiền tệ cần chính xác |
| Element đầu tiên | `/ord:GetOrderRequest/ord:orderId` | `Node` | Có thể không có node, kiểm tra null |
| Danh sách element | `/ord:GetOrderRequest/ord:item` | `NodeList` | Xử lý namespace và thứ tự node |

### 8.1. Boolean XPath khác boolean XSD

Trong XSD, `xs:boolean` có lexical values hợp lệ bao gồm `true`, `false`, `1`, `0`. Nếu code viết:

~~~xpath
/ord:GetOrderRequest/ord:includeHistory = 'true'
~~~

thì XML:

~~~xml
<ord:includeHistory xmlns:ord="urn:example:orders:v1">1</ord:includeHistory>
~~~

hợp lệ theo `xs:boolean` nhưng biểu thức so sánh chuỗi với `'true'` sẽ cho `false`.

Cách giải quyết phụ thuộc yêu cầu:

- Nếu cần semantics XSD chuẩn, đọc giá trị và dùng bước validation/conversion phù hợp.
- Nếu hợp đồng thực tế buộc chỉ dùng `true`/`false`, hãy ghi rõ constraint bổ sung phù hợp thay vì mặc định mọi `xs:boolean` đều chỉ có hai lexical forms.
- Với field optional, đừng gộp tự động “không gửi” và “gửi false” nếu nghiệp vụ phân biệt hai trạng thái.

### 8.2. Số tiền không nên lấy bằng XPath double

XPath 1.0 dùng kiểu `number` với phép biểu diễn số dạng double. Khi xử lý tiền tệ `xs:decimal`, lấy `double` rồi chuyển sang `BigDecimal` có thể gây sai số.

Ví dụ an toàn hơn:

~~~java
@XPathParam(
    "string(/ord:SubmitOrderRequest/ord:amount)"
)
String amountText
~~~

Sau khi schema validation, có thể parse:

~~~java
BigDecimal amount = new BigDecimal(amountText);
~~~

và áp dụng kiểm tra business/scale phù hợp. `BigDecimal` giữ độ chính xác thập phân, nhưng XPath annotation **không tự xác nhận** `totalDigits`, `fractionDigits` hoặc min/max của XSD.

### 8.3. Node và NodeList cho dữ liệu phức tạp

Khi một request có danh sách `item`:

~~~xml
<ord:SubmitOrderRequest xmlns:ord="urn:example:orders:v1">
    <ord:item>
        <ord:sku>SKU-01</ord:sku>
    </ord:item>
    <ord:item>
        <ord:sku>SKU-02</ord:sku>
    </ord:item>
</ord:SubmitOrderRequest>
~~~

Có thể nhận:

~~~java
public void submit(
        @XPathParam(
            "/ord:SubmitOrderRequest/ord:item"
        ) NodeList items) {

    for (int i = 0; i < items.getLength(); i++) {
        Node itemNode = items.item(i);
        // Xử lý node theo QName và schema, không dựa vào prefix.
    }
}
~~~

Đoạn chỉ minh họa tham số `NodeList`; để trở thành endpoint cần đủ `@Endpoint`, `@PayloadRoot`, `@Namespace` và khai báo response thích hợp.

Với payload lớn hoặc nested collections phức tạp, việc viết nhiều XPath/DOM traversal có thể khiến code khó kiểm soát. Hãy cân nhắc JAXB hoặc StAX nếu cần một mô hình dữ liệu rõ ràng hoặc xử lý streaming.

## 9. Khi XPath không tìm thấy node: không vội kết luận dữ liệu null

Một XPath có thể không chọn được node vì nhiều nguyên nhân:

1. Element thật sự vắng mặt theo `minOccurs="0"`.
2. XPath chọn sai namespace URI.
3. XPath chọn sai local name, ví dụ `orderID` thay `orderId`.
4. XPath có thêm `soap:Envelope/soap:Body` dù resolver đang chạy trên payload.
5. Element nằm ở nhánh khác hoặc đường dẫn sai theo `xs:sequence`/model XML.
6. Attribute thực tế không có namespace nhưng XPath lại dùng prefix.
7. Client gửi contract v2 nhưng endpoint/XPath dùng namespace v1.
8. XML không hợp lệ và chưa được schema validation từ chối đúng.

### 9.1. So sánh missing, empty và nil

XSD có thể khai báo:

~~~xml
<xs:element name="note"
            type="xs:string"
            minOccurs="0"
            nillable="true"/>
~~~

Ba trường hợp:

~~~xml
<!-- 1. note vắng mặt -->
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

Nếu XPath chỉ lấy:

~~~xpath
string(/ord:UpdateOrderRequest/ord:note)
~~~

thì cả ba trường hợp có thể cho chuỗi rỗng. Điều đó **không chứng minh** chúng có cùng ngữ nghĩa.

Để phân biệt, cần kiểm tra **sự tồn tại của node** và **trạng thái `xsi:nil`**:

~~~xpath
boolean(/ord:UpdateOrderRequest/ord:note)
~~~

~~~xpath
boolean(
  /ord:UpdateOrderRequest/ord:note[@xsi:nil = 'true' or @xsi:nil = '1']
)
~~~

Biểu thức thứ hai cần khai báo thêm:

~~~java
@Namespace(
    prefix = "xsi",
    uri = "http://www.w3.org/2001/XMLSchema-instance"
)
~~~

hoặc đặt trong `@Namespaces` cùng prefix nghiệp vụ. Cũng phải bảo đảm XSD cho phép nillable và XML instance hợp lệ. Nếu ý nghĩa absent/nil/empty quan trọng trong nhiều field, binding JAXB có thể là lựa chọn dễ bảo trì hơn việc truyền nhiều boolean/XPath params rời rạc.

### 9.2. String() không tự phân biệt “missing” và “empty”

XPath 1.0:

~~~xpath
string(/ord:GetOrderRequest/ord:orderId)
~~~

cho chuỗi rỗng nếu node-set không có node phù hợp. Nếu node `orderId` tồn tại nhưng nội dung rỗng, kết quả cũng là `""`.

Đừng dùng `String.isEmpty()` làm cách duy nhất để xác định payload có element hay không. Với `minOccurs=1`, schema validation sẽ phát hiện trường hợp element vắng mặt. Với ứng dụng cập nhật một phần, cần tách presence khỏi value.

### 9.3. Node-set có nhiều phần tử

Nếu biểu thức XPath dùng `string(node-set)`, XPath 1.0 sẽ lấy string-value của node đầu tiên theo thứ tự tài liệu. Nếu contract cho phép nhiều `item`, việc dùng `String` cho XPath tới tất cả `item` có thể âm thầm bỏ những item còn lại.

Hãy dùng `NodeList` hoặc dữ liệu JAXB `List<T>`, đồng thời kiểm tra `minOccurs`/`maxOccurs` của XSD.

## 10. Kết hợp XPath với schema validation

Một endpoint có `@XPathParam` vẫn cần xử lý request hợp đồng chuẩn. `@XPathParam` không thay thế kiểm tra XSD.

Có thể khai báo Spring-WS interceptor:

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
public class SoapValidationConfiguration implements WsConfigurer {

    private final XsdSchema ordersSchema;

    public SoapValidationConfiguration(
            @Qualifier("ordersSchema") XsdSchema ordersSchema) {
        this.ordersSchema = ordersSchema;
    }

    @Override
    public void addInterceptors(
            List<EndpointInterceptor> interceptors) {

        PayloadValidatingInterceptor interceptor =
            new PayloadValidatingInterceptor();

        interceptor.setXsdSchema(ordersSchema);
        interceptor.setValidateRequest(true);
        interceptor.setValidateResponse(true);

        interceptors.add(interceptor);
    }
}
~~~

Giả định `ordersSchema` đã là bean `XsdSchema` chứa đầy đủ request/response và các import/include được phân giải. Khi XSD chỉ mô tả request, bật validateResponse sẽ cần bổ sung schema response tương ứng.

Quy trình mong muốn:

~~~mermaid
flowchart TD
    A["SOAP request"] --> B["Envelope + Header processing"]
    B --> C["Payload QName mapping"]
    C --> D["XSD validation"]
    D --> E["XPathParam argument resolution"]
    E --> F["Endpoint"]
    F --> G["Domain validation"]
    G --> H["Response payload / SOAP Fault"]
~~~

Thứ tự thực tế của mapping, interceptor, resolver và marshalling phụ thuộc cấu hình Spring-WS; sơ đồ chỉ trình bày các lớp trách nhiệm. Trong ứng dụng, phải kiểm tra rằng **request sai XSD bị từ chối trước khi nghiệp vụ thực hiện side effect**.

### 10.1. XPath chỉ lấy dữ liệu, không bảo đảm hợp đồng

Dù `@XPathParam` có thể đọc `orderId`, request vẫn có thể:

- Thiếu required attribute.
- Gửi `includeHistory` không phải `xs:boolean`.
- Chứa element thừa không có trong XSD.
- Sai thứ tự `xs:sequence`.
- Có QName v2 trong khi schema hỗ trợ v1.
- Có giá trị vi phạm `pattern`, `minLength`, `maxLength`.

Vì vậy, kiểm thử cả **happy path** và **negative cases** với payload độc lập từ đối tác.

### 10.2. Fault cần được thiết kế, không lộ chi tiết nội bộ

Nếu XPath không tìm được một field bắt buộc, hoặc application service phát hiện orderId không tồn tại, server nên trả SOAP Fault theo chính sách đã công bố. Lỗi xác thực XSD, lỗi nghiệp vụ và lỗi hạ tầng có thể cần mã và detail khác nhau.

Không trả raw stack trace, XPath expression nội bộ quá chi tiết, SQL, access token hoặc thông tin WS-Security nhạy cảm trong Fault. SOAP 1.1 và SOAP 1.2 có cấu trúc Fault khác nhau; phải kiểm thử theo phiên bản thực tế.

## 11. Cấu hình endpoint: Java và XML

### 11.1. Java Config

Một ứng dụng Spring Boot/Spring-WS có thể kích hoạt hạ tầng annotation endpoint:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.config.annotation.EnableWs;

@Configuration
@EnableWs
public class SoapEndpointConfig {
}
~~~

Kèm component scan bao phủ package có class `@Endpoint`, framework sẽ đăng ký mapping/adapter tương ứng. Với Spring-WS hiện đại, `DefaultMethodEndpointAdapter` và `XPathParamMethodArgumentResolver` tham gia cơ chế xử lý tham số.

Nếu một ứng dụng đã có cấu hình Spring Boot tự động hoặc các bean Spring-WS do thư viện nội bộ đăng ký, cần kiểm tra tránh trùng mapping/adapter. Chỉ có class `@Endpoint` tồn tại trong source chưa đảm bảo nó đã được scan hoặc được kết nối đúng vào `MessageDispatcherServlet`.

### 11.2. Spring XML trong hệ thống hiện hữu

Hệ thống sử dụng Spring XML có thể bật annotation-driven:

~~~xml
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
</beans>
~~~

Các class `@Endpoint`, `@PayloadRoot`, `@XPathParam`, `@Namespace` vẫn có thể được dùng trong endpoint Java dù bean infrastructure được khai báo bằng XML.

Với những Spring-WS phiên bản rất cũ, có thể gặp `XPathParamAnnotationMethodEndpointAdapter` và cách đăng ký namespace map trong XML. Những API đó thuộc mô hình cũ; Spring-WS hiện đại sử dụng `XPathParamMethodArgumentResolver` cùng namespace annotations. Khi nâng cấp, đối chiếu version và migration path thay vì sao chép cấu hình đã lỗi thời.

## 12. Khi nào chọn XPath, khi nào chọn JAXB/OXM?

Không có quy tắc XPath luôn nhanh hơn hoặc JAXB luôn tốt hơn. Hãy đánh giá từ hợp đồng và độ phức tạp của việc xử lý.

| Tiêu chí | @XPathParam | JAXB/OXM |
|---|---|---|
| Request rất nhỏ, chỉ vài field | Gọn, chọn trực tiếp field cần dùng | Có thể cần tạo/sinh binding classes |
| Request có cấu trúc lồng nhau | Nhiều biểu thức XPath khó bảo trì | Object graph thể hiện cấu trúc rõ |
| Danh sách lớn | `NodeList`/DOM có thể tốn bộ nhớ | JAXB cũng có overhead; streaming có thể cần StAX |
| Optional/nil/empty nhiều trường | Phải tự kiểm tra presence/nil/value | Binding phù hợp có thể bảo toàn rõ qua JAXBElement |
| Kiểu dữ liệu và enum | XPath trả kiểu hạn chế, cần convert | XJC sinh kiểu Java phù hợp XSD |
| Namespace nhiều miền | Cần `@Namespaces` và XPath cẩn thận | JAXB/XSD cũng cần namespace đúng, nhưng thường sinh tự động |
| Thay đổi contract | XPath string literal phải cập nhật thủ công | Binding được sinh lại, thay đổi hiện rõ ở compile/test |
| Debug giá trị một node | Tiện kiểm tra chọn node | Cần inspect object |
| XSD validation | Phải cấu hình độc lập | Vẫn nên có validation, không tự động đảm bảo |
| Tích hợp Spring-WS | Có resolver annotation chuyên dụng | Có JAXB argument/return value processors |

### 12.1. Trường hợp dùng XPath hợp lý

Endpoint chỉ cần đọc `orderId` từ một request nhỏ và gọi domain service. Biểu thức rõ ràng, stable theo XSD và có test QName đầy đủ. `@XPathParam` giúp giảm mã ánh xạ object cho một vài field.

### 12.2. Trường hợp nên cân nhắc JAXB

Endpoint nhận `SubmitOrderRequest` chứa nhiều item, các nhánh `xs:choice`, enum, số tiền, ngày giờ, dữ liệu tùy chọn/nillable và nhiều kiểu từ nhiều namespace. JAXB/XJC giúp giữ cấu trúc hợp đồng rõ ràng hơn, giảm rủi ro bỏ sót khi copy nhiều XPath.

### 12.3. Có thể kết hợp hai cách

Một endpoint có thể dùng XPath cho metadata/correlation hoặc field rất nhỏ, còn các endpoint khác sử dụng JAXB. Trong cùng một dịch vụ, việc chọn cách ánh xạ nên có tiêu chí nhất quán, không chỉ dựa vào sở thích của từng developer.

## 13. Kiểm thử @XPathParam với dữ liệu biên

Một bộ kiểm thử cần chứng minh XPath hoạt động với **namespace URI**, không phụ thuộc prefix do client chọn.

### 13.1. Ma trận hợp đồng và dữ liệu

| Ca | XML request | Kỳ vọng |
|---|---|---|
| T1 | Prefix `ord`, URI v1, orderId hợp lệ | Đúng endpoint, XPath lấy đúng orderId |
| T2 | Đổi prefix `ord` thành `x`, URI v1 giữ nguyên | Hành vi không đổi |
| T3 | Default namespace v1, element không có prefix | XPath prefix trong Java vẫn chọn được |
| T4 | URI đổi thành v2 | Không được định tuyến như payload v1 |
| T5 | Thiếu `orderId` | Bị schema validation từ chối nếu XSD yêu cầu |
| T6 | `orderId` rỗng | Kiểm tra theo facet hoặc nghiệp vụ; XSD minh họa chưa cấm rỗng |
| T7 | Thiếu `correlationId` | Bị XSD từ chối vì attribute required |
| T8 | `correlationId` là attribute unqualified | XPath `@correlationId` lấy đúng |
| T9 | `includeHistory=false` | XPath presence true, giá trị boolean false |
| T10 | `includeHistory=1` | Hợp lệ theo xs:boolean; so text với `'true'` không tự thành true |
| T11 | Gửi child element sai namespace | Không hợp schema v1 |
| T12 | XML không well-formed hoặc dữ liệu xâm nhập | Không chạy nghiệp vụ; phản hồi an toàn |

Ngoài các trường hợp này, nếu dùng `NodeList` cần test số lượng node 0/1/nhiều và thứ tự; nếu dùng nil cần test absent/nil/empty.

### 13.2. Dùng MockWebServiceClient kiểm thử không qua HTTP

Spring-WS cung cấp `MockWebServiceClient` từ `spring-ws-test` để gửi payload tới application context chứa endpoint. Một skeleton test có thể như sau:

~~~java
import static org.springframework.ws.test.server.RequestCreators.withPayload;
import static org.springframework.ws.test.server.ResponseMatchers.payload;

import org.junit.jupiter.api.Test;
import org.springframework.context.ApplicationContext;
import org.springframework.ws.test.server.MockWebServiceClient;
import org.springframework.xml.transform.StringSource;

class OrderXPathEndpointTest {

    private final MockWebServiceClient client;

    OrderXPathEndpointTest(ApplicationContext context) {
        this.client = MockWebServiceClient.createClient(context);
    }

    @Test
    void namespacePrefixDoesNotChangeMeaning() {
        String request = """
            <x:GetOrderRequest
                xmlns:x="urn:example:orders:v1"
                correlationId="REQ-1001">
                <x:orderId>ORD-2048</x:orderId>
                <x:includeHistory>true</x:includeHistory>
            </x:GetOrderRequest>
            """;

        String expected = """
            <x:GetOrderResponse xmlns:x="urn:example:orders:v1">
                <x:orderId>ORD-2048</x:orderId>
                <x:status>PAID</x:status>
            </x:GetOrderResponse>
            """;

        client.sendRequest(withPayload(new StringSource(request)))
            .andExpect(payload(new StringSource(expected)));
    }
}
~~~

**Đây là test skeleton**, chưa phải một class JUnit chạy độc lập nếu thiếu cấu hình inject `ApplicationContext`, Spring test extension và test bean `OrderLookupService` trả giá trị `PAID`. Cũng cần endpoint được component scan, `@EnableWs`, dependency `spring-ws-test` và framework version tương thích.

Bộ test hoàn chỉnh nên có **ít nhất một case dùng default namespace**, một case dùng prefix khác nhưng cùng URI và một case sai namespace. Khi so XML, nên dùng comparator/matcher hiểu XML namespace thay vì ép string prefix giống từng byte.

### 13.3. Test trực tiếp XPath độc lập với Spring

Nếu muốn kiểm tra một biểu thức dài trước khi đưa vào annotation, có thể dùng JAXP XPath API:

~~~java
import javax.xml.XMLConstants;
import javax.xml.namespace.NamespaceContext;
import javax.xml.xpath.XPath;
import javax.xml.xpath.XPathConstants;
import javax.xml.xpath.XPathFactory;

// document là DOM Document đã parse an toàn và namespace-aware.
XPath xpath = XPathFactory.newInstance().newXPath();

xpath.setNamespaceContext(new NamespaceContext() {

    @Override
    public String getNamespaceURI(String prefix) {
        return switch (prefix) {
            case "ord" -> "urn:example:orders:v1";
            case "xml" -> XMLConstants.XML_NS_URI;
            default -> XMLConstants.NULL_NS_URI;
        };
    }

    @Override
    public String getPrefix(String namespaceURI) {
        return null;
    }

    @Override
    public java.util.Iterator<String> getPrefixes(
            String namespaceURI) {
        return java.util.Collections.emptyIterator();
    }
});

String orderId = (String) xpath.evaluate(
    "string(/ord:GetOrderRequest/ord:orderId)",
    document,
    XPathConstants.STRING
);
~~~

Đoạn trên minh họa namespace context của **JAXP**, không phải replacement bắt buộc cho `@Namespace` của Spring-WS. Nó giả định bạn đã có DOM `document` được parse an toàn; với những hệ thống cần xử lý nhiều prefix, nên viết một NamespaceContext hoàn chỉnh theo contract thay vì coi skeleton này là component production.

Điểm đáng chú ý: prefix `ord` được ánh xạ trong code sang URI v1; nó không cần trùng prefix thật trong XML document.

### 13.4. Test qua SOAP HTTP thật vẫn cần thiết

`MockWebServiceClient` không kiểm tra tất cả:

- `MessageDispatcherServlet` mapping.
- HTTP Content-Type `text/xml` hay `application/soap+xml`.
- SOAPAction/action của binding.
- SOAP Envelope namespace và lỗi phiên bản.
- Proxy, TLS, xác thực HTTP, timeout.
- WS-Security Header/chữ ký/chứng chỉ được triển khai trong pipeline thực tế.

Một integration test qua HTTP SOAP phải xác nhận XPath được đánh giá đúng sau khi message đã đi qua transport, interceptor và security stack. XSD/WSDL công bố cũng cần được kiểm tra bằng công cụ client độc lập.

## 14. An toàn khi dùng XPath và XML đầu vào

### 14.1. XPath injection và biểu thức động

`@XPathParam` sử dụng biểu thức được khai báo tĩnh trong annotation; đây là cách tốt để tránh việc nối input người dùng vào XPath expression.

Không nên lấy một giá trị từ SOAP request rồi xây XPath theo cách:

~~~java
String expression =
    "/ord:GetOrderRequest/ord:item[ord:sku='" +
    userSuppliedSku +
    "']";
~~~

Nếu `userSuppliedSku` chứa ký tự XPath đặc biệt, biểu thức có thể bị thay đổi ý nghĩa, gây lỗi hoặc XPath injection. Khi thật sự cần XPath động, hãy sử dụng biến XPath hoặc xử lý dữ liệu theo một cách không đưa raw input vào cú pháp XPath.

Trong bài toán chỉ cần lấy dữ liệu từ payload đã có schema, thường nên dùng một XPath **cố định** hoặc chuyển sang JAXB/domain filtering.

### 14.2. XXE và external entities

XPath evaluation phụ thuộc vào việc XML được parse thành DOM/nguồn tương đương. Với XML từ nguồn không tin cậy, phải cấu hình XML parser/SOAP message stack để hạn chế DTD, external entities và truy cập tài nguyên ngoài.

Không thể chống XXE chỉ bằng việc kiểm tra namespace trong XPath. Nếu sử dụng `DocumentBuilderFactory` để parse XML tự làm, cần bật secure-processing và cấm các tính năng external entity không cần thiết theo JAXP/runtime. Với Spring-WS, cần kiểm tra cấu hình SOAP message factory và các thư viện XML được dùng.

### 14.3. XPath phức tạp có thể tốn tài nguyên

Các biểu thức dùng `//` quét nhiều node, predicates phức tạp hoặc materialize `NodeList` lớn có thể tăng chi phí CPU/bộ nhớ. Với request nhiều MB hoặc danh sách lớn, nên cân nhắc JAXB/StAX, streaming, giới hạn kích thước payload và số phần tử.

Một đường dẫn cụ thể như:

~~~xpath
/ord:GetOrderRequest/ord:orderId
~~~

thường dễ hiểu và ít rủi ro hơn:

~~~xpath
//ord:orderId
~~~

vì biểu thức thứ hai có thể chọn một `orderId` nằm ở nhánh khác ngoài ý định.

### 14.4. Không dựa vào XPath để xác thực quyền hoặc chữ ký

SOAP Header có thể chứa WS-Security tokens/chữ ký, còn payload chứa dữ liệu nghiệp vụ. Việc XPath chọn đúng `orderId` **không chứng minh** người gọi có quyền xem đơn hoặc thông điệp có chữ ký hợp lệ.

Hãy đặt xác thực/trust policy, WS-Security và domain authorization đúng tầng. Nếu SOAP Body được ký, đảm bảo toàn bộ pipeline kiểm tra chữ ký trước khi ứng dụng tin cậy dữ liệu; không sửa XML đã ký theo cách vô tình làm mất hiệu lực chữ ký.

## 15. Những lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
|---|---|---|
| XPath trả chuỗi rỗng dù XML có element | Thiếu `@Namespace`, sai prefix mapping | Kiểm tra `targetNamespace`, `@Namespace` và XPath |
| XPath không chọn element khi XML dùng default namespace | Viết XPath không prefix | Dùng prefix trong XPath và ánh xạ URI đúng |
| Gửi prefix khác làm test fail | So prefix/string thay vì QName | So URI namespace + local name |
| @PayloadRoot nhận request nhưng XPath không có dữ liệu | XPath viết theo SOAP Envelope hoặc đường dẫn sai | Bắt đầu từ payload root |
| XPath attribute trả rỗng | Attribute unqualified nhưng XPath có prefix, hoặc ngược lại | Kiểm tra `attributeFormDefault`, `form` |
| Boolean trả true khi XML chứa false | Dùng `boolean(node-set)` để kiểm tra giá trị | Phân biệt node presence và giá trị xs:boolean |
| XML `<x/>` và absent cùng ra `""` | Dùng `string(...)` | Kiểm tra presence/nil trước khi diễn giải |
| Trả chỉ item đầu tiên | Dùng String XPath cho node-set nhiều phần tử | Sử dụng `NodeList` hoặc JAXB List |
| Converter không xử lý được kiểu tham số | Chọn kiểu ngoài hỗ trợ và ConversionService không có converter | Thử String/Node/NodeList hoặc cấu hình converter |
| Request vi phạm XSD vẫn vào nghiệp vụ | Chưa bật validation hoặc schema không đầy đủ | PayloadValidatingInterceptor, test negative |
| Runtime báo không có endpoint adapter | Annotation infrastructure/bean context thiếu | `@EnableWs`, `<sws:annotation-driven/>`, resolver |
| Request v2 đến endpoint v1 | QName/versioning bị bỏ qua hoặc bypass mapping | Không dùng local-name-only workaround |
| SOAP Fault khác kỳ vọng | SOAP version/resolver/interceptor cấu hình khác | Kiểm tra binding, Fault và HTTP status |

### 15.1. Quy trình debug ngắn

Nếu endpoint nhận được request nhưng `orderId` rỗng:

1. Xác nhận raw SOAP payload (đã che dữ liệu nhạy cảm), QName root và namespace URI.
2. Kiểm tra `@PayloadRoot(namespace=..., localPart=...)`.
3. Kiểm tra biểu thức XPath bắt đầu từ payload root.
4. Kiểm tra `@Namespace`/ `@Namespaces` trong method/class/package và thứ tự override.
5. Kiểm tra local element/attribute thực sự có namespace nào theo XSD.
6. Tạo fixture XML tối giản và thử XPath namespace-aware độc lập.
7. Kiểm tra schema validation đã bật và chặn dữ liệu không hợp lệ.
8. Chạy lại integration test qua Spring-WS và một client SOAP độc lập.

Không sửa bằng cách bỏ namespace khỏi XPath hoặc lấy phần tử đầu tiên tên `orderId` ở bất cứ vị trí nào mà không có contract cho phép.

## 16. Thực hành nâng cao: nhiều namespace và giá trị boolean

Cho payload:

~~~xml
<ord:SubmitOrderRequest
    xmlns:ord="urn:example:orders:v1"
    xmlns:com="urn:example:common:v1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    correlationId="REQ-2002">

    <ord:meta>
        <com:tenantId>T-02</com:tenantId>
    </ord:meta>

    <ord:orderId>ORD-2048</ord:orderId>
    <ord:includeHistory>1</ord:includeHistory>
    <ord:note xsi:nil="true"/>
</ord:SubmitOrderRequest>
~~~

Giả sử XSD đã khai báo các elements tương ứng, includeHistory kiểu xs:boolean và note nillable.

Hãy hoàn thành:

1. Khai báo `@PayloadRoot` cho `SubmitOrderRequest`.
2. Khai báo `@Namespaces` cho `ord`, `com`, `xsi`.
3. Viết `@XPathParam` lấy `orderId` dạng String.
4. Viết `@XPathParam` lấy `tenantId` trong `ord:meta/com:tenantId`.
5. Viết XPath kiểm tra `note` có hiện diện hay không.
6. Viết XPath xác định `note` có `xsi:nil="true"` hay `"1"` không.
7. Giải thích tại sao phép so sánh `includeHistory = 'true'` không đủ để đọc mọi lexical form hợp lệ của xs:boolean.
8. Viết test đổi prefix trong XML nhưng giữ namespace, và test đổi URI namespace thì phải không còn được định tuyến như v1.
9. Gửi request vi phạm XSD; xác nhận service không xử lý side effect.
10. Chọn giữa XPath và JAXB nếu số item tăng lên hàng trăm và xuất hiện nhiều nhánh xs:choice.

**Tiêu chí hoàn thành:** Kết quả lấy dữ liệu không phụ thuộc prefix trong XML, không âm thầm bỏ qua namespace, phân biệt rõ trường hợp vắng mặt/nil và từ chối request sai hợp đồng theo đúng cấu hình.

## 17. Checklist khi dùng @XPathParam trong sản xuất

- [ ] `@Endpoint` được component scan và annotation infrastructure đã kích hoạt.
- [ ] `@PayloadRoot` khớp QName của payload root trong XSD/WSDL.
- [ ] XPath được viết từ **payload**, không mặc định từ SOAP Envelope.
- [ ] Mọi prefix dùng trong XPath đều được khai báo bằng `@Namespace` hoặc `@Namespaces`.
- [ ] Đã kiểm tra annotation ở method/class/package và trường hợp override prefix.
- [ ] XML default namespace được xử lý bằng prefix trong XPath.
- [ ] Attribute có/không namespace được chọn đúng theo XSD.
- [ ] Kiểu `@XPathParam` có hỗ trợ trực tiếp hoặc qua ConversionService.
- [ ] Không dùng `boolean(node-set)` khi muốn đọc giá trị xs:boolean.
- [ ] Không dùng `double` cho tiền tệ cần độ chính xác thập phân.
- [ ] Có xử lý rõ ràng missing/empty/nil và danh sách nhiều node.
- [ ] `PayloadValidatingInterceptor`/schema validation và domain validation được áp dụng đúng.
- [ ] Biểu thức XPath tĩnh hoặc có cơ chế tránh injection khi thực sự cần XPath động.
- [ ] XML parser và SOAP stack được cấu hình bảo mật, giới hạn tài nguyên.
- [ ] Có test đổi prefix, default namespace, sai namespace, sai QName và negative XSD.
- [ ] Có integration test SOAP/HTTP và interoperability test với client độc lập khi cần.

## 18. Ghi nhớ

- **`@XPathParam`** đưa kết quả XPath vào tham số endpoint; nó không phải cơ chế định tuyến endpoint hay trình xác thực XSD.
- **`@PayloadRoot`** chọn endpoint theo QName payload; **`@Namespace`/`@Namespaces`** gắn prefix của XPath với namespace URI.
- **Prefix trong XML không cần trùng prefix trong Java XPath**. Quan trọng là URI namespace và local name.
- **Default namespace của XML không tự áp dụng cho tên unprefixed trong XPath 1.0**; dùng prefix khai báo tường minh.
- **Attribute không có prefix thường không thuộc default namespace**, khác với element.
- **XPath boolean, string và node-set có semantics riêng**; đặc biệt cần cẩn thận khi node vắng mặt, rỗng, nil hoặc lặp lại.
- **XPath thích hợp cho việc trích một vài trường đơn giản**; với payload phức tạp nên cân nhắc JAXB/OXM hoặc cách xử lý XML thích hợp.
- **Contract-first và security không phụ thuộc cách trích dữ liệu**: vẫn cần XSD validation, SOAP Fault, kiểm tra quyền và WS-Security khi hợp đồng yêu cầu.

### Tài liệu tham khảo chính thức

- [Spring-WS Reference — `@XPathParam`](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/)
- [Spring-WS API — `XPathParam`](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/server/endpoint/annotation/XPathParam.html)
- [Spring-WS API — `Namespace`](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/server/endpoint/annotation/Namespace.html)
- [Spring-WS API — `Namespaces`](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/server/endpoint/annotation/Namespaces.html)

**Câu hỏi tự kiểm tra:** Một SOAP client gửi `GetOrderRequest` dưới dạng default namespace `xmlns="urn:example:orders:v1"` và có `orderId` hợp lệ. Endpoint dùng `@PayloadRoot(namespace="urn:example:orders:v1", localPart="GetOrderRequest")` nhưng `@XPathParam("/GetOrderRequest/orderId")` trả giá trị rỗng. Vì sao request vẫn được định tuyến đúng nhưng XPath không tìm thấy dữ liệu? Hãy sửa annotation, phân biệt thêm trường hợp `@correlationId` và nêu một test bảo đảm cách sửa không phụ thuộc prefix trong XML.

