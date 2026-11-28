# Những package Java SE như javax.xml.transform vẫn giữ tên cũ

Khi nâng cấp ứng dụng Java từ thế hệ Java EE sang Jakarta EE, một trong các thay đổi dễ gây nhầm lẫn nhất là việc đổi namespace từ `javax.*` sang `jakarta.*`. Nhiều package enterprise đã chuyển tên, nhưng **không phải mọi package bắt đầu bằng `javax` đều được đổi**. Các API thuộc Java SE, trong đó có JAXP như `javax.xml.transform`, vẫn dùng namespace `javax.xml.*` ở các JDK hiện đại.

Điểm này quan trọng với ứng dụng tích hợp SOAP. Một dự án Spring-WS có thể đồng thời sử dụng Jakarta Servlet, Jakarta JAXB, JAXP của Java SE, DOM, SAX và StAX. Trong cùng một source file, các import `jakarta.xml.bind.*` và `javax.xml.transform.*` có thể hoàn toàn đúng và cần thiết. Cố thay thế hàng loạt mọi `javax` thành `jakarta` sẽ tạo import không tồn tại, lệch API type và lỗi biên dịch.

Bài **“Những package Java SE như javax.xml.transform vẫn giữ tên cũ”** thuộc chương **Nâng cấp và di chuyển** của module `SPRING_WEB_SERVICES`. Module học phát triển dịch vụ SOAP theo hướng contract-first với Spring Web Services, thiết kế XSD/WSDL, ánh xạ JAXB, xây dựng endpoint và SOAP client; xử lý SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích để tích hợp hệ thống doanh nghiệp.

Bài này giúp người nâng cấp phân biệt API Java SE và Jakarta EE, nhận diện nhóm XML APIs không đổi namespace, biết package nào cần migration, xử lý dependency/classpath và đọc lỗi compile/runtime đúng nguyên nhân. Ví dụ có Spring-WS 4.x, Spring Framework 6.x, Jakarta Servlet và Jakarta JAXB; phiên bản cụ thể phải đối chiếu với JDK, Spring Boot BOM và dependency đang dùng. `SPECIAL_NOTE` của bài được truyền rỗng.

## 1. Vì sao không thể thay thế mọi javax thành jakarta?

Jakarta EE 9 đổi namespace của nhiều API trước đây thuộc Java EE từ `javax.*` sang `jakarta.*`. Đây là một thay đổi package/API có ảnh hưởng source và binary compatibility: class được biên dịch tham chiếu `javax.servlet.Servlet` không phải cùng type với `jakarta.servlet.Servlet`, dù tên class sau khi bỏ prefix nhìn rất giống nhau.

Tuy nhiên, `javax` cũng là namespace lâu đời của Java SE. Oracle/JDK không đổi toàn bộ các API Java SE sang `jakarta.*`. Các API chuẩn thuộc nền tảng Java SE tiếp tục giữ tên cũ, ví dụ:

~~~java
import javax.xml.transform.Source;
import javax.xml.transform.Result;
import javax.xml.transform.Transformer;
import javax.xml.transform.TransformerFactory;
~~~

Đây là các type thuộc JAXP trong Java SE. Khi ứng dụng dùng Jakarta JAXB:

~~~java
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.bind.Marshaller;
import jakarta.xml.bind.Unmarshaller;
~~~

thì việc hai nhóm import cùng tồn tại là bình thường. Không có mâu thuẫn chỉ vì package đầu tiên bắt đầu bằng `javax`, nhóm còn lại bắt đầu bằng `jakarta`.

### 1.1. Ranh giới quan trọng là chủ sở hữu API, không phải prefix

Hãy phân loại theo nguồn gốc và specification:

| Nhóm API | Ví dụ package | Sau chuyển dịch Jakarta EE 9 |
| --- | --- | --- |
| Java SE / JAXP | `javax.xml.transform`, `javax.xml.parsers`, `javax.xml.validation` | **Giữ `javax.*`** |
| Java SE / XML processing | `org.w3c.dom`, `org.xml.sax`, `javax.xml.stream` | **Giữ nguyên** |
| Jakarta XML Binding (JAXB) | Trước đây `javax.xml.bind` | Chuyển thành `jakarta.xml.bind` |
| Jakarta XML Web Services (JAX-WS) | Trước đây `javax.xml.ws` | Chuyển thành `jakarta.xml.ws` |
| Jakarta Servlet | Trước đây `javax.servlet` | Chuyển thành `jakarta.servlet` |
| Jakarta Annotation | Trước đây `javax.annotation` (một phần API enterprise) | Các API Jakarta tương ứng dùng `jakarta.annotation` |
| Java SE / annotations hoặc APIs khác | Có package `javax` thuộc JDK | Không tự động đổi; kiểm tra API cụ thể |

Không nên xây rule dựa trên chuỗi prefix. Hãy xác định class thuộc Java SE, Jakarta EE hay thư viện bên thứ ba trước khi sửa import.

### 1.2. Hai class cùng tên đơn giản không phải cùng type

Ví dụ `Source`:

~~~java
javax.xml.transform.Source
~~~

là type JAXP của Java SE. `JAXBContext` trong Jakarta JAXB có thể thao tác qua các API XML processing thuộc Java SE, và Spring OXM/Spring-WS cũng dùng JAXP abstractions. Khi chuyển JAXB từ `javax.xml.bind` sang `jakarta.xml.bind`, `Source` không tự chuyển thành `jakarta.xml.transform.Source` vì package đó không phải API tương ứng được định nghĩa trong Java SE/Jakarta EE.

Đây là nguyên tắc cốt lõi: **API có thể được migrate mà type ở biên của nó vẫn tham chiếu một API Java SE giữ tên cũ**.

## 2. Các nhóm XML package cần nhận diện

### 2.1. JAXP: vẫn là javax.xml.*

Java API for XML Processing (JAXP) là bộ API Java SE cho việc parse, transform và validate XML. Các package thường gặp:

| Package | Thành phần tiêu biểu | Nhiệm vụ |
| --- | --- | --- |
| `javax.xml.transform` | `Source`, `Result`, `Transformer`, `TransformerFactory` | Biến đổi XML, XSLT và nguồn/kết quả transform. |
| `javax.xml.transform.dom` | `DOMSource`, `DOMResult` | Dùng DOM tree làm nguồn/kết quả. |
| `javax.xml.transform.sax` | `SAXSource`, `SAXResult` | Kết nối SAX events với transform. |
| `javax.xml.transform.stream` | `StreamSource`, `StreamResult` | Đọc/ghi XML từ stream, reader, writer hoặc system ID. |
| `javax.xml.parsers` | `DocumentBuilder`, `SAXParser`, factories | Tạo DOM/SAX parser. |
| `javax.xml.validation` | `Schema`, `SchemaFactory`, `Validator` | Validate XML theo XSD. |
| `javax.xml.xpath` | `XPath`, `XPathExpression` | Truy vấn XML bằng XPath. |
| `javax.xml.namespace` | `QName`, `NamespaceContext` | Biểu diễn tên XML có namespace. |
| `javax.xml.stream` | `XMLInputFactory`, `XMLStreamReader`, `XMLStreamWriter` | Streaming XML bằng StAX. |
| `javax.xml.datatype` | `XMLGregorianCalendar`, `DatatypeFactory` | Datatypes ánh xạ giữa XML Schema và Java. |
| `javax.xml.crypto` | XML Signature/Crypto interfaces | API cryptographic XML processing trong Java SE. |
| `org.w3c.dom` | `Document`, `Element`, `Node` | Mô hình DOM chuẩn. |
| `org.xml.sax` | `XMLReader`, `InputSource`, handlers | SAX parser/events. |

Các package trên không phải cùng một loại API ở mọi JDK distribution, nhưng chúng thuộc XML/JAXP APIs của Java SE và giữ namespace chuẩn. Đừng đổi chúng bằng một global replace.

### 2.2. JAXB và JAX-WS là nhóm đã chuyển

Một số API thường xuất hiện trong SOAP project cần phân biệt:

| API cũ trong thế hệ Java EE/JAXB/JAX-WS cũ | API ở thế hệ Jakarta tương ứng | Ghi chú |
| --- | --- | --- |
| `javax.xml.bind.JAXBContext` | `jakarta.xml.bind.JAXBContext` | JAXB API đã chuyển namespace. |
| `javax.xml.bind.annotation.XmlRootElement` | `jakarta.xml.bind.annotation.XmlRootElement` | Generated JAXB sources phải khớp runtime API. |
| `javax.xml.bind.JAXBException` | `jakarta.xml.bind.JAXBException` | Không trộn exception types. |
| `javax.xml.ws.Service` | `jakarta.xml.ws.Service` | JAX-WS API đã chuyển; không đồng nhất với Spring-WS. |
| `javax.jws.WebService` | `jakarta.jws.WebService` | API Jakarta Web Services Metadata tương ứng. |
| `javax.servlet.Servlet` | `jakarta.servlet.Servlet` | Spring Framework 6 / Boot 3 dùng Jakarta Servlet. |
| `javax.activation.DataHandler` (Java EE/JAF cũ) | `jakarta.activation.DataHandler` | Activation API đã tách khỏi JDK và chuyển namespace ở Jakarta. |

Spring-WS không phải JAX-WS. Spring-WS xây dựng trên message dispatcher, endpoint mapping, OXM/JAXB và `WebServiceTemplate`; việc dùng JAXB không biến endpoint Spring-WS thành JAX-WS service. Khi migration, phải kiểm tra đúng stack và không thêm JAX-WS API chỉ vì project là SOAP.

### 2.3. DOM, SAX, StAX không đổi namespace chỉ vì JAXB đổi

Các XML APIs nền tảng thường nằm ngay trên đường tích hợp:

~~~java
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.transform.Source;
import javax.xml.transform.Transformer;
import javax.xml.transform.TransformerFactory;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;
import javax.xml.namespace.QName;

import org.w3c.dom.Document;
import org.xml.sax.InputSource;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLStreamReader;
~~~

Đây là tập import hợp lệ trong một ứng dụng dùng Jakarta JAXB. DOM/SAX/StAX và JAXP là những nền tảng XML processing của Java SE; API JAXB dùng chúng hoặc tương tác với chúng qua bridge/adapter.

### 2.4. javax.activation và javax.annotation cần xét riêng

Có package từng được phân phối cùng Java EE hoặc từng nằm trong các JDK cũ nhưng không còn thuộc JDK hiện tại. Điều đó không có nghĩa mọi `javax.*` đã trở thành `jakarta.*` theo cùng một quy tắc.

- Activation API có namespace `jakarta.activation` ở thế hệ Jakarta tương ứng; cần dependency phù hợp nếu code dùng `DataHandler`, `DataSource` hoặc MTOM.
- Các package annotation có lịch sử khác nhau: `javax.annotation` từng có một phần API Java SE (`javax.annotation.processing`) và một phần Common Annotations/Java EE. `javax.annotation.processing` là Java SE và vẫn giữ tên; `jakarta.annotation` là API Jakarta tương ứng cho annotations enterprise.
- `javax.transaction`/`jakarta.transaction`, persistence và validation cũng phải phân loại theo specification; không suy từ chữ `javax`.

**Cùng một prefix không đồng nghĩa cùng lifecycle hoặc cùng artifact.** Kiểm tra package-level API owner và JDK/module trước khi migration.

## 3. Java/Jakarta package: phân loại theo API

### 3.1. JDK 8, JDK 11 và JDK hiện đại không đóng gói XML APIs giống nhau

Một nguồn gây nhầm lẫn khác là lịch sử đóng gói API trong JDK:

- JDK 8 từng bundle một số API Java EE/XML như JAXB, JAX-WS, SAAJ, Activation trong runtime distribution.
- Từ JDK 11, các module Java EE/CORBA đã bị loại khỏi JDK; ứng dụng cần dependency riêng nếu sử dụng JAXB, JAX-WS, SAAJ hoặc Activation.
- JAXP, DOM, SAX, StAX, XPath, XML validation và `javax.xml.transform` vẫn thuộc Java SE, được cung cấp bởi JDK.
- Việc phải thêm dependency JAXB sau khi nâng JDK không có nghĩa package JAXP cũng phải đổi sang Jakarta.

