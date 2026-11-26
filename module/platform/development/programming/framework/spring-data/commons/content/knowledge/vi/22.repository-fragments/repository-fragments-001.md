# Khai báo giao diện fragment và lớp triển khai

## 1. Repository fragment giải quyết vấn đề gì?

Một repository thường cần nhiều loại hành vi:

- Các thao tác có sẵn như `save`, `findById` và `deleteById`.
- Các truy vấn được tạo từ tên phương thức.
- Một nhóm phương thức cần logic triển khai riêng.

Trong Spring Data Commons, **repository fragment** giúp khai báo và ghép nhóm hành vi tùy chỉnh vào repository. Mô hình cơ bản gồm:

1. Một interface fragment định nghĩa hợp đồng.
2. Một lớp triển khai thực hiện hợp đồng đó.
3. Một interface repository kế thừa fragment.

Ví dụ về tên:

~~~text
CustomerSearchFragment
        ↑ implements
CustomerSearchFragmentImpl

CustomerRepository
        extends CustomerSearchFragment
        và interface repository của store
~~~

Caller chỉ cần làm việc với `CustomerRepository`. Repository proxy do Spring Data tạo sẽ định tuyến lời gọi đến phần triển khai phù hợp.

Mục tiêu của bài là khai báo đúng cấu trúc này, hiểu cách Spring Data tìm implementation và nhận diện lỗi cấu hình thường gặp. Ví dụ dùng Spring Data JPA cho phần truy cập dữ liệu; cơ chế fragment thuộc abstraction chung, còn API truy vấn bên trong implementation vẫn có phạm vi store cụ thể.

## 2. Phân biệt ba vai trò

| Thành phần | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| Interface fragment | Nhóm hành vi tùy chỉnh có những phương thức nào? | `CustomerSearchFragment` |
| Lớp triển khai fragment | Những phương thức đó được thực hiện ra sao? | `CustomerSearchFragmentImpl` |
| Interface repository | Repository cung cấp tổng hợp những khả năng nào? | `CustomerRepository` |

### 2.1. Interface là hợp đồng, không phải implementation

~~~java
public interface CustomerSearchFragment {

    List<Customer> searchActiveInCountry(
            String country,
            int maximumResults);
}
~~~

Chữ ký trên chưa nói cho Spring Data cách thực hiện truy vấn. Logic nằm trong lớp triển khai tương ứng.

Không nên thêm một phương thức tùy chỉnh vào repository rồi mặc định Spring sẽ tự đoán phần triển khai. Nếu phương thức không được cung cấp bởi fragment, base repository hoặc một cơ chế truy vấn hợp lệ, việc khởi tạo repository có thể thất bại.

### 2.2. Repository không tự implements toàn bộ phương thức

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                CustomerSearchFragment {
}
~~~

Đây vẫn là interface. Spring Data tạo proxy và ghép các phần triển khai; bạn không phải tạo một lớp rồi tự viết lại toàn bộ CRUD của `JpaRepository`.

Lớp fragment chỉ triển khai `CustomerSearchFragment`, không triển khai cả `CustomerRepository`:

~~~java
public class CustomerSearchFragmentImpl
        implements CustomerSearchFragment {
    // Chỉ triển khai hành vi của fragment.
}
~~~

Đoạn trên chỉ minh họa cấu trúc. Lớp đầy đủ ở phần sau sẽ có thân phương thức.

## 3. Quy tắc đặt tên và bố trí package

Với hậu tố mặc định `Impl`, tên implementation được xây từ **tên interface fragment**:

~~~text
CustomerSearchFragment + Impl
= CustomerSearchFragmentImpl
~~~

Một bố cục đơn giản:

~~~text
com.example.customer
├── Customer.java
├── CustomerSearchFragment.java
├── CustomerSearchFragmentImpl.java
├── CustomerRepository.java
└── CustomerSearchService.java
~~~

