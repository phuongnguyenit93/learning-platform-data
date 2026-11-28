# Database console proxy

## 1. Database console proxy là gì?

Database console proxy là một điểm trung gian cho truy cập tương tác tới database. Người dùng đi qua một console hoặc cổng truy cập, được xác thực và kiểm tra quyền, rồi hệ thống thiết lập kết nối tới database theo phạm vi đã được cấp.

Console có thể là giao diện web hoặc một luồng cấp truy cập cho công cụ SQL trên máy người dùng. Proxy có thể hiểu giao thức database, kết thúc kết nối và tạo kết nối phía sau, hoặc chỉ chuyển tiếp dữ liệu. Kiến trúc thực tế quyết định hệ thống nhìn thấy và kiểm soát được gì.

Trong PAM, mục tiêu thường là:

- Liên kết truy cập database với danh tính cá nhân.
- Cấp quyền đúng mục đích và trong khoảng thời gian phù hợp.
- Hạn chế phân phối credential quản trị cho người dùng.
- Kiểm soát đích kết nối.
- Ghi nhận hoạt động đủ để đối soát.
- Thu hồi quyền và xử lý phiên khi công việc kết thúc.

Các mục tiêu này là yêu cầu thiết kế, không phải tính năng mặc định của mọi proxy.

Một tunnel TCP chỉ nhìn thấy kết nối không tự trở thành bộ kiểm soát từng câu SQL. Một connection pooler cũng không tự có MFA, phê duyệt hay JIT chỉ vì nó nằm giữa client và database.

Sau bài học, bạn có thể xác định ranh giới kiểm soát của một database console proxy, thiết kế ánh xạ danh tính và credential, và kiểm chứng cả sử dụng lẫn kết thúc đặc quyền.

## 2. Phân biệt các kiểu trung gian

| Kiểu thành phần | Năng lực điển hình | Cần kiểm chứng thêm khi dùng cho PAM |
|---|---|---|
| Bastion hoặc tunnel | Tạo đường mạng tới database | Danh tính database, phạm vi quyền, mức ghi nhận SQL |
| Proxy giao thức database | Xử lý một phần giao thức kết nối | Những chế độ truy vấn, xác thực và mã hóa được hỗ trợ |
| Console SQL trên web | Nhận thao tác người dùng rồi gọi database | Quyền backend, session, xuất dữ liệu và bảo vệ trình duyệt |
| Connection pooler | Tái sử dụng kết nối phía database | Cách giữ hoặc tách ngữ cảnh của từng người |
| Broker credential | Cấp credential cho client sử dụng | Đường truy cập trực tiếp và khả năng thu hồi phiên đã mở |
| Cổng truy cập đặc quyền | Điều phối danh tính, phê duyệt và phiên | Mức tích hợp thực sự với database và các đường đi vòng |

Một sản phẩm có thể kết hợp nhiều kiểu. Điều quan trọng là mô tả đúng những chức năng đã cấu hình và kiểm thử.

### Ví dụ ranh giới quan sát

Nếu TLS được thiết lập trực tiếp từ client tới database và proxy chỉ chuyển tiếp byte, proxy không có nội dung SQL rõ để phân tích. Nếu proxy kết thúc TLS, nó trở thành một điểm xử lý dữ liệu và credential nhạy cảm.

Hai lựa chọn tạo ra trách nhiệm khác nhau. Thiết kế cần xác định điểm nào xác minh danh tính, điểm nào thực thi quyền và điểm nào giữ bằng chứng.

## 3. Luồng truy cập đặc quyền

Một luồng minh họa gồm:

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant G as Cổng truy cập
    participant P as Proxy phiên
    participant V as Kho hoặc broker credential
    participant D as Database
    participant A as Hệ thống bằng chứng

    U->>G: Yêu cầu truy cập gắn với tác vụ và đích
    G->>G: Xác thực, kiểm tra quyền và phê duyệt
    G->>P: Cho mở phiên có phạm vi và thời hạn
    P->>V: Nhận credential hoặc danh tính backend
    V-->>P: Bằng chứng truy cập được giới hạn
    P->>D: Kết nối tới đích đã được duyệt
    D-->>P: Kết quả xác thực và quyền database
    P-->>U: Console hoặc kênh sử dụng được phép
    P->>A: Sự kiện phiên và thao tác theo khả năng thực tế
    G->>P: Hết hạn hoặc thu hồi
    P->>D: Xử lý phiên backend theo chính sách
    P->>A: Bằng chứng kết thúc và ngoại lệ
~~~

Đây là kiến trúc khái niệm. Không yêu cầu mọi triển khai phải có từng thành phần độc lập.

### Ba ranh giới quyền

1. Quyền vào cổng và yêu cầu truy cập.
2. Quyền dùng proxy để tới một database cụ thể.
3. Quyền thực hiện thao tác bên trong database.

Được phép mở console Orders không có nghĩa được đọc mọi schema hoặc tạo người dùng mới. Quyền ở database vẫn cần được thiết kế theo tác vụ.

## 4. Khai báo đích bằng định danh được quản lý

Một yêu cầu tốt nên chọn tài nguyên đã đăng ký, chẳng hạn orders-reporting-prod, thay vì cho người dùng nhập host, port và tài khoản backend tùy ý.

Hồ sơ tài nguyên có thể gồm:

- Instance hoặc cụm database.
- Môi trường và chủ sở hữu.
- Engine và phiên bản liên quan.
- Endpoint cùng cơ chế xác minh máy chủ.
- Database hoặc catalog được phép.
- Role hoặc danh tính có thể cấp.
- Phạm vi dữ liệu.
- Cấu hình ghi nhận và kế hoạch thu hồi.
- Những đường truy cập trực tiếp còn được phép.

Nếu cổng nhận địa chỉ tùy ý, nó có thể trở thành đường tới đích ngoài phạm vi hoặc làm credential bị đưa tới máy chủ không tin cậy. Cần kiểm tra đích từ phía hệ thống và bảo vệ cấu hình ánh xạ.

### Phê duyệt gắn với đích và hành động

Yêu cầu:

> Cần xem dữ liệu đã che của Orders production để xác minh lỗi báo cáo, chỉ trong phạm vi tác vụ SUPPORT-EX-024.

Có ích hơn yêu cầu:

> Cần mở SQL console.

Phê duyệt cần liên kết chủ thể, tài nguyên, role, mục đích, thời hạn và điều kiện. Nếu đổi sang instance khác hoặc role mạnh hơn, không tái dùng dấu “đã duyệt” cho tập đầu vào mới mà không đánh giá lại.

## 5. Danh tính ở cổng và danh tính tại database

### 5.1. Danh tính cá nhân ở phía trước

Mỗi người nên xác thực bằng danh tính có thể quy trách nhiệm. Tài khoản console dùng chung khiến khó xác định ai đã mở và dùng phiên.

Một phiên đặc quyền có thể cần:

- Xác thực phù hợp rủi ro.
- Xác thực lại khi bắt đầu tác vụ nhạy cảm.
- Kiểm tra trạng thái nhân sự và nhóm.
- Phê duyệt độc lập nếu cần.
- Mã yêu cầu và lý do.
- Thời gian hiệu lực.
- Scope cụ thể.

Chỉ có MFA không thay cho kiểm tra quyền database. Một người xác thực mạnh vẫn có thể không được phép sửa dữ liệu.

### 5.2. Các mô hình danh tính backend

| Mô hình | Ưu điểm có thể đạt | Trách nhiệm cần xử lý |
|---|---|---|
| Tài khoản database riêng cho từng người | Database có danh tính phân biệt trực tiếp | Cấp phát, quyền và thu hồi từng người |
| Danh tính hoặc credential riêng cho từng phiên | Liên kết tốt với một lease truy cập | Tạo, kết thúc, đối soát và dọn hiện vật |
| Danh tính trung gian rồi chuyển role có kiểm soát | Tách đăng nhập khỏi role tác vụ | Bảo vệ khả năng đổi role và ngữ cảnh phiên |
| Tài khoản backend dùng chung | Tương thích một số hệ thống cũ | Bằng chứng ánh xạ ở proxy, phạm vi credential và nguy cơ quy trách nhiệm sai |

Không mô hình nào tự giải quyết toàn bộ PAM. Lựa chọn phụ thuộc engine, proxy và khả năng vận hành.

Nếu database chỉ thấy cùng một backend account cho mọi người, cần một chuỗi bằng chứng đáng tin cậy ở proxy. Không mô tả database đã có danh tính cá nhân trực tiếp trong trường hợp đó.

### 5.3. Ví dụ PostgreSQL: kiểm tra danh tính phiên

Trong phiên thử nghiệm được phép:

~~~sql
SELECT
    session_user,
    current_user,
    current_database(),
    pg_backend_pid();
~~~

