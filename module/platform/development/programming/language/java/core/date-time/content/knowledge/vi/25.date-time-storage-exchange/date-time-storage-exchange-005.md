# java.sql.Date với LocalDate và java.sql.Time với LocalTime

## 1. Hai cặp kiểu cùng ý nghĩa, khác thế hệ API

Khi làm việc với JDBC, ta có thể gặp hai lớp cũ `java.sql.Date` và `java.sql.Time`. Chúng phục vụ việc ánh xạ kiểu dữ liệu SQL qua JDBC, còn mã nghiệp vụ hiện đại thường phù hợp hơn với các kiểu `java.time`.

| Ý nghĩa cần biểu diễn | Kiểu Java hiện đại | Lớp cầu nối JDBC cũ |
| --- | --- | --- |
| Một ngày gồm năm, tháng, ngày | `LocalDate` | `java.sql.Date` |
| Một giờ trong ngày, không gắn ngày hoặc offset | `LocalTime` | `java.sql.Time` |

Ví dụ ngày sinh hoặc ngày nghiệp vụ có thể dùng `LocalDate`. Giờ mở cửa hằng ngày có thể dùng `LocalTime`. Cả hai đều chưa phải một thời điểm duy nhất trên dòng thời gian.

Không nhầm `java.sql.Date` với `java.util.Date`:

- `java.util.Date` thường được dùng như biểu diễn một thời điểm dựa trên mili giây.
- `java.sql.Date` được JDBC dùng cho giá trị ngày kiểu `DATE`.
- `java.sql.Time` được JDBC dùng cho giá trị giờ kiểu `TIME`.
- Hai lớp SQL kế thừa `java.util.Date` vì lịch sử thiết kế, nhưng không có nghĩa chúng có đầy đủ cùng ngữ nghĩa sử dụng.

Ánh xạ trong bài nói về ý nghĩa kiểu JDBC `DATE` và `TIME`. Khi áp dụng cho một DBMS cụ thể, vẫn cần kiểm tra kiểu cột, độ chính xác và hành vi của driver; không chỉ nhìn một tên kiểu SQL rồi suy đoán mọi đặc điểm lưu trữ.

## 2. Chuyển java.sql.Date và LocalDate

Hai phương thức trực tiếp:

```java
LocalDate local = LocalDate.of(2024, 2, 29);

java.sql.Date sql = java.sql.Date.valueOf(local);
LocalDate restored = sql.toLocalDate();
```

Theo [java.sql.Date](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Date.html), `valueOf(LocalDate)` tạo giá trị SQL có cùng năm, tháng và ngày. `toLocalDate()` lấy các thành phần ngày để tạo `LocalDate`.

Đây là chuyển đổi theo ý nghĩa **ngày trên lịch**, không phải thao tác “đổi thời điểm sang UTC”. Không cần đi vòng qua `Instant` chỉ để chuyển hai kiểu ngày này.

Các tên phương thức dễ gây nhầm:

| Lời gọi | Ý nghĩa |
| --- | --- |
| `java.sql.Date.valueOf(localDate)` | Tạo lớp ngày JDBC từ `LocalDate` |
| `sqlDate.toLocalDate()` | Đọc lại ngày bằng API hiện đại |
| `java.util.Date.from(instant)` | Tạo lớp cũ cho một thời điểm; không phải ánh xạ ngày thuần |
| `sqlDate.toInstant()` | Không được hỗ trợ |

`java.sql.Date` là lớp cũ có thể bị sửa bằng các phương thức như `setTime`. `LocalDate` bất biến. Việc chuyển sang `LocalDate` ở biên đọc dữ liệu giúp phần nghiệp vụ không giữ một đối tượng SQL có thể thay đổi ngoài ý muốn.

### 2.1. Không dùng constructor cũ với năm và tháng lệch quy ước

