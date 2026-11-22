# Giả lập ngoại lệ trong beforeCheckpoint() và afterRestore()

CRaC (Coordinated Restore at Checkpoint) gọi các callback Resource để ứng dụng chuẩn bị tài nguyên trước khi tạo checkpoint image và phục hồi chúng sau khi tiến trình được restore. Hai callback nằm ở hai ranh giới khác nhau:

- beforeCheckpoint() chạy trước khi runtime tạo checkpoint. Ứng dụng thường drain công việc, đồng bộ dữ liệu và đóng socket, file handle hoặc connection pool.
- afterRestore() chạy trong tiến trình đã được khôi phục. Ứng dụng thường tạo lại kết nối, xác minh dependency và khởi động lại worker.

Các callback có thể thất bại vì lỗi I/O, timeout, credential hết hạn, dependency không sẵn sàng, thiếu quyền hoặc lỗi lập trình. Nếu chỉ kiểm thử đường chạy thành công, ứng dụng có thể rơi vào trạng thái nửa sẵn sàng mà không được phát hiện.

Cách kiểm thử là chủ động đưa lỗi vào những điểm đã xác định, xác nhận trạng thái tài nguyên sau lỗi, rồi kiểm tra đường phục hồi tương ứng. Lỗi trong beforeCheckpoint() làm checkpoint preparation thất bại; lỗi trong afterRestore() có nghĩa tiến trình đã restore chưa thể được coi là sẵn sàng. Hai nhánh cần được kiểm thử riêng.

## 1. Mục tiêu của fault injection

Fault injection là kỹ thuật cố ý tạo lỗi có kiểm soát tại một điểm trong luồng thực thi.

Trong kiểm thử CRaC, có thể mô phỏng:

- Resource không thể flush hoặc đóng file.
- Database pool không drain được connection đang hoạt động.
- HTTP client không đóng được socket.
- Secret provider không cấp được token mới.
- DNS hoặc remote service chưa sẵn sàng.
- File hoặc mount không tồn tại sau restore.
- Resource được khởi tạo một phần rồi ném exception.
- Bước validation thất bại sau khi kết nối đã mở.
- Một Resource thành công nhưng Resource tiếp theo thất bại.

Một test hữu ích cần xác nhận:

1. Lỗi được truyền ra đúng tầng gọi.
2. Ứng dụng không tiếp tục ở trạng thái nửa sẵn sàng.
3. Tài nguyên đã thay đổi được nhận diện chính xác.
4. Tài nguyên có thể được phục hồi hoặc được đánh dấu không thể phục hồi.
5. Request, worker và scheduler không chạy khi dependency chưa sẵn sàng.
6. Log giữ được nguyên nhân và exception chain mà không làm lộ secret.
7. Lần thử checkpoint tiếp theo không bị ảnh hưởng bởi trạng thái còn sót lại.

## 2. Xác định điểm lỗi trong từng callback

Trước khi viết test, chia callback thành các bước nhỏ và xác định ranh giới side effect.

Một beforeCheckpoint() quản lý pool có thể gồm:

~~~text
Ngừng nhận request mới
        |
        v
Chờ request và transaction đang chạy
        |
        v
Flush dữ liệu cần thiết
        |
        v
Đóng connection pool
        |
        v
Đánh dấu resource đã đóng
~~~

Có thể chèn lỗi khi ngừng nhận request, lúc chờ transaction, sau khi flush hoặc sau khi pool đã đóng.

Một afterRestore() có thể gồm:

~~~text
Đọc cấu hình và credential hiện tại
        |
        v
Tạo connection pool mới
        |
        v
Kiểm tra database
        |
        v
Khởi động worker
        |
        v
Mở request gate
~~~

Có thể chèn lỗi trước khi mở pool, ngay sau khi mở pool, khi validation thất bại hoặc trước khi mở request gate.

Phân biệt lỗi trước và sau side effect rất quan trọng:

| Vị trí lỗi | Trạng thái có thể còn lại |
|---|---|
| Trước khi drain | Resource có thể vẫn hoạt động bình thường |
| Sau khi drain | Request gate đã đóng, worker có thể đã dừng |
| Sau khi đóng resource | Tiến trình gốc cần mở lại nếu checkpoint bị hủy |
| Trong lúc tạo resource | Có thể còn socket hoặc thread được tạo một phần |
| Sau khi tạo resource | Handle tồn tại nhưng chưa được xác minh |
| Trước khi mở gate | Dependency có thể sẵn sàng nhưng ứng dụng vẫn chưa nhận traffic |

