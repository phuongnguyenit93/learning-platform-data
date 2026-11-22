# Giới hạn của CRaC đối với dữ liệu bền vững và hệ thống bên ngoài

CRaC (Coordinated Restore at Checkpoint) giúp một ứng dụng Java khởi động nhanh bằng cách tạo checkpoint của tiến trình rồi khôi phục tiến trình từ checkpoint đó. Cách làm này có thể giữ lại nhiều trạng thái đã được chuẩn bị trong JVM, chẳng hạn lớp đã nạp, đối tượng đã khởi tạo và dữ liệu đang nằm trong heap. Tuy nhiên, một ứng dụng thường không hoạt động độc lập. Nó đọc và ghi cơ sở dữ liệu, trao đổi thông điệp, gọi API, giữ kết nối mạng, sử dụng tệp và tham gia vào các cơ chế phối hợp giữa nhiều máy.

Những hệ thống bên ngoài đó tiếp tục hoạt động theo vòng đời riêng. Cơ sở dữ liệu vẫn nhận giao dịch, hàng đợi vẫn có thể nhận thông điệp, token vẫn hết hạn, lease vẫn được gia hạn hoặc bị thu hồi, và tệp trên ổ đĩa vẫn có thể thay đổi trong lúc tiến trình Java đang được lưu thành checkpoint. Vì vậy, khôi phục được JVM không đồng nghĩa với khôi phục được toàn bộ thế giới mà ứng dụng đang tương tác.

Muốn sử dụng CRaC an toàn, cần xác định rõ trạng thái nào thuộc tiến trình, trạng thái nào là dữ liệu bền vững do hệ thống khác quản lý, và trạng thái nào phải được tạo lại sau khi restore. CRaC là kỹ thuật tối ưu thời gian khởi động; nó không thay thế cơ sở dữ liệu, hệ thống lưu trữ, cơ chế giao dịch hay giao thức phối hợp phân tán.

## 1. Ranh giới của một checkpoint

Checkpoint ghi lại trạng thái của tiến trình tại một thời điểm. Tùy runtime CRaC, hệ điều hành và công cụ checkpoint/restore, ảnh có thể bao gồm trạng thái bộ nhớ của JVM cùng một phần trạng thái tiến trình và tài nguyên hệ điều hành được hỗ trợ. Sau khi restore, JVM tiếp tục từ trạng thái đã lưu và các callback phục hồi tài nguyên được gọi theo cơ chế CRaC.

Phạm vi đó có một ranh giới quan trọng:

- Heap chứa một bản sao dữ liệu mà ứng dụng đã đọc trước thời điểm checkpoint. Bản sao đó có thể trở nên cũ trong lúc ứng dụng ngừng chạy.
- Dữ liệu đã ghi và commit vào cơ sở dữ liệu vẫn do cơ sở dữ liệu quản lý. Checkpoint không quay ngược hoặc đóng băng cơ sở dữ liệu.
- Dịch vụ bên ngoài không tự dừng cùng tiến trình Java. Chúng có thể thay đổi trạng thái, đóng kết nối hoặc xử lý yêu cầu khác trong thời gian ứng dụng đang được checkpoint.
- Một số tài nguyên hệ điều hành có thể được runtime hỗ trợ khôi phục, nhưng không nên mặc định rằng mọi file descriptor, socket, khóa, thiết bị hoặc trạng thái native đều có thể tiếp tục sử dụng như trước.
- Ảnh checkpoint không phải là một giao dịch phân tán bao trùm JVM, cơ sở dữ liệu, message broker, hệ thống tệp và các dịch vụ khác.

Có thể hình dung sự khác nhau qua hai loại trạng thái:

| Loại trạng thái | Ví dụ | Ai chịu trách nhiệm về tính bền vững? |
|---|---|---|
| Trạng thái trong tiến trình | Đối tượng Java, cache trong heap, cấu hình đã nạp, cấu trúc dữ liệu tạm | Ảnh checkpoint giữ lại trạng thái tại thời điểm chụp; ứng dụng phải kiểm tra xem trạng thái đó còn hợp lệ sau restore hay không |
| Dữ liệu bền vững bên ngoài | Bản ghi trong database, tệp trên persistent volume, thông điệp đã lưu trong broker | Hệ thống lưu trữ hoặc dịch vụ bên ngoài |
| Trạng thái kết nối và phối hợp | JDBC connection, socket, session, lease, distributed lock, token | Ứng dụng và hệ thống bên ngoài phải phối hợp đóng, kiểm tra hoặc tạo lại |

