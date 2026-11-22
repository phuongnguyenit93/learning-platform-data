# Calendar, TimeZone và các giá trị mặc định

## 1. Vì sao cần hiểu API ngày giờ cũ?

Trong Java Core, hai lớp lâu đời `java.util.Calendar` và `java.util.TimeZone` xuất hiện trong nhiều hệ thống, thư viện, ứng dụng enterprise và API cần tương thích ngược. Chúng có thể hoạt động đúng, nhưng **đặc biệt dễ phát sinh lỗi do phụ thuộc các giá trị mặc định dùng chung của JVM**.

Ví dụ, hai câu lệnh:

```java
Calendar calendar = Calendar.getInstance();
TimeZone zone = TimeZone.getDefault();
```

không có nghĩa là "lấy lịch và múi giờ của người dùng đang đăng nhập". Chúng lấy cấu hình mặc định của **tiến trình JVM** tại thời điểm tương ứng. Nếu cùng server phục vụ người dùng ở Việt Nam, Hoa Kỳ và Nhật Bản, việc dùng những mặc định đó một cách không kiểm soát có thể khiến **cùng một thời điểm** được đọc thành giờ/ngày khác mong muốn.

Sau bài học, bạn sẽ biết:

- `Calendar`, `GregorianCalendar` và `TimeZone` đại diện cho điều gì, cũng như mối quan hệ với `Date`.
- `Calendar.getInstance()` lấy **múi giờ mặc định** và **locale mặc định dạng FORMAT** như thế nào.
- Sự khác biệt giữa `Locale`, `TimeZone`, **offset UTC** và **điểm thời gian (instant)**.
- Rủi ro khi gọi `Locale.setDefault(...)` hoặc `TimeZone.setDefault(...)` theo từng request/thread.
- Những bẫy `MONTH` bắt đầu từ 0, lenient dates, `add`/`roll`, week rules và daylight saving time (DST).
- Cách dùng API legacy có truyền locale/time zone rõ ràng và hướng chuyển sang `java.time` trên Java 17+.

## 2. Ba đối tượng mang những ý nghĩa khác nhau

| Thành phần | Trả lời câu hỏi | Điểm cần nhớ |
| --- | --- | --- |
| `java.util.Date` | Một điểm thời gian với độ phân giải mili-giây | Không tự mang locale và múi giờ của người dùng |
| `java.util.TimeZone` | Quy tắc chuyển UTC sang giờ địa phương cho một vùng hoặc offset | Có thể gồm thay đổi DST trong lịch sử; khác với locale |
| `java.util.Calendar` | Các trường lịch như năm, tháng, ngày, giờ trong một hệ lịch, dựa trên time zone | Mutable; các trường phụ thuộc time zone và cấu hình lịch |
| `java.util.Locale` | Quy ước ngôn ngữ và vùng văn hóa cho hiển thị/định dạng | Không xác định duy nhất múi giờ |
| `java.time.Instant` | Điểm thời gian tuyệt đối, chính xác tới nano-giây trong mô hình Java Time | Thường thích hợp để lưu timestamp |
| `java.time.ZoneId` / `ZonedDateTime` | ID vùng và thời gian địa phương gắn quy tắc vùng | Thay thế hiện đại cho nhiều trường hợp của `TimeZone`/`Calendar` |

Một `Date` có thể được hiển thị ở các vùng khác nhau mà **mili-giây epoch không đổi**. `Calendar` kết hợp điểm thời gian với vùng giờ để suy các trường năm/tháng/ngày/giờ. Locale tác động đến cách đặt tên thứ, tháng, các quy tắc tuần và trong một số trường hợp loại lịch, nhưng **không** ngầm chỉ định vị trí địa lý hoặc time zone của người dùng.

Ví dụ: hai người có `Locale.forLanguageTag("en-US")` có thể sinh sống ở New York và Tokyo. Ngược lại, một người sống tại TP.HCM vẫn có thể dùng giao diện tiếng Anh. Vì vậy, **giữ `Locale` và `TimeZone`/`ZoneId` thành hai lựa chọn độc lập**.

## 3. Mặc định cấp JVM: nguồn gốc và phạm vi

### 3.1. `TimeZone.getDefault()`

`TimeZone.getDefault()` trả time zone mặc định của JVM. Mặc định ban đầu thường được xác định theo môi trường hệ điều hành và thiết lập khởi động, trong đó có thuộc tính hệ thống `user.timezone`. Chương trình có thể thay đổi vùng mặc định:

```java
TimeZone.setDefault(TimeZone.getTimeZone("UTC"));
```

Đây là **thay đổi phạm vi JVM**, không phải "múi giờ của request hiện tại". Các luồng khác dùng API lấy default về sau có thể nhận `UTC`. Việc gọi `setDefault(null)` có thể khiến runtime xác định lại giá trị mặc định; trong test thường nên lưu giá trị cũ và khôi phục chính nó, không suy đoán giá trị mới.

API `TimeZone.getDefault()` trả về một đối tượng mặc định được sao chép để tránh sửa trực tiếp default thông qua đối tượng trả về. Nhưng `TimeZone.setDefault(...)` là thao tác thay **cấu hình mặc định chung**; nhận đối tượng sao chép không làm biến default trở thành local theo thread.

