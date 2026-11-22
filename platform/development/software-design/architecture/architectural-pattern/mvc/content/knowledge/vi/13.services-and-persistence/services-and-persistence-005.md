# Xác định ranh giới giao dịch

Trong ứng dụng MVC, một request thường đi qua Controller, dịch vụ ứng dụng, Model và repository để thực hiện một thao tác nghiệp vụ. Có thao tác chỉ cần đọc một bản ghi, nhưng cũng có thao tác gồm nhiều bước phải cùng thành công hoặc cùng thất bại. **Ranh giới giao dịch (transaction boundary)** xác định khoảng công việc mà hệ thống cam kết tính nhất quán dữ liệu: khi giao dịch commit, các thay đổi được chấp nhận; khi rollback, các thay đổi thuộc giao dịch bị hủy theo cơ chế của hệ thống lưu trữ.

Ranh giới này nên được xác định theo **use case nghiệp vụ**, tức một thao tác có ý nghĩa đối với người dùng hoặc hệ thống, thay vì đặt tùy tiện quanh từng câu lệnh SQL hay toàn bộ vòng đời HTTP request. Controller chịu trách nhiệm tiếp nhận request và tạo response; application service thường điều phối use case và mở ranh giới giao dịch; Model bảo vệ bất biến; repository thực hiện truy cập dữ liệu.

Nếu giao dịch quá nhỏ, một thao tác nghiệp vụ có thể chỉ hoàn thành một nửa. Nếu giao dịch quá rộng, hệ thống giữ khóa và kết nối lâu, tăng xung đột, giảm khả năng mở rộng và khó xử lý tác dụng phụ bên ngoài. Thiết kế tốt cần xác định dữ liệu nào phải thay đổi nguyên tử, khi nào commit, điều gì cần rollback và phần nào phải thực hiện sau commit.

## 1. Giao dịch là gì?

Giao dịch (transaction) là một đơn vị công việc trên dữ liệu mà hệ quản trị hoặc transaction manager điều phối theo các thuộc tính nhất quán đã cấu hình. Trong cơ sở dữ liệu quan hệ, giao dịch thường bao gồm một hoặc nhiều thao tác đọc/ghi. Các thay đổi chỉ được xác nhận khi commit; nếu giao dịch rollback, hệ quản trị hủy các thay đổi chưa commit thuộc giao dịch đó.

Ví dụ, thao tác chuyển tiền giữa hai tài khoản cần:

1. Đọc số dư tài khoản gửi và nhận.
2. Kiểm tra tài khoản gửi đủ tiền và cả hai tài khoản hợp lệ.
3. Trừ tiền tài khoản gửi.
4. Cộng tiền tài khoản nhận.
5. Ghi lịch sử chuyển tiền.
6. Commit toàn bộ thay đổi.

Nếu bước trừ tiền đã lưu nhưng bước cộng tiền thất bại, hệ thống không được để tiền biến mất. Các thay đổi liên quan cần nằm trong cùng một giao dịch dữ liệu.

~~~mermaid
flowchart TD
    A["Bắt đầu giao dịch"] --> B["Đọc và kiểm tra dữ liệu"]
    B --> C["Cập nhật tài khoản gửi"]
    C --> D["Cập nhật tài khoản nhận"]
    D --> E["Ghi lịch sử"]
    E --> F{"Tất cả bước thành công?"}
    F -->|Có| G["COMMIT"]
    F -->|Không| H["ROLLBACK"]
    G --> I["Kết quả được xác nhận"]
    H --> J["Không giữ các thay đổi chưa commit"]
~~~

Giao dịch không phải một cách gọi khác của phương thức service. Một phương thức có thể không mở giao dịch, tham gia giao dịch do bên gọi mở hoặc tạo giao dịch mới tùy cấu hình. Cần hiểu ranh giới thực tế do framework và transaction manager tạo ra.

## 2. Bốn thuộc tính ACID

ACID là bốn thuộc tính thường dùng để mô tả giao dịch cơ sở dữ liệu:

| Thuộc tính | Ý nghĩa | Ví dụ |
|---|---|---|
| **Atomicity – Tính nguyên tử** | Các thay đổi trong giao dịch được commit cùng nhau hoặc rollback theo cơ chế giao dịch | Trừ và cộng tiền phải cùng thành công |
| **Consistency – Tính nhất quán** | Giao dịch đưa dữ liệu từ một trạng thái hợp lệ sang trạng thái hợp lệ theo ràng buộc đã định nghĩa | Số dư không âm nếu nghiệp vụ và constraint yêu cầu |
| **Isolation – Tính cô lập** | Các giao dịch đồng thời được quan sát theo mức cô lập đã chọn | Hai thao tác cập nhật không đọc/ghi dữ liệu theo cách tạo kết quả không hợp lệ |
| **Durability – Tính bền vững** | Sau khi commit thành công, dữ liệu được lưu bền vững theo cam kết của hệ quản trị | Bản ghi đơn hàng vẫn tồn tại sau khi ứng dụng khởi động lại |