Ví dụ, một đối tượng Java có thể đang giữ số dư tài khoản vừa đọc từ database. Sau checkpoint, một giao dịch khác cập nhật số dư trong database. Khi tiến trình được restore, đối tượng trong heap vẫn có thể chứa số dư cũ. JVM đã khôi phục thành công, nhưng dữ liệu trong bộ nhớ không còn phản ánh dữ liệu mới nhất.

Do đó, cần xem checkpoint là một điểm tiếp tục của tiến trình, không phải một bản sao nhất quán của toàn bộ hệ thống.

## 2. Giới hạn đối với dữ liệu bền vững

### 2.1. Cơ sở dữ liệu và giao dịch

Database thường là nguồn dữ liệu có thẩm quyền của ứng dụng. CRaC không lưu thay database, không bảo đảm một giao dịch đang chạy sẽ được commit, và cũng không bảo đảm trạng thái trong heap khớp với dữ liệu đã commit bên ngoài.

Một số tình huống cần chú ý:

1. Ứng dụng đã thay đổi một đối tượng trong heap nhưng chưa ghi thay đổi xuống database. Nếu checkpoint xảy ra, đối tượng đã thay đổi có thể được giữ lại dù dữ liệu bền vững chưa được cập nhật.
2. Ứng dụng gửi câu lệnh ghi và database đã commit, nhưng tiến trình chưa kịp cập nhật trạng thái trong heap hoặc chưa nhận được phản hồi. Sau restore, ứng dụng có thể thử thực hiện lại thao tác và tạo ra tác động trùng lặp.
3. Một transaction hoặc connection đang mở có thể không còn dùng được sau restore. Phía database có thể đã rollback transaction, đóng session hoặc hết thời gian chờ.
4. Một transaction bên ngoài có thể tiếp tục được xử lý trong khi ứng dụng đang dừng để checkpoint. Snapshot của heap và trạng thái database khi đó không tạo thành một điểm nhất quán chung.

Trước checkpoint, ứng dụng nên đưa luồng xử lý về ranh giới giao dịch rõ ràng:

- Ngừng nhận công việc mới hoặc chuyển ứng dụng sang trạng thái không nhận yêu cầu.
- Chờ các yêu cầu đang chạy hoàn tất trong một khoảng thời gian giới hạn.
- Commit những giao dịch đã hoàn tất; rollback hoặc hủy an toàn những giao dịch chưa hoàn tất theo chính sách của ứng dụng.
- Đóng connection và connection pool theo hướng dẫn của thư viện.
- Không giữ một đối tượng trong heap như bằng chứng rằng giao dịch đã được commit. Khi restore, đọc lại dữ liệu cần thiết hoặc xác minh bằng mã giao dịch và phiên bản dữ liệu.

Với thao tác có thể được gửi lại, hãy thiết kế tính idempotent. Chẳng hạn, một yêu cầu thanh toán nên có khóa idempotency ổn định được lưu ở nơi bền vững. Nếu tiến trình restore rồi gửi lại yêu cầu, dịch vụ thanh toán có thể nhận ra đó là cùng một thao tác. Khi cần phối hợp cập nhật database và phát thông điệp, có thể dùng mẫu transactional outbox để ghi sự kiện trong cùng transaction với dữ liệu nghiệp vụ, sau đó phát sự kiện bằng một tiến trình riêng.

CRaC không tự cung cấp exactly-once processing. Tính đúng đắn của giao dịch và việc chống xử lý trùng vẫn phải được giải quyết bằng transaction, idempotency key, version check, outbox hoặc giao thức phù hợp của hệ thống.

### 2.2. Tệp, thư mục và volume

Một đối tượng Java có thể giữ đường dẫn, nội dung đã đọc, vị trí đọc/ghi hoặc trạng thái bộ đệm của một tệp. Những giá trị này không bảo đảm rằng tệp bên ngoài vẫn có cùng nội dung sau restore.

Ví dụ:

- Một tiến trình khác có thể sửa, thay thế hoặc xóa tệp trong lúc ứng dụng đang được checkpoint.
- Tệp tạm trong thư mục của container có thể biến mất khi container hoặc máy được tạo lại.
- Persistent volume có thể còn nguyên, nhưng nội dung của nó vẫn có thể được cập nhật bởi một tiến trình hoặc máy khác.
- Một file descriptor, file lock, memory-mapped file hoặc vị trí đọc/ghi có thể phụ thuộc vào trạng thái hệ điều hành và môi trường triển khai. Không nên mặc định tài nguyên đó luôn hợp lệ sau restore.

