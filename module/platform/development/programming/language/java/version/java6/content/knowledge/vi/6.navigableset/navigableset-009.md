# Ứng dụng NavigableSet để tra cứu ngưỡng, khoảng và lịch biểu

## 1. Vì sao cần một tập hợp có khả năng điều hướng?

Một `Set` thông thường giúp trả lời “giá trị này có tồn tại không?”. Trong nhiều bài toán, câu hỏi thực tế lại là:

- Mức thấp nhất cần đạt đã được vượt qua tới đâu?
- Mốc tiếp theo không nhỏ hơn giá trị đang xét là gì?
- Những giá trị nào nằm trong một khoảng?
- Lịch bắt đầu gần nhất từ một thời điểm trở đi là lúc nào?

`NavigableSet` hữu ích khi dữ liệu là **các giá trị duy nhất, đã được tổ chức theo một thứ tự**, và ứng dụng thường hỏi về hàng xóm hoặc phạm vi. `TreeSet` là một cách triển khai quen thuộc để dùng trong chương trình đơn luồng.

Cần xác định ý nghĩa của thứ tự trước khi chọn phương thức. Ví dụ “ngưỡng đã đạt” thường đi về phía nhỏ hơn hoặc bằng, còn “ngưỡng cần đạt tiếp theo” đi về phía lớn hơn. Hai câu hỏi gần nhau về ngôn ngữ nhưng có kết quả khác nhau.

Các phép điều hướng và truy vấn khoảng vẫn là API hiện hành; xem [NavigableSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableSet.html).

## 2. Đổi yêu cầu nghiệp vụ thành một quan hệ rõ ràng

Với thứ tự tự nhiên của số hoặc ngày giờ:

| Yêu cầu | Phương thức |
| --- | --- |
| Mốc lớn nhất không vượt quá x | `floor(x)` |
| Mốc lớn nhất nhưng phải nhỏ hơn x | `lower(x)` |
| Mốc nhỏ nhất không thấp hơn x | `ceiling(x)` |
| Mốc nhỏ nhất nhưng phải lớn hơn x | `higher(x)` |
| Các mốc trong khoảng hai đầu | `subSet(...)` |
| Các mốc trước một biên | `headSet(...)` |
| Các mốc sau một biên | `tailSet(...)` |

`floor/lower/ceiling/higher` trả `null` nếu không có phần tử đáp ứng; chúng không tự tạo mốc mới. Cần quyết định trước có chấp nhận **bằng mốc truy vấn** hay không. Hợp đồng chính xác được mô tả tại [các phương thức điều hướng NavigableSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableSet.html).

Nếu tập hợp dùng comparator đảo hoặc một quy tắc riêng, “nhỏ hơn/lớn hơn” phải hiểu theo comparator ấy. Trong các ví dụ của bài, số nguyên và `LocalDateTime` đều dùng thứ tự tự nhiên để ý nghĩa nghiệp vụ dễ kiểm tra.

## 3. Ứng dụng thứ nhất: tra cứu ngưỡng

Giả sử hệ thống có các mức điểm tối thiểu:

```text
0, 50, 100, 200
```

Với số điểm 135:

- `floor(135)` là 100: đây là ngưỡng cao nhất đã đạt.
- `ceiling(135)` là 200: đây là ngưỡng thấp nhất không dưới điểm đang xét.

Với đúng 100 điểm:

- `floor(100)` và `ceiling(100)` cùng trả 100.
- `lower(100)` trả 50.
- `higher(100)` trả 200.

Nếu “mức tiếp theo” nghĩa là **một mức mới cao hơn mức hiện tại**, dùng `higher`. Nếu nghĩa là **mức đáp ứng điều kiện ít nhất bằng đầu vào**, dùng `ceiling`. Viết rõ điều kiện giúp tránh lỗi ở chính điểm ranh giới.

### Không có kết quả là một trạng thái nghiệp vụ

