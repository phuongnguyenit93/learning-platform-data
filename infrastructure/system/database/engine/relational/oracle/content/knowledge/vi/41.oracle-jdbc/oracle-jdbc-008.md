# Ánh xạ DATE/TIMESTAMP sang kiểu java.time và xử lý múi giờ

Khi Java truy cập Oracle Database qua JDBC, việc ánh xạ ngày giờ cần được thiết kế theo ý nghĩa của dữ liệu, không chỉ theo tên kiểu SQL. Oracle có nhiều kiểu lưu ngày giờ với độ chính xác và ngữ nghĩa múi giờ khác nhau; Java cũng có nhiều kiểu trong gói java.time. Nếu chọn sai kiểu, ứng dụng có thể làm mất phần giờ, mất độ chính xác phần giây, thay đổi thời điểm khi chuyển timezone hoặc hiển thị khác nhau giữa các môi trường.

Các nguyên tắc quan trọng:

- Oracle DATE lưu ngày và giờ đến giây, không lưu múi giờ. Dù tên là DATE, nó không chỉ chứa ngày lịch.
- Oracle TIMESTAMP lưu ngày và giờ với phần giây thập phân, không lưu múi giờ.
- TIMESTAMP WITH TIME ZONE lưu ngày giờ kèm thông tin múi giờ/độ lệch, phù hợp khi cần xác định thời điểm cùng offset hoặc vùng thời gian.
- TIMESTAMP WITH LOCAL TIME ZONE chuẩn hóa dữ liệu theo database time zone khi lưu và hiển thị theo session time zone khi đọc; bản thân giá trị không giữ nguyên múi giờ ban đầu của từng hàng.
- LocalDate phù hợp với ngày lịch không có giờ; LocalDateTime phù hợp với ngày giờ không có timezone; OffsetDateTime biểu diễn ngày giờ kèm offset; Instant biểu diễn một thời điểm tuyệt đối trên timeline.
- Phải kiểm soát session time zone của từng kết nối JDBC, đặc biệt khi sử dụng TIMESTAMP WITH LOCAL TIME ZONE hoặc các hàm SQL phụ thuộc session timezone.

## 1. Mô hình ngày giờ ở Oracle và Java

### 1.1. Oracle DATE không giống java.sql.Date

Oracle DATE chứa các thành phần năm, tháng, ngày, giờ, phút và giây. Độ chính xác phần giây là một giây; nó không chứa fractional seconds và không lưu timezone.

Ví dụ một giá trị Oracle DATE có thể là:

    2026-11-14 21:19:35

Nó có cả ngày và giờ. Vì vậy, ánh xạ Oracle DATE sang java.sql.Date có thể làm mất thông tin giờ, phút và giây do java.sql.Date được thiết kế theo ngữ nghĩa SQL DATE chỉ có ngày. Khi cần giữ nguyên toàn bộ giá trị Oracle DATE, thường dùng java.sql.Timestamp ở API JDBC cũ hoặc LocalDateTime ở API java.time tương ứng.

Không nên suy luận từ tên DATE rằng dữ liệu trong cột chắc chắn chỉ có ngày. Hãy kiểm tra hợp đồng dữ liệu và giá trị thật của cột trước khi đổi mapping.

### 1.2. Oracle TIMESTAMP

Oracle TIMESTAMP lưu năm, tháng, ngày, giờ, phút, giây và phần giây thập phân. Độ chính xác phần giây được cấu hình từ 0 đến 9 chữ số; mặc định thường là 6.

Ví dụ:

    TIMESTAMP(6)
    2026-11-14 21:19:35.123456

TIMESTAMP không chứa timezone hoặc offset. Giá trị chỉ là ngày giờ địa phương theo quy ước của ứng dụng. Nếu cùng một TIMESTAMP được diễn giải ở hai múi giờ khác nhau, database không có đủ thông tin để biết nó đại diện cho cùng một thời điểm hay hai thời điểm khác nhau.

### 1.3. TIMESTAMP WITH TIME ZONE

TIMESTAMP WITH TIME ZONE (TSTZ) lưu ngày giờ cùng thông tin múi giờ, có thể là offset hoặc timezone region. Ví dụ:

    2026-11-14 21:19:35.123456 +07:00

hoặc giá trị gắn với vùng thời gian như Asia/Ho_Chi_Minh.

Kiểu này phù hợp khi cần giữ thông tin offset/timezone của giá trị được nhập và xác định thời điểm tương ứng. Oracle có thể lưu thông tin vùng thời gian nếu giá trị được cung cấp bằng region; cách driver Java biểu diễn giá trị khi đọc cần được kiểm tra theo phiên bản.

Java OffsetDateTime là kiểu java.time tự nhiên để biểu diễn ngày giờ kèm offset. Khi chuyển sang Instant, ứng dụng giữ được thời điểm tuyệt đối nhưng không giữ được tên timezone region như Asia/Ho_Chi_Minh. Nếu nghiệp vụ cần lưu cả vùng thời gian do người dùng chọn, hãy lưu ZoneId riêng hoặc thiết kế một cột bổ sung cho region ID.

### 1.4. TIMESTAMP WITH LOCAL TIME ZONE

TIMESTAMP WITH LOCAL TIME ZONE (TSLTZ) có hành vi khác TSTZ:

- Oracle chuẩn hóa giá trị về database time zone khi lưu.
- Khi truy vấn, Oracle chuyển giá trị sang session time zone của session hiện tại.
- Giá trị được trả về không giữ lại timezone/offset ban đầu được nhập cho từng hàng.

Ví dụ cùng một thời điểm có thể được hiển thị khác nhau khi hai session có SESSIONTIMEZONE khác nhau. Đây là hành vi có chủ đích của kiểu dữ liệu.

