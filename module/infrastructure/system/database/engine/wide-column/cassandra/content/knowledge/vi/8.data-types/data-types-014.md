# Chuyển kiểu, literal, dữ liệu biên và ánh xạ sang Java trong Apache Cassandra

Khi dùng **Apache Cassandra** từ Java, dữ liệu đi qua nhiều ranh giới: JSON/HTTP hoặc message queue ở bên ngoài, object Java trong ứng dụng, **codec** của Java Driver, giá trị có kiểu của **CQL**, rồi tới cell và khóa phân vùng trong cluster. Một giá trị `"42"` có thể là **chuỗi hai ký tự**, **số nguyên 42**, hoặc một đoạn byte mã hóa văn bản; Cassandra **không tự đoán** ý nghĩa theo ý định của lập trình viên.

Bài thuộc chương **Kiểu dữ liệu** của module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**. Mục tiêu module bao gồm kiến trúc wide-column phân tán, partition key, thiết kế bảng theo truy vấn, consistency đọc/ghi, CQL, replication, compaction, repair, xử lý lỗi và tích hợp Java. Vì vậy, ngoài cú pháp literal và `CAST`, bài giải thích vì sao **đúng kiểu và đúng đơn vị** quyết định tính đúng đắn của khóa, dữ liệu biên, retry và truy vấn trên nhiều replica.

## 1. Phân biệt bốn thao tác thường bị gọi chung là “chuyển kiểu”

| Cơ chế | Diễn ra ở đâu? | Ví dụ | Hạn chế quan trọng |
|---|---|---|---|
| **Parse đầu vào** | Ứng dụng Java/API | `Integer.parseInt("42")`, `UUID.fromString(s)` | Phải validate định dạng, miền, timezone, số chiều |
| **CQL literal** | Parser CQL dựa trên kiểu đích/ngữ cảnh | `42`, `'Việt Nam'`, `0x4f4b` | Literal không phải chuỗi tùy ý có thể gán cho mọi cột |
| **CQL `CAST`** | CQL trên các kiểu native có phép chuyển được hỗ trợ | `CAST(amount AS bigint)` | **Không phải** mọi tổ hợp nguồn/đích đều hỗ trợ; có thể mất thông tin |
| **Driver codec** | Java Driver mã hóa/giải mã native protocol | `setBigDecimal`, `getInstant` | Kiểu Java phải tương thích với kiểu cột CQL và codec đang có |

Một luồng dữ liệu nên được thiết kế theo chiều:

~~~text
Dữ liệu nguồn chưa tin cậy
  -> Parse/validate về kiểu miền nghiệp vụ của Java
  -> Kiểm tra giá trị biên, đơn vị, timezone, Unicode, ID
  -> Prepared statement + codec có kiểu
  -> CQL partition/clustering key và cột dữ liệu
  -> Replica/SSTable
  -> Driver decode -> kiểm tra null -> DTO/domain object
~~~

Đừng trông chờ việc `CAST` trong `SELECT` tự thay đổi kiểu dữ liệu lưu trong bảng. Cũng không giả định đổi getter Java, chẳng hạn từ `getInt` sang `getString`, sẽ thực hiện chuyển đổi theo ý muốn: **codec dùng kiểu CQL của cột**, không phải một hệ ép kiểu tùy ý.

## 2. CQL literal: cú pháp dữ liệu khác cú pháp tên cột

Trong CQL, một **literal** là cách viết trực tiếp một giá trị, khác **identifier** là tên bảng/cột/type.

| Kiểu giá trị | Literal minh họa | Cách hiểu |
|---|---|---|
| `int`, `bigint`, `varint` | `42`, `-7`, `9000000000` | Số nguyên không đặt trong dấu nháy |
| `decimal`, `float`, `double` | `19.95`, `1.25e-3` | Số có dấu thập phân hoặc số mũ |
| `boolean` | `true`, `false` | Từ khóa boolean; không phải chuỗi |
| `text`/`varchar`/`ascii` | `'Việt Nam'`, `'OK'` | Chuỗi được bao bằng **nháy đơn** |
| `uuid` | `550e8400-e29b-41d4-a716-446655440000` | Dạng UUID canonical, không phải chuỗi tùy ý |
| `timeuuid` | UUID **v1** hợp lệ | Phải đúng phiên bản thời gian |
| `blob` | `0x4f4b00ff` | Bốn byte nhị phân viết bằng hex |
| `inet` | `'203.0.113.24'`, `'2001:db8::1'` | IPv4/IPv6 literal đặt trong nháy |
| `date` | `'2026-11-21'` | Ngày lịch |
| `timestamp` | `'2026-11-21T08:30:15.123Z'` | Thời điểm UTC đến mili giây |
| `time` | `'09:30:15.123456789'` | Giờ trong ngày đến nano giây |
| `duration` | `1mo2d3h` | Tháng/ngày/nano giây; không phải số giây chung |
| `list<text>` | `['a', 'b']` | Dãy có thứ tự, có thể có giá trị trùng |
| `set<text>` | `{'java', 'cassandra'}` | Tập không có thành viên trùng |
| `map<text,int>` | `{'red': 1, 'blue': 2}` | Key → value |
| `tuple<int,text>` | `(10, 'OK')` | Giá trị theo vị trí |
| UDT | `{street: 'A', city: 'B'}` | Field có **tên** được định nghĩa trong UDT |
| `vector<float,3>` (Cassandra 5.0+) | `[0.1, 0.2, 0.3]` | Đúng ba phần tử số float, không null |

**Cú pháp trông giống nhau không làm hai kiểu trở thành một.** `[0.1,0.2,0.3]` có thể là literal list hoặc vector tùy **kiểu cột/ngữ cảnh**. `'123'` là text literal, khác số `123`; `'false'` là text, khác `false`.

### 2.1. Nháy đơn, nháy kép và escape

Nháy **đơn** bao literal chuỗi; một dấu nháy đơn bên trong được biểu diễn bằng **hai dấu nháy đơn**:

~~~cql
CREATE TABLE labels_by_id (
    label_id uuid PRIMARY KEY,
    display_text text
);

INSERT INTO labels_by_id (label_id, display_text)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'O''Reilly học Cassandra'
);
~~~

Ở đây giá trị thực được lưu là `O'Reilly học Cassandra`. Không dựa vào cách escape bằng dấu backslash của Java, JSON hoặc SQL dialect khác để tạo CQL; mỗi lớp có quy tắc của nó.

Nháy **kép** được dùng khi khai báo/truy cập **identifier có chữ hoa hoặc ký tự đặc biệt**:

~~~cql
-- Hợp lệ nhưng dễ gây bất tiện vì phải giữ đúng chữ hoa.
CREATE TABLE "CaseSensitiveNames" (
    id uuid PRIMARY KEY,
    "DisplayName" text
);
~~~

Tên `"DisplayName"` là **identifier**, không phải chuỗi `'DisplayName'`. Với dự án mới, dùng tên CQL chữ thường `snake_case` thường giảm lỗi truy cập và metadata codec.

Trong Java production, **dùng prepared statements thay vì tự escape chuỗi bằng cách nối CQL**. Không coi việc thay `'` thành `''` bằng tay là thay thế cho bind variable.

### 2.2. Literal có thể là NULL, nhưng NULL không phải “chưa gửi”

~~~cql
UPDATE labels_by_id
SET display_text = null
WHERE label_id = 11111111-1111-4111-8111-111111111111;
~~~

Trong mutation CQL, ghi NULL cho cột thường thường có nghĩa **xóa giá trị** và sinh tombstone. Bỏ cột khỏi một lệnh INSERT/UPDATE, hoặc bind **UNSET** từ driver trong trường hợp hỗ trợ, có ý nghĩa **không ghi cột đó**. Cả hai tình huống có thể làm `SELECT` trả null, nhưng ý nghĩa phân tán và chi phí tombstone khác nhau.

## 3. Bảng CQL dùng xuyên suốt bài thực hành

Yêu cầu giả định của hệ thống: lưu mẫu API của mỗi tenant theo **ngày UTC**, đọc 100 mẫu mới nhất trong ngày, biết mã phản hồi, thời lượng, số tiền chính xác, IP, trạng thái xác nhận và một ít byte chẩn đoán.

~~~cql
CREATE TABLE api_observations_by_tenant_day (
    tenant_id uuid,
    observation_day date,
    observed_at timestamp,
    observation_id uuid,
    status_code smallint,
    latency_us bigint,
    bill_amount decimal,
    attempt_count varint,
    client_ip inet,
    verified boolean,
    display_label text,
    trace_sample blob,
    tags set<text>,
    PRIMARY KEY (
        (tenant_id, observation_day),
        observed_at, observation_id
    )
) WITH CLUSTERING ORDER BY (observed_at DESC, observation_id ASC);
~~~

Thiết kế:

- **`(tenant_id, observation_day)`** là composite partition key; ngày UTC hạn chế sự tăng trưởng của một partition trong thời gian dài.
- **`observed_at timestamp`** là clustering column chính để sắp theo thời điểm nguồn, có độ phân giải **mili giây**.
- **`observation_id uuid`** phân biệt những mẫu có cùng `observed_at` tới mili giây. ID phải ổn định khi retry.
- **`status_code smallint`** chứa số HTTP status code trong miền ứng dụng; Java dùng `short`.
- **`latency_us bigint`** là số **micro giây** đo được; không được hiểu là timestamp epoch hay số mili giây.
- **`bill_amount decimal`** cần độ chính xác thập phân; Java dùng `BigDecimal`.
- **`attempt_count varint`** minh họa số nguyên tùy độ dài; với số lần thử thực tế có giới hạn nhỏ, `int` thường phù hợp hơn.
- **`client_ip inet`**, **`verified boolean`**, **`display_label text`**, **`trace_sample blob`**, **`tags set<text>`** giữ các ngữ nghĩa khác nhau; không tự chuyển thành `text` để cho tiện ghi.

