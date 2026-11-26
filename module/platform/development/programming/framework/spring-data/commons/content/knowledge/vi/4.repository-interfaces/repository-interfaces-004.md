# Chỉ công khai các phương thức cần cho nghiệp vụ

Một repository interface vừa là điểm tích hợp với Spring Data vừa là tập thao tác mà mã gọi được phép sử dụng ở mức kiểu Java. Nếu kế thừa một interface có đầy đủ CRUD chỉ để dùng một phương thức đọc, repository cũng công khai nhiều thao tác ghi, xóa hoặc truy xuất toàn bộ dữ liệu mà nghiệp vụ hiện tại chưa cần.

Spring Data Commons cho phép chọn một hợp đồng nhỏ hơn: bắt đầu từ marker interface `Repository`, khai báo những phương thức cần thiết, hoặc định nghĩa base interface dùng chung có phạm vi rõ ràng. Mục tiêu là làm cho API thể hiện đúng nhu cầu, giảm thao tác vô tình được sử dụng và giúp thay đổi hợp đồng có chủ đích.

Bài học thuộc chương **Giao diện repository**, tập trung vào cách thu hẹp bề mặt phương thức mà vẫn sử dụng được hạ tầng repository của module Spring Data phù hợp. API hẹp là một công cụ thiết kế; quyền truy cập, giao dịch và ràng buộc dữ liệu vẫn cần được thực hiện ở các tầng chịu trách nhiệm tương ứng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao kế thừa một interface repository cũng là quyết định công khai một tập thao tác.
- Dùng `Repository<T, ID>` để chọn phương thức CRUD thay vì nhận toàn bộ CRUD.
- Phân biệt phương thức base repository, derived query và thao tác cần implementation riêng.
- Thiết kế base interface với `@NoRepositoryBean` mà không mở rộng quyền thao tác ngoài ý muốn.
- Lựa chọn kiểu trả về và ranh giới service theo nhu cầu đọc, ghi của nghiệp vụ.
- Nhận ra giới hạn của một repository được gọi là “chỉ đọc”.

## 2. Bắt đầu từ những gì mã gọi thực sự cần

Giả sử ứng dụng quản lý khách hàng có ba nơi dùng dữ liệu:

| Nơi sử dụng | Nhu cầu | Chưa cần |
| --- | --- | --- |
| Màn hình tra cứu | Tìm theo ID, tìm theo trạng thái có phân trang | Lưu, xóa và đọc mọi khách hàng không giới hạn |
| Tiến trình nhập khách hàng | Lưu khách hàng và đọc lại khi cần | Xóa toàn bộ dữ liệu |
| Nghiệp vụ tạm ngưng khách hàng | Kiểm tra trạng thái, ghi lý do và cập nhật theo quy tắc | Cho bên gọi tự sửa mọi thuộc tính qua một API ghi tổng quát |

Nếu tất cả nhận cùng một repository đầy đủ CRUD, chữ ký dependency không thể hiện được sự khác biệt này. Một lớp chỉ phục vụ tra cứu vẫn có thể gọi `deleteAll()` nếu kiểu repository được inject công khai phương thức đó.

Thay vì bắt đầu bằng câu hỏi “interface nào có nhiều phương thức tiện nhất?”, hãy lập danh sách thao tác cần cho từng bên dùng. Sau đó mới chọn interface và cách lắp ghép phù hợp.

Một API nhỏ có các lợi ích cụ thể:

- Người đọc nhận ra vai trò của dependency nhanh hơn.
- IDE chỉ gợi ý những thao tác nằm trong hợp đồng đã chọn.
- Việc thêm thao tác ghi hoặc xóa tạo thành thay đổi cần được xem xét.
- Mã gọi ít phụ thuộc vào những khả năng không dùng của store module.

API nhỏ vẫn cần đáp ứng đủ nghiệp vụ. Không nên giấu một phương thức hợp lệ rồi khiến service phải dựng lại một thao tác phức tạp, kém hiệu quả hoặc sai về cạnh tranh chỉ để giữ số phương thức thấp.

