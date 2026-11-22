# Phạm vi close, reopen và giới hạn của chính sách tài nguyên

Trong CRaC, close và reopen là những thao tác quản lý vòng đời tài nguyên quanh checkpoint và restore. Ứng dụng có thể đóng file, channel, socket hoặc client trước checkpoint rồi mở lại sau restore. Tuy nhiên, một chính sách tài nguyên chỉ có hiệu lực trong phạm vi các tài nguyên mà thành phần sở hữu đã nhận diện và quản lý rõ ràng.

Không có một lệnh close chung có thể tự hiểu toàn bộ tài nguyên của ứng dụng. Đóng một object wrapper không nhất thiết đóng mọi tài nguyên liên quan; mở lại một handle cũng không tự khôi phục phiên làm việc, transaction, lock, subscription hoặc trạng thái nghiệp vụ. Muốn thiết kế đúng, cần xác định ranh giới sở hữu, thứ tự phụ thuộc, trạng thái cần lưu và những giới hạn mà ứng dụng phải chấp nhận.

## 1. Chính sách tài nguyên bao gồm những gì?

Một chính sách tài nguyên mô tả cách một thành phần chuẩn bị trước checkpoint và phục hồi sau restore. Tối thiểu, chính sách cần trả lời:

- Thành phần nào sở hữu tài nguyên?
- Những handle hoặc hoạt động nào phải dừng trước checkpoint?
- Dữ liệu nào cần flush hoặc lưu lại?
- Tài nguyên nào phải đóng và tài nguyên nào có thể được giữ theo hướng dẫn của runtime/thư viện?
- Sau restore, mở lại bằng cấu hình nào và khôi phục trạng thái tới đâu?
- Nếu close hoặc reopen thất bại thì ứng dụng sẽ xử lý thế nào?
- Khi nào thành phần được phép nhận công việc trở lại?

Ví dụ, một thành phần đọc file có thể sở hữu FileChannel và buffer đọc. Chính sách của nó có thể yêu cầu dừng reader, ghi lại offset logic đã xử lý, đóng channel và bỏ buffer cũ. Sau restore, thành phần mở channel mới, đặt lại vị trí theo offset đã lưu, tạo buffer mới rồi mới tiếp tục đọc.

Chính sách này không áp dụng tự động cho mọi object khác đang giữ cùng đường dẫn file. Một service khác có thể sở hữu một channel riêng, và phải có chính sách vòng đời riêng hoặc được quản lý bởi cùng một chủ sở hữu rõ ràng.

## 2. Phạm vi quản lý: từ handle tới hệ thống bên ngoài

Có thể phân biệt các phạm vi sau:

| Phạm vi | Ví dụ | Chính sách close/reopen quản lý được gì? | Giới hạn cần nhớ |
|---|---|---|---|
| Handle | InputStream, OutputStream, FileChannel, socket | Đóng handle và tạo handle mới | Không tự khôi phục dữ liệu đã xử lý, vị trí logic hoặc phiên giao thức |
| Thành phần | File reader, HTTP client, connection pool, broker consumer | Phối hợp nhiều handle và trạng thái nội bộ của thành phần | Cần biết rõ handle nào thuộc quyền sở hữu của thành phần |
| Tiến trình | Nhiều service, executor, listener và tài nguyên dùng chung | Điều phối các thành phần đã đăng ký với CRaC | Không tự phát hiện mọi tài nguyên native hoặc tài nguyên do thư viện ẩn bên trong quản lý |
| Hệ thống bên ngoài | Database, filesystem, broker, Redis, dịch vụ HTTP, distributed lock | Có thể kết nối lại hoặc xác minh trạng thái qua API của hệ thống | Không thể quay ngược thời gian hoặc hoàn tác side effect đã commit ở hệ thống đó |

