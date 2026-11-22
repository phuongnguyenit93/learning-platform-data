# Không dùng InheritableThreadLocal như giải pháp chung cho nhóm luồng tái sử dụng

## 1. Vấn đề: thread con kế thừa lúc được tạo, không phải mỗi lần chạy task

Trong ứng dụng Java và Spring, một request có thể cần chuyển một ít **ngữ cảnh thực thi** sang công việc bất đồng bộ: request ID, tenant ID, correlation ID dùng cho log hoặc thông tin bảo mật đã được framework kiểm soát. Vì các ngữ cảnh này thường gắn với thread hiện hành, developer dễ nghĩ rằng thay `ThreadLocal<T>` bằng `InheritableThreadLocal<T>` sẽ khiến task bất đồng bộ “tự có” dữ liệu của request.

**Cách nghĩ đó không đúng khi dùng thread pool tái sử dụng worker.** `InheritableThreadLocal` truyền **giá trị khởi tạo từ thread cha sang thread con tại thời điểm thread con được tạo**. Một pool có thể tạo worker khi khởi động hoặc khi nhận một task đầu tiên, rồi tái sử dụng **cùng worker** để chạy các task của nhiều request khác nhau. Việc request B gửi task vào worker đã được tạo từ request A **không làm Java kế thừa lại** ngữ cảnh B.

Hệ quả có thể là **đọc ngữ cảnh cũ**, đọc `null` không ngờ tới, hoặc lẫn dữ liệu giữa các request/tenant. Đây không chỉ là lỗi log: nếu code vô tình dùng một tenant/user ID cũ để quyết định truy cập dữ liệu, vấn đề có thể trở thành **sự cố phân quyền và cô lập dữ liệu**.

### Mục tiêu bài học

Sau bài này, bạn sẽ:

- Hiểu thời điểm `InheritableThreadLocal` sao chép giá trị và cơ chế `childValue(parentValue)`, phân biệt với truyền ngữ cảnh **theo từng task**.
- Giải thích vì sao `ExecutorService`, `ThreadPoolExecutor`, `ThreadPoolTaskExecutor` và `@Async` có thể tái sử dụng worker, làm dữ liệu thừa kế không cập nhật theo caller.
- Tái hiện lỗi bằng chương trình **Java 17+ có stdout xác định**, sau đó sửa bằng wrapper capture/restore ngữ cảnh ở thời điểm **submit**.
- Biết khi nào nên truyền dữ liệu bằng tham số rõ ràng, khi nào dùng `TaskDecorator` của Spring, công cụ context propagation, hoặc wrapper của Spring Security.
- Xử lý `ThreadLocal.remove()` và khôi phục giá trị trước đó trong `finally`, tránh lưu trạng thái request trên thread phục vụ nhiều yêu cầu.
- Phân biệt trường hợp một thread mới thực sự được tạo với trường hợp worker đã tồn tại; hiểu rủi ro của giá trị mutable được chia sẻ theo tham chiếu.
- Kiểm thử tính đúng đắn của ngữ cảnh với **cùng một worker được tái sử dụng** và nhiều request, không dựa vào số lượng thread/ngẫu nhiên.

**Phiên bản ví dụ:** Java 17+, Spring Framework 6.1.3 (ví dụ Maven Spring thuần). Các quy tắc kế thừa của `InheritableThreadLocal` là hợp đồng Java; Spring không tự sửa hợp đồng đó chỉ bằng việc dùng `@EnableAsync`.

## 2. Chính xác InheritableThreadLocal hoạt động thế nào?

### 2.1. ThreadLocal thường và InheritableThreadLocal

`ThreadLocal<T>` cung cấp một vùng giá trị **theo từng thread**. Nếu hai thread cùng gọi `REQUEST_ID.get()` trên một key `ThreadLocal`, mỗi thread đọc giá trị riêng của mình, không mặc nhiên thấy giá trị của thread kia.

`InheritableThreadLocal<T>` kế thừa `ThreadLocal<T>`, thêm bước **khởi tạo dữ liệu cho một thread con khi thread con được tạo**. Theo Javadoc Java 17:

- Khi tạo child thread, child có thể nhận những giá trị ban đầu từ parent thread cho các biến `InheritableThreadLocal` đang có giá trị.
- Phương thức `childValue(parentValue)` tính giá trị khởi tạo của child; việc tính xảy ra **trong parent thread trước khi child được khởi động**.
- Mặc định `childValue` chỉ **trả lại đối tượng `parentValue`**. Nếu giá trị là đối tượng mutable, parent và child có thể giữ **cùng tham chiếu**, không phải một bản sao sâu.
- Java cho phép một số hình thức tạo thread **không kế thừa** inheritable thread-locals. Do đó không được coi tính kế thừa là một cơ chế xuyên qua mọi executor và runtime.

Bảng so sánh:

| Đặc điểm | `ThreadLocal<T>` | `InheritableThreadLocal<T>` |
| --- | --- | --- |
| Giá trị được phân theo thread | Có | Có |
| Child thread tự nhận giá trị khởi tạo từ parent theo mặc định | Không | Có, tại lúc **child thread được tạo** |
| Tự cập nhật giá trị mỗi lần executor nhận task mới | Không | **Không** |
| Worker của thread pool tự đổi sang context của request B | Không | **Không** |
| `remove()` trên caller tự xóa giá trị ở worker đã tồn tại | Không | **Không** |
| Dùng cho ngữ cảnh request với pool tái sử dụng mà không có wrapper | Không phù hợp | **Không phù hợp** |
| Có thể dùng khi tạo một child thread thật với lifecycle gắn parent | Cần tự truyền | Có thể phù hợp nếu hiểu rõ phạm vi và đối tượng chia sẻ |

