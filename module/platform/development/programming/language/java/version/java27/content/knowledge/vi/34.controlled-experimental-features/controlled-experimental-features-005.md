# Đánh giá Structured Concurrency theo trạng thái và API của JDK mục tiêu — Java 27

**Structured Concurrency** là cách tổ chức các công việc đồng thời có liên quan thành một nhóm có **vòng đời được giới hạn bởi một phạm vi mã nguồn** (*scope*). Khi một yêu cầu cần thực hiện hai hoặc nhiều tác vụ con rồi tổng hợp kết quả, mô hình này giúp diễn đạt quan hệ cha–con rõ ràng, thống nhất cách chờ, truyền lỗi và yêu cầu hủy, đồng thời cải thiện khả năng quan sát các tác vụ liên quan.

Trong **Java SE 27**, Structured Concurrency là **Seventh Preview (JEP 533)**, **chưa phải tính năng vĩnh viễn**. API hiện tại thuộc package `java.util.concurrent`, trọng tâm là `StructuredTaskScope` và `StructuredTaskScope.Joiner`. Nếu muốn sử dụng trong JDK 27, ứng dụng cần chủ động bật preview khi biên dịch và chạy. API có thể tiếp tục thay đổi hoặc bị loại bỏ trong một JDK tương lai.

Bài thuộc chương **Tính năng thử nghiệm có kiểm soát**, trong chương trình **JAVA_VERSION_JAVA27 — Java 27 và các kiến thức liên quan**. Mục tiêu không chỉ là học cú pháp mà là **biết xác minh trạng thái của JDK đích, lựa chọn đúng API theo phiên bản, hiểu trade-off và đặt điều kiện áp dụng thực tế**. Không sử dụng API incubator hoặc mẫu code từ các bản preview cũ như thể chúng còn đúng trên Java 27.

## 1. Khi nào Structured Concurrency có ích?

Giả sử một API xây dựng trang tổng quan tài khoản cần lấy đồng thời:

- Thông tin hồ sơ từ dịch vụ A.
- Danh sách đơn hàng từ dịch vụ B.
- Hạn mức tín dụng từ dịch vụ C.

Ba kết quả đều cần thiết để tạo một response. Một lựa chọn là nộp ba task vào executor, giữ ba `Future` và tự xử lý lỗi, timeout, cancellation. Khi task đầu tiên thất bại, mã phải nhớ yêu cầu hủy những task còn lại và chờ chúng kết thúc trước khi trả response. Với các tác vụ lồng nhau, việc theo dõi trở nên khó hơn.

Structured Concurrency tổ chức luồng xử lý:

~~~text
                   HTTP request
                         |
                   request handler
                         |
              StructuredTaskScope
                   /     |     \
                  /      |      \
          fetchProfile fetchOrders fetchCredit
                  \      |      /
                   \     |     /
                    join policy
                         |
                compose response
                         |
             scope close, không còn
               subtask sống bên ngoài
~~~

Điều mong muốn là các tác vụ con **không tồn tại độc lập vô thời hạn** sau khi task cha đã kết thúc công việc.

### 1.1. Bốn mục tiêu chính

1. **Vòng đời có cấu trúc:** scope mở trong `try-with-resources` và đóng khi rời block.
2. **Lỗi có phối hợp:** policy (joiner) quyết định khi nào cần hủy các task còn lại và cách trả lỗi về owner.
3. **Cancellation có quan hệ:** khi scope bị hủy, các thread chưa hoàn thành được interrupt.
4. **Observability:** quan hệ giữa scope và subtasks có thể được thể hiện trong các công cụ quan sát thread hierarchy.

Không coi đây là lời hứa giúp tất cả thuật toán chạy nhanh hơn. Chạy đồng thời có lợi khi các tác vụ có thể tiến triển độc lập, thường là tác vụ chờ I/O; còn CPU-bound workload vẫn bị giới hạn bởi core, bandwidth và chi phí điều phối.

## 2. Trạng thái chính xác trong JDK 27

**Tại JDK 27, Structured Concurrency là API Preview lần thứ bảy (JEP 533)**. Nó đã trải qua nhiều vòng thử nghiệm để tiếp nhận phản hồi và điều chỉnh thiết kế.

| JDK | Trạng thái | Điều cần hiểu |
|---|---|---|
| 21 | First Preview | Mẫu cũ có class `StructuredTaskScope` và các policy kiểu subclass |
| 22–24 | Các vòng preview kế tiếp | API tiếp tục được điều chỉnh, mã mẫu không tự động dùng được cho 27 |
| 25 | Fifth Preview — JEP 505 | Thay đổi lớn: scope và chính sách kết hợp `Joiner`; dùng `open(...)` |
| 26 | Sixth Preview — JEP 525 | Tiếp tục thay đổi cách xử lý kết quả/timeout |
| **27** | **Seventh Preview — JEP 533** | **`StructuredTaskScope<T,R,R_X>`, `Joiner<T,R,R_X>`, lỗi được mô tả bằng kiểu generic và `ExecutionException` trong policy mặc định** |

Bảng tóm tắt ý chính, không phải danh sách đầy đủ mọi thay đổi theo từng JEP. Luôn xem **API specification đúng JDK đang chạy**, nhất là khi xây code từ ví dụ trên blog cho Java 21–26.

### 2.1. Preview khác incubator và final

| Loại | Ý nghĩa | Đối với Structured Concurrency JDK 27 |
|---|---|---|
| Final/permanent API | Được đưa vào Java SE lâu dài theo đặc tả, phát hành bình thường | **Chưa** |
| Preview API | Thiết kế đủ hoàn chỉnh để thử nghiệm rộng rãi, nhưng chưa cố định | **Đúng** |
| Incubator API/module | API thử nghiệm được cung cấp qua module incubator riêng | **Không phải trạng thái của tính năng này ở 27** |

Tính năng preview có thể thay đổi tên, chữ ký, hành vi hoặc bị rút khỏi bản phát hành sau. Việc JDK 27 hỗ trợ API không đồng nghĩa JDK 28 hoặc mọi runtime Java khác sẽ hỗ trợ **chính xác cùng chữ ký**.

### 2.2. Vì sao tên package là java.util.concurrent?

Trên JDK 27, nhập:

~~~java
import java.util.concurrent.StructuredTaskScope;
import java.util.concurrent.StructuredTaskScope.Joiner;
import java.util.concurrent.StructuredTaskScope.Subtask;
~~~

Các kiểu thuộc `java.base`. Không cần cài dependency bên ngoài chỉ để có API này trên JDK 27, và không dùng `jdk.incubator.concurrent` như một giải pháp hiện hành.

**Nhưng phải bật preview.** Có `java.util.concurrent` trong classpath/module graph không đủ để sử dụng các API được đánh dấu PREVIEW.

## 3. Những thay đổi của JDK 27 dễ làm hỏng ví dụ cũ

Điểm khác biệt quan trọng của JEP 533:

| Chủ đề | Mẫu cũ thường gặp | Trong JDK 27 |
|---|---|---|
| Kiểu scope | `StructuredTaskScope<T,R>` ở Java 25–26; hoặc class cũ ở 21–24 | `StructuredTaskScope<T,R,R_X extends Throwable>` |
| Kiểu joiner | `Joiner<T,R>` | `Joiner<T,R,R_X extends Throwable>` |
| Policy lỗi mặc định | Một số ví dụ JDK 26 bắt `StructuredTaskScope.FailedException` | `join()` mặc định ném **`ExecutionException`** |
| Timeout mặc định | Ví dụ có thể dùng exception hoặc callback cũ | `CancelledByTimeoutException` thường nằm ở **cause** của `ExecutionException` |
| Tùy biến cấu hình | Ở 26 có `open(Joiner, configOperator)` | **JDK 27 thêm `open(configOperator)`** cho policy mặc định |
| Custom Joiner | API cũ có thể dùng tên callback `onTimeout` | Trong 27 có phương thức `timeout()` |
| Cơ chế chỉ định policy | Subclass `ShutdownOnFailure/ShutdownOnSuccess` trong ví dụ đời đầu | `StructuredTaskScope.open(...)` và `Joiner` |

Các khác biệt trên là lý do cần **pin JDK và đọc API docs đúng version**, không copy ví dụ `new StructuredTaskScope.ShutdownOnFailure()` hay `scope.joinUntil(deadline)` từ bài viết cũ vào source Java 27.

### 3.1. Generic thứ ba R_X có ý nghĩa gì?

Cú pháp JDK 27:

~~~java
StructuredTaskScope<T, R, R_X extends Throwable>
StructuredTaskScope.Joiner<T, R, R_X extends Throwable>
~~~

- `T`: loại kết quả mà subtasks có thể trả về.
- `R`: loại kết quả mà `join()` trả về.
- `R_X`: loại ngoại lệ mà `join()` có thể ném do policy của joiner.

`join()` có chữ ký khái niệm:

~~~java
R join() throws R_X, InterruptedException;
~~~

Ví dụ, joiner `allSuccessfulOrThrow()` có thể tạo scope với `R = List<T>` và `R_X = ExecutionException`. Đây không chỉ là tài liệu: nó giúp compiler kiểm tra loại checked exception mà caller cần xử lý.

