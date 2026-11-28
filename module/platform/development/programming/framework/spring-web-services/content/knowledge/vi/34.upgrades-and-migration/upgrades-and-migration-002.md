# Chuyển javax sang jakarta cho JAXB, SAAJ và Activation đúng phạm vi

> **Chương:** Nâng cấp và di chuyển  
> **Module:** SPRING_WEB_SERVICES — phát triển dịch vụ SOAP theo hướng contract-first với Spring Web Services, thiết kế XSD/WSDL, ánh xạ JAXB và xây dựng endpoint cùng SOAP client; xử lý SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích trong tích hợp doanh nghiệp ổn định.

## 1. Vì sao migration javax sang jakarta cần có phạm vi rõ?

Khi nâng cấp hệ sinh thái Spring lên thế hệ dựa trên Jakarta EE 9+, nhiều API enterprise chuyển package Java từ namespace javax.* sang jakarta.*. Với ứng dụng SOAP/Spring-WS, những khu vực thường chịu tác động gồm JAXB, SAAJ và Activation:

- JAXB: javax.xml.bind chuyển sang jakarta.xml.bind.
- SAAJ: javax.xml.soap chuyển sang jakarta.xml.soap.
- Activation: javax.activation chuyển sang jakarta.activation.

Tuy nhiên, không phải mọi package bắt đầu bằng javax đều thuộc Jakarta EE và phải đổi. Nhiều API XML là Java SE APIs, vẫn giữ package javax.xml.*. Ví dụ QName, XML parsers, DOM, SAX, StAX và XML transformation vẫn có package cũ. XSD/WSDL namespaces cũng là URI trong tài liệu XML, không phải Java package names.

Một phép thay thế toàn cục có thể phá source code, làm lỗi dependency resolution hoặc thay nhầm API của JDK. Ngược lại, chỉ đổi imports mà giữ runtime implementation cũ có thể gây NoSuchMethodError, ClassCastException hoặc provider discovery failure.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt các package Java EE/Jakarta đã đổi với API Java SE giữ nguyên.
2. Xác định ranh giới tương thích giữa Spring Boot, Spring Framework và Spring-WS.
3. Chuyển imports, annotations và JAXB model sang jakarta APIs.
4. Chọn đúng JAXB API/runtime, SAAJ API/implementation và Activation API/provider.
5. Regenerate JAXB classes bằng tooling tương thích thay vì sửa generated code thủ công.
6. Phát hiện dependency javax và jakarta bị trộn trong cùng runtime.
7. Kiểm thử marshal/unmarshal, SOAP message creation, attachments và provider discovery.
8. Triển khai migration theo bước có thể rollback mà không đổi wire contract ngoài ý muốn.

**Nguyên tắc:** Migration package Java không đồng nghĩa thay XML namespace, WSDL binding hay SOAP wire format. Chỉ đổi những API đã chuyển namespace và nâng đồng bộ implementation phụ thuộc chúng.

## 2. Phạm vi package: cái gì đổi và cái gì giữ nguyên?

### 2.1. Các package trọng tâm phải đổi

| API | Trước Jakarta | Sau Jakarta |
|---|---|---|
| JAXB API | javax.xml.bind.* | jakarta.xml.bind.* |
| JAXB annotations | javax.xml.bind.annotation.* | jakarta.xml.bind.annotation.* |
| JAXB adapters | javax.xml.bind.annotation.adapters.* | jakarta.xml.bind.annotation.adapters.* |
| SAAJ | javax.xml.soap.* | jakarta.xml.soap.* |
| Activation | javax.activation.* | jakarta.activation.* |

Ví dụ import:
~~~java
// Trước
import javax.xml.bind.JAXBContext;
import javax.xml.bind.annotation.XmlRootElement;
import javax.xml.soap.SOAPMessage;
import javax.activation.DataHandler;

// Sau
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.bind.annotation.XmlRootElement;
import jakarta.xml.soap.SOAPMessage;
import jakarta.activation.DataHandler;
~~~

Những package API này không tương thích nhị phân với nhau. Một method nhận javax.xml.bind.JAXBElement không thể được truyền một jakarta.xml.bind.JAXBElement chỉ vì tên class và chức năng giống nhau.

### 2.2. Các API XML Java SE vẫn giữ javax.xml

Không thực hiện global replace trên mọi javax.*. Các package sau vẫn dùng namespace Java SE:

| API | Package vẫn dùng |
|---|---|
| QName | javax.xml.namespace.QName |
| XML transformation | javax.xml.transform.* |
| XML parsing | javax.xml.parsers.* |
| XML validation | javax.xml.validation.* |
| StAX | javax.xml.stream.* |
| XPath | javax.xml.xpath.* |
| XML constants | javax.xml.XMLConstants |
| DOM | org.w3c.dom.* |
| SAX | org.xml.sax.* |

