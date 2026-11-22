# Khôi phục trạng thái thành phần khi checkpoint bị hủy

Trong CRaC (Coordinated Restore at Checkpoint), mỗi thành phần có thể chuẩn bị tài nguyên trước checkpoint và khởi tạo lại tài nguyên sau restore thông qua interface Resource. Tuy nhiên, không phải yêu cầu checkpoint nào cũng tạo được ảnh thành công. Một callback có thể ném exception, runtime có thể không tạo được ảnh hoặc engine checkpoint có thể gặp lỗi ở bước native.

Khi checkpoint bị hủy, tiến trình Java ban đầu tiếp tục chạy. Những thay đổi mà các thành phần đã thực hiện trong giai đoạn chuẩn bị vẫn có thể còn hiệu lực. Ứng dụng cần khôi phục chúng để tiếp tục phục vụ bình thường.

Điểm cần phân biệt là **checkpoint bị hủy** và **restore thất bại**. Hai trường hợp xảy ra ở hai giai đoạn khác nhau và cần cách xử lý khác nhau.

## 1. Vòng đời resource và điểm có thể xảy ra lỗi

Một đối tượng triển khai Resource đăng ký với Context để nhận thông báo từ CRaC. API có hai callback:

- beforeCheckpoint(): chuẩn bị thành phần trước khi runtime tạo ảnh.
- afterRestore(): khởi tạo lại thành phần sau khi một tiến trình được khôi phục từ ảnh.

Một chu kỳ thành công có dạng:

~~~text
Ứng dụng đang hoạt động
        |
        | Yêu cầu checkpoint
        v
beforeCheckpoint() của các Resource
        |
        v
Runtime tạo checkpoint image
        |
        v
Khởi chạy tiến trình từ image
        |
        v
afterRestore() của các Resource
        |
        v
Ứng dụng tiếp tục hoạt động
~~~

Nếu một callback beforeCheckpoint() thất bại hoặc thao tác checkpoint ở tầng runtime/native thất bại, chu kỳ rẽ sang nhánh hủy:

~~~text
Ứng dụng đang hoạt động
        |
        | Yêu cầu checkpoint
        v
beforeCheckpoint() của Resource
        |
        v
Một callback hoặc engine gặp lỗi
        |
        v
Checkpoint bị hủy
        |
        v
Tiến trình Java ban đầu tiếp tục chạy
        |
        v
Ứng dụng khôi phục các thành phần đã chuẩn bị
        |
        v
Ứng dụng trở lại trạng thái sẵn sàng
~~~

Không có ảnh hợp lệ để restore trong nhánh này. Vì vậy, afterRestore() không phải callback rollback cho checkpoint bị hủy. afterRestore() chỉ được gọi khi runtime thực sự khôi phục một tiến trình từ checkpoint image.

### Phân biệt ba kết quả

| Kết quả | Điều gì đã xảy ra? | Nơi ứng dụng tiếp tục |
|---|---|---|
| Checkpoint thành công và restore thành công | Ảnh được tạo và tiến trình được khôi phục | Tiến trình mới, sau giai đoạn restore |
| Checkpoint thất bại hoặc bị hủy | Không tạo được checkpoint hợp lệ | Tiến trình Java ban đầu |
| Restore notification thất bại | Tiến trình đã được khôi phục nhưng một callback afterRestore() gặp lỗi | Tiến trình đã restore, nhưng có thể chưa sẵn sàng phục vụ |

Với API Core.checkpointRestore(), checkpoint thất bại được báo bằng CheckpointException và việc thực thi tiếp tục trong Java instance ban đầu. Lỗi trong giai đoạn restore được báo bằng RestoreException và xảy ra trong Java instance mới. Nếu runtime không hỗ trợ checkpoint/restore, API có thể ném UnsupportedOperationException.

## 2. Vì sao phải rollback trạng thái đã chuẩn bị?

beforeCheckpoint() thường làm thay đổi trạng thái đang hoạt động để đáp ứng điều kiện tạo ảnh. Ví dụ:

- Tạm dừng nhận request mới.
- Dừng worker hoặc thread pool.
- Flush buffer rồi đóng file.
- Đóng socket và kết nối database.
- Tạm dừng lịch chạy định kỳ.
- Đưa cache hoặc component sang chế độ chỉ đọc.

