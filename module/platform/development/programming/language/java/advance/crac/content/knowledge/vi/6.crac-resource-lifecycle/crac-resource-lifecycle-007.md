# Thiết kế callback có thể xử lý trạng thái khởi tạo dở dang

Trong ứng dụng Java, một resource hiếm khi được tạo trong một thao tác duy nhất. Để mở một HTTP server, ứng dụng có thể đọc cấu hình, tạo executor, bind socket và đăng ký handler. Một connection pool có thể tạo nhiều connection, kiểm tra health rồi mới được đưa vào sử dụng. Bất kỳ bước nào cũng có thể thất bại giữa chừng.

CRaC (Coordinated Restore at Checkpoint) thêm hai điểm chuyển trạng thái vào vòng đời của ứng dụng: callback trước checkpoint và callback sau restore. Nếu callback giả định mọi thành phần đã khởi tạo đầy đủ, một lỗi xảy ra giữa quá trình startup có thể khiến callback đóng nhầm tài nguyên chưa tồn tại, bỏ sót tài nguyên đã mở một phần hoặc đánh dấu ứng dụng sẵn sàng dù chỉ một phần dependency được khôi phục.

Thiết kế tốt cần theo dõi trạng thái thực tế của từng resource, xử lý được thao tác khởi tạo thất bại giữa chừng, đóng tài nguyên theo thứ tự ngược với lúc mở và chỉ công bố ứng dụng sẵn sàng sau khi toàn bộ thành phần bắt buộc đã hoạt động.

## 1. Khởi tạo dở dang xuất hiện khi nào?

Một resource có thể ở trạng thái chưa hoàn chỉnh trong nhiều tình huống:

- Constructor hoặc factory mở được một phần tài nguyên rồi gặp exception.
- Startup của ứng dụng đang chạy thì checkpoint được yêu cầu.
- Một dependency bắt buộc không kết nối được, trong khi các dependency trước đó đã mở thành công.
- Ứng dụng có resource tùy chọn, chỉ được tạo khi một tính năng được bật.
- Restore thành công một số resource nhưng resource tiếp theo không thể kết nối đến hệ thống bên ngoài.
- Một callback bị timeout hoặc bị gián đoạn trong khi đang đóng/mở tài nguyên.

Ví dụ, khởi tạo một HTTP server có thể gồm các bước:

~~~text
NEW
 │
 ▼
Đọc cấu hình
 │
 ▼
Tạo executor
 │
 ▼
Bind socket
 │
 ▼
Đăng ký handler
 │
 ▼
Bắt đầu nhận request
 │
 ▼
READY
~~~

Nếu bind socket thành công nhưng đăng ký handler thất bại, ứng dụng đã tạo ra một tài nguyên hệ điều hành nhưng server chưa ở trạng thái phục vụ. Một biến boolean duy nhất như initialized = true/false không mô tả được chính xác tình trạng này.

Callback cần biết đã thử mở những thành phần nào, thành phần nào thực sự đang hoạt động và thành phần nào có thể cần được đóng dọn sau lỗi.

## 2. Mô hình trạng thái cho vòng đời resource

Thay vì suy luận trạng thái từ việc một field có khác null hay không, hãy mô hình hóa vòng đời thành các trạng thái rõ ràng.

| Trạng thái | Ý nghĩa |
|---|---|
| NEW | Resource manager đã được tạo, chưa bắt đầu khởi tạo |
| INITIALIZING | Đang mở các thành phần theo thứ tự dependency |
| READY | Tất cả thành phần bắt buộc đã khởi tạo thành công |
| PREPARING | Đang dừng và giải phóng tài nguyên trước checkpoint |
| PREPARED | Các tài nguyên cần đóng đã được giải phóng, trạng thái sẵn sàng để checkpoint |
| RESTORING | Đang tạo lại tài nguyên sau restore |
| FAILED | Một bước khởi tạo, đóng hoặc khôi phục thất bại |
| CLOSED | Ứng dụng chủ động kết thúc vòng đời resource |

