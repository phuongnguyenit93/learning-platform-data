# Theo dõi trạng thái bị chia sẻ qua đối số và giá trị trả về

## 1. Mục tiêu: nhìn thấy trạng thái thực sự được chia sẻ ở đâu

Trong Spring Framework, một bean `singleton` thường được nhiều request và nhiều thread gọi đồng thời. Rủi ro không chỉ đến từ các trường (field) nằm trong bean: trạng thái mutable có thể đi **vào bean qua đối số**, đi qua nhiều lớp service/repository/callback, rồi **thoát ra ngoài qua giá trị trả về**. Hai lời gọi tưởng như độc lập vẫn có thể cùng giữ tham chiếu đến một đối tượng và sửa dữ liệu của nhau.

Bài này hướng dẫn lần theo **đường đi của tham chiếu, quyền sửa và thời điểm truy cập**. Sau khi học, bạn cần trả lời được năm câu hỏi cho một lời gọi:

1. Đối tượng được tạo ở đâu, do ai sở hữu, có thể thay đổi hay không?
2. Tham số nhận **giá trị riêng** hay **tham chiếu tới cùng đối tượng mutable**?
3. Phương thức có sửa đối tượng tham số, lưu nó vào field/cache, hoặc chuyển tiếp sang thread khác không?
4. Giá trị trả về là giá trị mới, snapshot, view hay chính đối tượng nội bộ?
5. Có bao nhiêu luồng có thể đọc/ghi cùng đối tượng tại một thời điểm, và cơ chế bảo vệ là gì?

**Phạm vi:** theo dõi trạng thái bean qua luồng dữ liệu Java và Spring; hiểu vấn đề correctness và phương án thiết kế. Đây không phải bài tổng quan tất cả primitive concurrency.

## 2. Từ vựng và mô hình tham chiếu phải nắm

- **State (trạng thái):** dữ liệu mô tả một đối tượng tại một thời điểm, ví dụ `Cart.items`, `Order.status` hay `Service.lastRequest`.
- **Mutable object:** đối tượng có thể thay đổi sau khi tạo, ví dụ `ArrayList`, `HashMap`, DTO có setter, mảng, `StringBuilder`.
- **Immutable value:** đối tượng có trạng thái quan sát được không đổi sau khi tạo, ví dụ `String`, `Integer`, hoặc record được thiết kế với toàn bộ dữ liệu bên trong cũng bất biến.
- **Reference/alias:** hai biến khác nhau cùng trỏ tới một đối tượng. `a == b` đúng với hai biến tham chiếu nghĩa là cùng identity; `a.equals(b)` có thể đúng dù là hai đối tượng khác nhau.
- **Ownership:** quy ước thành phần nào được phép sửa và quản lý vòng đời đối tượng. Java không tự áp đặt ownership qua kiểu tham chiếu thông thường.
- **Escape:** tham chiếu vốn được xem là nội bộ thoát ra ngoài, chẳng hạn lưu đối số vào singleton field, đưa vào callback giữ lâu, hoặc trả về collection nội bộ.
- **Snapshot:** bản chụp giá trị tại một thời điểm. Snapshot nông (*shallow*) chỉ sao chép cấu trúc ngoài; các phần tử mutable bên trong có thể vẫn dùng chung.
- **Thread confinement:** trạng thái chỉ được một thread truy cập trong vòng đời liên quan. Một biến local chỉ có ô tham chiếu riêng trên stack; đối tượng nó trỏ tới vẫn có thể được chia sẻ.

Java **truyền đối số theo giá trị** (*pass-by-value*). Với kiểu nguyên thủy, giá trị số/boolean được sao chép; với kiểu tham chiếu, **giá trị tham chiếu được sao chép**, còn đối tượng phía sau không được sao chép tự động. Vì vậy trong phương thức, gán lại biến tham số không làm biến của người gọi trỏ sang đối tượng mới, nhưng sửa trạng thái trên đối tượng mà cả hai cùng tham chiếu thì người gọi có thể quan sát thay đổi.

```text
Caller                         Bean method                      Return
  request ── reference ───────► parameter
     │                              │
     └────────► Mutable DTO ◄────────┘
                    │
                    ├──── bean.field = parameter  (escape/retention)
                    ├──── executor.submit(() -> use(parameter))  (cross-thread)
                    └──── return parameter  (escape/alias)
                              │
callerResult ─────────────────┘ cùng identity, không tự tạo bản sao
```

Sơ đồ mô tả trường hợp có thể xảy ra, không có nghĩa mọi phương thức đều lưu hay trả về chính đối tượng đầu vào. Tại từng mũi tên phải xác minh điều gì thực sự được truyền và có thao tác copy hay không.

## 3. Theo dõi một đối số từ caller vào bean

Giả sử controller gọi `service.process(command)`. Đừng chỉ nhìn tên biến `command`; cần theo một **đối tượng cụ thể** đi qua lời gọi:

| Điểm kiểm tra | Câu hỏi quan trọng | Tín hiệu cần quan sát |
| --- | --- | --- |
| Controller / caller | `command` được tạo mới cho lần gọi này hay lấy từ field/cache/session? | Vị trí `new`, factory, cache lookup, injection |
| Lúc tạo DTO | Trường bên trong có được copy không? | Constructor, setter, `List.copyOf`, copy constructor |
| Vào service | Phương thức chỉ đọc, sửa trực tiếp hay giữ lại tham chiếu? | `setX`, `add`, `put`, `this.current = command` |
| Qua lời gọi tiếp | Có truyền chính DTO hoặc các phần tử mutable của nó sang phương thức khác? | Parameter forwarding, lambda capture, callback, event |
| Sang async | Tác vụ bắt đầu trước hay sau khi caller tiếp tục sửa DTO? | `@Async`, executor, future, queue, latch |
| Kết thúc | Caller nhận giá trị mới hay reference đang được nhiều nơi nắm giữ? | `return command`, `return this.items`, copy/snapshot |

Một đối tượng được tạo riêng cho mỗi HTTP request **thường có thể an toàn** nếu không ai chia sẻ nó đồng thời và nó không thoát vào trạng thái sống lâu hơn request. Tuy nhiên, nhận DTO ở một tham số không chứng minh DTO đó là riêng tư: caller có thể truyền cùng một object cho hai request công việc, đặt nó trong cache, hoặc đưa nó sang task async.

Các cách trạng thái có thể được chia sẻ mà không dễ thấy:

- Lưu đối số vào field của singleton bean, đối tượng `static`, registry, cache hoặc collection dùng chung.
- Trả lại nguyên object, mảng, `List` hay `Map` được quản lý nội bộ.
- Truyền một phần tử mutable nằm trong collection cho thành phần khác.
- Bắt tham chiếu trong lambda, callback, listener hoặc `Runnable` để chạy về sau.
- Dùng cùng bean phụ thuộc có field mutable mặc dù bean hiện tại không có field.
- Dùng `ThreadLocal` hoặc context chứa đối tượng mutable rồi lại đưa chính đối tượng đó cho thread khác. ThreadLocal không làm đối tượng trở thành immutable.

Một field khai báo `final` chỉ ngăn **gán lại tham chiếu field**, không ngăn `list.add(...)` trên danh sách mà field đang giữ.

## 4. Ví dụ Java: cùng object đi qua tham số và được trả lại

Tệp `AliasFlowDemo.java` chạy với Java 17+:

```java
import java.util.ArrayList;
import java.util.List;

public class AliasFlowDemo {
    static final class RequestData {
        private final List<String> tags;

        RequestData(List<String> tags) {
            this.tags = tags; // Cố tình giữ nguyên tham chiếu
        }

        List<String> tags() {
            return tags; // Cố tình lộ collection nội bộ
        }
    }

    static List<String> process(RequestData request) {
        request.tags().add("server");
        return request.tags();
    }

    public static void main(String[] args) {
        List<String> callerTags = new ArrayList<>(List.of("caller"));
        RequestData request = new RequestData(callerTags);

        List<String> returned = process(request);

        System.out.println(callerTags);
        System.out.println(callerTags == returned);

        returned.add("outside");
        System.out.println(request.tags());
    }
}
```

```bash
javac AliasFlowDemo.java
java AliasFlowDemo
```

Kết quả:

```text
[caller, server]
true
[caller, server, outside]
```

Phân tích đường tham chiếu:

1. `callerTags` là một `ArrayList` mutable do caller tạo.
2. Constructor `RequestData` gán `this.tags = tags`; đây là cùng một list, dù field được khai báo `final`.
3. `process` sửa list qua tham số `request`, nên caller thấy phần tử `server`.
4. `process` trả về chính list đó; `returned == callerTags` là `true`.
5. Caller sửa `returned` thì `request.tags()` cũng thay đổi. Không có đồng thời trong ví dụ, nhưng khi nhiều thread cùng thực hiện các bước này, sẽ có nguy cơ data race và vi phạm quy tắc nghiệp vụ.

**Điều cần ghi nhớ:** hai biến có tên khác nhau, nằm ở hai lớp khác nhau, không có nghĩa hai vùng trạng thái độc lập. Theo dõi identity của đối tượng chứ không chỉ tên biến.

## 5. Phân biệt tham số local với đối tượng bên trong tham số

Phương thức sau chỉ gán lại biến tham số cục bộ nên không làm caller đổi tham chiếu:

```java
static void replace(List<String> values) {
    values = new ArrayList<>(); // Chỉ biến local 'values' trỏ nơi khác
    values.add("new");
}
```

