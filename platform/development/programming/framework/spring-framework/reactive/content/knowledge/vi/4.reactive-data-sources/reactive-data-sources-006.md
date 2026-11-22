# Chuyển CompletableFuture thành Mono và xem xét thời điểm khởi chạy

## 1. Vì sao phải phân biệt thời điểm tạo CompletableFuture với thời điểm subscribe Mono?

Trong một ứng dụng Spring WebFlux, có thể bạn phải tích hợp một thư viện Java trả về **CompletableFuture<T>**: HTTP client bất đồng bộ, SDK cloud, API truy vấn từ dịch vụ bên ngoài hoặc một tác vụ nền. Trong khi đó, service và controller WebFlux thường trả về **Mono<T>** để tiếp tục dùng các operator Reactor và để framework quản lý vòng đời request.

Reactor cung cấp phương thức **Mono.fromFuture(...)** để chuyển tín hiệu hoàn tất của CompletableFuture thành Mono: hoàn tất thành công với một giá trị thì Mono phát tối đa một phần tử; hoàn tất không có giá trị (null) thì Mono hoàn tất rỗng; hoàn tất lỗi thì Mono phát onError.

Câu hỏi khó nhất không phải cú pháp chuyển đổi, mà là **tác vụ bất đồng bộ thực sự được khởi chạy vào lúc nào**.

- **CompletableFuture đại diện cho một công việc/kết quả có thể đã được khởi chạy.** Nếu bạn gọi API bất đồng bộ hoặc CompletableFuture.supplyAsync(...) ngay lúc khai báo biến, công việc thường đã được gửi đi, dù chưa có ai subscribe Mono.
- **Mono mô tả một Publisher có vòng đời đăng ký.** Trong nhiều pipeline Reactor, việc tính toán được kích hoạt khi subscribe. Tuy nhiên, Mono được tạo từ **một Future đã có sẵn** không thể quay ngược thời gian để trì hoãn tác vụ đã khởi chạy.
- **Mono.fromFuture(Supplier)** cho phép trì hoãn **việc gọi hàm tạo CompletableFuture** đến lúc có subscription. Nếu Supplier trả một Future mới mỗi lần, mỗi lần subscribe tạo một tác vụ mới; nếu Supplier chỉ trả một Future đã tồn tại, tác vụ đó vẫn được dùng chung.

Vì vậy, **lazy của Mono** và **lazy của công việc bên trong CompletableFuture** là hai tính chất cần xem xét riêng. Chỉ thấy kiểu trả về Mono không đủ để khẳng định request mạng hay tác vụ đã được hoãn.

## 2. CompletableFuture và Mono: hai hợp đồng khác nhau

| Khía cạnh | CompletableFuture<T> | Mono<T> |
| --- | --- | --- |
| Đối tượng biểu đạt | Một kết quả hoàn tất trong tương lai, thành công, lỗi hoặc hủy. | Một Publisher phát tối đa một giá trị rồi hoàn tất hoặc lỗi. |
| Bắt đầu công việc | Do API tạo Future quyết định; nhiều API bắt đầu ngay khi được gọi. | Do nguồn Publisher/operator quyết định; với Supplier có thể hoãn đến subscribe. |
| Bên nhận | Đăng ký các callback như thenApply, thenCompose, whenComplete. | Subscriber nhận onNext, onComplete hoặc onError; có Subscription và demand. |
| Đăng ký nhiều lần | Nhiều callback có thể quan sát **cùng một** Future. | Nhiều subscription có thể kích hoạt lại nguồn **nếu** Mono tạo nguồn mới mỗi lần. |
| Giá trị null | CompletableFuture có thể hoàn tất thành công với null. | Reactive Streams không phát onNext(null); Mono.fromFuture chuyển trường hợp đó thành hoàn tất rỗng. |
| Hủy | CompletableFuture.cancel(...) có ngữ nghĩa hủy tại Future; không bảo đảm tác vụ nền bị dừng vật lý. | Hủy subscription có thể được chuyển đến Future theo tùy chọn của fromFuture. |
| Lỗi | CompleteExceptionally hoặc kết quả callback thất bại. | Lỗi trở thành tín hiệu onError trong pipeline. |

