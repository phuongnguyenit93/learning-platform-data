# Giao diện đặc thù store như JpaRepository hoặc MongoRepository

Spring Data Commons cung cấp các hợp đồng chung như `Repository`, các thao tác CRUD, phân trang, sắp xếp và mô hình hỗ trợ truy vấn. Khi làm việc với một công nghệ lưu trữ cụ thể, ứng dụng thường sử dụng interface do module tích hợp cung cấp, chẳng hạn `JpaRepository` của Spring Data JPA hoặc `MongoRepository` của Spring Data MongoDB.

Những interface này vừa tái sử dụng các abstraction chung vừa thể hiện khả năng và semantics của store. Cùng nhìn thấy một phương thức `save` không có nghĩa hai repository dùng cùng vòng đời đối tượng, cùng cách cập nhật hay cùng cơ chế giao dịch.

Bài học thuộc chương **Giao diện repository**, tập trung vào cách chọn interface theo công nghệ, đọc đúng các khả năng đặc thù và giữ ranh giới rõ ràng giữa phần nghiệp vụ với phần tích hợp dữ liệu.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt interface trong Commons với interface của module store.
- Giải thích vai trò của `JpaRepository` và `MongoRepository`.
- Nhận ra khác biệt giữa lưu entity JPA, lưu document MongoDB, flush và insert.
- Chọn mapping, kiểu ID và annotation theo module đang sử dụng.
- Biết khi nào nên sử dụng trực tiếp interface đặc thù, khi nào nên đưa một hợp đồng hẹp hơn ra cho bên gọi.
- Tổ chức repository khi ứng dụng dùng nhiều store và xác định phần cần kiểm tra tích hợp.

## 2. Interface chung và interface đặc thù nằm ở đâu?

| Nhóm | Vai trò | Ví dụ |
| --- | --- | --- |
| Định danh repository | Mô tả kiểu miền và kiểu ID để hạ tầng repository xử lý | `Repository<T, ID>` |
| Hợp đồng thao tác chung | Diễn đạt lưu, đọc, xóa, phân trang hoặc sắp xếp | Các interface CRUD và sorting của Commons |
| Hợp đồng truy vấn bổ sung | Cung cấp một cách biểu đạt hoặc thực thi truy vấn khi module hỗ trợ | Query by Example, Querydsl executor tương ứng |
| Interface của store | Kết hợp API chung với khả năng theo công nghệ | `JpaRepository`, `MongoRepository` |
| Interface của ứng dụng | Diễn đạt nhu cầu sử dụng dữ liệu của nghiệp vụ | `CustomerLookup`, `CustomerRegistration` |

Interface đặc thù được repository factory của module tương ứng xử lý. Implementation phía sau có thể dùng `EntityManager`, thao tác MongoDB hoặc hạ tầng khác của module.

```text
Interface repository của ứng dụng
        |
        +-- JpaRepository
        |       -> repository factory của JPA
        |       -> EntityManager / JPA provider
        |       -> cơ sở dữ liệu quan hệ
        |
        +-- MongoRepository
                -> repository factory của MongoDB
                -> thao tác và driver MongoDB
                -> MongoDB
```

Sơ đồ biểu diễn hai lựa chọn, không phải một repository đồng thời kế thừa cả hai. Một interface ghép mọi store không tự tạo được một implementation có semantics thống nhất.

Quan hệ kế thừa chi tiết, kiểu trả về và phương thức bổ sung có thể thay đổi theo dòng phiên bản. Khi cần dùng một phương thức cụ thể, hãy đối chiếu API của bộ dependency thực tế, thay vì dựa vào sơ đồ kế thừa của một phiên bản khác.

## 3. `JpaRepository`: repository gắn với mô hình JPA

`JpaRepository<T, ID>` thuộc package `org.springframework.data.jpa.repository`. Nó dành cho thực thể được mapping theo JPA và cần hạ tầng JPA phù hợp.

Các khái niệm quan trọng phía sau repository gồm:

- Entity và metadata mapping quan hệ.
- `EntityManager` và persistence context.
- Trạng thái thực thể, chẳng hạn đang được quản lý hoặc detached.
- Cơ chế persist, merge, dirty checking và flush.
- Giao dịch và các ràng buộc của cơ sở dữ liệu quan hệ.

Không phải tất cả những khái niệm này được định nghĩa bởi Commons. Chúng giải thích vì sao interface JPA có những phương thức hoặc hành vi không có ý nghĩa tương đương trên một document store.

