# Kiểm thử nhiều đường vào thay vì chỉ luồng sử dụng thông thường trong AOP

## 1. Vấn đề: có advice trên đường chính vẫn chưa chứng minh mọi đường đều được bảo vệ

Aspect-Oriented Programming (AOP) cho phép tách kiểm soát truy cập thành một mối quan tâm cắt ngang: tại một join point, advice kiểm tra chủ thể, hành động, tài nguyên và bối cảnh trước khi cho phép thực thi phương thức nghiệp vụ. Điều này giảm trùng lặp, nhưng cũng dễ tạo một giả định nguy hiểm: nếu luồng sử dụng thông thường đã chạy qua advice, mọi lời gọi đến thao tác đó đều an toàn.

Ví dụ luồng quen thuộc:

~~~text
Người dùng -> HTTP handler -> access advice -> service -> tài nguyên
~~~

Test một người dùng trái quyền qua handler trên có thể trả thông báo từ chối đúng. Tuy nhiên, cùng thao tác nghiệp vụ có thể được gọi từ CLI, background job, message consumer, callback, API nội bộ, một endpoint khác, một đối tượng được tạo trực tiếp hoặc một lời gọi nội bộ cùng đối tượng. Nếu các lối này không đi qua điểm kiểm tra quyền, ta có **lỗ hổng phạm vi áp dụng AOP**.

Kiểm thử phải trả lời hai câu hỏi riêng:

1. **Policy correctness:** khi chính sách được gọi, nó quyết định đúng ALLOW/DENY trên chủ thể, hành động và tài nguyên cụ thể không?
2. **Enforcement coverage:** mọi đường có thể đi đến thao tác nhạy cảm có thực sự được kiểm tra quyền tại ít nhất một ranh giới bắt buộc trước khi dữ liệu bị lộ hoặc side effect xảy ra không?

Một bài kiểm thử chỉ đi qua luồng thông thường có thể chứng minh điều thứ nhất trong một tình huống, nhưng không chứng minh điều thứ hai.

Mục tiêu sau bài học là biết lập bản đồ entry point và join point, thiết kế kiểm thử nhiều đường vào, nhận diện bypass do self-invocation/proxy và bất đồng bộ, bảo vệ theo tài nguyên, xác minh hiệu ứng phụ và xây regression test khi kiến trúc thay đổi.

Bài học áp dụng cho **AOP nói chung**, không phụ thuộc vào một framework AOP cụ thể. Ví dụ Java 17 dùng wrapper để mô phỏng advice, đồng thời chỉ rõ nơi cần kiểm thử cơ chế interception/weaving thật.

## 2. Phân biệt các ranh giới

**Entry point:** nơi yêu cầu hoặc sự kiện bắt đầu đi vào một phần hệ thống. Ví dụ HTTP endpoint, CLI command, scheduler, message listener hoặc một lời gọi giữa các module.

**Join point:** điểm thực thi mà cơ chế AOP cho phép quan sát hoặc can thiệp, chẳng hạn method call hoặc method execution. Những loại join point được hỗ trợ phụ thuộc cách triển khai AOP.

**Pointcut:** biểu thức/quy tắc chọn join point cần áp dụng advice.

**Advice:** hành vi chạy tại join point, ví dụ kiểm tra quyền, ghi audit và quyết định có tiếp tục lời gọi hay không.

**Sensitive operation:** hành động đọc/ghi/xuất/xóa dữ liệu hoặc gọi dịch vụ tạo side effect cần bảo vệ. Nó có thể nằm sâu trong hệ thống và có nhiều caller.

**Policy decision point:** nơi đánh giá quyền dựa trên subject/action/resource/context.

**Policy enforcement point:** ranh giới thực sự ngăn thao tác khi không được phép. Advice có thể là một điểm enforcement, nhưng chỉ nếu mọi đường cần bảo vệ thực sự phải đi qua nó.

Ví dụ quyết định quyền đọc một tài liệu:

~~~text
ALLOW nếu:
  chủ thể đã xác thực hợp lệ
  AND chủ thể có quyền READ
  AND tài liệu nằm trong phạm vi được phép
  AND chính sách trạng thái/tenant/chia sẻ hiện tại thỏa mãn
DENY trong các trường hợp còn lại.
~~~

Chỉ kiểm tra một role chung chung chưa đủ: người có vai trò đọc không nhất thiết có quyền đọc mọi tài liệu hoặc mọi tenant. Mặt khác, yêu cầu kiểm tra quyền cũng không được tự động bỏ qua chỉ vì thao tác xảy ra trong backend.

## 3. Những lối vào có thể dẫn tới cùng thao tác

