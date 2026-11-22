# Phân biệt độ phân giải dữ liệu với độ chính xác của đồng hồ trong Java

Khi làm việc với ngày giờ, hai câu hỏi rất dễ bị đánh đồng:

- **Dữ liệu thời gian biểu diễn được chi tiết đến mức nào?** Đây là **độ phân giải của kiểu dữ liệu hoặc biểu diễn thời gian** (*resolution/granularity*). Ví dụ, một giá trị `Instant` có thể lưu phần giây ở đơn vị nano giây.
- **Thời điểm do đồng hồ trả về gần thời gian thực đến mức nào?** Đây là **độ chính xác của đồng hồ** (*clock accuracy*). Muốn biết một đồng hồ sai bao nhiêu, phải so sánh với mốc tham chiếu đáng tin cậy và xét độ bất định của phép so sánh.

**Thông điệp quan trọng:** Một timestamp có chín chữ số sau dấu thập phân không chứng minh đồng hồ chính xác tới một nano giây. Khả năng *biểu diễn* và chất lượng *đo đạc* là hai thuộc tính độc lập.

## 1. Bốn khái niệm cần tách bạch

| Khái niệm | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| **Độ phân giải dữ liệu** (*representation resolution*) | Kiểu dữ liệu phân biệt được hai giá trị cách nhau tối thiểu bao nhiêu? | `Instant` và `LocalTime` có trường nano giây; `java.util.Date` lưu mili giây. |
| **Độ phân giải lấy mẫu của đồng hồ** (*clock resolution*) | Giá trị đọc thực tế có thể thay đổi theo các nấc nhỏ đến đâu? | Một đồng hồ có thể chỉ đổi giá trị từng 1 ms, dù API trả về kiểu hỗ trợ nano giây. |
| **Độ chính xác** (*accuracy*) | Kết quả gần mốc thời gian tham chiếu đúng đến đâu? | Đồng hồ luôn nhanh hơn UTC tham chiếu 250 ms có sai lệch +250 ms dù kết quả hiển thị nhiều chữ số. |
| **Độ ổn định/lặp lại** (*precision/repeatability*) | Các phép đọc/đo dưới điều kiện tương tự có phân tán nhiều không? | Một đồng hồ có thể lặp lại rất đều nhưng luôn nhanh 250 ms: ổn định mà không chính xác. |

Trong kỹ thuật, từ tiếng Anh *precision* đôi khi được dùng để chỉ số chữ số có nghĩa hoặc độ mịn biểu diễn, đôi khi chỉ độ lặp lại của phép đo. Khi viết yêu cầu hệ thống, hãy nói rõ **độ phân giải lưu trữ**, **độ phân giải đồng hồ**, **sai số so với tham chiếu** hay **độ biến thiên giữa các lần đo** để tránh nhập nhằng.

Một mô hình đơn giản:

- **Sai lệch hệ thống** (*offset/bias*): đồng hồ luôn nhanh hoặc chậm một khoảng.
- **Độ trôi** (*drift*): sai lệch thay đổi dần theo thời gian vì nhịp đồng hồ không khớp tuyệt đối với chuẩn.
- **Dao động** (*jitter*): độ chênh ngẫu nhiên giữa các lần đọc hoặc truyền nhận phép đo.
- **Lượng tử hóa** (*quantization*): giá trị bị làm tròn/cắt theo những nấc biểu diễn hoặc nấc đồng hồ.

Những yếu tố này có thể tồn tại đồng thời. Chia kết quả ra nhiều chữ số thập phân không tự loại bỏ được chúng.

## 2. Java biểu diễn được nano giây nhưng không cam kết đồng hồ đo được nano giây

### 2.1. Cấu trúc dữ liệu và nguồn thời gian

