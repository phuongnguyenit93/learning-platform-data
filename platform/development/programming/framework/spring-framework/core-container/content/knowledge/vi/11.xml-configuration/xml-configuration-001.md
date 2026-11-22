# Cấu trúc `<beans>`, XML namespace và kiểm tra XSD schema trong Spring Core Container

## 1. Vì sao vẫn cần hiểu Spring XML?

Spring Framework hỗ trợ mô tả bean definitions bằng Java configuration, annotation và XML. Trong dự án hiện đại, Java configuration thường nổi bật; nhưng các hệ thống lâu năm, thư viện tích hợp, ứng dụng lai Java/XML hoặc file cấu hình hạ tầng vẫn có thể sử dụng XML.

Một file Spring XML không chỉ là “danh sách class”. Nó là tài liệu XML có **phần tử gốc**, **XML namespaces**, **khai báo schema**, **bean definitions**, **dependency references** và những phần mở rộng namespace do Spring hoặc thư viện cung cấp.

Ví dụ cấu trúc tối thiểu đúng chuẩn:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="messageRepository"
          class="demo.MessageRepository"/>

    <bean id="messageService"
          class="demo.MessageService">
        <constructor-arg ref="messageRepository"/>
    </bean>
</beans>
```

Đoạn trên là **XML minh họa**: để chạy, các class `demo.MessageRepository` và `demo.MessageService` phải tồn tại và constructor của service phải nhận repository phù hợp. `<beans>` là root, hai `<bean>` là bean definitions, `<constructor-arg>` khai báo dependency.

Bài này trả lời những câu hỏi cốt lõi:

1. Vì sao `<beans>` phải nằm trong đúng namespace?
2. `xmlns`, `xmlns:xsi` và `xsi:schemaLocation` khác nhau thế nào?
3. Vì sao một file có nhiều namespaces nhưng vẫn chỉ có một root?
4. Thế nào là XSD validation, và nó **kiểm tra được/không kiểm tra được** những điều gì?
5. Spring tìm các XSD ở đâu, tại sao URI `www.springframework.org` không nhất thiết có nghĩa phải tải mạng mỗi lần?
6. `beans`, `p`, `c`, `util`, `context`, `tx`, `aop` khác nhau thế nào?
7. Làm sao viết, chạy và xác minh một dự án Java 17+ với XML và schema đúng?
8. Chẩn đoán lỗi XML parse, schema, namespace handler và bean creation ra sao?

## 2. Ba tầng xử lý khác nhau: XML, XSD và Spring beans

Khi Spring đọc một XML resource, có ít nhất ba mức kiểm tra cần phân biệt:

**Tầng 1 — XML well-formedness:** XML parser kiểm tra cấu trúc cơ bản: tag đóng mở cân bằng, attribute có dấu nháy, ký tự được escape, chỉ một document element. Lỗi như thiếu `</bean>`, dấu `&` chưa escape hoặc có hai phần tử root khiến XML không well-formed.

**Tầng 2 — XML Schema/XSD validation:** Nếu validation được bật và schema phù hợp được nạp, parser kiểm tra những phần tử/thuộc tính/kiểu/quan hệ mà XSD mô tả. Ví dụ, đặt một thẻ không thuộc vocabulary hoặc một attribute không được định nghĩa có thể gây lỗi validation.

**Tầng 3 — Spring bean-definition processing và runtime:** Spring đọc metadata XML, áp dụng namespace handlers, đăng ký bean definitions, rồi BeanFactory tạo/ghép instances. Lỗi class không tồn tại, thiếu constructor, tham chiếu bean sai, circular dependency hoặc exception trong constructor thuộc tầng này; XML hoàn toàn hợp lệ **không bảo đảm ứng dụng chạy được**.

```text
application-context.xml
        |
        v
  XML parser: well-formed?
        | no -> XML parse error
        v
  XML Schema validation?
        | no -> SAXParseException / schema error
        v
  Spring namespace parsers / bean definition reader
        | unknown namespace / invalid bean metadata
        v
  BeanDefinitionRegistry
        |
        v
  BeanFactory + ApplicationContext refresh
        | missing class/ref / DI / lifecycle exception
        v
  Managed beans sẵn sàng
```

Một thông báo “XML schema validation succeeded” chỉ khẳng định file đáp ứng schema trong phạm vi được kiểm tra. Nó **không** kiểm chứng rằng `class="demo.X"` trỏ đến class tồn tại, hoặc `ref="y"` thực sự có bean tên `y`.

## 3. Phần tử gốc `<beans>`

Định dạng XML Spring thông thường có một root `<beans>`. Phần tử này chứa các child elements như `<bean>`, `<alias>`, `<import>`, nested `<beans>` trong trường hợp hỗ trợ profile, hoặc các phần tử mở rộng namespace.

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="clock" class="java.time.Clock"
          factory-method="systemUTC"/>

    <alias name="clock" alias="applicationClock"/>
</beans>
```

Đây là **đoạn minh họa**. Bean `clock` sử dụng static factory method `Clock.systemUTC()`; alias `applicationClock` tham chiếu cùng bean name. Để kiểm tra application startup trong thực tế cần khởi tạo một context có file này.

### 3.1. `id`, `name`, `class`, `ref`

| Cấu trúc | Ý nghĩa | Ghi nhớ |
| --- | --- | --- |
| `<bean id="service" .../>` | Bean name/identifier chính của definition | Phải giải quyết duy nhất trong registry phù hợp |
| `<bean name="one,two" .../>` | Cho phép dùng tên và alias theo cú pháp được Spring hỗ trợ | `name` không đồng nghĩa Java class name |
| `class="com.example.Service"` | Tên class đầy đủ, thường là implementation | XSD nhìn như chuỗi, Spring/JVM mới kiểm tra class |
| `<constructor-arg ref="repo"/>` | Tham chiếu một bean khác | `ref` là bean name, không phải URL hoặc Java package |
| `<property name="title" value="Demo"/>` | Set JavaBean property/giá trị cấu hình | Cần setter/cơ chế gán tương thích |
| `<property name="repo" ref="repo"/>` | Gán bean reference cho property | Spring resolve bean theo tên trong context |
| `<alias name="service" alias="gateway"/>` | Thêm một tên phụ cho cùng bean | Không sinh instance thứ hai |
| `<import resource="other.xml"/>` | Nhập thêm file Spring XML | Khác `@Import(Config.class)` trong JavaConfig |

Các attributes khác như `scope`, `lazy-init`, `init-method` và `destroy-method` được xử lý theo Spring bean semantics. `<beans>` cũng hỗ trợ một số mặc định như `default-lazy-init`, `default-init-method` hoặc `default-destroy-method` trong các trường hợp phù hợp.

### 3.2. Cấu trúc lồng nhau không được phép tùy tiện

Không phải phần tử XML bất kỳ cũng có thể đặt ở mọi vị trí:

```xml
<!-- SAI về ý tưởng: <property> không phải child trực tiếp
     thông thường của <beans>. -->
<beans xmlns="http://www.springframework.org/schema/beans">
    <property name="title" value="X"/>
</beans>
```

Đây là **ví dụ sai có chủ đích**, không phải file để chạy. `<property>` là child của một `<bean>`, không phải top-level definition độc lập. XSD giúp phát hiện lỗi đặt phần tử không phù hợp vị trí (khi schema validation hoạt động).

### 3.3. Nested `<beans>` và profile

Spring hỗ trợ nested `<beans profile="...">` để biểu diễn bean definitions theo môi trường:

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">
    <beans profile="dev">
        <bean id="storage" class="demo.InMemoryStorage"/>
    </beans>
    <beans profile="prod">
        <bean id="storage" class="demo.JdbcStorage"/>
    </beans>
</beans>
```

Đoạn này minh họa cần class `demo.InMemoryStorage`/`demo.JdbcStorage`. Các nested `<beans>` có quy tắc thứ tự/placement do XSD quy định; không rải nested `<beans>` tùy ý xen giữa những định nghĩa khác. Các profile active ảnh hưởng nhóm beans được đăng ký. **XML profile selection khác XSD validation:** một tài liệu có thể hợp lệ về schema nhưng chứa bean definitions chỉ hoạt động khi profile tương ứng active.

## 4. XML namespace là URI, không phải tên prefix

XML namespace phân biệt các phần tử/thuộc tính theo URI định danh.

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:context="http://www.springframework.org/schema/context"
       xmlns:util="http://www.springframework.org/schema/util"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/context
           https://www.springframework.org/schema/context/spring-context.xsd
           http://www.springframework.org/schema/util
           https://www.springframework.org/schema/util/spring-util.xsd">

    <bean id="name" class="java.lang.String">
        <constructor-arg value="Spring"/>
    </bean>
    <util:list id="regions">
        <value>north</value>
        <value>south</value>
    </util:list>
    <context:annotation-config/>
</beans>
```

Ở ví dụ:

- `xmlns="http://www.springframework.org/schema/beans"` chọn **default namespace** cho các phần tử không có prefix như `<beans>`, `<bean>`, `<constructor-arg>` và `<value>`.
- `xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"` cho phép sử dụng attribute `xsi:schemaLocation` của XML Schema instance vocabulary.
- `xmlns:context="http://www.springframework.org/schema/context"` ánh xạ prefix `context` sang Spring context namespace, cho phép dùng `<context:annotation-config/>`.
- `xmlns:util="http://www.springframework.org/schema/util"` ánh xạ prefix `util`, cho phép dùng `<util:list/>`.

Đây là **mã XML minh họa riêng**, không phải phần chương trình hoàn chỉnh ở mục 11. Nó đòi các dependency Spring tương ứng để namespace handlers có sẵn.

### 4.1. Prefix là tên cục bộ, URI quyết định nghĩa

Về XML, có thể viết:

```xml
xmlns:ctx="http://www.springframework.org/schema/context"
```

và dùng `<ctx:annotation-config/>` thay cho `<context:annotation-config/>`. Bản chất namespace vẫn như nhau vì URI không đổi. Convention `context` dễ đọc hơn và được tài liệu Spring sử dụng phổ biến, nhưng parser không dựa vào chữ “context” của prefix để nhận diện handler.

Ngược lại:

```xml
xmlns:context="http://example.invalid/not-spring-context"
```

dù prefix tên `context` nhưng URI đã khác Spring context namespace; handler/schema tương ứng không được Spring cung cấp chỉ vì prefix giống nhau.

### 4.2. Namespace URI không nhất thiết là file để tải

`http://www.springframework.org/schema/beans` là namespace name/identifier, còn `https://www.springframework.org/schema/beans/spring-beans.xsd` là địa điểm được đề xuất để tham chiếu schema. Trong `xsi:schemaLocation`, hai giá trị này tạo thành một **cặp**.

Bản thân default namespace URI không khiến XML parser yêu cầu tải nội dung của nó như một HTML page. Trình xử lý XML phân biệt namespace URI, schema location hint và các entity/schema resolution mechanisms.

### 4.3. Có thể đặt prefix cho beans namespace không?

Được. Ví dụ:

```xml
<beans:beans
    xmlns:beans="http://www.springframework.org/schema/beans"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        http://www.springframework.org/schema/beans
        https://www.springframework.org/schema/beans/spring-beans.xsd">
    <beans:bean id="clock" class="java.time.Clock"
                factory-method="systemUTC"/>
</beans:beans>
```

Nhưng cấu hình Spring tiêu chuẩn thường chọn beans namespace làm **default namespace** để tránh phải viết `beans:` trước từng thẻ. Tên namespace URI chứ không phải cách viết prefix quyết định nghĩa.

## 5. `xsi:schemaLocation`: đọc đúng từng cặp

Hình thức:

```xml
xsi:schemaLocation="
    NAMESPACE_URI_1   LOCATION_OF_XSD_1
    NAMESPACE_URI_2   LOCATION_OF_XSD_2"
```

Đây là **khung cú pháp**, không phải XML chạy độc lập; mỗi namespace được khai báo có thể có mapping tới XSD liên quan để editor/parser thực hiện validation.

Ví dụ thực tế:

```xml
xsi:schemaLocation="
    http://www.springframework.org/schema/beans
    https://www.springframework.org/schema/beans/spring-beans.xsd
    http://www.springframework.org/schema/util
    https://www.springframework.org/schema/util/spring-util.xsd"
```

Suy ra:

| Namespace URI | XSD location |
| --- | --- |
| `http://www.springframework.org/schema/beans` | `https://www.springframework.org/schema/beans/spring-beans.xsd` |
| `http://www.springframework.org/schema/util` | `https://www.springframework.org/schema/util/spring-util.xsd` |

**Không được** trộn URI beans với XSD util hoặc đảo từng phần tử vì parser/schema resolver cần biết XSD ứng với namespace nào.

### 5.1. Tại sao URI namespace thường dùng `http` nhưng XSD có thể dùng `https`?

Đây là quy ước được tài liệu Spring sử dụng. **Namespace URI là định danh cố định**, không phải cam kết về giao thức tải mạng; XSD location là schema hint/resource location. Đừng tự đổi `xmlns` thành `https://.../schema/beans` chỉ vì muốn “an toàn hơn”: đó là **namespace URI khác**, Spring handler có thể không nhận ra.

Cấu hình đúng:

```xml
xmlns="http://www.springframework.org/schema/beans"
```

và mapping theo tài liệu:

```xml
http://www.springframework.org/schema/beans
https://www.springframework.org/schema/beans/spring-beans.xsd
```

Hai đoạn này là các **fragment minh họa**, không phải XML document hoàn chỉnh.

### 5.2. Versionless XSD và versioned XSD