TSLTZ hữu ích khi ứng dụng muốn lưu thời điểm và hiển thị theo timezone của session. Tuy nhiên, vì timezone ban đầu không được giữ theo từng hàng, kiểu này không phù hợp nếu nghiệp vụ phải biết người dùng đã nhập thời gian ở vùng nào.

### 1.5. Bảng đối chiếu kiểu SQL và java.time

| Oracle SQL type | Nội dung | Java type thường phù hợp | Lưu ý |
|---|---|---|---|
| DATE | Ngày và giờ đến giây, không timezone | LocalDateTime | Tránh java.sql.Date nếu cần giữ phần giờ |
| TIMESTAMP(p) | Ngày giờ với fractional seconds, không timezone | LocalDateTime | Không tự xác định instant nếu không có timezone |
| TIMESTAMP WITH TIME ZONE | Ngày giờ kèm offset/region | OffsetDateTime | Chuyển sang Instant khi cần thời điểm UTC; lưu ZoneId riêng nếu cần giữ tên vùng |
| TIMESTAMP WITH LOCAL TIME ZONE | Thời điểm chuẩn hóa theo DBTIMEZONE, hiển thị theo SESSIONTIMEZONE | LocalDateTime theo session timezone hoặc mapping driver phù hợp | Cần cố định session timezone; không giữ timezone nhập ban đầu |
| DATE chỉ dùng cho ngày lịch | Oracle vẫn có thành phần giờ | LocalDate theo hợp đồng ứng dụng | Phải bảo đảm phần giờ luôn là nửa đêm và không làm mất dữ liệu |

Đây là hướng chọn kiểu theo ý nghĩa dữ liệu. Khả năng getObject/setObject trực tiếp phụ thuộc phiên bản JDBC driver Oracle và kiểu cột cụ thể; hãy kiểm thử trên ojdbc đang triển khai.

## 2. Chọn kiểu Java theo ý nghĩa nghiệp vụ

### 2.1. LocalDate: ngày lịch, không có giờ

Dùng LocalDate cho các khái niệm như ngày sinh, ngày hiệu lực theo lịch, ngày nghỉ hoặc ngày chốt sổ khi giờ trong ngày không có ý nghĩa.

Ví dụ:

    LocalDate dueDate = LocalDate.of(2026, 12, 31);

Nếu cột Oracle là DATE nhưng được dùng như ngày lịch, cần thống nhất quy tắc rằng phần giờ luôn là 00:00:00. Có thể kiểm tra dữ liệu hiện có:

    SELECT COUNT(*) AS rows_with_time
    FROM contract
    WHERE start_date <> TRUNC(start_date);

Nếu kết quả lớn hơn 0, cột đang chứa thành phần giờ; chuyển sang LocalDate có thể làm mất thông tin. Không nên thay đổi mapping trước khi xác định dữ liệu có thực sự chỉ mang ngữ nghĩa ngày lịch hay không.

### 2.2. LocalDateTime: ngày giờ không gắn timezone

Dùng LocalDateTime khi nghiệp vụ lưu một ngày giờ theo lịch mà không gắn với vùng thời gian cụ thể, ví dụ giờ mở cửa của cửa hàng, giờ hẹn theo lịch địa phương hoặc thời điểm nghiệp vụ trong một hệ thống có quy ước timezone riêng.

LocalDateTime không phải một instant. Giá trị 2026-11-14T09:00 không thể xác định là thời điểm UTC nào nếu không biết timezone hoặc offset cần áp dụng.

Oracle DATE và TIMESTAMP không có timezone thường được ánh xạ sang LocalDateTime để giữ ngày giờ mà không tự ý áp dụng timezone.

### 2.3. Instant: thời điểm tuyệt đối

Instant biểu diễn một điểm trên timeline UTC. Dùng nó cho thời điểm sự kiện, log nghiệp vụ, thời gian tạo record hoặc event timestamp khi cần so sánh giữa các hệ thống ở nhiều múi giờ.

Ví dụ:

    Instant createdAt = Instant.now();

Nếu database lưu bằng TIMESTAMP không timezone, ứng dụng phải có quy ước rõ ràng rằng các giá trị được ghi theo UTC. Tên cột như CREATED_AT_UTC có thể giúp làm rõ hợp đồng, nhưng tên cột không tự chuyển đổi timezone. Cả writer và reader phải tuân thủ cùng quy ước.

Nếu cần database giữ rõ timezone/offset cùng giá trị, cân nhắc TIMESTAMP WITH TIME ZONE và OffsetDateTime thay vì dựa vào quy ước ngầm trên TIMESTAMP.

### 2.4. OffsetDateTime và ZonedDateTime

OffsetDateTime chứa ngày giờ cùng offset như +07:00. Nó đủ để xác định một instant và giữ offset của giá trị.

ZonedDateTime còn chứa ZoneId như Asia/Ho_Chi_Minh hoặc Europe/Paris, bao gồm quy tắc DST theo dữ liệu timezone của Java. Oracle TSTZ có thể chứa timezone region, nhưng mapping JDBC sang OffsetDateTime thường biểu diễn offset; không nên giả định tên region sẽ luôn được giữ nguyên qua chuyển đổi.

Nếu yêu cầu nghiệp vụ cần biết timezone region do người dùng chọn, lưu riêng ZoneId dạng chuỗi có kiểm soát. Ví dụ:

    event_time       TIMESTAMP WITH TIME ZONE
    event_zone_id    VARCHAR2(64)

Khi đọc, có thể dựng ZonedDateTime từ instant/offset phù hợp và ZoneId đã lưu. Cần xác định rõ ZoneId có được chuẩn hóa theo danh sách region được phép hay không.

## 3. Khác biệt giữa instant và local wall-clock time

