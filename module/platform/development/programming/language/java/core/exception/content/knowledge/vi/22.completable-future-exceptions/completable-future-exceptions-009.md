# allOf, anyOf và giới hạn khi cần thu thập mọi thất bại — CompletableFuture (Java 17+)

## 1. Mục tiêu và phạm vi

Bài học giúp bạn:

- Phân biệt chính xác khi nào <code>CompletableFuture.allOf(...)</code> và <code>CompletableFuture.anyOf(...)</code> hoàn tất.
- Hiểu sự khác nhau giữa “mọi future đã kết thúc” và “mọi future đã thành công”.
- Nhận ra rằng <code>allOf</code> **không trả danh sách giá trị** và **không gom toàn bộ Throwable** từ những future thất bại.
- Hiểu <code>anyOf</code> chọn **completion xảy ra trước**, dù completion đó thành công, thất bại hay bị hủy.
- Tạo một collector dùng <code>handle</code> để nhận đầy đủ từng kết quả hoặc từng lỗi, bảo toàn đối tượng Throwable và thứ tự nguồn.
- Thiết kế chính sách cho lỗi đến muộn, timeout, cancellation, nguồn không hoàn tất và input rỗng.
- Kiểm thử các tình huống trên bằng ví dụ Java 17 có đầu ra không phụ thuộc lịch chạy của thread.

Trong Java, <code>CompletableFuture&lt;T&gt;</code> vừa biểu diễn một kết quả tương lai, vừa hỗ trợ các stage xử lý tiếp theo. Nó có thể **chưa hoàn tất**, **hoàn tất bình thường** với giá trị kiểu <code>T</code> (kể cả <code>null</code>), hoặc **hoàn tất bằng ngoại lệ**. Một future bị hủy cũng được tính là đã hoàn tất bất thường theo cơ chế của <code>CompletableFuture</code>.

## 2. Hai toán tử kết hợp có hai câu hỏi khác nhau

~~~java
CompletableFuture<Void> all =
        CompletableFuture.allOf(first, second, third);

CompletableFuture<Object> any =
        CompletableFuture.anyOf(first, second, third);
~~~

Đây là đoạn **minh họa**, giả định có ba biến nguồn kiểu <code>CompletableFuture&lt;?&gt;</code> và import <code>java.util.concurrent.CompletableFuture</code>.

| Phương thức | Câu hỏi được trả lời | Kiểu kết quả | Nếu có lỗi |
| --- | --- | --- | --- |
| <code>allOf(f1, f2, ...)</code> | **Tất cả** future nguồn đã hoàn tất hay chưa? | <code>CompletableFuture&lt;Void&gt;</code> | Hoàn tất bằng ngoại lệ nếu ít nhất một future nguồn thất bại |
| <code>anyOf(f1, f2, ...)</code> | Đã có **một** future nguồn hoàn tất hay chưa? | <code>CompletableFuture&lt;Object&gt;</code> | Nếu nguồn thắng hoàn tất lỗi, future kết hợp cũng lỗi |
| Bộ gom outcome do ứng dụng định nghĩa | Mỗi nguồn hoàn tất **như thế nào**? | Ví dụ <code>CompletableFuture&lt;List&lt;Outcome&lt;T&gt;&gt;&gt;</code> | Lưu từng lỗi thành dữ liệu để kiểm tra toàn bộ |

<code>allOf</code> thường được dùng như **hàng rào hoàn tất** (*completion barrier*). <code>anyOf</code> thường được dùng như **cuộc đua hoàn tất** (*completion race*). Hai khái niệm đó không đồng nghĩa với phép gom giá trị, thu thập lỗi hay tự động chọn kết quả thành công tốt nhất.

~~~text
Nguồn 1: SUCCESS("A") ----------+
                                 |
Nguồn 2: FAILURE(error) ---------+---- allOf: đợi tất cả, kết quả là lỗi
                                 |
Nguồn 3: SUCCESS("C") -----------+

Nguồn 1: ------- SUCCESS("A")
Nguồn 2: -- FAILURE(error)             <- hoàn tất đầu tiên
Nguồn 3: ----- SUCCESS("C")
anyOf:    -- FAILURE(error)            <- không chờ thành công
~~~

## 3. allOf: tất cả đã hoàn tất, không nhất thiết tất cả thành công

Theo hợp đồng, <code>CompletableFuture.allOf</code> trả một future mới hoàn tất khi **toàn bộ** future đầu vào hoàn tất. Mỗi đầu vào được xem là đã hoàn tất dù nó thành công, lỗi hoặc bị hủy.

Nếu tất cả nguồn thành công, future kết hợp hoàn tất bình thường với giá trị <code>null</code> thuộc kiểu <code>Void</code>. Nếu **bất kỳ** nguồn nào hoàn tất bằng ngoại lệ, future kết hợp hoàn tất bằng ngoại lệ.