ACID không có nghĩa mọi quy tắc nghiệp vụ tự động được bảo vệ. Database chỉ bảo vệ các ràng buộc được mô hình hóa và thực thi, chẳng hạn NOT NULL, UNIQUE, FOREIGN KEY, CHECK, khóa và giao dịch. Quy tắc như “đơn đã giao không thể hủy” vẫn cần được kiểm tra trong Model hoặc use case.

Tính cô lập cũng có nhiều mức. Mức cô lập thấp hơn có thể cho phép một số hiện tượng đọc đồng thời; mức cao hơn thường tốn tài nguyên hoặc làm tăng khả năng transaction phải retry. Cần chọn mức phù hợp với yêu cầu nghiệp vụ và hành vi thực tế của database.

## 3. Đặt ranh giới giao dịch theo use case

Trong MVC, Controller không nên mở một giao dịch riêng cho từng repository rồi tự điều phối commit/rollback. Một thao tác nghiệp vụ thường có nhiều bước và cần một nơi hiểu toàn bộ ý nghĩa của thao tác. Application service hoặc use case là vị trí phù hợp để đặt ranh giới đó.

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant C as Controller
    participant S as Application Service
    participant M as Model
    participant R as Repository
    User->>C: POST /orders/{id}/approve
    C->>S: approve(command)
    S->>R: begin transaction / load order
    R-->>S: Order
    S->>M: kiểm tra và chuyển trạng thái
    S->>R: lưu thay đổi
    S->>R: commit
    S-->>C: kết quả use case
    C-->>User: HTTP response
~~~

Một use case duyệt đơn có thể cần tải đơn, kiểm tra quyền, kiểm tra trạng thái, cập nhật người duyệt và ghi lịch sử. Những thao tác ghi dữ liệu phải cùng nằm trong ranh giới giao dịch nếu nghiệp vụ yêu cầu chúng cùng thành công.

Ví dụ Spring:

~~~java
@Service
class ApproveOrderService {
    private final OrderRepository orders;
    private final ApprovalHistoryRepository history;

    ApproveOrderService(
        OrderRepository orders,
        ApprovalHistoryRepository history
    ) {
        this.orders = orders;
        this.history = history;
    }

    @Transactional
    public ApprovalResult approve(ApproveOrderCommand command) {
        Order order = orders.findById(command.orderId())
            .orElseThrow(OrderNotFoundException::new);

        order.approve(command.approverId());

        history.save(new ApprovalHistory(
            order.getId(),
            command.approverId()
        ));

        return new ApprovalResult(order.getId(), order.getStatus());
    }
}
~~~

Ở ví dụ này, transaction bao quanh thao tác nghiệp vụ duyệt đơn. Nếu lưu lịch sử thất bại và exception khiến giao dịch rollback, thay đổi trạng thái đơn cũng không được commit. Điều này phụ thuộc repository dùng cùng transaction manager và cùng cơ chế giao dịch.

Controller giữ phần HTTP:

~~~java
@PostMapping("/{id}/approval")
ResponseEntity<ApprovalResponse> approve(
    @PathVariable UUID id,
    @AuthenticationPrincipal AppPrincipal principal
) {
    ApprovalResult result = approveOrderService.approve(
        new ApproveOrderCommand(id, principal.userId())
    );

    return ResponseEntity.ok(
        new ApprovalResponse(result.orderId(), result.status())
    );
}
~~~

Controller không cần biết khi nào connection commit hoặc rollback. Nó chuyển request thành command và biểu diễn kết quả thành HTTP response.

### 3.1. Không phải mọi thao tác đọc đều cần giao dịch dài

Một truy vấn đọc đơn giản có thể chạy trong giao dịch chỉ đọc ngắn hoặc theo cơ chế mặc định của repository/framework. Việc đặt `@Transactional(readOnly = true)` ở dịch vụ truy vấn có thể thể hiện ý định và cho phép framework/ORM tối ưu trong một số trường hợp.

Tuy nhiên, readOnly thường là một hint hoặc cấu hình tối ưu; không nên coi nó là cơ chế bảo mật bảo đảm mọi câu lệnh ghi đều bị cấm. Hành vi phụ thuộc transaction manager, ORM và database.

Nếu một use case đọc nhiều dữ liệu cần cùng một snapshot nhất quán, cần cân nhắc ranh giới và isolation. Nếu mỗi truy vấn có thể quan sát thời điểm khác nhau, kết quả tổng hợp có thể không phản ánh một trạng thái thống nhất.

### 3.2. Không kéo dài giao dịch qua thời gian người dùng suy nghĩ

Không nên mở transaction khi hiển thị form rồi giữ transaction cho đến khi người dùng gửi form vài phút sau. Người dùng có thể rời trang, mất kết nối hoặc mở nhiều tab. Giữ transaction lâu sẽ giữ connection và có thể giữ khóa, làm tăng contention.

Thay vào đó:
- GET đọc dữ liệu và trả form trong một lần xử lý ngắn.
- Người dùng chỉnh sửa ngoài transaction.
- POST gửi dữ liệu mới trong request khác.
- Use case cập nhật mở transaction ngắn, kiểm tra phiên bản và commit.

