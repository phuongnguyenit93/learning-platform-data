# Xử lý sự kiện theo thứ tự và quy tắc khi cùng thời điểm

Nhiều bài toán thuật toán không xử lý một dãy giá trị độc lập, mà xử lý **các sự kiện (events)** xảy ra theo thời gian hoặc theo một tọa độ: cuộc họp bắt đầu/kết thúc, xe vào/ra bãi, khách đến/rời quầy, các đoạn trên trục số bắt đầu/kết thúc, giao dịch được thêm/xóa hoặc truy vấn trạng thái tại một mốc. Một kỹ thuật phổ biến là **biến đổi dữ liệu thành các sự kiện, sắp theo thứ tự rồi quét từ trái sang phải (sweep line)**.

Điểm khó không chỉ là “sắp theo thời điểm tăng dần”. **Nhiều sự kiện có thể mang cùng thời điểm**, và kết quả có thể thay đổi nếu xử lý START trước END, END trước START hay QUERY ở giữa. Vì vậy, **quy tắc phá hòa (tie-breaking rule)** phải được rút ra từ **đặc tả thời gian và ý nghĩa trạng thái**, không được chọn tùy tiện.

Bài học giải thích cách xây dựng sự kiện, quy tắc tại mốc trùng, bất biến quét, cách xử lý theo nhóm cùng thời điểm, tính đúng đắn, độ phức tạp và chương trình Java 17+ có thể biên dịch/chạy. Ví dụ chủ đạo là **số khoảng hoạt động đồng thời lớn nhất**; mô hình này cũng là nền tảng của bài toán số phòng họp tối thiểu và nhiều bài xử lý khoảng.

## 1. Mô hình sự kiện gồm những gì?

Một sự kiện thường có ít nhất:

- **`time`**: thời điểm hoặc tọa độ xảy ra.
- **`kind`**: loại sự kiện, chẳng hạn `START`, `END`, `QUERY`.
- **`payload`** (khi cần): mã đối tượng, số lượng thay đổi, giá trị truy vấn hoặc một trường dữ liệu nghiệp vụ.
- **`sequence`** (khi cần): vị trí xuất hiện ban đầu để xử lý các sự kiện mà thứ tự ghi nhận cũng có ý nghĩa.

Ví dụ cho một cuộc họp `[2,5)`:

```text
(time=2, kind=START, id=A)
(time=5, kind=END,   id=A)
```

Sau khi biến đổi `n` khoảng thành các sự kiện bắt đầu/kết thúc, có tối đa **`2n` sự kiện**. Nếu dùng danh sách để sắp theo thời điểm, ta có thể tính số khoảng đang hoạt động bằng cách tăng bộ đếm khi gặp `START`, giảm khi gặp `END`. Nhưng trước khi viết comparator, phải xác định chính xác **“đang hoạt động tại t”** nghĩa là gì.

## 2. Quy ước khoảng nửa mở và khoảng đóng

Hai quy ước được dùng nhiều nhất là:

| Quy ước | Ký hiệu | Hoạt động tại thời điểm `t` khi nào? | Ý nghĩa tại cận kết thúc |
| --- | --- | --- | --- |
| **Nửa mở** (đầu gồm, cuối không gồm) | `[start, end)` | `start ≤ t < end` | Tại `t=end`, khoảng **không còn** hoạt động. |
| **Đóng** (gồm cả hai cận) | `[start, end]` | `start ≤ t ≤ end` | Tại `t=end`, khoảng **vẫn còn** hoạt động. |

Xét hai cuộc họp `A=[1,3)` và `B=[3,5)`. Tại đúng `t=3`, `A` đã kết thúc còn `B` vừa bắt đầu, nên chỉ cần **một phòng** nếu phòng được tái sử dụng ngay khi cuộc họp trước kết thúc. Trái lại, với hai khoảng đóng `A=[1,3]`, `B=[3,5]`, cả hai cùng chứa thời điểm 3 theo nghĩa toán học; số khoảng đồng thời tại mốc đó là **2**.

```text
Nửa mở [start,end):
A: 1 ------- 3)          A không hoạt động tại 3
B:           [3 ------- 5)
active tại t=3: 1

Đóng [start,end]:
A: [1 ------- 3]         A có mặt tại 3
B:           [3 ------- 5]
active tại t=3: 2
```

**Khoảng có độ dài 0 cần xét riêng.** Trong quy ước nửa mở, `[3,3)` là **rỗng**, không hoạt động ở bất kỳ thời điểm nào; trong mô hình quét, nên **bỏ qua** cả cặp START/END của khoảng ấy. Với quy ước đóng, `[3,3]` là **một điểm**, hoạt động đúng tại `t=3`.

