# So sánh Pattern Matching với Registry Handler: Case study Command trong Java 21+

## 1. Bài toán: định tuyến nhiều loại command

Trong ứng dụng xử lý đơn hàng, một lớp điều phối (*dispatcher*) có thể nhận các lệnh như:

- **`Create(id, units)`:** tạo đơn hàng mới với mã đơn và số lượng.
- **`Cancel(id, reason)`:** hủy đơn hàng với lý do.
- **`Ship(id, tracking)`:** bàn giao đơn cho bên vận chuyển với mã vận đơn.
- **`Export(report)`:** yêu cầu xuất báo cáo, minh họa một extension có thể được thêm bởi mô-đun khác.

Một câu hỏi thiết kế thường gặp là: **nên viết `switch` với pattern matching cho từng command, hay xây dựng một registry ánh xạ loại command tới handler?**

Hai cách đều có thể đúng, nhưng tối ưu cho những đặc tính khác nhau:

1. **Pattern `switch` trên tập subtype `sealed`:** dễ nhìn thấy toàn bộ trường hợp, không cần đăng ký handler, compiler giúp kiểm tra *exhaustiveness*.
2. **Registry handler:** mỗi handler được đăng ký dưới một khóa (ví dụ `Class<?>`); bộ điều phối tìm handler khi chạy. Phù hợp khi cấu hình handler, lắp ghép mô-đun hoặc extension thay đổi theo môi trường.
3. **Kết hợp:** xử lý **core command** bằng `sealed` và pattern matching; cung cấp lớp mở cho **plugin action** nếu hệ thống thực sự cần thêm loại command từ ngoài.

Không nên coi registry mặc định là “kiến trúc tốt hơn” vì có nhiều class, hoặc `switch` luôn tốt hơn vì ít code. Cần xét **tập lệnh đóng hay mở**, nơi đặt nghiệp vụ, độ an toàn kiểu, độ rõ lỗi thiếu handler, chi phí vận hành và tần suất mở rộng.

Bài này dùng **Java 21+** với `sealed interface`, `record`, type pattern trong `switch`, generic handler và `Map.copyOf`. Một chương trình độc lập kiểm chứng hai chiến lược trên cùng nghiệp vụ, với **28 phép kiểm tra**.

## 2. Thiết lập mô hình: cố tình phân biệt tập đóng và tập mở

Ta định nghĩa một interface mở cho mọi action, sau đó một interface `sealed` dành riêng cho các lệnh lõi:

~~~java
interface Action {}

sealed interface CoreCommand extends Action
        permits Create, Cancel, Ship {}

record Create(String id, int units) implements CoreCommand {}
record Cancel(String id, String reason) implements CoreCommand {}
record Ship(String id, String tracking) implements CoreCommand {}

// Extension: thuộc Action, nhưng không thuộc CoreCommand.
record Export(String report) implements Action {}
~~~

Đây là **các khai báo minh họa**. Chúng được đặt trong một lớp chạy được ở mục 8.

Cấu trúc kiểu:

~~~text
Action (interface mở)
├── CoreCommand (sealed)
│   ├── Create (record/final)
│   ├── Cancel (record/final)
│   └── Ship (record/final)
└── Export (record/final, ví dụ extension)
~~~

Cách phân chia này có chủ đích:

- `CoreCommand` là **tập đóng**: compiler biết chính xác ba subtype trực tiếp được phép. Một `switch expression` xử lý đủ `Create`, `Cancel` và `Ship` có thể không cần `default`.
- `Action` là **interface mở**: các mô-đun khác có thể khai báo thêm implementation. Registry sẽ nhận đối tượng có kiểu `Action` và tìm handler theo loại thực tế tại runtime.
- `Export` là một implementation của `Action`, **không phải** subtype của `CoreCommand`. Vì vậy một phương thức có tham số `CoreCommand` không nhận `Export` trực tiếp; đây là giới hạn kiểu hữu ích, không phải lỗi bất ngờ.

**Lưu ý:** ví dụ `Export` chỉ minh họa khả năng mở rộng bằng đăng ký trong code. Nó **không** tự thực hiện plugin discovery, hot reload, dependency injection hay tải JAR bên ngoài. Những cơ chế đó phải được thiết kế riêng nếu dự án cần.

### Hai cấp độ trách nhiệm

- **Command model** trả lời “lệnh là gì, dữ liệu của lệnh gồm những gì?”.
- **Dispatcher** trả lời “lệnh này được đưa tới handler nào?”.
- **Handler/service** trả lời “dữ liệu đã hợp lệ chưa và quy tắc nghiệp vụ cho phép hành động không?”.

Giữ ba trách nhiệm tách bạch giúp bài so sánh công bằng: **cả `switch` lẫn registry sẽ gọi cùng một bộ hàm xử lý nghiệp vụ**, thay vì viết hai phiên bản logic khác nhau rồi so tính dễ đọc hoặc kết quả.

## 3. Hợp đồng nghiệp vụ chung để hai cách dispatch tương đương

Ta dùng trạng thái đơn hàng:

~~~java
enum State { MISSING, CREATED, PAID, SHIPPED }

record Context(State state) {
    Context {
        java.util.Objects.requireNonNull(state, "state");
    }
}
~~~

`Context` chứa trạng thái hiện tại của đối tượng cần xử lý. Trong ứng dụng thật, trạng thái có thể đến từ database và đi kèm quyền người dùng, version/locking hoặc các ràng buộc khác; bài cố tình dùng value object nhỏ và **không làm thay đổi trạng thái** để tập trung vào cơ chế dispatch.

Kết quả được phân loại bằng kiểu dữ liệu:

~~~java
enum Code { OK, INVALID, REJECTED, UNSUPPORTED }
record Outcome(Code code, String detail) {}
~~~

Trong đó:

| Kết quả | Ý nghĩa trong ví dụ |
| --- | --- |
| `OK` | Dữ liệu và trạng thái cho phép thực hiện thao tác |
| `INVALID` | Payload thiếu hoặc không đạt validation |
| `REJECTED` | Payload hợp lệ nhưng trạng thái hiện tại không cho phép |
| `UNSUPPORTED` | Registry không có handler cho loại action nhận được |

