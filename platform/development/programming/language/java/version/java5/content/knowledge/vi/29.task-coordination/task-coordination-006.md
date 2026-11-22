# BrokenBarrierException, ngắt luồng và hết hạn chờ

## 1. Một bên không qua được rào thì cả lượt phải dừng

`CyclicBarrier` phối hợp một nhóm có số bên tham gia cố định. Mỗi bên làm phần việc của một giai đoạn rồi gọi `await()`. Khi đủ số bên đến rào, lượt đồng bộ hoàn tất và các bên có thể đi tiếp.

Vấn đề xuất hiện khi một bên không thể tiếp tục đợi: bị ngắt, hết thời gian chờ hoặc thao tác tổng hợp tại rào thất bại. Nếu các bên còn lại vẫn coi giai đoạn đã hoàn tất, chúng có thể sử dụng dữ liệu chưa đủ.

Vì vậy, barrier có cơ chế hỏng cả lượt: một sự cố trong việc đồng bộ có thể làm các bên khác rời rào bằng `BrokenBarrierException`.

Cần phân biệt hai loại thông tin:

- **Lỗi tại bên gây sự cố**, chẳng hạn `InterruptedException` hoặc `TimeoutException`.
- **Thông báo lượt đồng bộ không còn hợp lệ** ở các bên khác: `BrokenBarrierException`.

Các API này có từ Java 5 và vẫn áp dụng trong Java hiện đại. Bài dùng ví dụ Java 17 trở lên, không dùng ngủ để đoán một luồng đã kịp đến rào hay chưa.

## 2. Trạng thái bình thường và trạng thái broken

Một barrier có thể trải qua nhiều lượt bình thường:

```text
Lượt 1: đủ bên → tất cả qua rào
Lượt 2: đủ bên → tất cả qua rào
Lượt 3: ...
```

Khi một lượt bị phá vỡ:

```text
Một bên không tiếp tục chờ được
             ↓
Lượt hiện tại bị hỏng
             ↓
Các bên đang đợi rời rào bất thường
             ↓
Các await mới trên barrier đang hỏng cũng thất bại
```

Barrier không tự trở lại hoạt động chỉ vì số bên bị thiếu cuối cùng đã tới. Có thể kiểm tra trạng thái bằng `isBroken()`, nhưng kiểm tra trước không loại bỏ khả năng sự cố xảy ra ngay sau đó:

```java
// Không thay được việc xử lý ngoại lệ từ await.
if (!barrier.isBroken()) {
    barrier.await();
}
```

Đây là đoạn minh họa trong phương thức đã xử lý hoặc khai báo ngoại lệ. Lần kiểm tra chỉ phản ánh một thời điểm; `await` vẫn có thể thất bại.

Tính tái sử dụng sau một lượt thành công khác với việc phục hồi sau một lượt hỏng.

## 3. Ngoại lệ nào đến với bên nào?

| Sự kiện trong lượt hiện tại | Bên gặp trực tiếp | Những bên khác đang chờ |
| --- | --- | --- |
| Một bên bị ngắt khi đang đợi hoặc mang cờ ngắt khi vào một lượt còn lành | Thường nhận `InterruptedException` | Nhận `BrokenBarrierException`, trừ khi đồng thời gặp ngắt riêng |
| Một lần `await(timeout, unit)` thực sự hết hạn trước khi lượt hoàn tất | Bên hết hạn nhận `TimeoutException` | Nhận `BrokenBarrierException` |
| Barrier action ném ngoại lệ | Bên đến cuối chạy action nhận ngoại lệ đó | Nhận `BrokenBarrierException` |
| Có `reset()` khi các bên đang chờ | Những bên đang chờ bị đưa ra bằng `BrokenBarrierException` | Cùng bị kết thúc lượt cũ |
| Gọi `await` trên barrier đang broken | Bên gọi nhận `BrokenBarrierException` | Không có lượt thành công để đi tiếp |

Bảng mô tả các trường hợp không có tranh đua phức tạp tại ranh giới kết thúc lượt. Nếu nhiều sự kiện xảy ra gần nhau, không nên gán cứng một ngoại lệ duy nhất cho mọi lịch thực thi.

`BrokenBarrierException` không tự cho biết tác vụ nào gây lỗi và không tự mang ngoại lệ nghiệp vụ gốc của tác vụ khác. Nếu cần chẩn đoán nguyên nhân đầu tiên, lưu nó qua một kênh an toàn giữa các luồng hoặc thu nhận kết quả tác vụ bằng `Future`.

## 4. Ngắt luồng không phải “cứu” riêng một người đợi

