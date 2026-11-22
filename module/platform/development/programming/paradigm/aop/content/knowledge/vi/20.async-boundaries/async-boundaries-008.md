# Xác định rõ điểm kết thúc hành vi được advice bao quanh

## 1. Vấn đề cốt lõi: “trả về” và “hoàn tất” là hai sự kiện khác nhau

Trong lập trình hướng khía cạnh (Aspect-Oriented Programming, AOP), **advice** là hành vi cắt ngang được áp dụng tại một **join point** (điểm thực thi có thể can thiệp), thường được chọn bằng **pointcut**. Với một phương thức đồng bộ, việc phương thức trả về hoặc ném ngoại lệ thường cũng là lúc công việc mà người gọi chờ đã kết thúc. Vì vậy, advice đo thời gian, ghi log hoặc dọn dẹp tài nguyên quanh lời gọi có vẻ tự nhiên.

Với phương thức bất đồng bộ, giả định ấy không còn đúng. Phương thức có thể **trả về ngay một đối tượng đại diện cho kết quả tương lai**, trong khi công việc thực tế vẫn đang chạy hoặc thậm chí chưa bắt đầu. Advice cần xác định mình quan sát sự kiện nào, thay vì gọi chung tất cả là “kết thúc”.

Có ít nhất ba ranh giới cần phân biệt:

1. **Kết thúc lượt thực thi tại join point:** phương thức/đoạn được intercept đã trả về một giá trị hoặc đã ném ngoại lệ đồng bộ. Đây là ranh giới mặc định của advice bao quanh một lời gọi hoặc thực thi phương thức.
2. **Kết thúc thao tác bất đồng bộ theo hợp đồng API:** đối tượng kết quả phát tín hiệu hoàn tất thành công, thất bại hoặc hủy; đối với luồng nhiều phần tử là sự kiện kết thúc của từng lượt tiêu thụ/đăng ký.
3. **Kết thúc toàn bộ tác động phụ và vòng đời tài nguyên:** tác vụ phụ, ghi log nền, gửi thông báo, đóng kết nối, giải phóng tài nguyên… có thể tiếp diễn sau khi kết quả chính hoàn tất. Không được tự đồng nhất ranh giới này với hai ranh giới trên.

**Nguyên tắc:** advice mặc định bao quanh *thực thi join point*; chỉ khi có thiết kế quan sát kết quả bất đồng bộ riêng mới có thể nói advice theo dõi *vòng đời logic của tác vụ*.

## 2. Nhìn trên dòng thời gian

Ví dụ một phương thức bắt đầu công việc nền rồi trả về một đối tượng kiểu CompletionStage:

~~~text
Luồng gọi:
t0  -> advice trước proceed()
t1  -> bắt đầu gọi phương thức đích
t2  -> phương thức đích trả về CompletionStage (có thể chưa hoàn tất)
t3  -> proceed() trả về; advice sau-return/around chạy xong
t4  -> người gọi nhận CompletionStage
          ...
t5  -> công việc bất đồng bộ hoàn tất hoặc thất bại
t6  -> callback theo dõi completion được kích hoạt
~~~

Khoảng **t1–t3** là thời gian thực thi phương thức bị bao quanh. Khoảng **t1–t5** gần hơn với thời gian của *tác vụ logic*, nếu t1 thật sự là lúc tác vụ bắt đầu. Hai khoảng này đo hai thứ khác nhau.

Dòng thời gian trên minh họa trường hợp thường gặp, không phải thứ tự bắt buộc. Một tác vụ rất nhanh có thể hoàn tất **trước khi** phương thức trả về. Khi đó đối tượng được trả về đã hoàn tất sẵn; tuy vậy, việc trả về và việc completion vẫn là hai sự kiện có ý nghĩa độc lập.

### Điểm then chốt về proceed()

