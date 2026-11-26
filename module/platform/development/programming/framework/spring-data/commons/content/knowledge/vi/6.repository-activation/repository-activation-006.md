# XML namespace khi duy trì hệ thống cấu hình cũ

Trong một hệ thống Spring sử dụng lâu năm, repository có thể được kích hoạt bằng XML thay vì annotation `@Enable...Repositories`. Khi bảo trì, cần đọc đúng namespace, phạm vi quét, tham chiếu bean và cách tài nguyên XML được nạp vào application context.

XML là một cách khai báo cấu hình. Nó vẫn phải kết nối repository với module store, mapping và hạ tầng dữ liệu phù hợp. Spring Data Commons cung cấp phần hạ tầng dùng chung; các phần tử như `jpa:repositories` hoặc `mongo:repositories` do module tích hợp tương ứng xử lý.

Bài học thuộc chương **Kích hoạt repository**, tập trung vào việc duy trì cấu hình XML có thể giải thích và kiểm tra được, đồng thời chuẩn bị cho trường hợp XML và Java configuration cùng tồn tại.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Đọc quan hệ giữa prefix, namespace URI và XSD trong một file Spring XML.
- Giải thích cách phần tử repository của store tạo bean từ interface.
- Xác định tài nguyên XML có thực sự được nạp và các bean tham chiếu có nhìn thấy nhau không.
- Cấu hình phạm vi repository cùng entity manager factory, transaction manager hoặc MongoTemplate phù hợp.
- Chẩn đoán lỗi namespace, schema, thiếu bean và quét trùng.
- Chuyển một nhóm repository sang Java configuration mà vẫn giữ rõ quyền sở hữu cấu hình.

## 2. XML namespace tham gia kích hoạt repository như thế nào?

Một luồng xử lý khái quát:

```text
Application context nạp tài nguyên XML
    -> XML parser đọc namespace và schema
    -> Spring tìm bộ xử lý namespace của module
    -> phần tử repositories được xử lý
    -> xác định package và candidate repository
    -> đăng ký bean definition/factory tương ứng
    -> gắn với hạ tầng dữ liệu
    -> tạo proxy repository
```

Một file XML có mặt trong thư mục tài nguyên chưa có nghĩa mọi cách khởi chạy ứng dụng sẽ tự nạp nó. Cũng không phải cứ khai báo namespace là repository đã được kích hoạt: phải có phần tử cấu hình tương ứng được xử lý trong context.

Tương tự annotation, việc đăng ký repository và việc sử dụng kết nối thật có thể xảy ra ở những thời điểm khác nhau tùy cách khởi tạo. Context nạp được XML chưa chứng minh mọi truy vấn, projection hoặc thao tác ghi đã hoạt động.

## 3. Phân biệt prefix, namespace URI và địa chỉ schema

Xét phần đầu của một tài nguyên cấu hình JPA:

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:jpa="http://www.springframework.org/schema/data/jpa"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/data/jpa
           https://www.springframework.org/schema/data/jpa/spring-jpa.xsd">

    <jpa:repositories base-package="example.customer.jpa" />

</beans>
```

Ba phần có vai trò khác nhau:

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Prefix | `jpa` | Tên viết tắt dùng trong tài liệu XML |
| Namespace URI | `http://www.springframework.org/schema/data/jpa` | Định danh bộ từ vựng mà phần tử thuộc về |
| Schema location | Địa chỉ kết thúc bằng `spring-jpa.xsd` | Chỉ vị trí schema dùng để mô tả và kiểm tra cấu trúc |

Prefix do tài liệu lựa chọn. Có thể đổi `jpa` thành một prefix khác nếu đổi nhất quán; bộ xử lý vẫn được xác định theo namespace URI.

Trong `xsi:schemaLocation`, dữ liệu được ghi theo từng cặp:

```text
namespace URI thứ nhất    schema location thứ nhất
namespace URI thứ hai     schema location thứ hai
```

