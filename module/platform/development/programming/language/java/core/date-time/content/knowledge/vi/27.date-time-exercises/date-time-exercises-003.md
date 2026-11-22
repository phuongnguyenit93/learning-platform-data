# Tính ngày làm việc kế tiếp theo chính sách ngày nghỉ

## 1. Bài toán thực hành

Một bộ phận xử lý yêu cầu cần trả lời:

> Sau ngày tiếp nhận, ngày làm việc gần nhất là ngày nào theo lịch hoạt động của bộ phận?

Không thể chỉ gọi `plusDays(1)` rồi mặc định đã có đáp án. Ngày tiếp theo có thể là ngày nghỉ tuần, ngày đóng cửa đặc biệt hoặc ngược lại là ngày mở cửa bổ sung.

Trong bài thực hành này, ta xây một lời giải có:

- Đầu vào và quy ước ngày bắt đầu rõ ràng.
- Một đối tượng mô tả chính sách ngày nghỉ.
- Thuật toán tìm ngày gần nhất.
- Phạm vi dữ liệu lịch hữu hạn.
- Chương trình Java 17+ chạy được với kết quả có thể đối chiếu.

**Mọi ngày đóng cửa và mở cửa đặc biệt trong bài là dữ liệu giả định.** Chúng không đại diện cho lịch nghỉ lễ thực tế của một quốc gia hay doanh nghiệp.

Mục tiêu không phải ghi nhớ một danh sách ngày nghỉ, mà là biến chính sách thành dữ liệu và bảo đảm thuật toán tôn trọng chính sách đó.

## 2. Viết hợp đồng trước khi viết vòng lặp

Tên `nextWorkingDayAfter` được chọn với nghĩa chặt:

1. Không xét chính ngày đầu vào.
2. Bắt đầu kiểm tra từ ngày kế tiếp trên lịch.
3. Trả ngày làm việc đầu tiên tìm được.
4. Nếu không có kết quả trong phạm vi lịch đã được cung cấp, báo lỗi.
5. Không tự tạo ngày nghỉ, tự tải lịch năm khác hoặc đoán trạng thái ngoài phạm vi.

Ví dụ nếu thứ Sáu là ngày làm việc:

| Yêu cầu | Kết quả có thể là thứ Sáu đầu vào không? |
| --- | --- |
| “Ngày làm việc sau thứ Sáu” | Không |
| “Ngày làm việc từ thứ Sáu trở đi, gồm hôm đó” | Có |

Ta cung cấp một hàm riêng `workingDayOnOrAfter` cho hợp đồng thứ hai. Việc tách tên giúp nơi gọi không phải đoán một biến `includeStart` truyền ở mỗi chỗ có nghĩa gì.

`LocalDate` phù hợp vì bài toán xử lý đơn vị ngày. Theo [LocalDate](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html), kiểu này không chứa giờ hoặc múi giờ và các phép tính trả đối tượng mới. Nếu đầu vào của ứng dụng là một `Instant`, cần xác định ngày tiếp nhận theo vùng nghiệp vụ trước khi gọi thuật toán này.

## 3. Chuẩn bị dữ liệu lịch

Chính sách mẫu có năm thành phần:

| Thành phần | Ý nghĩa |
| --- | --- |
| `validFromInclusive` | Ngày đầu có dữ liệu lịch |
| `validToExclusive` | Ngày kết thúc bị loại khỏi phạm vi lịch |
| `weeklyDaysOff` | Những thứ nghỉ lặp lại hằng tuần |
| `closedDates` | Các ngày đóng cửa bổ sung |
| `extraOpenDates` | Các ngày mở cửa đặc biệt |

Phạm vi lịch là khoảng nửa mở `[validFromInclusive, validToExclusive)`. Ví dụ `[2024-01-01, 2025-01-01)` có dữ liệu cho mọi ngày của năm 2024, không bao gồm 01/01/2025.

### 3.1. Quy tắc phân loại một ngày

Chính sách trong bài chọn:

1. Ngày phải nằm trong phạm vi đã biết.
2. Nếu thuộc `extraOpenDates` thì làm việc, kể cả rơi vào ngày nghỉ tuần.
3. Nếu thuộc `closedDates` thì nghỉ.
4. Nếu không có ngoại lệ, xét `weeklyDaysOff`.