Nếu cần phát hiện dữ liệu đã thay đổi giữa lúc hiển thị và lúc gửi form, dùng optimistic locking, version hoặc ETag thay vì giữ transaction xuyên suốt thời gian người dùng thao tác.

## 4. Ranh giới giao dịch không nhất thiết trùng với ranh giới HTTP

Một request HTTP có thể gọi một use case duy nhất, nhiều use case hoặc chỉ đọc dữ liệu. Một use case cũng có thể được gọi từ HTTP, message consumer, lịch chạy nền hoặc một tác vụ nội bộ.

Vì vậy, đặt giao dịch quanh use case giúp hành vi nhất quán dù nguồn gọi thay đổi. Nếu chỉ mở transaction ở Controller, các luồng gọi khác có thể bỏ qua giao dịch. Nếu mở giao dịch cho toàn bộ request, thời gian giao dịch có thể kéo dài qua binding, xử lý response hoặc các công việc không cần truy cập database.

Ví dụ:
- Một request GET có thể gọi một query service chạy read-only.
- Một request POST tạo đơn gọi use case có transaction.
- Một message consumer gọi cùng use case tạo đơn mà không đi qua Controller.
- Một tác vụ nền gọi use case cập nhật trạng thái và dùng cùng quy tắc giao dịch.

Ranh giới nên được xác định từ tính nguyên tử của thao tác nghiệp vụ, không phải chỉ từ annotation trên endpoint.

## 5. Spring `@Transactional` hoạt động như thế nào?

Trong Spring, `@Transactional` khai báo metadata cho transaction infrastructure. Với cấu hình proxy-based phổ biến, Spring tạo proxy bao quanh bean và mở hoặc tham gia giao dịch khi phương thức được gọi qua proxy. Khi phương thức kết thúc bình thường, transaction được commit; khi exception phù hợp thoát ra ngoài, transaction được rollback theo quy tắc.

~~~java
@Service
class TaskService {
    private final TaskRepository repository;

    TaskService(TaskRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void complete(UUID taskId) {
        Task task = repository.findById(taskId)
            .orElseThrow(TaskNotFoundException::new);

        task.complete();
    }
}
~~~

Với JPA, entity được quản lý trong persistence context. Khi thuộc tính thay đổi, ORM có thể phát hiện thay đổi và ghi SQL khi flush hoặc commit. Không nhất thiết phải gọi repository.save cho mọi thay đổi trên entity đang được quản lý, dù việc gọi save có thể là một phần của abstraction repository trong dự án.

### 5.1. Gọi nội bộ cùng lớp và proxy

Một giới hạn quan trọng của proxy-based transaction là lời gọi phương thức nội bộ trong cùng object (self-invocation) thường không đi qua proxy. Do đó, annotation trên phương thức được gọi nội bộ có thể không được áp dụng như kỳ vọng.

Ví dụ:

~~~java
@Service
class ImportService {

    public void importAll(List<Row> rows) {
        for (Row row : rows) {
            importOne(row);
        }
    }

