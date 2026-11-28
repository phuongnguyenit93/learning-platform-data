# Lưu tường minh trước khi chuyển công việc cho thành phần khác

Khi một thành phần tạo hoặc cập nhật Spring Session rồi chuyển công việc cho thành phần khác, thành phần nhận cần biết dữ liệu phiên đã được lưu và có thể đọc lại. Nếu chỉ sửa một object Session trong bộ nhớ rồi gửi session ID sang worker, message broker hoặc service khác trước khi gọi thao tác lưu, thành phần nhận có thể truy vấn repository nhưng chưa thấy thay đổi mới nhất.

Spring Session cung cấp SessionRepository với các thao tác createSession(), findById(), save() và deleteById(). Với cách dùng API repository trực tiếp, ứng dụng gọi save(session) sau khi hoàn tất các thay đổi cần chia sẻ. Chỉ sau khi thao tác lưu hoàn tất thành công mới nên chuyển session ID hoặc thông tin tham chiếu cho thành phần khác đọc lại.

Bài học tập trung vào ý nghĩa của việc lưu tường minh trước khi handoff, sự khác nhau giữa API SessionRepository và HttpSession integration, cách chuyển giao an toàn cho worker bất đồng bộ, cùng các giới hạn về transaction, TTL và cập nhật đồng thời. Spring Session thường được dùng gián tiếp qua HttpSession trong ứng dụng Servlet; chỉ dùng repository trực tiếp khi có lý do rõ ràng và đã xác định ai chịu trách nhiệm lưu.

## 1. Vì sao phải lưu trước khi handoff?

Giả sử một request tạo trạng thái quy trình thanh toán trong session rồi gửi một công việc sang worker:

1. Web application tạo session.
2. Ứng dụng đặt workflow.id và workflow.status vào session.
3. Ứng dụng gửi message chứa session ID đến queue.
4. Worker nhận message và gọi findById(sessionId).
5. Worker đọc trạng thái quy trình từ repository.

Nếu message được gửi trước khi session được lưu, worker có thể chạy ngay và không tìm thấy session hoặc đọc được phiên bản cũ. Đây là race condition giữa thao tác ghi session và thao tác handoff.

Luồng chưa an toàn:

    Tạo Session trong bộ nhớ
             |
             v
    setAttribute("workflow.status", ...)
             |
             v
    Gửi message cho worker
             |
             v
    Worker findById(sessionId)
             |
             v
    Session chưa được save hoặc dữ liệu cũ

Luồng rõ ràng hơn khi dùng SessionRepository trực tiếp:

    Tạo Session
         |
         v
    Đặt các thuộc tính cần chia sẻ
         |
         v
    repository.save(session)
         |
         | Chỉ khi save thành công
         v
    Gửi thông tin handoff
         |
         v
    Thành phần nhận findById(sessionId)
         |
         v
    Đọc trạng thái đã lưu

Điểm handoff nên nằm sau ranh giới lưu thành công. Tuy nhiên, lưu session và gửi message thường là hai thao tác trên hai hệ thống khác nhau; gọi save trước giúp tránh consumer đọc quá sớm, nhưng không tự tạo transaction nguyên tử giữa repository và message broker.

## 2. SessionRepository và hợp đồng save()

SessionRepository là API cơ bản để tạo, tìm, lưu và xóa Session. Mỗi repository quản lý loại Session riêng, vì vậy ứng dụng cần giữ đúng generic type và dùng object được tạo hoặc tải từ chính repository đó.

Ví dụ hợp đồng:

~~~java
public interface SessionRepository<S extends Session> {

    S createSession();

    S findById(String id);

    void save(S session);

    void deleteById(String id);
}
~~~

Các thao tác có ý nghĩa:

| Phương thức | Mục đích |
|---|---|
| createSession() | Tạo một Session có thể được repository đó lưu |
| findById(id) | Tải Session theo session ID; trả null nếu không tìm thấy hoặc đã hết hạn |
| save(session) | Bảo đảm Session được lưu theo hợp đồng repository |
| deleteById(id) | Xóa Session theo ID; không làm gì nếu không tìm thấy |

