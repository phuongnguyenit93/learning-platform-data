# Khác biệt kiểu Boolean, UUID, chuỗi rỗng và NULL

## 1. Vì sao bốn khái niệm này thường gây lỗi khi chuyển DBMS?

Một ứng dụng có thể chạy đúng trên một hệ quản trị cơ sở dữ liệu (DBMS), nhưng gặp lỗi sau khi chuyển PostgreSQL sang MySQL, SQL Server, Oracle hoặc SQLite. Một phần nguyên nhân đến từ những khác biệt tưởng như nhỏ:

- Một DBMS có kiểu SQL `BOOLEAN` thực sự; DBMS khác dùng `BIT`, `TINYINT` hoặc quy ước số nguyên.
- Một DBMS có kiểu UUID 128 bit riêng; DBMS khác lưu UUID dưới dạng chuỗi hoặc 16 byte.
- Chuỗi rỗng `''` có thể là một giá trị hợp lệ, nhưng Oracle xử lý chuỗi ký tự độ dài 0 như `NULL`.
- `NULL` không phải số 0, chuỗi rỗng, `FALSE` hoặc một giá trị “chưa biết” thông thường.
- So sánh, nối chuỗi, UNIQUE constraint, CHECK constraint và JDBC mapping có thể khác giữa các hệ.

Bốn khái niệm này thường đi cùng nhau trong các bảng người dùng, đơn hàng, cấu hình, trạng thái và dữ liệu tích hợp. Ví dụ:

~~~sql
CREATE TABLE app_user (
    user_id      UUID,
    is_active    BOOLEAN,
    external_ref VARCHAR(100)
);
~~~

Đoạn DDL này phù hợp với PostgreSQL, nhưng không thể sao chép nguyên văn sang mọi DBMS. Khi thiết kế đa hệ, cần quyết định **ý nghĩa dữ liệu trước**, sau đó chọn cách biểu diễn phù hợp cho từng hệ.

Bài học thuộc **Database SQL → SQL đa hệ quản trị**. Các ví dụ đối chiếu PostgreSQL, MySQL, SQL Server, Oracle và SQLite; những khác biệt phụ thuộc phiên bản sẽ được nêu rõ.

## 2. Phân biệt Boolean, UUID, chuỗi rỗng và NULL

| Khái niệm | Ý nghĩa | Không đồng nghĩa với |
| --- | --- | --- |
| Boolean TRUE/FALSE | Giá trị logic đúng hoặc sai | Số bất kỳ, chuỗi "true"/"false" |
| UUID | Định danh 128 bit theo định dạng UUID | Số thứ tự tăng, chuỗi bất kỳ |
| Chuỗi rỗng `''` | Chuỗi có độ dài bằng 0 | SQL NULL, chuỗi chứa dấu cách |
| SQL NULL | Giá trị vắng mặt/không xác định theo ngữ nghĩa SQL | 0, FALSE, `''`, chuỗi "NULL" |

SQL còn có logic ba giá trị (*three-valued logic*). Khi một phép so sánh có liên quan đến NULL, kết quả có thể là:

- TRUE;
- FALSE;
- UNKNOWN (trong biểu thức SQL thường được biểu diễn bằng NULL).

Do đó, một cột Boolean nullable không chỉ có TRUE và FALSE. Nó còn có trạng thái SQL NULL.

Ví dụ:

| Giá trị cột enabled | Có nghĩa gì theo hợp đồng ứng dụng? |
| --- | --- |
| TRUE | Đã xác nhận bật |
| FALSE | Đã xác nhận tắt |
| NULL | Chưa được thiết lập/chưa biết/không áp dụng, tùy nghiệp vụ |

Nếu ứng dụng chỉ cần hai trạng thái, nên đặt NOT NULL và DEFAULT rõ ràng. Nếu cần trạng thái “chưa biết”, phải giữ NULL có chủ đích và xử lý riêng.

## 3. Kiểu Boolean giữa các DBMS

### 3.1. PostgreSQL: BOOLEAN là kiểu riêng

PostgreSQL có kiểu `BOOLEAN` với các giá trị TRUE, FALSE và NULL.

~~~sql
CREATE TABLE feature_flags (
    flag_key TEXT PRIMARY KEY,
    is_enabled BOOLEAN NOT NULL DEFAULT FALSE
);

INSERT INTO feature_flags (flag_key, is_enabled)
VALUES
    ('new_checkout', TRUE),
    ('legacy_export', FALSE);
~~~

Có thể viết literal:

~~~sql
SELECT
    TRUE AS enabled,
    FALSE AS disabled,
    NULL::BOOLEAN AS unknown_value;
~~~

Một số cách biểu diễn đầu vào được PostgreSQL chấp nhận có thể gồm chuỗi như `'true'`, `'yes'`, `'on'` hoặc `'1'` khi được chuyển kiểu Boolean. Tuy nhiên, để code dễ đọc và portable, nên dùng literal TRUE/FALSE và bind tham số đúng kiểu thay vì dựa vào chuỗi nhập linh hoạt.

Lọc các hàng bật:

~~~sql
SELECT flag_key
FROM feature_flags
WHERE is_enabled IS TRUE;
~~~

PostgreSQL có các predicate hữu ích:

- `IS TRUE`: chỉ khớp TRUE;
- `IS FALSE`: chỉ khớp FALSE;
- `IS UNKNOWN`: khớp NULL;
- `IS NOT TRUE`: khớp FALSE hoặc NULL;
- `IS NOT FALSE`: khớp TRUE hoặc NULL.

Các predicate này khác `= TRUE` ở chỗ biểu thức IS trả kết quả Boolean xác định, không trả UNKNOWN chỉ vì giá trị là NULL.

### 3.2. MySQL: BOOLEAN/BOOL là alias của TINYINT(1)

MySQL không lưu một kiểu Boolean độc lập giống PostgreSQL. `BOOLEAN` và `BOOL` là synonym của `TINYINT(1)`.

~~~sql
CREATE TABLE feature_flags (
    flag_key VARCHAR(100) PRIMARY KEY,
    is_enabled BOOLEAN NOT NULL DEFAULT FALSE
);
~~~

Trong thực tế, giá trị thường được biểu diễn:

- 0 = false;
- 1 = true;
- NULL = chưa biết nếu cột nullable.

Nhưng vì nền tảng là số nguyên, một cột có thể nhận các giá trị số khác 0/1 nếu không có constraint phù hợp. Nếu hợp đồng chỉ cho phép 0 hoặc 1, thêm CHECK:

~~~sql
CREATE TABLE feature_flags (
    flag_key VARCHAR(100) PRIMARY KEY,
    is_enabled TINYINT NOT NULL DEFAULT 0,
    CONSTRAINT chk_feature_enabled
        CHECK (is_enabled IN (0, 1))
);
~~~

MySQL thực thi CHECK constraint từ MySQL 8.0.16 trở lên; các bản cũ hơn có lịch sử phân tích nhưng bỏ qua CHECK. Với hệ cũ, phải xác minh version và cơ chế bảo vệ dữ liệu khác.

Literal `TRUE`/`FALSE` của MySQL được hiểu như 1/0. Do đó:

~~~sql
SELECT TRUE, FALSE, TRUE + 1;
~~~

có ngữ nghĩa số học, không phải Boolean type độc lập.

### 3.3. SQL Server: dùng BIT

SQL Server dùng `BIT` cho cờ logic:

~~~sql
CREATE TABLE dbo.feature_flags (
    flag_key VARCHAR(100) NOT NULL PRIMARY KEY,
    is_enabled BIT NOT NULL
        CONSTRAINT df_feature_enabled DEFAULT (0)
);
~~~

`BIT` có thể lưu 0, 1 hoặc NULL nếu cho phép NULL. Khi chuyển số sang BIT, SQL Server có quy tắc chuyển đổi riêng: giá trị 0 thành 0, giá trị khác 0 thành 1. Vì vậy nếu cần kiểm soát dữ liệu đầu vào nghiêm ngặt, không chỉ dựa vào kiểu BIT để bảo đảm nguồn gửi đúng 0/1.

Dùng điều kiện:

~~~sql
SELECT flag_key
FROM dbo.feature_flags
WHERE is_enabled = 1;
~~~

SQL Server không dùng literal Boolean TRUE/FALSE trong biểu thức T-SQL như PostgreSQL. Thường dùng 1/0.

### 3.4. Oracle: khác biệt theo phiên bản

Trong Oracle Database trước Oracle Database 23c, SQL không có kiểu cột BOOLEAN dùng như một kiểu SQL thông thường. PL/SQL có BOOLEAN, nhưng điều đó không có nghĩa có thể khai báo cột bảng `BOOLEAN` trong các bản cũ.

Cách biểu diễn phổ biến:

~~~sql
CREATE TABLE feature_flags (
    flag_key VARCHAR2(100) PRIMARY KEY,
    is_enabled NUMBER(1) DEFAULT 0 NOT NULL,
    CONSTRAINT chk_feature_enabled
        CHECK (is_enabled IN (0, 1))
);
~~~

Một số hệ dùng `CHAR(1)` với 'Y'/'N', nhưng phải thống nhất contract:

~~~sql
is_enabled CHAR(1) DEFAULT 'N' NOT NULL
    CHECK (is_enabled IN ('Y', 'N'))
~~~

Oracle Database 23c trở lên bổ sung kiểu SQL BOOLEAN. Nếu ứng dụng cần chạy trên nhiều thế hệ Oracle, không thể giả định mọi database đều hỗ trợ cột Boolean; hãy xác định phiên bản đích trước khi chọn DDL.

### 3.5. SQLite: kiểu động, Boolean thường là 0/1

SQLite không có storage class Boolean riêng. Giá trị TRUE/FALSE được biểu diễn như integer 1/0. Các tên TRUE và FALSE được hỗ trợ như literal tương ứng trong các phiên bản hiện đại.

~~~sql
CREATE TABLE feature_flags (
    flag_key TEXT PRIMARY KEY,
    is_enabled INTEGER NOT NULL DEFAULT 0
        CHECK (is_enabled IN (0, 1))
);
~~~

SQLite dùng hệ kiểu động (*dynamic typing*) và type affinity. CHECK giúp giới hạn miền giá trị theo hợp đồng, nhưng vẫn cần hiểu affinity và cách chuyển kiểu của SQLite.

