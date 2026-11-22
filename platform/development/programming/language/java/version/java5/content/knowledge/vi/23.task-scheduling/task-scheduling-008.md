# TimeUnit và biểu diễn đơn vị thời gian

## 1. Một con số thời gian chưa đủ ý nghĩa

Giá trị `500` có thể là 500 giây, 500 mili giây hoặc 500 nano giây. Nếu đơn vị không rõ, chương trình vẫn có thể biên dịch nhưng chờ lâu hơn hoặc ngắn hơn hàng nghìn lần.

`java.util.concurrent.TimeUnit` là enum biểu diễn **đơn vị của một khoảng thời gian**, đồng thời cung cấp các phép chuyển đổi và tiện ích chờ theo đơn vị ấy.

Ví dụ:

```java
scheduler.schedule(task, 500, TimeUnit.MILLISECONDS);
```

Ở đây, giá trị là 500 và đơn vị là mili giây. TimeUnit không tự chứa giá trị 500; nó chỉ làm rõ cách API phải hiểu đối số số lượng.

Trong bài, các API được sử dụng trên Java 17+ và vẫn áp dụng trong Java hiện hành.

## 2. Các đơn vị và quan hệ

| Hằng TimeUnit | Ý nghĩa |
|---|---|
| `NANOSECONDS` | Nano giây |
| `MICROSECONDS` | Micro giây |
| `MILLISECONDS` | Mili giây |
| `SECONDS` | Giây |
| `MINUTES` | Phút |
| `HOURS` | Giờ |
| `DAYS` | Ngày theo độ dài cố định 24 giờ |

Các quan hệ:

```text
1 micro giây = 1.000 nano giây
1 mili giây  = 1.000 micro giây
1 giây       = 1.000 mili giây
1 phút       = 60 giây
1 giờ        = 60 phút
1 ngày       = 24 giờ
```

Trong ngữ cảnh này, một DAYS luôn là 24 giờ. Nó không mô tả “ngày lịch tiếp theo tại một múi giờ” hay tự xử lý thay đổi giờ mùa hè.

Không có TimeUnit.MONTHS hoặc YEARS vì các khoảng lịch ấy không có độ dài cố định theo giây như các đơn vị ở đây. Nhu cầu theo lịch cần dùng mô hình ngày giờ phù hợp.

Khái niệm và các đơn vị được mô tả tại [TimeUnit API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/TimeUnit.html).

## 3. Dùng cặp giá trị và đơn vị ở ranh giới API

Ví dụ các lời gọi có ý nghĩa khác nhau:

```java
future.get(500, TimeUnit.MILLISECONDS);
future.get(500, TimeUnit.SECONDS);
```

Đây là các lựa chọn minh họa, không phải đề xuất chờ hai lần liên tiếp. Lời đầu có ngân sách chờ 0,5 giây; lời sau là 500 giây.

Tương tự:

```java
scheduler.schedule(task, 2, TimeUnit.SECONDS);
pool.awaitTermination(5, TimeUnit.SECONDS);
queue.poll(200, TimeUnit.MILLISECONDS);
```

Các biến và tác vụ do ứng dụng chuẩn bị; nơi gọi phải xử lý ngoại lệ theo hợp đồng từng API.

TimeUnit chỉ xác định đơn vị. Nó không làm các API có cùng ngữ nghĩa:

- Schedule dùng khoảng trễ trước khi công việc được phép chạy.
- Future.get dùng thời gian chờ kết quả của nơi gọi.
- AwaitTermination dùng thời gian chờ executor kết thúc.
- Poll có thời hạn dùng thời gian chờ lấy phần tử.

Cùng là năm giây nhưng mục tiêu được chờ và kết quả khi hết hạn khác nhau.

## 4. Hai cách đọc phép chuyển đổi

### Cách 1: đơn vị nguồn gọi to...

```java
long milliseconds = TimeUnit.SECONDS.toMillis(2); // 2000
long minutes = TimeUnit.SECONDS.toMinutes(120);  // 2
```

Cách đọc: “lấy số lượng đang tính bằng giây, chuyển sang mili giây hoặc phút”.

Đơn vị đứng trước dấu chấm là đơn vị của đối số.

### Cách 2: đơn vị đích gọi convert

```java
long milliseconds =
        TimeUnit.MILLISECONDS.convert(2, TimeUnit.SECONDS); // 2000

long minutes =
        TimeUnit.MINUTES.convert(120, TimeUnit.SECONDS);    // 2
```

Cách đọc: “chuyển số lượng từ đơn vị nguồn được truyền vào sang đơn vị đang gọi convert”.

Đơn vị đứng trước dấu chấm là **đơn vị đích**.