**Phân biệt rõ**: `UNSUPPORTED` không phải một `ClassCastException`; đó là kết quả có chủ đích khi không tìm thấy handler. `REJECTED` không đồng nghĩa với dữ liệu sai: ví dụ lệnh `Ship` có mã vận đơn đúng định dạng nhưng trạng thái chưa `PAID`.

Các quy tắc minh họa:

- `Create`: `id` không trắng, `units > 0`; chỉ được tạo khi trạng thái là `MISSING`.
- `Cancel`: `id` và `reason` không trắng; chỉ được hủy khi trạng thái là `CREATED` hoặc `PAID`.
- `Ship`: `id` và `tracking` không trắng; chỉ được giao khi trạng thái là `PAID`.
- `Export`: `report` không trắng; là extension trong registry, không kiểm tra trạng thái đơn hàng.

Các số, tên và chính sách trên chỉ là quy tắc **của case study**; không áp đặt lên mọi hệ thống thương mại điện tử.

Ví dụ một handler nghiệp vụ:

~~~java
static Outcome onShip(Ship command, Context context) {
    if (blank(command.id())) return invalid("orderId");
    if (blank(command.tracking())) return invalid("tracking");
    if (context.state() != State.PAID) return rejected("requires-paid");

    return ok("shipped:" + command.id() + ":" + command.tracking());
}
~~~

Đây là **phương thức minh họa** sử dụng các helper `blank`, `invalid`, `rejected` và `ok` được khai báo đầy đủ trong chương trình mục 8.

Điểm quan trọng cho phần so sánh: **không để logic kiểm tra dữ liệu nằm riêng trong một dispatcher**. Nếu cả hai dispatcher đều gọi `onShip(...)`, sự khác nhau chỉ còn nằm ở cách chọn handler.

## 4. Cách A — Pattern `switch` trên `sealed CoreCommand`

Phương thức điều phối ngắn gọn:

~~~java
static Outcome viaSwitch(CoreCommand command, Context context) {
    java.util.Objects.requireNonNull(context, "context");

    return switch (command) {
        case null -> invalid("request");
        case Create c -> onCreate(c, context);
        case Cancel c -> onCancel(c, context);
        case Ship c -> onShip(c, context);
    };
}
~~~

Đây là **phương thức chạy được khi đặt trong lớp đầy đủ** ở mục 8.

### Vì sao cách này dễ đọc?

- Mỗi `case` biểu thị một loại command cụ thể.
- Biến mẫu `c` có kiểu tĩnh chính xác (`Create`, `Cancel`, `Ship`), không cần cast.
- Không có lookup trong `Map` hoặc cấu hình đăng ký nằm ở nơi khác.
- Vì `CoreCommand` là `sealed` và ba subtype `record` là final, compiler Java 21 xác minh các nhánh **bao phủ đủ mọi core command khác null**.
- `case null` công bố rõ chính sách selector null: trả `INVALID:request`, không để `NullPointerException` xảy ra ngoài ý muốn.

**Trường hợp cần nhớ:** `default` trong pattern `switch` Java 21 **không tự xử lý selector `null`**. Vì vậy nếu API cho phép null, dùng `case null`; nếu API cấm null, có thể chủ động dùng `Objects.requireNonNull(command, "command")` trước `switch`.

### Khi thêm core command mới

Giả sử có:

~~~java
// Minh họa phần khai báo, không thuộc chương trình chính:
record Refund(String id, long cents) implements CoreCommand {}
~~~

Nếu `Refund` được thêm vào `permits` của `CoreCommand` nhưng `viaSwitch` chưa có nhánh `Refund`, trình biên dịch có thể từ chối vì `switch expression` không exhaustive. **Đây là một lợi thế về an toàn khi bảo trì**, nhất là khi tập command lõi do cùng team kiểm soát.

Không nên thêm `default -> unsupported(...)` vào `viaSwitch` chỉ để né việc phải cập nhật khi mở rộng tập core: nhánh mặc định rộng có thể che thiếu sót đáng ra compiler nên cảnh báo.

### Hạn chế

Cách `switch` không cho phép tự động “cắm” handler cho loại command hoàn toàn mới mà không thay đổi khai báo kiểu/nguồn sử dụng. Một `Export` chỉ triển khai interface mở `Action` không thể được truyền trực tiếp vào `viaSwitch(CoreCommand, ...)`. Nếu runtime cần tiếp nhận nhiều loại command do plugin độc lập khai báo, tập `sealed` có thể không phù hợp làm tầng dispatch duy nhất.

## 5. Cách B — Registry handler: ánh xạ class tới hàm xử lý

Registry giữ bảng:

~~~text
Create.class  -> onCreate(Create, Context)
Cancel.class  -> onCancel(Cancel, Context)
Ship.class    -> onShip(Ship, Context)
Export.class  -> onExport(Export, Context)   // chỉ ở registry mở rộng
~~~

Khi có một action, nó tra bảng bằng class runtime của action:

~~~java
Registration<? extends Action> match =
        handlers.get(action.getClass());

if (match == null) {
    return unsupported(action.getClass().getSimpleName());
}
return match.run(action, context);
~~~

Đây là **phần thân minh họa** của phương thức `Registry.dispatch`. Nó được kiểm thử đầy đủ trong chương trình mục 8.

### Vì sao dùng `Class` thay vì chuỗi?

Có thể viết `Map<String, Handler>` với khóa `"CREATE"`, `"CANCEL"`, v.v. Nhưng chuỗi dễ bị sai chính tả, trùng tên hoặc thay đổi mà compiler không phát hiện. Trong case study này, `Class<C>` là khóa gắn với kiểu Java cụ thể và giúp **đăng ký handler có type parameter đúng**.

Cú pháp đăng ký mong muốn:

~~~java
new Registry.Builder()
        .add(Create.class, CommandRegistryComparisonDemo::onCreate)
        .add(Cancel.class, CommandRegistryComparisonDemo::onCancel)
        .add(Ship.class, CommandRegistryComparisonDemo::onShip)
        .build();
~~~

Mỗi lời gọi `add(Class<C>, Handler<C>)` yêu cầu handler nhận đúng command kiểu `C`. Ví dụ không thể dễ dàng gán handler `onShip(Ship, Context)` dưới khóa `Create.class` nếu giữ chữ ký generic và method reference chính xác.

