# Quan sát phiên trong bảng mà không công bố thông tin truy cập

Spring Session JDBC lưu trạng thái phiên trong các bảng cơ sở dữ liệu, thường là SPRING_SESSION và SPRING_SESSION_ATTRIBUTES. Những bảng này hữu ích khi điều tra số lượng phiên, thời hạn, hoạt động cleanup hoặc lỗi lưu trữ. Tuy nhiên, dữ liệu bên trong có thể chứa session ID, tên principal, thông tin xác thực và các thuộc tính ứng dụng. Session ID thường hoạt động như bearer credential: người có được giá trị đó có thể giả mạo client cho đến khi phiên bị thu hồi hoặc hết hạn.

Quan sát vận hành vì thế phải tuân theo nguyên tắc tối thiểu dữ liệu: thu thập đủ thông tin để biết hệ thống đang khỏe hay gặp sự cố, nhưng không đưa cookie, session ID, SecurityContext, token hoặc dữ liệu cá nhân lên dashboard, log, ticket hỗ trợ hay báo cáo. Bài học này trình bày cách quan sát Spring Session JDBC an toàn, từ truy vấn tổng hợp đến phân quyền database và quy trình hỗ trợ.

## 1. Những dữ liệu nhạy cảm trong hai bảng JDBC

Schema tiêu chuẩn của Spring Session tách metadata phiên và các thuộc tính của phiên:

| Bảng/cột | Nội dung | Mức độ cần bảo vệ |
|---|---|---|
| SPRING_SESSION.SESSION_ID | Định danh được client gửi qua cookie hoặc header | Rất nhạy cảm; xử lý như credential |
| SPRING_SESSION.PRIMARY_ID | Khóa nội bộ liên kết metadata với attributes | Không công khai; chỉ dùng trong truy vấn nội bộ |
| SPRING_SESSION.PRINCIPAL_NAME | Tên người dùng hoặc principal | Dữ liệu định danh cá nhân |
| SPRING_SESSION.CREATION_TIME | Thời điểm tạo phiên | Metadata có thể liên kết với hành vi người dùng |
| SPRING_SESSION.LAST_ACCESS_TIME | Lần truy cập gần nhất | Metadata hoạt động; hạn chế truy cập |
| SPRING_SESSION.EXPIRY_TIME | Mốc hết hạn | Metadata vận hành; chỉ hiển thị ở mức cần thiết |
| SPRING_SESSION_ATTRIBUTES.ATTRIBUTE_NAME | Tên thuộc tính, có thể tiết lộ loại dữ liệu | Hạn chế hiển thị |
| SPRING_SESSION_ATTRIBUTES.ATTRIBUTE_BYTES | Giá trị đã serialize, có thể chứa SecurityContext hoặc dữ liệu cá nhân | Không đưa vào dashboard |

Không phải mọi thuộc tính đều là bí mật, nhưng bảng attributes không phân biệt sẵn trường nào an toàn để công bố. Một thuộc tính có thể chứa đối tượng xác thực, thông tin người dùng, mã giỏ hàng, trạng thái quy trình hoặc dữ liệu do ứng dụng tự định nghĩa. Vì vậy, không nên truy vấn hoặc xuất toàn bộ bảng để xem session đang có gì.

### 1.1. Session ID là credential

Cookie session thường mang một giá trị định danh. Khi máy chủ nhận giá trị hợp lệ, nó có thể khôi phục session và trạng thái xác thực gắn với session đó. Do vậy:

- Không chụp màn hình cookie/session ID gửi vào ticket.
- Không ghi header Cookie hoặc Set-Cookie trong access log.
- Không đưa session ID vào URL, query string, trace attribute hay metric label.
- Không gửi session ID qua chat hoặc email không được bảo vệ.
- Không hiển thị giá trị ID đầy đủ trong công cụ quản trị.

Việc một ID không phải mật khẩu không làm nó trở nên công khai. Nếu có thể dùng nó để tiếp tục phiên đã xác thực, hãy bảo vệ nó như một thông tin truy cập.

## 2. Quan sát vận hành khác với đọc nội dung phiên

Đa số câu hỏi vận hành có thể trả lời bằng metadata tổng hợp:

