# Không lưu state nghiệp vụ mutable vào context chung

## 1. Vấn đề trong Java concurrency

Một ứng dụng Java có thể xử lý đồng thời nhiều yêu cầu: mỗi yêu cầu có người dùng, đơn hàng, số tiền, quyền thao tác và trạng thái xử lý khác nhau. **State nghiệp vụ mutable** là dữ liệu có thể thay đổi trong quá trình xử lý, chẳng hạn `currentOrder`, `cartItems`, `balance`, `discount` hoặc `currentUser`. Nếu nhiều tác vụ nhìn vào **cùng một đối tượng context có thể sửa**, chúng có thể ghi đè dữ liệu của nhau, khiến thao tác của yêu cầu A dùng nhầm dữ liệu yêu cầu B.

Đây là lỗi **ranh giới sở hữu state**: dữ liệu chỉ thuộc một request/tác vụ lại được đặt vào nơi mà nhiều request cùng đọc và sửa. Lỗi xảy ra với platform threads lẫn virtual threads; thêm `volatile`, `synchronized` hoặc `ConcurrentHashMap` không tự tạo ra sự tách biệt giữa các yêu cầu.

Trong chương **Ngữ cảnh luồng**, cần phân biệt:

- **Execution context**: dữ liệu kèm theo một lần thực thi, thường gồm request ID, correlation ID, actor/user ID, locale, trace context hoặc thông tin quan sát. Nên nhỏ, có phạm vi sống rõ ràng và ưu tiên bất biến.
- **Business state**: dữ liệu quyết định kết quả nghiệp vụ, chẳng hạn các dòng giỏ hàng, tồn kho, trạng thái chuyển tiền, trạng thái xử lý đơn. Nó cần chủ sở hữu, vòng đời và quy tắc cập nhật riêng.
- **Shared state**: dữ liệu nhiều tác vụ thực sự cần dùng chung, như cache được đồng bộ, bộ đếm hệ thống hoặc kho dữ liệu bền vững. Nếu mutable thì phải có giao thức cập nhật đảm bảo các bất biến nghiệp vụ.
- **Thread-local context**: một cách liên kết giá trị với thread hiện tại, không tự đảm bảo đối tượng bên trong bất biến, không tự biến dữ liệu thành tài sản của request, cũng không tự truyền dữ liệu sang mọi thread khác.

Nguyên tắc: **context truyền thông tin nhận diện và quan sát; state nghiệp vụ nằm trong tham số, kết quả, thực thể hoặc nơi lưu trữ được quản lý bằng quy tắc concurrency phù hợp**.

## 2. Thế nào là “context chung” gây rủi ro?

Các mẫu thiết kế dưới đây dễ biến thông tin theo request thành state toàn cục:

```java
// Ví dụ sai: tất cả tác vụ chia sẻ cùng một biến user.
static String currentUserId;

// Ví dụ sai: một map dùng cho mọi request.
static final java.util.Map<String, Object> CONTEXT =
        new java.util.concurrent.ConcurrentHashMap<>();

// Ví dụ sai: singleton chứa "đơn đang xử lý".
final class ProcessingContext {
    String currentOrderId;
    long currentAmount;
}
```

Ba đoạn trên chỉ minh họa anti-pattern, **không phải chương trình độc lập**. `ConcurrentHashMap` có thể bảo vệ tính an toàn của thao tác `put/get` trên chính map, nhưng không ngăn A gọi `put("currentUser", "alice")` rồi B ghi đè `"bob"`. Khi A đọc lần tiếp theo, map hoàn toàn nhất quán về mặt bộ nhớ nhưng giá trị thuộc request B. **Thread-safe container không có nghĩa là request-safe business data.**

Một ví dụ khác tưởng an toàn:

```java
static final ThreadLocal<java.util.Map<String, Object>> CTX =
        ThreadLocal.withInitial(java.util.HashMap::new);
```

