# Kiểm tra chuyển đổi đi-về để phát hiện mất dữ liệu

> **Ngữ cảnh:** Spring Framework → Data Access → Kiểu dữ liệu đặc biệt. Bài học hướng dẫn kiểm thử **round-trip** khi lưu giá trị Java qua Spring JDBC xuống cơ sở dữ liệu rồi đọc lại, nhằm phát hiện dữ liệu bị làm tròn, cắt bớt, đổi múi giờ, đổi biểu diễn, sai kiểu hoặc mất thông tin mà không nhất thiết có exception.

## 1. Chuyển đổi đi-về (round-trip) là gì?

Một luồng lưu/đọc thường trải qua nhiều bước:

```text
Giá trị domain Java ban đầu
        |
        v
Chuẩn bị tham số / converter / PreparedStatement
        |
        v
JDBC driver -> SQL type -> cột và quy tắc lưu của DB
        |
        v
Dữ liệu đã commit trong cơ sở dữ liệu
        |
        v
ResultSet / RowMapper / converter
        |
        v
Giá trị domain Java đọc lại
```

Phép kiểm tra cơ bản là:

```text
original = giá trị Java đầu vào
persisted = readFromDatabase(writeToDatabase(original))

assert equivalent(original, persisted)
```

Từ khóa là **`equivalent` (tương đương theo hợp đồng nghiệp vụ)**. Không phải lúc nào `Object.equals(...)` cũng là phép so sánh đúng:
- `BigDecimal("12.0").equals(BigDecimal("12.00"))` là `false` do khác `scale`, nhưng `compareTo(...) == 0` cho biết chúng bằng nhau về **giá trị số**.
- Hai `OffsetDateTime` có offset khác nhau vẫn có thể biểu diễn **cùng một instant**. Nếu nghiệp vụ chỉ cần mốc thời gian, so sánh `toInstant()`.
- Hai JSON có thứ tự key khác nhau có thể tương đương về cấu trúc, nhưng sự khác biệt kiểu số, key trùng, thứ tự phần tử mảng hoặc `null` có thể quan trọng.
- Hai `byte[]` phải so sánh bằng `Arrays.equals(...)`, không dùng `byte[].equals(...)` (so sánh identity của mảng).

**Câu hỏi đầu tiên:** “Giữ nguyên điều gì?” Có ba mức thường gặp:

1. **Không mất giá trị nghiệp vụ:** ví dụ `12.0` và `12.00` được coi là cùng một số tiền nếu scale không mang ý nghĩa.
2. **Không mất biểu diễn:** ngoài giá trị, giữ scale, offset gốc, đúng dạng Unicode, thứ tự trường JSON, từng byte hoặc metadata.
3. **Biến đổi có kiểm soát:** ví dụ cho phép làm tròn tới 2 chữ số thập phân, chuẩn hóa UTC, chuẩn hóa Unicode hoặc canonical JSON; phải công bố chính sách và so với **kết quả kỳ vọng sau chuẩn hóa**, đồng thời không che giấu giá trị bị loại bỏ.

Nếu chưa xác định mức bảo toàn, một bài kiểm thử “pass” có thể đang bỏ sót mất dữ liệu thực sự.

## 2. Ba nơi có thể gây mất dữ liệu

Round-trip test nên tách ba lớp để chẩn đoán lỗi:

| Vị trí | Ví dụ lỗi | Biện pháp xác minh |
| --- | --- | --- |
| **Trước khi ghi:** mapping DTO → domain hoặc binder JDBC | Chuyển `BigDecimal` sang `double`, `enum.name()` thay cho mã ổn định, format ngày bỏ nano | Kiểm tra giá trị ngay sau converter, unit test encode/decode |
| **Trong DB:** cột/driver ép kiểu, làm tròn, giới hạn độ dài | `DECIMAL(8,2)` không chứa đủ chữ số lẻ; `TIMESTAMP(3)` không giữ nano; `CHAR` đệm khoảng trắng | Kiểm tra DDL, SQL type, đọc raw value bằng SQL/JDBC, thử tại DB thực |
| **Sau khi đọc:** `ResultSet`/`RowMapper`/converter | `getInt()` làm mất null nếu không `wasNull()`, parse JSON số thành `double`, chuyển timezone sai | So sánh raw DB value với domain value sau mapper |

Spring JDBC hỗ trợ quản lý connection, bind tham số và ánh xạ kết quả, nhưng **không bảo đảm mọi giá trị đặc biệt được round-trip lossless** trên mọi DB/driver. Cấu trúc cột, kiểu dữ liệu, converter và cách so sánh phải do ứng dụng quyết định và kiểm thử.

Khi phát hiện sai biệt, giữ ba mẫu ở môi trường kiểm thử (đầu vào, dạng trong DB, đầu ra) để xác định lỗi ở bước ghi hay đọc. Với dữ liệu nhạy cảm, chỉ lưu checksum/độ dài/thông tin đã ẩn thích hợp; tránh đưa giá trị thô vào log sản xuất.