Constructor nhiều thành phần của `java.sql.Date` đã bị đánh dấu deprecated và dùng các quy ước cũ như năm trừ 1900, tháng bắt đầu từ 0. Dễ nhầm với `LocalDate.of` dùng năm thực và tháng `1..12`.

Dùng `Date.valueOf(localDate)` thay cho việc tự trừ 1900 hoặc trừ 1. Khi chuyển từ dữ liệu văn bản, hãy phân tích thành `LocalDate` theo hợp đồng đã chọn rồi mới tạo lớp JDBC nếu cần.

### 2.2. Không lấy getTime() làm bản chất nghiệp vụ của ngày

Lớp SQL cũ vẫn bọc giá trị mili giây và sử dụng các quy tắc diễn giải của API cũ. Giá trị mili giây đó không phải hợp đồng thích hợp để trao đổi “ngày sinh 29/02/2024” giữa các vùng.

Không dùng chuỗi thao tác sau như một công thức mặc định:

```java
// Minh hoa cach lam khong phu hop cho ngay thuan:
// Instant.ofEpochMilli(sqlDate.getTime())
//        .atZone(ZoneId.of("UTC"))
//        .toLocalDate();
```

Cách diễn giải mili giây theo UTC có thể đổi ngày so với ngữ cảnh dùng khi lớp cũ được tạo. Khi đầu vào thật sự là `java.sql.Date` mang ngày JDBC, dùng `toLocalDate()` theo mục đích API.

Các lớp cũ có thể phụ thuộc môi trường múi giờ khi xây dựng và đọc thành phần. Đừng thay đổi múi giờ mặc định giữa các bước chuyển đổi rồi mong mọi đối tượng cũ tiếp tục giữ cùng cách diễn giải. Trong tích hợp thực tế, cần thống nhất cấu hình driver/môi trường và kiểm chứng ngày đọc–ghi, đặc biệt gần các ranh giới.

## 3. Chuyển java.sql.Time và LocalTime

Hai phương thức đối xứng về hình thức:

```java
LocalTime local = LocalTime.of(12, 34, 56);

java.sql.Time sql = java.sql.Time.valueOf(local);
LocalTime restored = sql.toLocalTime();
```

Nhưng có một giới hạn quan trọng: [java.sql.Time](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Time.html) chỉ giữ các thành phần giờ, phút và giây qua cặp `valueOf(LocalTime)`/`toLocalTime()`. Phần nano giây của `LocalTime` bị bỏ khi đi qua cầu nối này.

Ví dụ:

```java
LocalTime precise = LocalTime.of(12, 34, 56, 123_456_789);
java.sql.Time sql = java.sql.Time.valueOf(precise);
LocalTime restored = sql.toLocalTime();
```

Giá trị ban đầu là `12:34:56.123456789`; kết quả quay lại là `12:34:56`, với `getNano() == 0`. Thông tin đã mất không thể được khôi phục từ chính `java.sql.Time` đó.

Đây không chỉ là vấn đề `toString()` giấu phần giây lẻ. So sánh `precise.equals(restored)` trả `false`: giá trị thời gian đã khác thật.

### 3.1. Chọn chính sách cho phần giây lẻ

Có ba hướng thường gặp:

| Chính sách | Khi phù hợp |
| --- | --- |
| Từ chối nếu `getNano() != 0` | Hợp đồng chỉ cho phép giờ chính xác đến giây và không muốn cắt ngầm |
| Chủ động bỏ phần giây lẻ | Nghiệp vụ đã chấp nhận độ chính xác đến giây |
| Tránh cầu nối `java.sql.Time`, dùng ánh xạ hiện đại phù hợp | Cần giữ phần giây lẻ và driver/cột hỗ trợ |

Nếu chọn bỏ phần giây lẻ, viết rõ `localTime.withNano(0)` hoặc `truncatedTo(ChronoUnit.SECONDS)` trước bước chuyển sẽ thể hiện quyết định đó. Đây là cắt phần lẻ, không phải làm tròn: `12:34:56.999` trở thành `12:34:56`, không thành `12:34:57`.