Đây là fragment minh họa; giả định `List` và `ArrayList` đã import. Ngược lại, `values.clear()` hoặc `values.add(...)` tác động lên chính đối tượng mà caller truyền vào.

Với tham số primitive như `int count`, tăng `count++` trong phương thức không sửa biến primitive của caller. Nhưng nếu primitive là **field trong một object** và phương thức dùng `request.setCount(...)`, object chung vẫn bị sửa.

Đừng đánh đồng hai phát biểu:

- “Method không có mutable local variable dùng chung” là nhận định về **ô biến local**.
- “Method không thao tác shared mutable state” là nhận định mạnh hơn về **toàn bộ object graph có thể truy cập**: đối tượng tham số, phần tử của chúng, các bean được inject và đối tượng được trả về.

Một service không có field mutable vẫn có thể thực hiện thao tác không thread-safe nếu caller truyền cùng một `ArrayList` cho các thread khác nhau để cùng sửa. Ngược lại, một service stateless chỉ đọc immutable input và tạo immutable output thường dễ dùng an toàn giữa nhiều request.

## 6. Theo dõi trạng thái đi ra qua return value

Giá trị trả về là một điểm thoát (escape) quan trọng. Xem cách phương thức tạo giá trị trước khi đánh giá an toàn.

| Dạng trả về | Thực chất | Rủi ro/khả năng |
| --- | --- | --- |
| `return internalList;` | Cùng list nội bộ | Caller có thể sửa dữ liệu bean; nhiều caller có thể cùng sửa |
| `return Collections.unmodifiableList(internalList);` | View không cho sửa qua biến view | Nếu nguồn `internalList` đổi, view vẫn phản ánh thay đổi |
| `return List.copyOf(internalList);` | Collection không sửa được, có nội dung snapshot của list lúc copy | Copy **nông**; phần tử mutable vẫn có thể dùng chung |
| `return new ArrayList<>(internalList);` | List ngoài mới, có thể sửa | Caller sửa cấu trúc list riêng nhưng phần tử mutable vẫn chia sẻ |
| `return new Result(total, status);` | Đối tượng kết quả mới | An toàn hơn nếu các field và object lồng nhau bất biến |
| `return this;` | Cùng instance chứa trạng thái | Có thể làm lộ toàn bộ API mutable của đối tượng |
| `return CompletableFuture<T>;` | Handle kết quả tương lai | Khi hoàn tất, `T` vẫn có thể là mutable object dùng chung |

Không có một loại copy tự động giải quyết mọi vấn đề. Cần quyết định **snapshot ở mức nào**: chỉ sao chép list ngoài, sao chép DTO từng phần tử, hay chuyển thành immutable value object hoàn toàn. `List.copyOf` yêu cầu phần tử khác `null`; nếu dữ liệu có null, chọn chiến lược khác và ghi rõ hợp đồng.

### 6.1. Ví dụ: read-only view khác snapshot

Tệp `ViewVsSnapshotDemo.java` chạy với Java 17+:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ViewVsSnapshotDemo {
    public static void main(String[] args) {
        List<String> original = new ArrayList<>(List.of("A"));
        List<String> view = Collections.unmodifiableList(original);
        List<String> snapshot = List.copyOf(original);

        original.add("B");

        System.out.println("view=" + view);
        System.out.println("snapshot=" + snapshot);

        try {
            snapshot.add("C");
        } catch (UnsupportedOperationException e) {
            System.out.println("snapshot blocks add");
        }
    }
}
```

```bash
javac ViewVsSnapshotDemo.java
java ViewVsSnapshotDemo
```

Kết quả:

```text
view=[A, B]
snapshot=[A]
snapshot blocks add
```

`view` cấm sửa thông qua chính view, nhưng vẫn quan sát thay đổi từ `original`; `snapshot` giữ cấu trúc danh sách tại thời điểm tạo. Ví dụ dùng `String` (immutable). Nếu phần tử là `MutableAddress` hoặc `ArrayList`, dù có snapshot outer list, nội dung từng phần tử vẫn có thể bị sửa từ nơi khác.

### 6.2. Thiết kế DTO immutable với defensive copy

Tệp `ImmutableBoundaryDemo.java` chạy với Java 17+:

```java
import java.util.ArrayList;
import java.util.List;

public class ImmutableBoundaryDemo {
    record Command(String id, List<String> tags) {
        Command {
            tags = List.copyOf(tags);
        }
    }

    record Result(String id, int count) {}

    static Result handle(Command command) {
        return new Result(command.id(), command.tags().size());
    }