## 3. Kế thừa đồng nghĩa nhận các phương thức công khai

Xét khai báo:

```java
import java.util.UUID;

import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, UUID> {
}
```

Dù thân interface rỗng, hợp đồng không rỗng. Nó kế thừa các thao tác của `CrudRepository`, bao gồm lưu, đọc, đếm và xóa theo API tương ứng.

Đặt tên interface là `CustomerReadRepository` cũng không thay đổi các phương thức được kế thừa. Tương tự, viết chú thích “chỉ sử dụng để đọc” không ngăn mã gọi sử dụng phương thức ghi đã có trong kiểu Java.

Nếu kế thừa một interface đặc thù store như `JpaRepository`, tập phương thức còn có thể bao gồm các thao tác gắn với công nghệ đó, chẳng hạn flush hoặc thao tác batch tương ứng. Những phương thức này hữu ích khi có nhu cầu, nhưng cũng trở thành một phần dependency mà mã gọi nhìn thấy.

Trong Java, không thể loại bỏ một phương thức public được kế thừa bằng cách khai báo lại nó với mức truy cập hẹp hơn. Muốn không công khai phương thức đó trong hợp đồng, cần chọn lại quan hệ kế thừa hoặc đưa một interface khác ra cho bên sử dụng.

## 4. Dùng marker `Repository` để chọn phương thức

### 4.1. `Repository` định danh kiểu miền và kiểu ID

`Repository<T, ID>` là marker interface nền tảng. Nó không tự khai báo toàn bộ các phương thức CRUD.

Vì vậy, có thể bắt đầu từ `Repository` rồi khai báo đúng tập phương thức cần dùng:

```java
import java.util.Optional;
import java.util.UUID;

import org.springframework.data.repository.Repository;

public interface CustomerLookupRepository
        extends Repository<Customer, UUID> {

    Optional<Customer> findById(UUID id);
}
```

Trong ví dụ này:

- `Customer` là kiểu miền được module đang dùng mapping phù hợp.
- `UUID` là kiểu định danh của mô hình.
- Bên gọi nhìn thấy `findById` nhưng không nhận thêm `save` hoặc `deleteAll` từ `CrudRepository`.

Khi repository được module phù hợp phát hiện và tạo proxy, phương thức có chữ ký tương ứng với thao tác base repository được định tuyến tới implementation thích hợp. Đây là cơ chế chọn phương thức, không phải yêu cầu người dùng tự viết lại mọi thao tác CRUD.

Commons cung cấp hợp đồng chung; repository factory, mapping và khả năng thực thi vẫn thuộc module tích hợp store. Chỉ có marker interface trên classpath chưa tự tạo ra một kho dữ liệu.

### 4.2. Sao chép chữ ký có chủ đích

Nếu nghiệp vụ nhập khách hàng cần lưu và tìm theo ID:

```java
import java.util.Optional;
import java.util.UUID;

import org.springframework.data.repository.Repository;

public interface CustomerImportRepository
        extends Repository<Customer, UUID> {

    <S extends Customer> S save(S customer);

    Optional<Customer> findById(UUID id);
}
```

Chữ ký generic của `save` thể hiện hình dạng hợp đồng CRUD tương ứng. Khi chọn phương thức, nên đối chiếu chữ ký của interface Commons đang sử dụng, gồm generic, tham số và kiểu trả về.

Không cần sao chép mọi phương thức để “phòng khi dùng đến”. Nếu sau này thật sự cần `saveAll`, hãy thêm cùng với nhu cầu, cách xử lý lỗi và phạm vi thao tác được xác định rõ.

Với thao tác lưu, mã gọi nên sử dụng giá trị trả về theo hợp đồng:

```java
Customer persisted = importRepository.save(customer);
```

Việc chỉ công khai một phương thức `save` không làm cho insert, update, merge hay nhận diện thực thể mới giống nhau trên mọi store. Nó thu hẹp API ở mức thao tác, còn semantics lưu cụ thể vẫn cần xem theo module.

### 4.3. Không đổi tên CRUD rồi mặc định được định tuyến như cũ

