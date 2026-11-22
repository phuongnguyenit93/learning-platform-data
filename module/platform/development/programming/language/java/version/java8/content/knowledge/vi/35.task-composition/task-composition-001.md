# thenCompose và làm phẳng công việc phụ thuộc trong Java

**Chủ đề:** Java 8 → Ghép tác vụ → thenCompose và làm phẳng công việc phụ thuộc.

**CompletableFuture.thenCompose(...)** giúp kết nối **những công việc bất đồng bộ phụ thuộc kết quả của nhau** mà không tạo ra nhiều tầng future. Khi bước đầu trả về một giá trị **T**, và bước kế tiếp nhận **T** để tạo một **CompletionStage<U>**, thenCompose trả một **CompletableFuture<U>** đại diện cho kết quả cuối cùng sau khi cả hai bước hoàn tất.

Công thức tư duy:

~~~text
Bước 1:  CompletableFuture<T>
                       │ T
                       ▼
Bước 2:       T -> CompletionStage<U>
                       │
                       ▼
thenCompose: CompletableFuture<U>

KHÔNG phải: CompletableFuture<CompletableFuture<U>>
~~~

Ví dụ nghiệp vụ: **tải tài khoản → lấy số điểm của tài khoản đó → phát hành ưu đãi**. Công việc sau không thể bắt đầu với dữ liệu đúng nếu bước trước chưa trả kết quả. thenCompose diễn tả mối quan hệ này thành một pipeline, thay vì gọi **join()** hoặc **get()** giữa chừng để chặn luồng.

**thenCompose là API từ Java 8 và vẫn còn áp dụng.** Các chương trình độc lập trong bài biên dịch với **Java 17+**, một số phần dùng **record**, **CompletableFuture.failedFuture** và **exceptionallyCompose** (những API được bổ sung sau Java 8 sẽ có ghi chú). Các nguyên lý tạo dependent stage, flatten, lựa chọn Executor và xử lý lỗi vẫn là cách dùng hiện đại.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Diễn giải chữ ký và hợp đồng của **thenCompose(Function<T, CompletionStage<U>>)**.
2. Phân biệt **thenApply** và **thenCompose** khi callback trả về **giá trị thông thường** hoặc **future/stage**.
3. Nhận diện và loại bỏ **CompletableFuture<CompletableFuture<T>>**.
4. Ghép các công việc **A → B → C**, trong đó B cần kết quả của A và C cần kết quả của B.
5. Phân biệt chuỗi phụ thuộc với các công việc độc lập có thể dùng **thenCombine** hoặc **allOf**.
6. Hiểu khi nào callback được gọi, khi nào future kết quả hoàn tất và thread/executor nào có thể chạy callback.
7. Dùng **thenComposeAsync** với Executor rõ ràng; tránh giả định mọi callback đều chạy trên thread mới.
8. Xử lý lỗi từ source stage, callback và stage trả về; lựa chọn **exceptionally**, **handle**, **exceptionallyCompose**.
9. Hiểu các giới hạn của timeout, cancellation, null, blocking và resource management.
10. Viết test xác định không cần sleep bằng **completedFuture**, future chưa hoàn tất và **complete/completeExceptionally**.

## 2. CompletableFuture và CompletionStage là gì?

**CompletableFuture<T>** là một future có thể được hoàn tất bình thường bằng một giá trị **T**, hoặc hoàn tất bất thường bằng một exception/cancellation. Nó đồng thời thực thi **CompletionStage<T>**, giao diện cho phép nối các hành động khi một stage hoàn tất.

Trong mô hình CompletionStage:

- Mỗi stage có thể đang chờ, hoàn tất thành công hoặc hoàn tất bất thường.
- Các phương thức **thenApply**, **thenCompose**, **thenCombine**, **handle**... tạo **stage phụ thuộc mới**.
- Một stage được hoàn tất bình thường thì callback bình thường mới có cơ hội chạy.
- Một lỗi hoặc cancellation có thể khiến stage phụ thuộc hoàn tất bất thường.
- **CompletableFuture** chứa cả API chờ kết quả (**join/get**) và API ghép tác vụ; ta nên ưu tiên **ghép stage** trong business workflow thay vì chặn thread giữa các bước.

Hình dung hai tầng:

~~~text
CompletionStage<T>:
  "Sau khi dữ liệu T sẵn sàng, tiếp tục thực hiện việc liên quan"

CompletableFuture<T>:
  CompletionStage<T>
  + Future<T> (join/get/cancel...)
  + khả năng hoàn tất bằng complete/completeExceptionally
~~~

Một API dịch vụ nên cân nhắc **trả CompletionStage<T>** nếu người gọi chỉ cần composition, không cần quyền hoàn tất future từ bên ngoài. Trả **CompletableFuture<T>** vẫn hợp lý khi phần mềm của bạn cần những chức năng cụ thể của CompletableFuture.

**Lưu ý:** CompletionStage là abstraction của chuỗi xử lý, **không bảo đảm bản thân công việc đang chạy bất đồng bộ**; một stage đã hoàn tất và callback nhẹ có thể được thực hiện ngay trên thread hiện tại.

## 3. Chữ ký của thenCompose

Trên **CompletableFuture<T>**:

~~~java
<U> CompletableFuture<U> thenCompose(
        Function<? super T,
                ? extends CompletionStage<U>> fn);
~~~

Đây là **chữ ký rút gọn để học**, không phải đoạn Java độc lập để biên dịch.

Ý nghĩa từng phần:

- **T:** kiểu giá trị của stage hiện tại.
- **Function<? super T, ...>:** callback nhận kết quả T khi stage hiện tại hoàn tất bình thường.
- **CompletionStage<U>:** một stage khác biểu diễn công việc phụ thuộc.
- **U:** kiểu giá trị cuối.
- **CompletableFuture<U>:** stage được trả ra, chỉ hoàn tất bình thường sau khi stage mà callback trả về hoàn tất bình thường.

Đây là điểm quan trọng: callback **không** cần trả ngay một giá trị **U**; nó được phép trả một công việc có thể hoàn thành trong tương lai.

### 3.1. Trình tự hoạt động

~~~text
source: CompletableFuture<T>
           │
           ├── pending
           │      (callback chưa chạy)
           │
           └── completed normally với T
                         │
                         ▼
                   gọi fn(T)
                         │
                         ▼
              CompletionStage<U> inner
                         │
                    ┌────┴────┐
                    │         │
                 pending   completed
                    │         │
                    └────┬────┘
                         ▼
              composed future nhận U

Nếu source lỗi → fn không được gọi → composed future lỗi.
Nếu fn ném lỗi → composed future lỗi.
Nếu inner lỗi → composed future lỗi.
~~~

**thenCompose không "chờ" bằng cách chặn một thread bên trong phép ghép.** Nó đăng ký mối quan hệ hoàn tất. Nhưng callback do bạn truyền vào **vẫn có thể tự viết code chặn**; thenCompose không ngăn điều đó.

### 3.2. Khi stage thứ hai được tạo?

Trong biểu thức:

~~~java
first.thenCompose(value -> fetchSecondAsync(value));
~~~

đoạn **fetchSecondAsync(value)** được gọi **sau khi first hoàn tất bình thường**, vì nó cần giá trị của first.

Nếu code tạo công việc thứ hai **trước** khi nối stage, hai công việc đó có thể đã bắt đầu sớm hơn, và bài toán không còn là dependency thuần. Không chỉ tên phương thức, mà cả **thời điểm gọi hàm** quyết định workflow thực tế.

## 4. thenApply và thenCompose khác nhau ở điểm nào?

Quy tắc dễ nhớ:

- **thenApply:** dùng khi callback **biến đổi một giá trị T thành U**.
- **thenCompose:** dùng khi callback **biến đổi T thành một CompletionStage<U>**, rồi **làm phẳng** về một stage U.

### 4.1. thenApply: chuyển đổi kết quả đồng bộ

~~~java
CompletableFuture<Integer> length =
        CompletableFuture.completedFuture("Java")
                .thenApply(String::length);

// length.join() == 4
~~~

Đây là đoạn minh họa; cần import CompletableFuture. **String::length** trả một số nguyên, không trả future, nên thenApply rất phù hợp.

### 4.2. thenApply tạo tầng lồng nhau nếu callback trả future

Giả sử:

~~~java
CompletableFuture<String> userId =
        CompletableFuture.completedFuture("u42");
~~~

và một phương thức:

~~~java
CompletableFuture<String> emailById(String id);
~~~

Phương thức emailById là **khai báo minh họa**, giả sử nó trả về future sẽ chứa email.

Nếu viết:

~~~java
CompletableFuture<CompletableFuture<String>> nested =
        userId.thenApply(id -> emailById(id));
~~~

Kiểu kết quả là **future của future**:

~~~text
CompletableFuture<
    CompletableFuture<String>
>
~~~

**outer future hoàn tất khi callback trả ra inner future**, không nhất thiết khi inner future đã có email. Người dùng phải xử lý thêm một tầng future, dễ dẫn tới chờ nhầm hoặc truyền sai kiểu vào API.

### 4.3. thenCompose: làm phẳng một tầng

~~~java
CompletableFuture<String> email =
        userId.thenCompose(id -> emailById(id));
~~~

Lúc này kiểu trả về là:

~~~text
CompletableFuture<String>
~~~

**email** hoàn tất bình thường khi future trả về từ **emailById** hoàn tất bình thường. Không còn kiểu lồng nhau.

