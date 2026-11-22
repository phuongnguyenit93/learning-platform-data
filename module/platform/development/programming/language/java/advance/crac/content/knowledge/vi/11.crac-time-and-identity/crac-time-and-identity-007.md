# UUID và bộ đếm được tạo trước checkpoint khi nhân nhiều bản sao

CRaC (Coordinated Restore at Checkpoint) cho phép tạo một ảnh trạng thái của tiến trình Java rồi khởi chạy nhiều tiến trình từ cùng ảnh đó. Khi có nhiều bản sao được restore từ một checkpoint image, mỗi bản sao bắt đầu với trạng thái heap giống nhau tại thời điểm checkpoint.

Điều này ảnh hưởng trực tiếp đến UUID, bộ đếm và các bộ sinh định danh. Một UUID đã được tạo trước checkpoint sẽ có cùng giá trị trong mọi bản sao. Một AtomicLong hoặc bộ đếm trong bộ nhớ cũng bắt đầu từ cùng giá trị ở tất cả bản sao. Nếu mỗi bản sao tiếp tục tăng bộ đếm hoặc sinh ID theo cùng trạng thái nội bộ, chúng có thể tạo ra định danh trùng nhau.

Muốn tạo ID duy nhất sau khi nhân bản, ứng dụng phải phân biệt trạng thái dùng chung được kế thừa từ image với định danh riêng của từng instance. Các định danh cần phân biệt bản sao phải được cấp hoặc khởi tạo lại sau restore bằng nguồn có tính duy nhất giữa các instance.

## 1. Vì sao nhân bản checkpoint làm lặp trạng thái định danh?

Giả sử ứng dụng tạo checkpoint khi có trạng thái:

~~~text
instanceId = 7f...
requestId  = a2...
counter    = 5000
workerId   = 12
randomState = S
~~~

Từ cùng một image, hệ thống restore ba tiến trình:

~~~text
                 Checkpoint image
                counter = 5000
                workerId = 12
                randomState = S
                       |
          +------------+------------+
          |            |            |
          v            v            v
       Copy A        Copy B        Copy C
       count=5000    count=5000    count=5000
       worker=12     worker=12     worker=12
       state=S       state=S       state=S
~~~

Mỗi tiến trình có không gian bộ nhớ riêng sau khi restore, nhưng các giá trị ban đầu được sao chép từ cùng một image. AtomicLong bảo đảm các thread trong một tiến trình cập nhật nguyên tử; nó không phối hợp với AtomicLong ở các tiến trình khác.

Nếu ba bản sao đều gọi incrementAndGet(), mỗi bản sao có thể nhận cùng giá trị 5001. Nếu giá trị đó được dùng làm khóa toàn cục, ba bản sao có thể ghi đè hoặc xung đột dữ liệu.

Cần phân biệt:

- **Logical application ID:** định danh cùng một ứng dụng hoặc cùng một dịch vụ; có thể giống nhau giữa các bản sao.
- **Instance ID:** định danh riêng cho từng tiến trình được restore; phải khác nhau giữa các bản sao.
- **Request/job/event ID:** định danh một hoạt động cụ thể; cần duy nhất theo phạm vi mà hệ thống yêu cầu.
- **Counter/sequence:** số thứ tự tăng dần; phạm vi duy nhất có thể là một instance, một worker, một database hoặc toàn hệ thống.

Không phải mọi giá trị giống nhau giữa các bản sao đều là lỗi. Lỗi xảy ra khi một giá trị được dùng với kỳ vọng duy nhất trong một phạm vi rộng hơn phạm vi mà nó thực sự bảo đảm.

## 2. UUID đã tạo trước checkpoint vẫn giống nhau

UUID là một giá trị 128 bit. Java biểu diễn nó bằng java.util.UUID.

~~~java
UUID id = UUID.randomUUID();
~~~

UUID.randomUUID() tạo UUID phiên bản 4 (version 4), sử dụng nguồn số ngẫu nhiên để tạo các bit của UUID. Với nguồn ngẫu nhiên phù hợp, xác suất va chạm giữa các UUID mới là rất nhỏ.

Tuy nhiên, UUID là một giá trị dữ liệu. Nếu ứng dụng tạo UUID trước checkpoint rồi giữ trong field, mọi bản sao restore từ image sẽ nhận cùng giá trị đó:

~~~java
public final class ApplicationState {
    // Giá trị này được tạo một lần trước checkpoint.
    private final UUID instanceId = UUID.randomUUID();
}
~~~

