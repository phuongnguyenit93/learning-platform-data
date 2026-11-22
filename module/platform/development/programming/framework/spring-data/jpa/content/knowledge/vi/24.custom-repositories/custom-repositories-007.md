# Tùy chỉnh lớp Repository cơ sở với `repositoryBaseClass`

Spring Data JPA tạo repository dưới dạng proxy và mặc định dùng `SimpleJpaRepository` để cung cấp các thao tác CRUD như `save`, `findById`, `findAll` và `delete`. Khi nhiều repository cần cùng một hành vi bổ sung hoặc cần thay đổi cách một thao tác chung hoạt động, ta có thể tạo lớp triển khai cơ sở riêng rồi cấu hình bằng thuộc tính `repositoryBaseClass` của `@EnableJpaRepositories`.

Cách này phù hợp với hành vi dùng chung cho nhiều repository trong cùng một vùng cấu hình. Nếu một phương thức chỉ thuộc về một repository hoặc một nhóm nhỏ repository, repository fragment thường linh hoạt hơn.

## 1. Phân biệt interface repository và lớp triển khai cơ sở

Một repository thường có hai phần:

- **Repository interface** khai báo các thao tác mà ứng dụng được phép gọi.
- **Lớp triển khai cơ sở** cung cấp phần cài đặt dùng chung cho các repository được Spring Data tạo proxy.

`repositoryBaseClass` cho Spring Data JPA biết lớp nào sẽ làm lớp nền thay cho triển khai mặc định. Lớp tùy chỉnh thường kế thừa `SimpleJpaRepository`, nhờ đó vẫn giữ được các thao tác CRUD có sẵn và chỉ cần bổ sung hoặc ghi đè hành vi cần thiết.

## 2. Khai báo interface cơ sở

Tạo một interface generic để các repository cụ thể cùng kế thừa. Ví dụ dưới đây bổ sung phương thức lưu entity rồi tải lại trạng thái từ cơ sở dữ liệu.

```java
package com.example.data;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface BaseRepository<T, ID> extends JpaRepository<T, ID> {

    <S extends T> S saveAndRefresh(S entity);
}
```

`T` là kiểu entity và `ID` là kiểu khóa chính. `@NoRepositoryBean` báo cho Spring Data rằng đây là interface nền, không phải repository độc lập cần tạo bean. Nếu bỏ annotation này, Spring có thể cố tạo repository cho kiểu generic chưa được gắn với một entity cụ thể.

Phương thức `saveAndRefresh` được khai báo ở interface để các repository cụ thể có thể gọi nó thông qua kiểu repository của mình.

## 3. Viết lớp triển khai cơ sở

Tạo lớp kế thừa `SimpleJpaRepository` và triển khai interface vừa khai báo:

```java
package com.example.data;

import jakarta.persistence.EntityManager;
import org.springframework.data.jpa.repository.support.JpaEntityInformation;
import org.springframework.data.jpa.repository.support.SimpleJpaRepository;
import org.springframework.transaction.annotation.Transactional;

public class BaseRepositoryImpl<T, ID>
        extends SimpleJpaRepository<T, ID>
        implements BaseRepository<T, ID> {

    private final EntityManager entityManager;

    public BaseRepositoryImpl(
            JpaEntityInformation<T, ?> entityInformation,
            EntityManager entityManager) {
        super(entityInformation, entityManager);
        this.entityManager = entityManager;
    }

    @Override
    @Transactional
    public <S extends T> S saveAndRefresh(S entity) {
        S saved = save(entity);
        entityManager.flush();
        entityManager.refresh(saved);
        return saved;
    }
}
```

Constructor nhận `JpaEntityInformation` và `EntityManager`, sau đó chuyển cả hai cho constructor của `SimpleJpaRepository`. Spring Data sử dụng thông tin entity để biết repository đang thao tác với kiểu domain nào; `EntityManager` thực hiện các thao tác JPA.

Phương thức `saveAndRefresh` thực hiện ba bước:

1. Gọi `save` và giữ lại entity mà JPA trả về. Điều này quan trọng vì khi lưu một entity detached, `save` có thể trả về một instance đã được merge.
2. Gọi `flush` để đồng bộ các thay đổi đang chờ xuống cơ sở dữ liệu.
3. Gọi `refresh` để nạp lại trạng thái của entity từ cơ sở dữ liệu, rồi trả về instance đã lưu.

`@Transactional` bảo đảm phương thức chạy trong transaction. `refresh` cần entity đang được quản lý bởi persistence context; vì vậy ví dụ sử dụng kết quả trả về từ `save`, thay vì tiếp tục dùng tham chiếu đầu vào.

Ví dụ này hữu ích khi cần đọc lại giá trị do cơ sở dữ liệu tạo ra sau khi ghi, chẳng hạn giá trị được cập nhật bởi trigger. Hãy nhớ rằng `refresh` nạp lại dữ liệu từ database và có thể ghi đè những thay đổi mới chỉ tồn tại trong bộ nhớ.

> Với Spring Boot 2 / Spring Data JPA 2, dùng `javax.persistence.EntityManager`. Với Spring Boot 3 trở lên, dùng `jakarta.persistence.EntityManager` như ví dụ.

## 4. Cấu hình `repositoryBaseClass`

Khai báo lớp triển khai trong cấu hình repository:

```java
package com.example;

import com.example.data.BaseRepositoryImpl;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@SpringBootApplication
@EnableJpaRepositories(
        basePackages = "com.example.repository",
        repositoryBaseClass = BaseRepositoryImpl.class
)
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

Hai thuộc tính cần chú ý:

- `basePackages` xác định package mà Spring Data quét để tìm repository interface.
- `repositoryBaseClass` chỉ định lớp triển khai cơ sở được sử dụng cho các repository tìm thấy trong vùng quét đó.

Nếu dự án đã có `@EnableJpaRepositories`, hãy bổ sung `repositoryBaseClass` vào cấu hình hiện tại và giữ đúng phạm vi package đang sử dụng. Tránh tạo thêm cấu hình quét trùng cùng một repository. Với dự án có nhiều `EntityManagerFactory` hoặc nhiều nhóm repository, hãy cấu hình lớp cơ sở trong đúng khai báo `@EnableJpaRepositories` tương ứng.

## 5. Cho repository cụ thể kế thừa interface cơ sở

Ví dụ entity `Customer` đã được khai báo là một JPA entity. Repository của entity đó chỉ cần kế thừa `BaseRepository`:

```java
package com.example.repository;

import com.example.data.BaseRepository;
import com.example.domain.Customer;

public interface CustomerRepository
        extends BaseRepository<Customer, Long> {
}
```

Ứng dụng có thể gọi cả CRUD kế thừa từ `JpaRepository` lẫn phương thức bổ sung:

```java
Customer saved = customerRepository.saveAndRefresh(customer);
```

Không cần viết lại `save`, `findById` hay các phương thức CRUD khác. Proxy repository do Spring Data tạo sẽ sử dụng `BaseRepositoryImpl` làm lớp nền; phương thức `saveAndRefresh` được thực thi bởi lớp này.

Lưu ý: repository cụ thể phải kế thừa `BaseRepository` thì phương thức `saveAndRefresh` mới xuất hiện trong kiểu Java của repository đó. Chỉ thêm phương thức vào lớp triển khai mà không khai báo trong interface sẽ không làm phương thức đó trở thành API có thể gọi qua interface repository.

## 6. Phạm vi ảnh hưởng và lựa chọn giải pháp

`repositoryBaseClass` áp dụng cho tất cả repository được phát hiện bởi khai báo `@EnableJpaRepositories` tương ứng. Vì vậy, chỉ đưa vào lớp cơ sở những phương thức thật sự có ý nghĩa chung cho nhóm repository đó.

| Nhu cầu | Giải pháp phù hợp |
|---|---|
| Bổ sung hành vi dùng chung cho nhiều repository | Interface cơ sở và `repositoryBaseClass` |
| Thay đổi cách triển khai một thao tác chung như `save` | Ghi đè phương thức trong lớp kế thừa `SimpleJpaRepository` |
| Thêm hành vi riêng cho một repository | Repository fragment |
| Tạo truy vấn theo điều kiện hoặc tên phương thức | Derived query hoặc `@Query` |

Repository fragment cho phép ghép các phần triển khai tùy chỉnh vào từng repository. Đây thường là lựa chọn tốt khi hành vi không cần áp dụng cho toàn bộ nhóm repository. Lớp cơ sở phù hợp hơn khi hành vi là quy ước chung của cả nhóm.

## 7. Lỗi thường gặp và cách kiểm tra

- **Quên `@NoRepositoryBean`:** Spring có thể cố khởi tạo interface generic `BaseRepository` như một repository độc lập. Thêm annotation vào interface nền.
- **Lớp triển khai không kế thừa `SimpleJpaRepository`:** các phương thức CRUD mặc định có thể không còn được cung cấp theo cách mong muốn. Hãy kế thừa `SimpleJpaRepository<T, ID>` và gọi constructor cha.
- **Constructor không tương thích:** repository factory không tạo được lớp cơ sở. Dùng constructor nhận `JpaEntityInformation<T, ?>` và `EntityManager` như ví dụ.
- **Package quét không đúng:** repository không thuộc vùng cấu hình có thể không sử dụng lớp cơ sở này. Kiểm tra `basePackages` trên cấu hình đang quản lý repository.
- **Không thấy phương thức tùy chỉnh trên repository:** bảo đảm interface repository cụ thể kế thừa interface cơ sở có khai báo phương thức.
- **Gọi `refresh` với entity detached:** JPA không thể refresh một entity không còn được quản lý. Dùng instance được trả về từ `save` và thực hiện trong transaction.
- **Dùng lớp cơ sở cho hành vi chỉ thuộc một repository:** điều này làm phạm vi áp dụng rộng hơn nhu cầu. Chuyển hành vi đó sang repository fragment.

Khi kiểm tra cấu hình, hãy khởi động Application Context để xác nhận repository factory tạo được các repository, sau đó gọi một phương thức bổ sung trên repository cụ thể. Với `saveAndRefresh`, kiểm tra thêm rằng entity trả về có khóa chính và các giá trị cần đọc lại từ database.

## 8. Ghi nhớ

`repositoryBaseClass` là điểm mở rộng để thay lớp triển khai nền mặc định của Spring Data JPA. Kết hợp một interface generic có `@NoRepositoryBean`, một lớp kế thừa `SimpleJpaRepository`, và cấu hình `@EnableJpaRepositories(repositoryBaseClass = ...)` sẽ giúp chia sẻ hành vi nhất quán giữa nhiều repository mà vẫn giữ các thao tác CRUD chuẩn.