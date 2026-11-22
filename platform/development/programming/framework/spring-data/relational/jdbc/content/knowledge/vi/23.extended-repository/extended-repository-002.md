# Quy ước đặt tên, phát hiện triển khai và thứ tự ghép fragment

Trong **Spring Data Relational JDBC**, repository interface thường chỉ khai báo hợp đồng truy cập dữ liệu. Spring Data tạo repository proxy và kết hợp nhiều thành phần để cung cấp các phương thức CRUD, query method và chức năng mở rộng. Khi cần thêm hành vi riêng, cách được khuyến nghị là dùng **repository fragments**: một interface mô tả phần mở rộng và một class triển khai interface đó.

Để Spring Data tìm được class triển khai, tên class và vị trí package cần tuân theo quy ước. Khi một repository có nhiều fragment, thứ tự các interface được khai báo cũng có ý nghĩa vì chúng quyết định cách các phần được ghép và xử lý method trùng chữ ký.

Bài này giải thích:

- Quy ước tên fragment interface và implementation class.
- Cách Spring Data JDBC phát hiện implementation, hậu tố mặc định và cách đổi hậu tố.
- Xử lý khi có nhiều class triển khai trùng tên.
- Cách ghép nhiều fragment và ưu tiên khi method trùng chữ ký.
- Khác biệt giữa fragment, implementation kiểu cũ và custom repository base class.

## 1. Repository proxy được ghép từ những thành phần nào?

Một repository như:

```java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
```

không cần class cụ thể do lập trình viên tự viết để implement toàn bộ method. Spring Data tạo proxy dựa trên repository metadata và kết hợp các thành phần:

1. **Base repository implementation:** cung cấp API nền tảng như `save`, `findById`, `deleteById`. Với Spring Data JDBC, implementation mặc định là `SimpleJdbcRepository`.
2. **Repository aspects:** các chức năng bổ sung do Spring Data cung cấp khi được bật và hỗ trợ, ví dụ các extension liên quan query.
3. **Custom repository fragments:** các interface mở rộng do ứng dụng hoặc thư viện cung cấp cùng implementation tương ứng.
4. **Query methods:** các method được phân tích từ tên hoặc khai báo bằng `@Query`.

Sơ đồ khái niệm:

```text
CustomerRepository
       │
       ▼
Spring Data repository proxy
       │
       ├── Base repository implementation
       │      └── CRUD của Spring Data JDBC
       │
       ├── Repository aspects
       │      └── Các chức năng mở rộng được hỗ trợ
       │
       └── Custom fragments
              ├── CustomerSearch + CustomerSearchImpl
              └── CustomerExport + CustomerExportImpl
```

Nhờ cơ chế composition, repository có thể kết hợp CRUD chuẩn với nhiều nhóm chức năng riêng mà không cần một class implementation khổng lồ.

## 2. Tạo fragment interface và implementation

Mỗi fragment bắt đầu bằng một interface mô tả hành vi cần bổ sung. Ví dụ, repository khách hàng cần tìm theo domain email:

```java
import java.util.List;

public interface CustomerSearch {
    List<Customer> findByEmailDomain(String domain);
}
```

Implementation tương ứng:

```java
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;

public class CustomerSearchImpl implements CustomerSearch {

    private final JdbcTemplate jdbcTemplate;

    public CustomerSearchImpl(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public List<Customer> findByEmailDomain(String domain) {
        String sql = """
                SELECT id, email, status
                FROM customer
                WHERE email LIKE ?
                ORDER BY id
                """;

        return jdbcTemplate.query(
                sql,
                (rs, rowNum) -> new Customer(
                        rs.getLong("id"),
                        rs.getString("email"),
                        rs.getString("status")
                ),
                "%@" + domain
        );
    }
}
```

Ví dụ dùng `JdbcTemplate` để minh họa một implementation có thể gọi hạ tầng JDBC thông thường. Trong ứng dụng thực tế, cần xác định rõ domain model, schema, validation domain và cách xử lý input. Giá trị `domain` được truyền bằng bind parameter; không ghép nó thành một đoạn SQL tùy ý.

Repository mở rộng fragment:

```java
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long>, CustomerSearch {
}
```

Giờ đây bean `CustomerRepository` có cả method CRUD và `findByEmailDomain`. Spring Data kết hợp fragment implementation với repository proxy khi tạo bean.

## 3. Quy ước tên mặc định: tên fragment interface + Impl