Nếu ba tiến trình cùng restore image chứa instanceId, cả ba đều nhìn thấy cùng một UUID. Không có thuật toán ngẫu nhiên nào chạy lại chỉ vì đối tượng đã được restore; field đang giữ một giá trị UUID đã hoàn chỉnh.

Nếu UUID biểu diễn logical application ID, việc giữ nguyên có thể đúng. Nếu nó được dùng làm instance ID, cần cấp một UUID mới cho mỗi bản sao sau restore.

### Tạo instance ID sau restore

Có thể đăng ký một Resource để cập nhật định danh riêng của instance sau khi tiến trình được khôi phục:

~~~java
import java.util.UUID;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class InstanceIdentity implements Resource {
    private volatile UUID instanceId;

    public InstanceIdentity() {
        this.instanceId = UUID.randomUUID();
        Core.getGlobalContext().register(this);
    }

    public UUID instanceId() {
        return instanceId;
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) {
        // Không cần thay đổi logical application ID ở đây.
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) {
        instanceId = UUID.randomUUID();
    }
}
~~~

Ví dụ minh họa vị trí cập nhật ID. Khi triển khai thực tế, cần xác nhận nguồn SecureRandom được runtime và provider sử dụng có trạng thái độc lập sau restore. Nếu runtime có cơ chế CRaC reseed cho SecureRandom, hãy dùng đúng cấu hình và phiên bản được hỗ trợ. Nếu không có bảo đảm đó, hãy dùng generator được reseed từ entropy độc lập hoặc cấp ID từ một dịch vụ bên ngoài.

Việc gán UUID mới trong afterRestore() cũng cần diễn ra trước khi request listener, worker hoặc scheduler bắt đầu phát sinh ID. Nếu các thành phần khác dùng instanceId trong callback restore của chúng, cần điều phối thứ tự khởi tạo để ID mới đã sẵn sàng trước.

## 3. Trạng thái bộ sinh số ngẫu nhiên có thể được sao chép

Không chỉ UUID đã lưu sẵn mới có nguy cơ trùng. Bộ sinh số ngẫu nhiên cũng có trạng thái nội bộ.

Một PRNG (Pseudo-Random Number Generator) thường tạo chuỗi giá trị tiếp theo từ trạng thái hiện tại. Nếu trạng thái đó được sao chép nguyên vẹn sang nhiều tiến trình, các tiến trình có thể tạo ra cùng chuỗi giá trị:

~~~text
Generator A: state S -> x1 -> x2 -> x3 -> x4
Generator B: state S -> x1 -> x2 -> x3 -> x4
Generator C: state S -> x1 -> x2 -> x3 -> x4
~~~

Điều này không có nghĩa mọi implementation SecureRandom đều chắc chắn lặp chuỗi sau CRaC. Hành vi phụ thuộc provider, entropy source, phiên bản JDK và cơ chế tích hợp checkpoint/restore. Một số runtime hoặc provider có thể xử lý reseed khi restore. Cần kiểm tra tài liệu của JDK và provider đang chạy.

Điểm quan trọng là không được suy luận rằng chỉ cần tạo một đối tượng SecureRandom mới sau restore thì trạng thái chắc chắn độc lập. Nếu provider khởi tạo từ trạng thái hoặc nguồn entropy bị sao chép, việc tạo đối tượng mới chưa đủ.

### UUID.randomUUID() và SecureRandom

UUID.randomUUID() là API tiện lợi, nhưng ứng dụng không truyền một SecureRandom riêng vào phương thức này. Vì vậy, ứng dụng không trực tiếp điều khiển thời điểm reseed generator nội bộ mà UUID sử dụng.

Nếu cần kiểm soát rõ quá trình tạo UUID sau restore, có thể quản lý một SecureRandom riêng, dùng provider có hỗ trợ reseed và kiểm tra lỗi nếu không thể lấy entropy mới.

Ví dụ tạo UUID v4 từ generator được quản lý:

~~~java
import java.nio.ByteBuffer;
import java.util.UUID;
import java.security.SecureRandom;

public final class UuidGenerator {
    private final SecureRandom random;

    public UuidGenerator(SecureRandom random) {
        this.random = random;
    }