Nếu phải làm tròn theo quy tắc khác, cần nêu chính sách và xét trường hợp vượt sang ngày mới. `LocalTime` tự nó không chứa ngày để giữ thông tin tăng ngày.

### 3.2. SQL TIME không đồng nghĩa với Duration

`LocalTime` biểu diễn giờ trong một ngày. Nó không biểu diễn “mất 36 giờ xử lý” hay “chênh lệch âm 2 giờ”. Những đại lượng đó thuộc ý nghĩa thời lượng và thường cần `Duration` hoặc kiểu lưu trữ thích hợp khác.

Một DBMS có thể cho kiểu cột giờ những khả năng riêng. Việc tên cột là `TIME` chưa đủ để bảo đảm toàn bộ miền dữ liệu của cột đó ánh xạ đúng sang `LocalTime`. Kiểm tra hợp đồng kiểu trước khi chọn kiểu Java.

## 4. toInstant() trên hai lớp SQL luôn bị từ chối

Cả `java.sql.Date.toInstant()` và `java.sql.Time.toInstant()` đều ném `UnsupportedOperationException`:

- Ngày thuần chưa có giờ và vùng để xác định một thời điểm.
- Giờ thuần chưa có ngày và vùng để xác định một thời điểm.

Không nên dựa vào quan hệ kế thừa để gọi một tiện ích dành cho `java.util.Date` mà không biết lớp thực tế:

```java
java.util.Date reference = java.sql.Date.valueOf(
        LocalDate.of(2024, 2, 29));

// reference.toInstant() van goi phuong thuc cua java.sql.Date.
```

Tham chiếu có kiểu `java.util.Date` không thay đổi đối tượng thực bên dưới. Lời gọi vẫn bị từ chối.

Nếu nghiệp vụ cần biến một ngày thành mốc bắt đầu ngày, phải thêm chính sách rõ ràng, ví dụ `localDate.atStartOfDay(businessZone).toInstant()`. Đây là tạo một mốc theo quy tắc mới, không phải đọc một thời điểm đã có sẵn trong ngày thuần.

Bài này không dùng `Timestamp` để “vá” sự thiếu thông tin. Đổi sang một lớp có ngày giờ mà tự chèn ngày hoặc giờ giả sẽ làm sai ý nghĩa đầu vào nếu chưa có yêu cầu nghiệp vụ tương ứng.

## 5. Chương trình Java 17+ đầy đủ

Lưu thành `SqlDateTimeBridgeDemo.java`. Chương trình dùng thư viện chuẩn, không cần cơ sở dữ liệu hoặc driver ngoài.