### 3.1. Kết quả bình thường không chứa các giá trị thành phần

~~~java
CompletableFuture<String> name =
        CompletableFuture.completedFuture("An");
CompletableFuture<Integer> count =
        CompletableFuture.completedFuture(3);

CompletableFuture<Void> barrier =
        CompletableFuture.allOf(name, count);

barrier.join();
System.out.println(name.join() + ": " + count.join());
~~~

Đây là mã minh họa đặt trong một phương thức có import phù hợp. Giá trị in ra là <code>An: 3</code>. <code>barrier.join()</code> trả <code>null</code> vì nó chỉ xác nhận rằng các nguồn đã hoàn tất bình thường. Muốn lấy giá trị thành phần, phải đọc chính các future nguồn.

Nếu nguồn thành công với <code>null</code>, điều đó vẫn được tính là **normal completion**. Không được dùng phép kiểm tra <code>value == null</code> để khẳng định đã thất bại.

### 3.2. Một nguồn lỗi không làm allOf kết thúc ngay

Giả sử nguồn A đã thất bại nhưng nguồn B còn pending:

~~~text
A: FAILURE ------------ done=true
B: chưa hoàn tất ------- done=false
allOf(A,B): chờ -------- done=false
~~~

<code>allOf</code> **không** cam kết “fail fast” ngay khi một nguồn báo lỗi. Nó chờ mọi future đầu vào hoàn tất trước khi có completion của chính nó. Nếu một nguồn không bao giờ hoàn tất, gọi <code>allOf(...).join()</code> có thể đợi vô thời hạn dù nguồn khác đã lỗi.

Điểm này quan trọng khi gom lỗi: việc chờ tất cả có thể cho thời gian để ghi nhận toàn bộ failure, nhưng cần chính sách timeout hoặc nguồn hủy nếu không thể chờ vô hạn.

### 3.3. Nhiều nguồn lỗi không tạo một danh sách lỗi tự động

Giả sử ba nguồn đều thất bại:

- Nguồn A ném <code>IllegalArgumentException</code>.
- Nguồn B ném <code>IllegalStateException</code>.
- Nguồn C ném một ngoại lệ truy cập dữ liệu riêng của ứng dụng.

<code>allOf(A,B,C).join()</code> báo lỗi theo cơ chế <code>CompletionException</code>. Tuy nhiên, API không cung cấp phương thức kiểu <code>allOf.getAllErrors()</code> để truy ra cả ba exception. Future kết hợp có **một exceptional completion**; không nên mặc định lỗi được nêu ở cause là lỗi đầu tiên theo thời gian, lỗi cuối cùng, lỗi quan trọng nhất hoặc mọi lỗi.

Nếu cần toàn bộ failure, hãy **giữ tham chiếu đến các future nguồn** và thu kết quả từ từng nguồn sau khi chúng đã done, hoặc chuyển mỗi nguồn sang outcome chứa value/error rồi dùng <code>allOf</code> trên các outcome future đó.

Cũng không được giả định <code>CompletionException.getSuppressed()</code> trên kết quả <code>allOf</code> đã tự gom những ngoại lệ bị bỏ sót. <code>allOf</code> không có hợp đồng hứa hẹn tập suppressed exceptions tương ứng với mọi nguồn.

### 3.4. Gom giá trị chỉ khi tất cả thành công

~~~java
CompletableFuture<Void> barrier = CompletableFuture.allOf(a, b, c);

CompletableFuture<List<String>> values = barrier.thenApply(ignored ->
        List.of(a.join(), b.join(), c.join()));
~~~

Đây là **mã minh họa** với ba future kiểu <code>CompletableFuture&lt;String&gt;</code> và import <code>java.util.List</code>. Khi barrier thành công, ba nguồn đã thành công và callback có thể lấy kết quả. Nhưng nếu barrier lỗi, <code>thenApply</code> sẽ **bị bỏ qua** và <code>values</code> cũng thất bại.

Ngoài ra, <code>List.of</code> không chấp nhận null. Nếu một future thành công với null, callback sẽ ném <code>NullPointerException</code> dù tất cả nguồn đã hoàn tất bình thường. Vì vậy đoạn này chỉ minh họa cách gom dữ liệu khi biết giá trị không null; nó **không** phải collector tổng quát của mọi outcome.

## 4. anyOf: completion đầu tiên có thể là lỗi

<code>CompletableFuture.anyOf</code> hoàn tất khi **bất kỳ một** future nguồn hoàn tất. Future kết hợp nhận kết quả thành công hoặc trạng thái lỗi từ nguồn thắng cuộc.

Ví dụ:

~~~java
CompletableFuture<String> fastError = new CompletableFuture<>();
CompletableFuture<String> slowSuccess = new CompletableFuture<>();

CompletableFuture<Object> first =
        CompletableFuture.anyOf(fastError, slowSuccess);

