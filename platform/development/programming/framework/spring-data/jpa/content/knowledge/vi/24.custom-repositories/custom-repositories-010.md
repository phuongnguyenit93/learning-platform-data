# Kiểm thử repository fragment và bảo đảm cấu hình được áp dụng

Repository fragment cho phép bổ sung hành vi tùy biến vào repository Spring Data JPA bằng cách ghép một interface với lớp triển khai tương ứng. Một bài kiểm thử tốt cần chứng minh ba việc: Spring Data đã ghép đúng fragment vào repository proxy, cấu hình repository tùy biến đã được nạp trong application context, và phương thức fragment thực sự truy vấn dữ liệu qua JPA.

Bài viết dùng Java 17+, Spring Boot 3.x, Spring Data JPA, JUnit 5, AssertJ và H2 cho ví dụ kiểm thử. Các lớp dưới đây là mã nguồn của một dự án Spring Boot có dependency JPA và test phù hợp; chúng không phải một chương trình Java độc lập có thể chạy chỉ bằng `javac`.

## 1. Hiểu đúng repository fragment

Một fragment gồm hai thành phần:

- Interface khai báo hành vi tùy biến.
- Lớp triển khai thực hiện hành vi đó.

Repository chính kế thừa cả `JpaRepository` và interface fragment. Spring Data tạo repository proxy bằng cách ghép phần triển khai CRUD mặc định với các fragment đã phát hiện.

Ví dụ cấu trúc package:

```text
com.example.customer
├── Customer.java
├── CustomerRepository.java
├── CustomerSearch.java
├── CustomerSearchExtension.java
└── CustomerJpaRepositoryConfig.java
```

Tên lớp triển khai được tạo từ tên interface fragment cộng với hậu tố cấu hình. Hậu tố mặc định là `Impl`; ví dụ `CustomerSearch` thường đi với `CustomerSearchImpl`. Nếu cấu hình hậu tố là `Extension`, lớp triển khai phải có tên `CustomerSearchExtension`.

Lớp triển khai phải nằm trong phạm vi package mà Spring Data quét để tìm repository implementation. Cách dễ kiểm soát nhất là đặt repository, fragment interface và lớp triển khai trong cùng package hoặc trong các package con thuộc phạm vi quét.

Fragment khác với custom repository base class. Fragment bổ sung một nhóm hành vi vào repository cụ thể; `repositoryBaseClass` thay đổi lớp nền dùng chung cho các repository được cấu hình. Không dùng hai cơ chế này thay thế cho nhau.

## 2. Tạo entity, fragment và repository

**Customer.java**

```java
package com.example.customer;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    protected Customer() {
        // JPA cần constructor không tham số.
    }

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

**CustomerSearch.java** — interface fragment:

```java
package com.example.customer;

import java.util.List;

public interface CustomerSearch {
    List<Customer> findByNamePrefix(String prefix);
}
```

Tên phương thức `findByNamePrefix` ở đây cố ý không tương ứng với thuộc tính của entity: `Customer` chỉ có thuộc tính `name`, không có `namePrefix`. Vì vậy, phương thức chỉ hoạt động khi Spring Data tìm thấy và ghép đúng fragment implementation. Đây là cách giúp bài test phát hiện lỗi wiring thay vì vô tình chạy một derived query khác.

**CustomerSearchExtension.java** — lớp triển khai fragment:

```java
package com.example.customer;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import java.util.List;

public class CustomerSearchExtension implements CustomerSearch {

    @PersistenceContext
    private EntityManager entityManager;

