# Phân loại repository theo giao diện cơ sở đặc thù store

Khi một ứng dụng có nhiều module Spring Data, việc tìm thấy một interface repository chưa đủ để tạo đúng bean. Hạ tầng còn phải xác định module nào chịu trách nhiệm cho interface đó: JPA, MongoDB hay một module khác.

Một dấu hiệu rõ ràng là **giao diện cơ sở đặc thù store**. Repository kế thừa `JpaRepository` thể hiện sự phụ thuộc vào Spring Data JPA; repository kế thừa `MongoRepository` thể hiện sự phụ thuộc vào Spring Data MongoDB. Dấu hiệu này vẫn có ý nghĩa khi đi qua một hoặc nhiều base interface trung gian.

Bài học thuộc chương **Nhiều store**, tập trung vào cách đọc chuỗi kế thừa để phân loại repository. Phần này cũng phân biệt việc chọn module với phạm vi scan, lựa chọn nguồn dữ liệu và lựa chọn bean ở tầng ứng dụng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao môi trường có nhiều repository factory cần căn cứ phân loại rõ ràng.
- Nhận diện repository theo interface store được kế thừa trực tiếp hoặc gián tiếp.
- Phân biệt base interface chung của Commons với base interface đã gắn một công nghệ.
- Dùng `@NoRepositoryBean` đúng vai trò của interface trung gian.
- Giải thích vì sao biết repository thuộc JPA vẫn chưa biết nó dùng datasource nào.
- Nhận ra tình huống mơ hồ do chuỗi kế thừa, metadata hoặc phạm vi scan.
- Kiểm tra việc đăng ký và truy cập đúng store thay vì chỉ dựa vào tên bean hoặc tên proxy.

## 2. Vì sao cần phân loại khi có nhiều module?

Trong một ứng dụng chỉ có một module repository phù hợp, hạ tầng có ít lựa chọn hơn khi xử lý một interface dựa trên các abstraction chung. Khi nhiều repository factory của các module cùng xuất hiện, một interface chung có thể chưa mang đủ thông tin để gắn với đúng module.

Spring Data có cơ chế **strict repository configuration mode** trong bối cảnh phát hiện nhiều module repository. Cơ chế này sử dụng các dấu hiệu mà module nhận biết, chẳng hạn interface đặc thù trong chuỗi kế thừa hoặc metadata trên domain, để xác định candidate phù hợp.

Ở đây, “strict” nói về phân loại và cấu hình repository. Nó không có nghĩa tự tăng isolation giao dịch, bật phân quyền hoặc kiểm tra mọi truy vấn một cách giống nhau trên mọi store.

```text
Có nhiều repository factory trên classpath
        |
        v
Phát hiện candidate repository
        |
        v
Module kiểm tra dấu hiệu nhận diện phù hợp
        |
        +-- chuỗi kế thừa interface đặc thù
        +-- metadata domain mà module nhận biết
        +-- phạm vi cấu hình và điều kiện liên quan
        |
        v
Đăng ký repository bằng factory của module phù hợp
```

Phạm vi và quy tắc cụ thể cần được xem theo module, phiên bản và cấu hình thực tế. Không nên hình dung đây là một bộ suy luận đọc tên nghiệp vụ rồi tự chọn cơ sở dữ liệu.

### 2.1. Nhiều module khác với nhiều nguồn kết nối

Hai datasource đều dùng JPA là bài toán lựa chọn tài nguyên trong cùng công nghệ. JPA và MongoDB cùng xuất hiện là bài toán có nhiều module store.

Cả hai có thể cùng tồn tại trong một ứng dụng, nhưng cần giải quyết ở những ranh giới khác nhau:

| Câu hỏi | Ví dụ |
| --- | --- |
| Repository thuộc module nào? | JPA hay MongoDB? |
| Repository dùng hạ tầng nào trong module đó? | Entity manager factory bán hàng hay lưu vết? |
| Service nhận bean nào? | Adapter tra cứu khách hàng chính hay adapter dữ liệu lưu trữ? |

