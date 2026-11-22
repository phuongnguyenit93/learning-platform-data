# Detached Entity, merge sai và EntityExistsException

Trong JPA, một Entity có thể ở các trạng thái new/transient, managed, detached hoặc removed. Nhiều lỗi khi cập nhật dữ liệu xuất phát từ việc nhầm lẫn các trạng thái này hoặc dùng persist/merge không đúng mục đích.

Một Entity detached từng được quản lý bởi persistence context nhưng hiện không còn được EntityManager quản lý. Muốn đồng bộ thay đổi của nó, có thể dùng merge. Tuy nhiên, merge không gắn lại chính object đầu vào; nó sao chép trạng thái sang một instance managed và trả về instance đó. Nếu bỏ qua giá trị trả về của merge hoặc JpaRepository.save(), ứng dụng có thể tiếp tục sửa object detached và tưởng rằng thay đổi đã được lưu.

EntityExistsException thường xuất hiện khi persist một Entity đã có định danh/tồn tại, hoặc có xung đột danh tính mà persistence provider phát hiện. Cần phân biệt lỗi này với lỗi merge dữ liệu cũ, optimistic locking và lỗi constraint ở database.

## 1. Bốn trạng thái vòng đời của Entity

JPA quản lý Entity thông qua persistence context, thường gắn với một EntityManager.

| Trạng thái | Ý nghĩa | Thay đổi có được tự đồng bộ không? |
|---|---|---|
| New/transient | Object mới, chưa được persist và chưa được quản lý | Chưa |
| Managed/persistent | Entity đang được EntityManager quản lý | Có, qua dirty checking khi flush |
| Detached | Entity từng được quản lý nhưng không còn thuộc persistence context hiện tại | Không |
| Removed | Entity đã được đánh dấu xóa trong persistence context | DELETE được đồng bộ khi flush |

Ví dụ tạo Entity mới:

~~~java
Customer customer = new Customer("An");
~~~

Object này đang ở trạng thái new/transient. Sau khi gọi persist trong một transaction:

~~~java
entityManager.persist(customer);
~~~

customer trở thành managed. Thay đổi thuộc tính của nó sẽ được JPA theo dõi:

~~~java
customer.rename("An Nguyen");
~~~

Khi flush hoặc commit, Hibernate/JPA phát sinh câu UPDATE nếu Entity có thay đổi.

Khi EntityManager bị đóng, persistence context bị clear hoặc Entity bị detach, object không còn managed. Thay đổi trên object detached không tự động được ghi xuống database.

## 2. Detached Entity hình thành khi nào?

Một Entity có thể trở thành detached trong các tình huống:

- EntityManager bị đóng.
- Gọi entityManager.clear(), làm detach toàn bộ Entity đang managed.
- Gọi entityManager.detach(entity), làm detach một Entity cụ thể.
- Transaction/persistence context kết thúc và Entity không còn được quản lý.
- Entity được trả khỏi service, serialize hoặc truyền qua một request khác rồi được dùng lại.
- Entity được giữ trong session/web state hoặc cache ứng dụng sau khi persistence context đã kết thúc.

Ví dụ:

~~~java
@Transactional
public Customer loadCustomer(Long id) {
    return customerRepository.findById(id).orElseThrow();
}
~~~

Sau khi service kết thúc, object trả về thường không còn được quản lý bởi transaction/persistence context của service. Việc sửa object đó ở controller hoặc một request sau không tự cập nhật database.

Có thể kiểm tra trạng thái trong phạm vi EntityManager:

~~~java
boolean managed = entityManager.contains(customer);
~~~

Nếu trả về false, Entity không được EntityManager hiện tại quản lý. Điều này không nhất thiết có nghĩa object là detached trong mọi bối cảnh; một object mới/transient cũng trả false. Cần biết lịch sử vòng đời của object để phân biệt.

## 3. persist() dùng cho Entity mới

EntityManager.persist() đưa một Entity mới vào persistence context:

~~~java
Customer customer = new Customer("An");

entityManager.persist(customer);

assert entityManager.contains(customer);
~~~

Sau persist:
- Chính object truyền vào trở thành managed.
- JPA theo dõi thay đổi của object.
- INSERT có thể được thực hiện ngay hoặc trì hoãn đến flush/commit tùy chiến lược ID và provider.
- Không có object managed mới được trả về; persist() có kiểu trả về void.

