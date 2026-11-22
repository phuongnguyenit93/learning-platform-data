# Không dùng chuỗi đã định dạng làm dữ liệu ngày giờ nội bộ

## 1. Giá trị ngày giờ và cách hiển thị là hai việc khác nhau

Một thời điểm như `2024-01-15T02:00:10.123Z` có thể được hiển thị thành:

```text
15/01/2024 09:00
15 Jan 2024, 09:00
2024-01-15 02:00 UTC
```

Những chuỗi này phục vụ người đọc, không có cùng cấu trúc và không nhất thiết giữ đủ thông tin gốc. Nếu chuỗi chỉ hiển thị đến phút, nó đã bỏ giây và phần lẻ. Nếu không có offset/múi giờ, người đọc mã cũng chưa biết phải diễn giải giờ theo nơi nào.

Trong phần nghiệp vụ, hãy giữ giá trị bằng kiểu phù hợp như `LocalDate`, `YearMonth`, `LocalDateTime`, `Instant` hoặc kiểu có offset/vùng. Định dạng khi cần giao tiếp với người dùng hoặc xuất dữ liệu theo một hợp đồng rõ ràng.

Mục tiêu của quy tắc này là tránh để một nhãn hiển thị trở thành nguồn dữ liệu cho phép so sánh, tính toán hoặc ra quyết định. Chuỗi đầu vào/đầu ra vẫn có vai trò đúng tại ranh giới hệ thống.

## 2. Vì sao chuỗi hiển thị làm sai nghiệp vụ?

### 2.1. So sánh chuỗi khác so sánh ngày

Hai ngày:

```text
31/12/2024
01/01/2025
```

Theo lịch, ngày 31/12/2024 đứng trước 1/1/2025. Theo thứ tự từ điển, chuỗi bắt đầu bằng `01` lại đứng trước chuỗi bắt đầu bằng `31`.

Vì thế, `String.compareTo`, `sorted()` trên các nhãn hiển thị hoặc toán tử so sánh chuỗi của một tầng khác không tự mang ý nghĩa lịch.

Cách đúng là sắp xếp `LocalDate` trước, sau đó mới định dạng từng ngày. Nếu dữ liệu là sự kiện trên trục thời gian, sắp xếp theo `Instant`, không theo giờ hiển thị của từng người dùng.

### 2.2. Một nhãn có thể tương ứng nhiều giá trị

Hai thời điểm `02:00:10.123Z` và `02:00:59.999Z` cùng được hiển thị thành “09:00” tại offset +07:00 khi mẫu chỉ có giờ-phút.

Nhãn giống nhau không có nghĩa sự kiện xảy ra cùng lúc. Vì thế:

- Không dùng nhãn đến phút để phát hiện hai thời điểm bằng nhau.
- Không dùng nhãn định dạng làm mã định danh sự kiện.
- Không lấy kết quả đã làm tròn hiển thị để kiểm tra hạn hoặc thứ tự.

Mã định danh sự kiện là một trách nhiệm riêng. Thời điểm có kiểu được dùng để tính toán và lọc; nhãn hiển thị dùng để trình bày.

### 2.3. Đổi ngôn ngữ hoặc múi giờ không được đổi dữ liệu gốc

Một người dùng xem giờ Việt Nam, người khác xem UTC; cả hai có thể đang xem cùng sự kiện. Đổi định dạng hiển thị không nên làm thay `Instant` trong mô hình.

Nếu dữ liệu nội bộ đã là chuỗi địa phương, mỗi lần hiển thị lại có thể đòi hỏi đoán ngôn ngữ, định dạng hoặc múi giờ gốc. Những thông tin đó có thể đã không còn được lưu.

`Instant` mô hình hóa một thời điểm, còn `LocalDate` mô hình hóa một ngày không kèm giờ/múi giờ. Chọn đúng kiểu giúp giữ rõ điều dữ liệu đang diễn đạt; xem [Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html) và [LocalDate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html).

## 3. ISO không tự biến mọi phép so chuỗi thành phép so thời gian

Một số biểu diễn được quy định chặt có thể giữ thứ tự khi so chuỗi, chẳng hạn ngày năm-tháng-ngày với cùng độ rộng và cùng miền năm phù hợp. Nhưng không được mở rộng kết luận ấy cho mọi chuỗi “trông giống ISO”.

Các yếu tố có thể làm khác thứ tự:

- Chuỗi dùng offset khác nhau.
- Chuỗi có và không có phần lẻ của giây.
- Phần lẻ có độ dài khác nhau.
- Miền năm hoặc dấu năm không cùng cấu trúc.
- Chuỗi có thêm thông tin vùng hoặc cách biểu diễn khác.

