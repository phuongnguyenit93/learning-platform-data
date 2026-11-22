# Hành động tại barrier và hoàn tất một chặng

## 1. Vì sao “mọi bên đã đến” chưa phải là toàn bộ công việc?

Một phép tính song song thường được chia thành nhiều chặng. Trong mỗi chặng, các tác vụ xử lý phần riêng; trước khi sang chặng tiếp theo, chương trình cần ghép kết quả hoặc kiểm tra một điều kiện chung.

Ví dụ, ba tác vụ tính ba tổng thành phần:

```text
Tác vụ 0 → kết quả phần 0 ─┐
Tác vụ 1 → kết quả phần 1 ─┼→ ghép kết quả của chặng → chặng tiếp theo
Tác vụ 2 → kết quả phần 2 ─┘
```

Nếu các tác vụ chỉ chờ đủ bên rồi tự chạy tiếp, một tác vụ nhanh có thể bắt đầu chặng mới khi thao tác ghép kết quả chưa hoàn tất. Ta cần một ranh giới rõ:

1. Mọi bên hoàn thành phần riêng của chặng hiện tại.
2. Một hành động chung tổng hợp hoặc chuẩn bị trạng thái tiếp theo.
3. Chỉ sau khi hành động đó xong, các bên mới được tiếp tục.

`CyclicBarrier` hỗ trợ **hành động tại điểm đồng bộ (barrier action)** để thực hiện bước thứ hai.

## 2. Barrier action nằm ở đâu trong vòng đời một chặng?

Một `CyclicBarrier` được tạo với số bên tham gia cố định và một `Runnable` tùy chọn:

```java
// Mã minh họa.
CyclicBarrier barrier = new CyclicBarrier(3, () -> {
    mergeCurrentPhase();
});
```

Mỗi bên gọi `await()` sau khi hoàn tất phần của mình. Bên đến cuối thực hiện barrier action. Action chạy một lần cho lần mở barrier đó, sau khi đủ bên đến và trước khi các bên được giải phóng. Xem [hợp đồng CyclicBarrier](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CyclicBarrier.html).

```text
T0: tính phần riêng ─── await() ─── chờ ───────────────────── tiếp tục
T1: tính phần riêng ───────── await() ─── chờ ─────────────── tiếp tục
T2: tính phần riêng ───────────────── await() → action xong → tiếp tục
                                               ↑
                                  T2 là bên đến cuối trong ví dụ này
```

Bên đến cuối có thể thay đổi giữa các chặng. Không gán nghiệp vụ cho “luồng luôn chạy action” vì barrier không bảo đảm một luồng cố định.

Action không phải một tác vụ nền tự động được gửi tới nhóm thực thi khác. Chính luồng đến cuối chạy nó, nên mọi công việc trong action nằm trên đường tiến triển của cả nhóm.

## 3. “Hoàn tất chặng” phải có ý nghĩa cụ thể

Trong bài toán tổng hợp, có thể định nghĩa một chặng gồm:

- Các tác vụ ghi xong phần dữ liệu do mình sở hữu.
- Action đọc các phần đó và ghi kết quả tổng hợp.
- Action hoàn tất bình thường.
- Các lời gọi `await()` tương ứng trở về thành công.

Chỉ đủ lượt gọi `await()` chưa có nghĩa action thành công. Nếu action ném ngoại lệ, không thể coi kết quả chặng đã hợp lệ rồi tiếp tục như bình thường.

Barrier cũng không xác nhận các tác vụ đã làm đúng việc trước khi đến. Nếu một tác vụ bắt lỗi tính toán rồi vẫn gọi `await()` mà không công bố trạng thái lỗi, action có thể tổng hợp dữ liệu thiếu hoặc cũ. Cần quy định dữ liệu đầu vào và chính sách lỗi cho từng chặng.

## 4. Ví dụ đầy đủ: ba phần, ba chặng, một lần ghép mỗi chặng

Trong ví dụ:

- Có ba tác vụ, mỗi tác vụ sở hữu một phần tử của mảng `partials`.
- Ở chặng `phase`, tác vụ i ghi `(i + 1) * phase`.
- Barrier action cộng ba phần và in kết quả.
- Sau khi action kết thúc, tác vụ mới bước sang chặng kế tiếp.

Tệp `BarrierActionDemo.java`, chạy trên JDK 17 trở lên:

```java
import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class BarrierActionDemo {
    public static void main(String[] args) throws InterruptedException {
        int parties = 3;
        int rounds = 3;
        int[] partials = new int[parties];
        int[] completedPhases = {0};
        Throwable[] failures = new Throwable[parties];

        CyclicBarrier barrier = new CyclicBarrier(parties, () -> {
            int sum = 0;
            for (int value : partials) {
                sum += value;
            }
            completedPhases[0]++;
            System.out.println("phase=" + completedPhases[0] + ", sum=" + sum);
        });

        Thread[] workers = new Thread[parties];
        for (int i = 0; i < parties; i++) {
            final int index = i;
            workers[i] = new Thread(() -> {
                try {
                    for (int phase = 1; phase <= rounds; phase++) {
                        partials[index] = (index + 1) * phase;
                        barrier.await(5, TimeUnit.SECONDS);
                    }
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    failures[index] = interrupted;
                } catch (BrokenBarrierException | TimeoutException failure) {
                    failures[index] = failure;
                } catch (RuntimeException failure) {
                    failures[index] = failure;
                }
            });
            workers[i].start();
        }

        for (Thread worker : workers) {
            worker.join();
        }
        for (Throwable failure : failures) {
            if (failure != null) {
                throw new AssertionError("A phase failed", failure);
            }
        }
        System.out.println("completedPhases=" + completedPhases[0]);
        System.out.println("broken=" + barrier.isBroken());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 BarrierActionDemo.java
java BarrierActionDemo
```

Kết quả khi các bên đến đủ trong thời hạn:

```text
phase=1, sum=6
phase=2, sum=12
phase=3, sum=18
completedPhases=3
broken=false
```

Chặng thứ nhất: các phần là 1, 2, 3 nên tổng bằng 6. Chặng thứ hai: 2, 4, 6 nên tổng bằng 12. Chặng thứ ba: 3, 6, 9 nên tổng bằng 18.

Thứ tự các tác vụ đến không ảnh hưởng kết quả. Action chỉ tính khi mọi bên đã ghi xong phần của mình và đến barrier.

`completedPhases` do action cập nhật, không phải mọi tác vụ cùng tăng. Luồng chính chỉ đọc sau khi `join()` mọi luồng. Chương trình dùng biến mảng một phần tử để lambda có thể thay đổi giá trị lưu bên trong; bản thân biến tham chiếu được lambda bắt giữ không bị gán lại.

Timeout giúp ví dụ không chờ mãi tại barrier nếu một bên không đến. Nó không phải cam kết rằng toàn bộ chương trình hoặc barrier action sẽ hoàn tất trong đúng năm giây.

## 5. Tại sao dữ liệu của từng phần được nhìn thấy trong action?

Ranh giới đồng bộ của barrier có ý nghĩa về bộ nhớ:

```text
Ghi dữ liệu trước await()
    ↓ happens-before
Barrier action đọc/ghép dữ liệu
    ↓ happens-before
Các bên tiếp tục sau await() thành công
```

Đây là chuỗi quan hệ **xảy ra trước (happens-before)** được API quy định; xem phần Memory consistency effects của [CyclicBarrier](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CyclicBarrier.html).

Trong ví dụ, không cần biến từng phần tử `partials` thành biến nguyên tử vì:

1. Mỗi tác vụ chỉ ghi vào phần tử của chính mình.
2. Action chỉ đọc sau khi tất cả đã đến.
3. Không tác vụ nào sang lượt mới trước khi action xong.
4. Action chặng tiếp theo chỉ đọc sau khi mọi bên lại ghi xong lượt mới.

Chính giao thức sở hữu dữ liệu và ranh giới chặng làm ví dụ đúng. Barrier không tự biến mọi cấu trúc được dùng chung thành an toàn.

Nếu mọi tác vụ cùng sửa một `ArrayList` thường trước khi đến, chúng vẫn có thể gây tranh chấp khi sửa. Tương tự, nếu action giao việc ghép dữ liệu cho một tác vụ bất đồng bộ rồi trả về ngay, barrier chỉ chờ việc **giao công việc**, không chờ thao tác ghép thật sự hoàn tất.

### Dữ liệu giữa hai chặng cần được giữ ổn định đến khi nào?

