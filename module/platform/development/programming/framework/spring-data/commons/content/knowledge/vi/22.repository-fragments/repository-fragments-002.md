# Quy ước hậu tố Impl và phạm vi phát hiện

Repository fragment cho phép bổ sung một nhóm hành vi tùy chỉnh vào repository thông qua một interface và implementation riêng. Để Spring Data ghép đúng implementation vào repository proxy, cần làm rõ hai câu hỏi: lớp triển khai được đặt tên theo interface nào, và hạ tầng repository có thể phát hiện lớp đó ở đâu.

Hậu tố mặc định `Impl` là một quy ước của cơ chế tìm implementation, không phải annotation hay từ khóa của Java. Một lớp có tên kết thúc bằng `Impl` không tự trở thành repository fragment nếu thiếu hợp đồng interface, không nằm trong phạm vi dò phù hợp hoặc không được ghép vào repository.

Bài học tập trung vào cơ chế chung của Spring Data Commons và dùng Spring Data JPA để minh họa cấu hình cụ thể. Phạm vi cấu hình, cách tạo bean và công cụ truy cập dữ liệu phải được đối chiếu với module của store thực tế.

## 1. Ba thành phần cần được nối đúng

Một fragment thường có ba phần:

```java
public interface CustomerSearch {
    List<Customer> findActiveCustomers(int maxResults);
}
```

```java
public class CustomerSearchImpl implements CustomerSearch {
    // Triển khai findActiveCustomers(...).
}
```

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>, CustomerSearch {
}
```

Ở đây:

| Thành phần | Trách nhiệm |
| --- | --- |
| `CustomerSearch` | Khai báo hợp đồng của fragment |
| `CustomerSearchImpl` | Triển khai hợp đồng tùy chỉnh |
| `CustomerRepository` | Kết hợp repository của store với fragment cần dùng |

Khi gọi `customerRepository.findActiveCustomers(...)`, lời gọi đi qua repository proxy và được chuyển tới implementation của fragment đã được ghép.

`CustomerSearchImpl` chỉ cần triển khai `CustomerSearch`; không cần tự triển khai toàn bộ `CustomerRepository` hay viết lại những phương thức CRUD của `JpaRepository`.

```text
Service
   |
   v
CustomerRepository proxy
   |
   +--> CRUD và truy vấn do module JPA cung cấp
   |
   +--> CustomerSearch
           |
           v
        CustomerSearchImpl
```

Sơ đồ mô tả việc ghép hành vi, không có nghĩa ứng dụng phải tự tạo repository proxy.

## 2. Hậu tố gắn với tên interface fragment

Với quy ước mặc định, tên implementation được hình thành từ tên interface fragment cộng hậu tố `Impl`:

```text
CustomerSearch        + Impl -> CustomerSearchImpl
CustomerStatistics    + Impl -> CustomerStatisticsImpl
CustomerSearchFragment + Impl -> CustomerSearchFragmentImpl
```

Từ `Fragment` trong một tên interface chỉ là một phần của tên do lập trình viên chọn. Nó không phải một đoạn mà Spring Data tự bỏ đi khi suy tên implementation.

Ví dụ, nếu repository khai báo:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>, CustomerSearchFragment {
}
```

thì tên theo quy ước là `CustomerSearchFragmentImpl`, không phải `CustomerSearchImpl`.

### Phân biệt với cách đặt tên theo repository

Một số mã nguồn có thể dùng lớp như `CustomerRepositoryImpl` theo mô hình custom implementation gắn với tên repository. Cơ chế lịch sử này có thể được một số cấu hình nhận diện, nhưng không nên dùng nó để suy tên cho một fragment riêng.

Nếu hợp đồng tùy chỉnh tên là `CustomerSearch`, lựa chọn rõ ràng theo mô hình fragment là:

```java
CustomerSearchImpl implements CustomerSearch
```