Kế thừa interface đặc thù chủ yếu cung cấp căn cứ cho câu hỏi đầu tiên.

## 3. Interface Commons không tự chỉ định store

Các interface như `Repository` hoặc `CrudRepository` thuộc phần hợp đồng dùng chung. Chúng mô tả domain, ID và nhóm thao tác, không tự nói dữ liệu được lưu bằng JPA hay MongoDB.

Ví dụ:

```java
import org.springframework.data.repository.CrudRepository;

public interface GenericCustomerRepository
        extends CrudRepository<CustomerData, String> {
}
```

Chỉ từ chuỗi kế thừa trên, chưa thể kết luận store. `CustomerData` ở ví dụ là một kiểu chưa có metadata đặc thù được dùng để phân loại.

Những dấu hiệu sau cũng không tự thay thế interface đặc thù:

- ID là `String`, `Long` hoặc một kiểu khác.
- Repository có phương thức `findByEmail`.
- Tên interface chứa chữ `Jpa`, `Mongo` hay `Document`.
- Interface có annotation `@Repository`.
- Base interface được đặt tên `PersistentRepository`.

Tên package có thể giúp con người tổ chức mã và được dùng để khoanh phạm vi scan. Nhưng một package có chữ `mongo` không tự biến một interface thành `MongoRepository` nếu các căn cứ cấu hình và mapping không phù hợp.

### 3.1. Không phải mọi repository chung đều thất bại

Một repository chỉ kế thừa `CrudRepository` vẫn có thể được một module nhận diện nhờ metadata domain hoặc cấu hình hợp lệ. Vì vậy, không có quy tắc “dùng Commons là không thể chạy khi nhiều store”.

Điểm cần nhớ là **chuỗi kế thừa chung không cung cấp dấu hiệu đặc thù store**. Khi không có căn cứ khác đủ rõ, module có thể không nhận candidate đó; lỗi thiếu bean có thể chỉ xuất hiện khi một thành phần yêu cầu inject repository.

## 4. Kế thừa trực tiếp interface đặc thù

### 4.1. Repository JPA

```java
package example.customer.persistence.jpa;

import org.springframework.data.jpa.repository.JpaRepository;

public interface JpaCustomerRepository
        extends JpaRepository<CustomerEntity, String> {
}
```

Dấu hiệu nhận diện nằm ở `JpaRepository`, không phải tiền tố `Jpa` của tên interface.

Chuỗi kiểu:

```text
JpaCustomerRepository
        -> JpaRepository<CustomerEntity, String>
        -> các abstraction repository liên quan
```

Module JPA có thể nhận ra quan hệ này. Nó vẫn cần domain được mapping hợp lệ và hạ tầng JPA phù hợp để thực sự tạo và sử dụng bean.

### 4.2. Repository MongoDB

```java
package example.customer.persistence.mongo;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface MongoCustomerRepository
        extends MongoRepository<CustomerDocument, String> {
}
```

Chuỗi kiểu:

```text
MongoCustomerRepository
        -> MongoRepository<CustomerDocument, String>
        -> các abstraction repository liên quan
```

Cả hai ví dụ đều dùng ID `String`, nhưng thuộc hai module khác nhau. Đây là minh họa trực tiếp rằng kiểu ID không phải quy tắc phân loại store.

### 4.3. Phân loại không có nghĩa chuyển đổi mô hình

JPA repository cần entity JPA hợp lệ; MongoDB repository cần mapping document phù hợp. Nếu domain không tương thích, nhận diện được interface vẫn chưa đủ để tạo một repository hoạt động.

Interface đặc thù cũng công khai những phương thức mà nó kế thừa. Chọn `JpaRepository` để làm rõ module đồng thời là chọn tập API JPA tương ứng. Nếu bên gọi chỉ cần ít phương thức, cần cân nhắc ranh giới hẹp hơn ở nơi sử dụng.

## 5. Kế thừa gián tiếp qua base interface