**Nhưng** tra handler runtime không được compiler chứng minh exhaustive như `switch` trên `sealed`: quên đăng ký `Ship.class` vẫn có thể biên dịch và chỉ được phát hiện khi chạy hoặc khi test kiểm tra coverage.

## 6. Viết registry không cần unchecked cast

Một bản registry quá đơn giản thường viết:

~~~java
// Anti-pattern minh họa: unchecked cast, có thể che lỗi type safety.
Map<Class<?>, Object> handlers = new java.util.HashMap<>();
Object handler = handlers.get(command.getClass());
// Ép về một handler generic bất kỳ tại đây rất dễ không an toàn.
~~~

Trong Java, type erasure khiến việc cast trực tiếp từ `Handler<?>` sang `Handler<Create>` không thể kiểm chứng đầy đủ bằng runtime. Không nên lạm dụng `@SuppressWarnings("unchecked")` khi có lựa chọn an toàn hơn.

Dùng một lớp `Registration<C extends Action>` **đóng gói cặp khóa và handler cùng type parameter**:

~~~java
@FunctionalInterface
interface Handler<C extends Action> {
    Outcome handle(C command, Context context);
}

static final class Registration<C extends Action> {
    private final Class<C> type;
    private final Handler<C> handler;

    Registration(Class<C> type, Handler<C> handler) {
        this.type = type;
        this.handler = handler;
    }

    Outcome run(Action action, Context context) {
        return handler.handle(type.cast(action), context);
    }
}
~~~

Ở đây:

1. `Class<C> type` và `Handler<C> handler` cùng sử dụng `C`, nên registration nhất quán theo kiểu.
2. `Class.cast(action)` kiểm tra tại runtime rằng đối tượng thực sự thuộc kiểu đăng ký; không cần cast handler generic không kiểm tra.
3. `Registry.dispatch` chỉ gọi `run` của `Registration<? extends Action>`; wildcard được gói bên trong registration, nơi `C` vẫn thống nhất.
4. `Class.cast` **vẫn có thể ném `ClassCastException`** nếu gọi sai đối tượng hoặc dữ liệu registry bị xây dựng sai. Trong đường dispatch bình thường, việc tra bằng `action.getClass()` và thêm entry qua builder generic giúp tránh trường hợp đó.

Một builder:

~~~java
static final class Builder {
    private final java.util.Map<Class<? extends Action>,
            Registration<? extends Action>> entries =
            new java.util.HashMap<>();

    <C extends Action> Builder add(Class<C> type, Handler<C> handler) {
        java.util.Objects.requireNonNull(type, "type");
        java.util.Objects.requireNonNull(handler, "handler");

        if (entries.putIfAbsent(type,
                new Registration<>(type, handler)) != null) {
            throw new IllegalArgumentException(
                    "duplicate handler: " + type.getSimpleName());
        }
        return this;
    }
}
~~~

Đoạn trên là **phần chính của builder**; phương thức `build()` và lớp `Registry` đầy đủ ở mục 8. Kiểm tra `putIfAbsent` làm lỗi đăng ký trùng xuất hiện **ngay khi khởi tạo**, thay vì âm thầm ghi đè handler cũ.

### Đóng băng registry sau khi đăng ký

Chương trình dùng:

~~~java
this.handlers = java.util.Map.copyOf(handlers);
~~~

`Map.copyOf` tạo ánh xạ không sửa đổi qua API của map. Sau khi `build()`, registry không nhận đăng ký mới; muốn thêm extension phải tạo **một registry mới có tập đăng ký mới**.

Điều này giảm rủi ro handler thay đổi giữa chừng khi nhiều thread đang dispatch. Tuy nhiên, **map bất biến không tự làm handler thread-safe**. Nếu handler giữ state mutable, kết nối hoặc cache dùng chung, vẫn phải bảo vệ đồng bộ và lifecycle ở tầng tương ứng.

## 7. So sánh công bằng: hai dispatcher gọi chung business logic

Ta không nhân bản `onCreate`, `onCancel`, `onShip` theo từng kiến trúc. Cả `viaSwitch` và `Registry.dispatch` đều chọn đúng **cùng một hàm nghiệp vụ**.

Ví dụ với `Create("O1", 3)` và `Context(MISSING)`:

~~~text
             +----------------------+
             | CoreCommand: Create  |
             +----------------------+
                      |
           +----------+-----------+
           |                      |
           v                      v
    Pattern switch             Registry
    case Create c        handlers[Create.class]
           |                      |
           +----------+-----------+
                      |
                      v
            onCreate(Create, Context)
                      |
                      v
           Outcome(OK, "created:O1:3")
~~~

Khi `Create("O1", 0)`, cả hai cùng trả `Outcome(INVALID, "units")`. Khi context đã `CREATED`, cả hai cùng trả `Outcome(REJECTED, "order-exists")`.

**Một chi tiết quan trọng:** quy tắc nghiệp vụ được kiểm tra **trước khi xác nhận trạng thái cho phép**. Ví dụ `Create(" ", 0)` ngay cả khi đơn đã tồn tại sẽ báo lỗi dữ liệu `orderId` trước. Nếu thay thứ tự kiểm tra trong các handler, cả hai chiến lược dispatch vẫn có thể giống nhau nhưng **hợp đồng lỗi của API đã đổi**; cần test thứ tự ưu tiên.

### Phương thức registry xử lý null và handler thiếu

Chương trình chính dùng:

~~~java
Outcome dispatch(Action action, Context context) {
    java.util.Objects.requireNonNull(context, "context");

    if (action == null) return invalid("request");

    Registration<? extends Action> match =
            handlers.get(action.getClass());

    if (match == null) {
        return unsupported(action.getClass().getSimpleName());
    }
    return match.run(action, context);
}
~~~

Registry phân biệt:

- `null` action → `INVALID:request`.
- Không có handler cho runtime class → `UNSUPPORTED:<type>`.
- Có handler → trả kết quả `OK`, `INVALID` hoặc `REJECTED` tùy nghiệp vụ.

**Không nên** thay toàn bộ đường này bằng `try/catch (ClassCastException | NullPointerException)` rồi coi tất cả là lỗi dữ liệu. Exception lập trình, handler thiếu và payload không hợp lệ là những sự kiện khác nhau.