Một ngày không được đồng thời nằm trong `closedDates` và `extraOpenDates`. Constructor sẽ từ chối dữ liệu xung đột thay vì chọn ưu tiên ngầm giữa hai ngoại lệ.

Đây là hợp đồng mẫu. Một nghiệp vụ khác có thể cho phép xung đột và chọn một bên ưu tiên, nhưng khi đó phải ghi rõ và kiểm chứng chính sách khác. Vòng lặp tìm ngày không nên tự chứa các quyết định đó.

### 3.2. Dùng DayOfWeek thay vì các số khó nhớ

[DayOfWeek](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/DayOfWeek.html) biểu diễn thứ trong tuần bằng enum. Tập:

```java
Set.of(DayOfWeek.SATURDAY, DayOfWeek.SUNDAY)
```

thể hiện ý định rõ hơn một cặp số. Nếu cần lịch nghỉ thứ Sáu–thứ Bảy, chỉ thay tập cấu hình, không sửa thuật toán.

Ngày nghỉ tuần không được suy ra từ ngôn ngữ giao diện. Người dùng đọc tiếng Việt vẫn có thể làm việc với một đơn vị có ngày nghỉ tuần khác thứ Bảy và Chủ nhật.

### 3.3. Cố định ảnh chụp lịch trong một phép tính

[Set.copyOf](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)) tạo tập không cho thay đổi qua tham chiếu được giữ. Các phần tử `LocalDate` và `DayOfWeek` trong bài cũng là giá trị bất biến.

Nhờ vậy, nếu bên ngoài sửa tập đầu vào sau khi tạo lịch, ảnh chụp của chính sách không bị thay đổi theo. Thuật toán không gặp trường hợp ngày 16 vừa bị coi là nghỉ ở một vòng rồi bất ngờ đổi thành làm việc trong cùng lượt tính.

Constructor còn kiểm tra các ngày ngoại lệ thuộc phạm vi lịch. Một ngoại lệ của năm khác bị đưa nhầm vào dữ liệu năm 2024 phải được phát hiện sớm.

## 4. Thuật toán tìm ngày gần nhất

Thuật toán có thể diễn đạt bằng các bước:

1. Kiểm tra ngày bắt đầu có trong phạm vi lịch.
2. Đặt ứng viên bằng ngày bắt đầu cộng một ngày.
3. Trong khi ứng viên chưa tới mốc kết thúc loại trừ:
   - Hỏi chính sách ứng viên có làm việc không.
   - Nếu có, trả ngay ứng viên.
   - Nếu không, chuyển sang ngày lịch tiếp theo.
4. Nếu đã hết phạm vi mà chưa tìm được, báo không có kết quả trong phần lịch đã biết.

Lý do kết quả là **gần nhất**: các ngày được xét tăng dần từng ngày và trả ngay ngày đầu được chấp nhận. Không ngày nào nằm giữa ngày đầu và kết quả bị bỏ qua.

Nếu chỉ chuyển ứng viên khi gặp ngày làm việc, vòng lặp sẽ kẹt tại ngày nghỉ. Con trỏ phải tiến sau mọi lần không tìm được kết quả.

Không dùng một bước nhảy cố định “thứ Sáu thì cộng ba ngày” vì thứ Hai có thể đóng cửa, hoặc thứ Bảy lại được mở đặc biệt. Chính sách có đầy đủ câu trả lời cho từng ngày; thuật toán nên hỏi chính sách một cách thống nhất.

## 5. Chương trình Java 17+ đầy đủ

Lưu thành `NextWorkingDayPractice.java`:

```java
import java.time.DateTimeException;
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.util.Collections;
import java.util.EnumSet;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class NextWorkingDayPractice {
    record WorkCalendar(
            LocalDate validFromInclusive,
            LocalDate validToExclusive,
            Set<DayOfWeek> weeklyDaysOff,
            Set<LocalDate> closedDates,
            Set<LocalDate> extraOpenDates) {

        WorkCalendar {
            Objects.requireNonNull(validFromInclusive);
            Objects.requireNonNull(validToExclusive);
            if (!validFromInclusive.isBefore(validToExclusive)) {
                throw new IllegalArgumentException("Empty calendar coverage");
            }
            weeklyDaysOff = Set.copyOf(weeklyDaysOff);
            closedDates = Set.copyOf(closedDates);
            extraOpenDates = Set.copyOf(extraOpenDates);
            if (!Collections.disjoint(closedDates, extraOpenDates)) {
                throw new IllegalArgumentException("Conflicting date overrides");
            }
            Set<LocalDate> exceptions = new HashSet<>(closedDates);
            exceptions.addAll(extraOpenDates);
            for (LocalDate date : exceptions) {
                if (date.isBefore(validFromInclusive)
                        || !date.isBefore(validToExclusive)) {
                    throw new IllegalArgumentException(
                            "Override outside calendar coverage");
                }
            }
        }

        boolean covers(LocalDate date) {
            Objects.requireNonNull(date);
            return !date.isBefore(validFromInclusive)
                    && date.isBefore(validToExclusive);
        }

        boolean isWorkingDate(LocalDate date) {
            if (!covers(date)) {
                throw new DateTimeException("Date outside calendar coverage");
            }
            if (extraOpenDates.contains(date)) {
                return true;
            }
            if (closedDates.contains(date)) {
                return false;
            }
            return !weeklyDaysOff.contains(date.getDayOfWeek());
        }
    }

    static LocalDate nextWorkingDayAfter(
            LocalDate startExclusive, WorkCalendar calendar) {
        Objects.requireNonNull(startExclusive);
        Objects.requireNonNull(calendar);
        if (!calendar.covers(startExclusive)) {
            throw new DateTimeException("Start outside calendar coverage");
        }

        for (LocalDate candidate = startExclusive.plusDays(1);
                candidate.isBefore(calendar.validToExclusive());
                candidate = candidate.plusDays(1)) {
            if (calendar.isWorkingDate(candidate)) {
                return candidate;
            }
        }
        throw new DateTimeException("No working day in covered range");
    }

    static LocalDate workingDayOnOrAfter(
            LocalDate startInclusive, WorkCalendar calendar) {
        Objects.requireNonNull(calendar);
        if (calendar.isWorkingDate(startInclusive)) {
            return startInclusive;
        }
        return nextWorkingDayAfter(startInclusive, calendar);
    }

    public static void main(String[] args) {
        LocalDate from = LocalDate.of(2024, 1, 1);
        LocalDate until = LocalDate.of(2025, 1, 1);
        Set<DayOfWeek> weekend =
                Set.of(DayOfWeek.SATURDAY, DayOfWeek.SUNDAY);

        WorkCalendar normal = new WorkCalendar(
                from, until, weekend, Set.of(), Set.of());
        WorkCalendar closure = new WorkCalendar(
                from, until, weekend,
                Set.of(LocalDate.of(2024, 9, 16),
                       LocalDate.of(2024, 9, 17)),
                Set.of());
        WorkCalendar extraOpen = new WorkCalendar(
                from, until, weekend, closure.closedDates(),
                Set.of(LocalDate.of(2024, 9, 14)));

        LocalDate friday = LocalDate.of(2024, 9, 13);
        System.out.println("normal after Friday = "
                + nextWorkingDayAfter(friday, normal));
        System.out.println("closure after Friday = "
                + nextWorkingDayAfter(friday, closure));
        System.out.println("extra-open after Friday = "
                + nextWorkingDayAfter(friday, extraOpen));
        System.out.println("on-or-after Friday = "
                + workingDayOnOrAfter(friday, closure));
        System.out.println("closure after Sunday = "
                + nextWorkingDayAfter(LocalDate.of(2024, 9, 15), closure));
        System.out.println("leap day = " + nextWorkingDayAfter(
                LocalDate.of(2024, 2, 28), normal));

        WorkCalendar fridaySaturdayOff = new WorkCalendar(
                from, until,
                Set.of(DayOfWeek.FRIDAY, DayOfWeek.SATURDAY),
                Set.of(), Set.of());
        System.out.println("different weekend = "
                + nextWorkingDayAfter(friday, fridaySaturdayOff));

        WorkCalendar closedEveryDay = new WorkCalendar(
                from, until, EnumSet.allOf(DayOfWeek.class),
                Set.of(), Set.of());
        try {
            nextWorkingDayAfter(LocalDate.of(2024, 12, 29), closedEveryDay);
        } catch (DateTimeException ex) {
            System.out.println("no result = " + ex.getMessage());
        }

        try {
            nextWorkingDayAfter(LocalDate.of(2024, 12, 31), normal);
        } catch (DateTimeException ex) {
            System.out.println("coverage limit = " + ex.getMessage());
        }

        try {
            new WorkCalendar(from, until, weekend,
                    Set.of(friday), Set.of(friday));
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid policy = " + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 NextWorkingDayPractice.java
java NextWorkingDayPractice
```