Ví dụ code sau vẫn đúng trong ứng dụng Jakarta:

~~~java
import javax.xml.namespace.QName;
import javax.xml.transform.Source;
import javax.xml.transform.stream.StreamSource;
import javax.xml.validation.Schema;
import javax.xml.stream.XMLInputFactory;
import org.w3c.dom.Document;
import org.xml.sax.SAXException;
~~~

Các API này là một phần của Java SE. Jakarta migration không đổi package của chúng. Hãy compile trên JDK và dependency line mục tiêu để xác nhận.

### 2.3. Không thay XML namespace URI

Các URI sau không đổi chỉ vì Java imports đổi:

- Namespace SOAP 1.1: http://schemas.xmlsoap.org/soap/envelope/
- Namespace SOAP 1.2: http://www.w3.org/2003/05/soap-envelope
- Namespace XML Schema: http://www.w3.org/2001/XMLSchema
- Namespace WSDL 1.1: http://schemas.xmlsoap.org/wsdl/
- Namespace XOP: http://www.w3.org/2004/08/xop/include

Ví dụ XSD targetNamespace business, QName, element names và WSDL service contract giữ nguyên nếu mục tiêu migration chỉ là đổi Java runtime APIs. Consumer SOAP không cần đổi prefix hay URI chỉ vì server chuyển từ javax JAXB sang Jakarta JAXB.

## 3. Ranh giới tương thích Spring Boot và Spring-WS

Migration phải đồng bộ framework generations. Các dòng phổ biến có quan hệ như sau:

| Stack thế hệ cũ | Stack Jakarta |
|---|---|
| Spring Boot 2.x | Spring Boot 3.x |
| Spring Framework 5.x | Spring Framework 6.x |
| Spring-WS 3.x | Spring-WS 4.x |
| JAXB 2.x / javax JAXB | JAXB 3.x/4.x / jakarta JAXB |
| SAAJ javax API line | Jakarta SOAP API line |
| Activation javax API line | Jakarta Activation API line |

Bảng này chỉ mô tả ranh giới hệ sinh thái tổng quát. Hãy xác minh version cụ thể trong dependency management của dự án và compatibility matrix chính thức. Không chọn riêng một artifact Jakarta rồi kỳ vọng nó hoạt động với framework generation còn dùng javax.

### 3.1. Vì sao phải nâng cùng nhau?

Spring-WS 4 chạy trên thế hệ Spring Framework 6/Jakarta. Các lớp framework có thể tham chiếu Jakarta APIs. Nếu ứng dụng giữ Spring-WS 3 hoặc một thư viện endpoint cũ mong javax, hai thế giới type không thể thay thế cho nhau.

Một ứng dụng có thể compile nếu một số dependency vẫn kéo cả hai APIs, nhưng lỗi chỉ xuất hiện ở runtime khi provider hoặc framework gọi method với type khác package. Vì vậy compile pass chưa đủ.

### 3.2. Chọn một baseline trước khi sửa code

Ghi rõ:
- JDK baseline.
- Spring Boot/Spring Framework version.
- Spring-WS version.
- JAXB API và provider version.
- SAAJ API và implementation version.
- Activation API và provider version.
- WSS4J/XML Security/provider versions.
- App server/servlet container generation.

Đừng trộn các version mới nhất độc lập; dùng Spring Boot dependency management/BOM hoặc một dependency platform đã được xác minh.

## 4. JDK 11+ và sự thay đổi của Java EE modules

Từ Java 11, nhiều Java EE modules từng có trong JDK đã bị loại bỏ khỏi JDK distribution, trong đó có JAXB, JAX-WS, SAAJ và Activation. Ứng dụng chạy trên JDK 11+ không nên dựa vào việc các classes này xuất hiện sẵn từ JDK.

Điều này tạo ra hai việc riêng:
1. Khai báo API/runtime dependencies tường minh.
2. Chọn đúng javax hoặc jakarta generation tương thích với framework.

JDK 11 không có nghĩa tự động phải dùng Jakarta packages. Một ứng dụng legacy chạy Spring Boot 2/Spring-WS 3 vẫn có thể cần JAXB 2 javax dependencies. Jakarta package migration là bước tương thích hệ sinh thái riêng.

## 5. JAXB: API, implementation và generated classes

JAXB gồm API types/annotations, runtime implementation và code generated từ XSD. Đổi một phần có thể để lại type mismatch.

### 5.1. Trước và sau import migration