    @Override
    public List<Customer> findByNamePrefix(String prefix) {
        if (prefix == null || prefix.isBlank()) {
            throw new IllegalArgumentException("prefix must not be blank");
        }

        return entityManager.createQuery(
                "select c from Customer c "
                    + "where c.name like :pattern "
                    + "order by c.name",
                Customer.class
            )
            .setParameter("pattern", prefix + "%")
            .getResultList();
    }
}
```

Spring quản lý lớp fragment được phát hiện trong quá trình tạo repository. Vì vậy, có thể tiêm `EntityManager` bằng `@PersistenceContext`; không tự tạo implementation bằng `new CustomerSearchExtension()`. Nếu implementation cần thêm dependency, hãy để Spring tiêm dependency đó qua cơ chế phù hợp.

**CustomerRepository.java** — ghép fragment vào repository:

```java
package com.example.customer;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
        extends JpaRepository<Customer, Long>, CustomerSearch {
}
```

Khi repository được tạo, lời gọi `findByNamePrefix` được chuyển tới fragment `CustomerSearch`. Các phương thức CRUD vẫn được cung cấp bởi `JpaRepository`.

## 3. Khai báo cấu hình repository cần kiểm thử

Trong ví dụ này, ta đổi hậu tố implementation từ mặc định `Impl` thành `Extension`. Cấu hình đó phải khớp với tên lớp `CustomerSearchExtension`.

**CustomerJpaRepositoryConfig.java**

```java
package com.example.customer;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@Configuration(proxyBeanMethods = false)
@EnableJpaRepositories(
    basePackageClasses = CustomerRepository.class,
    repositoryImplementationPostfix = "Extension"
)
public class CustomerJpaRepositoryConfig {
}
```

`basePackageClasses` yêu cầu Spring Data quét package chứa `CustomerRepository`. Trong ví dụ, fragment interface và implementation nằm cùng package nên cũng nằm trong phạm vi phát hiện. Nếu đặt implementation ở package khác, cần điều chỉnh cấu trúc hoặc phạm vi quét để Spring Data có thể tìm thấy nó.

Trong ứng dụng Spring Boot, cấu hình `@EnableJpaRepositories` có thể đã nằm trong cấu hình production. Khi đó, bài test nên nạp đúng lớp cấu hình production. Không tạo thêm một cấu hình quét repository thứ hai nếu ứng dụng đã có cấu hình tương ứng.

## 4. Viết integration test cho fragment

Dùng `@DataJpaTest` để kiểm thử repository trong một Spring context tập trung vào JPA. Annotation này cấu hình entity, repository và transaction kiểm thử; khi H2 có trong test classpath, Spring Boot thường dùng cơ sở dữ liệu nhúng. Bài test được rollback sau mỗi phương thức kiểm thử.

**CustomerRepositoryTest.java**

```java
package com.example.customer;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.context.annotation.Import;