Không nên dùng chuỗi `'true'`/`'false'` ở nơi khác rồi trông đợi SQLite tự chuyển thành cùng kiểu với PostgreSQL.

### 3.6. Bảng so sánh Boolean

| DBMS | Kiểu thường dùng | TRUE/FALSE biểu diễn | Ghi chú |
| --- | --- | --- | --- |
| PostgreSQL | BOOLEAN | TRUE/FALSE | Kiểu logic riêng; nullable có trạng thái UNKNOWN |
| MySQL | BOOLEAN/BOOL (TINYINT) | 1/0 | Alias số nguyên; thêm CHECK nếu cần giới hạn |
| SQL Server | BIT | 1/0 | Không có literal Boolean SQL TRUE/FALSE tương đương |
| Oracle trước 23c | NUMBER(1), CHAR(1) | 1/0 hoặc Y/N | SQL BOOLEAN chưa có như kiểu cột |
| Oracle 23c+ | BOOLEAN | TRUE/FALSE | Xác định đúng phiên bản triển khai |
| SQLite | INTEGER convention | 1/0 | Không có storage class Boolean riêng |

## 4. Boolean nullable và logic ba giá trị

### 4.1. Bảng chân trị AND, OR và NOT

Khi Boolean có thể NULL, logic SQL có ba trạng thái. Bảng dưới dùng U để chỉ UNKNOWN:

**AND**

| A | B | A AND B |
| --- | --- | --- |
| TRUE | TRUE | TRUE |
| TRUE | FALSE | FALSE |
| TRUE | U | U |
| FALSE | TRUE | FALSE |
| FALSE | FALSE | FALSE |
| FALSE | U | FALSE |
| U | TRUE | U |
| U | FALSE | FALSE |
| U | U | U |

**OR**

| A | B | A OR B |
| --- | --- | --- |
| TRUE | TRUE | TRUE |
| TRUE | FALSE | TRUE |
| TRUE | U | TRUE |
| FALSE | TRUE | TRUE |
| FALSE | FALSE | FALSE |
| FALSE | U | U |
| U | TRUE | TRUE |
| U | FALSE | U |
| U | U | U |

**NOT**

| A | NOT A |
| --- | --- |
| TRUE | FALSE |
| FALSE | TRUE |
| U | U |

Điểm dễ nhớ:

- FALSE AND UNKNOWN = FALSE.
- TRUE OR UNKNOWN = TRUE.
- NOT UNKNOWN = UNKNOWN.

### 4.2. WHERE chỉ giữ hàng có điều kiện TRUE

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE subscribers (
    subscriber_id BIGINT PRIMARY KEY,
    marketing_opt_in BOOLEAN
);

INSERT INTO subscribers VALUES
    (1, TRUE),
    (2, FALSE),
    (3, NULL);
~~~

Truy vấn:

~~~sql
SELECT subscriber_id
FROM subscribers
WHERE marketing_opt_in;
~~~

Chỉ hàng có TRUE được trả về. Hàng FALSE và NULL đều không thỏa điều kiện WHERE.

Nếu muốn lấy cả người chưa đồng ý và người chưa có lựa chọn, phải viết điều kiện rõ:

~~~sql
SELECT subscriber_id
FROM subscribers
WHERE marketing_opt_in IS NOT TRUE;
~~~

Điều này trả cả FALSE và NULL. Không dùng nó nếu nghiệp vụ cần chỉ lấy FALSE đã xác nhận.

### 4.3. Phân biệt FALSE với UNKNOWN

Một lỗi thiết kế là coi NULL có nghĩa FALSE mà không thống nhất với nghiệp vụ.

Ví dụ cột `is_verified`:

- FALSE: người dùng đã được kiểm tra và xác nhận chưa verified;
- NULL: hệ thống chưa kiểm tra hoặc chưa có dữ liệu.

Nếu hai trạng thái cần được phân biệt, truy vấn và API phải giữ đủ ba trạng thái.

Nếu không cần trạng thái chưa biết, nên khai báo:

~~~sql
is_verified BOOLEAN NOT NULL DEFAULT FALSE
~~~

trong PostgreSQL, hoặc kiểu biểu diễn tương đương và NOT NULL ở DBMS khác.

### 4.4. So sánh Boolean nullable

Không dùng:

~~~sql
WHERE is_enabled = NULL
~~~

vì so sánh với NULL tạo UNKNOWN, không phải TRUE.

Dùng:

~~~sql
WHERE is_enabled IS NULL
~~~

Để kiểm tra Boolean:

~~~sql
WHERE is_enabled IS TRUE
WHERE is_enabled IS FALSE
WHERE is_enabled IS UNKNOWN
~~~

Cú pháp predicate có thể khác theo DBMS. Một truy vấn portable hơn cho trường hợp null:

~~~sql
WHERE is_enabled = 1
~~~

với cột biểu diễn 0/1, nhưng vẫn phải chọn đúng kiểu theo hệ.

### 4.5. CHECK constraint và NULL

Một CHECK constraint thường chỉ từ chối hàng khi biểu thức đánh giá FALSE; UNKNOWN do NULL có thể không bị từ chối. Ví dụ:

~~~sql
CHECK (is_enabled IN (0, 1))
~~~

không tự buộc cột phải có giá trị. Nếu NULL không được phép, cần cả:

~~~sql
is_enabled NOT NULL
~~~

Điều này quan trọng ở nhiều DBMS. CHECK và NOT NULL có hai trách nhiệm khác nhau:

- CHECK giới hạn miền giá trị đã có;
- NOT NULL cấm vắng giá trị.

## 5. UUID là gì và khi nào nên dùng?

### 5.1. Định danh UUID

UUID (*Universally Unique Identifier*) là định danh có chiều dài 128 bit, thường được hiển thị theo dạng 36 ký tự:

~~~text
550e8400-e29b-41d4-a716-446655440000
~~~

Cấu trúc text canonical có nhóm hex theo dạng 8-4-4-4-12, gồm 32 chữ số hex và 4 dấu gạch nối.

UUID thường được dùng khi:

- Nhiều hệ thống tự tạo ID mà không cần hỏi một sequence trung tâm;
- Dữ liệu được tạo offline rồi đồng bộ;
- Cần ID khó đoán hơn số thứ tự tuần tự;
- Nhiều service tạo bản ghi độc lập;
- ID cần tồn tại ổn định khi hợp nhất dữ liệu từ nhiều nguồn.

UUID không tự động là bí mật hoặc token xác thực. Không dùng UUID làm cơ chế phân quyền; vẫn phải kiểm tra quyền truy cập đối tượng.

### 5.2. Các phiên bản UUID

Các phiên bản phổ biến theo đặc tả UUID:

| Version | Nguồn tạo | Đặc điểm |
| --- | --- | --- |
| v1 | Thời gian và node identifier | Có thành phần thời gian; có thể tiết lộ thông tin node/thời điểm |
| v3 | Namespace + tên, MD5 | Deterministic: cùng namespace/name tạo cùng UUID |
| v4 | Số ngẫu nhiên | Phổ biến, dễ dùng; phụ thuộc nguồn random phù hợp |
| v5 | Namespace + tên, SHA-1 | Deterministic; dùng hash SHA-1 theo chuẩn UUID |
| v6 | Dạng sắp xếp theo thời gian, dựa trên v1 | Hữu ích cho locality/index trong một số workload |
| v7 | Unix time milliseconds + phần ngẫu nhiên/sequence | Có tính sắp xếp gần theo thời gian tạo |

Không phải DBMS hoặc driver đều có hàm tạo mọi phiên bản. Cần phân biệt **chuẩn UUID** và **hàm tạo UUID mà một DBMS cụ thể cung cấp**.

UUID v4 không có thứ tự thời gian. UUID v7 có cấu trúc hỗ trợ sắp xếp gần thời điểm tạo, nhưng không đảm bảo một thứ tự toàn cục tuyệt đối giữa các máy đồng hồ lệch nhau.

### 5.3. UUID khác số tăng tự động

| Tiêu chí | BIGINT identity/sequence | UUID |
| --- | --- | --- |
| Kích thước thường gặp | 8 byte | 16 byte |
| Tạo phân tán | Cần cơ chế sequence/ID riêng | Có thể tạo độc lập |
| Tính tuần tự | Thường tăng dần | Tùy UUID version |
| Khả năng đoán | Dễ suy ra ID kế tiếp | Khó đoán hơn nếu sinh đúng ngẫu nhiên, nhưng không phải quyền truy cập |
| Index locality | Thường tốt với insert tăng dần | v4 có thể phân tán; v7 có tính thời gian |
| Đọc bằng mắt | Dễ hơn | Dài hơn |
| Tương thích hệ thống | Phổ biến | Hữu ích cho tích hợp phân tán |

UUID có kích thước lớn gấp đôi BIGINT. Điều này làm tăng kích thước index, khóa ngoại và dữ liệu truyền tải. Chọn UUID khi lợi ích định danh phân tán đáng giá; không dùng UUID chỉ vì nó “hiện đại hơn”.

## 6. Biểu diễn UUID theo từng DBMS

### 6.1. PostgreSQL: kiểu UUID riêng

PostgreSQL có kiểu `UUID`:

~~~sql
CREATE TABLE documents (
    document_id UUID PRIMARY KEY,
    title TEXT NOT NULL
);
~~~

Có thể bind literal dạng chuẩn:

~~~sql
INSERT INTO documents (document_id, title)
VALUES (
    '550e8400-e29b-41d4-a716-446655440000',
    'Example'
);
~~~

Hàm `gen_random_uuid()` tạo UUID ngẫu nhiên v4 trong PostgreSQL hiện đại:

~~~sql
INSERT INTO documents (document_id, title)
VALUES (gen_random_uuid(), 'Example');
~~~

Có thể đặt default:

~~~sql
CREATE TABLE documents (
    document_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL
);
~~~

Các phiên bản PostgreSQL cũ có thể dựa vào extension `uuid-ossp` hoặc `pgcrypto` tùy hàm và phiên bản. Kiểm tra phiên bản và extension được cài trong môi trường triển khai; không giả định mọi server cũ có cùng hàm mặc định.

### 6.2. MySQL: CHAR(36) hoặc BINARY(16)

MySQL không có kiểu UUID native tương đương PostgreSQL `UUID`. Hai lựa chọn thường gặp:

**Dạng text:**