CRaC không tự rollback các side effect mà ứng dụng đã thực hiện trước khi callback ném exception. Nếu ba resource đã đóng rồi resource thứ tư thất bại, ứng dụng cần biết trạng thái của cả ba resource và cách phục hồi chúng.

## 3. Tạo FaultInjector xác định và có thể bật một lần

Không nên rải các điều kiện test trong production code hoặc dùng lỗi ngẫu nhiên. Tạo một abstraction nhỏ để đưa lỗi vào đúng điểm.

~~~java
public enum FaultPoint {
    BEFORE_CHECKPOINT_AFTER_DRAIN,
    BEFORE_CHECKPOINT_AFTER_CLOSE,
    AFTER_RESTORE_BEFORE_OPEN,
    AFTER_RESTORE_AFTER_OPEN,
    AFTER_RESTORE_BEFORE_READY
}
~~~

Implementation đơn giản dùng AtomicReference:

~~~java
import java.util.concurrent.atomic.AtomicReference;

public final class FaultInjector {
    private final AtomicReference<FaultPoint> armed =
        new AtomicReference<>();

    public void arm(FaultPoint point) {
        armed.set(point);
    }

    public void hit(FaultPoint point) throws InjectedFailure {
        if (armed.compareAndSet(point, null)) {
            throw new InjectedFailure(
                "Injected failure at " + point
            );
        }
    }
}
~~~

Exception riêng giúp test phân biệt lỗi giả lập với lỗi thật:

~~~java
public final class InjectedFailure extends Exception {
    public InjectedFailure(String message) {
        super(message);
    }
}
~~~

Mỗi test chỉ kích hoạt một FaultPoint. Lỗi được tiêu thụ một lần nên recovery không vô tình ném lại cùng lỗi. Production có thể dùng implementation không làm gì.

Không bật fault injection qua endpoint public. Nếu điều khiển bằng cấu hình, chỉ cho phép trong profile test và xác nhận profile đó không thể được triển khai vào production.

## 4. Mô phỏng lỗi trong beforeCheckpoint()

Ví dụ Resource quản lý một handle và request gate. Các interface là abstraction của ứng dụng:

~~~java
public interface RequestGate {
    void stopAndDrain() throws Exception;
    void resume();
    void keepClosed();
}

public interface ManagedHandle {
    void validate() throws Exception;
    void close() throws Exception;
}

public interface HandleFactory {
    ManagedHandle open() throws Exception;
}
~~~

Resource minh họa:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class TestableFileResource implements Resource {
    enum State {
        READY, PREPARING, CLOSED, RESTORING, FAILED
    }

    private final RequestGate gate;
    private final HandleFactory factory;
    private final FaultInjector faults;

    private ManagedHandle handle;
    private volatile State state = State.READY;

    public TestableFileResource(
            RequestGate gate,
            HandleFactory factory,
            FaultInjector faults) throws Exception {
        this.gate = gate;
        this.factory = factory;
        this.faults = faults;
        this.handle = factory.open();
        Core.getGlobalContext().register(this);
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        prepareForCheckpoint();
    }

    synchronized void prepareForCheckpoint() throws Exception {
        state = State.PREPARING;
        gate.stopAndDrain();

        faults.hit(FaultPoint.BEFORE_CHECKPOINT_AFTER_DRAIN);

        if (handle != null) {
            handle.close();
            handle = null;
        }

        state = State.CLOSED;
        faults.hit(FaultPoint.BEFORE_CHECKPOINT_AFTER_CLOSE);
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        restoreResources();
    }

    synchronized void restoreResources() throws Exception {
        state = State.RESTORING;
        ManagedHandle opened = null;

        try {
            faults.hit(FaultPoint.AFTER_RESTORE_BEFORE_OPEN);

            opened = factory.open();
            faults.hit(FaultPoint.AFTER_RESTORE_AFTER_OPEN);

            opened.validate();
            faults.hit(FaultPoint.AFTER_RESTORE_BEFORE_READY);

            handle = opened;
            opened = null;
            state = State.READY;
            gate.resume();

        } catch (Exception failure) {
            state = State.FAILED;
            gate.keepClosed();

            if (opened != null) {
                try {
                    opened.close();
                } catch (Exception closeFailure) {
                    failure.addSuppressed(closeFailure);
                }
            }

            throw failure;
        }
    }

    synchronized void recoverAfterAbortedCheckpoint()
            throws Exception {
        if (handle == null) {
            handle = factory.open();
        }

        handle.validate();
        state = State.READY;
        gate.resume();
    }

    State state() {
        return state;
    }
}
~~~