Không dùng persist() để cập nhật một detached Entity đã tồn tại. persist() được thiết kế cho trạng thái new/transient.

Nếu truyền một Entity detached hoặc một Entity có cùng định danh với một Entity đã tồn tại, JPA có thể báo lỗi như EntityExistsException hoặc IllegalArgumentException tùy tình huống và thời điểm phát hiện. Hibernate có thể ném lỗi provider-specific như PersistentObjectException với thông báo detached entity passed to persist.

## 4. merge() dùng để đồng bộ trạng thái detached

EntityManager.merge() sao chép trạng thái của object đầu vào sang một instance managed cùng identity. Giá trị trả về mới là instance được quản lý trong persistence context hiện tại.

~~~java
Customer detached = loadOutsideCurrentPersistenceContext();

Customer managed = entityManager.merge(detached);

assert entityManager.contains(managed);
~~~

Nếu detached thực sự không được quản lý trong persistence context hiện tại, managed là instance đại diện cho cùng identity trong context đó. Object detached ban đầu vẫn detached.

Điểm cần nhớ:

- merge() không biến object đầu vào thành managed.
- merge() trả về instance managed.
- Thay đổi tiếp theo cần thực hiện trên instance trả về.
- Trạng thái của object đầu vào được sao chép sang managed instance theo quy tắc merge của JPA.
- Các quan hệ chỉ được merge lan truyền nếu mapping có cascade MERGE hoặc ALL.

Không nhầm merge() với một câu SQL UPDATE đơn giản. Provider phải đồng bộ trạng thái object với persistence context và database; thao tác có thể cần đọc dữ liệu hiện tại, kiểm tra version và lên lịch INSERT/UPDATE.

## 5. Lỗi phổ biến: bỏ qua object trả về từ merge()

Ví dụ sai:

~~~java
Customer detached = receiveCustomerFromRequest();

entityManager.merge(detached);

// Sai: detached vẫn không được quản lý.
detached.rename("New name");
~~~

merge() đã sao chép trạng thái hiện tại của detached sang managed instance. Lệnh rename() chạy sau đó trên detached không được dirty checking theo dõi.

Cách đúng:

~~~java
Customer detached = receiveCustomerFromRequest();

Customer managed = entityManager.merge(detached);

managed.rename("New name");
~~~

Nếu chỉ cần đồng bộ trạng thái hiện tại, hãy dùng instance trả về. Nếu cần sửa thêm, tiếp tục làm việc trên managed.

Quy tắc tương tự áp dụng cho JpaRepository.save(). Khi save() chọn merge, phương thức trả về instance managed. Hãy sử dụng giá trị trả về:

~~~java
Customer managed = customerRepository.save(detached);
managed.rename("New name");
~~~

Không viết save(detached) rồi mặc định object detached ban đầu đã được gắn lại vào persistence context.

## 6. Spring Data JPA save() chọn persist hay merge như thế nào?

JpaRepository.save(entity) không luôn gọi persist() và cũng không luôn gọi merge(). Spring Data JPA kiểm tra Entity có được xem là mới hay không thông qua EntityInformation.isNew().

Quy tắc mặc định phổ biến:
1. Nếu Entity có thuộc tính @Version không phải primitive, Spring Data kiểm tra version. Version null thường được xem là Entity mới.
2. Nếu không có version property phù hợp, Spring Data kiểm tra ID. ID null thường được xem là Entity mới.
3. Nếu Entity implement Persistable, Spring Data dùng isNew() do Entity cung cấp.
4. Ứng dụng có thể tùy chỉnh EntityInformation thông qua cơ chế repository factory khi thực sự cần.

Nếu được xem là mới, save() gọi EntityManager.persist(entity) và trả về entity đó. Nếu không mới, save() gọi EntityManager.merge(entity) và trả về managed instance.

Vì vậy, ID/version mapping ảnh hưởng trực tiếp đến đường đi persist hay merge.

## 7. Vì sao Entity có ID gán trước có thể bị save() xử lý sai?

Một số ứng dụng dùng ID do bên ngoài cấp, UUID tự tạo hoặc khóa nghiệp vụ thay vì ID do database sinh.

Ví dụ:

~~~java
@Entity
public class ExternalCustomer {

    @Id
    private UUID id;