## 3. Hợp đồng lưu trữ cho các kiểu đặc biệt

Trước khi viết test, ghi rõ **kiểu Java → kiểu SQL → kỳ vọng bảo toàn**:

| Giá trị Java | Kiểu SQL điển hình | Rủi ro round-trip | So sánh đúng theo hợp đồng |
| --- | --- | --- | --- |
| `BigDecimal` | `DECIMAL(p,s)` / `NUMERIC(p,s)` | Giảm scale, làm tròn, overflow precision | `compareTo == 0` cho giá trị; kiểm thêm `scale` nếu scale quan trọng |
| `LocalDateTime` | `TIMESTAMP(p)` không timezone | Mất nano; mơ hồ khi coi là thời điểm tuyệt đối | `equals` khi kỳ vọng ngày/giờ địa phương chính xác |
| `Instant`/`OffsetDateTime` | `TIMESTAMP WITH TIME ZONE` hoặc epoch theo contract | Thay đổi offset, lệch timezone, mất fractional seconds | `toInstant().equals(...)` nếu chỉ cần instant; kiểm riêng offset nếu phải giữ |
| `LocalDate` | `DATE` | Đổi ngày do ép qua timestamp + timezone | `LocalDate.equals` |
| `UUID` | `UUID`, `BINARY(16)` hoặc `CHAR(36)` | Sai byte order, dấu gạch nối, case/parse | So sánh đối tượng `UUID` sau decode |
| `byte[]` | `VARBINARY`/`BLOB` | Truncate, mã hóa sai, chuyển text làm hỏng byte | `Arrays.equals`, kiểm length/hash |
| `String` Unicode | `VARCHAR`/`NVARCHAR`/`TEXT` | Charset sai, giới hạn độ dài, normalization, trim | Exact code points hoặc quy tắc NFC/NFD được công bố |
| JSON | `JSON`/`JSONB`/text theo DB | Mất precision số, key/array, `null`, canonicalization | So sánh cây JSON + invariant từng trường hoặc byte-for-byte khi cần |
| Enum/domain code | `VARCHAR`, `SMALLINT`, enum riêng của DB | Đổi tên hằng, ordinal thay đổi, case/default | Round-trip mã nghiệp vụ ổn định, từ chối giá trị lạ |
| Danh sách/array | SQL `ARRAY`, bảng con, JSON | Sai thứ tự, null phần tử, đổi kiểu số | So sánh theo thứ tự/kích thước/null hoặc so sánh tập nếu contract là set |

**Giới hạn dữ liệu bắt buộc phải rõ:** `DECIMAL(p,s)` có tối đa `p` chữ số có nghĩa và `s` chữ số thập phân (chi tiết tùy DB); `TIMESTAMP(p)` có `p` chữ số phần giây; chiều dài `VARCHAR(n)` và cách đếm ký tự/byte, cách xử lý cắt bớt, cùng quy tắc `JSON` phụ thuộc hệ quản trị.

Nếu ứng dụng tuyên bố không mất nano nhưng cột chỉ là `TIMESTAMP(3)`, kỳ vọng đó đã mâu thuẫn ngay với schema. Test round-trip sẽ phơi bày sai lệch và hướng tới **nâng cấp cột**, **giới hạn đầu vào**, hoặc **thay đổi hợp đồng nghiệp vụ**.

## 4. Thiết kế phép so sánh: đừng pass sai, đừng fail sai

Ví dụ tiền:

```java
import java.math.BigDecimal;

BigDecimal before = new BigDecimal("12.0");
BigDecimal after = new BigDecimal("12.00");

System.out.println(before.equals(after));         // false: scale khác
System.out.println(before.compareTo(after) == 0); // true: cùng giá trị số
```

Nếu scale là thành phần của miền dữ liệu (ví dụ biểu diễn tỷ lệ với độ chính xác khác nhau), so sánh thêm `before.scale() == after.scale()`. Nếu chính sách chỉ cần giá trị số, dùng `compareTo == 0`.

**Tránh comparator quá dễ dãi:** dùng sai số `epsilon` cho tiền có thể cho qua một thay đổi 0,01 vốn là mất tiền thực. Với phép đo có sai số được phép, xác định rõ absolute/relative tolerance theo đơn vị, xử lý `NaN`, vô cực và cả giá trị biên; không tự mặc định `epsilon = 0.001` cho tất cả.

Với thời gian:

```java
import java.time.OffsetDateTime;

OffsetDateTime a = OffsetDateTime.parse("2026-10-30T09:00:00+07:00");
OffsetDateTime b = OffsetDateTime.parse("2026-10-30T02:00:00Z");

System.out.println(a.equals(b)); // false: offset khác
System.out.println(
    a.toInstant().equals(b.toInstant())
); // true: cùng instant
```