| API | Có sẵn trong JDK hiện đại? | Namespace cần xem xét |
| --- | --- | --- |
| JAXP / `javax.xml.transform` | Có, thuộc Java SE | Giữ `javax.xml.transform`. |
| DOM / `org.w3c.dom` | Có, thuộc Java SE | Giữ `org.w3c.dom`. |
| SAX / `org.xml.sax` | Có, thuộc Java SE | Giữ `org.xml.sax`. |
| StAX / `javax.xml.stream` | Có, thuộc Java SE | Giữ `javax.xml.stream`. |
| JAXB | Không bundle như JDK 8 | Chọn `javax.xml.bind` (JAXB 2.x) hoặc `jakarta.xml.bind` (Jakarta JAXB 3/4), theo stack. |
| JAX-WS | Không bundle như JDK 8 | Chọn API/runtime tương thích `javax` hoặc `jakarta`. |
| SAAJ | Không bundle như JDK 8 | Chọn `javax.xml.soap` hoặc `jakarta.xml.soap` theo thế hệ. |
| Jakarta Servlet | Không phải API Java SE | Dùng API servlet tương ứng container/framework; Boot 3 / Spring 6 dùng `jakarta.servlet`. |

Không dùng sự hiện diện của class trong JDK 8 để kết luận nó là Java SE. Hãy xác định module/specification owner.

### 3.2. javax.xml.soap không giống javax.xml.transform

Tên package nhìn gần nhau nhưng lifecycle khác:

~~~java
javax.xml.transform.Source
javax.xml.soap.SOAPMessage
javax.xml.bind.JAXBContext
~~~

- `javax.xml.transform.Source`: JAXP / Java SE, tiếp tục giữ namespace.
- `javax.xml.soap.SOAPMessage`: SAAJ API, trước đây thuộc Java EE; thế hệ Jakarta tương ứng dùng `jakarta.xml.soap.SOAPMessage`.
- `javax.xml.bind.JAXBContext`: JAXB API cũ; Jakarta JAXB dùng `jakarta.xml.bind.JAXBContext`.

Không thể suy từ `javax.xml` rằng tất cả type ở dưới đều thuộc JAXP. Cần kiểm tra từng subpackage và specification. Đặc biệt, `javax.xml.soap` và `javax.xml.bind` là những trường hợp thường khiến migration thiếu dependency hoặc trộn thế hệ API.

### 3.3. Spring-WS khác JAX-WS

Hai công nghệ đều xử lý SOAP nhưng khác programming model:

| Chủ đề | Spring Web Services | JAX-WS |
| --- | --- | --- |
| Endpoint programming | `@Endpoint`, `@PayloadRoot`, message handling | `@WebService`, generated/service endpoint APIs |
| Client | `WebServiceTemplate` | `Service` / generated port |
| JAXB | Thường dùng qua Spring OXM | Là binding model tiêu chuẩn trong nhiều JAX-WS stacks |
| Servlet integration | Spring-WS `MessageDispatcherServlet` | Container/JAX-WS runtime-specific |
| API migration | Spring-WS/Spring Framework version và OXM dependency | JAX-WS API/runtime package generation (`javax` hoặc `jakarta`) |

Một dự án Spring-WS không cần import `jakarta.xml.ws.Service` chỉ để tạo SOAP client. Nếu code thật sự dùng JAX-WS generated stubs, đó là dependency riêng cần kiểm tra.

## 4. Code có thể dùng Jakarta JAXB và Java SE JAXP cùng lúc

### 4.1. Ví dụ Source và DOMSource

Một method có thể nhận XML source từ JAXP:

~~~java
import javax.xml.transform.Source;
import javax.xml.transform.dom.DOMSource;
import javax.xml.transform.stream.StreamSource;

import org.w3c.dom.Document;

public final class XmlSources {

    private XmlSources() {
    }

    public static Source fromDocument(Document document) {
        return new DOMSource(document);
    }

    public static Source fromReader(java.io.Reader reader) {
        return new StreamSource(reader);
    }
}
~~~

Ở đây không có API Jakarta nào bị bỏ sót. `Source`, `DOMSource` và `StreamSource` tiếp tục thuộc JAXP. Nếu một method khác dùng Jakarta JAXB để marshal object vào một `Result`, type `Result` vẫn là `javax.xml.transform.Result`.

### 4.2. Ví dụ JAXB context hiện đại và JAXP Source

~~~java
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.bind.Unmarshaller;

import javax.xml.transform.Source;
import javax.xml.transform.stream.StreamSource;

import java.io.Reader;

public final class OrderXmlReader {

    private final JAXBContext context;

    public OrderXmlReader(JAXBContext context) {
        this.context = context;
    }

    public Object read(Reader reader) throws Exception {
        Unmarshaller unmarshaller =
            context.createUnmarshaller();

        Source source = new StreamSource(reader);
        return unmarshaller.unmarshal(source);
    }
}
~~~

Đây là minh họa cho project dùng Jakarta JAXB runtime tương thích. `Source` được cung cấp bởi Java SE; `JAXBContext` và `Unmarshaller` thuộc Jakarta JAXB. Các API cùng tồn tại vì chúng có ownership khác nhau. Trong ứng dụng thực tế, hãy dùng typed JAXB object hoặc `JAXBElement<T>` thay vì trả `Object`, và cấu hình schema validation/security phù hợp.

### 4.3. Spring-WS WebServiceMessage và Transformer

Spring-WS/OXM có các API làm việc với `Source` và `Result`. Khi đọc code hoặc nâng cấp dependency, một method nhận `javax.xml.transform.Source` không phải dấu hiệu dự án còn dùng JAXB cũ.

~~~java
import javax.xml.transform.Source;
import javax.xml.transform.Result;