Nếu dữ liệu cần tồn tại qua lần khởi động hoặc qua máy khác, hãy lưu nó trên hệ thống lưu trữ có bảo đảm phù hợp, ví dụ database, object storage hoặc persistent volume được quản lý đúng cách. Khi ghi tệp quan trọng, cần áp dụng quy trình ghi an toàn của hệ thống tệp: ghi vào tệp tạm, flush dữ liệu theo yêu cầu, rồi thay thế tệp đích bằng thao tác phù hợp. Trong Java, FileChannel.force có thể yêu cầu hệ điều hành đẩy thay đổi của kênh xuống thiết bị lưu trữ, nhưng điều đó không tự bảo đảm tính nhất quán của volume, khả năng nhân bản của storage hay tính nguyên tử của toàn bộ quy trình triển khai.

Trước checkpoint, nên đóng các tệp đang ghi sau khi hoàn tất thao tác cần thiết. Sau restore, mở lại tệp theo đường dẫn và kiểm tra trạng thái hiện tại thay vì dựa vào một handle cũ. Nếu ứng dụng cần tiếp tục ghi nối tiếp, hãy xác minh kích thước, phiên bản hoặc vị trí hợp lệ từ dữ liệu bền vững.

### 2.3. Cache và dữ liệu chỉ nằm trong bộ nhớ

Cache trong heap là trường hợp dễ gây nhầm lẫn vì checkpoint có thể giữ lại toàn bộ nội dung cache tại thời điểm chụp. Điều đó không có nghĩa cache vẫn mới khi ứng dụng hoạt động trở lại.

Trong khoảng thời gian giữa checkpoint và restore:

- Bản ghi gốc có thể được cập nhật hoặc xóa.
- TTL của cache có thể đã hết.
- Một phiên đăng nhập có thể bị thu hồi.
- Quyền truy cập hoặc cấu hình có thể đã thay đổi.
- Một khóa trong cache có thể không còn tồn tại ở hệ thống phân tán.

Hãy phân loại cache theo mức độ quan trọng. Cache có thể dựng lại nên được xóa hoặc làm mới sau restore. Cache chứa dữ liệu nhạy cảm về thời gian cần kiểm tra TTL và phiên bản. Nếu cache được dùng như nguồn dữ liệu duy nhất cho một nghiệp vụ, cần xem lại thiết kế vì dữ liệu đó có thể mất khi tiến trình bị thay thế, checkpoint bị hỏng hoặc restore sang môi trường khác.

Một cách triển khai thường dùng là giữ cấu hình và dữ liệu khởi tạo ít thay đổi trong checkpoint, nhưng làm mới dữ liệu có tính thời điểm từ nguồn chính sau restore. Với cache lớn, có thể khởi tạo lại theo từng phần để tránh tạo tải đột biến lên database.

### 2.4. Hàng đợi và thông điệp

Message broker quản lý thông điệp và trạng thái giao nhận độc lập với JVM. Checkpoint không tự đồng bộ offset, acknowledgment, consumer group hoặc trạng thái xử lý giữa ứng dụng và broker.

Giả sử một consumer nhận thông điệp, thực hiện thay đổi trong heap rồi xác nhận đã xử lý với broker. Nếu thay đổi nghiệp vụ chưa được ghi bền vững mà tiến trình bị checkpoint, sau restore thông điệp có thể không được gửi lại vì broker đã nhận acknowledgment. Công việc khi đó có thể bị mất.

Trường hợp ngược lại cũng có thể xảy ra: thay đổi nghiệp vụ đã được commit, nhưng acknowledgment chưa tới broker. Sau restore, broker gửi lại thông điệp và ứng dụng xử lý lần nữa.

Để giảm rủi ro:

- Chỉ xác nhận thông điệp sau khi kết quả nghiệp vụ đã được lưu bền vững.
- Dùng message ID hoặc khóa nghiệp vụ để nhận diện thông điệp đã xử lý.
- Thiết kế consumer có thể xử lý lặp an toàn.
- Dừng nhận thông điệp mới và xử lý xong hoặc trả lại các thông điệp đang giữ trước checkpoint.
- Khi restore, tạo lại consumer và xác minh subscription, offset cùng trạng thái group.

Mức bảo đảm giao nhận vẫn phụ thuộc vào cấu hình broker và thiết kế consumer. CRaC không biến giao nhận at-most-once thành at-least-once hoặc exactly-once.

## 3. Giới hạn khi làm việc với hệ thống bên ngoài