### 3.1. Ví dụ mô hình JPA

Các ví dụ tiếp theo dùng chung enum nghiệp vụ:

```java
package example.customer.model;

public enum CustomerStatus {
    ACTIVE,
    SUSPENDED
}
```

Ví dụ JPA sử dụng namespace Jakarta Persistence, phù hợp với một bộ thư viện hỗ trợ namespace đó. Mỗi kiểu public đặt trong file riêng.

```java
package example.customer.jpa;

import java.util.Objects;

import example.customer.model.CustomerStatus;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Enumerated;
import jakarta.persistence.EnumType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "customers")
public class JpaCustomer {
    @Id
    @GeneratedValue
    private Long id;

    @Version
    private Long version;

    @Column(nullable = false)
    private String email;

    @Enumerated(EnumType.STRING)
    private CustomerStatus status;

    protected JpaCustomer() {
    }

    public JpaCustomer(String email) {
        this.email = Objects.requireNonNull(email, "email");
        this.status = CustomerStatus.ACTIVE;
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getEmail() {
        return email;
    }

    public CustomerStatus getStatus() {
        return status;
    }

    public void changeEmail(String email) {
        this.email = Objects.requireNonNull(email, "email");
    }
}
```

`@GeneratedValue` trong ví dụ để provider lựa chọn chiến lược theo cấu hình mặc định tương ứng. Trong dự án thực, chiến lược ID, schema và migration cần được quyết định phù hợp với hệ quản trị. Đoạn mapping này không tự cung cấp datasource hoặc khởi tạo cơ sở dữ liệu.

Repository có thể khai báo:

```java
package example.customer.jpa;

import java.util.Optional;

import example.customer.model.CustomerStatus;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface JpaCustomerRepository
        extends JpaRepository<JpaCustomer, Long> {

    Optional<JpaCustomer> findByEmail(String email);

    Page<JpaCustomer> findByStatus(
            CustomerStatus status,
            Pageable pageable);
}
```

Generic `Long` phù hợp ID trong mô hình mẫu. JPA không bị giới hạn ở `Long`; kiểu ID phải phù hợp mapping thực tế.

`Optional` diễn đạt kỳ vọng truy vấn đơn kết quả hoặc không có kết quả. Nó không tự tạo unique constraint cho email. Nếu nghiệp vụ yêu cầu email duy nhất, cần thiết kế và triển khai ràng buộc riêng.

### 3.2. `save` liên quan đến persist hoặc merge

Trong implementation JPA thông thường của Spring Data, `save` lựa chọn persist hoặc merge dựa vào việc xác định thực thể mới. Cách xác định có thể sử dụng metadata phiên bản, ID hoặc cơ chế được cấu hình phù hợp.

Không nên mô tả `save` đơn giản thành “cứ có ID là chạy SQL update”. Trạng thái entity, metadata và hành vi JPA provider đều có vai trò.

Với entity detached, merge có thể trả về một instance được quản lý khác với instance đầu vào. Vì thế, cách dùng cần giữ đúng hợp đồng:

```java
JpaCustomer persisted = repository.save(customer);
```

Việc dùng giá trị trả về cũng là thói quen phù hợp với hợp đồng lưu chung, kể cả khi một trường hợp cụ thể có thể cập nhật trực tiếp instance đầu vào.

### 3.3. Dirty checking không phải khả năng chung của mọi repository

Nếu entity đang được quản lý trong persistence context và ranh giới giao dịch phù hợp, thay đổi thuộc tính có thể được ghi qua dirty checking. Không phải mọi thay đổi đều cần một lời gọi `save` trực tiếp để JPA nhận biết.

Điều này không có nghĩa cứ gọi setter ở bất kỳ đâu cũng ghi xuống cơ sở dữ liệu. Phải xem entity còn được quản lý không, giao dịch đang diễn ra thế nào và khi nào có flush.

Cũng không thể mang giả định này sang `MongoRepository`. Hai store có vòng đời đối tượng khác nhau.

## 4. Flush, commit và thao tác batch của JPA

### 4.1. `flush` đồng bộ thay đổi, không tự là commit

Các phương thức như `flush` hoặc `saveAndFlush` gắn với cơ chế JPA. Về ý tưởng:

```java
JpaCustomer persisted = repository.saveAndFlush(customer);
```