**Quy tắc:** `ThreadLocal` quản lý dữ liệu theo **thread**; request/task là một phạm vi logic **khác thread**. Việc đặt dữ liệu trên thread không tự thiết lập ranh giới cleanup sau mỗi task.

### 2.2. Dòng thời gian gây lỗi

Giả sử một thread pool chỉ có một worker:

~~~text
Request A (caller): TENANT.set("tenant-A")
    |
    +-- submit task A
          |
          +-- pool cần worker mới: tạo worker-1
                |
                +-- worker-1 kế thừa giá trị "tenant-A"
                +-- chạy task A, đọc tenant-A
                +-- task A hoàn tất, worker-1 KHÔNG bị hủy

Request B (caller): TENANT.set("tenant-B")
    |
    +-- submit task B
          |
          +-- pool TÁI SỬ DỤNG worker-1
                |
                +-- KHÔNG tạo thread mới
                +-- KHÔNG gọi lại childValue cho request B
                +-- task B vẫn đọc tenant-A từ worker-1
~~~

**Sai lầm cốt lõi:** developer nghĩ việc `submit(task B)` tạo ra một quan hệ **parent/child mới** giữa request B và worker-1. Thực tế submit chỉ đưa `Runnable`/`Callable` đến executor; worker-1 **đã được tạo từ trước**.

Không bảo đảm mọi pool đều trả kết quả sai theo đúng một cách. Nếu worker được tạo trong lúc khởi động, dữ liệu thừa kế có thể **trống**; nếu pool mở rộng khi load tăng, worker mới có thể nhận context khác; khi thread chết và được tạo lại, hành vi có thể đổi. Chính sự phụ thuộc vào thời điểm tạo worker làm cách dùng này **không ổn định**.

## 3. Java 17+ chạy độc lập: tái hiện ngữ cảnh request bị cũ

Ví dụ cố ý dùng `InheritableThreadLocal` theo cách sai để quan sát lỗi. `Executors.newSingleThreadExecutor()` sử dụng một worker và sẽ tái sử dụng worker đó cho các task tiếp theo trong điều kiện bình thường. Ta gọi `Future.get()` sau mỗi task để bảo đảm task A hoàn tất rồi mới nộp B.