~~~java
// JAXB javax generation
import javax.xml.bind.JAXBContext;
import javax.xml.bind.Marshaller;
import javax.xml.bind.Unmarshaller;
import javax.xml.bind.annotation.XmlElement;
import javax.xml.bind.annotation.XmlRootElement;
import javax.xml.bind.annotation.XmlType;
~~~

~~~java
// JAXB Jakarta generation
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.bind.Marshaller;
import jakarta.xml.bind.Unmarshaller;
import jakarta.xml.bind.annotation.XmlElement;
import jakarta.xml.bind.annotation.XmlRootElement;
import jakarta.xml.bind.annotation.XmlType;
~~~

Annotations có tên tương tự nhưng thuộc type system khác. Một class có jakarta XmlRootElement không được JAXB 2 javax runtime nhận diện như annotation JAXB javax.

### 5.2. Tách API và runtime

Với Jakarta JAXB thế hệ mới, ứng dụng thường cần API và provider implementation. Ví dụ dependency Maven theo nhóm artifact hiện hành:

~~~xml
<dependency>
  <groupId>jakarta.xml.bind</groupId>
  <artifactId>jakarta.xml.bind-api</artifactId>
</dependency>

<dependency>
  <groupId>org.glassfish.jaxb</groupId>
  <artifactId>jaxb-runtime</artifactId>
  <scope>runtime</scope>
</dependency>
~~~

Version nên được quản lý bằng Spring Boot BOM hoặc BOM tương thích được dự án chọn. Không chép version ngẫu nhiên hoặc override phiên bản mà framework đã quản lý khi chưa kiểm dependency convergence.

### 5.3. Regenerate model từ XSD

Generated JAXB source có thể chứa:
- JAXB imports.
- XmlAccessorType/XmlType/XmlElement annotations.
- ObjectFactory và JAXBElement.
- XmlAdapter.
- Package-level XmlSchema annotation.
- Generated comments/tool versions.

Khi đổi JAXB generation, ưu tiên cấu hình XJC phù hợp để regenerate từ XSD. Không sửa hàng trăm generated files thủ công rồi để lần build kế tiếp ghi đè. Xác minh output packages, bindings và generated source target namespace.

### 5.4. Binding customizations

External JAXB binding files hoặc plugin XJC có thể phụ thuộc namespace/version của binding schema và toolchain. Kiểm:
- Binding file version/namespace.
- XJC plugin có hỗ trợ JAXB generation mục tiêu không.
- Adapter class imports.
- Generated class package names.
- Episode files/shared schema generation.
- Build reproducibility giữa developer và CI.

JAXB 2 và JAXB 3/4 tooling không được giả định là interchangeably compatible.

## 6. Spring-WS marshaller và unmarshaller

Một cấu hình Spring-WS thường dùng Jaxb2Marshaller. Với Jakarta stack, marshaller/provider phải xử lý Jakarta JAXB annotations và API.

~~~java
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SoapBindingConfiguration {

    @Bean
    Jaxb2Marshaller ordersMarshaller() {
        Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
        marshaller.setContextPath("com.example.orders.jakarta");
        marshaller.setMtomEnabled(true);
        return marshaller;
    }
}
~~~

Spring-WS/Spring OXM generation cần tương thích với JAXB API line. Không dùng marshaller class từ framework generation javax với Jakarta JAXB runtime không được hỗ trợ.

### 6.1. Kiểm tra cả hai hướng

- Marshal request Java DTO thành XML.
- Unmarshal response XML thành Java DTO.
- Marshal response server.
- Unmarshal request tại endpoint.
- Validate schema khi marshalling/unmarshalling theo cấu hình.
- Optional/nil values, collections, enum và date/time.
- JAXBElement/ObjectFactory paths.
- MTOM/DataHandler nếu contract dùng attachment.

Một chiều pass không chứng minh chiều còn lại tương thích.

## 7. SAAJ: SOAP message API và provider

SAAJ cung cấp SOAPMessage, SOAPPart, SOAPEnvelope, SOAPHeader và SOAPBody APIs. Package đổi từ javax.xml.soap sang jakarta.xml.soap khi chuyển Jakarta generation.

### 7.1. Import migration

~~~java
// Trước
import javax.xml.soap.MessageFactory;
import javax.xml.soap.SOAPMessage;
import javax.xml.soap.SOAPEnvelope;
import javax.xml.soap.SOAPBody;
~~~

~~~java
// Sau
import jakarta.xml.soap.MessageFactory;
import jakarta.xml.soap.SOAPMessage;
import jakarta.xml.soap.SOAPEnvelope;
import jakarta.xml.soap.SOAPBody;
~~~

### 7.2. API dependency và implementation

Jakarta SOAP API artifact thường dùng:

~~~xml
<dependency>
  <groupId>jakarta.xml.soap</groupId>
  <artifactId>jakarta.xml.soap-api</artifactId>