- Có bao nhiêu session chưa hết hạn?
- Có bao nhiêu dòng đã quá hạn nhưng chưa được cleanup?
- Số session tăng đột biến hay giảm bất thường?
- Cleanup có chạy và có loại bỏ dữ liệu không?
- Số dòng attributes và dung lượng lưu trữ có tăng bất thường không?
- Truy vấn repository có chậm hoặc lỗi kết nối không?

Những câu hỏi này không cần biết session ID, principal name hay nội dung thuộc tính. Một dashboard tốt hiển thị số lượng theo môi trường, ứng dụng, khoảng thời gian hoặc nhóm trạng thái; không hiển thị từng người dùng hoặc từng session.

| Nhu cầu | Dữ liệu nên hiển thị | Dữ liệu không cần hiển thị |
|---|---|---|
| Theo dõi tổng phiên | Số lượng session | Session ID |
| Theo dõi timeout | Số phiên theo nhóm thời hạn | Cookie hoặc token |
| Theo dõi cleanup | Số dòng quá hạn, số dòng đã dọn | Principal của từng phiên |
| Theo dõi kích thước | Tổng số attribute, dung lượng bảng | ATTRIBUTE_BYTES |
| Điều tra một mã hỗ trợ | Kết quả tồn tại/hết hạn và thời điểm tương đối nếu được phép | Giá trị ID hoặc toàn bộ SecurityContext |

Không dùng truy vấn SELECT * trên bảng session hoặc bảng attributes trong công cụ quan sát. Câu lệnh này có thể kéo dữ liệu nhạy cảm vào terminal history, query log, clipboard, ảnh chụp màn hình hoặc hệ thống APM.

## 3. Hiểu metadata trước khi viết truy vấn

Các cột thời gian của Spring Session JDBC thường được lưu dưới dạng epoch milliseconds:

- CREATION_TIME: thời điểm tạo phiên.
- LAST_ACCESS_TIME: thời điểm truy cập gần nhất.
- MAX_INACTIVE_INTERVAL: thời gian không hoạt động tối đa, đơn vị giây.
- EXPIRY_TIME: mốc hết hạn tính theo epoch milliseconds.

Với timeout dương, EXPIRY_TIME thường được tính từ lần truy cập cuối cộng khoảng không hoạt động tối đa. Cần dùng cùng đơn vị khi so sánh. Không so sánh trực tiếp epoch milliseconds với CURRENT_TIMESTAMP hoặc giá trị epoch seconds.

Một dòng còn tồn tại trong bảng không nhất thiết có nghĩa session còn được chấp nhận. Phiên có thể đã quá hạn nhưng job cleanup chưa xóa vật lý. Repository phải áp dụng logic hết hạn khi tìm phiên; cleanup chịu trách nhiệm dọn dữ liệu cũ theo lịch.

Vì vậy, số lượng dòng trong SPRING_SESSION là chỉ số lưu trữ, không phải phép đo chính xác số người đang đăng nhập hoặc số người đang hoạt động ngay lúc xem.

## 4. Truy vấn tổng hợp số session

Truy vấn sau chỉ trả về một số tổng hợp, không trả session ID hoặc principal:

~~~sql
SELECT COUNT(*) AS SESSION_ROWS
FROM SPRING_SESSION;
~~~

Đây là tổng số dòng vật lý hiện có. Nó có thể bao gồm session đã hết hạn nhưng chưa cleanup. Không diễn giải con số này thành số người dùng đang đăng nhập.

Để đếm các dòng có mốc hết hạn còn ở tương lai, truyền thời điểm hiện tại dưới dạng epoch milliseconds:

~~~sql
SELECT COUNT(*) AS NOT_EXPIRED_ROWS
FROM SPRING_SESSION
WHERE EXPIRY_TIME > ?;
~~~

Tham số là nowEpochMillis. Tên NOT_EXPIRED_ROWS có chủ ý: đây là số dòng chưa qua mốc hết hạn theo metadata, không chứng minh người dùng đang tương tác hoặc còn đủ quyền truy cập.

Đếm riêng các dòng đã quá hạn nhưng vẫn còn trong bảng:

~~~sql
SELECT COUNT(*) AS EXPIRED_ROWS_PENDING_CLEANUP
FROM SPRING_SESSION
WHERE EXPIRY_TIME <= ?;
~~~