fastError.completeExceptionally(
        new IllegalStateException("Lỗi sớm"));
slowSuccess.complete("Thành công muộn");
~~~

Đây là **mã minh họa**, trong đó lần hoàn tất được gọi tuần tự theo đúng thứ tự. Future <code>first</code> đã hoàn tất bằng ngoại lệ của <code>fastError</code>. Thành công của <code>slowSuccess</code> đến sau không thay kết quả của <code>first</code>.

**anyOf không có nghĩa “nguồn thành công đầu tiên”.** Nếu muốn bỏ qua các lỗi xuất hiện sớm và chỉ dùng kết quả thành công, phải viết logic điều phối riêng.

### anyOf không dừng các nguồn thua cuộc

<code>anyOf</code> trả kết quả trước không đồng nghĩa những future nguồn khác bị hủy hoặc các tác vụ gắn với chúng tự dừng. Chúng có thể tiếp tục hoàn thành, tạo side effect hoặc gặp lỗi về sau.

Nếu ứng dụng dùng <code>anyOf</code> cho hai cuộc gọi dịch vụ, cần quyết định:

- Có cần duy trì và ghi nhận lỗi từ nguồn về sau không?
- Những lời gọi đang chạy có thể hủy an toàn hay không?
- Nếu nguồn thắng lỗi, có chuyển sang chờ nguồn khác thành công hay báo lỗi ngay?
- Phải đóng tài nguyên nào sau khi không còn cần kết quả?
- Có thể có tác dụng phụ đã được thực hiện dù future nguồn bị hủy không?

Không xem <code>anyOf</code> là cơ chế quản lý vòng đời mọi công việc nền.

## 5. Ví dụ Java 17 độc lập: so sánh trực tiếp allOf và anyOf

Lưu tệp **AllAnyDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class AllAnyDemo {
    public static void main(String[] args) {
        CompletableFuture<String> a = new CompletableFuture<>();
        CompletableFuture<String> b = new CompletableFuture<>();
        CompletableFuture<String> c = new CompletableFuture<>();

        CompletableFuture<Void> all =
                CompletableFuture.allOf(a, b, c);
        CompletableFuture<Object> any =
                CompletableFuture.anyOf(a, b, c);

        b.completeExceptionally(
                new IllegalStateException("B failed"));

        System.out.println("any.isDone: " + any.isDone());
        System.out.println("all.isDone khi A/C pending: " + all.isDone());

        try {
            any.join();
        } catch (CompletionException e) {
            System.out.println("any lỗi: "
                    + e.getCause().getClass().getSimpleName());
        }

        a.complete("A");
        c.completeExceptionally(
                new IllegalArgumentException("C failed"));

        System.out.println("all.isDone sau A/C: " + all.isDone());
        System.out.println("all.isCompletedExceptionally: "
                + all.isCompletedExceptionally());

        try {
            all.join();
        } catch (CompletionException e) {
            System.out.println("all có cause: "
                    + (e.getCause() != null));
        }

        System.out.println("A lỗi: " + a.isCompletedExceptionally());
        System.out.println("B lỗi: " + b.isCompletedExceptionally());
        System.out.println("C lỗi: " + c.isCompletedExceptionally());
    }
}
~~~

Biên dịch/chạy bằng Java 17+:

~~~bash
javac -encoding UTF-8 AllAnyDemo.java
java AllAnyDemo
~~~

**Stdout chính xác:**

~~~text
any.isDone: true
all.isDone khi A/C pending: false
any lỗi: IllegalStateException
all.isDone sau A/C: true
all.isCompletedExceptionally: true
all có cause: true
A lỗi: false
B lỗi: true
C lỗi: true
~~~

Diễn giải:

1. Ngay khi B hoàn tất bằng ngoại lệ, <code>anyOf</code> có lỗi, trong khi <code>allOf</code> còn pending vì A/C chưa xong.
2. <code>any.join()</code> ném <code>CompletionException</code> chứa lỗi của B.
3. Sau khi A thành công và C lỗi, cả ba nguồn đã done. Khi đó <code>all</code> hoàn tất bằng ngoại lệ.
4. Ví dụ chỉ kiểm tra <code>all</code> có cause, **không giả định** allOf phải chọn B hay C làm lỗi đại diện.
5. Đọc trạng thái từng nguồn cho biết hai lỗi tồn tại cùng lúc. Nếu chương trình chỉ nhìn lỗi của <code>all</code>, thông tin chi tiết về cả B và C sẽ không được tự động tổng hợp.

Chương trình không tạo thread nền: thứ tự <code>complete</code> được xác định ngay trong <code>main</code>, nên đầu ra không bị ảnh hưởng bởi lịch chạy ngẫu nhiên.

## 6. Vì sao không thể “thu mọi thất bại” chỉ bằng allOf.join()

Khi hàng chục tác vụ cùng chạy, yêu cầu “thu mọi lỗi” khác với yêu cầu “báo thất bại nếu có bất kỳ lỗi nào”.

