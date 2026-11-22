# Xóa log theo yêu cầu — Quyền riêng tư trong Java Logging

## 1. Xóa log theo yêu cầu là gì?

Log của ứng dụng Java chứa sự kiện vận hành, lỗi, truy vết request, thông tin bảo mật và đôi khi có **dữ liệu cá nhân**. “Xóa log theo yêu cầu” là quy trình tiếp nhận một yêu cầu về dữ liệu, xác minh quyền, tìm những bản ghi liên quan trong toàn bộ hệ thống logging, đánh giá dữ liệu nào phải xóa hoặc được giữ hợp lệ, thực hiện biện pháp kỹ thuật rồi **xác minh và phản hồi đúng phạm vi**.

Một số ví dụ:

~~~text
INFO  orderId=42 userId=user-7 outcome=SUCCESS
ERROR request failed email=person@example.invalid
INFO  healthcheck status=OK
AUDIT userId=user-7 action=ROLE_CHANGED result=SUCCESS
~~~

Không thể chỉ xóa dòng chứa userId=user-7 và tuyên bố hoàn tất: cùng chủ thể có thể xuất hiện qua email, IP, deviceId hoặc mã giao dịch. Dòng audit thay đổi quyền lại có thể thuộc diện cần giữ vì nghĩa vụ pháp lý hoặc điều tra phù hợp. Và ngay cả khi xóa file ứng dụng, một bản sao đã có thể nằm ở log collector, search index, archive, backup hoặc file export.

**Mục tiêu đúng:** bảo vệ dữ liệu cá nhân mà không xóa nhầm sự kiện của chủ thể khác, không phá hủy chứng cứ cần lưu và không báo “đã xóa hết” khi mới xử lý một phần.

**Không phải chức năng có sẵn của SLF4J:** các lời gọi logger.info(), logger.error() hoặc Logback/Log4j 2 Appender không có phương thức chung để xóa chọn lọc một sự kiện đã được ghi vào mọi sink. Đây là một bài toán quản lý vòng đời dữ liệu xuyên suốt pipeline.

## 2. Xác định dữ liệu cá nhân có thể nằm trong log

| Loại dữ liệu | Ví dụ | Lưu ý khi xác định phạm vi |
| --- | --- | --- |
| Định danh trực tiếp | email, userId, số điện thoại, tên | Thường có thể liên kết tới một chủ thể cụ thể |
| Định danh gián tiếp | IP, deviceId, sessionId, correlationId | Có thể tái nhận dạng khi kết hợp với hệ thống khác |
| Metadata nghiệp vụ | orderId, documentId, accountId | Phụ thuộc khả năng liên kết qua bảng dữ liệu nghiệp vụ |
| Nội dung lỗi | exception message, request URL, query string | Dễ vô tình ghi PII vào trường message tự do |
| Dữ liệu bảo mật/audit | lần đăng nhập, thay đổi quyền, truy cập bị từ chối | Có thể cần lưu có căn cứ và giới hạn quyền truy cập |
| Bản sao log | stdout, rotating files, search index, snapshot, archive | Cùng một sự kiện tồn tại ở nhiều nơi |

**Hash userId không mặc nhiên làm nó vô danh.** Nếu còn bảng ánh xạ, khóa liên kết, hoặc mã có thể bị đoán và kết hợp với dữ liệu khác thì vẫn có rủi ro nhận dạng. Pseudonymization giảm tính trực tiếp nhưng không phải lúc nào cũng đáp ứng yêu cầu xóa/khử nhận dạng hoàn toàn.

Không đưa password, access token, API key, session cookie, dữ liệu thanh toán đầy đủ hoặc nguyên request body có thông tin nhạy cảm vào log ngay từ đầu. Sau khi thông tin đã được thu thập hoặc xuất ra bên ngoài, việc xóa sau này không thể làm người đã đọc mất khả năng nhớ hoặc lưu bản sao riêng.

## 3. Căn cứ pháp lý và những trường hợp phải giữ lại

Quyền yêu cầu xóa **không đồng nghĩa quyền xóa tất cả chứng cứ trong mọi trường hợp**. Việc quyết định xóa, hạn chế xử lý hoặc giữ bản ghi phải dựa vào luật áp dụng, mục đích xử lý, nghĩa vụ lưu trữ, lịch sử sự cố và chính sách đã được phê duyệt.

