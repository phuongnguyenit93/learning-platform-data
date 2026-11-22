# Kiểm thử mất kết nối, thử lại và tính lặp an toàn

Trong ứng dụng dùng PostgreSQL, mất kết nối có thể xảy ra khi máy chủ khởi động lại, chuyển primary, mạng chập chờn, connection pool giữ một kết nối đã hỏng hoặc truy vấn bị hủy. Ứng dụng thường cần thử lại để tiếp tục phục vụ người dùng. Tuy nhiên, thử lại một thao tác ghi có thể tạo ra dữ liệu trùng nếu lần chạy trước đã được PostgreSQL xác nhận nhưng phản hồi không đến được ứng dụng.

Vì vậy, kiểm thử khả năng phục hồi cần trả lời đồng thời ba câu hỏi:

1. Ứng dụng có nhận biết và loại bỏ kết nối hỏng đúng cách không?
2. Ứng dụng có quyết định đúng khi chưa biết transaction trước đã COMMIT hay chưa không?
3. Khi cùng một yêu cầu được gửi nhiều lần, dữ liệu nghiệp vụ có chỉ thay đổi một lần không?

Ba câu hỏi này liên quan với nhau nhưng không đồng nghĩa. Kết nối có thể được khôi phục mà thao tác nghiệp vụ vẫn bị thực hiện hai lần. Ngược lại, thao tác có thể được bảo vệ bằng idempotency nhưng ứng dụng vẫn làm cạn connection pool nếu không loại bỏ kết nối hỏng.

## 1. Hiểu đúng các thời điểm có thể mất kết nối

PostgreSQL quản lý mỗi kết nối như một session. Transaction được thực hiện bên trong session đó. Khi session mất, transaction chưa COMMIT sẽ không thể tiếp tục trên một kết nối mới. Ứng dụng phải mở kết nối khác và quyết định có nên thực hiện lại thao tác hay không.

Điểm khó nhất là thời điểm COMMIT. Giả sử ứng dụng gửi lệnh COMMIT, PostgreSQL xử lý thành công và ghi nhận transaction, nhưng mạng bị ngắt trước khi phản hồi COMMIT đến ứng dụng. Ở phía ứng dụng, lời gọi commit ném lỗi hoặc hết thời gian chờ. Ứng dụng không thể suy ra transaction đã rollback chỉ từ lỗi kết nối. Transaction có thể đã commit thành công.

Các tình huống cần phân biệt:

| Thời điểm lỗi | Điều ứng dụng có thể biết | Cách xử lý phù hợp |
|---|---|---|
| Trước khi mở được kết nối | Chưa có transaction nào được gửi trên kết nối đó | Thử kết nối lại theo ngân sách retry |
| Sau khi kết nối nhưng trước khi gửi thao tác | Chưa có thay đổi nghiệp vụ từ thao tác đó | Mở kết nối mới và thử lại |
| Trong khi câu lệnh đang chạy | Câu lệnh có thể chưa hoàn tất; session có thể đã bị đóng | Bỏ kết nối hỏng; thực hiện lại toàn bộ thao tác nghiệp vụ theo cơ chế idempotency |
| Sau câu lệnh ghi nhưng trước COMMIT | Transaction chưa được commit nếu máy chủ thực sự chưa nhận COMMIT; kết nối mới không thể tiếp tục transaction cũ | Bắt đầu transaction mới và xử lý bằng cùng idempotency key |
| Trong lúc gửi COMMIT hoặc chờ phản hồi COMMIT | Kết quả commit có thể chưa xác định ở phía client | Tra cứu hoặc gửi lại cùng yêu cầu idempotent trên kết nối mới |
| Sau khi nhận xác nhận COMMIT | Transaction đã được PostgreSQL xác nhận theo cấu hình durability hiện hành | Không chạy lại thao tác; trả kết quả đã lưu |

Không nên gọi mọi lỗi mất kết nối là rollback. Cụm từ *kết quả transaction chưa xác định* mô tả chính xác tình huống client không nhận được xác nhận cuối cùng. Đây là lý do một thao tác ghi cần có định danh yêu cầu ổn định, thay vì chỉ dựa vào số lần gọi hàm hoặc trạng thái của socket.

Một kết nối mới luôn là một session mới. Nó không thể tiếp tục transaction, trạng thái session, temporary table hoặc advisory lock gắn với session cũ. Sau lỗi kết nối, hãy bỏ kết nối cũ khỏi pool theo API của thư viện đang dùng; không trả một connection đã hỏng về pool để request khác tiếp tục sử dụng.

## 2. Nhận diện và phân loại lỗi PostgreSQL

PostgreSQL trả SQLSTATE cho nhiều lỗi SQL. Ứng dụng nên phân loại bằng SQLSTATE và trạng thái của thao tác, thay vì dò nội dung thông báo lỗi vốn có thể thay đổi theo phiên bản hoặc ngôn ngữ.

Một số mã thường gặp:

| SQLSTATE | Tên hoặc ý nghĩa | Hướng xử lý |
|---|---|---|
| Nhóm 08, ví dụ 08000, 08003, 08006 | Lỗi kết nối; kết nối không còn tồn tại hoặc bị mất | Loại bỏ kết nối; kết quả thao tác đang chạy có thể chưa xác định |
| 08001 | Không thiết lập được kết nối | Có thể thử kết nối lại nếu còn ngân sách và dịch vụ đang phục hồi |
| 08007 | Kết quả transaction chưa xác định | Không giả định rollback; tra cứu bằng idempotency key hoặc thực hiện lại qua luồng idempotent |
| 40003 | Kết quả hoàn tất câu lệnh chưa xác định | Xử lý như kết quả chưa xác định, đặc biệt với thao tác ghi |
| 40001 | serialization_failure | Rollback và thử lại toàn bộ transaction |
| 40P01 | deadlock_detected | PostgreSQL hủy một transaction tham gia deadlock; thử lại toàn bộ transaction bị hủy |
| 55P03 | lock_not_available | Xem xét thử lại theo chính sách khóa và deadline; không retry vô hạn |
| 57P01 | admin_shutdown | Máy chủ đang shutdown; kết nối hiện tại không còn dùng được |
| 57P02 | crash_shutdown | Máy chủ đã crash; kết nối cần được tạo lại sau khi dịch vụ phục hồi |
| 57P03 | cannot_connect_now | Máy chủ tạm thời chưa nhận kết nối, thường gặp trong giai đoạn khởi động hoặc phục hồi |
| 53300 | too_many_connections | Máy chủ hết hạn mức kết nối; giảm áp lực và chờ theo backoff |
| 57014 | query_canceled | Câu lệnh bị hủy, có thể do statement_timeout hoặc yêu cầu hủy từ client |
| 25P02 | in_failed_sql_transaction | Transaction hiện tại đã ở trạng thái lỗi; cần ROLLBACK trước khi tiếp tục |
| 23505 | unique_violation | Vi phạm ràng buộc duy nhất; thường là lỗi dữ liệu hoặc xung đột idempotency cần xử lý, không phải lỗi để retry mù |

Các thư viện JDBC, driver và connection pool có thể bọc lỗi SQL trong exception khác. Khi phân loại, hãy đi theo chuỗi nguyên nhân để lấy SQLSTATE nếu có, đồng thời ghi nhận liệu lỗi xuất hiện lúc lấy connection, lúc thực thi câu lệnh hay trong commit. Một số lỗi mạng ở tầng TCP có thể không mang SQLSTATE PostgreSQL.

Không phải lỗi nào có vẻ tạm thời cũng nên retry. Ví dụ:

- Lỗi cú pháp, thiếu bảng, thiếu cột hoặc sai kiểu dữ liệu cần sửa câu lệnh hay schema.
- Lỗi xác thực và phân quyền cần sửa thông tin đăng nhập hoặc quyền.
- 23505 có thể là dấu hiệu yêu cầu đã được xử lý trước đó; ứng dụng phải tra cứu bản ghi idempotency thay vì chạy lại cùng câu lệnh.
- 57014 có thể phản ánh câu truy vấn quá chậm hoặc người dùng chủ động hủy. Retry ngay có thể làm tăng tải mà không giải quyết nguyên nhân.
- 25P02 là trạng thái tiếp theo sau một lỗi trước đó. Cần tìm lỗi gốc trong transaction, rollback, rồi mới quyết định có retry hay không.

## 3. Retry đúng đơn vị: toàn bộ transaction

Khi PostgreSQL trả 40001 hoặc 40P01, transaction bị hủy. Ứng dụng phải rollback hoặc đóng kết nối theo trạng thái thực tế, sau đó chạy lại toàn bộ transaction từ đầu trên kết nối mới hoặc transaction mới.

Không chỉ chạy lại câu lệnh cuối cùng. Các câu lệnh đọc trước đó có thể đã tạo ra quyết định nghiệp vụ dựa trên snapshot hoặc thứ tự khóa cũ. Chạy riêng câu lệnh cuối có thể tạo kết quả không nhất quán.

Ví dụ, một transaction chuyển tiền có thể thực hiện:

1. Đọc số dư tài khoản nguồn.
2. Kiểm tra số dư đủ để chuyển.
3. Trừ tiền ở tài khoản nguồn.
4. Cộng tiền ở tài khoản đích.
5. Ghi hai dòng sổ cái.
6. COMMIT.

Nếu transaction bị deadlock hoặc serialization failure, hãy chạy lại cả sáu bước trong một transaction mới. Không retry riêng bước trừ tiền hoặc cộng tiền.

Một quy tắc thực tế:

- 40001 và 40P01: thường phù hợp để retry toàn transaction với số lần hữu hạn.
- Lỗi kết nối: tạo connection mới và đưa yêu cầu qua luồng idempotent. Không dựa vào việc client có nhận được phản hồi của COMMIT hay không.
- 55P03: chỉ retry nếu nghiệp vụ cho phép chờ khóa và deadline còn đủ; cần xem lại nguyên nhân tranh chấp khóa.
- 53300, 57P03 hoặc lỗi dịch vụ tạm thời: retry kết nối có backoff, đồng thời hạn chế số request đồng thời.
- Lỗi dữ liệu, cú pháp, xác thực và phân quyền: trả lỗi hoặc xử lý theo nghiệp vụ; không retry tự động.

### Backoff, jitter và giới hạn retry

Retry liên tục có thể làm tình trạng quá tải nặng hơn. Nếu hàng nghìn request cùng retry ngay sau khi database phục hồi, chúng tạo thành một đợt tải dồn dập.

Một chính sách thường dùng là exponential backoff có full jitter:

    delay = random(0, min(cap, base × 2^(attempt - 1)))

Trong đó:

- attempt là số lần thử hiện tại, bắt đầu từ 1.
- base là thời gian chờ cơ sở.
- cap là giới hạn thời gian chờ tối đa.
- random chọn ngẫu nhiên trong khoảng từ 0 đến giới hạn đã tính.

Ví dụ minh họa, base 100 ms và cap 2 giây. Lần retry đầu có thể chờ ngẫu nhiên từ 0 đến 100 ms; các lần sau tăng dần nhưng không vượt 2 giây. Giá trị thực tế cần căn cứ SLA, độ trễ bình thường và thời gian phục hồi của hệ thống.

Chính sách retry phải có đủ các giới hạn:

- Số lần thử tối đa.
- Tổng deadline của yêu cầu, tính cả thời gian chờ connection pool, kết nối, thực thi và backoff.
- Giới hạn số thao tác retry đồng thời.
- Jitter để các client không đồng bộ retry cùng lúc.
- Cơ chế dừng hoặc giảm tải khi database đang quá tải.

Không để mỗi tầng trong hệ thống tự retry nhiều lần mà không có ngân sách chung. Ví dụ API retry 4 lần, service retry 4 lần và driver retry 4 lần có thể biến một yêu cầu thành hàng chục lần truy cập database. Hãy xác định rõ tầng nào chịu trách nhiệm retry và truyền deadline xuống các tầng dưới.

## 4. Thiết kế idempotency cho thao tác ghi

Một thao tác là idempotent nếu thực hiện lặp lại cùng một yêu cầu không làm thay đổi kết quả nghiệp vụ so với thực hiện một lần. Ví dụ, đặt trạng thái đơn hàng thành PAID có thể idempotent nếu cập nhật có điều kiện và lưu được kết quả; cộng thêm 100 vào số dư mỗi lần nhận request thì không idempotent.

Idempotency key là mã duy nhất đại diện cho một ý định nghiệp vụ. Client tạo key một lần cho yêu cầu ban đầu và gửi lại đúng key đó trong mọi lần retry. Key phải được giữ ổn định qua timeout, mất kết nối, retry ở API gateway và retry ở worker. Không tạo key mới cho mỗi lần thử.

Bảng sau minh họa nơi lưu key và kết quả:

    CREATE TABLE request_dedup (
        idempotency_key uuid PRIMARY KEY,
        request_hash bytea NOT NULL,
        response jsonb,
        created_at timestamptz NOT NULL DEFAULT now()
    );

Trong hệ thống nhiều tenant hoặc nhiều loại thao tác, có thể dùng khóa chính ghép như (tenant_id, operation, idempotency_key). Phạm vi khóa phải bảo đảm hai khách hàng hoặc hai loại thao tác không vô tình dùng chung không gian key.

Quy trình xử lý trong một transaction:

1. Chuẩn hóa payload và tính request_hash. Hash đại diện cho nội dung nghiệp vụ, không bao gồm thông tin thay đổi theo lần thử như timestamp của request.
2. INSERT idempotency key với ON CONFLICT DO NOTHING và RETURNING.
3. Nếu INSERT tạo được bản ghi mới, transaction hiện tại sở hữu việc xử lý yêu cầu. Thực hiện các thay đổi nghiệp vụ.
4. Lưu response cuối cùng vào cùng bản ghi idempotency.
5. COMMIT cả bản ghi idempotency, thay đổi nghiệp vụ và response trong cùng transaction.
6. Nếu INSERT không tạo bản ghi mới, đọc bản ghi đã có. So sánh request_hash. Nếu hash khớp, trả response đã lưu. Nếu hash khác, từ chối vì cùng một key đang bị dùng cho hai nội dung yêu cầu khác nhau.

Ví dụ phần SQL khởi đầu:

    INSERT INTO request_dedup (idempotency_key, request_hash)
    VALUES ($1, $2)
    ON CONFLICT (idempotency_key) DO NOTHING
    RETURNING idempotency_key;

