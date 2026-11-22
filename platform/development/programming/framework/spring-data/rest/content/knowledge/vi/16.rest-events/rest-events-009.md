# Tính đồng bộ mặc định, thứ tự xử lý và ngoại lệ trong listener

Spring Data REST phát các repository event khi REST exporter xử lý thao tác trên entity. Listener cho phép kiểm tra hoặc chuẩn hóa dữ liệu trước khi lưu, phản ứng sau khi tạo/cập nhật/xóa, hoặc xử lý thay đổi liên kết giữa các tài nguyên.

Ba điều cần hiểu rõ khi thiết kế listener là: listener chạy đồng bộ theo mặc định, các event Before và After xuất hiện theo thứ tự của thao tác repository, và ngoại lệ có thể ảnh hưởng trực tiếp tới request HTTP. Đây là event của Spring Data REST; không nên nhầm chúng với callback vòng đời JPA như @PrePersist hoặc @PostUpdate.

## 1. Tám repository event của Spring Data REST

REST exporter phát tám loại event trong quá trình làm việc với entity:

| Giai đoạn | Event trước thao tác | Event sau thao tác | Mục đích |
|---|---|---|---|
| Tạo entity | BeforeCreateEvent | AfterCreateEvent | Xử lý khi tạo tài nguyên mới |
| Lưu entity | BeforeSaveEvent | AfterSaveEvent | Xử lý khi lưu/cập nhật tài nguyên |
| Lưu liên kết | BeforeLinkSaveEvent | AfterLinkSaveEvent | Xử lý khi cập nhật association link |
| Xóa entity | BeforeDeleteEvent | AfterDeleteEvent | Xử lý khi xóa tài nguyên |

Ý nghĩa thực tế:

- BeforeCreateEvent: được phát trước khi REST exporter lưu entity mới.
- AfterCreateEvent: được phát sau thao tác tạo entity.
- BeforeSaveEvent: được phát trước khi entity được lưu.
- AfterSaveEvent: được phát sau thao tác lưu entity.
- BeforeLinkSaveEvent: được phát trước khi association link được lưu/cập nhật.
- AfterLinkSaveEvent: được phát sau thao tác lưu association link.
- BeforeDeleteEvent: được phát trước thao tác xóa entity.
- AfterDeleteEvent: được phát sau thao tác xóa entity.

Các event này gắn với luồng xử lý của Spring Data REST. Nếu ứng dụng gọi repository trực tiếp từ một service hoặc ghi dữ liệu qua một luồng khác, không nên mặc định rằng các Spring Data REST repository event cũng sẽ được phát. Nếu cần bắt mọi thay đổi bất kể nguồn gọi, hãy thiết kế event/domain service hoặc cơ chế persistence phù hợp với phạm vi đó.

## 2. Đăng ký listener bằng @RepositoryEventHandler

Cách thường dùng là tạo một Spring bean và đánh dấu lớp bằng @RepositoryEventHandler. Các method được đánh dấu bằng annotation tương ứng với thời điểm muốn xử lý.

~~~java
@Component
@RepositoryEventHandler(Person.class)
public class PersonEventHandler {

    @HandleBeforeCreate
    public void beforeCreate(Person person) {
        // Kiểm tra hoặc chuẩn hóa dữ liệu trước khi tạo.
        person.setDisplayName(person.getDisplayName().trim());
    }

    @HandleBeforeSave
    public void beforeSave(Person person) {
        // Kiểm tra quy tắc nghiệp vụ trước khi lưu.
    }

    @HandleAfterSave
    public void afterSave(Person person) {
        // Phản ứng sau thao tác lưu.
    }

    @HandleAfterDelete
    public void afterDelete(Person person) {
        // Ghi nhận hoặc xử lý sau thao tác xóa.
    }
}
~~~

Một số quy tắc khi khai báo:

- Bean phải được Spring quản lý, ví dụ qua @Component, hoặc được khai báo bằng @Bean trong cấu hình.
- @RepositoryEventHandler(Person.class) giới hạn handler cho domain type Person.
- Kiểu tham số đầu tiên của method handler xác định domain type mà method nhận.
- @HandleBeforeCreate, @HandleAfterCreate, @HandleBeforeSave, @HandleAfterSave, @HandleBeforeLinkSave, @HandleAfterLinkSave, @HandleBeforeDelete và @HandleAfterDelete tương ứng với tám event ở trên.
- Đặt logic đúng giai đoạn: kiểm tra/chuẩn hóa trước thao tác; gửi thông báo hoặc ghi nhận kết quả sau thao tác.