Một pipeline như **map**, **flatMap**, **timeout**, **onErrorResume** có thể đặt sau Mono.fromFuture để xử lý kết quả theo quy tắc Reactor. Nhưng không nên kết luận tất cả API dùng CompletableFuture đều non-blocking: ví dụ một hàm tự dùng Thread.sleep, JDBC blocking hoặc làm việc CPU nặng trong Executor vẫn có thể chiếm luồng.

## 3. Ba cách chuyển đổi phổ biến và khác biệt về khởi chạy

### 3.1. Truyền CompletableFuture có sẵn: công việc có thể đã bắt đầu

Giả sử **client.fetchAsync(id)** gọi một API và lập tức bắt đầu xử lý bất đồng bộ khi phương thức được gọi:

~~~java
CompletableFuture<User> future = client.fetchAsync(id); // Gọi API ngay ở đây
Mono<User> mono = Mono.fromFuture(future);               // Bao Future đã có

// Đến lúc có subscribe, Reactor mới quan sát/đẩy tín hiệu vào Subscriber.
~~~

Dòng gọi client diễn ra **trước** khi Mono được tạo. Nếu API thật sự khởi chạy I/O ngay ở lời gọi, request có thể đang chạy hoặc đã hoàn tất dù Mono chưa có Subscriber.

Viết gọn lại vẫn có cùng tính chất:

~~~java
Mono<User> mono = Mono.fromFuture(client.fetchAsync(id));
~~~

Java phải tính đối số **client.fetchAsync(id)** trước khi gọi **Mono.fromFuture(...)**. Vì vậy, đây **không** phải cách trì hoãn lời gọi client đến subscription.

### 3.2. Truyền Supplier: khởi tạo Future tại subscription

~~~java
Mono<User> mono = Mono.fromFuture(() -> client.fetchAsync(id));
~~~

Ở thời điểm khai báo Mono, biểu thức lambda chưa chạy. Khi có subscription, Reactor gọi Supplier để lấy CompletableFuture, sau đó theo dõi kết quả của Future đó.

Điểm cần nhớ:

- **Không subscribe:** không gọi client.fetchAsync(id) qua Supplier này.
- **Subscribe một lần:** gọi Supplier một lần cho lượt đăng ký đó.
- **Subscribe hai lần:** Supplier được gọi cho từng lượt đăng ký; nếu client tạo Future mới, có thể có **hai request thật**.
- **Retry:** retry thực hiện subscription mới; một Supplier tạo Future mới có thể khởi chạy lại tác vụ. Cần xem xét idempotency nếu tác vụ có side effect.

Supplier chỉ hoãn **việc đánh giá biểu thức trả về Future**. Nếu bạn đã tạo Future trước đó và viết **() -> existingFuture**, thì tác vụ vẫn có thể chạy từ trước; chỉ việc truy xuất tham chiếu bị hoãn.

### 3.3. Dùng Mono.defer: viết rõ ranh giới deferred assembly

~~~java
Mono<User> mono = Mono.defer(
        () -> Mono.fromFuture(client.fetchAsync(id))
);
~~~

**Mono.defer** gọi Supplier để tạo một Mono nguồn mới mỗi khi subscribe. Trong trường hợp chỉ chuyển Future, cách này có tác dụng tương đương về thời điểm gọi **client.fetchAsync(id)** với **Mono.fromFuture(() -> client.fetchAsync(id))**.

Dùng **Mono.defer** nếu bạn cần quyết định *cả cách xây dựng publisher* tại thời điểm đăng ký, chẳng hạn chọn nguồn dựa trên điều kiện, lấy cấu hình hiện hành hoặc tổ hợp nhiều thao tác. Nếu chỉ hoãn một lời gọi Future, overload nhận Supplier của **Mono.fromFuture** thường ngắn gọn và rõ ý hơn.

**Phân biệt quan trọng:** Không có cách nào trong ba cách trên làm Future vốn đã chạy trở thành “chưa chạy”. Muốn lazy thật, phải trì hoãn **chính lời gọi API bắt đầu tác vụ**.

## 4. Thứ tự thời gian: assembly, subscription, completion

Xét hai trường hợp:

~~~text
A. Mono.fromFuture(client.fetchAsync(id))

t0  Gọi fetchAsync → Future được tạo, I/O có thể bắt đầu
t1  Xây dựng Mono từ Future đó
t2  subscribe Mono → đăng ký nhận kết quả
t3  Future hoàn tất → Mono phát giá trị / hoàn tất / lỗi

Nếu Future hoàn tất trước t2, Mono vẫn phát kết quả phù hợp khi subscribe.


