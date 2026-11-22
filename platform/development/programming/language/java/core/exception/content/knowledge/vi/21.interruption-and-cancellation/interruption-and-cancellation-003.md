# Phân biệt `Thread.interrupted()` với `isInterrupted()` trong Java

Khi cần dừng một công việc đang chạy trên luồng (thread), Java thường dùng cơ chế **ngắt hợp tác** (*cooperative interruption*): một luồng gửi yêu cầu ngắt bằng `interrupt()`, còn luồng nhận tự kiểm tra tín hiệu và quyết định cách kết thúc an toàn. Để kiểm tra tín hiệu ấy, Java có hai phương thức trông rất giống nhau: `Thread.interrupted()` và `thread.isInterrupted()`. Cả hai đều trả `boolean`, nhưng **chúng kiểm tra luồng nào** và **có xóa trạng thái ngắt hay không** là hai khác biệt quyết định.

Hiểu sai hai phương thức có thể khiến tín hiệu hủy bị “tiêu thụ” quá sớm, luồng không dừng khi được yêu cầu, hoặc một công việc cấp trên không còn biết rằng luồng đang bị ngắt.

## 1. Hiểu trạng thái ngắt trước khi so sánh

Mỗi đối tượng `Thread` có trạng thái ngắt (*interrupt status*, thường gọi là cờ ngắt). Đây là tín hiệu cho luồng phối hợp với việc dừng, không phải lệnh cưỡng bức chấm dứt lập tức.

- `targetThread.interrupt()` gửi yêu cầu ngắt đến `targetThread`. Trong tình huống thông thường, nếu luồng đích đang chạy, trạng thái ngắt của nó được đặt thành `true`.
- Mã của luồng đích có thể đọc cờ ngắt, kết thúc vòng lặp, dọn dẹp tài nguyên và trả quyền điều khiển về cho người gọi.
- Một số thao tác chờ có khả năng ngắt, như `Thread.sleep()`, `Object.wait()`, `Thread.join()` hoặc `BlockingQueue.take()`, có thể ném `InterruptedException`. Những thao tác này thường **xóa trạng thái ngắt khi ném ngoại lệ**.
- Không phải mọi thao tác đều phản ứng với `interrupt()`. Ví dụ, một phép tính CPU không kiểm tra cờ sẽ không tự dừng; chờ giành khóa `synchronized` thông thường cũng không tự động trở thành phép chờ có thể ngắt.

Vì thế, cần phân biệt **gửi tín hiệu** (`interrupt()`), **quan sát tín hiệu** (`isInterrupted()` hoặc `Thread.interrupted()`), và **chính sách đáp ứng** (dừng, truyền lỗi hoặc dọn dẹp).

## 2. Hai API: cùng đọc cờ, khác đối tượng và tác dụng phụ

| Đặc điểm | `Thread.interrupted()` | `someThread.isInterrupted()` |
| --- | --- | --- |
| Kiểu phương thức | `static` | Phương thức thể hiện (instance) |
| Luồng được kiểm tra | **Luồng hiện tại**, tức luồng đang thực thi lời gọi | **Đối tượng `Thread` được gọi** (`someThread`); có thể là luồng hiện tại hoặc luồng khác |
| Giá trị trả về | `true` nếu trạng thái ngắt đang được đặt, ngược lại là `false` | `true` nếu trạng thái ngắt của đối tượng luồng đang được đặt, ngược lại là `false` |
| Trạng thái sau khi gọi | **Xóa cờ ngắt của luồng hiện tại** | **Không thay đổi cờ ngắt** |
| Đọc nhiều lần liên tiếp khi không có tín hiệu mới | Lần đầu có thể `true`, lần sau `false` vì lần đầu đã xóa | Có thể vẫn `true` ở cả hai lần |
| Trường hợp sử dụng | Luồng hiện tại muốn kiểm tra **và chủ động tiêu thụ** tín hiệu | Kiểm tra trạng thái mà **không làm mất** tín hiệu; cũng có thể quan sát một `Thread` khác |

Ví dụ phân biệt ngay trong luồng đang chạy:

```java
Thread current = Thread.currentThread();

boolean a = current.isInterrupted(); // Chỉ đọc, giữ nguyên cờ.
boolean b = Thread.interrupted();     // Đọc rồi xóa cờ của current.
boolean c = current.isInterrupted(); // Có thể false vì b đã xóa.
```

Ba dòng trên là đoạn minh họa, không phải chương trình Java độc lập. Nếu trạng thái ngắt trước dòng đầu là `true` và không có yêu cầu ngắt mới xen vào thì `a == true`, `b == true`, `c == false`.