Không ghép URI JPA với XSD MongoDB. Cũng không đổi tùy ý namespace URI từ `http` sang `https` chỉ vì địa chỉ XSD dùng `https`. Namespace là định danh cần khớp với mapping mà module hỗ trợ.

### 3.1. Khai báo schema không tải dependency Java

Viết namespace JPA trong XML không tải `spring-data-jpa` vào classpath. Dự án vẫn phải khai báo module và bộ thư viện tương thích qua công cụ build.

Một XSD mô tả phần tử hoặc thuộc tính không tự thêm implementation Java cho tính năng đó. Thay URL schema sang một bản khác không thay thế nâng cấp dependency.

### 3.2. Schema có thể được phân giải từ classpath

Các JAR Spring sử dụng những tài nguyên như `META-INF/spring.handlers` và `META-INF/spring.schemas` để ánh xạ namespace handler và schema tương ứng.

Với mapping thích hợp, Spring có thể sử dụng schema đóng gói trong dependency, thay vì bắt buộc tải lại XSD từ Internet mỗi lần khởi động. IDE có thể có cơ chế phân giải hoặc cache riêng, nên việc IDE không gạch đỏ chưa chứng minh runtime có đủ namespace handler.

Khi giữ một hệ thống chạy trong môi trường hạn chế mạng, cần kiểm tra bộ JAR và cách đóng gói có giữ đúng các tài nguyên này hay không. Việc truy cập được một URL XSD từ trình duyệt cũng chưa giải quyết được trường hợp module xử lý namespace đang thiếu ở runtime.

## 4. Mẫu kích hoạt repository JPA bằng XML

Giả sử ứng dụng có:

- `CustomerEntity` được mapping theo JPA.
- `CustomerRepository` thuộc package `example.customer.jpa`.
- Bean `customerEntityManagerFactory` quản lý entity tương ứng.
- Bean `customerTransactionManager` phù hợp với factory đó.

Repository minh họa:

```java
package example.customer.jpa;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
        extends JpaRepository<CustomerEntity, Long> {

    Optional<CustomerEntity> findByEmail(String email);
}
```

Tài nguyên XML kích hoạt:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:jpa="http://www.springframework.org/schema/data/jpa"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/data/jpa
           https://www.springframework.org/schema/data/jpa/spring-jpa.xsd">

    <jpa:repositories
            base-package="example.customer.jpa"
            entity-manager-factory-ref="customerEntityManagerFactory"
            transaction-manager-ref="customerTransactionManager" />

</beans>
```

Đoạn XML này hoàn chỉnh về cấu trúc tài liệu, nhưng phụ thuộc các bean hạ tầng đã nêu. Những bean đó phải được khai báo trong cùng context, được import hoặc có thể nhìn thấy qua quan hệ context phù hợp.

### 4.1. `base-package` xác định nơi tìm interface

`base-package` giới hạn phạm vi repository scan. Nên chọn package có ranh giới rõ, thay vì quét toàn bộ ứng dụng khi chỉ cần một nhóm repository.

Đây là chuỗi package, không phải một bean ID và cũng không phải đường dẫn file XML. Khi refactor package Java, cần kiểm tra lại giá trị XML vì tham chiếu dạng chuỗi có thể không được cập nhật như tham chiếu kiểu trong Java.

Phạm vi repository scan không tự xác định tất cả entity mà entity manager factory quản lý. Hai việc này liên quan nhưng riêng biệt.

### 4.2. Các thuộc tính `*-ref` là tham chiếu bean

`entity-manager-factory-ref` cần trỏ tới bean entity manager factory thích hợp, không phải tên datasource. `transaction-manager-ref` cần trỏ tới transaction manager mà repository sử dụng theo cấu hình.

Tài nguyên XML không cần nằm cùng file với mọi bean nó tham chiếu, nhưng các bean phải nằm trong phạm vi nhìn thấy được khi context tạo chúng.

Trong ứng dụng chỉ có một bộ hạ tầng theo tên mặc định của module, có thể không cần đặt mọi tham chiếu tường minh. Khi bảo trì nhiều nguồn dữ liệu hoặc các tên riêng, khai báo rõ giúp giảm việc suy đoán.

## 5. Đọc phần hạ tầng JPA tách khỏi phần repository

Một phần cấu hình hạ tầng có thể được tổ chức như sau, với datasource đã được cung cấp từ cấu hình môi trường:

```xml
<bean id="customerEntityManagerFactory"
      class="org.springframework.orm.jpa.LocalContainerEntityManagerFactoryBean">
    <property name="dataSource" ref="customerDataSource" />
    <property name="packagesToScan" value="example.customer.jpa" />
    <property name="jpaVendorAdapter">
        <bean class="org.springframework.orm.jpa.vendor.HibernateJpaVendorAdapter" />
    </property>
