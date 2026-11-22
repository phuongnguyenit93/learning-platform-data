# CompletableFuture: Hoàn tất bình thường và hoàn tất bằng ngoại lệ trong Java

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích hai kết quả cơ bản của một <code>CompletableFuture&lt;T&gt;</code>: **hoàn tất bình thường** (*normal completion*) và **hoàn tất bằng ngoại lệ** (*exceptional completion*).
- Nhận biết một future chưa hoàn tất, đã hoàn tất thành công hoặc đã hoàn tất lỗi; phân biệt chúng với khái niệm luồng đang chạy hay đã dừng.
- Dùng <code>complete(value)</code>, <code>completeExceptionally(error)</code>, <code>completedFuture(value)</code>, <code>failedFuture(error)</code>, <code>supplyAsync(...)</code> và <code>runAsync(...)</code> đúng mục đích.
- Quan sát kết quả với <code>get()</code>, <code>join()</code>, <code>getNow(...)</code>, <code>isDone()</code>, <code>isCompletedExceptionally()</code> và <code>isCancelled()</code>.
- Dự đoán cách các stage phụ thuộc như <code>thenApply</code>, <code>thenCompose</code>, <code>exceptionally</code>, <code>handle</code> và <code>whenComplete</code> hoạt động khi nguồn thành công hoặc thất bại.
- Hiểu mối quan hệ giữa completion, cancellation, timeout và việc xử lý công việc ở luồng thực thi.

Bài sử dụng API Java 17+ trong <code>java.util.concurrent</code>, ưu tiên ví dụ chạy độc lập với kết quả xác định.

## 2. CompletableFuture biểu diễn điều gì?

<code>CompletableFuture&lt;T&gt;</code> biểu diễn một kết quả có kiểu <code>T</code> có thể xuất hiện về sau. Nó triển khai cả <code>Future&lt;T&gt;</code> và <code>CompletionStage&lt;T&gt;</code>: vừa cho phép đợi/đọc kết quả, vừa có thể khai báo các bước xử lý tiếp theo.

Tại một thời điểm, future có thể:

1. **Chưa hoàn tất:** chưa có kết quả cuối cùng được ghi vào future.
2. **Hoàn tất bình thường:** chứa một giá trị kết quả kiểu <code>T</code> (kể cả <code>null</code> nếu API cho phép).
3. **Hoàn tất bằng ngoại lệ:** chứa trạng thái thất bại được liên kết với một <code>Throwable</code>, để những nơi quan sát kết quả biết thao tác không có giá trị thành công.

~~~text
                     CompletableFuture<T> chưa hoàn tất
                                   |
                     +-------------+-------------+
                     |                           |
             hoàn tất bình thường        hoàn tất bằng ngoại lệ
                     |                           |
                giá trị T/null               Throwable/cause
                     |                           |
               join()/get()                 join()/get()
               trả giá trị                 ném lỗi theo API
                     |                           |
          stage thành công chạy        stage chỉ chạy khi thành công
                                      có thể được bỏ qua; nhánh xử lý
                                      ngoại lệ có thể được kích hoạt
~~~

**Hai kiểu hoàn tất đều là “đã hoàn tất”.** Vì vậy <code>isDone()</code> trả về <code>true</code> cho cả kết quả bình thường, lỗi và hủy. Không được dùng riêng <code>isDone()</code> để kết luận thành công.

Cần phân biệt **completion của future** và **vòng đời tác vụ thực thi**. Một future có thể được hoàn tất thủ công mà không có thread chạy nền; ngược lại, đánh dấu một future bị hủy không nhất thiết buộc code đang chạy dừng ngay. Một future chỉ lưu trạng thái kết quả theo hợp đồng của nó.

## 3. Hoàn tất bình thường: normal completion

Một <code>CompletableFuture&lt;String&gt;</code> hoàn tất bình thường khi đã có kết quả thành công cuối cùng, ví dụ <code>"OK"</code>.

### 3.1. Tạo future đã hoàn tất

~~~java
CompletableFuture<String> done =
        CompletableFuture.completedFuture("OK");
~~~

Đoạn trên là **mã minh họa**, với import <code>java.util.concurrent.CompletableFuture</code> trong ngữ cảnh Java phù hợp. <code>done</code> đã hoàn tất ngay tại thời điểm khởi tạo, nên <code>done.join()</code> trả về <code>"OK"</code> mà không phải đợi một computation nào.

<code>CompletableFuture.completedFuture(null)</code> cũng là một future **hoàn tất bình thường** với giá trị <code>null</code>. Do đó, **giá trị null không đồng nghĩa future chưa hoàn tất hoặc đã lỗi**.

### 3.2. Hoàn tất thủ công

~~~java
CompletableFuture<String> result = new CompletableFuture<>();
boolean first = result.complete("Đã xử lý");
boolean second = result.complete("Giá trị khác");
~~~

Đây là **đoạn mã minh họa**, không phải chương trình độc lập. Trong trình tự không có cạnh tranh như trên:

- <code>new CompletableFuture&lt;&gt;()</code> tạo một future chưa hoàn tất.
- Lời gọi <code>complete("Đã xử lý")</code> đầu tiên hoàn tất thành công và trả về <code>true</code>.
- Lời gọi <code>complete("Giá trị khác")</code> trả về <code>false</code>, vì future đã có kết quả; giá trị thành công ban đầu vẫn được giữ.

Phương thức <code>complete(T value)</code> trả về <code>true</code> khi chính lời gọi đó hoàn tất future, và <code>false</code> nếu future đã được hoàn tất trước. Trong chương trình nhiều luồng, nhiều bên có thể cố gắng hoàn tất cùng một future; chỉ một lời gọi hoàn tất thông thường thắng cuộc đua.

### 3.3. Completion từ tác vụ bất đồng bộ

~~~java
CompletableFuture<Integer> answer =
        CompletableFuture.supplyAsync(() -> 40 + 2);
~~~

<code>supplyAsync</code> nhận <code>Supplier&lt;T&gt;</code>: nếu supplier kết thúc bằng việc trả về một giá trị, future được hoàn tất bình thường với giá trị đó. Không có bảo đảm future đã hoàn tất tại ngay thời điểm phương thức <code>supplyAsync</code> trả về. Phải dùng cơ chế quan sát kết quả nếu cần biết chắc.

<code>runAsync</code> nhận <code>Runnable</code>, trả về <code>CompletableFuture&lt;Void&gt;</code>. Khi runnable chạy xong bình thường, future của nó hoàn tất bình thường với giá trị <code>null</code>; đây là trạng thái thành công, không phải thiếu kết quả do lỗi.