Khai báo một phương thức có tên nghiệp vụ như:

```java
Customer register(Customer customer);
```

không tự biến nó thành bí danh của `save`. Nếu phương thức nằm trong repository, Spring Data phải có cách xác định implementation hoặc truy vấn tương ứng. Nếu không có cơ chế phù hợp, việc tạo hoặc gọi repository có thể thất bại.

Muốn có thao tác `register`, có thể:

- Viết service nghiệp vụ gọi repository đã chọn.
- Cung cấp repository fragment và implementation theo cơ chế module hỗ trợ.
- Sử dụng cách khai báo truy vấn hoặc implementation thích hợp nếu thao tác thực sự thuộc tầng repository.

Tên mang ý nghĩa nghiệp vụ có giá trị khi đi cùng hành vi được triển khai rõ ràng.

## 5. Kết hợp phương thức base với derived query cần thiết

Giả sử mô hình `Customer` có các thuộc tính `id`, `name`, `status`; `CustomerStatus` biểu diễn trạng thái. Màn hình tra cứu cần ID và tên:

```java
import java.util.UUID;

public interface CustomerSummary {
    UUID getId();
    String getName();
}
```

Repository có thể khai báo:

```java
import java.util.Optional;
import java.util.UUID;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.Repository;

public interface CustomerLookupRepository
        extends Repository<Customer, UUID> {

    Optional<Customer> findById(UUID id);

    Page<CustomerSummary> findByStatus(
            CustomerStatus status,
            Pageable pageable);
}
```

Ví dụ giả định module hỗ trợ derived query, kiểu projection và phân trang tương ứng. Interface lúc này có hai loại phương thức:

| Phương thức | Cách xác định hành vi |
| --- | --- |
| `findById` | Chữ ký base repository tương ứng, dùng metadata định danh |
| `findByStatus` | Derived query theo thuộc tính miền, với kiểu trả về được module hỗ trợ |

`findById` là một tên phương thức dành cho thao tác định danh của repository. Không nên suy ra nó luôn truy vấn một thuộc tính thông thường chỉ vì thuộc tính đó có tên `id`; metadata ID mới là căn cứ của thao tác định danh.

`findByStatus` dựa vào quy ước truy vấn và mô hình miền. Nó không trở thành hợp lệ chỉ vì phương thức có thể biên dịch về mặt Java. Module phải nhận diện thuộc tính, toán tử và kiểu trả về tương ứng.

### 5.1. Phân trang giúp định hình truy cập nhưng cần quy tắc đầu vào

Chọn `Pageable` thay vì công khai `findAll()` không có tham số giúp diễn đạt nhu cầu đọc theo trang. Tuy nhiên, `Pageable` có thể biểu diễn cả yêu cầu không phân trang trong các trường hợp API hỗ trợ.

Nếu nghiệp vụ yêu cầu bắt buộc phân trang, service hoặc ranh giới API phải kiểm tra yêu cầu, giới hạn kích thước và các trường được phép sắp xếp. Không suy ra mọi lời gọi sẽ bị giới hạn chỉ vì chữ ký có `Pageable`.

Ngoài ra, `Page` cung cấp thông tin tổng số. Nếu giao diện chỉ cần biết còn dữ liệu tiếp theo hay không, có thể cân nhắc `Slice` khi module hỗ trợ và hợp đồng nghiệp vụ phù hợp.

### 5.2. Projection thu hẹp dữ liệu trả về, không cấp quyền truy cập

`CustomerSummary` giúp nơi gọi chỉ làm việc với ID và tên theo hình dạng đã chọn. Nó cũng tránh đưa toàn bộ mô hình persistence vào một màn hình chỉ cần ít dữ liệu.

Nhưng projection không tự quyết định người dùng được xem khách hàng nào. Điều kiện phạm vi dữ liệu và quyền truy cập vẫn cần được thực hiện. Khả năng tối ưu lượng dữ liệu thực sự đọc cũng phụ thuộc projection, truy vấn và module.

