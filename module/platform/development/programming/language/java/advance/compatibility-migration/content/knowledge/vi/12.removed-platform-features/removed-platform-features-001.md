# Java EE và CORBA không còn đi kèm JDK: xác định dependency thay thế

## 1. Bối cảnh: vì sao ứng dụng Java cũ đột nhiên thiếu API?

Khi chuyển hệ thống từ JDK 8 sang JDK 11 hoặc các phiên bản mới hơn, nhiều dự án gặp lỗi biên dịch hoặc khởi động dù phần mã nghiệp vụ gần như không thay đổi. Những lỗi điển hình gồm không tìm thấy package javax.xml.bind, javax.xml.ws, javax.activation hoặc org.omg.CORBA; công cụ wsimport/xjc biến mất; hay ứng dụng không tìm được implementation JAXB/JAX-WS khi chạy.

Nguyên nhân quan trọng là **JEP 320 — Remove the Java EE and CORBA Modules**: từ **JDK 11**, một tập module Java EE và CORBA từng được phân phối cùng JDK đã bị loại bỏ. Trước đó, ở JDK 9 và 10 các module này vẫn có mặt nhưng đã bị đánh dấu deprecated for removal. Một số ứng dụng JDK 8 từng sử dụng chúng mà không hề khai báo dependency bên ngoài, nên sau khi nâng JDK sẽ lộ ra sự phụ thuộc ngầm.

Thay đổi này không có nghĩa toàn bộ Java EE biến mất, cũng không có nghĩa tất cả package bắt đầu bằng javax đều không còn tồn tại. Nó có nghĩa những API, công cụ và implementation cụ thể trước đây do JDK cung cấp không còn được bảo đảm có sẵn trên classpath/module path. Muốn tiếp tục dùng chức năng tương ứng, ứng dụng cần **xác định dependency độc lập hoặc lựa chọn công nghệ thay thế**.

Mục tiêu của bài học:

- Nhận diện chính xác module Java EE/CORBA và công cụ bị loại khỏi JDK.
- Phân biệt API thuộc Java SE còn tồn tại với API Java EE đã tách khỏi JDK.
- Tìm nguồn dependency API và runtime implementation theo đúng thế hệ javax hoặc jakarta.
- Xử lý trường hợp thư viện, generated code, plugin build và container vẫn phụ thuộc công nghệ cũ.
- Đánh giá khi nào có thể thêm dependency, khi nào cần thay framework/giao thức.
- Tạo ma trận thay thế và kiểm chứng migration trên JDK mục tiêu.

## 2. Những module bị loại bỏ khi chuyển sang JDK 11

Các module sau là phạm vi chính cần rà soát khi nâng từ JDK 8/9/10:

| Module từng có trong JDK 9/10 | Công nghệ hoặc package thường gặp | Hướng thay thế |
|---|---|---|
| java.xml.bind | JAXB; javax.xml.bind và annotation liên quan | Dùng JAXB API và JAXB runtime độc lập, chọn thế hệ javax hoặc jakarta phù hợp. |
| java.xml.ws | JAX-WS; javax.xml.ws, SOAP service/client | Dùng JAX-WS API và runtime độc lập hoặc framework SOAP như Apache CXF. |
| java.activation | JavaBeans Activation Framework; javax.activation | Thêm Activation API và implementation thích hợp, hoặc Jakarta Activation ở stack mới. |
| java.xml.ws.annotation | Một số Common Annotations, ví dụ javax.annotation.Resource / PostConstruct | Dùng Common Annotations API độc lập, tương ứng với thế hệ framework. |
| java.transaction | Tập con Java Transaction API từng được JDK cung cấp | Dùng API transaction độc lập khi ứng dụng cần JTA; xác định rõ phần đang dùng. |
| java.corba | CORBA, IIOP, các kiểu org.omg.*, javax.rmi.CORBA | Chọn ORB độc lập được bảo trì và tương thích, hoặc chuyển giao thức/kiến trúc. |
| java.se.ee | Aggregator module gom nhóm các module trên | Bỏ phụ thuộc aggregator và khai báo từng API cần thiết; không có JAR thay thế 1:1. |

Hai module công cụ cũng bị loại bỏ:

| Module công cụ | Công cụ JDK cũ | Giải pháp |
|---|---|---|
| jdk.xml.bind | xjc, schemagen | Dùng JAXB code-generation tool/plugin được phân phối độc lập. |
| jdk.xml.ws | wsimport, wsgen | Dùng JAX-WS/Metro hoặc CXF tooling/plugin độc lập. |

Một số JDK cũ còn đi kèm implementation hoặc tool liên quan dưới dạng chi tiết triển khai. Sau JDK 11 không được giả định runtime chỉ cần một API JAR là sẽ tự có provider thích hợp.

### 2.1. Không đánh đồng mọi javax.* với phần bị loại bỏ

Nhiều package javax vẫn thuộc Java SE và còn tồn tại trong JDK hiện đại, ví dụ:

- javax.xml.parsers, javax.xml.transform, javax.xml.stream và javax.xml.namespace thuộc API xử lý XML của Java SE.
- javax.crypto thuộc API mật mã của Java SE.
- javax.sql và các API liên quan JDBC thuộc Java SE.
- javax.transaction.xa thuộc phần hỗ trợ XA trong module java.sql của Java SE.
- javax.annotation.processing thuộc Java compiler API, không phải Common Annotations của Java EE.

Ngược lại, các API như javax.servlet hoặc javax.persistence vốn không phải API mặc định của JDK SE, dù chúng dùng tiền tố javax. Một số API đã tách khỏi JDK từ Java 11; một số khác chưa từng nằm trong JDK.

Vì vậy, thao tác tìm và thay tất cả javax bằng jakarta là sai. Cần phân loại theo **API cụ thể, version framework, module sở hữu, dependency hiện tại và hợp đồng tương thích**.

### 2.2. Không thể dùng --add-modules để khôi phục module đã bị xóa

Trên JDK 9/10, ứng dụng có thể tạm thời kích hoạt các module deprecated trong JDK bằng tùy chọn như:

~~~bash
java --add-modules java.xml.bind -jar application.jar
~~~