</bean>

<bean id="customerTransactionManager"
      class="org.springframework.orm.jpa.JpaTransactionManager">
    <property name="entityManagerFactory"
              ref="customerEntityManagerFactory" />
</bean>
```

Đây là fragment đặt bên trong một tài liệu `beans` phù hợp. Nó minh họa quan hệ bean, giả định provider Hibernate và bộ JPA tương thích đã được chọn. Nó chưa định nghĩa `customerDataSource`, driver, migration hoặc toàn bộ thuộc tính provider của ứng dụng.

Cần phân biệt ba tên và vai trò:

```text
customerDataSource
    -> cung cấp truy cập cơ sở dữ liệu quan hệ

customerEntityManagerFactory
    -> tạo hạ tầng quản lý entity JPA dựa trên datasource và mapping

customerTransactionManager
    -> điều phối giao dịch JPA tương ứng
```

`LocalContainerEntityManagerFactoryBean` là một Spring `FactoryBean`; tham chiếu thông thường tới ID của bean cung cấp đối tượng factory JPA mà nó tạo. Không cần tùy ý thêm ký tự tham chiếu đến chính `FactoryBean` khi cấu hình repository.

Nếu báo entity không được quản lý, hãy kiểm tra `packagesToScan`, metadata entity và factory thật sự gắn với repository. Tăng phạm vi `jpa:repositories` không thay thế việc sửa managed type của factory.

### 5.1. Giao dịch ở service là một phần cấu hình khác

Một hệ thống có service dùng annotation giao dịch có thể cần phần cấu hình tương ứng, chẳng hạn:

```xml
<tx:annotation-driven
        transaction-manager="customerTransactionManager" />
```

Fragment này yêu cầu khai báo namespace `tx` và schema của nó trong tài liệu:

```text
xmlns:tx="http://www.springframework.org/schema/tx"

Cặp schemaLocation:
http://www.springframework.org/schema/tx
https://www.springframework.org/schema/tx/spring-tx.xsd
```

Bật xử lý annotation giao dịch trên service khác với bật repository scan. Service cũng phải được đăng ký thành bean và lời gọi cần đi qua cơ chế giao dịch phù hợp.

Không suy ra mọi tài nguyên trong cùng context đều tự chung một giao dịch. Khi có nhiều transaction manager, phải chỉ rõ ranh giới và tài nguyên tham gia theo thiết kế.

## 6. Mẫu namespace MongoDB

Với MongoDB, dùng namespace của module MongoDB, không dùng phần tử JPA cho document repository.

Giả sử có `CustomerDocument`, `MongoCustomerRepository` và bean `customerMongoTemplate` phù hợp:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:mongo="http://www.springframework.org/schema/data/mongo"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/data/mongo
           https://www.springframework.org/schema/data/mongo/spring-mongo.xsd">

    <mongo:repositories
            base-package="example.customer.mongo"
            mongo-template-ref="customerMongoTemplate" />

</beans>
```

`mongo-template-ref` trỏ tới hạ tầng thao tác MongoDB phù hợp, không chỉ là tên client kết nối. Template phải được cấu hình với client/database và mapping mà nhóm repository cần sử dụng.

Repository ví dụ:

```java
package example.customer.mongo;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface MongoCustomerRepository
        extends MongoRepository<CustomerDocument, String> {
}
```

Ví dụ giả định `CustomerDocument` có metadata MongoDB phù hợp với ID kiểu `String`. Nó không đòi hỏi document dùng cùng kiểu ID hoặc vòng đời đối tượng với entity JPA.

### 6.1. Giữ lại ý nghĩa thay vì sao chép cú pháp giữa store

Các phần tử đều có ý nghĩa “bật repository”, nhưng tham chiếu hạ tầng khác nhau:

| JPA | MongoDB |
| --- | --- |
| `jpa:repositories` | `mongo:repositories` |
| `entity-manager-factory-ref` | `mongo-template-ref` |
| Entity manager factory và mapping JPA | Template cùng mapping document |
| Transaction manager JPA khi áp dụng | Cơ chế giao dịch MongoDB khi cấu hình và môi trường hỗ trợ |

Không chép thuộc tính JPA sang phần tử MongoDB. Tương tự, không suy ra mọi tính năng annotation mới đều có một phần tử XML tương ứng trong mọi module và phiên bản.

Khi cần reactive repository hoặc một khả năng bổ sung, kiểm tra module đang dùng có hỗ trợ cấu hình XML tương ứng không. Không tự suy ra tên phần tử bằng cách đổi tên annotation sang chữ thường.

## 7. File XML phải được nạp vào đúng application context

### 7.1. Nạp trực tiếp trong ứng dụng Spring thuần

Một cách khởi tạo context là:

```java
import org.springframework.context.support.ClassPathXmlApplicationContext;

public class LegacyApplication {
    public static void main(String[] args) {
        try (ClassPathXmlApplicationContext context =
                     new ClassPathXmlApplicationContext(
                             "legacy/customer-repositories.xml")) {
            // Lấy bean hoặc khởi chạy thành phần của ứng dụng tại đây.
        }
    }
}
```

Tài nguyên được nạp phải cung cấp hoặc import các dependency cần thiết. Các tên tài nguyên trong bài là ví dụ bố trí cấu hình; chúng không đại diện cho file đã có sẵn trong một dự án cụ thể.

Một tài nguyên có thể import phần hạ tầng:

```xml
<import resource="classpath:/legacy/customer-infrastructure.xml" />
```

Việc tách file giúp nhìn rõ trách nhiệm, nhưng không thay đổi yêu cầu các bean phải được nạp và tham chiếu đúng. Một vòng import hoặc nhiều nhánh import chồng cần được điều tra thay vì thêm ngẫu nhiên một bản sao cấu hình.

### 7.2. Nạp từ Java configuration

Có thể giữ XML và đưa nó vào một context được cấu hình bằng Java:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportResource;