Một lỗi thiết kế thường gặp là dùng LocalDateTime cho mọi cột ngày giờ. LocalDateTime chỉ là các thành phần lịch; nó không có timezone. Instant là thời điểm tuyệt đối; OffsetDateTime có offset; ZonedDateTime có quy tắc vùng thời gian.

Ví dụ cùng một thời điểm:

    Instant:
      2026-11-14T14:19:00Z

    Asia/Ho_Chi_Minh:
      2026-11-14T21:19:00+07:00

Hai biểu diễn trên cùng chỉ một instant. Nếu bỏ offset và chỉ lưu LocalDateTime 21:19, hệ thống không còn biết đó là 14:19Z hay một thời điểm khác ở vùng timezone khác.

### 3.1. Khi nào nên lưu UTC?

Với event timestamp cần so sánh xuyên hệ thống, lưu thời điểm chuẩn hóa UTC thường giúp giảm mơ hồ. Có thể dùng:

- TIMESTAMP WITH TIME ZONE để lưu giá trị có offset và chuyển đổi rõ ràng.
- TIMESTAMP với quy ước mọi giá trị được ghi/đọc như UTC, đồng thời đặt tên và tài liệu cột rõ ràng.
- Một mô hình lưu epoch/instant riêng nếu có yêu cầu đặc thù, nhưng cần xem xét độ chính xác và khả năng truy vấn SQL.

Dù chọn cách nào, phải thống nhất từ API, Java domain, JDBC, database và báo cáo. Không để một service ghi local time trong khi service khác đọc như UTC.

### 3.2. Khi nào giữ local time?

Một số dữ liệu là giờ địa phương theo nghiệp vụ, không phải instant:

- Cửa hàng mở cửa lúc 09:00 theo giờ địa phương.
- Cuộc hẹn diễn ra lúc 10:30 tại một địa điểm.
- Lịch chạy batch mỗi ngày lúc 02:00 ở một vùng thời gian.
- Ngày chốt sổ là ngày lịch tại quốc gia vận hành.

Trong các trường hợp này, cần lưu ZoneId hoặc quy tắc timezone bên cạnh LocalDate/LocalTime/LocalDateTime nếu hệ thống phải chuyển đổi sang instant hoặc xử lý DST.

## 4. JDBC 4.2 và java.time

JDBC 4.2 bổ sung khả năng làm việc với các kiểu java.time thông qua PreparedStatement.setObject và ResultSet.getObject có target type. Oracle JDBC driver hỗ trợ các mapping cụ thể tùy phiên bản. Hãy dùng driver tương thích với JDK và database, rồi kiểm tra trực tiếp các kiểu DATE, TIMESTAMP, TSTZ và TSLTZ đang dùng.

### 4.1. Ghi LocalDateTime vào TIMESTAMP

Ví dụ cột:

    CREATE TABLE audit_event (
        event_id NUMBER PRIMARY KEY,
        occurred_at TIMESTAMP(6) NOT NULL
    );

Java:

    LocalDateTime occurredAt =
        LocalDateTime.of(2026, 11, 14, 21, 19, 35, 123456000);

    String sql =
        "INSERT INTO audit_event (event_id, occurred_at) VALUES (?, ?)";

    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        ps.setLong(1, 1001L);
        ps.setObject(2, occurredAt);
        ps.executeUpdate();
    }

Đọc:

    String sql =
        "SELECT occurred_at FROM audit_event WHERE event_id = ?";

    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        ps.setLong(1, 1001L);

        try (ResultSet rs = ps.executeQuery()) {
            if (rs.next()) {
                LocalDateTime value =
                    rs.getObject("occurred_at", LocalDateTime.class);
            }
        }
    }

Cách này giữ ngữ nghĩa local date-time. Nó không tự chuyển sang UTC vì cột TIMESTAMP không chứa timezone.

### 4.2. Ghi LocalDate vào cột ngày lịch

Nếu cột được định nghĩa là Oracle DATE nhưng hợp đồng dữ liệu chỉ là ngày lịch:

    LocalDate birthDate = LocalDate.of(1990, 5, 20);

Có thể dùng JDBC 4.2 setObject với LocalDate nếu driver hỗ trợ mapping tương ứng:

    ps.setObject(1, birthDate);

Khi đọc:

    LocalDate value = rs.getObject("birth_date", LocalDate.class);

Vì Oracle DATE có cả thành phần giờ, cần bảo đảm cột chỉ chứa nửa đêm hoặc quy tắc chuyển đổi có chủ đích. Nếu dữ liệu có giờ, hãy dùng LocalDateTime để tránh cắt bỏ thông tin.

### 4.3. TIMESTAMP WITH TIME ZONE và OffsetDateTime

DDL:

    CREATE TABLE meeting (
        meeting_id NUMBER PRIMARY KEY,
        starts_at TIMESTAMP(6) WITH TIME ZONE NOT NULL
    );

Java:

    OffsetDateTime startsAt =
        OffsetDateTime.parse("2026-11-14T21:19:35.123456+07:00");

    try (PreparedStatement ps = connection.prepareStatement(
            "INSERT INTO meeting (meeting_id, starts_at) VALUES (?, ?)")) {
        ps.setLong(1, 2001L);
        ps.setObject(2, startsAt);
        ps.executeUpdate();
    }

Đọc:

    try (PreparedStatement ps = connection.prepareStatement(
            "SELECT starts_at FROM meeting WHERE meeting_id = ?")) {
        ps.setLong(1, 2001L);

        try (ResultSet rs = ps.executeQuery()) {
            if (rs.next()) {
                OffsetDateTime value =
                    rs.getObject("starts_at", OffsetDateTime.class);

                Instant instant = value.toInstant();
            }
        }
    }

