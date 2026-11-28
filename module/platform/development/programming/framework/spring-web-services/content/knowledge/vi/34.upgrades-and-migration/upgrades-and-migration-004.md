# Đối chiếu mã được sinh, plugin sinh mã và implementation XML khi nâng cấp

Trong dự án **Spring Web Services (Spring-WS)** theo hướng **contract-first**, XSD/WSDL là hợp đồng trao đổi dữ liệu. Mã Java do XJC sinh ra, plugin sinh mã và thư viện xử lý XML chỉ là những cách triển khai hợp đồng đó. Khi nâng cấp JDK, Spring-WS, JAXB hoặc công cụ build, dự án có thể biên dịch thành công nhưng lại gửi XML khác trước: thay namespace, mất một phần tử, đổi quy tắc xử lý `null`, hay phát sinh SOAP Fault tại hệ thống đối tác.

Bài học thuộc chương **Nâng cấp và di chuyển**, tập trung vào cách đối chiếu **ba lớp có liên hệ chặt chẽ**: (1) hợp đồng XSD/WSDL và mã được sinh, (2) plugin cùng cấu hình sinh mã, (3) implementation XML/JAXB chạy thực tế. Mục tiêu là nâng cấp dịch vụ SOAP hoặc SOAP client mà vẫn giữ được khả năng tương thích được cam kết với hệ thống doanh nghiệp.

## 1. Xác định chính xác điều gì cần giữ ổn định

Hãy phân biệt **tương thích nguồn Java**, **tương thích XML trên đường truyền** và **tương thích hành vi SOAP**:

| Lớp | Thành phần cần đối chiếu | Ví dụ thay đổi gây lỗi |
| --- | --- | --- |
| Hợp đồng XML | `targetNamespace`, phần tử gốc, kiểu XSD, thứ tự `xs:sequence`, `minOccurs`, `nillable` | Bên nhận không nhận diện `GetOrderRequest` do sai namespace |
| WSDL | `message`, `portType`, `operation`, `binding`, `soapAction`, SOAP 1.1/1.2, địa chỉ endpoint | Client sinh proxy khác hoặc gửi sai `SOAPAction` |
| Mã được sinh | `ObjectFactory`, `package-info.java`, `@XmlElement`, `@XmlRootElement`, `JAXBElement`, kiểu trường | Mã mới biểu diễn phần tử tùy chọn bằng `JAXBElement<T>` thay vì `T` |
| Công cụ sinh mã | Plugin, phiên bản XJC, binding customization, catalog, JDK/toolchain | Một máy dùng XJC 2.x, máy khác dùng XJC 4.x |
| Runtime XML | JAXB API, JAXB provider, SAAJ, parser XML, schema validation | XJC sinh annotation `jakarta.*` nhưng ứng dụng vẫn nạp runtime `javax.*` |
| Spring-WS và tích hợp | `@Endpoint`, `Jaxb2Marshaller`, `WebServiceTemplate`, interceptor, Fault, WS-Security | Payload đúng XSD nhưng chữ ký SOAP hoặc cơ chế xử lý Fault thay đổi |

**Nguyên tắc:** tên lớp Java hoặc mã nguồn Java thay đổi chưa chắc làm đổi hợp đồng XML. Ngược lại, mã Java nhìn gần như giống nhau vẫn có thể marshal ra XML không tương thích. Vì vậy cần so sánh cả **mã được sinh** lẫn **XML/WSDL thực tế**.

## 2. Lập đường cơ sở trước khi nâng cấp

Trước khi thay phiên bản phụ thuộc, lưu một bộ dữ liệu đối chứng của bản đang chạy ổn định:

1. **Contract:** XSD và WSDL thực sự công bố cho đối tác. Nếu dùng `DefaultWsdl11Definition`, tải WSDL từ dịch vụ đang chạy để phát hiện thay đổi phát sinh từ cấu hình Spring, không chỉ từ file XSD.
2. **Build:** phiên bản JDK, Maven/Gradle, plugin XJC/WSDL codegen, các dependency transitives liên quan JAXB, Activation, SAAJ và XML parser; cùng các file binding `.xjb` và XML catalog nếu có.
3. **Generated Java:** mã được sinh sau một lần build sạch, đặc biệt `ObjectFactory.java`, `package-info.java`, annotation JAXB, kiểu Java và danh sách class.
4. **Wire samples:** ít nhất một SOAP request/response hợp lệ, một trường hợp phần tử tùy chọn, một SOAP Fault và một thông điệp có WS-Security nếu tích hợp sử dụng chữ ký hoặc mã hóa.
5. **Kết quả tương thích:** danh sách client/đối tác, SOAP version, endpoint URL, yêu cầu `SOAPAction`, các XSD import và chính sách WS-Security đang áp dụng.

Có thể lưu bộ baseline trong thư mục kiểm thử hoặc artifact của bản phát hành (ví dụ `compat/baseline/`), kèm commit/build ID để truy lại. Nếu tổ chức không commit generated sources, vẫn phải lưu bản sinh của release làm đối chứng. **Không so sánh bản build mới với thư mục `target/` cũ còn sót lại.**

Một cấu trúc tham khảo:

```text
compat/
  baseline/
    orders.xsd
    orders.wsdl
    request-soap11.xml
    response-soap11.xml
    fault.xml
    generated-java/
  candidate/
    orders.wsdl
    generated-java/
src/main/resources/xsd/orders.xsd
src/main/resources/jaxb/bindings.xjb
```

Trong quy trình **contract-first**, chỉnh XSD/WSDL phải là quyết định có chủ đích. Không nên sửa bản hợp đồng chỉ để ép mã Java mới trông giống mã cũ.

## 3. Đối chiếu công cụ và quá trình sinh mã

### 3.1. Xác nhận đầu vào và phiên bản có thể tái lập

Plugin XJC biên dịch XSD thành các class JAXB. Các plugin khác (ví dụ công cụ codegen dựa trên WSDL) có thể sinh thêm service interface, stub hoặc client proxy. Không nên dùng hai bộ sinh mã khác nhau cho cùng một package rồi để class nào xuất hiện sau cùng quyết định kết quả.

Với Maven, một **ví dụ minh họa** cho nhánh JAXB/Jakarta là:

```xml
<plugin>
    <groupId>org.codehaus.mojo</groupId>
    <artifactId>jaxb2-maven-plugin</artifactId>
    <version>3.2.0</version>
    <executions>
        <execution>
            <id>generate-order-model</id>
            <goals>
                <goal>xjc</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <sources>
            <source>src/main/resources/xsd/orders.xsd</source>
        </sources>
        <outputDirectory>target/generated-sources/jaxb</outputDirectory>
        <packageName>com.example.orders.ws.schema</packageName>
        <clearOutputDir>true</clearOutputDir>
    </configuration>
</plugin>
```

Đây là **một lựa chọn plugin**, không phải cấu hình bắt buộc cho mọi dự án. Nếu đang dùng `org.jvnet.jaxb:jaxb-maven-plugin`, Apache CXF codegen hoặc plugin khác, đối chiếu cú pháp cấu hình và bộ XJC thực tế của **chính plugin đó**. Chỉ đổi `groupId`/`artifactId` mà giữ nguyên các tham số cấu hình có thể khiến binding file hoặc schema import bị bỏ qua.

Các điểm cần khóa và lưu lại:

| Hạng mục | Câu hỏi kiểm chứng |
| --- | --- |
| Plugin và phiên bản | Phiên bản được khai báo cố định hay lấy từ property/profiles khác nhau? |
| JAXB/XJC | Bộ sinh dùng JAXB 2.x (`javax.xml.bind`) hay Jakarta XML Binding 3.x/4.x (`jakarta.xml.bind`)? |
| Nguồn schema | Đọc đúng XSD, schema import/include và XML catalog? Có tải URL bên ngoài trong lúc build không? |
| Binding file | File `.xjb` có đúng namespace, phiên bản và XPath/node selector của XJC mới? |
| Package và output | `packageName`/mapping namespace có ổn định? Generated sources có bị chồng lên mã viết tay? |
| Tính tái lập | JDK/toolchain, locale, encoding, profile, nguồn dependency và đường dẫn sinh có được kiểm soát? |