Phạm vi càng rộng thì yêu cầu điều phối càng lớn. Một Resource cấp ứng dụng có thể quản lý nhiều thành phần, nhưng chỉ nên làm vậy khi có chủ sở hữu rõ ràng và thứ tự vòng đời được định nghĩa. Việc đăng ký một Resource với global context không biến nó thành bộ quản lý tự động cho mọi tài nguyên trong JVM.

## 3. Close có phạm vi tới đâu?

### Close theo hợp đồng của API

Mỗi API định nghĩa hành vi close riêng. Ví dụ:

- Đóng BufferedInputStream thường đóng stream bên dưới mà nó bọc.
- Đóng BufferedOutputStream thường flush buffer theo hợp đồng của lớp rồi đóng stream bên dưới.
- Đóng FileChannel làm channel không còn sử dụng được và giải phóng các tài nguyên liên quan theo hợp đồng của API.
- Đóng một connection lấy từ pool có thể chỉ trả connection về pool, không nhất thiết đóng physical connection tới server.
- Đóng một client cấp cao có thể đóng nhiều kết nối nội bộ, nhưng phạm vi chính xác phụ thuộc thư viện.

Do đó, không thể suy luận rằng gọi close trên một object bất kỳ sẽ giải phóng toàn bộ tài nguyên của thành phần. Hãy đọc hợp đồng của API và xác định object nào thực sự sở hữu handle.

### Wrapper và tài nguyên bên dưới

Một chuỗi wrapper thường có dạng:

~~~text
Ứng dụng
   |
   v
BufferedInputStream
   |
   v
FileInputStream
   |
   v
File descriptor của hệ điều hành
   |
   v
File trên filesystem
~~~

Đóng wrapper ngoài cùng có thể đóng stream bên dưới theo hợp đồng của wrapper. Nhưng điều đó không xóa file, không đóng các stream độc lập khác đang mở cùng file và không dừng một thread khác đang giữ tham chiếu tới một wrapper khác.

Tương tự, hai service có thể cùng dùng một client được chia sẻ. Nếu một service tự đóng client trong callback của mình trong khi service kia vẫn đang sử dụng, ứng dụng sẽ gặp lỗi. Tài nguyên dùng chung cần có một chủ sở hữu vòng đời hoặc một bộ đếm/quy tắc phối hợp rõ ràng.

### Close không thay thế việc dừng công việc

Đóng handle khi thread khác vẫn đang đọc hoặc ghi có thể làm thao tác đó thất bại, ghi dở dữ liệu hoặc để lại trạng thái nghiệp vụ không nhất quán. Trước khi close, thành phần cần:

1. Ngừng nhận công việc mới.
2. Chờ các thao tác đang sử dụng tài nguyên hoàn tất hoặc hủy chúng theo quy tắc đã định.
3. Đồng bộ buffer và lưu tiến độ cần thiết.
4. Đóng handle sau khi không còn người sử dụng.

Một callback Resource chỉ đóng tài nguyên không tự động giải quyết việc điều phối request, executor hoặc consumer. Phần đó thuộc trách nhiệm của kiến trúc ứng dụng.

## 4. Reopen có nghĩa là tạo tài nguyên mới

Reopen thường tạo một handle mới tới cùng nguồn tài nguyên. Nó không làm sống lại object handle đã đóng và cũng không đảm bảo môi trường bên ngoài vẫn giống lúc checkpoint.

Khi reopen, cần xác định:

- Địa chỉ hoặc đường dẫn hiện tại.
- Chế độ truy cập: read, write, append hay truncate.
- Credential và chứng thư còn hiệu lực.
- Offset, sequence hoặc cursor cần khôi phục.
- Subscription, consumer group hoặc lease cần đăng ký lại.
- Quyền sở hữu tài nguyên dùng chung.
- Dependency nào phải sẵn sàng trước khi mở tài nguyên phụ thuộc.

