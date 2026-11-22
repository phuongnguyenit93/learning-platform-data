# tinyint, smallint, int, bigint và varint trong Apache Cassandra

Trong Apache Cassandra, **tinyint**, **smallint**, **int**, **bigint** và **varint** đều biểu diễn **số nguyên có dấu**, nhưng khác nhau về miền giá trị, số byte mã hóa và kiểu tương ứng trong ứng dụng Java. Chọn sai có thể làm thao tác ghi thất bại khi vượt biên, khiến code Java ép kiểu mất dữ liệu, hoặc tạo chi phí không cần thiết trên một bảng có hàng tỷ dòng.

Bài này thuộc chương **Kiểu dữ liệu** của module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**, nơi học kiến trúc phân tán, mô hình wide-column, khóa phân vùng, thiết kế bảng theo truy vấn, mức nhất quán đọc/ghi và kết nối Cassandra từ Java. Với năm kiểu số nguyên, điều cần quyết định trước tiên là **miền giá trị thực tế và dự kiến tăng trưởng**, sau đó mới xét kích thước lưu trữ, vai trò của cột trong khóa và khả năng xử lý của ứng dụng. Các vấn đề replication, compaction, repair và retry không thể bù lại một kiểu số đã chọn sai miền.

## 1. So sánh năm kiểu số nguyên CQL

| Kiểu CQL | Biểu diễn | Miền giá trị | Kiểu Java mặc định (Driver 4.x) | Tình huống điển hình |
|---|---:|---|---|---|
| **tinyint** | 1 byte (8 bit) | −128 đến 127 | `byte` / `Byte` | Mức chất lượng 0–5, mã trạng thái nhỏ đã giới hạn |
| **smallint** | 2 byte (16 bit) | −32.768 đến 32.767 | `short` / `Short` | Số lần thử với giới hạn rõ ràng, mã giao thức |
| **int** | 4 byte (32 bit) | −2.147.483.648 đến 2.147.483.647 | `int` / `Integer` | Số lượng, chỉ số, độ dài trong giới hạn 32 bit |
| **bigint** | 8 byte (64 bit) | −9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 | `long` / `Long` | Số byte tích lũy, thứ tự sự kiện, số tiền ở đơn vị nhỏ nhất |
| **varint** | Độ dài biến thiên | Số nguyên có dấu với độ chính xác tùy ý, chịu giới hạn tài nguyên thực tế | `BigInteger` | Số nguyên vượt 64 bit, số lượng tổ hợp toán học |

Mỗi miền cố định là miền của **số nguyên có dấu dùng bù hai**: từ \( -2^{n-1} \) đến \( 2^{n-1}-1 \) với \(n\) bit. Do có một phần miền dành cho số âm, **int không chứa được 4.000.000.000**, dù giá trị đó vừa 32 bit *không dấu* trong một số hệ thống khác. Cassandra không cung cấp họ `uint8`, `uint16`, `uint32`, `uint64` tương ứng để thay thế trực tiếp.

**varint** không có giới hạn 8/16/32/64 bit cố định; giá trị có thể lớn hơn `bigint`. Tuy nhiên, “tùy ý” nói về độ chính xác biểu diễn, không có nghĩa Cassandra lưu được một số dài vô hạn byte. Kích thước giá trị, bộ nhớ, giao thức, khả năng mã hóa và chi phí vận hành vẫn áp dụng.

## 2. Quy tắc chọn theo miền giá trị

### 2.1. Tính biên theo tương lai, không chỉ dữ liệu hiện tại

Giả sử một thiết bị hiện có 25 lần thử kết nối, nhưng hệ thống có thể giữ tổng số lần thử trong suốt vòng đời. **tinyint** chỉ chịu được tối đa 127; **smallint** được 32.767; nếu tổng có thể lớn hơn, phải chọn **int** hoặc **bigint** theo dự báo.

Cách đánh giá:

1. Xác định **giá trị nhỏ nhất và lớn nhất theo nghiệp vụ**: có số âm không, giá trị có reset hay tích lũy mãi?
2. Xác định **tốc độ tăng** và thời gian giữ dữ liệu: 10.000 sự kiện/giây tích lũy nhiều năm khác với 10 lần retry cho một yêu cầu.
3. Xem xét **tích số và tổng** ở Java: hai toán hạng đều vừa `int` không bảo đảm tổng hoặc tích cũng vừa `int`.
4. Chọn kiểu đủ miền và có biên an toàn, nhất là với cột khóa hoặc trường khó thay đổi sau khi triển khai.

Ví dụ:

| Giá trị cần lưu | Chọn kiểu | Lý do |
|---|---|---|
| Đánh giá chất lượng từ 0 đến 5 | **tinyint** | Miền đóng, rất nhỏ |
| Mã trạng thái giao thức nằm trong khoảng 100 đến 599 | **smallint** | Vượt 127 nhưng vừa 16 bit |
| Số mili độ C trong khoảng −50.000 đến 150.000 | **int** | Có âm, vượt `smallint`; dùng số nguyên để giữ độ phân giải 0,001 °C |
| Số byte đã truyền: 5.000.000.000 | **bigint** | Vượt `int` nhưng vừa 64 bit |
| Số tổ hợp tính toán: 18.446.744.073.709.551.616 | **varint** | Bằng \(2^{64}\), vượt `bigint` |
| Mã sản phẩm `"0000123"` | **text**, không phải kiểu số | Số 0 đầu là một phần của định danh |
| Số tiền 19,95 theo đơn vị tiền lớn | **decimal** hoặc **bigint** theo đơn vị nhỏ nhất | Năm kiểu đang học không biểu diễn phần thập phân trực tiếp |

Không mặc định rằng giá trị “chỉ dương” sẽ có gấp đôi miền dương của kiểu có dấu. Ví dụ, nếu nhận **unsigned 32-bit** từ giao thức ngoài (0 đến 4.294.967.295), nên ánh xạ sang **bigint**, đồng thời kiểm tra miền 0..4.294.967.295 ở tầng ứng dụng.

### 2.2. tinyint và smallint: giá trị nhỏ có giới hạn rõ ràng

**tinyint** là 8 bit có dấu. Phù hợp cho một số điểm, mức độ hoặc mã nhỏ biết chắc không vượt 127. Một điều dễ nhầm là số **255 không vừa tinyint** trong Cassandra.

**smallint** là 16 bit có dấu. Đây là lựa chọn hợp lý khi danh mục giá trị vượt 127 nhưng vẫn trong ±32.767. Ví dụ, mã HTTP 200/404/503 có thể lưu bằng `smallint`; lưu bằng `tinyint` sẽ vượt biên.

Cần phân biệt mã nghiệp vụ dạng số với mã có ý nghĩa văn bản. Nếu trạng thái là `"OK"`, `"TIMEOUT"`, `"PENDING_REVIEW"`, dùng **text** hoặc một biểu diễn đã được chuẩn hóa giữa các dịch vụ; đừng gán số thứ tự rồi phụ thuộc vào thứ tự enum Java nếu không có hợp đồng ánh xạ bền vững.

### 2.3. int và bigint: mặc định thực dụng cho nhiều số đếm

**int** thường vừa cho số lượng trong một trang dữ liệu, chỉ số bắt đầu từ 0, thời lượng ngắn tính bằng mili giây, hoặc đại lượng đã giới hạn. **bigint** phù hợp với offset lớn, bộ đếm tích lũy, số byte, ID số 64 bit do nguồn ngoài phát hành và số tiền theo đơn vị nhỏ nhất.