    public static void main(String[] args) {
        List<String> callerTags = new ArrayList<>(List.of("first"));
        Command command = new Command("R-1", callerTags);

        callerTags.add("later");
        Result result = handle(command);

        System.out.println(command.tags());
        System.out.println(result.id() + ":" + result.count());
    }
}
```

```bash
javac ImmutableBoundaryDemo.java
java ImmutableBoundaryDemo
```

Kết quả:

```text
[first]
R-1:1
```

Record không tự biến các thành phần mutable thành bất biến sâu. Constructor chuẩn hóa bằng `List.copyOf` để ngăn alias với list gốc. Vì phần tử ở đây là `String`, snapshot này đủ cho ví dụ. Nếu record chứa `List<MutableItem>`, cần immutable element/copy tương ứng. Thời điểm copy cũng phải được bảo vệ nếu một thread khác đang đồng thời sửa list nguồn.

Trong API thực tế, tạo *result DTO* mô tả dữ liệu caller cần thay vì trả cả entity đang được cache/quản lý bởi bean. Tách **hợp đồng dữ liệu** khỏi **object identity nội bộ** giúp dễ theo dõi và test hơn.

## 7. Bean scope không thay thế việc kiểm tra chia sẻ tham chiếu

Trong Spring, các scope ảnh hưởng vòng đời instance; chúng không tự biến đối tượng mutable thành thread-safe.

| Phạm vi/tình huống | Điều thường đúng | Điều vẫn phải kiểm tra |
| --- | --- | --- |
| `singleton` (mặc định) | Một instance bean cho mỗi bean definition trong một Spring container | Các request/thread cùng gọi và có thể truy cập field hoặc dữ liệu được giữ lại |
| `prototype` | Spring tạo instance khi container được yêu cầu cấp bean | Nếu inject prototype vào singleton một lần, singleton thường giữ instance nhận lúc inject; không tự tạo mới theo từng lời gọi |
| `request` | Instance gắn với một HTTP request đang hoạt động | Reference có bị chuyển sang async/lưu vào singleton; request scope có còn active lúc truy cập không? |
| Method local | Mỗi invocation có biến local riêng | Object do biến local trỏ tới có bị chia sẻ không? |
| Bean dependency `final` | Tham chiếu dependency không bị gán lại | Dependency có field mutable hay cache thiếu đồng bộ không? |

Ví dụ **mẫu Spring không an toàn** (fragment, cần project Spring và định nghĩa `Cart`):

```java
@Service
class CartService {
    private Cart lastCart;

    public Cart inspect(Cart argument) {
        lastCart = argument; // Giữ reference từ caller trong singleton
        return lastCart;     // Đưa reference đang giữ ra caller
    }
}
```

Giả định đã import `org.springframework.stereotype.Service`. Trong thiết kế này, `argument` được chuyển vào field sống lâu và trả về, nên request sau có thể thay `lastCart`; hai thread cũng có thể truy cập `Cart` mutable cùng lúc. Thêm `volatile` vào `lastCart` chỉ cải thiện visibility của **tham chiếu field**, không làm thao tác trên `Cart` trở nên atomic, không tách ownership và cũng không ngăn request này đọc trạng thái request khác.

Một phiên bản an toàn hơn thường không cần field `lastCart`: đọc dữ liệu cần thiết từ command, tính toán bằng local immutable value và trả `CartResult` mới. Nếu thực sự phải lưu shared state (ví dụ cache), hãy xác định rõ dữ liệu được lưu, cách cập nhật atomic, thời gian sống, chính sách đồng bộ và kiểu snapshot trả ra.

## 8. Khi đi qua thread boundary: đối số vẫn có thể cùng identity

Với executor, `CompletableFuture` hoặc `@Async`, caller có thể tiếp tục chạy sau khi nộp tác vụ. Nếu task giữ cùng tham chiếu tới DTO mutable thì trạng thái có thể đổi **trước khi task đọc**. Điều này khác với trường hợp truyền giá trị immutable đã chụp trước khi submit.

Quy tắc quan trọng của `ExecutorService`: các hành động trong thread trước khi submit task có quan hệ *happens-before* với hành động của task; và hành động của task có quan hệ *happens-before* với việc caller truy xuất kết quả thành công qua `Future.get()`. Quy tắc đó **không** tạo một snapshot bất biến của đối số và không tự sắp thứ tự cho mọi thao tác sửa xảy ra sau khi submit.

### 8.1. Ví dụ hoàn chỉnh: task đọc thay đổi được thực hiện sau khi submit

Tệp `AsyncAliasDemo.java` chạy với Java 17+:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class AsyncAliasDemo {
    static final class Payload {
        private String message;

        Payload(String message) {
            this.message = message;
        }

        void setMessage(String message) {
            this.message = message;
        }

        String message() {
            return message;
        }
    }

    public static void main(String[] args) throws Exception {
        Payload payload = new Payload("before");
        CountDownLatch allowRead = new CountDownLatch(1);
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            Future<String> result = executor.submit(() -> {
                allowRead.await();
                return payload.message();
            });

            payload.setMessage("after");
            allowRead.countDown();
            System.out.println(result.get());
        } finally {
            executor.shutdown();
        }
    }
}
```

