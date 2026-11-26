# Không xác định được kiểu miền hoặc kiểu ID của generic

Khi tạo repository, Spring Data cần biết repository đó quản lý kiểu miền nào và nhận kiểu định danh nào. Một interface trung gian còn chứa `T` hoặc `ID` là điều bình thường trong thiết kế dùng chung, nhưng interface được tạo thành repository bean cụ thể phải cung cấp metadata phù hợp. Nếu chuỗi kế thừa làm mất thông tin kiểu, hoặc một template generic bị tạo bean trực tiếp, lỗi có thể xuất hiện ngay khi khởi tạo repository.

Trong chương **Lỗi và chẩn đoán** của module **SPRING_DATA_COMMONS**, bài học này giải thích cách lần theo kiểu miền và kiểu ID qua generic, nhận diện các khai báo làm mất thông tin và sửa đúng tầng. Metadata này là nền cho Repository, CRUD, derived query, QBE, projection và các mở rộng repository; nó không thay thế yêu cầu mapping riêng của từng store.

## 1. Hai tham số kiểu có vai trò khác nhau

Khai báo repository cơ bản:

```java
Repository<T, ID>
```

Trong đó:

- `T` là kiểu miền hoặc aggregate mà repository quản lý.
- `ID` là kiểu định danh được hợp đồng repository sử dụng.

Ví dụ:

```java
import org.springframework.data.repository.CrudRepository;

import java.util.UUID;

public interface CustomerRepository
        extends CrudRepository<Customer, UUID> {
}
```

Trong ví dụ, `Customer` là lớp miền của ứng dụng và định danh của nó được thiết kế là UUID. Framework có thể lần từ `CustomerRepository` tới `Repository<Customer, UUID>` để xác định hai kiểu đó.

Tên biến generic không quyết định vai trò. Một interface có thể đặt tên là `ENTITY`, `KEY` hoặc `E`, `K`; điều quan trọng là chúng được truyền đúng vị trí vào `Repository<T, ID>`.