## 8. Chương trình Java 21 hoàn chỉnh — 28 ca kiểm thử

Lưu nguyên mã thành tệp **`CommandRegistryComparisonDemo.java`**. Chương trình chỉ dùng JDK, không cần Maven, DI framework hoặc thư viện bên ngoài.

~~~java
public class CommandRegistryComparisonDemo {
    interface Action {}

    sealed interface CoreCommand extends Action
            permits Create, Cancel, Ship {}

    record Create(String id, int units) implements CoreCommand {}
    record Cancel(String id, String reason) implements CoreCommand {}
    record Ship(String id, String tracking) implements CoreCommand {}
    record Export(String report) implements Action {}

    enum State { MISSING, CREATED, PAID, SHIPPED }
    enum Code { OK, INVALID, REJECTED, UNSUPPORTED }

    record Context(State state) {
        Context {
            java.util.Objects.requireNonNull(state, "state");
        }
    }

    record Outcome(Code code, String detail) {}
    record Case(String name, CoreCommand command, Context context,
                Outcome expected) {}

    static Outcome ok(String detail) {
        return new Outcome(Code.OK, detail);
    }

    static Outcome invalid(String detail) {
        return new Outcome(Code.INVALID, detail);
    }

    static Outcome rejected(String detail) {
        return new Outcome(Code.REJECTED, detail);
    }

    static Outcome unsupported(String detail) {
        return new Outcome(Code.UNSUPPORTED, detail);
    }

    static boolean blank(String text) {
        return text == null || text.isBlank();
    }

    static Outcome onCreate(Create command, Context context) {
        if (blank(command.id())) return invalid("orderId");
        if (command.units() <= 0) return invalid("units");
        if (context.state() != State.MISSING) return rejected("order-exists");
        return ok("created:" + command.id() + ":" + command.units());
    }

    static Outcome onCancel(Cancel command, Context context) {
        if (blank(command.id())) return invalid("orderId");
        if (blank(command.reason())) return invalid("reason");
        if (context.state() == State.MISSING) {
            return rejected("order-not-found");
        }
        if (context.state() == State.SHIPPED) {
            return rejected("already-shipped");
        }
        return ok("cancelled:" + command.id());
    }

    static Outcome onShip(Ship command, Context context) {
        if (blank(command.id())) return invalid("orderId");
        if (blank(command.tracking())) return invalid("tracking");
        if (context.state() != State.PAID) {
            return rejected("requires-paid");
        }
        return ok("shipped:" + command.id() + ":" + command.tracking());
    }

    static Outcome onExport(Export action, Context context) {
        if (blank(action.report())) return invalid("report");
        return ok("export:" + action.report());
    }

    static Outcome viaSwitch(CoreCommand command, Context context) {
        java.util.Objects.requireNonNull(context, "context");
        return switch (command) {
            case null -> invalid("request");
            case Create c -> onCreate(c, context);
            case Cancel c -> onCancel(c, context);
            case Ship c -> onShip(c, context);
        };
    }

    @FunctionalInterface
    interface Handler<C extends Action> {
        Outcome handle(C command, Context context);
    }

    static final class Registration<C extends Action> {
        private final Class<C> type;
        private final Handler<C> handler;

        Registration(Class<C> type, Handler<C> handler) {
            this.type = type;
            this.handler = handler;
        }

        Outcome run(Action action, Context context) {
            return handler.handle(type.cast(action), context);
        }
    }

    static final class Registry {
        private final java.util.Map<Class<? extends Action>,
                Registration<? extends Action>> handlers;

        private Registry(java.util.Map<Class<? extends Action>,
                Registration<? extends Action>> handlers) {
            this.handlers = java.util.Map.copyOf(handlers);
        }

        Outcome dispatch(Action action, Context context) {
            java.util.Objects.requireNonNull(context, "context");
            if (action == null) return invalid("request");

            Registration<? extends Action> match =
                    handlers.get(action.getClass());

            if (match == null) {
                return unsupported(action.getClass().getSimpleName());
            }
            return match.run(action, context);
        }

        java.util.Set<Class<? extends Action>> types() {
            return handlers.keySet();
        }

        static final class Builder {
            private final java.util.Map<Class<? extends Action>,
                    Registration<? extends Action>> entries =
                    new java.util.HashMap<>();

            <C extends Action> Builder add(
                    Class<C> type, Handler<C> handler) {
                java.util.Objects.requireNonNull(type, "type");
                java.util.Objects.requireNonNull(handler, "handler");

                if (entries.putIfAbsent(type,
                        new Registration<>(type, handler)) != null) {
                    throw new IllegalArgumentException(
                            "duplicate handler: "
                            + type.getSimpleName());
                }
                return this;
            }

            Registry build() {
                return new Registry(entries);
            }
        }
    }

    static Registry.Builder coreBuilder() {
        return new Registry.Builder()
                .add(Create.class,
                        CommandRegistryComparisonDemo::onCreate)
                .add(Cancel.class,
                        CommandRegistryComparisonDemo::onCancel)
                .add(Ship.class,
                        CommandRegistryComparisonDemo::onShip);
    }

    static final Registry CORE = coreBuilder().build();
    static final Registry EXTENDED = coreBuilder()
            .add(Export.class, CommandRegistryComparisonDemo::onExport)
            .build();

    private static int passed = 0;

    static void check(String label, boolean condition) {
        if (!condition) throw new AssertionError(label);
        passed++;
        System.out.println("PASS " + label);
    }

    static void compare(Case item) {
        Outcome expected = item.expected();
        Outcome bySwitch =
                viaSwitch(item.command(), item.context());
        Outcome byRegistry =
                CORE.dispatch(item.command(), item.context());

        if (!expected.equals(bySwitch)
                || !expected.equals(byRegistry)) {
            throw new AssertionError(
                    item.name() + ": expected=" + expected
                    + ", switch=" + bySwitch
                    + ", registry=" + byRegistry);
        }
        check(item.name(), true);
    }

    static void duplicateRegistration() {
        try {
            new Registry.Builder()
                    .add(Create.class,
                            CommandRegistryComparisonDemo::onCreate)
                    .add(Create.class,
                            CommandRegistryComparisonDemo::onCreate);
            throw new AssertionError(
                    "expected duplicate handler error");
        } catch (IllegalArgumentException expected) {
            check("duplicate-handler-rejected", true);
        }
    }

