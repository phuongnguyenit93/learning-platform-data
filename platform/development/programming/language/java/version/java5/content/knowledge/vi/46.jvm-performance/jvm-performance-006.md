# System.nanoTime cho đo khoảng thời gian

## 1. Cần đo “mất bao lâu” hay “xảy ra lúc nào”?

Hai câu hỏi này cần hai loại thời gian khác nhau:

| Câu hỏi | Loại dữ liệu phù hợp |
| --- | --- |
| Một thao tác kéo dài bao lâu? | Khoảng thời gian từ hai mốc nanoTime |
| Tác vụ xảy ra vào ngày giờ nào? | Mốc thời gian lịch, chẳng hạn Instant |
| Luồng dùng bao nhiêu CPU? | Bộ đếm CPU time phù hợp |
| Khi nào ngân sách chờ đã hết? | Thời gian đã trôi qua so với một khoảng cho phép |

`System.nanoTime()` phục vụ **đo khoảng thời gian trôi qua**. Kết quả có đơn vị nano giây nhưng không phải số nano giây kể từ năm 1970 và không dùng để tạo ngày giờ.

Công thức cơ bản:

```java
long start = System.nanoTime();
// Thực hiện công việc cần đo.
long elapsedNanos = System.nanoTime() - start;
```

Ý nghĩa nằm ở hiệu hai mốc lấy trong cùng JVM. Hợp đồng chi tiết có ở [System.nanoTime()](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html#nanoTime()).

## 2. Hiểu đúng giá trị trả về

`nanoTime()` trả `long` từ nguồn thời gian có gốc tùy ý, thống nhất trong một JVM. Một giá trị mốc âm không phải lỗi.

Do đó, không làm những việc sau:

- Ghi mốc nanoTime như một timestamp có thể chuyển sang ngày giờ.
- So sánh mốc từ hai tiến trình JVM khác nhau.
- Lưu mốc rồi dùng sau khi ứng dụng khởi động lại như thể gốc vẫn giữ nguyên.
- So sánh một mốc nanoTime trực tiếp với currentTimeMillis.
- Loại bỏ một mốc chỉ vì nó âm.

Đơn vị nano giây cũng không bảo đảm đồng hồ thay đổi mỗi một nano giây. Độ mịn biểu diễn, độ phân giải thực tế và chi phí gọi hàm là các khái niệm khác nhau. Tài liệu [System](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html) chỉ cam kết mức phân giải tối thiểu theo hợp đồng, không hứa độ chính xác vật lý một nano giây cho mọi môi trường.

Một hiệu bằng 0 với công việc rất ngắn không chứng minh công việc “miễn phí”. Nó có thể nhỏ hơn mức nguồn thời gian phân biệt được trong lần quan sát.

## 3. Thời gian trôi qua không phải thời gian CPU

Đặt hai mốc quanh một thao tác chờ cũng đo được khoảng thời gian. Kết quả có thể gồm:

- Công việc CPU của chính luồng.
- Thời gian chờ khóa hoặc I/O.
- Khoảng luồng không được lập lịch chạy.
- Tác động của hoạt động JVM và hệ điều hành trong khoảng đó.

Vì thế, nếu đo một yêu cầu từ lúc nhận đến lúc hoàn tất, kết quả phù hợp với độ trễ được quan sát ở phạm vi đó. Nó không tự tách ra bao nhiêu thời gian dùng CPU, bao nhiêu chờ cơ sở dữ liệu hoặc bao nhiêu do GC.

Muốn phân tích nguyên nhân, cần thêm nguồn đo khác. Đừng đặt nhãn “CPU time” cho một hiệu nanoTime.

## 4. Ví dụ chạy được: phép tính cố định và đo thật

Lưu thành **NanoTimeDemo.java**, dùng Java 17 trở lên:

```java
import java.util.Locale;
import java.util.concurrent.TimeUnit;

public class NanoTimeDemo {
    public static void main(String[] args) throws InterruptedException {
        if (args.length == 0) {
            long start = 1_000_000L;
            long end = 3_500_000L;
            long elapsed = end - start;
            System.out.println("elapsed-ns=" + elapsed);
            System.out.println("whole-ms="
                    + TimeUnit.NANOSECONDS.toMillis(elapsed));
            System.out.printf(Locale.ROOT,
                    "decimal-ms=%.3f%n", elapsed / 1_000_000.0);

            long startNearWrap = Long.MAX_VALUE - 5L;
            long endAfterWrap = Long.MIN_VALUE + 4L;
            long wrappedElapsed = endAfterWrap - startNearWrap;
            System.out.println("wrapped-elapsed-ns=" + wrappedElapsed);
            System.out.println("timeout-reached="
                    + expired(startNearWrap, endAfterWrap, 10L));
            return;
        }

        if (args.length != 1 || !"--live".equals(args[0])) {
            throw new IllegalArgumentException("Use no arguments or --live");
        }

        long start = System.nanoTime();
        Thread.sleep(20L);
        long elapsed = System.nanoTime() - start;

        System.out.println("elapsed-ns=" + elapsed);
        System.out.printf(Locale.ROOT,
                "elapsed-ms=%.3f%n", elapsed / 1_000_000.0);
    }

    private static boolean expired(long start, long now, long timeoutNanos) {
        if (timeoutNanos < 0L) {
            throw new IllegalArgumentException("Negative timeout");
        }
        return now - start >= timeoutNanos;
    }
}
```

Biên dịch và chạy chế độ cố định:

```shell
javac NanoTimeDemo.java
java NanoTimeDemo
```

Stdout chính xác:

```text
elapsed-ns=2500000
whole-ms=2
decimal-ms=2.500
wrapped-elapsed-ns=10
timeout-reached=true
```

Các mốc của chế độ mặc định là số tự tạo để kiểm tra phép tính. Phần tràn số mô phỏng điểm mốc đi qua ranh giới của long; không cần chạy JVM nhiều năm để thử nguyên tắc.

Đo khoảng chờ thật:

```shell
java NanoTimeDemo --live
```

Hai dòng có nhãn elapsed-ns và elapsed-ms nhưng số cụ thể thay đổi. Không kiểm thử bằng một kết quả cố định như “đúng 20.000 ms”. Lời gọi ngủ yêu cầu chờ, không cam kết luồng tiếp tục chạy đúng tại một thời điểm tuyệt đối.

Ví dụ này minh họa cách dùng đồng hồ và đơn vị. Nó không đo hiệu năng thuật toán hay chi phí của sleep như một chuẩn so sánh hệ thống.

## 5. Đổi đơn vị mà không mất ý nghĩa

Một giây bằng 1.000.000.000 nano giây; một mili giây bằng 1.000.000 nano giây.

Để giữ phần lẻ:

```java
// elapsedNanos là một khoảng hợp lệ đã tính.
double millis = elapsedNanos / 1_000_000.0;
```

Nếu dùng phép chia số nguyên:

```java
long wholeMillis = elapsedNanos / 1_000_000L;
```

Phần nhỏ hơn mili giây bị bỏ. Tương tự, `TimeUnit.NANOSECONDS.toMillis()` chuyển sang số mili giây nguyên. `2_500_000 ns` thành `2 ms`, không làm tròn thành 3.

[TimeUnit](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/TimeUnit.html) giúp thể hiện rõ đơn vị và có quy tắc chuyển đổi khi không thể biểu diễn. Không suy ra timeout có độ phân giải một nano giây chỉ vì tham số dùng NANOSECONDS.

Có thể biểu diễn khoảng thời gian bằng:

```java
java.time.Duration duration = java.time.Duration.ofNanos(elapsedNanos);
```

[Duration](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Duration.html) biểu diễn một lượng thời gian; nó không tự biến mốc nanoTime thành thời điểm lịch.

Giữ giá trị gốc bằng long và ghi đơn vị trong tên biến hoặc chỉ số. Tránh lưu một số tên “duration” mà không biết đó là ns, ms hay giây.

## 6. Timeout: lấy hiệu thay vì cộng vào mốc

Mẫu so sánh nên dùng:

```java
// Đoạn minh họa; start và timeoutNanos thuộc cùng một ngân sách chờ.
if (System.nanoTime() - start >= timeoutNanos) {
    // Ngân sách thời gian đã hết.
}
```

Tránh mẫu:

```java
// Cách dễ sai do phép cộng mốc có thể tràn.
if (System.nanoTime() >= start + timeoutNanos) {
    // ...
}
```

Phép cộng có thể đi qua ranh giới long và làm phép so sánh mốc sai. Phép trừ theo hiệu là mẫu được nêu trong [hợp đồng nanoTime](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html#nanoTime()).

Mẫu này vẫn có điều kiện phạm vi: khoảng thực cần đo phải nhỏ hơn `2^63` nano giây, xấp xỉ 292 năm. Không coi phép trừ là giải pháp cho khoảng dài tùy ý, hoặc cho mốc lấy từ nguồn/JVM khác.

Với timeout của ứng dụng:

1. Xác định timeout không âm và đơn vị ngay từ đầu.
2. Chuyển đổi có kiểm tra giới hạn theo hợp đồng của API dùng.
3. Lấy mốc bắt đầu một lần cho ngân sách tổng.
4. Trước bước tiếp theo, tính thời gian đã trôi qua và thời gian còn lại.
5. Dùng API chờ có timeout phù hợp, thay vì quay vòng kiểm tra liên tục.

Ví dụ giả định một thao tác gồm ba bước với ngân sách tổng 1 giây. Nếu mỗi bước đều nhận lại đủ 1 giây thì toàn thao tác có thể kéo dài hơn nhiều. Cần truyền phần ngân sách còn lại hoặc dùng cơ chế deadline phù hợp của thư viện.

Kiểm tra đồng hồ chỉ phát hiện ngân sách đã hết ở thời điểm kiểm tra. Nó không tự hủy I/O, ngắt luồng hay làm tác vụ không hợp tác dừng ngay.

## 7. Chọn đúng hai đầu của phép đo

Trước khi viết mã, quyết định đo phạm vi nào:

| Phạm vi | Hai đầu nên đại diện cho |
| --- | --- |
| Thời gian xử lý một lời gọi đồng bộ | Ngay trước gọi và sau khi lời gọi hoàn tất |
| Thời gian yêu cầu gồm chờ hàng đợi | Trước khi đưa vào hàng đợi và khi kết quả hoàn tất |
| Công việc bất đồng bộ | Lúc bắt đầu cần quan sát và lúc kết quả thực sự hoàn tất |
| Một bước nội bộ | Chỉ bao quanh bước đó, có nhãn rõ |

Một lỗi thường gặp là đo lúc gửi tác vụ vào executor rồi dừng ngay khi lời gọi submit trả về. Kết quả khi đó chủ yếu nói về thời gian gửi, không phải thời gian hoàn tất tác vụ.

Nếu mốc bắt đầu được chuyển sang luồng khác trong cùng JVM, phải truyền nó bằng cơ chế phối hợp luồng đúng, như cấu trúc thông điệp hoặc future phù hợp. nanoTime không thay thế quy tắc an toàn khi chia sẻ dữ liệu giữa các luồng.

Không ghép mốc bắt đầu trên dịch vụ A và kết thúc trên dịch vụ B bằng phép trừ trực tiếp nanoTime. Với theo dõi phân tán, dùng cơ chế theo dõi có mô hình thời gian và đồng bộ phù hợp; giữ khoảng cục bộ ở từng tiến trình.

## 8. Đo cả đường thành công và đường lỗi

Nếu cần ghi thời gian dù công việc thành công hay ném ngoại lệ, một khối finally có thể bao quanh phạm vi đo:

```java
// Mẫu tích hợp, không phải chương trình độc lập.
long start = System.nanoTime();
try {
    runOperation();
} finally {
    long elapsedNanos = System.nanoTime() - start;
    recordDuration(elapsedNanos);
}
```

Phải định nghĩa nhãn kết quả riêng nếu muốn phân biệt thành công, lỗi hoặc hủy. Một histogram chung có thể trộn yêu cầu lỗi rất nhanh với yêu cầu thành công chậm.

Lời gọi ghi số liệu cũng có chi phí và có thể lỗi nếu thiết kế không phù hợp. Tránh để lỗi ở đường ghi thời gian che ngoại lệ nghiệp vụ ban đầu. Ví dụ trên diễn đạt phạm vi đo; phần triển khai recordDuration cần tuân theo chính sách vận hành của ứng dụng.

Nếu không muốn tính chi phí xuất số liệu vào chính thời lượng thao tác, lấy mốc kết thúc trước khi định dạng hoặc gửi dữ liệu, như trong mẫu trên.

## 9. Đúng đồng hồ chưa đủ để thành phép thử hiệu năng tốt

Hai lần nanoTime bao quanh đoạn mã chỉ cho một lần quan sát. Kết quả có thể chịu ảnh hưởng của làm nóng JVM, JIT, GC, tối ưu hóa loại bỏ công việc, tải nền và lịch CPU.

Các lỗi phổ biến:

- Đo một thao tác quá nhỏ so với chi phí lấy mốc.
- Không sử dụng kết quả, khiến trình tối ưu loại bỏ công việc.
- In ra màn hình ngay trong đoạn cần đo rồi coi đó là chi phí thuật toán.
- Chỉ chọn lần chạy nhanh nhất và bỏ qua mọi lần chậm.
- Lặp nhiều lần nhưng không kiểm soát thay đổi trạng thái hoặc dữ liệu đầu vào.
- Dùng trung bình để suy ra p99 hoặc thời gian tệ nhất.

Khi cần benchmark vi mô cho Java/JVM, xem [OpenJDK JMH](https://github.com/openjdk/jmh), công cụ chuyên cho các phép thử hiệu năng kiểu này. nanoTime vẫn là công cụ thích hợp để ghi nhận khoảng thời gian trong ứng dụng; lựa chọn đồng hồ và thiết kế benchmark là hai tầng vấn đề khác nhau.

Không lấy một lần chạy ví dụ ngủ 20 ms làm bằng chứng hệ thống nào nhanh hơn. Với số liệu vận hành, nhìn phân bố và ngữ cảnh của nhiều mẫu thay vì một số đơn lẻ.

## 10. Tự kiểm tra

1. Mốc nanoTime âm có hợp lệ không? **Có.**
2. Có thể chuyển trực tiếp mốc ấy thành Instant không? **Không.**
3. 2.500.000 ns chuyển sang mili giây nguyên là bao nhiêu? **2 ms**; nếu cần phần lẻ, dùng phép đổi phù hợp.
4. Vì sao so sánh timeout bằng hiệu? **Tránh lỗi so sánh mốc do cộng tràn**, trong phạm vi đo hợp lệ.
5. Thời gian đo quanh lời gọi chờ có phải CPU time không? **Không.**
6. Đo xong submit có nghĩa tác vụ đã hoàn thành không? **Không.**

Kỹ năng cần đạt là chọn hai đầu đo đúng phạm vi, lấy hiệu trong cùng JVM, giữ đơn vị rõ và diễn giải kết quả theo giới hạn thực tế của phép quan sát.
