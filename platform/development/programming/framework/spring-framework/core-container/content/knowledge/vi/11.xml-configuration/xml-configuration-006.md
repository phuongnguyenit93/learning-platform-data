# Nhập tài nguyên cấu hình bằng import trong Spring XML

## 1. Mục tiêu và bối cảnh

Trong một ứng dụng dùng Spring Framework Core Container, cấu hình XML không bắt buộc phải dồn hết vào một file `applicationContext.xml`. Khi số lượng beans tăng, bạn có thể chia definitions theo module — repositories, services, messaging, security, integrations — rồi ghép chúng bằng phần tử **`<import resource="..."/>`**.

Ví dụ:

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <import resource="repositories.xml"/>
    <import resource="services.xml"/>

</beans>
```

Nếu file trên ở `classpath:config/root.xml`, hai imports có đường dẫn tương đối `repositories.xml` và `services.xml` được giải quyết dựa trên **vị trí tài nguyên `root.xml` đang thực hiện import**. Các bean definitions từ những file con đi vào **cùng BeanFactory** với definitions trong file cha.

Sau bài học, bạn sẽ:

1. Hiểu chính xác `<import resource="..."/>` khác với `<bean>`, `<ref>`, `@Import` và `@ImportResource` ra sao.
2. Dùng import để chia XML thành modules và ghép lại từ một root configuration.
3. Phân biệt đường dẫn **tương đối so với file XML import**, `classpath:` và `file:`.
4. Biết vì sao một slash đầu trong đường dẫn tương đối không nhất thiết đổi sang “gốc classpath”.
5. Tránh `../`, đường dẫn phụ thuộc thư mục hiện hành, wildcard thiếu kiểm soát và cấu hình import vòng.
6. Hiểu import được Spring xử lý khi **đọc bean definitions**, không phải runtime lookup và không tạo ApplicationContext con.
7. Viết ví dụ Java 17 + Spring Framework 6.2 chạy được: ba file module XML, một root XML, references qua file, alias, singleton identity và stdout rõ ràng.
8. Xử lý bean-name collisions, scopes, lifecycle và ambiguity khi gộp definitions.
9. Tìm nguyên nhân lỗi resource not found, XML schema, bean class loading, missing refs, duplicate definitions và circular dependencies.
10. Kiểm thử mô hình cấu hình XML nhiều module và biết khi nào chuyển sang Java `@ImportResource`.

**Quy tắc quan trọng nhất:** `<import resource="..."/>` nhập **bean definitions từ một tài nguyên cấu hình** vào container đang đọc XML. Một import không tự tạo bean nghiệp vụ, không chạy workflow, không bảo đảm singleton riêng cho module và không thay thế dependency injection.

## 2. Vì sao nên tách một file XML lớn?

Một file duy nhất có hàng trăm hoặc hàng nghìn `<bean>` definitions thường gây:

- Khó tìm một dependency hoặc bean đang được tham chiếu.
- Các module bị trộn, ownership của cấu hình không rõ.
- Merge conflicts khi nhiều nhóm cùng sửa file.
- Khó tái sử dụng cùng một tập definitions trong môi trường thử nghiệm.
- Khó cô lập configuration errors theo package/feature.
- Dễ vô tình khai báo nhiều lần cùng bean name hoặc import các thành phần không cần thiết.

Có thể tổ chức tài nguyên:

```text
src/main/resources/
└── config/
    ├── root.xml
    ├── modules/
    │   ├── repositories.xml
    │   ├── services.xml
    │   └── reporting.xml
    └── environments/
        └── development.xml
```

Trong `config/root.xml`:

```xml
<import resource="modules/repositories.xml"/>
<import resource="modules/services.xml"/>
<import resource="modules/reporting.xml"/>
```

Đây là mẫu kiến trúc: root mô tả module nào được đưa vào application, mỗi module sở hữu những bean definitions tương ứng. File không được import sẽ **không tự động được Spring nạp** chỉ vì nó nằm cạnh những XML khác trong `src/main/resources`.

### File XML là đơn vị tổ chức, không phải container riêng

Ba file XML khác nhau **không đồng nghĩa** ba BeanFactory khác nhau. Khi một `ClassPathXmlApplicationContext("config/root.xml")` đọc root và các imports, mọi definitions được nạp vào **cùng một registry/BeanFactory**.

```text
ClassPathXmlApplicationContext
              |
              v
       config/root.xml
              |
       +------+------+ 
       |      |      |
       v      v      v
  repo.xml service.xml reporting.xml
       |      |      |
       +------+------+ 
              |
              v
    Một BeanDefinitionRegistry
              |
              v
        Một BeanFactory
              |
              v
    Dependency injection chung
```

Một `<constructor-arg ref="catalogRepository"/>` trong `services.xml` có thể trỏ tới bean `catalogRepository` khai báo trong `repositories.xml`. Đó là dependency resolution thông thường, không phải một phương thức “import bean” riêng.

## 3. Cú pháp <import> và cấu trúc XML hợp lệ

Cú pháp của Spring XML là:

```xml
<import resource="relative-or-qualified-location.xml"/>
```

`resource` là thuộc tính bắt buộc chứa **resource location**. Một file import hợp lệ vẫn là tài liệu Spring bean definitions đầy đủ:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="clock" class="example.FixedClock"/>
</beans>
```

Ví dụ `example.FixedClock` chỉ minh họa cấu trúc; Java class đó phải tồn tại trong dự án thật. Không được viết file import chỉ gồm một vài thẻ `<bean>` đứng tự do **bên ngoài root `<beans>`**, trừ khi đang dùng một định dạng được Spring reader xử lý theo hợp đồng riêng.

### Import là phần tử bên trong <beans>

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <import resource="modules/infrastructure.xml"/>

    <bean id="localService" class="example.LocalService">
        <constructor-arg ref="sharedRepository"/>
    </bean>
</beans>
```

File `infrastructure.xml` được nhập vào root, còn `localService` được khai báo ngay ở root. Nếu file imported cung cấp bean tên `sharedRepository` thì reference có thể được phân giải trong cùng container khi BeanFactory tạo service.

### Có thể có nhiều <import> trong cùng file

```xml
<import resource="base.xml"/>
<import resource="features/orders.xml"/>
<import resource="features/notifications.xml"/>
```

Mỗi lần import yêu cầu Spring đọc resource tương ứng. Trong ứng dụng lớn, đừng ngầm dựa vào việc import cuối “ghi đè thắng” các bean names của import trước; cần kiểm soát collision policy rõ ràng.

### Import có thể lồng nhau

```text
root.xml
  -> modules/orders.xml
       -> repositories.xml
  -> modules/notifications.xml
```

Lưu ý: nếu `orders.xml` ở thư mục `modules`, thì `<import resource="repositories.xml"/>` bên trong `orders.xml` tương đối với **`orders.xml`**, không phải nhất thiết tương đối với `root.xml` ở tầng ngoài.

## 4. Resource location tương đối với file đang import

Đây là quy tắc cốt lõi trong tài liệu Spring Framework.

Giả sử:

```text
src/main/resources/
└── spring/
    ├── application.xml
    ├── repositories.xml
    └── features/
        ├── notifications.xml
        └── templates.xml