public interface XmlExchange {
    void writeResponse(Result target);
    Source readRequest();
}
~~~

Đây là JAXP boundary. Một implementation có thể sử dụng Jakarta JAXB ở phía sau để marshal/unmarshal, trong khi vẫn nhận/trả `javax.xml.transform` types. Không tạo một lớp `jakarta.xml.transform.Source` giả để “đồng bộ namespace”.

### 4.4. Package import không tự cho biết runtime implementation

JAXP API được gọi qua factory abstractions như `TransformerFactory`, `DocumentBuilderFactory`, `SchemaFactory` và `XMLInputFactory`. Runtime implementation có thể đến từ JDK hoặc provider được cài thêm và chọn thông qua provider discovery/configuration. Vì vậy hai môi trường cùng compile nhưng có thể có hành vi transform/validation khác nếu provider khác.

Khi migration, kiểm tra:

- API class được load từ module/JDK nào.
- Provider implementation thực tế mà `Factory.newInstance()` trả về.
- Các system properties/service provider configuration có thay đổi?
- XML parser secure-processing/XXE settings có được giữ?
- XSLT extension functions hoặc external document access có phụ thuộc provider?
- Schema resolver/catalog có còn resolve import như trước?

Nâng version JAXB không tự nâng provider JAXP, và đổi Spring không bảo đảm mọi parser behavior giống hệt.

## 5. Dependency graph và classpath: tránh trộn thế hệ API

### 5.1. Không đặt cả JAXB cũ và Jakarta JAXB vào cùng đường xử lý

Hai API này có class names gần nhau nhưng type identity khác:

~~~java
javax.xml.bind.JAXBContext
jakarta.xml.bind.JAXBContext
~~~

Không thể truyền một `javax.xml.bind.JAXBContext` vào method đòi `jakarta.xml.bind.JAXBContext`. Code generated từ JAXB 2.x (imports `javax.xml.bind.annotation.*`) không chạy với runtime JAXB 3/4 chỉ bằng cách thêm dependency; package mismatch vẫn tồn tại.

| Thành phần | JAXB cũ | Jakarta JAXB |
| --- | --- | --- |
| API import | `javax.xml.bind.*` | `jakarta.xml.bind.*` |
| Annotations generated | `javax.xml.bind.annotation.*` | `jakarta.xml.bind.annotation.*` |
| Runtime implementation | JAXB 2.x-compatible | Jakarta JAXB 3.x/4.x-compatible |
| XJC/codegen | Toolchain phát sinh `javax` | Toolchain phát sinh `jakarta` |
| Spring OXM | Spring version tương thích stack cũ | Spring Framework 6+ / OXM version tương thích Jakarta |

Đừng chỉ nâng runtime jar rồi kỳ vọng generated code đổi namespace. Cần chọn generator/binding tool phù hợp và generate lại từ cùng WSDL/XSD contract nếu quyết định migrate JAXB namespace.

### 5.2. Tránh kéo hai API thế hệ qua dependency transitive

Một thư viện cũ có thể kéo JAXB 2.x trong khi ứng dụng chính dùng Jakarta JAXB. Hãy xem dependency tree và xác định:

- Ai cung cấp `javax.xml.bind` API?
- Ai cung cấp `jakarta.xml.bind` API?
- Có nhiều version của activation/istack/SAAJ/JAX-WS không?
- Có code generated từ tool khác version không?
- Có thư viện dùng reflection theo class name cũ không?
- Runtime provider/service loader đang chọn implementation nào?

Hai namespace có thể cùng tồn tại ở JVM, nhưng cùng tồn tại không có nghĩa chúng tương thích với nhau. Hãy tránh để một message đi vào pipeline dùng JAXB API khác thế hệ mà không có adapter rõ ràng.

### 5.3. Kiểm tra jar contents và nguồn class

Với một lỗi type không rõ, kiểm tra artifact:

~~~text
javax/xml/transform/Source.class
javax/xml/bind/JAXBContext.class
jakarta/xml/bind/JAXBContext.class
~~~

`javax/xml/transform/Source.class` thường đến từ module Java SE `java.xml`, không phải dependency JAXB. Còn `javax.xml.bind` có thể không tồn tại trong JDK hiện đại và cần artifact JAXB 2.x; `jakarta.xml.bind` cần API Jakarta phù hợp.

Trong runtime có thể kiểm tra nguồn class:

~~~java
System.out.println(
    javax.xml.transform.Source.class
        .getProtectionDomain()
        .getCodeSource());

System.out.println(
    jakarta.xml.bind.JAXBContext.class
        .getProtectionDomain()
        .getCodeSource());
~~~

`CodeSource` có thể là `null` với class được load từ module/bootstrap. Đây là thông tin chẩn đoán, không phải điều kiện duy nhất để kết luận classpath đúng.

### 5.4. JPMS và module ownership

Trên Java Platform Module System, JAXP APIs thuộc module `java.xml`. Việc source code import `javax.xml.transform` không yêu cầu thêm dependency bên ngoài nếu đang compile với JDK phù hợp. Ứng dụng modular có thể khai báo:

~~~java
module com.example.orders.soap {
    requires java.xml;
    requires jakarta.xml.bind;
}
~~~

Đây chỉ là ví dụ khái niệm: tên module thực tế phụ thuộc API/runtime JAXB được chọn, và dự án Spring Boot/classpath thông thường có thể không dùng module-info.java. Không copy nguyên module declaration nếu module name của dependency khác.

### 5.5. Dependency cũ cung cấp XML parser không đồng nghĩa phải loại ngay

Một ứng dụng có thể có Xerces, Xalan hoặc provider XML khác được thêm để hỗ trợ behavior/feature cụ thể. Trước khi loại bỏ:

- Xác định provider nào đang được chọn.
- Chạy regression test với XML, XSLT, XSD và signature fixtures.
- Kiểm tra external entity, secure processing và resolver config.
- Đảm bảo provider version hỗ trợ JDK đang nâng.
- Xóa duplicate parser chỉ khi chứng minh không còn consumer phụ thuộc.

