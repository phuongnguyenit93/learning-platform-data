# Ghép nhiều fragment vào một repository

Repository fragment cho phép mở rộng repository bằng các nhóm hành vi có hợp đồng và implementation riêng. Một repository có thể đồng thời cung cấp CRUD, tìm kiếm tùy chỉnh, thống kê và những khả năng khác mà không cần gom toàn bộ mã mở rộng vào một lớp lớn.

Trong Spring Data Commons, cơ chế này được xây dựng theo hướng composition: repository khai báo các interface fragment, còn Spring Data ghép các implementation phù hợp vào repository proxy. Việc ghép nhiều fragment tạo ra một đối tượng repository có nhiều khả năng, không tạo ra một chuỗi tự động chạy tất cả implementation.

## 1. Mục tiêu và phạm vi

Sau bài này, bạn có thể:

- Chia phần mở rộng repository thành nhiều hợp đồng có trách nhiệm rõ ràng.
- Khai báo một repository kế thừa nhiều interface fragment.
- Đặt tên và bố trí implementation để Spring Data phát hiện đúng.
- Phân biệt fragment, repository proxy và implementation CRUD của module.
- Giải thích cách xử lý phương thức trùng chữ ký.
- Thiết kế nơi phối hợp nhiều thao tác và ranh giới transaction phù hợp.

Cơ chế composition thuộc Commons. Các API truy cập dữ liệu như EntityManager, template hoặc client của một kho cụ thể thuộc module và công nghệ lưu trữ tương ứng.

Ví dụ thực hành trong bài dùng JPA để có implementation cụ thể. Những câu JPQL và annotation persistence trong ví dụ không phải yêu cầu chung cho mọi fragment Spring Data.

## 2. Cấu trúc của một repository ghép từ nhiều phần

Giả sử repository khách hàng cần ba nhóm khả năng:

| Nhóm khả năng | Thành phần cung cấp |
| --- | --- |
| CRUD cơ bản | Implementation repository của module |
| Tìm khách hàng đang kích hoạt theo quốc gia | Fragment CustomerSearch |
| Đếm khách hàng chưa kích hoạt theo quốc gia | Fragment CustomerStatistics |

Repository tổng hợp:

```java
public interface CustomerRepository
        extends CrudRepository<Customer, Long>,
                CustomerSearch,
                CustomerStatistics {
}
```

Hai quan hệ cần phân biệt:

- Java nhìn thấy CustomerRepository kế thừa toàn bộ hợp đồng phương thức.
- Spring Data cần có các implementation fragment tương ứng để thực thi phần tùy chỉnh.

Chỉ khai báo interface không tự tạo mã thực thi tùy chỉnh. Ngược lại, chỉ tạo một lớp implementation nhưng không ghép interface fragment vào repository cũng chưa làm các phương thức trở thành một phần API của repository đó.

### 2.1. Một proxy, nhiều điểm chuyển tiếp lời gọi

Có thể hình dung:

```text
Thành phần gọi
      |
      v
CustomerRepository proxy
      |
      +-- save / findById / delete ... --> repository cơ sở của module
      |
      +-- findActiveInCountry(...) ---> CustomerSearchImpl
      |
      +-- countInactiveInCountry(...) -> CustomerStatisticsImpl
```

Đây là sơ đồ trách nhiệm ở mức khái niệm. Không cần giả định proxy có một superclass do ứng dụng tự viết chứa tất cả các phương thức.

Khi gọi findActiveInCountry, Spring Data chuyển lời gọi đến implementation cung cấp phương thức đó. Nó không tự gọi tiếp countInactiveInCountry.

## 3. Thiết kế hai hợp đồng fragment

Một fragment nên biểu diễn một khả năng có tên và hành vi rõ ràng.

### 3.1. Hợp đồng tìm kiếm

```java
package com.example.customer;

import java.util.List;

public interface CustomerSearch {

    List<Customer> findActiveInCountry(String country);
}
```