Nếu một đề bài dùng mốc thời gian nguyên mà cho “kết thúc tại phút 3”, đừng tự đoán mốc 3 có được tính hay không. Quy tắc phụ thuộc định nghĩa của bài toán, không phụ thuộc việc mốc được biểu diễn bằng `int`, `long` hay thời gian lịch.

## 3. Quy tắc khi các sự kiện cùng thời điểm

Giả sử ta tính `active`: số khoảng đang hoạt động, cập nhật `+1` cho START và `-1` cho END. Để đếm **số khoảng đồng thời lớn nhất (peak overlap)**, thứ tự xử lý các sự kiện có cùng `time` phải khớp quy ước:

| Ngữ nghĩa | Ưu tiên sự kiện tại cùng `t` | Lý do |
| --- | --- | --- |
| Khoảng **`[start,end)`** | **END trước START** | Những khoảng kết thúc ở `t` đã rời đi trước khi đếm các khoảng bắt đầu tại `t`. |
| Khoảng **`[start,end]`** | **START trước END** | Cả khoảng vừa bắt đầu và khoảng vừa kết thúc đều hiện diện tại `t`; phải đếm chúng cùng lúc. |
| Truy vấn số khoảng của **`[start,end)` tại `t`** | **END → START → QUERY** | Truy vấn cần trạng thái sau khi loại các khoảng kết thúc và thêm các khoảng bắt đầu đúng `t`. |
| Truy vấn số khoảng của **`[start,end]` tại `t`** | **START → QUERY → END** | Truy vấn phải thấy cả khoảng bắt đầu lẫn khoảng kết thúc tại `t`. |

**Phản ví dụ đơn giản:** với hai khoảng nửa mở `[1,3)` và `[3,5)`, nếu xử lý START ở `t=3` trước END rồi cập nhật `peak` sau từng sự kiện, ta thấy tạm thời `active=2` và trả **2 sai**. Quy tắc END trước START cho `peak=1`, đúng với đặc tả. Ngược lại, cùng hai khoảng theo quy ước đóng thì **2** mới là đáp án đúng.

Nếu hệ thống có các loại sự kiện khác như `DELETE`, `UPDATE`, `CREATE`, `QUERY`, thứ tự phá hòa phải xác định dựa vào quy tắc nghiệp vụ. Chẳng hạn, “truy vấn sau khi áp dụng mọi thay đổi tại `t`” khác với “truy vấn trạng thái ngay trước mọi thay đổi tại `t`”. Không có một thứ tự START/END/QUERY “đúng cho mọi bài toán”.

### Cách thiết kế khóa sắp xếp

Một khóa sắp xếp thường gồm:

```text
(time tăng dần, priority(kind) tăng dần, sequence tăng dần nếu cần)
```

Trong đó `priority` được định nghĩa rõ theo bài toán. Ví dụ, với khoảng nửa mở, `priority(END)=0`, `priority(START)=1`; với khoảng đóng thì đảo hai giá trị. Trường `sequence` chỉ cần nếu hai sự kiện **cùng time và cùng priority** còn phải được xử lý theo thứ tự ghi nhận.

**Không nên mặc định dựa vào tính ổn định của sort để giải quyết ngữ nghĩa phá hòa.** Kể cả khi sort ổn định, nó chỉ giữ thứ tự đầu vào cho các sự kiện có khóa so sánh bằng nhau; điều đó không tự tạo ra quy tắc nghiệp vụ START/END. Hãy viết ưu tiên rõ ràng trong comparator.

## 4. Sweep line đếm số khoảng đồng thời

**Bài toán:** cho `n` khoảng thời gian `[start_i,end_i)` với `start_i ≤ end_i`, tìm số khoảng cùng hoạt động lớn nhất tại một thời điểm. Mỗi khoảng rỗng `[t,t)` không được tính.

Phương pháp:

1. Với mỗi khoảng không rỗng, tạo START tại `start` và END tại `end`.
2. Sắp tất cả sự kiện theo `time` tăng dần, khi bằng thời điểm cho **END trước START**.
3. Khởi tạo `active=0`, `peak=0`.
4. Duyệt lần lượt: gặp END thì giảm `active`, gặp START thì tăng `active`; sau mỗi cập nhật, đặt `peak=max(peak,active)`.
5. Trả `peak`.

Giả mã:

```text
ALGORITHM PEAK_OVERLAP_HALF_OPEN(intervals)
    events <- empty list

    FOR EACH interval [s,e) IN intervals DO
        REQUIRE s <= e
        IF s = e THEN
            CONTINUE  // Khoảng nửa mở rỗng.
        END IF
        APPEND (time=s, priority=1, delta=+1) TO events
        APPEND (time=e, priority=0, delta=-1) TO events
    END FOR

    SORT events BY (time ASC, priority ASC)

    active <- 0
    peak <- 0

    FOR EACH event IN events DO
        active <- active + event.delta
        peak <- MAX(peak, active)
    END FOR

    RETURN peak
END ALGORITHM
```

**Bất biến:** trước khi xử lý thời điểm kế tiếp, `active` bằng số khoảng nửa mở đang hoạt động ở trạng thái ngay sau mốc đã xử lý trước đó. Khi duyệt các sự kiện ở cùng `t`, quy tắc END trước START lần lượt loại những khoảng không còn chứa `t`, rồi thêm những khoảng chứa `t`. Sau toàn bộ nhóm sự kiện của `t`, `active` bằng đúng số khoảng hoạt động tại `t`.

Các trạng thái trung gian trong cùng một nhóm thời điểm là **trạng thái xử lý**, không phải những thời điểm thực khác nhau. Với END trước START, chúng không tạo ra `peak` lớn giả, vì các END chỉ giảm và các START mới tăng số đếm tới giá trị thật tại `t`. Do đó việc cập nhật `peak` sau từng sự kiện vẫn cho kết quả đúng.

Nếu đã sắp theo START trước END đối với khoảng nửa mở mà vẫn cập nhật `peak` từng sự kiện, có thể ghi nhận một đỉnh **không tồn tại** tại thời điểm thực, như phản ví dụ hai cuộc họp liền nhau.

## 5. Ví dụ chi tiết khi nhiều START và END trùng nhau

Cho năm khoảng:

```text
A = [1,4)
B = [2,4)
C = [4,6)
D = [4,5)
E = [5,7)
```

Các sự kiện theo thứ tự nửa mở:

| Thời điểm | Sự kiện trong cùng mốc | Trạng thái sau mốc `active` |
| ---: | --- | ---: |
| 1 | START A | 1 |
| 2 | START B | 2 |
| 4 | END A, END B, START C, START D | 2 |
| 5 | END D, START E | 2 |
| 6 | END C | 1 |
| 7 | END E | 0 |

Tại `t=4`, `A` và `B` rời đi, còn `C`, `D` bắt đầu. Số khoảng hoạt động ngay sau mốc vẫn là 2. Tại `t=5`, `D` kết thúc và `E` bắt đầu; số khoảng vẫn bằng 2. Vậy **`peak=2`**.

Nếu **chuyển cùng các cặp cận sang khoảng đóng**, tại `t=4` cả `A,B,C,D` đều chứa thời điểm 4, nên đỉnh là **4**. Trong sweep kiểu đóng, START của C và D phải được áp dụng **trước** END của A và B; nếu loại END trước ta sẽ bỏ sót sự chồng lấp ngay tại biên.

Đây là lý do **một thứ tự sắp xếp sai có thể cho kết quả sai dù mọi timestamp đều được sắp tăng dần**.

## 6. Xử lý theo nhóm thời điểm: giải pháp khác cho các sự kiện cộng gộp

Thay vì thao tác trên từng sự kiện, có thể gom mọi sự kiện có cùng `time` rồi cập nhật số đếm **một lần cho mỗi mốc**. Cách này đặc biệt hữu ích khi nhiều sự kiện trùng thời điểm hoặc khi có truy vấn “trạng thái sau mọi cập nhật tại `t`”.

Với **khoảng nửa mở**, đặt:

- `startCount(t)`: số khoảng không rỗng bắt đầu tại `t`.
- `endCount(t)`: số khoảng kết thúc tại `t`.
- `activeBefore`: số khoảng còn hoạt động ngay trước lúc thực hiện nhóm sự kiện tại `t`, sau mốc trước đó.

Ta có:

```text
activeAfter(t) = activeBefore - endCount(t) + startCount(t)
peak = MAX(peak, activeAfter(t))
```

Công thức này chính là **quét mảng sai phân/sự kiện (difference events)**: START đóng góp `+1`, END đóng góp `-1`, rồi lấy tổng tích lũy theo thời gian. Với nửa mở, `activeAfter(t)` phản ánh số khoảng hoạt động tại `t`. Nếu các khoảng không rỗng và hợp lệ, số khoảng sau mỗi mốc không âm.

Với **khoảng đóng**, nhóm thời điểm cần phân biệt trạng thái **tại mốc** với **sau mốc**:

```text
activeAt(t) = activeBefore + startCount(t)
peak = MAX(peak, activeAt(t))
activeAfter(t) = activeAt(t) - endCount(t)
```

Tại `t`, những khoảng cũ kết thúc lúc đó và những khoảng mới bắt đầu lúc đó **đồng thời hiện diện**. Nếu chỉ lấy `activeBefore + startCount - endCount` rồi tính peak, có thể làm mất đỉnh ngay tại mốc. Đây là khác biệt quan trọng giữa **quét từng sự kiện có priority** và **gộp số lượng theo timestamp**.

### Khi nào có thể bỏ qua thứ tự nội bộ?

Nếu chỉ cần trạng thái **sau toàn bộ nhóm thay đổi** và các phép cập nhật là các phép cộng hợp lệ, tổng `+1/-1` có tính giao hoán; ta có thể cộng gộp trước rồi áp dụng một lần. Tuy nhiên, nếu bài toán yêu cầu:

- phát hiện **đỉnh tức thời** theo một quy ước khoảng đóng;
- trả lời **QUERY nằm giữa** các pha cập nhật;
- kiểm tra các ràng buộc trung gian như “không xóa mục chưa tồn tại”;
- phân phối tài nguyên cho từng đối tượng có mã;

thì việc chỉ biết **tổng delta** là chưa đủ. Phải giữ thông tin loại sự kiện, giai đoạn xử lý hoặc thứ tự `sequence` theo đặc tả.

## 7. Java 17+: chương trình quét sự kiện chạy được

Chương trình bên dưới hỗ trợ cả khoảng **nửa mở** `[start,end)` lẫn khoảng **đóng** `[start,end]`. Nó sắp sự kiện bằng **khóa kép `(time, priority)`**, không trừ trực tiếp hai timestamp trong comparator. Kết quả in ra bao gồm đỉnh đồng thời, trạng thái sau từng mốc nửa mở, hai khoảng chạm biên và trường hợp khoảng có hai cận trùng nhau.

Tạo tệp **`EventSweepDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.StringJoiner;

public class EventSweepDemo {
    record Interval(long start, long end) {}
    enum Kind { START, END }
    record Event(long time, Kind kind) {}

    private static int priority(Kind kind, boolean halfOpen) {
        if (halfOpen) {
            return kind == Kind.END ? 0 : 1;
        }
        return kind == Kind.START ? 0 : 1;
    }

    private static List<Event> buildEvents(
            Interval[] intervals, boolean halfOpen) {
        Objects.requireNonNull(intervals, "intervals");
        List<Event> events = new ArrayList<>();

        for (Interval interval : intervals) {
            Objects.requireNonNull(interval, "interval");
            if (interval.start() > interval.end()) {
                throw new IllegalArgumentException("start > end");
            }

            // [t,t) rỗng; [t,t] là một điểm hợp lệ.
            if (halfOpen && interval.start() == interval.end()) {
                continue;
            }

            events.add(new Event(interval.start(), Kind.START));
            events.add(new Event(interval.end(), Kind.END));
        }

        events.sort(Comparator.comparingLong(Event::time)
                .thenComparingInt(e -> priority(e.kind(), halfOpen)));

        return events;
    }

    public static int peakOverlap(
            Interval[] intervals, boolean halfOpen) {
        List<Event> events = buildEvents(intervals, halfOpen);
        int active = 0;
        int peak = 0;

        for (Event event : events) {
            active += event.kind() == Kind.START ? 1 : -1;
            if (active < 0) {
                throw new AssertionError("Negative active count");
            }
            peak = Math.max(peak, active);
        }

        if (active != 0) {
            throw new AssertionError("Unbalanced events");
        }
        return peak;
    }

    public static String halfOpenTimeline(Interval[] intervals) {
        List<Event> events = buildEvents(intervals, true);
        StringJoiner out = new StringJoiner(", ", "[", "]");
        int active = 0;
        int i = 0;

        while (i < events.size()) {
            long time = events.get(i).time();
            while (i < events.size() && events.get(i).time() == time) {
                active += events.get(i).kind() == Kind.START ? 1 : -1;
                i++;
            }
            // Ghi trạng thái sau TOÀN BỘ sự kiện cùng time.
            out.add(time + ":" + active);
        }

        return out.toString();
    }

    public static void main(String[] args) {
        Interval[] intervals = {
            new Interval(1, 4),
            new Interval(2, 4),
            new Interval(4, 6),
            new Interval(4, 5),
            new Interval(5, 7)
        };

        System.out.println("halfOpenPeak=" +
                peakOverlap(intervals, true));
        System.out.println("closedPeak=" +
                peakOverlap(intervals, false));
        System.out.println("halfOpenTimeline=" +
                halfOpenTimeline(intervals));

        Interval[] touching = {
            new Interval(1, 3),
            new Interval(3, 5)
        };
        System.out.println("touchHalfOpen=" +
                peakOverlap(touching, true));
        System.out.println("touchClosed=" +
                peakOverlap(touching, false));

        Interval[] atPoint = {new Interval(3, 3)};
        System.out.println("zeroHalfOpen=" +
                peakOverlap(atPoint, true));
        System.out.println("pointClosed=" +
                peakOverlap(atPoint, false));

        System.out.println("emptyHalfOpen=" +
                peakOverlap(new Interval[0], true));
    }
}
```