~~~text
                       HTTP endpoint -------+
                                            |
                       Admin endpoint ------+
                                            |
                       CLI / batch ---------+
                                            |
                       Scheduler -----------+---> service / action ---> dữ liệu
                                            |
                       Message consumer ----+
                                            |
                       Callback / future ---+
                                            |
                       Internal direct call +
~~~

Ma trận đầu tiên cần lập:

| Đường vào | Cách có thể bỏ qua điểm kiểm tra dự kiến | Kiểm thử tiêu biểu |
| --- | --- | --- |
| HTTP giao diện chính | Advice chỉ gắn một handler | Người khác tenant gọi handler chính bị từ chối |
| HTTP API khác | Handler mới gọi thẳng nghiệp vụ | Cùng hành động qua API mới vẫn bị từ chối |
| Endpoint quản trị | Cấp role quá rộng hoặc bỏ resource scope | Admin phạm vi hạn chế không truy cập toàn tenant |
| CLI/batch | Command không dùng object đã được instrument | CLI bị deny với tài nguyên ngoài quyền |
| Scheduler | System account được cấp toàn quyền mặc định | Job chỉ được xử lý phạm vi đã cấu hình |
| Message consumer | Tin role/tenant khai trong payload | Message giả metadata không mở được quyền |
| Callback | Chạy sau request context hoặc trên thread khác | Thiếu context thì deny; có context đúng mới allow |
| Future/queue | Advice chỉ bảo vệ submit, không bảo vệ task thực | Worker bị deny nếu chính sách tại execution yêu cầu |
| Self-invocation | Lời gọi nội bộ có thể bỏ qua call interception | Gọi method A dẫn đến sensitive method B vẫn bị kiểm tra |
| Direct reference | Caller cầm object đích thay vì proxy/wrapper | Gọi thẳng đối tượng cũng không bypass được quyền |
| Reflection/dynamic call | Cơ chế gọi không đi qua điểm interception được giả định | Xác minh behavior với runtime và loại join point thực tế |
| Overload/inheritance | Pointcut không khớp chữ ký mới | Mỗi overload/override nhạy cảm vẫn được bảo vệ |
| Retry/replay | Nhánh hồi phục bỏ qua kiểm tra hoặc dùng quyền cũ | Một retry/replay không mở đường đặc quyền |

Không cần tạo tất cả mô hình này trong một ứng dụng nhỏ. Cần liệt kê **đúng những đường vào đang tồn tại**, đặc biệt đường vận hành ít người nhìn thấy.

## 4. Vì sao proxy/interceptor và weaving có coverage khác nhau?

### 4.1. Gọi qua wrapper so với gọi thẳng target

Một dạng interception có thể biểu diễn bằng wrapper:

~~~java
// Fragment minh họa, các thành phần được định nghĩa nơi khác.
Result guardedCall(Request req) {
    policy.requireAllowed(req);
    return target.execute(req);
}
~~~

Caller gọi qua guardedCall sẽ được kiểm tra. Nhưng nếu caller có tham chiếu trực tiếp tới target:

~~~java
// Fragment minh họa lối khác.
Result directCall(Request req) {
    return target.execute(req);
}
~~~

Nếu target không có guard riêng, directCall có thể trở thành bypass. Test chỉ xác minh guardedCall hoạt động chưa chứng minh directCall an toàn.

Với một số hệ thống AOP dựa trên proxy, lời gọi qua proxy mới chạy advice. Với weaving tại method execution, một số lời gọi trực tiếp hoặc nội bộ có thể vẫn bị instrument. Vì vậy, **không khẳng định mọi AOP đều có cùng lỗ hổng proxy**; hãy đo coverage của cơ chế cụ thể.

### 4.2. Self-invocation

Ví dụ:

~~~java
// Fragment minh họa.
public void executeBatch() {
    changeSensitiveState();
}

public void changeSensitiveState() {
    writeRepository();
}
~~~

Lời gọi changeSensitiveState từ executeBatch trên **cùng đối tượng** có thể không đi qua proxy, nên một advice gắn với lời gọi external vào changeSensitiveState không chạy. Nếu AOP instrument tại method execution bằng weaving, kết quả có thể khác.

Bộ kiểm thử cần có ca từ chối đi vào executeBatch và quan sát số lần write thực tế. Không chỉ gọi changeSensitiveState từ client và kết luận mọi đường đều an toàn.

### 4.3. Overload, phương thức kế thừa, constructor và reflection

Khi thêm một overload, đổi package hoặc đổi annotation, biểu thức pointcut có thể không còn khớp. Một số hình thức proxy có giới hạn đối với method final/private hoặc đối tượng không được tạo qua bộ cấp phát phù hợp. Reflection và method handle cũng cần được xem theo cơ chế join point mà runtime hỗ trợ.

Tạo các test rõ ràng:

- Mỗi overload thực sự có thể gọi thao tác nhạy cảm.
- Method qua interface, superclass, override và default implementation.
- Object được xây qua factory/composition root và object được tạo trực tiếp khi điều đó có thể.
- Internal call và external call tới cùng method.
- Đường reflection/dynamic invocation được sản phẩm thật cho phép.
- Sau mỗi refactor đổi tên method/package, pointcut vẫn match đúng hoặc đã được điều chỉnh.

Không cần đoán hành vi của một công nghệ chưa xác định; kiểm thử integration trên runtime thật sẽ cho câu trả lời.

## 5. Chính sách quyền phải dựa trên cả tài nguyên

Tổ chức kiểm thử theo bộ dữ liệu có ý nghĩa:

| Chủ thể | Hành động | Tài nguyên | Kết quả |
| --- | --- | --- | --- |
| Owner có quyền | READ | Tài liệu thuộc phạm vi owner | ALLOW |
| Người cùng tenant nhưng thiếu quyền | READ | Tài liệu cùng tenant | DENY |
| Người có READ ở tenant A | READ | Tài liệu tenant B | DENY |
| Người được chia sẻ tường minh | READ | Tài liệu được cấp grant | ALLOW nếu grant hợp lệ |
| User đã bị thu hồi | UPDATE | Tài liệu từng được phép | DENY theo chính sách hiện hành |
| Anonymous | EXPORT | Tài liệu bất kỳ | DENY |
| Service account có scope A | DELETE | Tài liệu scope B | DENY |
| Chủ thể có READ | DELETE | Tài liệu được đọc | DENY nếu không có DELETE |

Mục đích là tránh lỗi **Broken Object-Level Authorization**: caller có quyền thực hiện một loại thao tác nhưng không có quyền với **đối tượng cụ thể**. Trong ứng dụng đa tenant, không được tin tenant do client tự khai là đủ; phải dựa trên danh tính và quyền được xác nhận tại trust boundary.

Một ma trận hữu ích có năm chiều:

1. **Subject:** anonymous, owner, non-owner, revoked, service account.
2. **Action:** read, update, delete, export, batch.
3. **Resource:** owner, foreign tenant, shared, archived, nonexistent.
4. **Entry:** HTTP, CLI, scheduler, callback, message, direct call.
5. **State/time:** trước/sau thu hồi quyền, trước/sau thay đổi sở hữu, callback muộn.

Không cần kiểm thử tích Descartes vô hạn. Chọn các cặp và tình huống rủi ro cao, đồng thời **mỗi đường vào quan trọng đều có ca DENY**.

## 6. Ví dụ Java 17+: kiểm thử nhiều đường vào có backstop ở nghiệp vụ

Chương trình sau dùng một policy tập trung: subject phải có quyền đọc và thuộc đúng tenant của tài liệu. Hai điểm cưỡng chế được minh họa:

- GuardAdvice kiểm tra trước khi gọi target, tương đương một dạng around advice.
- DocumentService kiểm tra lại ở **ranh giới nghiệp vụ**, vì đó là nơi dữ liệu được trả. Nhờ vậy, caller giữ tham chiếu trực tiếp tới service vẫn không được bypass quyền.

Tạo tệp **AspectAccessPathsDemo.java**:

~~~java
import java.util.function.Supplier;

public class AspectAccessPathsDemo {
    record Actor(String tenantId, boolean canRead) {}
    record Document(String id, String tenantId) {}

    static final class Denied extends SecurityException {
        Denied() {
            super("access denied");
        }
    }

    static final class Policy {
        void requireRead(Actor actor, Document document) {
            if (actor == null || document == null
                    || !actor.canRead()
                    || !actor.tenantId().equals(document.tenantId())) {
                throw new Denied();
            }
        }
    }

    interface DocumentApi {
        String read(Actor actor, Document document);
    }

    static final class DocumentService implements DocumentApi {
        private final Policy policy;

        DocumentService(Policy policy) {
            this.policy = policy;
        }

        @Override
        public String read(Actor actor, Document document) {
            policy.requireRead(actor, document);
            return "DATA:" + document.id();
        }
    }

    static final class GuardAdvice implements DocumentApi {
        private final DocumentApi target;
        private final Policy policy;

        GuardAdvice(DocumentApi target, Policy policy) {
            this.target = target;
            this.policy = policy;
        }

        @Override
        public String read(Actor actor, Document document) {
            policy.requireRead(actor, document);
            return target.read(actor, document);
        }
    }

    static void verify(
            String path, boolean shouldAllow, Supplier<String> action) {
        try {
            String value = action.get();
            if (!shouldAllow) {
                throw new AssertionError("Unexpected access: " + path);
            }
            System.out.println("ALLOW " + path + " -> " + value);
        } catch (Denied denied) {
            if (shouldAllow) {
                throw new AssertionError("Unexpected denial: " + path, denied);
            }
            System.out.println("DENY " + path);
        }
    }