PostgreSQL phân biệt danh tính phiên và ngữ cảnh thực thi; các hàm trên hỗ trợ quan sát database cùng backend hiện tại. [PostgreSQL: Session Information Functions](https://www.postgresql.org/docs/current/functions-info.html).

Nếu hệ thống dùng chuyển role, current_user có thể khác session_user. Quyền chuyển role phải được quản lý; SET ROLE là một thay đổi ngữ cảnh quyền có quy tắc riêng, không phải một nhãn audit tùy ý. [PostgreSQL: SET ROLE](https://www.postgresql.org/docs/current/sql-set-role.html).

Kết quả truy vấn là một điểm quan sát. Nó chưa chứng minh người ở đầu console là ai nếu database account được chia sẻ.

## 6. Credential backend và bảo vệ hai chặng kết nối

### 6.1. Proxy không nên phát credential quản trị dài hạn cho người dùng

Một mục tiêu thiết kế là để người dùng dùng phiên được kiểm soát mà không trực tiếp giữ bí mật backend rộng.

Có thể dùng:

- Credential riêng theo người hoặc phiên.
- Credential ngắn hạn do cơ chế được hỗ trợ cấp.
- Certificate hoặc liên kết danh tính phù hợp nền tảng.
- Credential lưu trong vault với quyền truy xuất hạn chế.

Trong mỗi trường hợp cần xác định nguồn cấp, thời hạn, quyền, consumer và khả năng kết thúc hiệu lực.

Credential nằm trong vault vẫn có thể quá rộng. Nếu proxy lấy cùng một tài khoản quản trị cho mọi tác vụ, quyền backend chưa đạt least privilege chỉ nhờ việc người dùng không nhìn thấy mật khẩu.

### 6.2. Tách credential quản trị proxy khỏi credential kết nối tác vụ

Một thành phần tạo user tạm có thể cần quyền quản trị khác với phiên SQL của người dùng.

Không đưa cùng credential cấp phát mạnh vào mọi connection pool. Cần tách trách nhiệm, giới hạn scope và bảo vệ đường gọi thao tác quản trị.

Nếu kẻ điều khiển proxy có thể lấy mọi credential, proxy là một điểm đặc quyền cao. Cần quản lý người sửa cấu hình, mã, plugin, nguồn image, kho bí mật và điểm ghi bằng chứng của nó.

### 6.3. Bảo vệ cả client–proxy và proxy–database

Mã hóa một chặng không chứng minh chặng còn lại an toàn. Cần xác minh máy chủ đúng ở từng chặng theo cơ chế được dùng.

Với libpq, chế độ verify-full kiểm tra chuỗi tin cậy và tên máy chủ, trong khi chỉ có mã hóa không tương đương xác minh danh tính endpoint. [PostgreSQL: SSL Support](https://www.postgresql.org/docs/current/libpq-ssl.html).

Áp dụng vào kiến trúc:

- Client phải tới đúng proxy được tin cậy.
- Proxy phải kết nối đúng database đã đăng ký.
- Trust và certificate cần có chủ sở hữu cùng vòng đời.
- Không chấp nhận một lần kết nối sau khi tắt kiểm tra TLS làm bằng chứng cấu hình đã đúng.

## 7. Quyền database vẫn là ranh giới quan trọng

Một proxy có thể hỗ trợ chọn role, kiểm tra truy vấn hoặc điều phối phiên. Tuy nhiên, quyền trong engine cần bảo vệ dữ liệu ngay tại nơi thực thi.

### Phân tách theo nhu cầu

| Nhu cầu | Thiết kế quyền cần cân nhắc |
|---|---|
| Xem lỗi báo cáo | Chỉ đọc tập dữ liệu hoặc view phù hợp |
| Xác minh trạng thái vận hành | Đọc metadata cần thiết, không mặc định đọc mọi dữ liệu nghiệp vụ |
| Sửa một lỗi dữ liệu | Tác vụ sửa cụ thể, có phê duyệt và bằng chứng kết quả |
| Migration | Danh tính và cửa sổ tác vụ riêng |
| Quản lý user hoặc role | Đặc quyền riêng, không gộp vào console hỗ trợ |
| Kiểm toán | Đọc bằng chứng theo phạm vi, không sửa chính bằng chứng |

Tên role “read-only” không mô tả đầy đủ rủi ro. Người đọc có thể tiếp cận dữ liệu nhạy cảm hoặc tải dữ liệu ra ngoài nếu scope quá rộng.

Quyền sở hữu đối tượng, quyền qua role khác, hàm được cấp quyền và cơ chế chạy dưới danh tính mạnh cũng phải được xem xét trong engine cụ thể.

### Kiểm soát theo nhãn SQL là chưa đủ

Một quy tắc cho phép mọi chuỗi bắt đầu bằng SELECT không mô tả đầy đủ ngữ nghĩa SQL, hàm, câu lệnh lồng hoặc tác động của đối tượng được gọi.

Nếu proxy có bộ phân tích truy vấn, phải biết:

- Engine và dialect nào được hỗ trợ.
- Các đường query nào được phân tích.
- Tham số và prepared statement được xử lý ra sao.
- Hành vi với nội dung không hiểu.
- Có đường gọi nào đi ngoài bộ phân tích không.
- Quyền tại database có giữ được giới hạn khi bộ lọc không đủ ngữ nghĩa không.

Một tác vụ JEA có thể được đóng gói thành thao tác được duyệt thay vì cho mở console SQL tự do. Cơ chế đóng gói vẫn cần kiểm soát tham số, đối tượng đích và quyền của mã thực thi.

## 8. Proxy hiểu giao thức đến mức nào?

PostgreSQL có nhiều luồng giao thức, gồm simple query, extended query và COPY. Hệ thống kiểm soát SQL cần xét đúng những đường được client sử dụng. [PostgreSQL: Frontend/Backend Message Flow](https://www.postgresql.org/docs/current/protocol-flow.html).

Từ đó cần một ma trận khả năng:

| Đường sử dụng | Cần xác nhận |
|---|---|
| SQL console web | Cổng thực thi và audit câu lệnh nào? |
| Native client | Có cùng kiểm soát hay chỉ tạo tunnel? |
| Prepared statement | Có liên kết được bước chuẩn bị, tham số và thực thi? |
| Truy vấn nhiều statement | Chính sách áp dụng từng statement hay toàn request? |
| Import hoặc export | Dữ liệu đi qua đâu, ai được phép và có bằng chứng nào? |
| Metadata browser | Có truy cập schema ngoài nhu cầu qua tính năng khám phá không? |
| Hủy truy vấn | Có điều khiển đúng request và đúng backend không? |
| Tái kết nối | Có phải kiểm tra lại lease và danh tính không? |

Không đưa một tính năng chưa được kiểm thử vào cam kết kiểm soát chỉ vì giao diện có một lựa chọn tương tự.

Nếu chỉ kiểm soát cổng web nhưng cùng credential có thể dùng qua tunnel khác, cần ghi rõ giới hạn và xử lý đường còn lại.

## 9. Pooling và ngữ cảnh từng người dùng

Connection pooling có thể làm một phiên logic ở console không tương ứng một-một với connection tại database.

Ví dụ cụ thể, PgBouncer phân biệt session pooling và transaction pooling; ở transaction pooling, connection phía server có thể được trả về pool khi transaction kết thúc, và các tính năng dựa trên trạng thái session có giới hạn tương thích. [PgBouncer: Features](https://www.pgbouncer.org/features.html).

Không suy ra mọi proxy dùng cùng cách. Tuy nhiên, khi có pooling, thiết kế PAM cần trả lời:

- Kết nối được tách theo database user hay dùng chung?
- Một phiên logic có thể dùng nhiều backend không?
- Một backend có thể phục vụ nhiều người nối tiếp không?
- Role, cấu hình session và trạng thái transaction được xử lý thế nào?
- Có thể hủy đúng tác vụ mà không tác động người dùng khác không?
- Bằng chứng liên kết từng request với backend theo thời gian ra sao?

### Rủi ro từ trạng thái còn lại

Nếu hệ thống dùng cùng backend account rồi thay role hoặc tham số để biểu diễn người dùng, việc trả connection về pool phải bảo đảm trạng thái phù hợp trước khi cho người khác sử dụng.

Một bộ quy tắc reset không được kiểm chứng có thể tạo rò rỉ ngữ cảnh hoặc quyền. Nếu chế độ pooling không hỗ trợ mô hình session đang cần, nên đổi thiết kế thay vì giả định mọi lệnh SET sẽ được giữ đúng.

### Không dùng backend PID làm định danh duy nhất

Một phiên console có thể được ánh xạ qua nhiều backend, và định danh tiến trình còn phụ thuộc instance cùng thời điểm.

Cần mã phiên logic, instance database và dữ liệu liên kết theo thời gian. Khi cần kết thúc một backend, phải kiểm tra nó vẫn thuộc phiên cần xử lý, tránh điều khiển nhầm sau khi connection đã được tái sử dụng.

## 10. JIT: quản lý quyền và phiên đang hoạt động

Một lease truy cập nên gắn với người, mục đích, tài nguyên, role và thời hạn. Lease không chỉ là một bộ đếm trên giao diện.

Cần phân biệt các mốc:

1. Người dùng được phép yêu cầu truy cập.
2. Yêu cầu đã được phê duyệt.
3. Phiên được mở.
4. Credential backend được cấp hoặc lấy từ kho.
5. Connection database được thiết lập.
6. Quyền tại database còn hiệu lực.
7. Console đóng hoặc mất kết nối.
8. Backend và khả năng tái kết nối đã được xử lý.

Các mốc này có thể khác nhau. Thiết kế phải xác định việc gì xảy ra khi hết hạn trong lúc một transaction đang mở hoặc truy vấn dài đang chạy.

### Mô hình trạng thái minh họa

~~~text
REQUESTED
    -> APPROVED
    -> OPENING
    -> ACTIVE
    -> REVOKING
    -> CLOSED_VERIFIED
~~~

Các trường hợp cần xử lý riêng:

~~~text
OPENING_FAILED
    -> dọn credential hoặc connection tạo dở

REVOKING_INCOMPLETE
    -> chặn cấp mới
    -> tiếp tục đối soát backend
    -> ghi ngoại lệ có chủ sở hữu
~~~

Không đổi trạng thái thành CLOSED_VERIFIED chỉ vì tab trình duyệt đã biến mất.

### Thời gian và điều kiện xác thực

Một người có phiên SSO dài có thể được cấp một lease database ngắn hơn. Hết lease database không nên tự mở lại bằng cookie SSO còn tồn tại nếu yêu cầu cần phê duyệt lại.

Nếu người dùng được gia hạn, cần ghi nhận gia hạn có thẩm quyền với scope và thời hạn rõ ràng. Không để thao tác tự động retry âm thầm tạo một lease mới ngoài ý định.

Đối với truy cập nền hoặc ứng dụng thường trực, nên dùng mô hình danh tính workload riêng thay vì giả một phiên console của con người.

## 11. Kết thúc phiên: đóng console chưa chắc đã đóng database

Kế hoạch thu hồi phải xác định chính xác đối tượng cần xử lý:

- Phiên đăng nhập ở cổng.
- Lease truy cập database.
- Connection client tới proxy.
- Connection proxy tới database.
- Credential hoặc quyền backend.
- Truy vấn và transaction đang tồn tại.
- Tác vụ bất đồng bộ hoặc credential được tạo trong phiên.
- Đường truy cập trực tiếp khác.

### Hủy truy vấn và kết thúc session là hai hành động khác nhau

Trong PostgreSQL, pg_cancel_backend yêu cầu hủy truy vấn đang chạy, còn pg_terminate_backend xử lý session backend. Đây là các chức năng quản trị có kiểm tra quyền và tác động khác nhau. [PostgreSQL: Server Signaling Functions](https://www.postgresql.org/docs/current/functions-admin.html).

Vì vậy, một thiết kế “hết hạn thì cancel” chưa đủ để chứng minh người dùng không tiếp tục gửi truy vấn mới qua connection còn mở.

Bài học không yêu cầu chạy lệnh kết thúc session trên hệ thống thật. Runbook vận hành phải chọn đúng backend và đánh giá tác động transaction trước khi thực hiện.

### Credential rotation không thay kiểm chứng phiên

Thay credential để ngăn lần đăng nhập tiếp theo và xử lý connection đã xác thực là hai việc cần kiểm tra riêng.

Khi proxy giữ pool, một frontend bị đóng có thể không đồng nghĩa backend được đóng. Backend có thể được tái sử dụng cho phiên khác nếu kiến trúc cho phép. Cần hiểu điều đó trước khi áp dụng chính sách “kill toàn bộ backend của user”.

Với backend account dùng chung, một thao tác thu hồi quá rộng có thể ảnh hưởng những người hoặc ứng dụng không thuộc sự cố.

### Transaction khi kết thúc phiên

Runbook cần quy định:

- Chặn nhận statement mới ở mốc nào.
- Cho transaction hợp lệ kết thúc hay phải ngắt.
- Hành động nào đã commit, hành động nào chưa.
- Cách xử lý connection mất giữa lúc gửi hoặc nhận kết quả.
- Cách phát hiện trạng thái chưa thể kết luận.
- Điều kiện rollback hoặc xử lý bù.

Một thao tác đã commit không được hoàn tác chỉ vì console bị đóng sau đó. Khi client mất phản hồi đúng lúc commit, không được tự retry thao tác ghi nếu chưa đánh giá khả năng thực thi trùng.

## 12. Đối soát session tại database

Trong PostgreSQL, pg_stat_activity cung cấp dữ liệu về backend và trạng thái hoạt động, bao gồm thông tin kết nối, thời điểm và trạng thái transaction theo quyền quan sát. Nó không phải kho lịch sử audit đầy đủ. [PostgreSQL: Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html).

Một bộ điều khiển phiên có thể dùng nguồn quan sát phù hợp để trả lời:

- Backend nào thuộc lease đang xử lý?
- Backend bắt đầu khi nào và trên instance nào?
- Nó đang chạy truy vấn hay chờ?
- Có transaction đang mở không?
- Backend còn tồn tại sau bước kết thúc không?
- Connection đã được chuyển sang người khác qua pool chưa?

Chỉ thu thập thông tin cần thiết. Query text hoặc metadata vận hành có thể chứa dữ liệu nhạy cảm; quyền quan sát toàn hệ thống cũng là quyền cần kiểm soát.

### Mã tương quan cần đáng tin cậy

Proxy có thể gắn mã tương quan vào metadata phiên hoặc sử dụng định danh riêng. Tuy nhiên, không tin một nhãn do client tự khai là bằng chứng người dùng.

Ví dụ, PostgreSQL cho phép ứng dụng đặt application_name và hỗ trợ ghi nó trong các đầu ra log phù hợp. Do đó, trường này hữu ích để liên kết nhưng không nên là căn cứ duy nhất chứng minh danh tính cá nhân. [PostgreSQL: Error Reporting and Logging](https://www.postgresql.org/docs/current/runtime-config-logging.html).

Cần liên kết nhãn với một bản ghi phía hệ thống được bảo vệ: ai mở phiên, bằng quyết định quyền nào, backend nào được cấp và trong khoảng thời gian nào.

Nếu proxy không có khả năng tạo một liên kết đáng tin cậy tới database, phải ghi rõ giới hạn quy trách nhiệm thay vì coi một application_name có tên người là đủ.

## 13. Audit: phân biệt thao tác gửi, thực thi và kết quả

Một phiên có thể có nhiều lớp bằng chứng:

| Lớp | Có thể chứng minh | Không tự chứng minh |
|---|---|---|
| Log đăng nhập cổng | Chủ thể đã xác thực vào cổng | Đã truy cập database nào |
| Log mở phiên | Lease và đích được chọn | Quyền thực tế bên trong database |
| Log request SQL | Statement hoặc thao tác được gửi qua điểm quan sát | Database đã thực thi và commit thành công |
| Audit database | Hoạt động theo cơ chế audit của engine | Ai ở đầu console nếu backend account chia sẻ mà thiếu liên kết |
| Ghi kết quả console | Nội dung người dùng nhận qua đường được ghi | Mọi dữ liệu đã đi qua các đường khác |
| Log kết thúc | Các bước cleanup được yêu cầu | Mọi backend và credential tồn dư đã mất hiệu lực |

Khả năng ghi nhận phụ thuộc sản phẩm, giao thức và cấu hình. Không quảng bá “ghi lại mọi hoạt động database” khi mới có lịch sử câu lệnh của một giao diện web.

### Thông tin nên liên kết

- Danh tính cá nhân đã xác minh.
- Mã yêu cầu và phê duyệt.
- Tài nguyên cùng môi trường.
- Role được chọn và database principal thực tế.
- Mã phiên logic.
- Connection hoặc backend theo thời gian.
- Thao tác, thời điểm và kết quả.
- Trạng thái transaction nếu cần chứng minh tác động.
- Cách kết thúc và các ngoại lệ.

Nếu kết quả chưa được xác nhận, trạng thái phải thể hiện điều đó. Một request đã được proxy chấp nhận không đồng nghĩa thay đổi đã được lưu vào database.

### Bảo vệ bằng chứng

Người dùng phiên SQL không nên tùy ý sửa log của chính phiên đó. Quản trị proxy, quản trị database và người đọc audit có thể cần ranh giới trách nhiệm riêng.

Bảo vệ cả:

- Cấu hình bật hoặc tắt thu thập.
- Đích xuất log.
- Quyền xóa và sửa bản ghi.
- Khóa bảo vệ dữ liệu audit.
- Thời gian lưu giữ và quyền đọc.
- Cách ghi nhận khi thu thập bị gián đoạn.

Việc dùng proxy có đặc quyền rộng không thay thế kiểm soát đối với người có quyền sửa chính proxy.

## 14. Truy vấn, kết quả và xuất dữ liệu đều có thể nhạy cảm

Console làm dữ liệu dễ tiếp cận hơn, nên quyền đọc và khả năng xuất phải được phân tích cùng nhau.

Một người chỉ được đọc vẫn có thể tải nhiều dữ liệu nếu scope cho phép. Chặn nút Export chưa chứng minh dữ liệu không thể được sao chép qua kết quả query hoặc native client.

### Những câu hỏi thiết kế

- Người dùng được xem những bảng, view và cột nào?
- Có cần che hoặc tách dữ liệu nhạy cảm không?
- Có giới hạn số hàng, dung lượng hay thời gian truy vấn không?
- Các giới hạn này nằm ở giao diện, proxy hay engine?
- Người dùng có đường thực thi khác để vượt giới hạn giao diện không?
- File xuất được lưu ở đâu, ai đọc được và khi nào bị xóa?
- Bộ nhớ cache của console có giữ kết quả sau khi lease hết hạn không?
- Log SQL có chứa literal, tham số hoặc nội dung nghiệp vụ không?
- Người đọc recording có được quyền xem dữ liệu tương đương người dùng gốc không?

Các câu hỏi là yêu cầu đánh giá, không khẳng định một sản phẩm đã có sẵn mọi kiểm soát.

### Chọn mức ghi nhận theo nhu cầu

Ghi nguyên vẹn kết quả có thể tạo thêm một kho dữ liệu nhạy cảm. Chỉ lưu hash cũng không tự đủ để chứng minh người dùng đã thấy nội dung gì.

Cần xác định mục tiêu: truy vết thao tác, xác nhận thay đổi hay điều tra xuất dữ liệu. Từ đó chọn metadata, SQL, tham số hoặc kết quả phù hợp và bảo vệ tương ứng.

Không lưu mật khẩu, token hay credential backend trong URL, query log hoặc thông báo lỗi. Những chuỗi SQL chứa dữ liệu nhạy cảm cũng cần chính sách xử lý, không chỉ những trường có tên “password”.

## 15. Ngăn đường truy cập đi vòng

Một console được kiểm soát chỉ bảo vệ luồng đi qua nó. Cần đối soát các đường khác tới cùng database:

- Endpoint trực tiếp.
- VPN, bastion và tunnel khác.
- Máy của quản trị viên.
- Runner và job automation.
- Credential trong cấu hình ứng dụng.
- Công cụ sao lưu hoặc migration.
- Replica và bản sao dữ liệu.
- Giao diện quản trị của nền tảng hoặc dịch vụ cloud.

Không phải mọi đường đều phải bị loại bỏ. Nhưng mỗi đường cần chủ sở hữu, mục đích, danh tính và kiểm soát tương ứng.

### Kết hợp mạng và xác thực database

Nếu yêu cầu là chỉ cho console tương tác qua proxy, cần giới hạn đường mạng và cơ chế chấp nhận credential phù hợp. Chỉ giấu mật khẩu trên giao diện không đủ nếu cùng credential đã được phân phối ở nơi khác.

Phải bảo vệ cấu hình allowlist, endpoint và danh tính proxy. Nếu người dùng tùy ý thay đích hoặc lấy được backend credential, họ có thể không còn bị giới hạn bởi lease phía trước.

### Break-glass cần một đường rõ ràng

Khi proxy không hoạt động, có thể cần truy cập khẩn cấp. Đường này cần:

- Điều kiện và thẩm quyền sử dụng.
- Danh tính có thể quy trách nhiệm.
- Scope cùng thời hạn.
- Bằng chứng riêng.
- Đối soát thao tác và credential sau sự kiện.

Không để một tài khoản quản trị dùng chung trở thành luồng hàng ngày vì cổng chuẩn bất tiện.

## 16. Độ sẵn sàng và lỗi từng phần

Proxy trở thành một phụ thuộc của truy cập database. Thiết kế cần biết điều gì xảy ra khi một thành phần lỗi.

| Thành phần lỗi | Quyết định cần có |
|---|---|
| Nguồn danh tính | Có được mở phiên mới khi không xác minh được chủ thể không? |
| Dịch vụ phê duyệt | Yêu cầu nào có thể tiếp tục theo quyết định còn hợp lệ? |
| Vault hoặc broker | Có cơ chế lấy credential hợp lệ khác đã được duyệt không? |
| Bộ ghi bằng chứng | Có buffer được bảo vệ, giới hạn và tín hiệu xử lý không? |
| Proxy worker | Ai theo dõi và xử lý backend mà worker đã mở? |
| Database failover | Phiên mới có đi đúng đích và chịu lại điều kiện quyền không? |
| Nguồn thời gian | Thời hạn lease được đánh giá thế nào? |
| Mạng client | Có backend hoặc transaction tồn dư cần đối soát không? |

Không nên mặc định bỏ qua kiểm tra bắt buộc để mọi yêu cầu tiếp tục. Nếu tổ chức có ngoại lệ về tính sẵn sàng, cần phạm vi và thẩm quyền đã xác định.

### Cleanup cần có chủ sở hữu bền vững

Nếu chỉ lưu trạng thái phiên trong bộ nhớ của một proxy worker, worker chết có thể làm mất thông tin cleanup.

Một thiết kế có thể cần kho trạng thái lease, định danh worker, bộ đối soát và thao tác kết thúc có khả năng lặp an toàn.

Khi xử lý lặp, phải bảo đảm connection đích vẫn thuộc lease cũ. Không gửi thao tác kết thúc dựa trên một PID cũ mà không kiểm tra ngữ cảnh hiện tại.

### Hành vi failover phải được kiểm thử

Người dùng không nên tự đổi sang một database hoặc role rộng hơn khi reconnect. Đích thay thế phải thuộc cùng hợp đồng truy cập hoặc được đánh giá lại.

Đồng thời, một phiên web còn tồn tại không nên được hiểu là mọi connection mới phía sau đều được phép mở vô thời hạn.

## 17. Hồ sơ truy cập minh họa

Mẫu sau là hồ sơ điều phối, không phải cấu hình của một sản phẩm proxy cụ thể:

~~~yaml
database_console_access:
  request_reference: SUPPORT-EX-024
  user_reference: "<danh tính cá nhân đã xác minh>"
  accountable_owner: team-orders

  target:
    resource_reference: orders-reporting-training
    database: orders
    environment: training
    endpoint_reference: "<đích đã đăng ký>"

  authorization:
    task: inspect-masked-order-report
    database_role_reference: orders-report-reader
    direct_backend_credential_disclosure: forbidden
    approval_reference: APPROVAL-EX-024

  session:
    logical_session_reference: DBSESSION-EX-024
    starts_at: "<thời điểm có múi giờ>"
    ends_at: "<thời điểm có múi giờ>"
    reconnect_requires_active_lease: true
    backend_identity_mode: "<cơ chế thực tế>"
    pooling_mode_reference: "<cấu hình thực tế>"

  data_access:
    object_scope_reference: "<tập đối tượng được duyệt>"
    export_policy_reference: "<quy tắc xuất được thực thi>"
    result_retention_reference: "<vòng đời kết quả>"

  evidence:
    proxy_event_reference: EVID-PROXY-EX-024
    database_event_reference: EVID-DB-EX-024
    correlation_mapping_reference: MAP-EX-024
    raw_credential_logging: forbidden

  termination:
    procedure_reference: CLOSE-EX-024
    backend_verification_required: true
    residual_access_review_required: true
~~~

Một trường trong hồ sơ không tự tạo kiểm soát. Ví dụ, reconnect_requires_active_lease cần được thực thi trên các đường mở connection, còn backend_verification_required cần một nguồn quan sát đủ quyền và đúng phạm vi.

## 18. Tình huống thực tế: console đóng nhưng truy vấn vẫn tồn tại

### Bối cảnh

Mai được phép xem dữ liệu Orders đã che trong một khoảng truy cập ngắn. Console dùng proxy có pooling. Khi hết thời hạn, giao diện đăng xuất Mai.

Đội vận hành vẫn thấy một backend liên quan đang hoạt động. Log database ghi cùng tài khoản dùng chung cho nhiều người, nên chưa rõ backend đó còn thuộc Mai hay đã được pool tái sử dụng.

### Những điều chưa thể kết luận

- Tab đóng không chứng minh backend đã kết thúc.
- Cùng database username không chứng minh cùng người.
- PID từng được liên kết không chứng minh nó vẫn thuộc cùng lease.
- Một câu SQL trong log chưa xác nhận transaction đã commit.
- Lease hết hạn không chứng minh credential backend không còn dùng qua đường khác.

### Cách điều tra

Đội đối chiếu mã phiên logic, instance, thời gian backend, ánh xạ pool và bản ghi request. Họ xác định connection hiện còn thuộc tác vụ nào trước khi xử lý.

Nếu nguồn ánh xạ không đủ, hồ sơ phải ghi nhận giới hạn quy trách nhiệm. Không kết thúc hàng loạt backend của tài khoản dùng chung chỉ để đạt một trạng thái giao diện.

### Cải thiện thiết kế

- Ràng buộc lease với từng lần mở hoặc tái sử dụng connection.
- Tách danh tính hoặc connection theo ranh giới phù hợp.
- Ghi mapping theo transaction hoặc request nếu chế độ pooling yêu cầu.
- Xác định hành vi khi hết hạn trong lúc transaction đang mở.
- Có bộ đối soát backend sau khi frontend đóng.
- Ghi trạng thái cleanup chưa hoàn tất và người chịu trách nhiệm.
- Kiểm thử để không tác động phiên khác.

Kết quả mong muốn là kết luận có bằng chứng về cả quyền và trạng thái tại database, không chỉ một màn hình thông báo “session expired”.

## 19. Ma trận kiểm thử trước khi đưa vào sử dụng

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
| Người không có quyền yêu cầu mở Orders | Bị từ chối |
| Người có quyền nhưng chưa có phê duyệt bắt buộc | Chưa mở phiên đặc quyền |
| Đúng người, tài nguyên và role | Mở được phiên trong scope |
| Đổi tài nguyên sau phê duyệt | Đánh giá lại hoặc từ chối theo chính sách |
| Đọc view được duyệt | Thành công |
| Đọc đối tượng ngoài scope | Bị từ chối tại lớp thực thi phù hợp |
| Chuyển sang role quản trị ngoài nhu cầu | Bị từ chối |
| Dùng native client | Chịu đúng hợp đồng và ghi nhận đã tuyên bố |
| Prepared statement hoặc export | Được xử lý đúng khả năng đã kiểm chứng |
| Đường trực tiếp ngoài proxy | Không vượt chính sách truy cập tương tác |
| Credential backend được thay | Phiên mới dùng đúng credential; phiên cũ được xử lý riêng |
| Lease hết hạn khi idle | Không nhận thêm tác vụ ngoài hạn; backend được xử lý đúng |
| Lease hết hạn khi transaction mở | Thực hiện theo chính sách đã đánh giá |
| Proxy worker dừng | Không để mất ownership cleanup |
| Pool tái sử dụng backend | Không rò ngữ cảnh hoặc kết thúc nhầm người |
| Nguồn audit bị gián đoạn | Có hành vi và cảnh báo theo chính sách |
| Kết thúc phiên | Có bằng chứng cả frontend, quyền và backend trong scope |
| Mất phản hồi sau thao tác ghi | Không tự suy là thất bại rồi retry thiếu kiểm soát |

Thử trong môi trường và scope được phép. Các ca kiểm thử quyền nên chọn dữ liệu tổng hợp và thao tác ít tác động. Không cần truy cập dữ liệu production thật để chứng minh một giới hạn đã được cấu hình.

## 20. Những lỗi thường gặp

### Đồng nhất tunnel với kiểm soát SQL

Tunnel có thể quản lý đường kết nối nhưng chưa có khả năng hiểu từng thao tác database.

### Dùng backend account quản trị cho mọi người

Ẩn mật khẩu không làm giảm scope của tài khoản. Cần quyền tác vụ và bằng chứng ánh xạ phù hợp.

### Chỉ giới hạn ở giao diện

API, native client hoặc đường truy cập khác có thể không chịu cùng điều kiện.

### Tin application_name là danh tính cá nhân

Một nhãn tương quan cần đi cùng nguồn xác minh và mapping được bảo vệ.

### Ghi mọi kết quả để “đủ audit”

Recording có thể tạo kho dữ liệu nhạy cảm mới. Cần mục tiêu, phạm vi và vòng đời rõ ràng.

### Chặn nút Export rồi coi đã chặn lấy dữ liệu

Kết quả query và các client khác cũng là đường đưa dữ liệu ra ngoài.

### Thay password rồi báo đã kết thúc mọi phiên

Phải kiểm tra connection đã xác thực và quyền tại các đường khác theo engine thực tế.

### Hết hạn thì chỉ cancel truy vấn

Cancel không đồng nghĩa kết thúc mọi khả năng gửi truy vấn tiếp theo.

### Kill backend theo thông tin cũ

Trong kiến trúc pooling, có thể tác động phiên không thuộc đối tượng cần thu hồi.

### Bỏ qua trạng thái transaction

Mất kết nối, hủy truy vấn và rollback hoặc commit là các kết quả khác nhau cần đối soát.

## 21. Bài thực hành

Thiết kế một console cho đội hỗ trợ xem dữ liệu báo cáo Orders đã che trong môi trường thử nghiệm.

Yêu cầu:

- Danh tính cá nhân ở phía trước.
- Phê duyệt gắn với tài nguyên, role và thời hạn.
- Người dùng không nhận credential backend quản trị.
- Chỉ được đọc tập đối tượng đã duyệt.
- Có thể giải thích ai làm gì qua chuỗi proxy–database.
- Hết hạn phải có kế hoạch xử lý connection và transaction.
- Có kiểm thử đường đi vòng và lỗi worker.

Sản phẩm cần tạo:

1. Sơ đồ các điểm xác thực, phân quyền và ghi nhận.
2. Bản mô tả danh tính frontend và backend.
3. Hồ sơ tài nguyên cùng cơ chế xác minh endpoint.
4. Ma trận role và scope dữ liệu.
5. Chính sách lease, reconnect và kết thúc.
6. Bản phân tích pooling, correlation và reset ngữ cảnh.
7. Ma trận kiểm thử ca thành công, từ chối và thu hồi.
8. Mẫu audit không chứa credential.
9. Kế hoạch bảo vệ kết quả và file xuất.
10. Phương án break-glass cùng điều kiện đối soát sau sử dụng.

Phương án đạt cần chỉ ra nơi thực thi từng yêu cầu. Nếu proxy chỉ ghi metadata kết nối, hãy mô tả đúng giới hạn đó và bổ sung bằng chứng tại database khi cần.

## 22. Câu hỏi tự kiểm tra

**Một console có MFA đã đủ để người dùng chỉ đọc dữ liệu cần thiết chưa?**

Chưa. Còn cần quyền database, scope dữ liệu và kiểm soát các đường sử dụng thực tế.

**Vì sao cần phân biệt danh tính frontend và backend?**

Vì database có thể chỉ thấy tài khoản trung gian; muốn quy trách nhiệm phải có ánh xạ đáng tin cậy tới người dùng.

**Connection pooler có tự là một cổng PAM không?**

Không. Phải có các cơ chế danh tính, quyết định quyền, vòng đời và bằng chứng phù hợp.

**Nếu proxy không kết thúc TLS, nó có tự phân tích SQL rõ được không?**

Không thể mặc định. Khả năng quan sát phụ thuộc điểm kết thúc mã hóa và kiến trúc thực tế.

**Đóng tab console chứng minh điều gì?**

Nó có thể chỉ chứng minh frontend đã đóng. Cần đối soát lease, backend và credential riêng.

**Một request SQL được proxy ghi nhận có chứng minh dữ liệu đã thay đổi không?**

Chưa. Cần kết quả thực thi và trạng thái transaction hoặc bằng chứng phù hợp mục tiêu.

**Vì sao không nên dùng PID làm khóa đối soát duy nhất?**

Vì cần xét instance, thời gian và khả năng backend được pool tái sử dụng.

**Điều gì quyết định một phiên đã kết thúc đầy đủ?**

Những tiêu chí về frontend, quyền, credential, backend và truy cập tồn dư đều được kiểm chứng trong phạm vi hợp đồng đã xác định.