Nếu câu lệnh trả về một dòng, transaction hiện tại có thể tiếp tục xử lý nghiệp vụ. Nếu không có dòng trả về, thực hiện SELECT request_hash, response FROM request_dedup WHERE idempotency_key = $1 trong câu lệnh tiếp theo. Với mức cô lập mặc định READ COMMITTED, câu SELECT tiếp theo nhận snapshot mới và có thể đọc bản ghi đã commit của request trước. Nếu hệ thống dùng REPEATABLE READ hoặc SERIALIZABLE, xung đột đồng thời có thể dẫn đến serialization failure; khi đó retry toàn transaction theo quy tắc 40001.

Ví dụ phần cập nhật nghiệp vụ và lưu kết quả:

    UPDATE accounts
    SET balance = balance - $1
    WHERE account_id = $2
      AND balance >= $1;

    -- Ứng dụng phải xác nhận đúng một dòng được cập nhật.
    -- Sau đó ghi ledger và tạo response nghiệp vụ.

    UPDATE request_dedup
    SET response = $3::jsonb
    WHERE idempotency_key = $4;

Đoạn SQL trên chỉ minh họa cấu trúc. Trong ứng dụng thật, phải kiểm tra số dòng được cập nhật, xác thực số tiền dương, khóa đúng tài khoản, ghi ledger trong cùng transaction và rollback nếu bất kỳ điều kiện nghiệp vụ nào không đạt.

### Vì sao bản ghi idempotency và thay đổi nghiệp vụ phải cùng transaction?

Nếu lưu key trước rồi mới cập nhật số dư ở transaction khác, tiến trình có thể crash giữa hai bước. Lần retry thấy key đã tồn tại và tưởng yêu cầu hoàn tất, trong khi số dư chưa thay đổi. Nếu cập nhật số dư trước rồi mới lưu key ở transaction khác, tiến trình có thể crash sau khi cộng tiền nhưng trước khi lưu key; lần retry sẽ cộng tiền lần nữa.

Khi key, thay đổi nghiệp vụ và response được commit nguyên tử:

- Nếu transaction rollback, cả key và thay đổi nghiệp vụ đều không tồn tại; lần retry có thể xử lý lại.
- Nếu transaction commit, cả key và thay đổi nghiệp vụ đều tồn tại; lần retry nhận ra key và trả response đã lưu.
- Nếu client mất phản hồi COMMIT, lần retry trên connection mới sẽ xác định kết quả bằng cách tra cứu key.

Bản ghi idempotency không nên được xóa sớm hơn thời gian mà client, message broker hoặc hệ thống trung gian có thể gửi lại yêu cầu. Nếu key hết hạn trong khi một request cũ vẫn có thể được gửi lại, thao tác có nguy cơ được thực hiện lần nữa. Thời hạn lưu cần dựa trên quy tắc nghiệp vụ và thời gian retry tối đa.

Không cho phép tái sử dụng cùng key với payload khác. So sánh request_hash giúp phát hiện lỗi phía client hoặc hành vi gửi request sai. Cần quy định cách chuẩn hóa payload trước khi hash để thứ tự thuộc tính JSON hoặc định dạng số không làm hai nội dung tương đương bị coi là khác nhau.

## 5. Idempotency khi có tác động ra hệ thống bên ngoài

Transaction PostgreSQL chỉ bảo đảm nguyên tử đối với dữ liệu do chính transaction đó quản lý. Nó không thể COMMIT nguyên tử cùng một lời gọi HTTP đến cổng thanh toán, email service hoặc message broker độc lập.

Ví dụ, ứng dụng trừ tiền trong PostgreSQL rồi gọi API thanh toán. Nếu API thanh toán xử lý thành công nhưng kết nối bị mất trước khi trả phản hồi, ứng dụng không biết khoản thanh toán đã được thực hiện hay chưa. Rollback database không thể thu hồi tác động đã xảy ra ở hệ thống bên ngoài.

Một mẫu phổ biến là transactional outbox:

    CREATE TABLE outbox (
        event_id uuid PRIMARY KEY,
        event_type text NOT NULL,
        payload jsonb NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        published_at timestamptz
    );

Trong cùng transaction nghiệp vụ, ứng dụng cập nhật dữ liệu và INSERT event vào outbox. Sau khi commit, một worker đọc outbox và gửi event đến hệ thống đích. Worker có thể gửi lại nếu không nhận được xác nhận.

Outbox giải quyết việc không bị mất event giữa thay đổi database và việc phát event, nhưng bản thân nó không tạo ra exactly-once delivery. Worker có thể gửi event thành công rồi crash trước khi đánh dấu published_at. Khi chạy lại, worker sẽ gửi event lần nữa.

Vì vậy, consumer nên có inbox hoặc bảng processed_messages với event_id là khóa duy nhất. Consumer ghi nhận event_id và thay đổi nghiệp vụ của nó trong cùng transaction. Nếu nhận lại cùng event_id, consumer bỏ qua tác động đã xử lý và trả kết quả phù hợp. Với API thanh toán, hãy dùng idempotency key do nhà cung cấp hỗ trợ nếu có.