## 4. Vòng đời chuẩn: open → fork → join → close

Sử dụng phổ biến:

~~~java
try (var scope = StructuredTaskScope.open()) {
    var taskA = scope.fork(() -> computeA());
    var taskB = scope.fork(() -> computeB());

    scope.join();

    var result = combine(taskA.get(), taskB.get());
    // Xử lý kết quả bên trong hoặc sau try phù hợp.
}
~~~

Mẫu minh họa giả định `computeA`, `computeB` và `combine` được định nghĩa. Chúng ta sẽ có chương trình đầy đủ ở mục sau.

### 4.1. Chỉ owner được điều phối scope

Thread gọi `StructuredTaskScope.open(...)` trở thành **scope owner**. Owner chịu trách nhiệm `fork`, `join` và `close`. Không chuyển một scope đang mở cho thread khác rồi nhờ thread đó `join()`; API có thể ném `WrongThreadException`.

### 4.2. Không fork sau join

Một scope tạo subtasks ở **forking phase**. Sau khi gọi `join()`, không tiếp tục `fork` task mới vào scope đã join; API từ chối bằng `IllegalStateException`. Với một giai đoạn xử lý mới, mở một scope mới.

### 4.3. Phải join sau khi fork

Nếu owner đã fork các task nhưng bỏ qua việc `join` rồi đóng scope, `close()` hủy và chờ các task kết thúc, sau đó **ném `IllegalStateException`** theo hợp đồng API. Không được dựa vào `close()` như một cơ chế “join ngầm hoàn hảo”.

### 4.4. close chờ thread kết thúc thật

`close` yêu cầu hủy nếu chưa hủy, interrupt các task còn sống và **đợi tất cả các thread được fork trong scope kết thúc**. Vì thế mã ngoài `try` không tiếp tục khi còn thread con của scope đang chạy.

Điều này **không đồng nghĩa scope có hard timeout**: nếu một subtask không hợp tác với interruption (ví dụ mã native không thể dừng), `close` có thể bị trì hoãn vô hạn.

## 5. Chạy và biên dịch preview trên Java 27

Với một file `StructuredScopeDemo.java` sử dụng `StructuredTaskScope`:

~~~shell
javac --release 27 --enable-preview -encoding UTF-8 StructuredScopeDemo.java
java --enable-preview StructuredScopeDemo
~~~

Lệnh `javac` phải là compiler **JDK 27**, và lệnh `java` cũng phải chạy trên **JDK 27**.

Kiểm tra:

~~~shell
java --version
javac --version
~~~

### 5.1. Vì sao phải dùng cả --release 27 và --enable-preview?

Theo quy tắc preview, compiler cần biết đúng **release hiện tại** đang cho phép thử tính năng. Không dùng `javac --release 21 --enable-preview` trên JDK 27 rồi mong thử Structured Concurrency của JDK 27 theo một target cũ.

### 5.2. Cấu hình runtime cũng bắt buộc

Một class biên dịch bằng preview có thể phụ thuộc phiên bản class-file preview của đúng JDK đích (thường có **minor version 65535**). Runtime khác release có thể từ chối class đó ngay cả khi bật preview. Không phân phối artifact preview Java 27 như một JAR thư viện đa nền tảng mà mặc nhiên mong chạy trên Java 21/25/26.

Trong Maven/Gradle, cần cấu hình cả compiler, test JVM và runtime deployment với preview options thích hợp. `--enable-preview` **không phải** `--enable-native-access` hay `--add-modules`.

### 5.3. Chạy preview có rủi ro phiên bản

- API có thể không compile khi nâng JDK tiếp theo.
- Bytecode preview có hạn chế runtime theo release.
- IDE, formatter, static analyzer, agent/coverage cần hỗ trợ JDK 27.
- Có thể phải duy trì một implementation không dùng preview làm phương án thay thế.

Nếu dự án phát hành thư viện cho khách hàng trên nhiều JDK, cần cân nhắc rất kỹ trước khi đưa preview type vào public API.

## 6. Ví dụ hoàn chỉnh: hai dịch vụ độc lập, cần cả hai kết quả

Đây là cách dùng **policy mặc định** của JDK 27: thành công khi tất cả subtasks thành công; lỗi đầu tiên làm scope hủy các task còn lại và `join()` ném `ExecutionException`.

~~~java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.StructuredTaskScope;
import java.util.concurrent.StructuredTaskScope.Subtask;

public class StructuredScopeDemo {

    record Profile(String displayName) {}

    record Orders(int count) {}

    record Dashboard(Profile profile, Orders orders) {}

    static Profile fetchProfile() throws InterruptedException {
        // Mô phỏng lời gọi I/O có hỗ trợ interruption.
        Thread.sleep(150);
        return new Profile("Linh");
    }

    static Orders fetchOrders() throws InterruptedException {
        Thread.sleep(100);
        return new Orders(5);
    }

    static Dashboard loadDashboard()
            throws InterruptedException, ExecutionException {

        try (var scope = StructuredTaskScope.open()) {
            Subtask<Profile> profile =
                    scope.fork(StructuredScopeDemo::fetchProfile);

            Subtask<Orders> orders =
                    scope.fork(StructuredScopeDemo::fetchOrders);

            // Thành công khi cả hai hoàn tất; lỗi thì throw.
            scope.join();

            return new Dashboard(profile.get(), orders.get());
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println(loadDashboard());
    }
}
~~~

Ví dụ chạy với Java 27 theo lệnh ở mục 5. Kết quả mang tính quyết định:

~~~text
Dashboard[profile=Profile[displayName=Linh], orders=Orders[count=5]]
~~~

Thời điểm hai subtask bắt đầu hoặc kết thúc **không có thứ tự cố định**. Cả hai có thể tiến triển đồng thời vì các thao tác không phụ thuộc kết quả lẫn nhau.

### 6.1. Vì sao get() chỉ sau join()?

`Subtask.get()` trả kết quả khi subtask đã thành công, nhưng **không có ngữ nghĩa chờ như `Future.get()`**. Với policy mặc định, sau `scope.join()` thành công, cả hai subtasks đã thành công nên `get()` hợp lệ. Nếu một task thất bại, `join()` ném ngoại lệ, và mã không được tiếp tục gọi `get()` một cách vô điều kiện.

### 6.2. Nếu một task lỗi?

- Scope mặc định được hủy khi có thất bại.
- Task còn chạy sẽ nhận yêu cầu interrupt.
- `join()` ném `ExecutionException` với cause là ngoại lệ của subtask thất bại.
- `close()` vẫn đợi những thread do scope tạo ra kết thúc.

**Hủy không bảo đảm dừng ngay:** một task chặn trên lời gọi không hỗ trợ interruption vẫn có thể khiến `close()` chờ lâu.

## 7. Ví dụ đồng nhất kiểu: Joiner.allSuccessfulOrThrow

Khi các subtasks trả **cùng một kiểu**, có thể dùng Joiner để `join()` trả danh sách kết quả thay vì giữ từng `Subtask`:

~~~java
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.StructuredTaskScope;
import java.util.concurrent.StructuredTaskScope.Joiner;

public class AllResultsDemo {

    static List<String> fetchBoth()
            throws InterruptedException, ExecutionException {

        try (var scope = StructuredTaskScope.open(
                Joiner.<String>allSuccessfulOrThrow())) {

            scope.fork(() -> "kết quả A");
            scope.fork(() -> "kết quả B");

            return scope.join();
        }
    }

    public static void main(String[] args) throws Exception {
        List<String> results = fetchBoth();
        System.out.println(results);
    }
}
~~~

`Joiner.<String>allSuccessfulOrThrow()` đợi tất cả thành công và trả `List<String>` từ `join()`. Nếu một subtask thất bại, joiner yêu cầu hủy và `join()` ném `ExecutionException`. Danh sách là **kết quả nghiệp vụ**, không tự chứa exception của các subtask.

Trong ví dụ này không có lý do dùng subclass kiểu `ShutdownOnFailure` của những preview đời đầu.

## 8. Ví dụ “đường nhanh nhất”: Joiner.anySuccessfulOrThrow

Nếu có hai endpoint dự phòng trả cùng kết quả, bạn chỉ cần **một** kết quả thành công:

~~~java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.StructuredTaskScope;
import java.util.concurrent.StructuredTaskScope.Joiner;

public class FirstSuccessDemo {

    static String query(String replica, long delay)
            throws InterruptedException {

        Thread.sleep(delay);
        return "response from " + replica;
    }

    static String firstSuccess()
            throws InterruptedException, ExecutionException {

        try (var scope = StructuredTaskScope.open(
                Joiner.<String>anySuccessfulOrThrow())) {

            scope.fork(() -> query("replica-A", 300));
            scope.fork(() -> query("replica-B", 100));

            return scope.join();
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println(firstSuccess());
    }
}
~~~

`anySuccessfulOrThrow`:

- Trả kết quả từ **một subtask thành công đầu tiên**.
- Yêu cầu hủy các subtask chưa hoàn tất khi có một kết quả thành công.
- Nếu **tất cả** thất bại, `join()` ném `ExecutionException`.
- `close()` vẫn đợi thread còn lại kết thúc, kể cả sau khi `join()` đã có kết quả.

Không suy luận rằng “replica-B luôn thắng” chỉ vì delay ngắn hơn; scheduling và môi trường thực tế có thể thay đổi. Việc gọi hai dịch vụ dự phòng còn phải tuân thủ **idempotency, rate limits và nghiệp vụ**. Không dùng cạnh tranh nhiều task cho các thao tác ghi có side effect mà chưa có giao thức điều phối.

## 9. Cấu hình tên, timeout và thread factory

JDK 27 cung cấp overload **`StructuredTaskScope.open(configOperator)`** sử dụng policy mặc định nhưng cho phép tùy chỉnh cấu hình.

~~~java
import java.time.Duration;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.StructuredTaskScope;

public class ScopeConfigurationDemo {

