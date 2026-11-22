# `newIncompleteFuture` và `defaultExecutor` khi mở rộng lớp

Từ Java 9, `CompletableFuture` cung cấp hai phương thức có thể override để lớp con kiểm soát cách các stage phụ thuộc được tạo ra và cách các tác vụ bất đồng bộ được lập lịch: `newIncompleteFuture()` và `defaultExecutor()`. Hai hook này giải quyết hai vấn đề khác nhau. Một hook quyết định **kiểu đối tượng của stage mới**; hook còn lại quyết định **executor mặc định cho các phương thức async không truyền executor riêng**.

Khi xây dựng một subclass có cấu hình riêng, chẳng hạn một executor chuyên dụng hoặc metadata đi kèm future, thường cần override cả hai. Nếu chỉ override một phương thức, chuỗi stage có thể mất kiểu subclass hoặc chuyển sang executor mặc định của `CompletableFuture` ở một bước tiếp theo.

## 1. Bối cảnh: `CompletableFuture` tạo ra nhiều stage

`CompletableFuture<T>` vừa là `Future<T>` có thể hoàn tất, vừa triển khai `CompletionStage<T>`. Các phương thức như `thenApply`, `thenCompose`, `handle` và `whenComplete` tạo ra stage phụ thuộc để biểu diễn bước xử lý tiếp theo.

Ví dụ:

```java
CompletableFuture<String> result = CompletableFuture
    .supplyAsync(() -> 21)
    .thenApply(value -> value * 2)
    .thenApply(Object::toString);
```

Mỗi bước trả về một future mới. Nếu ứng dụng mở rộng `CompletableFuture` thành một lớp riêng nhưng các bước tiếp theo lại trở về kiểu `CompletableFuture` cơ sở, cấu hình hoặc hành vi riêng của lớp con có thể không còn được duy trì trong toàn bộ chuỗi.

Java 9 cung cấp `newIncompleteFuture()` để lớp con kiểm soát việc tạo stage mới. `defaultExecutor()` cho phép lớp con chọn executor dùng bởi các phương thức async không nhận tham số executor.

## 2. `newIncompleteFuture()` — giữ kiểu lớp con cho stage mới

Chữ ký:

```java
public <U> CompletableFuture<U> newIncompleteFuture()
```

Phương thức này tạo một `CompletableFuture<U>` mới ở trạng thái chưa hoàn tất. Các phương thức instance của `CompletionStage` cần tạo stage phụ thuộc sử dụng hook này để lấy đối tượng kết quả.

Triển khai mặc định của `CompletableFuture` tạo một `CompletableFuture` cơ sở. Lớp con có thể override để trả về một instance của chính lớp con, nhờ đó các thao tác tiếp theo tiếp tục sử dụng implementation mở rộng.

Ví dụ tối giản:

```java
class AppFuture<T> extends CompletableFuture<T> {
    @Override
    public <U> CompletableFuture<U> newIncompleteFuture() {
        return new AppFuture<U>();
    }
}
```

Khi gọi:

```java
AppFuture<Integer> source = new AppFuture<>();
CompletableFuture<String> next = source.thenApply(Object::toString);
```

`next` được tạo thông qua `newIncompleteFuture()`, vì vậy nó cũng là một `AppFuture`. Kiểu biến khai báo vẫn có thể là `CompletableFuture<String>`, nhưng object thực tế giữ implementation của lớp con.

### Vì sao phải trả về một future chưa hoàn tất?

`newIncompleteFuture()` cung cấp container cho kết quả của một stage mới. Chính logic của thao tác như `thenApply` hoặc `thenCompose` sẽ hoàn tất container đó khi điều kiện phụ thuộc được thỏa mãn.

Không trả về `this`, một future đã hoàn tất hoặc một future đang được dùng chung cho nhiều stage. Mỗi dependent stage cần một kết quả độc lập; dùng chung object có thể làm các nhánh ghi đè hoặc quan sát cùng một completion ngoài ý muốn.

### Mang cấu hình của lớp con sang stage mới

Nếu subclass chứa cấu hình bất biến như executor, trace context hoặc chính sách xử lý, override nên chuyển cấu hình cần thiết sang instance mới:

```java
class AppFuture<T> extends CompletableFuture<T> {
    private final Executor executor;

    AppFuture(Executor executor) {
        this.executor = Objects.requireNonNull(executor, "executor");
    }

    @Override
    public <U> CompletableFuture<U> newIncompleteFuture() {
        return new AppFuture<U>(executor);
    }
}
```