    private String name;
}
~~~

Nếu tạo một ExternalCustomer mới nhưng đã gán id khác null, và Entity không có version property phù hợp, quy tắc mặc định có thể xem nó là Entity đã tồn tại và chọn merge.

Điều đó có thể làm phát sinh SELECT trước khi ghi, hoặc dẫn đến hành vi khác với ý định tạo mới. Khi version hoặc trạng thái database không như mong đợi, kết quả có thể là insert/update không đúng, optimistic locking exception hoặc lỗi constraint.

Không được suy luận rằng ID khác null luôn đồng nghĩa bản ghi đã tồn tại. ID có thể được gán trước khi insert.

## 8. Dùng @Version để hỗ trợ phát hiện Entity mới

Một version property không phải primitive có thể giúp Spring Data nhận diện Entity mới:

~~~java
@Entity
public class ExternalCustomer {

    @Id
    private UUID id;

    @Version
    private Long version;

    private String name;
}
~~~

Với Entity mới, version thường null; Spring Data có thể nhận diện là new và dùng persist. Sau khi Entity được lưu, provider quản lý version theo cơ chế optimistic locking.

Dùng wrapper Long thay vì primitive long nếu cần trạng thái null để nhận diện mới. Primitive không thể biểu diễn null nên không cung cấp tín hiệu “chưa được persist” theo cách này.

Version không chỉ là cờ newness. Nó còn bảo vệ cập nhật đồng thời bằng cách kiểm tra version cũ khi UPDATE. Không tự gán version tùy tiện để ép Spring Data đi vào nhánh persist/merge.

## 9. Dùng Persistable khi ID được gán trước

Nếu Entity dùng assigned ID và không thể dựa vào version, có thể implement Persistable<ID> để tự xác định trạng thái mới.

Ví dụ:

~~~java
import jakarta.persistence.*;
import org.springframework.data.domain.Persistable;

@Entity
public class ExternalCustomer implements Persistable<UUID> {

    @Id
    private UUID id;

    private String name;

    @Transient
    private boolean newEntity = true;

    protected ExternalCustomer() {
    }

    public ExternalCustomer(UUID id, String name) {
        this.id = id;
        this.name = name;
    }

