# CheckpointException, RestoreException và các ngoại lệ bị gom

Trong CRaC, một lần checkpoint hoặc restore có thể gọi nhiều resource callback. Mỗi resource có thể gặp một lỗi riêng: đóng file thất bại, flush dữ liệu không thành công, kết nối không thể mở lại hoặc một thư viện native không khôi phục được trạng thái. Nếu chỉ giữ lại lỗi đầu tiên, những lỗi còn lại sẽ bị che khuất và việc chẩn đoán trở nên khó khăn.

CRaC dùng hai exception tổng hợp là **CheckpointException** và **RestoreException**. Các lỗi phát sinh từ callback được gắn vào exception tổng hợp dưới dạng *suppressed exceptions*. Vì vậy, khi xử lý lỗi CRaC, cần đọc toàn bộ danh sách suppressed exception thay vì chỉ xem message hoặc cause của exception ngoài cùng.

Bài này giải thích thời điểm từng exception xuất hiện, cách CRaC gom nhiều lỗi, cách đọc exception tree và cách viết resource callback để lỗi được báo cáo đầy đủ mà ứng dụng vẫn phục hồi đúng trạng thái.

## 1. Hai exception đại diện cho hai giai đoạn

API CRaC có hai callback chính trên interface Resource:

- **beforeCheckpoint(Context)**: thông báo cho resource rằng tiến trình sắp được checkpoint. Resource chuẩn bị trạng thái và giải phóng tài nguyên không nên giữ trong ảnh.
- **afterRestore(Context)**: thông báo rằng tiến trình vừa được restore. Resource tạo lại handle và kết nối cần thiết để ứng dụng tiếp tục.

Nếu một callback ném exception, Context toàn cục thu thập lỗi và truyền kết quả về nơi yêu cầu checkpoint/restore.

| Exception | Giai đoạn có lỗi | Ý nghĩa vận hành |
|---|---|---|
| CheckpointException | Thông báo trước checkpoint thất bại, hoặc quá trình chuẩn bị checkpoint có lỗi | Không tạo được checkpoint image; ứng dụng tiếp tục trong tiến trình Java ban đầu sau khi các callback phục hồi được chạy |
| RestoreException | Thông báo sau restore thất bại | Image đã được dùng để tạo tiến trình mới, nhưng một hoặc nhiều resource không phục hồi thành công |
| UnsupportedOperationException | Runtime không hỗ trợ dịch vụ checkpoint/restore | Không có callback nào được thực hiện; yêu cầu checkpoint không được hỗ trợ |

Hai exception đầu là exception tổng hợp, kế thừa từ **Exception**. Chúng không đại diện cho một lỗi nghiệp vụ cụ thể như IOException hay SQLException. Thông tin chi tiết nằm trong các suppressed exception bên trong.

### 1.1 CheckpointException

CheckpointException được ném khi thông báo checkpoint của Context toàn cục kết thúc với lỗi. Một hoặc nhiều resource có thể đã ném exception trong beforeCheckpoint.

Ví dụ:

- FileChannel không đóng được.
- Buffer không flush được xuống file.
- HTTP server không dừng được listener.
- Connection pool không thể hoàn tất thao tác shutdown.
- Một resource phát hiện trạng thái ứng dụng chưa an toàn và chủ động ném exception.

Khi Context toàn cục xử lý lỗi callback, nó vẫn tiếp tục thông báo cho các resource còn lại theo chính sách của Context. Sau đó, các lỗi được đưa vào CheckpointException dưới dạng suppressed exception.

Nếu checkpoint notification thất bại, image không được tạo. CRaC gọi tiếp notification sau restore ngay trong tiến trình Java ban đầu để các resource có cơ hội mở lại những gì đã đóng trong quá trình chuẩn bị. Nếu những callback phục hồi này cũng thất bại, lỗi của chúng được thêm vào cùng CheckpointException.

Do đó, một CheckpointException có thể chứa cả lỗi ở beforeCheckpoint và lỗi ở afterRestore được gọi để phục hồi tiến trình ban đầu. Đây là lý do không nên chỉ đọc exception đầu tiên rồi kết luận toàn bộ vấn đề.

### 1.2 RestoreException

RestoreException xuất hiện khi checkpoint đã đi qua giai đoạn chuẩn bị và tiến trình mới được tạo từ image, nhưng một hoặc nhiều callback afterRestore thất bại.

Ví dụ:

- File cấu hình không còn tồn tại ở đường dẫn đã lưu.
- Database từ chối kết nối mới.
- Socket không thể kết nối lại tới dịch vụ từ xa.
- Certificate hoặc credential đã hết hạn.
- Một native library không thể tái tạo handle.
- Một cache bắt buộc không thể nạp lại.