Tuy nhiên, `bigint` **không tự biến một phép tăng thành thao tác nguyên tử**. Nếu hai ứng dụng cùng đọc `total = 10` rồi đều ghi `total = 11`, một lần tăng có thể bị mất. Cassandra xử lý xung đột theo metadata ghi và mô hình nhất quán, không dựa trên độ rộng của `bigint`. Khi cần đếm phân tán, phải thiết kế cơ chế ghi nhận sự kiện/tổng hợp hoặc cân nhắc **counter** với đặc tính riêng của nó.

**Không đánh đồng timestamp với bigint** chỉ vì cả hai liên quan đến số 64 bit. Nếu một cột mang ngữ nghĩa thời điểm ở độ phân giải mili giây, kiểu **timestamp** và Java **Instant** giúp diễn đạt rõ ý nghĩa; `bigint` thích hợp khi bạn thực sự cần một số nguyên, ví dụ epoch nanoseconds tự định nghĩa hoặc offset sự kiện, và phải tài liệu hóa đơn vị.

### 2.4. varint: dùng khi số nguyên vượt 64 bit thật sự cần thiết

**varint** mã hóa số nguyên có dấu với độ dài thay đổi theo độ lớn giá trị, dùng biểu diễn bù hai. Giá trị càng lớn có thể cần càng nhiều byte. Nó phù hợp cho:

- Kết quả tổ hợp hoặc thống kê chính xác vượt \(2^{63}-1\).
- Giá trị đầu vào từ hệ thống ngoài dùng số nguyên lớn hơn 64 bit.
- Kết quả tính toán cần bảo toàn toàn bộ chữ số, không cho phép làm tròn.

**varint không phải kiểu nén thông minh thay thế mặc định cho bigint**. Mặc dù một số nguyên nhỏ có thể cần ít byte dữ liệu, lợi ích tổng thể còn phụ thuộc metadata của cell, số dòng, mô hình truy cập và chi phí giải mã; không suy ra `varint` sẽ luôn tiết kiệm hơn hay nhanh hơn `bigint`.

Nếu số có phần thập phân, **varint không giữ được phần lẻ**. Dùng **decimal** khi cần số thập phân chính xác; dùng **float/double** khi đại lượng đo chấp nhận sai số dấu phẩy động.

## 3. Lựa chọn kiểu trong bảng thiết kế theo truy vấn

Bối cảnh hệ thống thu thập dữ liệu: “Lấy tối đa 100 mẫu mới nhất của một thiết bị trong một ngày; mỗi mẫu có trạng thái, số lần retry, nhiệt độ ở đơn vị milli-degree và tổng số byte chuyển”.

~~~cql
CREATE TABLE readings_by_device_day (
    device_id uuid,
    reading_day date,
    sample_no bigint,
    quality_code tinyint,
    retry_count smallint,
    temperature_milli_c int,
    transferred_bytes bigint,
    PRIMARY KEY ((device_id, reading_day), sample_no)
) WITH CLUSTERING ORDER BY (sample_no DESC);
~~~

Cột số ở đây được chọn theo ngữ nghĩa:

| Cột | Kiểu | Giải thích |
|---|---|---|
| `sample_no` | **bigint** | Số thứ tự do nguồn dữ liệu cấp, có thể tăng vượt 32 bit |
| `quality_code` | **tinyint** | Mã chất lượng 0–5, miền được giới hạn |
| `retry_count` | **smallint** | Số lần thử cho một mẫu, với ràng buộc nghiệp vụ 0–32.767 |
| `temperature_milli_c` | **int** | Số nguyên đã nhân 1.000, lưu được giá trị âm và tránh sai số binary float cho độ phân giải cố định |
| `transferred_bytes` | **bigint** | Một mẫu có thể báo số byte tích lũy lớn hơn 2,147 tỷ |

**Khóa chính** gồm partition key kép `(device_id, reading_day)` và clustering key `sample_no`. Cassandra băm partition key để phân phối dữ liệu trên cluster; `sample_no` quyết định sắp xếp giảm dần **bên trong phân vùng**. Không phải các dòng trong toàn cluster được sắp xếp theo số thứ tự.