## 6. Base interface dùng chung cần nhỏ và ổn định

Nếu nhiều repository chỉ cần tra cứu theo ID, có thể định nghĩa một base interface:

```java
import java.util.Optional;

import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.repository.Repository;

@NoRepositoryBean
public interface LookupRepository<T, ID> extends Repository<T, ID> {
    Optional<T> findById(ID id);
}
```

Repository cụ thể kế thừa nó:

```java
import java.util.UUID;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public interface CustomerLookupRepository
        extends LookupRepository<Customer, UUID> {

    Page<CustomerSummary> findByStatus(
            CustomerStatus status,
            Pageable pageable);
}
```

`@NoRepositoryBean` cho biết interface trung gian không phải đích để tạo repository bean trực tiếp. Các repository cụ thể mới gắn kiểu miền và ID cần thiết cho từng trường hợp.

Base interface là nơi có ảnh hưởng rộng. Thêm `deleteAll` vào một base chung có thể công khai xóa toàn bộ ở mọi repository con, kể cả những nơi chỉ phục vụ tra cứu.

Trước khi thêm một phương thức vào base, cần trả lời:

1. Tất cả repository con có thật sự cần nó không?
2. Nó có cùng ý nghĩa ở mọi miền sử dụng không?
3. Các module store liên quan có hỗ trợ hợp đồng đó không?
4. Việc mở rộng API có làm sai vai trò của một nhóm repository hiện có không?

Không cần có một base khổng lồ chứa mọi tiện ích của hệ thống. Có thể giữ một base đọc nhỏ, còn thao tác ghi hoặc truy vấn đặc thù nằm ở repository phù hợp.

## 7. Dùng `@RepositoryDefinition` khi cần một cách khai báo khác

Spring Data cũng có annotation định nghĩa domain và ID mà không yêu cầu interface kế thừa trực tiếp marker `Repository`:

```java
import java.util.Optional;
import java.util.UUID;

import org.springframework.data.repository.RepositoryDefinition;

@RepositoryDefinition(domainClass = Customer.class, idClass = UUID.class)
public interface CustomerQueries {
    Optional<Customer> findById(UUID id);
}
```

Cách này có thể hữu ích khi muốn giữ quan hệ kế thừa của interface theo thiết kế riêng. Các phương thức vẫn cần được repository factory diễn giải theo cơ chế tương ứng.

Đây là một lựa chọn khai báo, không phải cách tạo quyền truy cập khác với repository thông thường. Nó cũng không tự cung cấp implementation cho mọi phương thức tùy ý trong interface.

Trong một nhóm phát triển, nên chọn cách khai báo nhất quán và có lý do. Kế thừa marker thường thể hiện domain và ID trực tiếp qua generic; annotation thể hiện chúng qua metadata.

## 8. Phân biệt API đọc hẹp với tính chỉ đọc thực tế

Cụm từ “repository chỉ đọc” có thể chỉ nhiều điều khác nhau:

| Mức | Ý nghĩa | Cơ chế cần xem |
| --- | --- | --- |
| API Java | Interface không công khai phương thức ghi | Quan hệ kế thừa và các phương thức khai báo |
| Dữ liệu trả về | Bên gọi không nhận đối tượng có thể dễ dàng sửa trạng thái persistence | DTO, projection, mô hình bất biến và cách mapping |
| Giao dịch | Thao tác tham gia ranh giới giao dịch được cấu hình cho việc đọc | Module, transaction manager và thuộc tính giao dịch |
| Quyền runtime | Chủ thể không được phép thực hiện thao tác ghi | Phân quyền ứng dụng và quyền của tài khoản truy cập dữ liệu |
| Bất biến nghiệp vụ | Không có đường ghi nào làm sai quy tắc miền | Service, ràng buộc dữ liệu và kiểm soát cạnh tranh |

### 8.1. Không có `save` chưa chắc không có thay đổi dữ liệu

Nếu phương thức trả về một entity được quản lý trong persistence context của JPA, sửa entity trong một giao dịch phù hợp có thể được ghi thông qua dirty checking mà không có lời gọi `save` trực tiếp ở lớp đó.