    @Transactional
    public void importOne(Row row) {
        // lưu một dòng
    }
}
~~~

Nếu importAll được gọi qua proxy nhưng gọi this.importOne nội bộ, lời gọi importOne không đi qua proxy; transaction annotation ở importOne có thể không tạo transaction riêng. Cần thiết kế ranh giới rõ hơn, chẳng hạn đặt thao tác transactional trong bean khác và gọi qua dependency, hoặc đặt transaction ở importAll nếu toàn bộ import là một đơn vị nguyên tử.

Không nên tách bean chỉ để né một quy tắc kỹ thuật mà không xét ý nghĩa giao dịch. Cần xác định mong muốn: cả lô phải cùng thành công, hay mỗi dòng là một giao dịch độc lập?

### 5.2. Visibility và phương thức transactional

Khả năng áp dụng proxy phụ thuộc loại proxy và cấu hình Spring. Với proxy interface hoặc class-based, các giới hạn về visibility và phương thức final/private có thể khác nhau theo cơ chế. Trong ứng dụng thông thường, nên đặt `@Transactional` trên phương thức public của application service được gọi qua Spring bean proxy, trừ khi dự án chủ động dùng cơ chế khác.

### 5.3. Transaction gắn với thread trong mô hình imperative

Trong mô hình Spring imperative/JDBC/JPA thông thường, transaction context được gắn với thread hiện tại. Nếu trong một phương thức transactional gọi executor hoặc `CompletableFuture` để chạy công việc trên thread khác, giao dịch hiện tại không tự truyền sang thread đó.

Không nên giả định:

~~~java
@Transactional
public void updateAndRunAsync() {
    repository.updateSomething();

    executor.execute(() -> {
        repository.updateSomethingElse();
    });
}
~~~

Hai thao tác có thể chạy trong hai transaction hoặc không có transaction như mong đợi. Nếu công việc bất đồng bộ phải thực hiện sau khi giao dịch chính commit, hãy phát sự kiện sau commit hoặc dùng outbox. Nếu cần một giao dịch riêng cho tác vụ nền, hãy để worker gọi một use case transactional độc lập.

Trong Spring reactive, transaction context có thể được quản lý qua Reactor Context thay vì thread-bound. Không áp dụng máy móc giả định của JDBC/JPA imperative cho reactive stack.

## 6. Propagation: giao dịch mới hay tham gia giao dịch hiện tại?

Propagation xác định hành vi khi một phương thức transactional được gọi trong lúc đã có hoặc chưa có giao dịch.

| Propagation | Hành vi phổ biến | Khi nào cân nhắc |
|---|---|---|
| `REQUIRED` | Tham gia giao dịch hiện tại; nếu chưa có thì tạo mới | Mặc định phù hợp với phần lớn use case và dịch vụ con |
| `REQUIRES_NEW` | Tạm ngưng giao dịch hiện tại và tạo giao dịch mới | Ghi nhận độc lập phải commit dù giao dịch ngoài rollback, sau khi đánh giá kỹ |
| `SUPPORTS` | Tham gia nếu có; nếu không thì chạy không có giao dịch | Logic có thể hoạt động ở cả hai ngữ cảnh |
| `MANDATORY` | Yêu cầu phải có giao dịch hiện tại, nếu không thì lỗi | Thành phần chỉ được gọi trong một use case transactional |
| `NOT_SUPPORTED` | Tạm ngưng giao dịch hiện tại và chạy không có giao dịch | Công việc không nên nằm trong transaction đang mở |
| `NEVER` | Yêu cầu không có giao dịch hiện tại | Bảo đảm một thao tác không chạy bên trong transaction |
| `NESTED` | Giao dịch lồng nhau thường dựa trên savepoint nếu transaction manager hỗ trợ | Rollback một phần trong giao dịch ngoài khi có hỗ trợ phù hợp |

Mặc định `REQUIRED` thường là lựa chọn hợp lý. Nếu Controller gọi service A và service A gọi service B, cả hai thường tham gia cùng một transaction vật lý. Nếu B thất bại theo quy tắc rollback, transaction chung có thể bị đánh dấu rollback-only.

### 6.1. Cẩn trọng với REQUIRES_NEW

`REQUIRES_NEW` tạo transaction độc lập. Nó có thể hữu ích khi cần ghi một bản ghi audit độc lập với thao tác chính, nhưng cần đánh giá hậu quả: audit có thể commit trong khi nghiệp vụ chính rollback. Điều này có thể đúng nếu audit ghi nhận “đã thử thao tác”, nhưng sai nếu audit khẳng định thao tác đã thành công.

Transaction mới cũng có thể cần thêm connection trong khi transaction ngoài đang bị tạm ngưng. Dùng quá nhiều `REQUIRES_NEW` có thể làm cạn connection pool hoặc tạo thời gian chờ khóa.

### 6.2. NESTED không đồng nghĩa với transaction phân tán

Nested transaction thường dựa trên savepoint trong cùng transaction vật lý và chỉ được hỗ trợ bởi một số transaction manager/nguồn dữ liệu. Nó không biến hai database hoặc một database và một message broker thành một giao dịch nguyên tử chung.

Hãy kiểm tra transaction manager thực tế và khả năng hỗ trợ trước khi dựa vào `NESTED`.

## 7. Isolation và các hiện tượng đọc đồng thời

Isolation xác định giao dịch này có thể quan sát thay đổi của giao dịch khác như thế nào. Các mức thường gặp trong JDBC/Spring:

| Mức | Đặc điểm khái quát | Rủi ro/đánh đổi |
|---|---|---|
| READ_UNCOMMITTED | Có thể đọc dữ liệu chưa commit | Dirty read có thể xảy ra nếu database hỗ trợ mức này |
| READ_COMMITTED | Chỉ đọc dữ liệu đã commit | Một truy vấn lặp lại có thể thấy giá trị mới sau commit của transaction khác |
| REPEATABLE_READ | Dữ liệu đã đọc thường ổn định trong giao dịch theo định nghĩa database | Phantom và chi tiết triển khai khác nhau giữa hệ quản trị |
| SERIALIZABLE | Mục tiêu tương đương thực thi tuần tự | Có thể giảm concurrency, phát sinh lỗi serialization/retry |
| DEFAULT | Dùng mức mặc định của transaction manager/database | Cần hiểu cấu hình thực tế |

Các hiện tượng thường được nhắc đến:

- **Dirty read:** đọc thay đổi chưa commit của giao dịch khác.
- **Non-repeatable read:** cùng một hàng được đọc lại nhưng giá trị đã thay đổi do giao dịch khác commit.
- **Phantom read:** truy vấn cùng điều kiện trả về tập hàng khác do giao dịch khác thêm/xóa hàng phù hợp.
- **Lost update:** hai thao tác ghi dựa trên dữ liệu cũ làm mất một thay đổi; cách phát sinh và xử lý phụ thuộc câu lệnh, khóa và isolation.

Tên mức isolation không bảo đảm mọi database triển khai giống hệt nhau. Một số hệ quản trị dùng MVCC, một số dùng khóa khác nhau; READ_COMMITTED trên hai hệ thống có thể có đặc tính vận hành khác. Cần đọc tài liệu database đang sử dụng và kiểm thử các luồng cạnh tranh quan trọng.

### 7.1. Chọn isolation theo quy tắc nghiệp vụ

Không nên tăng mọi giao dịch lên SERIALIZABLE chỉ để “an toàn hơn”. Mức cô lập cao có thể tạo contention hoặc lỗi serialization. Thay vào đó:

- Dùng constraint database để bảo vệ điều kiện đơn giản như unique.
- Dùng optimistic locking khi xung đột không thường xuyên và có thể yêu cầu client thử lại.
- Dùng pessimistic locking khi cần tuần tự hóa thao tác trên tài nguyên cụ thể.
- Dùng isolation phù hợp với truy vấn cần snapshot nhất quán.
- Thiết kế lại thao tác thành câu lệnh atomic khi có thể.

Ví dụ, đặt chỗ một ghế cần bảo đảm chỉ một người có thể đặt. Một câu lệnh cập nhật có điều kiện hoặc unique constraint có thể bảo vệ tốt hơn việc chỉ đọc trạng thái rồi cập nhật mà không khóa.

## 8. Rollback: khi nào giao dịch bị hủy?

Khi lỗi xảy ra, ứng dụng cần xác định có nên rollback các thay đổi hay không. Trong Spring transaction management theo mặc định phổ biến, RuntimeException và Error làm rollback; checked exception thường không tự động rollback nếu không cấu hình thêm.

Ví dụ:

~~~java
@Transactional
public void register(RegisterCommand command) throws DuplicateEmailException {
    userRepository.save(User.create(command.email()));

    if (command.requiresExternalCheck()) {
        throw new DuplicateEmailException();
    }
}
~~~

Nếu DuplicateEmailException là checked exception, giao dịch có thể không rollback theo mặc định. Có thể khai báo rõ:

~~~java
@Transactional(rollbackFor = DuplicateEmailException.class)
public void register(RegisterCommand command)
        throws DuplicateEmailException {
    // ...
}
~~~

Hoặc thiết kế exception nghiệp vụ phù hợp với chính sách rollback của ứng dụng. Đừng thay mọi exception thành RuntimeException chỉ để buộc rollback; cần phân loại lỗi và quy định rõ lỗi nào làm giao dịch không thể tiếp tục.

### 8.1. Bắt exception rồi tiếp tục có thể gây commit ngoài ý muốn

Nếu một phương thức transactional bắt exception bên trong rồi không ném lại, transaction có thể kết thúc bình thường và commit, tùy transaction đã bị đánh dấu rollback-only hay chưa.

~~~java
@Transactional
public void process() {
    try {
        repository.updateA();
        repository.updateB();
    } catch (DataAccessException exception) {
        log.warn("Cập nhật thất bại", exception);
        // Tiếp tục bình thường có thể khiến transaction commit nếu chưa rollback-only
    }
}
~~~

Không nên nuốt lỗi rồi trả thành công. Nếu không thể tiếp tục, hãy ném lỗi phù hợp hoặc chủ động đánh dấu rollback theo API transaction. Nếu có thể xử lý từng phần, hãy thiết kế từng phần thành use case/transaction riêng với ngữ nghĩa rõ ràng.

### 8.2. Lỗi xuất hiện lúc flush hoặc commit

Với ORM, một số lỗi không xuất hiện ngay tại lời gọi save. SQL có thể được gửi khi flush hoặc commit. Ví dụ unique constraint có thể chỉ bị phát hiện khi database thực thi câu lệnh. Vì vậy, việc phương thức service chạy hết mà chưa thấy exception không luôn có nghĩa giao dịch đã commit thành công; transaction interceptor còn phải hoàn tất commit.

## 9. Persistence context và ranh giới giao dịch

Với JPA/Hibernate, persistence context theo dõi entity đang được quản lý. Trong một transaction, thay đổi trên entity có thể được ghi xuống database khi flush. Ranh giới giao dịch ảnh hưởng đến:

- Khi nào entity được tải và trở thành managed.
- Khi nào thay đổi được flush.
- Khi nào lazy relationship còn có thể được truy cập.
- Khi nào lock được giữ.
- Khi nào lỗi constraint được phát hiện.
- Khi nào dữ liệu được commit và trở nên nhìn thấy với transaction khác.

Không nên dựa vào việc View truy cập lazy relationship sau khi transaction đã đóng. Hãy truy vấn và chuẩn bị dữ liệu cần thiết trong use case, rồi chuyển thành DTO/ViewModel trước khi trả response.

### 9.1. Flush không phải commit

Flush đồng bộ các thay đổi của persistence context xuống database trong transaction hiện tại. Các thay đổi vẫn chưa được xác nhận cuối cùng cho đến khi commit. Nếu sau flush giao dịch rollback, thay đổi vẫn có thể bị hủy.

Không nên gọi flush sau mọi thao tác một cách máy móc. Flush sớm có thể giúp phát hiện lỗi constraint trước một bước xử lý tiếp theo, nhưng cũng có thể tạo thêm SQL và ảnh hưởng hiệu năng.

### 9.2. Open Session in View không thay thế ranh giới giao dịch

Một số ứng dụng bật Open Session in View để persistence context còn mở trong quá trình render View. Điều đó có thể cho phép lazy loading khi template được dựng, nhưng không có nghĩa giao dịch ghi dữ liệu nên kéo dài đến hết response, cũng không nên để View điều khiển truy vấn database.

Thiết kế rõ hơn là tải dữ liệu cần thiết trong application service/query service, tạo DTO cho View và đóng transaction ở ranh giới use case.

## 10. Tác dụng phụ bên ngoài không tự rollback cùng database

Một giao dịch database không thể tự động hoàn tác email đã gửi, HTTP request đã gửi sang dịch vụ khác, file đã ghi vào object storage hoặc message đã được broker nhận. Đây là điểm quan trọng khi use case vừa thay đổi dữ liệu vừa tương tác hệ thống ngoài.

Ví dụ không an toàn:

~~~java
@Transactional
public void approve(UUID orderId) {
    Order order = orderRepository.findById(orderId).orElseThrow();
    order.approve();

    emailClient.sendApproval(order); // Gửi thành công ngay lập tức
    // Sau đó database commit thất bại
}
~~~

Nếu email đã được gửi nhưng commit thất bại, người nhận nhận thông báo đơn đã duyệt trong khi database vẫn ghi đơn ở trạng thái chờ duyệt. Rollback database không thu hồi email đã gửi.

Cũng không nên giữ transaction và database connection mở trong khi chờ một dịch vụ mạng chậm nếu có thể tránh. Thời gian chờ ngoài database làm tăng thời gian giữ connection/lock và khiến hệ thống dễ cạn tài nguyên khi dịch vụ phụ thuộc chậm.

### 10.1. Gửi tác dụng phụ sau commit

Với tác dụng phụ đơn giản, có thể đăng ký xử lý sau khi transaction commit. Trong Spring, `@TransactionalEventListener(phase = AFTER_COMMIT)` có thể lắng nghe sự kiện chỉ sau khi transaction thành công.

~~~java
public record OrderApprovedEvent(UUID orderId) {}

@Service
class ApproveOrderService {
    private final ApplicationEventPublisher events;

