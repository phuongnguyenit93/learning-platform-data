# Giao dịch qua nhiều câu lệnh trên cùng kết nối trong ứng dụng

Một nghiệp vụ thường không thể hoàn thành bằng một câu SQL. Ví dụ chuyển tiền cần trừ số dư tài khoản nguồn, cộng số dư tài khoản đích và ghi nhận giao dịch. Nếu mỗi câu lệnh tự commit riêng, lỗi ở bước thứ ba có thể để lại trạng thái chỉ hoàn thành một phần.

Để giữ dữ liệu nhất quán, ứng dụng cần thực hiện các câu SQL trong **cùng một transaction trên cùng một kết nối database**:

~~~sql
BEGIN;

UPDATE tai_khoan
SET so_du = so_du - 100000
WHERE id = 1;

UPDATE tai_khoan
SET so_du = so_du + 100000
WHERE id = 2;

INSERT INTO lich_su_chuyen_tien (...);

COMMIT;
~~~

Nếu bất kỳ bước bắt buộc nào thất bại, ứng dụng gửi `ROLLBACK` trên **chính kết nối đó**. Khi transaction được rollback thành công, những thay đổi thuộc transaction bị hủy cùng nhau.

Bài học thuộc **Database SQL → SQL trong ứng dụng**. Trọng tâm là hiểu ranh giới transaction khi ứng dụng gửi nhiều câu lệnh, cách giữ đúng connection khi dùng connection pool, quản lý autocommit, xử lý lỗi, isolation, retry, savepoint và các ví dụ trong JDBC, Python và Node.js.

**Nguyên tắc cốt lõi:** transaction gắn với session/connection mà DBMS đang quản lý. Gửi `BEGIN` trên kết nối A, rồi gửi UPDATE hoặc COMMIT trên kết nối B không tạo thành một transaction chung.

## 1. Transaction là một đơn vị công việc

Transaction là nhóm thao tác database được quản lý như một đơn vị. Theo nguyên tắc ACID:

- **Atomicity:** hoặc các thay đổi thuộc transaction được xác nhận cùng nhau, hoặc bị hủy theo cơ chế rollback.
- **Consistency:** transaction phải giữ các ràng buộc và bất biến dữ liệu mà ứng dụng/database thiết kế.
- **Isolation:** các transaction đồng thời tương tác theo isolation level được chọn.
- **Durability:** sau khi commit thành công theo cam kết của DBMS, thay đổi được lưu bền vững theo cấu hình hệ thống.

Ví dụ chuyển tiền 100.000:

1. Trừ 100.000 khỏi tài khoản An.
2. Cộng 100.000 vào tài khoản Bình.
3. Ghi một bản ghi lịch sử chuyển tiền.
4. Commit.

Nếu bước cộng tiền thất bại, không được giữ riêng bước trừ tiền. Nếu bản ghi lịch sử là thành phần bắt buộc, lỗi khi ghi lịch sử cũng phải làm transaction thất bại.

~~~mermaid
flowchart TD
    A["Ứng dụng lấy một connection"] --> B["BEGIN / tắt autocommit"]
    B --> C["Statement 1: trừ tiền"]
    C --> D{"Bước 1 thành công?"}
    D -->|"Không"| R["ROLLBACK trên cùng connection"]
    D -->|"Có"| E["Statement 2: cộng tiền"]
    E --> F{"Bước 2 thành công?"}
    F -->|"Không"| R
    F -->|"Có"| G["Statement 3: ghi lịch sử"]
    G --> H{"Bước 3 thành công?"}
    H -->|"Không"| R
    H -->|"Có"| I["COMMIT trên cùng connection"]
    I --> J["Trả kết quả thành công"]
    R --> K["Trả lỗi / quyết định retry"]
~~~

### 1.1. Tại sao phải dùng cùng một kết nối?

Một kết nối database thường tương ứng với một **session** ở server. Session giữ ngữ cảnh transaction, trạng thái autocommit, một số thiết lập, temporary objects, biến session và các tài nguyên liên quan.

Giả sử:

~~~text
Connection A:
  BEGIN
  UPDATE tai_khoan SET so_du = so_du - 100000 WHERE id = 1

Connection B:
  UPDATE tai_khoan SET so_du = so_du + 100000 WHERE id = 2
  COMMIT
~~~

Hai kết nối là hai session khác nhau. UPDATE trên B không thuộc transaction đang mở trên A. B có thể tự commit câu lệnh của nó trong autocommit, trong khi A vẫn đang giữ phần trừ tiền chưa commit.

**Không được chia một transaction nghiệp vụ thành các câu lệnh gửi ngẫu nhiên qua nhiều connection.**

### 1.2. Cùng connection là điều kiện cần, chưa phải toàn bộ thiết kế

Ngoài việc dùng cùng connection, ứng dụng còn phải:

- Bắt đầu transaction đúng cách.
- Không để connection bị trả về pool trước khi commit/rollback.
- Kiểm tra số hàng bị ảnh hưởng và kết quả từng bước.
- Rollback khi lỗi.
- Không chia sẻ cùng một connection cho các request độc lập chạy đồng thời.
- Chọn isolation level và khóa phù hợp với bất biến nghiệp vụ.
- Xử lý trường hợp kết quả COMMIT không xác định do mất kết nối.
- Đảm bảo các thao tác ngoài database không bị nhầm là đã rollback cùng SQL.

## 2. Autocommit và transaction tường minh

Nhiều driver và DBMS có chế độ **autocommit**. Khi autocommit bật, mỗi câu lệnh độc lập thường được thực hiện như một transaction riêng và được xác nhận khi thành công.

Ví dụ:

~~~sql
UPDATE tai_khoan
SET so_du = so_du - 100000
WHERE id = 1;

UPDATE tai_khoan
SET so_du = so_du + 100000
WHERE id = 2;
~~~

Nếu autocommit đang bật, câu UPDATE đầu có thể đã commit trước khi câu thứ hai chạy. Nếu câu thứ hai lỗi, câu đầu vẫn còn hiệu lực.

### 2.1. Autocommit bật

~~~text
Statement 1 → transaction riêng → COMMIT
Statement 2 → transaction riêng → COMMIT
Statement 3 → transaction riêng → COMMIT
~~~

Đây là cách tiện cho truy vấn độc lập. Nó **không phù hợp** khi nhiều statement phải thành công cùng nhau.

### 2.2. Transaction tường minh

~~~sql
BEGIN;

-- Statement 1
UPDATE ...;

-- Statement 2
INSERT ...;

-- Statement 3
UPDATE ...;

COMMIT;
~~~

Các statement nằm trong transaction cho tới khi COMMIT hoặc ROLLBACK theo quy tắc DBMS.

### 2.3. Autocommit trong driver

Không phải mọi driver dùng cùng API:

| Môi trường | Cách thường gặp |
| --- | --- |
| JDBC | `Connection.setAutoCommit(false)` |
| Python DB-API | Tùy driver; thường cấu hình autocommit hoặc gọi commit/rollback |
| Node.js pg | Gửi `BEGIN`/`COMMIT` qua một `Client` được lấy từ pool |
| ADO.NET | `SqlConnection.BeginTransaction()` rồi gắn transaction vào command |
| ORM | Transaction scope/transaction manager của framework |
| SQLite API | `BEGIN`/`COMMIT` hoặc transaction context của thư viện |

Không giả định đổi autocommit ở một connection sẽ thay đổi trạng thái của mọi connection trong pool.

## 3. Bộ dữ liệu thực hành PostgreSQL

Ví dụ chính sử dụng PostgreSQL và schema `bai391` để tránh đụng tên bảng khác. Chỉ tạo schema trên database thử nghiệm mà bạn được phép sửa.

~~~sql
CREATE SCHEMA bai391;

CREATE TABLE bai391.tai_khoan (
    id BIGINT PRIMARY KEY,
    chu_so_huu TEXT NOT NULL,
    so_du NUMERIC(14,2) NOT NULL
        CHECK (so_du >= 0)
);

CREATE TABLE bai391.chuyen_tien (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    khoa_idempotency TEXT NOT NULL UNIQUE,
    tai_khoan_nguon BIGINT NOT NULL
        REFERENCES bai391.tai_khoan(id),
    tai_khoan_dich BIGINT NOT NULL
        REFERENCES bai391.tai_khoan(id),
    so_tien NUMERIC(14,2) NOT NULL
        CHECK (so_tien > 0),
    tao_luc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (tai_khoan_nguon <> tai_khoan_dich)
);

INSERT INTO bai391.tai_khoan (id, chu_so_huu, so_du)
VALUES
    (1, 'An',   500000),
    (2, 'Bình', 200000),
    (3, 'Chi',  900000);

SELECT id, chu_so_huu, so_du
FROM bai391.tai_khoan
ORDER BY id;
~~~

Số dư ban đầu:

| Tài khoản | Chủ sở hữu | Số dư |
| ---: | --- | ---: |
| 1 | An | 500.000 |
| 2 | Bình | 200.000 |
| 3 | Chi | 900.000 |
| **Tổng** | | **1.600.000** |

Bảng `chuyen_tien` có khóa `khoa_idempotency` duy nhất để minh họa việc nhận diện một yêu cầu gửi lại. Đây là **mã yêu cầu nghiệp vụ** do ứng dụng tạo và giữ ổn định khi retry cùng một yêu cầu.

## 4. Chuyển tiền bằng nhiều statement trong một transaction

Nghiệp vụ chuyển 100.000 từ An sang Bình cần thực hiện trên **một connection**. Ví dụ PostgreSQL dưới đây mô tả các câu lệnh mà ứng dụng gửi tuần tự; phần kiểm tra số hàng là logic ứng dụng phải thực hiện giữa các câu lệnh.

~~~sql
BEGIN;

-- 1. Khóa hai tài khoản theo thứ tự ID để giảm nguy cơ deadlock.
SELECT id
FROM bai391.tai_khoan
WHERE id IN (1, 2)
ORDER BY id
FOR UPDATE;

-- Ứng dụng kiểm tra kết quả có đúng hai tài khoản.
-- Nếu thiếu một tài khoản: ROLLBACK và báo lỗi.

-- 2. Trừ tiền, đồng thời kiểm tra đủ số dư.
UPDATE bai391.tai_khoan
SET so_du = so_du - 100000
WHERE id = 1
  AND so_du >= 100000;

-- Ứng dụng phải kiểm tra affected rows = 1.
-- Nếu bằng 0: ROLLBACK.

-- 3. Cộng tiền vào tài khoản đích.
UPDATE bai391.tai_khoan
SET so_du = so_du + 100000
WHERE id = 2;