Lời gọi yêu cầu lưu thực thể rồi flush các thay đổi liên quan trong ngữ cảnh persistence. Việc flush không có nghĩa giao dịch đã commit.

```text
Thay đổi trạng thái entity
        -> flush: đồng bộ thay đổi theo cơ chế JPA
        -> commit: hoàn tất giao dịch nếu thành công
```

Một giao dịch vẫn có thể rollback sau flush. Thời điểm câu lệnh được phát còn phụ thuộc provider và thao tác; không nên hiểu hình vẽ là mọi câu lệnh luôn đợi đến một điểm duy nhất.

Flush có thể làm một số lỗi ràng buộc xuất hiện sớm hơn, nhưng không bảo đảm mọi lỗi chỉ có thể xảy ra ở thời điểm flush. Việc dữ liệu đã nhìn thấy ở giao dịch khác còn phụ thuộc commit, isolation và hệ quản trị.

Vì vậy, `saveAndFlush` không phải biến thể “an toàn hơn cho mọi tình huống” hoặc luôn nhanh hơn `save`. Gọi flush quá thường xuyên có thể làm giảm khả năng tối ưu và tăng số lần đồng bộ không cần thiết.

### 4.2. Batch ở tên phương thức cần được đọc đúng semantics

Các phương thức xóa bulk như `deleteAllInBatch` có hành vi khác với việc tải từng entity rồi xóa từng phần tử. Khi sử dụng cần xem:

- Phạm vi dữ liệu bị tác động.
- Entity lifecycle callback có được thực hiện như đường xóa từng entity không.
- Cascade ở cấp JPA và ràng buộc hoặc trigger ở database khác nhau ra sao.
- Persistence context có còn giữ entity không phản ánh trạng thái database không.
- Việc flush, làm mới hoặc clear context cần được xử lý như thế nào trong luồng đó.

Đặc biệt, không dùng xóa bulk rồi mặc định mọi entity callback và JPA cascade đều diễn ra như thao tác xóa riêng lẻ. Database vẫn có cơ chế ràng buộc của nó; hai tầng không được đánh đồng.

`saveAll` theo hợp đồng chung cũng không tự hứa một câu lệnh SQL batch duy nhất. Khả năng batch thực tế còn phụ thuộc provider, chiến lược ID và cấu hình.

## 5. `MongoRepository`: repository gắn với document MongoDB

`MongoRepository<T, ID>` thuộc package `org.springframework.data.mongodb.repository`. Nó sử dụng mô hình document, mapping và hạ tầng MongoDB của module.

Các khái niệm cần quan tâm gồm:

- Document và collection.
- Mapping thuộc tính Java sang field lưu trữ.
- Định danh `_id` và cách chuyển đổi kiểu.
- Lưu document, insert và cập nhật theo field.
- Chỉ mục, write concern và các yêu cầu triển khai liên quan.

Những khái niệm này không phải bản sao đổi tên của bảng, entity và persistence context trong JPA.

### 5.1. Ví dụ mô hình MongoDB riêng

```java
package example.customer.mongo;

import java.util.Objects;

import example.customer.model.CustomerStatus;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "customers")
public class MongoCustomer {
    @Id
    private String id;

    @Version
    private Long version;

    private String email;
    private CustomerStatus status;

    protected MongoCustomer() {
    }

    public MongoCustomer(String email) {
        this.email = Objects.requireNonNull(email, "email");
        this.status = CustomerStatus.ACTIVE;
    }

    public String getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getEmail() {
        return email;
    }

    public CustomerStatus getStatus() {
        return status;
    }

    public void changeEmail(String email) {
        this.email = Objects.requireNonNull(email, "email");
    }
}
```

ID kiểu `String` là lựa chọn của ví dụ MongoDB này, không phải quy tắc bắt buộc cho mọi document. Cách phát sinh, chuyển đổi và lưu ID phải được xem cùng mapping của module.

Repository tương ứng:

```java
package example.customer.mongo;

import java.util.Optional;

import example.customer.model.CustomerStatus;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface MongoCustomerRepository
        extends MongoRepository<MongoCustomer, String> {

    Optional<MongoCustomer> findByEmail(String email);

    Page<MongoCustomer> findByStatus(
            CustomerStatus status,
            Pageable pageable);
}
```

Hai repository mẫu diễn đạt các truy vấn tương tự ở mức nhu cầu. Chúng dùng hai mô hình persistence và kiểu ID khác nhau để thể hiện rõ lựa chọn của từng adapter.