### 3.2. `Locale.getDefault()` và `Locale.Category.FORMAT`

Java có mặc định locale ở cấp JVM, trong đó có hai category:

- `Locale.Category.FORMAT` dành cho các thao tác định dạng/lịch theo locale.
- `Locale.Category.DISPLAY` dành cho việc hiển thị tên ngôn ngữ/vùng và nội dung tương tự.

`Calendar.getInstance()` không lấy preference cá nhân từ một HTTP request. Khi dựng calendar theo mặc định, việc lựa chọn locale thường dùng **`Locale.getDefault(Locale.Category.FORMAT)`**.

`Locale.setDefault(Locale)` thay base default và thiết lập category mặc định; `Locale.setDefault(Locale.Category.FORMAT, locale)` chỉ thay category tương ứng nhưng **vẫn ở phạm vi JVM**. Không áp dụng cách đổi các giá trị này ở đầu mỗi request để cố hỗ trợ đa ngôn ngữ/đa vùng giờ.

### 3.3. Các overload của `Calendar.getInstance`

| Cách tạo | Time zone | Locale |
| --- | --- | --- |
| `Calendar.getInstance()` | Default của JVM | FORMAT default của JVM |
| `Calendar.getInstance(TimeZone zone)` | Time zone được truyền | FORMAT default |
| `Calendar.getInstance(Locale locale)` | Default time zone | Locale được truyền |
| `Calendar.getInstance(TimeZone zone, Locale locale)` | **Time zone tường minh** | **Locale tường minh** |

Khi xử lý dữ liệu người dùng hoặc giao tiếp với hệ thống bên ngoài, **ưu tiên overload nhận cả time zone lẫn locale** nếu vẫn phải dùng `Calendar`.

### 3.4. Có phải đổi default sẽ cập nhật các đối tượng `Calendar` đã tạo?

Không mặc định. Một đối tượng calendar đã được xây dựng có time zone và các thuộc tính của nó. Thay default của JVM chủ yếu ảnh hưởng **lần xây dựng mới** của code đang dựa vào default, chứ không tự đồng bộ mọi calendar đã tạo trước đó.

Điều này khiến việc đổi default giữa chừng còn khó kiểm soát hơn: hai thành phần của ứng dụng có thể giữ những đối tượng đã khởi tạo ở thời điểm khác nhau, với các time zone/locale khác nhau.

## 4. Ví dụ Java 17+: xem tác động của default và category

Tạo file `LegacyDefaultsDemo.java`:

```java
import java.util.Calendar;
import java.util.Locale;
import java.util.TimeZone;

public class LegacyDefaultsDemo {
    public static void main(String[] args) {
        Locale beforeBase = Locale.getDefault();
        Locale beforeFormat =
                Locale.getDefault(Locale.Category.FORMAT);
        Locale beforeDisplay =
                Locale.getDefault(Locale.Category.DISPLAY);
        TimeZone beforeZone = TimeZone.getDefault();

        try {
            Locale.setDefault(Locale.US);
            Locale.setDefault(Locale.Category.FORMAT, Locale.FRANCE);
            TimeZone.setDefault(TimeZone.getTimeZone("UTC"));

            Calendar fromDefault = Calendar.getInstance();
            Calendar explicit = Calendar.getInstance(
                    TimeZone.getTimeZone("UTC"), Locale.US);

            System.out.println("base locale: "
                    + Locale.getDefault().toLanguageTag());
            System.out.println("format locale: "
                    + Locale.getDefault(Locale.Category.FORMAT)
                            .toLanguageTag());
            System.out.println("default calendar zone: "
                    + fromDefault.getTimeZone().getID());
            System.out.println("default first day: "
                    + fromDefault.getFirstDayOfWeek());
            System.out.println("default minimal days: "
                    + fromDefault.getMinimalDaysInFirstWeek());
            System.out.println("US first day: "
                    + explicit.getFirstDayOfWeek());
            System.out.println("US minimal days: "
                    + explicit.getMinimalDaysInFirstWeek());

            TimeZone.setDefault(
                    TimeZone.getTimeZone("Asia/Tokyo"));
            System.out.println("existing calendar zone: "
                    + fromDefault.getTimeZone().getID());
            System.out.println("new calendar zone: "
                    + Calendar.getInstance().getTimeZone().getID());
        } finally {
            // Chỉ an toàn trong thí nghiệm/test JVM không chạy đồng thời.
            Locale.setDefault(beforeBase);
            Locale.setDefault(
                    Locale.Category.FORMAT, beforeFormat);
            Locale.setDefault(
                    Locale.Category.DISPLAY, beforeDisplay);
            TimeZone.setDefault(beforeZone);
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 LegacyDefaultsDemo.java
java LegacyDefaultsDemo
```

Kết quả với dữ liệu locale chuẩn của JDK đã kiểm chứng:

```text
base locale: en-US
format locale: fr-FR
default calendar zone: UTC
default first day: 2
default minimal days: 4
US first day: 1
US minimal days: 1
existing calendar zone: UTC
new calendar zone: Asia/Tokyo
```