Trên JDK 11 trở lên, module java.xml.bind của JDK không còn để kích hoạt. Nếu vẫn yêu cầu module đó theo tên cũ, ứng dụng có thể gặp lỗi trong quá trình khởi tạo layer/module, vì module được yêu cầu không tìm thấy.

Do đó, **--add-modules không phải giải pháp migration lâu dài** cho thành phần đã bị loại bỏ. Phải bổ sung dependency hoặc thay công nghệ, đồng thời cập nhật build và runtime packaging.

## 3. Nhận diện sự phụ thuộc trước khi chọn thư viện thay thế

Đừng bắt đầu bằng cách thêm ngẫu nhiên nhiều JAR có tên JAXB, Jakarta hoặc CORBA. Hãy xác định ứng dụng đang phụ thuộc chính xác vào chức năng nào.

### 3.1. Khảo sát mã nguồn

Tìm các import, fully qualified name, cấu hình và chuỗi gọi API thường gặp:

~~~text
javax.xml.bind.*
javax.xml.ws.*
javax.activation.*
javax.annotation.*
javax.transaction.*
org.omg.*
javax.rmi.CORBA.*
com.sun.xml.internal.*
com.sun.xml.bind.internal.*
~~~

Trong môi trường có ripgrep:

~~~bash
rg -n "javax[.]xml[.](bind|ws)|javax[.]activation|javax[.]annotation|javax[.]transaction|org[.]omg|javax[.]rmi[.]CORBA|com[.]sun[.]xml[.].*internal" src
~~~

Trên PowerShell có thể tìm trong source Java:

~~~powershell
Get-ChildItem -Recurse -File -Filter *.java -Path src |
    Select-String -Pattern 'javax\.xml\.(bind|ws)|javax\.activation|javax\.annotation|javax\.transaction|org\.omg|javax\.rmi\.CORBA'
~~~

Lưu ý regex chỉ là điểm khởi đầu. Mã có thể sử dụng reflection, tên class trong XML/YAML, generated code, service provider configuration, WSDL/XSD hoặc các module được đóng gói tách rời.

### 3.2. Khảo sát lỗi compiler và runtime

| Triệu chứng | Giả thuyết ban đầu | Điều cần xác minh |
|---|---|---|
| package javax.xml.bind does not exist | Thiếu JAXB API trên compile classpath. | Build dependency và namespace mà source sử dụng. |
| NoClassDefFoundError: javax/xml/bind/JAXBContext | Artifact runtime thiếu JAXB API hoặc nạp sai version. | Runtime classpath, fat JAR/container image, dependency conflict. |
| JAXBException không tìm được implementation/provider | Có API nhưng thiếu JAXB runtime hoặc provider không được tìm thấy. | Runtime dependency, service provider files, module path/classloader. |
| package javax.xml.ws does not exist | Thiếu JAX-WS API. | SOAP framework được dùng và version tương thích. |
| wsimport hoặc xjc: command not found | Tool từng đi kèm JDK không còn. | Build plugin/code-generation workflow. |
| package org.omg.CORBA does not exist | Phụ thuộc CORBA/IIOP đã bị loại khỏi JDK. | ORB, IDL stub và giao thức giao tiếp thực tế. |
| javax.annotation.PostConstruct không tồn tại | Common Annotations API chưa được bổ sung hoặc namespace đã đổi. | Framework version và dependency annotations. |
| ClassNotFoundException: jakarta.xml.bind.* | Runtime/compile stack đang dùng namespace Jakarta nhưng artifact thiếu API/implementation tương ứng. | Version thư viện và runtime provider. |

Một exception tương tự cũng có thể do dependency xung đột hoặc runtime nạp bản JAR khác với bản compile. Vì vậy, trước khi quyết định thêm dependency phải kiểm tra classpath thực tế.

### 3.3. Kiểm tra dependency graph

Đối với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jaxb --configuration runtimeClasspath
~~~

Đối với Maven:

~~~bash
./mvnw dependency:tree
~~~

Các lệnh chỉ là công cụ để người thực hiện migration dùng trong dự án thật; cần điều chỉnh configuration/module nếu dự án không có runtimeClasspath hoặc không sử dụng Java plugin.

Mục đích là phát hiện:

- API JAR có mặt ở compile nhưng không có ở runtime.
- Hai thế hệ javax và jakarta cùng xuất hiện không có chủ đích.
- Nhiều phiên bản JAXB/JAX-WS/Activation được kéo vào gián tiếp.
- Dependency bị khai báo scope provided dù môi trường triển khai không cung cấp.
- Application server hoặc framework tự cung cấp provider và gây conflict với provider đóng gói.

### 3.4. Phân tích artifact đã biên dịch

Với JAR chưa có source, có thể dùng jdeps:

~~~bash
jdeps --multi-release 11 --missing-deps --class-path "lib/*" application.jar
~~~

Trên Windows, classpath separator và đường dẫn cần điều chỉnh. Khi phân tích Java bytecode, jdeps giúp tìm dependency không phân giải được trong điều kiện classpath đã cung cấp, nhưng một kết quả không có cảnh báo không chứng minh tất cả chức năng dynamic/reflection đều tương thích.

Khi cần xác định class bị thiếu, có thể xem:

~~~bash
jar tf application.jar
javap -classpath application.jar -verbose com.example.LegacyClient
~~~

Đừng nhầm jdeps --jdk-internals với kiểm kê toàn bộ API Java EE: tùy chọn đó tập trung vào JDK internal APIs, còn JEP 320 chủ yếu liên quan các module từng được phân phối chính thức rồi bị loại bỏ.

## 4. Xác định dependency thay thế cho JAXB

### 4.1. JAXB có hai lớp: API và implementation

JAXB (Java Architecture for XML Binding) chuyển đổi XML và object Java, thường dùng với JAXBContext, Marshaller, Unmarshaller cùng các annotation XML.

Để chạy ngoài JDK cũ, ứng dụng thường cần:

1. **JAXB API:** cung cấp kiểu, annotation và interface để source compile.
2. **JAXB runtime implementation:** thực hiện binding/marshalling ở runtime.

Chỉ thêm API mà thiếu runtime có thể dẫn tới lỗi provider/implementation. Chỉ thêm runtime nhưng chọn API không tương thích cũng có thể lỗi liên kết hoặc không tìm được service.