Khi nâng cấp từ JAXB 2 sang Jakarta XML Binding, binding customization cũ có thể phải đổi từ namespace `http://java.sun.com/xml/ns/jaxb` sang `https://jakarta.ee/xml/ns/jaxb` và dùng phiên bản binding phù hợp. Không tự động thay mọi namespace của XSD: namespace trong tài liệu binding chỉ điều khiển **công cụ sinh mã**, còn `targetNamespace` của XSD là **hợp đồng với đối tác**.

### 3.2. So sánh kết quả sinh mã đúng cách

Sau một lần sinh lại từ cùng input, đối chiếu bản baseline và candidate:

```bash
# Minh họa việc so sánh hai thư mục generated sources đã lưu:
git diff --no-index -- compat/baseline/generated-java compat/candidate/generated-java
```

`git diff --no-index` trả exit code `1` khi có khác biệt; đây là tín hiệu cần phân tích, không mặc định là build lỗi.

Thứ tự đọc khác biệt nên là:

1. **`package-info.java`:** `@XmlSchema(namespace=...)`, `elementFormDefault`, mapping giữa package và namespace.
2. **`ObjectFactory.java`:** `@XmlElementDecl`, QName (`namespace` + `localPart`), các phương thức khởi tạo `JAXBElement`.
3. **Các model:** `@XmlType(propOrder=...)`, `@XmlElement(name=..., required=..., nillable=...)`, `@XmlAttribute`, adapter, enum và kiểu dữ liệu.
4. **API được tham chiếu:** import `javax.xml.bind.*` so với `jakarta.xml.bind.*`, các adapter và kiểu dữ liệu tùy biến.
5. **Lượng class:** class bị mất, thêm hoặc đổi package có thể do schema import không được nạp, binding không còn tác dụng hoặc đổi kiểu sinh phần tử gốc.

Phải phân biệt thay đổi **dự kiến ở Java API** với thay đổi **không được phép ở XML**:

| Diff nhận được | Cách đánh giá |
| --- | --- |
| `javax.xml.bind.annotation.XmlElement` → `jakarta.xml.bind.annotation.XmlElement` | Dự kiến khi chuyển sang Jakarta; vẫn phải chạy test marshal/unmarshal |
| Chỉ đổi thứ tự method, định dạng hoặc comment được sinh | Thường không ảnh hưởng XML; kiểm tra cấu hình sinh trước khi bỏ qua |
| `@XmlSchema(namespace="urn:example:orders:v1")` bị đổi/mất | Nguy cơ phá hợp đồng; kiểm tra XSD, binding và XML thực tế |
| `propOrder`, `required`, `nillable` hoặc `@XmlElementDecl` đổi | Có thể đổi XML và cách xử lý dữ liệu; cần test riêng |
| `String` → `JAXBElement<String>` hoặc type adapter thay đổi | Kiểm tra phân biệt absent / `xsi:nil` / có giá trị |
| Không còn `ObjectFactory` hoặc class của namespace phụ | Xác minh plugin đã đọc đủ schema/import và đúng package |

Không nên thay model sinh mã bằng chỉnh sửa thủ công trong `target/generated-sources`: lần build kế tiếp sẽ ghi đè và làm kết quả không tái lập được. Sửa schema/binding khi thật sự cần và sinh lại.

## 4. Tách phần XML contract khỏi Java binding

Giả sử hợp đồng đang dùng:

```xml
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           targetNamespace="urn:example:orders:v1"
           xmlns:tns="urn:example:orders:v1"
           elementFormDefault="qualified">
    <xs:element name="GetOrderRequest">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="orderId" type="xs:string"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
```

Một SOAP body tương thích có payload:

```xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
    <ord:orderId>ORD-42</ord:orderId>
</ord:GetOrderRequest>
```

Trong XML, **prefix `ord` có thể đổi tên** nhưng QName của hai phần tử phải giữ nguyên. Chẳng hạn `<GetOrderRequest xmlns="urn:example:orders:v1">` tương đương về tên XML với `<ord:GetOrderRequest ...>`, miễn namespace của các phần tử con cũng chính xác. Trái lại, chuỗi `<orderId>` ở namespace rỗng **không tương đương** với `<ord:orderId>` trong ví dụ trên.