~~~cql
INSERT INTO readings_by_device_day (
    device_id, reading_day, sample_no,
    quality_code, retry_count, temperature_milli_c, transferred_bytes
) VALUES (
    123e4567-e89b-12d3-a456-426614174000, '2026-11-21', 1002,
    2, 300, 23875, 5000000000
);

SELECT sample_no, quality_code, retry_count,
       temperature_milli_c, transferred_bytes
FROM readings_by_device_day
WHERE device_id = 123e4567-e89b-12d3-a456-426614174000
  AND reading_day = '2026-11-21'
LIMIT 100;
~~~

Truy vấn cung cấp đầy đủ partition key và tận dụng thứ tự clustering `sample_no DESC`. Nếu yêu cầu “tìm mọi mẫu có `quality_code = 2` trên toàn bộ thiết bị”, chỉ đổi `quality_code` sang `int` hay `bigint` cũng **không** làm truy vấn đó hiệu quả: cần thiết kế một đường truy cập khác phù hợp với lượng dữ liệu thực tế.

Mô hình theo ngày cũng không bảo đảm phân vùng đủ nhỏ với thiết bị phát hàng triệu mẫu/giây; khi đó cần điều chỉnh bucket, shard hoặc kiến trúc ingest dựa trên dung lượng và tải đo được. Độ rộng của kiểu số ảnh hưởng kích thước giá trị, nhưng phân vùng và mẫu truy vấn vẫn là yếu tố quyết định chính cho độ trễ đọc.

**Lưu ý về khóa:** số thứ tự phải được cấp ổn định bởi nguồn hoặc cơ chế cấp phát riêng. Cassandra không tự tạo dãy `AUTO_INCREMENT` cho cột `bigint`. Khi retry cùng một sự kiện, dùng lại **cùng `device_id`, `reading_day`, `sample_no`** để tránh tạo dòng trùng.

## 4. Thử miền giá trị với CQL

Một bảng độc lập để thử `varint` vượt miền `bigint`:

~~~cql
CREATE TABLE exact_totals_by_job (
    job_id uuid PRIMARY KEY,
    paths_count varint,
    completed_steps bigint
);

INSERT INTO exact_totals_by_job (job_id, paths_count, completed_steps)
VALUES (
    11111111-1111-4111-8111-111111111111,
    18446744073709551616,
    5000000000
);

SELECT paths_count, completed_steps
FROM exact_totals_by_job
WHERE job_id = 11111111-1111-4111-8111-111111111111;
~~~

`18446744073709551616` bằng \(2^{64}\), lớn hơn giá trị tối đa của `bigint`. Kiểu `varint` bảo toàn nguyên giá trị. `5000000000` vừa `bigint`, nhưng vượt `int`.

Những giá trị **không hợp lệ** về miền:

~~~text
tinyint   :  128                   # vượt giới hạn dương 127
tinyint   : -129                   # nhỏ hơn giới hạn âm -128
smallint  :  32768                 # vượt giới hạn dương 32767
int       :  2147483648            # vượt giới hạn dương 2147483647
bigint    :  9223372036854775808   # vượt giới hạn dương 9223372036854775807
~~~

Đó là ví dụ biên để kiểm tra schema và validation, **không phải script CQL để chạy**. Hãy kiểm tra dữ liệu ở ứng dụng trước khi bind: việc một literal là số nguyên hợp lệ trong cú pháp CQL không đồng nghĩa nó vừa miền của cột đích.

**Số âm** được hỗ trợ ở cả năm kiểu; ví dụ `temperature_milli_c = -5000` là −5,000 °C nếu đơn vị được định nghĩa là phần nghìn độ. Nếu nghiệp vụ cấm âm, Cassandra không tự hiểu quy tắc đó từ kiểu `int`; validation phải được thực hiện ở biên ghi dữ liệu.

