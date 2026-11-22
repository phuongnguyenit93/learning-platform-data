# Kiểm tra mã sinh, service provider và tài nguyên trong JAR

Trong quá trình **Java Advance Compatibility Migration**, việc chuyển ứng dụng từ **Java EE sang Jakarta EE** không thể chỉ dừng ở thao tác đổi import **javax.\*** sang **jakarta.\***. Một bản JAR có thể biên dịch thành công nhưng vẫn chứa **generated classes tham chiếu API cũ**, **file META-INF/services đăng ký sai interface**, hoặc **XML và metadata còn tên class, schema cũ**. Những thành phần này thường không được kiểm tra khi compiler xử lý source Java, nhưng ảnh hưởng trực tiếp đến cách ORM, servlet container, validator và framework khởi tạo runtime.

Bài học thuộc chương **Java EE và Jakarta**, giải thích cách rà soát ba lớp artifact:

- **Mã sinh:** source, class và resource do annotation processor, XJC, WSDL/OpenAPI generator hoặc công cụ khác tạo ra.
- **Service provider:** Java **ServiceLoader**, tệp **META-INF/services/** và đăng ký provider trong **module-info.java**.
- **Tài nguyên JAR/WAR:** **persistence.xml**, **orm.xml**, **beans.xml**, **validation.xml**, **web.xml**, metadata của Spring, manifest và các tài nguyên đặc thù.

Mục tiêu là xác minh **artifact cuối được phân phối và nạp trong môi trường triển khai**, chứ không chỉ tìm kiếm chuỗi trong repository hoặc thấy thông báo BUILD SUCCESS.

## 1. Bản chất của thay đổi Java EE sang Jakarta

Từ bước chuyển đổi Jakarta EE 9, nhiều Java EE APIs được đổi namespace:

| Công nghệ | Namespace cũ | Namespace Jakarta |
|---|---|---|
| Persistence/JPA | **javax.persistence** | **jakarta.persistence** |
| Servlet | **javax.servlet** | **jakarta.servlet** |
| Bean Validation | **javax.validation** | **jakarta.validation** |
| CDI | **javax.enterprise** | **jakarta.enterprise** |
| REST/JAX-RS | **javax.ws.rs** | **jakarta.ws.rs** |
| XML Binding/JAXB | **javax.xml.bind** | **jakarta.xml.bind** |
| Annotations | **javax.annotation** | **jakarta.annotation** |
| Dependency injection | **javax.inject** | **jakarta.inject** |
| Messaging/JMS | **javax.jms** | **jakarta.jms** |
| Transaction API | **javax.transaction** | **jakarta.transaction** |

JVM xem **javax.persistence.Entity** và **jakarta.persistence.Entity** là hai kiểu khác nhau. Framework Jakarta đọc annotation mới sẽ không tự coi annotation javax là tương đương. Provider cũ implement interface javax cũng không tự trở thành provider Jakarta.

### 1.1. Một số javax thuộc Java SE và không được đổi

**Không** thay mọi **javax.** bằng **jakarta.**. Các package sau vẫn thuộc Java SE:

- **javax.annotation.processing** và **javax.lang.model**: annotation processing và compiler model.
- **javax.tools**: Compiler API.
- **javax.xml.parsers** và **javax.xml.transform**: Java SE XML APIs.
- **javax.crypto**, **javax.net**, **javax.sql**, **javax.management**.

Ví dụ tên service descriptor của annotation processor vẫn phải là:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

Không tạo file **META-INF/services/jakarta.annotation.processing.Processor** vì interface đó không phải API Jakarta.

### 1.2. Các lớp tương thích

| Lớp | Câu hỏi | Ví dụ lỗi |
|---|---|---|
| Source | Source dùng đúng API đích? | Import javax.persistence không còn |
| Binary | Class đã compile liên kết đúng? | NoSuchMethodError |
| Generated code | Processor tạo class thuộc namespace đúng? | Metamodel vẫn dùng javax |
| Metadata | Descriptor và XML đúng? | Không tìm thấy provider |
| Packaging | Resource thực sự có trong JAR/WAR? | Service file mất khi shading |
| Runtime | Framework bootstrap được? | ServiceConfigurationError |
| Behavioral | Chức năng vẫn đúng? | Mapper đổi cách xử lý null |

Một lượt compile chỉ kiểm tra một phần bảng này. Không nên xem build thành công là bằng chứng runtime compatible.

## 2. Tại sao cần kiểm tra bên trong JAR?

Một JAR có thể có cấu trúc:

~~~text
application.jar
  com/example/domain/Order.class
  com/example/generated/OrderMapperImpl.class
  META-INF/services/...
  META-INF/persistence.xml
  META-INF/orm.xml
  META-INF/beans.xml
  META-INF/spring/...
  META-INF/MANIFEST.MF
  module-info.class
  META-INF/versions/...
~~~

Các mục có vai trò khác nhau:

1. **Class file**: JVM nạp và xác minh type identity.
2. **Generated class**: JVM hoặc framework dùng để mapping/DI/query.
3. **META-INF/services**: ServiceLoader đọc provider registration.
4. **XML**: JPA, CDI, Servlet hoặc integration framework đọc cấu hình.
5. **Spring metadata**: Spring Boot tìm auto-configurations và handlers.
6. **Manifest/module descriptor**: quyết định launch/module/service metadata.
7. **Multi-release entries**: runtime có thể chọn class variant theo JDK.

Một source file đúng không tự động khiến tài nguyên dạng text trong META-INF được sửa. Một generated file có trong build directory cũng chưa chắc được đưa vào artifact sẽ publish.

## 3. Kiểm kê toàn bộ nguồn sinh mã

Các công cụ thường xuất hiện trong migration Java:

| Công cụ | Output điển hình | Điểm dễ sai |
|---|---|---|
| MapStruct | **MapperImpl.java/.class** | Processor không chạy, dependency sai |
| JPA/Hibernate metamodel | **Customer_.java/.class** | javax versus jakarta metamodel |
| QueryDSL APT | **QCustomer.java/.class** | Processor variant khác namespace |
| Lombok | Getter/builder trong bytecode | Dùng javac internals, JDK support |
| JAXB XJC | Model classes, ObjectFactory, package-info | JAXB annotations javax/jakarta |
| WSDL/wsimport | Service stubs, binding types | API JAX-WS thế hệ cũ |
| OpenAPI Generator | DTO/client/server source | Generated dependency imports |
| Dagger, Immutables, AutoValue | Implementation/source/metadata | Processor path và output ownership |

Các thư mục có thể gặp:

~~~text
target/generated-sources/annotations/
target/generated-test-sources/test-annotations/
build/generated/sources/annotationProcessor/java/main/
build/generated/sources/annotationProcessor/java/test/
build/generated/sources/...
~~~

Đường dẫn chỉ là ví dụ; mỗi plugin có thể cấu hình khác. Cần lập inventory cho từng module: **generator → version → input schema/annotation → output directory → generated class/resource → consumer**.

### 3.1. Vì sao generated code dễ che lỗi?

- Output không được commit nên tìm trong source tree không thấy.
- Local workspace còn output của lần compile trước.
- IDE kích hoạt processor nhưng CI chưa cấu hình.
- Build cache khôi phục generated files.
- Một module khác tiêu thụ generated class.
- Mã sinh nằm trong dependency JAR, không nằm trong module ứng dụng.
- Tool sinh metadata/resources chứ không sinh Java source riêng.

Do đó, nên có **clean build từ đầu** và đối chiếu generated output của chính phiên bản generator đích.

## 4. Ví dụ MapStruct trong migration

Source interface:

~~~java
package com.example.mapping;

import org.mapstruct.Mapper;

@Mapper
public interface OrderMapper {
    OrderDto toDto(OrderEntity entity);
}
~~~

Processor có thể tạo code tương đương:

~~~java
package com.example.mapping;

// Mã minh họa, không phải output cố định cho mọi release.
public final class OrderMapperImpl implements OrderMapper {
    @Override
    public OrderDto toDto(OrderEntity entity) {
        if (entity == null) {
            return null;
        }
        OrderDto result = new OrderDto();
        result.setId(entity.getId());
        return result;
    }
}
~~~

Các câu hỏi cần kiểm tra:

1. Processor có được javac kích hoạt không?
2. Processor có tương thích Java compiler đích không?
3. Generated implementation có được tạo mới trong clean build?
4. Nó tham chiếu DTO/entity thuộc namespace đích không?
5. Class sinh ra có nằm trong JAR cuối?
6. Runtime framework có tìm đúng implementation không?
7. Mapping về null, enum, collection có còn đúng theo contract?

Nếu **OrderMapperImpl** đã từng được commit hoặc còn trong **target/classes**, build có thể giả thành công dù annotation processing không chạy.

## 5. Ví dụ JPA static metamodel

Entity dùng Jakarta Persistence:

~~~java
package com.example.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class Customer {
    @Id
    private Long id;

    private String name;
}
~~~

Một metamodel processor hỗ trợ Jakarta có thể sinh:

~~~java
package com.example.domain;

import jakarta.persistence.metamodel.SingularAttribute;
import jakarta.persistence.metamodel.StaticMetamodel;

@StaticMetamodel(Customer.class)
public abstract class Customer_ {
    public static volatile SingularAttribute<Customer, Long> id;
    public static volatile SingularAttribute<Customer, String> name;
}
~~~

Một file **Customer_.java** vẫn import **javax.persistence.metamodel.SingularAttribute** là dấu hiệu output cũ hoặc processor không phù hợp.

| Hiện tượng | Nguyên nhân cần xét |
|---|---|
| Không có Customer_ | Processor không chạy hoặc không nhận annotation |
| Có Customer_ nhưng dùng javax | Processor/version legacy hoặc stale code |
| Customer_ compile được vì cả hai API cùng nằm classpath | Mismatch bị che bởi dependency |
| Compile thành công nhưng query fail | Mapping/provider khác namespace hoặc behavior |

Không bổ sung **javax.persistence-api** vào Jakarta runtime chỉ để generated metamodel cũ tiếp tục compile, trừ khi có một adapter độc lập được thiết kế có chủ đích.

### 5.1. QueryDSL

QueryDSL có thể có processor artifacts/variants dành cho JPA namespace khác nhau. Khi đổi **javax.persistence** sang **jakarta.persistence**, xác nhận đúng annotation processor variant và các **Q-types** mới. Không suy luận từ tên thư viện rằng nó tự hỗ trợ mọi release.

## 6. JAXB/XJC và generated XML-binding classes

Với XJC hoặc code generators liên quan, output Java có thể chuyển từ:

~~~java
import javax.xml.bind.annotation.XmlElement;
import javax.xml.bind.annotation.XmlRootElement;
~~~

sang:

~~~java
import jakarta.xml.bind.annotation.XmlElement;
import jakarta.xml.bind.annotation.XmlRootElement;
~~~

Sau Java 11, những module/công cụ JAXB legacy từng đi kèm một số JDK đã không còn sẵn trong JDK như trước; cần dependency và generator phù hợp.

Các artifact có thể xuất hiện:

~~~text
Order.java
ObjectFactory.java
package-info.java
jaxb.index
jaxb.properties
~~~

Cần đối chiếu:

- XJC/generator version.
- API/runtime Jakarta XML Binding version.
- Binding files và các customization namespace.
- Generated **ObjectFactory** và **package-info**.
- Resource lookup của runtime.
- XML samples cũ/mới có marshal/unmarshal được không.

**Quan trọng:** Java API đổi từ javax.xml.bind sang jakarta.xml.bind không tự động yêu cầu đổi namespace của **XML dữ liệu nghiệp vụ** do đối tác quy định. XML Schema của hợp đồng trao đổi là một concern riêng.

### 6.1. API không phải runtime implementation

Có Jakarta XML Binding API trên compile classpath không có nghĩa JAXB runtime provider đã được đóng gói. Cần tạo **JAXBContext** và thực hiện ít nhất một round-trip để xác nhận provider hoạt động.

## 7. Annotation processor và thay đổi kích hoạt theo JDK

Annotation processor chuẩn triển khai:

~~~java
javax.annotation.processing.Processor
~~~

và thường đăng ký qua:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

Dù dự án đã chuyển toàn bộ Jakarta APIs, service type Java SE này **không đổi**.

Từ **JDK 23**, javac không còn tự bật implicit annotation processing khi thiếu cấu hình yêu cầu processing. Các JDK 21/22 đã cảnh báo bằng note khi một build dựa vào implicit classpath discovery.

Một migration có thể gặp hai lỗi riêng:

1. Processor không được kích hoạt vì build chưa khai báo processor path.
2. Processor chạy nhưng chỉ nhận các annotation javax cũ.

Sửa lỗi thứ nhất không tự sửa lỗi thứ hai.

### 7.1. Gradle

~~~groovy
plugins {
    id 'java'
}

dependencies {
    implementation 'org.mapstruct:mapstruct:VERSION'
    annotationProcessor 'org.mapstruct:mapstruct-processor:VERSION'
}
~~~

Nếu test source dùng annotation processing:

~~~groovy
dependencies {
    testAnnotationProcessor 'org.mapstruct:mapstruct-processor:VERSION'
}
~~~

**VERSION** phải thay bằng release được xác nhận hỗ trợ JDK/framework đích. Đặt processor chỉ ở **implementation** không phải khai báo tường minh đáng tin cậy.

### 7.2. Maven Compiler Plugin 3.x

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-compiler-plugin</artifactId>
  <version>3.14.1</version>
  <configuration>
    <release>17</release>
    <annotationProcessorPaths>
      <path>
        <groupId>org.mapstruct</groupId>
        <artifactId>mapstruct-processor</artifactId>
        <version>1.6.3</version>
      </path>
    </annotationProcessorPaths>
  </configuration>
</plugin>
~~~

Các versions trong ví dụ minh họa cú pháp. Maven 4 và compiler plugin 4.x có hướng quản lý processor qua dependency type riêng như **processor**, **classpath-processor** hoặc **modular-processor**. Cấu hình phải khớp build tool version.

### 7.3. Compiler JDK khác target Java release

Nếu javac chạy bằng JDK 23 và dùng **--release 17**, processor vẫn chạy trong môi trường javac JDK 23; chỉ output ứng dụng bị giới hạn theo Java 17 target. Với processor dùng **jdk.compiler** internals như một số tích hợp Lombok, JDK compiler mới có thể yêu cầu phiên bản processor mới.

Không dùng **--release 17** như một cách giả lập runtime processor trên JDK 17.

## 8. Java ServiceLoader hoạt động như thế nào?

**ServiceLoader** phát hiện provider implementations cho một service interface. Trên classpath, cơ chế phổ biến sử dụng file:

~~~text
META-INF/services/<service-interface-full-name>
~~~

Ví dụ:

~~~text
META-INF/services/com.example.spi.TextFormatter
~~~

Nội dung:

~~~text
com.example.provider.DefaultTextFormatter
com.example.provider.PrettyTextFormatter
~~~

Tên file phải là tên fully qualified của **service interface**, còn các dòng bên trong là tên provider classes.

### 8.1. Ví dụ service API

~~~java
package com.example.spi;

public interface TextFormatter {
    String format(String input);
}
~~~

Provider:

~~~java
package com.example.provider;

import com.example.spi.TextFormatter;

public final class DefaultTextFormatter implements TextFormatter {
    public DefaultTextFormatter() {
    }

    @Override
    public String format(String input) {
        return input == null ? "" : input.trim();
    }
}
~~~

Tài nguyên:

~~~text
src/main/resources/META-INF/services/com.example.spi.TextFormatter
~~~

Nội dung:

~~~text
com.example.provider.DefaultTextFormatter
~~~

Consumer:

~~~java
package com.example.app;

import com.example.spi.TextFormatter;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        TextFormatter formatter = ServiceLoader
            .load(TextFormatter.class)
            .findFirst()
            .orElseThrow(() ->
                new IllegalStateException("No provider"));

        System.out.println(formatter.format("  Hello  "));
    }
}
~~~

Với classpath và packaging đúng, output là **Hello**.

### 8.2. Provider class tồn tại chưa chắc nạp được

Provider còn phải:

- Implement đúng service type.
- Có đủ dependency transitive.
- Được classloader phù hợp nhìn thấy.
- Có cách khởi tạo hợp lệ theo ServiceLoader.
- Không bị relocation khiến descriptor trỏ tên cũ.
- Không xung đột với một bản API khác ở runtime.

File **META-INF/services** tồn tại chỉ là một bước trong kiểm chứng.

## 9. Service descriptors khi migrate javax sang jakarta

Hai file sau là **hai resource khác nhau**:

~~~text
META-INF/services/javax.persistence.spi.PersistenceProvider
META-INF/services/jakarta.persistence.spi.PersistenceProvider
~~~

Runtime Jakarta Persistence tìm provider của **jakarta.persistence.spi.PersistenceProvider** không tự xem descriptor javax là tương đương.

Một số ví dụ:

| Loại provider | Service descriptor legacy | Jakarta |
|---|---|---|
| JPA | **javax.persistence.spi.PersistenceProvider** | **jakarta.persistence.spi.PersistenceProvider** |
| Bean Validation | **javax.validation.spi.ValidationProvider** | **jakarta.validation.spi.ValidationProvider** |
| Servlet initializer | **javax.servlet.ServletContainerInitializer** | **jakarta.servlet.ServletContainerInitializer** |
| Compiler annotation processor | **javax.annotation.processing.Processor** | **Giữ nguyên javax** |

Các tên trong bảng cần được đặt dưới thư mục **META-INF/services/** nếu dùng cơ chế file-based service discovery tương ứng.

### 9.1. Provider JPA

Một Jakarta-compatible JPA provider JAR có thể có:

~~~text
META-INF/services/jakarta.persistence.spi.PersistenceProvider
~~~

với provider class ví dụ:

~~~text
org.hibernate.jpa.HibernatePersistenceProvider
~~~

Tên này phải tồn tại trong artifact đúng version, và class phải thực sự implement Jakarta Persistence SPI. Chỉ đổi nội dung service descriptor là không đủ để biến implementation javax thành Jakarta.

### 9.2. Bean Validation

Với Jakarta Validation, cần đúng API **jakarta.validation.Validation**, provider SPI **jakarta.validation.spi.ValidationProvider** và runtime implementation tương thích. Một project compile **@NotNull** được nhưng runtime không tìm provider vẫn có thể thất bại khi tạo validator factory.

### 9.3. ServletContainerInitializer

Ứng dụng Jakarta Servlet cần implementation thuộc **jakarta.servlet.ServletContainerInitializer**. Một JAR extension cũ chỉ có **javax.servlet.ServletContainerInitializer** sẽ không tự được Jakarta container xem là cùng loại initializer.

Một WAR có thể deploy nhưng một listener/filter/initializer mong đợi không được đăng ký. Đây là lỗi runtime metadata chứ không nhất thiết là lỗi source compiler.

## 10. JPMS và module-info.java

Với Java Platform Module System, explicit named modules có thể dùng khai báo:

~~~java
module com.example.formatter.provider {
    requires com.example.formatter.api;

    provides com.example.spi.TextFormatter
        with com.example.provider.DefaultTextFormatter;
}
~~~

Consumer module:

~~~java
module com.example.formatter.app {
    requires com.example.formatter.api;

    uses com.example.spi.TextFormatter;
}
~~~

Đây là module names minh họa. API module phải export service interface package, provider và consumer modules cần có module graph phù hợp.

| Packaging | Cơ chế thường cần xem |
|---|---|
| Plain JAR trên classpath | META-INF/services |
| Explicit named module | uses/provides trong module-info |
| Automatic module | Quy tắc automatic module và service registration |
| WAR/EAR/container | Classloader/container resource discovery |
| Nested executable JAR | Resource loading của launcher |

### 10.1. Classloader có thể quyết định thành bại

Trong application server hoặc plugin architecture, cùng fully qualified name được nạp bởi hai classloaders có thể là hai runtime types khác nhau. Provider implement một bản interface nhưng consumer dùng bản interface khác có thể gây **ServiceConfigurationError** hoặc **ClassCastException**.

Một cách chẩn đoán:

~~~java
ClassLoader loader =
    Thread.currentThread().getContextClassLoader();

ServiceLoader<TextFormatter> providers =
    ServiceLoader.load(TextFormatter.class, loader);
~~~

Đổi loader chỉ là một phép thử; nếu API dependency bị nạp trùng, cần sửa ownership và classloader isolation.

### 10.2. Kiểm tra module metadata

~~~bash
jar --describe-module --file provider.jar
~~~

Kiểm tra **module-info.class**, **Automatic-Module-Name** nếu có, và service directives. Đừng tự suy đoán tên module từ artifactId.

## 11. Shaded/fat JAR: rủi ro mất service files

Hai JAR có thể cùng chứa:

~~~text
META-INF/services/com.example.spi.TextFormatter
~~~

JAR A ghi **ProviderA**, JAR B ghi **ProviderB**. Khi tạo một fat JAR mà chỉ giữ lại một resource, provider còn lại biến mất.

Kết quả mong muốn là service file được merge:

~~~text
com.example.provider.ProviderA
com.example.provider.ProviderB
~~~

### 11.1. Maven Shade

Có thể dùng **ServicesResourceTransformer**:

~~~xml
<transformers>
  <transformer
      implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
</transformers>
~~~

### 11.2. Gradle Shadow

Một cấu hình minh họa:

~~~groovy
tasks.named('shadowJar') {
    mergeServiceFiles()
}
~~~

Cấu hình thực tế tùy plugin version. Sau khi shading, vẫn phải đọc final JAR để xác nhận service descriptor và provider classes được giữ lại.

### 11.3. Relocation đổi tên class

Nếu shading đổi:

~~~text
com.example.provider.ProviderA
~~~

thành:

~~~text
hidden.com.example.provider.ProviderA
~~~

nhưng service file vẫn trỏ tên cũ, provider không được nạp. Kiểm tra transformer/relocation rules.

### 11.4. Các resources khác không thể merge bằng cách nối dòng

- **META-INF/persistence.xml**
- **META-INF/beans.xml**
- **META-INF/spring.handlers**
- **META-INF/spring.schemas**
- **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

Một resource merge strategy phù hợp ServiceLoader không nhất thiết phù hợp XML, properties hoặc Spring metadata. Không gộp hai XML documents bằng phép nối text.

## 12. META-INF/persistence.xml và Jakarta Persistence

Một Jakarta JPA deployment có thể dùng file:

~~~text
META-INF/persistence.xml
~~~

Ví dụ Jakarta Persistence 3.0:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        https://jakarta.ee/xml/ns/persistence
        https://jakarta.ee/xml/ns/persistence/persistence_3_0.xsd"
    version="3.0">

    <persistence-unit name="ordersPU"
                      transaction-type="RESOURCE_LOCAL">
        <class>com.example.domain.OrderEntity</class>
        <properties>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:h2:mem:orders"/>
        </properties>
    </persistence-unit>
</persistence>
~~~

Cấu hình chỉ minh họa cấu trúc. Database, datasource, provider và transaction management cần được thiết kế cho runtime thật.

### 12.1. Những mục cần đối chiếu

- Namespace và XML schema version có đúng Jakarta release?
- Persistence unit name còn khớp?
- Entity classes có tồn tại?
- Mapping-file **orm.xml** có path và namespace đúng?
- Provider class được nêu tường minh có còn đúng không?
- Property keys thuộc API/framework version?
- File có thực sự trong JAR/WAR?
- Bootstrap persistence unit có thành công tại runtime?

### 12.2. Không bỏ qua XML mapping

**META-INF/orm.xml** có thể chứa entity class names, field names, access modes và relationship mappings. Chuyển annotation Java sang Jakarta chưa làm XML ở dependency JAR khác tự thay đổi.

## 13. Các descriptor khác trong JAR/WAR

### 13.1. CDI

Thường gặp:

~~~text
META-INF/beans.xml
WEB-INF/beans.xml
~~~

Kiểm tra CDI version, XML schema, **bean-discovery-mode**, bean archive và class names. Quy tắc bean discovery có thể thay đổi theo framework/runtime version; không giả định một file rỗng luôn cho kết quả giống nhau.

### 13.2. Servlet

Một WAR thường chứa:

~~~text
WEB-INF/web.xml
~~~

Ví dụ Jakarta Servlet 6.0:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<web-app
    xmlns="https://jakarta.ee/xml/ns/jakartaee"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        https://jakarta.ee/xml/ns/jakartaee
        https://jakarta.ee/xml/ns/jakartaee/web-app_6_0.xsd"
    version="6.0">
</web-app>
~~~

Đây không phải schema áp dụng cho mọi Servlet container. Chọn descriptor version phù hợp container được hỗ trợ. Ngoài XML namespace, xem servlet/filter/listener FQCN và init-params.

### 13.3. WAR layout

~~~text
application.war
  WEB-INF/classes/com/example/...
  WEB-INF/classes/META-INF/persistence.xml
  WEB-INF/lib/provider.jar
  WEB-INF/lib/other.jar
  WEB-INF/web.xml
~~~

Service descriptor có thể nằm trong một dependency JAR dưới **WEB-INF/lib**. Chỉ kiểm tra root WAR không đủ; còn cần xem nested JAR và classloader.

### 13.4. Các tài nguyên đáng lưu ý khác

- **META-INF/validation.xml** khi dùng Bean Validation XML.
- **META-INF/web-fragment.xml** của web libraries.
- Taglib/TLD resources.
- **META-INF/spring.factories**, **spring.handlers**, **spring.schemas**.
- **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**.
- **META-INF/native-image/**.
- **META-INF/MANIFEST.MF**.
- **module-info.class**.
- **META-INF/versions/** trong multi-release JAR.

## 14. Spring Boot auto-configuration resources

Trong nhiều Spring Boot libraries, auto-configuration được khai báo tại:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung là các auto-configuration class names:

~~~text
com.example.autoconfigure.OrdersAutoConfiguration
com.example.autoconfigure.OrdersMetricsAutoConfiguration
~~~

Spring Boot 2.7 hỗ trợ cơ chế imports và Spring Boot 3 sử dụng nó cho auto-configuration thay cho cách đăng ký cũ bằng key tương ứng trong **spring.factories**.

### 14.1. Không xóa spring.factories một cách mù quáng

**spring.factories** vẫn có thể được dùng cho các extension points khác theo Spring version. Cần xác định resource nào được framework đích đọc.

Ngoài ra, một auto-config class có thể tồn tại nhưng điều kiện **@ConditionalOnClass** hoặc tương tự vẫn tham chiếu **javax.servlet.\***, khiến configuration không kích hoạt như mong muốn trên Jakarta stack.

### 14.2. Resource bị mất do shading

Nếu nhiều dependency đóng góp **AutoConfiguration.imports** và fat JAR chỉ giữ một resource, auto-config khác sẽ biến mất. Cần xác minh merge strategy đúng cho format này, không giả định **mergeServiceFiles()** tự xử lý nó.

## 15. Kiểm tra JAR bằng công cụ JDK

### 15.1. Liệt kê entries

~~~bash
jar tf application.jar
~~~

Hoặc:

~~~bash
jar --list --file application.jar
~~~

Tìm các đường dẫn:

~~~text
META-INF/services/
META-INF/persistence.xml
META-INF/orm.xml
META-INF/beans.xml
META-INF/spring/
META-INF/MANIFEST.MF
module-info.class
META-INF/versions/
com/example/generated/
~~~

### 15.2. Đọc service descriptor

Trên hệ có unzip:

~~~bash
unzip -p application.jar META-INF/services/com.example.spi.TextFormatter
~~~

Hoặc trích ra trong **thư mục kiểm tra riêng**:

~~~bash
jar xf application.jar META-INF/services/com.example.spi.TextFormatter
~~~

Tránh giải nén đè lên source workspace. Một entry tồn tại không có nghĩa nội dung của nó đúng; phải đọc service names bên trong.

### 15.3. Kiểm tra class file

~~~bash
javap -classpath application.jar -p com.example.domain.Customer
~~~

Muốn xem thêm metadata/constant pool:

~~~bash
javap -classpath application.jar -v com.example.domain.Customer
~~~

Có thể tìm những reference **javax.persistence** đáng ngờ. Tuy nhiên, string javax trong JAR không tự động là lỗi do còn Java SE javax packages hợp lệ.

### 15.4. jdeps

~~~bash
jdeps --recursive --multi-release 21 application.jar
~~~

Kiểm tra API JDK nội bộ:

~~~bash
jdeps --jdk-internals application.jar
~~~

**jdeps** không phân tích thay cho các file resource text hoặc tên class chỉ được ghi dưới dạng XML/ServiceLoader string. Một kết quả sạch chưa chứng minh migration metadata đúng.

### 15.5. JPMS metadata

~~~bash
jar --describe-module --file application.jar
~~~

Với multi-release JAR, cần kiểm tra class/module variant được dùng trên runtime JDK đích.

### 15.6. Gắn artifact với checksum

PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 -LiteralPath application.jar
~~~

Unix:

~~~bash
sha256sum application.jar
~~~

Cần có bằng chứng rằng file đã kiểm tra là file được publish/deploy, không phải một artifact khác được build lại trong container image.

## 16. Tự động kiểm tra entries với JarFile

~~~java
package com.example.verify;

import java.io.IOException;
import java.nio.file.Path;
import java.util.jar.JarFile;

public final class JarInspector {
    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException("JAR path required");
        }

        try (JarFile jar = new JarFile(Path.of(args[0]).toFile())) {
            requireEntry(
                jar,
                "META-INF/services/com.example.spi.TextFormatter"
            );
            requireEntry(
                jar,
                "com/example/provider/DefaultTextFormatter.class"
            );
        }
    }

    private static void requireEntry(JarFile jar, String path) {
        if (jar.getJarEntry(path) == null) {
            throw new IllegalStateException("Missing: " + path);
        }
    }
}
~~~

Đây là **structural test**: kiểm tra sự hiện diện của entry. Nó chưa đọc nội dung descriptor và chưa thử tạo provider.

### 16.1. Các mức xác minh

1. **Structural:** resource/class tồn tại trong archive.
2. **Metadata:** resource chứa service/provider/namespace/version đúng.
3. **Runtime:** framework/ServiceLoader khởi tạo provider thành công.
4. **Behavioral:** tính năng nghiệp vụ cho kết quả mong đợi.

Một test ở mức 1 không thay thế mức 3/4. Cần đặt acceptance criteria đúng với rủi ro.

## 17. ServiceLoader smoke test

Ví dụ với JUnit 5:

~~~java
import com.example.spi.TextFormatter;
import java.util.ServiceLoader;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertTrue;

class ProviderDiscoveryTest {
    @Test
    void findsProvider() {
        boolean found = ServiceLoader.load(TextFormatter.class)
            .stream()
            .anyMatch(provider ->
                provider.type().getName().equals(
                    "com.example.provider.DefaultTextFormatter"
                )
            );

        assertTrue(found);
    }
}
~~~

**Lưu ý:** nếu test chạy trên classpath **build/classes + build/resources**, có thể bỏ sót lỗi packaging JAR. Với artifact-release gate, chạy test dùng **JAR cuối** và đúng launch mechanism.

### 17.1. Kiểm chứng JPA

- Bootstrap Jakarta Persistence unit.
- Xác nhận provider/version đã chọn.
- Khởi tạo entity manager factory.
- Thực hiện thao tác persistence representative.
- Đóng tài nguyên.

### 17.2. Kiểm chứng Bean Validation

~~~java
import jakarta.validation.Validation;

var factory = Validation.buildDefaultValidatorFactory();
try {
    var validator = factory.getValidator();
    // Validate object thật có constraint.
} finally {
    factory.close();
}
~~~

Compile **@NotNull** không chứng minh runtime validation provider đã có. Cần ít nhất một bootstrap và validation thực tế.

### 17.3. Kiểm chứng JAXB

Tạo **jakarta.xml.bind.JAXBContext** và marshal/unmarshal dữ liệu mẫu. Nếu API JAR có nhưng implementation runtime không có, lỗi thường chỉ xuất hiện khi tạo context.

### 17.4. Kiểm chứng Servlet

Với WAR, kiểm tra deployment trên Jakarta Servlet container phù hợp. ServiceLoader test đơn lẻ không mô phỏng hết container lifecycle và classloader rules.

## 18. Các lỗi phổ biến và hướng điều tra

| Lỗi / triệu chứng | Nguyên nhân khả dĩ | Bước kiểm tra |
|---|---|---|
| **ServiceConfigurationError** | Descriptor/provider sai | META-INF/services và cause |
| **ClassNotFoundException** | Resource chứa class name không còn | JAR entries, loader |
| **NoClassDefFoundError** | Provider thiếu dependency | Runtime graph, static initializer |
| **ClassCastException** | Provider không thuộc service type | javax/jakarta, classloader |
| **NoSuchMethodError** | Binary API/provider versions không khớp | javap và JAR version |
| **AbstractMethodError** | SPI contract khác implementation | Interface/method signatures |
| **IllegalAccessError** | Module access hoặc binary access sai | JPMS, class metadata |
| **No Persistence provider** | JPA service/bootstrap không tương thích | persistence.xml, provider JAR |
| **Validation provider missing** | API và implementation khác namespace | Validation SPI |
| **JAXBException** lúc bootstrap | Runtime JAXB implementation/metadata thiếu | JAXB artifacts |
| **cannot find symbol** cho generated type | Processor không chạy hoặc output stale | Clean compile, processor path |
| **FilerException** | Processor ghi file trùng | Processing rounds, output dirs |
| Spring auto-config bị bỏ qua | Metadata/class/condition sai | AutoConfiguration.imports |
| XML parse/schema error | Resource namespace/version lỗi | XML trong final artifact |

Cần đọc full stack trace, cause chain, tên provider và artifact thực sự được nạp. Không chữa mọi lỗi bằng cách thêm một JAR javax khác.

## 19. Multi-release JAR và manifest

Một multi-release JAR có thể có:

~~~text
META-INF/MANIFEST.MF
META-INF/versions/9/module-info.class
META-INF/versions/17/com/example/SomeClass.class
com/example/SomeClass.class
~~~

Khi manifest có **Multi-Release: true**, runtime có thể chọn class variant theo JDK version. Nếu nâng JDK, biến thể được nạp có thể khác baseline và vẫn tham chiếu Java EE namespace cũ.

Cần kiểm tra:

- Manifest.
- Base class và các variant liên quan.
- Class-file version.
- Module metadata.
- Dependencies của từng variant.
- Service registration theo cơ chế đặc tả, không tự giả định phiên bản hóa service file.

Lệnh hữu ích:

~~~bash
jar tf library.jar
jar --describe-module --file library.jar
jdeps --multi-release 17 library.jar
~~~

## 20. Đóng gói và class loader thật

### 20.1. Plain JAR

Runtime classpath có thể nhìn trực tiếp class/resources ở root archive. Đây là trường hợp khác nested executable JAR.

### 20.2. Spring Boot executable JAR

Một số Boot JAR chứa nested libraries và launcher. Lệnh chạy đúng có thể là:

~~~bash
java -jar application.jar
~~~

Thử **java -cp application.jar com.example.Main** không luôn tương đương vì nested JARs/resource loader khác. Khi kiểm chứng provider, dùng cơ chế launch thực sự của production.

### 20.3. WAR

Jakarta Servlet container có thể cung cấp API runtime, còn ứng dụng cung cấp implementation libraries. Kiểm tra:

- WAR có đóng gói nhầm servlet API legacy không?
- Container hỗ trợ Jakarta Servlet version nào?
- WEB-INF/classes và WEB-INF/lib đúng?
- WEB-INF/web.xml và service descriptors đúng?
- ServletContainerInitializer có thực thi?

### 20.4. EAR/container shared libraries

Nếu provider nằm ở server-shared library còn API nằm trong WAR, có thể xảy ra classloader isolation hoặc duplicate classes. Một JAR đúng về mặt file chưa chắc được đúng loader nạp.

### 20.5. Container image

Artifact được test có thể khác file được copy vào image. Nên đối chiếu checksum và entry list ở đúng stage deploy.

## 21. Dependency graph: javax và jakarta đồng thời

Ví dụ:

~~~text
application
  +-- jakarta.persistence-api
  +-- Hibernate compatible with Jakarta
  +-- legacy-validation-extension
        +-- javax.validation-api
  +-- jakarta.validation-api
~~~

Việc cả hai API cùng tồn tại không tự động là sai trong mọi trường hợp, nhưng cần xác định có adapter có chủ đích hay không. Nếu extension được compile cho **javax.validation.spi.ValidationProvider**, nó không tự phục vụ **jakarta.validation.Validation**.

Ba nhóm path cần phân biệt:

- **Compile classpath:** source cần APIs nào?
- **Processor path:** code generators nào chạy?
- **Runtime classpath/module path:** provider implementations và resources nào tồn tại?

Lệnh khảo sát:

~~~bash
mvn dependency:tree
~~~

hoặc:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration annotationProcessor
~~~

Dependency graph là bằng chứng version/path, chưa chắc chỉ ra mọi service resource sau shading.

## 22. Ma trận kiểm thử artifact

| Trường hợp | Source/generated | Packaging | Runtime | Cần chứng minh |
|---|---|---|---|---|
| Baseline Java EE | javax | Legacy JAR/WAR | Legacy stack | Hành vi cũ |
| Generated code mới | jakarta | Compile output | Target javac | Mã sinh đúng |
| Plain JAR Jakarta | jakarta | META-INF/services | Classpath | SPI discovery |
| Named module | jakarta | module-info | Module path | uses/provides |
| Shaded JAR | jakarta | Merged descriptors | Launcher thật | Không mất provider |
| WAR | jakarta | WEB-INF/META-INF | Jakarta container | Deployment |
| Spring starter | jakarta | AutoConfiguration.imports | Boot target | Auto-config |
| Clean CI | jakarta | Artifact tái lập | Target JDK | Không dùng stale files |
| Negative case | javax provider | Jakarta API consumer | Target runtime | Phát hiện mismatch |

Test nên bao gồm các bước theo thứ tự:

1. Clean compile/generation.
2. Check generated source namespace.
3. Check artifact entries.
4. Read service/XML metadata.
5. Runtime provider bootstrap.
6. Integration behavior test.
7. Verify artifact checksum và launch layout.

Không cần bắt các tổ hợp legacy/Jakarta không được hỗ trợ chạy thành công. Mục tiêu là phát hiện mismatch sớm.

## 23. Quy trình migration theo gates

### Gate A — Inventory

- Chốt JDK/framework/Java EE/Jakarta versions.
- Liệt kê processors, generators và output.
- Liệt kê SPI names và provider classes.
- Liệt kê JAR/WAR resources.
- Xác định classloader/packaging.
- Lưu artifact baseline và checksum.

### Gate B — Generated code

- Nâng processor/generator hỗ trợ Jakarta.
- Cấu hình annotation processing explicit.
- Dùng clean build.
- Soát output có namespace đúng.
- Không phụ thuộc generated files cũ.
- Đảm bảo generated class được package.

### Gate C — Services và resources

- Dùng Jakarta SPI descriptor names cho APIs đã chuyển.
- Giữ **javax.annotation.processing.Processor**.
- Kiểm tra provider class và dependencies.
- Cập nhật XML schemas/version/class names.
- Kiểm tra Spring metadata và shading rules.
- Kiểm tra module-info/manifest/multi-release.

### Gate D — Runtime

- Chạy artifact trong target JDK/container.
- Test ServiceLoader.
- Test JPA/Validation/JAXB bootstrap.
- Test Servlet/Spring integration.
- Test behavior và error paths.
- Chốt release evidence.

### Gate E — Cleanup

- Loại dependencies/adapters cũ khi không còn consumer.
- Xóa stale generator outputs theo build lifecycle.
- Bỏ packaging workaround không còn cần.
- Cập nhật build templates và documentation.
- Lưu rollback pairing và các exception được chấp nhận.

## 24. Mẫu ghi nhận kết quả

~~~text
Migration ID:
Module / component:
Owner:
Baseline Java EE/JDK:
Target Jakarta EE/JDK:
Framework and container versions:
Packaging: jar / bootJar / war / ear / module

Code generators and versions:
Annotation APIs and processors:
Generated directories:
Generated classes/resources:
Namespace scan result:

Service interface old/new:
Provider implementation:
Service descriptor paths:
JPMS uses/provides:
Classloader expectations:

XML/resource inventory:
persistence.xml:
orm.xml:
beans.xml:
validation.xml:
web.xml:
Spring metadata:
Manifest/multi-release:
Shade/relocation/merge:

Artifact checksum:
Structural checks:
Provider bootstrap tests:
Business integration tests:
Legacy adapters:
Rollback plan:
Blockers:
Owner approval:
~~~

Mẫu này tạo một đường truy vết từ code generator tới file được đóng gói và runtime consumer.

## 25. Checklist trước khi phát hành

### Mã sinh

- [ ] Đã kiểm kê processors và generators.
- [ ] Đã nâng tool hỗ trợ Jakarta namespace.
- [ ] Đã kích hoạt annotation processing tường minh.
- [ ] Test/main source sets được xét riêng.
- [ ] Generated files là kết quả clean build.
- [ ] Không có stale generated artifacts che lỗi.
- [ ] Generated source không còn legacy API ngoài phạm vi phê duyệt.
- [ ] Generated class/resource có mặt trong JAR/WAR cuối.

### Service provider

- [ ] Service descriptor name khớp interface.
- [ ] Jakarta service names được cập nhật đúng.
- [ ] **javax.annotation.processing.Processor** được giữ nguyên.
- [ ] Provider implement đúng Jakarta SPI.
- [ ] Provider dependencies có ở runtime.
- [ ] Classloader/JPMS configuration đúng.
- [ ] Shaded JAR merge descriptors đúng.
- [ ] Runtime ServiceLoader/provider bootstrap thành công.

### Tài nguyên

- [ ] persistence.xml và orm.xml phù hợp runtime.
- [ ] beans.xml, validation.xml, web.xml phù hợp framework.
- [ ] Spring metadata và custom resources không bị mất.
- [ ] Các FQCN trong XML/properties được đối chiếu.
- [ ] Manifest và multi-release variants được kiểm tra.
- [ ] Không đổi XML namespace nghiệp vụ ngoài contract.
- [ ] Kiểm tra nested JARs và WAR layout.
- [ ] Artifact kiểm tra có checksum khớp artifact deploy.

### Vận hành

- [ ] Clean CI kiểm chứng generated outputs.
- [ ] Có structural/metadata/runtime tests.
- [ ] Không xem compile success là đủ.
- [ ] Không replace-all mọi javax packages.
- [ ] Không thêm legacy API chỉ để che mismatch.
- [ ] Có release gate, owner và rollback plan.
- [ ] Có tài liệu về adapters/legacy exceptions còn được hỗ trợ.

## 26. Tài liệu tham khảo

- **Jakarta EE Specifications:** https://jakarta.ee/specifications/
- **Jakarta Persistence:** https://jakarta.ee/specifications/persistence/
- **Jakarta Servlet:** https://jakarta.ee/specifications/servlet/
- **Jakarta Bean Validation:** https://jakarta.ee/specifications/bean-validation/
- **Jakarta XML Binding:** https://jakarta.ee/specifications/xml-binding/
- **Java ServiceLoader:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html
- **Java JarFile:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/jar/JarFile.html
- **Java Annotation Processing:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/annotation/processing/package-summary.html
- **javac tool:** https://docs.oracle.com/en/java/javase/23/docs/specs/man/javac.html
- **Spring Boot Auto-Configuration:** https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- **Maven Shade Resource Transformers:** https://maven.apache.org/plugins/maven-shade-plugin/examples/resource-transformers.html
- **Gradle Shadow:** https://gradleup.com/shadow/configuration/merging/
- **JAR tool:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html

Mỗi ví dụ phải được đối chiếu theo Java/Jakarta/Servlet/Spring/Hibernate/build-tool version thực tế. Một cấu hình chỉ đúng ở phiên bản mới hơn không tự áp dụng cho dự án chạy ở nền tảng cũ.

---

**Kết luận:** Chuyển Java EE sang Jakarta không hoàn tất khi các import Java đã đổi. Cần xác minh **generated source/classes**, **META-INF/services và provider implementation**, **XML/resource trong JAR/WAR**, và cách chúng được nạp ở runtime. Quy trình đáng tin cậy là clean generation, kiểm tra artifact cuối, đối chiếu service/interface names, xác minh provider bootstrap và kiểm thử tích hợp với container đích. **Build thành công nhưng provider không được phát hiện** là một lỗi migration điển hình; kiểm tra đủ ba lớp mã sinh, service và tài nguyên sẽ giúp ngăn vấn đề đó trước khi phát hành.