    @Override
    public UUID getId() {
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

Khi mới tạo object qua constructor, newEntity là true nên save() chọn persist. Sau persist hoặc load, callback đánh dấu Entity không còn mới.

Đây là mẫu minh họa. Cần bảo đảm mọi đường tạo/load Entity đều thiết lập cờ đúng, đặc biệt với serialization, deserialization, factory và các công cụ import. Không nhận trạng thái isNew từ dữ liệu client như một giá trị có thể tin cậy; nó là metadata persistence do ứng dụng quản lý.

## 10. EntityExistsException là gì?

Jakarta Persistence định nghĩa EntityExistsException để báo rằng thao tác persist gặp Entity đã tồn tại hoặc xung đột theo identity mà persistence provider phát hiện.

Một tình huống thường gặp:

~~~java
Customer customer = entityManager.find(Customer.class, 10L);
entityManager.detach(customer);

// Không dùng persist() cho object detached này.
entityManager.persist(customer);
~~~

Entity đã có ID và từng tồn tại. Gọi persist() không phải cách cập nhật nó. Provider có thể phát hiện xung đột ngay tại persist() hoặc trì hoãn đến flush/commit.

Một ví dụ khác là ứng dụng tự gán ID trùng với một Entity đã tồn tại rồi gọi persist() cho object mới đó.

Không dựa vào một thời điểm duy nhất để bắt lỗi. Với JPA, một số lỗi persistence có thể chỉ xuất hiện khi flush hoặc commit.

## 11. Phân biệt EntityExistsException với các lỗi gần giống

| Lỗi | Ý nghĩa thường gặp | Hướng kiểm tra |
|---|---|---|
| EntityExistsException | persist gặp Entity/identity đã tồn tại | Kiểm tra trạng thái Entity, ID và persist/merge |
| PersistentObjectException | Lỗi riêng của Hibernate, ví dụ detached entity passed to persist | Kiểm tra detached object bị truyền vào persist/cascade |
| NonUniqueObjectException | Hibernate Session đã quản lý object khác cùng identifier | Kiểm tra nhiều instance cùng ID trong một Session |
| OptimisticLockException | Version không còn khớp khi cập nhật | Kiểm tra stale data và @Version |
| DataIntegrityViolationException | Spring dịch lỗi constraint/data integrity | Kiểm tra unique, FK, NOT NULL và dữ liệu đầu vào |
| ConstraintViolationException | Hibernate báo vi phạm constraint SQL | Kiểm tra constraint database và câu SQL |

Các lớp exception có thể được bọc trong exception khác qua Spring exception translation. Hãy xem root cause, SQL state, constraint name và thời điểm lỗi thay vì chỉ dựa vào tên exception ngoài cùng.

Không coi mọi lỗi “detached” là EntityExistsException. Detached là trạng thái vòng đời; EntityExistsException là một loại lỗi persistence cụ thể.

## 12. persist() và merge() khác nhau thế nào?

| Tiêu chí | persist() | merge() |
|---|---|---|
| Đầu vào phù hợp | Entity mới/transient | Entity detached hoặc trạng thái cần merge |
| Kết quả trả về | void | Instance managed |
| Object đầu vào | Trở thành managed | Vẫn detached nếu ban đầu detached |
| Identity | Dùng identity của Entity mới | Đồng bộ vào managed instance cùng identity |
| Mục đích | Tạo Entity mới | Sao chép trạng thái vào persistence context |
| Cascade | PERSIST hoặc ALL | MERGE hoặc ALL |
| Rủi ro thường gặp | Persist detached/existing object | Bỏ qua managed copy hoặc ghi đè trạng thái mới hơn |

Không dùng merge() như cách chữa mọi lỗi persist. Nếu object thực ra là một bản ghi mới, hãy xác định đúng newness và dùng persist. Nếu object detached đại diện cho một bản ghi hiện có, merge có thể phù hợp nhưng cần kiểm soát dữ liệu được merge.

## 13. merge() có thể ghi đè dữ liệu database

merge() đồng bộ trạng thái của object detached. Nếu object được tạo từ một payload cũ hoặc chỉ chứa một phần field, các giá trị null/default có thể được sao chép lên managed instance và ghi đè dữ liệu mới hơn.

Ví dụ database đang có:

~~~text
id = 10
name = "An Nguyen"
email = "an@example.com"
active = true
~~~

Client chỉ gửi:

~~~json
{
  "id": 10,
  "name": "An"
}
~~~

Nếu ứng dụng dựng một Entity mới chỉ có id và name rồi merge toàn bộ object, email có thể bị ghi thành null và active có thể bị ghi thành giá trị mặc định tùy mapping/field initialization.

Đây là lý do không nên biến request DTO thành detached Entity rồi merge trực tiếp khi request chỉ chứa một phần dữ liệu.

Cách an toàn hơn:
1. Load Entity managed bằng ID.
2. Kiểm tra quyền và trạng thái nghiệp vụ.
3. Chỉ áp dụng các field được phép thay đổi.
4. Để dirty checking đồng bộ thay đổi.
5. Dùng @Version nếu cần phát hiện update dựa trên dữ liệu cũ.

## 14. Cập nhật Entity managed thay vì merge một object mới dựng

Mẫu service thường an toàn:

~~~java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public CustomerDto update(Long id, UpdateCustomerCommand command) {
        Customer customer = repository.findById(id)
                .orElseThrow(() -> new CustomerNotFoundException(id));

        if (command.name() != null) {
            customer.rename(command.name());
        }

        if (command.email() != null) {
            customer.changeEmail(command.email());
        }

        return CustomerDto.from(customer);
    }
}
~~~

Customer được load trong transaction nên là managed. Thay đổi trên object được theo dõi bởi persistence context. Khi commit, dirty checking tạo UPDATE cho các thuộc tính đã thay đổi.

Trong trường hợp này thường không cần gọi repository.save(customer) lần nữa. Gọi save() trên Entity đã managed thường không cần thiết cho dirty checking, dù có thể được dùng theo quy ước codebase.

Nếu API cần phân biệt “không gửi field” với “gửi null để xóa field”, DTO phải biểu diễn được hai trạng thái đó. Kiểm tra command.email() != null chỉ là ví dụ cho API không cho phép đặt email thành null.

## 15. Cascade MERGE và đồ thị Entity

Khi merge một Entity có quan hệ, trạng thái của Entity liên quan chỉ được merge lan truyền nếu mapping khai báo cascade phù hợp.

Ví dụ:

~~~java
@OneToMany(
    mappedBy = "customer",
    cascade = CascadeType.MERGE
)
private List<Address> addresses = new ArrayList<>();
~~~

CascadeType.MERGE cho phép thao tác merge trên Customer lan truyền đến các Address theo quy tắc JPA.

Các cascade phổ biến:

- PERSIST: lan truyền persist.
- MERGE: lan truyền merge.
- REMOVE: lan truyền remove.
- REFRESH: lan truyền refresh.
- DETACH: lan truyền detach.
- ALL: gồm các loại cascade trên.

Không thêm CascadeType.ALL chỉ để tránh lỗi. Cascade là quy tắc vòng đời: xóa Customer có thể kéo theo xóa Address nếu REMOVE được bật. Chỉ cascade khi Entity cha thực sự sở hữu vòng đời của đối tượng con.

Với quan hệ nhiều-nhiều hoặc Entity dùng chung, cascade REMOVE có thể xóa nhầm dữ liệu dùng chung nếu mapping không phù hợp.

## 16. Detached graph và quan hệ có thể gây lỗi gì?

Một object detached có thể chứa cả một graph Entity. Khi merge, provider phải xử lý các quan hệ theo cascade và mapping.

Các vấn đề thường gặp:
- Quan hệ con không có cascade MERGE nên thay đổi trên object con không được merge như kỳ vọng.
- Một object con detached có cùng ID nhưng trạng thái cũ ghi đè dữ liệu mới hơn.
- Một quan hệ trỏ đến Entity transient nhưng mapping không cascade PERSIST/MERGE phù hợp.
- Collection được gửi thiếu phần tử rồi merge làm thay đổi quan hệ không như ý.
- Nhiều instance đại diện cùng ID trong một graph tạo xung đột ở Hibernate Session.
- Orphan removal xóa Entity con khi phần tử bị loại khỏi collection managed.

Với aggregate nghiệp vụ, thường nên load root managed, sau đó thêm/xóa/cập nhật child thông qua phương thức domain của root. Không merge toàn bộ graph từ request bên ngoài một cách mù quáng.

## 17. Không dùng persist() để cập nhật detached Entity

Một đoạn code sai thường gặp:

~~~java
@Transactional
public void update(Customer detached) {
    entityManager.persist(detached);
}
~~~

Nếu detached đại diện cho bản ghi đã tồn tại, persist() không phải thao tác cập nhật. Có thể nhận EntityExistsException hoặc lỗi provider-specific.

Có hai hướng đúng tùy use case.

Dùng managed entity:

~~~java
@Transactional
public void update(Long id, String newName) {
    Customer customer = entityManager.find(Customer.class, id);

    if (customer == null) {
        throw new CustomerNotFoundException(id);
    }

    customer.rename(newName);
}
~~~

Hoặc merge khi thực sự cần đồng bộ detached state:

~~~java
@Transactional
public Customer updateDetached(Customer detached) {
    return entityManager.merge(detached);
}
~~~

Hướng thứ nhất thường dễ kiểm soát field được phép sửa và tránh ghi đè dữ liệu ngoài ý muốn. Hướng thứ hai phù hợp khi ứng dụng có chủ đích merge toàn bộ trạng thái detached.

## 18. save() không có nghĩa là luôn INSERT hoặc luôn UPDATE

Spring Data JPA save() chọn persist hay merge dựa trên newness detection, không chỉ dựa trên ý định của người gọi.

| Entity | Newness thường được nhận diện | Hành vi save() |
|---|---|---|
| ID null, không có version | Mới | persist |
| ID khác null, không có version | Không mới | merge |
| ID khác null, version Long null | Mới theo version strategy | persist |
| ID khác null, version đã có giá trị | Không mới | merge |
| Implement Persistable và isNew() true | Mới theo custom strategy | persist |
| Implement Persistable và isNew() false | Không mới theo custom strategy | merge |

Bảng này mô tả chiến lược mặc định phổ biến của Spring Data JPA. Nếu ứng dụng custom EntityInformation hoặc override repository behavior, kết quả có thể khác.

Nếu save() đi vào merge, hãy luôn nhận object trả về. Nếu ID được gán trước nhưng Entity thực sự mới, hãy cấu hình newness strategy rõ ràng thay vì dựa vào suy đoán.

## 19. saveAndFlush() không sửa được lỗi merge/persist

saveAndFlush() gọi save() rồi yêu cầu flush persistence context. Nó không thay đổi cách Spring Data quyết định persist hay merge.

~~~java
Customer saved = repository.saveAndFlush(customer);
~~~

Nếu save() chọn merge, saved vẫn là managed copy trả về từ merge. Nếu save() chọn persist, saved thường là chính object mới.

Flush buộc provider đồng bộ SQL sớm hơn và có thể làm lỗi EntityExistsException, constraint hoặc optimistic locking xuất hiện ngay tại điểm gọi. Flush không phải commit; transaction vẫn có thể rollback sau đó.

Đừng dùng saveAndFlush() như một cách “ép update” detached Entity hoặc chữa việc newness detection sai.

## 20. Optimistic locking khi merge dữ liệu cũ

Nếu Entity có @Version, provider dùng version để phát hiện hai transaction cùng sửa một bản ghi.

Ví dụ:

~~~java
@Entity
public class Customer {