Kiểm tra driver có hỗ trợ mapping TSTZ trực tiếp tới OffsetDateTime hay không. Nếu driver cũ hoặc mapping không tương thích, dùng Oracle JDBC API được tài liệu hóa cho phiên bản đó hoặc đọc qua kiểu tương thích rồi chuyển đổi có kiểm soát.

OffsetDateTime giữ offset, nhưng không nhất thiết giữ nguyên tên timezone region. Nếu cần giữ region, lưu ZoneId riêng.

### 4.4. Dùng Instant

Instant phù hợp cho event timestamp. Có hai hướng thiết kế phổ biến:

1. Lưu vào TIMESTAMP WITH TIME ZONE và chuyển Instant thành OffsetDateTime ở UTC.
2. Lưu vào TIMESTAMP với quy ước UTC được áp dụng nhất quán.

Ví dụ chuyển sang UTC OffsetDateTime:

    Instant instant = Instant.now();
    OffsetDateTime utcValue = instant.atOffset(ZoneOffset.UTC);

    ps.setObject(1, utcValue);

Khi đọc TSTZ:

    OffsetDateTime offsetValue =
        rs.getObject("occurred_at", OffsetDateTime.class);

    Instant occurredAt = offsetValue.toInstant();

Nếu dùng TIMESTAMP thuần theo quy ước UTC, cần chuyển LocalDateTime sang Instant bằng cách gắn ZoneOffset.UTC:

    LocalDateTime storedUtc =
        rs.getObject("occurred_at", LocalDateTime.class);

    Instant occurredAt = storedUtc.toInstant(ZoneOffset.UTC);

Không dùng ZoneId.systemDefault() để diễn giải một TIMESTAMP UTC. Kết quả khi đó sẽ phụ thuộc timezone của máy chạy ứng dụng.

### 4.5. Fallback cho driver chưa hỗ trợ mapping trực tiếp

Với API JDBC cũ hoặc driver chưa hỗ trợ getObject/setObject cho java.time như mong muốn, có thể dùng java.sql.Timestamp làm cầu nối cho DATE/TIMESTAMP không timezone:

    Timestamp timestamp = rs.getTimestamp("created_at");
    LocalDateTime value = timestamp.toLocalDateTime();

Ghi:

    Timestamp timestamp = Timestamp.valueOf(value);
    ps.setTimestamp(1, timestamp);

Với Oracle DATE có thành phần giờ, getTimestamp thường là lựa chọn an toàn hơn getDate nếu cần giữ giờ/phút/giây. Cần kiểm tra hành vi của driver cụ thể và tránh các overload có Calendar không thống nhất giữa writer và reader.

Đối với TSTZ/TSLTZ, không nên dùng Timestamp như thể nó giữ được timezone gốc. Timestamp không mang offset hay ZoneId. Nếu phải dùng API cũ, cần dùng Oracle JDBC type/API hoặc biểu diễn SQL có timezone rõ ràng và chuyển đổi tại một ranh giới được kiểm thử.

## 5. Vì sao java.sql.Date và java.util.Date dễ gây lỗi?

### 5.1. java.sql.Date

java.sql.Date đại diện cho SQL DATE theo hợp đồng JDBC và không giữ thành phần thời gian theo cách mà Oracle DATE có. Khi cột Oracle DATE đang chứa 14:30:00, đọc qua java.sql.Date có thể làm mất phần giờ.

Chỉ dùng java.sql.Date khi nghiệp vụ thực sự chỉ cần ngày lịch và dữ liệu đã tuân thủ quy tắc không có giờ. Với ứng dụng mới, ưu tiên LocalDate cho ngày lịch.

### 5.2. java.sql.Timestamp

java.sql.Timestamp giữ phần giây thập phân nhưng không mang timezone. Nó phù hợp với cầu nối JDBC legacy cho TIMESTAMP/DATE có giờ, nhưng không biểu diễn được offset của TSTZ.

Các chuyển đổi:

    LocalDateTime local = timestamp.toLocalDateTime();
    Timestamp timestamp2 = Timestamp.valueOf(local);

Hai thao tác này chuyển thành phần lịch mà không tự thêm timezone.

    Instant instant = timestamp.toInstant();
    Timestamp timestamp3 = Timestamp.from(instant);

Hai thao tác này dùng instant và có tương tác với quy ước timezone ở các API liên quan. Không trộn hai nhóm conversion một cách tùy tiện.

### 5.3. java.util.Date

java.util.Date biểu diễn thời điểm theo milliseconds từ epoch, không lưu timezone region. Khi format thành chuỗi, kết quả phụ thuộc timezone formatter hoặc timezone mặc định của JVM. Nó không phù hợp làm kiểu domain chính trong code mới nếu có thể dùng Instant, LocalDate, LocalDateTime hoặc OffsetDateTime.

### 5.4. Không truyền ngày giờ qua String nếu có thể bind typed value

Cách dễ gây lỗi:

    String sql =
        "INSERT INTO event_log(created_at) VALUES (TO_DATE('" +
        userInput + "', 'YYYY-MM-DD HH24:MI:SS'))";

Cách này dễ gặp lỗi format, NLS, SQL injection và sai timezone. Hãy parse input thành java.time, validate, rồi bind bằng PreparedStatement.setObject hoặc API JDBC phù hợp.

## 6. Oracle timezone: DBTIMEZONE và SESSIONTIMEZONE

Oracle có hai khái niệm quan trọng:

- DBTIMEZONE: timezone của database, liên quan đến cách Oracle xử lý và chuẩn hóa TIMESTAMP WITH LOCAL TIME ZONE.
- SESSIONTIMEZONE: timezone của session hiện tại, ảnh hưởng cách hiển thị TSLTZ và các hàm ngày giờ phụ thuộc session.