    @Transactional
    public void approve(UUID orderId) {
        // cập nhật đơn và lưu lịch sử
        events.publishEvent(new OrderApprovedEvent(orderId));
    }
}

@Component
class ApprovalNotificationListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderApprovedEvent event) {
        // gửi thông báo sau khi transaction đã commit
    }
}
~~~

Cách này tránh gửi thông báo trước khi commit. Tuy nhiên, listener chạy sau commit trong bộ nhớ không tự bảo đảm sự kiện được giao bền vững nếu tiến trình chết ngay sau commit và trước khi listener hoàn tất. Với tác dụng phụ quan trọng, cần cơ chế lưu sự kiện bền vững.

### 10.2. Transactional Outbox

Transactional Outbox ghi thay đổi nghiệp vụ và một bản ghi sự kiện vào cùng database transaction. Một worker đọc outbox sau đó gửi message hoặc gọi dịch vụ ngoài. Nhờ vậy, việc commit dữ liệu và ghi nhận ý định phát sự kiện là nguyên tử trong cùng database.

~~~mermaid
flowchart TD
    A["Use case bắt đầu transaction"] --> B["Cập nhật đơn hàng"]
    B --> C["Ghi bản ghi Outbox"]
    C --> D["COMMIT cùng transaction"]
    D --> E["Worker đọc Outbox"]
    E --> F["Gửi message / gọi dịch vụ"]
    F --> G["Đánh dấu đã xử lý"]