    public synchronized UUID nextUuid() {
        byte[] bytes = new byte[16];
        random.nextBytes(bytes);

        // Đặt version 4.
        bytes[6] = (byte) ((bytes[6] & 0x0f) | 0x40);

        // Đặt RFC 4122 variant.
        bytes[8] = (byte) ((bytes[8] & 0x3f) | 0x80);

        ByteBuffer buffer = ByteBuffer.wrap(bytes);
        return new UUID(buffer.getLong(), buffer.getLong());
    }
}
~~~

Đoạn code tạo UUID v4 từ 122 bit ngẫu nhiên. Nó không tự giải quyết vấn đề entropy sau restore; trách nhiệm của phần quản lý SecureRandom là cung cấp generator có trạng thái độc lập giữa các bản sao.

### Reseed sau restore

Với JDK hỗ trợ SecureRandom.reseed() và provider có khả năng reseed, có thể yêu cầu provider lấy entropy mới:

~~~java
SecureRandom random = SecureRandom.getInstanceStrong();
random.reseed();
~~~

Cần lưu ý:

- getInstanceStrong() chọn thuật toán/provider theo cấu hình bảo mật của JDK; nó có thể chậm hoặc chờ entropy tùy môi trường.
- reseed() cần provider hỗ trợ. Nếu provider không hỗ trợ, ứng dụng phải xử lý UnsupportedOperationException hoặc lỗi tương ứng.
- setSeed(System.currentTimeMillis()) không phải cách reseed an toàn. Thời gian có thể giống nhau giữa các bản sao và không cung cấp entropy mật mã đủ mạnh.
- setSeed() bổ sung dữ liệu seed theo hợp đồng của SecureRandom; không nên xem một seed dự đoán được là cách đảm bảo độc lập giữa các tiến trình.
- Việc reseed cần hoàn tất trước khi generator được dùng để cấp ID.

Nếu không thể xác nhận entropy độc lập, hãy không phát ID dựa trên generator đó. Giữ ứng dụng ở trạng thái chưa sẵn sàng hoặc dùng một dịch vụ cấp ID bên ngoài.

## 4. AtomicLong và bộ đếm trong bộ nhớ cũng bị nhân bản

Ví dụ:

~~~java
public final class LocalSequence {
    private final AtomicLong counter = new AtomicLong(0);

    public long next() {
        return counter.incrementAndGet();
    }
}
~~~

Nếu checkpoint được tạo khi counter là 100, mọi bản sao restore đều bắt đầu từ 100. Các bản sao có thể cùng cấp:

| Instance | Giá trị counter sau restore | ID tiếp theo |
|---|---:|---:|
| A | 100 | 101 |
| B | 100 | 101 |
| C | 100 | 101 |

AtomicLong chỉ giải quyết tranh chấp giữa các thread trong cùng tiến trình. Nó không cung cấp khóa phân tán, không liên lạc với các bản sao và không biết một image đã được restore bao nhiêu lần.

Tương tự, các cơ chế sau đều chỉ có phạm vi trong tiến trình nếu không có điều phối bên ngoài:

- synchronized.
- ReentrantLock.
- AtomicInteger và AtomicLong.
- LongAdder.
- Biến static.
- Bộ đếm trong singleton hoặc bean.
- Bộ đếm theo thread hoặc ThreadLocal.

Các giá trị này có thể được sao chép cùng checkpoint image. Không dùng chúng một mình làm sequence toàn cục khi một image có thể tạo ra nhiều instance.

## 5. Các chiến lược tạo ID duy nhất sau restore

Không có một cách cấp ID phù hợp cho mọi hệ thống. Hãy chọn theo phạm vi duy nhất, yêu cầu thứ tự và khả năng truy cập dịch vụ bên ngoài.

| Chiến lược | Cách hoạt động | Phù hợp |
|---|---|---|
| UUID v4 với entropy độc lập | Sinh UUID mới sau restore bằng nguồn ngẫu nhiên đã được reseed/đảm bảo độc lập | ID phân tán, không cần thứ tự |
| Database sequence | Database cấp số tăng duy nhất | ID số toàn hệ thống |
| Cấp block/range | Coordinator cấp các khoảng số không chồng lấn cho từng instance | Nhiều ID, giảm số lần gọi dịch vụ |
| Instance ID + local counter | Cấp ID instance riêng sau restore rồi ghép với counter cục bộ | ID duy nhất theo instance |
| Worker ID + timestamp + sequence | Bộ sinh kiểu Snowflake với worker ID được cấp riêng | ID số có thứ tự gần theo thời gian |
| ID service tập trung | Mỗi yêu cầu hoặc batch lấy ID từ dịch vụ cấp phát | Hệ thống cần chính sách tập trung |