**Việt Nam, tại thời điểm 2026:** Luật Bảo vệ dữ liệu cá nhân **91/2025/QH15** có hiệu lực **01/01/2026**, thừa nhận các quyền liên quan tới dữ liệu cá nhân, gồm quyền yêu cầu xóa. Điều 14 đề cập xóa, hủy và khử nhận dạng dữ liệu; khi áp dụng cần xem các trường hợp, giới hạn liên quan, bao gồm Điều 19. **Nghị định 356/2025/NĐ-CP**, hiệu lực cùng ngày, quy định chi tiết một số điều và biện pháp thi hành. Tổ chức phải xem cụ thể trách nhiệm, quy trình và thời hạn theo hệ thống pháp luật áp dụng, không tự đặt một thời hạn cố định cho mọi loại log.

**Nếu GDPR áp dụng:** **GDPR Article 17** quy định quyền xóa khi có căn cứ, nhưng không phải quyền tuyệt đối; các ngoại lệ có thể bao gồm việc xử lý cần thiết để tuân thủ nghĩa vụ pháp lý hoặc thiết lập, thực hiện, bảo vệ yêu cầu pháp lý. Điều 19 còn liên quan tới việc thông báo tới các bên nhận dữ liệu trong điều kiện áp dụng.

Đây là kiến thức kỹ thuật về cách thiết kế hệ thống, **không thay thế quyết định của bộ phận pháp chế**. Đặc biệt, không lấy lý do “audit” làm ngoại lệ chung cho tất cả log: phải xác định **trường nào cần giữ, trong bao lâu và trên cơ sở nào**.

### Ma trận quyết định mẫu

| Tập log | Hướng xử lý sau khi đã đánh giá |
| --- | --- |
| DEBUG/INFO chứa PII đã hết mục đích | Xóa hoặc khử nhận dạng được xác minh |
| Lỗi kỹ thuật còn cần điều tra có thời hạn | Giới hạn truy cập, lưu tối thiểu, xóa đúng thời hạn |
| Audit/security thuộc nghĩa vụ lưu giữ hợp lệ | Giữ phần thực sự cần, bảo vệ và xác định mốc đánh giá lại |
| Dữ liệu của người khác cùng record | Không xóa mù toàn record nếu gây mất dữ liệu không thuộc phạm vi |
| Bản copy đã chuyển sang collector/index | Xử lý tại đích, không chỉ ở file nguồn |
| Backup chưa thể chỉnh sửa an toàn | Có chính sách vòng đời và cơ chế ngăn dữ liệu hồi sinh sau restore |

Khi chỉ hoàn thành được một phần, trạng thái phải là **PARTIAL_RESTRICTED** hoặc trạng thái tương đương, không được gọi là COMPLETED.

## 4. Quy trình nghiệp vụ từ yêu cầu đến xác nhận

~~~text
Nhận yêu cầu xóa (requestId)
         |
         v
Xác minh người yêu cầu / quyền đại diện
         |
         v
Xác định subject, tenant, thời gian, data map
         |
         v
Phân loại bản ghi: xóa / giữ hợp lệ / hạn chế
         |
         v
Phê duyệt phương án và dry-run
         |
         +----> file và rotated files
         +----> collector / index / dashboard copy
         +----> archive / object versions
         +----> backup / restore process
         +----> processor / đơn vị nhận dữ liệu (nếu có)
         |
         v
Thực thi có giới hạn + theo dõi job
         |
         v
Readback, đối chiếu, deletion ledger
         |
         v
Phản hồi kết quả chính xác; theo dõi phần còn lại
~~~

Một quy trình đầy đủ thường gồm:

1. **Tiếp nhận:** tạo requestId duy nhất, ghi thời điểm và loại quyền yêu cầu, không đưa nguyên nội dung PII vào ticket mở rộng quyền.
2. **Xác thực:** kiểm tra danh tính chủ thể hoặc người đại diện bằng kênh tin cậy. Không dùng giá trị userId do client tự truyền làm bằng chứng sở hữu.
3. **Khoanh vùng:** tìm những ID trực tiếp và gián tiếp liên quan; dùng tenant scope, service, loại event và khoảng thời gian.
4. **Phân loại:** quyết định xóa, hạn chế, giữ hợp lệ hoặc chuyển cho pháp chế đánh giá. Không để client tự khai báo legalHold.
5. **Lập bản đồ:** xác định mọi kho và bản sao chứa thông tin, người quản lý chúng và API/khả năng xóa thực tế.
6. **Dry-run và phê duyệt:** dự kiến số record, tính đúng bộ lọc, tác động tới người khác, backup, tính toàn vẹn audit.
7. **Thực thi:** tác vụ với quyền tối thiểu, giới hạn tài nguyên và idempotency, giám sát lỗi từng đích.
8. **Nghiệm thu:** xác minh log không còn trong phạm vi được xóa, job xử lý hoàn tất, dữ liệu không được tái ingest từ nguồn cũ.
9. **Phản hồi:** phân biệt hoàn tất, còn bản bị giữ hợp lệ, hoặc chưa xử lý xong; không cung cấp thông tin người khác.

