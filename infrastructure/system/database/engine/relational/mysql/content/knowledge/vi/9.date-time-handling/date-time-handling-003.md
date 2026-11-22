# Độ chính xác phần giây và quy tắc làm tròn khi lưu

Thời điểm trong ứng dụng thường cần độ chính xác cao hơn một giây: thời gian tạo đơn hàng, log sự kiện, thời điểm nhận thanh toán hoặc thứ tự xử lý các request gần như đồng thời. MySQL hỗ trợ phần giây lẻ cho các kiểu `TIME`, `DATETIME` và `TIMESTAMP`, với độ chính xác từ 0 đến 6 chữ số thập phân. Tuy nhiên, nếu cột không khai báo độ chính xác, MySQL mặc định dùng 0 chữ số; phần giây đầu vào có thể bị làm tròn khi lưu.

Điểm quan trọng là phân biệt **độ chính xác của dữ liệu đầu vào**, **độ chính xác được khai báo ở cột**, **độ chính xác của hàm tạo thời gian** và **quy tắc làm tròn hoặc cắt phần lẻ**. Nếu các tầng này không thống nhất, ứng dụng có thể thấy thời điểm lệch vài mili giây, hai sự kiện bị gộp vào cùng một mốc thời gian hoặc một giá trị bị chuyển sang giây/ngày tiếp theo.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích FSP (fractional seconds precision) và miền giá trị từ 0 đến 6.
- Chọn `TIME(fsp)`, `DATETIME(fsp)` hoặc `TIMESTAMP(fsp)` phù hợp với độ chính xác cần lưu.
- Hiểu hành vi mặc định khi giá trị đầu vào có nhiều chữ số phần giây hơn cột.
- Phân biệt làm tròn với cắt phần lẻ bằng SQL mode `TIME_TRUNCATE_FRACTIONAL`.
- Dùng `NOW(fsp)`, `CURRENT_TIMESTAMP(fsp)` và các hàm thời gian có tham số FSP.
- Kiểm tra carry khi làm tròn qua giây, phút, ngày hoặc năm.
- Thiết kế default, `ON UPDATE`, truy vấn và migration phù hợp với độ chính xác thời gian.

## 1. FSP là gì?

FSP là viết tắt của *fractional seconds precision*, tức số chữ số được lưu sau dấu thập phân của phần giây. MySQL cho phép FSP từ `0` đến `6` đối với `TIME`, `DATETIME` và `TIMESTAMP`.

| Khai báo | Phần giây được lưu | Độ phân giải danh nghĩa |
|---|---|---|
| `DATETIME` hoặc `DATETIME(0)` | Không có chữ số thập phân | 1 giây |
| `DATETIME(1)` | 1 chữ số, ví dụ `.7` | 0,1 giây |
| `DATETIME(2)` | 2 chữ số, ví dụ `.78` | 0,01 giây |
| `DATETIME(3)` | 3 chữ số, ví dụ `.789` | 1 mili giây |
| `DATETIME(4)` | 4 chữ số, ví dụ `.7896` | 0,1 mili giây |
| `DATETIME(5)` | 5 chữ số, ví dụ `.78960` | 10 micro giây |
| `DATETIME(6)` | 6 chữ số, ví dụ `.789600` | 1 micro giây |

FSP là số chữ số phần giây, không phải số byte và cũng không phải cam kết đồng hồ hệ thống luôn đo được chính xác đến mức đó. Ví dụ, `DATETIME(6)` có thể lưu sáu chữ số microsecond, nhưng độ chính xác thực tế của thời điểm do ứng dụng hoặc hệ điều hành cung cấp còn phụ thuộc nguồn đồng hồ.

Nếu bỏ qua FSP, MySQL dùng `0`. Do đó:

```sql
CREATE TABLE event_log (
    event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (event_id)
);
```

`created_at` trong ví dụ có độ chính xác đến giây. Muốn lưu mili giây, phải khai báo `DATETIME(3)`; muốn lưu microsecond, dùng `DATETIME(6)`.