```bash
javac AsyncAliasDemo.java
java AsyncAliasDemo
```

Kết quả:

```text
after
```

Điều gì xảy ra?

- Task được submit khi `payload.message` vẫn là `"before"`, nhưng không nhận bản copy của `Payload`.
- Caller sửa cùng object thành `"after"` rồi mới gọi `countDown()`.
- Worker chờ `await()`; sau khi latch mở, nó đọc object đã sửa. Quan hệ *happens-before* do latch bảo đảm kết quả xác định trong ví dụ.
- `result.get()` đợi task hoàn thành. Nếu bỏ latch, thời điểm task đọc so với lần caller sửa sẽ phụ thuộc scheduling; không dựa vào `sleep` để đoán kết quả.

**Cách sửa hợp đồng:** tạo immutable `PayloadSnapshot` trước khi submit, rồi truyền snapshot vào task; hoặc chuyển quyền sở hữu sang task, và caller cam kết không sửa nữa. Nếu cả hai bên cần sửa, cần thiết kế cơ chế đồng bộ/queue phù hợp. Không giải quyết bằng cách tùy tiện thêm `volatile` vào tất cả field.

### 8.2. `@Async` trong Spring

Đoạn minh họa Spring với input immutable (cần dependency Spring, đã bật `@EnableAsync` và phương thức được gọi **qua proxy Spring**):

```java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

record InspectCommand(String id, List<String> codes) {
    InspectCommand {
        codes = List.copyOf(codes);
    }
}

record InspectResult(String id, int codeCount) {}

@Service
public class InspectService {
    @Async
    public CompletableFuture<InspectResult> inspect(InspectCommand command) {
        InspectResult result =
                new InspectResult(command.id(), command.codes().size());
        return CompletableFuture.completedFuture(result);
    }
}
```

Đây là **mẫu tích hợp Spring**, chưa phải chương trình tự chạy bằng `javac` vì cần file, package và cấu hình Spring phù hợp. Một file Java công khai đặt tên `InspectService.java`. `@Async` chuyển công việc sang executor do Spring quản lý khi đi qua cơ chế interception phù hợp; nó **không tự sao chép tham số**. Self-invocation, tức gọi `this.inspect(...)` trong chính bean, thường bỏ qua proxy `@Async` ở chế độ proxy mặc định. Tùy cấu hình, một executor có thể cần khai báo rõ để kiểm soát tài nguyên.

Trong ví dụ, `InspectCommand` tạo snapshot danh sách lúc khởi tạo và phần tử là `String` immutable; dữ liệu task đọc không bị caller làm đổi thông qua list ban đầu. Return value cũng là `InspectResult` mới chỉ chứa giá trị immutable. Lưu ý thread chạy `@Async` thường không tự kế thừa transaction hoặc mọi thread-local context của thread caller; truyền context được cho phép bằng cơ chế rõ ràng, không giữ toàn bộ request object chỉ để lấy một thuộc tính sau này.

## 9. Trường hợp trạng thái sai qua field và return: lỗi xen kẽ giữa hai request

Xét singleton bean có field `currentUser`. Mỗi request gọi `begin(user)` rồi `finish()` để nhận user tương ứng. Hai lời gọi riêng lẻ có thể được bảo vệ bằng `synchronized` nhưng **chuỗi nghiệp vụ** vẫn có thể bị xen kẽ nếu không có thiết kế trạng thái riêng cho request.

Ví dụ runnable `CrossRequestLeakDemo.java` (Java 17+), dùng latch để tạo thứ tự xác định mà không dùng `sleep`:

```java
import java.util.concurrent.CountDownLatch;

public class CrossRequestLeakDemo {
    static final class SingletonLikeService {
        private String currentUser;

        void begin(String user) {
            currentUser = user;
        }

        String finish() {
            return currentUser;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        SingletonLikeService bean = new SingletonLikeService();
        CountDownLatch firstBegun = new CountDownLatch(1);
        CountDownLatch secondBegun = new CountDownLatch(1);

        Thread first = new Thread(() -> {
            bean.begin("Lan");
            firstBegun.countDown();
            try {
                secondBegun.await();
                System.out.println("Lan sees " + bean.finish());
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        Thread second = new Thread(() -> {
            try {
                firstBegun.await();
                bean.begin("Minh");
                secondBegun.countDown();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        first.start();
        second.start();
        first.join();
        second.join();
    }
}
```

```bash
javac CrossRequestLeakDemo.java
java CrossRequestLeakDemo
```

Kết quả khi các thread không bị ngắt từ ngoài:

```text
Lan sees Minh
```

`firstBegun` và `secondBegun` tạo quan hệ thứ tự và visibility rõ ràng. Vấn đề là **state được lưu sai chỗ**, trong field của một instance dùng chung, nên request của Lan nhận dữ liệu của Minh. Cách sửa đơn giản: không lưu `currentUser` ở field singleton; truyền user thành đối số cho hàm xử lý và trả kết quả của chính lần gọi, hoặc lưu theo request/transaction có định danh và vòng đời tường minh.