Trong `Calendar`, `Calendar.SUNDAY == 1` và `Calendar.MONDAY == 2`. `Locale.FRANCE` thông thường có tuần bắt đầu vào thứ Hai và yêu cầu tối thiểu 4 ngày trong tuần đầu của năm; `Locale.US` thường bắt đầu vào Chủ nhật với 1 ngày tối thiểu. Đây là lý do **locale có thể ảnh hưởng số thứ tự tuần** dù time zone của hai lịch đều là `UTC`.

Ví dụ cố ý đổi các default để chứng minh hành vi, sau đó khôi phục trong `finally`. **Không đưa kiểu thay default này vào request handler của server đa luồng.** `finally` không biến một chuỗi thay default/thực hiện/khôi phục thành phép toán được cách ly cho từng request.

## 5. Cùng một instant, ngày và giờ địa phương có thể khác

Giả sử một điểm thời gian tuyệt đối là:

```text
2026-01-01T00:30:00Z
```

Chữ `Z` ở đây có nghĩa offset UTC +00:00. Tại điểm thời gian này:

- `UTC`: ngày 1/1/2026, 00:30.
- `America/Los_Angeles`: ngày 31/12/2025, 16:30 theo offset hiệu lực mùa đông.
- `Asia/Tokyo`: ngày 1/1/2026, 09:30.

Nếu dùng `Calendar.getInstance()` mà không truyền time zone, kết quả phụ thuộc JVM default; cùng dữ liệu timestamp có thể nhảy sang **ngày hoặc năm khác**.

### Ví dụ chạy được: một epoch, ba múi giờ

Tạo `CalendarInstantDemo.java`:

```java
import java.time.Instant;
import java.util.Calendar;
import java.util.Locale;
import java.util.TimeZone;

public class CalendarInstantDemo {
    static void show(Instant instant, String zoneId) {
        Calendar calendar = Calendar.getInstance(
                TimeZone.getTimeZone(zoneId), Locale.US);
        calendar.setTimeInMillis(instant.toEpochMilli());

        System.out.printf(
                "%s => %04d-%02d-%02d %02d:%02d%n",
                zoneId,
                calendar.get(Calendar.YEAR),
                calendar.get(Calendar.MONTH) + 1,
                calendar.get(Calendar.DAY_OF_MONTH),
                calendar.get(Calendar.HOUR_OF_DAY),
                calendar.get(Calendar.MINUTE));
    }

    public static void main(String[] args) {
        Instant instant =
                Instant.parse("2026-01-01T00:30:00Z");
        show(instant, "UTC");
        show(instant, "America/Los_Angeles");
        show(instant, "Asia/Tokyo");
    }
}
```

```bash
javac CalendarInstantDemo.java
java CalendarInstantDemo
```

Kết quả (với quy tắc tzdb cho mốc thời gian đã nêu):

```text
UTC => 2026-01-01 00:30
America/Los_Angeles => 2025-12-31 16:30
Asia/Tokyo => 2026-01-01 09:30
```

`setTimeInMillis(...)` đặt cùng một epoch cho cả ba lịch; chỉ có **cách suy ra các trường Calendar** khác nhau. Ngược lại, nếu đặt `2026-01-01 00:30` bằng `set(...)` trên ba time zone khác nhau, mỗi vùng có thể biểu thị một instant khác nhau.

**Ghi nhớ:** `Calendar.getTime()` trả về `Date` đại diện cho instant, không phải "Date mang timezone"; khi format `Date`, formatter và zone bạn chọn mới quyết định cách hiển thị.

## 6. Những bẫy quen thuộc của `Calendar`

### 6.1. `MONTH` bắt đầu từ số 0

Trong `Calendar`:

```text
Calendar.JANUARY  == 0
Calendar.FEBRUARY == 1
Calendar.MARCH    == 2
Calendar.DECEMBER == 11
```

Do đó:

```java
Calendar c = Calendar.getInstance(
        TimeZone.getTimeZone("UTC"), Locale.US);
c.clear();
c.set(2026, Calendar.MARCH, 8);
System.out.println(c.get(Calendar.MONTH) + 1); // 3
```

Đây là đoạn code **minh họa trong phương thức**, không phải một chương trình Java độc lập. `clear()` xóa các trường còn tồn dư để tránh ảnh hưởng khi dựng thời điểm; đừng dùng tháng `3` nếu đang muốn nói tháng Ba trong `set(year, month, day)`.

Các trường khác cũng có khác biệt:

- `Calendar.DAY_OF_WEEK`: Chủ nhật = `1`, thứ Hai = `2`.
- `Calendar.HOUR`: giờ theo chu kỳ 12 giờ, cần kết hợp `AM_PM`.
- `Calendar.HOUR_OF_DAY`: giờ 0–23, thường thích hợp hơn cho timestamp.
- `Calendar.WEEK_OF_YEAR` và `Calendar.getWeekYear()` có thể khác `YEAR` quanh giao điểm năm, tùy quy tắc tuần của locale.
- `Calendar.getActualMaximum(Calendar.DAY_OF_MONTH)` tính số ngày tối đa của tháng trong trạng thái lịch hiện tại; khác với việc mặc định tháng luôn có 31 ngày.