-- Ứng dụng phải kiểm tra affected rows = 1.
-- Nếu bằng 0: ROLLBACK để hoàn lại bước trừ tiền.

-- 4. Ghi lịch sử trong cùng transaction.
INSERT INTO bai391.chuyen_tien (
    khoa_idempotency,
    tai_khoan_nguon,
    tai_khoan_dich,
    so_tien
)
VALUES (
    'transfer-req-0001',
    1,
    2,
    100000
);

-- 5. Chỉ khi tất cả bước bắt buộc thành công:
COMMIT;
~~~

Trong ví dụ thực tế, ứng dụng phải gửi `ROLLBACK` nếu một bước kiểm tra thất bại. Các comment nhắc kiểm tra không tự thực thi; database không tự dừng chỉ vì một dòng comment nói “rollback”.

### 4.1. Kết quả khi commit thành công

| Tài khoản | Trước | Thay đổi | Sau |
| --- | ---: | ---: | ---: |
| An | 500.000 | -100.000 | 400.000 |
| Bình | 200.000 | +100.000 | 300.000 |
| Chi | 900.000 | 0 | 900.000 |
| **Tổng** | **1.600.000** | **0** | **1.600.000** |

Bảng lịch sử có một dòng tương ứng. Ba thay đổi (trừ, cộng, ghi lịch sử) được xác nhận cùng nhau.

### 4.2. Nếu bước cộng tiền thất bại

Giả sử câu UPDATE tài khoản đích ảnh hưởng 0 hàng hoặc gặp lỗi constraint. Ứng dụng phải rollback:

~~~sql
ROLLBACK;
~~~

Khi rollback thành công:

- Số dư An trở lại 500.000.
- Số dư Bình vẫn là 200.000.
- Không có bản ghi chuyển tiền mới trong transaction bị hủy.
- Transaction kết thúc; connection có thể được dùng cho transaction mới sau khi ở trạng thái hợp lệ.

### 4.3. Vì sao cần kiểm tra số hàng?

Một UPDATE không lỗi SQL vẫn có thể tác động **0 hàng**:

~~~sql
UPDATE bai391.tai_khoan
SET so_du = so_du - 100000
WHERE id = 999;
~~~

Câu lệnh hợp lệ về cú pháp nhưng không có tài khoản ID 999. Nếu ứng dụng không kiểm tra affected rows, nó có thể tiếp tục cộng tiền ở tài khoản khác và ghi một lịch sử sai.

Quy tắc thường dùng:

- UPDATE yêu cầu đúng một bản ghi: kiểm tra affected rows bằng 1.
- INSERT có khóa được sinh: dùng `RETURNING` (PostgreSQL) hoặc API tương ứng để nhận ID.
- DELETE bắt buộc phải xóa một bản ghi: kiểm tra số hàng.
- Nếu 0 hàng là trạng thái hợp lệ (ví dụ idempotent no-op), phải định nghĩa rõ, không coi tất cả 0 hàng là thành công.

## 5. Transaction phải theo cùng một connection vật lý

Ứng dụng thường không mở socket database bằng tay. Nó dùng driver hoặc **connection pool**. Dù vậy, một transaction cụ thể vẫn phải được gắn với một connection/session cụ thể.

### 5.1. Connection pool làm gì?

Pool giữ sẵn một số connection để nhiều request có thể mượn dùng:

~~~text
Request A ── lấy connection C1 ── BEGIN
                                  UPDATE ...
                                  INSERT ...
                                  COMMIT
             trả C1 về pool

Request B ── lấy connection C2 ── SELECT ...
             trả C2 về pool
~~~

Khi request A lấy C1, pool cho request đó quyền sử dụng connection trong một khoảng thời gian. Sau khi transaction kết thúc và connection được trả về, request khác có thể lấy lại C1.

### 5.2. Sai lầm: lấy connection lại cho từng câu SQL

~~~text
pool.query("BEGIN")       → Connection C1
pool.query("UPDATE ...")  → Connection C2
pool.query("INSERT ...")  → Connection C3
pool.query("COMMIT")      → Connection C4
~~~

Đây là mô hình **không an toàn** nếu API pool chọn connection riêng cho từng lời gọi. BEGIN có thể chỉ mở transaction trên C1; UPDATE trên C2 có thể autocommit; COMMIT trên C4 không commit được những thay đổi ở C1/C2/C3.

Cách đúng: **mượn một client/connection từ pool, chạy mọi statement trên đối tượng ấy, commit/rollback, rồi mới release**.

### 5.3. Không trả connection về pool khi transaction còn mở

Nếu ứng dụng trả connection về pool trong trạng thái transaction chưa kết thúc, request khác có thể nhận một session đang:

- Có transaction còn mở;
- Đang giữ row/table locks;
- Có transaction PostgreSQL aborted;
- Có session variables hoặc isolation settings đã bị đổi;
- Có temporary tables hoặc advisory locks còn tồn tại;
- Đang giữ snapshot cũ hoặc tài nguyên chưa được giải phóng.

Pool tốt thường reset trạng thái khi connection được trả lại hoặc kiểm tra trước khi cấp lại, nhưng **không dựa vào reset của pool để thay thế rollback có chủ đích**.

## 6. Java JDBC: setAutoCommit(false), commit và rollback

JDBC đại diện connection bằng `java.sql.Connection`. Mặc định nhiều connection JDBC ở chế độ auto-commit. Khi cần transaction nhiều câu, đặt `autoCommit=false` và gửi mọi statement qua **cùng Connection**.

### 6.1. Ví dụ JDBC hoàn chỉnh

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class ChuyenTienService {
    private final DataSource dataSource;

    public ChuyenTienService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void chuyenTien(
            long taiKhoanNguon,
            long taiKhoanDich,
            BigDecimal soTien
    ) throws SQLException {
        if (taiKhoanNguon == taiKhoanDich) {
            throw new IllegalArgumentException(
                "Tai khoan nguon va dich phai khac nhau"
            );
        }
        if (soTien == null || soTien.signum() <= 0) {
            throw new IllegalArgumentException(
                "So tien phai lon hon 0"
            );
        }

        try (Connection conn = dataSource.getConnection()) {
            // Giả định DataSource cấp connection ở auto-commit=true.
            conn.setAutoCommit(false);

            try {
                // Khóa hai tài khoản trên cùng connection.
                try (PreparedStatement ps = conn.prepareStatement(
                        "SELECT id " +
                        "FROM bai391.tai_khoan " +
                        "WHERE id IN (?, ?) " +
                        "ORDER BY id FOR UPDATE")) {
                    ps.setLong(1, taiKhoanNguon);
                    ps.setLong(2, taiKhoanDich);

                    int soTaiKhoan = 0;
                    try (ResultSet rs = ps.executeQuery()) {
                        while (rs.next()) {
                            soTaiKhoan++;
                        }
                    }
                    if (soTaiKhoan != 2) {
                        throw new SQLException(
                            "Tai khoan nguon hoac dich khong ton tai"
                        );
                    }
                }

                // Trừ tiền và xác nhận đúng một hàng bị cập nhật.
                try (PreparedStatement ps = conn.prepareStatement(
                        "UPDATE bai391.tai_khoan " +
                        "SET so_du = so_du - ? " +
                        "WHERE id = ? AND so_du >= ?")) {
                    ps.setBigDecimal(1, soTien);
                    ps.setLong(2, taiKhoanNguon);
                    ps.setBigDecimal(3, soTien);

                    if (ps.executeUpdate() != 1) {
                        throw new SQLException(
                            "Khong du so du hoac tai khoan nguon khong hop le"
                        );
                    }
                }

                // Cộng tiền và xác nhận tài khoản đích tồn tại.
                try (PreparedStatement ps = conn.prepareStatement(
                        "UPDATE bai391.tai_khoan " +
                        "SET so_du = so_du + ? " +
                        "WHERE id = ?")) {
                    ps.setBigDecimal(1, soTien);
                    ps.setLong(2, taiKhoanDich);

                    if (ps.executeUpdate() != 1) {
                        throw new SQLException(
                            "Khong cap nhat duoc tai khoan dich"
                        );
                    }
                }

                // Ghi lịch sử trong cùng transaction.
                try (PreparedStatement ps = conn.prepareStatement(
                        "INSERT INTO bai391.chuyen_tien " +
                        "(khoa_idempotency, tai_khoan_nguon, " +
                        " tai_khoan_dich, so_tien) " +
                        "VALUES (?, ?, ?, ?)")) {
                    ps.setString(1, "request-key-do-ung-dung-cap");
                    ps.setLong(2, taiKhoanNguon);
                    ps.setLong(3, taiKhoanDich);
                    ps.setBigDecimal(4, soTien);
                    ps.executeUpdate();
                }

                conn.commit();
            } catch (SQLException | RuntimeException ex) {
                try {
                    conn.rollback();
                } catch (SQLException rollbackError) {
                    ex.addSuppressed(rollbackError);
                }
                throw ex;
            }
        }
    }
}
~~~

Điểm quan trọng:

- Tất cả `PreparedStatement` đều được tạo từ **cùng biến `conn`**.
- Tham số được bind, không nối chuỗi từ dữ liệu người dùng.
- Mỗi bước bắt buộc kiểm tra số hàng bị ảnh hưởng.
- `commit()` chỉ được gọi sau khi các bước đều thành công.
- Nếu có lỗi, code thử `rollback()` trên chính connection.
- `try-with-resources` đóng connection khi ra khỏi scope; nếu dùng pool, `close()` thường trả connection về pool thay vì đóng socket vật lý.

**Lưu ý vận hành:** ví dụ giả định connection mới lấy ra có auto-commit bật. Ứng dụng dùng pool cần bảo đảm connection được reset hoặc loại bỏ nếu rollback/cleanup thất bại. Không đổi auto-commit trở lại true khi transaction chưa được giải quyết, vì theo JDBC việc bật lại auto-commit trong transaction có thể commit transaction hiện tại.

### 6.2. Tại sao không dùng connection mới trong catch?

Sai:

~~~java
try (Connection c1 = ds.getConnection()) {
    c1.setAutoCommit(false);
    // UPDATE trên c1
} catch (SQLException e) {
    try (Connection c2 = ds.getConnection()) {
        c2.rollback();
    }
}
~~~

`c2.rollback()` không rollback transaction trên `c1`. Rollback phải gửi qua **connection đang sở hữu transaction**. Nếu connection đó mất hoặc không thể sử dụng, kết quả cần được xử lý như lỗi kết nối/transaction không xác định; không có connection mới nào tự khôi phục được transaction cũ.

### 6.3. Commit ném exception có nghĩa transaction chắc chắn rollback?

