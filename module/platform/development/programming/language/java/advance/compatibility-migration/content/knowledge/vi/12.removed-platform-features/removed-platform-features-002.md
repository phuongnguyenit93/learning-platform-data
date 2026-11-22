# JAXB, JAX-WS, Activation và công cụ sinh mã được cung cấp bên ngoài

Khi di chuyển ứng dụng Java từ một JDK cũ sang JDK hiện đại, nhóm phát triển có thể gặp lỗi dù mã nghiệp vụ gần như không thay đổi: `package javax.xml.bind does not exist`, `package javax.xml.ws does not exist`, `NoClassDefFoundError: javax/activation/DataHandler`, hoặc không còn tìm thấy lệnh `xjc` và `wsimport` trong thư mục `bin` của JDK. Đây không nhất thiết là lỗi của JAXB, SOAP hay WSDL; nguyên nhân nền tảng là một số API và công cụ từng được phân phối cùng JDK đã được loại bỏ khỏi bản phân phối Java SE.

Từ **JDK 11**, theo **JEP 320**, các module Java EE/CORBA trước đây đi kèm JDK, trong đó có JAXB, JAX-WS và JavaBeans Activation Framework (JAF), không còn là thành phần được đóng gói với JDK. Các công cụ liên quan như `xjc`, `schemagen`, `wsimport` và `wsgen` cũng không còn được cung cấp như các chương trình tích hợp sẵn trong JDK. Để tiếp tục dùng các công nghệ này trên JDK 11, 17, 21 hoặc mới hơn, dự án phải chủ động quản lý **API, implementation/runtime, provider, build plugin và tool sinh mã** như những dependency bên ngoài.

Song song với thay đổi về cách phân phối, hệ sinh thái Java EE đã chuyển sang Jakarta EE. Một số thế hệ API vẫn dùng package `javax.*`, trong khi các thế hệ Jakarta EE mới dùng `jakarta.*`. Hai hệ tên này không tương đương nhị phân. Chọn đúng thư viện bên ngoài nhưng chọn sai thế hệ namespace vẫn có thể làm ứng dụng không compile hoặc lỗi khi chạy.

Bài học này cung cấp cách hiểu lịch sử thay đổi, phân biệt vai trò của từng thành phần, chọn dependency phù hợp, cấu hình sinh mã từ XSD/WSDL, xử lý lỗi tương thích và lập quy trình migration có thể kiểm chứng.

## 1. Vì sao các công nghệ này biến mất khỏi JDK?

### 1.1. Từ JDK 8 đến JDK 11

Trên nhiều bản phân phối JDK 8, lập trình viên có thể import JAXB và JAX-WS mà không khai báo thư viện bên ngoài. Một số công cụ sinh mã cũng nằm trong `JAVA_HOME/bin`.

Ví dụ:

```java
import javax.xml.bind.JAXBContext;
import javax.xml.bind.Marshaller;
import javax.xml.ws.Service;
import javax.activation.DataHandler;
```

Và các lệnh có thể quen thuộc:

```bash
xjc -d generated src/main/xsd/customer.xsd
wsimport -keep -s generated src/main/wsdl/CustomerService.wsdl
```

Từ JDK 9, các module liên quan bị đánh dấu deprecated for removal. Đến **JDK 11**, JEP 320 loại bỏ chúng khỏi JDK. Vì vậy, cùng một repository có thể xây dựng được trên JDK 8 nhưng thất bại ở bước compile hoặc code generation khi chuyển lên JDK 17/21.

### 1.2. Các module bị loại bỏ liên quan trực tiếp

| Thành phần từng đi kèm JDK | Module liên quan trước khi loại bỏ | Công việc chính |
|---|---|---|
| JAXB API | `java.xml.bind` | Ánh xạ object Java ↔ XML |
| JAX-WS API | `java.xml.ws` | SOAP web service và client |
| JavaBeans Activation Framework | `java.activation` | MIME type, DataHandler, DataSource |
| Common Annotations subset | `java.xml.ws.annotation` | Một số annotation được các stack này sử dụng |
| JAXB tools | `jdk.xml.bind` | `xjc`, `schemagen` |
| JAX-WS tools | `jdk.xml.ws` | `wsimport`, `wsgen` |

JEP 320 còn liên quan các module khác như CORBA; bài này tập trung vào JAXB, JAX-WS, Activation và generator.

**Điểm cần phân biệt:** không phải mọi package tên `javax.xml.*` đều bị loại bỏ. Java XML Processing API như `javax.xml.parsers`, `javax.xml.transform`, `javax.xml.namespace`, `javax.xml.stream`, DOM và SAX vẫn thuộc các API XML của Java SE, chủ yếu trong module `java.xml`. Không nên thay toàn bộ `javax.xml.*` bằng `jakarta.xml.*` một cách cơ học.

### 1.3. Trên JDK 17 hoặc 21, vấn đề đã tồn tại từ trước

Nếu ứng dụng đang chạy trên JDK 17 và dự định lên JDK 21, việc JAXB/JAX-WS không còn bundled là tình trạng đã xuất hiện từ JDK 11, không phải thay đổi riêng của JDK 21.

Tuy nhiên, vấn đề có thể chỉ lộ ra khi nâng cấp vì CI hoặc một task generator trước đó vẫn chạy bằng JDK 8, runtime ứng dụng dùng image khác, IDE có dependency ẩn hoặc plugin cũ kéo các class `javax.*` vào classpath. Migration cần chốt phiên bản JDK thực tế tại từng bước: build, generate, compile, test, package và production runtime.

## 2. Phân biệt API, runtime implementation và tool sinh mã

Các thành phần này có nhiệm vụ khác nhau; không thể thay thế lẫn nhau.

| Nhóm | Vai trò | Ví dụ |
|---|---|---|
| API | Chứa interface, annotation và contract mà source biên dịch dựa trên | `JAXBContext`, `Marshaller`, `Service`, `DataHandler` |
| Implementation/runtime | Thực thi các API ở runtime | JAXB Runtime, Metro JAX-WS RI, Apache CXF |
| Provider/service discovery | Cho phép API tìm implementation tương ứng | Provider được khai báo bằng cơ chế SPI/ServiceLoader hoặc cơ chế của implementation |
| Generator | Tạo source hoặc metadata từ schema/service contract | JAXB XJC, JAX-WS wsimport, CXF wsdl2java |
| Build plugin | Tích hợp generator vào Maven/Gradle và task graph | Plugin XJC, CXF Codegen Plugin, Metro tools integration |
| Runtime integration | Kết nối với HTTP transport, servlet, SOAP attachment, security và service registry | Endpoint runtime, SOAP binding, MTOM, transport |

Một lỗi biên dịch `package ... does not exist` thường cho biết thiếu API trên compile classpath. Ngược lại, một lỗi “provider not found” sau khi compile thành công thường cho biết thiếu hoặc không thể tìm implementation/runtime phù hợp.

Công cụ `xjc` tạo mã Java không đồng nghĩa với việc chương trình đã có JAXB runtime để marshal/unmarshal. Công cụ `wsimport` tạo SOAP stub không đồng nghĩa với việc ứng dụng đã có JAX-WS provider, HTTP transport và dependency cần thiết để gửi request.