### UUID mới sau restore

Dùng UUID v4 khi cần ID có xác suất va chạm cực thấp và không cần sắp xếp theo thời gian. Cần bảo đảm generator sau restore dùng entropy độc lập.

### Database sequence

Database sequence có thể cấp số duy nhất cho nhiều instance cùng sử dụng một database:

~~~sql
CREATE SEQUENCE event_id_seq START WITH 1 INCREMENT BY 1;
~~~

Mỗi instance lấy ID bằng:

~~~sql
SELECT nextval('event_id_seq');
~~~

Tên hàm và cú pháp phụ thuộc database; ví dụ trên dùng PostgreSQL. Sequence thường không rollback theo transaction, vì vậy có thể xuất hiện khoảng trống khi transaction thất bại. Khoảng trống không ảnh hưởng tính duy nhất.

Ưu điểm là nhiều bản sao dùng chung một nguồn cấp phát. Nhược điểm là cần database sẵn sàng khi cấp ID và có thể tăng tải nếu mỗi ID đều phải truy vấn database.

### Cấp range từ coordinator

Để giảm số lần gọi database, mỗi instance có thể xin một block số:

~~~text
Copy A xin range:  100000 - 100999
Copy B xin range:  101000 - 101999
Copy C xin range:  102000 - 102999
~~~

Mỗi bản sao tăng counter cục bộ trong range của mình. Coordinator phải cấp range bằng thao tác nguyên tử để không có hai instance nhận cùng một khoảng.

Không được cấp range trước checkpoint rồi dùng lại sau restore. Nếu range được lưu trong heap, mọi bản sao sẽ kế thừa cùng range. Mỗi bản sao phải xin range mới sau restore hoặc xin một lease/namespace mới.

### Instance ID kết hợp local counter

Một cách đơn giản là cấp instance ID duy nhất sau restore, sau đó ghép với sequence cục bộ:

~~~text
instanceId = 6f2b...
localCounter = 1, 2, 3, 4, ...

Generated ID:
6f2b...-1
6f2b...-2
6f2b...-3
~~~

Các bản sao có instance ID khác nhau nên có thể dùng cùng giá trị localCounter mà không tạo cùng ID.

Điều kiện là instance ID phải thực sự mới và duy nhất giữa các bản sao. Nếu instance ID được tạo trước checkpoint, giải pháp này mất tác dụng.

## 6. Cấp instance identity mới từ một coordinator

Với hệ thống cần uniqueness mạnh, có thể cấp identity từ database hoặc dịch vụ điều phối sau restore.

Một abstraction đơn giản:

~~~java
import java.util.UUID;

public interface InstanceIdentityAllocator {
    InstanceIdentity acquireNewIdentity() throws Exception;
}

public record InstanceIdentity(
    UUID instanceId,
    long fencingToken
) {}
~~~

Mỗi lần cấp phát, coordinator trả về một instance ID mới và một fencing token tăng đơn điệu. Fencing token giúp hệ thống bên ngoài nhận biết instance nào có quyền ghi mới nhất.

Resource có thể yêu cầu identity mới trong afterRestore():

~~~java
import java.util.concurrent.atomic.AtomicLong;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class CloneAwareIdentity implements Resource {
    private final InstanceIdentityAllocator allocator;

    private volatile InstanceIdentity identity;
    private final AtomicLong localCounter = new AtomicLong();

    public CloneAwareIdentity(
            InstanceIdentityAllocator allocator) throws Exception {
        this.allocator = allocator;
        this.identity = allocator.acquireNewIdentity();
        Core.getGlobalContext().register(this);
    }

    public String nextId() {
        InstanceIdentity current = identity;

        if (current == null) {
            throw new IllegalStateException(
                "Instance identity is not ready"
            );
        }

        long sequence = localCounter.getAndIncrement();

        return current.instanceId() + "-" + sequence;
    }

    public long fencingToken() {
        InstanceIdentity current = identity;
        if (current == null) {
            throw new IllegalStateException("Identity is not ready");
        }

        return current.fencingToken();
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) {
        // Không xóa identity ở đây.
        // Nếu checkpoint bị hủy, instance gốc vẫn cần identity hiện tại.
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        InstanceIdentity fresh = allocator.acquireNewIdentity();

        // Reset sequence trước khi công bố identity mới.
        localCounter.set(0);
        identity = fresh;
    }
}
~~~