| Tiêu chí | thenApply | thenCompose |
|---|---|---|
| Callback thường trả | **U** | **CompletionStage<U>** |
| Kiểu future trả về | **CompletableFuture<U>** | **CompletableFuture<U>** (đã flatten) |
| Nếu callback thực sự trả Future<U> | **CompletableFuture<Future<U>>** | Chỉ dùng được nếu đó là **CompletionStage<U>** |
| Dùng cho | Mapping đồng bộ, tính toán, format | Call API/DB bất đồng bộ phụ thuộc kết quả trước |
| Chờ inner stage tự động? | **Không**, inner chỉ là một giá trị | **Có**, composed stage theo dõi inner |
| Tương tự ở nhiều ngôn ngữ | map | flatMap / bind |

**Đừng chọn thenCompose chỉ vì có chữ "async" trong câu chuyện.** Nếu callback chỉ tính một giá trị số hay chuỗi, dùng thenApply. Nếu callback trả một stage, dùng thenCompose.

## 5. Chương trình đầu tiên: so sánh future lồng nhau và future phẳng

Lưu thành **ThenComposeBasicsDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;

public class ThenComposeBasicsDemo {
    static CompletableFuture<String> fetchEmailAsync(String userId) {
        // Giả lập kết quả đã có; trong hệ thống thật có thể
        // trả stage từ HTTP client hoặc database async.
        return CompletableFuture.completedFuture(
                userId + "@example.test");
    }

    public static void main(String[] args) {
        CompletableFuture<String> id =
                CompletableFuture.completedFuture("u42");

        CompletableFuture<CompletableFuture<String>> nested =
                id.thenApply(ThenComposeBasicsDemo::fetchEmailAsync);

        CompletableFuture<String> flat =
                id.thenCompose(ThenComposeBasicsDemo::fetchEmailAsync);

        System.out.println("nested=" + nested.join().join());
        System.out.println("flat=" + flat.join());
    }
}
~~~

Biên dịch và chạy trên Java 17+:

~~~bash
javac -encoding UTF-8 ThenComposeBasicsDemo.java
java ThenComposeBasicsDemo
~~~

**Stdout:**

~~~text
nested=u42@example.test
flat=u42@example.test
~~~

**Giải thích:**

1. **id** có kiểu CompletableFuture<String>.
2. **fetchEmailAsync** trả CompletableFuture<String>.
3. **thenApply** giữ nguyên future trả về như **một giá trị** của outer future.
4. **nested.join().join()** cần hai lớp join trong ví dụ này: outer future rồi inner future.
5. **thenCompose** theo dõi inner stage nên **flat.join()** chỉ cần một lần tại ranh giới chương trình.

Ví dụ dùng **completedFuture** để có kết quả xác định và không lệ thuộc network. Nó minh họa **composition**, không giả vờ rằng call I/O đã thực sự chạy song song. Trong ứng dụng thực, hàm fetchEmailAsync phải là API có cơ chế bất đồng bộ thích hợp.

**Không copy mẫu nested.join().join() vào trong các callback** để thay thế thenCompose. Nếu inner đang chờ thread khác cùng executor, việc join giữa chừng có thể gây nghẽn hoặc deadlock.

## 6. Tại sao gọi là flatten?

Giả sử một thao tác sinh ra công việc khác:

~~~text
fetchUserAsync("u42")
    └── CompletableFuture<User>
          └── user -> fetchOrdersAsync(user.id())
                         └── CompletableFuture<List<Order>>
~~~

Dùng **thenApply** sẽ cho ra:

~~~text
CompletableFuture<CompletableFuture<List<Order>>>
~~~

Dùng **thenCompose**:

~~~text
CompletableFuture<List<Order>>
~~~

Có thể hiểu đây là phép **flatMap** trên ngữ cảnh bất đồng bộ. Kết quả đang nằm trong một "hộp tương lai". Callback trả thêm một "hộp tương lai" khác, và thenCompose **nối hai trạng thái hoàn tất thành một stage kết quả**.

### 6.1. Làm phẳng một nested future đã có

Nếu bạn đã nhận một giá trị lồng:

~~~java
CompletableFuture<CompletableFuture<String>> nested =
        CompletableFuture.completedFuture(
                CompletableFuture.completedFuture("done"));
~~~

Bạn có thể dùng:

~~~java
CompletableFuture<String> flat =
        nested.thenCompose(
                java.util.function.Function.identity());

// flat.join().equals("done") là true.
~~~

Đây là đoạn minh họa cần import CompletableFuture. **Function.identity()** trả lại chính inner stage, và thenCompose làm phẳng đúng một tầng. Nếu có nhiều tầng lồng nhau, bạn phải compose tương ứng hoặc thiết kế lại pipeline để tránh tạo tầng thừa ngay từ đầu.

### 6.2. thenCompose không tạo thêm một tầng lỗi hay kết quả

Composed future cuối cùng có đúng kiểu giá trị U. Khi inner hoàn tất **exceptionally**, composed future cũng hoàn tất bất thường; nó không trả một Future chứa lỗi như một payload bình thường.

Việc flatten là **theo trạng thái completion**, không chỉ là phép ép kiểu. Không thể thay thenCompose bằng một cast từ CompletableFuture<CompletableFuture<T>> sang CompletableFuture<T>.

## 7. Chuỗi công việc phụ thuộc A → B → C

Giả sử quy trình:

1. **loadAccount(id)** trả **CompletableFuture<Account>**.
2. Có Account rồi mới **loadPoints(account)** trả **CompletableFuture<Integer>**.
3. Có points rồi mới **issueCoupon(points)** trả **CompletableFuture<String>**.

Mỗi bước cần kết quả bước trước, vì vậy dùng thenCompose nối thành một chuỗi.

Lưu thành **DependentWorkflowDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;

public class DependentWorkflowDemo {
    record Account(int id, String tier) {}

    static CompletableFuture<Account> loadAccount(int id) {
        return CompletableFuture.completedFuture(
                new Account(id, "GOLD"));
    }

    static CompletableFuture<Integer> loadPoints(Account account) {
        return CompletableFuture.completedFuture(
                account.id() * 10);
    }

    static CompletableFuture<String> issueCoupon(int points) {
        String coupon = points >= 200 ? "VIP" : "STD";
        return CompletableFuture.completedFuture(coupon);
    }

    public static void main(String[] args) {
        CompletableFuture<String> coupon =
                loadAccount(21)
                        .thenCompose(
                                DependentWorkflowDemo::loadPoints)
                        .thenCompose(
                                DependentWorkflowDemo::issueCoupon);

        System.out.println("coupon=" + coupon.join());
    }
}
~~~

~~~bash
javac -encoding UTF-8 DependentWorkflowDemo.java
java DependentWorkflowDemo
~~~

**Stdout:**

~~~text
coupon=VIP
~~~

**Dòng dữ liệu thực tế:**

~~~text
loadAccount(21)                 -> Account(id=21, tier=GOLD)
    thenCompose(loadPoints)     -> 210
    thenCompose(issueCoupon)    -> VIP
    join tại main                -> "VIP"
~~~

**Lưu ý:** Các hàm giả lập trả **completedFuture** để dễ học và có đầu ra cố định. Một API truy vấn database bất đồng bộ thật có thể trả future chưa hoàn tất; logic thenCompose vẫn giữ nguyên.

Với kiểu hàm như **loadAccount** hoặc **issueCoupon**, hãy thiết kế contract rõ ràng: lỗi "không tìm thấy" nên là exceptional completion, một giá trị Optional, hay một result object? thenCompose không tự lựa chọn chính sách nghiệp vụ ấy.

## 8. Chỉ gọi bước phụ thuộc sau khi bước trước hoàn tất

Không nên hiểu thenCompose như việc tất cả các callback đều được chạy ngay khi đăng ký. Nếu source future chưa hoàn tất, mapper phải chờ giá trị của source.

Để chứng minh mà không cần Thread.sleep, ta có thể tạo **CompletableFuture chưa hoàn tất** và tự complete từng bước.

Lưu thành **DependentCompletionDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicBoolean;

public class DependentCompletionDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> source =
                new CompletableFuture<>();

        CompletableFuture<String> inner =
                new CompletableFuture<>();

        AtomicBoolean mapperCalled =
                new AtomicBoolean(false);

        CompletableFuture<String> composed =
                source.thenCompose(id -> {
                    mapperCalled.set(true);
                    return inner;
                });

        System.out.println("before="
                + mapperCalled.get() + ","
                + composed.isDone());

        source.complete(7);

        System.out.println("afterSource="
                + mapperCalled.get() + ","
                + composed.isDone());

        inner.complete("ok-7");

        System.out.println("afterInner="
                + composed.isDone() + ","
                + composed.join());
    }
}
~~~

~~~bash
javac -encoding UTF-8 DependentCompletionDemo.java
java DependentCompletionDemo
~~~

**Stdout:**

~~~text
before=false,false
afterSource=true,false
afterInner=true,ok-7
~~~

**Giải thích:**

- Ban đầu source còn pending nên mapper chưa chạy.
- **source.complete(7)** kích hoạt mapper (ở ví dụ đơn luồng này) và mapper trả về **inner**.
- Dù source đã hoàn tất, **composed vẫn pending** vì inner chưa hoàn tất.
- Khi **inner.complete("ok-7")**, composed hoàn tất với chính giá trị của inner.

Đây là cách kiểm thử **trạng thái và thứ tự phụ thuộc** rất rõ ràng, không phụ thuộc độ trễ thread pool hoặc network.

**Không suy ra từ ví dụ rằng callback của thenCompose luôn chạy trên thread gọi complete.** Đó chỉ là hành vi trong môi trường kiểm thử cụ thể này. Phần sau sẽ giải thích chính sách thread của CompletionStage.