## 3. Hai thế hệ namespace: `javax.*` và `jakarta.*`

### 3.1. Vì sao tên thư viện không đủ để suy ra package?

Khi công nghệ Java EE chuyển sang Jakarta EE, một giai đoạn đầu vẫn giữ package `javax.*` nhưng đổi tên artifact hoặc tổ chức quản lý. Các thế hệ Jakarta EE tiếp theo mới đổi namespace công khai sang `jakarta.*`.

Đối với migration, cần dựa vào **package thực sự chứa trong JAR** và ma trận của framework, không chỉ dựa vào việc tên artifact có chữ “jakarta”.

| Họ công nghệ | Nhánh API cũ thường gặp | Nhánh API mới thường gặp |
|---|---|---|
| JAXB | `javax.xml.bind.*` | `jakarta.xml.bind.*` |
| JAX-WS | `javax.xml.ws.*` | `jakarta.xml.ws.*` |
| Activation | `javax.activation.*` | `jakarta.activation.*` |
| Web Services Metadata annotations | `javax.jws.*` | `jakarta.jws.*` |
| Common Annotations | `javax.annotation.*` | `jakarta.annotation.*` |

Theo cách phân chia phiên bản phổ biến, JAXB/JAX-WS thế hệ 2.x dùng `javax.*`, còn thế hệ 3.x trở lên dùng `jakarta.*`. Activation thế hệ 1.x dùng `javax.activation.*`, thế hệ 2.x dùng `jakarta.activation.*`. Hãy xác minh bản phát hành cụ thể vì tọa độ Maven và nhãn Jakarta EE không phải lúc nào cũng biểu thị trực tiếp package namespace.

### 3.2. Hai namespace không thay thế được cho nhau ở bytecode

Ví dụ:

```java
// Kiểu thuộc thế hệ cũ:
javax.xml.bind.JAXBContext oldContext;

// Kiểu thuộc thế hệ mới:
jakarta.xml.bind.JAXBContext newContext;
```

Đây là hai binary name khác nhau. JVM không tự chuyển `javax/xml/bind/JAXBContext` thành `jakarta/xml/bind/JAXBContext`.

Cùng nguyên tắc áp dụng với annotation:

```java
@javax.xml.bind.annotation.XmlRootElement
public class CustomerLegacy {
}
```

Một JAXB runtime thế hệ `jakarta` không nên được giả định sẽ diễn giải annotation `javax.xml.bind.annotation.XmlRootElement` như annotation `jakarta.xml.bind.annotation.XmlRootElement`. Việc dùng runtime mới với model code sinh từ generator cũ có thể gây lỗi không tìm thấy class hoặc mapping không như mong đợi.

### 3.3. Chọn chiến lược trước khi chọn dependency

Có hai hướng migration hợp lý nhưng khác độ lớn:

**Hướng A — Giữ `javax.*`, chỉ tách dependency khỏi JDK.** Thích hợp khi ứng dụng hoặc framework hiện tại còn ở thế hệ Java EE/Jakarta EE tương thích namespace cũ. Tập trung thêm JAXB/JAX-WS/Activation API và runtime bên ngoài, giữ source import và generator phù hợp với `javax.*`.

**Hướng B — Chuyển cả stack sang `jakarta.*`.** Thích hợp khi nâng framework sang thế hệ yêu cầu Jakarta, ví dụ các phiên bản framework hiện đại đã chuyển namespace. Cần đổi import, annotation, generated source, provider, binding customization, framework integration và plugin theo một ma trận thống nhất.

Không nên trộn ngẫu nhiên các thành phần `javax` và `jakarta` trong cùng một chuỗi marshalling hoặc SOAP call. Nếu buộc phải hỗ trợ cả hai ở ranh giới tích hợp, hãy dùng adapter hoặc tách module, có test rõ ràng về kiểu dữ liệu và contract.

## 4. Kiểm kê trước khi sửa mã hoặc build

### 4.1. Tìm import và API đang được dùng

Các dấu hiệu trong source:

```java
import javax.xml.bind.JAXBContext;
import javax.xml.bind.annotation.XmlElement;
import javax.xml.ws.Service;
import javax.jws.WebService;
import javax.activation.DataHandler;
```

Hoặc tương đương `jakarta.*`.

Những vị trí cần xem ngoài source chính:

- Source được sinh trong `target/generated-sources` hoặc `build/generated`.
- DTO và JAXB annotations sinh từ XSD.
- SOAP client stub, SEI và service class sinh từ WSDL.
- Code dùng MTOM/SOAP attachment, `DataHandler` và MIME.
- WSDL/XSD/binding XML, catalog, cấu hình endpoint.
- Dependency injection, component scanning và web service endpoint publication.
- Plugin build, CI script và custom command gọi `xjc`/`wsimport`.
- Consumer hoặc thư viện nội bộ đã compile sẵn với binary name `javax.*`.

### 4.2. Xem dependency graph thực tế

Với Maven:

```bash
./mvnw -version
./mvnw dependency:tree
./mvnw help:effective-pom
./mvnw dependency:resolve-plugins
```

Với Gradle:

```bash
./gradlew --version
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencies --configuration testRuntimeClasspath
./gradlew :app:buildEnvironment
```

Thay `:app` bằng project path thực tế. Với Gradle, `buildEnvironment` không bao quát đầy đủ các plugin từ Plugin DSL; cần kiểm tra `plugins {}`, `pluginManagement`, convention plugin, version catalog và included build.

Mục tiêu là xác định API/runtime/generator version nào được **chọn thật sự**, không chỉ version khai báo trực tiếp. Các BOM hoặc dependency management có thể đổi version bắc cầu. Một JAR Activation hoặc JAXB API không đúng thế hệ có thể được kéo vào từ client SOAP, framework hoặc thư viện mail.

### 4.3. Kiểm kê môi trường

Ghi rõ:

| Thành phần | Nội dung cần chốt |
|---|---|
| JDK chạy Maven/Gradle | Vendor, major/update version, `JAVA_HOME`, wrapper |
| Compiler/toolchain | Release target, language level, API target |
| Generator JVM | JDK chạy `xjc`/`wsimport` hoặc plugin codegen |
| Runtime JVM | JDK/container image production |
| Framework stack | Servlet/JAX-WS implementation, Jakarta/Javax generation |
| Contract | Version WSDL, XSD, imported schemas, XML namespace |
| Artifact | JAR/WAR/EAR, module path/classpath, shaded/uber-JAR |
| Integration | SOAP endpoints, TLS/WS-Security, MTOM, timeout và authentication |

Đặc biệt, một generator chạy trên JDK 8 có thể tạo source `javax.*` trong khi compiler application chạy trên JDK 21 và framework muốn `jakarta.*`. Nếu không chốt riêng generator JVM và generator version, lỗi dễ bị chẩn đoán nhầm thành lỗi JDK.

## 5. JAXB bên ngoài JDK

### 5.1. JAXB dùng để làm gì?

JAXB (XML Binding) ánh xạ object Java sang XML và ngược lại. Các API thường dùng:

- `JAXBContext` tạo binding context.
- `Marshaller` chuyển object thành XML.
- `Unmarshaller` chuyển XML thành object.
- `@XmlRootElement`, `@XmlElement`, `@XmlAttribute`, `@XmlType` mô tả XML mapping.
- `@XmlAccessorType`, `@XmlSchema` và adapter điều chỉnh cấu trúc binding.

Một model đơn giản ở thế hệ Jakarta:

```java
package com.example.model;

import jakarta.xml.bind.annotation.XmlElement;
import jakarta.xml.bind.annotation.XmlRootElement;

@XmlRootElement(name = "customer")
public class Customer {
    private String name;

    public Customer() {
    }

    @XmlElement
    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
```

Và quá trình marshal:

```java
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.bind.Marshaller;

JAXBContext context = JAXBContext.newInstance(Customer.class);
Marshaller marshaller = context.createMarshaller();
marshaller.setProperty(Marshaller.JAXB_FORMATTED_OUTPUT, Boolean.TRUE);
marshaller.marshal(customer, System.out);
```

Với nhánh `javax`, import chuyển thành `javax.xml.bind.*` và annotations tương ứng. Ý tưởng API gần giống, nhưng không được trộn namespace từ hai thế hệ trong cùng một ví dụ triển khai.

### 5.2. Dependency API và JAXB runtime

Đối với nhánh Jakarta hiện đại, Maven có thể khai báo API và runtime:

```xml
<dependencies>
    <dependency>
        <groupId>jakarta.xml.bind</groupId>
        <artifactId>jakarta.xml.bind-api</artifactId>
        <version>${jaxb.api.version}</version>
    </dependency>
    <dependency>
        <groupId>org.glassfish.jaxb</groupId>
        <artifactId>jaxb-runtime</artifactId>
        <version>${jaxb.runtime.version}</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Các property `jaxb.api.version` và `jaxb.runtime.version` là placeholder cần thay bằng version đã được xác minh **cùng thế hệ Jakarta**. Trong Gradle, cấu hình tương đương có thể là `implementation` cho API và `runtimeOnly` cho runtime; nếu code cần trực tiếp API implementation thì phải chọn scope phù hợp.

Với nhánh `javax`, chọn JAXB API và implementation thế hệ 2.x có package `javax.xml.bind.*`, thường gặp các tọa độ như `javax.xml.bind:jaxb-api` và `org.glassfish.jaxb:jaxb-runtime` thuộc thế hệ tương thích. Một số artifact mang tên `jakarta.xml.bind-api` nhưng version 2.3.x vẫn dùng namespace `javax`; do đó phải xác minh nội dung JAR và release notes, không chỉ dựa vào groupId.

API JAR một mình không đủ để chạy mọi tác vụ JAXB. Ở runtime cần có implementation và các dependency của implementation để `JAXBContext.newInstance(...)` tìm được provider phù hợp.

### 5.3. Các lỗi JAXB điển hình

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `package javax.xml.bind does not exist` | JDK mới không cung cấp JAXB API cũ trên compile classpath | Thêm API `javax` bên ngoài hoặc chuyển source sang `jakarta` và thêm API đúng |
| `package jakarta.xml.bind does not exist` | Thiếu Jakarta JAXB API trên compile classpath | Thêm API đúng thế hệ và scope |
| `JAXBException` báo không tìm được implementation/provider | Có API nhưng không có runtime/provider tương thích | Bổ sung JAXB runtime, kiểm tra provider discovery và classpath |
| `NoClassDefFoundError` liên quan `javax.activation` hoặc `jakarta.activation` | Thiếu hoặc lệch Activation dependency | Đồng bộ API/implementation Activation |
| Runtime không nhận annotation XML | Generated model dùng namespace khác với JAXB runtime hoặc model không đúng | Đồng bộ generator, annotation và runtime |
| Lỗi `ClassCastException` giữa hai kiểu JAXB | Hai hệ namespace hoặc class loader khác nhau | Tách ranh giới, không cast trực tiếp giữa `javax` và `jakarta` |

Không nên xử lý mọi lỗi JAXB bằng cách thêm cả API 2.x và 4.x vào classpath. Sự cùng tồn tại của hai hệ không tự làm framework nhận diện và chuyển đổi model giữa hai hệ.

## 6. JAX-WS bên ngoài JDK

### 6.1. JAX-WS và SOAP contract

JAX-WS (XML Web Services) cung cấp API xây dựng và gọi SOAP web service. Một số khái niệm điển hình:

- `Service` tạo hoặc truy cập service theo WSDL.
- Service Endpoint Interface (SEI) mô tả operation.
- `@WebService`, `@WebMethod` và các annotation metadata.
- `BindingProvider` cho request context, endpoint address, timeout theo implementation.
- `SOAPBinding`, handler chain, SOAP fault và attachment.
- Generator tạo service class, request/response model và client proxy.

API không tự cung cấp một stack HTTP/SOAP hoàn chỉnh. Một ứng dụng thường dùng implementation như **Metro JAX-WS RI** hoặc **Apache CXF** tùy framework và kiến trúc.

### 6.2. Runtime API và implementation phải đồng bộ

Với nhánh Jakarta hiện đại, Maven có thể dùng:

```xml
<dependencies>
    <dependency>
        <groupId>jakarta.xml.ws</groupId>
        <artifactId>jakarta.xml.ws-api</artifactId>
        <version>${jaxws.api.version}</version>
    </dependency>
    <dependency>
        <groupId>com.sun.xml.ws</groupId>
        <artifactId>jaxws-rt</artifactId>
        <version>${metro.version}</version>
    </dependency>