Trong trường hợp này, tiến trình mới đã được restore nhưng trạng thái phục hồi của ứng dụng chưa hoàn chỉnh. Không nên mặc định rằng ứng dụng có thể nhận traffic chỉ vì JVM đã chạy tiếp từ image.

Nếu gọi checkpoint bằng Core.checkpointRestore(), RestoreException được truyền về đoạn code gọi trong tiến trình mới. Ứng dụng cần giữ readiness ở trạng thái chưa sẵn sàng, ghi nhận các lỗi chi tiết và thực hiện chính sách phục hồi hoặc dừng khởi động theo yêu cầu vận hành.

## 2. Vì sao CRaC gom nhiều exception?

Một ứng dụng có thể đăng ký nhiều Resource với global Context. Mỗi Resource quản lý một phần trạng thái riêng: file, socket, database pool, scheduler, message consumer hoặc một thư viện native.

Giả sử ứng dụng có ba resource:

- Resource A đóng file log.
- Resource B dừng HTTP listener.
- Resource C đóng connection pool.

Khi checkpoint bắt đầu, A có thể đóng file thành công, B có thể thất bại khi dừng listener, và C vẫn cần được thông báo để đóng pool. Nếu Context dừng ngay ở lỗi đầu tiên, C có thể tiếp tục giữ tài nguyên trong khi checkpoint đang được chuẩn bị.

Global Context của CRaC có các hành vi quan trọng:

1. Mỗi Resource được đăng ký vẫn nhận notification, kể cả khi Resource khác đã ném exception.
2. Exception từ callback được Context bắt lại và đưa vào exception tổng hợp.
3. Các lỗi được lưu dưới dạng suppressed exception.
4. Restore notification cũng được thực hiện cho các Resource theo quy tắc của Context, kể cả khi callback khác đã thất bại.

Nhờ đó, một lần chạy có thể báo cáo nhiều lỗi độc lập. Người vận hành có thể sửa tất cả nguyên nhân trong một vòng chẩn đoán thay vì xử lý từng lỗi xuất hiện nối tiếp.

Các bảo đảm về thứ tự và cách thu thập này mô tả global Context. Một custom Context có thể định nghĩa chính sách notification riêng; khi dùng custom Context, cần đọc hợp đồng của chính Context đó.

### 2.1 Thứ tự notification của global Context

Global Context gọi callback checkpoint theo thứ tự ngược với thứ tự đăng ký Resource. Callback restore chạy theo thứ tự ngược lại, tức theo thứ tự đăng ký.

Ví dụ, nếu đăng ký A, sau đó B, sau đó C:

~~~text
Đăng ký:            A -> B -> C
beforeCheckpoint:   C -> B -> A
afterRestore:       A -> B -> C
~~~

Cách gọi ngược chiều giúp ứng dụng đóng các thành phần theo một thứ tự và mở lại theo thứ tự đảo ngược. Ví dụ, nếu server phụ thuộc vào connection pool, có thể đăng ký resource sao cho server dừng trước khi pool đóng và pool mở lại trước khi server hoạt động.

Thứ tự callback không thay đổi nguyên tắc gom lỗi: một callback thất bại không có nghĩa các callback còn lại sẽ bị bỏ qua.

## 3. Suppressed exception là gì?

Java có hai cơ chế thường gặp để liên kết exception:

- **Cause:** một exception được tạo ra vì một exception khác; truy cập bằng getCause().
- **Suppressed exception:** một exception phụ được giữ kèm một exception chính; truy cập bằng getSuppressed().

CRaC dùng suppressed exception cho lỗi từ nhiều Resource callback. Exception ngoài cùng đóng vai trò container tổng hợp, còn từng lỗi thực tế nằm trong mảng trả về bởi getSuppressed().

Ví dụ cấu trúc:

~~~text
CheckpointException
  Suppressed: IOException
    Message: Cannot flush application log
  Suppressed: SQLException
    Message: Connection pool shutdown failed
  Suppressed: IllegalStateException
    Message: HTTP listener is still active
~~~

Ví dụ restore:

~~~text
RestoreException
  Suppressed: IOException
    Message: Configuration file is missing
  Suppressed: SQLException
    Message: Database authentication failed
~~~

Trong các API CRaC hiện hành, CheckpointException và RestoreException là exception tổng hợp không có message, cause hoặc stack trace riêng. Vì vậy:

- getMessage() trên exception ngoài cùng có thể trả về null.
- getCause() trên exception ngoài cùng có thể trả về null.
- getStackTrace() của exception ngoài cùng không chứa stack trace của từng callback.
- getSuppressed() mới là nơi chứa các lỗi cần điều tra.