Một luồng có thể bị ngắt trong `await()`, hoặc đã có cờ ngắt khi đi vào lời gọi. Khi thao tác chờ báo `InterruptedException`, trạng thái ngắt được xóa theo hợp đồng; tầng xử lý thường truyền ngoại lệ lên hoặc khôi phục cờ rồi kết thúc phần việc hiện tại.

Mẫu cho một tác vụ:

```java
// Mã minh họa bên trong Runnable hoặc một phương thức void.
try {
    barrier.await();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
} catch (BrokenBarrierException e) {
    return;
}
continueWithNextPhase();
```

`continueWithNextPhase` đại diện cho phần việc chỉ được làm sau khi đồng bộ thành công.

Không viết một `catch` chung rồi tiếp tục xử lý giai đoạn kế tiếp. Cũng không tự khôi phục cờ ngắt chỉ vì bắt được `BrokenBarrierException`: thông báo đó không có nghĩa chính luồng hiện tại bị ngắt.

Có một chi tiết ở ranh giới tranh đua: nếu lượt đã hoàn tất trước khi yêu cầu ngắt được xử lý, luồng có thể đi qua rào thành công mà vẫn mang cờ ngắt. Vì vậy, phát biểu “gọi interrupt lúc nào cũng phá barrier” là quá mạnh. Bài không dựa vào cuộc đua đó; ví dụ bên dưới tạo trường hợp ngắt trước khi gọi `await` trên barrier còn lành.

## 5. Hết hạn chờ là ngoại lệ, không phải giá trị false

Khác với một số API chờ khác, `CyclicBarrier.await(timeout, unit)` trả chỉ số đến rào khi thành công; khi thực sự hết thời gian chờ, nó ném `TimeoutException`.

```java
try {
    int arrivalIndex = barrier.await(2, TimeUnit.SECONDS);
    // Chỉ tại đây mới được coi lượt đồng bộ là thành công.
} catch (TimeoutException e) {
    // Dừng hoặc báo thất bại của lượt.
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Dừng phần việc phụ thuộc vào lượt này.
} catch (BrokenBarrierException e) {
    // Một bên khác hoặc cơ chế điều phối đã làm lượt hỏng.
}
```

Đây là đoạn xử lý minh họa; không đặt bước xử lý giai đoạn tiếp theo vô điều kiện ở sau toàn bộ `try/catch`.

Thời gian chờ thuộc từng lời gọi, không phải một bộ hẹn giờ toàn cục dùng chung cho cả nhóm. Một bên có thể đang dùng `await()` không giới hạn mà vẫn bị đưa ra bằng `BrokenBarrierException` khi bên khác hết hạn.

Hết hạn không tự dừng những phép tính khác còn đang chạy ngoài barrier, không hoàn tác dữ liệu chúng đã ghi và không hủy mọi tác vụ liên quan. Ứng dụng cần chính sách hủy hoặc dừng hợp tác cho cả nhóm.

Giá trị thời gian chờ bằng không cho phép thử mà không đợi thêm. Nếu chưa đủ bên, lời gọi có thể hết hạn và phá lượt; nếu chính bên gọi là bên cuối cùng đến một lượt hợp lệ thì vẫn có thể thành công. Ví dụ sau cố ý để thiếu một bên nên không phụ thuộc vào sự khác biệt này.

## 6. Ví dụ chạy được: nguyên nhân cục bộ và ảnh hưởng đến bên khác

Chương trình tạo barrier cần ba bên nhưng mỗi tình huống chỉ có hai bên xuất hiện. Điều đó bảo đảm không tình huống nào vô tình vượt rào thành công trước khi tạo lỗi.

Lưu thành `BarrierFailureDemo.java`:

```java
import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class BarrierFailureDemo {
    private static Thread peer(
            CyclicBarrier barrier,
            String[] outcome) {
        return new Thread(() -> {
            try {
                barrier.await();
                outcome[0] = "passed";
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                outcome[0] = "InterruptedException";
            } catch (BrokenBarrierException e) {
                outcome[0] = "BrokenBarrierException";
            }
        });
    }

    private static void timeoutCase() throws Exception {
        CyclicBarrier barrier = new CyclicBarrier(3);
        String[] peerOutcome = new String[1];
        Thread other = peer(barrier, peerOutcome);
        other.start();

        String cause;
        try {
            barrier.await(0, TimeUnit.NANOSECONDS);
            cause = "passed";
        } catch (TimeoutException e) {
            cause = "TimeoutException";
        }

        other.join();
        System.out.println("timeout.cause=" + cause);
        System.out.println("timeout.peer=" + peerOutcome[0]);
        System.out.println("timeout.broken=" + barrier.isBroken());
    }

    private static void interruptCase() throws InterruptedException {
        CyclicBarrier barrier = new CyclicBarrier(3);
        String[] peerOutcome = new String[1];
        String[] cause = new String[1];
        boolean[] restored = new boolean[1];

        Thread other = peer(barrier, peerOutcome);
        Thread interrupted = new Thread(() -> {
            Thread.currentThread().interrupt();
            try {
                barrier.await();
                cause[0] = "passed";
            } catch (InterruptedException e) {
                cause[0] = "InterruptedException";
                Thread.currentThread().interrupt();
                restored[0] = Thread.currentThread().isInterrupted();
            } catch (BrokenBarrierException e) {
                cause[0] = "BrokenBarrierException";
            }
        });

        other.start();
        interrupted.start();
        interrupted.join();
        other.join();

        System.out.println("interrupt.cause=" + cause[0]);
        System.out.println("interrupt.peer=" + peerOutcome[0]);
        System.out.println("interrupt.restored=" + restored[0]);
        System.out.println("interrupt.broken=" + barrier.isBroken());
    }

    public static void main(String[] args) throws Exception {
        timeoutCase();
        interruptCase();
    }
}
```

Chạy với JDK 17 trở lên:

```shell
javac --release 17 BarrierFailureDemo.java
java BarrierFailureDemo
```

Stdout khi chương trình không bị can thiệp bằng ngắt từ bên ngoài:

```text
timeout.cause=TimeoutException
timeout.peer=BrokenBarrierException
timeout.broken=true
interrupt.cause=InterruptedException
interrupt.peer=BrokenBarrierException
interrupt.restored=true
interrupt.broken=true
```

Trong mỗi tình huống, luồng còn lại có thể đã vào đợi hoặc đến sau khi barrier đã hỏng. Cả hai lịch đều cho nó `BrokenBarrierException`; ví dụ không cần quan sát trạng thái luồng để ép nó đã chờ.

Lời gọi `join()` cho phép luồng chính đọc các ô kết quả mà từng luồng đã ghi. Các dòng chỉ được in sau khi các luồng tương ứng kết thúc nên stdout không phụ thuộc thứ tự in giữa các luồng.

Đây là minh chứng về phân loại kết quả lỗi, không phải mẫu quản lý vòng đời hoàn chỉnh cho một dịch vụ. Ứng dụng thực tế còn phải xử lý lỗi khởi chạy, hủy nhóm và thu hồi tài nguyên.

## 7. Barrier action thất bại cũng phá lượt

Khi cấu hình action, bên đến cuối cùng chạy nó trước khi các bên được cho qua. Ví dụ minh họa:

```java
CyclicBarrier barrier = new CyclicBarrier(2, () -> {
    throw new IllegalStateException("Cannot merge partial results");
});
```

Khi đủ hai bên:

- Bên chạy action nhận `IllegalStateException` từ action.
- Bên đang đợi nhận `BrokenBarrierException`.
- Barrier ở trạng thái broken.

Chỉ bắt `InterruptedException` và `BrokenBarrierException` không tự thu nhận ngoại lệ runtime phát sinh trong action ở bên cuối. Cần đặt chính sách báo lỗi tại ranh giới tác vụ hoặc dùng cơ chế thu nhận kết quả phù hợp.

Không tiếp tục dùng kết quả tổng hợp nếu action thất bại giữa chừng. Barrier không hoàn tác những thay đổi action đã thực hiện trước khi ném ngoại lệ.

Một tác vụ ném ngoại lệ **trước khi gọi await** là tình huống khác: barrier không tự nhận biết rằng bên đó đã bỏ cuộc. Những bên đã đợi có thể chờ mãi nếu không có giới hạn thời gian, yêu cầu hủy hoặc điều phối riêng.

## 8. reset không phải lệnh thử lại an toàn cho mọi luồng

`reset()` đưa barrier về trạng thái ban đầu; các bên đang chờ của lượt cũ nhận `BrokenBarrierException`.

Nhưng tự gọi reset trong từng khối catch có thể tạo thêm cuộc đua:

```text
A phát hiện lỗi → reset
B vẫn xử lý lượt cũ
C đi vào lượt mới
B reset lần nữa → phá luôn lượt C đang đợi
```

Đừng viết vòng lặp “hỏng thì reset rồi await lại” độc lập ở từng bên. Các tác vụ có thể đang ở các giai đoạn dữ liệu khác nhau mà cùng đếm vào một lượt mới.

Quy trình phục hồi cần một bên điều phối:

1. Đánh dấu lượt hoặc toàn bộ lần chạy hiện tại là thất bại.
2. Yêu cầu các bên cũ dừng và thu nhận kết quả/lỗi.
3. Bảo đảm nhóm cũ không còn gọi vào barrier đang được phục hồi.
4. Chọn dữ liệu bắt đầu lại và cách xử lý tác dụng phụ của lượt thất bại.
5. Cho nhóm mới tham gia một barrier mới hoặc một barrier đã reset theo giao thức thống nhất.

Tạo barrier mới thường giúp tách vòng đời rõ ràng hơn. Số bên của `CyclicBarrier` là cố định; reset không thay nó thành một nhóm có số bên mới.

## 9. Dữ liệu và tính đúng sau lần await thất bại

Không coi `catch (BrokenBarrierException)` là đường hoàn tất thành công của giai đoạn.

Khi `await` thành công, barrier có hợp đồng phối hợp và công bố dữ liệu của các bên theo ranh giới lượt. Khi một bên đi ra bằng lỗi, không được dựa vào đó để khẳng định:

- Đã có đủ mọi phần kết quả.
- Action đã hoàn tất thành công.
- Mọi bên đều chuẩn bị xong cho giai đoạn kế tiếp.
- Dữ liệu của lượt thất bại tạo thành một ảnh chụp hợp lệ.

Nếu cần xem dữ liệu để chẩn đoán sau lỗi, dùng giao thức công bố khác phù hợp, chẳng hạn chờ tác vụ kết thúc bằng `join`/`Future.get`, hoặc lưu trạng thái lỗi bằng cấu trúc an toàn giữa các luồng.

Barrier cũng không thay thế khóa cho mọi dữ liệu dùng chung. Những phép ghi tranh chấp trước khi đến rào vẫn cần tổ chức đúng; barrier không sửa những cập nhật đã bị mất.

## 10. Những lỗi thiết kế thường gặp

- **Nuốt ngoại lệ rồi sang giai đoạn sau:** dữ liệu từng bên có thể không cùng lượt.
- **Coi BrokenBarrierException là nguyên nhân gốc:** nó thường chỉ là dấu hiệu một lỗi khác đã xảy ra.
- **Đặt thời gian chờ rồi tưởng mọi tác vụ sẽ tự bị hủy:** chỉ việc đợi đó kết thúc; công việc ngoài rào cần cơ chế dừng riêng.
- **Chờ khi giữ khóa mà bên khác cần để đến rào:** có thể gây bế tắc.
- **Nhóm thực thi quá ít luồng cho số tác vụ cần đồng thời đến rào:** các tác vụ đang đợi chiếm hết luồng, những bên còn thiếu không có cơ hội chạy.
- **Gọi reset từ mọi bên:** làm lẫn lượt cũ và lượt mới.
- **Dùng isBroken/getNumberWaiting để thay giao thức:** đây là quan sát trạng thái theo thời điểm, không đặt trước được kết quả của lời gọi await tiếp theo.

Thời gian chờ có thể giúp phát hiện một thiết kế không tiến triển, nhưng không thay thế việc sửa số bên, nguồn lực thực thi và thứ tự tài nguyên.

## 11. Tự kiểm tra

1. A hết hạn trong `await(timeout)`; B đang ở `await()`. Hai bên thường nhận ngoại lệ nào?
2. B bắt được `BrokenBarrierException`; có nên tự đặt cờ ngắt cho B không?
3. Một bên ném lỗi trong phần tính toán trước khi đến rào; barrier có tự biết bên đó sẽ không đến không?
4. Mọi bên đều reset trong catch có bảo đảm cùng bước vào một lượt dữ liệu mới không?
5. Một await thất bại có chứng minh các phần kết quả đã đủ để tổng hợp không?

Đáp án:

1. A nhận `TimeoutException`, B nhận `BrokenBarrierException` nếu không có ngắt riêng đồng thời.
2. Không; chỉ khôi phục ngắt khi chính luồng xử lý đường ngắt phù hợp.
3. Không; cần chính sách điều phối/hủy hoặc giới hạn thời gian.
4. Không; cần đồng bộ vòng đời ở ngoài barrier.
5. Không; phải xem lượt đó là thất bại và xác minh dữ liệu bằng giao thức riêng.

Khi xử lý lỗi barrier, cần quyết định rõ ai ghi nhận nguyên nhân đầu tiên, ai dừng các bên còn lại, và ai được phép tạo lượt chạy tiếp theo.

## Tài liệu đối chiếu

- [CyclicBarrier — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CyclicBarrier.html): await, trạng thái broken, action và reset.
- [BrokenBarrierException — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/BrokenBarrierException.html): ý nghĩa ngoại lệ khi rào đang hoặc trở thành broken.