Mỗi thread nhận một `HashMap` mặc định riêng, nhưng điều đó chỉ nói về **thread**, không phải request. Platform thread trong executor có thể chạy liên tiếp nhiều request; nếu quên xóa/khôi phục state, request sau nhận dữ liệu trước. Ngược lại, nếu ai đó lấy `CTX.get()` rồi truyền tham chiếu map ấy sang một task khác, hai thread có thể cùng sửa **chính một map**. `ThreadLocal` không sao chép hay tự bảo vệ đối tượng được lưu.

## 3. Ví dụ Java 21+: cùng một context làm hai yêu cầu nhiễm dữ liệu

Chương trình độc lập dưới đây ép thứ tự để lỗi xuất hiện **xác định**, không phụ thuộc may rủi của race condition. Hai virtual threads cùng dùng một map toàn cục. Request Alice ghi `alice` rồi chờ Bob ghi `bob`; khi Alice đọc lại, dữ liệu đã bị ghi đè.

Lưu thành `SharedContextPitfall.java`:

```java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class SharedContextPitfall {
    private static final Map<String, String> SHARED =
            new ConcurrentHashMap<>();

    // Snapshot metadata bất biến của từng request.
    private record RequestContext(String requestId, String userId) {}

    private static String process(RequestContext context) {
        // Không đọc "currentUser" từ một biến toàn cục.
        return context.userId();
    }

    public static void main(String[] args) throws Exception {
        CountDownLatch alicePublished = new CountDownLatch(1);
        CountDownLatch bobPublished = new CountDownLatch(1);

        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            Future<String> aliceWrong = executor.submit(() -> {
                SHARED.put("currentUser", "alice");
                alicePublished.countDown();
                bobPublished.await();
                return SHARED.get("currentUser");
            });

            Future<String> bobWrong = executor.submit(() -> {
                alicePublished.await();
                SHARED.put("currentUser", "bob");
                bobPublished.countDown();
                return SHARED.get("currentUser");
            });

            // Hai kết quả sau phản ánh cùng một context dùng chung.
            System.out.println("shared alice=" + aliceWrong.get());
            System.out.println("shared bob=" + bobWrong.get());

            RequestContext alice = new RequestContext("A", "alice");
            RequestContext bob = new RequestContext("B", "bob");

            Future<String> aliceSafe =
                    executor.submit(() -> process(alice));
            Future<String> bobSafe =
                    executor.submit(() -> process(bob));

            System.out.println("isolated A=" + aliceSafe.get());
            System.out.println("isolated B=" + bobSafe.get());
        }
    }
}
```

Biên dịch và chạy với **JDK 21+**:

```bash
javac SharedContextPitfall.java
java SharedContextPitfall
```

Kết quả chính xác:

```text
shared alice=bob
shared bob=bob
isolated A=alice
isolated B=bob
```

Giải thích:

1. `SHARED` là một `ConcurrentHashMap` đúng chuẩn và từng thao tác `put/get` hợp lệ.
2. Hai request vẫn sai về nghiệp vụ vì cả hai dùng **một khóa “currentUser” có phạm vi toàn process**.
3. `CountDownLatch` buộc Alice chờ đến khi Bob đã ghi; do đó lỗi tái hiện ổn định.
4. Phiên bản đúng tạo **hai `RequestContext` riêng**, được truyền tường minh vào hàm xử lý. Việc thực thi trên virtual threads không làm thay đổi logic.
5. `Future.get()` đợi task hoàn tất và giúp lỗi trong task được báo về caller. `try-with-resources` đóng executor đúng vòng đời.

Đừng diễn giải ví dụ thành “mọi map chia sẻ đều sai”. Một cache hoặc index có thể chia sẻ an toàn khi được thiết kế để dùng chung; vấn đề là lưu **giá trị riêng của một yêu cầu dưới tên toàn cục duy nhất** rồi coi đó là context hiện tại cho tất cả tác vụ.

## 4. ThreadLocal: giá trị theo thread không phải state theo request

`ThreadLocal<T>` giữ một ô giá trị cho **mỗi thread**. Hai thread khác nhau gọi `get()` trên cùng đối tượng `ThreadLocal` sẽ truy cập hai ô riêng. Tuy vậy:

- **Platform-thread pool tái sử dụng thread**: request A kết thúc nhưng thread không chết; nếu không xóa state, request B chạy trên thread ấy có thể đọc giá trị còn sót.
- **Chuyển việc sang thread mới**: `ThreadLocal` thường không tự truyền sang thread được tạo hoặc task trong executor. Phần code chạy ở thread khác có thể thấy `null`/default value.
- **Đối tượng mutable được lưu**: `ThreadLocal` chỉ cô lập *slot* của từng thread; nếu hai slot đều trỏ tới một đối tượng do code tự chia sẻ, đối tượng vẫn có alias và race.
- **Virtual threads**: cũng hỗ trợ `ThreadLocal`, nhưng thường có một virtual thread cho một tác vụ, không nên tạo pool virtual threads. Nhiều virtual threads cùng giữ payload lớn trong thread-local làm tiêu tốn bộ nhớ đáng kể; không dùng thread-local để cache đối tượng đắt tiền trên mỗi virtual thread.

### Ví dụ: request sau đọc nhầm dữ liệu request trước

Lưu file `ThreadLocalCleanupDemo.java`:

```java
import java.util.concurrent.Executors;

public class ThreadLocalCleanupDemo {
    private static final ThreadLocal<String> USER = new ThreadLocal<>();

    public static void main(String[] args) throws Exception {
        // Một platform worker tái sử dụng cho ba task.
        try (var executor = Executors.newSingleThreadExecutor()) {
            String first = executor.submit(() -> {
                USER.set("alice");
                return USER.get(); // Cố ý không remove(): minh họa lỗi.
            }).get();

            String leaked = executor.submit(() -> {
                String value = USER.get(); // Nhìn thấy "alice" từ task 1.
                USER.remove();            // Dọn sạch để quan sát task 3.
                return value;
            }).get();

            String cleared = executor.submit(
                    () -> String.valueOf(USER.get())).get();

            System.out.println("task1=" + first);
            System.out.println("task2=" + leaked);
            System.out.println("task3=" + cleared);
        }
    }
}
```

Chạy bằng JDK 21+:

```bash
javac ThreadLocalCleanupDemo.java
java ThreadLocalCleanupDemo
```

```text
task1=alice
task2=alice
task3=null
```

`newSingleThreadExecutor()` đảm bảo các tác vụ được thực thi lần lượt bởi một worker, vì vậy việc request thứ hai nhìn thấy dữ liệu request trước là điều được chủ động minh họa. Ví dụ **cố ý chứa lỗi ở task 1**; tuyệt đối không áp dụng cách quên cleanup này trong code vận hành.

Nếu vì tương thích thư viện bạn buộc phải dùng thread-local để đặt metadata ngắn hạn, hãy khoanh vòng đời:

```java
// Đoạn minh họa trong phương thức xử lý:
USER.set(userId);
try {
    processRequest();
} finally {
    USER.remove();
}
```

Trong ví dụ này, `USER`, `userId` và `processRequest()` phải được định nghĩa bởi ứng dụng; **đây là snippet, không phải chương trình chạy độc lập**. Khi có khả năng đã có binding trước đó trong cùng luồng gọi, việc thay một binding cũ bằng binding mới rồi `remove()` có thể làm mất binding của outer scope; hãy thiết kế người sở hữu context và quy tắc khôi phục giá trị trước đó thật rõ. Cách tốt nhất vẫn là dùng tham số tường minh nếu có thể.

## 5. InheritableThreadLocal không biến context mutable thành bản sao độc lập

`InheritableThreadLocal<T>` có thể truyền **giá trị ban đầu** từ thread cha sang thread con tại thời điểm tạo thread. Mặc định, phương thức `childValue(parentValue)` trả lại **chính tham chiếu** của cha. Ví dụ:

```java
import java.util.ArrayList;
import java.util.List;

InheritableThreadLocal<List<String>> tags = new InheritableThreadLocal<>();
List<String> sharedTags = new ArrayList<>();
tags.set(sharedTags);

Thread child = Thread.ofVirtual().start(() -> {
    tags.get().add("child");
});
child.join();

System.out.println(sharedTags); // [child]
tags.remove();
```

