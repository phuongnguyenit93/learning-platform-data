# Công cụ chuyển namespace và giới hạn của việc biến đổi tự động

Khi nâng cấp ứng dụng Java EE sang Jakarta EE trong một dự án **Java Advance Compatibility Migration**, lỗi thường gặp không chỉ là thiếu thư viện hay JDK không tương thích. Nhiều API trước đây mang package `javax.*` đã được chuyển sang `jakarta.*` từ **Jakarta EE 9**. Những class trông giống nhau về tên và phương thức vẫn trở thành **hai kiểu khác nhau** trong JVM: `javax.servlet.http.HttpServletRequest` không thể tự động thay thế cho `jakarta.servlet.http.HttpServletRequest`; một bean dùng `javax.persistence.Entity` không phải là entity được Jakarta Persistence provider mới nhận diện theo `jakarta.persistence.Entity`.

Các công cụ tự động như **OpenRewrite**, khả năng refactor của IDE, **Eclipse Transformer** và **Apache Tomcat Jakarta EE Migration Tool** có thể giảm đáng kể công việc thay import, dependency, descriptor và bytecode. Nhưng **biến đổi tự động không phải bảo đảm tương thích hành vi**: công cụ có thể sửa những ký hiệu mà nó nhận diện được nhưng không tự quyết định được một annotation có semantics mới hay không, một framework cũ có hỗ trợ Jakarta hay không, hoặc một giao thức truyền serialized Java object giữa hai phiên bản có còn đọc được hay không.

Bài học này tập trung vào **chọn đúng công cụ chuyển namespace, hiểu phạm vi của từng cách biến đổi, xử lý những phần không thể tự động chuyển và xác minh trên Jakarta runtime đích**. Nội dung thuộc chương **Java EE và Jakarta**, trong đó thay package chỉ là một bước của migration API, dependency, container và hệ sinh thái framework.

## 1. Bối cảnh: Java EE, Jakarta EE 8 và Jakarta EE 9+

Cần phân biệt ba giai đoạn để tránh nhầm giữa **tên artifact** và **tên package**:

| Giai đoạn | Namespace phổ biến của API enterprise | Ý nghĩa khi migration |
|---|---|---|
| Java EE 7/8 | `javax.servlet.*`, `javax.persistence.*`, `javax.ws.rs.*`, ... | Ứng dụng legacy thường được biên dịch theo namespace `javax` |
| **Jakarta EE 8** | **Vẫn là `javax.*`** ở các API được chuyển giao | Tên Jakarta trong group/artifact hoặc tên sản phẩm **chưa đồng nghĩa** package đã thành `jakarta` |
| **Jakarta EE 9/9.1** | Các API Jakarta EE liên quan đổi sang **`jakarta.*`** | Mốc chuyển namespace lớn; source và binary cần được điều chỉnh |
| Jakarta EE 10/11+ | Tiếp tục namespace `jakarta.*` | Có thêm thay đổi về phiên bản đặc tả, phương thức và Java baseline; không chỉ đổi import |

Ví dụ, một dependency có groupId bắt đầu bằng `jakarta` **không đủ** để kết luận nội dung JAR chứa package `jakarta.servlet`. Một số artifact Jakarta EE 8 vẫn mang class dưới `javax.servlet`. Ngược lại, một application server mới hỗ trợ Jakarta Servlet 6 có thể không cung cấp class `javax.servlet` cho web app đã biên dịch theo Java EE 8.

**Quy tắc làm việc:** chọn **Jakarta EE platform/profile và phiên bản container/framework đích**, rồi từ đó xác định phiên bản API artifact, dependency implementation và các bước chuyển đổi. Không bắt đầu bằng một lệnh thay chữ trên toàn repository.

### 1.1. Đổi JDK và đổi Jakarta namespace là hai trục khác nhau

Nâng Java 8 lên Java 17 không tự chuyển `javax.servlet` thành `jakarta.servlet`. Một ứng dụng có thể chạy JDK 17 nhưng vẫn dùng stack `javax` nếu server/framework còn hỗ trợ. Ngược lại, framework Jakarta mới có thể yêu cầu một JDK tối thiểu cao hơn, dù source không sử dụng syntax Java mới.

Ví dụ:
- Ứng dụng WAR dùng Servlet 4 và container hỗ trợ `javax.servlet` có thể nâng JDK theo support matrix mà chưa chuyển Jakarta.
- Ứng dụng muốn chuyển sang Tomcat 10.1 dùng Jakarta Servlet 6 cần **namespace `jakarta.servlet`** và dependency tương ứng.
- Một dự án Spring Boot 2.x thường thuộc stack Java EE/`javax` đối với một số API; Spring Boot 3.x thuộc stack Jakarta/`jakarta` và có những yêu cầu Java/framework khác. Chuyển Boot major version không chỉ là đổi import.

Vì vậy, lập ma trận ít nhất ba chiều: **JDK runtime**, **platform/container/framework** và **namespace/API version**.

## 2. Package nào chuyển, package nào không được thay?

Một lệnh `replaceAll("javax.", "jakarta.")` trên mọi file Java là nguy hiểm. **Jakarta EE chuyển namespace của các API thuộc Jakarta EE**, còn nhiều package `javax.*` thuộc **Java SE** vẫn giữ nguyên.

### 2.1. Các ví dụ Jakarta EE thường cần chuyển

| API/domain | Namespace Java EE/Jakarta EE 8 | Namespace Jakarta EE 9+ |
|---|---|---|
| Servlet | `javax.servlet.*` | `jakarta.servlet.*` |
| Persistence/JPA | `javax.persistence.*` | `jakarta.persistence.*` |
| CDI | `javax.enterprise.*` | `jakarta.enterprise.*` |
| Dependency Injection | `javax.inject.*` | `jakarta.inject.*` |
| Bean Validation | `javax.validation.*` | `jakarta.validation.*` |
| REST/JAX-RS | `javax.ws.rs.*` | `jakarta.ws.rs.*` |
| WebSocket | `javax.websocket.*` | `jakarta.websocket.*` |
| JMS/Messaging | `javax.jms.*` | `jakarta.jms.*` |
| JAXB/XML Binding | `javax.xml.bind.*` | `jakarta.xml.bind.*` |
| SOAP/JAX-WS | `javax.xml.ws.*` | `jakarta.xml.ws.*` |
| Mail | `javax.mail.*` | `jakarta.mail.*` |
| Activation | `javax.activation.*` | `jakarta.activation.*` |
| JSON-P | `javax.json.*` | `jakarta.json.*` |
| JSON-B | `javax.json.bind.*` | `jakarta.json.bind.*` |
| Faces/JSF | `javax.faces.*` | `jakarta.faces.*` |
| EJB | `javax.ejb.*` | `jakarta.ejb.*` |
| Jakarta Transactions/JTA | `javax.transaction.*` (phần Jakarta quản lý) | `jakarta.transaction.*` |
| Jakarta Security | `javax.security.enterprise.*` | `jakarta.security.enterprise.*` |
| Expression Language | `javax.el.*` | `jakarta.el.*` |
| Common Annotations | `javax.annotation.*` thuộc Jakarta Annotations | `jakarta.annotation.*` tương ứng |

Bảng dùng để định hướng **đối với API thuộc Jakarta EE**, không phải luật thay chuỗi không phân biệt context. Từng dự án cần chốt phiên bản đặc tả và class thực sự có trong JAR đích.

### 2.2. Các package `javax.*` thuộc Java SE phải giữ

Một số ví dụ:

