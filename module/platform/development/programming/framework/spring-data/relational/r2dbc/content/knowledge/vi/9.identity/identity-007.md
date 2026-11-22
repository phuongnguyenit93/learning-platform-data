# Quan hệ giữa thuộc tính @Version và việc xác định thực thể mới

Khi gọi save() trong Spring Data Relational R2DBC, framework cần quyết định sẽ thực hiện thao tác INSERT hay UPDATE. Quyết định này dựa trên trạng thái mới/cũ của entity (new state). Spring Data không mặc định gửi một câu SELECT để kiểm tra xem ID đã tồn tại trong database hay chưa; nó dùng metadata và trạng thái của object để xác định hướng ghi.

Thông thường, Spring Data kiểm tra thuộc tính ID. Tuy nhiên, nếu entity có thuộc tính được đánh dấu bằng @Version, thuộc tính version được ưu tiên để xác định entity mới. Điều này tạo ra mối liên hệ quan trọng giữa **nhận diện entity mới** và **optimistic locking**:

- Version chưa được thiết lập biểu thị entity mới.
- Version đã có giá trị biểu thị entity đã tồn tại.
- Với entity đã tồn tại, version được dùng để kiểm tra xem bản ghi có bị một transaction khác thay đổi kể từ lần đọc hay không.

Vì vậy, @Version không chỉ là một cột đếm số lần cập nhật. Nó còn ảnh hưởng trực tiếp đến việc Spring Data chọn INSERT hay UPDATE khi lưu entity.

## 1. Vì sao Spring Data cần xác định entity mới?

Một repository có thể cung cấp cùng một phương thức save() cho cả entity mới và entity đã tồn tại:

~~~java
Mono<Customer> saved = customerRepository.save(customer);
~~~

Nhưng hai trường hợp cần câu SQL khác nhau:

- Entity mới cần được thêm vào bảng bằng INSERT.
- Entity đã tồn tại cần được thay đổi bằng UPDATE.

Spring Data phải xác định trạng thái trước khi thực hiện thao tác lưu. Cơ chế này được gọi là entity state detection hoặc xác định new state.

Ví dụ bảng customer:

| id | name | version |
|---:|---|---:|
| 10 | An | 3 |
| 11 | Bình | 5 |

Một object mới có thể chưa có ID do database sinh tự động. Nhưng nhiều hệ thống dùng ID được cấp từ trước, chẳng hạn UUID hoặc ID do ứng dụng tạo. Khi đó, chỉ nhìn ID không đủ để biết object cần insert hay update.

Thuộc tính @Version giúp Spring Data nhận diện trạng thái bằng một dấu hiệu khác. Một entity mới có thể đã có ID nhưng version vẫn chưa được thiết lập.

## 2. @Version là gì?

@Version là annotation của Spring Data dùng để đánh dấu thuộc tính version trong entity. Trong Spring Data Relational, thuộc tính này được dùng để hỗ trợ **optimistic locking** (khóa lạc quan).

Ví dụ entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Version
    private Long version;

    private String name;

    private String email;

    protected Customer() {
    }

    public Customer(String name, String email) {
        this.name = name;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getName() {
        return name;
    }

    public void assignId(Long id) {
        this.id = id;
    }
}
~~~

Trong ví dụ:

- id là định danh của customer.
- version là phiên bản của trạng thái được lưu trong database.
- name và email là dữ liệu nghiệp vụ.

Nên dùng đúng annotation org.springframework.data.annotation.Version trong mô hình Spring Data Relational. Annotation version của JPA thuộc một API khác và không phải annotation cần dùng cho entity R2DBC.

Version thường là kiểu số nguyên như Long hoặc Integer. Framework quản lý giá trị version khi insert/update theo quy tắc của module và phiên bản đang dùng. Ứng dụng không nên tự tăng version trong business code như thể đó là một thuộc tính nghiệp vụ thông thường.

## 3. Thứ tự xác định entity mới

Với cơ chế mặc định của Spring Data, có thể hiểu thứ tự quyết định như sau:

1. Nếu entity triển khai Persistable, Spring Data sử dụng phương thức isNew() do entity cung cấp.
2. Nếu entity không triển khai Persistable nhưng có thuộc tính @Version, Spring Data kiểm tra version trước.
3. Nếu không có version property, Spring Data kiểm tra ID.

Version được ưu tiên trước ID là điểm quan trọng nhất của bài học này. Khi version property có mặt, Spring Data không đơn giản bỏ qua nó rồi quay lại dùng ID để quyết định.

### Khi có thuộc tính @Version

Với thuộc tính version dạng wrapper nullable như Long:

- version == null: entity được xem là mới.
- version != null: entity được xem là đã tồn tại.

Với thuộc tính version dạng primitive số nguyên như long hoặc int, giá trị mặc định 0 được xem là trạng thái mới; giá trị khác 0 được xem là trạng thái đã tồn tại.

Điểm cần chú ý: nếu dùng wrapper Long, giá trị 0L vẫn là một giá trị khác null. Vì vậy, một object mới có version = 0L được xem là existing theo phép kiểm tra null của wrapper. Khi dựa vào version để nhận diện entity mới, nên để version wrapper ở trạng thái null trước lần lưu đầu tiên.

### Khi không có thuộc tính @Version

Spring Data quay về kiểm tra ID:

- ID dạng wrapper có giá trị null: entity mới.
- ID dạng primitive số nguyên có giá trị mặc định 0: entity mới.
- ID đã có giá trị khác trạng thái mới: entity được xem là đã tồn tại.

Điều này có ý nghĩa với ID được cấp trước. Nếu một entity có UUID đã được gán và không có version property, Spring Data mặc định có thể xem entity đó là existing và chọn update. Nếu cần insert entity có ID được cấp trước, phải dùng cơ chế nhận diện trạng thái phù hợp, chẳng hạn version nullable hoặc Persistable.

## 4. Bảng trạng thái: version ảnh hưởng đến quyết định như thế nào?

Bảng sau minh họa quy tắc mặc định với entity không triển khai Persistable:

| ID | Version | Kết quả nhận diện | Thao tác save |
|---|---|---|---|
| null | null (Long) | Mới | INSERT |
| 42 | null (Long) | Mới | INSERT |
| 42 | 3L (Long) | Đã tồn tại | UPDATE |
| 42 | 0L (Long) | Đã tồn tại vì wrapper khác null | UPDATE |
| 42 | 0 (long) | Mới vì primitive mặc định bằng 0 | INSERT |
| 42 | 3 (long) | Đã tồn tại | UPDATE |

Hai dòng có ID 42 nhưng version khác nhau có thể dẫn tới quyết định khác nhau. Đây là lý do không nên chỉ nhìn ID rồi kết luận save() sẽ insert hay update.

Nếu trạng thái object không phù hợp với dữ liệu thật trong database, thao tác có thể thất bại:

- Một entity bị nhận diện là mới sẽ đi theo nhánh insert. Nếu ID đã tồn tại, database có thể báo vi phạm khóa chính.
- Một entity bị nhận diện là existing sẽ đi theo nhánh update. Nếu không có dòng phù hợp, thao tác không tự động chuyển thành insert.
- Nếu update có optimistic locking và không dòng nào khớp cả ID lẫn version, Spring Data báo lỗi optimistic locking.

## 5. @Version thay đổi luồng save như thế nào?

Hãy xét entity mới với ID được ứng dụng gán sẵn:

~~~java
Customer customer = new Customer("An", "an@example.com");
customer.assignId(42L);
// version vẫn null vì chưa được thiết lập.
~~~

Do version đang null, Spring Data nhận diện entity là mới dù ID đã có giá trị. Khi gọi:

~~~java
Mono<Customer> saved = customerRepository.save(customer);
~~~

Framework chọn thao tác insert. Với version dạng số, Spring Data khởi tạo version theo quy tắc của module (thông thường giá trị ban đầu là 0) và trả về entity đã được lưu.

