# Giới hạn toInstant() trên java.sql.Date và java.sql.Time

## 1. Cùng kế thừa Date nhưng không cùng hợp đồng thời gian

`java.util.Date` thuần biểu diễn một thời điểm và có thể chuyển sang `Instant` bằng `toInstant()`. Tuy nhiên, hai kiểu legacy của JDBC là `java.sql.Date` và `java.sql.Time` ghi đè phương thức này với hợp đồng khác:

| Kiểu thực tế | Ý nghĩa chính | toInstant() |
|---|---|---|
| `java.util.Date` thuần | Một thời điểm ở độ chính xác mili giây | Chuyển được |
| `java.sql.Date` | Ngày theo nghĩa SQL DATE, không có phần giờ nghiệp vụ | Luôn ném `UnsupportedOperationException` |
| `java.sql.Time` | Giờ theo nghĩa SQL TIME của lớp legacy, không có ngày nghiệp vụ | Luôn ném `UnsupportedOperationException` |

Đây là hành vi được công bố của API, không phải lỗi ngẫu nhiên của một bản driver hay một múi giờ đặc biệt.

Nguyên nhân thuộc về ý nghĩa dữ liệu: một ngày đơn lẻ hoặc một giờ đơn lẻ chưa đủ xác định một thời điểm duy nhất. Việc các lớp có biểu diễn mili giây kế thừa từ Date không tự bổ sung phần thông tin nghiệp vụ đang thiếu.

## 2. Kiểu tham chiếu cha không làm đổi đối tượng thực tế

Đoạn minh họa:

```java
java.sql.Date sqlDate = java.sql.Date.valueOf("2026-10-25");
java.util.Date value = sqlDate;
value.toInstant(); // UnsupportedOperationException.
```

Gán vào biến `java.util.Date` chỉ đổi kiểu tham chiếu được khai báo, không tạo một đối tượng Date thuần mới. Lời gọi phương thức vẫn được điều phối theo kiểu thực tế và chạy phiên bản bị ghi đè của `java.sql.Date`.

Một hàm tiện ích nhận `java.util.Date` rồi gọi `toInstant()` vì vậy không an toàn về hợp đồng nếu nơi gọi có thể truyền SQL Date hoặc Time vào. Compiler có thể cho phép lời gọi, nhưng hành vi lúc chạy còn phụ thuộc đối tượng được nhận.

Không chữa bằng cách ép kiểu sang `java.util.Date` lần nữa. Phép cast không thay dữ liệu hoặc loại bỏ phương thức ghi đè. Cần xác định ý nghĩa cột và chọn phép chuyển tương ứng.

## 3. Chuyển đúng sang kiểu thành phần của java.time

Các phép chuyển thường phù hợp:

```java
LocalDate date = sqlDate.toLocalDate();
LocalTime time = sqlTime.toLocalTime();
```

Chiều ngược lại:

```java
java.sql.Date sqlDate = java.sql.Date.valueOf(date);
java.sql.Time sqlTime = java.sql.Time.valueOf(time);
```

Đây là các đoạn minh họa trong ngữ cảnh có biến đầu vào hợp lệ; chương trình độc lập ở phần 6 có đầy đủ khai báo.

`toLocalDate()` giữ năm-tháng-ngày theo hợp đồng của SQL Date. `toLocalTime()` giữ giờ-phút-giây theo hợp đồng của SQL Time legacy. Chúng không tự tạo giờ hoặc ngày bị thiếu và không tự gắn một múi giờ cho nghiệp vụ.

Dùng đầy đủ tên `java.sql.Date` trong mã ranh giới khi dễ nhầm với `java.util.Date`. Hai lớp cùng tên ngắn không có nghĩa là mọi phép chuyển có thể dùng thay nhau.

### Lưu ý phần lẻ của SQL Time legacy