Nếu không cung cấp <code>Executor</code> riêng, các dạng async phổ biến của <code>CompletableFuture</code> sử dụng cơ chế executor mặc định của JDK, thường là <code>ForkJoinPool.commonPool()</code> theo điều kiện được tài liệu API mô tả. Không dựa vào tên luồng cụ thể để xác định thành công hay thất bại.

## 4. Hoàn tất bằng ngoại lệ: exceptional completion

Một future hoàn tất bằng ngoại lệ khi kết quả cuối cùng của nó là trạng thái lỗi, thay vì giá trị <code>T</code>. Ngoại lệ có thể đến từ code thực thi hoặc được gắn vào future bằng lời gọi hoàn tất thủ công.

### 4.1. Hoàn tất thủ công bằng completeExceptionally

~~~java
CompletableFuture<String> result = new CompletableFuture<>();
IOException original = new IOException("Không thể đọc dữ liệu");

boolean first = result.completeExceptionally(original);
boolean second = result.complete("Kết quả đến muộn");
~~~

Đây là **mã minh họa** trong ngữ cảnh có import <code>CompletableFuture</code> và <code>IOException</code>. Với trình tự trên, <code>first</code> là <code>true</code>, còn <code>second</code> là <code>false</code>.

<code>result</code> hoàn tất bằng ngoại lệ <code>original</code>; lời gọi <code>complete</code> sau đó không thay trạng thái lỗi thành thành công.

**Quan trọng:** <code>completeExceptionally(error)</code> là thao tác **hoàn tất future với trạng thái lỗi**, không phải trực tiếp ném <code>error</code> tại nơi gọi. Nơi quan sát kết quả về sau sẽ nhận ngoại lệ theo hợp đồng của <code>get()</code> hoặc <code>join()</code>.

Tham số <code>Throwable</code> của <code>completeExceptionally</code> không được là <code>null</code>; truyền <code>null</code> gây <code>NullPointerException</code> ở lời gọi này và không đại diện cho một completion thành công.

### 4.2. Tạo future lỗi ngay từ đầu

~~~java
CompletableFuture<String> failed =
        CompletableFuture.failedFuture(
                new IllegalStateException("Dịch vụ không khả dụng"));
~~~

Đoạn này dùng <code>failedFuture(Throwable)</code>, có từ Java 9 và khả dụng trên Java 17+. Future trả về đã hoàn tất bằng ngoại lệ. Đây là công cụ thuận tiện cho việc biểu đạt một bước thất bại ngay lập tức, ví dụ khi kiểm tra tiền điều kiện hoặc trả về stub/test fixture.

### 4.3. Supplier hoặc Runnable ném ngoại lệ

~~~java
CompletableFuture<Integer> future =
        CompletableFuture.supplyAsync(() -> {
            throw new IllegalArgumentException("Dữ liệu không hợp lệ");
        });
~~~

Future sẽ hoàn tất bằng ngoại lệ khi supplier ném lỗi và cơ chế thực thi đã ghi nhận thất bại. Loại exception mà code bên ngoài thấy phụ thuộc API quan sát kết quả: ví dụ <code>join()</code> thường ném <code>CompletionException</code> có cause là lỗi của supplier.

Tuy nhiên, <code>supplyAsync</code> được gọi thành công **không đồng nghĩa supplier chạy thành công**. Phương thức đặt lịch có thể trả về một future trước khi supplier bắt đầu, và completion sau đó mới nói lên kết quả xử lý.

## 5. Quy tắc chỉ một lần hoàn tất thông thường có hiệu lực

<code>CompletableFuture</code> cho phép nhiều luồng cạnh tranh hoàn tất bằng <code>complete</code>, <code>completeExceptionally</code> hoặc <code>cancel</code>. Chỉ một kết quả hoàn tất thông thường được ghi nhận đầu tiên có hiệu lực; những lời gọi hoàn tất đến sau không ghi đè kết quả đã có.

| Trạng thái trước lời gọi | Lời gọi | Kết quả |
| --- | --- | --- |
| Chưa hoàn tất | <code>complete("A")</code> | Hoàn tất thành công; trả <code>true</code> |
| Chưa hoàn tất | <code>completeExceptionally(e)</code> | Hoàn tất lỗi; trả <code>true</code> |
| Đã thành công | <code>complete("B")</code> | Không đổi giá trị; trả <code>false</code> |
| Đã thành công | <code>completeExceptionally(e)</code> | Không đổi thành lỗi; trả <code>false</code> |
| Đã lỗi | <code>complete("B")</code> | Không đổi thành công; trả <code>false</code> |
| Đã lỗi | <code>completeExceptionally(other)</code> | Không thay lỗi cũ; trả <code>false</code> |

Với các lời gọi hoàn tất đồng thời, không thể biết trước bên nào thắng chỉ nhờ thứ tự viết trong hai thread khác nhau. Nếu ứng dụng cần một chính sách “chọn kết quả tốt nhất”, “ưu tiên dữ liệu mới” hoặc “ưu tiên lỗi”, phải định nghĩa và đồng bộ hóa chính sách đó; <code>complete</code> không tự so sánh mức độ ưu tiên.

Ngoại lệ đối với quy tắc *không ghi đè* là API cấp thấp <code>obtrudeValue</code> và <code>obtrudeException</code>, vốn có chủ đích ép kết quả ở một future đã hoàn tất. Chúng được tài liệu API định vị chủ yếu cho mục đích phục hồi lỗi đặc biệt và có thể gây ra sự không nhất quán với dependent stage đã quan sát kết quả trước đó. Không dùng chúng làm cơ chế thay đổi kết quả thông thường trong nghiệp vụ.

## 6. Ví dụ Java 17 độc lập: hai trạng thái và giá trị trả về của complete