</dependencies>
```

Đây là minh họa theo stack Metro; các version thực tế cần được chọn theo ma trận hỗ trợ chung với JAXB và Activation. Metro runtime có thể kéo thêm nhiều dependency bắc cầu, vì vậy cần đọc dependency graph và bảo đảm không bị override lệch version bởi BOM khác.

Nếu dùng Apache CXF, chọn các module CXF cho frontend JAX-WS và transport phù hợp, chẳng hạn `org.apache.cxf:cxf-rt-frontend-jaxws` cùng transport HTTP tương ứng, theo đúng version CXF được hỗ trợ bởi runtime/framework của dự án. Không trộn tùy tiện Metro và CXF trên cùng classpath chỉ vì cả hai đều có JAX-WS implementation.

Với nhánh `javax`, chọn JAX-WS API và implementation thế hệ 2.x tương ứng. Tên package `javax.xml.ws.*` trong client code cũ không biến thành `jakarta.xml.ws.*` chỉ bằng việc nâng tọa độ runtime.

### 6.3. Endpoint và SOAP client phải được kiểm chứng riêng

Việc nâng API/JAX-WS provider có thể ảnh hưởng các lớp tích hợp khác nhau:

| Vị trí | Cần kiểm tra |
|---|---|
| SOAP client | WSDL lookup, service name, port name, SOAP action, endpoint URL |
| Service endpoint | Annotation, publication, servlet/HTTP transport, lifecycle |
| Binding | SOAP 1.1/1.2, document/literal, header, wrapper style |
| Fault | Checked exception mapping và SOAP Fault detail |
| Security | TLS, WS-Security, signature, certificate, authentication |
| Attachment | MTOM, XOP, MIME, `DataHandler` |
| Operability | Timeout, retry, proxy, tracing, metrics và logging |
| Generated stubs | Package, namespace, `Service` subclass, request/response DTO |

Một ứng dụng có thể build thành công nhưng SOAP request không tương thích với đối tác vì WSDL binding hoặc SOAP envelope đã thay đổi. Vì vậy cần contract test trên XML/SOAP thực tế, không chỉ unit test của proxy.

### 6.4. JAX-WS không phải JAX-RS

JAX-WS chủ yếu gắn với SOAP/XML web service, trong khi JAX-RS/Jakarta REST xử lý mô hình REST. Dự án có thể dùng cả hai, nhưng chuyển SOAP client sang REST không phải yêu cầu bắt buộc của việc nâng JDK.

Đổi sang REST là migration giao thức và contract lớn hơn. Nếu mục tiêu là duy trì SOAP integration khi nâng JDK, việc dùng JAX-WS implementation bên ngoài thường là con đường ít thay đổi nghiệp vụ hơn.

## 7. Activation và MIME attachment

### 7.1. Activation đảm nhận việc gì?

JavaBeans Activation Framework — thường gọi JAF hoặc Activation — cung cấp abstraction cho nội dung có MIME type, `DataSource`, `DataHandler` và cơ chế xử lý nội dung. Nó được dùng trong thư viện mail, SOAP attachment/MTOM và các hệ thống trao đổi dữ liệu có tệp đính kèm.

Ở thế hệ Jakarta:

```java
import jakarta.activation.DataHandler;
import jakarta.activation.DataSource;
```

Một luồng xử lý attachment có thể dùng `DataHandler` bọc `DataSource` rồi chuyển cho SOAP/message framework. Cần đảm bảo API và implementation phù hợp với JAX-WS hoặc mail stack đang dùng.

### 7.2. API Activation không đồng nghĩa với implementation

Với nhánh Jakarta hiện đại, API và implementation thường được phân phối độc lập, chẳng hạn API `jakarta.activation:jakarta.activation-api` và implementation Angus Activation như `org.eclipse.angus:angus-activation`.

Ví dụ Maven:

```xml
<dependencies>
    <dependency>
        <groupId>jakarta.activation</groupId>
        <artifactId>jakarta.activation-api</artifactId>
        <version>${activation.api.version}</version>
    </dependency>
    <dependency>
        <groupId>org.eclipse.angus</groupId>
        <artifactId>angus-activation</artifactId>
        <version>${angus.activation.version}</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Những version phải cùng namespace và nằm trong tổ hợp mà SOAP/mail framework hỗ trợ. Thư viện có thể tự cung cấp provider qua dependency bắc cầu; chỉ thêm trực tiếp khi ứng dụng cần hoặc dependency graph cho thấy thiếu, theo chính sách quản lý dependency của dự án.

### 7.3. Dấu hiệu lệch Activation version

- Compiler thấy `jakarta.activation.DataHandler` nhưng SOAP framework đang cần `javax.activation.DataHandler`.
- Runtime có API nhưng thiếu content handler hoặc implementation.
- Provider tìm sai factory/handler do phiên bản implementation không khớp.
- MTOM attachment không được encode/decode đúng.
- Mail/SMTP library đang dùng namespace khác với stack SOAP.

Kiểm tra cả attachment thực sự, bao gồm MIME type, filename, charset, stream lifecycle, kích thước file, header, transfer encoding và khả năng xử lý tệp lớn. Khởi động SOAP client thành công không chứng minh attachment hoạt động đúng.

## 8. Các công cụ sinh mã không còn nằm trong JDK

### 8.1. XJC — XSD sang Java

`xjc` đọc XML Schema (XSD) và tạo Java model cùng JAXB annotations. Ví dụ nhiệm vụ:

```text
src/main/xsd/customer.xsd
            |
            v
   External XJC tool
            |
            v
target/generated-sources/xjc/com/example/xml/Customer.java
            |
            v
   Java compiler
            |
            v
  Application artifact
```

Trong JDK 8, `xjc` thường được cung cấp cùng JDK. Từ JDK 11, phải cài tool độc lập hoặc dùng Maven/Gradle plugin tích hợp JAXB XJC. Với JAXB RI, tool artifact thường gặp là `org.glassfish.jaxb:jaxb-xjc`, cần đồng bộ thế hệ với JAXB API/runtime.

Ví dụ cách gọi command-line khi đã cài đúng bộ XJC bên ngoài:

```bash
xjc -d target/generated-sources/xjc \
    -p com.example.xml \
    src/main/xsd/customer.xsd
```

Lệnh này giả định đã có executable `xjc` từ bản phân phối/tool riêng và thư mục output đã được chuẩn bị theo yêu cầu của tool. Không kỳ vọng `JAVA_HOME/bin/xjc` tồn tại trên JDK 17/21.

### 8.2. schemagen — Java model sang XSD

`schemagen` tạo XML Schema từ các class Java có JAXB annotations, hữu ích trong workflow Java-first. Tool này cũng phải được cung cấp ngoài JDK hiện đại, ví dụ qua JAXB RI schema generator/tool tương thích.

Nếu dùng Java-first, cần giữ version input class và annotation ổn định. Một thay đổi annotation hoặc package có thể làm XSD được sinh khác so với contract đã công bố, ngay cả khi compile vẫn thành công.

### 8.3. wsimport — WSDL sang JAX-WS client/stubs

`wsimport` đọc WSDL và schema liên quan, tạo Java types và service endpoint proxy. Từ JDK 11, dùng JAX-WS tooling từ bên ngoài, chẳng hạn Metro JAX-WS tools hoặc plugin tương ứng.

Ví dụ command-line khi đã cài bộ tools thích hợp:

```bash
wsimport -keep \
    -s target/generated-sources/wsimport \
    -p com.example.soap.client \
    src/main/wsdl/CustomerService.wsdl
```

Thư mục output và option có thể khác theo bản tool. Quan trọng hơn, **version generator quyết định họ annotation/import được sinh ra**. Source được tạo bởi generator `javax` không tự phù hợp với runtime `jakarta`.

### 8.4. wsgen — endpoint code sang artifact WSDL liên quan

`wsgen` hỗ trợ quy trình Java-first JAX-WS ở các stack cung cấp chức năng này. Trên JDK mới, nó không còn là công cụ tích hợp. Nếu dự án dùng Java-first SOAP, cần chọn JAX-WS implementation/tool phù hợp và xác minh output WSDL cũng như endpoint runtime.

Không phải mọi framework yêu cầu `wsgen`: có stack dùng WSDL-first và tool khác. Đừng thêm lại tool chỉ vì trước đây nó có mặt trong JDK; trước hết xác định pipeline thực tế có gọi nó không.

### 8.5. Công cụ thay thế và vai trò tương đương

