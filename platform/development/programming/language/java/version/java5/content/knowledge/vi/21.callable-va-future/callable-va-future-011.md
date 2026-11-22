# invokeAny và lựa chọn một kết quả thành công

## 1. Khi nhiều tác vụ là những cách thay thế nhau

Giả sử có hai bản sao dữ liệu. Ứng dụng có thể đọc từ một trong hai, miễn kết quả đáp ứng yêu cầu. Chờ mọi nguồn hoàn tất sẽ làm độ trễ phụ thuộc cả nguồn chậm; điều ta cần là **một kết quả chấp nhận được**.

`ExecutorService.invokeAny` thực hiện một nhóm `Callable<T>` và trả kết quả của một tác vụ hoàn thành thành công. Những tác vụ chưa hoàn tất bị hủy khi phương thức trả về, dù trả bình thường hay ném ngoại lệ.

Khác với việc ghép nhiều phần của báo cáo:

- Các phần báo cáo bổ sung cho nhau: thường cần tất cả.
- Các bản sao hoặc thuật toán thay thế nhau: có thể chỉ cần một.

Chọn `invokeAny` khi một kết quả đã đủ theo hợp đồng nghiệp vụ, không phải chỉ vì tên gọi nghe có vẻ nhanh. Những API trong bài có từ Java 5 và vẫn áp dụng trên Java hiện đại; ví dụ chạy với Java 17+.

## 2. “Thành công” theo API nghĩa là gì?

Một `Callable` thành công khi nó **trả về bình thường, không ném ngoại lệ**. API không biết dữ liệu bên trong đúng nghiệp vụ hay không.

| Kết quả của Callable | API coi là thành công? |
| --- | --- |
| Trả một đối tượng hợp lệ | Có |
| Trả `null` | Có |
| Trả chuỗi rỗng hoặc dữ liệu cũ | Có, nếu không ném ngoại lệ |
| Ném ngoại lệ vì nguồn lỗi | Không |
| Ném ngoại lệ vì dữ liệu không đạt yêu cầu | Không |

Nếu null, dữ liệu hết hạn hoặc sai phiên bản không được chấp nhận, phải kiểm tra **bên trong tác vụ trước khi trả về**. Nếu chờ `invokeAny` trả xong mới kiểm tra, các ứng viên khác đã có thể bị hủy.

Các chữ ký:

```java
<T> T invokeAny(Collection<? extends Callable<T>> tasks)
        throws InterruptedException, ExecutionException;

<T> T invokeAny(Collection<? extends Callable<T>> tasks,
                long timeout, TimeUnit unit)
        throws InterruptedException, ExecutionException, TimeoutException;
```