B. Mono.fromFuture(() -> client.fetchAsync(id))

t0  Xây dựng Mono, chỉ giữ Supplier; chưa gọi fetchAsync
t1  Chưa subscribe → chưa có thao tác do Supplier khởi chạy
t2  subscribe → Supplier gọi fetchAsync, Future được tạo
t3  Future hoàn tất → Mono phát giá trị / hoàn tất / lỗi

Mỗi subscription là một lần đánh giá Supplier mới.
~~~

Thời điểm **Future hoàn tất** có thể xảy ra trước hoặc sau subscribe đối với Future có sẵn. Điều đó không thay đổi bản chất một Mono: mỗi subscription nhận tối đa một giá trị, tín hiệu hoàn tất hoặc lỗi tùy kết quả của nguồn.

Về ngữ nghĩa Java, **CompletableFuture.supplyAsync(...)** thường lên lịch công việc ngay khi được gọi. Đặt câu lệnh đó ngoài Supplier có thể khiến công việc chạy trước subscribe, bất kể sau đó có bao nhiêu operator Reactor.

## 5. Ví dụ Java 17+ chạy được: thấy chính xác lúc Future được tạo

Ví dụ dùng **CompletableFuture.completedFuture(...)** để kết quả và stdout hoàn toàn xác định. Mỗi lần tạo Future, hàm in một dòng và tăng bộ đếm. Mục đích là chứng minh **thời điểm đánh giá lời gọi tạo Future**, không mô phỏng độ trễ I/O thật.

Tạo dự án:

~~~text
future-mono-timing/
├── pom.xml
└── src/main/java/FutureMonoTiming.java
~~~

Tệp **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>future-mono-timing</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>FutureMonoTiming</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp **src/main/java/FutureMonoTiming.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import reactor.core.publisher.Mono;

public class FutureMonoTiming {
    private static int created = 0;

    private static CompletableFuture<String> newFuture(String label) {
        created++;
        System.out.println("Tạo future " + label + " #" + created);
        return CompletableFuture.completedFuture(label + "-" + created);
    }

    public static void main(String[] args) {
        Mono<String> eager = Mono.fromFuture(newFuture("eager"));

        Mono<String> lazy = Mono.fromFuture(() -> newFuture("lazy"));

        Mono<String> deferred = Mono.defer(
                () -> Mono.fromFuture(newFuture("defer"))
        );

        System.out.println("--- trước subscribe ---");

        eager.subscribe(v -> System.out.println("eager lần 1 = " + v));
        eager.subscribe(v -> System.out.println("eager lần 2 = " + v));

        lazy.subscribe(v -> System.out.println("lazy lần 1 = " + v));
        lazy.subscribe(v -> System.out.println("lazy lần 2 = " + v));

        deferred.subscribe(v -> System.out.println("defer lần 1 = " + v));
        deferred.subscribe(v -> System.out.println("defer lần 2 = " + v));
    }
}
~~~

Yêu cầu JDK 17+ và Maven. Chạy trong thư mục dự án:

~~~bash
mvn -q compile exec:java
~~~

Các dòng chương trình in ra:

~~~text
Tạo future eager #1
--- trước subscribe ---
eager lần 1 = eager-1
eager lần 2 = eager-1
Tạo future lazy #2
lazy lần 1 = lazy-2
Tạo future lazy #3
lazy lần 2 = lazy-3
Tạo future defer #4
defer lần 1 = defer-4
Tạo future defer #5
defer lần 2 = defer-5
~~~

**Giải thích kết quả:**

1. Ở biểu thức **Mono.fromFuture(newFuture("eager"))**, Java gọi newFuture trước subscribe, nên dòng “Tạo future eager #1” xuất hiện đầu tiên.
2. Hai Subscriber của **eager** cùng quan sát **một CompletableFuture đã tạo**. Không có Future mới cho lần subscribe thứ hai.
3. Với **Mono.fromFuture(() -> newFuture("lazy"))**, mã trong Supplier chạy cho từng subscription, tạo Future #2 rồi Future #3.
4. Với **Mono.defer(...)**, Publisher mới được tạo cho từng subscription, dẫn đến Future #4 rồi #5.
5. Vì mỗi Future là **completedFuture** đã hoàn tất đồng bộ, callback của subscribe trong ví dụ này in kết quả tức thời và đúng thứ tự. Nếu dùng công việc bất đồng bộ trên Executor, **thứ tự completion giữa nhiều công việc có thể khác**.

