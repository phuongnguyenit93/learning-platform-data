# Độ chính xác cột dữ liệu và mất phần nano giây khi đọc ghi

## 1. Java giữ được nano giây không có nghĩa cột dữ liệu cũng giữ được

Giả sử ứng dụng có giá trị:

```text
2024-01-01T12:00:00.123456789Z
```

Phần sau dấu chấm có chín chữ số, tức có thể phân biệt đến nano giây. Nếu một đường lưu trữ chỉ giữ được sáu chữ số phần giây, nó không thể biểu diễn nguyên vẹn mọi giá trị như trên.

Có ba kết quả hợp đồng thường gặp:

- Từ chối đầu vào vì độ chi tiết vượt khả năng lưu.
- Cắt thành `.123456`.
- Làm tròn thành `.123457`.

Đọc lại rồi thêm ba số `0` thành `.123456000` không khôi phục được ba chữ số `789` đã mất. Đó chỉ là cách viết một giá trị mới ít chi tiết hơn.

Vì vậy, câu hỏi cần trả lời không chỉ là “Java có trường nano không?” mà là: **toàn bộ đường ghi–lưu–đọc giữ được giá trị đến mức nào và xử lý phần dư theo quy tắc nào?**

Bài dùng từ “độ chính xác phần giây” để nói số chữ số lưu được. Nó khác độ chính xác đo lường của đồng hồ: một kiểu có khả năng lưu chín chữ số không chứng minh thiết bị thực sự đo chính xác đến nano giây.

## 2. Số chữ số phần giây và bước biểu diễn

Trong nhiều kiểu thời gian SQL, tham số `p` biểu thị số chữ số phần giây. Ý nghĩa cụ thể và miền `p` phải kiểm tra theo DBMS, nhưng bảng sau minh họa quan hệ toán học:

| Chữ số phần giây | Đơn vị nhỏ nhất tương ứng | Ví dụ phần giây sau khi cắt |
| --- | --- | --- |
| `0` | Giây | Không có phần lẻ |
| `3` | Mili giây, `10^-3` giây | `.123` |
| `6` | Micro giây, `10^-6` giây | `.123456` |
| `9` | Nano giây, `10^-9` giây | `.123456789` |