### 6.2. Chế độ `lenient` mặc định

`Calendar` thường **lenient** theo mặc định: nó có thể chấp nhận trường lịch vượt miền và chuẩn hóa thành một ngày hợp lệ. Nếu đặt **30/2/2026**, kết quả có thể chuyển thành **2/3/2026** theo lịch Gregory.

```java
Calendar calendar = new java.util.GregorianCalendar(
        TimeZone.getTimeZone("UTC"), Locale.US);
calendar.clear();
calendar.set(2026, Calendar.FEBRUARY, 30);
// Vì mặc định lenient=true, truy cập thời gian sẽ chuẩn hóa.
```

Khi input cần chặt chẽ, dùng `calendar.setLenient(false)` rồi buộc tính toán qua `getTimeInMillis()` hoặc `getTime()` để phát hiện giá trị không hợp lệ. `setLenient(false)` thường không ném lỗi ngay ở lệnh `set(...)`; kiểm tra có thể xảy ra khi truy cập thời gian/các trường đã tính.

### Ví dụ Java 17+: lenient và strict

Tạo `CalendarLeniencyDemo.java`:

```java
import java.util.Calendar;
import java.util.GregorianCalendar;
import java.util.Locale;
import java.util.TimeZone;

public class CalendarLeniencyDemo {
    public static void main(String[] args) {
        GregorianCalendar c = new GregorianCalendar(
                TimeZone.getTimeZone("UTC"), Locale.US);

        c.clear();
        c.set(2026, Calendar.FEBRUARY, 30);
        System.out.printf(
                "lenient: %04d-%02d-%02d%n",
                c.get(Calendar.YEAR),
                c.get(Calendar.MONTH) + 1,
                c.get(Calendar.DAY_OF_MONTH));

        c.setLenient(false);
        c.clear();
        c.set(2026, Calendar.FEBRUARY, 30);
        try {
            c.getTimeInMillis();
            System.out.println("accepted");
        } catch (IllegalArgumentException ex) {
            System.out.println("strict invalid date rejected");
        }
    }
}
```

```bash
javac CalendarLeniencyDemo.java
java CalendarLeniencyDemo
```

```text
lenient: 2026-03-02
strict invalid date rejected
```

### 6.3. `add`, `roll` và cộng mili-giây khác nhau

- `calendar.add(Calendar.DAY_OF_MONTH, 1)` có ý nghĩa **cộng một ngày theo trường lịch**; qua DST, độ dài thời gian thực có thể khác 24 giờ.
- `calendar.roll(field, amount)` thay đổi trường trong phạm vi của nó **mà không làm thay đổi các trường lớn hơn** theo quy tắc của `roll`. Không dùng như phép cộng ngày/tháng thông thường.
- `calendar.setTimeInMillis(calendar.getTimeInMillis() + 86_400_000L)` cộng **chính xác 24 giờ** theo epoch, không nhất thiết giữ cùng giờ đồng hồ địa phương vào hôm sau.

Nếu yêu cầu là "ngày mai lúc 12:00 tại một khu vực", hãy cộng **ngày** theo múi giờ; nếu là "sau 24 giờ", hãy cộng **Duration** hoặc mili-giây. Hai yêu cầu này khác nhau.

## 7. DST: cộng một ngày không phải lúc nào cũng bằng 24 giờ

Múi giờ chứa **quy tắc dịch chuyển giờ mùa hè (daylight saving time)** có thể khiến một ngày lịch dài 23 hoặc 25 giờ thực. Ví dụ tại `America/New_York`, chuyển sang giờ mùa hè năm 2026 xảy ra trong tháng Ba.

Bắt đầu từ **12:00 ngày 7/3/2026** rồi cộng một ngày lịch, cùng 12:00 ngày 8/3/2026 chỉ cách nhau **23 giờ thực**, vì offset UTC thay đổi từ `-05:00` sang `-04:00`.

Tạo `CalendarDstDemo.java`:

```java
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.util.Calendar;
import java.util.GregorianCalendar;
import java.util.Locale;
import java.util.TimeZone;

public class CalendarDstDemo {
    public static void main(String[] args) {
        ZoneId zoneId = ZoneId.of("America/New_York");
        Calendar calendar = new GregorianCalendar(
                TimeZone.getTimeZone(zoneId), Locale.US);
        calendar.clear();
        calendar.setLenient(false);
        calendar.set(2026, Calendar.MARCH, 7, 12, 0, 0);

        long start = calendar.getTimeInMillis();
        calendar.add(Calendar.DAY_OF_MONTH, 1);
        long end = calendar.getTimeInMillis();

        System.out.println("start: "
                + Instant.ofEpochMilli(start).atZone(zoneId));
        System.out.println("end: "
                + Instant.ofEpochMilli(end).atZone(zoneId));
        System.out.println("elapsed hours: "
                + Duration.ofMillis(end - start).toHours());
    }
}
```

```bash
javac CalendarDstDemo.java
java CalendarDstDemo
```