Tham số cũng là epoch milliseconds. Nếu con số tăng liên tục, hãy kiểm tra lịch cleanup, lỗi database, thời gian chạy job và index trên EXPIRY_TIME. Không xóa thủ công toàn bộ kết quả trong production chỉ dựa trên một dashboard.

### 4.1. Phân nhóm theo trạng thái thời hạn

Có thể tạo báo cáo theo nhóm để biết số phiên đã hết hạn, sắp hết hạn và còn thời gian:

~~~sql
SELECT
    CASE
        WHEN EXPIRY_TIME <= ? THEN 'EXPIRED'
        WHEN EXPIRY_TIME <= ? THEN 'EXPIRING_SOON'
        ELSE 'NOT_EXPIRING_SOON'
    END AS EXPIRY_BUCKET,
    COUNT(*) AS SESSION_COUNT
FROM SPRING_SESSION
GROUP BY
    CASE
        WHEN EXPIRY_TIME <= ? THEN 'EXPIRED'
        WHEN EXPIRY_TIME <= ? THEN 'EXPIRING_SOON'
        ELSE 'NOT_EXPIRING_SOON'
    END;
~~~

Tham số được bind theo thứ tự xuất hiện: nowEpochMillis, soonEpochMillis, rồi lặp lại hai giá trị đó cho biểu thức GROUP BY. soonEpochMillis là mốc hiện tại cộng khoảng thời gian cảnh báo do vận hành chọn.

Tên bucket chỉ mô tả metadata. Không hiển thị chi tiết từng phiên trong bảng tổng hợp. Nếu số lượng nhóm nhỏ có thể làm lộ hoạt động của một người hoặc một nhóm rất nhỏ, hãy gộp nhóm hoặc ẩn số lượng dưới ngưỡng công bố nội bộ.

## 5. Theo dõi bảng attributes mà không đọc payload

Để phát hiện bảng thuộc tính tăng nhanh, chỉ cần đếm số dòng:

~~~sql
SELECT COUNT(*) AS ATTRIBUTE_ROWS
FROM SPRING_SESSION_ATTRIBUTES;
~~~

Có thể so sánh xu hướng theo thời gian bằng metric hoặc snapshot định kỳ. Tránh chọn ATTRIBUTE_BYTES để tính hoặc xuất nội dung. Nếu cần đo kích thước lưu trữ, dùng thống kê dung lượng bảng/index từ hệ quản trị hoặc công cụ quản trị database; không tải toàn bộ bytes về máy trạm.

Không cần nhóm theo ATTRIBUTE_NAME trong dashboard công khai. Tên thuộc tính đôi khi tiết lộ loại nghiệp vụ, chẳng hạn một thuộc tính có thể cho biết người dùng đang ở quy trình thanh toán hoặc xác thực. Nếu cần phát hiện thuộc tính bất thường, hãy dùng danh sách tên đã được duyệt và chỉ trả về tổng số theo nhóm rộng.

## 6. Kiểm tra một session mà không tiết lộ ID

Trong một sự cố cụ thể, đội hỗ trợ có thể cần xác nhận một session còn tồn tại hay đã hết hạn. Nếu quy trình cho phép tra cứu theo ID, chỉ dùng giá trị đó làm tham số bind và chỉ trả về kết quả tối thiểu:

~~~sql
SELECT CASE
    WHEN COUNT(*) > 0 THEN 1
    ELSE 0
END AS SESSION_IS_NOT_EXPIRED
FROM SPRING_SESSION
WHERE SESSION_ID = ?
  AND EXPIRY_TIME > ?;
~~~

Hai tham số lần lượt là session ID lấy từ kênh hỗ trợ được bảo vệ và epoch milliseconds hiện tại. Kết quả chỉ là 0 hoặc 1; không trả lại ID, principal, cookie hay attributes.

Truy vấn này vẫn phải được kiểm soát chặt:

- Không ghi giá trị bind vào application log hoặc SQL bind-value log.
- Không lưu câu truy vấn kèm tham số trong ticket.
- Chỉ nhân sự được phân quyền mới được thực hiện.
- Không cho phép người dùng cuối tra cứu ID tùy ý qua endpoint công khai.
- Xóa dữ liệu tạm khỏi clipboard, shell history và file xuất sau khi hoàn tất.