</dependency>
~~~

Cần một SAAJ implementation tương thích runtime, ví dụ Metro SAAJ implementation thuộc dòng Jakarta:

~~~xml
<dependency>
  <groupId>com.sun.xml.messaging.saaj</groupId>
  <artifactId>saaj-impl</artifactId>
  <scope>runtime</scope>
</dependency>
~~~

Version phải khớp API/framework và được quản lý bởi BOM tương ứng. Không chỉ thêm API jar rồi bỏ qua provider implementation.

### 7.3. Provider discovery

MessageFactory.newInstance() và các factory APIs dựa vào provider discovery. Lỗi thường gặp:
- Không tìm thấy SAAJ provider.
- Provider cũ được kéo bắc cầu trước provider mới.
- Service loader metadata không tương thích.
- Classloader của app server nạp implementation javax thay vì Jakarta.
- API và implementation major versions không tương thích.

Kiểm test tạo SOAPMessage, đọc/write Envelope, Header/Body và xử lý SOAP Fault trên runtime thực. Trên app server, kiểm classloading precedence/modules vì container có thể cung cấp API/provider riêng.

## 8. Activation: DataHandler và MIME content

Activation cung cấp DataHandler, DataSource, CommandMap và MIME type abstractions. Trong SOAP, Activation thường xuất hiện khi xử lý attachments, MTOM/XOP hoặc binary payload.

### 8.1. Import migration

~~~java
// Trước
import javax.activation.DataHandler;
import javax.activation.DataSource;
import javax.activation.FileDataSource;
~~~

~~~java
// Sau
import jakarta.activation.DataHandler;
import jakarta.activation.DataSource;
import jakarta.activation.FileDataSource;
~~~

### 8.2. API và provider

Jakarta Activation API:

~~~xml
<dependency>
  <groupId>jakarta.activation</groupId>
  <artifactId>jakarta.activation-api</artifactId>
</dependency>
~~~

Một provider implementation phổ biến trong hệ sinh thái Jakarta là Angus Activation:

~~~xml
<dependency>
  <groupId>org.eclipse.angus</groupId>
  <artifactId>angus-activation</artifactId>
  <scope>runtime</scope>
</dependency>
~~~

Chọn version theo BOM/compatibility line của framework. Kiểm API artifact và runtime provider được nạp từ cùng generation. Không để javax.activation.DataHandler đi vào code path đang mong jakarta.activation.DataHandler.

### 8.3. MTOM/DataHandler integration

Khi dùng MTOM, test:
- DataHandler có mở đúng stream và trả content type phù hợp.
- Attachment được serialize thành MIME part.
- Content-ID và XOP Include liên kết đúng.
- Stream được đóng theo ownership contract.
- Large attachment có behavior buffering/spooling dự kiến.
- Client/server đều sử dụng Jakarta Activation-compatible stack.
- WS-Security policy bảo vệ attachment theo yêu cầu.

Không giả định đổi DataHandler import là đủ; message factory, marshaller và transport cũng phải hỗ trợ.

## 9. Namespace đôi: Java imports và XML contract

Một lỗi migration phổ biến là thay package Java rồi thay luôn XML namespace hoặc WSDL/XSD imports. Hai thứ độc lập:

- Java package xác định type mà code compile/runtime dùng.
- XML namespace URI xác định QName trên wire.
- XSD/WSDL targetNamespace là contract identifier.
- JAXB package-level XmlSchema annotation ánh xạ Java model vào XML namespace.

Ví dụ annotation Jakarta vẫn giữ business namespace cũ:

~~~java
@jakarta.xml.bind.annotation.XmlSchema(
    namespace = "urn:example:orders:v1",
    elementFormDefault =
        jakarta.xml.bind.annotation.XmlNsForm.QUALIFIED
)
package com.example.orders.jakarta;
~~~

Package Java đổi từ com.example.orders.generated sang com.example.orders.jakarta không bắt buộc đổi urn:example:orders:v1. Nếu giữ nguyên contract, request/response XML phải tương đương trước và sau migration.

### 9.1. Wire compatibility test

Lưu fixtures SOAP cũ đã redaction, sau đó so:
- Root/body QName.
- Element order và namespace.
- Attribute presence.
- Nil/absent/default semantics.
- Decimal/date/time lexical form.
- SOAP Header/Action.
- SOAP Fault detail.
- MIME/MTOM attachment references.

Không so prefix literal; so namespace URI và local name.

## 10. Dependency convergence: tìm javax sót lại và Jakarta bị trộn

Ứng dụng có thể kéo dependencies qua nhiều thư viện: Spring-WS, WSS4J, JAXB plugins, SAAJ provider, Activation, servlet container, logging hoặc partner SDK.