Ví dụ, mở lại FileChannel với READ và WRITE không tự đặt channel về vị trí trước checkpoint. Ứng dụng phải lưu và khôi phục position theo nhu cầu. Mở lại HTTP client không khôi phục phiên đăng nhập nếu token đã hết hạn. Mở lại broker consumer không có nghĩa message chưa xác nhận sẽ không được gửi lại.

Reopen cũng có thể thất bại. File có thể đã bị xóa, quyền truy cập thay đổi, database không sẵn sàng hoặc credential đã bị thu hồi. Nếu tài nguyên là bắt buộc, ứng dụng cần báo trạng thái chưa sẵn sàng và không nhận công việc phụ thuộc vào tài nguyên đó.

## 5. Xác định ranh giới sở hữu

Mỗi tài nguyên nên có một chủ sở hữu vòng đời duy nhất. Chủ sở hữu chịu trách nhiệm:

- Tạo handle và công bố cách sử dụng nó.
- Không để code bên ngoài tự ý đóng handle nếu chưa có quy ước.
- Ngừng người dùng tài nguyên trước checkpoint.
- Thực hiện close và reopen theo cùng một chính sách.
- Kiểm tra trạng thái sau khi phục hồi.

Nếu một pool được dùng bởi nhiều repository, repository không nên tự đăng ký callback để đóng pool. Thành phần quản lý pool nên chịu trách nhiệm vòng đời của pool; các repository chỉ sử dụng pool theo hợp đồng.

Nếu nhiều loại tài nguyên phụ thuộc nhau, thứ tự close và reopen có thể khác nhau. Ví dụ, một consumer phụ thuộc vào broker client:

- Trước checkpoint, dừng consumer trước rồi mới đóng client.
- Sau restore, tạo client trước rồi mới khởi động consumer.

Tương tự, nếu một writer phụ thuộc vào FileChannel, cần dừng writer và flush dữ liệu trước khi đóng channel; sau restore, mở channel trước rồi mới cho writer hoạt động.

Không nên dựa vào thứ tự callback giữa các Resource độc lập nếu chưa được bảo đảm bởi phiên bản CRaC API/runtime đang dùng. Khi thứ tự có ý nghĩa, hãy gom các phần phụ thuộc vào một thành phần điều phối hoặc dùng cơ chế điều phối có thứ tự do framework hỗ trợ.

## 6. Ví dụ: quản lý một nhóm tài nguyên có quan hệ phụ thuộc

Ví dụ sau mô tả một Resource cấp thành phần quản lý nhiều phần tài nguyên. Danh sách được truyền theo thứ tự phụ thuộc: thành phần nền tảng trước, thành phần sử dụng nó sau. Khi chuẩn bị checkpoint, nhóm đóng theo thứ tự ngược; khi restore, nhóm mở theo thứ tự thuận.