Ví dụ giả định allocator có thể cấp một identity mới, không trùng với bất kỳ bản sao đang hoạt động nào. Trong thực tế, allocator cần thao tác nguyên tử ở database hoặc coordinator và có chính sách xử lý khi dịch vụ đó không khả dụng.

Việc lấy identity mới trong constructor phục vụ instance khởi chạy bình thường. Trong afterRestore(), mỗi bản sao nhận một identity riêng. localCounter có thể bắt đầu lại từ 0 vì namespace instanceId đã thay đổi.

### Vì sao có fencing token?

Một lease có thể hết hạn hoặc một instance cũ có thể vẫn chạy do network partition. Nếu instance cũ tiếp tục ghi sau khi instance mới nhận lease, chỉ dựa vào instance ID là chưa đủ.

Fencing token là số thế hệ tăng dần do coordinator cấp. Hệ thống nhận ghi kiểm tra token; token cũ hơn bị từ chối. Nhờ vậy, instance có lease cũ không thể ghi đè dữ liệu do instance có token mới quản lý.

Ví dụ:

~~~text
Checkpoint chứa fencing token = 40

Sau restore:
Copy A nhận token = 41
Copy B nhận token = 42
Copy C nhận token = 43

Kho lưu trữ chỉ chấp nhận token mới nhất theo lease/ownership.
~~~

Cách áp dụng token cần được hỗ trợ bởi hệ thống nhận ghi. Chỉ tăng một biến trong heap không tạo fencing giữa các tiến trình.

## 7. Bộ đếm theo instance và cấp range

Nếu mỗi bản sao tạo nhiều ID, việc gọi coordinator cho từng ID có thể tốn kém. Có thể xin một range mới sau restore rồi tăng local counter trong phạm vi đó.

Ví dụ abstraction:

~~~java
public record IdRange(long firstInclusive, long lastInclusive) {}

public interface IdRangeAllocator {
    IdRange allocateRange(int size) throws Exception;
}
~~~

Resource giữ range:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class RangeSequence implements Resource {
    private final IdRangeAllocator allocator;
    private final int blockSize;

    private long nextValue;
    private long rangeEndExclusive;

    public RangeSequence(
            IdRangeAllocator allocator,
            int blockSize) throws Exception {
        this.allocator = allocator;
        this.blockSize = blockSize;
        allocateNewRange();
        Core.getGlobalContext().register(this);
    }

    public synchronized long nextId() throws Exception {
        if (nextValue >= rangeEndExclusive) {
            allocateNewRange();
        }

        return nextValue++;
    }

    private synchronized void allocateNewRange() throws Exception {
        IdRange range = allocator.allocateRange(blockSize);
        nextValue = range.firstInclusive();
        rangeEndExclusive = Math.addExact(range.lastInclusive(), 1);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) {
        // Không dựa vào range đang giữ để chia sẻ cho các bản sao.
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        // Mỗi bản sao xin một range mới, không dùng range trong image.
        allocateNewRange();
    }
}
~~~

Đây là ví dụ khái niệm; implementation thực tế phải xử lý tràn số, lỗi khi cấp range và việc công bố range mới. Phương thức nextId() được đồng bộ để minh họa tính đúng đắn; nếu cần throughput cao, có thể tối ưu bằng atomic reservation nhưng vẫn phải bảo đảm không hai thread nhận cùng một giá trị và không sử dụng range đã hết.

Quy tắc quan trọng: range được lưu trong image là range đã bị nhân bản. Không dùng lại range đó sau restore. Hãy xin range mới từ nguồn cấp phát dùng chung.

## 8. Bộ sinh ID kiểu Snowflake

Một số hệ thống dùng ID số 64 bit có cấu trúc gồm:

- Timestamp tương đối so với một custom epoch.
- Worker ID hoặc node ID.
- Sequence tăng trong cùng một khoảng thời gian.

Một bố cục minh họa:

~~~text
| timestamp | workerId | sequence |
| 41 bits   | 10 bits  | 12 bits  |
~~~

Worker ID phân biệt các node; sequence phân biệt các ID do cùng node tạo trong cùng một đơn vị thời gian.

Cách này có thể tạo ID có thứ tự gần theo thời gian và không cần truy cập database cho từng ID. Tuy nhiên, khi restore nhiều bản sao từ cùng checkpoint, worker ID và sequence trong heap đều có thể giống nhau.