Tài liệu [định nghĩa repository interface](https://docs.spring.io/spring-data/commons/reference/repositories/definition.html) mô tả yêu cầu repository gắn với domain class và kiểu ID, cùng cách tạo base interface dùng chung.

### 1.1. Có hai bước kiểm tra riêng

```text
Bước A: metadata suy ra kiểu nào?
    domain = Customer
    ID = UUID
                |
                v
Bước B: store có quản lý Customer và mapping ID tương ứng không?
```

Bước A đúng không bảo đảm bước B đúng. Một repository có thể xác định rõ domain là một DTO không được JPA quản lý; khi đó lỗi không phải vì tên generic còn chưa ràng buộc.

Ngược lại, thêm annotation entity lên một lớp không sửa được một nhánh kế thừa đã làm mất toàn bộ thông tin kiểu.

## 2. Lỗi đầu tiên cần kiểm tra: template generic bị tạo bean

Một base repository dùng chung:

```java
import org.springframework.data.repository.CrudRepository;

public interface BaseRepository<T, ID>
        extends CrudRepository<T, ID> {
}
```

Nếu base này nằm trong phạm vi discovery và được coi là repository cần tạo trực tiếp, framework chưa có một Customer hay Order cụ thể để gán cho T.

Cách diễn đạt đúng ý định là đánh dấu nó không phải repository bean độc lập:

```java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface BaseRepository<T, ID>
        extends CrudRepository<T, ID> {
}
```

Repository cuối cùng mới ràng buộc các kiểu:

```java
import java.util.UUID;

public interface CustomerRepository
        extends BaseRepository<Customer, UUID> {
}
```

`@NoRepositoryBean` loại interface template khỏi việc được tạo instance repository trực tiếp; nó không xóa chức năng kế thừa của các repository cụ thể. Xem [NoRepositoryBean API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/NoRepositoryBean.html).

### 2.1. Điều annotation này không làm

Nó không:

- Tự chọn `Customer` thay cho `T` ở repository con.
- Tự suy ID từ tên field hoặc tên repository.
- Biến `Object` thành một entity đã mapping.
- Sửa một khai báo raw type.
- Làm một store hỗ trợ thêm mọi kiểu repository khác.

Nếu đặt `@NoRepositoryBean` lên chính repository cần inject, bean đó có thể không được tạo. Việc lỗi khởi tạo biến mất nhưng xuất hiện lỗi thiếu bean không phải là đã sửa metadata đúng.

## 3. Mất thông tin do raw type

### 3.1. Repository cuối cùng dùng raw CrudRepository

```java
// Ví dụ sai: thiếu domain và ID.
public interface BrokenCustomerRepository extends CrudRepository {
}
```

Java có thể cho biên dịch với cảnh báo raw type, nhưng chữ ký trên không còn nói repository quản lý Customer với UUID.

Cần khai báo đầy đủ:

```java
public interface CustomerRepository
        extends CrudRepository<Customer, UUID> {
}
```

Không dùng `@SuppressWarnings("rawtypes")` như một cách sửa repository. Annotation đó chỉ che cảnh báo compiler, không thêm lại metadata.

### 3.2. Repository con có tham số nhưng cầu nối ở giữa đã mất

Một lỗi khó nhìn hơn:

```java
@NoRepositoryBean
public interface BrokenBaseRepository<T, ID>
        extends CrudRepository {
}

public interface CustomerRepository
        extends BrokenBaseRepository<Customer, UUID> {
}
```

Nhìn ở repository cuối, Customer và UUID đều đã xuất hiện. Tuy nhiên, hai biến của `BrokenBaseRepository` không được truyền tiếp vào `CrudRepository`; nhánh đi tới `Repository` vẫn bị raw.

Cách sửa nằm ở interface trung gian:

```java
@NoRepositoryBean
public interface BaseRepository<T, ID>
        extends CrudRepository<T, ID> {
}
```

Không chỉ kiểm tra dòng `extends` cuối cùng. Phải đi qua mọi interface trung gian cho tới gốc `Repository`.

## 4. Repository cuối còn type variable chưa được ràng buộc

### 4.1. Chỉ cố định domain nhưng để ID mở

```java
@NoRepositoryBean
public interface CustomerTemplate<ID>
        extends CrudRepository<Customer, ID> {
}
```

Interface trên có thể là template hợp lệ. Nhưng một interface được scan để tạo bean như sau vẫn chưa chọn ID cụ thể:

```java
// Nếu được tạo bean trực tiếp, ID vẫn là biến kiểu.
public interface IncompleteCustomerRepository<ID>
        extends CustomerTemplate<ID> {
}
```

Cần một repository cụ thể:

```java
public interface CustomerRepository
        extends CustomerTemplate<UUID> {
}
```

Nếu `IncompleteCustomerRepository` cũng chỉ là tầng trung gian có chủ đích, đánh dấu nó bằng `@NoRepositoryBean` và tiếp tục tạo một interface cuối với ID rõ ràng.

### 4.2. Type bound không thay thế kiểu cụ thể của nghiệp vụ

Ví dụ `ID extends Serializable` chỉ đặt một giới hạn Java cho những loại ID được phép. Nó không xác định rằng ID của Customer là UUID hay Long.

Tương tự, `T extends BaseEntity` không tự chọn được subclass mà một repository cụ thể cần quản lý. Tùy cơ chế introspection và phiên bản, thông tin chưa được ràng buộc có thể được biểu diễn bằng bound, `Object`, thông tin chưa resolve hoặc một lỗi metadata. Không viết logic chẩn đoán chỉ dựa vào giả định rằng mọi trường hợp thiếu kiểu đều phải cho ra `null`.

### 4.3. Cố định ID ở tầng trung gian là hợp lệ

Một cấu trúc nhiều tầng đúng:

```java
@NoRepositoryBean
public interface BaseRepository<T, ID>
        extends CrudRepository<T, ID> {
}

@NoRepositoryBean
public interface UuidRepository<T>
        extends BaseRepository<T, UUID> {
}

public interface CustomerRepository
        extends UuidRepository<Customer> {
}
```

Có thể lần các phép thế:

```text
CustomerRepository
    -> UuidRepository<Customer>
    -> BaseRepository<Customer, UUID>
    -> CrudRepository<Customer, UUID>
    -> Repository<Customer, UUID>
```

Mỗi tầng giữ lại liên kết giữa biến kiểu của mình với tham số của interface cha. Cả hai interface template đều không được tạo bean trực tiếp.

## 5. Tham số đã resolve nhưng bị truyền nhầm vị trí

Không phải lỗi generic nào cũng là thiếu thông tin. Có những khai báo hoàn toàn xác định nhưng xác định sai.

Ví dụ base interface cố ý đặt ID trước domain:

```java
@NoRepositoryBean
public interface IdFirstRepository<ID, T>
        extends CrudRepository<T, ID> {
}
```

Cách dùng đúng:

```java
public interface CustomerRepository
        extends IdFirstRepository<UUID, Customer> {
}
```

Nếu viết nhầm:

```java
public interface BrokenCustomerRepository
        extends IdFirstRepository<Customer, UUID> {
}
```

thì phép thế dẫn tới:

```text
domain = UUID
ID     = Customer
```

Đây là metadata sai theo ý định nghiệp vụ, nhưng không nhất thiết là metadata không thể resolve. Store có thể tiếp tục báo rằng UUID không phải domain được quản lý, hoặc phát sinh một lỗi khác tùy module.

Khi kiểm tra, hãy ghi ra tên đầy đủ của hai lớp, không chỉ nhìn thấy “có hai class khác Object” rồi kết luận hợp lệ.

### 5.1. ID rõ ràng nhưng không khớp mapping

```java
public interface CustomerRepository
        extends CrudRepository<Customer, String> {
}
```

Nếu ID persistence của Customer được thiết kế là UUID, khai báo String cần được đối chiếu lại. Một số đường truy cập có conversion, nhưng conversion không thay cho việc xác định hợp đồng ID nhất quán.

Với ID tổng hợp, kiểu repository phải tương ứng với mô hình định danh của store, chẳng hạn một lớp khóa được ánh xạ phù hợp. Không mặc định ID luôn là Long chỉ vì một ví dụ CRUD khác dùng Long.

## 6. Kiểu của phương thức không thay kiểu gốc của repository

### 6.1. Generic ở cấp phương thức có phạm vi khác

Một interface bất kỳ có thể khai báo:

```java
public interface LookupService {

    <T, ID> Optional<T> lookup(ID id);
}
```

Các biến T và ID này thuộc từng lần gọi phương thức. Chúng không tự cung cấp metadata `Repository<Customer, UUID>` cho một repository raw hoặc chưa định nghĩa đúng.

Tương tự, một danh sách phương thức có tên `findById`, `save` hoặc `findAll` không tự thay thế mọi yêu cầu khai báo repository của Spring Data.

### 6.2. Projection không phải domain root mới

Ví dụ repository đúng có thể quản lý Customer và trả một view:

```java
public interface CustomerRepository
        extends CrudRepository<Customer, UUID> {

    List<CustomerNameView> findByActiveTrue();
}
```

`CustomerNameView` là kiểu kết quả của query. Root domain vẫn là Customer, ID vẫn là UUID.

Nếu đổi tham số đầu của `CrudRepository` thành một DTO chỉ để có response nhỏ, framework có thể resolve được DTO đó nhưng store không quản lý nó như entity. Đây thường là nhầm lẫn giữa kiểu miền và kiểu đọc dữ liệu, không phải lý do thêm annotation mapping ngẫu nhiên lên mọi DTO.

### 6.3. Executor bổ sung không tự cung cấp đủ metadata ID

`QueryByExampleExecutor<T>` hoặc `QuerydslPredicateExecutor<T>` diễn đạt một khả năng truy vấn và không có tham số ID như `Repository<T, ID>`.

Nếu muốn một repository CRUD kèm QBE, cấu trúc có thể là:

```java
public interface CustomerRepository
        extends CrudRepository<Customer, UUID>,
                QueryByExampleExecutor<Customer> {
}
```

Đoạn này dùng `QueryByExampleExecutor` từ `org.springframework.data.repository.query`. Store cụ thể vẫn phải hỗ trợ khả năng đó.

Không coi việc chỉ thêm một executor là đã tự khai báo đầy đủ một repository domain/ID theo mọi cơ chế discovery.

## 7. Khi không muốn kế thừa Repository: metadata tường minh

Spring Data có `@RepositoryDefinition` để chỉ định domain và ID cho interface không kế thừa các interface repository chuẩn.

```java
import org.springframework.data.repository.RepositoryDefinition;

import java.util.Optional;
import java.util.UUID;

@RepositoryDefinition(domainClass = Customer.class, idClass = UUID.class)
public interface ExplicitCustomerRepository {

    Optional<Customer> findById(UUID id);

    <S extends Customer> S save(S entity);
}
```

`domainClass` và `idClass` có vai trò tương ứng với T và ID của repository. Đây là một cách khai báo có chủ đích được mô tả trong [RepositoryDefinition API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/RepositoryDefinition.html), không phải annotation để che mọi chuỗi kế thừa generic sai.

Interface vẫn phải nằm trong phạm vi repository discovery thích hợp và được factory của store xử lý. Các phương thức được công bố phải có implementation hoặc ngữ nghĩa query phù hợp.

Các ví dụ trong bài là các phương án riêng; không cần tạo đồng thời mọi repository minh họa cùng quản lý Customer trong một ứng dụng.

## 8. Quan sát kiểu đã suy ra bằng API hỗ trợ

### 8.1. Dùng ResolvableType từ interface khai báo

```java
import org.springframework.core.ResolvableType;
import org.springframework.data.repository.Repository;

ResolvableType root = ResolvableType
        .forClass(CustomerRepository.class)
        .as(Repository.class);

Class<?> domain = root.getGeneric(0).resolve();
Class<?> id = root.getGeneric(1).resolve();

System.out.println("Repository type: " + root);
System.out.println("Domain: " + domain);
System.out.println("ID: " + id);
System.out.println("Unresolvable generics: "
        + root.hasUnresolvableGenerics());
```

Đối với ví dụ kế thừa đúng, kỳ vọng domain là Customer và ID là UUID. Kết quả này là một phép kiểm tra cấu trúc kiểu, chưa yêu cầu mở kết nối database.

`ResolvableType` cho phép đi qua generic và các supertype; xem [ResolvableType API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/ResolvableType.html).

Cần áp dụng cách trên đúng mục tiêu:

- Dùng interface repository cuối cùng cần được tạo bean.
- Không lấy một interface cha tùy ý rồi mong nó biết phép thế của mọi lớp con.
- Với phương án `@RepositoryDefinition` không kế thừa Repository, không kỳ vọng phép `.as(Repository.class)` tự biểu diễn metadata từ annotation.
- Một kiểu resolve được vẫn có thể là kiểu sai theo nghiệp vụ hoặc không được store quản lý.

### 8.2. Dùng metadata của Spring Data

```java
import org.springframework.data.repository.core.RepositoryMetadata;
import org.springframework.data.repository.core.support.AbstractRepositoryMetadata;

RepositoryMetadata metadata = AbstractRepositoryMetadata.getMetadata(
        CustomerRepository.class);

System.out.println(metadata.getRepositoryInterface().getName());
System.out.println(metadata.getDomainType().getName());
System.out.println(metadata.getIdType().getName());
```

Factory metadata này giúp quan sát thông tin repository theo cơ chế của Spring Data. Nó cũng có thể phát lỗi nếu khai báo không đáp ứng yêu cầu metadata. API [RepositoryMetadata](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/core/RepositoryMetadata.html) mô tả domain type, ID type và repository interface; [AbstractRepositoryMetadata](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/core/support/AbstractRepositoryMetadata.html) cung cấp phương thức tạo metadata tương ứng.

Không sửa framework để trả `Object.class` chỉ nhằm vượt qua lỗi. Factory của store còn phải dùng domain thực cho mapping, query và CRUD.

### 8.3. Không introspect tùy tiện lớp proxy runtime

Bean repository thường là proxy. `repository.getClass()` có thể là lớp proxy được tạo động, không phải interface nguồn mà người viết cần kiểm tra.

Lấy interface generic đầu tiên của lớp proxy bằng chỉ số cố định cũng dễ sai: proxy có thể triển khai nhiều interface phục vụ hạ tầng. Hãy bắt đầu từ interface repository được đăng ký hoặc metadata do hạ tầng cung cấp.

### 8.4. Một kiểm thử cấu trúc nhỏ

```java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CustomerRepositoryMetadataTest {

    @Test
    void declaresExpectedDomainAndId() {
        RepositoryMetadata metadata = AbstractRepositoryMetadata.getMetadata(
                CustomerRepository.class);

        assertEquals(Customer.class, metadata.getDomainType());
        assertEquals(UUID.class, metadata.getIdType());
    }
}
```

Đoạn test sử dụng cùng các import metadata và UUID ở ví dụ trước. Nó có ích khi dự án có nhiều tầng base repository hoặc thay đổi cách truyền generic. Nó không thay integration test khởi tạo repository thật của store.

## 9. Phân biệt với các lỗi ở tầng kế tiếp

Thông báo bọc ngoài có thể đều xuất hiện dưới dạng lỗi tạo bean. Cần tìm repository được nêu tên và nguyên nhân liên quan sâu hơn, thay vì kết luận từ mỗi chữ “BeanCreation”.

| Dấu hiệu | Câu hỏi cần kiểm tra trước |
| --- | --- |
| Không xác định được domain hoặc ID khi tạo metadata | Template bị scan, raw type, type variable chưa ràng buộc hoặc chuỗi truyền generic sai? |
| Domain bị suy ra thành Object, bound hoặc kiểu ngoài ý định | Thông tin mất ở tầng nào, có truyền nhầm vị trí không? |
| Metadata ra đúng Customer nhưng store không quản lý Customer | Mapping, entity scanning, import lớp và persistence unit có đúng không? |
| Metadata ra UUID làm domain | Có đảo tham số ở interface trung gian không? |
| Không tìm thấy bean repository | Interface có bị loại discovery, nằm ngoài scope hoặc gắn NoRepositoryBean nhầm không? |
| Không xác định được module sở hữu repository | Có nhiều store factory và thiếu cách phân biệt module không? |
| Không tìm thấy property trong tên query | Domain đã xác định nhưng tên thuộc tính hoặc đường dẫn query sai? |
| Lỗi kiểu ID khi gọi phương thức | Giá trị gọi, contract ID và conversion có tương thích không? |

Không cần sửa schema hoặc dữ liệu trong database để giải quyết một lỗi metadata xảy ra trước khi repository biết domain nào cần quản lý.

### 9.1. Import nhầm lớp có cùng tên

Một dự án có thể có Customer của domain, DTO Customer và một lớp được sinh trong package khác. Tất cả có thể hiển thị cùng tên ngắn trong IDE.

Ghi tên đầy đủ bằng `getName()` giúp xác nhận lớp nào thực sự được truyền. Nếu generic đã trỏ vào sai Customer, thêm entity scan cho package của Customer đúng không tự thay tham số đã khai báo sai.

### 9.2. Nhiều module không làm generic biến mất

Khi có nhiều repository factory, Spring Data có thể dùng chế độ cấu hình chặt hơn để xác định repository thuộc công nghệ lưu trữ nào. Một repository đã resolve đủ Customer và UUID vẫn có thể chưa được phân biệt rõ giữa các module.

Nếu repository chủ đích dùng JPA, một cấu trúc như `JpaRepository<Customer, UUID>` và phạm vi cấu hình phù hợp giúp thể hiện ý định module. Với store khác, dùng cơ chế tương ứng của module đó.

Đây là câu hỏi về binding với store, khác với việc T và ID còn chưa ràng buộc. Không đổi toàn bộ repository sang JPA chỉ để làm một lỗi discovery tạm biến mất khi ứng dụng thực tế dùng kho khác.

## 10. Đừng giải thích mọi lỗi bằng type erasure

Java có type erasure, nhưng nhiều thông tin generic trong khai báo class và interface vẫn được lưu dưới dạng metadata chữ ký để công cụ reflection và framework phân tích.

Vì vậy, framework có thể lần theo:

```text
CustomerRepository -> BaseRepository<Customer, UUID>
```

mà không cần tạo một Customer mẫu hoặc truy vấn database để đoán kiểu.

Điều khác biệt là giữa:

- Tham số kiểu có mặt trong chuỗi khai báo và có thể được thay thế rõ ràng.
- Thông tin đã bị bỏ bởi raw type hoặc chưa được ràng buộc ở interface mục tiêu.

Nếu source nhìn đúng nhưng artifact chạy cho metadata khác, lúc đó mới kiểm tra class thực được nạp, phiên bản dependency, bytecode được sinh hoặc công cụ đóng gói có bảo toàn thông tin cần thiết không. Không dùng giả thuyết này thay cho bước kiểm tra `extends CrudRepository<T, ID>` rất thường gặp.

Không mặc định reflection trên một object generic bất kỳ sẽ khôi phục được tất cả type argument của từng biến tại mọi điểm gọi. Hãy chọn đúng ngữ cảnh interface hoặc implementation có chữ ký cần phân tích.

## 11. Quy trình chẩn đoán theo thứ tự

1. Xác định chính xác repository interface mà hạ tầng đang tạo.
2. Xác định interface đó là template dùng chung hay repository cụ thể.
3. Nếu là template, kiểm tra `@NoRepositoryBean` đúng import và đúng vị trí.
4. Lần toàn bộ đường kế thừa đến `Repository<T, ID>`, tìm raw type và điểm mất liên kết.
5. Thay thế các biến kiểu bằng tay để biết domain và ID cuối cùng.
6. Kiểm tra kết quả bằng metadata hoặc ResolvableType khi cần.
7. So sánh tên lớp đầy đủ với domain và ID mà nghiệp vụ dự định dùng.
8. Khi generic đã đúng, mới chuyển sang mapping, module binding, query và cấu hình store.
9. Xác nhận repository cụ thể được tạo và thực hiện một thao tác có ý nghĩa trong integration test phù hợp.

Một bản ghi chẩn đoán hữu ích có thể gọn như:

```text
Repository gặp lỗi: CustomerRepository
Vai trò: repository cụ thể
Đường kế thừa: CustomerRepository -> UuidRepository -> BaseRepository
Domain mong muốn: Customer
ID mong muốn: UUID
Điểm mất kiểu: BaseRepository kế thừa raw CrudRepository
Sửa cấu trúc: truyền lại <T, ID> vào interface cha
Kiểm chứng tiếp: metadata đúng, sau đó khởi tạo store repository
```

Không cần nới kiểu thành Object, thêm annotation lên mọi lớp hoặc tắt discovery toàn bộ package để chữa triệu chứng. Một repository generic có cấu trúc đúng sẽ làm rõ interface nào chỉ là mẫu, interface nào là bean cụ thể và phép thế nào dẫn đến domain cùng ID mà store thực sự cần quản lý.
