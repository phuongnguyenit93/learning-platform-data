# allOf() chờ nhiều công việc và cách thu kết quả có kiểu

## 1. Vì sao cần allOf()?

Trong một ứng dụng Spring, một API tổng hợp có thể phải lấy giá, tồn kho và trạng thái vận chuyển từ ba nguồn độc lập. Nếu từng nguồn được gọi qua `@Async` hoặc `CompletableFuture.supplyAsync`, ta có ba `CompletableFuture<T>` có thể hoàn thành ở những thời điểm khác nhau. Yêu cầu nghiệp vụ là **chờ đủ các nguồn cần thiết rồi kết hợp kết quả**, không phải lấy “kết quả nào xong trước”.

Java cung cấp:

~~~java
public static CompletableFuture<Void> allOf(CompletableFuture<?>... cfs)
~~~

Khi dùng `CompletableFuture.allOf(a, b, c)`, bạn nhận một **barrier Future**: nó hoàn tất khi **tất cả** các Future đầu vào đã hoàn tất (thành công hoặc lỗi). Nếu tất cả thành công, Future tổng hợp hoàn tất bình thường với giá trị `null` do kiểu trả về là `Void`; **nó không chứa danh sách kết quả**. Nếu có ít nhất một Future lỗi, Future tổng hợp hoàn tất exceptionally.

Vì vậy thiết kế thường có hai bước:

1. **Ghép tín hiệu hoàn tất:** `CompletableFuture.allOf(...)`.
2. **Thu giá trị đúng kiểu:** sau khi barrier **thành công**, đọc từng Future đầu vào bằng `join()` và biến đổi thành `List<T>` hoặc một record/DTO cụ thể.

Ví dụ khái niệm:

~~~java
CompletableFuture<User> userFuture = loadUser();
CompletableFuture<Balance> balanceFuture = loadBalance();

CompletableFuture<AccountView> combined =
        CompletableFuture.allOf(userFuture, balanceFuture)
                .thenApply(ignored ->
                        new AccountView(
                                userFuture.join(),
                                balanceFuture.join()));
~~~

Đây là đoạn minh họa nằm trong service, **không phải chương trình độc lập**: `User`, `Balance`, `AccountView`, `loadUser` và `loadBalance` là kiểu/method do dự án định nghĩa. Bản chất của ví dụ: kết quả có kiểu `CompletableFuture<AccountView>`, không bị biến thành `Object[]` hay mất generic type.

**Nhớ nhanh:** `allOf` **chờ đủ**; `thenApply` **thu kết quả**; `join` **đọc từng giá trị đã hoàn tất**. Không có bước nào trong ba bước này tự tạo worker thread.

## 2. Hợp đồng chính xác của CompletableFuture.allOf

### 2.1. API và kết quả

| Tình huống | `CompletableFuture.allOf(...)` | Điều cần nhớ |
| --- | --- | --- |
| Hai Future chưa xong | Future tổng hợp chưa xong | Không được coi là kết quả hoàn chỉnh |
| Một Future xong, một Future chưa xong | Vẫn chưa xong | `allOf` là barrier chờ **tất cả** |
| Tất cả thành công | Hoàn tất bình thường, giá trị `Void/null` | Đọc đầu vào để lấy giá trị cụ thể |
| Ít nhất một Future hoàn tất exceptionally | Future tổng hợp hoàn tất exceptionally sau khi các đầu vào hoàn tất | Xử lý exception; không chạy nhánh `thenApply` chỉ-dành-cho-thành-công |
| Danh sách rỗng | Future tổng hợp đã hoàn tất với `null` | Hàm `sequence` có thể trả danh sách rỗng |
| Một phần tử `null` trong mảng đầu vào | Ném `NullPointerException` lúc gọi | Kiểm tra danh sách đầu vào |
| Một Future không bao giờ hoàn tất | Barrier có thể chờ vô hạn | Deadline, rejection rõ ràng và theo dõi trạng thái job |

`allOf` không giới hạn thời gian chờ, không tự hủy tác vụ đang chạy, không tự tạo thread pool, không ngăn tác vụ nhận quá tải và **không bảo đảm partial results** được trả về nếu một phần tử lỗi.

Với nhiều lỗi, đừng dựa vào việc `join()` của barrier sẽ báo lỗi nào đầu tiên theo thứ tự thời gian. Khi cần báo cáo từng nguồn lỗi, hãy xử lý từng Future bằng `handle` trước khi gom.

### 2.2. allOf khác anyOf và thenCombine