Có thể dùng trạng thái RECEIVED → VERIFIED → APPROVED → IN_PROGRESS → COMPLETED/PARTIAL_RESTRICTED/FAILED. Trong mọi trạng thái phải rõ lý do và quyền truy cập vào báo cáo.

## 5. Vì sao phải quản lý toàn bộ chuỗi lưu trữ?

~~~text
Ứng dụng Java
   |
   +--> ConsoleAppender / stdout
   +--> FileAppender / RollingFileAppender
   +--> AsyncAppender / queue trong RAM
                   |
                   v
             Log shipper / collector
                   |
             +-----+------+
             |            |
             v            v
         Search index   Object storage
             |            |
             v            v
         Dashboard     Archive / snapshot
                          |
                          v
                       Backup
~~~

Một event sau khi được ghi có thể tồn tại ở nhiều nơi:

- **Local:** stdout container, file chính, file đã rotate, tệp nén, log tạm trong thư mục hỗ trợ.
- **Transport:** agent, buffer hoặc queue của hệ thống chuyển log; một số bản còn chờ retry.
- **Central:** Elasticsearch/OpenSearch, hệ thống tìm kiếm log hoặc cơ sở dữ liệu truy vấn.
- **Long-term:** object storage, snapshot, WORM/immutable archive, file export và backup.
- **Bên thứ ba:** công cụ quan sát hoặc hỗ trợ kỹ thuật đã nhận dữ liệu theo hợp đồng.

**Xóa tại một chặng không có nghĩa mọi chặng đã xóa.** Ví dụ delete-by-query trong search backend không xóa file nguồn, và bản backup cũ có thể đưa dữ liệu vừa xóa trở lại index sau restore.

Cần lập **data inventory** với tên kho, owner, loại dữ liệu, policy retention, khả năng xóa theo event, loại xác nhận, lịch backup, cách restore và đơn vị liên hệ. Không lập bản đồ chỉ bằng một đường dẫn mà người phát triển nhớ được.

## 6. Khó khăn của log append-only và giới hạn framework

Logback RollingFileAppender, Log4j 2 FileAppender, JUL FileHandler thường **nối sự kiện vào file**, không cung cấp một API CRUD theo userId để xóa mọi dòng đã ghi. Nếu một file có:

~~~text
evt-101 user-A login
evt-102 user-B purchase
evt-103 user-A profile-view
~~~

Việc xóa cả file vì user-A sẽ xóa nhầm evt-102 của user-B. Thay text user-A bằng "anonymous" cũng chưa chắc làm hết thông tin nhận dạng nếu còn timestamp, IP, email hoặc mã giao dịch ở chỗ khác.

Những phương án kỹ thuật cần cân nhắc:

1. **Lifecycle theo segment:** phù hợp khi mọi log trong một segment có cùng thời hạn và có thể hết hạn theo thời gian; không giải quyết mọi trường hợp xóa từng người trước hạn.
2. **Viết lại file có kiểm soát:** dừng/điều phối writer, đọc bản nguồn, loại hoặc khử nhận dạng đúng record, xác minh số sự kiện cần giữ rồi thay file an toàn theo filesystem/backend. Phải xử lý rotation, file handle đang mở và bản copy tiếp nhận.
3. **Kho có thao tác theo record:** log cấu trúc trong backend hỗ trợ xóa theo document ID hoặc query, kèm xác nhận job và snapshot.
4. **Khử nhận dạng thực sự:** loại những thuộc tính có thể liên kết lại với cá nhân, nếu hợp lệ; không chỉ xóa trường email.
5. **Crypto-erasure:** tiêu hủy khóa mã hóa tách biệt có thể làm dữ liệu không thể giải mã trong điều kiện thiết kế phù hợp; phải kiểm tra key scope, backup key, replica và khả năng ảnh hưởng người khác.

Không sử dụng một lệnh rm/truncate/sed trực tiếp trên production file đang được ghi để chứng minh xóa. Thao tác kiểu đó có thể gây mất log của người khác, làm mất chứng cứ, tạo file corrupted hoặc khiến appender vẫn ghi vào inode cũ sau rename. Cần quy trình thay thế tệp và nghiệm thu riêng nếu backend không hỗ trợ xóa có cấu trúc.