Luồng trạng thái chính:

~~~text
                 startup thành công
        NEW ──> INITIALIZING ─────────> READY
                     │                   │
                     │ startup lỗi       │ beforeCheckpoint
                     ▼                   ▼
                   FAILED            PREPARING
                                         │
                              đóng thành công
                                         ▼
                                      PREPARED
                                         │
                                      restore
                                         ▼
                                     RESTORING
                                         │
                              khôi phục thành công
                                         ▼
                                       READY

        INITIALIZING / READY / RESTORING
                     │
                 lỗi không phục hồi
                     ▼
                   FAILED
~~~

Mỗi callback chỉ nên chấp nhận những trạng thái hợp lệ đối với giai đoạn của nó:

- beforeCheckpoint chỉ bắt đầu khi toàn bộ resource bắt buộc ở trạng thái READY.
- afterRestore chỉ khởi động lại resource đã đi qua giai đoạn PREPARED.
- Nếu startup hoặc restore thất bại, trạng thái phải thể hiện FAILED; không tiếp tục nhận traffic như thể ứng dụng đã sẵn sàng.
- Nếu ứng dụng đã CLOSED, callback không nên tự ý mở lại tài nguyên.

Việc kiểm tra trạng thái giúp phát hiện sai trình tự sớm. Một callback chạy khi resource còn NEW hoặc FAILED phải báo lỗi rõ ràng thay vì âm thầm bỏ qua và để checkpoint chứa trạng thái không an toàn.

## 3. Theo dõi từng tài nguyên đã được mở

Một resource manager thường sở hữu nhiều tài nguyên: executor, socket, connection pool, consumer hoặc scheduler. Các tài nguyên này được mở theo một thứ tự và phải được đóng theo thứ tự ngược lại.

Ví dụ:

~~~text
Mở:
1. Configuration
2. DatabasePool
3. OrderService
4. HttpServer

Đóng trước checkpoint:
4. HttpServer
3. OrderService
2. DatabasePool
1. Configuration (nếu cần giải phóng)
~~~

Không nên chỉ lưu một cờ ready. Hãy lưu danh sách hoặc trạng thái riêng cho từng phần đã được khởi tạo. Khi startup thất bại ở bước 4, manager biết các bước 1, 2, 3 đã được thử mở và cần được dọn dẹp.

Một nguyên tắc quan trọng là **ghi nhận một phần tử trước khi gọi thao tác start**. Nếu start mở được socket rồi mới ném exception, manager vẫn biết phải gọi cleanup cho phần tử đó.

~~~java
for (Part part : parts) {
    attempted.add(part);
    part.start();
}
~~~

Vì phần tử được thêm vào danh sách trước lời gọi start(), phương thức stop() của nó phải chịu được trường hợp start mới hoàn tất một phần. Nếu một thư viện không cung cấp thao tác close an toàn sau khi khởi tạo lỗi, adapter của ứng dụng phải tự giải phóng các tài nguyên cục bộ trước khi ném exception.

## 4. Đăng ký resource và tránh để lộ object chưa hoàn chỉnh

Một lỗi thiết kế phổ biến là đăng ký this trong constructor rồi tiếp tục khởi tạo các field:

~~~java
public MyResource() {
    Core.getGlobalContext().register(this);
    openConnection();
    startWorker();
}
~~~

Nếu openConnection() hoặc startWorker() thất bại, object đã được đưa vào context dù constructor không hoàn thành. JVM/CRaC có thể vẫn giữ reference tới resource đã đăng ký, trong khi object đang ở trạng thái chưa đầy đủ. Callback sau đó phải xử lý một object mà constructor đã thất bại.

Có hai cách tổ chức phù hợp, tùy thời điểm ứng dụng cho phép checkpoint.

### 4.1. Đăng ký một coordinator trước khi bắt đầu khởi tạo