Ngay với hai `Instant`:

```text
2024-01-15T02:00:00Z
2024-01-15T02:00:00.001Z
```

Thời điểm thứ nhất xảy ra trước. Nhưng khi so hai chuỗi này, ký tự `Z` của chuỗi đầu được so với dấu `.` của chuỗi sau, dẫn đến thứ tự từ điển ngược với mong muốn.

Do đó, `toString()` hữu ích để trao đổi theo cấu trúc được định nghĩa, nhưng không phải lý do để bỏ phép so có kiểu trong nghiệp vụ. Nếu một hệ thống cố ý thiết kế khóa chuỗi có thứ tự, nó phải công bố đầy đủ định dạng và điều kiện áp dụng; đó là một hợp đồng riêng.

## 4. Chọn kiểu nội bộ theo ý nghĩa dữ liệu

| Ý nghĩa | Kiểu nên xem xét | Không nên tự thêm hoặc bỏ |
| --- | --- | --- |
| Ngày sinh hoặc ngày nghỉ cụ thể | `LocalDate` | Không tự gắn giờ và múi giờ nếu chưa cần |
| Kỳ báo cáo tháng | `YearMonth` | Không tự thêm ngày 1 như thể đã có ngày |
| Ngày giờ địa phương chưa gắn vùng | `LocalDateTime` | Không tự khẳng định một thời điểm UTC |
| Sự kiện đã xác định trên trục thời gian | `Instant` | Không biến thành chuỗi địa phương rồi quên vùng |
| Dữ liệu cần giữ offset | `OffsetDateTime` | Chỉ giữ `Instant` sẽ bỏ offset ban đầu |
| Lịch gắn với vùng có quy tắc | `ZonedDateTime` hoặc ngày giờ + `ZoneId` theo mô hình | Không thay toàn bộ quy tắc vùng bằng một nhãn giờ |

Chọn `LocalDateTime` không tự giải quyết bài toán thời điểm: nó không chứa offset hoặc múi giờ. Chọn kiểu chỉ vì dễ định dạng là chưa đủ; kiểu phải tương ứng với ngữ nghĩa.

Cũng không nhất thiết thay chuỗi bằng một số epoch trần ở mọi nơi. Nếu dùng số ở giao thức, cần công bố đơn vị và cách chuyển; trong Java, kiểu thời gian vẫn giúp tránh nhầm giây với mili giây.

## 5. Luồng xử lý: phân tích ở đầu vào, định dạng ở đầu ra

Một luồng rõ trách nhiệm:

```text
Chuỗi từ biểu mẫu / JSON / tệp
            ↓ phân tích theo hợp đồng đầu vào
Giá trị có kiểu trong Java
            ↓ xác thực, so sánh, sắp xếp, tính toán
Kết quả nghiệp vụ có kiểu
            ↓ chọn locale, múi giờ và mẫu hiển thị
Chuỗi trên màn hình / báo cáo
```

### 5.1. Đầu vào

Chuỗi bên ngoài phải có quy ước. Ví dụ:

- Biểu mẫu nhận ngày theo `dd/MM/uuuu`.
- API nhận thời điểm có offset rõ ràng.
- Trường kỳ tháng nhận `uuuu-MM`.

Phân tích một lần tại nơi nhận dữ liệu, rồi truyền đối tượng có kiểu vào hàm nghiệp vụ. Khi sai, báo lỗi theo hợp đồng; không âm thầm lấy ngày hiện tại, epoch hoặc một múi giờ bất kỳ để bù phần thiếu.

Với mẫu tùy chỉnh dùng để xác thực, nên xác định chế độ xử lý ngày. Ví dụ trong bài dùng `ResolverStyle.STRICT` để từ chối `29/02/2023`.

### 5.2. Phần nghiệp vụ

Các hàm xử lý nhận và trả kiểu thời gian:

- So ngày bằng `isBefore`, `isAfter`, `equals`.
- Cộng lịch bằng các API như `plusDays`, `plusMonths`.
- Sắp xếp sự kiện bằng trường `Instant`.
- Gom nhóm theo `LocalDate` hoặc `YearMonth` đã xác định đúng vùng/quy tắc.

Không định dạng rồi lại tách bằng `substring` để lấy tháng/năm. Các trường này đã có API trực tiếp trên đối tượng.

### 5.3. Đầu ra

Tại lớp hiển thị hoặc đối tượng trả về phục vụ giao diện, chuỗi định dạng là phù hợp. Một mô hình `Event` có thể giữ `Instant startsAt`, trong khi `EventView` có `String displayStart`.