| Công cụ | Khi nào stage tổng hợp có thể xong? | Kết quả tổng hợp |
| --- | --- | --- |
| `allOf(a,b,c)` | Sau khi cả ba đã hoàn tất | `CompletableFuture<Void>`; không tự lấy các giá trị |
| `anyOf(a,b,c)` | Khi **một** Future bất kỳ xong | `CompletableFuture<Object>`; có thể khó bảo đảm kiểu |
| `a.thenCombine(b, fn)` | Khi cả hai thành công | Kiểu giá trị do `fn` trả về, thích hợp cho hai nguồn |
| `a.thenCompose(fn)` | Khi a xong thành công rồi cần Future tiếp theo | Dùng cho công việc **phụ thuộc tuần tự**, không phải barrier |
| `allOf(...).thenApply(fn)` | Khi mọi Future đầu vào thành công | Kiểu giá trị do `fn` tạo, dùng cho n nguồn |

`anyOf` với đầu vào rỗng trả một Future chưa hoàn tất, còn `allOf` với đầu vào rỗng trả Future đã hoàn tất. Đó là khác biệt quan trọng khi xử lý danh sách động.

### 2.3. allOf không tự khởi chạy các tác vụ

Giả sử:

~~~java
CompletableFuture<String> a =
        CompletableFuture.supplyAsync(() -> "A", executor);
CompletableFuture<String> b =
        CompletableFuture.supplyAsync(() -> "B", executor);
CompletableFuture<Void> barrier = CompletableFuture.allOf(a, b);
~~~

`supplyAsync` mới là thao tác **gửi công việc** tới `executor`; `allOf` chỉ theo dõi sự hoàn tất. Nếu executor là `SyncTaskExecutor`, từng supplier có thể chạy trên caller thread; nếu là một pool bất đồng bộ, công việc được xử lý trên worker của pool. Tham số `Executor` và cấu hình pool mới quyết định execution model, không phải tên `allOf`.

Nếu không truyền `Executor` cho `supplyAsync`, Java thường sử dụng `ForkJoinPool.commonPool()`. Trong dự án Spring cần tách pool báo cáo, JDBC và tác vụ ngắn, hãy truyền executor tường minh hoặc gọi các phương thức `@Async("beanName")` qua Spring proxy; không mặc định rằng mọi CompletableFuture đều chạy trong pool của Boot.

## 3. Pattern chuẩn: thu List<T> theo thứ tự đầu vào

Một danh sách `List<CompletableFuture<T>>` có thể được chuyển thành **một** `CompletableFuture<List<T>>` mà không cần cast từ `Object`.

~~~java
import java.util.List;
import java.util.concurrent.CompletableFuture;

public final class FutureCollections {
    private FutureCollections() { }

    public static <T> CompletableFuture<List<T>> sequence(
            List<CompletableFuture<T>> input) {
        List<CompletableFuture<T>> futures = List.copyOf(input);

        CompletableFuture<?>[] array =
                futures.toArray(new CompletableFuture<?>[0]);

        return CompletableFuture.allOf(array)
                .thenApply(ignored ->
                        futures.stream()
                                .map(CompletableFuture::join)
                                .toList());
    }
}
~~~

Đây là một class Java 17 hợp lệ, có thể đặt trong file `FutureCollections.java`. Trong một dự án dùng Java 8–15, `Stream.toList()` chưa có; có thể thay bằng collector phù hợp. `List.copyOf(input)` chụp danh sách các **tham chiếu Future** tại thời điểm gọi, tránh caller sửa cấu trúc danh sách sau khi xây barrier. Nó không sao chép hoặc đóng băng các kết quả `T` có thể mutable. `List.copyOf` không chấp nhận phần tử `null` và bản thân `allOf` cũng từ chối phần tử null.

**Các đặc tính quan trọng:**

- Khi `input` có `CompletableFuture<Report>`, kiểu trả về là `CompletableFuture<List<Report>>`. Compiler giúp kiểm tra kiểu; không ép kiểu `List<Object>`.
- `thenApply` **chỉ chạy khi barrier hoàn tất bình thường**. Nếu một task thất bại, stage trả về cũng exceptional; không đọc vòng lặp và vô tình biến lỗi thành thành công.
- Khi chạy callback `thenApply` sau barrier thành công, từng Future con đã hoàn tất; `join()` lúc này **không chờ thêm** trong điều kiện các Future giữ nguyên terminal state.
- Danh sách kết quả giữ **thứ tự của `input`**, không phải thứ tự task hoàn tất. `Stream.toList()` trả một list không sửa được qua API list.
- `input` rỗng tạo kết quả `CompletableFuture<List<T>>` đã hoàn tất với list rỗng.

Nếu cần kiểm soát thứ tự theo deadline, mức ưu tiên hoặc độ hoàn tất, phải có logic sắp xếp riêng. `allOf` không cung cấp “results in completion order”.

### Sai lầm: trả List<Object> hoặc cast toàn bộ

~~~java
// Anti-pattern minh họa, không phải API để khuyến khích sử dụng.
CompletableFuture<?>[] array = ...;
CompletableFuture<Void> barrier = CompletableFuture.allOf(array);
// Không có hàm barrier.getResults().
// barrier.join() trả null (Void), không thể ép thành List<Report>.
~~~