```

Trong `spring/application.xml`:

```xml
<import resource="repositories.xml"/>
<import resource="features/notifications.xml"/>
```

Hai paths tương ứng:

- `repositories.xml` → `spring/repositories.xml`.
- `features/notifications.xml` → `spring/features/notifications.xml`.

Nếu trong `spring/features/notifications.xml` có:

```xml
<import resource="templates.xml"/>
```

thì tài nguyên được tham chiếu là `spring/features/templates.xml`.

**Không phải**:

- `./repositories.xml` tính theo working directory của Java process.
- `src/main/resources/repositories.xml`.
- Một resource tự động ở gốc classpath bất kể vị trí file đang import.

Tính tương đối giúp bạn chuyển cả một module directory sang một vị trí khác mà các imports nội bộ không cần đổi, miễn quan hệ thư mục giữa các file còn giữ nguyên.

### Slash ở đầu không nên được hiểu như chuyển về classpath root

Tài liệu Spring minh họa `<import resource="/resources/themeSource.xml"/>` và giải thích rằng với loại **đường dẫn relative import** ấy, **leading slash được bỏ qua**. Vì thế:

```xml
<import resource="/features/notifications.xml"/>
```

không nên được dùng làm cách nói “từ root của classpath” khi file đang import nằm ở `spring/application.xml`. Hãy dùng đường dẫn relative dễ đọc **không có slash đầu**:

```xml
<import resource="features/notifications.xml"/>
```

Nếu muốn địa chỉ classpath rõ ràng và không phụ thuộc vị trí file import, dùng prefix `classpath:` theo phần sau.

## 5. Đường dẫn classpath: — vị trí rõ tại runtime

Bạn có thể sử dụng resource location đầy đủ:

```xml
<import resource="classpath:config/shared/metrics.xml"/>
```

Nó yêu cầu Spring đọc tài nguyên từ runtime **Java classpath**, không diễn giải như chuỗi đường dẫn relative theo file XML hiện tại.

Giả sử `metrics.xml` ở:

```text
src/main/resources/config/shared/metrics.xml
```

Maven thường copy `src/main/resources` vào output classpath, vì vậy location:

```xml
<import resource="classpath:config/shared/metrics.xml"/>
```

phù hợp sau cả khi chạy trong IDE và đóng gói JAR với resource được bundle đúng.

### classpath: không phải src/main/resources

Cách viết sau dễ sai trong JAR:

```xml
<import resource="src/main/resources/config/shared/metrics.xml"/>
```

`src/main/resources` là cấu trúc **source tree** của Maven, không phải runtime classpath path. Nếu chương trình tình cờ chạy được khi working directory ở project root, việc đó không chứng minh cấu hình portable sang JAR/container.

### classpath: và classpath:/ có gì khác?

Trong nhiều Spring resource-loading contexts, `classpath:/config/shared/metrics.xml` cũng nhận diện location tính từ gốc classpath. Tuy vậy, hãy chọn **một convention** nhất quán trong codebase và xác minh bằng context test; không phối hợp slash/prefix ngẫu nhiên.

### Dùng classpath relative hay fully qualified?

| Nhu cầu | Cách viết | Nhận xét |
| --- | --- | --- |
| File cùng thư mục với importer | `resource="repositories.xml"` | Đơn giản, module dễ di chuyển |
| File nằm thư mục con | `resource="modules/services.xml"` | Rõ cấu trúc module |
| File ở một vị trí classpath ổn định, không phụ thuộc importer | `resource="classpath:config/shared/services.xml"` | Vị trí absolute trong classpath |
| File do deployment đặt ngoài package | `resource="file:/opt/app/conf/extra.xml"` | Phụ thuộc filesystem/runtime |
| File cha bằng `../` | `resource="../shared.xml"` | Có thể hoạt động nhưng nên hạn chế |

**Khuyến nghị:** Với một cây XML thuộc cùng module, ưu tiên relative imports. Với tài nguyên chia sẻ được package như một contract rõ trong classpath, cân nhắc `classpath:`. Đừng dùng location tuyệt đối khi chỉ cần một tài nguyên nằm cạnh importer.

## 6. file: — nhập cấu hình từ filesystem

Ví dụ:

```xml
<import resource="file:/etc/myapp/spring/external-services.xml"/>
```

Đây là đường dẫn **minh họa cho hệ Linux/container**, không tồn tại sẵn trong project chạy ở mục 12.

Một ứng dụng dùng `file:` có thể thay đổi file cấu hình theo deployment mà không thay JAR; tuy nhiên:

- File phải tồn tại và có quyền đọc trên **máy/container thực thi**.
- Volume mounts và permissions cần được triển khai đúng.
- Đường dẫn khác nhau giữa Linux/Windows và giữa các môi trường.
- Có thể có rủi ro cấu hình bị sửa ngoài quy trình triển khai.
- Nếu file chứa bean classes của thư viện ngoài, các class đó vẫn phải có trong runtime classpath.
- Resource import xảy ra lúc container nạp configuration; sửa file sau khi app chạy **không tự cập nhật** BeanFactory.
- Đừng nạp XML không tin cậy như một dạng “cấu hình vô hại”: Spring bean definitions có khả năng instantiate classes và chạy init callbacks, mang tính thực thi rất mạnh.

Spring documentation cũng dùng ví dụ file URL trên Windows như `file:C:/config/services.xml`; hãy chuẩn hóa location phù hợp hệ điều hành và tooling thật.

### Không lạm dụng absolute paths

Absolute file path giúp định vị rõ nhưng tăng coupling giữa application và deployment layout. Khi đường dẫn phải thay theo môi trường, có thể dùng biến môi trường/system property hoặc một cơ chế chỉ định resource location thích hợp, rồi test **giá trị thực cuối cùng** được resolver sử dụng.

## 7. Vì sao nên tránh ../ trong imports?

Tài liệu Spring cho phép đề cập `../` ở relative imports nhưng **không khuyến nghị**, đặc biệt với classpath URL.

Ví dụ:

```xml
<import resource="../shared/common.xml"/>
```

Nó phụ thuộc mạnh vào vị trí vật lý của file importer và cấu trúc thư mục bên ngoài module. Trong môi trường classpath gồm nhiều JAR, dependency order, classloaders hoặc packaging, việc “đi lên thư mục cha” có thể cho ra vị trí khác với dự đoán hoặc thất bại.

Đặc biệt, cách viết dạng:

```xml
<import resource="classpath:../services.xml"/>
```

không nên coi là portable. Spring docs giải thích resource resolution có thể chọn classpath root gần nhất rồi tìm lên parent, và classpath thay đổi có thể làm đường dẫn trỏ sai nơi.

**Giải pháp thực dụng:**

1. Nếu tài nguyên cùng feature, sắp xếp dưới cùng thư mục và import relative không cần `../`.
2. Nếu dùng shared resource có vị trí công khai, chọn `classpath:shared/...`.
3. Nếu do runtime cung cấp, chọn `file:` hoặc location từ configuration mà startup nắm rõ.
4. Test dưới artifact được đóng gói thật, không chỉ chạy từ IDE.

## 8. Import và ClassPathXmlApplicationContext nhận nhiều locations

Có **hai phương án phổ biến** để ghép nhiều XML.

### Phương án A — Một root XML điều phối imports

```java
try (var context =
        new ClassPathXmlApplicationContext("config/root.xml")) {
    // Sử dụng beans từ root và tất cả imported files.
}
```

Ưu điểm:

- Java bootstrap chỉ biết một location.
- Root XML nêu rõ module topology.
- Có thể import nested modules.
- Cấu trúc dễ review vì nhìn root thấy những components được bật.

### Phương án B — Truyền nhiều locations cho constructor

```java
try (var context = new ClassPathXmlApplicationContext(
        "config/modules/repositories.xml",
        "config/modules/services.xml",
        "config/modules/reporting.xml")) {
    // Cùng một ApplicationContext xử lý ba XML locations.
}
```

Ưu điểm:

- Java code chọn danh sách resources.
- Không cần file root chỉ để liệt kê imports.
- Có thể phù hợp với ứng dụng nhỏ hoặc test cấu hình module.

### Không nên dùng đồng thời hai cách để nhập trùng

Nếu `root.xml` **đã import** `modules/repositories.xml` mà Java lại truyền thêm `modules/repositories.xml` cùng với `root.xml`, cùng bean definition có thể được đọc lặp. Tác động phụ thuộc bean-name override policy; bạn có thể thấy lỗi, definition bị thay thế hoặc cấu hình không như mong đợi.

**Chọn một composition entry point rõ ràng.** Trong ví dụ chính, ta chỉ nạp `config/root.xml`.

### Nhập ba file không tạo ba ApplicationContexts

Cả root import và nhiều constructor locations trong **một** `ClassPathXmlApplicationContext` đều nhằm xây một BeanFactory. Khác hoàn toàn với:

```java
// Phản ví dụ nếu mục tiêu là một container chung.
var a = new ClassPathXmlApplicationContext(
        "config/modules/repositories.xml");
var b = new ClassPathXmlApplicationContext(
        "config/modules/services.xml");
```

Đoạn trên tạo **hai contexts** độc lập, nên bean `service` trong context `b` không tự tìm được `repository` thuộc context `a`, trừ khi bạn cấu hình parent-child relationship có chủ đích. Nếu mục tiêu là một graph dependency bình thường, không cần chia contexts.

## 9. Import được xử lý khi nào?

Quy trình khái niệm:

```text
Mở ApplicationContext
         |
         v