### 3.2. Hợp đồng thống kê

```java
package com.example.customer;

public interface CustomerStatistics {

    long countInactiveInCountry(String country);
}
```

Hai phương thức phục vụ hai câu hỏi khác nhau:

- Danh sách khách hàng nào đang kích hoạt?
- Có bao nhiêu khách hàng chưa kích hoạt?

Không cần để implementation thống kê tải danh sách khách hàng rồi đếm. Mỗi fragment có thể chọn cách truy cập dữ liệu phù hợp với hợp đồng của nó.

Cũng không cần để CustomerStatistics kế thừa CustomerSearch chỉ vì chúng cùng truy cập Customer. Quan hệ kế thừa nên thể hiện nhu cầu hợp đồng thực sự, không chỉ sự trùng nhau về domain.

## 4. Bố trí interface và implementation

Với hậu tố implementation mặc định Impl, cấu trúc minh họa là:

```text
com.example.customer
  Customer.java
  CustomerRepository.java
  CustomerSearch.java
  CustomerSearchImpl.java
  CustomerStatistics.java
  CustomerStatisticsImpl.java
  CustomerReportService.java
```

Quan hệ tên cần chú ý:

```text
CustomerSearch       -> CustomerSearchImpl
CustomerStatistics   -> CustomerStatisticsImpl
```

Tên implementation được gắn với tên interface fragment. Không phải mọi phần tùy chỉnh đều phải đặt trong một lớp CustomerRepositoryImpl.

Cách tổ chức dựa trên nhiều interface fragment giúp tái sử dụng và phân chia trách nhiệm rõ ràng. Không nên lấy mô hình một implementation tùy chỉnh theo tên repository làm nền tảng để gom lại mọi khả năng.

### 4.1. Điều kiện phát hiện implementation

Ví dụ giả định:

- Repository scanning đã bao phủ package minh họa.
- Implementation nằm trong phạm vi mà cơ chế phát hiện fragment của module kiểm tra.
- Hậu tố implementation đang là giá trị mặc định Impl.
- Không có ứng viên implementation mơ hồ do trùng tên hoặc cấu hình bean khác.

Nếu dự án đã đổi hậu tố qua cấu hình repository của module, tên implementation phải khớp với cấu hình đó. Không suy hậu tố từ một dự án khác.

Implementation fragment là đối tượng được Spring quản lý trong quá trình tạo repository, nên có thể được inject các dependency phù hợp. Trong quy ước phát hiện mặc định, không cần thêm một annotation stereotype chỉ để lớp có hậu tố Impl được nhận diện như fragment.

Nếu đăng ký bean thủ công hoặc có nhiều ứng viên, phải đối chiếu thêm quy tắc tên bean và cách module lắp fragment. Ví dụ cơ bản cố ý dùng một ứng viên rõ ràng cho mỗi hợp đồng.

## 5. Implementation minh họa bằng JPA

Phần này giả định ứng dụng đã cấu hình Spring Data JPA, persistence provider, EntityManagerFactory và repository scanning phù hợp.

Ví dụ dùng namespace jakarta.persistence. Với một hệ JPA dùng namespace khác, cần dùng bộ API cùng module tương thích; không trộn hai hệ kiểu persistence.

### 5.1. Domain tối giản

```java
package com.example.customer;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class Customer {

    @Id
    private Long id;

    private String country;

    private boolean active;

    protected Customer() {
    }

    public Long getId() {
        return id;
    }

    public String getCountry() {
        return country;
    }

    public boolean isActive() {
        return active;
    }
}
```

Đây là model tối giản phục vụ truy vấn trong bài. Annotation đặt trên field nên ví dụ sử dụng field access của JPA. Cách tạo dữ liệu, cấp ID và các hành vi ghi cần được bổ sung theo mô hình của ứng dụng.

### 5.2. Implementation fragment tìm kiếm

