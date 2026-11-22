# Reflection, sinh mã và các đánh đổi trong cơ chế lắp ghép

Khi học **Dependency Injection (DI)** bằng Java thuần, ta thường tạo cộng tác viên rồi truyền trực tiếp vào constructor:

```java
EventStore store = new InMemoryEventStore();
AuditService service = new AuditService(store, clock);
```

Khi object graph mở rộng, một **DI container** có thể thay phần mã lắp ghép thủ công: tìm constructor, xác định dependency nào tương ứng với tham số nào, tạo các instance và quản lý scope. Có nhiều cách triển khai cơ chế này. Hai hướng nổi bật là **dùng reflection tại runtime** và **sinh mã lắp ghép trước lúc chạy** (*code generation*, thường ở giai đoạn compile/build hoặc AOT).

Điều cần hiểu là: **cơ chế lắp ghép không làm thay đổi bản chất của DI**. Lớp nghiệp vụ vẫn nên công khai collaborator qua constructor; composition root vẫn quyết định implementation và vòng đời; dữ liệu của mỗi lần gọi vẫn đi qua API nghiệp vụ. Reflection hay sinh mã là các cách thực hiện phần *composition*, mỗi cách có lợi ích và chi phí riêng.

Bài thuộc chương **Bộ chứa DI** của module Dependency Injection, sử dụng ví dụ Java 17 có thể đọc và chạy không cần framework. Trước khi dùng một container thực tế, ta cần hiểu nó có thể kiểm tra điều gì, có thể thất bại ở đâu và vì sao quyết định scope không thể giao phó hoàn toàn cho một kỹ thuật tạo đối tượng.

## 1. Container cần thực hiện những việc gì?

Giả sử `AuditService` nhận một `EventStore` và một `Clock`:

```java
final class AuditService {
    private final EventStore store;
    private final Clock clock;

    AuditService(EventStore store, Clock clock) {
        this.store = Objects.requireNonNull(store);
        this.clock = Objects.requireNonNull(clock);
    }
}
```

Để tạo `AuditService`, một cơ chế lắp ghép phải trả lời ít nhất bốn câu hỏi:

1. **Phụ thuộc nào được yêu cầu?** Constructor cần `EventStore` và `Clock`.
2. **Implementation nào được chọn?** `EventStore` là interface, có thể dùng `InMemoryEventStore`, `JdbcEventStore` hoặc fake khi kiểm thử.
3. **Instance nào được cấp?** Dùng chung một `EventStore`, tạo mới mỗi lần resolve hay cấp theo request/transaction?
4. **Ai sở hữu và đóng tài nguyên?** Nếu implementation mở file, pool hoặc client, cần biết khi nào tài nguyên được giải phóng.

Phần quan hệ giữa đối tượng có thể biểu diễn bằng đồ thị:

```text
                 Composition root
                       │
             chọn implementation
                       │
                       ▼
         ┌────────────────────────┐
         │       AuditService     │
         └──────────┬─────────────┘
                    │ constructor
             ┌──────┴────────┐
             ▼               ▼
         EventStore         Clock
             │
             ▼
      InMemoryEventStore
```

Tự viết `new` là một cách lắp graph. DI container dùng cấu hình và một cơ chế phân giải để tạo graph tương tự. Có container kết hợp nhiều kỹ thuật: dùng reflection cho một số thành phần, mã sinh cho thành phần khác, hoặc sử dụng metadata sẵn có và factory do người dùng cung cấp.

## 2. Reflection là gì trong cơ chế lắp ghép?

**Reflection** cho phép chương trình Java quan sát kiểu và thành viên của lớp khi đang chạy: xem constructor, tham số, annotation và gọi constructor thông qua API như `Class`, `Constructor` hoặc `Method`.

Ví dụ cốt lõi:

```java
Constructor<AuditService> constructor =
        AuditService.class.getConstructor(EventStore.class, Clock.class);

AuditService service = constructor.newInstance(store, clock);
```

Đoạn mã giả định `AuditService` có constructor `public` đúng chữ ký; cần import `java.lang.reflect.Constructor` và xử lý các checked exception của reflection. Nếu constructor không công khai, cách truy cập sẽ chịu quy tắc Java access control và module system.

Một bộ phân giải dùng reflection thường đi theo luồng:

```text
                     Runtime
                        │
              Yêu cầu AuditService
                        │
                        ▼
             Đọc metadata constructor
                        │
                        ▼
           Cần EventStore và Clock?
                        │
             ┌──────────┴──────────┐
             ▼                     ▼
       Tìm binding            Tìm instance
      EventStore → ...         Clock đã đăng ký
             │                     │
             └──────────┬──────────┘
                        ▼
            Constructor.newInstance(...)
                        │
                        ▼
                AuditService hợp lệ
```

Nếu `AuditService` cần thêm collaborator, resolver có thể quan sát tham số constructor mới mà **không sửa mã duyệt graph**. Đó là một lý do reflection thuận tiện cho container tổng quát.

Tuy nhiên, reflection chỉ nói cho ta **class yêu cầu kiểu nào**. Nó không tự biết chọn implementation đúng, scope phù hợp, qualifier nào ưu tiên hoặc ai đóng tài nguyên. Những quyết định này vẫn cần registration, quy ước, annotation và logic của container.

### Reflection không nhất thiết xuất hiện ở mọi lời gọi nghiệp vụ

Một container có thể dùng reflection **khi tạo object graph**, sau đó service gọi collaborator qua interface Java bình thường:

```java
AuditService service = containerResolveAuditService();

// Sau khi lắp xong, đây là lời gọi Java thông thường.
service.record("order-created");
```

Vì vậy không nên suy luận rằng “container dùng reflection thì mọi lời gọi của ứng dụng đều chậm do reflection”. Chi phí metadata/constructor có thể nằm chủ yếu ở lúc khởi động hoặc lần phân giải đầu tiên; có container cache metadata hoặc dùng các kỹ thuật tối ưu khác. Hiệu năng thực tế phụ thuộc implementation, tần suất tạo đối tượng, scope và khối lượng nghiệp vụ.

## 3. Sinh mã lắp ghép là gì?

Với **code generation**, một công cụ đọc mô tả dependency **trước khi ứng dụng chạy**, rồi tạo ra mã nguồn hoặc bytecode biết gọi trực tiếp các constructor cần thiết.

Ví dụ, từ graph đã xác định, công cụ có thể tạo mã tương đương:

```java
final class GeneratedApplicationGraph {
    static AuditService createAuditService(Clock clock) {
        EventStore store = new InMemoryEventStore();
        return new AuditService(store, clock);
    }
}
```

Đây là **mẫu mã có thể được sinh**, không phải ví dụ về một annotation processor cụ thể. `AuditService` vẫn dùng constructor injection như trước; chỉ khác là quá trình chọn và gọi constructor đã được diễn đạt bằng câu lệnh Java tường minh.

Sơ đồ hai thời điểm:

```text
Sinh mã trước runtime:

   Java source + metadata/registration
                  │
                  ▼
      Processor / source generator
                  │
                  ▼
      GeneratedApplicationGraph.java
                  │
                  ▼
           Java compiler
                  │
                  ▼
         Bytecode ứng dụng
                  │
               Runtime
                  │
                  ▼
     Gọi new và constructor trực tiếp
                  │
                  ▼
             Object graph
```

Trong hệ sinh thái Java, việc sinh mã có thể được thực hiện qua **annotation processing** trong quá trình biên dịch, một bước build sinh source, sinh bytecode, hoặc một công đoạn **Ahead-of-Time (AOT)** có thêm phân tích ứng dụng. Những kỹ thuật này không hoàn toàn đồng nghĩa:

- **Annotation processor:** công cụ đọc annotation và cấu trúc mã nguồn do compiler cung cấp để tạo source/metadata mới.
- **Source/bytecode generator:** tạo mã lắp ghép dựa trên thông tin đã biết; không bắt buộc dùng annotation.
- **AOT processing:** phân tích và chuẩn bị một phần công việc trước runtime; có thể bao gồm code generation, metadata tối ưu hoặc cấu hình cho môi trường triển khai cụ thể.
- **Runtime reflection:** vẫn có thể tồn tại ở các phần khác của cùng ứng dụng dù container dùng mã sinh cho graph.

Vì thế, cặp đối lập chính trong bài là **“phát hiện và lắp phụ thuộc chủ yếu khi chạy”** so với **“chuẩn bị nhiều quyết định lắp ghép trong build”**, thay vì coi mọi framework chỉ thuộc đúng một trong hai nhóm.

## 4. Ví dụ Java 17: cùng một graph, hai cơ chế lắp ghép

Ví dụ sau chủ ý viết một resolver reflection **rất nhỏ** rồi đối chiếu với một factory gọi constructor trực tiếp. Nó minh họa cơ chế, không nhằm xây DI container dùng production.

Lưu toàn bộ vào `WiringMechanismsDemo.java`:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Modifier;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Map;
import java.util.Objects;

public final class WiringMechanismsDemo {

    // Contract của cộng tác viên.
    interface EventStore {
        String save(String event);
    }

    static final class InMemoryEventStore implements EventStore {
        public InMemoryEventStore() {}

        @Override
        public String save(String event) {
            return "stored(" + event + ")";
        }
    }

    // Consumer chỉ biết hợp đồng, không biết cách lắp ghép.
    static final class AuditService {
        private final EventStore store;
        private final Clock clock;

        public AuditService(EventStore store, Clock clock) {
            this.store = Objects.requireNonNull(store, "store");
            this.clock = Objects.requireNonNull(clock, "clock");
        }

        String record(String message) {
            Objects.requireNonNull(message, "message");
            return store.save(clock.instant() + "|" + message);
        }
    }

    // Resolver minh họa: một public constructor cho mỗi class.
    static final class ReflectiveResolver {
        private final Map<Class<?>, Class<?>> bindings;
        private final Map<Class<?>, Object> suppliedInstances;

        ReflectiveResolver(
                Map<Class<?>, Class<?>> bindings,
                Map<Class<?>, Object> suppliedInstances) {
            this.bindings = Map.copyOf(
                    Objects.requireNonNull(bindings, "bindings"));
            this.suppliedInstances = Map.copyOf(
                    Objects.requireNonNull(
                        suppliedInstances, "suppliedInstances"));
        }

        <T> T resolve(Class<T> requestedType) {
            Objects.requireNonNull(requestedType, "requestedType");
            return requestedType.cast(
                    create(requestedType, new ArrayDeque<>()));
        }

