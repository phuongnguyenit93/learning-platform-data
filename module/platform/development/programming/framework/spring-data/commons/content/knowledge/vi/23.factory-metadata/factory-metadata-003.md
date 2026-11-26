# EntityInformation và thông tin kiểu miền, ID, trạng thái mới

Repository cần hiểu nhiều hơn tên của một lớp Java. Nó cần biết kiểu miền đang quản lý, kiểu định danh, cách lấy ID từ một đối tượng và cách xác định đối tượng đó được coi là mới hay không. Spring Data Commons tập hợp những thông tin này qua abstraction `EntityInformation<T, ID>`.

Metadata này được repository infrastructure sử dụng để thực hiện các thao tác phù hợp với store. Đặc biệt, kết quả `isNew(entity)` có thể ảnh hưởng trực tiếp đến nhánh xử lý của `save(...)`. Tuy nhiên, “được coi là mới” không đồng nghĩa với “đã kiểm tra và chắc chắn chưa tồn tại trong database”.

Bài học phân biệt hợp đồng chung với các chiến lược của từng module, đồng thời minh họa cách ID, version và `Persistable` tham gia việc xác định trạng thái mới.

## 1. EntityInformation đứng ở đâu trong hạ tầng repository?

Khi tạo một repository, factory của module cần kết hợp thông tin khai báo trên repository với mapping của domain type. Implementation repository sau đó có thể dùng entity information để xử lý từng đối tượng cụ thể.

```text
Repository interface với kiểu T và ID
                |
                v
Repository factory của module
                |
                +--> Metadata của repository
                +--> Mapping metadata của domain type
                |
                v
EntityInformation<T, ID>
                |
                +--> Kiểu Java của miền
                +--> Kiểu và giá trị ID
                +--> Quyết định trạng thái mới
                |
                v
Implementation thao tác với store
```

Sơ đồ thể hiện vai trò, không khẳng định mọi module có cùng lớp implementation hoặc cùng thuật toán lưu. Commons định nghĩa abstraction; JPA, MongoDB và các module khác cung cấp cách tích hợp với metadata cùng cơ chế truy cập dữ liệu của chúng.

Trong code ứng dụng thông thường, không cần tự tạo entity information cho mọi entity. Factory của module quản lý phần này. Hiểu abstraction giúp giải thích hành vi repository và xây phần mở rộng khi thực sự cần.

## 2. Những phương thức cốt lõi

Interface nằm trong package:

```java
import org.springframework.data.repository.core.EntityInformation;
```

Nó mở rộng `EntityMetadata<T>`, từ đó có thông tin kiểu Java của domain type. Các phương thức cần nắm gồm:

| Phương thức | Thông tin cung cấp | Điểm cần lưu ý |
| --- | --- | --- |
| `getJavaType()` | `Class<T>` của kiểu miền | Không phải lúc nào cũng trùng với runtime class của một proxy |
| `getIdType()` | `Class<ID>` của kiểu định danh Java | Không mô tả toàn bộ cách ID được biểu diễn trong database |
| `getId(entity)` | Giá trị ID của đối tượng | Có thể trả null nếu đối tượng chưa có ID |
| `getRequiredId(entity)` | ID bắt buộc phải có | Báo lỗi nếu không lấy được ID khác null |
| `isNew(entity)` | Đối tượng có được coi là mới theo chiến lược đang dùng không | Không phải lời gọi kiểm tra sự tồn tại trong store |

`getRequiredId(...)` biểu đạt yêu cầu mạnh hơn `getId(...)`: nếu ID là null, nó ném `IllegalArgumentException` thay vì trả một giá trị nullable.

### ID chưa có có thể là trạng thái hợp lệ

Một entity sử dụng định danh được sinh khi lưu có thể chưa có ID trước thao tác ghi. Trong trạng thái đó:

```text
getId(entity)         -> null
getRequiredId(entity) -> lỗi vì yêu cầu ID bắt buộc chưa được đáp ứng
```

Không kết luận mapping hỏng chỉ vì ID null ở một thời điểm mà cơ chế sinh ID chưa hoạt động. Cũng không gọi `getRequiredId(...)` quá sớm rồi sửa bằng cách tự tạo một ID không phù hợp với chiến lược định danh.

### Kiểu Java khác với biểu diễn lưu trữ