```java
package com.example.customer;

import java.util.List;
import java.util.Objects;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;

import org.springframework.transaction.annotation.Transactional;

public class CustomerSearchImpl implements CustomerSearch {

    @PersistenceContext
    private EntityManager entityManager;

    @Override
    @Transactional(readOnly = true)
    public List<Customer> findActiveInCountry(String country) {
        Objects.requireNonNull(country, "country");

        return entityManager.createQuery(
            "select c from Customer c "
                + "where c.country = :country "
                + "and c.active = true "
                + "order by c.id",
            Customer.class
        )
        .setParameter("country", country)
        .getResultList();
    }
}
```

Fragment này chỉ thực hiện truy vấn danh sách. Sắp xếp theo ID giúp ví dụ có thứ tự rõ ràng; đó là quyết định của truy vấn, không phải hiệu ứng tự động của composition.

Tham số được truyền qua setParameter. Tên country trong JPQL là thuộc tính entity, không phải giả định về tên cột trong bảng.

### 5.3. Implementation fragment thống kê

```java
package com.example.customer;

import java.util.Objects;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;

import org.springframework.transaction.annotation.Transactional;

public class CustomerStatisticsImpl
        implements CustomerStatistics {

    @PersistenceContext
    private EntityManager entityManager;

    @Override
    @Transactional(readOnly = true)
    public long countInactiveInCountry(String country) {
        Objects.requireNonNull(country, "country");

        return entityManager.createQuery(
            "select count(c) from Customer c "
                + "where c.country = :country "
                + "and c.active = false",
            Long.class
        )
        .setParameter("country", country)
        .getSingleResult();
    }
}
```

Fragment thống kê yêu cầu số đếm trực tiếp thay vì tải các Customer rồi tính kích thước danh sách.

Hai implementation cùng dùng EntityManager không có nghĩa chúng cần kế thừa nhau. EntityManager được inject theo cấu hình JPA của ứng dụng. Nếu có nhiều persistence unit, cần cấu hình chọn đúng unit và transaction manager tương ứng.

## 6. Ghép hai fragment vào repository chính

```java
package com.example.customer;

import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long>,
                CustomerSearch,
                CustomerStatistics {
}
```

Repository này cung cấp đồng thời:

```text
Các phương thức từ CrudRepository
Các phương thức từ CustomerSearch
Các phương thức từ CustomerStatistics
```

Một thành phần gọi chỉ cần dependency vào CustomerRepository:

```java
List<Customer> active =
    customerRepository.findActiveInCountry("VN");

long inactiveCount =
    customerRepository.countInactiveInCountry("VN");
```

Thành phần gọi không cần tự tạo CustomerSearchImpl hoặc CustomerStatisticsImpl. Nếu tự new các lớp này, đối tượng sẽ không tự có EntityManager được inject hoặc các cơ chế quản lý cần thiết của Spring.

Thêm một fragment thứ ba có thể thực hiện bằng cách bổ sung hợp đồng và implementation tương ứng, rồi ghép interface đó vào repository. Không cần sửa implementation CRUD của module để mỗi lần có thêm một khả năng.

## 7. Phối hợp các fragment tại service

Composition làm các phương thức cùng xuất hiện trên repository, nhưng việc gọi nhiều phương thức theo một kịch bản nghiệp vụ vẫn cần được viết rõ ràng.

### 7.1. Kiểu kết quả báo cáo

```java
package com.example.customer;

import java.util.List;

public record CountryCustomerReport(
    String country,
    List<Customer> activeCustomers,
    long inactiveCount
) {
}
```

Ví dụ dùng cú pháp record của Java 17 trở lên. Có thể thay bằng DTO class thông thường.

### 7.2. Service điều phối

