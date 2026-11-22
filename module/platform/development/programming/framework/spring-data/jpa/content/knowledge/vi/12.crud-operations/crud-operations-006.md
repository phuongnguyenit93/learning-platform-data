# getReferenceById, proxy và thời điểm kiểm tra sự tồn tại trong Spring Data JPA

`getReferenceById(id)` lấy một tham chiếu JPA đến entity theo khóa chính mà không nhất thiết phải đọc ngay tất cả cột của hàng đó. Cách này hữu ích khi ứng dụng chỉ cần thiết lập một quan hệ bằng ID. Tuy nhiên, nhận được một object tham chiếu không chứng minh rằng bản ghi đích đang tồn tại.

Điểm dễ gây lỗi là việc kiểm tra sự tồn tại có thể bị trì hoãn. Ứng dụng có thể tạo proxy, gán proxy vào một entity khác, rồi chỉ gặp lỗi khi đọc thuộc tính, flush hoặc commit transaction. Bài này tập trung vào vòng đời proxy, các mốc phát hiện ID thiếu, lựa chọn API và cách kiểm thử để lỗi được xử lý ở đúng tầng.

## 1. Một tình huống thực tế

Giả sử hệ thống quản lý phiếu hỗ trợ. Mỗi phiếu có một nhân viên phụ trách:

~~~java
@Entity
@Table(name = "support_tickets")
public class SupportTicket {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "assignee_id", nullable = false)
    private StaffMember assignee;

    protected SupportTicket() {
    }

    public SupportTicket(StaffMember assignee) {
        this.assignee = assignee;
    }

    public Long getId() {
        return id;
    }

    public StaffMember getAssignee() {
        return assignee;
    }

    public void setAssignee(StaffMember assignee) {
        this.assignee = assignee;
    }
}
~~~

Khi tạo phiếu, ứng dụng nhận ID nhân viên là 27. Có hai nhu cầu khác nhau:

- Cần kiểm tra nhân viên 27 có tồn tại, đang hoạt động và có quyền nhận phiếu hay không.
- Quy trình đã xác minh nhân viên và chỉ cần gán ID của họ vào quan hệ để ghi khóa ngoại.

Nhu cầu đầu tiên cần đọc dữ liệu và áp dụng quy tắc nghiệp vụ. Nhu cầu thứ hai có thể chỉ cần một tham chiếu JPA. Chọn sai API khiến lỗi xuất hiện muộn, tạo truy vấn thừa hoặc làm logic nghiệp vụ khó dự đoán.

## 2. Ba API không cùng một mục đích

### 2.1. findById — lấy entity hoặc biết chắc không tìm thấy

~~~java
StaffMember assignee = staffRepository.findById(27L)
        .orElseThrow(() -> new StaffNotFoundException(27L));
~~~

`findById` trả về `Optional<StaffMember>`. Khi không có hàng, caller nhận `Optional.empty()`. Khi có hàng, entity được tải theo fetch plan của query.

Dùng API này khi:

- ID đến từ request bên ngoài.
- Cần trả lỗi “không tìm thấy” rõ ràng.
- Cần đọc trạng thái, tên hoặc quyền của entity đích.
- Cần kiểm tra điều kiện nghiệp vụ trước khi ghi.

### 2.2. existsById — chỉ cần câu trả lời boolean

~~~java
boolean exists = staffRepository.existsById(27L);
~~~

`existsById` phù hợp nếu caller chỉ cần biết có hay không. Nếu sau đó vẫn cần entity, gọi `existsById` rồi `findById` thường tạo hai lượt truy cập database. Khi cần entity và xử lý trường hợp thiếu, `findById` thường làm cả hai việc trong một lần đọc.

### 2.3. getReferenceById — lấy tham chiếu theo khóa chính

~~~java
StaffMember assignee =
        staffRepository.getReferenceById(27L);
~~~

Spring Data JPA ủy quyền thao tác này cho `EntityManager.getReference`. Provider có thể tạo proxy hoặc một đối tượng được enhancement để giữ thông tin định danh và trì hoãn việc tải trạng thái.

Dùng API này khi:

- Caller chỉ cần gắn entity đích vào một quan hệ.
- ID đã được xác minh ở một bước có kiểm soát hoặc được bảo vệ bằng FK.
- Không cần đọc thuộc tính của entity đích trong use case hiện tại.
- Muốn tránh SELECT chỉ để lấy object làm giá trị quan hệ.