Kết quả 1 chỉ có nghĩa có dòng session với thời hạn tương lai. Nó không chứng minh người giữ ID hiện tại là đúng chủ thể, cũng không chứng minh mọi quyền nghiệp vụ còn hợp lệ.

## 7. Tạo lớp quan sát chỉ đọc

Không cấp quyền đọc toàn bộ hai bảng cho mọi người cần xem dashboard. Một cách làm an toàn là tạo view chỉ trả dữ liệu tổng hợp rồi cấp quyền đọc view cho tài khoản monitoring.

Ví dụ view tổng số dòng:

~~~sql
CREATE VIEW SESSION_OBSERVABILITY_SUMMARY AS
SELECT COUNT(*) AS SESSION_ROW_COUNT
FROM SPRING_SESSION;
~~~

Sau đó, DBA cấp quyền SELECT trên view cho role quan sát và không cấp SELECT trên bảng gốc. Cú pháp GRANT và cách thu hồi quyền khác nhau giữa PostgreSQL, MySQL, SQL Server và Oracle; hãy áp dụng đúng hệ quản trị đang dùng.

Với báo cáo theo thời hạn động, có thể dùng stored procedure hoặc một dịch vụ nội bộ chỉ chạy các truy vấn tổng hợp đã duyệt, nhận thời gian qua tham số và trả số liệu đã lọc. Không tạo view chứa một dòng cho mỗi session rồi coi việc ẩn cột ID là đủ an toàn: tổ hợp thời gian và metadata vẫn có thể giúp nhận diện một cá nhân.

### 7.1. Tách tài khoản ứng dụng và tài khoản quan sát

Nên có ít nhất hai nhóm quyền:

| Tài khoản/role | Quyền cần thiết |
|---|---|
| Spring Session application role | Các thao tác SELECT/INSERT/UPDATE/DELETE cần cho repository và cleanup |
| Monitoring role | Chỉ đọc view hoặc thủ tục trả số liệu tổng hợp |
| DBA/break-glass role | Quyền quản trị có kiểm soát, chỉ dùng khi có phê duyệt và audit |

Không dùng thông tin đăng nhập database của ứng dụng trong dashboard hoặc công cụ BI. Tài khoản ứng dụng có thể cần đọc cả ATTRIBUTE_BYTES; tài khoản quan sát thông thường không cần quyền đó.

## 8. Không đưa thông tin session vào log, trace và metric

Rò rỉ thường xảy ra ngoài database. Các nguồn cần rà soát:

- Access log của reverse proxy và web server.
- Log request/response khi bật debug.
- APM agent thu thập HTTP headers.
- Distributed tracing và baggage.
- Error report có serialize request hoặc session.
- Dashboard có label theo username hoặc session ID.
- Ticket hỗ trợ chứa cookie copy từ trình duyệt.

Không ghi Cookie, Set-Cookie, Authorization header, session ID hoặc toàn bộ SecurityContext. Nếu cần liên kết sự kiện của cùng một session để điều tra, dùng một fingerprint giả danh có kiểm soát thay cho ID gốc.

### 8.1. Dùng HMAC khi cần tương quan sự kiện

Nếu cần biết hai log thuộc cùng một session mà không công bố session ID, có thể tạo fingerprint bằng HMAC-SHA-256 với secret chỉ hệ thống quan sát được phép sử dụng:

~~~java
Mac mac = Mac.getInstance("HmacSHA256");
mac.init(new SecretKeySpec(hmacKey, "HmacSHA256"));
byte[] digest = mac.doFinal(sessionId.getBytes(StandardCharsets.UTF_8));
String fingerprint = HexFormat.of().formatHex(digest);
~~~

Ví dụ chỉ minh họa phép tính. hmacKey phải được lấy từ secret manager/KMS, không hard-code hoặc ghi log. Fingerprint vẫn là dữ liệu giả danh có thể liên kết hoạt động theo thời gian; giới hạn quyền truy cập, thời gian lưu và phạm vi sử dụng.