Spring Data mặc định dùng hậu tố `Impl` để tìm implementation của fragment. Tên class được hình thành từ **tên interface fragment**, không phải tên repository chính.

| Fragment interface | Implementation mặc định |
| --- | --- |
| `CustomerSearch` | `CustomerSearchImpl` |
| `CustomerExport` | `CustomerExportImpl` |
| `CustomizedSave` | `CustomizedSaveImpl` |
| `OrderStatistics` | `OrderStatisticsImpl` |

Ví dụ:

```text
CustomerRepository
       │ extends
       ▼
CustomerSearch
       │ Spring Data tìm class theo hậu tố
       ▼
CustomerSearchImpl
```

Nếu fragment interface là `CustomerSearch` mà class triển khai tên `CustomerSearchService`, Spring Data không thể tự suy ra đó là implementation theo quy ước mặc định. Hãy đổi tên class theo quy ước hoặc cấu hình hậu tố phù hợp.

### 3.1. Package nơi implementation được tìm kiếm

Repository infrastructure tìm các class implementation trong package bên dưới package nơi repository được phát hiện. Cách tổ chức phổ biến là đặt repository, fragment interface và implementation trong cùng package:

```text
com.acme.customer
├── Customer.java
├── CustomerRepository.java
├── CustomerSearch.java
└── CustomerSearchImpl.java
```

Cũng có thể đặt implementation ở package con thuộc vùng được repository infrastructure quét. Nếu class nằm ngoài vùng package đó, implementation có thể không được tự phát hiện dù tên class đúng.

Giữ các fragment liên quan gần repository giúp người đọc dễ xác định phần mở rộng nào thuộc repository nào. Với fragment dùng chung ở nhiều repository hoặc đóng gói trong thư viện riêng, xem phần đăng ký fragment ở mục sau.

## 4. Đổi hậu tố implementation

Hậu tố mặc định là `Impl`. Có thể đổi qua thuộc tính `repositoryImplementationPostfix` của `@EnableJdbcRepositories`.

Ví dụ:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.EnableJdbcRepositories;

@Configuration
@EnableJdbcRepositories(
        basePackages = "com.acme.customer",
        repositoryImplementationPostfix = "JdbcExtension"
)
public class JdbcRepositoryConfiguration {
}
```

Khi đó:

| Fragment interface | Hậu tố cấu hình | Class Spring Data tìm |
| --- | --- | --- |
| `CustomerSearch` | `JdbcExtension` | `CustomerSearchJdbcExtension` |
| `CustomerExport` | `JdbcExtension` | `CustomerExportJdbcExtension` |

Ví dụ implementation:

```java
public class CustomerSearchJdbcExtension
        implements CustomerSearch {

    // Implementation...
}
```

Chỉ đổi hậu tố nếu dự án có quy ước đặt tên riêng hoặc cần tránh xung đột. Nếu đổi cấu hình nhưng quên đổi tên class, Spring Data không tìm thấy implementation tương ứng và repository có thể không khởi tạo được khi fragment method cần được triển khai.

Trong Spring Boot, repository scanning thường được auto-configure theo package của ứng dụng. Nếu cần điều chỉnh hậu tố, có thể cấu hình repository scanning tường minh bằng `@EnableJdbcRepositories` với package phù hợp. Tránh bật hai cấu hình repository scanning chồng lấn mà không có chủ đích.

## 5. Phát hiện implementation và bean name

Implementation được phát hiện theo hai yếu tố chính:

1. **Tên class:** tên fragment interface cộng hậu tố đã cấu hình.
2. **Vị trí:** class nằm trong vùng package mà repository infrastructure tìm kiếm.

Implementation có thể là một Spring bean thông thường. Constructor injection hoạt động như với các bean khác; fragment có thể nhận `JdbcTemplate`, service, mapper hoặc bean ứng dụng khác.

Ví dụ implementation cần một service:

```java
public class CustomerSearchImpl implements CustomerSearch {

    private final CustomerPolicy customerPolicy;
    private final JdbcTemplate jdbcTemplate;

    public CustomerSearchImpl(
            CustomerPolicy customerPolicy,
            JdbcTemplate jdbcTemplate) {
        this.customerPolicy = customerPolicy;
        this.jdbcTemplate = jdbcTemplate;
    }