Đặt repository, fragment và implementation trong cùng package như trên giúp cách phát hiện dễ quan sát. Package đó cần nằm trong phạm vi cấu hình repository của Spring Data module đang dùng.

### 3.1. Tên lớp bám theo fragment

| Interface fragment | Hậu tố cấu hình | Tên implementation tương ứng |
| --- | --- | --- |
| `CustomerSearchFragment` | `Impl` | `CustomerSearchFragmentImpl` |
| `CustomerSearchFragment` | `Custom` | `CustomerSearchFragmentCustom` |
| `CustomerStatistics` | `Impl` | `CustomerStatisticsImpl` |

Trong mô hình fragment của bài, không tự đổi tên implementation thành `CustomerRepositoryImpl` khi interface cần triển khai là `CustomerSearchFragment`. Cách đặt tên theo repository là một quy ước khác; nó không thay thế việc khai báo fragment rõ ràng đang sử dụng ở đây.

### 3.2. Hậu tố có thể cấu hình nhưng phải đồng bộ

Một số annotation bật repository của store cung cấp thuộc tính `repositoryImplementationPostfix`. Ví dụ JPA có khả năng cấu hình thuộc tính đó trên `@EnableJpaRepositories`.

Nếu đổi hậu tố thành `Custom` thì implementation của ví dụ phải có tên tương ứng. Không giữ lớp `CustomerSearchFragmentImpl` rồi kỳ vọng cấu hình tìm hậu tố `Custom` sẽ tự suy ra nó.

Bài thực hành giữ hậu tố mặc định `Impl` để tập trung vào cấu trúc. Không cần thêm cấu hình thay đổi hậu tố chỉ để dùng fragment thông thường.

### 3.3. Fragment interface không cần là repository độc lập

`CustomerSearchFragment` ở đây là một interface Java thông thường. Nó không kế thừa `Repository` và không cần tự trở thành một Spring Data repository bean.

`@NoRepositoryBean` dùng cho những trường hợp interface trung gian thuộc hệ thống repository nhưng không muốn được khởi tạo độc lập. Không cần thêm annotation đó chỉ vì một interface được dùng làm fragment.

## 4. Ví dụ đầy đủ: tìm khách hàng hoạt động theo quốc gia

Giả sử yêu cầu nghiệp vụ là:

- Mã quốc gia bắt buộc.
- Chỉ lấy khách hàng có `active = true`.
- Số kết quả tối đa từ `1` đến `100`.
- Sắp xếp theo tên rồi theo ID để phân định khi trùng tên.
- Không có kết quả thì trả danh sách rỗng.

Ví dụ giả định ứng dụng đã có cấu hình JPA, nguồn dữ liệu và phạm vi quét entity/repository phù hợp. Mỗi khối Java dưới đây tương ứng với một file trong package `com.example.customer`.

### 4.1. Entity Customer

~~~java
package com.example.customer;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;

@Entity
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    @Column(nullable = false)
    private String displayName;

    @Column(nullable = false)
    private String country;

    @Column(nullable = false)
    private Boolean active;

    public Customer() {
    }

    public Long getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getCountry() {
        return country;
    }

    public void setCountry(String country) {
        this.country = country;
    }

    public Boolean getActive() {
        return active;
    }

    public void setActive(Boolean active) {
        this.active = active;
    }
}
~~~

Quy ước của ví dụ là quốc gia được lưu bằng mã chữ hoa như `VN`. Các thuộc tính bắt buộc cần được ứng dụng gán phù hợp khi ghi dữ liệu.

Annotation JPA là chi tiết của adapter đang minh họa, không phải yêu cầu chung cho mọi Spring Data store.

### 4.2. Khai báo interface fragment

~~~java
package com.example.customer;

import java.util.List;

public interface CustomerSearchFragment {

    List<Customer> searchActiveInCountry(
            String country,
            int maximumResults);
}
~~~

Interface thể hiện một nhóm hành vi có tên rõ ràng. Nó không chứa `EntityManager` và không buộc caller biết chuỗi JPQL.