Đoạn trên là **snippet** dùng các câu lệnh trong một phương thức; chạy độc lập cần bọc trong lớp và `main`. Nó cho thấy cha và con cùng giữ tham chiếu `ArrayList`, nên sửa từ con tác động tới đối tượng mà cha nhìn thấy. Ví dụ chủ động dùng `join()` để tránh đọc đồng thời `ArrayList` chưa đồng bộ. Nếu hai thread sửa đồng thời, đó còn là **data race**.

Không dựa vào tính kế thừa để truyền mutable business state; sử dụng thông điệp/bản sao snapshot riêng hoặc tham số bất biến. Khi tạo thread, một số `Thread.Builder` cho phép `inheritInheritableThreadLocals(false)`; tuy nhiên điều đó chỉ tắt kế thừa, **không giải quyết bài toán sở hữu dữ liệu**.

## 6. Record, final, unmodifiable không tự động tạo deep immutability

Cách thuận tiện để mang metadata theo request là tạo một value object bất biến:

```java
record RequestContext(
        String requestId,
        String userId,
        String traceId
) {}
```

`String` bất biến và các trường của `record` là `final`, nên với các thành phần trên context phù hợp để chia sẻ đọc mà không lo một tác vụ đổi trường `userId` sau khi được tạo. Nhưng **record chỉ bất biến ở tham chiếu trường**, không tự sao chép sâu đối tượng bên trong:

```java
record CartContext(java.util.List<String> productIds) {}

var products = new java.util.ArrayList<String>();
products.add("book");
var context = new CartContext(products);
products.add("laptop"); // context.productIds() cũng nhìn thấy laptop.
```

Nếu metadata cần chứa collection, tạo **snapshot** bằng `List.copyOf` / `Map.copyOf` / `Set.copyOf`, đồng thời cân nhắc sao chép sâu các phần tử mutable:

```java
import java.util.List;
import java.util.Objects;

record SafeContext(String requestId, List<String> roles) {
    SafeContext {
        Objects.requireNonNull(requestId);
        roles = List.copyOf(Objects.requireNonNull(roles));
    }
}
```

Đây là đoạn khai báo có thể đặt trong một file Java phù hợp; không có `main` riêng. `List.copyOf` tạo danh sách không thể sửa qua API danh sách và tách khỏi việc thay đổi cấu trúc danh sách đầu vào; ở đây phần tử là `String` bất biến. Với `List<MutableOrder>`, danh sách không sửa được **vẫn có thể chứa các `MutableOrder` bị sửa bên trong**. Không lưu những entity mutable đó trong context chỉ vì đã bọc chúng trong một list “immutable”.

Cũng đừng nhầm `final Map<K,V>` với map bất biến: `final` ngăn gán lại biến/tham chiếu, nhưng không ngăn `map.put(...)`.

## 7. Chọn cách truyền dữ liệu: explicit parameter, ThreadLocal, ScopedValue

| Nhu cầu | Cách phù hợp | Điều cần tránh |
| --- | --- | --- |
| Tính phí đơn hàng theo dữ liệu request | Tham số `OrderInput`/`OrderSnapshot`, kết quả trả về rõ ràng | Cất `currentOrder` mutable vào global/shared context |
| Chuyển request ID/user ID qua nhiều method | Tham số tường minh; có thể dùng `ThreadLocal` hoặc `ScopedValue` cho metadata cần truyền ngầm | Mở rộng context thành “túi” chứa mọi entity nghiệp vụ |
| Gọi tác vụ ở executor khác | Capture context bất biến và đưa vào `Runnable`/`Callable`/tham số | Giả định `ThreadLocal` tự đi theo task |
| Nhiều tác vụ cùng cập nhật tồn kho | Nơi sở hữu state và giao thức cập nhật nguyên tử/transaction thích hợp | `Map<String,Object>` chung với thao tác check-then-act không được bảo vệ |
| Chia sẻ cache đọc | Cache được thiết kế concurrent, key/value an toàn, chính sách hết hạn | Cache chứa đối tượng mutable mà caller tự sửa |
| Logging/correlation trong một call stack | ID ngắn, bất biến, vòng đời rõ ràng | Giữ request body/connection/đối tượng lớn trong thread-local |

### ScopedValue trên Java 25+