### 4.2. Giữ code javax.xml.bind

Nếu mục tiêu là nâng JDK nhưng **chưa đổi framework, package và source API**, có thể chọn một nhánh JAXB 2.x tương thích với code javax.xml.bind và các dependency liên quan.

Ví dụ source legacy:

~~~java
import javax.xml.bind.JAXBContext;
import javax.xml.bind.Marshaller;

public final class XmlWriter {
    public static void write(Object object, java.io.OutputStream output)
            throws Exception {
        JAXBContext context = JAXBContext.newInstance(object.getClass());
        Marshaller marshaller = context.createMarshaller();
        marshaller.marshal(object, output);
    }
}
~~~

Một cấu hình Gradle Groovy **minh họa theo họ phiên bản cũ**:

~~~groovy
dependencies {
    implementation "javax.xml.bind:jaxb-api:2.3.1"
    runtimeOnly "org.glassfish.jaxb:jaxb-runtime:2.3.8"
}
~~~

Các version trên là ví dụ mô tả một thế hệ API/runtime; khi triển khai phải chọn bản còn được phép sử dụng, đánh giá bảo mật, version compatibility và dependency bắc cầu theo BOM/framework thực tế. Không xem những version ví dụ là khuyến nghị “mới nhất”.

### 4.3. Chuyển sang jakarta.xml.bind

Nếu hệ thống chủ động nâng lên framework dùng Jakarta namespace, source có thể cần đổi:

~~~java
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.bind.Marshaller;
~~~

Ví dụ Gradle khi đã định nghĩa alias/version được quản lý trong version catalog:

~~~kotlin
dependencies {
    implementation(libs.jakarta.xml.bind.api)
    runtimeOnly(libs.glassfish.jaxb.runtime)
}
~~~

Version catalog phải ánh xạ đúng các artifact:

~~~text
jakarta.xml.bind:jakarta.xml.bind-api
org.glassfish.jaxb:jaxb-runtime
~~~

Chọn cặp API và runtime thuộc thế hệ tương thích với framework, JVM mục tiêu và các thư viện đang chạy. Không chỉ thay groupId thành jakarta rồi giữ nguyên mọi dependency cũ.

### 4.4. Các điểm cần kiểm tra riêng cho JAXB

- Annotation XML trên DTO/entity dùng javax.xml.bind.annotation hay jakarta.xml.bind.annotation?
- Class được sinh từ XSD dùng namespace nào?
- JAXB provider được tìm thấy qua ServiceLoader hoặc cấu hình runtime nào?
- Có chạy trên classpath, module path hoặc môi trường có classloader riêng?
- Runtime có yêu cầu Activation hoặc module phụ trợ không?
- Có sử dụng Jakarta XML Binding cùng framework Spring, JPA, SOAP hoặc JSON/XML converter không?
- XML schema, namespace, element name và format thời gian có được giữ nguyên sau nâng cấp không?

Trong trường hợp dùng JPMS, cần xem lại module-info.java, requires, opens và reflective access để JAXB có thể truy cập class cần binding. Việc thêm JAR không tự động giải quyết mọi lỗi reflection dưới strong encapsulation.

## 5. Xác định dependency thay thế cho JAX-WS và SOAP

JAX-WS cung cấp API cho SOAP service/client, web service endpoint và code generated từ WSDL. Trên JDK mới, cả API và các công cụ đã từng đi kèm JDK có thể không còn.

### 5.1. API và runtime

Với code legacy dùng javax.xml.ws, có thể cần:

- Một JAX-WS API thuộc thế hệ javax.*.
- Runtime implementation như một bản Metro/JAX-WS RI tương thích, hoặc một framework SOAP tương ứng.
- Dependency JAXB, Activation, SAAJ và các thành phần WS-* theo yêu cầu runtime.

Với stack Jakarta EE hiện đại, các package thường đổi thành jakarta.xml.ws, jakarta.xml.soap, jakarta.xml.bind và jakarta.activation. Cần chọn một bộ framework/runtime có các module tương thích, thay vì trộn ngẫu nhiên nhiều API và provider.

| Nhu cầu | Nhánh legacy | Hướng cho stack Jakarta |
|---|---|---|
| SOAP API | javax.xml.ws.* | jakarta.xml.ws.* |
| SOAP message API | javax.xml.soap.* | jakarta.xml.soap.* |
| XML binding | javax.xml.bind.* | jakarta.xml.bind.* |
| Activation | javax.activation.* | jakarta.activation.* |
| SOAP runtime | Metro/JAX-WS RI hoặc CXF phiên bản còn hỗ trợ javax | Metro/CXF hoặc nền tảng tương thích Jakarta |
| Generated stub | Code được sinh theo javax | Sinh lại stub bằng phiên bản tool chọn jakarta |

Một số framework SOAP có thể bao gồm API và provider transitively. Khi đó, không nhất thiết thêm từng API trực tiếp. Nhưng phải xác nhận tổ hợp runtime thực tế, không chỉ dựa vào compile thành công.

### 5.2. Công cụ wsimport, wsgen không còn là lệnh JDK mặc định

Trong quy trình cũ:

~~~bash
wsimport -keep -p com.example.soap.generated https://example.invalid/service?wsdl
~~~

Sau JDK 11, không được giả định wsimport có trong JDK bin. Cần chuyển code generation sang plugin của hệ sinh thái SOAP phù hợp, ví dụ plugin của Metro/JAX-WS RI hoặc Apache CXF.

Quy trình nên trở thành:

~~~text
WSDL / XSD nằm trong repository hoặc nguồn versioned
                     |
                     v
        Maven/Gradle code-generation plugin
                     |
                     v
           Source Java được sinh ra
                     |
                     v
          Compiler + packaging + tests
~~~

Nên pin phiên bản plugin, version API/runtime và WSDL/XSD đầu vào. Không nên phụ thuộc vào công cụ được cài thủ công trên máy phát triển vì CI sẽ dễ cho ra generated code khác.

Nếu WSDL do đối tác cung cấp qua network, cân nhắc lưu snapshot đã kiểm soát phiên bản để build reproducible; phải tuân thủ quyền sử dụng và quy trình cập nhật hợp đồng dữ liệu.