Một đoạn code dùng `CompletableFuture<?>[]` ở bước tạo barrier **không làm mất kiểu** của danh sách `List<CompletableFuture<Report>>` ban đầu. Giữ danh sách có generic type để thu kết quả ở bước sau. Tránh raw `CompletableFuture[]` và cast không kiểm tra khi không cần.

## 4. Ví dụ Java 17 độc lập với kết quả xác định

Ví dụ sau minh họa ba trường hợp không phụ thuộc tốc độ CPU hoặc lập lịch thread:

1. `allOf` **chưa hoàn tất** khi một trong hai tác vụ vẫn pending, dù tác vụ còn lại đã xong.
2. Thu dữ liệu cùng kiểu thành `List<String>`; thu dữ liệu **khác kiểu** thành record `Summary`.
3. Một Future lỗi làm barrier lỗi; khi muốn giữ thành công từng phần thì chuyển mỗi Future thành `Outcome<T>` trước khi gom.

Lưu thành **`FanInDemo.java`**:

~~~java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public final class FanInDemo {
    record Summary(String sku, int stock) { }

    record Outcome<T>(String source, T value, String error) { }

    static <T> CompletableFuture<List<T>> sequence(
            List<CompletableFuture<T>> input) {
        List<CompletableFuture<T>> snapshot = List.copyOf(input);
        CompletableFuture<?>[] array =
                snapshot.toArray(new CompletableFuture<?>[0]);

        return CompletableFuture.allOf(array)
                .thenApply(ignored ->
                        snapshot.stream()
                                .map(CompletableFuture::join)
                                .toList());
    }

    public static void main(String[] args) {
        CompletableFuture<String> first = new CompletableFuture<>();
        CompletableFuture<String> second = new CompletableFuture<>();
        CompletableFuture<List<String>> together =
                sequence(List.of(first, second));

        second.complete("B");
        System.out.println("WAIT_AFTER_B=" + together.isDone());

        first.complete("A");
        System.out.println("TYPED_VALUES=" + together.join());

        CompletableFuture<String> sku =
                CompletableFuture.completedFuture("P-7");
        CompletableFuture<Integer> stock =
                CompletableFuture.completedFuture(4);

        CompletableFuture<Summary> summary =
                CompletableFuture.allOf(sku, stock)
                        .thenApply(ignored ->
                                new Summary(sku.join(), stock.join()));
        System.out.println("SUMMARY=" + summary.join());

        CompletableFuture<String> ok =
                CompletableFuture.completedFuture("OK");
        CompletableFuture<String> failed =
                CompletableFuture.failedFuture(
                        new IllegalStateException("unavailable"));

        CompletableFuture<Void> all =
                CompletableFuture.allOf(ok, failed);

        try {
            all.join();
        } catch (CompletionException ex) {
            System.out.println("ALL_ERROR="
                    + ex.getCause().getClass().getSimpleName());
        }

        CompletableFuture<Outcome<String>> safeOk =
                ok.handle((value, error) ->
                        new Outcome<>("first", value,
                                error == null ? null
                                        : error.getClass().getSimpleName()));

        CompletableFuture<Outcome<String>> safeFailed =
                failed.handle((value, error) ->
                        new Outcome<>("second", value,
                                error == null ? null
                                        : error.getClass().getSimpleName()));

        System.out.println("PARTIAL="
                + sequence(List.of(safeOk, safeFailed)).join());

        System.out.println("EMPTY="
                + sequence(List.<CompletableFuture<String>>of()).join());
    }
}
~~~

Chạy với JDK 17+:

~~~bash
javac --release 17 FanInDemo.java
java FanInDemo
~~~

Stdout do chương trình in:

~~~text
WAIT_AFTER_B=false
TYPED_VALUES=[A, B]
SUMMARY=Summary[sku=P-7, stock=4]
ALL_ERROR=IllegalStateException
PARTIAL=[Outcome[source=first, value=OK, error=null], Outcome[source=second, value=null, error=IllegalStateException]]
EMPTY=[]
~~~

**Tại sao xác định?** Không có worker chạy ngẫu nhiên trong ví dụ; hai Future được `complete` thủ công theo thứ tự đã định. Khi mới `second.complete("B")`, `first` chưa xong nên `together.isDone()` phải là `false`. Sau `first.complete("A")`, barrier thành công và kết quả vẫn theo `List.of(first, second)`, nên là `[A, B]` dù B hoàn tất trước.