Biên dịch và chạy:

```bash
javac EventSweepDemo.java
java EventSweepDemo
```

**Đầu ra chính xác:**

```text
halfOpenPeak=2
closedPeak=4
halfOpenTimeline=[1:1, 2:2, 4:2, 5:2, 6:1, 7:0]
touchHalfOpen=1
touchClosed=2
zeroHalfOpen=0
pointClosed=1
emptyHalfOpen=0
```

**Đọc kết quả:**

1. `halfOpenPeak=2`: tại mốc 4, hai khoảng cũ đã kết thúc trước khi hai khoảng mới bắt đầu; không có bốn khoảng cùng hoạt động.
2. `closedPeak=4`: cả bốn khoảng chứa mốc 4 nếu cận kết thúc được tính vào khoảng.
3. `halfOpenTimeline` chỉ ghi một trạng thái **sau mỗi mốc thời gian khác nhau**, không ghi các giá trị trung gian chưa hoàn tất nhóm sự kiện.
4. Hai khoảng chạm biên có đỉnh 1 với quy ước nửa mở và đỉnh 2 với quy ước đóng.
5. `[3,3)` không có phần tử thời gian nào và bị bỏ qua; `[3,3]` có một điểm nên đỉnh bằng 1.
6. Với danh sách khoảng rỗng, không có sự kiện, đỉnh bằng 0.

**Giải thích mã:** `buildEvents` tạo tối đa hai sự kiện cho mỗi khoảng, bỏ qua khoảng rỗng khi `halfOpen=true`, rồi sắp bằng `Comparator.comparingLong(Event::time).thenComparingInt(...)`. `peakOverlap` duyệt từng sự kiện đã sắp, còn `halfOpenTimeline` gom mọi sự kiện trùng timestamp trước khi ghi lại trạng thái.

Ở đây các sự kiện **cùng time và cùng kind** chỉ làm thay đổi một bộ đếm bằng phép cộng, nên thứ tự của chúng không ảnh hưởng kết quả. Nếu sự kiện có mã người dùng, giao dịch hoặc các tác động không giao hoán, cần thêm quy tắc phá hòa thứ ba theo `sequence` hoặc `id` phù hợp.

**Kiểu dữ liệu:** timestamp dùng `long`. Comparator không làm `(int)(a.time-b.time)` hoặc `a.time-b.time`, vì phép trừ có thể tràn; API `comparingLong` xử lý so sánh theo giá trị có thứ tự. Bộ đếm `int` đủ khi số khoảng được truyền bằng độ dài mảng Java; giá trị `active` không vượt số khoảng đầu vào hợp lệ.

## 8. Chứng minh đúng và phân tích độ phức tạp

### Tính đúng của bản quét nửa mở

Gọi `S(t)` là số khoảng `[s,e)` thỏa `s ≤ t < e`. Sau khi xử lý tất cả sự kiện ở một timestamp `t`, ta muốn `active=S(t)`.

**Cơ sở:** trước timestamp nhỏ nhất, không có khoảng không rỗng nào bắt đầu; `active=0`.

**Bước quy nạp:** xét timestamp kế tiếp `t`. Từ trạng thái ở mốc trước, chỉ các khoảng có END tại `t` thôi không còn hoạt động, và chỉ các khoảng có START tại `t` mới bắt đầu hoạt động. Không có thay đổi tại những thời điểm trung gian vì tất cả cận đều đã được biểu diễn bằng sự kiện. Xử lý END trước START cho:

`active mới = active cũ - endCount(t) + startCount(t) = S(t)`.

Do số đếm đúng sau mỗi timestamp và không thay đổi giữa các timestamp liên tiếp, đỉnh của các trạng thái đúng ấy là **số khoảng hoạt động đồng thời lớn nhất**. Với END trước START, các bước trung gian không vượt đỉnh thật tại mốc; vì vậy cập nhật `peak` ngay sau từng sự kiện cũng đúng.