Để hiểu literal, có thể nhập một row thử:

~~~cql
INSERT INTO api_observations_by_tenant_day (
    tenant_id, observation_day, observed_at, observation_id,
    status_code, latency_us, bill_amount, attempt_count,
    client_ip, verified, display_label, trace_sample, tags
) VALUES (
    22222222-2222-4222-8222-222222222222,
    '2026-11-21',
    '2026-11-21T08:30:15.123Z',
    33333333-3333-4333-8333-333333333333,
    200, 123456, 19.95, 3,
    '203.0.113.42', true,
    'Thanh toán thử nghiệm', 0x4f4b,
    {'payment', 'verified'}
);
~~~

IP `203.0.113.42` thuộc dải dùng trong tài liệu, không phải địa chỉ để gửi request thật. `0x4f4b` là **hai byte** hex, tình cờ giải mã ASCII thành “OK”; kiểu `blob` không tự gắn charset.

Truy vấn hợp khóa:

~~~cql
SELECT observed_at, observation_id, status_code, latency_us,
       bill_amount, verified, client_ip
FROM api_observations_by_tenant_day
WHERE tenant_id = 22222222-2222-4222-8222-222222222222
  AND observation_day = '2026-11-21'
LIMIT 100;
~~~

**Không được suy rằng** một cột dữ liệu có kiểu đúng sẽ tạo đường truy vấn theo cột đó. `WHERE client_ip = ...` hoặc `WHERE verified = false` trên tất cả tenant/ngày vẫn cần index/bảng theo truy vấn phù hợp; `CAST` không tạo index.

## 4. Số nguyên và các giá trị biên: kiểm tra trước khi bind

Các kiểu số nguyên CQL có miền khác nhau:

| CQL | Miền giá trị (có dấu) | Java thường dùng | Trường hợp sử dụng |
|---|---|---|---|
| `tinyint` | -128 đến 127 | `byte` | Giá trị trạng thái nhỏ có miền chặt |
| `smallint` | -32.768 đến 32.767 | `short` | Mã nhỏ, ví dụ status code |
| `int` | -2.147.483.648 đến 2.147.483.647 | `int` | Số lượng có giới hạn |
| `bigint` | -9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 | `long` | Epoch millis, latency micro, ID số trong miền 64 bit |
| `varint` | Số nguyên **độ chính xác không giới hạn theo kiểu** | `BigInteger` | Giá trị lớn vượt 64 bit |
| `counter` | Số đếm 64 bit với quy tắc mutation riêng | `long` | Phép tăng/giảm, không phải scalar upsert thông thường |

Kích thước và miền kiểu phải được xác định ở **hợp đồng dữ liệu**. Ví dụ:

- HTTP status `200` vừa miền `smallint`; `32768` thì không. Nhưng HTTP status còn có **miền nghiệp vụ** (mã ba chữ số), nên giá trị `12000` tuy vừa `smallint` vẫn phải bị từ chối nếu không phải mã hợp lệ.
- `latency_us = 123456` có nghĩa 123.456 **mili giây**, không phải 123.456 giây. Đặt hậu tố `_us` để tránh nhầm đơn vị.
- `attempt_count` không cần `varint` chỉ vì Java có `BigInteger`; chọn kiểu vừa đủ để giảm byte và làm rõ hợp đồng.

### 4.1. Java narrowing cast có thể đổi giá trị âm thầm

~~~java
int raw = 200;
byte narrowed = (byte) raw;

System.out.println(narrowed); // -56, KHÔNG phải 200.
~~~

Trong Java, ép `int` sang `byte` lấy 8 bit thấp; nó không kiểm tra miền bằng cách tự ném exception. Vì vậy, nếu giá trị đến từ JSON/HTTP, **đừng viết `setByte(0, (byte) raw)`** mà không validate.

Một helper kiểm tra trước khi chuyển:

~~~java
static byte checkedTinyInt(int value) {
    if (value < Byte.MIN_VALUE || value > Byte.MAX_VALUE) {
        throw new IllegalArgumentException("tinyint ngoài miền");
    }
    return (byte) value;
}

static short checkedSmallInt(int value) {
    if (value < Short.MIN_VALUE || value > Short.MAX_VALUE) {
        throw new IllegalArgumentException("smallint ngoài miền");
    }
    return (short) value;
}
~~~

Phía CQL cũng không nên bị dùng như bộ kiểm tra đầu vào duy nhất. Một literal ngoài miền kiểu đích có thể bị từ chối, nhưng ứng dụng cần báo lỗi nghiệp vụ **trước** khi phát request mạng đến cluster.

### 4.2. BigInteger và chuyển đổi chính xác

~~~java
import java.math.BigInteger;

BigInteger huge = new BigInteger("9223372036854775808");
// Lớn hơn Long.MAX_VALUE.

try {
    long exact = huge.longValueExact();
} catch (ArithmeticException outsideLongRange) {
    // Không thể biểu diễn bằng bigint CQL.
}
~~~

`huge.longValue()` **không** thay thế `longValueExact()`: phép chuyển không kiểm tra có thể mất bit. Nếu lưu `varint`, bind trực tiếp `BigInteger` theo codec `varint`, không vòng qua `double` hoặc `long` để “đơn giản hóa”.

**Tràn số không chỉ gây lỗi lúc INSERT.** Nếu một số đếm trong app cộng bằng `int`, phép toán có thể tràn **trước khi** bind vào Cassandra. Dùng `Math.addExact`/`Math.multiplyExact` cho phép tính cần phát hiện tràn, hoặc chọn miền `long`/`BigInteger` thích hợp.

## 5. decimal, float và double: “cùng là số” không có nghĩa cùng độ chính xác

CQL cung cấp:

- **`decimal`**: số thập phân với độ chính xác thay đổi, Java `BigDecimal`.
- **`float`**: IEEE 754 32 bit, Java `float`.
- **`double`**: IEEE 754 64 bit, Java `double`.

Ví dụ:

~~~java
import java.math.BigDecimal;

BigDecimal exact = new BigDecimal("0.10");
BigDecimal fromBinaryFloat = new BigDecimal(0.1);

System.out.println(exact);           // 0.10
System.out.println(fromBinaryFloat); // Biểu diễn thập phân dài từ double.
~~~

Đối với **tiền tệ, thuế, đối soát**, dùng `BigDecimal` tạo từ **chuỗi thập phân hoặc số nguyên đơn vị nhỏ nhất**, không dùng `new BigDecimal(double)` sau phép tính `double` và mong giá trị có độ chính xác decimal ban đầu.

~~~java
BigDecimal amount = new BigDecimal("19.95");
BigDecimal taxRate = new BigDecimal("0.10");

BigDecimal tax = amount.multiply(taxRate);
BigDecimal rounded = tax.setScale(2, java.math.RoundingMode.HALF_UP);
// rounded = 2.00, theo quy tắc làm tròn minh họa.
~~~

**Quy tắc làm tròn phải do nghiệp vụ quyết định.** Không tự chọn `HALF_UP` cho mọi giao dịch; hệ tài chính có thể dùng `HALF_EVEN`, làm tròn từng dòng hay tổng hóa đơn, hoặc cần lưu scale khác.

### 5.1. Biên của float/double

Những điều nên kiểm tra tại API:

- `Float.isFinite(value)`/`Double.isFinite(value)` để phát hiện `NaN` và `Infinity` trong pipeline số học. Đừng đưa chúng vào key hay embedding mà chưa kiểm tra semantics.
- `0.1` thường không có biểu diễn nhị phân hữu hạn nên phép tính `float`/`double` có thể sai khác nhỏ khi so sánh bằng `==`.
- `-0.0` và `+0.0` có thể cho hành vi xử lý chuỗi/so sánh khác ở một số lớp; đừng dựa vào dấu của zero làm định danh nghiệp vụ.
- `float` chỉ có khoảng 6–9 chữ số thập phân có nghĩa, `double` khoảng 15–17; một số nguyên lớn có thể không còn biểu diễn chính xác từng đơn vị nếu chuyển sang double.

Nếu cần tiền theo **đơn vị nhỏ nhất**, `bigint amount_minor` cũng là lựa chọn tốt khi đồng tiền và scale được xác định rõ. Nhưng không trộn `19.95` **đơn vị tiền** với `1995` **đơn vị nhỏ nhất** trong cùng một cột.

### 5.2. Decimal có scale, Java equals không luôn như compareTo

~~~java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.compareTo(b) == 0); // true: bằng nhau về giá trị số.
System.out.println(a.equals(b));         // false: khác scale.
~~~

Điều này ảnh hưởng đến validation, cache key, test round-trip và serialization. Nếu API quy định scale cố định cho tiền, hãy **chuẩn hóa scale và rounding** trước khi bind; không trông chờ CQL decimal tự áp một scale chung cho mọi nguồn.

## 6. CQL CAST: danh sách được hỗ trợ, không phải parser vạn năng