Ví dụ cố ý **không** dùng Thread.sleep để “đợi” hay giả định thứ tự của nhiều luồng. Đó là cách kiểm tra thời điểm khởi tạo một cách xác định.

## 6. Khi Future thật sự thực hiện công việc bất đồng bộ

Để thấy sự khác biệt trên nguồn có thể chạy nền, so sánh:

~~~java
// EAGER: supplyAsync được gọi ngay khi biểu thức này chạy.
Mono<String> eager = Mono.fromFuture(
        CompletableFuture.supplyAsync(() -> fetchFromRemoteSystem())
);

// LAZY: supplyAsync chỉ được gọi khi Mono có subscription.
Mono<String> lazy = Mono.fromFuture(
        () -> CompletableFuture.supplyAsync(() -> fetchFromRemoteSystem())
);
~~~

Đây là **hai đoạn minh họa**, với fetchFromRemoteSystem() là hàm do ứng dụng cung cấp; chúng không phải một chương trình Java độc lập.

**Điểm chính:** Trong trường hợp eager, công việc có thể được gửi vào Executor và chạy ngay. Trong trường hợp lazy, chỉ đến subscribe mới gọi supplyAsync và xếp công việc vào Executor. Sau khi đã bắt đầu, cả hai vẫn là công việc bất đồng bộ; Mono không tự “chạy lại” Future khi nó hoàn tất.

Ngoài ra, **supplyAsync không biến logic blocking thành non-blocking I/O**. Nếu fetchFromRemoteSystem dùng JDBC blocking hoặc gọi mạng đồng bộ, nó vẫn giữ luồng Executor trong lúc chờ. Cách này có thể phù hợp khi phải tương thích API cũ, nhưng cần quản lý Executor và tránh sử dụng tùy tiện commonPool cho tác vụ blocking kéo dài. Nếu đã có client non-blocking thực sự, ưu tiên dùng API bất đồng bộ của client và chỉ bridge kết quả.

### Đăng ký sau khi Future đã hoàn tất

~~~java
CompletableFuture<String> alreadyDone =
        CompletableFuture.completedFuture("OK");

Mono<String> mono = Mono.fromFuture(alreadyDone);
mono.subscribe(System.out::println); // In: OK
~~~

Không cần khởi chạy lại Future: Reactor quan sát trạng thái hoàn tất sẵn có rồi phát tín hiệu tương ứng cho Subscriber.

### Đăng ký trước khi Future hoàn tất

~~~java
CompletableFuture<String> pending = new CompletableFuture<>();
Mono<String> mono = Mono.fromFuture(pending);

mono.subscribe(v -> System.out.println("Nhận: " + v));
pending.complete("READY"); // In: Nhận: READY
~~~

Khi subscribe, Future chưa hoàn tất nên chưa có onNext. Tới khi **complete("READY")** được gọi, Mono phát giá trị. Với Future thực sự hoàn tất từ một luồng khác, callback có thể chạy trên luồng hoàn tất Future hoặc bị ảnh hưởng bởi operator lên lịch của Reactor; không nên dựa vào một tên luồng cố định.

## 7. Một Future dùng chung khác nhiều Future mới

Hai đoạn sau khác nhau dù đều có Supplier.

~~~java
// Một Future có sẵn, có thể đã bắt đầu.
CompletableFuture<String> shared = client.fetchAsync("42");

// Supplier chỉ trả lại đối tượng shared; không tạo yêu cầu mới.
Mono<String> sharedMono = Mono.fromFuture(() -> shared);

// Supplier gọi API tạo Future mới cho mỗi subscription.
Mono<String> newPerSubscription =
        Mono.fromFuture(() -> client.fetchAsync("42"));
~~~

**sharedMono** có hai Subscriber thì hai bên quan sát cùng kết quả, lỗi và trạng thái hủy của một Future. **newPerSubscription** có hai Subscriber có thể tạo hai request/đơn vị công việc độc lập.

Đây là khác biệt rất quan trọng với các API có side effect như tạo đơn hàng, ghi thanh toán, gửi email hoặc cập nhật dữ liệu. Nếu controller hoặc operator thực hiện subscribe nhiều lần, nguồn lazy có thể gửi lại tác vụ thật. **Lazy không mặc nhiên có nghĩa là thực thi đúng một lần trên toàn ứng dụng.**