Không dùng `getReferenceById` làm validation cho ID do người dùng gửi. Việc nhận được object tham chiếu không chứng minh bản ghi tồn tại.

| Nhu cầu | API phù hợp |
|---|---|
| Kiểm tra ID có tồn tại và trả lỗi rõ ràng | `findById` |
| Chỉ cần boolean tồn tại | `existsById` |
| Thiết lập quan hệ bằng ID đáng tin cậy | `getReferenceById` |
| Cần đọc thuộc tính entity đích | `findById` hoặc query chuyên biệt |
| Trả DTO chứa dữ liệu entity đích | Query/projection lấy đúng các trường |

Các tên cũ `getOne` và `getById` đã bị deprecated trong các phiên bản Spring Data JPA mới hơn. Code mới nên dùng `getReferenceById` và đối chiếu Javadoc của phiên bản dependency đang dùng.

## 3. Proxy được tạo và khởi tạo như thế nào?

Proxy là object đại diện cho entity. Với Hibernate, một ToOne association thường có thể được biểu diễn bằng proxy subclass. Proxy biết kiểu entity và ID, nhưng chưa nhất thiết chứa trạng thái đầy đủ.

~~~java
@Transactional
public void inspectAssignee(Long id) {
    StaffMember reference =
            staffRepository.getReferenceById(id);

    Long knownId = reference.getId();

    // Getter này thường cần trạng thái thật và có thể phát SELECT.
    String displayName = reference.getDisplayName();
}
~~~

Quy trình điển hình:

1. Ứng dụng yêu cầu tham chiếu theo entity type và ID.
2. Provider trả proxy hoặc indirection object.
3. Tham chiếu giữ thông tin định danh.
4. Khi code đọc thuộc tính cần trạng thái, proxy yêu cầu provider khởi tạo.
5. Provider đọc hàng theo ID và nạp trạng thái.
6. Các lần truy cập sau trong cùng persistence context có thể dùng trạng thái đã tải.

Với Hibernate proxy truyền thống, `getId()` thường có thể trả ID mà không khởi tạo proxy; `getDisplayName()` thường cần tải dữ liệu. Đây là hành vi phổ biến của Hibernate, không phải cam kết giống nhau cho mọi provider, enhancement mode hoặc mapping.

### 3.1. Proxy không phải DTO

Không nên trả proxy trực tiếp cho tầng trình bày hoặc serializer. Proxy có thể cần persistence context để tải dữ liệu. Nếu serializer gọi getter sau khi transaction đóng, ứng dụng có thể gặp lỗi.

Ngoài ra, `reference.getClass()` có thể trả về lớp proxy được tạo động thay vì lớp entity gốc. Tránh so sánh class bằng phép bằng tuyệt đối hoặc đưa tên lớp proxy vào logic nghiệp vụ.

Với subclass proxy, entity final hoặc method final có thể hạn chế khả năng proxy truyền thống. Bytecode enhancement có thể thay đổi cách thực hiện lazy loading nhưng cần cấu hình build/runtime phù hợp.

## 4. Bản ghi được kiểm tra vào thời điểm nào?

### 4.1. Lúc gọi getReferenceById

JPA cho phép provider trì hoãn việc đọc trạng thái. Tuy vậy, provider có thể phát hiện lỗi sớm và ném exception ngay khi tạo reference. Không nên giả định lời gọi này luôn thành công với mọi ID.

### 4.2. Lúc proxy cần trạng thái

Nếu proxy chưa khởi tạo, việc gọi getter như `getDisplayName()` có thể kích hoạt SELECT. Nếu không có hàng tương ứng, provider có thể ném `EntityNotFoundException` hoặc exception riêng.

~~~java
StaffMember reference =
        entityManager.getReference(StaffMember.class, 999999L);

// Có thể là nơi provider SELECT và phát hiện hàng không tồn tại.
String name = reference.getDisplayName();
~~~

JPA định nghĩa `EntityNotFoundException` cho trường hợp trạng thái entity được yêu cầu nhưng không có entity tương ứng. Thời điểm phát hiện có thể khác nhau; Spring cũng có thể dịch một số exception persistence sang hệ thống `DataAccessException`.

### 4.3. Lúc chỉ gán reference vào quan hệ

~~~java
@Transactional
public Long openTicket(Long staffId) {
    StaffMember assignee =
            staffRepository.getReferenceById(staffId);

    SupportTicket ticket = new SupportTicket(assignee);
    return ticketRepository.save(ticket).getId();
}
~~~