Nếu checkpoint thành công, các thành phần được khởi tạo lại trong afterRestore(). Nhưng nếu checkpoint bị hủy, tiến trình cũ vẫn đang tồn tại. Những thành phần đã đóng kết nối hoặc tạm dừng worker cần được mở lại.

Ví dụ, một server đã đóng listener trong beforeCheckpoint(). Sau đó một Resource khác phát hiện file descriptor chưa được đóng và làm checkpoint thất bại. Nếu server không mở listener trở lại, JVM vẫn chạy nhưng ứng dụng không nhận được request mới.

Đây là lỗi trạng thái sau checkpoint bị hủy: tiến trình còn sống nhưng một phần ứng dụng vẫn ở chế độ chuẩn bị.

### Không dùng afterRestore() làm rollback mặc định

afterRestore() không được gọi chỉ vì một callback beforeCheckpoint() thất bại. Nếu đặt logic phục hồi duy nhất trong afterRestore(), ứng dụng có thể bị kẹt ở trạng thái đã pause khi checkpoint bị hủy.

Cần tách rõ hai thao tác:

- **Rollback sau hủy checkpoint:** khôi phục trạng thái của tiến trình ban đầu sau khi Core.checkpointRestore() ném CheckpointException.
- **Khởi tạo sau restore:** tạo lại tài nguyên trong afterRestore() của tiến trình được khôi phục.

Hai thao tác có thể dùng chung một số hàm mở lại kết nối hoặc tiếp tục worker, nhưng phải được gọi theo đúng nhánh vòng đời.

## 3. Mô hình trạng thái của một thành phần

Một resource nên biểu diễn rõ trạng thái của nó. Ví dụ:

| Trạng thái | Ý nghĩa |
|---|---|
| ACTIVE | Thành phần đang phục vụ bình thường |
| PREPARING | Đang dừng công việc hoặc giải phóng tài nguyên |
| PREPARED | Đã chuẩn bị xong cho checkpoint |
| ROLLING_BACK | Đang khôi phục sau khi checkpoint bị hủy |
| RESTORING | Đang tạo lại tài nguyên sau restore |
| READY | Tài nguyên đã sẵn sàng để phục vụ |

Luồng trạng thái khi checkpoint thành công:

~~~text
ACTIVE -> PREPARING -> PREPARED
                           |
                           | Restore thành công
                           v
                       RESTORING
                           |
                           v
                         READY
~~~

Luồng trạng thái khi checkpoint bị hủy:

~~~text
ACTIVE -> PREPARING -> PREPARED
                           |
                           | CheckpointException
                           v
                      ROLLING_BACK
                           |
                           v
                         READY
~~~

Nếu lỗi xảy ra ngay giữa lúc chuẩn bị, thành phần phải tự hoàn tác phần việc mà chính nó đã thực hiện trước khi ném exception. Nếu thành phần đã chuẩn bị thành công nhưng một resource khác hoặc engine checkpoint thất bại sau đó, bộ điều phối của ứng dụng cần yêu cầu các thành phần đã chuẩn bị rollback.

### Các nguyên tắc thiết kế

**Ghi nhận từng thay đổi:** nếu đã pause worker, đóng connection hoặc flush buffer, lưu lại trạng thái tương ứng để biết cần hoàn tác bước nào.

**Rollback có thể gọi nhiều lần:** một thành phần có thể được yêu cầu rollback trong lúc xử lý lỗi cục bộ và sau đó được bộ điều phối gọi lại. Hàm rollback nên idempotent, tức gọi lại không làm hỏng trạng thái.

**Hoàn tác theo thứ tự ngược:** nếu A được chuẩn bị trước B và B phụ thuộc vào A, quá trình rollback thường cần phục hồi B trước rồi mới phục hồi A. Thứ tự này đảo ngược thứ tự chuẩn bị.

**Không đánh dấu READY quá sớm:** chỉ cho phép nhận request sau khi listener, worker, pool kết nối và các dependency bắt buộc đã hoạt động.

**Giữ lỗi gốc:** nếu rollback cũng thất bại, lưu lỗi rollback dưới dạng suppressed exception hoặc log riêng, không che mất nguyên nhân khiến checkpoint bị hủy.

## 4. Tự rollback nếu beforeCheckpoint() thất bại giữa chừng