Ví dụ không cho các tác vụ đọc toàn bộ `partials` sau `await()`; kết quả ghép đã được action xử lý xong. Nếu mỗi tác vụ cần đọc mảng chung sau khi barrier mở, một tác vụ nhanh có thể bắt đầu ghi dữ liệu chặng mới trong lúc tác vụ chậm còn đọc dữ liệu chặng cũ.

Khi đó cần một thiết kế bổ sung, chẳng hạn:

- Action xuất bản một ảnh chụp bất biến để các bên đọc.
- Dùng hai vùng dữ liệu, phân biệt rõ vùng đọc và vùng ghi theo chặng.
- Có thêm một điểm đồng bộ để xác nhận mọi bên đọc xong trước khi ghi đè.

Chọn cách nào tùy vòng đời dữ liệu. Không mặc định rằng một barrier ở cuối phần tính toán tự bảo vệ mọi thao tác đọc xảy ra sau nó.

## 6. Đừng thay action bằng “một bên làm sau await” khi cần thứ tự

`await()` trả về chỉ số thứ tự đến. Bên đến cuối nhận 0. Ta có thể gặp mẫu:

```java
// Mã minh họa.
if (barrier.await() == 0) {
    mergeCurrentPhase();
}
```

Mẫu này chọn một bên để làm công việc sau khi barrier đã mở. Các bên khác không phải chờ `mergeCurrentPhase()` hoàn tất trước khi tiếp tục.

Do đó:

| Nhu cầu | Cách diễn đạt |
| --- | --- |
| Ghi một thông báo mà các bên khác không cần chờ | Có thể chọn một bên qua chỉ số đến |
| Ghép dữ liệu mà chặng sau bắt buộc phải dùng | Barrier action hoặc một giao thức đồng bộ bổ sung |
| Giao việc phụ bất đồng bộ, không thuộc điều kiện hoàn tất chặng | Có thể tách riêng và quản lý vòng đời của việc phụ |

Điểm khác biệt là **thời điểm các bên được phép chạy tiếp**, không chỉ là số lần hàm ghép được gọi.

## 7. Action nên ngắn, xác định và không chờ vòng phụ thuộc

Action chạy trong lúc cả nhóm chưa được đi tiếp. Các việc thường phù hợp gồm cộng các kết quả thành phần, hoán đổi hai bộ đệm đã chuẩn bị, cập nhật số chặng hoặc xác định một điều kiện dừng chung.

Các việc cần cân nhắc kỹ:

- Truy cập mạng hoặc đĩa có thời gian chờ không ổn định.
- Chờ một khóa đang được một tác vụ giữ khi đi vào barrier.
- Chờ kết quả từ nhóm thực thi đang bị các bên của barrier chiếm hết chỗ.
- Gọi lại `await()` trên chính barrier để đợi một lượt mới.

Ví dụ vòng phụ thuộc:

```text
Các tác vụ đang chờ barrier mở
    ↓
Barrier action chờ một tác vụ mới trong cùng nhóm thực thi
    ↓
Không còn luồng trống để chạy tác vụ mới
    ↓
Action không xong, barrier không mở
```

Nếu công việc ghép cần nhiều bước song song, hãy thiết kế thành các pha công việc có tài nguyên thực thi phù hợp. Không giấu một luồng xử lý phức tạp bên trong action rồi kỳ vọng barrier tự điều phối hộ.

Một vấn đề khác là mất cân bằng tải: các bên nhanh vẫn phải chờ bên chậm nhất. Rút ngắn action không giải quyết được sự chênh lệch quá lớn giữa các phần tính toán; có thể cần chia lại công việc.

## 8. Action thất bại thì điều gì xảy ra?

Nếu action ném một ngoại lệ không kiểm tra:

- Luồng đang chạy action nhận ngoại lệ đó.
- Barrier chuyển sang trạng thái hỏng.
- Các bên đang chờ khác rời lần chờ với `BrokenBarrierException`.
- Các lần chờ tiếp trên barrier hỏng không tạo thành chặng bình thường mới cho đến khi có phục hồi phù hợp.

```java
// Mã minh họa lỗi trong action.
CyclicBarrier barrier = new CyclicBarrier(3, () -> {
    throw new IllegalStateException("Cannot merge this phase");
});
```

Vì vậy chỉ bắt `BrokenBarrierException` ở mọi tác vụ chưa đủ để nhận lỗi gốc từ bên chạy action. Chương trình cần thu thập hoặc chuyển tiếp lỗi của cả đường thực thi action.