Không. Nếu server đã commit nhưng phản hồi bị mất trên mạng, client có thể nhận exception dù thay đổi **đã commit**. Đây là trạng thái **outcome không xác định**. Gọi rollback trên connection đã mất không thể chứng minh server chưa commit.

Để xử lý an toàn, cần khóa idempotency, mã giao dịch duy nhất và khả năng tra cứu trạng thái sau khi kết nối lại. Phần retry sẽ được giải thích ở mục 16.

## 7. Python DB-API và psycopg

Trong Python, nhiều driver tuân theo DB-API 2.0 với các phương thức `commit()` và `rollback()`. Cách cấu hình autocommit và transaction context phụ thuộc driver.

### 7.1. Ví dụ psycopg 3

~~~python
from decimal import Decimal
import psycopg

def chuyen_tien(dsn, nguon_id, dich_id, so_tien):
    if nguon_id == dich_id:
        raise ValueError("Tai khoan nguon va dich phai khac nhau")

    so_tien = Decimal(so_tien)
    if so_tien <= 0:
        raise ValueError("So tien phai lon hon 0")

    # Context connection của psycopg 3:
    # thành công thì commit; exception thì rollback;
    # khi thoát context, connection được đóng.
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id
                FROM bai391.tai_khoan
                WHERE id IN (%s, %s)
                ORDER BY id
                FOR UPDATE
                """,
                (nguon_id, dich_id),
            )

            if len(cur.fetchall()) != 2:
                raise ValueError("Tai khoan khong ton tai")

            cur.execute(
                """
                UPDATE bai391.tai_khoan
                SET so_du = so_du - %s
                WHERE id = %s AND so_du >= %s
                """,
                (so_tien, nguon_id, so_tien),
            )
            if cur.rowcount != 1:
                raise ValueError("Khong du so du")

            cur.execute(
                """
                UPDATE bai391.tai_khoan
                SET so_du = so_du + %s
                WHERE id = %s
                """,
                (so_tien, dich_id),
            )
            if cur.rowcount != 1:
                raise ValueError("Khong cap nhat duoc tai khoan dich")

            cur.execute(
                """
                INSERT INTO bai391.chuyen_tien
                    (khoa_idempotency, tai_khoan_nguon,
                     tai_khoan_dich, so_tien)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    "request-key-do-ung-dung-cap",
                    nguon_id,
                    dich_id,
                    so_tien,
                ),
            )
~~~

Trong psycopg 3, context manager của connection quản lý commit/rollback theo việc block kết thúc bình thường hay phát sinh exception. Các câu SQL trong block dùng **cùng đối tượng conn**.

Placeholder `%s` của psycopg là placeholder driver; không thay bằng nối chuỗi SQL.

### 7.2. DB-API tổng quát

Với driver khác, mô hình có thể là:

~~~python
conn = driver.connect(...)
try:
    # Cấu hình autocommit theo driver.
    conn.autocommit = False

    cur = conn.cursor()
    try:
        cur.execute("UPDATE ...", params_1)
        if cur.rowcount != 1:
            raise RuntimeError("Buoc 1 that bai")

        cur.execute("INSERT ...", params_2)
        if cur.rowcount != 1:
            raise RuntimeError("Buoc 2 that bai")

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
finally:
    conn.close()
~~~

Đây là **mẫu DB-API khái niệm**. Không phải mọi driver cho phép gán `conn.autocommit` giống nhau hoặc có cùng transaction-start semantics. Đọc tài liệu driver đang dùng.

### 7.3. Context manager không phải lúc nào cũng có nghĩa “mở transaction mới”

Một số thư viện cung cấp `with connection.transaction():` hoặc transaction context lồng. Cần đọc rõ:

- Context ngoài có tự mở connection không?
- Nó commit khi block thành công hay chỉ kết thúc savepoint?
- Khi lồng, có tạo savepoint không?
- Connection có được đóng hay trả về pool không?
- Exception bị bắt bên trong block có khiến transaction vẫn commit không?

Đừng suy từ cú pháp `with` hoặc tên API `transaction` mà bỏ qua semantics.

## 8. Node.js và node-postgres: lấy Client từ pool

Với `pg` (node-postgres), nếu dùng connection pool, transaction phải chạy trên **một Client đã checkout**. Không gọi `pool.query` cho từng statement của cùng transaction.

### 8.1. Mẫu đúng

~~~javascript
const { Pool } = require("pg");

const pool = new Pool({
  connectionString: process.env.DATABASE_URL
});

async function chuyenTien(nguonId, dichId, soTien) {
  if (nguonId === dichId || soTien <= 0) {
    throw new Error("Tham so chuyen tien khong hop le");
  }

  const client = await pool.connect();

  try {
    await client.query("BEGIN");

    const accounts = await client.query(
      "SELECT id\n" +
      "FROM bai391.tai_khoan\n" +
      "WHERE id = ANY($1::bigint[])\n" +
      "ORDER BY id\n" +
      "FOR UPDATE",
      [[nguonId, dichId]]
    );

    if (accounts.rowCount !== 2) {
      throw new Error("Tai khoan nguon hoac dich khong ton tai");
    }

    const debit = await client.query(
      "UPDATE bai391.tai_khoan\n" +
      "SET so_du = so_du - $1\n" +
      "WHERE id = $2 AND so_du >= $1",
      [soTien, nguonId]
    );

    if (debit.rowCount !== 1) {
      throw new Error("Khong du so du");
    }

    const credit = await client.query(
      "UPDATE bai391.tai_khoan\n" +
      "SET so_du = so_du + $1\n" +
      "WHERE id = $2",
      [soTien, dichId]
    );

    if (credit.rowCount !== 1) {
      throw new Error("Khong cap nhat duoc tai khoan dich");
    }

    await client.query(
      "INSERT INTO bai391.chuyen_tien\n" +
      "(khoa_idempotency, tai_khoan_nguon, tai_khoan_dich, so_tien)\n" +
      "VALUES ($1, $2, $3, $4)",
      ["request-key-do-ung-dung-cap", nguonId, dichId, soTien]
    );

    await client.query("COMMIT");
  } catch (error) {
    try {
      await client.query("ROLLBACK");
    } catch (rollbackError) {
      error.rollbackError = rollbackError;
      // Connection có thể không còn an toàn để tái sử dụng.
      // Xử lý discard/evict theo cơ chế của pool.
    }
    throw error;
  } finally {
    client.release();
  }
}
~~~

Điểm quan trọng:

- `pool.connect()` lấy một Client.
- Mọi câu lệnh dùng `client.query()`.
- `client.release()` chỉ được gọi sau khi transaction đã được commit/rollback hoặc connection được xử lý như không còn an toàn.
- Không thay bằng `pool.query("BEGIN")` rồi `pool.query("UPDATE ...")` vì pool có thể chọn các client khác nhau.
- Khi rollback thất bại, ứng dụng/pool cần loại bỏ connection hỏng thay vì trả nó như session sạch.

### 8.2. Sai lầm với Promise.all

Không nên gửi các bước phụ thuộc lẫn nhau bằng:

~~~javascript
await Promise.all([
  client.query("UPDATE ..."),
  client.query("INSERT ..."),
  client.query("UPDATE ...")
]);
~~~

Các câu lệnh trong một transaction có thứ tự logic. Nhiều driver sẽ xếp hàng câu lệnh trên connection, nhưng dựa vào việc xếp hàng để thực thi các bước phụ thuộc có thể làm code khó hiểu và khó xử lý lỗi. Hãy **await tuần tự** những bước cần kết quả của nhau; chỉ song song hóa các truy vấn độc lập khi driver và mô hình transaction hỗ trợ rõ ràng.

### 8.3. Không chia sẻ Client giữa nhiều request

Một Client có một session và một trạng thái transaction. Nếu hai request cùng dùng chung Client:

~~~text
Request A: BEGIN
Request A: UPDATE tài khoản

Request B: SELECT ...
Request B: COMMIT
~~~

Request B có thể vô tình tham gia hoặc kết thúc transaction của A. Không chia sẻ một connection transaction-bound cho nhiều request độc lập; dùng connection riêng cho mỗi transaction/request scope.

## 9. ADO.NET: SqlConnection và SqlTransaction

Trong .NET với SQL Server, các command cần tham gia cùng transaction phải gắn cùng đối tượng `SqlTransaction` và dùng cùng `SqlConnection`.

~~~csharp
using Microsoft.Data.SqlClient;
using System.Data;

public static async Task ChuyenTienAsync(
    string connectionString,
    long nguonId,
    long dichId,
    decimal soTien)
{
    await using var connection = new SqlConnection(connectionString);
    await connection.OpenAsync();

    await using var transaction =
        await connection.BeginTransactionAsync(
            IsolationLevel.ReadCommitted
        );

    try
    {
        await using (var debit = connection.CreateCommand())
        {
            debit.Transaction = (SqlTransaction)transaction;
            debit.CommandText = @"
                UPDATE dbo.TaiKhoan
                SET SoDu = SoDu - @SoTien
                WHERE Id = @NguonId
                  AND SoDu >= @SoTien;";

            debit.Parameters.AddWithValue("@SoTien", soTien);
            debit.Parameters.AddWithValue("@NguonId", nguonId);

            if (await debit.ExecuteNonQueryAsync() != 1)
                throw new InvalidOperationException("Khong du so du");
        }

        await using (var credit = connection.CreateCommand())
        {
            credit.Transaction = (SqlTransaction)transaction;
            credit.CommandText = @"
                UPDATE dbo.TaiKhoan
                SET SoDu = SoDu + @SoTien
                WHERE Id = @DichId;";

            credit.Parameters.AddWithValue("@SoTien", soTien);
            credit.Parameters.AddWithValue("@DichId", dichId);

            if (await credit.ExecuteNonQueryAsync() != 1)
                throw new InvalidOperationException("Tai khoan dich khong ton tai");
        }

        await transaction.CommitAsync();
    }
    catch
    {
        await transaction.RollbackAsync();
        throw;
    }
}
~~~

Đây là mẫu T-SQL/ADO.NET. Cần bảo đảm:

- Command dùng đúng `connection`.
- Command gắn đúng `transaction`.
- Không tạo connection mới cho statement tiếp theo.
- Commit/rollback đúng scope.
- Xử lý riêng lỗi rollback nếu connection đã hỏng; không để lỗi cleanup che nguyên nhân ban đầu trong code production.

Tên bảng và cột ở ví dụ .NET là giả định của schema SQL Server, không phải bảng PostgreSQL `bai391`.

## 10. Connection pool và trạng thái session