Có thể bỏ tham số domain type trên @RepositoryEventHandler nếu muốn handler xử lý nhiều loại entity, nhưng khi đó cần khai báo method theo đúng kiểu domain và tránh nhận nhầm loại tài nguyên.

## 3. Dùng AbstractRepositoryEventListener

Một cách khác là kế thừa AbstractRepositoryEventListener và override những hook cần thiết:

~~~java
@Component
public class AuditRepositoryEventListener
        extends AbstractRepositoryEventListener<Object> {

    @Override
    protected void onBeforeSave(Object entity) {
        // Xử lý trước khi lưu.
    }

    @Override
    protected void onAfterSave(Object entity) {
        // Xử lý sau khi lưu.
    }

    @Override
    protected void onBeforeDelete(Object entity) {
        // Xử lý trước khi xóa.
    }

    @Override
    protected void onAfterDelete(Object entity) {
        // Xử lý sau khi xóa.
    }
}
~~~

Cách này thuận tiện khi muốn gom nhiều event vào một listener chung. Tuy nhiên, kiểu entity thường cần được kiểm tra trong code vì listener có thể nhận nhiều domain type. Với logic đặc thù từng entity, @RepositoryEventHandler thường dễ đọc và an toàn kiểu dữ liệu hơn.

Không cần triển khai cả tám hook nếu nghiệp vụ chỉ quan tâm một vài thời điểm.

## 4. Đồng bộ là hành vi mặc định

Spring Data REST event là Spring application event. Với cấu hình mặc định, Spring phát event và gọi listener đồng bộ trong thread đang phát event.

Điều đó có nghĩa là:

1. Request HTTP đi vào REST exporter.
2. REST exporter phát event.
3. Listener chạy trong luồng xử lý hiện tại.
4. Publisher chờ listener hoàn tất.
5. Luồng xử lý tiếp tục và trả response sau khi các listener đồng bộ đã xử lý xong.

Ví dụ, nếu một request cập nhật Person kích hoạt ba listener đồng bộ và mỗi listener mất 100 ms, thời gian xử lý của request sẽ bao gồm thời gian của cả ba listener cùng với các công việc còn lại của request. Đây chỉ là ví dụ minh họa; thời gian thực tế phụ thuộc workload và cách các listener thực hiện.

Hệ quả của xử lý đồng bộ:

- Listener có thể đọc hoặc chỉnh sửa entity tại thời điểm event được phát.
- Ngoại lệ từ listener có thể đi ngược về nơi phát event.
- Công việc lâu như gọi dịch vụ ngoài, gửi email hoặc tạo báo cáo làm tăng latency của request.
- Một listener chậm có thể làm các request đang xử lý phải chờ.
- Không có hàng đợi, retry hay cơ chế giao nhận bền vững tự động chỉ vì đã đăng ký repository event listener.

Khi event được phát trong một transaction đang hoạt động, listener đồng bộ có thể chạy trong transaction context của publisher. Tuy nhiên, cần kiểm tra transaction boundary thực tế của repository operation và listener; không suy luận rằng mọi event đều nằm trong cùng một transaction chỉ dựa trên tên Before hoặc After.

## 5. Thứ tự xử lý của Before và After

Thứ tự ở cấp thao tác repository là rõ ràng: event Before được phát trước thao tác tương ứng, còn event After được phát sau thao tác đó.

~~~text
Tạo tài nguyên:
BeforeCreateEvent
        |
        v
Thực hiện thao tác tạo/lưu
        |
        v
AfterCreateEvent

Cập nhật/lưu tài nguyên:
BeforeSaveEvent
        |
        v
Thực hiện thao tác lưu
        |
        v
AfterSaveEvent

Cập nhật association link:
BeforeLinkSaveEvent
        |
        v
Thực hiện thao tác lưu liên kết
        |
        v
AfterLinkSaveEvent

Xóa tài nguyên:
BeforeDeleteEvent
        |
        v
Thực hiện thao tác xóa
        |
        v
AfterDeleteEvent
~~~

Một số lưu ý quan trọng:

- Before event là nơi phù hợp để xác thực, bổ sung dữ liệu hoặc chuẩn hóa entity trước khi repository thực hiện thao tác.
- After event phù hợp để ghi nhận kết quả hoặc khởi tạo phản ứng tiếp theo.
- AfterCreateEvent hoặc AfterSaveEvent biểu thị rằng thao tác repository tương ứng đã được thực hiện trong luồng REST exporter. Không nên tự động hiểu đây là cam kết rằng transaction database đã commit bền vững.
- Nếu request bị lỗi ở một giai đoạn, không giả định mọi event phía sau vẫn được phát.
- Spring Data REST công bố event cho thao tác lưu association link; không tự suy diễn rằng mọi thay đổi quan hệ đều phát một cặp event riêng cho từng thao tác remove.

Thứ tự Before → thao tác repository → After là thứ tự của vòng đời event. Nó không đồng nghĩa với thứ tự SQL cụ thể mà ORM phát xuống database, cũng không phải thứ tự commit của mọi transaction liên quan.

## 6. Thứ tự giữa nhiều listener cùng nhận một event

Một event có thể được nhiều listener nhận. Không nên để listener thứ hai phụ thuộc ngầm vào việc listener thứ nhất đã sửa entity hoặc ghi dữ liệu phụ, nếu thứ tự thực thi chưa được xác định rõ.

Với listener đăng ký trực tiếp qua cơ chế Spring ApplicationListener hoặc @EventListener, Spring hỗ trợ sắp xếp listener bằng Ordered hoặc annotation @Order. Giá trị order nhỏ hơn có độ ưu tiên trước giá trị lớn hơn.

~~~java
@Component
public class PersonAuditListener {

    @EventListener
    @Order(10)
    public void onPersonSaved(AfterSaveEvent event) {
        // Listener được xếp trước listener có order lớn hơn.
    }
}
~~~

Lưu ý: ví dụ trên minh họa Spring @EventListener nhận application event. @RepositoryEventHandler là cơ chế handler riêng của Spring Data REST; không mặc định rằng mọi quy tắc sắp xếp method của @EventListener đều áp dụng giống hệt cho các method @HandleBeforeSave hoặc @HandleAfterSave. Hãy kiểm tra hành vi của phiên bản đang dùng nếu thứ tự handler là yêu cầu bắt buộc.

Nếu nghiệp vụ cần trình tự xác định, có thể:

- Gom các bước phụ thuộc nhau vào một service được gọi từ một handler điều phối.
- Đặt các thao tác cần thứ tự trong cùng một method/service call.
- Dùng application event riêng và listener có thứ tự rõ ràng khi cần tách các bước.
- Viết integration test ghi nhận thứ tự thực tế thay vì dựa vào thứ tự khai báo bean hoặc method.

Tránh tạo chuỗi phụ thuộc ngầm giữa nhiều listener độc lập. Điều đó khiến việc thay đổi cấu hình, thêm listener hoặc nâng cấp Spring khó dự đoán hơn.

## 7. Ngoại lệ trong listener đồng bộ

Trong chế độ mặc định, listener chạy ngay trong luồng phát event. Nếu listener ném runtime exception và không có cơ chế xử lý ngoại lệ riêng, exception có thể truyền ngược về publisher và làm request REST thất bại.

### Ngoại lệ ở Before event

Ví dụ listener từ chối dữ liệu trước khi lưu:

~~~java
@HandleBeforeSave
public void validate(Person person) {
    if (person.getEmail() == null || person.getEmail().isBlank()) {
        throw new IllegalArgumentException("Email is required");
    }
}
~~~

Vì thao tác lưu chưa được thực hiện tại thời điểm BeforeSaveEvent, ngoại lệ thường ngăn luồng REST tiếp tục tới thao tác lưu. Đây là vị trí phù hợp cho validation có thể quyết định request có được phép tiếp tục hay không.

Tuy vậy, nếu listener đã thực hiện side effect riêng trước khi ném exception, side effect đó không tự động được hoàn tác chỉ vì thao tác lưu entity bị chặn.

### Ngoại lệ ở After event

~~~java
@HandleAfterSave
public void afterSave(Person person) {
    // Ví dụ: gọi hệ thống khác để gửi thông báo.
    notificationService.notifyPersonUpdated(person);
}
~~~

Nếu listener ném exception ở đây, thao tác repository đã được gọi trước đó. Request có thể nhận lỗi dù dữ liệu đã được lưu. Việc database có rollback hay không phụ thuộc transaction boundary, propagation và thời điểm commit thực tế.