~~~text
Hành vi cần thiết           allOf thuần túy
----------------------     -----------------------------
Đợi tất cả nguồn            Có
Biết có ít nhất một lỗi     Có, qua exceptional completion
Trả về List kết quả         Không
Trả về List mọi Throwable   Không
Giữ ID của từng nguồn       Không tự động
Phân biệt lỗi và thành công null  Không tự động
Tự hủy công việc treo       Không
~~~

Một cách thực hiện thủ công là đợi các nguồn đã done rồi kiểm tra từng future riêng bằng <code>join()</code> trong <code>try/catch</code>. Nhưng nếu code chỉ đặt một <code>try/catch</code> bao quanh **toàn bộ vòng lặp**, nó có thể dừng ngay ở nguồn lỗi đầu tiên và không thăm những nguồn sau.

Một cách dễ bảo trì hơn là chuyển từng future nguồn thành một future **hoàn tất bình thường với dữ liệu outcome**, rồi dùng <code>allOf</code> làm hàng rào. Bộ gom sẽ không phụ thuộc cơ chế chọn lỗi đại diện của allOf.

## 7. Thiết kế Outcome: biến thất bại thành dữ liệu để gom

Định nghĩa đơn giản:

~~~java
record Outcome<T>(boolean success, T value, Throwable error) {}
~~~

Một outcome đại diện cho kết quả của **một nguồn**:

- <code>success=true, value="OK", error=null</code>: thành công với giá trị.
- <code>success=true, value=null, error=null</code>: thành công với null; vẫn là **thành công**.
- <code>success=false, value=null, error=someThrowable</code>: thất bại, giữ đối tượng Throwable.

Khi một future thất bại, callback <code>handle</code> vẫn được chạy:

~~~java
CompletableFuture<Outcome<String>> outcome = source.handle(
        (value, error) -> new Outcome<>(error == null, value, error));
~~~

Đây là **đoạn minh họa**, giả định <code>source</code> có kiểu <code>CompletableFuture&lt;String&gt;</code> và <code>Outcome</code> đã định nghĩa. Nếu callback tạo Outcome và trả bình thường, future <code>outcome</code> **thành công** với đối tượng Outcome, dù source thất bại. Nhờ vậy các future outcome có thể được gom bằng <code>allOf</code> mà không làm mất lỗi nguồn.

### Không làm phức tạp callback capture

Callback capture nên chỉ đọc <code>value</code>/<code>error</code> và tạo dữ liệu. Nếu callback tự ném lỗi (ví dụ vì gọi một bộ chuyển đổi dữ liệu hỏng), future outcome cũng có thể thất bại. Khi đó, <code>allOf</code> của các outcome có thể lỗi vì **collector**, làm hỏng mục tiêu thu thập mọi nguồn.

Để có độ tin cậy cao, tách riêng:

1. Capture completion của nguồn.
2. Đợi mọi outcome.
3. Trình bày/log/ánh xạ outcome theo hợp đồng nghiệp vụ.

Không thực hiện network call hoặc formatting phức tạp trong bước capture.

### Throwable có thể đã được bọc

Trong <code>handle((value, error) -&gt; ...)</code>, <code>error</code> là <code>Throwable</code> nhìn thấy tại stage nguồn đó. Nếu lỗi đã đi qua các dependent stage, đối tượng nhận được có thể là <code>CompletionException</code> mang cause là lỗi thấp hơn.

Collector nên **giữ nguyên đối tượng lỗi** để còn cause chain, stack trace và suppressed exceptions. Việc quyết định hiển thị loại nào hay tìm root cause nên để tầng chẩn đoán riêng thực hiện. Không nên biến exception thành một chuỗi <code>getMessage()</code> rồi làm mất thông tin.

## 8. Ví dụ Java 17 độc lập: thu cả giá trị lẫn mọi lỗi

Tạo tệp **CollectOutcomesDemo.java**:

~~~java
import java.util.List;
import java.util.concurrent.CompletableFuture;

public class CollectOutcomesDemo {
    record Outcome<T>(boolean success, T value, Throwable error) {}

    static <T> CompletableFuture<Outcome<T>> capture(
            CompletableFuture<T> source) {
        return source.handle((value, error) ->
                new Outcome<>(error == null, value, error));
    }

    static <T> CompletableFuture<List<Outcome<T>>> collect(
            List<CompletableFuture<T>> sources) {
        List<CompletableFuture<Outcome<T>>> observed =
                sources.stream()
                       .map(CollectOutcomesDemo::capture)
                       .toList();

        CompletableFuture<Void> barrier = CompletableFuture.allOf(
                observed.toArray(CompletableFuture[]::new));

        return barrier.thenApply(ignored ->
                observed.stream()
                        .map(CompletableFuture::join)
                        .toList());
    }