Nếu các record được ký, hash chain hoặc lưu dưới chế độ bất biến để chống sửa đổi, xóa một phần có thể phá cơ chế kiểm chứng. Không được vượt quyền phá tính toàn vẹn; phải áp dụng quy trình đã được phê duyệt hoặc thiết kế kho khác phù hợp đồng thời yêu cầu kiểm toán và quyền dữ liệu.

## 7. Ví dụ Java 17+ chạy độc lập: xóa có phạm vi và giữ hợp lệ

Ví dụ sau minh họa **logic quyết định** bằng ArrayList các sự kiện tổng hợp trong bộ nhớ. Nó thử trường hợp chưa xác minh, xóa đúng hai event, giữ có kiểm soát một event onLegalHold và không động tới dữ liệu của chủ thể khác.

**Đây không phải hàm xóa production.** Các giá trị verified và onLegalHold chỉ mô phỏng kết quả đã được kiểm tra bởi hệ thống tin cậy; không được nhận trực tiếp từ HTTP input rồi mặc nhiên tin là đúng. Đoạn mã cũng không xóa dữ liệu trên disk, collector, index, heap memory hay backup.

Tạo file **LogErasureDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.stream.Collectors;

public class LogErasureDemo {
    record LogEvent(String eventId, String subjectRef,
                    String details, boolean onLegalHold) {}

    record ErasureResult(int deleted, int restricted) {}

    static ErasureResult erase(List<LogEvent> events,
                               String subjectRef,
                               boolean verified) {
        if (!verified) {
            throw new SecurityException("Identity not verified");
        }

        int deleted = 0;
        int restricted = 0;
        for (Iterator<LogEvent> it = events.iterator(); it.hasNext();) {
            LogEvent event = it.next();
            if (!event.subjectRef().equals(subjectRef)) {
                continue;
            }
            if (event.onLegalHold()) {
                restricted++;
            } else {
                it.remove();
                deleted++;
            }
        }
        return new ErasureResult(deleted, restricted);
    }

    public static void main(String[] args) {
        List<LogEvent> events = new ArrayList<>(List.of(
            new LogEvent("evt-1", "subject-A", "profile-view", false),
            new LogEvent("evt-2", "subject-A", "login-fail", false),
            new LogEvent("evt-3", "subject-A", "case-123", true),
            new LogEvent("evt-4", "subject-B", "purchase", false)
        ));

        System.out.println("before=" + events.size());

        try {
            erase(events, "subject-A", false);
        } catch (SecurityException ex) {
            System.out.println("unauthorized=REJECTED");
        }

        ErasureResult result = erase(events, "subject-A", true);
        System.out.println("deleted=" + result.deleted());
        System.out.println("restricted=" + result.restricted());
        System.out.println("after=" + events.size());

        String ids = events.stream().map(LogEvent::eventId)
                .collect(Collectors.joining(","));
        System.out.println("remaining=" + ids);
        System.out.println("status=" +
                (result.restricted() > 0
                    ? "PARTIAL_RESTRICTED"
                    : "COMPLETED"));
    }
}
~~~

Lệnh biên dịch và chạy:

~~~bash
javac LogErasureDemo.java
java LogErasureDemo
~~~

Stdout xác định của ví dụ:

~~~text
before=4
unauthorized=REJECTED
deleted=2
restricted=1
after=2
remaining=evt-3,evt-4
status=PARTIAL_RESTRICTED
~~~

Giải thích:

- Yêu cầu chưa xác thực bị chặn, không có bản ghi nào bị sửa.
- evt-1 và evt-2 thuộc subject-A và không có cờ lưu giữ, được loại khỏi danh sách.
- evt-3 thuộc subject-A có onLegalHold=true, tạm được giữ có kiểm soát; **legal hold phải là quyết định có căn cứ** từ hệ thống/pháp chế, không phải một flag tùy ý.
- evt-4 thuộc subject-B không bị ảnh hưởng.
- Kết quả PARTIAL_RESTRICTED cho biết chưa thể xác nhận đã xóa tất cả dữ liệu liên quan.

List.remove() chỉ loại phần tử khỏi một danh sách, không tẩy dữ liệu ở heap ngay, không xóa file và không thích hợp làm API xóa log thực tế cho nhiều thread hay nhiều bản sao. Đoạn này nhằm dạy **xác thực – khoanh vùng – phân loại – ghi nhận kết quả**, không phải một giải pháp bảo mật hoàn chỉnh.

Một event có thể liên quan nhiều chủ thể; mô hình có mỗi subjectRef chưa giải quyết trường hợp đó. Khi dùng thật, phải có schema, mapping và kiểm tra PII nằm trong nhiều field.

## 8. Xóa trong Elasticsearch/OpenSearch hoặc kho log có index

