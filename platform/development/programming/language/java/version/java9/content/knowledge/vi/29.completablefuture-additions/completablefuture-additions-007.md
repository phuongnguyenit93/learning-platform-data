# Ảnh hưởng của các phương thức trả lại cùng CompletableFuture

Trong Java 9, một số phương thức của **CompletableFuture** thực hiện thao tác trên chính future hiện tại và trả về lại cùng một đối tượng. Các phương thức đáng chú ý là **completeAsync()**, **orTimeout()** và **completeOnTimeout()**.

Điểm quan trọng nằm ở danh tính đối tượng: giá trị trả về không phải một future độc lập đại diện cho kết quả của một bước mới. Nó là cùng instance với future ban đầu. Vì vậy, mọi biến tham chiếu đến instance đó đều quan sát cùng trạng thái hoàn thành, cùng kết quả hoặc cùng lỗi.

Điều này khác với các phương thức nối pipeline như thenApply() hay handle(), vốn tạo một future phụ thuộc mới.

## 1. Nhận biết phương thức trả lại cùng future

Ba phương thức Java 9 cần nhớ:

| Phương thức | Tác dụng lên future hiện tại | Giá trị trả về |
|---|---|---|
| completeAsync(Supplier) | Yêu cầu hoàn thành future bằng kết quả Supplier được tính bất đồng bộ | Chính future hiện tại |
| orTimeout(timeout, unit) | Nếu chưa hoàn thành trước thời hạn, hoàn thành future hiện tại với TimeoutException | Chính future hiện tại |
| completeOnTimeout(value, timeout, unit) | Nếu chưa hoàn thành trước thời hạn, hoàn thành future hiện tại bình thường bằng giá trị dự phòng | Chính future hiện tại |

Cả ba phương thức trả về kiểu CompletableFuture<T> và trả lại tham chiếu this. Có thể kiểm chứng bằng toán tử ==:

~~~java
CompletableFuture<String> future = new CompletableFuture<>();

CompletableFuture<String> returned =
        future.completeOnTimeout("fallback", 1, TimeUnit.SECONDS);

System.out.println(returned == future);
~~~

Kết quả là true. Điều đó cho biết returned và future là hai biến tham chiếu đến cùng một đối tượng.

## 2. completeAsync(): hoàn thành chính future bằng Supplier

completeAsync() yêu cầu CompletableFuture lấy kết quả từ một Supplier và dùng kết quả đó để hoàn thành future hiện tại.

Có hai overload:

~~~java
future.completeAsync(supplier);
future.completeAsync(supplier, executor);
~~~

- Overload thứ nhất dùng executor mặc định của CompletableFuture.
- Overload thứ hai dùng Executor do ứng dụng cung cấp.
- Supplier trả về giá trị dùng để hoàn thành future.
- Nếu Supplier ném ngoại lệ, future được hoàn thành theo hướng exceptional.
- Phương thức trả lại chính future ban đầu, không tạo một future kết quả riêng.

Ví dụ:

~~~java
CompletableFuture<String> future = new CompletableFuture<>();

CompletableFuture<String> returned =
        future.completeAsync(() -> "loaded");

System.out.println(returned == future);
System.out.println(future.join());
~~~

Kết quả:

~~~text
true
loaded
~~~

completeAsync() không phải là phép biến đổi tạo ra một stage mới như thenApply(). Nó yêu cầu hoàn thành chính future đang được gọi. Nếu future đã được hoàn thành trước đó, lần hoàn thành tiếp theo không thay thế kết quả đã được thiết lập bằng các thao tác hoàn thành thông thường.

Khi cần kiểm soát nơi chạy Supplier, truyền Executor rõ ràng. Executor quyết định cách thực thi tác vụ; không nên giả định Supplier luôn chạy trên một thread cụ thể.

## 3. orTimeout(): đặt thời hạn cho chính future

orTimeout(long timeout, TimeUnit unit) đặt thời hạn hoàn thành cho future hiện tại.

~~~java
CompletableFuture<String> future = new CompletableFuture<>();

CompletableFuture<String> returned =
        future.orTimeout(2, TimeUnit.SECONDS);
~~~

Nếu future chưa hoàn thành khi hết thời hạn, chính future đó được hoàn thành exceptionally với TimeoutException.