    static void nullContext(String label, Runnable operation) {
        try {
            operation.run();
            throw new AssertionError(
                    "expected null context error");
        } catch (NullPointerException expected) {
            check(label, true);
        }
    }

    public static void main(String[] args) {
        Context missing = new Context(State.MISSING);
        Context created = new Context(State.CREATED);
        Context paid = new Context(State.PAID);
        Context shipped = new Context(State.SHIPPED);

        Case[] cases = {
            new Case("create-ok", new Create("O1", 3), missing,
                    ok("created:O1:3")),
            new Case("create-existing", new Create("O1", 3), created,
                    rejected("order-exists")),
            new Case("create-null-id", new Create(null, 3), missing,
                    invalid("orderId")),
            new Case("create-blank-id", new Create(" ", 3), missing,
                    invalid("orderId")),
            new Case("create-zero", new Create("O1", 0), missing,
                    invalid("units")),
            new Case("create-negative", new Create("O1", -1), missing,
                    invalid("units")),
            new Case("cancel-created",
                    new Cancel("O1", "changed"), created,
                    ok("cancelled:O1")),
            new Case("cancel-paid",
                    new Cancel("O1", "changed"), paid,
                    ok("cancelled:O1")),
            new Case("cancel-missing",
                    new Cancel("O1", "changed"), missing,
                    rejected("order-not-found")),
            new Case("cancel-shipped",
                    new Cancel("O1", "changed"), shipped,
                    rejected("already-shipped")),
            new Case("cancel-null-id",
                    new Cancel(null, "changed"), created,
                    invalid("orderId")),
            new Case("cancel-blank-reason",
                    new Cancel("O1", " "), created,
                    invalid("reason")),
            new Case("ship-paid", new Ship("O1", "TR-5"), paid,
                    ok("shipped:O1:TR-5")),
            new Case("ship-created",
                    new Ship("O1", "TR-5"), created,
                    rejected("requires-paid")),
            new Case("ship-missing",
                    new Ship("O1", "TR-5"), missing,
                    rejected("requires-paid")),
            new Case("ship-shipped",
                    new Ship("O1", "TR-5"), shipped,
                    rejected("requires-paid")),
            new Case("ship-null-id",
                    new Ship(null, "TR-5"), paid,
                    invalid("orderId")),
            new Case("ship-blank-tracking",
                    new Ship("O1", " "), paid,
                    invalid("tracking")),
            new Case("ship-long-code",
                    new Ship("O2", "TRACK-123"), paid,
                    ok("shipped:O2:TRACK-123")),
            new Case("null-command",
                    null, paid, invalid("request"))
        };

        for (Case test : cases) compare(test);

        check("complete-registry-coverage", CORE.types().equals(
                java.util.Set.of(
                        Create.class, Cancel.class, Ship.class)));

        check("extension-registered", EXTENDED.dispatch(
                new Export("monthly"), missing)
                .equals(ok("export:monthly")));

        check("extension-invalid", EXTENDED.dispatch(
                new Export(" "), missing)
                .equals(invalid("report")));

        check("extension-unregistered", CORE.dispatch(
                new Export("monthly"), missing)
                .equals(unsupported("Export")));

        Registry partial = new Registry.Builder()
                .add(Create.class,
                        CommandRegistryComparisonDemo::onCreate)
                .build();

        check("missing-core-handler", partial.dispatch(
                new Ship("O1", "TR-5"), paid)
                .equals(unsupported("Ship")));

        duplicateRegistration();

        nullContext("null-context-switch",
                () -> viaSwitch(new Create("O1", 1), null));

        nullContext("null-context-registry",
                () -> CORE.dispatch(new Create("O1", 1), null));

        System.out.println("ALL PASSED: " + passed);
    }
}
~~~

### Lệnh biên dịch/chạy

Dùng JDK 21 trở lên:

~~~bash
javac --release 21 CommandRegistryComparisonDemo.java
java CommandRegistryComparisonDemo
~~~

**Output chính xác:**

~~~text
PASS create-ok
PASS create-existing
PASS create-null-id
PASS create-blank-id
PASS create-zero
PASS create-negative
PASS cancel-created
PASS cancel-paid
PASS cancel-missing
PASS cancel-shipped
PASS cancel-null-id
PASS cancel-blank-reason
PASS ship-paid
PASS ship-created
PASS ship-missing
PASS ship-shipped
PASS ship-null-id
PASS ship-blank-tracking
PASS ship-long-code
PASS null-command
PASS complete-registry-coverage
PASS extension-registered
PASS extension-invalid
PASS extension-unregistered
PASS missing-core-handler
PASS duplicate-handler-rejected
PASS null-context-switch
PASS null-context-registry
ALL PASSED: 28
~~~

### Kết quả này chứng minh điều gì?

**20 ca đầu** cùng kiểm tra `viaSwitch` và `CORE.dispatch` trên một danh sách core command rồi so sánh hai kết quả với `Outcome` kỳ vọng. Nhờ record `Outcome` có `equals` theo component, phép so sánh kiểm tra cả mã lỗi lẫn nội dung, không chỉ tên class.

**Tám ca cuối** kiểm tra những điều mà ví dụ dispatch bình thường dễ bỏ qua:

1. `complete-registry-coverage`: kiểm tra thủ công `CORE` đã đăng ký đúng ba class core hiện biết.
2. `extension-registered`: registry mở rộng nhận `Export` đã đăng ký.
3. `extension-invalid`: extension vẫn phải validate dữ liệu của mình.
4. `extension-unregistered`: registry core trả `UNSUPPORTED` cho `Export` chưa đăng ký.
5. `missing-core-handler`: registry thiếu handler `Ship` vẫn được xây dựng; khi chạy mới trả `UNSUPPORTED`.
6. `duplicate-handler-rejected`: builder từ chối hai handler cùng khóa `Create.class`.
7. `null-context-switch`: dispatcher dùng `switch` từ chối context null.
8. `null-context-registry`: registry cũng từ chối context null, giữ hợp đồng giống nhau.