## 9. thenCompose không đồng nghĩa "tạo một tác vụ song song"

Cả ba đoạn dưới đều hợp lệ về mặt cú pháp, nhưng ý nghĩa thực thi khác nhau.

~~~java
// Giả sử source là CompletableFuture<Integer>.
CompletableFuture<Integer> immediate =
        source.thenCompose(
                n -> CompletableFuture.completedFuture(n + 1));
~~~

Callback trả một future đã hoàn tất. Không có việc I/O hoặc thread mới nào bắt buộc xảy ra.

~~~java
CompletableFuture<Integer> asynchronous =
        source.thenCompose(
                n -> CompletableFuture.supplyAsync(() -> n + 1));
~~~

Bước bên trong được **supplyAsync** đưa vào executor mặc định (trên CompletableFuture tiêu chuẩn thường là ForkJoinPool.commonPool), nên có scheduling thực. Nhưng bạn phải cân nhắc nguồn tải, loại tác vụ và chính sách executor.

~~~java
CompletableFuture<Integer> transformed =
        source.thenApply(n -> n + 1);
~~~

Nếu chỉ cộng một số, **thenApply** đơn giản hơn và tránh tạo một future mới không cần thiết bên trong callback.

**thenCompose là phép ghép**, còn "chạy thực sự bất đồng bộ bằng executor nào" là vấn đề của **API sinh ra stage** và biến thể Async mà bạn dùng.

## 10. thenCompose, thenComposeAsync và Executor

Ba overload chính:

~~~java
source.thenCompose(fn);

source.thenComposeAsync(fn);

source.thenComposeAsync(fn, executor);
~~~

Đây là đoạn minh họa, trong đó **source**, **fn** và **executor** đã được khai báo đúng kiểu.

| API | Mapper được thực hiện ở đâu? | Khi nào nên dùng? |
|---|---|---|
| **thenCompose(fn)** | Có thể trên thread hoàn tất source hoặc thread gọi completion theo hợp đồng | Mapper nhẹ, chỉ chọn và trả stage tiếp theo |
| **thenComposeAsync(fn)** | Thông qua default async execution facility của source | Khi cần chạy mapper qua cơ chế async mặc định |
| **thenComposeAsync(fn, executor)** | Thông qua Executor chỉ định | Khi cần kiểm soát tài nguyên, tách tải/luồng |
| **supplyAsync(supplier, executor)** | Chạy supplier trong executor | Tạo một stage cho việc có kết quả bằng supplier |

**Quan trọng về thenCompose không Async:** Callback có thể chạy **ngay trong thread đang hoàn tất source**, hoặc thread khác có quyền gọi completion method. Không nên dựa vào tên thread cụ thể hay giả định nó luôn là main thread.

**Quan trọng về thenComposeAsync:** Nó quyết định cách thực thi **mapper**. Mapper vẫn phải **trả về một CompletionStage**. Nó không tự biến một hàm I/O đồng bộ lâu thành một API phi chặn; nếu mapper gọi một HTTP client blocking, thread chạy mapper vẫn bị chặn.

### 10.1. Về ForkJoinPool.commonPool

Trên CompletableFuture tiêu chuẩn, các phương thức Async không nhận Executor thường dùng **ForkJoinPool.commonPool()** (hoặc cơ chế fallback được mô tả trong API khi common pool không đủ parallelism). Các subclass có thể override defaultExecutor, nên câu trả lời chính xác phải xét implementation.

**Không nên vô tình đưa nhiều I/O blocking lâu vào common pool** trong server. Dùng một Executor phù hợp hoặc API I/O phi chặn khi cần. Thread pool có giới hạn, nên khi quá nhiều tác vụ đồng thời, cần kiểm soát hàng đợi và khả năng từ chối công việc.

### 10.2. Khi nào nên dùng thenComposeAsync?

Nếu mapper thực sự chỉ thực hiện:

~~~java
id -> asyncClient.fetch(id)
~~~

thì thường **thenCompose** đủ, vì mapper nhanh chóng trả một stage và API client làm phần nặng bất đồng bộ ở nơi khác.

Nếu mapper có tính toán đắt, yêu cầu tách thread/context, hoặc cần chính sách thực thi cụ thể, hãy cân nhắc **thenComposeAsync(..., executor)**. Nhưng cũng có thể tách phần tính toán đồng bộ bằng **thenApplyAsync(...)** rồi compose tiếp stage I/O.

### 10.3. Executor truyền vào không tự được quản lý vòng đời

Nếu tự tạo ExecutorService, bạn chịu trách nhiệm **shutdown** đúng lúc. Trong ứng dụng thật, nhiều service dùng chung executor được quản lý bởi application lifecycle; không tự tạo pool mới cho mỗi request.

## 11. Ví dụ thực sự dùng ExecutorService