Trong around advice, lời gọi **proceed()** chuyển quyền điều khiển sang hành vi được bao quanh và sau đó trả lại điều khiển cho advice theo ngữ nghĩa của cơ chế AOP đang dùng. Nếu hành vi ấy chỉ *khởi tạo* một tác vụ rồi trả về handle, proceed() **không tự chờ** tác vụ đó xong.

Tương tự, advice loại **after returning** thường nhận *giá trị trả về* (ví dụ CompletionStage chưa hoàn tất), còn **after throwing** bắt được ngoại lệ được ném *trong lần thực thi join point*. Chúng không tự động chuyển thành callback nhận kết quả cuối cùng của một tác vụ bất đồng bộ. Advice kiểu **after/finally** cũng kết thúc theo lượt thực thi join point, kể cả khi có công việc nền đang tiếp diễn.

## 3. Phải xác định “kết thúc” theo hợp đồng trả về

| Hình thức API | Khi nào lần gọi phương thức kết thúc? | Khi nào công việc logic có thể coi là kết thúc? | Điều advice cần làm nếu muốn theo dõi đến cùng |
| --- | --- | --- | --- |
| Trả về giá trị đồng bộ | Khi trả về/throw | Thông thường tại cùng ranh giới | Advice thông thường là đủ nếu không có tác vụ phụ |
| CompletionStage hoặc CompletableFuture | Khi trả về đối tượng stage/future | Khi stage đại diện kết quả đã hoàn tất thành công hoặc ngoại lệ | Gắn hành động quan sát completion, xử lý cả lỗi |
| Future cổ điển | Khi trả về Future | Khi Future hoàn tất/hủy theo hợp đồng của nó | Cần cơ chế thông báo/giám sát riêng; Future thông thường không có callback completion |
| API callback | Khi phương thức đăng ký/lên lịch xong và trả về | Khi callback hợp đồng báo kết quả cuối | Bao quanh callback hoặc điểm phát kết quả, không chỉ hàm đăng ký |
| Java Flow.Publisher | Khi trả về Publisher | Theo từng subscription: kết thúc với onComplete, onError hoặc bị cancel; phải phân biệt cancel với terminal signal | Theo dõi vòng đời mỗi subscription và yêu cầu hủy |
| Gửi công việc không trả về handle | Khi enqueue/start xong hoặc khi throw đồng bộ | Không xác định đáng tin từ lời gọi ban đầu | Thiết kế API có handle/tín hiệu hoàn tất hoặc instrument ở điểm chạy thật |

Đối với API phát nhiều kết quả, một lần **trả về Publisher không đồng nghĩa đã chạy**: publisher có thể bắt đầu tạo dữ liệu khi có subscriber (cold), hoặc đã phát dữ liệu trước đó (hot). Một publisher có thể có nhiều subscription với các thời điểm kết thúc khác nhau. Đừng ghi một bản ghi “tác vụ hoàn tất” duy nhất tại lần trả về publisher.

Không nên suy ra vòng đời logic chỉ từ kiểu dữ liệu. Ví dụ, stage A có thể báo “đã gửi yêu cầu đến hàng đợi”, còn stage B báo “nghiệp vụ đã được xử lý”; A và B có tiêu chí completion khác nhau. **Hợp đồng của phương thức** mới xác định stage nào là kết quả cần quan sát.

## 4. Ví dụ Java 17+: chứng minh hai ranh giới là độc lập

Ví dụ sau là một wrapper viết bằng Java thuần **mô phỏng ngữ nghĩa quan sát của around advice**, giúp chạy thử mà không cần trình dệt AOP. Nó cố tình trả về future chưa hoàn tất để thứ tự in ra rõ ràng.

Tạo tệp **AsyncBoundaryDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.function.Supplier;