## 5. Java Driver 4.x: bind đúng kiểu, tránh ép kiểu âm thầm

Trong Apache Cassandra Java Driver 4.x, các phương thức được dùng phổ biến:

| CQL | Java | Ghi với prepared statement | Đọc từ `Row` |
|---|---|---|---|
| `tinyint` | `byte` | `setByte(...)` | `getByte(...)` |
| `smallint` | `short` | `setShort(...)` | `getShort(...)` |
| `int` | `int` | `setInt(...)` | `getInt(...)` |
| `bigint` | `long` | `setLong(...)` | `getLong(...)` |
| `varint` | `BigInteger` | `setBigInteger(...)` | `getBigInteger(...)` |

Mẫu ghi vào hai bảng đã tạo (giả sử `session` là `CqlSession` đã kết nối và chọn keyspace phù hợp):

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.math.BigInteger;
import java.time.LocalDate;
import java.util.UUID;

// CqlSession session = ...; // tạo theo cấu hình cluster của ứng dụng

UUID deviceId = UUID.fromString("123e4567-e89b-12d3-a456-426614174000");

PreparedStatement insertReading = session.prepare(
    "INSERT INTO readings_by_device_day "
  + "(device_id, reading_day, sample_no, quality_code, retry_count, "
  + " temperature_milli_c, transferred_bytes) "
  + "VALUES (?, ?, ?, ?, ?, ?, ?)");

BoundStatement reading = insertReading.boundStatementBuilder()
    .setUuid(0, deviceId)
    .setLocalDate(1, LocalDate.parse("2026-11-21"))
    .setLong(2, 1002L)
    .setByte(3, (byte) 2)
    .setShort(4, (short) 300)
    .setInt(5, 23875)
    .setLong(6, 5_000_000_000L)
    .build();

session.execute(reading);

PreparedStatement insertTotal = session.prepare(
    "INSERT INTO exact_totals_by_job "
  + "(job_id, paths_count, completed_steps) VALUES (?, ?, ?)");

UUID jobId = UUID.fromString("11111111-1111-4111-8111-111111111111");

BigInteger pathsCount = new BigInteger("18446744073709551616");
BoundStatement total = insertTotal.boundStatementBuilder()
    .setUuid(0, jobId)
    .setBigInteger(1, pathsCount)
    .setLong(2, 5_000_000_000L)
    .build();

session.execute(total);
~~~

**Tại sao `5_000_000_000L` cần hậu tố `L`?** Trong Java, literal số nguyên không có hậu tố thường phải vừa `int`; `L` yêu cầu kiểu `long`. Đây là quy tắc của **Java**, không phải cú pháp literal CQL. `new BigInteger("...")` bảo toàn mọi chữ số trong giá trị rất lớn.

**Không dùng `(byte) userInput` hoặc `(short) userInput` trên dữ liệu chưa kiểm tra.** Phép ép kiểu hẹp ở Java có thể cắt bỏ các bit cao:

~~~java
int input = 200;
byte wrong = (byte) input;    // -56, không còn là 200

if (input < Byte.MIN_VALUE || input > Byte.MAX_VALUE) {
    throw new IllegalArgumentException("quality_code vượt miền tinyint");
}
byte checked = (byte) input;  // Chỉ ép kiểu sau khi đã kiểm tra
~~~

Tương tự, nếu một giá trị `BigInteger` phải chuyển xuống `long`, dùng **`longValueExact()`** để báo lỗi khi vượt miền, thay vì `longValue()` có thể mất thông tin:

~~~java
BigInteger tooLarge = new BigInteger("9223372036854775808");

try {
    long value = tooLarge.longValueExact();
    // Sẽ không tới đây vì giá trị vượt Long.MAX_VALUE.
} catch (ArithmeticException ex) {
    // Chọn lưu varint, từ chối giá trị, hoặc thay đổi hợp đồng dữ liệu.
}
~~~