Kiểm tra:

    SELECT DBTIMEZONE, SESSIONTIMEZONE
    FROM dual;

Có thể kiểm tra timezone của session JDBC sau khi lấy connection:

    SELECT SESSIONTIMEZONE FROM dual;

Trong connection pool, nhiều request có thể dùng lại cùng physical session. Nếu một request chạy ALTER SESSION SET TIME_ZONE rồi trả connection về pool mà không reset, request sau có thể nhận session với timezone do request trước để lại.

Đây là lỗi đặc biệt khó phát hiện vì chỉ xuất hiện khi request được phân phối vào những connection có session state khác nhau.

### 6.1. Cố định session timezone

Nếu ứng dụng muốn mọi session xử lý TSLTZ và các hàm thời gian theo UTC, có thể cấu hình khởi tạo session:

    ALTER SESSION SET TIME_ZONE = 'UTC';

Cần đặt lệnh này trong cơ chế connection initialization phù hợp với pool, hoặc bảo đảm mỗi physical connection được khởi tạo đúng một lần và session state không bị thay đổi ngoài kiểm soát.

Nếu ứng dụng có nhiều tenant hoặc người dùng ở nhiều timezone, không nên tùy tiện đổi SESSIONTIMEZONE trên connection rồi trả về pool. Nếu bắt buộc thay đổi, cần lưu timezone cũ và khôi phục trong finally trước khi trả connection; tốt hơn là dùng connection initialization/reset mechanism của pool đã được kiểm chứng.

### 6.2. DBTIMEZONE không phải timezone của máy ứng dụng

DBTIMEZONE không nhất thiết bằng timezone của operating system, timezone của JVM hay SESSIONTIMEZONE. Không giả định các giá trị này giống nhau.

Với TSLTZ, Oracle chuyển đổi từ session timezone khi đọc; vì vậy cùng một hàng có thể hiển thị giá trị khác nhau ở hai session. Với DATE/TIMESTAMP không timezone, Oracle không tự biết timezone của dữ liệu.

## 7. Các hàm ngày giờ Oracle và tác động timezone

Một số hàm trả kiểu DATE/TIMESTAMP khác nhau và dùng các nguồn timezone khác nhau.

| Hàm | Kiểu trả về | Ngữ nghĩa chính |
|---|---|---|
| SYSDATE | DATE | Ngày giờ theo clock của hệ điều hành database server |
| SYSTIMESTAMP | TIMESTAMP WITH TIME ZONE | Timestamp theo clock hệ điều hành database server, có offset |
| CURRENT_DATE | DATE | Ngày giờ hiện tại theo SESSIONTIMEZONE |
| CURRENT_TIMESTAMP | TIMESTAMP WITH TIME ZONE | Timestamp hiện tại theo SESSIONTIMEZONE |
| LOCALTIMESTAMP | TIMESTAMP | Timestamp hiện tại theo SESSIONTIMEZONE nhưng không mang timezone trong giá trị trả về |
| DBTIMEZONE | VARCHAR2 | Timezone cấu hình ở cấp database |
| SESSIONTIMEZONE | VARCHAR2 | Timezone của session hiện tại |

Ví dụ:

    SELECT
        SYSDATE,
        SYSTIMESTAMP,
        CURRENT_DATE,
        CURRENT_TIMESTAMP,
        LOCALTIMESTAMP,
        DBTIMEZONE,
        SESSIONTIMEZONE
    FROM dual;

Không thay SYSDATE bằng CURRENT_DATE hoặc ngược lại mà không đánh giá ngữ nghĩa. Nếu database server chạy UTC nhưng session chạy Asia/Ho_Chi_Minh, SYSDATE và CURRENT_DATE có thể hiển thị giờ khác nhau.

### 7.1. Chuyển đổi timezone trong SQL

Có thể gắn timezone cho một TIMESTAMP không timezone bằng FROM_TZ:

    SELECT FROM_TZ(
        TIMESTAMP '2026-11-14 21:00:00',
        'Asia/Ho_Chi_Minh'
    ) AS value_with_zone
    FROM dual;

Có thể chuyển giá trị có timezone sang vùng khác bằng AT TIME ZONE:

    SELECT
        FROM_TZ(
            TIMESTAMP '2026-11-14 21:00:00',
            'Asia/Ho_Chi_Minh'
        ) AT TIME ZONE 'UTC' AS utc_value
    FROM dual;

Đây là chuyển đổi theo timezone region và quy tắc timezone của Oracle. Tránh tự cộng hoặc trừ một số giờ cố định để chuyển timezone, vì offset có thể thay đổi theo DST hoặc quy tắc pháp lý của vùng.

### 7.2. NLS format không phải timezone

NLS_DATE_FORMAT, NLS_TIMESTAMP_FORMAT và NLS_TIMESTAMP_TZ_FORMAT điều khiển cách Oracle chuyển đổi/hiển thị chuỗi trong một số ngữ cảnh. Chúng không thay đổi bản chất dữ liệu đã lưu.

Ví dụ:

    ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD HH24:MI:SS';

Không dựa vào NLS format mặc định để parse chuỗi ngày giờ. Dùng bind variable có kiểu hoặc chỉ định format mask tường minh khi phải chuyển chuỗi SQL.

## 8. Daylight Saving Time (DST), gap và overlap

Timezone region có quy tắc thay đổi offset theo lịch sử và quy định địa phương. Ở vùng có DST, đồng hồ có thể tiến lên hoặc lùi lại.

Hai tình huống:

- **Gap**: một khoảng local time không tồn tại khi đồng hồ nhảy tiến. Ví dụ 02:30 có thể không xảy ra trong ngày chuyển DST.
- **Overlap**: một khoảng local time xuất hiện hai lần khi đồng hồ lùi. Ví dụ 01:30 có thể ứng với hai instant khác nhau.