Không tự thêm implementation XML parser mới chỉ vì thấy `javax.xml.*` trong import.

## 6. Cách xử lý import khi nâng Spring Framework và Spring-WS

### 6.1. Spring Framework 6 chuyển sang Jakarta EE APIs

Spring Framework 6 chuyển integration Servlet/JAXB/Jakarta APIs sang thế hệ Jakarta tương thích và yêu cầu baseline JDK mới hơn so với Spring Framework 5. Trong một migration Spring Boot 2 → 3, những import liên quan đến Servlet, JAXB, Validation, Persistence hoặc Annotation Jakarta có thể phải chuyển.

Nhưng import JAXP của Java SE không cần thay:

~~~java
// Jakarta APIs ở stack mới
import jakarta.servlet.http.HttpServletRequest;
import jakarta.xml.bind.JAXBContext;

// Java SE XML APIs, tiếp tục giữ namespace
import javax.xml.transform.Source;
import javax.xml.transform.TransformerFactory;
import javax.xml.validation.Schema;
import javax.xml.parsers.DocumentBuilderFactory;
~~~

Một source file có cả jakarta.* và javax.xml.* có thể là trạng thái đúng sau migration. Đừng dùng số lượng chữ javax còn lại làm thước đo migration hoàn tất.

### 6.2. Spring-WS endpoint/servlet và JAXP boundary

Với Spring-WS trên Jakarta Servlet stack, một cấu hình servlet có thể dùng:

~~~java
import jakarta.servlet.ServletContext;
import org.springframework.ws.transport.http.MessageDispatcherServlet;

public final class SoapServletSetup {

    public void register(ServletContext servletContext) {
        MessageDispatcherServlet servlet =
            new MessageDispatcherServlet();

        var registration = servletContext.addServlet(
            "messageDispatcher", servlet);

        registration.setLoadOnStartup(1);
        registration.addMapping("/ws/*");
    }
}
~~~

`ServletContext` là Jakarta Servlet. Nếu cùng project xử lý XML bằng Transformer/Source, những type đó vẫn thuộc `javax.xml.transform`. Migration Servlet và migration JAXP không phải cùng việc.

### 6.3. JAXB generated sources cần được xem là artifact có version

Nếu generated classes được tạo từ schema bằng JAXB 2.x, file có thể chứa:

~~~java
import javax.xml.bind.annotation.XmlType;
import javax.xml.bind.annotation.XmlElement;
~~~

Khi project chuyển sang Jakarta JAXB, generator phải phát ra:

~~~java
import jakarta.xml.bind.annotation.XmlType;
import jakarta.xml.bind.annotation.XmlElement;
~~~

Điều đó không yêu cầu sửa các imports `javax.xml.transform` trong code xử lý XML. Cũng không nên tìm-thay trong toàn bộ thư mục generated mà không regenerate từ đúng XSD và toolchain.

### 6.4. Một quy tắc migration hữu ích cho code review

Với mỗi import bị sửa, PR nên chỉ ra:

1. Import thuộc API nào/specification nào?
2. API đó có chuyển package trong Jakarta EE 9+ không?
3. Code đang dùng API version nào và runtime nào cung cấp nó?
4. Generated code có được tạo lại từ XSD/WSDL không?
5. Có public method/signature nào đổi type làm ảnh hưởng consumer?
6. Tests nào chứng minh boundary JAXP/JAXB/Servlet vẫn hoạt động?

Nếu câu trả lời duy nhất là “tên package bắt đầu bằng javax”, thay đổi đó chưa có cơ sở.

## 7. XML security và provider behavior trong quá trình nâng cấp

Việc giữ namespace `javax.xml.transform` không có nghĩa mọi behavior XML giữ nguyên giữa các JDK/provider. JAXP API có thể được triển khai bởi provider khác nhau; parser defaults, XSLT capabilities, entity resolution và secure-processing behavior có thể thay đổi theo JDK hoặc implementation.

### 7.1. Cấu hình parser an toàn vẫn quan trọng sau migration

Ví dụ tạo DOM parser với cấu hình hạn chế external entities:

~~~java
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;

public final class SecureXmlFactories {

    private SecureXmlFactories() {
    }