Đọc resource config/root.xml
         |
         v
XML reader thấy <import resource="..."/>
         |
         v
Resolve từng Resource location
         |
         v
Parse/import XML bean definitions từ file con
         |
         v
Gộp definitions vào BeanDefinitionRegistry
         |
         v
BeanFactoryPostProcessors / BeanPostProcessors
         |
         v
Resolve dependencies, instantiate bean theo scope/lifecycle
         |
         v
ApplicationContext sẵn sàng cho client code
```

Điểm cần nhớ:

- `<import>` là hành động **nạp configuration metadata**.
- Nó không tương đương một lời gọi `getBean()` cho từng bean ngay tại chỗ.
- Một bean có thể là singleton non-lazy và được tạo sau khi context đọc xong definitions, hoặc lazy/prototype và được tạo theo nhu cầu.
- Bean được import tham gia dependency resolution với bean được khai báo tại root và với nhau.
- Không có namespace/container tự động tách biệt theo file.
- Resource không tìm thấy/parse không được thường làm quá trình tạo context thất bại; đây không phải cú pháp import optional.

Trong XML reader, imported resources được xử lý ngay trong quy trình parse/import bean definitions. Nhưng **thứ tự parse** không được dùng làm công cụ bảo đảm thứ tự business initialization. Khi bean A cần bean B, thể hiện quan hệ bằng `ref`, `constructor-arg`, dependency metadata, không chỉ sắp xếp thẻ imports.

## 10. Liên hệ giữa import và ref/constructor-arg/property

Import chỉ giúp Spring **biết bean definitions từ nhiều file**. Việc sử dụng beans vẫn tuân theo DI.

Repositories XML:

```xml
<bean id="orderRepository"
      class="example.InMemoryOrderRepository"/>
```

Services XML:

```xml
<bean id="orderService" class="example.OrderService">
    <constructor-arg ref="orderRepository"/>
</bean>
```

Reporting XML:

```xml
<bean id="orderReporter" class="example.OrderReporter">
    <property name="orderService" ref="orderService"/>
</bean>
```

Các classes `example.*` trong ba đoạn trên là minh họa. Khi root import đủ ba files, `orderService` có thể nhận repository và `orderReporter` có thể nhận service dù definitions nằm ở files khác nhau.

### ref là bean name, không phải tên XML file

```xml
<constructor-arg ref="orderRepository"/>
```

tìm bean **tên `orderRepository`**, không tìm `orderRepository.xml`. File chứa bean đó có thể đổi vị trí nếu root import đúng và bean name được giữ ổn định.

### value không tương đương ref

```xml
<constructor-arg value="orderRepository"/>
```

truyền **chuỗi literal** thay vì managed repository bean. Nếu constructor mong interface `OrderRepository`, thường sẽ có lỗi type conversion/constructor matching. Đừng thay `ref` bằng `value` để “sửa” một bean name missing.

### Dependency bean có thể xuất hiện trước hoặc sau thẻ import

Đừng phụ thuộc vào thứ tự thẻ XML để nghĩ rằng mỗi bean phải được instantiated ngay khi declaration được đọc. BeanFactory đăng ký definitions trước, rồi resolve dependencies và lifecycle khi tạo beans. Tuy nhiên duplicate definition/overriding theo thứ tự nạp vẫn là rủi ro cần tránh.

## 11. Bean names và aliases khi imports nhiều modules

Một BeanFactory có **không gian tên bean chung**. Nếu hai files khai báo:

```xml
<!-- modules/catalog.xml -->
<bean id="client" class="example.CatalogClient"/>
```

và:

```xml
<!-- modules/payment.xml -->
<bean id="client" class="example.PaymentClient"/>
```

bạn có **xung đột bean name** khi cùng import vào một root. Spring Framework và các tầng cấu hình (đặc biệt Boot) có chính sách override khác nhau; không nên dựa vào việc “file import sau sẽ luôn thắng”.

### Tên theo module

Ưu tiên:

```xml
<bean id="catalogClient" class="example.CatalogClient"/>
<bean id="paymentClient" class="example.PaymentClient"/>
```

Cách đặt tên làm rõ ownership và giảm collision trong hệ thống lớn.

### Alias không đăng ký một bean độc lập

Repositories XML:

```xml
<bean id="catalogRepository"
      class="example.InMemoryCatalogRepository"/>
<alias name="catalogRepository"
       alias="legacyCatalogRepository"/>
```

Trong cùng context, `legacyCatalogRepository` là tên bổ sung trỏ tới bean `catalogRepository`. Với singleton scope:

```java
Object a = context.getBean("catalogRepository");
Object b = context.getBean("legacyCatalogRepository");
System.out.println(a == b);
```

Kết quả là:

```text
true
```

Alias có ích khi module cũ cần tên lịch sử, trong khi cấu hình mới sử dụng tên chuẩn. Nhưng alias **không** tạo thêm bean definition, không tạo thêm singleton và không giải quyết việc hai implementations cùng interface bị nhập nhằng.

### Type matching và @Primary/qualifier

Khi các imports bổ sung nhiều beans cùng interface, autowiring theo type có thể không còn duy nhất. Trong XML, bạn có thể dùng `primary="true"` khi phù hợp hoặc chỉ rõ tên qua `ref`. Trong Java injection, có thể dùng `@Qualifier`/`@Primary`. Việc import nhiều files chỉ tăng tập candidates; nó không tự chọn implementation đúng theo nghiệp vụ.

## 12. Ví dụ hoàn chỉnh Java 17 + Spring Framework 6.2

Ví dụ này dùng **Spring Framework thuần**, không cần Spring Boot. Ta có một root XML và ba XML modules chứa các beans phụ thuộc xuyên file. Tất cả tạo thành **một ApplicationContext**, trong đó repository và service là singleton mặc định.

### 12.1. Yêu cầu môi trường

- JDK 17 trở lên.
- Maven 3.8+ hoặc Maven tương thích với JDK đang dùng.
- Dependency Spring Framework `spring-context`, ví dụ phiên bản 6.2.19.
- Không yêu cầu database, internet ở runtime, web server hoặc file ngoài project.

Maven cần tải dependencies ở lần build đầu nếu local cache chưa có; sau khi tải về, demo là chương trình Java console thuần.

### 12.2. Cấu trúc thư mục

```text
spring-xml-import-demo/
├── pom.xml
└── src/main/
    ├── java/
    │   └── demo/
    │       └── XmlImportDemo.java
    └── resources/
        └── config/
            ├── root.xml
            └── modules/
                ├── repositories.xml
                ├── services.xml
                └── reporting.xml
```

Vị trí này quan trọng: `root.xml` ở `config/`, vì vậy `resource="modules/repositories.xml"` sẽ tìm ở `config/modules/repositories.xml`.

### 12.3. File pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-xml-import-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 12.4. File Java đầy đủ

Tạo `src/main/java/demo/XmlImportDemo.java`:

```java
package demo;

import java.util.Arrays;

import org.springframework.context.support.ClassPathXmlApplicationContext;

public class XmlImportDemo {

    public interface CatalogRepository {
        String titleFor(String sku);
    }

    // Class public static nested để Spring đọc được tên binary có dấu $.
    public static final class InMemoryCatalogRepository
            implements CatalogRepository {

        public InMemoryCatalogRepository() {
        }

        @Override
        public String titleFor(String sku) {
            return switch (sku) {
                case "BK-7" -> "Java book";
                case "MUG-2" -> "Coffee mug";
                default -> "Unknown item";
            };
        }
    }

    public static final class CatalogService {
        private final CatalogRepository repository;
        private final String prefix;

        public CatalogService(CatalogRepository repository, String prefix) {
            this.repository = repository;
            this.prefix = prefix;
        }

        public String describe(String sku) {
            return prefix + repository.titleFor(sku);
        }

        public CatalogRepository repository() {
            return repository;
        }
    }

    public static final class ReportBoard {
        private final CatalogService service;

        public ReportBoard(CatalogService service) {
            this.service = service;
        }

        public String report(String sku) {
            return "REPORT->" + service.describe(sku);
        }

        public CatalogService service() {
            return service;
        }
    }

    public static final class RootTag {
        private final String label;

