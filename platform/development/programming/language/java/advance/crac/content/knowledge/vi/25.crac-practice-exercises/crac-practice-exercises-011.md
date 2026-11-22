# Chủ động gây lỗi checkpoint và restore để luyện chẩn đoán

Checkpoint/restore là một quy trình có nhiều thành phần tham gia: ứng dụng, CRaC Resource, JDK runtime, checkpoint engine, hệ điều hành, filesystem và các dịch vụ bên ngoài. Một lần checkpoint thành công chưa chứng minh ứng dụng sẽ restore thành công trên môi trường đích. Tương tự, một lần restore thành công chưa chứng minh tài nguyên bên ngoài vẫn hợp lệ hoặc ứng dụng có thể nhận traffic an toàn.

Muốn vận hành CRaC đáng tin cậy, đội phát triển cần luyện cách nhận biết và xử lý lỗi trước khi đưa quy trình vào production. Cách hiệu quả là chủ động tạo lỗi có kiểm soát trong một môi trường thử nghiệm riêng, quan sát log và trạng thái tài nguyên, rồi xác minh đường phục hồi.

Bài thực hành này xây dựng một lab để gây lỗi ở các điểm khác nhau: callback beforeCheckpoint, callback afterRestore, kết nối bên ngoài, file descriptor, checkpoint artifact và compatibility của runtime. Mỗi lần chỉ thay đổi một yếu tố để có thể xác định nguyên nhân. Tất cả thử nghiệm cần chạy trên ứng dụng mẫu, dữ liệu giả và checkpoint artifact dùng riêng cho lab.

## 1. Mục tiêu và nguyên tắc của lab

Sau khi hoàn thành, người học có thể:

- Phân biệt lỗi trong Resource callback với lỗi của JDK runtime hoặc checkpoint engine.
- Chủ động làm một callback thất bại và xác định trạng thái của tiến trình sau lỗi.
- Nhận biết tài nguyên đã đóng một phần khi checkpoint bị hủy.
- Tạo lỗi phục hồi sau restore và giữ readiness ở trạng thái chưa sẵn sàng.
- Mô phỏng dependency bên ngoài bị mất kết nối hoặc không thể xác thực lại.
- Nhận biết lỗi do file descriptor/socket không được hỗ trợ.
- Phân biệt artifact bị thiếu/hỏng với lỗi runtime compatibility.
- Thu thập log, PID, FD, trạng thái kết nối, thời gian và thông tin runtime để lập báo cáo.
- Xây dựng quyết định retry, cold start hoặc rollback dựa trên nguyên nhân.

Các nguyên tắc cần giữ:

1. Chỉ dùng môi trường disposable, không dùng checkpoint hoặc credential production.
2. Dùng port, thư mục, database schema và service account riêng cho lab.
3. Ghi lại baseline trước khi gây lỗi.
4. Mỗi kịch bản chỉ bật một fault injection tại một thời điểm.
5. Không đóng file descriptor bằng tay từ shell để tạo lỗi; hãy dùng API của resource owner hoặc fault switch trong ứng dụng.
6. Không sửa checkpoint gốc khi thử artifact corruption. Tạo bản sao dành riêng cho kịch bản đó.
7. Không mở traffic nếu restore hook hoặc health check bắt buộc chưa hoàn tất.
8. Ghi phiên bản JDK, CRaC runtime, engine, OS/kernel, container image và cách gọi checkpoint/restore của đúng nền tảng.

Fault injection là thao tác có chủ đích. Một callback bị làm cho thất bại trong lab không có nghĩa mọi runtime xử lý lỗi theo cùng một cách. Hãy ghi nhận hành vi thực tế của JDK distribution và checkpoint engine đang dùng.

## 2. Chuẩn bị môi trường thử nghiệm

Một lab tối thiểu cần:

- Một ứng dụng Java nhỏ có ít nhất một CRaC Resource.
- Một JDK/runtime có hỗ trợ CRaC.
- Checkpoint engine và hệ điều hành được runtime hỗ trợ.
- Một thư mục riêng để lưu checkpoint artifact và log.
- Một dependency giả lập, chẳng hạn HTTP server nhỏ hoặc database thử nghiệm.
- Công cụ quan sát process, thread, file descriptor và socket.

Có thể tổ chức thư mục như sau:

~~~text
crac-fault-lab/
  app/
    application.jar
    config/
  checkpoint/
    baseline/
    before-failure/
    after-failure/
    corrupt-copy/
  logs/
    application.log
    checkpoint.log
    restore.log
  evidence/
    runtime.txt
    process.txt
    fd-before.txt
    fd-after.txt
    timings.csv
  scripts/
    run-app.sh
    create-checkpoint.sh
    restore-checkpoint.sh
~~~