    @Id
    private Long id;

    @Version
    private Long version;

    private String name;

    public void rename(String name) {
        this.name = name;
    }
}
~~~

Tình huống:
1. Transaction A đọc Customer version 4.
2. Transaction B cũng đọc version 4.
3. B cập nhật và commit; version thành 5.
4. A merge/update object cũ vẫn mang version 4.
5. Khi flush/commit, provider phát hiện version không còn khớp và báo OptimisticLockException hoặc exception được Spring dịch tương ứng.

Đây là bảo vệ chống lost update. Không bỏ qua lỗi optimistic locking bằng cách merge lại object cũ liên tục. Hãy tải trạng thái mới, so sánh thay đổi và quyết định retry hoặc trả conflict cho caller.

## 21. Khi nào cần refresh(), detach() và clear()?

Các API persistence context có mục đích khác nhau:

- detach(entity): loại một Entity khỏi persistence context.
- clear(): detach tất cả Entity đang managed trong context.
- refresh(entity): tải lại trạng thái database vào một Entity managed, ghi đè thay đổi chưa flush của object.
- merge(entity): sao chép trạng thái object vào một managed instance và trả về instance đó.

Ví dụ refresh:

~~~java
entityManager.refresh(customer);
~~~

Chỉ refresh Entity đang managed. Refresh có thể làm mất các thay đổi chưa flush trên object vì trạng thái database được tải lại.

clear() hữu ích trong batch để tránh persistence context giữ quá nhiều Entity, nhưng sau clear, mọi object trước đó đều detached. Nếu tiếp tục cập nhật chúng, cần load lại hoặc merge đúng cách.

Không gọi clear() giữa chừng rồi tiếp tục giả định các object cũ vẫn managed.

## 22. EntityExistsException có thể xuất hiện lúc nào?

JPA provider có thể phát hiện lỗi tại nhiều thời điểm:

- Ngay khi gọi persist() nếu biết Entity không hợp lệ cho thao tác đó.
- Khi flush() vì lúc đó SQL mới được gửi xuống database.
- Khi commit() vì transaction manager yêu cầu flush và database kiểm tra constraint.

Vì vậy, đoạn test chỉ bọc persist() trong assertThrows có thể không bắt được lỗi nếu provider trì hoãn kiểm tra:

~~~java
entityManager.persist(entity);
entityManager.flush();
~~~

Khi kiểm thử lỗi persistence, cần xác định thời điểm flush/commit rõ ràng và kiểm tra root cause. Đừng bắt một loại exception quá cụ thể nếu JPA/provider có thể báo lỗi tương đương dưới dạng wrapper.

## 23. Quy trình chẩn đoán lỗi detached/merge

Khi gặp thông báo như detached entity passed to persist, EntityExistsException hoặc merge không lưu thay đổi, hãy kiểm tra theo thứ tự:

1. Xác định Entity đang new, managed, detached hay removed.
2. Kiểm tra EntityManager.contains(entity) trong đúng persistence context.
3. Xem code gọi persist(), merge() hay repository.save().
4. Nếu gọi merge/save, kiểm tra có dùng object trả về hay không.
5. Kiểm tra ID được sinh hay gán trước.
6. Kiểm tra @Version có tồn tại và có phải wrapper type hay không.
7. Nếu implement Persistable, kiểm tra isNew() và callback cập nhật trạng thái.
8. Kiểm tra cascade PERSIST/MERGE trên từng quan hệ.
9. Kiểm tra có nhiều object cùng ID trong một persistence context không.
10. Kiểm tra dữ liệu detached có field null/default làm ghi đè dữ liệu hiện có không.
11. Kiểm tra version cũ và optimistic locking.
12. Gọi flush có chủ đích trong test để xác định lỗi xuất hiện ở persist, flush hay commit.
13. Đọc root cause, SQL state và constraint name thay vì chỉ nhìn exception wrapper.

Không chữa lỗi bằng cách thêm CascadeType.ALL, gọi saveAndFlush() hoặc merge mọi object mà chưa xác định nguyên nhân.

## 24. Kiểm thử merge và trạng thái managed

Một integration test có thể chứng minh merge trả về instance managed riêng:

~~~java
@DataJpaTest
class CustomerMergeTest {