Không nên kết luận rằng không có lỗi chỉ vì message hoặc cause của exception ngoài cùng rỗng.

### 3.1 Đọc lỗi đầu tiên và toàn bộ lỗi

Đoạn code sau in ra tất cả suppressed exception trực tiếp:

~~~java
static void printSuppressed(Throwable aggregate) {
    Throwable[] failures = aggregate.getSuppressed();

    System.err.println(
            aggregate.getClass().getSimpleName()
            + " contains " + failures.length + " failure(s)");

    for (int i = 0; i < failures.length; i++) {
        System.err.println("Failure #" + (i + 1));
        failures[i].printStackTrace(System.err);
    }
}
~~~

Gọi hàm này trong catch:

~~~java
try {
    Core.checkpointRestore();
} catch (CheckpointException e) {
    printSuppressed(e);
} catch (RestoreException e) {
    printSuppressed(e);
}
~~~

Gọi printStackTrace() trên từng lỗi giúp xem stack trace gốc, cause và các suppressed exception lồng bên trong lỗi đó.

Một exception callback có thể tự chứa suppressed exception. Ví dụ, khi đóng nhiều tài nguyên bằng try-with-resources, Java có thể giữ lỗi close phụ bên trong exception chính. Vì vậy, cây exception có thể sâu hơn một cấp.

### 3.2 In toàn bộ cause và suppressed tree

Khi cần log có cấu trúc, có thể duyệt cả cause và suppressed exception. Dùng identity set để tránh in lặp nếu cùng một đối tượng Throwable được tham chiếu từ nhiều nhánh.

~~~java
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

static void printThrowableTree(Throwable error) {
    Set<Throwable> visited =
            Collections.newSetFromMap(new IdentityHashMap<>());
    printThrowableTree(error, "", visited);
}

private static void printThrowableTree(
        Throwable error,
        String indent,
        Set<Throwable> visited) {

    if (error == null || !visited.add(error)) {
        return;
    }

    System.err.println(
            indent + error.getClass().getName()
            + ": " + error.getMessage());

    if (error.getCause() != null) {
        System.err.println(indent + "Caused by:");
        printThrowableTree(
                error.getCause(), indent + "  ", visited);
    }

    for (Throwable suppressed : error.getSuppressed()) {
        System.err.println(indent + "Suppressed:");
        printThrowableTree(
                suppressed, indent + "  ", visited);
    }
}
~~~

Cách duyệt này hữu ích khi hệ thống logging cần tách từng lỗi thành field riêng hoặc gửi exception tree tới công cụ quan sát. Nếu chỉ cần log chẩn đoán thông thường, printStackTrace() đã hiển thị cause và suppressed exception theo cấu trúc.

## 4. Phân biệt lỗi checkpoint và lỗi restore trong cùng một lần gọi

Khi ứng dụng gọi Core.checkpointRestore(), có thể hình dung luồng thành công như sau:

~~~mermaid
sequenceDiagram
    participant App as Application
    participant Core as CRaC Core
    participant Ctx as Global Context
    participant Image as Checkpoint Engine

    App->>Core: checkpointRestore()
    Core->>Ctx: beforeCheckpoint
    Ctx-->>Core: Không có lỗi
    Core->>Image: Tạo checkpoint image
    Image-->>Core: Image được tạo
    Note over App,Image: Tiến trình cũ kết thúc
    Image->>Core: Khởi tạo tiến trình từ image
    Core->>Ctx: afterRestore
    Ctx-->>Core: Không có lỗi
    Core-->>App: Tiếp tục sau checkpointRestore()
~~~

Trong luồng thành công, code sau lời gọi checkpointRestore() chạy trong tiến trình mới sau khi restore hoàn tất.

Nếu beforeCheckpoint thất bại, luồng khác xảy ra:

~~~mermaid
sequenceDiagram
    participant App as Original JVM
    participant Ctx as Global Context
    participant Engine as Checkpoint Engine

    App->>Ctx: beforeCheckpoint
    Ctx->>Ctx: Gọi các Resource callback
    Ctx-->>App: CheckpointException
    Note over App,Engine: Không tạo image
    App->>Ctx: afterRestore trên tiến trình ban đầu
    Ctx->>Ctx: Thử phục hồi Resource đã thay đổi
    Ctx-->>App: Kết quả phục hồi được gom vào CheckpointException
    App->>App: Bắt CheckpointException
~~~

Điểm quan trọng: khi checkpoint notification thất bại, CRaC chạy restore notification ngay trong tiến trình ban đầu để resource có cơ hội trở lại trạng thái hoạt động. Đây là một bước phục hồi lifecycle, không phải transaction rollback tổng quát. Các side effect đã xảy ra ở hệ thống bên ngoài không tự động được hoàn tác.