```java
package com.example.customer;

import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerReportService {

    private final CustomerRepository customers;

    public CustomerReportService(
            CustomerRepository customers) {
        this.customers = customers;
    }

    @Transactional(readOnly = true)
    public CountryCustomerReport report(String country) {
        if (country == null || country.isBlank()) {
            throw new IllegalArgumentException(
                "Quốc gia không được để trống"
            );
        }

        List<Customer> active =
            customers.findActiveInCountry(country);

        long inactive =
            customers.countInactiveInCountry(country);

        return new CountryCustomerReport(
            country,
            active,
            inactive
        );
    }
}
```

Service nhận một repository nhưng sử dụng hai khả năng. Đây là nơi thể hiện rõ việc phối hợp, thay vì khiến hai implementation fragment phụ thuộc vòng vào nhau.

### 7.3. Một transaction không mặc nhiên là một snapshot

Khi cấu hình transaction JPA phù hợp và lời gọi đi qua proxy cần thiết, transaction của service có thể bao phủ hai lần đọc.

Tuy nhiên:

- Ghép fragment không tự tạo transaction chung cho nhiều lời gọi.
- Hai lời gọi có thể là hai truy vấn riêng.
- Khả năng nhìn thấy cùng một snapshot phụ thuộc mức cô lập và kho dữ liệu.
- Thuộc tính readOnly không tự tạo mọi bảo đảm nhất quán hoặc cấm mọi thay đổi ở tất cả provider.

Annotation transaction trên từng implementation giúp diễn đạt nhu cầu khi gọi riêng lẻ, còn thao tác phối hợp cần ranh giới phù hợp với nghiệp vụ.

Nếu có nhiều transaction manager hoặc nhiều nguồn dữ liệu, phải xác định rõ manager nào quản lý thao tác. Chỉ gọi qua cùng một repository interface không tự tạo transaction phân tán.

## 8. Kết quả logic trên dữ liệu minh họa

Giả sử dữ liệu:

| id | country | active |
| --- | --- | --- |
| 1 | VN | true |
| 2 | VN | false |
| 3 | VN | true |
| 4 | TH | false |

Các kết quả mong đợi:

| Lời gọi | Kết quả |
| --- | --- |
| findActiveInCountry("VN") | Danh sách ID 1 và 3 theo thứ tự tăng dần |
| countInactiveInCountry("VN") | 1 |
| findActiveInCountry("JP") | Danh sách rỗng |
| countInactiveInCountry("JP") | 0 |
| report("VN") | Báo cáo chứa danh sách ID 1, 3 và số chưa kích hoạt bằng 1 |

Lời gọi report có hai thao tác được service viết rõ. Không phải lời gọi tìm kiếm tự kích hoạt fragment thống kê.

Ví dụ giả định tập dữ liệu ổn định trong thời điểm đối chiếu. Với tập lớn, hợp đồng tìm kiếm cần xem xét giới hạn hoặc phân trang; composition không tự thêm phân trang cho một phương thức trả List.

## 9. Khi hai fragment có cùng chữ ký phương thức

### 9.1. Trùng hợp đồng có thể hợp lệ về mặt Java

Xét ví dụ độc lập với hai fragment:

```java
interface PrimaryLabel {
    String label();
}

interface SecondaryLabel {
    String label();
}
```

Repository ghép chúng:

```java
interface CustomerLabelRepository
        extends Repository<Customer, Long>,
                PrimaryLabel,
                SecondaryLabel {
}
```

Ở đây Repository là `org.springframework.data.repository.Repository`. Giả định cả hai fragment có implementation được phát hiện đúng và cùng cung cấp label.

Trong cơ chế composition, thứ tự các fragment được khai báo có vai trò giải quyết trường hợp nhiều implementation cung cấp cùng chữ ký. Với cấu trúc minh họa, PrimaryLabel đứng trước nên implementation của nó được ưu tiên cho lời gọi label.

Đổi thứ tự có thể làm thay đổi implementation được chọn mà không đổi tên phương thức. Vì vậy, thứ tự interface không còn chỉ là cách trình bày khi tồn tại chữ ký trùng.

### 9.2. Đây là chọn implementation, không phải chạy tuần tự