Khi checkpoint có thể được yêu cầu trong lúc ứng dụng startup, hãy tạo một resource coordinator có trạng thái NEW, đăng ký coordinator trước, rồi mới bắt đầu mở các thành phần. Callback của coordinator kiểm tra trạng thái và từ chối checkpoint nếu startup chưa hoàn tất.

~~~java
ManagedCracResource resource =
        new ManagedCracResource(parts);

Core.getGlobalContext().register(resource);

// Chỉ READY sau khi tất cả thành phần bắt buộc đã mở thành công.
resource.start();
~~~

Coordinator tồn tại hợp lệ ngay từ đầu, nhưng chưa tuyên bố các resource con đã sẵn sàng. Nếu callback chạy trước khi start() bắt đầu, nó thấy trạng thái NEW và báo lỗi để checkpoint không tiếp tục với trạng thái ứng dụng chưa hoàn chỉnh. Nếu startup đã giữ lifecycle lock, callback được tuần tự hóa và chỉ tiếp tục sau khi startup kết thúc; khi đó nó thấy READY hoặc FAILED.

Cách này tránh đăng ký một object con chưa hoàn tất constructor. Coordinator sở hữu toàn bộ vòng đời và theo dõi tiến độ khởi tạo của các thành phần.

Nếu startup thất bại, coordinator đã đăng ký vẫn ở trạng thái FAILED. Ứng dụng phải giữ trạng thái NOT_READY và đi theo chính sách dừng/khởi động lại đã định nghĩa; không tạo thêm coordinator thứ hai trên cùng context rồi tiếp tục phục vụ như thể lần khởi tạo trước chưa từng xảy ra.

### 4.2. Đăng ký sau khi khởi tạo hoàn tất

Nếu hệ thống có cơ chế chắc chắn ngăn checkpoint trong giai đoạn startup, có thể khởi tạo đầy đủ resource trước rồi mới đăng ký nó. Tuy nhiên, cần đóng khoảng thời gian giữa lúc tài nguyên đã mở và lúc resource được đăng ký. Nếu checkpoint có thể xảy ra trong khoảng đó, callback sẽ không được gọi cho resource chưa đăng ký.

Vì vậy, không chọn thời điểm đăng ký chỉ dựa trên sự tiện lợi của constructor. Hãy xác định rõ checkpoint có thể được yêu cầu lúc nào và thành phần nào chịu trách nhiệm chặn checkpoint trước khi ứng dụng READY.

## 5. Khởi tạo phải có khả năng rollback

Khi một bước startup thất bại, manager cần đóng các phần đã mở trước đó theo thứ tự ngược. Không nên để mỗi lần khởi động lỗi tạo thêm socket, thread hoặc connection mà không có đường giải phóng.

Một contract hữu ích cho mỗi thành phần là:

- start() tạo tài nguyên và chỉ trả về thành công khi thành phần sẵn sàng.
- Nếu start() ném exception sau khi đã cấp phát một phần, stop() vẫn phải có thể gọi an toàn.
- stop() có tính idempotent: gọi khi chưa start, gọi sau khi start thất bại một phần hoặc gọi lại sau khi đã đóng đều không tạo lỗi phụ không cần thiết.
- Thành phần tự giải phóng tài nguyên tạm thời mà nó tạo ra nhưng chưa bàn giao cho manager.

Mẫu rollback:

~~~java
List<Part> attempted = new ArrayList<>();

try {
    for (Part part : parts) {
        // Ghi nhận trước để cleanup cả trường hợp start thất bại giữa chừng.
        attempted.add(part);
        part.start();
    }
} catch (Exception startupFailure) {
    Exception cleanupFailure = stopInReverseOrder(attempted);

    if (cleanupFailure != null) {
        startupFailure.addSuppressed(cleanupFailure);
    }

    throw startupFailure;
}
~~~

stopInReverseOrder cần tiếp tục đóng các phần còn lại ngay cả khi một thao tác đóng thất bại. Nếu dừng ngay tại exception đầu tiên, những tài nguyên ở sâu hơn trong dependency graph có thể vẫn mở.