### 5.3. Kiểm chứng SOAP contract

Thay provider SOAP có thể gây khác biệt dù Java source đã compile:

- Namespace XML, SOAPAction, endpoint URL, encoding và schema validation.
- WSDL compatibility và kiểu dữ liệu được generate.
- HTTP transport, timeout, proxy, TLS và xác thực.
- SOAP headers, attachment/MTOM, SAAJ, SOAP handler.
- Policy WS-Security, WS-Addressing, transaction và interoperability.
- Exception mapping và lỗi SOAP Fault.

Nếu hệ thống trao đổi với đối tác ngoài, nên lưu các request/response mẫu được phép dùng và chạy interoperability test với endpoint hoặc mock tương ứng. Một unit test tạo đối tượng generated stub chưa chứng minh SOAP contract đang hoạt động.

## 6. Java Activation Framework

Activation hỗ trợ biểu diễn kiểu dữ liệu/nguồn nội dung, thường xuất hiện cùng JAXB, JAX-WS, SOAP attachment hoặc mail stack.

Trên JDK cũ, javax.activation có thể có sẵn; sau JDK 11 phải xem thư viện nào thực sự cung cấp API/runtime. Trong thế hệ Jakarta mới, package và artifact có thể chuyển sang jakarta.activation.

Các cách tiếp cận:

1. Nếu còn sử dụng code javax.activation.*, chọn API/implementation thuộc thế hệ javax tương thích với stack legacy.
2. Nếu toàn bộ framework đã dùng jakarta.activation.*, chọn Jakarta Activation và provider tương ứng.
3. Nếu Activation chỉ là dependency bắc cầu từ JAXB/JAX-WS, xem BOM của framework trước khi thêm một version thủ công.
4. Kiểm tra runtime packaging nếu compile có API nhưng khi chạy thiếu provider hoặc DataHandler/DataSource.

Không nhầm sự thay đổi của Activation với JavaMail. Mail API là một công nghệ liên quan và có thể kéo Activation làm dependency, nhưng JavaMail không phải một trong các module Java EE bị JDK 11 loại bỏ theo JEP 320.

## 7. Common Annotations và javax.annotation

Một số dự án dùng:

~~~java
import javax.annotation.PostConstruct;
import javax.annotation.PreDestroy;
import javax.annotation.Resource;
~~~

Các annotation này gắn với Common Annotations, không đồng nhất với javax.annotation.processing trong Java compiler.

Hướng xử lý:

- Với stack Java EE/legacy sử dụng javax.annotation.*, chọn Common Annotations API thế hệ javax tương ứng.
- Với framework hỗ trợ Jakarta namespace, dùng jakarta.annotation.* và Jakarta Annotations API phù hợp.
- Kiểm tra framework/container có thực sự xử lý lifecycle và injection annotation không.

Điểm dễ sai: thêm annotation API có thể làm code compile nhưng chưa chắc PostConstruct hoặc Resource được thực thi. Một Java SE application thông thường không tự có container để inject resource hoặc gọi lifecycle callback. Behavior phụ thuộc framework hoặc runtime được sử dụng.

Trong ứng dụng Spring/Jakarta, khi đổi namespace phải kiểm tra version framework, bean lifecycle và code generated; chỉ sửa import mà runtime container chưa hỗ trợ namespace mới có thể làm callback không chạy.

## 8. Java Transaction API và javax.transaction

JDK cũ có module java.transaction cung cấp một tập con API liên quan transaction. Khi nâng JDK, các kiểu javax.transaction.* do module đó cung cấp có thể không còn.

Nhưng cần phân biệt:

- **JTA API cấp cao** như UserTransaction, TransactionManager hoặc các exception liên quan đến transaction cần dependency tương ứng của Java EE/Jakarta Transactions khi ứng dụng dùng.
- **XA API** trong javax.transaction.xa vẫn là thành phần Java SE liên quan JDBC/XA ở module java.sql; không nên loại bỏ hay rename chỉ vì thấy tiền tố javax.

Nếu ứng dụng hoạt động trong application server, server có thể cung cấp transaction API và implementation. Nếu ứng dụng chạy embedded/standalone, có thể cần transaction manager implementation riêng, không chỉ API JAR.

Các câu hỏi trước khi chọn dependency:

1. Ứng dụng gọi UserTransaction/TransactionManager trực tiếp hay chỉ dùng @Transactional của framework?
2. Transaction manager hiện do app server, Spring hay library bên ngoài quản lý?
3. Có cần distributed transaction/XA qua nhiều resource không?
4. Framework đang dùng javax.transaction hay jakarta.transaction?
5. Scope provided có phù hợp môi trường triển khai thực tế không?

Không nên tự thêm cả javax.transaction và jakarta.transaction cùng các manager khác nhau nếu chưa xác định ai sở hữu transaction boundary. Việc giữ code compile nhưng đổi transaction manager có thể ảnh hưởng commit/rollback, timeout, isolation và dữ liệu production.

## 9. CORBA và RMI-IIOP: trường hợp thường không có thay thế 1:1

CORBA (Common Object Request Broker Architecture) cho phép các thành phần phân tán giao tiếp qua ORB/IIOP. Trong Java cũ, ứng dụng có thể dùng:

~~~java
import org.omg.CORBA.ORB;
import org.omg.CosNaming.NamingContextExt;
import javax.rmi.CORBA.Stub;
~~~

Sau JDK 11, các API và công cụ CORBA/IDL đi kèm JDK không còn. Khác với JAXB, **không thể mặc định chỉ thêm một API JAR là toàn bộ ORB/RMI-IIOP cũ sẽ hoạt động lại**.

### 9.1. Nhận diện phạm vi CORBA

Khảo sát:

- Code gọi ORB.init, narrow, Naming Service, Portable Object Adapter (POA).
- Tệp .idl, generated stubs/skeletons, mapping IDL-to-Java.
- Bootstrap và cấu hình ORB, naming service, endpoint IIOP.
- Interface giữa Java và hệ thống bên ngoài viết bằng ngôn ngữ khác.
- RMI-IIOP hoặc EJB legacy dùng CORBA bên dưới.
- Security, transaction, SSL/TLS, object reference và yêu cầu interoperability.