Một lần gọi label không tự chạy PrimaryLabelImpl rồi SecondaryLabelImpl. Nó được chuyển đến implementation phù hợp theo quy tắc composition.

Nếu nghiệp vụ cần kết hợp hai kết quả, hãy đặt tên phương thức khác nhau hoặc viết một phương thức điều phối rõ ràng. Không dựa vào vị trí trong danh sách extends để biểu diễn một pipeline.

### 9.3. Java vẫn phải chấp nhận hợp đồng trước

Cơ chế Spring Data không sửa được mọi xung đột kế thừa:

- Hai phương thức có kiểu trả về không tương thích có thể làm interface không biên dịch.
- Xung đột default method cần được giải quyết theo quy tắc của Java.
- Các overload khác danh sách tham số là những phương thức khác nhau.
- Chữ ký sau khi xét generic cũng cần được kiểm tra cẩn thận.

Chỉ sau khi hợp đồng Java hợp lệ mới có ý nghĩa xét Spring Data sẽ chuyển lời gọi đến implementation nào.

Ưu tiên thiết kế tránh trùng tên/chữ ký ngoài ý muốn. Nếu chủ động dùng tính ưu tiên để thay thế hành vi, phải mô tả mục đích và giữ kiểm chứng phù hợp.

## 10. Trùng với phương thức của repository cơ sở

Fragment tùy chỉnh có thể cung cấp phương thức trùng với hành vi repository cơ sở. Trong composition, implementation tùy chỉnh có mức ưu tiên để thay thế phương thức tương ứng của repository cơ sở.

Ví dụ một hợp đồng tùy chỉnh có thể khai báo đúng chữ ký generic của save:

```java
interface CustomerSaveCustomization {

    <S extends Customer> S save(S entity);
}
```

Nếu ghép fragment này cùng CrudRepository và cung cấp implementation phù hợp, đây là quyết định thay đổi hành vi save, không chỉ là bổ sung một tên phương thức mới.

Cần đặc biệt chú ý:

- Giữ đúng chữ ký và hợp đồng mà thành phần gọi kỳ vọng.
- Xác định transaction cùng cách lưu dữ liệu thực tế.
- Không gọi ngược customerRepository.save từ chính implementation đang thay thế save với kỳ vọng tự chuyển đến bản gốc; lời gọi có thể quay lại chính fragment.
- Không giả định method tùy chỉnh được gọi xong thì base repository sẽ tự chạy tiếp.

Nếu cần thay đổi hành vi cơ sở cho cả một nhóm repository, custom base repository là một lựa chọn thiết kế khác. Không nên mở rộng việc override cục bộ thành một cơ chế toàn hệ thống chỉ bằng các chữ ký trùng không được quản lý.

## 11. Tái sử dụng các fragment đã thiết kế

Một repository khác cho cùng domain có thể chọn lại các khả năng cần dùng:

```java
package com.example.customer;

import org.springframework.data.repository.Repository;

public interface CustomerReadRepository
        extends Repository<Customer, Long>,
                CustomerSearch,
                CustomerStatistics {
}
```

CustomerReadRepository chỉ công khai những khả năng của hai fragment trong ví dụ, còn CustomerRepository trước đó công khai thêm CRUD.

Đây là tái sử dụng hợp đồng và implementation theo composition. Hai interface repository không vì vậy trở thành cùng một bean repository.

Cũng không mặc định mỗi repository có một instance fragment riêng. Bean implementation có thể được dùng chung theo cấu hình và cơ chế lắp ghép của ứng dụng.

Vì vậy, tránh giữ dữ liệu của một lần gọi trong field của fragment:

```text
Không giữ country hiện tại trong một field để truy vấn sau.
Không giữ danh sách kết quả của request trước.
Dùng tham số phương thức và biến cục bộ cho dữ liệu từng lần gọi.
```