`ScopedValue<T>` trở thành API ổn định ở **JDK 25** (được giới thiệu dạng preview từ JDK 21). Nó cung cấp **binding theo phạm vi thực thi**, phù hợp cho dữ liệu chỉ đọc truyền qua nhiều hàm, đặc biệt khi kết hợp với cấu trúc tác vụ con được hỗ trợ. Khác với `ThreadLocal.set` có thể thay đổi binding từ code bất kỳ, code bên trong phạm vi thường chỉ đọc binding hiện tại, rồi binding tự kết thúc khi rời scope.

```java
// Snippet JDK 25+, không phải chương trình độc lập.
record RequestMetadata(String requestId, String actorId) {}

private static final ScopedValue<RequestMetadata> CURRENT =
        ScopedValue.newInstance();

static void execute(RequestMetadata metadata) {
    ScopedValue.where(CURRENT, metadata).run(() -> {
        audit(CURRENT.get().requestId());
    });
}
```

`audit(...)` là hàm do ứng dụng định nghĩa; đây là **snippet** minh họa. Code `ScopedValue` ổn định nói trên không biên dịch trực tiếp trên JDK 21 nếu không dùng đúng preview API và các cờ preview của phiên bản đó.

**Điểm cốt lõi:** binding của `ScopedValue` có vòng đời được kiểm soát, nhưng nó vẫn giữ **tham chiếu tới một object**. Nếu bạn bind một `HashMap`, `ArrayList`, `Order` mutable, các code được phép truy cập có thể vẫn sửa object đó. “Scoped” không đồng nghĩa “deep immutable”. Chỉ gắn metadata bất biến, nhỏ gọn, thực sự phù hợp với luồng thực thi.

Một binding `ScopedValue` cũng không tự động truyền sang **mọi** tác vụ executor độc lập. Khả năng kế thừa ở các tác vụ con có cấu trúc phải tuân theo API/cơ chế task scope của đúng JDK đang chạy. Qua ranh giới thread/process hoặc message queue thông thường, hãy chuyển metadata có chủ đích.

## 8. State nghiệp vụ nên sống ở đâu?

Quyết định theo **chủ sở hữu dữ liệu** và **thời điểm cần cập nhật**, thay vì theo thread hiện đang chạy.

### 8.1. State chỉ cần trong một tác vụ

Sử dụng tham số, biến cục bộ, object sống trong phạm vi tác vụ và kết quả trả về. Ví dụ:

```java
record OrderInput(String orderId, long subtotal, long discount) {}
record OrderResult(String orderId, long payable) {}

static OrderResult calculate(OrderInput input) {
    if (input.subtotal() < 0 || input.discount() < 0 ||
            input.discount() > input.subtotal()) {
        throw new IllegalArgumentException("invalid amount");
    }
    return new OrderResult(
            input.orderId(),
            input.subtotal() - input.discount());
}
```

Đây là đoạn khai báo minh họa, có thể nằm trong một lớp Java thích hợp. Các biến và kết quả thuộc một lời gọi `calculate`, không bị request khác sửa thông qua biến `currentAmount` toàn cục. Ví dụ dùng `long` đơn vị tiền nhỏ nhất đã được quy ước; bài này tập trung vào concurrency, không bàn quy tắc tiền tệ đa loại.

### 8.2. State cần nhiều tác vụ cùng cập nhật

Lúc này **có shared mutable state thật**. Chuyển state vào object sở hữu rõ ràng, kho dữ liệu/transaction, mailbox/actor hoặc cấu trúc concurrent có invariant được bảo vệ. Ví dụ “chỉ còn một sản phẩm” cần thao tác kiểm tra và trừ tồn kho là **một bước logic nguyên tử**: đơn thuần `ConcurrentHashMap.get` rồi `put` không đủ nếu nhiều tác vụ cùng mua.

`AtomicInteger` phù hợp với bộ đếm đơn giản; `ConcurrentHashMap.compute(...)` có thể hỗ trợ cập nhật một key với quy tắc nhất quán phù hợp, nhưng không tự cung cấp transaction xuyên nhiều key/DB. Khi nghiệp vụ trải qua database hoặc hệ thống ngoài, cần cơ chế nhất quán tương ứng ở nơi quản lý dữ liệu. Không đặt một `synchronized` lên “request context” rồi cho rằng đã bảo vệ toàn bộ giao dịch phân tán.