```java
import java.sql.Time;
import java.time.LocalDate;
import java.time.LocalTime;

public class SqlDateTimeBridgeDemo {
    static java.sql.Date toSqlDate(LocalDate value) {
        return value == null ? null : java.sql.Date.valueOf(value);
    }

    static LocalDate fromSqlDate(java.sql.Date value) {
        return value == null ? null : value.toLocalDate();
    }

    static LocalTime fromSqlTime(Time value) {
        return value == null ? null : value.toLocalTime();
    }

    static Time toSqlTimeRejectFraction(LocalTime value) {
        if (value == null) {
            return null;
        }
        if (value.getNano() != 0) {
            throw new IllegalArgumentException("Fractional seconds rejected");
        }
        return Time.valueOf(value);
    }

    static void unsupported(String label, Runnable operation) {
        try {
            operation.run();
        } catch (UnsupportedOperationException ex) {
            System.out.println(label + " -> "
                    + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        LocalDate birthday = LocalDate.of(2024, 2, 29);
        java.sql.Date sqlDate = toSqlDate(birthday);
        LocalDate restoredDate = fromSqlDate(sqlDate);

        System.out.println("local date = " + birthday);
        System.out.println("SQL date = " + sqlDate);
        System.out.println("restored date = " + restoredDate);
        System.out.println("date equal = " + birthday.equals(restoredDate));

        LocalTime precise = LocalTime.of(12, 34, 56, 123_456_789);
        Time sqlTime = Time.valueOf(precise);
        LocalTime restoredTime = fromSqlTime(sqlTime);

        System.out.println("local time = " + precise);
        System.out.println("SQL time = " + sqlTime);
        System.out.println("restored time = " + restoredTime);
        System.out.println("restored nano = " + restoredTime.getNano());
        System.out.println("exact time equal = "
                + precise.equals(restoredTime));
        System.out.println("seconds equal = "
                + precise.withNano(0).equals(restoredTime));

        try {
            toSqlTimeRejectFraction(precise);
        } catch (IllegalArgumentException ex) {
            System.out.println("strict bridge = " + ex.getMessage());
        }

        Time wholeSecond = toSqlTimeRejectFraction(
                LocalTime.of(12, 34, 56));
        System.out.println("strict whole second = " + wholeSecond);
        System.out.println("null date preserved = "
                + (fromSqlDate(toSqlDate(null)) == null));
        System.out.println("null time preserved = "
                + (fromSqlTime(toSqlTimeRejectFraction(null)) == null));
        System.out.println("midnight preserved = "
                + Time.valueOf(LocalTime.MIDNIGHT).toLocalTime()
                        .equals(LocalTime.MIDNIGHT));

        unsupported("SQL date toInstant", () -> sqlDate.toInstant());
        unsupported("SQL time toInstant", () -> sqlTime.toInstant());

        java.util.Date baseReference = sqlDate;
        unsupported("base reference toInstant",
                () -> baseReference.toInstant());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 SqlDateTimeBridgeDemo.java
java SqlDateTimeBridgeDemo
```

Stdout:

```text
local date = 2024-02-29
SQL date = 2024-02-29
restored date = 2024-02-29
date equal = true
local time = 12:34:56.123456789
SQL time = 12:34:56
restored time = 12:34:56
restored nano = 0
exact time equal = false
seconds equal = true
strict bridge = Fractional seconds rejected
strict whole second = 12:34:56
null date preserved = true
null time preserved = true
midnight preserved = true
SQL date toInstant -> UnsupportedOperationException
SQL time toInstant -> UnsupportedOperationException
base reference toInstant -> UnsupportedOperationException
```

Các phương thức cầu nối trong chương trình có hợp đồng rõ:

- `toSqlDate` và `fromSqlDate` giữ `null` và chuyển ý nghĩa ngày.
- `fromSqlTime` giữ `null` và lấy giờ–phút–giây.
- `toSqlTimeRejectFraction` từ chối mọi giá trị có phần giây lẻ thay vì làm mất thông tin ngầm.
- `unsupported` chỉ phục vụ quan sát các lời gọi không được hỗ trợ trong ví dụ.

Chương trình cho thấy nửa đêm là một giá trị hợp lệ, khác với `null`. Nó cũng cho thấy khai báo tham chiếu bằng lớp cha không thay đổi hành vi `toInstant` của đối tượng SQL thực tế.

## 6. SQL NULL cần được giữ hoặc xử lý theo chính sách

`ResultSet.getDate` và `getTime` có thể trả `null` khi cột là SQL `NULL`. Gọi thẳng `rs.getDate("business_date").toLocalDate()` sẽ gây `NullPointerException` trong trường hợp đó.

Đoạn đọc JDBC cũ sau là **các phương thức minh họa**, cần đặt trong một lớp và dùng với `ResultSet` đang ở hàng hợp lệ:

```java
static LocalDate readDateLegacy(
        java.sql.ResultSet rs, String column)
        throws java.sql.SQLException {

    java.sql.Date value = rs.getDate(column);
    return value == null ? null : value.toLocalDate();
}

static LocalTime readTimeLegacy(
        java.sql.ResultSet rs, String column)
        throws java.sql.SQLException {

    java.sql.Time value = rs.getTime(column);
    return value == null ? null : value.toLocalTime();
}
```