### 5.2. `insert` thể hiện ý định thêm mới

`MongoRepository` có các phương thức `insert` gắn với ý định thêm document mới. Ví dụ:

```java
MongoCustomer inserted = repository.insert(
        new MongoCustomer("an@example.test"));
```

Nếu thao tác đụng một giá trị định danh đã tồn tại hoặc ràng buộc duy nhất khác, nó không được hiểu như yêu cầu cập nhật document đó. Ứng dụng cần xử lý lỗi theo hợp đồng và ràng buộc thực tế.

`save` có ý nghĩa lưu thực thể theo cơ chế của module, trong đó trạng thái mới/cũ và metadata có thể ảnh hưởng cách thực thi. Không nên thay mọi `insert` bằng `save`, hoặc ngược lại, chỉ vì cả hai đều có thể lưu một document mới trong một tình huống đơn giản.

Chọn API theo ý định nghiệp vụ và semantics mong muốn: bắt buộc tạo mới, lưu trạng thái hay cập nhật một số field có điều kiện.

### 5.3. Lưu document không phải dirty checking của JPA

Sau khi đọc một document về thành đối tượng Java, việc thay đổi thuộc tính không tự tạo một persistence context theo mô hình JPA để ghi thay đổi ở cuối giao dịch.

Ứng dụng cần gọi thao tác lưu hoặc cập nhật thích hợp. Với cập nhật theo field, thao tác nguyên tử hoặc điều kiện phiên bản, có thể cần API thao tác dữ liệu của module, chẳng hạn `MongoTemplate`, hoặc một fragment phù hợp.

Không mặc định `save` là patch chỉ những field vừa được setter thay đổi. Nó lưu dữ liệu theo mapping và semantics của đường thao tác đó. Nếu nghiệp vụ chỉ được sửa một vài trường, cần chọn cơ chế cập nhật rõ phạm vi thay vì dựa vào giả định về object trong bộ nhớ.

### 5.4. Không có một `flush` MongoDB tương đương persistence context JPA

Nếu code nghiệp vụ phụ thuộc `flush`, cần xem nó thật sự muốn điều gì: phát hiện lỗi sớm, chờ xác nhận ghi, kiểm tra ràng buộc hay bảo đảm một ranh giới giao dịch.

Khi chuyển sang MongoDB, phải ánh xạ nhu cầu đó sang cơ chế thích hợp của MongoDB. Thêm một phương thức `flush` rỗng vào adapter không làm hợp đồng cũ được giữ nguyên.

## 6. So sánh các khả năng theo đúng tầng

| Khía cạnh | `JpaRepository` | `MongoRepository` |
| --- | --- | --- |
| Module cung cấp | Spring Data JPA | Spring Data MongoDB |
| Mô hình lưu trữ | Entity được mapping theo JPA | Document được mapping theo MongoDB |
| Hạ tầng thao tác | `EntityManager`, provider và cơ sở dữ liệu quan hệ | Hạ tầng thao tác MongoDB và driver |
| Metadata mẫu | `@Entity`, annotation ID/version của JPA | `@Document`, annotation ID/version của Spring Data |
| Vòng đời đối tượng | Có persistence context và trạng thái managed/detached | Không có cùng cơ chế dirty checking managed entity của JPA |
| Thao tác đặc thù dễ gặp | Flush, lưu kèm flush, xóa bulk theo API | Insert document và các tích hợp theo mô hình MongoDB |
| Cập nhật chi tiết | Phụ thuộc JPA, truy vấn cập nhật hoặc implementation đặc thù | Có thể dùng thao tác update theo field của MongoDB |
| Truy vấn khai báo | JPQL hoặc native SQL theo cấu hình | Biểu thức và toán tử theo MongoDB |
| Giao dịch | Cần hạ tầng transaction JPA phù hợp | Cần hỗ trợ MongoDB, cấu hình và môi trường triển khai phù hợp |
| Chỉ mục và tính duy nhất | Schema, constraint, migration và hệ quản trị | Index, cấu hình tạo index và quy trình vận hành |

Bảng không xếp hạng khả năng của hai store. Nó chỉ ra nơi phải xem xét khi API có tên giống nhau nhưng đường thực thi khác nhau.

## 7. Annotation cùng tên không có nghĩa cùng loại

Ví dụ `@Id` và `@Version` xuất hiện ở cả hai mô hình nhưng import khác package:

| Ý nghĩa | Ví dụ JPA dùng Jakarta Persistence | Ví dụ MongoDB |
| --- | --- | --- |
| Định danh | `jakarta.persistence.Id` | `org.springframework.data.annotation.Id` |
| Phiên bản | `jakarta.persistence.Version` | `org.springframework.data.annotation.Version` |
| Kiểu persistence | `jakarta.persistence.Entity` | `org.springframework.data.mongodb.core.mapping.Document` |

Cần đọc import khi xem mã, không chỉ đọc tên annotation. Nếu dự án thuộc thế hệ dùng namespace khác, phải đồng bộ entity, provider và module theo đúng bộ đó.

Việc có trường `version` hoặc annotation trong mô hình cũng chưa chứng minh mọi đường ghi đều kiểm soát cạnh tranh. API cập nhật trực tiếp, thao tác bulk hoặc lệnh từ hệ thống khác có thể có cơ chế khác; cần xác định những đường ghi nào tham gia quy tắc phiên bản.

Tương tự, các trường auditing cần cấu hình và cơ chế thực thi của module. Chỉ kế thừa `JpaRepository` hoặc `MongoRepository` chưa tự bật việc điền người tạo, người sửa hoặc thời điểm thay đổi.

## 8. Tên derived query giống nhau, truy vấn thực tế khác nhau

Hai phương thức mẫu `findByStatus` đều dựa vào thuộc tính Java và các quy ước chung của Spring Data. Module sẽ chuyển điều kiện đó sang thao tác mà store hỗ trợ.

Không thể suy ra từ tên phương thức rằng:

- Mọi toán tử đều khả dụng ở cả hai module.
- Chuỗi được so sánh giống nhau về chữ hoa, dấu hoặc collation.
- Đường dẫn lồng nhau có cùng chi phí hay cùng cơ chế join.
- `null` và dữ liệu thiếu field luôn có cùng ý nghĩa.
- Truy vấn sẽ dùng chỉ mục tương đương.

### 8.1. Annotation truy vấn thuộc module

Khi dùng `@Query`, phải xác định đúng annotation và ngôn ngữ của nó. Một biểu thức JPQL không thể được chép sang annotation truy vấn MongoDB rồi mặc định sẽ chạy.

Tên lớp entity và thuộc tính trong JPQL cũng khác với tên bảng/cột của SQL native. Tương tự, truy vấn MongoDB cần được hiểu cùng mapping field và khả năng chuyển đổi giá trị của module.

### 8.2. Interface đặc thù không tự có mọi extension

Chọn `JpaRepository` không có nghĩa mọi khả năng trong Spring Data JPA đều đã được công khai. Chẳng hạn, khi cần specification, thường phải khai báo thêm hợp đồng như `JpaSpecificationExecutor` theo nhu cầu và phiên bản hỗ trợ.

Querydsl cũng cần các dependency, kiểu truy vấn được sinh và tích hợp của module tương ứng. Không coi nó là một tính năng tự xuất hiện chỉ vì repository đã là interface đặc thù store.

Query by Example, projection và các loại kết quả khác cần được đánh giá theo API của module đang dùng. Việc có một abstraction chung là điểm xuất phát để tái sử dụng cách diễn đạt, không phải lời hứa mọi store có tập tính năng hoàn toàn giống nhau.

## 9. Phân trang và projection vẫn cần xem khả năng thực thi

Hai repository có thể cùng nhận một yêu cầu:

```java
Pageable request = PageRequest.of(
        0,
        20,
        Sort.by("email").ascending());
```

Ví dụ cần import `Pageable`, `PageRequest` và `Sort` từ `org.springframework.data.domain`. Thuộc tính `email` phải được mapping và hỗ trợ sắp xếp trong mô hình tương ứng.

Điều dùng chung là cách mô tả trang và thứ tự. Chi phí lấy trang, lấy tổng số, xử lý offset lớn và dùng chỉ mục cần được đánh giá trên store thật.

Nếu nhiều bản ghi có cùng email và ứng dụng cần thứ tự xác định, có thể thêm một tiêu chí phân định như ID theo mô hình. Tuy nhiên, thứ tự xác định chưa tạo ảnh chụp dữ liệu ổn định qua nhiều request khi có cập nhật đồng thời.

Với projection, kiểu trả về có thể chỉ chứa ID và email. Cần kiểm tra cách module tạo projection và truy vấn thực tế trước khi kết luận chỉ những field đó được đọc từ store.