**Bẫy về cú pháp:** `interrupted()` là phương thức `static`, vì thế dù Java cho phép cú pháp `someThread.interrupted()`, lời gọi ấy vẫn kiểm tra **luồng hiện tại**, không kiểm tra `someThread`. Tránh viết kiểu này. Muốn hỏi trạng thái của luồng khác, gọi `someThread.isInterrupted()`.

Có thể viết `Thread.currentThread().isInterrupted()` để đọc cờ của chính mình nhưng không xóa. Đây không phải một phương thức mới: chỉ là cách lấy đối tượng luồng hiện tại rồi gọi API instance.

## 3. Ví dụ có thể chạy: quan sát thay đổi của cờ ngắt

Tạo tệp **`InterruptFlagComparison.java`**:

```java
public class InterruptFlagComparison {
    public static void main(String[] args) {
        Thread current = Thread.currentThread();

        System.out.println("initial: " + current.isInterrupted());

        current.interrupt();
        System.out.println("peek: " + current.isInterrupted());
        System.out.println("readAndClear: " + Thread.interrupted());
        System.out.println("afterClear: " + current.isInterrupted());

        current.interrupt();
        try {
            Thread.sleep(10);
            throw new AssertionError("sleep should have been interrupted");
        } catch (InterruptedException exception) {
            System.out.println("afterSleepThrows: " + current.isInterrupted());
            current.interrupt();
            System.out.println("restored: " + current.isInterrupted());
        }

        System.out.println("finalReadAndClear: " + Thread.interrupted());
        System.out.println("finalStatus: " + current.isInterrupted());
    }
}
```

Biên dịch và chạy bằng Java 17 trở lên:

```bash
javac InterruptFlagComparison.java
java InterruptFlagComparison
```

Kết quả trên một lần chạy độc lập bình thường:

```text
initial: false
peek: true
readAndClear: true
afterClear: false
afterSleepThrows: false
restored: true
finalReadAndClear: true
finalStatus: false
```

Đọc kết quả theo từng nhóm:

1. Khi chương trình mới bắt đầu, luồng `main` chưa được ngắt, nên `initial: false`.
2. `current.interrupt()` đặt cờ thành `true`. `current.isInterrupted()` chỉ đọc nên `peek: true`, cờ vẫn còn.
3. `Thread.interrupted()` trả `true` và xóa cờ. Vì thế `afterClear: false`.
4. Chương trình đặt lại cờ rồi gọi `Thread.sleep(10)`. Vì luồng đã mang trạng thái ngắt, `sleep()` ném `InterruptedException`; khi vào `catch`, trạng thái đã bị xóa, tạo ra `afterSleepThrows: false`.
5. Lệnh `current.interrupt()` bên trong `catch` **khôi phục tín hiệu ngắt**. Vì thế `restored: true`.
6. Lệnh `Thread.interrupted()` cuối cùng lại nhận `true` và xóa cờ. `finalStatus: false` xác nhận trạng thái sau lần xóa cuối.

Giá trị `10` trong `sleep(10)` là thời gian chờ tối đa dự định (mili giây), không phải khoảng trễ cần đợi để phát sinh lỗi: việc cờ đã được đặt làm thao tác ngủ bị ngắt.

Ví dụ này cố tình gọi `Thread.interrupted()` để chứng minh tác dụng xóa cờ. Trong chương trình nghiệp vụ, không nên xóa tín hiệu ngắt nếu mã phía sau hoặc tầng gọi cần biết luồng đã được yêu cầu dừng.

## 4. Trạng thái nào đổi khi đọc?

Hãy xem một chuỗi thao tác **trên cùng luồng**, không có luồng nào gửi tín hiệu mới ở giữa:

| Thao tác | Giá trị trả về | Cờ sau thao tác |
| --- | --- | --- |
| Ban đầu chưa bị ngắt | — | `false` |
| `Thread.currentThread().interrupt()` | `void` | `true` |
| `Thread.currentThread().isInterrupted()` | `true` | `true` |
| `Thread.currentThread().isInterrupted()` lần nữa | `true` | `true` |
| `Thread.interrupted()` | `true` | `false` |
| `Thread.interrupted()` lần nữa | `false` | `false` |

Bảng mô tả một chuỗi có kiểm soát. Trong ứng dụng chạy đồng thời, một luồng khác có thể gọi `interrupt()` bất kỳ lúc nào; vì vậy kết quả của hai lần đọc tách rời có thể khác nhau do tín hiệu mới, chứ không chỉ do cách API xử lý cờ.

