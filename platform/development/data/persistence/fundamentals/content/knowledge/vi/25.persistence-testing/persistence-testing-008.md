# Kiểm thử ánh xạ kiểu, null, số chính xác và thời gian

Một ứng dụng Java nhận thanh toán `125000.10 VND`, ghi vào PostgreSQL rồi đọc lại để đối soát. Unit test của service dùng một repository giả, khẳng định số tiền đọc lại bằng số tiền đầu vào và đều **PASS**. Nhưng bản triển khai JDBC thật dùng `double` trước khi đưa vào `NUMERIC(18,2)`, ghi phí giao dịch nullable bằng `ResultSet.getInt()` và ánh xạ thời điểm thanh toán qua `LocalDateTime`. Trong production, một số giao dịch bị làm tròn sai, `NULL` bị hiểu thành `0`, và timestamp lệch giờ khi triển khai ở vùng thời gian khác.

Ba lỗi trên không nhất thiết thuộc về logic nghiệp vụ: chúng phát sinh ở **ranh giới ánh xạ dữ liệu** (*data mapping boundary*) giữa domain Java, JDBC/JPA/ORM và kiểu của kho lưu trữ. Kiểm thử persistence phải đi qua **driver và database thực** để quan sát hành vi lưu, ràng buộc schema, chuyển đổi kiểu và round-trip. Mock repository rất hữu ích cho unit test use case, nhưng không thể chứng minh database đã lưu đúng những gì ứng dụng dự định.

Bài học thuộc chương **Kiểm thử lưu trữ** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Người học sẽ xây dựng chiến lược kiểm thử ánh xạ kiểu dữ liệu, xử lý `NULL`, decimal chính xác và ngày giờ/time zone; thiết kế test boundary, migration và regression cho ứng dụng Java; đồng thời giữ nguyên bảo đảm transaction, durability, concurrency và tính đúng đắn của dữ liệu.

**Mục tiêu:** kết quả **ghi → commit → đọc lại qua adapter/driver thật** phải tuân thủ một hợp đồng dữ liệu được định nghĩa rõ: đúng kiểu, đúng giá trị, đúng ý nghĩa `NULL`, đúng độ chính xác và đúng mốc thời gian. Nếu thông tin không thể biểu diễn trung thực trong cột đã chọn, test phải cho thấy sự khác biệt hoặc xác nhận lỗi được xử lý có chủ đích.

## 1. Kiểm thử ánh xạ dữ liệu khác kiểm thử business logic ra sao?

Ví dụ `OrderService` gọi `PaymentRepository.save()`:

~~~mermaid
flowchart LR
    A[Java Domain: Money, Order, Instant] --> B[Repository / Mapper]
    B --> C[JDBC / JPA / ORM]
    C --> D[(Database schema)]
    D --> C
    C --> B
    B --> E[Java Domain đọc lại]
~~~

Có ít nhất bốn lớp hợp đồng:

| Lớp | Ví dụ câu hỏi | Cách kiểm thử thích hợp |
| --- | --- | --- |
| **Domain validation** | Có chấp nhận amount âm hoặc currency sai? | Unit test Java |
| **Mapper/adapter** | Java `null`, `BigDecimal`, `Instant` chuyển thành tham số SQL nào? | Integration test qua JDBC/JPA |
| **Schema/engine** | `NUMERIC(18,2)` làm tròn ra sao, `NOT NULL` có từ chối không? | Test với cùng loại DB production |
| **Round-trip và transaction** | Commit xong, kết nối mới đọc được giá trị và ý nghĩa ban đầu không? | Integration/contract test với DB |

Một unit test dùng fake repository có thể kiểm tra rằng service đã gọi `save(payment)` với `BigDecimal("125000.10")`. Nhưng fake thường giữ nguyên object trong RAM, trong khi database có thể:

- Chuẩn hóa scale của decimal, cắt/round microseconds của timestamp hoặc áp timezone khi cast.
- Từ chối overflow, `NULL`, duplicate key hoặc check constraint.
- Trả một giá trị bằng kiểu khác so với Java domain.
- Tự tạo ID, default value, trigger hoặc generated column.
- Chỉ cho thấy dữ liệu sau commit, tùy transaction isolation.

**Không được dùng mock làm bằng chứng** cho những hành vi do database và driver quyết định.

## 2. Định nghĩa hợp đồng dữ liệu trước khi viết test

Giả sử hệ thống thanh toán có model miền:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.UUID;

public record PaymentEntry(
        UUID externalId,
        long tenantId,
        BigDecimal amount,
        BigDecimal fee,            // Có thể NULL khi chưa tính phí.
        Integer installmentCount,  // Có thể NULL, khác số 0.
        LocalDate settlementDate,  // Ngày nghiệp vụ, chưa phải một instant.
        Instant submittedAt,       // Thời điểm tuyệt đối.
        LocalDateTime localCutoff, // Giờ địa phương, cần quy ước zone.
        String memo                // Có thể NULL hoặc rỗng.
) {}
~~~

Trước khi mapping, xác định một **hợp đồng**:

| Trường | Ý nghĩa | Kiểu Java | Kiểu SQL dự kiến | Bất biến |
| --- | --- | --- | --- | --- |
| `externalId` | ID bất biến của request | `UUID` | `UUID NOT NULL UNIQUE` | Không trùng |
| `tenantId` | Phạm vi sở hữu | `long` | `BIGINT NOT NULL` | Dương, lấy từ principal đáng tin |
| `amount` | Số tiền chính xác | `BigDecimal` | `NUMERIC(18,2) NOT NULL` | Không âm; 2 chữ số thập phân |
| `fee` | Phí có thể chưa tính | `BigDecimal` nullable | `NUMERIC(18,4) NULL` | NULL khác 0 |
| `installmentCount` | Số kỳ, chưa biết được phép | `Integer` nullable | `INTEGER NULL` | NULL khác 0 |
| `settlementDate` | Ngày theo lịch nghiệp vụ | `LocalDate` | `DATE` | Không tự gán múi giờ |
| `submittedAt` | Thời điểm đã gửi | `Instant` | `TIMESTAMPTZ` | Cùng instant sau round-trip |
| `localCutoff` | Giờ dân sự của nghiệp vụ | `LocalDateTime` | `TIMESTAMP WITHOUT TIME ZONE` | Chưa đủ để suy ra UTC |
| `memo` | Ghi chú tùy chọn | `String` nullable | `TEXT` | Phân biệt NULL và chuỗi rỗng khi cần |

Đây là một **phương án thiết kế** để kiểm thử, không phải ánh xạ mặc định bắt buộc của mọi framework. Ví dụ phí có thể là `Money` chứa amount và currency; ngày settlement thực tế cần calendar, ngày nghỉ và timezone được quản lý riêng.

### Một câu hỏi quan trọng: dữ liệu có cần giữ nguyên từng bit không?

Không phải mọi trường đều cần bitwise equality:

- `BigDecimal("1.0")` và `BigDecimal("1.00")` có **giá trị số** bằng nhau nhưng scale khác; schema `NUMERIC(18,2)` thường trả scale 2.
- Timestamp PostgreSQL thường biểu diễn thời gian ở độ phân giải microsecond; `Instant` của Java có độ phân giải nanosecond. Nếu gửi nanosecond không trùng bội số microsecond, phải xác định quy tắc làm tròn/kiểm soát trước khi test.
- `TIMESTAMPTZ` bảo toàn thời điểm tuyệt đối nhưng không lưu nguyên offset/zone ban đầu. Do đó không nên assert “offset không đổi” khi DB không lưu thông tin đó.

Test phải kiểm tra **hợp đồng ngữ nghĩa**, không áp dụng `equals()` mù cho mọi kiểu.