Để dùng an toàn:

1. Mỗi instance xin worker ID hoặc lease riêng sau restore.
2. Coordinator bảo đảm hai instance đang hoạt động không dùng cùng worker ID trong cùng phạm vi.
3. Sequence được reset theo quy tắc generator sau khi worker ID mới được cấp.
4. Nếu đồng hồ lùi, generator phải chờ, báo lỗi hoặc dùng cơ chế fencing; không tiếp tục tạo ID có thể trùng.
5. Nếu sequence trong cùng millisecond bị tràn, generator phải chờ sang tick tiếp theo hoặc báo quá tải.
6. Lease worker ID phải có TTL, renewal và fencing để xử lý instance cũ chưa dừng.

Không dùng hostname hoặc PID làm worker ID duy nhất nếu không có quy tắc cấp phát. Hostname có thể trùng trong container, PID có thể được tái sử dụng, và một checkpoint image có thể được restore nhiều lần trên cùng host.

## 9. Phân biệt định danh được giữ lại và định danh phải tạo mới

Khi thiết kế đối tượng được checkpoint, hãy phân loại từng trường:

| Dữ liệu | Giữ nguyên sau restore? | Lý do |
|---|---|---|
| Logical application ID | Thường có | Các bản sao vẫn thuộc cùng ứng dụng |
| Tenant ID | Có, nếu cùng tenant | Phạm vi dữ liệu nghiệp vụ không đổi |
| ID của bản ghi đã tồn tại | Có | Định danh bản ghi không được thay đổi |
| Instance ID | Không, nếu cần phân biệt bản sao | Mỗi tiến trình restore là một instance riêng |
| Worker ID/lease | Phải cấp lại | Tránh hai bản sao dùng chung namespace |
| AtomicLong toàn cục trong heap | Không thể dùng như sequence toàn cục | Giá trị bị sao chép |
| Local counter gắn với instance ID mới | Có thể reset | Namespace đã được thay mới |
| UUID cho request đang xử lý | Phụ thuộc nghiệp vụ | Cần tránh gửi lại cùng request như một hoạt động mới |
| PRNG state dùng sinh ID | Phải đảm bảo độc lập | Tránh lặp chuỗi sau khi nhân bản |

Một field final không tự trở thành duy nhất. final chỉ ngăn gán lại tham chiếu sau khi khởi tạo; nó không ngăn checkpoint image sao chép cùng giá trị sang nhiều tiến trình.

## 10. Thời điểm cấp lại identity

Thời điểm phù hợp thường là afterRestore(), sau khi các dependency cần thiết đã sẵn sàng và trước khi ứng dụng mở lưu lượng.

Một trình tự có thể là:

~~~text
Restore tiến trình
       |
       v
Khởi tạo cấu hình và dependency
       |
       v
Kết nối coordinator / ID allocator
       |
       v
Cấp instance ID, worker ID hoặc range mới
       |
       v
Khởi tạo counter cục bộ
       |
       v
Khởi động worker và scheduler
       |
       v
Mở request listener
~~~

Nếu resource cấp identity chạy sau resource khởi động worker, worker có thể phát ID từ namespace cũ. Hãy điều phối thứ tự callback hoặc dùng một startup gate để worker không chạy trước khi identity mới được cấp.

### Nếu coordinator không khả dụng

Nếu identity phải duy nhất toàn hệ thống và coordinator không thể cấp identity, không nên tự tạo một worker ID từ timestamp hoặc PID rồi giả định nó không trùng.

Có thể:

- Giữ instance ở trạng thái not-ready và retry có backoff.
- Dùng UUID từ entropy độc lập nếu chính sách hệ thống cho phép.
- Không nhận công việc tạo ID cho đến khi allocator hoạt động.
- Báo lỗi rõ ràng để hệ thống orchestration thử lại hoặc chuyển instance sang trạng thái lỗi.

Tính duy nhất là điều kiện correctness. Tiếp tục chạy với namespace không xác định có thể tạo xung đột dữ liệu khó sửa hơn việc tạm thời chưa sẵn sàng.

## 11. Trường hợp checkpoint bị hủy

Cần phân biệt checkpoint bị hủy với restore thành công.

- Khi checkpoint thành công và tiến trình được restore, afterRestore() chạy trên tiến trình mới. Mỗi bản sao cần cấp identity riêng.
- Khi checkpoint bị hủy, tiến trình Java ban đầu tiếp tục. afterRestore() không phải callback rollback cho trường hợp này.

