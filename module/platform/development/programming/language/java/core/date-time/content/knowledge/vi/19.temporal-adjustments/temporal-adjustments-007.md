# Tính ngày làm việc và tách chính sách ngày nghỉ khỏi phép tính lịch

## 1. Ngày làm việc là kết quả của một chính sách

`LocalDate` biểu diễn một ngày trên lịch ISO, chẳng hạn `2024-04-05`. Nó biết ngày đó là thứ mấy, biết năm nhuận và biết chuyển sang ngày kế tiếp. Nó không biết một doanh nghiệp, chi nhánh hay thị trường có làm việc vào ngày đó hay không.

**Ngày theo lịch** là mọi ngày liên tiếp trên lịch. **Ngày làm việc** là ngày được một chính sách nghiệp vụ chấp nhận. Một chính sách có thể gồm ngày nghỉ hằng tuần, ngày nghỉ cụ thể và ngày làm bù. Vì vậy, phép cộng ba ngày theo lịch và phép cộng ba ngày làm việc trả lời hai câu hỏi khác nhau.

Theo [Java API của LocalDate](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html), đối tượng này không chứa giờ hay múi giờ và không đại diện trực tiếp cho một thời điểm trên dòng thời gian. Bài này xử lý đơn vị ngày; không tính số giờ làm, thời hạn theo giờ hay lịch ca.

Ví dụ giả định: thứ Sáu 05/04/2024 là ngày nhận yêu cầu; thứ Bảy và Chủ nhật nghỉ; thứ Hai 08/04 được cấu hình nghỉ thêm. Nếu không tính ngày nhận, một ngày làm việc tiếp theo là thứ Ba 09/04. Gọi `plusDays(1)` chỉ ra thứ Bảy 06/04, vì phương thức đó không có tham số chính sách làm việc.

Không có một lịch nghỉ mặc định phù hợp mọi quốc gia hay đơn vị. Mọi ngày nghỉ và ngày làm bù trong bài đều là **dữ liệu giả định để kiểm chứng thuật toán**, không phải công bố lịch nghỉ thực tế.

## 2. Tách hai trách nhiệm trước khi viết vòng lặp

Phần **chính sách** trả lời một câu hỏi:

```java
boolean isBusinessDay(LocalDate date);
```

Phần **phép tính lịch** duyệt các ngày, gọi chính sách và quyết định khi nào dừng. Nó không cần biết ngày nghỉ đến từ tệp cấu hình, cơ sở dữ liệu, lịch thị trường hay quy tắc riêng của chi nhánh.

Trong Java, có thể dùng `Predicate<LocalDate>` để truyền câu trả lời đó vào thuật toán. Với mô hình nhỏ, một đối tượng lịch có phương thức `isBusinessDay` và được truyền dưới dạng `calendar::isBusinessDay` là đủ. Khi cần thêm mã lịch, phiên bản hay phạm vi hiệu lực, có thể tạo một giao diện nghiệp vụ riêng; không cần đưa việc tải dữ liệu vào vòng lặp tính ngày.

| Thành phần | Chịu trách nhiệm |
| --- | --- |
| `LocalDate` và `plusDays` | Bước qua lịch ISO, gồm ranh giới tháng, năm và năm nhuận |
| Chính sách ngày làm việc | Phân loại một ngày cụ thể là làm hay nghỉ |
| Thuật toán cộng hoặc đếm | Quy ước khoảng, hướng di chuyển, số ngày được chấp nhận |
| Nơi tải lịch | Chọn lịch của đơn vị, kiểm tra dữ liệu và cung cấp ảnh chụp ổn định |

Nhờ sự tách biệt này, sửa ngày nghỉ không buộc sửa thuật toán. Cùng thuật toán có thể phục vụ hai đơn vị có lịch cuối tuần khác nhau.

## 3. Chốt quy ước đầu mút và ngày bắt đầu

Sai lệch một ngày thường xuất phát từ hợp đồng chưa rõ, dù vòng lặp không có lỗi cú pháp.

### 3.1. Đếm trong khoảng nửa mở

Trong bài, `countBusinessDays(fromInclusive, toExclusive, policy)` đếm các ngày trong khoảng **[fromInclusive, toExclusive)**:

- Bao gồm ngày đầu nếu chính sách xác định đó là ngày làm việc.
- Không bao gồm ngày cuối.
- Hai đầu bằng nhau cho kết quả `0`.
- Ngày cuối trước ngày đầu là đầu vào không hợp lệ; không tự đảo hai đầu.

Ví dụ `[2024-04-05, 2024-04-10)` gồm các ngày 05, 06, 07, 08 và 09/04. Nếu chỉ nghỉ thứ Bảy, Chủ nhật thì có ba ngày làm việc: 05, 08 và 09. Nếu 08/04 cũng nghỉ thì còn hai.

`LocalDate.datesUntil(endExclusive)` thích hợp với hợp đồng này: sinh từng ngày từ ngày hiện tại và không lấy ngày kết thúc. Không cần tự cộng thêm một ngày vào đầu mút. Cách đổi khoảng đóng thành `endInclusive.plusDays(1)` có thể vượt miền biểu diễn nếu đầu cuối là `LocalDate.MAX`; cần xét riêng nếu giao diện nghiệp vụ chọn khoảng đóng.

### 3.2. Cộng số ngày làm việc

Trong bài, `addBusinessDays(start, amount, policy, maxCalendarSteps)` có hợp đồng:

- `amount > 0`: đi về tương lai và đếm ngày làm việc sau `start`.
- `amount < 0`: đi về quá khứ và đếm ngày làm việc trước `start`.
- **Không tính chính ngày bắt đầu**, dù ngày đó làm hay nghỉ.
- `amount == 0`: trả nguyên `start`, kể cả khi đó là ngày nghỉ.
- `maxCalendarSteps` phải dương; đây là giới hạn số ngày theo lịch được phép duyệt, không phải giới hạn số ngày làm việc.

Ví dụ bắt đầu vào Chủ nhật 07/04, cộng `0` vẫn là 07/04; cộng `1` theo lịch nghỉ cuối tuần thông thường là thứ Hai 08/04. Nếu muốn “cộng 0 nhưng tự dời sang ngày làm việc”, hãy định nghĩa một phép điều chỉnh riêng, tránh ngầm thay đổi ý nghĩa của phép cộng.

Cũng không nên giả định phép cộng luôn có phép nghịch đảo khi điểm bắt đầu là ngày nghỉ. Theo hợp đồng trên, Chủ nhật 07/04 cộng một ngày làm việc thành thứ Hai 08/04; từ thứ Hai trừ một ngày làm việc thành thứ Sáu 05/04, không trở lại Chủ nhật.

## 4. Chính sách mẫu: nghỉ tuần, nghỉ cụ thể và làm bù

Ta chọn thứ tự ưu tiên minh bạch:

1. Có trong tập ngày làm bù thì là ngày làm việc.
2. Nếu không, có trong tập ngày nghỉ cụ thể thì là ngày nghỉ.
3. Nếu không, xét ngày nghỉ hằng tuần.

Ngày làm bù trong ví dụ được ưu tiên kể cả khi trùng một ngày nghỉ cụ thể. Đây là lựa chọn của chính sách mẫu. Một hệ thống khác có thể cấm hai tập trùng nhau hoặc ưu tiên ngày nghỉ; khi đó cần sửa chính sách và kiểm tra dữ liệu, không sửa vòng lặp.

Dữ liệu dùng `Set` để một ngày nghỉ bị nhập lặp không làm tăng số lần loại ngày đó. `Set.copyOf` tạo bản sao không cho sửa qua tham chiếu đã lưu, giúp kết quả không thay đổi giữa chừng do bên ngoài thêm hoặc xóa ngày nghỉ. Bản thân `LocalDate` là bất biến.

Không tính “số ngày thường trừ số ngày nghỉ trong danh sách” một cách máy móc: ngày nghỉ có thể nằm ngoài khoảng, rơi đúng cuối tuần, bị trùng hoặc được một ngoại lệ làm bù ghi đè. Phân loại từng ngày theo một hàm duy nhất tránh đếm trừ hai lần.

## 5. Chương trình Java 17+ đầy đủ

Lưu mã sau thành `BusinessDaysDemo.java`. Chương trình chỉ dùng thư viện chuẩn và mọi ngày đều được tạo rõ ràng, không phụ thuộc ngày hiện tại của máy.