Đây là khung minh họa. Implementation thật cần xử lý cleanup nếu factory.open() tạo tài nguyên một phần rồi ném exception, và cần xác định close() có an toàn khi được gọi nhiều lần hay không.

Nếu lỗi xảy ra tại BEFORE_CHECKPOINT_AFTER_DRAIN, handle vẫn mở nhưng request gate đã đóng. Nếu lỗi xảy ra tại BEFORE_CHECKPOINT_AFTER_CLOSE, handle đã đóng và tiến trình gốc cần tạo lại handle nếu checkpoint bị hủy. Hai tình huống cần test riêng.

## 5. Kiểm tra checkpoint bị hủy sau lỗi beforeCheckpoint()

Khi beforeCheckpoint() ném exception, quá trình chuẩn bị checkpoint thất bại. Nếu ứng dụng chủ động gọi Core.checkpointRestore(), API CRaC báo lỗi checkpoint qua CheckpointException.

Nhánh phục hồi cần đưa tiến trình ban đầu về trạng thái có thể chạy:

~~~java
try {
    Core.checkpointRestore();

    // Khi restore thành công, afterRestore() đã chạy.
    application.markRestoredAndReady();

} catch (CheckpointException checkpointFailure) {
    try {
        fileResource.recoverAfterAbortedCheckpoint();
    } catch (Exception recoveryFailure) {
        checkpointFailure.addSuppressed(recoveryFailure);
        application.markNotReady();
    }

    throw checkpointFailure;

} catch (RestoreException restoreFailure) {
    application.markNotReady();
    throw restoreFailure;
}
~~~

Ví dụ giả định fileResource là resource đã đóng hoặc thay đổi trạng thái. Ứng dụng thực tế có thể cần phục hồi nhiều resource và chỉ mở request gate sau khi tất cả đã phục hồi thành công.

Không giả định afterRestore() chạy như callback rollback khi checkpoint bị hủy. afterRestore() phục vụ tiến trình thực sự được restore.

### Nếu checkpoint được yêu cầu bằng jcmd

~~~bash
jcmd <pid> JDK.checkpoint
~~~

Khi lệnh được gửi từ terminal bên ngoài, luồng gọi API trong ứng dụng không có khối try/catch bao quanh lời gọi đó. Không thể dựa vào catch CheckpointException trong coordinator để tự phục hồi tiến trình gốc.

Nếu rollback ngay trong ứng dụng là yêu cầu bắt buộc, nên điều phối checkpoint qua API trong ứng dụng hoặc có cơ chế recovery độc lập. Với jcmd, cần kiểm thử kết quả lệnh, log runtime và trạng thái process bằng harness bên ngoài.

## 6. Mô phỏng lỗi trong afterRestore()

afterRestore() chạy trong tiến trình được khôi phục. Một số resource có thể đã được mở lại nhưng dependency khác vẫn chưa sẵn sàng.

Các điểm lỗi có ý nghĩa khác nhau:

- AFTER_RESTORE_BEFORE_OPEN: chưa tạo handle mới.
- AFTER_RESTORE_AFTER_OPEN: handle tồn tại nhưng chưa được xác minh.
- AFTER_RESTORE_BEFORE_READY: handle đã xác minh nhưng ứng dụng chưa được phép nhận việc.

Nếu callback ném exception, không mở request gate hoặc đánh dấu ứng dụng ready. Giữ trạng thái FAILED/RESTORING và truyền exception ra ngoài theo hợp đồng API.

### Cleanup khi restore thất bại một phần

