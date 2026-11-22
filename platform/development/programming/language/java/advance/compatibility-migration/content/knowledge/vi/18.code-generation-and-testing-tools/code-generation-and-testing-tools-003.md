# Mã sinh từ OpenAPI, JAXB hoặc Protocol Buffers

## 1. Vì sao mã sinh là điểm dễ bị bỏ sót khi nâng JDK?

Trong nhiều dự án Java, một phần mã nguồn không được lập trình viên viết trực tiếp. Nó được **sinh từ một mô tả hợp đồng** như OpenAPI, XML Schema (XSD) hoặc tệp `.proto`. Các lớp DTO, HTTP client, controller interface, JAXB binding, protobuf message và adapter liên quan có thể được tạo lại mỗi lần build hoặc được commit vào repository.

Khi chuyển JDK, nhóm phát triển có thể nhìn thấy lỗi xuất hiện trong một file Java được sinh ra rồi sửa trực tiếp file đó. Cách sửa này thường không bền vững: lần chạy generator tiếp theo có thể ghi đè tất cả. Vấn đề gốc có thể nằm ở phiên bản **generator**, **template**, **schema**, **plugin build**, **runtime library** hoặc **kiểu Java mà generator đang nhắm tới**.

Một ví dụ đơn giản:

- Ứng dụng nâng runtime từ JDK 17 lên JDK 21.
- OpenAPI generator cũ tạo code import `javax.annotation.Generated` hoặc `javax.validation.*`, trong khi framework mới dùng các API `jakarta.*` tương ứng.
- Một plugin XJC còn giả định JAXB có sẵn trong JDK, nhưng runtime đích không đóng gói JAXB như ở các Java release cũ.
- Một build plugin gọi `protoc` bản khác với protobuf Java runtime mà ứng dụng dùng.
- Generated source được commit từ trước; CI không chạy generator nên build thành công, nhưng file sinh mới từ máy phát triển lại khác.
- Đổi tên field trong schema làm code sinh đổi tên getter; Java compiler báo lỗi dù wire format có thể vẫn đọc được dữ liệu cũ.

Đó là lý do cần xem generated code như **kết quả của một pipeline có phiên bản và hợp đồng**, không phải như source code viết tay độc lập.

Bài học tập trung vào ba hệ sinh thái phổ biến:

1. **OpenAPI:** sinh Java HTTP client, server stub, interface, model và mã tích hợp dựa trên mô tả REST API.
2. **JAXB/XJC:** sinh Java binding classes từ XSD hoặc ánh xạ object Java với XML theo JAXB.
3. **Protocol Buffers:** sinh Java message classes, builder, parser và những thành phần hỗ trợ từ schema `.proto`.

Mục tiêu là kiểm kê pipeline, nhận diện compatibility blockers và tổ chức việc sinh lại mã an toàn khi nâng JDK, compiler, framework hoặc dependency.

## 2. Năm lớp tương thích phải kiểm tra riêng

Việc nói “generator hỗ trợ Java 21” chưa đủ để kết luận dự án có thể nâng JDK. Cần phân biệt:

| Lớp | Câu hỏi cần trả lời | Rủi ro điển hình |
| --- | --- | --- |
| Schema/contract | OpenAPI, XSD hoặc `.proto` còn tương thích với client và dữ liệu cũ không? | Xóa field, đổi loại dữ liệu, đổi mã trạng thái |
| Generator executable | Generator, plugin, `protoc` hay XJC có chạy trên build JDK đích không? | Plugin không khởi động, API compiler nội bộ thay đổi |
| Generated Java source | Java code mới có compile với source/release target không? | Import thiếu, keyword mới, kiểu API không hỗ trợ |
| Generated runtime dependencies | Các thư viện mà code sinh sử dụng có phù hợp JDK/framework không? | `javax`/`jakarta` lệch, Jackson/OkHttp/protobuf runtime không tương thích |
| Consumer compatibility | Các module đã compile và dữ liệu đã phát hành có tiếp tục hoạt động không? | Getter/class đổi tên, API descriptor đổi, payload không đọc được |

Thêm một lớp thứ sáu rất quan trọng là **behavioral compatibility**: cùng một schema nhưng generator mới có thể biểu diễn `null`, default value, collection, date/time, enum hoặc lỗi HTTP khác trước. Source compile thành công không chứng minh ứng dụng còn hành xử như mong đợi.

Ví dụ `String` trong generated model có thể chuyển từ một trường nullable sang một wrapper khác, hoặc code mới chuyển từ field-based JSON mapping sang constructor-based mapping. Đường gọi vẫn chạy nhưng ý nghĩa dữ liệu vắng mặt đã thay đổi.

## 3. Pipeline sinh mã và các điểm cần cố định phiên bản

Quy trình khái quát:

~~~text
            Contract source
      OpenAPI | XSD | *.proto
                |
                v
      Generator + templates
       + configuration
                |
                v
       Generated Java source
                |
                v
      javac / language compiler
                |
                v
       Generated class files
                |
                v
      Runtime dependencies
       + deployed JDK/JRE
                |
                v
          Application
~~~

Mỗi đầu vào cần có nguồn gốc rõ:

- **Schema:** path, repository/commit, schema version, contract owner.
- **Generator:** tên, chính xác version, distribution/checksum hoặc cách được cài đặt.
- **Templates:** template mặc định hay custom, phiên bản và những override cụ thể.
- **Configuration:** ngôn ngữ đích, package, thư viện transport, annotation strategy, nullability/date options.
- **Build environment:** JDK chạy generator, Maven/Gradle/plugin version, hệ điều hành khi có ảnh hưởng.
- **Compiler:** compiler JDK, `--release`, language level.
- **Runtime:** thư viện JSON/XML/protobuf, framework, JDK image và environment.

Chỉ cố định schema mà bỏ version generator vẫn có thể tạo output khác sau một lần build. Ngược lại, cố định generator nhưng lấy contract từ URL “latest” không có revision cũng làm build không tái lập.

## 4. Kiểm kê generated code trong dự án

Trước khi sửa, xác định ba điều: mã nào được sinh, công cụ nào sinh và nguồn hợp đồng nằm ở đâu.

Các vị trí thường gặp:

~~~text
src/main/openapi/*.yaml
src/main/resources/xsd/*.xsd
src/main/proto/*.proto
build/generated/
target/generated-sources/
generated-src/
src/generated/java/
gradle build scripts / pom.xml
custom template directories
~~~

Không phải dự án nào cũng theo cấu trúc này; có thể code được sinh ở một repository riêng rồi đóng gói thành dependency JAR. Nếu vậy, nâng JDK ứng dụng còn liên quan pipeline phát hành của JAR generated đó.

Mẫu kiểm kê:

| Thuộc tính | Ví dụ cần ghi |
| --- | --- |
| Generated module | `orders-api-client` |
| Contract source | `src/main/openapi/orders.yaml` |
| Contract revision | Commit/tag được duyệt |
| Generator | OpenAPI Generator/XJC/`protoc` |
| Generator version | Phiên bản cố định trong wrapper/plugin |
| Build integration | Task Gradle hoặc Maven phase/goal |
| Output path | `build/generated/...` |
| Target package | `com.example.api.generated` |
| Runtime libraries | Jackson, JAXB Runtime, protobuf-java, HTTP client |
| Java compatibility | Build JDK, compiler JDK, `--release`, runtime tối thiểu |
| Consumers | Server, mobile backend, plugin, downstream JAR |
| Owner | Nhóm quản lý hợp đồng và generated artifact |

Một repository có thể dùng đồng thời cả ba công cụ. Cần bản ghi riêng cho từng pipeline, vì cùng một JDK migration có thể yêu cầu ba thay đổi khác nhau.

## 5. Nguyên tắc cơ bản: sửa nguồn sinh, không sửa output bằng tay

Giả sử code được tạo:

~~~java
// Generated code. Do not edit directly.
public class OrderDto {
    private String orderId;

    public String getOrderId() {
        return orderId;
    }
}
~~~

Nếu cần đổi tên `getOrderId()` hoặc annotation của class, không nên mở file generated và sửa trực tiếp rồi coi là hoàn thành. Thay đổi đó có thể mất sau lần chạy generator hoặc gây khác nhau giữa máy local và CI.

Vị trí sửa thường là:

1. **Schema:** tên/kiểu field, constraint, operation hoặc message nếu hợp đồng cần đổi.
2. **Generator configuration:** generator type, library, naming, serialization, nullable và package options.
3. **Template customization:** chỉ khi cấu hình chuẩn không đáp ứng và nhóm sẵn sàng bảo trì template.
4. **Adapter/wrapper viết tay:** đặt bên ngoài thư mục generated để tránh sửa trực tiếp API sinh ra.
5. **Generator/runtime version:** chọn cặp version được hỗ trợ và có test đi kèm.

Có thể tồn tại các dự án cố ý commit generated source để người dùng không phải cài công cụ sinh mã. Khi đó vẫn cần một quy trình **regenerate → kiểm tra diff → commit** với version cố định, không coi file generated là nguồn sự thật duy nhất.

## 6. OpenAPI sinh ra những thành phần gì?

OpenAPI mô tả các endpoint HTTP, method, path, parameters, request/response bodies, schemas, authentication và các ràng buộc liên quan. Một generator có thể tạo:

- Java API client với method gọi HTTP.
- Model/DTO dùng Jackson/Gson hoặc serializer được cấu hình.
- Server stub/controller interfaces.
- Validation annotations, API documentation annotations.
- Exception/response wrappers.
- Build metadata hoặc test scaffolding.

Tập output phụ thuộc **generator name**, version, library template và options. Không phải generator nào cũng tạo cùng cấu trúc, cùng annotations hoặc cùng transport client.

Ví dụ một OpenAPI contract tối giản:

~~~yaml
openapi: 3.0.3
info:
  title: Orders API
  version: 1.0.0
paths:
  /orders/{id}:
    get:
      operationId: getOrderById
      parameters:
        - in: path
          name: id
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Order found
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Order'
        '404':
          description: Order not found
components:
  schemas:
    Order:
      type: object
      required: [id, totalCents]
      properties:
        id:
          type: string
        totalCents:
          type: integer
          format: int64
        createdAt:
          type: string
          format: date-time
~~~

Tùy cấu hình, Java model có thể chứa `String id`, `Long totalCents` hoặc primitive `long`, và một kiểu Java thời gian phù hợp. Không nên suy đoán chính xác kiểu sinh ra chỉ từ schema mà không xem options của generator/version đã chọn.

### 6.1. Một ví dụ sinh client

Với OpenAPI Generator CLI đã được cài và version được cố định:

~~~bash
openapi-generator-cli generate \
  -i src/main/openapi/orders.yaml \
  -g java \
  -o build/generated/openapi-client
~~~

Lệnh minh họa các tham số input, generator name và output. Trong dự án thực, cần cố định version của CLI, chọn library/serialization options phù hợp, cấu hình package names và tích hợp generated source path vào build.

Generator có thể tạo cả file build và tài liệu ngoài `.java`. Cần xác định những file nào là output phục vụ compile, những file nào chỉ là tài liệu hoặc cấu hình.

## 7. Các lựa chọn OpenAPI ảnh hưởng khả năng tương thích

Một số cấu hình hoặc thay đổi schema có thể làm Java API khác đáng kể:

| Điều chỉnh | Ảnh hưởng có thể xảy ra |
| --- | --- |
| `operationId` | Đổi tên method Java được sinh |
| Schema name | Đổi tên generated class hoặc reference |
| `required` / optional | Đổi constructor, validation và nullability |
| `nullable` / union type | Đổi cách biểu diễn null, wrapper và JSON mapping |
| `format: date-time` | Đổi kiểu thời gian và serializer phụ thuộc config |
| `type: integer`, `format: int64` | Đổi `Integer`/`Long`/primitive, overflow semantics |
| `enum` | Đổi generated enum và khả năng nhận giá trị chưa biết |
| `oneOf` / `anyOf` / `allOf` | Đổi hierarchy, wrapper hoặc discriminator logic |
| `additionalProperties` | Đổi cách xử lý trường chưa khai báo |
| HTTP library template | Đổi class của client, return type, async support, exception mapping |
| Package/module config | Đổi fully qualified class name và binary API |
| Annotation family | `javax.*` hay `jakarta.*`, Jackson/JAXB/validation imports |

Ví dụ schema v1 có:

~~~yaml
properties:
  totalCents:
    type: integer
    format: int32
~~~

V2 đổi thành `int64`. Mặc dù HTTP JSON vẫn biểu diễn một con số, client Java có thể đổi getter từ `Integer` sang `Long`, kéo theo source/binary incompatibility và các rủi ro chuyển đổi dữ liệu. Cần kiểm thử response thực tế, không chỉ nhìn diff YAML.

### 7.1. Đổi tên không giống thêm alias

Đổi `operationId: getOrderById` thành `fetchOrder` có thể làm method Java được sinh đổi tên, dù endpoint `GET /orders/{id}` không đổi. Server HTTP vẫn tương thích nhưng source code của consumer dùng Java SDK bị phá. Một contract change có thể **wire-compatible nhưng generated-source-incompatible**.

Giải pháp có thể là giữ tên operation trong schema công khai, tạo adapter ở SDK mới, hoặc phát hành major version với migration guide.

### 7.2. `required` và `nullable` là hai khái niệm khác

Một field được khai báo `required` nghĩa là phải xuất hiện theo schema tương ứng; nó không tự đồng nghĩa “không bao giờ null” trong mọi phiên bản OpenAPI và mọi kiểu biểu diễn. Trong OpenAPI 3.0, `nullable` là một cơ chế; trong OpenAPI 3.1, schema dựa theo JSON Schema có cách biểu diễn null khác, ví dụ union type.

Không copy options hoặc giả định generator diễn giải hai version specification giống nhau. Khi nâng OpenAPI document version hoặc generator, kiểm thử:

- Field vắng mặt.
- Field hiện diện với `null`.
- Field hiện diện với chuỗi rỗng, 0, false.
- Field chứa giá trị không hợp lệ.

## 8. OpenAPI: các rủi ro runtime ít thấy ở compiler

### 8.1. JSON serializer

Generated client/server có thể dùng Jackson, Gson hoặc serialization library khác. Thay generator hoặc template có thể thay:

- Tên property và naming strategy.
- Include/exclude null.
- Default values khi field không có trong payload.
- Kiểu `OffsetDateTime`, `LocalDate` hoặc class wrapper.
- Xử lý enum chưa biết.
- Policy về unknown properties.
- Serialization của polymorphic models/discriminators.

Một DTO mới compile được nhưng có thể gửi JSON khác trước. Đối với APIs công khai, nên có golden JSON fixtures và contract tests kiểm tra cả chiều đọc lẫn ghi.

### 8.2. HTTP transport

Generated Java client có thể dùng các thư viện HTTP khác nhau tùy generator template. Thay template có thể đổi:

- Sync/async method signatures.
- Kiểu exception khi HTTP status không thành công.
- Timeout, connection pooling, retry và redirect policy.
- TLS, proxy, cookie và authentication behavior.
- Cách encode path/query parameters.
- Multipart upload/download và resource closing.

Không nên coi việc thay generator là thay DTO thuần túy nếu generated code chứa cả HTTP client runtime.

### 8.3. Enum chưa biết và mở rộng server

Server có thể thêm enum value mới nhưng client Java cũ được sinh từ danh sách enum cố định. Tùy thư viện/option, client có thể fail deserialization, trả null, ánh xạ về unknown sentinel hoặc dùng cơ chế khác. Nếu service cần forward compatibility, hãy quyết định rõ hành vi với unknown values và kiểm thử bằng payload có giá trị mới.

### 8.4. Mô hình lỗi và response wrappers

Một version generator có thể trả DTO trực tiếp, một version khác sinh `ApiResponse<T>` hoặc một wrapper cho HTTP status/header. Thay đổi này có thể phá Java source dù OpenAPI response giữ nguyên. Cần so sánh public Java API của SDK trước/sau, không chỉ so swagger/openapi YAML.

## 9. OpenAPI và ranh giới `javax.*` / `jakarta.*`

Khi chuyển framework theo thế hệ Jakarta, generated source có thể cần dùng:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
~~~

thay cho những import của hệ `javax.validation.*` tương ứng. Điều tương tự có thể xảy ra ở các annotation liên quan Servlet, Persistence hoặc những framework APIs khác, tùy generator type.

Đây không phải quy tắc “đổi mọi `javax` thành `jakarta`”. Một số `javax.*` thuộc Java SE và vẫn là API tiêu chuẩn; các package Jakarta khác có version/namespace riêng. Với OpenAPI Generator, những options như `useJakartaEe` hoặc `useSpringBoot3` có thể xuất hiện ở **một số generator/version**; cần đọc options của generator cụ thể.

Một cách điều tra:

1. Xác định framework server/client sẽ chạy.
2. Xác định generated imports thật sau khi sinh.
3. Xác định dependency cung cấp những annotation/API đó.
4. Chọn generator/options và runtime libraries theo cùng hệ namespace.
5. Sinh lại sạch và chạy compile/integration tests.

Không nên chỉ thêm đồng thời mọi JAR `javax` và `jakarta` để dập lỗi compiler. Điều đó có thể tạo hai hệ annotation không được framework nhận diện đồng nhất, dẫn tới validation hoặc dependency injection không hoạt động như mong đợi.

## 10. OpenAPI Generator trong Maven và Gradle

### 10.1. Maven plugin minh họa

Ví dụ cấu trúc cấu hình, **cần thay phiên bản placeholder bằng phiên bản đã duyệt**:

~~~xml
<plugin>
  <groupId>org.openapitools</groupId>
  <artifactId>openapi-generator-maven-plugin</artifactId>
  <version>PINNED_GENERATOR_VERSION</version>
  <executions>
    <execution>
      <id>generate-orders-client</id>
      <goals>
        <goal>generate</goal>
      </goals>
      <configuration>
        <inputSpec>src/main/openapi/orders.yaml</inputSpec>
        <generatorName>java</generatorName>
        <apiPackage>com.example.orders.client.api</apiPackage>
        <modelPackage>com.example.orders.client.model</modelPackage>
        <output>target/generated-sources/orders-client</output>
      </configuration>
    </execution>
  </executions>
</plugin>
~~~

Ví dụ tập trung vào đường vào/ra và khả năng cố định version. Phần library/serialization options, source roots và runtime dependencies phải được cấu hình theo plugin/generator thực tế. Đừng đưa placeholder vào build production mà chưa thay bằng version cụ thể.

### 10.2. Gradle plugin minh họa

Một dự án có thể dùng task `openApiGenerate` của plugin tương ứng và thiết lập `inputSpec`, `generatorName`, `outputDir`, package options. Bản plugin, kiểu DSL và nhiệm vụ thêm generated sources vào `sourceSets` có thể khác giữa versions.

Nguyên tắc kỹ thuật:

~~~text
compileJava
  dependsOn generateOpenApi

generateOpenApi
  inputs:  pinned orders.yaml + templates + options + generator version
  outputs: build/generated/openapi/...

sourceSets.main.java
  includes generated Java source directory
~~~

Điều kiện quan trọng là compile task phải có **task dependency rõ**, không chỉ trỏ vào một thư mục vốn tình cờ đã có generated files từ lần build trước. Sau clean build, generator phải chạy trước compiler.

Nếu generator tạo cả `pom.xml`/Gradle build metadata riêng, cần phân biệt output nào được dùng làm SDK độc lập và output nào được compile trực tiếp trong ứng dụng.

## 11. JAXB: XML binding và lý do migration khó hơn đổi import

JAXB (*Java Architecture for XML Binding*) cung cấp cách ánh xạ giữa XML và các đối tượng Java. XJC thường được dùng để sinh Java classes từ XSD. JAXB có thể tham gia:

- SOAP/XML service integration.
- XML configuration hoặc document processing.
- Hệ thống lưu trữ/trao đổi XML lâu đời.
- Generated clients từ WSDL/XSD và schema có namespaces phức tạp.
- Các công cụ framework sinh model từ hợp đồng XML.

Trên những JDK cũ, một số thành phần JAXB từng được đi kèm JDK. Từ Java 11, các module Java EE/CORBA liên quan (trong đó có `java.xml.bind`) không còn được đóng gói sẵn theo cách cũ. Vì vậy code từng compile không khai báo JAXB dependency có thể gặp:

~~~text
package javax.xml.bind does not exist
~~~

hoặc:

~~~text
java.lang.NoClassDefFoundError: javax/xml/bind/JAXBContext
~~~

Không nên phản ứng bằng cách đổi toàn bộ XML code sang một package bất kỳ. Cần xác định đang dùng **JAXB API thế hệ nào**, công cụ XJC nào, runtime implementation nào, và framework phụ thuộc namespace nào.

## 12. Phân biệt JAXB API, runtime implementation và XJC

Ba thành phần thường bị nhầm:

1. **JAXB API:** các type như `JAXBContext`, `Marshaller`, `Unmarshaller` và annotations.
2. **JAXB runtime implementation:** provider thực thi binding/marshalling/unmarshalling khi chạy.
3. **XJC/schema compiler:** công cụ đọc XSD và sinh Java sources tại build time.

Chỉ thêm API dependency có thể giúp source compile nhưng chưa đủ để thực thi mọi thao tác JAXB. Chỉ cài XJC để generate cũng không tự cung cấp runtime phù hợp cho ứng dụng.

Ví dụ hai hệ namespace:

~~~java
// Thế hệ JAXB cũ
import javax.xml.bind.JAXBContext;
import javax.xml.bind.annotation.XmlRootElement;
~~~

~~~java
// Thế hệ Jakarta XML Binding mới tương ứng
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.bind.annotation.XmlRootElement;
~~~

Các package này khác nhau ở cấp Java type. Một class được annotate bằng `javax.xml.bind.annotation.XmlRootElement` không đương nhiên được một runtime JAXB phiên bản Jakarta nhận như annotation tương ứng.

### 12.1. Ma trận cần kiểm tra

| Thành phần | Cần ghi nhận |
| --- | --- |
| XSD/WSDL | Schema revision, XML namespace, imported schemas |
| XJC tool/plugin | Distribution, version, build JDK, binding files |
| Generated sources | Package và annotation imports |
| JAXB API | `javax.xml.bind` hoặc `jakarta.xml.bind` |
| JAXB runtime provider | Implementation và dependency version phù hợp API |
| Application/framework | Có nhận cùng JAXB namespace không |
| Runtime JDK | JDK đích, modules, classpath/module path |

Một plugin XJC có thể chạy được trên JDK mới nhưng sinh annotations cũ; một JAXB runtime mới có thể dùng namespace Jakarta trong khi framework cũ trông đợi Javax. Hai trường hợp cần hướng xử lý khác nhau.

## 13. XSD và Java classes được sinh như thế nào?

Một XSD tối giản:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           targetNamespace="urn:example:orders"
           xmlns="urn:example:orders"
           elementFormDefault="qualified">
  <xs:element name="order" type="OrderType"/>

  <xs:complexType name="OrderType">
    <xs:sequence>
      <xs:element name="id" type="xs:string"/>
      <xs:element name="totalCents" type="xs:long"/>
      <xs:element name="note"
                  type="xs:string"
                  minOccurs="0"
                  nillable="true"/>
    </xs:sequence>
  </xs:complexType>
</xs:schema>
~~~

XJC có thể tạo class chứa fields và JAXB annotations tương ứng, cộng `ObjectFactory`, `package-info.java` và những types khác tùy schema/tool options.

Ví dụ code Java chỉ để minh họa cấu trúc (không phải output cam kết của một XJC version):

~~~java
@XmlAccessorType(XmlAccessType.FIELD)
@XmlType(name = "OrderType", propOrder = {
        "id", "totalCents", "note"
})
public class OrderType {
    protected String id;
    protected long totalCents;
    protected JAXBElement<String> note;
}
~~~

Trong schema thật, việc `note` trở thành `String`, `JAXBElement<String>` hoặc representation khác phụ thuộc vào XJC version và binding customizations. Không viết logic nghiệp vụ dựa trên suy luận về một class chưa được sinh lại thực tế.

### 13.1. XML namespaces là một phần của hợp đồng

XML namespace như `urn:example:orders` thuộc format XML; nó **không phải** Java package. Một generator có thể ánh xạ namespace sang package Java bằng quy tắc mặc định hoặc binding file. Đổi package Java có thể phá source/binary clients dù namespace XML vẫn giữ nguyên.

Ngược lại, đổi XML namespace trong XSD có thể làm dữ liệu XML cũ không được unmarshal đúng dù tên Java class không đổi. Cần quản lý hai lớp compatibility riêng.

### 13.2. `minOccurs`, `nillable` và biểu diễn null

XML cho phép phân biệt một phần tử **không xuất hiện** với phần tử xuất hiện có `xsi:nil="true"` khi schema cho phép. Generated model/runtime có thể dùng wrapper để giữ thông tin trạng thái này.

Ví dụ:

~~~xml
<order xmlns="urn:example:orders"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <id>O-10</id>
  <totalCents>1200</totalCents>
  <note xsi:nil="true"/>
</order>
~~~

không nhất thiết tương đương XML không có phần tử `note`. Một thay đổi XJC/generator có thể làm mất khác biệt đó nếu kiểu Java được chọn khác trước.

## 14. JAXB: version XJC, runtime và binding customizations

### 14.1. XJC không nên được coi là một lệnh JDK luôn có sẵn

Ở các JDK hiện đại, không nên giả định `xjc` được đóng gói như một command có sẵn trong mọi JDK distribution. Đội phát triển thường dùng Maven/Gradle plugin hoặc distribution XJC độc lập.

Một lệnh mang tính minh họa khi XJC đã được cài đúng phiên bản:

~~~bash
xjc -d target/generated-sources/xjc \
    src/main/resources/schema/orders.xsd
~~~

Trong CI, cần cố định plugin/tool version, input schemas và output directory; đừng phụ thuộc vào một `xjc` ngẫu nhiên đang có trong `PATH`.

### 14.2. External binding files

Các tệp `.xjb` có thể điều chỉnh package, class names hoặc mapping schema → Java. Khi nâng JAXB/XJC qua các thế hệ, cú pháp, namespace và phiên bản của binding language có thể thay đổi.

Khâu kiểm kê nên ghi:

- Những file `.xjb` đang áp dụng.
- Schema location mà customization tham chiếu.
- Package/class naming rules.
- Các XJC extensions/vendor plugins.
- Runtime namespace (`javax` hay `jakarta`) mà generated code sẽ sử dụng.

Không tự động đổi namespace trong mọi binding file rồi kết luận migration hoàn thành. Cần xem syntax của đúng XJC version và sinh lại mã để xác nhận binding thực sự được áp dụng.

### 14.3. JAXB API và runtime dependency

Nếu chọn hệ Jakarta XML Binding, cần có API dependency và implementation phù hợp với BOM/support policy:

~~~xml
<!-- Versions are managed by the approved BOM/dependencyManagement. -->
<dependencies>
  <dependency>
    <groupId>jakarta.xml.bind</groupId>
    <artifactId>jakarta.xml.bind-api</artifactId>
  </dependency>
  <dependency>
    <groupId>org.glassfish.jaxb</groupId>
    <artifactId>jaxb-runtime</artifactId>
  </dependency>
</dependencies>
~~~

Ví dụ giả định dự án có BOM hoặc `dependencyManagement` quản lý phiên bản; nếu không, phải khai báo version được duyệt. Chọn cặp API/runtime không phù hợp nhau có thể gây lỗi class loading hoặc provider discovery.

Nếu hệ thống vẫn cần JAXB API `javax.xml.bind` do framework cũ, không thể thay trực tiếp bằng các artifact Jakarta mới mà không chuyển framework/consumer tương ứng.

## 15. JAXB: những thay đổi serialized XML cần kiểm thử

Một build thành công không đủ để kết luận XML compatibility. Cần kiểm tra:

| Thay đổi | Rủi ro |
| --- | --- |
| `@XmlElement` name/namespace | XML producer/consumer không còn khớp |
| `@XmlType(propOrder)` | Thứ tự phần tử XML khác schema |
| `minOccurs`, `maxOccurs` | Optional/repeated fields đổi Java API |
| `nillable` | Mất phân biệt missing với nil |
| Kiểu XSD `int` ↔ `long` | Java field/getter và miền giá trị thay đổi |
| `xs:dateTime` mapping | Timezone và kiểu thời gian đổi |
| XML attributes ↔ elements | Format dữ liệu thay đổi |
| Enumeration restriction | Giá trị XML mới chưa có trong generated enum cũ |
| Namespace/package binding | XML hoặc Java ABI có thể bị ảnh hưởng |
| Custom adapters | Cách parse/format giá trị có thể đổi |

Ví dụ một schema đổi `totalCents` từ `xs:int` sang `xs:long`. XML chứa số vẫn có thể đọc được trong một số trường hợp, nhưng Java getter/setter có thể đổi từ `int` sang `long`, phá source/binary clients đang dùng generated class.

### 15.1. Validation không tự xảy ra theo mọi đường unmarshalling

Cần xác định hệ thống có cấu hình XML Schema validation cho `Unmarshaller`/`Marshaller` hay không. Việc code có JAXB annotations không bảo đảm mọi input được kiểm tra đầy đủ theo XSD tại runtime.

Khi tăng độ chặt của validation, một XML trước đây được chấp nhận có thể bị từ chối. Đây là thay đổi behavior cần contract tests và release note.

### 15.2. Bảo mật xử lý XML

Không dùng XML schema/compiler/runtime cũ với các cấu hình mở mặc định mà không xét nguồn dữ liệu và XML parser security. Các rủi ro như external entity resolution, tải schema ngoài ý muốn hoặc resource exhaustion cần được đánh giá theo parser/validator cụ thể.

Khi nâng JAXB hoặc framework, kiểm tra chính sách XML parser, external schema access và cách xử lý tài liệu không tin cậy. Không chỉ sửa import cho compiler pass.

## 16. Protocol Buffers: schema và code generation

Protocol Buffers dùng schema `.proto` để mô tả message, field numbers, types và cấu trúc dữ liệu. `protoc` cùng Java code generator sinh ra classes hỗ trợ builder, parser, serialization và các phương thức truy cập field.

Ví dụ schema proto3:

~~~proto
syntax = "proto3";

package lesson.orders.v1;

option java_package = "com.example.orders.v1";
option java_multiple_files = true;

message Order {
  string id = 1;
  int64 total_cents = 2;
  repeated string tags = 3;
  optional string note = 4;
  reserved 5, 6;
  reserved "legacy_status";
}
~~~

Các con số `1`, `2`, `3`, `4` là **field numbers trong wire format**, không chỉ là thứ tự khai báo trong file. Chúng là phần quan trọng của hợp đồng binary protocol.

Lệnh minh họa:

~~~bash
protoc \
  --proto_path=src/main/proto \
  --java_out=build/generated/source/proto/main/java \
  src/main/proto/orders.proto
~~~

Lệnh giả định `protoc` đã được cài đúng version và input có tên `orders.proto`. Trong dự án thật, nên quản lý binary/tool version qua plugin, wrapper hoặc môi trường build có thể tái lập.

### 16.1. Generated Java API

Với options ở trên, mã sử dụng có thể có dạng:

~~~java
Order order = Order.newBuilder()
        .setId("O-100")
        .setTotalCents(2500L)
        .addTags("priority")
        .setNote("Express")
        .build();

byte[] payload = order.toByteArray();
Order decoded = Order.parseFrom(payload);

System.out.println(decoded.getId());
System.out.println(decoded.getTotalCents());
System.out.println(decoded.hasNote());
~~~

Với `optional string note` được hỗ trợ theo proto3 field presence, generated API có thể cung cấp `hasNote()`. Nếu bỏ `optional` hoặc đổi schema syntax/semantics, code client dựa vào presence có thể bị ảnh hưởng dù payload vẫn là protobuf.

## 17. `protoc`, generated Java code và protobuf runtime là ba thành phần khác nhau

Nên ghi riêng:

- **`protoc` compiler:** executable đọc `.proto` và điều phối plugins.
- **Java code generator:** phần phát ra `.java`, có thể gắn với bản `protoc`/plugin.
- **`protobuf-java` runtime:** thư viện Java được generated classes dùng tại compile/runtime.

Với những cấu hình khác, dự án có thể chọn protobuf runtime dạng lite hoặc plugin gRPC có version riêng. Không mặc định một class được sinh với tool mới nhất sẽ tương thích với mọi runtime Java protobuf cũ.

### 17.1. Quy tắc lựa chọn version

Ưu tiên dùng tổ hợp generator/runtime được dự án protobuf và framework tích hợp công bố hỗ trợ. Đọc release notes khi thay major version. Không chọn `protoc` một phiên bản, `protobuf-java` một phiên bản khác và gRPC plugin một phiên bản thứ ba tùy ý chỉ vì mỗi công cụ chạy được riêng.

Một lỗi có thể xuất hiện khi generated source gọi method không tồn tại trong protobuf runtime đang được resolve. Khi đó source compilation có thể thất bại; nếu class đã được compile với runtime khác rồi triển khai với JAR cũ, có thể gặp `NoSuchMethodError`.

### 17.2. Kiểm kê output và package

Các options như `java_package`, `java_multiple_files` và `java_outer_classname` ảnh hưởng Java class names và file layout. Chúng có thể thay đổi API của consumer Java **mà không đổi số field hoặc wire schema**.

Ví dụ chuyển từ nested message class trong outer class sang top-level classes bằng `java_multiple_files = true` có thể buộc code client thay imports và class references. Đừng đánh đồng protobuf wire compatibility với Java source/binary compatibility.

## 18. Protobuf: quy tắc field numbers và schema evolution

### 18.1. Không tái sử dụng field number

Giả sử v1:

~~~proto
message Customer {
  string id = 1;
  string email = 2;
}
~~~

V2 không còn dùng `email`. Không nên gán field `2` cho một ý nghĩa mới:

~~~proto
// Rủi ro: tái sử dụng tag 2 với ý nghĩa khác.
message Customer {
  string id = 1;
  string phone_number = 2;
}
~~~

Một consumer cũ có thể đọc dữ liệu `phone_number` như `email` vì cùng field number và wire type. Không có exception nhưng semantics bị sai.

Hướng an toàn hơn là reserve tag/name cũ:

~~~proto
message Customer {
  string id = 1;
  reserved 2;
  reserved "email";
  string phone_number = 3;
}
~~~

`reserved` giúp compiler schema phát hiện một số trường hợp vô tình tái sử dụng tag hoặc tên. Nó không tự di chuyển dữ liệu lịch sử sang field mới.

### 18.2. Thêm field thường dễ tương thích hơn xóa/đổi ý nghĩa

Một message v2 có thể bổ sung field number mới:

~~~proto
message Customer {
  string id = 1;
  string email = 2;
  string display_name = 3;
}
~~~

Reader cũ không biết `display_name` có thể xử lý như unknown field theo cơ chế protobuf. Reader mới đọc message v1 sẽ không thấy field mới, nên phải dùng quy tắc default/presence phù hợp.

Tuy nhiên, “thêm field” không có nghĩa business logic tự an toàn: nếu server bắt đầu yêu cầu `display_name` luôn có mặt, client v1 không thể tự cung cấp thông tin mới. Cần phân biệt wire-level compatibility với **semantic compatibility**.

### 18.3. Đổi type không phải phép refactor vô hại

Một số protobuf field types có cùng wire type, nhưng việc đổi giữa chúng vẫn có thể tạo sai miền giá trị, cách giải mã và semantics. Ví dụ `int32` → `int64` không nên được coi là hoàn toàn an toàn chỉ vì cả hai dùng varint; dữ liệu ngoài miền int32 có thể không được reader cũ hiểu đúng.

Khi muốn đổi type lớn, tên/ý nghĩa field hoặc dạng repeated/singular, cách ít rủi ro thường là **thêm field mới với tag mới, hỗ trợ đọc cũ và mới trong giai đoạn chuyển tiếp**, sau đó reserve field cũ khi ngừng dùng.

### 18.4. Protobuf field name và Java getter

Trong protobuf binary wire, field number quan trọng hơn spelling của field name. Nhưng tên field ảnh hưởng generated getter và JSON mapping. Đổi `total_cents` thành `amount_cents` trong `.proto` mà giữ tag có thể vẫn tương thích ở một mức binary wire, nhưng `getTotalCents()` biến thành `getAmountCents()`, phá source/binary clients Java.

Với protobuf JSON mapping, tên field còn liên quan tới property names. Vì vậy một thay đổi “chỉ rename” cần kiểm thử cả Java API và JSON nếu hệ thống dùng hai dạng encoding.

## 19. Proto3 presence, defaults, `oneof` và enum evolution

### 19.1. Giá trị mặc định không nhất thiết có nghĩa “đã được gửi”

Với nhiều scalar fields trong proto3 không có explicit presence, getter trả default (ví dụ `0`, `false`, chuỗi rỗng) khi field vắng mặt. Không được suy ra rằng:

~~~java
order.getTotalCents() == 0L
~~~

nghĩa là producer cố tình gửi tổng tiền bằng 0. Nếu cần phân biệt vắng mặt với giá trị 0, cần thiết kế field presence đúng từ schema, chẳng hạn dùng `optional` khi phù hợp hoặc một mô hình message khác.

Khi nâng generator hoặc thay schema, phải kiểm tra consumer có dùng `hasX()`, `getX()` hoặc `getXCount()` với giả định cụ thể không.

### 19.2. `oneof`

`oneof` diễn tả nhóm field trong đó một lựa chọn có mặt tại một thời điểm. Generated code thường có API kiểm tra case của lựa chọn. Nếu đổi field vào/ra khỏi `oneof`, hoặc đổi tag/ý nghĩa, có thể gây tác động đến default và presence semantics.

Ví dụ:

~~~proto
message PaymentMethod {
  oneof method {
    string card_token = 1;
    string bank_account = 2;
  }
}
~~~

Consumer cần xử lý cả trường hợp không có lựa chọn và các trạng thái chưa biết. Không giả định thêm một option mới vào `oneof` luôn được các consumer cũ xử lý an toàn về nghiệp vụ.

### 19.3. Enum

Enum proto3 nên định nghĩa một giá trị số 0 làm mặc định, với tên phù hợp như `UNSPECIFIED`:

~~~proto
enum OrderState {
  ORDER_STATE_UNSPECIFIED = 0;
  ORDER_STATE_CREATED = 1;
  ORDER_STATE_PAID = 2;
}
~~~

Khi thêm enum values, code Java đã sinh từ schema cũ có thể gặp unrecognized values với cách biểu diễn tùy runtime/API. Consumer không nên giả định rằng mọi enum number sẽ trùng một hằng số đã biết. Cần kiểm thử đường parse và fallback, nhất là khi message có thể được phát từ server mới.

Đổi ý nghĩa của enum number cũ là một phá vỡ semantic contract dù wire bytes hợp lệ.

## 20. Tương thích protobuf wire khác tương thích Java classes

Đây là một phân biệt quan trọng:

| Thay đổi | Protobuf wire | Java generated API | Business behavior |
| --- | --- | --- | --- |
| Thêm field với tag mới | Thường có thể đọc chéo, tùy cách dùng | Có getter/builder mới | Cần default/presence logic |
| Đổi `java_package` | Binary message format có thể không đổi | Fully qualified class đổi | Consumer phải cập nhật imports/dependency |
| Đổi `java_multiple_files` | Wire format không đổi | Class layout/names đổi | Cần migration client Java |
| Rename field, giữ tag và type | Binary wire có thể không đổi | Getter/setter names đổi | JSON mapping/semantics cần xét |
| Tái sử dụng tag cũ | Rất nguy hiểm | Có thể vẫn compile | Dữ liệu có thể bị hiểu sai |
| Đổi field type | Tùy types, nhiều rủi ro | Getter và builder signatures đổi | Overflow/precision/meaning |
| Thêm enum number | Wire format có thể chứa số mới | Consumer cũ có thể không nhận enum mới | Cần fallback/unknown handling |
| Đổi RPC service/method name | Message schema có thể không đổi | Stub/API và service routing đổi | RPC contract có thể bị phá |

Ngay cả khi protobuf binary decoder đọc được message cũ, Java module có thể không compile nếu generated classes đổi tên. Ngược lại, code Java có thể compile và parse bytes nhưng hiểu sai một tag đã bị tái sử dụng.

Không đánh giá migration chỉ dựa trên một chiều “`protoc` chạy thành công”.

## 21. Mã sinh trong hệ gRPC và các plugin bổ sung

Một dự án dùng protobuf qua gRPC thường có thêm `service` definitions:

~~~proto
service OrderService {
  rpc GetOrder (GetOrderRequest) returns (Order);
}

message GetOrderRequest {
  string id = 1;
}
~~~

Khi đó pipeline có thể gồm:

~~~text
*.proto
 ├─ protoc Java message generator
 │     └─ protobuf-java runtime
 └─ protoc gRPC Java plugin
       └─ grpc-java runtime/stubs
~~~

`protoc-gen-grpc-java` và gRPC Java runtime là thành phần riêng cần kiểm tra version/support. Không nên nghĩ nâng `protobuf-java` là tự động nâng toàn bộ gRPC stack.

Các breaking changes có thể liên quan:

- Tên service hoặc method.
- Kiểu request/response.
- Streaming mode (unary/server-streaming/client-streaming/bidirectional).
- Error/status mapping.
- Deadline, cancellation, retry và authentication.
- Version gRPC stubs/runtime và transport provider.

Thay JDK có thể làm lỗi xuất hiện ở Netty/TLS/native transport hoặc executor, dù `.proto` và generated message vẫn hợp lệ.

## 22. Kiểm soát Java source target của generated code

Không phải mọi generator cung cấp một tùy chọn tên “target Java version”, và cùng một tùy chọn có thể có nghĩa khác giữa các generator. Cần kiểm tra:

- Java syntax mà template phát ra: records, var, switch expressions, pattern matching, sealed types...
- APIs JDK được gọi trong output: `java.time`, `java.net.http.HttpClient`, `List.of`, `Stream.toList`...
- Annotations, JSR APIs hoặc framework types được import.
- Mức bytecode được compiler tạo.
- Minimum runtime Java được sản phẩm cam kết.

Ví dụ build chạy JDK 21 nhưng library phải hỗ trợ Java 17:

~~~text
Generator JVM:    JDK 21
Compiler JDK:     JDK 21
--release:        17
Production floor: JDK 17
~~~

Khi đó generated source không được dùng API chỉ xuất hiện sau Java 17. Compiler với `--release 17` có thể phát hiện nhiều trường hợp dùng API không thuộc Java 17, nhưng vẫn cần kiểm tra dependencies và runtime behavior.

### 22.1. Vì sao `sourceCompatibility` không tương đương `--release`?

Chọn source language level chỉ kiểm soát một phần cú pháp/bytecode. `javac --release N` còn ràng buộc sử dụng Java platform APIs theo release tương ứng. Nếu mục tiêu là duy trì tương thích với runtime cũ, ưu tiên cơ chế release target phù hợp thay vì chỉ dựa vào source flag.

Tuy nhiên, `--release` không tự phát hiện mọi thư viện bên thứ ba có bytecode yêu cầu runtime cao hơn. Cần kiểm tra cả dependency JAR và chạy test trên Java thấp nhất mà sản phẩm cam kết.

## 23. Generated code và module system

Với Java Module System (JPMS), code được sinh có thể yêu cầu modules cho runtime libraries hoặc dùng reflection. Những vấn đề có thể gặp:

- Generated JAXB models cần runtime truy cập fields/constructors bằng reflection.
- Model packages trong named module có thể phải `opens` tới module thực hiện binding/serialization.
- Dependency được đặt ở classpath hay module path ảnh hưởng class loading.
- Tên automatic module và service provider discovery có thể khác sau nâng dependency.

Ví dụ một cấu hình module có tính minh họa:

~~~java
module com.example.orders {
    requires java.xml;
    requires jakarta.xml.bind;

    opens com.example.orders.generated
            to jakarta.xml.bind;
}
~~~

Tên module cụ thể phụ thuộc các artifact được chọn, và một số implementation có module name khác. Đoạn này không thay việc kiểm tra descriptors của những JAR thực tế.

Không nên mở mọi package cho `ALL-UNNAMED` như một giải pháp mặc định nếu chỉ có một package generated cần reflection access. Đồng thời, không tự thay thuộc tính module của thư viện chỉ vì một dependency mới xuất hiện; cần hiểu classpath/module path đang được triển khai.

## 24. Tạo build có thể tái lập và không lệ thuộc cache cũ

Một pipeline tốt nên thỏa:

1. Input contract nằm trong version control hoặc được trỏ tới revision immutable.
2. Generator/plugin/tool versions được cố định.
3. Templates/customizations được version hóa.
4. Generated output nằm ở thư mục được build quản lý.
5. Compile task phụ thuộc generation task đúng cách.
6. Runtime libraries được quản lý nhất quán với generated source.
7. Clean build có thể sinh lại code từ đầu.
8. Generated output được review khi có thay đổi schema/tool/config.

### 24.1. Tránh việc build dùng output từ lần trước

Ví dụ cấu trúc:

~~~text
src/main/openapi/orders.yaml
src/main/proto/orders.proto
src/main/resources/xsd/orders.xsd
build/generated/openapi/
build/generated/proto/
build/generated/xjc/
~~~

Nếu `compileJava` chỉ thêm thư mục `build/generated` vào source roots mà không có task dependency với các generator, build local có thể pass do file cũ còn tồn tại. Nhưng CI clean build sẽ fail, hoặc tệ hơn, compile với version generated code không khớp schema hiện tại.

Trong Gradle, nên liên kết source directory với output của task tương ứng theo API build được hỗ trợ; trong Maven, bind generator goals vào phase phù hợp và xác nhận output source roots được đăng ký.

### 24.2. Deterministic generation

Đầu ra có thể khác giữa hai lần sinh do:

- Generator/templates version khác.
- Schema tải từ URL không cố định.
- Timestamps, absolute paths, banners hoặc metadata trong generated files.
- Sort order của model/operation/property.
- Locale/charset và line endings.
- Plugin extensions và code formatting versions.

Nên cấu hình deterministic output khi công cụ hỗ trợ. Nếu output có timestamp, cần biết cách tắt hoặc bỏ metadata đó trong so sánh, thay vì coi mọi diff là thay đổi API thật.

Một phép kiểm tra thường hữu ích ở CI: **generate từ sạch và xác nhận output không tạo diff ngoài dự kiến**. Nếu project commit generated code, điều này giúp phát hiện source/schema đã cập nhật nhưng code sinh chưa được regenerate.

## 25. Commit generated source hay generate mỗi lần build?

Không có một lựa chọn đúng tuyệt đối:

| Cách làm | Ưu điểm | Rủi ro/cần kiểm soát |
| --- | --- | --- |
| Commit generated code | Consumer có thể build khi không cài generator; review diff thuận tiện | Dễ stale nếu schema đổi mà quên regenerate; diff lớn |
| Generate trong build | Source of truth rõ; giảm file generated trong repo | Build phải có tool/plugin, nguồn schema immutable, cấu hình reproducible |
| Phát hành generated SDK như artifact riêng | Consumer dùng dependency version ổn định | Phải đồng bộ SDK/schema/server, quản lý release riêng |

Quyết định nên dựa vào cách tổ chức repository, yêu cầu offline build, số consumer và policy phát hành SDK. Dù chọn cách nào, phải chỉ rõ:

- Ai có quyền thay schema.
- Ai có trách nhiệm regenerate/release.
- Cách khóa version generator.
- Cách phát hiện output stale.
- Cách review breaking changes.

Không để một module âm thầm sinh code từ spec mới trong khi module khác vẫn dùng JAR client cũ mà không có compatibility contract.

## 26. Test migration theo bốn góc nhìn

### 26.1. Generated source compilation

Xác nhận output mới compile với compiler/toolchain dự kiến:

- Không còn import tới API vắng mặt.
- Không có class name trùng hoặc keyword conflict.
- API annotations và generated models hợp lệ.
- Java release target và dependencies phù hợp.

Đây là bước đầu, chưa phải bằng chứng rằng HTTP/XML/protobuf contract còn đúng.

### 26.2. Contract tests từ dữ liệu thật

**OpenAPI:** kiểm tra request/response JSON, status codes, query/path encoding, auth headers, missing/null, enum mới, pagination, exception mapping.

**JAXB:** dùng XML fixtures từ schema/version cũ và mới; kiểm tra namespace, optional/nil, element order, validation, date/time và unmarshalling → marshalling.

**Protocol Buffers:** dùng binary fixtures tạo từ generated writer v1 và reader v2; kiểm tra field numbers, unknown fields, presence, enum, repeated/oneof và semantics dữ liệu.

Đừng dùng generator v2 để tạo fixture có nhãn v1. Test compatibility cần **bytes/JSON/XML thực sự được tạo từ version cũ** hoặc một fixture được xác nhận đại diện.

### 26.3. Java consumer compatibility

Nếu generated SDK là public artifact, tạo một consumer được biên dịch với SDK cũ rồi chạy hoặc compile theo ma trận cần hỗ trợ. Những thay đổi như package, return type hoặc method names có thể phá source/binary compatibility trong khi contract HTTP/XML/proto vẫn hoàn toàn tương thích.

Nên so sánh public Java API của generated JAR v1/v2 bằng công cụ API diff phù hợp khi thư viện được phát hành cho downstream consumers.

### 26.4. Runtime integration

Chạy test trên runtime image thực tế:

- HTTP client với server thực, TLS/proxy/auth.
- JAXB implementation/provider được load đúng.
- Protobuf/gRPC runtime/stubs và transport.
- Native libraries và Java agents liên quan.
- JDK module access và serialization behavior.

Một test chỉ so generated source file không thể phát hiện lỗi runtime như `NoClassDefFoundError` hoặc provider mismatch.

## 27. Ma trận tương thích qua các phiên bản

| Contract/writer | Generated code/reader | Runtime | Câu hỏi |
| --- | --- | --- | --- |
| Schema v1 | Generator v1 | JDK cũ | Baseline chạy đúng không? |
| Schema v1 | Generator v2 | JDK đích | Chỉ đổi generator/JDK có đổi Java API hoặc behavior không? |
| Schema v2 | Generator v2 | JDK đích | Trạng thái mục tiêu chạy đúng không? |
| Payload v1 | Reader generated v2 | JDK đích | Dữ liệu cũ có đọc được không? |
| Payload v2 | Reader generated v1 | JDK cũ/đích, nếu phải hỗ trợ | Rolling deployment/rollback có an toàn không? |
| SDK Java v1 | Server/API v2 | Runtime thực tế | Client cũ có tiếp tục gọi được không? |

Không phải mọi tổ hợp bắt buộc được hỗ trợ; ma trận phải xuất phát từ hợp đồng sản phẩm. Nếu ứng dụng không cho phép rollback về runtime cũ, vẫn phải ghi rõ điều đó thay vì mặc định có thể quay lại chỉ bằng cách đổi Docker image.

Đối với hệ gRPC/Protobuf, cần thêm test **wire compatibility**. Đối với OpenAPI, cần kiểm tra cả **HTTP behavior** và **generated Java SDK compatibility**. Đối với JAXB, cần test schema XML và provider/runtime compatibility.

## 28. Xử lý schema evolution có kiểm soát

### 28.1. OpenAPI

Một thay đổi dễ tương thích hơn có thể là thêm một response property tùy chọn, với điều kiện client cũ chấp nhận unknown properties và semantics không đòi field mới. Thay endpoint path, xóa required property hoặc đổi authentication thường có tác động lớn hơn.

Khi breaking change là cần thiết, cân nhắc endpoint/version mới, adapter hoặc một giai đoạn hỗ trợ song song. Không kỳ vọng đổi generated client SDK tự làm server cũ hiểu schema mới.

### 28.2. JAXB/XSD

Thêm optional element có thể tương thích với một số reader, nhưng XML Schema validation hoặc thứ tự `xs:sequence` có thể làm dữ liệu mới bị reader cũ từ chối. XML namespaces, nillability và adapter behavior phải được kiểm thử thực tế. Một schema “hợp lệ” không đồng nghĩa một Java JAXB class cũ nhận được nó.

### 28.3. Protobuf

Giữ field numbers ổn định, không tái sử dụng tag, reserve field đã loại bỏ khi phù hợp và bổ sung field mới với số mới. Với thay đổi semantics không tương thích, dùng message/service version mới hoặc giai đoạn reader hiểu đồng thời format cũ/mới. Kiểm tra riêng binary và JSON encoding nếu cả hai được dùng.

## 29. Rollout giữa nhiều service: expand → migrate → contract

Một chiến lược tổng quát:

**Expand:** trước tiên cập nhật readers/servers để nhận cả payload cũ và mới, hoặc phát hành API version mới mà chưa xóa version cũ.

**Migrate:** nâng từng client, regenerate SDK và triển khai theo nhóm; theo dõi lỗi decode, validation, HTTP status, gRPC status và latency.

**Contract:** chỉ loại schema field, endpoint, Java adapter hoặc dependency legacy sau khi xác nhận không còn consumer cần chúng.

Ví dụ khi đổi từ một field JSON `amount` sang `amountCents`:

1. Server tạm hỗ trợ cả hai cách biểu diễn theo quy tắc rõ.
2. Cập nhật OpenAPI contract và sinh SDK mới.
3. Triển khai các client mới theo đợt.
4. Quan sát traffic còn sử dụng field cũ.
5. Chỉ bỏ field cũ khi chính sách hỗ trợ cho phép.

Với protobuf, không tái sử dụng field number cũ sau khi contract; với JAXB, schema namespaces và compatibility XML cần được quản lý riêng. Mô hình expand/contract là định hướng, không thay những quy tắc đặc thù của từng format.

## 30. Lỗi thường gặp trong thực tế

| Triệu chứng | Nguyên nhân thường gặp | Hướng điều tra |
| --- | --- | --- |
| `package javax.xml.bind does not exist` | JAXB không còn bundled trong JDK; chọn dependency sai thế hệ | JAXB API/runtime/XJC stack và JDK |
| `ClassNotFoundException: jakarta.xml.bind...` | Generated source/runtime lệch dependency | Resolved runtime graph, provider |
| `NoSuchMethodError` trong protobuf runtime | Generated classes và protobuf runtime không phù hợp | `protoc`/plugin/runtime versions |
| Compile lỗi getter của DTO | Schema/options đổi generated method | Generated API diff, schema revision |
| Unknown enum gây decode failure | Server/payload có enum mới | Serializer/runtime và fallback policy |
| JSON null/missing xử lý khác | Generator hoặc serialization options thay | Golden fixtures, nullable/required |
| XML validation fail sau regenerate | Namespace, element order hoặc XSD thay | Schema diff và XML fixtures |
| CI clean build fail nhưng local pass | Generated source cũ còn trong build dir, thiếu task dependency | Clean generation graph |
| Build pass nhưng production không start | Agent/native/JAXB provider hoặc JDK module khác | Runtime image và deployment classpath |
| gRPC stub compile lỗi | Version plugin gRPC/protobuf runtime hoặc schema API đổi | Compiler/plugin/runtime matrix |
| Chênh lệch hàng nghìn dòng generated | Generator/templates version thay hoặc output không deterministic | Pin tool, review diff theo nhóm |

Không nên sửa generated Java file để che một lỗi thuộc schema/compiler plugin/runtime dependency. Cần tìm đúng tầng và giữ bằng chứng.

## 31. Một ví dụ migration tổng hợp

Giả sử hệ thống đặt hàng đang dùng JDK 17, dự kiến chuyển JDK 21. Nó có:

~~~text
orders-service
  src/main/openapi/orders.yaml      -> Java HTTP SDK/server API
  src/main/resources/xsd/order.xsd  -> JAXB order document binding
  src/main/proto/order.proto        -> Order events và gRPC messages
  Gradle plugins + codegen tasks
  runtime: framework, Jackson, JAXB, protobuf-java, gRPC
~~~

### 31.1. Trước migration

Nhóm ghi baseline:

- Source contract revision của cả ba schema.
- Generator/plugin/`protoc`/XJC versions.
- Generated Java packages, imports và API signatures.
- JDK chạy build, JDK compiler và Java release target.
- Resolved runtime dependencies.
- JSON/XML/protobuf fixtures từ bản đã phát hành.
- Consumers nào dùng SDK và messages.

### 31.2. Phát hiện blocker

Trong ví dụ giả định:

- OpenAPI server generator cũ sinh `javax.validation`, framework mục tiêu dùng Jakarta Validation.
- JAXB code cũ import `javax.xml.bind` nhưng nhóm đang chuyển sang Jakarta XML Binding.
- Protobuf Java code vẫn compile, song `protoc` và runtime chưa được quản lý version thống nhất.
- Một Gradle task compile file đã sinh từ trước mà không khai báo phụ thuộc task generate.

Không nên giải quyết bằng cách sửa trực tiếp hàng trăm file generated hoặc thêm tất cả legacy libraries vào classpath.

### 31.3. Kế hoạch kỹ thuật

1. Chốt mức Java tối thiểu và chọn tổ hợp framework/generator/runtime được hỗ trợ.
2. Pin schema revisions, tools và templates.
3. Chọn OpenAPI generator/options đúng hệ Jakarta/HTTP transport, regenerate sạch.
4. Chọn XJC/JAXB API/runtime nhất quán, cập nhật bindings nếu cần và regenerate sạch.
5. Chọn `protoc`, protobuf runtime và gRPC plugin theo compatibility policy.
6. Sửa build graph để generation chạy trước compile, không phụ thuộc output cũ.
7. Chạy Java API diff và JSON/XML/protobuf fixture tests.
8. Chạy smoke/integration tests trên JDK 21 cùng container runtime/agents.
9. Triển khai reader/server tương thích trước, rồi cập nhật SDK consumers.

### 31.4. Tiêu chí hoàn thành

Không chỉ là “đã compile được”. Cần chứng minh:

- Clean build trên JDK/CI mục tiêu tái sinh mã thành công.
- Không còn generated source phụ thuộc API thiếu ngoài ý muốn.
- Generated runtime libraries khớp công cụ và framework.
- Client Java được hỗ trợ vẫn compile/liên kết theo chính sách đã công bố.
- JSON/XML/protobuf dữ liệu cũ có thể được đọc bởi phiên bản mới nếu sản phẩm yêu cầu.
- HTTP/gRPC behavior và authorization không đổi ngoài phạm vi cho phép.
- Runtime image production có đúng dependencies, modules và agents.
- Có kế hoạch rollback hoặc roll-forward rõ nếu payload mới không được reader cũ hỗ trợ.

## 32. Checklist trước khi phê duyệt thay đổi

- [ ] Đã xác định đầy đủ contract sources: OpenAPI, XSD/WSDL, `.proto`.
- [ ] Đã phân biệt schema revision với generator/tool/plugin version.
- [ ] Đã ghi JDK chạy generator, compiler JDK, `--release` và runtime Java tối thiểu.
- [ ] Generator/plugin/XJC/`protoc` versions được cố định.
- [ ] Custom templates/bindings được kiểm kê và version hóa.
- [ ] Output path và generated source registration được cấu hình rõ.
- [ ] Compile task có dependency đúng với generation task.
- [ ] Clean build không sử dụng generated files cũ.
- [ ] Đã review generated Java API diff, package/class/getter changes.
- [ ] OpenAPI generator options phù hợp HTTP library, Jackson và framework mục tiêu.
- [ ] Đã kiểm tra `javax`/`jakarta` imports, tránh kết hợp hai hệ không nhất quán.
- [ ] JAXB API, runtime implementation và XJC tool được kiểm tra riêng.
- [ ] XSD XML namespaces, optional/nillable, order và adapters có tests.
- [ ] `protoc`/protobuf runtime/gRPC plugin có compatibility policy thống nhất.
- [ ] Không tái sử dụng protobuf field numbers; field bỏ được reserve khi phù hợp.
- [ ] Proto presence, unknown fields và enum evolution có tests.
- [ ] Đã kiểm tra cả wire compatibility lẫn Java generated API compatibility.
- [ ] Có golden JSON/XML/binary fixtures từ phiên bản đã phát hành.
- [ ] Đã kiểm tra runtime image, modules, agents và native components nếu liên quan.
- [ ] Đã rà soát security của HTTP client, XML parsing và dependency/tool supply chain.
- [ ] Có consumer inventory, version support policy và rollout/rollback plan.
- [ ] Release notes phân biệt thay đổi schema, generator và Java runtime.

## 33. Tài liệu chính thức nên đối chiếu

Do generator options và compatibility policy thay đổi theo phiên bản, khi thực hiện migration cần đọc tài liệu đúng release:

- **OpenAPI Specification:** semantics của operations, schemas, required/nullable, responses và version 3.0/3.1.
- **OpenAPI Generator Documentation:** CLI/Maven/Gradle integration, generator-specific options, supported libraries và migration guides.
- **Jakarta XML Binding Specification và JAXB/XJC documentation:** API/runtime, binding files, mapping XSD ↔ Java và serialization semantics.
- **JDK migration guides:** các module từng được JDK đóng gói, Java Module System và `--release`.
- **Protocol Buffers Language Guide:** field numbers, reserved tags, presence, oneof, enums và compatibility.
- **Protocol Buffers Java Generated Code Guide:** Java package, generated getters/builders, runtime compatibility.
- **gRPC Java documentation:** generated stubs, transport/runtime versions, deadlines và status semantics.
- **Maven/Gradle documentation:** lifecycle, source roots, task dependencies và reproducible builds.

Không lấy một đoạn cấu hình từ phiên bản plugin cũ rồi áp vào bản mới mà không kiểm tra options và runtime constraints. Với những công cụ sinh mã, **version của công cụ là một phần của nguồn gốc generated artifact**.

## 34. Kết luận

Mã Java sinh từ OpenAPI, JAXB hoặc Protocol Buffers nằm giữa **hợp đồng dữ liệu**, **công cụ sinh mã**, **compiler** và **runtime libraries**. Nâng JDK có thể làm hỏng bất kỳ tầng nào; trong khi một thay đổi schema hoặc generator còn có thể phá Java source/binary API dù HTTP/XML/protobuf wire format vẫn tương thích.

Để migration an toàn, hãy kiểm kê từng pipeline, cố định schema và tool versions, sinh lại mã bằng clean build, không sửa generated files thủ công, rồi kiểm tra ba chiều riêng: **khả năng sinh và biên dịch mã**, **khả năng chạy với đúng dependencies/JDK**, và **khả năng trao đổi dữ liệu với các phiên bản đã phát hành**.

Đặc biệt, với OpenAPI cần xem HTTP client/server semantics và nullability; với JAXB cần xem hệ `javax`/`jakarta`, XJC bindings và XML namespaces; với protobuf cần bảo vệ field numbers/presence và giữ `protoc`–runtime–gRPC stack phù hợp. Một quy trình có phiên bản, contract tests và rollout rõ ràng sẽ giúp đổi JDK mà không làm generated code trở thành nguồn lỗi âm thầm giữa các service.