Sau lần insert, object được trả về có ID và version đã được thiết lập. Khi dùng entity đã lưu để cập nhật, version có giá trị nên Spring Data nhận diện đây là entity existing và đi theo nhánh update.

Luồng tổng quát:

~~~text
Tạo entity
   |
   +-- version chưa có giá trị
   |
   v
Spring Data nhận diện NEW
   |
   v
INSERT
   |
   v
Thiết lập ID / version ban đầu
   |
   v
Trả về entity đã lưu
   |
   +-- version đã có giá trị
   |
   v
Spring Data nhận diện EXISTING
   |
   v
UPDATE có điều kiện theo ID và version
   |
   v
Tăng version và trả entity mới
~~~

Hãy sử dụng object được trả về từ save():

~~~java
return customerRepository.save(customer)
    .flatMap(savedCustomer -> {
        // savedCustomer chứa ID/version sau khi persistence
        return Mono.just(savedCustomer);
    });
~~~

Điều này đặc biệt quan trọng với entity bất biến hoặc khi ID/version được framework cập nhật bằng cách tạo ra instance mới. Không nên bỏ kết quả trả về rồi tiếp tục dùng object cũ với version chưa được cập nhật.

## 6. @Version và optimistic locking

Optimistic locking giả định xung đột ghi không xảy ra thường xuyên. Thay vì khóa bản ghi trong suốt thời gian người dùng đọc và chỉnh sửa, ứng dụng lưu lại version đã đọc. Khi ghi, database chỉ cập nhật nếu version hiện tại vẫn bằng version mà ứng dụng đã đọc.

Ví dụ ban đầu:

| id | name | version |
|---:|---|---:|
| 42 | An | 5 |

Hai request A và B cùng đọc customer có version 5.

| Thời điểm | Request A | Request B | Database |
|---|---|---|---|
| T1 | Đọc version 5 | | version 5 |
| T2 | | Đọc version 5 | version 5 |
| T3 | Cập nhật tên, gửi version 5 | | version 5 |
| T4 | Update thành công, version thành 6 | | version 6 |
| T5 | | Gửi update với version 5 cũ | version 6 |
| T6 | | Không có dòng khớp ID và version 5 | version 6 |

Về ý tưởng, câu lệnh update tương đương:

~~~sql
UPDATE customer
SET name = :name,
    version = :next_version
WHERE id = :id
  AND version = :previous_version;
~~~

Request A cập nhật thành công vì database đang có version 5. Version được chuyển sang 6. Request B vẫn gửi version 5, nhưng database đã có version 6; điều kiện WHERE không khớp nên không có dòng nào được cập nhật.

Spring Data nhận biết số dòng bị tác động không như mong đợi và báo lỗi optimistic locking, thường dưới dạng OptimisticLockingFailureException. Ứng dụng có thể trả lỗi xung đột cho client, tải lại dữ liệu mới rồi yêu cầu người dùng giải quyết thay đổi, hoặc thực hiện một chiến lược merge/retry phù hợp với nghiệp vụ.

@Version cũng được dùng để bảo vệ thao tác xóa có kiểm tra version trong các trường hợp được Spring Data hỗ trợ. Một entity cũ không nên xóa bản ghi đã được cập nhật bởi request khác mà không phát hiện xung đột.

## 7. Phân biệt version với ID

ID và version có vai trò khác nhau:

| Thuộc tính | ID | Version |
|---|---|---|
| Mục đích | Xác định entity | Xác định phiên bản trạng thái đã đọc/lưu |
| Thay đổi qua các lần cập nhật | Thông thường không | Được tăng khi cập nhật thành công |
| Dùng làm khóa chính | Thường có | Không |
| Hỗ trợ new-state detection | Có, khi không có version hoặc chiến lược tùy chỉnh | Được ưu tiên nếu có version property |
| Hỗ trợ optimistic locking | Không tự nó | Có |

Không dùng version như ID thứ hai. Hai entity khác nhau có thể cùng version 0, 1 hoặc 5; giá trị version chỉ có ý nghĩa trong phạm vi một bản ghi.