    // Implement các method của CustomerSearch.
}
```

Với cấu hình thông thường, Spring Data có thể tự tạo bean implementation theo quy ước. Nếu implementation cần wiring đặc biệt, có thể khai báo bean thủ công nhưng phải dùng bean name mà repository infrastructure mong đợi.

### 5.1. Khi có nhiều implementation trùng tên

Giả sử có hai class cùng tên `CustomerSearchImpl` ở hai package khác nhau:

```text
com.acme.impl.defaultsearch.CustomerSearchImpl
com.acme.impl.specialsearch.CustomerSearchImpl
```

Spring Data dùng **bean name** để phân giải implementation tương ứng. Bean name mặc định thường được tạo từ tên class theo quy tắc camel case, ví dụ `customerSearchImpl`. Khi cần chọn implementation đặc biệt, có thể đặt tên bean tường minh để khớp với tên fragment cộng hậu tố.

Ví dụ:

```java
import org.springframework.stereotype.Component;

@Component("specialCustomerSearchImpl")
public class CustomerSearchImpl implements CustomerSearch {
    // Implementation đặc biệt.
}
```

Repository interface có thể được đặt tên bean tương ứng:

```java
import org.springframework.stereotype.Component;

@Component("specialCustomerSearch")
public interface CustomerRepository
        extends CrudRepository<Customer, Long>, CustomerSearch {
}
```

Trong tình huống cần lựa chọn implementation theo bean name, quy tắc tên phải khớp với fragment/repository và hậu tố đã cấu hình. Đây là cấu hình nâng cao; trong dự án bình thường nên tránh có nhiều class cùng tên implementation trong các package cùng vùng scan.

### 5.2. Wiring thủ công

Nếu implementation cần cấu hình đặc biệt, có thể đăng ký bean thủ công theo tên convention:

```java
@Configuration
class CustomerSearchConfiguration {

    @Bean("customerSearchImpl")
    CustomerSearch customerSearch(
            JdbcTemplate jdbcTemplate,
            CustomerPolicy policy) {
        return new CustomerSearchImpl(policy, jdbcTemplate);
    }
}
```

Khi infrastructure tìm thấy bean definition với tên mong đợi, nó có thể dùng bean đã cấu hình thay vì tự tạo implementation. Đảm bảo kiểu trả về bean thực sự triển khai fragment interface và tên bean đúng với quy ước.

## 6. Mô hình cũ: tên implementation dựa trên repository interface

Trước khi repository fragments trở thành mô hình mở rộng được khuyến nghị, Spring Data hỗ trợ cách đặt một implementation class theo tên repository:

```text
CustomerRepository
CustomerRepositoryImpl
```

Ví dụ cũ:

```java
public interface CustomerRepositoryCustom {
    List<Customer> searchCustomers(String text);
}

public interface CustomerRepository
        extends CrudRepository<Customer, Long>, CustomerRepositoryCustom {
}

public class CustomerRepositoryImpl implements CustomerRepositoryCustom {
    @Override
    public List<Customer> searchCustomers(String text) {
        // Cách triển khai tùy ứng dụng.
        return List.of();
    }
}
```

Cách này dễ dẫn đến implementation class phải gánh nhiều method hoặc vô tình bị nhận diện như custom implementation cho toàn bộ repository. Tài liệu Spring Data hiện hành xem **single-custom implementation naming pattern** là deprecated và khuyến nghị chuyển sang fragment-based programming model.

Cách hiện đại:

```java
public interface CustomerSearch {
    List<Customer> searchCustomers(String text);
}

public class CustomerSearchImpl implements CustomerSearch {
    @Override
    public List<Customer> searchCustomers(String text) {
        // Chỉ triển khai chức năng tìm kiếm.
        return List.of();
    }
}

public interface CustomerRepository
        extends CrudRepository<Customer, Long>, CustomerSearch {
}
```

Ở đây `CustomerSearchImpl` chỉ triển khai fragment `CustomerSearch`. Repository chính kết hợp fragment với CRUD, không cần một class tự implement toàn bộ `CustomerRepository`.

Không đặt một class `CustomerRepositoryImpl` mới nếu ý định thực sự chỉ là một fragment nhỏ. Tên đó có thể kích hoạt cơ chế phát hiện legacy và gây xung đột với cách ghép fragment.

## 7. Ghép nhiều fragment trong một repository

Một repository có thể mở rộng nhiều fragment:

```java
public interface CustomerSearch {
    List<Customer> search(String text);
}

public interface CustomerExport {
    byte[] exportCsv(String status);
}

