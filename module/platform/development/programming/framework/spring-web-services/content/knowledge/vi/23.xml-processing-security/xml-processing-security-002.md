# DTD, external entity và điều kiện dẫn đến XXE

## 1. Vì sao SOAP client/server cần quan tâm đến XXE?

Trong module **SPRING_WEB_SERVICES**, ta phát triển SOAP service theo hướng **contract-first** với XSD/WSDL, ánh xạ JAXB, xây dựng Spring-WS `@Endpoint` và `WebServiceTemplate`, thêm SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích. XML là định dạng trung tâm của SOAP, vì vậy **cách XML được phân tích** là ranh giới bảo mật quan trọng không kém logic nghiệp vụ.

Một SOAP message có thể đi qua nhiều bộ xử lý XML:

- SOAP message factory đọc Envelope, Header và Body.
- Spring-WS định tuyến endpoint dựa trên payload QName hoặc action.
- JAXB/OXM unmarshal/marshal các Java objects.
- DOM/SAX/StAX/Transformer phục vụ xử lý XML trực tiếp.
- XSD validator đọc payload và biên dịch schema imports/includes.
- Các thành phần WSDL/XSD generation và SOAP client đọc tài liệu contract.
- WS-Security sử dụng XML Signature/Encryption và xử lý những XML nodes liên quan.

Nếu parser nhận dữ liệu từ phía ngoài mà **cho phép DTD và phân giải external entities** không kiểm soát, một XML document có thể khiến ứng dụng mở tệp cục bộ, truy cập mạng hoặc tiêu thụ quá nhiều tài nguyên. Lớp tấn công này gọi là **XML External Entity injection (XXE)**. Một biến thể gây gián đoạn khác là **entity expansion/resource exhaustion**, có thể xảy ra ngay cả khi entity không trỏ đến tài nguyên bên ngoài.

Bài thuộc chương **Bảo vệ xử lý XML**, tập trung vào chủ đề **“DTD, external entity và điều kiện dẫn đến XXE”**. Đây là bài về **nguyên nhân, bề mặt tấn công, phòng vệ và kiểm chứng**, không phải hướng dẫn sử dụng XXE để lấy dữ liệu của hệ thống khác.

### Sau bài học, bạn có thể

1. Giải thích vai trò của `DOCTYPE`, DTD internal/external subset và XML entity.
2. Phân biệt entity nội bộ, external entity, parameter entity, character reference và predefined entity.
3. Nêu đủ những điều kiện để XML không đáng tin gây XXE, SSRF, rò rỉ file hoặc denial of service.
4. Phân biệt **DTD parsing**, **schema validation**, **XInclude**, **XSLT** và **WS-Security**.
5. Cấu hình JAXP DOM, SAX, StAX, TransformerFactory và SchemaFactory theo hướng chặn external access.
6. Hiểu vì sao cấu hình một `Jaxb2Marshaller` không nhất thiết bảo vệ toàn SOAP ingress.
7. Thiết kế policy fail-closed, local XML catalog và schema resolver khi cần DTD/XSD dependencies.
8. Viết negative tests cho SOAP endpoint, SOAP client, WSDL/XSD load và các đường XML trực tiếp.
9. Quan sát parser violations an toàn, không để thông tin nhạy cảm xuất hiện trong SOAP Fault hoặc log.

## 2. XML document và DTD gồm những thành phần gì?

XML cho phép phần khai báo `DOCTYPE` để liên kết tài liệu với **Document Type Definition (DTD)**. DTD có thể mô tả element types, attributes, entities và một số ràng buộc cấu trúc.