Một luồng an toàn thường có các bước:

1. API nhận yêu cầu với idempotency key.
2. PostgreSQL commit thay đổi nghiệp vụ và outbox event trong cùng transaction.
3. Worker lấy event chưa gửi, đánh dấu lease hoặc trạng thái xử lý trong một transaction ngắn rồi commit.
4. Worker gọi hệ thống ngoài với event_id ổn định làm idempotency key.
5. Worker đánh dấu đã gửi sau khi nhận kết quả.
6. Nếu worker crash ở giữa, event có thể được gửi lại; hệ thống đích hoặc consumer phải loại bỏ tác động trùng.

Không giữ transaction database mở trong thời gian dài chỉ để chờ HTTP. Cách đó giữ lock và connection, làm tăng nguy cơ cạn pool. Nếu cần claim event, dùng lease có thời hạn hoặc một cơ chế claim ngắn; thiết kế để việc gửi lặp vẫn an toàn.

Nếu hệ thống ngoài không hỗ trợ idempotency và không có cách tra cứu kết quả, không thể khẳng định retry sẽ không tạo tác động trùng. Khi đó cần quy trình đối soát, trạng thái nghiệp vụ chờ xác nhận hoặc thao tác bù trừ theo đặc thù hệ thống.

## 6. Xử lý connection pool và thời gian chờ

Connection pool tái sử dụng các session PostgreSQL để giảm chi phí mở kết nối. Điều này giúp tăng hiệu năng nhưng tạo thêm một số trường hợp lỗi:

- Kết nối nhàn rỗi đã bị firewall, proxy hoặc máy chủ đóng.
- Database vừa restart hoặc failover nhưng pool vẫn giữ socket cũ.
- Kết nối bị hỏng sau một lần timeout và được trả nhầm về pool.
- Pool cạn vì request giữ connection quá lâu hoặc transaction bị bỏ quên.
- Số kết nối từ nhiều instance ứng dụng cộng lại vượt quá khả năng của PostgreSQL.

Ứng dụng nên cấu hình pool có giới hạn, kiểm tra hoặc loại bỏ kết nối không hợp lệ theo khả năng của thư viện, đặt thời gian sống phù hợp với hạ tầng mạng và đóng connection trong mọi nhánh xử lý. Kiểm tra bằng SELECT 1 chỉ cho biết kết nối hoạt động tại thời điểm kiểm tra; nó không bảo đảm câu lệnh tiếp theo hoặc COMMIT sẽ thành công.

Các timeout cần được phân biệt:

| Timeout | Phạm vi | Mục đích |
|---|---|---|
| connect_timeout | Client/driver | Giới hạn thời gian thiết lập kết nối |
| statement_timeout | PostgreSQL | Hủy câu lệnh vượt quá thời gian cho phép |
| lock_timeout | PostgreSQL | Không chờ khóa quá lâu |
| idle_in_transaction_session_timeout | PostgreSQL | Đóng session bỏ không trong transaction |
| Timeout phía client hoặc socket | Driver/runtime | Giới hạn thời gian client chờ phản hồi |

Ví dụ xem một số cấu hình phía PostgreSQL:

    SHOW statement_timeout;
    SHOW lock_timeout;
    SHOW idle_in_transaction_session_timeout;

Có thể đặt timeout riêng cho transaction bằng SET LOCAL để giới hạn phạm vi áp dụng:

    BEGIN;
    SET LOCAL lock_timeout = '500ms';
    SET LOCAL statement_timeout = '5s';
    -- Thực hiện các câu lệnh nghiệp vụ.
    COMMIT;

Giá trị chỉ là ví dụ. Timeout phải phù hợp với deadline của request và thời gian xử lý hợp lệ của truy vấn. Nếu statement_timeout hủy câu lệnh, transaction thường chuyển sang trạng thái lỗi và cần ROLLBACK trước khi tiếp tục. Không coi timeout của client là bằng chứng PostgreSQL đã hủy câu lệnh; server có thể vẫn đang xử lý nếu việc hủy chưa đến nơi.

Không đặt pool quá lớn với kỳ vọng càng nhiều connection càng tốt. Tổng connection từ tất cả instance ứng dụng, worker, migration và công cụ quản trị phải nằm trong giới hạn an toàn của server. Một pool chờ có giới hạn thường tốt hơn việc tạo vô hạn connection và nhận 53300.

## 7. Xây dựng luồng retry trong ứng dụng

Luồng xử lý nên tách ba trách nhiệm:

- Hàm nghiệp vụ thực hiện các bước database trong một transaction.
- Bộ phân loại lỗi xác định lỗi nào có thể retry dựa trên SQLSTATE và giai đoạn thực thi.
- Bộ điều phối retry quản lý deadline, số lần thử, backoff và idempotency key.