Tạo tệp **CompletionOutcomeDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class CompletionOutcomeDemo {
    public static void main(String[] args) {
        CompletableFuture<String> success = new CompletableFuture<>();
        CompletableFuture<String> failed = new CompletableFuture<>();

        System.out.println("Ban đầu: " + success.isDone()
                + ", " + failed.isDone());

        boolean successFirst = success.complete("DONE");
        boolean successAgain = success.completeExceptionally(
                new IllegalStateException("Quá muộn"));

        IllegalArgumentException original =
                new IllegalArgumentException("ID không hợp lệ");
        boolean failedFirst = failed.completeExceptionally(original);
        boolean failedAgain = failed.complete("LATE");

        System.out.println("Complete success: "
                + successFirst + ", " + successAgain);
        System.out.println("Complete failure: "
                + failedFirst + ", " + failedAgain);

        System.out.println("Success status: "
                + success.isDone() + ", "
                + success.isCompletedExceptionally());
        System.out.println("Failure status: "
                + failed.isDone() + ", "
                + failed.isCompletedExceptionally());

        System.out.println("Success value: " + success.join());

        try {
            failed.join();
        } catch (CompletionException ex) {
            System.out.println("Failure cause: "
                    + ex.getCause().getClass().getSimpleName());
            System.out.println("Original instance: "
                    + (ex.getCause() == original));
        }

        CompletableFuture<String> emptySuccess =
                CompletableFuture.completedFuture(null);
        System.out.println("Null is normal: "
                + emptySuccess.isDone() + ", "
                + emptySuccess.isCompletedExceptionally() + ", "
                + (emptySuccess.join() == null));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 CompletionOutcomeDemo.java
java CompletionOutcomeDemo
~~~

**Stdout chính xác:**

~~~text
Ban đầu: false, false
Complete success: true, false
Complete failure: true, false
Success status: true, false
Failure status: true, true
Success value: DONE
Failure cause: IllegalArgumentException
Original instance: true
Null is normal: true, false, true
~~~

### Giải thích kết quả

1. Cả hai future ban đầu đều chưa hoàn tất, nên <code>isDone()</code> là <code>false</code>.
2. <code>success.complete("DONE")</code> thắng và đưa future vào trạng thái bình thường. Lần <code>completeExceptionally</code> sau không đảo ngược được kết quả.
3. <code>failed.completeExceptionally(original)</code> thắng và đưa future vào trạng thái lỗi. Lần <code>complete("LATE")</code> sau không sửa được lỗi đã lưu.
4. <code>isDone()</code> đều trả về <code>true</code> sau khi hai future hoàn tất; chỉ future lỗi có <code>isCompletedExceptionally()</code> trả về <code>true</code>.
5. <code>success.join()</code> trả đúng <code>DONE</code>. <code>failed.join()</code> ném <code>CompletionException</code> trong trường hợp lỗi <code>IllegalArgumentException</code> của ví dụ.
6. <code>ex.getCause() == original</code> xác nhận cause là **cùng đối tượng lỗi** đã được dùng để hoàn tất, không chỉ cùng loại hoặc cùng message.
7. Future có kết quả <code>null</code> vẫn là future hoàn tất bình thường: <code>isDone()</code> là <code>true</code>, <code>isCompletedExceptionally()</code> là <code>false</code> và <code>join()</code> trả <code>null</code>.

Ví dụ không dùng luồng nền, nên thứ tự các lần hoàn tất và các dòng kết quả không phụ thuộc lịch chạy của executor.

## 7. Quan sát trạng thái: isDone, isCompletedExceptionally và isCancelled

Các phương thức này trả lời những câu hỏi khác nhau:

| Phương thức | Câu hỏi | Điều không thể suy ra |
| --- | --- | --- |
| <code>isDone()</code> | Future đã hoàn tất theo bất kỳ hình thức nào chưa? | Không chứng minh thành công |
| <code>isCompletedExceptionally()</code> | Future đã kết thúc vì trạng thái ngoại lệ/hủy hay chưa? | Không cung cấp toàn bộ nguyên nhân nếu không quan sát exception |
| <code>isCancelled()</code> | Future đã bị hủy theo trạng thái cancellation của CompletableFuture chưa? | Không chứng minh công việc bên dưới đã dừng hoàn toàn |
| <code>getNumberOfDependents()</code> | Ước lượng số dependent stage chờ completion của future | Không phải metric điều phối có tính nhất quán tức thời |

Ví dụ:

~~~java
CompletableFuture<String> f =
        CompletableFuture.failedFuture(new IllegalStateException("x"));

System.out.println(f.isDone());                   // true
System.out.println(f.isCompletedExceptionally()); // true
System.out.println(f.isCancelled());              // false
~~~

Đây là **đoạn minh họa**, không phải chương trình độc lập. <code>isCompletedExceptionally()</code> nhận diện trạng thái lỗi, còn <code>isCancelled()</code> giúp phân biệt tình huống hủy. Không coi mọi ngoại lệ là cancellation.

Một pattern dễ sai:

~~~java
if (future.isDone()) {
    String value = future.join(); // Vẫn có thể ném lỗi!
}
~~~

Đây là **đoạn minh họa**. Việc <code>isDone()</code> là <code>true</code> chỉ bảo đảm không còn phải đợi để có trạng thái cuối cùng, không bảo đảm <code>join()</code> có giá trị để trả về.

Một pattern khác cũng dễ sai là kiểm tra <code>!future.isCompletedExceptionally()</code> ngay khi future còn pending rồi kết luận chắc chắn nó sẽ thành công. Lúc đó <code>isCompletedExceptionally()</code> có thể là <code>false</code> đơn giản vì **chưa có kết quả**.

## 8. Lấy kết quả: get() và join() khác nhau thế nào?

Cả <code>Future.get()</code> và <code>CompletableFuture.join()</code> đều có thể đợi kết quả, nhưng hợp đồng ngoại lệ khác nhau.

| Hoạt động | <code>get()</code> | <code>join()</code> |
| --- | --- | --- |
| Future hoàn tất bình thường | Trả giá trị <code>T</code> | Trả giá trị <code>T</code> |
| Future còn pending | Chờ completion (bản get không timeout) | Chờ completion |
| Future hoàn tất bằng lỗi thông thường | Ném checked <code>ExecutionException</code> với cause | Thường ném unchecked <code>CompletionException</code> với cause |
| Chờ bị interrupt | Có thể ném checked <code>InterruptedException</code> | Không khai báo <code>InterruptedException</code>; chờ theo chính sách không gián đoạn của join |
| Future đã cancelled | Có thể ném <code>CancellationException</code> | Có thể ném <code>CancellationException</code> |
| Chờ có thời hạn | <code>get(timeout, unit)</code> có thể ném <code>TimeoutException</code> | Không có overload timeout trực tiếp của <code>join()</code> |

**Phân biệt hai lần “cause”:** lỗi gốc được future dùng để hoàn tất có thể được bọc trong <code>CompletionException</code> khi gọi <code>join()</code>, hoặc trong <code>ExecutionException</code> khi gọi <code>get()</code>. Người xử lý cần kiểm tra <code>getCause()</code> để truy tới lỗi kỹ thuật hoặc nghiệp vụ ban đầu.

Một ví dụ minh họa:

~~~java
CompletableFuture<Integer> bad =
        CompletableFuture.failedFuture(
                new IllegalArgumentException("bad input"));

try {
    bad.get();
} catch (java.util.concurrent.ExecutionException e) {
    System.out.println(e.getCause().getClass().getSimpleName());
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
}
~~~

Đây là **đoạn minh họa nằm trong phương thức Java** có import <code>CompletableFuture</code>. Trong tình huống ví dụ, lỗi gốc là <code>IllegalArgumentException</code>. Nhánh <code>InterruptedException</code> khôi phục interrupt flag để tránh nuốt yêu cầu ngắt nếu lời gọi chờ bị ngắt.

### getNow(valueIfAbsent)

<code>future.getNow(fallback)</code> không chờ completion:

- Nếu future đã hoàn tất bình thường, trả kết quả (kể cả <code>null</code>).
- Nếu chưa hoàn tất, trả <code>fallback</code>.
- Nếu đã hoàn tất bằng ngoại lệ, nó vẫn có thể ném exception tương ứng, thay vì lặng lẽ trả fallback.

Vì vậy, <code>getNow("default")</code> **không phải** cơ chế phục hồi một future thất bại. Giá trị fallback chỉ đại diện cho trường hợp kết quả chưa sẵn sàng; nó không thay thế exception đã có. Nếu <code>fallback</code> trùng với giá trị hợp lệ, chỉ nhìn return value cũng không phân biệt chắc chắn giữa “pending” và “đã thành công với chính giá trị đó”.

## 9. Chuỗi xử lý bình thường: thenApply, thenAccept và thenRun

Một <code>CompletionStage</code> có thể tạo các stage phụ thuộc vào kết quả trước.

~~~text
source: CompletableFuture<String>
          |
          | hoàn tất bình thường với "java"
          v
thenApply(String::toUpperCase)
          |
          v
dependent: CompletableFuture<String> = "JAVA"
~~~

Với <code>thenApply(fn)</code>:

- Khi nguồn hoàn tất bình thường, hàm nhận giá trị nguồn và trả về giá trị mới để hoàn tất stage tiếp theo.
- Khi nguồn hoàn tất bằng ngoại lệ, hàm chuyển đổi thông thường **không được chạy**; dependent stage cũng hoàn tất theo đường ngoại lệ.
- Khi hàm chuyển đổi tự ném lỗi, dependent stage hoàn tất bằng ngoại lệ do hàm đó, dù source trước đó thành công.

Hai dạng tương tự:

- <code>thenAccept(consumer)</code>: chỉ chạy trên nhánh thành công để tiêu thụ giá trị; dependent stage có kiểu <code>Void</code>.
- <code>thenRun(runnable)</code>: chỉ chạy sau khi source thành công nhưng không nhận giá trị source; dependent stage cũng có kiểu <code>Void</code>.

Không được nghĩ rằng “future nguồn đã done” thì callback của <code>thenApply</code> chắc chắn đã chạy. Nếu nguồn hoàn tất lỗi, stage bình thường được bỏ qua. Việc dependent stage dùng bản <code>Async</code> có thể ảnh hưởng luồng và lịch chạy, nhưng **không thay đổi điều kiện nhánh thành công/lỗi**.

## 10. Phục hồi khi thất bại: exceptionally, handle và whenComplete

Đây là điểm phân biệt quan trọng nhất khi thiết kế pipeline có hai kết quả.

| API | Khi nguồn thành công | Khi nguồn thất bại | Kết quả stage trả về |
| --- | --- | --- | --- |
| <code>thenApply(fn)</code> | Chạy <code>fn</code> | Bỏ qua <code>fn</code> | Stage chuyển đổi dữ liệu nếu thành công |
| <code>exceptionally(fn)</code> | Không gọi <code>fn</code>, giữ kết quả | Gọi <code>fn</code> với lỗi để cung cấp giá trị thay thế | Stage có thể phục hồi bằng giá trị |
| <code>handle((value, error) -&gt; ...)</code> | Gọi với kết quả và <code>error == null</code> | Gọi với <code>error != null</code> | Stage có kết quả do hàm xử lý quyết định |
| <code>whenComplete((value, error) -&gt; ...)</code> | Gọi để quan sát, giữ kết quả bình thường nếu callback không lỗi | Gọi để quan sát, giữ failure ban đầu nếu callback không lỗi | Stage quan sát, **không tự thay lỗi bằng giá trị phục hồi** |

### 10.1. exceptionally: tạo giá trị thay thế khi lỗi

~~~java
CompletableFuture<String> recovered = original
        .exceptionally(error -> "Tài liệu dự phòng");
~~~

Đây là **mã minh họa** với <code>original</code> là <code>CompletableFuture&lt;String&gt;</code> có trước. Nếu nguồn thành công, stage mới giữ giá trị thành công; nếu nguồn lỗi, hàm cung cấp giá trị thay thế để stage mới hoàn tất bình thường.

**Không nhầm lẫn:** <code>exceptionally</code> tạo stage tiếp theo có khả năng phục hồi; nó không sửa trạng thái của future nguồn đã thất bại. Nếu các nhánh khác vẫn giữ tham chiếu tới future nguồn và gọi <code>join()</code>, nhánh đó có thể tiếp tục thấy exception ban đầu.

Nếu hàm <code>exceptionally</code> tự ném lỗi, stage phục hồi cũng hoàn tất bằng ngoại lệ mới. “Đã gắn exceptionally” không bảo đảm toàn pipeline chắc chắn thành công.

### 10.2. handle: xử lý cả hai đường

~~~java
CompletableFuture<Integer> normalized = original.handle(
        (value, error) -> error == null ? value.length() : -1);
~~~

Đây là **mã minh họa**, giả định <code>original</code> có kiểu <code>CompletableFuture&lt;String&gt;</code>. Hàm <code>handle</code> được gọi khi source hoàn tất theo bất kỳ hình thức nào:

- Thành công: <code>error == null</code>; <code>value</code> có thể là một chuỗi hoặc <code>null</code> nếu thành công hợp lệ với giá trị null. Ví dụ này giả định nguồn thành công không trả null.
- Thất bại: <code>error != null</code>; code dùng nhánh thay thế để trả <code>-1</code>.

Đừng kiểm tra đơn thuần <code>value == null</code> để suy ra lỗi, vì một future hoàn tất bình thường với <code>null</code> cũng đưa <code>null</code> vào callback.

### 10.3. whenComplete: quan sát mà không biến failure thành success

~~~java
CompletableFuture<String> observed = original.whenComplete(
        (value, error) -> {
            if (error != null) {
                recordFailure(error);
            }
        });
~~~

Đây là **mã minh họa** với <code>recordFailure</code> là hàm do ứng dụng định nghĩa. Khi <code>original</code> thất bại và callback chạy bình thường, <code>observed</code> vẫn hoàn tất bằng ngoại lệ. Nó không “nuốt” lỗi để trả một chuỗi hợp lệ.

Nếu callback của <code>whenComplete</code> ném ngoại lệ khi source trước đó thành công, dependent stage có thể hoàn tất bằng ngoại lệ callback. Nếu source đã thất bại và callback cũng ném lỗi, theo hợp đồng <code>whenComplete</code>, lỗi từ source được ưu tiên khi quyết định completion của dependent stage. Vì vậy, callback quan sát lỗi nên được thiết kế đáng tin cậy và tránh vô tình gây thêm lỗi.

### 10.4. thenCompose và exceptional completion

<code>thenCompose</code> dùng khi hàm chuyển đổi trả về một <code>CompletionStage</code> khác. Khi nguồn thất bại, hàm compose bình thường bị bỏ qua, còn dependent stage đi theo đường lỗi. Khi nguồn thành công và hàm trả về một stage bị lỗi, future kết quả cũng thất bại tương ứng.

Nếu việc phục hồi lỗi phải chạy **bất đồng bộ** và trả về một <code>CompletionStage</code> thay thế, Java 17 hỗ trợ <code>exceptionallyCompose</code> và các biến thể Async. Phương thức này khác <code>exceptionally</code> ở chỗ hàm phục hồi trả về một stage, tránh tình huống vô tình tạo future lồng nhau.

## 11. Ví dụ Java 17 độc lập: pipeline đi qua hai nhánh completion

Tạo tệp **CompletionStageRoutingDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class CompletionStageRoutingDemo {
    public static void main(String[] args) {
        CompletableFuture<String> ok =
                CompletableFuture.completedFuture("java");

        CompletableFuture<String> bad =
                CompletableFuture.failedFuture(
                        new IllegalStateException("service down"));

        AtomicInteger skippedCalls = new AtomicInteger();
        AtomicBoolean observedFailure = new AtomicBoolean();

        CompletableFuture<Integer> transformed =
                ok.thenApply(String::length);

        CompletableFuture<Integer> skipped =
                bad.thenApply(value -> {
                    skippedCalls.incrementAndGet();
                    return value.length();
                });

        CompletableFuture<Integer> recovered =
                skipped.exceptionally(error -> -1);

        CompletableFuture<Integer> handled =
                bad.handle((value, error) ->
                        error == null ? value.length() : -2);

        CompletableFuture<String> observed =
                bad.whenComplete((value, error) ->
                        observedFailure.set(error != null));

        System.out.println("Thành công thenApply: "
                + transformed.join());
        System.out.println("Lần chạy callback bị bỏ qua: "
                + skippedCalls.get());
        System.out.println("Phục hồi exceptionally: "
                + recovered.join());
        System.out.println("Xử lý handle: "
                + handled.join());
        System.out.println("whenComplete thấy lỗi: "
                + observedFailure.get());
        System.out.println("Stage nguồn vẫn lỗi: "
                + bad.isCompletedExceptionally());

        try {
            observed.join();
        } catch (CompletionException ex) {
            System.out.println("Quan sát không phục hồi: "
                    + ex.getCause().getClass().getSimpleName());
        }
    }
}
~~~

Chạy với Java 17+:

~~~bash
javac -encoding UTF-8 CompletionStageRoutingDemo.java
java CompletionStageRoutingDemo
~~~

**Stdout chính xác:**

~~~text
Thành công thenApply: 4
Lần chạy callback bị bỏ qua: 0
Phục hồi exceptionally: -1
Xử lý handle: -2
whenComplete thấy lỗi: true
Stage nguồn vẫn lỗi: true
Quan sát không phục hồi: IllegalStateException
~~~

Phân tích:

1. <code>ok</code> hoàn tất bình thường với <code>"java"</code>, nên <code>thenApply(String::length)</code> trả <code>4</code>.
2. <code>bad</code> đã hoàn tất bằng ngoại lệ. Callback trong <code>thenApply</code> của nhánh lỗi không chạy, nên <code>skippedCalls</code> vẫn bằng <code>0</code>.
3. <code>skipped</code> thất bại theo source. <code>exceptionally</code> trên <code>skipped</code> chuyển thất bại thành giá trị <code>-1</code>, nên **future recovered** hoàn tất bình thường.
4. <code>handle</code> được gọi trên nguồn lỗi, nhận <code>error != null</code> và trả <code>-2</code>. Stage <code>handled</code> hoàn tất bình thường.
5. <code>whenComplete</code> được gọi để ghi nhận rằng đã có lỗi, nhưng <code>observed</code> vẫn hoàn tất bằng ngoại lệ <code>IllegalStateException</code>.
6. <code>bad.isCompletedExceptionally()</code> vẫn là <code>true</code>: các stage phục hồi khác không thay trạng thái source.

Ví dụ sử dụng các future đã hoàn tất và callback không có độ trễ bất đồng bộ, nên không phụ thuộc vào việc các tác vụ chạy theo thứ tự nào trên thread pool. Những kết quả được in **sau khi** các phép <code>join()</code> liên quan bảo đảm stage đã hoàn tất.

## 12. Completion của một tác vụ chạy bằng Executor

Một future từ <code>supplyAsync</code> có kết quả được xác định bởi công việc bên trong supplier. Nếu supplier ném <code>RuntimeException</code>, thao tác thu thập kết quả từ future phải xử lý đường exceptional completion.

Tạo tệp **AsyncCompletionDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class AsyncCompletionDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newFixedThreadPool(2);

        try {
            CompletableFuture<Integer> good =
                    CompletableFuture.supplyAsync(() -> 20 + 22, executor);

            CompletableFuture<Integer> bad =
                    CompletableFuture.supplyAsync(() -> {
                        throw new IllegalArgumentException("bad input");
                    }, executor);

            System.out.println("Kết quả tốt: " + good.join());

            try {
                bad.join();
            } catch (CompletionException ex) {
                System.out.println("Kết quả lỗi: "
                        + ex.getCause().getClass().getSimpleName()
                        + " -> " + ex.getCause().getMessage());
            }

            System.out.println("Good exceptional: "
                    + good.isCompletedExceptionally());
            System.out.println("Bad exceptional: "
                    + bad.isCompletedExceptionally());
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
                executor.shutdownNow();
                throw new IllegalStateException("Executor không kết thúc");
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 AsyncCompletionDemo.java
java AsyncCompletionDemo
~~~

**Stdout trong điều kiện executor chạy bình thường:**

~~~text
Kết quả tốt: 42
Kết quả lỗi: IllegalArgumentException -> bad input
Good exceptional: false
Bad exceptional: true
~~~

Hai supplier có thể chạy song song và kết thúc theo thứ tự bất kỳ. Chương trình vẫn in theo thứ tự đã chọn vì <code>main</code> quan sát <code>good.join()</code> trước, sau đó mới quan sát <code>bad.join()</code> và trạng thái của chúng.

<code>shutdown()</code> yêu cầu executor ngừng nhận task mới, còn <code>awaitTermination(...)</code> chờ các task kết thúc và giúp dọn tài nguyên. Nếu xảy ra timeout bất thường trong môi trường quá tải, ví dụ ném lỗi riêng về executor và không khẳng định stdout phía trên còn đầy đủ; đó là điều kiện vận hành, không phải đường kết quả bài học đang minh họa.

Một lưu ý: <code>join()</code> trên future thất bại báo trạng thái của future, **không truyền exception theo một đường gọi đồng bộ nguyên gốc từ worker về main**. Wrapper <code>CompletionException</code> cung cấp hợp đồng quan sát kết quả bất đồng bộ.

## 13. Cancellation là một dạng hoàn tất bất thường

<code>CompletableFuture.cancel(boolean mayInterruptIfRunning)</code> đánh dấu future là đã hủy nếu có thể. Trên implementation <code>CompletableFuture</code> của Java, cancellation là một dạng exceptional completion mang <code>CancellationException</code>.

Ví dụ minh họa:

~~~java
CompletableFuture<String> future = new CompletableFuture<>();
boolean cancelled = future.cancel(true);

System.out.println(cancelled);                        // true
System.out.println(future.isDone());                  // true
System.out.println(future.isCancelled());             // true
System.out.println(future.isCompletedExceptionally()); // true
~~~

Đây là **đoạn minh họa** chưa có lời gọi hoàn tất nào trước <code>cancel(true)</code>. Lưu ý:

- <code>future.join()</code> hoặc <code>future.get()</code> trên chính future đã hủy có thể ném <code>CancellationException</code> trực tiếp. Đừng chỉ bắt <code>CompletionException</code> rồi cho rằng đã bao phủ mọi loại thất bại.
- Với <code>CompletableFuture</code>, tham số <code>mayInterruptIfRunning</code> **không dùng để điều khiển interrupt xử lý bên dưới** theo hợp đồng của implementation này. Vì thế, <code>cancel(true)</code> không bảo đảm công việc async đã dừng.
- Các dependent stage đang chờ hoàn tất bình thường có thể trở thành exceptional completion do cancellation của nguồn. Ngoại lệ quan sát ở dependent stage có thể được bọc theo đường <code>CompletionException</code>.
- Đọc <code>isCancelled()</code> chỉ cung cấp trạng thái của future, không phải một phép xác nhận tài nguyên, transaction hoặc worker đã cleanup xong.

Với một producer cần dừng công việc thật, phải thiết kế cơ chế hợp tác riêng như cờ hủy, interrupt ở luồng phù hợp hoặc quy trình dừng executor; không coi thay đổi trạng thái future là hành động cưỡng bức dừng code.

## 14. Timeout cũng có thể quyết định completion

Java 17 có hai phương thức tiện lợi được giới thiệu từ Java 9:

- <code>orTimeout(timeout, unit)</code>: nếu future chưa hoàn tất trong thời hạn, cố gắng hoàn tất **chính future đó** bằng ngoại lệ <code>TimeoutException</code>.
- <code>completeOnTimeout(value, timeout, unit)</code>: nếu chưa hoàn tất trong thời hạn, cố gắng hoàn tất **chính future đó** bình thường với giá trị dự phòng <code>value</code>.

Hai phương thức này trả về **chính CompletableFuture nhận lời gọi**, không phải một bản sao với quy tắc timeout độc lập. Chúng cạnh tranh với kết quả mà tác vụ hoặc code hoàn tất thủ công có thể cung cấp trước.

Ví dụ minh họa:

~~~java
CompletableFuture<String> slow = new CompletableFuture<>();
slow.completeOnTimeout("Giá trị dự phòng", 200,
        java.util.concurrent.TimeUnit.MILLISECONDS);
~~~

Nếu không có bên nào hoàn tất <code>slow</code> sớm hơn trong thời hạn, future sẽ hoàn tất **bình thường** với <code>"Giá trị dự phòng"</code>.

~~~java
CompletableFuture<String> another = new CompletableFuture<>();
another.orTimeout(200, java.util.concurrent.TimeUnit.MILLISECONDS);
~~~

Nếu không có bên nào hoàn tất <code>another</code> trước hạn, future sẽ hoàn tất **bằng ngoại lệ** <code>TimeoutException</code>. Tại nơi gọi <code>join()</code>, có thể thấy <code>CompletionException</code> với cause là timeout tương ứng.

**Không suy luận** rằng timeout đã chấm dứt I/O hoặc task đang chạy. Timeout chỉ ảnh hưởng completion của future theo quy tắc được công bố. Nếu tác vụ hạ tầng tiếp tục chạy và cuối cùng gọi <code>complete(...)</code>, lời gọi hoàn tất đến muộn không thay được kết quả timeout đã thắng.

Phân biệt thêm <code>get(timeout, unit)</code>: nếu thời gian chờ của **chính lời gọi get** hết, nó ném <code>TimeoutException</code> cho caller, nhưng không vì thế mà tự hoàn tất future bằng lỗi. Đây là khác biệt lớn giữa “timeout khi chờ để lấy kết quả” và “timeout được đặt lên trạng thái completion”.

## 15. Kết hợp nhiều future: allOf và anyOf

### allOf

<code>CompletableFuture.allOf(f1, f2, ...)</code> tạo một future kiểu <code>Void</code> hoàn tất khi tất cả future đầu vào đã hoàn tất. Nếu có future đầu vào hoàn tất bằng ngoại lệ, future kết hợp cũng hoàn tất bằng ngoại lệ theo hợp đồng, thay vì trả về một danh sách kết quả thành công.

~~~java
CompletableFuture<String> first =
        CompletableFuture.completedFuture("A");
CompletableFuture<Integer> second =
        CompletableFuture.completedFuture(10);

CompletableFuture<Void> combined =
        CompletableFuture.allOf(first, second);
combined.join();

String a = first.join();
Integer b = second.join();
~~~

Đây là **mã minh họa**. <code>allOf</code> không tự gom giá trị của từng future thành list; sau khi kết hợp thành công, đọc từng nguồn để thu giá trị.

Nếu một trong các nguồn lỗi, <code>combined.join()</code> có thể ném <code>CompletionException</code>. Không nên dựa vào việc nó “fail fast” tại thời điểm nguồn đầu tiên lỗi; theo hợp đồng <code>allOf</code> hoàn tất khi **tất cả các future đầu vào hoàn tất**, rồi biểu đạt exceptional completion nếu có lỗi.

### anyOf

<code>CompletableFuture.anyOf(f1, f2, ...)</code> hoàn tất khi **bất kỳ một future đầu vào hoàn tất**, dùng kết quả hoặc lỗi của future đó. Nó không có nghĩa “lấy future thành công đầu tiên”.

Nếu một future thất bại sớm hơn future thành công, <code>anyOf</code> có thể hoàn tất bằng ngoại lệ của nguồn lỗi. Muốn chính sách “ưu tiên kết quả thành công”, cần thiết kế cách chọn khác, chứ không thể chỉ đổi <code>allOf</code> thành <code>anyOf</code>.

Trong code đa luồng thật, kết quả cuộc đua phụ thuộc thứ tự completion. Không công bố stdout giả định một future nhất định thắng nếu ví dụ không có đồng bộ hóa buộc thứ tự đó.

## 16. Mô hình lỗi trong chuỗi stage: failure không tự bị nuốt

Xét pipeline:

~~~text
supplyAsync(fetchData)
    |
    +-- thành công --> thenApply(parse) --> thenApply(validate) --> kết quả
    |
    +-- thất bại --> các thenApply thông thường bị bỏ qua
                     |
                     +--> exceptionally(fallback) --> có thể phục hồi
                     |
                     +--> whenComplete(log) --> vẫn báo lỗi
~~~

Cần lưu ý các đặc điểm:

1. **Mỗi bước trả về một stage mới.** Nếu giữ tham chiếu tới source thất bại, gọi <code>source.join()</code> vẫn báo lỗi dù một nhánh con đã hồi phục.
2. **Lỗi trong callback được ghi vào stage do callback tạo.** Một <code>thenApply</code> nhận giá trị thành công nhưng tự ném <code>NumberFormatException</code> sẽ khiến stage mới lỗi; source trước đó vẫn có thể thành công.
3. **Exception propagation có thể được bọc trong <code>CompletionException</code>.** Khi xử lý sâu trong chuỗi, kiểm tra cause một cách có kiểm soát, tránh mặc định mọi throwable đều là cùng một class gốc.
4. **Phục hồi chỉ xảy ra khi code chủ động cung cấp kết quả hợp lệ.** Một giá trị mặc định như <code>0</code>, chuỗi rỗng hoặc <code>null</code> không phải lúc nào cũng là cách biểu diễn thất bại đúng cho hợp đồng API.
5. **Stage Async vẫn có thể lỗi.** Việc chạy callback trên executor khác không đổi tính chất thành công hay thất bại; nó chỉ thay đổi thời điểm và môi trường thực thi callback.

Một mẫu lựa chọn hợp đồng là phục hồi các lỗi có thể dự kiến, còn lỗi không thể phục hồi tiếp tục lan truyền:

~~~java
CompletableFuture<String> recovered = source.exceptionally(error -> {
    if (isRecoverable(error)) {
        return cachedValue();
    }
    throw new IllegalStateException("Không thể phục hồi", error);
});
~~~

Đây là **đoạn mã minh họa**, giả định <code>source</code>, <code>isRecoverable</code> và <code>cachedValue</code> đã tồn tại, và kiểu dữ liệu phù hợp. Ở nhánh recoverable, dependent stage hoàn tất bình thường. Ở nhánh khác, nó hoàn tất lỗi bằng <code>IllegalStateException</code> có cause để chẩn đoán.

Trước khi viết <code>isRecoverable</code>, cần biết ngoại lệ nhận được có thể là wrapper <code>CompletionException</code>. Không phân loại lỗi bằng cách so sánh một chuỗi <code>getMessage()</code> dễ thay đổi; nên dựa vào loại lỗi và contract cụ thể.

## 17. Luồng thực thi callback và thời điểm completion

Một câu hỏi phổ biến: “Callback <code>thenApply</code> có luôn chạy trên worker đã hoàn tất source không?”

Không. Theo chính sách thực thi của <code>CompletableFuture</code>, các dependent action **không có hậu tố <code>Async</code>** có thể được thực thi bởi luồng hoàn tất future hoặc một caller khác tham gia quá trình completion. Các action **có hậu tố <code>Async</code>** được gửi tới executor tương ứng, mặc định hoặc do bạn cung cấp.

Điều này có hai hệ quả:

- Không dựa vào tên thread, thời điểm in log hoặc thứ tự callback độc lập để xác định state của future. Dùng API completion hoặc các cơ chế đồng bộ phù hợp.
- Không đặt tác vụ blocking nặng hoặc thao tác có side effect không kiểm soát trong callback mà bạn tưởng chắc chắn chạy ở background executor. Cân nhắc dùng phiên bản Async với executor quản lý rõ ràng.

Tuy nhiên, dù callback chạy trên luồng nào, **mối quan hệ logic vẫn vậy**: <code>thenApply</code> chỉ thực hiện khi source hoàn tất bình thường; <code>handle</code> thực hiện với cả success/error; <code>exceptionally</code> phục hồi nhánh lỗi.

Đối với workflow cần báo cho client một kết quả duy nhất, nên chọn một stage đầu ra rõ ràng và quan sát completion của chính stage đó, tránh nhiều thread cùng ghi một biến “trạng thái” không được đồng bộ hóa.

## 18. Những hiểu nhầm và lỗi phổ biến

### 18.1. isDone() bằng true nghĩa là thành công

Sai. Future lỗi và bị hủy cũng là done. Dùng <code>join()</code>/<code>get()</code> để lấy kết quả theo hợp đồng, hoặc kiểm tra thêm trạng thái/thiết kế callback xử lý lỗi.

### 18.2. completeExceptionally() ném exception ngay cho caller

Sai. Nó hoàn tất future với trạng thái lỗi; nếu muốn caller thấy exception, caller cần quan sát future qua API hoặc stage phù hợp. Chính lời gọi <code>completeExceptionally(error)</code> thông thường trả boolean.

### 18.3. complete() luôn ghi đè kết quả cũ

Sai. Completion thông thường chỉ có một lần thắng. <code>complete</code> đến sau trả <code>false</code>. Không sử dụng <code>obtrudeValue</code> để vá một thiết kế producer cạnh tranh không rõ ràng.

### 18.4. getNow(fallback) biến mọi lỗi thành fallback

Sai. Nó chỉ trả fallback khi future **chưa hoàn tất**. Future đã lỗi vẫn có thể ném exception khi gọi.

### 18.5. exceptionally làm future nguồn thành công lại

Sai. Nó tạo dependent stage có thể hoàn tất thành công bằng giá trị thay thế. Future nguồn vẫn giữ trạng thái lỗi và các nhánh khác vẫn có thể quan sát lỗi đó.

### 18.6. whenComplete nuốt lỗi vì đã chạy callback

Sai. <code>whenComplete</code> quan sát, còn exceptional completion của nguồn thường tiếp tục tới dependent stage. Nếu cần chuyển failure thành giá trị, dùng <code>exceptionally</code> hoặc <code>handle</code> theo hợp đồng.

### 18.7. null có nghĩa là lỗi hoặc chưa xong

Sai. <code>CompletableFuture.completedFuture(null)</code> là normal completion. Nếu muốn biết lỗi trong <code>handle</code>, kiểm tra tham số <code>error</code>, không chỉ giá trị <code>value</code>.

### 18.8. join() và get() ném cùng một ngoại lệ

Sai. <code>get()</code> có checked exception như <code>InterruptedException</code> và <code>ExecutionException</code>; <code>join()</code> biểu diễn lỗi hoàn tất thông thường qua unchecked <code>CompletionException</code>. Cả hai có thể trực tiếp báo <code>CancellationException</code> khi future đã hủy.

### 18.9. cancel(true) luôn interrupt và dừng task

Sai đối với <code>CompletableFuture</code>. Trạng thái future đã hủy không bảo đảm supplier đang chạy dừng; tham số interrupt của phương thức này không điều khiển worker theo cách một số cách triển khai <code>FutureTask</code> làm.

### 18.10. allOf trả danh sách kết quả

Sai. Nó trả <code>CompletableFuture&lt;Void&gt;</code>. Cần đọc kết quả ở từng future nguồn sau khi nhóm hoàn tất bình thường.

### 18.11. anyOf luôn lấy một thành công

Sai. Future đầu tiên hoàn tất có thể kết thúc bằng ngoại lệ; <code>anyOf</code> có thể lỗi ngay theo kết quả đó.

### 18.12. Timeout luôn làm tác vụ nền dừng

Sai. <code>orTimeout</code> hoặc <code>completeOnTimeout</code> quyết định **state của future** khi hết hạn; không tự đảm bảo task hay I/O đã được hủy.

## 19. Kiểm thử cần xác nhận gì?

Khi viết unit test hoặc integration test cho completion, hãy tách **trạng thái future**, **giá trị/lỗi quan sát được** và **hành vi dependent stage**.

| Trường hợp | Kiểm tra |
| --- | --- |
| Future mới tạo | <code>isDone() == false</code> |
| <code>complete(value)</code> lần đầu | Trả <code>true</code>; <code>join()</code> trả đúng giá trị |
| <code>complete</code> lần thứ hai | Trả <code>false</code>; giá trị trước không đổi |
| <code>completeExceptionally(original)</code> | Trả <code>true</code> nếu đang pending; future hoàn tất lỗi |
| <code>complete</code> sau exceptional completion | Trả <code>false</code>; lỗi trước còn nguyên |
| <code>join()</code> trên lỗi thông thường | Ném <code>CompletionException</code> có cause phù hợp |
| <code>get()</code> trên lỗi thông thường | Ném <code>ExecutionException</code> có cause phù hợp |
| Future hoàn tất thành công với <code>null</code> | <code>isDone() == true</code>, <code>isCompletedExceptionally() == false</code> |
| <code>thenApply</code> trên nguồn lỗi | Callback bình thường không chạy; dependent stage lỗi |
| <code>exceptionally</code> trả fallback | Dependent stage thành công, source vẫn lỗi |
| <code>whenComplete</code> quan sát lỗi | Callback được gọi; lỗi không bị tự động xóa |
| <code>cancel</code> trước completion | Future chuyển sang trạng thái hủy; đọc kết quả báo cancellation |

Ví dụ kiểm tra cause trong JUnit 5 (đoạn **minh họa trong lớp test đã có dependency JUnit 5 và import phù hợp**):

~~~java
IllegalArgumentException original =
        new IllegalArgumentException("bad id");

CompletableFuture<String> failed = new CompletableFuture<>();
boolean updated = failed.completeExceptionally(original);

assertTrue(updated);
assertTrue(failed.isDone());
assertTrue(failed.isCompletedExceptionally());

CompletionException thrown =
        assertThrows(CompletionException.class, failed::join);
assertSame(original, thrown.getCause());
~~~

Đoạn này kiểm tra **đúng đối tượng cause**, không chỉ so sánh class hoặc message. Với Java 17 và JUnit 5, các assertion tương ứng thuộc <code>org.junit.jupiter.api.Assertions</code>. Không trình bày đoạn trên như chương trình Java standalone vì cần lớp kiểm thử và dependency JUnit.

Trong kiểm thử đồng thời, hãy dùng <code>CountDownLatch</code>, các future để điều phối hoặc API có thời hạn; tránh phụ thuộc vào thứ tự thread chạy “may mắn”. Với một cuộc đua giữa normal và exceptional completion, khẳng định rằng **chỉ một completion thắng**, thay vì luôn đòi một nhánh cụ thể thắng nếu chưa thiết lập thứ tự.

## 20. Checklist khi thiết kế API trả về CompletableFuture

Trước khi phát hành phương thức trả <code>CompletableFuture&lt;T&gt;</code>, hãy tự hỏi:

1. **Giá trị thành công là gì?** <code>null</code> có hợp lệ không; có nên dùng một kiểu dữ liệu diễn đạt rõ “không có kết quả” không?
2. **Ngoại lệ có ý nghĩa với bên gọi là gì?** Một lỗi kỹ thuật có cần được chuyển thành ngoại lệ tầng API và giữ cause không?
3. **Ai chịu trách nhiệm hoàn tất?** Producer nào gọi <code>complete</code>/<code>completeExceptionally</code>; có nguy cơ nhiều producer cạnh tranh không?
4. **Ai chịu trách nhiệm quan sát?** Bên gọi dùng <code>get()</code>, <code>join()</code> hay đăng ký một dependent stage?
5. **Có nhánh phục hồi thực sự không?** Nếu dùng <code>exceptionally</code>/<code>handle</code>, giá trị fallback có còn đúng hợp đồng nghiệp vụ không?
6. **Có stage chỉ để ghi log không?** Dùng <code>whenComplete</code> và hiểu rằng nó không tự biến lỗi thành thành công.
7. **Timeout và cancellation có ý nghĩa gì?** Trạng thái future có đủ để xác nhận task đã dừng hoặc tài nguyên đã được giải phóng không?
8. **Cần kiểm soát executor không?** Callback blocking có được chuyển sang executor phù hợp không?
9. **Khi kết hợp nhiều future**, cần chờ tất cả, chờ một completion đầu tiên hay chọn kết quả thành công đầu tiên theo chính sách riêng?
10. **Kiểm thử đã bao phủ cả hai loại completion** và các stage phụ thuộc, kể cả <code>null</code>, cancellation, timeout và lỗi trong callback chưa?

**Ghi nhớ:** một <code>CompletableFuture</code> đã hoàn tất có thể mang **giá trị thành công** hoặc **trạng thái lỗi**. Hai trạng thái đều làm <code>isDone()</code> thành <code>true</code>, nhưng chúng dẫn tới các nhánh callback và cách quan sát hoàn toàn khác. Thiết kế tốt cần xác định rõ ai hoàn tất future, ai xử lý ngoại lệ, khi nào phục hồi bằng giá trị và khi nào giữ lỗi để bên gọi quyết định.