Điểm quan trọng là `displayStart` không được quay trở lại làm nguồn tính hạn hoặc sắp xếp sự kiện. Giữ dữ liệu có kiểu hoặc dữ liệu trao đổi có hợp đồng riêng cho các thao tác đó.

`DateTimeFormatter` cho phép cấu hình mẫu, locale và múi giờ; bản thân bộ định dạng là bất biến và an toàn để dùng chung theo hợp đồng. Các thao tác này thuộc trách nhiệm biểu diễn/đọc dữ liệu, không thay cho mô hình nghiệp vụ; xem [DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html).

## 6. Chương trình Java 17+ minh họa lỗi và cách sửa

Lưu mã sau thành `TypedDateTimeInside.java`. Chương trình không cần thư viện ngoài.

`Event` giữ thời điểm bằng `Instant`; `EventView` giữ chuỗi chỉ phục vụ hiển thị. Hàm `readInput` phân tích đầu vào, còn `toView` chỉ định dạng ở đầu ra.

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class TypedDateTimeInside {
    public record Event(String id, Instant startsAt) {
        public Event {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(startsAt, "startsAt");
        }
    }

    public record EventView(String id, String displayStart) {}

    private static final DateTimeFormatter INPUT_DATE =
            DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT);
    private static int checks;

    private static Event readInput(String id, String rawInstant) {
        return new Event(id, Instant.parse(rawInstant));
    }

    private static EventView toView(Event event, DateTimeFormatter display) {
        return new EventView(event.id(), display.format(event.startsAt()));
    }

    private static void eq(Object actual, Object expected) {
        if (!Objects.equals(actual, expected)) {
            throw new AssertionError("expected=" + expected + ", actual=" + actual);
        }
        checks++;
    }

    private static void rejects(Runnable action) {
        try {
            action.run();
        } catch (DateTimeParseException expected) {
            checks++;
            return;
        }
        throw new AssertionError("Expected DateTimeParseException");
    }

    public static void main(String[] args) {
        LocalDate last = LocalDate.parse("31/12/2024", INPUT_DATE);
        LocalDate next = LocalDate.parse("01/01/2025", INPUT_DATE);
        List<LocalDate> dates = List.of(next, last);
        List<String> textOrder = dates.stream().map(INPUT_DATE::format)
                .sorted().toList();
        List<String> dateOrder = dates.stream().sorted()
                .map(INPUT_DATE::format).toList();
        eq(last.isBefore(next), true);
        eq(textOrder, List.of("01/01/2025", "31/12/2024"));
        eq(dateOrder, List.of("31/12/2024", "01/01/2025"));
        eq(last.plusDays(1), next);
        rejects(() -> LocalDate.parse("29/02/2023", INPUT_DATE));

        Event first = readInput("A", "2024-01-15T02:00:10.123Z");
        Event second = readInput("B", "2024-01-15T02:00:59.999Z");
        DateTimeFormatter display = DateTimeFormatter
                .ofPattern("dd/MM/uuuu HH:mm", Locale.ROOT)
                .withZone(ZoneId.of("Asia/Ho_Chi_Minh"));
        EventView firstView = toView(first, display);
        EventView secondView = toView(second, display);
        eq(first.startsAt().isBefore(second.startsAt()), true);
        eq(firstView.displayStart(), "15/01/2024 09:00");
        eq(firstView.displayStart(), secondView.displayStart());
        eq(first.startsAt().equals(second.startsAt()), false);
        eq(toView(first, display.withZone(ZoneOffset.UTC)).displayStart(),
                "15/01/2024 02:00");
        eq(first.startsAt(), Instant.parse("2024-01-15T02:00:10.123Z"));

        List<String> eventOrder = List.of(second, first).stream()
                .sorted(Comparator.comparing(Event::startsAt))
                .map(Event::id).toList();
        eq(eventOrder, List.of("A", "B"));
        rejects(() -> readInput("C", "2024-01-15T09:00:00"));

        Instant whole = Instant.parse("2024-01-15T02:00:00Z");
        Instant fraction = whole.plusMillis(1);
        eq(whole.isBefore(fraction), true);
        eq(whole.toString().compareTo(fraction.toString()) > 0, true);
        eq(Instant.parse(first.startsAt().toString()), first.startsAt());

        System.out.println("textOrder=" + textOrder);
        System.out.println("dateOrder=" + dateOrder);
        System.out.println("sharedDisplay=" + firstView.displayStart());
        System.out.println("differentInstants="
                + !first.startsAt().equals(second.startsAt()));
        System.out.println("eventOrder=" + eventOrder);
        System.out.println("wholeBeforeFraction=" + whole.isBefore(fraction));
        System.out.println("wholeTextBeforeFractionText="
                + (whole.toString().compareTo(fraction.toString()) < 0));
        System.out.println("PASS checks=" + checks);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 TypedDateTimeInside.java
java TypedDateTimeInside
```

Stdout:

```text
textOrder=[01/01/2025, 31/12/2024]
dateOrder=[31/12/2024, 01/01/2025]
sharedDisplay=15/01/2024 09:00
differentInstants=true
eventOrder=[A, B]
wholeBeforeFraction=true
wholeTextBeforeFractionText=false
PASS checks=16
```

Các kết quả cần giải thích:

- `textOrder` sắp xếp theo ký tự và sai thứ tự lịch.
- `dateOrder` sắp xếp ngày có kiểu trước, rồi mới định dạng.
- `sharedDisplay` giống nhau cho hai thời điểm khác nhau vì mẫu bỏ giây.
- `eventOrder` vẫn là A trước B do dùng `Instant`.
- Hai dòng cuối chứng minh so chuỗi từ `Instant.toString()` không tự đúng với mọi cặp thời điểm.

Hàm `eq` chủ động ném `AssertionError` khi sai nên không cần cờ `-ea`. Hàm `rejects` xác nhận dữ liệu sai bị từ chối. Chương trình cũng kiểm tra rằng đổi múi giờ hiển thị sang UTC không đổi thời điểm trong mô hình.

Ở ví dụ, biểu mẫu ngày là dữ liệu `LocalDate`, còn đầu vào sự kiện là thời điểm. Chuỗi `2024-01-15T09:00:00` bị từ chối khi đọc thành `Instant` vì thiếu offset; chương trình không tự đoán đó là UTC hay giờ Việt Nam.

## 7. Chuỗi vẫn có vai trò ở ranh giới và trong lưu trữ

Quy tắc của bài không cấm dùng chuỗi trong JSON, CSV, log, tệp cấu hình hoặc cột lưu trữ được thiết kế rõ. Điều cần tránh là dùng **chuỗi đã định dạng cho người đọc** như thể nó là giá trị ngày giờ nội bộ đã được xác thực.

Cần phân biệt:

| Loại chuỗi | Mục đích | Cách dùng phù hợp |
| --- | --- | --- |
| Chuỗi nhập | Dữ liệu bên ngoài chờ xác thực | Phân tích theo định dạng được công bố |
| Chuỗi giao thức | Trao đổi giữa các hệ thống | Có kiểu ngữ nghĩa, offset/vùng và độ chính xác rõ |
| Chuỗi hiển thị | Người dùng đọc theo ngôn ngữ/múi giờ | Định dạng từ giá trị có kiểu |
| Chuỗi nguyên văn cần lưu | Giữ bản gốc phục vụ mục đích riêng | Lưu riêng; không tự coi nó là dữ liệu đã hợp lệ |

Nếu kho lưu ngày giờ bằng văn bản, phần đọc cần chuyển thành kiểu phù hợp trước khi tính toán. Kiểm tra đi-về phải chứng minh giữ đúng thông tin theo hợp đồng, gồm phần giây và ngữ cảnh vùng nếu cần.

Một bộ tuần tự hóa có thể cho phép mô hình Java vẫn dùng `Instant` trong khi JSON xuất chuỗi. Đó không phải mâu thuẫn: biểu diễn trên đường truyền và kiểu trong mô hình là hai lớp khác nhau. Cách ánh xạ cụ thể phải được cấu hình và kiểm chứng theo thư viện đang dùng.

## 8. Những chỗ chuỗi hiển thị hay vô tình trở thành nguồn dữ liệu

### Lọc và tìm kiếm ngày

Nếu người dùng chọn một ngày, hãy phân tích thành `LocalDate`. Nếu cần tìm sự kiện của ngày đó, tính khoảng thời điểm theo múi giờ phù hợp rồi so giá trị thời gian. Không lọc bằng tiền tố chuỗi hiển thị đã đổi theo locale.

### Gom nhóm báo cáo

Nhóm theo `YearMonth` hoặc ngày có kiểu, sau đó tạo nhãn cho nhóm. Nếu dùng nhãn “tháng 2/2024” làm khóa từ đầu, thay ngôn ngữ hoặc kiểu viết có thể tạo nhiều khóa cho cùng kỳ.

### Bộ nhớ đệm và mã định danh

Một chuỗi “15/01/2024 09:00” có thể trùng cho nhiều sự kiện. Dùng mã định danh thật cho đối tượng và giữ thời gian có kiểu cho các tiêu chí thời gian. Nếu cố ý dùng khóa thời gian chuẩn, phải xác định ngữ nghĩa và mức chính xác, không lấy nhãn màn hình làm khóa ngẫu nhiên.

### Kiểm tra hạn

Không so `deadlineText` với `todayText`. Với hạn là ngày, so các `LocalDate` theo cùng quy tắc ngày nghiệp vụ. Với hạn là thời điểm, so `Instant`. Hai loại hạn có ngữ nghĩa khác nhau ngay cả khi giao diện đều in ra một ngày.

## 9. Chuyển mã đang dùng chuỗi sang mô hình có kiểu

Có thể cải thiện từng bước:

1. **Xác định ý nghĩa từng trường.** Chuỗi đang là ngày lịch, giờ địa phương, thời điểm hay kỳ tháng?
2. **Chọn kiểu đúng.** Không chọn `LocalDateTime` cho mọi trường chỉ vì nó có nhiều thành phần.
3. **Tập trung việc phân tích ở đầu vào.** Công bố định dạng và cách báo lỗi.
4. **Đổi chữ ký các hàm tính toán.** Truyền kiểu ngày giờ thay cho chuỗi hiển thị.
5. **Thay các phép so và tách chuỗi.** Dùng API lịch và bộ so sánh theo trường có kiểu.
6. **Đưa định dạng về đầu ra.** Mỗi nơi hiển thị chọn locale/múi giờ theo nhu cầu, không sửa giá trị gốc.
7. **Kiểm tra dữ liệu cũ và ca mất thông tin.** Nếu trước đây chỉ lưu đến phút, không thể tự khôi phục giây/nano gốc.
8. **Kiểm tra giao thức và kho.** Đảm bảo chuyển đổi không làm thay nghĩa khi đi qua các lớp.

Không tự sửa dữ liệu lịch sử bằng cách đoán. Nếu một chuỗi không có múi giờ nhưng nghiệp vụ cần thời điểm, phải có nguồn quy tắc diễn giải; chỉ đổi tên trường thành `Instant` chưa cung cấp thông tin thiếu.

## 10. Lỗi phổ biến và thực hành

Các lỗi cần tránh:

- Coi sắp xếp từ điển là sắp xếp thời gian cho mọi định dạng.
- Định dạng sớm, rồi phân tích lại nhiều lần ở các hàm bên trong.
- Lấy nhãn đã bỏ giây làm dữ liệu gốc.
- Dùng cùng một chuỗi vừa làm nhãn, vừa làm khóa, vừa làm điều kiện lọc.
- Cho rằng định dạng ISO nào cũng có cùng thứ tự khi so ký tự.
- Chọn múi giờ từ môi trường một cách ngầm định khi giải mã chuỗi địa phương.
- Dùng ngày/giờ hiện tại để thay dữ liệu sai mà không có yêu cầu.
- Cho rằng thay chuỗi bằng bất kỳ kiểu thời gian nào cũng đã đúng ngữ nghĩa.

Thực hành:

1. **Danh sách hạn có “31/01/2025”, “01/02/2025”, “15/12/2024”.** Phân tích thành `LocalDate`, sắp xếp, rồi định dạng. Kết quả đúng là 15/12/2024, 31/01/2025, 01/02/2025.

2. **Giao diện chỉ muốn hiển thị đến phút nhưng thứ tự sự kiện cần chính xác đến mili giây.** Giữ `Instant` đầy đủ trong mô hình; mẫu đầu ra có thể bỏ giây mà phép sắp xếp vẫn dùng giá trị gốc.

3. **Người dùng đổi múi giờ hiển thị.** Tạo nhãn mới từ cùng thời điểm; không cộng/trừ vào dữ liệu sự kiện chỉ để màn hình đổi giờ.

4. **Báo cáo nhóm theo tháng và có hai ngôn ngữ.** Nhóm theo `YearMonth`, đặt nhãn theo ngôn ngữ sau khi nhóm. Không để cùng một kỳ trở thành hai nhóm vì nhãn khác nhau.

5. **Đầu vào thời điểm thiếu offset.** Nếu hợp đồng yêu cầu thời điểm rõ ràng, báo lỗi hoặc yêu cầu ngữ cảnh được quy định. Không dùng chuỗi thiếu thông tin để tự khẳng định một `Instant`.

Hãy để kiểu ngày giờ giữ ý nghĩa và phục vụ phép tính; để bộ định dạng quyết định cách người dùng nhìn thấy kết quả. Khi hai trách nhiệm này được giữ rõ, thay đổi cách hiển thị không làm thay đổi quy tắc nghiệp vụ.