Ví dụ này giữ cùng executor cho stage mới. Nếu subclass có thêm cấu hình khác, hãy xác định rõ cấu hình nào cần được kế thừa và truyền nó qua constructor. Tránh tạo executor mới bên trong mỗi lần gọi hook vì một chuỗi dài có thể tạo ra rất nhiều stage.

## 3. `defaultExecutor()` — chọn executor cho các phương thức async

Chữ ký:

```java
public Executor defaultExecutor()
```

Phương thức trả về executor mặc định được dùng bởi các phương thức bất đồng bộ không nhận executor riêng. `CompletableFuture` cơ sở sử dụng `ForkJoinPool.commonPool()` khi common pool hỗ trợ parallelism ít nhất là hai; nếu không, nó dùng executor tạo thread mới cho mỗi tác vụ. Lớp con có thể override để chọn executor khác.

Ví dụ:

```java
class AppFuture<T> extends CompletableFuture<T> {
    private final Executor executor;

    AppFuture(Executor executor) {
        this.executor = Objects.requireNonNull(executor, "executor");
    }

    @Override
    public Executor defaultExecutor() {
        return executor;
    }
}
```

Khi gọi một phương thức như `thenApplyAsync(function)` trên instance này, tác vụ async dùng executor do `defaultExecutor()` trả về.

### Những phương thức nào sử dụng executor mặc định?

Các phương thức async không truyền executor, ví dụ:

- `thenApplyAsync(...)`
- `thenAcceptAsync(...)`
- `thenRunAsync(...)`
- `thenCombineAsync(...)`
- `thenComposeAsync(...)`
- `handleAsync(...)`
- `whenCompleteAsync(...)`
- `exceptionallyAsync(...)` trong các phiên bản Java có cung cấp phương thức này.

Phương thức đồng bộ như `thenApply(...)`, `thenCompose(...)` hoặc `whenComplete(...)` không được lập lịch thông qua `defaultExecutor()`. Hành động đồng bộ có thể chạy trên thread hoàn tất stage trước hoặc thread kích hoạt việc đăng ký khi stage đã hoàn tất; không nên dựa vào một thread cụ thể.

### Khi truyền executor tường minh

Overload có tham số executor sử dụng executor được truyền vào:

```java
CompletableFuture<String> result = source.thenApplyAsync(
    Object::toString,
    dedicatedExecutor
);
```

Trong trường hợp này, `dedicatedExecutor` quyết định nơi thực thi callback. `defaultExecutor()` không thay thế executor được truyền tường minh.

## 4. Phân biệt trách nhiệm của hai hook

| Hook | Quyết định | Không quyết định |
| --- | --- | --- |
| `newIncompleteFuture()` | Implementation/kiểu object của dependent future mới | Thread chạy callback |
| `defaultExecutor()` | Executor mặc định cho phương thức async không truyền executor | Kiểu object của dependent future |

Hai hook bổ sung cho nhau:

1. Override `newIncompleteFuture()` để các stage mới tiếp tục là instance của subclass.
2. Override `defaultExecutor()` để các lời gọi async không truyền executor dùng đúng executor đã cấu hình.
3. Khi stage mới tiếp tục tạo stage khác, hook của subclass vẫn có thể giữ cả kiểu object và cấu hình executor trong chuỗi.

Nếu chỉ override `defaultExecutor()`, một async callback có thể chạy đúng executor nhưng future kết quả vẫn là `CompletableFuture` cơ sở theo triển khai mặc định của `newIncompleteFuture()`. Những stage tiếp theo trên future cơ sở đó có thể dùng common pool thay vì executor tùy chỉnh.

Nếu chỉ override `newIncompleteFuture()`, kiểu subclass được giữ lại, nhưng các phương thức async không truyền executor vẫn dùng chính sách executor mặc định của lớp cơ sở trừ khi lớp con override `defaultExecutor()`.

## 5. Ví dụ subclass kết hợp cả hai phương thức

Ví dụ sau tạo `RoutedFuture<T>`. Mọi dependent stage mới tiếp tục là `RoutedFuture`, đồng thời các phương thức async không truyền executor sử dụng executor được truyền vào constructor.