| Package không được đổi đại trà | Vai trò |
|---|---|
| `javax.crypto.*` | Mã hóa Java SE/JCA |
| `javax.net.ssl.*` | TLS/JSSE |
| `javax.swing.*` | Giao diện desktop Swing |
| `javax.sql.*` | JDBC DataSource và API liên quan |
| `javax.naming.*` | JNDI |
| `javax.management.*` | JMX |
| `javax.xml.parsers.*` | XML parser API thuộc Java SE |
| `javax.xml.transform.*` | XSLT/transformer API |
| `javax.xml.namespace.*` | Namespace XML |
| `javax.xml.stream.*` | StAX |
| `javax.annotation.processing.*` | Annotation processing trong Java compiler |
| `javax.lang.model.*` | Compiler language model |
| `javax.transaction.xa.*` | XA APIs thuộc Java SE (`java.transaction.xa` trong Java 9+) |

Ví dụ, code này **không** được đổi thành `jakarta.xml.parsers.DocumentBuilderFactory`:

~~~java
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.parsers.DocumentBuilder;

// Java SE XML parsing API; giữ nguyên javax.*
DocumentBuilder builder =
        DocumentBuilderFactory.newInstance().newDocumentBuilder();
~~~

Cũng không đổi `javax.crypto.Cipher` thành `jakarta.crypto.Cipher` vì không có Jakarta API tương đương như vậy.

### 2.3. Có namespace trùng tiền tố nhưng khác quyền sở hữu

Một ví dụ đặc biệt dễ sai là:
- `javax.annotation.PostConstruct` thuộc Common Annotations cũ, chuyển sang `jakarta.annotation.PostConstruct` trong Jakarta Annotations.
- `javax.annotation.processing.Generated` thuộc API xử lý annotation của Java SE, **vẫn giữ nguyên**.
- `javax.transaction.Transactional` của Java EE chuyển sang `jakarta.transaction.Transactional`.
- `javax.transaction.xa.XAResource` là API Java SE, **không chuyển** sang `jakarta.transaction.xa.XAResource`.

Nếu một công cụ chỉ thay toàn bộ prefix `javax.annotation` hoặc `javax.transaction`, nó có thể phá mã Java SE hợp lệ. Đây là lý do cần recipe có hiểu biết về từng API và bước đối chiếu dependency/compilation, không chỉ tìm-thay văn bản.

## 3. Tại sao việc đổi namespace gây bất tương thích nhị phân?

JVM nhận diện class bằng **tên đầy đủ** gồm package. Hai tên sau là hai kiểu khác nhau:

~~~text
javax.servlet.http.HttpServletRequest
jakarta.servlet.http.HttpServletRequest
~~~

Ở mức class file, tên JVM/internal descriptor cũng thay:
 
~~~text
Ljavax/servlet/http/HttpServletRequest;
Ljakarta/servlet/http/HttpServletRequest;
~~~

Ví dụ một phương thức thư viện cũ:

~~~java
public void handle(javax.servlet.http.HttpServletRequest request)
~~~

không còn cùng descriptor với phiên bản mới:

~~~java
public void handle(jakarta.servlet.http.HttpServletRequest request)
~~~

Một consumer Java đã biên dịch với descriptor `javax` **không tự liên kết được** tới method mới nhận `jakarta`. Những lỗi có thể xuất hiện:
- `NoClassDefFoundError` hoặc `ClassNotFoundException` khi chỉ thiếu API cũ.
- `NoSuchMethodError` nếu phương thức mong đợi theo descriptor cũ không còn.
- `ClassCastException` nếu hệ thống cố ép kiểu giữa hai object/class không tương đương.
- Lỗi nạp annotation, CDI injection, provider discovery hoặc framework integration.
- `LinkageError` khi classpath/module path tạo graph hỗn hợp không hợp lệ.

**Không thể khắc phục bằng cách thêm cả hai API JAR rồi cast một object từ `javax` sang `jakarta`.** Hai kiểu có thể cùng tồn tại như hai class riêng, nhưng container cũ và mới vẫn cần đúng hợp đồng API tương ứng.

### 3.1. Source migration, binary migration và runtime migration khác nhau

| Hoạt động | Thay đổi | Chưa tự bảo đảm |
|---|---|---|
| Source transformation | Imports, type names, annotations, dependency declarations | Thư viện runtime và container đã tương thích |
| Bytecode transformation | Constant pool, references, annotation descriptors và resources được hỗ trợ | Hành vi, cấu trúc framework và giao thức đã tương thích |
| Runtime migration | Container/framework dùng `jakarta`, JVM và cấu hình deployment mới | Client/data cũ đọc được object mới |
| Semantic migration | API behavior, serialization, validation, auth, transaction, provider config | Không thể chứng minh chỉ bằng phép thay namespace |

Tách các hoạt động này giúp đội migration chọn công cụ đúng và biết còn phần nào phải xử lý thủ công.

## 4. Kiểm kê trước khi chạy công cụ

Trước khi chuyển đổi, cần lập danh sách cả source, thư viện, descriptor, generated code và cấu hình triển khai.

### 4.1. Tìm usage trong source

Ví dụ tìm import:

~~~bash
rg -n --glob '*.java' \
  '(^|[[:space:]])import[[:space:]]+javax\.' src
~~~

Tìm tên class dưới dạng chuỗi hoặc cấu hình:

~~~bash
rg -n --hidden \
  -g '!**/.git/**' \
  'javax\.(servlet|persistence|validation|ws\.rs|enterprise|inject|jms|xml\.bind|mail)' .
~~~

Tìm những điểm nạp class/provider bằng reflection:

~~~bash
rg -n --glob '*.java' \
  'Class\.forName|ServiceLoader|loadClass|forName|MethodHandles' src
~~~

Tìm kiếm text chỉ giúp phát hiện một phần:
- Class name có thể được ghép động, lấy từ DB/config hoặc do framework sinh.
- JAR dependency đã biên dịch không có source trong repository.
- XML/JSP/TLD/property file có thể chứa tên class hoặc namespace URI.
- Test fixtures có thể nhúng class name hoặc JSON polymorphic type identifier.
- Package Java SE `javax.*` không được đưa vào danh sách thay thế chỉ vì regex thấy nó.

### 4.2. Kiểm kê dependency đã resolve

Với Maven:

~~~bash
./mvnw dependency:tree
~~~

Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency jakarta.servlet-api \
  --configuration runtimeClasspath
~~~

Những lệnh trên phục vụ dự án thực tế; khi viết bài ở STEP 4 không cần chạy chúng.

Tập trung:
- API JAR: `javax.servlet-api`, `jakarta.servlet-api`, JPA, Validation, JMS, JAXB, JAX-RS.
- Implementation/runtime: Hibernate ORM, Jersey/RESTEasy, Weld/CDI, Faces, JSON-B, Mail, JAX-WS.
- Framework: Spring Framework/Boot, application server libraries, plugin/agent.
- Transitive dependencies còn import `javax` trong bytecode.
- Generated sources và annotation processors.
- Driver/native libraries và test integration.

### 4.3. Xác minh class bên trong JAR, không chỉ groupId

Có thể xem:

~~~bash
jar --list --file path/to/api-or-library.jar
~~~

Tìm package thật:
 
~~~text
javax/servlet/...
jakarta/servlet/...
~~~

Hoặc dùng:
 
~~~bash
jdeps --recursive --class-path "lib/*" app.jar
~~~