save(session) không đơn thuần là ghi toàn bộ object một cách mù quáng. Repository có thể theo dõi thay đổi và chỉ ghi delta. Một số implementation ghi ngay khi Session được cập nhật, nên lần gọi save() có thể không cần làm thêm thao tác. Dù vậy, gọi save() là cách thể hiện rõ ranh giới hoàn tất khi code dùng API repository trực tiếp.

Một yêu cầu quan trọng: Session truyền vào save() phải được tạo bằng createSession() hoặc tải bằng findById() từ cùng repository. Không tự tạo một object Session tùy ý rồi kỳ vọng repository hiểu metadata và trạng thái nội bộ của nó.

## 3. Ví dụ tạo và lưu session trước khi chuyển giao

Ví dụ sau tạo một session, lưu dữ liệu cần thiết cho một workflow, gọi save() rồi mới trả session ID cho tầng handoff:

~~~java
@Service
public class WorkflowSessionService {

    private final SessionRepository<MapSession> sessions;

    public WorkflowSessionService(
            SessionRepository<MapSession> sessions) {
        this.sessions = sessions;
    }

    public String createAndSave(WorkflowSnapshot snapshot) {
        MapSession session = this.sessions.createSession();

        session.setAttribute("workflow.id", snapshot.workflowId());
        session.setAttribute("workflow.status", snapshot.status());
        session.setAttribute("workflow.owner", snapshot.ownerId());

        session.setMaxInactiveInterval(Duration.ofMinutes(20));

        this.sessions.save(session);

        return session.getId();
    }
}
~~~

MapSession trong ví dụ đại diện cho kiểu Session cụ thể. Trong ứng dụng dùng Redis hoặc JDBC, hãy inject đúng generic type của repository đang được cấu hình. Không khai báo cứng MapSession nếu implementation trả về một kiểu Session khác.

Sau khi phương thức trả về thành công, caller có thể dùng session ID làm tham chiếu để handoff. Nếu save() ném exception, phương thức không trả ID và caller không nên gửi message cho worker như thể session đã sẵn sàng.

Ví dụ tầng điều phối:

~~~java
public void submitWorkflow(WorkflowSnapshot snapshot) {
    String sessionId = workflowSessionService.createAndSave(snapshot);

    taskPublisher.publish(new WorkflowTask(
            snapshot.workflowId(),
            sessionId
    ));
}
~~~

Trong production, message thường nên mang workflow ID và dữ liệu công việc tối thiểu. Chỉ đưa session ID vào message khi consumer thực sự cần đọc session và kênh handoff được bảo vệ như một kênh mang credential.

## 4. Thành phần nhận tải lại session từ repository

Thành phần nhận nên dùng session ID để tải một snapshot mới từ repository, thay vì nhận một object Session còn nằm trong bộ nhớ của thành phần gửi.

~~~java
@Service
public class WorkflowWorker {

    private final SessionRepository<MapSession> sessions;

    public WorkflowWorker(SessionRepository<MapSession> sessions) {
        this.sessions = sessions;
    }

    public void handle(WorkflowTask task) {
        MapSession session = this.sessions.findById(task.sessionId());

        if (session == null) {
            throw new WorkflowSessionExpiredException(task.workflowId());
        }

        String status = session.getAttribute("workflow.status");
        String ownerId = session.getAttribute("workflow.owner");

        process(task.workflowId(), status, ownerId);
    }
}
~~~

Cách này có một số lợi ích:

- Thành phần nhận đọc trạng thái đã được repository lưu.
- Không chia sẻ object mutable giữa thread hoặc process.
- Worker có thể chạy trên instance khác nếu các node dùng cùng repository và cấu hình tương thích.
- Worker có thể phát hiện session đã hết hạn hoặc bị xóa.
- Việc đọc lại cho phép repository áp dụng logic expiration và deserialize theo implementation.

Không nên coi findById() thành công là bằng chứng người dùng hiện tại vẫn được phép thực hiện mọi thao tác. Session có thể chứa trạng thái cũ; worker vẫn cần xác minh workflow ownership, trạng thái tài khoản và quyền nghiệp vụ theo dữ liệu có thẩm quyền.