Spring thường khuyên dùng `spring-beans.xsd` không gắn số phiên bản trong URL để schema được ánh xạ tương thích với Spring artifacts của project. Một số hệ thống legacy có thể ghi `spring-beans-3.0.xsd` hoặc dạng versioned khác.

Khi bảo trì:

1. Kiểm tra Spring Framework version thực tế trong dependency graph.
2. Ưu tiên schema URL chính thức tương ứng với phiên bản Spring đang chạy; với cấu hình mới, dùng versionless URL theo reference hiện tại.
3. Không copy nguyên schemaLocation cũ từ một bài hướng dẫn rất lâu trước khi đối chiếu thư viện.
4. Kiểm tra sự hiện diện của namespace handler cho phần tử sử dụng, không chỉ sự tồn tại URL schema.
5. Nếu framework phụ thuộc một custom schema, phải có provider JAR/resource phù hợp.

Đừng nhầm **XSD version** với XML declaration `<?xml version="1.0"?>`: version của ngôn ngữ XML khác hoàn toàn phiên bản schema của Spring.

### 5.3. Schema location là hint, không phải toàn bộ hợp đồng runtime

Theo XML Schema, `xsi:schemaLocation` là gợi ý ánh xạ namespace → schema document, không biến XML metadata thành Java bean definition một cách tự động. Spring XML reader còn có namespace parser/handler riêng cho những elements tùy biến.

Một file có cặp schemaLocation đúng nhưng thiếu Spring module cung cấp namespace handler (ví dụ một namespace của Spring Integration hoặc thư viện bên thứ ba) vẫn có thể không được Spring xử lý như mong đợi.

## 6. Spring giải quyết schema trên classpath ra sao?

Spring có cơ chế ánh xạ schema URLs tới resources bên trong thư viện để tránh phụ thuộc bắt buộc vào network mỗi lần khởi động. Nhiều Spring modules đi kèm cấu hình `META-INF/spring.schemas` và các XSD resources của chính chúng. `PluggableSchemaResolver` có thể đọc mapping này từ classpath.

Cơ chế khái niệm:

```text
XML khai báo:
https://www.springframework.org/schema/beans/spring-beans.xsd
                        |
                        v
             Spring EntityResolver
                        |
                        v
         Tìm mapping META-INF/spring.schemas
                        |
          +-------------+-------------+
          |                           |
          v                           v
   Có mapping classpath         Không có mapping
          |                           |
          v                           v
   Nạp XSD local resource      Resolver/parser có thể
                               cần xử lý location gốc
```

Sơ đồ không bảo đảm mọi XML parser/custom resolver đều offline được. Đối với schema bên thứ ba, nếu thiếu mapping/resource hoặc ứng dụng tự thay thế resolver, việc tìm schema có thể thất bại hoặc cần network. Hãy kiểm tra dependency và resource thay vì mặc định suy ra “Spring luôn tải XSD qua Internet”.

### 6.1. `META-INF/spring.handlers` khác `spring.schemas`

Hai file mapping phục vụ mục đích khác nhau:

| Resource | Vai trò |
| --- | --- |
| `META-INF/spring.schemas` | Ánh xạ schema URL sang XSD resource có thể nạp từ classpath |
| `META-INF/spring.handlers` | Ánh xạ XML namespace URI sang Spring `NamespaceHandler` implementation |
| XSD file | Định nghĩa các phần tử/thuộc tính/vocabulary hợp lệ |
| Namespace handler/parser | Chuyển custom XML elements thành bean definitions hoặc cấu hình hạ tầng |

Ví dụ có XSD cho một custom namespace giúp editor biết thẻ nào hợp lệ; nhưng Spring vẫn cần namespace handler tương ứng để hiểu semantics và đăng ký beans. Có handler nhưng thiếu XSD mapping cũng gây vấn đề validation/editor/resolution tùy cấu hình.

### 6.2. Vì sao IDE báo đỏ nhưng application chạy?

Một XML editor có thể tự tải XSD từ URL trong `schemaLocation`, và mạng/proxy/certificate/cached schema ảnh hưởng kết quả. Spring runtime có thể resolve XSD từ classpath mapping, dẫn đến tình huống IDE báo “cannot resolve schema” nhưng application vẫn load thành công.

Ngược lại, IDE cache một XSD cũ có thể không phản ánh đúng Spring libraries hiện tại; application có thể lỗi do namespace handler không có trên classpath. Hãy kiểm tra **cả IDE schema configuration lẫn runtime dependencies**, đừng chỉ nhìn một dấu gạch đỏ.

### 6.3. Những vấn đề an toàn với XML parser

XML có khả năng khai báo external entities/DOCTYPE và kéo tài nguyên bên ngoài. Khi xử lý XML **không tin cậy**, phải chủ động hạn chế XXE, external entity resolution và quyền truy cập filesystem/network theo API parser đang dùng. Spring XML config thường là tài nguyên do developer kiểm soát; không nên cho user upload XML tùy ý rồi load trực tiếp thành bean definitions.

Đừng tắt validation hoặc mở network/entity expansion vô hạn để “chữa” một lỗi schema. Trước tiên tìm đúng namespace, XSD, module và mapping.

## 7. Một số namespace thường gặp trong Spring XML

| Namespace | URI theo quy ước | Công dụng phổ biến |
| --- | --- | --- |
| `beans` (thường default) | `http://www.springframework.org/schema/beans` | `<bean>`, `<alias>`, `<import>`, dependency metadata |
| `context` | `http://www.springframework.org/schema/context` | `<context:component-scan>`, `<context:annotation-config>`, cấu hình hạ tầng context |
| `util` | `http://www.springframework.org/schema/util` | `<util:list>`, `<util:map>`, `<util:properties>`, constants |
| `tx` | `http://www.springframework.org/schema/tx` | Khai báo transaction infrastructure như `<tx:annotation-driven/>` |
| `aop` | `http://www.springframework.org/schema/aop` | Khai báo các cấu hình AOP liên quan |
| `p` | `http://www.springframework.org/schema/p` | Attributes rút gọn để đặt JavaBean property |
| `c` | `http://www.springframework.org/schema/c` | Attributes rút gọn để truyền constructor arguments |

Những namespaces như `mvc`, `security`, `jms`, `batch` hay integration namespaces còn phụ thuộc vào module/framework tương ứng; không thể mặc định chúng có sẵn chỉ vì application dùng `spring-context`.

### 7.1. `p` namespace: property injection bằng attribute

Dạng đầy đủ:

```xml
<bean id="worker" class="demo.Worker">
    <property name="label" value="primary"/>
</bean>
```

Dạng `p` namespace tương đương về mục đích:

```xml
<bean id="worker"
      class="demo.Worker"
      p:label="primary"/>
```

Đây là hai fragments minh họa; nếu dùng fragment thứ hai, root `<beans>` phải khai báo:

```xml
xmlns:p="http://www.springframework.org/schema/p"
```

`p` namespace **không có XSD riêng**: Spring xử lý cú pháp attribute này ở core. Đừng thêm cặp `.../schema/p .../spring-p.xsd` vào `schemaLocation` rồi kỳ vọng file XSD có tồn tại theo cùng quy ước như beans/util/context.

Chú ý sự khác biệt giữa `p:label="primary"` (literal string/property) và `p:repository-ref="repository"` (tham chiếu bean `repository`). Hậu tố `-ref` phân biệt value với bean reference theo quy tắc của p-namespace.

### 7.2. `c` namespace: constructor argument bằng attribute

Dạng cơ bản:

```xml
<bean id="service" class="demo.MessageService">
    <constructor-arg ref="repository"/>
</bean>
```

Dạng rút gọn dùng chỉ số:

```xml
<bean id="service"
      class="demo.MessageService"
      c:_0-ref="repository"/>
```

`c` namespace cũng **không có XSD riêng**. Root khai báo:

```xml
xmlns:c="http://www.springframework.org/schema/c"
```

`c:_0-ref` trỏ tới tham số constructor index 0, còn `c:repository-ref` dùng tên tham số (phụ thuộc metadata parameter names khả dụng và constructor matching thích hợp). Với Java 17+ và Gradle, cần chú ý compiler option `-parameters` nếu dựa vào tên tham số Java. **Dùng index hoặc `<constructor-arg>` có `index` rõ ràng** giúp tránh phụ thuộc vào parameter-name metadata trong những ví dụ nhỏ.

### 7.3. `util` namespace: collection/configuration utilities

```xml
<util:list id="channels">
    <value>sms</value>
    <value>email</value>
</util:list>
```

Cần khai báo `xmlns:util` và mapping `spring-util.xsd` trong `schemaLocation`. Spring đăng ký một bean dạng `List` có thể lookup qua `getBean("channels")`.

Một số utilities khác gồm `<util:map>`, `<util:set>`, `<util:properties>` và `<util:constant>`. Chúng giúp XML ngắn và diễn đạt rõ hơn một số factory beans tương đương.

### 7.4. `context` namespace: kích hoạt annotation processing

Ví dụ:

```xml
<context:annotation-config/>
```

Khi namespace handler tương ứng hoạt động, Spring đăng ký infrastructure để xử lý nhiều dependency-injection/lifecycle annotations trên **những bean đã được đăng ký**. Nhưng phần tử này **không tự động quét package**. Để scan component candidates, dùng:

```xml
<context:component-scan base-package="demo.services"/>
```

Cả hai đoạn là fragments minh họa. Cần có component classes ở package tương ứng; `<context:component-scan>` mới thực hiện component scanning. Nó cũng thường kích hoạt annotation configuration phù hợp theo mặc định. Đừng thêm cả hai chỉ vì “càng nhiều càng tốt” mà không hiểu scope.

### 7.5. `tx` và `aop` là infrastructure, không phải thay thế toàn bộ application setup

```xml
<tx:annotation-driven/>
```

đòi đúng `xmlns:tx`, schema mapping, module dependencies và transaction manager phù hợp. Nó không tự tạo JDBC datasource, database hoặc mọi transaction resource. Tương tự, `aop` namespace cần module hạ tầng tương ứng; không cứ khai báo prefix `aop` là toàn bộ Spring AOP đang chạy.

## 8. Cách Spring kiểm tra schema: AUTO, XSD, DTD, NONE

Spring cung cấp `org.springframework.beans.factory.xml.XmlBeanDefinitionReader` với các validation modes:

- `VALIDATION_AUTO`: tự xác định cơ chế phù hợp.
- `VALIDATION_XSD`: yêu cầu XSD validation.
- `VALIDATION_DTD`: dùng DTD validation khi có tài liệu DTD tương ứng.
- `VALIDATION_NONE`: không thực hiện validation theo mode ấy; XML vẫn cần well-formed và Spring vẫn phải hiểu bean metadata.

API ví dụ:

```java
DefaultListableBeanFactory factory =
        new DefaultListableBeanFactory();

XmlBeanDefinitionReader reader =
        new XmlBeanDefinitionReader(factory);

reader.setValidationMode(XmlBeanDefinitionReader.VALIDATION_XSD);
reader.loadBeanDefinitions(new ClassPathResource("application-context.xml"));
```

Đây là **trích đoạn Java minh họa**; cần imports của `DefaultListableBeanFactory`, `XmlBeanDefinitionReader`, `ClassPathResource` và resource XML. Nó tải bean definitions vào registry; không tương đương toàn bộ `ApplicationContext.refresh()` với post-processors, events và lifecycle callbacks.

### 8.1. Dùng explicit validation khi học/debug

Khi cấu hình Spring XML truyền thống, `ClassPathXmlApplicationContext` mặc định dùng reader và validation strategy phù hợp. Để chứng minh rõ XSD validation, có thể tạo `XmlBeanDefinitionReader` và gọi `setValidationMode(VALIDATION_XSD)`.

Một trang XML hợp lệ về schema nhưng có class name không tồn tại vẫn có thể qua giai đoạn XSD parsing; khi BeanFactory tạo bean mới phát hiện class không load được. Nếu muốn kiểm tra cả semantics, hãy **refresh một Spring application context thật** và gọi các beans.

### 8.2. Cách phân biệt ba lỗi khi debug

**Sai cấu trúc XML:**

```xml
<beans>
    <bean id="x" class="demo.X">
</beans>
```

Thiếu `</bean>` nên XML không well-formed: parser sẽ lỗi trước khi Spring hiểu bean definitions.

**Đúng XML nhưng sai XSD:**

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">
    <bean id="x" class="demo.X" unknown-attribute="bad"/>
</beans>
```

Đây là ví dụ **cố ý sai** ở tầng schema: thuộc tính không được XSD của Spring beans chấp nhận. Parser validating có thể báo kiểu `cvc-complex-type...`, tùy XML library và phiên bản.

**Đúng XML và XSD nhưng sai Spring runtime:**

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">
    <bean id="x" class="demo.ClassDoesNotExist"/>
</beans>
```

Đây là ví dụ **cố ý sai** ở tầng bean creation/class loading. XSD không biết class Java có tồn tại trên classpath hay không. Application context sẽ thất bại khi cố resolve hoặc tạo bean theo metadata đó.

### 8.3. Không nên sửa lỗi bằng cách tắt validation trước tiên

Gặp `cvc-complex-type.2.4.a` hay `Cannot find declaration of element 'beans'` không nên phản xạ tắt validation để ứng dụng chạy. Lỗi có thể do namespace URI sai, cặp schemaLocation nhầm hoặc thiếu module cung cấp XSD/namespace handler. Vô hiệu validation làm mất cơ chế phát hiện cấu trúc sai mà không giải quyết missing class, missing bean hoặc namespace handler.