    public static void main(String[] args) {
        List<CompletableFuture<String>> sources = List.of(
                CompletableFuture.completedFuture("OK"),
                CompletableFuture.failedFuture(
                        new IllegalArgumentException("bad ID")),
                CompletableFuture.failedFuture(
                        new IllegalStateException("service unavailable")),
                CompletableFuture.completedFuture(null));

        List<Outcome<String>> outcomes = collect(sources).join();

        for (int i = 0; i < outcomes.size(); i++) {
            Outcome<String> result = outcomes.get(i);
            if (result.success()) {
                System.out.println(i + ": SUCCESS "
                        + String.valueOf(result.value()));
            } else {
                Throwable error = result.error();
                System.out.println(i + ": FAIL "
                        + error.getClass().getSimpleName()
                        + " -> " + error.getMessage());
            }
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 CollectOutcomesDemo.java
java CollectOutcomesDemo
~~~

**Stdout chính xác:**

~~~text
0: SUCCESS OK
1: FAIL IllegalArgumentException -> bad ID
2: FAIL IllegalStateException -> service unavailable
3: SUCCESS null
~~~

### Từng bước thực thi

1. Danh sách chứa bốn nguồn đã hoàn tất. Hai nguồn thành công, hai nguồn thất bại.
2. <code>capture</code> đăng ký một callback <code>handle</code> cho mỗi nguồn, tạo đúng một Outcome.
3. Những callback đó chỉ xây dựng record nên tương ứng bốn future outcome hoàn tất bình thường.
4. <code>allOf</code> trên bốn future outcome hoàn tất bình thường khi cả bốn outcome sẵn sàng.
5. <code>thenApply</code> chạy sau barrier và đọc lần lượt các outcome; không cần block thêm vì barrier đã hoàn tất.
6. <code>stream().toList()</code> trên nguồn có thứ tự giữ encounter order. Dữ liệu được in theo **thứ tự đầu vào**, không cần đoán nguồn nào chạy trước.
7. Mỗi outcome thất bại giữ lại <code>Throwable</code> của chính nguồn đó. Do vậy không mất một trong hai lỗi chỉ vì <code>allOf</code> có một exceptional completion đại diện.
8. Kết quả <code>SUCCESS null</code> thể hiện rõ rằng null không tự động đồng nghĩa thất bại.

Đây là mẫu cơ sở để gom lỗi, nhưng trong ứng dụng thực tế thường cần thêm một <code>sourceId</code> hoặc thông tin thao tác tương ứng từng outcome. Nếu đầu vào đến từ nhiều dịch vụ khác nhau, trả về lỗi theo chỉ số 0..N có thể khó đọc khi danh sách thay đổi.

## 9. Chính sách sau khi gom: partial success, all-or-nothing và best effort

Sau khi nhận <code>List&lt;Outcome&lt;T&gt;&gt;</code>, API có thể cần chọn một trong những hợp đồng:

| Hợp đồng | Ý nghĩa | Cách xử lý outcome |
| --- | --- | --- |
| **Partial success** | Mỗi nguồn độc lập; kết quả thành công vẫn hữu ích | Trả dữ liệu thành công kèm lỗi từng nguồn |
| **All-or-nothing** | Kết quả tổng hợp chỉ hợp lệ nếu mọi nguồn thành công | Thu mọi lỗi rồi báo một thất bại tổng hợp có thông tin các lỗi thành phần |
| **Best effort** | Dùng mọi kết quả có thể, ghi nhận những nguồn hỏng | Trả dữ liệu khả dụng và quan sát lỗi phù hợp |

Collector chỉ có trách nhiệm **giữ dữ liệu hoàn tất**, không tự quyết định lỗi nào chấp nhận được. Tầng nghiệp vụ mới quyết định một nguồn thiếu dữ liệu có khiến yêu cầu tổng thể thất bại hay không.

Nếu chọn all-or-nothing, có thể tạo một exception tổng hợp do ứng dụng sở hữu, chứa danh sách lỗi với ID nguồn. Hoặc dùng <code>addSuppressed</code> một cách có chủ đích để giữ các failure phụ, nhưng cần hiểu rằng <code>Throwable</code> chỉ có một cause trực tiếp và suppressed không phải một chức năng tự động của <code>allOf</code>. Thiết kế exception tổng hợp phải phục vụ nhu cầu caller, không ép mọi client xử lý bằng cách phân tích message.

Nếu chỉ chọn một ngoại lệ đại diện, hãy quy định cách chọn (chẳng hạn độ ưu tiên nghiệp vụ hoặc thứ tự nguồn), thay vì dựa vào lỗi mà <code>allOf</code> tình cờ báo.

## 10. Tránh lẫn lộn future lỗi, hủy và timeout

### Cancellation

~~~java
CompletableFuture<String> f = new CompletableFuture<>();
f.cancel(true);

System.out.println(f.isDone());                   // true
System.out.println(f.isCancelled());              // true
System.out.println(f.isCompletedExceptionally()); // true
~~~

Đoạn trên là **mã minh họa**. Cancellation là một hình thức hoàn tất bất thường. Một source hủy có thể khiến <code>allOf</code> cuối cùng hoàn tất bằng ngoại lệ, hoặc khiến <code>anyOf</code> hoàn tất bằng ngoại lệ nếu nó thắng cuộc đua.

Khi đọc trực tiếp future đã hủy bằng <code>join()</code>, có thể thấy <code>CancellationException</code>. Dependent stage có thể nhận/báo completion lỗi đã được bọc. Nếu collector cần phân biệt trạng thái hủy với thất bại nghiệp vụ, nên lưu trạng thái riêng thay vì gộp mọi <code>Throwable</code> vào một thông báo giống nhau.

Đối với <code>CompletableFuture</code>, <code>cancel(true)</code> **không dùng cờ true để cưỡng bức interrupt** công việc đang chạy theo cách mọi triển khai Future có thể làm. Không xem <code>isCancelled()</code> là bằng chứng luồng nền đã dừng hoặc cleanup hoàn tất.

### Timeout

- <code>orTimeout(timeout, unit)</code> hoàn tất **chính future được gọi** bằng <code>TimeoutException</code> nếu nó còn pending sau thời hạn.
- <code>completeOnTimeout(value, timeout, unit)</code> hoàn tất chính future đó bình thường với giá trị dự phòng nếu nó còn pending sau thời hạn.
- <code>get(timeout, unit)</code> chỉ giới hạn **lần chờ của caller**; nếu timeout, lời gọi <code>get</code> ném <code>TimeoutException</code> nhưng không tự biến future đang pending thành future lỗi.

Các trường hợp này không giống nhau. Nếu cần gom mọi outcome trong thời hạn, phải định nghĩa rõ lúc hết hạn sẽ ghi lỗi timeout, trạng thái “chưa có kết quả” hay một giá trị dự phòng. Không mặc định timeout đã dừng computation, HTTP request hay I/O nền.

### Source pending mãi

Nếu một source không bao giờ hoàn tất, <code>allOf</code> và bộ gom outcome dựa trên nó cũng có thể chờ vô thời hạn. Muốn trả kết quả cuối cùng trong một khoảng thời gian, phải có chính sách deadline hoặc timeout với các nguồn; không thể kỳ vọng <code>allOf</code> tự động giải phóng sự chờ đợi.

## 11. allOf và anyOf với đầu vào rỗng hoặc null

~~~java
CompletableFuture<Void> emptyAll = CompletableFuture.allOf();
CompletableFuture<Object> emptyAny = CompletableFuture.anyOf();
~~~

Hai trường hợp có hành vi khác:

- <code>allOf()</code> không có nguồn nào nên hoàn tất **bình thường ngay** với giá trị <code>null</code>.
- <code>anyOf()</code> không có nguồn để cung cấp completion, nên future trả về **chưa hoàn tất**. Gọi <code>emptyAny.join()</code> có thể chờ vô thời hạn nếu không có nơi nào chủ động hoàn tất future đó.

Khi một danh sách nguồn có thể rỗng, ứng dụng phải quy định kết quả riêng. Chẳng hạn bộ gom ở ví dụ trên có thể trả danh sách outcome rỗng thông qua <code>allOf</code> rỗng, còn logic dùng <code>anyOf</code> cần xử lý sớm đầu vào rỗng để tránh chờ mãi.

Một future **hoàn tất bình thường với null** là hợp lệ. Vì thế <code>anyOf</code> có thể nhận <code>null</code> của nguồn thắng; riêng giá trị null không cho biết tên nguồn hoặc có lỗi hay không. Nếu cần biết nguồn thắng, hãy ánh xạ giá trị nguồn sang record có nhãn trước khi đua.

Tham số future null trong mảng truyền tới <code>allOf/anyOf</code> không phải một future nguồn hợp lệ; không dùng null như phần tử đại diện cho nhiệm vụ “chưa có” trong mảng.

## 12. “Thành công đầu tiên” là bài toán khác anyOf

Giả sử yêu cầu là:

> Gọi ba nguồn đồng thời; bỏ qua những lỗi đến sớm, trả về kết quả thành công đầu tiên; nếu cả ba đều thất bại, báo đủ mọi lỗi.

Đây là hai quy tắc bổ sung: **first-success** và **aggregate-failure**. Chỉ gọi <code>anyOf</code> không đủ vì một failure có thể thắng sớm.

Một hướng thiết kế ở mức thuật toán:

1. Tạo <code>CompletableFuture&lt;T&gt; result</code> đại diện kết quả chung.
2. Gắn <code>whenComplete</code> hoặc callback phù hợp lên từng nguồn.
3. Nếu nguồn thành công, thử <code>result.complete(value)</code>; chỉ một completion thành công có hiệu lực.
4. Nếu nguồn thất bại, ghi lỗi kèm source ID vào cấu trúc đồng bộ hóa.
5. Nếu **mọi nguồn đã thất bại** và <code>result</code> vẫn pending, tạo lỗi tổng hợp từ tất cả failure rồi thử <code>completeExceptionally</code>.
6. Dự liệu race giữa nhiều callback và chọn cấu trúc thread-safe để lưu lỗi, đếm completion, tránh báo lỗi quá sớm.
7. Quy định số phận những nguồn còn chạy sau khi tìm được thành công, bao gồm dừng, timeout, cleanup và lỗi đến muộn.

Một biến thể đơn giản là dùng collector trong mục 8, đợi mọi nguồn hoàn tất rồi chọn một outcome thành công. Biến thể đó **thu được mọi lỗi**, nhưng không trả kết quả sớm theo thời gian; không được gọi nó là first-success về hiệu năng.

Nếu nguồn có tác dụng phụ, không giả định “nguồn thua cuộc” có thể bị hủy an toàn. Kết quả Future và tình trạng thực thi/commit dữ liệu của hệ bên dưới cần được quản lý riêng.

## 13. Lỗi từ callback collector khác lỗi của nguồn

Một source thất bại và một callback thu thập thất bại là hai nguyên nhân khác nhau.

Ví dụ:

~~~java
CompletableFuture<String> source =
        CompletableFuture.failedFuture(
                new IllegalArgumentException("source failure"));

CompletableFuture<Integer> badCollector = source.handle(
        (value, error) -> {
            throw new IllegalStateException("collector failure");
        });
~~~

Đây là **mã minh họa**. <code>badCollector</code> mang exceptional completion của **callback**. Nếu sau đó dùng <code>allOf(badCollector, ...)</code>, future tổng hợp vẫn có thể lỗi, nhưng đó là lỗi xử lý outcome chứ không nhất thiết là một failure bổ sung ở hệ nguồn.

Vì vậy, collector cơ bản nên đơn giản và tránh gọi code không kiểm soát. Muốn báo cáo hay chuyển lỗi sang định dạng phức tạp, hãy thực hiện ở tầng sau khi dữ liệu outcome đã tập hợp xong; xử lý lỗi của tầng báo cáo như một loại sự cố riêng.

Không dùng <code>exceptionally(error -&gt; null)</code> bừa bãi chỉ để khiến mọi future thành công, vì cách đó đánh mất nguyên nhân và còn lẫn lộn với kết quả thành công null. Một Outcome có trường trạng thái là cơ chế rõ ràng hơn.

## 14. Kiểm thử: xác định completion bằng thao tác thủ công

Để kiểm thử allOf/anyOf, ưu tiên tạo <code>new CompletableFuture&lt;&gt;()</code>, rồi chủ động gọi <code>complete</code>/<code>completeExceptionally</code> theo thứ tự mong muốn. Đây là cách chứng minh ngữ nghĩa mà không dựa vào may rủi từ scheduler.

| Kịch bản | Kỳ vọng |
| --- | --- |
| Hai nguồn đều thành công | <code>allOf</code> thành công sau khi cả hai done |
| Một nguồn lỗi, nguồn khác pending | <code>allOf</code> chưa done; <code>anyOf</code> có thể lỗi nếu nguồn đó là winner |
| Hai nguồn đều lỗi | <code>allOf</code> báo lỗi nhưng không tự trả đủ hai exception |
| Hai source lỗi được bọc bằng <code>handle</code> | Collector có đúng hai outcome lỗi |
| Một source thành công null | Outcome thành công riêng biệt với lỗi |
| Một source hủy | Trạng thái completion bất thường được ghi nhận |
| Một source treo mãi | <code>allOf</code> có thể pending cho tới khi có completion/timeout |
| Mảng nguồn rỗng | <code>allOf</code> thành công ngay, <code>anyOf</code> pending |
| Source hoàn tất sớm bằng lỗi | <code>anyOf</code> chọn lỗi, không tự đợi thành công |
| Callback capture ném ngoại lệ | Kiểm tra lỗi riêng của collector thay vì gán nhầm cho nguồn |

Đoạn JUnit 5 **minh họa** sau giả định có lớp <code>CollectOutcomesDemo</code> và các import/thư viện JUnit thích hợp:

~~~java
CompletableFuture<String> first = new CompletableFuture<>();
CompletableFuture<String> second = new CompletableFuture<>();

CompletableFuture<List<CollectOutcomesDemo.Outcome<String>>> collected =
        CollectOutcomesDemo.collect(List.of(first, second));

IllegalArgumentException e1 = new IllegalArgumentException("one");
IllegalStateException e2 = new IllegalStateException("two");

first.completeExceptionally(e1);
assertFalse(collected.isDone());

second.completeExceptionally(e2);
List<CollectOutcomesDemo.Outcome<String>> data = collected.join();

assertEquals(2, data.size());
assertFalse(data.get(0).success());
assertFalse(data.get(1).success());
assertSame(e1, data.get(0).error());
assertSame(e2, data.get(1).error());
~~~

Các assertion từ <code>org.junit.jupiter.api.Assertions</code>; cần import <code>List</code>, <code>CompletableFuture</code> và JUnit. Mục tiêu của ví dụ là chứng minh collector **đợi đủ hai nguồn** và giữ nguyên **đối tượng Throwable**, không chỉ cùng class/message.

Nếu test với các tác vụ async thật, hãy có giới hạn thời gian và cleanup tài nguyên để tránh làm cả suite treo vì một future không bao giờ kết thúc. Timeout của kiểm thử không thay thế việc xác nhận đúng số lỗi đã thu thập.

## 15. Những lỗi thiết kế phổ biến

1. **Cho rằng allOf fail fast:** nó chờ mọi nguồn hoàn tất, kể cả khi đã có một nguồn lỗi.
2. **Chỉ in exception từ allOf.join():** có thể bỏ sót các failure khác.
3. **Mặc định allOf chọn lỗi đầu tiên/quan trọng nhất:** không có quy tắc public đảm bảo thứ tự như vậy.
4. **Tưởng allOf trả List:** kiểu trả là <code>CompletableFuture&lt;Void&gt;</code>.
5. **Gom bằng thenApply sau allOf rồi mong xử lý failure:** thenApply bị bỏ qua khi source lỗi.
6. **Dùng anyOf như first-success:** một exception sớm vẫn có thể thắng cuộc đua.
7. **Quên các tác vụ còn chạy sau anyOf:** lỗi và tác dụng phụ đến muộn có thể không được quản lý.
8. **Gom lỗi thành chuỗi message:** mất type, cause, stack trace và danh tính nguồn.
9. **Dùng null làm dấu hiệu thất bại:** normal completion cũng có thể chứa null.
10. **Dùng List.of để gom giá trị có thể null:** có thể gây NullPointerException mới trong callback.
11. **Không xử lý danh sách nguồn rỗng:** <code>anyOf()</code> không có nguồn nào để hoàn tất.
12. **Nhầm cancellation với việc thread đã dừng:** <code>cancel(true)</code> không tự bảo đảm task nền đã chấm dứt.
13. **Đặt timeout vào future chia sẻ mà không xem tác động:** <code>orTimeout</code> có thể thay trạng thái future đó.
14. **Callback capture quá phức tạp:** collector có thể ném lỗi mới, làm lu mờ failure nguồn.
15. **Đồng nhất mọi lỗi với cùng một loại:** có thể cần phân biệt lỗi nghiệp vụ, hạ tầng, timeout và cancellation.
16. **Kiểm thử dựa vào thứ tự thread:** kết quả race không xác định nếu không chủ động điều phối.
17. **Không gắn ID nguồn:** khó giải thích cho người dùng vì sao từng dịch vụ thất bại.
18. **Bỏ qua cơ chế bảo mật thông tin lỗi:** stack trace/cause có thể chứa thông tin nội bộ không nên đưa ra API response.

## 16. Checklist áp dụng

Khi thiết kế API dùng nhiều <code>CompletableFuture</code>, hãy kiểm tra:

- Có cần **đợi tất cả** hay chỉ cần **completion đầu tiên**?
- Một completion lỗi đến trước có được phép chấm dứt yêu cầu tổng thể không?
- Bên gọi cần **một lỗi đại diện** hay danh sách **tất cả lỗi**?
- Nếu cần đầy đủ, có giữ được outcome riêng cho từng nguồn, kể cả thành công-null?
- Có yêu cầu thứ tự ổn định và ID nguồn rõ ràng không?
- Callback capture có đảm bảo đơn giản, không phát sinh lỗi riêng ngoài ý muốn không?
- Có chính sách cho source pending mãi, deadline, timeout và cancellation không?
- Khi anyOf hoàn tất, ai quản lý nguồn còn chạy và lỗi/tác dụng phụ đến muộn?
- Có phân biệt trạng thái future với việc tác vụ nền thật sự kết thúc không?
- Test có kiểm tra nhiều lỗi đồng thời, lỗi sớm, null, danh sách rỗng và trường hợp pending không?

**Ghi nhớ:** <code>allOf</code> xác định **khi mọi nguồn hoàn tất**, còn <code>anyOf</code> xác định **khi một nguồn hoàn tất trước**. Chúng không tự gom các exception thành phần. Khi cần báo cáo đầy đủ mọi thất bại, hãy dùng <code>handle</code> chuyển từng completion thành một outcome chứa value và Throwable, kết hợp tất cả outcome rồi mới áp chính sách trả kết quả theo hợp đồng của ứng dụng.