        private Object create(
                Class<?> requestedType, Deque<Class<?>> path) {
            Object supplied = suppliedInstances.get(requestedType);
            if (supplied != null) {
                return supplied;
            }

            Class<?> implementation =
                    bindings.getOrDefault(requestedType, requestedType);

            if (!requestedType.isAssignableFrom(implementation)) {
                throw new IllegalStateException(
                    "Binding does not implement "
                        + requestedType.getName());
            }
            if (implementation.isInterface()
                    || Modifier.isAbstract(
                        implementation.getModifiers())) {
                throw new IllegalStateException(
                    "No concrete binding for " + requestedType.getName());
            }
            if (path.contains(implementation)) {
                throw new IllegalStateException(
                    "Circular dependency: " + path
                        + " -> " + implementation.getName());
            }

            path.addLast(implementation);
            try {
                Constructor<?>[] constructors =
                        implementation.getConstructors();

                if (constructors.length != 1) {
                    throw new IllegalStateException(
                        "Expected exactly one public constructor: "
                            + implementation.getName());
                }

                Constructor<?> constructor = constructors[0];
                Class<?>[] types = constructor.getParameterTypes();
                Object[] dependencies = new Object[types.length];

                for (int i = 0; i < types.length; i++) {
                    dependencies[i] = create(types[i], path);
                }

                return constructor.newInstance(dependencies);

            } catch (InvocationTargetException failure) {
                throw new IllegalStateException(
                    "Constructor failed for "
                        + implementation.getName(),
                    failure.getCause());
            } catch (ReflectiveOperationException failure) {
                throw new IllegalStateException(
                    "Cannot construct " + implementation.getName(),
                    failure);
            } finally {
                path.removeLast();
            }
        }
    }

    // Factory viết tay mô phỏng dạng code mà generator có thể tạo.
    static final class GeneratedStyleGraph {
        static AuditService createAuditService(Clock clock) {
            EventStore store = new InMemoryEventStore();
            return new AuditService(store, clock);
        }
    }