Dùng `VALIDATION_NONE` chỉ khi có lý do kỹ thuật rõ và hiểu mức kiểm tra bị bỏ. Với XML do bên ngoài cung cấp, tắt XSD validation cũng không biến việc deserialize/instantiate tùy ý thành an toàn.

## 9. Những lỗi namespace và schema kinh điển

| Lỗi / triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra và sửa |
| --- | --- | --- |
| `Cannot find declaration of element 'beans'` | Root sai namespace hoặc schema resolver không nạp đúng XSD | So sánh `xmlns` và cặp beans `schemaLocation` theo docs |
| `cvc-complex-type...` | Phần tử/attribute sai, đặt sai vị trí hoặc vi phạm XSD | Đọc tên element/attribute và vị trí lỗi trong XML |
| `The prefix "context" ... is not bound` | Dùng `<context:...>` mà thiếu `xmlns:context` | Khai báo namespace prefix trên root |
| Namespace prefix có nhưng tag không được hiểu | URI không đúng hoặc handler JAR thiếu | Kiểm tra URI thực tế, `META-INF/spring.handlers` và dependencies |
| `Unable to locate Spring NamespaceHandler` | Thiếu module chứa handler hoặc namespace URI không khớp | Bổ sung dependency đúng module, không chỉ XSD |
| `schema_reference.4: Failed to read schema document` | XSD URL/mapping sai, network/SSL IDE hoặc thiếu schema resource | Kiểm tra `spring.schemas`, schemaLocation, environment |
| IDE đỏ nhưng runtime chạy | IDE không resolve XSD trong khi Spring dùng classpath mapping | Kiểm tra IDE catalog/network, không vội sửa XML đúng |
| `xmlns="https://www.springframework.org/schema/beans"` | Đổi nhầm namespace URI từ http sang https | Dùng `http://www.springframework.org/schema/beans` theo docs |
| `xmlns:p` có nhưng cố thêm `spring-p.xsd` | p namespace không có XSD riêng | Giữ prefix, bỏ cặp p XSD không tồn tại |
| `xmlns:c` có nhưng cố thêm `spring-c.xsd` | c namespace cũng không có XSD riêng | Dùng constructor args đúng cú pháp, không khai c XSD |
| `ref="wrongName"` lỗi khi refresh | Tên bean không tồn tại trong context | Kiểm tra `id`/`alias`, files được import, active profiles |
| Class name sai trong `class=...` | Typo FQCN hoặc dependency runtime thiếu | Kiểm tra classpath và `package` thực tế |
| `<context:annotation-config/>` không tạo component | Nó không tự quét classpath | Thêm `<context:component-scan>` khi thực sự muốn scan |
| XSD đúng nhưng property setter lỗi | JavaBean property name/type không phù hợp | Đọc exception creation/`NotWritablePropertyException` |
| Hai beans trùng `id` | Registry name collision/overriding theo policy | Đổi tên/namespace bean hợp lý; không dựa vào XSD phát hiện |
| `util:list` gây lỗi parsing | Chưa khai `xmlns:util`/schema handler hoặc sai cấu trúc | Thêm mapping đúng và Spring module cần thiết |
| XML từ tutorial cũ dùng schema versions lạ | Schema không khớp Spring runtime hiện tại | Đối chiếu Spring 6.2 docs và JAR resources |
| `DOCTYPE` làm tải external resource | XML/parser entity resolution và input không đáng tin | Không load XML user-supplied tùy ý; hạn chế XXE/DTD theo nhu cầu |

### 9.1. Checklist debug trong năm phút

1. **Mở đúng XML file** thực sự được application context đọc: có thể có nhiều `applicationContext.xml` trên classpath.
2. Kiểm tra XML **well-formed** trước: đóng mở tag, dấu nháy, escape `&amp;`, chỉ một root.
3. Kiểm tra namespace URI chính xác ở `xmlns` và mọi prefixed `xmlns:...`.
4. Đọc `xsi:schemaLocation` theo từng **cặp** namespace → XSD, không chỉ nhìn dòng cuối.
5. Kiểm tra dependency Spring có module namespace handler và schema resource không.
6. Xem stack trace phát sinh ở XML parse, schema validation, bean-definition parsing hay bean creation.
7. Nếu context load được, kiểm tra beans bằng `containsBean`/`getBeanNamesForType` và thử method ứng dụng.
8. Với IDE-only warning, kiểm tra cache/catalog/proxy của IDE riêng với Spring runtime.
9. Nếu XML là legacy, đối chiếu tài liệu Spring đúng phiên bản thay vì sửa hằng loạt namespace tùy tiện.
10. Không dùng `VALIDATION_NONE` để che lỗi chưa hiểu.

## 10. Định dạng XML và Java: vài quy tắc quan trọng

### 10.1. XML escaping

Trong attribute literal hoặc text, những ký tự đặc biệt phải escape đúng:

| Muốn biểu diễn | Trong XML |
| --- | --- |
| `&` | `&amp;` |
| `<` | `&lt;` |
| `>` | `&gt;` (khi cần/để rõ nghĩa) |
| `"` trong attribute dùng dấu kép | `&quot;` |
| `'` trong attribute dùng dấu nháy đơn | `&apos;` |

Ví dụ đúng:

```xml
<bean id="formatter" class="demo.Formatter">
    <property name="label" value="A &amp; B"/>
</bean>
```

Đây là đoạn minh họa; cần class `Formatter` và JavaBean property `label`. Spring sẽ nhìn thấy string `A & B` sau khi XML parser xử lý entity.

### 10.2. Java class names trong `class`

`class="demo.MessageService"` phải trỏ đến class Java có thể load được. Đối với nested Java classes, tên nhị phân có thể chứa `$`; trong ứng dụng thật nên tách class độc lập để XML dễ đọc hoặc dùng đúng JVM binary name nếu cần.

### 10.3. Bảo đảm resource nằm trên classpath

Với Gradle Java project:

```text
src/main/java/demo/MessageService.java
src/main/resources/application-context.xml
```

Gradle Java plugin đưa resource trong `src/main/resources` lên runtime classpath. Khi code gọi:

```java
new ClassPathXmlApplicationContext("application-context.xml")
```

Spring tìm file theo classpath resource name, không phải tự tìm mọi file cùng tên trong toàn workspace.

### 10.4. Hợp nhất nhiều XML files

```xml
<import resource="repository-context.xml"/>
```

Đây là child element của `<beans>`, không phải Java `@Import`. File được import phải là Spring XML hợp lệ; đường dẫn tương đối được giải quyết theo file định nghĩa và resource system. Với ứng dụng lớn, chia XML theo module có thể giúp ownership rõ, nhưng phải quản lý tránh import vòng, definitions trùng tên và environment/profile khác nhau.

## 11. Ví dụ Java 17+ chạy được: beans, p/c/util/context và XSD validation