### 3.1. Kết nối mạng và connection pool

Kết nối TCP, JDBC, HTTP keep-alive, WebSocket và kết nối tới message broker đều có vòng đời ở cả hai đầu. Trong khi JVM bị dừng, máy chủ từ xa có thể đóng kết nối do timeout, cân bằng tải, triển khai lại hoặc chính sách mạng. Firewall và NAT cũng có thể loại bỏ trạng thái kết nối không còn hoạt động.

Ngay cả khi một socket hoặc file descriptor được runtime khôi phục về mặt kỹ thuật, kết nối đó vẫn có thể không còn hợp lệ ở phía đối tác. Vì vậy, ứng dụng không nên coi một connection đang được tham chiếu trong heap là kết nối đang hoạt động.

Các connection pool như pool JDBC cần được đóng trước checkpoint và tạo mới sau restore. HTTP client hoặc SDK có quản lý connection cũng cần được kiểm tra theo hướng dẫn của thư viện. Sau restore, ứng dụng nên:

1. Tạo connection hoặc pool mới.
2. Kiểm tra khả năng kết nối tới dịch vụ quan trọng.
3. Khôi phục subscription hoặc session cần thiết.
4. Chỉ nhận lưu lượng nghiệp vụ khi các phụ thuộc bắt buộc đã sẵn sàng.

Không nên gửi toàn bộ yêu cầu kiểm tra kết nối đồng thời ngay khi nhiều bản sao ứng dụng restore. Hãy cân nhắc giới hạn concurrency, retry có backoff và jitter để tránh tạo một đợt tải lớn lên dịch vụ bên ngoài.

### 3.2. Session, lease và distributed lock

Nhiều hệ thống phân tán cấp quyền sở hữu tài nguyên trong một khoảng thời gian. Ví dụ gồm lease của service discovery, distributed lock, session của coordinator, quyền lãnh đạo (leader election) và heartbeat của worker.

Khi tiến trình bị dừng, heartbeat có thể ngừng gửi. Lease có thể hết hạn và được cấp cho tiến trình khác. Một distributed lock có thể được giải phóng hoặc bị thu hồi. Khi tiến trình cũ được restore, heap của nó vẫn có thể chứa thông tin rằng nó đang giữ lock hoặc đang là leader, dù quyền sở hữu đó không còn tồn tại.

Đây là tình huống nguy hiểm vì hai tiến trình có thể cùng tin rằng mình được phép cập nhật một tài nguyên. Cần xem quyền sở hữu là trạng thái do hệ thống phối hợp bên ngoài xác nhận, không phải một cờ boolean trong heap.

Các biện pháp thường dùng:

- Giải phóng lease hoặc lock trước checkpoint nếu giao thức cho phép.
- Sau restore, đăng ký lại và chờ hệ thống bên ngoài xác nhận quyền sở hữu mới.
- Dùng fencing token hoặc generation number tăng dần để hệ thống nhận biết và từ chối thao tác từ chủ sở hữu cũ.
- Không tiếp tục ghi dữ liệu chỉ vì một biến trong bộ nhớ vẫn có giá trị như trước checkpoint.
- Khởi tạo lại heartbeat và cơ chế phát hiện lỗi sau khi kết nối đã được thiết lập.

Fencing token đặc biệt hữu ích khi một tiến trình cũ có thể tỉnh lại sau thời gian dài. Mỗi lần cấp quyền mới, hệ thống phối hợp phát một token mới; tầng lưu trữ kiểm tra token trước khi chấp nhận thao tác ghi. Nhờ vậy, một chủ sở hữu cũ không thể ghi đè dữ liệu sau khi quyền của nó đã hết hiệu lực.

### 3.3. Token, chứng thực và quyền truy cập

Token truy cập, session cookie, chứng thư tạm thời và thông tin xác thực từ cloud provider thường có thời hạn. Chúng có thể còn nguyên trong heap nhưng đã hết hạn hoặc bị thu hồi khi tiến trình restore.

Một số thông tin xác thực còn được gắn với địa chỉ IP, máy, phiên TLS, danh tính workload hoặc phiên làm việc cụ thể. Restore sang môi trường khác có thể làm thay đổi các điều kiện đó.

Ứng dụng nên kiểm tra thời hạn và trạng thái chứng thực sau restore, làm mới token khi cần, và tạo lại phiên bảo mật theo hướng dẫn của nhà cung cấp. Không nên giả định rằng việc giữ một đối tượng client trong heap đồng nghĩa với việc phiên xác thực phía máy chủ vẫn còn hiệu lực.