Đây là hành vi của công nghệ tích hợp, không phải đặc tính chung của mọi store. Nó cho thấy vì sao chỉ đếm phương thức ghi trên interface chưa đủ để kết luận một luồng thực thi không thể thay đổi dữ liệu.

Nếu màn hình chỉ cần dữ liệu hiển thị, DTO hoặc projection phù hợp có thể giúp ranh giới rõ hơn. Cần đánh giá cụ thể kiểu trả về thay vì chỉ đổi tên repository.

### 8.2. `readOnly = true` không phải một quyền cấm ghi phổ quát

Trong những công nghệ có hỗ trợ, thuộc tính giao dịch read-only có thể ảnh hưởng tối ưu hoặc cách quản lý giao dịch. Nó không phải một bảo đảm chung rằng mọi lệnh ghi sẽ bị từ chối trên mọi store, driver và cấu hình.

Nếu yêu cầu thật sự là không cho ghi, phải chọn cơ chế thực thi tương ứng, chẳng hạn phân quyền ở ứng dụng hoặc quyền tài khoản dữ liệu phù hợp. Repository hẹp đóng góp vào thiết kế nhưng không thay thế những cơ chế đó.

### 8.3. Không kế thừa CRUD vẫn có thể khai báo thao tác ghi

Một interface chỉ kế thừa `Repository` vẫn có thể khai báo derived delete hoặc một truy vấn cập nhật nếu module hỗ trợ. Marker không phân loại interface thành “chỉ đọc”.

Muốn đánh giá API, hãy đọc cả phương thức được khai báo, phương thức kế thừa, fragment và default method. Một tên interface hoặc một annotation không tự mô tả đầy đủ các đường ghi.

## 9. Đưa thao tác nghiệp vụ vào ranh giới phù hợp

### 9.1. `save` là thao tác persistence tổng quát

Một service gọi `save(customer)` có thể ghi nhiều trạng thái khác nhau tùy đối tượng đưa vào. Nếu nghiệp vụ chỉ cho phép “tạm ngưng khách hàng với lý do”, đưa `save` trực tiếp tới mọi bên gọi có thể làm hợp đồng rộng hơn nhu cầu.

Có thể công bố một interface ứng dụng:

```java
import java.util.UUID;

public interface CustomerSuspension {
    void suspend(UUID customerId, String reason);
}
```

Interface này không kế thừa `Repository` và không phải yêu cầu Spring Data tự suy diễn thao tác `suspend`. Một service implementation phải thực hiện quy tắc:

```text
Nhận yêu cầu tạm ngưng
    -> xác thực đầu vào và chủ thể
    -> đọc khách hàng trong phạm vi được phép
    -> kiểm tra trạng thái hiện tại
    -> áp dụng quy tắc chuyển trạng thái và lý do
    -> lưu bằng repository nội bộ
    -> trả kết quả theo hợp đồng ứng dụng
```

Ranh giới giao dịch và cách xử lý cập nhật cạnh tranh cần được chọn theo store và nghiệp vụ. Chỉ đổi một phương thức thành tên nghiệp vụ không tự tạo tính nguyên tử.

### 9.2. Repository fragment dành cho hành vi persistence cần mở rộng

Nếu cần thao tác cập nhật đặc thù ở tầng persistence, có thể dùng fragment và implementation phù hợp. Ví dụ, một cập nhật có điều kiện phiên bản hoặc một truy vấn chuyên biệt có thể cần API store mà derived query không biểu đạt được.

Hãy phân biệt:

- Service điều phối quy tắc và nhiều thao tác nghiệp vụ.
- Repository fragment triển khai hành vi truy cập dữ liệu được mở rộng.
- Derived query diễn đạt truy vấn theo quy ước mà module hỗ trợ.

Chọn đúng nơi giúp interface rõ nghĩa hơn. Không gom toàn bộ workflow, gửi thông báo và gọi hệ thống ngoài vào một repository chỉ để bên gọi có một phương thức duy nhất.