`null` có thể được giữ trong đối tượng dữ liệu, bọc bằng `Optional` ở giao diện phù hợp hoặc bị từ chối nếu trường là bắt buộc. Lựa chọn nào cũng cần thể hiện đúng ý nghĩa của miền dữ liệu.

Không tự thay SQL `NULL` bằng:

- `1970-01-01` cho ngày.
- `00:00` cho giờ.
- Ngày/giờ hiện tại của máy.

Các giá trị đó đều có ý nghĩa thật. Dùng chúng làm “không có dữ liệu” tạo ra bản ghi tưởng hợp lệ và khó phân biệt về sau.

Khi ghi bằng JDBC, có thể biểu đạt `NULL` có kiểu rõ ràng bằng `setNull(index, Types.DATE)` hoặc `setNull(index, Types.TIME)`. Không cần chuyển một `null` qua `Date.valueOf` hay `Time.valueOf`; các phương thức này không coi `null` là ngày/giờ mặc định.

## 7. Khi có JDBC hiện đại, có thể dùng java.time trực tiếp

JDBC 4.2 bổ sung khả năng làm việc với các kiểu ngày giờ hiện đại. Khi driver hỗ trợ ánh xạ tương ứng, có thể truyền `LocalDate` cho `DATE` và `LocalTime` cho `TIME` thay vì đi qua lớp SQL cũ.

Ví dụ gán tham số, giả sử `statement` là `PreparedStatement` đã được tạo đúng câu lệnh:

```java
statement.setObject(1, businessDate, java.sql.Types.DATE);
statement.setObject(2, openingTime, java.sql.Types.TIME);
```

Đây là ví dụ tích hợp, không phải chương trình độc lập. `businessDate` có kiểu `LocalDate` và `openingTime` có kiểu `LocalTime`. [PreparedStatement](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/PreparedStatement.html) cung cấp `setObject` với kiểu SQL đích để diễn đạt cách ánh xạ.

Đọc theo kiểu mong muốn:

```java
LocalDate businessDate =
        rs.getObject("business_date", LocalDate.class);
LocalTime openingTime =
        rs.getObject("opening_time", LocalTime.class);
```

[ResultSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/ResultSet.html) cung cấp `getObject` nhận kiểu Java đích khi phép chuyển đổi được hỗ trợ. Với SQL `NULL`, kết quả đối tượng là `null`.

Đối với đầu vào có thể `null`, một phương thức gán minh họa đầy đủ về xử lý giá trị là:

```java
static void bindDateAndTime(
        java.sql.PreparedStatement statement,
        LocalDate date,
        LocalTime time) throws java.sql.SQLException {

    if (date == null) {
        statement.setNull(1, java.sql.Types.DATE);
    } else {
        statement.setObject(1, date, java.sql.Types.DATE);
    }

    if (time == null) {
        statement.setNull(2, java.sql.Types.TIME);
    } else {
        statement.setObject(2, time, java.sql.Types.TIME);
    }
}
```

Phương thức giả sử tham số 1 và 2 thực sự là hai cột phù hợp trong câu SQL. Việc chuẩn bị câu lệnh, thực thi và đóng tài nguyên thuộc mã tích hợp sử dụng phương thức này.

### 7.1. “Dùng trực tiếp LocalTime” không tự bảo đảm mọi nano giây được lưu

Khả năng giữ phần giây lẻ phụ thuộc cả:

- Kiểu cột và độ chính xác được khai báo.
- Miền giá trị của DBMS.
- Phiên bản và cấu hình driver.
- Cách driver xử lý giá trị không vừa độ chính xác cột.

Tránh `java.sql.Time` giúp tránh bước bỏ phần nano đã biết của cặp phương thức cầu nối cũ; nó không làm cột `TIME(0)` tự lưu được chín chữ số phần giây lẻ.

