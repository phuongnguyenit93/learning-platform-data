# Đóng SubmissionPublisher bình thường hoặc với lỗi

## Mục tiêu

Sau bài học này, bạn có thể:

- Phân biệt \`SubmissionPublisher.close()\` và \`closeExceptionally(Throwable)\`.
- Chọn tín hiệu kết thúc đúng với kết quả của luồng dữ liệu.
- Hiểu việc đóng publisher ảnh hưởng đến subscriber hiện tại và subscriber đăng ký sau đó như thế nào.
- Biết vì sao \`close()\` trả về không có nghĩa mọi subscriber đã xử lý xong tín hiệu kết thúc.
- Kiểm tra trạng thái đóng bằng \`isClosed()\` và \`getClosedException()\`.
- Quản lý executor và lỗi khi đóng publisher an toàn.

## 1. Hai cách kết thúc một SubmissionPublisher

\`SubmissionPublisher<T>\` là publisher bất đồng bộ có sẵn trong JDK, triển khai \`Flow.Publisher<T>\`. Publisher tiếp nhận item qua \`submit\` hoặc \`offer\`, rồi chuyển chúng đến các subscriber hiện tại theo thứ tự, tùy theo demand và chính sách gửi.

Khi nguồn dữ liệu đã hoàn tất, ứng dụng cần kết thúc publisher. Java cung cấp hai cách:

~~~java
publisher.close();
publisher.closeExceptionally(error);
~~~

| Method | Tín hiệu kết thúc | Ý nghĩa |
|---|---|---|
| \`close()\` | \`onComplete()\` | Nguồn kết thúc bình thường, không có lỗi |
| \`closeExceptionally(error)\` | \`onError(error)\` | Nguồn kết thúc do lỗi |

Cả hai method đều đánh dấu publisher đã đóng và không nhận thêm lần gửi mới. Chúng không xóa hay biến các item đã gửi thành kết quả khác. Subscriber nhận tín hiệu kết thúc theo giao thức Flow.

Chọn method theo kết quả thực tế:

- Đọc file, truy vấn hoặc xử lý luồng hoàn tất thành công: gọi \`close()\`.
- Nguồn dữ liệu thất bại và không thể tiếp tục: gọi \`closeExceptionally(cause)\`.
- Không dùng \`close()\` để che giấu lỗi đã xảy ra; nếu subscriber cần biết luồng thất bại, hãy gửi \`onError\` qua \`closeExceptionally\`.

## 2. close(): kết thúc bình thường

Khi gọi:

~~~java
publisher.close();
~~~

\`SubmissionPublisher\` phát tín hiệu \`onComplete()\` đến các subscriber hiện tại và từ chối những lần publish tiếp theo.

Một subscriber xử lý tín hiệu bình thường trong callback:

~~~java
@Override
public void onComplete() {
    System.out.println("source completed");
}
~~~

Tín hiệu hoàn tất biểu thị publisher không còn item nào được phát thêm cho subscription đó. Đây là tín hiệu kết thúc một chiều; subscriber không thể yêu cầu publisher mở lại.

Một publisher đã đóng không thể được tái sử dụng để phát một đợt dữ liệu mới. Nếu ứng dụng cần một luồng mới, hãy tạo một \`SubmissionPublisher\` khác.

### 2.1. Item đã gửi và tín hiệu hoàn tất

\`SubmissionPublisher\` chuyển item bất đồng bộ. Các item đã được chấp nhận cho subscriber được xử lý theo thứ tự trước tín hiệu kết thúc tương ứng, miễn là chúng không bị drop và subscriber có demand để nhận.

Subscriber phải tiếp tục yêu cầu dữ liệu theo hợp đồng Flow. Đóng publisher không làm tăng demand thay subscriber và không biến một item bị drop thành item được giao.

Nếu subscriber không còn demand hoặc đã hủy subscription, đừng giả định mọi item đều đã được xử lý. Hãy thiết kế subscriber và chính sách gửi để phù hợp với yêu cầu dữ liệu.

## 3. closeExceptionally(): kết thúc do lỗi

Khi nguồn không thể tiếp tục vì lỗi, gọi:

~~~java
publisher.closeExceptionally(cause);
~~~

Publisher phát tín hiệu \`onError(cause)\` đến các subscriber hiện tại. Subscriber có thể ghi log, giải phóng tài nguyên hoặc hoàn tất một future exceptional:

~~~java
@Override
public void onError(Throwable error) {
    System.err.println("stream failed: " + error.getMessage());
}
~~~

\`closeExceptionally\` không ném chính \`cause\` ra như một exception đồng bộ để thay cho callback. Nó chuyển lỗi thành tín hiệu kết thúc của publisher. Caller vẫn có thể nhận exception khác nếu executor không thể lập lịch callback; truyền \`null\` làm \`error\` sẽ ném \`NullPointerException\`.

Không tiếp tục gọi \`submit\` để phát dữ liệu sau khi đã kết thúc exceptional. Nếu muốn thử lại một nguồn, tạo publisher mới cho lần chạy mới và xác định rõ subscriber nào cần đăng ký lại.

## 4. Subscriber đăng ký sau khi publisher đã đóng

Một điểm quan trọng của \`SubmissionPublisher\` là subscriber đăng ký sau khi publisher đóng vẫn nhận tín hiệu kết thúc:

- Nếu publisher đã đóng bình thường, subscriber mới nhận \`onSubscribe\` rồi \`onComplete\`.
- Nếu publisher đã đóng exceptional, subscriber mới nhận \`onSubscribe\` rồi \`onError\` với lỗi đóng tương ứng.

Subscriber mới không nhận lại các item đã được gửi trước lúc đăng ký. \`SubmissionPublisher\` không phải replay publisher hay kho lưu lịch sử.

Điều này hữu ích khi một thành phần đăng ký muộn và chỉ cần biết nguồn đã kết thúc theo cách nào. Nếu cần phát lại dữ liệu cũ, ứng dụng phải lưu trữ và phát lại bằng cơ chế riêng.

## 5. Đóng publisher không đồng nghĩa callback đã chạy xong

Cả \`close()\` và \`closeExceptionally()\` đều không bảo đảm rằng mọi subscriber đã hoàn tất callback khi method trả về. Việc phân phối tín hiệu là bất đồng bộ và phụ thuộc executor.

Ví dụ:

~~~java
publisher.close();
// Không suy ra rằng mọi onComplete() đã chạy xong tại đây.
~~~

Nếu ứng dụng cần đợi subscriber xử lý xong tín hiệu cuối, hãy tạo cơ chế xác nhận ở subscriber, chẳng hạn \`CompletableFuture\`, \`CountDownLatch\` hoặc một future do \`consume(consumer)\` trả về.

Không shutdown executor ngay sau khi gọi close nếu executor đó vẫn cần thực thi callback đang chờ. Hãy đợi các subscriber hoàn tất công việc cần thiết, sau đó mới shutdown executor do ứng dụng sở hữu.

\`SubmissionPublisher\` không sở hữu vòng đời của executor được truyền vào constructor. Đóng publisher không tự shutdown executor dùng chung.

## 6. Kiểm tra trạng thái đóng

Hai method hữu ích:

~~~java
boolean closed = publisher.isClosed();
Throwable failure = publisher.getClosedException();
~~~

- \`isClosed()\` trả về \`true\` khi publisher không còn nhận submission.
- \`getClosedException()\` trả về lỗi được truyền vào \`closeExceptionally\`, hoặc \`null\` nếu publisher chưa đóng hay đã đóng bình thường.

Vì \`getClosedException()\` trả về \`null\` ở cả trạng thái chưa đóng và đóng bình thường, hãy kết hợp nó với \`isClosed()\`:

| isClosed | getClosedException | Diễn giải |
|---|---|---|
| \`false\` | \`null\` | Publisher còn mở |
| \`true\` | \`null\` | Publisher đã đóng bình thường |
| \`true\` | Có lỗi | Publisher đã đóng exceptional |

Đây là thông tin trạng thái để quan sát và chẩn đoán. Không dùng việc đọc trạng thái để thay thế đồng bộ hóa giữa các thread hoặc để dự đoán một thao tác publish kế tiếp chắc chắn thành công.

## 7. Đóng là thao tác một chiều

Hai method chỉ có hiệu lực nếu publisher chưa đóng. Khi đã đóng:

- Gọi \`close()\` lần nữa không mở lại publisher.
- Gọi \`closeExceptionally()\` sau khi đã đóng bình thường không đổi tín hiệu kết thúc thành lỗi.
- Gọi \`close()\` sau khi đã đóng exceptional không xóa lỗi đã ghi nhận.
- \`submit\` hoặc \`offer\` sau khi đóng sẽ bị từ chối, thường bằng \`IllegalStateException\`.

Vì vậy, nếu nhiều thread có thể quyết định kết thúc cùng một publisher, ứng dụng cần thống nhất thành phần nào chịu trách nhiệm đóng và xử lý race giữa thành công, lỗi và hủy. Không giả định một lời gọi đóng đến sau có thể ghi đè quyết định trước.

## 8. Ví dụ hoàn chỉnh: đóng bình thường và đóng với lỗi

Tạo file **SubmissionPublisherCloseDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;

public class SubmissionPublisherCloseDemo {

    private static final class LoggingSubscriber
            implements Flow.Subscriber<Integer> {

        private final String name;
        private final CompletableFuture<Void> terminal =
                new CompletableFuture<>();

        private Flow.Subscription subscription;

        LoggingSubscriber(String name) {
            this.name = name;
        }

        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            this.subscription = subscription;
            System.out.println(name + " subscribed");
            subscription.request(1);
        }

        @Override
        public void onNext(Integer item) {
            System.out.println(name + " item: " + item);
            subscription.request(1);
        }

        @Override
        public void onError(Throwable error) {
            System.out.println(name + " failed: "
                    + error.getClass().getSimpleName());
            terminal.complete(null);
        }

        @Override
        public void onComplete() {
            System.out.println(name + " completed");
            terminal.complete(null);
        }

        void awaitTerminal() throws Exception {
            terminal.get(5, TimeUnit.SECONDS);
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor(
                task -> new Thread(task, "publisher-demo"));

        SubmissionPublisher<Integer> normalPublisher =
                new SubmissionPublisher<>(executor, 8);
        SubmissionPublisher<Integer> failedPublisher =
                new SubmissionPublisher<>(executor, 8);

        try {
            LoggingSubscriber normal =
                    new LoggingSubscriber("normal");

            normalPublisher.subscribe(normal);
            normalPublisher.submit(10);
            normalPublisher.submit(20);
            normalPublisher.close();

            // close() chỉ phát tín hiệu; chờ callback hoàn tất riêng.
            normal.awaitTerminal();

            System.out.println("normal closed = "
                    + normalPublisher.isClosed());
            System.out.println("normal close exception = "
                    + (normalPublisher.getClosedException() == null));

            // Subscriber đến muộn chỉ nhận tín hiệu kết thúc.
            LoggingSubscriber lateNormal =
                    new LoggingSubscriber("late normal");
            normalPublisher.subscribe(lateNormal);
            lateNormal.awaitTerminal();

            LoggingSubscriber failed =
                    new LoggingSubscriber("error");

            failedPublisher.subscribe(failed);
            failedPublisher.submit(30);

            IllegalStateException cause =
                    new IllegalStateException("source failed");
            failedPublisher.closeExceptionally(cause);

            failed.awaitTerminal();

            System.out.println("error closed = "
                    + failedPublisher.isClosed());
            System.out.println("error close exception = "
                    + failedPublisher.getClosedException()
                            .getClass().getSimpleName());

            LoggingSubscriber lateError =
                    new LoggingSubscriber("late error");
            failedPublisher.subscribe(lateError);
            lateError.awaitTerminal();

            try {
                normalPublisher.submit(99);
                System.out.println("submit after close = accepted");
            } catch (IllegalStateException expected) {
                System.out.println("submit after close = rejected");
            }
        } finally {
            // Hai publisher đã đóng; lời gọi lặp lại không đổi kết quả.
            normalPublisher.close();
            failedPublisher.close();

            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac --release 17 -Xlint:all -d out SubmissionPublisherCloseDemo.java
java -cp out SubmissionPublisherCloseDemo
~~~

Output chính xác:

~~~text
normal subscribed
normal item: 10
normal item: 20
normal completed
normal closed = true
normal close exception = true
late normal subscribed
late normal completed
error subscribed
error item: 30
error failed: IllegalStateException
error closed = true
error close exception = IllegalStateException
late error subscribed
late error failed: IllegalStateException
submit after close = rejected
~~~

Ví dụ dùng một executor đơn luồng để callback có thứ tự dễ quan sát. Subscriber yêu cầu một item mỗi lần và xác nhận khi nhận tín hiệu kết thúc. Phần kiểm tra subscriber đăng ký muộn minh họa rằng publisher giữ trạng thái đóng, nhưng không phát lại các item cũ.

## 9. Xử lý lỗi trong vòng đời publisher

Một publisher có thể gặp lỗi ở nhiều giai đoạn:

- Nguồn dữ liệu thất bại trước khi phát item.
- Executor từ chối task phân phối.
- Handler xử lý drop ném exception.
- Subscriber ném exception trong callback.

Khi nguồn không thể tiếp tục, hãy đóng exceptional với nguyên nhân phù hợp. Nếu lỗi xảy ra ở executor hoặc khi phân phối, không giả định mọi subscriber đã nhận cùng một tập item; việc gửi có thể không hoàn tất đồng đều.

Subscriber nên tự bảo vệ callback của mình. Exception do subscriber ném ra có thể khiến subscription của subscriber đó bị hủy. Handler truyền vào constructor của \`SubmissionPublisher\` chỉ có vai trò được tài liệu API mô tả đối với exception trong \`onNext\`; không coi nó là bộ xử lý chung cho mọi lỗi ở \`onSubscribe\`, \`onError\` và \`onComplete\`.

Nếu cần độ tin cậy cao, ghi nhận trạng thái nguồn, lỗi kết thúc và số liệu giao nhận ở tầng ứng dụng. Không dựa riêng vào việc \`closeExceptionally\` đã trả về để kết luận mọi subscriber đã xử lý lỗi xong.

## 10. Lỗi thường gặp

### Gọi close() khi nguồn thực tế thất bại

Subscriber sẽ nhận \`onComplete\` và có thể hiểu nhầm dữ liệu đã đầy đủ. Dùng \`closeExceptionally(cause)\` nếu luồng kết thúc do lỗi.

### Nghĩ close() đợi tất cả subscriber

Lệnh đóng phát tín hiệu bất đồng bộ. Dùng future hoặc latch ở subscriber để đợi callback nếu cần.

### Shutdown executor ngay sau khi đóng

Callback có thể còn nằm trong hàng đợi. Đợi subscriber hoàn tất rồi mới shutdown executor do ứng dụng sở hữu.

### Tiếp tục submit sau khi đóng

Publisher không nhận item mới sau terminal state. Tạo publisher mới cho một lần phát dữ liệu mới.

### Coi getClosedException() == null là chắc chắn đang mở

Giá trị null có thể biểu thị publisher chưa đóng hoặc đã đóng bình thường. Kiểm tra thêm \`isClosed()\`.

### Dùng closeExceptionally để ném lỗi ngược về caller

Method phát \`onError\` cho subscriber. Nó không thay thế cơ chế throw/catch của luồng gọi; caller phải tự xử lý lỗi tại nơi phát sinh.

### Nghĩ subscriber đăng ký muộn sẽ nhận lại dữ liệu cũ

Subscriber đến sau chỉ nhận subscription và tín hiệu kết thúc tương ứng. Muốn replay, phải lưu và phát dữ liệu bằng cơ chế khác.

### Gọi cả close và closeExceptionally để đổi trạng thái

Đóng publisher là một chiều. Lời gọi sau không thay thế terminal state đã được thiết lập.

## 11. Checklist

- [ ] Đã chọn \`close()\` cho kết thúc bình thường.
- [ ] Đã chọn \`closeExceptionally(cause)\` khi nguồn kết thúc do lỗi.
- [ ] Đã hiểu publisher không nhận submission sau khi đóng.
- [ ] Đã tính đến subscriber hiện tại và subscriber đăng ký sau khi đóng.
- [ ] Đã hiểu lời gọi close không bảo đảm callback đã hoàn tất.
- [ ] Đã chờ subscriber nếu cần xác nhận xử lý xong terminal signal.
- [ ] Đã quản lý executor độc lập với vòng đời publisher.
- [ ] Đã dùng \`isClosed()\` cùng \`getClosedException()\` để đọc trạng thái.
- [ ] Đã xử lý race giữa các thread cùng muốn đóng publisher.
- [ ] Đã kiểm thử cả đường kết thúc bình thường và exceptional.

## 12. Tài liệu tham khảo

- [Java SE 17 API: SubmissionPublisher](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html)
- [Java SE 11 API: SubmissionPublisher](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html)