    public static void main(String[] args) {
        Policy policy = new Policy();
        DocumentService core = new DocumentService(policy);
        DocumentApi guarded = new GuardAdvice(core, policy);

        Actor owner = new Actor("TENANT-A", true);
        Actor outsider = new Actor("TENANT-B", true);
        Actor noPermission = new Actor("TENANT-A", false);
        Document doc = new Document("DOC-7", "TENANT-A");

        verify("http-owner", true, () -> guarded.read(owner, doc));
        verify("http-cross-tenant", false,
                () -> guarded.read(outsider, doc));
        verify("cli-no-permission", false,
                () -> guarded.read(noPermission, doc));
        verify("scheduled-cross-tenant", false,
                () -> guarded.read(outsider, doc));

        // Cố ý đi thẳng vào core, bỏ qua GuardAdvice.
        verify("direct-cross-tenant", false,
                () -> core.read(outsider, doc));
        verify("direct-owner", true, () -> core.read(owner, doc));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac AspectAccessPathsDemo.java
java AspectAccessPathsDemo
~~~

Stdout chính xác:

~~~text
ALLOW http-owner -> DATA:DOC-7
DENY http-cross-tenant
DENY cli-no-permission
DENY scheduled-cross-tenant
DENY direct-cross-tenant
ALLOW direct-owner -> DATA:DOC-7
~~~

**Đọc kết quả:**

- Chủ thể hợp lệ đi qua wrapper được cho phép.
- Người có quyền READ chung nhưng ở tenant khác vẫn bị từ chối.
- Đường CLI giả lập với người thiếu quyền bị từ chối.
- Đường job giả lập không có đặc quyền mặc định với tenant khác.
- Lời gọi **trực tiếp** vào DocumentService bỏ qua GuardAdvice nhưng vẫn bị deny vì core thực hiện cùng policy.
- Lời gọi trực tiếp hợp lệ vẫn nhận đúng dữ liệu, chứng minh backstop không gây deny tất cả.

Các tên đường HTTP, CLI, scheduler trong chương trình chỉ là **nhãn của các test driver** gọi cùng API; ví dụ không dựng máy chủ, parser hay scheduler thật. Test này minh họa semantics policy và wrapper. Để chứng minh AOP được gắn đúng ở từng entry point của sản phẩm, cần integration test chạy **runtime/cơ chế weaving hoặc interception thật**.

Trong ví dụ, một AccessDenied exception bắt nguồn từ policy; class Denied kế thừa SecurityException nhưng tên/kiểu exception trong ứng dụng thật do hợp đồng API quyết định. Dùng một exception riêng cũng giúp bộ kiểm thử phân biệt DENY do chính sách với các lỗi hệ thống khác.

### Vì sao cần chốt bảo vệ tại core?

Nếu DocumentService trả dữ liệu mà không kiểm tra policy, đường direct có thể bypass wrapper. Việc có chốt quyền ở nơi dữ liệu thực sự được truy cập giúp bảo toàn bất biến khi có caller nội bộ mới. Nếu toàn bộ đường gọi được hệ thống khác bảo đảm buộc phải đi qua advice, có thể chọn một điểm cưỡng chế duy nhất; nhưng bảo đảm đó phải có bằng chứng kiểm thử, chứ không chỉ là quy ước giữa lập trình viên.

## 7. Kiểm thử side effect: từ chối phải xảy ra trước hành động

Một bài test thấy ngoại lệ DENY chưa đủ nếu thao tác ghi đã diễn ra trước đó:

~~~text
caller -> update database -> publish event -> check permission -> DENY
~~~

Caller thấy từ chối, nhưng dữ liệu đã đổi và event đã phát. Với thao tác UPDATE, DELETE hoặc EXPORT, test cần assert đồng thời:

- Trạng thái kết quả là DENY đúng hợp đồng.
- Số lần ghi vào repository bằng 0.
- Số thông điệp hoặc callback ra ngoài bằng 0.
- Không có dữ liệu bí mật được trả, ghi vào log hay phát qua event.
- Không có tác dụng phụ bị retry hoặc compensation thiếu kiểm soát.

Ví dụ expected assertion:

~~~text
outcome = DENIED
repositoryWriteCount = 0
publishedEventCount = 0
externalRequestCount = 0
disclosedRecords = 0
~~~

Đây là checklist kiểm thử, không phải stdout của chương trình Java ở phần trước. Có thể dùng fake repository, fake event publisher và test spy để đo số lần gọi. Với tác vụ có transaction hoặc nhiều bước, cần kiểm tra trạng thái **sau transaction/commit** chứ không chỉ số lệnh được gọi.

Một around advice được thiết kế đúng nên từ chối trước khi gọi target nếu không có quyền; nhưng nếu target có lối khác trực tiếp vào phần cập nhật, cũng cần một điểm enforcement đủ mạnh tại nơi chịu trách nhiệm cho side effect.

## 8. Internal call và self-invocation

Tình huống minh họa:

~~~java
// Fragment của một class; chưa phải chương trình độc lập.
public void batchUpdate() {
    updateSensitiveRecord();
}

public void updateSensitiveRecord() {
    writeDatabase();
}
~~~

Với một số cơ chế proxy-based interception, lời gọi từ batchUpdate tới updateSensitiveRecord trong cùng đối tượng không đi qua proxy, nên advice gắn ở external entry của updateSensitiveRecord không được gọi lần nữa. Với method-execution weaving, kết quả có thể khác.

Bài kiểm thử cần chủ động gọi batchUpdate với người không được phép và assert writeCount bằng 0. Nếu test chỉ gọi updateSensitiveRecord từ một client đi qua proxy, trường hợp tự gọi này vẫn chưa được chứng minh.

Cách xử lý có thể là chuyển kiểm tra tới ranh giới nghiệp vụ bắt buộc, tổ chức caller đi qua một API có guard đáng tin, hoặc dùng cơ chế AOP hỗ trợ join point mong muốn. Không áp dụng một cách khắc phục chung cho mọi implementation; quan sát thực tế runtime và bảo toàn kiến trúc quyền là yêu cầu chính.

## 9. CLI, batch và scheduler: đừng coi nguồn nội bộ là toàn quyền

Một batch import có thể xử lý hàng nghìn bản ghi. Nếu nó gọi thẳng repository và không thực thi chính sách theo tài nguyên, một lỗi cấu hình hoặc một tệp nhập sai tenant có thể gây ảnh hưởng lớn.

Những câu hỏi cần kiểm thử:

1. Command được gọi bằng danh tính nào, và actor gốc có được lưu vết không?
2. Task dùng service account nào, scope được cấu hình tới đâu?
3. Mỗi record trong batch có được kiểm tra đúng resource/tenant không?
4. Batch chứa cả bản ghi hợp lệ và không hợp lệ sẽ atomic rollback hay partial success theo hợp đồng?
5. Retry một batch bị từ chối có gây mutation lặp lại không?
6. Một lệnh quản trị có được phép bỏ một số kiểm tra không; nếu có, ngoại lệ đó có được chính sách phê duyệt và ghi audit?

System account phải tuân theo nguyên tắc **quyền tối thiểu**. Một job chạy tự động không chứng minh mọi hành động của nó đều được ủy quyền. Nếu thiếu actor người dùng, chính sách có thể dùng một danh tính workload đã được xác thực và bị giới hạn, thay vì coi null principal là admin.

## 10. Message consumer và dữ liệu nguồn không đáng tin

Một message có thể chứa subjectId, role, tenantId, action và resourceId. Các trường trong payload **không tự chứng minh quyền**. Consumer phải xác định nguồn tin cậy và đánh giá chính sách theo resource thật.

Ví dụ payload:

~~~json
{
  "actorId": "user-17",
  "tenantId": "TENANT-A",
  "role": "ADMIN",
  "action": "DELETE",
  "resourceId": "DOC-7"
}
~~~

Nên kiểm thử:

- Role tự khai là ADMIN nhưng người gửi không có bằng chứng ủy quyền.
- Tenant trong payload khác tenant được xác nhận.
- Message bị replay sau khi role của user bị thu hồi.
- Consumer retry code qua nhánh recovery và bỏ qua một advice.
- Service account của consumer có quyền vận hành queue nhưng không có quyền xóa tùy ý mọi document.
- Message tới từ producer hợp lệ nhưng resource đã đổi ownership.

Mỗi hệ thống có thể chọn “quyền tại lúc yêu cầu được nhận” hoặc “quyền tại thời điểm consumer thực thi”. Nếu cần giữ quyền của thời điểm trước, phải có **ủy quyền có scope, thời hạn và nguồn tin cậy rõ ràng**. Không ngầm giữ một role trong message mãi mãi.

## 11. Callback, future và ngữ cảnh bảo mật qua luồng

Một lời gọi được advice kiểm tra quyền lúc t0 có thể chỉ enqueue công việc và trả về future. Worker thực sự đọc/ghi dữ liệu ở t1, sau khi caller đã rời đi hoặc quyền thay đổi.

~~~text
t0: request -> advice check -> submit task -> trả future
t1: context thay đổi / quyền bị thu hồi
t2: worker chạy task -> đọc hoặc cập nhật tài nguyên
t3: callback/future hoàn tất
~~~

Điều cần kiểm thử phụ thuộc policy:

- Task có phải kiểm tra quyền lại ở t2 không?
- Ai là principal đáng tin khi worker thực thi?
- ThreadLocal của caller được capture/restore/cleanup như thế nào?
- Nếu không có context hoặc context lỗi, hệ thống DENY hay tự cấp quyền hệ thống?
- Callback được gọi ngay trong thread caller hoặc sau này trên worker có khác hành vi không?
- Retry sau exceptional completion có làm lặp side effect đã xảy ra không?
- Khi cancellation được yêu cầu, code task còn có thể tiếp tục ghi dữ liệu không?

**ThreadLocal không tự động đi qua executor hoặc callback**. Nếu dùng context theo luồng, cần chuyển tường minh hoặc cơ chế propagation của mô hình thực thi; khôi phục context ở worker và dọn trong finally để không rò qua công việc sau.

Một completion callback báo lỗi không đồng nghĩa mọi side effect được rollback. Cancellation cũng không đồng nghĩa task đã thực sự dừng. Khi kiểm thử quyền cho tác vụ bất đồng bộ, assert trạng thái resource cuối cùng và khả năng truy cập dữ liệu, không chỉ trạng thái future.

## 12. TOCTOU: kiểm tra quyền rồi tài nguyên thay đổi

Time-of-check to time-of-use (TOCTOU) xảy ra khi quyền được kiểm tra ở một thời điểm nhưng resource hoặc quyền đổi trước khi thao tác thật diễn ra.

~~~text
t0: policy cho user A quyền sửa DOC-7
t1: quyền bị thu hồi hoặc DOC-7 chuyển owner
t2: worker cập nhật DOC-7 dựa vào kết quả cũ
~~~

Nếu hợp đồng yêu cầu quyền còn hiệu lực tại lúc commit, việc check từ t0 là chưa đủ. Có thể cần kiểm tra lại ở transaction boundary, khóa/version, điều kiện cập nhật dữ liệu hoặc token ủy quyền có thời hạn theo chính sách.

Kiểm thử phải chủ động thay đổi trạng thái giữa t0 và t2; nếu test luôn dùng dữ liệu cố định, nó không phát hiện race. Tình huống này không có đáp án chung cho mọi nghiệp vụ, vì một operation đã được chấp nhận có thể được cấp quyền tiếp tục theo một lease hợp lệ. Nhưng quy tắc về thời điểm quyết định quyền phải được công bố và kiểm chứng.

## 13. Thiết kế ba tầng kiểm thử để không nhầm phạm vi

### Tầng 1: Policy unit test

Gọi trực tiếp policy với nhiều subject/action/resource/context. Bao gồm: hợp lệ, khác tenant, thiếu quyền, null, anonymous, revoked, shared resource và hành động khác nhau. Tầng này chứng minh **logic quyết định**, chưa chứng minh advice thực sự được gắn.

### Tầng 2: Advice/interceptor test

Gọi qua một wrapper/proxy được thiết lập trong test; xác minh:

- Denied action không chạy target.
- Allowed action chạy target đúng một lần.
- Exception từ policy và target truyền đúng hợp đồng.
- Nhánh around/before/after thực thi đúng thứ tự.
- Logging/metrics không che mất quyết định quyền.
- Nếu có nhiều advice, thứ tự kiểm tra quyền so với side effect phù hợp.

Đây là bằng chứng cho **cấu hình interception đã test**, không mặc nhiên phủ hết entry point ngoài môi trường đó.

### Tầng 3: Integration test trên đường vào thực tế

Khởi động runtime AOP và các adapter cần thiết. Gọi đúng HTTP endpoint, CLI, scheduler handler, consumer, callback hoặc service trực tiếp như một caller thực. Ghi nhận:

- Đúng chủ thể/action/resource được đưa vào policy.
- Advice ở join point dự định có chạy hay không.
- Từ chối có giữ dữ liệu bí mật và side effect an toàn không.
- Những điểm direct/self-call có một điểm cưỡng chế tương đương không.
- Sau khi thay đổi phương thức/overload/pointcut, coverage còn đúng không.

Một HTTP test trả “forbidden” có thể là do handler chặn sớm; để biết advice ở service được áp dụng thật, dùng instrumentation/test spy thích hợp thay vì suy đoán từ status code.

## 14. Bản đồ coverage và cách lấy bằng chứng

Một bảng bằng chứng nên liên kết **sensitive operation → entry point → enforcement point → test allow/deny → side effect assertion**:

| Operation | Entry point | Enforcement | Deny test | Side effect |
| --- | --- | --- | --- | --- |
| Read document | HTTP | GuardAdvice + core policy | Cross-tenant | No disclosure |
| Read document | CLI | Core policy | Missing READ | No disclosure |
| Update document | Batch | Core policy / transactional boundary | Invalid resource grant | No write |
| Delete document | Consumer | Authenticated workload + policy | Fake role/foreign tenant | No delete/event |
| Export data | Scheduled task | Scoped service identity + policy | Tenant outside job scope | No export |
| Modify resource | Internal self-call | Guard at sensitive operation | Unauthorized caller | No mutation |

Việc gắn nhãn “enforcement point” bắt buộc đội ngũ chỉ ra **vị trí có thể ngăn hành động**, thay vì chỉ liệt kê test đã pass. Khi một entry point mới xuất hiện, cần thêm nó vào bản đồ và test tương ứng.

### Negative testing phải kiểm tra nguyên nhân từ chối

Nếu test gửi request trái quyền và thấy connection refused, đó không phải bằng chứng authorization hoạt động. Nếu CLI không khởi chạy vì thiếu cấu hình, test cũng chưa kiểm tra policy. Bộ kiểm thử phải phân biệt Denied từ chính sách với lỗi transport, validation, dependency và lỗi ngoài ý muốn.

Đối với thao tác UPDATE/DELETE, kiểm tra DB state sau lỗi. Đối với export/read, đảm bảo response/log/error không vô tình chứa dữ liệu nhạy cảm. Nếu có retry hoặc callback, kiểm tra sau khi toàn bộ tác vụ liên quan đã đến ranh giới hoàn tất/cleanup theo hợp đồng.

## 15. Hạn chế của chỉ một lớp AOP cho bảo mật

AOP có thể giảm lặp mã authorization, nhưng không thay thế thiết kế bảo mật tổng thể. Một chính sách chỉ gắn bằng proxy/wrapper có thể trở nên mong manh nếu code có cách tạo target trực tiếp hoặc chọn sai join point. Những biện pháp hỗ trợ gồm:

- Policy service tập trung để nhiều điểm enforcement sử dụng cùng quy tắc.
- Guard tại boundary sở hữu dữ liệu hoặc thao tác nhạy cảm.
- Least privilege ở data store, queue và service account.
- Identity/context đáng tin tại từng trust boundary.
- Kết quả DENY mặc định khi thiếu thông tin cần thiết.
- Giám sát việc pointcut không còn match sau refactor.
- Integration tests cho entry mới, self-invocation và async continuation.
- Không dùng log/audit thành chứng cứ duy nhất rằng quyền đã được kiểm tra.

Không bắt buộc kiểm tra trùng ở mọi tầng nếu có **một ranh giới duy nhất thực sự không thể bypass**. Tuy nhiên, tính không thể bypass ấy phải được xây dựng và kiểm chứng trên kiến trúc thật.

## 16. Các lỗi phổ biến khi lập bài test

**Chỉ test happy path.** Người hợp lệ đọc được dữ liệu chưa chứng minh người khác không thể đọc.

**Chỉ test policy object.** Unit test có thể pass khi pointcut không match ở runtime.

**Chỉ test endpoint chính.** CLI, consumer, scheduler hoặc lệnh trực tiếp vẫn có thể bypass.

**Chỉ assert exception.** Exception có thể bị ném sau khi mutation đã commit; phải kiểm tra side effect.

**Giả định mọi AOP đều có cùng coverage.** Proxy, wrapper và weaving có quy tắc khác nhau; kiểm tra behavior thật.

**Cho phép null principal như system admin.** Thiếu context phải được xử lý an toàn, thường deny-by-default.

**Tin role/tenant trong message.** Dữ liệu từ producer không tự tạo quyền truy cập.

**Không kiểm tra resource scope.** Role READ không có nghĩa có quyền với tất cả tài liệu.

**Không test overload hoặc method mới.** Pointcut chỉ khớp chữ ký cũ dẫn tới lỗ hổng khi refactor.

**Cho rằng submit job đã được check nghĩa là execution an toàn.** Worker có thể chạy sau khi context/permission đổi.

**Không test retry/replay.** Nhánh hồi phục có thể đi qua code khác hoặc giữ quyền cũ không còn hợp lệ.

## 17. Quy trình thực hành khi thêm một điểm vào mới

1. Xác định tài nguyên và hành động nhạy cảm mà entry point mới có thể chạm tới.
2. Vẽ lại đường gọi tới điểm đọc/ghi dữ liệu thật.
3. Xác định chủ thể và bằng chứng ủy quyền được lấy từ đâu.
4. So điểm gọi với pointcut và join point đang được runtime AOP áp dụng.
5. Tạo ít nhất một trường hợp ALLOW hợp lệ và một trường hợp DENY có ý nghĩa.
6. Với DENY, assert không có data disclosure, mutation, event hoặc external call.
7. Nếu có callback/queue, xác định quyền tại thời điểm đăng ký hay thực thi.
8. Nếu có self-call/direct-call, xác minh guard bắt buộc vẫn hoạt động.
9. Chạy integration test qua chính adapter thật, ghi nhận lý do từ chối.
10. Cập nhật ma trận khi có overload, tài nguyên mới, thay đổi pointcut hoặc chính sách chia sẻ.

## 18. Bài tập tự đánh giá

**Câu 1.** Một user không có quyền bị từ chối khi gọi HTTP, nhưng CLI gọi thẳng service và xem được cùng tài liệu. Điều gì chưa đúng?

**Đáp án:** Enforcement coverage thiếu. Đường HTTP chạy advice, CLI không có kiểm tra quyền tương đương. Cần buộc CLI đi qua guard và/hoặc bảo vệ tại thao tác nhạy cảm.

**Câu 2.** Tại sao test nhận Denied không đủ cho phương thức xóa dữ liệu?

**Đáp án:** Xóa có thể đã xảy ra trước khi policy từ chối. Phải kiểm tra trạng thái database, event, external request và ranh giới commit, đảm bảo không có side effect trái quyền.

**Câu 3.** Nếu một phương thức tự gọi một phương thức nhạy cảm trên cùng đối tượng, advice có luôn chạy không?

**Đáp án:** Phụ thuộc cơ chế AOP. Proxy-based call interception có thể bỏ qua self-invocation, method-execution weaving có thể khác. Test phải chạy trên runtime thật và giữ guard ở boundary phù hợp.

**Câu 4.** Người dùng có READ nhưng không thuộc tenant của tài liệu. Có được phép không?

**Đáp án:** Không, trừ khi có một grant/resource policy hợp lệ cho phép rõ ràng. Authorization cần dựa trên tài nguyên cụ thể, không chỉ role.

**Câu 5.** Một message chứa role ADMIN từ producer không đáng tin. Consumer có thể tin không?

**Đáp án:** Không. Cần xác thực nguồn, chủ thể, phạm vi ủy quyền và đánh giá policy tại trust boundary.

**Câu 6.** Task được submit khi user hợp lệ, nhưng chạy sau khi quyền bị thu hồi. Kiểm thử gì?

**Đáp án:** Tạo trường hợp thay quyền giữa submit và execution, rồi xác minh behavior theo chính sách thời điểm authorization đã công bố; không mặc định context ở thời điểm submit luôn còn hợp lệ.

**Câu 7.** Policy unit test đều pass nhưng một overload mới không có advice. Loại test cần thêm?

**Đáp án:** Integration test gọi overload qua runtime AOP thật, xác minh policy/enforcement hoạt động trước side effect. Có thể dùng spy để chứng minh advice được kích hoạt.

**Câu 8.** Vì sao đường direct trong chương trình Java minh họa vẫn bị từ chối dù không dùng GuardAdvice?

**Đáp án:** Vì DocumentService cũng gọi Policy.requireRead tại ranh giới dữ liệu. Đây là một điểm cưỡng chế bổ sung chống bypass wrapper.

## 19. Checklist trước khi công bố đã kiểm thử truy cập

- [ ] Có inventory sensitive operation và entry point hiện tại.
- [ ] Có ma trận subject/action/resource/entry/context tối thiểu.
- [ ] Có test cross-tenant và thiếu quyền cho mỗi đường vào quan trọng.
- [ ] Có bằng chứng pointcut match đúng join point trên runtime thật.
- [ ] Có kiểm thử self-invocation, direct reference và overload nếu kiến trúc cho phép.
- [ ] Có test deny với side effect bằng 0, không chỉ exception.
- [ ] Có xử lý an toàn khi principal/context thiếu hoặc giả mạo.
- [ ] Có test callback/future/worker khi context hoặc permission đổi.
- [ ] Có kiểm thử CLI/batch/message consumer với least-privilege system account.
- [ ] Có kiểm tra quyền theo resource, không chỉ role chung.
- [ ] Có regression khi thêm entry point, refactor pointcut hoặc thay policy.
- [ ] Có danh sách đường chưa kiểm chứng cùng phương án giảm thiểu rủi ro.

## Kết luận kiến thức

Một access-control aspect hoạt động trên luồng thông thường chưa chứng minh mọi lời gọi nghiệp vụ đã an toàn. Phải xuất phát từ **tài nguyên và thao tác nhạy cảm**, liệt kê tất cả đường có thể đi tới chúng, đối chiếu coverage của cơ chế AOP thực, rồi kiểm thử cả ALLOW, DENY và hậu quả ở mỗi đường. Bảo vệ cần kiểm tra subject/action/resource/context tại một ranh giới không thể bỏ qua; trực tiếp, nội bộ, callback, job và message phải được xem như những trường hợp kiểm thử thật.