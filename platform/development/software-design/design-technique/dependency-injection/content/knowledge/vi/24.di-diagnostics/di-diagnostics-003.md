# Đối tượng được tạo trực tiếp nên không có phụ thuộc do container cung cấp

Một trong những lỗi khó hiểu khi mới dùng **Dependency Injection (DI)** là: một lớp đã khai báo dependency qua annotation hoặc callback của framework, nhưng lúc chạy dependency vẫn **`null`**, phương thức khởi tạo không được gọi, hoặc các hành vi như transaction, caching và authorization không có tác dụng. Nguyên nhân rất thường gặp là **đối tượng đang được sử dụng đã được tạo bằng `new` ở một nơi khác, không phải instance mà DI container đã tạo và cấu hình**.

Lỗi này không có nghĩa **mọi lệnh `new` đều sai**. Với Java thuần, composition root vẫn có thể gọi constructor và truyền đầy đủ dependency một cách hợp lệ. Vấn đề là **trông chờ container tự inject, khởi tạo, áp dụng proxy hoặc dọn dẹp cho một object mà container không sở hữu và không tham gia tạo/cấu hình**.

Bài thuộc chương **Chẩn đoán DI** trong module **Dependency Injection**. Ta sẽ xác định đúng instance đang chạy, phân biệt container-managed với manually constructed, sửa lỗi bằng **constructor injection** và **composition root**, tìm nguyên nhân sâu hơn liên quan đến scope/proxy/lifecycle, rồi thực hành Java 17 thuần trước khi mở rộng sang DI container.

## 1. Triệu chứng: có khai báo injection nhưng dependency vẫn thiếu

Giả sử một ứng dụng dùng Spring có lớp:

~~~java
// Ví dụ cú pháp Spring, KHÔNG thuộc chương trình Java thuần ở mục 7.
@Component
class ReminderService {
    @Autowired
    private NoticeGateway gateway;

    void remind(String customerId) {
        gateway.deliver(customerId);
    }
}
~~~

Nếu một controller hoặc helper viết:

~~~java
ReminderService reminder = new ReminderService();
reminder.remind("C-100");
~~~

thì đối tượng `reminder` được tạo trực tiếp theo quy tắc Java: constructor chạy, các trường nhận giá trị mặc định của JVM, sau đó method được gọi. Annotation `@Component` và `@Autowired` **không tự khiến JVM tìm bean và gán trường**. Với cơ chế tiêm trường thông thường của Spring, việc inject diễn ra khi Spring tham gia quản lý instance. `gateway` ở object tạo trực tiếp sẽ vẫn `null` nếu không có mã nào khác gán nó.

Vì thế, lời gọi `gateway.deliver(...)` có thể ném `NullPointerException`, trong khi cùng một lớp đó được container cung cấp ở nơi khác lại hoạt động bình thường.

### Các triệu chứng có thể xuất hiện cùng nhau

| Triệu chứng | Giả thuyết cần kiểm tra | Điều chưa thể kết luận ngay |
| --- | --- | --- |
| Trường `@Autowired` bằng `null` | Object được `new` trực tiếp, bean không được quản lý, hoặc injection chưa thực hiện | Chỉ thấy `null` chưa đủ chứng minh nguyên nhân; cũng có thể sai registration/qualifier |
| Giá trị `@Value` không được gán | Object không đi qua bước xử lý cấu hình của container | Không có nghĩa biến môi trường chắc chắn thiếu |
| Callback `@PostConstruct` không chạy | Instance không trải qua lifecycle init của framework | Có thể callback bị cấu hình sai hoặc context chưa hoàn tất |
| `@Transactional` không có hiệu lực | Lời gọi không đi qua proxy/advice thích hợp | Cũng có thể do self-invocation hoặc cấu hình transaction |
| `@Async` chạy đồng bộ hoặc `@Cacheable` không cache | Invocation không được intercept theo cơ chế đang dùng | Cần kiểm tra cả cấu hình AOP, pointcut và loại proxy |
| `@PreDestroy` không được gọi khi tắt context | Resource có thể nằm ngoài ownership của context | Không nên suy rằng mọi object bắt buộc được container tự đóng |
| Hai nơi nhìn thấy hai trạng thái khác nhau | Một nơi nhận managed bean, nơi khác tự tạo instance mới | Cũng có thể là hai scope/context khác nhau được cấu hình có chủ đích |

**Nguyên tắc chẩn đoán:** kiểm tra **đúng object mà consumer đang dùng**. Việc tìm thấy một bean đúng kiểu trong container không chứng minh caller đang giữ **cùng instance** hoặc đi qua đúng proxy.

## 2. Vì sao container không thể tự xử lý mọi object được tạo bằng new?

JVM không tự biết có một DI container đang hoạt động. Khi code gọi `new ReminderService()`, Java tạo object theo constructor và field initialization của lớp. Những cơ chế như field injection, setter injection do framework điều phối, lifecycle callback hoặc proxy weaving **đều cần một bước xử lý bổ sung** tùy framework.

So sánh hai luồng:

~~~mermaid
flowchart TD
    subgraph Manual["Tạo trực tiếp ngoài container"]
        CallerA["Consumer"] -->|"new ReminderService()"| Raw["Object được tạo trực tiếp"]
        Raw --> Missing["Không tự có field injection / lifecycle / proxy của container"]
    end
    subgraph Managed["Lấy instance do container quản lý"]
        Root["Composition root / registration"] --> Container["DI container"]
        Container --> Create["Tạo hoặc nhận bean theo hợp đồng"]
        Create --> Inject["Resolve và inject dependency"]
        Inject --> Init["Khởi tạo, áp dụng cơ chế lifecycle"]
        Init --> MaybeProxy["Có thể tạo proxy/interceptor"]
        MaybeProxy --> CallerB["Consumer nhận managed reference"]
    end