    @PersistenceContext
    private EntityManager entityManager;

    @Test
    void mergeReturnsManagedCopyOfDetachedEntity() {
        Customer customer = new Customer("An");
        entityManager.persist(customer);
        entityManager.flush();

        Long id = customer.getId();

        entityManager.detach(customer);
        assertFalse(entityManager.contains(customer));

        customer.rename("An Nguyen");

        Customer managed = entityManager.merge(customer);

        assertNotSame(customer, managed);
        assertTrue(entityManager.contains(managed));
        assertFalse(entityManager.contains(customer));

        entityManager.flush();

        Customer reloaded = entityManager.find(Customer.class, id);
        assertEquals("An Nguyen", reloaded.getName());
    }
}
~~~

Test giả định Customer có ID được sinh, constructor và rename/getName tương ứng. EntityManager vẫn giữ transaction của test; flush đồng bộ SQL nhưng transaction test có thể rollback khi kết thúc.

Test cần xác nhận:
- Detached object không được quản lý.
- merge() trả về object managed.
- Object đầu vào vẫn detached.
- Giá trị merge được lưu sau flush.
- Đọc lại trong persistence context phản ánh trạng thái mong đợi.

## 25. Kiểm thử Spring Data save() với Entity detached

Với Repository, hãy kiểm tra cả giá trị trả về:

~~~java
@DataJpaTest
class CustomerRepositorySaveTest {