~~~java
private static Exception stopInReverseOrder(List<Part> parts) {
    Exception firstFailure = null;

    for (int i = parts.size() - 1; i >= 0; i--) {
        try {
            parts.get(i).stop();
        } catch (Exception failure) {
            if (firstFailure == null) {
                firstFailure = failure;
            } else {
                firstFailure.addSuppressed(failure);
            }
        }
    }

    return firstFailure;
}
~~~

Exception khởi tạo ban đầu vẫn là lỗi chính. Các lỗi cleanup được gắn bằng addSuppressed để log giữ được cả nguyên nhân gốc lẫn các lỗi giải phóng tài nguyên.

## 6. Ví dụ coordinator quản lý trạng thái và callback

Ví dụ sau dùng một interface Part để đại diện cho database pool, service hoặc HTTP server. Các thành phần được truyền vào theo thứ tự dependency: thành phần nền trước, thành phần phụ thuộc sau.

~~~java
package com.example.crac;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

import java.util.ArrayList;
import java.util.List;

public final class ManagedCracResource implements Resource {

    public interface Part {
        void start() throws Exception;
        void stop() throws Exception;
    }

    private enum State {
        NEW,
        INITIALIZING,
        READY,
        PREPARING,
        PREPARED,
        RESTORING,
        FAILED,
        CLOSED
    }

    private final Object lifecycleLock = new Object();
    private final List<Part> parts;

    // Gồm cả phần tử mà start() đang thực hiện hoặc đã thực hiện.
    private final List<Part> attempted = new ArrayList<>();

    private State state = State.NEW;

    public ManagedCracResource(List<Part> parts) {
        this.parts = List.copyOf(parts);
    }

    public static ManagedCracResource register(List<Part> parts) {
        ManagedCracResource resource =
                new ManagedCracResource(parts);

        Core.getGlobalContext().register(resource);
        return resource;
    }

