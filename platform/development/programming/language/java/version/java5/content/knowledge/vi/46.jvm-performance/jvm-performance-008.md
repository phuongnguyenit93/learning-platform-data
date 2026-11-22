# Đơn vị nanosecond và giới hạn độ phân giải thực tế

## 1. Một số đo mang đơn vị ns chưa có nghĩa đo được từng ns

Một nanosecond (ns) là một phần tỷ giây. Trong Java, `System.nanoTime()` trả giá trị bằng đơn vị này, nhưng nguồn thời gian không bắt buộc thay đổi sau mỗi 1 ns.

Cần phân biệt bốn khái niệm:

| Khái niệm | Câu hỏi nó trả lời |
| --- | --- |
| Đơn vị biểu diễn | Con số được tính bằng ns, µs, ms hay giây? |
| Độ phân giải (resolution) | Nguồn thời gian có thể phân biệt những thay đổi nhỏ đến mức nào? |
| Độ chính xác của phép đo (accuracy) | Kết quả gần khoảng thời gian thực đến đâu? |
| Mức dao động giữa các lần đo | Cùng cách đo nhưng kết quả thay đổi bao nhiêu? |

Tài liệu Java nói rõ `nanoTime()` có độ mịn biểu diễn ở mức nanosecond nhưng không bảo đảm độ phân giải nanosecond. Xem [System.nanoTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#nanoTime()).

Ví dụ giả định, một nguồn thời gian chỉ cho các mức đọc cách nhau 100 ns:

```text
Thời điểm thực tương đối:  0     30     70     100     150 ns
Giá trị nguồn quan sát:    0      0      0     100     100 ns
```

Đây là mô hình minh họa lượng tử hóa, không phải cam kết mọi JVM dùng bước 100 ns. Hai lần đọc bằng nhau có thể bao quanh một đoạn công việc có thời gian khác 0 nhưng chưa đủ để nguồn thời gian thể hiện một mức khác.

Thêm chữ số sau dấu phẩy, đổi sang đơn vị nhỏ hơn hoặc lưu trong một kiểu số lớn hơn không tự làm nguồn đo phân giải tốt hơn.

## 2. Tại sao giá trị quan sát còn phụ thuộc môi trường?

JVM phải dựa vào nguồn thời gian và cách triển khai trên hệ điều hành/phần cứng. Không nên lấy một con số độ phân giải đo trên máy cá nhân làm thuộc tính cố định của ngôn ngữ Java.

Ngoài nguồn thời gian, **khoảng cách giữa hai lần gọi mà chương trình quan sát được** còn chịu ảnh hưởng của chính chương trình và việc chạy nó:

- Chi phí gọi hàm đọc thời gian.
- Lệnh của vòng lặp, lưu kết quả và nhánh điều kiện.
- Trạng thái biên dịch JIT và giai đoạn khởi động.
- Ngắt, luồng bị tạm dừng để hệ điều hành chạy công việc khác.
- Hoạt động GC hoặc tác vụ cùng chạy trên máy.

Các yếu tố này có thể làm khoảng cách quan sát lớn hơn. Không gọi mọi biến động do lập lịch hay GC là “độ phân giải đồng hồ”. Đó là những thành phần khác nhau của phép đo.

Tương tự, độ phân giải tốt không bảo đảm một phép đo duy nhất có sai số rất nhỏ. Một đồng hồ có bước thay đổi nhỏ vẫn có thể được dùng trong một phép đo bị nhiễu hoặc thiết kế sai.

## 3. nanoTime dùng để đo khoảng thời gian, không phải giờ lịch

Cách dùng cơ bản:

```java
long start = System.nanoTime();
// Thuc hien cong viec can do.
long elapsedNanos = System.nanoTime() - start;
```

Đây là đoạn minh họa vị trí đo; phần công việc thực cần được đặt giữa hai lần đọc.

Các giá trị tuyệt đối của `nanoTime()` có gốc tùy ý. Nó không phải số nanosecond từ Unix epoch, không nên chuyển trực tiếp thành ngày/giờ, và có thể mang giá trị âm.

Chỉ so sánh hai giá trị trong cùng miền thời gian của một JVM để lấy độ chênh. Không lưu một `nanoTime` thô rồi dùng nó làm mốc chung giữa hai tiến trình hoặc sau khi khởi động lại.

Muốn ghi thời điểm sự kiện theo giờ lịch thì dùng API thời điểm phù hợp, chẳng hạn `Instant`. Muốn đo thời gian đã trôi qua của thao tác trong tiến trình thì dùng nguồn dành cho elapsed time như `nanoTime()`. Hai loại dữ liệu trả lời hai câu hỏi khác nhau.

Với timeout, nên kiểm tra độ chênh:

```java
long startedAt = System.nanoTime();
long timeoutNanos = TimeUnit.MILLISECONDS.toNanos(250);

// Tai moi diem kiem tra cua vong doi thao tac:
boolean expired = System.nanoTime() - startedAt >= timeoutNanos;
```

Đây là đoạn tích hợp, cần `import java.util.concurrent.TimeUnit;`. Không dùng nó để tự quay vòng bận khi đang đợi I/O.

Mẫu trừ mốc tránh vấn đề cộng deadline có thể tràn số. Khoảng chênh vẫn phải nằm trong miền biểu diễn hợp lệ; một `long` nanosecond có giới hạn khoảng 292 năm cho phép đo chênh kiểu này. Những giới hạn số học và mốc tùy ý hoàn toàn độc lập với việc đồng hồ có độ phân giải bao nhiêu.

## 4. Chuyển đơn vị có thể làm mất phần lẻ

Các quan hệ:

```text
1 µs = 1.000 ns
1 ms = 1.000.000 ns
1 s  = 1.000.000.000 ns
```

Một khoảng thời gian 999.999 ns bằng 0,999999 ms. Nếu chuyển sang số millisecond nguyên, kết quả là 0 ms; điều đó không có nghĩa thao tác không mất thời gian.

`TimeUnit` cắt phần lẻ khi đổi từ đơn vị nhỏ sang đơn vị lớn. Khi đổi theo chiều có thể tràn số, nó có quy tắc bão hòa về giới hạn `long`; không nên xem phép chuyển là lúc nào cũng chính xác tuyệt đối. Xem [TimeUnit](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/TimeUnit.html).

Khi cần hiển thị phần lẻ:

```java
double milliseconds = elapsedNanos / 1_000_000.0;
```

Số `1_000_000.0` làm phép chia dùng số thực. Nếu viết `elapsedNanos / 1_000_000` rồi mới gán sang `double`, phần lẻ đã bị mất bởi phép chia số nguyên.

Ngược lại, lấy `currentTimeMillis()` rồi nhân 1.000.000 chỉ đổi cách biểu diễn sang ns. Nó không phục hồi phần thời gian nhỏ hơn mà nguồn ban đầu chưa cung cấp.

`Duration` cũng có thể biểu diễn phần nanosecond, nhưng đó là khả năng của mô hình dữ liệu, không phải bằng chứng nguồn tạo ra nó đo được từng ns. Một số phép chuyển, chẳng hạn chuyển một duration quá lớn thành tổng số nanosecond trong `long`, có thể vượt miền số. Xem [Duration](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Duration.html).

## 5. Ví dụ chạy được: đổi đơn vị và quan sát khoảng cách giữa lần đọc

Chương trình sau có hai chế độ:

- Mặc định: chỉ minh họa việc đổi đơn vị, có output xác định.
- Với `--sample`: lấy mẫu các khoảng cách liên tiếp của `nanoTime()`. Đây là thí nghiệm quan sát, không phải công cụ chứng nhận độ phân giải phần cứng hay benchmark cho một thao tác nghiệp vụ.

Lưu thành `NanoResolutionDemo.java`:

```java
import java.util.Arrays;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

public class NanoResolutionDemo {
    public static void main(String[] args) {
        long value = 999_999L;
        System.out.println("wholeMillis="
                + TimeUnit.NANOSECONDS.toMillis(value));
        System.out.printf(Locale.ROOT, "decimalMillis=%.6f%n",
                value / 1_000_000.0);

        if (args.length == 0 || !args[0].equals("--sample")) {
            return;
        }

        int count = 100_000;
        long[] gaps = new long[count];
        long previous = System.nanoTime();
        for (int i = 0; i < count; i++) {
            long current = System.nanoTime();
            gaps[i] = current - previous;
            previous = current;
        }

        Arrays.sort(gaps);
        int zeroCount = 0;
        long minimumPositive = Long.MAX_VALUE;
        for (long gap : gaps) {
            if (gap == 0) {
                zeroCount++;
            } else if (gap > 0 && gap < minimumPositive) {
                minimumPositive = gap;
            }
        }

        System.out.println("samples=" + count);
        System.out.println("zeroGaps=" + zeroCount);
        System.out.println("minimumPositiveNs="
                + (minimumPositive == Long.MAX_VALUE
                    ? "none" : Long.toString(minimumPositive)));
        System.out.println("p50ObservedGapNs=" + gaps[(count - 1) / 2]);
        System.out.println("p99ObservedGapNs=" + gaps[(count * 99 / 100) - 1]);
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```shell
javac --release 17 -encoding UTF-8 NanoResolutionDemo.java
java NanoResolutionDemo
```

Output của chế độ mặc định:

```text
wholeMillis=0
decimalMillis=0.999999
```

Chạy chế độ lấy mẫu:

```shell
java NanoResolutionDemo --sample
```

Hoặc chạy trực tiếp tệp nguồn:

```shell
java NanoResolutionDemo.java --sample
```

Một lần chạy thực tế trên Windows với JDK 24 cho kết quả:

```text
wholeMillis=0
decimalMillis=0.999999
samples=100000
zeroGaps=60663
minimumPositiveNs=100
p50ObservedGapNs=0
p99ObservedGapNs=100
```

Các dòng thống kê sau `samples` có thể thay đổi ở mỗi lần chạy và trên máy khác. Không viết test yêu cầu các giá trị đó luôn bằng mẫu.

Cách đọc:

- `zeroGaps` đếm số cặp lần đọc trả cùng giá trị. Nó không đếm số thao tác chạy trong thời gian thực bằng 0.
- `minimumPositiveNs` là khoảng cách dương nhỏ nhất **đã quan sát** trong phép lấy mẫu này.
- `p50ObservedGapNs` và `p99ObservedGapNs` là phân vị của khoảng cách lấy mẫu, không phải độ trễ của một phương thức được đo riêng.
- Giá trị 100 không chứng minh độ phân giải chính xác của mọi nguồn thời gian trên máy là 100 ns.
- Khoảng cách có cả chi phí đọc, ghi mảng và vòng lặp giữa hai thời điểm; không xem nó là phép đo thuần chi phí của `nanoTime()`.
- Việc sắp xếp và in được thực hiện sau khi thu mẫu để không chèn I/O console vào từng khoảng lấy mẫu.

Nếu không có khoảng cách dương trong một lần lấy mẫu, chương trình in `none`; không tự chia cho 0 hoặc thay bằng một số đo bịa đặt.

## 6. Vì sao lấy mẫu này chưa phải đo độ phân giải chính xác?

Quan sát có giới hạn. Chương trình không đọc được đồng hồ ở mọi thời điểm thực. Nếu mỗi lần gọi và phần mã giữa chúng mất nhiều thời gian hơn một bước nguồn, các bước nhỏ hơn có thể không xuất hiện trong mẫu.

Ví dụ:

```text
Nguồn có thể thay đổi theo các bước nhỏ
        ↓
Chương trình chỉ lấy mẫu ở một số thời điểm
        ↓
Khoảng cách quan sát bao gồm cả khoảng thời gian không được lấy mẫu
```

Do đó, “khoảng cách dương nhỏ nhất” là một dữ kiện của thí nghiệm, không tự trở thành:

- Độ chính xác tuyệt đối của nguồn thời gian.
- Chi phí cố định của một lần gọi.
- Thời gian chạy của một phép cộng.
- Giới hạn nhỏ nhất mà mọi phép đo trung bình có thể báo cáo.

Nếu cần kết luận về nguồn thời gian, phải xem tài liệu nền tảng và thiết kế phép đánh giá phù hợp. Nếu cần kết luận về hiệu năng một đoạn mã, phải thiết kế benchmark cho chính đoạn mã đó.

Không cần đổi đơn vị toàn bộ ứng dụng sang một hằng số “tick size” tự suy ra từ một lần lấy mẫu. Giữ đơn vị chuẩn và diễn giải giới hạn của nguồn đo rõ ràng thường phù hợp hơn.

## 7. Timer độ phân giải hữu hạn vẫn có thể cho số trung bình nhỏ hơn một bước

Giả sử một thí nghiệm tổng hợp đo 100.000 thao tác mất 1.000.000 ns:

```text
Trung bình = 1.000.000 / 100.000 = 10 ns/thao tác
```

Con số trung bình có thể nhỏ hơn bước thay đổi mà một lần đọc đồng hồ quan sát được. Điều này không tự mâu thuẫn: ta đo một khoảng tổng đủ dài rồi chia cho số thao tác.

Nhưng nó cũng không chứng minh từng thao tác riêng lẻ đều mất đúng 10 ns. Kết quả trung bình không mô tả đầy đủ phân bố hoặc độ trễ từng lần.

Đặc biệt trên JVM, tự đặt một vòng lặp lớn rồi chia thời gian có thể sai vì mã được JIT tối ưu theo cách khác với tình huống sử dụng thật:

- Kết quả không được dùng có thể bị loại bỏ.
- Đầu vào hằng có thể làm phép tính được rút gọn.
- Đo lần đầu có thể tính cả nạp lớp hoặc biên dịch.
- Trộn nhiều trường hợp trong một tiến trình có thể ảnh hưởng cách tối ưu.
- Bộ nhớ đệm, cấp phát và GC có thể làm các lần chạy khác nhau.

Khi cần microbenchmark có thể so sánh, dùng một công cụ chuyên dụng như [JMH của OpenJDK](https://github.com/openjdk/jmh), với thiết kế warmup, lần chạy độc lập, dữ liệu đầu vào và việc tiêu thụ kết quả phù hợp. Tên đơn vị `ns/op` trong báo cáo là cách biểu diễn kết quả; nó không nâng cấp phần cứng lên độ chính xác 1 ns.

Nếu chênh lệch hai phương án nhỏ hơn dao động/sai số của phép đo, không kết luận phương án nhanh hơn chỉ vì một lần chạy cho số thấp hơn.

## 8. Timeout và sleep nhận nanosecond không bảo đảm đánh thức sau đúng từng ns

Một API nhận thời lượng nanosecond chỉ xác định đơn vị tham số. Nó không cam kết hệ điều hành sẽ chạy lại luồng đúng thời điểm đó.

Ví dụ, yêu cầu chờ rất ngắn còn chịu ảnh hưởng của cơ chế hẹn giờ, lịch chạy và thời điểm luồng được cấp CPU trở lại. Độ phân giải đọc thời gian và khả năng hẹn giờ/đánh thức là hai khả năng khác nhau.

Không dùng `sleep(1 ns)` làm cách “hiệu chuẩn” độ phân giải của `nanoTime()`. Khi đo thời gian quanh lời gọi chờ, kết quả bao gồm cả độ trễ lập lịch, không chỉ bước đồng hồ.

Trong code ứng dụng:

- Đặt timeout theo yêu cầu nghiệp vụ và ngân sách thực tế.
- Kiểm tra lại thời gian đã trôi khi được đánh thức nếu API/vòng lặp cần.
- Dùng các cơ chế chờ có sẵn cho lock, queue hoặc I/O thay vì tự quay vòng bận.
- Không coi chênh lệch vài ns trong log là bằng chứng vi phạm một deadline ở mức đó.

Với bài toán cần thời gian thực cứng, phải đánh giá toàn bộ nền tảng và cách triển khai; chỉ chọn đơn vị nanosecond không tạo ra bảo đảm thời gian thực.

## 9. Những kết luận nên và không nên rút ra

| Quan sát | Kết luận phù hợp |
| --- | --- |
| Hai lần nanoTime trả cùng giá trị | Hai lần lấy mẫu chưa quan sát được mức thời gian khác |
| Đổi 999.999 ns sang ms nguyên được 0 | Phần lẻ bị cắt khi đổi đơn vị |
| Một lần lấy mẫu có bước dương nhỏ nhất 100 ns | Đó là bước dương nhỏ nhất của mẫu và cách chạy này |
| Lần đo sau lâu hơn nhiều | Cần xem nhiễu, lịch chạy, khởi động và công việc khác |
| Báo cáo trung bình 10 ns/op | Đó là đại lượng tổng hợp theo phương pháp benchmark |
| Timeout khai báo bằng ns | Tham số có đơn vị ns; không tự bảo đảm lịch chạy ở độ mịn đó |

Bài tập:

1. Vì sao `double ms = nanos / 1_000_000;` có thể trả 0,0 cho một khoảng khác 0? Hãy sửa phép chia.
2. Chạy `--sample` vài lần và so sánh số khoảng 0. Vì sao kết quả thay đổi không đủ để kết luận đồng hồ phần cứng thay đổi độ phân giải?
3. Một tác vụ có trung bình 15 ns/op nhưng một lần đọc đồng hồ quan sát bước 100 ns. Có nhất thiết sai không? Hãy phân biệt đo tổng và đo từng lần.
4. Một log ghi `elapsed=0 ms`. Cần kiểm tra đơn vị gốc, phép chuyển số và cách đo nào trước khi kết luận tác vụ tức thời?

Khi báo cáo hiệu năng, ghi rõ đại lượng, đơn vị, môi trường và phương pháp. Số chữ số nên phản ánh mức hiểu biết từ phép đo, thay vì tạo cảm giác chính xác hơn dữ liệu thực sự hỗ trợ.