| Nhu cầu | Tool/giải pháp ngoài JDK thường gặp | Đầu ra cần kiểm chứng |
|---|---|---|
| XSD → JAXB Java classes | JAXB RI XJC hoặc plugin XJC tương thích | POJO, annotations, `ObjectFactory`, `package-info.java` |
| Java JAXB classes → XSD | JAXB RI schema-generation tool | XML Schema phù hợp contract |
| WSDL → SOAP client/source | Metro JAX-WS tools, Apache CXF `wsdl2java` | SEI, service proxy, JAXB model |
| Java SOAP endpoint → WSDL | Tool JAX-WS phù hợp hoặc framework codegen | WSDL, binding và namespace |
| Tự động hóa build | Maven/Gradle plugin tương ứng | Generated source được nối đúng source set |
| Runtime binding và SOAP | JAXB runtime + Metro/CXF + Activation | Marshalling, transport, SOAP request/response |

Tránh xem “tool thay thế” là tương đương tuyệt đối về output. Hai generator có thể tạo class name, annotation, method signature, date/time mapping hoặc package cấu hình khác nhau từ cùng một schema.

## 9. Sinh mã theo contract: cần quản lý những gì?

### 9.1. Input là nguồn sự thật

Với WSDL-first hoặc XSD-first, **WSDL/XSD và cấu hình binding** là nguồn sự thật. Generated Java source là sản phẩm của bước build.

Lưu cùng repository hoặc artifact registry những thành phần cần thiết để tái tạo:

- WSDL chính và các WSDL/XSD import.
- Binding customization file.
- XML catalog dùng để map URI tới bản local.
- Version của tool và plugin.
- Option package, binding, extension và source target.
- JDK chạy generator và compiler.
- Output directory/source set.
- Quy trình tạo lại source trong CI.

Nếu WSDL import schema từ URL có thể thay đổi, build không còn tái lập. Nên kiểm soát dependency của schema qua local snapshot/catalog và quy định rõ thời điểm cập nhật.

### 9.2. Kiểm tra namespace trong generated source

Sau khi generate, xem import và annotation:

```java
// Code sinh bởi tool cũ:
import javax.xml.bind.annotation.XmlElement;
import javax.xml.ws.Service;
```

hoặc:

```java
// Code sinh bởi tool Jakarta tương thích:
import jakarta.xml.bind.annotation.XmlElement;
import jakarta.xml.ws.Service;
```

Kiểm tra generator cùng hệ namespace với API runtime và framework. Không dùng thay thế chuỗi hàng loạt `javax.` → `jakarta.` rồi mặc định mọi reference sẽ đúng; một số package `javax.xml.*` vẫn là API Java SE và một số generator có dependency nội bộ riêng.

### 9.3. Binding customization có thể phải migrate

Các file binding JAXB/JAX-WS dùng schema, XML namespace, cú pháp và option theo phiên bản tool. Khi chuyển thế hệ, có thể cần cập nhật namespace của binding file và các extension.

Một lỗi thường gặp là tool mới không chấp nhận binding file cũ, hoặc chấp nhận nhưng bỏ qua customization, dẫn tới generated model đổi tên class hoặc kiểu dữ liệu. Hãy kiểm tra log generator và diff output, không chỉ trạng thái exit code.

### 9.4. Không sửa generated source trực tiếp

Nếu cần đổi tên field, package, enum mapping hoặc kiểu ngày giờ, ưu tiên sửa schema hoặc binding customization. Sửa trực tiếp file generated khiến thay đổi mất khi generate lại.

Nếu dự án có lý do phải commit generated source, hãy quy định rõ cách regenerate, cách kiểm tra diff và cách ngăn sửa tay không tái lập được.

## 10. Maven: tổ chức API, runtime và code generation

### 10.1. Dependency profile nhất quán

Một mẫu Maven cho ứng dụng JAXB/JAX-WS **theo Jakarta namespace** có thể khai báo các thành phần chính như sau:

```xml
<dependencies>
    <!-- Compile-time API -->
    <dependency>
        <groupId>jakarta.xml.bind</groupId>
        <artifactId>jakarta.xml.bind-api</artifactId>
        <version>${jaxb.api.version}</version>
    </dependency>
    <dependency>
        <groupId>jakarta.xml.ws</groupId>
        <artifactId>jakarta.xml.ws-api</artifactId>
        <version>${jaxws.api.version}</version>
    </dependency>
    <dependency>
        <groupId>jakarta.activation</groupId>
        <artifactId>jakarta.activation-api</artifactId>
        <version>${activation.api.version}</version>
    </dependency>

    <!-- Ví dụ runtime stack Metro -->
    <dependency>
        <groupId>com.sun.xml.ws</groupId>
        <artifactId>jaxws-rt</artifactId>
        <version>${metro.version}</version>
    </dependency>
</dependencies>
```

Các biến version là placeholder, **không phải bộ version mặc định được bảo đảm tương thích**. Chọn theo BOM, release notes và dependency tree của stack. Ví dụ runtime Metro có thể cung cấp JAXB/Activation transitive dependencies; tránh ghim các version xung đột khi chưa xem graph.

Nếu chỉ dùng JAXB, không cần thêm JAX-WS. Nếu dùng Apache CXF thay Metro, chọn tập module CXF thích hợp và bỏ runtime provider không sử dụng. Nếu vẫn cần `javax`, phải dùng API/runtime nhánh phù hợp `javax`, không copy nguyên mẫu Jakarta trên.

### 10.2. Tích hợp WSDL code generation bằng CXF Codegen Plugin

Một cấu hình Maven phổ biến với Apache CXF:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.cxf</groupId>
            <artifactId>cxf-codegen-plugin</artifactId>
            <version>${cxf.version}</version>
            <executions>
                <execution>
                    <id>generate-soap-client</id>
                    <phase>generate-sources</phase>
                    <goals>
                        <goal>wsdl2java</goal>
                    </goals>
                    <configuration>
                        <wsdlOptions>
                            <wsdlOption>
                                <wsdl>${project.basedir}/src/main/wsdl/CustomerService.wsdl</wsdl>
                            </wsdlOption>
                        </wsdlOptions>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

Chọn version plugin CXF và CXF runtime cùng nhánh theo ma trận framework. CXF thế hệ cũ có thể tạo source `javax`, trong khi các nhánh Jakarta hiện đại tạo source `jakarta`. Cần đọc generated source để xác minh thực tế.

Source thường được sinh dưới thư mục build được plugin cấu hình và nối vào compilation lifecycle. Hãy kiểm tra output directory, target language/runtime và source roots thực tế. Không dùng hai plugin khác nhau cùng generate vào một thư mục làm các file chồng lấn.

### 10.3. XJC trong Maven

Có nhiều plugin XJC độc lập và plugin tích hợp với JAXB RI. Khi chọn, phải kiểm tra:

- Plugin được duy trì và chạy trên JDK build đang sử dụng.
- Tọa độ tool XJC và version JAXB API/runtime tương thích.
- XML binding customization, catalog và schema imports.
- Generated package và output directory.
- Việc gắn generated source vào Maven compile phase.
- Có thể generate lại từ clean checkout không.

Một số dự án dùng JAXB/XJC Maven plugin của cộng đồng, một số dùng plugin theo hệ Metro/CXF. Không nên giữ một plugin lâu năm chỉ vì nó từng chạy trên JDK 8; plugin đó có thể phụ thuộc vào JDK tools hoặc JDK internals không còn tồn tại.