```text
start: 2026-03-07T12:00-05:00[America/New_York]
end: 2026-03-08T12:00-04:00[America/New_York]
elapsed hours: 23
```

Đây là kết quả theo dữ liệu múi giờ tzdb cho năm 2026. Quy tắc DST có thể thay đổi theo pháp luật và phiên bản tzdb, vì vậy khi hệ thống xử lý lịch hẹn tương lai cần quản lý phiên bản timezone data phù hợp và kiểm thử theo vùng đích.

### Offset UTC không phải ID vùng giờ

- `-05:00` và `-04:00` chỉ là **offset** tại từng thời điểm.
- `America/New_York` là **ZoneId** có quy tắc về offset theo thời gian.
- `TimeZone.getRawOffset()` thể hiện phần offset cơ bản, **không đủ** để suy offset hiệu lực ở một instant khi có DST; có thể lấy `getOffset(long epochMillis)` hoặc dùng `ZoneId.getRules().getOffset(instant)`.
- Đừng xây timestamp bằng cách cộng thủ công một offset "cố định cả năm" nếu vùng có DST.

`java.time` có các thao tác khác nhau: `zoned.plusDays(1)` theo ngày lịch địa phương và `instant.plus(Duration.ofHours(24))` theo khoảng thời gian tuyệt đối. Chọn đúng ngữ nghĩa nghiệp vụ.

## 8. Rủi ro đổi `TimeZone` mặc định theo từng request

Một hệ thống đa người dùng có thể xử lý hai yêu cầu song song:

1. A chọn `UTC`, code gọi `TimeZone.setDefault(UTC)`.
2. A chưa kịp dựng `Calendar` hoặc formatter, luồng B đặt `TimeZone.setDefault(Asia/Tokyo)`.
3. A tiếp tục đọc `TimeZone.getDefault()` hoặc `Calendar.getInstance()` và nhận `Asia/Tokyo`, trái với lựa chọn của A.

Đây là race condition trên **trạng thái toàn cục**, không chỉ là lỗi thứ tự dòng code. Không thể giải quyết bằng cách gọi `setDefault` rồi khôi phục trong `finally` của từng request: hai request vẫn có thể xen giữa chúng.

### Ví dụ Java 17+ có thứ tự rõ ràng

File `DefaultZoneRaceDemo.java`:

```java
import java.util.TimeZone;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

public class DefaultZoneRaceDemo {
    public static void main(String[] args)
            throws InterruptedException {
        TimeZone before = TimeZone.getDefault();

        CountDownLatch aHasSet = new CountDownLatch(1);
        CountDownLatch bHasSet = new CountDownLatch(1);
        AtomicReference<String> aObserved = new AtomicReference<>();

        Thread a = new Thread(() -> {
            TimeZone.setDefault(TimeZone.getTimeZone("UTC"));
            aHasSet.countDown();
            try {
                bHasSet.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }
            aObserved.set(TimeZone.getDefault().getID());
        });

        Thread b = new Thread(() -> {
            try {
                aHasSet.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }
            TimeZone.setDefault(
                    TimeZone.getTimeZone("Asia/Tokyo"));
            bHasSet.countDown();
        });

        try {
            a.start();
            b.start();
            a.join();
            b.join();
            System.out.println("A expected UTC but read "
                    + aObserved.get());
        } finally {
            TimeZone.setDefault(before);
        }
    }
}
```

```bash
javac DefaultZoneRaceDemo.java
java DefaultZoneRaceDemo
```

```text
A expected UTC but read Asia/Tokyo
```

`CountDownLatch` buộc luồng B thay default sau A nhưng trước khi A đọc. Đây là **thí nghiệm tái hiện rủi ro**, không phải phương pháp sử dụng trong server. Khôi phục trong `finally` chỉ nhằm không để test thử nghiệm làm thay đổi cấu hình mặc định của tiến trình sau khi hai thread đã kết thúc. Không chạy thí nghiệm này cùng các tác vụ khác phụ thuộc JVM default.

## 9. Phương pháp đúng với API cũ: truyền `TimeZone` và `Locale`

Nếu dự án buộc phải sử dụng `Calendar`, hãy truyền cấu hình rõ ràng:

```java
TimeZone userZone = TimeZone.getTimeZone("Asia/Ho_Chi_Minh");
Locale userLocale = Locale.forLanguageTag("vi-VN");

Calendar calendar = Calendar.getInstance(
        userZone, userLocale);
calendar.setTimeInMillis(epochMillis);
```

Đây là **đoạn minh họa trong phương thức**, cần `import java.util.*;` và biến `epochMillis` có giá trị từ nguồn dữ liệu. Lưu ý:

- `userZone` nên lấy từ preference được xác thực hoặc dữ liệu nghiệp vụ, không suy từ `userLocale`.
- `epochMillis` đại diện instant; date/time fields lấy theo `userZone`.
- Không tự đổi `TimeZone.setDefault(...)` hoặc `Locale.setDefault(...)` khi tiếp nhận yêu cầu.
- `Calendar` là mutable và **không thread-safe**; không dùng chung một đối tượng `Calendar` giữa các request đồng thời.
- `DateFormat`/`SimpleDateFormat` cũng mutable, không thread-safe. Với code legacy, tạo formatter riêng và gọi `setTimeZone(userZone)` nếu API/kiểu format yêu cầu, thay vì dùng default.