~~~

Worker có thể gửi lại nếu không nhận được xác nhận, vì vậy consumer cần xử lý idempotent hoặc lưu trạng thái xử lý theo event ID. Outbox giúp tránh mất sự kiện giữa commit database và publish message, nhưng không biến việc gửi message thành exactly-once tuyệt đối trong mọi tình huống.

### 10.3. Saga cho quy trình qua nhiều hệ thống

Nếu một use case trải qua nhiều dịch vụ hoặc database độc lập, một transaction ACID cục bộ thường không bao trùm tất cả. Saga chia quy trình thành các giao dịch cục bộ, mỗi bước có thể có hành động bù trừ (compensation) nếu bước sau thất bại.

Ví dụ đặt hàng có thể:
1. Tạo đơn ở trạng thái chờ.
2. Giữ tồn kho.
3. Yêu cầu thanh toán.
4. Xác nhận đơn.

Nếu thanh toán thất bại sau khi đã giữ hàng, bước bù trừ có thể giải phóng tồn kho và đánh dấu đơn thất bại. Compensation là một thao tác nghiệp vụ mới, không phải rollback vật lý của transaction đã commit.

## 11. Transaction và cập nhật đồng thời

Một ranh giới transaction đúng không tự giải quyết mọi xung đột giữa các request. Hai giao dịch vẫn có thể cùng đọc một trạng thái và cố gắng cập nhật. Cần chọn chiến lược concurrency control phù hợp.