Vì vậy đừng quyết định tương thích bằng việc so sánh byte-for-byte của XML sau khi JAXB marshal: prefix, khoảng trắng, thứ tự khai báo namespace và cách định dạng có thể thay đổi mà không phá schema. Hãy so sánh **QName, cấu trúc, giá trị và các ràng buộc XSD**. Riêng chữ ký số WS-Security, phải kiểm tra việc ký/xác minh và canonicalization thực tế; không được chỉ dựa vào phép so sánh XML đã bỏ qua prefix.

Các khác biệt về dữ liệu dễ bị bỏ sót:

- `minOccurs="0"` cho phép **vắng mặt**; `nillable="true"` cho phép phần tử tồn tại với `xsi:nil="true"`. Hai trạng thái này không đồng nghĩa.
- `xs:decimal` cần bảo toàn giá trị và độ chính xác; kiểm tra schema facets như `totalDigits`, `fractionDigits`.
- `xs:date`/`xs:dateTime` có thể chịu ảnh hưởng adapter, múi giờ và biểu diễn lexical; thử các giá trị có và không có timezone theo contract.
- `xs:sequence` ràng buộc thứ tự; `@XmlType(propOrder=...)` thay đổi có thể làm đối tác từ chối payload.
- `xs:choice`, phần tử lặp và nillable collections cần test riêng vì XJC có thể đổi hình dạng Java API.

## 5. Đối chiếu implementation XML chạy thực tế

Một bản nâng cấp hoàn chỉnh phải kiểm tra **cả lúc sinh Java** và **lúc serialize/deserialize XML**. Trong ứng dụng Spring-WS, class JAXB được sinh là model; `Jaxb2Marshaller` dùng JAXB runtime để marshal/unmarshal; `WebServiceTemplate` hoặc `@Endpoint` dùng model đó để xử lý SOAP message.

Ví dụ cấu hình marshaller cho model được sinh trong package xác định:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.ClassPathResource;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;

@Bean
Jaxb2Marshaller ordersMarshaller() {
    Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
    marshaller.setContextPath("com.example.orders.ws.schema");
    marshaller.setSchema(new ClassPathResource("xsd/orders.xsd"));
    return marshaller;
}
```

`setContextPath` yêu cầu JAXB context tìm được các class hỗ trợ của package (thường có `ObjectFactory` do XJC sinh). Đường dẫn `xsd/orders.xsd` phải thực sự được đóng gói vào classpath. Schema validation ở mức marshaller hữu ích nhưng **không thay thế** kiểm thử endpoint, SOAP Fault, cấu hình `PayloadValidatingInterceptor` (nếu dùng) hoặc xác minh trao đổi với đối tác.

Ở phía endpoint, kiểm tra QName dùng để dispatch:

```java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

@Endpoint
public class OrderEndpoint {
    private static final String NS = "urn:example:orders:v1";