Phương thức restoreResources() trong ví dụ ở phần trước giữ handle mới ở biến cục bộ cho đến khi validation hoàn tất. Nếu fault injection hoặc validation ném exception, nó đóng handle mới, giữ gate đóng và gắn lỗi cleanup vào exception gốc bằng addSuppressed(). Nhờ vậy, field handle không trỏ tới một resource mới chỉ được tạo một phần.

Gate cần được giữ đóng trong suốt quá trình bootstrap restore. Không nuốt exception rồi trả về bình thường nếu dependency chưa thể hoạt động.

## 7. Phân biệt CheckpointException và RestoreException

Khi gọi API điều phối CRaC trực tiếp, cần phân biệt hai nhánh:

| Exception | Thời điểm | Điều cần kiểm tra |
|---|---|---|
| CheckpointException | Quá trình checkpoint không hoàn tất | Phục hồi tiến trình ban đầu sau lỗi preparation |
| RestoreException | Quá trình restore gặp lỗi | Instance được restore không mở traffic khi callback thất bại |

Test beforeCheckpoint() phải xác nhận nhánh checkpoint failure. Test afterRestore() phải xác nhận nhánh restore failure. Không gộp cả hai vào một catch Exception chung vì sẽ che khuất loại lỗi và đường phục hồi cần chạy.

Exception chain và chi tiết chẩn đoán có thể phụ thuộc phiên bản JDK/CRaC và cách checkpoint được kích hoạt. Trong integration test, ghi nhận cause và suppressed exception thay vì phụ thuộc vào một message text cố định.

## 8. Unit test cho từng điểm lỗi

Unit test gọi logic callback trực tiếp mà không cần tạo checkpoint image. Có thể tách phần xử lý thành phương thức package-private như prepareForCheckpoint() và restoreResources() để kiểm thử.

Ví dụ JUnit 5 kiểm tra lỗi sau khi handle đóng:

~~~java
@Test
void checkpointFailureAfterCloseCanBeRecovered() throws Exception {
    FaultInjector faults = new FaultInjector();
    FakeGate gate = new FakeGate();
    FakeHandleFactory factory = new FakeHandleFactory();

    TestableFileResource resource =
        new TestableFileResource(gate, factory, faults);

    faults.arm(FaultPoint.BEFORE_CHECKPOINT_AFTER_CLOSE);

    assertThrows(
        InjectedFailure.class,
        resource::prepareForCheckpoint
    );

    assertEquals(
        TestableFileResource.State.CLOSED,
        resource.state()
    );
    assertTrue(gate.isClosed());
    assertEquals(1, factory.openCount());
    assertEquals(1, factory.closeCount());

    resource.recoverAfterAbortedCheckpoint();

    assertEquals(
        TestableFileResource.State.READY,
        resource.state()
    );
    assertFalse(gate.isClosed());
    assertEquals(2, factory.openCount());
}
~~~

Ví dụ kiểm tra lỗi sau khi mở handle mới nhưng trước khi readiness được bật:

~~~java
@Test
void restoreFailureAfterOpenKeepsApplicationClosed() throws Exception {
    FaultInjector faults = new FaultInjector();
    FakeGate gate = new FakeGate();
    FakeHandleFactory factory = new FakeHandleFactory();

    TestableFileResource resource =
        new TestableFileResource(gate, factory, faults);

    resource.prepareForCheckpoint();
    faults.arm(FaultPoint.AFTER_RESTORE_AFTER_OPEN);

    assertThrows(
        InjectedFailure.class,
        resource::restoreResources
    );

    assertTrue(gate.isClosed());
    assertEquals(
        TestableFileResource.State.FAILED,
        resource.state()
    );
    assertEquals(2, factory.closeCount());
}
~~~

Ví dụ thứ hai giả định restoreResources() có cleanup partial handle như mẫu ở phần trước. Test cần xác nhận handle vừa mở đã được đóng khi lỗi xảy ra.

Các assertion quan trọng:

- Exception đúng loại được ném ra.
- State đúng với điểm lỗi.
- Request gate vẫn đóng nếu restore chưa hoàn tất.
- Handle được mở và đóng đúng số lần.
- Worker hoặc scheduler không chạy ngoài ý muốn.
- Cleanup failure được gắn vào exception gốc bằng addSuppressed().
- Recovery thành công đưa resource về READY.
- Recovery thất bại giữ resource ở FAILED và gate đóng.