Connection pool giúp tái sử dụng connection, nhưng cũng tạo nguy cơ **rò rỉ trạng thái session** nếu ứng dụng không kết thúc transaction và không khôi phục cấu hình.

### 10.1. Vòng đời đúng

~~~mermaid
flowchart TD
    A["Checkout connection từ pool"] --> B["Kiểm tra/nhận trạng thái sạch"]
    B --> C["Bắt đầu transaction"]
    C --> D["Thực hiện mọi statement"]
    D --> E{"Kết quả"}
    E -->|"Thành công"| F["COMMIT"]
    E -->|"Lỗi"| G["ROLLBACK"]
    F --> H["Reset trạng thái nếu cần"]
    G --> H
    H --> I["Release connection về pool"]
~~~

Không release ở giữa các bước D.

### 10.2. Các trạng thái có thể rò rỉ

- Autocommit false;
- Isolation level tùy chỉnh;
- Read-only mode;
- Schema/search path;
- Session variables;
- Temporary tables;
- Advisory locks;
- Prepared statements/session state;
- Role hoặc authorization context;
- Transaction đang mở/aborted.

Pool thường có cơ chế reset một số trạng thái, nhưng hỗ trợ tùy driver/pool. Ứng dụng nên **đặt và khôi phục trạng thái trong scope transaction** theo hợp đồng rõ ràng.

### 10.3. Trả connection khi transaction bị aborted

Trong PostgreSQL, sau một statement lỗi trong transaction tường minh, session có thể ở trạng thái transaction aborted. Những câu SQL tiếp theo bị từ chối cho tới khi rollback toàn transaction hoặc rollback về savepoint hợp lệ.

Nếu connection bị trả lại pool trong trạng thái này, request sau có thể gặp lỗi khó hiểu. Luôn rollback trước khi release; nếu rollback thất bại, loại connection khỏi pool theo API của pool.

### 10.4. Connection timeout không thay thế transaction timeout

Pool acquisition timeout giới hạn thời gian **chờ lấy connection**. Statement timeout giới hạn câu SQL. Lock timeout giới hạn chờ khóa. Transaction timeout (nếu DBMS/driver hỗ trợ) giới hạn giao dịch. Chúng giải quyết các vấn đề khác nhau.

Một transaction có thể giữ connection và lock quá lâu dù mỗi statement riêng lẻ đều nhanh.

## 11. Transaction không được trải qua nhiều request tùy ý

Một sai lầm kiến trúc:

~~~text
HTTP request 1:
  BEGIN
  UPDATE giỏ hàng
  Trả response, giữ connection

Người dùng suy nghĩ 3 phút

HTTP request 2:
  INSERT đơn
  COMMIT
~~~

Giữ transaction mở trong thời gian người dùng tương tác có thể:

- Giữ connection trong pool;
- Giữ khóa và snapshot;
- Tăng nguy cơ deadlock/timeout;
- Làm database khó vacuum/thu hồi phiên bản cũ ở hệ MVCC;
- Khiến request sau không chắc lấy đúng connection;
- Dễ gặp lỗi nếu server restart hoặc request bị hủy.

**Không giữ transaction mở qua nhiều HTTP request hoặc chờ thao tác người dùng.** Nếu cần workflow nhiều bước kéo dài, dùng trạng thái nghiệp vụ bền vững, draft/reservation/expiry, optimistic concurrency hoặc saga; mỗi bước database ngắn có transaction riêng theo thiết kế.

### 11.1. Transaction scope thường nên nằm trong một service operation

~~~text
HTTP request
  → xác thực
  → service operation
      → checkout connection
      → BEGIN
      → SQL 1
      → SQL 2
      → SQL 3
      → COMMIT/ROLLBACK
      → release
  → trả response
~~~

Ranh giới transaction nên phản ánh **một đơn vị nghiệp vụ ngắn và nguyên tử**.

## 12. Xử lý lỗi giữa nhiều statement

Ứng dụng cần định nghĩa rõ việc gì xảy ra khi một câu SQL lỗi.

### 12.1. Quy tắc tổng quát

~~~text
Checkout connection
Begin transaction

Try:
    Execute statement 1
    Validate result 1
    Execute statement 2
    Validate result 2
    Execute statement 3
    Validate result 3
    Commit
Catch:
    Rollback
    Rethrow/translate error
Finally:
    Release only a clean or safely discarded connection
~~~

Không bắt exception rồi tiếp tục chạy statement tiếp theo như thể transaction vẫn hợp lệ.

### 12.2. PostgreSQL: transaction aborted sau lỗi

Trong PostgreSQL, một lỗi statement thông thường bên trong transaction tường minh làm transaction chuyển sang trạng thái **aborted**. Ví dụ:

~~~sql
BEGIN;

INSERT INTO bai391.tai_khoan (id, chu_so_huu, so_du)
VALUES (10, 'Demo', 100000);

-- Cố ý vi phạm PRIMARY KEY:
INSERT INTO bai391.tai_khoan (id, chu_so_huu, so_du)
VALUES (10, 'Trung ID', 200000);

-- Các câu lệnh bình thường tiếp theo bị từ chối
-- cho tới khi ROLLBACK hoặc ROLLBACK TO SAVEPOINT.
ROLLBACK;
~~~

Ứng dụng thường phải rollback toàn transaction. Nếu đã đặt savepoint **trước bước có thể lỗi**, có thể rollback tới mốc ấy để tiếp tục theo thiết kế; xem mục 13.

### 12.3. Không phải mọi DBMS xử lý lỗi giống PostgreSQL

- **PostgreSQL:** lỗi statement thường làm transaction hiện tại aborted cho đến rollback phù hợp.
- **SQL Server:** trạng thái transaction sau lỗi phụ thuộc loại lỗi/cấu hình; `XACT_STATE()` có thể là -1, nghĩa là transaction không thể commit.
- **MySQL/InnoDB:** nhiều lỗi chỉ rollback statement, nhưng deadlock có thể khiến InnoDB rollback toàn transaction; lock wait timeout có hành vi theo cấu hình.
- **Oracle:** nhiều lỗi statement chỉ rollback statement đó, transaction có thể tiếp tục; vẫn phải phân tích loại lỗi và ràng buộc deferred.
- **SQLite:** hành vi phụ thuộc loại lỗi và conflict resolution; một số lỗi hủy statement, một số có thể rollback transaction.

**Đừng viết một khối catch dùng chung cho mọi DBMS mà giả định transaction vẫn luôn usable.** Cách an toàn cho lỗi nghiệp vụ bắt buộc thường là rollback toàn transaction, sau đó phân loại retry nếu phù hợp.

### 12.4. Lỗi rollback cũng cần được xử lý

Nếu lỗi ban đầu là constraint violation nhưng rollback tiếp tục lỗi vì connection mất, không nên chỉ log lỗi rollback rồi trả connection vào pool. Connection có thể không còn ở trạng thái xác định. Hãy giữ cả lỗi gốc và lỗi cleanup, đồng thời đánh dấu connection cần discard/evict theo thư viện pool.

## 13. Savepoint: hoàn nguyên một phần nhưng vẫn cùng connection

Có trường hợp một transaction có phần bắt buộc và phần tùy chọn. Ví dụ đơn hàng bắt buộc được tạo, còn ghi một tùy chọn quà tặng có thể bị bỏ qua nếu dữ liệu không hợp lệ.

PostgreSQL:

~~~sql
BEGIN;

INSERT INTO bai391.tai_khoan (id, chu_so_huu, so_du)
VALUES (11, 'Khach demo', 100000);

SAVEPOINT truoc_buoc_tuy_chon;

-- Bước tùy chọn có thể thất bại.
-- Nếu thất bại và transaction còn khả năng phục hồi:
ROLLBACK TO SAVEPOINT truoc_buoc_tuy_chon;

RELEASE SAVEPOINT truoc_buoc_tuy_chon;

COMMIT;
~~~

Ví dụ này chỉ minh họa vị trí savepoint; nó chưa chứa bảng quà tặng. Trong PostgreSQL, `ROLLBACK TO` giữ transaction mở và giữ chính savepoint; `RELEASE` bỏ mốc chứ không commit transaction ngoài cùng.

### 13.1. Savepoint không phải nested commit

~~~text
BEGIN
  UPDATE A
  SAVEPOINT p
    UPDATE B
  RELEASE p
ROLLBACK
~~~

Kết quả: cả A và B đều bị rollback. RELEASE không làm B bền vững độc lập.

### 13.2. Dùng savepoint qua API

JDBC:

~~~java
Savepoint sp = conn.setSavepoint("before_optional");
try {
    // Các statement tùy chọn trên cùng conn.
    conn.releaseSavepoint(sp);
} catch (SQLException ex) {
    conn.rollback(sp);
    conn.releaseSavepoint(sp);
}
~~~

Chỉ bắt và bỏ lỗi nếu nghiệp vụ thật sự cho phép bỏ phần tùy chọn và lỗi có thể phục hồi. Với PostgreSQL, không gọi `RELEASE` trước khi rollback phần lỗi; transaction aborted cần rollback-to mốc đã có.

### 13.3. Không thay rollback toàn bộ bằng savepoint một cách tùy tiện

Nếu hai cập nhật là **hai vế bắt buộc của chuyển tiền**, không được rollback riêng bước cộng tiền rồi commit bước trừ tiền. Savepoint chỉ phù hợp cho đoạn nghiệp vụ được phép hủy độc lập.

## 14. Isolation level và dữ liệu thay đổi đồng thời

Dùng cùng connection bảo đảm các statement nằm trong cùng transaction, nhưng không có nghĩa transaction nhìn thấy một database đứng yên. Các transaction khác vẫn có thể chạy đồng thời theo isolation level.

### 14.1. READ COMMITTED

Ở PostgreSQL, `READ COMMITTED` mặc định thường cấp snapshot mới cho mỗi statement. Một transaction có thể:

~~~sql
BEGIN;

SELECT so_du
FROM bai391.tai_khoan
WHERE id = 1;

-- Transaction khác có thể COMMIT thay đổi ở đây.

SELECT so_du
FROM bai391.tai_khoan
WHERE id = 1;

COMMIT;
~~~

Hai SELECT trong cùng transaction có thể nhìn thấy **hai trạng thái đã commit khác nhau** nếu transaction khác commit giữa chúng.

Các DBMS khác có cách triển khai READ COMMITTED khác nhau, ví dụ locking read hay row-versioning tùy cấu hình SQL Server.

### 14.2. REPEATABLE READ

Mục tiêu là làm các lần đọc phù hợp trong transaction nhất quán hơn, nhưng semantics cụ thể phụ thuộc DBMS.