Không dùng version để lưu thời điểm cập nhật hoặc trạng thái nghiệp vụ. Nếu cần updatedAt, hãy dùng một thuộc tính thời gian riêng và cơ chế auditing phù hợp. Version là token kiểm soát đồng thời, không phải dữ liệu hiển thị cho người dùng.

## 8. Persistable và trường hợp cần tự quyết định trạng thái

Spring Data cung cấp interface Persistable<ID> để entity tự cung cấp:

- getId() trả về định danh.
- isNew() cho biết entity có phải mới hay không.

Khi entity triển khai Persistable, Spring Data sử dụng isNew() do entity cung cấp thay cho chiến lược mặc định dựa trên version/ID. Cách này hữu ích khi ứng dụng có quy tắc nhận diện đặc biệt, chẳng hạn ID luôn được gán trước khi insert.

Ví dụ minh họa:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.domain.Persistable;
import java.util.UUID;

public class Customer implements Persistable<UUID> {

    @Id
    private UUID id;

    @Transient
    private boolean newEntity;

    protected Customer() {
        // Entity được Spring Data tạo lại từ database là entity đã tồn tại.
        this.newEntity = false;
    }

    public static Customer newCustomer(UUID id) {
        Customer customer = new Customer();
        customer.id = id;
        customer.newEntity = true;
        return customer;
    }

    @Override
    public UUID getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }

    public void markPersisted() {
        this.newEntity = false;
    }
}
~~~

Đây là khung minh họa cho chiến lược tùy chỉnh; ứng dụng phải quản lý thời điểm chuyển newEntity sang false một cách nhất quán với kết quả persistence, ví dụ qua lifecycle callback phù hợp hoặc factory/domain flow. Không được đánh dấu entity là existing trước khi insert thành công.

Nếu đã có @Version, thường nên tận dụng chiến lược mặc định trước khi thêm trạng thái Persistable thủ công. Hai cơ chế cùng tồn tại nhưng Persistable.isNew() sẽ điều khiển quyết định new state; nếu cài đặt sai, nó có thể làm mất ý nghĩa nhận diện từ version.

## 9. Các tình huống cần chú ý

### Entity có ID được gán trước

Nếu entity mới có UUID hoặc ID do ứng dụng cấp, @Version Long để null giúp Spring Data nhận diện entity mới và insert. Nếu không có version property, ID khác null có thể khiến chiến lược mặc định chọn update. Trong trường hợp đó, cân nhắc Persistable hoặc một chiến lược ID phù hợp.

### Entity mới nhưng version wrapper được khởi tạo bằng 0

Với Long version, giá trị 0L khác null. Theo chiến lược version-based detection, nó biểu thị existing. Nếu muốn entity mới được nhận diện bằng version wrapper, hãy để trường version null trước lần save đầu tiên. Với primitive long, giá trị mặc định 0 được xem là new.

### Entity hiện có nhưng version bị đặt lại null

Nếu tải entity hiện có rồi vô tình đặt version về null, Spring Data có thể xem object đó là mới và chọn insert. Nếu ID đã tồn tại, insert có thể thất bại do trùng khóa. Không nên chỉnh sửa version bằng tay.

### Entity có version nhưng version không khớp database

Nếu version trong object cũ hơn database, update không khớp điều kiện optimistic locking và phát sinh lỗi xung đột. Nếu version trong object lớn hơn hoặc không tồn tại ở database, thao tác cũng không tự chuyển sang insert.

### Entity bất biến

Với entity immutable, framework có thể tạo instance mới khi gán ID hoặc version. Vì vậy, luôn tiếp tục pipeline bằng entity trả về từ save() thay vì giả định object ban đầu đã được thay đổi tại chỗ.

### Nhiều repository hoặc nhiều ConnectionFactory

Optimistic locking chỉ có thể bảo vệ thao tác được thực hiện qua mapping và database có version tương ứng. Nếu một luồng ghi khác cập nhật trực tiếp cột dữ liệu nhưng không tăng version, cơ chế phát hiện xung đột có thể bị vô hiệu hóa. Mọi đường ghi vào bảng cần tuân thủ cùng quy ước version.