Kiểm chứng tích hợp cần đọc lại giá trị từ cơ sở dữ liệu rồi so sánh theo hợp đồng. Chương trình không dùng DB ở trên chỉ chứng minh hành vi chuyển đổi của các lớp Java, chưa chứng minh cách lưu trữ của một DBMS cụ thể.

### 7.2. Không bắt mọi SQLException rồi âm thầm chuyển sang đường cũ

Driver không hỗ trợ một ánh xạ có thể báo lỗi chuyển đổi hoặc không hỗ trợ tính năng. Đó là thông tin cần phân biệt với sai câu SQL, sai tên cột, mất kết nối hoặc lỗi dữ liệu.

Nếu phải duy trì đường tương thích cũ, chọn và kiểm chứng nó có chủ đích theo driver đang dùng. Đặc biệt, không chuyển sang `java.sql.Time` như một phương án dự phòng ngầm khi hệ thống cần phần giây lẻ; kết quả có thể thành công về kỹ thuật nhưng mất dữ liệu.

## 8. Múi giờ, phạm vi và khả năng thay đổi của lớp cũ

### 8.1. Ngữ nghĩa không có múi giờ khác với việc hiện thực cũ có phụ thuộc môi trường

`LocalDate` và `LocalTime` không mang múi giờ. Tuy nhiên, lớp `java.sql.Date`/`Time` dùng nền tảng mili giây của API cũ, và driver có thể phải diễn giải nó theo múi giờ mặc định hoặc cấu hình tương ứng.

Các overload JDBC nhận `Calendar` có thể tác động cách driver dựng hoặc đọc giá trị cũ. Chúng không tự gắn một `ZoneId` vào `LocalDate` hay `LocalTime`. Không trộn tùy tiện cách tạo mili giây trong một vùng với cách đọc thành phần ở vùng khác.

Với hệ thống cũ, cần kiểm chứng trọn đường đi: giá trị nghiệp vụ → lời gọi JDBC → cột thực tế → lời gọi đọc → giá trị nghiệp vụ. Giữ môi trường rõ ràng và ưu tiên ánh xạ hiện đại khi nó được hỗ trợ đúng yêu cầu.

### 8.2. Miền dữ liệu không đồng nhất giữa mọi lớp và cơ sở dữ liệu

`LocalDate` hỗ trợ một miền năm rộng. Điều đó không có nghĩa driver hoặc cột `DATE` của hệ thống đích hỗ trợ mọi giá trị trong miền đó.

Dữ liệu rất xa về quá khứ còn có thể gặp khác biệt quy tắc lịch giữa lớp cũ và lịch ISO mở rộng của `java.time`. Với ứng dụng chỉ cho phép một khoảng năm nhất định, xác thực theo khoảng nghiệp vụ và khả năng hệ thống đích. Không coi ví dụ hiện đại năm 2024 là bằng chứng cho mọi ngày lịch sử.

### 8.3. Đừng để lớp JDBC có thể thay đổi lan vào miền nghiệp vụ

`java.sql.Date` và `Time` có thể bị sửa thông qua API cũ; `LocalDate` và `LocalTime` là bất biến. Có thể chuyển ngay khi đọc/ghi để phần nghiệp vụ chỉ thấy các giá trị hiện đại.

Không lưu một đối tượng SQL dùng chung rồi để các đoạn mã khác thay đổi `setTime` trong lúc đang xử lý. Dùng kiểu bất biến ở lớp nghiệp vụ giúp tránh việc ngày/giờ thay đổi ngoài dự kiến.

Cũng nên viết tên lớp đầy đủ ở nơi có khả năng nhầm lẫn: `java.sql.Date` và `java.util.Date` cùng có tên ngắn `Date`. Không import cả hai bằng wildcard rồi để người đọc phải đoán lớp nào đang dùng.