### `TimeZone.getTimeZone(String)` có thể âm thầm fallback

`TimeZone.getTimeZone("Not/A_Zone")` có thể trả **`GMT`** thay vì ném ngoại lệ. Nếu vùng được gửi từ client không hợp lệ, việc tiếp tục dùng `GMT` sẽ làm thời gian hiển thị sai mà không thấy lỗi.

Tạo `ZoneValidationDemo.java`:

```java
import java.time.DateTimeException;
import java.time.ZoneId;
import java.util.TimeZone;

public class ZoneValidationDemo {
    public static void main(String[] args) {
        System.out.println("legacy: "
                + TimeZone.getTimeZone("Not/A_Zone").getID());

        try {
            ZoneId.of("Not/A_Zone");
            System.out.println("accepted");
        } catch (DateTimeException ex) {
            System.out.println("invalid ZoneId rejected");
        }

        ZoneId accepted = ZoneId.of("Asia/Ho_Chi_Minh");
        TimeZone legacy = TimeZone.getTimeZone(accepted);
        System.out.println("validated: " + legacy.getID());
    }
}
```

```bash
javac ZoneValidationDemo.java
java ZoneValidationDemo
```

```text
legacy: GMT
invalid ZoneId rejected
validated: Asia/Ho_Chi_Minh
```

**Khuyến nghị:** với vùng nhận từ bên ngoài, kiểm tra bằng `ZoneId.of(...)` (có thể kết hợp danh sách vùng được phép), sau đó chuyển sang `TimeZone.getTimeZone(zoneId)` khi cần gọi API cũ. Đừng xác minh vùng chỉ bằng cách so `getTimeZone(id).getID()` với input vì alias/ID chuẩn hóa cũng có thể ảnh hưởng hành vi.

## 10. Các mặc định còn ảnh hưởng đến formatter

Trong API ngày giờ cũ, `java.text.DateFormat` và `java.text.SimpleDateFormat` có thể phụ thuộc **locale, timezone và pattern**.

Ví dụ:

```java
DateFormat df = DateFormat.getDateTimeInstance(
        DateFormat.MEDIUM, DateFormat.SHORT, userLocale);
df.setTimeZone(userZone);
String text = df.format(date);
```

Đây là **đoạn mã trong phương thức** với các import phù hợp, biến `date` là `java.util.Date` và `userLocale/userZone` đã được khai báo. `DateFormat` được tạo theo locale được truyền, rồi đặt time zone rõ ràng trước khi format. Nếu bạn chỉ gọi `DateFormat.getDateTimeInstance()` không tham số, code phụ thuộc default locale và default time zone tại lúc formatter được dựng.

Điều cần tránh:

```java
// Không phù hợp cho ứng dụng phục vụ nhiều múi giờ:
TimeZone.setDefault(userZone);
Locale.setDefault(userLocale);
String text = DateFormat.getDateTimeInstance().format(date);
```

Mặc dù đôi khi in đúng trong chương trình một người dùng, cách này thay trạng thái JVM và có thể làm request khác sai.

Một bẫy khác của `SimpleDateFormat` là pattern và `Calendar` nội bộ có thể bị thay đổi khi parse/format; class không thread-safe. Không tạo một instance `static` để đồng thời phục vụ mọi request. Với code mới, ưu tiên `java.time.format.DateTimeFormatter` vì immutable và thread-safe sau khi tạo.

## 11. `GregorianCalendar` và khái niệm lịch mặc định

Không phải mọi `Calendar.getInstance(...)` luôn tạo đúng một kiểu `GregorianCalendar` cho mọi locale. Dựa trên provider, locale và Unicode extension liên quan đến calendar (`u-ca-*`), runtime có thể chọn hệ lịch khác, ví dụ Buddhist/Japanese calendar. Vì vậy:

- Nếu dữ liệu nghiệp vụ giả định **lịch Gregorian/ISO**, hãy khai báo rõ hệ lịch hoặc chuyển sang `java.time.LocalDate`/`LocalDateTime`.
- Đừng mặc định `Calendar.YEAR` luôn có cùng ý nghĩa biên niên trong mọi lịch.
- `GregorianCalendar` legacy có cơ chế cutover lịch Julian/Gregorian; điều này có thể ảnh hưởng dữ liệu lịch sử, khác với ISO proleptic Gregorian của `java.time.LocalDate`.
- Week-of-year cũng chịu cấu hình locale (`getFirstDayOfWeek`, `getMinimalDaysInFirstWeek`), nên đừng dùng `Calendar.WEEK_OF_YEAR` như một "week index chuẩn toàn cầu" mà không định nghĩa chuẩn.

Với báo cáo theo tuần ISO 8601, Java Time có `java.time.temporal.IsoFields.WEEK_OF_WEEK_BASED_YEAR` và `WEEK_BASED_YEAR`; với tuần theo locale, có `WeekFields.of(locale)`. Cách tính tuần và hiển thị lịch cần thống nhất trước khi triển khai.