Đây chỉ là cấu trúc gợi ý. Tên file và thư mục checkpoint thực tế phụ thuộc engine/runtime. Một số implementation tạo nhiều file hoặc metadata phụ trợ; không tự giả định checkpoint chỉ là một file duy nhất.

### Ghi lại runtime và host

Trước khi chạy, lưu thông tin nền tảng:

~~~shell
java -version
java -XshowSettings:properties -version
uname -a
uname -m
~~~

Ghi thêm:

- JDK vendor và build đầy đủ.
- CRaC API/runtime version.
- Checkpoint engine và version.
- JVM flags và system properties liên quan.
- Container image digest nếu chạy trong container.
- Kernel, CPU architecture, libc và filesystem của thư mục checkpoint.
- Memory limit, swap policy và quyền/capability của process.

Không dùng các lệnh trên để suy ra engine nếu runtime không công bố engine qua chúng. Lấy engine version từ công cụ hoặc tài liệu của đúng distribution.

### Kiểm tra cách gọi checkpoint

Lệnh tạo checkpoint và restore không hoàn toàn giống nhau giữa các JDK distribution. Trước tiên xem các diagnostic command mà JVM đang chạy công bố:

~~~shell
jcmd PID help
~~~

Thay PID bằng PID thực tế. Nếu output của runtime có command checkpoint, dùng đúng cú pháp mà runtime liệt kê và tài liệu vendor hướng dẫn. Một số runtime có thể cung cấp command dạng JDK.checkpoint; không mặc định command này tồn tại trên mọi JDK.

Tương tự, lệnh restore phải theo hướng dẫn của runtime/engine. Không tự ghép một checkpoint được tạo bởi engine này với launcher option của engine khác.

## 3. Xây dựng ứng dụng mẫu có fault switch

Ứng dụng lab nên có một Resource sở hữu một client giả lập và một admission gate. Fault switch cho phép bật một lỗi theo cấu hình khi chạy lab. Cấu hình phải được tắt trong lần chạy baseline.