~~~

Đối tượng do `new` tạo không có một “sợi dây thần kỳ” kết nối với container chỉ vì **class của nó có annotation**. Container cần được yêu cầu tạo bean, được cấu hình quản lý instance trả về từ factory, hoặc được chỉ thị xử lý một instance hiện có qua API chuyên biệt mà framework cung cấp.

**Phạm vi khẳng định:** mỗi framework định nghĩa chính xác giai đoạn nào và callback nào chạy. Ví dụ, Spring có thể quản lý object **được trả về từ phương thức `@Bean`**, dù bên trong phương thức đó code dùng `new`. Điều quan trọng là **object được đăng ký và xử lý qua container**, không phải việc file nguồn có chứa từ khóa `new` hay không.

### Tại sao lỗi thường lộ ở request đầu chứ không ngay bootstrap?

Với field injection, constructor không đòi dependency ở tham số. Do đó, `new ReminderService()` vẫn biên dịch và tạo instance thành công. Lỗi có thể chỉ phát sinh khi request đầu tiên đi qua một method cần `gateway`.

Với constructor injection tường minh:

~~~java
final class ReminderService {
    private final NoticeGateway gateway;

    ReminderService(NoticeGateway gateway) {
        this.gateway = java.util.Objects.requireNonNull(gateway, "gateway");
    }
}
~~~

một lời gọi thiếu tham số **không thể biên dịch** nếu chỉ có constructor này. Lời gọi cố ý truyền `null` được chặn **ngay lúc khởi tạo**. Đây là một trong những lợi ích chẩn đoán quan trọng của constructor injection: **dependency bắt buộc được khai báo trong chữ ký**, thay vì chỉ được phát hiện muộn trong thân method.

## 3. Phân biệt direct construction đúng và direct construction sai

Không nên áp dụng quy tắc “trong dự án dùng Spring thì tuyệt đối không được `new`”.

| Trường hợp | Có vấn đề về DI không? | Lý do |
| --- | --- | --- |
| Composition root viết `new ReminderService(gateway)` với dependency đầy đủ | **Không nhất thiết** | Đây là **manual DI** hợp lệ; root chịu trách nhiệm wiring và lifecycle |
| Logic nghiệp vụ viết `new ReminderService()` rồi trông đợi `@Autowired` được xử lý | **Có khả năng cao** | Object chưa đi qua injection/lifecycle của container |
| Tạo `new Order(id, quantity)` hoặc một `ArrayList` trong method | **Thông thường không** | Value object/collection không cần là managed dependency |
| Một phương thức `@Bean` trả về `new Client(settings)` | **Có thể hợp lệ** | Container quản lý instance được factory trả về theo hợp đồng registration |
| Một bean managed tự `new Helper()` nội bộ chỉ để tính toán thuần | **Thông thường không** | Helper không cần container nếu không có managed behavior |
| Một bean managed tự `new TransactionalWorker()` rồi gọi method gắn transaction advice | **Đáng nghi** | Worker được tạo ngoài container, lời gọi có thể bỏ qua proxy |
| Gọi `container.getBean(Service.class)` ở composition root | **Có thể hợp lệ** | Đây là trách nhiệm resolve ở điểm lắp ghép |
| Gọi `container.getBean(...)` rải rác trong business method | **Nên tránh** | Dễ chuyển sang Service Locator và che giấu dependency |

Điều cần bảo vệ là **ranh giới trách nhiệm**:

- **Composition root** được quyền chọn implementation, tạo object và quản lý ownership.
- **Service nghiệp vụ** nên nhận dependency đã chọn qua constructor, sử dụng chúng theo hợp đồng và không tự đi tìm một container toàn cục.
- **DI container** có thể hỗ trợ binding, scope, injection, init và teardown **cho những object mà nó quản lý**, không phải mọi object cùng class trong JVM.

## 4. Quy trình chẩn đoán từng bước

Khi gặp lỗi “`@Autowired` vẫn null” hoặc “annotation AOP không chạy”, đừng vội thêm annotation mới. Hãy lần theo **đường tạo và đường sử dụng instance**.

### Bước 1 — Xác định caller đang dùng reference nào

Bắt đầu ở dòng gây lỗi hoặc nơi policy không được áp dụng. Ghi nhận:

- Kiểu của biến mà consumer nhận.
- Instance đó đến từ tham số constructor, factory, container hay `new` trực tiếp?
- Có một wrapper/decorator/proxy ở giữa không?
- Một object mới có được tạo ngay trước lời gọi hay không?

Khi debug, có thể tạm log `System.identityHashCode(instance)` cùng loại/nguồn tạo để hỗ trợ theo dấu, nhưng **identity hash code không bảo đảm duy nhất**. Muốn biết hai reference có trỏ đúng cùng object không, dùng **`==`** trong mã chẩn đoán/test thích hợp.

### Bước 2 — Truy dấu nơi object được tạo

Tìm những đường tạo trực tiếp như:

~~~java
new ReminderService();
new TransactionalWorker();
factory.createReminderService();
ReflectionFactory.instantiate(ReminderService.class);
~~~

Không chỉ tìm `new`. Một factory, serializer, test fixture, builder hoặc API reflection cũng có thể tạo instance bên ngoài container. Cần mở implementation của factory/đường tạo liên quan và xác minh **kết quả được container quản lý hay không**.

