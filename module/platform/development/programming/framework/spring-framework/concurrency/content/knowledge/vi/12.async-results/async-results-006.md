# Không dùng kiểu trả về đồng bộ thông thường để giả định vẫn nhận kết quả

## 1. Vấn đề: ghi @Async không biến String thành kết quả trả ngay

Trong Java thông thường, một phương thức khai báo `String` và chạy đồng bộ cho người gọi một giá trị ngay khi phương thức kết thúc:

```java
public String calculate() {
    return "42";
}

// Lời gọi đồng bộ:
String value = service.calculate();
System.out.println(value);
```

Đây là một đoạn mã minh họa trong các class có sẵn, chưa phải chương trình độc lập. Người gọi đi tiếp sau khi `calculate()` hoàn thành và nhận chính giá trị trả về.

Khi muốn Spring chạy một phương thức **bất đồng bộ** qua `@Async`, người học dễ viết nhầm:

```java
import org.springframework.scheduling.annotation.Async;

@Async
public String calculate() {
    return "42";
}
```

**Đây là cách khai báo sai đối với cơ chế Spring `@Async` thông thường.** `String` là kiểu trả về đồng bộ: nó không biểu diễn một công việc sẽ hoàn thành sau, cũng không có kênh thông báo lỗi, chờ hoặc hủy. Spring không thể vừa trả ngay cho caller vừa giữ nguyên hợp đồng method `String calculate()` theo cách mà proxy `@Async` hỗ trợ.

Theo JavaDoc `org.springframework.scheduling.annotation.Async`, kiểu trả về của phương thức đích được hỗ trợ là **`void` hoặc một kiểu `java.util.concurrent.Future`**, trong đó có **`CompletableFuture<T>`**. Các kiểu đơn giản như `String`, `int`, `UserDto`, `List<UserDto>`, `Optional<UserDto>` hoặc `ResponseEntity<UserDto>` **không được phép** làm kiểu trả về trực tiếp của phương thức `@Async` theo mô hình này.

Trong một lời gọi thật sự bị Spring async interceptor chặn, kiểu không được hỗ trợ thường gây `IllegalArgumentException` với nội dung tương tự “Invalid return type for async method ...” thay vì trả về `String` như mong đợi. Nếu bạn vẫn quan sát thấy `String` trả về bình thường, đó có thể là vì phương thức **đã chạy đồng bộ**, ví dụ qua lời gọi `this.calculate()` bỏ qua proxy, hoặc chưa bật xử lý `@Async`. Không được lấy biểu hiện “có dữ liệu” làm bằng chứng bất đồng bộ đang hoạt động.

**Nguyên tắc trung tâm:** Khi muốn nhận kết quả từ công việc `@Async`, hãy thiết kế **giao diện trả về đại diện cho kết quả tương lai**, phổ biến nhất là `CompletableFuture<T>`; khi không cần trả kết quả cho caller, có thể dùng `void` và thiết kế cách ghi nhận lỗi phù hợp.

## 2. Vì sao kiểu trả về đồng bộ không phù hợp?

Một phương thức đồng bộ trả `T` biểu đạt:

```text
Caller --------------------> method()
       chờ method chạy xong
       <-------------------- T
       tiếp tục với giá trị T
```

Một phương thức `@Async` được Spring xử lý qua proxy thường biểu đạt:

```text
Caller -> Spring proxy -> chọn Executor -> gửi công việc
Caller <---------------- Future<T> / CompletableFuture<T>
    |                          |
    | làm việc khác            | worker thực thi method thật
    |                          |
    +-- quan sát/chờ ----------+--> T hoặc exception khi hoàn tất
```

Vì kết quả `T` chưa chắc đã có khi caller trở về, đối tượng được trả phải đại diện cho **trạng thái chưa hoàn tất, hoàn tất thành công hoặc hoàn tất thất bại**. `Future<T>` mang hợp đồng cơ bản đó, còn `CompletableFuture<T>` hỗ trợ thêm các thao tác phối hợp và biến đổi kết quả.

Không nên suy luận rằng `@Async` tạo ra một đối tượng `T` đặc biệt để người gọi sử dụng như dữ liệu đã có. Nếu muốn dữ liệu `T` ngay lập tức, đó là **hợp đồng đồng bộ**: gọi một phương thức bình thường, chờ hoàn tất, hoặc quyết định rõ thời điểm chờ qua `Future.get()`/`join()`. Không thể nhận cả “ngay lập tức” và “kết quả thực của việc chưa hoàn tất” mà không có một abstraction biểu diễn trạng thái tương lai.

### 2.1. So sánh các kiểu trả về

| Khai báo method | Dùng với Spring @Async thông thường? | Người gọi có gì? |
|---|---|---|
| `void send()` | Có | Không có handle kết quả; cần kênh lỗi/giám sát riêng |
| `Future<String> load()` | Có | `Future` để chờ, hủy, quan sát trạng thái và lỗi |
| `CompletableFuture<String> load()` | Có | Future và API phối hợp kết quả không chặn |
| `String load()` | **Không** | Kiểu đồng bộ, không phải handle của tác vụ |
| `int count()` / `boolean check()` | **Không** | Giá trị nguyên thủy đồng bộ |
| `UserDto load()` | **Không** | DTO trực tiếp, không biểu diễn việc chưa hoàn tất |
| `List<UserDto> loadAll()` | **Không** | Collection trực tiếp, không phải Future |
| `Optional<UserDto> find()` | **Không** | Có/không có giá trị hiện tại, không phải trạng thái hoàn tất |
| `ResponseEntity<UserDto> response()` | **Không** | Wrapper HTTP không phải Future |
| `CompletionStage<String> load()` | **Không theo khai báo này** | `CompletionStage` không mở rộng `Future`; hãy khai báo `CompletableFuture<String>` nếu dùng Spring @Async |
| `Mono<String> load()` / `Flux<String> load()` | **Không theo @Async này** | Reactive Publisher có mô hình thực thi khác; không phải Future |

**Điểm tinh tế:** `CompletableFuture<T>` vừa triển khai `Future<T>` vừa triển khai `CompletionStage<T>`. Nhưng **kiểu trả về khai báo trong chữ ký** mới là điều Spring kiểm tra. Viết `CompletionStage<T>` không giống viết `CompletableFuture<T>` dù đối tượng thực tế trả về có thể là một `CompletableFuture`.

Các ghi chú này áp dụng cho annotation `@Async` của Spring với interceptor mặc định, không khẳng định mọi hệ thống bất đồng bộ Java chỉ có thể dùng Future. Reactor, Kotlin coroutine, messaging và Spring MVC có những hợp đồng khác; đừng trộn các cơ chế đó một cách vô thức.

## 3. Quy tắc API chính xác của Spring @Async

JavaDoc `@Async` cho biết:

- Method có thể nhận các tham số thông thường.
- Kiểu trả về phải là `void` hoặc thuộc họ `Future` được hỗ trợ.
- Có thể khai báo `CompletableFuture<T>` để phối hợp với bước tiếp theo.
- `Future` caller nhận từ Spring proxy là **handle bất đồng bộ thực** để theo dõi kết quả.
- Method đích vẫn phải trả đúng kiểu khai báo. Vì vậy nó có thể trả một `CompletableFuture.completedFuture(value)` sau khi hoàn tất phép tính **trên worker**; Spring proxy tạo ra một handle khác đại diện cho lần thực thi bất đồng bộ.

Điểm cuối dễ gây nhầm lẫn. Nhìn vào thân method:

```java
@Async("resultExecutor")
public CompletableFuture<Integer> doubleValue(int n) {
    int result = n * 2;
    return CompletableFuture.completedFuture(result);
}
```

Nhiều người thấy `completedFuture(...)` rồi kết luận “method này thực ra không async”. Kết luận ấy **không đúng nếu lời gọi đi qua Spring proxy**. Thân method được worker thực thi và trả một Future đã hoàn tất khi tính xong; proxy sẽ cung cấp cho caller một handle của **toàn bộ công việc được gửi đi**. Điều đó khác với:

```java
public CompletableFuture<Integer> doubleValue(int n) {
    return CompletableFuture.completedFuture(n * 2);
}
```

Nếu thiếu `@Async` và không có cơ chế async khác, phép tính `n * 2` được thực hiện trên luồng gọi; đối tượng CompletableFuture chỉ gói kết quả đã có. **Kiểu trả về CompletableFuture tự nó không bảo đảm có luồng nền.**

Có thể diễn đạt hai tầng Future như sau:

```text
Caller
  |
  | gọi qua @Async proxy
  v
Spring tạo/sử dụng Future ngoài (caller giữ)
  |
  | Executor nhận task
  v
Worker thực thi method đích
  |
  | method trả Future trong, thường completedFuture(value)
  v
Spring lấy/ghép kết quả vào Future ngoài
  |
  v
Caller quan sát Future ngoài -> value hoặc lỗi
```

Với phương thức trả `void`, caller không nhận Future ngoài. Với phương thức khai báo `String`, không có giao diện `Future` phù hợp để proxy trả và Spring từ chối chữ ký đó.

## 4. Ví dụ sai thường gặp và cách sửa đúng

### 4.1. Trả String trực tiếp

**Sai:**

```java
@Async("resultExecutor")
public String generateCode(String prefix) {
    return prefix + "-123";
}
```

**Đúng khi phải nhận giá trị:**

```java
@Async("resultExecutor")
public CompletableFuture<String> generateCode(String prefix) {
    String code = prefix + "-123";
    return CompletableFuture.completedFuture(code);
}
```

Đây là những phương thức minh họa trong một Spring bean; không phải chương trình độc lập. Bên gọi phải thay chữ ký:

```java
CompletableFuture<String> pending = service.generateCode("INV");
// Làm việc khác hoặc gắn pipeline trước khi quan sát kết quả.
String code = pending.join();
```

`join()` có thể chặn cho đến khi kết quả sẵn sàng. Nếu gọi nó ngay và luôn phải chờ, caller vẫn bị chặn dù thân method đã chuyển sang executor khác; xem phần phối hợp không chặn ở dưới.

### 4.2. Trả DTO, List hoặc Optional trực tiếp

**Sai:**

```java
@Async
public UserDto findUser(String id) {
    return repository.load(id);
}
```

**Cách thiết kế trả về hợp lệ:**

```java
@Async("resultExecutor")
public CompletableFuture<UserDto> findUser(String id) {
    UserDto user = repository.load(id);
    return CompletableFuture.completedFuture(user);
}
```

`UserDto` và `repository` là kiểu/thành phần nghiệp vụ do ứng dụng cung cấp; hai đoạn trên **không** phải class Java độc lập. Đoạn sửa dùng Future chứa **UserDto** chứ không trả UserDto trực tiếp.

Nếu nghiệp vụ trả một collection, kiểu tương ứng có thể là `CompletableFuture<List<UserDto>>`. Nếu kết quả có thể vắng mặt, có thể dùng `CompletableFuture<Optional<UserDto>>`. Đó là những Future chứa kết quả nghiệp vụ; không đảo thành `List<CompletableFuture<UserDto>>` nếu nghiệp vụ thực sự chỉ có một task tạo ra cả danh sách, và không nhầm `Optional` với handle hoàn tất.

### 4.3. Trả boolean hoặc int trực tiếp

**Sai:**

```java
@Async
public boolean sendNotification(String recipient) {
    // Trả boolean khi method chạy xong không được Spring @Async hỗ trợ.
    return true;
}
```

**Đúng nếu caller cần biết thành công/thất bại bằng dữ liệu nghiệp vụ:**

```java
@Async("resultExecutor")
public CompletableFuture<Boolean> sendNotification(String recipient) {
    boolean delivered = sendThroughProvider(recipient);
    return CompletableFuture.completedFuture(delivered);
}
```

`sendThroughProvider` là phương thức giả định của service. Nếu thành công được biểu diễn bằng việc method hoàn tất, còn thất bại bằng ngoại lệ, có thể trả `CompletableFuture<Void>` thay vì `Boolean`. Nhưng phải xác định rõ boolean đại diện cho “đã gửi tới provider”, “provider chấp nhận” hay “người nhận đã nhận”; async không tự định nghĩa ý nghĩa thành công.

### 4.4. Không cần trả kết quả: dùng void có chủ đích

```java
@Async("resultExecutor")
public void writeAuditEvent(String eventId) {
    auditRepository.save(eventId);
}
```

Đây là ví dụ phương thức trong Spring bean, giả định có `auditRepository`. `void` hợp lệ nhưng caller không thể gọi `get()` hoặc `join()` để lấy kết quả, cũng không nhận trực tiếp lỗi bên trong task nếu nó chạy trên worker. Nếu audit là dữ liệu quan trọng phải lưu dù JVM crash, chỉ dùng `@Async void` chưa đủ; cần cơ chế lưu công việc bền vững phù hợp.

**Không chọn `void` chỉ để sửa lỗi chữ ký khi caller thực sự cần nhận trạng thái.** Hãy chọn kiểu trả về theo hợp đồng của nghiệp vụ, không chỉ để làm annotation hết báo lỗi.

## 5. Future<T> và CompletableFuture<T> — khác nhau thế nào?

Cả hai có thể biểu diễn một phép tính sẽ hoàn tất sau; nhưng khả năng theo dõi và phối hợp khác nhau:

| Nhu cầu | Future<T> | CompletableFuture<T> |
|---|---|---|
| Chờ lấy giá trị | `get()` | `get()` hoặc `join()` |
| Chờ có thời hạn | `get(timeout, unit)` | `get(timeout, unit)`, và các API timeout đặc thù |
| Kiểm tra hoàn tất | `isDone()` | `isDone()` |
| Hủy theo hợp đồng | `cancel(...)` | `cancel(...)` |
| Biến đổi khi hoàn tất mà không chờ ngay | Không có API composition trong giao diện Future cơ bản | `thenApply(...)`, `thenCompose(...)` |
| Phối hợp hai công việc | Cần orchestration riêng | `thenCombine(...)`, `allOf(...)` |
| Phục hồi lỗi | Thường xử lý quanh `get()` | `exceptionally(...)`, `handle(...)`, `whenComplete(...)` |
| Kiểu được Spring @Async chấp nhận | Có | Có |

Ghi chú: `Future.get()` có thể ném `InterruptedException` và `ExecutionException`; `get(timeout, unit)` thêm `TimeoutException`. `CompletableFuture.join()` thường báo lỗi qua `CompletionException` (unchecked), có thể ném `CancellationException` nếu bị hủy. Những cách báo lỗi khác nhau không làm cho task tự an toàn hơn.

### 5.1. Cách dùng Future cơ bản

```java
@Async("resultExecutor")
public Future<Integer> calculateTax(int amount) {
    int tax = amount / 10;
    return CompletableFuture.completedFuture(tax);
}
```

Đây là đoạn method Spring hợp lệ: chữ ký khai báo `Future<Integer>`; thân method trả một `CompletableFuture<Integer>` vì kiểu này hiện thực `Future<Integer>`.

Caller:

```java
Future<Integer> pending = service.calculateTax(200);
try {
    Integer tax = pending.get();
    System.out.println(tax);
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    // Tầng gọi quyết định dừng hoặc truyền lỗi phù hợp.
} catch (ExecutionException execution) {
    Throwable rootCause = execution.getCause();
    // Ghi nhận/xử lý lỗi gốc.
}
```

Đây là mảnh mã minh họa trong phương thức caller, cần import `java.util.concurrent.Future` và `ExecutionException`. `get()` chặn tới khi task xong. Nếu muốn UI/request không bị chặn, nên thiết kế phản hồi theo tương lai thay vì gọi `get()` ngay.

### 5.2. Cách dùng CompletableFuture

```java
@Async("resultExecutor")
public CompletableFuture<Integer> calculateTax(int amount) {
    int tax = amount / 10;
    return CompletableFuture.completedFuture(tax);
}
```

Caller có thể gắn một phép biến đổi:

```java
CompletableFuture<String> description = service
        .calculateTax(200)
        .thenApply(tax -> "Thuế: " + tax);
```

Phần tạo pipeline ở caller không nhất thiết chặn để chờ phép tính hoàn tất. `thenApply` có thể được chạy ở luồng hoàn tất stage trước hoặc luồng đăng ký continuation nếu kết quả đã sẵn sàng; **không cam kết chạy trên một executor riêng**. Khi cần ấn định executor cho continuation bất đồng bộ, dùng overload `thenApplyAsync(action, specificExecutor)` và đảm bảo executor được quản lý đúng vòng đời.

### 5.3. Khi nhiều bước phụ thuộc

Nếu bước B cũng là async và trả `CompletableFuture<U>`, hãy cân nhắc `thenCompose` để ghép pipeline:

```java
CompletableFuture<String> workflow = service.findUserId("A")
        .thenCompose(userId -> service.loadProfile(userId))
        .thenApply(profile -> "Đã tải hồ sơ: " + profile);
```

Đây là mảnh code kiến trúc, giả định service có hai method trả `CompletableFuture<String>`. `thenCompose` “làm phẳng” future của bước B, khác với `thenApply` có thể tạo `CompletableFuture<CompletableFuture<String>>` nếu lambda trả future.

Đừng bao bọc thêm một lớp `CompletableFuture.supplyAsync(...)` bên ngoài phương thức `@Async` chỉ để “chắc chắn bất đồng bộ”: điều đó có thể tạo hai lượt scheduling, chuyển việc sang common pool nếu không truyền executor, tăng khó khăn về context và làm lỗi khó theo dõi.

## 6. Ví dụ Spring đầy đủ với Java 17: @Async trả Future đúng cách

Ví dụ này cho thấy một method trả `CompletableFuture<Integer>`, một method trả `Future<String>` và executor có thread prefix riêng. Chương trình lấy service từ Spring `ApplicationContext` để lời gọi **đi qua proxy `@Async`**.

Đây là ví dụ Maven tối giản sử dụng **Java 17+** và **Spring Framework 6.2.7**. Spring sẽ được Maven tải; không thể chỉ chạy `javac AsyncReturnTypesDemo.java` khi chưa có dependency.

### 6.1. Cấu trúc dự án

```text
async-return-types-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── lesson/
                └── AsyncReturnTypesDemo.java
```

### 6.2. Tệp pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>lesson</groupId>
    <artifactId>async-return-types-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.7</version>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.3. Tệp src/main/java/lesson/AsyncReturnTypesDemo.java

```java
package lesson;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Future;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class AsyncReturnTypesDemo {

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            ResultService service = context.getBean(ResultService.class);

            CompletableFuture<Integer> number = service.doubleValue(21);
            Future<String> workerName = service.workerName();

            System.out.println("Kết quả: " + number.join());
            System.out.println("Đúng executor: "
                    + workerName.get().startsWith("result-worker-"));
        }
    }

    @Configuration
    @EnableAsync
    public static class AppConfig {

        @Bean("resultExecutor")
        public ThreadPoolTaskExecutor resultExecutor() {
            ThreadPoolTaskExecutor executor =
                    new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(4);
            executor.setThreadNamePrefix("result-worker-");
            return executor;
        }

        @Bean
        public ResultService resultService() {
            return new ResultService();
        }
    }

    public static class ResultService {

        @Async("resultExecutor")
        public CompletableFuture<Integer> doubleValue(int input) {
            int result = input * 2;
            return CompletableFuture.completedFuture(result);
        }

        @Async("resultExecutor")
        public Future<String> workerName() {
            return CompletableFuture.completedFuture(
                    Thread.currentThread().getName());
        }
    }
}
```

### 6.4. Biên dịch/chạy