Stdout:

```text
normal after Friday = 2024-09-16
closure after Friday = 2024-09-18
extra-open after Friday = 2024-09-14
on-or-after Friday = 2024-09-13
closure after Sunday = 2024-09-18
leap day = 2024-02-29
different weekend = 2024-09-15
no result = No working day in covered range
coverage limit = No working day in covered range
invalid policy = Conflicting date overrides
```

Chương trình chỉ sử dụng thư viện chuẩn. Không cần cơ sở dữ liệu, mạng hoặc ngày hiện tại của máy.

## 6. Đọc kết quả theo từng tình huống

### 6.1. Nghỉ tuần thông thường

Ngày bắt đầu là thứ Sáu 13/09/2024. Lịch `normal` nghỉ thứ Bảy và Chủ nhật, không có ngoại lệ:

| Ứng viên | Kết luận |
| --- | --- |
| 14/09, thứ Bảy | Nghỉ tuần |
| 15/09, Chủ nhật | Nghỉ tuần |
| 16/09, thứ Hai | Ngày làm việc đầu tiên |

Kết quả là 16/09.

### 6.2. Có hai ngày đóng cửa sau cuối tuần

Lịch `closure` bổ sung ngày đóng cửa 16/09 và 17/09. Hai ngày cuối tuần vẫn nghỉ; hai ngày sau đó cũng nghỉ; 18/09 là ngày đầu được chấp nhận.

Kết quả thay đổi thành 18/09 mà không sửa `nextWorkingDayAfter`.

Đây là bằng chứng phần thuật toán không phụ thuộc một danh sách nghỉ cụ thể. Nó chỉ dùng giao diện phân loại ngày của `WorkCalendar`.

### 6.3. Có ngày mở cửa đặc biệt

Lịch `extraOpen` cho phép làm việc vào thứ Bảy 14/09. Vì đó là ứng viên đầu tiên sau thứ Sáu và chính sách cho làm việc, kết quả là 14/09.

Không cần thêm nhánh “nếu làm bù thứ Bảy” vào vòng lặp. Ngoại lệ nằm trong đối tượng chính sách.

### 6.4. Tính từ ngày đầu vào hay sau ngày đầu vào

`workingDayOnOrAfter` nhận thứ Sáu 13/09 và thấy ngày đó đã làm việc nên trả chính 13/09. `nextWorkingDayAfter` với cùng ngày luôn đi ít nhất một ngày trước khi xét.

Hai kết quả khác nhau đều đúng theo hai hợp đồng. Khi nơi gọi chọn sai hàm, không nên sửa bằng cách bù một ngày tùy tiện; cần xác định yêu cầu thật sự muốn loại hay gồm ngày đầu.

### 6.5. Một lịch có ngày nghỉ tuần khác

`fridaySaturdayOff` nghỉ thứ Sáu và thứ Bảy. Sau thứ Sáu 13/09, thứ Bảy nghỉ nhưng Chủ nhật 15/09 được chấp nhận.

Chủ nhật không phải ngày nghỉ tuyệt đối của `LocalDate`. Trạng thái làm/nghỉ đến từ chính sách của lịch.

### 6.6. Năm nhuận

Sau 28/02/2024, lịch thường chấp nhận 29/02. Thuật toán không cần tự tính số ngày của tháng Hai; `LocalDate.plusDays` xử lý ranh giới lịch.