Không dùng exception trong AfterSaveEvent như một cơ chế rollback nghiệp vụ. Nếu cần đảm bảo side effect chỉ xảy ra sau commit, hãy thiết kế transaction event phù hợp hoặc phát domain event trong transaction do ứng dụng kiểm soát. Với yêu cầu giao nhận đáng tin cậy giữa database và hệ thống ngoài, cân nhắc Transactional Outbox thay vì chỉ gọi HTTP/email trực tiếp từ listener.

### Ảnh hưởng tới các listener tiếp theo

Khi listener đồng bộ ném exception mà không được xử lý, quá trình dispatch có thể dừng tại listener đó; các listener tiếp theo không nên được giả định là đã chạy. Nếu cần cô lập lỗi của một bước không quan trọng, hãy bắt và xử lý lỗi có chủ đích, ghi log đầy đủ và xác định cách retry hoặc phục hồi.

Không nên bắt mọi Exception rồi bỏ qua. Làm như vậy có thể biến lỗi validation, lỗi dữ liệu hoặc lỗi nghiệp vụ thành response thành công giả.

## 8. Khi chuyển listener sang xử lý bất đồng bộ

Spring hỗ trợ @Async cho listener được đăng ký qua cơ chế @EventListener. Khi xử lý bất đồng bộ, công việc được chuyển sang thread khác và publisher không chờ listener hoàn tất.

~~~java
@Component
public class PersonNotificationListener {

    @Async
    @EventListener
    public void onPersonSaved(AfterSaveEvent event) {
        // Xử lý thông báo ở thread khác.
    }
}
~~~

Để @Async hoạt động, ứng dụng phải bật async processing, ví dụ bằng @EnableAsync, và có executor phù hợp.

Khác biệt quan trọng so với listener đồng bộ:

| Đặc điểm | Đồng bộ mặc định | Bất đồng bộ |
|---|---|---|
| Thread thực thi | Thread phát event | Thread do executor quản lý |
| Publisher chờ listener | Có | Không |
| Latency của request | Bao gồm thời gian listener | Không chờ phần xử lý async |
| Exception truyền về publisher | Có thể truyền ngược | Không truyền về caller |
| Thứ tự hoàn tất giữa các tác vụ | Theo thứ tự dispatch đồng bộ | Có thể khác thứ tự phát event |
| Retry/durable delivery | Không tự có | Không tự có |

Với listener async, exception không được truyền về caller. Hãy cấu hình xử lý lỗi phù hợp, chẳng hạn AsyncUncaughtExceptionHandler cho async method trả về void, đồng thời ghi log, metric và trạng thái retry khi nghiệp vụ cần.

Không mặc định rằng ThreadLocal, security context, transaction context hoặc MDC logging context được truyền sang thread khác. Nếu listener cần dữ liệu ngữ cảnh, hãy truyền tường minh hoặc cấu hình cơ chế truyền context phù hợp.

Ví dụ trên minh họa Spring @EventListener nhận Spring Data REST event. Không suy luận rằng chỉ cần thêm @Async vào method @HandleAfterSave là Spring sẽ tự động áp dụng cùng cơ chế. Hãy dùng đúng cơ chế listener được framework hỗ trợ.

Nếu tác vụ phải chạy sau khi transaction commit, @TransactionalEventListener với phase AFTER_COMMIT có thể phù hợp khi event được phát trong một transaction đang hoạt động. Nếu không có transaction, listener transactional mặc định không được gọi trừ khi cấu hình fallbackExecution. Đối với yêu cầu đảm bảo giao nhận kể cả khi tiến trình dừng đột ngột, cần cơ chế lưu trạng thái bền vững như Outbox.

## 9. Thiết kế listener an toàn

Một listener tốt nên ngắn, có mục tiêu rõ và không tạo thêm rủi ro cho request chính.

**Đặt validation ở Before event**

- Kiểm tra các điều kiện mà API phải tuân thủ.
- Chuẩn hóa dữ liệu trước khi lưu.
- Ném exception có ý nghĩa khi request không hợp lệ.
- Không gọi dịch vụ ngoài chậm nếu có thể kiểm tra bằng dữ liệu cục bộ.

**Đặt phản ứng ở After event**

- Ghi nhận audit hoặc metric phù hợp.
- Khởi tạo một domain event tiếp theo.
- Nếu gửi email hoặc gọi API bên ngoài, xác định rõ việc thất bại có được phép làm request thất bại hay không.
- Nếu cần chạy sau commit, dùng transaction-aware design thay vì dựa vào tên After.