Không chỉ kiểm tra assertThrows. Trạng thái sau exception mới là phần quan trọng.

## 9. Ma trận fault injection

| Callback | Điểm lỗi | Kết quả cần xác nhận |
|---|---|---|
| beforeCheckpoint | Trước khi drain | Không đóng resource |
| beforeCheckpoint | Sau khi drain | Gate được phục hồi nếu checkpoint bị hủy |
| beforeCheckpoint | Sau khi đóng handle | Handle được mở lại trong tiến trình gốc |
| beforeCheckpoint | Khi đóng resource thứ hai | Resource đã đóng trước đó được phục hồi |
| afterRestore | Trước khi mở handle | Gate đóng, ứng dụng chưa ready |
| afterRestore | Sau khi mở handle | Partial handle được cleanup |
| afterRestore | Validation thất bại | Worker và listener chưa start |
| afterRestore | Trước khi mở gate | Traffic vẫn bị chặn |
| recovery | Mở lại resource thất bại | Lỗi recovery được giữ lại, instance không ready |
| cleanup | Đóng partial resource thất bại | Lỗi cleanup được suppressed và ghi nhận |

Với nhiều Resource, thêm test một Resource chuẩn bị thành công nhưng Resource tiếp theo thất bại. Kiểm tra mọi resource đã thay đổi trạng thái có thể được phục hồi hoặc đưa vào trạng thái an toàn.

## 10. Kiểm thử nhiều Resource và dependency

Ứng dụng thường có listener, worker, JDBC pool, HTTP client và file channel:

~~~text
Request Listener
       |
       v
Background Worker
       |
       +------> JDBC Pool
       |
       +------> HTTP Client
       |
       +------> File Channel
~~~

Trước checkpoint, listener và worker cần dừng trước dependency mà chúng sử dụng. Sau restore, dependency phải được mở lại trước khi worker và listener chạy.

Không dựa vào thứ tự đăng ký Resource một cách ngầm định nếu tính đúng đắn phụ thuộc vào thứ tự. Dùng coordinator với trình tự tường minh hoặc integration CRaC được hỗ trợ.

Test có thể ghi event log:

~~~java
List<String> events = new CopyOnWriteArrayList<>();

events.add("gate.stop");
events.add("worker.stop");
events.add("jdbc.close");
events.add("http.close");
~~~

Sau callback hoặc coordinator, so sánh event log với thứ tự mà thiết kế yêu cầu. Khi một callback lỗi, xác nhận các bước rollback được gọi đúng theo dependency.

## 11. Integration test với checkpoint thật

Unit test chỉ gọi trực tiếp phương thức callback không kiểm tra toàn bộ runtime. Cần integration test chạy trong JVM riêng với JDK CRaC và môi trường checkpoint/restore thực tế.

Một harness có thể:

1. Khởi chạy ứng dụng thử nghiệm trong process riêng.
2. Đăng ký Resource kiểm thử.
3. Ghi trạng thái và mốc callback vào file kết quả.
4. Bật một FaultPoint xác định.
5. Gọi Core.checkpointRestore() hoặc kích hoạt bằng công cụ runtime.
6. Thu thập exit code, stdout/stderr và trạng thái process.
7. Kiểm tra callback đã chạy, exception xuất hiện và resource đang ở trạng thái nào.

Không chạy checkpoint integration test trong cùng JVM với test suite thông thường. Restore có thể thay đổi luồng thực thi và trạng thái process theo cách không phù hợp với test runner.

### Test qua Core.checkpointRestore()

~~~java
try {
    Core.checkpointRestore();
    writeMarker("RESTORE_RETURNED");
} catch (CheckpointException failure) {
    writeMarker("CHECKPOINT_FAILED");
    recoverOriginalProcess();
} catch (RestoreException failure) {
    writeMarker("RESTORE_FAILED");
    keepApplicationNotReady();
}
~~~

Marker nên được ghi vào file kết quả bền vững hoặc test channel độc lập. Không chỉ dựa vào log buffer trong heap vì buffer có thể chưa được flush khi process gặp lỗi.

### Test bằng jcmd

~~~bash
jcmd <pid> JDK.checkpoint
~~~

