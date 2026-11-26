# Chế độ cấu hình repository nghiêm ngặt khi có nhiều mô-đun Spring Data

## Mục tiêu bài học

Một ứng dụng có thể dùng Spring Data JPA cho dữ liệu quan hệ và Spring Data MongoDB cho document. Cả hai module đều xây dựng trên các abstraction của Spring Data Commons, nên một interface chỉ kế thừa `Repository` hoặc `CrudRepository` chưa tự nói rõ nó thuộc công nghệ nào.

Khi phát hiện nhiều repository factory liên quan trên classpath, Spring Data chuyển sang **strict repository configuration mode**, tức chế độ cấu hình repository nghiêm ngặt. Mục tiêu là xác định repository candidate nào có đủ dấu hiệu để được một module nhận quản lý.

Bài học thuộc chương **Nhiều store** của module SPRING_DATA_COMMONS. Sau bài học, bạn có thể:

- Giải thích khi nào chế độ nghiêm ngặt xuất hiện và nó giải quyết vấn đề gì.
- Nhận diện vai trò của interface chuyên biệt, annotation domain và phạm vi scanning.
- Phân biệt cấu hình module với việc chọn một cơ sở dữ liệu vật lý.
- Thiết kế repository JPA và MongoDB với ranh giới rõ ràng.
- Đọc thông báo nhận diện store mà không coi mọi dòng chẩn đoán là lỗi nghiêm trọng.
- Tránh kỳ vọng rằng abstraction chung sẽ tự tạo mapping hoặc giao dịch xuyên store.

## 1. Vấn đề xuất hiện khi một hợp đồng được nhiều module sử dụng

Giả sử có interface:

~~~java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
~~~

Hai thông tin từ hợp đồng là:

- Domain được quản lý có kiểu `Customer`.
- Định danh được diễn đạt bằng `Long`.

Chúng chưa cho biết repository phải được triển khai bằng JPA, MongoDB hay một module khác.

Nếu chỉ có một module repository phù hợp trong ứng dụng, ngữ cảnh có thể đủ rõ. Khi nhiều module cùng tham gia cấu hình, mỗi module cần xác định những candidate thuộc khả năng của mình.

~~~mermaid
flowchart TD
    A["Interface repository của ứng dụng"] --> B["Metadata dùng chung của Commons"]
    B --> C["Cấu hình repository JPA"]
    B --> D["Cấu hình repository MongoDB"]
    C --> E{"Có dấu hiệu nhận diện phù hợp JPA?"}
    D --> F{"Có dấu hiệu nhận diện phù hợp MongoDB?"}
    E --> G["Factory và hạ tầng JPA"]
    F --> H["Factory và hạ tầng MongoDB"]
~~~

Sơ đồ mô tả việc phân loại candidate. Nó không có nghĩa cùng một lời gọi CRUD được gửi đồng thời tới hai kho dữ liệu.

Sau khi được đăng ký, repository gắn với cơ chế thực thi của module đã tạo nó. Commons không chọn lại store cho từng lời gọi dựa trên tên method hoặc giá trị ID.

## 2. Chế độ nghiêm ngặt được kích hoạt như thế nào?

Cơ chế này liên quan đến việc phát hiện nhiều repository factory/module trên classpath. Nó không đếm số interface repository hoặc suy ra số cơ sở dữ liệu từ tên package.

Những tình huống cần phân biệt:

| Tình huống | Liên hệ với chế độ nghiêm ngặt |
| --- | --- |
| Một module JPA, nhiều repository JPA. | Số lượng repository tự nó không phải lý do chuyển sang cấu hình nhiều module. |
| Hai DataSource dùng cùng module JPA. | Là bài toán nhiều nguồn/persistence unit; không đồng nhất với nhiều module Spring Data. |
| JPA và MongoDB cùng có khả năng tham gia cấu hình repository. | Là tình huống điển hình cần phân loại repository theo module. |
| Một dependency bắc cầu đưa thêm module Spring Data vào. | Có thể làm ứng dụng có nhiều factory trên classpath dù người viết ứng dụng chỉ chú ý một store. |

Một thông báo minh họa thường gặp có nội dung:

~~~text
Multiple Spring Data modules found, entering strict repository configuration mode
~~~