Nếu CORBA chỉ là dependency không thực sự dùng, có thể thay/loại dependency. Nếu nó là giao thức đang phục vụ một hệ thống ngoài, phải coi đây là dự án tương thích giao thức và tích hợp, không chỉ sửa import.

### 9.2. Lựa chọn A: ORB độc lập

Có thể đánh giá các triển khai ORB độc lập như JacORB hoặc Apache Yoko tùy tình trạng phát hành, phiên bản Java được hỗ trợ và yêu cầu dự án.

Trước khi chọn, cần chứng minh:

- Các package/API và mapping IDL hiện tại có được hỗ trợ không?
- Tool sinh stub/skeleton có tương thích với IDL cũ không?
- Naming service, POA, portable interceptor và transaction/security có được hỗ trợ đủ không?
- Dữ liệu trao đổi với đối tác non-Java có còn interoperable không?
- Việc cài đặt trên JDK mục tiêu, module path/classpath và container có được kiểm thử không?
- License, CVE, chính sách bảo trì và lộ trình dài hạn có phù hợp không?

Không dựa vào tên thư viện để kết luận tương thích. Một ORB có thể hỗ trợ CORBA nói chung nhưng không hỗ trợ đầy đủ tập tính năng hoặc RMI-IIOP mà ứng dụng cũ dùng.

### 9.3. Lựa chọn B: thay giao thức theo giai đoạn

Nếu CORBA đã trở thành rủi ro dài hạn, có thể chuyển dịch vụ sang:

- HTTP/REST cho API request/response đơn giản, contract công khai.
- gRPC cho giao tiếp RPC cần schema rõ ràng, streaming hoặc hiệu năng phù hợp.
- Messaging/event cho tương tác bất đồng bộ.
- Adapter/gateway giữ một biên CORBA trong thời gian các client chưa chuyển đổi.

Một chiến lược thường dùng:

~~~text
Client CORBA cũ ── IIOP ── Legacy CORBA Gateway ── Application Service
                                               ▲
                                               │
Client mới ───────────── REST/gRPC/Message ────┘
~~~

Gateway hỗ trợ giai đoạn chuyển tiếp nhưng đưa vào độ trễ, vận hành và yêu cầu bảo mật riêng. Phải thiết kế xác thực, giới hạn tải, timeout, error mapping, retry/idempotency và transaction semantics.

### 9.4. RMI Java SE không đồng nghĩa với RMI-IIOP

Một số công nghệ Java RMI cơ bản vẫn có trong Java SE thông qua module java.rmi. Điều đó **không có nghĩa RMI-IIOP/CORBA do JDK từng cung cấp vẫn còn**. Khi kiểm kê, phân biệt cụ thể Java RMI thông thường với javax.rmi.CORBA, IIOP và các công cụ IDL của hệ CORBA.

## 10. javax.* và jakarta.*: chọn đúng thế hệ

Việc tách API khỏi JDK và việc đổi namespace từ javax sang jakarta là **hai thay đổi khác nhau**, dù chúng thường cùng xuất hiện trong một đợt migration.

### 10.1. Hai giai đoạn cần hiểu

1. JDK 11 loại bỏ các module Java EE/CORBA theo JEP 320. Ứng dụng có thể vẫn dùng source javax.* bằng cách bổ sung API và runtime độc lập thuộc thế hệ tương ứng.
2. Jakarta EE 9 và các phiên bản mới chuyển nhiều API Java EE từ package javax.* sang jakarta.*. Thay đổi này ảnh hưởng import, class signature, annotation và binary compatibility.

Đặc biệt, artifact có groupId bắt đầu bằng jakarta không nhất thiết chứa package jakarta ở mọi version. Một số release Jakarta EE 8 vẫn duy trì package javax.*; cần kiểm tra **major version thực tế của API** và nội dung class thay vì chỉ suy luận từ tên artifact.

### 10.2. Bảng chọn nhanh

| Khi source/framework đang dùng | Ưu tiên xem xét | Tránh |
|---|---|---|
| javax.xml.bind.* | JAXB API/runtime cùng thế hệ javax (thường JAXB 2.x). | Kéo JAXB 3.x/4.x jakarta vào mà không chuyển source/framework. |
| jakarta.xml.bind.* | Jakarta XML Binding API/runtime cùng thế hệ jakarta. | Giữ provider chỉ hỗ trợ javax.xml.bind. |
| javax.xml.ws.* | JAX-WS/Metro/CXF thế hệ javax. | Ghép JAX-WS Jakarta 3+ với generated stubs javax cũ một cách ngẫu nhiên. |
| jakarta.xml.ws.* | Jakarta XML Web Services provider/tooling phù hợp. | Dùng generated code javax mà không regenerate/chuyển đổi. |
| javax.annotation.* | Common Annotations API thế hệ javax khi framework yêu cầu. | Đổi annotation import trong khi container vẫn xử lý javax. |
| jakarta.annotation.* | Jakarta Annotations và framework hỗ trợ Jakarta. | Chỉ thêm API JAR rồi giả định lifecycle/injection hoạt động. |
| org.omg.CORBA.* | Đánh giá ORB độc lập/IDL toolchain hoặc kế hoạch thay giao thức. | Giả định có một thư viện Jakarta thay hoàn toàn CORBA cũ. |

### 10.3. Không nên chuyển mọi thứ cùng lúc nếu thiếu khả năng kiểm chứng

Một migration lớn có thể chia thành:

~~~text
JDK 8, Java EE API được JDK cung cấp
          │
          ▼
JDK mới + javax API/runtime độc lập, giữ hợp đồng cũ
          │
          ▼
Nâng framework, tool sinh mã và dependency lên hệ sinh thái Jakarta
          │
          ▼
Chuyển import/annotation/generated code + kiểm thử hợp đồng
          │
          ▼
Loại bỏ dependency legacy không còn sử dụng
~~~

Các bước này không bắt buộc cho mọi hệ thống. Nếu framework mục tiêu yêu cầu Jakarta ngay, việc chuyển namespace có thể phải diễn ra đồng bộ. Tuy nhiên, tách các nhóm thay đổi trong kế hoạch và test giúp xác định lỗi đến từ JDK hay từ phiên bản API/framework.