Một số trường hợp muốn tạo Future ở lần subscription đầu và dùng chung kết quả cho các lần sau có thể dùng **cache** ở tầng Mono:

~~~java
Mono<String> cached = Mono.fromFuture(
        () -> client.fetchAsync("42")
).cache();
~~~

**cache()** lưu và phát lại các tín hiệu cuối cho Subscriber tiếp theo, đồng thời phối hợp các Subscriber đồng thời của nguồn đã cache. Tuy nhiên, điều đó cũng đồng nghĩa kết quả hoặc lỗi có thể bị giữ lại: cần cân nhắc cache có thời hạn, giới hạn bộ nhớ, hiệu lực dữ liệu và các tác vụ có side effect. Cache không tự biến thao tác ghi thành một giao dịch exactly-once.

## 8. Giá trị, rỗng, lỗi và sự khác nhau giữa complete với subscribe

### Future hoàn tất thành công với một giá trị

~~~java
Mono<Integer> value =
        Mono.fromFuture(CompletableFuture.completedFuture(42));
// Khi subscribe: onNext(42), rồi onComplete.
~~~

### Future hoàn tất với null

~~~java
CompletableFuture<String> emptyFuture =
        CompletableFuture.completedFuture(null);

Mono<String> empty = Mono.fromFuture(emptyFuture);
// Khi subscribe: onComplete mà không có onNext.
~~~

Reactive Streams không cho phép onNext(null). Nếu **null** thực sự cần phân biệt với “không tìm thấy”, hãy thiết kế kiểu kết quả phù hợp (chẳng hạn Optional hoặc kết quả có trạng thái) ở biên API; Mono không mang giá trị null dưới dạng onNext.

### Future hoàn tất ngoại lệ

~~~java
CompletableFuture<String> failed = new CompletableFuture<>();
Mono<String> result = Mono.fromFuture(failed);

result.subscribe(
        value -> System.out.println("OK: " + value),
        error -> System.out.println("Lỗi: " + error.getMessage())
);

failed.completeExceptionally(
        new IllegalStateException("Dịch vụ không sẵn sàng")
);
~~~

Khi Future hoàn tất ngoại lệ, Mono phát **onError** thay vì một giá trị bình thường. Trên đường chuyển đổi có thể có lớp bọc exception từ CompletionStage; khi cần phân loại lỗi, nên kiểm tra nguyên nhân và hợp đồng của API gốc. Ví dụ trên chỉ minh họa cách bắt lỗi, không giả định bất kỳ retry hoặc khôi phục tự động nào.

Nếu Supplier **ném exception ngay khi được gọi**, thao tác tạo Future thất bại và pipeline deferred cũng phải được xử lý như lỗi. Nên đặt **onErrorResume**, **retryWhen** hoặc chính sách lỗi phù hợp ở pipeline, tránh giấu lỗi khi tạo tác vụ.

## 9. Hủy subscription có thể hủy Future: chú ý khi dùng chung

Theo API Reactor, mặc định **Mono.fromFuture(future)** có cơ chế chuyển tín hiệu cancel từ subscription sang CompletableFuture. Ngoài overload thông thường còn có overload **Mono.fromFuture(future, suppressCancel)**:

~~~java
CompletableFuture<String> future = client.fetchAsync("42");

Mono<String> defaultCancellation =
        Mono.fromFuture(future); // Mặc định: có thể cancel Future.

Mono<String> keepFutureRunning =
        Mono.fromFuture(future, true); // suppressCancel = true.
~~~

Đây là đoạn minh họa sử dụng client do ứng dụng cung cấp.

- **suppressCancel = false** (mặc định): khi subscription bị hủy, adapter có thể gọi hủy đối tượng CompletableFuture.
- **suppressCancel = true**: tránh truyền việc hủy subscription sang Future đó; có ích khi Future do bên khác quản lý hoặc cần được nhiều Subscriber cùng quan sát.
- Overload nhận Supplier cũng có biến thể **Mono.fromFuture(() -> client.fetchAsync(id), true)** khi cần cấu hình tương tự.

Một điểm dễ bỏ qua: **CompletableFuture.cancel(...) không bảo đảm công việc trên Executor/ngay tại hệ thống bên ngoài đã bị dừng**. Với CompletableFuture chuẩn, tham số **mayInterruptIfRunning** không có tác dụng ngắt luồng thực thi như ở một số Future khác. Việc một HTTP request, RPC hoặc I/O thật có được hủy hay không phụ thuộc vào client/SDK và tích hợp của nó.