## 12. Chuyển từ API cũ sang `java.time`

Java 8+ cung cấp nhóm `java.time` với đối tượng bất biến và phân biệt mục đích rõ hơn:

| API legacy | Lựa chọn Java Time | Lưu ý chuyển đổi |
| --- | --- | --- |
| `Date` | `Instant` | `date.toInstant()`, nhưng độ chính xác của `Date` là mili-giây |
| `TimeZone` | `ZoneId` | `timeZone.toZoneId()` và `TimeZone.getTimeZone(zoneId)` |
| `Calendar` tại một thời điểm | `Instant` + `ZoneId` hoặc `ZonedDateTime` | Phân biệt instant và các trường địa phương |
| `GregorianCalendar` | `ZonedDateTime`, `LocalDateTime`, `LocalDate` tùy ngữ nghĩa | Không phải chuyển trường 1:1 cho mọi loại lịch |
| `SimpleDateFormat` | `DateTimeFormatter` | Pattern gần giống nhưng không hoàn toàn tương thích; kiểm tra từng token |
| `Calendar.getInstance()` | `ZonedDateTime.now(zoneId)` hoặc `Instant.now()` | Truyền zone tường minh khi cần local date/time |

Một ví dụ Java Time thuần:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class ModernTimeDemo {
    public static void main(String[] args) {
        Instant instant = Instant.parse("2026-01-01T00:30:00Z");
        ZoneId zone = ZoneId.of("Asia/Tokyo");
        ZonedDateTime local = instant.atZone(zone);

        System.out.println("instant: " + instant);
        System.out.println("local: " + local);
    }
}
```

```bash
javac ModernTimeDemo.java
java ModernTimeDemo
```

```text
instant: 2026-01-01T00:30:00Z
local: 2026-01-01T09:30+09:00[Asia/Tokyo]
```

Lưu ý chuyển đổi:

- Để lưu timestamp sự kiện, `Instant` thường rõ ràng hơn. Nếu người dùng cần lưu một **lịch hẹn tương lai lúc 09:00 theo vùng**, mô hình có thể cần `LocalDateTime + ZoneId` và chính sách xử lý DST.
- `LocalDateTime` không mang time zone nên không tự xác định một instant.
- Khi dữ liệu cũ chứa `Calendar` của hệ lịch không phải Gregorian, không tự giả định chuyển `YEAR/MONTH/DAY_OF_MONTH` trực tiếp thành `LocalDate` mà không biết chronology.
- `DateTimeFormatter` immutable và thread-safe; vẫn cần truyền `Locale` trong `withLocale(locale)` và `ZoneId` phù hợp trong `withZone(zoneId)` khi format `Instant` hay dữ liệu yêu cầu zone.

## 13. Thiết kế đa người dùng: tách state theo request

Luồng triển khai phù hợp:

```text
Request / user profile
       |
       +--> locale hiển thị (vi-VN / en-US / ...)
       |
       +--> zone ID (Asia/Ho_Chi_Minh / America/New_York / ...)
       |
       v
Kiểm tra danh sách hỗ trợ, xác định chính sách thời gian
       |
       +--> Instant hoặc dữ liệu domain time
       |
       +--> Locale / ZoneId truyền tường minh
       |
       v
Formatter, Calendar legacy adapter hoặc java.time
       |
       v