## 11. Cách thiết kế dependency và scope trong Maven/Gradle

### 11.1. API và implementation có vai trò khác nhau

Với thư viện dùng JAXB hoặc JAX-WS:

- API dependency thường cần ở compile classpath vì source tham chiếu kiểu public.
- Runtime implementation phải có ở runtime classpath hoặc được platform/container cung cấp.
- Nếu application server đã cung cấp API và provider, không nên đóng gói trùng lặp mà chưa xác minh classloader và chính sách của server.
- Với executable JAR hoặc Docker image chạy standalone, thường phải đóng gói dependency runtime cần thiết.

Trong Gradle:

~~~groovy
dependencies {
    // API: dùng khi compile source tham chiếu JAXB.
    implementation "javax.xml.bind:jaxb-api:2.3.1"

    // Provider: cần để JAXBContext thực thi ở runtime.
    runtimeOnly "org.glassfish.jaxb:jaxb-runtime:2.3.8"
}
~~~

Trong Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>javax.xml.bind</groupId>
        <artifactId>jaxb-api</artifactId>
        <version>2.3.1</version>
    </dependency>
    <dependency>
        <groupId>org.glassfish.jaxb</groupId>
        <artifactId>jaxb-runtime</artifactId>
        <version>2.3.8</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Các phiên bản trên chỉ là **một ví dụ về cùng thế hệ JAXB 2.x**. Trong dự án thật cần dùng dependency constraints/BOM hoặc bộ phiên bản đã được xác minh, đồng thời xem lại CVE và chính sách hỗ trợ. Đừng copy cứng version mà bỏ qua framework đang quản lý dependency.

### 11.2. Tránh lạm dụng provided

Scope provided có ý nghĩa khi môi trường triển khai **thực sự** cung cấp API/implementation cần thiết. Nó không có nghĩa JDK 11+ tự cung cấp các API đã bị loại bỏ.

Ví dụ một ứng dụng chạy Java 21 trên container tự quản không thể dựa vào giả định rằng javax.xml.bind nằm sẵn trong JDK. Nếu runtime dependency bị loại khỏi artifact vì scope provided nhưng container không cung cấp, ứng dụng có thể build thành công rồi lỗi khi chạy.

### 11.3. Quản lý version thống nhất

Nên sử dụng BOM hoặc dependency management tương ứng với framework và chốt:

- Major version API phù hợp với namespace javax hay jakarta.
- Runtime implementation tương thích với API.
- Build plugin/code generator sinh ra source cùng namespace.
- Java runtime tối thiểu của tất cả dependency.
- Version security-patched trong phạm vi hỗ trợ.

Nếu cần override dependency, hãy ghi lý do và kiểm thử tương thích. Không nên vô tình kéo cả hai major API với package khác nhau vào runtime rồi kết luận chúng có thể thay thế qua lại; đối tượng JAXBContext của javax và jakarta là **hai kiểu Java khác nhau**.

### 11.4. JPMS và module path

Trên Java 9+, project có thể dùng module-info.java và module path. Việc bổ sung dependency không chỉ liên quan classpath:

- API và runtime có module name khác nhau giữa các bản phát hành.
- Automatic module name có thể khác tên artifact.
- Các thư viện có thể yêu cầu opens cho reflection hoặc JAXB binding.
- Module path có thể phát hiện split package, duplicate module hoặc thiếu required module.
- Service provider discovery có thể cần khai báo uses/provides hoặc cấu hình module hợp lệ.

Nếu đang dùng JPMS, hãy kiểm tra tên module bằng công cụ trên chính artifact đã chọn thay vì suy ra từ tên JAR. Trên classpath, vấn đề lại thường là thứ tự tải class và phiên bản trùng lặp; hai mô hình đóng gói có cách xử lý khác nhau.

## 12. Build-time tools và generated code

Các dự án Java EE cũ thường có source sinh từ XSD/WSDL/IDL. Khi đổi JDK, source generated có thể vẫn tham chiếu API cũ dù source viết tay đã được sửa.

| Nguồn sinh code | Tool cũ | Hướng xử lý |
|---|---|---|
| XSD → JAXB model | xjc từ JDK/tool cũ | Thêm JAXB code-generation plugin/tool độc lập theo namespace mục tiêu. |
| Java model → schema | schemagen từ JDK/tool cũ | Chuyển sang plugin của JAXB implementation phù hợp. |
| WSDL → SOAP client | wsimport | Chuyển sang JAX-WS RI/Metro hoặc CXF codegen. |
| Java service → WSDL | wsgen | Sử dụng tool/plugin phù hợp với stack SOAP đang dùng. |
| IDL → Java stubs | CORBA idlj/toolchain cũ | Đánh giá ORB/IDL generator độc lập hoặc chuyển contract sang giao thức mới. |

Quy trình nên tách:

1. Input schema (WSDL/XSD/IDL) được quản lý phiên bản.
2. Tool và version được pin trong build.
3. Generated source nằm trong generated sources directory, không sửa tay.
4. Compiler và runtime dùng API cùng hệ package.
5. Contract test xác nhận wire format và tương thích với hệ thống ngoài.

Nếu nâng code generator, hãy so sánh generated source ở API surface, annotation và serialization mapping. Tên method và kiểu dữ liệu sinh ra có thể thay đổi do generator, mặc dù WSDL/XSD không đổi.

Không nên chạy công cụ từ PATH mà không rõ nó được cài ở đâu; máy phát triển và CI có thể chọn các bản wsimport/xjc khác nhau.

## 13. Migration từng bước cho hệ thống có Java EE/CORBA

### Bước 1 — Chốt baseline hiện tại

Ghi JDK hiện tại và JDK mục tiêu, source/bytecode target, framework/application server, dependency graph, artifact packaging và môi trường runtime. Lưu một bản build và test baseline.

### Bước 2 — Tìm toàn bộ tham chiếu

Quét import trong source, generated code, các file cấu hình và class file. Tìm sử dụng javax.xml.bind, javax.xml.ws, javax.activation, javax.annotation, javax.transaction và org.omg.*. Ghi rõ module/dịch vụ nào đang sở hữu từng tham chiếu.