Cú pháp trên các biểu thức được CQL hỗ trợ:

~~~cql
SELECT
    latency_us,
    CAST(latency_us AS int) AS latency_narrowed,
    CAST(latency_us AS decimal) AS latency_decimal,
    CAST(status_code AS text) AS status_as_text,
    CAST(bill_amount AS bigint) AS amount_truncated
FROM api_observations_by_tenant_day
WHERE tenant_id = 22222222-2222-4222-8222-222222222222
  AND observation_day = '2026-11-21'
LIMIT 10;
~~~

Đọc các dòng đó như **biểu thức trả về trong SELECT**, không phải đổi schema:

- `latency_us bigint → int`: chỉ an toàn khi giá trị nằm trong miền `int`. Với số quá lớn, có thể mất thông tin theo semantics chuyển của Java.
- `bigint → decimal`: chuyển sang một biểu diễn decimal, nhưng không làm thay đổi độ lớn hoặc đơn vị của giá trị.
- `smallint → text`: tạo **chuỗi để hiển thị**, không biến cột `status_code` thành text trong storage.
- `decimal → bigint`: có thể **bỏ phần thập phân**; không nên dùng kết quả này làm phép làm tròn tiền.

Tài liệu Apache Cassandra liệt kê một **ma trận CAST native types**. Một số nhóm chính:

| Nguồn | Đích tiêu biểu được hỗ trợ | Cần ghi nhớ |
|---|---|---|
| `tinyint/smallint/int/bigint/varint` | Các kiểu số khác, `text`, `varchar` theo ma trận | Chuyển hẹp có thể mất số/bit |
| `float/double/decimal` | Các kiểu số và text phù hợp theo ma trận | Chuyển sang số nguyên không phải làm tròn nghiệp vụ |
| `ascii` | `text`, `varchar` | Không tự chuẩn hóa Unicode |
| `boolean` | `text`, `varchar` | Không có CAST ngược text → boolean tổng quát |
| `inet`, `uuid`, `timeuuid` | Một số đích như text; riêng timeuuid có date/timestamp | Không có CAST text → inet/uuid tổng quát |
| `timestamp` | `date`, `text`, `varchar` | Lấy date làm mất giờ/phút/giây |
| `date` | `timestamp` | Tạo mốc thời gian theo semantics CQL, mất ý nghĩa ngày nguồn nếu tự đổi timezone |
| `blob`, collection, tuple, UDT, vector | Không nằm trong ma trận CAST native tổng quát | Cần các API/hàm/chuyển đổi riêng, không đoán CAST |

**Không giả định các câu sau hợp lệ:**

~~~cql
-- Không có CAST tổng quát text -> int:
-- SELECT CAST(display_label AS int) FROM ...;

-- Không có CAST tổng quát text -> uuid:
-- SELECT CAST(display_label AS uuid) FROM ...;

-- Không có CAST tổng quát bigint -> timestamp:
-- SELECT CAST(latency_us AS timestamp) FROM ...;
~~~

Ngay cả khi một phép **`CAST` được phép**, nó **không thay đổi column type**. Nếu sau đó truy vấn `WHERE` dùng partition key cũ, vẫn phải bind đúng kiểu khóa gốc; không cố viết `WHERE CAST(tenant_id AS text) = ...` để né việc parser UUID trong Java. Đường truy cập theo partition key được thiết kế cho khóa **đã mã hóa đúng kiểu**.

### 6.1. Vì sao CAST có thể âm thầm mất dữ liệu?

Tài liệu Cassandra nêu các chuyển `CAST` dựa trên **ngữ nghĩa của Java**. Với số `decimal` có phần lẻ, chuyển sang kiểu nguyên **không đồng nghĩa** `setScale` với một quy tắc nghiệp vụ. Với số vượt miền, phép chuyển hẹp cũng có thể mất thông tin hoặc có quy tắc bão hòa khác tùy nguồn/đích.

**Quy tắc an toàn:** coi `CAST` là tiện ích trình bày/tính toán khi **đã biết miền dữ liệu hợp lệ**, không phải lớp validation. Nếu đòi đúng tuyệt đối, hãy kiểm tra và chuyển trong Java bằng các phương thức `...Exact()` hoặc ràng buộc miền được kiểm thử.

### 6.2. Không chuyển kiểu vật lý cột chỉ bằng SELECT CAST

Ví dụ bảng đang có `status_code text` với giá trị `"200"`, và hệ thống muốn đổi sang `smallint`. Câu `SELECT CAST(status_code AS smallint)` không phải giải pháp — phép text → smallint **không có trong ma trận CAST tổng quát**.

Cách bền vững:

1. Parse `"200"` ở ứng dụng với quy tắc rõ ràng.
2. Validate miền `short` và miền HTTP status.
3. Ghi vào **cột/bảng mới** có kiểu `smallint`.
4. Chuyển luồng đọc/ghi và đối soát dữ liệu.
5. Chỉ dọn dữ liệu cũ khi đã có kế hoạch rollback/retention.

**Đừng `ALTER TABLE` tùy tiện** nếu cột tham gia primary key hoặc kiểu cũ/kiểu mới không tương thích. Trong Cassandra, thay kiểu khóa thường cần **bảng mới + migration**, không phải cast trong query.

## 7. Hàm chuyển đổi thời gian và đơn vị

Các hàm CQL liên quan đến thời gian:

| Hàm | Nguồn | Kết quả |
|---|---|---|
| `to_date(value)` | `timestamp`, `timeuuid` | CQL `date` |
| `to_timestamp(value)` | `date`, `timeuuid` | CQL `timestamp` |
| `to_unix_timestamp(value)` | `date`, `timestamp`, `timeuuid` | Unix **mili giây** dạng `bigint` |
| `CAST(timestamp AS date)` | `timestamp` | CQL `date` theo semantics Cassandra |
| `current_timestamp()` | Không có đối số | CQL `timestamp` hiện tại của nơi thực thi |

Ví dụ:

~~~cql
SELECT
    observed_at,
    to_date(observed_at) AS observation_date,
    to_unix_timestamp(observed_at) AS epoch_ms,
    CAST(observed_at AS text) AS observation_as_text
FROM api_observations_by_tenant_day
WHERE tenant_id = 22222222-2222-4222-8222-222222222222
  AND observation_day = '2026-11-21'
LIMIT 10;
~~~

Phân biệt ít nhất **ba loại timestamp**:

| Khái niệm | Đơn vị | Vai trò |
|---|---|---|
| Cột **`timestamp`** | Unix **mili giây** | Sự kiện xảy ra tại thời điểm nào |
| Cassandra **write timestamp** (`USING TIMESTAMP`, `WRITETIME`) | Unix **micro giây** | Metadata giải quyết xung đột cell |
| `time` | **Nano giây từ nửa đêm** | Giờ trong ngày, không có ngày/timezone |

**Một số có vẻ là timestamp không đủ để xác định đơn vị.** Ví dụ số `1234567890000` có thể được ai đó coi là ms, nhưng một API khác lại đang gửi microseconds. Cần ghi rõ `epoch_ms`, `epoch_us`, `elapsed_ns` và validate đơn vị ngay tại biên giao thức.

### 7.1. `date` khác `timestamp`

`date` chỉ là ngày lịch; nó không có timezone. `timestamp` là mốc tuyệt đối; `Instant` cũng vậy.

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;

Instant sourceTime = Instant.parse("2026-11-20T18:30:00Z");
LocalDate utcDay = sourceTime.atZone(ZoneOffset.UTC).toLocalDate();

System.out.println(utcDay); // 2026-11-20
~~~

Ở Việt Nam (UTC+07:00), mốc đó thuộc **ngày 21/11** theo địa phương. Nếu bảng được partition theo `observation_day` UTC thì Java phải tạo ngày UTC **ở cả nơi ghi và nơi đọc**. Đừng suy ra ngày partition từ timezone mặc định của JVM hoặc cqlsh.

### 7.2. Precision và DST

`Instant` trong Java có thể biểu diễn nanosecond, nhưng CQL `timestamp` lưu tới **mili giây**. Hai event ở `08:30:15.123456Z` và `08:30:15.123987Z` có thể trở thành **cùng `timestamp`** sau khi được mã hóa ở độ phân giải millisecond. Vì vậy, bảng timeline cần `observation_id uuid` làm tie-breaker.

Ngược lại, `time` giữ phần giờ tới nano giây nhưng **không** có ngày hay timezone. Khi chuyển `LocalDate + LocalTime + ZoneId` thành `Instant`, cần xử lý múi giờ mùa hè (DST) nếu có giờ bị lặp/không tồn tại.

~~~java
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.Instant;

LocalDate calendarDay = LocalDate.parse("2026-11-21");
LocalTime openingTime = LocalTime.parse("08:30");
ZoneId storeZone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant openingInstant =
    calendarDay.atTime(openingTime).atZone(storeZone).toInstant();
~~~

`LocalDate` không nên bị đưa vào một `timestamp` “nửa đêm UTC” chỉ để lưu **ngày sinh**. `LocalTime` không nên dùng cho **thời điểm thanh toán**. Chuyển kiểu có thể đúng mặt cú pháp nhưng làm mất ngữ nghĩa.

### 7.3. `duration` không mặc định là `java.time.Duration`

CQL `duration` lưu **tháng, ngày, nano giây**. Java Driver dùng **`CqlDuration`**; `java.time.Duration` của JDK biểu diễn thời lượng trôi qua theo giây/nano giây, không mang thành phần **tháng lịch**.