Trong bước này, hãy phân biệt **factory do container gọi và trả về managed bean** với **factory được business code gọi để tạo object ngoài quản lý**. Cùng một lệnh `new` bên trong factory có thể dẫn đến ownership khác nhau tùy cách instance được đăng ký.

### Bước 3 — Xác minh bean có được đăng ký trong đúng context không

Nếu mong container cấp dependency, hãy kiểm tra:

- Class hoặc factory có được khai báo trong phạm vi scan/registration không?
- Profile, điều kiện cấu hình, qualifier hoặc tên bean có khớp không?
- Có nhiều bean cùng abstraction khiến container không biết chọn cái nào không?
- Có nhiều application context hoặc test context, mỗi context giữ instance riêng không?
- Bean có bị loại khỏi context bởi điều kiện môi trường không?

**Lưu ý:** tìm được bean trong context là điều kiện cần nhưng **chưa đủ**. Consumer vẫn có thể sử dụng một object khác do chính nó tạo bằng `new`.

### Bước 4 — Kiểm tra đường inject và lifecycle thực tế

Nếu container đúng là owner của instance, kiểm tra tiếp:

- Dependency được truyền bằng constructor, field hay setter?
- Có bean post-processor/lifecycle integration tương ứng không?
- Object có bị sử dụng trước khi bước initialization cần thiết hoàn tất không?
- Có code ghi đè field đã inject hoặc tự đổi reference không?
- Bean có proxy không và caller có đi **qua proxy** không?

Với Spring proxy-based AOP, lời gọi nội bộ `this.someMethod()` trên target thường **bỏ qua interceptor**. Vì thế, một bean đã được Spring quản lý vẫn có thể gặp lỗi **self-invocation**, khác với lỗi object được `new` trực tiếp. Đừng nhầm hai nguyên nhân.

### Bước 5 — Kiểm tra scope và object identity

Một service singleton-scoped nhận dependency request-scoped cần có cơ chế đúng scope (tham số phương thức, scoped provider/proxy được framework hỗ trợ...). Nếu consumer tự tạo object riêng, nó có thể giữ instance khác, không đồng bộ với bean trong container.

Những câu hỏi hữu ích:

- Cùng một binding có được resolve qua đúng context không?
- Có vô tình tạo một root container thứ hai trong test hoặc trong background worker không?
- Một bean bị gọi qua proxy ở nơi A nhưng target/raw instance ở nơi B không?
- Dependency được giữ quá vòng đời request hoặc transaction không?

### Bước 6 — Khoanh vùng bằng test không cần hạ tầng thật

Để tái hiện một lỗi injection, không nhất thiết mở database. Có thể kiểm tra:

- Object do `new` không có bước injection thủ công thì không được kỳ vọng tự có dependency.
- Object được truyền dependency qua constructor có thể chạy bằng fake.
- Managed reference do container trả về nhận dependency đúng và callback cần thiết chạy.
- Hai reference thực sự có cùng identity hay không, nếu hợp đồng scope yêu cầu.

Mục 7 xây dựng một **mini-container bằng Java 17** để minh họa chính xác sự khác biệt.

### Bước 7 — Sửa đúng ranh giới, rồi kiểm tra lại kết quả nghiệp vụ

Sửa code sao cho **consumer nhận dependency/managed service từ composition root hoặc framework**, thay vì tự tạo một đối tượng khác rồi hy vọng container tìm thấy nó. Sau đó kiểm tra **hành vi quan sát được**, scope, proxy policy và cleanup, không chỉ kiểm tra một field hết null.

## 5. Ví dụ với Spring: cùng một class nhưng hai object khác nhau

Những snippet dưới đây là **ví dụ riêng cho Spring**, không phải mã chạy độc lập bằng `javac Main.java` ở phần thực hành.

### Cách gọi có nguy cơ bỏ qua container

~~~java
// Spring-specific: ví dụ chống mẫu.
@Service
class NotificationFacade {
    void notify(String id) {
        ReminderService service = new ReminderService();
        service.remind(id);
    }
}
~~~

Dù `NotificationFacade` là managed bean, lệnh `new ReminderService()` **vẫn tạo instance thủ công**. Tính managed **không tự lan theo cú pháp `new`** từ parent sang child.

### Cách dùng constructor injection qua container

~~~java
// Spring-specific: cả hai component do Spring tạo theo cấu hình phù hợp.
@Service
class ReminderService {
    private final NoticeGateway gateway;

    ReminderService(NoticeGateway gateway) {
        this.gateway = java.util.Objects.requireNonNull(gateway);
    }

    void remind(String id) {
        gateway.deliver(id);
    }
}

@Service
class NotificationFacade {
    private final ReminderService reminders;

    NotificationFacade(ReminderService reminders) {
        this.reminders = reminders;
    }

    void notify(String id) {
        reminders.remind(id);
    }
}
~~~

Khi Spring tạo `NotificationFacade`, container giải quyết `ReminderService` cùng `NoticeGateway` theo binding/scope tương ứng, thay vì facade tự `new` một service không được xử lý.

### Trường hợp method @Bean vẫn hợp lệ dù chứa new

~~~java
// Spring-specific: container quản lý object trả về theo @Bean.
@Configuration
class ReminderConfiguration {
    @Bean
    ReminderService reminderService(NoticeGateway gateway) {
        return new ReminderService(gateway);
    }
}
~~~

Đây **không** phải lỗi “dùng `new` nên không có DI”. Phương thức bean factory là một phần composition configuration: container gọi nó theo registration, cung cấp `NoticeGateway` và quản lý object được trả về theo lifecycle hợp lệ. Mặt khác, một helper được tạo bên trong phương thức nhưng **không trả về hoặc đăng ký** chưa chắc trở thành managed bean.