## 3. Schema mẫu để chạy kiểm thử tích hợp

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE payment_entries (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_id        UUID NOT NULL UNIQUE,
    tenant_id          BIGINT NOT NULL CHECK (tenant_id > 0),
    amount             NUMERIC(18, 2) NOT NULL CHECK (amount >= 0),
    fee                NUMERIC(18, 4),
    installment_count  INTEGER,
    settlement_date    DATE,
    submitted_at       TIMESTAMPTZ NOT NULL,
    local_cutoff       TIMESTAMP WITHOUT TIME ZONE,
    memo               TEXT,
    CHECK (
        installment_count IS NULL
        OR installment_count BETWEEN 1 AND 120
    )
);
~~~

Trong PostgreSQL:

- `NUMERIC(18,2)` giới hạn **18 chữ số tổng cộng, gồm 2 chữ số thập phân**, sau khi engine áp dụng scale theo quy tắc của kiểu. Dữ liệu vượt phạm vi có thể gây lỗi.
- `NUMERIC(18,4)` có 4 chữ số sau dấu thập phân, phù hợp một số dạng tỷ lệ/phí nhưng không tự thể hiện currency.
- `NULL` khác `0`. `CHECK` thường không từ chối một biểu thức có kết quả *unknown*, nên quy tắc bắt buộc cần `NOT NULL` riêng khi thực sự cần.
- `DATE` lưu ngày lịch; `TIMESTAMP WITHOUT TIME ZONE` lưu giá trị ngày-giờ không mang zone; `TIMESTAMPTZ` lưu một instant theo semantics của PostgreSQL và chuyển hiển thị theo session time zone.
- Một ràng buộc schema tốt ngăn một số giá trị không hợp lệ, nhưng không biết mọi quy tắc miền, chẳng hạn currency hay quyền tenant.

Trong môi trường thực, schema phải được tạo bằng **migration đã version hóa** như Flyway/Liquibase hoặc pipeline tương đương. Dùng DDL thử nghiệm không được trở thành bản sao khác schema production; contract test phải chạy trên **schema sau migration** mà ứng dụng thực tế sẽ dùng.

## 4. Ma trận test: giá trị bình thường, biên, lỗi và khôi phục

Một bài kiểm thử chỉ dùng một bản ghi “đẹp” thường bỏ qua lỗi mapping:

| Nhóm | Input điển hình | Điều cần xác minh |
| --- | --- | --- |
| Số nguyên | `0`, `1`, `Integer.MAX_VALUE`, NULL | Không overflow âm thầm; NULL không thành 0 |
| Decimal | `0.00`, `1.20`, `-0.01`, max precision | Giá trị, dấu, scale, constraint và rounding |
| Decimal scale vượt schema | `1.234` vào cột scale 2 | Lỗi trước ghi hoặc quy tắc làm tròn có chủ đích |
| Java `null` | Fee, count, note, ngày tùy chọn | `NULL` thật được ghi và đọc về `null` |
| Chuỗi | `""`, khoảng trắng, Unicode, chuỗi dài | Phân biệt empty/NULL; encoding không hỏng |
| Date | Ngày cuối tháng, năm nhuận, `2024-02-29` | Round-trip đúng calendar day |
| Instant | Trước/sau nửa đêm UTC, offset `+07:00` | Bảo toàn instant theo độ chính xác schema |
| Giờ địa phương | DST gap/overlap, zone khác nhau | Không tự suy instant khi zone chưa rõ |
| Database default | Không truyền cột khác với truyền NULL | Hiểu đúng sự khác biệt |
| Transaction | Commit, rollback, lỗi giữa chừng | Trạng thái DB đúng từ kết nối mới |
| Schema constraint | `NOT NULL`, `CHECK`, `UNIQUE` | SQL lỗi đúng loại, không bị mapper nuốt |

Đặt **kết quả mong đợi** ngay trong test fixture, không tính expected bằng cùng helper mapping đang được kiểm thử. Nếu helper `toDatabase()` sai và expected cũng gọi helper đó, cả hai cùng sai nhưng test vẫn xanh.

## 5. SQL NULL không phải số 0, chuỗi rỗng hoặc giá trị mặc định

SQL `NULL` biểu thị giá trị thiếu/chưa biết/không áp dụng, tùy hợp đồng dữ liệu. Nó **không tương đương** với Java primitive default, chuỗi rỗng, `false` hay mốc thời gian epoch.

~~~sql
SELECT
    NULL = NULL    AS equality_result,
    NULL IS NULL   AS is_null_result,
    COALESCE(NULL::INTEGER, 0) AS filled_zero;
~~~

Trong SQL, so sánh `NULL = NULL` có kết quả *unknown*, không phải `TRUE`. Cần dùng `IS NULL` hoặc `IS NOT DISTINCT FROM` khi phép so sánh phải coi hai NULL là tương đương.

### Lỗi kinh điển với `ResultSet.getInt()`

~~~java
int count = rs.getInt("installment_count");
// Nếu SQL NULL, JDBC trả 0 cho getInt; cần kiểm tra rs.wasNull().
Integer nullableCount = rs.wasNull() ? null : count;
~~~

`wasNull()` phải được gọi **ngay sau lệnh getter liên quan**. Nếu gọi `rs.getString("memo")` trước rồi mới `wasNull()`, nó sẽ phản ánh trạng thái NULL của getter sau, không còn chắc là của `installment_count`.

Với JDBC driver hỗ trợ typed retrieval:

~~~java
Integer count = rs.getObject("installment_count", Integer.class);
BigDecimal fee = rs.getBigDecimal("fee");
String memo = rs.getString("memo");
// Các getter kiểu tham chiếu trên trả null cho SQL NULL.
~~~

Tính khả dụng của `getObject(..., Integer.class)` phụ thuộc JDBC driver và phiên bản được hỗ trợ, nên integration test là nơi xác nhận. Tránh dùng `Optional<Integer>` như một field của entity JPA theo giả định mọi provider đều hỗ trợ; có thể dùng `Optional` ở kết quả tìm kiếm của repository.

### Những trạng thái dễ bị gộp nhầm

| Database | Giá trị Java mong đợi | Nghĩa có thể khác |
| --- | --- | --- |
| `fee = NULL` | `fee == null` | Phí chưa tính/không áp dụng |
| `fee = 0.0000` | `BigDecimal.ZERO` với scale theo DB | Đã tính, phí bằng 0 |
| `memo = NULL` | `null` | Không có thông tin |
| `memo = ''` | `""` | Có chuỗi, độ dài 0 |
| `installment_count = NULL` | `null` | Chưa biết |
| `installment_count = 0` | Giá trị 0 — nếu schema cho phép | Có thể là dữ liệu sai nghiệp vụ |

Nếu chuyển `NULL` thành `0` trong mapper, ứng dụng có thể đưa ra quyết định sai, ví dụ coi một phí **chưa xác định** là “miễn phí”. Việc chọn default phải là quyết định nghiệp vụ có kiểm chứng, không phải side effect của JDBC getter.

## 6. Test JDBC: truyền NULL đúng kiểu và đọc lại

Khi bind nullable parameter, dùng `setNull(index, sqlType)` hoặc typed setter phù hợp và xử lý null rõ ràng:

~~~java
import java.math.BigDecimal;
import java.sql.PreparedStatement;
import java.sql.Types;

// ps là PreparedStatement cho INSERT có fee ở vị trí 1.
BigDecimal fee = null;
if (fee == null) {
    ps.setNull(1, Types.NUMERIC);
} else {
    ps.setBigDecimal(1, fee);
}
~~~

Không ghép chuỗi `"NULL"` trực tiếp vào SQL để tạo “giá trị NULL”; đó là một text literal, không phải SQL NULL. Với `PreparedStatement.setObject(index, null)`, một số driver/statement có thể không suy ra được kiểu khi server cần type rõ; `setNull` giúp hợp đồng cụ thể hơn.

Test nên so sánh **hai trạng thái độc lập**:

~~~java
assertNull(readBackFeeFor(externalIdWithNull));
assertEquals(0, readBackFeeFor(externalIdWithZero)
        .compareTo(new BigDecimal("0.0000")));
~~~

Không chỉ kiểm tra `getBigDecimal() == null` mà còn xác nhận database thật có `IS NULL`:

~~~sql
SELECT
    external_id,
    fee IS NULL AS fee_missing
FROM payment_entries
WHERE external_id = :externalId;
~~~

Điều này bắt các mapper tự thay `null` thành `BigDecimal.ZERO` hoặc ngược lại. Nếu legacy database có default cho `fee`, một test cũng cần phân biệt **bỏ cột khi INSERT** (sử dụng default) với **INSERT cột bằng NULL** (thường không áp dụng default theo cách tương tự).

## 7. SQL three-valued logic và `CHECK` cần được kiểm thử

SQL có ba trạng thái cho biểu thức logic: `TRUE`, `FALSE` và `UNKNOWN`. Một ràng buộc:

~~~sql
CHECK (installment_count > 0)
~~~

**không cấm NULL** nếu cột còn nullable, vì biểu thức với NULL là unknown và `CHECK` không xem unknown là vi phạm. Nếu yêu cầu phải có số kỳ:

~~~sql
installment_count INTEGER NOT NULL
    CHECK (installment_count BETWEEN 1 AND 120)
~~~

Nếu yêu cầu cho phép “chưa biết số kỳ”, cột nullable có thể chính xác hơn — nhưng Java phải giữ trạng thái chưa biết.

Test cần xác minh cả ba nhánh:

1. `NULL` được lưu nếu hợp đồng cho phép.
2. `0` bị từ chối bởi `CHECK` nếu không hợp lệ.
3. `12` được chấp nhận và đọc lại chính xác.

Thêm test về query filter:

~~~sql
-- Sai nếu định tìm tất cả giá trị NULL.
SELECT id FROM payment_entries WHERE fee = NULL;

-- Đúng khi cần tìm giá trị NULL.
SELECT id FROM payment_entries WHERE fee IS NULL;
~~~

Một truy vấn repository sử dụng `= NULL` có thể trả rỗng trên môi trường thật trong khi fake repository Java dùng `Objects.equals` lại trả kết quả, tạo ảo giác mọi test đều đúng.

## 8. Tiền và số chính xác: `BigDecimal` thay vì `double`

Giá trị tiền, tỷ lệ thuế và số có yêu cầu chính xác thập phân không nên đi qua `float`/`double` mà không có quyết định rõ ràng về sai số.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal correct = new BigDecimal("0.10")
        .add(new BigDecimal("0.20"));
BigDecimal risky = new BigDecimal(0.1);
BigDecimal fromText = new BigDecimal("0.1");

assertEquals(0, correct.compareTo(new BigDecimal("0.30")));
assertNotEquals(fromText, risky); // 0.1 dạng binary không chính xác.
~~~

`new BigDecimal(0.1)` tạo biểu diễn decimal **chính xác của giá trị binary double 0.1 đã được làm tròn**, không phải decimal 0.1 mong muốn. `BigDecimal.valueOf(double)` có hành vi qua biểu diễn chuỗi chuẩn của double, nhưng nếu đầu vào đã trải qua tính toán binary sai thì không thể tự khôi phục ý nghĩa kế toán ban đầu.

### Chọn quy tắc scale tại ranh giới

Ví dụ amount theo đơn vị tiền có hai chữ số thập phân:

~~~java
static BigDecimal requireExactScale2(BigDecimal amount) {
    if (amount == null || amount.signum() < 0) {
        throw new IllegalArgumentException("Số tiền không hợp lệ");
    }
    try {
        return amount.setScale(2, RoundingMode.UNNECESSARY);
    } catch (ArithmeticException cannotRepresent) {
        throw new IllegalArgumentException(
                "Số tiền không biểu diễn chính xác ở scale 2",
                cannotRepresent);
    }
}
~~~

`RoundingMode.UNNECESSARY` từ chối `1.235` khi cần scale 2, thay vì bí mật làm tròn. Nếu sản phẩm có quy tắc thuế cho phép làm tròn (ví dụ `HALF_EVEN` hoặc `HALF_UP`), áp dụng **ở ranh giới nghiệp vụ được định nghĩa** và kiểm thử những giá trị sát điểm hòa, số âm và dấu. Không để driver/DB quyết định âm thầm khác với Java.

Trong PostgreSQL, khai báo `NUMERIC(p,s)` có thể **làm tròn** đầu vào về scale của cột rồi mới kiểm tra phạm vi; nhiều phép so sánh giá trị không phản ánh điều đó nếu test chỉ dùng số tròn. Không được tự suy mọi DB sẽ từ chối `1.235` ở `NUMERIC(18,2)` — một test tích hợp sẽ cho thấy hành vi engine thật.

## 9. Precision, scale, rounding và overflow

**Precision** là tổng số chữ số có nghĩa; **scale** là số chữ số ở phần thập phân theo khai báo và biểu diễn. Với `NUMERIC(18,2)`, dữ liệu có tối đa 16 chữ số trước dấu thập phân sau khi áp dụng scale phù hợp.

| Input dự kiến | Điều cần test | Kết quả đáng quan sát |
| --- | --- | --- |
| `0.00` | Zero với scale 2 | Không thành NULL |
| `125000.10` | Giá trị bình thường | Đọc lại 125000.10 |
| `1.2` | Scale khác từ client | DB có thể trả scale 2 (`1.20`) |
| `1.234` | Vượt scale 2 | Java có thể từ chối; DB có thể round theo quy tắc |
| `9999999999999999.99` | Biên tối đa với 16 chữ số nguyên | Cần xác minh không overflow |
| `10000000000000000.00` | Vượt precision của cột | Database thường từ chối overflow |
| `-0.01` | Dấu âm | `CHECK (amount >= 0)` từ chối |
| `9999999999999999.999` | Làm tròn vượt phạm vi | Có thể phát sinh overflow sau rounding |

### Dùng `compareTo` hay `equals`?

~~~java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

assertEquals(0, a.compareTo(b));  // Cùng giá trị số.
assertNotEquals(a, b);            // Scale khác.
assertEquals(1, a.scale());
assertEquals(2, b.scale());
~~~

Nếu hợp đồng chỉ yêu cầu **giá trị tiền**, `compareTo() == 0` thường phù hợp. Nếu DTO/serialization hoặc business rule yêu cầu scale chuẩn, assert **cả scale** sau khi chuẩn hóa. Một test dùng `stripTrailingZeros()` trước mọi so sánh có thể che mất lỗi scale mà ứng dụng cần phát hiện.

### Nhớ tính độ lớn trung gian

`amount × exchangeRate` hoặc `unitPrice × quantity` có thể tạo nhiều chữ số hơn độ rộng cột. Hãy kiểm thử phép nhân với giá trị biên, quy tắc rounding và cách giới hạn trước khi ghi. `BigDecimal` không tự ngăn giá trị quá lớn so với schema.

## 10. Mapping số nguyên, boolean, enum và UUID

Không phải mọi sai lệch kiểu đều thuộc decimal. Một repository cũng cần kiểm thử:

| Cặp kiểu | Rủi ro | Test cần có |
| --- | --- | --- |
| Java `long` ↔ SQL `BIGINT` | Overflow khi ép sang `int` hoặc khi API JSON dùng số quá lớn | Min/max hợp lệ, giá trị ngoài range |
| Java `Integer` nullable ↔ SQL `INTEGER` | `getInt()` biến NULL thành 0 | NULL và 0 độc lập |
| Java `boolean`/`Boolean` ↔ SQL `BOOLEAN` | NULL bị biến thành false | true, false, null |
| Java `UUID` ↔ PostgreSQL `UUID` | Chuyển chuỗi không hợp lệ hoặc dùng `CHAR` mất chuẩn | UUID round-trip, input lỗi |
| Java enum ↔ SQL `VARCHAR`/custom enum | Rename enum làm dữ liệu cũ không đọc được | Giá trị cũ/mới/unknown |
| Java `String` ↔ SQL `VARCHAR(n)` | Quá chiều dài, Unicode/truncation | Độ dài biên, tiếng Việt, ký tự bổ sung |