**Giữ listener có thể kiểm thử**

- Không phụ thuộc thứ tự tình cờ giữa các bean.
- Dùng service riêng cho logic nghiệp vụ có thể tái sử dụng.
- Đảm bảo side effect có tính idempotent nếu có khả năng retry.
- Không đưa công việc nặng hoặc không giới hạn thời gian vào luồng đồng bộ.
- Ghi log đủ thông tin để truy vết entity và event, nhưng tránh ghi dữ liệu nhạy cảm.

## 10. Kiểm thử thứ tự và ngoại lệ

Integration test nên đi qua endpoint Spring Data REST thật để xác nhận event được phát đúng trong luồng HTTP.

Các trường hợp nên kiểm tra:

1. POST tạo mới: BeforeCreate chạy trước thao tác lưu và AfterCreate chạy sau thao tác.
2. PUT/PATCH cập nhật: BeforeSave chạy trước thao tác lưu và AfterSave chạy sau thao tác.
3. Xóa tài nguyên: BeforeDelete và AfterDelete được phát theo đúng thứ tự.
4. Cập nhật association: BeforeLinkSave và AfterLinkSave được phát khi endpoint thực hiện thao tác liên kết tương ứng.
5. Listener Before ném exception: request thất bại và thao tác repository chưa được thực hiện.
6. Listener After ném exception: xác nhận response và trạng thái database theo transaction boundary thực tế.
7. Nhiều listener cùng nhận event: xác nhận thứ tự nếu ứng dụng có yêu cầu thứ tự.
8. Listener async: xác nhận request không chờ công việc async và lỗi được ghi nhận theo cơ chế xử lý bất đồng bộ.
9. Gọi repository trực tiếp từ service: xác nhận rõ liệu luồng đó có phát Spring Data REST event hay không.

Không chỉ assert HTTP status. Với các tình huống exception, hãy đọc lại database để xác nhận dữ liệu đã lưu hay rollback. Với async listener, dùng cơ chế đồng bộ trong test như latch hoặc Awaitility thay vì sleep cố định.

## 11. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
|---|---|
| AfterSave có nghĩa transaction đã commit | Event biểu thị giai đoạn sau thao tác repository; commit phụ thuộc transaction boundary |
| Mọi thao tác repository đều phát Spring Data REST event | Event gắn với REST exporter; các luồng gọi khác cần cơ chế riêng |
| Listener chạy nền mặc định | Spring application event chạy đồng bộ mặc định |
| Gọi nhiều listener thì chúng tự chạy song song | Dispatch đồng bộ chờ listener; async phải cấu hình rõ |
| Exception trong AfterSave tự rollback dữ liệu | Không thể kết luận nếu chưa biết transaction đã commit hay chưa |
| Thứ tự khai báo bean quyết định thứ tự listener | Cần cơ chế ordering rõ ràng và kiểm thử |
| Bắt exception rồi bỏ qua luôn là an toàn | Có thể che giấu lỗi và làm request thành công giả |
| Listener async tự có retry và bảo đảm giao nhận | @Async chỉ chuyển thread; không cung cấp durable queue hoặc retry tự động |

## 12. Checklist trước khi triển khai

- [ ] Xác định thao tác REST cần lắng nghe: create, save, link save hay delete.
- [ ] Chọn Before hoặc After theo đúng thời điểm nghiệp vụ.
- [ ] Đăng ký handler thành Spring bean.
- [ ] Giới hạn domain type để tránh xử lý nhầm entity.
- [ ] Giữ listener đồng bộ ngắn và có giới hạn thời gian.
- [ ] Xác định ngoại lệ có được phép làm request thất bại hay không.
- [ ] Kiểm tra transaction boundary trước khi dựa vào rollback hoặc After event.
- [ ] Nếu có nhiều listener phụ thuộc nhau, định nghĩa thứ tự rõ ràng.
- [ ] Nếu chạy async, cấu hình executor, error handler và cách quan sát lỗi.
- [ ] Nếu cần xử lý sau commit hoặc giao nhận bền vững, dùng transaction-aware event hoặc Outbox.
- [ ] Kiểm thử cả response HTTP và trạng thái database sau khi listener ném exception.

## Tài liệu tham khảo

- Spring Data REST Reference — Events: https://docs.spring.io/spring-data/rest/reference/events.html
- Spring Framework Reference — Application Events and Listeners: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html