~~~sql
CREATE TABLE documents (
    document_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin
        NOT NULL PRIMARY KEY,
    title VARCHAR(255) NOT NULL
);
~~~

Ưu điểm:

- Dễ đọc và debug;
- Dễ trao đổi với API;
- Dễ copy/paste và so sánh với hệ khác.

Nhược điểm:

- 36 ký tự chiếm nhiều dung lượng hơn 16 byte;
- Index lớn hơn;
- Cần chuẩn hóa format và collation.

**Dạng nhị phân:**

~~~sql
CREATE TABLE documents (
    document_id BINARY(16) NOT NULL PRIMARY KEY,
    title VARCHAR(255) NOT NULL
);
~~~

MySQL có các hàm:

~~~sql
UUID_TO_BIN('550e8400-e29b-41d4-a716-446655440000')
BIN_TO_UUID(document_id)
~~~

Từ MySQL 8.0, tham số swap flag của `UUID_TO_BIN(uuid, 1)` và `BIN_TO_UUID(binary, 1)` có thể đổi thứ tự một số phần UUID để cải thiện locality cho một số dạng UUID thời gian, đặc biệt cách sắp xếp UUID v1. Không bật flag một cách tùy tiện cho mọi UUID version; mọi đường ghi và đọc phải dùng **cùng quy ước**.

Ví dụ lưu/đọc nhất quán không dùng swap:

~~~sql
INSERT INTO documents (document_id, title)
VALUES (
    UUID_TO_BIN('550e8400-e29b-41d4-a716-446655440000'),
    'Example'
);

SELECT BIN_TO_UUID(document_id) AS document_id
FROM documents;
~~~

Hàm `UUID()` của MySQL tạo UUID theo cơ chế của MySQL; không mặc định rằng output là UUID v4. Nếu ứng dụng yêu cầu một version cụ thể, hãy tạo bằng thư viện/nguồn đã xác định hoặc kiểm tra khả năng của đúng DBMS version.

### 6.3. SQL Server: UNIQUEIDENTIFIER

SQL Server có kiểu `UNIQUEIDENTIFIER`:

~~~sql
CREATE TABLE dbo.documents (
    document_id UNIQUEIDENTIFIER NOT NULL
        CONSTRAINT pk_documents PRIMARY KEY
        DEFAULT NEWID(),
    title NVARCHAR(255) NOT NULL
);
~~~

`NEWID()` tạo một GUID mới. SQL Server còn có `NEWSEQUENTIALID()`:

~~~sql
CREATE TABLE dbo.documents_sequential (
    document_id UNIQUEIDENTIFIER NOT NULL
        CONSTRAINT df_documents_id DEFAULT NEWSEQUENTIALID(),
    title NVARCHAR(255) NOT NULL,
    CONSTRAINT pk_documents_sequential PRIMARY KEY (document_id)
);
~~~

`NEWSEQUENTIALID()` chỉ dùng trong DEFAULT constraint, không gọi trực tiếp như một hàm tùy ý trong SELECT/INSERT values. Nó được thiết kế tạo GUID có tính tuần tự hơn trong phạm vi cơ chế SQL Server, có thể giảm page splits so với GUID ngẫu nhiên trong một số workload. Không coi nó là một thứ tự thời gian toàn cục hoặc một cơ chế bảo mật.

Literal có thể được viết theo dạng chuẩn:

~~~sql
INSERT INTO dbo.documents (document_id, title)
VALUES (
    '550e8400-e29b-41d4-a716-446655440000',
    N'Example'
);
~~~

### 6.4. Oracle: RAW(16) hoặc CHAR(36)

Oracle truyền thống không có kiểu cột UUID native giống PostgreSQL. Một lựa chọn tiết kiệm dung lượng là `RAW(16)`:

~~~sql
CREATE TABLE documents (
    document_id RAW(16) PRIMARY KEY,
    title VARCHAR2(255) NOT NULL
);
~~~

`SYS_GUID()` trả một giá trị RAW 16 byte có tính duy nhất cao theo cơ chế Oracle:

~~~sql
INSERT INTO documents (document_id, title)
VALUES (SYS_GUID(), 'Example');
~~~

`SYS_GUID()` là global unique identifier của Oracle; không nên giả định nó luôn có đúng cấu trúc/version UUID RFC 4122/9562 mà ứng dụng đang yêu cầu.

Nếu cần lưu UUID canonical do service tạo, có thể lưu dạng CHAR(36):

~~~sql
CREATE TABLE documents_text (
    document_id CHAR(36) PRIMARY KEY,
    title VARCHAR2(255) NOT NULL
);
~~~

Hoặc ứng dụng parse UUID thành 16 byte rồi bind vào RAW(16). Cần thống nhất byte order và format chuyển đổi giữa Java, Oracle và các hệ khác.

Oracle Database 23c bổ sung nhiều hỗ trợ SQL hiện đại, nhưng khi thiết kế portability, vẫn phải dựa trên phiên bản thực tế và kiểu dữ liệu được hỗ trợ.

### 6.5. SQLite: TEXT hoặc BLOB 16 byte

SQLite không có UUID storage class riêng. Có thể lưu dạng text:

~~~sql
CREATE TABLE documents (
    document_id TEXT PRIMARY KEY,
    title TEXT NOT NULL
);
~~~

Hoặc 16 byte:

~~~sql
CREATE TABLE documents_binary (
    document_id BLOB PRIMARY KEY
        CHECK (length(document_id) = 16),
    title TEXT NOT NULL
);
~~~

Nếu lưu text, nên thống nhất canonical lowercase với dấu gạch nối hoặc một format khác và kiểm tra đầu vào. SQLite type affinity không tự đảm bảo chuỗi là UUID hợp lệ.

Nếu lưu BLOB, ứng dụng phải chuyển UUID sang đúng 16 byte và giữ quy ước byte order giống nhau khi ghi/đọc. Không trộn byte layout của Java UUID, SQL Server UNIQUEIDENTIFIER và MySQL UUID_TO_BIN mà không kiểm tra.

### 6.6. Bảng so sánh UUID

| DBMS | Kiểu lưu phổ biến | Tạo ID phía DB | Ghi chú |
| --- | --- | --- | --- |
| PostgreSQL | UUID | gen_random_uuid() trên bản hiện đại | Native 128 bit |
| MySQL | BINARY(16), CHAR(36) | UUID() | Không có native UUID type |
| SQL Server | UNIQUEIDENTIFIER | NEWID(), NEWSEQUENTIALID() trong DEFAULT | Native GUID type |
| Oracle | RAW(16), CHAR(36) | SYS_GUID() cho RAW | SYS_GUID không mặc định là RFC UUID version cụ thể |
| SQLite | BLOB(16), TEXT | Thường tạo ở ứng dụng | Không có storage class UUID |

## 7. Lưu UUID ở dạng chuỗi hay nhị phân?

### 7.1. Dạng CHAR(36)

Ví dụ canonical:

~~~text
550e8400-e29b-41d4-a716-446655440000
~~~

Ưu điểm:

- Con người có thể đọc và so sánh;
- Dễ dùng trong log, CSV và API;
- Ít lỗi chuyển đổi byte order giữa nhiều DBMS;
- Dễ kiểm tra bằng regex/validation ở tầng ứng dụng.

Nhược điểm:

- Chiếm 36 ký tự (thường nhiều hơn 36 byte nếu charset Unicode);
- Index và foreign key có thể lớn hơn;
- Collation/case có thể ảnh hưởng so sánh;
- Có thể lưu nhiều cách viết nếu không chuẩn hóa.

Nếu dùng CHAR/VARCHAR, nên chọn ASCII/binary collation hoặc chuẩn hóa chữ thường theo quy tắc thống nhất; canonical UUID thường dùng chữ hex lowercase.

### 7.2. Dạng BINARY(16)/RAW(16)

Ưu điểm:

- Dữ liệu UUID đúng 16 byte;
- Index và khóa ngoại nhỏ hơn text 36 ký tự;
- Không có khác biệt hoa/thường của chuỗi;
- Có thể tiết kiệm I/O và bộ nhớ.

Nhược điểm:

- Khó đọc trực tiếp;
- Dễ lỗi byte order khi các hệ chuyển đổi khác nhau;
- Công cụ debug/export phải chuyển về canonical text;
- Mỗi driver có thể ánh xạ kiểu nhị phân khác nhau.

### 7.3. Quy ước byte order là một phần của schema contract

Một UUID là 128 bit, nhưng các API chuyển đổi có thể chia nhóm byte và sắp xếp chúng khác nhau. SQL Server UNIQUEIDENTIFIER có cách biểu diễn nhị phân/ordering riêng trong một số thao tác so với byte sequence canonical mà ứng dụng kỳ vọng.

Vì vậy, nếu hệ thống có PostgreSQL UUID, MySQL BINARY(16), Oracle RAW(16), SQL Server UNIQUEIDENTIFIER và Java UUID cùng trao đổi một ID, hãy định nghĩa:

1. Chuỗi canonical nào được dùng trên API;
2. Cách parse thành 16 byte;
3. Byte order khi lưu;
4. Cách serialize ngược;
5. Test vector cố định để kiểm tra mọi service/DBMS.

Không chỉ kiểm tra một UUID ngẫu nhiên. Dùng một vài giá trị đã biết và xác nhận round-trip chính xác:

~~~text
UUID text
   |
   v
parse theo chuẩn đã chọn
   |
   v
16 byte canonical
   |
   v
lưu vào DBMS
   |
   v
đọc 16 byte
   |
   v
format lại UUID text
   |
   v
phải bằng UUID ban đầu
~~~

### 7.4. Index locality và UUID version

UUID v4 ngẫu nhiên thường phân bố khóa trên không gian index. Nếu dùng làm clustered primary key hoặc B-tree insert key, có thể làm page splits và phân tán page hơn ID tuần tự.

Các lựa chọn:

- BIGINT identity/sequence nếu chỉ cần ID nội bộ tuần tự;
- UUID v7 hoặc dạng time-ordered nếu cần ID phân tán và locality tốt hơn;
- UUID v4 nếu cần tạo độc lập, chấp nhận index locality;
- Một surrogate sequential key nội bộ cùng public UUID nếu workload cần cả hai đặc tính.

Đây là trade-off workload, không có lựa chọn tốt nhất cho mọi hệ. Cần benchmark với kích thước bảng, pattern insert, index và DBMS thật.