Harness bên ngoài theo dõi kết quả lệnh, log runtime và process. Vì lệnh được thực hiện bên ngoài JVM, ứng dụng không có catch block trong luồng gọi API để tự xử lý exception của lệnh đó.

Trong báo cáo test, ghi rõ đang dùng Core.checkpointRestore() hay jcmd. Hai cách kích hoạt có đường quan sát và phục hồi khác nhau.

## 12. Mô phỏng lỗi dependency bên ngoài

Một số lỗi nên được tạo bằng test double hoặc dịch vụ thử nghiệm để kiểm tra hành vi thực tế của thư viện:

- Database từ chối kết nối.
- HTTP endpoint trả lỗi hoặc timeout.
- DNS không phân giải được.
- Secret manager trả lỗi xác thực.
- File path không tồn tại hoặc chỉ đọc.
- Mount volume chưa sẵn sàng.
- TLS certificate không hợp lệ.
- Native client không khởi tạo được.

Với lỗi mạng, dùng mock server hoặc service test có thể điều khiển được. Với lỗi file, dùng thư mục test riêng và quyền truy cập được thiết lập có chủ đích. Không sửa quyền hoặc xóa dữ liệu trên filesystem production để tạo lỗi.

Test cần xác nhận timeout, retry có giới hạn, backoff và readiness behavior. Không để callback retry vô hạn vì có thể làm restore treo hoặc kéo dài thời gian khởi động.

## 13. Kiểm tra exception chain và log

Log nên giữ:

- Tên Resource và callback.
- Operation đang thực hiện.
- FaultPoint hoặc trạng thái trước lỗi.
- Loại exception và cause.
- Thời gian thực hiện.
- Kết quả cleanup.
- Instance ID hoặc checkpoint generation không nhạy cảm.

Ví dụ log có cấu trúc:

~~~text
event=crac_callback_failure
resource=fileResource
callback=beforeCheckpoint
operation=close_handle
state=CLOSED
exception=IOException
checkpointGeneration=test-42
~~~

Không ghi token, password, private key, request body hoặc nội dung file nhạy cảm. Nếu exception message chứa credential hoặc connection string, cần redact trước khi ghi.

Nếu cleanup thất bại trong lúc đang xử lý lỗi chính, dùng addSuppressed() để giữ cả hai lỗi:

~~~java
try {
    handle.close();
} catch (Exception closeFailure) {
    originalFailure.addSuppressed(closeFailure);
}

throw originalFailure;
~~~

Lỗi gốc cho biết callback thất bại ở đâu; suppressed exception cho biết cleanup cũng gặp vấn đề.

## 14. Giữ fault injection ngoài production

Fault injection cần có phạm vi rõ ràng:

- Chỉ cung cấp implementation FaultInjector trong test source hoặc test profile.
- Production mặc định dùng implementation không gây lỗi.
- Không tạo endpoint public để kích hoạt lỗi.
- Nếu bật qua cấu hình, chỉ cho phép trong môi trường test cô lập.
- Ghi log khi fault injection được kích hoạt.
- Đặt timeout cho integration test.
- Dọn process, checkpoint image, file tạm và test volume sau test.
- Không dùng secret production hoặc checkpoint image production làm fixture.

Có thể dùng interface:

~~~java
public interface Faults {
    void hit(FaultPoint point) throws Exception;
}

public final class NoOpFaults implements Faults {
    @Override
    public void hit(FaultPoint point) {
        // Không gây lỗi trong production.
    }
}
~~~

Test thay NoOpFaults bằng FaultInjector. Việc tách interface giúp production code không phụ thuộc vào environment variable hoặc endpoint điều khiển lỗi.

## 15. Những lỗi thường gặp trong bộ kiểm thử

**Chỉ kiểm tra exception:** test pass nhưng file channel vẫn đóng hoặc worker vẫn chạy. Hãy kiểm tra state, open/close count và readiness.

**Dùng lỗi ngẫu nhiên:** test khó tái hiện. Dùng FaultPoint cụ thể và kích hoạt một lần.

**Dùng cùng process cho nhiều lần restore:** restore có thể thay đổi luồng thực thi. Dùng JVM riêng cho từng kịch bản integration.

**Dựa vào thứ tự callback chưa được bảo đảm:** nếu cần thứ tự, điều phối trong coordinator hoặc integration được hỗ trợ.