Dự án này dùng **Spring Framework 6.2.19** qua `spring-context`, không dùng Spring Boot. File `application-context.xml` có:

- default `beans` namespace và `xsi` mapping;
- `p` namespace để inject setter property;
- `c` namespace để inject constructor dependency;
- `util` namespace tạo bean `List<String>`;
- `context` namespace bật annotation configuration infrastructure;
- `<alias>` làm tên phụ;
- chương trình Java load XML bằng `ClassPathXmlApplicationContext` rồi gọi managed beans;
- một lượt đọc riêng bằng `XmlBeanDefinitionReader` đặt `VALIDATION_XSD` nhằm chứng minh schema parse không đồng nghĩa bean instantiation.

### 11.1. Cấu trúc thư mục

```text
spring-xml-namespaces-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       ├── MessageRepository.java
        │       ├── MessageService.java
        │       └── XmlApplication.java
        └── resources/
            └── application-context.xml
```

File `settings.gradle`:

```groovy
rootProject.name = 'spring-xml-namespaces-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
}

application {
    mainClass = 'demo.XmlApplication'
}
```

Dùng JDK 17+ và Gradle tương thích. `spring-context` đem theo các module core/beans cần thiết để parse Spring XML, đăng ký bean definitions và sử dụng util/context namespace handlers.

### 11.2. Java repository

File `src/main/java/demo/MessageRepository.java`:

```java
package demo;

public final class MessageRepository {
    public String lookup(String key) {
        return "order-" + key;
    }
}
```

Đây là class Java thông thường, không có `@Component`. Nó được Spring đăng ký bằng `<bean>` trong XML. Có public no-arg constructor ngầm định để BeanFactory tạo instance.

### 11.3. Java service với constructor và setter

File `src/main/java/demo/MessageService.java`:

```java
package demo;

import java.util.Objects;

public final class MessageService {

    private final MessageRepository repository;
    private String prefix = "";

    public MessageService(MessageRepository repository) {
        this.repository = Objects.requireNonNull(repository);
    }

    public void setPrefix(String prefix) {
        this.prefix = Objects.requireNonNull(prefix);
    }

    public String render(String key) {
        return prefix + repository.lookup(key);
    }
}
```

`MessageService` có một constructor bắt buộc nhận `MessageRepository`. `setPrefix` là JavaBean setter được dùng bởi `p:prefix` trong XML. `render("42")` lấy dữ liệu `order-42` từ repository và thêm prefix.

### 11.4. Spring XML resource

File `src/main/resources/application-context.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:p="http://www.springframework.org/schema/p"
       xmlns:c="http://www.springframework.org/schema/c"
       xmlns:util="http://www.springframework.org/schema/util"
       xmlns:context="http://www.springframework.org/schema/context"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/util
           https://www.springframework.org/schema/util/spring-util.xsd
           http://www.springframework.org/schema/context
           https://www.springframework.org/schema/context/spring-context.xsd">

    <bean id="repository" class="demo.MessageRepository"/>

    <bean id="service"
          class="demo.MessageService"
          c:_0-ref="repository"
          p:prefix="Hello: "/>

    <alias name="service" alias="messageGateway"/>

    <util:list id="channels">
        <value>sms</value>
        <value>email</value>
    </util:list>

    <context:annotation-config/>
</beans>
```

**Vì sao không có cặp XSD cho `p` và `c`?** Hai namespaces này không được định nghĩa bằng XSD riêng; chúng dùng cú pháp attribute shorthand được Spring hỗ trợ. Trái lại, `util` và `context` có schema mappings cụ thể.

**Vì sao `c:_0-ref`?** Nó chỉ tham số constructor ở index 0, tham chiếu bean `repository`. Cách dùng index tránh phụ thuộc vào Java parameter name metadata. `p:prefix="Hello: "` set literal value, không phải ref bean.

**Vì sao `<context:annotation-config/>`?** Để minh họa một thẻ custom namespace làm kích hoạt annotation-processing infrastructure. Hai Java class của demo không có annotation injection nên nó **không bắt buộc cho logic repository/service**. Nếu bỏ thẻ này và đồng thời bỏ khai báo `context`/schema mapping, hành vi render chính của ứng dụng vẫn có thể giữ nguyên.

### 11.5. Java main: kiểm tra XSD riêng rồi load context

File `src/main/java/demo/XmlApplication.java`:

```java
package demo;

import java.util.List;

import org.springframework.beans.factory.support.DefaultListableBeanFactory;
import org.springframework.beans.factory.xml.XmlBeanDefinitionReader;
import org.springframework.context.support.ClassPathXmlApplicationContext;
import org.springframework.core.io.ClassPathResource;

public final class XmlApplication {

    public static void main(String[] args) {
        DefaultListableBeanFactory registry =
                new DefaultListableBeanFactory();

        XmlBeanDefinitionReader reader =
                new XmlBeanDefinitionReader(registry);
        reader.setValidationMode(XmlBeanDefinitionReader.VALIDATION_XSD);
        reader.loadBeanDefinitions(
                new ClassPathResource("application-context.xml"));

        boolean definitionsLoaded =
                registry.containsBeanDefinition("repository") &&
                registry.containsBeanDefinition("service");
        System.out.println("xmlDefinitionsLoaded = " +
                definitionsLoaded);

        try (ClassPathXmlApplicationContext context =
                     new ClassPathXmlApplicationContext(
                             "application-context.xml")) {

            MessageService service =
                    context.getBean("service", MessageService.class);
            MessageService alias =
                    context.getBean("messageGateway",
                            MessageService.class);

            List<?> channels =
                    context.getBean("channels", List.class);

            System.out.println("message = " +
                    service.render("42"));
            System.out.println("aliasSame = " +
                    (service == alias));
            System.out.println("channels = " + channels);
            System.out.println("repositoryExists = " +
                    context.containsBean("repository"));
        }
    }
}
```

Đoạn `XmlBeanDefinitionReader` thứ nhất chỉ tải **definitions** vào một registry riêng và bật validation XSD; nó không thay thế toàn bộ `ApplicationContext.refresh` và không được dùng để tạo service trong demo. Đoạn `ClassPathXmlApplicationContext` thứ hai là context thật quản lý beans và lifecycle; khi đóng context, Spring thực hiện các bước kết thúc phù hợp cho managed beans.

### 11.6. Chạy và đầu ra kỳ vọng

Trong thư mục `spring-xml-namespaces-demo`:

```bash
gradle run --quiet
```

Nếu có Gradle Wrapper, dùng `./gradlew run --quiet` (Linux/macOS) hoặc `.\gradlew.bat run --quiet` (Windows PowerShell).

Các dòng do chương trình in:

```text
xmlDefinitionsLoaded = true
message = Hello: order-42
aliasSame = true
channels = [sms, email]
repositoryExists = true
```