### 10.1. Kiểm dependency tree

Maven:

~~~bash
mvn dependency:tree
~~~

Có thể lọc theo group/artifact liên quan:

~~~bash
mvn dependency:tree -Dincludes=javax.xml.bind:*,jakarta.xml.bind:*,javax.xml.soap:*,jakarta.xml.soap:*,javax.activation:*,jakarta.activation:*
~~~

Cú pháp filter tùy Maven/plugin; nếu không match, xuất dependency tree rồi tìm thủ công các group/artifact. Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Kiểm cả compileClasspath và runtimeClasspath. Một dependency có thể compile được nhưng provider thiếu ở runtime.

### 10.2. Dùng Maven Enforcer/Gradle constraints

Dùng dependency convergence/upper-bound rules hoặc constraints để tránh nhiều versions của cùng API/provider. Tuy nhiên, javax và jakarta có group/artifact khác nhau nên convergence rule thông thường không tự phát hiện chúng là hai thế hệ của cùng conceptual API. Cần explicit scan và policy cấm namespace cũ trong module đã migrate.

### 10.3. Tìm package references

Tìm trong:
- Main sources.
- Test sources.
- Generated source directories.
- XJC binding files/plugins.
- Reflection strings/class names.
- META-INF/services provider files.
- XML Spring configuration.
- OSGi/module descriptors nếu có.
- Shaded/relocated dependencies.

Không thay mọi javax occurrence. Lập allowlist cho các Java SE package giữ nguyên như javax.xml.namespace, javax.xml.transform, javax.xml.parsers, javax.xml.validation, javax.xml.stream và javax.xml.xpath.

## 11. Xử lý dependency cũ không có Jakarta release

Nếu một thư viện partner SDK chỉ cung cấp javax JAXB/SAAJ APIs, không thể truyền Jakarta types trực tiếp qua public method. Các lựa chọn:
1. Nâng thư viện lên release có Jakarta support.
2. Thay bằng thư viện tương thích.
3. Cô lập legacy component trong module/process riêng.
4. Dùng adapter chuyển đổi qua XML/bytes ở ranh giới độc lập, nếu semantics và security cho phép.
5. Tạm hoãn migration module nếu dependency là blocker thực sự.

Không cố đưa cả javax và jakarta implementation vào cùng object graph rồi ép cast. Khi cần bridge, serialize contract XML qua boundary tách biệt, validate lại và kiểm performance/security.

### 11.1. Không dùng bytecode transformer một cách mù quáng

Một số công cụ có thể transform namespace trong bytecode. Transformation không tự bảo đảm:
- Service provider descriptors đã đổi.
- Reflection/resource strings đã đổi.
- Generated code/plugin hỗ trợ.
- Third-party runtime behavior tương thích.
- Signature/security providers hoạt động.
- XML bindings không bị biến dạng.

Nếu dùng transformer trong migration legacy, cần kiểm output, provenance và regression tests cho từng library. Ưu tiên artifact Jakarta-native.

## 12. JAX-WS và các API SOAP khác không được gộp nhầm

Bài này tập trung JAXB, SAAJ và Activation trong Spring-WS. JAX-WS là API riêng, không đồng nghĩa với Spring Web Services. Nếu dự án cũng dùng JAX-WS/wsimport/Endpoint/Dispatch, cần một workstream migration riêng cho API/tooling tương ứng.

Tương tự, package javax.servlet chuyển sang jakarta.servlet trong thế hệ Jakarta Servlet, nhưng đây là phạm vi khác. Với Spring Boot 3/Spring Framework 6, web container và servlet-related dependencies cũng phải tương thích Jakarta. Không chỉ đổi JAXB/SAAJ rồi bỏ qua web runtime.

## 13. Quy trình migration an toàn theo từng bước

### Bước 1 — Inventory

Ghi JDK, Boot, Spring Framework, Spring-WS, JAXB, SAAJ, Activation, WSS4J, servlet container, XJC plugins và partner libraries. Lưu dependency tree baseline.

### Bước 2 — Chốt target platform

Chọn một Spring Boot/Spring Framework/Spring-WS generation tương thích Jakarta. Kiểm JDK minimum, servlet container và Jakarta API level trước khi thay imports.

### Bước 3 — Nâng framework platform

Nâng Spring Boot/Framework/WS cùng nhóm dependency được quản lý. Compile và xử lý breaking changes của framework tách khỏi wire-contract changes khi có thể.

### Bước 4 — Align JAXB/SAAJ/Activation

Thay APIs và implementations cùng thế hệ. Dùng BOM hoặc dependency management thống nhất; loại trừ các javax transitive artifacts nếu dependency mới yêu cầu Jakarta và không còn đường code nào dùng legacy.