Ứng dụng thường có một base interface để gom các quy ước chung. Dấu hiệu store có thể được giữ qua base này.

### 5.1. Base dành riêng cho JPA

```java
package example.persistence.base;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface JpaBaseRepository<T, ID>
        extends JpaRepository<T, ID> {
}
```

Repository cụ thể:

```java
package example.customer.persistence.jpa;

import example.persistence.base.JpaBaseRepository;

public interface JpaCustomerRepository
        extends JpaBaseRepository<CustomerEntity, String> {
}
```

Chuỗi kế thừa vẫn chứa `JpaRepository`:

```text
JpaCustomerRepository
        -> JpaBaseRepository
        -> JpaRepository
```

Không cần repository cụ thể nhắc lại `JpaRepository` chỉ để dấu hiệu tồn tại. Quan hệ kiểu được giữ thông qua kế thừa gián tiếp.

### 5.2. Base dành riêng cho MongoDB

```java
package example.persistence.base;

import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface MongoBaseRepository<T, ID>
        extends MongoRepository<T, ID> {
}
```

Repository cụ thể:

```java
package example.customer.persistence.mongo;

import example.persistence.base.MongoBaseRepository;

public interface MongoCustomerRepository
        extends MongoBaseRepository<CustomerDocument, String> {
}
```

Đây là phương án thay cho kế thừa trực tiếp ở phần trước, không phải yêu cầu tạo thêm một repository cùng tên trong dự án.

### 5.3. `@NoRepositoryBean` không phải nhãn store

Annotation đánh dấu base không được tạo thành repository bean trực tiếp. Nó hữu ích với interface trung gian chưa gắn domain và ID cụ thể.

Dấu hiệu JPA của `JpaBaseRepository` đến từ việc kế thừa `JpaRepository`. Dấu hiệu MongoDB đến từ `MongoRepository`. Bản thân `@NoRepositoryBean` không mang thông tin chọn store.

Ví dụ sau vẫn chỉ là một base chung:

```java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface CommonBaseRepository<T, ID>
        extends CrudRepository<T, ID> {
}
```

Repository con của `CommonBaseRepository` không tự trở thành JPA hoặc MongoDB chỉ nhờ tên hay annotation của base.

### 5.4. Base đặc thù vẫn kế thừa API rộng

Nếu `JpaBaseRepository` kế thừa `JpaRepository`, các phương thức của `JpaRepository` vẫn có trong repository con. Không thể biến nó thành API chỉ đọc chỉ bằng việc không viết thêm phương thức ghi ở thân interface.

Có thể giữ base persistence rộng nhưng chỉ đưa service hoặc một kiểu đọc hẹp ra cho bên sử dụng. Không nên đánh đổi ý nghĩa hợp đồng chỉ để đạt một hình thức phân loại.

## 6. Mô hình persistence cần đồng bộ với dấu hiệu interface

Một ví dụ domain JPA, dùng namespace Jakarta Persistence phù hợp bộ dependency đã chọn:

```java
package example.customer.persistence.jpa;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class CustomerEntity {
    @Id
    private String id;

    private String name;

    protected CustomerEntity() {
    }

    public CustomerEntity(String id, String name) {
        this.id = id;
        this.name = name;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

Mô hình MongoDB riêng:

```java
package example.customer.persistence.mongo;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "customers")
public class CustomerDocument {
    @Id
    private String id;

    private String name;

    protected CustomerDocument() {
    }

