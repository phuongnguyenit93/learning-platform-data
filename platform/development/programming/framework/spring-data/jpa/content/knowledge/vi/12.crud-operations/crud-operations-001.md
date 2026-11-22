# save và cách lựa chọn persist hoặc merge trong Spring Data JPA

## 1. save() thực sự làm gì?

Trong Spring Data JPA, repository thường kế thừa `JpaRepository` hoặc `CrudRepository`, vì vậy có sẵn phương thức `save(entity)` để lưu một entity. Tuy nhiên, `save()` không phải một câu lệnh SQL cố định và cũng không có nghĩa là luôn chạy INSERT hoặc luôn chạy UPDATE.

Trong triển khai repository JPA mặc định (`SimpleJpaRepository`), luồng xử lý cốt lõi là:

~~~java
if (entityInformation.isNew(entity)) {
    entityManager.persist(entity);
    return entity;
} else {
    return entityManager.merge(entity);
}
~~~

Có thể hiểu:

- Nếu Spring Data JPA nhận diện entity là **mới**, `save()` gọi `EntityManager.persist()`.
- Nếu entity được nhận diện là **đã tồn tại**, `save()` gọi `EntityManager.merge()`.
- `save()` trả về đối tượng cần tiếp tục sử dụng. Đặc biệt với nhánh `merge`, phải dùng đối tượng trả về vì nó là instance managed mà JPA trả lại.

Vì thế, để hiểu `save()`, cần hiểu hai thao tác `persist` và `merge` của JPA, đồng thời biết Spring Data JPA quyết định entity mới bằng cách nào.

## 2. Entity state: new, managed, detached và removed

JPA quản lý entity thông qua persistence context. Một entity thường ở một trong các trạng thái sau:

| Trạng thái | Ý nghĩa |
|---|---|
| **New / transient** | Đối tượng vừa được tạo trong Java, chưa được persistence context quản lý và chưa được lưu như một entity trong database |
| **Managed / persistent** | Đối tượng đang được persistence context quản lý; thay đổi thuộc tính có thể được ghi xuống database khi flush |
| **Detached** | Entity từng được quản lý nhưng hiện không còn nằm trong persistence context; thay đổi của nó không tự động được theo dõi |
| **Removed** | Entity đang được persistence context đánh dấu để xóa; DELETE được đồng bộ khi flush |

Ví dụ:

~~~java
Customer customer = new Customer("An");
// customer đang ở trạng thái new

entityManager.persist(customer);
// customer trở thành managed

entityManager.detach(customer);
// customer trở thành detached

entityManager.remove(entityManager.merge(customer));
// instance được merge trở thành managed rồi bị đánh dấu removed
~~~

Đoạn cuối chỉ minh họa các trạng thái. Trong ứng dụng thực tế, cần quản lý transaction và tránh gọi các thao tác vòng đời không cần thiết. `remove()` yêu cầu đối tượng managed; vì vậy ví dụ merge trước khi remove.

Một điểm quan trọng: entity detached vẫn là một object Java bình thường và có thể chứa dữ liệu. Nhưng JPA không còn tự theo dõi thay đổi của object đó cho tới khi nó được merge vào một persistence context.

## 3. persist(): đưa entity mới vào persistence context

`EntityManager.persist(entity)` dùng để đăng ký một entity mới vào persistence context hiện tại.

~~~java
Customer customer = new Customer("An");

entityManager.persist(customer);

// customer hiện là managed
~~~

Sau `persist()`:

- Đối tượng được truyền vào trở thành managed trong persistence context.
- Provider sẽ lập kế hoạch INSERT khi đồng bộ dữ liệu.
- Câu lệnh SQL có thể được gửi ngay hoặc trì hoãn tới flush/commit, tùy chiến lược sinh khóa và provider.
- Các thay đổi tiếp theo trên chính object managed được JPA theo dõi bằng dirty checking.