~~~java
import java.util.ArrayList;
import java.util.List;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ResourceScope implements Resource {
    public interface ManagedPart {
        // Nếu phương thức ném lỗi, phần tử phải tự giữ hoặc khôi phục
        // trạng thái có thể sử dụng của chính nó.
        void closeForCheckpoint() throws Exception;

        // Nếu phương thức ném lỗi, phần tử phải tự dọn trạng thái
        // mở dở dang và giữ trạng thái đóng.
        void reopenAfterRestore() throws Exception;
    }

    private final List<ManagedPart> dependencyOrder;
    private boolean prepared;
    private boolean unavailable;

    public ResourceScope(List<ManagedPart> dependencyOrder) {
        this.dependencyOrder = List.copyOf(dependencyOrder);
        Core.getGlobalContext().register(this);
    }

    public synchronized boolean isReady() {
        return !prepared && !unavailable;
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        if (prepared) {
            return;
        }

        unavailable = true;
        List<ManagedPart> closed = new ArrayList<>();

        try {
            for (int i = dependencyOrder.size() - 1; i >= 0; i--) {
                ManagedPart part = dependencyOrder.get(i);
                part.closeForCheckpoint();
                closed.add(part);
            }
            prepared = true;
        } catch (Exception failure) {
            boolean recovered = true;
            for (int i = closed.size() - 1; i >= 0; i--) {
                try {
                    closed.get(i).reopenAfterRestore();
                } catch (Exception recoveryFailure) {
                    failure.addSuppressed(recoveryFailure);
                    recovered = false;
                }
            }
            if (recovered) {
                unavailable = false;
            }
            throw failure;
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        if (!prepared) {
            return;
        }

        List<ManagedPart> reopened = new ArrayList<>();
        try {
            for (ManagedPart part : dependencyOrder) {
                part.reopenAfterRestore();
                reopened.add(part);
            }
            prepared = false;
            unavailable = false;
        } catch (Exception failure) {
            for (int i = reopened.size() - 1; i >= 0; i--) {
                try {
                    reopened.get(i).closeForCheckpoint();
                } catch (Exception cleanupFailure) {
                    failure.addSuppressed(cleanupFailure);
                }
            }
            throw failure;
        }
    }
}
~~~

Trong ví dụ:

- dependencyOrder được sắp từ tài nguyên nền tảng tới thành phần phụ thuộc vào nó.
- beforeCheckpoint đánh dấu scope chưa sẵn sàng, sau đó đóng theo thứ tự ngược.
- Nếu một phần tử đóng thất bại, các phần tử đã đóng được mở lại theo thứ tự phù hợp và lỗi được truyền lên.
- afterRestore mở theo thứ tự phụ thuộc; nếu một bước mở thất bại, các phần đã mở được đóng lại theo thứ tự ngược.
- isReady cho phép tầng ứng dụng kiểm tra scope trước khi nhận công việc.

Đây là khung điều phối minh họa. Các ManagedPart cần thực hiện close/reopen an toàn khi có lỗi một phần như hợp đồng trong code đã mô tả. Trong ứng dụng thực tế, trạng thái unavailable cần được nối với readiness/traffic gate; nếu thao tác phục hồi hoặc rollback thất bại, không tiếp tục xử lý công việc phụ thuộc vào nhóm tài nguyên. Việc đồng bộ callback với thread đang sử dụng tài nguyên cũng phải được thực hiện ở tầng sở hữu.

Ví dụ này quản lý thứ tự bên trong một scope. Nó không đặt ra thứ tự cho những Resource khác được đăng ký độc lập với CRaC runtime.

## 7. Giới hạn của chính sách close/reopen

### Không tự phát hiện mọi tài nguyên

Một ứng dụng có thể sử dụng tài nguyên thông qua thư viện, JNI, native code hoặc framework. Resource do ứng dụng viết chỉ quản lý những gì nó biết và được giao quyền sở hữu. Tài nguyên ẩn bên trong thư viện cần được xử lý bởi tích hợp CRaC của thư viện hoặc hướng dẫn riêng của nhà cung cấp.

Không nên tạo một callback tổng quát cố đóng mọi thứ trong JVM. Cách làm đó có thể đóng nhầm tài nguyên do framework quản lý, xung đột với thứ tự shutdown hoặc làm hỏng trạng thái cần thiết cho restore.

### Không hoàn tác side effect bên ngoài

Đóng database connection không hoàn tác một transaction đã commit. Đóng OutputStream không xóa nội dung file đã ghi. Đóng broker consumer không thu hồi message đã được xác nhận. Reopen không đưa database, broker hoặc filesystem về trạng thái tại thời điểm checkpoint.

Nếu một thao tác có thể được gửi lại sau restore, cần có idempotency key, deduplication hoặc checkpoint nghiệp vụ để xác định thao tác đã hoàn tất hay chưa. Checkpoint của JVM không phải transaction phân tán.

### Không bảo đảm khôi phục đúng cùng một trạng thái

Một handle mới có thể trỏ tới cùng đường dẫn hoặc endpoint nhưng trạng thái dữ liệu đã thay đổi. File có thể đã được thay thế; server có thể chuyển node; token có thể bị thu hồi; lease có thể đã hết hạn.

Ứng dụng phải xác minh phiên bản, offset, quyền sở hữu và trạng thái hiện tại trước khi tiếp tục. Nếu không thể xác minh, cần khởi tạo lại từ nguồn dữ liệu chuẩn hoặc yêu cầu quy trình nghiệp vụ phục hồi.

### Không thay thế điều phối luồng

Resource callback không tự động dừng mọi thread đang dùng tài nguyên. Một thread có thể đang ghi vào buffer, một request đang giữ connection hoặc một consumer đang xử lý message. Ứng dụng phải phối hợp dừng nhận công việc, drain hoặc hủy thao tác đang chạy trước khi đóng handle.

### Không bảo đảm mọi close đều có thể reopen

Một số nguồn là luồng một lần, pipe hoặc response body không hỗ trợ seek/resume. Sau khi đóng, không thể lấy lại cùng byte tiếp theo nếu nguồn không cung cấp giao thức resume. Khi đó cần lưu checkpoint ở tầng giao thức hoặc nghiệp vụ.

### Không thay thế backup và phục hồi dữ liệu

Close/reopen quản lý vòng đời handle. Nó không thay thế backup file, database backup, transaction log, replication hoặc quy trình khôi phục dữ liệu. Nếu file bị xóa hoặc dữ liệu bị hỏng trong thời gian checkpoint, mở lại file không thể tự khôi phục nội dung đã mất.

### Không bảo đảm callback luôn hoàn tất thành công

Close có thể thất bại do I/O error; reopen có thể thất bại do dịch vụ không sẵn sàng hoặc quyền truy cập thay đổi. Lỗi callback cần được truyền lên và xử lý theo khả năng của CRaC runtime. Không nên nuốt lỗi rồi đánh dấu tài nguyên sẵn sàng.

Nếu chuẩn bị checkpoint thất bại sau khi một số tài nguyên đã đóng, ứng dụng cần có chiến lược rollback hoặc phục hồi cục bộ. Nếu rollback cũng thất bại, giữ ứng dụng ở trạng thái không sẵn sàng và để cơ chế vận hành quyết định cách phục hồi; không tiếp tục dùng một nhóm tài nguyên ở trạng thái không xác định.

## 8. Các loại tài nguyên và giới hạn thường gặp

| Tài nguyên | Chính sách thường cần | Giới hạn |
|---|---|---|
| InputStream từ file | Lưu offset logic, đóng, mở lại, khôi phục vị trí | Stream tổng quát không có API seek; file có thể thay đổi |
| OutputStream | Dừng writer, flush, đóng, chọn append/truncate đúng | Flush không luôn đồng nghĩa dữ liệu đã bền vững; record có thể ghi dở |
| FileChannel | Lưu position, đồng bộ khi cần, đóng và mở lại | Position I/O có thể khác tiến độ nghiệp vụ; lock phải giành lại |
| JDBC connection/pool | Drain transaction, đóng hoặc làm mới theo hướng dẫn pool, kiểm tra kết nối | Session và transaction phía database có vòng đời riêng |
| HTTP client/socket | Đóng hoặc làm mới connection, xác thực và kết nối lại | Peer có thể thay đổi; phiên giao thức không tự được khôi phục |
| Message consumer | Dừng nhận message, xử lý/ack theo quy tắc, đăng ký lại | Message chưa ack có thể được gửi lại; cần deduplication |
| Distributed lock/lease | Nhả hoặc xác minh lại quyền sở hữu | Lease tiếp tục hết hạn theo thời gian bên ngoài |
| Native handle/JNI | Dùng API và hook do thư viện/native component cung cấp | Java Resource không thể tự suy ra cách đóng mọi con trỏ native |

## 9. Thiết kế chính sách theo mức độ cần thiết

Không phải tài nguyên nào cũng cần cùng một chính sách. Có thể chia thành các nhóm:

**Giữ nguyên khi đã được hỗ trợ.** Một số trạng thái hoặc tài nguyên được CRaC runtime hay thư viện hỗ trợ trực tiếp. Hãy theo hướng dẫn chính thức của phiên bản đang sử dụng và tránh tự đóng thêm nếu điều đó xung đột với integration.

**Đóng rồi tạo lại.** Áp dụng cho handle có thể mở lại an toàn như file channel, client hoặc connection pool khi thư viện yêu cầu. Lưu những thông tin cần để tái tạo, không lưu kỳ vọng rằng handle cũ vẫn hợp lệ.

**Xác minh rồi tiếp tục.** Áp dụng cho cache, credential, lease, subscription hoặc trạng thái từ xa có thể vẫn còn nhưng đã thay đổi. Sau restore, truy vấn nguồn chuẩn trước khi sử dụng.

**Không thể resume trực tiếp.** Áp dụng cho stream một lần hoặc giao thức không hỗ trợ khôi phục offset. Cần thiết kế lại checkpoint ở tầng nghiệp vụ, hoặc chấp nhận đọc lại từ đầu theo cách an toàn.

Một thành phần có thể kết hợp nhiều nhóm. Ví dụ, ứng dụng đóng HTTP connection, đọc lại credential, xác minh cache và đăng ký lại subscription. Chính sách cần mô tả từng tài nguyên thay vì gán một hành động duy nhất cho toàn bộ thành phần.

## 10. Kiểm thử và vận hành

Kiểm thử chính sách tài nguyên nên bao gồm cả tình huống thành công và lỗi:

- Checkpoint khi không có thao tác I/O đang chạy.
- Checkpoint khi request hoặc consumer đang sử dụng tài nguyên.
- Một close thất bại sau khi các tài nguyên phụ thuộc đã đóng.
- Reopen thất bại vì file không còn tồn tại, credential hết hạn hoặc dịch vụ chưa sẵn sàng.
- Một tài nguyên dùng chung được nhiều thành phần sử dụng.
- File hoặc dữ liệu bên ngoài thay đổi trong khoảng thời gian checkpoint.
- Một message hoặc thao tác ghi được gửi lại sau restore.
- Nhiều chu kỳ checkpoint/restore để phát hiện handle mở trùng, thread bị nhân đôi hoặc trạng thái sẵn sàng sai.

Quan sát vận hành nên thể hiện rõ thành phần đang ở trạng thái nào: hoạt động, đang chuẩn bị checkpoint, đã đóng, đang phục hồi, sẵn sàng hoặc lỗi. Log nên chỉ ra tài nguyên nào thất bại và nguyên nhân, nhưng không ghi credential hay dữ liệu nhạy cảm.

Readiness cần phản ánh khả năng sử dụng thực tế của dependency thiết yếu. Một object client khác null chưa đủ để đánh dấu ready; cần xác minh kết nối hoặc hoàn thành handshake/đăng ký cần thiết.

## 11. Kết luận

Phạm vi close/reopen được xác định bởi quyền sở hữu và hợp đồng của từng tài nguyên. Một chính sách tốt nêu rõ handle nào cần đóng, thành phần nào điều phối, dữ liệu nào phải lưu, thứ tự phục hồi và cách xử lý lỗi. Với các tài nguyên phụ thuộc nhau, nên quản lý thứ tự trong cùng một scope có chủ sở hữu rõ ràng.

Giới hạn cốt lõi là close/reopen chỉ quản lý vòng đời tài nguyên mà ứng dụng kiểm soát. Nó không tự phát hiện mọi native handle, không dừng mọi thread, không hoàn tác side effect bên ngoài, không bảo đảm nguồn dữ liệu còn nguyên và không làm cho mọi stream có thể resume. Ứng dụng cần xác minh trạng thái sau restore và chỉ tiếp tục khi các tài nguyên bắt buộc đã sẵn sàng.