Vì vậy, CheckpointException có thể chứa:

- Lỗi từ một hoặc nhiều beforeCheckpoint callback.
- Lỗi từ một hoặc nhiều afterRestore callback được gọi để phục hồi tiến trình ban đầu.

Nếu checkpoint notification thành công và image được tạo, nhưng callback afterRestore trên tiến trình mới thất bại, lỗi được gom trong RestoreException.

## 5. Bắt exception từ Core.checkpointRestore()

Ví dụ dưới đây minh họa cách phân nhánh theo loại exception:

~~~java
import org.crac.CheckpointException;
import org.crac.Core;
import org.crac.RestoreException;

public final class CheckpointCoordinator {

    public void checkpoint() {
        try {
            Core.checkpointRestore();

            // Chỉ chạy tiếp ở tiến trình đã restore thành công.
            System.out.println("Restore completed");

        } catch (CheckpointException e) {
            System.err.println(
                    "Checkpoint preparation failed in original JVM");
            printThrowableTree(e);

            // Không có image mới được tạo.
            // Kiểm tra resource đã được phục hồi về trạng thái dùng được.

        } catch (RestoreException e) {
            System.err.println(
                    "One or more resources failed after restore");
            printThrowableTree(e);

            // Đang ở tiến trình mới nhưng resource chưa phục hồi đầy đủ.
            // Không mở readiness phục vụ traffic ở trạng thái này.

        } catch (UnsupportedOperationException e) {
            System.err.println(
                    "Checkpoint/restore is not supported by this runtime");
            e.printStackTrace(System.err);
        }
    }

    private static void printThrowableTree(Throwable error) {
        System.err.println(error.getClass().getName());

        for (Throwable failure : error.getSuppressed()) {
            failure.printStackTrace(System.err);
        }
    }
}
~~~

Ví dụ sử dụng package **org.crac**. Nếu ứng dụng dùng API tích hợp trong JDK, import các lớp tương ứng từ **jdk.crac**. Không trộn class từ hai package trong cùng một hệ thống Resource vì chúng là các kiểu Java khác nhau.

Cần nhớ ba trường hợp:

1. **Không có exception:** checkpoint và restore hoàn tất; lời gọi trả về trong tiến trình đã restore.
2. **CheckpointException:** checkpoint không tạo được image; ứng dụng tiếp tục trong tiến trình ban đầu sau quy trình notification phục hồi.
3. **RestoreException:** image đã được restore thành tiến trình mới, nhưng có lỗi trong các callback afterRestore.

UnsupportedOperationException là trường hợp riêng: runtime không hỗ trợ thao tác và không thực hiện notification. Đừng xử lý nó như một CheckpointException có suppressed callback failures.

Nếu checkpoint được kích hoạt từ bên ngoài bằng jcmd, HTTP endpoint hoặc controller, đoạn code gọi Core.checkpointRestore() có thể không phải nơi phát sinh yêu cầu. Khi đó, exception không nhất thiết được trả về cho client gửi lệnh. Hãy đọc log của JVM đích và kết quả từ checkpoint engine để xem lỗi chi tiết.

## 6. Thiết kế Resource callback để không làm mất lỗi

Context toàn cục gom exception giữa các Resource khác nhau. Tuy nhiên, trong một Resource, lập trình viên vẫn phải bảo đảm các bước cleanup độc lập được thử thực hiện.

Ví dụ, một Resource quản lý ba thành phần: file, socket và scheduler. Nếu đóng file thất bại rồi callback lập tức ném exception, socket và scheduler có thể không được đóng. Context không thể tự biết các bước nội bộ còn lại của Resource.

Có thể thu thập lỗi trong callback rồi ném một exception chính kèm suppressed exception phụ:

~~~java
import java.io.IOException;
import org.crac.Context;
import org.crac.Resource;

public final class CompositeResource implements Resource {

    private final LogFile logFile;
    private final ClientSocket socket;
    private final WorkerScheduler scheduler;