`java.sql.Time.valueOf(LocalTime)` lấy giờ, phút, giây; phần nano giây của LocalTime không được giữ qua phép chuyển đó. `toLocalTime()` của Time legacy cũng không phải lời hứa rằng mọi độ chính xác phần lẻ của một cột SQL TIME hiện đại đều được bảo toàn.

Nếu dữ liệu cần phần lẻ giây, hãy kiểm tra hỗ trợ và ánh xạ của driver/cột thực tế. Không đưa nó qua `java.sql.Time` rồi mặc định kết quả vẫn đầy đủ chỉ vì LocalTime ở đầu vào hỗ trợ nano giây.

## 4. Muốn tạo Instant phải thêm ngữ cảnh có chủ đích

### Từ SQL Date: cần chọn giờ và múi giờ

Nếu chức năng thật sự muốn thời điểm bắt đầu của một ngày tại một vùng, có thể viết:

```java
Instant start = sqlDate.toLocalDate()
        .atStartOfDay(businessZone)
        .toInstant();
```

`businessZone` phải là vùng đã được chức năng xác định. `atStartOfDay(zone)` chọn thời điểm đầu ngày hợp lệ theo quy tắc vùng; không được mặc định mọi ngày ở mọi vùng luôn có đúng 00:00 hợp lệ.

Lời gọi này thêm một quyết định “đầu ngày theo vùng X”. Nó không chứng minh SQL Date vốn đã chứa thời điểm đầu ngày đó. Nếu dữ liệu là ngày sinh hoặc ngày chứng từ không có giờ, giữ LocalDate thường đã đúng mục tiêu và không cần chuyển sang Instant.

### Từ SQL Time: cần thêm ngày và ngữ cảnh vùng

Nếu dữ liệu là giờ mở cửa, cần ngày cụ thể và vùng để tính một lần mở cửa:

```java
Instant opening = selectedDate.atTime(sqlTime.toLocalTime())
        .atZone(businessZone)
        .toInstant();
```

`selectedDate` không được lấy tùy ý từ ngày epoch hoặc “hôm nay” của máy nếu hợp đồng không yêu cầu. Một giờ như 09:15:30 có thể xảy ra ở vô số ngày; không có Instant duy nhất chỉ từ các trường giờ.

Ở vùng có DST, ngày-giờ địa phương còn có thể không tồn tại hoặc có hai offset hợp lệ. Khi chức năng cần kiểm tra nghiêm ngặt, phải chọn chính sách gap/overlap thay vì để một phép gắn vùng mặc định âm thầm quyết định mọi trường hợp.

Các bước trên là **xây dựng một thời điểm từ dữ liệu thành phần và chính sách bổ sung**, không phải mở khóa một `toInstant()` vốn bị vô hiệu hóa.

## 5. Vì sao dùng getTime để đi vòng không giải quyết ý nghĩa?

Có thể viết về mặt kỹ thuật:

```java
Instant raw = Instant.ofEpochMilli(sqlDate.getTime());
```

Lệnh này tạo Instant từ một số mili giây, nên không gọi phương thức `toInstant()` bị ghi đè. Nhưng nó đang dùng biểu diễn legacy của đối tượng, không tự chứng minh đó là thời điểm đúng mà nghiệp vụ cần.

Tương tự, tạo `new java.util.Date(sqlTime.getTime())` rồi gọi `toInstant()` có thể chạy được về mặt API, nhưng phần ngày gắn với Time không biến thành ngày nghiệp vụ chỉ vì đã đổi lớp bao.

Chỉ dùng một đường chuyển như vậy nếu hợp đồng nguồn thật sự xác định ý nghĩa thời điểm của số mili giây ấy và bạn chủ động cần nó. Đừng dùng như một cách chung để “né ngoại lệ” cho mọi SQL Date/Time.

Ngoại lệ ở đây giúp làm lộ khoảng trống của mô hình. Trả epoch, `null` hoặc một thời điểm được ghép ngầm khi bắt `UnsupportedOperationException` có thể che mất lỗi gọi sai API. Hãy sửa nơi chọn kiểu hoặc yêu cầu ngữ cảnh cần thiết thay vì tạo dữ liệu thay thế không có căn cứ.