- `Instant` biểu diễn một điểm trên dòng thời gian bằng **số giây** và **phần nano giây trong giây** (0 đến 999.999.999). Nó hỗ trợ thao tác ở độ phân giải danh nghĩa 1 ns.
- `LocalTime` và `LocalDateTime` cũng chứa thành phần nano giây; riêng `LocalDateTime` không có múi giờ/offset nên **không tự xác định duy nhất một thời điểm UTC**.
- `Duration` có thể biểu diễn khoảng thời gian tới đơn vị nano giây.
- `java.util.Date` giữ số mili giây tính từ epoch, nên mất phần nhỏ hơn mili giây nếu chuyển từ một `Instant` có phần lẻ nhỏ hơn.
- `System.currentTimeMillis()` trả về số mili giây tính từ Unix epoch, nhưng **độ phân giải thực tế và sai số phụ thuộc hệ điều hành, phần cứng và cách đồng bộ đồng hồ**.
- `Instant.now()` và `Clock.systemUTC().instant()` lấy thời điểm từ đồng hồ hệ thống. Java có thể tận dụng nguồn thời gian phân giải tốt hơn mili giây trên một số nền tảng, nhưng API **không hứa** mỗi lần đọc là phép đo chính xác 1 ns.

Cần phân biệt ba phát biểu:

1. “Kiểu `Instant` **có chỗ lưu** phần nano giây” — đúng.
2. “`Instant.now()` **luôn thay đổi** mỗi nano giây” — không được bảo đảm.
3. “`Instant.now()` **sai lệch so với UTC nhỏ hơn** 1 ns” — không được bảo đảm.

Ví dụ, chuỗi `2026-01-02T03:04:05.123456789Z` có phần nano là `123456789`. Chuỗi đó có thể được tạo bằng cách phân tích văn bản, cộng thời lượng, hoặc đọc đồng hồ. Chỉ nhìn vào chuỗi **không suy ra được** đồng hồ nào tạo ra nó và sai số bao nhiêu.

### 2.2. Độ phân giải đầu ra khác với định dạng hiển thị

Định dạng có thể cắt bớt hoặc thêm chữ số, nhưng đó là quyết định **trình bày**:

- `03:04:05` bỏ qua phần giây lẻ.
- `03:04:05.123` hiển thị ba chữ số phần giây.
- `03:04:05.123000000` hiển thị chín chữ số, nhưng sáu số 0 cuối **không phải bằng chứng** có phép đo ở mức nano giây.

Ngược lại, nếu log chỉ in mili giây, điều đó không chứng minh nguồn thời gian bên trong chỉ có độ phân giải mili giây. Muốn biết cần kiểm tra kiểu dữ liệu, phép biến đổi, định dạng, nguồn clock và hệ thống lưu trữ ở từng bước.

## 3. Ví dụ chạy được: đồng hồ mịn, đồng hồ sai và đồng hồ bước lớn

Để tránh phụ thuộc đồng hồ thực của máy, chương trình sau dùng `Clock.fixed` làm mốc giả định. `Clock.offset` tạo ra một đồng hồ bị lệch; `Clock.tick` tạo đồng hồ chỉ xuất các mốc theo bước 100 ms. Đây là **mô phỏng có kiểm soát**, không phải phép hiệu chuẩn đồng hồ vật lý.

Lưu vào tệp `ResolutionVsAccuracy.java`:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