`jdeps` hữu ích cho tham chiếu tĩnh giữa các class/modules. Nó **không phát hiện đầy đủ** tên class được load qua reflection, file `META-INF/services`, resource strings hoặc script. Nếu JAR đã được biến đổi, cần phân tích lại output chứ không suy đoán chỉ từ tên artifact.

### 4.4. Ghi phạm vi trước khi chuyển

Một bảng inventory thực tế:

| Thành phần | Hiện trạng | Mục tiêu | Owner |
|---|---|---|---|
| Web module | WAR Servlet `javax` | Jakarta Servlet 6/Tomcat 10.1 | Web team |
| Persistence | JPA `javax.persistence` | Jakarta Persistence provider tương thích | Data team |
| REST endpoints | JAX-RS `javax.ws.rs` | Jakarta REST runtime phù hợp | API team |
| Validation | `javax.validation` | Jakarta Validation provider mới | API team |
| XML descriptors | `web.xml`, `persistence.xml` bản cũ | Schema/namespace đúng platform mục tiêu | Platform team |
| Library nội bộ | JAR chỉ có `javax` | Rebuild source hoặc transform tạm | Shared library team |
| Plugin bên ngoài | Chưa có Jakarta release | Upgrade, adapter hoặc thay thế | Integration team |
| Test | Mock container `javax` | Test runtime `jakarta` và contract tests | QA/dev team |

Không biến bảng thành danh sách thao tác tự động ngay lập tức. Trước tiên kiểm tra **đích Java EE/Jakarta EE cụ thể** và khả năng hỗ trợ của runtime.

## 5. Chọn công cụ theo loại đầu vào

Không có một công cụ duy nhất xử lý mọi lớp migration.

| Công cụ/nhóm | Đầu vào phù hợp | Kết quả thường mong đợi | Giới hạn chính |
|---|---|---|---|
| **OpenRewrite** | Source Java, build files, một số resource/config có recipe | Thay API/import/dependency theo recipe có cấu trúc | Không hiểu toàn bộ nghiệp vụ, reflection động hoặc mọi schema |
| **IDE refactoring** (IntelliJ IDEA/Eclipse IDE) | Source do mình sở hữu | Đổi import/type và chỉnh code có thể review | Phụ thuộc indexing/config, không tự sửa JAR bên ngoài |
| **Eclipse Transformer** | JAR/WAR, class, archive và tài nguyên hỗ trợ | Chuyển một số reference/resource ở mức binary/package | Không đảm bảo mọi thư viện, signature, reflection hoặc behavior |
| **Apache Tomcat Jakarta EE Migration Tool** | Web app Java EE/WAR/JAR tương ứng | Chuyển artifact cho môi trường Tomcat Jakarta | Phạm vi Tomcat/Jakarta rules; không sửa business semantics |
| **Compiler + dependency analysis** | Source và artifact sau chuyển | Phát hiện thiếu type, wrong API/bytecode | Không chứng minh runtime behavior |
| **Integration/contract tests** | App triển khai trong runtime đích | Xác minh các luồng nghiệp vụ | Không tự thực hiện migration |

**Chiến lược ưu tiên:** nếu có source và dependency được bảo trì, ưu tiên **nâng dependency lên bản Jakarta chính thức rồi chuyển source một cách có kiểm soát**. Binary transformer hữu ích cho artifact legacy chưa có Jakarta variant, nhưng nên xem đó là giải pháp tạm có owner và ràng buộc support.

## 6. OpenRewrite: chuyển source theo recipe có cấu trúc

OpenRewrite là nền tảng transformation theo recipe, phù hợp với repository nhiều module, các lần nâng Java/framework và những thay đổi API/dependency có thể mô tả bằng quy tắc. Nó có thể biến đổi Java syntax tree và một số build/config files theo recipe tương ứng, thay vì tìm-thay toàn bộ text mù ngữ cảnh.

### 6.1. Cách tổ chức một lượt chuyển OpenRewrite

Một quy trình làm việc an toàn:
1. Chốt version JDK, Jakarta platform, framework và dependency đích.
2. Xem danh sách recipe **thực sự có trong phiên bản rewrite-migrate-java được dùng**.
3. Chạy recipe trên branch riêng để tạo diff có thể review.
4. Xem thay đổi imports, annotations, field/method types, dependency declarations và XML/config.
5. Build và chạy test trên target environment, rồi sửa những chỗ recipe chưa bao phủ.
6. Khóa version recipe/plug-in để kết quả có thể tái lập.

Không nên đoán recipe ID từ tên tài liệu hoặc một ví dụ cũ. Recipe có thể được đổi tên, tách thành recipe con, bổ sung điều kiện phiên bản hoặc thay phạm vi theo release. Dùng catalog tài liệu chính thức của **đúng recipe artifact version** đang pin.

### 6.2. Ví dụ trước/sau chuyển source

Trước:

~~~java
import javax.servlet.annotation.WebServlet;
import javax.servlet.http.HttpServlet;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

@WebServlet("/health")
public class HealthServlet extends HttpServlet {
    @Override
    protected void doGet(
            HttpServletRequest req,
            HttpServletResponse resp
    ) throws java.io.IOException {
        resp.getWriter().write("OK");
    }
}
~~~

Sau khi chuyển đúng Jakarta Servlet API:

~~~java
import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

@WebServlet("/health")
public class HealthServlet extends HttpServlet {
    @Override
    protected void doGet(
            HttpServletRequest req,
            HttpServletResponse resp
    ) throws java.io.IOException {
        resp.getWriter().write("OK");
    }
}
~~~

Đây là trường hợp phần lớn thay đổi là package/import. Nhưng code trên chỉ chạy trong một servlet container hỗ trợ **Jakarta Servlet** tương ứng. Nếu server vẫn cung cấp `javax.servlet`, compile thành công không bảo đảm deployment thành công.

### 6.3. Dependency/build file cũng cần thay

Với Maven, ví dụ một WAR dành cho runtime hỗ trợ Jakarta Servlet 6:

~~~xml
<dependency>
    <groupId>jakarta.servlet</groupId>
    <artifactId>jakarta.servlet-api</artifactId>
    <version>6.0.0</version>
    <scope>provided</scope>
</dependency>
~~~

`provided` có thể phù hợp khi container quản lý Servlet API; nhưng một executable JAR hoặc embedded server có packaging và dependency strategy khác. Không tự dùng `provided` cho mọi API Jakarta, vì JPA/Validation/JAXB có thể cần implementation/provider runtime được đóng gói.

Ví dụ Gradle cho WAR triển khai lên container hỗ trợ Servlet 6:

~~~groovy
plugins {
    id 'java'
    id 'war'
}

dependencies {
    providedCompile 'jakarta.servlet:jakarta.servlet-api:6.0.0'
}
~~~

Các ví dụ cho thấy **thay import và dependency phải thống nhất**. Nếu source dùng `jakarta.servlet` nhưng JAR runtime chỉ có `javax.servlet`, lỗi thường chỉ xuất hiện khi chạy hoặc deploy.

### 6.4. Review diff: không phải thay nào cũng có thể áp dụng máy móc

Một lượt OpenRewrite có thể bỏ sót:
- Class name được truyền dưới dạng string.
- Static resource/config không có recipe tương ứng.
- Generated code sẽ được sinh lại từ plugin cũ.
- Thư viện internal có API tương tự nhưng semantics khác.
- Custom extension/reflective provider.
- Binary-only dependency không nằm trong source.

Review diff là để xác minh **phạm vi được thay**, không phải chỉ đếm số import đã đổi. Hãy ghi lại các nhóm file chưa được recipe xử lý để xử lý thủ công hoặc tạo recipe riêng có test.