Một Gradle build hoặc logging backend có thể hiển thị thêm dòng ngoài những `System.out.println` trên.

**Giải thích:**

1. `xmlDefinitionsLoaded = true`: reader parse XML với XSD validation và registry chứa hai definitions được đặt tên đúng. Đây là chứng cứ parse/registration, không phải chứng cứ bean instances đã tạo trong registry này.
2. `message = Hello: order-42`: constructor dependency theo `c:_0-ref` đưa managed repository vào service; setter `p:prefix` nhận literal `Hello: `.
3. `aliasSame = true`: `messageGateway` là alias của `service`, không tạo bản sao service.
4. `channels = [sms, email]`: `util:list` tạo collection bean với hai phần tử theo thứ tự khai báo.
5. `repositoryExists = true`: bean repository có trong context dù class Java không mang stereotype annotation.

### 11.7. Một thay đổi nhỏ để thấy khác biệt XSD và Spring runtime

**Thử A — XML không well-formed:** xóa dấu `>` của một tag. Parser fail trước khi đăng ký bean.

**Thử B — XML sai XSD:** đổi `<alias>` thành `<aliases>` nhưng giữ beans namespace; validating parser không nhận child element này.

**Thử C — XML/XSD hợp lệ nhưng sai runtime:** đổi `class="demo.MessageRepository"` thành `class="demo.MissingRepository"`. Schema có thể vẫn chấp nhận string class; context có khả năng lỗi class loading/creation.

**Thử D — Bỏ `p:prefix`:** service vẫn tạo được, nhưng default Java field `prefix=""` khiến message là `order-42`. Đây là thay đổi cấu hình bean hợp lệ, không phải lỗi XSD.

**Thử E — Sai schema mapping:** thay `spring-util.xsd` bằng một schema khác hoặc bỏ namespace mapping phù hợp. Parser/IDE có thể báo lỗi XSD/namespace; xem stack trace và local schema resolver.

**Thử F — Bỏ `<context:annotation-config/>`:** giữ beans, util, p và c; logic service vẫn hoạt động do không dùng annotated injection trong hai domain classes. Cần bỏ thêm context namespace declaration/schema mapping nếu muốn tối giản file.

## 12. Cách kiểm tra XML mà không cần đoán từ IDE

### 12.1. Dùng Spring làm nguồn kiểm chứng chính

Với XML Spring, một XML validator độc lập có thể hữu ích để phát hiện syntax/schema issues. Tuy nhiên, validator chung **không biết** Spring namespace handlers, bean classpath, constructor signatures hoặc dependency graph.

Vì vậy trong quá trình phát triển:

1. Thực hiện validation trong IDE nếu nó đọc đúng XSD.
2. Chạy `XmlBeanDefinitionReader` với XSD mode nếu cần xác nhận cú pháp/schema.
3. Khởi tạo `ClassPathXmlApplicationContext` để kiểm tra bean definitions và dependency resolution.
4. Gọi một use case nhỏ trên managed beans để chắc semantics đúng.
5. Lặp với các profiles/conditions và dependencies thực sự dùng khi deploy.

### 12.2. Khi nào dùng `xmllint` hoặc XML editor?

Công cụ `xmllint --noout file.xml` (nếu cài) kiểm tra XML well-formedness, không chứng minh bean definitions đúng. Cú pháp `xmllint --schema ...` có thể validate với XSD resource cụ thể, nhưng khi có nhiều namespaces/custom schemas, bạn cần cấu hình catalog/resolver đầy đủ. Trong một Spring project thực tế, phép thử tạo context thường có giá trị xác minh tổng thể cao hơn.

Không ép dùng network validator công khai cho file XML chứa secrets hoặc thông tin nội bộ. Nếu có dữ liệu nhạy cảm, dùng công cụ local và chính sách bảo mật của dự án.

### 12.3. Kiểm tra Gradle dependencies

Ví dụ bài này chỉ dùng `spring-context`, là đủ cho `beans`/`context`/`util` trong Spring Framework Core. Nếu bổ sung `tx`, `aop`, `jdbc` hay namespace của thư viện khác, cần module phù hợp có handler và runtime classes.

Đọc dependency graph khi gặp lỗi namespace handler:

```bash
gradle dependencies --configuration runtimeClasspath
```

Lệnh trên chỉ có ý nghĩa khi chạy trong Gradle project có cấu hình `runtimeClasspath` thích hợp. Nó chứng minh dependency graph, **không xác nhận** rằng file XML đã được load hoặc bean đã tạo thành công.

## 13. Bài tập có đáp án

### Bài 1 — Root của Spring XML

Tài liệu có hai top-level `<bean>` và không có `<beans>`. Hợp lệ như một Spring beans document chuẩn không?

**Đáp án:** Không. XML nói chung yêu cầu một document root, và định dạng Spring beans thông thường dùng root `<beans>` chứa các bean definitions.

### Bài 2 — Namespace URI bị đổi thành HTTPS

Người học đổi `xmlns="http://www.springframework.org/schema/beans"` thành `xmlns="https://www.springframework.org/schema/beans"` vì nghĩ URL mới an toàn hơn. Điều gì sai?

**Đáp án:** XML namespace URI là identifier; hai chuỗi khác nhau là hai namespaces khác nhau. Cần dùng URI mà Spring/schema quy định; XSD location dùng HTTPS có thể được khai báo riêng trong schemaLocation.

### Bài 3 — Schema mapping

Có `xmlns:util="http://www.springframework.org/schema/util"` và muốn sử dụng `<util:list>`. Một cặp `xsi:schemaLocation` phù hợp là gì?

**Đáp án:** `http://www.springframework.org/schema/util` ghép với `https://www.springframework.org/schema/util/spring-util.xsd` trong tài liệu Spring 6.2.

### Bài 4 — `p` namespace và XSD

Dùng `p:name="alpha"` trong bean. Có bắt buộc thêm một `spring-p.xsd` không?

**Đáp án:** Không. `p` namespace là shorthand property attributes do Spring core hỗ trợ và không có XSD riêng như beans/util/context.

### Bài 5 — `c` namespace chọn tham số constructor

Một class có constructor `Service(Repository repository)`. Cần truyền bean tên `repositoryBean` mà không dựa vào parameter name metadata. Thuộc tính c nào phù hợp?

**Đáp án:** `c:_0-ref="repositoryBean"` (khi constructor phù hợp), hoặc dùng `<constructor-arg index="0" ref="repositoryBean"/>`.

### Bài 6 — Lỗi XML hay lỗi runtime?

File có `<bean id="foo" class="no.such.Class"/>` và mọi namespace/XSD đều đúng. XSD có chắc báo class không tồn tại không?

**Đáp án:** Không. XSD xem `class` như metadata dạng string. Spring/JVM kiểm tra class loading/creation ở tầng container.

### Bài 7 — `context:annotation-config` có tự scan package?