~~~java
import com.datastax.oss.driver.api.core.data.CqlDuration;

CqlDuration billingCycle = CqlDuration.from("1mo");
CqlDuration retryDelay = CqlDuration.from("30m");

System.out.println(billingCycle.getMonths());   // 1
System.out.println(retryDelay.getNanoseconds()); // 1800000000000
~~~

`1mo` không luôn bằng `30d`; `1d` không luôn tương đương **24 giờ thực** tại một vùng có DST. Nếu cần deadline để truy vấn Cassandra, hãy tính **`due_at timestamp`** theo calendar/ZoneId và lưu riêng; `duration` không có thứ tự đủ để làm clustering key.

## 8. Unicode, ASCII, VARCHAR và chuỗi khóa

`text` và `varchar` trong CQL là các kiểu chuỗi UTF-8 tương đương về ngữ nghĩa; `ascii` chỉ chấp nhận tập ký tự ASCII. Java dùng **`String`** cho cả ba, nhưng **`String` không tự xác nhận giá trị phù hợp `ascii`**.

### 8.1. Các dạng Unicode trông giống nhau

Hai chuỗi “Café” có thể được biểu diễn theo cách khác nhau:

~~~java
import java.text.Normalizer;
import java.nio.charset.StandardCharsets;

String composed = "Caf\u00e9";
String decomposed = "Cafe\u0301";

System.out.println(composed.equals(decomposed)); // false
System.out.println(composed.getBytes(StandardCharsets.UTF_8).length);
System.out.println(decomposed.getBytes(StandardCharsets.UTF_8).length);

String nfc = Normalizer.normalize(decomposed, Normalizer.Form.NFC);
System.out.println(composed.equals(nfc)); // true
~~~

Đối với một **partition key dạng text**, những chuỗi khác byte có thể tạo **partition khác**. Hãy canonicalize ở tầng ứng dụng khi nghiệp vụ coi hai biểu diễn là cùng một định danh, ví dụ username đã chuẩn hóa NFC và case policy.

**Không luôn lower-case mọi chuỗi.** Tên hiển thị, mã sản phẩm phân biệt chữ hoa/thường, email local part và chuỗi pháp lý có quy tắc riêng. Hãy lưu **khóa chuẩn hóa để tra cứu** và **giá trị gốc để hiển thị** khi cần.

### 8.2. Java String.length không đếm ký tự người dùng nhìn thấy

`String.length()` trả về số **UTF-16 code units**, không nhất thiết là số Unicode code points, grapheme clusters hay số byte UTF-8.

~~~java
String label = "💡";
System.out.println(label.length()); // 2 UTF-16 code units
System.out.println(label.codePointCount(0, label.length())); // 1 code point
System.out.println(label.getBytes(StandardCharsets.UTF_8).length); // 4 byte
~~~

Với key/cell cần giới hạn byte, validate kích thước **UTF-8 đã mã hóa**, không dùng `String.length()` như một proxy chính xác cho chi phí lưu trữ. Với UI có giới hạn “30 ký tự người dùng nhìn thấy”, cần quy tắc Unicode grapheme cluster, không chỉ đếm code point.

### 8.3. Validation cho ascii

~~~java
static boolean isAscii(String value) {
    for (int i = 0; i < value.length(); i++) {
        if (value.charAt(i) > 0x7F) {
            return false;
        }
    }
    return true;
}
~~~

Chuỗi `"VND"` hợp miền ASCII; `"Việt"` có ký tự ngoài ASCII và không thích hợp cho cột `ascii`. Tuy nhiên **hợp ASCII chưa đồng nghĩa hợp miền nghiệp vụ**: mã tiền tệ thường có ba chữ cái in hoa và phải nằm trong danh mục hợp lệ.

## 9. UUID, timeuuid, inet và blob: bốn trường hợp cần parser chuyên biệt

### 9.1. UUID không phải text tùy ý

~~~java
import java.util.UUID;

UUID userId = UUID.fromString("550e8400-e29b-41d4-a716-446655440000");
UUID newId = UUID.randomUUID(); // UUID v4
~~~

Dùng `UUID.fromString` và kiểm tra hợp đồng trước khi bind `uuid`; đừng lưu một chuỗi tùy ý vào cột text rồi tự tạo một định dạng ID thiếu nhất quán.

`timeuuid` là UUID **v1**, không phải mọi UUID. Java Driver có `Uuids.timeBased()` để tạo timeuuid ở client. Không dùng `UUID.randomUUID()` (v4) cho cột `timeuuid`.

Nếu dùng CQL `uuid()` hoặc `now()` ngay trong INSERT, retry lệnh có thể **sinh ID mới** sau timeout. Với sự kiện cần idempotency, tạo ID một lần ở ứng dụng và giữ nguyên trong các lần thử.

### 9.2. inet chỉ lưu địa chỉ IP

CQL literal `inet` được viết như chuỗi IP:

~~~cql
-- Cột inet:
-- '203.0.113.42'
-- '2001:db8::42'
~~~

`'api.example.com'` là **hostname**, không phải IP literal; `'203.0.113.0/24'` là **CIDR**, không phải một địa chỉ đơn. `InetAddress.getByName(input)` của Java có thể thực hiện DNS với hostname, vì vậy **không dùng trực tiếp nó để xác thực rằng input là địa chỉ IP literal**.

Một cách tạo địa chỉ thử đã được parse thành bytes:

~~~java
import java.net.InetAddress;

InetAddress address = InetAddress.getByAddress(
    new byte[]{(byte)203, 0, 113, 42}
);
System.out.println(address.getHostAddress()); // 203.0.113.42
~~~

Với input từ API, dùng parser chỉ chấp nhận literal IPv4/IPv6 theo quy tắc rõ ràng, tránh DNS không mong muốn. IP trong log còn có thể là IP proxy/NAT; **đúng kiểu `inet` không xác nhận nguồn gốc**.

### 9.3. Blob là byte, không phải string được đoán charset

Literal:

~~~cql
-- Bốn byte: 00 4f 4b ff
-- 0x004f4bff
~~~

Trong Java:

~~~java
import java.nio.ByteBuffer;

byte[] raw = {0x00, 0x4f, 0x4b, (byte) 0xff};
ByteBuffer snapshot = ByteBuffer.wrap(raw.clone());

ByteBuffer view = snapshot.duplicate();
byte[] actual = new byte[view.remaining()];
view.get(actual);
~~~

`ByteBuffer` có `position`, `limit` và `remaining()`. Đừng dùng `buffer.array()` mặc định: direct/read-only buffer có thể không có accessible array, và array có thể chứa byte nằm ngoài đoạn dữ liệu hợp lệ.

Base64 (`T0s=`) và hex (`0x4f4b`) là **biểu diễn text của bytes**, không phải bản thân bytes trong mọi giao thức. Khi API gửi Base64, ứng dụng phải **decode** trước khi bind `blob`, và phải biết format đầu ra khi đọc.

### 9.4. Hàm blob conversion khác CAST

CQL có nhóm hàm chuyển native type sang cách biểu diễn byte, theo dạng **`type_as_blob(...)`** và chuyển ngược **`blob_as_type(...)`** với kiểu phù hợp. Ví dụ:

~~~cql
SELECT
    latency_us,
    bigint_as_blob(latency_us) AS latency_binary
FROM api_observations_by_tenant_day
WHERE tenant_id = 22222222-2222-4222-8222-222222222222
  AND observation_day = '2026-11-21'
LIMIT 5;
~~~

`bigint_as_blob(3)` có thể biểu diễn 8 byte cho `bigint` theo định dạng CQL; đây **không** phải chuỗi UTF-8 `"3"`. Các hàm blob có mục tiêu **diễn giải/cấp phát bytes theo codec native**, khác với `CAST(... AS text)` dùng để tạo chuỗi.

Không đưa một blob tự do vào `blob_as_bigint` mà không đảm bảo **số byte/định dạng** phù hợp, nếu không có thể gặp lỗi giải mã.

## 10. Collections, tuple, UDT và vector cần codec đúng kiểu

Một số kiểu CQL không thể “cứ CAST sang text rồi tự parse lại” như một giải pháp dữ liệu chuẩn:

| CQL | Literal | Java Driver 4.x |
|---|---|---|
| `list<uuid>` | `[uuid1, uuid2]` | `List<UUID>`, `setList`/`getList` |
| `set<text>` | `{'a','b'}` | `Set<String>`, `setSet`/`getSet` |
| `map<text,int>` | `{'x':1}` | `Map<String,Integer>`, `setMap`/`getMap` |
| `tuple<double,double>` | `(10.77,106.70)` | `TupleValue`, `setTupleValue`/`getTupleValue` |
| `frozen<address_udt>` | `{street:'A',city:'B'}` | `UdtValue`, `setUdtValue`/`getUdtValue` |
| `vector<float,3>` (5.0+) | `[0.1,0.2,0.3]` | `CqlVector<Float>`, `setVector`/`getVector` trên driver tương thích |

**Những điểm biên:**