Đối với bản **khoảng đóng**, xét trạng thái tại đúng mốc `t` sau START nhưng **trước END**; đó là lúc mọi khoảng đóng chứa `t` đều được tính. Bởi thế cập nhật `peak` khi START được xử lý trước END cũng cho đúng đỉnh.

**Kết thúc:** danh sách sự kiện hữu hạn (tối đa `2n` mục); sau sort, vòng duyệt xử lý từng mục đúng một lần. Không có vòng lặp phụ nào không giảm chỉ số; `halfOpenTimeline` tăng `i` sau mỗi sự kiện, nên chắc chắn kết thúc.

### Chi phí

Với `n` khoảng:

| Giai đoạn | Thời gian | Bộ nhớ phụ |
| --- | --- | --- |
| Tạo sự kiện | O(n) | O(n) cho tối đa `2n` sự kiện |
| Sắp theo `(time,priority)` | O(n log n) với sort so sánh | Phụ thuộc thuật toán sắp xếp của thư viện |
| Quét tính peak | O(n) | O(1) ngoài danh sách đã sắp |
| Ghi timeline theo timestamp | O(n) bước quét, cộng chi phí tạo chuỗi đầu ra | O(k) cho kết quả chuỗi với `k` mốc khác nhau |

Tổng thời gian của lời gọi quét gồm bước sort là **O(n log n)** trong trường hợp xấu nhất của thuật toán sắp xếp so sánh phù hợp; bộ nhớ để lưu sự kiện là **O(n)**. Không được tuyên bố toàn bộ lời giải dùng O(1) bộ nhớ chỉ vì bước quét có vài biến đếm.

Nếu đầu vào đã là các sự kiện được sắp đúng khóa, bản quét riêng có thể chỉ O(n); nhưng phải bảo đảm **cả thứ tự thời gian và priority khi trùng mốc**, không chỉ thời gian.

Trong một số bài với thời điểm nguyên nằm trong miền nhỏ, có thể dùng **mảng sai phân** hoặc **đếm theo tọa độ** thay vì sort. Nếu các mốc rất lớn hoặc rất thưa, danh sách sự kiện + sort thường tránh việc cấp bộ nhớ theo toàn bộ miền thời gian.

## 9. Truy vấn trạng thái tại cùng thời điểm

Nhiều bài không chỉ hỏi peak mà còn hỏi **“đang hoạt động bao nhiêu tại t?”**. Hãy coi truy vấn như một loại event:

```text
Event(time, kind=QUERY, queryId)
```

Lúc này quy tắc ưu tiên phải bao hàm QUERY:

- Với khoảng **nửa mở**: `END(0) → START(1) → QUERY(2)`. Query tại `t` nhìn thấy các khoảng bắt đầu tại `t`, không nhìn thấy các khoảng kết thúc tại `t`.
- Với khoảng **đóng**: `START(0) → QUERY(1) → END(2)`. Query tại `t` thấy cả hai loại khoảng có cận tại `t`.

Ví dụ `A=[1,3)`, `B=[3,5)`, truy vấn tại `t=3` phải trả 1. Nếu đẩy QUERY lên trước START, nó có thể trả 0 sau khi END của A đã được xử lý; đó là **trạng thái giữa hai pha**, không phải trạng thái tại `t=3` theo quy ước nửa mở.

Với các phép xử lý không có tính giao hoán, chẳng hạn “nạp tiền” và “rút tiền” vào cùng tài khoản, chưa chắc chỉ một quy tắc ưu tiên START/END là đủ. Cần đặc tả rõ các giao dịch cùng thời điểm được xử lý theo thứ tự bản ghi, số thứ tự giao dịch hay cơ chế nguyên tử nào. Nếu đề bài không nói, không nên tự gán kết quả được coi là duy nhất.

## 10. So sánh các hướng xử lý sự kiện

| Phương pháp | Khi nào phù hợp | Điểm cần nhớ |
| --- | --- | --- |
| **Sort sự kiện + quét** | Khoảng hoạt động, giao nhau, đếm lịch sự kiện; tọa độ thưa/lớn | Định nghĩa `(time,priority)` chính xác. |
| **Nhóm các timestamp rồi áp dụng delta** | Chỉ quan tâm trạng thái sau mốc, cập nhật cộng dồn | Với khoảng đóng cần tính peak **trước khi trừ END**. |
| **Mảng sai phân trực tiếp** | Thời điểm là chỉ số nguyên trong miền nhỏ | Cẩn thận cách đổi cận đóng/nửa mở và kích thước mảng. |
| **Nén tọa độ + sai phân** | Nhiều timestamp rất lớn nhưng chỉ ít mốc khác nhau | Giữ thứ tự mốc; mỗi mốc có thể chứa nhiều sự kiện. |
| **Min-heap thời điểm kết thúc** | Bài toán phân phòng họp/số tài nguyên cần mở | Phải xác định tại `start == end` phòng cũ có thể tái sử dụng không. |