Nếu chỉ thêm `synchronized` lên `begin()` và `finish()` riêng lẻ, lỗi thiết kế vẫn có thể xảy ra giữa hai lời gọi. Muốn dùng lock phải bảo vệ **toàn bộ invariant** trong một vùng tới hạn thích hợp; tuy nhiên kiến trúc không giữ trạng thái request trong singleton thường tốt hơn.

## 10. Quy trình lần vết một luồng dữ liệu trong dự án thực tế

Với một endpoint hoặc một lời gọi service, hãy bắt đầu tại **giá trị đầu vào đang nghi vấn** rồi đi theo *reference graph*, không bắt đầu bằng việc đổi toàn bộ bean scope.

### Bước 1 — Xác định object gốc và ownership

Ghi lại: loại dữ liệu, nơi tạo, bean/request nào sở hữu, ai được phép mutate, thời điểm hết vòng đời. Ví dụ `List<OrderItem> items` lấy từ cache khác với list do JSON request body được deserialize riêng cho từng request.

### Bước 2 — Vẽ đường đi qua đối số

Theo dõi các method call, cả field trên DTO và phần tử collection. Nếu `serviceA(A)` gọi `serviceB(A.getItems())`, chính `List` có thể đang được chia sẻ dù serviceB không nhận toàn bộ DTO. Những lời gọi setter, `clear`, `sort`, `removeIf`, `computeIfAbsent`, hoặc thao tác trên entity đang managed đều đáng đánh dấu.

### Bước 3 — Tìm điểm giữ lại hoặc phát tán tham chiếu

Các điểm thường cần xem: gán vào `this.field`/`static`, cache, listener, event chứa payload mutable, callback/lambda, tạo future, đưa vào queue, đặt vào request/session attribute. Một method có vẻ chỉ “chuyển tiếp dữ liệu” nhưng lại khiến đối tượng sống lâu hơn caller.

### Bước 4 — Tìm đường trả về và biến đổi trung gian

Dùng bảng theo dõi ngắn:

| Mốc | Đối tượng cụ thể | Hành động | Ai có thể sửa tiếp? |
| --- | --- | --- | --- |
| Controller | `request.tags` | Tạo list từ input | Controller/các method được truyền |
| Service | `command.tags` | Trỏ vào cùng list nếu không copy | Service và caller |
| Executor | `capturedCommand` | Lambda giữ tham chiếu | Worker; caller nếu còn alias |
| Bean field | `lastTags` | Giữ lại reference | Mọi invocation thấy field |
| Return | `result.tags` | Trả list gốc hoặc bản copy | Caller và các chủ sở hữu còn lại |
| Boundary an toàn | `List.copyOf(tags)` của immutable elements | Snapshot trước khi chạy async | Caller chỉ đọc snapshot; input gốc do caller quản lý |

Điền tên thật của object và thời điểm mutation; không kết luận chỉ từ tên kiểu dữ liệu. Với đối tượng nested, tiếp tục theo tới phần tử có thể thay đổi.

### Bước 5 — Kiểm tra concurrency và happens-before

Xác định thread nào tạo, sửa, đọc; có cùng executor không; task có thể chạy sau khi phương thức caller trả về không; có sử dụng lock/atomic/queue/future đúng cách không. Cần biết **cả trật tự thực thi lẫn quyền sửa**. `Future.get()` có thể cho bạn thấy kết quả đã hoàn tất, nhưng không ngăn một thread khác tiếp tục sửa đối tượng kết quả mutable sau đó.

### Bước 6 — Quan sát bằng công cụ

- Debugger: đặt breakpoint tại constructor, chỗ sửa field, điểm submit async và return; so sánh identity tham chiếu bằng `==` khi có hai biến cụ thể.
- Logging/tracing: ghi `traceId`/`requestId` tường minh, thread name, loại sự kiện (created/copied/mutated/returned) và một mã object có mục đích chẩn đoán; tránh log toàn bộ dữ liệu nhạy cảm.
- `System.identityHashCode(object)` có thể hỗ trợ nhận diện trong log điều tra, nhưng **không bảo đảm duy nhất** và không phải object ID ổn định xuyên các lần chạy.
- Thread dump/JFR: dùng khi cần xác định thread đang chờ/giữ monitor hoặc thời gian truy cập; chúng không tự chỉ ra semantic ownership của DTO.
- Test: dùng `assertSame` để chứng minh alias, `assertNotSame` để kiểm tra object khác identity và các assertion về snapshot; dùng latch để tái tạo thời điểm đọc/ghi.

Không dùng log “cùng content” để kết luận “cùng object”: hai object độc lập vẫn có thể cùng `equals`. Cũng đừng dùng `System.identityHashCode` làm khóa dữ liệu trong production.