Đặt đồng thời một lớp theo tên repository và một lớp theo tên fragment có thể làm người đọc khó xác định implementation nào đang được ghép. Nên giữ một cách tổ chức nhất quán và kiểm tra cấu hình mà module đang sử dụng.

### Chính xác cả tên và kiểu

Không chỉ tên lớp phải phù hợp. Lớp triển khai còn phải thực hiện đúng interface và chữ ký phương thức:

```java
@Override
public List<Customer> findActiveCustomers(int maxResults) {
    // ...
}
```

`@Override` giúp compiler phát hiện lỗi chữ ký. Nó không giúp Spring Data tìm một implementation ở ngoài phạm vi dò hoặc thay thế quy ước đặt tên.

## 3. Một bố trí package dễ kiểm soát

Bố trí đơn giản nhất là đặt repository, interface fragment và implementation trong cùng package:

```text
com.example.customer
├── domain
│   └── Customer
├── repository
│   ├── CustomerRepository
│   ├── CustomerSearch
│   └── CustomerSearchImpl
└── config
    └── CustomerRepositoriesConfiguration
```

Với cấu hình repository hướng tới package `com.example.customer.repository`, cách bố trí này làm quan hệ giữa ba thành phần rõ ràng và tránh phải dựa vào các giả định về package ngoài vùng tìm kiếm.

Trong bố trí thông thường, implementation cũng có thể được đặt trong một package con phù hợp, chẳng hạn:

```text
com.example.customer.repository.CustomerSearch
com.example.customer.repository.impl.CustomerSearchImpl
```

Điểm cần giữ là implementation thuộc vùng mà cơ chế lookup của repository và fragment đang xét có thể tìm thấy. Không có quy tắc rằng Spring Data sẽ tìm mọi lớp tên `CustomerSearchImpl` trên toàn bộ classpath.

Nếu chuyển riêng fragment sang một package dùng chung nhưng để implementation ở một nhánh khác, không nên mặc định phạm vi dò vẫn giữ nguyên. Cần đối chiếu cơ chế lookup của module, cấu hình repository và cách đăng ký fragment thực tế.

## 4. Phân biệt ba loại phạm vi quét

Trong một ứng dụng Spring, nhiều cơ chế scanning có thể cùng tồn tại. Chúng không có cùng mục đích.

| Cơ chế | Tìm gì? | Không tự bảo đảm |
| --- | --- | --- |
| Repository scanning | Các repository interface thuộc module đang cấu hình | Mọi implementation tùy chỉnh ở mọi package đều được tìm thấy |
| Implementation lookup của fragment | Ứng viên triển khai theo hợp đồng và quy ước của repository infrastructure | Mọi component cùng tên phương thức đều được ghép thành fragment |
| Component scanning | Bean ứng dụng qua stereotype và cấu hình Spring | Một bean bất kỳ sẽ được gắn vào đúng repository |

Với JPA còn cần phân biệt entity scanning. Entity được nhận diện không có nghĩa repository và fragment đã được phát hiện; repository được tạo cũng không tự xác nhận mọi entity mapping đã đúng.

### Ví dụ cấu hình phạm vi repository JPA

```java
package com.example.customer.config;

import com.example.customer.repository.CustomerRepository;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@Configuration
@EnableJpaRepositories(basePackageClasses = CustomerRepository.class)
public class CustomerRepositoriesConfiguration {
}
```

`basePackageClasses` dùng package của lớp tham chiếu làm mốc quét repository, giúp tránh một chuỗi tên package viết tay. Nó không có nghĩa chỉ duy nhất `CustomerRepository` được xét, và không phải cấu hình entity scan.

Ví dụ chỉ minh họa phần repository; persistence unit, datasource, entity mapping và transaction manager phải được ứng dụng cấu hình phù hợp.

### Vì sao thêm `@Component` chưa chắc sửa được lỗi fragment?

Một lớp có thể được Spring tạo thành bean nhưng repository vẫn chưa biết phải ghép bean đó vào fragment nào. Ngược lại, implementation được repository infrastructure tìm thấy theo quy ước không bắt buộc phải có `@Component` chỉ để được tự dò.