## 8. Chuỗi rỗng và NULL: khác biệt quan trọng nhất

### 8.1. PostgreSQL, MySQL, SQL Server và SQLite phân biệt chuỗi rỗng với NULL

Ví dụ:

~~~sql
INSERT INTO sample_text (value)
VALUES (''), (NULL);
~~~

Trong các hệ này, hai giá trị có ý nghĩa khác nhau:

- `''`: có giá trị chuỗi, độ dài bằng 0;
- NULL: không có giá trị/không xác định.

Có thể kiểm tra:

~~~sql
SELECT
    value,
    value IS NULL AS is_null
FROM sample_text;
~~~

Một cột VARCHAR nullable có thể chứa cả hai trạng thái.

### 8.2. Oracle coi chuỗi ký tự độ dài 0 là NULL

Trong Oracle Database, chuỗi ký tự có độ dài 0 khi gán vào kiểu character như VARCHAR2 được xử lý như NULL.

Ví dụ:

~~~sql
INSERT INTO sample_text (value)
VALUES ('');
~~~

Giá trị lưu được xem như NULL. Do đó Oracle không giữ được sự phân biệt giữa “chuỗi rỗng có chủ ý” và NULL cho các kiểu chuỗi ký tự thông thường.

Đây là khác biệt lớn khi migrate dữ liệu:

- Ở PostgreSQL, `''` và NULL có thể là hai trạng thái riêng.
- Chuyển sang Oracle, chuỗi rỗng có thể trở thành NULL.
- Khi đọc ngược, không thể biết giá trị NULL vốn là NULL hay từng là chuỗi rỗng trước migration, trừ khi nguồn có metadata khác.

Không thiết kế một contract portable yêu cầu Oracle lưu riêng hai trạng thái này trong một VARCHAR2 thông thường.

### 8.3. Bảng so sánh empty string

| DBMS | `''` so với NULL | Ghi chú |
| --- | --- | --- |
| PostgreSQL | Khác nhau | Chuỗi rỗng là giá trị text hợp lệ |
| MySQL | Khác nhau | VARCHAR có thể chứa chuỗi rỗng |
| SQL Server | Khác nhau | VARCHAR/NVARCHAR có thể chứa chuỗi rỗng |
| Oracle | Chuỗi rỗng được xem là NULL | Với kiểu character thông thường như VARCHAR2 |
| SQLite | Khác nhau | TEXT rỗng khác SQL NULL |

### 8.4. Chuỗi chứa dấu cách không phải chuỗi rỗng

Các giá trị:

~~~text
''       -- độ dài 0
' '      -- một dấu cách
'   '    -- ba dấu cách
NULL     -- không có giá trị
~~~

là những trạng thái khác nhau trong các hệ giữ empty string riêng. Oracle có xử lý empty string thành NULL, nhưng chuỗi chứa dấu cách vẫn là một chuỗi có ký tự.

Nếu ứng dụng muốn coi chuỗi chỉ gồm whitespace là trống, cần quy tắc trim rõ ràng ở tầng ứng dụng hoặc SQL. Không tự giả định mọi DBMS trim cùng một cách.

### 8.5. CHAR và VARCHAR khác nhau

`CHAR(n)` thường là kiểu độ dài cố định và có thể đệm dấu cách. `VARCHAR/VARCHAR2` là biến độ dài theo đặc điểm DBMS.

Ví dụ cột CHAR(5) có thể biểu diễn giá trị `'A'` bằng chuỗi được đệm thành độ dài 5. So sánh và hàm độ dài có thể chịu ảnh hưởng quy tắc padding/collation của DBMS.

Khi lưu UUID canonical hoặc mã cần so khớp chính xác, thường cân nhắc kiểu biến độ dài phù hợp, collation rõ ràng và validation, thay vì chọn CHAR chỉ vì UUID có độ dài hiển thị cố định.

## 9. NULL trong SQL: không phải một giá trị thông thường

### 9.1. NULL biểu diễn sự vắng mặt hoặc chưa biết

NULL có thể được dùng cho:

- Dữ liệu chưa được cung cấp;
- Dữ liệu chưa biết;
- Thuộc tính không áp dụng;
- Giá trị chưa được tính;
- Thông tin bị ẩn hoặc chưa đồng bộ.

Những ý nghĩa này không nhất thiết giống nhau. Nếu một cột dùng NULL cho quá nhiều lý do, ứng dụng khó diễn giải. Có thể cần status riêng hoặc bảng trạng thái thay vì nhồi nhiều nghĩa vào NULL.

### 9.2. So sánh bằng dấu bằng không dùng cho NULL

Sai:

~~~sql
SELECT *
FROM customers
WHERE phone = NULL;
~~~

Đúng:

~~~sql
SELECT *
FROM customers
WHERE phone IS NULL;
~~~

Và:

~~~sql
SELECT *
FROM customers
WHERE phone IS NOT NULL;
~~~

Bất kỳ phép so sánh thông thường nào như `=`, `<>`, `<`, `>` với NULL đều thường cho UNKNOWN.

### 9.3. NOT IN và NULL trap

Giả sử:

~~~sql
SELECT 1
WHERE 5 NOT IN (1, 2, NULL);
~~~

Kết quả không có hàng. Vì phép kiểm tra tương đương:

~~~sql
5 <> 1
AND 5 <> 2
AND 5 <> NULL
~~~

Hai điều kiện đầu TRUE, điều kiện cuối UNKNOWN, và TRUE AND TRUE AND UNKNOWN = UNKNOWN. WHERE không giữ UNKNOWN.

Nếu dùng NOT IN với subquery có thể chứa NULL, có thể mất kết quả ngoài ý muốn.

Một lựa chọn an toàn hơn trong nhiều tình huống là `NOT EXISTS`:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

`NOT EXISTS` kiểm tra có hàng tương quan hay không và tránh vấn đề NULL của danh sách NOT IN. Tuy nhiên, nếu quan hệ có logic NULL đặc biệt, vẫn phải xác định điều kiện tương quan đúng nghiệp vụ.

### 9.4. COALESCE

`COALESCE` trả đối số đầu tiên không NULL:

~~~sql
SELECT COALESCE(phone, 'Chưa cung cấp')
FROM customers;
~~~

Dùng để đặt giá trị fallback khi hiển thị hoặc tính toán:

~~~sql
SELECT COALESCE(discount_amount, 0)
FROM orders;
~~~

Nhưng không nên thay NULL bằng 0 ở mọi nơi. NULL có thể có ý nghĩa khác 0; chỉ dùng fallback khi hợp đồng nghiệp vụ định nghĩa hai trạng thái đó tương đương cho phép tính đang thực hiện.

### 9.5. NULLIF

`NULLIF(a, b)` trả NULL nếu hai đối số bằng nhau; nếu khác, trả a:

~~~sql
SELECT NULLIF(input_text, '');
~~~

Ở PostgreSQL/MySQL/SQL Server/SQLite, biểu thức này có thể chuẩn hóa chuỗi rỗng thành NULL. Ở Oracle, chuỗi rỗng đã được xem như NULL nên biểu thức không tạo ra một trạng thái mới.

Cẩn thận khi dùng NULLIF trong phép chia:

~~~sql
SELECT numerator / NULLIF(denominator, 0)
FROM measurements;
~~~

Nếu denominator bằng 0, biểu thức trả NULL thay vì lỗi chia cho 0 (chi tiết kiểu số/engine cần kiểm tra). Nhưng ứng dụng phải quyết định NULL kết quả có ý nghĩa gì.

### 9.6. COUNT(*) và COUNT(column)

~~~sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(phone) AS rows_with_phone
FROM customers;
~~~

- `COUNT(*)` đếm mọi hàng.
- `COUNT(phone)` bỏ qua hàng có phone NULL.

Nếu phone là chuỗi rỗng ở PostgreSQL/MySQL/SQL Server/SQLite, COUNT(phone) vẫn đếm vì chuỗi rỗng không phải NULL. Trong Oracle, chuỗi rỗng character được xem như NULL nên không được đếm.

Đây là một khác biệt có thể làm lệch báo cáo khi chuyển DBMS.

### 9.7. Aggregate bỏ qua NULL

Các aggregate như SUM, AVG, MIN, MAX thường bỏ qua NULL đầu vào; nếu không có giá trị không NULL, kết quả thường là NULL (COUNT có quy tắc riêng).

~~~sql
SELECT
    AVG(score) AS average_score,
    COUNT(score) AS known_scores,
    COUNT(*) AS all_rows
FROM exam_results;
~~~

Nếu không có score nào, AVG là NULL. Đổi thành 0 bằng COALESCE có thể hữu ích cho dashboard nhưng làm thay đổi ý nghĩa “không có dữ liệu” thành “điểm trung bình bằng 0”.

## 10. So sánh NULL-safe giữa các DBMS

Khi so hai cột có thể NULL, đôi khi cần biết chúng **khác nhau về giá trị kể cả trạng thái NULL**.

### 10.1. PostgreSQL: IS DISTINCT FROM

~~~sql
SELECT
    NULL::TEXT IS DISTINCT FROM NULL::TEXT AS same_nulls,
    NULL::TEXT IS DISTINCT FROM 'x' AS null_vs_value,
    'x' IS DISTINCT FROM 'x' AS same_values;
~~~

Kết quả lần lượt FALSE, TRUE, FALSE.

`IS DISTINCT FROM` và `IS NOT DISTINCT FROM` coi hai NULL là bằng nhau trong phép so sánh null-safe.

### 10.2. MySQL: toán tử <=>

MySQL hỗ trợ null-safe equality:

~~~sql
SELECT
    NULL <=> NULL AS same_nulls,
    NULL <=> 'x' AS null_vs_value,
    'x' <=> 'x' AS same_values;
~~~

`<=>` trả 1 nếu hai giá trị bằng nhau hoặc cả hai NULL, ngược lại trả 0. Muốn kiểm tra khác nhau có thể phủ định biểu thức.

### 10.3. SQL Server: IS [NOT] DISTINCT FROM

SQL Server 2022 trở lên hỗ trợ:

~~~sql
SELECT
    CASE
        WHEN NULL IS NOT DISTINCT FROM NULL THEN 1
        ELSE 0
    END AS same_nulls;
~~~