## 11. Gradle: tách runtime dependency và generator task

### 11.1. Thư viện runtime

Ví dụ Groovy DSL cho JAXB Jakarta:

```groovy
dependencies {
    implementation "jakarta.xml.bind:jakarta.xml.bind-api:${jaxbApiVersion}"
    runtimeOnly "org.glassfish.jaxb:jaxb-runtime:${jaxbRuntimeVersion}"
}
```

Với JAX-WS, bổ sung API/runtime provider phù hợp nếu ứng dụng thực sự dùng SOAP. Các biến version phải được định nghĩa trong build và lựa chọn theo compatibility matrix.

### 11.2. Configuration riêng cho XJC

Không nên đưa toàn bộ generator tool lên runtime classpath của ứng dụng chỉ để chạy task sinh mã. Tạo configuration cho tool và một task riêng:

```groovy
configurations {
    xjcTool
}

dependencies {
    xjcTool "org.glassfish.jaxb:jaxb-xjc:${jaxbToolVersion}"
}

def generatedXjcDir = layout.buildDirectory.dir("generated/sources/xjc/main")

tasks.register("generateJaxb", JavaExec) {
    classpath = configurations.xjcTool
    mainClass = "com.sun.tools.xjc.XJCFacade"

    inputs.file("src/main/xsd/customer.xsd")
    outputs.dir(generatedXjcDir)

    doFirst {
        generatedXjcDir.get().asFile.mkdirs()
    }

    args "-d", generatedXjcDir.get().asFile.absolutePath,
         "-p", "com.example.xml",
         file("src/main/xsd/customer.xsd").absolutePath
}

sourceSets {
    main {
        java.srcDir(generatedXjcDir)
    }
}

tasks.named("compileJava") {
    dependsOn(tasks.named("generateJaxb"))
}
```

Đây là mẫu tổ chức task với JAXB RI XJC; **entrypoint, classpath và cú pháp CLI phải được xác nhận theo version XJC đã chọn**, nhất là khi chuyển major version. Những generator khác, chẳng hạn CXF wsdl2java hoặc Metro tools, có main class và option riêng.

Những nguyên tắc đáng giữ lại:

- Tool dependency nằm trên `xjcTool`, không mặc nhiên trở thành runtime dependency.
- Task có input/output rõ để build tái lập và hỗ trợ caching/incremental behavior.
- Generated source nằm trong `build/`, không ghi đè source viết tay.
- `compileJava` phụ thuộc vào generator khi output của generator được biên dịch.
- Build sạch phải regenerate được toàn bộ source cần thiết.

### 11.3. Plugin và JDK chạy generator

Cấu hình Java toolchain cho compiler không nhất thiết tự đổi JDK chạy mọi `JavaExec` task hoặc plugin. Cần xác định JDK được sử dụng để chạy generator, JDK compiler, source/bytecode target và JVM runtime production.

Nếu compiler JDK 21 nhưng artifact vẫn phải chạy Java 17, hãy cấu hình `--release 17` ở các task `JavaCompile`, đồng thời chọn generator tạo source tương thích Java 17 và đúng namespace. Cấu hình release không tự làm JAX-WS hoặc JAXB runtime mới tương thích với framework cũ.

## 12. JPMS, classpath và module path

### 12.1. Không thể “bật lại” module đã bị xóa

Trên JDK 11+, việc thêm:

```bash
java --add-modules java.xml.bind -jar app.jar
```

không khôi phục được module JAXB từng được bundled trong JDK cũ. Nếu module không có trong runtime/module path, JVM báo không tìm thấy module. Các tùy chọn `--add-opens` và `--add-exports` cũng không tạo lại class hoặc module đã bị loại bỏ.

Giải pháp đúng là cung cấp API và implementation dưới dạng dependency bên ngoài, rồi cấu hình classpath/module path phù hợp.

### 12.2. Module descriptor và automatic module

Một ứng dụng có `module-info.java` có thể cần khai báo dependency module của JAXB/JAX-WS/Activation theo tên module mà artifact thực tế cung cấp. Tên module có thể là explicit module name hoặc automatic module name tùy version/thư viện.

Không suy ra module name chỉ từ Maven artifactId. Kiểm tra JAR manifest, module descriptor và kết quả phân tích:

```bash
jar --describe-module --file path/to/library.jar
jdeps --print-module-deps path/to/application.jar
```

Các artifact có split package, automatic module hoặc service provider wiring không phù hợp có thể chạy trên classpath nhưng thất bại trên module path. Hãy chọn một chiến lược đóng gói có chủ đích và test trên cấu hình runtime đích.

### 12.3. ServiceLoader và provider discovery

JAXB và JAX-WS implementation thường dùng cơ chế provider/factory discovery. Khi đóng gói uber-JAR, shading hoặc minimization, các file `META-INF/services` và resource metadata có thể bị mất hoặc không được merge.

Nếu API compile thành công nhưng runtime không tìm được provider, hãy kiểm tra:

- Runtime JAR có được đóng gói vào artifact không.
- `META-INF/services` và metadata provider còn nguyên không.
- Có nhiều provider xung đột trên classpath không.
- Class loader nào đang nạp API và implementation.
- Provider thuộc cùng thế hệ `javax`/`jakarta` không.
- Module path có khai báo service usage/provider đúng không.

Không nên dùng workaround bằng cách ép classpath ngẫu nhiên cho tới khi chạy được. Cần xác định provider cụ thể sẽ được dùng và bảo đảm build tạo artifact có thể tái lập.

## 13. An toàn XML: không bỏ qua XXE và nguồn schema

Migration có thể đổi parser implementation, generator, thư viện XML và cách xử lý schema. Đây là thời điểm cần xác định rõ chính sách đối với XML External Entities (XXE), DTD và external resource loading.

### 13.1. Bảo vệ ở đầu vào XML

Khi unmarshalling dữ liệu từ nguồn không tin cậy, không giả định JAXB runtime tự động chặn toàn bộ external entities. Hãy cấu hình parser XML ở điểm nhận dữ liệu theo chính sách bảo mật, và chỉ cung cấp cho JAXB nguồn parser đã được cấu hình.

Ví dụ với StAX khi môi trường và provider hỗ trợ các thuộc tính:

```java
XMLInputFactory inputFactory = XMLInputFactory.newFactory();
inputFactory.setProperty(XMLInputFactory.SUPPORT_DTD, Boolean.FALSE);
inputFactory.setProperty(
    XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES,
    Boolean.FALSE
);

try (InputStream in = Files.newInputStream(xmlPath)) {
    XMLStreamReader reader = inputFactory.createXMLStreamReader(in);
    try {
        Object value = unmarshaller.unmarshal(reader);
        // Xử lý value.
    } finally {
        reader.close();
    }
}
```

Đây là minh họa chính sách parser, không phải lời bảo đảm an toàn với mọi provider. Cần xác nhận implementation có chấp nhận và thực thi thuộc tính, kiểm tra thêm entity expansion/resource limit và test XML độc hại theo chính sách tổ chức.

### 13.2. WSDL/XSD import ngoài mạng