public interface CustomerStatistics {
    long countByStatus(String status);
}

public interface CustomerRepository
        extends CrudRepository<Customer, Long>,
                CustomerSearch,
                CustomerExport,
                CustomerStatistics {
}
```

Mỗi fragment có implementation tương ứng:

```text
CustomerRepository
   ├── CrudRepository
   ├── CustomerSearch
   │      └── CustomerSearchImpl
   ├── CustomerExport
   │      └── CustomerExportImpl
   └── CustomerStatistics
          └── CustomerStatisticsImpl
```

Spring Data kết hợp các phần mở rộng theo thứ tự interface được khai báo. Fragment có thể được tái sử dụng bởi nhiều repository:

```java
public interface CustomerRepository
        extends CrudRepository<Customer, Long>, CustomerSearch {
}

public interface ArchivedCustomerRepository
        extends CrudRepository<ArchivedCustomer, Long>, CustomerSearch {
}
```

Nếu fragment có tính tổng quát, có thể khai báo generic interface:

```java
public interface SearchExtension<T> {
    List<T> search(String text);
}

public interface CustomerRepository
        extends CrudRepository<Customer, Long>,
                SearchExtension<Customer> {
}
```

Implementation generic cần bảo đảm biết domain type và cách truy vấn phù hợp. Không phải fragment generic nào cũng tự biết bảng/cột; có thể cần metadata repository, converter hoặc service chuyên biệt.

## 8. Thứ tự ghép fragment và xử lý method trùng chữ ký

Thứ tự interface trong khai báo repository có ý nghĩa:

```java
public interface CustomerRepository
        extends CrudRepository<Customer, Long>,
                CustomerSearch,
                CustomerExport {
}
```

Các fragment được ghép theo thứ tự khai báo. Custom fragment implementations có độ ưu tiên cao hơn base implementation và repository aspects. Điều này cho phép fragment tùy chỉnh method vốn được base repository hoặc aspect cung cấp.

Ví dụ fragment tùy chỉnh `save`:

```java
public interface CustomizedSave<T> {
    <S extends T> S save(S entity);
}

public class CustomizedSaveImpl<T> implements CustomizedSave<T> {

    private final JdbcAggregateTemplate template;

    public CustomizedSaveImpl(JdbcAggregateTemplate template) {
        this.template = template;
    }

    @Override
    public <S extends T> S save(S entity) {
        // Chèn logic chung có chủ đích trước khi lưu.
        return template.save(entity);
    }
}
```

Repository:

```java
public interface CustomerRepository
        extends CrudRepository<Customer, Long>,
                CustomizedSave<Customer> {
}
```

Fragment có thể cung cấp implementation cho chữ ký `save` và được ưu tiên so với base implementation. Tuy nhiên, khi override method nền tảng, phải giữ đúng contract của method, generic type, transaction behavior, event/callback và semantics lưu aggregate. Không nên thêm logic phụ gây thay đổi bất ngờ cho tất cả thao tác save.

### 8.1. Hai fragment cùng khai báo một method

Giả sử:

```java
public interface CustomerSearch {
    List<Customer> findByCode(String code);
}