    public void start() throws Exception {
        synchronized (lifecycleLock) {
            requireState(State.NEW);
            state = State.INITIALIZING;

            try {
                startInOrder();
                state = State.READY;
            } catch (Exception startupFailure) {
                Exception cleanupFailure =
                        stopInReverseOrder(attempted);
                attempted.clear();
                state = State.FAILED;

                if (cleanupFailure != null) {
                    startupFailure.addSuppressed(cleanupFailure);
                }

                throw startupFailure;
            }
        }
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {

        synchronized (lifecycleLock) {
            requireState(State.READY);
            state = State.PREPARING;

            Exception failure =
                    stopInReverseOrder(attempted);
            attempted.clear();

            if (failure != null) {
                state = State.FAILED;
                throw failure;
            }

            state = State.PREPARED;
        }
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {

        synchronized (lifecycleLock) {
            requireState(State.PREPARED);
            state = State.RESTORING;

            try {
                startInOrder();
                state = State.READY;
            } catch (Exception restoreFailure) {
                Exception cleanupFailure =
                        stopInReverseOrder(attempted);
                attempted.clear();
                state = State.FAILED;

                if (cleanupFailure != null) {
                    restoreFailure.addSuppressed(cleanupFailure);
                }

                throw restoreFailure;
            }
        }
    }

    private void startInOrder() throws Exception {
        for (Part part : parts) {
            // Ghi nhận trước khi start để cleanup được phần khởi tạo dở dang.
            attempted.add(part);
            part.start();
        }
    }

    private static Exception stopInReverseOrder(List<Part> parts) {
        Exception firstFailure = null;

        for (int i = parts.size() - 1; i >= 0; i--) {
            try {
                parts.get(i).stop();
            } catch (Exception failure) {
                if (firstFailure == null) {
                    firstFailure = failure;
                } else {
                    firstFailure.addSuppressed(failure);
                }
            }
        }

        return firstFailure;
    }

    private void requireState(State expected) {
        if (state != expected) {
            throw new IllegalStateException(
                    "Expected state " + expected + " but was " + state);
        }
    }
}
~~~

Trình tự sử dụng:

~~~java
List<ManagedCracResource.Part> parts = List.of(
        databasePoolPart,
        orderServicePart,
        httpServerPart
);

ManagedCracResource resource =
        ManagedCracResource.register(parts);

resource.start();

// Chỉ công bố READY cho ứng dụng sau khi start() hoàn tất.
applicationReadiness.markReady();
~~~

Ví dụ minh họa những điểm quan trọng:

1. Coordinator được đăng ký trước khi mở các resource con.
2. Callback không giả định các thành phần luôn ở trạng thái READY.
3. Danh sách attempted ghi nhận phần tử trước khi gọi start().
4. Startup thất bại sẽ rollback theo thứ tự ngược.
5. beforeCheckpoint chỉ chấp nhận trạng thái READY.
6. afterRestore chỉ khôi phục khi trạng thái checkpoint là PREPARED.
7. Restore thất bại cũng rollback các thành phần đã thử mở và giữ trạng thái FAILED.
8. Exception cleanup được gắn vào lỗi gốc thay vì bị bỏ qua.

Đây là khung quản lý vòng đời. Trong ứng dụng thực tế, cần bổ sung chính sách timeout, shutdown chủ động, readiness/health check, xử lý fatal error và đồng bộ với lifecycle của framework.

Ví dụ gọi applicationReadiness.markReady() minh họa cho startup ban đầu. Trong ứng dụng thật, readiness phải được cập nhật sau cả hai đường thành công: sau start() ban đầu và sau khi afterRestore() hoàn tất, coordinator chuyển về READY. Trước khi bắt đầu dừng resource để checkpoint, ứng dụng cũng nên chuyển readiness sang NOT_READY để load balancer hoặc lớp điều phối không gửi thêm traffic.

## 7. Callback trước checkpoint phải xử lý trạng thái chưa sẵn sàng

beforeCheckpoint là cơ hội cuối cùng để ứng dụng dừng công việc và đưa tài nguyên về trạng thái an toàn trước khi snapshot. Callback không nên chỉ gọi close() trên mọi field mà không kiểm tra trạng thái.

### 7.1. Nếu startup chưa hoàn tất

Có hai chính sách phổ biến:

- **Từ chối checkpoint:** nếu startup đang diễn ra, ném exception có ý nghĩa để báo rằng ứng dụng chưa đạt trạng thái có thể checkpoint.
- **Chờ startup có giới hạn:** chỉ dùng khi startup có thể hoàn tất nhanh, có deadline rõ ràng và callback không thể bị kẹt vô hạn.

Nếu dùng cơ chế chờ, phải có timeout. Không để checkpoint thread chờ vô hạn trong khi startup thread bị treo vì kết nối mạng hoặc dependency không sẵn sàng.

Trong coordinator ví dụ, start() và callback dùng cùng một lock. Callback chỉ đi vào sau khi startup nhả lock; sau đó kiểm tra trạng thái. Nếu startup thành công, callback thấy READY; nếu startup thất bại, callback thấy FAILED và từ chối checkpoint.

Đây là cách đơn giản để tuần tự hóa chuyển trạng thái. Với startup có I/O dài, hệ thống production nên dùng một lifecycle gate có timeout hoặc một readiness barrier riêng, thay vì giữ monitor trong thời gian dài mà không có giới hạn.

### 7.2. Nếu chỉ một phần tài nguyên được mở

Nếu ứng dụng cho phép callback nhìn thấy trạng thái một phần, nó phải dựa vào danh sách các resource đã được thử mở. Đóng theo thứ tự ngược và để mỗi stop() xử lý trường hợp chưa mở hoặc mở một phần.

Không dùng điều kiện kiểu:

~~~java
if (initialized) {
    closeEverything();
}
~~~

Cờ này thường chỉ được đặt sau khi toàn bộ startup thành công. Nếu startup thất bại giữa chừng, nó vẫn là false dù socket, thread hoặc connection đã được tạo. Kết quả là cleanup bị bỏ qua.

## 8. Callback sau restore phải khôi phục có kiểm soát

Sau restore, trạng thái trong checkpoint cần cho biết ứng dụng đã hoàn thành giai đoạn chuẩn bị trước checkpoint. Coordinator ví dụ lưu trạng thái PREPARED trước khi snapshot. afterRestore chỉ bắt đầu từ trạng thái đó.

### 8.1. Khôi phục theo thứ tự dependency

Nếu lúc startup đã mở:

~~~text
Configuration → DatabasePool → OrderService → HttpServer
~~~

thì sau restore cũng khôi phục theo đúng thứ tự này. Database pool phải có kết nối hợp lệ trước khi service sử dụng nó; HTTP server chỉ mở listener sau khi service sẵn sàng.

### 8.2. Nếu restore thất bại giữa chừng

Giả sử database pool và service khôi phục thành công nhưng HTTP server không bind được port. Không nên đánh dấu ứng dụng READY. Có thể chọn một trong hai chính sách tùy kiến trúc:

- **Fail restore:** dừng các thành phần đã khôi phục theo thứ tự ngược, ghi lỗi và để tiến trình không nhận traffic.
- **Degraded mode có chủ đích:** chỉ phù hợp khi thành phần thất bại là tùy chọn, mọi request liên quan được chặn rõ ràng và health/readiness thể hiện đúng trạng thái.

Không tự động bỏ qua lỗi của resource bắt buộc. Nếu HTTP server là thành phần duy nhất nhận request, không thể coi ứng dụng đã sẵn sàng khi listener không mở được.

### 8.3. Kiểm tra lại tài nguyên bên ngoài

Checkpoint giữ trạng thái tiến trình, nhưng hệ thống bên ngoài vẫn tiếp tục hoạt động trong thời gian tiến trình tạm dừng. Sau restore:

- Database connection có thể đã bị server đóng vì timeout.
- Token hoặc credential có thể hết hạn.
- Lease phân tán có thể đã được cấp cho instance khác.
- Message consumer có thể cần xác thực lại vị trí xử lý.
- DNS, endpoint hoặc network route có thể đã thay đổi.

Vì vậy, afterRestore nên tạo lại hoặc xác thực lại các resource có vòng đời bên ngoài. Không coi một Java object còn nằm trong heap là bằng chứng rằng socket hoặc session mà object đại diện vẫn dùng được.

## 9. Tài nguyên tùy chọn và tài nguyên bắt buộc

Không phải mọi resource đều cần có trong mọi cấu hình. Ví dụ, ứng dụng có thể bật message consumer ở production nhưng tắt trong môi trường phát triển.

Hãy tạo danh sách resource theo cấu hình đã được xác định trước khi startup:

~~~java
List<ManagedCracResource.Part> parts =
        new ArrayList<>();

parts.add(configurationPart);
parts.add(databasePoolPart);

if (messagingEnabled) {
    parts.add(messageConsumerPart);
}

parts.add(orderServicePart);
parts.add(httpServerPart);
~~~

Không thêm null vào danh sách và không dùng một phần tử giả chỉ để giữ vị trí. Thứ tự của danh sách phải phản ánh dependency của cấu hình đang chạy.

Nếu resource tùy chọn không khởi tạo được, quyết định ứng dụng có thể chạy ở degraded mode hay phải fail startup cần được xác định rõ. Nếu cho phép degraded mode, resource đó phải được đánh dấu là không hoạt động và các tính năng phụ thuộc vào nó phải bị vô hiệu hóa. Callback không nên tự suy diễn rằng mọi exception đều có thể bỏ qua.

Với resource bắt buộc, lỗi khởi tạo hoặc restore phải làm ứng dụng không READY. Điều này ngăn checkpoint hoặc traffic đi qua một trạng thái không đầy đủ.

## 10. Đồng bộ callback với thread và request đang chạy

Quản lý trạng thái resource không chỉ là quản lý field. Một HTTP server có thể còn request đang xử lý; một executor có thể còn task; một consumer có thể đang xử lý message.

Trước checkpoint, ứng dụng nên:

1. Ngừng nhận công việc mới ở các thành phần biên.
2. Đợi công việc đang chạy hoàn tất trong một khoảng thời gian giới hạn.
3. Hủy hoặc lưu trạng thái công việc còn lại theo chính sách nghiệp vụ.
4. Đóng dependency sau khi không còn consumer sử dụng.
5. Chỉ báo callback hoàn tất khi trạng thái đã an toàn.

Không đóng database pool trong khi request đang chạy vẫn giữ connection. Không đóng executor trước khi đã quyết định các task đang thực thi sẽ hoàn tất hay bị hủy. Không tạo checkpoint khi một thread có thể đang sửa dữ liệu nghiệp vụ dở dang mà không có cơ chế phục hồi.

Sử dụng lock để bảo vệ state transition, nhưng tránh giữ lock trong lúc chờ một thread khác mà thread đó lại cần cùng lock để kết thúc. Đây là nguyên nhân phổ biến gây deadlock khi shutdown. Với các thao tác chờ, dùng deadline rõ ràng và ghi log tên resource đang chờ.

## 11. Phân biệt lỗi khởi tạo, lỗi cleanup và lỗi restore

Ba lỗi này xảy ra ở các giai đoạn khác nhau và cần được ghi nhận riêng:

| Giai đoạn | Ví dụ | Hành động |
|---|---|---|
| Startup | Database pool mở được nhưng service không tạo được | Rollback các phần đã thử mở, không READY |
| beforeCheckpoint | HTTP server dừng được nhưng database pool không đóng được | Tiếp tục thử cleanup phần còn lại, báo callback thất bại |
| afterRestore | Database pool mở được nhưng HTTP server bind port thất bại | Cleanup phần đã khôi phục, không nhận traffic |

Khi có nhiều lỗi, giữ exception gốc và đính kèm các lỗi cleanup bằng suppressed exception. Log nên có tên resource, giai đoạn, trạng thái trước/sau và thời gian thao tác.

Không bắt exception rồi chỉ ghi một dòng log chung như “checkpoint failed”. Thông tin đó không cho biết resource nào đã dừng, resource nào còn mở hoặc ứng dụng đang ở trạng thái nào.

## 12. Những lỗi thiết kế thường gặp

### Đăng ký this quá sớm trong constructor

Nếu constructor thất bại sau khi đã đăng ký resource, context có thể giữ một object chưa hoàn chỉnh. Dùng coordinator đã có trạng thái rõ ràng hoặc factory kiểm soát thời điểm đăng ký.

### Chỉ dùng một boolean initialized

Một boolean không thể mô tả trường hợp đã mở một phần tài nguyên. Dùng state machine và theo dõi các thành phần đã thử mở.

### Chỉ cleanup khi startup hoàn tất

Nếu chỉ đặt cờ initialized sau bước cuối cùng, startup thất bại giữa chừng sẽ bỏ qua cleanup. Ghi nhận từng phần trước khi gọi start và cho phép stop xử lý partial state.

### Dừng ngay khi một close thất bại

Nếu một resource không đóng được, các resource khác vẫn cần được thử đóng. Gom lỗi thay vì dừng vòng cleanup tại exception đầu tiên.

### Khôi phục tất cả rồi mới kiểm tra lỗi

Nếu thành phần nền không sẵn sàng, tiếp tục mở listener có thể làm request đi vào một service chưa hoạt động. Khởi tạo theo dependency và chỉ đánh dấu READY sau health check cần thiết.

### Nuốt exception trong callback

Nếu callback thất bại nhưng vẫn trả về bình thường, runtime có thể tiếp tục checkpoint hoặc restore với trạng thái không an toàn. Báo lỗi rõ ràng để quá trình thất bại theo cách có thể quan sát và điều tra.

### Không giới hạn thời gian chờ

Một request, connection hoặc thread bị treo có thể khiến callback không kết thúc. Đặt timeout, ghi nhận phần chưa dừng và xử lý theo chính sách fail-fast hoặc phục hồi của ứng dụng.

## 13. Quy trình kiểm chứng thiết kế

Có thể kiểm chứng callback với các tình huống cố ý tạo lỗi, thay vì chỉ chạy đường thành công.

| Tình huống thử | Cách tạo lỗi | Kết quả mong đợi |
|---|---|---|
| Lỗi ở resource đầu tiên | Cho start() của resource đầu tiên ném exception | Không READY; cleanup được gọi cho phần đã thử mở |
| Lỗi ở resource giữa | Resource thứ hai mở một phần rồi ném exception | Resource thứ hai và resource trước đó được stop theo thứ tự ngược |
| Checkpoint trước READY | Yêu cầu checkpoint trong khi startup chưa hoàn tất | Callback từ chối hoặc chờ có giới hạn; không tạo checkpoint ở trạng thái dở dang |
| Lỗi khi đóng | Cho một stop() ném exception | Vẫn thử stop các resource còn lại; callback báo lỗi |
| Lỗi khi restore | Cho một start() sau restore thất bại | Cleanup các resource đã thử khôi phục; không READY |
| Resource tùy chọn vắng mặt | Tắt một tính năng bằng cấu hình | Không có null entry; thứ tự các resource còn lại vẫn đúng |
| Request đang chạy | Giữ request trong lúc chuẩn bị checkpoint | Callback drain hoặc timeout theo chính sách đã thiết kế |

Khi kiểm tra, lưu log theo trình tự:

~~~text
resource=<name> phase=<phase> stateBefore=<state>
resource=<name> action=<start|stop> result=<success|failure>
resource=<name> stateAfter=<state>
application readiness=<READY|NOT_READY>
~~~

Thử lỗi cần được thực hiện trong môi trường kiểm thử riêng. Không cố tình làm hỏng database hoặc dừng production resource để xác nhận callback.

## 14. Checklist thiết kế trước khi đưa vào ứng dụng

Trước khi tích hợp callback CRaC vào một ứng dụng có nhiều resource, hãy trả lời được các câu hỏi sau:

- Resource nào bắt buộc, resource nào tùy chọn?
- Ai sở hữu mỗi socket, thread, connection pool, consumer và scheduler?
- Resource nào phụ thuộc resource nào?
- Trạng thái nào chứng minh startup đã hoàn tất?
- Nếu start thất bại sau khi mở một phần, ai chịu trách nhiệm cleanup?
- stop() có an toàn khi resource chưa mở hoặc mới mở một phần không?
- Callback có thể chạy trong lúc startup hoặc request đang xử lý không?
- Khi cleanup một phần thất bại, các resource còn lại có tiếp tục được đóng không?
- Sau restore, tài nguyên bên ngoài được tạo lại hoặc xác thực như thế nào?
- Ứng dụng có chỉ đánh dấu READY sau khi mọi resource bắt buộc hoạt động không?
- Có timeout và log đủ chi tiết để xác định resource gây lỗi không?

Một callback đáng tin cậy phải mô tả đúng trạng thái thật của tiến trình tại từng thời điểm. Hãy đăng ký một lifecycle coordinator có thể tồn tại độc lập với các resource con, quản lý trạng thái tường minh, ghi nhận từng lần thử khởi tạo và thực hiện cleanup theo thứ tự ngược. Khi restore, tạo lại các dependency theo thứ tự ban đầu và chỉ công bố READY sau khi toàn bộ thành phần bắt buộc đã vượt qua kiểm tra.

Với cách thiết kế này, startup thất bại giữa chừng, checkpoint đến quá sớm hoặc restore chỉ thành công một phần đều trở thành các trạng thái có thể phát hiện và xử lý có kiểm soát.