    public static void main(String[] args) {
        Clock fixedClock = Clock.fixed(
            Instant.parse("2026-01-01T00:00:00Z"),
            ZoneOffset.UTC
        );

        ReflectiveResolver resolver = new ReflectiveResolver(
            Map.of(EventStore.class, InMemoryEventStore.class),
            Map.of(Clock.class, fixedClock)
        );

        AuditService reflection =
                resolver.resolve(AuditService.class);
        AuditService generatedStyle =
                GeneratedStyleGraph.createAuditService(fixedClock);

        System.out.println(
            "reflection=" + reflection.record("order-created"));
        System.out.println(
            "generated-style="
                + generatedStyle.record("order-created"));
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac WiringMechanismsDemo.java
java WiringMechanismsDemo
```

Kết quả dự kiến:

```text
reflection=stored(2026-01-01T00:00:00Z|order-created)
generated-style=stored(2026-01-01T00:00:00Z|order-created)
```

### Đọc nhánh reflection

`ReflectiveResolver.resolve(AuditService.class)` mở một lần phân giải graph. Nó đọc constructor public của `AuditService`, thấy hai tham số `EventStore` và `Clock`:

- Với `EventStore`, map `bindings` chỉ định `InMemoryEventStore`, nên resolver tiếp tục tìm constructor của lớp này và tạo instance.
- Với `Clock`, map `suppliedInstances` đã cung cấp một instance; resolver dùng lại instance đó.
- Sau khi có đủ đối số, resolver gọi `Constructor.newInstance(...)` để tạo `AuditService`.

Map `bindings` trả lời câu hỏi **“dùng implementation nào?”**. Map `suppliedInstances` trả lời một phần câu hỏi **“dùng instance có sẵn nào?”**. Việc chọn một `Clock` cố định còn giúp test có kết quả xác định, không phụ thuộc giờ hệ thống.

Để tránh đệ quy vô hạn khi có vòng constructor, resolver duy trì `path` riêng cho mỗi lần phân giải. Nếu A đang xây cần B rồi B lại cần A, resolver phát hiện type lặp trong đường đi và báo lỗi. Đây mới là kiểm tra chu trình đơn giản: container thực tế có thể cần xử lý provider, lazy dependency, qualifier và graph có nhiều registration.

### Đọc nhánh mã sinh

`GeneratedStyleGraph.createAuditService(fixedClock)` không cần suy ra constructor bằng reflection lúc chạy. Nó có sẵn đường lắp ghép:

```java
EventStore store = new InMemoryEventStore();
return new AuditService(store, clock);
```

Nếu ai đó đổi constructor của `AuditService` và không cập nhật factory, Java compiler có thể báo lỗi ngay tại lệnh `new AuditService(...)`. Trong một hệ thống sinh mã thật, bước generate phải chạy đúng quy trình build để factory được cập nhật.

Cả hai nhánh đều dùng **constructor injection**; thuật toán nghiệp vụ trong `AuditService.record(...)` không cần biết cơ chế wiring. Đây là lợi ích thiết kế quan trọng nhất của việc đặt ranh giới DI đúng chỗ.

### Những giới hạn có chủ ý của resolver minh họa

Resolver nhỏ ở trên **không** có đầy đủ tính năng của một DI container:

- Chỉ chấp nhận **đúng một constructor public** cho mỗi concrete class, không có quy tắc `@Inject` hay lựa chọn constructor phức tạp.
- Chỉ bind theo `Class<?>`; không hiểu qualifier, tên, generic type đầy đủ hoặc nhiều registration cho cùng interface.
- Mặc định tạo mới các đối tượng được resolve và không cache chúng; `suppliedInstances` chỉ cấp instance đăng ký sẵn. Đây **không phải** một bộ quản lý scope.
- Không triển khai lifecycle hook, tự động đóng tài nguyên, kiểm tra thread safety, circular proxy, interception hay transaction.
- Không hỗ trợ tùy ý constructor private; Java module system có thể hạn chế reflective access. Ví dụ dùng constructor public để tránh phụ thuộc vào việc mở quyền truy cập.
- Chưa phân biệt rõ các lỗi mang tính nghiệp vụ do constructor ném với chính sách lỗi của một container production; ví dụ bọc chúng để bổ sung ngữ cảnh.

Không nên đưa resolver này vào sản phẩm thực tế. Nó là công cụ học để hiểu **reflection thực hiện việc khám phá và gọi constructor ra sao**, rồi so sánh với việc biết trước graph trong mã được sinh.

## 5. Kiểm thử Java thuần: kết quả, lỗi binding và thời điểm phân giải

Lưu `WiringMechanismsCheck.java` bên cạnh `WiringMechanismsDemo.java`:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Map;

public final class WiringMechanismsCheck {
    public static void main(String[] args) {
        Clock clock = Clock.fixed(
            Instant.parse("2026-01-01T00:00:00Z"),
            ZoneOffset.UTC
        );

        var resolver = new WiringMechanismsDemo.ReflectiveResolver(
            Map.of(
                WiringMechanismsDemo.EventStore.class,
                WiringMechanismsDemo.InMemoryEventStore.class),
            Map.of(Clock.class, clock)
        );

        var reflective = resolver.resolve(
            WiringMechanismsDemo.AuditService.class);
        var generated =
            WiringMechanismsDemo.GeneratedStyleGraph
                .createAuditService(clock);

        String expected =
            "stored(2026-01-01T00:00:00Z|created)";

        if (!expected.equals(reflective.record("created"))
                || !expected.equals(generated.record("created"))) {
            throw new AssertionError(
                "The two compositions produced different behavior");
        }

        // Resolver ví dụ tạo một graph mới ở mỗi lần resolve.
        if (resolver.resolve(WiringMechanismsDemo.AuditService.class)
                == resolver.resolve(
                    WiringMechanismsDemo.AuditService.class)) {
            throw new AssertionError(
                "Expected a new service per resolution");
        }

        // Thiếu mapping cho EventStore: lỗi khi runtime resolve.
        var incomplete = new WiringMechanismsDemo.ReflectiveResolver(
            Map.of(), Map.of(Clock.class, clock)
        );

        boolean bindingFailed = false;
        try {
            incomplete.resolve(
                WiringMechanismsDemo.AuditService.class);
        } catch (IllegalStateException expectedFailure) {
            bindingFailed = expectedFailure.getMessage()
                .contains("No concrete binding");
        }

        if (!bindingFailed) {
            throw new AssertionError(
                "Expected an error for missing EventStore binding");
        }

        // Với constructor injection, test dùng fake trực tiếp.
        WiringMechanismsDemo.EventStore fake =
            event -> "fake:" + event;

        var service = new WiringMechanismsDemo.AuditService(
            fake, clock
        );

        if (!"fake:2026-01-01T00:00:00Z|created"
                .equals(service.record("created"))) {
            throw new AssertionError(
                "Service did not use the injected fake");
        }

        System.out.println("PASS");
    }
}
```

Chạy:

```bash
javac WiringMechanismsDemo.java WiringMechanismsCheck.java
java WiringMechanismsCheck
```

Kết quả dự kiến: `PASS`.

Bài kiểm tra minh họa ba điều: hai cơ chế wiring có thể cấp những collaborator **tương đương về hành vi**; resolver reflection có thể chỉ phát hiện thiếu binding **khi resolve**; và lớp nghiệp vụ vẫn có thể được kiểm thử bằng fake trực tiếp qua constructor, không cần chạy bất kỳ container nào.

Cũng cần nhớ: resolver ở ví dụ chọn chính sách **tạo mới** cho class không đăng ký sẵn. Việc hai lời gọi `resolve(AuditService.class)` trả về hai instance khác nhau là do **chính sách của resolver này**, không phải tính chất bắt buộc của reflection. Một container phản chiếu vẫn có thể cung cấp singleton, request scope hoặc transient; mã sinh cũng vậy.

## 6. Bảng so sánh reflection và sinh mã

| Khía cạnh | Chủ yếu dựa vào reflection runtime | Chủ yếu dựa vào mã sinh trước runtime |
|---|---|---|
| Cách tìm quan hệ phụ thuộc | Đọc metadata và constructor khi ứng dụng chạy hoặc khi resolve | Phân tích source/metadata tại build, chuẩn bị lệnh tạo graph |
| Khả năng thay đổi graph lúc chạy | Có thể linh hoạt hơn nếu cơ chế registry cho phép | Thường cần graph hoặc nhánh lựa chọn đã được dự liệu; vẫn có thể gọi factory động |
| Phát hiện thiếu binding | Có thể ở startup nếu container validate/eager create; có thể muộn nếu lazy | Có thể sớm ở compile/build khi thông tin đầy đủ; không bắt được mọi cấu hình runtime |
| Chi phí lúc build | Ít hoặc không có bước sinh mã riêng | Có thêm processor, mã sinh, bước build và khả năng phát sinh lỗi toolchain |
| Chi phí lúc startup | Có thể cần scan metadata, xác định constructor và xây graph | Có thể giảm công việc khám phá động; vẫn phải tạo instance và mở tài nguyên |
| Overhead khi resolve | Có thể có lookup/reflective construction; có thể cache hoặc tối ưu | Thường gọi factory/constructor trực tiếp; vẫn có scope lookup và điều kiện |
| Debugging | Có thể cần đọc trace phân giải và cấu hình container | Có thể xem generated source nhưng stack trace có lớp/hàm sinh ra |
| Dynamic plugin | Thuận lợi khi phải khám phá kiểu/annotation mới ở runtime | Cần thiết kế registry/điểm mở rộng phù hợp, có thể vẫn dùng reflection |
| Đóng gói native/AOT | Cần quan tâm metadata reflective access nếu có closed-world analysis | Thường thuận lợi hơn cho phân tích trước runtime, tùy stack |
| Scope và disposal | Do container và cấu hình quyết định | Cũng do container và cấu hình quyết định |

**Không kết luận “sinh mã luôn nhanh hơn” hoặc “reflection luôn chậm” nếu chưa đo**. Phần lớn thời gian của ứng dụng nghiệp vụ có thể nằm ở I/O, database, serialization hoặc thuật toán, không phải constructor. Chi phí tạo object graph chỉ nổi bật ở ứng dụng khởi động liên tục, khởi tạo nhiều bean hoặc resolve transient với tần suất rất cao.

Một container dùng reflection nhưng chỉ introspect một lần và cache metadata có thể hoạt động hiệu quả. Một container dùng generated factory nhưng tạo quá nhiều object hoặc mở kết nối lặp vẫn có thể chậm. Kết quả phụ thuộc **thiết kế graph và workload cụ thể**.

## 7. Thời điểm phát hiện lỗi: compile, build, startup hay request?

Một lợi ích được quảng bá cho code generation là **“phát hiện lỗi sớm”**. Điều đó đúng trong nhiều trường hợp, nhưng cần phân biệt lỗi nào có thể xác định trước.

### Lỗi có thể phát hiện từ source/type

Nếu factory đã được sinh với lệnh:

```java
return new AuditService(store, clock);
```

và constructor chuyển thành:

```java
AuditService(EventStore store, Clock clock, RetryPolicy retry)
```

thì factory cũ sẽ không biên dịch được. Compiler báo vấn đề về chữ ký; generator phù hợp có thể tạo lại factory với dependency mới hoặc báo thiếu binding ở giai đoạn build.

### Lỗi chỉ xuất hiện khi cấu hình cụ thể có hiệu lực

Giả sử ứng dụng chọn `EventStore` theo `STORAGE_MODE` đọc từ biến môi trường:

```text
STORAGE_MODE=memory   → InMemoryEventStore
STORAGE_MODE=jdbc     → JdbcEventStore
STORAGE_MODE=unknown  → lỗi cấu hình
```

Ngay cả khi mã sinh chứa factory cho cả hai implementation, giá trị `unknown` vẫn có thể chỉ được đọc khi ứng dụng chạy. Việc xác minh biến môi trường, credential, network và readiness phải có bước runtime phù hợp.

### Lỗi chỉ xuất hiện ở nhánh lazy hoặc dynamic

Một container có thể đăng ký rất nhiều thành phần nhưng chỉ tạo một số thành phần khi chúng được yêu cầu. Nếu chỉ kiểm tra graph đã dùng trong lúc startup, dependency thiếu ở nhánh ít được gọi có thể không lộ ra cho tới runtime. **Eager validation** hoặc build-time graph analysis có thể mở rộng mức kiểm tra, nhưng phải xem cơ chế cụ thể có bao phủ mọi registration/nhánh hay không.

| Lỗi | Điểm phát hiện sớm có thể đạt |
|---|---|
| Sai số tham số của lệnh `new` trong mã đã sinh | Compile |
| Thiếu binding của một dependency cố định và generator biết toàn bộ graph | Build/compile |
| Qualifier trùng hoặc mapping mơ hồ | Build hoặc startup, tùy container |
| Config môi trường chứa key không hợp lệ | Startup khi parse config |
| Credential sai hoặc database không sẵn sàng | Startup/readiness hoặc trong runtime |
| Provider tạo dependency theo dữ liệu request mà không tìm được implementation | Khi nhánh runtime được thực thi |
| Singleton giữ tài nguyên request đã đóng | Có thể phát hiện qua scope validation; đôi khi chỉ lộ trong test/runtime |

Một đường lắp ghép đáng tin cậy thường kết hợp **compiler checks**, **validation tại composition root**, **readiness**, **kiểm thử graph** và **xử lý lỗi vận hành**, thay vì đặt mọi kỳ vọng vào reflection hoặc code generation.

## 8. Tính linh hoạt lúc chạy và ranh giới extension

Reflection hữu ích nếu ứng dụng thực sự phải khám phá class hoặc plugin từ metadata runtime. Ví dụ plugin host tải module mới, quét các implementation theo hợp đồng và cấp chúng vào graph.

Nhưng “có reflection” không đồng nghĩa **container được phép tự động lựa chọn mọi class tìm thấy**. Ứng dụng phải kiểm soát:

- **Trust boundary:** plugin có được phép tải/chạy không, ai phê duyệt và cách cách ly?
- **Contract:** class có thực sự đáp ứng interface và tiền điều kiện của hệ thống không?
- **Qualifier/key:** nếu nhiều class cùng thỏa một interface, chọn instance nào?
- **Lifecycle:** khi thay plugin, instance cũ có còn công việc đang chạy không?
- **Lỗi:** nếu plugin thiếu constructor hoặc thiếu binding, báo lỗi ở thời điểm nào?

Mã sinh vẫn có thể hỗ trợ động **trong một danh sách lựa chọn đã biết** bằng factory hoặc switch được sinh:

```java
// Mã minh họa khi các implementation đều được biết tại build.
EventStore createStore(StorageMode mode) {
    return switch (mode) {
        case MEMORY -> new InMemoryEventStore();
        case JDBC -> new JdbcEventStore(config);
    };
}
```

Đoạn trên là pseudocode vì `StorageMode`, `JdbcEventStore` và `config` phụ thuộc ứng dụng. Runtime vẫn chọn `mode`; mã sinh chỉ chuẩn bị sẵn các đường xây object. Nếu cần tải **class chưa từng biết tại build**, hệ thống có thể phải kết hợp plugin loader, reflection, service provider hoặc cách tiếp cận động khác.

## 9. Reflection và Java module system, native image

Trong JVM thông thường, reflection tuân theo quyền truy cập của Java. `getConstructors()` chỉ liệt kê constructor public; để truy cập thành viên không công khai có thể phải dùng `getDeclaredConstructors()` và cơ chế quyền truy cập phản chiếu. Với **Java Platform Module System (JPMS)**, việc mở quyền sâu vào package có giới hạn rõ ràng; tùy cấu hình, yêu cầu mở package bằng cơ chế module `opens` hoặc cách khác được thư viện hỗ trợ.

Vì vậy một container dùng reflection cần hiểu **quy tắc đóng gói module**, không nên xem `setAccessible(true)` là giải pháp chung cho mọi package và mọi runtime.

Ở môi trường **native image hoặc AOT theo mô hình closed-world**, công cụ build cần biết trước những class, constructor hoặc thành viên có thể được truy cập động. Một số hình thức reflective access cần metadata, registration/hints hoặc phân tích mà toolchain hỗ trợ. Mã sinh gọi constructor trực tiếp có thể làm cho quan hệ kiểu và lời gọi dễ phân tích hơn, nhưng **không đồng nghĩa toàn bộ ứng dụng hết reflection**: JSON serialization, plugin loading, proxy hoặc các thư viện khác vẫn có thể cần xử lý đặc biệt.

Các đánh đổi thường thấy:

| Mục tiêu | Điều cần xem xét |
|---|---|
| Chạy trên JVM, ứng dụng nhỏ | Độ đơn giản và khả năng đọc composition có thể quan trọng hơn tối ưu wiring |
| Khởi động nhanh, cold start thường xuyên | Đo thời gian scan, graph creation và initialization; cân nhắc build-time preparation |
| Đóng gói native image | Kiểm tra reflective metadata và hỗ trợ AOT của cả framework lẫn thư viện |
| Plugin được thêm lúc runtime | Cần cơ chế discovery/loader, kiểm tra bảo mật và vòng đời rõ |
| Nhiều module Java với encapsulation nghiêm | Kiểm tra reflective access và public API thay vì dựa vào truy cập private |

Không cần chọn framework chỉ từ một khẩu hiệu “zero reflection”. Hãy kiểm tra **phiên bản cụ thể, tính năng thật đang dùng, cách đóng gói và số liệu đo trên ứng dụng**.

## 10. Scope và ownership độc lập với cách tạo object

Dù resolver biết constructor qua reflection hay generated factory gọi trực tiếp `new`, **scope** vẫn cần được thiết kế:

- **Application/singleton:** dùng một instance theo phạm vi một container/application. Phải xét thread safety và tài nguyên được đóng khi shutdown.
- **Request/transaction scoped:** các consumer trong cùng scope có thể dùng chung một instance; scope khác nhận instance khác, và tài nguyên kết thúc đúng ranh giới.
- **Transient/prototype:** mỗi lần resolve có thể tạo một instance mới; nhưng nếu một singleton giữ tham chiếu tới instance đó, lifetime thực tế có thể kéo dài theo singleton.

Cả reflection resolver và code-generated wiring đều có thể thêm cache, provider hoặc scope object. Ví dụ khái niệm:

```text
ApplicationGraph
   ├── singleton ClientPool ─────────────┐
   │                                     │
   ├── RequestScope #1                   │
   │    ├── UnitOfWork #1 ───────────────┤
   │    └── RequestHandler #1            │
   │                                     │
   └── RequestScope #2                   │
        ├── UnitOfWork #2 ───────────────┘
        └── RequestHandler #2
```

Nếu `ClientPool` dùng chung cần đóng lúc shutdown, root/container là owner hợp lý. Nếu `UnitOfWork` là tài nguyên transaction, scope/caller phải kết thúc nó đúng lúc; một container biết constructor không tự bảo đảm giao dịch commit/rollback đúng.

Một lỗi điển hình là **captive dependency**: singleton giữ trực tiếp một dependency chỉ hợp lệ trong request. Việc đổi từ reflection sang mã sinh không tự chữa lỗi scope đó. Có thể cần sửa lifetime, truyền thông tin request qua method hoặc inject factory/provider để lấy dependency trong scope hiện hành.

### Thứ tự giải phóng cũng là trách nhiệm của composition

Nếu `JobWorker` dùng `Repository` và repository dùng `ClientPool`, khi dừng phải bảo đảm worker ngừng xử lý trước khi đóng những dependency mà nó còn cần. Với graph đơn giản, thứ tự giải phóng thường ngược chiều tạo:

```text
Tạo: ClientPool → Repository → JobWorker
Đóng: JobWorker → Repository → ClientPool
```

Container có lifecycle management có thể hỗ trợ việc này, nhưng cần kiểm tra hợp đồng destroy hook, thứ tự đóng bean và nghĩa vụ cleanup khi startup thất bại. Những ràng buộc này tồn tại với cả mã sinh và reflection.

## 11. Khi nào dùng reflection, sinh mã hoặc wiring thủ công?

Không có lựa chọn đúng cho mọi hệ thống. Nên đánh giá **độ phức tạp thực tế của graph** và các yêu cầu vận hành.

| Tình huống | Cách tiếp cận đáng cân nhắc | Lý do |
|---|---|---|
| Công cụ CLI nhỏ, vài service, graph ổn định | Java thuần, constructor injection thủ công | Ít cấu hình, rất dễ đọc và debug |
| Ứng dụng framework có DI container sẵn | Dùng cơ chế đã hỗ trợ đúng phiên bản | Tận dụng scope, lifecycle và integration |
| Nhiều binding động, plugin/discovery tại runtime | Reflection/registry có kiểm soát | Khả năng quan sát metadata và nạp động |
| Workload nhạy cold start và hỗ trợ AOT tốt | Build-time codegen/AOT hoặc cấu hình tối ưu | Có thể chuyển bớt công việc sang build |
| Native image với hạn chế reflective access | Giải pháp có metadata và công cụ AOT phù hợp | Giảm cấu hình truy cập động khó theo dõi |
| Nhiều mode chọn theo request nhưng implementation hữu hạn | Factory/selector chuyên biệt, có thể sinh mã | Đường chọn tường minh và dễ kiểm thử |

Dù chọn gì, ba trách nhiệm nên tiếp tục rõ ràng:

1. **Business class** khai báo collaborator cần thiết, ưu tiên constructor injection cho dependency bắt buộc.
2. **Composition root** chọn implementation, scope và cách xây graph.
3. **Lifecycle boundary** chịu trách nhiệm readiness, shutdown và cleanup những tài nguyên do nó sở hữu.

Nếu business class gọi trực tiếp `container.get(...)` để tự đi tìm nhiều dependency, mã đang nghiêng sang **Service Locator**. Cách đó vẫn có thể hoạt động, nhưng che khuất các collaborator thật và khiến test khó tập trung. Một container có API `resolve` không bắt buộc ứng dụng dùng API đó ngay trong lớp nghiệp vụ.

## 12. Cách đo và đánh giá thay vì kết luận theo tên kỹ thuật

Khi so sánh các giải pháp thực tế, nên đo riêng các chi phí:

- **Build time:** bước annotation processing/AOT tăng bao nhiêu thời gian, generated source có dễ kiểm tra khi lỗi không?
- **Startup:** thời gian đọc cấu hình, scan metadata, xây graph, khởi tạo bean và readiness là bao nhiêu?
- **Memory:** metadata cache, generated classes, object graph và resource được tạo giữ lại bao nhiêu bộ nhớ?
- **Resolution hot path:** có thật sự resolve rất nhiều lần cho mỗi request không, hay graph được xây một lần và dùng lại?
- **Độ ổn định:** thiếu binding được phát hiện sớm đến đâu, vòng phụ thuộc có được báo dễ hiểu không, cleanup khi lỗi có đầy đủ không?
- **Khả năng thay đổi:** thêm implementation, qualifier, plugin, test fake hay scope mới cần sửa những chỗ nào?

Về phép đo, cần kiểm soát warm-up, JIT, số lần chạy, điều kiện tải và hoạt động I/O. Một benchmark chỉ đo `Constructor.newInstance` so với `new` không đại diện cho toàn bộ tác động của container: container có thể cache metadata và khối lượng nghiệp vụ thực tế thường lớn hơn việc tạo đối tượng.

Để debug lỗi graph, nên tìm **đường phụ thuộc gây lỗi**, ví dụ:

```text
OrderHandler
  → OrderService
    → PaymentGateway
      → Missing binding / ambiguous qualifier
```

Một thông báo như trên hữu ích hơn việc chỉ thấy “cannot create OrderHandler”. Mã sinh thường cho stack trace tại factory đã sinh; container reflection có thể báo lỗi khi resolve và kèm dependency path. Cả hai cần khả năng quan sát đủ tốt để chẩn đoán.

## 13. Các lỗi thường gặp

| Hiểu nhầm hoặc lỗi | Hệ quả | Cách nhìn đúng |
|---|---|---|
| “DI là reflection” | Không nhận ra constructor injection thủ công hoặc mã sinh | DI là cách cấp collaborator; cơ chế wiring là lựa chọn khác |
| “Mã sinh luôn nhanh hơn” | Tối ưu nhầm khi chi phí nằm ở I/O hoặc graph design | Đo workload thực tế, phân biệt build/startup/runtime |
| “Reflection chỉ lỗi khi request đầu tiên tới” | Bỏ qua eager validation/startup checks | Container reflection vẫn có thể validate graph sớm |
| “Sinh mã bắt được mọi lỗi trước compile” | Bỏ qua config và hạ tầng runtime | Chỉ bắt sớm những gì công cụ biết được trong build |
| “Có interface thì tự tìm được implementation đúng” | Binding thiếu hoặc mơ hồ | Khai báo selection/qualifier có chủ đích |
| “Transient nghĩa method nào cũng có object mới” | Instance bị giữ lâu ngoài ý định | Hiểu resolve boundary và provider |
| “Container quản lý scope thì không cần ownership” | Leak tài nguyên, đóng nhầm pool, captive dependency | Thiết kế lifecycle và quyền đóng rõ ràng |
| “Dùng reflection phải mở mọi private member” | Đụng encapsulation/module access và khó bảo trì | Ưu tiên public contract hoặc mở quyền có kiểm soát |
| “Native image không thể dùng reflection” | Đánh giá sai khả năng toolchain | Xác minh registration/metadata/AOT hỗ trợ trong stack |
| “Sinh mã là không thể chọn runtime” | Thiết kế factory cứng nhắc | Có thể sinh các nhánh rồi chọn theo dữ liệu runtime |
| “Dùng container thì business service tự resolve dependency” | Ẩn collaborator và khó unit test | Tiêm dependency vào constructor từ ranh giới composition |

## 14. Bài tập thực hành

**Bài tập 1 — Đổi binding reflection.** Trong `WiringMechanismsDemo`, viết thêm `ConsoleEventStore implements EventStore` và đổi map `EventStore.class → ConsoleEventStore.class`. Quan sát `AuditService` không cần thay đổi. Hãy tự trả lời: việc chọn implementation nằm ở đâu?

**Bài tập 2 — Tạo lỗi constructor.** Thêm một dependency bắt buộc vào `AuditService`. Quan sát resolver reflection báo thiếu binding tại thời điểm `resolve` như thế nào; sau đó sửa `GeneratedStyleGraph` để cấp dependency. Phân biệt thời điểm lỗi biên dịch và lỗi runtime trong hai nhánh.

**Bài tập 3 — Thử phát hiện vòng phụ thuộc.** Tạo hai class có constructor public: `First(Second second)` và `Second(First first)`. Resolve `First.class` qua resolver. Giải thích vì sao cần tracking dependency path và vì sao global singleton/Service Locator không phải cách sửa thiết kế chu trình.

**Bài tập 4 — Thiết kế scope.** Giả sử `EventStore` không giữ trạng thái và muốn dùng chung một instance toàn application. Bổ sung instance này vào `suppliedInstances` rồi so sánh tham chiếu của các lần phân giải. Tiếp theo, mô tả cách thêm request scope mà không rò instance sang request khác.

**Bài tập 5 — Cleanup khi startup thất bại.** Thay `InMemoryEventStore` bằng `ClosableEventStore implements EventStore, AutoCloseable`. Thiết kế owner trong composition root để đóng mọi resource đã tạo nếu `AuditService` không lắp được, và đóng theo thứ tự ngược quan hệ phụ thuộc khi shutdown.

**Bài tập 6 — Lựa chọn công nghệ.** Với hai bối cảnh: (a) CLI chạy 5 lệnh, graph có 4 lớp; (b) dịch vụ nhiều module khởi động hàng nghìn lần mỗi ngày và cần native image, hãy nêu tiêu chí quyết định chọn wiring thủ công, reflection container hay codegen/AOT. Không dùng một kết luận cố định chỉ dựa vào số lượng class.

### Câu hỏi tự kiểm tra

1. Reflection tìm constructor ở giai đoạn nào? Mã sinh có thể chuyển công việc nào sang build?
2. Vì sao constructor injection vẫn là DI khi được tạo bằng lệnh `new` thủ công?
3. Container reflection có thể phát hiện thiếu dependency lúc startup không? Phụ thuộc điều kiện gì?
4. Mã sinh có đảm bảo biến môi trường đúng và database luôn sẵn sàng không?
5. Một transient được inject vào singleton sẽ tạo lại mỗi lần method chạy chứ?
6. Có thể dùng mã sinh nhưng vẫn hỗ trợ chọn một trong hai implementation theo mode runtime không?
7. Tại sao một ứng dụng native image có thể cần cấu hình reflective metadata?
8. Reflection hay codegen có tự bảo đảm đóng connection đúng thứ tự không?

**Gợi ý trả lời:** (1) runtime; codegen có thể chuẩn bị factory/graph trước runtime; (2) dependency được cung cấp từ bên ngoài; (3) có, nếu các registration/nhánh được kiểm tra hoặc khởi tạo sớm; (4) không; (5) không, phải xác định resolution boundary; (6) có, thông qua nhánh hoặc factory đã biết; (7) công cụ closed-world cần biết các truy cập động; (8) không, ownership và lifecycle phải được định nghĩa.

## Ghi nhớ

- **Reflection và sinh mã là hai cơ chế hỗ trợ lắp ghép**, không phải hai định nghĩa khác nhau của DI. Lớp nghiệp vụ vẫn nhận collaborator qua constructor và composition root vẫn chịu trách nhiệm chọn implementation.
- **Reflection** khám phá metadata khi chạy, thuận lợi cho khả năng cấu hình/khám phá động nhưng cần thiết kế validation, caching, module access và lifecycle phù hợp.
- **Code generation/AOT** chuẩn bị đường tạo object trước runtime, có thể giảm khám phá động và phát hiện một số lỗi sớm; đồng thời tăng yêu cầu build và không loại bỏ mọi lỗi runtime.
- **Khác biệt hiệu năng phải được đo trên workload thực tế.** Scope, số object cần tạo, I/O, readiness và ứng dụng có dùng lazy initialization hay không đều ảnh hưởng kết quả.
- **Scope và ownership không phụ thuộc công nghệ wiring.** Singleton, request scope, transient, cleanup và thứ tự đóng vẫn phải được thiết kế rõ ràng.
- **Java thuần đủ để nắm bản chất:** viết constructor injection, thử một reflective resolver đơn giản, đối chiếu với factory gọi constructor trực tiếp rồi mới học cấu hình của DI container cụ thể.