## 2. Những kiểu thời gian hỗ trợ phần giây lẻ

Ba kiểu thời gian hỗ trợ FSP là `TIME`, `DATETIME` và `TIMESTAMP`:

```sql
CREATE TABLE temporal_precision_types (
    id INT NOT NULL PRIMARY KEY,
    duration TIME(3),
    local_event_time DATETIME(6),
    recorded_instant TIMESTAMP(6)
);
```

- `TIME(fsp)` biểu diễn thời gian trong ngày hoặc khoảng thời lượng theo miền của kiểu `TIME`; phần giây có thể có độ chính xác đến microsecond.
- `DATETIME(fsp)` lưu thành phần ngày và giờ như được cung cấp, không tự chuyển đổi theo múi giờ session.
- `TIMESTAMP(fsp)` biểu diễn thời điểm được chuyển đổi giữa múi giờ session và UTC khi ghi/đọc; FSP quyết định số chữ số phần giây được giữ.

FSP không làm thay đổi quy tắc múi giờ của kiểu dữ liệu. `DATETIME(6)` vẫn không tự chuyển đổi múi giờ; `TIMESTAMP(6)` vẫn có chuyển đổi theo session time zone. Khi thiết kế, hãy chọn kiểu dữ liệu theo ý nghĩa thời gian trước, rồi chọn FSP theo độ phân giải cần thiết.

`DATE` và `YEAR` không có phần giây lẻ. Không khai báo FSP cho các kiểu này.

## 3. Tạo bảng để so sánh độ chính xác

Ví dụ sau lưu cùng một giá trị vào ba cột `DATETIME` với độ chính xác khác nhau:

```sql
CREATE TABLE fractional_precision_demo (
    id INT NOT NULL PRIMARY KEY,
    captured_at_0 DATETIME(0) NOT NULL,
    captured_at_3 DATETIME(3) NOT NULL,
    captured_at_6 DATETIME(6) NOT NULL
) ENGINE = InnoDB;

INSERT INTO fractional_precision_demo
    (id, captured_at_0, captured_at_3, captured_at_6)
VALUES
    (1,
     '2025-06-10 14:25:36.789600',
     '2025-06-10 14:25:36.789600',
     '2025-06-10 14:25:36.789600');

SELECT
    id,
    captured_at_0,
    captured_at_3,
    captured_at_6
FROM fractional_precision_demo;
```

Với hành vi mặc định của MySQL, phần giây được làm tròn khi giá trị đầu vào có nhiều chữ số hơn FSP của cột. Kết quả dự kiến:

| Cột | Giá trị được lưu |
|---|---|
| `captured_at_0` | `2025-06-10 14:25:37` |
| `captured_at_3` | `2025-06-10 14:25:36.790` |
| `captured_at_6` | `2025-06-10 14:25:36.789600` |

Cột FSP 0 làm tròn `.789600` lên giây kế tiếp. Cột FSP 3 làm tròn đến mili giây gần nhất, từ `.789600` thành `.790`. Cột FSP 6 giữ nguyên sáu chữ số vì đầu vào đã có đúng độ chính xác mà cột hỗ trợ.

Đây là khác biệt quan trọng: nếu ứng dụng gửi microsecond vào cột `DATETIME` không có FSP, phần lẻ không được giữ nguyên. Việc dữ liệu “đã insert thành công” không có nghĩa thời điểm được lưu chính xác như đầu vào.

## 4. Quy tắc mặc định: làm tròn phần giây

Khi MySQL lưu giá trị có nhiều chữ số phần giây hơn FSP của cột, hành vi mặc định là **làm tròn**. Các chữ số vượt quá độ chính xác đích được dùng để quyết định có tăng chữ số cuối được giữ hay không.

Ví dụ với cột `DATETIME(3)`:

| Đầu vào | Kết quả làm tròn đến FSP 3 |
|---|---|
| `.1234` | `.123` |
| `.1236` | `.124` |
| `.7894` | `.789` |
| `.7896` | `.790` |

Ví dụ với cột `DATETIME(0)`:

| Đầu vào | Kết quả làm tròn đến giây |
|---|---|
| `12:00:10.200000` | `12:00:10` |
| `12:00:10.600000` | `12:00:11` |

Bạn có thể kiểm tra trực tiếp trong SQL:

```sql
SELECT
    CAST('2025-06-10 14:25:36.1234' AS DATETIME(3)) AS rounded_down,
    CAST('2025-06-10 14:25:36.1236' AS DATETIME(3)) AS rounded_up,
    CAST('2025-06-10 14:25:36.600000' AS DATETIME(0)) AS rounded_to_next_second;
```

Kết quả chuyển đổi thể hiện độ chính xác đích của kiểu temporal. Khi kiểm thử ứng dụng, nên dùng các giá trị nằm rõ ràng dưới và trên ngưỡng làm tròn như `.1234` và `.1236`, thay vì chỉ dùng một giá trị thông thường.

## 5. Làm tròn có thể chuyển sang giây hoặc ngày kế tiếp

Khi phần lẻ làm tròn vượt qua giới hạn của giây hiện tại, MySQL điều chỉnh cả phần giây và các thành phần thời gian liên quan. Việc carry có thể đi qua phút, giờ, ngày, tháng hoặc năm.

```sql
CREATE TABLE rounding_boundary_demo (
    id INT NOT NULL PRIMARY KEY,
    at_second DATETIME(0) NOT NULL,
    at_millisecond DATETIME(3) NOT NULL
);

INSERT INTO rounding_boundary_demo
    (id, at_second, at_millisecond)
VALUES
    (1,
     '2025-12-31 23:59:59.999600',
     '2025-12-31 23:59:59.999600');

SELECT * FROM rounding_boundary_demo;
```

Kết quả dự kiến:

| Cột | Giá trị sau khi làm tròn |
|---|---|
| `at_second` | `2026-01-01 00:00:00` |
| `at_millisecond` | `2026-01-01 00:00:00.000` |

Vì vậy, nếu hệ thống dùng thời điểm làm khóa sắp xếp hoặc ranh giới nghiệp vụ, hãy kiểm tra các giá trị gần cuối giây, cuối ngày, cuối tháng và cuối năm. Không giả định làm tròn chỉ thay đổi vài chữ số cuối.

## 6. Cắt phần lẻ thay vì làm tròn

Trong một số hệ thống, yêu cầu là bỏ các chữ số vượt độ chính xác đích mà không làm tăng thời điểm. MySQL cung cấp SQL mode `TIME_TRUNCATE_FRACTIONAL` để cắt phần giây lẻ thay vì làm tròn khi lưu vào cột có FSP thấp hơn đầu vào.

Ví dụ, với đầu vào `2025-06-10 14:25:36.789600`:

| Cột | Mặc định (round) | Có `TIME_TRUNCATE_FRACTIONAL` (truncate) |
|---|---|---|
| `DATETIME(0)` | `2025-06-10 14:25:37` | `2025-06-10 14:25:36` |
| `DATETIME(3)` | `2025-06-10 14:25:36.790` | `2025-06-10 14:25:36.789` |
| `DATETIME(6)` | `2025-06-10 14:25:36.789600` | `2025-06-10 14:25:36.789600` |

Có thể bật mode ở phạm vi session để thử nghiệm:

```sql
-- Lưu lại sql_mode hiện tại của kết nối
SET @old_sql_mode = @@SESSION.sql_mode;

-- Giữ các mode đang có và thêm TIME_TRUNCATE_FRACTIONAL
SET SESSION sql_mode = CONCAT_WS(
    ',',
    NULLIF(@@SESSION.sql_mode, ''),
    'TIME_TRUNCATE_FRACTIONAL'
);

SELECT @@SESSION.sql_mode;
```

Sau đó chèn một hàng khác vào bảng thử nghiệm:

```sql
INSERT INTO fractional_precision_demo
    (id, captured_at_0, captured_at_3, captured_at_6)
VALUES
    (2,
     '2025-06-10 14:25:36.789600',
     '2025-06-10 14:25:36.789600',
     '2025-06-10 14:25:36.789600');

SELECT *
FROM fractional_precision_demo
WHERE id = 2;
```

Trong session có mode truncate, cột FSP 0 giữ `14:25:36`, cột FSP 3 giữ `.789`, còn cột FSP 6 giữ nguyên `.789600`. Sau khi thử nghiệm, khôi phục mode ban đầu:

```sql
SET SESSION sql_mode = @old_sql_mode;
```

`TIME_TRUNCATE_FRACTIONAL` là SQL mode, vì vậy phạm vi và vòng đời của nó gắn với cấu hình session/global tương ứng. Khi bật ở session, kết nối khác không tự nhận thay đổi đó. Trong ứng dụng dùng connection pool, cần tránh để một request thay đổi `sql_mode` rồi trả kết nối về pool mà không reset trạng thái.

Không nên bật mode này chỉ để che giấu việc schema thiếu độ chính xác. Hãy chọn FSP phù hợp với dữ liệu nghiệp vụ trước; chỉ dùng truncation khi quy tắc sản phẩm yêu cầu cắt phần lẻ và nhóm đã thống nhất hành vi.

## 7. Hàm thời gian có tham số FSP

Một số hàm thời gian hiện tại hỗ trợ tham số FSP từ 0 đến 6. Ví dụ:

```sql
SELECT
    NOW(0) AS current_to_second,
    NOW(3) AS current_to_millisecond,
    NOW(6) AS current_to_microsecond,
    CURRENT_TIMESTAMP(6) AS current_timestamp_6,
    UTC_TIMESTAMP(6) AS utc_timestamp_6,
    CURTIME(6) AS current_time_6;
```

Nếu không truyền FSP, hàm trả về độ chính xác mặc định 0. Dùng `NOW(6)` không tự bảo đảm cột đích giữ sáu chữ số; cột cũng phải khai báo FSP tương ứng. Ví dụ:

```sql
CREATE TABLE request_audit (
    audit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    received_at DATETIME(6) NOT NULL,
    PRIMARY KEY (audit_id)
);

INSERT INTO request_audit (received_at)
VALUES (NOW(6));
```

Nếu cột là `DATETIME(3)`, giá trị `NOW(6)` sẽ được làm tròn hoặc cắt theo `sql_mode` của session khi lưu. Để tránh chuyển đổi không cần thiết, có thể gọi `NOW(3)` khi cột chỉ cần mili giây.

`NOW(fsp)` và `CURRENT_TIMESTAMP(fsp)` biểu diễn thời gian hiện tại theo múi giờ session. `UTC_TIMESTAMP(fsp)` trả về thời gian UTC. Độ chính xác phần giây không thay đổi quy tắc múi giờ của hàm.

## 8. DEFAULT và ON UPDATE với độ chính xác phần giây

Với cột cần tự ghi thời điểm tạo và cập nhật, có thể khai báo `DEFAULT CURRENT_TIMESTAMP(fsp)` và `ON UPDATE CURRENT_TIMESTAMP(fsp)`. Nên dùng cùng FSP giữa cột và biểu thức thời gian để tránh làm tròn ngoài ý muốn.

```sql
CREATE TABLE document_revision (
    document_id BIGINT UNSIGNED NOT NULL,
    body TEXT NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL
        DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (document_id)
) ENGINE = InnoDB;
```

Trong ví dụ này, thời điểm tạo và cập nhật được lưu với sáu chữ số phần giây. Nếu chỉ cần mili giây, thay cả kiểu cột và biểu thức thành FSP 3:

```sql
created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
updated_at DATETIME(3) NOT NULL
    DEFAULT CURRENT_TIMESTAMP(3)
    ON UPDATE CURRENT_TIMESTAMP(3)
```

Nếu cột có FSP thấp hơn biểu thức, MySQL phải chuyển giá trị về độ chính xác cột theo quy tắc round/truncate đang áp dụng. Kiểm tra `SHOW CREATE TABLE` để chắc chắn định nghĩa thực tế giống thiết kế mong muốn.