`getIdType()` cho biết kiểu ID trong mô hình Java. Một store có thể dùng conversion hoặc mapping để biểu diễn giá trị đó theo kiểu khác ở phía lưu trữ.

Vì vậy, không lấy `getIdType()` làm bằng chứng rằng tên cột, kiểu SQL hoặc dạng BSON của ID chắc chắn giống hệt kiểu Java. Đối với định danh tổng hợp, kiểu Java có thể là một lớp ID riêng, không phải chuỗi được ghép thủ công từ các thành phần.

## 3. Phân biệt các lớp metadata liên quan

Các abstraction có tên gần nhau nhưng trả lời những câu hỏi khác nhau:

| Abstraction | Câu hỏi chính |
| --- | --- |
| `RepositoryMetadata` | Repository này quản lý domain type và ID type nào theo khai báo của nó? |
| `EntityMetadata<T>` | Kiểu Java của đối tượng miền là gì? |
| `EntityInformation<T, ID>` | Với đối tượng này, ID là gì và nó được coi là mới hay không? |
| Mapping metadata như `PersistentEntity` | Những thuộc tính nào được ánh xạ, đâu là ID, version và các đặc điểm lưu trữ khác? |
| Metadata chuyên biệt của store | Store cần thêm thông tin gì để nhận diện hoặc lưu entity? |

Thông tin khai báo trên generic repository và mapping thực tế phải nhất quán. Ví dụ, nếu entity có ID kiểu `Long` nhưng repository được khai báo với ID kiểu `String`, compiler không tự đối chiếu mọi annotation mapping để chứng minh cấu hình là đúng. Mức độ phát hiện và thời điểm báo lỗi phụ thuộc module.

`EntityInformation` cũng không bắt buộc ID phải nằm trong thuộc tính có tên đúng là `id`. Một entity có thể dùng thuộc tính `customerNumber` làm định danh. Cách tìm định danh phải dựa trên metadata hoặc implementation phù hợp, không chỉ tìm một field bằng tên cố định.

## 4. Ví dụ Commons: tách metadata khỏi một đối tượng cụ thể

Để quan sát chiến lược dựa trên ID, có thể dùng `AbstractEntityInformation`. Đây là ví dụ về abstraction Commons, không phải cấu hình thay thế cho metadata JPA của ứng dụng.

Mô hình Java đơn giản:

```java
public final class Customer {

    private final Long customerNumber;
    private final String displayName;

    public Customer(Long customerNumber, String displayName) {
        this.customerNumber = customerNumber;
        this.displayName = displayName;
    }

    public Long getCustomerNumber() {
        return customerNumber;
    }

    public String getDisplayName() {
        return displayName;
    }
}
```

Implementation metadata:

```java
import org.springframework.data.repository.core.support.AbstractEntityInformation;

public final class CustomerInformation
        extends AbstractEntityInformation<Customer, Long> {

    public CustomerInformation() {
        super(Customer.class);
    }

    @Override
    public Long getId(Customer entity) {
        return entity.getCustomerNumber();
    }

    @Override
    public Class<Long> getIdType() {
        return Long.class;
    }
}
```

Cách sử dụng:

```java
import org.springframework.data.repository.core.EntityInformation;

EntityInformation<Customer, Long> information = new CustomerInformation();

Customer withoutId = new Customer(null, "Linh");
Customer withId = new Customer(42L, "Mai");

Class<Customer> domainType = information.getJavaType();
Class<Long> idType = information.getIdType();

Long missingId = information.getId(withoutId);
Long presentId = information.getRequiredId(withId);

boolean firstIsNew = information.isNew(withoutId);
boolean secondIsNew = information.isNew(withId);
```

Theo chiến lược ID mặc định của lớp cơ sở trong ví dụ:

```text
domainType  = Customer.class
idType      = Long.class
missingId   = null
presentId   = 42
firstIsNew  = true
secondIsNew = false
```

Không có dữ liệu nào ở đây chứng minh một khách hàng mang ID 42 đã tồn tại trong kho dữ liệu. Kết quả chỉ phản ánh trạng thái được suy ra từ ID theo implementation đang dùng.

Việc tạo `CustomerInformation` trong ví dụ cũng không tự đăng ký nó với repository factory. Thay đổi cách một repository thực tế lấy metadata cần dùng cơ chế mở rộng phù hợp của module, không chỉ tạo một bean hoặc một lớp cùng tên.