Trên các phiên bản cũ, dùng điều kiện tường minh hoặc kỹ thuật so sánh tương thích. Không đưa cú pháp mới vào ứng dụng vẫn phải hỗ trợ SQL Server phiên bản cũ mà không kiểm tra.

### 10.4. SQLite: IS và IS NOT

SQLite có phép so sánh `IS`/`IS NOT` với ngữ nghĩa xử lý NULL khác phép bằng thông thường:

~~~sql
SELECT
    NULL IS NULL,
    NULL IS NOT 'x',
    'x' IS 'x';
~~~

Có thể dùng để kiểm tra null-safe trong SQLite. Nhưng không sao chép cú pháp `<=>` của MySQL sang SQLite.

### 10.5. Oracle: điều kiện tường minh hoặc DECODE

Oracle có thể dùng `DECODE` với hành vi coi hai NULL là tương đương:

~~~sql
SELECT
    DECODE(a, b, 0, 1) AS is_distinct
FROM sample_values;
~~~

Hoặc viết điều kiện tường minh, dễ portable hơn:

~~~sql
WHERE
    (a <> b)
    OR (a IS NULL AND b IS NOT NULL)
    OR (a IS NOT NULL AND b IS NULL)
~~~

Cần xem kiểu dữ liệu, implicit conversion và collation của hai biểu thức. Tránh để DBMS tự chuyển kiểu ngoài ý muốn.

## 11. UNIQUE, NULL và chuỗi rỗng

### 11.1. UNIQUE không đồng nghĩa NOT NULL

Một UNIQUE constraint giới hạn trùng lặp theo quy tắc DBMS, nhưng thường không tự cấm NULL. Nếu cột cần bắt buộc có giá trị, thêm NOT NULL.

~~~sql
CREATE TABLE users (
    user_id BIGINT PRIMARY KEY,
    email VARCHAR(255) UNIQUE
);
~~~

Định nghĩa trên vẫn cho phép email NULL nếu cột nullable. Số lượng NULL được phép trong unique key khác nhau giữa các DBMS.

### 11.2. Khác biệt NULL trong UNIQUE

Các hệ thường gặp:

| DBMS | UNIQUE trên một cột nullable |
| --- | --- |
| PostgreSQL | Mặc định cho phép nhiều NULL; có tùy chọn NULLS NOT DISTINCT ở phiên bản hỗ trợ để coi NULL trùng nhau |
| MySQL | Thường cho phép nhiều NULL trong unique index |
| SQL Server | Unique index/constraint một cột thường chỉ cho phép một NULL; có thể dùng filtered unique index để cho phép nhiều NULL |
| Oracle | Unique constraint thường cho phép nhiều NULL theo quy tắc NULL của Oracle; composite key có quy tắc riêng |
| SQLite | Cho phép nhiều NULL trong UNIQUE |

Với PostgreSQL có thể khai báo:

~~~sql
CREATE TABLE contact_points (
    contact_id BIGINT PRIMARY KEY,
    external_code TEXT UNIQUE NULLS NOT DISTINCT
);
~~~

`NULLS NOT DISTINCT` được hỗ trợ từ PostgreSQL 15. Nếu cần chạy phiên bản cũ hơn, cần thiết kế constraint/index khác.

Với SQL Server, mẫu filtered index:

~~~sql
CREATE UNIQUE INDEX ux_users_email_not_null
ON dbo.users(email)
WHERE email IS NOT NULL;
~~~

Điều này bảo đảm các email không NULL là duy nhất và cho phép nhiều hàng NULL. Cần chọn đúng index/constraint theo phiên bản và nhu cầu.

### 11.3. Chuỗi rỗng và UNIQUE

Ở các DBMS phân biệt empty string và NULL, một UNIQUE index trên một cột text thường chỉ cho phép một giá trị `''` vì các chuỗi rỗng bằng nhau; nhiều NULL có thể được xử lý khác.

Ở Oracle, `''` được xem như NULL, nên quy tắc unique của NULL áp dụng thay vì một chuỗi rỗng riêng.

Đây là lý do một migration từ PostgreSQL/MySQL sang Oracle có thể thay đổi số lượng bản ghi chấp nhận được khi email/external code là chuỗi rỗng.

### 11.4. Composite unique và NULL

Ví dụ:

~~~sql
UNIQUE (tenant_id, external_code)
~~~

Quy tắc xử lý nhiều NULL trong composite key có thể phức tạp hơn unique một cột và khác nhau theo DBMS. Không chỉ đọc bảng so sánh tổng quát; hãy thử đúng cấu trúc key, số cột NULL và phiên bản DBMS đích.

## 12. DEFAULT, CHECK và dữ liệu nullable

### 12.1. DEFAULT không thay thế NOT NULL

~~~sql
is_enabled BOOLEAN DEFAULT FALSE
~~~

Nếu INSERT bỏ qua cột, DEFAULT có thể được dùng. Nhưng nếu INSERT ghi rõ NULL, cột nullable vẫn có thể nhận NULL.

Muốn luôn có TRUE/FALSE:

~~~sql
is_enabled BOOLEAN NOT NULL DEFAULT FALSE
~~~

Ở DBMS không có BOOLEAN native, dùng kiểu tương ứng và constraint.

### 12.2. CHECK không tự cấm NULL

~~~sql
CHECK (is_enabled IN (0, 1))
~~~

Biểu thức với NULL là UNKNOWN. CHECK thường chỉ từ chối FALSE, vì vậy NULL có thể vẫn qua được. Kết hợp NOT NULL nếu không muốn trạng thái đó.

### 12.3. Chuẩn hóa chuỗi rỗng

Nếu nghiệp vụ coi chuỗi rỗng và NULL tương đương, có thể chuẩn hóa đầu vào:

~~~sql
INSERT INTO contacts (phone)
VALUES (NULLIF(?, ''));
~~~

Ở PostgreSQL/MySQL/SQL Server/SQLite, chuỗi rỗng được chuyển thành NULL. Ở Oracle, giá trị chuỗi rỗng đã là NULL.

Nếu cần bỏ whitespace:

~~~sql
NULLIF(TRIM(?), '')
~~~

Cú pháp trim cơ bản phổ biến nhưng quy tắc Unicode whitespace và collation có thể khác. Nên quyết định normalization ở một tầng thống nhất nếu dữ liệu đến từ nhiều client.

### 12.4. Đừng chuẩn hóa khi hai trạng thái mang nghĩa khác nhau

Ví dụ `nickname`:

- NULL: người dùng chưa đặt nickname;
- `''`: người dùng chủ động đặt nickname thành chuỗi rỗng.

Có thể hợp đồng sản phẩm không cho phép nickname rỗng; khi đó validation nên từ chối. Nhưng nếu hệ thống có ý nghĩa phân biệt, không dùng NULLIF để tự xóa thông tin.

## 13. Nối chuỗi với NULL

Cách nối chuỗi là một trong những nơi khác biệt giữa DBMS dễ làm hỏng output.

### 13.1. PostgreSQL

Toán tử `||` truyền NULL qua kết quả:

~~~sql
SELECT 'Hello ' || NULL;
~~~

kết quả SQL NULL.

Hàm `concat` bỏ qua đối số NULL:

~~~sql
SELECT concat('Hello ', NULL, 'World');
~~~

kết quả `Hello World`.

Không mặc định toán tử và hàm có cùng quy tắc.

### 13.2. MySQL

`CONCAT` trả NULL nếu bất kỳ đối số nào là NULL:

~~~sql
SELECT CONCAT('Hello ', NULL, 'World');
~~~

kết quả NULL.

`CONCAT_WS(separator, ...)` bỏ qua các đối số NULL sau separator:

~~~sql
SELECT CONCAT_WS(' ', 'An', NULL, 'Nguyen');
~~~

kết quả `An Nguyen`. Giá trị separator NULL có quy tắc riêng và có thể làm kết quả NULL.

### 13.3. SQL Server

SQL Server dùng `+` để nối chuỗi, nhưng kết quả khi có NULL liên quan thiết lập CONCAT_NULL_YIELDS_NULL; từ SQL Server 2017 trở lên hành vi này luôn ON. Hàm `CONCAT` coi NULL như chuỗi rỗng:

~~~sql
SELECT CONCAT('Hello ', NULL, 'World');
~~~

kết quả `Hello World`.

Khi hỗ trợ phiên bản cũ, cần kiểm tra setting và dialect thay vì giả định `+` luôn có cùng semantics.

### 13.4. Oracle

Oracle dùng `||` để nối chuỗi. Với chuỗi ký tự NULL/empty theo quy tắc Oracle, toán tử nối có hành vi khác với PostgreSQL; một toán hạng NULL thường được xử lý như chuỗi rỗng trong phép nối, trừ trường hợp cả hai đều NULL.

~~~sql
SELECT 'Hello ' || NULL || 'World'
FROM dual;
~~~

Kết quả là `Hello World` trong Oracle.

Đừng lấy kết quả này để suy rằng Oracle đã phân biệt empty string và NULL; nó chính là một hệ quả của quy tắc empty string được coi là NULL.

### 13.5. SQLite

Toán tử `||` của SQLite cho kết quả NULL nếu toán hạng liên quan là NULL:

~~~sql
SELECT 'Hello ' || NULL || 'World';
~~~

Kết quả NULL.

### 13.6. Viết portable bằng COALESCE

Nếu hợp đồng muốn NULL được coi như chuỗi rỗng khi nối:

~~~sql
SELECT
    COALESCE(first_name, '')
    || ' '
    || COALESCE(last_name, '')
FROM people;
~~~

Cú pháp toán tử nối cần được điều chỉnh theo DBMS nếu không hỗ trợ `||` theo cùng cách. Với SQL Server có thể dùng `CONCAT` hoặc `+` cùng COALESCE; MySQL có thể dùng `CONCAT` cùng COALESCE.

Nhưng trước khi thay NULL bằng chuỗi rỗng, hãy xác định đây có đúng ý nghĩa nghiệp vụ không. Nếu NULL có nghĩa “chưa biết tên”, chuỗi hiển thị có thể cần placeholder khác.

## 14. Boolean, UUID và NULL trong Java/JDBC

### 14.1. Boolean primitive và wrapper

Java có:

- `boolean`: chỉ true hoặc false;
- `Boolean`: true, false hoặc null.

Nếu SQL Boolean/bit nullable, dùng `Boolean` để giữ ba trạng thái:

~~~java
Boolean enabled = resultSet.getObject("is_enabled", Boolean.class);
~~~