        public RootTag(String label) {
            this.label = label;
        }

        public String value() {
            return label;
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new ClassPathXmlApplicationContext("config/root.xml")) {

            CatalogRepository repository =
                    context.getBean(CatalogRepository.class);
            CatalogService service =
                    context.getBean(CatalogService.class);
            ReportBoard board =
                    context.getBean(ReportBoard.class);
            RootTag tag =
                    context.getBean(RootTag.class);

            String[] repositoryNames =
                    context.getBeanNamesForType(CatalogRepository.class);
            Arrays.sort(repositoryNames);

            System.out.println("root=" + tag.value());
            System.out.println("catalog=" + service.describe("BK-7"));
            System.out.println("report=" + board.report("MUG-2"));
            System.out.println("sameRepo=" +
                    (repository == service.repository()));
            System.out.println("sameService=" +
                    (service == board.service()));
            System.out.println("aliasSame=" +
                    (context.getBean("catalogRepository") ==
                     context.getBean("legacyCatalogRepository")));
            System.out.println("repositoryBeans=" +
                    Arrays.toString(repositoryNames));
        }
    }
}
```

**Lưu ý:** Các class XML tham chiếu dùng tên binary nested class, chẳng hạn `demo.XmlImportDemo$InMemoryCatalogRepository`. Chúng được khai báo `public static` và có public constructors nên Spring có thể instantiate mà không cần object ngoài `XmlImportDemo`.

### 12.5. File root: config/root.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <!-- Import ba tài nguyên so với thư mục của root.xml. -->
    <import resource="modules/repositories.xml"/>
    <import resource="modules/services.xml"/>
    <import resource="modules/reporting.xml"/>

    <!-- Bean định nghĩa ngay ở root để chứng minh cùng context. -->
    <bean id="rootTag" class="demo.XmlImportDemo$RootTag">
        <constructor-arg value="ready"/>
    </bean>

</beans>
```

Chỉ `root.xml` được nạp bởi Java `ClassPathXmlApplicationContext`. Ba modules được đọc thông qua `<import>`, không cần truyền thêm paths từ `main`.

### 12.6. File module: config/modules/repositories.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="catalogRepository"
          class="demo.XmlImportDemo$InMemoryCatalogRepository"/>

    <alias name="catalogRepository"
           alias="legacyCatalogRepository"/>

</beans>
```

Bean `catalogRepository` implement `CatalogRepository`. `legacyCatalogRepository` là alias của cùng definition/instance singleton.

### 12.7. File module: config/modules/services.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="catalogService"
          class="demo.XmlImportDemo$CatalogService">
        <constructor-arg index="0" ref="catalogRepository"/>
        <constructor-arg index="1" value="CAT:"/>
    </bean>

</beans>
```

`ref="catalogRepository"` yêu cầu Spring tìm bean repository dù declaration của nó nằm ở **XML khác**. Prefix `CAT:` là literal, được truyền qua constructor.

### 12.8. File module: config/modules/reporting.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="reportBoard" class="demo.XmlImportDemo$ReportBoard">
        <constructor-arg ref="catalogService"/>
    </bean>

</beans>
```

`ReportBoard` được Spring inject managed `CatalogService` bằng constructor. Nó không instantiate service mới trong Java business code.

### 12.9. Lệnh chạy

Trong thư mục chứa `pom.xml`:

```bash
mvn -q clean compile exec:java -Dexec.mainClass=demo.XmlImportDemo
```

Output **do chính chương trình in** (không tính Maven/Spring logs có thể xuất hiện tùy logging configuration):

```text
root=ready
catalog=CAT:Java book
report=REPORT->CAT:Coffee mug
sameRepo=true
sameService=true
aliasSame=true
repositoryBeans=[catalogRepository]
```

### 12.10. Giải thích output

**`root=ready`:** Bean `rootTag` được khai báo ngay trong `root.xml`, tạo một object `RootTag` với literal `ready`.

**`catalog=CAT:Java book`:** Service bean khai báo ở `services.xml` nhận repository từ `repositories.xml` và prefix literal `CAT:`. Repository nhận `BK-7` rồi trả `Java book`.

**`report=REPORT->CAT:Coffee mug`:** `ReportBoard` từ `reporting.xml` nhận managed service từ `services.xml`. Service nhận `MUG-2`, repository trả `Coffee mug`, rồi board thêm `REPORT->`.

**`sameRepo=true`:** Tham số `ref` của service trỏ tới managed singleton repository. Lấy bean từ context và lấy reference mà service giữ cho cùng Java object.

**`sameService=true`:** Board giữ đúng managed `CatalogService` singleton, chứ không tạo một instance mới vì ở module XML khác.

**`aliasSame=true`:** `legacyCatalogRepository` không phải một bean độc lập; hai tên alias/main resolve cùng singleton reference.

**`repositoryBeans=[catalogRepository]`:** Có một bean definition tương thích interface `CatalogRepository`. `getBeanNamesForType` trả tên chính; alias không tăng số bean. `Arrays.sort` bảo đảm thứ tự output khi có nhiều tên, không phụ thuộc thứ tự register.

### 12.11. Những kiểm chứng có thể làm thêm

Thêm vào `main` khi `context` còn mở:

```java
if (!context.containsBean("catalogRepository")) {
    throw new AssertionError("Imported repository missing");
}
if (!context.containsBean("catalogService")) {
    throw new AssertionError("Imported service missing");
}
if (!context.containsBean("reportBoard")) {
    throw new AssertionError("Imported reporter missing");
}
if (context.getBean(CatalogService.class).repository()
        != context.getBean(CatalogRepository.class)) {
    throw new AssertionError("Repository singleton not shared");
}
```

Nếu tất cả điều kiện đúng, đoạn assert không in gì. Đây là **đoạn bổ sung**, không phải class Java độc lập. Nó kiểm tra việc XML imports đã làm các bean cùng hiện diện trong context.

### 12.12. Thử thay đổi import

- **Bỏ import reporting:** Xóa `<import resource="modules/reporting.xml"/>`. `context.getBean(ReportBoard.class)` sau đó sẽ không có bean phù hợp, chương trình không in đủ output. Điều này chứng minh file XML khác không được tự tải chỉ vì có trên classpath.
- **Đổi prefix:** Sửa `value="CAT:"` thành `value="ITEM:"` ở `services.xml`. Output catalog/report thay đổi theo, Java source giữ nguyên.
- **Đổi alias:** Sửa `legacyCatalogRepository` thành `oldCatalogRepository` ở `repositories.xml` và sửa lookup tương ứng trong Java. Số bean repository vẫn là một.
- **Nhập cùng file hai lần:** Thêm dòng import `repositories.xml` lần nữa. Cần quan sát/kiểm soát duplicate definition handling; không coi việc import trùng là cách tạo bean thứ hai có ý nghĩa.
- **Đổi đường dẫn sai:** `resource="module/repositories.xml"` (thiếu “s”) dẫn đến resource not found; context không khởi động thành công.
- **Đổi tên bean service:** Sửa `id="catalogService"` thành `id="catalogSrv"` nhưng không sửa `reporting.xml`; reference `ref="catalogService"` bị thiếu. Đây là một regression trong cross-file contract.

## 13. Cách chia module XML mà không tạo phụ thuộc vòng

Một phân chia dễ bảo trì:

```text
config/root.xml
    imports repositories.xml
    imports services.xml
    imports reporting.xml

Bean dependencies:
reportBoard ---> catalogService ---> catalogRepository
```

Ở đây import graph và dependency graph là hai khái niệm khác nhau.

**Import graph:** file nào cần đọc file nào? Nên có root composition một chiều.

**Bean dependency graph:** bean nào cần instance của bean nào? Được mô tả bởi `ref`, `property`, `constructor-arg` hoặc các cơ chế DI tương đương.

Nếu service XML import repository XML và repository XML lại import service XML, bạn tạo **import cycle** dù các bean trong hai files chưa chắc cần nhau. Không nên có quan hệ “mỗi module import module kia để lấy bean” khi một root có thể nhập cả hai.

### Một root thay vì import chéo

Không nên:

```text
services.xml ---> repositories.xml
repositories.xml ---> services.xml
```

Nên:

```text
root.xml ---> services.xml
         \-> repositories.xml