Hợp đồng trả `List<Customer>` có nghĩa đây là một danh sách bị giới hạn số phần tử. Nó không cung cấp tổng số, offset hoặc metadata trang. Nếu caller cần phân trang thực sự, phải thiết kế chữ ký và implementation đáp ứng nhu cầu đó.

### 4.3. Viết lớp triển khai

~~~java
package com.example.customer;

import java.util.List;
import java.util.Locale;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.transaction.annotation.Transactional;

public class CustomerSearchFragmentImpl
        implements CustomerSearchFragment {

    @PersistenceContext
    private EntityManager entityManager;

    @Override
    @Transactional(readOnly = true)
    public List<Customer> searchActiveInCountry(
            String country,
            int maximumResults) {

        if (country == null || country.trim().isEmpty()) {
            throw new IllegalArgumentException(
                    "Phải cung cấp mã quốc gia");
        }

        if (maximumResults < 1 || maximumResults > 100) {
            throw new IllegalArgumentException(
                    "Số kết quả tối đa phải từ 1 đến 100");
        }

        String countryCode =
                country.trim().toUpperCase(Locale.ROOT);

        return entityManager.createQuery(
                "select c from Customer c " +
                "where c.country = :country " +
                "and c.active = true " +
                "order by c.displayName asc, c.id asc",
                Customer.class)
                .setParameter("country", countryCode)
                .setMaxResults(maximumResults)
                .getResultList();
    }
}
~~~

Những điểm cần quan sát:

- Lớp có tên `CustomerSearchFragmentImpl` và implements đúng interface.
- `@Override` giúp trình biên dịch kiểm tra chữ ký khớp hợp đồng.
- `@PersistenceContext` yêu cầu hạ tầng JPA của Spring inject tham chiếu `EntityManager`.
- Điều kiện truy vấn nằm trong implementation, không do tên phương thức tự tạo ra.
- Giá trị quốc gia được truyền bằng tham số truy vấn.
- `setMaxResults` giới hạn dữ liệu trả về từ truy vấn.
- `getResultList` trả danh sách rỗng nếu không có bản ghi phù hợp.

Chuẩn hóa mã quốc gia trong đầu vào không tự sửa dữ liệu đã lưu khác quy ước. Thứ tự chuỗi còn phụ thuộc quy tắc so sánh của kho dữ liệu; ví dụ chỉ công bố sắp theo tên và có ID làm tiêu chí phân định.

### 4.4. Ghép fragment vào repository

~~~java
package com.example.customer;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                CustomerSearchFragment {

    List<Customer> findByCountry(String country);
}
~~~

Repository này có ba nguồn hành vi:

| Phương thức | Nguồn triển khai |
| --- | --- |
| `save`, `findById` và CRUD khác | Base repository của JPA |
| `findByCountry` | Cơ chế truy vấn theo tên phương thức |
| `searchActiveInCountry` | `CustomerSearchFragmentImpl` |

Không cần khai báo lại `searchActiveInCountry` trong `CustomerRepository` vì nó đã được kế thừa từ fragment.

Chỉ viết một lớp đúng tên nhưng quên `extends CustomerSearchFragment` trên repository thì repository không công bố phương thức đó qua hợp đồng của mình.

### 4.5. Gọi qua repository từ service

~~~java
package com.example.customer;

import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class CustomerSearchService {

    private final CustomerRepository repository;

    public CustomerSearchService(CustomerRepository repository) {
        this.repository = repository;
    }

    public List<Customer> search(
            String country,
            int maximumResults) {

        return repository.searchActiveInCountry(
                country,
                maximumResults);
    }
}
~~~

Service dùng constructor injection và chỉ phụ thuộc interface repository. Caller không cần tự tìm hoặc khởi tạo `CustomerSearchFragmentImpl`.

Không dùng `new CustomerSearchFragmentImpl()` ngoài Spring rồi gọi ngay phương thức trong ví dụ: instance tự tạo đó chưa được inject `EntityManager` và chưa đi qua hạ tầng proxy/transaction cần thiết.