Nhiều kho log cho xóa theo document ID, query hoặc thời gian; nhưng syntax, quyền và trạng thái thực thi khác nhau theo phiên bản. Một quy trình an toàn:

1. Định nghĩa query ràng buộc **tenant, subject ID đã xác minh, index allowlist và khoảng thời gian**.
2. Chạy dry-run/count hoặc truy vấn metadata phù hợp; xem số document dự kiến trước khi cho xóa.
3. Phê duyệt và chạy batch có giới hạn; không cho request tự xây wildcard trên mọi index.
4. Ghi lại task/job ID; đợi xử lý xong, kiểm tra lỗi, shard failures, timeout và retry.
5. Đọc lại theo đúng criteria, so sánh ID còn lại; kiểm tra event được bảo lưu hợp lệ.
6. Chặn nguồn **re-ingest/replay** từ file/queue/archive cũ, tránh log vừa xóa quay lại.
7. Đánh giá replica, snapshot, bản export và thời điểm xóa vật lý theo semantics của backend.

**HTTP 200 hoặc “task submitted” không tương đương hoàn tất xóa trên tất cả bản lưu.** Trong một số công cụ, deletion có thể là thao tác bất đồng bộ và segment vật lý được thu hồi sau. Hệ thống cần báo cáo rõ loại hoàn tất đang xác nhận.

Không cung cấp một lệnh delete-by-query với điều kiện chung chung để copy chạy trên production, vì cấu trúc index, trường định danh, version và policy có thể khác.

## 9. Archive, WORM và object storage

Đối với archive và object storage, cần phân biệt:

- **Delete object:** loại một object theo khả năng API và chính sách storage.
- **Versioning:** delete marker không nhất thiết loại bỏ mọi phiên bản cũ.
- **Object lock/WORM/legal hold:** có thể cố ý ngăn chỉnh sửa hoặc xóa trước hạn.
- **Object chứa nhiều chủ thể:** xóa cả object có thể gây mất dữ liệu hợp lệ của nhiều người.
- **Bản copy từ bên thứ ba:** có thể nằm ngoài quyền xóa trực tiếp của service Java.

Nếu cần xóa chọn lọc trong một object chứa nhiều event, phải có chiến lược lưu trữ theo phân vùng thích hợp, đọc/ghi lại an toàn hoặc mô hình kho hỗ trợ record-level operations. Không chủ động phá bảo vệ WORM chỉ để hoàn thành một yêu cầu; cần đánh giá cơ sở lưu giữ, hạn chế truy cập và thời điểm xử lý theo chính sách.

Crypto-erasure chỉ đáng tin nếu khóa của dữ liệu mục tiêu được quản lý tách biệt, đã loại mọi bản sao khóa không được phép, không làm mất dữ liệu người khác và có kiểm thử khôi phục. **Xóa một encryption key dùng chung cho cả bucket không phải xóa chọn lọc một user.**

## 10. Backup và rủi ro “hồi sinh” dữ liệu

Backup là phần dễ bị bỏ quên khi xử lý quyền xóa. Xóa ở index chính rồi khôi phục snapshot cũ có thể tái tạo dữ liệu đã được xóa.

Một thiết kế cần trả lời:

- Backup/snapshot chứa những tập log nào, giữ tới khi nào?
- Có thể xử lý object/phiên bản một cách có chọn lọc hay phải chờ lifecycle hết hạn?
- Ai có quyền khôi phục, và dữ liệu khôi phục có được công khai ngay hay không?
- **Deletion ledger/tombstone** có được lưu độc lập và áp dụng lại trước khi cho hệ thống phục hồi phục vụ traffic?
- Có thử tình huống restore từ bản backup trước ngày yêu cầu xóa không?

Nếu backup không thể sửa/xóa lẻ do thiết kế hoặc nghĩa vụ lưu giữ, cần chính sách riêng về quyền truy cập, xử lý khi phục hồi, thời gian tồn tại và phản hồi người yêu cầu. **Không tuyên bố “xóa tất cả bản sao”** nếu chưa có bằng chứng về trạng thái này.

Một bước khôi phục an toàn là: restore vào môi trường cách ly → đọc deletion ledger → áp dụng lại các yêu cầu xóa còn hiệu lực → kiểm tra → mới mở quyền truy cập phù hợp. Kỹ thuật cụ thể phụ thuộc backend, luật và chính sách dữ liệu.

## 11. Deletion ledger và audit kết quả xóa

Muốn xử lý lặp, lỗi từng phần và nhiều kho, cần lưu trạng thái tối thiểu theo requestId:

~~~json
{
  "requestId": "dsr-0042",
  "receivedAt": "2026-11-10T02:00:00Z",
  "scopeVersion": "privacy-map-v3",
  "status": "PARTIAL_RESTRICTED",
  "processedStores": ["logs-index", "rotated-logs"],
  "pendingStores": ["backup-lifecycle"],
  "deletedEventCount": 120,
  "restrictedEventCount": 3,
  "policyDecisionRef": "approval-007"
}
~~~

Các giá trị chỉ minh họa. Ledger không nên sao chép message có PII vừa bị xóa. Nếu cần ánh xạ requestId với một người cụ thể, lưu nó ở kho bảo vệ riêng và tuân thủ vòng đời dữ liệu phù hợp.

Yêu cầu kỹ thuật:

- **Idempotent:** chạy lại cùng requestId không tự động xóa thêm dữ liệu khác.
- **Có tracking:** per-store progress, job ID, lỗi, số record, thời gian, phương pháp kiểm chứng.
- **Có kiểm soát quyền:** xóa và xem ledger là thao tác nhạy cảm.
- **Trạng thái trung thực:** lỗi hoặc giữ có căn cứ không bị đánh dấu completed.
- **Không phát sinh PII thừa:** audit hành động xóa không lưu lại nội dung bị xóa.
- **Có kế hoạch phục hồi:** ledger phục vụ ngăn re-ingestion/restore làm hồi sinh record.

Một bản audit chỉ chứa requestId, policy version, jobId, result và số liệu tối thiểu có thể đủ để chứng minh thao tác đã diễn ra mà không lưu lại email/địa chỉ/ID thực của chủ thể ở nơi mở rộng quyền.

## 12. Xóa một phần record và khử nhận dạng

Không phải lúc nào xóa cả record cũng là cách duy nhất hoặc đúng: một event có thể liên quan chủ thể A và B, hoặc là chứng cứ hợp lệ cho một giao dịch của B. Khi đó cần đánh giá:

1. Có thể xóa toàn bộ record không?
2. Có thể loại field trực tiếp và gián tiếp liên quan A mà vẫn giữ phần có mục đích hợp lệ?
3. Các field còn lại có thể kết hợp để nhận dạng A không?
4. Có bảng ánh xạ hoặc khóa nào khiến “anonymous ID” vẫn liên kết được với A?
5. Việc thay đổi record có phá chứng cứ audit, chữ ký hoặc khả năng kiểm tra tính toàn vẹn không?
6. Phần được giữ có được giới hạn quyền truy cập và lịch xóa phù hợp không?

**Masking ở giao diện** khác với deletion và anonymization: ẩn cột email trên dashboard không xóa email khỏi index, file và backup. Thay userId bằng giá trị cố định cũng chưa chắc là khử nhận dạng nếu timestamp + IP + orderId còn phân biệt được người.

Với log cần chứng cứ không thể sửa đổi, nên thiết kế cơ chế giữ **metadata tối thiểu** tách khỏi phần thông tin cá nhân không bắt buộc, thay vì ghi tất cả vào một dòng text không thể xử lý.

## 13. Ngăn phải xóa bằng data minimization

Phương án hiệu quả nhất là **không ghi dữ liệu cá nhân không cần thiết vào LogEvent ngay từ đầu**.

### 13.1. Thiết kế event có cấu trúc

Ưu tiên các field ổn định như eventId, service, eventCode, status, latencyMs, requestId, thay vì ghi nguyên object hoặc request body. Khi cần liên hệ chủ thể, sử dụng mapping được kiểm soát và đánh giá vòng đời của chính mapping đó.

### 13.2. Không ghi secret

Không log password, token, session cookie, API key, private key, payment card data hay raw Authorization header. Với lỗi, tránh đưa email hoặc user input vào exception message nếu không cần. Đừng lấy nguyên URL query khi nó có thể chứa dữ liệu cá nhân.

### 13.3. Phân loại nguồn log

Tách application/debug logs khỏi security/audit logs để có retention, ACL và chính sách truy xuất/xóa phù hợp. Không dùng logger level DEBUG/INFO làm tiêu chí pháp lý cho việc có được giữ dữ liệu hay không.

### 13.4. Retention theo mục đích

Chọn hạn lưu theo loại dữ liệu, yêu cầu vận hành và nghĩa vụ pháp lý, không giữ toàn bộ log vô hạn chỉ vì ổ đĩa còn trống. Kiểm tra việc rotation/lifecycle có xóa thật hay chỉ chuyển file sang thư mục archive khác.

### 13.5. Kiểm tra library và môi trường

Log từ HTTP client, JDBC, framework, reverse proxy, background job và container có thể phát PII độc lập với logger trong ứng dụng. Không chỉ review lời gọi log.info của code tự viết.