```

Bean `catalogService` vẫn có thể `ref="catalogRepository"`. Tham chiếu cross-file không bắt buộc file service phải tự import file repo, miễn root đưa cả hai definitions vào cùng container.

### Import cycle không giống circular constructor dependency

Nếu XML import graph không có vòng nhưng bean A có constructor nhận B và bean B có constructor nhận A, Spring vẫn gặp **circular constructor dependency**.

```text
Import graph:     root -> a.xml; root -> b.xml  (không vòng)
Bean graph:       bean A -> bean B -> bean A    (có vòng)
```

Đừng chữa một trong hai bằng cách đổi tên file hoặc đảo thứ tự imports. Import cycle phải sửa cách ghép resources; bean cycle phải sửa dependency direction, trích abstraction hoặc coordinator.

## 14. Chia XML theo feature hay theo technical layer?

Hai cách tổ chức đều có thể hợp lý.

### Theo technical layer

```text
root.xml
├── infrastructure.xml
├── repositories.xml
├── services.xml
└── presentation.xml
```

Phù hợp với ứng dụng nhỏ hoặc cấu trúc tầng đã ổn định. Cần tránh để tầng thấp phụ thuộc ngược tầng cao.

### Theo feature/module

```text
root.xml
├── billing/billing-context.xml
├── catalog/catalog-context.xml
└── shipping/shipping-context.xml
```

Phù hợp khi nhóm chịu trách nhiệm từng feature và muốn module boundaries rõ. Mỗi feature config nên công bố những bean names/abstractions mà module khác thật sự cần, tránh import lẫn nhau chỉ để lấy một dependency.

### Một mẫu dung hòa

```text
root.xml
├── core/infrastructure.xml
├── catalog/catalog.xml
├── billing/billing.xml
└── integrations/external.xml
```

Root chọn hệ thống cần những module nào. Khi cần đổi integration triển khai theo môi trường, có thể thay một file import ở root hoặc chọn resource location từ bootstrap config, nhưng giữ một **entry point rõ ràng**.

## 15. Imports và Profiles/điều kiện môi trường

Không phải môi trường nào cũng cần tất cả bean definitions. Spring XML có thuộc tính `profile` trên `<beans>` giúp chọn subset definitions phù hợp với active profiles.

Ví dụ minh họa:

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <beans profile="dev">
        <import resource="environments/development.xml"/>
    </beans>

    <beans profile="prod">
        <import resource="environments/production.xml"/>
    </beans>

</beans>
```

Khi Spring XML reader xử lý profile-specific `<beans>`, những bean definitions trong nhánh profile không active không được đưa vào cùng tập active definitions theo hợp đồng `profile`. Cấu hình chi tiết phụ thuộc cách context đặt active profiles.

### Kích hoạt profile đúng thời điểm

Với `ClassPathXmlApplicationContext`, nếu bạn muốn set active profiles **trước khi refresh**, có thể tạo context chưa auto-refresh:

```java
ClassPathXmlApplicationContext context =
        new ClassPathXmlApplicationContext(
                new String[]{"config/root.xml"}, false);
context.getEnvironment().setActiveProfiles("dev");
context.refresh();
try {
    // Sử dụng beans của profile dev.
} finally {
    context.close();
}
```

Đây là đoạn minh họa luồng bootstrap. Nó **khác** constructor `ClassPathXmlApplicationContext("config/root.xml")` mặc định refresh ngay. Đặt active profiles sau refresh không có tác dụng quay ngược các import/bean definitions đã được xử lý.

### Nếu chỉ muốn chọn một import ngoài XML?

Có thể chọn resource list từ Java bootstrap/environment khi khởi tạo context, hoặc dùng profile-specific nested `<beans>` nếu phù hợp. Không phải cứ dùng `<import>` là có một thuộc tính `optional="true"` hay `condition="..."` trên chính thẻ import; đừng bịa attributes không thuộc Spring XML schema.

### Thận trọng với dependency bắt buộc

Nếu profile dev nạp `devRepository` nhưng profile prod không nạp bất kỳ `OrderRepository` nào, một `OrderService` bắt buộc cần repository vẫn fail startup ở prod. Hãy test từng profile hợp lệ.

## 16. Property placeholders trong đường dẫn import

Spring XML import location có thể chứa placeholders theo cơ chế environment/system-property resolution trong quá trình đọc XML, ví dụ:

```xml
<import resource="classpath:config/${module.resource}"/>
```

Nếu `module.resource` là một JVM system property được Spring environment thấy và có giá trị `modules/services.xml`, location dự kiến sau resolve là:

```text
classpath:config/modules/services.xml
```

**Lưu ý mốc thời gian:** XML imports được resolve **trong lúc đọc bean definitions**. Một `PropertySourcesPlaceholderConfigurer` do chính tài liệu XML đang import khai báo có thể chỉ được tạo/chạy ở giai đoạn BeanFactory post-processing **sau khi import đã cần location**. Vì vậy đừng phụ thuộc vào configurer khai báo muộn để resolve đường dẫn import sớm.

### Ví dụ chạy thử với JVM system property

Khi có file `config/root.xml` chứa:

```xml
<import resource="classpath:config/${module.resource}"/>
```

và tài nguyên nằm ở `config/modules/services.xml`, hãy bảo đảm system property đã được thiết lập **trước khi context refresh**, ví dụ qua JVM startup args hoặc:

```java
System.setProperty("module.resource", "modules/services.xml");
// Sau đó mới tạo/refresh ClassPathXmlApplicationContext.
```

Đoạn này là minh họa; project runnable chính ở mục 12 **không** cần property placeholder. Tránh đặt system properties từ business code khi có nhiều contexts chạy song song; dùng một startup configuration source nhất quán.

### Giá trị chưa resolve

Nếu placeholder không có giá trị, import location có thể không tìm được resource và context startup fail. Hãy coi placeholder dùng để chọn file configuration là một **yêu cầu bootstrap** và validate trong quá trình triển khai.

## 17. classpath*: và wildcard resource patterns

Spring `ResourcePatternResolver` hỗ trợ prefix **`classpath*:`** để tìm **tất cả** resources phù hợp trên classpath trong những ngữ cảnh hỗ trợ resource patterns.

Ví dụ minh họa:

```xml
<import resource="classpath*:META-INF/spring/module-context.xml"/>
```

Khi được xử lý bởi resolver có hỗ trợ `classpath*:`, location có thể trả **nhiều resources** ở những JAR/modules khác nhau. Đây là cơ chế khác với `classpath:` thường nhắm đến một resource tại path được yêu cầu.

### Vì sao cần cẩn trọng?

- Một thư viện khác có thể đóng gói cùng resource path.
- Thứ tự resources từ classloader không nên dùng làm nghiệp vụ precedence.
- Có thể nạp những XML không dự tính, thậm chí cùng bean names.
- Một số patterns/wildcards trong JAR còn phụ thuộc classloader và packaging.
- Resource set ở IDE test khác với JAR/container/runtime server.
- Không phù hợp nếu bạn muốn cho phép đúng **một** cấu hình module từ một package.

**Khuyến nghị:** Đối với module lõi có dependencies rõ, dùng đường dẫn cụ thể. Dùng wildcard resource discovery chỉ khi “nạp tất cả match” là yêu cầu rõ ràng, có kiểm thử package và quy tắc collision.

Không trộn nghĩa `classpath*:` với kiểu glob shell `*.xml`. Các dạng pattern cụ thể phải được hỗ trợ bởi Spring resource resolver và được test trên packaging mục tiêu.

## 18. Thiếu file import có được bỏ qua không?

Với Spring XML `<import>` bình thường, file bị thiếu hoặc lỗi parse thường dẫn đến **thất bại khi tạo ApplicationContext**, ví dụ exception liên quan bean definition store hoặc resource loading.

```xml
<import resource="modules/non-existent.xml"/>
```

Không nên mặc định rằng Spring sẽ bỏ qua vì tên file trông giống “tùy chọn”. Trong Spring XML schema thông dụng, `<import>` không có một cơ chế `optional="true"` chung tương đương với conditional import.

Nếu một feature không bắt buộc:

- Không include dòng import của nó trong root của môi trường đó.
- Hoặc dùng `<beans profile="...">` để chỉ import khi profile phù hợp.
- Hoặc cấu hình root/resources list được xác định ở bootstrap cho môi trường.
- Hoặc tách optional infrastructure thành mô-đun khác có enable flag/conditional configuration rõ ràng.