Pseudocode sau minh họa cách tổ chức. Các hàm evictConnection, isConnectionFailure và sleepWithJitter phụ thuộc thư viện ứng dụng:

    Result handleRequest(UUID key, Payload payload) {
        byte[] hash = canonicalHash(payload);

        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            try (Connection connection = pool.getConnection()) {
                connection.setAutoCommit(false);

                try {
                    Result result = applyIdempotently(
                        connection, key, hash, payload
                    );
                    connection.commit();
                    return result;
                } catch (SQLException error) {
                    if (isConnectionFailure(error)) {
                        evictConnection(connection);
                        // Không kết luận transaction đã rollback.
                        // Lần thử kế tiếp dùng cùng key và hash.
                    } else {
                        rollbackIfPossible(connection);
                        if (!isRetryableTransactionAbort(error)) {
                            throw error;
                        }
                    }
                }
            } catch (SQLException connectionOrPoolError) {
                if (!isRetryableConnectionError(connectionOrPoolError)) {
                    throw connectionOrPoolError;
                }
            }

            if (attempt == MAX_ATTEMPTS || deadlineExceeded()) {
                break;
            }
            sleepWithJitter(attempt);
        }

        throw new RetryExhaustedException(key);
    }

Pseudocode này thể hiện nguyên tắc, không phải lớp Java có thể biên dịch trực tiếp. Khi triển khai:

- Hàm applyIdempotently phải dùng cùng key, hash và transaction để lưu kết quả như phần trước.
- Nếu commit ném lỗi kết nối, không được coi đó là rollback. Connection phải bị loại khỏi pool; lần thử tiếp theo tra cứu cùng key trên connection mới.
- Với lỗi 40001 hoặc 40P01, rollback transaction và chạy lại toàn bộ hàm nghiệp vụ.
- Với lỗi kết nối, driver có thể không cho rollback vì socket đã hỏng. Đóng hoặc evict connection là cần thiết; không dùng lại đối tượng connection đó.
- Không nuốt exception không retry được. Cần trả lỗi đúng cho caller hoặc chuyển sang quy trình đối soát nếu kết quả chưa xác định.
- Không tạo idempotency key mới trong vòng lặp.

Nếu một yêu cầu đã hết deadline, không nên tiếp tục retry chỉ vì vẫn còn số lần thử. Hãy trả trạng thái phù hợp để client có thể tra cứu hoặc gửi lại cùng key. API có thể cung cấp endpoint tra cứu trạng thái yêu cầu theo key, giúp client giải quyết trường hợp timeout mà không phải đoán.

## 8. Thiết kế kịch bản kiểm thử mất kết nối

Kiểm thử chỉ dừng ở việc tắt PostgreSQL rồi bật lại chưa đủ. Cần chủ động làm lỗi ở nhiều thời điểm của vòng đời transaction, đặc biệt là cửa sổ quanh COMMIT.

Có thể dùng môi trường PostgreSQL riêng, Docker, Toxiproxy hoặc công cụ fault injection mạng để tạo lỗi có kiểm soát. Trong môi trường thử nghiệm, có thể dùng pg_terminate_backend để kết thúc backend PostgreSQL của một session. Không thực hiện thao tác phá kết nối trên database production.

Lấy PID của session đang kiểm thử:

    SELECT pg_backend_pid();

Từ một session có đủ quyền, có thể kết thúc backend mục tiêu:

    SELECT pg_terminate_backend(<pid>);

Lệnh này làm session tương ứng bị kết thúc; nó hữu ích để kiểm tra ứng dụng nhận biết connection bị đóng và loại bỏ connection khỏi pool. Nó không thay thế hoàn toàn việc cắt mạng ở đúng thời điểm COMMIT, vì vậy cần thêm proxy hoặc failpoint nếu muốn kiểm thử phản hồi COMMIT bị mất.

Ma trận kịch bản nên bao gồm:

| Kịch bản | Cách tạo lỗi | Điều cần xác nhận |
|---|---|---|
| Database chưa sẵn sàng | Dừng PostgreSQL trước khi ứng dụng kết nối | Retry kết nối có giới hạn; request không tạo thay đổi |
| Session bị kết thúc khi truy vấn chạy | Dùng pg_terminate_backend trên backend thử nghiệm | Driver báo lỗi; pool loại bỏ connection; request được xử lý lại an toàn |
| Mất kết nối sau câu lệnh ghi, trước COMMIT | Ngắt session trước khi gửi COMMIT | Transaction chưa commit không để lại dữ liệu một phần |
| Mất phản hồi COMMIT | Dùng proxy cắt chiều phản hồi sau khi server xử lý COMMIT | Client không giả định rollback; retry cùng key chỉ có một tác động |
| PostgreSQL restart hoặc failover | Khởi động lại primary hoặc chuyển primary trong môi trường thử nghiệm | Ứng dụng kết nối lại đúng node ghi và xử lý kết quả chưa xác định |
| Deadlock | Hai transaction khóa cùng hai hàng theo thứ tự ngược nhau | Một transaction nhận 40P01; toàn transaction được retry |
| Serialization failure | Chạy giao dịch đồng thời ở isolation SERIALIZABLE với xung đột có thể tái hiện | 40001 làm toàn transaction được chạy lại |
| Pool chứa connection cũ | Giữ connection nhàn rỗi rồi restart database hoặc đóng socket | Connection cũ bị phát hiện và không được cấp lại liên tục |
| Hết connection | Giới hạn pool/server rồi tạo tải đồng thời | Hệ thống không retry dồn dập; deadline và backoff được giữ |
| Hai request đồng thời cùng key | Gửi song song cùng key và cùng payload | Chỉ một transaction tạo tác động; request còn lại nhận cùng kết quả |
| Cùng key nhưng payload khác | Gửi lại key cũ với nội dung đã thay đổi | Request bị từ chối rõ ràng; không tạo tác động thứ hai |