## 5. Spring Data ghép các phần triển khai như thế nào?

Ở mức khái niệm, việc tạo repository diễn ra như sau:

1. Hạ tầng repository phát hiện `CustomerRepository` trong phạm vi cấu hình.
2. Nó nhận diện các interface mà repository kế thừa, trong đó có `CustomerSearchFragment`.
3. Nó tìm implementation phù hợp với fragment và quy ước hậu tố.
4. Implementation được tích hợp vào composition của repository.
5. Proxy định tuyến từng phương thức đến phần xử lý tương ứng.

~~~mermaid
flowchart TD
    C["Service gọi CustomerRepository"] --> P["Repository proxy"]
    P --> B["Base repository: CRUD"]
    P --> Q["Truy vấn từ tên phương thức"]
    P --> F["CustomerSearchFragmentImpl"]
    F --> E["EntityManager trong ví dụ JPA"]
~~~

Đây là sơ đồ trách nhiệm, không phải danh sách các lớp nội bộ mà caller cần tự tạo.

### 5.1. extends quyết định hợp đồng repository

Nếu repository không kế thừa `CustomerSearchFragment`, biến có kiểu `CustomerRepository` sẽ không có phương thức fragment trong hợp đồng đang học.

~~~java
// Thiếu phần kế thừa fragment:
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
~~~

Đoạn rút gọn trên là ví dụ lỗi khai báo so với yêu cầu. Việc đặt một lớp `CustomerSearchFragmentImpl` trong cùng dự án không tự thêm phương thức vào interface repository.

Cách sửa là bổ sung `CustomerSearchFragment` vào danh sách interface được kế thừa, như phiên bản đầy đủ đã trình bày.

### 5.2. implements quyết định hợp đồng implementation

Lớp triển khai phải thực hiện đúng interface:

~~~java
public class CustomerSearchFragmentImpl
        implements CustomerSearchFragment {
    // Thân phương thức đúng chữ ký.
}
~~~

Khi viết implementation thật, `@Override` giúp phát hiện những lỗi như:

- Viết sai tên phương thức.
- Đổi kiểu tham số.
- Thiếu một tham số.
- Trả về kiểu không tương thích.

Có một phương thức trùng tên gần giống trong một lớp không phải là thay thế cho việc implements đúng hợp đồng.

### 5.3. Tên đúng và package đúng là hai điều kiện khác nhau

Tên `CustomerSearchFragmentImpl` có thể đúng, nhưng nếu lớp nằm ngoài phạm vi phát hiện implementation thì hạ tầng repository vẫn có thể không tìm được.

Ngược lại, một lớp nằm trong package được quét nhưng tên không theo quy ước đang cấu hình cũng không mặc nhiên được ghép đúng fragment.

Trong ví dụ, đặt các kiểu cùng package và dùng hậu tố mặc định giúp giảm các biến số khi bắt đầu.

### 5.4. Annotation stereotype không tự tạo quan hệ fragment

Trong đường phát hiện theo quy ước của ví dụ, không cần thêm `@Repository` vào lớp implementation chỉ để chứng minh nó là fragment. Spring Data sử dụng thông tin interface, implementation và cấu hình để ghép composition.

Một lớp tùy ý được gắn `@Component` hoặc `@Repository` cũng không tự trở thành phần triển khai của mọi repository có phương thức giống nó.

Nếu cần đăng ký hoặc wiring implementation một cách chủ động, phải làm theo cơ chế mà module hỗ trợ, bao gồm việc nhận diện bean phù hợp. Không dùng nhiều implementation cùng hợp đồng mà chưa xác định rõ cách lựa chọn.

## 6. Dependency injection và trạng thái của implementation

### 6.1. Để Spring quản lý vòng đời

Một fragment có thể cần các dependency như:

- API truy cập store.
- Thành phần chuẩn hóa điều kiện.
- Một bean cung cấp thời gian.
- Một collaborator chuyên xử lý logic đọc/ghi.