**Đừng che mọi exception và tiếp tục với một container nạp thiếu definitions**: các bean bắt buộc có thể fail muộn và khó chẩn đoán hơn.

## 19. XML schema và namespace phải hợp lệ trong từng imported file

Một imported XML vẫn phải là một tài liệu Spring configuration parse được.

Ví dụ có namespace `context:`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:context="http://www.springframework.org/schema/context"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/context
           https://www.springframework.org/schema/context/spring-context.xsd">

    <context:annotation-config/>

</beans>
```

Đây là ví dụ cú pháp của một file module. Nếu file imported dùng namespace custom, nó phải khai báo `xmlns`/`xsi:schemaLocation` phù hợp và dependency cung cấp namespace handler trên classpath.

Một root có namespace `context` **không mặc định làm mọi file XML con tự có khai báo prefix `context:`**. Từng XML document phải hợp lệ riêng về mặt XML namespaces.

### Import không thay thế dependency JAR

Nếu imported XML có:

```xml
<bean id="legacyConnector" class="com.vendor.LegacyConnector"/>
```

mà `com.vendor.LegacyConnector` không tồn tại trong runtime classpath, Spring vẫn báo class loading/bean creation failure. `<import>` không tải code JAR từ mạng, không tự cài dependency và không sửa Java classpath.

## 20. Duplicate imports và bean overriding

Có hai tình huống khác nhau.

### 20.1. Cùng bean name xuất hiện trong hai tài nguyên

```xml
<!-- a.xml -->
<bean id="paymentGateway" class="example.DefaultGateway"/>
```

```xml
<!-- b.xml -->
<bean id="paymentGateway" class="example.LegacyGateway"/>
```

Nếu root import cả hai, tên bean trùng. Tùy BeanFactory và cấu hình, Spring có thể từ chối hoặc cho phép override. Chính sách ở Spring Boot có thể khác plain Framework. **Không thiết kế chọn gateway theo thứ tự imports**.

### 20.2. Một tài nguyên bị import hai lần

```xml
<import resource="modules/gateway.xml"/>
<import resource="modules/gateway.xml"/>
```

Điều này có thể khiến metadata được xử lý nhiều lần. Không hiểu “import hai lần” là cách có hai bean độc lập: cùng `id` sẽ tranh cùng tên trong registry.

### Để cần hai implementations có chủ đích

Định nghĩa tên riêng:

```xml
<bean id="standardGateway" class="example.StandardGateway"/>
<bean id="fallbackGateway" class="example.FallbackGateway"/>
```

và chọn qua explicit ref/qualifier/registry logic. Tên riêng làm rõ rằng đây là **hai bean definitions**, không phải kết quả ngẫu nhiên của importing cùng file nhiều lần.

### Giữ quy tắc một nguồn sở hữu một bean name

Ở dự án nhiều nhóm, nên tài liệu hóa module nào sở hữu mỗi public bean name quan trọng. Khi refactor XML, chuyển definition cùng với tests và xóa/điều chỉnh import cũ tránh duplicate.

## 21. Import không định nghĩa thứ tự khởi tạo nghiệp vụ

Thứ tự khai báo:

```xml
<import resource="services.xml"/>
<import resource="repositories.xml"/>
```

không nên được dùng để yêu cầu “services khởi động trước repositories” hay ngược lại theo nghiệp vụ. Spring thường resolve constructor/property references theo dependency graph dù definitions đến từ files khác nhau.

Nếu một bean phải nhận repository ở constructor:

```xml
<bean id="service" class="example.Service">
    <constructor-arg ref="repository"/>
</bean>
```

BeanFactory biết service cần repository. Không cần đổi thứ tự XML imports chỉ để biểu diễn dependency này.

### Khi cần explicit ordering

`depends-on` hoặc `@DependsOn` có thể chỉ rõ những ràng buộc khởi tạo ngoài DI reference, nhưng không nên dùng như một workflow engine. Nếu yêu cầu là seed data, gọi remote API, start listeners hoặc migrations, hãy chọn lifecycle/startup coordination phù hợp (ví dụ startup coordinator hoặc SmartLifecycle) thay vì nhồi hành vi nghiệp vụ vào constructor/import.

### Vòng A ↔ B vẫn là vòng

Nếu repository phụ thuộc vào service, đồng thời service phụ thuộc repository, chuyển hai definitions vào các file khác nhau không phá dependency cycle. Cần sửa thiết kế ứng dụng.

## 22. Import và @ImportResource trong cấu hình Java

Hai annotation/cơ chế rất dễ nhầm:

| Công cụ | Nơi khai báo | Nhận gì? | Mục tiêu |
| --- | --- | --- | --- |
| XML `<import resource="modules/a.xml"/>` | Một XML `<beans>` file | Resource XML | Ghép XML vào XML |
| Java `@Import(InfraConfig.class)` | Class cấu hình Java | Configuration/component class | Ghép Java configs |
| Java `@ImportResource("classpath:legacy.xml")` | Class cấu hình Java | XML resource location | Nhập XML từ Java config |
| Java `@ComponentScan(...)` | Java config/component | Package/classes markers | Tìm stereotype bean candidates |

Nếu ứng dụng khởi động bằng Java configuration:

```java
@Configuration(proxyBeanMethods = false)
@ImportResource("classpath:config/root.xml")
public class AppConfig {
}
```

thì Spring nạp `config/root.xml`; từ đó, nếu file này có `<import resource="modules/services.xml"/>`, các imported XML modules cũng được xử lý theo cơ chế XML reader thông thường.

### ImportResource không tạo container phụ

`@ImportResource` và XML `<import>` đều đưa bean definitions vào cùng container mà class/configuration root được nạp. Nếu một Java `@Bean` method nhận dependency thuộc imported XML, có thể inject nó theo type/qualifier như bình thường.

### Chiều ngược XML-centric

Nếu XML là entry point chính, như ví dụ `ClassPathXmlApplicationContext("config/root.xml")`, bạn không cần `@ImportResource`. Đừng thêm Java annotation chỉ vì muốn Spring hiểu `<import>`; XML reader tự xử lý import tags.

### Khi nào nên chuyển sang Java?

Khi một XML chỉ còn vài bean definitions đơn giản, có thể cân nhắc `@Bean` methods vì IDE/type safety/refactor dễ hơn. Nhưng XML import vẫn hữu dụng cho legacy namespaces/configurations. Không có yêu cầu tất cả cấu hình phải được chuyển trong một lượt.

## 23. Chẩn đoán lỗi import theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| XML root tìm được nhưng module missing | `resource` sai relative path | Tính đường dẫn từ chính file đang import |
| `FileNotFoundException` trong JAR | Dùng source tree path hoặc resource không được package | Kiểm tra `src/main/resources`, target/classes và nội dung JAR |
| Đường dẫn `../` chỉ lỗi ở prod | Package/classpath layout khác IDE | Dùng relative trong module hoặc `classpath:` rõ ràng |
| Resource path bắt đầu slash nhưng không tìm như kỳ vọng | Nhầm relative leading slash là classpath root | Bỏ slash hoặc dùng `classpath:` |
| `BeanDefinitionStoreException` | Resource không đọc được, XML invalid, import cycle hoặc reader failure | Xem exception cause/resource trong stack trace |
| `SAXParseException` | XML malformed hoặc sai schema namespace | Kiểm tra XML syntax và XSD mapping |
| `CannotLoadBeanClassException` | Class trong `<bean class=...>` thiếu/sai | Kiểm tra runtime JAR và FQCN |
| `NoSuchBeanDefinitionException` | File module chưa import hoặc bean id/ref sai | Xem root imports và tên bean chính/alias |
| `NoUniqueBeanDefinitionException` | Nhiều beans cùng interface sau khi import | Dùng qualifier/primary, giảm duplicate candidates |
| Bean name collision | Hai files dùng cùng `id` | Đặt tên theo module/giải quyết override policy |
| Bean bị nạp hai lần | Import cùng file ở nhiều đường | Rà soát root composition và nested imports |
| Bean count khác mong đợi | Alias bị đếm sai hoặc wildcard nhập nhiều files | Kiểm tra `getBeanNamesForType` và actual resource set |
| `ClassCastException`/bean not required type | XML `ref` trỏ bean khác type | Sửa FQCN, ref, exposed proxy/interface |
| Constructor cycle | A cần B, B cần A qua `ref` | Sửa dependency design, không đảo thứ tự imports |
| Placeholder location không được resolve | Property chưa có lúc XML parse | Đưa setting vào Environment/system properties trước refresh |
| `classpath*:` nạp dư mô-đun | Trùng resource path trong nhiều JAR | Giới hạn resources cụ thể, test package |
| Lỗi chỉ xảy ra theo profile | Nhánh profile import thiếu hoặc thừa beans | Test từng active profile trước refresh |
| Test thành công nhưng app lỗi | Boot root/scan/import topology khác test | Test đúng root context thực và artifact runtime |

### Quy trình debug từng bước

1. Xác nhận **đúng root XML** mà Java đang tải.
2. Xem `<import resource="..."/>` trong root và xác định location trên runtime classpath/filesystem.
3. Với nested imports, lần theo từng file importer và relative path từ **file đó**.
4. Đọc root cause trong exception — file missing, XML parse, class loading, duplicate definition hay missing bean.
5. Mở từng XML độc lập để kiểm tra `<beans>`, namespaces, schema và class names.
6. Kiểm tra BeanFactory có các bean names expected bằng `containsBean`/`getBeanDefinitionNames`.
7. Xem cross-file `ref`/`property`/`constructor-arg` đúng bean name và type.
8. Kiểm tra profile/placeholder có được set **trước refresh**.
9. Kiểm tra import cycle, duplicate paths và wildcard resources.
10. Chạy integration test bằng đúng root/context và dependency versions của ứng dụng.

## 24. Kiểm thử cấu hình nhiều file

### Test khởi tạo một context

```java
try (var context =
        new ClassPathXmlApplicationContext("config/root.xml")) {
    if (!context.containsBean("catalogRepository")) {
        throw new AssertionError("Repository XML not imported");
    }
    if (!context.containsBean("catalogService")) {
        throw new AssertionError("Service XML not imported");
    }
    if (!context.containsBean("reportBoard")) {
        throw new AssertionError("Reporting XML not imported");
    }
}
```

Đây là **đoạn test minh họa** dùng code/types từ project mục 12. Dựng context thật tốt hơn chỉ kiểm tra từng file XML có tồn tại; file hợp lệ về syntax vẫn có thể chứa sai reference hoặc thiếu class.

### Test identity qua module

```java
CatalogRepository repository =
        context.getBean(CatalogRepository.class);