Trong thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=lesson.AsyncReturnTypesDemo
```

**Hai dòng do chương trình in ra**, không tính thông báo riêng của Maven:

```text
Kết quả: 42
Đúng executor: true
```

Lý do kết quả ổn định:

1. `service` là bean lấy từ `AnnotationConfigApplicationContext`; lời gọi được interceptor `@Async` xử lý.
2. `@EnableAsync` kích hoạt annotation processing trong context có bean service.
3. Cả hai method chỉ rõ `@Async("resultExecutor")`; bean executor đặt thread prefix `result-worker-`.
4. `doubleValue(21)` tính ra 42 ở worker; `CompletableFuture.completedFuture(42)` là handle tạm của method đích; caller giữ CompletableFuture do proxy trả để đọc 42.
5. `workerName()` lấy tên thread của **bên đang chạy thân method**, không lấy tên caller. `startsWith("result-worker-")` kiểm chứng đúng prefix mà không phụ thuộc số thứ tự worker.
6. `join()` và `get()` trong `main` được dùng để **quan sát kết quả demo**. Với request HTTP thật, chờ trực tiếp ngay sau lời gọi có thể phá mục tiêu tránh chặn caller.
7. `ThreadPoolTaskExecutor` là bean do Spring quản lý, nên ứng dụng demo không tự `shutdown()` pool dùng chung trong service; đóng context kết thúc vòng đời bean theo cấu hình.

Ví dụ này cố ý không chứa network hoặc thao tác nặng; nó minh họa **kiểu trả về và đường thực thi**, không phải benchmark. Nếu viết `@Async public Integer doubleValue(...)` để “đơn giản hóa”, chữ ký sẽ không được async interceptor chấp nhận như ví dụ trên.

## 7. Phản ví dụ: vì sao @Async String có thể làm bạn tưởng đã chạy đúng?

Xem class minh họa:

```java
import org.springframework.scheduling.annotation.Async;

public class WrongReturnService {

    @Async("resultExecutor")
    public String getMessage() {
        return "Xin chào";
    }

    public String callFromSameClass() {
        return this.getMessage();
    }
}
```

Đoạn này không độc lập: cần đăng ký service và executor trong Spring mới có thể kiểm chứng proxy behavior. Có **hai đường gọi** cần phân biệt.

### Đường A — gọi từ bean khác qua proxy

```text
Bean ngoài -> proxy WrongReturnService -> @Async interceptor
                                   |
                                   +--> thấy declared return type String
                                   |
                                   +--> báo lỗi kiểu trả về không hợp lệ
```

Đường này không tạo ra `Future<String>` nào vì API mà method công bố là `String`; Spring sẽ từ chối chữ ký không hợp lệ. Đây là lỗi **hợp đồng lập trình**, không phải lỗi mất dữ liệu hay do quá tải pool.

### Đường B — gọi this.getMessage() trong cùng class

```text
Caller -> WrongReturnService.callFromSameClass()
                                 |
                                 +--> this.getMessage()
                                       (bỏ qua proxy)
                                 |
                                 +--> trả "Xin chào" đồng bộ
```

Trong proxy mode mặc định, lời gọi nội bộ thường không đi qua advice. Kết quả `String` có thể xuất hiện, nhưng **đó không phải bằng chứng method đã được Spring chạy bất đồng bộ**. Cách sửa không phải ép kiểu String thành Future tại caller: cần đổi chữ ký của method `@Async` cho phù hợp và gọi qua proxy đúng cách.

Nếu dùng `new WrongReturnService()` thay vì lấy bean từ Spring, annotation cũng không có hiệu lực vì đối tượng không được quản lý. Ngoài ra, lời gọi có thể chạy đồng bộ nếu executor cố ý thực thi trực tiếp; điều quan trọng là xác minh cơ chế và hợp đồng chứ không đoán theo tên annotation.

## 8. CompletableFuture trả về ngay: điều gì đã hoàn tất, điều gì chưa?

`CompletableFuture<T>` là **đối tượng kết quả tương lai**, không phải giá trị `T`. Có ít nhất ba trạng thái cần phân biệt:

- **Chưa hoàn tất:** tác vụ đang xếp hàng hoặc chạy, future chưa chứa kết quả cuối.
- **Hoàn tất bình thường:** có kết quả, có thể lấy bằng `join()/get()` hoặc pipeline.
- **Hoàn tất ngoại lệ/hủy:** future không có kết quả thành công; caller phải xử lý lỗi.

Không được hiểu mọi `CompletableFuture` được trả ra đều nhất thiết đang chờ: một phương thức có thể hoàn tất rất nhanh và caller nhận một future đã hoàn tất. Ngược lại, chỉ vì lời gọi `@Async` trả về ngay cũng không có nghĩa giá trị nghiệp vụ đã sẵn sàng.

Một quy trình an toàn:

```java
CompletableFuture<String> future = service.loadReport(reportId);

future.thenAccept(report -> {
    System.out.println("Có báo cáo: " + report);
}).exceptionally(error -> {
    System.err.println("Không tạo được báo cáo: " + error);
    return null;
});
```

Đây là đoạn code minh họa; `service.loadReport(...)` giả định trả `CompletableFuture<String>`. Caller **không** dùng `String report = service.loadReport(reportId)` vì kiểu không tương thích ngay tại biên dịch. Cũng không nên gọi `future.getNow(null)` rồi xem `null` là thất bại: `null` có thể chỉ có nghĩa công việc chưa xong hoặc kết quả hợp lệ là null, tùy thiết kế.

### 8.1. thenApply, thenCompose, thenCombine

- `thenApply(f)` biến đổi `T` thành `U` khi một stage đã hoàn tất thành công.
- `thenCompose(f)` dùng khi `f` trả một future khác, để không tạo future lồng future.
- `thenCombine(other, f)` chờ hai stage thành công và hợp nhất hai kết quả.
- `whenComplete(action)` quan sát kết quả/lỗi nhưng không phải API phục hồi lỗi có chủ đích.
- `handle(f)` có thể chuyển cả thành công và thất bại thành giá trị mới.
- `exceptionally(f)` cung cấp đường phục hồi một stage thất bại.

Với các pipeline có bước bất đồng bộ, chú ý `thenApply` không đảm bảo chạy ở một worker riêng: có thể chạy trên thread hoàn tất stage trước hoặc caller nếu stage đã hoàn tất. `thenApplyAsync(...)` không truyền executor có thể dùng common pool; nếu cần giữ một chính sách thực thi cụ thể, cung cấp executor được cấu hình rõ.

### 8.2. Không có giá trị đồng bộ để ép kiểu

Phản ví dụ:

```java
// Sai: Future<String> không thể ép thành String.
String result = (String) service.loadReport(reportId);
```

Đây là đoạn phản ví dụ cố tình sai; nếu `loadReport` khai báo trả `CompletableFuture<String>`, ép kiểu trên không hợp lệ và có thể bị lỗi biên dịch kiểu không tương thích. Không nên đổi sang `Object` để cố qua trình biên dịch rồi cast lại; đối tượng runtime vẫn là future, không biến thành `String`.

Nếu bắt buộc chờ tại một ranh giới đồng bộ, hãy **công khai việc chờ**:

```java
String result = service.loadReport(reportId).join();
```

Cách này chỉ hợp lệ nếu kiểu trả về đúng là `CompletableFuture<String>`; nó **chặn** caller cho đến lúc hoàn tất. Nó không phải phương pháp giữ API “vừa đồng bộ vừa không chặn”.

## 9. Java 17 độc lập: chứng minh Future không có kết quả ngay

Ví dụ này dùng `CountDownLatch` để giữ worker chưa hoàn tất cho tới khi caller quyết định mở chốt. Nhờ đó, `isDone()` chắc chắn là `false` ở lần kiểm tra đầu tiên và kết quả sau cùng là 42.

**Tệp `FutureIsNotValueDemo.java` — không cần Spring:**

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class FutureIsNotValueDemo {

    public static void main(String[] args)
            throws InterruptedException {

        ExecutorService pool =
                Executors.newSingleThreadExecutor();

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch allowFinish = new CountDownLatch(1);

        try {
            CompletableFuture<Integer> future =
                    CompletableFuture.supplyAsync(() -> {
                        started.countDown();
                        try {
                            allowFinish.await();
                        } catch (InterruptedException interrupted) {
                            Thread.currentThread().interrupt();
                            throw new IllegalStateException(
                                    "Đã bị ngắt", interrupted);
                        }
                        return 21 * 2;
                    }, pool);

            started.await();

            System.out.println("Đã xong trước mở chốt: "
                    + future.isDone());

            allowFinish.countDown();

            System.out.println("Kết quả sau chờ: "
                    + future.join());
        } finally {
            allowFinish.countDown();
            pool.shutdown();
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac FutureIsNotValueDemo.java
java FutureIsNotValueDemo
```