    static String load() throws InterruptedException, ExecutionException {
        try (var scope = StructuredTaskScope.open(
                config -> config
                        .withName("load-account")
                        .withTimeout(Duration.ofSeconds(2)))) {

            var a = scope.fork(() -> {
                Thread.sleep(100);
                return "A";
            });
            var b = scope.fork(() -> {
                Thread.sleep(100);
                return "B";
            });

            scope.join();
            return a.get() + b.get();
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println(load()); // AB
    }
}
~~~

Đặc điểm:

- `withName(...)` phục vụ monitoring; không thay đổi logic.
- `withTimeout(...)` bắt đầu đếm **khi scope mở**, không phải chỉ từ thời điểm `join()` được gọi.
- Timeout hết trước hoặc trong `join()` gây hủy scope.
- Với policy mặc định, `join()` ném `ExecutionException`, **cause** thường là `StructuredTaskScope.CancelledByTimeoutException` nếu hết thời gian.
- `close()` vẫn đợi các subtasks chưa dừng. Timeout là **yêu cầu hủy + kết quả timeout**, không phải hard upper bound cho toàn thời gian thực thi method.

### 9.1. Xử lý lỗi và timeout theo cause

~~~java
try {
    String value = ScopeConfigurationDemo.load();
    System.out.println(value);
} catch (ExecutionException e) {
    Throwable cause = e.getCause();
    if (cause instanceof
            StructuredTaskScope.CancelledByTimeoutException) {
        System.err.println("Scope đã timeout");
    } else {
        System.err.println("Subtask thất bại: " + cause);
    }
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    System.err.println("Owner bị yêu cầu hủy");
}
~~~

Đoạn minh họa cần đặt trong một method hoặc nơi có cấu trúc Java phù hợp. `CancelledByTimeoutException` trong JDK 27 **không được dùng làm ngoại lệ checked trực tiếp của `join()` mặc định**; nó là cause của `ExecutionException`.

### 9.2. Cấu hình virtual-thread factory

Theo mặc định, scope tạo **virtual thread không tên** cho mỗi subtask. Có thể đặt tên:

~~~java
var factory = Thread.ofVirtual().name("worker-", 0).factory();

try (var scope = StructuredTaskScope.open(
        cfg -> cfg.withThreadFactory(factory)
                  .withName("sample-scope"))) {
    scope.fork(() -> System.out.println(
            Thread.currentThread().getName()
    ));
    scope.join();
}
~~~

Cấu hình này **không biến việc tạo virtual thread thành một thread pool**. Nếu dùng platform threads thay virtual threads, cần suy nghĩ về giới hạn tài nguyên, độ trễ và nguy cơ thread starvation; thay thread factory không giải quyết mọi deadlock.

## 10. So sánh các join policy phổ biến trên JDK 27

| Policy | Điều kiện chờ / hủy | Kết quả `join()` | Dùng khi |
|---|---|---|---|
| `open()` | Đợi tất cả thành công hoặc task đầu thất bại | `null` hoặc `ExecutionException` | Kết quả các task có kiểu khác nhau |
| `open(configOperator)` | Như policy mặc định nhưng có cấu hình | `null` hoặc `ExecutionException` | Cần tên/timeout/thread factory |
| `Joiner.allSuccessfulOrThrow()` | Tất cả thành công, fail-fast khi lỗi | `List<T>` hoặc `ExecutionException` | Mọi subtask cùng kiểu và đều cần |
| `Joiner.awaitAllSuccessfulOrThrow()` | Tất cả thành công, fail-fast | `null` hoặc `ExecutionException` | Chỉ cần success/failure, tự giữ Subtask handles |
| `Joiner.anySuccessfulOrThrow()` | Có một task thành công là đủ; khi đó hủy còn lại | `T` hoặc `ExecutionException` | Replica, fallback/hedged read |
| `Joiner.allUntil(Predicate)` | Đợi đủ task hoặc predicate báo cần hủy | `List<Subtask<T>>` | Chính sách ngắt theo kết quả custom |

**Không tồn tại một policy “tốt nhất” cho mọi nghiệp vụ.** Quy tắc phản ứng thất bại, timeout và kết quả cần được xác định trước khi chọn joiner.

### 10.1. Default không phải “đợi tất cả dù có lỗi”

Policy mặc định **fail-fast**: có một task thất bại thì các task chưa xong bị yêu cầu hủy và owner có thể nhận lỗi ở `join`. Nếu cần thu thập cả lỗi và thành công của mọi task, dùng chính sách thu thập hoặc logic phù hợp, không giả định default chờ tất cả kết quả.

### 10.2. allUntil khác anySuccessfulOrThrow

`allUntil` cho phép xét **trạng thái/kết quả của từng subtask** bằng predicate để quyết định ngắt. Nó không tự ném lỗi chỉ vì một subtask thất bại. Sau `join()`, danh sách có thể có các subtask ở trạng thái `SUCCESS`, `FAILED` hoặc `UNAVAILABLE` (nếu bị hủy trước khi kết thúc). Caller cần kiểm tra state.

## 11. JDK 27: ánh xạ ngoại lệ có kiểu bằng Joiner

JEP 533 đưa thông tin exception vào generic type `R_X`. Các factory method nhận hàm ánh xạ ngoại lệ, chẳng hạn:

~~~java
Joiner.<String, AppFailure>allSuccessfulOrThrow(AppFailure::new)
~~~

Với `AppFailure` là exception type do ứng dụng tự định nghĩa, `join()` sẽ có hợp đồng ném loại exception đó.

Ví dụ hoàn chỉnh:

~~~java
import java.util.List;
import java.util.concurrent.StructuredTaskScope;
import java.util.concurrent.StructuredTaskScope.Joiner;

public class TypedFailureDemo {

    static class AppFailure extends Exception {
        AppFailure(Throwable cause) {
            super("Một tác vụ con thất bại", cause);
        }
    }

    static List<String> fetchAll()
            throws InterruptedException, AppFailure {

        try (var scope = StructuredTaskScope.open(
                Joiner.<String, AppFailure>
                        allSuccessfulOrThrow(AppFailure::new))) {

            scope.fork(() -> "A");
            scope.fork(() -> "B");

            return scope.join();
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println(fetchAll());
    }
}
~~~

Đây là ví dụ minh họa cách **JDK 27 gắn exception type với Joiner**, không phải một sự bảo đảm rằng exception nghiệp vụ được tạo ra từ mọi loại lỗi theo cùng cách.

Một hàm ánh xạ lỗi nên giữ **cause** gốc để thuận tiện chẩn đoán. Khi timeout, với joiner loại này, hàm ánh xạ sẽ nhận `CancelledByTimeoutException` làm đầu vào theo hợp đồng.

## 12. Subtask không phải Future: trạng thái và kết quả

`StructuredTaskScope.Subtask<T>` là handle cho một task đã fork. Những phương thức chính:

| API | Ý nghĩa |
|---|---|
| `state()` | Trạng thái hiện tại: `UNAVAILABLE`, `SUCCESS`, `FAILED` |
| `get()` | Trả kết quả của task thành công, không phải thao tác chờ |
| `exception()` | Trả throwable nếu task thất bại |
| `fork(Callable)` | Tạo thread chạy subtask trả giá trị |
| `fork(Runnable)` | Tạo thread chạy subtask không trả kết quả; `get()` là `null` khi thành công |

~~~text
Subtask bắt đầu
      |
 UNAVAILABLE ----- scope cancelled ------> UNAVAILABLE*
      |
  +---+----+
  |        |
 SUCCESS  FAILED
  |        |
 get()   exception()

* Một subtask chưa hoàn thành trước khi hủy có thể còn
  trạng thái UNAVAILABLE dù thread đang nhận interrupt.
~~~

Chỉ gọi `get()` với task `SUCCESS` và `exception()` với task `FAILED`. Nếu gọi sai trạng thái, API ném `IllegalStateException`. Trong code owner, việc đọc kết quả thường chỉ thực hiện **sau `join()`**. Trường hợp đặc biệt được Javadoc cho phép là gọi bên trong `Joiner.onComplete` trên task có trạng thái phù hợp.

### 12.1. Kết quả của task bị hủy không có nghĩa là kết quả hợp lệ

Khi scope đã yêu cầu hủy, các task chưa hoàn thành có thể còn chạy trong thời gian ngắn. Không dùng `get()` hoặc giả định task đã dừng chỉ vì `scope.isCancelled()` trả `true`. `close()` phải đợi thread kết thúc thực tế.

## 13. Lỗi của subtask và exception của owner

Một chương trình có ít nhất ba luồng thất bại:

1. **Subtask failure:** Callable ném exception/error; policy có thể hủy scope và `join()` trả lỗi.
2. **Owner interruption:** thread owner bị interrupt trước hoặc khi chờ `join()`; method ném `InterruptedException`.
3. **Resource cleanup failure/structure violation:** `close()` phát hiện owner không join, sai thread hoặc thứ tự scope không đúng.

### 13.1. Xử lý InterruptedException

Nếu không muốn xử lý tại lớp hiện tại, ưu tiên **propagate** bằng `throws InterruptedException` để caller quyết định. Nếu chuyển sang runtime exception, khôi phục trạng thái interrupt:

~~~java
try (var scope = StructuredTaskScope.open()) {
    scope.fork(() -> {
        Thread.sleep(100);
        return "OK";
    });
    scope.join();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Đã yêu cầu hủy", e);
} catch (java.util.concurrent.ExecutionException e) {
    throw new IllegalStateException(
            "Một subtask thất bại", e.getCause()
    );
}
~~~

Khi `join()` bị interrupt, scope vẫn được đóng theo try-with-resources; `close` yêu cầu hủy và đợi con kết thúc. Không nuốt interruption rồi tiếp tục trả kết quả như thể mọi task thành công.

### 13.2. Không gọi join nhiều lần sau khi đã nhận outcome

Trong JDK 27, owner gọi `join()` để lấy outcome **một lần**, trừ trường hợp một lần `join()` trước đó bị `InterruptedException`. Sau khi `join` trả kết quả hoặc lỗi nghiệp vụ, không tiếp tục `join` chỉ để “nhận kết quả lần nữa”.
## 14. Joiner.allUntil: thu thập nhiều kết quả và dừng theo điều kiện

`Joiner.allUntil(Predicate)` phù hợp khi caller muốn quan sát **nhiều kết quả** nhưng có một điều kiện dừng sớm, chẳng hạn tìm kiếm trên nhiều nguồn và ngừng khi một kết quả đạt ngưỡng chất lượng.

~~~java
import java.util.List;
import java.util.concurrent.StructuredTaskScope;
import java.util.concurrent.StructuredTaskScope.Joiner;
import java.util.concurrent.StructuredTaskScope.Subtask;
import java.util.concurrent.StructuredTaskScope.Subtask.State;

public class ConditionalSearchDemo {
    record Candidate(String origin, int score) {}