Phần `Summary` cho thấy cách thu hai loại kết quả `String` và `Integer` thành một **record có kiểu**, không phải `List<Object>`. Phần `ALL_ERROR` cho thấy mặc định `allOf` không trả kết quả thành công một phần. Cuối cùng `handle` biến từng Future thành một `Outcome<String>` **đều hoàn tất bình thường**, cho phép `sequence` thu cả trạng thái thành công và lỗi. Cách làm này có chủ đích: nếu cần toàn bộ công việc đều thành công thì **không** nuốt lỗi; nếu báo cáo chấp nhận thiếu một nguồn thì model hóa lỗi rõ ràng.

## 5. Khác kiểu: tạo DTO thay vì cố gom List<T>

`allOf` nhận `CompletableFuture<?>...` nên có thể chờ những Future mang kiểu khác nhau. Tuy nhiên không có một `T` duy nhất để biểu diễn chính xác cả `User`, `Money` và `Inventory` trong `List<T>`. Khi từng nguồn mang ý nghĩa khác nhau, tạo DTO:

~~~java
// Mã minh họa trong một service; các record được dự án định nghĩa.
CompletableFuture<User> user = findUser(userId);
CompletableFuture<Money> balance = findBalance(userId);
CompletableFuture<Inventory> inventory = findInventory(userId);

CompletableFuture<Dashboard> dashboard =
        CompletableFuture.allOf(user, balance, inventory)
                .thenApply(ignored ->
                        new Dashboard(
                                user.join(),
                                balance.join(),
                                inventory.join()));
~~~

Từng `join()` trả đúng kiểu ban đầu; constructor của `Dashboard` kiểm tra tương thích ở compile time. Điều này dễ đọc hơn:

~~~java
// Anti-pattern: làm mất type-safety và dựa vào vị trí số nguyên.
List<Object> result = List.of(
        user.join(), balance.join(), inventory.join());
User u = (User) result.get(0);
~~~

Trong ví dụ đúng, kết quả là `CompletableFuture<Dashboard>` để caller có thể `thenApply`/`thenCompose`/`handle`, chứ không buộc caller gọi `get()` đồng bộ ngay lập tức. Nếu có một Future đầu vào bị lỗi, `thenApply` tạo DTO **không chạy**; nhận lỗi bằng completion stage hoặc `handle` ở cấp phù hợp.

Với đúng **hai** Future, `thenCombine` có thể diễn đạt ngắn hơn:

~~~java
CompletableFuture<DashboardPart> part =
        user.thenCombine(balance, DashboardPart::new);
~~~

`thenCombine` phù hợp khi chỉ kết hợp hai nguồn và cả hai phải thành công; với ba nguồn trở lên, `allOf` cộng DTO giúp code đối xứng, hoặc có thể chuỗi `thenCombine` nếu cấu trúc phức tạp.

## 6. Tích hợp Spring Boot @Async: ví dụ runnable

Một chương trình thuần Java có thể dùng `CompletableFuture.supplyAsync`; trong Spring, ta thường có service gọi API hoặc DB trên executor riêng và aggregator chịu trách nhiệm ghép kết quả. Ví dụ dưới đây dùng **Java 17 + Maven + Spring Boot 3.3.5**; không yêu cầu web server hoặc DB.

Bộ ví dụ gồm hai phương thức async độc lập trả **hai kiểu record khác nhau**. `CatalogAggregator.fetch` gom cả hai bằng `allOf(...).thenApply(...)`; `ApplicationRunner` in DTO cuối cùng để kiểm thử.

### 6.1. Cấu trúc thư mục

~~~text
spring-allof-demo/
├── pom.xml
└── src/main/java/com/example/fanin/
    ├── FanInApplication.java
    ├── CatalogClient.java
    └── CatalogAggregator.java
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>spring-allof-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.3. FanInApplication.java

~~~java
package com.example.fanin;

import java.util.concurrent.TimeUnit;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@SpringBootApplication
@EnableAsync
public class FanInApplication {
    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(FanInApplication.class, args)) {
            // Context tự đóng sau khi ApplicationRunner hoàn tất.
        }
    }

    @Bean("catalogExecutor")
    ThreadPoolTaskExecutor catalogExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(2);
        pool.setQueueCapacity(10);
        pool.setThreadNamePrefix("catalog-");
        pool.setWaitForTasksToCompleteOnShutdown(true);
        return pool;
    }

    @Bean
    ApplicationRunner demonstration(CatalogAggregator aggregator) {
        return args -> {
            CatalogAggregator.Snapshot result =
                    aggregator.fetch("P-7").get(5, TimeUnit.SECONDS);
            System.out.println("SNAPSHOT=" + result);
        };
    }
}
~~~

`ApplicationRunner` cố ý gọi `get(5, SECONDS)` để có stdout xác định rồi đóng context. Cách này **chặn startup thread** trong demo; không bắt buộc đối với một web controller muốn bất đồng bộ thật sự. Hai worker core trong bean chỉ là cấu hình mẫu, không phải mặc định của mọi Spring app.