    @PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
    @ResponsePayload
    public GetOrderResponse getOrder(@RequestPayload GetOrderRequest request) {
        // Xử lý nghiệp vụ và tạo response hợp lệ theo schema.
        throw new UnsupportedOperationException("Minh họa chữ ký endpoint");
    }
}
```

Đoạn mã trên **minh họa cấu trúc**, không phải endpoint hoàn chỉnh: `GetOrderRequest`/`GetOrderResponse` phải thực sự được sinh từ contract thích hợp; cấu hình adapter/marshaller của Spring phải hỗ trợ tham số/trả về tương ứng. Nếu XJC sinh phần tử gốc dưới dạng `JAXBElement<T>` (qua `ObjectFactory`) thay vì class có `@XmlRootElement`, cần điều chỉnh cách marshal hoặc binding một cách nhất quán với contract.

Ở phía SOAP client, kiểm tra lại `WebServiceTemplate` được gán đúng marshaller và unmarshaller, đích `defaultUri`, callback cho `SOAPAction`, interceptor/bảo mật, và xử lý `SoapFaultClientException`. Việc đổi thư viện XML không được âm thầm đổi SOAP 1.1 thành SOAP 1.2 hay làm mất HTTP/header yêu cầu bởi đối tác.

### 5.1. Chuyển từ Java EE / `javax` sang Jakarta

Trong lộ trình phổ biến từ Spring Framework 5 / Spring-WS 3 sang Spring Framework 6 / Spring-WS 4, nhiều API Jakarta EE đổi package. Kiểm tra theo **từng API**, không thay toàn bộ chuỗi `javax.` một cách máy móc:

| Khu vực | Trước (ví dụ) | Sau (ví dụ) |
| --- | --- | --- |
| JAXB annotations và API | `javax.xml.bind.*` | `jakarta.xml.bind.*` |
| SOAP with Attachments API (SAAJ) | `javax.xml.soap.*` | `jakarta.xml.soap.*` |
| Activation | `javax.activation.*` | `jakarta.activation.*` |
| Servlet API | `javax.servlet.*` | `jakarta.servlet.*` |
| XML/JAXP thuộc Java SE | `javax.xml.namespace.QName`, `javax.xml.transform.*`, `javax.xml.parsers.*` | **Giữ nguyên tên package** |

Không nên trộn model mang annotation `javax.xml.bind` với JAXBContext/JAXB provider chỉ hiểu `jakarta.xml.bind`. Đồng thời phân biệt **JAXB API** (kiểu và interface) với **JAXB implementation/provider** (bộ thực thi thực sự). Tương tự, khai báo Jakarta SAAJ API chưa có nghĩa classpath đã có SAAJ implementation phù hợp.

Triệu chứng thường gặp khi phối hợp sai bộ thư viện là `ClassNotFoundException`, `NoClassDefFoundError`, `JAXBException` khi tạo context, lỗi tìm provider/factory, hoặc lỗi marshal chỉ xảy ra lúc nhận request đầu tiên. Kiểm tra cây phụ thuộc, classpath lúc chạy và nội dung package/annotation của **generated classes** thay vì cố sửa bằng việc thêm tùy tiện cả bộ `javax` và `jakarta`.

Một số dự án dùng EclipseLink MOXy thay cho JAXB RI hoặc dùng StAX, DOM, SAX, Axiom, SAAJ ở những lớp khác nhau. Khi đổi provider/parser, cần thử lại mapping đặc biệt (adapter, namespace prefix, nil, attachment/MTOM), cách xử lý XML lỗi và cấu hình chống XXE/DTD, không suy rằng kết quả của hai implementation luôn trùng khớp.

## 6. WSDL sinh động, SOAP Fault và WS-Security

Với Spring-WS, `DefaultWsdl11Definition` có thể xuất WSDL từ XSD cùng các thiết lập như `portTypeName`, `locationUri`, `targetNamespace` và schema được gán. Vì thế, giữ nguyên XSD chưa đủ để đảm bảo WSDL công bố không đổi.

Khi so sánh WSDL baseline/candidate, chú ý:

- `wsdl:definitions/@targetNamespace`, các QName trong `message`, `portType`, `binding`, `service` và `port`.
- Tên operation, kiểu binding document/literal, SOAP 1.1 so với SOAP 1.2 và giá trị `soapAction`.
- Các XSD được import, schemaLocation, relative URL và khả năng resolve trên môi trường triển khai thật.
- `soap:address location`: địa chỉ có thể hợp lệ khác nhau giữa test/prod; tách riêng khác biệt cấu hình môi trường khỏi khác biệt contract.
- WSDL phát sinh từ quá trình chạy ứng dụng, nhất là khi reverse proxy, servlet mapping hoặc tính năng transform location làm thay đổi URL.

Với SOAP Fault, kiểm tra đồng thời **HTTP status, Fault code, Fault string/reason, detail element và namespace** theo SOAP version đang dùng. Một exception Java khác sau nâng cấp có thể dẫn đến Fault detail khác, khiến hệ thống tích hợp không còn nhận diện lỗi nghiệp vụ.

Với WS-Security hoặc XML Signature/Encryption, thử lại UsernameToken, Timestamp, chữ ký/chứng chỉ/chuỗi tin cậy, alias keystore, thuật toán và phần tử được ký. Sự thay đổi namespace, ID attribute, parser, serializer hoặc interceptor có thể khiến chữ ký không xác minh được dù payload vẫn hợp lệ theo XSD. Nếu dùng MTOM/XOP, phải kiểm tra MIME boundary, Content-ID và kiểu attachment ở mức thông điệp SOAP.

## 7. Quy trình kiểm thử tương thích theo từng lớp

Thực hiện cùng một bộ trường hợp kiểm thử trên baseline và candidate. Một kết quả build thành công chỉ là điều kiện đầu tiên.

| Bước | Cách kiểm thử | Tiêu chí đạt |
| --- | --- | --- |
| 1. Clean codegen | Xóa **chỉ output được sinh** trong môi trường build kiểm soát; chạy lại goal sinh mã của dự án | Sinh lại đầy đủ, không lệ thuộc file cũ hoặc dữ liệu tải từ nguồn không kiểm soát |
| 2. Structural diff | So sánh `ObjectFactory`, `package-info`, model, binding và plugin | Mọi thay đổi được giải thích; QName/schema constraints không bị đổi ngoài ý muốn |
| 3. Contract diff | So sánh XSD/WSDL đã công bố, parse import và resolve schema | Giữ operation, namespace, binding và SOAPAction theo cam kết |
| 4. JAXB round-trip | Unmarshal XML baseline → object → marshal → validate lại XSD | Giữ cấu trúc và dữ liệu có ý nghĩa; không mất trường hoặc đổi nil/absent |
| 5. Endpoint test | Gửi SOAP request vào endpoint (có thể dùng `MockWebServiceClient`) | Dispatch đúng `@PayloadRoot`, response hợp lệ, Fault đúng contract |
| 6. Client test | Dùng `MockWebServiceServer` hoặc server đối chứng với `WebServiceTemplate` | Client gửi đúng payload, SOAPAction, SOAP version và xử lý response/Fault |
| 7. Integration test | Gọi dịch vụ thật ở môi trường kiểm thử với đối tác tương ứng | Tương thích cả WS-Security, TLS/chứng chỉ, proxy, timeout và attachment nếu có |

### Bộ ca thử tối thiểu

1. **Happy path:** một request/response hợp lệ, có namespace đầy đủ và dữ liệu Unicode.
2. **Phần tử tùy chọn:** vắng mặt, hiện diện rỗng, `xsi:nil="true"` (chỉ khi contract cho phép), và phần tử lặp 0/1/n lần.
3. **Dữ liệu biên:** precision của decimal, date/time kèm timezone, enum, độ dài lớn và ký tự XML cần escaping.
4. **XML không hợp lệ:** sai QName/namespace, sai thứ tự `xs:sequence`, sai kiểu dữ liệu, schema import lỗi; xác minh cách báo Fault phù hợp.
5. **Tích hợp:** SOAP 1.1/1.2 đúng phiên bản yêu cầu, `SOAPAction`, Fault detail, WS-Security và MTOM nếu đang dùng.

Có thể dùng hai XML mẫu minh họa sau để nhận diện lỗi rất thường gặp. Payload đầu có QName đúng:

```xml
<o:GetOrderRequest xmlns:o="urn:example:orders:v1">
  <o:orderId>ORD-42</o:orderId>