| Biểu thức | Nguồn | Đích | Kết quả |
|---|---|---|---:|
| `SECONDS.toMillis(2)` | Giây | Mili giây | 2000 |
| `MILLISECONDS.convert(2, SECONDS)` | Giây | Mili giây | 2000 |
| `SECONDS.toMinutes(120)` | Giây | Phút | 2 |
| `MINUTES.convert(120, SECONDS)` | Giây | Phút | 2 |

Các hằng trong bảng được viết ngắn để dễ so sánh; mã thông thường dùng tiền tố TimeUnit hoặc static import có chủ đích.

Không nhớ convert theo vị trí mơ hồ. Hãy đọc thành câu “đích.convert(số lượng, nguồn)”.

## 5. Chuyển từ đơn vị nhỏ sang lớn có thể mất phần lẻ

Kết quả chuyển đổi của TimeUnit là `long`, không phải số thực.

```java
long wholeSeconds = TimeUnit.MILLISECONDS.toSeconds(1500); // 1
long tinySeconds = TimeUnit.MILLISECONDS.toSeconds(999);   // 0
```

1500 ms là 1,5 giây nhưng kết quả nguyên chỉ là 1. Phép chuyển không làm tròn lên thành 2.

Với số âm, phần lẻ bị cắt theo hướng về 0, như -1500 ms chuyển sang giây được -1, không phải -2.

### Hệ quả với timeout ngắn

Giả sử cấu hình là 500 ms. Nếu chuyển sang giây trước rồi gọi một API nhận giây, giá trị sau chuyển là 0. Thế là ứng dụng đã đánh mất khoảng chờ mong muốn.

Cách tốt hơn thường là giữ đơn vị gốc đủ chi tiết:

```java
future.get(500, TimeUnit.MILLISECONDS);
```

thay vì:

```java
long seconds = TimeUnit.MILLISECONDS.toSeconds(500);
future.get(seconds, TimeUnit.SECONDS);
```

Đây là ví dụ lỗi mất độ chi tiết cần tránh. Ý nghĩa cụ thể của giá trị 0 còn do API đích quyết định; không có quy tắc rằng mọi API đều xem 0 là vô hạn hoặc đều xem 0 là chạy ngay.

## 6. Chuyển sang đơn vị nhỏ có thể vượt phạm vi long

Một khoảng thời gian rất lớn tính bằng ngày có thể không biểu diễn được bằng long khi chuyển sang nano giây.

TimeUnit dùng cách **bão hòa (saturation)** cho những chuyển đổi vượt phạm vi:

- Kết quả dương quá lớn: trả Long.MAX_VALUE.
- Kết quả âm quá nhỏ: trả Long.MIN_VALUE.

Ví dụ:

```java
long nanos = TimeUnit.DAYS.toNanos(Long.MAX_VALUE);
boolean saturated = nanos == Long.MAX_VALUE; // true
```

Nó không quấn vòng sang số âm và không báo ArithmeticException cho phép chuyển TimeUnit này.

Điều đó giúp tránh một lớp lỗi số học, nhưng không có nghĩa đầu vào quá lớn đã hợp lệ về nghiệp vụ. Nếu ứng dụng chỉ cho phép timeout tối đa vài phút, cần kiểm tra giới hạn trước, không chấp nhận giá trị khổng lồ chỉ vì kết quả không âm.

### Cẩn thận với arithmetic trước khi gọi TimeUnit

TimeUnit không sửa được một phép nhân đã tràn trước khi được truyền vào:

```java
long wrong = 30 * 24 * 60 * 60 * 1000;
```

Tất cả toán hạng là int, nên phép nhân thực hiện theo int trước rồi kết quả đã tràn mới được gán sang long.

Các cách rõ hơn:

```java
long usingLong = 30L * 24 * 60 * 60 * 1000;
long usingUnit = TimeUnit.DAYS.toMillis(30);
```

Dùng 30L làm phép nhân theo long, nhưng với các con số lớn hơn vẫn phải xét tràn long. TimeUnit làm rõ đơn vị và có hành vi bão hòa đã định nghĩa; nó không thay thế kiểm tra phạm vi nghiệp vụ.

## 7. Chương trình Java 17+: chuyển đổi và lập lịch

Lưu thành **`TimeUnitDemo.java`**:

```java
import java.time.Duration;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

public class TimeUnitDemo {
    public static void main(String[] args) throws Exception {
        System.out.println(
                "2 seconds in ms: " + TimeUnit.SECONDS.toMillis(2));
        System.out.println(
                "1500 ms in whole seconds: "
                + TimeUnit.MILLISECONDS.toSeconds(1500));
        System.out.println(
                "-1500 ms in whole seconds: "
                + TimeUnit.MILLISECONDS.toSeconds(-1500));
        System.out.println(
                "120 seconds in minutes: "
                + TimeUnit.MINUTES.convert(120, TimeUnit.SECONDS));

        long wrong = 30 * 24 * 60 * 60 * 1000;
        long correct = TimeUnit.DAYS.toMillis(30);
        System.out.println("int arithmetic first: " + wrong);
        System.out.println("30 days in ms: " + correct);

        long saturated = TimeUnit.DAYS.toNanos(Long.MAX_VALUE);
        System.out.println(
                "saturated: " + (saturated == Long.MAX_VALUE));

        Duration duration = Duration.ofMillis(1500);
        System.out.println(
                "Duration in ms: "
                + TimeUnit.MILLISECONDS.convert(duration));

        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();

        try {
            ScheduledFuture<String> future = scheduler.schedule(
                    () -> "done", 10, TimeUnit.MILLISECONDS);

            System.out.println(
                    "scheduled: " + future.get(5, TimeUnit.SECONDS));
        } finally {
            scheduler.shutdown();
            try {
                if (!scheduler.awaitTermination(5, TimeUnit.SECONDS)) {
                    scheduler.shutdownNow();
                    if (!scheduler.awaitTermination(
                            5, TimeUnit.SECONDS)) {
                        throw new IllegalStateException(
                                "Scheduler did not terminate");
                    }
                }
            } catch (InterruptedException e) {
                scheduler.shutdownNow();
                Thread.currentThread().interrupt();
                throw e;
            }
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 TimeUnitDemo.java
java TimeUnitDemo
```

Stdout chính xác:

```text
2 seconds in ms: 2000
1500 ms in whole seconds: 1
-1500 ms in whole seconds: -1
120 seconds in minutes: 2
int arithmetic first: -1702967296
30 days in ms: 2592000000
saturated: true
Duration in ms: 1500
scheduled: done
```

Các dòng số học là kết quả xác định. Dòng cuối chỉ xác nhận nhận được kết quả công việc đã lập lịch; nó không chứng minh scheduler chạy đúng tại mốc 10 ms.

Khoảng trễ lập lịch là 10 ms, còn khoảng chờ lấy kết quả là 5 giây. Đây là hai đại lượng và hai ý nghĩa riêng, được viết rõ đơn vị ở từng lời gọi.

Main khai báo throws Exception để giữ ví dụ tập trung; ứng dụng thực cần xử lý thất bại, ngắt và timeout theo chính sách.

## 8. TimeUnit không phải bộ đo độ chính xác thời gian

Dùng NANOSECONDS không bảo đảm một tác vụ bắt đầu chính xác đến nano giây. Đơn vị biểu diễn nhỏ không có nghĩa cơ chế chờ hoặc bộ lập lịch có độ chính xác tương đương.

Hệ điều hành, bộ lập lịch luồng, tải CPU, độ phân giải đồng hồ và worker đang bận đều có thể ảnh hưởng thời điểm thực tế.

Các phương thức đo khoảng thời gian như System.nanoTime dùng đơn vị nano giây nhưng không biến mọi phép đo thành chính xác tuyệt đối đến một nano giây.

Để đo thời gian trôi qua trong cùng tiến trình, thường dùng hiệu hai giá trị nanoTime:

```java
long started = System.nanoTime();
performOperation();
long elapsedNanos = System.nanoTime() - started;

long elapsedMillis = TimeUnit.NANOSECONDS.toMillis(elapsedNanos);
```

Đây là đoạn minh họa; performOperation do ứng dụng định nghĩa. Giá trị in theo mili giây là kết quả đã mất phần lẻ nhỏ hơn mili giây.