**Lưu ý:** đây là minh họa cho các lựa chọn phổ biến. Cơ chế post-processing, lifecycle, proxy và ownership của object cụ thể phụ thuộc Spring version, bean scope và cấu hình. Không tự suy rằng container sẽ đóng mọi resource được tạo sâu bên trong factory.

## 6. Không chỉ field injection: proxy và callback cũng bị ảnh hưởng

Lỗi tạo instance ngoài container có thể tinh vi hơn `NullPointerException`.

| Cơ chế | Nếu object được tạo trực tiếp ngoài container | Điều cần xác minh |
| --- | --- | --- |
| **Constructor injection thuần Java** | **Vẫn hoạt động** nếu caller truyền đầy đủ đối số | Có constructor nào cho phép tạo object thiếu dependency không? |
| **Field/setter injection do framework điều phối** | Thông thường **không chạy tự động** | Instance có đi qua đúng cơ chế injection không? |
| **Post-initialize callback** như `@PostConstruct` | Không tự được framework gọi | Callback thuộc lifecycle nào và object có được framework quản lý không? |
| **Destroy callback** như `@PreDestroy` | Không thể mong container gọi cho object nó không sở hữu | Ai có quyền và nghĩa vụ đóng resource? |
| **Proxy-based AOP** như transaction/cache/async | Annotation trên raw object không tự tạo proxy | Caller có nhận đúng proxied bean? Self-invocation có xảy ra? |
| **Scope application/request** | `new` trực tiếp tạo một instance ngoài chính sách cache/resolve của binding | Đúng scope, context và owner chưa? |
| **Configuration/qualifier resolution** | Không tự chọn bean theo qualifier để gán vào field | Tên/qualifier và cấu hình có khớp? |

Nếu object được tạo trực tiếp nhưng **constructor vẫn yêu cầu dependency** và caller cung cấp chúng, logic nghiệp vụ có thể chạy hoàn toàn đúng mà không cần container. Trong trường hợp này, chỉ các chức năng **cụ thể do framework cung cấp** mới là điều cần xem xét thêm.

### Một lời gọi qua bean không bảo đảm mọi lời gọi bên trong qua proxy

Giả sử Spring tạo `PaymentService` và bọc nó bằng proxy. `checkout()` gọi `this.charge()` trên target; `charge()` được cấu hình một advice. Với proxy-based AOP, lời gọi nội bộ đó có thể không đi qua proxy nên advice không chạy. Đây là **lỗi đường đi lời gọi**, không phải lỗi object không được đăng ký.

Không nên khắc phục mù bằng cách thêm `@Component` nhiều lần hoặc biến đối tượng thành Singleton pattern. Hãy vẽ caller → proxy → target và tìm chính xác lời gọi nào đi qua ranh giới interceptor.

## 7. Thực hành Java 17: một object "mồ côi" và một object được quản lý

Để hiểu cơ chế mà **không cần Spring**, ta viết một `MiniContainer` nhỏ. Container minh họa ba trách nhiệm:

1. **Tạo một `LegacyReminderService`** từ constructor không tham số.
2. **Tiêm `NoticeGateway` và gọi callback khởi tạo** trước khi trả service cho consumer.
3. **Đóng service khi container kết thúc**, còn object bên ngoài container không tự nhận callback này.

Ta cũng tạo `ExplicitReminderService` dùng **constructor injection tường minh**. Class này hoạt động đúng khi được `new` ở composition root và có thể kiểm thử với fake; nó không cần DI container. Đây là đối chứng quan trọng giúp tránh quan niệm “DI = cấm `new`”.

### Mã hoàn chỉnh

Lưu toàn bộ vào `Main.java`:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

record Notice(String customerId, String message) {
    Notice {
        Objects.requireNonNull(customerId, "customerId");
        Objects.requireNonNull(message, "message");
        if (customerId.isBlank()) {
            throw new IllegalArgumentException("Blank customerId");
        }
    }
}

@FunctionalInterface
interface NoticeGateway {
    void deliver(Notice notice);
}

// Fake gateway: ghi nhận kết quả, không gọi network thật.
final class RecordingNoticeGateway implements NoticeGateway {
    private final List<Notice> notices = new ArrayList<>();

    @Override
    public void deliver(Notice notice) {
        notices.add(Objects.requireNonNull(notice, "notice"));
    }

    List<Notice> delivered() {
        return List.copyOf(notices);
    }
}

// Mô phỏng lớp cũ dùng setter/field injection và lifecycle hook.
final class LegacyReminderService implements AutoCloseable {
    private NoticeGateway gateway;
    private boolean started;
    private boolean closed;

    // "Container" gọi phương thức này khi lắp ghép.
    void injectGateway(NoticeGateway gateway) {
        if (this.gateway != null) {
            throw new IllegalStateException("Gateway already injected");
        }
        this.gateway = Objects.requireNonNull(gateway, "gateway");
    }

    // "Container" gọi sau khi inject xong.
    void initialize() {
        if (gateway == null) {
            throw new IllegalStateException("Missing gateway injection");
        }
        if (closed) {
            throw new IllegalStateException("Service already closed");
        }
        started = true;
    }

    void remind(String customerId) {
        if (gateway == null) {
            throw new IllegalStateException("Missing injected gateway");
        }
        if (!started || closed) {
            throw new IllegalStateException("Service is not active");
        }
        gateway.deliver(new Notice(customerId, "payment-due"));
    }