</o:GetOrderRequest>
```

Payload sau **không tương thích** với ví dụ XSD ở mục 4: `orderId` ở namespace rỗng, dù local name và giá trị vẫn giống:

```xml
<o:GetOrderRequest xmlns:o="urn:example:orders:v1">
  <orderId>ORD-42</orderId>
</o:GetOrderRequest>
```

Trong phép so sánh tự động, nên parse XML với chế độ namespace-aware và khẳng định QName hoặc XPath có namespace map, sau đó validate với XSD. Với thông điệp đã ký, thêm bài kiểm tra **verify signature**, vì kiểm tra XML tương đương về ngữ nghĩa không tự chứng minh chữ ký còn hợp lệ.

## 8. Xử lý khi có khác biệt và quyết định phát hành

Khi phát hiện diff, truy nguyên theo hướng từ hợp đồng đến runtime:

| Hiện tượng | Nguồn gốc nên kiểm tra trước | Cách xử lý |
| --- | --- | --- |
| Sinh thiếu class, thiếu `ObjectFactory` | XSD import/include, XML catalog, package mapping, plugin profile, file binding | Sửa đầu vào/cấu hình codegen, clean-generate rồi đối chiếu lại |
| Class chuyển `javax.xml.bind` sang `jakarta.xml.bind` nhưng lỗi lúc chạy | JAXB API/provider, SAAJ/Activation runtime, generated code cũ lẫn mới | Đồng bộ dependency và nguồn sinh; kiểm tra classpath/runtime |
| Payload khác namespace hoặc sai thứ tự | `@XmlSchema`, `@XmlElement`, `propOrder`, adapter, provider XML | Sửa binding/marshaller có kiểm soát; regression test XML theo XSD |
| Không gọi được operation sau upgrade | `@PayloadRoot`, WSDL `portType`/binding, SOAPAction, servlet mapping | Đối chiếu WSDL công bố và SOAP request bắt tại endpoint |
| SOAP Fault/WS-Security không tương thích | Fault resolver, interceptor, SOAP version, keystore, signature canonicalization | So sánh full SOAP envelope và kiểm thử tích hợp với đối tác |

Nếu thay đổi thực sự cần **phá tương thích XML**, phải quản lý như một phiên bản contract mới: định nghĩa namespace/endpoint hoặc chính sách versioning phù hợp, thông báo khách hàng tích hợp, chuẩn bị giai đoạn hỗ trợ song song và kế hoạch chuyển đổi client. Không để việc đổi XJC, JAXB provider hay plugin vô tình trở thành một thay đổi hợp đồng.

Một bản nâng cấp được xem là **đủ điều kiện chuyển bước kiểm thử/phát hành** khi:

- Có baseline và candidate truy xuất được từ build/commit rõ ràng; plugin sinh mã và thư viện runtime được khai báo nhất quán.
- Mọi thay đổi trong generated Java đã được phân loại; không còn thay đổi QName, dữ liệu hoặc ràng buộc schema ngoài phạm vi đã phê duyệt.
- WSDL/XSD công bố được kiểm tra, client và endpoint round-trip thành công, tất cả ca thử biên và Fault có kết quả.
- Interceptor XML validation, WS-Security, chứng chỉ, SOAP version, SOAPAction và attachment (nếu có) được kiểm chứng trên môi trường tích hợp.
- Có phương án quay về artifact/contract bản cũ khi đối tác phát hiện không tương thích; log chẩn đoán đủ để xác định lớp gây lỗi.

## 9. Bài tập áp dụng

Một hệ thống chạy Spring-WS cũ đang sinh model JAXB từ XSD và cung cấp operation `GetOrder`. Sau khi nâng cấp lên stack Jakarta, build báo thành công. Tuy nhiên, client nhận SOAP Fault do không tìm thấy phần tử `orderId` trong namespace `urn:example:orders:v1`.

Hãy thực hiện theo thứ tự:

1. Dùng XSD và SOAP request baseline xác nhận QName mong đợi của `GetOrderRequest` và `orderId`.
2. So sánh `package-info.java`, `ObjectFactory.java` và các annotation trong generated Java trước/sau.
3. Kiểm tra plugin XJC, binding `.xjb`, JAXB provider, `Jaxb2Marshaller` và cấu hình endpoint thực sự được tải.
4. Marshal cùng một đối tượng bằng bản cũ và mới; parse XML namespace-aware, validate theo XSD, xác minh điều gì gây khác biệt.
5. Sửa lớp gây lỗi, sinh lại mã, chạy lại endpoint/client tests và test với hệ thống đối tác.

**Kết quả mong đợi:** giải thích được nguyên nhân ở lớp codegen, binding hay runtime; chứng minh bằng XML/WSDL và test rằng bản nâng cấp giữ nguyên hợp đồng. Đây là tiêu chí đáng tin cậy hơn việc chỉ nhìn vào generated Java hoặc trạng thái build thành công.