Nếu ứng dụng gọi Core.checkpointRestore(), có thể bắt CheckpointException. Tuy nhiên, không phải mọi identity đều cần thay mới khi checkpoint bị hủy. Nếu tiến trình gốc vẫn là cùng một instance và lease cũ còn hợp lệ, nó có thể tiếp tục dùng identity hiện tại.

~~~java
try {
    Core.checkpointRestore();
    // Tiếp tục ở tiến trình đã restore.
} catch (CheckpointException checkpointFailure) {
    // Tiến trình ban đầu vẫn tiếp tục.
    // Giữ identity/lease hiện tại nếu vẫn còn hợp lệ.
    recoverOriginalInstance(checkpointFailure);
    throw checkpointFailure;
} catch (RestoreException restoreFailure) {
    // Tiến trình đã restore nhưng restore notification thất bại.
    // Giữ instance ở trạng thái chưa sẵn sàng.
    markNotReady(restoreFailure);
    throw restoreFailure;
}
~~~

Nếu beforeCheckpoint() đã giải phóng lease trước khi checkpoint hoàn tất, khi checkpoint bị hủy tiến trình gốc có thể mất quyền sở hữu. Khi đó, coordinator phải cấp lại lease cho instance gốc trong nhánh CheckpointException. Một thiết kế khác là không giải phóng lease trong beforeCheckpoint(), mà chỉ cấp lease thế hệ mới trong afterRestore(); lựa chọn cần phù hợp với chính sách lease và fencing của hệ thống.

Với lệnh jcmd từ bên ngoài, mã ứng dụng không có khối try/catch bao quanh lời gọi đó. Cần quy trình quản trị và resource lifecycle phù hợp với cách yêu cầu checkpoint được vận hành.

## 12. Kiểm thử khi nhân nhiều bản sao

Không chỉ kiểm tra một lần restore. Cần tạo nhiều tiến trình từ cùng checkpoint image và xác minh chúng không phát sinh ID trùng.

Một bài kiểm thử có thể thực hiện:

1. Khởi động ứng dụng với counter và UUID state đã được khởi tạo.
2. Tạo checkpoint image.
3. Restore image thành nhiều tiến trình độc lập.
4. Mỗi tiến trình cấp instance ID mới.
5. Mỗi tiến trình tạo một số lượng lớn ID.
6. Ghi các ID vào kho dữ liệu dùng chung hoặc tập hợp kiểm thử.
7. Phát hiện trùng lặp và xác nhận worker ID/lease không bị chia sẻ.
8. Khởi động thêm instance sau khi lease hết hạn hoặc instance cũ bị dừng.
9. Kiểm tra fencing token ngăn instance cũ ghi sau khi mất quyền sở hữu.

### Các tình huống cần thử

| Tình huống | Điều cần xác nhận |
|---|---|
| Một image restore hai lần | Hai instance ID khác nhau |
| Nhiều image clone khởi động đồng thời | Allocator cấp identity/range không trùng |
| SecureRandom state được checkpoint | Generator sau restore có entropy độc lập theo runtime/provider |
| Counter được checkpoint ở giá trị N | Các bản sao không dùng N+1 làm ID toàn cục chung |
| Coordinator tạm thời không khả dụng | Instance chưa ready, không phát ID sai namespace |
| Instance cũ mất lease nhưng vẫn chạy | Fencing token cũ bị từ chối |
| Range gần hết | Cấp block mới nguyên tử, không có khoảng bị dùng đồng thời |
| Đồng hồ lùi với Snowflake | Generator không tạo ID có khả năng trùng |

### Ghi nhận bằng chứng

Log hoặc metric nên có:

- checkpoint generation hoặc image ID.
- instance ID mới sau restore.
- worker ID và fencing token.
- thời điểm cấp identity.
- range đầu/cuối nếu dùng block allocation.
- số lần cấp ID thất bại.
- số lần phát hiện xung đột.
- trạng thái readiness của ID generator.

Không log secret, seed hoặc trạng thái nội bộ của SecureRandom. Chỉ log metadata cần thiết để chẩn đoán.

## 13. Các lỗi thiết kế thường gặp

**Dùng UUID đã tạo trước checkpoint làm instance ID:** mọi bản sao giữ cùng UUID vì đó là một giá trị đã được lưu trong heap.