## 5. Phân biệt lưu trực tiếp Session với HttpSession trong request

Có hai cách sử dụng khác nhau:

**Dùng API SessionRepository trực tiếp**

Ứng dụng gọi createSession(), setAttribute(), save() và findById() theo ý mình. Code chịu trách nhiệm gọi save() đúng thời điểm trước khi chuyển ID cho thành phần khác.

**Dùng HttpSession integration**

Ứng dụng Servlet gọi request.getSession(), session.setAttribute() và để SessionRepositoryFilter tích hợp HttpSession với Spring Session. Filter thay HttpSession của container bằng implementation dựa trên repository và lưu phiên theo vòng đời request/response.

Ví dụ HttpSession thông thường:

~~~java
@PostMapping("/workflow/start")
public ResponseEntity<Void> start(HttpServletRequest request) {
    HttpSession session = request.getSession();
    session.setAttribute("workflow.status", "STARTED");

    return ResponseEntity.accepted().build();
}
~~~

Trong mô hình này, code controller không gọi session.save() vì Servlet HttpSession không có phương thức save(). Spring Session filter quản lý việc lưu session trong quá trình xử lý request và khi response được commit.

Điều đó dẫn đến một lưu ý quan trọng: nếu controller gửi message cho worker ngay sau setAttribute(), worker có thể bắt đầu trước khi filter hoàn tất việc lưu HttpSession ở cuối request. Không được giả định rằng chỉ vì setAttribute() đã chạy thì dữ liệu đã hiện diện trong Redis/JDBC cho consumer khác.

Khi cần handoff tức thời trước khi request kết thúc, hãy chọn một thiết kế có ranh giới lưu rõ ràng: dùng API SessionRepository trực tiếp cho workflow riêng, chuyển snapshot dữ liệu cần thiết trực tiếp trong message, hoặc điều phối handoff sau khi trạng thái đã được lưu qua cơ chế được hỗ trợ. Không cast HttpSession wrapper sang lớp nội bộ của Spring Session để gọi API không công khai.

## 6. Vì sao không nên chuyển object Session qua thread hoặc process?

Session là object có trạng thái và có thể chứa cơ chế theo dõi thay đổi riêng của repository. Truyền cùng object đó sang một thread khác có thể dẫn đến hai thành phần cùng sửa dữ liệu trong khi repository hoặc request lifecycle cũng đang quản lý nó.

Rủi ro gồm:

- Thay đổi không được đánh dấu hoặc không được save.
- Hai thread ghi đè thuộc tính của nhau.
- Object không an toàn khi dùng đồng thời.
- Consumer nhận tham chiếu không còn gắn với vòng đời request.
- Không thể truyền object Java trực tiếp qua process boundary hoặc message broker.
- Serialization của object Session có thể phụ thuộc implementation và version.

Cách handoff tốt hơn là chuyển một trong các dạng sau:

1. Session ID để consumer tải lại từ repository.
2. Workflow ID để consumer tải dữ liệu nghiệp vụ từ database.
3. Immutable DTO chứa snapshot tối thiểu cần xử lý.
4. Một reference có thời hạn tới bản ghi công việc hoặc tài nguyên.

Không truyền toàn bộ HttpSession, SecurityContext hoặc object graph nội bộ vào message queue. Điều đó làm tăng kích thước message, ghép chặt consumer với implementation session và có thể làm lộ dữ liệu xác thực.

## 7. Save phải hoàn tất trước publish, nhưng không tự tạo transaction phân tán

Giả sử ứng dụng lưu session ở Redis rồi publish message vào RabbitMQ/Kafka. Hai thao tác thuộc hai hệ thống độc lập:

    Application
       |
       +--> SessionRepository.save(session) --> Redis
       |
       +--> publish(task) -------------------> Message broker

Gọi save() trước publish() đảm bảo consumer không được thông báo trước khi code lưu hoàn tất. Tuy nhiên, vẫn có cửa sổ lỗi:

- Redis save thành công, publish thất bại: session tồn tại nhưng không có task.
- Redis save thành công, ứng dụng dừng trước publish: task không được gửi.
- Publish thành công nhưng broker redeliver: consumer có thể xử lý task nhiều lần.
- Session hết hạn trước khi consumer xử lý: consumer không còn tải được session.

Vì vậy, không tuyên bố hai thao tác đã nguyên tử chỉ vì chúng nằm trong cùng một phương thức Java hoặc cùng một @Transactional. Transaction manager chỉ điều phối tài nguyên mà nó quản lý; Redis và broker thường không cùng một transaction địa phương.

Nếu workflow cần độ tin cậy cao, hãy dùng một bản ghi công việc có trạng thái trong database nghiệp vụ và transactional outbox:

1. Trong một transaction database, ghi workflow state và outbox event.
2. Commit transaction.
3. Publisher đọc outbox và gửi message có event ID.
4. Consumer xử lý idempotent, ghi nhận event đã xử lý.
5. Session chỉ chứa ngữ cảnh giao diện hoặc tham chiếu ngắn hạn, không phải nguồn dữ liệu chuẩn của workflow.

Nếu session repository dùng cùng database và cùng transaction manager, có thể có cách phối hợp transaction, nhưng phải xác minh repository thực sự tham gia transaction đó và không suy ra điều này từ việc cùng dùng JDBC. Với Redis hoặc broker riêng, cần thiết kế consistency rõ ràng.

## 8. Xử lý lỗi khi save thất bại

SessionRepository.save() có kiểu trả về void trong API đồng bộ. Khi lưu thất bại, implementation thường ném exception runtime hoặc exception từ tầng lưu trữ. Caller cần để lỗi truyền lên hoặc xử lý có chủ đích trước khi handoff.

Một mẫu xử lý:

~~~java
public String createAndSave(WorkflowSnapshot snapshot) {
    MapSession session = sessions.createSession();

    session.setAttribute("workflow.id", snapshot.workflowId());
    session.setAttribute("workflow.status", snapshot.status());

    try {
        sessions.save(session);
    }
    catch (RuntimeException ex) {
        throw new WorkflowSessionPersistenceException(
                snapshot.workflowId(), ex);
    }

    return session.getId();
}
~~~

Không bắt exception rồi vẫn trả session ID như thể dữ liệu đã được lưu. Nếu lưu không thành công, thành phần nhận có thể không tìm thấy session hoặc đọc trạng thái không đầy đủ.

Các hành động phù hợp khi lỗi:

- Không publish task cần session đó.
- Trả lỗi có thể retry nếu thao tác an toàn.
- Ghi log có correlation ID và loại lỗi, không ghi session ID hoặc thuộc tính nhạy cảm.
- Phân biệt lỗi kết nối tạm thời với lỗi serialization/schema.
- Nếu đã tạo một record phụ nhưng không thể tiếp tục, dọn dẹp theo cơ chế bù trừ.
- Có metric cho save failure và handoff failure.

Nếu retry save(), cần hiểu repository có thao tác idempotent không và có thể tạo bản ghi trùng hay không. Với cùng một Session và ID, nhiều implementation có thể ghi đè cùng record, nhưng không nên tự giả định mọi custom repository có semantics giống nhau.

## 9. Xử lý publish thất bại sau khi save thành công

Trường hợp save thành công nhưng publish thất bại để lại session mồ côi. Nếu session có TTL hợp lý, repository sẽ hết hạn và dọn nó theo cơ chế implementation. Tuy nhiên, nếu session chứa dữ liệu lớn hoặc có tài nguyên phụ, cần chính sách cleanup.

Một cách xử lý đơn giản:

~~~java
String sessionId = createAndSave(snapshot);

try {
    taskPublisher.publish(new WorkflowTask(snapshot.workflowId(), sessionId));
}
catch (RuntimeException ex) {
    sessionRepository.deleteById(sessionId);
    throw ex;
}
~~~

Đây chỉ là compensation minh họa. Không xóa session nếu một thành phần khác đã bắt đầu sử dụng nó hoặc nếu retry publish có thể thành công sau đó. Với hệ thống phân tán, compensation cần dựa trên trạng thái workflow và idempotency key, không chỉ dựa trên việc bắt exception.