**Quy tắc cần nhớ:** `isInterrupted()` = *nhìn mà giữ*; `Thread.interrupted()` = *nhìn rồi xóa* (trên luồng hiện tại).

## 5. Kết hợp với `InterruptedException` và truyền tín hiệu hủy

Có ba tình huống quan trọng khi xử lý `InterruptedException`.

### 5.1. Phương thức có thể khai báo `throws InterruptedException`

Nếu phương thức chỉ là tầng trung gian và có thể truyền yêu cầu ngắt lên tầng gọi, thường nên **truyền tiếp ngoại lệ**:

```java
void waitForItem(java.util.concurrent.BlockingQueue<String> queue)
        throws InterruptedException {
    String item = queue.take();
    System.out.println(item);
}
```

Đây là đoạn phương thức minh họa đặt trong một lớp Java. Khi `take()` ném `InterruptedException`, phương thức trả quyền xử lý cho tầng gọi. Không cần bắt ngoại lệ chỉ để in log rồi tiếp tục vô điều kiện.

### 5.2. Không thể truyền `InterruptedException`: bắt và khôi phục cờ

`Runnable.run()` không khai báo checked exception. Nếu cần xử lý ngắt khi đang chờ trong `run()`, một mẫu phù hợp là **rời công việc** sau khi khôi phục trạng thái:

```java
@Override
public void run() {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            String item = queue.take();
            process(item);
        }
    } catch (InterruptedException exception) {
        Thread.currentThread().interrupt();
    } finally {
        closeOwnedResources();
    }
}
```

Đây là **mã minh họa bên trong một lớp triển khai `Runnable`**, với `queue`, `process(...)` và `closeOwnedResources()` do ứng dụng cung cấp. Không thể biên dịch độc lập nếu thiếu các thành phần đó.

Vì `queue.take()` đã xóa cờ khi ném `InterruptedException`, việc gọi `Thread.currentThread().interrupt()` trong `catch` khôi phục tín hiệu cho mã gọi hoặc cơ chế quản lý luồng có thể nhận biết. Sau đó `run()` kết thúc thay vì quay lại một vòng chờ khác. Việc dọn dẹp tài nguyên được thực hiện qua `finally`.

**Không nên** bắt `InterruptedException` rồi lặp lại ngay vô hạn như thể không có yêu cầu hủy. Nếu mã của bạn hoàn toàn chịu trách nhiệm xử lý và kết thúc sau ngắt, có thể có chiến lược riêng, nhưng phải nêu rõ ai sở hữu tín hiệu và khi nào được xóa.

### 5.3. Vì sao sau khi bắt ngoại lệ, `isInterrupted()` có thể là `false`?

Những API ném `InterruptedException` như `sleep()`, `wait()`, `join()` thường xóa trạng thái ngắt khi ném. Vì thế phép kiểm tra `Thread.currentThread().isInterrupted()` ngay đầu nhánh `catch` có thể trả `false` dù chính tác vụ đã bị ngắt. Đây là hành vi hợp lệ, không có nghĩa tín hiệu ngắt chưa từng xảy ra.

Đặc biệt, **đừng gọi thêm `Thread.interrupted()` trong `catch` với hy vọng xác minh lại ngoại lệ**: nếu trạng thái mới được khôi phục hoặc có tín hiệu ngắt khác đến, lời gọi này có thể xóa nó lần nữa.

## 6. Ví dụ thực tế: dừng worker chờ trên hàng đợi

Tạo tệp **`InterruptibleQueueWorker.java`**:

```java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;

public class InterruptibleQueueWorker {
    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<String> queue = new LinkedBlockingQueue<>();
        CountDownLatch started = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            try {
                started.countDown();
                while (!Thread.currentThread().isInterrupted()) {
                    String item = queue.take();
                    System.out.println("Processed: " + item);
                }
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
            } finally {
                System.out.println(
                        "Worker ended; interrupted="
                                + Thread.currentThread().isInterrupted());
            }
        }, "queue-worker");

        worker.start();
        started.await();
        worker.interrupt();
        worker.join();

        System.out.println("Main observed worker termination");
    }
}
```

Biên dịch và chạy:

```bash
javac InterruptibleQueueWorker.java
java InterruptibleQueueWorker
```

Khi chạy độc lập, không có dữ liệu được thêm vào hàng đợi, kết quả là:

```text
Worker ended; interrupted=true
Main observed worker termination
```

Diễn giải:

- `started` giúp `main` đợi worker bắt đầu trước khi phát yêu cầu ngắt; nếu lệnh ngắt đến trước lúc worker gọi `queue.take()`, `take()` vẫn phát hiện cờ và ném `InterruptedException`.
- Trong lúc không có phần tử, `take()` chờ. Khi bị ngắt, nó thoát bằng `InterruptedException` và xóa cờ.
- Worker gọi lại `interrupt()` trong nhánh `catch` để khôi phục cờ, sau đó đi vào `finally`; dòng đầu vì vậy hiển thị `true`.
- `worker.join()` chỉ giúp `main` đợi luồng worker kết thúc. Nó không gửi yêu cầu ngắt cho worker. Vì `main` in sau khi `join()` trả về, thứ tự hai dòng được bảo đảm.
- `worker.isInterrupted()` là phép đọc trạng thái tại thời điểm kiểm tra; đối với một luồng đã kết thúc, **không nên dùng cờ ngắt như hồ sơ lịch sử để kết luận vì sao nó dừng**. Ví dụ ghi trạng thái ngay trong `finally` của worker trước khi kết thúc.

Về mặt thiết kế, đây là **hủy hợp tác**: `main` đề nghị dừng, worker đáp ứng tại điểm chờ có hỗ trợ ngắt, dọn dẹp rồi kết thúc. `interrupt()` không cưỡng chế đóng tài nguyên hoặc bảo đảm mọi tác vụ tùy ý sẽ dừng.

## 7. Khi nào nên dùng phương thức nào?

**Dùng `thread.isInterrupted()`** khi muốn xem một luồng đã nhận yêu cầu ngắt mà **giữ nguyên tín hiệu**. Từ bên trong worker, `Thread.currentThread().isInterrupted()` là lựa chọn dễ đọc cho vòng lặp công việc:

```java
while (!Thread.currentThread().isInterrupted()) {
    doOneSmallNonBlockingStep();
}
```

Đây là đoạn minh họa: `doOneSmallNonBlockingStep()` do ứng dụng cung cấp và phải có khả năng kết thúc mỗi lượt; nếu chặn quá lâu ở thao tác không hỗ trợ ngắt thì kiểm tra đầu vòng không giúp dừng kịp thời.

**Dùng `Thread.interrupted()`** khi mã của **chính luồng hiện tại** chủ đích nhận và tiêu thụ tín hiệu ngắt, đã quyết định rõ việc xóa cờ phù hợp với hợp đồng của mình. Ví dụ, một đoạn kiểm tra trạng thái rồi rời hàm ngay có thể chấp nhận tiêu thụ tín hiệu nếu tầng đó thực sự sở hữu toàn bộ việc xử lý hủy. Tuy nhiên, nếu tầng gọi vẫn cần nhận biết ngắt, hãy bảo toàn/khôi phục trạng thái hoặc truyền `InterruptedException`.

Một vòng lặp `while (!Thread.interrupted())` có thể dùng để phát hiện rồi rời vòng lặp, nhưng lưu ý rằng cờ đã bị xóa lúc điều kiện trả `true`. Nếu mã phía sau đợi cờ vẫn còn hoặc muốn chuyển tín hiệu hủy lên tầng cao, hành vi này dễ gây lỗi. Với vòng lặp không cần tiêu thụ cờ, `isInterrupted()` thường diễn đạt ý định rõ hơn.

### 7.1. Quan sát luồng khác

Có thể dùng `worker.isInterrupted()` từ một luồng giám sát để đọc trạng thái ngắt của `worker` mà không xóa cờ của nó. Tuy nhiên, trạng thái cờ có thể thay đổi giữa lúc kiểm tra và lúc hành động; đây không phải một cơ chế đồng bộ hoặc kết quả nghiệp vụ hoàn chỉnh. Cần phối hợp với `join()`, `Future`, latch hoặc cơ chế kết thúc phù hợp nếu muốn biết công việc đã thật sự kết thúc.

Viết `worker.interrupted()` là sai ý định: vì `interrupted()` là `static`, nó đọc và xóa cờ của **luồng giám sát đang gọi**, không đọc cờ của `worker`. Dù một trình biên dịch cho phép cú pháp qua biến, hãy luôn gọi `Thread.interrupted()` để thể hiện chính xác rằng phương thức là static.

### 7.2. Quan hệ với `Future.cancel(true)`

Trong công việc do `ExecutorService` quản lý, `Future.cancel(true)` yêu cầu hủy và **có thể gửi interrupt tới luồng đang chạy tác vụ**; `cancel(false)` không yêu cầu ngắt tác vụ đang chạy. Trạng thái của `Future` và cờ ngắt của worker là hai khái niệm khác nhau. Không suy ra rằng `cancel(true)` sẽ buộc một tác vụ phớt lờ ngắt phải dừng ngay.