Các dependency bean thông thường có thể được truyền qua constructor. Trong ví dụ JPA, `EntityManager` được inject bằng `@PersistenceContext` để dùng đúng hạ tầng persistence của ứng dụng.

Nếu có nhiều persistence unit, cần cấu hình việc chọn đơn vị persistence phù hợp. Việc fragment được phát hiện không tự quyết định nguồn dữ liệu nghiệp vụ nào cần dùng.

### 6.2. Không giữ đầu vào request trong field

Không tổ chức implementation theo kiểu:

~~~java
// Không dùng field để giữ trạng thái của lần gọi:
// private String currentCountry;
// private int currentMaximumResults;
~~~

Instance implementation thường có thể được nhiều lời gọi dùng chung. Nếu ghi đầu vào của từng request vào field, các lời gọi đồng thời có thể ảnh hưởng lẫn nhau.

Trong ví dụ đầy đủ:

- `countryCode` là biến cục bộ.
- `maximumResults` là tham số.
- Đối tượng truy vấn được tạo và sử dụng trong phương thức.
- Field chỉ giữ dependency do hạ tầng inject.

Tham chiếu `EntityManager` được inject theo mô hình quản lý của Spring/JPA không có nghĩa bạn nên giữ thêm một query đang chạy hoặc một entity theo từng người dùng trong field của fragment.

### 6.3. Không tạo phụ thuộc vòng để gọi lại chính phương thức fragment

Không inject chính `CustomerRepository` vào `CustomerSearchFragmentImpl` chỉ để implementation gọi lại `repository.searchActiveInCountry(...)`.

Thiết kế đó có thể tạo phụ thuộc vòng hoặc đưa lời gọi quay lại đúng phương thức đang xử lý. Fragment cần thực hiện logic của nó qua dependency thích hợp, thay vì gọi vòng vào chính hợp đồng đang được triển khai.

Nếu nhiều lớp cần dùng chung một thuật toán, tách thuật toán đó thành một collaborator rõ trách nhiệm. Nếu cần điều phối nhiều repository, một service ở tầng ứng dụng thường là nơi phù hợp hơn.

## 7. Transaction trong ví dụ thuộc phạm vi JPA

Phương thức implementation có:

~~~java
@Transactional(readOnly = true)
public List<Customer> searchActiveInCountry(
        String country,
        int maximumResults) {
    // Logic truy vấn.
}
~~~

Annotation này thể hiện lựa chọn transaction cho phương thức đọc trong ví dụ JPA. Hạ tầng transaction phải được cấu hình phù hợp để annotation có hiệu lực.

Không suy ra rằng mọi phương thức tùy chỉnh sẽ tự nhận đầy đủ thiết lập transaction của mọi phương thức CRUD chỉ vì repository kế thừa `JpaRepository`.

Những điểm cần phân biệt:

- Fragment là cách ghép hành vi vào repository.
- Transaction là cơ chế quản lý thực thi và tài nguyên.
- `readOnly` không tự tạo snapshot ổn định cho mọi lần đọc.
- Một transaction của JPA không mặc nhiên bao phủ thêm một store khác.

Nếu implementation dùng store khác, API truy cập dữ liệu và cơ chế transaction phải phù hợp với store đó. Giữ interface tương tự không làm phần triển khai trở nên độc lập với persistence.

## 8. Interface dùng chung đến đâu?

### 8.1. Tách contract không đồng nghĩa tự có portability

`CustomerSearchFragment` không tham chiếu `EntityManager` nên phần hợp đồng không trực tiếp phụ thuộc API JPA. Tuy nhiên, nó vẫn trả về `Customer`, là entity JPA của ví dụ.

Nếu muốn cùng một hợp đồng đọc cho nhiều store có model khác nhau, cần xem lại kiểu đầu vào và đầu ra, chẳng hạn dùng DTO riêng. Sau đó mỗi adapter có implementation phù hợp.