    public CustomerDocument(String id, String name) {
        this.id = id;
        this.name = name;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

Các kiểu public nằm trong file riêng theo package đã ghi. Ví dụ dùng ID do ứng dụng cung cấp; nó không mô tả chiến lược phát sinh ID chung cho mọi store.

Hai mô hình có thể biểu diễn cùng khái niệm khách hàng nhưng vẫn được tách để tránh trộn metadata persistence. Một kiểu kết quả nghiệp vụ có thể được tạo từ chúng tại adapter.

Không suy ra hai repository có thể dùng thay thế cho nhau chỉ vì cùng ID `String` và cùng getter. Vòng đời đối tượng, truy vấn, ràng buộc và giao dịch vẫn khác nhau.

## 7. Interface đặc thù, metadata và phạm vi scan cần nhất quán

Interface đặc thù là một căn cứ mà module sử dụng để nhận candidate. Nó không phải một bộ phân xử toàn cục tự làm mọi metadata trái ngược trở nên vô hại.

Ví dụ cần tránh là một domain đồng thời gắn metadata JPA và MongoDB, trong khi các vùng scan chồng nhau và repository dựa vào abstraction chung. Nhiều module có thể thấy những dấu hiệu phù hợp với chính chúng, khiến việc gắn repository không còn rõ ràng.

Ngay cả khi thêm một interface đặc thù, không nên mặc định nó tạo ra thứ tự ưu tiên độc quyền trước mọi dấu hiệu của module khác. Thiết kế an toàn hơn là làm các căn cứ đồng bộ:

```text
Repository JPA
    -> kế thừa dấu hiệu JPA
    -> domain JPA
    -> phạm vi cấu hình JPA
    -> hạ tầng JPA phù hợp

Repository MongoDB
    -> kế thừa dấu hiệu MongoDB
    -> domain MongoDB
    -> phạm vi cấu hình MongoDB
    -> hạ tầng MongoDB phù hợp
```

Đối với mô hình cố ý dùng cho nhiều công nghệ, phải kiểm tra rõ mapping và quy tắc nhận diện của các module liên quan. Không nên bắt đầu bằng một giả định rằng mọi module sẽ tự bỏ qua candidate không đúng ý định của người viết.

## 8. Tách phạm vi scan để thể hiện ranh giới

Một cấu trúc package có thể là:

```text
example.persistence.base
    JpaBaseRepository
    MongoBaseRepository

example.customer.persistence.jpa
    CustomerEntity
    JpaCustomerRepository

example.customer.persistence.mongo
    CustomerDocument
    MongoCustomerRepository
```

Base interface được tham chiếu qua quan hệ kiểu; nó không cần được tạo thành bean. Repository cụ thể thuộc package của từng store.

Cấu hình JPA:

```java
package example.configuration;

import example.customer.persistence.jpa.JpaCustomerRepository;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@Configuration
@EnableJpaRepositories(
        basePackageClasses = JpaCustomerRepository.class,
        entityManagerFactoryRef = "customerEntityManagerFactory",
        transactionManagerRef = "customerTransactionManager")
public class CustomerJpaRepositoriesConfiguration {
}
```

Cấu hình MongoDB:

```java
package example.configuration;

import example.customer.persistence.mongo.MongoCustomerRepository;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@Configuration
@EnableMongoRepositories(
        basePackageClasses = MongoCustomerRepository.class,
        mongoTemplateRef = "customerMongoTemplate")
public class CustomerMongoRepositoriesConfiguration {
}
```

Các ví dụ giả định cấu hình được context nạp và các bean hạ tầng được khai báo đúng. Chúng chỉ minh họa ranh giới repository, không phải toàn bộ cấu hình kết nối.

`basePackageClasses` dùng kiểu để xác định package scan. Nó không có nghĩa chỉ quét duy nhất một interface được ghi trong thuộc tính.

### 8.1. Phạm vi scan không thay thế mapping

JPA repository được scan đúng nhưng entity manager factory không quản lý `CustomerEntity` vẫn có thể tạo lỗi. MongoDB repository trỏ đúng template nhưng converter hoặc mapping không phù hợp cũng chưa bảo đảm thực thi đúng.

Phân loại module, scan và mapping là các bước cần phối hợp, không phải ba tên gọi của cùng một việc.

### 8.2. Auto-configuration cũng phải được tính vào thiết kế

Nếu ứng dụng dùng Spring Boot, một phần repository có thể do auto-configuration quản lý. Khi thêm cấu hình tường minh, cần xem điều kiện phối hợp của module và phiên bản đang dùng.

Không quét lại toàn bộ package chỉ để “bổ sung chắc chắn” mà chưa biết nguồn nào đang đăng ký repository. Một module hoặc dependency mới trên classpath cũng có thể làm bối cảnh phân loại thay đổi so với trước.

## 9. Những tình huống dễ phân loại sai

### 9.1. Đổi tên base chung thành tên công nghệ

```java
@NoRepositoryBean
public interface MyJpaRepository<T, ID>
        extends CrudRepository<T, ID> {
}
```

Tên có chữ JPA nhưng chuỗi kế thừa vẫn chỉ chứa abstraction chung. Nếu muốn dùng interface đặc thù làm dấu hiệu, phải có quan hệ kiểu thực sự phù hợp.

Metadata domain có thể vẫn giúp phân loại trong một cấu hình hợp lệ. Điều sai là coi tên base như căn cứ mà repository factory tự hiểu.

### 9.2. Ghép hai interface store vào một repository

Một thiết kế cần tránh:

```java
public interface UniversalCustomerRepository
        extends JpaRepository<SharedCustomer, String>,
                MongoRepository<SharedCustomer, String> {
}
```

Đoạn khai báo minh họa sự pha trộn, không phải mô hình đề xuất. Tùy tổ hợp API, còn có thể phát sinh vấn đề chữ ký phương thức. Dù quan hệ kiểu có biên dịch được trong một bối cảnh, nó cũng không định nghĩa module nào chịu trách nhiệm hay cách hợp nhất semantics của hai store.

Nếu nghiệp vụ cần truy cập cả hai, hãy dùng hai repository riêng trong các adapter hoặc service có trách nhiệm rõ ràng.

### 9.3. Đổi annotation ở nơi inject

`@Qualifier` hoặc `@Primary` có thể giúp chọn bean khi nhiều bean phù hợp với một dependency. Chúng không biến repository thành JPA hay MongoDB và không sửa factory đã gắn sai.

Cần sửa phân loại, phạm vi hoặc tham chiếu hạ tầng ở nơi tạo repository trước. Sau đó mới giải quyết lựa chọn bean ở tầng tiêu thụ.

### 9.4. Dùng `@RepositoryDefinition` như nhãn store

`@RepositoryDefinition` có thể mô tả domain và ID cho một interface theo cách khai báo được hỗ trợ. Nó không tự chỉ định công nghệ persistence.

Một repository khai báo theo annotation này vẫn cần dấu hiệu và cấu hình để module nhận diện, tạo và thực thi phù hợp.

## 10. Ma trận đọc nhanh một candidate

| Chuỗi kế thừa và bối cảnh | Điều có thể kết luận |
| --- | --- |
| Có `JpaRepository`, domain JPA, phạm vi JPA rõ | Có căn cứ kiểu đặc thù để module JPA nhận diện; vẫn cần hạ tầng hợp lệ |
| Có `MongoRepository`, domain document, phạm vi MongoDB rõ | Có căn cứ kiểu đặc thù để module MongoDB nhận diện; vẫn cần hạ tầng hợp lệ |
| Base trung gian kế thừa `JpaRepository` | Dấu hiệu JPA được giữ qua kế thừa gián tiếp |
| Chỉ có `CrudRepository`, domain không có dấu hiệu đặc thù | Chuỗi kiểu chưa đủ để chọn store trong bối cảnh nhiều module |
| Chỉ có `CrudRepository`, domain có metadata duy nhất mà module nhận biết | Có thể được phân loại qua metadata; không phải qua interface chung |
| Có `@NoRepositoryBean` trên base chung | Base không tạo bean trực tiếp; chưa có thêm dấu hiệu store |
| Kế thừa nhiều interface store hoặc metadata chồng không rõ | Cần thiết kế lại hoặc làm rõ; không giả định có một store được ưu tiên tự động |
| Hai factory JPA đều quét một repository JPA | Module đã rõ nhưng lựa chọn tài nguyên/đăng ký có thể còn xung đột |

Ma trận này là công cụ đọc cấu hình, không thay thế tài liệu module hoặc kiểm tra trên bộ dependency cụ thể.

## 11. Biết store chưa biết datasource hoặc database

Giả sử ứng dụng có hai entity manager factory:

```text
salesEntityManagerFactory
archiveEntityManagerFactory
```

Một repository kế thừa `JpaRepository` cho biết nó thuộc hướng tích hợp JPA. Nó không tự nói phải dùng factory bán hàng hay lưu trữ.

Cần tách phạm vi repository và tham chiếu factory/transaction manager tương ứng. Nếu cùng interface bị hai cấu hình JPA quét, cả hai đều có thể thấy dấu hiệu JPA; interface đặc thù không giải quyết việc quét chồng trong cùng module.

MongoDB có tình huống tương tự với nhiều template hoặc database. Dấu hiệu `MongoRepository` không tự chọn `catalogMongoTemplate` thay vì `archiveMongoTemplate`.

Một bảng quan hệ hữu ích:

| Repository | Module | Bean hạ tầng | Phạm vi nghiệp vụ |
| --- | --- | --- | --- |
| Repository khách hàng giao dịch | JPA | Factory và transaction manager giao dịch | Nguồn khách hàng chính |
| Repository document hồ sơ | MongoDB | Template hồ sơ | Dữ liệu document bổ sung |
| Repository dữ liệu lưu trữ | JPA hoặc MongoDB theo thiết kế | Hạ tầng lưu trữ riêng | Tra cứu dữ liệu lưu trữ |

Đây là quyết định cấu hình và kiến trúc ứng dụng. Không nên mã hóa mọi lựa chọn này bằng một tên generic như `Repository<Customer, String>` rồi mong framework suy ra ý nghĩa nghiệp vụ.

## 12. Giữ API nghiệp vụ hẹp khi persistence đã đặc thù

Làm rõ store ở tầng persistence không bắt buộc mọi lớp của ứng dụng phải phụ thuộc `JpaRepository` hoặc `MongoRepository`.

Ví dụ, một interface tra cứu ở tầng ứng dụng có thể là:

```java
import java.util.Optional;

public interface CustomerLookup {
    Optional<CustomerView> findById(String id);
}
```

`CustomerView` là kiểu kết quả của ứng dụng. Adapter JPA dùng `JpaCustomerRepository`; adapter MongoDB dùng `MongoCustomerRepository`. Mỗi adapter thực hiện mapping và điều kiện truy cập phù hợp với vai trò được giao.

Nếu có hai adapter cùng triển khai `CustomerLookup`, ứng dụng cần quyết định nơi nào dùng adapter nào hoặc cấu hình nào được chọn. Đó là bài toán lựa chọn implementation nghiệp vụ, khác với Spring Data phân loại repository theo module.

Không mặc định hai adapter tương đương chỉ vì cùng triển khai interface. Phải định nghĩa yêu cầu về phạm vi dữ liệu, trạng thái không tìm thấy, kiểu ID và khả năng thấy thay đổi.

Cũng không suy ra việc gọi hai adapter trong một service tạo giao dịch nguyên tử xuyên store. Interface phân loại đúng giúp gắn hạ tầng đúng; tính nhất quán nhiều tài nguyên cần thiết kế riêng.

## 13. Nhận diện đúng chưa chứng minh mọi tính năng chạy được

Sau khi repository được gắn với module, còn có các câu hỏi tiếp theo:

| Khả năng | Phải xác nhận thêm |
| --- | --- |
| CRUD | Mapping ID, trạng thái mới/cũ, version và semantics lưu/xóa |
| Derived queries | Thuộc tính, toán tử và kiểu kết quả mà module hỗ trợ |
| Phân trang, sắp xếp | Mapping trường, collation, tổng số và kế hoạch truy vấn |
| Projection | Loại projection, cách tạo kết quả và khả năng tối ưu dữ liệu đọc |
| Query by Example | Executor và các quy tắc so khớp được hỗ trợ |
| Auditing | Cấu hình, nguồn thời gian/chủ thể và đường ghi thực sự kích hoạt |
| Giao dịch | Transaction manager, tài nguyên tham gia và giới hạn của store |

Một repository được nhận diện là JPA không tự có mọi extension của JPA. Một repository được nhận diện là MongoDB không tự hỗ trợ mọi toán tử MongoDB qua mọi kiểu khai báo.

Do đó, cần phân biệt lỗi phân loại với lỗi tạo query hoặc lỗi sử dụng tài nguyên. Nếu module đã chọn đúng nhưng tên thuộc tính trong derived query sai, đổi base interface không sửa được nguyên nhân.

## 14. Quy trình kiểm tra một repository trong ứng dụng nhiều store

### Bước 1: Viết rõ module đích

Ghi repository dùng JPA, MongoDB hay module khác. Nếu có hai nguồn trong cùng module, ghi thêm factory hoặc template mong muốn.

### Bước 2: Đọc toàn bộ chuỗi kế thừa

Đi qua các base interface của ứng dụng tới abstraction Spring Data thực sự. Tìm interface đặc thù thay vì chỉ nhìn tên interface gần nhất.

Nếu chỉ có Commons, xác định căn cứ metadata hoặc cấu hình nào đang được dùng để phân loại. Không tự cho rằng `@NoRepositoryBean` đã chọn store.

### Bước 3: Đối chiếu domain

Xác nhận domain được mapping cho module đích. Kiểm tra metadata chồng hoặc annotation nhập sai package. Với JPA, xác nhận domain thuộc managed type của đúng factory.

### Bước 4: Đối chiếu scan và nguồn đăng ký

Kiểm tra package của annotation kích hoạt, XML hoặc auto-configuration đang tham gia. Một nhóm repository cần nguồn cấu hình chịu trách nhiệm rõ ràng.

### Bước 5: Gắn và kiểm tra hạ tầng

Xác nhận factory, transaction manager hoặc template đúng tài nguyên. Không chỉ kiểm tra tên bean có xuất hiện mà còn kiểm tra vai trò và nguồn dữ liệu thật sự của nó.

### Bước 6: Thực hiện thao tác phân biệt được nguồn

Tạo dữ liệu kiểm tra phù hợp trong từng nguồn và thực hiện truy vấn có ý nghĩa. Nếu các nguồn có dữ liệu giống nhau hoàn toàn, việc đọc nhầm nguồn có thể khó phát hiện.

### Bước 7: Kiểm tra bối cảnh dependency thực tế

Runtime, test và IDE có thể khác classpath. Nếu một dependency bổ sung làm xuất hiện thêm repository factory, kiểm tra lại log phân loại và cấu hình có hiệu lực.

## 15. Chẩn đoán theo triệu chứng

| Triệu chứng | Điều nên điều tra |
| --- | --- |
| Log không xác định chắc store cho candidate | Chuỗi kế thừa chung, metadata domain và module đang hoạt động |
| Không có bean repository để inject | Candidate có được nhận, base có bị coi là không tạo bean, scan và cấu hình có được nạp không |
| Trùng tên hoặc nhiều bean | Quét chồng, nhiều nguồn đăng ký hoặc repository trùng tên đơn giản |
| JPA báo domain không được quản lý | Mapping và managed type của factory đã gắn |
| MongoDB tạo được bean nhưng truy cập nhầm database | Template tham chiếu và cấu hình database phía dưới |
| Thêm một store mới làm repository cũ không còn được tạo | Bối cảnh nhiều factory và căn cứ phân loại của repository cũ |
| Bean có nhưng derived query lỗi | Thuộc tính, toán tử hoặc khả năng module, không nhất thiết là phân loại |

Proxy là chi tiết thực thi. Tên lớp proxy có thể thay đổi và việc một bean là instance của một interface chỉ xác nhận quan hệ kiểu Java. Nó không chứng minh bean đang truy cập đúng database.

Tương tự, log tìm thấy một số repository hữu ích để kiểm tra scan nhưng chưa đủ chứng minh mapping, truy vấn và tài nguyên đều đúng.

## 16. Tình huống thực hành

Một dự án ban đầu chỉ dùng JPA. Nó có `CommonBaseRepository<T, ID> extends CrudRepository<T, ID>`, còn các domain được mapping theo JPA. Sau đó nhóm thêm MongoDB và tạo một số domain không có metadata rõ ràng, nhưng vẫn cho tất cả repository kế thừa base chung.

Cần phân tích từng repository thay vì đổi toàn bộ cùng một lúc:

1. Repository JPA cũ có thể vẫn được nhận nhờ metadata domain, nhưng cần xác nhận cấu hình thực tế.
2. Repository mới với base chung và domain không có dấu hiệu đặc thù có thể thiếu căn cứ phân loại.
3. Base chung không tự chọn MongoDB chỉ vì repository mới nằm trong package có chữ `mongo`.
4. Nếu cần phân loại theo interface, tạo base JPA và MongoDB có chuỗi kế thừa đặc thù tương ứng.
5. Đánh dấu base trung gian không tạo bean trực tiếp.
6. Tách phạm vi scan và gắn đúng hạ tầng cho mỗi nhóm.
7. Kiểm tra query và hành vi trên store sau khi việc phân loại đã rõ.

Nếu bên gọi không nên nhìn thấy toàn bộ CRUD của base đặc thù, giữ repository ở tầng persistence và công bố service hoặc interface hẹp thích hợp. Đừng trộn hai công nghệ vào một base để che vấn đề phân loại.

## 17. Câu hỏi tự kiểm tra

### Câu 1

`CustomerRepository` kế thừa `JpaBaseRepository`, còn base đó kế thừa `JpaRepository`. Repository cụ thể có dấu hiệu JPA không?

**Gợi ý trả lời:** Có. Dấu hiệu được giữ qua quan hệ kế thừa gián tiếp; không cần viết lại `JpaRepository` ở mọi interface cụ thể.

### Câu 2

`@NoRepositoryBean` trên một base kế thừa `CrudRepository` có làm repository con thuộc JPA không?

**Gợi ý trả lời:** Không. Annotation ngăn tạo bean trực tiếp cho base. Nó không chọn store; cần xem interface đặc thù, metadata và cấu hình liên quan.

### Câu 3

Repository có ID kiểu `String` có đủ căn cứ kết luận là MongoDB không?

**Gợi ý trả lời:** Không. Kiểu ID không định danh module. JPA cũng có thể dùng kiểu ID phù hợp mapping như `String`.

### Câu 4

Nếu đã biết repository thuộc JPA, đã biết nó dùng datasource bán hàng hay lưu trữ chưa?

**Gợi ý trả lời:** Chưa. Phải xem phạm vi cấu hình, entity manager factory và transaction manager được gắn với repository.

### Câu 5

Có nên ghép `JpaRepository` và `MongoRepository` vào một interface để tạo repository đa năng không?

**Gợi ý trả lời:** Không nên. Quan hệ kiểu đó không cung cấp một factory hoặc semantics chung cho hai store. Dùng repository và adapter riêng với trách nhiệm rõ ràng.

### Câu 6

Một repository chỉ kế thừa Commons có chắc luôn bị loại khi nhiều store không?

**Gợi ý trả lời:** Không. Metadata domain hoặc cấu hình hợp lệ có thể giúp phân loại. Điều chưa có là dấu hiệu store từ chính chuỗi interface chung.

### Câu 7

Vì sao kiểm tra `bean instanceof JpaRepository` chưa đủ xác nhận truy cập đúng nguồn dữ liệu?

**Gợi ý trả lời:** Nó xác nhận kiểu mà bean công khai, không xác nhận factory, datasource hoặc database đích. Cần kiểm tra quan hệ cấu hình và thao tác dữ liệu thực tế.