    public static DocumentBuilderFactory newDocumentBuilderFactory()
            throws Exception {
        DocumentBuilderFactory factory =
            DocumentBuilderFactory.newInstance();

        factory.setNamespaceAware(true);
        factory.setFeature(
            XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setFeature(
            "http://apache.org/xml/features/disallow-doctype-decl",
            true);
        factory.setFeature(
            "http://xml.org/sax/features/external-general-entities",
            false);
        factory.setFeature(
            "http://xml.org/sax/features/external-parameter-entities",
            false);
        factory.setXIncludeAware(false);
        factory.setExpandEntityReferences(false);

        return factory;
    }
}
~~~

Đây là cấu hình minh họa cho parser/provider hỗ trợ các features đã nêu. Nếu provider không hỗ trợ một feature, việc bật có thể ném exception; hãy fail closed theo policy và kiểm thử trên runtime production. Chỉ tắt một feature không đảm bảo đầy đủ mọi XXE/XML bomb protections.

### 7.2. External access restrictions cho JAXP

Một số JAXP factories/validators hỗ trợ thuộc tính external access:

~~~java
import javax.xml.XMLConstants;
import javax.xml.validation.SchemaFactory;

SchemaFactory schemaFactory =
    SchemaFactory.newInstance(XMLConstants.W3C_XML_SCHEMA_NS_URI);

schemaFactory.setProperty(
    XMLConstants.ACCESS_EXTERNAL_DTD, "");
schemaFactory.setProperty(
    XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
~~~

Tùy use case, schema import hợp lệ có thể cần catalog hoặc custom resolver được allowlist. Không bật external schema/DTD fetch không giới hạn chỉ để làm test pass; pin schema dependencies và chỉ cấp quyền truy cập những nguồn đã duyệt.

### 7.3. TransformerFactory và XSLT

Nếu hệ thống dùng XSLT, cần xem xét việc cho phép stylesheet truy cập ngoài:

~~~java
import javax.xml.XMLConstants;
import javax.xml.transform.TransformerFactory;

TransformerFactory factory =
    TransformerFactory.newInstance();

factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_STYLESHEET, "");
~~~

Provider có thể khác nhau về hỗ trợ thuộc tính/feature. Nếu cần include/import stylesheet nội bộ, dùng resolver có allowlist thay vì mở external access toàn cục. Regression tests nên bao gồm cả stylesheet hợp lệ, import đã duyệt và payload có DOCTYPE/external entity.

### 7.4. JAXP provider selection là một phần runtime compatibility

Khi nâng JDK hoặc thay parser dependency:

- Ghi lại class name của `DocumentBuilderFactory`, `TransformerFactory`, `SchemaFactory`, `XMLInputFactory`.
- Chạy tests trên đúng JDK/container image được deploy.
- Kiểm tra service provider files và module/classloader order.
- Xác minh XML catalog/resolver, XSLT extensions và schema imports.
- Kiểm tra secure-processing flags và external-access properties.
- Không giả định parser behavior chỉ dựa vào source imports.

JAXP namespace vẫn là `javax`, nhưng implementation/provider có thể đổi. Đây là lý do cần test behavior thay vì chỉ tìm kiếm import.

## 8. Migration recipe: nâng cấp Spring-WS mà không đổi nhầm JAXP

### 8.1. Chụp dependency baseline

Trước khi sửa, ghi nhận:

- JDK source/target/release đang dùng.
- Spring Boot và Spring Framework versions.
- Spring-WS và Spring OXM versions.
- JAXB API/runtime/XJC versions và namespace generated sources.
- Servlet container và Servlet API generation.
- SAAJ/JAX-WS/Activation usage nếu có.
- XML parser/transformer providers và overrides.
- Contract WSDL/XSD version, imports và security policy.

Không thêm một dependency chỉ vì thấy `javax` trong source. Xác định compile error/runtime error đến từ API nào trước.

### 8.2. Phân loại import bằng bảng migration

| Import hiện tại | Hành động khi chuyển Spring 5/Boot 2 sang Spring 6/Boot 3 |
| --- | --- |
| `javax.servlet.*` | Xem xét đổi sang `jakarta.servlet.*`. |
| `javax.xml.bind.*` | Chuyển sang `jakarta.xml.bind.*` nếu target stack dùng Jakarta JAXB; regenerate bindings. |
| `javax.xml.ws.*` | Chuyển API/runtime JAX-WS sang Jakarta generation nếu tiếp tục dùng JAX-WS. |
| `javax.xml.soap.*` | Chuyển SAAJ sang Jakarta generation tương thích nếu stack sử dụng SAAJ. |
| `javax.activation.*` | Xem xét `jakarta.activation.*` theo dependency/runtime và MTOM usage. |
| `javax.xml.transform.*` | **Giữ nguyên. Đây là JAXP Java SE.** |
| `javax.xml.parsers.*` | **Giữ nguyên. Đây là JAXP Java SE.** |
| `javax.xml.validation.*` | **Giữ nguyên. Đây là JAXP Java SE.** |
| `javax.xml.xpath.*` | **Giữ nguyên. Đây là Java SE.** |
| `javax.xml.stream.*` | **Giữ nguyên. Đây là StAX Java SE.** |
| `javax.xml.namespace.*` | **Giữ nguyên. Đây là Java SE.** |
| `org.w3c.dom.*`, `org.xml.sax.*` | **Giữ nguyên. Đây là XML processing APIs.** |
| `javax.annotation.processing.*` | **Giữ nguyên. Đây là Java SE compiler API.** |
| `javax.annotation.*` | Xét từng API: Common Annotations enterprise có Jakarta counterpart; không áp dụng global replacement. |

Bảng này là hướng dẫn phân loại, không phải danh sách thay thế tự động. Một số thư viện có compatibility bridge hoặc version riêng; quyết định cuối phải dựa trên dependency mà target framework thực sự hỗ trợ.

### 8.3. Thứ tự migration khuyến nghị

1. Nâng build JDK/toolchain và xác định source compatibility.
2. Nâng Spring Boot/Spring Framework theo release train tương thích.
3. Nâng Spring-WS/OXM theo matrix tương ứng.
4. Quyết định JAXB namespace/runtime (JAXB 2 `javax` hay Jakarta JAXB 3/4).
5. Chạy XJC/codegen bằng toolchain đúng namespace và regenerate sources.
6. Chuyển các Jakarta EE imports bắt buộc như Servlet/JAXB/SAAJ/Activation.
7. Giữ lại JAXP/DOM/SAX/StAX Java SE imports.
8. Loại bỏ dependency duplicate/incompatible sau khi kiểm tra dependency graph.
9. Chạy tests compile, marshal/unmarshal, XSD validation và SOAP integration.
10. Triển khai staging, quan sát parser/provider/security behavior rồi mới production.

Không gộp mọi bước vào một thay đổi không thể review. Tách build/runtime migration, generated-code migration và application source migration giúp xác định lỗi chính xác hơn.

### 8.4. Spring-WS endpoint/servlet và JAXP boundary

Với Spring-WS trên Jakarta Servlet stack, một cấu hình servlet có thể dùng:

~~~java
import jakarta.servlet.ServletContext;
import org.springframework.ws.transport.http.MessageDispatcherServlet;

public final class SoapServletSetup {