- `list` có thể chứa phần tử trùng; `set` không giữ bản sao thành viên trùng; `map` có key duy nhất. Đây là ngữ nghĩa kiểu, không phải sự khác nhau về chuỗi literal.
- Không đưa **NULL element** hoặc null map key/value như thể collection là JSON tùy ý.
- Tuple luôn được xử lý như **frozen**; thay đổi một phần tử là thay nguyên giá trị tuple.
- Frozen UDT/collection xử lý như một value; non-frozen hỗ trợ một số cập nhật field/entry theo cú pháp CQL.
- Vector có **N chiều cố định**, không có phần tử NULL và là tính năng phụ thuộc **phiên bản Cassandra/Java Driver**. Lưu vector **không đồng nghĩa** tự có chỉ mục ANN.
- Collection tăng vô hạn không nên bị nhét vào một cell/row. Nếu từng phần tử cần phân trang/TTL/tra cứu độc lập, dùng **bảng nhiều hàng** có primary key phù hợp.

### 10.1. Mẫu Java với set

~~~java
import java.util.Set;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

PreparedStatement changeTags = session.prepare(
    "UPDATE api_observations_by_tenant_day "
  + "SET tags = tags + ? "
  + "WHERE tenant_id = ? AND observation_day = ? "
  + "AND observed_at = ? AND observation_id = ?");

session.execute(
    changeTags.boundStatementBuilder()
        .setSet(0, Set.of("reviewed"), String.class)
        .setUuid(1, tenantId)
        .setLocalDate(2, observationDay)
        .setInstant(3, observedAt)
        .setUuid(4, observationId)
        .build()
);
~~~

Đây là ví dụ thao tác **thêm phần tử set**. Với `list`, phép append sau timeout có thể bị áp dụng lại và tạo phần tử trùng. Với `map`, thay nguyên map để sửa một key có thể làm mất cập nhật đồng thời; khi phù hợp, dùng update từng entry.

## 11. NULL, giá trị thiếu, UNSET và JSON có ngữ nghĩa khác nhau

Một PATCH API cần phân biệt ít nhất ba trạng thái:

| Input từ API | Ý định | CQL/driver |
|---|---|---|
| Trường **vắng mặt** | Giữ giá trị hiện tại | Không nêu trong mutation hoặc bind **UNSET** |
| Trường **có mặt với null** | Xóa giá trị, nếu contract quy định | Bind **CQL NULL**/`setToNull`; tạo tombstone |
| Trường **có mặt với giá trị** | Ghi mới | Bind typed value, kể cả `false`, `0`, `""` |

Ví dụ cập nhật từng phần:

~~~java
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

PreparedStatement patch = session.prepare(
    "UPDATE api_observations_by_tenant_day "
  + "SET display_label = ?, verified = ? "
  + "WHERE tenant_id = ? AND observation_day = ? "
  + "AND observed_at = ? AND observation_id = ?");

// Ví dụ này có khóa và các biến đã được xác định bên ngoài.
session.execute(
    patch.boundStatementBuilder()
        .setString(0, "Đã kiểm tra")
        .unset(1)               // Không thay đổi verified.
        .setUuid(2, tenantId)
        .setLocalDate(3, observationDay)
        .setInstant(4, observedAt)
        .setUuid(5, observationId)
        .build()
);
~~~

Nếu nghiệp vụ yêu cầu **xóa** `display_label`, dùng `setToNull(0)`, không dùng `unset(0)`. Trường `verified=false` là **giá trị thật**, không phải null; dùng `row.isNull("verified")` khi cần phân biệt trạng thái chưa xác nhận.

**Primary key không được NULL hoặc UNSET**: Cassandra cần đủ khóa trong INSERT để định vị row. UNSET là trạng thái bind của một giá trị; nó không phải một giá trị được lưu trong cell.

### 11.1. INSERT JSON có ngoại lệ quan trọng

CQL `INSERT JSON` mặc định xử lý các trường **thiếu trong JSON** như **NULL**; điều này có thể tạo tombstone và xóa giá trị cũ khi upsert cùng primary key. Muốn “trường thiếu thì giữ nguyên”, cần dùng **`DEFAULT UNSET`**:

~~~cql
-- Partial JSON upsert: cột thiếu được bỏ qua.
INSERT INTO api_observations_by_tenant_day
JSON '{"tenant_id":"22222222-2222-4222-8222-222222222222","observation_day":"2026-11-21","observed_at":"2026-11-21T08:30:15.123Z","observation_id":"33333333-3333-4333-8333-333333333333","display_label":"Cập nhật tên"}'
DEFAULT UNSET;
~~~

`DEFAULT UNSET` chỉ áp dụng **trường vắng mặt** trong JSON; nếu JSON có `"display_label": null`, đó vẫn là explicit NULL. Không để dữ liệu đầu vào JSON của client được ghép thẳng vào CQL command bằng string concatenation trong code sản xuất.

### 11.2. Kết quả SELECT null không chứng minh dữ liệu chưa từng tồn tại

Một cột có thể trả null vì **chưa được ghi**, **đã DELETE**, hoặc **TTL đã hết**. Tombstone dùng cho quá trình xóa phân tán; `UNSET` không tạo tombstone cho cột bị bỏ qua. Đừng suy ra lịch sử xóa từ một giá trị đọc null: nếu cần audit, lưu **sự kiện audit riêng** với ID/thời gian/người thực hiện.

## 12. Bảng ánh xạ CQL ↔ Java Driver 4.x

Bảng dưới đây ghi các kiểu/codec thường dùng; tên setter tương ứng với `BoundStatementBuilder`, getter tương ứng với `Row`.

| CQL | Java | Setter | Getter |
|---|---|---|---|
| `ascii`, `text`, `varchar` | `String` | `setString` | `getString` |
| `tinyint` | `byte` | `setByte` | `getByte` |
| `smallint` | `short` | `setShort` | `getShort` |
| `int` | `int` | `setInt` | `getInt` |
| `bigint`, `counter` | `long` | `setLong` cho bigint; **counter cập nhật khác** | `getLong` |
| `varint` | `BigInteger` | `setBigInteger` | `getBigInteger` |
| `decimal` | `BigDecimal` | `setBigDecimal` | `getBigDecimal` |
| `float`, `double` | `float`, `double` | `setFloat`, `setDouble` | `getFloat`, `getDouble` |
| `boolean` | `boolean` | `setBoolean` | `getBoolean` |
| `uuid`, `timeuuid` | `UUID` | `setUuid` | `getUuid` |
| `date` | `LocalDate` | `setLocalDate` | `getLocalDate` |
| `time` | `LocalTime` | `setLocalTime` | `getLocalTime` |
| `timestamp` | `Instant` | `setInstant` | `getInstant` |
| `duration` | `CqlDuration` | `setCqlDuration` | `getCqlDuration` |
| `inet` | `InetAddress` | `setInetAddress` | `getInetAddress` |
| `blob` | `ByteBuffer` | `setByteBuffer` | `getByteBuffer` |
| `list<T>` | `List<T>` | `setList` | `getList` |
| `set<T>` | `Set<T>` | `setSet` | `getSet` |
| `map<K,V>` | `Map<K,V>` | `setMap` | `getMap` |
| `tuple<...>` | `TupleValue` | `setTupleValue` | `getTupleValue` |
| UDT | `UdtValue` | `setUdtValue` | `getUdtValue` |
| `vector<float,N>` (5.0+) | `CqlVector<Float>` | `setVector` | `getVector` |

**Với `counter`**, không dùng `INSERT`/`setLong` như một cột bigint thường để tăng đếm. Counter có cú pháp `UPDATE ... SET count = count + ?` và đặc tính **không idempotent** khi retry; nó cần một quy trình riêng.

**Với Java primitive getters**, null có thể được ánh xạ sang giá trị mặc định của primitive. Vì vậy khi null có ý nghĩa nghiệp vụ, phải kiểm tra **`row.isNull("column")` trước**:

~~~java
Integer status = row.isNull("status_code")
    ? null : (int) row.getShort("status_code");

Boolean verifiedValue = row.isNull("verified")
    ? null : row.getBoolean("verified");
~~~

Một `Boolean false` khác **null**; một `Integer 0` khác null. Đừng làm mất thông tin “chưa có giá trị” chỉ vì DTO dùng primitive mặc định.

### 12.1. Codec được chọn theo kiểu CQL, không chỉ Java Class

`String` trong Java có thể tương ứng `text`, `varchar`, hoặc `ascii`. `UUID` có thể là `uuid` hoặc `timeuuid`. Vì vậy, driver cần kiểu CQL của **prepared bind variable/column metadata** để chọn đúng codec.

Với **simple statement** không có type metadata đầy đủ, suy luận mặc định có thể khác ý định. Ví dụ một `String` thường được suy thành `text`, không tự thành `ascii` hoặc `inet`. Prepared statement giúp binding đúng kiểu rõ ràng hơn và tránh viết literal thủ công.

Codec tùy chỉnh có thể hỗ trợ domain object riêng, nhưng cần test **encode/decode round-trip**, null, byte order, kích thước, tương thích phiên bản và mọi node/client sử dụng schema.

## 13. Java end-to-end: validate rồi ghi bằng prepared statement

Giả sử dữ liệu nguồn chứa:

~~~json
{
  "statusCode": 200,
  "latencyMicros": 123456,
  "billAmount": "19.95",
  "attemptCount": "3",
  "clientIp": "203.0.113.42",
  "verified": true,
  "displayLabel": "Thanh toán thử nghiệm"
}
~~~