@DataJpaTest
@Import(CustomerJpaRepositoryConfig.class)
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void composesCustomFragmentAndUsesConfiguredPostfix() {
        entityManager.persist(new Customer("Anna"));
        entityManager.persist(new Customer("Bao"));
        entityManager.persist(new Customer("An"));

        // Đẩy thay đổi xuống database trước khi chạy truy vấn.
        entityManager.flush();

        // Xóa persistence context để kết quả phải được đọc lại qua JPA.
        entityManager.clear();

        List<String> actualNames = repository.findByNamePrefix("An")
            .stream()
            .map(Customer::getName)
            .toList();

        assertThat(actualNames).containsExactly("An", "Anna");
    }
}
```

Có ba điểm quan trọng trong bài test:

1. `@Import(CustomerJpaRepositoryConfig.class)` nạp cấu hình repository cần kiểm thử vào test context. Test slice có phạm vi hẹp, vì vậy một lớp cấu hình ứng dụng thông thường có thể không được tự động nạp.
2. Cấu hình đặt hậu tố là `Extension`, còn implementation có tên `CustomerSearchExtension`. Nếu đổi một bên mà quên đổi bên kia, Spring Data sẽ không tìm thấy implementation đúng.
3. Test gọi trực tiếp `repository.findByNamePrefix("An")` và kiểm tra kết quả truy vấn. Vì entity không có thuộc tính `namePrefix`, lời gọi thành công với dữ liệu chính xác chứng minh fragment đã được ghép và thực thi. `flush()` bảo đảm dữ liệu test được gửi xuống database; `clear()` loại entity đang được giữ trong persistence context trước khi truy vấn.

Kết quả mong đợi là test thành công với danh sách tên theo thứ tự `An`, `Anna`. Không cần thêm `System.out.println`; assertion mới là bằng chứng kiểm thử. Đây là integration test chạy trong Spring context, không phải unit test thuần Java.

## 5. Bảo đảm test đang dùng đúng cấu hình

Khi kiểm thử cấu hình repository, hãy xác định rõ cấu hình nào cần được chứng minh:

- Nếu cần kiểm tra fragment discovery, xác nhận repository kế thừa interface fragment, implementation có đúng tên hậu tố và nằm trong package được quét.
- Nếu ứng dụng đặt `repositoryImplementationPostfix`, bài test phải nạp cấu hình chứa thuộc tính đó. Trong ví dụ, `@Import` làm việc này một cách tường minh.
- Nếu cấu hình repository nằm trong application configuration và cần kiểm thử toàn bộ wiring của ứng dụng, có thể dùng `@SpringBootTest`. Cách này tải application context đầy đủ và thường chậm hơn `@DataJpaTest`.
- Nếu dùng `@DataJpaTest` với cấu hình production, import đúng cấu hình cần kiểm thử. Không khai báo một `@EnableJpaRepositories` mới trong test chỉ để làm test chạy, vì như vậy test có thể kiểm tra một cấu hình khác với cấu hình thực tế.
- Nếu cần kiểm tra hành vi phụ thuộc vào hệ quản trị cơ sở dữ liệu cụ thể, hãy chạy test với cùng loại database hoặc Testcontainers. H2 hữu ích cho kiểm thử nhanh nhưng không chứng minh mọi khác biệt về dialect, collation, kiểu dữ liệu hay locking của database production.

Nếu ứng dụng dùng custom base class thay vì fragment, cấu hình thường dùng thuộc tính `repositoryBaseClass` của `@EnableJpaRepositories`. Khi đó, bài test cần gọi một hành vi chỉ có trong base class hoặc kiểm tra tác động của hành vi đó. Chỉ xác nhận context khởi động thành công chưa đủ để chứng minh base class mong muốn đã được áp dụng.

## 6. Các lỗi thường gặp và cách khoanh vùng

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Context báo không tạo được query hoặc không tìm thấy thuộc tính `namePrefix` | Fragment implementation chưa được phát hiện nên Spring Data thử xử lý phương thức như derived query | Kiểm tra repository có extends `CustomerSearch`; tên implementation và hậu tố có khớp; package có nằm trong phạm vi quét |
| Fragment không được ghép dù class đã tồn tại | Tên class sai, hậu tố cấu hình không khớp hoặc class nằm ngoài package scan | So sánh tên interface, tên implementation và `repositoryImplementationPostfix`; kiểm tra `basePackageClasses` hoặc `basePackages` |
| `EntityManager` hoặc dependency trong implementation không được tiêm | Implementation không được Spring quản lý đúng cách hoặc dependency chưa có bean | Để Spring Data phát hiện implementation; dùng `@PersistenceContext` hoặc constructor injection; không tự gọi `new` |
| Test chạy trong `@SpringBootTest` nhưng lỗi trong `@DataJpaTest` | Test slice không nạp lớp cấu hình ứng dụng cần thiết | Dùng `@Import` cho cấu hình cụ thể hoặc dùng `@SpringBootTest` khi cần full context |
| Kết quả test không phản ánh dữ liệu vừa persist | Chưa flush hoặc persistence context còn giữ entity | Gọi `flush()` trước truy vấn; dùng `clear()` khi cần kiểm tra việc đọc lại từ database |
| Test luôn pass dù fragment bị bỏ qua | Phương thức fragment trùng với một derived query hợp lệ hoặc repository đã bị mock | Dùng tên phương thức chỉ được xử lý bởi fragment và giữ repository thật trong integration test |

Không nên mock `CustomerRepository` trong bài test này. Mock repository chỉ xác nhận hành vi của mock, không kiểm tra Spring Data composition, query JPA hay cấu hình discovery. Có thể mock một dịch vụ bên ngoài mà fragment phụ thuộc vào, nhưng repository và JPA context cần được giữ thật nếu mục tiêu là kiểm thử wiring.

## 7. Chạy và mở rộng kiểm thử

Với Maven Wrapper:

```bash
./mvnw -Dtest=CustomerRepositoryTest test
```

Trên Windows:

```bat
mvnw.cmd -Dtest=CustomerRepositoryTest test
```

Với Gradle Wrapper:

```bash
./gradlew test --tests "com.example.customer.CustomerRepositoryTest"
```

Kết quả mong đợi là một test được thực thi và không có failure. Output chi tiết phụ thuộc phiên bản Maven/Gradle và cấu hình dự án, vì vậy hãy dựa vào trạng thái test report và assertion.

Có thể mở rộng bộ test theo các trường hợp có ý nghĩa:

- Prefix rỗng hoặc `null`: xác nhận quy tắc validation của fragment.
- Không có bản ghi phù hợp: xác nhận kết quả là danh sách rỗng.
- Nhiều bản ghi có cùng prefix: xác nhận thứ tự và tính ổn định của kết quả.
- Dữ liệu có ký tự tiếng Việt hoặc quy tắc collation đặc thù: kiểm thử trên database tương ứng nếu hành vi phụ thuộc hệ quản trị.
- Fragment dùng thêm bean cấu hình: xác nhận bean đó được import hoặc được tạo trong application context và kiểm tra kết quả quan sát được khi gọi phương thức.

Một bài kiểm thử fragment đạt yêu cầu khi nó chứng minh được repository proxy đã ghép đúng implementation, cấu hình discovery thực tế đã được nạp và hành vi tùy biến trả về kết quả đúng từ persistence layer.