Đặc biệt, nếu **hai subscription dùng cùng một Future** và một subscription bị hủy, thao tác hủy Future có thể ảnh hưởng cả bên quan sát còn lại. Vì thế phải quyết định rõ **ai sở hữu Future**, có được chia sẻ hay không và nên propagate cancel hay suppress.

Trong WebFlux, request của client bị hủy, timeout hoặc ngắt kết nối có thể dẫn tới hủy upstream subscription tùy pipeline. Nếu nguồn bên ngoài vẫn phải hoàn tất để lưu trạng thái, cần thiết kế ownership và cancellation một cách chủ đích, không mặc định việc hủy client có quyền dừng side effect nghiệp vụ.

## 10. Retry, timeout và phép biến đổi: Future nào thực sự được chạy lại?

### Retry với Future có sẵn

~~~java
CompletableFuture<String> once = client.fetchAsync("42");

Mono<String> onceMono =
        Mono.fromFuture(once).retry(1);
~~~

Nếu Future **once** hoàn tất lỗi, retry chỉ **đăng ký lại cùng một Future** đã lỗi; nó không tự gọi client.fetchAsync lần nữa. Nếu mong muốn tạo yêu cầu mới, nguồn phải được khai báo theo Supplier/defer.

### Retry với nguồn tạo Future theo subscription

~~~java
Mono<String> retried = Mono.fromFuture(
        () -> client.fetchAsync("42")
).retry(1);
~~~

Nếu lần đầu onError, retry đăng ký lại và Supplier được gọi để tạo một Future mới. **retry(1)** cho phép một lần thử bổ sung sau lỗi đầu tiên, nhưng không bảo đảm lỗi sẽ hết. Với side effect, chỉ retry khi API có cơ chế an toàn để không tạo hiệu ứng lặp ngoài ý muốn; có thể cần idempotency key, backoff và giới hạn tốc độ.

### Timeout

~~~java
Mono<String> bounded = Mono.fromFuture(
        () -> client.fetchAsync("42")
).timeout(java.time.Duration.ofSeconds(3));
~~~

Khi vượt thời gian, Mono báo lỗi timeout và hủy subscription upstream theo cơ chế operator. **Timeout ở tầng Reactor không phải cam kết hệ thống ngoài đã dừng I/O hoặc rollback tác vụ**; cần phân biệt hủy Publisher/Future với hủy tác vụ tại dịch vụ đích.

### Giữ pipeline thuần Reactor

~~~java
Mono<String> decorated = Mono.fromFuture(
        () -> client.fetchAsync("42")
)
.map(String::trim)
.filter(s -> !s.isEmpty())
.onErrorResume(error -> Mono.just("fallback"));
~~~

Đoạn này minh họa việc tích hợp các operator. Với bản ghi thực tế, chính sách fallback phải dựa vào loại lỗi và nghiệp vụ; không nên nuốt mọi lỗi chỉ vì có onErrorResume.

## 11. subscribeOn, publishOn và những hiểu lầm về luồng

**Mono.fromFuture** không có nghĩa kết quả phải xuất hiện trên một luồng chuyên dụng của Reactor. Lời gọi Supplier và callback hoàn tất Future có thể diễn ra ở những luồng khác nhau; sự khác nhau đó phụ thuộc API gốc, Executor, thread hoàn tất và operator sắp lịch.

- **subscribeOn(scheduler)** ảnh hưởng đến nơi đăng ký upstream được thực hiện. Nếu dùng nguồn **Mono.fromFuture(() -> client.fetchAsync(id))**, việc gọi Supplier thường diễn ra trong luồng subscribe đã được chuyển bởi subscribeOn.
- **publishOn(scheduler)** ảnh hưởng đến luồng xử lý tín hiệu ở các operator downstream tính từ vị trí publishOn.
- **subscribeOn không quay ngược thời gian.** Nếu bạn đã tạo **CompletableFuture.supplyAsync(...)** trước khi thêm subscribeOn, công việc đã được xếp lịch ở Executor của CompletableFuture.
- **publishOn không khiến thư viện blocking trở thành non-blocking.** Việc chuyển luồng chỉ đổi nơi thực thi, không đổi bản chất I/O hay giới hạn số luồng.