Nếu proxy không bị khởi tạo, provider có thể dùng ID để ghi `assignee_id` mà không SELECT bảng nhân viên.

Nếu `staffId` không tồn tại:

- Có FK trong database: INSERT có thể bị từ chối khi database kiểm tra FK.
- Constraint được trì hoãn: lỗi có thể chỉ xuất hiện khi commit.
- Không có FK: database có thể chấp nhận giá trị và tạo tham chiếu mồ côi.
- Provider có thể phát hiện sớm hơn nếu phải khởi tạo reference vì một lý do khác.

Vì vậy, `getReferenceById` không thay thế validation hoặc FK constraint.

### 4.4. Lúc flush và commit

`flush` đồng bộ các thay đổi đang chờ trong persistence context xuống database. Nó không kết thúc transaction. `commit` kết thúc transaction và yêu cầu database xác nhận thay đổi.

~~~java
@Transactional
public void assign(Long ticketId, Long staffId) {
    SupportTicket ticket = ticketRepository.findById(ticketId)
            .orElseThrow();

    StaffMember reference =
            staffRepository.getReferenceById(staffId);

    ticket.setAssignee(reference);

    entityManager.flush(); // FK violation có thể xuất hiện tại đây.
    // Commit xảy ra khi transaction kết thúc thành công.
}
~~~

Nếu FK được kiểm tra ngay tại câu lệnh, lỗi có thể phát sinh trong flush. Nếu database dùng deferred constraint, lỗi có thể xuất hiện khi commit. Nếu proxy bị khởi tạo trước đó, lỗi có thể xảy ra ngay tại getter.

### 4.5. Tổng hợp thời điểm lỗi

| Cách dùng | Điểm phát hiện | Kết quả có thể gặp |
|---|---|---|
| `findById` | SELECT | `Optional.empty()` |
| Provider kiểm tra ngay khi tạo reference | `getReferenceById` | Exception JPA/provider |
| Proxy được tạo rồi đọc thuộc tính | Proxy initialization | `EntityNotFoundException` hoặc exception provider |
| Gán reference rồi ghi FK | Flush/commit | Constraint violation |
| Không có FK, proxy không khởi tạo | Không có điểm kiểm tra chắc chắn | Có thể lưu FK mồ côi |

JPA `EntityNotFoundException` và lỗi FK là hai loại lỗi khác nhau. Loại thứ nhất xuất hiện khi provider cần trạng thái entity nhưng không tìm thấy. Loại thứ hai xuất hiện khi database từ chối dữ liệu ghi vi phạm ràng buộc.

## 5. Chọn API theo nguồn gốc của ID

### 5.1. ID từ request bên ngoài

Khi người dùng gửi `staffId`, service nên xác minh ID và áp dụng quy tắc nghiệp vụ:

~~~java
@Transactional
public Long openTicket(CreateTicketRequest request) {
    StaffMember assignee = staffRepository.findById(request.staffId())
            .orElseThrow(() ->
                    new StaffNotFoundException(request.staffId()));

    if (!assignee.isActive()) {
        throw new StaffCannotReceiveTicketException(request.staffId());
    }

    SupportTicket ticket = new SupportTicket(assignee);
    return ticketRepository.save(ticket).getId();
}
~~~

Cách này cho phép trả lỗi 404 hoặc lỗi nghiệp vụ rõ ràng trước khi ghi. Không để lỗi proxy muộn ở cuối transaction quyết định cách phản hồi request.

### 5.2. ID đã đáng tin cậy

Nếu quy trình nội bộ đã xác minh nhân viên và chỉ cần thiết lập quan hệ, có thể dùng reference:

~~~java
@Transactional
public void assignTicket(Long ticketId, Long staffId) {
    SupportTicket ticket = ticketRepository.findById(ticketId)
            .orElseThrow(() -> new TicketNotFoundException(ticketId));

    StaffMember reference =
            staffRepository.getReferenceById(staffId);

    ticket.setAssignee(reference);
}
~~~

Ví dụ giả định `staffId` đến từ nguồn đáng tin cậy và database có FK. Nếu không thể chấp nhận lỗi muộn khi ghi, dùng `findById` để xác minh.

### 5.3. Không kiểm tra hai lần bằng existsById rồi getReferenceById

~~~java
if (!staffRepository.existsById(staffId)) {
    throw new StaffNotFoundException(staffId);
}

StaffMember reference =
        staffRepository.getReferenceById(staffId);
~~~