    @Autowired
    private CustomerRepository repository;

    @PersistenceContext
    private EntityManager entityManager;

    @Test
    void saveReturnsManagedInstanceForDetachedEntity() {
        Customer customer = repository.save(new Customer("An"));
        repository.flush();

        Long id = customer.getId();

        entityManager.detach(customer);
        customer.rename("An Nguyen");

        Customer saved = repository.save(customer);

        assertNotSame(customer, saved);
        assertTrue(entityManager.contains(saved));
        assertFalse(entityManager.contains(customer));

        repository.flush();

        entityManager.clear();

        Customer reloaded = repository.findById(id).orElseThrow();
        assertEquals("An Nguyen", reloaded.getName());
    }
}
~~~

Đây là test minh họa cho Entity có ID được sinh và save() nhận diện object detached là không mới. Nếu Entity dùng assigned ID hoặc Persistable, cần điều chỉnh fixture theo newness strategy.

Trong dự án thực tế, hãy test cả trường hợp ID gán trước, version null, version khác null và callback Persistable để tránh insert/update sai.

## 26. Kiểm thử EntityExistsException theo provider

Có thể viết integration test cho tình huống persist một object detached, nhưng không nên giả định mọi provider ném cùng một class exception ở cùng dòng code.

Một test có thể:
1. Persist Entity và flush.
2. Detach Entity.
3. Gọi persist() trên object detached.
4. Flush nếu chưa có lỗi.
5. Xác nhận provider/JPA báo lỗi persistence phù hợp.
6. Kiểm tra root cause là xung đột trạng thái/identity, không phải lỗi test fixture khác.

Nếu test cần xác nhận chính xác EntityExistsException, hãy chạy trên provider và phiên bản Hibernate thực tế của ứng dụng, đồng thời kiểm tra thời điểm exception. Hibernate có thể ném exception provider-specific trước khi lớp JPA exception được bọc.

Không bắt Throwable chung rồi coi mọi lỗi là thành công. Test phải xác nhận nguyên nhân lỗi đúng với tình huống đang kiểm tra.

## 27. Những lỗi thường gặp

**Gọi persist() với detached Entity**

persist dành cho Entity mới. Dùng managed entity hoặc merge đúng cách.

**Bỏ qua giá trị trả về của merge()**

Object đầu vào vẫn detached. Dùng instance managed trả về.

**Bỏ qua giá trị trả về của repository.save()**

save() có thể gọi merge và trả managed copy. Tiếp tục làm việc với object cũ có thể làm mất các thay đổi tiếp theo.

**Tạo Entity mới từ DTO rồi merge toàn bộ**

Field null/default có thể ghi đè dữ liệu database. Load managed Entity rồi áp dụng field được phép sửa.

**ID gán trước nhưng Spring Data nhận diện sai newness**

Dùng @Version wrapper phù hợp hoặc implement Persistable.isNew().

**Dùng primitive version để mong nhận diện null**

Primitive không thể null. Dùng wrapper nếu cần tín hiệu newness từ version.

**Thiếu cascade MERGE trên quan hệ**

Thay đổi Entity con không được merge lan truyền như kỳ vọng. Kiểm tra cascade và ownership của quan hệ.

**Thêm CascadeType.ALL một cách máy móc**

Có thể kéo theo remove/refresh/detach ngoài ý muốn. Chọn đúng cascade cần thiết.

**Merge graph detached cũ**

Trạng thái cũ có thể ghi đè thay đổi mới hơn hoặc làm thay đổi collection không mong muốn. Load aggregate managed và áp dụng command.

**Nhầm EntityExistsException với OptimisticLockException**

Một lỗi là xung đột persist/identity; lỗi kia là version stale. Đọc root cause và kiểm tra version.

**Cho rằng saveAndFlush() sẽ commit**

Flush chỉ đồng bộ SQL; transaction vẫn có thể rollback.

**Kiểm tra lỗi trước flush**

Provider có thể trì hoãn lỗi đến flush/commit. Gọi flush có chủ đích trong integration test.

## 28. Quy trình chọn persist, merge hay cập nhật managed Entity

Khi cần ghi một Entity, hãy xác định:

1. Đây có phải Entity mới chưa có persistent identity không?
2. ID do database sinh hay được ứng dụng gán trước?
3. Spring Data sẽ nhận diện newness dựa trên version, ID hay Persistable?
4. Nếu Entity đang managed, có cần gọi save() không hay dirty checking đã đủ?
5. Nếu detached, có cần merge toàn bộ state hay chỉ cần load managed Entity và áp dụng một command?
6. Nếu merge, code có sử dụng object trả về không?
7. Các quan hệ cần cascade PERSIST hay MERGE?
8. Có thể ghi đè field null/default hoặc dữ liệu mới hơn không?
9. Có @Version để phát hiện stale update không?
10. Exception phát sinh tại persist, flush hay commit?
11. Integration test có xác nhận trạng thái managed, giá trị trả về và dữ liệu sau khi clear context không?

Với cập nhật nghiệp vụ thông thường, load Entity managed trong transaction rồi gọi phương thức domain thường là cách dễ kiểm soát nhất. Dùng merge khi thực sự cần đồng bộ một detached graph và hiểu rõ toàn bộ trạng thái sẽ được sao chép.

## 29. Kết luận

Detached Entity là object không còn được persistence context hiện tại quản lý. persist() dành cho Entity mới; merge() sao chép trạng thái vào một instance managed và trả về instance đó, còn object đầu vào vẫn detached. JpaRepository.save() chọn persist hoặc merge dựa trên newness detection qua version, ID hoặc Persistable.isNew(). Vì vậy, luôn dùng object trả về từ merge/save khi nhánh merge có thể xảy ra.

EntityExistsException thường liên quan đến việc persist một Entity đã tồn tại hoặc xung đột identity; cần phân biệt với lỗi Hibernate detached entity passed to persist, NonUniqueObjectException, OptimisticLockException và lỗi constraint. Merge detached state có thể ghi đè field mới hơn hoặc field null/default, nên với cập nhật một phần hãy load Entity managed rồi áp dụng command. Kiểm tra cascade, @Version, ID strategy và thời điểm flush/commit bằng integration test trên provider thực tế.