    static Candidate search(
            String origin, int score, long delay)
            throws InterruptedException {
        Thread.sleep(delay);
        return new Candidate(origin, score);
    }

    public static void main(String[] args)
            throws InterruptedException {

        var joiner = Joiner.<Candidate>allUntil(
                task -> task.state() == State.SUCCESS
                        && task.get().score() >= 90
        );

        try (var scope = StructuredTaskScope.open(joiner)) {
            scope.fork(() -> search("index-A", 60, 100));
            scope.fork(() -> search("index-B", 95, 150));
            scope.fork(() -> search("index-C", 70, 200));

            List<Subtask<Candidate>> subtasks = scope.join();

            for (var task : subtasks) {
                switch (task.state()) {
                    case SUCCESS ->
                        System.out.println(task.get());
                    case FAILED ->
                        System.err.println(task.exception());
                    case UNAVAILABLE ->
                        System.out.println("Chưa có kết quả do hủy");
                }
            }
        }
    }
}
~~~

Điều kiện `task.state() == State.SUCCESS && task.get().score() >= 90` hợp lệ vì `Joiner.onComplete` được phép xem kết quả **đã thành công**. Không gọi `get()` cho task `FAILED` hoặc `UNAVAILABLE`.

### 14.1. Danh sách có thể chứa nhiều trạng thái

Nếu một task đạt score đủ cao trước khi những task khác kết thúc, scope bị hủy. `join()` của `allUntil` trả danh sách các `Subtask` đã fork; một số có thể đã thành công, thất bại hoặc chưa có kết quả khi hủy.

**Không dùng `subtasks.stream().map(Subtask::get)` vô điều kiện.** Phải kiểm tra `state()` trước. Khác với `allSuccessfulOrThrow`, policy `allUntil` không tự biến mọi lỗi task thành exception của `join()`.

### 14.2. Predicate và custom policy phải thread-safe

Predicate có thể được đánh giá trên thread subtask khi hoàn thành. Tránh sửa shared `ArrayList` hoặc counter không atomic bên trong predicate.

Nếu triển khai `Joiner<T,R,R_X>` riêng, callback `onComplete` có thể chạy đồng thời với callback khác hoặc với lời gọi `onFork`, `result`, `timeout`. Phải thiết kế trạng thái joiner an toàn cho truy cập đồng thời.

## 15. Cancellation: interrupt là yêu cầu, không phải ngắt cưỡng bức

Khi policy, timeout hoặc `close` hủy scope:

1. Task chưa bắt đầu có thể không được chạy.
2. Task đang chạy nhận **interrupt**.
3. `join()` có thể trả về/throw sớm theo policy.
4. `close()` vẫn **đợi thread thực sự dừng**.

~~~text
Subtask A: thất bại
     |
     v
Joiner yêu cầu hủy scope
     |
     +-- Subtask B: interrupt
     +-- Subtask C: interrupt
     |
     v
Owner nhận lỗi từ join()
     |
     v
close(): đợi B và C dừng thật
     |
     v
Ra khỏi try-with-resources
~~~

### 15.1. Subtask phải hợp tác với hủy

~~~java
static String fetchData() throws InterruptedException {
    for (int attempt = 0; attempt < 5; attempt++) {
        if (Thread.currentThread().isInterrupted()) {
            throw new InterruptedException("Subtask bị hủy");
        }
        Thread.sleep(100);
    }
    return "ready";
}
~~~

Đối với I/O thật, phải xác minh từng client API có phản ứng với interrupt hoặc timeout thế nào. **Deadline của scope không thay thế timeout của DB/network client.**

### 15.2. Sai lầm: nuốt interrupt vô hạn

~~~java
static void badTask() {
    while (true) {
        try {
            Thread.sleep(1000);
        } catch (InterruptedException ignored) {
            // Sai: cứ tiếp tục chờ, không bao giờ kết thúc.
        }
    }
}
~~~

Nếu task này chạy trong scope, `close()` có thể treo vô hạn sau lỗi hoặc timeout. Việc chạy bằng virtual thread **không** giải quyết một vòng lặp cố tình bỏ qua interruption.

### 15.3. Hủy không rollback side effect

Nếu một subtask đã ghi database, gửi message hoặc sửa file trước khi nhận interrupt, side effect đó có thể đã xảy ra. Structured Concurrency **không cung cấp transaction, exactly-once hay rollback tự động**. Khi dùng policy tranh đua để lấy kết quả nhanh nhất, ưu tiên tác vụ đọc/idempotent hoặc thiết kế cơ chế bù trừ phù hợp.

## 16. Virtual threads và Structured Concurrency là hai khái niệm khác nhau

| Khía cạnh | Virtual threads | Structured Concurrency |
|---|---|---|
| Vấn đề chính | Thread giá rẻ cho nhiều tác vụ chờ I/O | Vòng đời cha–con, join, lỗi, hủy |
| API | `Thread.ofVirtual()`, `Executors.newVirtualThreadPerTaskExecutor()` | `StructuredTaskScope.open/fork/join/close` |
| Trạng thái Java 27 | Ổn định | **Seventh Preview** |
| Tự quản lý nhóm subtasks? | Không | Có |
| Tự hạn chế DB connections? | Không | Không |
| Tăng tốc CPU-bound mặc định? | Không | Không |

`StructuredTaskScope` dùng virtual thread theo mặc định, nhưng có thể cấu hình `ThreadFactory` khác. Điều này không làm thay đổi **ngữ nghĩa scope**.

### 16.1. Không nhầm thread rẻ với tài nguyên vô hạn

Nếu mỗi request fork ba subtask chạm database và có hàng nghìn requests đồng thời, số lượng query vẫn có thể rất lớn. Cần **connection pool, semaphore, rate limit, queue hoặc overload policy**. Scope không tự giới hạn kết nối hoặc tạo backpressure cho downstream.

### 16.2. CPU-bound workload

Parallel computation không mặc định nhanh hơn xử lý tuần tự khi CPU core hoặc memory bandwidth đã hết. Dùng benchmark trên workload thực tế, đo cả throughput lẫn tài nguyên hệ thống.

## 17. So sánh với ExecutorService và Future

`ExecutorService` và `Future` vẫn là API ổn định, hoàn toàn phù hợp với Java 27.

| Tình huống | ExecutorService/Future | StructuredTaskScope preview |
|---|---|---|
| Task nền độc lập, lâu dài | Phù hợp | Không phải trường hợp chính |
| Gộp 2–5 tác vụ I/O cho một request | Được, cần tự phối hợp lỗi/hủy | Phù hợp nếu chấp nhận preview |
| Fail-fast và hủy sibling | Caller phải triển khai | Joiner hỗ trợ |
| Đợi kết quả | `Future.get()` chờ | `join()` chờ, `Subtask.get()` không chờ |
| Truyền kết quả/lỗi | Qua Future | Outcome của `join()` và trạng thái Subtask |
| Dùng cho library đa JDK | Phù hợp | Rủi ro thay đổi preview |
| Scheduled/background jobs | Phù hợp | Không mặc định thay thế |

Ví dụ API ổn định:

~~~java
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    Future<String> a = executor.submit(() -> "A");
    Future<String> b = executor.submit(() -> "B");
    System.out.println(a.get() + b.get());
}
~~~

Mẫu trên giả định đặt trong method có thể ném exception phù hợp. Trong trường hợp một `Future.get()` thất bại, caller cần quyết định có hủy task còn lại, cách chờ cleanup và giới hạn thời gian.

**ExecutorService không phải công nghệ lỗi thời.** Chọn công cụ theo lifecycle công việc: task nền tồn tại lâu hơn request là trường hợp hợp lệ nhưng không nên ép vào một request scope.

## 18. ScopedValue truyền context cho subtasks

`ScopedValue` là API ổn định trong Java 27. Khi owner mở scope bên trong một binding, những subtasks do scope fork sẽ kế thừa binding đó.

~~~java
import java.util.concurrent.StructuredTaskScope;

public class ScopedContextDemo {
    private static final ScopedValue<String> REQUEST_ID =
            ScopedValue.newInstance();