Một callback có thể thực hiện nhiều thao tác. Nếu thao tác thứ ba thất bại sau khi hai thao tác đầu đã thành công, chính callback đó phải hoàn tác phần việc đã làm.

Ví dụ một resource quản lý cache có writer và file handle:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class CacheResource implements Resource {
    private final LocalCache cache;

    private boolean writersPaused;
    private boolean fileClosed;
    private boolean prepared;

    public CacheResource(LocalCache cache) {
        this.cache = cache;
        Core.getGlobalContext().register(this);
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {

        if (prepared) {
            return;
        }

        try {
            cache.pauseWriters();
            writersPaused = true;

            cache.flush();
            cache.closeFile();
            fileClosed = true;

            prepared = true;
        } catch (Exception failure) {
            rollbackPartialPreparation(failure);
            throw failure;
        }
    }

    private void rollbackPartialPreparation(Exception failure) {
        if (fileClosed) {
            try {
                cache.reopenFile();
                fileClosed = false;
            } catch (Exception rollbackFailure) {
                failure.addSuppressed(rollbackFailure);
            }
        }

        if (writersPaused) {
            try {
                cache.resumeWriters();
                writersPaused = false;
            } catch (Exception rollbackFailure) {
                failure.addSuppressed(rollbackFailure);
            }
        }

        prepared = false;
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        cache.reopenFile();
        cache.resumeWriters();

        fileClosed = false;
        writersPaused = false;
        prepared = false;
    }

    public synchronized void rollbackAfterAbortedCheckpoint()
            throws Exception {
        if (!prepared && !fileClosed && !writersPaused) {
            return;
        }

        if (fileClosed) {
            cache.reopenFile();
            fileClosed = false;
        }

        if (writersPaused) {
            cache.resumeWriters();
            writersPaused = false;
        }

        prepared = false;
    }
}
~~~

LocalCache chỉ là lớp minh họa. Trong ứng dụng thực tế, cần thay bằng cache và file resource thực tế.

Ví dụ thể hiện ba điểm:

1. Callback ghi nhận thay đổi sau mỗi thao tác thành công.
2. Nếu callback tự thất bại, nó rollback phần việc đã thực hiện rồi ném lại lỗi gốc.
3. Nếu callback đã hoàn tất nhưng checkpoint bị hủy về sau, bộ điều phối gọi rollbackAfterAbortedCheckpoint().

Trong triển khai thực tế, các hàm reopenFile() và resumeWriters() nên có khả năng xử lý trường hợp tài nguyên đã mở hoặc worker đã chạy. Nếu một bước rollback thất bại, cần giữ trạng thái chưa phục hồi để có thể thử lại hoặc chuyển ứng dụng sang trạng thái không sẵn sàng.

## 5. Rollback khi một Resource khác làm checkpoint thất bại

Một tình huống quan trọng là resource A đã chạy beforeCheckpoint() thành công, sau đó resource B ném exception. Resource A không tự biết rằng một callback khác đã làm checkpoint bị hủy.

Resource chỉ có hai callback chuẩn là beforeCheckpoint() và afterRestore(). API không cung cấp một callback afterCheckpointAborted() riêng để báo cho mọi resource rằng checkpoint đã bị hủy.

Khi ứng dụng gọi checkpoint thông qua Core.checkpointRestore(), bộ điều phối có thể bắt CheckpointException rồi gọi thao tác rollback tường minh trên các thành phần đã tham gia chuẩn bị.

### Định nghĩa participant

~~~java
public interface CheckpointParticipant {
    void rollbackAfterAbortedCheckpoint() throws Exception;
}
~~~

Mỗi thành phần triển khai interface này cùng với Resource. Phương thức rollback cần tự kiểm tra trạng thái nội bộ và chỉ khôi phục những thay đổi thực sự đã được thực hiện.

### Bộ điều phối checkpoint

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import org.crac.CheckpointException;
import org.crac.Core;
import org.crac.RestoreException;

public final class CheckpointCoordinator {
    private final List<CheckpointParticipant> participants;

    public CheckpointCoordinator(
            List<CheckpointParticipant> participants) {
        this.participants = new ArrayList<>(participants);
    }

    public void checkpoint() throws Exception {
        try {
            Core.checkpointRestore();

            // Chỉ tiếp tục tại đây sau khi restore thành công.
            resumeNormalTraffic();

        } catch (CheckpointException checkpointFailure) {
            rollbackPreparedComponents(checkpointFailure);
            throw checkpointFailure;

        } catch (RestoreException restoreFailure) {
            // Đang ở instance đã restore.
            // Đây là lỗi khởi tạo sau restore, không phải checkpoint bị hủy.
            markApplicationNotReady(restoreFailure);
            throw restoreFailure;
        }
    }

    private void rollbackPreparedComponents(
            CheckpointException originalFailure) {

        List<CheckpointParticipant> reverse =
                new ArrayList<>(participants);

        Collections.reverse(reverse);

        for (CheckpointParticipant participant : reverse) {
            try {
                participant.rollbackAfterAbortedCheckpoint();
            } catch (Exception rollbackFailure) {
                originalFailure.addSuppressed(rollbackFailure);
            }
        }
    }

    private void resumeNormalTraffic() {
        // Mở lại khả năng nhận request sau khi restore thành công.
    }

    private void markApplicationNotReady(Exception failure) {
        // Ghi nhận lỗi restore và giữ ứng dụng ở trạng thái chưa sẵn sàng.
    }
}
~~~

Danh sách participants cần chứa các thành phần có thể thay đổi trạng thái trong beforeCheckpoint(). Các hàm rollback phải an toàn khi được gọi với thành phần chưa kịp chuẩn bị hoặc đã tự rollback.

Trong ứng dụng thực tế, cần phối hợp trạng thái nhận request với bộ điều phối. Chẳng hạn, trước khi gọi Core.checkpointRestore(), hệ thống chuyển sang chế độ drain; khi nhận CheckpointException, bộ điều phối rollback resource và chỉ mở lại lưu lượng khi mọi thành phần bắt buộc đã phục hồi.

### Vì sao rollback theo thứ tự ngược?

Giả sử các thành phần được chuẩn bị theo thứ tự:

~~~text
1. DatabasePool.pauseAndClose()
2. Repository.flushAndPause()
3. RequestHandler.stopAccepting()
~~~

Nếu checkpoint bị hủy, có thể cần khôi phục theo thứ tự ngược:

~~~text
1. RequestHandler.startAccepting()
2. Repository.resume()
3. DatabasePool.reopenAndResume()
~~~

Tuy nhiên, ví dụ trên chỉ đúng nếu RequestHandler và Repository không bắt đầu xử lý trước khi database sẵn sàng. Trong nhiều hệ thống, thứ tự phục hồi thực tế nên là database, repository rồi request handler. Quy tắc cần tuân theo là khôi phục dependency trước consumer, không áp dụng máy móc một thứ tự cố định.

Hãy mô tả rõ quan hệ phụ thuộc giữa các thành phần và chọn thứ tự rollback để thành phần được mở lại chỉ sử dụng những dependency đã sẵn sàng.

## 6. Xử lý lỗi checkpoint và lỗi restore riêng biệt

CheckpointException và RestoreException biểu thị hai tình huống khác nhau.

### CheckpointException

CheckpointException được ném khi checkpoint không thành công, chẳng hạn lỗi trong callback checkpoint notification hoặc lỗi ở quá trình tạo ảnh. Việc thực thi tiếp tục trong Java instance ban đầu.

Ứng dụng cần:

1. Ghi log nguyên nhân checkpoint thất bại.
2. Kiểm tra những thành phần đã chuyển sang PREPARED.
3. Gọi rollback trên các thành phần đó.
4. Thu thập mọi lỗi phát sinh trong rollback.
5. Chỉ mở lại lưu lượng khi trạng thái ứng dụng đã được phục hồi.

CheckpointException có thể chứa các suppressed exception. Chúng thường cung cấp chi tiết về callback hoặc resource gây lỗi. Không chỉ ghi message cấp cao nhất rồi bỏ qua phần suppressed.

Ví dụ:

~~~java
try {
    Core.checkpointRestore();
} catch (CheckpointException e) {
    logger.error("Checkpoint failed", e);

    for (Throwable suppressed : e.getSuppressed()) {
        logger.error("Checkpoint preparation detail", suppressed);
    }

    rollbackComponents();
    throw e;
}
~~~

Nếu một thành phần không thể rollback, ứng dụng không nên giả vờ rằng nó đã sẵn sàng. Có thể giữ chế độ maintenance, thử phục hồi lại theo chính sách retry hoặc kết thúc tiến trình để hệ thống giám sát khởi động lại.

### RestoreException

RestoreException xảy ra khi quá trình restore notification gặp lỗi. Ở thời điểm này, tiến trình đã được khôi phục thành instance mới. Đây không phải trường hợp checkpoint bị hủy trong instance ban đầu.

Không chạy rollbackAfterAbortedCheckpoint() như thể checkpoint chưa từng xảy ra. Thay vào đó:

- Xác định resource nào không khởi tạo được.
- Giữ ứng dụng ở trạng thái chưa sẵn sàng.
- Thử tạo lại tài nguyên nếu thao tác có thể retry an toàn.
- Không nhận request phụ thuộc vào resource đang lỗi.
- Ghi log nguyên nhân và chuyển lỗi cho cơ chế giám sát hoặc chính sách dừng của ứng dụng.

Nếu một resource cần database nhưng afterRestore() không thể kết nối database, việc mở listener trước khi pool kết nối sẵn sàng có thể khiến request lỗi hàng loạt.

### UnsupportedOperationException

Nếu API CRaC được gọi trên runtime không hỗ trợ checkpoint/restore, có thể nhận UnsupportedOperationException. Trường hợp này khác với checkpoint bị hủy sau khi quá trình chuẩn bị đã bắt đầu. Ứng dụng nên kiểm tra cấu hình runtime và không để thành phần chuyển sang trạng thái PREPARED trước khi biết yêu cầu có thể được thực hiện.

## 7. Khi yêu cầu checkpoint đến từ jcmd

Có thể yêu cầu checkpoint từ bên ngoài bằng:

~~~bash
jcmd <pid> JDK.checkpoint
~~~

Khi dùng jcmd, yêu cầu được gửi tới JVM đang chạy. Mã Java của ứng dụng không trực tiếp gọi Core.checkpointRestore() tại vị trí có thể bao quanh bằng try/catch. Vì vậy, ứng dụng không thể dựa vào một khối catch CheckpointException trong luồng nghiệp vụ để tự động rollback cho lệnh jcmd bên ngoài.

Đây là điểm cần cân nhắc khi thiết kế quy trình vận hành.

Nếu việc rollback sau checkpoint bị hủy là bắt buộc, nên để ứng dụng điều phối yêu cầu thông qua một endpoint hoặc cơ chế quản trị nội bộ, rồi gọi Core.checkpointRestore() trong luồng điều khiển của ứng dụng. Bộ điều phối có thể bắt CheckpointException và khôi phục các participant.

Nếu tổ chức vẫn cần dùng jcmd trực tiếp, các callback cần được thiết kế để việc chuẩn bị có thể phục hồi an toàn và có một quy trình quản trị riêng để đưa ứng dụng về trạng thái phục vụ sau khi checkpoint thất bại. Không nên giả định rằng CRaC sẽ gọi afterRestore() khi checkpoint bị hủy.

Một số bản triển khai jcmd có thể trả thông báo command đã được thực thi ngay cả khi lỗi checkpoint được ghi trong console của ứng dụng. Vì vậy, không chỉ dựa vào output của jcmd để xác định checkpoint thành công. Cần quan sát log JVM và trạng thái ứng dụng theo hướng dẫn của bản JDK đang dùng.

## 8. Quản lý thứ tự callback và phụ thuộc resource

Thứ tự đăng ký resource ảnh hưởng đến thứ tự callback. Trong các triển khai CRaC phổ biến, beforeCheckpoint() được gọi theo thứ tự đăng ký; afterRestore() được gọi theo thứ tự ngược lại. Cần kiểm tra tài liệu của runtime đang sử dụng.

Ví dụ:

~~~java
Core.getGlobalContext().register(databaseResource);
Core.getGlobalContext().register(cacheResource);
Core.getGlobalContext().register(serverResource);
~~~

Thứ tự chuẩn bị:

~~~text
databaseResource.beforeCheckpoint()
cacheResource.beforeCheckpoint()
serverResource.beforeCheckpoint()
~~~

Thứ tự khôi phục sau restore:

~~~text
serverResource.afterRestore()
cacheResource.afterRestore()
databaseResource.afterRestore()
~~~

Đừng chọn thứ tự đăng ký chỉ dựa vào tên component. Hãy xác định dependency thực tế. Nếu server cần cache và database để hoạt động, server chỉ nên mở lại lưu lượng sau khi các dependency đã sẵn sàng.

Với checkpoint bị hủy, bộ điều phối ứng dụng có thể cần thứ tự rollback riêng. Thứ tự này phải dựa trên quan hệ phụ thuộc và trạng thái đã thay đổi, không phải gọi afterRestore() hàng loạt.

### Đăng ký một lần và giữ trạng thái nhất quán

Resource thường được đăng ký trong quá trình khởi tạo component. Tránh tạo và đăng ký thêm resource mới trong mỗi lần checkpoint nếu không có cơ chế quản lý vòng đời tương ứng.

Cần bảo đảm:

- Mỗi component có một trạng thái chuẩn để xác định đang hoạt động hay đã chuẩn bị.
- Việc đăng ký không bị lặp ngoài ý muốn.
- Rollback và afterRestore() có thể phân biệt trạng thái hiện tại.
- Component không phục vụ request trong khi dependency còn đóng.
- Log thể hiện thứ tự callback để dễ tìm component gây lỗi.

## 9. Kiểm thử tình huống checkpoint bị hủy

Không nên chỉ kiểm thử đường đi thành công. Cần chủ động tạo lỗi ở các giai đoạn khác nhau để xác nhận ứng dụng khôi phục đúng trạng thái.

### Kiểm thử callback tự thất bại

Cho một Resource ném exception sau khi đã pause worker nhưng trước khi hoàn tất đóng tài nguyên.

Kết quả mong đợi:

- Resource tự rollback phần việc đã làm.
- Worker hoạt động lại hoặc chuyển sang trạng thái lỗi có kiểm soát.
- Exception gốc vẫn được báo cho bộ điều phối.
- Ứng dụng không mở lại lưu lượng trước khi thành phần sẵn sàng.

### Kiểm thử một Resource khác thất bại

Cho Resource A chuẩn bị thành công, sau đó Resource B ném exception.

Kết quả mong đợi:

- Checkpoint bị hủy.
- Core.checkpointRestore() ném CheckpointException.
- Ứng dụng tiếp tục ở instance ban đầu.
- Bộ điều phối gọi rollback cho A.
- A phục hồi tài nguyên và trạng thái phục vụ.
- Không có ảnh checkpoint được xem là hợp lệ cho lần yêu cầu đó.

### Kiểm thử lỗi ở native checkpoint engine

Cho checkpoint engine thất bại sau khi các callback ứng dụng đã hoàn tất.

Kết quả mong đợi:

- Lỗi được nhận diện là checkpoint failure.
- Những thành phần đã PREPARED được rollback.
- Ứng dụng ban đầu trở lại trạng thái hoạt động hoặc chuyển sang maintenance nếu rollback không thành công.
- Log phân biệt lỗi callback và lỗi engine.

### Kiểm thử lỗi sau restore

Cho một Resource ném exception trong afterRestore().

Kết quả mong đợi:

- Lỗi được phân biệt với CheckpointException.
- Ứng dụng không chạy logic rollback của checkpoint bị hủy.
- Instance đã restore được giữ ở trạng thái chưa sẵn sàng.
- Thành phần lỗi được retry hoặc báo lỗi để hệ thống giám sát xử lý.

### Kiểm thử rollback lặp lại

Gọi rollback hai lần trên cùng participant.

Kết quả mong đợi:

- Lần gọi thứ hai không đóng/mở tài nguyên sai trạng thái.
- Không tạo thêm thread hoặc connection trùng lặp.
- Trạng thái cuối cùng vẫn nhất quán.

## 10. Ghi log và quan sát quá trình phục hồi

Khi checkpoint bị hủy, log cần đủ thông tin để xác định trạng thái của từng component.

Nên ghi:

- Tên resource và định danh lần checkpoint.
- Thời điểm bắt đầu và kết thúc beforeCheckpoint().
- Trạng thái trước khi chuẩn bị.
- Các thao tác đã hoàn thành, ví dụ pause worker, flush buffer, close connection.
- Nguyên nhân checkpoint thất bại.
- Thời điểm bắt đầu và kết thúc rollback.
- Lỗi rollback và suppressed exception.
- Trạng thái cuối cùng: READY, MAINTENANCE hoặc FAILED.

Không chỉ log một dòng “checkpoint failed”. Nếu ứng dụng đã tiếp tục chạy nhưng listener vẫn đóng, thông tin trạng thái component mới giúp tìm được nguyên nhân thực tế.

Có thể theo dõi các chỉ số:

| Chỉ số | Ý nghĩa |
|---|---|
| checkpoint_attempt_total | Tổng số yêu cầu checkpoint |
| checkpoint_failure_total | Số lần checkpoint thất bại |
| checkpoint_prepare_duration | Thời gian chuẩn bị resource |
| checkpoint_rollback_duration | Thời gian phục hồi sau khi hủy |
| checkpoint_rollback_failure_total | Số lần rollback không thành công |
| component_ready | Thành phần có sẵn sàng phục vụ hay không |

Tránh ghi credential, token, dữ liệu cá nhân hoặc nội dung nhạy cảm vào log. Dùng định danh resource và mã lỗi để liên kết các sự kiện trong cùng một chu kỳ.

## 11. Các lỗi thiết kế thường gặp

**Chỉ phục hồi trong afterRestore():** checkpoint bị hủy không tạo ra restore, do đó tiến trình ban đầu có thể tiếp tục với resource đang đóng hoặc pause.

**Không ghi nhận trạng thái từng bước:** callback thất bại giữa chừng khiến ứng dụng không biết phần nào đã được thực hiện và cần rollback.

**Rollback không idempotent:** gọi phục hồi hai lần có thể tạo kết nối trùng, mở file nhiều lần hoặc khởi động nhiều worker.

**Rollback sai thứ tự:** consumer được mở trước dependency khiến request truy cập vào tài nguyên chưa sẵn sàng.

**Bỏ qua lỗi rollback:** checkpoint thất bại đã được ghi nhận nhưng component vẫn ở trạng thái lỗi. Ứng dụng lại mở lưu lượng và tạo thêm lỗi dây chuyền.

**Dùng jcmd nhưng kỳ vọng catch trong mã Java:** lệnh jcmd đến từ bên ngoài, không chạy trong khối try/catch của luồng nghiệp vụ. Nếu cần rollback có kiểm soát, dùng bộ điều phối gọi API CRaC trong ứng dụng.

**Nhầm CheckpointException với RestoreException:** checkpoint bị hủy cần rollback trên instance cũ; restore notification thất bại cần phục hồi trên instance mới.

## 12. Nguyên tắc triển khai

- Xem beforeCheckpoint() là giai đoạn chuẩn bị có thể thất bại.
- Tự rollback phần thay đổi cục bộ nếu callback của component thất bại giữa chừng.
- Với checkpoint được yêu cầu bằng Core.checkpointRestore(), bắt CheckpointException và rollback tất cả participant đã chuẩn bị.
- Không chờ afterRestore() để phục hồi khi checkpoint bị hủy.
- Phân biệt CheckpointException, RestoreException và UnsupportedOperationException.
- Thiết kế rollback idempotent và lưu trạng thái từng bước.
- Phục hồi dependency trước consumer và chỉ mở lưu lượng khi toàn bộ thành phần bắt buộc đã READY.
- Nếu rollback thất bại, giữ ứng dụng ở trạng thái chưa sẵn sàng và báo lỗi cho hệ thống giám sát.
- Nếu dùng jcmd trực tiếp, thiết kế quy trình quản trị phù hợp vì ứng dụng không thể bắt exception đó trong luồng gọi API.
- Kiểm thử lỗi callback, lỗi engine, lỗi restore và rollback lặp lại.

Khả năng phục hồi sau checkpoint bị hủy là một phần của thiết kế resource CRaC. Mỗi thành phần cần biết mình đã thay đổi những gì, có thể hoàn tác ra sao và khi nào được phép hoạt động trở lại. Khi bộ điều phối phân biệt rõ nhánh checkpoint thất bại với nhánh restore thành công, ứng dụng có thể tiếp tục an toàn ngay cả khi một yêu cầu checkpoint không tạo được ảnh.