Ảnh checkpoint cũng có thể chứa dữ liệu nhạy cảm đang nằm trong heap, bao gồm token, mật khẩu, khóa API, dữ liệu cá nhân hoặc nội dung yêu cầu. Vì vậy, checkpoint cần được bảo vệ như một bản sao có thể chứa bí mật:

- Hạn chế quyền đọc và tải ảnh checkpoint.
- Mã hóa nơi lưu trữ và đường truyền theo chính sách triển khai.
- Giới hạn thời gian lưu giữ và xóa ảnh cũ an toàn.
- Không ghi bí mật vào log trong callback.
- Ưu tiên lấy hoặc làm mới thông tin xác thực từ secret manager sau restore khi kiến trúc cho phép.

### 3.4. Thời gian, deadline và tác vụ định kỳ

Thời gian tiếp tục trôi qua trong lúc tiến trình không chạy. Một deadline tính từ thời điểm trước checkpoint có thể đã đến hạn khi restore. Dữ liệu được đánh dấu là còn hiệu lực trong một khoảng thời gian cũng có thể đã hết hạn.

Ví dụ, ứng dụng lưu thời điểm hết hạn token, thời gian chờ thanh toán, thời điểm chạy tác vụ tiếp theo hoặc thời gian còn lại của một phiên. Nếu chỉ lưu một bộ đếm trong heap và tiếp tục dùng bộ đếm đó sau restore, ứng dụng có thể xử lý muộn hoặc dùng trạng thái đã hết hạn.

Với deadline nghiệp vụ, nên lưu mốc thời gian tuyệt đối hoặc trạng thái tác vụ trong nguồn dữ liệu bền vững, rồi tính lại thời gian còn lại bằng đồng hồ hiện tại sau restore. Với tác vụ định kỳ, hãy đăng ký lại lịch với scheduler hoặc kiểm tra lịch chạy từ nguồn có thẩm quyền. Không nên dựa vào việc một thread đang sleep hoặc một timer trong bộ nhớ sẽ thể hiện chính xác khoảng thời gian thực đã trôi qua.

Các giá trị đo thời lượng trong tiến trình, chẳng hạn bộ đếm thời gian phục vụ profiling hoặc timeout nội bộ, cũng cần được xem xét. Sau restore, hãy xác định lại deadline và trạng thái timeout theo yêu cầu nghiệp vụ thay vì mặc định rằng thời gian trong heap vẫn phù hợp.

### 3.5. Tài nguyên native và tài nguyên của hệ điều hành

Ứng dụng Java có thể sử dụng tài nguyên không được quản lý hoàn toàn bởi heap: thư viện native, JNI, bộ nhớ ngoài heap, file lock, shared memory, thiết bị, pipe, thread đang chờ I/O hoặc tài nguyên do thư viện bên thứ ba tạo ra.

Khả năng checkpoint và restore các tài nguyên này phụ thuộc vào nền tảng, runtime CRaC, phiên bản thư viện và cách tài nguyên được mở. Một thư viện có thể không biết rằng tiến trình sắp bị checkpoint, nên không tự giải phóng hoặc tái tạo tài nguyên đúng cách.

Với mỗi thư viện có sử dụng tài nguyên native hoặc kết nối bên ngoài, cần kiểm tra tài liệu hỗ trợ CRaC và xác định callback hoặc cơ chế tích hợp phù hợp. Nếu thư viện không thể tái tạo trạng thái an toàn, hãy khởi tạo lại phần tài nguyên đó sau restore hoặc thay đổi cách sử dụng thư viện. Không nên xem việc một ứng dụng restore thành công là bằng chứng rằng mọi tài nguyên native đều hoạt động đúng.

## 4. Dùng callback CRaC để quản lý vòng đời tài nguyên

CRaC cung cấp API Resource để ứng dụng đăng ký công việc cần thực hiện trước checkpoint và sau restore. Với API CRaC trong package org.crac, một resource triển khai hai phương thức:

- beforeCheckpoint: chuẩn bị tài nguyên trước khi tiến trình được checkpoint. Ví dụ: dừng nhận việc mới, chờ công việc đang chạy hoàn tất, flush dữ liệu cần thiết và đóng kết nối.
- afterRestore: khôi phục tài nguyên sau khi tiến trình được restore. Ví dụ: tạo connection pool mới, kết nối lại broker, làm mới token và đăng ký lại subscription.