Một tác vụ chạy trong pool nên có chiến lược phản hồi khi bị ngắt và dọn dẹp an toàn. Tuy nhiên, không nên tự ý gọi `Thread.interrupted()` chỉ để “làm sạch” cờ của worker; việc xóa tín hiệu có thể khiến logic hủy phía ngoài khó hiểu. Khi hợp đồng thư viện hoặc framework yêu cầu quản lý tín hiệu khác, cần tuân theo hợp đồng đó một cách nhất quán.

## 8. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Gọi `Thread.interrupted()` chỉ để “kiểm tra xem có bị ngắt không” | Xóa mất cờ, mã phía sau có thể không thấy yêu cầu ngắt | Dùng `Thread.currentThread().isInterrupted()` nếu chỉ muốn xem |
| Gọi `otherThread.interrupted()` để hỏi về luồng khác | Thực tế lại kiểm tra/xóa cờ của luồng gọi | Gọi `otherThread.isInterrupted()` |
| Bắt `InterruptedException` rồi bỏ qua | Tác vụ có thể tiếp tục mặc dù đã được yêu cầu dừng | Truyền ngoại lệ lên hoặc khôi phục cờ và kết thúc phù hợp |
| Cho rằng `isInterrupted() == false` trong `catch` chứng minh chưa bị ngắt | Bỏ qua việc API chờ có thể đã xóa cờ khi ném ngoại lệ | Dựa vào `InterruptedException` vừa bắt, xử lý và khôi phục nếu cần |
| Dùng `interrupt()` như lệnh dừng cứng | Công việc không hợp tác vẫn chạy | Chọn điểm chờ có thể ngắt và kiểm tra cờ trong các vòng tính toán |
| Kết luận `isInterrupted() == true` nghĩa là luồng đã dừng | Ngắt là yêu cầu; luồng có thể vẫn đang chạy | Dùng `join()` hoặc cơ chế hoàn tất phù hợp |
| Dùng `Thread.interrupted()` rồi chạy tiếp, không xem xét tín hiệu đã tiêu thụ | Làm mất ý nghĩa của yêu cầu hủy đối với tầng gọi | Xác định rõ trách nhiệm xử lý; khôi phục nếu cần chuyển tiếp |

Một lưu ý thêm về luồng chạy đồng thời: không dùng cờ ngắt làm biến trạng thái nghiệp vụ để thay thế cho `volatile`, khóa, hàng đợi hay các primitive đồng bộ khác. Cờ ngắt có vai trò riêng là phối hợp hủy/ngắt công việc.

## 9. Câu hỏi tự kiểm tra

1. Luồng `main` gọi `worker.interrupt()`, sau đó gọi `Thread.interrupted()` trong chính `main`. Phương thức đó kiểm tra cờ của ai? **Của `main`**, vì `interrupted()` là static và luôn tác động lên luồng hiện tại; nó không đọc cờ của `worker`.
2. Luồng đang có cờ ngắt `true`. Gọi `Thread.currentThread().isInterrupted()` hai lần liên tiếp mà không có thay đổi khác sẽ trả gì? **`true` và `true`**, bởi phương thức này không xóa cờ.
3. Cùng điều kiện trên, gọi `Thread.interrupted()` hai lần liên tiếp trả gì? **`true` và `false`**, vì lần đầu đã xóa cờ.
4. Vì sao `isInterrupted()` ngay trong `catch (InterruptedException e)` thường có thể trả `false`? Vì API chờ đã **xóa cờ khi ném `InterruptedException`**.
5. Trong `Runnable.run()`, nên làm gì nếu `BlockingQueue.take()` bị ngắt và chương trình cần ngừng worker? **Khôi phục cờ bằng `Thread.currentThread().interrupt()` rồi rời công việc và dọn dẹp**, hoặc thực hiện chính sách ngắt đã được ứng dụng quy định.
6. Có thể dùng `isInterrupted()` để kiểm tra luồng khác không? **Có**, qua `otherThread.isInterrupted()`. Điều đó chỉ đọc cờ tại thời điểm quan sát, không bảo đảm tác vụ đã hoàn tất.

**Ghi nhớ:** `Thread.interrupted()` hỏi *“luồng hiện tại có bị ngắt không?”* và **xóa** trạng thái; `thread.isInterrupted()` hỏi *“luồng này có bị ngắt không?”* và **giữ nguyên** trạng thái. Chọn đúng API dựa trên việc bạn cần **chỉ quan sát** hay **chủ động tiêu thụ** tín hiệu ngắt.