Tương tự, chuyển tháng và năm thuộc phép tính lịch của Java, còn việc ngày mới có làm việc hay không thuộc chính sách.

## 7. Phạm vi lịch ngăn việc suy đoán dữ liệu thiếu

Ngày 31/12/2024 nằm trong lịch mẫu, nhưng ngày sau đó đã ngoài `validToExclusive`. Hàm không được thấy tập `closedDates` không có 01/01/2025 rồi kết luận 01/01 là ngày làm việc.

Không có mục ngày nghỉ của năm 2025 có thể chỉ là **chưa có dữ liệu năm đó**.

Trong chương trình:

```text
coverage limit = No working day in covered range
```

Thông báo này chỉ nói chưa tìm được ngày làm việc trong phạm vi đã cung cấp. Nó không khẳng định sau đó không bao giờ có ngày làm việc.

Nếu muốn tính sang năm mới, nơi chuẩn bị dữ liệu phải cung cấp ảnh chụp lịch có miền bao phủ phù hợp. Không để vòng lặp tự gọi một dịch vụ mạng ở mỗi ngày vì việc tải lịch và việc tính ngày có trách nhiệm khác nhau.

Tương tự, đầu vào bắt đầu nằm ngoài phạm vi bị từ chối ngay. Bài chọn hợp đồng này để tránh một yêu cầu không rõ ngày đầu có được lịch biết tới hay không. Có thể thiết kế API khác cho trường hợp bắt đầu ngay trước phạm vi, nhưng phải định nghĩa riêng.

## 8. Vì sao lịch đóng mọi ngày vẫn dừng?

`closedEveryDay` cấu hình cả bảy thứ là ngày nghỉ. Nếu không có ngày mở đặc biệt, không ứng viên nào được chấp nhận.

Vòng lặp vẫn dừng tại `validToExclusive` và báo lỗi. Nó không là một vòng `while (true)` chờ một ngày làm việc không chắc sẽ tồn tại.

Với ví dụ, phạm vi một năm là hữu hạn và nhỏ. Với hệ thống cho phép phạm vi rất lớn, nên bổ sung giới hạn hợp lý cho số ngày có thể tìm hoặc miền năm ứng dụng chấp nhận. Một giới hạn tài nguyên bị vượt cũng cần được báo rõ, không trả ứng viên cuối cùng như thể đó là ngày làm việc.

Phạm vi bao phủ trả lời “dữ liệu này biết đến đâu”; giới hạn tìm kiếm trả lời “yêu cầu này được phép tốn bao nhiêu công”. Hai khái niệm có thể cùng tồn tại trong một triển khai lớn hơn.

## 9. Kiểm chứng những thuộc tính quan trọng

Đối chiếu vài ngày mẫu là cần thiết, nhưng bài toán còn có các thuộc tính để kiểm tra:

1. Kết quả phải sau ngày bắt đầu với hàm `nextWorkingDayAfter`.
2. Kết quả phải được chính sách chấp nhận.
3. Mọi ngày nằm giữa ngày bắt đầu và kết quả đều phải là ngày nghỉ.
4. Kết quả nằm trong phạm vi đã biết.
5. Cùng đầu vào và cùng ảnh chụp chính sách phải cho cùng kết quả.

Đoạn phương thức sau minh họa kiểm chứng tính gần nhất. Có thể đặt thêm vào lớp ví dụ để kiểm tra một kết quả; nó không phải chương trình độc lập:

```java
static void verifyNearest(
        LocalDate startExclusive,
        LocalDate result,
        WorkCalendar calendar) {

    if (!result.isAfter(startExclusive)) {
        throw new AssertionError("Result must be after start");
    }
    if (!calendar.isWorkingDate(result)) {
        throw new AssertionError("Result must be a working date");
    }
    for (LocalDate date = startExclusive.plusDays(1);
            date.isBefore(result);
            date = date.plusDays(1)) {
        if (calendar.isWorkingDate(date)) {
            throw new AssertionError("An earlier working date was skipped");
        }
    }
}
```