LocalDateTime không thể tự phân biệt hai instant trong khoảng overlap. Nếu cần biểu diễn một sự kiện thực tế, hãy dùng OffsetDateTime/Instant hoặc LocalDateTime đi kèm ZoneId và quy tắc chọn offset khi overlap.

### 8.1. Java ZoneId và ZonedDateTime

Ví dụ chuyển local date-time sang vùng thời gian:

    LocalDateTime local =
        LocalDateTime.of(2026, 11, 14, 9, 0);

    ZonedDateTime zoned =
        local.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

    Instant instant = zoned.toInstant();

Asia/Ho_Chi_Minh hiện không dùng DST theo quy tắc hiện hành, nhưng ứng dụng không nên suy rộng điều đó cho mọi ZoneId. Khi dùng Europe/Paris hoặc America/New_York, phải kiểm tra gap/overlap theo timezone rules.

Java cung cấp ZoneRules để kiểm tra các offset hợp lệ:

    ZoneId zone = ZoneId.of("Europe/Paris");
    LocalDateTime localTime =
        LocalDateTime.of(2026, 10, 25, 2, 30);

    List<ZoneOffset> offsets =
        zone.getRules().getValidOffsets(localTime);

Nếu danh sách rỗng, local time nằm trong gap. Nếu có hai offset, local time nằm trong overlap và ứng dụng cần chính sách chọn offset. Không nên để lựa chọn mặc định của thư viện quyết định ngầm cho nghiệp vụ quan trọng.

### 8.2. Giữ cả thời điểm và timezone nghiệp vụ

Với lịch hẹn, lịch bay hoặc sự kiện có địa điểm, mô hình dữ liệu có thể cần:

- Instant hoặc TSTZ: thời điểm thực tế.
- ZoneId: timezone nghiệp vụ/địa điểm.
- LocalDateTime: giờ địa phương đã được người dùng chọn, nếu cần giữ nguyên lịch nhập.

Không phải ứng dụng nào cũng cần lưu cả ba. Chọn theo yêu cầu: sự kiện đã xảy ra cần instant; lịch tương lai có thể cần cả local wall-clock time và ZoneId để giữ ý định khi luật DST thay đổi.

## 9. TSLTZ và session pool: tình huống dễ sai

Giả sử ORDS, Spring Boot hoặc một ứng dụng batch sử dụng connection pool. Một connection vật lý được dùng lại cho nhiều request. Nếu request A thay đổi session timezone sang Europe/Paris rồi trả connection về pool, request B có thể nhận cùng session và đọc TSLTZ theo timezone của request A.

Hệ quả có thể là:

- Timestamp hiển thị khác nhau giữa các request.
- Test chạy độc lập thành công nhưng production lỗi ngẫu nhiên.
- Một số kết quả SQL phụ thuộc thứ tự request.
- Dữ liệu TSLTZ được serialize thành JSON với giờ khác kỳ vọng.
- Các hàm CURRENT_DATE/CURRENT_TIMESTAMP trả kết quả khác theo session.

Cách kiểm soát:

1. Chọn một session timezone chuẩn, thường là UTC cho service xử lý event timestamp.
2. Cấu hình timezone khi physical connection được tạo.
3. Không thay session timezone tùy tiện trong request.
4. Nếu phải thay đổi, luôn reset trước khi trả connection về pool.
5. Ghi nhận SESSIONTIMEZONE trong chẩn đoán.
6. Kiểm thử với nhiều physical connection và request chạy song song.
7. Dùng kiểu dữ liệu có ngữ nghĩa rõ ràng thay vì phụ thuộc session state không được kiểm soát.

Nếu business cần hiển thị theo timezone người dùng, chuyển đổi ở application layer từ Instant sang ZoneId người dùng thường dễ quan sát và kiểm thử hơn việc thay SESSIONTIMEZONE liên tục trên pool.

## 10. Độ chính xác phần giây và làm tròn

Oracle TIMESTAMP hỗ trợ fractional seconds từ 0 đến 9 chữ số. Java LocalDateTime và Instant có độ chính xác nano giây. Khi ghi dữ liệu có độ chính xác cao hơn cột, Oracle sẽ áp dụng quy tắc chuyển đổi/rounding phù hợp với kiểu và thao tác; ứng dụng không nên dựa vào việc mọi chữ số nano đều được giữ.

Ví dụ:

    TIMESTAMP(3)   -- millisecond precision
    TIMESTAMP(6)   -- microsecond precision
    TIMESTAMP(9)   -- nanosecond precision

Nếu hệ thống dùng TIMESTAMP(6), cần chuẩn hóa hoặc chấp nhận việc cắt/làm tròn phần nano xuống độ chính xác của cột. Khi so sánh timestamp hoặc tạo khóa duy nhất dựa trên thời gian, phải tính đến precision thực tế của database và driver.

Không dùng timestamp làm khóa duy nhất nếu có thể tạo nhiều sự kiện trong cùng độ chính xác của cột. Dùng sequence, identity hoặc UUID phù hợp hơn.

## 11. Spring Boot, Hibernate và timezone

Trong ứng dụng Spring Boot, JDBC driver và ORM cùng ảnh hưởng tới mapping. Nếu dùng Hibernate/JPA, cần xác định phiên bản Hibernate, dialect Oracle, JDBC driver và cách mapping entity.

Ví dụ domain:

    @Entity
    class AuditEvent {
        @Id
        private Long id;

        private Instant occurredAt;
    }

Instant thường phù hợp với event timestamp. Với cột TSTZ, kiểm tra Hibernate version và cấu hình timezone storage strategy. Với TIMESTAMP thuần lưu UTC, ghi rõ convention và bảo đảm tất cả đường ghi/đọc áp dụng UTC.