Ví dụ không nên persist enum theo `ordinal()` nếu không có hợp đồng version hóa rõ: thêm một enum constant ở giữa danh sách có thể làm những số ordinal cũ biểu thị ý nghĩa khác.

~~~java
public enum PaymentStatus {
    PENDING, SETTLED, FAILED
}

// Minh họa mapping ổn định theo tên:
String dbValue = PaymentStatus.SETTLED.name();
PaymentStatus parsed = PaymentStatus.valueOf(dbValue);
~~~

Ngay cả khi lưu tên, việc đổi tên enum cần migration hoặc một mã ổn định riêng; test phải bao phủ dữ liệu lịch sử chưa được migrate. Các kiểu JSON/BSON, array, UUID và enum của từng database có driver-specific behavior; không suy từ một implementation JDBC rằng tất cả đều giống nhau.

## 11. Ngày lịch và thời điểm tuyệt đối là hai khái niệm riêng

Java `java.time` cung cấp những kiểu có ý nghĩa khác nhau:

| Kiểu Java | Ý nghĩa | Mapping thường xem xét |
| --- | --- | --- |
| `LocalDate` | Một ngày theo lịch, không mang giờ/zone | SQL `DATE` |
| `LocalTime` | Một giờ trong ngày, không mang ngày/zone | SQL `TIME WITHOUT TIME ZONE` |
| `LocalDateTime` | Ngày-giờ địa phương, chưa chỉ ra instant | SQL `TIMESTAMP WITHOUT TIME ZONE` |
| `Instant` | Một thời điểm trên dòng thời gian UTC | Thường ánh xạ qua `TIMESTAMPTZ`/`OffsetDateTime` |
| `OffsetDateTime` | Ngày-giờ với offset cố định | JDBC 4.2; thường dùng cho `TIMESTAMP WITH TIME ZONE` |
| `ZonedDateTime` | Ngày-giờ với ZoneId và quy tắc lịch sử/DST | Thường cần lưu zone ID riêng nếu phải khôi phục |
| `Duration` | Khoảng thời gian đo theo giây/nano | Không tương đương trực tiếp ngày lịch hoặc giờ dân sự |

Ví dụ ngày thanh toán theo lịch `2026-11-22` không đồng nghĩa `2026-11-22T00:00:00Z`. Nếu hệ thống định nghĩa ngày nghiệp vụ theo `Asia/Ho_Chi_Minh`, mốc đầu ngày ở local có thể là một instant UTC của **ngày hôm trước**; chuyển một `LocalDate` sang UTC một cách tự động có thể làm ngày bị lệch khi xuất báo cáo.

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;

LocalDate settlementDate = LocalDate.of(2026, 11, 22);
LocalDateTime localCutoff =
        LocalDateTime.of(2026, 11, 22, 17, 30);
Instant submittedAt = Instant.parse("2026-11-22T08:15:00Z");
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant startOfBusinessDay =
        settlementDate.atStartOfDay(businessZone).toInstant();
~~~

Trong mapping, mỗi phép chuyển cần có **chính sách zone và business calendar** rõ. Không dùng máy chủ mặc định `ZoneId.systemDefault()` như một nguồn nghiệp vụ bất biến, vì timezone trên laptop, CI container và production có thể khác nhau.

## 12. `TIMESTAMPTZ` khác `TIMESTAMP WITHOUT TIME ZONE` như thế nào?

Trong PostgreSQL, tên `TIMESTAMP WITH TIME ZONE` hay `TIMESTAMPTZ` dễ làm người mới hiểu nhầm rằng cột giữ nguyên **tên múi giờ của người gửi**. Thực chất, loại cột này biểu diễn một **thời điểm tuyệt đối**; engine chuẩn hóa thời gian và có thể hiển thị theo timezone của session khi truy vấn. Offset gốc `+07:00` hoặc zone ID `Asia/Ho_Chi_Minh` không mặc nhiên được lưu như một phần riêng của giá trị.

~~~sql
-- Hai biểu diễn sau cùng chỉ đến một instant:
SELECT
    TIMESTAMPTZ '2026-11-22 15:15:00+07' =
    TIMESTAMPTZ '2026-11-22 08:15:00+00'
        AS same_instant;

-- Không dùng chuỗi không kèm zone rồi giả định đó là UTC.
~~~

`TIMESTAMP WITHOUT TIME ZONE` chỉ giữ các trường ngày-giờ như `2026-11-22 15:15:00`. Nếu bạn lưu một giá trị thuộc timezone khác, database **không tự biết** nó thuộc zone nào và không thể suy ra một instant duy nhất.

| Yêu cầu | Kiểu SQL gợi ý | Kiểu Java gợi ý | Test quan trọng |
| --- | --- | --- | --- |
| Log lúc request vào hệ thống | `TIMESTAMPTZ` | `Instant`/`OffsetDateTime` | Hai offset khác nhau cùng instant |
| Giờ mở cửa theo địa phương | `TIME` hoặc `TIMESTAMP` cùng zone ID riêng | `LocalTime`/`LocalDateTime` + `ZoneId` | DST và rule zone |
| Ngày sinh/ngày kế toán | `DATE` | `LocalDate` | Không lệch ngày khi đổi timezone |
| Lịch hẹn ở một khu vực | Local date-time + zone ID, có thể thêm instant đã giải quyết | `ZonedDateTime` hoặc cấu trúc domain riêng | Gap/overlap và thay đổi quy tắc zone |
| Thời gian xử lý/TTL | Duration/deadline theo instant/clock monotonic cho đo lường | `Duration`, `Instant` | Không trộn wall clock với elapsed time |

Ví dụ input hai offset:

~~~java
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

OffsetDateTime vietnam =
        OffsetDateTime.parse("2026-11-22T15:15:00+07:00");
OffsetDateTime utc =
        OffsetDateTime.parse("2026-11-22T08:15:00Z");

assertEquals(vietnam.toInstant(), utc.toInstant());
assertNotEquals(vietnam.getOffset(), utc.getOffset());
~~~

Khi test `TIMESTAMPTZ`, so sánh `toInstant()` thay vì khẳng định offset object đọc từ driver **phải bằng** offset ban đầu. Với PostgreSQL JDBC, có thể đọc bằng `getObject(column, OffsetDateTime.class)` khi driver hỗ trợ đúng phiên bản; nhiều trường hợp object trả về có offset UTC. Không lấy offset này làm bằng chứng zone mà người dùng từng chọn.

## 13. Độ chính xác thời gian: nanosecond của Java và microsecond của DB

`Instant` và `LocalDateTime` trong Java có trường nanosecond, nhưng PostgreSQL timestamp thường lưu với độ phân giải **microsecond**. Ví dụ:

~~~text
Java Instant:    2026-11-22T08:15:00.123456789Z
PostgreSQL:      độ chính xác tương ứng microsecond
Kết quả đọc:     có thể 2026-11-22T08:15:00.123457Z
                 theo cách làm tròn của engine/driver.
~~~

Do đó, test `assertEquals(inputInstant, readBackInstant)` có thể thất bại một cách chính đáng khi đầu vào có phần nanosecond không biểu diễn được trong cột. Hãy chọn một trong hai hợp đồng:

1. **Chuẩn hóa trước khi lưu** về microsecond theo chính sách rõ, rồi kiểm tra round-trip **chính xác** của giá trị đã chuẩn hóa.
2. **Chấp nhận sai số độ phân giải** được mô tả và kiểm thử theo khoảng, nhưng không che lỗi lệch nhiều giờ bằng một tolerance quá rộng.