Cách này kiểm tra đúng tính chất bài toán. Nếu chỉ kiểm tra `result.isAfter(start)`, một hàm trả bừa ngày làm việc sau đó hai tuần vẫn có thể qua.

Không dùng `assert` mà quên rằng cơ chế assert có thể bị tắt khi chạy thông thường. Ví dụ kiểm chứng trên ném `AssertionError` rõ ràng khi thuộc tính bị vi phạm.

## 10. Các trường hợp dữ liệu sai cần được phát hiện

| Dữ liệu sai | Hành vi của lời giải |
| --- | --- |
| Ngày đầu phạm vi bằng hoặc sau ngày kết thúc | Từ chối tạo lịch |
| Một ngày vừa đóng vừa mở đặc biệt | Từ chối chính sách xung đột |
| Ngày ngoại lệ ngoài miền đã khai báo | Từ chối dữ liệu lịch |
| Tập chứa phần tử `null` | `Set.copyOf` từ chối |
| Ngày bắt đầu ngoài phạm vi | Báo lỗi, không tìm tiếp |
| Hết miền nhưng không có kết quả | Báo không có ngày làm việc trong miền |

Việc kiểm tra này không chứng minh dữ liệu lịch đúng về mặt nghiệp vụ. Một người nhập nhầm ngày nghỉ từ 16 sang 17 vẫn có thể tạo cấu hình hợp lệ về cấu trúc. Nguồn lịch và quy trình duyệt dữ liệu cần được quản lý ở lớp chuẩn bị chính sách.

Bài thực hành chủ động dùng dữ liệu giả định để kiểm chứng cơ chế. Không lấy một tập ngày trong ví dụ đưa vào hệ thống thật như thể đó là lịch nghỉ đã được xác nhận.

## 11. Đặt thuật toán trong ứng dụng

Một cách chia trách nhiệm hợp lý:

| Thành phần | Việc cần làm |
| --- | --- |
| Nơi nhận yêu cầu | Xác định ngày đầu và lịch của đơn vị nào |
| Nơi tải lịch | Đọc ngày nghỉ/ngày mở và phạm vi bao phủ |
| `WorkCalendar` | Kiểm tra dữ liệu, phân loại ngày |
| Hàm tìm ngày | Duyệt có giới hạn và trả ngày gần nhất |
| Nơi hiển thị hoặc lưu kết quả | Định dạng/lưu theo yêu cầu |

Nếu đầu vào là một thời điểm, nơi nhận yêu cầu phải chọn vùng nghiệp vụ rồi mới lấy `LocalDate`. Gần nửa đêm, cùng một `Instant` có thể là hai ngày khác nhau ở hai vùng.

Nếu yêu cầu nhận sau giờ chốt được coi là tiếp nhận ngày sau, quy tắc giờ chốt là bước riêng trước phép tìm hoặc trong quy trình nghiệp vụ đã được nêu rõ. Không đưa thêm giờ vào `LocalDate` bằng một phép đoán.

Nếu cần một thời điểm thực thi vào giờ mở cửa của ngày tìm được, kết quả `LocalDate` mới chỉ là một phần. Cần ghép giờ, vùng và xử lý những trường hợp ngày giờ địa phương không tồn tại hoặc không duy nhất nếu vùng có thay đổi offset.

## 12. Độ phức tạp và giới hạn của cách duyệt

Nếu phải kiểm tra `K` ứng viên trước khi tìm được kết quả, thuật toán gọi chính sách `K` lần. Với tập có chi phí tra cứu trung bình hằng số, thời gian tương ứng là `O(K)`.

Bộ nhớ bổ sung của vòng lặp là hằng số: chỉ giữ ngày ứng viên. Bộ nhớ của chính sách phụ thuộc kích thước các tập ngoại lệ.

Với các yêu cầu tìm ngày kế tiếp trong lịch một năm, cách duyệt dễ hiểu và kiểm chứng. Nếu một hệ thống cần tính rất nhiều lần trên cùng dữ liệu lớn, có thể tiền tính chỉ mục ngày làm việc. Chỉ mục phải gắn với đúng phiên bản và phạm vi lịch; thay ngày nghỉ mà không xây lại dữ liệu suy ra sẽ cho kết quả cũ.