@Configuration
@ImportResource("classpath:/legacy/customer-repositories.xml")
public class LegacyRepositoriesImport {
}
```

Lớp `LegacyRepositoriesImport` cũng phải được context biết đến qua scan, import hoặc đăng ký tường minh. Annotation nằm trong một lớp chưa bao giờ được nạp sẽ không có tác dụng.

Trong ứng dụng Boot, cách này cho phép giữ một phần cấu hình cũ trong khi phần còn lại dùng auto-configuration hoặc Java configuration. Cần kiểm tra điều kiện auto-configuration của module và tránh để nhiều cơ chế cùng đăng ký một nhóm repository ngoài ý muốn.

### 7.3. Hệ thống web cũ có thể có context cha và con

Một số ứng dụng Spring MVC truyền thống có root context và context riêng của servlet. Bean ở context con có thể nhìn thấy bean phù hợp ở context cha; chiều nhìn thấy ngược lại không được mặc định.

Nếu repository được đặt ở context con nhưng service ở root context cần inject nó, ứng dụng có thể không tìm thấy bean theo cấu trúc đó.

Nếu cùng tài nguyên repository bị nạp cả ở cha lẫn con, có thể tạo ra hai tập bean hoặc hành vi che khuất khiến việc chẩn đoán khó hơn. Hãy xác định nơi sở hữu cấu hình dữ liệu trước khi sửa phạm vi scan.

## 8. Component scan, mapping và repository scan là ba câu hỏi riêng

Một file XML có thể có cả `context:component-scan` và `jpa:repositories`, nhưng chúng không thay thế nhau.

| Cơ chế | Câu hỏi được giải quyết |
| --- | --- |
| Component scan | Những component, service hoặc lớp cấu hình nào cần đăng ký? |
| Repository scan | Interface nào cần repository factory tạo implementation/proxy? |
| Mapping của store | Những kiểu persistence nào được quản lý và biểu diễn ra sao? |

Thêm `@Repository` lên interface không tự làm component scanner tạo được implementation như repository factory của module.

Ngược lại, repository đã được tìm thấy vẫn có thể không tạo được vì thiếu factory, template hoặc mapping. Cần xác định lỗi xuất hiện ở bước nào thay vì mở rộng mọi loại scan cùng lúc.

Các base interface generic dùng để kế thừa cần được phân loại phù hợp, thường bằng `@NoRepositoryBean`. XML không làm mất nhu cầu này chỉ vì cơ chế kích hoạt khác annotation.

## 9. Nhiều nhóm repository và nhiều nguồn dữ liệu

Khi duy trì XML có nhiều datasource, nên làm rõ quan hệ từng nhóm. Ví dụ JPA:

```xml
<jpa:repositories
        base-package="example.sales.repository"
        entity-manager-factory-ref="salesEntityManagerFactory"
        transaction-manager-ref="salesTransactionManager" />

<jpa:repositories
        base-package="example.audit.repository"
        entity-manager-factory-ref="auditEntityManagerFactory"
        transaction-manager-ref="auditTransactionManager" />
```

Hai nhóm cần các bean hạ tầng và managed type tương ứng. Không quét chồng package của chúng trừ khi thiết kế thật sự yêu cầu và module hỗ trợ cách phân loại đó.

Với MongoDB:

```xml
<mongo:repositories
        base-package="example.catalog.mongo"
        mongo-template-ref="catalogMongoTemplate" />

<mongo:repositories
        base-package="example.archive.mongo"
        mongo-template-ref="archiveMongoTemplate" />
```

Các fragment phải được đặt trong tài liệu có namespace phù hợp. Nếu cả JPA và MongoDB cùng xuất hiện, khai báo cả hai namespace cùng cặp schema tương ứng.

Điều quan trọng là package, bean đích và mapping phải đồng bộ. Có hai template không đủ nếu cả hai nhóm repository vô tình trỏ vào cùng một template.

### 9.1. Tên bean và alias cần được đọc cẩn thận

Một hệ thống cũ có thể dùng alias để giữ tương thích tên bean sau khi đổi cấu hình. Hãy theo dõi alias tới bean thật, không suy ra vai trò chỉ từ tên ở một file.

Thay tên bean tham chiếu có thể làm repository sử dụng nguồn dữ liệu khác ngay cả khi interface và query không đổi. Đây là thay đổi hành vi cần được kiểm tra bằng dữ liệu hoặc kết nối phân biệt được.

`@Qualifier` ở service chỉ chọn bean để inject; nó không sửa một repository đã được tạo bằng sai factory hoặc template.

## 10. Quản lý schema và dependency khi nâng cấp hệ thống cũ

XML có hai lớp tương thích cần xem:

1. Cú pháp và thuộc tính mà schema/module hỗ trợ.
2. Các lớp Java, API provider, driver và hành vi mà cấu hình đang tạo.

Một XML được parse thành công chưa chứng minh các constructor, property hoặc API được tham chiếu vẫn phù hợp với dependency mới.

### 10.1. Không dùng số phiên bản trong XSD để thay cho version dependency

Các ví dụ trong bài dùng địa chỉ schema không gắn số phiên bản. Khi áp dụng, phải xác nhận địa chỉ đó được bộ dependency đang dùng hỗ trợ và phân giải đúng.

Nếu tài liệu cũ ghim một XSD có số phiên bản, hãy xem lý do, mapping và yêu cầu nâng cấp trước khi thay. Chỉ đổi URL schema không tự nâng được Spring Data hoặc khôi phục một API Java đã thay đổi.

### 10.2. Namespace XML không quyết định namespace của entity Java

Một file vẫn dùng namespace Spring Data JPA trong XML không có nghĩa entity Java có thể trộn tùy ý API `javax.persistence` và `jakarta.persistence`.

Khi đi qua một lần nâng cấp nền tảng có thay đổi namespace persistence, phải đồng bộ entity, provider, Spring Framework và module theo bộ tương thích. XSD không chuyển đổi tên kiểu Java trong bytecode.

### 10.3. Kiểm tra các phần tử cũ theo đúng module

Một số cấu hình client, converter, index, auditing hoặc thuộc tính repository có thể thay đổi qua các dòng phát hành. Đừng áp dụng nhận định “XML cũ luôn chạy nguyên trạng” hoặc “mọi XML đều phải bỏ” cho toàn bộ hệ thống.

Đánh giá từng cấu hình theo khả năng module đang sử dụng. Nếu một tính năng không còn có cách cấu hình XML phù hợp, có thể chuyển riêng phần đó sang Java configuration trong khi giữ những phần còn lại.

## 11. Tránh kích hoạt trùng khi XML và annotation cùng tồn tại

Một tình huống thường gặp:

```text
XML:
    jpa:repositories quét example.customer.jpa