`wsimport` và `xjc` có thể cần import schema từ đường dẫn hoặc URL ngoài. Tránh để CI tự tải tài nguyên không kiểm soát từ mạng công cộng trong mỗi lần build. Sử dụng XML catalog, bản schema đã pin hoặc repository được phép, kiểm tra checksum và giới hạn quyền truy cập của generator.

Tài liệu WSDL/XSD từ đối tác không nên tự động được coi là input tin cậy. Generator chạy trong build có thể đọc file, truy cập URL và tạo mã nguồn; cần xem xét quyền môi trường và nguồn phụ thuộc.

## 14. Quy trình migration thực tế

### Bước 1: Chụp baseline

Ghi commit, JDK vendor/build, Maven/Gradle Wrapper, framework, dependency tree, WSDL/XSD và bản generated source hiện tại. Giữ build log và test baseline để phân biệt lỗi đã có từ trước.

### Bước 2: Xác định công nghệ thực sự đang sử dụng

Phân biệt JAXB-only, SOAP client, SOAP server, Java-first hoặc WSDL-first, MTOM/attachment. Không thêm JAX-WS runtime cho ứng dụng chỉ cần marshal/unmarshal XML.

### Bước 3: Chọn namespace target

Quyết định giữ `javax` để giảm thay đổi hoặc chuyển sang `jakarta` cùng với framework. Không chọn hai hướng trong một module mà không xác định rõ ranh giới adapter.

### Bước 4: Chọn bộ API/runtime/provider tương thích

Đối chiếu vendor documentation của JAXB RI, Metro hoặc CXF, Activation provider và framework. Xác định version có hỗ trợ JDK build/runtime và Jakarta/Javax generation đã chọn.

### Bước 5: Tách code generator khỏi JDK

Pin XJC/wsimport/wsgen/schemagen tool version trong Maven/Gradle hoặc tool distribution. Thay đường dẫn dựa vào `JAVA_HOME/bin` bằng task/goal dùng dependency bên ngoài. Chốt input/output và generated source roots.

### Bước 6: Generate sạch và kiểm tra output

Chạy lại generator từ clean checkout trên môi trường chuẩn, rồi so sánh generated source. Chú ý package, annotation, enum, date/time type, service/port names, operation signature và binding customization.

### Bước 7: Compile và đóng gói

Compile toàn bộ source viết tay và generated source trên JDK đích. Kiểm tra dependency compile/runtime, shaded JAR, service provider metadata, JPMS và Activation library cần thiết.

### Bước 8: Kiểm tra contract XML/SOAP

Thực hiện round-trip JAXB, schema validation, SOAP request/response, fault mapping, headers, TLS, timeout và attachment. Đối với hệ thống trao đổi với đối tác, dùng WSDL/XSD và payload đã được chấp thuận làm contract test.

### Bước 9: Thử nghiệm trên artifact cuối

Chạy đúng JAR/WAR/container sẽ phát hành, không chỉ classpath IDE. Nếu hệ thống dùng application server, kiểm tra xem server cung cấp API/provider nào và có xung đột với các thư viện application đóng gói không.

### Bước 10: Phát hành và rollback

Phát hành theo chiến lược canary/rolling/blue-green tùy hệ thống. Lưu artifact cũ, version WSDL/XSD, cấu hình provider và image runtime; xác định điều kiện rollback và khả năng tương thích dữ liệu XML giữa hai phiên bản.

## 15. Ví dụ xuyên suốt: ứng dụng SOAP từ JDK 8 lên JDK 21

Giả sử một dịch vụ cũ dùng JDK 8 và có:

- `javax.xml.bind` annotations trên DTO.
- SOAP client dùng `javax.xml.ws.Service`.
- Generator `wsimport` được gọi qua script `$JAVA_HOME/bin/wsimport`.
- SOAP response có file đính kèm dùng `javax.activation.DataHandler`.
- CI build bằng JDK 8; mục tiêu mới là JDK 21.

### 15.1. Chẩn đoán đầu tiên

Nếu chỉ đổi JDK sang 21, build có thể lỗi ở hai lớp độc lập:

1. Script không còn tìm được `wsimport` trong JDK.
2. Compiler không tìm được `javax.xml.bind`, `javax.xml.ws` hoặc `javax.activation` nếu không có dependency ngoài.

Ngay cả khi thêm API JAR làm compile pass, runtime vẫn có thể thiếu JAX-WS/JAXB provider hoặc Activation implementation.

### 15.2. Phương án ít thay đổi: giữ javax

Nếu framework và runtime hiện tại còn hỗ trợ nhánh `javax`:

1. Giữ import và WSDL contract ban đầu.
2. Chọn JAXB API/runtime, JAX-WS API/implementation và Activation dependency thế hệ `javax` tương thích JDK 21.
3. Dùng bộ generator ngoài JDK tạo source `javax`.
4. Đồng bộ các transitive dependencies và service provider.
5. Generate sạch, compile, chạy SOAP contract test và MTOM test.
6. Phát hành theo kế hoạch và ghi rõ đây là tách dependency khỏi JDK, chưa phải migration sang Jakarta namespace.

Ưu điểm là phạm vi source change nhỏ. Nhược điểm là phiên bản framework/implementation cũ có thể có giới hạn bảo trì hoặc không còn đáp ứng chính sách hỗ trợ. Không giữ nhánh `javax` vô thời hạn nếu hệ sinh thái của tổ chức đã yêu cầu Jakarta.

### 15.3. Phương án nâng stack: chuyển sang jakarta

Nếu mục tiêu bao gồm framework Jakarta hiện đại:

1. Chốt version framework và SOAP/JAXB/Activation stack Jakarta.
2. Nâng generator cùng thế hệ để tạo source `jakarta.*`.
3. Chuyển import và annotation của mã viết tay.
4. Migrate binding customization nếu tool mới yêu cầu.
5. Kiểm tra class public, method descriptor và consumer đã compile: `javax` và `jakarta` là binary names khác nhau.
6. Kiểm tra dữ liệu đã serialize/metadata theo class name nếu ứng dụng sử dụng.
7. Chạy XML/SOAP contract test, security/attachment test và integration test trên JDK 21.
8. Ghi migration guide cho consumer và phương án rollback.

Thay đổi namespace nên được xem như một bước migration API thực sự. Chỉ thay dependency version mà không regenerate source hoặc chuyển import tương ứng sẽ không hoàn thành công việc.

## 16. Các lỗi thường gặp và hướng điều tra