## 14. Giới hạn quyền và chống xóa nhầm

Một deletion service có thể trở thành công cụ phá chứng cứ nếu quyền quá rộng. Cần:

- **Xác thực người yêu cầu:** quyền đối với đúng chủ thể, tenant và vai trò đại diện.
- **Định nghĩa điều kiện xóa cố định:** không cho caller tự chọn tên index hoặc regex không kiểm soát.
- **Allowlist:** giới hạn kho, namespace, loại event và thao tác.
- **Dry-run:** dự kiến số record và tác động, không phơi nguyên PII khi preview.
- **Phê duyệt:** bổ sung kiểm tra độc lập với hành động quy mô lớn, chứa chứng cứ quan trọng.
- **Idempotency và khóa theo request:** tránh đua tranh giữa job trùng và các đợt ingest.
- **Rate limit và giới hạn lô:** tránh làm sập collector hoặc xóa sai hàng triệu record.
- **Audit độc lập:** không ghi nhật ký job vào chính file đang bị xóa.
- **Cảnh báo:** khi job bị lỗi, bất thường số lượng hoặc phát hiện query ngoài tenant.

Một tham số HTTP như userId=someone-else không phải chứng cứ người gọi có quyền xóa dữ liệu của someone-else. Không để role/legalHold được quyết định bằng boolean tự báo trên client.

## 15. Kiểm thử và tiêu chí nghiệm thu

Dùng môi trường test với **dữ liệu tổng hợp**, không chạy thử xóa trên log chứa người dùng thật.

### Ma trận kiểm thử

| Ca | Kỳ vọng |
| --- | --- |
| Chưa xác minh danh tính | Từ chối, không thay đổi dữ liệu |
| Yêu cầu chỉ chủ thể A | Không xóa event riêng của B |
| A có email ở message và userId ở metadata | Tìm đủ qua schema/mapping, không chỉ một chuỗi |
| Event của A thuộc diện giữ có căn cứ | Không xóa sai; hạn chế và báo PARTIAL_RESTRICTED |
| Event có cả A và B | Áp dụng quyết định theo field/record, không tự xóa bừa |
| Job đang chạy bị ngắt | Retry cùng requestId không gây xóa lệch |
| File đang rotate hoặc queue còn event | Không mất event của người khác, không ingest lại event cần xóa |
| Index xóa bất đồng bộ | Đợi job hoàn tất và kiểm tra lại |
| Backup trước ngày yêu cầu xóa | Restore không làm dữ liệu bị xóa xuất hiện lại |
| Object versioning/WORM | Không nhầm delete marker thành loại bỏ hết mọi bản |
| Quyền operator không đủ | Thao tác bị từ chối, có ghi nhận an toàn |

### Tiêu chí xác nhận

Một yêu cầu chỉ được coi hoàn tất trong phạm vi đã phê duyệt khi:

1. Đã xác minh quyền và chính sách xử lý.
2. Data inventory bao phủ mọi location liên quan.
3. Mọi job tại nơi có khả năng xóa đã hoàn tất, không còn lỗi chưa xử lý.
4. Truy vấn lại theo ID/tenant và mọi key liên quan xác nhận không còn dữ liệu phải xóa.
5. Không có pipeline ingest/replay làm event quay lại.
6. Archive/version/backup được xử lý đúng chính sách; restore gate được thử khi cần.
7. Phần giữ hợp lệ được ghi lý do, hạn truy cập và thời điểm đánh giá lại.
8. Phản hồi không đánh đồng **completed**, **partial** và **failed**.

Metric gợi ý: pending_deletion_requests, deletion_failures, deleted_event_count, restricted_event_count, oldest_pending_request_age, restore_replay_pending. Không đưa email/userId trực tiếp vào metric label.

## 16. Lỗi thường gặp

**“Xóa application.log là hoàn tất.”** Sai nếu file có log của nhiều người và đã có collector/index/backup. Xóa file chung có thể gây mất dữ liệu của người khác.

**“Đã cấu hình retention 7 ngày nên không cần xử lý yêu cầu xóa.”** Hết hạn định kỳ có giá trị nhưng phải đối chiếu yêu cầu và luật áp dụng; không mặc nhiên đủ cho mọi trường hợp.

**“Không thấy email trong dashboard là đã xóa.”** Dashboard có thể chỉ ẩn field, còn index, file và bản sao vẫn chứa dữ liệu.

**“Hash userId là vô danh.”** Nếu hash có thể liên kết, đảo đoán hoặc có bảng mapping thì vẫn có nguy cơ tái nhận dạng.