Không dùng hash không khóa như SHA-256(sessionId) nếu cần chống đối chiếu ngoài ý muốn. HMAC có secret giúp người không có khóa khó tự tạo bảng đối chiếu. Khi xoay khóa, cần cân nhắc việc fingerprint cũ và mới không còn khớp nhau.

## 9. Metric và dashboard an toàn

Có thể thu thập các metric vận hành với nhãn ít biến thiên:

| Metric gợi ý | Ý nghĩa | Nhãn an toàn |
|---|---|---|
| Số session chưa hết hạn | Xu hướng quy mô kho session | môi trường, ứng dụng |
| Số session quá hạn chờ cleanup | Theo dõi backlog cleanup | môi trường, store |
| Số dòng attributes | Theo dõi tăng trưởng dữ liệu | môi trường, ứng dụng |
| Thời gian truy vấn repository | Phát hiện database chậm | operation, database |
| Tỷ lệ lỗi repository | Phát hiện lỗi kết nối/SQL | error class đã chuẩn hóa |
| Số lần deserialize thất bại | Phát hiện dữ liệu hoặc phiên bản không tương thích | serializer version, app version |
| Thời gian cleanup | Theo dõi tác vụ nền | môi trường, store |

Không dùng session ID, username, email, IP đầy đủ hoặc principal name làm metric label. Những giá trị này tạo cardinality cao và có thể tiết lộ hành vi cá nhân. Nếu cần điều tra một tài khoản, thực hiện qua quy trình hỗ trợ có kiểm soát thay vì dashboard tổng quan.

Thu thập metric theo chu kỳ phù hợp, tránh chạy truy vấn đếm toàn bảng trên mỗi request. Trên bảng lớn, truy vấn tổng hợp vẫn tiêu tốn I/O và CPU. Dùng index phù hợp, thống kê database, snapshot định kỳ hoặc view/materialized view nếu yêu cầu độ mới cho phép.

## 10. Quy trình hỗ trợ khi người dùng báo mất session

Khi tiếp nhận sự cố, không yêu cầu người dùng gửi cookie hoặc session ID qua kênh thông thường. Thu thập thông tin không nhạy cảm trước:

1. Mã yêu cầu hỗ trợ và thời điểm xảy ra sự cố.
2. Môi trường, ứng dụng và khu vực triển khai.
3. Loại thao tác người dùng thực hiện trước khi mất session.
4. Mã correlation ID đã được hệ thống tạo, nếu có.
5. Phiên bản ứng dụng và node xử lý, nếu log đã ghi an toàn.

Đội vận hành kiểm tra xu hướng lỗi repository, Redis/JDBC connectivity, expiration, cleanup và deployment. Nếu phải kiểm tra một session cụ thể, dùng công cụ nội bộ được phân quyền, không hiển thị ID và chỉ trả kết quả tối thiểu như tồn tại, hết hạn hoặc không tìm thấy.

Nếu người dùng vô tình gửi cookie hoặc session ID, coi giá trị đó đã bị lộ: không trích lại vào ticket, xóa khỏi bản ghi hỗ trợ theo quy trình, và cân nhắc thu hồi session tương ứng. Không dùng ID đã gửi qua kênh không bảo vệ để tiếp tục đăng nhập thử.

## 11. Audit truy cập và bảo vệ dữ liệu quan sát

Quyền đọc bảng session là quyền có thể dẫn đến truy cập dữ liệu xác thực. Cần audit:

- Ai truy vấn bảng gốc hoặc gọi công cụ tra cứu session?
- Thời điểm và mục đích nghiệp vụ là gì?
- Truy vấn nào được chạy và số dòng trả về?
- Có export dữ liệu, tải file hoặc copy kết quả không?
- Có thay đổi session hoặc xóa dữ liệu không?

Audit log cũng phải tránh lưu giá trị session ID, cookie, principal nhạy cảm hoặc payload. Có thể ghi tên truy vấn đã chuẩn hóa, tài khoản DB, mã yêu cầu, số dòng trả về và thời gian thực thi.

Tách quyền đọc và quyền sửa. Monitoring role không được UPDATE hoặc DELETE. Công cụ quan sát không nên có nút xóa session trừ khi đó là công cụ quản trị riêng có xác nhận, audit và phạm vi thu hồi được giới hạn.

## 12. Bảo vệ truy vấn và dữ liệu đầu ra