| Lỗi hoặc hiện tượng | Nguyên nhân có thể | Bước kiểm tra |
|---|---|---|
| `package javax.xml.bind does not exist` | API JAXB cũ không bundled trong JDK 11+ | Xem compile classpath; thêm đúng API ngoài JDK hoặc chuyển namespace |
| `package jakarta.xml.ws does not exist` | Thiếu JAX-WS API Jakarta | Xem dependency scope và version API |
| `xjc: command not found` | XJC không còn trong JDK hiện đại | Thay bằng tool/plugin XJC bên ngoài |
| `wsimport: command not found` | wsimport không còn trong JDK | Tích hợp Metro tools hoặc CXF codegen |
| JAXB provider not found | Có API nhưng thiếu runtime/provider | Xem runtime dependency và service metadata |
| `NoClassDefFoundError: javax/activation/DataHandler` | Thiếu Activation cũ hoặc library đang lệch thế hệ | Xác định namespace do caller yêu cầu |
| Generated code import `javax` nhưng application dùng `jakarta` | Generator và runtime khác thế hệ | Chọn lại generator, regenerate và kiểm tra binding file |
| `ClassNotFoundException` trong SOAP client | Thiếu JAX-WS implementation hoặc class được generate | Kiểm tra JAR cuối, class loader, generated roots |
| WSDL client compile nhưng không gọi được service | Binding, endpoint, TLS, SOAP action, security hoặc transport | Chạy SOAP contract/integration test |
| MTOM attachment bị lỗi | Activation/provider/MIME hoặc stream lifecycle không đúng | Test attachment thật và dependency graph |
| Chạy IDE được, packaged JAR lỗi | Shading làm mất service metadata hoặc runtime JAR | Kiểm tra artifact cuối và `META-INF/services` |
| Build sạch cho output khác | Tool không pin, schema remote thay đổi hoặc environment-dependent output | Pin tool/schema, dùng catalog và diff generated source |
| JPMS báo module not found | Cố dùng module JDK đã bị xóa hoặc module path thiếu library | Cung cấp external dependency, kiểm tra module descriptor |

Một lỗi có thể có nhiều nguyên nhân. Quy trình tốt nhất là xác định **đúng class và class loader gây lỗi**, dependency version được chọn, namespace và giai đoạn lỗi (generate, compile, startup hay runtime request) trước khi sửa.

## 17. Những ngộ nhận cần tránh

### “Thêm `--add-modules java.xml.bind` là đủ”

Không đúng trên JDK 11+ nếu module đó không còn tồn tại trong JDK. Cần cung cấp API và implementation ngoài JDK.

### “Jakarta JAXB API là bản thay thế nhị phân của JAXB javax”

Không đúng khi namespace đổi. `javax.xml.bind.JAXBContext` và `jakarta.xml.bind.JAXBContext` là hai kiểu khác tên. Cần xử lý source, generated code, framework và consumer compatibility.

### “Có `jaxb-api` nên marshaling chắc chắn chạy”

Không đủ. API cần provider/runtime; hoạt động XML còn phụ thuộc model annotation, parser, security và binding configuration.

### “Có `jaxws-api` thì SOAP client dùng được”

Không đủ. SOAP client/server cần implementation, transport, dependency và đôi khi generator. Cần test với service thật hoặc contract test tương đương.

### “Generated source đã được commit thì không cần generator”

Có thể build hiện tại không gọi generator, nhưng dự án vẫn phụ thuộc vào khả năng tạo lại source khi schema thay đổi. Cần ghi rõ source of truth và quyết định có chủ đích về việc pin/duy trì generator.

### “Tất cả `javax.xml.*` phải thành `jakarta.xml.*`”

Không đúng. Một số API XML processing của Java SE vẫn ở `javax.xml.*`. Chỉ chuyển các API có namespace migration tương ứng.

### “JDK 21 mới xóa JAXB/JAX-WS”

Không đúng. Mốc loại bỏ là JDK 11. Nếu hệ thống từng chạy trên JDK 17, cần xem điều gì đang cung cấp các thành phần đó.

### “Sửa import là đủ để chuyển sang Jakarta”

Không đủ. Generated source, annotation metadata, runtime provider, Activation, SOAP transport, module path, test và các consumer có thể vẫn phụ thuộc namespace cũ.

## 18. Tiêu chí hoàn thành và hồ sơ bàn giao

Một đợt migration JAXB/JAX-WS/Activation có thể xem là sẵn sàng phát hành khi nhóm có các bằng chứng sau:

1. **Inventory:** vị trí sử dụng JAXB, JAX-WS, Activation, WSDL/XSD và generator.
2. **Version matrix:** JDK build/runtime, framework, API, implementation, provider, generator và plugin; ghi rõ `javax` hoặc `jakarta`.
3. **Dependency graph:** version được chọn ở compile/runtime/test/tool classpath, không có xung đột chưa được xử lý.
4. **Codegen record:** tool version, command/plugin config, schema/binding input, generated output và khả năng tái tạo.
5. **Source change record:** import, annotation, package, config, module descriptor, service metadata và adapter.
6. **JAXB tests:** marshal/unmarshal, XML schema validation, namespace, null/nillable, date/time, encoding và dữ liệu đặc biệt.
7. **SOAP tests:** WSDL compatibility, request/response/fault, headers, endpoint, auth, TLS, WS-Security và MTOM attachment.
8. **Security evidence:** XML parser settings, XXE/DTD policy, schema import policy và dependency vulnerability review.
9. **Artifact verification:** JAR/WAR/container cuối có provider, metadata và runtime đúng.
10. **Release plan:** owner, rollout, monitoring, rollback, compatibility limitations và tài liệu vận hành.

### Checklist triển khai

- [ ] Đã phân biệt JAXB/JAX-WS/Activation với các API XML Java SE vẫn còn trong JDK.
- [ ] Đã xác nhận mốc JDK 11 và loại bỏ giả định tool nằm trong `JAVA_HOME/bin`.
- [ ] Đã chọn namespace `javax` hoặc `jakarta` theo framework và runtime.
- [ ] API và implementation/provider cùng thế hệ, không chỉ có API JAR.
- [ ] JAXB runtime được đóng gói đúng và provider discovery hoạt động.
- [ ] JAX-WS implementation/transport hoạt động trong artifact cuối.
- [ ] Activation API/implementation tương thích với attachment/mail stack.
- [ ] XJC, wsimport, wsgen và schemagen đang dùng được pin version ngoài JDK.
- [ ] Generated source được tạo lại từ WSDL/XSD/binding đã kiểm soát.
- [ ] Không còn import/annotation sai namespace trong generated source.
- [ ] Plugin codegen chạy trên JDK build và không gây xung đột dependency.
- [ ] Module path, ServiceLoader và `META-INF/services` được xác minh.
- [ ] XML parser có chính sách XXE/DTD và external resource phù hợp.
- [ ] Có JAXB round-trip tests và SOAP contract tests.
- [ ] MTOM/MIME attachment đã được kiểm tra trên payload đại diện.
- [ ] Đã kiểm thử artifact cuối trên đúng JDK/container production.
- [ ] Có log, artifact checksum, release note và phương án rollback.

Khi chuyển từ JDK cũ sang JDK hiện đại, JAXB, JAX-WS và Activation không biến mất khỏi hệ sinh thái Java; chúng **không còn là những thành phần mà ứng dụng có thể mặc định lấy từ JDK**. Migration thành công đòi hỏi chọn đúng thế hệ namespace, khai báo đủ API và implementation, đưa generator ra khỏi phụ thuộc ngầm vào JDK, sau đó kiểm chứng XML/SOAP contract trên artifact cuối. Cách tiếp cận này giúp build tái lập, giảm lỗi classpath và giữ các tích hợp SOAP/XML hoạt động ổn định qua nhiều phiên bản JDK.