Khi đọc cột có thể vắng mặt/`null`, kiểm tra **`row.isNull("ten_cot")`** trước khi gọi getter primitive. Zero, giá trị không có dữ liệu và giá trị không biết là ba ý nghĩa nghiệp vụ khác nhau.

## 6. Tràn số xảy ra trước khi ghi Cassandra

Cassandra không thay bạn kiểm tra phép cộng ở Java. Ví dụ:

~~~java
int current = Integer.MAX_VALUE;
int incorrect = current + 1;  // -2147483648: tràn số int của Java

int safe = Math.addExact(current, 1); // ném ArithmeticException

long promoted = (long) current + 1L;  // 2147483648: đúng trong long

long large = Long.MAX_VALUE;
BigInteger exact = BigInteger.valueOf(large).add(BigInteger.ONE);
// 9223372036854775808: cần varint nếu ghi nguyên giá trị
~~~

Quy tắc chọn theo kết quả:

- Cộng/trừ hai `int` có thể vượt `int`; kiểm tra với **`Math.addExact`** hoặc nâng lên `long` trước phép tính.
- Nhân hai `long` có thể vượt `long` rất nhanh; nếu miền kết quả thực sự lớn hơn 64 bit, dùng **`BigInteger`** từ đầu.
- Nếu dữ liệu đến từ JSON, CSV, API khác, parser hoặc serializer có thể giới hạn số ở 64 bit hay biến tất cả số thành `double`. Phải giữ chuỗi chữ số hoặc `BigInteger` khi nhận số nguyên lớn; nếu chuyển qua `double` trước đó thì độ chính xác có thể đã mất.
- Nếu hệ thống làm tròn nhiệt độ/giá trị theo đơn vị cố định thành `int`, phải thống nhất quy tắc làm tròn, đơn vị và kiểm tra miền trước khi ghi.

**Lỗi miền và lỗi đồng thời là hai vấn đề riêng:** tăng từ 2.147.483.647 lên 2.147.483.648 gây tràn `int`; hai worker cùng đọc 99 rồi ghi 100 gây mất cập nhật. Nâng kiểu thành `bigint` xử lý được miền số, nhưng không tự giải quyết cạnh tranh khi cập nhật.

## 7. bigint không phải counter: tăng số trong hệ phân tán

Ba trường hợp dễ nhầm:

| Yêu cầu | Cách tiếp cận |
|---|---|
| Ghi một số tổng do hệ thống khác đã tính xong | **int/bigint/varint** tùy miền; ghi cả giá trị |
| Cộng giảm một bộ đếm phân tán, chấp nhận các đặc tính counter Cassandra | **counter** trong bảng được thiết kế riêng |
| Đếm chính xác sự kiện dùng để thanh toán/kiểm toán, retry không được tính trùng | Lưu sự kiện với ID ổn định, xử lý idempotency và tổng hợp theo quy trình kiểm soát |

**counter** trong Cassandra là một kiểu đặc biệt, dù Java thường đọc kết quả của nó bằng `long`. Nó không phải `bigint` có cú pháp cộng tắt: cột counter có hạn chế riêng trong bảng, truy vấn cập nhật dùng biểu thức cộng/trừ trên counter, và retry sau timeout có thể khiến một lần cộng được áp dụng nhiều lần.

~~~cql
-- Chỉ minh họa bảng counter riêng; không thay thế bảng sự kiện nguồn.
CREATE TABLE page_views_by_page (
    page_id uuid PRIMARY KEY,
    view_count counter
);

UPDATE page_views_by_page
SET view_count = view_count + 1
WHERE page_id = 11111111-1111-4111-8111-111111111111;
~~~

