# Fragment không được nạp, tên Impl sai hoặc phương thức trùng

Một phương thức custom có implementation đầy đủ vẫn có thể không được gọi khi đi qua repository. Nguyên nhân thường nằm ở một trong ba liên kết: repository chưa kế thừa fragment interface, hạ tầng chưa tìm đúng implementation, hoặc một implementation khác đang nhận cùng chữ ký phương thức.

Trong chương **Lỗi và chẩn đoán** của module **SPRING_DATA_COMMONS**, bài học này trình bày cách theo dõi quá trình ghép repository từ các fragment, sửa quy ước tên và phân biệt lỗi discovery với lỗi dispatch. Cơ chế mở rộng dùng chung phải phối hợp đúng với CRUD, derived query, metadata và module lưu trữ thực tế; một class có hậu tố Impl không tự trở thành mọi loại custom repository.

## 1. Repository là một composition, không chỉ một lớp implementation

Một repository có thể kết hợp:

- Implementation nền của store cho các phương thức CRUD.
- Các khả năng bổ sung do module cung cấp, như executor truy vấn được hỗ trợ.
- Một hoặc nhiều custom fragment của ứng dụng.
- Query methods và cách xử lý lời gọi của hạ tầng repository.

Mô hình cần quan sát:

```text
CustomerRepository proxy
    |
    +-- CRUD của store
    |
    +-- CustomerSearch -> CustomerSearchImpl
    |
    +-- Một fragment khác nếu được khai báo
    |
    +-- Cơ chế thực thi query methods tương ứng
```

Để một phương thức custom được gọi đúng, cần đồng thời có:

1. Hợp đồng phương thức nằm trong fragment interface được repository kế thừa.
2. Implementation thực hiện đúng hợp đồng đó.
3. Implementation được discovery hoặc đăng ký theo cơ chế repository nhận biết.
4. Không có xung đột dispatch ngoài ý định.