## 10. Chỉ đưa một góc nhìn hẹp ra cho bên đọc

Có trường hợp một repository nội bộ phải có cả đọc và ghi, nhưng một nhóm bên gọi chỉ cần đọc. Có thể định nghĩa một interface trung gian không tạo bean riêng:

```java
import java.util.Optional;
import java.util.UUID;

import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.repository.Repository;

@NoRepositoryBean
public interface CustomerReadOperations
        extends Repository<Customer, UUID> {

    Optional<Customer> findById(UUID id);
}
```

Repository cụ thể bổ sung thao tác ghi:

```java
public interface CustomerPersistenceRepository
        extends CustomerReadOperations {

    <S extends Customer> S save(S customer);
}
```

Một thành phần chỉ đọc phụ thuộc `CustomerReadOperations`; một thành phần thực sự cần ghi có thể phụ thuộc `CustomerPersistenceRepository`.

Cách này thu hẹp những gì bên đọc nhìn thấy ở mức kiểu Java, trong khi bean cụ thể vẫn có khả năng ghi. Nó phù hợp khi giới hạn API cho từng nơi dùng là mục tiêu thiết kế.

Cần xác định phạm vi repository scanning và bean injection rõ ràng. `@NoRepositoryBean` ở interface trung gian tránh yêu cầu tạo bean trực tiếp cho nó. Nếu có nhiều bean phù hợp cùng kiểu đọc, phải giải quyết việc lựa chọn bean theo cấu hình ứng dụng.

Bên đọc vẫn không nên tìm cách ép kiểu sang repository rộng hơn để gọi ghi. Nếu nghiệp vụ cần thao tác mới, hãy sửa hợp đồng hoặc đi qua service thích hợp thay vì vòng qua ranh giới đã chọn.

## 11. Phạm vi dữ liệu cũng là một phần của hợp đồng

Thu hẹp danh sách phương thức mới chỉ trả lời “được làm thao tác nào”. Nghiệp vụ còn cần trả lời “được làm trên dữ liệu nào”.

Ví dụ, hệ thống có nhiều tổ chức. Một phương thức `findById` không mang tham số tổ chức trong chữ ký. Nếu yêu cầu là chỉ tra cứu trong tổ chức hiện tại, có thể cần một truy vấn có phạm vi hoặc service thực hiện điều kiện tương ứng.

Giả sử mô hình có thêm thuộc tính `organizationId`, một khai báo có thể là:

```java
Optional<CustomerSummary> findByOrganizationIdAndId(
        UUID organizationId,
        UUID id);
```

Module phải hỗ trợ derived query và projection tương ứng. Ngoài ra, ứng dụng cần quyết định nguồn `organizationId` tin cậy. Nhận một UUID tổ chức từ request mà không kiểm tra không tự thực hiện phân quyền.

Điều này cũng áp dụng cho trạng thái soft-delete, quyền sở hữu hoặc dữ liệu đã lưu trữ. Một phương thức càng sát phạm vi sử dụng càng dễ đọc, nhưng ràng buộc runtime phải được thực hiện đầy đủ.

## 12. Các cách thu hẹp dễ gây hiểu nhầm

### 12.1. Kế thừa CRUD rồi ghi đè để ném exception

Một default method ném `UnsupportedOperationException` cho `deleteAll` không xóa phương thức khỏi API. Mã gọi vẫn nhìn thấy nó và chỉ thất bại lúc thực thi.

Ngoài ra, những đường xóa hoặc ghi khác vẫn có thể còn được kế thừa. Nếu mục tiêu là không công khai CRUD rộng, chọn lại interface thường thể hiện ý định rõ hơn.

### 12.2. Ẩn phương thức HTTP rồi coi như không còn phương thức Java

Khi ứng dụng dùng cơ chế đưa repository ra HTTP, cấu hình không export một phương thức có thể thay đổi HTTP API. Nó không loại bỏ phương thức đó khỏi interface Java của repository.

Ngược lại, interface hẹp cũng chưa thay thế xác thực, phân quyền và cấu hình HTTP. Cần đánh giá từng ranh giới theo nơi thực sự sử dụng nó.