Ví dụ số phòng họp tối thiểu cho các cuộc họp nửa mở, với một phòng không chứa hai cuộc họp chồng nhau: đáp án bằng **`peak`** của sweep. Khi một cuộc họp kết thúc đúng lúc cuộc họp khác bắt đầu, có thể dùng lại phòng, do đó END trước START là đúng.

Nếu bài toán yêu cầu **gán mã phòng cụ thể**, chỉ đếm `peak` chưa đủ để xuất phương án. Ta có thể cần heap chứa thời điểm kết thúc và ID phòng, cùng quy tắc giải phóng/tái sử dụng. Khái niệm tie-break vẫn cần thiết, nhưng cấu trúc kết quả nhiều hơn một bộ đếm.

## 11. Lỗi thường gặp

1. **Chỉ sắp theo timestamp mà không xét thứ tự trùng.** Thứ tự START/END có thể làm kết quả `peak` sai dù toàn bộ mốc tăng dần.
2. **Tự coi mọi khoảng là nửa mở.** Một đề yêu cầu cả hai đầu đều được tính thì cần START trước END tại mốc trùng.
3. **Xử lý `[t,t)` như khoảng hoạt động.** Khoảng nửa mở độ dài 0 là rỗng; nếu không bỏ qua, END trước START có thể làm `active` tạm âm.
4. **Đếm đỉnh chỉ ở cuối nhóm timestamp cho khoảng đóng.** Có thể bỏ lỡ trạng thái tất cả khoảng cùng hiện diện đúng tại mốc.
5. **Ghi `QUERY` sai pha.** Query tại `t` phải được đặt giữa/bên cạnh các sự kiện khác theo chính xác ngữ nghĩa của bài.
6. **Dựa vào stable sort như một quy tắc nghiệp vụ.** Sort ổn định không tự thay comparator có priority đúng.
7. **Comparator dùng phép trừ timestamp.** `a.time-b.time` có thể tràn số, làm kết quả so sánh không nhất quán; dùng `Long.compare` hoặc `Comparator.comparingLong`.
8. **Quên ranh giới cận.** `[s,e)` hoạt động khi `s ≤ t < e`, còn `[s,e]` hoạt động khi `s ≤ t ≤ e`; chỉ khác một dấu nhưng ảnh hưởng tie.
9. **Gộp sự kiện khi tác động không giao hoán.** Một chuỗi UPDATE/DELETE/QUERY không thể luôn rút gọn thành tổng delta.
10. **Đọc trạng thái giữa những sự kiện cùng mốc rồi tưởng là trạng thái thực.** Cần xác định điểm đọc trạng thái sau nhóm nào.
11. **Dùng thời gian địa phương không rõ múi giờ/DST.** Nếu sự kiện có thể trải qua chuyển giờ hoặc nhiều múi giờ, nên chuẩn hóa về các mốc thời gian có thứ tự xác định (ví dụ `Instant`) trước khi so sánh.
12. **Báo O(n) cho toàn thuật toán khi còn phải sort.** Quét O(n) nhưng việc sort `2n` sự kiện thường O(n log n).
13. **Không kiểm tra khoảng không hợp lệ.** Nếu `start > end`, phải xác định lỗi thay vì âm thầm sinh sự kiện không đúng ngữ nghĩa.
14. **Không kiểm thử sự kiện trùng thời điểm.** Dữ liệu có các mốc liền nhau, tất cả bắt đầu/kết thúc cùng lúc và khoảng rỗng là các kiểm thử bắt buộc.

## 12. Bài tập tự kiểm tra và lời giải

**Bài 1.** Hai khoảng `[1,3)` và `[3,5)` cần tối thiểu bao nhiêu phòng? **Đáp án:** 1 phòng, vì tại `t=3` khoảng thứ nhất không còn hoạt động; xử lý END trước START.

**Bài 2.** Nếu cùng hai khoảng ở Bài 1 đổi thành `[1,3]` và `[3,5]`, số khoảng hoạt động lớn nhất là bao nhiêu? **Đáp án:** 2; tại `t=3` cả hai khoảng đóng đều chứa mốc này, nên START trước END.