### Bước 5 — Regenerate JAXB classes

Cập nhật XJC/toolchain, binding files và plugins. So output packages/annotations, compile generated sources, không hand-edit hàng loạt.

### Bước 6 — Sửa application imports

Chỉ đổi package đã migrate: JAXB, SAAJ và Activation (cùng các API Jakarta khác mà target framework yêu cầu). Giữ Java SE javax.xml.* và org.w3c.dom/org.xml.sax.

### Bước 7 — Kiểm provider discovery

Khởi tạo JAXBContext, Marshaller, Unmarshaller, SAAJ MessageFactory, Activation DataHandler/DataSource. Kiểm classloader trên đúng runtime/container.

### Bước 8 — Chạy contract regression

So SOAP requests/responses, WSDL/XSD, SOAP Faults, namespaces, MTOM attachments và WS-Security behavior. Giữ wire contract nếu migration không nhằm thay contract.

### Bước 9 — Integration/performance tests

Chạy embedded/container HTTP tests, test certificates, attachment workloads, memory/concurrency và partner interoperability.

### Bước 10 — Rollout và rollback

Deploy canary/staging, kiểm startup/provider logs, latency/fault rates, partner traffic và class loading. Giữ artifact/dependency lock baseline để rollback.

## 14. Mẫu dependency baseline Jakarta

Một phần dependency minh họa (version do BOM/parent quản lý):

~~~xml
<dependencies>
  <dependency>
    <groupId>jakarta.xml.bind</groupId>
    <artifactId>jakarta.xml.bind-api</artifactId>
  </dependency>

  <dependency>
    <groupId>org.glassfish.jaxb</groupId>
    <artifactId>jaxb-runtime</artifactId>
    <scope>runtime</scope>
  </dependency>

  <dependency>
    <groupId>jakarta.xml.soap</groupId>
    <artifactId>jakarta.xml.soap-api</artifactId>
  </dependency>

  <dependency>
    <groupId>com.sun.xml.messaging.saaj</groupId>
    <artifactId>saaj-impl</artifactId>
    <scope>runtime</scope>
  </dependency>

  <dependency>
    <groupId>jakarta.activation</groupId>
    <artifactId>jakarta.activation-api</artifactId>
  </dependency>

  <dependency>
    <groupId>org.eclipse.angus</groupId>
    <artifactId>angus-activation</artifactId>
    <scope>runtime</scope>
  </dependency>
</dependencies>
~~~

Đây là dependency inventory gợi ý, không phải yêu cầu thêm tất cả artifacts vào mọi ứng dụng. Framework BOM có thể đã cung cấp một số API/provider; chỉ khai báo phần cần thiết và tránh duplicate versions. Kiểm compatibility giữa JAXB runtime, SAAJ implementation, Activation provider và Spring-WS line đã chọn.

## 15. Kiểm thử sau migration

### 15.1. Compile/import checks

- Không còn javax JAXB imports trong module Jakarta.
- Không còn javax SAAJ imports.
- Không còn javax Activation imports.
- Java SE javax.xml.* imports vẫn hợp lệ.
- Generated sources dùng đúng annotation namespace.
- Không có duplicate API classes đến từ shaded libraries.

### 15.2. Runtime/provider smoke tests

Kiểm:
- JAXBContext.newInstance tạo context.
- Marshaller marshal request.
- Unmarshaller đọc response fixture.
- SAAJ MessageFactory tạo SOAPMessage.
- SOAP Envelope/Header/Body đọc/ghi được.
- Activation DataHandler mở stream.
- MTOM/MIME attachment serialize/deserialize nếu được sử dụng.
- Provider discovery hoạt động trong packaged artifact/container.

### 15.3. Spring-WS integration tests

Chạy:
- SOAP 1.1 và SOAP 1.2 theo contract hỗ trợ.
- Endpoint nhận request và trả response.
- Client gọi qua HTTP transport thật.
- Request/response XSD validation.
- SOAP Fault mapping.
- Interceptor chain và WS-Security.
- Certificate/key loading.
- MTOM attachments và cleanup.
- WSDL/XSD publication.

### 15.4. Wire compatibility

Nếu không chủ đích đổi contract, so XML fixtures trước/sau migration. Assert QName/namespace/sequence/value semantics; so MIME structure và attachment checksum khi dùng MTOM. Prefix/whitespace serialization có thể khác nhưng XML infoset và contract semantics phải giữ nguyên.