Nếu ứng dụng gửi lại cùng câu `UPDATE` sau khi không biết lần trước đã được xử lý chưa, có nguy cơ đếm hai lần. Muốn **exactly-once theo sự kiện**, cần một thiết kế nghiệp vụ có ID duy nhất và cách quản lý trùng lặp; chỉ chọn kiểu số không tạo được bảo đảm đó.

Với cột `bigint`/ `varint` bình thường, đọc một số, cộng ở client, rồi ghi lại không bảo đảm atomic khi nhiều writer cạnh tranh. Có thể cần cơ chế điều phối, ghi sự kiện bất biến hoặc điều kiện ghi (LWT) tùy yêu cầu nhất quán và throughput.

## 8. Tác động lên khóa, replication, compaction và khả năng mở rộng

### 8.1. Cột số trong khóa có ý nghĩa truy vấn

Trong bảng ví dụ, `sample_no bigint` là **clustering key**. Cassandra sắp xếp giá trị này theo thứ tự **số học** đúng với kiểu, khác với việc lưu một số dưới dạng `text`: chuỗi `"100"` và `"20"` được so theo thứ tự từ điển, không phải 100 và 20 như số nguyên.

Chọn `bigint` thay `int` cho khóa nếu miền thứ tự sẽ vượt 32 bit; thay đổi kiểu một khóa của bảng đã có dữ liệu thường kéo theo quy trình tạo bảng mới, sao chép dữ liệu và chuyển ứng dụng. Nếu khóa là ID bên ngoài như `"00042"`, phải giữ **text** để không mất nghĩa của định danh.

### 8.2. Kích thước dữ liệu và chi phí vận hành

Về giá trị số được mã hóa, `tinyint` / `smallint` / `int` / `bigint` dùng lần lượt 1/2/4/8 byte, trong khi `varint` thay đổi theo độ lớn số. Nhưng mỗi row/cell trong Cassandra còn có metadata, tombstone, cấu trúc phân vùng, chỉ mục và chi phí nén, nên không thể ước tính tổng dung lượng bảng chỉ bằng cách lấy số byte kiểu nhân với số dòng.

Chọn kiểu hẹp tiết kiệm dữ liệu giá trị khi có nhiều bản ghi; chọn kiểu quá hẹp rồi di chuyển hàng tỷ row vì vượt miền có thể còn tốn kém hơn. Dùng `varint` rộng ở hot path cũng có chi phí codec/CPU và dung lượng khác `bigint`; đo bằng workload thực tế nếu ảnh hưởng đến SLA.

**Compaction** sắp xếp, gộp SSTable và xử lý dữ liệu cũ theo quy tắc lưu trữ; nó không tự mở rộng `int` khi giá trị vượt miền. **Repair** giúp đồng bộ dữ liệu giữa replica; nó không sửa phép ép kiểu bị tràn ở client. Replication và consistency level quyết định phạm vi xác nhận đọc/ghi, không thay thế validation số.

### 8.3. Cẩn trọng khi đổi kiểu

Việc đổi `int` thành `bigint` hoặc `bigint` thành `varint` sau khi chạy production cần kiểm tra hỗ trợ của phiên bản Cassandra và giới hạn thay đổi schema, đặc biệt với **primary key**. Không giả định lệnh `ALTER TABLE ... ALTER ... TYPE` sẽ chuyển đổi an toàn các row hiện hữu.

Một lộ trình đáng tin cậy thường gồm:

1. Tạo bảng mới có cột và khóa đúng miền, vẫn đáp ứng truy vấn cần phục vụ.
2. Chuyển code Java sang đúng codec/getter/setter; kiểm tra logic tính toán và nguồn dữ liệu trước bước ghi.
3. Backfill dữ liệu cũ, tổ chức dual-write hoặc đổi luồng cập nhật có kiểm soát; xử lý ID và retry nhất quán.
4. So sánh số bản ghi và giá trị biên, chuyển luồng đọc, rồi thu hồi bảng cũ theo chính sách lưu trữ.