Ví dụ đầu vào đã căn đúng microsecond:

~~~java
import java.time.Instant;
import java.time.temporal.ChronoUnit;

Instant input =
        Instant.parse("2026-11-22T08:15:00.123456Z");
assertEquals(input, input.truncatedTo(ChronoUnit.MICROS));
~~~

Nếu dùng cách 1, phải thống nhất **truncate hay round**, và thời điểm thực hiện trước khi hash payload/idempotency hoặc lưu lịch sử. Không chuyển timestamp về giây chỉ để test PASS nếu nghiệp vụ cần độ phân giải cao hơn.

### Cảnh báo về timezone mặc định

Với `java.sql.Timestamp`, `Calendar`, `java.util.Date` hoặc kiểu legacy, các overload JDBC/ORM có thể áp dụng timezone của JVM/session theo quy tắc riêng. Các API `java.time` qua JDBC 4.2 thường thể hiện ý nghĩa rõ hơn, nhưng vẫn phải test với **driver cụ thể**, cấu hình `hibernate.jdbc.time_zone` nếu dùng Hibernate, timezone của DB session và loại cột thực tế. Đừng đặt một config UTC rồi kết luận mọi field ngày giờ đều trở thành instant; `LocalDate` và `LocalDateTime` vẫn có ngữ nghĩa riêng.

## 14. Kiểm thử Daylight Saving Time, lịch và giờ không tồn tại

Ở một số timezone, đồng hồ địa phương có thể **nhảy qua một giờ** vào mùa xuân (*DST gap*) và **lặp lại một giờ** vào mùa thu (*DST overlap*). Một `LocalDateTime` có thể không tồn tại hoặc chỉ đến hai instant khác nhau.

Ví dụ năm 2026 với vùng `America/New_York`:

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;

ZoneId zone = ZoneId.of("America/New_York");

LocalDateTime missing =
        LocalDateTime.of(2026, 3, 8, 2, 30);
LocalDateTime repeated =
        LocalDateTime.of(2026, 11, 1, 1, 30);

assertTrue(zone.getRules()
        .getValidOffsets(missing).isEmpty());
assertEquals(2, zone.getRules()
        .getValidOffsets(repeated).size());
~~~

Một cột `TIMESTAMP WITHOUT TIME ZONE` có thể lưu cả hai giá trị như text ngày-giờ hợp lệ về mặt SQL, nhưng **không đủ thông tin** để xác định instant cho một lịch hẹn tại New York. Nếu ứng dụng dùng `atZone(zone)` để giải quyết gap/overlap, Java có hành vi lựa chọn điều chỉnh/offset mà bạn phải hiểu và kiểm thử; đừng mặc định nó sẽ tự báo lỗi khi thời gian không tồn tại.

Nếu nghiệp vụ yêu cầu một thời điểm cụ thể, có thể lưu:

- Local date-time đã được người dùng nhập.
- Zone ID IANA như `America/New_York`.
- Chính sách chọn offset khi overlap và xử lý khi gap.
- Instant đã được xác nhận, nếu cần thực thi chính xác.

Thử thêm: ngày nhuận `2024-02-29`, ngày cuối tháng, năm mới theo UTC/local, tính ngày kỳ hạn, thời gian lịch dài, lịch ngân hàng và trường hợp múi giờ không áp dụng DST. **Không giả định một ngày luôn có đúng 24 giờ** ở mọi timezone.

## 15. Một integration test JUnit 5 + Testcontainers + PostgreSQL

Một bài kiểm thử thật cần khởi động PostgreSQL bằng môi trường test, áp dụng schema được kiểm soát, ghi dữ liệu qua JDBC và đọc lại bằng connection riêng. Ví dụ sử dụng **JUnit Jupiter**, **Testcontainers** và **PostgreSQL JDBC Driver**.

Các thư viện phải có trong test runtime (ví dụ nhóm `org.junit.jupiter`, `org.testcontainers:junit-jupiter`, `org.testcontainers:postgresql`, `org.postgresql:postgresql` với phiên bản do project quản lý). Các dòng dependency cụ thể thay đổi theo bản Testcontainers, vì vậy hãy dùng BOM/version catalog và tài liệu tương thích của dự án. Testcontainers cần môi trường container hợp lệ trên máy/CI.

**Ví dụ minh họa tự chứa, không tạo dữ liệu sản xuất:**

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.sql.Types;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.UUID;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
class PaymentMappingIT {
    @Container
    static final PostgreSQLContainer<?> db =
            new PostgreSQLContainer<>("postgres:16-alpine");

    private static Connection connect() throws SQLException {
        return DriverManager.getConnection(
                db.getJdbcUrl(), db.getUsername(), db.getPassword());
    }

    @BeforeAll
    static void createSchema() throws SQLException {
        try (Connection c = connect();
             Statement s = c.createStatement()) {
            s.execute("""
                CREATE TABLE payment_entries (
                    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    external_id UUID NOT NULL UNIQUE,
                    tenant_id BIGINT NOT NULL CHECK (tenant_id > 0),
                    amount NUMERIC(18,2) NOT NULL CHECK (amount >= 0),
                    fee NUMERIC(18,4),
                    installment_count INTEGER,
                    settlement_date DATE,
                    submitted_at TIMESTAMPTZ NOT NULL,
                    local_cutoff TIMESTAMP WITHOUT TIME ZONE,
                    memo TEXT,
                    CHECK (installment_count IS NULL OR
                           installment_count BETWEEN 1 AND 120)
                )
                """);
        }
    }

    @Test
    void roundTripPreservesNullDecimalAndInstant() throws SQLException {
        UUID id = UUID.randomUUID();
        BigDecimal amount = new BigDecimal("125000.10");
        LocalDate day = LocalDate.of(2026, 11, 22);
        LocalDateTime cutoff =
                LocalDateTime.of(2026, 11, 22, 17, 30);
        OffsetDateTime submitted = OffsetDateTime.parse(
                "2026-11-22T15:15:00.123456+07:00");

        // INSERT được autocommit, kết nối mới kiểm tra dữ liệu đã commit.
        try (Connection c = connect();
             PreparedStatement ps = c.prepareStatement("""
                INSERT INTO payment_entries (
                    external_id, tenant_id, amount, fee,
                    installment_count, settlement_date,
                    submitted_at, local_cutoff, memo
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """)) {
            ps.setObject(1, id);
            ps.setLong(2, 501L);
            ps.setBigDecimal(3, amount);
            ps.setNull(4, Types.NUMERIC);
            ps.setNull(5, Types.INTEGER);
            ps.setObject(6, day);
            ps.setObject(7, submitted);
            ps.setObject(8, cutoff);
            ps.setString(9, ""); // Chuỗi rỗng khác NULL.
            assertEquals(1, ps.executeUpdate());
        }

        try (Connection c = connect();
             PreparedStatement ps = c.prepareStatement("""
                SELECT amount, fee, installment_count,
                       settlement_date, submitted_at,
                       local_cutoff, memo
                FROM payment_entries
                WHERE external_id = ? AND tenant_id = ?
                """)) {
            ps.setObject(1, id);
            ps.setLong(2, 501L);
            try (ResultSet rs = ps.executeQuery()) {
                assertTrue(rs.next());
                assertEquals(0,
                        rs.getBigDecimal("amount").compareTo(amount));
                assertEquals(2, rs.getBigDecimal("amount").scale());
                assertNull(rs.getBigDecimal("fee"));

                // getInt trả 0 cho SQL NULL; phải xét wasNull ngay.
                assertEquals(0, rs.getInt("installment_count"));
                assertTrue(rs.wasNull());

                assertEquals(day,
                        rs.getObject("settlement_date", LocalDate.class));
                assertEquals(submitted.toInstant(),
                        rs.getObject("submitted_at",
                                OffsetDateTime.class).toInstant());
                assertEquals(cutoff,
                        rs.getObject("local_cutoff",
                                LocalDateTime.class));
                assertEquals("", rs.getString("memo"));
                assertFalse(rs.next());
            }
        }
    }
}
~~~