## 5. Chiến lược dựa trên ID và các giá trị mặc định

Trong chiến lược ID cơ sở của `AbstractEntityInformation`, ID tham chiếu null biểu diễn trạng thái mới. Với ID số primitive được hỗ trợ, giá trị 0 được dùng để nhận diện trạng thái mới.

Phải phân biệt primitive và wrapper:

| Kiểu ID và giá trị | Kết quả trong chiến lược ID cơ sở | Lý do |
| --- | --- | --- |
| `Long`, giá trị null | Mới | Chưa có ID tham chiếu |
| `Long`, giá trị `0L` | Không mới | Wrapper khác null |
| `Long`, giá trị `42L` | Không mới | Đã có ID tham chiếu |
| `String`, giá trị null | Mới | Chưa có ID tham chiếu |
| `String`, giá trị `""` | Không mới | Chuỗi rỗng vẫn khác null |
| `long`, giá trị 0 | Mới | Giá trị mặc định theo chiến lược cho ID số primitive |
| `long`, giá trị 42 | Không mới | Khác giá trị mặc định dùng để nhận diện mới |

Bảng này không phải thuật toán bắt buộc cho mọi store. Module có thể dùng version, `Persistable` hoặc cơ chế metadata khác trước khi đi tới quy tắc dựa trên ID.

Đặc biệt, “không mới” không có nghĩa ID hợp lệ về nghiệp vụ. Chuỗi rỗng hay số âm vẫn có thể là ID không được ứng dụng chấp nhận dù chiến lược metadata không coi chúng là vắng mặt. Validation định danh và quyết định trạng thái mới là hai trách nhiệm khác nhau.

### ID do ứng dụng gán trước

Ví dụ ứng dụng tạo một UUID hoặc mã nghiệp vụ trước lần lưu đầu tiên:

```text
Đối tượng vừa được tạo trong bộ nhớ
ID đã được ứng dụng gán
Chưa từng được ghi vào database
```

Một chiến lược chỉ dựa trên ID có thể coi đối tượng này là không mới. Đó không phải nghịch lý: chiến lược đang suy ra trạng thái từ ID, không ghi nhớ lịch sử tồn tại của đối tượng.

Khi dùng assigned ID, cần chọn chiến lược nhận diện phù hợp với store và vòng đời đối tượng. Không tự đổi ID về null chỉ để ép repository đi vào một nhánh ghi khác.

## 6. JPA: version có thể quyết định trạng thái mới

Spring Data JPA có metadata chuyên biệt như `JpaMetamodelEntityInformation`. Với cách nhận diện mặc định của JPA và entity không tự cung cấp `Persistable.isNew()`, một thuộc tính version kiểu tham chiếu có thể được dùng trước ID để xác định trạng thái mới.

Ví dụ:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class VersionedCustomer {

    @Id
    private String id;

    @Version
    private Long version;

    protected VersionedCustomer() {
    }

    public VersionedCustomer(String id) {
        this.id = id;
    }

    public String getId() { return id; }
    public Long getVersion() { return version; }
}
```

Entity sử dụng ID do ứng dụng gán nhưng version ban đầu là null. Với chiến lược JPA nêu trên:

| Trạng thái | Quyết định mới |
| --- | --- |
| ID đã có, `Long version == null` | Có thể được nhận diện là mới theo version |
| ID đã có, `Long version == 0L` | Không mới theo kiểm tra version null |
| ID đã có, `Long version > 0` | Không mới theo kiểm tra version null |

Không tự khởi tạo wrapper version bằng 0 nếu dự định dựa vào null để biểu diễn trạng thái chưa lưu. Version còn phục vụ optimistic locking; không nên chỉnh nó chỉ để điều khiển nhánh của `save`.

### Primitive version không có cùng cách xử lý

Một thuộc tính `long version` không thể nhận null và giá trị 0 có thể là một version hợp lệ của entity đã được lưu. Với metadata JPA mặc định tương ứng, primitive version không được dùng theo quy tắc kiểm tra null như wrapper; hạ tầng có thể quay về kiểm tra ID.

Vì vậy, đổi `Long` thành `long` không chỉ là thay đổi cách biểu diễn Java. Nó có thể làm thay đổi chiến lược nhận diện entity mới.

Không áp nguyên bảng JPA này cho một document store. Annotation version và thuật toán nhận diện của module khác có thể khác; phải dùng hợp đồng của store đang chạy.

## 7. `Persistable`: entity cung cấp quyết định mới

Commons định nghĩa interface:

```java
import org.springframework.data.domain.Persistable;
```

Các phương thức quan trọng là:

```text
getId()
isNew()
```

Trong module hỗ trợ chiến lược này, entity triển khai `Persistable<ID>` có thể tự cung cấp trạng thái mới. Với JPA, metadata dành cho entity kiểu này sử dụng quyết định `isNew()` của entity thay vì chỉ suy ra từ ID hoặc version theo cách mặc định ở phần trước.

Một mẫu JPA cho assigned ID:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.PostLoad;
import jakarta.persistence.PostPersist;
import jakarta.persistence.Transient;
import org.springframework.data.domain.Persistable;

@Entity
public class AssignedCustomer implements Persistable<String> {

    @Id
    private String id;

    @Transient
    private boolean newEntity = true;

    protected AssignedCustomer() {
    }

    public AssignedCustomer(String id) {
        if (id == null || id.trim().isEmpty()) {
            throw new IllegalArgumentException("ID không được trống");
        }
        this.id = id;
    }

    @Override
    public String getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }

    @PostPersist
    @PostLoad
    protected void markNotNew() {
        this.newEntity = false;
    }
}
```