**Quan trọng:** ca coverage thủ công là test dựa trên danh sách `Create/Cancel/Ship` hiện tại. Nó **không cung cấp bảo đảm compiler exhaustiveness** nếu sau này thêm `Refund` mà quên sửa cả danh sách test. Registry vẫn cần quy trình đăng ký và kiểm tra runtime riêng.

Chương trình chỉ **tính và trả kết quả mô phỏng**, không ghi database, không gửi yêu cầu vận chuyển và không thực hiện export thật. Vì vậy đây là ví dụ kiểm thử điều phối và validation, không phải bản implementation hoàn chỉnh của hệ thống đơn hàng.

## 9. Khác biệt thật sự khi thêm command mới

### 9.1. Thêm một core command

Giả sử bổ sung `Refund` như một subtype của `CoreCommand`:

~~~java
// Minh họa, không thêm vào tệp chính khi chưa cập nhật permits.
record Refund(String id, long cents) implements CoreCommand {}
~~~

Để dùng đúng mô hình `sealed`, phải cập nhật `permits` của `CoreCommand`. Sau đó:

- **Pattern `switch`:** `viaSwitch` có thể báo lỗi **không exhaustive** khi biên dịch lại vì chưa có nhánh `Refund`.
- **Registry:** bản registry core cũ vẫn có thể tạo được và không có handler `Refund`; khi nhận lệnh ấy sẽ trả `UNSUPPORTED`. Việc thiếu đăng ký chỉ được phát hiện qua validation tại startup, test hoặc runtime.
- **Business logic:** cả hai cách đều phải định nghĩa handler và test cho nghiệp vụ hoàn tiền; dispatch không tự sinh ra luật.

Một **negative compile test** nhỏ để quan sát compiler:

~~~java
// Tệp minh họa cố ý không biên dịch:
public class MissingCommandCase {
    sealed interface C permits A, B {}
    record A() implements C {}
    record B() implements C {}

    static int route(C cmd) {
        return switch (cmd) {
            case null -> 0;
            case A a -> 1;
        };
    }
}
~~~

Chạy `javac --release 21 MissingCommandCase.java` sẽ bị từ chối vì `switch expression` **thiếu xử lý `B`**. Tệp này là **negative compile test**, không được gộp vào chương trình chạy ở mục 8.

### 9.2. Thêm một action mở rộng

Một extension như `Export` chỉ triển khai `Action`. Nó không làm thay đổi `CoreCommand.permits`, nên `viaSwitch(CoreCommand, ...)` tiếp tục exhaustive cho tập core hiện tại.

Để registry nhận extension, cần tạo instance có đăng ký:

~~~java
Registry extended = coreBuilder()
        .add(Export.class, CommandRegistryComparisonDemo::onExport)
        .build();
~~~

**Registry không tự phát hiện handler** chỉ vì một implementation tồn tại. `Export` chỉ hoạt động nếu đã đăng ký trong builder hoặc qua cơ chế plugin discovery/DI mà ứng dụng thực sự cung cấp.

Ở hệ thống production, việc nạp plugin có thể dùng `ServiceLoader`, dependency injection hoặc cấu hình mô-đun. Khi đó phải xác định rõ lifecycle, quyền truy cập, xử lý đăng ký trùng, lỗi khởi tạo, thứ tự tải, tính an toàn và contract phiên bản. Không nên lấy một registry map đơn giản làm bằng chứng hệ thống đã hỗ trợ plugin an toàn.

## 10. Bảng so sánh kiến trúc

| Tiêu chí | Pattern `switch` trên `sealed` | Registry handler |
| --- | --- | --- |
| Tập command lý tưởng | Đóng, biết tại compile time | Có thể mở hoặc thay đổi theo cấu hình |
| Dispatch | Nhánh `case` trên kiểu command | Lookup handler theo khóa runtime |
| Kiểm tra handler còn thiếu | Compiler giúp kiểm tra exhaustive | Startup validation, test hoặc runtime |
| Cơ chế type safety | Biến pattern có kiểu xác định | Generic registration + `Class.cast` |
| Cấu hình handler | Nằm trong code `switch` | Có thể tập trung hoặc ghép từ mô-đun |
| Thêm subtype core | Cần sửa `permits` và các `switch` liên quan | Cần đăng ký handler; nếu thiếu có thể chỉ lỗi lúc chạy |
| Thêm plugin từ ngoài | `sealed` cố tình giới hạn | Có thể hỗ trợ khi interface và lifecycle cho phép |
| Phụ thuộc framework | Không bắt buộc | Không bắt buộc, nhưng DI/discovery có thể hữu ích |
| Khi debug | Nhìn case tương ứng và guard | Kiểm tra registry đã đăng ký, class key, handler và logic |
| Lỗi null | Cần `case null` hoặc từ chối sớm | Cần nhánh `action == null` hoặc hợp đồng từ chối |
| Độ phức tạp khởi đầu | Thấp cho vài command | Cao hơn do builder/map/registration |
| Tính testable | Test từng handler và nhánh `switch` | Test handler, coverage, duplicate, missing, lookup |
| Hiệu năng | Phụ thuộc JVM/JIT và workload | Phụ thuộc map lookup, cast, handler dispatch, JVM/JIT |
| Khả năng quan sát | Có thể gắn metrics ở dispatcher/handler | Có thể gắn metrics quanh mỗi entry/handler |

Registry có thể tích hợp với **Command Pattern** (mỗi command là đối tượng đại diện yêu cầu và handler thực thi yêu cầu), nhưng các mẫu thiết kế không có quy tắc độc quyền: một `switch` tập trung hoặc method đa hình cũng có thể thực thi command hợp lý.

## 11. Chi tiết dễ sai với registry

### 11.1. Lookup theo exact class, không tự tìm superclass

Mã ví dụ dùng:

~~~java
handlers.get(action.getClass())
~~~

Nó tìm entry với **runtime class chính xác** của đối tượng, không tự duyệt superclass hay interface để tìm handler “gần đúng nhất”.

Điều này phù hợp với các record final trong case study. Nhưng nếu command có phân cấp mở, proxy do framework tạo hoặc subtype của một class command, lookup theo exact class có thể không tìm thấy handler đăng ký cho class cha.