## 10. Khi nào nên dùng trực tiếp interface đặc thù?

### 10.1. Khi công nghệ là một lựa chọn rõ ràng của ứng dụng

Nếu ứng dụng đã chọn JPA và cần flush hoặc hành vi JPA cụ thể, phụ thuộc `JpaRepository` tại tầng persistence là lựa chọn rõ ràng. Người bảo trì thấy ngay API và tài liệu nào liên quan.

Tương tự, nếu ứng dụng lưu document và cần ý định insert rõ ràng, `MongoRepository` có thể thể hiện nhu cầu tốt hơn một interface tự tạo che mọi chi tiết nhưng không mô tả semantics.

Không cần che tên công nghệ ở mọi nơi bằng nhiều lớp chỉ để repository trông tổng quát. Ranh giới bổ sung có giá trị khi nó bảo vệ hợp đồng nghiệp vụ, giảm phụ thuộc cho bên dùng hoặc tạo nơi chuyển đổi có ý nghĩa.

### 10.2. Khi chỉ cần một phần nhỏ API

Kế thừa interface store cũng công khai tập phương thức của nó. Nếu một bên dùng chỉ cần tra cứu, có thể:

- Đưa một service tra cứu hoặc interface ứng dụng hẹp ra phía ngoài.
- Chọn lọc phương thức trên interface dựa vào `Repository`, nếu phù hợp cơ chế module và cấu hình.
- Giữ repository rộng ở tầng persistence, chỉ cho các thành phần có nhu cầu phù hợp sử dụng.

Không đặt tên interface là “chỉ đọc” rồi vẫn kế thừa đầy đủ thao tác ghi, xóa mà không xem xét tác động. Tên không làm mất phương thức được kế thừa.

### 10.3. Khi cần đổi store trong tương lai

Hãy mô tả hành vi nghiệp vụ phải giữ nguyên trước. Ví dụ, “tra cứu khách hàng theo email chuẩn hóa trong một tổ chức” cụ thể hơn “có một repository chung”.

Sau đó adapter JPA và adapter MongoDB có thể dùng repository riêng để đáp ứng hợp đồng. ID, mapping, query và ràng buộc dữ liệu được xử lý theo từng store.

Việc thay `extends JpaRepository` thành `extends MongoRepository` không tự chuyển schema, quan hệ, chỉ mục, callback, transaction và dữ liệu đã có. Đây là thay đổi mô hình tích hợp, không chỉ là thay import.

## 11. Tổ chức ứng dụng có nhiều store

Một ứng dụng có thể dùng JPA cho dữ liệu nghiệp vụ và MongoDB cho một phần dữ liệu document. Trong trường hợp đó, cần xác định repository nào do module nào quản lý.

Một cấu trúc package có thể là:

```text
example.customer.model
    CustomerStatus

example.customer.jpa
    JpaCustomer
    JpaCustomerRepository

example.customer.mongo
    MongoCustomer
    MongoCustomerRepository
```

Kế thừa interface đặc thù giúp thể hiện module đích. Mapping của domain và phạm vi quét repository cũng là những căn cứ quan trọng khi có nhiều module trên classpath.

Nếu cấu hình quét tường minh, có thể giới hạn theo lớp đại diện:

```java
@Configuration
@EnableJpaRepositories(basePackageClasses = JpaCustomerRepository.class)
class JpaRepositoryConfiguration {
}
```

```java
@Configuration
@EnableMongoRepositories(basePackageClasses = MongoCustomerRepository.class)
class MongoRepositoryConfiguration {
}
```

Các annotation tương ứng thuộc `org.springframework.context.annotation`, `org.springframework.data.jpa.repository.config` và `org.springframework.data.mongodb.repository.config`.

Đây chỉ là minh họa giới hạn phạm vi repository scan. JPA vẫn cần entity mapping và `EntityManagerFactory` phù hợp; MongoDB vẫn cần client, database và hạ tầng thao tác thích hợp. Nếu có nhiều nguồn kết nối, còn cần gắn repository với đúng bean hạ tầng theo cấu hình module.

Không dùng một domain gắn lẫn mọi annotation rồi mặc định việc nhận diện store luôn rõ ràng. Khi repository chỉ dựa trên interface chung hoặc metadata có nhiều dấu hiệu tích hợp, cần kiểm tra cách module phân loại repository và tránh quét chồng ngoài ý muốn.

## 12. Giao dịch qua hai loại repository cần quyết định riêng