Một ví dụ độc lập không cần tài nguyên bên ngoài:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE greeting [
    <!ELEMENT greeting (#PCDATA)>
    <!ENTITY company "Example Company">
]>
<greeting>Hello, &company;!</greeting>
~~~

Nếu parser hỗ trợ DTD và entity replacement, giá trị văn bản sau expansion có thể tương đương:

~~~xml
<greeting>Hello, Example Company!</greeting>
~~~

Điểm cần hiểu: entity là một **cơ chế thay thế trong quá trình XML processing**, không phải business field mà XSD của ứng dụng chủ động định nghĩa. Việc thay thế có thể diễn ra **trước** khi code Java nhận được DOM, JAXB object hay payload validation result.

### 2.1. DOCTYPE và root element

`DOCTYPE` là declaration ở **prolog của XML document**, trước document element:

~~~xml
<?xml version="1.0"?>
<!DOCTYPE GetOrderRequest [
    <!ENTITY reference "ORD-2048">
]>
<GetOrderRequest>&reference;</GetOrderRequest>
~~~

Nó **không** phải một thẻ con được đặt tùy ý bên trong `soap:Body`. Khi phân tích một SOAP Envelope như một XML document, `DOCTYPE` (nếu được phép) nằm ở trước phần tử `Envelope`.

Nếu một hệ thống tách riêng XML payload thành document mới rồi parse lại, payload đó có thể có prolog/DOCTYPE của riêng nó tùy cách wrapper xây dựng dữ liệu. Vì vậy phải bảo vệ **mọi parser nhận XML từ nguồn không tin cậy**, không chỉ lớp đọc SOAP Envelope đầu tiên.

### 2.2. Internal subset

Phần DTD nằm trong ngoặc vuông:

~~~xml
<!DOCTYPE order [
    <!ENTITY region "VN">
]>
~~~

được gọi là **internal subset**. Nó không yêu cầu tải một tệp DTD khác để định nghĩa `region`, nhưng vẫn có thể chứa các khai báo dẫn tới external entity hoặc tạo chuỗi expansions tiêu thụ tài nguyên.

### 2.3. External subset

XML cũng có thể trỏ đến một DTD bên ngoài bằng system identifier:

~~~xml
<!DOCTYPE order SYSTEM "https://schemas.example.test/order.dtd">
<order>...</order>
~~~

Ở parser có external DTD loading được bật, việc đọc DTD có thể tạo request mạng. Nếu nguồn XML do client không đáng tin cung cấp, **không nên để client quyết định máy chủ nào được parser truy cập**.

External subset có thể dùng trong một số XML standards/legacy contracts hợp lệ. Vì thế câu trả lời phòng vệ là **đánh giá xem DTD có cần thiết không**; nếu không cần, cấm DOCTYPE hoàn toàn. Nếu cần, chỉ cho phân giải qua nguồn tài nguyên được cấp phép và kiểm soát.

### 2.4. SYSTEM và PUBLIC

Ngoài `SYSTEM`, DTD có thể sử dụng `PUBLIC` với public identifier và system identifier:

~~~xml
<!DOCTYPE order
    PUBLIC "-//EXAMPLE//DTD Orders 1.0//EN"
           "https://schemas.example.test/order.dtd">
~~~

Public identifier **không làm tài nguyên trở nên đáng tin**. XML processor/entity resolver phải quản lý nơi thực sự lấy nội dung. Một XML catalog cục bộ có thể ánh xạ các identifiers được phép đến tài liệu đã kiểm soát thay vì tải URL từ internet.

## 3. Entity có những loại nào?

Entity là tên được tham chiếu trong XML. Không phải loại entity nào cũng nguy hiểm như nhau.

| Loại | Ví dụ | Rủi ro/ghi chú |
|---|---|---|
| Predefined entity | `&amp;`, `&lt;` | Có sẵn theo XML; không cần DTD bên ngoài |
| Numeric character reference | `&#65;`, `&#x41;` | Biểu diễn ký tự theo mã điểm; không phải external entity |
| Internal general entity | `<!ENTITY x "abc">`, dùng `&x;` | Có thể nhân bản nội dung gây resource exhaustion |
| External general entity | `<!ENTITY x SYSTEM "...">` | Có thể khiến parser đọc file/URL nếu được phép |
| Internal parameter entity | `<!ENTITY % p "...">`, dùng `%p;` trong DTD | Thay thế trong DTD, có thể khiến declarations phức tạp |
| External parameter entity | `<!ENTITY % p SYSTEM "...">` | Có thể dẫn tới việc parser tải tài nguyên ngoài khi xử lý DTD |
| External DTD subset | `<!DOCTYPE r SYSTEM "...">` | Có thể tải tài liệu DTD từ ngoài |
| Unparsed external entity | Khai báo có `NDATA` | Cơ chế khác với parsed entity; vẫn cần đánh giá URI/access |

### 3.1. Predefined entities không phải lý do phải bật DTD

XML sử dụng các entity định nghĩa sẵn như:

~~~xml
<note>Tom &amp; Jerry</note>
<comparison>2 &lt; 3</comparison>
~~~

Một parser chặn DOCTYPE vẫn đọc các predefined entities và numeric character references theo XML specification. Không nên bật DTD chỉ vì SOAP payload có dấu `&amp;` hoặc `&lt;`.

### 3.2. General entity và parameter entity khác nhau

- **General entity** được tham chiếu trong nội dung XML bằng cú pháp `&name;`.
- **Parameter entity** được tham chiếu trong DTD bằng cú pháp `%name;`.

Một số cấu hình phòng thủ chặn external general entities nhưng quên external parameter entities, hoặc tắt việc đọc external DTD nhưng vẫn cho DTD internal subset khai báo entities phức tạp. Vì vậy nếu không cần DTD, **chặn hẳn DOCTYPE** là một chiến lược đơn giản và rõ ràng hơn việc chỉ tắt một tập con.

### 3.3. Không phải mọi dấu & là một entity hợp lệ

Một dấu `&` trong XML text phải được escape nếu nó không mở entity reference hợp lệ:

~~~xml
<!-- XML đúng -->
<name>R&amp;D</name>
~~~

Không cố “sửa” dữ liệu XML không hợp lệ bằng cách bật external entity resolution. XML escaping là trách nhiệm serialization; DTD và schema validation là các tầng khác.

## 4. XXE là gì và phát sinh tại đâu?

**XML External Entity injection (XXE)** là trường hợp một XML processor phân giải entity hoặc DTD reference bên ngoài theo nội dung mà attacker có thể ảnh hưởng, từ đó thực hiện hành vi ngoài ý muốn ở phía ứng dụng.

Các tác động có thể gồm:

- Đọc tài nguyên cục bộ mà process có quyền truy cập.
- Truy vấn HTTP hoặc các schemes khác theo khả năng XML resolver.
- Truy cập tài nguyên nội bộ qua network (một dạng server-side request forgery).
- Lộ thông tin qua response/log/error nếu nội dung hoặc kết quả được xuất ra.
- Từ chối dịch vụ do entity expansion, remote DTD loading, xử lý kích thước lớn hoặc các biến thể parser workload.

Không phải mọi XML có `DOCTYPE` đều là XXE. Nhưng một parser **cho phép DOCTYPE và external resolution từ input không đáng tin** có thể tạo ra bề mặt tấn công.

### 4.1. Ví dụ minh họa chỉ dùng một tệp thử nghiệm vô hại

Đây là fixture để hiểu rủi ro, **không dùng trên máy chủ không thuộc quyền kiểm thử**. Tệp `/tmp/xxe-demo-only.txt` chỉ là tài liệu giả định chứa chuỗi thử nghiệm công khai:

~~~xml
<?xml version="1.0"?>
<!DOCTYPE order [
    <!ENTITY externalLabel
        SYSTEM "file:///tmp/xxe-demo-only.txt">
]>
<order>&externalLabel;</order>
~~~

Nếu parser được cấu hình cho phép đọc external file entity, giá trị `&externalLabel;` có thể bị thay bằng dữ liệu từ tệp. Nếu tệp không tồn tại, parser có thể báo lỗi I/O; **việc parser cố đọc tệp đã là tín hiệu boundary thất bại** trong hệ thống không cho phép external entity.

Trong production, không thử bằng các tệp chứa secret thật. Một negative test nên kiểm tra parser **từ chối DOCTYPE ngay**, hoặc chặn external access, thay vì cố chứng minh đọc được một bí mật.

### 4.2. XML well-formed không đồng nghĩa an toàn

Một tài liệu chứa DTD external entity có thể đúng cú pháp XML. Việc parse thành công hoặc JAXB unmarshal ra Java object không có nghĩa XML đó an toàn.

Ngược lại, XSD validation có thể báo `orderId` sai pattern **sau khi** parser đã cố đọc external entity. Vì vậy chỉ dựa vào XSD validator để “bảo vệ XXE” là sai thứ tự trách nhiệm.

### 4.3. XXE là lớp lỗi của parser/resolver, không phải SOAP operation

SOAP service có thể chỉ expose `GetOrderRequest` và `GetOrderResponse` nhưng vẫn gặp XXE nếu XML parser bên dưới resolve external entities. Lỗ hổng không nhất thiết nằm trong `getOrder(...)`; nó có thể ở tầng message factory, DTO converter, XSLT transformer hoặc nơi đọc một XML document phụ.

## 5. Điều kiện cần để XXE thực sự xảy ra

Một mô hình phân tích tối thiểu:

~~~mermaid
flowchart TD
    A["XML input từ nguồn có thể bị điều khiển"] --> B{"Parser nhận DTD/entity declarations?"}
    B -->|"Không"| X["Chặn nhánh XXE qua DTD"]
    B -->|"Có"| C{"External entity / subset resolution được phép?"}
    C -->|"Không"| Y["External reference không được thực thi"]
    C -->|"Có"| D{"Resolver/transport truy cập đích?"}
    D -->|"Không"| Z["Bị chặn bởi resolver, permissions hoặc network"]
    D -->|"Có"| E["Parser đọc tài nguyên ngoài"]
    E --> F{"Nội dung hay side effect có thể gây hại?"}
    F -->|"Có"| G["XXE impact: file, network hoặc resource abuse"]
    F -->|"Không"| H["Vẫn là bề mặt cần kiểm soát"]
~~~

Cần phân biệt **bề mặt bị mở** và **tác động thực tế**:

1. XML có nguồn không tin cậy hoặc bị attacker tác động được.
2. Nó đi tới XML processor xử lý DTD/external references.
3. XML processor và entity resolver được phép truy xuất loại tài nguyên được chỉ định.
4. Process có quyền đọc file/network tương ứng.
5. Có một hậu quả quan sát được: truy cập mạng, nội dung bị đưa vào XML, exception/log, tài nguyên bị tiêu thụ...

Thiếu một điều kiện có thể ngăn một kiểu XXE, nhưng không nên coi firewall hoặc file permission **là biện pháp duy nhất**. Defense-in-depth gồm parser policy, runtime permission, network egress control, validation và tests.

### 5.1. Không cần thấy bí mật trong SOAP response mới có XXE

Một parser có thể cố gửi request tới một endpoint nội bộ, hoặc tạo traffic không mong muốn, dù ứng dụng không bao giờ echo nội dung entity ra SOAP Body. Vì vậy negative test nên quan sát **parser rejection và network access** (qua fake resolver/server được phép), không chỉ kiểm tra response không chứa dữ liệu bí mật.

### 5.2. Internal entity expansion không cần external network

Một XML document có thể khai báo các entities nội bộ lồng nhau:

~~~xml
<!DOCTYPE sample [
    <!ENTITY a "x">
    <!ENTITY b "&a;&a;">
    <!ENTITY c "&b;&b;">
]>
<sample>&c;</sample>
~~~

Ví dụ nhỏ này có chủ đích vô hại. Khi quy mô declarations và số lần tham chiếu tăng, entity expansion có thể tiêu thụ CPU và memory. Vì vậy chặn external network **không tự ngăn** mọi entity-based denial of service; nếu không cần DTD, chặn DOCTYPE là cách giảm bề mặt rõ nhất.

### 5.3. “Billion Laughs” và quadratic blowup là lớp resource exhaustion

Tên gọi “Billion Laughs” thường dùng cho entity expansion theo cấp số nhân; quadratic blowup dùng nội dung được lặp lại rất nhiều lần. Không cần tái tạo payload cực lớn để hiểu cơ chế: một đoạn XML ngắn có thể khiến parser tạo ra lượng text/DOM nodes lớn hơn nhiều.

Biện pháp bảo vệ cần gồm:

- Không nhận DTD khi business contract không yêu cầu.
- XML parser resource limits/secure processing.
- Giới hạn request body và thời gian xử lý.
- Hạn chế memory và concurrency ở service boundary.
- Kiểm thử bằng fixture nhỏ, có kiểm soát, không dùng payload gây cạn tài nguyên môi trường chung.

## 6. External entity có thể chạm đến những nguồn nào?

Phụ thuộc XML parser/provider, resource resolver, runtime permissions và network:

| Tài nguyên | Bề mặt rủi ro | Ví dụ chính sách |
|---|---|---|
| Local file scheme | Đọc file ứng dụng có quyền truy cập | Cấm `file:` đối với XML không tin cậy |
| HTTP/HTTPS URL | SSRF, tải DTD từ mạng không kiểm soát | Cấm external fetch; dùng resource local |
| File shares hoặc schemes đặc thù | Truy cập tài nguyên ngoài ý muốn | Whitelist protocols tuyệt đối nếu cần |
| Remote DTD/XSD | Supply-chain/reproducibility, network outage | Pin/copy dependencies vào classpath |
| Large expansion | CPU/RAM và queue pressure | DTD off, resource limits |
| XInclude, XSLT imports | XML transformation/include riêng | Cấu hình riêng; không chỉ chặn entity |

### 6.1. Parser authority là quyền của process, không phải của SOAP caller

Một attacker có thể không có quyền đọc file của container, nhưng nếu dịch vụ SOAP chạy dưới identity có quyền, parser có thể đọc file **nhân danh process của dịch vụ**. Đây là lý do XXE là một dạng confused-deputy: input người ngoài kích hoạt quyền mạnh hơn của server.

### 6.2. XML network access có thể vượt qua kiểm soát HTTP client thông thường

Một application có thể cấu hình `WebServiceTemplate` chỉ gọi allowlisted partner URLs. Nhưng một XML parser riêng, được phép tải external DTD, có thể tạo network access **ngoài đường đi của WebServiceMessageSender**. Bảo vệ chỉ ở HTTP client không thay parser hardening.

### 6.3. Không dựa chỉ vào container network policy

Egress allowlist, no-internet container hoặc filesystem permissions là defense-in-depth tốt. Nhưng policy hạ tầng có thể thay đổi, tests chạy ở máy phát triển có mạng khác, hoặc parser tiếp cận file local dù không có network. **Không bỏ các cờ chống XXE chỉ vì hiện tại container bị chặn outbound internet.**

## 7. Bề mặt XXE trong Spring-WS contract-first

Một service SOAP có các điểm XML ingress/processing như sau:

~~~mermaid
flowchart TD
    A["SOAP request không tin cậy"] --> B["HTTP / MessageDispatcherServlet"]
    B --> C["SOAP message factory parse Envelope"]
    C --> D["SOAP Header/security processing"]
    D --> E["Payload XML Source"]
    E --> F["JAXB / DOM / SAX / StAX"]
    F --> G["XSD validation và endpoint"]
    G --> H["Domain logic"]
    I["WSDL / XSD / XML từ đối tác"] --> J["Contract parser/schema compiler"]
    K["SOAP response từ đối tác"] --> L["Client SOAP message factory"]
    L --> F
    J --> G
~~~

Những điểm quan trọng:

- **SOAP Envelope parser** có thể đã xử lý DTD trước khi Spring-WS chọn endpoint.
- Một endpoint nhận `@RequestPayload Element` rồi tự tạo `DocumentBuilderFactory` có thể parse **lần thứ hai** từ XML string.
- `Jaxb2Marshaller` có thể được gọi trên `Source` do framework hoặc ứng dụng tạo; nguồn đó có thể đến từ parser khác.
- `SchemaFactory` có thể tải external schema qua `xs:import`/`xs:include` nếu cho phép.
- Một SOAP client đọc XML response không đáng tin cậy từ partner cũng cần hardening; client không được miễn bảo mật parser.
- WS-Security signature validation không thay việc ngăn DTD/entity loading ở tầng parser.

### 7.1. Bảo vệ ở điểm sớm nhất nhận XML

Nếu một `EndpointInterceptor` kiểm tra text `<!DOCTYPE` sau khi SOAP message factory đã parse XML, nó có thể **quá muộn**: external entity đã được xử lý. Cấu hình kiểm soát XXE phải ở **XML processor trước khi side effect phát sinh**, hoặc tại một ranh giới nhận XML sớm hơn có thể từ chối dữ liệu đó.

### 7.2. Kiểm tra XSD là việc khác

Spring-WS `PayloadValidatingInterceptor` kiểm tra **business XML payload theo XSD**; nó không phải biện pháp cấu hình DTD/external entity resolution cho toàn bộ SOAP parser.

Một yêu cầu có thể sai XSD và đồng thời kích hoạt external read trước lúc validator thấy được các phần tử. Vì vậy cần:

~~~text
Secure parsing / external access policy
    -> SOAP interpretation / security
    -> XSD validation
    -> Domain authorization và nghiệp vụ
~~~

Thứ tự tuyệt đối của từng interceptor phụ thuộc stack, nhưng ranh giới security về mặt khái niệm phải được giải quyết trước khi tin vào XML data.

## 8. Một hợp đồng XSD có an toàn không khi vẫn cho XML DOCTYPE?

Giả sử XSD cho `GetOrderRequest`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:ord="urn:example:orders:v1"
    targetNamespace="urn:example:orders:v1"
    elementFormDefault="qualified">

    <xs:simpleType name="OrderIdType">
        <xs:restriction base="xs:string">
            <xs:pattern value="ORD-[0-9]+"/>
        </xs:restriction>
    </xs:simpleType>

    <xs:element name="GetOrderRequest">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="orderId"
                            type="ord:OrderIdType"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
~~~

Một SOAP document là XML hoàn chỉnh:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
    <soap:Body>
        <ord:GetOrderRequest>
            <ord:orderId>ORD-2048</ord:orderId>
        </ord:GetOrderRequest>
    </soap:Body>
</soap:Envelope>
~~~

XSD validator kiểm tra root business payload `GetOrderRequest`, namespace và pattern. Việc **từ chối `DOCTYPE`** là quyết định bảo mật XML parser/SOAP stack, không phải kết quả mặc định của `xs:pattern`.

### 8.1. DTD không bắt buộc để dùng XSD

XSD validation có thể được thực hiện trên XML không có DOCTYPE. Một service contract-first hiện đại thường có thể:

- Không cho phép DTD trong SOAP input.
- Đóng gói XSD đáng tin trong application resources.
- Không tải schemaLocation từ XML document do client tự cung cấp.
- Sử dụng schema đã biên dịch/resolver cục bộ.
- Kiểm tra element QNames và facets theo XSD.

Đó là thiết kế đơn giản hơn so với “cho phép mọi DTD rồi cố validate để lọc”.

### 8.2. xsi:schemaLocation không phải lời mời tự tải từ Internet

XML có thể chứa:

~~~xml
<ord:GetOrderRequest
    xmlns:ord="urn:example:orders:v1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        urn:example:orders:v1
        https://untrusted.example.test/orders.xsd">
    <ord:orderId>ORD-2048</ord:orderId>
</ord:GetOrderRequest>
~~~

Trong một SOAP server contract-first, **không nên tự tin dùng URL `xsi:schemaLocation` từ request như nguồn schema để kiểm tra hợp lệ**. Validator nên được cấu hình theo XSD version mà service công bố/trust từ trước, để client không điều khiển nguồn schema hoặc quy tắc validation.

Đây là vấn đề **external schema loading**, có họ hàng với XML parser external access nhưng khác cơ chế DTD entity. Cần cấu hình `SchemaFactory` và `Validator` tương ứng.

## 9. Phòng thủ ưu tiên: không cho DTD nếu không cần

Trong dịch vụ SOAP/XSD hiện đại, một lựa chọn mạnh là **reject mọi XML document chứa DOCTYPE** ở parser nhận nguồn không tin cậy.

Ưu điểm:

- Ngăn các general/parameter entities do DTD khai báo.
- Ngăn việc tải external DTD subset.
- Giảm các kiểu entity expansion attacks từ DTD.
- Chính sách dễ hiểu: “SOAP input không có DTD”.
- Negative tests có thể assert parser reject ngay, trước domain service.

Nhưng cần nhớ:

- Những cấu hình parser có thể dùng tên feature/property **đặc thù implementation**.
- Nếu một feature bảo mật không được parser hỗ trợ, **không được lặng lẽ tiếp tục với parser thiếu bảo vệ**.
- Vẫn cần giới hạn XML body size, entity-independent XML depth, timeouts và concurrency.
- XInclude, XSLT và external schema loading cần các cấu hình riêng khi được sử dụng.

### 9.1. Fail-closed khi feature không được hỗ trợ

Một đoạn cấu hình kiểu này **không an toàn** nếu chỉ log warning rồi tiếp tục:

~~~java
try {
    factory.setFeature(
        "http://apache.org/xml/features/disallow-doctype-decl",
        true
    );
} catch (ParserConfigurationException unsupported) {
    log.warn("Không bật được XXE protection", unsupported);

    // Nguy hiểm: ứng dụng vẫn tiếp tục nhận XML không tin cậy.
}
~~~

Nếu policy của hệ thống yêu cầu cấm DOCTYPE, hãy fail startup hoặc từ chối đường xử lý cần parser đó khi không thể chứng minh bảo vệ được áp dụng.

### 9.2. Không dựa vào chuỗi tìm kiếm raw "<!DOCTYPE"

Một số hệ thống cố chặn XXE bằng cách:

~~~java
if (xmlString.contains("<!DOCTYPE")) {
    reject();
}
~~~

Đây **không** phải biện pháp bảo mật đủ tin cậy: XML encoding, parser behavior, input splitting, và nhiều parser entrypoints có thể khiến kiểm tra raw string không tương đương parse policy. Hãy cấu hình **XML processor** đúng cách và kiểm thử để không cho DTD được giải nghĩa.

## 10. Secure XML processing là defense-in-depth

Nhiều lớp bảo vệ kết hợp:

| Lớp | Chính sách gợi ý |
|---|---|
| XML parser | Cấm DOCTYPE nếu không cần; chặn general/parameter external entities |
| JAXP external access | `ACCESS_EXTERNAL_DTD=""` và `ACCESS_EXTERNAL_SCHEMA=""` nơi áp dụng |
| Schema compiler | Chỉ compile trusted XSD và resolve imports/includes nội bộ |
| XSLT/Transformer | Chặn external DTD/stylesheet và URIResolver tùy nhu cầu |
| Filesystem | Process quyền tối thiểu, không cho đọc secrets không cần |
| Network | Egress allowlist, chặn metadata/internal services |
| HTTP ingress | Request size limits, timeouts, content-type policy |
| Resource limits | XML nesting/attribute/element limits, CPU/memory constraints |
| SOAP framework | Đánh giá message factory và các XML parsing entrypoints |
| WS-Security | Chữ ký, timestamp, trust và authorization theo policy |
| Tests | DTD negative fixtures, network observations, parser reuse và upgrade regression |

**Không một checkbox duy nhất bảo vệ toàn bộ XML pipeline.** Ví dụ chặn external entities trong `DocumentBuilderFactory` không kiểm soát một `TransformerFactory` khác đang tải stylesheet từ URL, và WS-Security không tự chặn external schemaLocation.

## 11. Cấu hình DOM DocumentBuilderFactory chống XXE

Nếu ứng dụng tự đọc XML từ SOAP attachment, file import hoặc string của đối tác để tạo DOM, hãy cấu hình `DocumentBuilderFactory` **trước khi parse**.

Một helper theo chính sách **không chấp nhận DOCTYPE**:

~~~java
package com.example.soap.xml;

import java.io.InputStream;

import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;

import org.w3c.dom.Document;
import org.xml.sax.SAXException;

public final class SecureXml {

    private SecureXml() {}

    public static Document parse(InputStream xml)
            throws Exception {

        DocumentBuilderFactory factory =
            DocumentBuilderFactory.newInstance();

        // Rất quan trọng với SOAP QName/namespace.
        factory.setNamespaceAware(true);

        // Hạn chế chi phí của XML processing.
        factory.setFeature(
            XMLConstants.FEATURE_SECURE_PROCESSING,
            true
        );

        // Chính sách chính: từ chối mọi DOCTYPE.
        factory.setFeature(
            "http://apache.org/xml/features/disallow-doctype-decl",
            true
        );

        // Defense-in-depth cho provider có hỗ trợ features.
        factory.setFeature(
            "http://xml.org/sax/features/external-general-entities",
            false
        );
        factory.setFeature(
            "http://xml.org/sax/features/external-parameter-entities",
            false
        );
        factory.setFeature(
            "http://apache.org/xml/features/nonvalidating/load-external-dtd",
            false
        );

        // Không bật XInclude hoặc tự mở rộng entity refs.
        factory.setXIncludeAware(false);
        factory.setExpandEntityReferences(false);

        // Chặn truy cập tài nguyên ngoài qua JAXP.
        factory.setAttribute(
            XMLConstants.ACCESS_EXTERNAL_DTD, ""
        );
        factory.setAttribute(
            XMLConstants.ACCESS_EXTERNAL_SCHEMA, ""
        );

        DocumentBuilder builder = factory.newDocumentBuilder();

        // Nếu provider cố resolve, từ chối ngay.
        builder.setEntityResolver((publicId, systemId) -> {
            throw new SAXException(
                "External XML entity is forbidden"
            );
        });

        // Truyền InputStream do caller kiểm soát vòng đời.
        return builder.parse(xml);
    }
}
~~~

Đoạn code minh họa sử dụng Java/JAXP provider hỗ trợ các features/attributes trên. Các URI `http://apache.org/xml/features/...` là **provider-specific features**, không phải những phương thức bắt buộc của mọi XML parser. Nếu parser không hỗ trợ chính sách cấm DTD, lời gọi `setFeature(...)` có thể ném exception; ví dụ trên **để exception lan ra**, không âm thầm tiếp tục với cấu hình yếu hơn.

Trong ứng dụng thật, nên dùng typed exceptions, logging an toàn và kiểm tra parser provider tại startup. `DocumentBuilder` và các cấu trúc DOM mutable **không nên chia sẻ đồng thời giữa threads**.

### 11.1. Vì sao cấu hình nhiều cờ?

| Cờ | Mục đích |
|---|---|
| `disallow-doctype-decl=true` | Chặn DOCTYPE nói chung, kể cả internal subset |
| `external-general-entities=false` | Không phân giải external general entities |
| `external-parameter-entities=false` | Không phân giải external parameter entities |
| `load-external-dtd=false` | Không tải external DTD từ non-validating parser |
| `ACCESS_EXTERNAL_DTD=""` | Không cho phép các protocols ngoài đối với DTD/entity access ở JAXP layer |
| `ACCESS_EXTERNAL_SCHEMA=""` | Hạn chế external schema access trong các đường xử lý liên quan |
| `setXIncludeAware(false)` | Không bật XInclude processing |
| `FEATURE_SECURE_PROCESSING=true` | Bật giới hạn bảo vệ của XML processor, không thay thế các cờ khác |
| `setExpandEntityReferences(false)` | Hạn chế expansion behavior của DOM, **không đủ để chống XXE nếu đứng một mình** |

Một số flags có ý nghĩa phòng vệ trùng lặp khi `DOCTYPE` đã bị từ chối. Việc đặt nhiều lớp nhằm giảm rủi ro khi provider có những đường xử lý khác nhau và giúp policy rõ ràng; nhưng cần **test trên parser thực tế**.

### 11.2. Không bắt UnsupportedOperationException rồi bỏ qua

`setXIncludeAware(false)` có thể không được provider hỗ trợ. Nếu yêu cầu chắc chắn XInclude bị tắt mà provider không thể xác minh, phải chọn provider khác hoặc từ chối xử lý. Không viết:

~~~java
try {
    factory.setXIncludeAware(false);
} catch (UnsupportedOperationException ignore) {
    // Sai: tiếp tục mà không biết provider có xử lý XInclude hay không.
}
~~~

Nếu tổ chức đã chứng minh một parser không hỗ trợ XInclude trong mọi trường hợp, chính sách có thể được tài liệu hóa qua tests. Nhưng bỏ qua lỗi cấu hình mà không xác minh là lựa chọn yếu.

### 11.3. Vì sao setExpandEntityReferences(false) không đủ?

Một số implementation có thể vẫn truy cập hoặc phân giải external entity trước khi DOM builder quyết định có chèn replacement node hay không. Chỉ tắt entity reference expansion không bảo đảm **không có I/O**; cần chặn DOCTYPE và external resolution từ parser.

### 11.4. Nên giới hạn kích thước trước khi parse

Ngay cả XML không có DTD cũng có thể có hàng triệu element hoặc text cực dài. Hạn chế HTTP request body size, attachment size và định dạng XML được chấp nhận **trước khi tạo DOM**. Việc xây DOM có chi phí memory theo toàn bộ document.

## 12. SAX và XMLReader: chặn external resolution ở parser streaming

SAX xử lý XML theo các callbacks sự kiện, nhưng nó cũng có thể chịu rủi ro DTD/external entity nếu không được cấu hình.

Một ví dụ:

~~~java
import java.io.InputStream;

import javax.xml.XMLConstants;
import javax.xml.parsers.SAXParser;
import javax.xml.parsers.SAXParserFactory;

import org.xml.sax.InputSource;
import org.xml.sax.XMLReader;
import org.xml.sax.helpers.DefaultHandler;
import org.xml.sax.SAXException;

public final class SecureSaxReader {

    public static void parse(
            InputStream input,
            DefaultHandler handler) throws Exception {

        SAXParserFactory factory = SAXParserFactory.newInstance();

        factory.setNamespaceAware(true);
        factory.setFeature(
            XMLConstants.FEATURE_SECURE_PROCESSING,
            true
        );

        factory.setFeature(
            "http://apache.org/xml/features/disallow-doctype-decl",
            true
        );
        factory.setFeature(
            "http://xml.org/sax/features/external-general-entities",
            false
        );
        factory.setFeature(
            "http://xml.org/sax/features/external-parameter-entities",
            false
        );

        factory.setXIncludeAware(false);

        SAXParser parser = factory.newSAXParser();
        XMLReader reader = parser.getXMLReader();

        reader.setFeature(
            "http://apache.org/xml/features/nonvalidating/load-external-dtd",
            false
        );

        reader.setProperty(
            XMLConstants.ACCESS_EXTERNAL_DTD, ""
        );
        reader.setProperty(
            XMLConstants.ACCESS_EXTERNAL_SCHEMA, ""
        );

        reader.setEntityResolver((publicId, systemId) -> {
            throw new SAXException(
                "External entity is forbidden"
            );
        });

        reader.setContentHandler(handler);
        reader.parse(new InputSource(input));
    }
}
~~~

Các SAX/JAXP feature/property có khả năng không được hỗ trợ trên một provider; **fail closed** khi yêu cầu security bắt buộc không áp dụng được. `DefaultHandler` trong ví dụ xử lý events của ứng dụng, còn parser phải reject DTD trước khi handler nhận dữ liệu đã bị mở rộng.

### 12.1. SAX streaming không tự chống XXE

SAX đọc XML theo stream và thường dùng ít memory hơn DOM, nhưng không có nghĩa nó bỏ qua DTD. Cấu hình parser là yếu tố quyết định, không phải việc API có tên `SAX` hay `DOM`.

### 12.2. EntityResolver không thay thế cấm DOCTYPE

Nếu ứng dụng cần DTD legacy, `EntityResolver` hoặc `EntityResolver2` có thể định tuyến identifiers đến tài liệu local đáng tin. Nhưng nếu DTD không cần, reject toàn bộ DOCTYPE đơn giản hơn.

Một resolver chỉ trả empty InputSource có thể làm document parse thành công nhưng semantics thay đổi âm thầm. Với security policy chặn external entities, **ném lỗi rõ ràng** thường dễ kiểm tra và quan sát hơn.

## 13. StAX XMLInputFactory và XMLStreamReader

StAX thường được dùng khi xử lý SOAP/XML streaming hoặc JAXB unmarshal từ `XMLStreamReader`. Nó có những cờ riêng:

~~~java
import java.io.InputStream;

import javax.xml.XMLConstants;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamReader;

public final class SecureStaxReader {

    public static void process(InputStream input)
            throws XMLStreamException {

        XMLInputFactory factory = XMLInputFactory.newFactory();

        factory.setProperty(
            XMLInputFactory.SUPPORT_DTD,
            Boolean.FALSE
        );

        factory.setProperty(
            XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES,
            Boolean.FALSE
        );

        factory.setProperty(
            XMLConstants.ACCESS_EXTERNAL_DTD,
            ""
        );

        factory.setXMLResolver(
            (publicId, systemId, baseUri, namespace) -> {
                throw new XMLStreamException(
                    "External XML resolution forbidden"
                );
            }
        );

        XMLStreamReader reader =
            factory.createXMLStreamReader(input);

        try {
            while (reader.hasNext()) {
                int event = reader.next();
                // Xử lý sự kiện XML được phép ở đây.
            }
        } finally {
            reader.close();
        }
    }
}
~~~

Trong Java, `XMLStreamReader.close()` đóng reader/resource nội bộ theo implementation, **không được giả định luôn đóng InputStream do caller truyền**. Caller nên quản lý input stream bằng `try-with-resources` hoặc cơ chế lifecycle của transport.

### 13.1. Những chi tiết version/provider cần kiểm tra

- `SUPPORT_DTD=false` có thể khiến DOCTYPE bị từ chối hoặc không được xử lý theo cách khác nhau giữa các StAX providers; cần negative test.
- `IS_SUPPORTING_EXTERNAL_ENTITIES=false` nhằm chặn resolution.
- `XMLConstants.ACCESS_EXTERNAL_DTD` có thể không được một số providers chấp nhận qua `setProperty`; khi đó phải đánh giá bảo vệ thay thế hoặc chọn provider phù hợp.
- XMLResolver chủ động chặn attempts ngoại lệ là một lớp bảo vệ.
- Các XML readers đã tạo **trước** khi factory được cấu hình không được tự thay đổi; thiết lập trước khi tạo reader.

### 13.2. StAX + JAXB Unmarshaller

Một phương án khi nhận XML từ nguồn trực tiếp là tạo stream reader an toàn trước, sau đó chuyển cho JAXB unmarshaller:

~~~java
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.bind.Unmarshaller;

import javax.xml.stream.XMLStreamReader;

// reader đã được tạo bởi XMLInputFactory có chính sách an toàn.
JAXBContext context = JAXBContext.newInstance(
    com.example.contract.orders.v1.ObjectFactory.class
);

Unmarshaller unmarshaller =
    context.createUnmarshaller();

Object result = unmarshaller.unmarshal(reader);
~~~

Mẫu này **không tự cấu hình reader**; caller phải bảo đảm `reader` được tạo từ factory an toàn như phần trên. Không đưa một `XMLStreamReader` do thư viện khác tạo vào JAXB rồi kết luận `JAXBContext` đã tự chặn DTD.

`JAXBContext` thường có thể được chia sẻ, còn `Unmarshaller` là đối tượng mutable và **không nên chia sẻ không đồng bộ giữa threads**.

## 14. JAXB và Jaxb2Marshaller trong Spring-WS

Với Spring OXM, `Jaxb2Marshaller` có các tùy chọn liên quan đến hỗ trợ DTD/external entities ở những phiên bản nhất định:

~~~java
import org.springframework.oxm.jaxb.Jaxb2Marshaller;

Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
marshaller.setContextPath(
    "com.example.contract.orders.v1"
);

// Chính sách: không cần DTD cho SOAP payload.
marshaller.setSupportDtd(false);
marshaller.setProcessExternalEntities(false);
~~~

Các setters có thể khác về khả năng hỗ trợ/default giữa những dòng Spring Framework/Spring-WS. **Đối chiếu API cụ thể của dependency** trước khi dùng. Nếu thiết lập không có hoặc không thể thực thi, phải chọn cách đưa vào nguồn XML được parse an toàn, hoặc dùng đường xử lý khác đã được chứng minh an toàn.

### 14.1. JAXB không tự nhận nhiệm vụ bảo vệ mọi XML input

Một JAXB unmarshaller có thể nhận:

- `StreamSource` hoặc `InputStream` chưa qua parser hardened.
- `SAXSource` có XMLReader do ứng dụng tạo.
- `DOMSource` đã được xây bằng DOM parser khác.
- `StAXSource`/`XMLStreamReader` do provider khác tạo.

Nếu một DOM document **đã** chứa dữ liệu external entity được mở rộng, việc truyền DOM đó cho marshaller/unmarshaller “an toàn” **không thể thu hồi file/network access đã xảy ra**.

Điều này đặc biệt quan trọng khi Spring-WS endpoint có custom adapter:

~~~java
@PayloadRoot(
    namespace = "urn:example:orders:v1",
    localPart = "GetOrderRequest"
)
@ResponsePayload
public GetOrderResponse handle(
        @RequestPayload GetOrderRequest request) {
    // XML đã đi qua SOAP parser/unmarshaller trước method này.
}
~~~

Bên trong method, kiểm tra business DTO hoặc XSD quá muộn để ngăn một external fetch đã được SOAP message factory thực hiện. Cần đánh giá security **ở ingress parser stack**.

### 14.2. XSD validation của JAXB khác XXE protection

`marshaller.setSchema(...)` giúp kiểm tra XML có tuân XSD không, nhưng không thay thế `setSupportDtd(false)` hoặc parser external access policy. Khi schema có import/include, phần compiler cũng phải được bảo vệ.

Không lập luận rằng XSD cấm `orderId` sai pattern thì entity loading không thể xảy ra: parser có thể resolve entity **trước khi** áp facet.

### 14.3. JAXB context path nên cố định theo contract version

Với Spring-WS contract-first, hãy biên dịch JAXB classes từ trusted XSD đã versioned. Không tải `xsi:schemaLocation` do SOAP caller cung cấp làm “phiên bản schema mới” rồi tự sinh/nhận binding trong runtime.

Một sơ đồ an toàn:

~~~text
Trusted XSD/WSDL v1
    -> Build-time XJC
    -> JAXB package v1
    -> Secure SOAP parsing
    -> XSD validation (trusted resources)
    -> @Endpoint
~~~

Nếu contract đổi v2, kiểm soát versioning và interoperability. Đừng cho XML request từ đối tác tự quyết định schema compiler sẽ tải XSD ở đâu.

## 15. SchemaFactory và Validator: chặn external schema access

XML Schema là thứ khác DTD, nhưng XSD có thể dùng `xs:include`, `xs:import` hoặc `xs:redefine` tùy schema version để nạp các tài liệu khác. Nếu dùng schemaLocation không đáng tin hoặc resolver truy cập network tự do, bộ schema compiler có thể bị lợi dụng hoặc trở nên không tái lập được.

Một helper kiểm tra **XSD đơn lẻ đã đóng gói trong classpath**:

~~~java
import java.io.InputStream;

import javax.xml.XMLConstants;
import javax.xml.transform.dom.DOMSource;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;
import javax.xml.validation.Validator;

import org.springframework.core.io.ClassPathResource;
import org.w3c.dom.Document;

public final class OrdersXsdValidator {

    private final Schema schema;

    public OrdersXsdValidator() throws Exception {
        SchemaFactory factory =
            SchemaFactory.newInstance(
                XMLConstants.W3C_XML_SCHEMA_NS_URI
            );

        factory.setFeature(
            XMLConstants.FEATURE_SECURE_PROCESSING,
            true
        );

        factory.setProperty(
            XMLConstants.ACCESS_EXTERNAL_DTD, ""
        );
        factory.setProperty(
            XMLConstants.ACCESS_EXTERNAL_SCHEMA, ""
        );

        ClassPathResource resource =
            new ClassPathResource("xsd/orders-v1.xsd");

        // XSD này phải là trusted resource không có external
        // includes/imports, hoặc đã có local resolver phù hợp.
        schema = factory.newSchema(resource.getURL());
    }

    public void validate(InputStream xml)
            throws Exception {

        // Từ chối DOCTYPE trước khi kiểm tra XSD.
        Document safeDom = SecureXml.parse(xml);

        Validator validator = schema.newValidator();
        validator.setProperty(
            XMLConstants.ACCESS_EXTERNAL_DTD, ""
        );
        validator.setProperty(
            XMLConstants.ACCESS_EXTERNAL_SCHEMA, ""
        );

        validator.validate(new DOMSource(safeDom));
    }
}
~~~

Ở ví dụ, `SecureXml.parse` là helper đã tạo ở phần 11. `Schema` có thể dùng chung khi implementation tuân JAXP thread-safety requirements; `Validator` là mutable, **không chia sẻ đồng thời** giữa các threads. Nếu cần sử dụng nhiều XSD files có imports/includes, cấu hình resolver/catalog **cục bộ được kiểm soát**, không đơn giản bỏ restrictions để parser tải Internet.

### 15.1. Đường dẫn resource của XSD vẫn có base URI

`schemaFactory.newSchema(resource.getURL())` có thể dùng URL của resource để xác định base URI cho relative imports/includes. Nếu `ACCESS_EXTERNAL_SCHEMA=""`, một dependency được tham chiếu qua URL ngoài có thể bị chặn (đúng theo policy). Nếu contract sử dụng nhiều schema, phải cung cấp **nguồn tin cậy tương ứng** cho compiler.

Không “sửa” startup error bằng cách đặt:

~~~java
factory.setProperty(
    XMLConstants.ACCESS_EXTERNAL_SCHEMA,
    "all"
);
~~~

chỉ để mọi imports hoạt động. Điều đó mở rộng external access, không chứng minh tất cả dependencies đều đáng tin.

### 15.2. XML catalog và LSResourceResolver

Một chiến lược cho XSD dependencies:

- Package toàn bộ XSD v1/v2 đã phê duyệt trong JAR/WAR.
- Gán các namespace/system IDs vào local catalog.
- Dùng `LSResourceResolver` hoặc resolver của framework để trả đúng resources đã cho phép.
- Fail khi import trỏ tới namespace/system ID lạ.
- Kiểm tra schema compilation ở CI/startup.
- Không dựa vào DNS hoặc external HTTPS để build `Schema` mỗi request.

Lưu ý: theo một số JAXP implementations, một custom resolver được tin cậy có thể cung cấp resource dù `ACCESS_EXTERNAL_SCHEMA` bị hạn chế. Vì vậy resolver cũng phải enforce allowlist; không coi property một mình kiểm soát mọi mã tùy chỉnh.

### 15.3. Không tải XSD từ URL do client gửi

Một client SOAP có thể tự thêm `xsi:schemaLocation` vào payload, nhưng application phải dùng **schema đã được cấu hình từ hợp đồng**, không tự lấy XSD ở một hostname theo ý client. Điều này quan trọng với cả bảo mật lẫn khả năng tương thích.

## 16. TransformerFactory và XSLT cũng cần external-access policy

Nếu ứng dụng dùng XSLT hoặc `TransformerFactory` để biến đổi SOAP payload, có thể gặp những cơ chế nạp tài liệu khác như stylesheet imports/includes, `document()` trong XSLT hoặc resolver tùy biến.

Một cấu hình hạn chế:

~~~java
import javax.xml.XMLConstants;
import javax.xml.transform.Transformer;
import javax.xml.transform.TransformerFactory;

TransformerFactory factory =
    TransformerFactory.newInstance();

factory.setFeature(
    XMLConstants.FEATURE_SECURE_PROCESSING,
    true
);

factory.setAttribute(
    XMLConstants.ACCESS_EXTERNAL_DTD, ""
);

factory.setAttribute(
    XMLConstants.ACCESS_EXTERNAL_STYLESHEET, ""
);

Transformer transformer =
    factory.newTransformer();
~~~

Đối với một `StreamSource` XML từ nguồn không tin cậy, **đừng giả định** các thuộc tính của transformer đủ để chặn mọi parser paths. Có thể parse trước bằng DOM/SAX an toàn rồi dùng `DOMSource`/`SAXSource`, đồng thời giới hạn output/result size.

### 16.1. ACCESS_EXTERNAL_STYLESHEET khác ACCESS_EXTERNAL_SCHEMA

- `ACCESS_EXTERNAL_DTD` hạn chế DTD/entity external access.
- `ACCESS_EXTERNAL_SCHEMA` hạn chế schema access của validation infrastructure.
- `ACCESS_EXTERNAL_STYLESHEET` hạn chế stylesheet/document access của XSLT/Transformer.

Chúng phục vụ **những XML processors khác nhau**. Một ứng dụng không dùng XSLT có thể không cần cấu hình TransformerFactory, nhưng nếu đã dùng thì không thể dựa vào settings của DocumentBuilderFactory bên cạnh.

### 16.2. Custom URIResolver là nguồn đáng chú ý

Nếu `TransformerFactory`/`Transformer` sử dụng custom `URIResolver`, ứng dụng có thể tự tải HTTP/file resources. Resolver phải áp dụng allowlist và local resource mapping, không trả mọi URL từ stylesheet theo input bên ngoài.

### 16.3. XInclude không thuộc external entity DTD

XInclude là cơ chế include riêng (`http://www.w3.org/2001/XInclude`). Tắt external general entities không đủ để chứng minh XInclude bị tắt nếu một processor khác được cấu hình xử lý XInclude. Với DOM factory, dùng `setXIncludeAware(false)` khi không cần và kiểm thử provider thực tế.

## 17. SOAP message factory và ranh giới parse trước endpoint

Spring-WS có thể dùng SAAJ hoặc các XML message factories khác tùy version/dependencies. Một `SaajSoapMessageFactory` bao bọc SOAP provider; parser XML nằm trong provider/runtime và không nhất thiết nhận cài đặt từ một `DocumentBuilderFactory` do ứng dụng tạo riêng ở một bean khác.

Ví dụ:

~~~text
HTTP POST /ws
    -> MessageDispatcherServlet
    -> WebServiceMessageFactory creates SoapMessage
    -> SOAP Envelope parsed
    -> WS-Security/EndpointInterceptor
    -> @PayloadRoot / @RequestPayload
    -> @Endpoint method
~~~

Nếu parser ở bước “SOAP Envelope parsed” đã truy cập external resource, một interceptor kiểm tra XML sau đó là **quá muộn** để ngăn side effect. Vì thế cần đánh giá cụ thể XML parser của message factory/runtime.

### 17.1. Không có một setter chung cho mọi SOAP provider

Không tự chế một dòng:

~~~java
soapMessageFactory.setDisallowDoctype(true);
~~~

và coi nó là API Spring-WS chung khi chưa có bằng chứng. Tùy message factory, XML provider và Spring-WS major version, việc hạn chế DTD/entity có thể nằm ở:

- Cấu hình XML parser/transport handler được framework sử dụng.
- XML provider (SAAJ, Axiom hoặc thành phần tương đương).
- Factory/resource resolver của một transform custom.
- Upstream XML ingress filter có thể kiểm tra đúng encoding/stream.
- Thư viện XML cập nhật đã chặn DTD mặc định, cần test để xác nhận.

Vì vậy phần hành động là **xác minh parser thực tế** và viết SOAP integration test, không ghi một setter không có trong class.

### 17.2. SOAP client cũng có đường XML không đáng tin

`WebServiceTemplate` nhận response từ remote server và SOAP factory parse nó. Dù remote có HTTPS, ứng dụng vẫn cần defense-in-depth nếu response bị malformed hoặc server bị compromise. Một client chỉ cấu hình `Jaxb2Marshaller` mà không biết SOAP provider parse behavior vẫn chưa chứng minh toàn đường nhận response chống XXE.

### 17.3. XML attachments và multipart

Nếu dịch vụ hỗ trợ SOAP with Attachments hoặc MTOM, nội dung attachment có thể được ứng dụng đọc rồi parse như XML riêng. Khi đó nó là **một parser ingress thứ hai**, không mặc định hưởng cấu hình bảo vệ Envelope parser. Hạn chế attachment size, content type, XML features và external access độc lập.

## 18. XSD validation, SOAP Fault và bảo vệ XML parser là ba lớp khác nhau

Giả sử client gửi payload với `orderId=ABC` không khớp `ORD-[0-9]+`. `PayloadValidatingInterceptor` có thể tạo lỗi validation và SOAP Fault theo policy.

Nếu XML có DOCTYPE chứa external entity, parser nên **từ chối DOCTYPE ở tầng thấp hơn**. Kỳ vọng không nhất thiết là cùng một loại Fault giống lỗi XSD; đây có thể là lỗi SOAP message creation/XML parse.

Nếu SOAP Header WS-Security signature không đúng, lỗi phải qua policy của WS-Security. Không gộp tất cả thành “Schema invalid”.

| Tình huống | Lớp phát hiện | Hành vi mong muốn |
|---|---|---|
| XML không well-formed | XML parser | Reject sớm, không chạy domain |
| XML có DOCTYPE bị cấm | Secure XML parser | Reject sớm, không external I/O |
| XML external DTD URL | Parser/resolver | Không truy cập network từ untrusted XML |
| XSD pattern sai | Schema validator | SOAP validation Fault/error theo policy |
| SOAP Header signature sai | WS-Security | Reject, không xử lý nghiệp vụ |
| JAXB class không map được | OXM/unmarshaller | Contract/mapping error |
| Người dùng không có quyền xem đơn | Authentication/authorization | Domain/security rejection |

### 18.1. Không tiết lộ parser internals trong SOAP Fault

Nếu parser ném exception có absolute path/URL của external entity, **không đưa nguyên error message** vào SOAP Fault cho client không tin cậy. Một Fault công khai có thể có mã lỗi an toàn như `INVALID_XML_REQUEST`, correlation ID và thông báo chung; log nội bộ phải masking theo policy.

### 18.2. Payload validation không thay Authentication/Authorization

XML hợp XSD và không có DOCTYPE vẫn có thể yêu cầu một operation trái quyền. Ngược lại, chữ ký WS-Security hợp lệ không cho phép parser tải external entities. Các lớp bảo mật phải phối hợp chứ không được thay thế lẫn nhau.

## 19. Phân biệt XXE, XML Signature Wrapping và XPath injection

Các lỗi đều liên quan XML nhưng điều kiện và cách phòng vệ khác nhau:

| Lớp lỗi | Trọng tâm | Biện pháp chính |
|---|---|---|
| XXE | External entities/DTD làm parser truy cập tài nguyên | Cấm DTD, external access restrictions, resolver an toàn |
| Entity expansion DoS | Entities nội bộ nhân bản nội dung quá mức | DTD off, parser resource limits |
| XML Signature Wrapping | Sự khác biệt giữa phần XML được ký và phần xử lý nghiệp vụ | Xác minh WS-Security đúng nodes/IDs, schema/profile |
| XPath injection | Dữ liệu đầu vào được ghép vào biểu thức XPath | Tham số hóa/escaping đúng và giới hạn query |
| XSLT external document access | Stylesheet lấy tài nguyên từ ngoài | `ACCESS_EXTERNAL_STYLESHEET`, URIResolver allowlist |
| XInclude SSRF/file access | Include XML khác từ URI | Tắt XInclude hoặc resolver có policy |
| Oversized XML/Deep XML | XML quá lớn hoặc quá sâu gây CPU/RAM pressure | Request size, depth/time/concurrency limits |

Một dịch vụ có thể chống XXE đúng nhưng vẫn có XML Signature Wrapping nếu xác minh chữ ký xong lại xử lý sai DOM node. Vì vậy đừng ghi “XML secure” chỉ vì một negative XXE test pass.

### 19.1. Well-formed vs valid vs authenticated vs authorized

- **Well-formed**: XML đúng cú pháp.
- **Schema-valid**: payload tuân XSD được tin cậy.
- **Authenticated**: danh tính nguồn/endpoint được xác minh.
- **Integrity-protected**: nội dung nằm trong phạm vi chữ ký không bị thay đổi.
- **Authorized**: nguồn được phép thực hiện business operation.
- **Safe-to-process**: parser/input/resource limits đã đáp ứng chính sách.

Một thông điệp có thể đúng bốn điều đầu mà vẫn gây DoS vì XML quá lớn, hoặc đúng XSD nhưng người gửi không có quyền.

## 20. Khi thật sự cần DTD legacy thì làm gì?

Một số XML protocols hoặc tài liệu kế thừa cần DTD. Lúc đó không thể “cấm DOCTYPE vô điều kiện” mà không phá hợp đồng. Thay vì mở external entity resolution tự do:

1. **Phân loại dữ liệu**: DTD bắt buộc cho loại tài liệu nào, do ai cung cấp, với định danh nào?
2. **Đóng gói DTD đáng tin** trong classpath hoặc local catalog.
3. **Resolver allowlist** chỉ ánh xạ các public/system IDs được phê duyệt.
4. **Không truy cập mạng** theo system IDs do XML input tự chọn.
5. **Giới hạn entity expansion và tài nguyên**.
6. **Không dùng chung permissive parser** cho dữ liệu SOAP bên ngoài không cần DTD.
7. **Kiểm thử security riêng** cho DTD nội bộ/ngoài và các dependency references.
8. **Ghi nhận migration plan** sang XSD/no-DTD nếu có thể.

### 20.1. Logic EntityResolver allowlist

Pseudocode:

~~~java
// PSEUDOCODE: logic chính sách, không phải implementation hoàn chỉnh.
resolveEntity(publicId, systemId):
    if (publicId, systemId) == approvedLegacyCatalogKey:
        return trustedClasspathDtd()
    else:
        throw XmlPolicyViolation(
            "Unknown external entity identifier"
        )
~~~

Một resolver có thể trả `InputSource` của DTD đã kiểm soát. Đừng trả nguyên `new URL(systemId).openStream()` cho mọi request: điều đó chuyển quyền quyết định destination sang XML input của caller.

### 20.2. Local catalog không miễn việc kiểm tra nội dung

Tài liệu DTD được đóng gói phải được review và versioned. Nếu DTD tự định nghĩa parameter entities/imports trỏ ra network, resolver vẫn phải chặn nested external accesses không được phép. Kiểm thử mọi dependency paths và fail khi catalog chưa đầy đủ.

### 20.3. Tách parser profile

Một cách kiến trúc hợp lý:

~~~text
Public SOAP ingress:
    DTD prohibited
    External access prohibited
    Size/depth limits

Trusted legacy XML import:
    DTD allowed only via local catalog
    External network prohibited
    Expansion/resource limits
    Isolated permissions and separate tests
~~~

Không cho phép một legacy use case làm yếu mọi SOAP endpoints và SOAP client responses.

## 21. Kiểm thử XXE: phải chứng minh không có external I/O

Một chính sách parser chỉ thực sự đáng tin nếu được kiểm tra trên **đúng XML provider và entrypoint** đang chạy production.

Các mục tiêu của security tests:

1. XML bình thường được xử lý chính xác.
2. XML có DOCTYPE bị reject khi policy yêu cầu.
3. External entity tham chiếu file vô hại không được phép đọc.
4. External DTD/network access không được thực hiện.
5. Internal expansion không vượt qua parser policy.
6. XSD validation vẫn hoạt động trên XML hợp lệ, nhưng không thay chặn DTD.
7. SOAP endpoint không chạy domain logic nếu request bị reject.
8. SOAP client không chấp nhận response chứa DTD/external entity.
9. Schema/Transformer imports chỉ tới nguồn được phép.
10. Parser factory/security settings không đổi khi upgrade JDK/Spring-WS/XML provider.

### 21.1. Positive fixture: XML không có DTD

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
    <ord:orderId>ORD-2048</ord:orderId>
</ord:GetOrderRequest>
~~~

Đây là fixture hợp XSD `orders-v1.xsd` nếu contract định nghĩa các elements/namespace phù hợp. Test parser nên parse được, đọc root QName theo namespace và trả nội dung orderId đúng.

### 21.2. Negative fixture: DTD nội bộ, không tải bên ngoài

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE GetOrderRequest [
    <!ENTITY orderId "ORD-2048">
]>
<GetOrderRequest>&orderId;</GetOrderRequest>
~~~

Nếu parser policy là **cấm mọi DOCTYPE**, fixture này phải bị reject **dù entity chỉ nội bộ và vô hại**. Đây là cách kiểm tra tính nhất quán của chính sách, không chỉ khả năng chặn một external URL.

### 21.3. Negative fixture: SOAP Envelope có DOCTYPE

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE Envelope [
    <!ENTITY demo "ORD-2048">
]>
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
    <soap:Body>
        <ord:GetOrderRequest>
            <ord:orderId>&demo;</ord:orderId>
        </ord:GetOrderRequest>
    </soap:Body>
</soap:Envelope>
~~~

Một test SOAP ingress thực tế cần bảo đảm message factory từ chối document trước khi các XML entity replacements được dùng. Không chỉ assert payload validation sinh SOAP Fault và nghĩ rằng điều đó chứng minh external access bị chặn.

### 21.4. Negative fixture: external entity trỏ tệp mô phỏng

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE Envelope [
    <!ENTITY externalText SYSTEM "file:///tmp/xxe-demo-only.txt">
]>
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
    <soap:Body>
        <ord:GetOrderRequest>
            <ord:orderId>&externalText;</ord:orderId>
        </ord:GetOrderRequest>
    </soap:Body>
</soap:Envelope>
~~~

Không đặt secret thật tại đường dẫn này. Khi parser policy là reject DOCTYPE, test kỳ vọng parser **thất bại sớm**, không có nỗ lực mở tệp. Có thể dùng một custom `EntityResolver` ghi nhận mọi attempt và tự ném lỗi; lưu ý parser có thể reject DOCTYPE trước khi resolver được gọi, vẫn là hành vi an toàn.

### 21.5. Không dùng các payload DoS quá lớn trong CI chung

Để kiểm tra entity expansion/resource limits, dùng fixture nhỏ và kiểm soát kích thước, có timeout test và memory limit phù hợp. Không cố tạo “billion laughs” thực sự trên shared CI hay máy vận hành để chứng minh ứng dụng dễ bị cạn tài nguyên.

## 22. Unit test cho SecureXml.parse

Một test JUnit 5 tối giản cho DOM helper ở mục 11:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.w3c.dom.Document;
import org.xml.sax.SAXException;

class SecureXmlTest {

    private static ByteArrayInputStream bytes(String xml) {
        return new ByteArrayInputStream(
            xml.getBytes(StandardCharsets.UTF_8)
        );
    }

    @Test
    void acceptsNormalXmlWithoutDtd() throws Exception {
        String xml = """
            <order><id>ORD-2048</id></order>
            """;

        Document dom = SecureXml.parse(bytes(xml));

        assertEquals(
            "order",
            dom.getDocumentElement().getNodeName()
        );

        assertEquals(
            "ORD-2048",
            dom.getDocumentElement()
                .getElementsByTagName("id")
                .item(0)
                .getTextContent()
        );
    }

    @Test
    void rejectsEvenInternalDoctype() {
        String xml = """
            <!DOCTYPE order [
                <!ENTITY value "ORD-2048">
            ]>
            <order>&value;</order>
            """;

        assertThrows(
            SAXException.class,
            () -> SecureXml.parse(bytes(xml))
        );
    }
}
~~~

Test này kiểm tra **DOM parser helper**, không chứng minh một Spring-WS SOAP provider khác cũng sử dụng helper. Cần thêm integration test cho SOAP request/response thật.

Nếu parser implementation báo lỗi khác trong một tình huống do setup API/provider, cần kiểm tra đúng nguyên nhân, không sửa test thành `assertThrows(Exception.class, ...)` quá rộng rồi mặc nhiên coi protection đúng.

### 22.1. Test đảm bảo fail-closed ở startup

Một parser provider có thể không hỗ trợ `disallow-doctype-decl`. Nếu chọn provider đó, policy yêu cầu **không khởi chạy đường xử lý XML không an toàn**.

Test nên bao gồm việc tạo factory, áp toàn bộ các cờ và parse fixture DTD. Nếu chỉ assert methods `setFeature(...)` không ném exception, bạn chưa chắc provider thực thi như tài liệu.

### 22.2. Kiểm tra escape values không bị phá vỡ

Parser an toàn vẫn phải xử lý XML hợp lệ như:

~~~xml
<note>R&amp;D &lt;production&gt;</note>
~~~

Không cần DTD để decode `&amp;`/`&lt;`. Nếu hệ thống “chống XXE” bằng cách reject mọi ký tự `&`, nó đã làm hỏng XML hợp lệ và không thay thế một XML parser policy đúng đắn.

### 22.3. Negative test không nên tạo tác động bên ngoài

Với external URL, dùng một HTTP test server **local và đã được phép**, đếm inbound requests và khẳng định **zero external fetch**; hoặc dùng entity resolver ghi nhận các attempts, đồng thời chặn I/O. Không gọi ngẫu nhiên các endpoint internet, nội bộ hay metadata service của hạ tầng thật để kiểm tra XXE.

## 23. Spring-WS server integration test: khác với unit test parser

Một XML string không có DTD khi được đưa trực tiếp vào `MockWebServiceClient` có thể đi qua một code path khác so với raw HTTP bytes được `MessageDispatcherServlet`/SOAP provider parse.

Vì thế có hai tầng test:

| Tầng | Công cụ | Điều chứng minh |
|---|---|---|
| Parser unit | `SecureXml.parse`, SAX/StAX helper | Parser do ứng dụng tạo chặn DTD/external access |
| Endpoint unit | `MockWebServiceClient`/Spring-WS test | Endpoint mapping, SOAP Fault, domain side effects |
| HTTP integration | SOAP POST tới servlet embedded test server | Message factory/transport parser nhận raw XML có an toàn không |
| Client transport integration | Fake HTTP SOAP server trả XML có DOCTYPE | SOAP response parser/JAXB thực tế có chặn không |
| Contract test | Trusted XSD/JAXB/XML fixtures | QName, schema facets, WSDL binding |
| Security integration | WSS4J/TLS test configuration | Chữ ký, token, certificate, replay policy |

**Điểm mạnh của HTTP integration test:** nó có thể gửi raw XML request chứa `DOCTYPE` ngay từ đầu tài liệu và quan sát hành vi của SOAP message factory trước khi endpoint được gọi.

### 23.1. Kỳ vọng cho request có DOCTYPE

Một test đủ mạnh nên assert:

1. Response bị từ chối theo HTTP/SOAP error policy của runtime.
2. Domain service mock không được gọi.
3. Không có database write hoặc queue publish.
4. Parser không truy cập file/network ngoài.
5. Không log raw XML hoặc system paths.
6. Metric phân loại là `XML_POLICY_REJECTED`/`INVALID_XML`, không đếm nhầm là lỗi nghiệp vụ.

Không giả định mọi Spring-WS version trả cùng SOAP Fault code hoặc HTTP status khi parse lỗi **trước** endpoint mapping. Một số parser failures có thể không tạo SOAP Envelope response hợp lệ. Test phải bám theo chính sách được triển khai thực tế.

### 23.2. Kỳ vọng cho SOAP client nhận response nguy hiểm

Nếu partner trả một SOAP response có DOCTYPE bị cấm, client không nên:

- Đọc external entity.
- Unmarshal message như response hợp lệ.
- Đánh dấu operation thành công.
- Retry vô hạn nếu response là dữ liệu XML không hợp chính sách.

Client nên đưa lỗi tới tầng integration/contract handling và quan sát an toàn. `ClientInterceptor.handleFault` không nhất thiết chạy, vì lỗi parser có thể xảy ra **trước khi một SOAP Fault object tồn tại**.

### 23.3. Tái kiểm tra khi nâng cấp runtime

Sau khi nâng cấp Spring Boot/Spring-WS, Java/Jakarta XML Bind, SAAJ provider, Xerces, StAX provider hoặc WSS4J, phải chạy lại ít nhất:

- DOM/SAX/StAX DTD rejection.
- SOAP Envelope DTD rejection.
- SOAP client response DTD rejection.
- Local XSD imports/includes.
- XSLT external access restrictions nếu ứng dụng dùng XSLT.
- SOAP 1.1 và SOAP 1.2 conformance.
- WS-Security signatures và Fault handling.

Không chỉ nhìn version release notes rồi suy luận tất cả XML parsers mặc định đã an toàn.

## 24. Quan sát, log và xử lý vi phạm XML policy

Một sự kiện chặn DTD có thể được ghi như:

~~~text
event=xml_policy_rejected
service=orders-soap
operation=GetOrder
stage=soap_message_parse
policy=doctype_forbidden
partner_alias=partner-a
correlation_id=<approved-safe-id>
outcome=rejected
~~~

Đây là minh họa về format, không yêu cầu log chính xác các fields nếu chúng chưa được xác thực. Nếu parser fail trước khi đọc được WS-Addressing header, không tự lấy Action/MessageID từ XML chưa tin cậy rồi hiển thị như đã xác minh.

### 24.1. Không xuất nội dung của external resource vào log

Nếu parser trả lỗi có đường dẫn/URL, không ghi nguyên error stack vào một SOAP Fault công khai. Với log nội bộ, áp dụng data minimization và masking, nhất là khi system ID có thể do attacker tự đặt.

### 24.2. Metric labels nên có cardinality hữu hạn

Các labels tốt:

~~~text
parser=dom
policy=doctype_forbidden
channel=soap_inbound
result=rejected
~~~

Tránh dùng URI external entity tùy ý, raw XML body, request UUID, file path hoặc entire error message làm metric label. Chúng có cardinality cao và có thể chứa dữ liệu nhạy cảm.

### 24.3. Cảnh báo theo xu hướng, không chỉ một sự kiện

Một số XML policy violations có thể do client lỗi hoặc test; nhiều yêu cầu bị chặn liên tiếp có thể cho thấy hoạt động thăm dò. Hãy giám sát tỷ lệ, nguồn ở mức được phép, failure phase và mức ảnh hưởng tài nguyên. Đừng tự động ghi raw payload để “phân tích bảo mật” nếu nó chứa dữ liệu nhạy cảm.

## 25. Các lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Parser vẫn mở external URL | External entities/DTD loading chưa bị tắt ở entrypoint thật | Factory/provider, resolver, integration test |
| DOM helper an toàn nhưng SOAP service vẫn lỗi XXE | SOAP message factory parse trước helper | HTTP raw SOAP test, SOAP provider |
| Chỉ tắt `setExpandEntityReferences(false)` | Không chặn I/O hoặc external entity resolution chắc chắn | Cấm DOCTYPE, access restrictions |
| Chỉ bật `FEATURE_SECURE_PROCESSING` | Không chắc chặn mọi external access | Explicit access properties và tests |
| Feature không được hỗ trợ nhưng service vẫn chạy | Catch exception rồi bỏ qua | Fail closed, chọn parser phù hợp |
| SAX dùng reader từ factory khác | Config không áp vào XMLReader thực tế | Inspect reader/provider |
| StAX vẫn xử lý DTD | Provider không tuân `SUPPORT_DTD` như kỳ vọng | External resolver + negative tests |
| JAXB setSchema nhưng external entity vẫn được đọc | XSD validation không thay parser security | Secure Source và OXM config |
| XSD compilation lỗi sau khi hardening | `xs:import` cần resource | Local catalog/LSResourceResolver |
| XSLT tải document ngoài | Transformer/URIResolver chưa bị giới hạn | `ACCESS_EXTERNAL_STYLESHEET` |
| SOAP Body có DOCTYPE bên trong | XML không well-formed | Nhớ DOCTYPE thuộc prolog document |
| Chỉ bảo vệ request nhưng không bảo vệ response | Client SOAP factory dùng parser khác | Client transport integration |
| Endpoint không thấy request nhưng có file/network I/O | Parser xảy ra trước endpoint mapping | Kiểm soát message factory |
| XML không có DTD nhưng vẫn DoS | Body quá lớn/sâu hoặc XSLT phức tạp | Size/depth/time/concurrency limits |
| Vừa sửa cấu hình parser, WS-Security signature fail | XML normalization/transform thay message | Signature coverage/canonicalization test |

### 25.1. Quy trình điều tra một nghi vấn XXE

1. Xác định **XML entrypoint** thật: HTTP SOAP request, client response, file import, attachment, WSDL/XSD parser hay XSLT.
2. Xác định parser/provider và nơi factory được tạo.
3. Kiểm tra liệu XML có DOCTYPE hoặc external reference không qua log an toàn/test fixture.
4. Xác định security flags và resolver có thực sự áp vào object đang parse.
5. Xem có đường xử lý XML lần hai (DOM→StreamSource→JAXB) hay không.
6. Kiểm tra network/file access tại runtime bằng monitoring hợp pháp và được kiểm soát.
7. Đánh giá library/provider version và defaults, không dựa vào niềm tin “JDK mới đã an toàn”.
8. Viết regression test không gây external side effects.
9. Cấu hình fail-closed, hạn chế quyền filesystem/network và giới hạn tài nguyên.
10. Đảm bảo các SOAP operations hợp lệ vẫn parse/validate được sau khi hardening.

Không vô hiệu hóa security flags chỉ để làm một legacy DTD import hoạt động; giải quyết nguồn resource qua catalog đáng tin.

## 26. Bài thực hành: bảo vệ GetOrder SOAP service

Giả sử một service Spring-WS có:

~~~text
POST /ws/orders
  -> SOAP 1.1 Envelope
  -> GetOrderRequest / GetOrderResponse
  -> JAXB generated classes
  -> PayloadValidatingInterceptor
  -> OrdersEndpoint
~~~

Ứng dụng còn có một chức năng import XML từ đối tác legacy dùng DTD và xuất report XML bằng XSLT.

### Nhiệm vụ

1. Vẽ sơ đồ **mọi XML entrypoints và parsers**: SOAP factory, JAXB, DOM/SAX/StAX, XSD, XSLT.
2. Phân loại nguồn XML nào **không đáng tin** và nguồn nào là trusted resources.
3. Viết một XSD có `GetOrderRequest` và constraint cho `orderId`.
4. Viết SOAP request hợp lệ không có DTD, xác nhận endpoint nhận đúng QName.
5. Tạo `SecureXml.parse` cấm DOCTYPE và external access; test với XML đơn giản.
6. Test internal DOCTYPE vô hại bị từ chối.
7. Test external entity tham chiếu **dummy local file** không được đọc.
8. Test external DTD tham chiếu một **fake HTTP server** không có request tới.
9. Test malformed XML khác với parser-policy violation.
10. Test SOAP HTTP POST có DOCTYPE bị chặn trước domain service.
11. Test SOAP client nhận response có DTD không chấp nhận và không truy cập external resources.
12. Test `SchemaFactory`/`Validator` với trusted XSD, chặn schema URL lạ.
13. Nếu XSD có include/import, tạo `LSResourceResolver` chỉ trả resource có trong catalog.
14. Cấu hình `TransformerFactory` chặn external DTD/stylesheet access và test.
15. Với legacy DTD import, tạo parser profile riêng chỉ dùng catalog local và strict resource limits.
16. Chạy regression với SOAP 1.1/1.2 và JAXB nil/namespace semantics.
17. Kiểm tra WS-Security signature/timestamp không bị thay đổi ngoài ý muốn khi hardening.
18. Đo XML body size, CPU/memory, latency và số requests bị policy chặn.
19. Đảm bảo SOAP Fault/log không lộ file paths, external URLs hoặc secrets.
20. Ghi lại chính sách fail-closed khi provider không hỗ trợ một protection feature.

**Tiêu chí đạt:** Request/response SOAP bình thường vẫn chạy đúng contract; mọi DOCTYPE bị chặn ở nguồn SOAP không tin cậy; không có file/network external access do entity; legacy DTD chỉ hoạt động qua catalog đã tin cậy; resource limits và security tests có thể tái chạy trên đúng runtime.

### 26.1. Câu hỏi tình huống A

Một đội phát triển bật `PayloadValidatingInterceptor` và xác nhận request sai pattern `orderId` bị SOAP Fault. Họ kết luận service không thể có XXE. Lập luận này sai ở bước nào? Hãy chỉ ra parser nào có thể đọc external entity **trước** validator và mô tả negative test chứng minh external I/O bị chặn.

### 26.2. Câu hỏi tình huống B

Một XSD sử dụng `xs:import` từ một namespace chung. Sau khi đặt `ACCESS_EXTERNAL_SCHEMA=""`, schema compilation fail vì không tìm thấy import. Có nên đặt `ACCESS_EXTERNAL_SCHEMA="all"` để chạy lại không? Hãy đề xuất cách đóng gói XSD cùng resolver/catalog local, vẫn giữ external access restricted.

## 27. Checklist trước khi phát hành SOAP service có XML an toàn

- [ ] Đã xác định tất cả XML entrypoints và parser implementations.
- [ ] Không nhận DOCTYPE từ SOAP XML không tin cậy khi contract không cần DTD.
- [ ] External general entities, external parameter entities và external DTD loading đã bị chặn.
- [ ] `ACCESS_EXTERNAL_DTD` và `ACCESS_EXTERNAL_SCHEMA` được cấu hình ở những JAXP processors phù hợp.
- [ ] `FEATURE_SECURE_PROCESSING` được bật nhưng không bị coi là thay thế các bảo vệ khác.
- [ ] XInclude tắt nếu ứng dụng không cần.
- [ ] Không dựa riêng vào `setExpandEntityReferences(false)` hoặc quét raw XML string.
- [ ] Parser không hỗ trợ security feature sẽ fail-closed theo policy.
- [ ] SOAP message factory và JAXB/OXM được kiểm tra trên runtime thực, không chỉ trên helper DOM riêng.
- [ ] Client SOAP response parsing cũng được harden.
- [ ] XSD compilation sử dụng resources/resolver tin cậy, không tải URL client tự chọn.
- [ ] XSLT/Transformer external access được giới hạn nếu có sử dụng.
- [ ] Legacy DTD được tách profile và chỉ resolve từ local catalog allowlist.
- [ ] Request body, attachment size, XML depth, entity limits, timeout và concurrency có giới hạn phù hợp.
- [ ] XML parser policy được kiểm thử bằng benign DTD và external entity fixtures.
- [ ] SOAP HTTP integration test chứng minh domain service không được gọi khi parse bị reject.
- [ ] Có tests xác nhận không phát sinh external file/network access.
- [ ] SOAP Fault/log/metrics không lộ secrets, file paths hoặc raw XML nhạy cảm.
- [ ] WS-Security, SOAP 1.1/1.2, JAXB và WSDL/XSD interoperability vẫn chạy đúng.
- [ ] Test XXE/resource limits được chạy lại sau mỗi nâng cấp JDK, Spring-WS, JAXB hoặc parser provider.

## 28. Ghi nhớ

- **DTD** có thể khai báo entities trong internal hoặc external subset; `DOCTYPE` nằm trước root element của XML document.
- **External entity** có thể khiến XML processor truy cập file hoặc network khi parser/resolver cho phép; tác động phụ thuộc quyền process và cách dữ liệu bị sử dụng.
- **XXE cần input không tin cậy đi tới parser có khả năng phân giải external references**, không chỉ vì XML chứa một chuỗi trông giống entity.
- **Entity expansion DoS** có thể xảy ra với internal entities mà không cần external network.
- **Cấm DOCTYPE khi không cần DTD** là chính sách đơn giản, rõ ràng; kết hợp external access restrictions, resource limits và fail-closed.
- **DOM/SAX/StAX/JAXB, SchemaFactory và TransformerFactory có các điểm cấu hình riêng**; cài đặt một factory không tự bảo vệ mọi entrypoint.
- **XSD validation không thay XXE prevention**, và WS-Security signature không thay XML parser hardening.
- **Spring-WS message factory có thể parse XML trước endpoint/interceptor**, nên phải kiểm tra security ở ranh giới nhận XML thực tế.
- **Legacy DTD phải qua local trusted catalog**, không mở URL/system IDs tự do.
- **Negative tests cần chứng minh không có external I/O**, đồng thời giữ positive SOAP/XSD/JAXB tests hoạt động.

**Câu hỏi tự kiểm tra:** Một ứng dụng Spring-WS nhận SOAP request qua `MessageDispatcherServlet` và dùng `PayloadValidatingInterceptor` kiểm tra XSD. Developer còn có một `DocumentBuilderFactory` riêng trong domain service, đã đặt `setExpandEntityReferences(false)`, nên khẳng định hệ thống chống XXE hoàn toàn. Hãy phân tích tại sao hai biện pháp đó chưa đủ, nêu các **điều kiện dẫn đến XXE**, điểm parser có thể chạy trước endpoint, cấu hình bảo vệ cần áp dụng cho DOM/SAX/StAX/JAXB và thiết kế ba negative tests chứng minh SOAP input không thể đọc file hoặc truy cập external URL.