    boolean isStarted() {
        return started && !closed;
    }

    @Override
    public void close() {
        if (!closed) {
            closed = true;
            started = false;
        }
    }
}

// Một container học tập tối giản: tạo, tiêm, init và close.
final class MiniContainer implements AutoCloseable {
    private final NoticeGateway gateway;
    private LegacyReminderService singleton;
    private boolean closed;

    MiniContainer(NoticeGateway gateway) {
        this.gateway = Objects.requireNonNull(gateway, "gateway");
    }

    LegacyReminderService reminder() {
        if (closed) {
            throw new IllegalStateException("Container already closed");
        }
        if (singleton == null) {
            LegacyReminderService created = new LegacyReminderService();
            created.injectGateway(gateway);
            created.initialize();
            singleton = created;
        }
        return singleton;
    }

    @Override
    public void close() {
        if (!closed) {
            closed = true;
            if (singleton != null) {
                singleton.close();
            }
        }
    }
}

// Cách mới: dependency bắt buộc được thể hiện ở constructor.
final class ExplicitReminderService {
    private final NoticeGateway gateway;
    private final Clock clock;

    ExplicitReminderService(NoticeGateway gateway, Clock clock) {
        this.gateway = Objects.requireNonNull(gateway, "gateway");
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    void remind(String customerId) {
        Instant now = Instant.now(clock);
        gateway.deliver(new Notice(customerId, "payment-due@" + now));
    }
}

public class Main {
    public static void main(String[] args) {
        RecordingNoticeGateway gateway = new RecordingNoticeGateway();

        // A. Tạo trực tiếp một service cũ: không có injection.
        LegacyReminderService orphan = new LegacyReminderService();
        check(!orphan.isStarted(),
                "Object tạo trực tiếp chưa được initialize");
        expectIllegalState(
                () -> orphan.remind("C-0"),
                "Object tạo trực tiếp phải báo thiếu gateway");

        // B. Container tạo, inject, initialize và quản lý vòng đời.
        LegacyReminderService managed;
        try (MiniContainer container = new MiniContainer(gateway)) {
            managed = container.reminder();
            check(managed == container.reminder(),
                    "Cùng container trả cùng managed instance");
            check(managed != orphan,
                    "Object tạo trực tiếp khác instance trong container");
            check(managed.isStarted(),
                    "Managed instance đã được khởi tạo");

            managed.remind("C-1");
            check(gateway.delivered().equals(
                    List.of(new Notice("C-1", "payment-due"))),
                    "Managed service sử dụng đúng gateway được inject");
        }

        check(!managed.isStarted(),
                "Đóng container phải kết thúc managed service");
        expectIllegalState(
                () -> managed.remind("C-2"),
                "Không dùng lại bean đã kết thúc vòng đời");

        // C. Manual DI đúng: vẫn new, nhưng truyền đủ dependency.
        RecordingNoticeGateway directGateway =
                new RecordingNoticeGateway();
        Clock clock = Clock.fixed(
                Instant.parse("2026-06-01T09:00:00Z"),
                ZoneOffset.UTC);

        ExplicitReminderService direct =
                new ExplicitReminderService(directGateway, clock);
        direct.remind("C-3");

        check(directGateway.delivered().equals(List.of(
                new Notice("C-3",
                        "payment-due@2026-06-01T09:00:00Z"))),
                "Constructor injection chạy không cần container");

        // D. Thiếu dependency: fail fast ngay khi tạo object.
        boolean nullRejected = false;
        try {
            new ExplicitReminderService(null, clock);
        } catch (NullPointerException expected) {
            nullRejected = true;
        }
        check(nullRejected,
                "Constructor phải chặn dependency bắt buộc bị null");

        System.out.println("PASS");
    }