PostgreSQL `REPEATABLE READ` dùng snapshot transaction và ngăn nhiều dạng anomaly, nhưng vẫn có thể gặp serialization anomaly theo mô hình snapshot isolation. MySQL/InnoDB REPEATABLE READ có semantics consistent read và locking read riêng. Không coi tên isolation level giữa các hệ là một bản sao hoàn toàn.

### 14.3. SERIALIZABLE

SERIALIZABLE hướng tới kết quả tương đương một thứ tự thực thi tuần tự hợp lệ. DBMS có thể phải **từ chối transaction** khi phát hiện xung đột/serialization failure. Ứng dụng phải sẵn sàng rollback và retry toàn transaction.

Isolation cao hơn thường có chi phí về khóa, phát hiện xung đột hoặc retry. Chọn theo **bất biến cần bảo vệ**, không chỉ chọn mức cao nhất theo thói quen.

### 14.4. Một transaction nhiều statement có thể bị lost update

Mẫu nguy hiểm:

~~~text
A: SELECT so_du → 500000
B: SELECT so_du → 500000
A: ứng dụng tính 400000
B: ứng dụng tính 300000
A: UPDATE so_du = 400000
B: UPDATE so_du = 300000
~~~

Nếu không có lock/version/điều kiện thích hợp, một thay đổi có thể ghi đè thay đổi còn lại.

Thay vì đọc rồi tính trong ứng dụng, dùng phép cập nhật nguyên tử:

~~~sql
UPDATE bai391.tai_khoan
SET so_du = so_du - 100000
WHERE id = 1
  AND so_du >= 100000;
~~~

Database thực hiện biểu thức trên giá trị hàng được cập nhật theo cơ chế concurrency của nó; ứng dụng kiểm tra affected rows. Với bất biến nhiều hàng, vẫn cần transaction/locking/isolation phù hợp.

### 14.5. SELECT FOR UPDATE

PostgreSQL:

~~~sql
BEGIN;

SELECT id, so_du
FROM bai391.tai_khoan
WHERE id IN (1, 2)
ORDER BY id
FOR UPDATE;

-- Các transaction cạnh tranh cần khóa các hàng này
-- sẽ phải chờ theo quy tắc lock của PostgreSQL.

COMMIT;
~~~

`FOR UPDATE` khóa những hàng được chọn cho tới khi transaction kết thúc. Dùng khi cần đọc rồi ra quyết định dựa trên trạng thái hàng mà không muốn một transaction khác đồng thời sửa nó theo cách xung đột.

**Lưu ý:** lock càng lâu, khả năng chờ và deadlock càng cao. Chỉ khóa các hàng cần thiết, giữ transaction ngắn và thống nhất thứ tự khóa.

## 15. Deadlock: transaction đúng vẫn có thể bị hủy

Ví dụ:

~~~text
Transaction A                 Transaction B
--------------                --------------
UPDATE tài khoản 1             UPDATE tài khoản 2
chờ tài khoản 2                chờ tài khoản 1
~~~

A giữ lock hàng 1 và đợi hàng 2; B giữ lock hàng 2 và đợi hàng 1. DBMS phát hiện vòng chờ và chọn một transaction làm nạn nhân để hủy.

### 15.1. Cách giảm deadlock

- Lấy khóa theo cùng một thứ tự, ví dụ ID tăng dần.
- Giữ transaction ngắn.
- Tránh gọi API hoặc chờ người dùng khi đang giữ khóa.
- Có index phù hợp cho điều kiện WHERE, tránh lock/scan rộng ngoài dự tính.
- Xử lý deadlock error bằng rollback và retry **toàn transaction** khi thao tác có thể retry.
- Ghi nhận deadlock metrics để tìm mẫu truy vấn.

Ví dụ chuyển tiền từ tài khoản 1 sang 2 và từ 2 sang 1 đều khóa theo `ORDER BY id` trước khi cập nhật. Điều này giảm nguy cơ hai giao dịch lấy hai khóa theo thứ tự ngược nhau, dù không loại trừ mọi deadlock do các bảng/tài nguyên khác.

## 16. Retry: phải chạy lại cả transaction

Một lỗi deadlock hoặc serialization failure thường có nghĩa DBMS đã rollback transaction hoặc yêu cầu caller hủy transaction hiện tại. Không nên chỉ chạy lại **statement cuối cùng** nếu các bước trước đã dựa trên snapshot hoặc kết quả cũ.

Mẫu:

~~~text
for attempt in 1..N:
    checkout connection
    begin transaction
    try:
        chạy lại từ bước đầu
        kiểm tra từng kết quả
        commit
        return success
    catch retryable error:
        rollback nếu connection còn dùng được
        release/discard connection
        backoff
        continue
    catch non-retryable error:
        rollback
        raise
~~~

### 16.1. Lỗi nào có thể retry?

Tùy DBMS, một số mã lỗi đại diện:

- PostgreSQL: deadlock detected `40P01`; serialization failure `40001`.
- SQL Server: deadlock victim `1205`; các lỗi transient khác theo môi trường.
- MySQL: deadlock `1213`; lock wait timeout `1205` có semantics riêng.
- SQLite: `SQLITE_BUSY` hoặc `SQLITE_LOCKED` trong những ngữ cảnh phù hợp.

Đây là ví dụ mã lỗi, không phải danh sách đầy đủ. Cần phân biệt **transient/retryable** với lỗi dữ liệu như FK violation, CHECK violation hoặc input không hợp lệ. Retry một lỗi nghiệp vụ cố định thường chỉ lặp lại thất bại.

### 16.2. Backoff và giới hạn retry

Retry ngay lập tức nhiều lần có thể làm tải hệ thống nặng hơn và lặp deadlock. Dùng backoff có giới hạn, có thể thêm jitter, giới hạn tổng thời gian và ghi metrics. Nếu hết retry, trả lỗi có thể xử lý cho tầng gọi.

### 16.3. Retry phải idempotent

Nếu transaction bị mất kết nối **trong lúc COMMIT**, ứng dụng có thể không biết server đã commit hay chưa. Retry toàn bộ mà không có idempotency có thể chuyển tiền hai lần.

Đây là vấn đề khác với deadlock thông thường: **outcome commit không xác định**. Cần một mã yêu cầu duy nhất có ràng buộc UNIQUE và khả năng tra cứu kết quả đã commit.

## 17. Idempotency key cho thao tác ghi có retry

Trong schema demo, `bai391.chuyen_tien.khoa_idempotency` là UNIQUE. Ứng dụng tạo một key cho **một yêu cầu nghiệp vụ** và dùng lại key đó khi retry cùng yêu cầu.

Ví dụ ý tưởng PostgreSQL:

~~~sql
BEGIN;

INSERT INTO bai391.chuyen_tien (
    khoa_idempotency,
    tai_khoan_nguon,
    tai_khoan_dich,
    so_tien
)
VALUES (
    'transfer-req-0002',
    1,
    2,
    100000
)
ON CONFLICT (khoa_idempotency) DO NOTHING
RETURNING id;

-- Nếu trả về một hàng:
-- Đây là yêu cầu mới; tiếp tục khóa tài khoản,
-- trừ/cộng tiền, rồi COMMIT.

-- Nếu không trả về hàng:
-- Đọc giao dịch đã tồn tại bằng key.
-- So sánh payload (nguồn, đích, số tiền).
-- Nếu giống: trả lại kết quả cũ, không chuyển tiền lần nữa.
-- Nếu khác: từ chối việc tái sử dụng key cho yêu cầu khác.

COMMIT;
~~~

Đây là **khung xử lý**: ứng dụng phải kiểm tra kết quả `RETURNING` và quyết định có tiếp tục các bước tài khoản hay không. Nếu INSERT mới được thực hiện rồi một bước sau thất bại, ROLLBACK cũng hủy dòng idempotency mới; yêu cầu có thể được retry an toàn sau khi sửa nguyên nhân nếu thiết kế cho phép.

### 17.1. Key phải gắn với nội dung yêu cầu

Không chỉ kiểm tra key tồn tại. Nếu request đầu là chuyển 100.000 từ 1 sang 2, nhưng request thứ hai dùng cùng key để chuyển 900.000 từ 1 sang 3, không được trả thành công như thể đó là cùng yêu cầu.

Lưu các thuộc tính cần thiết hoặc hash request đã chuẩn hóa để xác nhận payload trùng khớp.

### 17.2. Idempotency không thay transaction

Idempotency ngăn xử lý trùng theo key. Nó không tự đảm bảo trừ/cộng tiền nguyên tử. Vẫn phải thực hiện các bước bắt buộc trong cùng transaction và kiểm tra kết quả.

## 18. Side effect bên ngoài transaction

Một transaction database không tự rollback những hành động bên ngoài:

- Gửi email/SMS;
- Gọi HTTP API;
- Gửi message tới broker;
- Ghi file;
- Cập nhật cache ngoài;
- Gửi thông báo push.

Ví dụ:

~~~text
BEGIN
UPDATE đơn hàng
Gửi email "đơn đã xác nhận"
ROLLBACK
~~~

Database có thể quay về trạng thái cũ, nhưng email đã rời hệ thống.

### 18.1. Transactional outbox

Một cách phổ biến là ghi sự kiện vào **bảng outbox** trong cùng transaction:

~~~sql
BEGIN;

UPDATE don_hang
SET trang_thai = 'DA_XAC_NHAN'
WHERE id = 101
  AND trang_thai = 'MOI';

-- Ứng dụng kiểm tra đúng một hàng được cập nhật.

INSERT INTO outbox (event_id, loai_su_kien, payload)
VALUES (
    'order-101-confirmed-v1',
    'DON_DA_XAC_NHAN',
    '{"don_id":101,"trang_thai":"DA_XAC_NHAN"}'
);

COMMIT;
~~~

Worker đọc các event **đã commit** và gửi ra broker/email/API. Nếu transaction rollback, cả thay đổi đơn và outbox row bị hủy.

### 18.2. Outbox vẫn cần idempotency

Worker có thể gửi thành công rồi crash trước khi đánh dấu đã gửi. Lần chạy sau có thể gửi lại. Consumer cần event ID và cơ chế xử lý trùng. Outbox cải thiện tính nhất quán giữa DB và việc phát sự kiện; nó không bảo đảm exactly-once cho mọi hệ ngoài.

### 18.3. Saga cho workflow dài qua nhiều hệ thống

Nếu một quy trình gồm nhiều dịch vụ độc lập và không có distributed transaction chung, có thể dùng **saga**: mỗi bước là transaction cục bộ và có hành động bù trừ khi bước sau thất bại. Đây là mô hình khác với transaction nhiều statement trên một connection. Không giữ một connection SQL mở trong suốt workflow dài.