### 8.3. State dùng chung nhưng chỉ đọc

Có thể chia sẻ cấu hình bất biến, danh mục/lookup bất biến, formatter thread-safe (ví dụ `java.time.format.DateTimeFormatter`) hoặc snapshot sau khi xây dựng xong. Phải công bố đối tượng an toàn và không expose reference tới các thành phần mutable để bên dùng sửa.

Trong Java, **an toàn xuất bản (safe publication)** và **bất biến thực sự** là hai vấn đề bổ trợ: một object được publish an toàn nhưng vẫn mutable thì các sửa đổi đồng thời tiếp theo vẫn cần đồng bộ.

## 9. Cách nhận diện và sửa lỗi trong codebase

Khi thấy class dạng `RequestContextHolder`, `UserContext`, `ProcessingContext` hoặc utility static, kiểm tra kỹ:

1. Có trường `static`/singleton nào mang tên `currentUser`, `currentOrder`, `pendingPayment`, `cart`, `amount`, `transactionState` không?
2. Context có chứa `Map<String,Object>`, `List`, entity hoặc DTO mutable được expose trực tiếp qua getter không?
3. Có `ThreadLocal.set(...)` nhưng thiếu `remove()` trong `finally` không? Có code xóa ở nhiều chỗ khiến khó xác định owner không?
4. Có method nhận context nhưng âm thầm sửa nó, khiến thứ tự gọi method làm thay đổi kết quả không?
5. Có tạo child thread, executor task, `CompletableFuture` hoặc virtual thread mới rồi kỳ vọng thấy cùng thread-local mà không truyền dữ liệu không?
6. Có log theo `requestId` để đối chiếu xem một xử lý đã truy cập sai `userId/orderId` của yêu cầu khác không?
7. Có quy tắc nghiệp vụ đòi hỏi cập nhật nguyên tử nhưng implementation chỉ khóa từng thao tác riêng lẻ trên collection không?

Quy trình refactor có kiểm soát:

- **Bước 1:** Phân loại field: metadata bất biến theo request, business data trong request, shared domain state hay resource holder.
- **Bước 2:** Với business data theo request, đưa vào tham số hoặc object riêng cho tác vụ, có quyền sửa và vòng đời rõ ràng; tốt nhất truyền snapshot bất biến giữa các tác vụ.
- **Bước 3:** Với shared domain state, thiết kế owner và atomicity/transaction ở đúng cấp; kiểm tra invariant dưới tải đồng thời.
- **Bước 4:** Với metadata thực sự cần truyền ngầm, giữ phạm vi nhỏ, ràng buộc cleanup/binding; tránh mang theo mutable domain objects.
- **Bước 5:** Thử nhiều yêu cầu với actor và dữ liệu khác nhau chạy đồng thời, tái sử dụng platform pool, có lỗi/timeout/cancel và có nhánh tạo thread mới.

### Kiểm thử quan trọng hơn “cứ chạy nhiều lần”

Việc chạy 1.000 lần có thể vẫn không tái hiện lỗi do timing. Hãy dùng `CountDownLatch`/`CyclicBarrier` để **ép interleaving có chủ đích**, như ví dụ ở mục 3, rồi assert rằng kết quả mỗi request khớp input của nó. Thêm trường hợp exception và cancel để bảo đảm cleanup trong `finally`. Với domain state chung, xác minh invariant cuối cùng: tổng số hàng đã bán không vượt tồn kho, tiền chuyển không mất/nhân đôi, trạng thái không đảo trái phép.

## 10. Những ngộ nhận thường gặp

**“Dùng ConcurrentHashMap là xong.”** Collection thread-safe giữ đúng thao tác container, nhưng không sửa lỗi hai request cùng truy cập khóa `currentUser` hoặc quy tắc check-then-act bị tách rời.