### Bước 3 — Phân loại tác động

| Nhóm | Câu hỏi quyết định | Hướng triển khai |
|---|---|---|
| JAXB trực tiếp | Source dùng javax hay jakarta? Có provider ngoài JDK chưa? | Chọn API/runtime cùng hệ, test XML contract. |
| SOAP/JAX-WS | Client/server cần generated stubs và WS-* gì? | Chọn framework SOAP + codegen + runtime đồng bộ. |
| Activation | Có dùng trực tiếp hay chỉ thông qua SOAP/JAXB/mail? | Chọn dependency theo framework BOM. |
| Annotation | Lifecycle/injection do container/framework nào xử lý? | Chọn Common Annotations theo namespace thực tế. |
| Transaction | App server hay embedded transaction manager? XA có dùng không? | Chọn JTA API + implementation phù hợp, test transaction. |
| CORBA | Có ORB/IIOP và đối tác phụ thuộc không? | Đánh giá ORB độc lập hoặc kế hoạch gateway/đổi giao thức. |

### Bước 4 — Quyết định giai đoạn javax hay jakarta

Nếu mục tiêu trước mắt chỉ là chạy trên JDK mới, có thể ưu tiên dependency độc lập thuộc thế hệ javax tương thích với source/framework cũ. Nếu nâng framework sang Jakarta EE mới, phải lập kế hoạch đổi package cùng generated code và runtime provider.

Không ghi “đổi mọi javax thành jakarta” như một công việc duy nhất. Mỗi công nghệ và dependency có major version, chuyển đổi tên package và yêu cầu runtime riêng.

### Bước 5 — Thay toolchain và dependency

Xóa giả định công cụ Java EE/CORBA nằm trong JDK. Thêm plugin codegen, API, implementation và dependency transitives phù hợp. Chốt version, scope, runtime packaging, classpath/module path.

### Bước 6 — Compile và chạy test mục tiêu

Chạy build trên JDK mục tiêu, sau đó kiểm thử:

- XML marshal/unmarshal cùng schema/fixture lịch sử.
- SOAP request/response thật hoặc contract mock đáng tin cậy.
- Annotation lifecycle và resource injection trên framework thực tế.
- Transaction commit/rollback, timeout, retry và XA nếu có.
- CORBA naming, IDL stubs, ORB/IIOP interoperability nếu vẫn giữ giao thức.
- Đóng gói executable JAR/container và khởi động runtime trên môi trường tương ứng.

### Bước 7 — Triển khai theo giai đoạn

Thử nghiệm staging và canary khi phù hợp; theo dõi class loading, errors, runtime provider discovery và hợp đồng với đối tác. Với thay đổi SOAP/CORBA hoặc dữ liệu, cần kế hoạch rollback cả giao thức lẫn trạng thái, không chỉ đổi JDK.

### Bước 8 — Loại bỏ dependency dư thừa

Sau khi chức năng hoạt động ổn định, kiểm tra dependency graph để loại provider trùng, API cũ không dùng hoặc tool chỉ dành cho migration. Giữ evidence về bộ phiên bản đã kiểm chứng và các trường hợp ngoại lệ.

## 14. Ma trận quyết định dependency thay thế

Mẫu kiểm kê có thể dùng ngay trong migration plan:

| Thành phần / package | Nguồn phụ thuộc hiện tại | Runtime mục tiêu | Hướng thay thế | Tình trạng kiểm chứng |
|---|---|---|---|---|
| javax.xml.bind.* | JDK 8 hoặc API legacy | JDK 17/21 | JAXB API 2.x + runtime cùng hệ nếu giữ javax; hoặc chuyển Jakarta XML Binding đồng bộ. | Chưa / Đã compile / Đã test XML. |
| javax.xml.ws.* | JDK/tool cũ | JDK 17/21 | JAX-WS RI/Metro hoặc CXF phù hợp source/namespace; tool codegen độc lập. | Chưa / Đã test SOAP. |
| javax.activation.* | JDK 8/transitive | JDK 17/21 | Activation API/provider tương ứng javax/jakarta. | Chưa / Đã test runtime. |
| javax.annotation.* | Java EE module hoặc framework | JDK 17/21 | Common Annotations API và framework xử lý callback phù hợp. | Chưa / Đã test lifecycle. |
| javax.transaction.* | JDK cũ / container | JDK 17/21 | JTA/Transaction API và manager nếu cần, theo thế hệ framework. | Chưa / Đã test commit/rollback. |
| org.omg.* | CORBA JDK 8 / ORB cũ | JDK 17/21 | ORB độc lập hoặc gateway/REST/gRPC; xác minh IDL/IIOP. | Chưa / Đã test interoperability. |
| wsimport / xjc | JDK tools | Build trên JDK mới | Maven/Gradle plugin của JAX-WS/JAXB; pin version. | Chưa / Đã regenerate. |

Mỗi hàng triển khai thực tế nên bổ sung:

- Tên module/service và owner.
- Phiên bản source, JDK, framework và dependency.
- Dependency được chọn với groupId/artifactId/version hoặc tên ORB/framework.
- Scope compile/runtime/provided và cách đóng gói container.
- Có thay package namespace không; có breaking binary/API change không.
- Bằng chứng test/CI, lỗi còn mở, điều kiện rollback.

Không điền một version “theo cảm tính” chỉ để bảng trông hoàn chỉnh. Nếu chưa có lựa chọn được kiểm chứng, ghi rõ “cần đánh giá” và lý do.

## 15. Các lỗi thường gặp và cách tránh

### 15.1. Chỉ thêm API nhưng thiếu implementation

Đây là lỗi phổ biến với JAXB và JAX-WS: compile hết lỗi, nhưng khởi động hoặc sử dụng API thực tế mới báo không tìm được provider.

Giải pháp: phân biệt dependency compile API và runtime provider; kiểm tra service discovery trên đúng artifact deploy và runtime classpath.

### 15.2. Dùng API javax với runtime jakarta không tương thích

Các class javax.xml.bind.JAXBContext và jakarta.xml.bind.JAXBContext không cùng binary name. Framework hoặc generated code được biên dịch với một thế hệ không tự tương thích với thế hệ còn lại.