Không đổi import của `EntityManager` thành một API khác rồi mặc định tất cả truy vấn và transaction vẫn giữ nguyên ý nghĩa.

### 8.2. Tái sử dụng fragment khi trách nhiệm thực sự giống nhau

Một fragment có thể hữu ích khi nhiều repository cần một nhóm hành vi có hợp đồng rõ ràng. Tuy nhiên, một implementation cụ thể viết cứng `Customer` không tự trở thành implementation generic cho mọi entity.

Những yêu cầu như xác định kiểu domain tại runtime, metadata repository hoặc thao tác chung cho nhiều loại entity cần thiết kế riêng. Không thêm tham số kiểu `<T>` chỉ để che đi logic thực chất vẫn cố định theo một model.

Ở bước khai báo đầu tiên, ưu tiên một fragment nhỏ, tên rõ và có implementation đúng hợp đồng.

### 8.3. Giữ nhóm phương thức có tính liên quan

Một fragment tìm kiếm có thể chứa những phương thức đọc cùng chủ đề. Không nên để nó đồng thời chứa mọi thao tác không biết đặt ở đâu.

| Nhu cầu | Cách tổ chức thường phù hợp |
| --- | --- |
| Truy vấn đơn giản đã diễn đạt rõ bằng tên phương thức | Dùng cơ chế query của repository |
| Nhóm thao tác tùy chỉnh gắn với truy cập một domain/store | Fragment |
| Điều phối nhiều repository trong một quy trình nghiệp vụ | Service |
| Thay đổi hành vi nền tảng cho một hệ repository rộng hơn | Xem xét cơ chế base repository phù hợp |
| Tự động cập nhật metadata tạo/sửa | Cơ chế auditing và lifecycle tương ứng |

Bảng là gợi ý về trách nhiệm, không bắt buộc phải tạo fragment cho mọi phương thức dài.

## 9. Phương thức trùng chữ ký cần được thiết kế có chủ đích

Một repository có thể ghép nhiều fragment. Khi các fragment hoặc base repository cùng liên quan đến một chữ ký, thứ tự composition và quy tắc ưu tiên trở nên quan trọng.

Với bài nhập môn, chọn phương thức đặc thù `searchActiveInCountry` giúp tránh vô tình đụng vào CRUD.

Nếu muốn tùy chỉnh một phương thức có sẵn như `save`:

- Xác định rõ signature và generic của hợp đồng.
- Hiểu quy tắc ghép fragment và phần triển khai base của module.
- Bảo đảm các hành vi cần thiết như transaction và semantics ghi vẫn phù hợp.
- Xác nhận phương thức nào thực sự nhận lời gọi.

Chỉ có tên `save` trong một lớp không chứng minh bạn đã thay thế thành công hành vi của repository.

Nếu nhiều fragment vô tình công bố cùng một phương thức, nên làm rõ trách nhiệm hoặc đổi thiết kế trước khi dựa vào thứ tự khai báo để giải quyết sự mơ hồ.

## 10. Quan sát hành vi mong đợi

Giả sử dữ liệu ổn định trong lúc gọi ví dụ:

| id | displayName | country | active |
| --- | --- | --- | --- |
| 11 | An | VN | true |
| 12 | An | VN | true |
| 13 | Binh | VN | true |
| 14 | Chi | VN | false |
| 15 | David | US | true |

Gọi:

~~~java
List<Customer> customers =
        repository.searchActiveInCountry(" vn ", 2);
~~~

Theo hợp đồng và implementation:

1. Đầu vào được chuẩn hóa thành `VN`.
2. Khách hàng có `active = false` bị loại.
3. Khách hàng thuộc `US` bị loại.
4. Các khách hàng phù hợp được sắp theo tên và ID.
5. Giới hạn `2` được áp dụng.

Trên dữ liệu minh họa với thứ tự chuỗi tương ứng, kết quả là khách hàng ID `11` và `12`.