Do đó, khi fragment không hoạt động, cần kiểm tra đồng thời:

1. Repository đã kế thừa interface fragment chưa?
2. Implementation có tên và kiểu phù hợp không?
3. Implementation lookup có nhìn thấy ứng viên không?
4. Nếu dùng bean đăng ký sẵn, tên bean và cách đăng ký có phù hợp với cơ chế ghép không?

Không mở rộng component scan toàn ứng dụng như một cách chữa chung cho mọi lỗi phát hiện implementation.

## 5. Ví dụ JPA đầy đủ theo quy ước mặc định

### 5.1. Mô hình dữ liệu tối thiểu

```java
package com.example.customer.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class Customer {

    @Id
    private Long id;

    private String displayName;
    private boolean active;

    protected Customer() {
    }

    public Long getId() { return id; }
    public String getDisplayName() { return displayName; }
    public boolean isActive() { return active; }
}
```

Ví dụ giả định stack JPA dùng namespace Jakarta và tập trung vào truy vấn đọc. Một stack dùng persistence namespace khác phải dùng bộ API tương ứng.

### 5.2. Interface fragment

```java
package com.example.customer.repository;

import java.util.List;

import com.example.customer.domain.Customer;

public interface CustomerSearch {
    List<Customer> findActiveCustomers(int maxResults);
}
```

### 5.3. Implementation đúng tên

```java
package com.example.customer.repository;

import java.util.List;

import com.example.customer.domain.Customer;
import jakarta.persistence.EntityManager;
import org.springframework.transaction.annotation.Transactional;

public class CustomerSearchImpl implements CustomerSearch {

    private final EntityManager entityManager;

    public CustomerSearchImpl(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Override
    @Transactional(readOnly = true)
    public List<Customer> findActiveCustomers(int maxResults) {
        if (maxResults < 1 || maxResults > 100) {
            throw new IllegalArgumentException(
                "maxResults phải nằm trong khoảng 1 đến 100"
            );
        }

        return entityManager.createQuery(
                "select c from Customer c "
                    + "where c.active = true order by c.id",
                Customer.class
            )
            .setMaxResults(maxResults)
            .getResultList();
    }
}
```

Spring tạo implementation như một bean để có thể cấp dependency qua constructor. Ví dụ giả định có một `EntityManager` phù hợp để inject. Khi dùng nhiều persistence unit, cần chọn đúng manager theo cơ chế cấu hình của ứng dụng, thay vì dựa vào tên lớp fragment để suy ra nguồn dữ liệu.

Annotation giao dịch thể hiện phạm vi đọc của phương thức trong ví dụ. Tác dụng cụ thể phụ thuộc transaction infrastructure của JPA; hậu tố `Impl` không tạo transaction hay làm phương thức tự trở thành chỉ đọc.

### 5.4. Repository ghép fragment

```java
package com.example.customer.repository;

import com.example.customer.domain.Customer;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
        extends JpaRepository<Customer, Long>, CustomerSearch {
}
```

Tại service đã được inject `CustomerRepository repository`:

```java
List<Customer> customers = repository.findActiveCustomers(20);
```

Service gọi qua repository, không cần tự tạo `CustomerSearchImpl`. Trong mô hình này, các phương thức CRUD vẫn do implementation repository JPA cung cấp, còn phương thức tùy chỉnh được chuyển tới fragment.

Nếu thiếu implementation hoặc việc ghép thất bại, method tùy chỉnh có thể không được nhận diện như dự định; tùy module, hạ tầng có thể tiếp tục xét nó theo cơ chế truy vấn khác rồi báo lỗi. Không dựa vào một chuỗi thông báo duy nhất để kết luận nguyên nhân.

## 6. Đổi hậu tố mặc định

Một số module cho phép cấu hình hậu tố implementation trong annotation bật repository. Với Spring Data JPA, ví dụ:

```java
@Configuration
@EnableJpaRepositories(
    basePackageClasses = CustomerRepository.class,
    repositoryImplementationPostfix = "Adapter"
)
public class CustomerRepositoriesConfiguration {
}
```

Với cấu hình đó, tên suy ra cho fragment `CustomerSearch` là:

```java
public class CustomerSearchAdapter implements CustomerSearch {
    // Triển khai các phương thức của CustomerSearch.
}
```

Quy ước mới áp dụng cho nhóm repository thuộc cấu hình đó, không phải một phép đổi tên riêng cho một phương thức. `CustomerSearchImpl` không còn là tên implementation được suy ra tự động từ hậu tố đã chọn.

Khi đổi hậu tố, cần đối chiếu cả:

- Tên các lớp triển khai thuộc phạm vi cấu hình.
- Tên bean nếu có đăng ký hoặc tham chiếu tường minh.
- Những cấu hình repository khác cùng tồn tại trong ứng dụng.
- Những module hoặc thư viện đang cung cấp fragment cho nhóm repository đó.

Không mặc định annotation cấu hình của store khác có hoàn toàn cùng tập thuộc tính. Abstraction fragment thuộc Commons, còn cách khai báo cấu hình cụ thể phải theo module đang dùng.

Hậu tố phân biệt chữ hoa, chữ thường theo tên lớp Java. `Impl`, `impl` và `Adapter` không phải ba cách viết tương đương.

## 7. Tên bean và trường hợp có nhiều ứng viên

Với lớp thông thường `CustomerSearchImpl`, tên bean mặc định thường là:

```text
customerSearchImpl
```

Đây là tên bean, khác với tên đầy đủ của lớp:

```text
com.example.customer.repository.CustomerSearchImpl
```

Nếu có nhiều lớp cùng tên đơn giản trong các package mà lookup có thể thấy, chỉ nói “lớp này tên đúng” chưa đủ. Hạ tầng có thể dùng tên bean để phân giải ứng viên theo quy tắc của nó; nếu vẫn không xác định được duy nhất, việc ghép có thể thất bại.

Ví dụ cần tránh trong cùng vùng dò:

```text
com.example.customer.repository.jpa.CustomerSearchImpl
com.example.customer.repository.archive.CustomerSearchImpl
```

Không dựa vào thứ tự file, thứ tự dependency hoặc việc một lớp tình cờ được tìm thấy trước để chọn implementation. Cách dễ kiểm soát hơn là chỉ để một ứng viên phù hợp trong vùng lookup, tách rõ phạm vi cấu hình hoặc đăng ký implementation theo cơ chế tường minh được module hỗ trợ.

Đổi tên bean bằng stereotype cũng không tự đổi quy ước tên lớp hoặc phạm vi dò. Nếu chủ động dùng bean name để phân giải, cần giữ nhất quán với tên mà hạ tầng repository đang yêu cầu.

## 8. Đăng ký bean implementation có chủ đích

Nếu cần kiểm soát cách tạo implementation, có thể đăng ký bean với tên mà cơ chế repository lookup mong đợi. Với bố trí mặc định ở ví dụ, tên thông thường là `customerSearchImpl`:

```java
package com.example.customer.config;

import com.example.customer.repository.CustomerSearchImpl;
import jakarta.persistence.EntityManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CustomerFragmentConfiguration {

    @Bean(name = "customerSearchImpl")
    public CustomerSearchImpl customerSearchImpl(EntityManager entityManager) {
        return new CustomerSearchImpl(entityManager);
    }
}
```

Cấu hình này phải thực sự được application context nạp. Khi implementation bean được đăng ký đúng tên và phù hợp với hợp đồng lookup, hạ tầng repository có thể dùng bean đã có thay vì tự tạo thêm implementation.

Trong ví dụ, lớp vẫn nằm trong bố trí package rõ ràng và vẫn thực hiện `CustomerSearch`. Việc khai báo bean làm tường minh cách tạo nó, không thay thế yêu cầu repository phải kế thừa fragment.