`floor(-1)` trả `null` vì chưa đạt ngưỡng thấp nhất. Ứng dụng có thể từ chối đầu vào âm hoặc báo chưa đủ điều kiện, tùy quy tắc.

`ceiling(250)` trả `null` vì không có mốc nào lớn hơn hoặc bằng 250 trong dữ liệu. Nó không có nghĩa phép tra cứu gặp lỗi; có thể đơn giản là đã vượt mức cao nhất đang được cấu hình.

Giữ kiểu tham chiếu để kiểm tra trước khi mở hộp:

```java
// minimumScores la NavigableSet<Integer>.
Integer threshold = minimumScores.floor(score);
if (threshold == null) {
    // Xu ly truong hop khong co nguong phu hop.
} else {
    int reached = threshold;
    // Dung nguong da tim duoc.
}
```

Đoạn trên là minh họa cách dùng, không phải chương trình độc lập.

### Khi nào cần cấu trúc khác?

`NavigableSet<Integer>` chỉ lưu các mốc. Nếu mỗi mốc còn có tên hạng, tỷ lệ hoặc cấu hình đi kèm, một `NavigableMap` từ mốc sang dữ liệu thường diễn đạt yêu cầu trực tiếp hơn.

Đừng tự hiểu `ceiling(x)` là “gần x nhất theo khoảng cách”. Nó chỉ tìm về một phía. Với bài toán gần nhất theo khoảng cách số học, cần xét cả `floor` và `ceiling`, xử lý phía bị thiếu và quy tắc khi hai khoảng cách bằng nhau.

## 4. Ứng dụng thứ hai: truy vấn khoảng giá trị

Với các mã `[10, 20, 30, 40, 50, 60]`:

```java
// codes la NavigableSet<Integer>.
NavigableSet<Integer> selected = codes.subSet(20, true, 50, false);
```

Kết quả là `[20, 30, 40]`, tương ứng khoảng nửa mở `[20, 50)`. Mốc 20 được phép xuất hiện, mốc 50 bị loại.

Khoảng nửa mở hữu ích khi chia các đoạn liên tiếp. Hai đoạn `[0, 100)` và `[100, 200)` không tính 100 hai lần.

Mốc không cần có sẵn. `subSet(21, true, 49, true)` vẫn hợp lệ và cho `[30, 40]`. Cờ bao gồm biên chỉ điều khiển điều kiện so sánh, không tạo ra 21 hoặc 49.

Kết quả truy vấn khoảng là khung nhìn dùng chung dữ liệu với tập gốc. Nếu chỉ muốn giữ một tập kết quả độc lập tại thời điểm truy vấn, có thể sao chép bằng `new TreeSet<>(selected)`. Nếu sửa trực tiếp khung nhìn, tập gốc cũng chịu tác động. Xem [hợp đồng khung nhìn của TreeSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeSet.html).

## 5. Ứng dụng thứ ba: tra cứu mốc trong lịch biểu

Giả sử lịch ngày 02/11/2026 có các giờ bắt đầu 08:30, 10:00, 13:30 và 18:00.

Tại mốc 10:00:

- “Từ bây giờ trở đi, có thể gồm chính 10:00”: `ceiling(reference)` trả 10:00.
- “Sau 10:00, phải là một mốc muộn hơn”: `higher(reference)` trả 13:30.
- “Mốc gần nhất không muộn hơn 10:00”: `floor(reference)` trả 10:00.
- “Mốc trước 10:00”: `lower(reference)` trả 08:30.

Đây là tìm trong **các mốc bắt đầu đã có**. Không được gọi `floor(reference)` là “cuộc hẹn đang diễn ra” nếu chưa xét thời lượng và giờ kết thúc.

### Lấy trọn một ngày bằng hai mốc

Có thể lấy lịch trong ngày bằng khoảng:

```java
// starts la NavigableSet<LocalDateTime>, day la LocalDate.
NavigableSet<LocalDateTime> today = starts.subSet(
        day.atStartOfDay(), true,
        day.plusDays(1).atStartOfDay(), false);
```

Cách này gồm đúng đầu ngày và loại đầu ngày tiếp theo. Không cần đoán giá trị kiểu `23:59:59.999`, dễ bỏ sót dữ liệu có độ chính xác cao hơn.

Trong ví dụ, `LocalDateTime` biểu diễn ngày giờ địa phương trong cùng một ngữ cảnh lịch. Nó không chứa múi giờ và không tự xác định một thời điểm tuyệt đối. Xem [LocalDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDateTime.html).

## 6. Chương trình đầy đủ chạy trên Java 17+

Ví dụ cố định dữ liệu và thời điểm truy vấn để stdout luôn có thể tái hiện. Nó không phụ thuộc giờ hiện tại của máy.

Tệp `NavigableSetApplications.java`:

```java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;
import java.util.NavigableSet;
import java.util.TreeSet;

public class NavigableSetApplications {
    private static void thresholds() {
        NavigableSet<Integer> minimumScores =
                new TreeSet<>(List.of(0, 50, 100, 200));

        System.out.println("threshold floor(135)=" + minimumScores.floor(135));
        System.out.println("threshold ceiling(135)=" + minimumScores.ceiling(135));
        System.out.println("threshold floor(100)=" + minimumScores.floor(100));
        System.out.println("threshold lower(100)=" + minimumScores.lower(100));
        System.out.println("threshold ceiling(100)=" + minimumScores.ceiling(100));
        System.out.println("threshold higher(100)=" + minimumScores.higher(100));
        System.out.println("threshold floor(-1)=" + minimumScores.floor(-1));
        System.out.println("threshold ceiling(250)=" + minimumScores.ceiling(250));
    }

    private static void valueRanges() {
        NavigableSet<Integer> codes =
                new TreeSet<>(List.of(10, 20, 30, 40, 50, 60));

        System.out.println("codes [20,50)="
                + codes.subSet(20, true, 50, false));
        System.out.println("codes <30=" + codes.headSet(30, false));
        System.out.println("codes >=30=" + codes.tailSet(30, true));
        System.out.println("codes [21,49]="
                + codes.subSet(21, true, 49, true));
    }

    private static void schedule() {
        LocalDate day = LocalDate.of(2026, 11, 2);
        NavigableSet<LocalDateTime> starts = new TreeSet<>(List.of(
                day.atTime(8, 30),
                day.atTime(10, 0),
                day.atTime(13, 30),
                day.atTime(18, 0),
                day.plusDays(1).atStartOfDay()
        ));

        LocalDateTime reference = day.atTime(10, 0);
        System.out.println("schedule at-or-after=" + starts.ceiling(reference));
        System.out.println("schedule strictly-after=" + starts.higher(reference));
        System.out.println("schedule at-or-before=" + starts.floor(reference));
        System.out.println("schedule strictly-before=" + starts.lower(reference));

        NavigableSet<LocalDateTime> today = starts.subSet(
                day.atStartOfDay(), true,
                day.plusDays(1).atStartOfDay(), false);
        System.out.println("schedule day=" + today);
        System.out.println("schedule [09:00,14:00)=" + starts.subSet(
                day.atTime(9, 0), true, day.atTime(14, 0), false));
        System.out.println("schedule due-by-10:00="
                + today.headSet(reference, true));

        NavigableSet<LocalDateTime> snapshot = new TreeSet<>(today);
        snapshot.remove(reference);
        System.out.println("snapshot size=" + snapshot.size());
        System.out.println("original day size=" + today.size());

        LocalDateTime afterLast = day.plusDays(1).atTime(23, 0);
        System.out.println("schedule after-last=" + starts.ceiling(afterLast));
    }

    public static void main(String[] args) {
        thresholds();
        valueRanges();
        schedule();
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 NavigableSetApplications.java
java NavigableSetApplications
```