Giải pháp: chọn nhất quán API, runtime, generated code và framework. Nếu phải dùng cả hai trong cùng hệ thống, cô lập ranh giới qua adapter và kiểm thử rõ, không cố coi hai API là một.

### 15.3. Thay mọi javax bằng jakarta

Việc sửa hàng loạt có thể làm hỏng javax.xml.parsers, javax.crypto, javax.sql hoặc javax.annotation.processing vẫn thuộc Java SE.

Giải pháp: kiểm kê theo từng API bị tác động; sử dụng mapping cụ thể theo framework và major version.

### 15.4. Giữ scope provided từ thời JDK 8

Ứng dụng build thành công vì CI có API JAR, nhưng Docker runtime không có JAR hoặc implementation cần thiết.

Giải pháp: xác minh thành phần nào do app server/runtime cung cấp; với standalone deployment, đóng gói runtime dependency đầy đủ.

### 15.5. Chỉ sửa source, bỏ qua generated code

Source viết tay chuyển sang Jakarta nhưng SOAP stub được sinh bởi wsimport cũ vẫn import javax.xml.ws; build và runtime tiếp tục lỗi.

Giải pháp: nâng codegen plugin và regenerate từ schema/WSDL được quản lý phiên bản.

### 15.6. Xem CORBA như một dependency XML

JAXB chủ yếu xử lý binding XML. CORBA là middleware giao tiếp phân tán với ORB/IIOP/IDL và có thể phụ thuộc đối tác ngoài Java. Không thể thay bằng một XML library.

Giải pháp: tìm tất cả integration contract, đánh giá ORB độc lập hoặc gateway và lập kế hoạch giao thức có kiểm chứng.

### 15.7. Bỏ qua runtime và classloader

Test unit chạy được trên classpath giản lược, nhưng application server hoặc module path có provider trùng, split package hoặc reflection restriction.

Giải pháp: test deployment artifact thực tế trên runtime tương đương production, đối chiếu classpath/module path và version thư viện.

## 16. Ví dụ đọc lỗi và chọn hướng xử lý

### Ví dụ A — JAXB lỗi biên dịch sau khi chuyển JDK

Giả sử source báo:

~~~text
error: package javax.xml.bind does not exist
~~~

Trình tự hợp lý:

1. Xác nhận JDK đang compile là JDK 11+ và source vẫn import javax.xml.bind.
2. Tìm dependency JAXB API hiện có hay chưa.
3. Kiểm tra framework đang thuộc thế hệ javax hay Jakarta.
4. Nếu giữ javax, chọn JAXB API/runtime tương thích thế hệ legacy.
5. Nếu chuyển Jakarta, cập nhật import và các annotation/generated code, chọn API/runtime đồng bộ.
6. Chạy marshal/unmarshal test; không dừng ở bước compile thành công.

### Ví dụ B — SOAP client không còn wsimport

Trước đây CI dùng:

~~~bash
$JAVA_HOME/bin/wsimport -keep service.wsdl
~~~

Sau khi dùng JDK mới, lệnh không tồn tại. Phương án đúng không phải sao chép một executable từ JDK cũ vào image mới rồi bỏ qua dependency.

Hãy đưa WSDL vào quy trình build có versioned code generator, chọn Metro hoặc CXF plugin tương ứng, pin phiên bản, sinh source và test SOAP contract trên JDK mục tiêu.

### Ví dụ C — CORBA client cũ lỗi tại import org.omg

Nếu hệ thống vẫn trao đổi IIOP với một server CORBA, lựa chọn thực tế có thể là ORB độc lập nếu hỗ trợ contract hiện có. Nếu giao thức đã lỗi thời và có quyền thay server, có thể thiết kế gateway rồi di chuyển client theo giai đoạn.

Cần kiểm tra IDL, object reference, naming service và security trước khi khẳng định việc thay ORB đủ để chạy. Một ứng dụng dùng RMI thông thường không nhất thiết cần CORBA; phải xem import và giao thức thực tế.

## 17. Kết quả cần có sau khi khảo sát và thay thế

Một đợt migration được chuẩn bị tốt nên tạo ra:

1. **Danh sách module/API JDK bị loại bỏ** mà từng module ứng dụng thực sự sử dụng.
2. **Bảng mapping dependency** cho JAXB, JAX-WS, Activation, Common Annotations, Transactions và CORBA với namespace, API, runtime, version và scope rõ ràng.
3. **Danh sách tool build thay thế** cho xjc/schemagen/wsimport/wsgen/IDL generation.
4. **Quyết định javax hay jakarta** tương ứng với phiên bản framework mục tiêu.
5. **Bộ dependency được khóa phiên bản** và build artifact có thể tái tạo trên JDK mục tiêu.
6. **Kết quả kiểm thử runtime và contract** cho XML, SOAP, transaction, annotation lifecycle và IIOP nếu còn dùng.
7. **Kế hoạch xử lý rủi ro** cho dependency chưa được bảo trì, thiếu provider, generated code và integration ngoài hệ thống.
8. **Kế hoạch triển khai và rollback** có xem xét schema, giao thức và trạng thái dữ liệu.

## 18. Kết luận

Từ JDK 11, các module Java EE và CORBA bị loại bỏ theo JEP 320 không còn mặc định nằm trong JDK. Với JAXB, JAX-WS, Activation, Common Annotations và Transactions, hướng thường gặp là khai báo rõ API và runtime implementation độc lập, chọn cùng thế hệ javax hoặc jakarta mà framework và source đang sử dụng. Với CORBA, cần đánh giá ORB/IIOP độc lập hoặc chuyển giao thức theo lộ trình vì không có một JAR thay thế phổ quát cho toàn bộ middleware cũ.

Điều quan trọng nhất là **không chọn dependency chỉ dựa trên tên package hoặc thông báo compile lỗi**. Hãy phân loại API bị ảnh hưởng, kiểm tra dependency graph, tách API khỏi implementation, cập nhật build-time tools, xác định namespace và chạy contract test trên runtime thực tế. Cách tiếp cận đó biến một thay đổi tưởng như “thiếu class của JDK” thành kế hoạch migration có kiểm soát, tránh sửa compile mà để lại lỗi runtime hoặc tương thích hệ thống phân tán.