Không dùng nanoTime như thời điểm lịch hoặc epoch. Nguồn thời gian này phục vụ đo khoảng trôi qua theo hợp đồng; xem [System.nanoTime API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html#nanoTime()).

## 9. Các tiện ích sleep, timedJoin và timedWait

TimeUnit có một số phương thức giúp biểu đạt đơn vị tại nơi chờ:

```java
TimeUnit.MILLISECONDS.sleep(250);
TimeUnit.SECONDS.timedJoin(worker, 2);
```

Đây là mã minh họa. Sleep làm luồng hiện tại chờ; timedJoin chờ worker kết thúc trong khoảng yêu cầu. Các lời gọi có thể phản hồi ngắt, nên nơi gọi phải truyền hoặc xử lý InterruptedException.

Không dùng sleep như một phép đồng bộ để bảo đảm luồng khác đã khởi động, kết thúc hoặc cập nhật dữ liệu. Khi cần chờ điều kiện, dùng cơ chế điều phối phù hợp.

### timedWait vẫn có quy tắc của Object.wait

`TimeUnit.SECONDS.timedWait(monitor, 2)` không bỏ yêu cầu phải sở hữu monitor. Việc chờ điều kiện vẫn cần kiểm tra điều kiện trong vòng lặp vì có thể thức dậy mà điều kiện chưa đúng.

Không xem việc đổi đơn vị thành một cơ chế khóa mới; tiện ích này chỉ hỗ trợ cách biểu đạt thời hạn.

### Số 0 không có một ngữ nghĩa chung cho mọi API

Đọc tài liệu của phương thức đang gọi thay vì suy từ tên TimeUnit. Ví dụ, việc làm tròn một khoảng dương nhỏ về 0 có thể đổi hành vi của lời gọi đích theo cách không mong muốn.

TimeUnit không tự xác nhận giá trị âm, 0 hay quá lớn là hợp lệ đối với mọi nơi sử dụng.

## 10. Liên hệ với Duration

`java.time.Duration` biểu diễn **cả một lượng thời gian**, thay vì chỉ một đơn vị. Nó thích hợp khi muốn truyền hoặc lưu một giá trị thời lượng có cấu trúc rõ:

```java
Duration timeout = Duration.ofMillis(1500);
```

Một API nhận cặp long và TimeUnit vẫn có thể được dùng bằng cách chuyển tại ranh giới:

```java
long timeoutMillis = TimeUnit.MILLISECONDS.convert(timeout);
future.get(timeoutMillis, TimeUnit.MILLISECONDS);
```

Cần chọn đơn vị đủ chi tiết và kiểm tra giới hạn, vì chuyển vẫn có thể mất phần lẻ hoặc bão hòa.

Duration không có nghĩa tự chạy một lịch hoặc tự giới hạn thời gian thực thi. Nó là dữ liệu thời lượng. DAYS trong Duration cũng là ngày cố định 24 giờ khi dùng theo mô hình này, không phải lịch theo múi giờ.

Không đồng nhất hành vi tràn của mọi API: một số phép chuyển như Duration.toNanos có thể ném ArithmeticException nếu không biểu diễn được trong long, khác với chuyển đổi bão hòa của TimeUnit.

Xem [Duration API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Duration.html).

## 11. Quy ước giúp tránh lỗi đơn vị

- Viết đơn vị ngay tại lời gọi API thay vì một con số không giải thích.
- Đặt tên biến như timeoutMillis hoặc elapsedNanos khi biến chỉ giữ số.
- Nếu cần truyền cả giá trị và đơn vị qua nhiều tầng, cân nhắc kiểu dữ liệu rõ như Duration.
- Không nhân thủ công nếu một phép chuyển TimeUnit làm ý định rõ hơn.
- Chuyển sang đơn vị nhỏ hoặc lớn chỉ ở nơi cần, để tránh mất độ chi tiết nhiều lần.
- Kiểm tra giá trị âm, 0, tối đa và null theo hợp đồng cấu hình của ứng dụng.

Khi đọc cấu hình ngoài như `timeout=500`, phải có quy định đơn vị. Có thể đặt tên khóa có đơn vị hoặc dùng định dạng thời lượng đã được parser của ứng dụng hỗ trợ; không tự đoán.

### Một lỗi khó thấy: chuyển đi rồi chuyển lại

Nếu đổi 1500 ms thành 1 giây rồi đổi lại sang ms, chỉ nhận 1000 ms. Phép chuyển ngược không khôi phục 500 ms đã mất.

Vì vậy, giữ biểu diễn gốc đủ chính xác khi còn cần tính toán. Không làm tròn sớm chỉ để log hoặc truyền qua một tầng trung gian.

## 12. Tự kiểm tra

1. Trong `MINUTES.convert(120, SECONDS)`, đơn vị nào là đích?
2. `MILLISECONDS.toSeconds(999)` trả bao nhiêu?
3. Vì sao gán kết quả `30 * 24 * 60 * 60 * 1000` vào long vẫn có thể sai?
4. TimeUnit chuyển một khoảng dương quá lớn sang đơn vị nhỏ hơn có quấn thành số âm không?
5. NANOSECONDS có bảo đảm scheduler chính xác tới nano giây không?
6. Chuyển 1500 ms sang giây rồi quay lại ms có giữ nguyên giá trị không?
7. DAYS có nghĩa “cùng giờ vào ngày lịch tiếp theo tại mọi múi giờ” không?

**Gợi ý:** (1) Phút. (2) 0. (3) Phép nhân đã thực hiện theo int trước khi gán. (4) Không; nó bão hòa tới Long.MAX_VALUE. (5) Không. (6) Không; phần lẻ đã bị cắt. (7) Không, DAYS là khoảng cố định 24 giờ.

TimeUnit giúp làm rõ **đơn vị của một lượng thời gian và cách chuyển đổi**, còn ý nghĩa timeout, độ chính xác thực tế và tính hợp lệ của giá trị vẫn phụ thuộc API và yêu cầu ứng dụng.