    public CompositeResource(
            LogFile logFile,
            ClientSocket socket,
            WorkerScheduler scheduler) {
        this.logFile = logFile;
        this.socket = socket;
        this.scheduler = scheduler;
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {

        Exception failure = null;

        try {
            scheduler.stopAndWait();
        } catch (Exception e) {
            failure = append(failure, e);
        }

        try {
            socket.close();
        } catch (Exception e) {
            failure = append(failure, e);
        }

        try {
            logFile.flushAndClose();
        } catch (Exception e) {
            failure = append(failure, e);
        }

        if (failure != null) {
            throw failure;
        }
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        // Tạo lại các thành phần theo thứ tự dependency.
    }

    private static Exception append(
            Exception primary,
            Exception next) {
        if (primary == null) {
            return next;
        }

        primary.addSuppressed(next);
        return primary;
    }
}
~~~

Ở ví dụ này, callback thử thực hiện cả ba thao tác. Lỗi đầu tiên trở thành exception chính; các lỗi tiếp theo được gắn vào nó. Khi callback ném exception ra ngoài, global Context tiếp tục gom exception đó vào CheckpointException.

Cấu trúc log có thể có nhiều tầng:

~~~text
CheckpointException
  Suppressed: IOException: Scheduler stop failed
    Suppressed: TimeoutException: Worker did not terminate
  Suppressed: IOException: Socket close failed
  Suppressed: IOException: Log flush failed
~~~

Cách gom lỗi bên trong Resource hữu ích khi một thành phần quản lý nhiều handle độc lập. Nếu một thao tác phụ thuộc vào thao tác trước, cần dừng đúng chuỗi đó khi điều kiện tiên quyết thất bại; không nên tiếp tục một thao tác có thể làm trạng thái tệ hơn.

### 6.1 Không nuốt exception

Một lỗi thường gặp là bắt exception rồi chỉ ghi log:

~~~java
@Override
public void beforeCheckpoint(
        Context<? extends Resource> context) {
    try {
        closeSocket();
    } catch (Exception e) {
        logger.error("Could not close socket", e);
    }
}
~~~

Callback trên trả về bình thường dù socket chưa đóng. Context có thể xem notification này là thành công và tiếp tục checkpoint. Nếu socket là tài nguyên bắt buộc phải giải phóng, hành vi đó khiến lỗi bị che giấu.

Hãy ghi log nếu cần, nhưng sau đó phải ném exception để CRaC biết callback thất bại:

~~~java
@Override
public void beforeCheckpoint(
        Context<? extends Resource> context) throws Exception {
    try {
        closeSocket();
    } catch (Exception e) {
        logger.error("Could not close socket", e);
        throw e;
    }
}
~~~

Không cần log ở mọi tầng nếu logger đã tự in exception tree ở tầng điều phối. Log lặp cùng stack trace ở từng Resource có thể làm nhiễu log. Nên chọn một nơi ghi đầy đủ exception tree, còn Resource bổ sung ngữ cảnh cần thiết như tên resource, loại handle và thao tác thất bại.

## 7. Phục hồi khi checkpoint thất bại

Khi một beforeCheckpoint callback thất bại, CRaC không tạo image và tiến trình ban đầu tiếp tục. Tuy nhiên, các Resource khác có thể đã đóng thành công trước khi lỗi được phát hiện.

Ví dụ:

- Scheduler đã dừng.
- Socket đã đóng.
- File log không đóng được.
- Một resource khác đã dừng consumer.

Sau lỗi, restore notification được gọi để các Resource có cơ hội mở lại tài nguyên và khởi động lại hoạt động. Vì vậy, afterRestore cần được thiết kế để xử lý trạng thái mà beforeCheckpoint chỉ hoàn tất một phần.

### 7.1 Callback phục hồi phải idempotent

Một Resource có thể chưa đóng tài nguyên nào, đóng một phần, hoặc đóng hoàn toàn khi checkpoint notification thất bại. Callback afterRestore không nên giả định rằng mọi thao tác beforeCheckpoint đều thành công.

Hãy lưu trạng thái lifecycle của chính Resource:

~~~java
public final class ManagedFileResource implements Resource {