Tài liệu [custom repository implementations của Spring Data Commons](https://docs.spring.io/spring-data/commons/reference/repositories/custom-implementations.html) mô tả mô hình composition và cơ chế fragment này.

## 2. Một cấu trúc fragment đúng để đối chiếu

Phần minh họa chọn Spring Data JPA. Domain `Customer` có ID kiểu UUID, tên và tenant ID. Entity mapping, cấu hình JPA và dữ liệu kết nối được giả định đã có.

Các kiểu đầu vào và đầu ra:

```java
package com.example.customer.persistence;

public record CustomerSearchCriteria(long tenantId, String name) {
}
```

```java
package com.example.customer.readmodel;

import java.util.UUID;

public record CustomerCard(UUID id, String name) {
}
```

### 2.1. Fragment interface

```java
package com.example.customer.persistence;

import com.example.customer.readmodel.CustomerCard;

import java.util.List;

public interface CustomerSearch {

    List<CustomerCard> searchByCriteria(CustomerSearchCriteria criteria);
}
```

Fragment này không cần tự kế thừa `CrudRepository`. Nó chỉ mô tả khả năng custom mà repository sẽ kết hợp.

### 2.2. Implementation theo hậu tố mặc định

```java
package com.example.customer.persistence.custom;

import com.example.customer.persistence.CustomerSearch;
import com.example.customer.persistence.CustomerSearchCriteria;
import com.example.customer.readmodel.CustomerCard;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

public class CustomerSearchImpl implements CustomerSearch {

    @PersistenceContext
    private EntityManager entityManager;

    @Override
    @Transactional(readOnly = true)
    public List<CustomerCard> searchByCriteria(
            CustomerSearchCriteria criteria) {
        if (criteria == null || criteria.tenantId() <= 0
                || criteria.name() == null || criteria.name().isBlank()) {
            throw new IllegalArgumentException("Điều kiện tìm kiếm không hợp lệ");
        }

        return entityManager.createQuery("""
                select new com.example.customer.readmodel.CustomerCard(
                    c.id, c.name)
                from Customer c
                where c.tenantId = :tenantId
                  and c.name = :name
                order by c.id
                """, CustomerCard.class)
                .setParameter("tenantId", criteria.tenantId())
                .setParameter("name", criteria.name().strip())
                .getResultList();
    }
}
```

JPQL dùng entity name `Customer` và các thuộc tính giả định ở trên. Ví dụ dùng một persistence context và transaction manager JPA phù hợp đã được cấu hình. Nếu ứng dụng có nhiều persistence unit hoặc manager, phải chỉ định tài nguyên đúng thay vì mặc định mọi fragment dùng chung một nguồn.

### 2.3. Repository kế thừa fragment

```java
package com.example.customer.persistence;

import com.example.customer.domain.Customer;
import org.springframework.data.repository.CrudRepository;

import java.util.UUID;

public interface CustomerRepository
        extends CrudRepository<Customer, UUID>, CustomerSearch {
}
```

Điểm cần đối chiếu là cặp **CustomerSearch → CustomerSearchImpl**, cùng quan hệ `CustomerRepository extends CustomerSearch`. Chỉ tạo class implementation mà quên quan hệ kế thừa cuối cùng chưa kết hợp được khả năng custom vào repository.

## 3. Quy ước tên: dựa vào fragment, không đoán từ repository cuối

Với postfix mặc định `Impl`:

| Fragment interface | Implementation theo convention |
| --- | --- |
| `CustomerSearch` | `CustomerSearchImpl` |
| `CustomerArchive` | `CustomerArchiveImpl` |
| `CustomerStatistics` | `CustomerStatisticsImpl` |

Đừng mặc định `CustomerRepositoryImpl` là tên implementation cho tất cả các fragment của CustomerRepository.

Spring Data từng có quy ước một custom implementation dựa trên tên repository cuối cộng postfix. Tài liệu hiện hành coi cách đặt tên single-custom implementation đó là hướng cũ không được khuyến nghị cho thiết kế mới, đồng thời ưu tiên mô hình fragment. Vì còn cơ chế tương thích, một class trùng tên theo quy ước cũ có thể bị nhận diện ngoài ý muốn.

Vì vậy, khi chuyển từ cấu trúc cũ sang fragment:

- Xác định mỗi interface custom cần implementation nào.
- Kiểm tra class có tên repository cuối cộng postfix còn tồn tại và còn được discovery không.
- Không chỉ đổi tên một file rồi để cả implementation cũ và mới cùng tham gia ngoài dự kiến.

Đây là vấn đề composition, không phải yêu cầu mọi implementation trong dự án đều phải có cùng một tên cố định.

### 3.1. Postfix có thể đã bị đổi

Ví dụ cấu hình JPA:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@Configuration
@EnableJpaRepositories(
        basePackages = "com.example.customer.persistence",
        repositoryImplementationPostfix = "Custom")
public class CustomerRepositoryConfiguration {
}
```

Khi cấu hình này quản lý repository, tên theo convention cho fragment `CustomerSearch` sẽ dùng postfix Custom, tức `CustomerSearchCustom`.

Nếu class vẫn là `CustomerSearchImpl`, cần đối chiếu cách đăng ký đang dùng thay vì tiếp tục cho rằng hậu tố Impl luôn là mặc định có hiệu lực. Annotation này chỉ minh họa phần cấu hình repository; không phải cấu hình JPA đầy đủ.

Các tùy chọn postfix, phạm vi và repository base class là những mục khác nhau trong [EnableJpaRepositories API](https://docs.spring.io/spring-data/jpa/docs/current/api/org/springframework/data/jpa/repository/config/EnableJpaRepositories.html). Với module khác, sử dụng cơ chế cấu hình tương ứng.

## 4. Tên đúng nhưng package hoặc classpath không đúng

Hạ tầng repository có phạm vi discovery cho implementation fragment. Một class nằm ở package bất kỳ trên classpath không được bảo đảm tự ghép vào mọi repository.

Với cấu trúc minh họa:

```text
com.example.customer.persistence
    CustomerRepository
    CustomerSearch
    CustomerSearchCriteria

com.example.customer.persistence.custom
    CustomerSearchImpl
```

implementation nằm trong namespace phù hợp bên dưới nơi repository được tìm thấy. Khi chuyển class sang một module hoặc package ngoài phạm vi đó, phải đánh giá lại cách đăng ký.

### 4.1. Component scan và fragment discovery là hai câu hỏi khác nhau

Một bean implementation đã có trong ApplicationContext chưa tự chứng minh rằng repository proxy đã ghép bean ấy cho phương thức custom.

Cũng không nên mặc định implementation nào không có `@Component` thì chắc chắn không được tìm thấy: hạ tầng repository có cơ chế phát hiện và đăng ký implementation theo convention, sau đó xử lý dependency injection như một bean phù hợp.

Thêm `@Repository` hoặc `@Component` có thể hữu ích cho một thiết kế bean cụ thể, nhưng không tự sửa tên fragment, quan hệ kế thừa hoặc postfix sai.

### 4.2. Trường hợp class nằm trong thư viện ngoài

Nếu fragment implementation được đóng gói trong một archive ở namespace khác, convention scan cục bộ có thể không tìm thấy nó. Cần dùng cơ chế đóng góp hoặc đăng ký fragment được phiên bản Spring Data đang dùng hỗ trợ.

Tài liệu hiện hành có mô tả cách đăng ký fragment qua metadata thư viện. Đây là một lựa chọn cho extension được phân phối riêng; không phải lý do mở rộng component scan ra toàn bộ classpath để giải quyết mọi trường hợp.

Trước khi thay cơ chế, hãy xác nhận artifact chứa implementation thật sự có trong runtime và cấu hình test có dùng cùng cơ chế đăng ký hay không.

## 5. Implementation có mặt nhưng method không khớp

### 5.1. Dùng `implements` và `@Override` để phát hiện sai chữ ký

Fragment yêu cầu:

```java
List<CustomerCard> searchByCriteria(CustomerSearchCriteria criteria);
```

Một method cùng tên nhưng nhận String hoặc một lớp Criteria khác package không phải cùng hợp đồng. Kiểu tham số và quan hệ kiểu trả về phải tương thích theo Java.

Việc class khai báo `implements CustomerSearch` cùng `@Override` trên method giúp compiler phát hiện nhiều sai sót sớm. Nếu bỏ implements và chỉ tình cờ viết một method gần giống, người đọc dễ nhầm rằng hạ tầng sẽ tự ghép theo ý định.

### 5.2. Overload không phải override

Hai method sau là hai overload khác nhau:

```java
List<CustomerCard> searchByCriteria(CustomerSearchCriteria criteria);
List<CustomerCard> searchByCriteria(String text);
```

Việc implementation có overload String không đủ để phục vụ lời gọi nhận CustomerSearchCriteria. Khi đặt breakpoint, phải chọn đúng chữ ký đang được gọi.

### 5.3. Generic và erasure cần giữ hợp đồng nhất quán

Một fragment generic có thể khai báo:

```java
public interface GuardedSave<T> {

    <S extends T> S save(S entity);
}
```

Nếu mục tiêu là can thiệp vào chữ ký CRUD tương ứng, implementation phải thực hiện hợp đồng tương thích. Không tùy tiện đổi sang `Object save(Object)` hoặc một method gần giống rồi dựa vào ép kiểu để coi là đã override đúng.

Một số xung đột generic hoặc return type bị Java từ chối ngay khi biên dịch; chúng chưa phải lỗi runtime của Spring Data. Phân biệt rõ lỗi compiler với việc method hợp lệ nhưng bị dispatch sang implementation khác.

## 6. Khi method custom bị hiểu thành query method

Một dấu hiệu thường gặp là lỗi tạo query hoặc lỗi không tìm thấy thuộc tính liên quan tới tên phương thức custom.

Ví dụ `searchByCriteria(CustomerSearchCriteria)` được thiết kế để implementation tự xây query. Nếu hạ tầng không nhận được implementation custom tương ứng, nó có thể đưa method vào quá trình xử lý query theo cấu hình lookup của store. Khi Customer không có property criteria, lỗi được quan sát có thể trông giống lỗi derived query.

Không mặc định cách sửa là thêm property criteria vào entity hoặc đổi tên method thành một chuỗi derived query rất dài. Trước tiên cần hỏi method này thuộc loại nào:

```text
Method vốn là derived query?
    -> Kiểm tra tên property, toán tử và hỗ trợ của store.

Method vốn là custom fragment?
    -> Kiểm tra fragment interface, implementation, tên và discovery.
```

Loại exception, thời điểm phát lỗi và thông báo cụ thể phụ thuộc phiên bản, store và bootstrap mode. Không yêu cầu mọi trường hợp thiếu fragment đều có cùng một dòng lỗi.

Nếu repository khởi tạo lazy, ứng dụng có thể lên được nhưng lỗi chỉ xuất hiện khi gọi method. Chỉ kiểm tra context đã khởi động chưa đủ để chứng minh fragment có thể được sử dụng.

## 7. Bean name và nhiều implementation cùng tên

Có thể có hai class `CustomerSearchImpl` ở hai package khác nhau. Hạ tầng phải giải quyết candidate dựa trên quy tắc discovery và tên bean, không phải theo thứ tự thư mục mà người dùng nhìn thấy.

Khi có nhiều candidate, cần ghi rõ:

- Fully qualified class name của từng implementation.
- Tên bean được đăng ký hoặc được sinh theo convention.
- Postfix đang có hiệu lực.
- Repository configuration nào đang quản lý repository.
- Bean nào cuối cùng được composition tham chiếu.

Đừng thêm `@Primary` rồi mặc định quy tắc discovery fragment đã được sửa. Lựa chọn dependency thông thường của container và việc hạ tầng repository gắn implementation là những cơ chế liên quan nhưng không đồng nhất.

Tương tự, `@Qualifier` ở một service để chọn repository bean không tự thay implementation bên trong repository proxy đó.

### 7.1. Manual wiring theo tên phù hợp

Khi cần khai báo bean rõ ràng, có thể dùng tên theo convention mà cấu hình đang nhận biết. Với postfix Impl của ví dụ:

```java
import com.example.customer.persistence.custom.CustomerSearchImpl;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CustomerSearchWiring {

    @Bean("customerSearchImpl")
    CustomerSearch customerSearchFragment() {
        return new CustomerSearchImpl();
    }
}
```

Cấu hình này giả định `CustomerSearch` được import hoặc nằm trong cùng package và cơ chế xử lý persistence annotation đã được bật. Đối tượng trả về là Spring-managed bean nên trường `@PersistenceContext` của implementation được xử lý theo hạ tầng JPA.

Đây là phương án wiring có chủ đích để hạ tầng tham chiếu bean tương ứng, không phải yêu cầu luôn khai báo thêm một bean bên cạnh mọi implementation tự phát hiện. Nếu postfix thay đổi, tên bean và cơ chế matching cũng phải được đối chiếu lại.

Không tạo implementation bằng `new` trong service rồi coi lời gọi đó tương đương lời gọi qua repository: khi ấy bạn đã đi theo một đường thực thi khác và có thể bỏ qua injection hoặc advice cần thiết.

## 8. Phương thức trùng: có thể gọi nhầm mà không ném lỗi

Giả sử hai fragment đều có cùng chữ ký:

```java
public interface LiveCustomerSearch {
    List<CustomerCard> searchByCriteria(CustomerSearchCriteria criteria);
}

public interface ArchivedCustomerSearch {
    List<CustomerCard> searchByCriteria(CustomerSearchCriteria criteria);
}
```

Repository kết hợp cả hai:

```java
public interface CustomerRepository
        extends CrudRepository<Customer, UUID>,
                LiveCustomerSearch,
                ArchivedCustomerSearch {
}
```

Giả định cả hai implementation đều được đăng ký đúng. Theo mô hình fragment của Spring Data, custom implementation được ghép theo thứ tự khai báo; thứ tự này giúp phân giải khi nhiều fragment đóng góp cùng method signature. Vì vậy, phương thức có thể đi tới một implementation ưu tiên trước mà không tạo lỗi “trùng method” ở runtime.

Điều cần sửa không chỉ là làm context khởi động. Phải xác định nghiệp vụ muốn tìm khách hàng đang hoạt động hay khách hàng lưu trữ.

### 8.1. Cách giảm sự mơ hồ

Nếu hai hành vi thực sự khác nhau, dùng method thể hiện ý nghĩa khác nhau, chẳng hạn:

```java
searchLiveByCriteria(criteria)
searchArchivedByCriteria(criteria)
```

Nếu chỉ muốn một khả năng, loại fragment không cần khỏi composition. Nếu thứ tự ưu tiên có chủ đích, cần thể hiện rõ trong thiết kế và có test xác nhận đường dispatch.

Không xem việc đổi thứ tự interface một cách tình cờ là sửa lỗi bền vững mà không giải thích lý do chọn hành vi.

### 8.2. Đừng nhầm với xung đột Java

Hai interface có method cùng tên nhưng khác tham số có thể tạo overload hợp lệ. Hai method có return type không tương thích hoặc những default method xung đột có thể bị Java từ chối ngay tại khai báo interface kế thừa.

Thứ tự fragment runtime không chữa được một khai báo Java vốn không biên dịch. Hãy giải quyết hợp đồng kiểu trước, rồi mới phân tích ưu tiên implementation của repository.

## 9. Custom fragment có thể ưu tiên hơn CRUD nền

Custom implementation có thể nhận method trùng chữ ký với implementation nền hoặc repository aspect. Tài liệu Spring Data mô tả custom fragment có ưu tiên cao hơn các phần nền đó.

Ví dụ một repository cố ý dùng fragment GuardedSave:

```java
public interface CustomerRepository
        extends CrudRepository<Customer, UUID>, GuardedSave<Customer> {
}
```

Nếu `GuardedSaveImpl` được ghép đúng và cung cấp save tương ứng, lời gọi `repository.save(customer)` có thể đi qua custom behavior. Đây là một khả năng mở rộng mạnh, nên phải có ý định rõ.

### 9.1. Tránh tự gọi lại chính repository proxy để thực hiện cùng method

Nếu implementation custom của save gọi lại `customerRepository.save(entity)` trên chính proxy có fragment đó, lời gọi có thể quay về custom save lần nữa, tạo vòng đệ quy hoặc vòng phụ thuộc khi wiring.

Cần chọn cách truy cập persistence phù hợp với module, hoặc đặt bước kiểm tra ở service nếu đó là nhu cầu nghiệp vụ đơn giản. Không sao chép một đoạn persist/merge chung rồi giả định mọi store có cùng cơ chế nhận diện entity mới, version và auditing.

### 9.2. Fragment riêng khác custom base class

Fragment bổ sung hành vi cho những repository chủ động kế thừa interface đó. Custom base repository class là cơ chế khác, thường dùng khi muốn thay hành vi nền trên một nhóm repository theo cấu hình factory.

Đặt tên một class là `MyRepositoryImpl` không tự biến nó thành base class của mọi repository. Nếu thực sự cần thay base class, phải dùng cấu hình module và constructor phù hợp hạ tầng của store.

## 10. Kiểm chứng bằng lời gọi qua repository thật

### 10.1. Bean implementation tồn tại chưa đủ

Một test chỉ lấy được `CustomerSearchImpl` từ container chứng minh rằng bean tồn tại. Nó chưa chứng minh `CustomerRepository.searchByCriteria` đang được dispatch tới bean đó.

Cần gọi qua repository mà ứng dụng sẽ sử dụng. Với ví dụ JPA, có thể chuẩn bị fixture:

```text
Customer A: tenant 42, name Lan
Customer B: tenant 7, name Lan
Customer C: tenant 42, name Mai
```

Sau khi fixture được lưu và đồng bộ theo thiết kế test, lời gọi:

```java
List<CustomerCard> result = repository.searchByCriteria(
        new CustomerSearchCriteria(42L, "  Lan  "));
```

phải trả đúng card của A theo logic custom trong ví dụ. Có thể so sánh ID của A và tên Lan, đồng thời xác nhận không có B hoặc C.

Đây là kiểm thử tích hợp đường gọi qua repository, không phải một lần gọi trực tiếp implementation tách rời.

### 10.2. Đặt quan sát ở implementation dự kiến

Trong quá trình điều tra, có thể dùng breakpoint, logging có mục tiêu hoặc một công cụ quan sát invocation phù hợp để xác nhận implementation và chữ ký thật sự được gọi.

Không kết luận từ tên lớp proxy. Cũng không mock toàn bộ repository trả kết quả mong muốn rồi coi là đã kiểm chứng discovery fragment.

### 10.3. Kiểm tra cả lỗi khi bootstrap và lần sử dụng đầu

Nếu dùng bootstrap lazy, cần gọi method trong test để kích hoạt đường khởi tạo thực sự. Với nhiều fragment cùng chữ ký, cần ca phân biệt được hai hành vi; chỉ kiểm tra kết quả không null có thể bỏ sót việc implementation sai được ưu tiên.

Với override CRUD, kiểm tra thêm entity mới, cập nhật, version và metadata liên quan theo store. Một test custom method chạy thành công không tự chứng minh mọi phương thức nền còn giữ đúng hợp đồng.

## 11. Quy trình chẩn đoán theo thứ tự

| Bước | Điều cần xác nhận |
| --- | --- |
| 1. Repository đích | Đúng bean và interface mà ứng dụng đang gọi |
| 2. Hợp đồng fragment | Repository thực sự kế thừa fragment chứa method |
| 3. Chữ ký | Implementation dùng đúng interface, tham số và return type |
| 4. Tên | Class name dựa trên fragment cùng postfix đang có hiệu lực |
| 5. Discovery | Package và runtime artifact nằm trong cơ chế đăng ký phù hợp |
| 6. Wiring | Dependency được inject, bean name và candidate không mơ hồ |
| 7. Composition | Không có implementation cũ hoặc fragment khác nhận method ngoài ý muốn |
| 8. Dispatch | Gọi qua repository thật và quan sát implementation dự kiến |
| 9. Store behavior | Query, transaction và mapping trong implementation đúng module |

Các triệu chứng thường gặp có thể đọc như sau:

```text
Method custom bị phân tích như derived query
    -> Ưu tiên kiểm tra việc ghép fragment.

Bean implementation tồn tại nhưng breakpoint không được chạm
    -> Kiểm tra composition, chữ ký và method ưu tiên khác.

Context khởi động nhưng lời gọi đầu thất bại
    -> Kiểm tra bootstrap lazy và nguyên nhân tạo query hoặc fragment.

Sau đổi package hoặc postfix, custom method ngừng hoạt động
    -> Đối chiếu discovery và convention đang có hiệu lực.

Sau thêm fragment, CRUD hoặc một method cũ đổi hành vi
    -> Kiểm tra trùng chữ ký và thứ tự ưu tiên.
```

Một fragment được nạp đúng phải có hợp đồng rõ, implementation được nhận diện đúng và đường gọi có thể kiểm chứng qua repository proxy. Khi ba liên kết đó tách bạch, việc sửa tên Impl, phạm vi scan hoặc phương thức trùng sẽ hướng vào nguyên nhân thực thay vì thay đổi entity, query hoặc wiring một cách ngẫu nhiên.