Có thể thiết kế cơ chế **assignable matching** hoặc đăng ký một interface chung, nhưng khi nhiều handler cùng khớp, phải định nghĩa **thứ tự ưu tiên/độ đặc hiệu**, và việc tìm kiếm có thể tăng độ phức tạp. Không âm thầm đổi `get(action.getClass())` sang duyệt `isAssignableFrom` mà không có luật giải quyết nhập nhằng.

### 11.2. Registration generic không làm mọi nhầm lẫn biến mất

`Builder.add(Create.class, Handler<Create>)` đảm bảo quan hệ kiểu cho mỗi entry. Nhưng runtime registry vẫn cần kiểm tra:

- Có handler cho mọi command dự kiến không?
- Có đăng ký trùng không?
- Handler có trả kết quả đúng hợp đồng không?
- Có code nào dùng raw type hoặc unchecked cast phá type safety không?
- Có class-loader khác nhau tạo ra class danh nghĩa giống nhau nhưng khác identity không?

`Class.cast` là một kiểm tra runtime hữu ích, không thay thế toàn bộ test integration.

### 11.3. Sự khác biệt giữa mutable builder và immutable registry

`Builder` dùng `HashMap` trong **giai đoạn lắp ghép**, không nên dùng chung tùy tiện giữa nhiều thread. Sau `build()`, `Registry` dùng `Map.copyOf` và không có API thay đổi đăng ký.

Nếu cần hot reload plugin, có thể cân nhắc tạo registry mới rồi **thay thế tham chiếu nguyên tử** ở ranh giới ứng dụng, thay vì sửa trực tiếp một map mà các luồng đang sử dụng. Nhưng hot reload là một yêu cầu khác, cần quản lý shutdown, sự nhất quán và lifecycle của handler.

### 11.4. Đăng ký handler không đồng nghĩa thực thi nghiệp vụ thành công

Registry có thể tìm thấy handler nhưng handler vẫn trả `INVALID` hoặc `REJECTED`. Ngược lại, handler thiếu là `UNSUPPORTED`. Tách các loại kết quả này giúp log, metrics và phản hồi API không làm người vận hành nhầm “không có code xử lý” với “người dùng gửi sai trường”.

## 12. Những lỗi thường gặp khi dùng Pattern Matching cho command

**Lỗi 1 — dùng `default` che mất lợi ích exhaustive.** Nếu `CoreCommand` là sealed, việc thiếu case mới nên được compiler báo; `default` rộng có thể giấu việc quên xử lý `Refund`.

**Lỗi 2 — hiểu sai `null`.** Trong Java 21 pattern `switch`, selector null không tự đi vào `default`. Định nghĩa `case null` hoặc kiểm tra `requireNonNull` theo hợp đồng.

**Lỗi 3 — đưa validation vào một loạt case khác nhau trong khi registry gọi logic khác.** Như vậy hai chiến lược không còn cùng hành vi và khó so sánh. Dùng chung service/handler nghiệp vụ giúp refactor dispatch không sửa luật.

**Lỗi 4 — coi `record` luôn hợp lệ.** `Create(null, -1)` vẫn là một record hợp lệ về kiểu nếu không có constructor validation. Pattern matching kiểm tra kiểu, không tự kiểm tra mã đơn hay số lượng dương.

**Lỗi 5 — sử dụng một `switch` rất lớn làm tất cả công việc.** Khi từng command có hàng chục bước và dependency, chuyển nghiệp vụ sang handler/service có tên rõ. `switch` chỉ làm dispatch.

**Lỗi 6 — kỳ vọng registry tự phát hiện mọi class mới.** Việc có một implementation `Action` chưa tạo registration. Phải đăng ký bằng code, DI hoặc plugin discovery được kiểm soát.

**Lỗi 7 — dùng `Map<Class<?>, Object>` rồi unchecked cast khắp nơi.** Dễ lỗi runtime và khó review. Kết hợp `Class<C>` + `Handler<C>` trong một typed registration để giới hạn điểm cast.

**Lỗi 8 — âm thầm ghi đè handler cũ.** `map.put(...)` có thể thay handler mà người vận hành không biết. Với registry một handler/loại, dùng `putIfAbsent` và fail-fast khi trùng.

**Lỗi 9 — coi test coverage thủ công giống exhaustiveness của compiler.** `Set.of(Create.class, Cancel.class, Ship.class)` chỉ đúng nếu người bảo trì nhớ cập nhật danh sách; compiler `switch` dựa trực tiếp trên tập subtype của kiểu sealed.

**Lỗi 10 — cho rằng registry map bất biến làm mọi handler thread-safe.** Handler có state mutable vẫn có thể race condition. Registry và handler là hai mức trách nhiệm khác nhau.

**Lỗi 11 — giả định lookup theo `Class` khớp cả subclass/proxy.** `map.get(actualClass)` chỉ khớp khóa chính xác; phải chủ động hỗ trợ kiểu kế thừa nếu ứng dụng cần.

**Lỗi 12 — kết luận hiệu năng không đo.** `switch` có thể được JIT tối ưu tốt; registry có chi phí lookup/cast, nhưng tác động thực phụ thuộc workload. Muốn kết luận, dùng benchmark có kiểm soát và đo đường xử lý thật.

## 13. Chọn chiến lược theo hoàn cảnh

### Nên ưu tiên `switch` với pattern matching khi

- Số command vừa phải, tập variant **đóng** và do một nhóm phát triển kiểm soát.
- Thêm command mới phải buộc người bảo trì rà soát mọi điểm dispatch.
- Nghiệp vụ từng loại được trích thành method ngắn, `switch` chỉ làm ánh xạ.
- Muốn khai thác **compiler exhaustiveness**, code dễ đọc và ít cấu hình runtime.

### Nên cân nhắc registry handler khi

- Command được cung cấp từ nhiều mô-đun, plugin, hoặc cần chọn handler theo cấu hình.
- Mỗi handler có dependency/lifecycle khác nhau và được DI container quản lý.
- Muốn thêm/bớt handler ở tầng lắp ghép mà không sửa một `switch` tập trung cho interface mở.
- Chấp nhận và kiểm soát đầy đủ lỗi thiếu handler, trùng handler và sai cấu hình.

### Nên kết hợp khi