Kết quả:

```text
Đã xong trước mở chốt: false
Kết quả sau chờ: 42
```

Diễn giải:

1. `supplyAsync(..., pool)` trả ngay `CompletableFuture<Integer>` đại diện cho phép tính, không trả `int` 42.
2. Worker bắt đầu, báo `started.countDown()` rồi chờ `allowFinish`. Caller chờ `started.await()` để biết worker đã đứng tại điểm báo hiệu.
3. Lần đọc `future.isDone()` diễn ra khi chốt chưa mở, nên giá trị chính xác là `false`.
4. Sau `allowFinish.countDown()`, worker được phép hoàn tất và trả 42.
5. `join()` lấy 42 sau khi task hoàn tất. Nếu task chưa xong, `join()` sẽ đợi; không biến lời gọi thành “lấy kết quả ngay”.
6. `finally` mở chốt để tránh để worker bị kẹt khi main rời sớm, rồi gọi `shutdown()` cho pool do chương trình tự tạo.

Đây là minh họa bằng Java chuẩn, **không phải triển khai `@Async` của Spring**. Nó giúp người học thấy rõ hai khái niệm: *nhận handle ngay* và *nhận giá trị sau khi công việc xong*. Trong Spring, proxy `@Async` cũng phải cung cấp một hợp đồng kết quả tương lai thay vì biến một `String` đồng bộ thành phép tính bất đồng bộ.

## 10. Lỗi: Future báo lỗi bằng cách nào?

Phân biệt **lỗi khi định tuyến/gửi việc** và **lỗi khi thân task đã chạy**.

### 10.1. Kiểu trả về không được hỗ trợ

`@Async public String get()` là lỗi hợp đồng của phương thức. Trong Spring proxy mặc định, khi interceptor kiểm tra chữ ký không hợp lệ, thường phát sinh `IllegalArgumentException` ngay trên đường gọi. Không có `Future` để lấy lỗi vì method không công bố Future hợp lệ.

Cách sửa: đổi chữ ký và cập nhật tất cả caller liên quan; không chỉ thay annotation hoặc cố bắt một lỗi chung rồi mặc định trả null.

### 10.2. Không tìm thấy executor / executor từ chối

`@Async("missingExecutor")` có thể thất bại khi Spring không tìm được bean phù hợp; pool đã đóng/đầy có thể từ chối công việc. Đây thường là **lỗi đồng bộ tại đường gửi**, chưa chứng minh thân method đã chạy. Cần sửa wiring hoặc xử lý quá tải theo chính sách của API.

### 10.3. Exception trong method trả Future

Một phương thức hợp lệ:

```java
@Async("resultExecutor")
public CompletableFuture<Integer> divide(int a, int b) {
    int value = a / b; // b = 0 gây ArithmeticException.
    return CompletableFuture.completedFuture(value);
}
```

Caller:

```java
CompletableFuture<Integer> pending = service.divide(10, 0);

pending.whenComplete((value, error) -> {
    if (error != null) {
        System.err.println("Không thực hiện được: " + error);
    }
});
```

Đây là các mảnh mã minh họa trong Spring service/caller, không phải chương trình độc lập. Nếu task chạy qua proxy, ngoại lệ trong worker được phản ánh bằng việc Future của caller **hoàn tất theo hướng lỗi**; không thể xem Future đã được tạo là một kết quả thành công.

Nếu dùng `get()`, lỗi thường xuất hiện trong `ExecutionException`, với nguyên nhân tại `getCause()`. Nếu dùng `join()`, lỗi thường được bao trong `CompletionException`; khi future đã bị hủy có thể gặp `CancellationException`. Đừng bỏ qua cause hoặc chỉ log rằng “job failed” mà không có correlation ID.

### 10.4. Exception trong method trả void

```java
@Async("resultExecutor")
public void sendMail(String address) {
    throw new IllegalStateException("Mô phỏng gửi thất bại");
}
```

Caller không có Future trả về để nhận `IllegalStateException` nếu task chạy trên worker. Với Spring `@Async void`, lỗi chưa được xử lý trong method có thể được chuyển cho `AsyncUncaughtExceptionHandler`; Spring mặc định ghi log. Có thể cung cấp handler riêng qua `AsyncConfigurer`.

**Không dùng `void` cho nghiệp vụ mà caller buộc phải biết chắc trạng thái thành công/thất bại.** Có thể sử dụng `CompletableFuture<Void>` nếu không cần dữ liệu nhưng vẫn cần handle hoàn tất.

### 10.5. CompletableFuture<Void> cho thao tác không trả dữ liệu

```java
@Async("resultExecutor")
public CompletableFuture<Void> updateCache(String key) {
    updateCacheInternal(key);
    return CompletableFuture.completedFuture(null);
}
```

Đây là mảnh method minh họa, giả định `updateCacheInternal` tồn tại. Caller nhận được `CompletableFuture<Void>`; `join()` trả `null` khi hoàn tất bình thường, nhưng điểm quan trọng là **có thể chờ/quan sát lỗi**, khác với `void`.

## 11. Không biến controller Spring thành một lời gọi đồng bộ giả

Xét ứng dụng web có service cần thời gian tạo báo cáo. Một anti-pattern là:

```java
// Sai chữ ký cho Spring @Async:
@Async("resultExecutor")
public ReportDto buildReport(String id) {
    return reportRepository.build(id);
}
```

Phương thức trên **không** thể dùng như một phép tính Spring `@Async` trả `ReportDto` trực tiếp. Giả sử đã sửa service thành:

```java
@Async("resultExecutor")
public CompletableFuture<ReportDto> buildReport(String id) {
    ReportDto dto = reportRepository.build(id);
    return CompletableFuture.completedFuture(dto);
}
```

Lúc này controller có nhiều quyết định hợp lệ theo hợp đồng HTTP:

- Nếu API **phải trả nội dung báo cáo khi xử lý xong**, với Spring MVC có thể trả một kiểu kết quả bất đồng bộ được MVC hỗ trợ, chẳng hạn `CompletableFuture<ReportDto>` hoặc `CompletableFuture<ResponseEntity<ReportDto>>` ở tầng controller thích hợp. Spring MVC sẽ quản lý quá trình hoàn tất HTTP theo abstraction được hỗ trợ; điều này khác với việc service trả `ReportDto` đồng bộ.
- Nếu API **chỉ xác nhận đã nhận yêu cầu và trả job ID**, cần lưu trạng thái job bền vững/khả năng tra cứu phù hợp. Trả HTTP 202 không tự chứng minh background job đã hoàn tất.
- Nếu dùng `future.join()` trong controller để trả `ReportDto` ngay, controller **chặn** tới lúc công việc xong. Đây là một lựa chọn đồng bộ có chủ đích chứ không phải lời giải bất đồng bộ hoàn toàn.

Mã ví dụ Spring MVC controller (đặt trong một controller hợp lệ, có service được inject):

```java
@GetMapping("/reports/{id}")
public CompletableFuture<ResponseEntity<ReportDto>> getReport(
        @PathVariable String id) {

    return reportService.buildReport(id)
            .thenApply(ResponseEntity::ok);
}
```

Đây là **mảnh Spring MVC**, giả định `reportService.buildReport` trả `CompletableFuture<ReportDto>` và các kiểu/import Spring MVC đã sẵn sàng. Kiểu trả về của **controller** ở đây được Spring MVC xử lý theo mô hình async web request; không cần gắn `@Async` trực tiếp lên controller method chỉ vì nó trả Future. Hãy để service chuyên xử lý nghiệp vụ, controller quyết định hợp đồng HTTP.

**Phân biệt chiều wrapper:** `CompletableFuture<ResponseEntity<ReportDto>>` có Future ở ngoài và có thể được xử lý bất đồng bộ. `ResponseEntity<CompletableFuture<ReportDto>>` có ResponseEntity ở ngoài; nếu đặt `@Async` trực tiếp lên method trả kiểu này thì declared return type **không phải Future**, nên không đáp ứng hợp đồng Spring `@Async`.

## 12. @Async không bảo đảm mọi caller đều không bị chặn

Có hai lý do lớn:

**Thứ nhất — code caller tự chờ:**

```java
int result = service.doubleValue(21).join();
```

Spring có thể chạy phép tính trên worker, nhưng `join()` vẫn chặn caller cho tới khi có 42. Để có lợi ích không chặn ở biên ứng dụng, cần trả Future hoặc gắn pipeline và chỉ chờ ở điểm thực sự cần kết quả.

**Thứ hai — executor/thiết kế có thể chạy trên caller:** `SyncTaskExecutor` chạy nhiệm vụ ngay trên thread gửi. Một số rejection policy như `CallerRunsPolicy` có thể khiến caller chạy task khi pool quá tải, nếu chưa shutdown. Vì vậy “có `@Async`” không đủ để suy ra “luôn dùng luồng khác” hoặc “caller luôn trả ngay”.

Thêm nữa, `CompletableFuture.completedFuture(value)` **trong một method không có `@Async`** chỉ bọc một kết quả đã có; nếu tính toán nặng xảy ra trước lời gọi `completedFuture` trên caller, trả kiểu CompletableFuture không làm phép tính đó tự chạy nền.

## 13. Các vấn đề Spring proxy có thể che giấu lỗi trả về

Nếu một method `@Async` có kiểu trả về bất hợp lệ nhưng bạn vẫn thấy nó trả một `String` thông thường, hãy kiểm tra hạ tầng trước khi kết luận “Spring tự xử lý được”.

### 13.1. Chưa bật @EnableAsync

Trong cấu hình Java thường cần:

```java
@Configuration
@EnableAsync
public class AsyncConfiguration {
    // Đăng ký Executor/TaskExecutor phù hợp nếu cần.
}
```

Đây là class cấu hình Spring minh họa, cần các import `Configuration` và `EnableAsync` tương ứng. Nếu không bật xử lý `@Async`, annotation có thể không có tác dụng trong context đang dùng; một method thông thường vẫn trả giá trị đồng bộ.

### 13.2. Self-invocation

```java
public String outer() {
    return this.wrongAsyncMethod();
}

@Async
public String wrongAsyncMethod() {
    return "value";
}
```

Đây là **đoạn lỗi cố ý**. Trong proxy mode mặc định, `this.wrongAsyncMethod()` không qua interceptor nên vẫn nhận `String` đồng bộ. Nhưng khi một bean khác gọi method qua proxy, chữ ký `@Async String` không hợp lệ. Không nên thiết kế chương trình dựa vào tình cờ bỏ qua interceptor.

Cách giải quyết: tách method cần chạy async vào một Spring bean khác, inject bean đó và dùng chữ ký `CompletableFuture<String>`. Một lựa chọn nâng cao là AspectJ weaving đúng cấu hình, nhưng không cần cho bài toán cơ bản này.

### 13.3. Class/method không được proxy phù hợp

Method `private`, lời gọi nội bộ, đối tượng tự `new`, method `final` trong cấu hình subclass proxy và cấu trúc nhiều `ApplicationContext` có thể khiến advice không áp dụng như dự tính. Khi học, ưu tiên **public non-final method** trên Spring-managed service, gọi từ bean khác.

Theo JavaDoc `@Async`, không dùng annotation này trên method khai báo trong `@Configuration`. Chỉ đặt cấu hình executor ở `@Configuration`, còn tác vụ ở service riêng.

### 13.4. @Transactional và các advice khác

Nếu method dùng đồng thời `@Transactional` và `@Async`, cần hiểu proxy/advice order và ranh giới transaction. Transaction trong caller **không tự truyền nguyên trạng** sang worker. Nếu nghiệp vụ cần transaction khi chạy async, thiết kế transaction đúng trong đường worker và kiểm tra hành vi thật bằng integration test.

Không giải quyết sai kiểu trả về bằng cách thêm `@Transactional`, `@Retryable` hoặc `@Cacheable`: chúng có trách nhiệm khác nhau và không biến `String` thành kiểu Future hợp lệ cho `@Async`.

## 14. Timeout, hủy và thời điểm kết quả còn giá trị

Với phương thức trả Future, caller có thể đặt ngân sách chờ:

```java
Future<String> pending = service.loadReport(id);
try {
    String report = pending.get(2, TimeUnit.SECONDS);
    consume(report);
} catch (TimeoutException timeout) {
    pending.cancel(true);
    // Ghi nhận timeout và áp dụng hợp đồng nghiệp vụ.
}
```

Đây là mảnh minh họa trong caller, giả định có `service`, `consume` và các import `java.util.concurrent`. Method bao quanh phải xử lý thêm `InterruptedException`/`ExecutionException` hoặc khai báo ném tiếp.