### 12.3. Chỉ dựa vào package hoặc tên interface

Package và tên tốt giúp định hướng người bảo trì. Nhưng một interface public đã kế thừa `deleteAll` vẫn công khai phương thức đó với mã có thể truy cập kiểu.

Nếu cần kiểm soát dependency giữa các module ứng dụng, hãy dùng cấu trúc module, phạm vi truy cập và ranh giới service phù hợp. Đừng đặt toàn bộ trách nhiệm này lên tên repository.

### 12.4. Tạo quá nhiều interface không có khác biệt thực tế

Không cần tạo một interface cho từng lời gọi nếu tất cả có cùng nhóm người dùng và cùng hợp đồng ổn định. Sự phân tách có giá trị khi phản ánh vai trò, phạm vi hoặc trách nhiệm khác nhau.

Nếu một thành phần thật sự cần toàn bộ CRUD và điều đó phù hợp thiết kế, kế thừa interface CRUD là lựa chọn hợp lệ. Nguyên tắc là công khai đủ cho nhu cầu đã xác định.

## 13. Quy trình thu hẹp một repository đang tồn tại

### Bước 1: Lập bảng nơi dùng và thao tác

Ghi những thành phần đang gọi repository, phương thức thực sự được gọi và nhu cầu nghiệp vụ tương ứng. Phân biệt đọc phục vụ màn hình, ghi nghiệp vụ và thao tác quản trị dữ liệu.

### Bước 2: Chọn ranh giới

Có thể chọn một trong các cách:

| Nhu cầu | Cách phù hợp để cân nhắc |
| --- | --- |
| Chỉ cần vài phương thức repository chuẩn | Kế thừa `Repository` và khai báo chọn lọc |
| Nhiều repository cùng có nhu cầu đọc nhỏ | Base interface với `@NoRepositoryBean` |
| Một bean persistence rộng nhưng nhiều loại bên dùng | Interface đọc hẹp cho bên chỉ đọc |
| Thao tác có quy tắc chuyển trạng thái | Service hoặc application interface theo nghiệp vụ |
| Truy cập dữ liệu đặc thù không có sẵn | Repository fragment và implementation |
| Thực sự cần đầy đủ CRUD | Giữ interface CRUD phù hợp |

### Bước 3: Giữ đúng các chữ ký cần định tuyến

Đối chiếu phương thức chuẩn với API của Commons đang dùng. Với derived query, kiểm tra thuộc tính miền, toán tử và kiểu trả về. Với phương thức custom, cung cấp implementation hoặc cơ chế truy vấn tương ứng.

### Bước 4: Đổi dependency của nơi dùng

Một lớp chỉ cần đọc nên nhận kiểu đọc. Một controller có thao tác nghiệp vụ nên nhận service thích hợp thay vì repository ghi tổng quát khi nghiệp vụ yêu cầu điều phối.

Các lỗi biên dịch xuất hiện sau khi thu hẹp giúp chỉ ra nơi còn phụ thuộc thao tác bị bỏ. Cần xem lại nhu cầu ở đó; không tự động thêm toàn bộ CRUD trở lại để hết lỗi.

### Bước 5: Kiểm tra hành vi có ý nghĩa

Xác nhận module vẫn tạo được repository; các phương thức chuẩn được định tuyến; derived query và projection chạy đúng trên store; service vẫn giữ quy tắc và ranh giới giao dịch cần thiết.

Với phạm vi dữ liệu, cần có trường hợp không tìm thấy hoặc dữ liệu ngoài phạm vi. Với thao tác ghi có điều kiện, cần kiểm tra trạng thái không hợp lệ hoặc xung đột nếu nghiệp vụ yêu cầu.

Kiểm tra chỉ nhìn cấu trúc interface không chứng minh truy vấn và mapping hoạt động. Ngược lại, kiểm tra trên store không thay thế việc đánh giá tập phương thức mà bên gọi được nhìn thấy.

## 14. Tình huống thực hành