Thông báo này không tự chứng minh ứng dụng bị lỗi. Một ứng dụng nhiều store được cấu hình đúng vẫn có thể khởi động và hoạt động bình thường trong chế độ đó.

Đây cũng không phải một chế độ bảo mật, một mức isolation transaction hay một quy tắc kiểm tra dữ liệu đầu vào. Nó phục vụ việc nhận diện và đăng ký repository.

Không cần tự thêm một thuộc tính có tên phỏng đoán để bật chế độ. Hãy giải quyết tính rõ ràng của cấu hình repository thay vì tìm cách né thông báo.

## 3. Hai nhóm dấu hiệu nhận diện quan trọng

### 3.1. Repository kế thừa interface chuyên biệt của module

Ví dụ:

~~~java
public interface CustomerAccountRepository
        extends JpaRepository<CustomerAccount, Long> {
}
~~~

`JpaRepository` là dấu hiệu gắn với module Spring Data JPA.

Tương tự:

~~~java
public interface CustomerProfileRepository
        extends MongoRepository<CustomerProfile, String> {
}
~~~

`MongoRepository` là dấu hiệu gắn với module Spring Data MongoDB.

Hạ tầng xét hệ interface của repository, không chỉ tên gọi của chính interface đó. Một interface nền chuyên biệt có thể truyền dấu hiệu này cho những interface kế thừa tiếp theo.

Đặt tên `CustomerJpaRepository` nhưng chỉ kế thừa một hợp đồng chung không tự tạo dấu hiệu JPA. Tên Java giúp người đọc; quan hệ kiểu và metadata mới là thông tin kỹ thuật liên quan.

### 3.2. Domain có annotation được module nhận diện

Một module có thể nhận diện repository dựa trên kiểu domain và annotation mapping đặc trưng.

Ví dụ:

| Domain mapping | Module có dấu hiệu liên quan |
| --- | --- |
| `jakarta.persistence.Entity` | Spring Data JPA trong bộ JPA dùng Jakarta Persistence. |
| `org.springframework.data.mongodb.core.mapping.Document` | Spring Data MongoDB. |

Do đó, một repository chỉ kế thừa `CrudRepository` vẫn có thể được nhận diện rõ nếu domain mang mapping đặc trưng và không có tín hiệu mâu thuẫn.

~~~java
@Entity
class CustomerAccount {
    // Mapping JPA của domain.
}

interface CustomerAccountRepository
        extends CrudRepository<CustomerAccount, Long> {
}
~~~

Đoạn trên chỉ minh họa quan hệ nhận diện; một entity JPA hoàn chỉnh vẫn cần định danh và mapping hợp lệ.

### 3.3. Có dấu hiệu nhận diện chưa đủ để truy cập dữ liệu thành công

Nếu repository kế thừa `JpaRepository` nhưng domain không phải một kiểu JPA được quản lý, việc có dấu hiệu ở hệ interface không tự làm mapping trở nên hợp lệ.

Cần phân biệt:

1. Candidate có thể được module nhận diện.
2. Factory có thể tạo repository với metadata và mapping hợp lệ.
3. Repository có thể kết nối và thực thi thao tác trên nguồn dữ liệu thực tế.

Lỗi có thể xuất hiện ở từng bước khác nhau. Không dùng bước nhận diện thành công làm bằng chứng rằng toàn bộ hạ tầng đã sẵn sàng.

## 4. Bảng phân tích các kiểu khai báo

| Hệ interface | Domain | Nhận định |
| --- | --- | --- |
| JpaRepository | Chỉ có mapping JPA phù hợp. | Dấu hiệu nhất quán cho module JPA. |
| MongoRepository | Chỉ có mapping MongoDB phù hợp. | Dấu hiệu nhất quán cho module MongoDB. |
| CrudRepository | Domain có @Entity phù hợp. | Có thể nhận diện JPA qua domain. |
| CrudRepository | Domain có @Document phù hợp. | Có thể nhận diện MongoDB qua domain. |
| Repository hoặc CrudRepository | Domain không có dấu hiệu được module nhận diện. | Thiếu cơ sở phân loại an toàn trong cấu hình nghiêm ngặt. |
| CrudRepository | Domain mang cả @Entity và @Document. | Có dấu hiệu cho nhiều module, dễ gây mơ hồ. |
| @RepositoryDefinition | Domain có dấu hiệu rõ cho một module. | Annotation cung cấp domain/ID; module vẫn phải được nhận diện qua các thông tin phù hợp. |