## 16. Lỗi migration thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| package jakarta không tồn tại | API dependency thiếu hoặc version sai | Align BOM/API dependencies |
| NoSuchMethodError JAXB | API/runtime generation lệch | Kiểm JAXB API và provider cùng line |
| ClassCastException giữa JAXBElement | javax và jakarta types bị trộn | Xác định boundary và loại dependency legacy |
| JAXB không nhận annotation | Generated model dùng javax annotation nhưng runtime Jakarta | Regenerate code |
| Provider not found SAAJ | Chỉ có API, thiếu implementation | Thêm SAAJ provider phù hợp |
| MessageFactory lỗi lúc startup | Provider discovery/classloader conflict | Kiểm service loader và container libraries |
| DataHandler không resolve | Activation API/provider thiếu hoặc sai namespace | Align Activation API/runtime |
| MTOM attachment mất | Message factory/marshaller/transport không tương thích | Kiểm MIME wire message và provider |
| Build pass, packaged app fail | Runtime dependency scope/packaging sai | Kiểm runtimeClasspath và deploy artifact |
| SOAP XML thay đổi bất ngờ | JAXB binding/namespace annotation đổi | So wire fixtures và package-info |
| javax.xml.namespace không compile sau global replace | Đã đổi nhầm Java SE package | Khôi phục package Java SE |
| WSS4J/security interceptor fail | Security stack chưa cùng Jakarta generation | Align WSS4J/Spring-WS dependencies và providers |

### 16.1. NoSuchMethodError và ClassCastException

Đây thường là dấu hiệu runtime classpath khác compile classpath hoặc hai generation APIs cùng xuất hiện. Xem class origin/classloader và dependency tree. Đừng chỉ thêm jar mới đến khi lỗi biến mất; điều đó có thể tạo thêm xung đột.

### 16.2. Provider discovery failure

Kiểm:
- Runtime artifact có chứa implementation.
- META-INF/services phù hợp API generation.
- Classloader container có override app libs.
- Có duplicate implementations.
- Dependency shading không làm mất service metadata.

## 17. Case study: ứng dụng Boot 2 chuyển sang Boot 3 nhưng SOAP endpoint không khởi động

### 17.1. Triệu chứng

Sau khi nâng Spring Boot và Spring Framework sang Jakarta generation, server fail lúc tạo JAXBContext hoặc SAAJ MessageFactory. Generated DTO vẫn còn import javax.xml.bind.annotation. Một module khác vẫn kéo javax.activation, trong khi endpoint dùng Jakarta DataHandler.

### 17.2. Nguyên nhân

- Framework generation đã chuyển Jakarta nhưng JAXB model chưa regenerate.
- JAXB API và runtime khác generation.
- SAAJ API đã được thêm nhưng thiếu implementation.
- Activation API/provider không thống nhất.
- Dependency transitive giữ legacy APIs.
- Một số javax.xml Java SE imports bị thay nhầm trong automated refactor.
- Container/shared libraries nạp provider cũ.

### 17.3. Quy trình xử lý

1. Lưu dependency tree/runtime classpath sau nâng cấp.
2. Xác định class nguồn của JAXB/SAAJ/Activation APIs và provider.
3. Regenerate JAXB từ XSD bằng Jakarta-compatible XJC.
4. Chỉnh imports JAXB/SAAJ/Activation, giữ Java SE javax.xml.*.
5. Align BOM/API/runtime dependencies.
6. Kiểm provider discovery trong packaged app.
7. Chạy marshal/unmarshal/SOAPMessage/MTOM smoke tests.
8. Chạy SOAP HTTP integration tests và wire compatibility suite.
9. Deploy canary và theo dõi faults/startup/partner metrics.

### 17.4. Tiêu chí đóng lỗi

- Application context khởi động không provider/classloading errors.
- JAXB và SAAJ factories tạo được.
- Generated DTO dùng Jakarta annotations.
- Java SE XML package imports không bị đổi.
- SOAP wire contract giữ semantics đã cam kết.
- Attachments và WS-Security vẫn hoạt động.
- Không còn legacy javax JAXB/SAAJ/Activation trên runtime path của module đã migrate.

## 18. Bài tập tự luyện

**Bài 1 — QName:** Sau migration, có phải đổi javax.xml.namespace.QName thành jakarta.xml.namespace.QName?

**Đáp án:** Không. QName vẫn là javax.xml.namespace.QName thuộc Java SE.

**Bài 2 — JAXB:** Đổi import source thành jakarta.xml.bind nhưng generated annotations vẫn javax. Runtime Jakarta có nhận annotation cũ?

**Đáp án:** Không nên giả định. Regenerate model với toolchain Jakarta hoặc dùng generation tương thích với runtime.

**Bài 3 — SOAP Envelope:** Có phải đổi SOAP 1.1 namespace URI khi đổi SAAJ package?

**Đáp án:** Không. Java API package và SOAP XML namespace là hai phạm vi khác nhau.

**Bài 4 — JDK 11:** JAXB luôn có sẵn trong JDK 11?