## 9. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng `sqlDate.toInstant()` | `UnsupportedOperationException` | Dùng `toLocalDate` cho ngày thuần |
| Dùng `sqlTime.toInstant()` | Thiếu ngày, thao tác không được hỗ trợ | Dùng `toLocalTime` cho giờ thuần |
| Chuyển qua epoch mili giây để lấy ngày theo UTC | Có thể đổi ngày so với ý nghĩa đầu vào | Dùng phương thức cầu nối đúng loại |
| Cho rằng `Time.valueOf(LocalTime)` giữ nano | Mất phần giây lẻ | Chọn chính sách độ chính xác rõ ràng |
| Chỉ nhìn `toString` để kiểm tra giữ dữ liệu | Có thể bỏ sót thay đổi giá trị | So sánh `LocalTime` và `getNano` |
| Gọi chuyển đổi trên giá trị SQL `NULL` | `NullPointerException` | Kiểm tra `null` ở biên |
| Thay `NULL` bằng nửa đêm hoặc năm 1970 | Trộn dữ liệu thiếu với giá trị thật | Giữ hoặc từ chối thiếu dữ liệu theo hợp đồng |
| Dùng `TIME` để lưu mọi loại thời lượng | Sai miền và ý nghĩa | Phân biệt giờ trong ngày với thời lượng |
| Dùng một tham chiếu `java.util.Date` rồi coi đối tượng SQL như thời điểm thường | Gọi sai hành vi của lớp thực | Kiểm tra đúng loại và ý nghĩa |
| Coi driver hiện đại đồng nghĩa giữ được mọi độ chính xác | Dữ liệu vẫn có thể bị cắt/làm tròn | Kiểm chứng cùng kiểu cột thật |

## 10. Tự kiểm chứng và thực hành

1. Chuyển `LocalDate.of(2024, 2, 29)` sang `java.sql.Date` rồi đọc lại. Kiểm tra bằng `equals`, không so sánh tham chiếu.
2. Chuyển `LocalTime` có phần giây lẻ khác `0` qua `java.sql.Time`. Kiểm tra rằng ngày giờ quay lại có `getNano() == 0` và không bằng giá trị gốc.
3. Dùng giờ đúng giây và kiểm tra cầu nối từ chối phần lẻ vẫn chấp nhận nó.
4. Dùng nửa đêm để xác nhận đó là giá trị hợp lệ, không phải tín hiệu `NULL`.
5. Kiểm tra helper với `null` ở cả chiều đọc và ghi. Chính sách giữ `null` phải nhất quán.
6. Gán một `java.sql.Date` cho biến `java.util.Date` rồi gọi `toInstant` trong một ví dụ bắt lỗi. Giải thích theo lớp thực tế của đối tượng.
7. Nếu có DBMS và driver phù hợp, tạo phép kiểm chứng đọc–ghi riêng cho cột ngày và cột giờ có độ chính xác phần giây đã công bố. Ghi rõ giá trị nào phải giữ nguyên và giá trị nào bị từ chối.
8. Với cột bắt buộc, sửa lớp ánh xạ để báo lỗi thiếu dữ liệu thay vì thay bằng ngày hoặc giờ giả.
9. Mô tả nơi đặt chuyển đổi trong ứng dụng để các hàm nghiệp vụ không cần import `java.sql.Date` hoặc `java.sql.Time`.
10. Trước khi thay một đường JDBC cũ bằng đường mới, đối chiếu ý nghĩa cột, xử lý `NULL`, độ chính xác và kết quả đọc lại; không chỉ kiểm tra câu lệnh không ném lỗi.

Mục tiêu là giữ đúng ý nghĩa ngày và giờ qua biên JDBC. Với ngày thuần, dùng cầu nối `Date.valueOf`/`toLocalDate` khi cần lớp cũ; với giờ, phải xét rõ giới hạn phần giây lẻ của `Time` và khả năng ánh xạ trực tiếp của driver.