Mọi giá trị truy vấn như session ID hoặc mốc thời gian phải được bind bằng PreparedStatement hoặc Spring JDBC. Không nối chuỗi đầu vào vào SQL:

~~~java
String sql = """
    SELECT COUNT(*)
    FROM SPRING_SESSION
    WHERE SESSION_ID = ?
      AND EXPIRY_TIME > ?
    """;

Integer active = jdbcTemplate.queryForObject(
    sql,
    Integer.class,
    suppliedSessionId,
    nowEpochMillis
);
~~~

Ví dụ trả về số lượng, không trả session ID. suppliedSessionId phải đến từ quy trình nội bộ đã xác thực và không được ghi vào log. Nếu dùng NamedParameterJdbcTemplate, vẫn phải bind tham số; named parameter không thay thế việc kiểm soát quyền truy cập.

Không trả lỗi SQL nguyên bản cho người dùng hoặc dashboard. Thông báo database có thể chứa tên schema, bảng, câu lệnh hoặc giá trị tham số. Ghi lỗi đã chuẩn hóa và correlation ID; chi tiết chỉ dành cho nhóm vận hành được phân quyền.

## 13. Theo dõi cleanup mà không đọc nội dung phiên

Spring Session JDBC có thể dọn session quá hạn theo lịch. Để đánh giá cleanup:

- Theo dõi số dòng quá hạn trước và sau mỗi chu kỳ.
- Theo dõi thời gian chạy và số lần job thất bại.
- Kiểm tra index trên EXPIRY_TIME và execution plan.
- Theo dõi lock wait, deadlock, connection pool và transaction duration.
- So sánh số dòng attributes và session để phát hiện tăng trưởng bất thường.

Ví dụ so sánh hai snapshot:

| Thời điểm | Session rows | Expired rows pending cleanup |
|---|---:|---:|
| Trước cleanup | 120.000 | 8.500 |
| Sau cleanup | 111.700 | 120 |

Các số liệu chỉ là ví dụ. Nếu backlog không giảm sau nhiều chu kỳ, kiểm tra scheduler và quyền xóa của tài khoản ứng dụng. Không truy vấn hoặc xuất nội dung attributes để xác định người dùng nào còn session.

## 14. Lưu giữ và xóa dữ liệu quan sát

Dữ liệu tổng hợp thường ít nhạy cảm hơn dữ liệu phiên, nhưng vẫn có thể tiết lộ quy mô hoạt động hoặc thời điểm sử dụng dịch vụ. Đặt thời gian lưu phù hợp:

- Metric chi tiết có thể giữ ngắn hơn dữ liệu tổng hợp theo ngày.
- Log hỗ trợ chỉ giữ theo chính sách vận hành và pháp lý của tổ chức.
- Fingerprint HMAC cần có thời hạn, mục đích và quyền truy cập rõ ràng.
- File export tạm phải được xóa sau khi điều tra.
- Không sao chép payload session sang data warehouse để phân tích chung.

Khi session bị invalidate hoặc hết hạn, repository và cleanup phải loại dữ liệu theo thiết kế. Bản sao trong log, trace, backup, export hoặc ticket không tự biến mất theo TTL của Redis/JDBC; chúng cần chính sách lưu giữ riêng.

## 15. Kiểm thử quan sát an toàn

Trước khi đưa dashboard hoặc công cụ hỗ trợ vào production, hãy kiểm tra cả dữ liệu trả về và quyền database:

| Kịch bản | Cách kiểm thử | Kết quả mong đợi |
|---|---|---|
| Dashboard tổng số phiên | Chạy truy vấn tổng hợp | Chỉ có count và bucket |
| Tài khoản monitoring | Thử đọc view tổng hợp | Thành công |
| Tài khoản monitoring đọc bảng gốc | Thử SELECT SESSION_ID hoặc ATTRIBUTE_BYTES | Bị từ chối |
| Log HTTP | Gửi request có cookie | Cookie không xuất hiện trong log |
| APM/tracing | Kiểm tra captured headers và attributes | Không có session ID hoặc Authorization |
| Hỗ trợ tra session | Tra qua công cụ nội bộ | Chỉ trả trạng thái tối thiểu |
| Bind parameter | Gửi dữ liệu có ký tự SQL đặc biệt | Giá trị được bind, không thay đổi câu SQL |
| Metric cardinality | Tạo nhiều session/principal | Không sinh label theo từng session hoặc người dùng |
| Cleanup | Tạo session hết hạn trong môi trường test | Backlog giảm sau cleanup |
| Export dữ liệu | Tải báo cáo | Không có cookie, principal hoặc payload |