Ý định của mẫu:

1. Đối tượng do ứng dụng tạo bắt đầu với cờ mới bằng true, dù ID đã được gán.
2. Sau callback persist hoặc load của JPA, cờ chuyển thành false.
3. Cờ là trạng thái phục vụ vòng đời đối tượng, không phải một cột nghiệp vụ.

Ví dụ dùng field access của JPA; `@Transient` trên field loại cờ khỏi mapping tương ứng. Nếu đổi sang property access hoặc store khác, phải đặt cấu hình loại thuộc tính khỏi persistence theo cơ chế đó. Không mặc định một annotation transient của JPA có hiệu lực giống hệt trên mọi store.

### `Persistable` không tự quản lý toàn bộ vòng đời

Interface không tự lật cờ sau khi lưu. Trong mẫu, việc đó do callback JPA đảm nhiệm. Nếu dùng MongoDB hoặc một module khác, cần cơ chế callback và vòng đời của module đó; annotation `@PostLoad` của JPA không tự trở thành callback dùng chung của Commons.

Cũng phải xét các tình huống như:

- Đối tượng được tái tạo từ một thông điệp có sẵn ID nhưng không đi qua callback load.
- Một lần ghi thất bại hoặc giao dịch rollback sau khi trạng thái trong bộ nhớ đã thay đổi.
- Một instance cũ được tái sử dụng cho một yêu cầu mới.

Cờ isNew không phải lịch sử giao dịch bền vững. Sau một lần ghi lỗi, không suy ra trạng thái database chỉ từ cờ còn lại trong bộ nhớ. Cần xử lý lại vòng đời đối tượng theo trường hợp sử dụng.

Không coi giá trị cờ do người gọi bên ngoài tự khai báo là căn cứ đáng tin để quyết định tạo mới hay cập nhật. Chiến lược này cần thuộc thiết kế domain và persistence của ứng dụng.

## 8. `isNew` ảnh hưởng đến save như thế nào?

Đối với implementation repository JPA thông thường, có thể mô tả nhánh chính bằng mã rút gọn:

```java
if (entityInformation.isNew(entity)) {
    entityManager.persist(entity);
    return entity;
}

return entityManager.merge(entity);
```

Đây là minh họa quyết định nhánh, không phải toàn bộ source của phương thức `save`. Cấu hình transaction, validation và các chi tiết implementation khác không được thể hiện.

Cần phân biệt cặp khái niệm:

```text
isNew true / false
        không đồng nhất với
chắc chắn INSERT / chắc chắn UPDATE
```

Trong JPA:

- `persist` đưa đối tượng vào luồng persistence cho entity mới; SQL có thể chỉ được thực thi khi flush hoặc ở thời điểm do provider quyết định.
- `merge` có thể sao chép trạng thái sang một instance managed khác; không phải một cam kết rằng chỉ một câu UPDATE sẽ chạy.
- ID đã có nhưng bản ghi chưa tồn tại không làm kiểm tra isNew tự biến thành phép dò database.
- Metadata cho rằng entity mới vẫn không bảo đảm thao tác ghi thành công nếu vi phạm khóa hoặc ràng buộc.