**Bài 3.** Với các khoảng nửa mở `[1,4),[2,4),[4,6),[4,5),[5,7)`, giá trị `active` sau xử lý toàn bộ sự kiện tại `t=4` là bao nhiêu? **Đáp án:** `2`; có hai END và hai START tại mốc đó.

**Bài 4.** Vì sao `[7,7)` nên bỏ qua trong thuật toán đếm số khoảng đồng thời nửa mở? **Đáp án:** đây là tập thời điểm rỗng. Sinh END và START rồi xử lý END trước START có thể làm số đếm tạm thời âm mà không biểu diễn một khoảng thực.

**Bài 5.** Với khoảng đóng `[1,4]` và `[4,6]`, nếu chỉ cộng `(+1)` cho START và `(-1)` cho END rồi ghi trạng thái **sau mọi sự kiện** tại `t=4`, có thể bỏ sót điều gì? **Đáp án:** đỉnh 2 đúng tại `t=4`. Phải xét trạng thái sau START nhưng trước END.

**Bài 6.** Nếu cần truy vấn số khoảng nửa mở hoạt động tại chính thời điểm `t`, thứ tự END, START, QUERY là gì? **Đáp án:** `END → START → QUERY`; truy vấn phải thấy khoảng mới bắt đầu và không thấy khoảng vừa kết thúc.

**Bài 7.** Nếu có `n` khoảng và tạo hai sự kiện mỗi khoảng, độ phức tạp sort + quét là bao nhiêu? **Đáp án:** O(n log n) thời gian và O(n) bộ nhớ để lưu sự kiện, vì `2n=O(n)`.

**Bài 8.** Hai sự kiện `START` có cùng timestamp nhưng thuộc hai người dùng khác nhau. Có cần sắp theo `id` không? **Đáp án:** không cần nếu bài chỉ đếm số lượng (hai phép cộng giao hoán); nếu hệ thống cần thứ tự thao tác nghiệp vụ hoặc log xác định, phải có khóa thứ ba như `sequence` hoặc `id` theo đặc tả.

**Bài 9.** Vì sao `Comparator.comparingLong(Event::time)` an toàn hơn `(int)(a.time() - b.time())`? **Đáp án:** kiểu `long` có thể tràn khi trừ hai mốc cách xa nhau; ép xuống `int` còn làm mất thông tin. API so sánh số nguyên đúng thứ tự tránh lỗi đó.

**Bài 10.** Với đúng một khoảng đóng `[3,3]` và một khoảng nửa mở `[3,3)`, kết quả đỉnh khác nhau thế nào? **Đáp án:** đóng cho 1, nửa mở cho 0, vì một khoảng gồm điểm 3 còn khoảng kia rỗng.

## 13. Checklist thiết kế một thuật toán sự kiện

Trước khi viết code, hãy trả lời:

1. **Đơn vị thời gian/toạ độ là gì?** Số nguyên, timestamp thực hay `Instant`? Có vấn đề múi giờ và giá trị bằng nhau không?
2. **Khoảng có bao gồm cận cuối không?** `[s,e)` hay `[s,e]`? Khoảng `s=e` có hợp lệ và có ý nghĩa gì?
3. **Những loại sự kiện nào có mặt?** START, END, QUERY hay cập nhật khác?
4. **Quy tắc phá hòa là gì?** Viết rõ bảng priority khi `time` bằng nhau, và thêm `sequence` nếu cần.
5. **Trạng thái được quan sát khi nào?** Sau mỗi sự kiện, sau mọi sự kiện cùng timestamp, hay chính xác ở pha QUERY?
6. **Có thể gộp theo timestamp không?** Chỉ gộp những phép cập nhật có tính chất toán học/giữ ngữ nghĩa phù hợp.
7. **Bất biến quét là gì?** `active` phải mô tả tập khoảng nào tại thời điểm đã xử lý.
8. **Độ phức tạp tính đủ chưa?** Có tính tạo sự kiện, sort, bộ nhớ sự kiện và dữ liệu kết quả không?
9. **Kiểm thử các mốc trùng chưa?** Chạm biên, nhiều START/END đồng thời, khoảng rỗng, mảng rỗng, khoảng sai cận và timestamp lớn.

**Ghi nhớ:** thuật toán xử lý sự kiện phải sắp xếp theo **thứ tự ngữ nghĩa**, không chỉ theo giá trị thời gian. Khi nhiều sự kiện cùng timestamp, quyết định END/START/QUERY trước–sau là **một phần của đặc tả và chứng minh đúng**, không phải chi tiết triển khai nhỏ có thể bỏ qua.