**Retry vô hạn trong afterRestore():** dependency không sẵn sàng có thể khiến callback không kết thúc. Dùng timeout và backoff có giới hạn.

**Nuốt exception:** runtime có thể tiếp tục trong khi resource chưa an toàn. Chỉ catch để cleanup hoặc bổ sung ngữ cảnh rồi truyền lỗi ra ngoài nếu callback không thể hoàn tất.

## 16. Quy trình kiểm thử đề xuất

### Chuẩn bị

1. Tạo Resource có trạng thái quan sát được.
2. Tách thao tác đóng/mở tài nguyên khỏi callback để unit test.
3. Thêm FaultPoint tại các ranh giới side effect quan trọng.
4. Tạo fake gate, fake handle factory và event recorder.
5. Chuẩn bị JVM và thư mục riêng cho integration test.

### Kiểm thử beforeCheckpoint()

1. Kích hoạt lỗi trước khi drain.
2. Kích hoạt lỗi sau khi drain.
3. Kích hoạt lỗi sau khi đóng handle.
4. Kích hoạt lỗi khi đóng resource thứ hai trong một nhóm.
5. Xác nhận checkpoint được báo thất bại.
6. Với Core.checkpointRestore(), chạy recovery trong tiến trình ban đầu.
7. Xác nhận resource được mở lại và readiness chỉ bật sau khi recovery thành công.

### Kiểm thử afterRestore()

1. Tạo checkpoint thành công trong môi trường test.
2. Restore với lỗi trước khi mở resource.
3. Restore với lỗi sau khi mở một phần resource.
4. Restore với lỗi trong validation.
5. Restore với lỗi ngay trước khi mở request gate.
6. Xác nhận exception được báo ra đúng đường lỗi.
7. Xác nhận request gate đóng và worker không chạy khi restore chưa hoàn tất.

### Kiểm thử phục hồi và lặp lại

1. Làm cho recovery thành công sau checkpoint failure.
2. Làm cho recovery thất bại và xác nhận ứng dụng vẫn not-ready.
3. Chạy lại checkpoint sau khi recovery thành công.
4. Chạy nhiều lần để phát hiện handle bị leak hoặc callback không idempotent.
5. Kiểm tra log, metric và cleanup artifact.

## 17. Nguyên tắc cần ghi nhớ

- beforeCheckpoint() và afterRestore() là hai điểm lỗi có hậu quả khác nhau.
- Fault injection nên xác định bằng FaultPoint, có thể bật một lần và tái hiện được.
- Kiểm tra lỗi cả trước và sau side effect.
- CRaC không tự rollback resource mà ứng dụng đã đóng hoặc thay đổi trước khi callback thất bại.
- Lỗi beforeCheckpoint() làm checkpoint preparation thất bại; tiến trình gốc cần phục hồi resource đã thay đổi.
- Lỗi afterRestore() phải giữ ứng dụng ở trạng thái chưa sẵn sàng.
- afterRestore() không phải callback rollback khi checkpoint bị hủy.
- Phân biệt CheckpointException và RestoreException khi điều phối bằng Core.checkpointRestore().
- Với jcmd từ bên ngoài, kiểm thử qua harness; luồng ứng dụng không bắt exception của lệnh đó.
- Unit test kiểm tra logic callback; integration test trong JVM riêng kiểm tra runtime thật.
- Kiểm tra state, side effect, readiness, cleanup và exception chain, không chỉ assertThrows.
- Không nuốt exception nếu resource chưa thể đưa về trạng thái an toàn.
- Không bật fault injection trong production hoặc dùng dữ liệu production để thử lỗi.
- Đặt timeout và giới hạn retry để callback không treo vô hạn.

Giả lập ngoại lệ có chủ đích giúp kiểm tra những trạng thái mà đường chạy bình thường không bộc lộ: resource đã đóng một phần, client mới chỉ được tạo một phần hoặc dependency chưa sẵn sàng sau restore. Khi từng điểm lỗi có trạng thái mong đợi, đường rollback rõ ràng và integration test chạy trên runtime thật, ứng dụng có thể thất bại theo cách kiểm soát được thay vì tiếp tục nhận công việc trong trạng thái không nhất quán.