Dependency được quản lý như EntityManager trong ví dụ có vòng đời do hạ tầng quyết định; nó không phải nơi lưu trạng thái tìm kiếm của người dùng.

### 11.1. Tái sử dụng không tự làm implementation độc lập kho dữ liệu

Một fragment dùng EntityManager và JPQL vẫn phụ thuộc JPA. Ghép cùng interface đó vào repository của loại kho khác không tự chuyển JPQL thành lệnh phù hợp với kho mới.

Có thể giữ hợp đồng nghiệp vụ tương tự nhưng cần implementation khác, được lựa chọn và cấu hình đúng theo module.

Tương tự, nếu thiết kế fragment generic, ứng dụng cần xác định đúng domain type, mapping và các dependency mà implementation dùng. Một tham số kiểu T không tự làm các câu truy vấn cụ thể trở thành tổng quát.

## 12. Tránh phụ thuộc vòng giữa các fragment

Một thiết kế dễ gây khó hiểu là:

```text
CustomerSearchImpl cần CustomerRepository
CustomerRepository cần lắp CustomerSearchImpl
```

Tùy cách khởi tạo và proxy, thiết kế đó có thể gây phụ thuộc vòng hoặc khiến lời gọi quay lại chính phương thức đang xử lý.

Nếu hai fragment cần dùng chung một phần tính toán hoặc truy cập dữ liệu, cân nhắc tách dependency dùng chung:

```text
CustomerSearchImpl --------+
                          +--> helper hoặc thành phần truy cập chung
CustomerStatisticsImpl ---+
```

Nếu cần phối hợp nhiều hành vi thành một kịch bản, service như CustomerReportService là vị trí rõ ràng.

Không dùng việc inject repository tổng hợp vào chính fragment như một cách mặc định để truy cập implementation cơ sở. Cần hiểu chính xác đường chuyển tiếp lời gọi trước khi thiết kế delegation.

## 13. Khi nào nên dùng nhiều fragment?

| Nhu cầu | Điểm bắt đầu phù hợp |
| --- | --- |
| Một truy vấn đơn giản diễn đạt rõ bằng tên phương thức | Derived query của module |
| Một câu truy vấn riêng có thể khai báo trực tiếp | Cơ chế query annotation phù hợp của module |
| Một nhóm truy vấn tùy chỉnh cùng trách nhiệm | Một fragment |
| Nhiều nhóm khả năng độc lập cần ghép vào repository | Nhiều fragment |
| Điều phối nhiều repository hoặc dịch vụ thành một nghiệp vụ | Service |
| Thay đổi hành vi cơ sở cho nhiều repository | Cơ chế custom base repository phù hợp |

Hai truy vấn JPA trong bài được giữ đơn giản để minh họa cách lắp ghép. Một ứng dụng thực tế có thể diễn đạt chúng bằng derived queries mà không cần custom implementation.

Giá trị của fragment rõ hơn khi có logic tùy chỉnh, API kho dữ liệu chuyên biệt hoặc một nhóm hành vi cần tái sử dụng. Không cần tạo một fragment mới cho từng phương thức nếu các phương thức đó thuộc cùng một trách nhiệm.

## 14. Chẩn đoán khi repository không được ghép đúng

| Triệu chứng | Điều cần kiểm tra |
| --- | --- |
| Repository không có phương thức custom ở compile time | Interface repository đã extends interface fragment chưa |
| Spring cố phân tích phương thức custom như derived query | Implementation fragment có được phát hiện và lắp đúng không |
| Báo lỗi không tìm thấy thuộc tính từ một tên phương thức tùy chỉnh | Kiểm tra discovery trước khi kết luận tên truy vấn sai |
| Implementation không được chọn | Tên lớp, hậu tố, package và cấu hình repository scanning |
| Có nhiều ứng viên implementation | Quy tắc tên bean và đăng ký implementation tường minh |
| EntityManager null trong đối tượng tự tạo | Có đang new implementation ngoài Spring hay không |
| Gọi một phương thức nhưng chạy implementation khác mong đợi | Chữ ký trùng và thứ tự fragment |
| Lời gọi lặp hoặc phụ thuộc vòng | Fragment có gọi ngược repository đang chứa nó không |
| Hai thao tác không cùng transaction | Ranh giới service, transaction manager và cách đi qua proxy |
| Chạy được trên module này nhưng lỗi trên module khác | Implementation có phụ thuộc API hoặc mapping của kho cụ thể không |