**Vì sao test này bắt được lỗi mà mock bỏ sót?**

- Ghi qua PostgreSQL JDBC, cột thật `NUMERIC`/`TIMESTAMPTZ`, không chỉ giữ object Java trong RAM.
- Kiểm tra `NULL` độc lập với số 0.
- Kiểm tra scale và giá trị `BigDecimal`.
- Input timestamp có offset `+07:00`, kết quả đối chiếu bằng **Instant** chứ không bằng offset.
- `LocalDate` và `LocalDateTime` được so theo đúng ý nghĩa kiểu.
- Chuỗi rỗng phải quay về `""`, không biến thành `NULL`.
- Dùng hai connection: dữ liệu được đọc qua một kết nối mới sau khi INSERT autocommit.

**Giới hạn:** Đây là test minh họa, không phải full test suite cho ứng dụng. Để kiểm thử adapter production, thay đoạn INSERT/SELECT trực tiếp bằng lời gọi thật tới Repository rồi kiểm tra dữ liệu trên DB. Schema trong `@BeforeAll` nên được thay bằng migration thực tế. Chọn image PostgreSQL phù hợp với phiên bản sản xuất; test container không tự đại diện cho cấu hình cluster, replication, RLS hay extension production.

## 16. Test ràng buộc, overflow và khác biệt rounding giữa Java/DB

Một suite đầy đủ phải kiểm tra rằng **dữ liệu không hợp lệ bị từ chối** chứ không bị mất/biến dạng âm thầm:

~~~sql
-- PostgreSQL probe trên môi trường TEST:
CREATE TEMP TABLE decimal_probe (
    amount NUMERIC(5,2) NOT NULL
);

-- Kiểm tra engine thực sự làm tròn ở boundary:
INSERT INTO decimal_probe(amount) VALUES (1.235), (-1.235);
SELECT amount FROM decimal_probe ORDER BY amount;

-- NUMERIC(5,2) chỉ có tối đa 3 chữ số phần nguyên:
-- Lệnh sau phải lỗi vì vượt phạm vi.
INSERT INTO decimal_probe(amount) VALUES (1000.00);
~~~

Ở PostgreSQL, kiểu `NUMERIC` với scale dương thường làm tròn các giá trị hòa theo hướng **ra xa số 0**, khác với `HALF_EVEN` thường được dùng trong một số tính toán kế toán. Vì vậy, nếu một business rule yêu cầu `HALF_EVEN`, việc để engine tự làm tròn có thể tạo kết quả khác. **Chuẩn hóa/validate bằng Java trước khi ghi**, rồi kiểm tra DB không thay nghĩa dữ liệu.

Một test Java có thể chủ động từ chối input không phù hợp:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

assertThrows(ArithmeticException.class, () ->
        new BigDecimal("1.235")
                .setScale(2, RoundingMode.UNNECESSARY));

assertEquals(new BigDecimal("1.24"),
        new BigDecimal("1.235")
                .setScale(2, RoundingMode.HALF_UP));

assertEquals(new BigDecimal("1.24"),
        new BigDecimal("1.245")
                .setScale(2, RoundingMode.HALF_EVEN));
~~~

Test ràng buộc còn cần SQLSTATE/exception:

- `23502`: `NOT NULL` violation ở PostgreSQL.
- `23505`: unique constraint violation.
- `23514`: check constraint violation.
- `22003`: numeric value out of range trong những trường hợp vượt precision.

**Đừng chỉ assert có một exception bất kỳ.** Kiểm tra SQLSTATE hoặc loại lỗi theo driver (và giữ cause) giúp phân biệt dữ liệu không hợp lệ với mất kết nối. Sau một lỗi SQL trong transaction PostgreSQL, transaction có thể ở trạng thái aborted và phải **ROLLBACK** trước khi chạy query khác; một test không được tiếp tục dùng transaction bị lỗi rồi hiểu lỗi sau là lỗi mapping.

### Không đoán hành vi DB khác

MySQL, Oracle, SQL Server và SQLite có thể khác PostgreSQL về kiểu decimal, strict mode, implicit cast, enum, timezone và lỗi ràng buộc. Test backend thật là bắt buộc khi đặc tính đó có thể làm thay đổi tính đúng đắn.

## 17. Test với timezone khác nhau và tránh phụ thuộc máy CI

Để phát hiện code vô tình dùng timezone mặc định, không chỉ chạy test trên một laptop. Với PostgreSQL, có thể dùng **hai connection có session timezone khác nhau**:

~~~sql
-- Connection A:
SET TIME ZONE 'UTC';
SELECT submitted_at FROM payment_entries
WHERE external_id = :id;

-- Connection B:
SET TIME ZONE 'Asia/Ho_Chi_Minh';
SELECT submitted_at FROM payment_entries
WHERE external_id = :id;
~~~

Giá trị hiển thị của `TIMESTAMPTZ` có thể khác, nhưng **cùng một instant** nếu đọc qua kiểu đủ semantics. Hãy khẳng định:

- `OffsetDateTime.toInstant()` của hai kết nối bằng nhau.
- `LocalDate` dùng cho `DATE` vẫn là đúng ngày lịch.
- `LocalDateTime` dùng cho `TIMESTAMP WITHOUT TIME ZONE` vẫn là đúng các trường ngày/giờ, không tự biến sang UTC.
- Không có code sử dụng `ZoneId.systemDefault()` mà thiếu policy nếu domain yêu cầu một zone ổn định.

Trong test suite Java có thể đổi timezone JVM ở mức cấu hình của **process chạy test riêng**, thay vì gọi `TimeZone.setDefault(...)` đồng thời trong nhiều test chạy song song. Default timezone là trạng thái toàn cục của process; thay đổi giữa các test concurrent dễ gây flakiness và làm sai kết quả không liên quan.

Một test timezone nên được thiết kế **độc lập với múi giờ host**, sử dụng `ZoneId` và `OffsetDateTime` tường minh ở input/expected; chỉ các test chủ đích về default timezone mới thay môi trường.

## 18. ORM/JPA: `flush` không phải `commit` và entity cache có thể che lỗi

Khi dùng JPA/Hibernate, có thêm lớp persistence context. Nếu test làm:

~~~java
entityManager.persist(payment);
PaymentEntity again = entityManager.find(
        PaymentEntity.class, payment.getId());
assertEquals(payment.getAmount(), again.getAmount());
~~~

thì có thể đọc lại **cùng instance managed entity trong first-level cache**, không đi qua database như kỳ vọng. Test xanh **không chứng minh** mapping round-trip.

Một test tốt hơn theo mục đích:

~~~java
entityManager.persist(payment);
entityManager.flush();  // Gửi SQL cần thiết tới DB.
entityManager.clear();  // Không còn managed entity cũ.

PaymentEntity reloaded = entityManager.find(
        PaymentEntity.class, payment.getId());
assertEquals(0, reloaded.getAmount()
        .compareTo(new BigDecimal("125000.10")));
~~~

Nhưng `flush()` **chưa phải commit**. Code trên vẫn chạy trong một transaction, nên nó chưa chứng minh một connection khác nhìn thấy giá trị đã commit. Nếu yêu cầu là “đã ghi bền vững và request sau đọc được”, cần **commit thực**, mở transaction/persistence context mới và xác minh theo isolation của database.

### Metadata mapping không tự thay schema

Ví dụ:

~~~java
@Column(name = "amount", nullable = false,
        precision = 18, scale = 2)
private BigDecimal amount;

@Column(name = "submitted_at", nullable = false)
private Instant submittedAt;
~~~