CatalogService service =
        context.getBean(CatalogService.class);
ReportBoard board =
        context.getBean(ReportBoard.class);

if (repository != service.repository()) {
    throw new AssertionError("Service uses a different repository");
}
if (service != board.service()) {
    throw new AssertionError("Board uses a different service");
}
```

Đoạn này cần chạy **bên trong block đang mở context** của ví dụ, không phải file Java độc lập. Nó xác nhận các beans được inject thực sự từ cùng BeanFactory.

### Test đường dẫn sau packaging

Một cấu hình chỉ hoạt động trong IDE chưa đủ. Hãy xác nhận file XML được Maven copy đúng dưới `target/classes/config/...` và nằm trong artifact JAR theo đường dẫn runtime:

```bash
jar tf target/spring-xml-import-demo-1.0-SNAPSHOT.jar
```

Lệnh này đọc artifact JAR mà Maven đã đóng gói; nếu chỉ chạy `compile` thì file JAR có thể chưa được tạo. Dùng:

```bash
mvn -q package
jar tf target/spring-xml-import-demo-1.0-SNAPSHOT.jar
```

Tìm paths `config/root.xml` và `config/modules/*.xml` trong danh sách. Mục đích là xác minh resource packaging, không phải thay đổi XML file.

### Test negative paths

Trong test resources riêng, có thể kiểm tra:

- Một import sai tên file phải làm context startup thất bại.
- Một bean `ref` sang module không được import phải lỗi.
- Hai bean definitions cùng tên bị phát hiện theo policy dự án.
- Profile dev/prod tải đúng modules.
- Không có vòng import A→B→A.
- Không có vòng constructor dependencies không được giải quyết.

Đừng cố dựa vào nguyên văn toàn bộ exception message: loại exception và wrapper stack có thể đổi theo Spring version. Hãy kiểm tra root cause và behavior quan trọng.

## 25. Hướng dẫn migration và tổ chức repository

Khi một dự án legacy đang có một XML lớn:

### Bước 1 — Lập danh sách beans và dependencies

Ghi nhận bean name, aliases, class, scope, ref dependencies, lifecycle, property placeholders và namespaces của từng bean. Chú ý những public bean names mà các consumer khác đang dùng.

### Bước 2 — Nhóm definitions theo ownership

Chia thành các files theo feature hoặc layer có ý nghĩa. Đừng thay đổi Java classes và XML wiring cùng lúc nếu không cần thiết; một thay đổi chỉ tái cấu trúc file thường dễ xác minh hơn.

### Bước 3 — Tạo root.xml

```xml
<import resource="modules/infrastructure.xml"/>
<import resource="modules/repositories.xml"/>
<import resource="modules/services.xml"/>
```

Root là nơi ứng dụng chọn modules cần dùng. Đừng để từng module import lẫn nhau chỉ để đáp ứng `ref`.

### Bước 4 — Bảo toàn bean-name contracts

Khi di chuyển `<bean id="accountRepository".../>` sang XML module khác, giữ `id="accountRepository"` nếu những consumers đang tham chiếu tên này. Nếu cần đổi tên, cân nhắc alias migration và kiểm thử.

### Bước 5 — Chỉ load một root

Đừng vừa nạp root mới vừa nạp những XML con riêng rẽ mà root đã import, tránh duplicate definitions.

### Bước 6 — Test context và hành vi chính

Khởi tạo từ đúng root; xác minh các dependencies, singleton identity, profiles, lifecycle và những output nghiệp vụ quan trọng. Dùng negative tests cho missing import/duplicate name.

### Bước 7 — Kiểm tra artifact deployment

Phải bảo đảm tài nguyên XML được copy vào JAR hoặc volume ngoài như cấu hình. Với file URLs, xác minh quyền đọc và tính ổn định của paths ở môi trường thực.

### Bước 8 — Nếu cần, chuyển dần sang Java configuration

Có thể dùng Java `@ImportResource` để tiếp tục nhập XML root; dần thay từng bean bằng `@Bean`/component scanning. Mỗi lần chuyển một definition, tránh để lại XML definition cùng tên nếu không có override policy thật sự. Không cần xóa mọi XML chỉ vì đã có Java config.

## 26. Bài tập có đáp án

### Bài 1 — Đường dẫn cùng thư mục

`root.xml` nằm ở `classpath:settings/root.xml` và `db.xml` ở `classpath:settings/db.xml`. Hãy viết import relative.

**Đáp án:**

```xml
<import resource="db.xml"/>
```

Đường dẫn được giải quyết tương đối với `root.xml`.

### Bài 2 — File trong thư mục con

`root.xml` ở `config/root.xml`, `inventory.xml` ở `config/modules/inventory.xml`.

**Đáp án:**

```xml
<import resource="modules/inventory.xml"/>
```

### Bài 3 — Đường dẫn classpath rõ ràng

Một module ở vị trí `config/shared/common.xml` phải được nạp bất kể root hiện nằm đâu.

**Đáp án:**

```xml
<import resource="classpath:config/shared/common.xml"/>
```

### Bài 4 — Slash đầu

`root.xml` nằm ở `config/root.xml`. Developer viết `<import resource="/modules/services.xml"/>` và cho rằng nó đi tới `classpath:/modules/services.xml`. Nhận định này chắc đúng không?

**Đáp án:** Không. Với relative XML import, tài liệu Spring giải thích leading slash bị bỏ qua. Nên viết `modules/services.xml` để đi tới `config/modules/services.xml` hoặc dùng `classpath:modules/services.xml` nếu thực sự muốn tài nguyên ở root classpath.

### Bài 5 — XML import có tạo context mới?

Một root có ba `<import>`. Có mấy BeanFactories khi chỉ có một `ClassPathXmlApplicationContext("root.xml")`?

**Đáp án:** Một BeanFactory trong một ApplicationContext (giả sử ứng dụng không tự dựng thêm contexts). Các files cung cấp bean definitions chung.

### Bài 6 — Ref giữa modules

`service.xml` khai báo bean `orderService` với `ref="orderRepository"`. Bean `orderRepository` nằm ở `repo.xml`. Có cần import `repo.xml` trực tiếp bên trong `service.xml` không?

**Đáp án:** Không nếu root đã nhập cả hai vào cùng context. `ref` được BeanFactory chung phân giải theo tên; không cần file service tự import file repo.

### Bài 7 — Số bean và alias

`repo.xml` khai báo `id="repo"` và alias `oldRepo`. Có thêm một bean independent không?

**Đáp án:** Không. Alias chỉ là tên thứ hai trỏ tới cùng bean definition; singleton reference từ hai tên là cùng object.

### Bài 8 — Duplicate import

Java tạo `new ClassPathXmlApplicationContext("root.xml","repo.xml")`, trong khi `root.xml` đã import `repo.xml`. Rủi ro gì?

**Đáp án:** Definition từ `repo.xml` bị đọc lặp, gây duplicate bean names/overriding phụ thuộc policy. Chỉ nạp root hoặc chọn danh sách leaf resources, tránh cả hai.

### Bài 9 — Missing resource

Trong root có `<import resource="does-not-exist.xml"/>`. Spring tự bỏ qua vì “optional feature” không?

**Đáp án:** Không. Import missing/parse invalid thường làm việc tạo context thất bại. Chọn root/profile phù hợp thay vì dựa vào optional import không có trong schema thông dụng.

### Bài 10 — File trong JAR

Sau đóng gói, `<import resource="src/main/resources/config/db.xml"/>` lỗi. Sửa như thế nào?

**Đáp án:** Nếu importer ở `config/root.xml` và target `config/db.xml`, dùng `resource="db.xml"`. Hoặc dùng `resource="classpath:config/db.xml"` để chỉ rõ runtime classpath.

### Bài 11 — import vòng và bean vòng

Hai XML imports không có cycle nhưng bean A constructor nhận B, B nhận A. Đổi thứ tự imports có sửa được không?

**Đáp án:** Không. Constructor dependency cycle là vấn đề đồ thị bean. Phải sửa hướng dependencies/abstraction, không phải thứ tự đọc XML.

### Bài 12 — Profiles

Root có `<beans profile="dev"><import resource="development.xml"/></beans>`. Khi nào cần đặt active profile `dev`?

**Đáp án:** Trước `context.refresh()`. Nếu dùng constructor tự refresh, phải cung cấp profile qua environment/system settings trước bootstrap hoặc dùng constructor chưa refresh rồi set profile và gọi `refresh()`.

### Bài 13 — classpath*: có phải “một file bất kỳ”?

`<import resource="classpath*:META-INF/spring/module.xml"/>` có thể tìm được nhiều files cùng tên ở nhiều JAR. Có nên dựa vào một file bất kỳ “được chọn đầu tiên” không?

**Đáp án:** Không. Ý nghĩa của `classpath*:` là tìm tất cả matching resources trong những ngữ cảnh hỗ trợ; resource ordering/collisions phải được kiểm thử và quản lý rõ.

### Bài 14 — @ImportResource khác @Import

Một Java `@Configuration` muốn import XML `legacy.xml`. Có dùng `@Import("legacy.xml")` không?

**Đáp án:** Không. Dùng `@ImportResource("classpath:legacy.xml")` cho XML resource; `@Import` dành cho class/configuration/component/selector/registrar theo API Spring.

### Bài 15 — Property placeholder ở import

XML muốn chọn file qua `resource="classpath:config/${module.file}"`. Configurer bean được khai báo trong chính file XML đó có chắc đã chạy trước khi import được resolve không?

**Đáp án:** Không. Import location được resolve trong lúc XML definitions đang được đọc, còn BeanFactory post-processors có thể chạy sau. Cung cấp property ở Environment/system properties trước bootstrap.

### Bài 16 — Tạo một module mới

Có root `config/root.xml`, module mới `config/modules/payments.xml`. Muốn root sử dụng module mới cần làm gì?

**Đáp án:** Đặt `payments.xml` đúng runtime resources, bổ sung `<import resource="modules/payments.xml"/>` trong root, đảm bảo XML hợp lệ, bean names không xung đột, dependencies được resolve và integration tests pass.

## 27. Checklist kiểm tra trước khi triển khai

- [ ] XML root có `<beans>` và schema hợp lệ.
- [ ] Mỗi imported file cũng là Spring XML hợp lệ với namespaces cần thiết.
- [ ] Mọi `<import resource="..."/>` được resolve từ đúng file importer hoặc dùng prefix `classpath:`/`file:` rõ.
- [ ] Không dùng `src/main/resources` làm runtime resource path.
- [ ] Không mặc định leading slash trong relative import nghĩa là classpath root.
- [ ] Tránh `../` đặc biệt với classpath-relative locations.
- [ ] Không import cùng XML nhiều lần qua root và bootstrap locations.
- [ ] Không có XML import cycles.
- [ ] Bean names/aliases không xung đột ngoài ý định.
- [ ] Cross-file `ref`, `constructor-arg` và `property` trỏ đúng managed beans/type.
- [ ] Không dựa vào import order để biểu diễn thứ tự business initialization.
- [ ] Không có constructor dependency cycles ở tầng bean.
- [ ] Profiles/property placeholders được set trước khi đọc imports.
- [ ] Optional features được lựa chọn bằng root/profile/bootstrap logic, không giả định import silently skipped.
- [ ] Mọi bean classes và namespace handlers có trong runtime dependencies.
- [ ] Tài nguyên ngoài JAR được quyền đọc và nằm ở path deployment xác định.
- [ ] Wildcard patterns chỉ dùng khi chủ đích là load toàn bộ matches.
- [ ] Integration tests mở đúng root ApplicationContext.
- [ ] Artifact JAR có các XML resources theo paths đã định.
- [ ] Lifecycle và singleton/prototype scopes còn đúng sau modularization.
- [ ] Không tạo ApplicationContext thứ hai chỉ để lấy bean của một XML module.
- [ ] Khi migrate Java configuration, dùng `@ImportResource` đúng trường hợp và loại definitions bị trùng.

## Tổng kết

`<import resource="..."/>` là cách chuẩn để **ghép các tài nguyên Spring XML thành một cấu hình logic**. Nó tải và đăng ký bean definitions từ XML khác, vẫn trong **cùng ApplicationContext/BeanFactory**, cho phép dependencies, scopes, aliases và lifecycle hoạt động xuyên file.

Hai điều dễ nhớ nhất:

- **Relative import** được giải quyết từ **file XML đang thực hiện import**.
- **`classpath:` / `file:`** cho biết resource location cụ thể khi muốn tránh phụ thuộc vào relative layout.

Thiết kế tốt cần một root composition dễ hiểu, module ownership rõ, không import chéo thành vòng, không có duplicate bean names và có integration test từ root thật. Khi dùng Java-centric configuration, `@ImportResource` có thể nạp toàn bộ root XML đó mà không cần tạo container phụ. XML import giúp tổ chức definitions; nó **không** thay thế cho DI, không tự chạy nghiệp vụ và không giải quyết các bean dependency cycles.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Container Overview, Composing XML-based Configuration Metadata](https://docs.spring.io/spring-framework/reference/6.2/core/beans/basics.html): `<import>`, relative resource paths, leading slash và tránh `../`.
- [Spring Framework 6.2 — Resources](https://docs.spring.io/spring-framework/reference/6.2/core/resources.html): `Resource`, `classpath:`, `file:`, `classpath*:` và application-context resource paths.
- [Spring Framework 6.2 — Composing Java-based Configurations](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/composing-configuration-classes.html): `@Import` và `@ImportResource` khi kết hợp Java/XML.
- [Spring Framework 6.2 — XML Bean Definition Basics](https://docs.spring.io/spring-framework/reference/6.2/core/beans/basics.html): `<beans>`, bean name, class metadata và import resources.
- [Spring Framework 6.2 — Bean Scopes](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html): singleton/prototype scopes xuyên definitions.
- [Spring Framework 6.2 — Dependency Injection](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-collaborators.html): constructor/property wiring và circular dependencies.