Nếu chỉ có một hàm **blocking đồng bộ** chứ không phải Future do client hỗ trợ thật, cách bridge đơn giản hơn là:

~~~java
Mono<Result> result = Mono.fromCallable(
        () -> blockingClient.fetch(id)
).subscribeOn(reactor.core.scheduler.Schedulers.boundedElastic());
~~~

Đây là đoạn minh họa trong ứng dụng đã có Result và blockingClient; boundedElastic cô lập công việc blocking khỏi event loop theo khả năng của scheduler. Nó **không biến thao tác blocking thành I/O non-blocking**, và vẫn cần giới hạn tải.

## 12. Ứng dụng trong Spring WebFlux

Giả sử một SDK có hàm **CompletableFuture<Profile> fetchAsync(String id)**. Controller WebFlux có thể trả Publisher được tạo bằng Supplier:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

record Profile(String id, String displayName) {}

interface ProfileAsyncClient {
    CompletableFuture<Profile> fetchAsync(String id);
}

@RestController
class ProfileController {
    private final ProfileAsyncClient client;

    ProfileController(ProfileAsyncClient client) {
        this.client = client;
    }

    @GetMapping("/profiles/{id}")
    public Mono<Profile> get(@PathVariable String id) {
        return Mono.fromFuture(() -> client.fetchAsync(id));
    }
}
~~~

Đây là các lớp minh họa để đặt trong **một dự án Spring Boot WebFlux đã cấu hình dependency và bean ProfileAsyncClient**; chưa phải ứng dụng có thể tự khởi chạy vì chưa định nghĩa client implementation và bootstrap.

**Vì sao chọn Supplier ở đây?** Phương thức controller được gọi để tạo giá trị trả về, nhưng framework mới thực hiện subscription theo vòng đời xử lý HTTP. Supplier đặt lời gọi fetchAsync vào lúc pipeline được subscribe. Điều này tạo ranh giới trì hoãn rõ ràng, đồng thời cho phép tích hợp cancellation và timeout theo chính sách.

Trong Spring, nên để **framework subscribe** với Mono được trả về; tránh gọi **subscribe()** thủ công trong controller để “kích hoạt cho chắc”, bởi việc đó có thể tách tác vụ khỏi quản lý tín hiệu lỗi và vòng đời response. Không gọi **block()**, **join()** hoặc **get()** trên luồng xử lý request WebFlux chỉ để lấy giá trị đồng bộ.

Nếu SDK đã trả một Future đang chạy trước khi controller gọi, việc bridge không thể làm tác vụ ấy trở thành lazy. Trường hợp đó phải xem xét thiết kế hoặc hợp đồng của SDK, hoặc chấp nhận mô hình eager có chủ đích.

## 13. Các lỗi phổ biến và cách kiểm tra

| Lỗi thường gặp | Hậu quả | Cách sửa |
| --- | --- | --- |
| **Mono.fromFuture(client.fetchAsync(id))** khi muốn deferred | Client có thể được gọi ngay lúc lắp pipeline, trước subscribe. | Dùng **Mono.fromFuture(() -> client.fetchAsync(id))**. |
| **Mono.fromFuture(() -> existingFuture)** rồi tưởng tạo request mới | Chỉ trả về một Future cũ đã chạy; các subscription cùng chia sẻ trạng thái. | Đặt chính lời gọi tạo Future vào Supplier nếu cần Future mới. |
| **subscribe hai lần để debug** | Nguồn Supplier có thể gửi hai request nghiệp vụ. | Hiểu số subscription; quan sát doOnSubscribe, số lần gọi API và cân nhắc cache/chia sẻ có chủ đích. |
| **retry trên Future cũ** | Retry không khởi chạy request mới, có thể nhận lại đúng lỗi đã xảy ra. | Dùng nguồn deferred; thiết kế idempotency và giới hạn retry. |
| **mặc định cancel vô hại** | Một Subscriber có thể cancel shared Future; công việc thực có thể vẫn chạy hoặc tác động bên khác. | Quy định ownership, lựa chọn suppressCancel khi phù hợp, kiểm thử client thật. |
| **dùng Future nhưng vẫn block/join trong WebFlux** | Chặn event loop hoặc gây nghẽn luồng. | Trả Mono và dùng operator bất đồng bộ. |
| **gọi supplyAsync rồi tin rằng tác vụ không blocking** | Công việc blocking vẫn chiếm Executor; dễ làm cạn pool dưới tải cao. | Ưu tiên client non-blocking; tách bounded pool nếu buộc dùng blocking. |
| **không xử lý null và lỗi** | Nhầm Mono rỗng với không có kết quả, bỏ qua onError. | Định nghĩa hợp đồng API, chuyển đổi empty/error theo nghiệp vụ. |
| **đòi stdout theo thứ tự từ nhiều Future chạy đồng thời** | Kiểm thử dễ flaky vì completion có thể race. | Kiểm tra số lần gọi/tín hiệu bằng counter, latch, StepVerifier hoặc mock có kiểm soát; tránh đo bằng sleep. |