## 10. Xử lý lỗi optimistic locking trong reactive pipeline

Với R2DBC, thao tác save là reactive và lỗi thường được phát ra khi publisher được subscribe. Có thể chuyển lỗi optimistic locking thành phản hồi nghiệp vụ ở tầng service:

~~~java
public Mono<Customer> update(Customer customer) {
    return customerRepository.save(customer)
        .onErrorMap(
            OptimisticLockingFailureException.class,
            error -> new CustomerConflictException(
                "Customer was changed by another request",
                error
            )
        );
}
~~~

Tên exception nghiệp vụ trong ví dụ là kiểu do ứng dụng định nghĩa. Tầng web có thể ánh xạ lỗi này thành HTTP 409 Conflict nếu phù hợp với hợp đồng API.

Không nên tự động retry một update với cùng entity và cùng version cũ. Retry như vậy sẽ tiếp tục gửi điều kiện version không còn đúng. Nếu nghiệp vụ cho phép retry, cần tải trạng thái mới, áp dụng lại thay đổi theo quy tắc rõ ràng, rồi lưu entity có version mới.

Đối với thao tác gồm nhiều bước, có thể dùng reactive transaction để bảo đảm các bước database liên quan cùng commit hoặc rollback. Tuy nhiên, transaction không thay thế optimistic locking: transaction kiểm soát tính nguyên tử của nhóm thao tác, còn version phát hiện một thay đổi cạnh tranh trên entity.

## 11. Cách thiết kế cột version và quy trình lưu

Schema cần có cột version tương ứng với thuộc tính được đánh dấu @Version. Ví dụ:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    email VARCHAR(320) NOT NULL,
    version BIGINT NOT NULL
);
~~~

Chi tiết kiểu dữ liệu và giá trị mặc định phải phù hợp với database và cách Spring Data quản lý version. Nếu framework thiết lập version lúc insert, không nên để trigger hoặc logic khác tự tăng version ngoài quy ước mà ứng dụng đang dùng.

Một quy trình lưu thông thường:

1. Tạo entity mới với version chưa được thiết lập (nếu dùng wrapper nullable).
2. Gọi save() và tiếp tục bằng entity được trả về.
3. Khi đọc entity hiện có, giữ nguyên version đã tải.
4. Khi cập nhật, gửi lại entity với version cũ mà ứng dụng đã đọc.
5. Nếu cập nhật thành công, dùng version mới được trả về.
6. Nếu optimistic locking thất bại, tải lại dữ liệu và giải quyết xung đột theo nghiệp vụ.

Không nên lấy version từ client một cách thiếu kiểm soát. Nếu API cho phép client gửi version như một cơ chế concurrency token, cần xác thực và ánh xạ rõ ràng; không cho phép client tự đặt một version tùy ý để bỏ qua kiểm soát đồng thời.

## 12. Ghi nhớ

- save() cần biết entity mới hay đã tồn tại để chọn INSERT hoặc UPDATE.
- Nếu entity có @Version, Spring Data ưu tiên version property để xác định new state trước ID.
- Với version wrapper như Long, null biểu thị entity mới; giá trị khác null biểu thị entity hiện có.
- Với version primitive số nguyên như int hoặc long, giá trị mặc định 0 được xem là mới.
- Không có @Version thì Spring Data thường dựa vào ID; ID đã gán có thể khiến entity được xem là existing.
- Persistable.isNew() cho phép entity tự điều khiển new-state detection và được ưu tiên hơn chiến lược mặc định.
- Sau insert, version được khởi tạo; sau update thành công, version được tăng. Hãy dùng entity trả về từ save().
- Optimistic locking so sánh version hiện tại với version đã đọc; nếu không khớp, Spring Data báo lỗi thay vì âm thầm ghi đè thay đổi của request khác.
- ID xác định entity; version xác định phiên bản trạng thái của entity. Hai thuộc tính không thay thế nhau.