    private FileChannel channel;
    private boolean reopenRequired;

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {

        if (channel != null && channel.isOpen()) {
            try {
                channel.close();
            } finally {
                if (!channel.isOpen()) {
                    channel = null;
                    reopenRequired = true;
                }
            }
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {

        if (reopenRequired) {
            FileChannel reopened = openChannel();
            channel = reopened;
            reopenRequired = false;
        }
    }

    private FileChannel openChannel() throws IOException {
        return FileChannel.open(
                Path.of("application.log"),
                StandardOpenOption.CREATE,
                StandardOpenOption.WRITE,
                StandardOpenOption.APPEND);
    }
}
~~~

Đây là ví dụ minh họa. Trong ứng dụng thực tế, cần khai báo import và xác định chính sách file cụ thể. Điểm chính là chỉ đánh dấu đã phục hồi sau khi mở tài nguyên thành công. Nếu openChannel() thất bại, reopenRequired vẫn true để lỗi được báo cáo và lần xử lý tiếp theo còn biết resource cần được mở.

### 7.2 Không giả định afterRestore chỉ chạy sau khi có image

Tên callback có thể khiến người đọc nghĩ nó chỉ chạy trong một tiến trình mới. Với global Context, khi checkpoint notification thất bại, restore notification vẫn được gọi ngay trong tiến trình ban đầu để phục hồi resource đã thay đổi.

Do đó, afterRestore nên được hiểu là callback đưa resource về trạng thái sau giai đoạn checkpoint, không nên phụ thuộc vào giả định rằng PID hoặc tiến trình đã thay đổi.

### 7.3 Phục hồi không phải rollback nghiệp vụ

Nếu beforeCheckpoint gửi một lệnh tới hệ thống bên ngoài rồi thất bại ở bước tiếp theo, CRaC không tự hoàn tác lệnh đó. Tương tự, việc mở lại socket không khôi phục một message đã được server xử lý hoặc một transaction đã commit.

Với side effect bên ngoài, cần dùng transaction, idempotency key, xác nhận message hoặc cơ chế bù trừ ở tầng nghiệp vụ. Callback chỉ quản lý vòng đời tài nguyên và trạng thái cần thiết để tiến trình tiếp tục.

## 8. Xử lý RestoreException và readiness của ứng dụng

RestoreException có nghĩa là tiến trình mới đã được tạo nhưng có ít nhất một callback phục hồi thất bại. Đây là trạng thái cần xử lý cẩn thận vì một số thành phần có thể hoạt động trong khi thành phần khác chưa sẵn sàng.

Ví dụ, database pool đã mở lại nhưng message consumer chưa kết nối được. Nếu ứng dụng mở readiness ngay, traffic có thể đi vào trong khi consumer hoặc một dependency quan trọng chưa phục hồi.

Một chính sách phục hồi có thể gồm:

1. Giữ readiness ở false.
2. Ghi đầy đủ exception tree cùng checkpoint ID và instance ID.
3. Phân loại lỗi theo resource và dependency.
4. Retry với backoff nếu lỗi có thể phục hồi và thao tác mở lại an toàn.
5. Chỉ bật readiness sau khi mọi dependency thiết yếu đã được xác minh.
6. Nếu hết thời hạn retry, dừng instance hoặc để bộ điều phối khởi động instance mới theo chính sách triển khai.

Không nên bắt RestoreException rồi tiếp tục phục vụ như thể restore thành công. Nếu callback thất bại vì credential sai hoặc file bắt buộc không tồn tại, retry vô hạn cũng không giúp ích. Cần có timeout, giới hạn retry và trạng thái lỗi có thể quan sát.

Một số lỗi có thể không ảnh hưởng chức năng thiết yếu. Ứng dụng có thể cho phép tiếp tục nếu resource đó thực sự tùy chọn, nhưng quyết định này phải được thể hiện trong readiness policy và được ghi nhận rõ ràng. Đừng bỏ qua lỗi chỉ vì callback không làm tiến trình dừng ngay.

## 9. Phân loại và chẩn đoán lỗi

Khi nhận được CheckpointException hoặc RestoreException, nên điều tra theo từng suppressed exception.

### 9.1 Phân loại theo callback

Đọc stack trace để xác định lỗi đến từ:

- beforeCheckpoint của Resource nào.
- afterRestore của Resource nào.
- Mã ứng dụng hay thư viện framework.
- API Java hay native library.
- Thao tác I/O, network, database hay thread lifecycle.

Một Resource nên bổ sung ngữ cảnh vào exception trước khi ném ra, chẳng hạn tên resource và hành động đang thực hiện:

~~~java
try {
    closeConnectionPool();
} catch (SQLException e) {
    throw new IllegalStateException(
            "Resource database-pool failed to close before checkpoint",
            e);
}
~~~

Cause của exception này giữ lại SQLException gốc. Khi Context gom exception, toàn bộ exception chain sẽ nằm dưới suppressed exception của CheckpointException.

### 9.2 Phân loại theo loại lỗi

| Nhóm lỗi | Ví dụ | Hướng điều tra |
|---|---|---|
| File system | File không tồn tại, permission denied, channel không đóng | Đường dẫn, quyền, mount, ownership và trạng thái channel |
| Network | Connection refused, timeout, DNS failure | DNS, route, peer, firewall, credential và timeout |
| Database | Pool shutdown hoặc reconnect thất bại | Transaction còn mở, session cũ, credential, database availability |
| Thread lifecycle | Worker không dừng, executor timeout | Thread đang chạy việc gì, interrupt policy và thời hạn drain |
| Native resource | Native handle không thể tạo lại | JNI/JNA, thư viện native, system call và tương thích runtime |
| Application state | Cache hoặc subscription chưa phục hồi | Trạng thái nghiệp vụ cần lưu và bước tái đồng bộ |

### 9.3 Dùng stack trace đúng cách

Khi in exception tổng hợp, nên giữ toàn bộ stack trace và suppressed exception. Chỉ log tên class hoặc message thường không đủ để xác định nơi tạo tài nguyên.

Đối với lỗi native hoặc lỗi từ checkpoint engine, stack trace Java có thể không chỉ ra chính xác nguyên nhân. Cần kết hợp log của runtime, checkpoint engine và công cụ hệ điều hành. Tài liệu CRaC Debugging mô tả ví dụ lỗi file descriptor còn mở và cách bật tùy chọn thu thập stack trace để tìm nguồn tạo FD.

### 9.4 Không chỉ xử lý lỗi đầu tiên

Nếu một CheckpointException có năm suppressed exception, xử lý lỗi đầu tiên rồi chạy lại checkpoint có thể chỉ làm lộ lỗi thứ hai, thứ ba. Hãy ghi nhận và nhóm tất cả lỗi trong một lần chạy, sửa các nguyên nhân độc lập, sau đó thử lại.

Nếu các lỗi có quan hệ phụ thuộc, xử lý theo thứ tự: lỗi khiến resource không thể dừng, lỗi cleanup phát sinh sau đó, rồi lỗi phục hồi. Giữ nguyên quan hệ cause và suppressed để không mất thứ tự và ngữ cảnh ban đầu.

## 10. Kiểm thử exception aggregation

Không chỉ kiểm tra đường đi thành công. Có thể tạo các Resource thử nghiệm chủ động ném exception để quan sát cách Context gom lỗi.

Ví dụ một Resource cố ý thất bại:

~~~java
public final class FailingResource implements Resource {

    private final String name;

    public FailingResource(String name) {
        this.name = name;
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        throw new IOException(
                name + ": simulated beforeCheckpoint failure");
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        throw new IOException(
                name + ": simulated afterRestore failure");
    }
}
~~~

Đăng ký nhiều instance trong môi trường kiểm thử:

~~~java
Context<? extends Resource> context = Core.getGlobalContext();

context.register(new FailingResource("resource-A"));
context.register(new FailingResource("resource-B"));
context.register(new FailingResource("resource-C"));
~~~

Khi yêu cầu checkpoint, kiểm tra:

- Các Resource có được gọi theo thứ tự của global Context hay không.
- Một callback thất bại có ngăn callback tiếp theo được gọi hay không.
- CheckpointException có chứa các suppressed exception từ tất cả callback thất bại hay không.
- Nếu checkpoint notification thất bại, afterRestore có được gọi trong tiến trình ban đầu hay không.
- Lỗi trong afterRestore khi phục hồi tiến trình ban đầu có được gom vào CheckpointException hay không.
- Nếu checkpoint notification thành công nhưng restore callback thất bại, RestoreException có chứa đầy đủ lỗi hay không.

Không chạy các Resource cố ý thất bại trong môi trường production. Dùng test runtime hỗ trợ CRaC và một môi trường có thể xóa checkpoint image sau thử nghiệm.

### 10.1 Ma trận tình huống

| beforeCheckpoint | afterRestore | Kết quả mong đợi |
|---|---|---|
| Tất cả thành công | Tất cả thành công | Checkpoint và restore thành công |
| Một callback lỗi | Phục hồi thành công | CheckpointException; không có image mới |
| Nhiều callback lỗi | Phục hồi thành công | Một CheckpointException chứa nhiều suppressed exception |
| Một callback lỗi | Một callback phục hồi cũng lỗi | CheckpointException chứa lỗi ở cả hai giai đoạn notification |
| Tất cả thành công | Một callback lỗi trên tiến trình mới | RestoreException |
| Tất cả thành công | Nhiều callback lỗi trên tiến trình mới | RestoreException chứa nhiều suppressed exception |

Bài kiểm thử nên xác nhận cả nội dung lỗi lẫn trạng thái resource sau khi callback hoàn tất. Chỉ đếm số exception là chưa đủ; cần bảo đảm các tài nguyên không bị bỏ quên và readiness không chuyển sang true khi còn lỗi thiết yếu.

## 11. Những lỗi xử lý thường gặp

### Chỉ đọc getMessage()

CheckpointException và RestoreException là exception tổng hợp, không có message riêng. getMessage() có thể trả về null trong khi có nhiều suppressed exception.

### Chỉ đọc getCause()

CRaC không dùng cause của exception ngoài cùng để lưu toàn bộ callback failures. Hãy đọc getSuppressed().

### Chỉ log exception ngoài cùng

Stack trace của aggregate không thay thế stack trace của từng callback. Ghi toàn bộ suppressed exception và cause để tìm lớp, dòng code và tài nguyên gây lỗi.

### Ném exception đầu tiên rồi bỏ qua cleanup còn lại

Global Context tiếp tục gọi Resource khác, nhưng không thể tự thực hiện các thao tác cleanup còn lại bên trong cùng một Resource. Hãy thử mọi thao tác độc lập và gom lỗi trước khi ném.

### Bắt lỗi rồi bỏ qua

Nếu callback trả về bình thường sau khi một thao tác thiết yếu thất bại, Context không biết resource đang ở trạng thái lỗi. Hãy truyền exception ra ngoài.

### Giả định CheckpointException có nghĩa tiến trình không thay đổi gì

Một số Resource có thể đã đóng tài nguyên trước khi Resource khác thất bại. Restore notification sẽ được gọi để phục hồi, nhưng đó không phải rollback tự động cho mọi side effect.

### Giả định RestoreException có nghĩa JVM không được restore

RestoreException báo lỗi trong callback sau restore. Tiến trình mới đã được tạo, nhưng trạng thái ứng dụng có thể chưa hoàn chỉnh. Cần giữ readiness false và xử lý lỗi.

### Nuốt RestoreException rồi mở traffic

Một resource thiết yếu chưa phục hồi có thể gây lỗi request, mất message hoặc hỏng trạng thái nghiệp vụ. Chỉ mở readiness sau khi xác minh thành phần bắt buộc.

### Để lỗi cleanup che mất lỗi ban đầu

Nếu một thao tác chính thất bại và bước cleanup cũng thất bại, hãy giữ lỗi chính làm exception chính và gắn lỗi cleanup bằng addSuppressed(). Không thay thế exception ban đầu bằng lỗi phát sinh trong finally.

## 12. Quy trình xử lý lỗi trong ứng dụng CRaC

Có thể áp dụng quy trình sau khi một lần checkpoint/restore thất bại:

**Bước 1 — Xác định exception ngoài cùng.** CheckpointException cho biết giai đoạn checkpoint notification thất bại; RestoreException cho biết giai đoạn restore notification thất bại.

**Bước 2 — Thu thập toàn bộ suppressed exception.** Duyệt getSuppressed(), in stack trace và tiếp tục đọc cause/suppressed lồng bên trong.

**Bước 3 — Xác định Resource và callback.** Dựa vào tên Resource, message có ngữ cảnh và stack trace để tìm thao tác thất bại.

**Bước 4 — Phân loại nguyên nhân.** Xác định lỗi từ file, socket, database, thread, native handle hay trạng thái nghiệp vụ.

**Bước 5 — Kiểm tra trạng thái sau lỗi.** Với CheckpointException, xác minh tiến trình ban đầu đã phục hồi resource. Với RestoreException, xác minh tiến trình mới có thể tiếp tục hay phải dừng.

**Bước 6 — Sửa nguyên nhân và thử lại.** Xử lý tất cả lỗi độc lập, kiểm thử callback và thực hiện checkpoint/restore lại trong môi trường phù hợp.

**Bước 7 — Lưu dấu vết vận hành.** Gắn checkpoint ID, instance ID, phase, resource name và timestamp vào log để truy vết qua nhiều lần thử.

Một hệ thống CRaC dễ chẩn đoán cần giữ được exception gốc, gom đủ lỗi từ các Resource và công bố trạng thái readiness đúng với kết quả phục hồi. Hai exception tổng hợp không phải là thông báo lỗi chung chung; chúng là điểm vào để tìm toàn bộ lỗi trong vòng đời checkpoint/restore.

## Tài liệu tham khảo

- [CRaC API — Package summary](https://crac.org/openjdk-builds/javadoc/api/java.base/jdk/crac/package-summary.html): mô tả luồng checkpoint/restore, suppressed exception và hành vi của global Context.
- [CRaC API — CheckpointException](https://crac.org/openjdk-builds/javadoc/api/java.base/jdk/crac/CheckpointException.html): exception tổng hợp cho các lỗi trong giai đoạn checkpoint.
- [CRaC API — RestoreException](https://crac.org/openjdk-builds/javadoc/api/java.base/jdk/crac/RestoreException.html): exception tổng hợp cho các lỗi trong giai đoạn restore.
- [CRaC API — Core](https://crac.org/openjdk-builds/javadoc/api/java.base/jdk/crac/Core.html): chữ ký và kết quả của Core.checkpointRestore().
- [CRaC API — Resource](https://crac.org/openjdk-builds/javadoc/api/java.base/jdk/crac/Resource.html): hợp đồng của beforeCheckpoint và afterRestore.
- [CRaC — Debugging failures](https://crac.org/reference/debugging/): ví dụ suppressed exception và chẩn đoán lỗi file descriptor.
- [Java Throwable API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/Throwable.html): getCause(), getSuppressed(), addSuppressed() và printStackTrace().