### 11.1. Optimistic locking

Optimistic locking giả định xung đột không thường xuyên. Entity có trường version; khi cập nhật, ORM kiểm tra version hiện tại. Nếu một giao dịch khác đã cập nhật trước, thao tác thất bại thay vì âm thầm ghi đè.

~~~java
@Entity
class InventoryItem {
    @Id
    private UUID id;

    @Version
    private long version;

    private int availableQuantity;
}
~~~

Khi version không còn khớp, ứng dụng có thể trả lỗi xung đột và yêu cầu client tải lại hoặc thử lại theo quy tắc. Không retry mù quáng nếu thao tác có tác dụng phụ hoặc không idempotent.

### 11.2. Pessimistic locking

Pessimistic locking đặt khóa ở database để ngăn giao dịch khác sửa tài nguyên trong thời gian khóa. Nó có thể phù hợp khi tranh chấp cao và cần tuần tự hóa thao tác.

Ví dụ repository có thể dùng lock mode PESSIMISTIC_WRITE để tải bản ghi cần cập nhật. Cần giữ transaction ngắn vì khóa có thể làm request khác phải chờ. Thứ tự lấy nhiều khóa cũng cần nhất quán để giảm deadlock.

### 11.3. Constraint database là lớp bảo vệ cuối

Một kiểm tra trong Java như “email chưa tồn tại” có thể bị hai request vượt qua cùng lúc:

1. Request A kiểm tra email chưa có.
2. Request B kiểm tra email chưa có.
3. A insert.
4. B insert.

Unique constraint ở database bảo vệ tính duy nhất ngay cả khi hai request chạy đồng thời. Ứng dụng cần bắt lỗi constraint và chuyển thành phản hồi phù hợp. Kiểm tra ở application service vẫn hữu ích cho trải nghiệm, nhưng không thay thế constraint.

## 12. Thời lượng giao dịch và hiệu năng

Giao dịch càng dài, hệ thống càng có thể giữ connection, khóa và snapshot lâu. Điều này làm tăng áp lực lên connection pool, giảm khả năng xử lý đồng thời và tăng xác suất deadlock hoặc timeout.

Nên:
- Tải dữ liệu cần thiết trong phạm vi use case.
- Tránh gọi dịch vụ mạng chậm trong transaction database.
- Không chờ người dùng nhập dữ liệu trong khi transaction đang mở.
- Tránh xử lý tệp lớn hoặc tính toán lâu bên trong transaction nếu không cần.
- Dùng batch hợp lý, chia lô khi nghiệp vụ cho phép.
- Đo thời gian transaction và truy vấn chậm bằng log/metrics.
- Giữ thứ tự truy cập tài nguyên nhất quán khi nhiều transaction cần cùng tập khóa.

Không nên chia một use case thành nhiều transaction nhỏ chỉ để giảm thời gian nếu việc chia làm mất tính nguyên tử cần thiết. Nếu quy trình dài không thể nằm trong một transaction ngắn, hãy xem xét trạng thái trung gian và mô hình saga thay vì giả vờ rằng nhiều commit riêng là một giao dịch duy nhất.

## 13. Kiểm thử ranh giới giao dịch

Kiểm thử cần xác minh cả kết quả thành công và hành vi rollback. Một test chỉ kiểm tra response HTTP 200 không chứng minh database đã lưu đúng hoặc các bước liên quan cùng rollback.

| Phạm vi | Điều cần xác minh |
|---|---|
| Application service | Use case mở đúng transaction và điều phối các bước cần thiết |
| Repository/persistence | Thay đổi được commit, constraint được thực thi, rollback hủy dữ liệu |
| Rollback policy | Runtime và checked exception được xử lý theo cấu hình |
| Propagation | REQUIRED/REQUIRES_NEW/NESTED có hành vi đúng với mục đích |
| Concurrency | Optimistic/pessimistic lock và unique constraint xử lý xung đột |
| External side effects | Email/message không được gửi trước commit; outbox có thể retry |
| MVC Controller | HTTP response phản ánh kết quả use case và lỗi đã phân loại |

### 13.1. Kiểm thử rollback

Một kịch bản hữu ích là:
1. Gọi use case thực hiện hai thay đổi dữ liệu.
2. Cố ý làm bước thứ hai thất bại.
3. Kết thúc transaction và kiểm tra database.
4. Xác minh thay đổi thứ nhất cũng không còn nếu hai bước thuộc cùng transaction.

Trong Spring Test, test method có thể tự chạy trong transaction và rollback khi kết thúc. Điều đó tiện cho test dữ liệu, nhưng có thể che giấu hành vi commit thật của use case. Với kiểm thử transaction boundary, cần kiểm soát transaction của test và có thể dùng TransactionTemplate hoặc kiểm tra từ transaction độc lập sau khi use case kết thúc.

### 13.2. Kiểm thử tác dụng phụ