    public void register(ServletContext servletContext) {
        MessageDispatcherServlet servlet =
            new MessageDispatcherServlet();

        var registration = servletContext.addServlet(
            "messageDispatcher", servlet);

        registration.setLoadOnStartup(1);
        registration.addMapping("/ws/*");
    }
}
~~~

`ServletContext` là Jakarta Servlet. Nếu cùng project xử lý XML bằng Transformer/Source, những type đó vẫn thuộc `javax.xml.transform`. Migration Servlet và migration JAXP không phải cùng việc.

### 8.5. JAXB generated sources cần được xem là artifact có version

Nếu generated classes được tạo từ schema bằng JAXB 2.x, file có thể chứa:

~~~java
import javax.xml.bind.annotation.XmlType;
import javax.xml.bind.annotation.XmlElement;
~~~

Khi project chuyển sang Jakarta JAXB, generator phải phát ra:

~~~java
import jakarta.xml.bind.annotation.XmlType;
import jakarta.xml.bind.annotation.XmlElement;
~~~

Điều đó không yêu cầu sửa các imports `javax.xml.transform` trong code xử lý XML. Cũng không nên tìm-thay trong toàn bộ thư mục generated mà không regenerate từ đúng XSD và toolchain.

### 8.6. Quy tắc migration hữu ích cho code review

Với mỗi import bị sửa, PR nên chỉ ra:

1. Import thuộc API nào/specification nào?
2. API đó có chuyển package trong Jakarta EE 9+ không?
3. Code đang dùng API version nào và runtime nào cung cấp nó?
4. Generated code có được tạo lại từ XSD/WSDL không?
5. Có public method/signature nào đổi type làm ảnh hưởng consumer?
6. Tests nào chứng minh boundary JAXP/JAXB/Servlet vẫn hoạt động?

Nếu câu trả lời duy nhất là “tên package bắt đầu bằng javax”, thay đổi đó chưa có cơ sở.

## 9. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách sửa đúng |
| --- | --- | --- |
| Package jakarta.xml.transform không tồn tại | Đã đổi JAXP import theo global replacement. | Đưa import về javax.xml.transform. |
| Package javax.xml.bind không tồn tại trên JDK hiện đại | JAXB không còn bundle trong JDK như trước. | Thêm đúng JAXB API/runtime thế hệ cần dùng hoặc migrate sang Jakarta JAXB. |
| ClassCastException giữa hai JAXB types | Trộn generated code javax và runtime jakarta hoặc ngược lại. | Đồng bộ generator, API, runtime và generated packages. |
| NoClassDefFoundError: jakarta/xml/bind | Jakarta JAXB API/runtime thiếu hoặc version mismatch. | Kiểm tra dependency graph và OXM compatibility. |
| NoSuchMethodError trong JAXB provider | API/runtime/provider khác version hoặc duplicate jars. | Chỉ giữ một dependency set tương thích. |
| Servlet initialization lỗi type | Spring 6 nhận Jakarta Servlet nhưng container/adapter còn javax generation. | Nâng container và servlet dependencies đồng bộ. |
| SOAP attachment lỗi DataHandler | Activation API namespace/runtime không khớp. | Chọn Activation API/runtime đúng thế hệ và test MTOM. |
| XSD validation đột nhiên cho kết quả khác | JAXP provider/JDK/schema resolver thay đổi. | Kiểm tra factory implementation, resolver, schema closure và fixtures. |
| XSLT bị chặn external stylesheet | Secure processing/external access restrictions hoặc provider mới. | Allowlist resolver/import hợp lệ và test secure configuration; không mở vô điều kiện. |
| Compile được nhưng endpoint không chạy | Runtime classloader/provider hoặc servlet generation khác compile classpath. | Kiểm tra packaged artifact và environment thực tế. |
| Generated JAXB sources vẫn import javax | XJC cũ tiếp tục được dùng. | Chọn codegen Jakarta và regenerate từ contract. |
| Tìm-thay làm đổi javax.xml.transform | Migration dựa prefix thay vì API ownership. | Revert phần JAXP, phân loại theo specification. |

Lỗi type ở tầng Spring không nhất thiết liên quan JAXP. Hãy đọc package đầy đủ trong compiler/runtime error, xác định classloader và artifact cung cấp class đó rồi mới sửa.

## 10. Test matrix cho migration

Nâng cấp chỉ hoàn thành khi build và runtime cùng dùng đúng thế hệ API. Bộ kiểm tra cần bao gồm:

| Kiểm thử | Bằng chứng mong đợi |
| --- | --- |
| Compile main source | javax.xml.transform, DOM/SAX/StAX imports vẫn resolve bằng JDK. |
| Compile Jakarta integration | Servlet/JAXB/SAAJ imports resolve đúng API generation. |
| Generated code | JAXB annotations/package khớp runtime JAXB đã chọn. |
| JAXB marshal/unmarshal | Request/response fixtures serialize và parse đúng namespace/schema. |
| JAXP transform | Source, Result, XSLT transform hoạt động trên provider mục tiêu. |
| XSD validation | Valid/invalid fixtures có kết quả như contract mong đợi. |
| Parser security | DOCTYPE/external entities bị xử lý theo policy; import schema hợp lệ vẫn hoạt động qua resolver allowlist. |
| SOAP endpoint | Spring-WS dispatcher/endpoint khởi tạo trên Jakarta Servlet container. |
| SOAP client | WebServiceTemplate gửi và nhận message đúng; fault mapping không regress. |
| MTOM/SAAJ | Attachment path dùng đúng Activation/SAAJ generation nếu project có sử dụng. |
| Runtime packaging | Không thiếu API/provider; không nạp nhầm version trong container. |
| Regression | Contract WSDL/XSD và SOAP wire behavior giữ nguyên trừ thay đổi đã chủ đích. |

### 10.1. Test đơn giản xác nhận JAXP vẫn đến từ Java SE

Một smoke test có thể tạo TransformerFactory và chạy transform với source/result trong bộ nhớ:

~~~java
import java.io.StringReader;
import java.io.StringWriter;

import javax.xml.transform.Transformer;
import javax.xml.transform.TransformerFactory;
import javax.xml.transform.stream.StreamResult;
import javax.xml.transform.stream.StreamSource;

public final class JaxpSmokeTest {