### Các ca kiểm thử nên có

1. **Chưa subscribe:** kiểm tra nguồn supplier chưa được gọi; đối chiếu với Future tạo sẵn.
2. **Một và nhiều subscription:** đếm số lần API được gọi để xác định eager, per-subscription hay shared.
3. **Future đã hoàn tất trước subscribe:** xác minh nhận giá trị/lỗi tương ứng.
4. **Future hoàn tất sau subscribe:** xác minh Mono chỉ phát khi Future complete.
5. **Future thành công với null:** xác minh Mono complete rỗng, không onNext(null).
6. **Future thất bại:** xác minh onError và chính sách retry/fallback.
7. **Cancel và timeout:** kiểm tra trạng thái CompletableFuture, hành vi của client gốc và tài nguyên thực sự được giải phóng.
8. **Retry trên nguồn có side effect:** kiểm tra idempotency và số lần tác vụ thực tế được gọi.

Có thể dùng **reactor-test / StepVerifier** để kiểm tra tín hiệu của Mono; riêng thời điểm khởi tạo Future nên bổ sung bộ đếm lời gọi hoặc fake client có thể hoàn tất Future thủ công. Không dùng sleep để suy ra thứ tự khi chưa kiểm soát được scheduling.

## 14. Checklist lựa chọn cách chuyển đổi

| Nhu cầu thực tế | Cách dùng phù hợp |
| --- | --- |
| Đã có CompletableFuture và chỉ cần quan sát kết quả của nó | **Mono.fromFuture(existingFuture)**. |
| Muốn API bất đồng bộ chỉ được gọi sau khi subscribe | **Mono.fromFuture(() -> api.callAsync())**. |
| Muốn dựng lại một Mono nguồn phức tạp theo từng subscription | **Mono.defer(() -> ...)**. |
| Future dùng chung, một Subscriber hủy không được hủy Future | **Mono.fromFuture(sharedFuture, true)** khi phù hợp hợp đồng sở hữu. |
| Nhiều Subscriber cần dùng chung kết quả của một lần gọi | Thiết kế chia sẻ/caching có kiểm soát thay vì vô tình khởi chạy nhiều lần. |
| Có thao tác blocking đồng bộ, không có API Future thực sự | **Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())**, có giới hạn tài nguyên. |
| Muốn chuyển CompletionStage chung, không nhất thiết CompletableFuture | Cân nhắc **Mono.fromCompletionStage(...)** và biến thể Supplier. |

## 15. Ghi nhớ

**Mono.fromFuture(future)** biến **một Future có sẵn** thành Publisher; Future đó có thể đã bắt đầu hoặc hoàn tất trước khi có subscribe. **Mono.fromFuture(() -> createFuture())** trì hoãn việc gọi hàm tạo Future đến **mỗi subscription**, còn **Mono.defer(() -> Mono.fromFuture(createFuture()))** là cách tổng quát hóa ranh giới deferred.

Vì **mỗi subscription có thể dẫn đến một lời gọi API khác**, luôn kiểm tra số lần khởi chạy, retry và side effect. Đồng thời phải quyết định **cancellation có truyền sang Future hay không**, xử lý null/lỗi/timeout đúng hợp đồng và tránh chặn event loop. Việc chuyển CompletableFuture thành Mono là cầu nối giữa hai mô hình bất đồng bộ; nó không tự thay đổi đặc tính blocking hay vòng đời thực của tác vụ đã được SDK khởi chạy.

**Tài liệu API tham khảo:**
- [Project Reactor Mono API – fromFuture và fromCompletionStage](https://projectreactor.io/docs/core/3.6.17/api/reactor/core/publisher/Mono.html)
- [Java SE 17 – CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