Java:
    @EnableJpaRepositories cũng quét example.customer.jpa
```

Tùy cách đăng ký và điều kiện của framework, có thể phát sinh xung đột tên bean, nhiều bean hoặc hành vi khác ngoài dự kiến. Với Boot, điều kiện auto-configuration còn tham gia quyết định, nên cần xem cấu hình thật sự được áp dụng.

Không mặc định bật bean overriding là cách giải quyết đúng. Nếu bean cuối cùng ghi đè bean trước, hệ thống có thể khởi động nhưng không còn dùng factory hoặc template mong muốn.

Một bảng quyền sở hữu cấu hình giúp việc bảo trì rõ hơn:

| Nhóm repository | Cơ chế đăng ký | Phạm vi | Hạ tầng đích |
| --- | --- | --- | --- |
| Khách hàng JPA | XML | `example.customer.jpa` | Factory và transaction manager khách hàng |
| Danh mục MongoDB | Java configuration | `example.catalog.mongo` | Template danh mục |

Mỗi nhóm cần có nguồn cấu hình chịu trách nhiệm rõ ràng. Không yêu cầu cả hệ thống chỉ được có một phong cách, nhưng phải tránh một nhóm bị nhiều nơi đăng ký ngoài ý muốn.

## 12. Chuyển từng phần sang Java configuration

Khi có nhu cầu chuyển đổi, hãy ánh xạ ý nghĩa của XML sang cấu hình mới thay vì chỉ xóa file cũ rồi thêm annotation.

Ví dụ tương ứng cho JPA:

| XML | Java configuration |
| --- | --- |
| `jpa:repositories` | `@EnableJpaRepositories` |
| `base-package` | `basePackages` hoặc ranh giới tương đương bằng `basePackageClasses` |
| `entity-manager-factory-ref` | `entityManagerFactoryRef` |
| `transaction-manager-ref` | `transactionManagerRef` |

Ví dụ tương ứng cho MongoDB:

| XML | Java configuration |
| --- | --- |
| `mongo:repositories` | `@EnableMongoRepositories` |
| `base-package` | `basePackages` hoặc ranh giới tương đương |
| `mongo-template-ref` | `mongoTemplateRef` |

Một quy trình chuyển đổi có thể là:

1. Ghi lại package, filter, bean tham chiếu và tùy chọn đang có hiệu lực.
2. Xác định tài nguyên XML được nạp từ những đường nào và ở context nào.
3. Tạo cấu hình mới cho đúng một nhóm repository với cùng ý nghĩa.
4. Chuyển quyền đăng ký nhóm đó sang cấu hình mới, tránh để hai cơ chế đồng thời sở hữu cùng phạm vi.
5. Giữ hoặc chuyển tiếp các bean hạ tầng theo quyết định riêng, không vô tình bỏ mất mapping hoặc giao dịch.
6. Kiểm tra lại nguồn dữ liệu, truy vấn và các đường nghiệp vụ liên quan.

Việc chuyển phần repository sang annotation không bắt buộc chuyển toàn bộ datasource, transaction manager và service trong cùng một lần. Chia theo ranh giới có thể kiểm tra giúp giảm số thay đổi đồng thời.

## 13. Chẩn đoán các lỗi thường gặp

| Triệu chứng | Nhóm nguyên nhân cần kiểm tra |
| --- | --- |
| Không tìm được `NamespaceHandler` | Sai namespace URI, thiếu module hoặc tài nguyên mapping namespace không được đóng gói đúng |
| XML không chấp nhận một phần tử/thuộc tính | Ghép sai schema, thuộc tính không thuộc module hoặc không được phiên bản hỗ trợ |
| Không có bean repository | XML chưa được nạp, sai package, interface không phải candidate hoặc bị loại |
| Thiếu bean factory/template tham chiếu | Sai bean ID, thiếu import hoặc không nhìn thấy bean qua cấu trúc context |
| Entity không được quản lý | Mapping của factory không chứa đúng kiểu entity |
| Bean name đã được đăng ký | Phạm vi quét chồng, import cấu hình lặp hoặc nguồn kích hoạt khác cùng tham gia |
| Có bean nhưng đọc nhầm dữ liệu | Tham chiếu sai factory/template hoặc alias trỏ sai nguồn |
| Query creation thất bại | Tên thuộc tính, toán tử, kiểu trả về hoặc query khai báo không hợp lệ |
| Khởi tạo hạ tầng lỗi sau nâng cấp | Constructor, property, provider hoặc driver không còn phù hợp bộ dependency |

### 13.1. Tách lỗi parse khỏi lỗi tạo bean

Một `SAXParseException` thường hướng điều tra về cấu trúc XML hoặc schema. Lỗi tạo bean sau khi parse có thể liên quan đến classpath, tham chiếu bean hoặc cấu hình tài nguyên.

Nếu XML đã parse nhưng thiếu `customerEntityManagerFactory`, tải lại XSD thường không giải quyết được nguyên nhân. Nếu parser không hiểu `jpa:repositories`, đổi tên datasource cũng không sửa đúng tầng lỗi.

### 13.2. Đọc toàn bộ chuỗi nguyên nhân

Thông báo không inject được service có thể xuất phát từ repository tạo thất bại; repository lại có thể thất bại do mapping hoặc query. Cần đi tới nguyên nhân sâu nhất có ý nghĩa thay vì chỉ xử lý tên bean ở thông báo ngoài cùng.

Với hệ thống nhiều file XML, đồng thời kiểm tra đường import và context sở hữu từng bean. Hai file đều đúng riêng lẻ vẫn có thể được nạp vào hai context không có quan hệ nhìn thấy cần thiết.

## 14. Kiểm tra một thay đổi XML có ý nghĩa

Một thay đổi chỉ sửa vài thuộc tính XML vẫn có thể đổi nơi đọc/ghi dữ liệu. Những kiểm tra nên gắn với tác động thực tế:

- Nạp context theo đúng đường khởi động mà ứng dụng dùng.
- Xác nhận repository cần thiết được tạo và inject.
- Xác nhận repository gắn đúng factory hoặc template.
- Thực hiện một thao tác đọc/ghi phù hợp và một truy vấn đặc trưng nếu có.
- Kiểm tra ranh giới giao dịch nếu thay transaction manager hoặc cấu hình proxy service.
- Với nhiều nguồn, dùng dữ liệu phân biệt được để phát hiện truy cập nhầm.

Mock repository không kiểm tra được XML namespace handler hay việc tạo factory. Ngược lại, chỉ xác nhận context khởi động không chứng minh CRUD, derived query, projection hoặc auditing đã chạy đúng đường mong muốn.

Nếu thay cách đóng gói hoặc dependency, cần kiểm tra trên artifact triển khai thực tế. Một lần chạy từ IDE có thể có classpath và cách phân giải tài nguyên khác với gói đưa lên môi trường.

## 15. Tình huống thực hành

Một hệ thống có `customer-repositories.xml` khai báo `jpa:repositories`, được nạp ở root context. Nhóm thêm một lớp Java có `@EnableJpaRepositories` quét cùng package để “bổ sung cấu hình mới”. Sau đó xuất hiện lỗi trùng bean hoặc repository có nguồn đăng ký khó xác định.

Cách xử lý có căn cứ:

1. Tìm hai nguồn đăng ký đang cùng chịu trách nhiệm cho package khách hàng.
2. Đối chiếu factory và transaction manager của từng nguồn.
3. Quyết định giữ XML hay chuyển nhóm này sang Java configuration.
4. Bảo đảm chỉ nguồn được chọn đăng ký nhóm repository đó trong thiết kế mới.
5. Xác nhận các bean hạ tầng cũ còn cần thiết vẫn được nạp.
6. Thực hiện lại thao tác dữ liệu để kiểm tra nguồn đích và hành vi giao dịch.

Nếu chỉ bật bean overriding, lỗi đăng ký có thể biến mất nhưng quyết định cấu hình vẫn mơ hồ. Mục tiêu bảo trì là biết bean được tạo từ đâu và sử dụng tài nguyên nào.

## 16. Câu hỏi tự kiểm tra

### Câu 1

Đổi prefix `jpa` thành `customerData` có làm chuyển repository sang một store khác không?

**Gợi ý trả lời:** Không, nếu namespace URI vẫn giữ đúng và prefix được đổi nhất quán. URI mới là định danh bộ từ vựng; prefix là tên viết tắt trong tài liệu.

### Câu 2

Khai báo XSD Spring Data JPA có tự tải dependency JPA cho ứng dụng không?

**Gợi ý trả lời:** Không. Dependency phải được cung cấp qua build/runtime classpath. Schema không thay thế module và namespace handler Java.

### Câu 3

Vì sao repository scan đúng vẫn có thể gặp lỗi entity không được quản lý?

**Gợi ý trả lời:** Phạm vi repository và mapping entity manager factory là hai cấu hình riêng. Factory mà repository dùng phải biết domain tương ứng.

### Câu 4

Hai file XML khai báo đúng bean nhưng service vẫn không inject được repository. Ngoài tên bean cần xem gì?

**Gợi ý trả lời:** Xem file có được nạp không, đường import, context cha/con và khả năng nhìn thấy bean giữa các context.

### Câu 5

Có thể giữ datasource trong XML nhưng chuyển kích hoạt repository sang Java configuration không?

**Gợi ý trả lời:** Có thể, nếu cấu hình mới tham chiếu đúng bean và có ranh giới đăng ký rõ. Không cần chuyển mọi phần cấu hình trong một lần.

### Câu 6

Một tài liệu XML parse thành công có đủ chứng minh derived query và auditing hoạt động không?

**Gợi ý trả lời:** Chưa đủ. Cần tạo và sử dụng repository, đồng thời có cấu hình và đường thực thi phù hợp cho từng tính năng.

### Câu 7

Tại sao không nên xử lý quét trùng chỉ bằng cách cho phép ghi đè bean?

**Gợi ý trả lời:** Ghi đè có thể che nguồn cấu hình và làm bean cuối dùng sai hạ tầng. Cần xác định nguồn sở hữu package repository và giữ quan hệ tài nguyên rõ ràng.