Hai số `"19.95"` và `"3"` được truyền dạng **string trong JSON** là một lựa chọn contract có chủ đích để tránh lớp trung gian parse chúng thành floating-point hoặc làm mất độ chính xác của `BigInteger`. Không phải mọi API bắt buộc làm như vậy; điều bắt buộc là thống nhất kiểu và validation.

### 13.1. Tạo các giá trị Java có kiểu

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

import java.math.BigDecimal;
import java.math.BigInteger;
import java.net.InetAddress;
import java.nio.ByteBuffer;
import java.text.Normalizer;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.Set;
import java.util.UUID;

// CqlSession session = ...; // Đã kết nối cluster và chọn keyspace.
UUID tenantId =
    UUID.fromString("22222222-2222-4222-8222-222222222222");
UUID observationId =
    UUID.fromString("33333333-3333-4333-8333-333333333333");

Instant observedAt = Instant.parse("2026-11-21T08:30:15.123Z");
LocalDate observationDay =
    observedAt.atZone(ZoneOffset.UTC).toLocalDate();

short statusCode = checkedSmallInt(200);
long latencyMicros = 123456L;
if (latencyMicros < 0) {
    throw new IllegalArgumentException("latency không được âm");
}

BigDecimal amount = new BigDecimal("19.95");
if (amount.signum() < 0 || amount.scale() > 2) {
    throw new IllegalArgumentException("billAmount không hợp lệ");
}
BigInteger attempts = new BigInteger("3");
if (attempts.signum() < 0) {
    throw new IllegalArgumentException("attempts phải >= 0");
}

// IP đã được parse/validate thành 4 byte, không DNS.
InetAddress ip = InetAddress.getByAddress(
    new byte[]{(byte)203, 0, 113, 42}
);

String label = Normalizer.normalize(
    "Thanh toán thử nghiệm", Normalizer.Form.NFC
);

byte[] traceBytes = {0x4f, 0x4b};
ByteBuffer trace = ByteBuffer.wrap(traceBytes.clone());
~~~

Code dùng `checkedSmallInt(int)` đã định nghĩa ở phần số nguyên; trong project thực tế, hãy đặt validation helper cùng module/domain tương ứng. Những kiểm tra minh họa không thay toàn bộ chính sách HTTP status, quy mô tiền, hạn mức nghiệp vụ và bảo vệ dữ liệu cá nhân.

### 13.2. Bind đúng kiểu và giữ statement qua retry

~~~java
PreparedStatement ps = session.prepare(
    "INSERT INTO api_observations_by_tenant_day "
  + "(tenant_id, observation_day, observed_at, observation_id, "
  + " status_code, latency_us, bill_amount, attempt_count, "
  + " client_ip, verified, display_label, trace_sample, tags) "
  + "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)");

BoundStatement stmt = ps.boundStatementBuilder()
    .setUuid(0, tenantId)
    .setLocalDate(1, observationDay)
    .setInstant(2, observedAt)
    .setUuid(3, observationId)
    .setShort(4, statusCode)
    .setLong(5, latencyMicros)
    .setBigDecimal(6, amount)
    .setBigInteger(7, attempts)
    .setInetAddress(8, ip)
    .setBoolean(9, true)
    .setString(10, label)
    .setByteBuffer(11, trace)
    .setSet(12, Set.of("payment", "verified"), String.class)
    .build();

session.execute(stmt);

// Nếu timeout/connection reset, đơn vị công việc có thể
// retry với chính tenantId, observationDay, observedAt,
// observationId và các giá trị đã chốt này.
~~~

Với thao tác async, đừng sửa `ByteBuffer`, mảng nguồn, collection hoặc object mutable mà request còn sử dụng; tạo snapshot dữ liệu khi cần. Việc sử dụng **cùng primary key** là điều kiện cần cho idempotency của một insert/upsert sự kiện, nhưng nếu cột được tính lại với giá trị khác và write timestamp khác, kết quả xung đột vẫn phải được xem xét.

### 13.3. Đọc có kiểm tra null

~~~java
import com.datastax.oss.driver.api.core.cql.Row;

PreparedStatement find = session.prepare(
    "SELECT status_code, latency_us, bill_amount, attempt_count, "
  + " client_ip, verified, display_label, trace_sample "
  + "FROM api_observations_by_tenant_day "
  + "WHERE tenant_id = ? AND observation_day = ? "
  + "AND observed_at = ? AND observation_id = ?");

Row row = session.execute(
    find.bind(tenantId, observationDay, observedAt, observationId)
).one();

if (row != null) {
    Integer status = row.isNull("status_code")
        ? null : (int) row.getShort("status_code");

    Long latency = row.isNull("latency_us")
        ? null : row.getLong("latency_us");

    BigDecimal bill = row.getBigDecimal("bill_amount");
    BigInteger attemptsRead = row.getBigInteger("attempt_count");
    InetAddress clientIp = row.getInetAddress("client_ip");

    Boolean verifiedRead = row.isNull("verified")
        ? null : row.getBoolean("verified");

    ByteBuffer binary = row.getByteBuffer("trace_sample");
    // Nếu binary != null, đọc theo remaining(), không
    // mặc định gọi array() trên buffer.
}
~~~

Hai tình huống khác nhau cần phân biệt: **`row == null`** (không tìm thấy row cho khóa truy vấn) và **`row.isNull("status_code")`** (row có nhưng cột thiếu/đã xóa/hết TTL). Không đánh đồng hai trạng thái khi xuất DTO hoặc ra quyết định nghiệp vụ.

## 14. Truy vấn theo kiểu đã lưu, không CAST để né partition key

Bảng ở phần 3 được thiết kế để đọc theo **tenant + ngày UTC**:

~~~cql
SELECT observed_at, observation_id, bill_amount
FROM api_observations_by_tenant_day
WHERE tenant_id = 22222222-2222-4222-8222-222222222222
  AND observation_day = '2026-11-21'
  AND observed_at >= '2026-11-21T08:00:00Z'
  AND observed_at <  '2026-11-21T09:00:00Z'
LIMIT 100;
~~~

Cassandra cần đủ **partition key**, rồi có thể dùng **clustering range**. Không mong `CAST(observed_at AS text)` tạo thứ tự text hữu ích hơn timestamp; cũng không áp một biểu thức chuyển kiểu vào `WHERE` rồi coi đó là “index mới”.

### 14.1. Dữ liệu biên của khóa gây lỗi phân vùng

| Sai khác nhỏ | Hệ quả có thể xảy ra |
|---|---|
| `observation_day` tính theo UTC ở ghi, theo timezone hệ thống ở đọc | Tìm nhầm partition ngày |
| Username key NFC so với NFD | Hai partition text khác nhau |
| Ghi event ID mới sau timeout | Hai row cho cùng nghiệp vụ |
| Dùng `timestamp` đơn lẻ mà không có UUID phụ | Hai event trùng millisecond dùng cùng primary key |
| Serialize key binary khác byte order giữa client | Khóa nhị phân khác nhau |
| Dùng IP proxy thay IP nguồn đáng tin trong key theo IP | Nhiều người dùng gom cùng partition/hotspot |
| Chuyển `bigint` ID thành `double` ở lớp JSON trung gian | Mất bit thấp, khóa sai |

**Một kiểu dữ liệu CQL hợp lệ không đảm bảo một partition key được phân phối tốt**. Ví dụ `boolean` có thể dùng trong khóa theo quy tắc kiểu, nhưng partition key chỉ có hai giá trị `true/false` sẽ tạo rất ít partition và dễ nóng với dữ liệu lớn. Chọn khóa dựa trên mẫu truy vấn, cardinality, kích thước partition và tải thực tế.

### 14.2. Khi phải chuyển schema/kiểu khóa

Nếu đã dùng `customer_id text` nhưng sau này muốn `uuid`, không nên kỳ vọng `ALTER TABLE ...` hoặc `CAST` có thể chuyển dữ liệu an toàn tại chỗ, nhất là khi cột nằm trong **PRIMARY KEY**. Khóa quyết định cách Cassandra mã hóa token và tìm row.

Quy trình an toàn:

1. Tạo **schema/bảng mới** với kiểu đích.
2. Chuẩn hóa và validate tất cả ID nguồn; phân loại giá trị không parse được.
3. Tạo mapping **old ID → new UUID** nếu không thể chuyển một-một mà giữ cùng định danh.
4. Ghi dữ liệu mới với **khóa ổn định**, dual-write khi cần.
5. Backfill có rate limit, checkpoint và retry idempotent.
6. Đối soát count/key/sample, giá trị biên, phân vùng, các bảng truy vấn khác.
7. Chuyển đọc, quan sát lỗi/latency, rồi dừng bảng cũ theo rollback plan.

**Đổi type của cột không phải đổi biểu diễn khi in ra màn hình.** Với `text → uuid`, `decimal → bigint` hoặc `timestamp → bigint`, phải quyết định ngữ nghĩa và kế hoạch migration riêng.

## 15. Các giá trị biên cần đưa vào test từ đầu

Để kiểm thử code ghi/đọc Cassandra, đừng chỉ dùng `1`, `"hello"`, một UUID đẹp và timestamp hiện tại. Ít nhất nên có ma trận sau:

| Nhóm | Test case | Điều cần xác minh |
|---|---|---|
| Số nguyên | Min/max của tinyint/smallint/int/bigint | Round-trip không đổi giá trị |
| Số nguyên | Min−1 / Max+1 | Validation từ chối trước bind |
| BigInteger | `Long.MAX_VALUE + 1` | `varint` giữ được, `bigint` không |
| Decimal | `0.1`, `19.95`, `1.00`, scale lớn | Không tạo từ double, rounding rõ |
| Floating point | `0.1f`, `-0.0`, `NaN`, infinity | Kiểm tra finite, không dùng làm tiền/ID |
| Boolean | `true`, `false`, null | False không bị đọc thành “chưa có giá trị” |
| Unicode | NFC/NFD, emoji, nháy đơn, chuỗi rỗng | Canonicalization, escape và byte length |
| ASCII | `ABC`, `Việt` | Đúng ASCII, validation miền |
| Time | Mốc UTC, offset khác UTC, trước epoch, DST | Round-trip/diễn giải timezone đúng |
| Precision | Hai `Instant` khác nhau dưới 1ms | Biết timestamp CQL có thể trùng |
| Date | Ngày UTC khác ngày địa phương | Bucket nhất quán |
| UUID | UUID v4, timeuuid v1, chuỗi sai định dạng | Không đưa nhầm version hoặc sinh lại retry |
| Blob | `0x00ff`, empty bytes, direct/read-only ByteBuffer | Đọc đúng remaining, không lệ thuộc array |
| IP | IPv4, IPv6, hostname, CIDR | Chỉ parse IP literal nếu schema là inet |
| Collection | Empty/null/thiếu, phần tử lặp, item NULL | Đúng ngữ nghĩa CQL và API |
| UDT/tuple | Field thiếu, index sai, frozen value | Codec và đơn vị cập nhật đúng |
| Vector | Sai dimension, NaN, zero norm, model khác | Chỉ khi cluster/driver hỗ trợ |
| Mutation | Missing field, explicit null, UNSET, TTL hết hạn | Giữ/xóa đúng, tombstone có chủ đích |
| Retry | Timeout sau khi coordinator có thể đã ghi | Cùng primary key, cùng dữ liệu nghiệp vụ |

### 15.1. Test round-trip, không chỉ test câu INSERT trả thành công

Với một input \(x\), kiểm thử:

~~~text
Input x
 -> Java parse + validate
 -> Driver encode
 -> CQL write
 -> CQL read
 -> Driver decode
 -> Value y
 -> So sánh x và y theo ngữ nghĩa đã chọn
~~~

Phải định nghĩa **thế nào là bằng nhau**:

- Với `BigDecimal`, có thể so `compareTo == 0` theo giá trị số hoặc cần **đúng scale**.
- Với `Instant` → CQL `timestamp`, nên so ở **độ phân giải mili giây**; không mong giữ nano giây.
- Với Unicode, nếu canonicalize, so giá trị **sau normalization** chứ không so raw input.
- Với `ByteBuffer`, so **cùng chuỗi byte trong vùng remaining**, không so object identity.
- Với `set`, không so thứ tự hiển thị; với `list`, thứ tự là một phần ngữ nghĩa.

### 15.2. Không quên dữ liệu xấu và nguồn JSON

Một ingest pipeline có thể nhận:

~~~json
{
  "statusCode": 9999999999,
  "billAmount": "19,95",
  "verified": "false",
  "observedAt": "21/11/2026 15:30",
  "clientIp": "api.example.com"
}
~~~

Mỗi trường có một vấn đề riêng:

- `9999999999` vượt miền `smallint` và cả `int`; phải từ chối hoặc route vào dead-letter queue.
- `"19,95"` không phải decimal chuẩn với dấu chấm theo contract đã chọn; không đoán locale trong parser tài chính.
- `"false"` là chuỗi JSON, khác boolean JSON `false`; quyết định có hỗ trợ parse chuỗi hay không ở API.
- `"21/11/2026 15:30"` thiếu timezone và format chuẩn; cần schema hợp đồng rõ.
- `"api.example.com"` là hostname, không phải IP literal cho `inet`.

Đừng dùng **CQL CAST** để làm sạch mọi loại input trên coordinator: đó không phải một chức năng ingest validation tổng quát, và đẩy dữ liệu lỗi qua mạng có thể làm tăng tải cluster.

## 16. Các lỗi thường gặp và cách xử lý

| Sai lầm | Hệ quả | Cách sửa |
|---|---|---|
| Nghĩ chuỗi `'123'` luôn tự chuyển sang int | Type mismatch hoặc ngữ nghĩa không rõ | Parse/validate ở ứng dụng, bind `setInt` |
| Dùng `CAST(text AS int)` như parser | Không thuộc bảng CAST native được hỗ trợ | Chuyển trước bằng Java, migration có kiểm soát |
| Ép `int` thành `byte` không kiểm miền | `200` thành `-56` | Kiểm `Byte.MIN_VALUE/MAX_VALUE` |
| Đổi `BigInteger` thành `long` bằng `longValue()` | Mất bit ngoài miền | `longValueExact()` hoặc giữ `varint` |
| Tạo BigDecimal từ `double` | Mang sai số biểu diễn nhị phân | `new BigDecimal("19.95")` |
| Dùng `float/double` cho tiền | Đối soát sai do binary precision | `decimal` hoặc `bigint` đơn vị nhỏ nhất |
| Dùng CAST decimal → int để làm tròn | Cắt phần lẻ/khác rounding nghiệp vụ | Rounding explicit trong Java |
| Nhầm ms với µs của `WRITETIME` | Thời gian lệch 1000 lần | Đặt tên và kiểm đơn vị |
| Mất nano giây khi ghi `Instant` vào timestamp | Hai event có thể trùng ms | Dùng UUID tie-breaker/sequence nguồn |
| Tính bucket bằng timezone mặc định JVM | Ghi và đọc sai partition | Dùng ZoneOffset.UTC hoặc business ZoneId thống nhất |
| Dùng `String.length()` làm số byte UTF-8 | Kiểm kích thước sai với Unicode | `getBytes(UTF_8).length` |
| Dùng `ascii` chứa tiếng Việt có dấu | Vi phạm miền ký tự | `text` cho Unicode |
| Coi NFC và NFD là một partition key | Tạo khóa khác cho chuỗi nhìn giống | Normalizer/canonical key |
| Gọi `InetAddress.getByName` để “chỉ parse IP” | Có thể thực hiện DNS | Parser literal + getByAddress |
| Bind UUID v4 vào `timeuuid` | Không đúng phiên bản CQL | Tạo UUID v1 |
| Dùng `ByteBuffer.array()` không kiểm tra | Lấy thừa bytes hoặc lỗi direct buffer | `duplicate()` + `remaining()` |
| Gửi NULL cho trường PATCH vắng | Xóa dữ liệu/tombstone không mong muốn | UNSET/không nêu cột |
| Gửi lại list append sau timeout | Có thể thêm phần tử trùng | Event ID ổn định hoặc bảng nhiều row |
| Ghi `vector<float,N>` vào cluster cũ | Schema/codec unsupported | Kiểm tra Cassandra/driver version |
| Chuyển kiểu khóa bằng `ALTER` không có migration | Token/row lookup thay đổi, mất nhất quán | Bảng mới, backfill, đối soát, cutover |
| Nghĩ `LOCAL_QUORUM` sửa được cast sai | Replica chỉ đồng bộ dữ liệu đã ghi | Validate và sửa dữ liệu tại nguồn |

## 17. Vận hành phân tán: dữ liệu sai vẫn có thể được replicate hoàn hảo

Một số lỗi dữ liệu không nằm ở cú pháp CQL mà ở **cách hiểu**:

- `latency_us = 5000` được service khác đọc như 5000 **ms**;
- `display_label` dùng NFC ở service A và NFD ở service B;
- `observation_day` được tạo theo UTC khi ghi, theo local timezone khi tìm;
- số tiền `19.95` bị đổi qua double rồi ghi thành giá trị decimal có nhiều chữ số ngoài ý muốn;
- hai worker tạo `observation_id` khác nhau cho cùng một request sau timeout.

**Replication** có thể sao chép những byte/giá trị đã ghi rất chính xác. **Repair** giúp replica hội tụ theo metadata ghi. **Compaction** sắp xếp SSTable và xử lý tombstone khi đủ điều kiện. **Không cơ chế nào tự suy ra “đúng đơn vị tiền”, “đúng ngày UTC”, hay “hai ID thực chất là một sự kiện”.**

Cassandra `INSERT` thường là **upsert** theo primary key. Khi retry:

1. Giữ **cùng partition key/clustering key**, không tạo ID mới.
2. Giữ **cùng giá trị đã chuẩn hóa**, không tính lại `Instant.now()` hoặc rounding theo context khác.
3. Nếu cập nhật nhiều bảng phục vụ truy vấn, có cơ chế đối soát/khôi phục. Nhiều CQL statements không tự là một transaction ACID đa partition.
4. Khi phải đảm bảo “chỉ tạo nếu chưa tồn tại”, cân nhắc `IF NOT EXISTS` (LWT) và xử lý kết quả `[applied]`/timeout, thay vì tưởng UUID tự là ràng buộc uniqueness nghiệp vụ.
5. Không dùng mức nhất quán `LOCAL_QUORUM` như biện pháp chữa dữ liệu nhập sai kiểu; consistency điều chỉnh xác nhận replica, không validate nghiệp vụ.

### 17.1. TTL và write timestamp cũng có đơn vị riêng