    public static void main(String[] args) throws Exception {
        String xml = "<order><id>42</id></order>";

        Transformer transformer =
            TransformerFactory.newInstance().newTransformer();

        StringWriter output = new StringWriter();
        transformer.transform(
            new StreamSource(new StringReader(xml)),
            new StreamResult(output));

        if (!output.toString().contains("<id>42</id>")) {
            throw new IllegalStateException("Unexpected XML output");
        }
    }
}
~~~

Test này không chứng minh toàn bộ XML security hoặc SOAP integration, nhưng xác nhận JAXP core API vẫn hoạt động sau khi thay dependency/framework.

### 10.2. Test class availability và namespace tách biệt

Có thể assert API types được load:

~~~java
import javax.xml.transform.Source;
import javax.xml.parsers.DocumentBuilderFactory;

import jakarta.xml.bind.JAXBContext;
import jakarta.servlet.Servlet;

public final class ApiNamespaceSmokeTest {

    public static void main(String[] args) throws Exception {
        Class.forName(Source.class.getName());
        Class.forName(DocumentBuilderFactory.class.getName());
        Class.forName(JAXBContext.class.getName());
        Class.forName(Servlet.class.getName());
    }
}
~~~

Test này chỉ phù hợp với ứng dụng đã chọn Jakarta JAXB/Servlet stack. Nếu dự án chủ ý giữ legacy JAXB/Servlet, dùng class names/runtime của thế hệ đó. Điểm cần xác nhận là JAXP classes vẫn ở Java SE trong cả hai trường hợp.

### 10.3. Chạy trong môi trường deploy thật

- Test bằng JDK distribution/container image giống production.
- Chạy packaged application, không chỉ IDE classpath.
- Kiểm tra embedded servlet container và external application server nếu có.
- Kiểm tra provider XML factory trên runtime classloader.
- Xem log startup để phát hiện duplicate APIs hoặc provider selection khác.
- Chạy SOAP integration test qua endpoint thực và xác nhận WSDL/XSD contract.

## 11. Checklist review migration

| Câu hỏi | Điều kiện đạt |
| --- | --- |
| API ownership đã được xác định? | Mọi package được phân loại Java SE, Jakarta EE hoặc third-party. |
| JAXP có bị thay sai không? | javax.xml.transform, parsers, validation, XPath, StAX giữ nguyên. |
| JAXB generation nhất quán? | API/runtime/XJC/generated annotations cùng thế hệ. |
| Servlet/Jakarta APIs khớp? | Spring Framework, Boot, container và servlet API cùng generation. |
| SAAJ/Activation có dùng không? | Dependency/runtime namespace đúng nếu ứng dụng thực sự cần. |
| Dependency graph sạch? | Không có duplicate/incompatible APIs hoặc providers ngoài chủ đích. |
| JDK module assumptions chính xác? | JAXP lấy từ java.xml; JAXB/JAX-WS không giả định còn bundle trong JDK mới. |
| XML provider được kiểm tra? | Transformer/parser/schema factories trên runtime đúng như mong đợi. |
| XML security giữ nguyên? | XXE, external access, XSLT và resolver policy có test. |
| SOAP contract giữ nguyên? | WSDL/XSD, QName, SOAPAction, Fault và WS-Security không đổi ngoài ý định. |
| Tests qua packaged runtime? | Compile, JAXB, JAXP, endpoint, client và MTOM tests đạt. |
| PR giải thích import changes? | Mỗi namespace replacement có lý do theo API/specification. |

## 12. Tài liệu tham khảo và nguyên tắc áp dụng

- **Oracle Java SE API — [javax.xml.transform package](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/transform/package-summary.html)**: API JAXP transform thuộc module java.xml.
- **Oracle Java SE API — [java.xml module](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/module-summary.html)**: DOM, SAX, StAX, JAXP, XPath, validation và XML processing packages trong Java SE.
- **Oracle Java SE API — [javax.xml.parsers](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/parsers/package-summary.html)** và **[javax.xml.validation](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/validation/package-summary.html)**: parser và schema validation APIs.
- **Jakarta EE — [Jakarta EE 9 Release](https://jakarta.ee/specifications/platform/9/)**: namespace transition và các specification Jakarta EE.
- **Jakarta XML Binding — [Jakarta XML Binding 4.0](https://jakarta.ee/specifications/xml-binding/4.0/)**: JAXB API ở namespace jakarta.xml.bind.
- **Spring Framework — [Spring Framework 6.x migration guide](https://github.com/spring-projects/spring-framework/wiki/What's-New-in-Spring-Framework-6.x)**: Java/Jakarta baseline và package migration.
- **Spring Web Services — [Reference Documentation 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/)**: Spring-WS endpoint, OXM, message processing và integration.
- **OWASP — [XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html)**: cấu hình parser và phòng XXE.

Tài liệu API phải được đối chiếu với JDK/framework version thực tế. Các mapping trong bài mô tả ranh giới specification; BOM và dependency management của ứng dụng quyết định version artifact cụ thể. Đừng dùng tài liệu JAXB 4 để kết luận behavior của JAXB 2 hoặc dùng Spring 6 docs để cấu hình Spring 5.

### Ghi nhớ

- **Không phải mọi javax.* đều chuyển thành jakarta.*.** Prefix không cho biết API owner.
- JAXP như javax.xml.transform, javax.xml.parsers, javax.xml.validation, javax.xml.xpath, javax.xml.stream, javax.xml.namespace cùng DOM/SAX là XML processing APIs của Java SE và giữ namespace.
- JAXB, JAX-WS, SAAJ, Servlet và các API Jakarta enterprise tương ứng có namespace/version riêng; phải chọn đồng bộ API, runtime, generator và container.
- javax.xml.soap không phải javax.xml.transform. Phân loại theo subpackage/specification, không suy từ prefix gần giống.
- Generated JAXB source từ JAXB 2 thường tham chiếu javax.xml.bind; Jakarta JAXB 3/4 dùng jakarta.xml.bind. Regenerate bằng toolchain đúng thay vì global replace.
- JAXP namespace có thể không đổi trong khi provider/parser behavior đổi theo JDK hoặc classpath. Kiểm tra TransformerFactory, parser, schema resolver và XML security.
- Migration hoàn tất khi compile, runtime, SOAP endpoint/client, JAXB, JAXP, MTOM và security tests cùng đạt trên môi trường triển khai mục tiêu.