Resource cần được đăng ký với global context để runtime biết phải gọi callback của nó:

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class DatabasePoolResource implements Resource {
    private volatile HikariDataSource pool;

    public DatabasePoolResource() {
        Core.getGlobalContext().register(this);
        openPool();
    }

    public HikariDataSource pool() {
        HikariDataSource current = pool;
        if (current == null) {
            throw new IllegalStateException("Database pool is not ready");
        }
        return current;
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) {
        closePool();
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) {
        openPool();
    }

    private synchronized void openPool() {
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(System.getenv("DB_URL"));
        config.setUsername(System.getenv("DB_USER"));
        config.setPassword(System.getenv("DB_PASSWORD"));
        pool = new HikariDataSource(config);
    }

    private synchronized void closePool() {
        HikariDataSource current = pool;
        pool = null;
        if (current != null) {
            current.close();
        }
    }
}
~~~

Ví dụ trên minh họa cách đóng pool cũ và tạo pool mới. Nó giả định ứng dụng đã ngừng nhận yêu cầu và không còn giao dịch đang sử dụng pool trước khi callback đóng pool được thực hiện. Trong ứng dụng thực tế, cần có bước điều phối để dừng lưu lượng, drain công việc đang chạy và chỉ đóng pool khi các thao tác đó đã hoàn tất. HikariCP cũng cần có trong classpath của ví dụ.

Các callback không tự giải quyết mọi vấn đề của hệ thống:

- Chỉ những resource đã đăng ký hoặc được tích hợp qua cơ chế tương ứng mới nhận callback.
- Callback không commit thay database, không xác nhận thông điệp thay broker và không gia hạn lease thay coordinator.
- Đóng kết nối trong beforeCheckpoint không bảo đảm rằng một thao tác nghiệp vụ đang dở đã được lưu bền vững.
- afterRestore có thể gặp lỗi vì database, broker hoặc mạng chưa sẵn sàng. Ứng dụng cần chính sách retry có giới hạn, trạng thái readiness và cách xử lý khi phụ thuộc quan trọng chưa thể khôi phục.
- Callback phải có thời gian thực thi hữu hạn, xử lý lỗi rõ ràng và tránh tạo ra tác động nghiệp vụ trùng lặp.

Nếu nhiều resource phụ thuộc lẫn nhau, cần điều phối thứ tự đóng và mở phù hợp. Ví dụ, dừng consumer trước khi đóng kết nối broker; khi restore thì tạo kết nối trước, sau đó mới khởi động consumer. Không nên dựa vào thứ tự callback không được bảo đảm bởi runtime hoặc thư viện.

## 5. Quy trình thiết kế trước checkpoint và sau restore

Một quy trình tổng quát có thể chia thành hai giai đoạn.

### Trước checkpoint

1. Chuyển ứng dụng sang trạng thái quiescing để ngừng nhận công việc mới.
2. Chờ các request, transaction và tác vụ đang chạy hoàn tất trong thời hạn đã định.
3. Commit hoặc rollback giao dịch theo quy tắc nghiệp vụ; chỉ acknowledgment thông điệp sau khi kết quả đã bền vững.
4. Flush và đóng tệp đang ghi; giải phóng lock hoặc lease nếu giao thức yêu cầu.
5. Đóng connection pool, socket, consumer và các tài nguyên không thể tiếp tục sử dụng an toàn.
6. Kiểm tra rằng ứng dụng đã đạt trạng thái có thể checkpoint; nếu không, báo lỗi để quy trình checkpoint xử lý.

### Sau restore

1. Đọc lại cấu hình có thể thay đổi và làm mới thông tin xác thực.
2. Tạo lại connection pool, socket, client và subscription.
3. Kiểm tra sức khỏe của các phụ thuộc quan trọng.
4. Làm mới cache, xác minh phiên bản dữ liệu và loại bỏ trạng thái đã hết hạn.
5. Đăng ký lại lease, lock, heartbeat và lịch tác vụ; xác minh quyền sở hữu trước khi tiếp tục ghi.
6. Mở trạng thái readiness và nhận lưu lượng khi ứng dụng đã sẵn sàng.

Luồng tổng quát:

~~~mermaid
flowchart TD
    A[Ngừng nhận công việc mới] --> B[Drain request và transaction]
    B --> C[Hoàn tất ghi dữ liệu bền vững]
    C --> D[Đóng tài nguyên bên ngoài]
    D --> E[Checkpoint tiến trình]
    E --> F[Restore tiến trình]
    F --> G[Tạo lại kết nối và chứng thực]
    G --> H[Đồng bộ cache, lease và lịch tác vụ]
    H --> I[Kiểm tra readiness]
    I --> J[Nhận công việc mới]