Các điểm cần nhớ:

- Phương thức trả về chính future được gọi.
- TimeoutException trở thành nguyên nhân của trạng thái hoàn thành exceptional.
- Nếu future đã hoàn thành trước thời hạn, timeout không thay đổi kết quả đã có.
- Các dependent stage gắn với future này sẽ nhận kết quả hoặc lỗi tương ứng khi future hoàn thành.
- Timeout không tạo ra một bản sao độc lập của future.

Khi lấy kết quả bằng join(), lỗi thường được bọc trong CompletionException và có thể đọc nguyên nhân bằng getCause(). Khi dùng get(), lỗi được biểu diễn qua ExecutionException.

Ví dụ:

~~~java
CompletableFuture<String> request = new CompletableFuture<>();

request.orTimeout(1, TimeUnit.SECONDS);

try {
    System.out.println(request.join());
} catch (CompletionException exception) {
    System.out.println(exception.getCause().getClass().getSimpleName());
}
~~~

Nếu request không được hoàn thành trong một giây, kết quả in ra là:

~~~text
TimeoutException
~~~

## 4. completeOnTimeout(): dùng giá trị dự phòng trên chính future

completeOnTimeout(T value, long timeout, TimeUnit unit) cũng đặt thời hạn, nhưng cách xử lý khi hết hạn khác orTimeout().

Nếu future chưa hoàn thành trước thời hạn, phương thức hoàn thành chính future đó bình thường bằng giá trị dự phòng được truyền vào.

~~~java
CompletableFuture<String> request = new CompletableFuture<>();

CompletableFuture<String> returned =
        request.completeOnTimeout("default response", 2, TimeUnit.SECONDS);

System.out.println(returned == request);
System.out.println(request.join());
~~~

Nếu không có kết quả thật trước thời hạn, kết quả là:

~~~text
true
default response
~~~

Nếu request đã hoàn thành trước thời hạn, giá trị dự phòng không ghi đè kết quả thật. Vì vậy, completeOnTimeout() phù hợp khi ứng dụng chấp nhận một giá trị mặc định nếu công việc chậm hơn thời gian cho phép.

So sánh hai phương thức timeout:

| Tình huống | orTimeout() | completeOnTimeout() |
|---|---|---|
| Future hoàn thành trước thời hạn | Giữ kết quả hiện có | Giữ kết quả hiện có |
| Future chưa hoàn thành khi hết hạn | Hoàn thành exceptionally bằng TimeoutException | Hoàn thành bình thường bằng giá trị dự phòng |
| Instance bị tác động | Future hiện tại | Future hiện tại |
| Kiểu trả về | CompletableFuture<T> | CompletableFuture<T> |

## 5. Ảnh hưởng đến các biến cùng tham chiếu và dependent stage

Vì phương thức trả về cùng instance, mọi biến tham chiếu đến future đó đều nhìn thấy trạng thái hoàn thành giống nhau.

~~~java
CompletableFuture<String> original = new CompletableFuture<>();
CompletableFuture<String> alias = original.orTimeout(1, TimeUnit.SECONDS);

System.out.println(alias == original);
~~~

Nếu timeout xảy ra, cả original và alias đều quan sát cùng một future đã hoàn thành exceptionally. Không có một bản sao nào được tạo ra để chỉ timeout ở alias.

Các dependent stage được tạo trước hoặc sau đó cũng phụ thuộc vào kết quả hoàn thành của future gốc:

~~~java
CompletableFuture<String> source = new CompletableFuture<>();
CompletableFuture<Integer> length = source.thenApply(String::length);

source.completeOnTimeout("fallback", 1, TimeUnit.SECONDS);
~~~

Nếu timeout hoàn thành source bằng fallback, stage length sẽ nhận chuỗi fallback và tính độ dài tương ứng.

Tuy nhiên, dependent stage là một đối tượng CompletableFuture khác. Việc source hoàn thành sẽ kích hoạt stage phụ thuộc; nó không biến stage đó thành cùng instance với source.

## 6. Phân biệt phương thức trả lại this và phương thức tạo future mới

Không phải mọi phương thức trả về CompletableFuture đều trả lại future ban đầu.