public class ResolutionVsAccuracy {
    public static void main(String[] args) {
        Instant reference = Instant.parse("2026-01-02T03:04:05.123456789Z");

        Clock referenceClock = Clock.fixed(reference, ZoneOffset.UTC);
        Clock fastClock = Clock.offset(referenceClock, Duration.ofMillis(250));
        Clock coarseClock = Clock.tick(referenceClock, Duration.ofMillis(100));

        System.out.println("Tham chieu: " + referenceClock.instant());
        System.out.println("Nhanh 250 ms: " + fastClock.instant());
        System.out.println("Buoc 100 ms: " + coarseClock.instant());

        long offsetMillis = Duration.between(
                referenceClock.instant(), fastClock.instant()).toMillis();
        System.out.println("Do lech: " + offsetMillis + " ms");
        System.out.println("Phan nano: " + reference.getNano());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac ResolutionVsAccuracy.java
java ResolutionVsAccuracy
~~~

Kết quả xác định:

~~~text
Tham chieu: 2026-01-02T03:04:05.123456789Z
Nhanh 250 ms: 2026-01-02T03:04:05.373456789Z
Buoc 100 ms: 2026-01-02T03:04:05.100Z
Do lech: 250 ms
Phan nano: 123456789
~~~

**Phân tích:**

- Đồng hồ tham chiếu và đồng hồ lệch đều có chín chữ số phần giây, nhưng đồng hồ lệch đang **nhanh hơn mốc giả định 250 ms**.
- Đồng hồ bước 100 ms trả `...05.100Z` vì `Clock.tick` giới hạn thời điểm quan sát về các mốc tương ứng với bước đã chọn; bước lớn làm dữ liệu thô hơn.
- `reference.getNano()` trả `123456789` vì giá trị đã được **biểu diễn** bằng trường nano, không phải vì Java vừa đo thực tế tới 1 ns.
- Trong ví dụ, sai lệch 250 ms là chính xác vì chúng ta **đã dựng** hai đồng hồ từ cùng một mốc. Với đồng hồ máy thật, cần nguồn tham chiếu độc lập mới ước tính được accuracy.

**Lưu ý API:** `Clock.tick(baseClock, duration)` là công cụ lấy mốc theo nhịp (tick), có thể dùng cache và không cam kết quan sát một lần thay đổi ở đúng mỗi tick. Đừng dùng nó để “nâng cấp” độ chính xác của nguồn. `Clock.offset` thay đổi mốc đọc được, cũng không giúp hiệu chuẩn đồng hồ thật.

## 4. Đo khoảng thời gian khác với lấy thời gian trên lịch

Có hai nhu cầu thường gặp, cần chọn đồng hồ theo mục đích.

### 4.1. Timestamp tuyệt đối: dùng `Instant` và `Clock`

Khi ghi “sự kiện xảy ra lúc nào?”, hãy sử dụng thời gian tường (*wall-clock time*) như `Instant.now(clock)` và lưu mốc kèm quy ước UTC/offset rõ ràng. Đồng hồ hệ thống có thể bị người dùng chỉnh tay, dịch bởi NTP hoặc cơ chế đồng bộ; các lần đọc wall clock **có thể nhảy tiến hoặc lùi**. Vì vậy không dùng hiệu hai timestamp tường để khẳng định thời lượng tác vụ luôn đáng tin khi clock bị điều chỉnh.

Trong mã nghiệp vụ cần kiểm thử, nên **truyền `Clock` từ ngoài vào**:

~~~java
import java.time.Clock;
import java.time.Instant;

public class DeadlineService {
    private final Clock clock;

    public DeadlineService(Clock clock) {
        this.clock = clock;
    }

    public boolean hasExpired(Instant deadline) {
        return !Instant.now(clock).isBefore(deadline);
    }
}
~~~

Đây là một **class nghiệp vụ**, không chứa `main`. Khi chạy thực tế, có thể truyền `Clock.systemUTC()`; trong unit test truyền `Clock.fixed(...)` để kết quả không phụ thuộc giờ hệ thống. Kiểm thử đúng logic thời hạn **không đồng nghĩa** với xác minh accuracy của đồng hồ vật lý.

### 4.2. Thời lượng chạy: dùng `System.nanoTime()`

`System.nanoTime()` trả giá trị đếm phù hợp để **đo khoảng thời gian trôi qua**. Gốc đếm là tùy ý và không liên quan Unix epoch; con số trả về **không phải một timestamp UTC**. Đơn vị kết quả là nano giây, nhưng mức phân giải thực và sai số đo vẫn phụ thuộc nền tảng.

Ví dụ đo thời gian của một thao tác:

~~~java
long started = System.nanoTime();
performOperation(); // Mã minh họa: thay bằng công việc cần đo.
long elapsedNanos = System.nanoTime() - started;
System.out.println("Elapsed ns: " + elapsedNanos);
~~~

Đoạn trên **không phải chương trình độc lập** vì chưa định nghĩa `performOperation()`, và không thể có stdout cố định: thời gian chạy thực phụ thuộc tải máy, JIT, GC, scheduling và hệ điều hành.

Khi trừ hai lần đọc `nanoTime()`, lấy **hiệu** theo thứ tự đúng; không đổi một giá trị `nanoTime()` đơn lẻ sang `Instant` hoặc cộng vào `currentTimeMillis()` như hai giá trị cùng chung mốc. Theo hợp đồng API, hiệu có ích cho các khoảng ngắn hơn khoảng 292 năm; với timeout thường dùng so sánh hiệu đã trôi qua với thời lượng yêu cầu thay vì cộng trực tiếp vào giá trị mốc có nguy cơ tràn số.

| Nhu cầu | API phù hợp | Điều cần nhớ |
|---|---|---|
| Thời điểm tạo bản ghi, audit timestamp | `Instant.now(clock)` | Là wall clock, có khả năng bị điều chỉnh và có sai số. |
| Test thời hạn, lịch chạy, ngày giờ phụ thuộc môi trường | `Clock` được inject | `Clock.fixed` giúp tái lập test; không tăng accuracy. |
| Đo latency/thời lượng thực thi | `System.nanoTime()` rồi lấy hiệu | Tính elapsed time; không gắn trực tiếp với UTC. |
| Biểu diễn khoảng thời gian giữa hai thời điểm | `Duration.between(a, b)` | Độ phân giải dữ liệu không bảo đảm đầu vào là phép đo chính xác. |

## 5. Đường đi dữ liệu có thể làm giảm độ phân giải

Độ phân giải sử dụng được của một timestamp bị giới hạn bởi từng khâu: nguồn đồng hồ → API → chuyển đổi kiểu → serialization → cột cơ sở dữ liệu → khi đọc lại → định dạng hiển thị.

Ví dụ sau mô phỏng việc lưu vào một nơi chỉ giữ đến micro giây (μs = 1.000 ns). Phép biến đổi dùng `truncatedTo` nên **cắt bỏ phần nhỏ hơn micro giây**, không làm tròn tới micro giây gần nhất.

Lưu vào `TruncationDemo.java`:

~~~java
import java.time.Instant;
import java.time.temporal.ChronoUnit;

public class TruncationDemo {
    public static void main(String[] args) {
        Instant original = Instant.parse("2026-01-02T03:04:05.123456789Z");
        Instant microseconds = original.truncatedTo(ChronoUnit.MICROS);
        Instant milliseconds = original.truncatedTo(ChronoUnit.MILLIS);

        System.out.println("Goc: " + original);
        System.out.println("Micro: " + microseconds);
        System.out.println("Milli: " + milliseconds);
        System.out.println("Bang goc? " + original.equals(microseconds));
    }
}
~~~

Chạy:

~~~bash
javac TruncationDemo.java
java TruncationDemo
~~~

Stdout:

~~~text
Goc: 2026-01-02T03:04:05.123456789Z
Micro: 2026-01-02T03:04:05.123456Z
Milli: 2026-01-02T03:04:05.123Z
Bang goc? false
~~~

Ở đây độ phân giải biểu diễn đã giảm từ nano giây xuống micro giây hoặc mili giây, nhưng **không có thao tác nào đo hoặc cải thiện độ chính xác đồng hồ**.

Trong ứng dụng thực tế, độ phân giải cột SQL `TIMESTAMP`/`TIMESTAMP WITH TIME ZONE` phụ thuộc hệ quản trị, độ chính xác khai báo, driver JDBC và phép mapping. Có hệ thống chỉ giữ micro giây hoặc mili giây; phần lẻ có thể bị cắt hoặc làm tròn theo quy tắc cụ thể. Hãy kiểm tra **schema thực, kiểu JDBC, thời điểm trước khi ghi và giá trị sau khi đọc**, thay vì suy luận từ khả năng lưu nano giây của `Instant`. Với các kiểu timestamp không kèm múi giờ, phải kiểm soát cả quy tắc diễn giải vùng giờ khi chuyển đổi.

## 6. Một ví dụ định lượng: “mịn” không có nghĩa “đúng”

Giả sử một sự kiện thực xảy ra đúng lúc `12:00:00.000 UTC` theo một chuẩn tham chiếu đáng tin:

- Đồng hồ **A** chỉ cho kết quả theo bước 1 giây và đang lệch +0,1 giây so với chuẩn; kết quả hiển thị thực tế có thể bị lượng tử hóa theo bước đó.
- Đồng hồ **B** trả kết quả nhiều chữ số ở mức nano giây nhưng luôn chạy nhanh **2 giây**.

B có khả năng xuất timestamp *mịn hơn*, nhưng ở giả thiết này nó *kém chính xác hơn* A. Không thể so hai đồng hồ chỉ bằng số chữ số sau dấu thập phân. Để đánh giá thực nghiệm phải tách **độ lớn bước thay đổi của giá trị trả về** khỏi **sai lệch so với tham chiếu** và độ biến thiên của phép đo.

Nếu đồng hồ có sai lệch `+250 ms` so với tham chiếu ở thời điểm thử, việc định dạng `2026-01-02T03:04:05.373456789Z` thành chuỗi có chín chữ số vẫn giữ sai lệch +250 ms. Tăng số chữ số chỉ thay đổi cách ghi, không làm đồng hồ chạy đúng hơn.

## 7. Thiết kế thực tế và cách kiểm chứng

### Khi thiết kế API, log và database

1. **Định nghĩa yêu cầu riêng rẽ.** Ví dụ: “lưu timestamp đến micro giây” là yêu cầu độ phân giải; “sai lệch đồng hồ máy chủ so với UTC tham chiếu nhỏ hơn 50 ms” là yêu cầu accuracy. Hai chỉ tiêu phải được kiểm chứng riêng.
2. **Chọn dữ liệu phù hợp.** Dùng `Instant` cho điểm thời gian tuyệt đối, `Duration` cho khoảng thời gian, `LocalDate` cho ngày lịch không cần giờ. Dùng UTC khi trao đổi timestamp giữa hệ thống và chỉ định quy tắc múi giờ khi hiển thị cho người dùng.
3. **Kiểm tra toàn bộ pipeline.** Serialize/deserialize thử các giá trị có phần nano không tròn mili giây; đọc lại sau lưu DB và so sánh chính xác phần giây được giữ.
4. **Chọn clock đúng mục đích.** Wall clock cho mốc lịch; nguồn thời gian tăng đều như `nanoTime()` cho elapsed time; `Clock.fixed` cho unit test quyết định theo lịch.
5. **Đánh giá đồng bộ bằng phép đo và giám sát.** Dùng nguồn tham chiếu đáng tin (ví dụ hạ tầng đồng bộ thời gian và giám sát offset phù hợp), đồng thời tính tới bất định đo, độ trễ truyền mạng, jitter và drift. Không suy ra accuracy chỉ từ NTP “đã bật” hoặc từ số chữ số của timestamp.
6. **Thiết kế cho tính không hoàn hảo.** Khi sắp xếp sự kiện phân tán, hai timestamp gần nhau có thể bị đảo thứ tự bởi lệch clock giữa các máy. Nếu cần quan hệ nhân quả/total order đáng tin, bổ sung số thứ tự, transaction order, sequence ID hoặc logical clock theo thiết kế hệ thống; không giả định mọi timestamp UTC tự quyết định được thứ tự tuyệt đối.

### Khi viết unit test

Nên kiểm thử rằng nghiệp vụ dùng `Clock` đã inject, rằng phép tính deadline xử lý đúng ranh giới, và rằng các chuyển đổi `Instant` ↔ serialization ↔ DB giữ độ phân giải cần thiết. Ví dụ với `DeadlineService` ở trên: khi giờ giả định *đúng bằng* deadline thì `hasExpired` trả `true`; một nano giây trước deadline thì trả `false`. Đây là kiểm thử **logic**, không phải phép đo accuracy của đồng hồ máy.

### Khi benchmark

Dùng `System.nanoTime()` đo hiệu giữa hai mốc; chạy warm-up, đo đủ nhiều lần, kiểm soát GC/scheduling và xem phân phối kết quả. Với microbenchmark Java, cân nhắc JMH để giảm các lỗi thường gặp từ JIT optimization, dead-code elimination và đo lường thiếu ổn định. Ngay cả khi `nanoTime()` trả đơn vị ns, đừng báo cáo một lần đo ngắn ở mức 1 ns như kết quả có độ chính xác 1 ns.

## 8. Lỗi thường gặp

| Nhận định hoặc cách làm sai | Vì sao sai | Cách sửa |
|---|---|---|
| “`Instant` có 9 chữ số phần giây nên clock chính xác 1 ns.” | Trường dữ liệu khác chất lượng đồng hồ. | Tách khả năng biểu diễn khỏi phép hiệu chuẩn clock. |
| “`System.currentTimeMillis()` luôn cập nhật sau mỗi 1 ms.” | Đơn vị trả về không bảo đảm độ phân giải thực tế. | Không giả định tần suất thay đổi; đo trong môi trường mục tiêu nếu cần. |
| “`System.nanoTime()` là timestamp UTC tốt hơn `Instant.now()`.” | `nanoTime()` có gốc tùy ý. | Dùng nó cho elapsed time, `Instant` cho thời điểm lịch. |
| “In thêm số 0 cho đủ 9 chữ số là chính xác hơn.” | Định dạng không tạo thông tin đo đạc. | Đánh giá nguồn đo, cách lưu và sai số. |
| “Hai sự kiện trên hai server có timestamp lớn nhỏ tương ứng thứ tự thực.” | Sai lệch, drift và jitter giữa máy có thể đảo thứ tự. | Dùng chiến lược ordering phù hợp và giám sát đồng hồ. |
| “Lưu `Instant` vào DB luôn giữ đủ nanoseconds.” | Kiểu cột, JDBC, serialization có thể mất phần lẻ. | Thử round-trip và định nghĩa precision của cột rõ ràng. |
| “`Clock.fixed` hoặc `Clock.tick` làm đồng hồ thật chính xác hơn.” | Chúng mô phỏng/biến đổi cách đọc clock. | Dùng cho test/mô phỏng; dùng chuẩn tham chiếu để đo accuracy thực. |

## 9. Tự kiểm tra kiến thức

**Câu 1.** Một log in `2026-01-02T03:04:05.123456789Z`. Có thể kết luận đồng hồ chính xác 1 ns không?

**Đáp án:** Không. Ta chỉ biết biểu diễn chứa chín chữ số phần giây; cần thông tin về nguồn đồng hồ và phép so sánh với tham chiếu.

**Câu 2.** Một phép đo latency dùng `System.currentTimeMillis()` trước/sau rồi trả 0 ms. Công việc có chắc tốn 0 ns không?

**Đáp án:** Không. Khoảng chạy có thể nhỏ hơn nấc thay đổi của đồng hồ hoặc bị ảnh hưởng bởi độ phân giải. Dùng `System.nanoTime()` để đo elapsed time, vẫn phải đánh giá nhiễu.

**Câu 3.** Chuyển `Instant` từ `...05.123456789Z` sang kiểu chỉ giữ mili giây, rồi đọc lại `...05.123Z`. Đây là mất gì?

**Đáp án:** Mất **độ phân giải dữ liệu** khi chuyển đổi/lưu trữ. Hiện tượng đó không tự nói đồng hồ gốc chính xác hay sai lệch bao nhiêu.

**Câu 4.** Đồng hồ bị lệch +500 ms nhưng mỗi lần đọc nhảy theo bước 1 μs. Nên mô tả ra sao?

**Đáp án:** Nó có thể có **độ phân giải đọc 1 μs** nhưng đang có **sai lệch +500 ms** so với tham chiếu. Hai con số cùng tồn tại, không mâu thuẫn.

## Ghi nhớ

**Độ phân giải** cho biết timestamp có thể biểu diễn hoặc được lấy mẫu mịn đến đâu; **độ chính xác của đồng hồ** cho biết timestamp gần thời gian tham chiếu đúng đến đâu. Kiểu dữ liệu `Instant` có khả năng lưu nano giây, còn độ phân giải và accuracy khi gọi `Instant.now()` phụ thuộc nguồn clock. Dùng `Instant` cho thời điểm, `System.nanoTime()` cho khoảng thời gian, kiểm thử bằng `Clock`, và kiểm chứng độ phân giải lưu trữ lẫn sai số đồng hồ bằng những phép thử riêng biệt.