Có hai tầng cần xác minh riêng:

1. **Lắp ghép:** repository có đúng fragment và chuyển lời gọi đúng implementation.
2. **Truy cập dữ liệu:** implementation có query, mapping, transaction và dependency đúng.

Một lỗi ở câu JPQL không có nghĩa composition sai. Ngược lại, một implementation query đúng vẫn không giúp repository hoạt động nếu implementation chưa được phát hiện.

## 15. Các điểm cần hiểu khi thay đổi cấu trúc

Khi bổ sung hoặc sắp xếp lại fragment:

- Kiểm tra tên phương thức và chữ ký có trùng với fragment khác hoặc repository cơ sở không.
- Nếu có trùng, xác định rõ implementation nào được chọn và vì sao.
- Giữ cùng trách nhiệm trong một fragment để hợp đồng dễ hiểu.
- Đặt logic phối hợp nhiều thao tác ở nơi thể hiện rõ trình tự và transaction.
- Kiểm tra khả năng phát hiện implementation theo đúng cấu hình module.
- Xác định phạm vi tái sử dụng thật sự của implementation.

Các điểm trên giúp đánh giá thay đổi composition. Những thuộc tính như độ đúng của truy vấn, tải quan hệ và hiệu năng vẫn cần được xem xét trên kho dữ liệu thực tế.

## 16. Bài tập tự kiểm tra

1. CustomerRepository cần khai báo gì để có cả phương thức tìm kiếm và thống kê trong bài?
2. Tạo CustomerSearchImpl nhưng không ghép CustomerSearch vào repository có tự thêm phương thức vào API repository không?
3. Gọi findActiveInCountry có tự gọi countInactiveInCountry sau đó không?
4. Vì sao tên CustomerSearchImpl liên quan đến CustomerSearch, thay vì bắt buộc đặt mọi mã trong CustomerRepositoryImpl?
5. Nếu hai fragment custom cùng cung cấp một chữ ký hợp lệ, yếu tố nào cần xét để biết implementation được ưu tiên?
6. Vì sao một service gọi hai fragment cần tự xác định ranh giới transaction?
7. Có thể dùng nguyên implementation JPQL này cho mọi module Spring Data không?
8. Nếu phương thức custom bị phân tích như derived query, nên kiểm tra điều gì trước?

Gợi ý đáp án:

1. Kế thừa cả CustomerSearch và CustomerStatistics, đồng thời có các implementation tương ứng được phát hiện.
2. Không. API repository cần ghép hợp đồng fragment.
3. Không. Mỗi lời gọi được chuyển đến implementation của phương thức đó.
4. Vì mô hình fragment gắn implementation với từng hợp đồng khả năng, giúp ghép nhiều phần độc lập.
5. Thứ tự các fragment tùy chỉnh trong composition, cùng các quy tắc ưu tiên liên quan.
6. Composition chỉ ghép khả năng, không tự gom nhiều lời gọi thành một đơn vị transaction.
7. Không. JPQL và EntityManager là phần phụ thuộc JPA.
8. Kiểm tra tên implementation, hậu tố, phạm vi phát hiện và việc ghép fragment.

Nguyên tắc áp dụng là chia hợp đồng theo khả năng, cung cấp implementation tương ứng rồi ghép chúng qua repository interface. Trình tự nghiệp vụ, transaction và khả năng của kho dữ liệu cần được thiết kế rõ bên cạnh cơ chế composition.