Mẫu này thường tạo hai round trip. Nó cũng có race condition: bản ghi có thể bị xóa sau lần kiểm tra đầu tiên nhưng trước khi sử dụng reference.

Nếu cần entity, `findById` vừa kiểm tra vừa trả entity. Nếu chỉ cần reference và database có FK, dùng `getReferenceById` rồi để FK bảo vệ tính toàn vẹn khi ghi.

## 6. Bảo vệ quan hệ bằng foreign key

Nếu phiếu hỗ trợ bắt buộc có nhân viên phụ trách, mapping có thể là:

~~~java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "assignee_id", nullable = false)
private StaffMember assignee;
~~~

Database cũng cần bảo vệ điều kiện này:

~~~sql
alter table support_tickets
    alter column assignee_id set not null;

alter table support_tickets
    add constraint fk_ticket_assignee
    foreign key (assignee_id) references staff_members(id);
~~~

Cú pháp ALTER COLUMN thay đổi theo database. `NOT NULL` cấm quan hệ rỗng; FK bảo đảm ID tham chiếu có hàng đích. Hai ràng buộc này bổ sung cho nhau.

Nếu hệ thống có dữ liệu legacy, tìm tham chiếu mồ côi trước khi thêm FK:

~~~sql
select t.id, t.assignee_id
from support_tickets t
left join staff_members s on s.id = t.assignee_id
where t.assignee_id is not null
  and s.id is null;
~~~

Làm sạch dữ liệu theo quy tắc nghiệp vụ rồi mới thêm constraint. Tránh dùng `@NotFound(IGNORE)` để che mọi lỗi dữ liệu; annotation đó thay đổi cách Hibernate đọc quan hệ và không sửa giá trị FK sai trong bảng.

## 7. Lazy loading và hợp đồng JPA

`FetchType.LAZY` là hint cho provider; `FetchType.EAGER` là requirement. Điều đó có nghĩa mapping LAZY không đảm bảo provider luôn trì hoãn tải.

Các mặc định phổ biến:

| Mapping | Fetch mặc định |
|---|---|
| `@ManyToOne` | `FetchType.EAGER` |
| `@OneToOne` | `FetchType.EAGER` |
| `@OneToMany` | `FetchType.LAZY` |
| `@ManyToMany` | `FetchType.LAZY` |
| `@ElementCollection` | `FetchType.LAZY` |
| `@Basic` | `FetchType.EAGER` |

Đối với quan hệ ToOne, thường nên khai báo LAZY rồi chọn fetch plan ở query khi cần. Provider vẫn có thể tải sớm theo mapping, query hoặc giới hạn kỹ thuật.

### 7.1. Hibernate

Hibernate thường dùng proxy cho ToOne và persistent collection wrapper cho ToMany. Các giới hạn thực tế:

- Subclass proxy truyền thống bị hạn chế bởi entity hoặc method final.
- Bytecode enhancement có thể hỗ trợ lazy attribute loading.
- One-to-One phía inverse có thể cần truy vấn sớm để xác định association có null hay không.
- Truy cập proxy chưa khởi tạo sau khi Session đóng thường gây `LazyInitializationException`.
- `@NotFound` trên ToOne khiến Hibernate tải quan hệ eager, kể cả khi khai báo LAZY.

Hibernate có batch fetching để giảm số query khi khởi tạo nhiều proxy/collection:

~~~properties
spring.jpa.properties.hibernate.default_batch_fetch_size=32
~~~

Hoặc annotation riêng:

~~~java
@BatchSize(size = 32)
@Entity
public class StaffMember {
    // fields
}
~~~

Batch size cần được đo theo tải thực tế. Nó không thay thế fetch plan và không bảo đảm mọi truy vấn chỉ phát một SELECT.

### 7.2. EclipseLink

EclipseLink dùng indirection. Lazy ToOne trong Java SE phụ thuộc weaving:

- Dynamic weaving biến đổi bytecode lúc class được nạp.
- Static weaving biến đổi bytecode trước khi chạy.
- Nếu weaving không hoạt động, ToOne có thể tải sớm dù mapping đặt LAZY.

Ví dụ cấu hình riêng EclipseLink:

~~~xml
<property name="eclipselink.weaving" value="true"/>
<property name="eclipselink.weaving.lazy" value="true"/>
~~~

Đây là cấu hình riêng EclipseLink, không áp dụng cho Hibernate. Hãy kiểm tra cả build và cách khởi chạy JVM; chỉ thêm property mà không thực hiện weaving phù hợp chưa đủ.