Hai lời gọi sau không tự tạo một giao dịch nguyên tử bao trùm hai store:

```text
Lưu khách hàng qua JpaRepository
        |
        v
Lưu document bổ sung qua MongoRepository
```

Nếu bước thứ hai thất bại, ứng dụng phải có quyết định về trạng thái bước thứ nhất. Cần xác định transaction manager nào tham gia, tài nguyên nào được quản lý và chiến lược nhất quán của nghiệp vụ.

Một annotation giao dịch không mặc định phối hợp mọi datasource và mọi loại store thành một tài nguyên duy nhất. Với MongoDB, hỗ trợ giao dịch còn phụ thuộc cấu hình và môi trường triển khai đáp ứng yêu cầu tương ứng.

Nếu nghiệp vụ trải qua nhiều store, có thể cần thiết kế xử lý bù, sự kiện hoặc cơ chế đồng bộ thích hợp. Chọn giải pháp theo yêu cầu nguyên tử và khả năng vận hành, không theo việc cả hai repository cùng nằm trong hệ sinh thái Spring Data.

Hai interface trong bài là các API theo hướng imperative. Nếu chuyển sang reactive, cần các interface, module, driver và cơ chế giao dịch tương ứng; không chỉ thay kiểu trả về bằng publisher.

## 13. Kiểm tra tích hợp theo khác biệt quan trọng

Một kiểm thử dùng mock `JpaRepository` hoặc `MongoRepository` có thể hữu ích cho logic điều phối của service. Nó không chứng minh mapping, query generation hoặc semantics lưu của store.

| Phần kiểm tra | Ví dụ với JPA | Ví dụ với MongoDB |
| --- | --- | --- |
| Khởi tạo repository | Entity được nhận diện, provider và repository factory hoạt động | Document mapping và repository factory hoạt động |
| Lưu mới | ID, version và trạng thái sau lưu đúng dự kiến | ID, version và document sau lưu đúng dự kiến |
| Cập nhật | Managed/detached và merge được xử lý phù hợp | Đường save/update thay đổi đúng phạm vi field |
| Thao tác đặc thù | Flush, rollback sau flush hoặc xóa bulk theo nhu cầu | Insert mới, xử lý trùng khóa hoặc update có điều kiện |
| Truy vấn | Derived query, JPQL/native query và projection | Derived query, biểu thức MongoDB và projection |
| Phân trang | Nội dung, tổng số, thứ tự và chi phí phù hợp | Nội dung, tổng số, thứ tự và chỉ mục phù hợp |
| Cạnh tranh | Version, khóa hoặc ràng buộc được dùng đúng đường ghi | Version, cập nhật nguyên tử hoặc ràng buộc được dùng đúng đường ghi |
| Auditing | Cấu hình và callback thực sự đi qua đường ghi | Cấu hình và callback thực sự đi qua đường ghi |

Chọn các tình huống ứng dụng thật sự sử dụng. Không cần kiểm tra lại mọi phương thức framework, nhưng phải có bằng chứng cho những giả định đặc thù mà nghiệp vụ dựa vào.

Khi gặp lỗi, phân biệt các tầng: dependency không tương thích, repository scan sai, mapping sai, truy vấn không hỗ trợ, cấu hình kết nối hoặc ràng buộc dữ liệu. Thêm một interface kế thừa mới không tự sửa được lỗi ở các tầng khác.

## 14. Tình huống thực hành: chuyển chức năng đăng ký khách hàng

Một service hiện dùng JPA, gọi `saveAndFlush` rồi trả ID khách hàng. Nhóm muốn chuyển chức năng sang MongoDB và đề xuất đổi repository sang `MongoRepository`.

Cần phân tích ít nhất các điểm sau:

1. **ID:** API có đang công bố ID kiểu `Long` không? Nếu mô hình mới chọn kiểu khác, hợp đồng bên ngoài thay đổi thế nào?
2. **Tính duy nhất:** Email được chuẩn hóa và ràng buộc ở đâu? Chỉ khai báo `findByEmail` chưa đủ chống hai yêu cầu tạo đồng thời.
3. **Mục đích flush:** Service dùng nó để quan sát điều gì? Cần ánh xạ nhu cầu đó sang cơ chế phù hợp, không tạo phương thức rỗng cho qua.
4. **Ý định tạo mới:** Đường MongoDB nên dùng insert hay save theo hợp đồng đăng ký?
5. **Giao dịch:** Có thao tác khác phải thành công cùng việc tạo khách hàng không?
6. **Auditing và version:** Cơ chế mới có được bật và bao phủ những đường ghi cần thiết không?
7. **Dữ liệu hiện có:** Mapping và quy trình chuyển dữ liệu có giữ được quy tắc nghiệp vụ không?