Đối với công việc quan trọng, transactional outbox thường đáng tin cậy hơn việc tự publish và xóa session trong catch block. Session nên có TTL giới hạn để dữ liệu phụ không tồn tại vô thời hạn.

## 10. SaveMode và FlushMode ảnh hưởng đến thời điểm ghi

Với repository có hỗ trợ các chính sách này, cần hiểu mối quan hệ giữa save() và flush behavior.

- FlushMode điều khiển khi thay đổi được đẩy xuống store.
- SaveMode điều khiển tập thuộc tính được ghi trong lần save.
- Với Redis session repository, mặc định thường ghi khi SessionRepository.save() được gọi; FlushMode.IMMEDIATE đẩy thay đổi sớm hơn.
- Một số repository có thể lưu ngay khi thuộc tính được thay đổi, khiến save() không phải lúc nào cũng tạo thêm I/O.

Nếu ứng dụng dựa vào explicit save làm điểm handoff, hãy xác nhận FlushMode thực tế của repository. Không giả định mọi thay đổi đều được ghi ngay khi setAttribute() chạy.

SaveMode cũng cần được tính đến. Nếu chỉ các thuộc tính được đánh dấu mới được ghi, việc sửa object mutable bên trong thuộc tính mà không gọi setAttribute() có thể khiến thay đổi không được đưa vào lần save theo policy đó. Hãy cập nhật thuộc tính theo cách repository có thể theo dõi hoặc chọn policy phù hợp.

Không dùng IMMEDIATE như một cách thay thế cho việc thiết kế handoff. Nó có thể ghi sớm hơn, nhưng code vẫn cần xác định khi nào dữ liệu đã sẵn sàng, xử lý lỗi và đảm bảo consumer chỉ được thông báo sau ranh giới lưu cần thiết.

## 11. Save có thể cập nhật lastAccessedTime và ảnh hưởng TTL

Theo hợp đồng SessionRepository và implementation chuẩn, thao tác save có thể cập nhật lastAccessedTime. Vì thời điểm hết hạn được tính dựa trên thời gian truy cập gần nhất và maxInactiveInterval, việc save có thể làm mới thời gian không hoạt động của session.

Điều này có hai hệ quả:

- Save trước handoff có thể làm session được xem là vừa hoạt động.
- Một background worker lưu session chỉ để ghi một thay đổi kỹ thuật có thể vô tình kéo dài thời gian sống của session.

Không dùng save() định kỳ như một heartbeat tùy tiện để giữ phiên người dùng sống mãi. Hãy phân biệt hoạt động người dùng thực tế với thao tác nền. Nếu worker cần trạng thái lâu dài hơn thời hạn session, hãy lưu trạng thái workflow ở kho nghiệp vụ với retention riêng.

Consumer cũng phải xử lý trường hợp findById() trả null vì session đã hết hạn hoặc bị xóa. Không tạo lại session tự động bằng ID cũ; nếu nghiệp vụ cần tiếp tục, hãy khôi phục từ workflow record có thẩm quyền.

## 12. Handoff bằng session ID cần bảo vệ như credential

Session ID là bearer credential. Người có ID còn hiệu lực có thể có khả năng truy cập session. Khi chuyển ID qua queue, event bus hoặc API nội bộ, cần áp dụng kiểm soát tương tự credential:

- Chỉ gửi tới consumer thực sự cần dùng session.
- Dùng transport được xác thực và mã hóa.
- Hạn chế quyền đọc queue/topic.
- Không đưa session ID vào log, tracing, dead-letter message hoặc dashboard.
- Đặt retention ngắn cho message chứa ID.
- Xác minh consumer có quyền xử lý workflow tương ứng.
- Không dùng session ID thay cho user ID hoặc workflow ID.

Nếu worker chỉ cần biết chủ sở hữu và trạng thái workflow, tốt hơn là gửi workflow ID hoặc immutable DTO không chứa session credential. Worker tải dữ liệu nghiệp vụ bằng quyền service-to-service và kiểm tra ownership theo quy tắc nghiệp vụ.