### 7.3. @NotFound của Hibernate

Với dữ liệu legacy không có physical FK, Hibernate cung cấp `@NotFound`:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "legacy_assignee_id")
@NotFound(action = NotFoundAction.IGNORE)
private StaffMember assignee;
~~~

- `NotFoundAction.EXCEPTION` báo lỗi khi Hibernate phát hiện hàng đích không tồn tại; Hibernate hiện đại có thể ném `FetchNotFoundException`.
- `NotFoundAction.IGNORE` coi association không hợp lệ như `null`.

Đây là extension riêng Hibernate, không phải Jakarta Persistence. Quan hệ ToOne có `@NotFound` bị tải eager. Chỉ dùng khi phải hỗ trợ dữ liệu legacy và đã hiểu hệ quả; schema mới nên được bảo vệ bằng FK.

## 8. Giữ proxy trong ranh giới transaction

Một entity có thể được trả khỏi service trong khi association vẫn là proxy chưa khởi tạo:

~~~java
public SupportTicket findTicket(Long id) {
    return ticketRepository.findById(id).orElseThrow();
}

// Transaction đã đóng trước khi caller thực hiện:
String name =
        findTicket(12L).getAssignee().getDisplayName();
~~~

Nếu `assignee` chưa được tải, Hibernate thường ném `LazyInitializationException`. Cách an toàn là tải dữ liệu cần thiết trong service và trả DTO:

~~~java
public record TicketView(Long id, String assigneeName) {
}

@Transactional(readOnly = true)
public TicketView getView(Long id) {
    SupportTicket ticket =
            ticketRepository.findById(id).orElseThrow();

    return new TicketView(
            ticket.getId(),
            ticket.getAssignee().getDisplayName()
    );
}
~~~

Nếu query luôn cần assignee, dùng EntityGraph:

~~~java
@EntityGraph(attributePaths = "assignee")
Optional<SupportTicket> findWithAssigneeById(Long id);
~~~

Hoặc JPQL fetch join:

~~~java
@Query("""
       select t
       from SupportTicket t
       left join fetch t.assignee
       where t.id = :id
       """)
Optional<SupportTicket> findWithAssignee(@Param("id") Long id);
~~~

DTO projection phù hợp nếu chỉ cần một số cột. Có thể tắt OSIV để service phải xác định dữ liệu cần thiết trước khi trả response:

~~~properties
spring.jpa.open-in-view=false
~~~

OSIV có thể khiến serializer khởi tạo proxy và phát SQL trong lúc tạo JSON, làm truy vấn bị ẩn khỏi service và tạo N+1 ngoài ý muốn.

## 9. N+1 và phân trang

Giả sử tải nhiều phiếu rồi đọc tên từng nhân viên:

~~~java
List<SupportTicket> tickets = ticketRepository.findAll();

for (SupportTicket ticket : tickets) {
    System.out.println(ticket.getAssignee().getDisplayName());
}
~~~

Nếu mỗi proxy được khởi tạo riêng, có thể có một SELECT cho danh sách phiếu và thêm một SELECT cho từng nhân viên. Đây là N+1 query.

Cách xử lý:

1. EntityGraph nếu query luôn cần assignee.
2. JOIN FETCH cho một quan hệ cụ thể.
3. DTO projection nếu chỉ cần một số trường.
4. Batch fetching nếu cần khởi tạo nhiều proxy/collection.
5. Bật SQL logging hoặc Hibernate statistics trong test để đếm query.

Khi phân trang, có thể khai báo:

~~~java
Page<SupportTicket> findByStatus(
        TicketStatus status,
        Pageable pageable
);
~~~

Không nên fetch join nhiều collection cùng lúc trong query phân trang mà chưa xem xét số hàng SQL bị nhân lên. Với danh sách lớn, có thể phân trang ID trước rồi tải quan hệ cần thiết cho nhóm ID đó, hoặc dùng DTO projection.

## 10. Kiểm thử ID không tồn tại và thời điểm khởi tạo proxy

### 10.1. findById trả Optional rỗng

~~~java
@DataJpaTest
class StaffRepositoryTest {

    @Autowired
    private StaffRepository staffRepository;

    @Test
    void missingIdReturnsEmpty() {
        assertThat(staffRepository.findById(999999L)).isEmpty();
    }
}
~~~

Đây là contract dễ dự đoán: ID không tồn tại trả về Optional rỗng.

### 10.2. getReference có thể lỗi khi truy cập trạng thái