## 7. IDE refactoring: phù hợp với những thay đổi có ngữ cảnh

IntelliJ IDEA hoặc Eclipse IDE có chức năng đổi import, tìm usage, rename/refactor và inspection. Chúng hữu ích khi:
- Repository nhỏ hoặc một module.
- Cần sửa source có logic framework riêng.
- Cần phát hiện lỗi compile ngay trong editor.
- Một vài API đổi method signature hoặc annotation semantics, không chỉ package.
- Cần người có kiến thức domain quyết định những trường hợp mơ hồ.

Tuy vậy:
- IDE có thể chưa index đúng dependency Jakarta nếu build file chưa cập nhật.
- Rename package theo text có thể chạm tới `javax` thuộc Java SE.
- Sửa source không biến đổi JAR binary bên ngoài.
- Người chạy IDE khác phiên bản/cấu hình có thể tạo diff khác nhau.

Với migration nhiều module, có thể kết hợp OpenRewrite tạo diff nền, IDE dùng để sửa trường hợp đặc biệt và code review để thống nhất semantics.

### 7.1. Ví dụ một trường hợp phải quyết định thủ công

Code cũ:

~~~java
import javax.annotation.PostConstruct;
import javax.annotation.processing.Generated;

@Generated("legacy-codegen")
public class CustomerCache {
    @PostConstruct
    public void initialize() {
        // ...
    }
}
~~~

Sau khi di chuyển component vào một Jakarta container phù hợp:
- `PostConstruct` có thể chuyển thành `jakarta.annotation.PostConstruct`.
- `Generated` từ `javax.annotation.processing` vẫn thuộc Java SE và **không được đổi**.

Một lần thay `javax.annotation` thành `jakarta.annotation` theo chuỗi thuần có thể khiến `Generated` sai package. Công cụ có hiểu biết API và review của developer là cần thiết.

## 8. Eclipse Transformer: chuyển artifact ở mức bytecode

**Eclipse Transformer** cung cấp cơ chế chuyển các namespace và resource theo rule set, có thể áp dụng cho một số loại JAR/WAR/archive hoặc artifact có bytecode đã biên dịch. Nó hữu ích khi:
- Thư viện legacy chỉ có artifact binary.
- Không sở hữu source để rebuild ngay.
- Cần thử khả năng chuyển giữa namespace theo rule set.
- Nhà cung cấp chưa phát hành Jakarta-compatible version.
- Đội đang tạo một adapter artifact có vòng đời ngắn trong migration.

### 8.1. Những vùng một binary transformer có thể xử lý

Tùy phiên bản/cấu hình/rule set, công cụ có thể tác động tới:
- Tên class/package trong constant pool và reference bytecode.
- Method/field descriptors, signature và annotation descriptors.
- Resource paths và tên class trong những resource được công cụ hỗ trợ.
- Manifest headers, service/provider metadata.
- Archive entry names và một số text resource theo quy tắc đã chọn.

**Không được khẳng định mọi trường hợp trên luôn được chuyển tự động.** Phạm vi cụ thể phụ thuộc công cụ, version, rule files, archive layout và kiểu tài nguyên. Khi migration, cần kiểm tra output thực tế bằng `jar`/`javap`/`jdeps` và test runtime.

### 8.2. Binary transformation khác rebuild từ source

Với source migration:
 
~~~text
Legacy source -> Jakarta imports -> javac -> Jakarta JAR
~~~

Với binary transformation:

~~~text
Legacy Java EE JAR
      |
      v
Transformer + namespace/resource rules
      |
      v
Transformed JAR (Jakarta-facing)
      |
      v
Verify bytecode, dependencies, resources, runtime behavior
~~~

Một JAR đã được transform có thể không tương đương artifact do vendor chính thức phát hành. Nếu vendor đã hỗ trợ Jakarta, **ưu tiên sử dụng bản Jakarta chính thức** để nhận bugfix, security patch và compatibility support.

### 8.3. Không tự sinh lệnh CLI chính xác khi chưa biết distribution

Cách đóng gói CLI, tên artifact, entrypoint và rule files thay đổi theo bản Eclipse Transformer. Do đó một runbook nên ghi:
- Version công cụ được pin.
- Source distribution/URL/checksum.
- Input artifact checksum.
- Rule set sử dụng.
- Command line chính xác đã kiểm chứng cho version đó.
- Output artifact name, hash và test evidence.

Mô hình lệnh ở mức khái niệm:

~~~text
transformer-cli <input-artifact> <output-artifact> <jakarta-rules>
~~~

Đây là **pseudocommand**, không phải một command copy-paste. Khi triển khai cần lấy CLI syntax của đúng release từ tài liệu chính thức.

### 8.4. Giới hạn với JAR có chữ ký và provenance

Nếu JAR được ký cryptographically, sửa bytes sau khi ký có thể làm chữ ký không còn hợp lệ. Phải:
1. Xác định artifact có chữ ký/manifests liên quan không.
2. Không dùng output đã biến đổi như thể nó còn giữ chữ ký gốc.
3. Nếu cần ký lại, tuân thủ chính sách ký/phát hành artifact của tổ chức.
4. Ghi provenance: artifact nguồn, rule set, tool version, artifact đích.
5. Kiểm tra license, SBOM và policy supply chain của bản transform.

Binary transformation không tự vá lỗ hổng bảo mật trong thư viện. Một dependency EOL vẫn có thể chứa bug dù package name đã thành `jakarta`.

## 9. Apache Tomcat Jakarta EE Migration Tool

Apache Tomcat cung cấp **Jakarta EE Migration Tool** phục vụ chuyển web application Java EE sang namespace Jakarta trong phạm vi tool hỗ trợ. Đây là lựa chọn hữu ích khi cần chuyển một WAR/JAR mà không có source hoặc muốn kiểm tra nhanh với Tomcat sử dụng Jakarta Servlet API.