**“Backup không cần xử lý vì là read-only.”** Backup có thể đưa dữ liệu quay lại sau restore; cần retention và cơ chế chống hồi sinh.

**“Mọi log audit luôn miễn xóa.”** Phải xem mục đích và cơ sở giữ cụ thể, dữ liệu tối thiểu và thời hạn.

**“Lệnh xóa trả 200 nghĩa là tất cả replica/snapshot đã xóa.”** Nhiều backend xử lý async hoặc giữ version khác; cần kiểm tra job và phạm vi đích.

**“Chỉ cần tìm đúng userId.”** Event có thể chứa email, IP, correlationId, orderId và các liên kết khác. Cần dữ liệu có cấu trúc và data inventory.

**“Đổi message thành [REDACTED] là không còn PII.”** Các metadata khác có thể tái nhận dạng, và bản gốc có thể vẫn tồn tại trong file/segment, cache hoặc backup.

**“Có thể rollback bằng cách khôi phục dữ liệu vừa xóa.”** Khôi phục không có kiểm soát có thể vi phạm trạng thái quyền riêng tư đã cam kết; cần restore gate và deletion ledger.

## 17. Checklist triển khai

- [ ] Có kênh tiếp nhận và xác minh yêu cầu xóa hợp lệ.
- [ ] Có quy trình đánh giá căn cứ pháp lý và loại event được giữ.
- [ ] Biết những field PII trực tiếp/gián tiếp và nguồn mapping tương ứng.
- [ ] Có inventory cho local file, rotated log, collector, index, archive, snapshot, backup và export.
- [ ] Mọi job xóa bị giới hạn theo tenant, subject, time range và quyền tối thiểu.
- [ ] Có dry-run, approval và cảnh báo số lượng bất thường.
- [ ] Xử lý được event của nhiều chủ thể mà không xóa nhầm dữ liệu người khác.
- [ ] Có deletion ledger/tombstone idempotent và audit thao tác tối thiểu.
- [ ] Readback hậu xóa và theo dõi async task/ingest/retry đầy đủ.
- [ ] Có vòng đời backup và ngăn dữ liệu hồi sinh sau restore.
- [ ] Tách rõ trạng thái hoàn tất, giữ hợp lệ, lỗi và công việc còn chờ.
- [ ] Retention và data minimization được thiết kế ngay từ nguồn log.
- [ ] Kiểm thử riêng với file append-only, WORM, versioning, async pipeline và snapshot.

**Kết luận:** Xóa log theo yêu cầu là một **quy trình quyền riêng tư và quản trị vòng đời dữ liệu**, không phải tính năng delete có sẵn của logger. Muốn xử lý đúng phải đồng thời hiểu quyền của chủ thể, cơ sở lưu giữ, cấu trúc event, các bản sao, đặc tính của sink và cách kiểm chứng. Phòng ngừa tốt nhất là **không ghi PII không cần thiết**, đặt retention phù hợp và thiết kế đường xóa có kiểm soát ngay từ đầu.

## 18. Tài liệu tham khảo

- [Luật Bảo vệ dữ liệu cá nhân 91/2025/QH15 — Cổng văn bản Chính phủ](https://vanban.chinhphu.vn/?classid=1&docid=214590&pageid=27160&typegroup=): quyền của chủ thể, quy định xóa, hủy và khử nhận dạng; hiệu lực 01/01/2026.
- [Nghị định 356/2025/NĐ-CP — Cổng văn bản Chính phủ](https://vanban.chinhphu.vn/?classid=1&docid=216387&pageid=27160): quy định chi tiết và thi hành Luật Bảo vệ dữ liệu cá nhân.
- [GDPR, Regulation (EU) 2016/679 — Articles 17, 19](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32016R0679): quyền xóa, ngoại lệ và các nghĩa vụ liên quan.
- [Irish Data Protection Commission — The Right to Erasure](https://www.dataprotection.ie/en/individuals/know-your-rights/right-erasure-articles-17-19-gdpr): diễn giải quyền xóa và giới hạn theo GDPR.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): dữ liệu cần loại khỏi log, quản lý lưu giữ, xử lý bản sao và tiêu hủy.
- [OWASP Logging Vocabulary Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Vocabulary_Cheat_Sheet.html): ghi nhận sự kiện xóa dữ liệu nhạy cảm mà không sao chép lại nội dung.
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html): appender file/rolling và giới hạn đường xuất.
- [Apache Log4j 2 — Appenders](https://logging.apache.org/log4j/2.x/manual/appenders.html): cách xuất log ra các đích khác nhau.
- [Java SE 17 — java.util.logging](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/package-summary.html): logging API và Handler, không có API xóa record trên mọi sink.