`persist()` có kiểu trả về `void`; nó không tạo một bản sao managed để trả về. Đối tượng được truyền vào chính là entity được quản lý.

### Khi nào persist phù hợp?

Dùng `persist()` khi tạo entity mới và muốn bắt đầu quản lý nó trong persistence context:

~~~java
@Transactional
public Customer createCustomer(String name) {
    Customer customer = new Customer(name);
    entityManager.persist(customer);
    return customer;
}
~~~

Không nên gọi `persist()` cho một entity detached với ý định cập nhật nó. Theo JPA, persist áp dụng cho entity mới; truyền một entity detached có thể dẫn đến exception, ngay lập tức hoặc trong quá trình flush.

Nếu entity đã managed trong persistence context, gọi `persist()` lại trên entity đó không biến nó thành một object khác và thường không tạo thêm bản ghi. Tuy nhiên, không cần gọi lặp lại thao tác này.

## 4. merge(): sao chép trạng thái vào một entity managed

`EntityManager.merge(entity)` dùng để đưa trạng thái của một entity new hoặc detached vào persistence context hiện tại.

Điểm quan trọng nhất của `merge()` là **đối tượng được truyền vào không nhất thiết trở thành managed**. JPA trả về một instance managed có trạng thái được đồng bộ từ object nguồn.

~~~java
Customer detached = receiveCustomerFromAnotherLayer();

Customer managed = entityManager.merge(detached);

// managed là instance được persistence context quản lý.
// detached vẫn là object nguồn và vẫn detached.
~~~

Có ba trường hợp cần phân biệt:

1. **Đối tượng detached:** JPA tìm hoặc lấy một instance managed tương ứng với định danh, sau đó sao chép trạng thái từ detached object vào instance managed và trả về instance managed đó.
2. **Đối tượng new:** JPA tạo một instance managed mới và sao chép trạng thái từ object nguồn vào instance đó. Tùy trạng thái và mapping, INSERT sẽ được thực hiện khi flush.
3. **Đối tượng đã managed:** thao tác merge trả về chính instance managed tương ứng; không cần merge để tiếp tục theo dõi các thay đổi vốn đã được persistence context quản lý.

Ví dụ minh họa:

~~~java
Customer source = new Customer("Binh");
Customer managed = entityManager.merge(source);

source.setName("Chi");
managed.setName("Dung");
~~~

Sau khi merge, thay đổi `source.setName("Chi")` không tự động được theo dõi vì `source` vẫn là object nguồn không managed. Thay đổi `managed.setName("Dung")` được persistence context theo dõi và có thể được ghi xuống database khi flush.

### merge không phải SQL MERGE hoặc upsert

Tên `merge()` dễ khiến người mới nghĩ đây là câu lệnh SQL `MERGE`, hoặc luôn có hành vi “có thì UPDATE, không có thì INSERT” dựa trên một câu lệnh database duy nhất.

Thực tế, đây là thao tác trong vòng đời entity của JPA. Provider xác định instance managed, sao chép trạng thái và lên kế hoạch SQL phù hợp. Nó không đồng nghĩa với câu lệnh SQL `MERGE`, cũng không phải cam kết rằng database luôn thực hiện một thao tác upsert nguyên tử.

Nếu một object mang ID nhưng bản ghi tương ứng không còn trong database, hành vi merge có thể dẫn tới INSERT hoặc lỗi tùy trạng thái, mapping và provider. Không nên dựa vào ID đơn thuần để suy luận chắc chắn câu SQL sẽ chạy.

## 5. Spring Data JPA nhận diện entity mới như thế nào?

`save()` cần quyết định gọi `persist()` hay `merge()`. Quyết định đó dựa trên `EntityInformation.isNew(entity)`.

Với cấu hình mặc định, Spring Data JPA thường nhận diện trạng thái mới theo thứ tự sau:

1. Nếu entity triển khai `Persistable`, Spring Data gọi `isNew()` của entity.
2. Nếu entity không triển khai `Persistable` và có thuộc tính `@Version` không phải kiểu primitive, giá trị version `null` được xem là entity mới.
3. Nếu không có version property phù hợp, Spring Data kiểm tra thuộc tính ID: ID `null` được xem là mới; ID khác `null` được xem là đã tồn tại.

Cơ chế version trước ID giúp xử lý entity dùng ID được gán thủ công: một entity có ID ngay từ lúc tạo vẫn có thể được nhận diện là mới nếu version object còn `null`.

### 5.1. Nhận diện bằng ID

Ví dụ entity dùng khóa chính tự sinh:

~~~java
@Entity
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Customer() {}

    public Customer(String name) {
        this.name = name;
    }
}
~~~

Với entity này, ID thường là `null` khi mới tạo. Spring Data nhận diện entity là mới và gọi `persist()`.

Sau khi entity đã được lưu và có ID, lần gọi `save()` tiếp theo thường đi vào nhánh `merge()` nếu không có version property hoặc cơ chế nhận diện khác.

### 5.2. Nhận diện bằng @Version

Nếu entity có version property không phải kiểu primitive, Spring Data kiểm tra version trước ID:

~~~java
@Entity
public class Product {
    @Id
    private UUID id;

    @Version
    private Long version;

    private String name;

    protected Product() {}

    public Product(UUID id, String name) {
        this.id = id;
        this.name = name;
    }
}
~~~

Khi tạo `Product` với ID được gán trước nhưng `version == null`, Spring Data có thể nhận diện entity là mới và chọn `persist()`.

Sau khi lưu, provider gán version ban đầu theo cơ chế optimistic locking. Khi entity được tải lại hoặc có version khác `null`, entity thường được nhận diện là đã tồn tại.

`@Version` còn có tác dụng kiểm soát cập nhật đồng thời: khi hai transaction cùng cập nhật một entity, version giúp phát hiện một transaction đang ghi trên dữ liệu đã cũ. Đây là một lợi ích độc lập với vai trò hỗ trợ nhận diện entity mới.

Lưu ý: thuộc tính version kiểu primitive như `long` không thể có giá trị `null`, nên không dùng được quy tắc kiểm tra null như ví dụ `Long` ở trên.

### 5.3. Tùy chỉnh bằng Persistable

Nếu ứng dụng dùng ID được gán thủ công và không có version property phù hợp, quy tắc ID null có thể không phản ánh đúng trạng thái mới. Có thể triển khai `Persistable<ID>` để tự quyết định:

~~~java
@Entity
public class ImportedCustomer implements Persistable<String> {
    @Id
    private String id;

    private String name;

    @Transient
    private boolean newEntity = true;

    protected ImportedCustomer() {}