Kết quả:

```text
threshold floor(135)=100
threshold ceiling(135)=200
threshold floor(100)=100
threshold lower(100)=50
threshold ceiling(100)=100
threshold higher(100)=200
threshold floor(-1)=null
threshold ceiling(250)=null
codes [20,50)=[20, 30, 40]
codes <30=[10, 20]
codes >=30=[30, 40, 50, 60]
codes [21,49]=[30, 40]
schedule at-or-after=2026-11-02T10:00
schedule strictly-after=2026-11-02T13:30
schedule at-or-before=2026-11-02T10:00
schedule strictly-before=2026-11-02T08:30
schedule day=[2026-11-02T08:30, 2026-11-02T10:00, 2026-11-02T13:30, 2026-11-02T18:00]
schedule [09:00,14:00)=[2026-11-02T10:00, 2026-11-02T13:30]
schedule due-by-10:00=[2026-11-02T08:30, 2026-11-02T10:00]
snapshot size=3
original day size=4
schedule after-last=null
```

### Đọc các chi tiết có ý nghĩa

Lịch gốc còn có `2026-11-03T00:00`, nhưng truy vấn cả ngày 02/11 loại mốc ấy. Như vậy một công việc đúng 00:00 của ngày sau không bị gán nhầm vào ngày trước.

`today.headSet(reference, true)` trả các mốc trong ngày không muộn hơn 10:00. Nhãn `due-by-10:00` chỉ diễn đạt quan hệ thời gian; dữ liệu ví dụ chưa lưu trạng thái đã xử lý hay chưa xử lý. Không thể suy ra mọi mục trong kết quả đều là công việc đang chờ.

Chương trình xóa 10:00 khỏi `snapshot`, còn `today` vẫn có bốn phần tử. Điều này minh họa bản sao cấu trúc độc lập với khung nhìn gốc.

Khi hỏi sau mốc cuối đã lưu, kết quả là `null`. Cấu trúc không tự tạo lịch cho những ngày chưa được đưa vào dữ liệu.

## 7. Mô hình lịch biểu có những giới hạn nào?

### Cùng giờ bắt đầu có thể có nhiều công việc

Một `TreeSet<LocalDateTime>` chỉ giữ một giá trị cho cùng ngày giờ. Nếu ba công việc bắt đầu lúc 10:00, lưu ba lần cùng `LocalDateTime` không giữ được ba công việc.

Có thể dùng bản đồ từ giờ bắt đầu đến danh sách công việc, hoặc dùng đối tượng có mã định danh cùng một quy tắc so sánh đầy đủ. Với đối tượng trong `TreeSet`, comparator quyết định phần tử nào được xem là trùng; thiết kế thứ tự phải phù hợp với yêu cầu danh tính và hợp đồng `equals`. Xem [TreeSet và quy tắc so sánh](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeSet.html).

### Có mốc bắt đầu không đồng nghĩa không chồng lịch

Giả sử đã có cuộc hẹn 09:00–11:00. Một yêu cầu mới 10:00–10:30 không tìm thấy mốc bắt đầu cũ nào trong `[10:00, 10:30)`, nhưng hai cuộc hẹn vẫn chồng nhau.

Với các khoảng nửa mở `[startA, endA)`, `[startB, endB)` có độ dài dương, điều kiện chồng nhau là:

```text
startA < endB AND startB < endA
```

Một tập chỉ lưu thời điểm bắt đầu không có đủ thông tin để đánh giá công thức này. Cần lưu giờ kết thúc và lựa chọn thuật toán tra cứu phù hợp với những ràng buộc của lịch. Không dùng một truy vấn `subSet` trên giờ bắt đầu rồi kết luận toàn bộ khoảng thời gian đang trống.

### Ngày giờ địa phương và thời điểm tuyệt đối

Nếu người dùng hoặc công việc trải qua nhiều múi giờ, cần phân biệt:

- Giờ theo lịch địa phương, ví dụ “09:00 ở một thành phố”.
- Thời điểm trên dòng thời gian, ví dụ một giá trị `Instant`.

Một giờ địa phương ở vùng có đổi giờ mùa hè có thể không tồn tại hoặc tương ứng với hai offset. `ZonedDateTime` kết hợp ngày giờ, múi giờ và offset, đồng thời có quy tắc xử lý những trường hợp ấy. Xem [ZonedDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html).

Nếu lưu `Instant` để truy vấn một ngày theo múi giờ người dùng, hãy xác định hai đầu ngày trong múi giờ đó rồi chuyển thành `Instant`. Không mặc định mọi ngày lịch đều dài đúng 24 giờ.

### Tra cứu lịch không phải tự chạy lịch

`NavigableSet` là cấu trúc dữ liệu. Nó không tự đánh thức luồng lúc đến hạn, thực thi công việc, lưu bền dữ liệu, tạo lịch lặp hay bảo đảm chạy đúng một lần.

Bộ lập lịch thực tế còn cần đồng hồ, cơ chế chờ/thực thi, quản lý hủy, lỗi và khởi động lại. Một set có thể đóng vai trò chỉ mục hỗ trợ truy vấn trong thiết kế ấy.

## 8. Cách áp dụng mà không làm sai yêu cầu

Trước khi viết lời gọi API, hãy xác định:

1. **Giá trị lưu là gì?** Mốc đơn lẻ, ngưỡng, giờ bắt đầu hay cả một khoảng thời gian?
2. **Thứ tự là gì?** Thứ tự tự nhiên, comparator đảo hay một ưu tiên nghiệp vụ?
3. **Có bao gồm điểm bằng nhau không?** Chọn đúng `lower/floor`, `higher/ceiling` và cờ biên.
4. **Không tìm thấy nghĩa là gì?** Chưa đạt mức, hết lịch, đầu vào không hợp lệ hay cần nạp thêm dữ liệu?
5. **Có cần giữ phần tử trùng hoặc dữ liệu kèm theo không?** Nếu có, một set giá trị đơn có thể chưa phù hợp.
6. **Kết quả có được phép làm thay đổi nguồn không?** Phân biệt khung nhìn đang hoạt động với bản sao.

Ví dụ chỉ dùng một luồng. Nếu các luồng cùng truy cập và có luồng sửa `TreeSet`, phải có cơ chế đồng bộ phù hợp; việc các câu truy vấn ngắn không tạo ra bảo đảm an toàn đa luồng. Xem [hợp đồng đồng bộ TreeSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeSet.html).

## 9. Kiểm thử và thực hành

- Với ngưỡng: thử dưới mức thấp nhất, đúng mỗi mốc, giữa hai mốc và trên mức cao nhất. Kiểm tra riêng trường hợp trả `null`.
- Với khoảng: thử mốc có sẵn/chưa có, bốn tổ hợp bao gồm biên và khoảng không chứa phần tử.
- Với lịch: thử đúng giờ bắt đầu, giữa hai giờ, trước giờ đầu, sau giờ cuối và đúng 00:00 của ngày kế tiếp.
- Với dữ liệu: thử hai công việc cùng giờ và xác định thiết kế có giữ được cả hai không.
- Với thời gian: giữ thời điểm truy vấn cố định trong kiểm thử; với xử lý múi giờ, có thêm ca cho ngày chuyển offset.

Bài tập: đổi thời điểm truy vấn từ 10:00 sang 10:01 và dự đoán bốn kết quả điều hướng trước khi chạy. Sau đó thêm 09:30 và kiểm tra truy vấn `[09:00, 14:00)`. Cuối cùng, giải thích vì sao thấy đủ các giờ bắt đầu trong khoảng vẫn chưa chứng minh không có cuộc hẹn dài bắt đầu từ trước khoảng đó.