## 9. Chọn FSP theo yêu cầu ứng dụng

Không phải hệ thống nào cũng cần microsecond. FSP cao hơn giữ được nhiều thông tin hơn nhưng tăng dung lượng lưu trữ phần lẻ, kích thước index và độ phức tạp khi so sánh với nguồn thời gian có độ chính xác thấp.

| Nhu cầu | FSP gợi ý | Ví dụ |
|---|---:|---|
| Ngày giờ nghiệp vụ chỉ cần đến giây | 0 | Ngày hiệu lực, lịch hẹn theo phút/giây |
| Ghi nhận log có độ phân giải mili giây | 3 | Thời điểm request, log ứng dụng |
| Đối chiếu sự kiện rất gần nhau | 6 | Telemetry, audit hoặc dữ liệu cần giữ microsecond từ nguồn |

Đây là gợi ý theo độ phân giải dữ liệu, không phải cam kết rằng FSP 6 tạo ra thứ tự duy nhất. Hai sự kiện vẫn có thể có cùng timestamp microsecond; nếu cần thứ tự duy nhất, dùng khóa tăng dần, sequence hoặc một tiêu chí sắp xếp phụ.

### 9.1. Chi phí lưu trữ phần giây

Phần giây lẻ cần thêm dung lượng lưu trữ tùy FSP. Với cách lưu temporal của MySQL, phần fractional seconds dùng thêm:

| FSP | Byte bổ sung cho phần giây |
|---:|---:|
| 0 | 0 |
| 1–2 | 1 |
| 3–4 | 2 |
| 5–6 | 3 |

Đây là dung lượng bổ sung cho phần fractional seconds, chưa phải tổng kích thước của cột. Khi cột temporal được dùng trong index, độ rộng index cũng chịu ảnh hưởng bởi kiểu và độ chính xác của cột.

## 10. Truy vấn theo khoảng thời gian có phần giây

Khi lọc dữ liệu theo thời gian, nên dùng khoảng nửa mở `[start, end)` để tránh phải đoán chữ số cuối của ngày hoặc giây:

```sql
SELECT audit_id, received_at
FROM request_audit
WHERE received_at >= '2025-06-10 00:00:00.000000'
  AND received_at <  '2025-06-11 00:00:00.000000'
ORDER BY received_at, audit_id;
```

Khoảng nửa mở bao gồm thời điểm đầu và loại trừ thời điểm cuối. Cách này hoạt động ổn định dù cột dùng FSP 0, 3 hay 6; không cần viết điều kiện kiểu `23:59:59.999999` để kết thúc một ngày.

Nếu truy vấn dùng equality với một thời điểm đầu vào có nhiều chữ số hơn cột, hãy bảo đảm ứng dụng đã chuẩn hóa độ chính xác trước khi bind parameter. Một giá trị microsecond so với cột FSP 3 có thể được chuyển đổi về mili giây và làm tròn theo quy tắc lưu trữ. Đối với tra cứu theo thời gian, khoảng nửa mở và tham số có cùng FSP với cột thường dễ kiểm soát hơn.

## 11. Migration từ cột không có FSP sang cột có FSP

Một cột khai báo `DATETIME` tương đương FSP 0. Khi đổi sang `DATETIME(3)` hoặc `DATETIME(6)`, dữ liệu cũ không tự có thêm độ chính xác đã mất. Những giá trị hiện tại chỉ có phần giây nguyên; migration không thể khôi phục mili giây hoặc microsecond từ lịch sử.

Ví dụ thay đổi cột:

```sql
ALTER TABLE request_audit
    MODIFY received_at DATETIME(6) NOT NULL;
```

Sau thay đổi, các giá trị cũ vẫn có phần lẻ bằng `.000000`; các lần ghi mới có thể lưu độ chính xác cao hơn nếu client gửi dữ liệu đủ chi tiết. Trước khi migration, hãy kiểm tra:

- Ứng dụng và driver có gửi timestamp với FSP mới hay vẫn chỉ gửi đến giây.
- Các câu lệnh insert/update, default và `ON UPDATE` có khai báo FSP phù hợp.
- Index và khóa ghép có bị tăng kích thước hay ảnh hưởng hiệu năng không.
- Các phép so sánh, sắp xếp và báo cáo có giả định thời gian chỉ đến giây không.
- Thay đổi DDL có cần dựng lại bảng, khóa bảng hoặc ảnh hưởng replication không.

`ALTER TABLE` có thể cần tài nguyên và thời gian tùy engine, phiên bản, kích thước bảng và loại thay đổi. Thử trên bản sao dữ liệu gần production, sao lưu trước và lập kế hoạch triển khai/khôi phục trước khi thay đổi bảng lớn.

## 12. Những lỗi thường gặp

- Khai báo `DATETIME` rồi kỳ vọng MySQL tự lưu microsecond; mặc định FSP là 0.
- Nghĩ `DATETIME(6)` bảo đảm nguồn đồng hồ có độ chính xác một microsecond.
- Không nhận ra MySQL mặc định làm tròn phần lẻ khi đầu vào có nhiều chữ số hơn cột.
- Bật `TIME_TRUNCATE_FRACTIONAL` nhưng quên đây là trạng thái session/global và để rò rỉ qua connection pool.
- Dùng `NOW()` rồi mong có microsecond; cần chỉ rõ `NOW(6)` nếu cần FSP 6.
- Chỉ tăng FSP của cột mà không tăng FSP của default expression hoặc dữ liệu ứng dụng gửi vào.
- Quên làm tròn có thể carry qua giây, ngày, tháng hoặc năm.
- Dùng `23:59:59` làm mốc cuối ngày và bỏ sót dữ liệu có phần giây lẻ.
- Nghĩ migration từ FSP 0 sang FSP 6 khôi phục được phần lẻ đã mất của dữ liệu cũ.
- Dùng timestamp microsecond làm khóa duy nhất dù nhiều sự kiện vẫn có thể có cùng giá trị.

## 13. Checklist thiết kế độ chính xác phần giây

- Đã chọn kiểu `TIME`, `DATETIME` hay `TIMESTAMP` theo ý nghĩa thời gian và quy tắc múi giờ.
- Đã xác định FSP cần thiết: 0, 3 hay 6 (hoặc giá trị khác từ 0 đến 6).
- Đã khai báo FSP rõ ràng cho cột thay vì phụ thuộc mặc định.
- Đã kiểm tra FSP của `NOW()`, `CURRENT_TIMESTAMP()` hoặc hàm thời gian được ứng dụng sử dụng.
- Đã hiểu đầu vào có nhiều chữ số hơn cột sẽ được làm tròn theo mặc định.
- Đã chỉ bật `TIME_TRUNCATE_FRACTIONAL` khi nghiệp vụ thực sự yêu cầu cắt phần lẻ.
- Đã thử giá trị ở dưới và trên ngưỡng làm tròn, cùng trường hợp carry qua ngày/năm.
- Đã dùng cùng FSP cho cột và `DEFAULT`/`ON UPDATE` expression khi cần.
- Đã chọn truy vấn khoảng nửa mở và tham số thời gian có độ chính xác tương thích.
- Đã tính đến dung lượng phần giây, index và tác động migration.
- Đã không giả định FSP cao hơn đồng nghĩa thứ tự sự kiện luôn duy nhất.

FSP quyết định MySQL giữ bao nhiêu chữ số sau phần giây của `TIME`, `DATETIME` và `TIMESTAMP`. Mặc định, MySQL làm tròn khi dữ liệu đầu vào có độ chính xác cao hơn cột; `TIME_TRUNCATE_FRACTIONAL` thay đổi hành vi đó thành cắt phần lẻ. Chọn FSP phù hợp, đồng bộ với hàm thời gian và ứng dụng, rồi kiểm thử cả trường hợp carry sẽ giúp thời điểm được lưu đúng theo quy tắc nghiệp vụ.