Đây là chữ ký API để đọc hợp đồng, không phải phương thức ứng dụng phải tự triển khai. [Tài liệu invokeAny](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html#invokeAny(java.util.Collection))

Kết quả trả về là `T`, không phải `Future<T>`. Luồng gọi đang chờ trong chính phương thức cho tới lúc có kết quả hoặc một điều kiện kết thúc khác.

## 3. Không phải ứng viên đầu tiên trong danh sách, cũng không phải kết quả tốt nhất

`invokeAny` không là cơ chế ưu tiên nguồn theo thứ tự đầu vào. Một ứng viên trong danh sách trước có thể thất bại, còn ứng viên sau trả kết quả.

Cũng không coi nó là phép chọn tối ưu:

- Không bảo đảm giá thấp nhất nếu các tác vụ trả báo giá.
- Không bảo đảm dữ liệu mới nhất nếu các tác vụ đọc nhiều bản sao.
- Không bảo đảm một nguồn cụ thể thắng nếu nhiều ứng viên đều thành công.
- Không cam kết mọi tác vụ đều đã bắt đầu trước khi có kết quả.

Mức đồng thời phụ thuộc bộ thực thi và cách lập lịch. Bộ thực thi một luồng không làm các nguồn chạy cùng lúc; một ứng viên chặn có thể giữ vị trí cần cho ứng viên khác.

Cách diễn đạt chính xác là “trả một kết quả thành công được cơ chế điều phối chọn”, thường được dùng để phản hồi sớm khi một ứng viên đã đạt yêu cầu. Không viết logic nghiệp vụ phụ thuộc vào một bên thắng cố định khi nhiều bên đều có thể thắng.

## 4. Thí nghiệm: một bên lỗi, một bên thắng, một bên bị hủy

Chương trình có ba ứng viên:

- Nguồn A báo lỗi.
- Nguồn chậm giữ ở một chốt và chỉ thoát khi bị ngắt.
- Nguồn B chờ hai ứng viên kia đi tới mốc đã định, rồi trả kết quả đã được kiểm tra.

Tệp **InvokeAnyWinnerDemo.java**:

```java
import java.io.IOException;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class InvokeAnyWinnerDemo {
    record Snapshot(String source, String payload) {}

    private static Snapshot validate(Snapshot value) throws IOException {
        if (value == null || value.payload() == null || value.payload().isBlank()) {
            throw new IOException("Unusable snapshot");
        }
        return value;
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(3);
        CountDownLatch otherCandidatesReachedPoint = new CountDownLatch(2);
        CountDownLatch holdSlow = new CountDownLatch(1);
        CountDownLatch slowExited = new CountDownLatch(1);
        AtomicBoolean slowObservedInterrupt = new AtomicBoolean();

        List<Callable<Snapshot>> candidates = List.of(
                () -> {
                    otherCandidatesReachedPoint.countDown();
                    throw new IOException("Source A unavailable");
                },
                () -> {
                    otherCandidatesReachedPoint.countDown();
                    try {
                        holdSlow.await();
                        return validate(new Snapshot("slow", "late-payload"));
                    } catch (InterruptedException ex) {
                        slowObservedInterrupt.set(true);
                        throw ex;
                    } finally {
                        slowExited.countDown();
                    }
                },
                () -> {
                    otherCandidatesReachedPoint.await();
                    return validate(new Snapshot("B", "payload-v1"));
                }
        );

        try {
            Snapshot result = pool.invokeAny(candidates);
            System.out.println("winner=" + result.source());
            System.out.println("payload=" + result.payload());

            if (!slowExited.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Slow task did not exit");
            }
            System.out.println("slowObservedInterrupt="
                    + slowObservedInterrupt.get());
            System.out.println("executorShutdown=" + pool.isShutdown());
        } finally {
            holdSlow.countDown();
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Executor did not terminate");
            }
        }
    }
}
```

Chạy:

```shell
javac --release 17 InvokeAnyWinnerDemo.java
java InvokeAnyWinnerDemo
```

Stdout khi hoàn tất bình thường:

```text
winner=B
payload=payload-v1
slowObservedInterrupt=true
executorShutdown=false
```

B được chọn vì A không thể trả kết quả và ứng viên chậm chưa thể trả kết quả khi B thành công. Các chốt tạo điều kiện xác định cho thí nghiệm, không khẳng định mọi lần gọi `invokeAny` đều cho các ứng viên bắt đầu cùng lúc.

Chương trình chờ `slowExited` để xác nhận tác vụ chậm đi qua điểm dọn dẹp. Nó không giả định việc `invokeAny` đã trả về đồng nghĩa mọi mã của các ứng viên khác đều dừng thực tế.

`executorShutdown=false` cũng cho thấy hủy phần việc còn lại của nhóm không đóng bộ thực thi. Bên sở hữu vẫn quản lý vòng đời tài nguyên đó.

Hàm `validate` kiểm tra mức tối thiểu phục vụ ví dụ. Ứng dụng thực tế có thể cần kiểm tra phiên bản, thời gian cập nhật, chữ ký hoặc điều kiện nhất quán trước khi chấp nhận nguồn.

## 5. Khi không có kết quả: phân biệt ba đường thoát

| Tình huống | Cách lời gọi kết thúc |
| --- | --- |
| Có một tác vụ thành công | Trả kết quả của một tác vụ thành công |
| Không tác vụ nào có thể hoàn thành thành công | Ném `ExecutionException` |
| Bản có timeout chưa có kết quả thành công trước hết hạn | Ném `TimeoutException` |
| Luồng đang gọi bị ngắt trong lúc chờ | Ném `InterruptedException` |

Một ứng viên lỗi chưa đủ để kết luận cả lời gọi thất bại. Cơ chế điều phối còn có thể chờ các ứng viên khác.

Nhưng nếu tất cả đều kết thúc bằng lỗi, `ExecutionException` cho biết không có kết quả thành công. Không có cam kết rằng cause của ngoại lệ này chứa toàn bộ lỗi, theo thứ tự đầu vào hoặc theo nguồn ưu tiên. Nếu cần chẩn đoán mọi ứng viên, hãy có cơ chế ghi nhận từng lỗi hoặc dùng cách điều phối thu thập kết quả phù hợp.

Timeout là thời hạn của cả lời gọi nhóm, gồm thời gian chờ luồng rảnh; không phải ngân sách mới cấp cho từng ứng viên lúc bắt đầu. Bản không timeout có thể chờ vô hạn nếu vẫn còn ứng viên chưa kết thúc mà không ứng viên nào thành công. [Tài liệu invokeAny có timeout](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html#invokeAny(java.util.Collection,long,java.util.concurrent.TimeUnit))

## 6. Thí nghiệm các trường hợp biên

Ví dụ sau tạo riêng ba tình huống: mọi ứng viên lỗi, ứng viên không thể hoàn tất trước khi mở chốt, và một Callable trả null bình thường. Nó cũng xác minh nhóm rỗng bị từ chối.

Tệp **InvokeAnyOutcomesDemo.java**:

```java
import java.io.IOException;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

public class InvokeAnyOutcomesDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch hold = new CountDownLatch(1);
        AtomicInteger attempts = new AtomicInteger();

        try {
            List<Callable<String>> failing = List.of(
                    () -> {
                        attempts.incrementAndGet();
                        throw new IOException("A failed");
                    },
                    () -> {
                        attempts.incrementAndGet();
                        throw new IOException("B failed");
                    }
            );

            try {
                pool.invokeAny(failing);
            } catch (ExecutionException ex) {
                System.out.println("allFailed=ExecutionException");
                System.out.println("reportedCauseType="
                        + ex.getCause().getClass().getSimpleName());
            }
            System.out.println("failedAttempts=" + attempts.get());

            List<Callable<String>> blocked = List.of(() -> {
                hold.await();
                return "late";
            });

            try {
                pool.invokeAny(blocked, 100, TimeUnit.MILLISECONDS);
            } catch (TimeoutException ex) {
                System.out.println("noSuccessBeforeDeadline=TimeoutException");
            }

            List<Callable<String>> returnsNull = List.of(() -> null);
            System.out.println("nullIsNormalResult="
                    + (pool.invokeAny(returnsNull) == null));

            try {
                pool.invokeAny(List.<Callable<String>>of());
            } catch (IllegalArgumentException ex) {
                System.out.println("emptyGroup=IllegalArgumentException");
            }
        } finally {
            hold.countDown();
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Executor did not terminate");
            }
        }
    }
}
```

Chạy:

```shell
javac --release 17 InvokeAnyOutcomesDemo.java
java InvokeAnyOutcomesDemo
```

Stdout:

```text
allFailed=ExecutionException
reportedCauseType=IOException
failedAttempts=2
noSuccessBeforeDeadline=TimeoutException
nullIsNormalResult=true
emptyGroup=IllegalArgumentException
```

Hai lỗi trong nhóm đầu đều là IOException nên kiểu cause được in chắc chắn như nhau; chương trình không đoán thông điệp A hay B sẽ được chọn.

Nhóm bị giữ bởi chốt không thể trả thành công trước khi lời gọi hết hạn. Không đo rồi tuyên bố nó luôn mất đúng 100 ms; chi phí lập lịch và xử lý có thể làm thời gian quan sát chênh lệch.

Nhóm trả null chỉ có một ứng viên, nên nó minh họa rõ null là kết quả bình thường của API. Nếu null không hợp lệ theo nghiệp vụ, phải biến nó thành đường thất bại ngay trong Callable.

## 7. Hủy các ứng viên khác không hoàn tác tác dụng phụ

Khi một bên thắng, các tác vụ chưa xong bị hủy; trong bộ thực thi chuẩn, điều đó có thể gửi tín hiệu ngắt tới luồng thực hiện. Nhưng:

- Tác vụ có thể đang chạy mã không kiểm tra ngắt.
- API chặn có thể cần timeout hoặc cơ chế đóng tài nguyên riêng.
- Yêu cầu mạng đã gửi có thể tiếp tục được xử lý ở máy chủ khác.
- Dữ liệu đã ghi không tự bị hoàn tác.

Vì vậy, đọc từ các bản sao là ví dụ dễ phù hợp hơn so với “gửi cùng một thanh toán tới ba cổng rồi chọn một bên”. Gọi hủy ở phía Java không chứng minh hai thanh toán còn lại chưa xảy ra.

Ngay cả với tác vụ đọc, gửi đồng thời nhiều yêu cầu vẫn có chi phí kết nối, CPU và hạn mức dịch vụ. Phải giới hạn số ứng viên, lượng công việc đồng thời và mức lặp yêu cầu theo tài nguyên thực tế.

Nếu một ứng viên bắt lỗi ngắt rồi trả dữ liệu giả để thoát bình thường, nó có thể vô tình được coi là thành công. Mã tác vụ nên giữ đúng ý nghĩa: trả dữ liệu đã được chấp nhận, hoặc báo không thể cung cấp dữ liệu.

## 8. Chọn cấu trúc kết quả đủ ngữ cảnh

Nếu chỉ trả một chuỗi, bên gọi có thể không biết dữ liệu đến từ nguồn nào. Một kiểu kết quả như record `Snapshot(source, payload)` giúp giữ danh tính nguồn cùng dữ liệu.

Có thể cần thêm:

- Phiên bản dữ liệu hoặc thời điểm cập nhật.
- Mã truy vết thao tác.
- Những giới hạn của kết quả đã được kiểm tra.
- Trạng thái dùng nguồn dự phòng nếu nghiệp vụ cần phân biệt.

Không dùng tên luồng làm danh tính nguồn. Một luồng làm việc có thể xử lý tác vụ của nhiều nguồn ở các lần gọi khác nhau.

Nếu cần so sánh chất lượng giữa nhiều kết quả, `invokeAny` có thể không phải công cụ đúng: nó dừng ở một thành công được chọn. Khi yêu cầu là “chọn bản mới nhất từ mọi nguồn”, cần thu đủ kết quả hoặc có tiêu chí chấp nhận rõ hơn để một kết quả sớm đã đủ giá trị.

## 9. Lỗi tiếp nhận và đầu vào cũng cần xử lý

Nhóm đầu vào phải khác null, không rỗng và không chứa phần tử null. Không thay đổi collection trong lúc `invokeAny` đang hoạt động.

Bộ thực thi đã đóng hoặc không tiếp nhận được tác vụ theo chính sách có thể dẫn tới `RejectedExecutionException`. Đây là lỗi lập lịch, khác `ExecutionException` dùng để báo không có tác vụ hoàn thành thành công.

Không giả định gửi nhóm là một giao dịch “hoặc chạy hết hoặc không chạy gì”. Nếu lập lịch gặp lỗi, một số công việc có thể đã bắt đầu và tạo tác dụng phụ.

Đừng bắt mọi ngoại lệ rồi trả `null` để thể hiện “không có dữ liệu”. Bạn sẽ trộn lẫn null hợp lệ, mọi nguồn lỗi, hết hạn và yêu cầu ngắt; người gọi mất khả năng quyết định đúng.

Khi bắt `InterruptedException` của luồng điều phối, truyền tiếp hoặc khôi phục cờ ngắt rồi rời luồng xử lý theo hợp đồng. Không biến yêu cầu dừng thành một lần thử lại vô hạn.

## 10. So sánh các cách chờ nhóm

| Nhu cầu | API/cách tiếp cận |
| --- | --- |
| Chỉ cần một tác vụ trả thành công | `invokeAny` |
| Cần Future cho toàn bộ nhóm | `invokeAll` |
| Cần xử lý từng kết quả theo lúc hoàn thành | `ExecutorCompletionService` |
| Kết hợp chuỗi bất đồng bộ theo mô hình CompletionStage | Thiết kế với `CompletableFuture` phù hợp |

`CompletableFuture.anyOf` không phải phép thay tên trực tiếp cho `invokeAny`: anyOf hoàn thành theo một future hoàn tất, có thể hoàn tất bằng ngoại lệ. Nó không mang cùng ý nghĩa “chờ một thành công” và cũng không tự có chính sách hủy các tác vụ còn lại như lời gọi invokeAny. [Tài liệu CompletableFuture.anyOf](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CompletableFuture.html#anyOf(java.util.concurrent.CompletableFuture...))

Một vòng lặp `get()` theo thứ tự Future cũng không tương đương: nó có thể chờ ứng viên đầu đang chậm dù ứng viên thứ hai đã có dữ liệu.

Nếu cần lỗi chi tiết từng nguồn và tiêu chí thành công phức tạp, dùng cơ chế thu nhận từng kết quả rồi tự quyết định lúc chấp nhận/dừng. Độ linh hoạt đó đi kèm trách nhiệm giữ handle, hủy phần việc còn lại và dọn tài nguyên.

## 11. Ranh giới vòng đời và quan hệ chờ

`invokeAny` quản lý nhóm ứng viên của lời gọi, không quản lý toàn bộ vòng đời ứng dụng.

- Không đóng một bộ thực thi mượn dùng chung sau mỗi lần chọn nguồn.
- Bên sở hữu đóng bộ thực thi khi vòng đời thật sự kết thúc.
- Nếu cần xác nhận các tác vụ đã dọn dẹp, đừng chỉ dựa vào việc lời gọi đã trả về.
- Không gọi chờ nhóm con từ tác vụ đang giữ toàn bộ vị trí chạy của chính bộ thực thi đó.

Ví dụ với bộ thực thi một luồng: tác vụ cha gọi `invokeAny` cho các tác vụ con trên cùng bộ thực thi rồi chờ. Cha giữ luồng duy nhất, các con không có cơ hội chạy. Bản có timeout chỉ khiến nó thất bại sau thời hạn; không sửa được quan hệ chờ.

Việc điều phối nên nằm ngoài nhóm luồng công việc khi thiết kế phụ thuộc như vậy.

## 12. Tự đánh giá một lựa chọn nguồn dữ liệu

Ứng dụng có ba bản sao và cần một bản có phiên bản ít nhất là 12. Hãy xác định:

1. Kiểm tra phiên bản nằm trong Callable hay sau `invokeAny`?
2. Nguồn trả null có được coi là ứng viên thành công không?
3. Nếu một nguồn lỗi nhưng hai nguồn còn chạy, nên kết luận điều gì?
4. Hết thời hạn nhóm báo ngoại lệ nào?
5. Sau khi một nguồn thắng, tác vụ còn lại có thể vẫn giữ tài nguyên không?
6. Nếu cần bản có phiên bản cao nhất, có còn đủ điều kiện dùng một kết quả sớm không?

Câu trả lời làm rõ ý nghĩa của “một thành công”: dữ liệu phải được xác thực trước khi được chấp nhận, những nguồn khác có chính sách hủy và quyền quản lý tài nguyên phải tiếp tục được giữ đúng nơi.