## 6. Chương trình chạy đầy đủ

Lưu đoạn sau vào `SqlDateTimeInstantDemo.java`. Chương trình dùng Java 17 trở lên, không cần thư viện ngoài hoặc kết nối cơ sở dữ liệu.

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneId;

public class SqlDateTimeInstantDemo {
    private static void probe(String label, java.util.Date value) {
        try {
            System.out.println(label + "=" + value.toInstant());
        } catch (UnsupportedOperationException e) {
            System.out.println(label + "=UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        java.sql.Date sqlDate = java.sql.Date.valueOf("2026-10-25");
        java.sql.Time sqlTime = java.sql.Time.valueOf("09:15:30");

        probe("utilDate", new java.util.Date(0L));
        probe("sqlDate", sqlDate);
        probe("sqlTime", sqlTime);

        java.util.Date widenedDate = sqlDate;
        java.util.Date widenedTime = sqlTime;
        probe("sqlDateAsUtilDate", widenedDate);
        probe("sqlTimeAsUtilDate", widenedTime);

        LocalDate date = sqlDate.toLocalDate();
        LocalTime time = sqlTime.toLocalTime();
        System.out.println("localDate=" + date);
        System.out.println("localTime=" + time);
        System.out.println("dateRoundTrip="
                + date.equals(java.sql.Date.valueOf(date).toLocalDate()));
        System.out.println("timeRoundTrip="
                + time.equals(java.sql.Time.valueOf(time).toLocalTime()));

        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        Instant selectedDayStart = date.atStartOfDay(zone).toInstant();
        Instant chosenDateTime = date.atTime(time).atZone(zone).toInstant();
        System.out.println("selectedDayStart=" + selectedDayStart);
        System.out.println("chosenDateTime=" + chosenDateTime);

        LocalTime preciseTime = LocalTime.of(9, 15, 30, 123_456_789);
        java.sql.Time legacyTime = java.sql.Time.valueOf(preciseTime);
        System.out.println("originalNanos=" + preciseTime.getNano());
        System.out.println("afterTimeValueOfNanos="
                + legacyTime.toLocalTime().getNano());
    }
}
```

Biên dịch và chạy:

```shell
javac SqlDateTimeInstantDemo.java
java SqlDateTimeInstantDemo
```

Kết quả chuẩn:

```text
utilDate=1970-01-01T00:00:00Z
sqlDate=UnsupportedOperationException
sqlTime=UnsupportedOperationException
sqlDateAsUtilDate=UnsupportedOperationException
sqlTimeAsUtilDate=UnsupportedOperationException
localDate=2026-10-25
localTime=09:15:30
dateRoundTrip=true
timeRoundTrip=true
selectedDayStart=2026-10-24T17:00:00Z
chosenDateTime=2026-10-25T02:15:30Z
originalNanos=123456789
afterTimeValueOfNanos=0
```

Tên ngoại lệ là nhãn do chương trình in khi bắt lỗi, không phải thông điệp đầy đủ của JDK.

`probe` nhận kiểu cha `java.util.Date`, nhưng vẫn quan sát đúng hành vi theo đối tượng thực tế. Hai lời gán `widenedDate` và `widenedTime` không thay kết quả vì không hề tạo một đối tượng mới.

Hai dòng tạo Instant có ngữ cảnh rõ: ngày được chọn là 25/10/2026, vùng là Việt Nam, một trường hợp chọn đầu ngày và một trường hợp ghép giờ 09:15:30. Chênh lệch so với chuỗi ngày UTC là hệ quả của việc xác định thời điểm theo vùng, không phải một lỗi đổi ngày.

Các phép vòng chuyển Date/Time trong chương trình chỉ kiểm tra dữ liệu ở mức ngày và giờ nguyên giây đã chọn. Dòng cuối cho thấy phép vòng qua Time không giữ phần nano giây của LocalTime nguồn.

## 7. Xử lý ở ranh giới JDBC

Nếu đã nhận `java.sql.Date` hoặc `java.sql.Time` từ mã JDBC legacy, chuyển sang kiểu thành phần đúng nghĩa càng gần ranh giới càng giúp giảm nhầm lẫn bên trong ứng dụng.

Ví dụ minh họa trong một phương thức có `ResultSet rs`:

```java
java.sql.Date rawDate = rs.getDate("business_date");
LocalDate businessDate = rawDate == null ? null : rawDate.toLocalDate();

java.sql.Time rawTime = rs.getTime("opening_time");
LocalTime openingTime = rawTime == null ? null : rawTime.toLocalTime();
```

`null` trong ví dụ biểu diễn SQL NULL theo hợp đồng dữ liệu đang xử lý; không tự thay bằng epoch hoặc nửa đêm. Nếu trường bắt buộc, kiểm tra và báo thiếu dữ liệu ở lớp phù hợp.

Với driver và phiên bản JDBC hỗ trợ kiểu `java.time`, có thể dùng cách lấy/gán kiểu trực tiếp phù hợp với cột. Tuy nhiên vẫn cần kiểm tra ánh xạ, độ chính xác và múi giờ session/driver bằng phép ghi-đọc qua hệ thống thật. Bài này chỉ minh chứng hành vi của các lớp Java; nó không kiểm chứng một database, ORM hoặc driver cụ thể.

Đừng tạo một bộ chuyển tổng quát chỉ dựa vào `instanceof java.util.Date` rồi coi mọi kiểu con là timestamp. Phải chọn theo ý nghĩa cột và hợp đồng API. Một cấu trúc đầu ra có thể chứa LocalDate cho trường ngày và LocalTime cho trường giờ, thay vì ép mọi thứ về Instant để đồng nhất hình thức.

## 8. Không suy rộng sang Timestamp

`java.sql.Timestamp` là một kiểu legacy khác, có phần nano giây và có hành vi `toInstant()` riêng. Việc Date và Time luôn từ chối không chứng minh Timestamp cũng từ chối.

Ngược lại, Timestamp chuyển được sang Instant về mặt API cũng không tự xác nhận một cột cơ sở dữ liệu vốn là thời điểm toàn cục. Một cột ngày-giờ không vùng vẫn cần được diễn giải đúng theo hợp đồng driver/ứng dụng. Cần tách **API cho phép chuyển** khỏi **dữ liệu có ý nghĩa thời điểm nào**.

Các lớp SQL legacy còn kế thừa tính có thể thay đổi từ Date. Chuyển sang LocalDate/LocalTime bất biến giúp cô lập trạng thái bên trong phần xử lý mới, nhưng không thay thế kiểm tra đầu vào đang bị nơi khác sửa hoặc dữ liệu đã được driver diễn giải trước đó.

## 9. Tự thực hành

1. Viết một hàm nhận `java.util.Date` và thử với Date thuần, SQL Date, SQL Time. Giải thích hành vi từng trường hợp bằng kiểu thực tế thay vì kiểu tham số.
2. Đổi múi giờ bổ sung trong phần tạo Instant sang UTC. Ngày/giờ thành phần giữ nguyên, nhưng Instant được tạo thay đổi; xác định đây là thay đổi quyết định nghiệp vụ, không phải phép sửa lỗi `toInstant()`.
3. Đưa `LocalTime` có phần lẻ vào `Time.valueOf`, rồi so sánh trước/sau. Chọn cách ánh xạ phù hợp nếu hợp đồng cần giữ độ chính xác ấy.
4. Cho một cột “ngày sinh”. Chỉ ra phép chuyển đúng tới LocalDate và vì sao không cần chọn một múi giờ để tự tạo Instant.

Tham khảo: [java.sql.Date — toInstant và toLocalDate](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Date.html) và [java.sql.Time — toInstant, toLocalTime và valueOf](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Time.html) trong Java SE 21.