Một số cấu hình Hibernate có thể dùng:

    spring:
      jpa:
        properties:
          hibernate:
            jdbc:
              time_zone: UTC

Thiết lập này có thể giúp Hibernate dùng timezone nhất quán cho một số JDBC timestamp operation, nhưng không biến TIMESTAMP không timezone thành kiểu có timezone, cũng không thay thế việc hiểu TSTZ/TSLTZ. Kiểm tra hành vi theo Hibernate version, Oracle dialect và driver đang dùng.

Nếu dùng Spring JDBC hoặc JdbcTemplate, có thể bind java.time trực tiếp qua PreparedStatementSetter/RowMapper khi driver hỗ trợ. Hãy giữ mapping ở repository layer và không để controller tự parse/format ngày giờ tùy tiện.

### 11.1. API JSON và ISO-8601

Khi nhận timestamp từ REST API, ưu tiên định dạng ISO-8601 có offset cho một instant:

    2026-11-14T21:19:35.123456+07:00

Hoặc UTC:

    2026-11-14T14:19:35.123456Z

Nếu API nhận LocalDateTime không offset, phải xác định timezone theo contract. Không suy ra timezone từ máy chủ hoặc browser nếu nghiệp vụ chưa quy định.

Jackson hỗ trợ java.time thông qua module phù hợp. Nên chuẩn hóa response và test round-trip giữa JSON, Java, JDBC và Oracle. Tránh format timestamp thành chuỗi theo locale mặc định.

## 12. Quy tắc thiết kế schema

Một số quy tắc thực tế:

| Ý nghĩa nghiệp vụ | Oracle type gợi ý | Java type gợi ý |
|---|---|---|
| Ngày sinh, ngày hóa đơn theo lịch | DATE với giờ luôn là 00:00:00, hoặc mô hình ngày phù hợp | LocalDate |
| Giờ mở cửa, giờ hẹn địa phương không có timezone | DATE hoặc TIMESTAMP theo precision cần thiết | LocalDateTime, có ZoneId riêng nếu cần |
| Thời điểm tạo/sửa record xuyên hệ thống | TIMESTAMP WITH TIME ZONE hoặc TIMESTAMP theo convention UTC | Instant hoặc OffsetDateTime |
| Thời điểm có offset do client gửi | TIMESTAMP WITH TIME ZONE | OffsetDateTime |
| Thời điểm hiển thị theo session timezone | TIMESTAMP WITH LOCAL TIME ZONE | LocalDateTime theo session timezone, có kiểm soát session |
| Lịch tương lai theo timezone địa điểm | Local date-time + ZoneId; có thể lưu thêm instant dự kiến | LocalDateTime + ZoneId/ZonedDateTime |

Đừng đổi toàn bộ cột DATE thành TIMESTAMP WITH TIME ZONE chỉ vì ứng dụng dùng java.time. Kiểu SQL phải thể hiện đúng semantics và tương thích với dữ liệu, báo cáo, index, partition, integration và ứng dụng hiện có.

### 12.1. Đặt tên cột để làm rõ semantics

Tên như CREATED_AT_UTC, BUSINESS_DATE, LOCAL_START_TIME hoặc EVENT_TSTZ giúp người đọc hiểu ý nghĩa. Tuy nhiên, convention phải được tài liệu hóa và enforced trong code, migration, test.

Ví dụ:

    CREATE TABLE payment_event (
        event_id NUMBER PRIMARY KEY,
        created_at TIMESTAMP(6) WITH TIME ZONE NOT NULL,
        business_date DATE,
        store_zone_id VARCHAR2(64)
    );

created_at là thời điểm có timezone; business_date là ngày nghiệp vụ; store_zone_id giữ timezone địa điểm. Không dùng cùng một cột cho cả ba khái niệm.

## 13. Kiểm thử mapping ngày giờ

Bài test cần bao phủ nhiều hơn một giá trị bình thường. Tối thiểu kiểm tra:

- Ngày cuối tháng và đầu tháng.
- Năm nhuận và ngày 29/02.
- Giá trị đúng nửa đêm và giá trị có giờ/phút/giây.
- Fractional seconds ở precision của cột.
- Offset UTC, +07:00 và offset âm.
- Timestamp ở timezone có DST.
- Thời điểm trong DST gap và overlap.
- Cùng một TSLTZ đọc từ hai session timezone khác nhau.
- Kết nối được lấy lại từ pool sau khi session state đã thay đổi.
- Round-trip JSON → Java → JDBC → Oracle → JDBC → Java → JSON.
- Giá trị null và các cột nullable.

Test phải chạy với đúng Oracle JDBC driver được triển khai. Mock JDBC không thể xác nhận đầy đủ cách driver Oracle chuyển đổi DATE, TSTZ và TSLTZ.

### 13.1. Ví dụ round-trip test đơn giản

Một test repository có thể ghi rồi đọc lại LocalDateTime:

    LocalDateTime input =
        LocalDateTime.of(2026, 11, 14, 21, 19, 35, 123456000);

    repository.save(input);

    LocalDateTime actual = repository.findById(1L);

    assertEquals(input, actual);

Nếu cột TIMESTAMP(3), test cần chuẩn hóa input theo millisecond trước khi so sánh. Nếu dùng TIMESTAMP(6), chuẩn hóa theo microsecond. Đừng so sánh nano giây với cột chỉ giữ 6 chữ số.

Với OffsetDateTime/TSTZ, so sánh Instant nếu mục tiêu là cùng thời điểm; so sánh offset hoặc ZoneId riêng nếu nghiệp vụ yêu cầu giữ biểu diễn gốc.