Response cho đúng người dùng
```

**Không đồng nhất các nguồn thông tin:**

- `Accept-Language` không xác định múi giờ.
- `TimeZone.getDefault()` không xác định nơi người dùng đang sống.
- `Locale.getDefault()` không xác định preference của request.
- Ngày giờ gửi từ client không có offset/zone cần được xử lý theo hợp đồng cụ thể, không tự gán vùng của server.

Nếu phải giữ adapter legacy, có thể tạo `Calendar`/`DateFormat` ngắn hạn cho từng thao tác từ `Locale` và `TimeZone` đã được chọn. Đừng truyền một `Calendar` mutable giữa các thread; đừng thay default JVM như cơ chế truyền context.

**Kiểm thử đa vùng:** chọn một instant gần nửa đêm UTC, ngày chuyển DST, ngày cuối năm và trường hợp cùng giờ địa phương không duy nhất. Kiểm tra output dựa trên `Instant` và `ZoneId` cụ thể, thay vì phụ thuộc môi trường máy chạy CI.

## 14. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| `Calendar.getInstance()` rồi coi là calendar của user | Lấy default JVM | Truyền zone/locale riêng |
| `TimeZone.setDefault(userZone)` cho mỗi request | Race condition giữa các user | Dùng `Calendar.getInstance(zone, locale)` hoặc `java.time` |
| `Locale.setDefault(userLocale)` cho mỗi request | Thay cấu hình chung, ảnh hưởng week/formatter | Truyền `Locale` tường minh |
| Suy múi giờ từ `Locale("vi","VN")` | Locale không xác định zone của người dùng | Dùng preference/ZoneId |
| Dùng `Calendar.set(2026, 3, 1)` để biểu diễn ngày 1/3 | `MONTH=3` là tháng Tư | Dùng `Calendar.MARCH` hoặc `LocalDate.of(2026,3,1)` |
| Đọc `Calendar.HOUR` rồi nghĩ là 0–23 | Đây là giờ 12h | Dùng `HOUR_OF_DAY` |
| Đặt 30/2 với lenient mặc định | Bị chuẩn hóa sang tháng khác | `setLenient(false)` và validation |
| Dùng `roll` để cộng ngày qua tháng | Trường lớn hơn không đổi như mong muốn | Dùng `add` hoặc Java Time |
| Cộng `24*60*60*1000` để "sang ngày mai" | Sai ở ngày DST 23/25 giờ | Cộng ngày theo vùng giờ |
| Lấy `getRawOffset()` thay offset tại instant | Bỏ qua DST | `getOffset(millis)`/ZoneRules |
| Dùng `TimeZone.getTimeZone(invalidId)` mà không kiểm tra | Âm thầm trả `GMT` | Validate `ZoneId.of(...)` |
| Dùng chung `SimpleDateFormat`/`Calendar` mutable | Không thread-safe | Instance riêng hoặc `java.time` |
| Chuyển `Date` thành chuỗi để lưu instant | Phụ thuộc formatter/locale/zone | Lưu epoch/ISO timestamp theo schema |
| Trộn các quy tắc tuần theo US và ISO | Week number sai gần giao năm | Xác định WeekFields/IsoFields |
| Thay default trong test chạy song song | Gây test ngẫu nhiên thất bại | Cô lập test/JVM hoặc không thay default |

## 15. Câu hỏi tự kiểm tra

1. **`Calendar.getInstance()` lấy time zone và locale từ đâu?** Từ mặc định JVM: `TimeZone.getDefault()` và locale FORMAT mặc định, không tự lấy từ HTTP request.
2. **`TimeZone.setDefault(...)` có áp dụng riêng cho một thread không?** Không, nó thay mặc định dùng chung của JVM.
3. **Nếu một calendar đã được tạo với UTC, sau đó đổi JVM default sang Tokyo thì calendar cũ có tự chuyển sang Tokyo không?** Không mặc định; time zone của instance đã được lưu.
4. **Tại sao `Calendar.MONTH` bằng 2 lại biểu diễn tháng Ba?** Vì chỉ số tháng trong `Calendar` bắt đầu từ 0.
5. **`Locale.US` và `Locale.FRANCE` có thể cho `getFirstDayOfWeek` khác nhau không?** Có: thông thường Chủ nhật = 1 và thứ Hai = 2.
6. **Vì sao 30/2/2026 có thể thành 2/3/2026?** Do `Calendar` lenient chuẩn hóa trường vượt miền.
7. **`add(DAY_OF_MONTH, 1)` có bằng cộng 86.400.000 mili-giây không?** Không nhất thiết, vì ngày DST có thể dài 23/25 giờ.
8. **`TimeZone.getRawOffset()` có luôn là offset hiệu lực của một vùng tại mọi thời điểm không?** Không, phải xét DST và lịch sử.
9. **`TimeZone.getTimeZone("Not/A_Zone")` có bắt buộc ném lỗi không?** Không; thường trả `GMT`, nên phải validate nguồn.
10. **`Locale.forLanguageTag("en-US")` có đủ để xác định vùng `America/New_York` không?** Không, locale và time zone là hai lựa chọn độc lập.
11. **Lưu `LocalDateTime` có đủ biểu diễn một instant tuyệt đối không?** Không, thiếu offset/zone.
12. **API mới nào nên ưu tiên cho code Java 17+?** `java.time.Instant`, `ZoneId`, `ZonedDateTime`, `LocalDate/LocalDateTime` và `DateTimeFormatter` theo ngữ nghĩa.
13. **Khi nào dùng `Calendar`?** Khi tích hợp hệ thống legacy hoặc API buộc dùng nó; truyền time zone/locale tường minh và cô lập đối tượng mutable.
14. **Cách kiểm thử không phụ thuộc timezone máy CI?** Dùng instant cố định và zone/locale tường minh, không dựa vào default của môi trường.

## Tài liệu tham khảo

- [Java SE 21 — Calendar](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Calendar.html): `getInstance`, lenient, add/roll, week fields và phạm vi các trường.
- [Java SE 21 — TimeZone](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TimeZone.html): `getDefault`, `setDefault`, `getOffset` và cách tìm ID.
- [Java SE 21 — GregorianCalendar](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/GregorianCalendar.html): lịch Gregory legacy, cutover và chuyển đổi.
- [Java SE 21 — Locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html): `Category.FORMAT`/`DISPLAY` và locale mặc định.
- [Java SE 21 — DateFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DateFormat.html): phụ thuộc locale/time zone của formatter cũ.
- [Java SE 21 — ZoneId](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZoneId.html): validate vùng IANA, quy tắc time zone.
- [Java SE 21 — ZonedDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html): zone, offset, DST, phép cộng ngày và giờ.
- [Java SE 21 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html): format/parse immutable với locale/zone tường minh.