Không gửi SecurityContext hoặc Authentication nguyên vẹn qua queue để worker “mượn” quyền của người dùng. Worker nên dùng identity dịch vụ và truyền actor ID đã xác minh làm audit context; authorization phải được thực hiện ở tầng nghiệp vụ theo policy rõ ràng.

## 13. Tránh dùng session làm nguồn dữ liệu chuẩn của background job

HttpSession được thiết kế cho trạng thái tương tác ngắn hạn của client. Background job có thể chạy sau vài giây, vài phút hoặc lâu hơn, vượt quá TTL của session. Người dùng cũng có thể logout hoặc bị thu hồi phiên trong lúc job đang chạy.

Không nên lưu toàn bộ tiến độ công việc dài hạn trong session rồi mong worker đọc lại bất cứ lúc nào. Hãy tách:

| Dữ liệu | Nơi lưu phù hợp |
|---|---|
| Session ID và trạng thái giao diện ngắn hạn | Spring Session |
| Workflow ID, trạng thái job, retry count | Database/job store |
| Payload công việc cần xử lý | Message broker hoặc object storage/database |
| Principal/actor đã khởi tạo công việc | Workflow record hoặc message metadata đã xác minh |
| Credential xác thực người dùng | Spring Security/session store theo chính sách |
| Kết quả job và lịch sử xử lý | Database nghiệp vụ |

Nếu công việc cần tiếp tục ngay cả sau khi session hết hạn, worker phải dựa vào workflow record, không phụ thuộc session. Session có thể chứa workflow ID để UI tra cứu trạng thái, nhưng không nên là nguồn duy nhất.

## 14. Cập nhật session trước khi handoff trong ứng dụng Servlet

Với HttpSession integration, Spring Session filter quản lý việc lưu và có thể thực hiện nhiều lần trong vòng đời request để bảo đảm session ID và thay đổi thuộc tính được lưu đúng thời điểm. Ứng dụng không nên tự gọi API nội bộ của wrapper để ép flush.

Nếu request cần khởi chạy công việc nền, có các lựa chọn thiết kế:

**Lựa chọn A: chuyển snapshot dữ liệu cho worker.**

Controller/service tạo immutable DTO từ dữ liệu cần thiết và gửi DTO hoặc workflow ID. Worker không cần đọc session. Đây thường là lựa chọn tốt nhất cho job độc lập.

**Lựa chọn B: dùng repository API trực tiếp cho workflow session riêng.**

Service tạo Session qua SessionRepository, cập nhật thuộc tính, gọi save() và chỉ sau khi save thành công mới publish session ID. Cách này phù hợp khi thật sự cần một record session riêng cho quy trình handoff.

**Lựa chọn C: phối hợp với điểm commit được hỗ trợ.**

Nếu kiến trúc yêu cầu consumer đọc HttpSession sau khi request kết thúc, hãy thiết kế một cơ chế điều phối sau khi dữ liệu đã được lưu bởi filter/repository và kiểm thử thứ tự thực tế. Không giả định @TransactionalEventListener(AFTER_COMMIT) tự động chạy sau khi Spring Session filter đã hoàn tất save; transaction commit và filter response commit có thể là hai mốc khác nhau.

Không thêm một lần save bằng cách cast HttpSession sang implementation cụ thể. Cách đó phụ thuộc nội bộ, dễ hỏng khi nâng cấp và có thể gây double-write.

## 15. Reactive repository và handoff bất đồng bộ

Trong WebFlux, ReactiveSessionRepository có hợp đồng reactive. Thao tác save thường trả về Publisher, chẳng hạn Mono<Void>, nên phải nối việc handoff sau khi publisher hoàn tất.

Mẫu khái niệm:

~~~java
Mono<String> saveBeforeHandoff(ReactiveSessionRepository<MySession> repository,
                               MySession session) {
    return repository.save(session)
            .thenReturn(session.getId());
}
~~~

Sau đó nối publish vào reactive chain:

~~~java
return saveBeforeHandoff(repository, session)
        .flatMap(sessionId -> taskPublisher.publish(sessionId));