Nếu có nhiều dịch vụ cùng đọc/ghi, cần cập nhật hợp đồng API và serialization trước. Một client vẫn dùng `int` có thể thất bại hoặc làm mất số dù Cassandra đã dùng `bigint` hoặc `varint`.

## 9. Các lỗi thường gặp và cách phòng tránh

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng `tinyint` cho số trong khoảng 0–255 | 128–255 vượt miền có dấu | Dùng `smallint`, validate 0–255 |
| Dùng `int` cho tổng byte không giới hạn | Tràn tại 2.147.483.647 | Dùng `bigint` hoặc `varint` nếu thực sự vượt 64 bit |
| Dùng `bigint` nhưng tính tổng bằng `int` ở client | Sai số trước lúc bind | Tính bằng `long`/`BigInteger`, kiểm tra tràn |
| Dùng `longValue()` cho mọi `BigInteger` | Có thể cắt mất bit cao | `longValueExact()` và xử lý trường hợp vượt miền |
| Lưu định danh có số 0 đầu bằng kiểu số | Mất định dạng định danh | Dùng `text` |
| Dùng `varint` cho giá 19,95 | Không biểu diễn phần lẻ | Dùng `decimal` hoặc `bigint` theo đơn vị nhỏ nhất |
| Xem `bigint` như bộ đếm cập nhật nguyên tử | Mất lần tăng do concurrent writers | Thiết kế event/aggregation hoặc counter phù hợp |
| Đổi kiểu khóa mà không tính tới truy vấn | Phải chuyển schema và ứng dụng | Chọn miền dự phòng và thiết kế migration trước |
| Để ứng dụng tự thay đổi đơn vị `temperature_milli_c` | Cùng một số mang nhiều ý nghĩa | Ghi rõ đơn vị, scale và quy tắc làm tròn trong hợp đồng |

## 10. Checklist khi review bảng có số nguyên

- [ ] Cột có thực sự mang giá trị **số** cần tính toán hoặc sắp xếp số học, thay vì một **mã định danh dạng chữ số**?
- [ ] Đã xác định min/max, có số âm không, giá trị tích lũy hay reset và dự báo tăng trưởng chưa?
- [ ] `tinyint`, `smallint`, `int`, `bigint` đã được kiểm tra theo miền **có dấu**, nhất là khi nhận số không dấu từ hệ khác?
- [ ] Nếu dùng `varint`, có yêu cầu chính xác vượt 64 bit thật sự và đã kiểm tra chi phí mã hóa/driver?
- [ ] Các phép cộng, nhân, ép kiểu hoặc parse ở Java có thể tràn **trước khi ghi Cassandra** không?
- [ ] Đã thống nhất đơn vị đo (byte, mili giây, milli-degree, minor currency units) và quy tắc làm tròn?
- [ ] Các cột thuộc primary key có đủ miền lâu dài, khớp mẫu truy vấn và giữ ID ổn định khi retry?
- [ ] Phương thức `setByte`, `setShort`, `setInt`, `setLong`, `setBigInteger` và getter có đúng CQL schema?
- [ ] Nhu cầu tăng/giảm đếm đã được thiết kế cho concurrency/idempotency, không chỉ chọn một kiểu số rộng?
- [ ] Nếu cần thay đổi kiểu về sau, đã có phương án bảng mới, backfill và chuyển ứng dụng?

**Ghi nhớ:** **tinyint → smallint → int → bigint** lần lượt mở rộng miền số nguyên có dấu cố định; **varint** dành cho số nguyên chính xác vượt 64 bit. Kiểu phù hợp phải khớp **miền nghiệp vụ**, **độ chính xác của phép tính**, **mẫu truy cập theo partition/clustering** và **kiểu Java**. Độ rộng lớn hơn giải quyết được một phần giới hạn biểu diễn, nhưng không tự tạo bộ đếm nguyên tử hay bảo đảm nhất quán nghiệp vụ trong hệ phân tán.