Nếu hệ thống phải hiển thị đúng offset ban đầu, phép so sánh theo instant là **chưa đủ**; phải giữ offset/zone riêng. Ngược lại, nếu hợp đồng chỉ cần mốc thời gian tuyệt đối, so sánh offset bằng `equals` có thể báo sai dù không mất instant.

Với JSON, nên parse về cây có hỗ trợ kiểu số chính xác, so sánh field và phần tử có ý nghĩa. Đừng chỉ `JSON.stringify`/chuỗi serialized nếu thứ tự object key không quan trọng; nhưng cũng đừng tự sort mảng hoặc xóa `null` nếu contract chưa cho phép.

## 5. Ví dụ chạy được: phát hiện làm tròn tiền và mất nano giây

Ví dụ độc lập dùng **Java 17+, Maven, Spring JDBC 6.2.19, H2 2.3.232**. Chương trình ghi một `BigDecimal`, `LocalDateTime` có nano giây và một mảng byte. Sau khi DB lưu, đọc lại bằng `JdbcTemplate` và `RowMapper`, rồi kiểm tra round-trip của từng trường.

Để quan sát mất dữ liệu, schema cố ý dùng:
- `DECIMAL(8,2)`: chỉ lưu được 2 chữ số sau dấu thập phân.
- `TIMESTAMP(3)`: chỉ lưu mili giây.
- `VARBINARY(8)`: đủ chỗ cho mảng 3 byte nên dự kiến không mất byte.

Cấu trúc thư mục:

```text
jdbc-roundtrip-demo/
├── pom.xml
└── src/main/java/demo/RoundTripDemo.java
```

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>jdbc-roundtrip-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-jdbc</artifactId>
      <version>6.2.19</version>
    </dependency>
    <dependency>
      <groupId>com.h2database</groupId>
      <artifactId>h2</artifactId>
      <version>2.3.232</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.6.3</version>
      </plugin>
    </plugins>
  </build>
</project>
```

Tạo `src/main/java/demo/RoundTripDemo.java`:

```java
package demo;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.Arrays;
import java.util.Objects;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public final class RoundTripDemo {
    private RoundTripDemo() {
    }

    private record Measurement(
            BigDecimal amount,
            LocalDateTime occurredAt,
            byte[] payload) {
    }

    public static void main(String[] args) {
        var dataSource = new DriverManagerDataSource(
            "jdbc:h2:mem:roundtrip;DB_CLOSE_DELAY=-1", "sa", ""
        );
        var jdbc = new JdbcTemplate(dataSource);

        jdbc.execute(
            "CREATE TABLE measurement (" +
            "id BIGINT PRIMARY KEY, " +
            "amount DECIMAL(8,2) NOT NULL, " +
            "occurred_at TIMESTAMP(3) NOT NULL, " +
            "payload VARBINARY(8) NOT NULL)"
        );

        Measurement before = new Measurement(
            new BigDecimal("12.3456"),
            LocalDateTime.parse("2026-10-30T09:10:11.123456789"),
            new byte[] {0x01, (byte) 0x80, 0x7f}
        );

        int inserted = jdbc.update(
            "INSERT INTO measurement " +
            "(id, amount, occurred_at, payload) VALUES (?, ?, ?, ?)",
            1L, before.amount(), before.occurredAt(), before.payload()
        );

        Measurement after = Objects.requireNonNull(
            jdbc.queryForObject(
                "SELECT amount, occurred_at, payload " +
                "FROM measurement WHERE id = ?",
                (rs, rowNum) -> new Measurement(
                    rs.getBigDecimal("amount"),
                    rs.getObject("occurred_at", LocalDateTime.class),
                    rs.getBytes("payload")
                ),
                1L
            )
        );

        System.out.println("inserted=" + inserted);
        System.out.println(
            "amount=" + before.amount() + " -> " + after.amount()
        );
        System.out.println(
            "amountEqual=" +
            (before.amount().compareTo(after.amount()) == 0)
        );
        System.out.println(
            "time=" + before.occurredAt() + " -> " + after.occurredAt()
        );
        System.out.println(
            "timeEqual=" + before.occurredAt().equals(after.occurredAt())
        );
        System.out.println(
            "bytesEqual=" +
            Arrays.equals(before.payload(), after.payload())
        );
    }
}
```

Trong thư mục `jdbc-roundtrip-demo`, chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.RoundTripDemo
```

Các dòng **do chương trình in ra** khi chạy với H2 ở phiên bản nêu trên (không tính thông báo Maven):

```text
inserted=1
amount=12.3456 -> 12.35
amountEqual=false
time=2026-10-30T09:10:11.123456789 -> 2026-10-30T09:10:11.123
timeEqual=false
bytesEqual=true
```