| Tình huống | Hành vi được định nghĩa |
| --- | --- |
| Quốc gia `" vn "`, giới hạn `2` | Chuẩn hóa đầu vào, lấy tối đa hai khách hàng phù hợp |
| Quốc gia `"US"`, giới hạn `10` | Trả khách hàng ID `15` trên tập dữ liệu minh họa |
| Quốc gia không có dữ liệu | Trả danh sách rỗng |
| Quốc gia `null` hoặc chỉ có khoảng trắng | `IllegalArgumentException` |
| Giới hạn `0` hoặc lớn hơn `100` | `IllegalArgumentException` |
| Hai người cùng tên | Phân định bằng ID tăng dần |
| Có hơn giới hạn số người phù hợp | Chỉ trả tối đa số lượng được yêu cầu |

Không lấy `customers.size()` làm tổng số khách hàng phù hợp trong kho: danh sách đã bị giới hạn. Nếu cần tổng số và trang, hãy thiết kế một phương thức có hợp đồng tương ứng.

Các kết quả trong bảng là minh họa hành vi mong đợi, không phải tuyên bố đã chạy ứng dụng hay truy vấn trên một cơ sở dữ liệu cụ thể.

## 11. Nhận diện lỗi theo triệu chứng

| Triệu chứng | Nguyên nhân có thể gặp | Điều cần xem lại |
| --- | --- | --- |
| Không gọi được phương thức trên biến repository | Repository chưa kế thừa interface fragment | Danh sách `extends` của repository |
| Lớp implementation không biên dịch | Chữ ký không khớp interface | Tên phương thức, tham số, kiểu trả về và `@Override` |
| Repository khởi tạo lỗi và nhắc đến việc phân tích tên phương thức | Hành vi tùy chỉnh chưa được ghép, phương thức bị xem như query cần tạo | Naming, package và quan hệ fragment |
| Implementation đúng tên nhưng không được dùng | Ngoài phạm vi phát hiện hoặc khác hậu tố cấu hình | Vị trí package và `repositoryImplementationPostfix` |
| Có nhiều ứng viên implementation | Nhiều lớp hoặc bean phù hợp nhưng chưa lựa chọn rõ | Quy tắc nhận diện/wiring theo module |
| `EntityManager` là `null` khi gọi | Tự tạo instance ngoài container hoặc thiếu hạ tầng injection | Vòng đời bean và cấu hình persistence |
| Có phụ thuộc vòng hoặc lời gọi lặp lại | Fragment gọi lại chính repository/phương thức mình triển khai | Hướng phụ thuộc và collaborator |
| Đầu vào giữa các request ảnh hưởng nhau | Giữ trạng thái từng lời gọi trong field | Chuyển dữ liệu request về biến cục bộ |
| Thay store thì implementation không còn dùng được | Logic truy vấn phụ thuộc API của store cũ | Tách hợp đồng và adapter phù hợp |
| Cần metadata trang nhưng chỉ nhận List | Hợp đồng chỉ giới hạn số phần tử | Thiết kế lại phương thức phân trang |

Khi gặp lỗi, bắt đầu từ ba quan hệ: **repository extends fragment**, **implementation implements fragment**, **implementation được phát hiện theo cấu hình**. Sau đó mới xem logic truy vấn bên trong.

## 12. Cách đọc một khai báo fragment hoàn chỉnh

Với ví dụ đã có, có thể diễn giải ngắn gọn:

~~~text
CustomerSearchFragment
    công bố hành vi searchActiveInCountry

CustomerSearchFragmentImpl
    thực hiện hành vi đó bằng EntityManager

CustomerRepository
    kế thừa fragment và JpaRepository

CustomerSearchService
    gọi qua CustomerRepository
~~~

Interface fragment giữ hợp đồng, implementation giữ logic tùy chỉnh và repository proxy ghép hành vi với các khả năng có sẵn. Đặt đúng tên, bố trí đúng phạm vi package và để Spring quản lý dependency là những bước nền tảng để một fragment hoạt động đúng.