**Hết hạn `get(timeout)` không tự hủy công việc.** `cancel(true)` là yêu cầu hủy/ngắt theo cơ chế của Future/executor; thao tác I/O hoặc task không hợp tác có thể tiếp tục. Ngoài ra, khi caller không đợi nữa, backend có thể đã thực hiện một side effect; hủy Future không phải rollback cho giao dịch hoặc dịch vụ bên ngoài.

Với `CompletableFuture`, có thể dùng các API hoàn tất khi quá hạn theo phiên bản Java, nhưng hãy phân biệt **hành vi của handle** và **việc task bên dưới thực sự dừng**. Đưa deadline vào yêu cầu nghiệp vụ nếu công việc trở nên vô nghĩa sau một thời điểm cụ thể.

Cũng tránh đợi một Future trong chính pool bị giới hạn nếu task được đợi cần tài nguyên/worker của cùng pool. Trường hợp một worker gửi việc phụ rồi chờ trong pool một worker có thể deadlock do starvation, không liên quan tới kiểu trả về `String` hay `CompletableFuture`. Kiểu đúng chỉ mở khả năng chờ/quan sát; thiết kế luồng và tài nguyên vẫn là trách nhiệm riêng.

## 15. Thread safety, visibility và kết quả bên ngoài Future

Một lỗi khác là cố dùng `void` nhưng lưu kết quả vào một field, rồi đọc field ngay sau lời gọi:

```java
private String latestReport;

@Async("resultExecutor")
public void generate() {
    latestReport = "Xong";
}

// Caller khác:
service.generate();
String value = service.getLatestReport();
```

Đây là **mảnh phản ví dụ**, không phải code độc lập. Nó có nhiều vấn đề:

- `generate()` có thể chưa chạy khi caller đọc field.
- Nếu field không được bảo vệ đúng, có vấn đề visibility và data race.
- Nhiều request cùng dùng một field trong singleton bean có thể ghi đè kết quả của nhau.
- Không có ID/handle giúp gắn kết quả với yêu cầu cụ thể.

Dùng `volatile` có thể cải thiện visibility cho một giá trị được ghi/đọc đơn giản nhưng **không** tạo cơ chế chờ hoàn tất, không liên kết kết quả với từng request và không làm một chuỗi cập nhật phức tạp thành nguyên tử.

Nếu caller cần **kết quả của chính lần gọi**, `CompletableFuture<T>` là hợp đồng tự nhiên. Nếu cần **trạng thái job tồn tại lâu** và nhiều client tra cứu, thiết kế kho trạng thái và job ID có vòng đời rõ ràng, không dùng một field singleton làm mailbox toàn ứng dụng.

Một Future hoàn tất thành công cung cấp điểm đồng bộ theo hợp đồng của các API concurrent thích hợp, nhưng dữ liệu mutable bên trong kết quả vẫn cần ownership rõ ràng. Ví dụ trả một `ArrayList` rồi tiếp tục sửa nó từ worker khác có thể gây race; ưu tiên snapshot bất biến hoặc cơ chế đồng bộ đúng.

## 16. Future không làm công việc nền trở thành bền vững

`CompletableFuture<T>` cho caller biết khi nào *một lần thực thi trong tiến trình hiện tại* hoàn tất; nó **không** tự đảm bảo công việc sẽ chạy tới cùng nếu JVM chết, application redeploy, pool bị đóng hoặc worker không được lên lịch.

Nếu nghiệp vụ gồm thanh toán, gửi email quan trọng, tạo chứng từ cần đảm bảo hoặc xử lý có thể kéo dài nhiều phút, phải quyết định rõ:

- Khi nào yêu cầu được xem là **accepted** và khi nào là **succeeded**?
- Có cần lưu lại công việc ở database/broker trước khi trả xác nhận cho caller?
- Retry có an toàn trước thao tác đã thực hiện một phần không? Có idempotency key?
- Làm sao truy vấn trạng thái, báo thất bại hoặc xử lý sự cố sau restart?
- Có giới hạn worker/queue, backpressure và policy từ chối rõ ràng không?

Trả `CompletableFuture<String>` đúng chữ ký `@Async` chỉ giải quyết khả năng **theo dõi kết quả của tác vụ**, không tự giải quyết toàn bộ bài toán reliability.

## 17. Kiểm thử kiểu trả về và hành vi thực thi

Một unit test chỉ thấy method được gắn `@Async` là chưa đủ. Với Spring, ít nhất cần kiểm tra:

1. Context có `@EnableAsync` thực sự hoạt động.
2. Service được lấy từ Spring, không tự `new`.
3. Method trả đúng `void`, `Future<T>` hoặc `CompletableFuture<T>`.
4. Với method cần kết quả, caller nhận Future và kết quả chính xác khi hoàn tất.
5. Ngoại lệ trong thân task làm Future lỗi, không bị coi là thành công.
6. Lỗi kiểu trả về không hợp lệ được phát hiện **khi gọi qua proxy**, không bị che bởi self-invocation.
7. Thread/executor được chọn đúng theo cấu hình; không chỉ suy đoán từ annotation.
8. Test chờ với timeout/latch nếu cần; không dùng `Thread.sleep(...)` để đoán task hoàn tất.
9. Test trường hợp pool quá tải/từ chối và chính sách dừng ứng dụng.
10. Kiểm tra hợp đồng HTTP/job khi caller không muốn đợi kết quả.

Ví dụ assertion minh họa (dùng JUnit và một Spring test context thực tế):

```java
CompletableFuture<Integer> future = service.doubleValue(21);
assertEquals(42, future.join());
```

Đoạn này không độc lập vì cần `service` lấy qua proxy và `assertEquals` từ thư viện kiểm thử. Quan trọng không phải dùng `join()` ở production, mà là test xác nhận kiểu và giá trị của Future.

Nếu cần test một invalid `@Async String`, hãy tạo bean riêng, gọi từ bean test qua proxy và kiểm tra lỗi hợp đồng; đừng “test” bằng cách tạo đối tượng `new` hoặc gọi `this.invalidMethod()` trong cùng bean, vì việc đó kiểm tra lời gọi Java thông thường chứ không kiểm tra Spring async interceptor.

### 17.1. Một số dấu hiệu cần điều tra trên production

- Runtime báo `Invalid return type for async method`: tìm chữ ký `@Async` trả `String`, DTO, primitive, `Optional`, `CompletionStage` hoặc loại không hỗ trợ.
- Người dùng báo kết quả đôi khi null: tìm logic đọc field ngay sau `void @Async` hoặc sử dụng `getNow(...)` không phân biệt trạng thái.
- API chậm dù đã `@Async`: tìm `join()/get()` ngay trên request thread hoặc `CallerRunsPolicy` lúc pool quá tải.
- Method tưởng async nhưng log luôn cùng tên thread caller: kiểm tra proxy, `@EnableAsync`, self-invocation và executor.
- Caller không thấy lỗi task: kiểm tra `void` vs Future, `AsyncUncaughtExceptionHandler` và việc có quan sát exceptionally/completion hay không.
- Lỗi “đã trả 202 nhưng tác vụ mất”: kiểm tra bảo đảm lưu công việc, không coi in-memory executor hoặc Future là message queue bền vững.