Không vừa đăng ký bean tường minh vừa tạo một bean khác cho cùng implementation theo một cơ chế không được kiểm soát. Nếu đổi postfix sang `Adapter`, phải đánh giá lại tên lớp và tên bean mà cấu hình mới yêu cầu.

Đối với implementation nằm ngoài phạm vi tự dò, cần dùng cách đăng ký và ghép fragment mà module cùng phiên bản hỗ trợ. Không suy ra rằng bất kỳ `@Bean` ở bất kỳ package nào, chỉ cần có cùng method, đều sẽ được repository nhận làm fragment.

## 9. Package, module và dependency JAR không phải cùng một khái niệm

Phạm vi lookup thường dựa trên package và metadata của repository infrastructure, không chỉ dựa trên ranh giới thư mục mã nguồn của một module build.

Một implementation nằm trong dependency JAR không tự bị loại chỉ vì không nằm trong source của ứng dụng. Ngược lại, có mặt trong một JAR trên classpath cũng không tự khiến nó được ghép vào mọi repository sử dụng interface tương ứng.

Ví dụ:

```text
Module customer-data:
  com.example.customer.repository.CustomerRepository
  com.example.customer.repository.CustomerSearch

Module shared-query:
  com.example.shared.query.CustomerSearchImpl
```

Trong bố trí này, không được mặc định implementation ở `com.example.shared.query` sẽ được tự dò chỉ vì hai module đều là dependency của ứng dụng. Tên đúng và classpath đầy đủ mới là một phần của điều kiện.

Nếu muốn phân phối fragment dùng chung, cần xác định rõ:

1. Module nào sở hữu interface và implementation.
2. Những package nào tham gia lookup.
3. Cách module repository đăng ký hoặc nhận fragment từ dependency.
4. Các dependency backend mà implementation cần.
5. Cách tránh nhiều implementation trùng hợp đồng trong cùng ứng dụng.

Một số tổ hợp module và phiên bản có cơ chế đăng ký fragment mở rộng cho thư viện. Khi dùng cơ chế đó, phải theo đúng hợp đồng cấu hình tương ứng, không dựa vào việc mở rộng component scan như một giải pháp tổng quát.

## 10. Phân biệt phát hiện thành công với hành vi thực thi đúng

Một fragment có thể được tìm thấy và khởi tạo nhưng vẫn dùng sai dependency hoặc có truy vấn sai. Cần tách các lớp vấn đề:

| Giai đoạn | Câu hỏi cần trả lời |
| --- | --- |
| Phát hiện repository | Interface repository có thuộc cấu hình module đang xét không? |
| Nhận diện fragment | Repository có kế thừa đúng hợp đồng tùy chỉnh không? |
| Tìm implementation | Tên, hậu tố và phạm vi lookup có khớp không? |
| Tạo bean | Dependency của implementation có thể được cấp đúng không? |
| Ghép lời gọi | Method trên repository có được chuyển tới đúng fragment không? |
| Thực thi nghiệp vụ | Query, transaction và phạm vi dữ liệu có đúng yêu cầu không? |

Hậu tố `Impl` chỉ liên quan một phần của chuỗi đó. Nó không tự chọn datasource, không bảo đảm quyền truy cập và không biến code JPA thành code dùng được cho MongoDB.

Nếu cùng một fragment interface có implementation cho nhiều store, nên tách cấu hình và phạm vi rõ ràng. Để nhiều lớp backend khác nhau cùng khớp một quy ước trong vùng dò rộng có thể gây nhập nhằng hoặc ghép sai ý định.

Cũng nên tránh inject repository chính vào fragment rồi gọi lại chính phương thức fragment đó. Nếu lời gọi quay về cùng proxy và được chuyển lại cho implementation, có thể tạo vòng lặp. Dependency của fragment nên phục vụ việc thực thi trách nhiệm của nó, không dựa vào tên `Impl` để kỳ vọng có một repository khác phía sau.