Không phải cơ sở dữ liệu nào cũng hỗ trợ `p = 9`. Ví dụ [PostgreSQL](https://www.postgresql.org/docs/current/datatype-datetime.html) mô tả các kiểu timestamp/time có độ phân giải micro giây và cho phép tham số độ chính xác từ `0` đến `6`.

Một giá trị không cần có đủ số chữ số tối đa mới được biểu diễn chính xác. `.123` có thể được lưu nguyên vẹn trong một cột cho phép sáu chữ số bằng giá trị `.123000`. Hai cách viết này biểu diễn cùng một phần giây.

Ngược lại, `.123456789` không nằm đúng trên các mốc micro giây. Với miền nano của Java, điều kiện thẳng hàng theo micro giây là:

```java
value.getNano() % 1_000 == 0
```

Nếu cho phép `p` chữ số với `0 <= p <= 9` và các bước biểu diễn đều nhau, kích thước mỗi bước theo nano giây là `10^(9-p)`. Đây là cách lý giải điều kiện chia hết, không phải lời bảo đảm mọi DBMS đều dùng đúng mô hình hoặc miền `p` đó.

## 3. Thông tin có thể mất ở nhiều lớp

Đường đi của giá trị thường gồm:

```text
Giá trị Java
    → lớp chuyển đổi / ORM
    → JDBC driver và cách gán tham số
    → kiểu cột, độ chính xác, chế độ DBMS
    → JDBC driver khi đọc
    → kiểu Java sau đọc
    → định dạng / dữ liệu trả ra
```

Chỉ cần một bước bỏ phần giây lẻ, bước sau có khả năng lưu cao hơn cũng không thể tự tìm lại thông tin.

| Điểm trong đường đi | Ví dụ nguy cơ |
| --- | --- |
| Chuyển thành epoch mili giây | Mất phần nhỏ hơn mili giây |
| Chuyển `LocalTime` qua cầu nối `java.sql.Time` | Có thể bỏ phần nano qua các phương thức chuyển đổi cũ |
| Cột chỉ có `p = 3` | Không lưu nguyên vẹn micro/nano khác bội số mili giây |
| Gán giá trị bằng kiểu không phù hợp | Driver có thể phải chuyển đổi hoặc từ chối |
| Đọc sang `java.util.Date` | Kiểu biểu diễn dựa trên mili giây |
| Định dạng chỉ ba chữ số phần giây | Chuỗi đầu ra không mang phần nhỏ hơn mili giây |
| Bộ tuần tự hóa gửi số epoch theo mili giây | Bên nhận chỉ có dữ liệu đến mili giây |

Phân biệt **mất giá trị** với **ẩn khi hiển thị**. Nếu một công cụ chỉ in ba chữ số nhưng giá trị bên trong vẫn có nano, dữ liệu có thể chưa mất. Phải đọc và so sánh giá trị thực; nhìn giao diện quản trị cơ sở dữ liệu chưa đủ để kết luận.

Tương tự, các số `0` ở cuối có thể được lược khi hiển thị mà không mất dữ liệu. `.123456` và `.123456000` bằng nhau về phần giây.

## 4. java.sql.Timestamp có nano nhưng getTime() chỉ trả mili giây

[java.sql.Timestamp](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Timestamp.html) giữ phần nano giây riêng ngoài phần dựa trên `java.util.Date`. Nó có `getNanos()` và có thể chuyển từ/đến `Instant` mà giữ phần nano trong miền biểu diễn phù hợp.

```java
Instant original = Instant.parse(
        "2024-01-01T12:00:00.123456789Z");

Timestamp timestamp = Timestamp.from(original);
Instant exact = timestamp.toInstant();
```

Với đầu vào này, `exact.equals(original)` là `true`.

Nhưng đường đi sau chỉ mang mili giây:

```java
Instant reduced =
        Instant.ofEpochMilli(timestamp.getTime());
```

Kết quả là `2024-01-01T12:00:00.123Z`. `getTime()` đã trả một số nguyên mili giây; phần nhỏ hơn mili giây không nằm trong số đó.

Tương tự, lấy `timestamp.getTime()` để dựng một `java.util.Date` mới sẽ không sao chép toàn bộ phần nano riêng của `Timestamp`. Không dùng “đã là long nên chắc giữ mọi chi tiết” làm giả định: đơn vị của số `long` mới quyết định ý nghĩa và độ chi tiết.

Việc `Timestamp` giữ được nano trong bộ nhớ cũng không chứng minh một cột timestamp của DBMS giữ được chín chữ số. Hai giới hạn ở hai tầng khác nhau.

## 5. Ba chính sách cho giá trị vượt khả năng cột

### 5.1. Từ chối

Phù hợp khi sai khác thời gian dù nhỏ cũng không được phép bị che. Với cột giả định lưu đến micro giây, có thể yêu cầu `getNano() % 1000 == 0`.

Nếu không đáp ứng, báo đầu vào vượt độ chính xác hỗ trợ. Chính sách này giữ hợp đồng mạnh: giá trị đã chấp nhận phải có khả năng biểu diễn nguyên vẹn theo mức đã công bố.

### 5.2. Cắt về mốc

Với `Instant`, [truncatedTo](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html#truncatedTo(java.time.temporal.TemporalUnit)) hỗ trợ cắt theo các đơn vị phù hợp:

```java
Instant micros = original.truncatedTo(ChronoUnit.MICROS);
Instant millis = original.truncatedTo(ChronoUnit.MILLIS);
```

Ví dụ `.123456789` thành `.123456` khi cắt theo micro giây. Kết quả không muộn hơn đầu vào. Trong cách biểu diễn của `Instant`, cắt theo đơn vị tạo mốc phía trước trên dòng thời gian, kể cả trước epoch; không nên tự lấy một số epoch có dấu rồi chia nguyên mà chưa xét quy tắc với số âm.

Chuẩn hóa bằng cùng phép cắt hai lần phải cho cùng kết quả như một lần. Tính chất này giúp việc đi qua nhiều lớp cùng tuân thủ một hợp đồng không tiếp tục làm thay đổi giá trị.

### 5.3. Làm tròn

Làm tròn chọn mốc gần hơn. Phải nói rõ cách xử lý đúng nửa bước, chẳng hạn chọn mốc phía tương lai, chọn số chẵn hoặc một quy tắc khác.

Trong ví dụ Java phía dưới, quy tắc được định nghĩa là:

**Làm tròn tới micro giây gần nhất; nếu đúng nửa micro giây, chọn mốc phía tương lai.**

Cách hiện thực là cộng `500` nano giây rồi cắt xuống mốc micro giây. Tên hàm `roundToMicrosTiesForward` cố ý nói rõ quy tắc. Đây là mô phỏng chính sách ứng dụng, không tuyên bố trùng cách làm tròn của mọi DBMS.

Làm tròn có thể đẩy giá trị sang giây hoặc ngày tiếp theo. `23:59:59.999999700` có thể thành `00:00:00` của ngày sau. Nếu giá trị sát giới hạn của `Instant`, phép cộng trung gian cũng có thể vượt miền; không được âm thầm quấn về một giá trị khác.

### 5.4. Đừng mặc định DBMS luôn cắt

[Tài liệu MySQL 8.4 về phần giây lẻ](https://dev.mysql.com/doc/refman/8.4/en/fractional-seconds.html) cho biết các kiểu thời gian tương ứng hỗ trợ đến sáu chữ số; khi ghi vào cột ít chữ số hơn, hành vi mặc định được mô tả là làm tròn. Chế độ `TIME_TRUNCATE_FRACTIONAL` có thể chuyển sang cắt.

Cùng tài liệu cũng nêu độ chính xác mặc định khi bỏ `fsp` là `0`. Vì vậy, một cột được tạo mà không ghi rõ phần giây lẻ có thể không đáp ứng mong muốn giữ micro giây.

Điểm học tập là phải kiểm tra **kiểu cột thực tế, cấu hình và phiên bản đang dùng**. Không suy hành vi lưu từ tên Java `Instant`, `LocalDateTime` hoặc từ một ví dụ trên DBMS khác.

## 6. Chương trình Java 17+ đầy đủ

Lưu thành `TemporalColumnPrecisionDemo.java`. Chương trình chỉ dùng thư viện chuẩn, không kết nối cơ sở dữ liệu.

```java
import java.sql.Timestamp;
import java.time.Duration;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Objects;

public class TemporalColumnPrecisionDemo {
    static Instant truncateToMicros(Instant value) {
        return Objects.requireNonNull(value).truncatedTo(ChronoUnit.MICROS);
    }

    static Instant roundToMicrosTiesForward(Instant value) {
        return Objects.requireNonNull(value)
                .plusNanos(500)
                .truncatedTo(ChronoUnit.MICROS);
    }

    static Instant requireMicroAligned(Instant value) {
        Objects.requireNonNull(value);
        if (value.getNano() % 1_000 != 0) {
            throw new IllegalArgumentException("More than 6 fractional digits");
        }
        return value;
    }

    public static void main(String[] args) {
        Instant original = Instant.parse("2024-01-01T12:00:00.123456789Z");
        Timestamp timestamp = Timestamp.from(original);
        Instant viaMillis = Instant.ofEpochMilli(timestamp.getTime());
        Instant micros = truncateToMicros(original);
        Instant rounded = roundToMicrosTiesForward(original);

        System.out.println("original = " + original);
        System.out.println("Timestamp nanos = " + timestamp.getNanos());
        System.out.println("Timestamp exact = "
                + original.equals(timestamp.toInstant()));
        System.out.println("via milliseconds = " + viaMillis);
        System.out.println("millisecond loss = "
                + !original.equals(viaMillis));
        System.out.println("truncate micros = " + micros);
        System.out.println("round micros = " + rounded);
        System.out.println("truncate loss nanos = "
                + Duration.between(micros, original).toNanos());
        System.out.println("round forward nanos = "
                + Duration.between(original, rounded).toNanos());

        System.out.println("truncate idempotent = "
                + micros.equals(truncateToMicros(micros)));
        Instant later = original.plusNanos(100);
        System.out.println("distinct originals = " + !original.equals(later));
        System.out.println("same stored bucket = "
                + truncateToMicros(original).equals(truncateToMicros(later)));

        Instant nearMidnight =
                Instant.parse("2024-01-01T23:59:59.999999700Z");
        System.out.println("round crosses date = "
                + roundToMicrosTiesForward(nearMidnight));

        Instant beforeEpoch =
                Instant.parse("1969-12-31T23:59:59.999999999Z");
        System.out.println("before epoch truncate = "
                + truncateToMicros(beforeEpoch));

        try {
            requireMicroAligned(original);
        } catch (IllegalArgumentException ex) {
            System.out.println("strict = " + ex.getMessage());
        }
        System.out.println("strict aligned = " + requireMicroAligned(micros));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 TemporalColumnPrecisionDemo.java
java TemporalColumnPrecisionDemo
```

Stdout:

```text
original = 2024-01-01T12:00:00.123456789Z
Timestamp nanos = 123456789
Timestamp exact = true
via milliseconds = 2024-01-01T12:00:00.123Z
millisecond loss = true
truncate micros = 2024-01-01T12:00:00.123456Z
round micros = 2024-01-01T12:00:00.123457Z
truncate loss nanos = 789
round forward nanos = 211
truncate idempotent = true
distinct originals = true
same stored bucket = true
round crosses date = 2024-01-02T00:00:00Z
before epoch truncate = 1969-12-31T23:59:59.999999Z
strict = More than 6 fractional digits
strict aligned = 2024-01-01T12:00:00.123456Z
```

Chương trình chứng minh các hành vi Java và chính sách mô phỏng đã nêu:

- `Timestamp.from`/`toInstant` giữ nano của đầu vào mẫu.
- Đi vòng qua epoch mili giây làm mất phần nhỏ hơn mili giây.
- Cắt theo micro giây làm mất `789` nano giây ở ví dụ.
- Làm tròn theo quy tắc mẫu tiến lên `211` nano giây.
- Hai thời điểm khác nhau có thể rơi vào cùng một mốc sau chuẩn hóa.
- Làm tròn có thể vượt ranh giới ngày.
- Chính sách từ chối không âm thầm bỏ dữ liệu.

Chương trình **không chứng minh cách một driver hoặc cột dữ liệu thật xử lý đầu vào**. Phần đó cần kiểm chứng tích hợp riêng bằng đúng schema, driver và cấu hình triển khai.

## 7. Đọc lại phải so với hợp đồng lưu trữ

Giả sử ứng dụng đã chọn rõ hợp đồng: mọi thời điểm được cắt theo micro giây trước khi ghi.

Ta có ba giá trị:

| Tên | Ý nghĩa |
| --- | --- |
| `original` | Giá trị ứng dụng ban đầu có thể có nano |
| `expectedStored` | `original.truncatedTo(MICROS)` theo chính sách |
| `readBack` | Giá trị thực đọc lại từ DB |

Khi đó, điều cần kiểm chứng là `expectedStored.equals(readBack)`. So trực tiếp `original` với `readBack` sẽ thất bại hợp lệ nếu chính sách đã cho phép cắt.

Tuy nhiên, không được chỉ cắt cả giá trị đọc lại rồi mới so sánh nếu điều đó che mất lỗi. Nếu DB bất ngờ trả về một giá trị không nằm đúng độ chính xác đã công bố, đó cũng là điều cần phát hiện.

Nếu hợp đồng là giữ nguyên đầu vào, so sánh phải là `original.equals(readBack)`. Đừng đổi bài kiểm chứng thành “cho phép chênh lệch một giây” chỉ để việc ghi–đọc có vẻ thành công.

Nếu hợp đồng chọn làm tròn, cần tính `expectedStored` bằng đúng quy tắc đã xác minh cho hệ thống, bao gồm trường hợp đúng nửa bước và tràn giây. Không dùng phép cắt của Java làm kỳ vọng cho một DBMS đang làm tròn.

## 8. Thiết kế một phép kiểm chứng tích hợp có ý nghĩa

Khi có DBMS và driver cụ thể, một phép kiểm chứng cần đi qua toàn bộ đường thực tế:

1. Xác nhận DDL của cột và độ chính xác được tạo thật.
2. Ghi bằng chính cách gán tham số mà ứng dụng sử dụng.
3. Đọc lại bằng kiểu Java mà ứng dụng thực sự nhận.
4. So sánh giá trị với chính sách đã chọn.
5. Quan sát phần nano, mốc giây và ranh giới ngày nếu có thay đổi.

Dữ liệu nên gồm:

| Đầu vào phần giây hoặc vị trí | Mục đích kiểm chứng |
| --- | --- |
| `.123000000` | Đã thẳng hàng theo mili giây |
| `.123456000` | Đã thẳng hàng theo micro giây |
| `.123456789` | Có phần nhỏ hơn micro giây |
| `.123456499` | Ngay dưới nửa bước làm tròn micro |
| `.123456500` | Đúng nửa bước |
| `.123456501` | Ngay trên nửa bước |
| `23:59:59.999999700` | Có thể làm tròn sang ngày mới |
| Giá trị trước epoch | Phát hiện xử lý dấu sai |
| SQL `NULL` | Phân biệt dữ liệu thiếu với mốc epoch |

Nếu cột hoặc driver không hỗ trợ một miền thời gian, đầu vào ngoài miền cần bị từ chối rõ ràng. Không nhầm mất độ chính xác phần giây với vượt miền năm hoặc sai ngữ nghĩa múi giờ.

Một cơ sở dữ liệu nhúng dùng trong kiểm chứng có thể có độ chính xác khác hệ thống triển khai. Nó phù hợp để kiểm tra một số phần mã nhưng không thay được kiểm chứng hành vi lưu của DBMS đích.

### 8.1. Chọn đúng ngữ nghĩa thời gian trước khi chọn độ chính xác

`LocalDateTime` không có offset hoặc vùng; `Instant` là thời điểm trên dòng thời gian. Một đường đọc–ghi sai múi giờ có thể lệch nhiều giờ, không chỉ lệch vài nano giây.

Hãy xác định trước cột biểu diễn thời điểm hay ngày giờ địa phương, cách driver ánh xạ kiểu đó và cách cấu hình vùng. Sau đó mới kiểm chứng phần giây. Việc tăng từ `p = 3` lên `p = 6` không sửa được một ánh xạ múi giờ sai.

Cũng không nên tự giả định mọi driver nhận `Instant` trực tiếp qua `setObject`. Chọn đường ánh xạ được driver công bố và dùng đúng đường đó trong phép kiểm chứng.

### 8.2. ORM và migration cần cùng một hợp đồng

Đổi trường Java từ kiểu cũ sang `Instant` không tự bảo đảm cột hiện hữu đã có độ chính xác phù hợp. Annotation, DDL sinh ra trong môi trường kiểm chứng và migration của hệ thống thật có thể không giống nhau.

Cần kiểm tra schema sau migration, không chỉ mã khai báo đối tượng. Nếu driver hoặc DBMS được nâng cấp, hành vi làm tròn và đọc phần giây cũng là điểm cần kiểm chứng lại khi có thay đổi liên quan.

## 9. Hệ quả đối với truy vấn, sắp xếp và đồng thời

### 9.1. So sánh bằng có thể không khớp kỳ vọng

Nếu giá trị đã lưu bị chuẩn hóa còn tham số truy vấn vẫn mang nano gốc, phép so sánh bằng có thể không khớp. Cách ép kiểu tham số phụ thuộc hệ thống, nên cần kiểm chứng thay vì dựa vào suy đoán.

Nên cung cấp cùng quy tắc chuẩn hóa cho các giá trị nghiệp vụ được dùng làm khóa thời gian, hoặc tìm bản ghi bằng khóa định danh ổn định nếu thời điểm không thực sự là định danh.

### 9.2. Hai sự kiện có thể cùng một thời gian sau lưu

Chương trình tạo hai `Instant` cách nhau `100` nano giây nhưng cùng mốc micro sau cắt. Vì thế, độ chính xác lưu thấp hơn có thể làm mất thứ tự phân biệt giữa chúng.

Không dùng một timestamp như bảo đảm duy nhất rằng bản ghi có thứ tự toàn phần hoặc duy nhất. Nếu cần phân trang ổn định khi nhiều bản ghi cùng thời gian, có thể dùng thêm một khóa định danh ổn định làm tiêu chí phụ theo thứ tự đã quy định.

Đây không phải cách khôi phục thứ tự nano đã mất; nó chỉ cung cấp một thứ tự xử lý rõ ràng cho các bản ghi đang có cùng mốc lưu.

### 9.3. Timestamp làm phiên bản có thể không đủ phân biệt

Nếu hai lần cập nhật nằm trong cùng bước biểu diễn của cột, dùng riêng thời gian làm dấu phiên bản có thể không phân biệt được chúng. Khi cần kiểm soát cập nhật đồng thời, một số phiên bản tăng riêng thường dễ diễn đạt hợp đồng hơn việc trông chờ đồng hồ luôn tạo giá trị khác nhau.

Lựa chọn cụ thể còn tùy mô hình ứng dụng, nhưng không nên coi “có nhiều chữ số phần giây” là bảo đảm tự động cho tính duy nhất hoặc quan hệ nhân quả.

### 9.4. Ranh giới khoảng cũng cần hợp đồng

Khoảng nửa mở `[fromInclusive, toExclusive)` giúp tránh chồng lặp ở ranh giới, nhưng không tự giải quyết mọi mất độ chính xác. Cắt hoặc làm tròn cả hai đầu mút có thể làm khoảng hẹp đi hoặc rộng ra so với yêu cầu ban đầu.

Phải xác định dữ liệu và ranh giới đang được diễn giải trên cùng mức độ chi tiết nào. Đừng chuẩn hóa mọi tham số một cách máy móc chỉ vì cột có `p = 6`; kiểm chứng các giá trị ngay trước, đúng tại và ngay sau ranh giới mong muốn.

## 10. Nếu thật sự cần giữ đủ nano giây

Các hướng lựa chọn tùy yêu cầu:

- Dùng kiểu cột và driver hỗ trợ độ chi tiết cần thiết, rồi kiểm chứng giá trị đọc lại.
- Nếu hệ thống đích chỉ hỗ trợ micro giây nhưng cần giữ dữ liệu gốc, có thể lưu thêm phần thời gian gốc theo một biểu diễn chính xác đã công bố.
- Một cách biểu diễn tùy biến là hai thành phần `epochSecond` và `nanoOfSecond`; phải có ràng buộc miền và cách so sánh nhất quán.

Không vội gom mọi thời điểm thành một `long` “epoch nano”. Miền `Instant` rộng hơn khả năng giữ mọi nano giây trong một `long`. Phép nhân `epochSecond * 1_000_000_000` có thể tràn nếu không giới hạn miền và kiểm tra số học.

Nếu dùng chuỗi hoặc số nhiều thành phần để giữ dữ liệu gốc, cần thiết kế truy vấn, sắp xếp, ràng buộc và khả năng tương tác. Đó là quyết định lưu trữ, không chỉ đổi kiểu Java ở một trường.

Cũng không nên dùng chuỗi hiển thị địa phương làm biểu diễn chính xác lâu dài. Nó có thể mất phần giây, thiếu offset hoặc phụ thuộc locale.

## 11. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Thấy Java có nano rồi tin DB giữ nguyên | Đọc lại khác giá trị gốc | Kiểm tra toàn bộ đường lưu |
| Mặc định cột timestamp nào cũng có cùng độ chính xác | Sai giả thiết giữa DBMS | Xem DDL và tài liệu hệ thống đích |
| Dùng `getTime` hoặc epoch mili giây giữa đường | Mất phần nhỏ hơn mili giây | Giữ kiểu có phần nano khi cần |
| Cho rằng DB luôn cắt | Kỳ vọng sai khi DB làm tròn | Xác minh quy tắc và cấu hình |
| Chỉ so chuỗi in bởi công cụ DB | Nhầm hiển thị với giá trị | Đọc kiểu thời gian và kiểm tra nano |
| Thêm số `0` để “khôi phục nano” | Không phục hồi dữ liệu đã mất | Giữ dữ liệu gốc từ trước khi giảm độ chi tiết |
| Dùng dung sai tùy tiện để làm kiểm chứng qua | Che lỗi ánh xạ | So với hợp đồng chuẩn hóa cụ thể |
| Dùng timestamp làm khóa duy nhất | Va chạm sau lượng tử hóa | Dùng định danh phù hợp |
| Chỉ đổi entity, không xem migration | Cột thật vẫn có độ chính xác cũ | Kiểm tra schema đã triển khai |
| Đổi độ chính xác để sửa lỗi lệch múi giờ | Không xử lý nguyên nhân | Kiểm tra ngữ nghĩa thời gian riêng |

## 12. Tự kiểm chứng và thực hành

1. Chạy chương trình và giải thích từng chữ số còn lại sau đường epoch mili giây, đường cắt micro và đường làm tròn micro.
2. Thay đầu vào bằng `.123456000`. Chính sách từ chối phần nhỏ hơn micro phải chấp nhận và phép cắt không đổi giá trị.
3. Thử đúng nửa micro giây để kiểm tra tên `TiesForward` có khớp cách hiện thực không.
4. Thử giá trị sát cuối ngày và xác nhận làm tròn có thể đổi cả ngày.
5. Thử hai sự kiện khác nano nhưng cùng mốc lưu. Giải thích vì sao không thể suy thứ tự nano từ timestamp đã bị cắt.
6. Viết một chính sách chỉ chấp nhận mili giây, với điều kiện thẳng hàng tương ứng, và không tự cắt khi đầu vào sai.
7. Nếu có DBMS đích, tạo phép kiểm chứng tích hợp theo bộ dữ liệu biên ở trên. Ghi rõ phiên bản driver, kiểu cột, `p` và chế độ làm tròn/cắt.
8. Kiểm tra đường chuyển đổi và định dạng JSON thực tế của ứng dụng để tìm điểm nào đổi sang epoch mili giây.
9. Thiết kế cách so sánh đọc lại cho hai hợp đồng: giữ nguyên đầu vào và cắt trước khi ghi. Hai phép so sánh phải phản ánh hai yêu cầu khác nhau.
10. Giải thích vì sao một cột chính xác đến nano giây vẫn không tự bảo đảm đồng hồ chính xác, bản ghi duy nhất hoặc thứ tự nhân quả.

Một hợp đồng lưu thời gian cần nêu đủ ý nghĩa kiểu, đơn vị nhỏ nhất, cách xử lý phần dư và cách kiểm chứng đọc lại. Khi những điều đó được quy định rõ, việc mất nano không còn là một sai khác bí ẩn xuất hiện sau khi dữ liệu đã lưu.