`@Column(precision=18, scale=2)` mô tả mapping/DDL metadata, **không đảm bảo** schema production đã được migrate. Nếu database thực vẫn dùng `DOUBLE PRECISION` hoặc `NUMERIC(10,0)`, test với schema tạo tự động bằng ORM có thể xanh trong khi production hỏng.

Test JPA cần kiểm tra:

- Schema thật và migration tương thích annotation/converter.
- `AttributeConverter`, enum, JSON mapping, kiểu boolean/UUID, null handling.
- Flush/clear/reload và sau commit đọc bằng transaction mới.
- Default/trigger/generated column có thay giá trị mà persistence context chưa refresh không.
- Đường read-only và write, transaction rollback, optimistic locking nếu có.

Một cách kiểm thử migration là cấu hình test **không auto-create schema từ entity**, áp dụng các migration production lên DB container rồi chạy repository/ORM suite với schema đã migrate.

## 19. Một số lỗi mapping ẩn dưới serialization và API boundary

Không phải mọi lỗi hiển thị ở SQL. Đôi khi database lưu đúng nhưng dữ liệu biến dạng khi đi qua HTTP/JSON:

~~~text
JSON request -> Java DTO -> Domain -> JDBC -> Database
    Database -> JDBC -> Domain -> JSON response
~~~

Ví dụ:

- JSON number lớn có thể bị mất độ chính xác khi đi qua client JavaScript dùng `Number` vượt phạm vi số nguyên an toàn; API có thể cần biểu diễn ID/decimal thành **string** theo hợp đồng.
- Jackson hoặc converter có thể deserialize số tiền qua `double` trước khi tạo `BigDecimal`, làm mất thông tin.
- JSON không có field, JSON `null` và field có giá trị `0` là ba input có thể cần ý nghĩa khác nhau trong PATCH.
- Timestamp API có thể bị parse từ chuỗi **không có offset**, rồi gán zone mặc định khác nhau theo môi trường.
- Serialization có thể thay scale từ `1.20` thành `1.2`, dù giá trị số bằng nhau, ảnh hưởng contract phía client.
- Unicode normalization/collation khác nhau có thể ảnh hưởng so sánh chuỗi, unique key hoặc sorting.

Vì vậy cần thêm **API contract test** bên ngoài integration test persistence:

~~~json
{
  "amount": "125000.10",
  "settlementDate": "2026-11-22",
  "submittedAt": "2026-11-22T08:15:00.123456Z",
  "fee": null
}
~~~

JSON trên chỉ là **một lựa chọn contract**. Nếu API chọn `amount` là JSON number, phải nêu rõ giới hạn tương thích với các client và kiểm thử độ chính xác xuyên suốt. Không tự cho rằng JSON text decimal, Java `BigDecimal` và kiểu money trong database đều tương đương khi thiếu quy định scale và currency.

## 20. Migration dữ liệu cũ: kiểm thử trước và sau thay đổi kiểu

Khi schema tiến hóa, dữ liệu đã lưu có thể mang kiểu hoặc ngữ nghĩa cũ:

~~~text
legacy.amount_string = "1,250.50"    (format nguồn nhập)
new.amount            = NUMERIC(18,2)

legacy.created_at     = TIMESTAMP không có zone
new.created_at        = TIMESTAMPTZ
~~~

Không thể chuyển `TIMESTAMP` sang `TIMESTAMPTZ` mà không biết timezone theo ý nghĩa dữ liệu lịch sử. PostgreSQL có thể diễn giải giá trị timestamp không zone theo session timezone khi cast, dẫn đến shift nếu session không phù hợp.

Một migration cần:

1. **Phân tích dữ liệu cũ:** có NULL, chuỗi sai format, số vượt precision, ngày giờ mơ hồ không?
2. **Xác định quy tắc chuyển đổi:** phân cách decimal, rounding mode, timezone lịch sử, xử lý invalid input.
3. **Tạo cột mới tương thích:** cho phép writer mới ghi đúng nhưng reader cũ chưa phải lập tức đổi.
4. **Backfill có kiểm soát:** batch, idempotent, CAS/phiên bản để tránh ghi đè concurrent writer.
5. **Test cả hai trạng thái:** dữ liệu trước migration và sau migration, kể cả giá trị xấu có chủ đích.
6. **Đối soát:** tổng tiền, số bản ghi, tỷ lệ NULL, distribution theo ngày/tenant và những mismatch.
7. **Siết constraint sau validation:** chỉ thêm `NOT NULL`/`CHECK` mạnh hơn khi các writer và dữ liệu cũ đáp ứng.

### Test migration phải có fixture dữ liệu lịch sử

Nếu test chỉ tạo record mới bằng Java sau migration thì không phát hiện các record cũ như `" 1250,5 "`, `"NaN"`, timestamp mất offset hoặc ngày sinh bị lưu theo epoch. Tạo một fixture **trước migration**, áp dụng migration, rồi xác minh record được chuyển đúng hoặc được đưa vào diện cần sửa — không được tự đặt số mặc định để làm cho mọi dòng pass.

Chú ý: đồng nhất cấu trúc cột không đủ nếu **nghĩa dữ liệu** đã thay đổi. `NULL` từng nghĩa “chưa tính phí” không được tự biến thành “0 đồng” chỉ để đáp ứng `NOT NULL` mới.

## 21. Kiểm thử transaction, concurrency và khả năng đọc sau commit

Một test ánh xạ có thể vô tình chỉ xác minh dữ liệu bên trong transaction chưa commit. Để chứng minh đường persistence thật:

~~~mermaid
sequenceDiagram
    participant W as Writer connection
    participant DB as Database
    participant R as Reader connection
    W->>DB: BEGIN; INSERT payment
    W->>DB: COMMIT
    DB-->>W: Commit acknowledged
    R->>DB: SELECT payment
    DB-->>R: Dữ liệu đã commit theo isolation
~~~

Với PostgreSQL, một test có thể:

- Mở transaction A, ghi số tiền và trường nullable.
- Trước commit, kiểm tra query ở connection B theo isolation thích hợp **không đọc dirty write**.
- Commit A và xác minh B trong **transaction đọc mới** thấy dữ liệu.
- Thử rollback A và xác minh không có record đã commit.
- Thử hai writer đồng thời cập nhật trường cần CAS/version để tránh lost update.
- Thử một writer ghi `NULL` hoặc giá trị invalid trong lúc transaction khác đang đọc, đảm bảo mapping và constraint vẫn đúng.

Không nên dùng các lời gọi `sleep` ngẫu nhiên để tạo race. Với concurrency test, dùng hai connection/transaction độc lập, `CountDownLatch` hoặc barrier để điều khiển thứ tự, timeout để tránh treo và cleanup an toàn.

**Một giới hạn cần nhớ:** test “read-after-commit” trên primary không chứng minh một read replica luôn mới. Nếu ứng dụng có replica, cache, CDC hoặc search index, phải có test riêng cho consistency/replication lag và ghi rõ đường đọc nào dùng được ở điểm quyết định nghiệp vụ.

## 22. Tổ chức bộ kiểm thử trong CI và tránh flaky test

Một pipeline kiểm thử persistence có thể phân tầng:

| Tầng | Mục tiêu | Chạy khi nào |
| --- | --- | --- |
| Unit test domain/converter thuần | Validation, decimal rounding, rule timezone | Mỗi commit |
| JDBC/JPA integration test trên DB thật | Kiểu SQL, NULL, constraint, driver, ORM mapping | Mỗi PR hoặc nightly theo chi phí |
| Migration compatibility test | Schema và dữ liệu lịch sử sau migration | Khi thay migration/schema |
| Repository contract test | Cùng semantics read/write giữa adapter và backend hỗ trợ | Khi đổi adapter/driver |
| Concurrency/fault-injection test | Commit/rollback, CAS, duplicate, timeout | PR quan trọng và lịch định kỳ |
| API end-to-end test | JSON request/response, auth, tenant scope, timezone | Mốc release và các luồng chính |