**Tin rằng AtomicLong là duy nhất toàn hệ thống:** AtomicLong chỉ nguyên tử trong một tiến trình; các bản sao bắt đầu từ cùng giá trị.

**Tạo SecureRandom mới rồi cho rằng chắc chắn độc lập:** hành vi phụ thuộc provider và nguồn entropy. Phải kiểm tra cơ chế reseed sau restore.

**Gọi setSeed() bằng thời gian hiện tại:** thời gian có thể giống nhau giữa các bản sao và không thay thế entropy mật mã.

**Cấp worker ID hoặc range trước checkpoint:** giá trị đó bị sao chép cùng image. Mỗi bản sao cần cấp lại namespace sau restore.

**Dùng PID hoặc hostname làm worker ID:** chúng không bảo đảm duy nhất khi chạy nhiều container hoặc restore trên cùng máy.

**Khởi động worker trước khi cấp identity mới:** worker có thể phát ID từ namespace cũ trước khi afterRestore() hoàn tất.

**Bỏ qua fencing token:** một instance cũ có thể tiếp tục ghi sau khi lease đã được cấp cho instance mới.

**Không kiểm thử nhiều bản sao:** một tiến trình chạy đơn lẻ không thể bộc lộ các xung đột do cùng image tạo ra.

## 14. Quy trình triển khai đề xuất

### Trước checkpoint

1. Phân loại ID nào là logical ID và ID nào phải duy nhất theo instance.
2. Xác định counter nào chỉ dùng cục bộ và counter nào cần duy nhất toàn hệ thống.
3. Đảm bảo không dùng UUID/worker ID/range được tạo trước checkpoint như namespace riêng cho mọi bản sao.
4. Lưu trạng thái nghiệp vụ cần giữ lại, chẳng hạn ID bản ghi và last processed sequence.
5. Đăng ký Resource chịu trách nhiệm khởi tạo lại identity sau restore.

### Sau restore

1. Khởi tạo dependency cần thiết cho ID allocator.
2. Lấy entropy mới hoặc xác nhận runtime/provider đã reseed generator theo cơ chế được hỗ trợ.
3. Cấp instance ID, worker ID, lease hoặc range mới từ nguồn dùng chung.
4. Reset local counter trong namespace mới.
5. Công bố identity mới trước khi khởi động worker và scheduler.
6. Kiểm tra fencing token hoặc quyền sở hữu nếu hệ thống dùng lease.
7. Chỉ mở lưu lượng khi ID generator sẵn sàng.

### Khi checkpoint bị hủy

1. Tiến trình ban đầu tiếp tục với identity hiện tại nếu lease còn hợp lệ.
2. Nếu lease đã được giải phóng trong giai đoạn chuẩn bị, cấp lại lease cho instance gốc.
3. Không gọi afterRestore() để xử lý rollback.
4. Giữ ứng dụng not-ready nếu không thể xác nhận namespace hiện tại còn hợp lệ.

## 15. Nguyên tắc cần ghi nhớ

- Một checkpoint image có thể được restore thành nhiều tiến trình với cùng trạng thái heap ban đầu.
- UUID đã tạo trước checkpoint sẽ có cùng giá trị trong mọi bản sao.
- AtomicLong, synchronized và counter trong bộ nhớ chỉ bảo đảm phạm vi tiến trình.
- Trạng thái PRNG có thể bị sao chép; kiểm tra hành vi reseed của JDK, runtime và provider.
- Không xem new SecureRandom() hoặc setSeed(currentTimeMillis) là bảo đảm độc lập giữa các bản sao.
- Cấp instance ID, worker ID, lease hoặc range mới sau restore.
- Kết hợp instance ID với local counter để tạo ID riêng theo instance.
- Dùng database sequence hoặc coordinator khi cần uniqueness toàn hệ thống.
- Không tái sử dụng range đã nằm trong checkpoint image.
- Dùng fencing token để ngăn instance cũ ghi sau khi mất quyền sở hữu.
- Cấp identity trước khi mở worker, scheduler và request listener.
- Kiểm thử restore đồng thời nhiều bản sao từ cùng image.

Khi nhân nhiều bản sao từ một checkpoint image, mọi giá trị trong heap cần được xem xét theo phạm vi duy nhất mà ứng dụng yêu cầu. Giữ lại logical ID và dữ liệu nghiệp vụ là hợp lý; instance identity, worker namespace và bộ đếm dùng để phát ID toàn cục cần được cấp lại hoặc phân vùng sau restore.