### Kiểm tra deadlock bằng hai session

Tạo hai hàng thử nghiệm trong bảng accounts, sau đó mở hai session.

Session A:

    BEGIN;
    UPDATE accounts SET balance = balance - 1 WHERE account_id = 1;
    -- Chờ session B cập nhật hàng thứ hai.
    UPDATE accounts SET balance = balance + 1 WHERE account_id = 2;
    COMMIT;

Session B:

    BEGIN;
    UPDATE accounts SET balance = balance - 1 WHERE account_id = 2;
    -- Chờ session A cập nhật hàng thứ nhất.
    UPDATE accounts SET balance = balance + 1 WHERE account_id = 1;
    COMMIT;

Nếu hai session giữ khóa theo thứ tự ngược nhau, PostgreSQL có thể phát hiện deadlock và hủy một transaction với SQLSTATE 40P01. Ứng dụng cần retry toàn bộ transaction bị hủy. Trong hệ thống thật, nên thống nhất thứ tự lấy khóa để giảm deadlock, nhưng vẫn cần xử lý trường hợp deadlock có thể xảy ra.

### Kiểm tra idempotency dưới tải đồng thời

Gửi nhiều request đồng thời với cùng idempotency key và payload. Sau khi tất cả hoàn tất, truy vấn database để kiểm tra:

- Chỉ có một bản ghi request_dedup cho key đó.
- Chỉ có một thay đổi nghiệp vụ tương ứng, chẳng hạn một ledger entry cho thao tác.
- Các request thành công nhận cùng một response nghiệp vụ.
- Không có transaction bị bỏ quên hoặc bản ghi trạng thái xử lý dở dang ngoài thiết kế.

Sau đó gửi cùng key với payload khác. Ứng dụng phải phát hiện request_hash không khớp và từ chối request. Không được âm thầm trả kết quả của payload cũ như thể payload mới đã được xử lý.

### Kiểm tra cửa sổ COMMIT

Đây là bài kiểm thử quan trọng nhất cho thao tác ghi:

1. Gửi request với một idempotency key đã tạo trước.
2. Để PostgreSQL thực hiện transaction và xử lý COMMIT.
3. Dùng proxy hoặc failpoint cắt phản hồi từ server về client trước khi client nhận xác nhận COMMIT.
4. Xác nhận client ghi nhận kết quả chưa xác định và không phát sinh key mới.
5. Gửi lại request với đúng key và payload ban đầu.
6. Xác nhận ứng dụng đọc response đã lưu nếu transaction trước đã commit; nếu transaction trước chưa commit, request mới xử lý và commit đúng một lần.
7. Đối chiếu số dư, ledger, bản ghi idempotency và event outbox.

Chỉ kiểm tra HTTP status hoặc exception ở client là chưa đủ. Cần kiểm tra dữ liệu cuối cùng trong PostgreSQL để biết hệ thống có tạo tác động trùng hay bỏ sót tác động không.

## 9. Tiêu chí đánh giá kết quả kiểm thử

Một bài kiểm thử phục hồi tốt cần thu thập bằng chứng ở cả phía ứng dụng và database.

Ở phía ứng dụng, ghi nhận:

- SQLSTATE và loại lỗi gốc.
- Giai đoạn phát sinh lỗi: lấy connection, thực thi SQL hay COMMIT.
- Số lần retry, thời gian backoff và tổng thời gian request.
- Việc connection bị loại khỏi pool.
- Kết quả cuối cùng: thành công, lỗi có thể retry, lỗi không retry hoặc kết quả chưa xác định cần tra cứu.
- Idempotency key đã được dùng, có thể log dạng hash/rút gọn để tránh lộ thông tin không cần thiết.

Ở phía PostgreSQL, có thể quan sát session bằng:

    SELECT
        pid,
        usename,
        application_name,
        state,
        wait_event_type,
        wait_event,
        xact_start,
        query_start
    FROM pg_stat_activity
    WHERE datname = current_database()
    ORDER BY xact_start NULLS LAST;