Vì `merge` có thể trả về instance khác, cần dùng kết quả của `save` khi xử lý tiếp:

```java
CustomerEntity saved = repository.save(entity);
```

`CustomerEntity` trong đoạn minh họa là domain type do repository thực tế quản lý. Không giả định object đầu vào luôn là instance chứa đầy đủ trạng thái ID, version hoặc các giá trị được hạ tầng cập nhật.

### Store khác có nhánh ghi khác

Một document repository có thể dùng quyết định mới để chọn giữa luồng insert và save theo cơ chế document store. Module khác có thể làm việc với aggregate hoặc chiến lược ghi riêng.

Không mang trực tiếp mô hình `persist`/`merge` của JPA sang mọi Spring Data repository. Điều dùng chung là vai trò của metadata; thao tác backend do implementation quyết định.

## 9. Những điều không thể suy ra từ EntityInformation

### 9.1. Không tự xác minh sự tồn tại

`isNew(entity) == false` không phải kết quả của `existsById(id)`. Một object vừa được tạo có ID được gán sẵn vẫn có thể được coi là không mới theo chiến lược ID.

Ngược lại, `isNew(entity) == true` không có nghĩa ID chắc chắn chưa bị một đối tượng khác sử dụng trong database.

Nếu thực sự gọi `existsById` trước thao tác ghi, khoảng thời gian giữa hai thao tác vẫn có thể có thay đổi đồng thời. Kiểm tra tồn tại không thay thế ràng buộc dữ liệu hay cơ chế giao dịch phù hợp.

### 9.2. Không cấp quyền ghi

Có ID, có version hoặc có kết quả isNew phù hợp không chứng minh người gọi được phép tạo hay sửa đối tượng. Quyền truy cập, phạm vi tenant và các bất biến nghiệp vụ thuộc luồng xử lý của ứng dụng.

Tương tự, một probe QBE có thể cùng kiểu entity nhưng chỉ chứa giá trị tìm kiếm. Metadata có thể đọc ID và trả isNew cho nó, nhưng điều đó không biến probe thành đối tượng hợp lệ để ghi.

### 9.3. Không kiểm tra tính đầy đủ của entity

Entity có thể thiếu trường bắt buộc, sai định dạng mã hoặc có quan hệ chưa hợp lệ. `getId` và `isNew` không phải bộ validation chung cho toàn bộ domain model.

### 9.4. Không tự cung cấp auditing hay optimistic locking

Metadata có thể đọc version phục vụ một chiến lược, nhưng chỉ có phương thức `isNew` không tự kích hoạt optimistic locking. Store phải được cấu hình hỗ trợ version đúng cách.

Các thuộc tính auditing như ngày tạo, người tạo hoặc ngày sửa cũng không tự trở thành bằng chứng trạng thái mới theo mọi implementation. Không thay thế chiến lược của module bằng suy luận rằng có ngày tạo thì chắc chắn đã lưu.

## 10. Những tình huống ID và kiểu miền dễ nhầm

| Tình huống | Cách hiểu phù hợp |
| --- | --- |
| Runtime object là proxy của JPA | `getJavaType()` thể hiện domain type do metadata quản lý; không chỉ dựa vào `entity.getClass()` |
| ID property tên `customerNumber` | Lấy ID qua mapping hoặc metadata, không tìm field tên `id` bằng giả định |
| ID tổng hợp | Dùng kiểu và cách lấy ID mà module quy định; không ép thành chuỗi ghép |
| ID Java là String nhưng store có conversion | Kiểu Java không mô tả toàn bộ kiểu lưu trữ vật lý |
| Repository khai báo sai generic ID | Generic và mapping phải được đối chiếu, không dựa vào việc code interface vẫn biên dịch |
| Entity có ID do ứng dụng gán trước | Cần chiến lược mới phù hợp; không đồng nhất có ID với đã tồn tại |
| Wrapper version bị đặt 0 ngay khi tạo | Có thể làm mất tín hiệu null dùng để nhận diện mới trong chiến lược JPA tương ứng |
| Entity triển khai Persistable | Phải quản lý isNew theo vòng đời phù hợp, không chỉ thêm interface rồi luôn trả true |