Nên dùng database cùng hệ quản trị với production để kiểm tra view, role, grant, query plan và hành vi audit. H2 có thể hỗ trợ unit test, nhưng không chứng minh quyền và cú pháp SQL trên PostgreSQL, MySQL, SQL Server hoặc Oracle.

## 16. Các lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Dashboard hiển thị cookie hoặc session ID | Dùng SELECT * hoặc log toàn bộ HTTP header | Chỉ truy vấn aggregate; redact header nhạy cảm |
| Người vận hành thấy username trong báo cáo | Nhóm theo PRINCIPAL_NAME | Dùng số liệu tổng hợp; chỉ pseudonymize khi có nhu cầu được duyệt |
| Tài khoản BI đọc được ATTRIBUTE_BYTES | Cấp SELECT trên bảng gốc | Thu hồi quyền và cấp quyền trên view tổng hợp |
| Số session lớn hơn số người đăng nhập | Đếm dòng vật lý, gồm phiên hết hạn chờ cleanup | Đặt tên metric chính xác và phân biệt trạng thái logic/vật lý |
| Query monitoring làm database chậm | Quét toàn bảng quá thường xuyên | Dùng index, snapshot, lịch lấy mẫu và execution plan |
| Ticket chứa session ID | Yêu cầu người dùng gửi cookie để hỗ trợ | Thay bằng correlation ID; xử lý/thu hồi giá trị đã lộ |
| HMAC fingerprint có thể liên kết quá lâu | Không xoay khóa hoặc không có retention | Giới hạn thời gian, scope và quyền; quản lý khóa qua KMS |
| Query log ghi bind value | Bật chế độ log tham số ở môi trường thật | Tắt/redact bind-value logging và kiểm tra APM |
| Monitoring role có thể sửa dữ liệu | Cấp quyền quá rộng | Tách role chỉ đọc khỏi role ứng dụng/DBA |

## 17. Nguyên tắc triển khai

- Xem SESSION_ID như bearer credential; không công bố, ghi log hoặc đưa vào dashboard.
- Không dùng SELECT * trên bảng session và bảng attributes trong hoạt động quan sát.
- Dùng truy vấn tổng hợp chỉ trả số lượng, bucket hoặc trạng thái tối thiểu.
- Phân biệt số dòng vật lý, session chưa qua EXPIRY_TIME và người dùng đang hoạt động.
- Không đọc hoặc xuất ATTRIBUTE_BYTES; dữ liệu này có thể chứa SecurityContext và thông tin cá nhân.
- Hạn chế quyền monitoring vào view/procedure chỉ đọc; không cấp quyền bảng gốc nếu không cần.
- Bind mọi tham số bằng JDBC; không ghi giá trị session ID trong SQL log hoặc ticket.
- Redact Cookie, Set-Cookie, Authorization và các header nhạy cảm trong proxy, application log và APM.
- Nếu cần tương quan sự kiện, dùng fingerprint HMAC có khóa, giới hạn retention và quyền truy cập.
- Theo dõi cleanup, query latency, connection error và deserialize failure bằng metric ít cardinality.
- Audit thao tác tra cứu và export; tách quyền quan sát khỏi quyền xóa hoặc sửa session.
- Kiểm thử quyền database, log redaction, dashboard và quy trình hỗ trợ trước khi triển khai.

Quan sát Spring Session JDBC an toàn bắt đầu từ việc chỉ thu thập dữ liệu cần thiết. Metadata tổng hợp đủ để theo dõi quy mô, timeout và cleanup; nội dung thuộc tính và session ID phải được bảo vệ như dữ liệu truy cập. Khi kết hợp truy vấn aggregate, database role chỉ đọc, log redaction và quy trình hỗ trợ có audit, đội vận hành có thể chẩn đoán session mà không biến công cụ quan sát thành một kênh rò rỉ thông tin xác thực.