public interface LegacyCustomerSearch {
    List<Customer> findByCode(String code);
}
```

Nếu cả hai implementation cùng được ghép vào một repository, cùng một method signature xuất hiện ở nhiều fragment. Spring Data dùng thứ tự ghép fragment để giải quyết sự trùng lặp. Vì vậy:

- Thứ tự khai báo interface là một phần của cấu hình composition.
- Không nên để nhiều fragment tình cờ cung cấp cùng một method nếu không có ý định override.
- Nếu cần override có chủ đích, đặt thứ tự rõ ràng và viết integration test để xác nhận implementation thực sự được gọi.
- Cách đơn giản hơn là đổi tên method để thể hiện chức năng khác nhau, ví dụ `findByCodeInCurrentCatalog` và `findByCodeInArchive`.

Tài liệu mô tả fragment được nhập theo thứ tự khai báo và thứ tự này dùng để xử lý ambiguity; không nên dựa vào một thứ tự ngầm định ngoài khai báo interface.

### 8.2. Ưu tiên giữa fragment và base implementation/aspect

Custom implementations có độ ưu tiên cao hơn base implementation và repository aspects. Ví dụ một fragment định nghĩa lại `save` có thể được dùng thay cho method `save` của base repository. Tương tự, fragment có thể override method được một aspect cung cấp nếu signature trùng.

Đây là cơ chế mạnh nhưng cần thận trọng: method cùng tên/chữ ký có thể thay đổi hành vi repository mà caller không nhận ra từ type declaration. Hãy ghi chú rõ trong fragment và kiểm thử cả đường gọi CRUD chuẩn.

## 9. Fragment ở ngoài package repository và thư viện dùng chung

Thông thường, implementation được dò trong package dưới package chứa repository. Nếu fragment được đóng gói trong thư viện ngoài vùng scan hoặc được chia sẻ qua một archive, tự động dò theo package có thể không tìm thấy.

Spring Data hỗ trợ đăng ký fragment extension qua file `META-INF/spring.factories`. Ví dụ:

```properties
com.acme.search.SearchExtension=com.acme.search.DefaultSearchExtension
```

Trong đó:

- `com.acme.search.SearchExtension` là fragment interface.
- `com.acme.search.DefaultSearchExtension` là implementation.
- Repository của ứng dụng chỉ cần extends fragment interface để nhận chức năng.

Ví dụ repository:

```java
public interface MovieRepository
        extends CrudRepository<Movie, Long>,
                SearchExtension<Movie> {
}
```

Đây là cách dành cho extension/library có nhu cầu đóng góp fragment từ bên ngoài package repository. Với một ứng dụng đơn giản, naming convention và package scanning thông thường dễ cấu hình hơn.

## 10. Phân biệt fragment với custom repository base class

Fragment phù hợp khi chỉ một số repository cần thêm chức năng. Nếu muốn thay đổi behavior nền tảng cho **mọi repository trong một cấu hình**, có thể tạo custom repository base class.

| Tiêu chí | Repository fragment | Custom repository base class |
| --- | --- | --- |
| Phạm vi | Repository nào extends fragment | Các repository dùng cấu hình base class đó |
| Mục đích | Thêm một nhóm method/chức năng | Thay đổi hoặc bổ sung behavior nền tảng |
| Cơ chế | Interface + implementation | Kế thừa base class của store |
| Cấu hình | Naming detection và repository composition | `repositoryBaseClass` trong `@EnableJdbcRepositories` |
| Độ phức tạp | Thường thấp hơn | Cao hơn; phụ thuộc constructor và factory của Spring Data JDBC |

Ví dụ cấu hình base class:

```java
@Configuration
@EnableJdbcRepositories(
        basePackages = "com.acme.customer",
        repositoryBaseClass = MyJdbcRepository.class
)
class JdbcConfiguration {
}
```

Custom class phải kế thừa base implementation phù hợp với Spring Data JDBC, thường là `SimpleJdbcRepository`. Constructor phải tương thích với constructor mà repository factory của **phiên bản Spring Data Relational đang dùng** yêu cầu. API constructor của base class có thể thay đổi giữa các phiên bản; hãy kiểm tra Javadoc đúng version trước khi triển khai.

Không dùng base class chỉ để thêm một method tìm kiếm cho một repository. Fragment là lựa chọn đơn giản hơn và không làm thay đổi mọi repository khác.

## 11. Quy trình Spring Data tìm và ghép implementation

Có thể hình dung quy trình khởi tạo:

```text
1. Repository scanning tìm CustomerRepository
              │
              ▼
2. Đọc các interface mà repository extends
              │
              ▼
3. Nhận diện các fragment interface
              │
              ▼
4. Với mỗi fragment, dò implementation:
      <FragmentInterfaceName> + <Postfix>
              │
              ▼
5. Resolve bean theo tên nếu có nhiều ứng viên
              │
              ▼
6. Tạo repository composition:
      base implementation + aspects + custom fragments
              │
              ▼