~~~

Không gọi subscribe() rời rạc rồi publish ngay ở dòng tiếp theo; cách đó không bảo đảm save hoàn tất trước handoff. Hãy compose publisher để thứ tự được thể hiện trong pipeline.

Không gọi SessionRepository đồng bộ/blocking trên event-loop thread của WebFlux. JDBC SessionRepository là API blocking và không thể thay thế trực tiếp ReactiveSessionRepository. Nếu cần reactive handoff, dùng repository reactive được hỗ trợ và driver không blocking.

## 16. Kiểm tra session đã lưu trước khi chuyển giao

Trong môi trường cần độ tin cậy cao, có thể kiểm thử bằng cách tải lại session sau save:

~~~java
repository.save(session);

S persisted = repository.findById(session.getId());
if (persisted == null) {
    throw new IllegalStateException("Session was not found after save");
}
~~~

Đây là bước xác minh bổ sung, không phải yêu cầu bắt buộc cho mọi request. Nó tạo thêm một lần đọc và có thể tăng latency. Với repository chuẩn, save() là hợp đồng lưu; hãy dùng read-after-write verification khi cần phát hiện cấu hình hoặc implementation bất thường.

Khi kiểm tra, so sánh các thuộc tính thực sự cần handoff, không chỉ kiểm tra record tồn tại. Cũng cần kiểm tra expiration: một session có thể được lưu thành công nhưng đã hết hạn khi consumer xử lý.

Nếu repository dùng replica hoặc cache có eventual consistency, cần hiểu read-after-write guarantee. Không mặc định truy vấn ngay sau save từ một replica bất kỳ sẽ thấy dữ liệu mới nhất nếu topology cho phép đọc stale.

## 17. Thiết kế idempotency và retry cho consumer

Message broker có thể giao lại cùng một message. Worker phải xử lý trường hợp cùng session ID hoặc workflow ID được gửi nhiều lần.

Các nguyên tắc:

- Dùng event ID hoặc workflow ID làm idempotency key.
- Ghi trạng thái xử lý và kết quả theo transaction nghiệp vụ.
- Không thực hiện side effect lần thứ hai chỉ vì message bị redeliver.
- Xử lý session không còn tồn tại bằng lỗi nghiệp vụ rõ ràng.
- Phân biệt lỗi tạm thời của repository với session đã hết hạn.
- Có retry limit và dead-letter policy.
- Không retry vô hạn một session ID đã bị revoke hoặc hết hạn.

Session ID không phải idempotency key phù hợp cho mọi công việc. Một người dùng có thể tạo nhiều job trong cùng session, và một job có thể được retry nhiều lần. Hãy dùng workflow ID/event ID riêng.

## 18. Kiểm thử thứ tự save và handoff

Một bộ test cần chứng minh consumer chỉ được gọi sau khi dữ liệu sẵn sàng và xử lý đúng các trường hợp lỗi.

Các trường hợp nên kiểm thử:

1. Tạo session qua SessionRepository, đặt thuộc tính rồi gọi save().
2. Xác nhận repository.findById() tải được thuộc tính vừa lưu.
3. Xác nhận task publisher chỉ được gọi sau khi save() hoàn tất.
4. Giả lập save() ném exception và xác nhận không publish task.
5. Giả lập publish thất bại sau save và xác nhận compensation/outbox policy được áp dụng.
6. Consumer nhận session ID hợp lệ và tải được dữ liệu.
7. Consumer nhận ID không tồn tại hoặc session hết hạn và xử lý theo policy.
8. Kiểm thử hai consumer xử lý cùng event để xác nhận idempotency.
9. Kiểm thử session ID bị thu hồi trước khi consumer chạy.
10. Kiểm thử save cập nhật lastAccessedTime và tác động tới TTL.
11. Kiểm thử SaveMode khi sửa object mutable bên trong thuộc tính.
12. Kiểm thử Redis/JDBC repository thật hoặc môi trường tương thích.
13. Với HttpSession integration, kiểm tra request filter commit và thời điểm background consumer đọc session.
14. Với WebFlux, xác nhận publisher save hoàn tất trước publisher handoff.
15. Kiểm tra message, log và trace không chứa credential thô.