**“Mỗi thread có ThreadLocal nên mỗi request có dữ liệu riêng.”** Sai khi một platform thread chạy nhiều request kế tiếp hoặc code đã chia sẻ reference mutable. `ThreadLocal` cô lập theo thread, không đảm bảo scope nghiệp vụ.

**“InheritableThreadLocal tự copy dữ liệu cho child thread.”** Mặc định nó có thể truyền cùng tham chiếu object. Copy reference không phải deep copy.

**“Record/final đã làm mọi thứ immutable.”** Trường tham chiếu không gán lại được nhưng object/list bên trong vẫn mutable nếu không tạo snapshot phù hợp.

**“ScopedValue sẽ bảo vệ mọi state.”** ScopedValue giới hạn vòng đời của *binding*, không biến object được bind thành immutable và không tạo transaction cho dữ liệu nghiệp vụ.

**“Chuyển sang virtual threads sẽ hết lẫn context.”** Virtual threads giúp mô hình một thread cho một task nhưng không sửa shared static holder, mutable alias hay lỗi ownership. Cũng không nên cache đối tượng lớn trong một `ThreadLocal` cho mỗi virtual thread.

**“Dùng synchronized trên tất cả access là đủ.”** Đồng bộ có thể tránh race ở mức bytecode nhưng vẫn cho request A đọc state của B theo đúng thứ tự khóa; còn có thể tạo contention và giảm throughput. Trước tiên phải thiết kế đúng scope.

**“Context tiện nên truyền cả entity để khỏi thêm parameter.”** Khi một entity mutable được gắn vào ambient context, các hàm ẩn phụ thuộc vào nó, khó test, khó quan sát đường sửa đổi, dễ lộ dữ liệu chéo request. Hãy làm dependency và ownership rõ ràng.

## 11. Checklist thiết kế và vận hành

- [ ] Context giữ **metadata nhỏ và đủ dùng**: request/correlation ID, actor ID, trace ID; không chứa mutable order/cart/payment.
- [ ] Mỗi request/tác vụ có snapshot input riêng; phép xử lý có tham số và kết quả rõ ràng.
- [ ] Không có singleton/static “current business object” cho mọi tác vụ đồng thời.
- [ ] Không expose trực tiếp collection/DTO mutable qua context; đã xét deep immutability.
- [ ] Nếu bắt buộc dùng ThreadLocal, mỗi binding có owner, vòng đời, `finally/remove` hoặc quy tắc restore rõ ràng.
- [ ] Các ranh giới executor/virtual thread/async đã truyền context phù hợp, không giả định thread-local tự theo task.
- [ ] Shared domain state có atomicity/invariant/transaction đúng mức.
- [ ] Có bài test ép interleaving và kiểm tra không lẫn actor, request, order; có test cleanup khi exception.
- [ ] Có metric/log theo request ID để phát hiện bất thường, nhưng không log mật khẩu, token hoặc dữ liệu nhạy cảm không cần thiết.

## Kết luận

**Context của thread là phương tiện giúp code biết mình đang xử lý việc gì; nó không phải kho lưu state nghiệp vụ mutable dùng chung.** Với Java concurrency, phòng tránh nhiễm dữ liệu bằng cách xác định chủ sở hữu từng state, truyền dữ liệu request tường minh hoặc qua metadata bất biến có scope rõ ràng, và dùng cơ chế đồng bộ/transaction khi thực sự cần nhiều tác vụ cập nhật chung một domain state. `ThreadLocal`, `InheritableThreadLocal` và `ScopedValue` đều có phạm vi sử dụng riêng; không cái nào thay thế thiết kế ownership đúng.

## Tài liệu tham khảo

1. Oracle, [ThreadLocal — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ThreadLocal.html): giá trị theo thread, vòng đời và `remove()`.
2. Oracle, [InheritableThreadLocal — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/InheritableThreadLocal.html): giá trị kế thừa và `childValue`.
3. Oracle, [Virtual Threads — Java SE 21](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): một thread cho mỗi task, cảnh báo về caching trong thread-local.
4. Oracle, [ScopedValue — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.html): binding theo scope và giới hạn khi truyền object mutable.
5. OpenJDK, [JEP 506: Scoped Values](https://openjdk.org/jeps/506): ổn định API trong JDK 25.