7. Tạo proxy và expose bean CustomerRepository
```

Nếu không tìm thấy implementation của một fragment, Spring Data không thể cung cấp method fragment đó. Repository có thể không khởi tạo được do thiếu fragment implementation. Khi gặp lỗi khởi tạo, kiểm tra tên class, hậu tố, package scan và bean name trước khi thay đổi SQL hoặc mapping entity.

## 12. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Fragment method không được triển khai | Không có class theo tên fragment + postfix | Đặt tên `CustomerSearchImpl` hoặc chỉnh hậu tố |
| Implementation class tồn tại nhưng không được tìm thấy | Class nằm ngoài package được repository infrastructure quét | Đặt class trong package phù hợp hoặc đăng ký extension theo cơ chế thư viện |
| Đổi hậu tố nhưng startup báo thiếu implementation | `repositoryImplementationPostfix` và tên class không khớp | Đối chiếu hậu tố cấu hình với tên implementation |
| Có hai implementation cùng tên | Bean name không phân giải đúng ứng viên | Đặt bean name tường minh và khớp convention |
| Method fragment bị gọi nhầm | Nhiều fragment có cùng signature hoặc trùng với base/aspect | Xem thứ tự khai báo và viết test xác nhận composition |
| `CustomerRepositoryImpl` gây hành vi ngoài ý muốn | Legacy single-custom implementation pattern bị nhận diện | Chuyển sang fragment interface và class `FragmentNameImpl` |
| Fragment không inject được dependency | Bean wiring/constructor không phù hợp hoặc bean không được tạo đúng | Dùng constructor injection và kiểm tra bean registration |
| Repository base class không khởi tạo | Constructor không khớp phiên bản store factory | Kiểm tra Javadoc đúng phiên bản và constructor của base class |
| Nhiều repository dùng chung fragment nhưng behavior sai | Fragment implementation phụ thuộc domain type cụ thể | Tách fragment chuyên biệt hoặc thiết kế generic fragment có metadata phù hợp |

## 13. Checklist thiết kế fragment

Trước khi thêm custom repository functionality, xác định:

1. Đây là hành vi riêng cho một repository hay cần tái sử dụng?
2. Có thể dùng derived query hoặc `@Query` thay cho custom fragment không?
3. Fragment interface có tên thể hiện rõ chức năng không?
4. Implementation class có đúng tên `FragmentNameImpl` không?
5. Class nằm trong vùng package được scan không?
6. Nếu dùng hậu tố riêng, `@EnableJdbcRepositories` đã cấu hình đúng chưa?
7. Nếu có nhiều fragment, thứ tự extends có rõ ràng và không tạo method collision không?
8. Nếu override `save` hoặc method nền tảng, contract/transaction/version/event có được giữ không?
9. Nếu muốn thay đổi tất cả repository, custom base class có thực sự cần thiết không?
10. Nếu fragment nằm trong thư viện ngoài, đã đăng ký extension đúng cơ chế chưa?

## 14. Bài tập thực hành

**Bài 1 — Fragment cơ bản.** Tạo `CustomerSearch` và `CustomerSearchImpl`, cho `CustomerRepository` extends fragment. Inject repository và gọi method tìm kiếm.

**Bài 2 — Hậu tố tùy chỉnh.** Cấu hình `repositoryImplementationPostfix = "JdbcExtension"`, đổi class thành `CustomerSearchJdbcExtension` và xác nhận repository vẫn khởi tạo.

**Bài 3 — Hai fragment.** Tạo `CustomerSearch` và `CustomerExport`, thêm cả hai vào repository. Gọi method của từng fragment qua cùng bean repository.

**Bài 4 — Xử lý ambiguity.** Tạo hai fragment có cùng method signature, thử thay đổi thứ tự khai báo và viết test xác nhận implementation được gọi. Sau đó đổi tên method để loại bỏ collision.

**Bài 5 — Override save.** Tạo fragment generic tùy chỉnh `save`. Thêm logging hoặc kiểm tra đơn giản, xác nhận fragment được ưu tiên. Kiểm tra cả insert, update, version và entity callbacks để tránh làm sai contract.

**Bài 6 — Legacy naming.** Tạo thử một class `CustomerRepositoryImpl` trong môi trường test riêng, quan sát cơ chế phát hiện cũ. Sau đó chuyển chức năng sang fragment-based naming và so sánh.

**Bài 7 — Base class.** Đọc Javadoc `SimpleJdbcRepository` đúng version, tạo custom base class tối thiểu và cấu hình `repositoryBaseClass`. So sánh phạm vi ảnh hưởng với fragment.

### Tài liệu tham khảo

- [Spring Data Relational — Custom Repository Implementations](https://docs.spring.io/spring-data/relational/reference/repositories/custom-implementations.html): fragment naming, detection, ambiguity, composition order và custom base repository.
- [Spring Data JDBC — EnableJdbcRepositories API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/repository/config/EnableJdbcRepositories.html): `repositoryImplementationPostfix`, `repositoryBaseClass` và repository scanning.
- [Spring Data JDBC — SimpleJdbcRepository API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/repository/support/SimpleJdbcRepository.html): base implementation của repository JDBC.