Driver cần hỗ trợ mapping tương ứng. Nếu dùng primitive:

~~~java
boolean enabled = resultSet.getBoolean("is_enabled");
boolean wasNull = resultSet.wasNull();
~~~

`getBoolean` trả false cho SQL NULL, vì vậy phải gọi `wasNull()` ngay sau getter nếu muốn phân biệt false thật với null.

Với SQL Server BIT, MySQL TINYINT(1), Oracle NUMBER(1), SQLite INTEGER, driver có thể map khác nhau. Một cách rõ ràng là đọc số/kiểu nguồn và chuyển đổi theo contract.

### 14.2. UUID trong Java

Java có `java.util.UUID`:

~~~java
UUID id = UUID.randomUUID();
String canonical = id.toString();
UUID parsed = UUID.fromString(canonical);
~~~

`UUID.randomUUID()` tạo UUID v4. Nếu ứng dụng cần UUID v7 hoặc một version khác, dùng API/thư viện hỗ trợ đúng version và kiểm tra đặc tả; không giả định randomUUID tạo v7.

### 14.3. JDBC mapping UUID

PostgreSQL JDBC driver thường hỗ trợ `setObject` với `java.util.UUID` cho cột UUID:

~~~java
UUID id = UUID.randomUUID();

try (PreparedStatement statement =
         connection.prepareStatement(
             "INSERT INTO documents(document_id, title) VALUES (?, ?)"
         )) {
    statement.setObject(1, id);
    statement.setString(2, "Example");
    statement.executeUpdate();
}
~~~

Đọc:

~~~java
UUID id = resultSet.getObject("document_id", UUID.class);
~~~

Đây là khả năng mapping cần xác nhận theo driver/version. Với DBMS lưu UUID dạng CHAR(36), BINARY(16), RAW(16) hoặc UNIQUEIDENTIFIER, có thể cần dùng `setString`, `setBytes` hoặc mapping đặc thù.

### 14.4. setString với chuỗi rỗng không portable hoàn toàn

~~~java
statement.setString(1, "");
~~~

Trên PostgreSQL/MySQL/SQL Server/SQLite, đây có thể là chuỗi rỗng thực sự. Với Oracle VARCHAR2, chuỗi rỗng được xử lý như NULL.

Nếu ứng dụng cần portability, quyết định một trong các hợp đồng:

- Chuỗi rỗng được phép và được phân biệt với NULL: Oracle VARCHAR2 không đáp ứng trực tiếp;
- Chuỗi rỗng chuẩn hóa thành NULL: chuẩn hóa trước khi bind hoặc chấp nhận semantics Oracle;
- Trạng thái cần phân biệt: dùng cột trạng thái/flag riêng hoặc biểu diễn khác, không dựa vào empty VARCHAR2.

### 14.5. setNull và SQL type

Khi bind SQL NULL, có thể khai báo type:

~~~java
statement.setNull(1, Types.VARCHAR);
statement.setNull(2, Types.BOOLEAN);
statement.setNull(3, Types.BINARY);
~~~

Không phải DBMS hỗ trợ mọi kiểu như nhau; `Types.BOOLEAN` có thể không phù hợp với driver/hệ không có kiểu SQL Boolean. Với trường hợp đa hệ, dùng kiểu SQL thực tế và mapping theo dialect, hoặc `setObject(index, null, sqlType)` với SQL type đúng.

### 14.6. NULL trong Optional

Không nên dùng `Optional<Boolean>` như một cách tự động cho mọi field nullable trong DTO, nhưng nó có thể biểu diễn rõ “có/không có giá trị” ở API nội bộ. Với object mapping, `Boolean` nullable thường đơn giản hơn.

Với String, Java `null` và `""` vẫn khác nhau. Đừng tự động gọi trim rồi chuyển chuỗi rỗng thành null nếu contract không yêu cầu.

## 15. Thiết kế schema đa hệ quản trị

### 15.1. Xác định canonical contract

Trước khi viết DDL cho nhiều DBMS, hãy định nghĩa:

**Cờ logic**

- Chỉ có hai trạng thái hay có thêm unknown?
- Nếu unknown có nghĩa gì?
- Giá trị mặc định là gì?
- NULL có được phép không?

**Định danh**

- UUID version nào?
- Tạo ở database hay service?
- Lưu text hay 16 byte?
- API trả canonical lowercase có dấu gạch nối hay format khác?
- Có yêu cầu thứ tự theo thời gian không?

**Chuỗi**

- Empty string có hợp lệ không?
- Empty string có đồng nghĩa “chưa cung cấp” không?
- Có trim whitespace không?
- Case sensitivity/collation ra sao?

**NULL**

- NULL biểu diễn chưa biết, không áp dụng hay chưa nhập?
- Unique key có cho phép nhiều NULL không?
- API trả null, bỏ key hay fallback?
- Các phép toán aggregate và nối chuỗi xử lý NULL thế nào?

### 15.2. Một schema biểu diễn portable

Nếu muốn chạy qua nhiều DBMS và cần portability cao, có thể chọn biểu diễn:

- Boolean: SMALLINT/TINYINT/NUMBER(1)/BIT với CHECK 0/1 và NOT NULL nếu chỉ hai trạng thái;
- UUID: canonical CHAR(36) ASCII hoặc BINARY(16)/RAW(16) với quy ước byte order;
- Optional text: VARCHAR có quy tắc normalization rõ; không dựa vào empty string để phân biệt NULL trên Oracle;
- NULL: dùng semantics SQL chuẩn và viết truy vấn kiểm tra IS NULL/IS NOT NULL.

Ví dụ logic trung lập:

~~~sql
-- Pseudocode DDL: thay kiểu/identity theo DBMS.
CREATE TABLE integration_record (
    record_id       /* UUID representation */ NOT NULL,
    is_active       /* 0/1 representation */ NOT NULL,
    external_code   VARCHAR(100) NULL,
    CONSTRAINT chk_is_active CHECK (is_active IN (0, 1))
);
~~~

Đây là **pseudocode**, không phải một câu DDL có thể chạy nguyên văn ở mọi hệ. Chọn kiểu cột cụ thể theo bảng so sánh ở trên.

### 15.3. Đừng hy sinh ngữ nghĩa để đạt cú pháp chung

Một schema có thể chạy được trên mọi DBMS nhưng vẫn làm mất dữ liệu nếu:

- Dùng NUMBER/TINYINT cho Boolean nhưng không ràng buộc 0/1;
- Lưu UUID text nhưng không chuẩn hóa case/hyphen;
- Chuyển empty string thành NULL mà nghiệp vụ phân biệt hai trạng thái;
- Dùng NULL cho cả “unknown” và “not applicable”;
- Dựa vào UNIQUE để cấm NULL trong mọi DBMS;
- Dựa vào concat để tạo chuỗi mà không chuẩn hóa NULL.

Portability tốt là **cùng một hợp đồng dữ liệu và hành vi**, không chỉ cùng một câu SQL.

## 16. Migration dữ liệu giữa các DBMS

### 16.1. Kiểm kê dữ liệu trước khi chuyển

Trước migration, đo số lượng trạng thái:

~~~sql
SELECT
    COUNT(*) AS total_rows,
    SUM(CASE WHEN external_code IS NULL THEN 1 ELSE 0 END) AS null_count,
    SUM(CASE WHEN external_code = '' THEN 1 ELSE 0 END) AS empty_count
FROM integration_record;
~~~

Câu trên phù hợp với DBMS phân biệt empty string và NULL. Khi chạy Oracle, điều kiện `external_code = ''` không giúp phân biệt empty string riêng vì empty string đã được coi như NULL; thống kê nguồn phải được lấy **trước khi dữ liệu mất phân biệt**.

Với Boolean 0/1:

~~~sql
SELECT is_active, COUNT(*)
FROM integration_record
GROUP BY is_active;
~~~

Kiểm tra các giá trị ngoài miền nếu kiểu nguồn cho phép, ví dụ MySQL TINYINT:

~~~sql
SELECT COUNT(*)
FROM integration_record
WHERE is_active NOT IN (0, 1)
   OR is_active IS NULL;
~~~

Nếu NULL được cho phép, tách thống kê NULL riêng thay vì coi nó là giá trị sai.

### 16.2. Chuẩn hóa UUID

Nếu nguồn có UUID text:

- Trim whitespace theo quy tắc đã chọn;
- Chuẩn hóa lowercase/canonical format;
- Kiểm tra đúng 36 ký tự và dấu gạch nối;
- Parse thành UUID ở ứng dụng hoặc DBMS;
- Phát hiện duplicate trước khi tạo primary key;
- Kiểm tra round-trip sau khi chuyển sang binary/native type.

Không chỉ kiểm tra độ dài 36; chuỗi bất kỳ 36 ký tự không phải UUID hợp lệ.

### 16.3. Không thể khôi phục empty string đã biến thành NULL

Khi dữ liệu đã được ghi vào Oracle VARCHAR2, giá trị `''` được xem như NULL. Sau đó export sang CSV hoặc chuyển sang PostgreSQL, không thể biết một NULL cụ thể vốn là NULL hay empty string ở nguồn trước đó nếu không có audit/metadata bổ sung.

Nếu phân biệt này quan trọng, phải giữ thông tin từ nguồn trước khi ghi vào Oracle, ví dụ:

~~~text
external_code_value = NULL
external_code_was_empty = TRUE/FALSE
~~~

Hoặc dùng trạng thái riêng phù hợp với schema và hợp đồng tích hợp.

### 16.4. Migration Boolean

Ví dụ nguồn MySQL TINYINT có thể chứa 0, 1, 2, -1 do không có CHECK. Trước khi chuyển sang PostgreSQL BOOLEAN, phải quyết định cách ánh xạ:

| Giá trị nguồn | Cách xử lý có thể chọn |
| ---: | --- |
| 0 | FALSE |
| 1 | TRUE |
| NULL | NULL nếu hợp đồng cho phép |
| 2 hoặc -1 | Từ chối, sửa dữ liệu hoặc ánh xạ theo quy tắc nghiệp vụ |

Không tự động chuyển mọi giá trị khác 0 thành TRUE trừ khi đó là hợp đồng nguồn đã được xác nhận.

### 16.5. Migration UUID version