~~~java
@Test
void missingReferenceCanFailOnInitialization() {
    assertThatThrownBy(() -> {
        StaffMember reference =
                entityManager.getReference(StaffMember.class, 999999L);

        reference.getDisplayName();
    }).isInstanceOf(EntityNotFoundException.class);
}
~~~

Thời điểm và exception cụ thể phụ thuộc provider/version. Có provider có thể phát hiện lỗi ngay lúc lấy reference. Vì vậy, chạy test trên đúng provider thực tế và không giả định một exception wrapper duy nhất là portable.

### 10.3. Kiểm tra trạng thái tải bằng PersistenceUnitUtil

~~~java
PersistenceUnitUtil util =
        entityManagerFactory.getPersistenceUnitUtil();

SupportTicket ticket =
        entityManager.find(SupportTicket.class, ticketId);

boolean assigneeLoaded =
        util.isLoaded(ticket, "assignee");
~~~

API này giúp kiểm tra thuộc tính đã được tải hay chưa. Kết quả phản ánh mapping và fetch plan thực tế; LAZY là hint nên không giả định luôn false.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| getReferenceById trả object nhưng getter lỗi | Proxy trỏ đến hàng không tồn tại | Dùng findById khi cần xác minh |
| Lỗi chỉ xuất hiện khi commit | FK được kiểm tra lúc flush/commit | Bắt và dịch lỗi ở ranh giới transaction phù hợp |
| Ghi được ID mồ côi | Database không có FK | Làm sạch dữ liệu và thêm constraint |
| LazyInitializationException | Proxy chưa tải nhưng persistence context đã đóng | Tải dữ liệu trong service hoặc trả DTO |
| LAZY vẫn tải sớm | Provider được phép tải eager; query/fetch plan yêu cầu | Kiểm tra SQL, provider và mapping |
| N+1 khi duyệt danh sách | Mỗi proxy được khởi tạo riêng | EntityGraph, JOIN FETCH, projection hoặc batch |
| getClass() không bằng lớp entity | Runtime object là proxy subclass | Không phụ thuộc class equality |
| Test khác production | Provider/version/weaving khác nhau | Dùng integration test với cấu hình production |

## 12. Checklist lựa chọn

- [ ] ID từ request cần phản hồi 404: dùng `findById`.
- [ ] Chỉ cần tham chiếu theo ID đáng tin cậy: cân nhắc `getReferenceById`.
- [ ] Không coi việc tạo proxy là xác nhận hàng tồn tại.
- [ ] Có FK database cho quan hệ cần toàn vẹn.
- [ ] Phân biệt lỗi proxy initialization với constraint violation.
- [ ] Biết LAZY là hint và EAGER là requirement.
- [ ] Kiểm tra giới hạn proxy/weaving của provider.
- [ ] Không để serializer khởi tạo proxy ngoài transaction.
- [ ] Chọn EntityGraph, JOIN FETCH hoặc projection theo use case.
- [ ] Đo SQL và test với provider/version triển khai.

## 13. Tài liệu tham khảo

- [Jakarta Persistence 3.1 Specification](https://jakarta.ee/specifications/persistence/3.1/jakarta-persistence-spec-3.1.pdf) — hợp đồng của `EntityManager.getReference` và fetch type.
- [Spring Data JPA — JpaRepository Javadoc](https://docs.spring.io/spring-data/jpa/docs/current/api/org/springframework/data/jpa/repository/JpaRepository.html) — `findById` và `getReferenceById`.
- [Hibernate ORM User Guide](https://docs.hibernate.org/orm/6.2/userguide/html_single/) — proxy, lazy fetching, `@NotFound` và batch fetching.
- [EclipseLink Concepts](https://eclipse.dev/eclipselink/documentation/4.0/concepts/concepts.html) — indirection và weaving.
- [EclipseLink JPA Extensions](https://eclipse.dev/eclipselink/documentation/4.0/jpa/extensions/jpa-extensions.html) — thuộc tính lazy weaving.

Chọn `findById` khi ứng dụng cần biết chắc entity có tồn tại và cần dữ liệu để ra quyết định. Chọn `getReferenceById` khi chỉ cần thiết lập quan hệ bằng ID đã đáng tin cậy. Luôn dựa vào FK để bảo vệ dữ liệu, hiểu thời điểm provider khởi tạo proxy và thiết kế fetch plan trong transaction thay vì để lỗi xuất hiện bất ngờ ở tầng serialize response.