public class AsyncBoundaryDemo {
    static CompletableFuture<String> around(
            Supplier<CompletableFuture<String>> invocation) {
        System.out.println("advice: before");

        // Tương đương gọi hành vi đích/proceed().
        CompletableFuture<String> future = invocation.get();

        // Dòng này chạy ngay sau khi phương thức đích trả về future.
        System.out.println("advice: after return, done=" + future.isDone());

        // Theo dõi lần hoàn tất của future, không chặn người gọi.
        future.whenComplete((value, failure) -> {
            try {
                if (failure == null) {
                    System.out.println("advice: async success=" + value);
                } else {
                    System.out.println("advice: async failure");
                }
            } catch (RuntimeException observerFailure) {
                // Lỗi ở telemetry/log không được làm đổi kết quả nghiệp vụ.
            }
        });

        // Giữ nguyên future của nghiệp vụ.
        return future;
    }

    public static void main(String[] args) {
        CompletableFuture<String> pending = new CompletableFuture<>();

        CompletableFuture<String> returned = around(() -> {
            System.out.println("target: returning a future");
            return pending;
        });

        System.out.println("caller: received future");
        pending.complete("OK");
        System.out.println("caller: value=" + returned.join());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac AsyncBoundaryDemo.java
java AsyncBoundaryDemo
~~~

Kết quả:

~~~text
advice: before
target: returning a future
advice: after return, done=false
caller: received future
advice: async success=OK
caller: value=OK
~~~

Ở đây **after return** xuất hiện khi future còn pending. Sự kiện **async success** xảy ra khi hoàn tất future. Việc gọi complete() trong main khiến ví dụ chạy ổn định, không phụ thuộc vào lịch thread. Trong ứng dụng thật, completion thường xảy ra trên thread khác.

Lưu ý: whenComplete tạo ra **một stage phụ thuộc mới**; ví dụ cố ý chỉ dùng nó làm observer và **trả về future gốc**. Callback whenComplete không có hậu tố Async có thể chạy ngay trên thread hoàn tất future hoặc trong những ngữ cảnh thực thi được CompletableFuture cho phép; không được mặc định rằng nó chạy trên một thread riêng.

## 5. Ba kiểu thất bại phải được báo cáo khác nhau

### 5.1. Throw đồng bộ trước khi trả về handle

~~~java
CompletableFuture<String> load() {
    throw new IllegalArgumentException("invalid request");
}
~~~

Không có future nào được trả về. Advice bao quanh lần thực thi có thể thấy ngoại lệ ở nhánh throw đồng bộ; không thể gắn completion callback lên giá trị trả về vì giá trị đó không tồn tại.

### 5.2. Trả về handle rồi hoàn tất lỗi

~~~java
CompletableFuture<String> load() {
    CompletableFuture<String> result = new CompletableFuture<>();
    result.completeExceptionally(
            new IllegalStateException("remote service failed"));
    return result;
}
~~~

Lần gọi phương thức **trả về bình thường** dù kết quả đã đánh dấu thất bại. After-returning advice thấy một future; after-throwing advice của lần gọi này không thấy IllegalStateException như một throw đồng bộ. Observer completion phải kiểm tra nhánh failure. Lỗi có thể được bọc, ví dụ trong CompletionException, tùy cách hoàn tất và cách người gọi lấy kết quả.

### 5.3. Hủy hoặc timeout

Hủy thường được biểu diễn như một trạng thái hoàn tất đặc biệt. Với CompletableFuture, cancel(...) làm future hoàn tất ngoại lệ bằng CancellationException; nó **không đảm bảo dừng công việc đang chạy**. Timeout do tầng nào đặt ra cũng cần được xác định: đó có thể là việc làm future hoàn tất lỗi, hủy việc chờ, hoặc chỉ có một bên quan sát ngừng quan tâm trong khi tác vụ gốc tiếp tục.

Nên phân loại outcome tối thiểu thành **success**, **failure**, **cancel** và **timeout** khi hợp đồng cung cấp đủ tín hiệu để phân biệt. Tránh ghi “success” chỉ vì phương thức đã trả về một future.

## 6. Hai cách thiết kế around advice và đánh đổi

### A. Chỉ quan sát completion; trả về đúng handle ban đầu

Hành vi khái quát:

~~~text
on join-point entry:
    ghi thời điểm bắt đầu
    gọi proceed()
    nếu proceed ném lỗi đồng bộ -> ghi lỗi -> ném lại
    nếu nhận handle:
        gắn observer khi handle completion
        trả về chính handle đó cho người gọi
~~~

Ưu điểm: thường giữ được danh tính đối tượng, cách các bên dùng handle và đường truyền cancellation của đối tượng gốc. Phù hợp cho telemetry/log thuần quan sát.

Giới hạn: việc gắn observer cũng là một tác động có thể nhìn thấy về tài nguyên/lịch chạy; observer chậm hoặc ném lỗi có thể ảnh hưởng hiệu năng hoặc một stage phụ thuộc do nó tạo ra. Mọi thao tác quan sát phải nhanh, an toàn ngoại lệ và không được vô tình giữ tham chiếu lớn quá lâu. Nếu API không cho phép callback, không thể tự tuyên bố đã theo dõi completion.

### B. Trả về một stage đã được biến đổi hoặc bọc lại

Có thể dùng composition để thêm bước cần hoàn tất **trước khi** người gọi nhận trạng thái kết quả cuối cùng, chẳng hạn một bước xử lý kết quả mang ý nghĩa nghiệp vụ.

~~~text
stage gốc -> xử lý bổ sung -> stage mới được trả về
~~~

Khi trả về stage mới, điều này **thay đổi hợp đồng quan sát được**: thời điểm completion, cách lỗi lan truyền, danh tính handle, hành vi hủy, thậm chí kiểu cụ thể của đối tượng trả về có thể khác. Không được bọc lại chỉ để đo số liệu mà chưa kiểm tra hợp đồng. Một phương thức khai báo trả về lớp con cụ thể của Future hoặc CompletableFuture có thể không chấp nhận stage biến đổi thuộc kiểu khác.

**Quy tắc chọn:** nếu chỉ cần số liệu về hoàn tất, ưu tiên quan sát có kiểm soát; nếu cần biến đổi kết quả hoặc ràng buộc bước xử lý bổ sung, thiết kế và kiểm thử hợp đồng của stage trả về như một thay đổi hành vi thực sự.

## 7. Điều gì nằm trong phạm vi được advice bao quanh?

Điểm bắt đầu và kết thúc phải đi cùng **loại join point** và **điều kiện pointcut**:

- Với join point kiểu **method execution**, ranh giới trực tiếp là lượt chạy thân phương thức, kể cả khi thân phương thức chỉ lập lịch một công việc khác.
- Với join point kiểu **method call**, ranh giới là thao tác gọi được instrument ở vị trí gọi, với các ngữ nghĩa cụ thể tùy trình dệt AOP. Nó cũng không tự bao trùm toàn bộ tác vụ được tạo ra.
- Với advice quanh callback, tác vụ con hoặc hàm thực sự thực thi nền, có thể quan sát được *một ranh giới khác*. Nhưng ranh giới đó cần được định nghĩa và chọn rõ; không phải hệ quả tự động của pointcut trên hàm khởi tạo.

Có hai mô hình trách nhiệm thường dùng:

**Mô hình 1 – đo lời gọi:** Tên metric phải phản ánh thời gian tạo/lấy handle, ví dụ invocation duration. Điểm kết thúc là return/throw của join point. Đây là lựa chọn đúng khi mục đích là đo overhead của hàm lập lịch hoặc adapter.

**Mô hình 2 – đo tác vụ logic:** Tên metric phản ánh thời gian từ lúc bắt đầu thao tác đến completion theo hợp đồng, ví dụ operation duration. Advice khởi tạo phép đo lúc bắt đầu và đăng ký observer phù hợp lên handle. Điểm kết thúc là terminal outcome đã xác định, không phải lần return ban đầu.

Một hệ thống có thể dùng cả hai metric, nhưng phải đặt tên và mô tả sao cho không trộn chúng trong cùng một đồ thị.

## 8. Các điểm nâng cao dễ làm sai

### 8.1. Một phương thức có thể khởi tạo nhiều tác vụ

Nếu phương thức khởi tạo ba tác vụ rồi trả về stage tổng hợp, lời gọi kết thúc khi stage tổng hợp được **trả về**. Tác vụ logic kết thúc khi **stage tổng hợp hoàn tất** theo phép tổng hợp đã chọn. Ví dụ allOf hoàn tất khi tất cả các future thành phần đã hoàn tất; nếu có thành phần hoàn tất ngoại lệ, future tổng hợp hoàn tất ngoại lệ theo đặc tả của allOf. Không suy từ completion của một tác vụ con rằng toàn bộ nghiệp vụ đã hoàn tất.

Tác vụ chạy nền không nằm trong stage tổng hợp có thể tiếp tục chạy ngay cả sau khi stage tổng hợp đã complete. Nếu yêu cầu phải chờ tác vụ đó, hợp đồng kết quả cần bao gồm nó.

### 8.2. Completion có thể xảy ra trước hoặc ngay trong lúc đăng ký observer

Không xây thiết kế dựa trên thứ tự giả định “return trước, callback sau”. Với stage đã hoàn tất sẵn, khi đăng ký callback thì callback có thể chạy ngay. Dùng cơ chế đăng ký completion chính thức của API để tránh race giữa kiểm tra trạng thái và đăng ký. Mẫu “nếu chưa done thì mới đăng ký callback” có thể đánh mất kết quả nếu trạng thái đổi giữa hai bước.

### 8.3. Context không tự đi theo thread

Thông tin như correlation ID, trace context, người khởi tạo thao tác hay thời điểm bắt đầu có thể được lưu trong đối tượng context phù hợp. Nếu lưu duy nhất trong ThreadLocal rồi đọc ở completion callback, callback chạy trên thread khác có thể không có giá trị đó. Capture dữ liệu cần thiết ở ranh giới ban đầu và truyền/khôi phục context một cách tường minh theo cơ chế runtime sử dụng. Đừng giả định after-advice và completion callback luôn dùng chung thread.

### 8.4. Không giữ tài nguyên theo lifetime sai

Ví dụ: mở tài nguyên trước proceed(), trả về future rồi đóng trong finally ngay sau proceed(). Nếu công việc nền còn dùng tài nguyên ấy, nó có thể bị đóng quá sớm. Ngược lại, gắn đóng tài nguyên vào completion callback nhưng không xử lý nhánh throw đồng bộ, hủy và timeout có thể gây rò rỉ.

Phải hỏi **ai sở hữu tài nguyên** và **sự kiện nào chứng minh không còn ai dùng nó**. Không buộc dọn dẹp theo completion nếu tác vụ phụ vẫn cần tài nguyên, cũng không kéo dài lifetime chỉ vì đo thời gian.

### 8.5. Chặn chờ bên trong advice có thể làm hỏng thiết kế

Gọi get(), join() hoặc một cơ chế block tương đương ngay trong around advice để “đợi cho xong” có thể làm mất tính bất đồng bộ, tốn thread, gây bế tắc khi runtime cần chính thread đang bị chặn để hoàn tất kết quả, hoặc làm sai timeout kỳ vọng. Theo dõi completion nên dùng cơ chế thông báo/composition phù hợp thay vì ép blocking.

### 8.6. Lỗi của instrumentation phải có chính sách riêng

Lỗi ghi log/metrics không nên tự biến một kết quả nghiệp vụ thành thất bại ngoài ý muốn. Nếu observer ném lỗi, các stage phụ thuộc có thể hoàn tất lỗi dù future nguồn không lỗi. Nếu hệ thống cố ý yêu cầu bước bổ sung là điều kiện bắt buộc, phải mô tả rõ rằng đó là thay đổi hợp đồng, thay vì coi nó chỉ là “log vô hại”.

### 8.7. Một thao tác có thể tạo nhiều ranh giới theo tầng

Ví dụ: enqueue thành công, worker bắt đầu, xử lý chính hoàn tất, dữ liệu được xác nhận bền vững, callback hậu xử lý hoàn tất. Mỗi sự kiện có ý nghĩa khác nhau. Advice tại hàm enqueue chỉ biết chắc enqueue đã được xác nhận theo hợp đồng của hàm đó. Muốn đo “nghiệp vụ bền vững” phải lấy tín hiệu xác nhận thích hợp.

## 9. Cách xác định ranh giới đúng khi thiết kế một aspect

Trước khi viết pointcut và advice, lần lượt trả lời các câu hỏi:

1. **Join point nào được bao quanh?** Một lần gọi, thực thi phương thức, callback hay điểm xử lý nền?
2. **Đầu vào và đầu ra của phương thức là gì?** Giá trị đồng bộ, CompletionStage, Future, Publisher, callback, hay fire-and-forget?
3. **Tín hiệu nào chứng minh mục tiêu đã kết thúc?** Return/throw, completion thành công/thất bại, onComplete/onError, cancel, hay xác nhận từ hệ thống bên ngoài?
4. **Ai phát tín hiệu ấy?** Chính phương thức, executor, một thread khác, subscriber, hoặc tầng lưu trữ?
5. **Có thể có nhiều tín hiệu không?** Nhiều subscription, retry, tác vụ con, lệnh gọi lại, hoặc cùng thao tác được theo dõi ở nhiều aspect?
6. **Ngoại lệ đồng bộ và thất bại bất đồng bộ được ghi nhận thế nào?** Cần hai đường xử lý riêng và đúng một kết quả cuối mỗi thao tác logic.
7. **Quan sát có làm đổi hành vi không?** Kiểm tra việc block, bọc future, lan truyền cancellation, ngoại lệ observer, context và thời gian giữ tài nguyên.
8. **Metric/log thể hiện thời lượng nào?** Invocation duration và end-to-end operation duration phải có nhãn riêng, có điểm bắt đầu và kết thúc được mô tả rõ.

Có thể lập bảng thiết kế ngắn trước khi triển khai:

| Mục tiêu | Start | End | Outcome |
| --- | --- | --- | --- |
| Đo thời gian lời gọi phương thức | Trước proceed() | Ngay sau return hoặc throw đồng bộ | Returned / synchronous failure |
| Đo xử lý async bằng CompletionStage | Trước khi khởi tạo thao tác | Stage hợp đồng hoàn tất | Success / exceptional / cancellation, phân loại thêm timeout nếu biết |
| Theo dõi xử lý Publisher | Tại subscription (hoặc điểm bắt đầu phù hợp) | Theo mỗi subscription: terminal signal hoặc cancel | Complete / error / cancel |
| Theo dõi công việc gửi vào queue | Theo mốc nghiệp vụ được chọn | Acknowledgement tương ứng từ queue/worker | Accepted / processed / durable… đúng theo hợp đồng |

## 10. Các lỗi thường gặp và cách sửa

**Lỗi 1: ghi “hoàn thành tác vụ” trong after-returning advice của một hàm trả về future.** Ở thời điểm đó chỉ biết hàm đã trả về handle. Sửa bằng cách đổi tên sự kiện thành “handle returned” hoặc theo dõi terminal completion của handle.

**Lỗi 2: bắt throw đồng bộ rồi cho rằng đã bao phủ mọi lỗi.** Một future có thể hoàn tất ngoại lệ sau đó. Sửa bằng cách xử lý riêng throw trước return và failure tại completion; cần cơ chế tránh đếm hai lần nếu instrumentation bao phủ nhiều tầng.

**Lỗi 3: dùng finally của around advice để đóng tài nguyên mà async work vẫn sử dụng.** Sửa bằng chính sách sở hữu tài nguyên theo vòng đời thực và xử lý đủ các đường kết thúc.

**Lỗi 4: thêm join() vào advice để có thể log kết quả cuối.** Sửa bằng callback/composition phi chặn; blocking chỉ được dùng khi chính hợp đồng gọi yêu cầu chờ đồng bộ và đã đánh giá ảnh hưởng.

**Lỗi 5: coi cancellation là success hoặc khẳng định đã dừng worker.** Sửa bằng phân loại cancellation riêng và xác nhận ngữ nghĩa hủy thực tế của API.

**Lỗi 6: trả về stage khác mà không xem xét tương thích.** Sửa bằng cách đối chiếu chữ ký, kiểu runtime, danh tính handle, propagation của lỗi/hủy và thời điểm complete.

**Lỗi 7: giả định có một completion duy nhất cho Publisher.** Sửa bằng đơn vị đo theo subscription, vì mỗi subscriber có vòng đời riêng; cancel cũng cần ghi nhận dù không có terminal callback.

## 11. Tình huống tự kiểm tra

**Tình huống A.** Một phương thức trả về CompletableFuture sau 2 ms; sau 500 ms future mới hoàn tất. Around advice chạy proceed() và kết thúc ngay sau khi nhận future. Hỏi hai thời lượng đo được là gì?

**Giải đáp:** advice mặc định đo xấp xỉ 2 ms cho lượt gọi (nếu điểm bắt đầu nằm trước khi khởi tạo); observer completion có thể đo xấp xỉ 500 ms cho thao tác logic. Số cụ thể phụ thuộc mốc start và overhead thực tế, nhưng hai khoảng có bản chất khác nhau.

**Tình huống B.** Phương thức trả về một CompletableFuture đã completeExceptionally. After-returning hay after-throwing của *lời gọi đó* được kích hoạt?

**Giải đáp:** theo ngữ nghĩa thông thường, lời gọi **trả về bình thường** một handle; after-returning nhận handle. Trạng thái lỗi của handle chỉ được nhận biết khi quan sát completion hoặc lấy kết quả.

**Tình huống C.** Advice đăng ký callback sau khi future đã complete. Có bị mất completion không?

**Giải đáp:** không, nếu dùng đúng API CompletionStage/CompletableFuture: callback phụ thuộc có thể được thực thi ngay hoặc theo lịch thực thi của API. Điều nguy hiểm là tự kiểm tra trạng thái rồi bỏ qua đăng ký callback.

**Tình huống D.** Một publisher được trả về nhưng không bao giờ có subscriber. Advice quanh hàm trả về có chứng minh việc xử lý dữ liệu đã kết thúc không?

**Giải đáp:** không. Lần trả về chỉ chứng minh publisher đã được tạo/lấy. Muốn theo dõi việc tiêu thụ phải quan sát subscription và các tín hiệu liên quan theo hợp đồng publisher.

## 12. Kết luận kỹ thuật

Khi xác định điểm kết thúc của hành vi được advice bao quanh, hãy viết rõ **đối tượng quan sát** và **tín hiệu hoàn tất**:

- **Advice theo join point:** kết thúc ở return/throw của lượt thực thi được intercept.
- **Theo dõi tác vụ bất đồng bộ:** kết thúc ở completion/terminal signal/cancellation được hợp đồng API xác định, có xử lý ngoại lệ và ngữ cảnh tương ứng.
- **Theo dõi tài nguyên hoặc tác động phụ:** kết thúc khi chính nghĩa vụ đó thực sự hoàn thành, đôi khi muộn hơn completion của kết quả chính.

Một aspect đúng phải làm rõ ranh giới này trong pointcut, advice, tên sự kiện và hợp đồng quan sát; nếu không, log có thể báo “đã xong” khi công việc thực tế vẫn đang chạy.