Lưu thành **ThenComposeExecutorDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ThenComposeExecutorDemo {
    public static void main(String[] args) {
        ExecutorService executor =
                Executors.newFixedThreadPool(2);

        try {
            CompletableFuture<Integer> first =
                    CompletableFuture.supplyAsync(
                            () -> 21,
                            executor);

            CompletableFuture<String> result =
                    first.thenComposeAsync(
                            n -> CompletableFuture.supplyAsync(
                                    () -> "ID-" + (n * 2),
                                    executor),
                            executor);

            System.out.println("result=" + result.join());
        } finally {
            executor.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ThenComposeExecutorDemo.java
java ThenComposeExecutorDemo
~~~

**Stdout:**

~~~text
result=ID-42
~~~

**Giải thích:**

1. **first** được tạo bằng supplyAsync trên executor có hai worker threads.
2. **thenComposeAsync** lên lịch mapper qua executor đã chỉ định.
3. Mapper tạo thêm CompletableFuture qua **supplyAsync** và trả stage này.
4. thenCompose gộp hai bước: future cuối chỉ có kiểu **String**, không phải future lồng.
5. **join() chỉ nằm ở main**, là ranh giới chờ kết quả của toàn ví dụ.
6. **shutdown()** được gọi trong finally để không để ExecutorService tồn tại vô hạn.

**Không in thread name hoặc thứ tự log của các worker làm stdout dự đoán được**: scheduling giữa threads có thể thay đổi. Chỉ kiểm tra **giá trị kết quả** là ổn định.

**Ví dụ này dùng pool 2 để minh họa, không phải hướng dẫn kích cỡ pool cho production.** Với I/O, CPU, workload và SLA khác nhau, kiến trúc executor cũng khác nhau.

## 12. thenCompose so với thenCombine: phụ thuộc và độc lập

Một nguyên tắc về luồng dữ liệu:

- Nếu **B cần kết quả của A** mới biết phải làm gì, dùng **thenCompose**.
- Nếu **A và B độc lập**, có thể **khởi động cả hai**, rồi kết hợp kết quả bằng **thenCombine**.
- Nếu cần gom một tập công việc độc lập, có thể dùng **allOf** hoặc một collector phù hợp.

### 12.1. Hai công việc phụ thuộc

~~~text
loadUser(userId)
        │ User
        ▼
loadOrders(user.id())
        │ Orders
        ▼
buildSummary(orders)
~~~

Có thể viết:

~~~java
CompletableFuture<Summary> summary =
        loadUser(userId)
                .thenCompose(user -> loadOrders(user.id()))
                .thenApply(orders -> buildSummary(orders));
~~~

Đây là **đoạn minh họa**, giả định các kiểu User, Summary và các phương thức được định nghĩa. **loadOrders** phụ thuộc user.id nên không thể bắt đầu đúng tham số trước khi có User.

### 12.2. Hai công việc độc lập

Nếu **loadProduct(sku)** và **loadStock(sku)** đều chỉ cần SKU sẵn có, có thể khởi động cả hai trước:

~~~java
CompletableFuture<Product> productFuture =
        loadProduct(sku);

CompletableFuture<Stock> stockFuture =
        loadStock(sku);
~~~

Rồi:

~~~java
CompletableFuture<Quote> quoteFuture =
        productFuture.thenCombine(
                stockFuture,
                (product, stock) -> buildQuote(product, stock));
~~~

**thenCombine** hoàn tất thành công sau khi **cả hai stage đầu vào** hoàn tất bình thường và callback kết hợp trả Quote.

Nếu sau đó **reserveAsync(quote)** phụ thuộc Quote, tiếp tục bằng **thenCompose**:

~~~java
CompletableFuture<Reservation> reservation =
        quoteFuture.thenCompose(this::reserveAsync);
~~~

Đây là các đoạn minh họa, không phải class chạy độc lập.

**Đừng dùng một chuỗi thenCompose để ép hai tác vụ thực sự độc lập chạy tuần tự** nếu mục tiêu là tận dụng concurrency. Nhưng cũng không khởi động song song những thao tác thật sự phụ thuộc nhau hoặc yêu cầu thứ tự giao dịch nghiêm ngặt.

## 13. Ví dụ đầy đủ: độc lập trước, phụ thuộc sau

Lưu thành **CombineAndComposeDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;

public class CombineAndComposeDemo {
    record Product(String sku, int unitPrice) {}
    record Stock(int available) {}
    record Quote(String sku, int unitPrice, int available) {}

    static CompletableFuture<Product> loadProduct(String sku) {
        return CompletableFuture.completedFuture(
                new Product(sku, 120));
    }

    static CompletableFuture<Stock> loadStock(String sku) {
        return CompletableFuture.completedFuture(
                new Stock(3));
    }

    static CompletableFuture<String> reserve(Quote quote) {
        return CompletableFuture.completedFuture(
                quote.sku() + ":" + quote.available()
                        + ":" + quote.unitPrice());
    }

    public static void main(String[] args) {
        CompletableFuture<Product> product =
                loadProduct("B-17");

        CompletableFuture<Stock> stock =
                loadStock("B-17");

        CompletableFuture<String> reservation =
                product.thenCombine(
                        stock,
                        (p, s) -> new Quote(
                                p.sku(),
                                p.unitPrice(),
                                s.available()))
                        .thenCompose(
                                CombineAndComposeDemo::reserve);

        System.out.println("reservation=" + reservation.join());
    }
}
~~~

~~~bash
javac -encoding UTF-8 CombineAndComposeDemo.java
java CombineAndComposeDemo
~~~

**Stdout:**

~~~text
reservation=B-17:3:120
~~~

**Giải thích:**

- **product** và **stock** không phụ thuộc nhau; trong hệ thống thật các call async có thể chạy đồng thời.
- **thenCombine** hợp nhất hai giá trị thành Quote.
- **reserve** phụ thuộc Quote nên dùng **thenCompose**.
- Future kết quả chỉ mang **String** đại diện cho Reservation trong ví dụ giả lập.
- Mọi fake client trong demo trả completedFuture để minh họa data flow xác định; không nên từ đó suy ra đang có concurrency thật.

### 13.1. Khi thứ hai cần dữ liệu từ thứ nhất

Nếu loadStock yêu cầu một thuộc tính chỉ có sau loadProduct, hãy viết:

~~~java
CompletableFuture<Quote> quote =
        loadProduct(sku).thenCompose(product ->
                loadStock(product.sku()).thenApply(stock ->
                        new Quote(
                                product.sku(),
                                product.unitPrice(),
                                stock.available())));
~~~

Đây là **đoạn minh họa** trong phạm vi class có record Product, Stock, Quote và phương thức tương ứng. **thenApply** bên trong phù hợp vì dựng Quote là tính toán đồng bộ; **thenCompose** bên ngoài phù hợp vì loadStock trả CompletableFuture.

**Đây là mẫu kết hợp rất thường gặp:** một bước async trả future, và bên trong dùng thenApply để chuyển kết quả của future ấy thành giá trị cuối.

## 14. allOf không thay thenCompose

**CompletableFuture.allOf(...)** chờ một tập future hoàn tất và trả **CompletableFuture<Void>**. Nó không tự trả List kết quả.

Ví dụ khi đã tạo ba future độc lập:

~~~java
CompletableFuture<String> a =
        CompletableFuture.completedFuture("A");

CompletableFuture<String> b =
        CompletableFuture.completedFuture("B");

CompletableFuture<String> c =
        CompletableFuture.completedFuture("C");

CompletableFuture<String> combined =
        CompletableFuture.allOf(a, b, c)
                .thenApply(ignored ->
                        a.join() + b.join() + c.join());

// combined.join() == "ABC"
~~~

Đây là đoạn minh họa, cần import CompletableFuture.

Ở đây **join() bên trong thenApply** chỉ đọc các future đã được **allOf** xác nhận hoàn tất bình thường. Nó **không chờ một công việc chưa hoàn tất** trên đường thành công. Tuy nhiên, nếu bất kỳ future thành phần nào lỗi, **allOf sẽ hoàn tất bất thường** và thenApply không chạy; cần thêm error handling nếu nghiệp vụ yêu cầu partial success.

Nếu mỗi bước **phụ thuộc kết quả của bước trước**, allOf không thay thế thenCompose. Nó phù hợp khi tập công việc đã biết và có thể hoàn tất độc lập.

### 14.1. Không tự đồng nhất thenCombine với thenCompose

**thenCombine** nhận **hai stage có sẵn**, callback nhận **hai giá trị**. **thenCompose** nhận **một stage và một callback sinh ra stage kế tiếp từ giá trị đầu tiên**.

Việc dùng sai phương thức có thể gây serialization không cần thiết, race condition hoặc làm API trả nested future khó xử lý.

## 15. Lỗi truyền qua chuỗi thenCompose như thế nào?

Có ba điểm phát sinh lỗi cơ bản:

1. **Source future** hoàn tất bất thường → callback thenCompose **không chạy**, future cuối lỗi.
2. **Callback** ném exception khi được gọi → future cuối hoàn tất bất thường.
3. **Inner CompletionStage** mà callback trả ra hoàn tất bất thường → future cuối cũng hoàn tất bất thường.

~~~text
source fails ─────────────────────────────► composed fails
source ok ──► mapper throws ──────────────► composed fails
source ok ──► mapper returns inner ──fails► composed fails
source ok ──► mapper returns inner ──ok───► composed succeeds
~~~

**thenCompose không tự retry, không nuốt exception và không biến lỗi thành giá trị mặc định**. Hãy xử lý lỗi bằng stage chuyên dụng và xác định rõ chính sách nghiệp vụ.

### 15.1. Phân biệt join và get

- **join()** có thể chặn cho tới khi stage hoàn tất; khi lỗi thường ném **CompletionException** không checked, chứa nguyên nhân.
- **get()** có thể chặn và thường ném **ExecutionException** checked khi tác vụ thất bại; còn có InterruptedException khi đang chờ.
- Với cancellation, có thể gặp **CancellationException** tùy cách stage được hủy.
- Exception có thể có các lớp wrapper. Khi log/định tuyến chính sách, cần xem cause thay vì giả định Throwable đầu tiên luôn chính là lỗi nghiệp vụ.

**Không gọi get/join giữa các bước trong pipeline** chỉ để lấy T rồi khởi động B; dùng thenCompose để đăng ký B mà không chặn.

## 16. Ví dụ đầy đủ: lỗi source, lỗi inner và recovery

Lưu thành **ThenComposeFailureDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.atomic.AtomicBoolean;

public class ThenComposeFailureDemo {
    public static void main(String[] args) {
        AtomicBoolean mapperCalled = new AtomicBoolean(false);

        CompletableFuture<String> sourceFailed =
                CompletableFuture.failedFuture(
                        new IllegalStateException("not-found"));

        CompletableFuture<String> chained =
                sourceFailed.thenCompose(value -> {
                    mapperCalled.set(true);
                    return CompletableFuture.completedFuture(
                            value + "!");
                });

        System.out.println("mapperCalled=" + mapperCalled.get());

        try {
            chained.join();
        } catch (CompletionException ex) {
            System.out.println("sourceCause="
                    + ex.getCause().getClass().getSimpleName()
                    + ":" + ex.getCause().getMessage());
        }

        CompletableFuture<String> innerFailed =
                CompletableFuture.completedFuture("ok")
                        .thenCompose(value ->
                                CompletableFuture.failedFuture(
                                        new IllegalArgumentException(
                                                "inner")));

        try {
            innerFailed.join();
        } catch (CompletionException ex) {
            System.out.println("innerCause="
                    + ex.getCause().getClass().getSimpleName()
                    + ":" + ex.getCause().getMessage());
        }

        CompletableFuture<String> recovered =
                sourceFailed.exceptionallyCompose(ex ->
                        CompletableFuture.completedFuture(
                                "fallback"));

        System.out.println("recovery=" + recovered.join());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ThenComposeFailureDemo.java
java ThenComposeFailureDemo
~~~

**Stdout:**

~~~text
mapperCalled=false
sourceCause=IllegalStateException:not-found
innerCause=IllegalArgumentException:inner
recovery=fallback
~~~

**Giải thích:**

- **sourceFailed** hoàn tất bất thường ngay từ đầu, nên callback bình thường **không chạy**.
- **innerFailed** biểu diễn lỗi từ bước phụ thuộc thứ hai và lỗi được đưa ra qua composed future.
- **exceptionallyCompose** cung cấp một **stage khôi phục** khi upstream lỗi.
- **failedFuture(...) được thêm từ Java 9**, **exceptionallyCompose(...) từ Java 12**. Chương trình dùng Java 17+ nên cả hai còn được hỗ trợ hiện nay.
- Nếu buộc tương thích mã nguồn Java 8, có thể tạo future chưa hoàn tất rồi **completeExceptionally**; và có thể tự viết recovery thông qua **handle(...).thenCompose(...)** khi không có exceptionallyCompose.

### 16.1. Nếu mapper tự ném lỗi?

~~~java
CompletableFuture<String> failed =
        CompletableFuture.completedFuture("u42")
                .thenCompose(id -> {
                    throw new IllegalArgumentException("invalid");
                });
~~~

Đây là đoạn minh họa. Composed future hoàn tất bất thường với lỗi từ mapper. **Không cần try/catch quanh thenCompose để bắt lỗi xảy ra sau này trong callback**; nên gắn stage xử lý lỗi hoặc đón lỗi tại ranh giới join/get.

### 16.2. Nếu inner hoàn tất chậm rồi lỗi?

Composed future chưa hoàn tất trong lúc inner pending. Khi inner được hoàn tất bằng **completeExceptionally**, composed future cũng hoàn tất bất thường. Logic phụ thuộc trong thenCompose không tự làm nhiệm vụ retry hoặc timeout.

## 17. exceptionally, handle, whenComplete và exceptionallyCompose

Những phương thức này có mục đích khác nhau:

| API | Khi nào chạy? | Kết quả thông thường | Dùng cho |
|---|---|---|---|
| **exceptionally(fn)** | Khi stage hoàn tất bất thường | Một giá trị **T** phục hồi | Fallback đồng bộ |
| **handle(fn)** | Khi stage hoàn tất bình thường hoặc bất thường | Giá trị **U** do handler trả | Biến đổi cả success/failure |
| **whenComplete(action)** | Khi stage kết thúc thành công hoặc lỗi | Theo dõi kết quả, không chủ yếu để đổi outcome | Logging/metrics |
| **exceptionallyCompose(fn)** | Khi stage lỗi | **CompletionStage<T>** phục hồi | Fallback **bất đồng bộ** |
| **thenCompose(fn)** | Khi stage thành công | **CompletionStage<U>** tiếp theo | Bước async phụ thuộc |

### 17.1. Fallback đồng bộ

~~~java
CompletableFuture<String> result =
        loadAsync(id)
                .exceptionally(error -> "not-available");
~~~

Đây là đoạn minh họa, giả định loadAsync trả CompletableFuture<String>. **exceptionally** trả giá trị String bình thường, không cần thêm một future.

### 17.2. Fallback bất đồng bộ

~~~java
CompletableFuture<String> result =
        primaryClient(id)
                .exceptionallyCompose(error ->
                        backupClient(id));
~~~

Đây là đoạn minh họa; các client trả CompletionStage<String> hoặc CompletableFuture<String>. Khi primary lỗi, backup mới được gọi và future kết quả theo dõi completion của backup.

**exceptionallyCompose là sự đối xứng có chủ ý với thenCompose cho nhánh lỗi**, phù hợp trên Java 12+. Không ép một future fallback vào **exceptionally** rồi sử dụng join bên trong handler để chờ.

### 17.3. handle và việc quan sát lỗi

~~~java
CompletableFuture<String> safe =
        source.handle((value, error) ->
                error == null ? value : "default");
~~~

Đây là đoạn minh họa, giả sử source mang String. Handler chạy cho cả success/failure và có thể thay đổi outcome. Nếu chỉ ghi log, dùng **whenComplete**, tránh vô tình nuốt lỗi bằng cách trả một giá trị mặc định ở mọi nơi.

### 17.4. Đặt recovery ở đâu trong pipeline?

~~~java
loadUserAsync(id)
        .thenCompose(this::loadOrdersAsync)
        .thenCompose(this::chargeAsync)
        .exceptionally(this::mapError);
~~~

Đây là đoạn minh họa trong một class có các phương thức đúng kiểu. Recovery cuối chuỗi xử lý lỗi từ **bất kỳ giai đoạn nào** ở trước nó. Nếu chính sách cần xử lý riêng lỗi loadUser mà không được che lỗi charge, hãy đặt handler ở đoạn tương ứng.

**Không viết exceptionally cuối pipeline trả "thành công" trong mọi trường hợp** nếu các thao tác như thanh toán hay đặt hàng có hậu quả ngoài hệ thống. Fallback phải giữ đúng semantics nghiệp vụ.

## 18. Timeout không tự hủy công việc nguồn

Từ **Java 9**, CompletableFuture có:

~~~java
future.orTimeout(2, TimeUnit.SECONDS);
future.completeOnTimeout(fallbackValue, 2, TimeUnit.SECONDS);
~~~

Đây là đoạn minh họa, cần import TimeUnit và biến future phù hợp.

- **orTimeout** hoàn tất **chính CompletableFuture nhận lời gọi** bằng TimeoutException nếu chưa hoàn tất trong hạn.
- **completeOnTimeout** hoàn tất **chính CompletableFuture nhận lời gọi** bằng giá trị fallback nếu quá hạn.
- Các phương thức này **trả về chính đối tượng future** đã nhận lời gọi, không phải một stage timeout tách biệt.
- Chúng không đảm bảo **dừng I/O thực tế** hoặc hủy công việc bên ngoài; cần thiết kế timeout/cancellation ở cả HTTP client, DB client hoặc API tương ứng.

### 18.1. Bọc timeout ở đúng ranh giới

~~~java
CompletableFuture<Result> composed =
        fetchUserAsync(userId)
                .thenCompose(this::fetchResultAsync);

CompletableFuture<Result> limited =
        composed.orTimeout(2, TimeUnit.SECONDS);
~~~

Đây là đoạn minh họa trong class có Result và các phương thức tương ứng.

**Cẩn thận:** Vì **orTimeout** thao tác trên cùng đối tượng composed, nếu future ấy được dùng chia sẻ với nhiều caller, đặt timeout vào nó có thể ảnh hưởng mọi người đang quan sát future đó.

Trên Java 9+, **copy()** có thể tạo dependent future riêng rồi gắn timeout nếu muốn giữ future gốc không bị hoàn tất do timeout:

~~~java
CompletableFuture<Result> localView =
        composed.copy().orTimeout(2, TimeUnit.SECONDS);
~~~

Đây là đoạn minh họa. **copy không hủy công việc nguồn**; nó chỉ tạo đường quan sát riêng. Tùy hệ thống, chính sách timeout và cancellation có thể cần được quản lý ở tầng cao hơn.

### 18.2. Timeout không phải retry

Nếu một hệ thống gọi API chậm và timeout, **gọi lại** có thể tạo tác dụng phụ (đặt đơn, trừ tiền) lần thứ hai. thenCompose và orTimeout không tự làm retry an toàn. Với thao tác có side effect, cần idempotency key hoặc hợp đồng nghiệp vụ phù hợp.

**Không giả định TimeoutException đồng nghĩa server chưa xử lý yêu cầu**; nó chỉ nói client chưa nhận được kết quả trong khoảng đã quy định.

## 19. Cancellation và thenCompose

**CompletableFuture.cancel(...)** làm future hoàn tất bất thường theo dạng cancellation. Trong CompletableFuture, tham số **mayInterruptIfRunning** không có hiệu lực để đảm bảo interrupt computation đang chạy; đây là khác biệt quan trọng so với một số implementation Future khác.

Khi hủy future kết quả của thenCompose:

- Không có hợp đồng tổng quát rằng tất cả upstream và inner future sẽ được hủy theo chiều ngược.
- Công việc I/O bên dưới có thể vẫn chạy nếu API không có cơ chế hủy riêng.
- Hủy future nguồn có thể làm dependent stages hoàn tất bất thường; nhưng đó không phải bằng chứng đã dừng hoàn toàn công việc bên ngoài.
- Khi cancellation là yêu cầu quan trọng, cần chính sách lan truyền hủy/tài nguyên ở tầng service/client.

### 19.1. Ví dụ xác định: hủy composed future không hủy inner

Lưu thành **ThenComposeCancellationDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;

public class ThenComposeCancellationDemo {
    public static void main(String[] args) {
        CompletableFuture<String> source =
                new CompletableFuture<>();

        CompletableFuture<String> inner =
                new CompletableFuture<>();

        CompletableFuture<String> composed =
                source.thenCompose(value -> inner);

        source.complete("ok");
        composed.cancel(false);

        System.out.println("composedCancelled="
                + composed.isCancelled());

        System.out.println("sourceCancelled="
                + source.isCancelled());

        System.out.println("innerCancelled="
                + inner.isCancelled());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ThenComposeCancellationDemo.java
java ThenComposeCancellationDemo
~~~

**Stdout với CompletableFuture chuẩn:**

~~~text
composedCancelled=true
sourceCancelled=false
innerCancelled=false
~~~

**Bài học:** Hủy future đại diện cho kết quả hợp thành **không tự lan hủy tới những future đã được tạo**. Với client có request thực tế, hãy thiết kế cơ chế hủy/abort rõ ràng khi có nhu cầu.

**Không dùng kết quả này để suy rộng rằng cancellation ở mọi chiều và mọi CompletionStage implementation có hành vi giống nhau.** Nên dựa trên hợp đồng của implementation đang dùng, đặc biệt nếu tích hợp framework bên thứ ba.

## 20. null: giá trị null khác với stage null

Một **CompletableFuture<String>** có thể hoàn tất bình thường với **giá trị null** nếu contract cho phép:

~~~java
CompletableFuture<String> valid =
        CompletableFuture.completedFuture("ok")
                .thenCompose(value ->
                        CompletableFuture.completedFuture(null));

// valid.join() == null
~~~

Đây là đoạn minh họa. Giá trị **null payload** đôi khi được phép trong CompletableFuture, nhưng nhiều API nghiệp vụ nên dùng **Optional**, một result type rõ ràng, hoặc lỗi cụ thể để tránh mơ hồ.

Ngược lại, **mapper của thenCompose phải trả một CompletionStage**, không được trả **null stage**:

~~~java
CompletableFuture<String> invalid =
        CompletableFuture.completedFuture("ok")
                .thenCompose(value -> null);
~~~

Đoạn minh họa trên tạo stage hoàn tất bất thường với **NullPointerException** khi callback trả null. Đây không phải cách biểu diễn "không có kết quả".

**Nếu không tìm thấy dữ liệu:** Chọn một contract hợp lý như **CompletionStage<Optional<User>>**, **CompletionStage<Result<User>>** hoặc exceptional completion. Không dùng **null stage** như tín hiệu absence.

## 21. Không chặn luồng trong thenCompose

Một anti-pattern:

~~~java
// Đoạn minh họa KHÔNG NÊN DÙNG:
CompletableFuture<String> result =
        fetchUserAsync(id)
                .thenApply(user ->
                        fetchOrdersAsync(user.id()).join()
                                .toString());
~~~

Vấn đề:

- **join() có thể chặn thread** đang chạy callback.
- Nếu thread đó cần xử lý việc hoàn tất inner future, nguy cơ **thread starvation/deadlock**.
- Pipeline trở nên khó thay đổi và khó xử lý timeout/cancellation.
- Người đọc có thể tưởng thenApply là một phép biến đổi nhẹ, trong khi nó đang chờ I/O.

**Thay bằng:**

~~~java
CompletableFuture<String> result =
        fetchUserAsync(id)
                .thenCompose(user ->
                        fetchOrdersAsync(user.id()))
                .thenApply(Object::toString);
~~~

Đây là đoạn minh họa với API trả đúng kiểu. **thenCompose** liên kết hai stage mà không cần chặn chờ inner trong callback.

### 21.1. Có bao giờ join được phép dùng?

**Có**, nhưng đặt tại ranh giới thích hợp:

- Trong **main** của ví dụ CLI để chờ kết quả trước khi kết thúc.
- Trong một adapter đồng bộ mà contract cho phép chặn, có timeout/cancellation phù hợp.
- Sau **allOf** khi đã biết các future đã hoàn tất bình thường, có thể dùng join để lấy payload hoàn tất; không tạo thêm chờ đợi ở đường thành công.
- Trong unit test để xác nhận giá trị của stage đã hoàn tất.

Không dùng **join/get giữa các bước phụ thuộc** như cơ chế composition chính.

### 21.2. Async không phải phi chặn một cách tự động

Hàm **CompletableFuture.supplyAsync(() -> blockingHttpCall(), executor)** giúp chuyển việc chặn sang executor, nhưng **blockingHttpCall** vẫn chặn **một thread**. Nó không biến I/O thành I/O phi chặn. Khi tải lớn, chọn HTTP client/DB driver và mô hình executor phù hợp để tránh cạn thread.

## 22. Không lẫn lộn đồng thời và phụ thuộc

Xem hai workflow:

~~~text
Workflow A: tuần tự phụ thuộc

userFuture
   └─ thenCompose(user -> loadOrders(user.id()))
         └─ thenCompose(orders -> charge(orders))

loadOrders phải biết user; charge phải biết orders.

Workflow B: độc lập rồi hợp nhất

productFuture ──┐
                ├─ thenCombine(...) ── thenCompose(reserveAsync)
stockFuture ────┘

Product và stock có thể được khởi động độc lập.
Reserve phải đợi Quote đã hợp nhất.
~~~

**thenCompose không hứa chạy nhanh hơn một chuỗi đồng bộ**; lợi ích chính là **không cần chặn để lấy kết quả trung gian** và cho phép hoàn tất theo sự kiện. Hiệu năng phụ thuộc I/O client, executor, số lượng công việc, chính sách retry, tắc nghẽn downstream và thời gian xử lý.

Nếu hai bước có quan hệ phụ thuộc thật, cố gắng chạy song song sai thứ tự còn nguy hiểm hơn chậm. Tối ưu concurrency phải bảo toàn đúng luồng dữ liệu.

## 23. Lưu ý về backpressure và tải hệ thống

Có một đoạn chain không chặn không có nghĩa hệ thống có thể nhận vô hạn tác vụ. Mỗi lượt gọi có thể tạo future, callback, request hoặc một công việc trên executor.

Các rủi ro:

1. **Tạo quá nhiều future** cùng lúc → tốn bộ nhớ.
2. **Executor queue không giới hạn** → backlog và độ trễ tăng.
3. **I/O downstream không có giới hạn đồng thời** → quá tải DB/API.
4. **Timeout chỉ ở future** mà không abort request → công việc thực tế vẫn chiếm tài nguyên.
5. **Retry không giới hạn** → khuếch đại lỗi.
6. **Tác vụ quá dài nằm trong callback non-async** → thread hoàn tất source bị giữ lâu.

Những biện pháp phù hợp tùy hệ thống:

- Dùng **bounded executor**, bulkhead, semaphore hoặc giới hạn concurrent requests.
- Dùng async client hỗ trợ timeout và cancellation thực sự.
- Dùng metrics cho queue depth, latency, error rate.
- Dùng deadline thống nhất và idempotency khi retry.
- Tạo **fan-out có giới hạn**, không gửi hàng triệu request cùng lúc chỉ vì thenCombine/allOf dễ viết.

**thenCompose không tự cung cấp backpressure.** Đây là trách nhiệm của tầng điều phối workload.

## 24. Đừng làm mất ngữ cảnh request, log và transaction

Vì callback có thể chạy trên thread khác, những thứ gắn với **ThreadLocal**, transaction context, security context hay logging MDC **không mặc nhiên được truyền qua mọi CompletableFuture stage**.

Ví dụ:

~~~java
source.thenCompose(value ->
        asyncClient.fetch(value));
~~~

Callback ở thread nào phụ thuộc cách stage hoàn tất và biến thể Async. Không nên giả định thông tin **requestId**, security principal hay transaction vốn nằm trong ThreadLocal ở thread tạo future vẫn có mặt khi callback chạy.

Giải pháp thường là:

- **Truyền explicit context** hoặc DTO có các trường cần thiết.
- Sử dụng cơ chế context propagation được framework hỗ trợ và kiểm thử nó.
- Giữ transaction boundary phù hợp với công việc bất đồng bộ; không trông chờ giao dịch database theo thread tồn tại qua mọi stage.

**Đừng dựa vào thứ tự ghi log của các task chạy song song** để kết luận thứ tự thời gian. Nên gắn correlation ID và log sự kiện có cấu trúc.

## 25. Thiết kế API trả về CompletionStage

Một service bất đồng bộ có thể khai báo:

~~~java
interface UserClient {
    CompletionStage<User> findById(String id);
}

interface OrderClient {
    CompletionStage<Orders> findByUserId(String userId);
}
~~~

Đây là **đoạn minh họa chữ ký**, cần định nghĩa kiểu User, Orders và import CompletionStage.

Sau đó một service khác có thể viết:

~~~java
CompletionStage<Orders> orders =
        userClient.findById(id)
                .thenCompose(user ->
                        orderClient.findByUserId(user.id()));
~~~

Chữ ký của **CompletionStage.thenCompose** cho phép mapper trả **CompletionStage<U>**, không yêu cầu mọi thư viện phải cung cấp đúng kiểu concrete CompletableFuture<U>.

**Lợi ích:** Bên gọi có thể tiếp tục compose mà không phụ thuộc trực tiếp vào cách client hoàn tất future. Nhưng đối tượng trả về vẫn có thể là implementation tùy ý; không suy rằng mọi stage là CompletableFuture hoặc mọi method có phương thức đặc thù của CompletableFuture.

### 25.1. Tránh trả future mà người ngoài có thể tự complete nếu không cần

Khi API chỉ cung cấp phép composition, **CompletionStage** là kiểu trả về phù hợp. Với CompletableFuture, có các API như **copy()** và **minimalCompletionStage()** (được bổ sung ở Java 9+) cho những tình huống muốn hạn chế cách caller can thiệp vào completion.

Không có nhu cầu đặc biệt thì giữ abstraction đơn giản và rõ ràng thay vì thêm adapter không cần thiết.

## 26. Ghép nhiều bước với dữ liệu gốc cần giữ lại

Một lỗi logic phổ biến: sau thenCompose, giá trị của stage mới chỉ là kết quả của B, nên nếu C còn cần dữ liệu của A, phải **giữ A trong lambda**, dùng record hoặc tạo một context object.

Ví dụ:

~~~java
CompletionStage<Receipt> receipt =
        findUserAsync(userId)
                .thenCompose(user ->
                        findCartAsync(user.id())
                                .thenCompose(cart ->
                                        chargeAsync(user, cart)));
~~~

Đây là đoạn minh họa. Trong lambda bên trong, **user** vẫn thuộc scope và được dùng cùng **cart**. Nếu phải truyền quá nhiều biến, có thể gom chúng vào một record immutable:

~~~java
record CheckoutContext(User user, Cart cart) {}
~~~

Với Java 17+, record giúp mô tả các dữ liệu trung gian rõ ràng. Không nên lạm dụng nested lambdas đến mức khó đọc; có thể tách **method reference** và phương thức nhỏ có kiểu trả về CompletionStage rõ ràng.

### 26.1. Khi nào phương thức tham chiếu đẹp hơn lambda?

Nếu **loadPoints(Account)** trả CompletableFuture<Integer>:

~~~java
loadAccount(21)
        .thenCompose(AccountService::loadPoints);
~~~

Đây là đoạn minh họa, giả sử phương thức static có đúng chữ ký. Nếu callback cần thêm biến như requestId, headers hoặc business rules, lambda có thể dễ đọc hơn:

~~~java
loadAccount(21)
        .thenCompose(account ->
                loadPointsWithContext(account, requestId));
~~~

**Không cố dùng method reference khi làm mất ý nghĩa hoặc khó thấy dependencies**.

## 27. Các anti-pattern phổ biến

### 27.1. Anti-pattern: thenApply cho một future

~~~java
CompletableFuture<CompletableFuture<Orders>> nested =
        userFuture.thenApply(user ->
                fetchOrdersAsync(user.id()));
~~~

Nếu caller chỉ cần Orders, dùng **thenCompose**.

### 27.2. Anti-pattern: join trong mapper

~~~java
userFuture.thenApply(user ->
        fetchOrdersAsync(user.id()).join());
~~~

Chặn thread, tăng nguy cơ nghẽn và giảm lợi ích của composition.

### 27.3. Anti-pattern: trả null stage

~~~java
userFuture.thenCompose(user -> null);
~~~

Mapper phải trả một CompletionStage. Nếu không có dữ liệu, dùng contract rõ ràng như Optional hoặc exceptional completion.

### 27.4. Anti-pattern: quên return stage mới

~~~java
userFuture.thenCompose(user ->
        fetchOrdersAsync(user.id()));
// Nếu bỏ qua stage trả về, caller không thể theo dõi pipeline.
~~~

**thenCompose không mutate userFuture** thành "future chứa orders". Nó tạo stage mới; hãy trả về hoặc giữ stage mới trong biến.

### 27.5. Anti-pattern: tự khởi động B trước khi A có tham số

Nếu B phụ thuộc ID lấy từ A, tạo B ngay từ đầu bằng ID tạm hoặc hard-code có thể gây truy vấn sai. Đặt việc tạo B **trong mapper của thenCompose**.

### 27.6. Anti-pattern: nghĩ thenCompose luôn tạo thread mới

Non-Async mapper có thể chạy inline. Chỉ vì có thenCompose không có nghĩa đang có thêm executor task.

### 27.7. Anti-pattern: nhồi blocking I/O vào commonPool

Số lượng thread hạn chế có thể gây starve nếu nhiều tác vụ blocking. Cần API async thật hoặc executor/tài nguyên được quản lý.

### 27.8. Anti-pattern: bỏ xử lý lỗi inner

**try/catch quanh dòng đăng ký thenCompose** không bắt lỗi async sẽ xảy ra sau khi dòng ấy trả về. Gắn **exceptionally/handle/exceptionallyCompose** hoặc xử lý tại boundary.

### 27.9. Anti-pattern: hủy composed future rồi tin rằng HTTP request đã bị abort

Hủy completion state không đồng nghĩa dừng I/O thật. Kiểm tra API client và xây cancellation policy riêng.

### 27.10. Anti-pattern: lạm dụng orTimeout trên future được chia sẻ

orTimeout hoàn tất **chính future nhận lời gọi**, có thể làm các observer khác nhận timeout không mong muốn. Cân nhắc isolate bằng copy() hoặc thiết kế timeout ở service boundary.

### 27.11. Anti-pattern: chạy độc lập thành chuỗi phụ thuộc

Hai request không liên quan mà cố đưa request thứ hai vào thenCompose của request thứ nhất tạo serialization không cần thiết. Khởi động riêng rồi dùng thenCombine hoặc allOf nếu hợp lý.

### 27.12. Anti-pattern: giả định thứ tự callback khi có nhiều dependent stages

CompletableFuture không hứa **mọi callback gắn trên cùng một source** chạy theo đúng thứ tự đăng ký. Nếu cần A trước B, biểu diễn quan hệ bằng một stage chain rõ ràng.

### 27.13. Anti-pattern: dùng Thread.sleep trong test

Test flaky và chậm. Với logic composition, dùng **new CompletableFuture<>**, **complete(...)**, **completeExceptionally(...)** để điều khiển từng bước một cách xác định.

### 27.14. Anti-pattern: lấy exception message làm giao thức nghiệp vụ

Exception text là chi tiết triển khai, có thể thay đổi. Dùng kiểu exception, error code hoặc result type được định nghĩa rõ ràng.

### 27.15. Anti-pattern: không quản lý executor lifecycle

Tự tạo ExecutorService trong mỗi request, không shutdown hoặc không giới hạn concurrency có thể làm quá tải hệ thống.

### 27.16. Anti-pattern: đặt side effect vào callback có thể được đăng ký nhiều lần

Nếu hai caller tạo hai chuỗi thenCompose riêng từ một source, mapper của mỗi chuỗi có thể được gọi riêng. Những thao tác charge/reserve phải có chiến lược idempotency hoặc deduplication tương ứng, không trông chờ CompletableFuture tự làm một lần cho toàn hệ thống.

## 28. Kiểm thử thenCompose có tính xác định

Unit test cho thenCompose nên xác nhận cả **giá trị** và **thứ tự phụ thuộc**, chứ không chỉ cuối cùng in ra đúng.

Một bộ test nên có:

1. Source pending → mapper chưa chạy.
2. Source complete bình thường → mapper được gọi.
3. Inner pending → composed vẫn pending.
4. Inner complete bình thường → composed có kết quả U.
5. Source failed → mapper không chạy, composed failed.
6. Mapper throws → composed failed.
7. Inner failed → composed failed.
8. Recovery theo đúng policy: fallback thành công hoặc fallback lỗi.
9. Callback trả null stage → composed failed với lỗi phù hợp.
10. Inner hoàn tất bằng null payload → contract phải xử lý rõ.
11. thenApply gây nested future, thenCompose flatten.
12. thenComposeAsync có Executor được kiểm soát trong test.
13. Cancellation: không giả định tự abort upstream/inner.
14. Timeout: không làm hỏng source shared ngoài ý muốn.
15. Những công việc độc lập dùng thenCombine và kết quả chờ đủ cả hai.
16. Một công việc phụ thuộc chỉ bắt đầu khi dữ liệu trước sẵn sàng.
17. Không kiểm tra tên thread/thứ tự log không được API đảm bảo.
18. Không dùng sleep để tạo race; điều khiển trạng thái bằng future cụ thể.

### 28.1. Ví dụ kiểm thử bằng main và AssertionError

Lưu thành **ThenComposeDeterminismTest.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;

public class ThenComposeDeterminismTest {
    static void check(String label, boolean ok) {
        if (!ok) {
            throw new AssertionError(label);
        }
        System.out.println("PASS " + label);
    }

    public static void main(String[] args) {
        CompletableFuture<Integer> source =
                new CompletableFuture<>();

        CompletableFuture<String> inner =
                new CompletableFuture<>();

        AtomicInteger calls = new AtomicInteger();

        CompletableFuture<String> result =
                source.thenCompose(id -> {
                    calls.incrementAndGet();
                    return inner;
                });

        check("mapper-not-called", calls.get() == 0);
        check("pending", !result.isDone());

        source.complete(7);

        check("mapper-called-once", calls.get() == 1);
        check("waits-inner", !result.isDone());

        inner.complete("value-7");

        check("done", result.isDone());
        check("result", "value-7".equals(result.join()));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ThenComposeDeterminismTest.java
java ThenComposeDeterminismTest
~~~

**Stdout:**

~~~text
PASS mapper-not-called
PASS pending
PASS mapper-called-once
PASS waits-inner
PASS done
PASS result
~~~

Đây là test **không phụ thuộc vào timing** và không cần thư viện bên ngoài. Nó kiểm tra các hợp đồng hoàn tất thực sự của thenCompose.

### 28.2. Với JUnit Jupiter

Một test JUnit 5 cũng có thể tạo **new CompletableFuture<>**, sau đó gọi **complete(...)** hoặc **completeExceptionally(...)** để kiểm soát trạng thái.

**Không nhất thiết dùng Mockito để mock CompletableFuture** khi một future thật chưa hoàn tất đã cho phép điều khiển kết quả dễ dàng. Test double nên dùng nơi có side effect hoặc I/O thật.

## 29. Khi nào nên tách phương thức và giữ pipeline ngắn?

Một pipeline dài có thể trở nên khó đọc:

~~~java
start.thenCompose(...)
     .thenCompose(...)
     .thenCompose(...)
     .thenApply(...)
     .exceptionally(...);
~~~

Đây là cú pháp minh họa, không phải code hoàn chỉnh.

Nên cân nhắc:

- Đặt tên từng bước như **findCustomerAsync**, **loadCartAsync**, **reserveInventoryAsync**, **chargeAsync**.
- Mỗi phương thức trả một **CompletionStage<T>** rõ ràng.
- Gói dữ liệu trung gian vào record immutable khi có nhiều thuộc tính cần đi cùng.
- Đặt handler lỗi ở đúng tầng và báo cáo lỗi có ngữ cảnh.
- Xác định side effect, idempotency và các thao tác rollback/compensation ở cấp workflow.

**thenCompose không cung cấp transaction xuyên nhiều dịch vụ.** Một pipeline đặt hàng có nhiều side effect không trở thành atomic chỉ vì nó là một chuỗi CompletableFuture. Với hệ thống phân tán có thể cần saga, outbox, idempotency hoặc giải pháp giao dịch tương ứng.

## 30. Bảng lựa chọn API khi ghép tác vụ

| Nhu cầu | API thường phù hợp |
|---|---|
| T đã có, biến thành U đồng bộ | **thenApply** |
| T đã có, gọi hàm trả CompletionStage<U> | **thenCompose** |
| Muốn mapper của bước phụ thuộc qua Executor | **thenComposeAsync(..., executor)** |
| Hai công việc độc lập cần cả hai kết quả | **thenCombine** |
| Nhiều future độc lập cần chờ tất cả | **allOf** |
| Dùng một trong hai kết quả hoàn tất bình thường | **applyToEither** |
| Chỉ thực hiện hành động khi thành công, không cần trả U | **thenAccept** hoặc **thenRun** |
| Chuyển lỗi thành một giá trị mặc định | **exceptionally** |
| Xử lý cả thành công và thất bại | **handle** |
| Chỉ log/metrics kết quả cuối | **whenComplete** |
| Khi lỗi cần gọi một future fallback khác | **exceptionallyCompose** (Java 12+) |
| Timeout một future của ứng dụng | **orTimeout** (Java 9+) với lưu ý mutation |
| Chuyển nested CompletionStage thành stage phẳng | **thenCompose(Function.identity())** |
| Lấy kết quả cuối tại boundary đồng bộ | **join** hoặc **get** với chính sách chờ |

**Không có phương thức nào phù hợp cho mọi bài toán.** Chọn theo quan hệ phụ thuộc, kiểu trả về của callback và chính sách lỗi/tài nguyên.

## 31. Bài tập thực hành

### Bài 1 — Từ thenApply sang thenCompose

Bạn có:

~~~java
CompletableFuture<String> userId = findUserIdAsync();

CompletableFuture<CompletableFuture<User>> user =
        userId.thenApply(this::fetchUserAsync);
~~~

Đây là đoạn minh họa, giả định findUserIdAsync và fetchUserAsync tồn tại.

**Yêu cầu:** sửa để **user** có kiểu CompletableFuture<User>, không dùng join/get trong callback.

**Gợi ý:** dùng thenCompose thay thenApply.

### Bài 2 — Ba bước phụ thuộc

Các hàm:

~~~text
getTokenAsync()                -> CompletionStage<String>
getProfileAsync(token)         -> CompletionStage<Profile>
getPermissionsAsync(profile)   -> CompletionStage<Permissions>
~~~

Hãy ghép thành CompletionStage<Permissions> mà không chặn thread. Hãy chỉ ra vì sao thenCombine không phù hợp khi profile cần token.

### Bài 3 — Song song rồi phụ thuộc

Hai hàm độc lập **loadPriceAsync(sku)** và **loadStockAsync(sku)**; thao tác **placeOrderAsync(price, stock)** cần cả hai.

Hãy dùng **thenCombine** hoặc ghép context, sau đó **thenCompose** bước order. Chỉ ra cách viết nào tránh tuần tự hóa không cần thiết.

### Bài 4 — Error propagation

Source future thất bại. Hãy dự đoán mapper của thenCompose có chạy không và future kết quả có trạng thái gì. Thêm một fallback đồng bộ bằng exceptionally, rồi một fallback async bằng exceptionallyCompose trên Java 17+.

### Bài 5 — Kiểm thử completion không ngủ

Tạo source và inner future chưa hoàn tất, nối bằng thenCompose. Test trạng thái pending trước và sau source.complete; cuối cùng complete inner và xác nhận output. Không dùng Thread.sleep.

### Bài 6 — Cancellation

Nối source.thenCompose(...). Hủy future kết quả. Test rằng việc này không được mặc định coi là hủy request HTTP thực tế. Thiết kế một interface cho phép abort khi người dùng đóng màn hình.

### Bài 7 — Timeout

Một pipeline dùng chung source future. Hãy giải thích vì sao gọi **source.orTimeout(...)** trong một nhánh có thể tác động các nhánh khác; xem xét **source.copy().orTimeout(...)** trên Java 9+ nếu cần một đường quan sát riêng.

### Bài 8 — Executor

Tạo ExecutorService có hai worker threads; dùng supplyAsync để tạo source rồi thenComposeAsync(..., executor). In **giá trị cuối** thay vì thread name, và shutdown executor trong finally.

### Bài 9 — Null

Phân biệt mapper trả **CompletableFuture.completedFuture(null)** với mapper trả **null**. Dự đoán future kết quả của từng trường hợp.

### Bài 10 — Thiết kế API

Một phương thức service chỉ cần cho phép caller ghép các bước phụ thuộc, không muốn caller tự hoàn tất future. Hãy đề xuất kiểu trả về và giải thích.

## 32. Câu hỏi tự kiểm tra

**Câu 1.** Chữ ký thenCompose cần callback trả U hay CompletionStage<U>?

**Câu 2.** Nếu callback trả CompletableFuture<String>, thenApply tạo kiểu kết quả gì?

**Câu 3.** thenCompose với callback trả CompletableFuture<String> tạo kiểu kết quả gì?

**Câu 4.** Khi source chưa hoàn tất, mapper thenCompose đã bắt đầu chưa?

**Câu 5.** Source hoàn tất nhưng inner còn pending, future compose đã có U chưa?

**Câu 6.** Source lỗi, mapper bình thường có được gọi không?

**Câu 7.** Callback ném exception, composed future xử lý thế nào?

**Câu 8.** Inner future lỗi, lỗi có được phản ánh ở composed future không?

**Câu 9.** thenCompose và thenComposeAsync có đảm bảo cùng thread không?

**Câu 10.** thenComposeAsync không nhận Executor thường dùng cơ chế nào trên CompletableFuture chuẩn?

**Câu 11.** Dùng thenCompose cho hai công việc độc lập có luôn là phương án tốt nhất không?

**Câu 12.** thenCombine khác thenCompose ở đâu?

**Câu 13.** allOf trả CompletableFuture<List<T>> trực tiếp hay CompletableFuture<Void>?

**Câu 14.** Có nên gọi join trong callback để chờ I/O phụ thuộc không?

**Câu 15.** exceptionally khác exceptionallyCompose khi muốn gọi một future fallback ở đâu?

**Câu 16.** exceptionallyCompose xuất hiện từ Java mấy?

**Câu 17.** orTimeout trả future mới tách biệt hay chính future đã gọi?

**Câu 18.** Hủy future compose có đảm bảo inner/upstream bị hủy không?

**Câu 19.** Mapper thenCompose trả null CompletionStage có hợp lệ không?

**Câu 20.** Bên trong inner future có kết quả null thì sao?

**Câu 21.** CompletionStage có đảm bảo I/O không chặn mọi thread không?

**Câu 22.** Đối với callback non-async, thread thực thi có được đảm bảo luôn là main thread không?

**Câu 23.** Muốn đo thời gian toàn pipeline, có cần gọi get/join giữa các bước không?

**Câu 24.** CompletableFuture có tự truyền ThreadLocal/MDC qua mọi thread không?

**Câu 25.** Dùng thenCompose có giúp transaction của hai dịch vụ tự atomic không?

### Đáp án

1. Callback phải trả **CompletionStage<U>** (hoặc subtype), không phải U thuần.
2. **CompletableFuture<CompletableFuture<String>>**.
3. **CompletableFuture<String>** đã flatten.
4. **Chưa**; mapper cần T từ source hoàn tất bình thường.
5. **Chưa**; composed future theo dõi inner.
6. **Không**; composed thường hoàn tất bất thường.
7. **Composed future hoàn tất bất thường** với exception từ callback.
8. **Có**; composed future phản ánh exceptional completion.
9. **Không**; biến thể Async thay chính sách thực thi mapper.
10. **Default async executor facility**, thường là ForkJoinPool.commonPool trên CompletableFuture chuẩn.
11. **Không**; công việc độc lập có thể dùng thenCombine/allOf để không tạo phụ thuộc không cần thiết.
12. **thenCombine** chờ hai stage sẵn có và kết hợp; **thenCompose** tạo stage thứ hai từ kết quả thứ nhất.
13. **CompletableFuture<Void>**; muốn List phải thu thập kết quả theo contract.
14. **Không nên**; có thể chặn thread và gây starvation/deadlock. Dùng thenCompose.
15. **exceptionally** trả giá trị T; **exceptionallyCompose** trả một stage T để recover async.
16. **Java 12**.
17. **Chính CompletableFuture nhận lời gọi**.
18. **Không**; phải thiết kế cancellation propagation và abort I/O riêng.
19. **Không**; stage sẽ hoàn tất bất thường, thường với NullPointerException.
20. **Có thể hợp lệ nếu payload được phép null**, nhưng cần contract rõ.
21. **Không**; async abstraction không tự chuyển blocking I/O thành nonblocking I/O.
22. **Không**; callback có thể chạy trên thread hoàn tất stage hoặc thread khác thực hiện completion.
23. **Không**; ghép toàn bộ pipeline rồi đo ở boundary với công cụ phù hợp.
24. **Không**; cần explicit context propagation hoặc cơ chế framework.
25. **Không**; cần transaction/idempotency/compensation riêng.

## 33. Tổng kết

**thenCompose là công cụ chuẩn để ghép những công việc bất đồng bộ có quan hệ phụ thuộc và làm phẳng future lồng nhau.** Nó cho phép biểu diễn dữ liệu chảy từ A sang B sang C mà không phải gọi join/get để chặn thread giữa các bước.

Những quy tắc cần nhớ:

- **thenApply** cho **T → U**, **thenCompose** cho **T → CompletionStage<U>**.
- thenCompose trả **CompletableFuture<U>**, không phải **CompletableFuture<CompletableFuture<U>>**.
- Mapper chỉ được gọi khi source hoàn tất **bình thường**, và composed future đợi completion của stage mà mapper trả về.
- Lỗi từ source, mapper hoặc inner stage đều có thể làm composed future **hoàn tất bất thường**.
- **thenComposeAsync** chọn cách scheduling mapper; không tự bảo đảm mọi I/O đều phi chặn.
- **thenCombine/allOf** phù hợp khi nhiều tác vụ độc lập; **thenCompose** phù hợp khi bước sau cần dữ liệu bước trước.
- **Không dùng join/get bên trong callback để nối I/O phụ thuộc**; dùng join/get tại boundary khi có chủ đích.
- **exceptionally/handle/whenComplete/exceptionallyCompose** có mục tiêu riêng; không nuốt lỗi vô điều kiện.
- **orTimeout và cancel không tự dừng mọi công việc bên dưới**; thiết kế timeout/cancellation, retry và idempotency phù hợp.
- Viết test bằng **CompletableFuture chưa hoàn tất** và **complete/completeExceptionally** để xác minh thứ tự phụ thuộc, không cần sleep.
- Quản lý Executor, context propagation, concurrency limits và giao dịch ở tầng ứng dụng; CompletableFuture không tự làm các việc này.

### Tài liệu chính thức (API hiện đại)

- [CompletableFuture — Oracle Java SE 26: thenCompose, thenComposeAsync, exceptional completion, cancellation, timeout và Executor](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [CompletionStage — Oracle Java SE 26: hợp đồng các phương thức composition](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletionStage.html)
- [Executor — Oracle Java SE 26: thực thi tác vụ](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Executor.html)
- [ExecutorService — Oracle Java SE 26: quản lý tài nguyên thread pool và shutdown](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [ForkJoinPool — Oracle Java SE 26: commonPool và xử lý công việc song song](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ForkJoinPool.html)
- [CompletionException — Oracle Java SE 26: wrapper của exceptional completion](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletionException.html)