## 14. Những lỗi thường gặp và cách xử lý

### 14.1. Giờ bị mất sau khi đọc Oracle DATE

Nguyên nhân thường gặp là dùng getDate hoặc java.sql.Date. Oracle DATE có cả giờ, nhưng java.sql.Date có ngữ nghĩa ngày lịch.

Cách xử lý: dùng LocalDateTime qua JDBC 4.2 nếu driver hỗ trợ, hoặc getTimestamp rồi toLocalDateTime. Xác nhận cột thực sự có dữ liệu giờ trước khi thay mapping.

### 14.2. Giờ bị lệch đúng một số giờ

Nguyên nhân có thể là chuyển đổi từ LocalDateTime sang Instant bằng timezone mặc định của JVM, session timezone khác nhau, hoặc API parse timestamp không offset như thể nó là UTC.

Cách xử lý: kiểm tra kiểu SQL, SESSIONTIMEZONE, timezone JVM, input JSON và code conversion. Không cộng/trừ giờ thủ công; chọn một quy ước UTC hoặc timezone region rõ ràng.

### 14.3. Cùng một TSLTZ trả ra giờ khác nhau

Đây là hành vi bình thường khi session timezone khác nhau. Kiểm tra SESSIONTIMEZONE trên từng connection. Cố định timezone session hoặc chuyển đổi ở application layer theo ZoneId được xác định.

### 14.4. Mất timezone region sau round-trip

OffsetDateTime có thể giữ offset nhưng không giữ tên region ban đầu. Nếu cần giữ Asia/Ho_Chi_Minh hoặc Europe/Paris như một phần nghiệp vụ, lưu ZoneId riêng và kiểm thử mapping của driver.

### 14.5. Timestamp bị mất chữ số phần giây

Kiểm tra precision của cột TIMESTAMP(p), driver và kiểu trung gian. java.sql.Date hoặc format chuỗi có thể làm mất phần giây; cột TIMESTAMP(3) cũng không giữ microsecond/nanosecond.

### 14.6. Lỗi phụ thuộc NLS_DATE_FORMAT

Nếu ứng dụng truyền chuỗi ngày giờ và dựa vào format mặc định của session, môi trường có NLS khác nhau có thể parse khác hoặc phát sinh lỗi. Bind typed value thay vì ghép chuỗi; nếu phải parse chuỗi trong SQL, dùng format mask rõ ràng.

## 15. Quy trình chẩn đoán một cột ngày giờ bị lệch

Khi nhận báo cáo ngày giờ khác nhau giữa Java và Oracle, điều tra theo thứ tự:

1. Lấy DDL chính xác của cột: DATE, TIMESTAMP(p), TSTZ hay TSLTZ.
2. Kiểm tra giá trị trực tiếp trong Oracle bằng format có đủ ngày, giờ, phần giây và timezone nếu có.
3. Kiểm tra kiểu Java đang dùng: LocalDate, LocalDateTime, Instant, OffsetDateTime hay kiểu legacy.
4. Xem code JDBC dùng getDate, getTimestamp, getObject hay getString.
5. Kiểm tra Oracle JDBC driver version và JDK version.
6. Kiểm tra DBTIMEZONE, SESSIONTIMEZONE và JVM default timezone.
7. Kiểm tra timezone của JSON input/output và thư viện serialize.
8. Nếu dùng pool, kiểm tra session state trên nhiều physical connection.
9. So sánh Instant khi mục tiêu là thời điểm; so sánh LocalDateTime khi mục tiêu là giờ lịch.
10. Tạo test round-trip với dữ liệu tái hiện lỗi và chạy trên đúng driver/runtime production.

Tránh sửa bằng cách cộng hoặc trừ một số giờ cố định trong mapper. Cách đó có thể làm một môi trường đúng nhưng làm sai môi trường khác hoặc thời điểm chuyển DST.

## 16. Nguyên tắc cần nhớ

- Oracle DATE lưu ngày và giờ đến giây; không coi nó như ngày-only nếu chưa xác minh dữ liệu.
- Oracle TIMESTAMP có fractional seconds nhưng không có timezone.
- TSTZ lưu ngày giờ kèm offset/region; OffsetDateTime là mapping tự nhiên, nhưng ZoneId có thể cần lưu riêng.
- TSLTZ chuẩn hóa theo DBTIMEZONE và hiển thị theo SESSIONTIMEZONE; timezone gốc từng hàng không được giữ.
- LocalDate dành cho ngày lịch; LocalDateTime dành cho giờ lịch không timezone; Instant dành cho thời điểm tuyệt đối; OffsetDateTime dành cho ngày giờ có offset.
- JDBC 4.2 hỗ trợ java.time qua getObject/setObject tùy driver; phải test trên ojdbc thực tế.
- Không dùng java.sql.Date cho Oracle DATE có thành phần giờ; dùng LocalDateTime hoặc Timestamp khi cần giữ thời gian.
- Không diễn giải LocalDateTime thành Instant bằng timezone mặc định của máy.
- Cố định hoặc reset SESSIONTIMEZONE trên connection pool; không để session state rò rỉ giữa request.
- Dùng bind variables và ISO-8601 có offset cho timestamp truyền qua API.
- Kiểm thử DST, precision, null, session timezone và round-trip trước khi triển khai.

Ánh xạ ngày giờ đúng bắt đầu từ câu hỏi dữ liệu đại diện cho ngày lịch, giờ địa phương hay một thời điểm tuyệt đối. Sau khi chọn đúng Oracle type và java.time type, hãy kiểm soát timezone ở JDBC session, driver và API boundary. Làm rõ semantics từ đầu sẽ tránh được lỗi mất giờ, lệch múi giờ và kết quả không ổn định giữa các môi trường.