Mock SessionRepository hữu ích để kiểm tra thứ tự lời gọi, nhưng không chứng minh dữ liệu đã được Redis/JDBC ghi bền vững. Cần integration test cho repository thật.

## 19. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Publish message trước repository.save() | Consumer đọc không thấy session hoặc thấy dữ liệu cũ | Save thành công rồi mới handoff |
| Nghĩ setAttribute() luôn đồng nghĩa đã persist | Thành phần khác có thể đọc trước khi request filter lưu | Phân biệt HttpSession lifecycle với direct repository API |
| Chuyển object Session mutable sang worker | Race condition và phụ thuộc implementation | Chuyển session ID hoặc DTO bất biến |
| Bắt lỗi save rồi vẫn publish | Worker xử lý dữ liệu chưa được lưu | Dừng handoff khi save thất bại |
| Giả định save và broker publish cùng transaction | Mất message hoặc session mồ côi | Dùng outbox/idempotency/compensation |
| Dùng session làm job store lâu dài | Job thất bại khi session hết hạn | Lưu workflow ở database/job store |
| Dùng session ID làm workflow ID | Trộn credential với định danh nghiệp vụ | Tạo workflow ID riêng |
| Worker dùng session để cấp quyền | Quyền có thể cũ hoặc session đã bị thu hồi | Xác minh quyền ở tầng nghiệp vụ |
| Gọi subscribe() rời rạc trong WebFlux | Handoff có thể chạy trước save | Compose reactive pipeline bằng then/flatMap |
| Dùng JDBC blocking trong reactive event loop | Làm nghẽn event-loop | Dùng ReactiveSessionRepository và driver non-blocking |

## 20. Quy trình triển khai đề xuất

Trước khi chuyển công việc cho thành phần khác dựa trên dữ liệu phiên, hãy thực hiện:

1. Xác định dữ liệu nào thực sự cần consumer và liệu nó có nên nằm trong session hay workflow store.
2. Chọn direct SessionRepository API hoặc HttpSession integration phù hợp.
3. Nếu dùng direct API, tạo/tải Session từ cùng repository, cập nhật thuộc tính rồi gọi save().
4. Chỉ sau khi save thành công mới gửi session ID hoặc reference cho consumer.
5. Ưu tiên gửi workflow ID và snapshot tối thiểu thay cho session credential.
6. Nếu dùng HttpSession, không giả định setAttribute() đã persist trước khi request filter commit.
7. Nếu save và publish ở hai hệ thống, thiết kế outbox hoặc compensation và idempotency.
8. Đặt TTL phù hợp và xử lý session hết hạn trước khi consumer chạy.
9. Bảo vệ session ID và không đưa nó vào log/message không cần thiết.
10. Kiểm thử thứ tự save, publish, retry, logout, expiration và nhiều instance.

## Kết luận

Lưu tường minh là ranh giới quan trọng khi code dùng SessionRepository trực tiếp và cần chuyển session cho thành phần khác đọc. Hãy tạo hoặc tải Session từ đúng repository, cập nhật thuộc tính, gọi save() và chỉ handoff sau khi save hoàn tất thành công. Với HttpSession integration, Spring Session filter tự quản lý việc lưu theo vòng đời request; HttpSession không có phương thức save() công khai, vì vậy không được giả định setAttribute() đã hiện diện trong repository trước khi request kết thúc. Khi handoff qua queue hoặc service khác, ưu tiên workflow ID/DTO, bảo vệ session ID như credential, xử lý TTL và lỗi, và không giả định save cùng publish là một transaction nguyên tử.

## Tài liệu tham khảo

- Spring Session API Documentation: https://docs.spring.io/spring-session/reference/api.html
- SessionRepository Javadoc: https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/SessionRepository.html
- HttpSession Integration: https://docs.spring.io/spring-session/reference/http-session.html
- Redis Session Storage and FlushMode: https://docs.spring.io/spring-session/reference/api.html#api-redis-session-repository