| Nhóm | Ví dụ | Quan hệ đối tượng |
|---|---|---|
| Trả lại chính future | completeAsync(), orTimeout(), completeOnTimeout() | Cùng instance |
| Tạo dependent future | thenApply(), thenCompose(), thenCombine(), handle(), whenComplete(), exceptionally() | Future mới phụ thuộc vào future trước |
| Tạo bản sao future | copy() | Future mới nhận kết quả hoặc lỗi từ future nguồn |
| Trả về CompletionStage giới hạn | minimalCompletionStage() | View CompletionStage riêng, không phải cùng CompletableFuture |

Ví dụ với thenApply():

~~~java
CompletableFuture<String> source =
        CompletableFuture.completedFuture("Java");

CompletableFuture<Integer> dependent =
        source.thenApply(String::length);

System.out.println(dependent == source);
System.out.println(dependent.join());
System.out.println(source.join());
~~~

Kết quả:

~~~text
false
4
Java
~~~

thenApply() tạo một future phụ thuộc chứa giá trị đã biến đổi. Source vẫn giữ kết quả Java; dependent giữ kết quả 4.

Ngược lại, orTimeout() tác động lên chính future mà nó được gọi. Sự khác nhau này quan trọng khi một future được chia sẻ cho nhiều thành phần trong ứng dụng.

## 7. Chọn vị trí đặt timeout trong pipeline

Vị trí gọi orTimeout() quyết định future nào bị giới hạn thời gian.

~~~java
CompletableFuture<String> source = loadData();

source.orTimeout(2, TimeUnit.SECONDS);
CompletableFuture<Integer> derived =
        source.thenApply(String::length);
~~~

Ở đây timeout được đặt trên source. Nếu source timeout, derived cũng hoàn thành exceptionally vì nó phụ thuộc vào source.

Ngược lại:

~~~java
CompletableFuture<String> source = loadData();

CompletableFuture<Integer> derived =
        source.thenApply(String::length)
              .orTimeout(2, TimeUnit.SECONDS);
~~~

Ở đây timeout được đặt trên derived. Source không bị áp dụng timeout trực tiếp; chỉ stage đã biến đổi bị giới hạn thời gian.

Nếu muốn đặt timeout riêng cho một nhánh mà không làm thay đổi future dùng chung, có thể tạo bản sao trước:

~~~java
CompletableFuture<String> shared = loadData();

CompletableFuture<String> branch =
        shared.copy().orTimeout(2, TimeUnit.SECONDS);
~~~

copy() tạo một CompletableFuture khác. Timeout áp dụng trên branch, còn shared giữ chính sách hoàn thành riêng. Khi shared hoàn thành, kết quả hoặc lỗi của nó được truyền sang bản sao nếu bản sao chưa hoàn thành trước đó.

## 8. Cạnh tranh hoàn thành và các lưu ý quan trọng

Một future có thể nhận yêu cầu hoàn thành từ nhiều nguồn:

- Supplier của completeAsync().
- Kết quả thật từ complete(value).
- Lỗi từ completeExceptionally(exception).
- Timeout từ orTimeout().
- Giá trị dự phòng từ completeOnTimeout().
- Hủy bằng cancel().

Các thao tác hoàn thành thông thường cạnh tranh để thiết lập kết quả. Một khi future đã hoàn thành, các lần hoàn thành thông thường sau đó không thay thế kết quả hiện có. Vì vậy, nếu kết quả thật đến gần thời điểm timeout, thao tác nào hoàn thành thành công trước sẽ quyết định trạng thái của future.

Một số lưu ý:

- **Timeout là tác động lên đối tượng:** nếu future được chia sẻ, mọi thành phần dùng cùng instance đều chịu kết quả timeout.
- **Không giả định timeout chính xác tuyệt đối theo thời gian thực:** việc thực thi tác vụ timeout còn phụ thuộc bộ lập lịch và tải của runtime.
- **Không gọi join() tùy tiện trên thread cần phản hồi nhanh:** join() chặn thread hiện tại cho đến khi future hoàn thành.
- **Supplier có thể thất bại:** ngoại lệ phát sinh trong Supplier của completeAsync() làm future hoàn thành exceptional.
- **Không nhầm cancel() với timeout:** cancel() hoàn thành future theo trạng thái hủy, còn orTimeout() dùng TimeoutException.
- **Cẩn trọng với obtrudeValue() và obtrudeException():** đây là các phương thức ép đặt kết quả trên future hiện tại và trả về void. Chúng có thể thay đổi kết quả quan sát qua get()/join() sau khi future đã hoàn thành, nhưng không tính toán lại các dependent stage đã chạy.