## 11. Chẩn đoán các lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể gặp | Hướng xử lý |
| --- | --- | --- |
| Method tùy chỉnh bị phân tích như derived query | Fragment chưa được ghép hoặc thiếu implementation phù hợp | Kiểm tra extends, tên fragment, postfix và phạm vi dò |
| `CustomerRepositoryImpl` không thực hiện hành vi mong muốn của `CustomerSearch` | Đang trộn quy ước theo repository với mô hình fragment | Dùng hợp đồng và implementation theo tên fragment một cách nhất quán |
| Thêm `@Component` nhưng repository vẫn lỗi | Bean tồn tại chưa đồng nghĩa được ghép đúng | Kiểm tra lookup, tên bean và interface mà repository kế thừa |
| Đổi hậu tố rồi không tìm thấy implementation | Tên lớp hoặc bean vẫn theo hậu tố cũ | Đồng bộ cấu hình và tên được suy ra |
| Có nhiều implementation cùng tên | Vùng dò chồng lấn hoặc dependency chứa ứng viên trùng | Thu hẹp phạm vi, tách cấu hình hoặc đăng ký lựa chọn tường minh |
| Không cấp được EntityManager | Dependency injection hoặc cấu hình persistence unit chưa phù hợp | Kiểm tra manager mà implementation cần, không chỉ kiểm tra tên lớp |
| Repository tìm thấy nhưng entity không được nhận diện | Nhầm repository scan với entity mapping | Kiểm tra cấu hình entity và persistence unit của JPA |
| Chạy ở một ứng dụng nhưng lỗi khi đưa vào thư viện | Giả định package lookup vẫn như cũ | Làm rõ cách phân phối và đăng ký fragment qua dependency |
| Fragment được gọi nhưng dùng sai backend | Cấu hình nhiều store hoặc dependency không rõ ràng | Tách vùng repository và cấp đúng hạ tầng cho implementation |
| Lời gọi lặp vô hạn | Fragment gọi lại chính method trên repository proxy | Sửa hướng phụ thuộc và đường thực thi của fragment |

Không bắt đầu bằng cách đổi hàng loạt tên lớp hoặc mở rộng mọi package scan. Hãy xác định lỗi nằm ở phát hiện, tạo bean, ghép method hay thực thi rồi sửa đúng giai đoạn đó.

## 12. Tình huống tự thực hành

Trên một module đã cấu hình JPA, có thể lần lượt đối chiếu:

| Tình huống | Điều cần quan sát |
| --- | --- |
| Fragment và implementation cùng package, hậu tố mặc định | Repository gọi được method do `CustomerSearchImpl` cung cấp |
| Repository không kế thừa `CustomerSearch` | Có implementation riêng chưa đủ để công khai method qua repository interface |
| Đổi interface thành `CustomerSearchFragment` | Tên implementation theo quy ước phải phản ánh tên interface mới |
| Chuyển implementation sang package ngoài vùng dò | Không mặc định nó vẫn được phát hiện chỉ vì classpath còn chứa lớp |
| Đổi postfix thành `Adapter` | Tên implementation và đăng ký bean phù hợp với cấu hình mới |
| Có hai ứng viên trùng tên đơn giản | Không dựa vào thứ tự classpath để quyết định implementation |
| Đăng ký bean đúng tên trong cấu hình đã được nạp | Phân biệt được quản lý bean với việc ghép hợp đồng fragment |
| Dùng nhiều persistence unit | Implementation nhận đúng hạ tầng truy cập dữ liệu theo cấu hình |

Khi thiết kế một fragment, hãy giữ quan hệ giữa interface, tên implementation và vùng lookup đủ rõ để người đọc có thể lần theo. Bố trí cùng package với hậu tố mặc định là một điểm bắt đầu dễ kiểm soát; tùy chỉnh hậu tố, phân phối qua thư viện hoặc dùng nhiều store đều cần cấu hình tương ứng thay vì dựa vào một lớp có tên kết thúc bằng `Impl`.