## 19. Transaction lồng nhau và savepoint trong ứng dụng

Nhiều framework gọi API là “nested transaction”, nhưng DBMS thường triển khai scope lồng bằng **savepoint** hoặc transaction counter, không phải một transaction độc lập commit bền vững.

### 19.1. PostgreSQL

PostgreSQL không tạo nested transaction độc lập bằng cách gọi BEGIN lần nữa trong transaction đang mở. Dùng:

~~~sql
BEGIN;
UPDATE ...;

SAVEPOINT p;
INSERT ...;

ROLLBACK TO SAVEPOINT p;
RELEASE SAVEPOINT p;

COMMIT;
~~~

### 19.2. SQL Server

SQL Server cho phép `BEGIN TRANSACTION` lồng và tăng `@@TRANCOUNT`, nhưng inner COMMIT chỉ giảm counter; nó **không commit độc lập**. ROLLBACK toàn bộ có thể hủy transaction ngoài. Rollback tới named savepoint là cách hoàn nguyên một phần trong transaction hợp lệ.

### 19.3. MySQL/InnoDB, Oracle, SQLite

Các hệ này có savepoint với cú pháp/semantics riêng. Không giả định `RELEASE`/`ROLLBACK TO` và DDL giống nhau. Một số DDL gây implicit commit ở MySQL/Oracle; SQLite có thể dùng savepoint ngoài cùng để khởi tạo transaction.

### 19.4. Transaction scope trong ORM

ORM có thể cung cấp:

- `BeginTransaction`;
- `TransactionScope`;
- `session.begin()`;
- `transaction.atomic()`;
- `withTransaction(...)`.

Hãy xem framework gắn transaction vào connection như thế nào. Nếu một repository/service tự mở connection mới, nó có thể **thoát khỏi transaction scope của caller** dù tên API vẫn chứa chữ transaction.

## 20. Khác biệt transaction giữa các hệ quản trị

Cú pháp và mặc định khác nhau; nguyên tắc **mọi statement của một transaction phải đi qua đúng session/connection** vẫn là điểm quan trọng.

| DBMS | Bắt đầu tường minh | Commit/rollback | Ghi chú |
| --- | --- | --- | --- |
| PostgreSQL | `BEGIN` hoặc `START TRANSACTION` | `COMMIT` / `ROLLBACK` | Autocommit thường do client điều khiển; lỗi trong transaction thường chuyển trạng thái aborted |
| MySQL/InnoDB | `START TRANSACTION` hoặc `BEGIN` | `COMMIT` / `ROLLBACK` | Autocommit mặc định thường bật; cần bảng/engine transactional; nhiều DDL implicit commit |
| SQL Server | `BEGIN TRANSACTION` | `COMMIT TRANSACTION` / `ROLLBACK TRANSACTION` | `@@TRANCOUNT` và `XACT_STATE()` quan trọng; nested BEGIN không phải nested commit độc lập |
| Oracle | Transaction bắt đầu ngầm khi DML phù hợp | `COMMIT` / `ROLLBACK` | Không dùng BEGIN TRANSACTION giống PostgreSQL; nhiều DDL implicit commit |
| SQLite | `BEGIN [DEFERRED/IMMEDIATE/EXCLUSIVE]` | `COMMIT` / `ROLLBACK` | Writer concurrency khác hệ server; một writer tại một thời điểm theo cơ chế locking |

### 20.1. PostgreSQL

~~~sql
BEGIN;
UPDATE ...;
INSERT ...;
COMMIT;
~~~

Với autocommit client bật, mỗi statement độc lập tự commit khi thành công. Khi cần nhiều statement nguyên tử, dùng BEGIN và kết thúc trên cùng session.

Trong transaction lỗi, rollback toàn bộ hoặc rollback tới savepoint hợp lệ. PostgreSQL hỗ trợ nhiều DDL trong transaction nhưng có ngoại lệ cho một số lệnh quản trị.

### 20.2. MySQL/InnoDB

~~~sql
START TRANSACTION;

UPDATE tai_khoan
SET so_du = so_du - 100000
WHERE id = 1;

UPDATE tai_khoan
SET so_du = so_du + 100000
WHERE id = 2;

COMMIT;
~~~

Cần bảo đảm bảng sử dụng **InnoDB** hoặc engine transactional phù hợp. Với bảng không hỗ trợ transaction, không được dựa vào rollback như PostgreSQL/InnoDB. Nhiều DDL gây implicit commit nên tránh trộn migration schema với transaction nghiệp vụ mà không đọc semantics cụ thể.

### 20.3. SQL Server

~~~sql
BEGIN TRANSACTION;

UPDATE dbo.TaiKhoan
SET SoDu = SoDu - 100000
WHERE Id = 1;

UPDATE dbo.TaiKhoan
SET SoDu = SoDu + 100000
WHERE Id = 2;

COMMIT TRANSACTION;
~~~

Trong T-SQL, transaction lồng và trạng thái lỗi có các quy tắc riêng. Sau lỗi cần xét `XACT_STATE()`; giá trị -1 nghĩa transaction uncommittable và chỉ có thể rollback toàn bộ. Đừng cho rằng mọi lỗi đều có thể tiếp tục bằng statement tiếp theo.

### 20.4. Oracle

Oracle thường bắt đầu transaction khi thực hiện DML; không cần viết `BEGIN TRANSACTION` như PostgreSQL/SQL Server:

~~~sql
UPDATE tai_khoan
SET so_du = so_du - 100000
WHERE id = 1;

UPDATE tai_khoan
SET so_du = so_du + 100000
WHERE id = 2;

COMMIT;
~~~

Nếu lỗi ở bước sau, ứng dụng có thể gửi ROLLBACK trên cùng session. DDL Oracle thường có implicit commit trước/sau theo quy tắc Oracle; không giả định DDL nằm trong cùng transaction rollback được như DML.

### 20.5. SQLite

~~~sql
BEGIN IMMEDIATE;

UPDATE tai_khoan
SET so_du = so_du - 100000
WHERE id = 1;

UPDATE tai_khoan
SET so_du = so_du + 100000
WHERE id = 2;

COMMIT;
~~~

`BEGIN IMMEDIATE` cố lấy quyền bắt đầu transaction ghi sớm hơn, giúp phát hiện/chờ xung đột writer ngay lúc bắt đầu thay vì tới câu ghi sau. SQLite có mô hình concurrency khác database server nhiều writer; giữ transaction ghi ngắn đặc biệt quan trọng.

### 20.6. Đừng chuyển cú pháp BEGIN máy móc

Một lớp abstraction ứng dụng có thể chuẩn hóa API begin/commit/rollback, nhưng cần biết dialect. Ví dụ Oracle không dùng cùng cú pháp BEGIN TRANSACTION; SQL Server có XACT_STATE; MySQL DDL implicit commit; SQLite có BEGIN IMMEDIATE. Tương thích nhiều DBMS đòi hỏi kiểm tra semantics chứ không chỉ thay chuỗi lệnh.

## 21. DDL, migration và transaction ứng dụng

Một số hệ quản trị cho phép DDL transactional trong nhiều trường hợp; hệ khác có implicit commit.

Ví dụ:

~~~sql
BEGIN;
ALTER TABLE tai_khoan ADD COLUMN ghi_chu TEXT;
ROLLBACK;
~~~

Kết quả phụ thuộc DBMS và lệnh cụ thể:

- PostgreSQL hỗ trợ nhiều DDL trong transaction, nhưng một số lệnh không được phép trong transaction block.
- MySQL có nhiều DDL gây implicit commit.
- Oracle nhiều DDL gây implicit commit.
- SQL Server hỗ trợ transaction cho nhiều DDL nhưng có ngoại lệ.
- SQLite hỗ trợ transactional schema changes trong nhiều trường hợp, nhưng vẫn phải xét lệnh/version.

**Không trộn migration schema và giao dịch nghiệp vụ** trong cùng connection với giả định chung rằng rollback sẽ hoàn tác cả hai. Dùng migration tool và kế hoạch triển khai phù hợp từng DBMS.

## 22. Transaction và truy vấn đọc

Transaction nhiều statement không chỉ dành cho UPDATE/INSERT. Một transaction có thể cần đọc nhất quán nhiều bảng:

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT ... FROM don_hang WHERE id = 101;
SELECT ... FROM chi_tiet_don WHERE don_hang_id = 101;
SELECT ... FROM thanh_toan WHERE don_hang_id = 101;

COMMIT;
~~~

Trong PostgreSQL REPEATABLE READ, các truy vấn đọc phù hợp dùng cùng snapshot transaction. Ở READ COMMITTED, mỗi statement có snapshot riêng. Chọn mức isolation theo câu hỏi nghiệp vụ:

- Có cần các truy vấn đọc thấy cùng một snapshot không?
- Có cần khóa các hàng để cập nhật tiếp không?
- Có chấp nhận dữ liệu thay đổi giữa hai SELECT không?
- Có cần serializable behavior hay có thể dùng version/locking?

### 22.1. Read-only transaction

Một số DBMS hỗ trợ khai báo transaction chỉ đọc hoặc driver có thuộc tính read-only. Đây là tín hiệu/giới hạn giúp DBMS và ứng dụng quản lý transaction. Nó không phải cơ chế phân quyền thay thế; quyền đọc vẫn cần được kiểm soát.

### 22.2. Không cần transaction tường minh cho mọi SELECT đơn

Một câu SELECT độc lập thường có transaction ngầm/autocommit riêng. Chỉ mở transaction nhiều statement khi có yêu cầu nhất quán/đọc-ghi rõ ràng; transaction dài không cần thiết giữ snapshot và connection lâu hơn.

## 23. Async/await và transaction context

Trong ứng dụng bất đồng bộ, một lỗi dễ gặp là gọi câu SQL trên connection không còn nằm trong scope của transaction.

### 23.1. Đúng: truyền client/transaction context

~~~javascript
async function capNhatDon(client, donId) {
  await client.query(
    "UPDATE don_hang SET trang_thai = $1 WHERE id = $2",
    ["DA_XAC_NHAN", donId]
  );

  await client.query(
    "INSERT INTO nhat_ky_don(don_hang_id, hanh_dong) VALUES ($1, $2)",
    [donId, "XAC_NHAN"]
  );
}

const client = await pool.connect();
try {
  await client.query("BEGIN");
  await capNhatDon(client, 101);
  await client.query("COMMIT");
} catch (error) {
  await client.query("ROLLBACK");
  throw error;
} finally {
  client.release();
}
~~~

Hàm con nhận rõ **client đang sở hữu transaction**. Nó không tự lấy connection mới từ pool.