## 11. Chiến lược thiết kế để cắt đường chia sẻ không mong muốn

**A. Stateless bean, immutable input và output.** Lý tưởng cho nghiệp vụ thuần tính toán: caller chuyển command immutable vào; service tạo result mới; không đặt `lastRequest`, `tempResult` hay `currentUser` trong field singleton.

**B. Chuyển ownership rõ ràng.** Nếu cần hiệu suất và cho phép mutable object, quy định sau khi submit thì caller không được sửa/đọc đồng thời đối tượng cho đến khi task hoàn thành; áp dụng bằng thiết kế API và test. Cam kết bằng lời mà không có ranh giới kỹ thuật thường dễ bị phá vỡ.

**C. Defensive copy tại boundary.** Sao chép trước khi bean lưu giữ/callback chạy, và sao chép khi trả ra nội bộ mutable. Chọn shallow hoặc deep copy theo kiểu các phần tử. Không đọc một collection đang bị thread khác sửa mà không có đồng bộ chỉ vì dự định “copy ngay”.

**D. Shared mutable state có chủ đích.** Nếu phải chia sẻ, chọn cấu trúc/primitive phù hợp: `ConcurrentHashMap.compute` cho cập nhật atomic một key, lock cho invariant nhiều trường, atomic type cho một giá trị độc lập, queue cho trao đổi message. Không giả định một collection thread-safe khiến chuỗi nhiều thao tác thành atomic.

**E. Context dữ liệu riêng với context thread.** Truyền trace ID, tenant ID hoặc quyền cần dùng theo hợp đồng của phương thức/cơ chế propagation được hỗ trợ. `@Async` đổi thread; `ThreadLocal` trong worker không mặc nhiên có cùng giá trị với caller. Không đưa nguyên `HttpServletRequest` hoặc bean request-scoped qua async chỉ để truy xuất về sau.

**F. API return có ý nghĩa.** Trả ID, immutable DTO, immutable snapshot hoặc operation result; tránh trả raw entity/cache object mutable nếu caller không được phép thay đổi trạng thái nội bộ. Với event payload và cache result cũng áp dụng cùng nguyên tắc.

Một contract hữu ích có thể ghi rõ: “Method không mutate đầu vào; không giữ tham chiếu đầu vào sau khi trả về; output không chia sẻ mutable state với repository cache”. Đó là điều có thể test, rõ hơn “service thread-safe”.

## 12. Kiểm thử tập trung vào alias và trạng thái bị rò rỉ

Thực hiện kiểm thử theo ba tầng, từ đơn giản đến concurrency:

1. **Alias/identity test:** caller tạo mutable object, gọi service, rồi sửa object gốc và object trả về; xác định bên nào thay đổi. Kiểm tra `assertSame`/`assertNotSame` chỉ khi identity thật sự là hợp đồng.
2. **Mutation isolation test:** tạo command/result theo API đã định, sửa nguồn ban đầu sau đó và kiểm tra snapshot không thay đổi; với nested mutable, sửa cả phần tử.
3. **Concurrent scheduling test:** cho hai lời gọi dùng chung bean, cùng hoặc khác đối tượng; dùng `CountDownLatch` để tạo thứ tự xác định, ghi nhận read/write và verify result đúng request. Đặt timeout để test không treo.
4. **Async completion test:** xác minh input được chụp trước submit, kết quả sau `Future.get()` đúng, lỗi/timeout/hủy được xử lý, và service không giữ reference khi tác vụ hoàn tất.
5. **Load test và quan sát:** với cache/shared state thực tế, tăng concurrency rồi đo race, queue, latency, error và ảnh hưởng bộ nhớ; test stress bổ sung nhưng không thay thế lập luận thread-safety.

Ví dụ assertion JUnit 5 dạng **fragment** (giả định có các lớp/constructor của `ImmutableBoundaryDemo` và đã import JUnit 5):

```java
var source = new ArrayList<>(List.of("one"));
var command = new ImmutableBoundaryDemo.Command("id-1", source);

source.add("two");

assertEquals(List.of("one"), command.tags());
assertNotSame(source, command.tags());
assertThrows(UnsupportedOperationException.class,
        () -> command.tags().add("three"));
```

Những assertion này kiểm tra hợp đồng snapshot của collection ngoài; chúng không chứng minh tất cả object nested là immutable hoặc mọi lời gọi đồng thời là an toàn. Có thể cần thêm test cho từng kiểu mutable ở tầng sâu.

## 13. Lỗi phổ biến và cách giải thích chính xác