Không tối ưu bằng việc lặp lại quy tắc nghỉ tuần trong nhiều chỗ. Dù dùng vòng lặp hay chỉ mục, cần một định nghĩa chính sách nhất quán để kết quả không mâu thuẫn.

## 13. Bài tập mở rộng

### 13.1. Bổ sung bộ tình huống kiểm chứng

Tạo các trường hợp:

- Ngày đầu vào là thứ Năm làm việc; ngày kế tiếp là thứ Sáu.
- Ngày đầu vào là một ngày nghỉ, nhưng ngày sau mở cửa.
- Nhiều ngày đóng cửa liên tiếp qua ranh giới tháng.
- Ngày mở đặc biệt nằm đúng cuối tuần.
- Đầu vào là ngày đầu phạm vi và ngày cuối phạm vi.
- Lịch nghỉ mọi thứ nhưng có một ngày mở đặc biệt trong miền.
- Cùng một ngày nằm ở cả hai tập ngoại lệ và phải bị từ chối.

Với từng trường hợp, giải thích đáp án bằng cách liệt kê ứng viên đã bị loại và lý do. Không chỉ ghi một ngày kết quả mà thiếu chính sách sử dụng.

### 13.2. Mở rộng sang n ngày làm việc

Thiết kế hàm cộng `n` ngày làm việc với hợp đồng rõ cho:

- `n = 0`.
- Ngày bắt đầu có được tính không.
- Có cho số âm không.
- Không đủ miền lịch thì làm gì.

Không suy rằng gọi hàm ngày kế tiếp `n` lần là đủ cho mọi hợp đồng. Nó có thể là một cách hiện thực, nhưng cần xét chi phí, miền bao phủ và ý nghĩa các giá trị biên.

### 13.3. Cung cấp giải thích kết quả

Thay vì chỉ trả `LocalDate`, có thể tạo một kiểu kết quả chứa ngày tìm được và lý do các ứng viên bị bỏ. Điều này hữu ích cho một công cụ học tập hoặc khi cần giải thích hạn xử lý.

Không để giải thích trở thành nguồn chính sách thứ hai. Lý do và quyết định phải được tính nhất quán từ cùng dữ liệu; không viết thêm một danh sách ngày nghỉ riêng chỉ để hiển thị.

### 13.4. Phân biệt thiếu lịch với không có ngày mở trong lịch

Trong ví dụ, hết phạm vi được báo bằng một ngoại lệ với thông điệp rõ. Một API lớn hơn có thể cần các kiểu kết quả riêng cho thiếu dữ liệu, lịch không có ngày mở trong khoảng cho phép hoặc đầu vào không hợp lệ.

Nếu chọn một kiểu kết quả như vậy, hãy giữ sự phân biệt khi hiển thị lỗi. Không chuyển mọi trường hợp thành `null` khiến người gọi không biết phải tải thêm dữ liệu, sửa cấu hình hay báo không có kết quả.

## 14. Tiêu chí hoàn thành bài thực hành

Một lời giải đáp ứng bài không chỉ cần chạy ra đúng 16/09 trong trường hợp thông thường. Nó cần chứng minh:

- Hiểu và giữ đúng hợp đồng loại/gồm ngày đầu.
- Chính sách tách khỏi phép duyệt lịch.
- Thay tập ngày nghỉ có thể đổi kết quả mà không sửa thuật toán.
- Có xử lý ngày mở đặc biệt và dữ liệu xung đột.
- Không suy đoán ngày ngoài miền dữ liệu.
- Dừng khi không tìm được và báo trạng thái có ý nghĩa.
- Kết quả thực sự là ngày làm việc gần nhất.
- Kiểm chứng được cuối tuần, ngoại lệ, năm nhuận và giới hạn phạm vi.

Qua bài này, phép tính lịch và chính sách nghiệp vụ được nối với nhau bằng một câu hỏi đơn giản: “ngày này có làm việc không?”. Hợp đồng và dữ liệu quyết định câu trả lời; thuật toán chỉ cần duyệt đúng thứ tự và dừng đúng điều kiện.