    static String retrieve() {
        return "request-id=" + REQUEST_ID.get();
    }

    public static void main(String[] args) throws Exception {
        String output = ScopedValue.where(
                REQUEST_ID, "req-42"
        ).call(() -> {
            try (var scope = StructuredTaskScope.open()) {
                var task = scope.fork(ScopedContextDemo::retrieve);
                scope.join();
                return task.get();
            }
        });

        System.out.println(output); // request-id=req-42
    }
}
~~~

Scope chụp các binding ở thời điểm mở. Khi fork, JDK kiểm tra những binding đó vẫn hợp lệ theo giao thức cấu trúc.

### 18.1. Shared reference không đồng nghĩa thread-safe

Nếu `ScopedValue` chứa `ArrayList` hoặc DTO mutable và các subtasks cùng sửa, vẫn có data race. Ưu tiên context bất biến, hoặc đồng bộ khi phải dùng shared mutable state.

### 18.2. Không suy từ ScopedValue sang ThreadLocal

`ScopedValue` và `ThreadLocal` có hợp đồng khác nhau. ThreadLocal bình thường có phạm vi mỗi thread, không tự được truyền cho các virtual threads giống ScopedValue. Đừng dùng InheritableThreadLocal thay thế mà không xem quy tắc inheritance của thread factory và yêu cầu bảo mật context.

## 19. Nested scopes: cấu trúc cha–con lồng nhau

Một subtask có thể mở scope riêng rồi fork tiếp:

~~~text
Scope của request
   |
   +-- fetchProfile
   |
   +-- calculateRecommendations
          |
          +-- fetchSignals
          +-- fetchPolicies
          +-- fetchRates
~~~

Ví dụ hai tầng:

~~~java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.StructuredTaskScope;

public class NestedScopeDemo {
    static String recommendations()
            throws InterruptedException, ExecutionException {

        try (var inner = StructuredTaskScope.open()) {
            var signal = inner.fork(() -> "signal");
            var policy = inner.fork(() -> "policy");
            inner.join();
            return signal.get() + "/" + policy.get();
        }
    }