Nếu ứng dụng chỉ yêu cầu UUID bất kỳ, v4 có thể đáp ứng. Nếu downstream dựa vào thứ tự gần theo thời gian của v7, việc đổi thành UUID v4 trong migration sẽ làm mất thuộc tính đó. Version là một phần của contract khi có hệ thống phụ thuộc vào nó.

## 17. JSON và API: NULL, missing, empty string, false

JSON có cách biểu diễn riêng:

~~~json
{
  "enabled": false,
  "externalCode": "",
  "phone": null,
  "tags": []
}
~~~

Các trạng thái này khác nhau:

- `enabled: false`: Boolean false;
- `externalCode: ""`: chuỗi rỗng;
- `phone: null`: key tồn tại, giá trị JSON null;
- `tags: []`: danh sách có 0 phần tử.

Document:

~~~json
{}
~~~

không có key nào trong bốn key trên. Key vắng mặt không giống key có null.

### 17.1. SQL NULL khi serialize JSON

Một số hàm JSON có chính sách khác nhau về NULL:

- PostgreSQL `jsonb_build_object` thường giữ key và JSON null nếu giá trị SQL NULL;
- SQL Server `FOR JSON PATH` mặc định thường bỏ thuộc tính có SQL NULL, có thể dùng `INCLUDE_NULL_VALUES` để giữ;
- Oracle SQL/JSON có tùy chọn như `NULL ON NULL` hoặc `ABSENT ON NULL` tùy hàm/phiên bản;
- MySQL và SQLite có quy tắc riêng của JSON builder.

Vì vậy, cùng một hàng SQL có thể tạo ra JSON khác nhau giữa các DBMS nếu không cấu hình null policy rõ ràng.

### 17.2. Boolean JSON không phải số JSON

JSON có literal `true`/`false` riêng:

~~~json
{"enabled": true}
~~~

Khác:

~~~json
{"enabled": 1}
~~~

Dù MySQL/SQL Server/SQLite có thể lưu Boolean dưới dạng số, tầng serialize nên tạo JSON Boolean nếu API định nghĩa kiểu Boolean. Không để client phải đoán 1 là true hay một mã trạng thái.

### 17.3. UUID trong JSON thường là string

UUID không phải loại scalar riêng trong JSON chuẩn. Thường serialize thành chuỗi:

~~~json
{"id": "550e8400-e29b-41d4-a716-446655440000"}
~~~

Duy trì canonical format và kiểm tra UUID khi parse request. Không dùng một số JSON 128 bit vì JSON number và các runtime như JavaScript không biểu diễn chính xác mọi integer 128 bit.

## 18. Truy vấn và kiểm thử đa hệ

### 18.1. Ma trận test tối thiểu

| Ca kiểm thử | Boolean | UUID | Text | NULL |
| --- | --- | --- | --- | --- |
| Giá trị bình thường | TRUE/1 | UUID hợp lệ | "abc" | Không NULL |
| Giá trị âm/false | FALSE/0 | UUID khác | "x" | — |
| Giá trị rỗng | — | Không áp dụng | `''` | — |
| Chỉ whitespace | — | — | `' '` | — |
| NULL | NULL nếu nullable | NULL nếu nullable | NULL | IS NULL |
| Duplicate | Cùng trạng thái | Cùng UUID | Cùng chuỗi | Unique semantics |
| Invalid | 2/-1 với integer mapping | UUID sai format | encoding/length | — |

Chạy ma trận này trên đúng phiên bản DBMS và driver sẽ triển khai, không chỉ trên một database giả lập.

### 18.2. Kiểm tra Boolean ba trạng thái

Tạo test data gồm TRUE, FALSE, NULL. Xác minh:

- WHERE column chỉ giữ TRUE;
- IS FALSE chỉ giữ FALSE;
- IS NULL chỉ giữ unknown;
- NOT column không giữ NULL trong WHERE;
- CHECK và NOT NULL hoạt động đúng.

### 18.3. Kiểm tra UUID round-trip

1. Tạo một UUID cố định trong ứng dụng.
2. Ghi vào DBMS.
3. Đọc lại bằng JDBC.
4. Serialize về canonical text.
5. So sánh bằng UUID equality.
6. Chạy qua mọi database/driver trong ma trận.

Với binary storage, kiểm tra byte sequence, không chỉ kiểm tra chuỗi hiển thị cuối.

### 18.4. Kiểm tra empty string

Chèn ba đầu vào:

~~~text
NULL
''
' '
~~~

Sau INSERT, đọc lại và xác minh từng DBMS. Oracle sẽ không giữ riêng empty string trong VARCHAR2; test cần thể hiện giới hạn đó để ứng dụng không mong đợi một trạng thái không thể lưu.

### 18.5. Kiểm tra unique nullable

Thử insert hai hàng có cùng email, một email NULL và một email empty string. Ghi lại hành vi DBMS đích. Đừng dựa vào kết quả từ PostgreSQL để kết luận SQL Server hoặc Oracle sẽ chấp nhận cùng dữ liệu.

## 19. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Khai báo BOOLEAN ở mọi DBMS | DDL không chạy trên một số hệ | Chọn kiểu theo DBMS/version |
| Dùng TINYINT như Boolean mà không CHECK | Dữ liệu có thể là 2, -1... | CHECK 0/1 và validation |
| Coi SQL Server BIT là kiểu Boolean có TRUE literal | Sai cú pháp T-SQL | Dùng 1/0 |
| Coi Oracle mọi phiên bản có SQL BOOLEAN | DDL không tương thích | Xác định phiên bản; dùng NUMBER(1)/CHAR(1) nếu cần |
| Lưu Boolean nullable nhưng map sang primitive | NULL biến thành false | Dùng Boolean wrapper hoặc wasNull |
| Nghĩ SQLite có storage class BOOLEAN | Hiểu sai kiểu lưu | Dùng INTEGER convention + CHECK |
| Coi UUID như chuỗi bất kỳ | ID sai format, duplicate | Parse/validate UUID |
| Giả định UUID() MySQL tạo v4 | Sai version contract | Chỉ định nguồn/version rõ |
| Dùng SYS_GUID như UUID RFC mà không kiểm tra | Có thể sai format/version | Xem semantics Oracle; tự tạo RFC UUID nếu cần |
| Lưu UUID binary mà không thống nhất byte order | Các hệ đọc ID khác nhau | Định nghĩa canonical byte contract và test vector |
| Dùng UUID v4 cho clustered index rồi bỏ qua locality | Index phân tán/page split | Benchmark, cân nhắc v7/sequential key |
| Dùng UUID làm token phân quyền | Lộ ID dẫn tới truy cập trái phép | Luôn kiểm tra authorization |
| Nghĩ `''` luôn khác NULL | Mất dữ liệu khi chuyển sang Oracle | Xác định empty-string contract |
| Nghĩ chuỗi whitespace là empty string | Chuẩn hóa sai | Trim theo quy tắc rõ |
| Dùng `= NULL` | Không khớp hàng | Dùng IS NULL |
| Dùng NOT IN với subquery có NULL | Kết quả biến mất do UNKNOWN | NOT EXISTS hoặc lọc NULL |
| Nghĩ CHECK cấm NULL | Dữ liệu NULL lọt qua | Thêm NOT NULL |
| Nghĩ DEFAULT thay cho NOT NULL | INSERT ghi NULL vẫn có thể NULL | Kết hợp DEFAULT và NOT NULL |
| Dùng UNIQUE để buộc chỉ một trạng thái rỗng trên mọi DBMS | Hành vi NULL khác nhau | Kiểm tra unique semantics và index cụ thể |
| Nối chuỗi mà không xử lý NULL | Output khác nhau giữa DBMS | COALESCE/CONCAT theo contract |
| COUNT(column) coi empty string như NULL ở mọi hệ | Báo cáo lệch trên Oracle | Kiểm tra empty string semantics |
| Serialize SQL NULL sang JSON rồi mặc định cùng chính sách | API khác field null/missing | Cấu hình JSON null policy |
| Ép UUID thành JSON number | Mất độ chính xác | Serialize UUID thành string |
| Dựa vào implicit cast | Lỗi khi đổi driver/version | Bind và cast rõ ràng |

## 20. Bài tập thực hành có đáp án

### Bài 1 — Boolean có ba trạng thái

Một cột PostgreSQL `is_active BOOLEAN` cho phép NULL. Có những giá trị logic SQL nào?

**Đáp án:** TRUE, FALSE và UNKNOWN (SQL NULL). Nếu nghiệp vụ chỉ cần hai trạng thái, thêm NOT NULL và DEFAULT.

### Bài 2 — Kiểu Boolean của MySQL

MySQL `BOOLEAN` lưu bằng kiểu nào?

**Đáp án:** `TINYINT(1)` alias. TRUE/FALSE được biểu diễn 1/0; nếu cần chỉ cho phép 0/1, thêm CHECK trên phiên bản MySQL thực thi CHECK.

### Bài 3 — SQL Server

Kiểu nào thường dùng cho cờ Boolean trong SQL Server?

**Đáp án:** `BIT`, có thể lưu 0, 1 và NULL nếu cột nullable.

### Bài 4 — Oracle cũ

Vì sao DDL có cột `BOOLEAN` có thể không chạy trên Oracle cũ?

**Đáp án:** SQL Boolean column chỉ có ở các phiên bản Oracle mới như 23c; trước đó thường dùng NUMBER(1) hoặc CHAR(1) kèm CHECK.

### Bài 5 — SQLite

Boolean được lưu như thế nào trong SQLite thông thường?

**Đáp án:** dùng INTEGER convention 1/0; SQLite không có storage class Boolean riêng. CHECK giúp giới hạn miền.

### Bài 6 — WHERE Boolean NULL

Trong PostgreSQL, WHERE `is_active` có giữ hàng NULL không?

**Đáp án:** không. Predicate UNKNOWN không được WHERE giữ; chỉ TRUE được giữ.

### Bài 7 — Lấy FALSE và NULL

Viết điều kiện PostgreSQL lấy cả FALSE và NULL.

**Đáp án:**

~~~sql
WHERE is_active IS NOT TRUE
~~~

Nếu chỉ cần FALSE đã xác nhận, dùng `IS FALSE`.

### Bài 8 — CHECK và NULL

`CHECK (is_active IN (0,1))` có tự cấm NULL không?

**Đáp án:** không. UNKNOWN từ NULL thường không bị CHECK từ chối. Thêm NOT NULL nếu cần.