`Runnable.run()` không khai báo checked exception. Nếu thao tác ghép gọi API có checked exception, phải xử lý hoặc chuyển đổi theo chính sách của ứng dụng. Bắt rồi bỏ qua lỗi để action trở về bình thường sẽ báo cho barrier rằng bước chung đã hoàn tất.

Một action lỗi sau khi đã sửa một phần trạng thái cũng không tự được hoàn tác. Nếu cần tránh trạng thái dở dang, hãy tính kết quả mới trước rồi chỉ xuất bản khi hợp lệ, hoặc thiết kế cơ chế khôi phục rõ ràng.

## 9. Timeout, ngắt và reset phải được nhìn ở cấp cả nhóm

Khi một bên đang chờ bị ngắt hoặc hết thời hạn, việc đồng bộ của lượt đó bị phá vỡ. Bên gặp timeout nhận `TimeoutException`; các bên đang chờ khác thường nhận `BrokenBarrierException`, hoặc nhận `InterruptedException` nếu chính chúng cũng bị ngắt.

Phải phân biệt:

- **Timeout khi đang đợi đủ bên** không có nghĩa một chặng đã hoàn tất.
- **Barrier hỏng** không tự dừng những tác vụ còn đang tính và chưa gọi `await()`.
- **Thời hạn của await** không phải cơ chế cưỡng bức dừng barrier action đang chạy.
- **reset()** thay đổi trạng thái barrier, không hoàn tác dữ liệu của chặng lỗi và không làm mọi tác vụ tự quay về cùng một bước.

Nếu một tác vụ tự gọi `reset()` rồi thử lại trong khi các tác vụ khác vẫn ở chặng trước, các lượt đến có thể bị trộn theo một giao thức sai. Thường cần bên điều phối quyết định dừng đợt cũ, thu thập trạng thái lỗi, xác nhận mọi bên đã thoát rồi mới tạo đợt mới.

Ở ví dụ đầy đủ, tác vụ ghi nhận ngoại lệ và kết thúc; luồng chính kiểm tra sau khi chờ các luồng. Chương trình không tự reset rồi giả định kết quả vẫn dùng được.

## 10. Giữ cùng số chặng và cùng quy tắc kết thúc

Với ba bên tham gia, cả ba phải gọi `await()` đúng một lần cho từng chặng hợp lệ. Nếu một bên chạy hai chặng rồi thoát nhưng hai bên kia còn chờ chặng thứ ba, chặng đó không thể mở bình thường.

Nếu điều kiện dừng được action quyết định, nên công bố cùng một kết quả dừng cho mọi bên trước khi giải phóng chúng. Mỗi bên kiểm tra điều kiện đó sau `await()` rồi cùng dừng theo giao thức.

Nếu số bên cần tham gia thay đổi theo thời gian, `CyclicBarrier` với số bên cố định có thể không phải mô hình phù hợp. `Phaser` hỗ trợ đăng ký, hủy đăng ký và hành động khi chuyển pha qua `onAdvance`; xem [Phaser](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Phaser.html). Không dùng `reset()` của barrier như cách tùy tiện thay thế việc quản lý số bên.

## 11. Bài tập kiểm tra hiểu biết

1. Chuyển phần cộng và in từ barrier action sang nhánh `if (barrier.await() == 0)`. Những tác vụ khác có thể ghi dữ liệu chặng sau trước khi cộng xong không? Có, vì barrier đã mở; cần một giao thức khác nếu muốn giữ cùng bảo đảm.
2. Cho action ném `IllegalStateException` ở chặng thứ hai. Dự đoán lỗi gốc thuộc về luồng nào: luồng đến cuối tại chặng đó, không nhất thiết là một tác vụ có chỉ số cố định.
3. Chạy ba tác vụ chờ barrier ba bên trên nhóm thực thi chỉ có hai luồng. Hai bên có thể chiếm hết chỗ và chờ bên thứ ba đang xếp hàng; cần thiết kế đủ khả năng tiến triển.
4. Vì sao không đọc toàn bộ mảng kết quả sau timeout như sau một chặng thành công? Vì không có bảo đảm rằng tất cả phần đã được ghi và action đã công bố kết quả hợp lệ.

Barrier action hữu ích khi nó diễn đạt rõ bước chuyển: **mọi phần của chặng hiện tại đã sẵn sàng, trạng thái chung được hoàn tất, rồi cả nhóm mới tiếp tục**.