Đặc biệt, `isNew()` luôn trả true có thể khiến các lần lưu tiếp theo liên tục đi vào luồng tạo mới. Luôn trả false cũng không bảo đảm một entity chưa lưu sẽ được xử lý đúng trong mọi backend. Giá trị trả về phải phản ánh chiến lược đã được thiết kế, không phải mẹo để ép một lần ghi cụ thể.

## 11. Chẩn đoán hành vi lưu ngoài dự định

Khi repository chọn nhánh xử lý khác mong đợi, nên đối chiếu theo thứ tự:

1. Repository factory của module đang dùng implementation metadata nào?
2. Domain type và ID type thực tế có khớp với repository không?
3. `getId(entity)` đang cho giá trị gì tại thời điểm gọi save?
4. Entity có thuộc tính version được module nhận diện không, và đó là primitive hay wrapper?
5. Entity có triển khai `Persistable` hoặc sử dụng chiến lược mới tùy chỉnh không?
6. Object có thực sự đi qua các callback vòng đời mà cờ trạng thái đang dựa vào không?
7. Trạng thái database, ràng buộc và giao dịch thực tế có phù hợp với ý định ghi không?

Các lỗi có thể biểu hiện như:

| Biểu hiện | Nguyên nhân cần xem xét |
| --- | --- |
| Entity mới có assigned ID đi vào nhánh merge của JPA | Đang dùng chiến lược dựa trên ID, không có tín hiệu mới khác phù hợp |
| Entity đã tồn tại bị coi là mới | Version null, cờ Persistable chưa đổi hoặc đối tượng bị tái tạo sai vòng đời |
| Wrapper ID bằng 0 được coi là không mới | Đang áp quy tắc khác null cho ID tham chiếu |
| `getRequiredId` thất bại trước lần lưu đầu | Định danh chưa được sinh tại thời điểm yêu cầu |
| Lưu thất bại sau khi nhận diện mới | Ràng buộc, mapping hoặc trạng thái database không được isNew xác minh |
| ID hoặc version đọc từ object đầu vào không như mong đợi | Cần sử dụng kết quả save và hiểu cơ chế trả instance của store |
| Thêm một lớp EntityInformation nhưng repository không đổi hành vi | Lớp đó chưa được factory sử dụng qua cơ chế mở rộng tương ứng |

Không sửa bằng cách thay ngẫu nhiên ID, xóa version hoặc bắt mọi lỗi persistence rồi thử một nhánh khác. Cần xác định chiến lược đang hoạt động và điều chỉnh thiết kế vòng đời hoặc cấu hình đúng nơi.

## 12. Tự thực hành đối chiếu chiến lược

Có thể sử dụng các mô hình minh họa để lần lượt quan sát:

| Tình huống | Điều cần xác nhận |
| --- | --- |
| POJO với CustomerInformation và ID null | Metadata lấy đúng domain type, ID type và nhận diện mới theo ID |
| Cùng POJO có ID 42 nhưng chưa có bản ghi tương ứng | isNew không tự kiểm tra tồn tại trong database |
| ID wrapper bằng 0 so với primitive bằng 0 | Phân biệt được hai quy tắc giá trị mặc định |
| Entity JPA có assigned ID và wrapper version null | Hiểu vì sao chiến lược version có thể nhận diện entity mới |
| Đổi wrapper version thành primitive | Không tiếp tục áp giả định kiểm tra version null |
| Entity JPA triển khai Persistable | isNew của entity và callback thực sự điều khiển trạng thái như thiết kế |
| Đọc lại entity từ store | Trạng thái ID, version và cờ vòng đời phù hợp với lần đọc |
| Một lần ghi bị rollback | Không coi cờ trong bộ nhớ là bằng chứng giao dịch đã thành công |
| Domain type dùng ID tổng hợp | Metadata trả đúng kiểu ID theo mapping của module |

`EntityInformation` cung cấp cầu nối từ một entity cụ thể tới thông tin mà repository cần để xử lý nó. Để dùng đúng, cần giữ rõ ba điều: kiểu miền và ID lấy từ metadata nào, trạng thái mới được xác định theo chiến lược nào, và store dùng quyết định đó để thực hiện thao tác gì. Không một giá trị ID hay boolean isNew riêng lẻ nào thay thế được sự tồn tại thực tế, quyền ghi và các quy tắc dữ liệu của ứng dụng.