```java
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.temporal.TemporalAdjuster;
import java.time.temporal.TemporalAdjusters;
import java.util.Objects;
import java.util.Set;
import java.util.function.Predicate;

public class BusinessDaysDemo {
    record BusinessCalendar(
            Set<DayOfWeek> weekend,
            Set<LocalDate> holidays,
            Set<LocalDate> workingOverrides) {

        BusinessCalendar {
            weekend = Set.copyOf(Objects.requireNonNull(weekend));
            holidays = Set.copyOf(Objects.requireNonNull(holidays));
            workingOverrides =
                    Set.copyOf(Objects.requireNonNull(workingOverrides));
        }

        boolean isBusinessDay(LocalDate date) {
            Objects.requireNonNull(date);
            if (workingOverrides.contains(date)) {
                return true;
            }
            return !holidays.contains(date)
                    && !weekend.contains(date.getDayOfWeek());
        }
    }

    static long countBusinessDays(
            LocalDate fromInclusive,
            LocalDate toExclusive,
            Predicate<LocalDate> policy) {

        Objects.requireNonNull(fromInclusive);
        Objects.requireNonNull(toExclusive);
        Objects.requireNonNull(policy);
        if (toExclusive.isBefore(fromInclusive)) {
            throw new IllegalArgumentException("Reversed interval");
        }

        return fromInclusive.datesUntil(toExclusive)
                .filter(policy)
                .count();
    }

    static LocalDate addBusinessDays(
            LocalDate start,
            int amount,
            Predicate<LocalDate> policy,
            int maxCalendarSteps) {

        Objects.requireNonNull(start);
        Objects.requireNonNull(policy);
        if (maxCalendarSteps <= 0) {
            throw new IllegalArgumentException("Limit must be positive");
        }
        if (amount == 0) {
            return start;
        }

        int direction = amount > 0 ? 1 : -1;
        long remaining = Math.abs((long) amount);
        LocalDate cursor = start;

        for (int steps = 0; steps < maxCalendarSteps; steps++) {
            cursor = cursor.plusDays(direction);
            if (policy.test(cursor)) {
                remaining--;
                if (remaining == 0) {
                    return cursor;
                }
            }
        }
        throw new IllegalStateException("Calendar search limit exceeded");
    }

    static LocalDate nextBusinessDayOrSame(
            LocalDate start,
            Predicate<LocalDate> policy,
            int maxCalendarSteps) {

        Objects.requireNonNull(start);
        Objects.requireNonNull(policy);
        if (maxCalendarSteps <= 0) {
            throw new IllegalArgumentException("Limit must be positive");
        }
        if (policy.test(start)) {
            return start;
        }
        return addBusinessDays(start, 1, policy, maxCalendarSteps);
    }

    public static void main(String[] args) {
        LocalDate friday = LocalDate.of(2024, 4, 5);
        LocalDate monday = LocalDate.of(2024, 4, 8);
        LocalDate wednesday = LocalDate.of(2024, 4, 10);

        BusinessCalendar normal = new BusinessCalendar(
                Set.of(DayOfWeek.SATURDAY, DayOfWeek.SUNDAY),
                Set.of(),
                Set.of());

        BusinessCalendar holiday = new BusinessCalendar(
                normal.weekend(),
                Set.of(monday),
                Set.of());

        BusinessCalendar makeUp = new BusinessCalendar(
                normal.weekend(),
                Set.of(monday),
                Set.of(LocalDate.of(2024, 4, 6)));

        System.out.println("calendar +1 = " + friday.plusDays(1));
        System.out.println("normal +1 = " + addBusinessDays(
                friday, 1, normal::isBusinessDay, 30));
        System.out.println("holiday +1 = " + addBusinessDays(
                friday, 1, holiday::isBusinessDay, 30));
        System.out.println("make-up +1 = " + addBusinessDays(
                friday, 1, makeUp::isBusinessDay, 30));

        System.out.println("normal count = " + countBusinessDays(
                friday, wednesday, normal::isBusinessDay));
        System.out.println("holiday count = " + countBusinessDays(
                friday, wednesday, holiday::isBusinessDay));
        System.out.println("make-up count = " + countBusinessDays(
                friday, wednesday, makeUp::isBusinessDay));

        System.out.println("holiday -1 = " + addBusinessDays(
                LocalDate.of(2024, 4, 9), -1,
                holiday::isBusinessDay, 30));

        LocalDate sunday = LocalDate.of(2024, 4, 7);
        System.out.println("zero = " + addBusinessDays(
                sunday, 0, holiday::isBusinessDay, 30));

        TemporalAdjuster following = TemporalAdjusters.ofDateAdjuster(
                date -> nextBusinessDayOrSame(
                        date, holiday::isBusinessDay, 30));
        System.out.println("following = " + sunday.with(following));

        System.out.println("empty count = " + countBusinessDays(
                friday, friday, normal::isBusinessDay));

        try {
            addBusinessDays(friday, 1, date -> false, 10);
        } catch (IllegalStateException ex) {
            System.out.println("closed calendar = " + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```shell