~~~

Đây là quy trình khái quát. Thứ tự thực tế phải phù hợp với giao thức của từng dịch vụ, thư viện và môi trường triển khai. Nếu checkpoint thất bại sau khi ứng dụng đã đóng tài nguyên, quy trình vận hành cũng cần có cách đưa ứng dụng trở lại trạng thái phục vụ hoặc khởi động lại tài nguyên đã đóng.

## 6. Các mẫu thiết kế giúp ứng dụng an toàn hơn

### 6.1. Xem hệ thống bên ngoài là nguồn có thẩm quyền

Không dùng dữ liệu trong heap làm bằng chứng cuối cùng cho trạng thái nghiệp vụ có thể thay đổi bên ngoài. Sau restore, đọc lại những dữ liệu quan trọng hoặc xác minh bằng version, revision hay transaction ID. Cache chỉ nên giữ dữ liệu có thể tái tạo hoặc có quy tắc kiểm tra tính hợp lệ rõ ràng.

### 6.2. Thiết kế thao tác idempotent

Một thao tác có thể được thực hiện lại khi tiến trình không biết chắc lần trước đã thành công hay chưa. Hãy gắn ID duy nhất hoặc idempotency key với yêu cầu nghiệp vụ và lưu kết quả xử lý ở nơi bền vững. Điều này giúp lần gọi lại không tạo thêm khoản thanh toán, đơn hàng hoặc sự kiện trùng.

### 6.3. Tách trạng thái nghiệp vụ khỏi trạng thái kết nối

Trạng thái nghiệp vụ như đơn hàng đã được xác nhận nên được lưu trong database. Connection tới database, session của broker hoặc HTTP client chỉ là tài nguyên phục vụ việc truy cập trạng thái đó. Có thể đóng và tạo lại kết nối mà không làm mất trạng thái nghiệp vụ.

### 6.4. Dùng readiness để kiểm soát lưu lượng

Một JVM vừa restore có thể đã chạy nhưng vẫn chưa kết nối được database hoặc broker. Readiness probe nên phản ánh khả năng xử lý công việc thực tế. Nếu phụ thuộc bắt buộc chưa sẵn sàng, không đưa instance vào nhận lưu lượng. Liveness và readiness cần thể hiện hai điều khác nhau: tiến trình còn sống và tiến trình đã sẵn sàng phục vụ.

### 6.5. Hỗ trợ nhiều bản restore từ cùng checkpoint

Một ảnh checkpoint có thể được dùng để tạo nhiều instance. Khi đó, mỗi instance bắt đầu với cùng một bản sao trạng thái trong heap. Nếu bản sao đó chứa consumer ID cố định, scheduler, sequence counter, session hoặc thông tin sở hữu tài nguyên, các instance có thể xung đột.

Hãy tạo danh tính instance mới khi khởi động, đăng ký tài nguyên phân tán độc lập và lấy ID nghiệp vụ từ nguồn có cơ chế duy nhất phù hợp. Không sao chép một lock, lease hay quyền leader từ ảnh checkpoint sang nhiều instance. Các thao tác có tác động bên ngoài vẫn cần cơ chế idempotency và phối hợp phân tán.

## 7. Những giả định không nên đưa vào thiết kế

| Giả định | Vì sao không an toàn | Cách xử lý |
|---|---|---|
| Database sẽ quay về đúng thời điểm checkpoint | Database hoạt động độc lập và có thể đã nhận giao dịch mới | Đọc lại dữ liệu hoặc xác minh phiên bản sau restore |
| Connection trong heap vẫn còn hoạt động | Phía từ xa, firewall hoặc broker có thể đã đóng kết nối | Đóng trước checkpoint và tạo kết nối mới sau restore |
| Biến cache vẫn phản ánh dữ liệu mới nhất | Dữ liệu gốc có thể thay đổi trong lúc tiến trình dừng | Xóa, refresh hoặc kiểm tra TTL/version |
| Thông điệp đã xử lý trong heap chắc chắn đã được lưu | Heap và acknowledgment của broker không tạo thành một transaction chung | Commit kết quả bền vững trước acknowledgment; xử lý lặp an toàn |
| Tiến trình restore vẫn sở hữu distributed lock | Lease có thể hết hạn và được cấp cho instance khác | Đăng ký lại, xác minh quyền sở hữu và dùng fencing token |
| Token trong bộ nhớ vẫn hợp lệ | Token có thể hết hạn hoặc bị thu hồi | Refresh hoặc xác thực lại sau restore |
| Timer trong heap phản ánh chính xác thời gian đã trôi qua | Thời gian thực vẫn trôi trong lúc tiến trình ngừng chạy | Tính lại deadline từ mốc thời gian có thẩm quyền |
| Mọi tài nguyên native đều được khôi phục | Hỗ trợ phụ thuộc nền tảng và thư viện | Kiểm tra hỗ trợ, giải phóng và tạo lại tài nguyên |
| Restore nhiều lần không tạo tác động trùng | Các instance có thể bắt đầu từ cùng một trạng thái heap | Tạo identity mới và dùng cơ chế chống trùng ở hệ thống bên ngoài |