## 9. Ví dụ hoàn chỉnh: kiểm tra danh tính và tác động của từng phương thức

Lưu chương trình dưới tên **SameFutureMethodsDemo.java**. Ví dụ dùng các API Java 9 và có thể biên dịch với Java 9 trở lên.

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.TimeUnit;

public class SameFutureMethodsDemo {
    public static void main(String[] args) {
        CompletableFuture<String> asyncFuture = new CompletableFuture<>();
        CompletableFuture<String> asyncReturned =
                asyncFuture.completeAsync(() -> "loaded");
        System.out.println("completeAsync same instance: " +
                (asyncReturned == asyncFuture));
        System.out.println("completeAsync value: " + asyncFuture.join());

        CompletableFuture<String> timeoutFuture = new CompletableFuture<>();
        CompletableFuture<String> timeoutReturned =
                timeoutFuture.orTimeout(0, TimeUnit.MILLISECONDS);
        System.out.println("orTimeout same instance: " +
                (timeoutReturned == timeoutFuture));
        try {
            timeoutFuture.join();
        } catch (CompletionException exception) {
            System.out.println("orTimeout outcome: " +
                    exception.getCause().getClass().getSimpleName());
        }

        CompletableFuture<String> fallbackFuture = new CompletableFuture<>();
        CompletableFuture<String> fallbackReturned =
                fallbackFuture.completeOnTimeout(
                        "fallback", 0, TimeUnit.MILLISECONDS);
        System.out.println("completeOnTimeout same instance: " +
                (fallbackReturned == fallbackFuture));
        System.out.println("completeOnTimeout value: " + fallbackFuture.join());

        CompletableFuture<String> source =
                CompletableFuture.completedFuture("Java");
        CompletableFuture<Integer> dependent =
                source.thenApply(String::length);
        System.out.println("thenApply creates different instance: " +
                ((Object) dependent != source));
        System.out.println("dependent value: " + dependent.join());
        System.out.println("source value remains: " + source.join());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 9 SameFutureMethodsDemo.java
java SameFutureMethodsDemo
~~~

Kết quả stdout:

~~~text
completeAsync same instance: true
completeAsync value: loaded
orTimeout same instance: true
orTimeout outcome: TimeoutException
completeOnTimeout same instance: true
completeOnTimeout value: fallback
thenApply creates different instance: true
dependent value: 4
source value remains: Java
~~~

Kết quả cho thấy ba phương thức completeAsync(), orTimeout() và completeOnTimeout() trả về đúng instance được gọi. thenApply() tạo một future phụ thuộc khác, còn future nguồn vẫn giữ kết quả ban đầu.

## 10. Ghi nhớ

- completeAsync(), orTimeout() và completeOnTimeout() có từ Java 9 và trả lại chính CompletableFuture hiện tại.
- Gán giá trị trả về của các phương thức này vào biến khác không tạo bản sao; hai biến cùng tham chiếu một đối tượng.
- completeAsync() yêu cầu Supplier hoàn thành future hiện tại bằng kết quả hoặc ngoại lệ của Supplier.
- orTimeout() hoàn thành future hiện tại exceptionally bằng TimeoutException nếu thời hạn đến trước khi có kết quả.
- completeOnTimeout() hoàn thành future hiện tại bình thường bằng giá trị dự phòng nếu thời hạn đến trước kết quả.
- Các dependent stage nhận kết quả hoặc lỗi từ future nguồn nhưng là những future riêng.
- Vị trí đặt timeout trong pipeline quyết định stage nào bị giới hạn thời gian.
- Dùng copy() nếu cần một future riêng để áp dụng chính sách timeout độc lập.
- Các thao tác hoàn thành có thể cạnh tranh; kết quả hoàn thành thành công đầu tiên thường quyết định trạng thái future.