    public ImportedCustomer(String id, String name) {
        this.id = id;
        this.name = name;
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
    void markNotNew() {
        this.newEntity = false;
    }
}
~~~

Trong ví dụ, `newEntity` không được lưu vào database vì có `@Transient`. Sau khi persist thành công hoặc load entity từ database, callback đánh dấu entity không còn mới.

Đây là mẫu triển khai cần được kiểm thử theo vòng đời thực tế của ứng dụng, đặc biệt khi entity được deserialize, tái tạo từ DTO hoặc được tạo lại trong một request khác. Không nên dùng một cờ `isNew` tùy tiện mà không xác định lúc nào nó chuyển sang `false`.

## 6. So sánh persist và merge

| Tiêu chí | `persist(entity)` | `merge(entity)` |
|---|---|---|
| Mục đích | Đưa entity mới vào persistence context | Sao chép trạng thái entity new/detached vào persistence context |
| Đối tượng nguồn | Thường là entity new | Entity new hoặc detached; entity managed cũng có thể được truyền |
| Đối tượng trở thành managed | Chính object được truyền vào | Instance được trả về từ `merge()` |
| Giá trị trả về | `void` | Instance managed |
| Dùng để cập nhật entity detached? | Không | Có |
| Entity detached được truyền vào | Không hợp lệ cho thao tác persist | Có thể merge trạng thái vào instance managed |
| SQL chạy lúc nào? | Khi provider đồng bộ, có thể ngay hoặc khi flush/commit | Khi provider đồng bộ, có thể ngay hoặc khi flush/commit |
| Cascade liên quan | `CascadeType.PERSIST` hoặc `ALL` | `CascadeType.MERGE` hoặc `ALL` |

Quy tắc thực hành:

- Tạo entity mới và đưa nó vào persistence context → `persist()`.
- Có entity detached và muốn sao chép trạng thái của object nguồn vào persistence context → `merge()`.
- Entity đã managed trong transaction → thay đổi thuộc tính trực tiếp; dirty checking sẽ ghi nhận thay đổi khi flush.

## 7. Dùng repository save() đúng cách

Trong ứng dụng Spring Data JPA, service thường gọi repository thay vì thao tác trực tiếp với `EntityManager`.

### 7.1. Tạo mới

~~~java
@Service
public class CustomerService {
    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Customer create(String name) {
        Customer customer = new Customer(name);
        return repository.save(customer);
    }
}
~~~

Entity mới có ID `null`, do đó Spring Data thường chọn `persist()` theo chiến lược nhận diện mặc định. Repository trả lại entity đã được lưu/đưa vào persistence context.

### 7.2. Cập nhật entity đã tải trong transaction

Cách thường dễ kiểm soát nhất là tải entity managed, sau đó thay đổi những thuộc tính được phép:

~~~java
@Transactional
public Customer rename(Long id, String newName) {
    Customer customer = repository.findById(id)
        .orElseThrow(() -> new EntityNotFoundException("Customer not found"));

    customer.setName(newName);

    return customer;
}
~~~

`customer` được tải trong transaction và đang managed. Khi thuộc tính thay đổi, JPA dirty checking phát hiện khác biệt và ghi UPDATE khi flush. Không cần gọi `repository.save(customer)` thêm lần nữa để JPA theo dõi thay đổi.

Nếu muốn gọi `save()` vì quy ước của lớp service hoặc repository abstraction, kết quả vẫn cần được dùng đúng cách. Tuy nhiên, gọi save trên managed entity thường không cần thiết về mặt vòng đời JPA.

### 7.3. Cập nhật từ một object detached

Có thể merge một object detached, nhưng cần hiểu rằng merge sao chép trạng thái của object nguồn. Ví dụ:

~~~java
Customer detached = new Customer();
detached.setId(10L);
detached.setName("Lan");

Customer managed = repository.save(detached);
~~~

Nếu Spring Data nhận diện object là đã tồn tại, nó gọi merge và trả về instance managed. Hãy tiếp tục dùng `managed`, không giả định `detached` đã trở thành managed.

Cách cập nhật này cần thận trọng vì object nguồn có thể không chứa đủ dữ liệu. Các thuộc tính chưa được gán, đang `null` hoặc collection chưa được tải có thể bị sao chép sang managed entity, dẫn tới ghi đè giá trị đang có. Với cập nhật một phần từ HTTP request, nên tải entity hiện tại rồi chỉ áp dụng các trường được phép thay đổi.

## 8. Vì sao phải dùng giá trị trả về của save()?

Với nhánh persist, Spring Data thường trả lại cùng instance vừa được persist. Với nhánh merge, JPA có thể trả về một instance managed khác với object nguồn.

Ví dụ:

~~~java
Customer detached = getDetachedCustomer();

Customer saved = repository.save(detached);

// Tiếp tục sử dụng saved.
saved.setName("Updated name");
~~~

Nếu tiếp tục thay đổi `detached`, thay đổi đó không được persistence context theo dõi. Vì vậy, luôn gán kết quả của `save()` vào biến khi entity có thể đi qua nhánh merge.

Đây là một trong những lỗi phổ biến nhất khi sử dụng `save()` với entity detached.

## 9. save(), flush() và commit khác nhau như thế nào?

`save()` chọn persist hoặc merge và trả về entity. Nó không đồng nghĩa với việc database đã commit dữ liệu ngay lập tức.

- **save:** đưa entity vào luồng lưu của repository; SQL có thể được trì hoãn.
- **flush:** yêu cầu persistence context đồng bộ các thay đổi đang chờ xuống database.
- **commit:** kết thúc transaction thành công và xác nhận thay đổi theo cơ chế transaction của database.

Ví dụ:

~~~java
@Transactional
public Customer createAndFlush(String name) {
    Customer customer = repository.save(new Customer(name));
    repository.flush();
    return customer;
}
~~~

`saveAndFlush()` là phương thức tiện ích kết hợp save và flush. Flush gửi các thay đổi cần thiết xuống database và có thể làm lộ lỗi constraint sớm hơn, nhưng nếu transaction bao quanh vẫn chưa commit thì transaction vẫn có thể rollback.

Không nên gọi flush sau mọi lần save một cách máy móc. Flush thường cần khi ứng dụng phải quan sát lỗi database tại một điểm cụ thể, cần bảo đảm câu SQL đã được gửi trước truy vấn tiếp theo, hoặc cần đồng bộ trạng thái trước một thao tác đặc biệt.

## 10. persist/merge và cascade giữa các entity

Khi entity có quan hệ với entity khác, việc persist hoặc merge có thể được truyền theo cascade được khai báo.

Ví dụ:

~~~java
@OneToMany(
    mappedBy = "customer",
    cascade = {CascadeType.PERSIST, CascadeType.MERGE}
)
private List<Address> addresses = new ArrayList<>();
~~~

- `CascadeType.PERSIST` truyền thao tác persist từ entity nguồn sang các entity đích.
- `CascadeType.MERGE` truyền thao tác merge tới các entity đích.
- `CascadeType.ALL` bao gồm cả persist và merge cùng các thao tác cascade khác.

Nếu không khai báo cascade phù hợp, persist một entity cha không tự động làm mọi entity con trở thành managed. Khi quan hệ trỏ tới một entity transient chưa được persist và không có cascade PERSIST, provider có thể báo lỗi transient object/reference.

Không nên thêm `CascadeType.ALL` cho mọi quan hệ. Cần xét quyền sở hữu vòng đời, khả năng chia sẻ entity con và tác động của từng thao tác cascade.

## 11. Những lỗi thường gặp khi dùng save()

### 11.1. Entity có ID nhưng thực chất là mới

Nếu ID được gán thủ công, quy tắc mặc định có thể xem entity có ID khác `null` là đã tồn tại. `save()` khi đó gọi merge thay vì persist.

Cách xử lý:

- Dùng `@Version` với kiểu object như `Long` nếu phù hợp với mô hình.
- Hoặc triển khai `Persistable<ID>` và định nghĩa `isNew()` rõ ràng.
- Kiểm thử cả trường hợp entity mới và entity được tải từ database.

### 11.2. Gọi save nhưng không dùng object trả về

Khi merge, object nguồn vẫn detached. Nếu bỏ qua kết quả `save()`, code phía sau có thể thay đổi nhầm object không còn được quản lý.

Cách xử lý: luôn dùng instance trả về từ `save()` nếu entity có thể đi qua nhánh merge.

### 11.3. Merge object thiếu dữ liệu làm ghi đè cột

Một DTO chỉ chứa `id` và một vài trường được gửi lên có thể được map thành entity thiếu các trường còn lại. Nếu merge object đó, trạng thái thiếu hoặc `null` có thể ghi đè dữ liệu hiện có.

Cách xử lý: tải entity managed theo ID, kiểm tra quyền cập nhật, rồi chỉ cập nhật các thuộc tính có mặt trong request. Với cập nhật một phần, phải phân biệt rõ “không gửi trường” và “gửi trường với giá trị null”.

### 11.4. Nhầm merge với upsert

Merge là thao tác vòng đời JPA, không phải cam kết về một lệnh SQL upsert nguyên tử. Không dùng nó như cơ chế chống trùng hoặc đồng bộ nhiều request đồng thời. Nếu cần bảo đảm duy nhất, hãy dùng unique constraint và xử lý xung đột ở database.

### 11.5. Bỏ qua optimistic locking

Hai request cùng tải một entity, mỗi request thay đổi một trường rồi cùng merge có thể gây ghi đè nếu không có cơ chế kiểm soát cập nhật đồng thời.

Dùng `@Version` giúp provider kiểm tra version khi UPDATE. Nếu version đã thay đổi kể từ lúc entity được đọc, transaction cũ có thể thất bại với optimistic locking exception. Ở tầng Spring, lỗi có thể được chuyển thành `ObjectOptimisticLockingFailureException` tùy đường gọi và exception translation.

## 12. Quy trình chọn persist hay merge

Khi viết service, có thể quyết định theo các bước sau:

1. Xác định object là entity mới hay đã từng được lưu.
2. Kiểm tra quy tắc nhận diện entity mới của Spring Data: `Persistable.isNew()`, version property hay ID.
3. Với entity mới, để `save()` chọn persist hoặc gọi `EntityManager.persist()` nếu đang làm việc trực tiếp với JPA.
4. Với entity detached, chỉ merge khi thật sự muốn sao chép trạng thái của object nguồn vào persistence context.
5. Với entity đã managed trong transaction, thay đổi trực tiếp và để dirty checking làm việc.
6. Luôn sử dụng instance trả về từ `save()` khi nhánh merge có thể xảy ra.
7. Chỉ flush khi cần đồng bộ SQL tại một thời điểm xác định; commit thuộc về transaction.
8. Kiểm tra cascade và `@Version` khi entity có quan hệ hoặc có nhiều transaction cập nhật cùng dữ liệu.

Trong phần lớn ứng dụng Spring Data JPA, không cần service tự phân nhánh gọi `persist()` hay `merge()` cho từng entity. Hãy để repository `save()` xử lý theo entity-state detection mặc định, trừ khi ứng dụng có lý do rõ ràng để tùy chỉnh.

## 13. Ghi nhớ

- `save()` của Spring Data JPA chọn `persist()` hoặc `merge()` dựa trên `isNew(entity)`.
- `persist()` làm chính object nguồn trở thành managed.
- `merge()` sao chép trạng thái vào một instance managed và trả về instance đó; object nguồn detached vẫn detached.
- Mặc định, Spring Data thường kiểm tra `Persistable.isNew()`, sau đó version object null/không null, rồi tới ID null/khác null theo quy tắc nhận diện entity mới.
- ID được gán thủ công cần chiến lược nhận diện entity mới phù hợp.
- Entity managed được dirty checking; không cần save lại chỉ để theo dõi thay đổi.
- `save()` không đồng nghĩa flush hoặc commit.
- Merge object thiếu dữ liệu có thể ghi đè trường đang có; cập nhật một phần nên tải entity managed rồi áp dụng trường được phép.
- `@Version` hỗ trợ phát hiện cập nhật đồng thời.
- Cascade PERSIST và MERGE quyết định thao tác có được truyền sang entity liên quan hay không.

Hiểu entity state và giá trị trả về của `merge()` là chìa khóa để sử dụng `save()` chính xác. Khi tạo mới, persist đưa object vào persistence context; khi làm việc với detached state, merge sao chép trạng thái sang instance managed; còn khi entity đã managed, dirty checking thường là đủ.