## 8. Kiểm chứng trong môi trường triển khai

Không nên chỉ kiểm tra rằng lệnh checkpoint và restore kết thúc thành công. Cần kiểm tra hành vi của ứng dụng khi các hệ thống bên ngoài thay đổi trong khoảng thời gian tiến trình dừng.

Một số tình huống thử nghiệm có giá trị:

- Database đóng connection hoặc được khởi động lại sau checkpoint. Ứng dụng có tạo pool mới và chỉ phục vụ khi truy cập được database không?
- Một bản ghi được cập nhật bởi tiến trình khác trong lúc ứng dụng đang dừng. Ứng dụng có đọc được phiên bản mới thay vì dùng cache cũ không?
- Broker gửi lại thông điệp vì acknowledgment chưa được xác nhận. Consumer có tránh tạo tác động nghiệp vụ trùng không?
- Token hết hạn hoặc bị thu hồi trước restore. Ứng dụng có làm mới chứng thực không?
- Lease hết hạn và được cấp cho worker khác. Instance được restore có xác minh lại quyền sở hữu trước khi ghi không?
- Tệp trên volume bị thay đổi hoặc volume được mount lại. Ứng dụng có mở lại và kiểm tra tệp đúng cách không?
- Thời gian thực đã vượt qua deadline của một tác vụ. Scheduler có tính lại lịch chạy không?
- Cùng một checkpoint được restore thành nhiều instance. Các instance có tránh dùng chung identity, lock và sequence state không?
- Dịch vụ phụ thuộc chưa sẵn sàng trong vài phút sau restore. Ứng dụng có retry có giới hạn và giữ readiness ở trạng thái phù hợp không?

Các thử nghiệm nên chạy trên môi trường gần với môi trường production về hệ điều hành, kernel, JDK, thư viện native, container runtime, volume và cấu hình CRaC. Khả năng khôi phục tài nguyên có thể khác nhau giữa các nền tảng. Một kết quả tốt trên máy phát triển không tự bảo đảm rằng cùng checkpoint sẽ hoạt động trong môi trường triển khai khác.

## 9. Khi nào nên dùng CRaC?

CRaC phù hợp khi mục tiêu là giảm thời gian khởi động và ứng dụng có thể xác định rõ cách chuẩn bị, đóng và tạo lại tài nguyên. Trạng thái khởi tạo tốn thời gian nhưng ít thay đổi, chẳng hạn lớp đã nạp, cấu trúc dữ liệu dùng chung có thể dựng lại hoặc cấu hình tĩnh, thường là ứng viên tốt cho checkpoint.

Những trạng thái phụ thuộc vào thời gian, kết nối đang mở, quyền sở hữu phân tán, dữ liệu nghiệp vụ mới nhất hoặc thao tác đang dở cần được xử lý riêng. Chúng phải được xác minh hoặc khôi phục từ nguồn có thẩm quyền sau restore.

Không nên dùng ảnh checkpoint làm nơi lưu dữ liệu nghiệp vụ duy nhất. Ảnh có thể bị xóa, không tương thích với môi trường mới, không thể restore hoặc chứa trạng thái đã lỗi thời. Dữ liệu cần tồn tại lâu dài vẫn phải được lưu trong hệ thống bền vững có chính sách sao lưu, phục hồi và nhất quán phù hợp.

Khi thiết kế đúng ranh giới, CRaC có thể rút ngắn thời gian đưa JVM vào trạng thái sẵn sàng mà không làm thay đổi trách nhiệm của database, message broker, hệ thống tệp hay dịch vụ phân tán. Ứng dụng cần chuẩn bị trạng thái trước checkpoint, tái tạo tài nguyên sau restore, và luôn xác minh lại những giả định có thể đã thay đổi trong thời gian tiến trình ngừng chạy.