- Có **lõi giao thức ổn định** và tập `CoreCommand` đóng cần bảo đảm exhaustive.
- Ngoài lõi vẫn cần các action bổ sung, được đăng ký vào registry chung.
- Cần giữ ranh giới rõ: loại nào thuộc core và loại nào có thể được nhà phát triển plugin bổ sung.

**Không cần registry** chỉ vì “có thể sau này thêm một command”. Cơ chế plugin có chi phí thiết kế, bảo trì và an toàn. Ngược lại, nếu thực sự có hàng chục module độc lập cung cấp handler, một `switch` trung tâm phải chỉnh sửa mỗi lần tích hợp có thể trở thành điểm nghẽn tổ chức.

## 14. Chiến lược chuyển đổi từ code cũ

Nếu đang có mã kiểu:

~~~java
// Cách cũ minh họa, cần các type tương ứng.
if (raw instanceof Create) {
    Create c = (Create) raw;
    return onCreate(c, context);
}
if (raw instanceof Cancel) {
    Cancel c = (Cancel) raw;
    return onCancel(c, context);
}
if (raw instanceof Ship) {
    Ship c = (Ship) raw;
    return onShip(c, context);
}
~~~

Có thể chuyển theo từng bước:

1. **Chốt hợp đồng input và null:** dữ liệu đến từ API công khai hay command đã parse? Null là lỗi validation hay lỗi lập trình?
2. **Tách nghiệp vụ khỏi dispatch:** đưa từng trường hợp về các method `onCreate`, `onCancel`, `onShip`. Viết test về outcome.
3. **Nếu tập core đóng:** khai báo `sealed CoreCommand` và chuyển dispatcher sang `switch expression`, không thêm `default` che thiếu subtype.
4. **Nếu có extension thực sự:** định nghĩa interface mở `Action` và cơ chế đăng ký typed handler; xác định chính sách `UNSUPPORTED`.
5. **Xác thực khi khởi động:** kiểm tra duplicate, missing handler (nếu danh sách handler bắt buộc được biết), dependency và cấu hình.
6. **Giữ test so sánh:** chạy cùng tập command qua dispatcher cũ/mới và đối chiếu kết quả. Với handler có side effect, dùng fake dependency hoặc transaction/test isolation để không thực hiện thao tác hai lần lên dữ liệu thật.
7. **Chỉ đo hiệu năng khi có nhu cầu:** nếu dispatch là điểm nóng, dùng JMH hoặc profiling đường đi thực tế, không suy luận từ số dòng mã.

Có thể giữ `switch` như “adapter” phân tuyến và dùng các handler class thực thi nghiệp vụ. Hai kỹ thuật **không loại trừ nhau**.

## 15. Checklist review và bài tập

### Checklist

1. Input dispatcher là `CoreCommand` đóng hay `Action` mở? Quyết định đó có đúng chiến lược extension?
2. `switch` có exhaustive khi thêm subtype mới vào `permits` không?
3. Null selector và null `Context` có hợp đồng rõ ràng không?
4. Handler có kiểm tra dữ liệu trước khi xem điều kiện trạng thái không?
5. Hai cách dispatch có dùng chung nghiệp vụ và trả cùng `Outcome` không?
6. Registry có đăng ký typed handler không, có tránh raw/unchecked casts?
7. Có từ chối duplicate registration ngay khi dựng registry?
8. Có test thiếu handler và xử lý `UNSUPPORTED` khi lookup thất bại?
9. Lookup theo exact runtime class có phù hợp với proxy/subclass/module không?
10. Registry đã immutable sau khởi tạo chưa, và handler riêng lẻ có thread-safe nếu cần?
11. Extension có được đăng ký rõ ràng, có kiểm soát dependency và quyền truy cập không?
12. Có test cho null, chuỗi trắng, giá trị biên, trạng thái không hợp lệ và thêm command mới?
13. Có tránh `default` che thiếu subtype trong tập core đóng?
14. Có phân biệt lỗi nghiệp vụ dự kiến với bug hoặc lỗi hạ tầng?
15. Có tài liệu hóa khả năng mở rộng và hậu quả tương thích API khi thêm subtype không?

### Bài tập

- **Bài 1:** Thêm `Refund(String id, long cents)` vào `CoreCommand`. Quan sát compiler báo `viaSwitch` thiếu nhánh, sau đó thêm `onRefund` và registration registry. Viết test so sánh hai dispatcher.
- **Bài 2:** Tạo registry thiếu `Cancel.class` rồi chạy lệnh `Cancel`. Viết startup validation để phát hiện lỗi trước khi nhận request.
- **Bài 3:** Thử đăng ký hai handler khác nhau cho cùng `Create.class`. Giải thích vì sao fail-fast ở builder tốt hơn ghi đè im lặng.
- **Bài 4:** Thêm `ExportJson(String report)` chỉ triển khai `Action`, đăng ký trong `EXTENDED` nhưng không chỉnh sửa `CoreCommand`. Kiểm thử đường extension và dữ liệu thiếu.
- **Bài 5:** Chuyển `Registry.dispatch` sang lookup cho phép superclass/interface, rồi đặt hai handler cùng khớp. Xác định luật ưu tiên và test trường hợp nhập nhằng.
- **Bài 6:** Viết bộ test cho side-effecting handler bằng fake repository, xác minh không chạy handler hai lần khi so hai chiến lược.
- **Bài 7:** Dùng JMH đo chi phí dispatch trên một tập hỗn hợp command, bảo đảm giữ nguyên logic handler và không bịa số liệu từ một lần chạy.
- **Bài 8:** Thử thêm `case Create(var id, var units) when units > 0` nhưng không có nhánh `Create` không guard. Giải thích vì sao guard không tự bảo đảm exhaustive cho toàn subtype.

**Ghi nhớ:** **Pattern `switch` + `sealed CoreCommand`** tối ưu cho tập lệnh đóng, tính dễ đọc và kiểm tra exhaustive tại compile time. **Registry handler** phù hợp khi cần lắp ghép handler theo kiểu và mở rộng runtime, nhưng đổi lại phải kiểm soát đăng ký trùng, thiếu handler, lookup và lifecycle. Cách so sánh đúng là giữ **cùng nghiệp vụ và cùng kết quả**, kiểm thử cả tình huống lỗi, rồi chọn cơ chế dispatch phù hợp với ranh giới kiến trúc — không chạy theo một design pattern vì tên gọi.