Một XML chỉ có `<context:annotation-config/>`, class `demo.UserService` mang `@Service` nhưng không được khai báo bean/import/scan. Có chắc bean `userService` xuất hiện?

**Đáp án:** Không. Để tự quét component candidates, cần `<context:component-scan base-package="demo"/>` hoặc cơ chế đăng ký khác.

### Bài 8 — Prefix hay URI?

Người học khai báo `xmlns:ctx="http://www.springframework.org/schema/context"` rồi dùng `<ctx:annotation-config/>`. Có cần đổi prefix thành `context` mới chạy không?

**Đáp án:** Không, prefix là tên cục bộ; URI đúng mới quan trọng. Tuy vậy theo convention `context` dễ đọc hơn.

### Bài 9 — Alias và singleton

`<alias name="service" alias="gateway"/>` có sinh hai instances singleton không?

**Đáp án:** Không. Hai names trỏ tới cùng bean trong container; alias không tạo bean definition riêng.

### Bài 10 — XSD validation và bean creation

`XmlBeanDefinitionReader` đọc thành công XML và registry có definitions. Điều này có bảo đảm `ApplicationContext.refresh()` thành công không?

**Đáp án:** Không. Constructor dependency sai, thiếu bean ref, factory method lỗi hoặc lifecycle exception vẫn có thể xảy ra khi Spring khởi tạo beans.

### Bài 11 — Thiếu handler

XML có `xmlns:tx`, mapping `spring-tx.xsd` đúng nhưng runtime classpath không có module cung cấp tx namespace handler. Có chắc parser hiểu `<tx:annotation-driven/>` không?

**Đáp án:** Không. Ngoài schema, Spring cần namespace handler và các dependencies hạ tầng tương ứng.

### Bài 12 — Không có mạng

Ứng dụng chạy trong môi trường offline, file XML tham chiếu Spring XSD qua location HTTPS. Có phải chắc chắn không khởi động được?

**Đáp án:** Không. Spring thường dùng classpath `META-INF/spring.schemas` để resolve XSD Spring chính thức. Nếu handler/schema mapping của module khác không có, có thể vẫn lỗi; phải kiểm tra actual resolver và dependencies.

### Bài 13 — Profile khác XSD

XML có `<beans profile="prod">` chứa một bean quan trọng; file qua validation. Trong môi trường chỉ active `dev`, bean đó có chắc được đăng ký không?

**Đáp án:** Không. Profile selection là điều kiện xử lý bean definitions của Spring, khác với việc cấu trúc XML có hợp lệ với XSD hay không.

### Bài 14 — XML escape

Muốn setter nhận chuỗi `Sales & Marketing` trong attribute `value`, viết nguyên dấu `&` có hợp lệ không?

**Đáp án:** Không. Trong XML cần `Sales &amp; Marketing` để parser tái tạo thành chuỗi mong muốn.

### Bài 15 — Kiểm tra bằng công cụ nào?

Bạn muốn chắc Java constructor của `demo.MessageService` nhận bean repository đã cấu hình. Chỉ cần kiểm tra syntax XML không?

**Đáp án:** Không. Cần load bean definitions và khởi tạo Spring context thật, rồi lookup/gọi method hoặc viết integration test.

## 14. Checklist dùng Spring XML bền vững

- Mỗi file có **một root `<beans>`** và XML well-formed.
- Default `xmlns` là URI beans **đúng**.
- `xmlns:xsi` được khai báo khi dùng `xsi:schemaLocation`.
- Mỗi namespace có schema mapping đúng khi cần XSD; cặp namespace→XSD không bị trộn.
- `p` và `c` được dùng đúng để rút gọn injection, **không** bịa XSD riêng cho chúng.
- `class` trỏ đến FQCN có trên runtime classpath, `ref` trỏ đúng bean name/alias.
- Các namespace handlers như `context`, `tx`, `aop` có module/JAR tương ứng.
- Resource `application-context.xml` nằm trên classpath và app load đúng file ấy.
- Không đồng nhất IDE schema warning với runtime Spring error; kiểm tra cả hai.
- Không tắt XSD validation chỉ để che lỗi cấu trúc hoặc thiếu handler.
- Đọc đầy đủ exception chain, phân biệt parsing, validation, registration và instantiation.
- Viết test Spring context nhỏ cho cấu hình quan trọng, cả positive và negative cases.
- Không load Spring XML từ input không tin cậy mà không có kiểm soát an toàn.
- Khi ghép nhiều XML files hoặc profile, kiểm soát trùng bean names và phạm vi các definitions.

## 15. Ghi nhớ cuối cùng

**`<beans>` là root của Spring XML configuration.** Các phần tử như `<bean>` được đặt trong namespace `http://www.springframework.org/schema/beans`. `xmlns` chọn default namespace, `xmlns:prefix` ánh xạ prefix sang một namespace URI, còn `xsi:schemaLocation` ghép từng URI với XSD được dùng cho validation.

**Schema validation chỉ kiểm tra những ràng buộc XSD mô tả.** Nó không tự khẳng định Java class tồn tại, bean references hợp lệ, constructors resolve thành công hoặc application context chạy được. Muốn đảm bảo cấu hình hoạt động, kiểm tra cả XML/XSD lẫn bean-definition parsing, tạo context và behavior ứng dụng.

**`p` và `c` là shorthands không có XSD riêng**, trong khi `util`/`context`/`tx`/`aop` có schema và handler tương ứng. Spring có thể resolve XSD chính thức từ classpath mapping, giảm phụ thuộc mạng; custom namespaces vẫn phải cung cấp handler/schema đúng.

Thực hành tốt nhất khi xử lý Spring XML là luôn trả lời được ba câu: **File có đúng XML namespace/XSD không? Spring có đăng ký đúng bean definitions không? BeanFactory có thực sự tạo và nối được những dependencies không?**

### Tài liệu chính thức

- [Spring Framework 6.2 — Container Overview / XML as an External Configuration DSL](https://docs.spring.io/spring-framework/reference/6.2/core/beans/basics.html).
- [Spring Framework 6.2 — Bean Overview / Naming Beans](https://docs.spring.io/spring-framework/reference/6.2/core/beans/definition.html).
- [Spring Framework 6.2 — Dependencies and Configuration in Detail: p/c namespaces](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-properties-detailed.html).
- [Spring Framework 6.2 — XML Schemas appendix (util, context, aop, beans)](https://docs.spring.io/spring-framework/reference/6.2/core/appendix/xsd-schemas.html).
- [Spring Framework 6.2 — Environment and XML Bean Definition Profiles](https://docs.spring.io/spring-framework/reference/6.2/core/beans/environment.html).
- [Spring Framework 6.2 — `XmlBeanDefinitionReader` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/xml/XmlBeanDefinitionReader.html).
- [Spring Framework 6.2 — `PluggableSchemaResolver` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/xml/PluggableSchemaResolver.html).