Một hợp đồng ứng dụng như `registerCustomer` có thể được giữ ổn định nếu các adapter đáp ứng cùng hành vi đã xác định. Repository bên trong adapter vẫn được lựa chọn theo store, không cần ép các thao tác đặc thù thành những tên phương thức chung thiếu ý nghĩa.

## 15. Những suy luận dễ sai

| Suy luận | Cách hiểu chính xác hơn |
| --- | --- |
| “Cùng có `save` nên cách cập nhật giống nhau.” | Hợp đồng lưu có phần chung; vòng đời entity/document và cách thực thi phụ thuộc module. |
| “`saveAndFlush` nghĩa là đã commit.” | Flush không thay thế commit; giao dịch vẫn có thể rollback hoặc lỗi về sau. |
| “MongoDB tự ghi thay đổi khi sửa object đã đọc.” | Không có cùng persistence context và dirty checking của JPA; cần thao tác lưu/update thích hợp. |
| “`insert` là tên khác của `save`.” | Insert thể hiện ý định thêm mới; cần phân biệt với lưu hoặc cập nhật. |
| “Cùng tên `@Id` thì import nào cũng được.” | Package annotation quyết định metadata mà công nghệ tích hợp hiểu. |
| “Kế thừa `JpaRepository` là đã có mọi extension JPA.” | Một số khả năng cần hợp đồng và dependency bổ sung theo nhu cầu. |
| “Chỉ đổi interface là chuyển xong store.” | Còn mapping, ID, query, index, giao dịch, dữ liệu và hành vi nghiệp vụ. |
| “Hai repository trong một service tự chung giao dịch.” | Phải xác định tài nguyên, transaction manager và cơ chế nhất quán thực tế. |

## 16. Câu hỏi tự kiểm tra

### Câu 1

Vì sao `JpaRepository` có thao tác flush mà không nên tự thêm một flush rỗng vào adapter MongoDB?

**Gợi ý trả lời:** Flush gắn với cơ chế persistence context JPA. Một hàm rỗng không bảo đảm nhu cầu ban đầu của ứng dụng; phải xác định và thực hiện hành vi tương ứng theo store mới.

### Câu 2

Một entity JPA detached được lưu bằng `save`. Vì sao nên giữ giá trị trả về?

**Gợi ý trả lời:** Đường merge có thể trả về một instance được quản lý khác instance đầu vào. Cần sử dụng kết quả theo hợp đồng lưu thay vì mặc định đầu vào luôn chứa trạng thái cuối cùng.

### Câu 3

Hai repository đều có `findByStatus(CustomerStatus, Pageable)`. Có đủ căn cứ kết luận hiệu năng, collation và truy vấn đếm giống nhau không?

**Gợi ý trả lời:** Không. Phần mô tả điều kiện và trang có thể tương tự; mapping, ngôn ngữ truy vấn, chỉ mục và kế hoạch thực thi phụ thuộc store.

### Câu 4

Có `@Version` trong hai mô hình có đủ chứng minh mọi cập nhật trực tiếp đều chống ghi đè không?

**Gợi ý trả lời:** Chưa đủ. Phải xác định đường thao tác có tham gia cơ chế kiểm tra phiên bản hay không và xử lý xung đột theo hợp đồng ứng dụng.

### Câu 5

Khi ứng dụng chỉ có một loại store và thật sự cần API đặc thù, có bắt buộc che nó sau nhiều lớp interface chung không?

**Gợi ý trả lời:** Không. Có thể dùng interface đặc thù ở ranh giới phù hợp. Lớp bổ sung có giá trị khi bảo vệ hợp đồng nghiệp vụ hoặc giảm phụ thuộc có ý nghĩa cho bên dùng.

### Câu 6

Một ứng dụng có JPA và MongoDB cần làm rõ những gì ngoài số phiên bản dependency?

**Gợi ý trả lời:** Mapping, phạm vi quét repository, bean hạ tầng gắn với từng module, giao dịch, chỉ mục và các quy tắc dữ liệu. Tập JAR phù hợp chưa thay thế cấu hình và kiểm tra hành vi trên store.