Không ghi toàn bộ payload nhạy cảm vào log query hoặc log ứng dụng chỉ để phục vụ retry. Hãy dùng request ID, operation name và key đã được bảo vệ để liên kết các sự kiện.

Các chỉ số hữu ích gồm tỷ lệ lỗi kết nối, số connection bị evict, số lần retry theo SQLSTATE, tỷ lệ retry thành công, số lần idempotency key được dùng lại, số request hết retry budget, thời gian chờ pool và số connection đang hoạt động. Nếu retry tăng mạnh nhưng tỷ lệ thành công không tăng, hệ thống có thể đang khuếch đại sự cố.

Một kết quả kiểm thử đạt yêu cầu cần chứng minh:

1. Kết nối hỏng được loại bỏ và ứng dụng có thể lấy kết nối mới sau khi PostgreSQL phục hồi.
2. 40001 và 40P01 dẫn đến retry toàn transaction, không retry riêng câu lệnh cuối.
3. Mất phản hồi COMMIT không dẫn đến giả định sai rằng transaction đã rollback.
4. Yêu cầu được gửi lại với cùng key không tạo thêm tác động nghiệp vụ.
5. Cùng key với payload khác bị từ chối.
6. Retry có giới hạn, có backoff và không vượt deadline.
7. Pool không giữ connection hỏng và không tạo bão kết nối khi database chưa sẵn sàng.
8. Outbox và consumer chịu được event được gửi lại.

## 10. Những sai lầm thường gặp

**Retry câu lệnh cuối cùng sau mọi lỗi.** Cách này bỏ qua snapshot, các bước kiểm tra và các thay đổi trước đó trong transaction. Với lỗi transaction có thể retry, phải chạy lại toàn bộ đơn vị nghiệp vụ.

**Coi timeout là rollback.** Timeout ở client chỉ cho biết client ngừng chờ. PostgreSQL có thể đã hoàn thành transaction hoặc vẫn đang xử lý nếu lệnh hủy chưa đến nơi. Với thao tác ghi, cần idempotency và khả năng tra cứu kết quả.

**Tạo idempotency key mới mỗi lần retry.** Khi đó mỗi lần thử được coi là một ý định mới, làm mất tác dụng chống trùng. Key phải được tạo ở ranh giới request nghiệp vụ và giữ nguyên trong toàn bộ vòng đời retry.

**Lưu key và dữ liệu nghiệp vụ ở hai transaction khác nhau.** Crash giữa hai transaction có thể làm hệ thống đánh dấu đã xử lý nhưng chưa tạo tác động, hoặc tạo tác động nhưng không có dấu vết chống trùng.

**Retry mọi SQLSTATE.** Lỗi cú pháp, quyền truy cập, dữ liệu và constraint thường không tự hết khi chờ. Retry mù chỉ tăng tải và che khuất lỗi gốc.

**Chỉ kiểm thử bằng cách tắt database.** Cách đó không tái hiện được tình huống server đã commit nhưng client mất phản hồi. Cần kiểm thử riêng cửa sổ quanh COMMIT.

**Cho rằng outbox bảo đảm gửi đúng một lần.** Outbox bảo đảm event được lưu cùng transaction nghiệp vụ. Việc chuyển event vẫn có thể lặp; consumer phải deduplicate.

**Giữ transaction mở trong lúc gọi dịch vụ ngoài.** Điều này kéo dài thời gian giữ connection và lock. Hãy ghi outbox rồi xử lý bên ngoài transaction.

## 11. Bài tập thực hành

1. Tạo một API chuyển tiền có idempotency key. Gửi cùng request ba lần và xác minh chỉ có một lần ghi ledger.
2. Dùng hai session tạo deadlock. Quan sát SQLSTATE 40P01 và sửa ứng dụng để retry toàn transaction.
3. Chạy transaction ở isolation SERIALIZABLE với hai request đồng thời có xung đột. Quan sát 40001 và xác minh lần chạy lại đọc dữ liệu mới.
4. Kết thúc backend PostgreSQL trong lúc ứng dụng đang thực hiện thao tác ghi. Xác minh connection pool loại bỏ session cũ và request không tạo tác động trùng.
5. Dùng proxy cắt phản hồi COMMIT. Gửi lại cùng key và kiểm tra cả response lẫn dữ liệu nghiệp vụ.
6. Tạo một outbox event, cho worker gửi event thành công rồi dừng worker trước khi đánh dấu published. Khởi động lại worker và xác minh consumer chỉ áp dụng tác động một lần.
7. Giới hạn connection để tạo lỗi 53300. Quan sát backoff, deadline, pool wait và hành vi khi retry budget hết.

Khi hoàn thành các bài tập, người học cần giải thích được vì sao mất kết nối trong lúc COMMIT tạo ra kết quả chưa xác định, vì sao lỗi 40001 và 40P01 yêu cầu chạy lại toàn transaction, và cách idempotency key kết hợp transaction PostgreSQL để bảo vệ thao tác ghi khỏi việc gửi lặp.