Ban đầu ứng dụng có một `CustomerRepository extends CrudRepository<Customer, UUID>` được dùng trực tiếp ở màn hình tra cứu, tiến trình nhập và service tạm ngưng khách hàng.

Phân tích thiết kế mới:

| Thành phần | Hợp đồng nên nhận | Lý do |
| --- | --- | --- |
| Màn hình tra cứu | Interface đọc, hoặc service tra cứu trả DTO | Chỉ cần truy vấn trong phạm vi và phân trang |
| Tiến trình nhập | Repository hoặc adapter có thao tác lưu cần thiết | Công khai đúng khả năng nhập dữ liệu |
| Nơi gọi tạm ngưng | `CustomerSuspension` | Yêu cầu là chuyển trạng thái có quy tắc, không phải ghi thực thể tùy ý |
| Implementation của service tạm ngưng | Repository nội bộ có đọc và ghi thích hợp | Có đủ khả năng thực hiện nghiệp vụ và kiểm soát cạnh tranh |

Có thể dùng một repository nội bộ và các ranh giới hẹp phía trên, hoặc tách repository theo cấu hình module nếu thật sự phù hợp. Không cần mặc định mỗi vai trò tạo một repository bean độc lập cho cùng domain.

Điều cần đánh giá là bên gọi được công khai khả năng nào, bean nào thực thi thao tác và các quy tắc được bảo đảm ở đâu. Số lượng interface không phải thước đo duy nhất của chất lượng thiết kế.

## 15. Câu hỏi tự kiểm tra

### Câu 1

Một interface tên `ReadOnlyCustomerRepository` kế thừa `CrudRepository`. Bên gọi có nhìn thấy `deleteAll` không?

**Gợi ý trả lời:** Có. Tên interface không thay đổi hợp đồng được kế thừa. Muốn không công khai phương thức đó, cần thay quan hệ kế thừa hoặc đưa ra một kiểu hẹp hơn.

### Câu 2

Chỉ khai báo `Optional<Customer> findById(UUID id)` trên interface kế thừa `Repository` có đồng nghĩa phải tự viết implementation không?

**Gợi ý trả lời:** Không nhất thiết. Phương thức có chữ ký base repository tương ứng có thể được định tuyến tới implementation của module khi repository được cấu hình hợp lệ. Commons một mình chưa cung cấp store để thực thi.

### Câu 3

Thêm `Customer register(Customer customer)` vào interface có tự tạo bí danh cho `save` không?

**Gợi ý trả lời:** Không. Cần cơ chế truy vấn hoặc implementation phù hợp. Nếu `register` là workflow nghiệp vụ, service thường là ranh giới cần xem xét.

### Câu 4

Tại sao không nên thêm `deleteAll` vào base interface chỉ vì một repository con cần nó?

**Gợi ý trả lời:** Phương thức sẽ được công khai qua mọi repository kế thừa base. Hãy đặt nó ở hợp đồng thật sự cần thao tác đó hoặc một ranh giới quản trị phù hợp.

### Câu 5

Một repository không có `save` trả về entity JPA. Có đủ căn cứ kết luận service không thể làm thay đổi dữ liệu không?

**Gợi ý trả lời:** Chưa đủ. Entity có thể được quản lý và thay đổi có thể được ghi qua dirty checking trong ngữ cảnh phù hợp. Cần xem kiểu trả về, ranh giới giao dịch và cơ chế thực thi.

### Câu 6

Một phương thức nhận `Pageable` có tự ngăn mọi lần đọc không giới hạn không?

**Gợi ý trả lời:** Không. Phải xác định có cho phép unpaged hay không và kiểm tra kích thước trang ở ranh giới phù hợp. Khả năng phân trang còn phụ thuộc module và truy vấn.

### Câu 7

Đánh dấu một phương thức không export qua HTTP có làm mất phương thức đó khỏi repository Java không?

**Gợi ý trả lời:** Không. HTTP export và tập phương thức Java là hai ranh giới khác nhau. Phải thiết kế và kiểm soát từng ranh giới theo nhu cầu sử dụng.