Giải thích:
1. `JdbcTemplate.update(...)` trả `1` vì đã chèn một hàng. **Count bằng 1 không chứng minh nội dung được lưu nguyên vẹn.**
2. H2 làm tròn `12.3456` thành `12.35` khi ép vào `DECIMAL(8,2)`. So sánh giá trị số `compareTo(...) == 0` là `false`: đã mất độ chính xác.
3. `TIMESTAMP(3)` lưu mili giây: `.123456789` giảm về `.123`. `LocalDateTime.equals` là `false`: đã mất thông tin dưới mili giây.
4. Ba byte ban đầu có giá trị `01 80 7F` được giữ trong `VARBINARY(8)`; `Arrays.equals` là `true`.

Ví dụ dùng `LocalDateTime` cố ý để tập trung vào **precision**, không đưa múi giờ vào cùng phép thử. Với thời điểm tuyệt đối, cần một test riêng sử dụng `OffsetDateTime`/`Instant` và cột/cấu hình DB tương thích.

**Chú ý:** ví dụ không phải bằng chứng rằng mọi DB/driver sẽ làm tròn giống H2. Có DB làm tròn, cắt bớt hoặc từ chối dữ liệu; hãy chạy integration test trên DB và version driver thực tế. Đối với `VARBINARY`, một số driver xử lý byte[]/BLOB khác nhau theo cột và kích thước dữ liệu; test lại theo loại cột thực.

## 6. Phát hiện sớm trước khi gửi SQL

Round-trip test tìm thấy lỗi sau khi ghi. Để ngăn các giá trị không thể biểu diễn **ngay khi nhận đầu vào**, có thể kiểm tra giới hạn schema trước `INSERT` hoặc `UPDATE`.

Đối với `DECIMAL(8,2)`, nếu không được mất phần thập phân, dùng:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

static BigDecimal requireScale2(BigDecimal value) {
    BigDecimal exact = value.setScale(2, RoundingMode.UNNECESSARY);
    if (exact.precision() > 8) {
        throw new IllegalArgumentException("Value exceeds DECIMAL(8,2)");
    }
    return exact;
}
```

`new BigDecimal("12.3456")` khiến `setScale(2, UNNECESSARY)` ném `ArithmeticException`, vì cần làm tròn để giảm scale. `new BigDecimal("12.3400")` có thể rút về `12.34` mà **không đổi giá trị số**, dù biểu diễn scale thay đổi. Với độ lớn vượt precision, cần kiểm tra thêm giới hạn cột và integer digits; ràng buộc DB vẫn là chốt cuối.

Đối với `TIMESTAMP(3)`, chỉ chấp nhận dữ liệu đã chính xác ở mili giây nếu không muốn mất nano:

```java
import java.time.LocalDateTime;

static LocalDateTime requireMillis(LocalDateTime value) {
    if (value.getNano() % 1_000_000 != 0) {
        throw new IllegalArgumentException(
            "Sub-millisecond precision is not representable"
        );
    }
    return value;
}
```

**Không tự truncation rồi khẳng định “không mất dữ liệu”.** Nếu nghiệp vụ chủ động cho phép mất chi tiết, hãy nêu chính sách ví dụ “làm tròn theo quy tắc DB tới mili giây”, lưu bản chuẩn hóa, và test:
- `normalized = normalize(original)` theo chính sách;
- `actual = read(write(original))`;
- assert `equivalent(normalized, actual)`;
- kiểm riêng phần dữ liệu bị loại bỏ được phép hay không.

Cần phân biệt *normalize trước khi ghi* với *normalize sau khi đọc để che lỗi*. Nếu chỉ chuẩn hóa cả hai đầu sau khi đã có lỗi, test có thể pass giả.

## 7. Tách riêng bước ghi và bước đọc để định vị lỗi

Nếu `roundTrip(original) != original`, chưa thể kết luận lỗi ở JDBC bind, ở SQL type hay ở `RowMapper`. Quy trình chẩn đoán:

1. Kiểm tra kiểu, range, precision và scale của dữ liệu **trước converter**. Không chuyển qua `double` hoặc `String` tạm thời nếu làm mất precision.
2. Kiểm tra giá trị **sau converter trước khi bind** (nếu có `AttributeConverter`, mapper riêng hoặc `ConversionService`).
3. Dùng `PreparedStatement` bind đúng SQL type; với type đặc biệt và `NULL`, có thể cần `java.sql.Types`/type name rõ ràng.
4. Sau commit, lấy giá trị bằng JDBC với kiểu gần SQL gốc nhất, hoặc `CAST`/hàm DB để quan sát dạng lưu.
5. So sánh với giá trị trả ra từ `RowMapper` cuối cùng. Nếu raw SQL đúng mà domain sai, kiểm tra mapper; nếu raw SQL đã lệch, kiểm tra bind, schema và DB coercion.
6. Chạy test bằng **connection khác** hoặc transaction mới nếu cần xác minh giá trị sau commit, không chỉ đối tượng Java còn trong bộ nhớ.

Spring cho phép chỉ định SQL type thay vì để driver tự suy đoán, ví dụ với `MapSqlParameterSource`:

```java
import java.math.BigDecimal;
import java.sql.Types;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