### Bài 9 — UUID độ dài

UUID canonical text có bao nhiêu ký tự, gồm dấu gạch nối?

**Đáp án:** 36 ký tự: 32 hex và 4 dấu gạch nối, theo nhóm 8-4-4-4-12.

### Bài 10 — UUID v4

`UUID.randomUUID()` trong Java tạo version nào?

**Đáp án:** UUID v4, dựa trên giá trị ngẫu nhiên theo implementation Java.

### Bài 11 — UUID v7

UUID v7 có lợi điểm gì so với UUID v4 trong một số workload index?

**Đáp án:** cấu trúc có thành phần thời gian giúp ID có xu hướng sắp xếp gần theo thời điểm tạo, có thể cải thiện locality. Nó không đảm bảo thứ tự toàn cục tuyệt đối.

### Bài 12 — PostgreSQL UUID

Kiểu cột nào dùng để lưu UUID native trong PostgreSQL?

**Đáp án:** `UUID`. Có thể dùng `gen_random_uuid()` trên phiên bản PostgreSQL hiện đại để tạo UUID v4.

### Bài 13 — MySQL UUID storage

MySQL có thể lưu UUID theo hai dạng phổ biến nào?

**Đáp án:** `CHAR(36)` và `BINARY(16)`. Dạng binary nhỏ hơn nhưng cần thống nhất byte order/convert function.

### Bài 14 — SQL Server UUID

Kiểu SQL Server nào lưu GUID?

**Đáp án:** `UNIQUEIDENTIFIER`. `NEWID()` tạo GUID; `NEWSEQUENTIALID()` chỉ dùng trong DEFAULT constraint.

### Bài 15 — Oracle SYS_GUID

Có thể giả định `SYS_GUID()` luôn trả UUID RFC v4 không?

**Đáp án:** không. Đây là RAW 16 byte global unique identifier theo cơ chế Oracle; không mặc định là UUID version cụ thể.

### Bài 16 — Empty string ở Oracle

Trong Oracle VARCHAR2, `''` được xử lý thế nào?

**Đáp án:** như NULL. Không thể giữ hai trạng thái riêng empty string và NULL trong cột VARCHAR2 thông thường.

### Bài 17 — Empty string ở PostgreSQL

PostgreSQL có phân biệt `''` và NULL không?

**Đáp án:** có. `''` là chuỗi rỗng có độ dài 0; NULL là giá trị vắng mặt/unknown.

### Bài 18 — Chuỗi whitespace

`' '` có giống `''` không?

**Đáp án:** không. Chuỗi đầu có một dấu cách. Nếu nghiệp vụ coi whitespace-only là trống, phải trim/normalize theo quy tắc rõ.

### Bài 19 — So sánh NULL

Vì sao `WHERE phone = NULL` không đúng?

**Đáp án:** phép so sánh với NULL trả UNKNOWN. Dùng `WHERE phone IS NULL`.

### Bài 20 — NOT IN và NULL

Vì sao `5 NOT IN (1,2,NULL)` không trả TRUE?

**Đáp án:** điều kiện tương đương AND của các phép khác nhau; phép so sánh 5 <> NULL là UNKNOWN, khiến toàn biểu thức UNKNOWN. Dùng NOT EXISTS hoặc loại NULL trong subquery khi đúng nghiệp vụ.

### Bài 21 — COUNT empty string

Một cột có một hàng `''` và một hàng NULL. COUNT(column) khác nhau thế nào giữa PostgreSQL và Oracle?

**Đáp án:** PostgreSQL đếm chuỗi rỗng, bỏ NULL nên kết quả 1. Oracle coi chuỗi rỗng là NULL, nên cả hai bị bỏ qua và kết quả 0.

### Bài 22 — DEFAULT và NULL

Cột có DEFAULT FALSE nhưng INSERT ghi rõ NULL. DEFAULT có tự thay NULL bằng FALSE không?

**Đáp án:** không. DEFAULT thường áp dụng khi bỏ cột hoặc dùng DEFAULT; ghi NULL rõ ràng vẫn là NULL nếu cột nullable. Thêm NOT NULL nếu không cho phép.

### Bài 23 — Nối chuỗi MySQL

`CONCAT('A', NULL, 'B')` trả gì trong MySQL?

**Đáp án:** NULL. `CONCAT_WS` có quy tắc bỏ qua đối số NULL sau separator; cần chọn hàm đúng contract.

### Bài 24 — UNIQUE nullable

Có thể giả định mọi DBMS cho phép nhiều NULL trong UNIQUE không?

**Đáp án:** không. PostgreSQL/MySQL/SQLite thường cho phép nhiều NULL trong unique index; SQL Server unique index một cột thường chỉ cho một NULL; Oracle có quy tắc riêng. Cần test đúng DBMS/version và composite key.

### Bài 25 — Java Boolean

Một cột SQL BIT/BOOLEAN nullable cần mapping ba trạng thái. Nên dùng Java boolean hay Boolean?

**Đáp án:** `Boolean` wrapper có thể giữ true, false và null. Nếu dùng primitive `getBoolean`, gọi `wasNull()` ngay sau getter.

### Bài 26 — Migration empty string

Đã chuyển VARCHAR2 Oracle sang PostgreSQL. Có thể biết một NULL trước đây vốn là empty string hay NULL không?

**Đáp án:** không nếu nguồn không lưu metadata khác. Oracle đã gộp empty string với NULL. Cần giữ trạng thái trước migration nếu phân biệt này quan trọng.

### Bài 27 — UUID JSON

UUID nên serialize thành JSON number hay string?

**Đáp án:** thường là string canonical. JSON number/runtime như JavaScript không thể biểu diễn chính xác mọi integer 128 bit.

### Bài 28 — Chuẩn hóa Boolean nguồn

Một cột MySQL TINYINT có giá trị 0, 1, 2, NULL. Khi migrate sang PostgreSQL BOOLEAN, có nên coi mọi số khác 0 là TRUE?

**Đáp án:** chỉ khi hợp đồng nghiệp vụ xác định như vậy. Nếu không, kiểm kê và xử lý 2/giá trị ngoài miền riêng; không tự làm mất thông tin.

## 21. Checklist thiết kế và migration

Trước khi phát hành schema đa hệ quản trị, hãy xác nhận:

1. **Boolean semantics:** có hai trạng thái hay ba trạng thái?
2. **Nullability:** NULL có ý nghĩa nghiệp vụ cụ thể không?
3. **Defaults:** DEFAULT có được kết hợp NOT NULL đúng cách?
4. **Boolean representation:** BOOLEAN, BIT, TINYINT, NUMBER(1) hay INTEGER?
5. **Constraint:** miền 0/1 hoặc Y/N có được bảo vệ?
6. **Oracle version:** SQL BOOLEAN có thực sự được hỗ trợ ở môi trường đích?
7. **UUID version:** v4, v7 hay version deterministic khác?
8. **UUID generation:** DBMS hay service tạo ID?
9. **UUID storage:** native, CHAR(36), BINARY(16) hay RAW(16)?
10. **Byte order:** mọi ứng dụng/DBMS có dùng cùng quy ước?
11. **UUID format:** lowercase, hyphen, canonical string được thống nhất?
12. **Empty string:** có phân biệt với NULL không?
13. **Whitespace:** có trim và normalize không?
14. **NULL comparisons:** dùng IS NULL/IS NOT NULL, tránh = NULL?
15. **Three-valued logic:** điều kiện WHERE/NOT/AND/OR có xử lý UNKNOWN?
16. **NOT IN:** subquery có thể chứa NULL không?
17. **UNIQUE:** quy tắc NULL và empty string có được test trên DBMS đích?
18. **CHECK:** có hiểu CHECK không tự cấm NULL?
19. **Concatenation:** NULL có làm kết quả nối thành NULL không?
20. **Aggregates:** COUNT(column) có bỏ empty string/NULL theo đúng contract?
21. **JDBC:** Boolean/UUID/NULL được map đúng với driver thực tế?
22. **JSON/API:** false, null, missing, empty string và empty array có phân biệt?
23. **Migration:** thống kê dữ liệu và xác định thông tin nào có thể mất trước khi chạy?
24. **Integration tests:** có test matrix trên từng DBMS/version?
25. **Rollback:** migration có kế hoạch backup, validate và phục hồi?

## 22. Tổng kết

Khả năng portable của SQL không chỉ nằm ở việc thay tên kiểu dữ liệu. **Boolean, UUID, chuỗi rỗng và NULL đều có ngữ nghĩa ảnh hưởng trực tiếp tới dữ liệu và logic ứng dụng**:

- PostgreSQL có BOOLEAN và UUID native; MySQL thường dùng TINYINT cho Boolean và CHAR(36)/BINARY(16) cho UUID; SQL Server có BIT và UNIQUEIDENTIFIER; Oracle cũ dùng NUMBER(1)/CHAR(1) và RAW(16)/CHAR(36); SQLite thường dùng INTEGER và TEXT/BLOB.
- Boolean nullable có ba trạng thái logic. WHERE chỉ giữ điều kiện TRUE; FALSE và UNKNOWN đều bị loại.
- UUID có nhiều version. Chọn version, nơi tạo, dạng lưu và byte order như một phần của schema contract.
- PostgreSQL, MySQL, SQL Server và SQLite phân biệt chuỗi rỗng với NULL; Oracle coi chuỗi ký tự độ dài 0 như NULL trong các kiểu character thông thường.
- NULL không so sánh bằng dấu bằng; dùng IS NULL, IS NOT NULL hoặc phép so sánh null-safe phù hợp DBMS.
- UNIQUE, CHECK, DEFAULT, COUNT và nối chuỗi có những quy tắc khác nhau khi gặp NULL/empty string.
- Java Boolean wrapper có thể giữ null; UUID thường được biểu diễn bằng java.util.UUID; JDBC driver cần được kiểm tra theo kiểu cột thực tế.
- JSON phân biệt false, null, chuỗi rỗng và key vắng mặt; không ép tất cả về một trạng thái.

**Nguyên tắc cốt lõi:** trước khi chuyển DBMS, hãy chuẩn hóa hợp đồng dữ liệu và kiểm tra hành vi thật trên đúng phiên bản đích. Một DDL chạy được chưa đủ; truy vấn, constraint, JDBC mapping, migration và JSON/API cũng phải giữ cùng ý nghĩa.