```java
import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;

class RoutedFuture<T> extends CompletableFuture<T> {
    private final Executor executor;

    RoutedFuture(Executor executor) {
        this.executor = Objects.requireNonNull(executor, "executor");
    }

    @Override
    public <U> CompletableFuture<U> newIncompleteFuture() {
        return new RoutedFuture<U>(executor);
    }

    @Override
    public Executor defaultExecutor() {
        return executor;
    }
}
```

Sử dụng:

```java
Executor executor = Executors.newFixedThreadPool(4);
RoutedFuture<Integer> source = new RoutedFuture<>(executor);

CompletableFuture<String> result = source
    .thenApply(value -> value + 1)
    .thenApplyAsync(Object::toString);

source.complete(41);
System.out.println(result.join());
```

Kết quả:

```text
42
```

Stage được tạo từ `thenApply` vẫn là `RoutedFuture`; lời gọi `thenApplyAsync` tiếp theo trên stage đó tiếp tục dùng executor mặc định đã cấu hình. Trong ứng dụng thật, executor cần được quản lý vòng đời rõ ràng và shutdown khi chủ sở hữu không còn cần dùng.

## 6. Chương trình hoàn chỉnh kiểm tra kiểu stage và thread thực thi

Chương trình dưới đây kiểm tra bốn điều:

1. Stage đồng bộ giữ kiểu subclass.
2. Stage async không truyền executor giữ kiểu subclass và chạy trên executor mặc định tùy chỉnh.
3. Stage async có executor tường minh vẫn giữ kiểu subclass nhưng chạy trên executor tường minh đó.
4. Một chuỗi stage tiếp tục giữ executor mặc định sau khi đi qua dependent stage trung gian.

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicReference;