Lưu thành `InheritablePoolPitfallDemo.java`:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public final class InheritablePoolPitfallDemo {

    private static final InheritableThreadLocal<String> TENANT =
            new InheritableThreadLocal<>();

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            TENANT.set("tenant-A");

            // Worker được tạo khi nhận task đầu tiên và kế thừa A.
            System.out.println("first="
                    + pool.submit(TENANT::get).get());

            // Caller thay đổi context, worker cũ không tự đổi.
            TENANT.set("tenant-B");
            System.out.println("caller=" + TENANT.get());

            // B vẫn chạy trên worker đã tồn tại.
            System.out.println("second="
                    + pool.submit(TENANT::get).get());

        } finally {
            // Chỉ xóa giá trị trên MAIN, không sửa context worker.
            TENANT.remove();

            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac InheritablePoolPitfallDemo.java
java InheritablePoolPitfallDemo
~~~

**Stdout với JDK 17+ thông thường trong ví dụ một worker này:**

~~~text
first=tenant-A
caller=tenant-B
second=tenant-A
~~~

### Vì sao kết quả này đáng tin?

1. `TENANT.set("tenant-A")` xảy ra trước lần đầu nộp task, nên worker được tạo để chạy task A nhận giá trị A khi được tạo.
2. `pool.submit(TENANT::get).get()` chờ task A hoàn tất. Task chỉ đọc giá trị; nó không gây exception làm worker bị thay thế.
3. Caller đổi `TENANT` sang B nhưng không tác động đến giá trị trong **worker khác**.
4. Executor một worker tái sử dụng worker đó, nên task B đọc giá trị **A**.
5. `TENANT.remove()` trong `main` chỉ tác động đến **main thread**. Cleanup của worker không được thực hiện tự động chỉ vì caller đã xóa context.
6. Chương trình đóng executor trong `finally`, không bỏ lại worker chạy sau khi demo kết thúc.

Nếu code production thật dùng worker với lifecycle dài và nhiều request, việc thấy tenant A tại request B là một **kết quả không chấp nhận được**. Đừng sao chép kiểu truyền ngữ cảnh của phản ví dụ này vào hệ thống có thông tin người dùng.

**Giới hạn của thí nghiệm:** Với các executor có nhiều worker, worker có thể được tạo vào thời điểm khác hoặc bị thay thế; khi đó dữ liệu quan sát có thể thay đổi. Điều này không làm phương pháp trở nên an toàn, mà cho thấy nó còn khó dự đoán hơn.

## 4. Không chỉ sai thời điểm: còn có nguy cơ chia sẻ mutable object

Mặc định `InheritableThreadLocal.childValue(parentValue)` trả lại **chính tham chiếu đầu vào**. Ví dụ nếu thread cha đặt một `Map<String, String>` hoặc `List<String>`, thread con có thể thấy và sửa **cùng object**. Hai thread có hai vị trí trong thread-local map nhưng giá trị các vị trí đó có thể trỏ tới **cùng instance**.

Đoạn Java minh họa ngắn (fragment, cần imports và method bao quanh):

~~~java
InheritableThreadLocal<java.util.List<String>> tags =
        new InheritableThreadLocal<>();

java.util.List<String> list = new java.util.ArrayList<>();
tags.set(list);

Thread child = new Thread(() -> tags.get().add("child"));
child.start();
child.join();

System.out.println(list); // [child]
tags.remove();
~~~

Ở đây `join()` bảo đảm child đã sửa xong trước khi main đọc `list`; không có cập nhật đồng thời vào `ArrayList` trong fragment. Nếu parent và child cùng sửa `ArrayList` đồng thời, lại thêm một nguy cơ **data race** vì `ArrayList` không thread-safe.

Bạn có thể override `childValue` để tạo một bản sao khi child thread được tạo:

~~~java
// Fragment minh họa một cách copy list khi tạo thread con.
InheritableThreadLocal<java.util.List<String>> tags =
        new InheritableThreadLocal<>() {
            @Override
            protected java.util.List<String> childValue(
                    java.util.List<String> parent) {
                return parent == null
                        ? null
                        : new java.util.ArrayList<>(parent);
            }
        };
~~~

Nhưng **cách này không sửa lỗi thread pool**: `childValue` vẫn chỉ được gọi **khi tạo worker**, không phải lúc mỗi task được nộp. Copy lúc tạo thread làm dữ liệu được tách về tham chiếu, **không làm dữ liệu luôn mới theo request**.

**Không gắn một entity JPA, connection, transaction object, mutable security context hay request object nặng** vào inheritable thread-local để truyền cho task. Những đối tượng đó thường gắn lifecycle, session hoặc thread cụ thể và có thể không thread-safe.

## 5. Những tình huống làm bug xuất hiện thất thường

### 5.1. Worker tạo sẵn trước khi request tới

`ThreadPoolExecutor` có thể được khởi tạo với core worker **chạy sẵn** bằng `prestartCoreThread()` hoặc `prestartAllCoreThreads()`. Spring `ThreadPoolTaskExecutor` cũng có tùy chọn `setPrestartAllCoreThreads(true)`.

~~~java
// Fragment JDK, không phải class độc lập.
ThreadPoolExecutor pool = new ThreadPoolExecutor(
        1, 1, 60, TimeUnit.SECONDS,
        new LinkedBlockingQueue<>());
pool.prestartAllCoreThreads();
~~~

Nếu tạo worker ở startup thread **không có tenant/request context**, worker đó không tự kế thừa context của những caller gửi task sau. Bạn có thể thấy `null`, ngay cả khi request thread đã đặt `InheritableThreadLocal`.

### 5.2. Worker tạo lười khi có request đầu tiên

Mặc định nhiều pool tạo worker khi có task. Nếu request A làm pool tạo worker, thread đó có thể nhận context A. Khi B/C/D dùng lại worker, context A vẫn còn. Nguy cơ gây rò rỉ thông tin giữa request nghiêm trọng hơn một giá trị `null` dễ phát hiện.

### 5.3. Pool tăng worker khi queue đầy

Với `ThreadPoolExecutor`, việc tạo worker phụ thuộc `corePoolSize`, `maximumPoolSize` và tình trạng queue. Worker mới có thể được tạo trong các thời điểm và từ các thread gửi task khác nhau. Do đó trong cùng một pool có thể tồn tại worker mang context A, worker mang context B và worker mang context rỗng. Kết quả còn phụ thuộc worker nào được chọn để chạy task.

Đừng viết test kiểu “gửi ba task rồi mong chúng dùng worker A/B/C theo thứ tự”. Hãy dùng executor một worker cho bài test khẳng định tính sai, hoặc kiểm tra có hệ thống với latch, giới hạn worker, queue và context của từng task.

### 5.4. Worker bị thay thế hoặc pool thay đổi size

Worker có thể kết thúc, bị thay thế, hoặc một số pool có idle timeout tùy cấu hình. Khi worker mới được tạo, một giá trị inheritable khác có thể xuất hiện. Vì thế lỗi có thể “biến mất” sau restart hoặc tự đổi khi tải cao; không có nghĩa là code đã đúng.

### 5.5. Parent thread cũng là worker của một pool khác

Trong pipeline có nhiều lớp executor, một task chạy trên worker của pool thứ nhất có thể tạo worker cho pool thứ hai. Giá trị `InheritableThreadLocal` được thừa kế từ **thread đang tạo worker**, chứ không nhất thiết là request gốc. Khi cấu trúc pool phức tạp, lineage của thread không phản ánh lineage của request.

## 6. Phân biệt phạm vi: thread, task, request và transaction

~~~text
Phạm vi request:    [ Request A ]  [ Request B ]  [ Request C ]
Phạm vi task:         [ Task A ]     [ Task B ]     [ Task C ]
Phạm vi worker:     [------------ worker-1 dùng lại ------------]
                           ^
                           |
                  InheritableThreadLocal
                  kế thừa một lần tại
                  creation, KHÔNG tại submit
~~~

Muốn task B biết ngữ cảnh B, cách đúng là **nắm ngữ cảnh tại thời điểm nộp B** rồi thiết lập ngữ cảnh đó **chỉ trong phạm vi thực thi B**, sau đó dọn/khôi phục.

Đặc biệt, những dữ liệu sau có cơ chế riêng:

| Dữ liệu | Giải pháp thích hợp |
| --- | --- |
| `tenantId`/`requestId` đơn giản | **Truyền tham số bất biến** hoặc snapshot ở điểm submit |
| MDC/correlation logging | Copy MDC map có kiểm soát hoặc context propagation facility được cấu hình |
| Spring Security `SecurityContext` | Dùng các wrapper/async integrations của **Spring Security**, kiểm tra scope và cleanup |
| Spring transaction | Thiết lập **transaction boundary riêng** ở nơi thực thi; không truyền transaction của caller qua ThreadLocal |
| Servlet request attributes | Hạn chế giữ request object sau response; truyền những dữ liệu cần thiết hoặc dùng facility có vòng đời rõ ràng |
| Micrometer observation/tracing | Context propagation có đăng ký accessor thích hợp và instrumentation |
| Database session/JPA EntityManager | Không chia sẻ resource gắn thread/session; đi qua service/repository tại worker với transaction phù hợp |

**Bảo mật:** Chuyển user ID bằng String không tự trở thành cơ chế authorization. Việc quyết định quyền phải dựa trên principal/context đã được xác thực theo contract bảo mật, không tin một ThreadLocal tùy ý như nguồn duy nhất của thông tin nhạy cảm.

## 7. Lựa chọn ưu tiên: truyền ngữ cảnh bằng tham số

Nếu một tác vụ chỉ cần `tenantId`, `documentId`, correlation ID hoặc một vài giá trị business **bất biến**, cách rõ nhất là truyền chúng trực tiếp cho task:

~~~java
// Fragment, tenantId là giá trị đã được xác thực ở boundary.
String tenantId = currentTenantId();

CompletableFuture<String> result =
        CompletableFuture.supplyAsync(
                () -> documentService.loadForTenant(tenantId),
                documentExecutor
        );
~~~

Đây là **fragment không độc lập**, cần các biến, hàm và executor của ứng dụng. Không có `InheritableThreadLocal`; task giữ snapshot `tenantId` trong closure. Khi cùng worker chạy task của các request khác nhau, mỗi closure mang giá trị riêng.

Ưu điểm: dễ test, quan hệ dữ liệu tường minh, không rò rỉ context qua worker và không cần đoán framework hiện có interceptor nào. Đổi lại, API cần chấp nhận tham số rõ ràng; với nhiều loại framework-specific context, một cơ chế propagation chính thức có thể phù hợp hơn.

**Cẩn thận với mutable object:** Nếu closure giữ object có thể bị caller sửa sau `submit`, vẫn có race. Hãy snapshot/immutable copy các giá trị cần thiết hoặc xây dựng DTO bất biến thay vì chuyển nguyên request/entity có thể bị thay đổi đồng thời.

## 8. Java 17+ chạy độc lập: capture/restore context theo từng task

Khi phải tương tác với một API dùng `ThreadLocal`, có thể viết wrapper **chụp giá trị tại thread nộp task**, rồi **cài giá trị đó trong worker đúng thời gian chạy task**. Sau đó wrapper khôi phục context có trước trong worker hoặc `remove()` nếu trước đó trống.

Ví dụ sau sử dụng `ThreadLocal<String>` thông thường, **không cần InheritableThreadLocal**. Đó là chủ ý: inheritance lúc tạo thread không giải quyết được scope theo task.

Lưu thành `ExplicitContextDemo.java`:

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class ExplicitContextDemo {

    private static final ThreadLocal<String> TENANT =
            new ThreadLocal<>();

    private static <T> Future<T> submitWithTenant(
            ExecutorService executor,
            Callable<T> task) {

        // Đọc tại caller NGAY LÚC SUBMIT, không đợi đến lúc worker chạy.
        final String captured = TENANT.get();

        return executor.submit(() -> {
            // Worker có thể đang phục vụ một scope khác.
            final String previous = TENANT.get();

            try {
                if (captured == null) {
                    TENANT.remove();
                } else {
                    TENANT.set(captured);
                }

                return task.call();
            } finally {
                // Đảm bảo không để lại context của task mới trên worker.
                if (previous == null) {
                    TENANT.remove();
                } else {
                    TENANT.set(previous);
                }
            }
        });
    }

    private static String currentTenant() {
        String tenant = TENANT.get();
        return tenant == null ? "none" : tenant;
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            TENANT.set("tenant-A");
            Future<String> first =
                    submitWithTenant(pool, ExplicitContextDemo::currentTenant);
            System.out.println("first=" + first.get());

            TENANT.set("tenant-B");
            Future<String> second =
                    submitWithTenant(pool, ExplicitContextDemo::currentTenant);
            System.out.println("second=" + second.get());

            TENANT.remove();
            Future<String> empty =
                    submitWithTenant(pool, ExplicitContextDemo::currentTenant);
            System.out.println("empty=" + empty.get());
            System.out.println("caller=" + currentTenant());

        } finally {
            // Cleanup ngữ cảnh ở MAIN và vòng đời executor.
            TENANT.remove();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac ExplicitContextDemo.java
java ExplicitContextDemo
~~~

Đầu ra:

~~~text
first=tenant-A
second=tenant-B
empty=none
caller=none
~~~

### Vì sao wrapper sửa được lỗi?

1. `captured = TENANT.get()` chạy trong **caller đang gửi task**. Vì vậy task A bắt snapshot A, task B bắt snapshot B.
2. Worker nhận task thì lưu lại `previous` của **worker thread**, sau đó cài snapshot của đúng task.
3. Task đọc giá trị của chính nó, không phụ thuộc worker được tạo ở thời điểm nào.
4. `finally` chạy cả khi `task.call()` ném exception, bảo đảm gỡ/khôi phục context theo scope đã thiết lập.
5. Nếu caller không có giá trị, wrapper gọi `TENANT.remove()` trong worker **trước task**, tránh nhìn thấy context cũ.
6. Sau khi task xong, context của worker được phục hồi đúng theo trước đó. Trong một worker sạch ban đầu, điều này nghĩa là không để lại giá trị của task A/B cho task tiếp.

**Giải thích “restore previous” so với “remove luôn”:** Khi wrapper chỉ sở hữu một phần context trong một stack tác vụ lồng nhau, khôi phục giá trị cũ là cần thiết để không phá scope bên ngoài. Với worker hoàn toàn chuyên dụng và không có context nền, cleanup bằng `remove()` sau mỗi task cũng là một chiến lược hợp lệ. Nhưng nếu `previous` vốn đã chứa context rò rỉ do code khác, việc restore không tự sửa bug bên ngoài; cần kiểm soát owner của executor và mọi đường thiết lập context.

**Chú ý:** Đây là ví dụ tối giản cho một `ThreadLocal<String>`. Không lấy nguyên mẫu và tự động áp dụng cho `SecurityContext`, transaction, MDC hoặc dữ liệu mutable khi chưa hiểu API snapshot/restore chính thức. Với dữ liệu bảo mật, ưu tiên wrapper của framework phù hợp.

## 9. Trong Spring: TaskDecorator là điểm đặt context theo từng task

`org.springframework.core.task.TaskDecorator` là functional interface để bọc `Runnable` trước khi chạy. `ThreadPoolTaskExecutor.setTaskDecorator(...)` áp decorator cho callback thực thi. Đây là vị trí phù hợp để tạo **per-submission context snapshot** và thiết lập/khôi phục trong worker, thay vì dựa vào inheritance lúc worker ra đời.

Trong Spring Framework 6.1.3, Javadoc `ThreadPoolTaskExecutor` ghi rõ decorator có thể nhận **wrapper của task** (không nhất thiết là đúng Runnable/Callable mà caller gửi). Vai trò chính là thiết lập execution context hoặc quan sát thời gian thực thi; không nên dựa vào decorator để bắt toàn bộ exception phát sinh từ `FutureTask` vì wrapper có thể giữ lỗi bên trong `Future`.

### 9.1. Ví dụ Maven Spring Framework 6.1.3 chạy được

Cấu trúc ba Java file:

~~~text
spring-context-demo/
├── pom.xml
└── src/main/java/demo/
    ├── ContextConfig.java
    ├── TenantService.java
    └── SpringContextDemo.java
~~~

**Tệp `pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-context-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.3</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>demo.SpringContextDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Tệp `src/main/java/demo/ContextConfig.java`:**

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class ContextConfig {

    // Một giá trị đơn giản để quan sát kết quả; không dùng làm
    // nguồn ủy quyền bảo mật trong ứng dụng thực tế.
    public static final ThreadLocal<String> TENANT = new ThreadLocal<>();

    @Bean("contextExecutor")
    public ThreadPoolTaskExecutor contextExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(8);
        executor.setThreadNamePrefix("tenant-");

        executor.setTaskDecorator(task -> {
            // Callback này được tạo khi task được nộp vào executor.
            String captured = TENANT.get();

            return () -> {
                String previous = TENANT.get();

                try {
                    if (captured == null) {
                        TENANT.remove();
                    } else {
                        TENANT.set(captured);
                    }
                    task.run();
                } finally {
                    if (previous == null) {
                        TENANT.remove();
                    } else {
                        TENANT.set(previous);
                    }
                }
            };
        });

        return executor;
    }

    @Bean
    public TenantService tenantService() {
        return new TenantService();
    }
}
~~~

`@EnableAsync` kích hoạt annotation processing, `@Bean` tạo executor có tên cụ thể để chọn bằng `@Async("contextExecutor")`. `TaskDecorator` chụp `TENANT` từ **thread nộp task**, rồi thiết lập snapshot trong worker và dọn dẹp sau khi task hoàn tất.

**Tệp `src/main/java/demo/TenantService.java`:**

~~~java
package demo;

import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;

public class TenantService {

    @Async("contextExecutor")
    public CompletableFuture<String> readTenant() {
        String current = ContextConfig.TENANT.get();
        String result = current == null ? "none" : current;
        return CompletableFuture.completedFuture(result);
    }
}
~~~

Method `readTenant()` nằm trên **bean service**, không được khai báo trong lớp `@Configuration`. Spring Javadoc `@Async` không hỗ trợ methods khai báo trực tiếp trong `@Configuration`, nên việc tách hai class là chủ ý.

**Tệp `src/main/java/demo/SpringContextDemo.java`:**

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public final class SpringContextDemo {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             ContextConfig.class)) {

            TenantService service = context.getBean(TenantService.class);

            try {
                ContextConfig.TENANT.set("tenant-A");
                System.out.println("first=" + service.readTenant().join());

                ContextConfig.TENANT.set("tenant-B");
                System.out.println("second=" + service.readTenant().join());

                ContextConfig.TENANT.remove();
                System.out.println("empty=" + service.readTenant().join());
            } finally {
                ContextConfig.TENANT.remove();
            }
        }
    }
}
~~~

Chạy:

~~~bash
mvn -q compile exec:java
~~~

Đầu ra của chương trình Java:

~~~text
first=tenant-A
second=tenant-B
empty=none
~~~

### Phân tích kết quả Spring

- Spring tạo một `ThreadPoolTaskExecutor` dùng **một worker**. Worker có thể được tái sử dụng từ lần gọi A sang B và lần gọi không có context.
- `@Async("contextExecutor")` làm lời gọi bên ngoài đi qua Spring proxy, được nộp vào executor chọn rõ.
- Mỗi lần nộp, `TaskDecorator` chụp giá trị ở caller đang gọi service: A, B, rồi `null`.
- Trước khi chạy method thực, worker được đặt context tương ứng. Sau khi method và callback kết thúc, `finally` khôi phục giá trị trước đó.
- `join()` chờ completion của `CompletableFuture`; vì chương trình chỉ in ở main, stdout có thứ tự ổn định.
- Đoạn này dùng **`ThreadLocal` thường**, không cần `InheritableThreadLocal`. Nó kiểm soát ngữ cảnh **theo task**, không theo lúc worker sinh ra.

**Không sao chép nguyên trạng `static ThreadLocal` chứa tenant ID vào production rồi dùng nó để cấp quyền.** Ví dụ này dùng String để minh họa cách truyền ngữ cảnh; hệ thống thật cần security boundary có thể audit, xác thực principal, ownership rõ ràng và cleanup ở điểm nhận/trả request.

**Vòng đời:** `AnnotationConfigApplicationContext` quản lý bean executor. Khi context đóng, Spring dọn dẹp thread pool theo lifecycle. Không khởi tạo một `ThreadPoolTaskExecutor` mới cho mỗi request.

## 10. Các lựa chọn tích hợp chuẩn của Spring

### 10.1. Spring 6.1+ và Micrometer Context Propagation

Spring Framework 6.1 cung cấp `org.springframework.core.task.support.ContextPropagatingTaskDecorator`. Nó có thể dùng cơ chế Micrometer Context Propagation để chụp và phục hồi những context đã đăng ký accessor phù hợp, hữu ích cho **tracing, observation và logging**.

~~~java
// Fragment Spring 6.1+; cần dependency/context accessors phù hợp.
executor.setTaskDecorator(
        new ContextPropagatingTaskDecorator());
~~~

Đây **không phải** câu thần chú tự truyền **mọi** `ThreadLocal` tùy ý. Cần xem các dependency `io.micrometer:context-propagation`, `ThreadLocalAccessor` được đăng ký, version Spring và cách instrumentation hiện hành lấy snapshot. Nếu chưa có accessor cho biến của ứng dụng, đừng khẳng định nó được truyền. Việc capture/restore cũng có overhead, nên cần đo với khối lượng lớn các task rất ngắn.

Đối với những context đơn giản chỉ chứa business ID, **truyền tham số tường minh** vẫn thường dễ hiểu và ít phụ thuộc hơn.

### 10.2. Spring Security: không dùng inheritable holder mode làm giải pháp chung

Spring Security thường lưu `SecurityContext` gắn với thread thông qua `SecurityContextHolder`. Chuyển sang `SecurityContextHolder.MODE_INHERITABLETHREADLOCAL` không giải quyết lỗi stale context trên một pool tái sử dụng worker; giá trị vẫn có thể được kế thừa lúc worker tạo, không phải lúc task mới nộp.

Spring Security cung cấp những wrapper concurrency chuyên dụng, ví dụ `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextExecutor` và `DelegatingSecurityContextAsyncTaskExecutor` (tùy API executor) để thiết lập/clear security context theo phạm vi thực thi. Với overload nhận `SecurityContext` cố định, wrapper có thể cố tình dùng **một context chung cho mọi task**; với chế độ chụp context tại submit, cần chọn constructor/wrapper đúng ý định. Không tự đoán mọi lớp đều truyền principal động theo cùng một cách.

Khi xử lý quyền truy cập thật, hãy đi qua cơ chế Spring Security chính thức và test **hai request có hai principal khác nhau trên cùng worker**, thêm case không có principal. Không tự copy reference mutable của `SecurityContext` rồi xem như đảm bảo snapshot an toàn.

### 10.3. MDC dùng map snapshot và cleanup

Với logging framework hỗ trợ MDC, hướng xử lý là:

1. Ở thread nộp task, lấy **bản sao context map** theo API MDC của framework (không chỉ chia sẻ cùng mutable map).
2. Trong worker, lưu/khôi phục MDC hiện hành theo yêu cầu framework, cài bản sao của đúng task.
3. Trong `finally`, xóa hoặc khôi phục dữ liệu cũ để worker không đem correlation ID của request A sang B.
4. Kiểm tra khi caller không có context, khi task lỗi, khi future bị từ chối và khi worker đã được tạo từ trước.

Không phải bản triển khai MDC nào cũng có cùng API và cấu trúc; đừng trộn `ThreadLocal` tùy ý với MDC mà không kiểm tra hợp đồng của thư viện log.

### 10.4. @Async và CompletableFuture phải dùng đúng executor

`@Async` trong Spring thường dựa vào proxy; **self-invocation** (`this.asyncMethod()` trong cùng service) sẽ bỏ qua proxy trong `AdviceMode.PROXY` mặc định. Do đó `TaskDecorator` trên một executor không tự giúp nếu lời gọi chưa đi qua executor.

Tương tự:

~~~java
// Fragment: businessExecutor là bean TaskExecutor/Executor.
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(
                () -> loadDocument(), businessExecutor);
~~~

Khi truyền executor Spring, decorator được áp cho task được gửi qua executor đó. Ngược lại, `CompletableFuture.supplyAsync(() -> loadDocument())` **không truyền executor** thường dùng `ForkJoinPool.commonPool()`, nên decorator của Spring **không được tự động áp dụng**.

Các stage `thenApplyAsync(fn)` hoặc `handleAsync(fn)` cũng có default async facility riêng khi không truyền executor. Nếu context quan trọng, truyền executor cần thiết vào **từng stage async cần isolation**, hoặc sử dụng cơ chế propagation đã thiết kế rõ.

## 11. Ngữ cảnh nào không nên “copy” như một String?

Không phải mọi context có thể sao chép đơn giản:

- **Transaction:** Spring transaction thường gắn với thread thực thi; không nên chụp rồi chuyển nguyên transaction/resource handles sang worker. Tạo transaction phù hợp trong method của worker qua Spring transaction interceptor/transaction template nếu cần.
- **Request/response object:** Servlet request có lifecycle giới hạn; không giữ nguyên object sau khi HTTP response xong chỉ để đọc header ở background thread. Truyền những giá trị bất biến thật sự cần thiết.
- **EntityManager/Session:** các resource persistence gắn phiên/transaction không mặc định thread-safe; mở tài nguyên theo worker và quản lý lifecycle.
- **Mutable security context:** có thể thay đổi trong lúc task đang chờ; dùng API/wrapper chính thức và xác định snapshot/ownership.
- **ThreadLocal có dữ liệu lớn:** pool worker sống lâu có thể giữ đối tượng lớn, dẫn đến tăng bộ nhớ và retention ngoài dự tính. Cleanup bằng `remove()` là trách nhiệm của code đặt context vào worker.

Với job chạy qua MQ hoặc process khác, `ThreadLocal`/`InheritableThreadLocal` không phải giao thức truyền context giữa process. Cần đưa metadata cần thiết vào message/headers theo chính sách bảo mật, rồi tái tạo context hợp lệ ở consumer.

## 12. Quan sát và kiểm thử đúng tình huống

### Test tối thiểu cần có

| Ca kiểm thử | Điều cần xác nhận |
| --- | --- |
| Một worker, hai task A/B từ caller đổi tenant | Mỗi task thấy **tenant đúng của chính nó** |
| Sau A/B có task C không có tenant | C phải thấy **none/null**, không rò rỉ A hoặc B |
| Worker đã `prestart` trước khi có tenant | Task vẫn nhận context đúng nhờ wrapper, không phụ thuộc inheritance |
| Task ném exception giữa chừng | `finally` khôi phục/clear context; task tiếp theo không bị nhiễm |
| Caller đổi tenant **sau** khi nộp task nhưng trước lúc worker chạy | Task dùng **snapshot lúc nộp**, không dùng giá trị mới |
| Pool có nhiều workers | Kết quả không phụ thuộc worker nào được scheduler chọn |
| `@Async` qua proxy và gọi self-invocation | Chỉ khẳng định async cho lời gọi đi qua interceptor phù hợp |
| Executor shutdown/rejection | Bắt lỗi tại submit và không để caller báo “đã nhận task” khi chưa nhận |
| Security context theo hai principal | Không có lẫn danh tính/authorization giữa request |
| MDC/correlation | Log trong task mang trace phù hợp, được cleanup khi hết task |

Để test race có kiểm soát, dùng `CountDownLatch` giữ worker, nộp một task rồi đổi context caller trước khi mở latch. Sau khi worker đọc, assert rằng wrapper đã chụp giá trị **ở thời điểm submit**. Tránh dùng `Thread.sleep(10)` rồi đoán worker chắc chắn đã chạy lúc nào.

### Các số liệu production nên quan sát

- Số task đang chạy, chiều dài queue, latency submit → start, thời gian chạy task và số rejection.
- Số job thiếu tenant/correlation ID, tỉ lệ context mismatch, số callback chạy trên executor ngoài dự tính.
- Lỗi bảo mật “wrong principal”, request ID trùng lặp bất thường và log lệch trace; **không log token, session secrets hoặc chi tiết nhạy cảm** để debug.
- Retention/memory của worker và `ThreadLocalMap` khi nghi ngờ leak.
- Đường đi của async context qua `@Async`, scheduler, `CompletableFuture` stages, retry và message consumer.

### Checklist code review

1. Tìm mọi `new InheritableThreadLocal<>()` và nơi code đặt `SecurityContextHolder.MODE_INHERITABLETHREADLOCAL`.
2. Xác định giá trị đó có phải **per-request/per-task** hay thực sự là dữ liệu hợp lệ của **child thread một lần**.
3. Nếu task chạy trên pool tái sử dụng worker, **không dựa vào inheritance** để lấy request context.
4. Ưu tiên tham số bất biến, hoặc wrapper/scope capture tại submit và restore/clear bằng `finally`.
5. Với Spring, cấu hình `ThreadPoolTaskExecutor.setTaskDecorator(...)` hoặc built-in propagation phù hợp, kiểm tra thứ tự decorator/context propagation khác nhau.
6. Với Spring Security, dùng lớp/wrapper tích hợp và kiểm thử principal cụ thể; không tự thêm cơ chế phân quyền dựa trên String ThreadLocal.
7. Đảm bảo `@Async` và các `CompletableFuture` stages thực sự chạy trên executor đã cấu hình; đừng vô tình bỏ qua proxy hoặc dùng common pool.
8. Nếu truyền mutable values, cân nhắc snapshot copy và thread-safety; không để child và parent vô tình chia sẻ state.
9. Xử lý cleanup cả khi task thất bại, bị cancel trước khi chạy, timeout hoặc exception ở worker; cẩn thận điều gì được gọi khi task chưa được nhận.
10. Không tuyên bố đã giải quyết chỉ bằng việc đổi tên thread hay tăng pool size; test trên cùng một worker nhiều lượt và đo hành vi thực tế.

## 13. Những hiểu lầm thường gặp

**“InheritableThreadLocal tự kế thừa lại mỗi lần submit.”** Sai: kế thừa gắn với **thread creation**, không phải submission.

**“Caller đã gọi remove() thì worker cũng mất giá trị cũ.”** Sai: `remove()` ảnh hưởng thread **đang gọi**, không xóa giá trị của mọi worker khác.

**“Pool không thể dùng InheritableThreadLocal vì không bao giờ có thread mới.”** Không chính xác. Pool có thể tạo worker mới, nhưng thời điểm tạo **không trùng phạm vi logic của mọi request**; đó mới là lý do inheritance không đáng tin.

**“Override childValue để clone context sẽ giải quyết được per-request propagation.”** Không. Nó chỉ thay đổi giá trị khởi tạo khi worker tạo, không chạy lại cho mỗi task.

**“Giá trị thread-local ở hai thread chắc chắn là hai object khác nhau.”** Sai. Hai vị trí có thể giữ **cùng tham chiếu mutable** nếu giá trị inherited mặc định.

**“Gọi TaskDecorator quanh task xong thì mọi Future exception đều ném ra từ decorator.”** Không. Với `submit`/`FutureTask`, lỗi có thể được giữ trong `Future`; cần kiểm tra `get()`/callback theo API.

**“Bật @EnableAsync đã đủ để context tự truyền.”** Không. Nó bật xử lý async method, không tự xác định propagation cho mọi `ThreadLocal` tùy ý.

**“Dùng MODE_INHERITABLETHREADLOCAL của Spring Security là an toàn cho pool tái sử dụng.”** Không. Nó có cùng giới hạn kế thừa lúc tạo thread; dùng wrapper bảo mật phù hợp.

**“CompletableFuture không truyền executor sẽ dùng ThreadPoolTaskExecutor của Spring.”** Sai. Overload không executor thường chạy trên common pool của JDK.

**“Mỗi lần chạy task gọi set(context) nhưng không cần finally.”** Sai. Worker có thể chạy task khác sau đó và nhìn thấy giá trị cũ.

**“Truyền một EntityManager/transaction bằng ThreadLocal sẽ làm chúng dùng được ở thread khác.”** Sai. Những resource này có ràng buộc lifecycle/thread riêng.

**“Khi worker thread bị thay thế làm bug biến mất tức là bug đã sửa.”** Sai. Sự thay đổi chỉ phản ánh thời điểm inheritance mới; lỗi vẫn có thể lặp lại.

## 14. Tự kiểm tra

**Câu 1.** `InheritableThreadLocal` sao chép giá trị của parent vào child khi nào?  
**Đáp án:** Khi **child thread được tạo**, theo cơ chế tính `childValue(parentValue)`, không tự lặp lại khi thread nhận task.

**Câu 2.** Pool một worker được tạo bởi request A. Request B thay đổi `TENANT` rồi submit task; task B tự nhận context B không?  
**Đáp án:** Không nếu chỉ dùng inheritance. Worker đã tồn tại có thể tiếp tục đọc giá trị A; cần snapshot tại submit và cài/cleanup trong worker.

**Câu 3.** `TENANT.remove()` ở request B có xóa `TENANT` trong worker không?  
**Đáp án:** Không. `remove()` chỉ tác động thread hiện hành; worker là thread khác.

**Câu 4.** Vì sao một `InheritableThreadLocal<List<String>>` có thể dẫn đến dữ liệu chung ngoài dự tính?  
**Đáp án:** `childValue` mặc định trả cùng tham chiếu parent; list mutable có thể được chia sẻ, dẫn tới thay đổi chéo và race.

**Câu 5.** Tại sao clone trong `childValue` không bảo đảm task B nhận context B?  
**Đáp án:** Clone chỉ xảy ra khi tạo child thread. Worker cũ không bị tạo lại khi nhận B.

**Câu 6.** Giải pháp đơn giản nhất nếu task chỉ cần một `tenantId` đã xác thực là gì?  
**Đáp án:** Truyền `tenantId` dưới dạng tham số bất biến vào task/service, thay vì ngầm lấy từ inheritable thread-local.

**Câu 7.** Trong Spring, `TaskDecorator` nên chụp context và dọn ở đâu?  
**Đáp án:** Chụp khi **task được nộp**; cài giá trị trên worker trước khi chạy callback; khôi phục hoặc remove trong `finally` sau khi callback kết thúc.

**Câu 8.** Khi `@Async` bị self-invocation thì TaskDecorator có chắc được chạy không?  
**Đáp án:** Không. Trong proxy mode, lời gọi tự gọi method có thể không đi qua async interceptor/executor, nên decorator có thể không tham gia.

**Câu 9.** Có nên truyền transaction/JPA EntityManager qua InheritableThreadLocal để giữ nguyên transaction caller sang worker?  
**Đáp án:** Không. Resource gắn thread/session/lifecycle cần boundary riêng trong worker; không copy trực tiếp để giả lập cùng transaction.

**Câu 10.** Một task trên pool một worker trả `null` dù caller vừa set context; trường hợp nào có thể gây ra?  
**Đáp án:** Worker đã được tạo sẵn lúc không có context; inheritance chỉ có ở thời điểm tạo, không ở lúc submit.

## 15. Tài liệu tham khảo chính thức

- [Java SE 17 — InheritableThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/InheritableThreadLocal.html): thời điểm inheritance, `childValue` và việc child có thể nhận cùng tham chiếu.
- [Java SE 17 — ThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): `get`, `set`, `remove` theo thread hiện hành.
- [Java SE 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): worker reuse, on-demand construction, prestart, pool sizing và queue.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): `submit`, `Future` và shutdown.
- [Spring Framework 6.1.3 — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): `setTaskDecorator`, thread pool lifecycle, queue và behavior của decorator với `FutureTask`.
- [Spring Framework 6.1.3 — TaskDecorator](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/core/task/TaskDecorator.html): callback bọc task, thiết lập execution context.
- [Spring Framework 6.1.2 — ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/6.1.2/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html): context propagation bằng Micrometer, có từ Spring 6.1.
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): executor, `@Async`, lựa chọn pool và xử lý concurrency.
- [Spring Security Reference — Concurrency Support](https://docs.spring.io/spring-security/reference/features/integrations/concurrency.html): `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextExecutor` và cleanup bảo mật theo task.