    private static void expectIllegalState(
            Runnable action, String message) {
        boolean failed = false;
        try {
            action.run();
        } catch (IllegalStateException expected) {
            failed = true;
        }
        check(failed, message);
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 Main.java
java Main
~~~

Kết quả mong đợi:

~~~text
PASS
~~~

### Từng assertion bảo vệ điều gì?

| Kiểm tra | Điều được chứng minh |
| --- | --- |
| `new LegacyReminderService()` không sẵn sàng | Không có quá trình inject/init tự động từ JVM |
| `orphan.remind(...)` báo lỗi | Dependency cần được gán trước khi service hoạt động |
| `container.reminder() == container.reminder()` | MiniContainer mô phỏng một binding singleton được tái sử dụng |
| `managed != orphan` | Managed object và object được tạo trực tiếp **khác identity** |
| Gateway giả nhận thông báo | Instance do container cấu hình sử dụng dependency đã tiêm |
| Đóng container làm `managed` ngừng hoạt động | Lifecycle cleanup áp dụng cho object mà container sở hữu |
| `new ExplicitReminderService(gateway, clock)` chạy đúng | Manual DI qua constructor **không cần container** |
| Constructor từ chối `null` | Dependency bắt buộc được kiểm tra lúc khởi tạo thay vì lỗi muộn |

**Phạm vi mô phỏng:** `MiniContainer` không phải DI container thực sự. Nó không hỗ trợ package scanning, resolution đồ thị tự động, proxy/AOP, circular dependency, request scope, thread safety hoặc callback chuẩn của một framework. Mục đích duy nhất là cho thấy **instance được quản lý khác instance cùng class do caller tạo bên ngoài**. Không dùng mã này để thay framework trong production.

## 8. Sửa lỗi theo hướng kiến trúc: ba lựa chọn chính

### Lựa chọn A — Constructor injection tại composition root

Đây là lựa chọn mặc định dễ hiểu khi có thể sửa thiết kế:

~~~java
// Java thuần: root chọn adapter và cung cấp dependency.
NoticeGateway gateway = new EmailNoticeGateway(/* cấu hình */);
Clock clock = Clock.systemUTC();

ExplicitReminderService reminders =
        new ExplicitReminderService(gateway, clock);
~~~

Snippet này là minh họa, `EmailNoticeGateway` là adapter giả định chưa định nghĩa trong `Main.java`. Ý tưởng là **root tự chọn adapter**, còn service chỉ biết interface `NoticeGateway` và `Clock`.

Lợi ích: dependency hiển thị tại constructor, dễ dùng fake, kiểm tra thiếu dependency sớm, không phụ thuộc framework. Đánh đổi: composition root phải lắp object graph và quản lý resource; ứng dụng lớn có thể dùng container để tự động hóa.

### Lựa chọn B — Consumer nhận managed bean từ container

Nếu project đã dùng container và cần lifecycle/proxy của nó, hãy để **container tạo/configure service** và inject service đó vào consumer, không để consumer tự `new`.

~~~java
// Spring-specific: đúng khi consumer cũng do Spring quản lý.
@Service
class CheckoutFacade {
    private final ReminderService reminders;

    CheckoutFacade(ReminderService reminders) {
        this.reminders = reminders;
    }
}
~~~

Ngay cả trong ví dụ Spring này, cần bảo đảm `ReminderService` được đăng ký đúng, không có xung đột binding, các profile/qualifier phù hợp và consumer nhận **managed reference** chứ không phải raw target.

### Lựa chọn C — Typed factory hoặc provider khi cần object mới mỗi lần

Một số object cần được tạo theo request/tác vụ, không thể dùng một singleton được inject sẵn. Khi đó hãy **inject một factory có kiểu cụ thể**, thay vì truyền container tổng quát vào domain:

~~~java
interface JobSessionFactory {
    JobSession open();
}

interface JobSession extends AutoCloseable {
    void runJob(String id);

    @Override
    void close();
}

final class JobService {
    private final JobSessionFactory sessions;

    JobService(JobSessionFactory sessions) {
        this.sessions = java.util.Objects.requireNonNull(sessions);
    }

    void execute(String id) {
        try (JobSession session = sessions.open()) {
            session.runJob(id);
        }
    }
}
~~~

Trong ví dụ, hợp đồng `open()` nên nêu rõ nó trả **session mới thuộc quyền sở hữu caller** và caller phải đóng. Nếu provider trả một bean được container quản lý theo scope, trách nhiệm cleanup có thể khác. Không suy lifecycle chỉ từ từ “factory” hoặc “provider”.

### Trường hợp đặc biệt: inject vào object do bên ngoài tạo

Một số framework cung cấp API **tiêm phụ thuộc vào object có sẵn** hoặc hỗ trợ integration với thư viện tạo instance bên ngoài. Đây là giải pháp chuyên biệt cần đọc tài liệu và hiểu sự khác nhau giữa **inject property**, **gọi initialization**, **tạo proxy**, **đăng ký ownership** và **teardown**. Không được giả định một lệnh “autowire existing object” sẽ biến object đó thành managed bean đầy đủ.

Nếu có thể thay đổi thiết kế, **constructor injection hoặc typed factory tại ranh giới tích hợp** thường minh bạch hơn việc vá một instance đã tồn tại.

## 9. Các cách sửa sai khiến lỗi khó hơn

### 9.1. Thêm annotation vào class rồi vẫn giữ new

~~~java
@Component
class ReminderService { /* ... */ }

// Ở nơi khác:
ReminderService x = new ReminderService();
~~~

Annotation có thể đăng ký **một bean do container quản lý**, nhưng không biến mọi `new ReminderService()` thành lời gọi tới bean đó. Đây là nguồn tạo **hai object khác identity** dễ bị nhầm lẫn.

### 9.2. Chuyển dependency sang static field

~~~java
// Chống mẫu: xóa lỗi null của instance bằng global state.
static NoticeGateway globalGateway;
~~~

Trường static làm dependency trở thành trạng thái toàn cục, gây khó test, khó chạy nhiều cấu hình và có nguy cơ chia sẻ sai dữ liệu. Nó không giải quyết đúng nguyên nhân là **object được tạo ngoài vòng lắp ghép**.

### 9.3. Tự lấy application context trong business method

~~~java
// Pseudocode: service tự tra cứu từ container toàn cục.
NoticeGateway gateway =
        GlobalApplicationContext.getBean(NoticeGateway.class);
~~~

Cách này gần **Service Locator**: dependency bị giấu trong implementation, tăng coupling với framework và làm unit test khó cô lập. Container có nơi sử dụng hợp lý tại **composition root**; không cần truyền quyền tra cứu toàn cục cho mọi service.

### 9.4. Gọi thủ công callback nhưng quên inject và owner

~~~java
LegacyReminderService service = new LegacyReminderService();
service.initialize(); // Sẽ báo thiếu gateway trong ví dụ Java 17.
~~~

Một callback không phải cơ chế diệu kỳ tạo dependency. Nếu tự lắp ghép thì phải **truyền dependency đầy đủ**, xác định lifecycle và đóng resource theo owner. Gọi callback thủ công cũng không tự tạo proxy, scope hoặc managed registration.

### 9.5. Thay null bằng No-Op để ứng dụng không lỗi

~~~java
// Chống mẫu nếu gửi thông báo là yêu cầu bắt buộc.
if (gateway == null) {
    gateway = notice -> { };
}
~~~

Điều này che lỗi wiring và có thể khiến hệ thống **mất thông báo quan trọng**. No-Op chỉ phù hợp khi nghiệp vụ cho phép một chế độ không gửi, được chọn rõ ràng tại configuration/composition root, không phải fallback bí mật cho một dependency thiếu.

### 9.6. Tạo thêm container mới trong mỗi request

Để “lấy được bean”, một số mã vô tình khởi tạo lại application context cho mỗi tác vụ. Điều đó không chỉ tốn kém mà còn có thể tạo singleton khác, pool khác và lifecycle khác. Hãy dùng **context được quản lý ở điểm khởi động** hoặc scope con đúng quy tắc của framework.

## 10. Scope, proxy và lifecycle sau khi sửa injection

Sửa lỗi `null` mới là phần đầu. Cần kiểm tra object graph sau khi đã thay đường tạo.

### Scope đúng chưa?

Một bean singleton thường được tái sử dụng theo registration/context. Nếu service giữ state của request hoặc giao dịch, không nên biến nó thành singleton chỉ vì container có thể tạo singleton. Thay vì giữ `RequestContext` trong field của singleton, hãy truyền data theo method hoặc dùng provider theo request scope khi framework hỗ trợ.

### Lời gọi đã đi qua proxy chưa?

Nếu có `@Transactional`, `@Async`, `@Cacheable` hoặc advice khác, test phải sử dụng **reference mà container cung cấp** và kiểm tra đường gọi qua proxy. Đừng giả định annotation tự hoạt động trên target được tạo thủ công. Đồng thời phân biệt self-invocation với unmanaged instance.

### Ai đóng tài nguyên?

Nếu container sở hữu một HTTP client/pool và cung cấp cho nhiều service, consumer **không được tự ý đóng client sau mỗi request**. Nếu một factory tạo session caller-owned mỗi lần, session cần được đóng theo thao tác bằng `try-with-resources` hoặc cơ chế tương ứng.

**Đối tượng mới không có lifecycle của container** không đồng nghĩa “mọi object được `new` đều bị rò rỉ”. Với manual DI hợp lệ, root hoặc caller có thể chủ động đóng resource. Câu hỏi đúng là: **owner đã được xác định và có cleanup bảo đảm cả khi xảy ra lỗi hay chưa?**

### Khởi tạo dở dang thì sao?

Nếu factory đã mở tài nguyên A rồi không tạo được B, factory phải dọn những resource nó còn sở hữu trước khi ném lỗi. Consumer chưa nhận B thì không thể đóng phần tài nguyên ẩn nằm trong quá trình khởi tạo. Một DI container có thể hỗ trợ cleanup trong một số giai đoạn, nhưng không thể tự biết mọi resource phát sinh bên ngoài phạm vi quản lý của nó.

## 11. Chiến lược kiểm thử sau khi sửa

Không nên chỉ viết một assertion “`gateway != null`”. Mục tiêu thực là chứng minh **lắp ghép đúng, nghiệp vụ đúng và lifecycle đúng**.

| Tầng test | Cách thực hiện | Điều kiểm chứng |
| --- | --- | --- |
| **Unit test Java thuần** | `new ExplicitReminderService(fakeGateway, fixedClock)` | Service dùng đúng dependency và trả side effect dự kiến |
| **Wiring test** | Tạo composition root hoặc context thật | Consumer nhận đúng instance; dependency bắt buộc được resolve |
| **Lifecycle test** | Đóng context/scope | Callback/cleanup đúng với owner và resource đã tạo |
| **Proxy integration test** | Gọi qua bean từ container | Advice/transaction/cache/async được áp dụng ở ranh giới mong muốn |
| **Negative test** | Cố tình thiếu binding hoặc cấu hình sai | Hệ thống phát hiện sớm, không âm thầm dùng No-Op |
| **Scope test** | Tạo hai request/context | Trạng thái không rò rỉ và đúng shared/reference identity |

Ví dụ, một test khởi động Spring context rồi dùng `applicationContext.getBean(ReminderService.class)` có thể chứng minh **bean được tạo và injection thành công**. Nhưng nó **không chứng minh** controller đang sử dụng bean đó nếu controller viết `new ReminderService()`. Do đó cần test luồng **qua đúng consumer và entrypoint thực tế**.

Khi service có nhiều dependency, một fake ít trạng thái và các assertion về behavior có ích hơn việc verify mọi lời gọi nội bộ. Với những side effect quan trọng như thanh toán, audit hoặc gửi notification, có thể kiểm tra số lần gọi và nội dung qua recorder vì đó là **hợp đồng nghiệp vụ**.

## 12. Checklist chẩn đoán trong review hoặc khi xử lý incident

- **[ ] Đã xác định exact instance gây lỗi, không chỉ dựa vào việc bean cùng class tồn tại trong container?**
- **[ ] Có đường `new`, factory, reflection, serializer hoặc test fixture tạo instance ngoài container không?**
- **[ ] Consumer có nhận service qua constructor, root hoặc bean registration đúng không?**
- **[ ] Có nhiều application context, scope, qualifier, profile hoặc bean definition ảnh hưởng tới lựa chọn instance không?**
- **[ ] Nếu có annotation DI, instance thực sự trải qua bước inject và callback cần thiết chưa?**
- **[ ] Nếu có AOP, caller có đi qua proxy và method có thuộc pointcut không?**
- **[ ] Có self-invocation trên target làm advice bị bỏ qua không?**
- **[ ] Constructor đã công khai dependency bắt buộc và chặn null thay vì cho lỗi muộn chưa?**
- **[ ] Khi dùng factory/provider, scope và ownership của sản phẩm đã rõ chưa?**
- **[ ] Đã có test qua đúng consumer để xác minh behavior, không chỉ test bean riêng lẻ?**
- **[ ] Resource được đóng bởi đúng owner khi thành công, lỗi hoặc shutdown chưa?**
- **[ ] Có loại bỏ workaround global static/Service Locator hoặc fallback No-Op thiếu chủ đích không?**

Khi báo cáo một lỗi DI, nên ghi **đường đi reference** (*ai tạo → ai inject → ai gọi → ai đóng*) cùng bằng chứng test. Thông tin đó giúp người khác phân biệt lỗi injection, lỗi bean registration, lỗi proxy và lỗi scope — những nguyên nhân có triệu chứng gần giống nhau nhưng cách sửa khác nhau.

## 13. Bài tập thực hành

**Bài 1 — Tìm instance mồ côi.** Một Spring controller có constructor nhận `ReminderService`, nhưng trong một method vẫn dùng `new ReminderService()`. Hãy vẽ hai đường tham chiếu, chỉ ra object nào là managed và sửa để dùng đúng instance đã inject.

**Bài 2 — Constructor injection.** Từ `LegacyReminderService` ở ví dụ, hãy bỏ `injectGateway` và `initialize` nếu nghiệp vụ không cần init riêng; chuyển `NoticeGateway` thành tham số constructor bắt buộc và cập nhật `MiniContainer`. Kiểm thử missing dependency bị chặn khi tạo object.

**Bài 3 — @Bean và new.** So sánh `return new ReminderService(gateway)` bên trong `@Bean` factory được container gọi với `new ReminderService(gateway)` trong business method. Trường hợp nào object được container quản lý? Trường hợp nào vẫn có thể dùng manual DI nhưng không có lifecycle/proxy của container?

**Bài 4 — Proxy hay unmanaged?** Một method `@Transactional` không tạo transaction. Lập sơ đồ chẩn đoán phân biệt: service bị `new` trực tiếp; service là bean managed nhưng có self-invocation; transaction manager/pointcut không được cấu hình phù hợp.

**Bài 5 — Scope và ownership.** Composition root tạo pool dùng chung; service mở session theo từng transaction. Hãy xác định bên sở hữu pool và bên đóng session. Vì sao không nên tiêm một session duy nhất vào singleton service?

**Bài 6 — Wiring test.** Viết một test nhỏ tạo managed instance qua `MiniContainer`, xác minh cùng binding trả cùng reference, service được init, callback close chạy sau khi context đóng. Sau đó tạo `new LegacyReminderService()` để xác minh nó không tự nhận được những bước ấy.

## 14. Tự kiểm tra mức độ hiểu

**Câu 1.** Một class được đánh dấu `@Component` có nghĩa mọi `new ClassName()` đều được Spring inject không? **Không.** Annotation/registration không biến mọi lần tạo object bằng JVM thành managed bean.

**Câu 2.** `new ExplicitReminderService(gateway, clock)` tại composition root có phải lỗi DI không? **Không.** Đây là manual constructor injection hợp lệ nếu caller truyền đủ dependency và quản lý lifecycle khi cần.

**Câu 3.** Vì sao chỉ thấy `@Autowired` bằng `null` chưa thể kết luận object được tạo trực tiếp? **Vì** còn những nguyên nhân khác liên quan registration, cấu hình, thời điểm khởi tạo, qualifier hoặc đường sử dụng sai instance.

**Câu 4.** Một phương thức `@Bean` trả về object tạo bằng `new` có mặc nhiên là unmanaged không? **Không.** Với container gọi factory và đăng ký instance trả về, object đó được quản lý theo cơ chế bean registration.

**Câu 5.** Vì sao một bean managed vẫn có thể không chạy `@Transactional`? **Có thể** do lời gọi không đi qua proxy, self-invocation hoặc cấu hình AOP/transaction không phù hợp.

**Câu 6.** Nếu object tạo trực tiếp có đầy đủ constructor dependency, container có tự gọi `@PreDestroy` cho nó không? **Không thể mong đợi.** Lifecycle thuộc owner/cơ chế quản lý; manual DI cần cleanup do caller/root điều phối.

**Câu 7.** Cách sửa mặc định phù hợp nhất khi business service tự tạo một cộng tác viên cần DI là gì? **Đưa dependency vào constructor**, để composition root hoặc container quyết định tạo/tiêm và cung cấp cho consumer.

## Ghi nhớ

- **Annotation của DI framework không tự được JVM thực thi** cho mọi object tạo bằng `new`. Đối tượng trực tiếp có thể bỏ qua field/setter injection, lifecycle callback và proxy/interceptor của container.
- **Chẩn đoán bằng reference thật:** lần theo nơi tạo, nơi truyền và nơi gọi; một bean cùng class tồn tại trong container không bảo đảm consumer đang dùng nó.
- **Đừng cấm mọi lệnh `new`.** Manual DI với constructor injection đầy đủ ở composition root là cách học và thiết kế hợp lệ bằng Java thuần.
- **Sửa đúng ranh giới:** dùng managed bean khi cần framework, constructor injection cho dependency bắt buộc, typed factory/provider khi cần tạo theo scope; tránh global registry và Service Locator trong nghiệp vụ.
- **Kiểm tra tiếp scope, proxy và ownership** sau khi hết lỗi `null`. Test behavior của consumer, wiring của container và cleanup tài nguyên để đảm bảo hệ thống thực sự đúng, không chỉ khởi động được.