Không đọc bảng thành một quy tắc ưu tiên tuyệt đối rằng “có interface chuyên biệt thì mọi dấu hiệu khác đều bị bỏ qua”.

Nếu domain đồng thời cung cấp dấu hiệu cho module khác, module đó vẫn có thể xem domain là một cơ sở nhận diện. Thiết kế nên làm các tín hiệu nhất quán thay vì tạo một domain nhiều mapping rồi dựa vào suy đoán về thứ tự xử lý.

`@RepositoryDefinition` cũng không có thuộc tính chọn JPA, MongoDB hay một datasource cụ thể. Nó thay cách cung cấp metadata domain/ID, không thay thế bài toán phân loại store.

## 5. Phạm vi scanning có vai trò bổ sung

Mỗi cấu hình repository chỉ nên quét vùng chứa repository mà nó quản lý.

Ví dụ:

~~~text
com.example.multistore
    account
        domain
        repository
    profile
        document
        repository
~~~

Có thể để cấu hình JPA quét `account.repository` và cấu hình MongoDB quét `profile.repository`.

Điều này có hai lợi ích:

- Giảm những candidate không liên quan mà một module phải xem xét.
- Làm ranh giới sở hữu repository rõ trong cấu hình ứng dụng.

Tuy nhiên, một package có chữ `jpa` hoặc `mongo` không tự trở thành metadata store. Phạm vi quét giới hạn nơi tìm candidate; nó không chuyển một interface chung và một domain chưa có mapping thành repository hợp lệ cho mọi module.

Vì vậy, nên phối hợp:

~~~text
Phạm vi quét rõ
    + hệ interface hoặc mapping nhận diện phù hợp
    + hạ tầng của module
        -> repository được đăng ký đúng mục đích
~~~

Không coi việc tách package là cách vô hiệu hóa các yêu cầu nhận diện của chế độ nghiêm ngặt.

## 6. Ví dụ cấu hình JPA và MongoDB có ranh giới rõ

Ví dụ mô hình hóa hai phần dữ liệu:

- Tài khoản khách hàng trong kho dữ liệu quan hệ.
- Hồ sơ tùy chọn của khách hàng trong MongoDB.

Hai domain chia sẻ một giá trị nghiệp vụ `customerNumber` nhưng có mapping và định danh lưu trữ riêng.

### 6.1. Dependency và hạ tầng cần có

Trong ứng dụng Boot, hai starter thường được sử dụng cho ví dụ là:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-jpa</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb</artifactId>
</dependency>
~~~

Đoạn này giả định dự án có cơ chế quản lý dependency phù hợp. Ứng dụng còn cần driver quan hệ, datasource, JPA infrastructure và cấu hình kết nối MongoDB tương ứng.

Không ghép riêng một version Commons chỉ để làm mất thông báo nhận diện nhiều module. Những module dùng chung Commons cần một bộ dependency tương thích.

Các đoạn mã dưới đây tập trung vào domain, repository và vùng quét. Chúng giả định hạ tầng kết nối đã được cấu hình; lớp cấu hình vùng quét không tự cung cấp cơ sở dữ liệu.

### 6.2. Cấu trúc package

~~~text
com.example.multistore
    MultiStoreApplication
    config
        StoreRepositoryConfiguration
    account
        domain
            CustomerAccount
        repository
            CustomerAccountRepository
    profile
        document
            CustomerProfile
        repository
            CustomerProfileRepository
~~~

Mỗi lớp public hoặc interface public được đặt trong file cùng tên.

### 6.3. Domain quan hệ

File `account/domain/CustomerAccount.java`:

~~~java
package com.example.multistore.account.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer_account")
public class CustomerAccount {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String customerNumber;

    private String displayName;

    protected CustomerAccount() {
    }

    public CustomerAccount(
            String customerNumber,
            String displayName) {
        this.customerNumber = customerNumber;
        this.displayName = displayName;
    }

    public Long getId() {
        return id;
    }

    public String getCustomerNumber() {
        return customerNumber;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

`@Entity` và `@Id` được import từ JPA. Domain này không mang annotation MongoDB.

Chiến lược sinh ID phải phù hợp với cơ sở dữ liệu quan hệ thực tế. Tên kiểu ID `Long` không phải dấu hiệu đủ để suy ra store; chính mapping và hệ repository mới làm rõ mục đích.

### 6.4. Domain document

File `profile/document/CustomerProfile.java`:

~~~java
package com.example.multistore.profile.document;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "customer_profiles")
public class CustomerProfile {