| Nhận định/lỗi | Vì sao sai | Cách kiểm tra/sửa |
| --- | --- | --- |
| “Các tham số là local nên luôn an toàn.” | Biến local riêng, object phía sau có thể được nhiều thread dùng chung | Trace identity, nested references và mutation |
| “Java truyền object bằng tham chiếu.” | Java truyền **bản sao của giá trị tham chiếu**; đổi biến tham số không đổi biến caller | Thử cả gán lại tham số và sửa object |
| “Field `final` bảo đảm object immutable.” | Chỉ cố định field reference; collection bên trong vẫn sửa được | Immutable elements + defensive copy |
| “`@Async` clone request DTO trước khi chạy.” | Nó chuyển execution, không tự deep-copy input | Snapshot/ownership trước khi submit |
| “Trả `unmodifiableList` là snapshot.” | Wrapper có thể phản ánh thay đổi của backing list | Dùng `List.copyOf` hoặc deep snapshot khi cần |
| “`List.copyOf` đã copy mọi object lồng nhau.” | Chỉ tạo snapshot cấu trúc ngoài | Sao chép phần tử mutable hoặc dùng value object |
| “Bean singleton có method synchronized là đủ.” | Khóa từng method có thể không bảo vệ chuỗi nghiệp vụ và ownership bị rò | Bảo vệ invariant hoặc bỏ per-request field |
| “Bean prototype luôn mới cho mỗi lời gọi.” | Inject vào singleton thông thường được resolve lúc inject | Xem cách lấy bean/lifecycle thực tế |
| “`volatile` sửa mọi race.” | Visibility khác atomicity và invariant nhiều bước | Atomic, lock, immutable data hoặc message passing |
| “`Future.get()` làm object kết quả bất biến.” | Nó đồng bộ việc hoàn thành/quan sát kết quả, không cấm sửa về sau | Tạo immutable result, không giữ mutable alias |
| “Hai object bằng `equals` là cùng instance.” | Equality theo giá trị khác identity theo `==` | Quan sát từng identity; tránh nhầm trong log |

## 14. Bài thực hành tích hợp: truy tìm lỗi qua ba tầng Spring

Giả sử một `@RestController` nhận danh sách sản phẩm; một `@Service` nhận list, lưu vào field `lastItems`, tính tổng; một service khác trả `lastItems` để debug. Đồng thời một `@Async` method cũng dùng list này.

Hãy thực hiện các bước sau:

1. Vẽ object graph bắt đầu từ request body: DTO, list, từng item, field singleton, async lambda, result. Phân biệt **same reference**, **shallow copy**, **deep copy** tại mỗi cạnh.
2. Chỉ ra hai cách rò rỉ: input bị giữ ở singleton và return đưa backing list ra ngoài. Giải thích vì sao caller có thể sửa dữ liệu của request khác.
3. Viết phiên bản stateless: DTO immutable hoặc defensive copy, xử lý bằng local variables, result DTO mới; nếu cần audit thì lưu event bất biến trong store có đồng bộ và chỉ trả snapshot.
4. Tạo test làm đổi backing list sau khi gọi constructor để kiểm chứng input snapshot; tạo test làm đổi result (nếu được thiết kế mutable) để kiểm chứng không ảnh hưởng nội bộ.
5. Thêm một task `@Async`, sửa list gốc sau khi submit và trước khi task đọc bằng latch. Quan sát lỗi cũ, rồi thay bằng immutable snapshot để bảo đảm kết quả; không dùng `Thread.sleep` để tạo timing giả.
6. Viết bảng ownership cho từng object: owner, nơi sinh ra, ai mutate, nơi được trả ra, thời điểm hết vòng đời, có đồng bộ hay không. Giải thích tại sao chỉ đổi bean scope hoặc thêm `volatile` không đủ.

### Tiêu chí hoàn thành

- [ ] Giải thích đúng Java pass-by-value và nhận ra hai tham chiếu `==` trỏ cùng object.
- [ ] Truy được object mutable từ caller → tham số → field/callback/async → return.
- [ ] Phân biệt view, shallow snapshot, deep copy và immutable result.
- [ ] Chứng minh local variable không đủ kết luận về thread-safety của trạng thái reachable.
- [ ] Phát hiện per-request state bị giữ nhầm trong singleton bean.
- [ ] Biết vì sao `@Async` và `Future` không tự ngăn caller/task cùng sửa một DTO.
- [ ] Đề xuất API có ownership rõ, copy đúng boundary, xử lý context và concurrency có chủ đích.
- [ ] Dùng test có assertion và phối hợp bằng latch để tái tạo lỗi mà không đoán timing.

**Kết luận học tập:** để đánh giá một bean có chia sẻ trạng thái an toàn hay không, phải theo dõi **đối tượng và quyền sửa qua mọi đối số, giá trị trả về và ranh giới thread**, thay vì chỉ đếm field trong bean hoặc nhìn tên biến. Khi owner, lifetime và mutation được biểu diễn rõ, race condition và rò rỉ dữ liệu giữa request trở nên dễ giải thích, kiểm thử và phòng tránh.