    static String handle()
            throws InterruptedException, ExecutionException {

        try (var outer = StructuredTaskScope.open()) {
            var profile = outer.fork(() -> "profile");
            var recommendation = outer.fork(
                    NestedScopeDemo::recommendations
            );

            outer.join();
            return profile.get() + ":" + recommendation.get();
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println(handle());
    }
}
~~~

Nếu inner scope lỗi, việc `recommendations()` ném `ExecutionException` trở thành lỗi của **outer subtask**, và outer scope xử lý nó theo policy của mình.

### 19.1. Cần đóng đúng thứ tự

Scope con phải đóng theo trật tự vòng đời. Khi đóng scope ngoài trước scope lồng trong do cùng owner mở, hoặc thoát `ScopedValue` binding sai cấu trúc, có thể phát sinh `StructureViolationException`. Không catch rồi bỏ qua. Dùng try-with-resources thể hiện quan hệ lồng nhau rõ ràng.

## 20. Quan sát cấu trúc qua thread dump

Trên JDK 27, có thể tạo JSON thread dump:

~~~shell
jcmd <PID> Thread.dump_to_file -format=json thread-dump.json
~~~

Thay `<PID>` bằng process ID thực tế của ứng dụng. Cần quyền attach phù hợp. JSON có thể thể hiện **thread containers**, scope và virtual threads cùng quan hệ parent/owner.

### 20.1. Thread dump không phải distributed tracing

Thread dump thể hiện tình trạng tại một thời điểm, không ghi đầy đủ mỗi request/response hoặc cuộc gọi cross-service. Khi cần truy vết, kết hợp tracing, log với correlation ID, metrics và tên scope.

### 20.2. Không đưa bí mật vào scope name

Không đặt token, mật khẩu hoặc thông tin cá nhân trong tên scope/thread; thông tin này có thể xuất hiện trong thread dumps và log chẩn đoán.

### 20.3. isCancelled chưa nói mọi task đã chết

`isCancelled()` có thể trả true trước khi các thread được interrupt hoặc kết thúc. Chỉ khi `close()` hoàn tất mới có bảo đảm không còn thread được fork trong scope đang chạy.

## 21. Deadline tổng và timeout từng downstream

Một request thường có nhiều giới hạn:

- Deadline của HTTP request.
- Timeout kết nối và đọc của từng external service.
- Timeout DB query.
- Timeout của scope.
- Thời gian cleanup sau hủy.

~~~java
try (var scope = StructuredTaskScope.open(
        c -> c.withTimeout(Duration.ofSeconds(3)))) {
    scope.fork(() -> remoteCallA());
    scope.fork(() -> remoteCallB());
    scope.join();
}
~~~

Đoạn khái niệm giả định các hàm remote và imports đã được định nghĩa. Timeout bắt đầu **khi scope mở**, không chỉ lúc gọi `join()`.

### 21.1. Đừng cộng nhiều timeout độc lập vượt deadline

Nếu request có tổng ngân sách 5 giây, một subtask đợi DB 5 giây rồi HTTP thêm 5 giây đã vượt yêu cầu. Truyền deadline chung hoặc tính thời gian còn lại cho mỗi downstream call.

### 21.2. Timeout không phải hard upper bound

Scope hết timeout sẽ hủy và cho `join()` outcome timeout, nhưng `close()` vẫn đợi task không hợp tác. Đảm bảo downstream clients có timeout riêng và cancellation thực sự có khả năng tác động tới I/O đang chạy.

### 21.3. Custom Joiner xử lý timeout ra sao?

Trong JDK 27, `Joiner.timeout()` được dùng để tạo outcome khi timeout cấu hình hết hạn. Joiner mặc định thường ném exception có `CancelledByTimeoutException` làm cause. Một custom joiner có thể thiết kế trả **partial results**, nhưng phải ghi rõ chúng chưa gồm tất cả subtasks và không được ngộ nhận là thành công hoàn toàn.

## 22. Custom Joiner: chỉ dùng khi thật sự cần chính sách riêng

JDK 27 có các factory Joiner đủ cho phần lớn bài toán. Chỉ tự tạo `Joiner<T,R,R_X>` khi cần chính sách như:

- Dừng khi có tối thiểu K kết quả thành công.
- Dừng khi kết quả vượt ngưỡng nghiệp vụ.
- Thu thập thống kê kết quả và lỗi.
- Cho phép trả partial result khi timeout, với điều kiện rõ ràng.

| Method | Chức năng |
|---|---|
| `onFork(Subtask)` | Gọi khi có task được fork; có thể yêu cầu hủy |
| `onComplete(Subtask)` | Gọi khi task thành công/thất bại; có thể gọi đồng thời |
| `result()` | Tạo outcome khi hoàn tất hoặc hủy không vì timeout |
| `timeout()` | Tạo outcome khi timeout của scope hết hạn |

**Custom Joiner phải thread-safe.** Không dùng `ArrayList` mutable bị nhiều callback `onComplete` sửa mà thiếu lock. `onComplete` có thể chạy song song với `onFork`, `result` và `timeout`.

### 22.1. Joiner không nên chứa logic nghiệp vụ nặng

Joiner nên quyết định **policy và kết quả điều phối**; những việc như ghi database hoặc gửi message nên nằm ở subtask/application layer. Một Joiner callback chặn lâu có thể ảnh hưởng tiến độ hoàn tất/cancellation.

### 22.2. Không reuse Joiner instance

Mỗi scope cần một Joiner mới. **Không chia sẻ Joiner instance giữa các scope hoặc tái sử dụng sau khi scope đã đóng**, vì Joiner có thể giữ trạng thái từng scope.

### 22.3. Thường không cần viết Joiner riêng

Nếu cần “mọi task đều thành công”, dùng `Joiner.allSuccessfulOrThrow()`. Nếu cần “một task thành công là đủ”, dùng `Joiner.anySuccessfulOrThrow()`. Nếu cần “điều kiện dừng dựa trên từng subtask”, thử `Joiner.allUntil(Predicate)` trước khi tự implement một policy phức tạp.

## 23. Những lỗi thiết kế dễ gặp

| Sai lầm | Tác động | Hướng sửa |
|---|---|---|
| Copy `ShutdownOnFailure` từ Java 21/22 | Không khớp API JDK 27 | `StructuredTaskScope.open()` hoặc Joiner |
| Bắt `FailedException` theo JDK 26 | Sai checked exception trên 27 | `ExecutionException` cho policy mặc định |
| Khai báo `StructuredTaskScope<T,R>` | Thiếu generic parameter `R_X` | Dùng `<T,R,R_X>` hoặc `var` |
| Quên `--enable-preview` | Compiler/runtime từ chối | Bật ở compiler, test JVM, runtime JDK 27 |
| Dùng `--release 21` để compile preview JDK 27 | Không hợp lệ | `--release 27 --enable-preview` |
| Fork sau `join()` | `IllegalStateException` | Mở scope mới cho giai đoạn mới |
| Không join sau fork | `close()` có thể ném `IllegalStateException` | Luôn attempt join |
| Thread không phải owner gọi `join` | `WrongThreadException` | Chỉ owner điều phối scope |
| Gọi `Subtask.get` trước `join` | Không có dữ liệu hợp lệ/IllegalStateException | Join trước; kiểm tra trạng thái |
| Coi `isCancelled()` là mọi task đã dừng | Trả response khi vẫn còn thread | Để `close()` bảo đảm cleanup |
| Task cố tình nuốt interrupt | Close chờ vô hạn | Cooperative cancellation, timeout I/O |
| Race hai thao tác ghi | Side effect trùng lặp | Idempotency hoặc policy khác |
| Cho rằng scope timeout là hard timeout | Request vẫn chờ cleanup | Downstream timeout và deadline |
| Chia sẻ mutable object qua ScopedValue | Data race | Context immutable hoặc synchronization |
| Fork quá nhiều DB jobs | Quá tải tài nguyên | Connection pool, quota, rate limit |
| Reuse custom Joiner | Trạng thái lẫn giữa scopes | Tạo Joiner mới |
| Đưa preview type vào public API thư viện | Client đa JDK khó dùng | Đặt sau interface ổn định |
| Chỉ test đường thành công | Bỏ sót cancellation/hang | Fault injection và timeout tests |
| Không lưu build JDK trong báo cáo | Không tái lập được | Pin JDK 27 vendor/build |

## 24. Khi nào nên và không nên thử Structured Concurrency?

| Nhu cầu | Đánh giá |
|---|---|
| Một HTTP request cần dữ liệu I/O độc lập rồi tổng hợp | Ứng viên tốt nếu chấp nhận preview |
| Fail-fast và cancel các sibling tasks | Ứng viên tốt |
| Dùng kết quả từ replica đọc nhanh nhất | Ứng viên tốt với `anySuccessfulOrThrow` |
| Code thư viện phải chạy Java 17/21/25 | Tránh lộ preview JDK 27 trong public API |
| Background service chạy liên tục | Ưu tiên executor/scheduler và lifecycle riêng |
| Native call hoặc I/O không hỗ trợ interruption | Rủi ro `close` chờ lâu |
| Dùng cho hàng nghìn CPU-bound tasks | Cần benchmark và giới hạn core |
| Mỗi subtask có side effect khó rollback | Cần thiết kế nghiệp vụ trước khi dùng race |
| Doanh nghiệp không cho phép preview production | Chỉ dùng ở thử nghiệm |
| Muốn tìm hiểu, thu phản hồi API trên JDK 27 | Phù hợp trong môi trường kiểm soát |

### 24.1. Ba quyết định thực tế

- **EXPERIMENT:** thử trong module nội bộ đã pin JDK 27, có kiểm thử lỗi và phương án rollback.
- **HOLD:** giữ `ExecutorService`/`Future` ổn định và đánh giá lại khi policy sản phẩm cho phép.
- **REJECT_FOR_USE_CASE:** không phù hợp với vòng đời task hoặc cancellation của nghiệp vụ.

Không có quy tắc “Structured Concurrency mặc định tốt hơn mọi phương án” cho mọi ứng dụng. Nó mạnh về **vòng đời và phối hợp nhiệm vụ con**, không thay thế transaction, backpressure, rate limiting hoặc quản lý tài nguyên.

## 25. Thử nghiệm có kiểm soát: thiết kế test matrix

Không kết luận API “an toàn” chỉ vì một chương trình in kết quả thành công.

| Tình huống | Kết quả/tiêu chí kiểm tra |
|---|---|
| Cả hai subtasks thành công | `join()` trả bình thường, kết quả đúng |
| Task A lỗi nhanh, task B đang chờ | `join()` ném `ExecutionException`, B bị yêu cầu hủy |
| Task B bị interrupt | B cleanup và kết thúc hữu hạn |
| Cả hai task thất bại | Policy mặc định ném lỗi; kiểm tra cause |
| Một task thành công, task còn lại chưa xong | `anySuccessfulOrThrow` lấy kết quả, task còn lại được hủy |
| Không có task nào thành công | `anySuccessfulOrThrow` ném lỗi theo hợp đồng |
| Task nhận interrupt nhưng không hợp tác | Phát hiện nguy cơ close chờ |
| Scope timeout | Xác nhận cause `CancelledByTimeoutException` |
| Timeout xảy ra trước khi gọi join | Scope bị hủy theo policy khi timeout |
| Owner bị interrupt trong join | `InterruptedException`, cleanup vẫn diễn ra |
| Không gọi join sau fork | `close` báo misuse |
| Fork sau join | `IllegalStateException` |
| Thread khác gọi fork/join/close | `WrongThreadException` |
| `Subtask.get()` không ở SUCCESS | `IllegalStateException` |
| `allUntil` cancel giữa chừng | Có thể có `UNAVAILABLE`; không đọc get tùy tiện |
| Nested scope bị đóng sai thứ tự | `StructureViolationException` |
| ScopedValue binding trong subtask | Context đúng, không rò sau scope |
| Custom Joiner có race | Stress test với nhiều task hoàn thành đồng thời |
| JDK preview flag thiếu | Biên dịch/chạy bị từ chối như dự kiến |

### 25.1. Test không nên dùng sleep để thay cho sự kiện

~~~java
Thread.sleep(100);
// Không chứng minh task khác đã hoàn tất hoặc bị hủy.
~~~

Trong test nên dùng `CountDownLatch`, `CompletableFuture` hoặc synchronization thích hợp để điều phối chính xác tình huống, đồng thời đặt deadline **cho chính test** để tránh treo CI.

### 25.2. Fault injection

Tạo các subtask mô phỏng:

- Ném `IOException`.
- Bị interrupt trong `Thread.sleep`.
- Bỏ qua interrupt (chạy **chỉ trong test process có timeout ngoài**, không chạy thử trực tiếp vô hạn).
- Hết thời gian chờ downstream.
- Thực hiện side effect trước khi bị hủy.
- Thất bại trong cleanup.

Mục tiêu là quan sát `join`, `close` và quy tắc nghiệp vụ, không chỉ thời gian chạy nhanh/chậm.

## 26. Compatibility matrix cho JDK đích

Vì là preview, **phiên bản JDK là một phần của API contract**.

| Vấn đề | JDK 25 | JDK 26 | **JDK 27** |
|---|---|---|---|
| Structured Concurrency | Fifth Preview | Sixth Preview | **Seventh Preview** |
| JEP | 505 | 525 | **533** |
| API chính | Scope/Joiner generics hai tham số | Tiếp tục điều chỉnh timeout và Joiner | Generics **ba tham số**, ngoại lệ có kiểu |
| Runtime flag | `--enable-preview` | `--enable-preview` | **`--enable-preview`** |
| Code đã compile preview cho release khác | Không mặc nhiên tương thích | Không mặc nhiên tương thích | Không mặc nhiên tương thích |
| Exception policy mặc định | Phải đọc API 25 | Phải đọc API 26 | `ExecutionException` |

**Không nên làm một bản JAR sử dụng preview rồi phát hành cho mọi JDK 25–27**. Hãy compile và test theo mỗi release với source tương ứng nếu thực sự cần hỗ trợ đa bản JDK; hoặc giữ phần API công khai ổn định và dùng implementation riêng theo runtime.

### 26.1. Thay ví dụ đời cũ

Ví dụ kiểu API đời đầu:

~~~java
// MẪU CŨ — KHÔNG DÙNG TRONG JDK 27:
// try (var scope = new StructuredTaskScope.ShutdownOnFailure()) {
//     ...
//     scope.join().throwIfFailed();
// }
~~~

Mẫu JDK 27:

~~~java
try (var scope = StructuredTaskScope.open()) {
    var a = scope.fork(() -> "A");
    var b = scope.fork(() -> "B");

    scope.join();
    System.out.println(a.get() + b.get());
}
~~~

Đoạn thứ hai đặt trong method đã import `StructuredTaskScope` và xử lý `InterruptedException`/`ExecutionException` thích hợp. Không bê nguyên `throwIfFailed`, `ShutdownOnSuccess` hoặc `joinUntil` từ bài viết cũ.

### 26.2. Đổi cách bắt lỗi từ JDK 26

JDK 27 dùng `ExecutionException` trong policy mặc định; `FailedException` theo những bản preview cũ không phải exception phải catch trong ví dụ JDK 27. Vì `ExecutionException` là checked exception, compiler giúp nhắc caller xử lý hoặc khai báo `throws`.

Nếu có custom Joiner, `R_X` có thể là loại exception khác do ứng dụng xác định, vì thế không nên viết một catch chung và giả định mọi Joiner đều ném `ExecutionException`.

### 26.3. Không nâng API vì đoán trước tương lai

Nếu một phiên bản JDK tương lai final hóa hoặc đổi Structured Concurrency, phải **đọc lại JEP/API của chính bản đó**. Đừng ghi code cho JDK 27 dựa vào tài liệu early-access hoặc đặc tả của một release tương lai chưa được xác nhận.

## 27. Cấu hình build/test/deploy và kiểm soát preview

### 27.1. Compiler + runtime

Ví dụ trên command line:

~~~shell
javac --release 27 --enable-preview -encoding UTF-8 StructuredScopeDemo.java
java --enable-preview StructuredScopeDemo
~~~

Trong CI, xác nhận chính xác:

- JDK chạy compiler là JDK 27.
- Test runner thực sự chạy JDK 27.
- Runtime image/container JDK 27.
- `--enable-preview` có ở **cả compiler và test/runtime** cần thiết.
- Dependency, Java agent, coverage và IDE nhận đúng class-file version.

### 27.2. Maven (minh họa)

~~~xml
<properties>
    <maven.compiler.release>27</maven.compiler.release>
</properties>
~~~

Cần kết hợp cấu hình `--enable-preview` cho Maven Compiler Plugin theo phiên bản được dự án dùng, và cấu hình `argLine` hoặc tương đương để test runner chạy với preview. Đoạn XML này chỉ minh họa một phần `pom.xml`, **không phải file cấu hình hoàn chỉnh**.

Một build Maven chạy bằng JDK 27 vẫn có thể fork test JVM khác; kiểm tra log runtime của test. Đừng chỉ xem `mvn --version`.

### 27.3. Gradle (minh họa)

Với Gradle Java plugin, người dùng có thể thiết lập toolchain Java 27 và cấu hình `--enable-preview` cho tác vụ compile/test/run phù hợp.

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(27)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("--enable-preview")
}

tasks.withType<Test>().configureEach {
    jvmArgs("--enable-preview")
}
~~~

Đoạn trên chỉ cấu hình phần compile/test cơ bản, không phải mọi task chạy Java hay mọi plugin trong project. Kiểm tra phiên bản Gradle/third-party plugins, JavaExec/application tasks và runtime deployment riêng.

### 27.4. Tách mã preview khỏi lõi ứng dụng

Một kiến trúc dễ quản lý:

~~~text
application/
    stable-api/
         RequestAggregator
    implementation-stable/
         ExecutorService + Future
    implementation-jdk27-preview/
         StructuredTaskScope + Joiner
~~~

Cấu trúc minh họa. Lớp `stable-api` không nên để lộ `StructuredTaskScope` preview type; hai implementation có thể trả cùng DTO hoặc dùng cùng interface ổn định.

Điều này giảm rủi ro khi thử nghiệm, rollback và nâng JDK đợt sau. Tuy vậy, **không** tải class preview vào một JVM thiếu hỗ trợ rồi trông đợi nó hoạt động; cơ chế phân phối/module lựa chọn implementation phải tuân thủ runtime tương thích.

## 28. Case study: đánh giá cho API tổng hợp tài khoản

Một ứng dụng có handler `GET /account/summary` cần ba lần gọi độc lập:

- `profile-service`: dữ liệu bắt buộc.
- `orders-service`: dữ liệu bắt buộc.
- `credit-service`: dữ liệu bắt buộc.

### 28.1. Hợp đồng cần xác định trước

- Nếu một downstream thất bại, response có phải lỗi không?
- Có cho phép trả thiếu dữ liệu không?
- Deadline tổng của request là bao nhiêu?
- Tác vụ nào có side effect hay chỉ đọc?
- Client downstream có hỗ trợ interruption và timeout không?
- Có giới hạn concurrency của từng downstream không?
- Khi request bị hủy, cancellation có được truyền đến handler không?

Nếu **cả ba kết quả đều bắt buộc** và các call có thể bị hủy hợp tác, scope mặc định là ứng viên tốt.

### 28.2. Thiết kế có kiểm soát

~~~text
Owner: handle request
    |
    +-- open(default, timeout)
           |
           +-- fetchProfile (downstream timeout)
           +-- fetchOrders  (downstream timeout)
           +-- fetchCredit  (downstream timeout)
    |
    +-- join (fail-fast)
    |
    +-- combine typed results
    |
    +-- close scope
    |
    +-- emit response / error
~~~

Nên dùng một **deadline chung** ở request layer, truyền thời gian còn lại đến clients. Nếu một client bị timeout mà không phản ứng với interrupt, `close()` vẫn có thể chờ, nên phải test rõ trước khi dùng cho production.

### 28.3. Các chỉ số đánh giá

| Chỉ số | Câu hỏi |
|---|---|
| P50/P95/P99 latency | Thời gian request tổng có cải thiện không? |
| Error propagation | Cause có đúng nguồn lỗi không? |
| Cancellation latency | Sau khi lỗi, các task khác dừng nhanh cỡ nào? |
| Live virtual threads | Có task nào tồn tại ngoài scope không? |
| DB/HTTP concurrent connections | Có gây quá tải downstream không? |
| Heap/native memory | Có tăng lượng task state/stack giữ lại không? |
| Retry/side effects | Có duplicate call không mong muốn không? |
| Observability | Thread dump/traces có nhóm đúng request không? |
| Operational overhead | Build, startup, diagnostics và rollback có an toàn không? |

### 28.4. Quyết định phải có điều kiện

Ví dụ kết luận:

> Có thể thử Structured Concurrency JDK 27 trong một implementation nội bộ, nếu có JDK 27 preview flags ở tất cả môi trường, clients có timeout/cancellation hợp tác, test lỗi/timeout đầy đủ và có phương án quay lại ExecutorService. Chưa nên coi API đã ổn định hoặc công bố public API phụ thuộc preview.

Đây là **khung quyết định**, không phải chứng nhận production readiness cho một hệ thống cụ thể.

## 29. Tiêu chí lựa chọn và phê duyệt thử nghiệm

| Tiêu chí | Điều cần xác minh | Blocker khi |
|---|---|---|
| Trạng thái | JDK 27 Seventh Preview, JEP 533 | Team không cho preview |
| Phiên bản | JDK 27 compiler, test, runtime đúng build | Có môi trường buộc JDK khác |
| API | Source dùng đúng `open/fork/join/Joiner` JDK 27 | Copy mẫu cũ không compile |
| Lifecycle | Tất cả subtask kết thúc trước khi thoát scope | Uncooperative task treo |
| Error policy | Fail-fast, all-success, any-success đúng nghiệp vụ | Side effects không an toàn |
| Timeout | Scope và downstream deadlines được quản lý | Không có thời hạn thực |
| Resources | DB/HTTP limits, rate limit, queue/bulkhead | Có thể gây bão tài nguyên |
| Observability | Logs, tracing, JSON thread dump phù hợp | Không đủ chẩn đoán |
| Testing | Success, fail, timeout, interrupt, nested, cancellation | Chỉ có happy path |
| Packaging | Preview enabled compile/test/runtime | Không kiểm soát runtime |
| Rollback | Có stable adapter/fallback được test | Không có phương án quay lại |
| Documentation | Có JDK build, JEP/API refs, owner và trạng thái | Không truy nguyên được |

### 29.1. Ma trận trạng thái đề xuất

- **UNKNOWN:** chưa kiểm tra đúng JDK/API.
- **SUPPORTED_BY_JDK_PREVIEW:** có API đúng JDK, nhưng chưa test dự án.
- **TESTED:** kiểm thử kỹ thuật trên tổ hợp JDK/source cụ thể đạt.
- **READY_FOR_CONTROLLED_EXPERIMENT:** đạt các điều kiện governance và rollback.
- **NOT_APPROVED_FOR_PRODUCTION:** chưa có quyền dùng preview hoặc chưa đủ bằng chứng.
- **BLOCKED:** có lỗi không thể chấp nhận trong deadline/cancellation/behavior.

Đây là trạng thái quản lý dự án đề xuất, **không phải enum của Java**.

## 30. Những câu hỏi thường gặp

### 30.1. Java 27 đã final hóa Structured Concurrency chưa?

**Chưa.** Theo JDK 27 Release Notes và JEP 533, đây là **Seventh Preview**. Cần bật `--enable-preview` và chấp nhận rủi ro thay đổi API ở JDK khác.

### 30.2. Java 27 có StructuredTaskScope.ShutdownOnFailure không?

Không nên dùng mẫu subclass này cho API hiện tại. Trong Java 27, dùng `StructuredTaskScope.open()` hoặc các `Joiner` phù hợp. Mẫu subclass nằm trong ví dụ của các vòng preview đời đầu.

### 30.3. Vì sao join ném ExecutionException chứ không phải FailedException?

JEP 533 chỉnh mô hình exception. Trong Java 27, policy mặc định của `join()` ném `ExecutionException` khi subtask lỗi hoặc scope timeout; với timeout, cause là `CancelledByTimeoutException`.

### 30.4. get() của Subtask có chặn như Future.get() không?

Không. Nó chỉ trả kết quả khi trạng thái đã thành công, không tự chờ. Owner thường phải `join()` trước khi dùng.

### 30.5. Scope đóng có chắc mất dưới 2 giây nếu withTimeout(2s)?

Không. Timeout yêu cầu hủy và làm `join` có outcome theo policy. `close` vẫn đợi thread con thực sự dừng; task bỏ qua interrupt có thể chặn vô hạn.

### 30.6. Dùng scope rồi có cần Semaphore nữa không?

Có thể vẫn cần. Scope quản lý vòng đời nhóm task, **không** giới hạn kết nối tới database hoặc concurrency downstream.

### 30.7. Có thể mở scope con trong một subtask không?

Có. Mỗi scope có owner riêng và phải đóng đúng quan hệ lồng nhau. Lỗi từ inner scope có thể lan thành thất bại của outer subtask.

### 30.8. Nên dùng CompletableFuture hay StructuredTaskScope?

`CompletableFuture` mạnh về composition bất đồng bộ và graph của future; `StructuredTaskScope` mạnh về mô hình synchronous style kết hợp nhiều subtasks với vòng đời có cấu trúc. Chọn theo hợp đồng và mức chấp nhận preview.

## 31. Bài tập thực hành

### Bài 1: Default scope fail-fast

Tạo ba subtasks, hai task trả giá trị và một task ném `IOException`. Kiểm tra `join()` ném `ExecutionException` và kết quả của task chưa xong không bị đọc vô điều kiện.

**Câu hỏi:** Vì sao không thể chỉ gọi `Subtask.get()` thay cho `join()`?

### Bài 2: So sánh joiner policies

Viết hai phiên bản chạy ba tác vụ đồng loại: một dùng `allSuccessfulOrThrow`, một dùng `anySuccessfulOrThrow`.

**Yêu cầu:** mô tả sự khác biệt khi cả ba thành công, một thất bại, tất cả thất bại và một tác vụ rất chậm.

### Bài 3: Timeout và close

Dùng `withTimeout(Duration.ofMillis(200))` với một subtask ngủ dài nhưng hỗ trợ interrupt. Bắt `ExecutionException`, xem cause.

**Câu hỏi:** Làm thế nào để kiểm thử trường hợp subtask không phản hồi interrupt mà **không treo tiến trình test chính**? Gợi ý: process riêng có watchdog.

### Bài 4: ScopedValue

Tạo `ScopedValue<String>` chứa request ID, mở scope bên trong binding và cho hai subtask in ID.

**Câu hỏi:** Nếu binding chứa một object mutable và hai task sửa cùng lúc thì còn an toàn không?

### Bài 5: allUntil

Sử dụng ba tác vụ trả `record Candidate(int score)`. Chọn predicate dừng khi một kết quả có score ít nhất 90. Quan sát trạng thái `SUCCESS/FAILED/UNAVAILABLE` của từng subtask sau `join()`.

**Câu hỏi:** Vì sao không được gọi `get()` trên mọi task trong danh sách?

### Bài 6: Kiểm tra tính tương thích

Đối chiếu chữ ký `StructuredTaskScope` và `Joiner` ở JDK 26 và 27 theo API docs, rồi thử compile code theo JDK 27 với và không có preview flag.

**Câu hỏi:** Vì sao việc bật `--enable-preview` trên JDK khác không tự bảo đảm chạy được bytecode preview của JDK 27?

### Bài 7: Thiết kế quyết định production

Lập bảng so sánh `ExecutorService/Future` và `StructuredTaskScope` cho một API cần hai external calls. Ghi rõ cancellation semantics, timeout, resource limit, deploy support, rollback và owner.

## 32. Checklist trước khi áp dụng

- [ ] Đã xác định chính xác JDK mục tiêu là Java 27 và đọc API docs của **27** chưa?
- [ ] Đã ghi Structured Concurrency là **Seventh Preview / JEP 533**, không final?
- [ ] Compile và runtime đã bật `--enable-preview` cho đúng Java 27?
- [ ] Không dùng API `ShutdownOnFailure/ShutdownOnSuccess` đời cũ?
- [ ] Đã cập nhật `StructuredTaskScope<T,R,R_X>` và `Joiner<T,R,R_X>` nếu khai báo generic?
- [ ] Có catch/propagate `ExecutionException` trong policy mặc định?
- [ ] Với custom Joiner, có xử lý đúng kiểu `R_X`?
- [ ] Mỗi scope mở trong `try-with-resources`?
- [ ] Chỉ owner fork/join/close?
- [ ] Có `join()` sau khi fork và không fork sau join?
- [ ] Không đọc `Subtask.get()` khi chưa thành công?
- [ ] Mỗi task có thể hoàn tất hoặc hủy trong thời gian hợp lý?
- [ ] `close()` không bị kẹt bởi uninterruptible/blocking task?
- [ ] Có deadline tổng và timeout downstream?
- [ ] Race policy chỉ dùng khi có thể chấp nhận side effects và duplicate calls?
- [ ] Có hạn mức connections, queue và tài nguyên downstream?
- [ ] `ScopedValue` binding không chứa shared mutable state không đồng bộ?
- [ ] Nested scopes được đóng đúng thứ tự?
- [ ] Custom Joiner thread-safe và không tái sử dụng qua scopes?
- [ ] Có unit/integration/fault-injection tests cho failure/timeout/cancellation?
- [ ] Có logs, metrics, thread dumps và tracing phù hợp?
- [ ] Public API của thư viện không vô tình phụ thuộc preview nếu phải hỗ trợ đa JDK?
- [ ] Có owner, tiêu chí phê duyệt và fallback stable implementation?
- [ ] Có pin source revision, JDK vendor/build và cấu hình preview khi kiểm thử?
- [ ] Có kế hoạch đánh giá lại khi đổi JDK release?

## 33. Tóm tắt

- **Structured Concurrency trong Java 27 vẫn là Seventh Preview (JEP 533)**; chưa phải API vĩnh viễn.
- `StructuredTaskScope` nhóm các task liên quan trong một scope có owner, fork, join và close.
- **JDK 27 sử dụng `StructuredTaskScope<T,R,R_X>` và `Joiner<T,R,R_X>`**; loại ngoại lệ của `join()` nằm trong generic parameter.
- Policy mặc định fail-fast: `join()` thành công nếu tất cả task thành công, hoặc ném `ExecutionException` khi một task lỗi.
- Các factory Joiner như `allSuccessfulOrThrow`, `anySuccessfulOrThrow` và `allUntil` giải quyết các kiểu phối hợp khác nhau.
- `Subtask.get()` **không tự chờ**; sau join phải đọc đúng trạng thái và outcome.
- Timeout từ cấu hình bắt đầu khi scope mở; **`close()` vẫn đợi thread con dừng**, nên task phải hợp tác với interruption.
- `ScopedValue` có thể truyền context vào subtasks, nhưng không tự làm mutable object trở nên thread-safe.
- Virtual threads và Structured Concurrency bổ trợ nhau, không thay thế rate limiting, transactions, resource quotas hoặc load testing.
- Khi sử dụng preview, **pin JDK 27, bật `--enable-preview` ở compiler và runtime**, viết tests cho lỗi/hủy/timeout và giữ phương án rollback.
- Chỉ áp dụng khi quan hệ cha–con rõ ràng và tổ chức chấp nhận preview; `ExecutorService/Future` vẫn là lựa chọn ổn định phù hợp ở nhiều tình huống.

## 34. Tài liệu chính thức cần đối chiếu

- [JDK 27 Release Notes — Structured Concurrency (Seventh Preview)](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)
- [JEP 533 — Structured Concurrency (Seventh Preview)](https://openjdk.org/jeps/533)
- [Oracle Java SE 27 — Structured Concurrency Developer Guide](https://docs.oracle.com/en/java/javase/27/core/structured-concurrency.html)
- [StructuredTaskScope — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html)
- [StructuredTaskScope.Joiner — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Joiner.html)
- [StructuredTaskScope.Subtask — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Subtask.html)
- [StructuredTaskScope.Configuration — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Configuration.html)
- [Java SE 27 Preview List](https://docs.oracle.com/en/java/javase/27/docs/api/preview-list.html)
- [Preview Features — Java SE 27](https://docs.oracle.com/en/java/javase/27/language/preview-language-vm-features.html)
- [Structured Concurrency — significant changes in JDK 27](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html)
- [Java SE 27 — Virtual Threads](https://docs.oracle.com/en/java/javase/27/core/virtual-threads.html)
- [JVM Specification 27 — Preview class files](https://docs.oracle.com/en/java/javase/27/docs/specs/jvms/jvms-1.html)

**Quy tắc kiểm chứng:** các ví dụ trong bài dùng API có trong **Java SE 27**. Khi đổi sang JDK khác, phải tra tài liệu API và preview status của chính JDK đó; không giả định chữ ký hoặc hành vi giữ nguyên.