    @Id
    private String id;

    private String customerNumber;

    private String preferredLanguage;

    protected CustomerProfile() {
    }

    public CustomerProfile(
            String customerNumber,
            String preferredLanguage) {
        this.customerNumber = customerNumber;
        this.preferredLanguage = preferredLanguage;
    }

    public String getId() {
        return id;
    }

    public String getCustomerNumber() {
        return customerNumber;
    }

    public String getPreferredLanguage() {
        return preferredLanguage;
    }
}
~~~

`@Document` cho biết mapping MongoDB. `@Id` ở đây đến từ Spring Data, khác import JPA dùng trong lớp tài khoản.

Hai domain không cần cùng kiểu ID lưu trữ. Nếu ứng dụng liên hệ dữ liệu qua customerNumber, những quy tắc như tính duy nhất, đồng bộ và vòng đời giá trị này phải được thiết kế riêng.

### 6.5. Hai repository chuyên biệt

File `account/repository/CustomerAccountRepository.java`:

~~~java
package com.example.multistore.account.repository;

import com.example.multistore.account.domain.CustomerAccount;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerAccountRepository
        extends JpaRepository<CustomerAccount, Long> {
}
~~~

File `profile/repository/CustomerProfileRepository.java`:

~~~java
package com.example.multistore.profile.repository;

import com.example.multistore.profile.document.CustomerProfile;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CustomerProfileRepository
        extends MongoRepository<CustomerProfile, String> {
}
~~~

Các dấu hiệu nhất quán:

| Repository | Interface chuyên biệt | Domain mapping | ID |
| --- | --- | --- | --- |
| CustomerAccountRepository | JpaRepository | @Entity | Long |
| CustomerProfileRepository | MongoRepository | @Document | String |

Không cần thêm stereotype `@Repository` lên hai interface chỉ để tạo implementation. Cơ chế repository của từng module chịu trách nhiệm tạo bean.

### 6.6. Cấu hình quét theo package của repository

File `config/StoreRepositoryConfiguration.java`:

~~~java
package com.example.multistore.config;

import com.example.multistore.account.repository.CustomerAccountRepository;
import com.example.multistore.profile.repository.CustomerProfileRepository;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@Configuration
@EnableJpaRepositories(
    basePackageClasses = CustomerAccountRepository.class
)
@EnableMongoRepositories(
    basePackageClasses = CustomerProfileRepository.class
)
public class StoreRepositoryConfiguration {
}
~~~

`basePackageClasses` dùng package của interface được truyền vào làm mốc quét. Nó không có nghĩa chỉ đăng ký đúng một interface đó.

Lớp ứng dụng nằm ở package cha:

~~~java
package com.example.multistore;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MultiStoreApplication {

    public static void main(String[] args) {
        SpringApplication.run(MultiStoreApplication.class, args);
    }
}
~~~

Với bố cục này, lớp cấu hình ở package con có thể được component scanning phát hiện, còn domain JPA ở vùng ứng dụng mặc định. Nếu chuyển domain ra ngoài vùng mặc định, cần cấu hình entity scanning hoặc persistence unit tương ứng.

Ví dụ chọn cấu hình repository tường minh để thể hiện ranh giới. Trong ứng dụng Boot có cấu hình mặc định đã đủ rõ, không phải lúc nào cũng cần thêm cả hai annotation Enable theo cách này.

## 7. Interface nền dùng chung có đủ để nhận diện store không?

Một base interface có thể tái sử dụng chữ ký CRUD:

~~~java
import java.util.Optional;
import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.repository.Repository;

@NoRepositoryBean
public interface LookupRepository<T, ID>
        extends Repository<T, ID> {

    Optional<T> findById(ID id);
}
~~~

`@NoRepositoryBean` ngăn việc tạo một repository bean độc lập cho interface nền này. Nó không đánh dấu interface là JPA hay MongoDB.

Một interface cụ thể:

~~~java
public interface CustomerLookupRepository
        extends LookupRepository<CustomerAccount, Long> {
}
~~~

vẫn cần dấu hiệu phù hợp ở domain hoặc hệ interface chuyên biệt. Trong ví dụ, CustomerAccount có @Entity, nên đó là thông tin nhận diện JPA liên quan.

Nếu thay domain bằng một kiểu Java không có mapping mà module nhận diện, việc thêm `@NoRepositoryBean` vào interface nền không giải quyết được sự thiếu thông tin ở repository cụ thể.

Nếu ứng dụng cần base repository chuyên biệt theo store, có thể thiết kế base JPA và base MongoDB riêng. Việc chia sẻ abstraction ở mức nghiệp vụ cũng có thể thực hiện qua một interface ứng dụng với các adapter riêng, thay vì buộc một repository persistence làm mọi vai trò.

## 8. Vì sao domain mang cả @Entity và @Document dễ gây mơ hồ?

Một ý tưởng dễ xuất hiện là dùng cùng một lớp cho cả bảng và document bằng cách gắn cả hai annotation.

Khi một repository chung quản lý lớp đó, nhiều module có thể thấy dấu hiệu nhận diện phù hợp. Kết quả gán repository cho store khi đó không còn rõ ràng theo mục đích ban đầu.

Ngay cả khi một repository kế thừa interface chuyên biệt, domain vẫn có thể cung cấp dấu hiệu cho module khác nếu vùng quét cho phép module đó xét candidate.

Những vấn đề cần phân biệt gồm:

- Repository bị module không mong muốn xem xét.
- Nhiều cấu hình cùng cố đăng ký một candidate.
- Mapping ID và cấu trúc dữ liệu có yêu cầu khác nhau.
- Entity và document có vòng đời hoặc chiến lược cập nhật khác nhau.

Một hướng thiết kế rõ hơn là dùng hai kiểu persistence riêng, như CustomerAccount và CustomerProfile, rồi chuyển đổi hoặc liên hệ chúng bằng giá trị nghiệp vụ có chủ đích.

Không có quy tắc rằng mọi ứng dụng tuyệt đối không thể dùng một lớp với nhiều mapping. Nhưng nếu chọn cách đó, ứng dụng phải làm rõ việc đăng ký repository và những giới hạn mapping, thay vì coi Commons sẽ tự chọn đúng store.

## 9. Đọc thông báo và xác định điều gì thực sự thất bại

### 9.1. Thông báo vào strict mode không phải lỗi khởi động

Dòng báo có nhiều module cho biết cơ chế đang thận trọng khi phân loại candidate. Nó là thông tin về cấu hình, không phải kết luận cần xóa một dependency.

Một module có thể ghi thông tin kiểu:

~~~text
Could not safely identify store assignment ...
~~~

Thông tin đó cần được đọc cùng tên module và repository candidate cụ thể.

Ví dụ, module JPA không nhận một Mongo repository có thể không phải vấn đề nếu MongoDB quản lý repository đó đúng cách và ứng dụng có các bean mong đợi.

### 9.2. Repository thật sự bị bỏ qua thì lỗi có thể xuất hiện sau đó

Nếu không module nào nhận candidate cần thiết, interface có thể không được đăng ký. Khi service cần inject nó, ứng dụng mới báo thiếu bean.

Chuỗi phân tích hợp lý:

~~~text
Candidate được phát hiện?
    -> module nào xét candidate?
    -> có dấu hiệu nhận diện nào?
    -> module nào thực sự đăng ký?
    -> bean có được tạo thành công?
    -> thao tác dữ liệu có thực thi được?
~~~

Đừng chỉ nhìn dòng thiếu bean cuối cùng rồi thêm @Repository lên interface. Cần tìm nguyên nhân tại khâu scanning hoặc phân loại trước đó.

### 9.3. Phân biệt lỗi phân loại với lỗi hạ tầng

| Hiện tượng | Nhóm nguyên nhân cần kiểm tra |
| --- | --- |
| Candidate không được gán cho module nào. | Interface chung, mapping không được nhận diện hoặc phạm vi cấu hình chưa rõ. |
| JPA nhận repository nhưng domain không được quản lý. | Entity scanning, mapping hoặc persistence unit. |
| Mongo repository được tạo nhưng không truy cập được server. | Kết nối, cấu hình, quyền hoặc hạ tầng MongoDB. |
| Query method không hợp lệ. | Tên thuộc tính, chữ ký hoặc khả năng query của module. |
| Hai bean repository xung đột tên. | Tên bean hoặc cấu hình đăng ký trùng, không đồng nhất với lỗi nhận diện store. |
| NoSuchMethodError trong factory hoặc metadata. | Bộ dependency có thể không tương thích. |

Strict mode chỉ xử lý một phần của toàn bộ quá trình. Không nên quy lỗi kết nối hoặc sai derived query về “có nhiều store” khi candidate đã được đăng ký đúng.

## 10. Những điều chế độ nghiêm ngặt không quyết định

### 10.1. Không chọn cơ sở dữ liệu vật lý cho mọi repository cùng module

Một ứng dụng có hai cơ sở dữ liệu quan hệ vẫn dùng cùng module JPA. Dấu hiệu JpaRepository chỉ xác định module, chưa xác định entity manager hoặc transaction manager nào phải được dùng.

Bài toán đó cần cấu hình các tập repository, persistence unit và bean hạ tầng tương ứng.

Tương tự, nhận diện MongoRepository không tự chọn một MongoTemplate hoặc một database bất kỳ trong cấu hình nhiều nguồn MongoDB.

### 10.2. Không tạo giao dịch nguyên tử xuyên store

Một service gọi JPA repository rồi Mongo repository không tự có bảo đảm cả hai cùng commit hoặc cùng rollback.

Việc thêm `@Transactional` phải được hiểu theo transaction manager và khả năng thực tế. Một transaction manager JPA không tự biến cập nhật MongoDB thành một phần của cùng giao dịch.

Nếu nghiệp vụ liên quan nhiều store, cần thiết kế nhất quán dữ liệu, khôi phục hoặc phối hợp cập nhật theo nhu cầu. Đó là bài toán bổ sung, không phải tính năng của strict repository configuration.

### 10.3. Không làm API và truy vấn giống nhau hoàn toàn

Các module dùng chung những kiểu như Pageable, Sort, projection hoặc metadata repository. Tuy nhiên, tập query được hỗ trợ, mapping, chi phí phân trang và auditing vẫn có khác biệt.

Cùng một tên method không có nghĩa có thể chuyển nguyên repository sang mọi store mà không kiểm tra lại khả năng thực thi.

### 10.4. Không đồng bộ dữ liệu giữa entity và document

Việc hai domain cùng có customerNumber không tự tạo quan hệ join xuyên store hoặc cơ chế cập nhật hồ sơ khi tài khoản thay đổi.

Ứng dụng phải quyết định nơi giữ dữ liệu chuẩn, cách đồng bộ và cách xử lý khi một lần cập nhật chỉ thành công ở một phía.

## 11. Những lỗi thiết kế thường gặp

| Cách làm | Vì sao chưa giải quyết đúng vấn đề | Hướng điều chỉnh |
| --- | --- | --- |
| Chỉ đổi tên interface thành tên có chữ Jpa hoặc Mongo. | Tên không thay quan hệ kiểu hoặc mapping. | Khai báo dấu hiệu module rõ và mapping phù hợp. |
| Mọi repository kế thừa cùng CrudRepository, domain không có dấu hiệu nhận diện. | Thiếu cơ sở phân loại trong strict mode. | Chọn interface chuyên biệt hoặc domain mapping rõ cho module. |
| Tách folder nhưng quét chung mọi repository từ cả hai module. | Ranh giới trên đĩa không được phản ánh trong cấu hình. | Thu hẹp vùng quét và giữ metadata nhất quán. |
| Gắn nhiều annotation store lên cùng domain để “dùng được mọi nơi”. | Có thể cung cấp dấu hiệu cho nhiều module. | Đánh giá tách model persistence hoặc cấu hình ranh giới cụ thể. |
| Thêm @NoRepositoryBean để sửa mọi lỗi nhiều store. | Annotation chỉ loại interface nền khỏi việc tạo bean. | Phân loại đúng repository cụ thể và kiểm tra mapping. |
| Bật ghi đè bean để bỏ qua hai repository trùng tên. | Có thể che việc một bean thay thế bean khác ngoài ý định. | Xác định cấu hình sở hữu và tên bean rõ ràng. |
| Tắt một auto-configuration rồi cho rằng không còn nhiều factory trên classpath. | Tắt một đường đăng ký không đồng nghĩa xóa dependency và mọi cơ chế phát hiện. | Xem dependency, cấu hình có hiệu lực và những registrar còn tham gia. |
| Đổi Commons sang version khác để né thông báo. | Không sửa metadata mơ hồ và có thể làm lệch bộ Spring Data. | Giải quyết ranh giới module, giữ dependency tương thích. |

Hai repository khác package nhưng cùng tên ngắn có thể dẫn tới xung đột tên bean theo cơ chế đặt tên được sử dụng. Tên khác nhau như CustomerAccountRepository và CustomerProfileRepository giúp thể hiện ý nghĩa và giảm sự nhầm lẫn, nhưng không thay thế cấu hình module.

## 12. Quy trình đối chiếu một ứng dụng nhiều store

Một quy trình có thể áp dụng khi cấu hình hoặc điều tra:

1. Liệt kê các module Spring Data thực sự có trên classpath, kể cả dependency bắc cầu.
2. Xác định từng repository phải thuộc module nào.
3. Kiểm tra hệ interface và mapping domain có nhất quán với mục đích đó không.
4. Xác định vùng quét của từng cấu hình repository.
5. Kiểm tra domain có được hạ tầng của module quản lý không.
6. Kiểm tra repository bean cần dùng đã được tạo và inject đúng kiểu.
7. Thực hiện một thao tác dữ liệu phù hợp trên từng repository trong môi trường thực hành.
8. Đánh giá riêng những yêu cầu liên quan nhiều store như transaction và đồng bộ.

Bảng đối chiếu cho ví dụ:

| Mục cần xác nhận | Tài khoản | Hồ sơ |
| --- | --- | --- |
| Module mong muốn | JPA | MongoDB |
| Interface đặc trưng | JpaRepository | MongoRepository |
| Mapping domain | @Entity | @Document |
| Vùng repository | account.repository | profile.repository |
| Hạ tầng cần có | Persistence unit và datasource phù hợp. | MongoDB infrastructure phù hợp. |
| Kiểu ID | Long | String |

Từng mức xác nhận có ý nghĩa riêng. Inject được bean chứng minh việc đăng ký/injection, còn thao tác thực tế thành công mới cung cấp thêm bằng chứng về kết nối và thực thi đường dữ liệu được dùng.

## 13. Bài tập vận dụng

### Bài tập 1: Phân loại bốn candidate

Một ứng dụng có module JPA và MongoDB. Hãy phân tích:

1. Repository kế thừa JpaRepository, domain chỉ có @Entity.
2. Repository kế thừa CrudRepository, domain chỉ có @Document.
3. Repository kế thừa CrudRepository, domain không có dấu hiệu của module.
4. Repository kế thừa CrudRepository, domain mang cả @Entity và @Document.

Với mỗi trường hợp, giải thích dấu hiệu nào giúp phân loại hoặc điều gì khiến cấu hình chưa rõ. Không chỉ dựa vào tên interface.

### Bài tập 2: Tách phạm vi quét

Ứng dụng đang để cả hai cấu hình JPA và MongoDB quét package cha chứa mọi repository.

Hãy đề xuất bố cục package và hai phạm vi quét riêng. Giải thích vì sao sau khi tách package, domain và hệ interface vẫn cần mapping hoặc dấu hiệu module phù hợp.

### Bài tập 3: Phân biệt module và nguồn dữ liệu

Một repository đã chắc chắn là JPA nhưng ứng dụng có hai entity manager factory.

Giải thích tại sao strict repository configuration chưa chọn xong cơ sở dữ liệu vật lý cho repository đó. Nêu những liên kết cấu hình cần làm rõ tiếp theo.

### Bài tập 4: Đọc thông báo đúng ngữ cảnh

Log cho biết module JPA không thể gán an toàn một candidate có domain MongoDB. Sau đó MongoDB đăng ký candidate và service inject thành công.

Hãy xác định thông tin nào là chẩn đoán bình thường và những bằng chứng nào còn cần có trước khi kết luận thao tác dữ liệu hoạt động.

Một cấu hình nhiều store rõ ràng giữ được ba ranh giới: repository thuộc module nào, module đó sử dụng hạ tầng nào và nghiệp vụ phối hợp dữ liệu ra sao. Strict repository configuration hỗ trợ ranh giới đầu tiên; hai ranh giới còn lại cần được thiết kế và cấu hình theo khả năng thực tế của từng kho dữ liệu.