## 18. Bài tập thực hành có hướng giải

### Bài 1 — Nhận diện chữ ký sai

Cho các chữ ký:

```java
@Async String a();
@Async void b();
@Async Future<Integer> c();
@Async CompletableFuture<List<String>> d();
@Async Optional<String> e();
@Async CompletionStage<String> f();
```

Hỏi: loại nào phù hợp với Spring `@Async` thông thường?

**Định hướng:** `b`, `c` và `d` phù hợp về kiểu trả về. `a`, `e`, `f` không phù hợp; riêng `CompletionStage` không mở rộng `Future` dù một triển khai như `CompletableFuture` có thể hiện thực cả hai giao diện. Các method còn cần được Spring quản lý/proxy đúng để chạy async.

### Bài 2 — Sửa cách sử dụng DTO

Một service hiện có:

```java
@Async
public CustomerDto load(String id) {
    return repository.find(id);
}
```

Caller viết `CustomerDto dto = service.load(id);`. Hãy sửa cả chữ ký service và caller để caller có thể làm việc khác trong lúc chờ kết quả.

**Định hướng:** Sửa service thành `CompletableFuture<CustomerDto>`, tính DTO bên trong worker rồi trả `CompletableFuture.completedFuture(dto)`. Caller giữ `CompletableFuture<CustomerDto>`, gắn `thenApply/thenAccept` hoặc chuyển future cho tầng có trách nhiệm. Không gọi `join()` ngay nếu mục tiêu là tránh chặn.

### Bài 3 — Vì sao completedFuture vẫn đúng?

Method `@Async` tính một giá trị rồi trả `CompletableFuture.completedFuture(value)`. Có mâu thuẫn với mục tiêu bất đồng bộ không?

**Định hướng:** Không, nếu method được gọi qua proxy. Thân method chạy trong task của Spring executor; `completedFuture` là handle tạm từ method đích. Proxy đưa cho caller Future đại diện cho lần chạy async đó.

### Bài 4 — Tìm self-invocation

`@Async public String get()` trả String bình thường khi được gọi từ `this.get()`. Có thể kết luận Spring hỗ trợ String không?

**Định hướng:** Không. Lời gọi nội bộ không đi qua proxy trong chế độ mặc định. Phải đổi chữ ký và gọi qua Spring bean proxy trước khi đánh giá hành vi.

### Bài 5 — CompletableFuture nhưng vẫn chặn

Caller gọi `service.calculate().join()` ngay sau khi gửi task. Vì sao HTTP request vẫn có thể chậm dù executor chạy trên worker riêng?

**Định hướng:** `join()` chặn luồng HTTP request tới lúc Future hoàn tất. Dùng tích hợp async ở tầng web hoặc thiết kế phản hồi theo job ID/SLO nếu không muốn chờ.

### Bài 6 — Không cần dữ liệu nhưng cần biết đã xong

Bạn đang dùng `@Async void saveAudit()`; caller không cần trả dữ liệu nhưng phải biết đã lưu thành công trước bước tiếp theo. Chọn kiểu nào?

**Định hướng:** `CompletableFuture<Void>` và xử lý completion/failure, hoặc thiết kế transaction/orchestration nghiệp vụ khác phù hợp. `void` không cung cấp handle hoàn tất cho caller.

### Bài 7 — Chạy ví dụ

Chạy project `AsyncReturnTypesDemo` trên Spring, sau đó chạy `FutureIsNotValueDemo` thuần Java 17. Giải thích vì sao ví dụ đầu nhận 42 qua Future từ proxy, còn ví dụ thứ hai nhận được Future trước khi task được phép hoàn tất.

**Định hướng:** Cả hai tách handle khỏi giá trị; Spring giải quyết dispatch qua interceptor và `@Async`, còn Java SE dùng `CompletableFuture.supplyAsync(..., executor)`.

## 19. Checklist khi review một method @Async có kết quả

| Câu hỏi | Điều kiện mong muốn |
|---|---|
| Method định trả dữ liệu gì? | `T` được đặt **bên trong** `Future<T>`/`CompletableFuture<T>` |
| Kiểu trả về có được @Async hỗ trợ? | `void` hoặc kiểu `Future` phù hợp |
| Caller có thật sự cần kết quả? | Nếu có, không chọn `void` rồi đọc shared mutable field |
| @EnableAsync đã bật đúng context? | Có, và method được gọi qua Spring proxy |
| Executor có được cấu hình rõ? | Biết bean được chọn, giới hạn worker/queue và rejection |
| Kết quả được lấy ở đâu? | `get/join` ở ranh giới chấp nhận chặn hoặc pipeline không chặn |
| Exception được quan sát ở đâu? | Future completion/error hoặc handler cho `void` |
| Có timeout/cancel/deadline không? | Có chính sách đúng yêu cầu và hiểu task có thể chưa dừng |
| State/thread context có an toàn? | Không suy diễn transaction hay ThreadLocal tự lan truyền |
| Kết quả cần tồn tại qua restart? | Nếu có, dùng cơ chế lưu công việc/nhật ký bền vững |

## 20. Tóm tắt nguyên tắc

- **Không dùng kiểu trả về đồng bộ như `String`, `int`, DTO hay `List<T>` trực tiếp trên Spring `@Async` rồi giả định caller vẫn nhận được dữ liệu.**
- **`@Async` hỗ trợ `void` hoặc các kiểu `Future` phù hợp**, phổ biến nhất là `CompletableFuture<T>` khi cần kết quả và phối hợp nhiều bước.
- **Spring proxy trả Future đại diện cho lần thực thi bất đồng bộ**; method đích có thể dùng `CompletableFuture.completedFuture(value)` như một handle tạm khi đã tính xong trên worker.
- **`void` hợp lệ nhưng không cho caller handle hoàn tất.** Nếu cần biết xong/lỗi mà không cần dữ liệu, cân nhắc `CompletableFuture<Void>`.
- **`get()`/`join()` là những điểm có thể chặn.** Dùng pipeline hoặc abstraction async của tầng web khi muốn tránh chặn caller.
- **Kiểu đúng chưa đủ:** phải bật `@EnableAsync`, gọi qua Spring bean proxy, chọn executor phù hợp và quan sát lỗi/tải/context theo nhu cầu.
- **Future không phải dữ liệu nghiệp vụ và không phải job queue bền vững.** Nó là hợp đồng theo dõi một lần thực thi; reliability vẫn cần thiết kế riêng.

### Tài liệu chuẩn

- [Spring Framework Javadoc — @Async](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/Async.html)
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework Javadoc — @EnableAsync](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html)
- [Java SE 17 Javadoc — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE 17 Javadoc — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 17 Javadoc — CompletionStage](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html)