Ví dụ dưới đây minh họa cấu trúc; các kiểu Client, ClientFactory và AdmissionGate là abstraction do ứng dụng mẫu định nghĩa:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class LabResource implements Resource {
    public enum FailurePoint {
        NONE,
        BEFORE_CHECKPOINT,
        AFTER_RESTORE
    }

    public interface AdmissionGate {
        void stopAndDrain() throws Exception;
        void resume() throws Exception;
        boolean isOpen();
    }

    public interface Client extends AutoCloseable {
        void healthCheck() throws Exception;
        @Override
        void close() throws Exception;
    }

    public interface ClientFactory {
        Client create() throws Exception;
    }

    private final AdmissionGate gate;
    private final ClientFactory factory;
    private final FailurePoint failurePoint;
    private volatile Client client;

    public LabResource(
            AdmissionGate gate,
            ClientFactory factory,
            FailurePoint failurePoint) throws Exception {
        this.gate = gate;
        this.factory = factory;
        this.failurePoint = failurePoint;
        this.client = factory.create();
        Core.getGlobalContext().register(this);
    }

    public Client client() {
        Client current = client;
        if (current == null) {
            throw new IllegalStateException(
                    "Client is not ready");
        }
        return current;
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        gate.stopAndDrain();

        if (client != null) {
            client.close();
            client = null;
        }

        if (failurePoint == FailurePoint.BEFORE_CHECKPOINT) {
            throw new IllegalStateException(
                    "LAB: intentional beforeCheckpoint failure");
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        Client restoredClient = factory.create();
        try {
            restoredClient.healthCheck();
            if (failurePoint == FailurePoint.AFTER_RESTORE) {
                throw new IllegalStateException(
                        "LAB: intentional afterRestore failure");
            }
            client = restoredClient;
            gate.resume();
        } catch (Exception failure) {
            restoredClient.close();
            client = null;
            throw failure;
        }
    }

    public synchronized void recoverAfterAbortedCheckpoint()
            throws Exception {
        if (client == null) {
            Client recovered = factory.create();
            recovered.healthCheck();
            client = recovered;
        }
        gate.resume();
    }
}
~~~

Điểm cần quan sát trong ví dụ:

- Admission được dừng và công việc đang chạy được drain trước khi đóng client.
- Lỗi beforeCheckpoint được ném sau khi client đã đóng, để mô phỏng trạng thái chuẩn bị một phần.
- Nếu checkpoint bị hủy và tiến trình ban đầu tiếp tục, callback afterRestore không phải cơ chế phục hồi cho tiến trình đó. Coordinator của lab phải gọi đường phục hồi như recoverAfterAbortedCheckpoint().
- Nếu afterRestore thất bại, client vừa tạo được đóng lại và admission vẫn đóng.
- Handler chỉ được truy cập client qua accessor kiểm tra trạng thái.

Đây không phải implementation production hoàn chỉnh. Ứng dụng thật cần bảo đảm không có thread nào giữ tham chiếu trực tiếp tới client và bỏ qua admission gate. Nếu có nhiều Resource phụ thuộc nhau, phải có coordinator hoặc lifecycle contract xác định thứ tự an toàn.

### Cấu hình fault switch

Có thể ánh xạ một system property hoặc biến môi trường thành FailurePoint. Ví dụ:

~~~java
LabResource.FailurePoint point =
        LabResource.FailurePoint.valueOf(
                System.getProperty("lab.failAt", "NONE"));
~~~

Giá trị hợp lệ của lab:

| Giá trị | Hành vi |
|---|---|
| NONE | Không chủ động gây lỗi |
| BEFORE_CHECKPOINT | Đóng client rồi làm callback trước checkpoint thất bại |
| AFTER_RESTORE | Tạo client rồi làm callback sau restore thất bại |

Không để fault switch bật mặc định. Tốt nhất chỉ cho phép bật trong profile lab và từ chối khởi động nếu profile này được dùng ngoài môi trường thử nghiệm.

## 4. Kịch bản 0: chạy baseline không có lỗi

Baseline là mốc để so sánh tất cả kịch bản khác. Chạy ứng dụng với fault switch NONE và dependency giả lập đang hoạt động.

Các bước:

1. Khởi động ứng dụng bằng JDK/CRaC runtime đã pin.
2. Xác nhận ứng dụng báo readiness.
3. Gửi một request mẫu và xác nhận client hoạt động.
4. Ghi PID, thread dump nếu cần, số lượng FD và socket đang mở.
5. Tạo checkpoint vào thư mục baseline theo command được runtime hỗ trợ.
6. Restore checkpoint bằng đúng runtime/engine.
7. Xác nhận callback afterRestore hoàn tất.
8. Gửi lại request mẫu và kiểm tra dependency.

Ghi lại:

- Thời gian khởi động ban đầu.
- Thời gian callback beforeCheckpoint.
- Thời gian tạo checkpoint.
- Kích thước và danh sách artifact.
- Thời gian restore.
- Thời gian callback afterRestore.
- Thời gian tới readiness.
- Latency request đầu tiên và các request tiếp theo.
- Log, PID và trạng thái client trước/sau restore.

<badge>Expected result</badge>

Ứng dụng tạo được checkpoint, restore thành công, client được xác minh và readiness chỉ mở sau khi Resource hoàn tất. Đây là kết quả đối chứng cho các bài thử tiếp theo.

## 5. Kịch bản 1: làm beforeCheckpoint thất bại

Mục tiêu là quan sát lỗi callback trước checkpoint và xác định điều gì xảy ra khi một số tài nguyên đã được đóng nhưng checkpoint chưa hoàn tất.

### Cách thực hiện

1. Khởi động ứng dụng trong profile lab với failure point BEFORE_CHECKPOINT.
2. Xác nhận client đang hoạt động và readiness đang mở.
3. Yêu cầu checkpoint bằng cơ chế của runtime.
4. Quan sát log của Resource và checkpoint coordinator.
5. Ghi lại việc runtime có hủy checkpoint hay không và trạng thái tiến trình ban đầu.
6. Kiểm tra client đã đóng hay còn mở.
7. Chạy đường phục hồi sau checkpoint abort của ứng dụng.
8. Xác nhận client mới hoạt động rồi mới mở admission.

Không giả định mọi runtime có cùng hành vi sau callback ném exception. Ghi nhận rõ runtime có dừng ngay thao tác checkpoint, có gọi callback khác đã đăng ký hay không và cách nó báo lỗi.

### Kết quả cần quan sát

- Log có chứa thông báo LAB intentional failure.
- Checkpoint artifact có được tạo hoàn chỉnh hay không.
- Process gốc còn chạy hay đã kết thúc.
- Admission gate đang đóng hay mở.
- Client có bị đóng một phần trước khi lỗi xảy ra không.
- Coordinator có gọi recovery path không.
- Request sau recovery có thành công không.

Nếu process tiếp tục chạy nhưng client đã đóng, request phải bị chặn cho đến khi client được tạo lại. Đây là lỗi dễ gặp khi callback chuẩn bị checkpoint thất bại sau khi đã thực hiện một số hành động có side effect.

### Bài học

Callback beforeCheckpoint không phải transaction tự động rollback. Nếu đã đóng một số resource rồi callback tiếp theo thất bại, ứng dụng cần một đường phục hồi cho process gốc. Không trông chờ afterRestore được gọi trên process chưa được restore.

## 6. Kịch bản 2: làm afterRestore thất bại

Mục tiêu là quan sát lỗi xảy ra sau khi process được phục hồi nhưng trước khi ứng dụng sẵn sàng nhận traffic.

### Cách thực hiện

1. Tạo checkpoint hợp lệ bằng cấu hình baseline.
2. Dùng một bản chạy restore có failure point AFTER_RESTORE.
3. Restore artifact theo đúng runtime/engine.
4. Quan sát log callback và lỗi LAB intentional failure.
5. Kiểm tra client đã được đóng lại trong catch block.
6. Xác nhận admission/readiness không mở.
7. Ghi nhận cách runtime xử lý lỗi restore callback.

### Kết quả cần quan sát

- Callback afterRestore bắt đầu chạy.
- Client được tạo nhưng health check hoặc fault injection làm callback thất bại.
- Client chưa sẵn sàng được đóng.
- Readiness vẫn false.
- Handler không thể dùng client chưa sẵn sàng.
- Runtime báo restore failure, giữ process không ready hoặc kết thúc process theo semantics của implementation.

Hành vi cuối cùng phụ thuộc runtime và checkpoint engine. Không giả định process chắc chắn sẽ tự retry callback. Nếu runtime coi lỗi callback là lỗi restore không thể tiếp tục, phương án phục hồi có thể là loại instance đó và khởi động instance mới từ cold start hoặc checkpoint đã xác minh.

### Bài học

Restore hoàn tất ở tầng process không đồng nghĩa ứng dụng đã sẵn sàng về nghiệp vụ. Readiness phải phụ thuộc vào việc phục hồi các resource bắt buộc, xác thực dependency và hoàn tất security initialization.

## 7. Kịch bản 3: dependency bên ngoài không sẵn sàng

Mục tiêu là kiểm tra ứng dụng khi database, HTTP service hoặc message broker không thể kết nối lại sau restore.

### Cách thực hiện với HTTP dependency

1. Dùng một HTTP service giả lập chạy trên port riêng của lab.
2. Khởi động ứng dụng và xác nhận health check thành công.
3. Tạo checkpoint sau khi Resource đã chuẩn bị tài nguyên theo đúng thiết kế.
4. Dừng HTTP service hoặc chặn kết nối từ môi trường lab.
5. Restore checkpoint.
6. Quan sát timeout, retry và readiness.
7. Khởi động lại HTTP service.
8. Cho ứng dụng retry theo chính sách và xác nhận readiness mở sau khi health check thành công.

Nếu dùng database, tạo schema và dữ liệu giả riêng. Không dùng database production để cố ý dừng service hoặc làm hỏng kết nối.

### Những lỗi cần phân biệt

- DNS lookup thất bại.
- TCP connection timeout hoặc connection refused.
- TLS handshake thất bại do certificate/clock/trust.
- Token hết hạn hoặc không còn audience/scope hợp lệ.
- Database session cũ đã bị server đóng.
- Broker client không thể tái lập subscription hoặc consumer group state.
- Dependency trả về lỗi ứng dụng dù TCP connection thành công.

### Kết quả cần quan sát

Ứng dụng không được đánh dấu ready chỉ vì process đã restore. Log cần phân biệt lỗi kết nối, lỗi xác thực, lỗi TLS và lỗi nghiệp vụ. Retry phải có timeout, backoff và giới hạn hợp lý để tránh tạo tải lớn lên dependency vừa phục hồi.

### Bài học

Checkpoint không đóng băng vòng đời của hệ thống bên ngoài. Database, broker, DNS, secret manager và API vẫn tiếp tục thay đổi trong thời gian snapshot được lưu. Sau restore, phải xác minh lại những điều kiện phụ thuộc thời gian.

## 8. Kịch bản 4: giữ một file descriptor không được xử lý

Mục tiêu là tìm ra resource còn mở khi checkpoint engine báo descriptor không được hỗ trợ hoặc không thể dump.

### Cách thực hiện

1. Tạo một FileChannel hoặc socket do ứng dụng lab sở hữu.
2. Bật chế độ test để Resource không đóng tài nguyên đó trong beforeCheckpoint.
3. Ghi lại PID và danh sách FD trước checkpoint.
4. Yêu cầu checkpoint.
5. Lưu toàn bộ log runtime/engine.
6. Nếu checkpoint thất bại, đối chiếu FD hoặc inode trong log với /proc/PID/fd và lsof.
7. Xác định component Java tạo tài nguyên.
8. Bật lại lifecycle đóng/mở đúng cách rồi chạy lại.

Các lệnh quan sát trên Linux:

~~~shell
ls -l /proc/PID/fd
lsof -nP -p PID
lsof -nP -a -p PID -i
ss -tanp
~~~

Thay PID bằng PID thực tế. Nếu process chạy trong container, dùng đúng PID namespace; nếu cần quan sát socket từ host, xác định network namespace tương ứng.

### Kết quả cần quan sát

- Loại FD: regular file, socket, pipe, eventpoll, device hay native handle.
- Descriptor number và inode nếu có.
- Đường dẫn hoặc endpoint.
- Resource owner trong ứng dụng.
- Lỗi engine cụ thể và bước native thất bại.
- Kết quả sau khi đóng đúng tài nguyên.

Không cố đóng FD bằng một lệnh shell. Đóng descriptor bên ngoài process có thể khiến object Java vẫn giữ số FD cũ và số đó bị kernel tái sử dụng cho tài nguyên khác. Sửa lifecycle tại owner API.

## 9. Kịch bản 5: checkpoint artifact bị thiếu hoặc hỏng

Mục tiêu là phân biệt lỗi artifact với lỗi ứng dụng hoặc runtime.

### Chuẩn bị bản sao thử nghiệm

1. Tạo checkpoint baseline hợp lệ.
2. Sao chép toàn bộ artifact sang thư mục corrupt-copy.
3. Giữ nguyên bản baseline.
4. Trong bản sao thử nghiệm, cố ý xóa một file phụ trợ hoặc làm thay đổi một file theo cách có thể phục hồi.
5. Tính checksum trước và sau thay đổi.
6. Thử restore bản sao bị lỗi.

Không sửa artifact gốc hoặc checkpoint đang được môi trường khác sử dụng. Nếu engine tạo nhiều file, phải biết file nào là thành phần bắt buộc từ manifest hoặc log của runtime.

### Hai loại thử nghiệm

**Thiếu file:** đổi tên hoặc loại bỏ một file trong bản sao thử nghiệm. Restore có thể báo file không tồn tại, metadata không đầy đủ hoặc lỗi đọc.

**Nội dung bị thay đổi:** thay đổi một byte hoặc truncate bản sao thử nghiệm rồi kiểm tra checksum và restore. Nếu manifest có hash, bước xác minh integrity nên phát hiện thay đổi trước khi gọi engine.

### Kết quả cần quan sát

- Checksum có còn khớp manifest không.
- Lỗi xảy ra ở bước xác minh artifact, đọc file hay restore engine.
- Có tạo ra process dở dang hay không.
- Ứng dụng có chuyển sang cold-start path không.
- Log có nhận diện rõ artifact ID và checkpoint ID không.

### Bài học

Một checkpoint không chỉ là một thư mục có tên đúng. Cần inventory file, checksum, manifest, quyền truy cập và quy trình phát hành bất biến. Nếu artifact không toàn vẹn, không cố restore bằng cách bỏ qua bước kiểm tra hash.

## 10. Kịch bản 6: thử runtime hoặc engine không tương thích

Mục tiêu là hiểu vì sao một checkpoint hợp lệ trên producer có thể không restore được trên consumer.

Chỉ thực hiện trong môi trường disposable có hai runtime/engine đã được cài riêng và không dùng chung thư mục dữ liệu. Không nâng hoặc thay runtime của production để thử.

### Cách thực hiện

1. Tạo checkpoint bằng tổ hợp JDK/CRaC/engine A.
2. Lưu manifest của producer: vendor, full runtime version, engine, kernel, architecture, native libraries và container digest.
3. Tạo môi trường thử nghiệm B với một thành phần khác biệt được chọn trước, chẳng hạn engine version hoặc JDK build.
4. Trước restore, kiểm tra tài liệu vendor để xác định tổ hợp B có được hỗ trợ hay không.
5. Nếu đây là tổ hợp không được hỗ trợ, chỉ thử trên bản sao artifact và host dùng riêng.
6. Lưu log và mã lỗi của runtime/engine.
7. Khôi phục lại tổ hợp A và xác nhận artifact baseline vẫn hoạt động.

### Không thay nhiều yếu tố cùng lúc

Nếu đổi JDK vendor, engine, kernel, CPU architecture và container image cùng lúc, kết quả thất bại không chỉ ra nguyên nhân cụ thể. Thay từng yếu tố trong môi trường lab và ghi ma trận producer/consumer.

### Kết quả cần quan sát

- Runtime có từ chối trước khi đọc artifact không.
- Engine có báo định dạng hoặc native state không tương thích không.
- Lỗi liên quan kernel, architecture, library hay permission.
- Có thể restore thành công trên tổ hợp producer ban đầu không.

### Bài học

Không được suy ra compatibility từ việc hai môi trường cùng chạy Linux hoặc cùng Java major version. Checkpoint binary gắn với runtime và engine cụ thể; phải dùng tổ hợp được hỗ trợ và kiểm thử.

## 11. Kịch bản 7: callback bị treo hoặc vượt timeout

Mục tiêu là kiểm tra Resource callback khi một thao tác đóng connection hoặc drain worker không hoàn tất.

### Cách thực hiện

1. Tạo một Resource test có latch hoặc test server giữ request chưa trả lời.
2. Trong beforeCheckpoint, yêu cầu Resource chờ thao tác đó hoàn tất.
3. Không cho test server trả lời trong khoảng thời gian giới hạn.
4. Yêu cầu checkpoint.
5. Ghi lại thời gian callback, log timeout và trạng thái admission.
6. Cho test server trả lời hoặc hủy tác vụ theo chính sách.
7. Chạy đường phục hồi nếu checkpoint đã abort.

Không tạo vòng lặp vô hạn hoặc sleep kéo dài trong process production. Dùng timeout ngắn, cấu hình được và một môi trường lab riêng.

### Kết quả cần quan sát

- Callback có timeout rõ ràng hay treo vô hạn.
- Coordinator có biết Resource nào chưa hoàn tất không.
- Thread nào đang chờ và đang chờ điều kiện gì.
- Admission gate có giữ trạng thái đóng khi callback thất bại không.
- Tiến trình ban đầu có thể phục hồi sau khi checkpoint bị hủy không.

### Bài học

Mọi thao tác trước checkpoint cần có timeout và chiến lược lỗi. Một callback không bao giờ kết thúc có thể khiến checkpoint coordinator bị kẹt. Timeout cần đi cùng rollback/recovery logic, không chỉ ném exception rồi để process ở trạng thái nửa đóng.

## 12. Kịch bản 8: kiểm tra phụ thuộc thứ tự giữa các Resource

Mục tiêu là tìm lỗi khi hai Resource quản lý những thành phần có quan hệ phụ thuộc.

Ví dụ:

- Resource A dừng HTTP client.
- Resource B dừng worker đang gửi request qua HTTP client.

Nếu client bị đóng trước khi worker dừng, worker có thể lỗi hoặc treo. Khi restore, worker có thể chạy trước khi client được tạo lại.

### Cách thực hiện

1. Tạo hai Resource test với log timestamp ở mỗi callback.
2. Cho một worker gửi request liên tục qua client.
3. Gọi checkpoint trong khi có request đang chạy.
4. Quan sát thứ tự dừng worker và đóng client.
5. Restore và quan sát thứ tự mở client và khởi động worker.
6. Lặp lại nhiều lần để phát hiện race.

Không dựa vào thứ tự tình cờ của callback độc lập nếu API/runtime không cam kết điều đó. Hãy dùng coordinator có ownership rõ ràng để điều phối chuỗi: stop admission, drain worker, close client; khi restore thì create client, health check, resume worker và mở admission.

## 13. Kịch bản 9: state bị nhân bản giữa nhiều replica

Mục tiêu là phát hiện dữ liệu trong heap không nên được chia sẻ khi cùng checkpoint được restore nhiều lần.

Tạo một ứng dụng test giữ:

- Một token giả có ID nhận diện.
- Một counter cục bộ.
- Một nonce generator.
- Một replica identity.

Trước checkpoint, ghi fingerprint hoặc ID không nhạy cảm của các giá trị này. Restore cùng checkpoint thành nhiều instance trong môi trường lab.

Kiểm tra:

- Mỗi replica có nhận identity mới không.
- Token có được cấp mới theo từng replica không.
- Counter toàn cục có bị lặp không.
- Nonce có thể trùng dưới cùng key không.
- Readiness có chờ hoàn tất security initialization không.

Không log token thật, private key hoặc nonce production. Dùng dữ liệu giả và fingerprint an toàn. Với nonce, bài test thống kê không chứng minh uniqueness tuyệt đối; cần xác minh thiết kế key/nonce allocator.

## 14. Bảng tổng hợp fault injection

| Kịch bản | Fault được tạo | Dấu hiệu cần tìm | Hướng xử lý |
|---|---|---|---|
| Baseline | Không có | Checkpoint/restore hoàn tất, readiness mở | Lưu làm mốc |
| beforeCheckpoint | Callback ném exception | Log Resource, checkpoint abort, resource đóng một phần | Recovery cho process gốc |
| afterRestore | Callback ném exception | Restore hook thất bại, readiness vẫn đóng | Retry có kiểm soát hoặc cold start |
| Dependency down | HTTP/DB/broker không sẵn sàng | Timeout, auth error, stale connection | Reconnect, retry/backoff, readiness gate |
| Unsupported FD | File/socket/pipe không được xử lý | FD/inode/errno trong log engine | Tìm owner và xử lý lifecycle |
| Artifact missing | Thiếu file checkpoint | ENOENT hoặc metadata incomplete | Khôi phục bundle đầy đủ |
| Artifact corrupt | Checksum/content thay đổi | Hash mismatch hoặc lỗi đọc/restore | Từ chối artifact và dùng bản hợp lệ |
| Incompatible runtime | Consumer khác producer | Runtime/engine/kernel compatibility error | Dùng profile được hỗ trợ |
| Callback timeout | Resource không kết thúc | Callback duration vượt ngưỡng, thread đang chờ | Timeout và recovery path |
| Resource ordering | Phụ thuộc callback không được điều phối | Race, client đóng quá sớm hoặc worker chạy quá sớm | Lifecycle coordinator |
| Cloned state | Nhiều replica cùng snapshot | Identity/token/counter/nonce bị trùng | Cấp mới identity và trạng thái riêng |

## 15. Thu thập bằng chứng trong mỗi lần chạy

Không nên chỉ ghi lại dòng exception. Một báo cáo chẩn đoán cần đủ thông tin để người khác tái hiện.

### Metadata môi trường

- Lab run ID.
- Thời gian bắt đầu/kết thúc theo UTC.
- Git commit và application build ID.
- JDK vendor, full version và CRaC runtime.
- Checkpoint engine và version.
- OS, kernel, CPU architecture và container digest.
- JVM flags, memory limit và checkpoint path.

### Log và trạng thái process

- Log ứng dụng trước, trong và sau callback.
- Log checkpoint/restore engine.
- PID, parent PID và trạng thái process.
- Thread dump nếu callback bị treo.
- File descriptor inventory nếu có lỗi FD/socket.
- Socket endpoint/state nếu có lỗi network.
- Resource name và callback duration.

### Kết quả

- Checkpoint có hoàn tất không?
- Artifact có đầy đủ và checksum đúng không?
- Restore có hoàn tất không?
- Readiness có mở đúng thời điểm không?
- Dependency có hoạt động không?
- Recovery hoặc cold-start fallback có thành công không?
- Thời gian từng giai đoạn là bao nhiêu?

Một mẫu bảng log:

| Timestamp UTC | Phase | Resource | Event | Duration | Outcome |
|---|---|---|---|---:|---|
| 08:00:00.100 | beforeCheckpoint | ApiClient | close started | - | - |
| 08:00:00.140 | beforeCheckpoint | ApiClient | close completed | 40 ms | success |
| 08:00:00.141 | beforeCheckpoint | LabResource | injected failure | - | failed |
| 08:00:00.180 | coordinator | checkpoint | request aborted | 80 ms | failed |
| 08:00:00.250 | recovery | ApiClient | reopen completed | 70 ms | success |

Các timestamp và duration ở trên chỉ là ví dụ. Đồng bộ clock trong môi trường lab hoặc ghi monotonic duration để tránh sai lệch khi wall clock thay đổi.

## 16. Cách phân loại nguyên nhân từ triệu chứng

| Triệu chứng | Nhóm nguyên nhân có thể | Bằng chứng cần tìm |
|---|---|---|
| Lỗi xuất hiện ngay khi gọi checkpoint | Resource callback hoặc runtime precondition | Java stack trace, callback log |
| Callback hoàn tất nhưng engine dump thất bại | Native FD, kernel, permission hoặc engine | Engine log, errno, FD inventory |
| Artifact tạo xong nhưng restore không đọc được | Artifact thiếu/hỏng, path hoặc permission | Checksum, file inventory, filesystem log |
| Restore process bắt đầu nhưng app không ready | afterRestore hoặc dependency failure | Restore hook log, health check, readiness |
| Chỉ lỗi trên host khác | Compatibility hoặc môi trường đích | Producer/consumer manifest, kernel, CPU, engine |
| Lúc được lúc không | Race, timeout, dependency biến động hoặc I/O pressure | Timestamp, thread dump, retry và metric |
| Restore xong nhưng request đầu tiên lỗi | State stale, credential hết hạn, cache hoặc connection | Request trace, auth error, client lifecycle |
| Nhiều replica tạo cùng ID/token/nonce | State bị clone | Replica identity, key ID, allocator state |

Đây là bản đồ hướng điều tra, không phải kết luận tự động. Một triệu chứng có thể có nhiều nguyên nhân; cần xác nhận bằng log và phép thử cô lập.

## 17. Thiết kế recovery và fallback

Fault injection chỉ có ích nếu sau khi nhận diện lỗi, ứng dụng có cách phục hồi được xác định.

### Khi beforeCheckpoint thất bại

- Đánh dấu lần checkpoint thất bại.
- Xác định Resource nào đã đóng hoặc thay đổi trạng thái.
- Giữ admission đóng nếu tài nguyên bắt buộc chưa sẵn sàng.
- Gọi recovery path cho tiến trình hiện tại.
- Tạo lại client/credential/file handle cần thiết.
- Health check rồi mới mở admission.

### Khi afterRestore thất bại

- Không mở readiness.
- Đóng resource được tạo dở.
- Ghi rõ Resource và dependency thất bại.
- Retry chỉ khi lỗi có thể phục hồi và runtime cho phép cách retry đó.
- Nếu restore không thể tiếp tục, loại instance và dùng cold-start path hoặc checkpoint đã được xác minh.

### Khi artifact hoặc compatibility sai

- Không bỏ qua checksum hoặc compatibility check.
- Không chỉnh sửa artifact production để thử phục hồi.
- Chọn release bundle đã được ký và xác minh.
- Dùng runtime/engine profile được hỗ trợ.
- Nếu không có checkpoint hợp lệ, cold start từ application artifact đã pin.

### Khi dependency ngoài bị lỗi

- Dùng timeout và backoff có giới hạn.
- Không tạo hàng nghìn kết nối retry đồng thời.
- Giữ readiness false cho dependency bắt buộc.
- Làm mới token/certificate nếu lỗi xác thực hoặc hết hạn.
- Ghi metric để phân biệt lỗi dependency với lỗi restore engine.

## 18. Checklist vận hành cho một buổi thực hành

Trước buổi lab:

- [ ] Xác nhận đây là host/container dùng riêng cho thử nghiệm.
- [ ] Tạo application build và checkpoint artifact riêng.
- [ ] Ghi runtime, engine, kernel, CPU và container digest.
- [ ] Chuẩn bị dependency giả lập và dữ liệu không nhạy cảm.
- [ ] Xác nhận cách gọi checkpoint/restore đúng với runtime.
- [ ] Kiểm tra fault switch mặc định đang tắt.
- [ ] Bật log callback, duration và readiness state.

Trong từng kịch bản:

- [ ] Chỉ bật một fault injection.
- [ ] Ghi run ID và cấu hình fault.
- [ ] Lưu log trước/sau checkpoint hoặc restore.
- [ ] Thu thập PID, FD, socket hoặc thread dump khi cần.
- [ ] Ghi trạng thái artifact và checksum.
- [ ] Xác định process còn chạy, đã restore hay đã kết thúc.
- [ ] Kiểm tra readiness và dependency.

Sau từng kịch bản:

- [ ] Phục hồi môi trường về baseline.
- [ ] Xóa fault switch và xác nhận đã tắt.
- [ ] Không tái sử dụng artifact bị sửa/hỏng cho kịch bản khác.
- [ ] Lưu kết quả và giả thuyết nguyên nhân.
- [ ] Chạy lại baseline để xác nhận lab không còn trạng thái lỗi.

## 19. Bài tập mở rộng

Sau khi hoàn thành các kịch bản cơ bản, có thể mở rộng:

**Bài tập A — lỗi chỉ xuất hiện khi restore trên host khác.** Tạo manifest producer/consumer, thay một yếu tố môi trường trong lab và xác định yếu tố nào khiến restore thất bại.

**Bài tập B — dependency phục hồi chậm.** Thêm delay vào HTTP service, đo readiness và p99 của request đầu tiên. Điều chỉnh timeout/backoff rồi so sánh.

**Bài tập C — callback chạy lâu.** Tạo một worker có tác vụ đang chạy, đo drain time và chứng minh checkpoint chỉ tiếp tục khi worker dừng an toàn.

**Bài tập D — nhiều Resource có quan hệ phụ thuộc.** Cho worker phụ thuộc client, thiết kế coordinator và chứng minh thứ tự stop/start không tạo race.

**Bài tập E — nhiều replica cùng restore.** Cấp identity riêng, kiểm tra token và key ID, đồng thời xác minh nonce allocator không bị clone.

**Bài tập F — rollback.** Phát hành hai bộ runtime/application/checkpoint khác nhau trong lab, cố ý làm restore release mới thất bại rồi chuyển về release bundle trước đó.

Với mỗi bài, nêu giả thuyết trước khi chạy, ghi kết quả quan sát, giải thích khác biệt giữa dự đoán và thực tế, rồi xác định thay đổi cần thiết trong ứng dụng hoặc quy trình vận hành.

## 20. Kết luận

Chủ động gây lỗi checkpoint và restore giúp đội phát triển hiểu rõ ranh giới giữa Resource callback, JDK runtime, checkpoint engine, hệ điều hành và dependency bên ngoài. Các kịch bản quan trọng gồm callback thất bại, tài nguyên đóng một phần, dependency không sẵn sàng, file descriptor không được hỗ trợ, artifact bị hỏng, runtime không tương thích, timeout và state bị nhân bản giữa nhiều replica.

Một lab tốt luôn có baseline, fault injection cô lập, log đủ ngữ cảnh và recovery path được kiểm chứng. Khi checkpoint thất bại, tiến trình ban đầu có thể cần phục hồi tài nguyên đã đóng; khi restore thất bại, readiness phải tiếp tục đóng; khi artifact hoặc runtime không tương thích, cần từ chối restore và dùng một release đã xác minh hoặc cold start. Hãy thực hiện các thử nghiệm trong môi trường disposable, dùng đúng lệnh và giới hạn của JDK/engine đang triển khai, rồi chuyển những phát hiện thành kiểm thử tự động và quy trình vận hành có thể lặp lại.