public class Main {
    public static void main(String[] args) {
        ExecutorService defaultPool = Executors.newSingleThreadExecutor(
            task -> new Thread(task, "routed-default"));
        ExecutorService explicitPool = Executors.newSingleThreadExecutor(
            task -> new Thread(task, "routed-explicit"));

        try {
            RoutedFuture<Integer> source = new RoutedFuture<>(defaultPool);
            AtomicReference<String> syncThread = new AtomicReference<>();
            AtomicReference<String> defaultAsyncThread = new AtomicReference<>();
            AtomicReference<String> explicitAsyncThread = new AtomicReference<>();
            AtomicReference<String> chainedAsyncThread = new AtomicReference<>();

            CompletableFuture<String> syncStage = source.thenApply(value -> {
                syncThread.set(Thread.currentThread().getName());
                return "sync-" + value;
            });

            CompletableFuture<String> defaultAsyncStage = source.thenApplyAsync(value -> {
                defaultAsyncThread.set(Thread.currentThread().getName());
                return "async-" + value;
            });

            CompletableFuture<String> explicitAsyncStage = source.thenApplyAsync(value -> {
                explicitAsyncThread.set(Thread.currentThread().getName());
                return "explicit-" + value;
            }, explicitPool);

            CompletableFuture<Integer> intermediate = source.thenApply(value -> value + 1);
            CompletableFuture<String> chainedAsyncStage = intermediate.thenApplyAsync(value -> {
                chainedAsyncThread.set(Thread.currentThread().getName());
                return "chain-" + (value * 2);
            });

            check(syncStage instanceof RoutedFuture<?>, "sync stage subtype");
            check(defaultAsyncStage instanceof RoutedFuture<?>, "default async stage subtype");
            check(explicitAsyncStage instanceof RoutedFuture<?>, "explicit async stage subtype");
            check(intermediate instanceof RoutedFuture<?>, "intermediate stage subtype");
            check(chainedAsyncStage instanceof RoutedFuture<?>, "chained stage subtype");

            source.complete(7);

            check("sync-7".equals(syncStage.join()), "sync result");
            check("async-7".equals(defaultAsyncStage.join()), "default async result");
            check("explicit-7".equals(explicitAsyncStage.join()), "explicit async result");
            check("chain-16".equals(chainedAsyncStage.join()), "chained async result");

            check("main".equals(syncThread.get()), "synchronous callback thread");
            check("routed-default".equals(defaultAsyncThread.get()), "default executor routing");
            check("routed-explicit".equals(explicitAsyncThread.get()), "explicit executor routing");
            check("routed-default".equals(chainedAsyncThread.get()), "chained default executor routing");

            System.out.println("dependent stages preserve subclass: true");
            System.out.println("sync callback thread: " + syncThread.get());
            System.out.println("default async callback thread: " + defaultAsyncThread.get());
            System.out.println("explicit async callback thread: " + explicitAsyncThread.get());
            System.out.println("chained default async callback thread: " + chainedAsyncThread.get());
            System.out.println("all stage results: sync-7, async-7, explicit-7, chain-16");
        } finally {
            defaultPool.shutdownNow();
            explicitPool.shutdownNow();
        }
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static final class RoutedFuture<T> extends CompletableFuture<T> {
        private final Executor executor;

        RoutedFuture(Executor executor) {
            this.executor = executor;
        }

        @Override
        public <U> CompletableFuture<U> newIncompleteFuture() {
            return new RoutedFuture<>(executor);
        }

        @Override
        public Executor defaultExecutor() {
            return executor;
        }
    }
}
```

Lưu thành `Main.java`, biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 -Xlint:all Main.java
java Main
```

Stdout chính xác:

```text
dependent stages preserve subclass: true
sync callback thread: main
default async callback thread: routed-default
explicit async callback thread: routed-explicit
chained default async callback thread: routed-default
all stage results: sync-7, async-7, explicit-7, chain-16
```

Trong chương trình này, `source.complete(7)` được gọi trên thread `main`, vì vậy callback đồng bộ quan sát được thread đó. Callback async không có executor riêng chạy trên `routed-default`; callback async có executor riêng chạy trên `routed-explicit`. Kết quả thread này là của chương trình kiểm thử với hai single-thread executor được đặt tên rõ ràng, không phải cam kết rằng mọi callback đồng bộ trong mọi ứng dụng luôn chạy trên thread gọi `complete`.

## 7. Những điều hai hook không thay đổi

### Phương thức đồng bộ không dùng `defaultExecutor()`

`thenApply`, `thenAccept`, `thenRun`, `thenCompose`, `handle` và `whenComplete` không trở thành async chỉ vì subclass override `defaultExecutor()`. Nếu cần tách công việc khỏi thread hoàn tất stage, hãy gọi biến thể `...Async`.

### Executor truyền tường minh được ưu tiên

Ví dụ `thenApplyAsync(action, executor)` dùng executor ở tham số. Override `defaultExecutor()` không ghi đè lựa chọn này. Điều đó cho phép một chuỗi có executor mặc định nhưng một số bước riêng dùng executor chuyên biệt.

### Static factory không lấy hook từ instance subclass

Các factory tĩnh như `CompletableFuture.supplyAsync(...)` và `CompletableFuture.runAsync(...)` không được gọi trên instance subclass, nên không sử dụng override `defaultExecutor()` hoặc `newIncompleteFuture()` của một object cụ thể. Nếu cần điều khiển executor cho factory tĩnh, truyền executor qua overload tương ứng; nếu cần một root future thuộc subclass, hãy tạo instance subclass theo thiết kế của ứng dụng.

### Không tự quản lý vòng đời executor thay cho caller

`defaultExecutor()` trả về executor được dùng để thực thi tác vụ; nó không làm cho `CompletableFuture` sở hữu hoặc tự shutdown executor đó. Chủ sở hữu executor phải quyết định lúc shutdown, chờ hoàn tất và xử lý tác vụ bị từ chối.

## 8. Thiết kế subclass an toàn

- **Giữ cấu hình ổn định:** lưu executor trong field `final` và truyền cùng cấu hình sang dependent stage mới.
- **Trả về object mới:** mỗi lần `newIncompleteFuture()` nên tạo một future chưa hoàn tất, riêng cho stage mới.
- **Không tạo pool trong hook:** hook có thể được gọi thường xuyên khi xây dựng chuỗi stage; tạo pool mỗi lần sẽ gây rò rỉ thread và tài nguyên.
- **Không shutdown executor trong `newIncompleteFuture()` hoặc `defaultExecutor()`:** nhiều stage có thể còn đang dùng chung executor.
- **Chọn pool phù hợp:** tác vụ CPU-bound và I/O blocking có đặc tính khác nhau. Dùng executor riêng khi cần cô lập tải hoặc tránh làm nghẽn common pool.
- **Giới hạn tài nguyên:** thread pool, queue và chính sách từ chối cần phù hợp với tải. `CompletableFuture` không tự cung cấp backpressure cho một hệ thống tạo tác vụ không giới hạn.
- **Xử lý rejection:** nếu executor từ chối tác vụ, stage async có thể hoàn tất exceptionally. Hãy xử lý lỗi bằng `exceptionally`, `handle` hoặc cơ chế báo lỗi của ứng dụng.
- **Không dựa vào thứ tự callback đồng bộ:** khi nhiều completion phụ thuộc nhau, thứ tự thực thi có thể phụ thuộc trạng thái hoàn tất và thread kích hoạt. Chỉ dùng quan hệ stage để mô tả thứ tự nghiệp vụ cần thiết.

## 9. Khi nào nên override?

| Nhu cầu | Cách làm |
| --- | --- |
| Muốn dependent stage vẫn là subclass | Override `newIncompleteFuture()` |
| Muốn async method không truyền executor dùng pool riêng | Override `defaultExecutor()` |
| Muốn cả kiểu stage và executor được giữ xuyên suốt chuỗi | Override cả hai |
| Chỉ một tác vụ cần executor đặc biệt | Dùng overload async có tham số executor |
| Chỉ cần chuỗi future thông thường | Dùng `CompletableFuture` cơ sở, không cần subclass |

Không cần tạo subclass chỉ để đổi executor cho một thao tác đơn lẻ; overload có executor tường minh thường dễ đọc hơn. Subclass hữu ích khi đây là chính sách mặc định nhất quán cho nhiều stage hoặc khi stage cần giữ một implementation/cấu hình riêng.

## 10. Lỗi thường gặp

1. **Chỉ override `defaultExecutor()`.** Callback async đầu tiên có thể chạy đúng pool, nhưng dependent future vẫn có thể là `CompletableFuture` cơ sở; các stage sau mất chính sách của subclass.
2. **Chỉ override `newIncompleteFuture()`.** Kiểu subclass được giữ nhưng async method không truyền executor vẫn dùng executor mặc định của lớp cơ sở.
3. **Trả về `this` từ `newIncompleteFuture()`.** Nhiều stage sẽ dùng chung một future, làm sai mô hình completion độc lập.
4. **Trả về một future đã hoàn tất.** Stage phụ thuộc cần một future mới ở trạng thái chưa hoàn tất để logic completion gắn kết quả.
5. **Tạo executor mới trong mỗi lần gọi hook.** Mỗi stage có thể tạo thêm thread pool; cấu hình executor nên được tạo và quản lý ở cấp ứng dụng hoặc đối tượng sở hữu.
6. **Nghĩ `defaultExecutor()` ảnh hưởng đến `thenApply`.** Chỉ các phương thức async không truyền executor dùng hook này.
7. **Nghĩ executor mặc định ghi đè executor tường minh.** Overload nhận executor luôn dùng executor được truyền vào.
8. **Nghĩ static `supplyAsync` dùng cấu hình của subclass.** Factory tĩnh không chạy trên instance subclass; truyền executor tường minh hoặc tự tạo root subclass.
9. **Shutdown pool quá sớm.** Nếu executor bị shutdown khi dependent stage còn cần lập lịch, tác vụ có thể bị từ chối.
10. **Dựa vào tên thread để định nghĩa tính đúng đắn nghiệp vụ.** Tên thread chỉ hữu ích cho quan sát và kiểm thử routing; hãy kiểm tra kết quả và quan hệ stage bằng `join`, `get` hoặc composition phù hợp.

## 11. Ghi nhớ

1. `newIncompleteFuture()` được bổ sung từ Java 9 và tạo future chưa hoàn tất cho dependent stage.
2. Override `newIncompleteFuture()` để các stage mới tiếp tục dùng subclass và giữ cấu hình cần thiết.
3. `defaultExecutor()` được bổ sung từ Java 9 và trả executor mặc định cho các phương thức async không truyền executor.
4. Phương thức đồng bộ không dùng `defaultExecutor()`; overload async có executor riêng dùng executor được truyền vào.
5. Muốn giữ cả kiểu subclass lẫn executor mặc định xuyên suốt chuỗi, thường cần override cả hai hook.
6. Mỗi dependent stage cần future mới; không trả về `this` hoặc một future dùng chung.
7. Chủ sở hữu ứng dụng quản lý vòng đời executor; subclass chỉ cung cấp executor cho các thao tác async.
8. Kiểm thử riêng kiểu stage, thread thực thi, executor tường minh và chuỗi stage nhiều bước.