Dùng test double cho email client hoặc message publisher để xác minh:
- Không phát thông báo nếu transaction rollback.
- Sự kiện được phát sau commit nếu dùng after-commit listener.
- Outbox được ghi cùng transaction với dữ liệu nghiệp vụ.
- Worker có thể xử lý lại cùng event mà không tạo tác dụng phụ trùng lặp ngoài ý muốn.

### 13.3. Kiểm thử concurrency

Có thể tạo hai transaction cùng đọc một version rồi đồng thời cập nhật để xác minh optimistic locking. Với unique constraint, gửi hai request cạnh tranh tạo cùng một khóa duy nhất và xác minh chỉ một request thành công.

Kiểm thử đồng thời cần đồng bộ điểm bắt đầu và xác minh trạng thái database cuối. Không nên dựa vào sleep tùy ý vì kết quả có thể thay đổi theo tốc độ máy và lịch lập lịch thread.

## 14. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Mỗi repository tự mở transaction độc lập cho một use case nhiều bước | Một phần nghiệp vụ có thể commit trong khi phần khác thất bại | Đặt transaction quanh use case |
| Mở transaction cho toàn bộ thời gian người dùng điền form | Giữ connection/lock quá lâu | Dùng request riêng và optimistic locking |
| Gọi email hoặc HTTP service trước commit | Tác dụng phụ có thể xảy ra dù database rollback | Xử lý sau commit hoặc dùng outbox |
| Dùng REQUIRES_NEW ở mọi service con | Tạo commit độc lập ngoài ý muốn, tốn connection | Dùng REQUIRED trừ khi có lý do rõ |
| Bắt exception rồi trả thành công | Transaction có thể commit dữ liệu chưa hoàn chỉnh | Ném lỗi phù hợp hoặc đánh dấu rollback |
| Nghĩ flush là commit | Hiểu sai thời điểm dữ liệu được xác nhận | Phân biệt flush với commit |
| Dùng SERIALIZABLE cho mọi thao tác | Giảm concurrency và tăng retry/timeout | Chọn isolation theo yêu cầu |
| Chỉ kiểm tra tồn tại trong Java, không có UNIQUE constraint | Hai request đồng thời vẫn tạo dữ liệu trùng | Bảo vệ ở database |
| Dùng self-invocation với @Transactional | Annotation có thể không được áp dụng qua proxy | Gọi qua bean proxy hoặc đặt ranh giới ở phương thức ngoài |
| Giữ transaction qua tác vụ async | Thread khác không tự tham gia transaction imperative hiện tại | Tạo use case/transaction riêng hoặc phát sự kiện sau commit |

## 15. Quy trình xác định ranh giới giao dịch

Khi thiết kế một use case, hãy trả lời lần lượt:

1. Những thay đổi dữ liệu nào phải cùng thành công hoặc cùng thất bại?
2. Những invariant hoặc constraint nào cần được bảo vệ?
3. Use case được gọi từ những adapter nào ngoài HTTP?
4. Ranh giới transaction nên nằm ở application service nào?
5. Các repository có dùng cùng transaction manager và nguồn dữ liệu không?
6. Cần propagation nào khi service gọi service khác?
7. Isolation mặc định có đủ không; có cần version, lock hoặc constraint không?
8. Exception nào phải rollback; exception nào có thể được xử lý và tiếp tục?
9. Có tác dụng phụ bên ngoài database không; chúng chạy sau commit hay qua outbox?
10. Transaction có giữ connection/lock trong thời gian quá lâu không?
11. Có kiểm thử rollback, commit, concurrency và retry chưa?

Một use case đơn giản có thể chỉ cần một annotation `@Transactional` ở application service. Một quy trình phức tạp có thể cần outbox hoặc saga. Không nên thêm propagation, lock hoặc tầng điều phối khi chưa có yêu cầu cụ thể.

## 16. Những điểm cần ghi nhớ

Ranh giới giao dịch xác định phần công việc dữ liệu cần được commit hoặc rollback như một đơn vị. Trong MVC, application service thường là nơi phù hợp để đặt ranh giới theo use case; Controller xử lý HTTP, Model bảo vệ quy tắc và repository thực hiện persistence.

Chọn ranh giới quá nhỏ có thể để lại dữ liệu nửa chừng; chọn quá rộng làm tăng thời gian giữ connection và khóa. ACID, propagation, isolation và rollback policy cần được hiểu theo transaction manager và database thực tế. Flush không phải commit; self-invocation có thể bỏ qua proxy; giao dịch imperative thường không tự truyền sang thread bất đồng bộ.

Email, message và HTTP call bên ngoài không tự rollback cùng database. Hãy xử lý sau commit hoặc dùng transactional outbox; với quy trình nhiều hệ thống, cân nhắc saga và hành động bù trừ. Kết hợp transaction với optimistic locking, pessimistic locking hoặc constraint khi cần bảo vệ cập nhật đồng thời.

Một ranh giới giao dịch tốt phản ánh đúng một use case nghiệp vụ, giữ các thay đổi liên quan nhất quán và có thể được kiểm thử rõ ràng khi thành công, thất bại hoặc cạnh tranh.