### 6.4. CatalogClient.java

~~~java
package com.example.fanin;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class CatalogClient {
    public record Price(String sku, int amount) { }
    public record Stock(String sku, int available) { }

    @Async("catalogExecutor")
    public CompletableFuture<Price> price(String sku) {
        // Giả lập kết quả tra giá, thay bằng HTTP/DB thật khi triển khai.
        return CompletableFuture.completedFuture(new Price(sku, 120));
    }

    @Async("catalogExecutor")
    public CompletableFuture<Stock> stock(String sku) {
        return CompletableFuture.completedFuture(new Stock(sku, 7));
    }
}
~~~

`CatalogClient` là Spring-managed bean được `CatalogAggregator` gọi **qua proxy**, nên hai method được interceptor `@Async` gửi vào `catalogExecutor`. Phương thức implementation trả một `CompletableFuture.completedFuture` chứa kết quả vừa tính: đó là kiểu return hợp lệ của target method, **không** làm mất cơ chế async của proxy bên ngoài. Cần lưu ý method nhỏ như demo không nhất thiết đáng gửi sang worker trong production; mục tiêu chỉ minh họa fan-out và fan-in.

### 6.5. CatalogAggregator.java

~~~java
package com.example.fanin;

import java.util.concurrent.CompletableFuture;
import org.springframework.stereotype.Service;

@Service
public class CatalogAggregator {
    public record Snapshot(
            String sku, int amount, int available) { }

    private final CatalogClient client;

    public CatalogAggregator(CatalogClient client) {
        this.client = client;
    }

    public CompletableFuture<Snapshot> fetch(String sku) {
        CompletableFuture<CatalogClient.Price> price =
                client.price(sku);
        CompletableFuture<CatalogClient.Stock> stock =
                client.stock(sku);

        return CompletableFuture.allOf(price, stock)
                .thenApply(ignored -> new Snapshot(
                        sku,
                        price.join().amount(),
                        stock.join().available()));
    }
}
~~~

Điểm chính:

- Lấy **hai handle Future trước**, không gọi `join()` ngay sau mỗi lần dispatch.
- Gộp bằng `allOf(price, stock)` để quan sát **cả hai** đã hoàn thành.
- Trong `thenApply`, đọc kết quả đúng kiểu `Price` và `Stock` để tạo `Snapshot`; đó là callback đồng bộ không-blocking theo dữ liệu đã có.
- `fetch` trả `CompletableFuture<Snapshot>` để caller chọn cách đợi/compose, thay vì chặn thread ngay trong aggregator.
- `@Async` nằm trên phương thức của bean **khác** so với aggregator; không có self-invocation.

### 6.6. Chạy và kết quả