### 23.2. Sai: hàm con tự dùng pool toàn cục

~~~javascript
async function capNhatDonSai(donId) {
  await pool.query("UPDATE don_hang ...");
  await pool.query("INSERT INTO nhat_ky_don ...");
}
~~~

Nếu caller đã BEGIN trên một Client khác, các câu gọi pool có thể chạy trên connection khác. Tên hàm không nói rằng nó tham gia transaction của caller; thực tế nó đã thoát scope.

### 23.3. Không dùng connection đồng thời giữa nhiều task

Nếu hai coroutine/task cùng dùng một connection, chúng có thể xen kẽ câu lệnh trong một transaction. Kết quả là thao tác của request A và B có thể vô tình nằm chung một transaction hoặc ảnh hưởng thứ tự nhau. Dùng **một connection cho một transaction owner** và truyền context tường minh.

## 24. Thời gian sống và giới hạn của transaction

Transaction càng dài, càng có thể:

- Giữ row/table locks;
- Giữ connection trong pool;
- Tăng lock wait/deadlock;
- Giữ snapshot cũ, làm chậm thu hồi phiên bản dữ liệu ở hệ MVCC;
- Tạo nhiều WAL/undo và công việc recovery;
- Làm tăng rủi ro timeout hoặc connection drop;
- Giữ tài nguyên server trong lúc ứng dụng chờ.

### 24.1. Không làm việc ngoài database giữa hai statement nếu không cần

Tránh:

~~~text
BEGIN
UPDATE bảng A
Gọi API thanh toán mất 15 giây
Chờ người dùng xác nhận
UPDATE bảng B
COMMIT
~~~

Trong 15 giây đó transaction có thể giữ lock và connection. Nếu API thất bại, rollback database không hoàn tác hành động bên ngoài đã xảy ra.

Hãy tách quy trình thành các transaction ngắn, trạng thái nghiệp vụ và outbox/saga khi phù hợp.

### 24.2. Batch processing: một transaction hay nhiều transaction?

Nếu nhập 1 triệu dòng:

- **Một transaction lớn:** atomic toàn bộ, nhưng giữ tài nguyên lâu và rollback có thể tốn kém.
- **Commit theo batch:** giảm thời gian transaction và có tiến độ bền vững, nhưng toàn job không còn atomic tất cả-hoặc-không-gì.
- **Savepoint theo batch trong một transaction:** vẫn chưa commit độc lập; rollback transaction ngoài vẫn hủy tất cả.
- **Staging table + validate + merge:** có thể phù hợp cho pipeline import, tùy yêu cầu và DBMS.

Chọn theo hợp đồng nghiệp vụ, khả năng retry và yêu cầu phục hồi.

## 25. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Gửi BEGIN qua một connection, UPDATE qua connection khác | Các statement không cùng transaction | Giữ một connection/client cho toàn scope |
| Dùng pool.query cho từng statement transaction | Pool có thể chọn connection khác | Checkout một client rồi dùng nó |
| Quên COMMIT | Transaction còn mở/giữ lock | Kết thúc rõ bằng commit/rollback |
| Bắt exception nhưng không rollback | Connection có thể ở trạng thái lỗi/aborted | Rollback trước release |
| Trả connection về pool khi còn transaction | Request sau nhận session bẩn | Commit/rollback rồi reset hoặc evict |
| Không kiểm tra affected rows | Bước nghiệp vụ có thể không tác động hàng nào nhưng vẫn báo thành công | Kiểm tra row count/RETURNING |
| Commit từng statement | Có thể lưu một phần workflow | Tắt autocommit hoặc BEGIN tường minh |
| Dùng SELECT rồi UPDATE không khóa/version | Lost update/race | Atomic UPDATE, lock, version/isolation |
| Retry chỉ statement cuối | Dùng kết quả/snapshot cũ | Retry toàn transaction khi phù hợp |
| Retry sau commit timeout không idempotent | Có thể thực hiện nghiệp vụ hai lần | Idempotency key và tra cứu kết quả |
| Giữ transaction qua HTTP requests | Lock/connection/snapshot tồn tại quá lâu | Transaction ngắn trong một service operation |
| Gọi HTTP/email trong transaction | Side effect không rollback, transaction dài | Outbox/worker/saga |
| Dùng nested BEGIN như nested commit | Không có commit độc lập như kỳ vọng | Savepoint hoặc transaction riêng có chủ đích |
| Giả định isolation giống mọi DBMS | Anomaly hoặc lỗi retry không dự đoán | Đọc semantics DBMS/driver |
| Chạy DDL giữa transaction trên mọi DBMS | Implicit commit hoặc lỗi | Tách migration và nghiệp vụ |
| Dùng Promise.all cho statement phụ thuộc | Thứ tự/error khó kiểm soát | Await tuần tự trong transaction |
| Chia sẻ connection giữa request | Transaction bị xen lẫn | Một owner cho mỗi transaction |
| Rollback lỗi nhưng vẫn tái sử dụng connection | Trạng thái session không xác định | Evict/discard connection |
| Coi COMMIT exception là chắc chắn rollback | Có thể commit thành công nhưng phản hồi mất | Reconcile bằng idempotency key |
| Mở transaction chỉ để chạy một SELECT nhanh | Giữ tài nguyên không cần thiết | Dùng autocommit nếu phù hợp |

## 26. Quy trình debug một transaction nhiều statement

Khi dữ liệu bị cập nhật một phần hoặc ứng dụng báo lỗi transaction:

1. Xác định **connection/session ID** nếu DBMS có công cụ cung cấp.
2. Ghi lại thứ tự statement, tham số đã ẩn dữ liệu nhạy cảm và transaction boundary.
3. Xác nhận BEGIN/autocommit thực sự được bật/tắt đúng.
4. Xác nhận mọi câu lệnh dùng cùng connection/client/transaction object.
5. Kiểm tra affected rows, RETURNING, generated keys.
6. Xác định statement nào lỗi và transaction state sau lỗi.
7. Kiểm tra rollback có thành công không; nếu không, connection đã được discard chưa?
8. Xem lock waits, deadlock logs, isolation level và timeout.
9. Nếu COMMIT bị timeout/mất kết nối, kiểm tra kết quả qua idempotency key thay vì gửi lại mù quáng.
10. Kiểm tra side effects ngoài DB và outbox.
11. Reproduce với hai hoặc nhiều session nếu lỗi liên quan concurrency.
12. Viết regression test cho thành công, rollback, retry, conflict và connection reuse.

### 26.1. Công cụ quan sát PostgreSQL

Có thể xem các session/transaction đang hoạt động bằng `pg_stat_activity`:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
~~~

Cần quyền phù hợp để xem đầy đủ thông tin của session khác. Cột `xact_start` lâu có thể giúp nhận diện transaction dài. Tránh đưa literal nhạy cảm từ query vào log/dashboard nếu không cần.

### 26.2. Quan sát khóa

PostgreSQL cung cấp `pg_locks` để phân tích lock đang được giữ/chờ. Kết hợp `pg_stat_activity` để xác định session nào đang block session nào. Không kết luận mọi lock đều là vấn đề; cần xét mode, relation, transaction age và wait chain.

### 26.3. Đừng log bí mật trong SQL parameters

Log transaction nên chứa correlation ID, operation name, transaction duration, SQLSTATE, số hàng ảnh hưởng và connection/trace ID khi phù hợp. Tránh log mật khẩu, token, dữ liệu thanh toán hoặc JSON cá nhân nguyên vẹn.

## 27. Bài tập thực hành có lời giải

Các bài 1–15 dùng schema PostgreSQL `bai391` ở mục 3. Bài có DML nên dùng transaction/ROLLBACK khi thực hành trên database thử nghiệm. Các bài còn lại kiểm tra kiến thức về ứng dụng và phương ngữ.

### Bài 1. Vì sao phải cùng connection?

**Câu hỏi:** gửi BEGIN qua connection A, UPDATE qua B và COMMIT qua C có tạo một transaction không?

**Đáp án:** Không. Mỗi connection là session riêng; transaction state không tự chia sẻ giữa A, B và C.

### Bài 2. Autocommit

**Tình huống:** autocommit bật, câu UPDATE đầu thành công, câu UPDATE thứ hai lỗi. Câu đầu có thể còn hiệu lực không?

**Đáp án:** Có. Mỗi statement có thể đã commit riêng. Muốn nguyên tử nhiều statement, phải dùng transaction tường minh hoặc tắt autocommit theo driver.

### Bài 3. Trừ tiền có điều kiện

**Yêu cầu:** trừ 100.000 khỏi An chỉ khi đủ số dư.

~~~sql
BEGIN;

UPDATE bai391.tai_khoan
SET so_du = so_du - 100000
WHERE id = 1
  AND so_du >= 100000
RETURNING id, so_du;

ROLLBACK;
~~~

**Đáp án:** Nếu đủ số dư và tài khoản tồn tại, trả một hàng. Nếu không, trả 0 hàng; ứng dụng phải không tiếp tục workflow như thể đã trừ thành công.

### Bài 4. Rollback nhiều statement

~~~sql
BEGIN;

UPDATE bai391.tai_khoan
SET so_du = so_du - 100000
WHERE id = 1;

UPDATE bai391.tai_khoan
SET so_du = so_du + 100000
WHERE id = 2;

ROLLBACK;
~~~

**Câu hỏi:** số dư cuối cùng thế nào?

**Đáp án:** Cả hai thay đổi bị hủy; An 500.000 và Bình 200.000 như trước transaction.

### Bài 5. Câu SQL không lỗi nhưng 0 hàng

**Câu hỏi:** UPDATE ID 999 không lỗi SQL. Có thể coi bước nghiệp vụ thành công không?

**Đáp án:** Không nếu nghiệp vụ yêu cầu đúng một tài khoản. Kiểm tra affected rows/RETURNING; 0 hàng phải được phân loại.

### Bài 6. Connection pool

**Câu hỏi:** vì sao không dùng pool.query("BEGIN"), rồi pool.query("UPDATE")?

**Đáp án:** Pool có thể chọn connection khác nhau cho từng lời gọi. Phải checkout một client/connection và dùng nó cho toàn bộ transaction.

### Bài 7. JDBC

**Yêu cầu:** API nào bắt đầu transaction thủ công và kết thúc thành công trong JDBC?

**Đáp án:** `conn.setAutoCommit(false)` để quản lý thủ công, sau đó `conn.commit()`; nếu lỗi thì `conn.rollback()`. Các statement phải tạo/thực thi qua cùng `conn`.

### Bài 8. Node.js pg

**Câu hỏi:** nên dùng `pool.query` hay `client.query` sau khi checkout `client`?