javac --release 17 BusinessDaysDemo.java
java BusinessDaysDemo
```

Kết quả:

```text
calendar +1 = 2024-04-06
normal +1 = 2024-04-08
holiday +1 = 2024-04-09
make-up +1 = 2024-04-06
normal count = 3
holiday count = 2
make-up count = 3
holiday -1 = 2024-04-05
zero = 2024-04-07
following = 2024-04-09
empty count = 0
closed calendar = Calendar search limit exceeded
```

### 5.1. Theo dõi phép cộng một ngày làm việc

Với `holiday` và ngày đầu là 05/04:

| Lần duyệt | Ngày được xét | Quyết định | Số ngày làm việc còn thiếu |
| --- | --- | --- | --- |
| 1 | 06/04, thứ Bảy | Nghỉ tuần, bỏ qua | 1 |
| 2 | 07/04, Chủ nhật | Nghỉ tuần, bỏ qua | 1 |
| 3 | 08/04, thứ Hai | Ngày nghỉ cụ thể, bỏ qua | 1 |
| 4 | 09/04, thứ Ba | Chấp nhận | 0 |

Điểm quyết định là `remaining` chỉ giảm khi `policy.test(cursor)` trả `true`. `cursor` vẫn tiến một ngày ở mọi vòng. Nếu chỉ tăng ngày khi gặp ngày làm việc, thuật toán sẽ mắc kẹt ở ngày nghỉ đầu tiên.

Với `makeUp`, ngày 06/04 được chấp nhận ngay vì có trong `workingOverrides`. Thuật toán cộng không có nhánh “thứ Bảy làm bù”; nó chỉ nhận kết quả từ chính sách.

### 5.2. Đi lùi và tránh tràn số nguyên

Khi `amount` âm, `direction` bằng `-1` nên `plusDays(-1)` duyệt lùi từng ngày. Từ thứ Ba 09/04 theo `holiday`: thứ Hai nghỉ, cuối tuần nghỉ, ngày được chấp nhận đầu tiên là thứ Sáu 05/04.

`Math.abs((long) amount)` chuyển sang `long` **trước khi** lấy trị tuyệt đối. `Math.abs(Integer.MIN_VALUE)` trên kiểu `int` vẫn âm vì trị tuyệt đối vượt miền số dương của `int`. Việc đổi kiểu ngăn lỗi đó; giới hạn duyệt vẫn có thể từ chối một yêu cầu quá lớn.

`LocalDate` cũng có biên. Đi tiếp sau `LocalDate.MAX` hoặc lùi trước `LocalDate.MIN` sẽ thất bại thay vì quấn vòng. Chương trình không bắt rồi đổi các lỗi vượt miền thành một ngày hợp lệ giả.

### 5.3. Giới hạn duyệt bảo vệ điều gì?

Một chính sách có thể trả `false` cho mọi ngày. Vòng `while (remaining > 0)` không có giới hạn sẽ không tìm được kết quả và có thể tiếp tục đến biên lịch.

`maxCalendarSteps` làm yêu cầu có giới hạn tài nguyên rõ ràng. Nếu đạt giới hạn, phương thức ném lỗi, không trả ngày cuối đã xét như thể đó là kết quả thành công. Việc vượt giới hạn không chứng minh lịch không bao giờ có ngày làm việc; nó chỉ cho biết không tìm được đủ ngày trong phạm vi đã cho.

Giá trị `30` trong ví dụ là cấu hình minh họa cho các yêu cầu rất nhỏ, không phải công thức tổng quát `amount * một hệ số`. Với lịch đóng cửa dài ngày, cần cấu hình giới hạn phù hợp hoặc dùng khoảng lịch có phạm vi được xác thực.

## 6. Điều chỉnh ngày đến hạn khác với cộng ngày làm việc

Có ba câu hỏi dễ bị trộn:

| Yêu cầu | Hành vi khi ngày đầu đã là ngày làm việc |
| --- | --- |
| Ngày làm việc kế tiếp | Luôn đi tiếp, không trả ngày đầu |
| Ngày làm việc kế tiếp hoặc chính ngày đó | Giữ nguyên ngày đầu |
| Cộng `n` ngày làm việc | Theo hợp đồng đếm; bài này loại ngày đầu, `n = 0` giữ nguyên |

`nextBusinessDayOrSame` trong chương trình phục vụ câu hỏi thứ hai. Khi ngày đầu đã hợp lệ, nó trả ngay; nếu chưa hợp lệ, nó dùng phép cộng một ngày làm việc để tìm về phía trước.

[TemporalAdjusters.ofDateAdjuster](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalAdjusters.html#ofDateAdjuster(java.util.function.UnaryOperator)) bọc hàm điều chỉnh `LocalDate` thành `TemporalAdjuster` để gọi bằng `date.with(adjuster)`. Nó không bổ sung cơ sở dữ liệu ngày nghỉ; logic nghiệp vụ vẫn do hàm được truyền vào quyết định.

`TemporalAdjusters.next(DayOfWeek.MONDAY)` tìm thứ Hai tiếp theo, nhưng thứ Hai đó có thể nghỉ theo chính sách. Tìm đúng thứ trong tuần và tìm ngày làm việc là hai phép điều chỉnh có ý nghĩa riêng.

Trong nghiệp vụ tài chính, đôi khi cần quy tắc “dời tới ngày làm việc tiếp theo nhưng nếu sang tháng mới thì dời lùi”. Đó là một hợp đồng khác, cần mô tả và kiểm chứng riêng; không nên đặt tên chung chung `fixDate` rồi âm thầm áp dụng cho mọi hạn thanh toán.

## 7. Dữ liệu lịch phải có nghĩa và có phạm vi

### 7.1. Ngày nghỉ là dữ liệu, không phải hằng số của thuật toán

Một lịch thực tế thường cần biết mã lịch/đơn vị, vùng áp dụng, năm hoặc khoảng ngày được bao phủ, nguồn dữ liệu và phiên bản. Hai đơn vị cùng đặt ở một quốc gia vẫn có thể có lịch vận hành khác nhau.

Lịch giả định trong chương trình được coi là đầy đủ cho những ngày đang xét. `Set.of()` nghĩa là “không có ngày nghỉ thêm theo cấu hình mẫu”, không chứng minh rằng một năm thực tế không có ngày lễ.

Nếu chỉ tải dữ liệu năm 2024 rồi tính kết quả sang 2025, tập ngày nghỉ không có 2025 là **thiếu thông tin**, không nhất thiết là ngày đó làm việc. Có thể bọc chính sách bằng kiểm tra khoảng hiệu lực và từ chối mọi ngày ngoài khoảng. Với phép đếm, xác thực toàn bộ khoảng yêu cầu trước khi duyệt; với phép cộng, xác thực từng ngày hoặc giới hạn tìm kiếm trong khoảng đã biết. Thiếu dữ liệu cần được báo rõ, không tự suy đoán ngày nghỉ.

Ngày nghỉ quan sát, nghỉ bù hoặc chuyển ngày nghỉ là nội dung của lịch được cung cấp. Không tự quy định “ngày lễ rơi vào Chủ nhật thì thứ Hai nghỉ” nếu chưa có chính sách yêu cầu.

### 7.2. Duy trì ảnh chụp nhất quán

Nên tải và kiểm tra lịch trước, sau đó tính trên một ảnh chụp bất biến. Nếu mỗi lần gọi `isBusinessDay` lại gọi một API từ xa, phép cộng có thể chậm, gặp lỗi mạng giữa chừng hoặc dùng hai phiên bản lịch trong cùng một phép tính.

Để giải thích lại kết quả về sau, có thể lưu ngày đầu, lượng cộng, mã lịch, phiên bản lịch và quy ước đầu mút. Nếu bộ nhớ đệm chỉ dùng ngày và số lượng làm khóa, hai chi nhánh có lịch khác nhau có thể nhận nhầm cùng kết quả. Khóa phải phản ánh cả chính sách và phiên bản tương ứng.

Trong ví dụ, `BusinessCalendar` dùng tập bất biến và không có trạng thái thay đổi trong lúc tính. Nếu truyền một `Predicate` khác có trạng thái hoặc kết quả ngẫu nhiên, thuật toán không thể tự bảo đảm tính nhất quán; hợp đồng của chính sách cần yêu cầu cùng một ngày, cùng ảnh chụp lịch thì cho cùng một câu trả lời.

### 7.3. Từ thời điểm sang ngày phải chọn múi giờ nghiệp vụ

Bản thân phép cộng ngày không cần múi giờ. Tuy nhiên, nếu đầu vào là `Instant`, phải chọn múi giờ của đơn vị trước khi lấy `LocalDate`; gần nửa đêm, cùng một thời điểm có thể thuộc hai ngày khác nhau ở hai múi giờ.

Lịch làm việc theo ngày cũng chưa đủ để quyết định thời hạn có mốc chốt giờ nhận yêu cầu. Ví dụ yêu cầu nhận sau 17 giờ được tính từ ngày hôm sau là một bước nghiệp vụ riêng cần `LocalTime` hoặc kiểu ngày giờ thích hợp.

Không đổi một ngày làm việc thành `24` giờ để cộng vào `Instant`: số giờ trên dòng thời gian và số ngày nghiệp vụ là hai đại lượng khác nhau. Bài này chỉ đếm ngày được chính sách chấp nhận.

## 8. Độ phức tạp và thời điểm cần tối ưu

`countBusinessDays` duyệt `D` ngày trong khoảng nên có `D` lần gọi chính sách. `addBusinessDays` duyệt `K` ngày theo lịch cho đến khi đủ số ngày làm việc, tối đa giới hạn được cấu hình. Nếu phép phân loại ngày có chi phí hằng số trung bình thì thời gian tương ứng là `O(D)` và `O(K)`; thao tác thành viên của tập băm thường phù hợp cho nhu cầu này.

Cách duyệt từng ngày dễ giải thích và kiểm chứng, thường đủ cho hạn xử lý vài ngày hoặc vài tháng. Nó không tạo toàn bộ danh sách ngày trong bộ nhớ; luồng `datesUntil` được tiêu thụ để đếm. Dữ liệu ngày nghỉ vẫn chiếm bộ nhớ theo kích thước tập cấu hình.

Công thức “mỗi tuần có năm ngày làm việc” chỉ áp dụng khi lịch thỏa giả thiết đó. Ngày nghỉ bổ sung và ngày làm bù phá vỡ bước nhảy đơn giản. Nếu thực sự cần xử lý khối lượng lớn trên một khoảng xác định, có thể tiền tính cờ làm/nghỉ và tổng tích lũy theo ngày; đổi lại phải quản lý miền dữ liệu và xây lại chỉ mục khi phiên bản lịch đổi.

Không tối ưu bằng cách rải lại quy tắc nghỉ trong nhiều thuật toán. Dù dùng vòng lặp hay chỉ mục, hãy giữ một định nghĩa chính sách thống nhất để tránh kết quả đếm và kết quả cộng mâu thuẫn nhau.

## 9. Các lỗi thường gặp và cách nhận diện

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Dùng `plusDays(n)` để cộng ngày làm việc | Tính cả cuối tuần và ngày nghỉ | Duyệt ngày và hỏi chính sách |
| Cố định nghỉ thứ Bảy, Chủ nhật trong nhiều hàm | Khó đổi lịch cho đơn vị khác | Truyền một chính sách chung |
| Trừ mọi ngày nghỉ khỏi số ngày trong tuần | Trừ lặp ngày cuối tuần, trừ cả ngày ngoài khoảng | Phân loại từng ngày hoặc lọc tập đúng hợp đồng |
| Đếm cả hai đầu nhưng đặt tên `endExclusive` | Lệch một ngày | Ghi rõ khoảng và dùng nhất quán |
| Tự dời ngày nghỉ khi cộng `0` | Hành vi khác hợp đồng mà nơi gọi không biết | Tách phép điều chỉnh ngày |
| Bỏ qua ngày làm bù | Kết quả muộn hơn chính sách | Quy định thứ tự ưu tiên ngoại lệ |
| Cho rằng danh sách nghỉ trống luôn là lịch hợp lệ | Biến dữ liệu thiếu thành ngày làm việc | Kiểm tra phạm vi và trạng thái tải lịch |
| Không giới hạn tìm kiếm | Tốn tài nguyên với lịch không có ngày làm | Giới hạn duyệt hoặc khoảng hiệu lực |
| Bỏ giá trị trả về của `plusDays` | Con trỏ không thay đổi vì `LocalDate` bất biến | Gán lại `cursor = cursor.plusDays(...)` |
| Chia số giờ đã trôi qua cho `24` | Nhầm thời lượng với ngày nghiệp vụ | Tính theo `LocalDate` và chính sách |

## 10. Tự kiểm chứng và luyện tập

Các trường hợp kiểm chứng cần thay đổi ý nghĩa đầu vào, không chỉ đổi số ngày:

1. **Hai đầu bằng nhau:** số ngày làm việc bằng `0`, dù ngày đó làm hay nghỉ.
2. **Cuối tuần:** từ 05/04/2024, lịch thường cộng một ngày ra 08/04.
3. **Nghỉ thứ Hai:** cùng đầu vào, lịch `holiday` ra 09/04.
4. **Làm bù thứ Bảy:** cùng đầu vào, lịch `makeUp` ra 06/04.
5. **Ngày nghỉ trùng cuối tuần:** thêm 06/04 vào tập ngày nghỉ của lịch thường; kết quả không bị trừ thêm lần nữa.
6. **Số âm và số không:** trừ một ngày từ 09/04 theo `holiday` ra 05/04; cộng `0` từ Chủ nhật giữ nguyên Chủ nhật.
7. **Đổi tháng và năm nhuận:** dùng lịch chỉ nghỉ cuối tuần; từ 28/02/2024 cộng một ngày làm việc ra 29/02, từ 29/02 cộng một ngày ra 01/03.
8. **Đổi năm:** với lịch chỉ nghỉ cuối tuần và không có ngày nghỉ bổ sung, từ 31/12/2024 cộng một ngày làm việc ra 01/01/2025. Đây chỉ kiểm tra thuật toán trên lịch giả định, không khẳng định 01/01 là ngày làm việc thực tế.
9. **Chính sách từ chối mọi ngày:** yêu cầu phải kết thúc bằng lỗi giới hạn, không treo và không trả ngày sai.
10. **Khoảng đảo ngược hoặc vượt miền lịch:** đầu vào không hợp lệ phải thất bại rõ ràng.

Bài tập:

- Tạo một lịch nghỉ thứ Sáu và thứ Bảy, giữ nguyên các thuật toán. Kiểm tra rằng Chủ nhật có thể được chấp nhận.
- Viết `previousBusinessDayOrSame` với hợp đồng tương tự phép tìm về phía trước; kiểm tra ngày đầu đang nghỉ và đang làm.
- Thêm lớp bọc giới hạn lịch vào `[validFrom, validToExclusive)`, rồi yêu cầu tính vượt năm dữ liệu đã tải. Hệ thống phải báo thiếu lịch thay vì trả kết quả dựa trên tập ngày nghỉ chưa đầy đủ.
- Giải thích vì sao hai phép tính dùng cùng ngày đầu và số lượng vẫn có thể khác kết quả khi mã lịch hoặc phiên bản lịch khác nhau.

Năng lực cần đạt là diễn đạt rõ “ngày nào được chấp nhận” và “các ngày được duyệt, đếm như thế nào”. Khi hai phần đó có hợp đồng riêng, việc thay đổi ngày nghỉ trở thành thay đổi chính sách có thể kiểm chứng, còn phép tính lịch vẫn nhất quán.