Những nguyên tắc giúp test đáng tin:

1. **Database đúng loại và phiên bản:** không dùng H2/SQLite thay PostgreSQL cho các hành vi `NUMERIC`, `TIMESTAMPTZ`, JSONB, RLS hay SQLSTATE mang tính PostgreSQL.
2. **Schema thật:** chạy migration thay vì auto-create schema khác production.
3. **Dữ liệu test cô lập:** tạo ID duy nhất, schema/database riêng hoặc cleanup; không phụ thuộc thứ tự các test.
4. **Clock/timezone xác định:** tiêm clock ở domain, dùng mốc/offset tường minh; test cần đổi timezone JVM thì chạy process cô lập.
5. **Transaction rõ:** test nào cần commit thì commit thật; test rollback phải kiểm tra kết quả sau rollback trên connection khác.
6. **Không nuốt lỗi:** không map SQL exception thành `Optional.empty()` rồi làm test tưởng “không có dữ liệu”.
7. **Không phụ thuộc môi trường production:** test container và secret dành riêng, không trỏ nhầm JDBC URL production.
8. **Thu thập bằng chứng lỗi:** SQLSTATE, loại cột, version driver/DB, expected/actual (ẩn dữ liệu nhạy cảm), không log mật khẩu hoặc thông tin cá nhân.

Đối với Postgres Testcontainers, có thể dùng phiên bản PostgreSQL đúng major version production trong CI, chạy migration và dữ liệu fixture; sau đó dùng **cùng DataSource/Repository code** của ứng dụng nếu có thể. Không hardcode hành vi của một driver cũ rồi nâng cấp mà thiếu regression suite.

## 23. Bài tập tổng hợp: lỗi tiền và ngày trên môi trường thật

Một hệ Java nhận request:

~~~json
{
  "externalId": "85f8cae5-9ea0-4ae2-899f-80483c87b1b0",
  "amount": "1.235",
  "fee": null,
  "installmentCount": null,
  "settlementDate": "2026-11-22",
  "submittedAt": "2026-11-22T15:15:00.123456+07:00",
  "localCutoff": "2026-11-22T17:30:00"
}
~~~

Database khai báo `amount NUMERIC(18,2) NOT NULL`, `fee NUMERIC(18,4) NULL`, `installment_count INTEGER NULL`, `settlement_date DATE`, `submitted_at TIMESTAMPTZ`, `local_cutoff TIMESTAMP WITHOUT TIME ZONE`. Code cũ làm:

~~~java
double amount = Double.parseDouble(request.amount());
ps.setDouble(1, amount);

int fee = rs.getInt("installment_count");
Instant when = rs.getTimestamp("submitted_at")
        .toLocalDateTime()
        .atZone(ZoneId.systemDefault())
        .toInstant();
~~~

**Câu hỏi:**

1. Tại sao `double` không phải kiểu an toàn để lưu số tiền decimal?
2. `"1.235"` có thỏa contract tiền scale 2 không? Nếu không, cần xử lý trước hay chờ DB rounding?
3. Khi `installment_count` trong SQL là `NULL`, `getInt()` trả gì và phải kiểm tra gì?
4. Vì sao chuyển `Timestamp → LocalDateTime → systemDefault()` có thể làm sai instant?
5. Với `submittedAt` có offset `+07:00`, nên assert điều gì sau round-trip ở cột `TIMESTAMPTZ`?
6. Có thể suy ra một instant từ `localCutoff=2026-11-22T17:30:00` khi không biết timezone không?
7. Nếu test JPA chỉ `persist()` rồi `find()` trong cùng persistence context, đã kiểm chứng round-trip thật chưa?
8. Hãy đề xuất test cho `NULL`/zero, overflow `NUMERIC`, timestamp microsecond, session timezone và rollback.

### Gợi ý lời giải

- (1) Binary floating point không biểu diễn chính xác mọi số thập phân; nhận `BigDecimal` từ chuỗi có kiểm soát.
- (2) Nếu hợp đồng yêu cầu scale 2 chính xác, dùng `setScale(2, UNNECESSARY)` để từ chối hoặc dùng quy tắc rounding đã được nghiệp vụ phê duyệt; không âm thầm phụ thuộc engine.
- (3) `getInt()` trả `0` cho `NULL`; gọi `wasNull()` ngay sau getter hoặc dùng typed `getObject()` với kiểu wrapper.
- (4) `LocalDateTime` bỏ mất ngữ nghĩa instant; `systemDefault()` có thể khác giữa laptop và CI/production. Đọc `OffsetDateTime` rồi chuyển `toInstant()`.
- (5) So sánh instant, không so offset gốc. Đầu vào đã có chính xác 6 chữ số thập phân nên phù hợp microsecond của PostgreSQL.
- (6) Không. Cần zone ID và quy tắc DST/khoảng không hợp lệ nếu muốn lập lịch thành instant.
- (7) Chưa. Cần flush/clear rồi reload, và test commit trên transaction mới nếu yêu cầu chứng minh dữ liệu bền vững.
- (8) Viết integration test với DB thật, input riêng cho từng case, kiểm tra SQLSTATE và dữ liệu đã commit; không chỉ kiểm tra mock.

## 24. Checklist trước khi tuyên bố mapping persistence đã đúng

1. **Schema:** SQL type, precision/scale, nullable, default, constraint và index phù hợp hợp đồng miền.
2. **Kiểu Java:** dùng `BigDecimal` cho decimal chính xác, wrapper cho nullable, `java.time` đúng ý nghĩa.
3. **Null:** phân biệt `NULL`, zero, false, chuỗi rỗng, field vắng mặt; kiểm tra `wasNull()` hoặc typed getter.
4. **Decimal:** test giá trị thường, min/max, overflow, scale, rounding và thứ tự phép toán.
5. **Ngày giờ:** phân biệt DATE, TIMESTAMP không zone và TIMESTAMPTZ; không coi offset gốc được bảo toàn nếu DB không lưu.
6. **Độ phân giải:** định nghĩa nanosecond/microsecond/second và test theo quy tắc rounding hoặc chuẩn hóa.
7. **Timezone:** test UTC và ít nhất một timezone khác, ngày sát nửa đêm và DST gap/overlap khi use case cần.
8. **Driver/ORM:** xác minh driver version, JDBC typed getter/setter, JPA converter, persistence context và cache.
9. **Round-trip:** ghi, commit, đọc lại từ kết nối/transaction mới; không chỉ so object trong RAM.
10. **Lỗi:** assert NOT NULL/CHECK/UNIQUE/overflow đúng SQLSTATE, rollback sau failure.
11. **Migration:** test dữ liệu lịch sử và schema sau migration, không chỉ record mới.
12. **API boundary:** JSON/serialization không làm mất precision, timezone hoặc trạng thái null.
13. **Concurrency:** mapping vẫn đúng khi hai transaction ghi/đọc và optimistic locking hoạt động.
14. **Bảo mật:** test dùng role, tenant scope và DB test riêng; không log credential/PII.
15. **CI:** test lặp lại ổn định, dữ liệu cô lập, version backend phù hợp, không dựa vào timezone máy chạy.

**Kết luận:** ánh xạ persistence là một hợp đồng **ngữ nghĩa**, không chỉ thao tác chuyển cú pháp giữa Java và SQL. Muốn dữ liệu lưu bền vững và đúng đắn, phải test **null khác zero**, **decimal chính xác khác floating point**, **Instant khác local date-time** và **round-trip qua database thật khác fake repository trong RAM**. Kết hợp kiểm thử domain, JDBC/JPA, schema/migration, commit và API contract sẽ giúp phát hiện những lỗi tiền, ngày giờ và dữ liệu thiếu trước khi chúng xuất hiện trong vận hành.