**Đáp án:** Không. Các Java EE modules như JAXB đã bị loại khỏi JDK từ Java 11; cần khai báo dependencies tường minh.

**Bài 5 — SAAJ:** Chỉ thêm jakarta.xml.soap-api có đủ để MessageFactory hoạt động?

**Đáp án:** Không nhất thiết. Cần provider implementation tương thích và provider discovery hoạt động.

**Bài 6 — Activation:** DataHandler javax có thể truyền trực tiếp vào API nhận jakarta DataHandler?

**Đáp án:** Không. Đây là hai Java types khác nhau.

**Bài 7 — Spring-WS:** Có thể giữ Spring-WS 3 và chỉ nâng JAXB runtime lên Jakarta?

**Đáp án:** Không nên. Align framework generation với Jakarta baseline đã chọn; Spring-WS 4 thuộc hệ sinh thái Spring 6/Jakarta.

**Bài 8 — Global replace:** Có thể thay mọi chuỗi javax. thành jakarta. trong repo?

**Đáp án:** Không. Sẽ làm hỏng Java SE packages như javax.xml.transform, javax.xml.parsers và javax.xml.namespace.

**Bài 9 — Wire contract:** Đổi package generated classes có tự đổi WSDL targetNamespace?

**Đáp án:** Không tự động. Kiểm JAXB XmlSchema mapping và wire fixtures; giữ namespace URI nếu contract không đổi.

**Bài 10 — Runtime error:** Compile pass nhưng production ClassCastException giữa JAXBElement. Kiểm gì?

**Đáp án:** Tìm javax/jakarta duplicate types, runtime class origin, generated sources và transitive dependencies.

**Bài 11 — MTOM:** Đổi Activation imports xong attachment vẫn fail. Kiểm gì?

**Đáp án:** MessageFactory, marshaller, SAAJ/Activation provider, MIME transport, Content-ID và actual wire package.

**Bài 12 — Legacy SDK:** Partner SDK chỉ có javax APIs. Có thể cast sang Jakarta?

**Đáp án:** Không. Nâng SDK, cô lập legacy module hoặc tạo boundary chuyển XML/bytes có validation.

## 19. Checklist nghiệm thu migration

### Platform alignment
- [ ] JDK và Spring Boot/Spring Framework/Spring-WS target versions đã chốt.
- [ ] Servlet container và Jakarta level tương thích.
- [ ] BOM/dependency management quản lý API và implementations.
- [ ] WSS4J/XML security libraries thuộc generation tương thích.

### Package scope
- [ ] JAXB imports chuyển sang jakarta.xml.bind.
- [ ] JAXB annotations/adapters/generated classes chuyển đồng bộ.
- [ ] SAAJ imports chuyển sang jakarta.xml.soap.
- [ ] Activation imports chuyển sang jakarta.activation.
- [ ] javax.xml.namespace/transform/parsers/validation/stream/xpath giữ nguyên.
- [ ] org.w3c.dom và org.xml.sax giữ nguyên.
- [ ] Không global-replace XML namespace URI trong WSDL/XSD/SOAP.

### Runtime and code generation
- [ ] JAXB API và runtime provider tương thích.
- [ ] SAAJ API và implementation provider tương thích.
- [ ] Activation API và implementation tương thích.
- [ ] XJC/binding files/plugins hỗ trợ Jakarta generation.
- [ ] Generated sources được regenerate, không sửa tay tạm thời.
- [ ] Dependency tree không trộn legacy APIs trong module đã migrate.
- [ ] Provider discovery/classloader được kiểm tra trong packaged runtime.

### Contract and security regression
- [ ] JAXB marshal/unmarshal tests pass.
- [ ] SAAJ MessageFactory/Envelope/Header/Body tests pass.
- [ ] WSDL/XSD publication giữ contract semantics.
- [ ] SOAP 1.1/1.2, Fault và interceptors được test.
- [ ] MTOM/Activation/DataHandler attachments được test nếu sử dụng.
- [ ] WS-Security, certificates và signed coverage vẫn hoạt động.
- [ ] HTTP integration và partner interoperability tests pass.
- [ ] Có rollback baseline và monitoring canary.

**Ghi nhớ:** Chuyển javax sang jakarta trong Spring-WS là migration của Java APIs và runtime ecosystem. JAXB, SAAJ và Activation đổi package; Java SE XML APIs như QName, transform, parsers, validation, StAX, DOM và SAX vẫn giữ package cũ. Align Spring Boot/Spring Framework/Spring-WS, API và provider versions; regenerate JAXB classes bằng tooling phù hợp; kiểm dependency/classloader; và chứng minh SOAP wire contract, attachments, Faults cùng WS-Security vẫn giữ behavior đã cam kết.