var params = new MapSqlParameterSource()
    .addValue("amount", new BigDecimal("12.34"), Types.DECIMAL)
    .addValue("externalId", null, Types.VARCHAR);
```

Đây là **đoạn minh họa tích hợp** dùng cho các API named parameters; với `JdbcTemplate` cũng có overload nhận mảng SQL type hoặc `SqlParameterValue`. Chỉ định type có thể giải quyết lỗi bind (đặc biệt `null`), nhưng **không thay thế kiểm thử độ rộng/precision/schema**. Type đặc thù như SQL `UUID`, `JSONB`, `ARRAY`, `OTHER` đòi hỏi mapping theo DB/driver, không có quy tắc `Types.OTHER` dùng được ở mọi hệ quản trị.

`RowMapper` nên giữ nguyên thông tin mà domain yêu cầu:
- Với nullable integer, dùng `getObject(..., Integer.class)` hoặc `getInt()` kết hợp `wasNull()`; nếu chỉ gọi `getInt` có thể biến SQL `NULL` thành `0`.
- Với decimal, dùng `getBigDecimal`, tránh `getDouble` rồi `new BigDecimal(double)` nếu yêu cầu exactness.
- Với bytes, dùng `getBytes` hoặc xử lý `Blob` phù hợp, kiểm tra độ dài.
- Với date/time JDBC 4.2, có thể dùng `getObject(..., LocalDateTime.class)`/`OffsetDateTime.class` nếu DB/driver hỗ trợ. Cần kiểm thử thực tế; không suy diễn rằng mọi SQL timestamp lưu cùng thông tin timezone.

## 8. Một số case bắt buộc cho kiểu đặc biệt

### 8.1 Decimal / tiền / tỷ lệ

- Giá trị rất nhỏ (`0.0001`), dấu âm, `0`, số sát giới hạn `DECIMAL(p,s)`, số có trailing zeros, số vượt precision.
- Nếu dùng `BigDecimal`, khởi tạo từ chuỗi decimal (`new BigDecimal("0.1")`) khi giá trị gốc là số thập phân chính xác; tránh `new BigDecimal(0.1)` vì 0.1 ở dạng `double` không chính xác.
- Khi một giá trị bị làm tròn **có chủ đích**, test cả input gốc và normalized expected. Xác định rõ `RoundingMode`, đơn vị, scale và sai số được phép.
- Đảm bảo số không âm/âm, giới hạn tổng và constraint không bị phá; DB có thể báo exception nếu overflow precision, hoặc ép kiểu nếu cho phép.

### 8.2 Thời gian và timezone

Kiểm tra riêng:
- `LocalDate` dùng cho ngày lịch (ngày sinh, ngày nghỉ); không tự quy nó thành instant.
- `LocalDateTime` chứa ngày/giờ địa phương và không có timezone; nếu coi nó như instant sẽ gây mơ hồ.
- `Instant` đại diện một mốc thời gian tuyệt đối; khi lưu qua SQL type, test cùng instant sau đọc.
- `OffsetDateTime` có cả thời gian và offset; phải quyết định giữ **instant**, **offset**, hay cả hai.

Dữ liệu test nên gồm ngày tại ranh giới DST, 00:00, 23:59:59, trước/sau năm nhuận, cuối tháng, giây lẻ `.123456789`, các offset `+07:00`, `Z`, `-05:00` và phiên timezone DB/session khác nhau.

**Không mặc nhiên xem `TIMESTAMP WITHOUT TIME ZONE` và `TIMESTAMP WITH TIME ZONE` tương đương.** Cách DB lưu offset và chuyển đổi phụ thuộc vendor; nhiều DB chuẩn hóa thời điểm và không giữ nguyên offset nhập. Nếu offset gốc là thông tin nghiệp vụ, lưu riêng offset/zone ID bên cạnh instant.

### 8.3 UUID / ID dạng nhị phân

Khi lưu `UUID` vào `BINARY(16)`, test đủ 16 byte và **cùng thứ tự byte** khi decode. Khi lưu `CHAR(36)`/`VARCHAR(36)`, test parse thành cùng UUID; chữ hoa/thường ở chuỗi có thể khác nhưng đối tượng UUID không đổi.

Không tự thay đổi byte order hoặc base64/hex encoder mà không có test. Với dữ liệu ID quan trọng, so sánh sau decode với input UUID và kiểm tra tính duy nhất trong DB. Một round-trip thành công của một UUID không chứng minh mọi giá trị đều thành công; thêm UUID có byte `0x00`, `0x80`, `0xFF` và tập random.

### 8.4 JSON / object tùy biến

Thử JSON có:
- chuỗi tiếng Việt, emoji, escape, ký tự Unicode tổ hợp;
- `null`, field không xuất hiện, array rỗng, object rỗng, mảng lồng nhau;
- số rất lớn / số thập phân có nhiều chữ số; boolean và string gần giống số;
- các field có tên gần trùng và thứ tự key đảo khác nhau.

Nếu hợp đồng là **cấu trúc JSON**, parse thành tree với cách xử lý số chính xác rồi so sánh field có nghĩa. Không tự coi `{"a":1}` và `{"a":"1"}` là tương đương. Nếu cần lưu từng byte JSON gốc (chữ hoa, khoảng trắng, thứ tự key, escape), phải lưu raw text/bytes theo thiết kế; loại `JSONB` của một số DB có thể chuẩn hóa biểu diễn.

Spring JDBC có thể đọc JSON qua `getString`, `getObject` hoặc đối tượng vendor-specific, tùy driver. Xác định explicit converter/`RowMapper` và kiểm tra cả chiều ghi, đọc. `ConversionService` không tự làm cho **mọi** mapping vendor-specific qua `JdbcTemplate` trở nên an toàn.

### 8.5 Binary / BLOB

So sánh `Arrays.equals(before, after)` trên byte[]; với BLOB lớn, tính digest SHA-256 và độ dài **từ cả hai luồng**, tránh tải toàn bộ vào RAM. Digest giúp phát hiện sai biệt với xác suất rất cao nhưng không thay cho xác minh business semantic. Test byte `0x00`, các byte âm khi xem dưới kiểu `byte` Java, độ dài 0, đúng bằng giới hạn và lớn hơn giới hạn.

Đừng chuyển binary qua `new String(bytes)` rồi `getBytes()` bằng charset mặc định; các chuỗi byte tùy ý không nhất thiết là văn bản UTF-8 hợp lệ. Nếu là text, chỉ rõ `StandardCharsets.UTF_8` và chính sách invalid sequence.

### 8.6 Enum / mã kiểu miền

Không lưu `enum.ordinal()` nếu thứ tự hằng có thể thay đổi trong phiên bản phần mềm; map sang mã nghiệp vụ ổn định (ví dụ `PENDING`, `PAID`) và từ chối mã không biết thay vì âm thầm trả default. Test mã cũ trong dữ liệu lịch sử, rename/migration, chữ hoa/thường, giá trị mới và `null`.

Với enum có converter, test `decode(encode(value)) == value` cho **mọi** hằng đang hỗ trợ và các mã legacy mà ứng dụng phải đọc được. Đồng thời chạy integration test qua cột SQL thật để kiểm tra DB type, constraint và JDBC binding.

### 8.7 ARRAY / collection / các type vendor-specific

Nếu mảng có thứ tự, so sánh theo chỉ số và giữ `null` phần tử. Nếu contract là **set**, có thể chuẩn hóa thứ tự nhưng vẫn phải kiểm tra duplicate policy. SQL `ARRAY`, PostgreSQL `JSONB`, geometry và kiểu tùy biến có cách bind/đọc phụ thuộc driver; một `RowMapper` có thể cần `java.sql.Array`, vendor objects hoặc converter riêng. Test kiểu phần tử, array rỗng, nested data, scale và các giá trị biên.

## 9. Bộ dữ liệu kiểm thử theo biên và thuộc tính

Một bài round-trip đơn lẻ chỉ chứng minh **một trường hợp**. Xây ma trận có chủ đích, rồi bổ sung random/property-based tests:

| Nhóm case | Dữ liệu gợi ý | Lỗi có thể lộ |
| --- | --- | --- |
| Giá trị thường gặp | decimal hai chữ số, timestamp tròn giây, UUID bình thường | Lỗi ánh xạ cột/tên/kiểu |
| Biên precision/scale | `0.001`, `-999999.99`, quá `p`, nhiều trailing zeros | Mất decimal, overflow, sai comparator |
| Biên timestamp | 1 ns, 999.999.999 ms, cuối ngày, DST | Rounding, chuyển ngày, lệch timezone |
| Unicode | `Đặng`, `café`, `e\u0301`, emoji, ký tự điều khiển | Charset, normalization, truncation |
| Null/missing | SQL `NULL`, JSON `null`, JSON key thiếu, chuỗi rỗng | Mất khác biệt null/zero/empty |
| Dữ liệu có cấu trúc | JSON nested, array có null, enum lạ | Sai kiểu/cấu trúc/thứ tự |
| Binary | byte `00`, `80`, `FF`, dài đúng/vượt giới hạn | Truncate, text decoding sai |
| Nâng cấp phiên bản | dữ liệu do phiên bản cũ ghi, schema migration | Converter không tương thích ngược |
| Driver/config khác | H2 test, PostgreSQL/MySQL thật, session timezone khác | Khác biệt vendor và session |

Ví dụ property cần kiểm tra là “với mọi `x` hợp lệ trong miền D, sau khi lưu rồi đọc, `equivalent(x, read(write(x)))` phải đúng”. Nếu D chỉ cho phép tối đa 2 chữ số decimal thì **giới hạn D trước khi test**; không “làm cho test pass” bằng cách xóa ngầm dữ liệu của mọi `x` không phù hợp.

Khi sinh dữ liệu ngẫu nhiên, lưu seed để tái lập ca lỗi. Thử thêm giá trị biên thủ công vì random có thể hiếm khi sinh chính xác giờ DST hoặc số sát giới hạn.

## 10. Kiểm thử với Spring JDBC và DB thực

Để round-trip đúng với luồng sản xuất, integration test nên dùng:
1. **DDL/schema thật** (bao gồm `NOT NULL`, `CHECK`, precision/scale, collation, timezone/encoding).
2. **Cùng JDBC driver và phiên bản DB** quan trọng trong production, có thể dựng bằng Testcontainers.
3. **Cùng code bind + RowMapper + converter** mà ứng dụng sử dụng; đừng viết mapper test giả khác với production.
4. **Commit rồi đọc bằng transaction/connection mới** khi cần kiểm tra trạng thái tồn tại và các phép biến đổi chỉ xuất hiện sau commit.
5. Kiểm tra exception và silent coercion: lỗi được ném là một trạng thái khác với lưu thành công nhưng sai giá trị.
6. Có cả test **đúng**, **thất bại có chủ đích** và **normalization được phép**.

Trong test dùng `JdbcTemplate`, đừng chỉ kiểm tra `jdbc.update(...) == 1`. Count cho biết hàng đã được ảnh hưởng, không xác nhận từng field còn nguyên. Sau khi ghi, hãy query lại **toàn bộ field quan trọng** và assert với comparator đúng.

Ví dụ assertion bổ sung theo mã Java trong phần 5 (đoạn này chỉ dùng trong ngữ cảnh test có biến `before` và `after`):

```java
if (before.amount().compareTo(after.amount()) != 0) {
    throw new AssertionError("Decimal changed during round-trip");
}
if (!before.occurredAt().equals(after.occurredAt())) {
    throw new AssertionError("Timestamp precision lost");
}
if (!java.util.Arrays.equals(before.payload(), after.payload())) {
    throw new AssertionError("Binary payload changed");
}
```

Các assertion **cố ý fail** với schema `DECIMAL(8,2)` và `TIMESTAMP(3)` của demo; đó là tín hiệu test hoạt động đúng. Để đạt yêu cầu exactness, nâng `DECIMAL`/`TIMESTAMP` theo precision cần thiết, hoặc validate đầu vào và chuẩn hóa minh bạch theo hợp đồng rồi test lại.

## 11. Phân biệt lỗi chuyển đổi thật và sai biệt biểu diễn được phép

Ba tình huống dễ nhầm:

**Trường hợp A — mất giá trị số thực sự.** `12.3456` → `12.35` làm thay đổi tiền nếu scale 4 có ý nghĩa. So sánh `BigDecimal.compareTo` phát hiện. Đây là lỗi thiết kế schema/mapping khi contract yêu cầu đủ scale 4.

**Trường hợp B — cùng giá trị số, scale đổi.** `12.3400` → `12.34` có `compareTo == 0`, nhưng `equals == false`. Nếu scale không có ý nghĩa nghiệp vụ, đó có thể là round-trip thành công; nếu cần giữ đúng scale, contract yêu cầu khác.

**Trường hợp C — cùng instant, offset đổi.** `2026-10-30T09:00+07:00` và `2026-10-30T02:00Z` biểu diễn cùng thời điểm. Nếu nghiệp vụ chỉ cần instant, không mất giá trị; nếu cần giữ offset gốc hoặc zone lịch sử, đã mất thông tin biểu diễn và phải lưu thêm metadata.

Tương tự, JSON có thể được chuẩn hóa thứ tự key, UUID có thể đổi chữ hoa/thường trong dạng text, Unicode có thể được normalize, `CHAR` có thể đệm dấu cách. Đừng gộp tất cả thành “mất dữ liệu” nếu contract không đòi giữ biểu diễn; cũng đừng bỏ qua sai biệt mà contract thật sự cần.

Một kiểu kiểm thử tốt sẽ có **hai assertion riêng**:
- `semanticEquivalent(expected, actual)` để kiểm giá trị nghiệp vụ;
- `representationPreserved(expected, actual)` khi cần giữ chính xác dữ liệu gốc.

## 12. Những lỗi phổ biến trong thực tế

- **Chỉ kiểm tra insert/update count:** SQL thành công nhưng `DECIMAL` hoặc `TIMESTAMP` đã làm tròn.
- **Dùng `BigDecimal.equals` vô điều kiện:** tạo false positive cho scale khác nhưng giá trị số bằng nhau; chiều ngược lại dùng tolerance tùy tiện có thể bỏ qua sai số tiền.
- **Đưa số chính xác qua `double` trước khi ghi:** lỗi đã xảy ra trước SQL nên nâng precision cột không sửa được.
- **Dùng `LocalDateTime` như instant:** khi chuyển qua timezone/session, cùng chuỗi giờ địa phương có thể trỏ tới thời điểm khác, đặc biệt ở DST.
- **Đọc SQL `NULL` bằng primitive `getInt` rồi quên `wasNull`:** biến null thành 0, làm sai hợp đồng.
- **So sánh mảng bằng `equals`:** kiểm identity, không kiểm nội dung.
- **So sánh JSON như string khi contract là cấu trúc, hoặc ép số qua `double`:** dễ có cả báo lỗi giả lẫn mất precision.
- **Chỉ kiểm tra converter bằng unit test:** không phát hiện coercion của cột SQL và driver; cần integration test trên DB thật.
- **Chỉ đọc lại từ cache/entity chưa refresh:** có thể đang nhìn object gốc chứ chưa phải dữ liệu persisted; dùng truy vấn DB/transaction khác khi cần.
- **Dùng DB H2 để khẳng định hành vi PostgreSQL/MySQL:** các quy tắc timestamp, decimal, JSON, enum, charset khác nhau.
- **Chỉ kiểm tra dữ liệu ngắn/ASCII:** bỏ sót Unicode, byte nhị phân, giá trị sát giới hạn và dữ liệu lịch sử.
- **Viết test chỉ so giá trị sau cùng của hai converter cùng có lỗi:** nếu cả chiều ghi và đọc áp dụng cùng một biến đổi sai, phép so sánh yếu có thể vẫn pass. Kiểm tra cả hợp đồng định dạng lưu, schema và giá trị DB trung gian.

## 13. Checklist khi code review và sau thay đổi schema

Trước khi đưa một kiểu dữ liệu đặc biệt vào production, xác nhận:

- Tên kiểu Java/domain, SQL type, `precision/scale/length` và chính sách `NULL` được khai báo rõ.
- Đã xác định thế nào là **tương đương**: số, scale, instant, offset, code points, JSON tree, bytes hay thứ tự phần tử.
- Code encode/bind và decode/map đã cùng chia sẻ một hợp đồng, có test hai chiều.
- Có test ghi/đọc với giá trị thật từ SQL, trên đúng DB/driver, không chỉ DTO/unit test.
- Có các ca bình thường, null, biên, invalid, Unicode, giá trị ngẫu nhiên và dữ liệu legacy.
- Có test xác minh **mất dữ liệu được phát hiện** (negative test), không chỉ test happy path.
- Dữ liệu bị chuẩn hóa có quy tắc và kiểm thử riêng; nếu không được mất thì phải reject trước ghi.
- Khi thay cột `DECIMAL`, `TIMESTAMP`, `VARCHAR`, JSON hoặc driver version, bộ round-trip test được chạy lại.
- Nếu phát hiện khác biệt, đã xác định nó đến từ converter Java, JDBC driver, DB coercion hay đọc về.
- Logging lỗi không lộ bí mật hoặc nội dung thô của BLOB/JSON nhạy cảm.

Khi migration từ `DECIMAL(12,4)` về `DECIMAL(12,2)`, test phải báo những bản ghi không thể biểu diễn chính xác ở scale 2 **trước khi migration**, không chỉ chứng minh bản ghi mới ghi được. Với thay đổi timezone/JSON mapping, nên đối soát một mẫu dữ liệu lịch sử bằng reader cũ và reader mới, dưới cùng business invariants.

## 14. Tổng kết và tài liệu chính thức

**Nguyên tắc cốt lõi:** Lưu thành công và đọc không lỗi chưa chứng minh dữ liệu nguyên vẹn. Hãy viết một hợp đồng *`read(write(x)) ≡ x`*, chọn `≡` theo ý nghĩa nghiệp vụ, chạy nó qua đúng schema + driver + converter, rồi kiểm thêm dạng raw khi cần. Nếu mất dữ liệu là không chấp nhận được, sửa schema hoặc từ chối giá trị đầu vào trước khi ghi; nếu chuẩn hóa được phép, công bố và kiểm thử phép chuẩn hóa đó.

Tài liệu tham khảo:
- Spring Framework 6.2 — JDBC data access: https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc.html
- Spring — Providing SQL type information and handling parameter values: https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html
- Spring — Using JdbcTemplate and mapping query results: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- H2 — Data types (DECIMAL, TIMESTAMP precision, VARBINARY): https://h2database.github.io/html/datatypes.html
- Java 17 — `ResultSet`/JDBC typed `getObject`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html
- Java 17 — `BigDecimal`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html
- Java 17 — `OffsetDateTime`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/OffsetDateTime.html
