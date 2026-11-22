# Hard parse, soft parse, shared cursor và library cache

Khi ứng dụng Java gửi một câu SQL đến **Oracle Database**, cơ sở dữ liệu không đơn giản “đọc câu lệnh rồi chạy”. Oracle phải xác định câu SQL có hợp lệ, người dùng có quyền truy cập, đối tượng nào được tham chiếu và cách thực thi nào phù hợp. Nếu cùng một câu SQL được thực thi lặp lại, Oracle có thể **tái sử dụng thông tin đã phân tích** thay vì làm lại toàn bộ công việc này.

Đó là lý do cần hiểu bốn khái niệm gắn liền với nhau:

- **Hard parse**: Oracle cần tạo hoặc tái tạo thông tin thực thi cho một câu SQL do không có shared cursor phù hợp để tái sử dụng; giai đoạn này thường bao gồm tối ưu hóa và sinh execution plan.
- **Soft parse**: Oracle tìm thấy một shared cursor có thể sử dụng và bỏ qua phần lớn công việc tối ưu hóa của hard parse, nhưng vẫn có chi phí kiểm tra và quản lý cursor.
- **Shared cursor**: cấu trúc dùng chung phía Oracle lưu thông tin của một câu SQL đã được phân tích, có thể được nhiều phiên sử dụng nếu điều kiện chia sẻ thỏa mãn.
- **Library cache**: vùng cache nằm trong **shared pool của SGA**, chứa các đối tượng dùng chung như SQL cursor và đối tượng PL/SQL đã biên dịch.

Hiểu đúng các khái niệm này giúp phân biệt **chậm do parse** với **chậm do thực thi SQL**, giải thích vì sao dùng bind variable có thể giảm tải máy chủ, và quan sát các trường hợp một câu SQL có nhiều *child cursor*.

## 1. Từ SQL text đến kết quả truy vấn

Một câu SQL có thể trải qua các giai đoạn sau:

\`\`\`text
Ứng dụng Java / công cụ SQL
        |
        | Gửi SQL text và các bind value
        v
Phiên Oracle (session)
        |
        v
Kiểm tra có cursor đã sẵn sàng để dùng lại trong session?
        |
        +-- Có, còn hợp lệ --> Có thể tái sử dụng session cursor
        |
        +-- Chưa --> Tra cứu shared cursor trong library cache
                       |
                       +-- Có child cursor tương thích
                       |      |
                       |      +--> SOFT PARSE --> EXECUTE --> FETCH (nếu có)
                       |
                       +-- Không có child cursor tương thích
                              |
                              +--> HARD PARSE
                                     - Phân tích cú pháp/ngữ nghĩa
                                     - Xác định quyền và đối tượng
                                     - Tối ưu hóa, xây dựng kế hoạch
                                     - Tạo child cursor có thể dùng chung
                                                |
                                                v
                                          EXECUTE --> FETCH
\`\`\`

Sơ đồ là mô hình tư duy, không phải mô tả mọi nhánh nội bộ trong tất cả phiên bản Oracle. Đặc biệt, **không phải mỗi lần \`EXECUTE\` đều phải parse lại**: một cursor đã mở và chuẩn bị sẵn có thể được thực thi nhiều lần với các bind value khác nhau.

### Phân biệt parse, execute và fetch

| Giai đoạn | Vai trò | Ví dụ quan sát |
| --- | --- | --- |
| **Parse** | Kiểm tra và chuẩn bị câu SQL/cursor | Xác định \`SELECT\` tham chiếu bảng/cột nào, chọn hoặc tìm plan phù hợp |
| **Execute** | Thực hiện câu SQL trên cơ sở dữ liệu | Chạy \`UPDATE\`, hoặc bắt đầu thực thi một \`SELECT\` |
| **Fetch** | Lấy các hàng kết quả của truy vấn | JDBC gọi \`ResultSet.next()\` để đọc hàng |

Một \`SELECT\` có thể tốn phần lớn thời gian trong lúc **fetch** nhiều hàng qua mạng, dù parse rất nhanh. Ngược lại, hàng nghìn câu SQL khác nhau được tạo liên tục có thể tạo tải CPU đáng kể ngay cả khi mỗi câu chỉ trả một hàng. Vì vậy cần xem riêng **tần suất parse**, **thời gian parse**, **số lần execute** và **thời gian thực thi/đọc dữ liệu**.

## 2. Library cache nằm ở đâu trong kiến trúc Oracle?

Ở mức khái niệm, Oracle sử dụng bộ nhớ chia sẻ (**SGA**) và bộ nhớ riêng của phiên/tiến trình (thường gọi là **PGA**). Trong SGA, **shared pool** bao gồm vùng **library cache** và các cấu trúc bộ nhớ chia sẻ khác.

\`\`\`text
Oracle Database instance
|
+-- SGA (bộ nhớ dùng chung)
|   |
|   +-- Shared pool
|   |   |
|   |   +-- Library cache
|   |   |    +-- SQL shared cursors
|   |   |    +-- PL/SQL program units và metadata liên quan
|   |   |
|   |   +-- Các cấu trúc bộ nhớ chia sẻ khác
|   |
|   +-- Database buffer cache
|   |    +-- Các block dữ liệu được cache
|   |
|   +-- Các thành phần SGA khác
|
+-- Session/process state
    +-- Trạng thái thực thi và cursor riêng theo phiên
\`\`\`

**Library cache không phải database buffer cache.** Library cache chủ yếu giúp tái sử dụng *cấu trúc thực thi, thông tin SQL/PLSQL và metadata*; database buffer cache giữ *các block dữ liệu*. Một câu SQL có shared cursor vẫn có thể phải đọc hàng triệu block dữ liệu; việc tái sử dụng parse không biến một truy vấn tốn I/O thành truy vấn tức thời.

Library cache cũng **không phải kho lưu vĩnh viễn**. Cursor có thể bị đẩy khỏi bộ nhớ khi chịu áp lực shared pool, không còn được dùng, bị vô hiệu hóa do thay đổi metadata hoặc phải được tạo child cursor mới vì bối cảnh thực thi không tương thích. Vì vậy “đã từng chạy câu SQL” không đảm bảo mãi mãi sẽ soft parse.

## 3. Hard parse: khi Oracle cần tạo thông tin thực thi

Giả sử lần đầu một session gửi câu SQL:

\`\`\`sql
SELECT ma_khach_hang, ho_ten
FROM khach_hang
WHERE ma_khach_hang = 101;
\`\`\`

Nếu chưa có shared cursor tương thích trong library cache, Oracle phải thực hiện **hard parse**. Các việc chính có thể gồm:

1. **Kiểm tra cú pháp**: các từ khóa, biểu thức và cấu trúc câu lệnh có hợp lệ hay không.
2. **Kiểm tra ngữ nghĩa và đối tượng**: bảng, cột, schema, kiểu dữ liệu và quyền truy cập có phù hợp không.
3. **Tối ưu hóa**: dùng thông tin về đối tượng, thống kê, bind và các thiết lập liên quan để đánh giá những cách truy cập, phép nối, thứ tự xử lý có thể sử dụng.
4. **Tạo execution plan/cursor**: lưu các cấu trúc cần thiết để thực thi và có thể chia sẻ với những phiên phù hợp về sau.

Hard parse thường tốn nhiều CPU, thao tác với cấu trúc chia sẻ và tài nguyên đồng bộ hơn soft parse. Khi nhiều session cùng cố tạo/tải cùng đối tượng, chi phí tranh chấp trong library cache có thể tăng lên.

Tuy nhiên, **hard parse không luôn là lỗi**. Câu SQL thực sự mới, một thay đổi schema, một bộ thống kê mới hoặc sự khác biệt cần thiết về môi trường tối ưu hóa có thể dẫn đến hard parse hợp lý. Mục tiêu là tránh hard parse **lặp đi lặp lại không cần thiết**, nhất là trên các câu SQL nghiệp vụ giống nhau.

### Execution plan được chọn lúc nào?

Trong hard parse, Oracle Optimizer có thể chọn một kế hoạch như dùng index, full table scan, nested loops hay hash join. Kế hoạch được lưu trong child cursor và dùng để thực thi. Không nên đồng nhất “đã chọn plan” với “đã chạy plan”: quá trình tối ưu hóa thuộc giai đoạn chuẩn bị, còn việc đọc và biến đổi dữ liệu thuộc thực thi.

Một SQL text **không cam kết chỉ có một plan cho mọi lúc**. Cùng một câu SQL có thể có nhiều child cursor với điều kiện thực thi hoặc plan khác nhau, và plan cũng có thể thay đổi sau lần parse mới khi thống kê, cấu trúc hoặc môi trường thay đổi.

## 4. Soft parse: tìm và tái sử dụng shared cursor

Giả sử cùng câu SQL tiếp tục được gửi ở phiên khác:

\`\`\`sql
SELECT ma_khach_hang, ho_ten
FROM khach_hang
WHERE ma_khach_hang = 101;
\`\`\`

Nếu Oracle tìm được một child cursor hợp lệ và tương thích, có thể **soft parse**: sử dụng thông tin thực thi đã có thay vì tối ưu hóa từ đầu. Oracle vẫn cần xử lý một số bước như tìm cursor và kiểm tra điều kiện chia sẻ, nên soft parse **không hoàn toàn miễn phí**.

Để hình dung:

| Tình huống | Khả năng xảy ra | Ghi chú |
| --- | --- | --- |
| Câu SQL mới, chưa có cursor phù hợp | **Hard parse** | Phải tạo thông tin thực thi |
| Câu SQL đã có trong library cache, điều kiện chia sẻ phù hợp | **Soft parse** | Tái sử dụng child cursor |
| Một \`PreparedStatement\` còn mở, được thực thi lặp lại | **Không nhất thiết parse mỗi lần** | Có thể tái sử dụng cursor/session state đã chuẩn bị |
| SQL đã chạy trước đó nhưng bị invalidated/aged out | **Có thể hard parse lại** | Cursor cũ không còn sử dụng được |
| Cùng SQL text nhưng khác môi trường cần child riêng | **Có thể hard parse child mới** | Chia sẻ không chỉ phụ thuộc chữ của SQL |

Soft parse còn khác khái niệm **session cursor cache hit**. Một session có thể giữ thông tin về cursor dùng gần đây để giảm chi phí chuẩn bị và tra cứu lặp lại. Đây là tối ưu hóa ở phạm vi session; còn shared cursor ở library cache phục vụ nhiều session tương thích. Cả hai đều hữu ích, nhưng không phải một cấu trúc.

## 5. Parent cursor và child cursor

Khi xem các dynamic performance view của Oracle, ta có thể gặp một \`SQL_ID\` với nhiều \`CHILD_NUMBER\`. Điều này liên quan đến cách Oracle quản lý **parent** và **child cursor**.

\`\`\`text
Library cache
  |
  +-- Parent cursor: SQL text / SQL identity
        SQL_ID = "ví dụ một mã của SQL text"
        |
        +-- Child cursor 0
        |      Môi trường và metadata A
        |      Execution plan X
        |
        +-- Child cursor 1
        |      Môi trường/đặc điểm bind B
        |      Execution plan X hoặc Y
        |
        +-- Child cursor 2
               Môi trường/đặc điểm bind C
               Execution plan Y
\`\`\`

**Parent cursor** đại diện cho danh tính câu SQL trong cơ chế quản lý cursor dùng chung; **child cursor** giữ những cấu trúc thực thi phù hợp với một bối cảnh chia sẻ cụ thể. Một parent có thể có một hoặc nhiều child, và **không bắt buộc mỗi child có một plan khác nhau**.

### Vì sao cùng SQL text vẫn có nhiều child?

Những lý do có thể gồm:

- Khác biệt **kiểu dữ liệu hoặc metadata của bind variable** khi gửi từ các client.
- Khác biệt **optimizer environment**, ví dụ một số thiết lập phiên có ảnh hưởng đến lựa chọn kế hoạch.
- Khác biệt về **ngữ cảnh đối tượng, quyền hoặc trạng thái phụ thuộc** khiến không thể dùng child đã có.
- Thay đổi thống kê hoặc metadata làm **invalidate** cursor trước đó.
- **Adaptive Cursor Sharing** có thể tạo các child phù hợp với những nhóm bind value khác nhau khi phân phối dữ liệu khiến lựa chọn plan nhạy với giá trị bind.

Không nên kết luận “nhiều child cursor = lỗi” chỉ từ con số \`VERSION_COUNT\`. Cần kiểm tra mức độ tăng, nguyên nhân các child không chia sẻ được, tiêu thụ bộ nhớ, thời gian parse và tác động thực tế đến workload.

### \`SQL_ID\`, \`CHILD_NUMBER\`, \`PLAN_HASH_VALUE\` khác nhau

| Trường | Diễn tả | Có thể dùng để làm gì? |
| --- | --- | --- |
| \`SQL_ID\` | Định danh một SQL text/câu SQL trong các view theo dõi | Tìm các thông tin thực thi của cùng câu SQL |
| \`CHILD_NUMBER\` | Số thứ tự child cursor dưới parent | Phân biệt các bản thực thi của cùng parent |
| \`PLAN_HASH_VALUE\` | Mã băm đại diện cấu trúc plan ở mức Oracle cung cấp | So sánh nhanh dấu hiệu thay đổi plan, không thay thế xem plan chi tiết |
| \`VERSION_COUNT\` | Số phiên bản child cursor của một SQL trong view tổng hợp | Gợi ý có nhiều child cần quan sát |

Hai child có thể có cùng \`PLAN_HASH_VALUE\`; hai SQL khác nhau cũng có thể có plan trông tương tự. Để chẩn đoán chính xác, hãy xem **SQL text, child number, nguyên nhân tạo child và execution plan thực tế**.

## 6. Bind variable: chìa khóa giảm SQL text phân mảnh

Xét một ứng dụng tra cứu khách hàng theo ID, nhưng tạo SQL bằng cách ghép giá trị trực tiếp:

\`\`\`sql
SELECT ma_khach_hang, ho_ten FROM khach_hang WHERE ma_khach_hang = 101;
SELECT ma_khach_hang, ho_ten FROM khach_hang WHERE ma_khach_hang = 102;
SELECT ma_khach_hang, ho_ten FROM khach_hang WHERE ma_khach_hang = 103;
\`\`\`

Ba câu chứa các **literal khác nhau**, vì thế Oracle không thể đơn giản xem chúng là cùng một SQL text khi sử dụng chế độ chia sẻ chính xác thông thường. Workload kiểu này dễ sinh nhiều parent cursor, gây thêm parse và dùng shared pool kém hiệu quả nếu ứng dụng tạo hàng nghìn biến thể.

Thay bằng một câu SQL sử dụng **bind variable**:

\`\`\`sql
SELECT ma_khach_hang, ho_ten
FROM khach_hang
WHERE ma_khach_hang = :ma_khach_hang;
\`\`\`

Các lần chạy truyền giá trị \`101\`, \`102\`, \`103\` riêng ở lúc bind. **SQL text giữ nguyên**, tạo cơ hội dùng chung cursor. Bind variable đồng thời hỗ trợ phòng chống **SQL injection** đối với dữ liệu đầu vào vì dữ liệu không bị ghép thành cú pháp SQL.

### Java JDBC: dùng \`PreparedStatement\`

\`\`\`java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public class KhachHangRepository {
    private final DataSource dataSource;

    public KhachHangRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void inTenKhachHang(long[] maKhachHang) throws SQLException {
        String sql = """
            SELECT ma_khach_hang, ho_ten
            FROM khach_hang
            WHERE ma_khach_hang = ?
            """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {

            for (long id : maKhachHang) {
                statement.setLong(1, id);
                try (ResultSet rs = statement.executeQuery()) {
                    while (rs.next()) {
                        System.out.printf("%d: %s%n",
                                rs.getLong("MA_KHACH_HANG"),
                                rs.getString("HO_TEN"));
                    }
                }
            }
        }
    }
}
\`\`\`

Ở đây:

1. **JDBC** dùng ký hiệu \`?\` thay cho cú pháp bind \`:ma_khach_hang\` của các công cụ SQL Oracle.
2. Câu SQL chỉ được chuẩn bị thành một \`PreparedStatement\` trong phạm vi connection đang mượn, rồi **thực thi nhiều lần** với giá trị bind khác nhau.
3. Oracle có cơ hội tái sử dụng cursor. Trong một ứng dụng nhiều request, khả năng tái sử dụng còn phụ thuộc **connection pool, statement cache, kiểu bind và trạng thái cursor**.
4. Tham số \`setLong\` giữ kiểu giá trị thống nhất. Gửi cùng vị trí bind lần thì kiểu số, lần thì kiểu chuỗi có thể làm phát sinh chuyển kiểu và/hoặc thêm child cursor không cần thiết.

Đây là ví dụ Java sử dụng text block, phù hợp với Java phiên bản hiện đại. Tên bảng và cột giả định đã có trong schema, driver JDBC Oracle đã được cấu hình và tài khoản có quyền \`SELECT\`.

**Không dùng nối chuỗi để thay thế bind**:

\`\`\`java
// Không nên: tạo nhiều SQL text, đồng thời không an toàn với đầu vào tùy ý.
String sql = "SELECT * FROM khach_hang WHERE ma_khach_hang = " + userInput;
\`\`\`

Bind variable đại diện cho **giá trị dữ liệu**, không dùng để thay tên bảng, tên cột hoặc từ khóa như \`ORDER BY\`. Với định danh động, ứng dụng phải kiểm soát bằng danh sách tên được phép và xây dựng SQL theo mẫu đã xác định.

## 7. Chia sẻ cursor không có nghĩa “mọi giá trị bind đều cùng plan”

Bind giúp tránh phân mảnh SQL text nhưng đôi khi các giá trị khác nhau có **độ chọn lọc rất khác nhau**. Ví dụ một bảng đơn hàng có 99% bản ghi mang trạng thái \`DONE\`, nhưng chỉ 1% mang trạng thái \`ERROR\`:

\`\`\`sql
SELECT *
FROM don_hang
WHERE trang_thai = :trang_thai;
\`\`\`

Một plan thích hợp khi trả gần hết bảng có thể khác plan phù hợp khi lấy rất ít hàng. Oracle có các cơ chế liên quan như:

- **Bind peeking**: trong những điều kiện nhất định, optimizer có thể xem giá trị bind ở lúc hard parse để ước lượng độ chọn lọc và chọn plan.
- **Adaptive Cursor Sharing (ACS)**: Oracle có thể ghi nhận rằng hiệu quả thực thi phụ thuộc đáng kể vào giá trị bind và cho phép nhiều child cursor tương ứng với những miền giá trị khác nhau.
- **Bind-sensitive / bind-aware**: các trạng thái có thể quan sát ở một số phiên bản và tình huống qua \`IS_BIND_SENSITIVE\`, \`IS_BIND_AWARE\` trong \`V$SQL\`.

Không phải mọi SQL có bind đều trở thành bind-sensitive hoặc bind-aware, cũng không phải mọi lần đổi giá trị bind đều tạo child mới. Hành vi phụ thuộc phiên bản Oracle, thống kê, kiểu predicate, khối lượng dữ liệu và môi trường tối ưu hóa. Khi thấy nhiều child, cần phân biệt **child hợp lý do giá trị bind** với **child không chia sẻ được do khác cấu hình/kiểu bind**.

Một nguyên tắc quan trọng: **tối ưu parse và tối ưu execution plan là hai mục tiêu có liên quan nhưng khác nhau**. Giảm hard parse không tự động làm một SQL quét quá nhiều dữ liệu trở nên nhanh. Ngược lại, ép mọi truy vấn dùng duy nhất một plan chỉ để giảm child cursor có thể khiến một số giá trị bind chạy rất chậm.

## 8. Thực hành: quan sát parse và shared cursor

Các ví dụ sau dành cho một **schema thực hành Oracle riêng**, có quyền tạo bảng và chạy SQL. Những view \`V$...\` thường cần quyền truy cập do DBA cấp; người học không mặc nhiên có quyền chỉ vì đăng nhập được schema. Không cấp quyền quản trị rộng chỉ để chạy bài quan sát.

### 8.1. Chuẩn bị bảng nhỏ

\`\`\`sql
CREATE TABLE cursor_demo (
    id       NUMBER(6) PRIMARY KEY,
    nhom     VARCHAR2(20 CHAR) NOT NULL,
    gia_tri  NUMBER(10, 2) NOT NULL
);

INSERT INTO cursor_demo VALUES (1, 'A', 100);
INSERT INTO cursor_demo VALUES (2, 'A', 200);
INSERT INTO cursor_demo VALUES (3, 'B', 300);
INSERT INTO cursor_demo VALUES (4, 'B', 400);
INSERT INTO cursor_demo VALUES (5, 'C', 500);
COMMIT;
\`\`\`

Bảng nhỏ này dùng để phân biệt SQL text, bind value và việc thực thi. DDL có thể làm phát sinh invalidation/commit theo cơ chế Oracle; hãy hoàn tất bước tạo bảng **trước khi** bắt đầu quan sát parse.

### 8.2. Gửi nhiều SQL text dùng literal

\`\`\`sql
SELECT /* cursor_demo_literal_1 */ id, nhom
FROM cursor_demo
WHERE id = 1;

SELECT /* cursor_demo_literal_2 */ id, nhom
FROM cursor_demo
WHERE id = 2;

SELECT /* cursor_demo_literal_3 */ id, nhom
FROM cursor_demo
WHERE id = 3;
\`\`\`

Ở đây không chỉ giá trị literal khác nhau mà cả comment để đánh dấu cũng khác nhau. Khi quan sát, ta mong thấy **nhiều SQL text khác biệt**. Không dùng ba câu này để đo tỷ lệ hard parse chính xác của ứng dụng thật; chúng chỉ thể hiện cơ chế các SQL text khác nhau không có cơ hội tái sử dụng cùng parent theo cách chia sẻ thông thường.

### 8.3. Gửi cùng SQL text với bind khác nhau

Trong **SQL*Plus hoặc SQLcl**, \`VARIABLE\` và \`EXEC\` là lệnh của công cụ, không phải câu SQL độc lập có thể đưa nguyên văn vào mọi JDBC API:

\`\`\`sql
VARIABLE p_id NUMBER

EXEC :p_id := 1
SELECT /* cursor_demo_bind */ id, nhom
FROM cursor_demo
WHERE id = :p_id;

EXEC :p_id := 2
SELECT /* cursor_demo_bind */ id, nhom
FROM cursor_demo
WHERE id = :p_id;

EXEC :p_id := 3
SELECT /* cursor_demo_bind */ id, nhom
FROM cursor_demo
WHERE id = :p_id;
\`\`\`

Phần comment và SQL text của ba \`SELECT\` **giống nhau**; chỉ giá trị của \`p_id\` thay đổi. Tùy phiên và cách công cụ chuẩn bị/cached statement, Oracle có thể tái sử dụng child cursor ở shared pool hoặc cả cursor trong session.

### 8.4. Xem các child cursor bằng \`V$SQL\`

Khi có quyền truy cập dynamic performance view:

\`\`\`sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       parse_calls,
       loads,
       invalidations,
       is_bind_sensitive,
       is_bind_aware
FROM v$sql
WHERE sql_text LIKE 'SELECT /* cursor_demo_bind */%'
ORDER BY sql_id, child_number;
\`\`\`

Ý nghĩa chính:

| Cột | Cách đọc |
| --- | --- |
| \`EXECUTIONS\` | Số lần SQL được thực thi ghi nhận cho child đó |
| \`PARSE_CALLS\` | Số lần parse call được ghi nhận; không đồng nghĩa toàn bộ đều là hard parse |
| \`LOADS\` | Số lần cursor được load/reload theo cơ chế thống kê Oracle |
| \`INVALIDATIONS\` | Số lần cursor bị đánh dấu không còn hợp lệ |
| \`IS_BIND_SENSITIVE\`, \`IS_BIND_AWARE\` | Gợi ý trạng thái liên quan đến bind và adaptive cursor sharing |
| \`PLAN_HASH_VALUE\` | Dấu hiệu để so sánh plan giữa các child |

Không mặc nhiên kỳ vọng \`PARSE_CALLS = EXECUTIONS\` hay \`PARSE_CALLS = 1\`. Kết quả chịu ảnh hưởng của thời điểm quan sát, cursor caching, số phiên và phiên bản driver/công cụ.

Xem tổng hợp parent:

\`\`\`sql
SELECT sql_id,
       version_count,
       executions,
       parse_calls,
       loads,
       invalidations
FROM v$sqlarea
WHERE sql_text LIKE 'SELECT /* cursor_demo_bind */%';
\`\`\`

Nếu \`VERSION_COUNT\` lớn hơn 1, hãy tìm nguyên nhân cụ thể thay vì giả định mọi child đều dư thừa.

### 8.5. Tìm lý do child cursor không chia sẻ được

\`V$SQL_SHARED_CURSOR\` có các cột chỉ dấu về khả năng chia sẻ cursor. Có thể bắt đầu bằng truy vấn:

\`\`\`sql
SELECT *
FROM v$sql_shared_cursor
WHERE sql_id = :sql_id
ORDER BY child_number;
\`\`\`

Tham số \`:sql_id\` là SQL_ID tìm được từ \`V$SQL\` hoặc \`V$SQLAREA\`. Các cột lý do, kiểu dữ liệu và cách hiển thị có thể khác nhau theo phiên bản Oracle. Thường cần chú ý những nhóm nguyên nhân như \`BIND_MISMATCH\`, \`OPTIMIZER_MISMATCH\` hoặc vấn đề bối cảnh truy cập, rồi đối chiếu với cấu hình phiên và metadata bind.

Một chỉ dấu bằng \`Y\` trong một cột không thay thế việc phân tích thời điểm child hình thành, số lần thực thi và tác động lên hiệu năng. Cũng không nên cố sửa mọi dấu hiệu khác biệt nếu Oracle tạo child hợp lệ để phục vụ plan phù hợp hơn.

### 8.6. Phân biệt tổng parse với hard parse bằng session statistics

Trong Oracle có các thống kê như \`parse count (total)\`, \`parse count (hard)\`, \`session cursor cache hits\` và \`execute count\`. Với quyền xem thống kê của chính phiên:

\`\`\`sql
SELECT n.name,
       s.value
FROM v$sesstat s
JOIN v$statname n
  ON n.statistic# = s.statistic#
WHERE s.sid = TO_NUMBER(SYS_CONTEXT('USERENV', 'SID'))
  AND n.name IN (
      'parse count (total)',
      'parse count (hard)',
      'session cursor cache hits',
      'execute count'
  )
ORDER BY n.name;
\`\`\`

Để đánh giá, ghi số liệu trước/sau một workload **được kiểm soát**, rồi nhìn vào **chênh lệch**. Truy vấn đo thống kê và các lệnh hỗ trợ cũng có thể đóng góp vào counters, nên không nên diễn giải chênh lệch một cách tuyệt đối khi chỉ thực hiện vài câu SQL thủ công. Với một bài đo nghiêm túc hơn, dùng workload nhiều lần và phương pháp quan sát nhất quán, tránh chạy lẫn truy vấn hoặc tác vụ khác.

Những thống kê này giúp trả lời:

- Tổng số lần Oracle nhận yêu cầu parse có tăng nhanh so với nhu cầu của ứng dụng không?
- Tỷ lệ hard parse có đáng kể khi workload chỉ gồm một số mẫu SQL lặp đi lặp lại không?
- Cache cursor theo session có đang được tận dụng không?
- Thay đổi cách bind và tái sử dụng statement có làm giảm lượng parse không?

**Không dùng một tỷ lệ cố định làm “chuẩn tốt cho mọi hệ thống”.** Một workload OLTP chạy cùng SQL hàng triệu lần khác hẳn một hệ thống báo cáo chạy hàng nghìn câu truy vấn duy nhất mỗi ngày.

## 9. Những yếu tố khiến cursor không còn được tái sử dụng

### 9.1. SQL text thay đổi liên tục

Chỉ khác khoảng trắng, comment, tên schema, literal hay cách dựng điều kiện cũng có thể làm Oracle xem là SQL text khác trong cơ chế cursor sharing chính xác. Ví dụ code tạo \`IN (1,2)\`, rồi \`IN (1,2,3)\` từ chuỗi sẽ làm hình dạng SQL thay đổi.

Giải pháp phụ thuộc nhu cầu: sử dụng bind, giữ mẫu SQL ổn định, chọn cấu trúc truy vấn thích hợp cho các danh sách tham số; không thay thế mọi trường hợp bằng một câu SQL chung quá phức tạp chỉ để giảm số SQL_ID.

### 9.2. Không tương thích kiểu bind hoặc optimizer environment

Cùng câu SQL \`WHERE id = :id\` nhưng client lúc truyền số, lúc truyền chuỗi có thể tạo khác biệt về chuyển kiểu hoặc chia sẻ child. Sự không thống nhất các thiết lập session như NLS hoặc optimizer cũng có thể ảnh hưởng khả năng chia sẻ trong những tình huống nhất định.

**Giữ cách bind có kiểu dữ liệu rõ ràng**, thống nhất giữa các code path và framework. Đồng thời kiểm tra metadata thực tế trước khi cho rằng vấn đề chỉ do “cùng SQL mà có nhiều child”.

### 9.3. Invalidation do thay đổi đối tượng hoặc thống kê

Thay đổi cấu trúc bảng/chỉ mục, một số hoạt động quản trị, thay đổi đối tượng phụ thuộc hoặc việc cập nhật thống kê theo cách có ảnh hưởng đến cursor có thể khiến cursor cần được biên dịch/tối ưu lại. Khi đó hard parse sau invalidation có thể hoàn toàn hợp lý.

Không nên cố ngăn mọi invalidation; hãy triển khai DDL/migration, thống kê và thay đổi ứng dụng có kiểm soát, đặc biệt với hệ thống có lưu lượng lớn.

### 9.4. Áp lực bộ nhớ shared pool

Library cache dùng bộ nhớ có giới hạn. Khi nhiều SQL text khác biệt và đối tượng dùng chung chiếm tài nguyên, một số cursor có thể bị loại bỏ khỏi cache; lần thực thi tiếp theo có thể cần hard parse lại.

Trước khi tăng kích thước shared pool, hãy xem **số lượng SQL text**, bind usage, child cursor, hiện tượng invalidation, tác động CPU và các wait event liên quan. Việc tăng bộ nhớ không sửa được nguyên nhân ứng dụng tạo hàng nghìn câu SQL gần giống nhau.

### 9.5. Tranh chấp trong library cache

Các session cần phối hợp khi truy cập, thay đổi hoặc pin các cấu trúc dùng chung. Trong một số workload, chờ đợi liên quan đến **library cache lock**, **library cache pin** hoặc cơ chế **cursor mutex** có thể xuất hiện. Nguyên nhân có thể là DDL tác động đối tượng đang dùng, parse quá nhiều, nhiều phiên tranh chấp cùng cursor, hoặc vấn đề tương thích/phiên bản.

Không nên suy luận “library cache wait = thiếu RAM” hay “mọi shared cursor đều tạo tranh chấp”. Cần xem wait event cụ thể, session liên quan, SQL_ID, thời điểm thay đổi schema và đặc điểm tải trước khi xử lý.

## 10. Ba tầng cache thường bị nhầm với nhau

Trong ứng dụng Java kết nối Oracle, cần phân biệt:

| Tầng | Phạm vi | Chứa gì? | Tác dụng |
| --- | --- | --- | --- |
| **JDBC statement cache / PreparedStatement reuse** | Phía ứng dụng/driver và theo connection vật lý | Thông tin statement do driver giữ, có thể gắn với server cursor | Giảm số lần prepare/mở statement và chi phí giao tiếp |
| **Session cursor cache** | Session Oracle | Cursor đã dùng gần đây có thể tái sử dụng trong phiên | Giảm công việc tìm/mở cursor lặp lại |
| **Library cache / shared cursor** | Shared pool, nhiều session | SQL shared cursor, PL/SQL và metadata dùng chung | Giảm hard parse cho nhiều session tương thích |

Ví dụ, ứng dụng Java có connection pool 10 connection vật lý. Cùng một mẫu SQL có thể được nhiều connection sử dụng; **library cache** giúp chia sẻ cấu trúc SQL ở cấp instance, trong khi **statement cache của driver** và **session cursor cache** vẫn có phạm vi riêng theo từng connection/Oracle session.

### \`SESSION_CACHED_CURSORS\` và \`OPEN_CURSORS\`

- \`SESSION_CACHED_CURSORS\` là tham số liên quan đến số cursor mà session có thể cache để giảm parse lặp lại. Giá trị thích hợp phụ thuộc workload và cách sử dụng statement.
- \`OPEN_CURSORS\` giới hạn số cursor mà một session có thể mở. **\`ORA-01000: maximum open cursors exceeded\`** thường đòi hỏi xem lại cách quản lý \`Statement\`/\`ResultSet\`, cache của driver và số cursor thực tế; chỉ tăng tham số có thể che giấu việc không đóng tài nguyên.

Trong JDBC, \`try-with-resources\` giúp đóng \`ResultSet\`, \`Statement\` và trả \`Connection\` về pool theo cơ chế \`DataSource\`. Nhưng việc đóng ở cấp API **không nhất thiết xóa ngay mọi cấu trúc cursor ở cả ba tầng cache**; các cache có thể chủ động giữ lại tài nguyên cho lần sử dụng sau, trong giới hạn được cấu hình.

Không nên bật mọi loại statement caching với kích thước lớn mà không đo lường. Hãy chọn cơ chế do driver/framework hỗ trợ, kiểm soát mức tiêu thụ cursor và đánh giá khả năng tái sử dụng theo mô hình ứng dụng thực tế.

## 11. \`CURSOR_SHARING\`: không phải công tắc sửa mọi hard parse

Oracle có tham số \`CURSOR_SHARING\` ảnh hưởng đến cách một số SQL text chứa literal có thể được chia sẻ. Hai chế độ thường được nhắc đến:

- **\`EXACT\`**: chia sẻ dựa trên SQL text và các điều kiện tương thích; ứng dụng nên tự dùng bind variable khi muốn lặp cùng mẫu SQL.
- **\`FORCE\`**: Oracle có thể thay thế một số literal bằng bind do hệ thống tạo, làm tăng cơ hội chia sẻ cursor giữa những câu có cấu trúc tương đồng.

Không nên coi \`FORCE\` là thay thế lâu dài cho việc sử dụng \`PreparedStatement\` đúng cách. Nó không sửa SQL injection trong code ghép chuỗi, không bảo đảm mọi SQL được chia sẻ, và có thể ảnh hưởng ước lượng cardinality/plan đối với truy vấn nhạy với literal. Các ngoại lệ cú pháp và ngữ nghĩa phụ thuộc phiên bản Oracle.

Đổi tham số ở cấp hệ thống có thể ảnh hưởng nhiều ứng dụng. Đây là quyết định cần kiểm chứng bằng workload và kế hoạch triển khai, không phải mẹo tối ưu mặc định trong một bài tập.

## 12. Từ dấu hiệu hiệu năng đến hành động

Khi nghi ngờ chi phí parse cao, có thể tiến hành theo trình tự:

1. **Xác định hiện tượng**: CPU cao, throughput giảm, latency tăng hoặc các wait event liên quan library cache/mutex.
2. **Đo số lần parse**: xem \`parse count (hard)\`, \`parse count (total)\`, \`execute count\` trong phạm vi session/workload phù hợp, cùng thống kê SQL cụ thể.
3. **Tìm mẫu SQL phân mảnh**: nhiều câu chỉ khác literal, tên đối tượng hoặc đoạn SQL động?
4. **Quan sát các child cursor**: nếu \`VERSION_COUNT\` cao, kiểm tra \`V$SQL_SHARED_CURSOR\` và metadata bind/optimizer.
5. **Kiểm tra invalidation và áp lực cache**: gần đây có DDL, cập nhật thống kê, thay đổi phiên hoặc thiếu bộ nhớ dùng chung?
6. **Sửa nguyên nhân tại nguồn**: dùng bind, tái sử dụng statement, ổn định kiểu dữ liệu, quản lý connection và giảm SQL text sinh không cần thiết.
7. **Đo lại cùng workload**: xem lượng hard parse, CPU, thời gian phản hồi và chất lượng execution plan có cải thiện không.

Một số view hỗ trợ quan sát như \`V$SQL\`, \`V$SQLAREA\`, \`V$SQL_SHARED_CURSOR\`, \`V$SESSTAT\`, \`V$STATNAME\` hoặc \`V$LIBRARYCACHE\`. Các công cụ chẩn đoán sâu hơn có thể yêu cầu quyền truy cập và giấy phép tương ứng; chỉ dùng khả năng được phép trong hệ thống của mình.

### Ba ví dụ chẩn đoán

**Trường hợp A — nhiều SQL_ID khác nhau, mỗi câu chỉ chạy một vài lần.** Ứng dụng có thể đang ghép giá trị literal thành SQL text. Bắt đầu từ code tạo câu SQL, chuyển dữ liệu đầu vào thành bind variable và đo lại.

**Trường hợp B — một SQL_ID có nhiều child cursor.** Kiểm tra \`V$SQL_SHARED_CURSOR\`, kiểu bind, khác biệt cấu hình session và khả năng adaptive cursor sharing. Không gộp child bằng mọi giá nếu các plan khác nhau là cần thiết.

**Trường hợp C — hard parse tăng sau deployment hoặc DDL.** Có thể do invalidation hoặc cache cần làm nóng lại sau thay đổi. Phân biệt đợt tăng tạm thời với hard parse kéo dài qua toàn bộ thời gian chạy.

## 13. Câu hỏi tự luyện

1. Hai câu \`SELECT ... WHERE id = 1\` và \`SELECT ... WHERE id = 2\` được tạo bằng nối chuỗi trong Java có điểm gì khác so với một \`PreparedStatement\` với \`WHERE id = ?\`?
2. Một SQL có \`EXECUTIONS = 10_000\` và \`PARSE_CALLS = 50\` có nhất thiết phải hard parse 50 lần không? Vì sao?
3. Nếu cùng một \`SQL_ID\` có hai \`CHILD_NUMBER\`, có thể khẳng định execution plan của hai child khác nhau không?
4. Vì sao bind variable vừa giảm phân mảnh SQL text vừa có thể dẫn đến nhiều child cursor trong một số truy vấn nhạy với giá trị bind?
5. Tại sao dữ liệu trong database buffer cache không đồng nghĩa SQL cursor đã nằm trong library cache, và ngược lại?
6. Khi gặp \`ORA-01000\`, vì sao cần kiểm tra cách ứng dụng đóng JDBC statement và cursor cache trước khi chỉ tăng \`OPEN_CURSORS\`?
7. Một câu SQL mới xuất hiện sau khi thêm index cần hard parse. Đây có nhất thiết là một vấn đề hiệu năng không? Thông tin nào cần xem thêm?

## 14. Tổng hợp cách hiểu đúng

**Hard parse** là công việc cần thiết để tạo thông tin thực thi khi chưa có child cursor dùng được; **soft parse** tái sử dụng shared cursor đã có và tránh phần lớn chi phí tối ưu hóa nhưng vẫn cần tài nguyên. **Library cache** nằm trong shared pool, giúp các session sử dụng lại cấu trúc SQL/PLSQL; **parent/child cursor** giải thích vì sao cùng SQL text vẫn có nhiều phiên bản thực thi tương thích với các bối cảnh khác nhau.

Đối với ứng dụng Java, nguyên tắc thực hành quan trọng nhất là **giữ SQL text ổn định khi nghiệp vụ giống nhau, truyền dữ liệu bằng bind variable, quản lý statement/connection đúng vòng đời và quan sát số liệu trước khi điều chỉnh cache**. Mục đích không phải biến mọi parse thành zero, mà là để Oracle dành tài nguyên cho công việc thực thi cần thiết và có execution plan phù hợp với dữ liệu thực tế.