**Đáp án:** Dùng `client.query` cho mọi statement transaction. Release client sau commit/rollback.

### Bài 9. Python

**Câu hỏi:** exception thoát khỏi psycopg connection transaction context có hành vi gì?

**Đáp án:** Với context manager connection của psycopg 3, block kết thúc bình thường thì commit; exception thoát ra thì rollback, rồi context đóng connection theo semantics thư viện.

### Bài 10. Savepoint

**Câu hỏi:** RELEASE SAVEPOINT có commit thay đổi trong savepoint không?

**Đáp án:** Không. Nó bỏ mốc; transaction ngoài vẫn có thể rollback toàn bộ thay đổi chưa commit.

### Bài 11. PostgreSQL aborted transaction

**Câu hỏi:** sau lỗi UNIQUE trong transaction PostgreSQL, có thể tiếp tục UPDATE bình thường ngay không?

**Đáp án:** Không. Transaction thường đã aborted; cần ROLLBACK toàn bộ hoặc ROLLBACK TO savepoint được tạo trước lỗi.

### Bài 12. Isolation

**Câu hỏi:** READ COMMITTED PostgreSQL có đảm bảo hai SELECT trong cùng transaction thấy đúng một snapshot không?

**Đáp án:** Không. Mỗi statement thường có snapshot riêng; transaction khác commit giữa hai SELECT có thể được nhìn thấy ở SELECT sau.

### Bài 13. Deadlock

**Câu hỏi:** hai transaction khóa hai tài khoản theo thứ tự ngược nhau có thể gây gì?

**Đáp án:** Deadlock. Khóa theo thứ tự thống nhất (ví dụ ID tăng dần), transaction ngắn và retry toàn transaction khi DBMS hủy một bên.

### Bài 14. Retry sau serialization failure

**Câu hỏi:** nên chạy lại riêng câu UPDATE cuối hay toàn bộ transaction?

**Đáp án:** Thường phải chạy lại toàn bộ transaction để đọc lại trạng thái và tính toán từ đầu; chỉ retry statement cuối có thể dùng kết quả cũ.

### Bài 15. Commit timeout

**Tình huống:** client mất kết nối khi gửi COMMIT. Có thể kết luận transaction đã rollback không?

**Đáp án:** Không. Server có thể đã commit nhưng phản hồi bị mất. Dùng idempotency key và truy vấn trạng thái để reconcile.

### Bài 16. Idempotency key

**Câu hỏi:** tại sao cùng request retry phải dùng lại key?

**Đáp án:** Để database nhận diện đó là cùng một yêu cầu, không tạo giao dịch mới. Key phải có UNIQUE và được đối chiếu với nội dung request.

### Bài 17. External email

**Tình huống:** transaction UPDATE đơn rồi gửi email, sau đó rollback. Email có biến mất không?

**Đáp án:** Không. Email nằm ngoài transaction database. Ghi outbox trong transaction và gửi sau commit.

### Bài 18. SQL Server

**Câu hỏi:** `BEGIN TRANSACTION` lồng nhau và COMMIT inner có tạo commit bền vững độc lập không?

**Đáp án:** Không. SQL Server tăng/giảm `@@TRANCOUNT`; inner COMMIT không commit độc lập toàn bộ dữ liệu trước outer transaction.

### Bài 19. Oracle

**Câu hỏi:** có dùng `BEGIN TRANSACTION` như PostgreSQL để mở transaction Oracle không?

**Đáp án:** Không theo cách đó. Oracle thường bắt đầu transaction ngầm khi DML phù hợp được thực hiện; kết thúc bằng COMMIT/ROLLBACK.

### Bài 20. MySQL

**Câu hỏi:** dùng transaction nhiều statement có rollback được trên mọi storage engine MySQL không?

**Đáp án:** Không. Phải dùng engine hỗ trợ transaction, thường là InnoDB, và xem xét implicit commit của DDL.

### Bài 21. SQLite

**Câu hỏi:** `BEGIN IMMEDIATE` giúp gì?

**Đáp án:** Nó yêu cầu quyền bắt đầu transaction ghi sớm hơn, giúp phát hiện/chờ xung đột writer từ đầu thay vì tới statement ghi sau.

### Bài 22. Async context

**Câu hỏi:** một hàm service con dùng pool toàn cục có tự tham gia transaction của caller không?

**Đáp án:** Không. Phải truyền transaction-bound client/connection hoặc context tương ứng. Nếu hàm con tự lấy connection khác, nó có thể chạy ngoài transaction.

### Bài 23. Transaction dài

**Tình huống:** mở transaction rồi chờ người dùng xác nhận trong 5 phút. Có nên không?

**Đáp án:** Không nên. Nó giữ connection/snapshot/lock và tăng rủi ro timeout. Dùng workflow trạng thái bền vững, transaction ngắn cho từng bước.

### Bài 24. Chuyển tiền và thứ tự khóa

**Yêu cầu:** chuyển tiền 1→2 và 2→1 đồng thời. Cách giảm deadlock?

**Đáp án:** Khóa cả hai tài khoản theo cùng thứ tự (ví dụ ORDER BY id), sau đó mới cập nhật; vẫn phải xử lý deadlock từ những tài nguyên khác.

### Bài 25. Kiểm tra toàn bộ workflow

**Câu hỏi:** chuyển tiền thành công nhưng không có dòng lịch sử do INSERT log bị lỗi thì sao?

**Đáp án:** Nếu lịch sử là bắt buộc, rollback cả transaction. Không commit hai vế số dư khi bước log bắt buộc thất bại.

## 28. Checklist triển khai transaction trong ứng dụng

Trước khi đưa một workflow nhiều statement lên production, hãy xác định:

1. **Transaction owner** là service, repository, ORM hay tầng nào?
2. Có lấy **một connection/client** cho toàn bộ transaction không?
3. Autocommit được cấu hình đúng cho driver?
4. BEGIN/commit/rollback có nằm trong cùng connection?
5. Mọi statement phụ thuộc nhau có được await/thực thi tuần tự?
6. Có command nào tự mở connection mới và thoát transaction scope không?
7. Có kiểm tra affected rows/RETURNING/generated keys sau mỗi bước bắt buộc?
8. Có rollback khi lỗi và cả khi exception runtime/cancellation?
9. Nếu rollback thất bại, connection có bị discard khỏi pool không?
10. Connection được reset trước khi trả về pool?
11. Có giữ transaction quá lâu qua network/API/user input không?
12. Isolation level có phù hợp với bất biến nghiệp vụ?
13. Có lock đúng hàng và thống nhất lock order?
14. Deadlock/serialization failure có retry toàn transaction không?
15. Retry có backoff, giới hạn và idempotency key?
16. Commit timeout/mất kết nối có quy trình reconcile không?
17. Side effect ngoài DB có được xử lý qua outbox/saga không?
18. Savepoint có đúng với phần nghiệp vụ được phép rollback riêng?
19. DDL có implicit commit trong DBMS đang dùng không?
20. Có kiểm thử hai session đồng thời và connection pool thật?
21. Có timeout cho statement, lock và transaction?
22. Log/trace có correlation ID, transaction duration, SQLSTATE và affected rows?
23. Có tránh log dữ liệu nhạy cảm?
24. Có xác nhận driver/ORM thực sự gắn command với transaction object?
25. Có tài liệu hóa DBMS/version và semantics khi triển khai nhiều database?

## 29. Tài liệu tham khảo chính thức

Cú pháp và semantics transaction thay đổi theo DBMS, driver và phiên bản. Khi triển khai, nên đọc đúng tài liệu của môi trường thực tế:

- **PostgreSQL:** [Transactions](https://www.postgresql.org/docs/current/tutorial-transactions.html), [BEGIN](https://www.postgresql.org/docs/current/sql-begin.html), [COMMIT](https://www.postgresql.org/docs/current/sql-commit.html), [ROLLBACK](https://www.postgresql.org/docs/current/sql-rollback.html), [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html), [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html).
- **Java JDBC:** [Connection](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Connection.html), [Savepoint](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Savepoint.html).
- **Python DB-API:** [PEP 249](https://peps.python.org/pep-0249/), [Psycopg transactions](https://www.psycopg.org/psycopg3/docs/basic/transactions.html).
- **Node.js pg:** [Transactions](https://node-postgres.com/features/transactions), [Pool API](https://node-postgres.com/apis/pool).
- **MySQL:** [START TRANSACTION, COMMIT, and ROLLBACK](https://dev.mysql.com/doc/refman/8.4/en/commit.html), [InnoDB Transaction Model](https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-model.html).
- **SQL Server:** [Transactions](https://learn.microsoft.com/en-us/sql/t-sql/language-elements/transactions-transact-sql), [COMMIT TRANSACTION](https://learn.microsoft.com/en-us/sql/t-sql/language-elements/commit-transaction-transact-sql), [XACT_STATE](https://learn.microsoft.com/en-us/sql/t-sql/functions/xact-state-transact-sql).
- **Oracle:** [Managing Transactions](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/transaction-processing-and-control.html), [COMMIT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/COMMIT.html), [ROLLBACK](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ROLLBACK.html).
- **SQLite:** [Transactions](https://www.sqlite.org/lang_transaction.html), [Isolation](https://www.sqlite.org/isolation.html).

## 30. Kết luận

Khi một nghiệp vụ gồm nhiều câu SQL bắt buộc phải thành công cùng nhau, ứng dụng cần thực hiện chúng trong **một transaction trên cùng connection/session**:

- Checkout một connection từ pool.
- Bắt đầu transaction hoặc tắt autocommit theo driver.
- Gửi mọi statement qua đúng connection đó.
- Kiểm tra kết quả và số hàng bị ảnh hưởng ở từng bước.
- COMMIT khi tất cả điều kiện bắt buộc thỏa mãn.
- ROLLBACK khi có lỗi; chỉ release connection sau khi transaction đã được giải quyết hoặc connection bị loại bỏ an toàn.
- Chọn isolation, khóa, retry và idempotency theo nghiệp vụ.
- Dùng outbox/worker cho side effects bên ngoài transaction.

**Đừng nhầm ba khái niệm:** một đối tượng connection từ pool, một transaction trên session đó, và một workflow nghiệp vụ có thể kéo dài qua nhiều request. Connection phải được giữ xuyên suốt transaction; transaction nên ngắn; workflow dài cần trạng thái và cơ chế điều phối riêng.

Một transaction được viết tốt không chỉ có BEGIN và COMMIT. Nó còn có **kiểm tra kết quả, đường rollback, xử lý concurrency, retry an toàn và quyền sở hữu connection rõ ràng**.