Từ thư mục chứa `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Bỏ qua log Spring/Maven, dòng do chương trình in là:

~~~text
SNAPSHOT=Snapshot[sku=P-7, amount=120, available=7]
~~~

Đầu ra DTO không phụ thuộc thứ tự worker hoàn thành, vì `allOf` đợi đủ và record được dựng theo đúng field name trong code. Dù pool có hai core workers, **không bảo đảm** hai method chắc chắn được CPU thực thi đồng thời; queue, thread scheduling và tốc độ công việc quyết định độ chồng lấp thực tế. Bài này kiểm tra correctness của ghép kết quả, không đo benchmark về concurrency.

## 7. Thu tất cả thành công hay chấp nhận thành công một phần?

### 7.1. All-or-nothing: giữ nguyên ngoại lệ

Với một báo cáo đòi hỏi **tất cả** nguồn chính xác, giữ chính sách mặc định:

~~~java
// Snippet trong service: price và stock là CompletableFuture có kiểu.
CompletableFuture<Snapshot> allRequired =
        CompletableFuture.allOf(price, stock)
                .thenApply(ignored -> new Snapshot(
                        price.join(), stock.join()));
~~~

`Snapshot` ở đây là record minh họa có hai field tương ứng kiểu đầu vào, không phải record `Snapshot` trong ví dụ Spring ở mục 6. Nếu `price` lỗi, `thenApply` không tạo snapshot. Gắn `whenComplete((value, error) -> ...)` để log/metric, hoặc `handle` ở tầng API để chuyển lỗi thành status. Trong `@Async` Spring, lỗi nghiệp vụ trong worker có thể được chuyển thành exceptional completion; lỗi **từ chối gửi việc** khi executor đầy có thể xảy ra ngay ở lời gọi proxy (ví dụ `TaskRejectedException`), vì vậy cả fan-out phase cũng cần `try/catch` nếu cần phản hồi 503 thay vì 500 ngẫu nhiên.

### 7.2. Partial success: bình thường hóa từng kết quả trước allOf

Nếu nghiệp vụ vẫn cho phép tổng hợp khi một nhà cung cấp lỗi, hãy **biến mỗi Future thành một kết quả có trạng thái tường minh** trước khi gửi vào `allOf`.

~~~java
// Trích đoạn minh họa; record Outcome<T> do dự án định nghĩa.
record Outcome<T>(String source, T value, Throwable error) { }

CompletableFuture<Outcome<Price>> safePrice =
        price.handle((value, error) ->
                new Outcome<>("price", value, error));

CompletableFuture<Outcome<Stock>> safeStock =
        stock.handle((value, error) ->
                new Outcome<>("stock", value, error));

CompletableFuture<PartialView> partial =
        CompletableFuture.allOf(safePrice, safeStock)
                .thenApply(ignored ->
                        new PartialView(
                                safePrice.join(),
                                safeStock.join()));
~~~

`Price`, `Stock` và `PartialView` trong snippet là model riêng của dự án; tên record `Outcome` chỉ áp dụng cho snippet. Vì `handle` chạy cho cả success/failure và trả về `Outcome` bình thường, barrier mới có thể thành công và callback nhìn thấy **từng lỗi**. Nếu handler ném exception thì Future `safePrice` vẫn có thể exceptional, do vậy handler cần ngắn, không bị lỗi ngoài ý muốn.

Với hệ thống thực, nên chuyển `Throwable` thành mã lỗi đã phân loại thay vì đưa stack trace/exception chứa dữ liệu nhạy cảm thẳng ra HTTP response. Giữ log gốc trên server, còn client nhận `source`, `status`, `message` phù hợp.

### 7.3. Fail-fast khác với đợi đủ rồi báo lỗi

Nếu một nguồn thất bại sớm còn một nguồn khác bị treo, `allOf` có thể chưa hoàn tất vì nó là barrier **chờ mọi Future terminal**. Vì vậy không được dựa vào `allOf` như cơ chế “fail-fast” để trả lỗi lập tức. Muốn kết thúc sớm khi gặp lỗi, cần thiết kế bổ sung: deadline chung, tín hiệu thất bại riêng hoặc thư viện/logic phối hợp có cancellation và quy tắc nhận trạng thái cụ thể.

Nếu nhiều nguồn thất bại, `allOf` không đưa ra danh sách các exception. Trong mô hình partial success, `handle` trên từng nguồn như trên giúp quan sát đầy đủ. Trong mô hình all-or-nothing, có thể log lỗi riêng tại từng Future trước khi tạo barrier, nhưng tránh log cùng một lỗi trùng lặp nhiều lần.

## 8. Timeout, hủy và bảo vệ khỏi chờ vô hạn

### 8.1. allOf không có timeout mặc định

Nếu một Future bị mất do `DiscardPolicy`/`DiscardOldestPolicy` âm thầm bỏ task, bị kẹt I/O hoặc không ai gọi `complete`, barrier cũng có thể pending mãi. `allOf` không nhận thời hạn đợi trong constructor.

Người gọi đồng bộ có thể dùng:

~~~java
// Snippet: combined là CompletableFuture<Snapshot>.
try {
    Snapshot view = combined.get(3, TimeUnit.SECONDS);
    send(view);
} catch (TimeoutException ex) {
    recordDeadlineExceeded();
} catch (ExecutionException ex) {
    recordFailure(ex.getCause());
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Interrupted while waiting", ex);
}
~~~

`send`, `recordDeadlineExceeded`, `recordFailure` ở đây là method nghiệp vụ giả định, không phải ví dụ độc lập. `get(timeout)` giới hạn **thời gian chờ của caller**; không làm `combined` tự hoàn tất và không tự dừng các task con.

Với `CompletableFuture`, có thể làm stage tổng hợp hoàn tất exceptionally khi quá hạn:

~~~java
// Snippet: future tổng hợp do ứng dụng tạo và quản lý.
CompletableFuture<Snapshot> bounded =
        combined.orTimeout(3, TimeUnit.SECONDS);
~~~

`orTimeout` trả **cùng chính** `CompletableFuture` được gọi, không tạo một bản copy độc lập. Sau timeout, `join()` có thể ném `CompletionException` chứa `TimeoutException`. Nhưng các Future con và công việc I/O thực tế vẫn có thể tiếp tục; timeout không thay thế HTTP/DB socket timeout, cancellation, idempotency hoặc quản lý worker lifecycle.

### 8.2. Cancellation của aggregate không phải cancellation của mọi child

~~~java
CompletableFuture<Void> all = CompletableFuture.allOf(a, b, c);
all.cancel(true);
~~~

`cancel(true)` trên `CompletableFuture` làm chính `all` hoàn tất như một cancellation (nếu chưa terminal). Nó **không tự interrupt** các task upstream và không cam kết `a`, `b`, `c` đều bị hủy. Trong implementation của `CompletableFuture`, tham số `mayInterruptIfRunning` không điều khiển trực tiếp việc interrupt task. Muốn quản lý hủy, cần lưu riêng các Future con và thực hiện hủy/cancel request theo hợp đồng executor, đồng thời xử lý việc task vẫn có thể hoàn tất muộn.

Khi task gây side effect DB/HTTP, sau timeout/hủy caller có thể retry và task cũ vẫn ghi dữ liệu. Dùng idempotency key, conditional update và trạng thái job để tránh duplicate. Với công việc lâu dài phải sống qua restart, in-memory `CompletableFuture` không thay thế DB/message queue bền vững.

### 8.3. Không tạo fan-out vô hạn

Với hàng ngàn Future cùng gửi vào pool và queue quá lớn, thời gian chờ của từng task có thể vượt deadline dù worker còn hoạt động. `allOf` không tự điều tiết số task đang in-flight. Áp dụng:

- Pool và queue có giới hạn; xử lý `TaskRejectedException` ngay khi submit.
- Semaphore/bulkhead hoặc chia danh sách thành các nhóm có kích thước tối đa; lưu ý batching tuần tự có thể giảm song song nhưng giúp ổn định tải.
- Timeout tổng và timeout riêng cho từng lời gọi bên ngoài; deadline truyền qua service nếu cần.
- Metric số task đã gửi, active, queued, failed, timeout, rejected và `allOf` đang pending.
- Không blocking `join()/get()` bên trong chính pool nhỏ đang cần chạy các task còn lại; có thể gây starvation/deadlock nếu tất cả worker chờ công việc vẫn nằm trong queue.

Đối với CPU-bound workload, tăng pool vô hạn không tăng throughput tùy ý; với I/O-bound workload phải xét số connection, quota và latency bên ngoài, không chỉ thread count.

## 9. Hiểu đúng thenApply, thenApplyAsync và thread thực thi

~~~java
CompletableFuture<Result> aggregate =
        CompletableFuture.allOf(a, b)
                .thenApply(ignored -> combine(a.join(), b.join()));
~~~

`thenApply` không tự hẹn chạy trên một executor riêng. Theo chính sách `CompletableFuture`, callback **có thể chạy trên thread vừa hoàn tất stage cuối**, hoặc thread tham gia completion khác; nếu barrier đã hoàn tất khi đăng ký, callback cũng có thể chạy ngay trên caller. Vì vậy callback nên **nhẹ**, chỉ tạo record/map hoặc tính toán rẻ.

Nếu bước tổng hợp tốn CPU hoặc ghi file lớn, có thể chọn:

~~~java
CompletableFuture<Result> aggregate =
        CompletableFuture.allOf(a, b)
                .thenApplyAsync(
                        ignored -> combine(a.join(), b.join()),
                        aggregationExecutor);
~~~

`aggregationExecutor` ở đây là `Executor` mà ứng dụng đã khởi tạo và quản lý; snippet chưa phải chương trình độc lập. `thenApplyAsync` gửi callback sang executor được truyền. Cũng cần quản lý rejection: nếu executor tổng hợp không nhận được task, stage có thể exceptional. Đừng dùng `thenApplyAsync` chỉ để đọc hai giá trị rồi tạo record nếu chi phí scheduling lớn hơn công việc.

Một nguy cơ khác là kết hợp kiểu sai:

~~~java
// Anti-pattern: join ngay khi submit, làm tuần tự hóa cả đường gọi.
Result aResult = loadA().join();
Result bResult = loadB().join();
return CompletableFuture.completedFuture(combine(aResult, bResult));
~~~

Đoạn này khiến caller đợi A xong **trước khi** gửi B (trong trường hợp `loadA` mới dispatch lúc gọi), mất lợi thế chạy song song. Hãy **khởi tạo toàn bộ futures trước**, rồi dùng barrier để thu kết quả. Với công việc phụ thuộc tuần tự, `thenCompose` mới là lựa chọn đúng, không cố fan-out các bước chưa có dữ liệu.

## 10. Các lỗi phổ biến

| Triệu chứng / hiểu nhầm | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `allOf(...).join()` trả `null` | Kiểu kết quả của barrier là `Void` | Giữ các Future đầu vào và đọc từng `join()` sau barrier |
| Thu kết quả thành `Object[]` và cast liên tục | Mất generic type ở tầng ứng dụng | `sequence(List<CompletableFuture<T>>)` hoặc record/DTO |
| Một nguồn thất bại, không nhận được kết quả còn lại | `allOf` exceptional, `thenApply` không chạy | Chọn all-or-nothing hoặc `handle` từng Future trước khi gom |
| Kết quả không theo thứ tự hoàn tất | Pattern `sequence` thu theo thứ tự danh sách đầu vào | Sắp xếp theo ID/priority/time nếu cần |
| Một task treo, allOf cũng treo | Không có deadline hoặc task bị silently discarded | Timeout, rejection có tín hiệu, job state và monitoring |
| Timeout tổng nhưng worker vẫn ghi DB | Timeout không cancel upstream task | Cancellation contract, I/O timeout, idempotency |
| Dùng `@Async` mà vẫn chạy inline | Thiếu `@EnableAsync`, self-invocation hoặc dùng `SyncTaskExecutor` | Gọi qua Spring proxy, xác nhận executor |
| Callback tổng hợp làm chậm worker | `thenApply` chạy trên completion thread | Giữ callback nhỏ hoặc dùng `thenApplyAsync` với pool riêng |
| API HTTP vẫn chậm | Controller gọi `join()` ngay sau khi fan-out | Trả async type hoặc job ID/202 theo contract |
| Vượt tải hàng ngàn task | Không giới hạn fan-out và queue | Bound concurrency, pool/queue, backpressure |
| Test thỉnh thoảng sai | Dựa vào `Thread.sleep` để đo thời gian hoàn tất | Dùng `CountDownLatch`, Future thủ công và assert trạng thái |
| Nuốt lỗi bằng `exceptionally` trả dữ liệu giả | Error handling che giấu dữ liệu thiếu | Kết quả partial phải chứa trạng thái nguồn, không báo thành công giả |

### Checklist khi review đoạn dùng allOf

1. Danh sách Future có kiểu cụ thể và không có phần tử `null`?
2. Có **dispatch tất cả** trước khi chờ, không vô tình gọi `join()` tuần tự?
3. `allOf` có được dùng như barrier, không nhầm nó chứa `List<T>`?
4. Code thu kết quả nằm trong `thenApply`/`thenCompose` sau khi barrier thành công, không block ở request thread khi chưa cần?
5. Nếu một Future lỗi, contract của API muốn fail toàn bộ hay trả partial result?
6. Có timeout, lỗi rejection, hủy và cơ chế báo task pending quá lâu?
7. Có giới hạn đồng thời/queue, không fan-out vô hạn hoặc block worker trên các Future cùng pool?
8. Trong Spring, lời gọi `@Async` đi qua proxy từ bean khác, executor có tên đúng và được quản lý vòng đời?
9. Output DTO giữ đúng các field/types, không dựa vào thứ tự hoàn tất ngẫu nhiên?
10. Có test cho input rỗng, nhiều kết quả, một lỗi, nhiều lỗi, timeout, một Future pending và overload?

## 11. Bài tập tự kiểm tra

1. Tại sao `CompletableFuture.allOf(a, b)` trả `CompletableFuture<Void>` chứ không phải `CompletableFuture<List<T>>`? Dữ liệu ở đâu?
2. Hai Future kiểu `CompletableFuture<String>` hoàn tất theo thứ tự B rồi A. Hàm `sequence(List.of(A,B))` trả thứ tự nào? Vì sao?
3. Nếu ba Future có các kiểu `User`, `Balance` và `Stock`, làm thế nào trả `CompletableFuture<Dashboard>` mà không dùng `Object[]`?
4. Vì sao `allOf(...).thenApply(...)` không chạy callback thành công khi một Future con thất bại? Cần làm gì nếu muốn báo cáo cả dữ liệu thành công lẫn lỗi?
5. Nếu một Future báo lỗi nhưng Future còn lại không bao giờ hoàn tất, barrier có thể trả lỗi ngay hay vẫn chờ? Cơ chế nào giải quyết thời hạn?
6. `get(2, SECONDS)`, `orTimeout(2, SECONDS)` và `cancel(true)` khác nhau thế nào? Chúng có dừng DB write không?
7. Khi dùng Spring `@Async`, tại sao controller không nên gọi `join()` ngay lập tức nếu API muốn trả lời nhanh?
8. `thenApply` có bảo đảm chạy trên một pool riêng không? Khi nào chọn `thenApplyAsync`?
9. Nếu 5.000 yêu cầu cùng fan-out 10 tác vụ, `allOf` có tự giới hạn độ đồng thời không? Cần lớp bảo vệ nào?

**Ghi nhớ:** `allOf` giải quyết bài toán **chờ đủ**, không giải quyết bài toán **thu dữ liệu có kiểu** hoặc điều tiết concurrency. Giữ các `CompletableFuture<T>` ban đầu, ghép tín hiệu bằng `allOf`, đọc từng kết quả sau khi tất cả thành công và dựng `List<T>`/DTO rõ ràng. Với lỗi từng phần, dùng `handle` trước khi gom; với production, bổ sung deadline, backpressure và theo dõi task.

## Tài liệu chính thức

- [Java SE 17 — CompletableFuture (allOf, anyOf, thenApply, handle, orTimeout)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 17 — CompletionStage](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html)
- [Spring Framework 6.2 — Task Execution, @Async và Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