- `USING TTL` nhận thời gian sống tính bằng **giây**.
- `USING TIMESTAMP` của mutation là **micro giây** để quyết định version ghi.
- Cột CQL `timestamp` là **mili giây** cho thời điểm nghiệp vụ.
- `time` biểu diễn **nano giây trong ngày**, không phải deadline tuyệt đối.
- `duration` chứa thành phần tháng/ngày/nano giây, không thể tự đổi sang TTL theo giây mà luôn đúng theo lịch.

Đặt hậu tố đơn vị trong code (`_sec`, `_ms`, `_us`, `_ns`) và viết test round-trip sẽ loại bỏ nhiều bug khó thấy hơn là dựa vào CQL CAST.

### 17.2. Theo dõi lỗi encode/decode và schema drift

Trong production, nên đo:

- Số lỗi validation theo field và nguồn dữ liệu.
- Lỗi `CodecNotFound`/type mismatch/invalid query, cùng version Java Driver/cluster.
- Tỷ lệ dead-letter records của ingest, retry và idempotency conflict.
- Số partition bị quá lớn/hotspot theo tenant/day; p95/p99 read/write latency.
- Tombstone và compaction/repair backlog nếu ứng dụng ghi NULL hàng loạt.
- Schema agreement và rollout phiên bản khi thêm UDT/vector hoặc đổi codec.

Không log toàn bộ dữ liệu cá nhân, IP, payload hoặc blob không kiểm soát chỉ để debug lỗi type conversion. Hãy redaction, trace ID và dùng mẫu dữ liệu giả lập trong tài liệu/test.

## 18. Bài tập có đáp án

### Bài 1 — Literal khác kiểu

Cho hai giá trị CQL:

~~~text
123
'123'
~~~

**Hỏi:** Có giống nhau không? Có nên gửi `"123"` từ API rồi bind bằng `setString` vào cột `int`?

**Đáp án:** không. Một giá trị là số nguyên literal, giá trị còn lại là chuỗi. Với cột `int`, parse `"123"` thành `int` ở ứng dụng, validate miền rồi bind `setInt` thông qua prepared statement.

### Bài 2 — Chuyển hẹp bị tràn

~~~java
int incoming = 200;
byte status = (byte) incoming;
~~~

**Hỏi:** `status` có bằng 200 không?

**Đáp án:** không, bằng `-56`. Dùng `tinyint` chỉ nếu miền hợp lệ đến 127. HTTP status 200 thường dùng `smallint` hoặc `int`, không dùng `tinyint`.

### Bài 3 — Decimal so với double

~~~java
BigDecimal a = new BigDecimal("19.95");
BigDecimal b = new BigDecimal(19.95);
~~~

**Hỏi:** Vì sao hai kết quả có thể khác?

**Đáp án:** `b` bắt đầu từ số thực nhị phân IEEE 754 không biểu diễn chính xác 19.95; `a` parse chữ số thập phân trực tiếp. Dùng `BigDecimal` từ chuỗi/đơn vị nhỏ nhất cho nghiệp vụ tài chính và quy tắc rounding tường minh.

### Bài 4 — Timestamp, timezone và bucket

Sự kiện `2026-11-20T18:30:00Z` được ghi theo bucket ngày UTC, nhưng một Java client tạo bucket bằng `ZoneId.of("Asia/Ho_Chi_Minh")`.

**Đáp án:** bucket UTC là `2026-11-20`, còn ngày địa phương ở Việt Nam là `2026-11-21`. Nếu quy tắc bảng là ngày UTC, client phải dùng UTC ở cả ghi và đọc.

### Bài 5 — NULL vs UNSET

Row đã có `verified = true`. API PATCH chỉ gửi `displayLabel`, không gửi `verified`.

**Hỏi:** Bind `setToNull` hay `unset` cho cột verified?

**Đáp án:** **UNSET** (hoặc không đưa cột vào mutation) để giữ nguyên true. `setToNull` là xóa verified, sinh tombstone nếu thao tác hợp lệ.

### Bài 6 — Blob từ API Base64

API gửi `"T0s="`, đây là Base64 của bytes `4f 4b`.

**Hỏi:** Nếu lưu `"T0s="` vào cột `text` thì dữ liệu có giống lưu `0x4f4b` vào `blob` không?

**Đáp án:** không. `text` chứa bốn ký tự; `blob` chứa hai byte. Muốn lưu đúng bytes, dùng `Base64.getDecoder().decode(value)` và `ByteBuffer.wrap(...)`.

### Bài 7 — CAST có giải quyết migration?

Bảng có `customer_id text PRIMARY KEY`; nhiều giá trị hiện là mã như `"0000123"`. Đội kỹ thuật muốn đổi cột thành `uuid`.

**Đáp án:** không thể chỉ dùng `CAST(customer_id AS uuid)` (không thuộc phép CAST native được hỗ trợ) hay đổi Java getter. Mã nguồn thậm chí **không phải UUID**, cần chính sách cấp/mapping ID, bảng mới, backfill và đối soát.

### Bài 8 — Thứ tự thời gian có đủ không?

Hai request có `observed_at = 08:30:15.123Z`, cùng tenant/ngày, nhưng `observation_id` khác nhau.

**Hỏi:** Bảng có lưu được hai row không? Có biết request nào xảy ra trước ở nano giây không?

**Đáp án:** có thể lưu hai row vì primary key đầy đủ khác nhau. Nhưng thứ tự phụ khi timestamp trùng được xác định bởi comparator UUID, **không phải thứ tự thực dưới mili giây**. Nếu cần thứ tự nguồn sâu hơn, bổ sung sequence/timestamp độ phân giải cao đã được kiểm chứng.

## 19. Checklist review chuyển kiểu, literal và dữ liệu biên

- [ ] Mọi dữ liệu nguồn đã được **parse và validate** trong Java, không dựa vào Cassandra tự đoán type?
- [ ] Literal CQL đúng quy tắc nháy đơn, boolean, UUID, IP, hex blob, collection/UDT/vector?
- [ ] Có dùng **prepared statement** thay vì nối chuỗi CQL và escape thủ công?
- [ ] Các phép `CAST` được dùng chỉ khi cặp nguồn/đích nằm trong **ma trận hỗ trợ**, không lạm dụng như parser text?
- [ ] Có biết chuyển số hẹp có thể mất thông tin; dùng `...Exact()`/kiểm tra miền khi cần?
- [ ] Tiền dùng `BigDecimal` hoặc `bigint` đơn vị nhỏ nhất, **không** tính bằng float/double?
- [ ] Đã quy định scale/rounding của decimal và kiểm tra `BigDecimal.equals` so với `compareTo`?
- [ ] Đã kiểm tra `NaN`, infinity, `-0.0` và sai số float/double theo workload?
- [ ] Có phân biệt **timestamp ms**, **write timestamp µs**, **TTL seconds**, **time ns** và **duration calendar**?
- [ ] Mọi chuỗi ISO timestamp có timezone/offset rõ ràng và bucket ngày được tính thống nhất?
- [ ] Unicode key đã có chính sách **NFC/NFD, case folding, byte length**, không dùng `String.length()` thay cho kích thước UTF-8?
- [ ] ASCII được validate đúng miền; giá trị có dấu tiếng Việt dùng `text`?
- [ ] UUID/timeuuid đúng version, ID ổn định khi retry?
- [ ] IP được validate là literal (không vô ý gọi DNS); blob được bind theo bytes/ByteBuffer đúng vùng?
- [ ] Collection/UDT/tuple/vector dùng đúng codec, đúng frozen semantics và phiên bản cluster?
- [ ] NULL, UNSET, vắng field, false/0/chuỗi rỗng được phân biệt ở API/driver?
- [ ] Primary key hợp lệ, không NULL/UNSET, và có đường truy vấn với partition/clustering đúng?
- [ ] Đã test round-trip với min/max, overflow, Unicode, DST, sai dimension, codec và timeout?
- [ ] Nếu đổi kiểu khóa hoặc schema, đã có migration bảng mới, backfill/dual-write/cutover/rollback?
- [ ] Đã quan sát tombstone, compaction, repair, consistency và lỗi mã hóa mà không làm lộ dữ liệu nhạy cảm?

## Tài liệu tham khảo

- [Apache Cassandra — CQL Data Types và cú pháp literal](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/types.html).
- [Apache Cassandra — CQL Functions: CAST, datetime, blob conversion](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/functions.html).
- [Apache Cassandra — CQL Data Manipulation: SELECT/INSERT/UPDATE/DELETE](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html).
- [Apache Cassandra — JSON Support và DEFAULT UNSET](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/json.html).
- [Apache Cassandra Java Driver 4.x — Data Types/Type Mapping](https://apache.github.io/cassandra-java-driver/4.19.0/core/).
- [Apache Cassandra Java Driver 4.x — Built-in TypeCodecs](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/type/codec/TypeCodecs.html).

**Ghi nhớ:** CQL **literal** là cú pháp biểu diễn giá trị, **`CAST`** chỉ chuyển giữa một số kiểu được hỗ trợ, còn **codec Java Driver** mã hóa và giải mã theo schema. Không có cơ chế nào thay thế **parse/validation của ứng dụng**. Với Cassandra phân tán, một giá trị sai đơn vị, sai Unicode, sai timestamp bucket hoặc bị đổi ID khi retry có thể được replicate rất nhất quán nhưng vẫn **sai nghiệp vụ**. Hãy chọn kiểu phù hợp, kiểm tra dữ liệu biên, bind đúng Java type và thiết kế partition/clustering key theo truy vấn thực tế.