Tài liệu và phạm vi nên được lấy từ dự án [Apache Tomcat Jakarta EE Migration Tool](https://github.com/apache/tomcat-jakartaee-migration).

### 9.1. Đầu vào và mục tiêu

Ví dụ khái niệm:

~~~text
legacy-app.war (javax.servlet.*)
        |
        v
Tomcat Jakarta migration tool + profile/rules phù hợp
        |
        v
migrated-app.war (jakarta.servlet.*)
        |
        v
Deploy lên Tomcat target hỗ trợ Jakarta Servlet
~~~

Tool có thể biến đổi class files và một số thành phần cấu trúc web app theo profile, nhưng:
- Nó không nâng thư viện framework lên phiên bản có support chính thức.
- Không sửa logic nghiệp vụ có thay đổi semantics.
- Không tự tạo provider runtime phù hợp khi thiếu.
- Không đảm bảo các Java object serialized trước migration còn đọc được.
- Không bảo đảm WAR đã đổi bytecode chạy được trên mọi Jakarta EE server.

**Cách sử dụng đúng là xem đây là bước chuyển artifact có test**, không phải một phép chứng minh tương thích độc lập.

### 9.2. Khi nào nên dùng tool của container?

- Cần chạy một WAR legacy trên Tomcat đã chuyển sang Jakarta Servlet, khi chưa rebuild source được ngay.
- Có quy định rõ WAR nào được transform, rule profile nào dùng và thời hạn sử dụng.
- Có integration test và kế hoạch chuyển sang source/Jakarta dependencies chính thức sau đó.

Nếu dự án đã có source và pipeline build kiểm soát được, chuyển import/dependency chính thức rồi build lại thường có khả năng bảo trì tốt hơn là luôn transform WAR ở mỗi deployment.

## 10. Giới hạn 1: reflection và tên class ở dạng chuỗi

Source transformer làm việc rất tốt với **tham chiếu type trong syntax tree**, bytecode transformer có thể sửa **descriptors**, nhưng reflection tạo ra trường hợp khó:

~~~java
Class<?> type = Class.forName(
        "javax.servlet.http.HttpServletRequest"
);
~~~

Một tool có thể nhận diện string literal trên và thay nó theo rule, nhưng không bảo đảm nếu tên được:
- Ghép từ nhiều biến.
- Đọc từ DB, YAML, XML hoặc system property.
- Tải qua network hoặc plugin.
- Mã hóa/đóng gói trong resource riêng.
- Sinh bằng annotation processor hoặc code generator.

Ví dụ:

~~~java
String namespace = config.get("servletNamespace");
String typeName = namespace + ".http.HttpServletRequest";
Class<?> type = Class.forName(typeName);
~~~

Không thể kết luận migration đúng chỉ vì `jdeps` không còn thấy dependency `javax.servlet`. Phải test các luồng reflective loading, plugin discovery, DI/proxy và nơi lấy metadata.

### 10.1. Class loader cũng là một phần hợp đồng

Ngay cả khi tên type đã được đổi, class loader có thể ảnh hưởng:
- Thư viện nào được nạp trước.
- API JAR có bị đóng gói thừa trong WAR không.
- Có nhiều bản framework không tương thích không.
- Class có thuộc module hoặc application server classloader mong đợi không.
- Plugin/JDBC/JPA provider được tìm qua `ServiceLoader` hoặc resource nào.

Cùng tên fully qualified class nhưng từ hai class loader khác nhau cũng có thể không tương thích. Vì vậy cần xem cả **classloader identity** và binary dependency, không chỉ namespace string.

## 11. Giới hạn 2: META-INF/services và provider discovery

Java `ServiceLoader` và nhiều framework tìm provider từ file:

~~~text
META-INF/services/<fully.qualified.InterfaceName>
~~~

Giả sử JAR cũ có entry:

~~~text
META-INF/services/javax.example.LegacyService
~~~

Nếu giao diện tương ứng được chuyển thành `jakarta.example.NewService`, resource name và nội dung provider có thể phải chuyển theo contract mới. Một transformer có thể hỗ trợ một số rule, nhưng không thể biết custom provider contract của mọi framework.

Các điểm cần rà:
- `META-INF/services`.
- `module-info.class` với `uses`/`provides` khi có JPMS.
- File metadata của CDI/JPA/Validation/JAX-RS.
- SPI do framework tự định nghĩa.
- Entry trong manifest hoặc cấu hình ứng dụng.
- Generated service registry và annotation index.

Đặc biệt, **không phải mọi service interface có `javax` đều thuộc Jakarta EE**. Nếu tool đổi `javax.xml.parsers.SAXParserFactory` hoặc một SPI Java SE tương ứng vì thay chữ không chọn lọc, nó có thể phá provider discovery.

## 12. Giới hạn 3: deployment descriptors, XML namespace và schema version

Enterprise Java dùng nhiều XML descriptor:
- `web.xml`.
- `persistence.xml` và `orm.xml`.
- `beans.xml` cho CDI.
- `faces-config.xml`.
- `validation.xml`.
- Một số EJB/JMS/JAX-RS deployment resources.
- JSP/TLD/taglib files.

Không chỉ package Java, những file này có thể sử dụng XML namespace URI, schema location và version khác nhau. **Không đổi URI bằng một phép thay text chung**: mỗi đặc tả có schema/version riêng, có thể chứa quy tắc validation mới.

### 12.1. Ví dụ web.xml cho Jakarta Servlet 6

Một `web.xml` được viết theo schema Jakarta Servlet 6 có thể có phần đầu:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<web-app
    xmlns="https://jakarta.ee/xml/ns/jakartaee"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        https://jakarta.ee/xml/ns/jakartaee
        https://jakarta.ee/xml/ns/jakartaee/web-app_6_0.xsd"
    version="6.0">

    <display-name>Orders Service</display-name>
</web-app>
~~~

**Không áp nguyên ví dụ Servlet 6 cho Servlet 5 hoặc mọi Jakarta EE profile.** Dự án dùng Jakarta EE 9/Servlet 5 phải chọn schema/version tương ứng, còn một runtime khác có thể có cách xử lý descriptor riêng.

### 12.2. Persistence, CDI và validation có nhiều lớp cấu hình

Sau khi đổi `javax.persistence.Entity` thành `jakarta.persistence.Entity`, cần kiểm tra:
- `persistence.xml` và `orm.xml` dùng đúng schema/version.
- Provider Jakarta Persistence tương ứng có mặt.
- Entity scanning và transaction integration vẫn hoạt động.
- Named queries, converters, listeners và validation hooks.
- Database dialect, JDBC driver và schema migration.
- Reflection, proxy và bytecode enhancement của provider.

Một recipe chỉ đổi annotation chưa chứng minh entity manager factory có thể khởi tạo, mapping SQL không đổi hoặc dữ liệu không bị phá.

Tương tự, với CDI:
- `javax.inject.Inject` → `jakarta.inject.Inject` nếu thuộc API cần chuyển.
- `beans.xml` và discovery mode cần phù hợp runtime.
- Scope lifecycle, interceptor, decorator và extension SPI cần test.
- Extension dựa vào `javax.enterprise.inject.spi` cũ phải được cập nhật hoặc thay thế.

## 13. Giới hạn 4: generated code và annotation processors

Nhiều ứng dụng sinh code từ:
- OpenAPI/Swagger generators.
- JAXB/XJC.
- JAX-WS tools.
- QueryDSL, MapStruct hoặc annotation processors.
- GraphQL/REST code generators.
- Build plugin tự sinh DTO, clients hoặc source.

Nếu chỉ sửa file nằm dưới `target/generated-sources` hoặc `build/generated`, build tiếp theo có thể **sinh lại imports `javax`**.

Quy trình đúng:
1. Xác định tool/generator và version sinh source.
2. Kiểm tra generator có output Jakarta namespace không.
3. Nâng generator/plugin hoặc cấu hình template phù hợp.
4. Xóa output đã sinh cũ và tái tạo.
5. Chạy compile trên source đã sinh mới.
6. Ghi version/template để pipeline tái lập.

Nếu generator chưa hỗ trợ Jakarta, có thể dùng post-processing transformation như giải pháp tạm, nhưng phải có test và owner. Không nên commit một lớp sửa tay vào generated source mà không sửa nguồn sinh.

### 13.1. javax.annotation.processing vẫn là Java SE

Nhiều annotation processors dùng `javax.annotation.processing.*` hoặc `javax.lang.model.*`. Chúng không cần đổi chỉ vì dự án chuyển Jakarta. Ngược lại, annotation trên domain code có thể đổi sang `jakarta.annotation.*` hay `jakarta.persistence.*`. Đây là sự khác biệt phổ biến trong dự án dùng nhiều generator.

## 14. Giới hạn 5: dependency graph và implementation provider

Một API JAR chỉ mô tả interface/annotation/contract. Nhiều Jakarta API cần **implementation/provider** để hoạt động:
- JPA cần persistence provider tương thích.
- Bean Validation cần validation provider.
- JAXB có thể cần runtime implementation.
- JAX-RS cần runtime/client implementation.
- JMS cần messaging provider/client hỗ trợ Jakarta namespace.
- CDI cần container hoặc implementation tương ứng.

Ví dụ thêm:

~~~xml
<dependency>
    <groupId>jakarta.persistence</groupId>
    <artifactId>jakarta.persistence-api</artifactId>
    <version>3.1.0</version>
</dependency>
~~~

có thể giúp source sử dụng `jakarta.persistence.Entity` biên dịch, nhưng **không tự tạo một JPA runtime**. Nếu deployment là WAR trong Jakarta EE full platform server, container có thể cung cấp provider theo profile. Nếu là ứng dụng standalone/Spring Boot, cần đúng ORM implementation và cấu hình do framework quản lý.

### 14.1. Tránh hai API namespace cùng tham gia một hợp đồng

Một tình huống lỗi:

~~~text
Web container API:     jakarta.servlet.*
Filter của library A: javax.servlet.Filter
Application endpoint: jakarta.servlet.http.HttpServlet
~~~

Library A đã được compile theo `javax.servlet.Filter`. Việc thêm `javax.servlet-api.jar` vào `WEB-INF/lib` không biến library A thành filter triển khai `jakarta.servlet.Filter` cho Jakarta container.

Lựa chọn đúng:
- Nâng library A lên bản Jakarta.
- Nếu không có, xem khả năng transform artifact binary với test và giới hạn rõ ràng.
- Viết adapter khi hai hệ cần trao đổi dữ liệu qua một hợp đồng **không phải direct cast**.
- Thay library không còn được duy trì.

### 14.2. Jakarta EE 8 artifacts không phải đích mặc định của Jakarta EE 9+

Không chọn dependency chỉ vì groupId là `jakarta.*`. Kiểm tra **JAR contents và API major version**. Một artifact Jakarta EE 8 có thể tiếp tục chứa `javax.*` trong class files, vì mốc đổi namespace là Jakarta EE 9. Điều này đặc biệt dễ gây nhầm khi dependency management/BOM chọn artifact cũ.

### 14.3. BOM và parent POM/framework quản lý version

Nếu dùng Maven BOM, Gradle platform hoặc Spring Boot dependency management, tránh override một dependency đơn lẻ mà không xem stack đồng bộ:
- API Jakarta version.
- Implementation/provider version.
- Servlet container version.
- JDK minimum.
- ORM/Validation/Jackson/Jersey/RESTEasy integration.
- Test framework/mock/instrumentation.

Một graph có API Jakarta mới nhưng implementation `javax` cũ vẫn có thể compile một phần rồi lỗi lúc runtime.

## 15. Giới hạn 6: dữ liệu serialized và giao thức giữa service

Đổi package là đổi **class identity**. Nếu hệ thống truyền Java native serialized objects qua RMI, JMS ObjectMessage, cache hoặc database BLOB, một object cũ mang class name `javax.*` hay một domain class phụ thuộc vào kiểu `javax` có thể không còn deserialize được ở runtime mới.

Các rủi ro:
- `ClassNotFoundException` hoặc `InvalidClassException`.
- `serialVersionUID`, object graph hoặc field type thay đổi.
- Session replication giữa container `javax` và `jakarta`.
- Distributed cache giữ object từ bản cũ.
- Message queue chứa dữ liệu cũ vẫn được replay sau upgrade.
- Consumer cũ không hiểu payload mới.

### 15.1. Source code đúng chưa chắc session/state migration đúng

Ví dụ một web app có serialized HTTP session chứa object từ thư viện framework cũ. Khi deploy Jakarta WAR mới, session được khôi phục bởi classloader mới có thể không đọc được class cũ. Tình huống này cần kế hoạch:
- Invalidate session có kiểm soát hoặc yêu cầu đăng nhập lại nếu chấp nhận được.
- Chuyển session data sang format độc lập với Java class name (ví dụ JSON theo schema) khi phù hợp.
- Dùng phiên bản session schema rõ ràng.
- Không cố ép session serializer tự thay class name mà bỏ qua hành vi thay đổi.

Nếu cần zero-downtime/rolling deployment, có thể phải tách state hoặc chuẩn bị coexistence trước khi cắt sang namespace mới. Không giả định hai phiên bản WAR `javax` và `jakarta` trao đổi session object trực tiếp được.

### 15.2. Giữ wire contract tách khỏi Java API

HTTP/JSON, Protobuf hoặc Avro có schema rõ có thể ít phụ thuộc tên package Java hơn, nếu type name không bị nhúng vào payload. Dù vậy cần test:
- JSON polymorphic type discriminator có thể chứa fully qualified class name.
- JAXB/XML namespace của payload có thể khác với Java package name.
- Serialization configuration có thể đổi khi nâng framework.
- Timestamp, enum, validation và lỗi API có thể có semantics khác.
- Consumer cũ có thể vẫn chạy trong giai đoạn song song.

**Không đồng nhất đổi namespace Java với đổi mọi giao thức bên ngoài**. Một API REST ổn định có thể giữ payload cũ trong khi server đổi Servlet/JAX-RS implementation, miễn contract tests xác minh được.

## 16. Giới hạn 7: hành vi framework thay đổi cùng migration

Chuyển Jakarta EE 9+ thường đi kèm nâng:
- Servlet container và HTTP stack.
- CDI implementation và bean discovery.
- Persistence provider (chẳng hạn Hibernate major version).
- Bean Validation provider.
- JAX-RS runtime và JSON mapping.
- Security/TLS/session integration.
- Build plugins và test framework.

Những thay đổi này có thể bao gồm:
- Default configuration/validation mới.
- Transaction boundary và exception wrapping khác.
- Query, SQL dialect hoặc schema generation khác.
- URI mapping, encoding và filter ordering.
- Serialization precision/null handling.
- Reflection/JPMS strong encapsulation.
- Class loader behavior và service discovery khác.
- Java baseline, bytecode target hoặc TLS defaults mới.

Công cụ chuyển namespace thường **không** tự giải quyết toàn bộ thay đổi hành vi trên. Cần đọc migration guide của runtime/framework đích và chạy characterization/integration tests.

### 16.1. Ví dụ: đổi import thành công nhưng validation không hoạt động

Một DTO cũ:

~~~java
import javax.validation.constraints.NotBlank;

public class RegisterRequest {
    @NotBlank
    public String email;
}
~~~

Sau source transform:

~~~java
import jakarta.validation.constraints.NotBlank;

public class RegisterRequest {
    @NotBlank
    public String email;
}
~~~

Compiler có thể pass khi có Jakarta Validation API. Nhưng nếu runtime chỉ có provider cũ nhận `javax.validation`, constraint mới có thể không được xử lý như mong đợi hoặc bootstrap thất bại. Cần chọn provider Jakarta-compatible, kiểm tra integration với framework và chạy request validation test thực tế.

**Không chỉ assert annotation tồn tại trong bytecode**; phải kiểm tra invalid input có bị từ chối theo contract của endpoint.

### 16.2. Ví dụ: JPA compile pass nhưng mapping thất bại

Code chuyển `javax.persistence.Entity` thành `jakarta.persistence.Entity` có thể compile nhưng entity manager không khởi tạo vì:
- Provider không hỗ trợ Jakarta Persistence version.
- `persistence.xml`/`orm.xml` chưa chuyển schema.
- Runtime classpath còn ORM plugin cũ.
- Envers/QueryDSL/bytecode enhancer khác version.
- Default naming/dialect/schema generation thay đổi.

Phải chạy query và transaction/integration tests trên database representative. Không cho migration tool chạy thêm schema DDL production tự động nếu chưa có kế hoạch dữ liệu.

## 17. Triển khai thực hành: từ WAR `javax` sang Jakarta Servlet 6

Giả sử một WAR legacy đang chạy trên container Servlet 4, dùng Java EE style annotations và một số thư viện nội bộ. Mục tiêu là Jakarta Servlet 6 trên Tomcat 10.1 hoặc container tương ứng.

### Bước 1: Chốt baseline

Ghi:
- JDK/runtime hiện tại và JDK đích.
- Servlet container/version.
- Full dependency tree và các JAR compile/runtime.
- `web.xml`, TLD, JSP, properties và provider metadata.
- Test hiện có cho URL mapping, auth/session và filters.
- Các consumer/sidecar vẫn dùng API/vocabulary cũ.

### Bước 2: Chuyển runtime dependencies

Chọn container và Jakarta API artifact tương thích. Kiểm tra thư viện: logging, security filter, ORM, Validation, JSON, JSP taglibs, REST runtime. Nếu một library không có Jakarta version, quyết định thay thế, nâng, hoặc transform có giới hạn.

### Bước 3: Chuyển source có cấu trúc

Chạy OpenRewrite/IDE refactor để đổi **chỉ** Jakarta-owned `javax.*`. Giữ nguyên `javax.xml.parsers`, `javax.net.ssl`, `javax.sql`, `javax.annotation.processing` và các API Java SE khác.

### Bước 4: Chuyển descriptor/resource

Cập nhật `web.xml` và resource liên quan theo Jakarta Servlet version; kiểm tra class names trong config, filters, listeners, taglibs, service registry và generated code. Không sửa URI schema của unrelated XML files.

### Bước 5: Build lại

Sử dụng JDK compiler và `--release` đúng runtime floor, bảo đảm WAR không đóng gói thừa Servlet API khi container cung cấp. Xem class/JAR output và dependency graph sau build.

### Bước 6: Chạy integration test trong container đích

Kiểm tra:
- Deploy không báo missing class.
- Servlet/filter/listener lifecycle.
- Route/controller mapping.
- Authentication, authorization, session, cookie.
- Request/response serialization, validation.
- File upload, multipart, async request.
- DB transaction/persistence.
- Logging, tracing và metrics.

### Bước 7: Canary và rollback

Nếu cần chạy song song:
- Tránh chia sẻ serialized session objects trực tiếp giữa hai stack.
- Chốt sticky session hoặc external session format/adapter khi cần.
- Giữ API contract cho consumer cũ.
- Triển khai routing có giới hạn và theo dõi error/latency.
- Xác minh database, cache và message format vẫn hỗ trợ rollback.

### Bước 8: Loại bỏ transformer tạm

Nếu trong giai đoạn đầu phải binary-transform một JAR, có issue/owner, version đầu vào, checksum và hạn loại bỏ. Khi vendor phát hành Jakarta build chính thức hoặc source được migrate, thay artifact transform bằng dependency chuẩn và chạy lại test.

## 18. Kiểm chứng sau biến đổi: không chỉ compile xanh

### 18.1. Ma trận build/runtime

| Kiểm chứng | Bằng chứng cần có |
|---|---|
| Source | Không còn import Jakarta-owned `javax.*` ngoài ngoại lệ có chủ đích |
| Java SE | Các `javax.*` thuộc Java SE vẫn giữ nguyên |
| Dependencies | Không trộn API và implementation `javax`/`jakarta` trong cùng contract |
| Bytecode | Method/field descriptors và annotation references đã phù hợp |
| Resources | `META-INF/services`, XML, properties, JSP/TLD và generated output đúng |
| Container | Deploy vào runtime Jakarta target thành công |
| Reflection | Class.forName, CDI scan, ORM entity discovery, SPI hoạt động |
| Business contract | HTTP status/body, validation, transaction, security và serialization phù hợp |
| Old consumers | Các client/event còn trong support window tiếp tục giao tiếp đúng |
| Rollback | Session/cache/database/message state cho phép rollback theo kế hoạch |

### 18.2. Dùng javap để kiểm descriptor

Sau khi build, có thể xem class:

~~~bash
javap -classpath target/classes -p -s \
  com.example.web.HealthServlet
~~~

`-s` in JVM descriptors giúp xác định method signature. Với JAR binary đã transform:

~~~bash
javap -classpath transformed.jar -verbose \
  com.example.library.SomeAdapter
~~~

Tìm các reference liên quan `javax/servlet` hoặc `jakarta/servlet` theo mục đích. Dù reference đã đổi, vẫn phải kiểm tra runtime behavior và provider compatibility.

### 18.3. Test integration với HTTP thực

Ví dụ một test contract HTTP có thể xác nhận endpoint:

~~~text
GET /health
Expect: 200
Content-Type: text/plain
Body: OK
~~~

Với các endpoint phức tạp, xác nhận filter chain, authentication, validation, headers, cookies, content negotiation, JSON format và status code. Dự án có JAX-RS/JPA phải bổ sung test provider/transaction chứ không dừng ở một health endpoint.

### 18.4. Test cả lỗi và dữ liệu cũ

Bộ test nên bao phủ:
- Invalid request bị validation reject.
- Token không hợp lệ vẫn bị từ chối.
- JSON/XML payload cũ vẫn parse đúng.
- Session/cache state có policy khi migration.
- Message replay từ bản cũ.
- SQL transaction/rollback và optimistic lock.
- Plugin/provider discovery.
- Classpath không chứa API sai namespace.
- Startup và shutdown của runtime đích.

Trên giai đoạn migration, **negative test** về security và validation quan trọng không kém test chức năng thành công.

## 19. Giải thích các lỗi thường gặp

| Triệu chứng | Nguyên nhân nên kiểm tra | Hướng xử lý |
|---|---|---|
| `ClassNotFoundException: javax.servlet...` trên Tomcat mới | Artifact/dependency vẫn dùng Servlet `javax` | Nâng library, chuyển source hoặc transform có kiểm chứng |
| `NoClassDefFoundError: jakarta.servlet...` trên server cũ | App đã compile Jakarta nhưng runtime chỉ có Java EE `javax` | Chọn container đúng phiên bản hoặc sửa chiến lược deploy |
| `NoSuchMethodError` có type `javax/jakarta` | Descriptor library/consumer không cùng namespace | Căn chỉnh toàn bộ API/implementation và rebuild consumer |
| CDI injection không hoạt động | Annotation/SPI/config chưa chuyển hoặc implementation cũ | Kiểm tra `jakarta.inject`, `beans.xml`, CDI provider |
| Bean Validation không trigger | Provider `javax` nhận annotation `jakarta` hoặc thiếu integration | Nâng provider/framework và test invalid input |
| EntityManager factory lỗi | JPA provider/XML/entity enhancement mismatch | Đồng bộ persistence stack và mapping |
| ServiceLoader không thấy provider | `META-INF/services` hoặc module descriptor còn tên cũ | Cập nhật metadata và kiểm tra classloader |
| JSP/TLD tag lỗi | Taglib/TLD hoặc dependencies cũ | Nâng taglib/JSP artifact, test render |
| Session deserialization lỗi | Serialized class identity không tương thích | Xây session migration/invalidation policy |
| Build vẫn sinh imports javax | Generator/annotation processor cũ | Nâng generator và tái sinh source |
| “Cannot cast javax X to jakarta X” | Hai kiểu khác nhau | Dùng cùng Jakarta API hoặc adapter qua dữ liệu |
| “Signed JAR verification failed” | Binary transformation làm mất tính hợp lệ chữ ký | Quản lý provenance, ký lại theo policy hoặc dùng upstream artifact |
| Compile pass nhưng test lỗi | Runtime/framework behavior thay đổi | Chạy integration/contract tests và đọc migration guide |
| Dependency mang tên jakarta nhưng vẫn có javax | Jakarta EE 8 artifact hoặc version sai | Kiểm tra JAR contents và API major version |

**Đọc stack trace theo class và method descriptor**, không chỉ theo tên JAR. Những lỗi namespace có thể xuất hiện sâu trong framework ở thời điểm lazy loading, không phải ngay khi startup.

## 20. Những sai lầm phổ biến

- **Thay toàn bộ chuỗi `javax.` thành `jakarta.`:** phá API Java SE như `javax.crypto`, `javax.xml.parsers` hoặc `javax.annotation.processing`.
- **Nhìn groupId `jakarta` rồi kết luận đã đổi namespace:** Jakarta EE 8 vẫn có package `javax`.
- **Chỉ sửa import trong application source:** dependency, provider, container, XML, SPI có thể vẫn là `javax`.
- **Thêm cả hai Servlet API JAR để sửa cast:** hai class khác tên không tương thích về type identity.
- **Transform WAR rồi coi là production-ready:** bytecode đổi chưa chứng minh security, validation, transaction, session hoặc contract.
- **Transform JAR đã ký nhưng giữ nguyên niềm tin vào chữ ký cũ:** nội dung mới cần provenance/signature policy phù hợp.
- **Tự sửa generated sources:** build tiếp theo có thể sinh lại `javax`.
- **Đổi schema URL bằng regex rộng:** từng Jakarta spec có schema/version riêng.
- **Không test reflection/ServiceLoader:** static compiler analysis không bao phủ dynamic metadata.
- **Dùng dependency `jakarta.*-api` nhưng thiếu provider:** API không tự là implementation runtime.
- **Nâng JDK và đổi namespace trong một diff khổng lồ không có baseline:** khó tìm nguyên nhân regression.
- **Không test consumer cũ:** JSON/serialized object/event có thể phá hợp đồng trong giai đoạn chạy song song.
- **Lạm dụng binary transformer thay upstream Jakarta release:** làm tăng rủi ro bảo trì và vá lỗi bảo mật.
- **Không ghi tool version/rule set/checksum:** không tái lập được artifact đã transform.
- **Chỉ test ứng dụng khởi động:** nhiều lỗi JPA/CDI/Validation/JMS chỉ xuất hiện khi chạy code path cụ thể.

## 21. Checklist triển khai

- [ ] Đã chốt JDK, Jakarta platform/profile và container/framework version đích.
- [ ] Đã phân biệt Java EE 8, Jakarta EE 8 và Jakarta EE 9+.
- [ ] Đã liệt kê namespace thuộc Jakarta cần chuyển.
- [ ] Đã giữ nguyên các package `javax.*` thuộc Java SE.
- [ ] Đã kiểm kê source, generated code, JAR, runtime dependencies và transitive graph.
- [ ] Đã xác định provider/implementation tương ứng với từng Jakarta API.
- [ ] Đã chọn OpenRewrite/IDE khi sở hữu source và có khả năng rebuild.
- [ ] Nếu dùng Eclipse Transformer/Tomcat migration tool, đã pin version/rule set và ghi rõ phạm vi.
- [ ] Đã quản lý chữ ký JAR, checksum, license, SBOM và provenance sau biến đổi.
- [ ] Đã rà tên class trong reflection strings, properties và custom metadata.
- [ ] Đã rà `META-INF/services`, module-info, CDI/JPA/Validation SPI.
- [ ] Đã cập nhật XML descriptor và schema theo đúng đặc tả/version.
- [ ] Đã sửa nguồn sinh hoặc template của generated code, không chỉ output sinh sẵn.
- [ ] Đã xác nhận không có consumer trực tiếp trộn `javax`/`jakarta` cho cùng một API.
- [ ] Đã kiểm tra compiled bytecode và dependency graph sau build.
- [ ] Đã deploy và chạy integration test trên Jakarta runtime đích.
- [ ] Đã test session, cache, serialized object, replay và protocol compatibility khi liên quan.
- [ ] Đã test validation, security, CDI, ORM, transactions, endpoints và error paths.
- [ ] Có kế hoạch rollout/rollback và xử lý dữ liệu trong thời gian hai stack cùng tồn tại.
- [ ] Mỗi binary transformation tạm có owner, version và điều kiện loại bỏ.
- [ ] Đã ghi rõ phần công cụ tự động không xử lý và các thay đổi thủ công cần bảo trì.

## 22. Tài liệu tham khảo

- [Jakarta EE Platform 9](https://jakarta.ee/specifications/platform/9/) — mốc namespace `jakarta.*`.
- [Jakarta EE Specifications](https://jakarta.ee/specifications/) — chọn đúng đặc tả và phiên bản API.
- [Jakarta Servlet 6.0](https://jakarta.ee/specifications/servlet/6.0/) — API/spec cho Servlet 6.
- [OpenRewrite Recipes](https://docs.openrewrite.org/recipes) — catalog recipe và migration tooling.
- [OpenRewrite — Running Recipes](https://docs.openrewrite.org/running-recipes) — cách chạy recipe qua build tool/CLI.
- [Eclipse Transformer](https://github.com/eclipse-transformer/transformer) — binary/resource transformation và rules.
- [Apache Tomcat Jakarta EE Migration Tool](https://github.com/apache/tomcat-jakartaee-migration) — chuyển artifact web app.
- [Apache Tomcat Migration Guide](https://tomcat.apache.org/migration-10.html) — khác biệt Java EE/Jakarta Servlet trên Tomcat.
- [OpenJDK jdeps Tool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeps.html) — phân tích dependency bytecode.

Các URL tham khảo giúp định vị tài liệu theo sản phẩm. Khi triển khai, đọc **tài liệu đúng version** của công cụ, Jakarta spec, container và framework mà dự án thực sự sử dụng; không suy rằng một command hoặc rule set từ release khác có cùng hành vi.

## 23. Kết luận

**Chuyển `javax.*` sang `jakarta.*` là một migration về API identity và hệ sinh thái runtime, không phải một phép đổi chữ thuần túy.** OpenRewrite và IDE phù hợp để sửa source/build configuration có cấu trúc; Eclipse Transformer và Apache Tomcat Jakarta EE Migration Tool hữu ích khi phải chuyển một số artifact đã biên dịch. Nhưng chúng không thể tự xác minh toàn bộ hợp đồng nghiệp vụ, reflection, provider, XML schema, serialization, an toàn bảo mật hoặc khả năng rollback.

Hướng bền vững là **xác định đúng Jakarta version → kiểm kê source và dependency → dùng công cụ có phạm vi chọn lọc → nâng provider/container → kiểm chứng bytecode, cấu hình và hành vi thật → loại bỏ adapter/transformer tạm thời**. Đặc biệt phải giữ nguyên Java SE `javax.*`, không trộn hai kiểu `javax`/`jakarta` trong cùng hợp đồng và ưu tiên dependency Jakarta được nhà cung cấp duy trì. Khi có đủ bằng chứng từ build, integration test và compatibility test, việc chuyển namespace mới thật sự trở thành một bước nâng Java/Jakarta có thể vận hành và bảo trì lâu dài.
