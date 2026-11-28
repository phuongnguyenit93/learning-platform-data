# Khóa trong một JVM không bảo vệ được mọi nút ứng dụng

## Mục tiêu bài học

Trong một ứng dụng Spring chạy trên một máy chủ, lập trình viên có thể dùng **synchronized**, **ReentrantLock** hoặc một biến khóa trong bộ nhớ để ngăn nhiều thread cùng cập nhật một tài nguyên. Cách này chỉ điều phối các thread nhìn thấy cùng đối tượng khóa trong cùng một JVM.

Khi ứng dụng Spring Session được triển khai thành nhiều instance, mỗi instance là một tiến trình JVM riêng. Instance A và instance B có heap, monitor, thread và các đối tượng khóa độc lập. Dù cả hai cùng dùng Redis hoặc JDBC để lưu session, một khóa Java trong A không thể ngăn B chạy cùng nghiệp vụ vào đúng thời điểm đó.

Bài học này giải thích giới hạn của khóa cục bộ, phân biệt lưu session dùng chung với đồng bộ nghiệp vụ phân tán và lựa chọn cơ chế phù hợp như atomic operation, optimistic locking, database row lock hoặc distributed lock.

Sau bài học, bạn có thể:

- Giải thích vì sao **synchronized** chỉ có phạm vi trong một JVM.
- Nhận biết lỗi khi nhiều node cùng cập nhật session hoặc dữ liệu nghiệp vụ.
- Phân biệt sticky session, shared session repository và distributed coordination.
- Chọn atomic update, optimistic locking, database lock hoặc distributed lock theo yêu cầu.
- Thiết kế lease, ownership token và fencing token để giảm rủi ro khóa hết hạn.
- Tránh khóa quá rộng, deadlock và giữ khóa trong lúc gọi dịch vụ ngoài quá lâu.
- Kiểm thử cạnh tranh giữa hai instance bằng Redis/JDBC dùng chung.
- Xác định phần dữ liệu nào nên nằm trong session và phần nào cần cơ chế nhất quán riêng.

## 1. Khóa trong JVM bảo vệ điều gì?

Trong Java, **synchronized** và các lớp khóa như **ReentrantLock** điều phối các thread trong cùng tiến trình. Chúng hoạt động dựa trên đối tượng khóa nằm trong bộ nhớ của JVM.

Ví dụ service Spring singleton:

~~~java
@Service
public class LocalInventoryService {

    private int available = 10;

    public synchronized boolean reserveOne() {
        if (available <= 0) {
            return false;
        }

        available--;
        return true;
    }
}
~~~

Trong một JVM, các thread gọi cùng instance **LocalInventoryService** sẽ lần lượt đi qua phương thức **reserveOne()**. Tại một thời điểm chỉ một thread giữ monitor của instance đó.

Phạm vi bảo vệ là:

- Cùng tiến trình JVM.
- Cùng đối tượng monitor hoặc cùng instance lock.
- Các thread thực sự dùng chung đối tượng khóa đó.
- Trong thời gian khóa được giữ.

Khóa này không tự được lưu vào Redis, không được gửi qua HTTP và không được chia sẻ với JVM khác.

### Hai instance có hai khóa khác nhau

Giả sử cùng một ứng dụng chạy hai instance:

~~~text
                 Load balancer
                 /           \
                v             v
         Application A   Application B
             JVM A           JVM B
          Local lock A    Local lock B
                |             |
                +------v------+
                 Shared database
                 available = 1
~~~

A có monitor của service A. B có monitor của service B. Hai đối tượng đó khác nhau dù class Java giống nhau và code giống hệt nhau.

Nếu request thứ nhất đến A và request thứ hai đến B, cả hai có thể cùng vào phương thức được đánh dấu **synchronized** vì mỗi JVM đang giữ một monitor riêng. Nếu cả hai cùng đọc số lượng còn 1 rồi ghi giảm, nghiệp vụ có thể bị xử lý hai lần.

Một cách diễn đạt chính xác:

> synchronized bảo vệ các thread trong cùng JVM cùng dùng một monitor; nó không tạo khóa dùng chung cho toàn bộ cụm ứng dụng.

Điều này vẫn đúng khi hai JVM chạy trên cùng máy vật lý, hai container trên cùng host hoặc hai pod ở các node Kubernetes khác nhau.

## 2. Vì sao shared session không đồng nghĩa shared lock?

Spring Session thay nơi lưu trữ **HttpSession** bằng repository như Redis hoặc JDBC. Nhờ đó, request đến instance khác có thể tải cùng trạng thái session.

Ví dụ:

1. Người dùng đăng nhập ở A.
2. A lưu session và SecurityContext vào Redis.
3. Request tiếp theo đến B.
4. B đọc session từ Redis và khôi phục trạng thái xác thực.

Điều này giải quyết việc chia sẻ dữ liệu phiên. Nó không có nghĩa các thao tác Java đang chạy trên A và B được khóa chung.

Spring Session repository quản lý vòng đời và lưu trữ session. Nó không tự biến mọi đoạn code đọc-sửa-ghi thuộc tính session thành một giao dịch phân tán nguyên tử.

### Phân biệt ba khái niệm

| Khái niệm | Giải quyết vấn đề | Không giải quyết |
|---|---|---|
| Shared session repository | Nhiều instance đọc/ghi trạng thái session dùng chung | Khóa thread hoặc hợp nhất mọi cập nhật đồng thời |
| Local JVM lock | Tuần tự hóa thread trong một JVM | Điều phối instance khác |
| Distributed coordination | Điều phối thao tác giữa các tiến trình/nút theo một phạm vi xác định | Tự động bảo đảm mọi nghiệp vụ đúng nếu code không tuân thủ giao thức |

Một session ID giống nhau chỉ giúp các instance tìm cùng session. Nó không khiến hai object **HttpSession** trong hai request trở thành cùng một object Java hoặc chia sẻ monitor.

### Ví dụ race trên thuộc tính session

Session ban đầu có:

~~~text
cartCount = 1
~~~

Hai request cùng tải giá trị 1:

- A đọc 1, tính 2.
- B đọc 1, tính 2.
- A lưu 2.
- B lưu 2.

Kết quả cuối là 2 thay vì 3. Đây là lost update. Dù repository dùng Redis hay JDBC, chuỗi đọc-sửa-ghi vẫn có thể bị cạnh tranh.

Thêm **synchronized** quanh đoạn code ở service A không khóa được đoạn code tương ứng ở B. Cần đặt thao tác nguyên tử ở kho dữ liệu hoặc dùng cơ chế phối hợp phân tán phù hợp.

## 3. Sticky session không thay thế đồng bộ phân tán

Sticky session (session affinity) yêu cầu load balancer ưu tiên chuyển các request của cùng client đến một instance. Cách này có thể giảm việc request đổi node, nhưng không phải cơ chế khóa.

Sticky session không bảo đảm:

- Một người dùng chỉ gửi một request tại một thời điểm.
- Hai tab không gửi request song song.
- Một request nền không chạy đồng thời với thao tác người dùng.
- Retry từ client hoặc gateway không tạo thao tác trùng.
- Một instance không xử lý nhiều request cùng session.
- Instance khác không xử lý cùng tài nguyên nghiệp vụ của người dùng khác.

Sticky session cũng có thể mất hiệu lực khi node lỗi, scale deployment, cấu hình load balancer thay đổi hoặc client đi qua đường truy cập khác.

Với Spring Session và repository dùng chung, ứng dụng thường có thể phục vụ session từ nhiều node mà không phụ thuộc affinity. Tuy nhiên, tính nhất quán của dữ liệu nghiệp vụ vẫn phải được thiết kế riêng.

Không dùng sticky session để che giấu race condition. Hãy kiểm thử với request được gửi trực tiếp đến hai instance hoặc luân phiên qua load balancer.

## 4. Phân biệt khóa theo session và khóa theo tài nguyên nghiệp vụ

Không phải mọi thao tác cần khóa đều nên khóa theo Session ID.

Ví dụ hai người dùng khác nhau có thể cùng mua sản phẩm cuối cùng trong kho. Khóa theo Session ID sẽ tạo hai khóa khác nhau, trong khi tài nguyên cần bảo vệ là bản ghi tồn kho của cùng một sản phẩm.

Ngược lại, một người dùng có thể mở nhiều session từ các thiết bị khác nhau. Nếu nghiệp vụ chỉ cần ngăn cùng một phiên chạy hai lần, khóa theo Session ID có thể phù hợp.

Chọn khóa theo tài nguyên thực sự cần bảo vệ:

| Nghiệp vụ | Khóa/cơ chế nên cân nhắc |
|---|---|
| Ngăn một phiên gửi lặp cùng một thao tác | Idempotency key gắn với thao tác hoặc session |
| Trừ tồn kho một sản phẩm | Atomic update hoặc row lock theo product ID |
| Cập nhật một hồ sơ dùng chung | Optimistic locking theo record ID |
| Chạy một tác vụ duy nhất cho một tài khoản | Lock theo account ID nếu quy tắc yêu cầu |
| Chỉ bảo vệ cache cục bộ của một JVM | Local lock có thể đủ |
| Điều phối tác vụ giữa nhiều worker | Distributed lock hoặc hàng đợi có phân vùng/consumer ownership |

Session ID có thể là một phần của idempotency scope, nhưng không nên coi nó là định danh duy nhất cho mọi tài nguyên nghiệp vụ.

## 5. Khi nào local lock vẫn phù hợp?

Khóa trong JVM vẫn hữu ích nếu tài nguyên thực sự chỉ tồn tại trong một tiến trình:

- Cache cục bộ không chia sẻ.
- Cấu trúc dữ liệu trong heap của một instance.
- Một bộ đệm hoặc scheduler chỉ chạy trong một JVM.
- Tối ưu hóa cạnh tranh giữa thread trên cùng node.
- Bảo vệ trạng thái nội bộ của một singleton bean.

Ví dụ **ConcurrentHashMap** và **ReentrantLock**:

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.locks.ReentrantLock;

import org.springframework.stereotype.Component;

@Component
public class LocalKeyLockRegistry {

    private final ConcurrentHashMap<String, ReentrantLock> locks =
            new ConcurrentHashMap<>();

    public void runLocally(String key, Runnable action) {
        ReentrantLock lock =
                locks.computeIfAbsent(key, ignored -> new ReentrantLock());

        lock.lock();
        try {
            action.run();
        } finally {
            lock.unlock();
        }
    }
}
~~~

Đoạn code này chỉ tuần tự hóa thread trong instance chứa **LocalKeyLockRegistry**. Nếu có ba instance Spring, sẽ có ba map và ba tập khóa riêng.

Còn một vấn đề vận hành: map có thể tăng không giới hạn nếu mỗi key mới tạo một lock và không được thu hồi. Việc xóa lock khỏi map cũng phải được thiết kế cẩn thận để không tạo hai lock khác nhau cho cùng key khi có thread đang chờ.

Chỉ dùng registry kiểu này cho phạm vi cục bộ có vòng đời rõ ràng. Không dùng nó để bảo vệ tồn kho, số dư hoặc dữ liệu chung được cập nhật bởi nhiều node.

## 6. Ưu tiên atomic operation khi có thể

Nếu nghiệp vụ biểu diễn được bằng một lệnh nguyên tử tại kho dữ liệu, thường không cần dựng distributed lock.

### Atomic update trong SQL

Ví dụ trừ tồn kho chỉ khi còn hàng:

~~~sql
UPDATE inventory
SET available = available - 1
WHERE product_id = :productId
  AND available > 0;
~~~

Sau khi thực hiện, kiểm tra số hàng được cập nhật:

- 1 hàng: giữ chỗ thành công.
- 0 hàng: sản phẩm không còn đủ số lượng hoặc không tồn tại.

Database thực hiện phép kiểm tra và cập nhật trong một câu lệnh có tính nguyên tử theo transaction semantics của hệ quản trị. Hai request cạnh tranh không thể cùng thành công bằng cách đọc một giá trị cũ rồi ghi đè tùy ý như code Java thuần.

### Atomic counter trong Redis

Với Redis, lệnh **INCR** hoặc **DECR** là thao tác nguyên tử trên một key:

~~~java
Long current = stringRedisTemplate
        .opsForValue()
        .increment("counter:daily-logins");
~~~

Ví dụ trên minh họa một counter nghiệp vụ riêng. Không dùng **INCR** trực tiếp trên key nội bộ của Spring Session để thay đổi thuộc tính session.

Nếu cần điều kiện như chỉ giảm tồn kho khi số lượng lớn hơn 0, hãy dùng Lua script hoặc một cấu trúc dữ liệu/transaction phù hợp để kiểm tra và cập nhật trong cùng thao tác nguyên tử. Không tách thành hai lệnh GET rồi DECR nếu giữa hai lệnh có thể có request khác chen vào.

### Vì sao atomic operation thường tốt hơn distributed lock?

- Kho dữ liệu vốn là nơi có thẩm quyền với bản ghi.
- Kiểm tra và cập nhật diễn ra trong cùng thao tác.
- Không cần quản lý lease, owner token hoặc release lock.
- Giảm số lượt round-trip.
- Dễ kiểm tra kết quả thành công/thất bại.

Tuy vậy, atomic operation chỉ giải quyết đúng phạm vi của lệnh đó. Nếu một nghiệp vụ cần cập nhật nhiều bảng hoặc gọi thêm hệ thống ngoài, cần transaction, outbox, saga hoặc cơ chế phối hợp khác.

## 7. Optimistic locking cho cập nhật cùng bản ghi

Optimistic locking phù hợp khi xung đột không quá thường xuyên và ứng dụng có thể phát hiện một request đang ghi trên phiên bản dữ liệu cũ.

Một bản ghi có cột version:

~~~text
account_id | balance | version
-----------+---------+--------
A-101      | 1000    | 7
~~~

Request đọc version 7. Khi ghi, nó yêu cầu version vẫn bằng 7:

~~~sql
UPDATE account
SET balance = :newBalance,
    version = version + 1
WHERE account_id = :accountId
  AND version = :expectedVersion;
~~~

Nếu update được 1 hàng, request đã cập nhật thành công. Nếu update 0 hàng, một request khác đã thay đổi version trước đó. Request hiện tại phải tải lại dữ liệu và xử lý conflict theo nghiệp vụ.

### Với JPA

Có thể dùng **@Version**:

~~~java
@Entity
public class Account {

    @Id
    private String id;

    private long balance;

    @Version
    private long version;
}
~~~

Khi hai transaction cùng cập nhật entity, JPA provider dùng version để phát hiện xung đột và thường ném **OptimisticLockException** hoặc exception được Spring chuyển đổi tương ứng.

Ứng dụng cần quyết định có retry hay trả lỗi conflict. Không retry vô hạn vì có thể tạo vòng lặp contention và làm tăng tải.

### Session không phải version store

Không chỉ đặt một thuộc tính version trong HttpSession rồi so sánh ở Java. Hai request có thể cùng đọc version cũ, cùng so sánh thành công và cùng ghi. Việc kiểm tra version và cập nhật phải nằm trong cùng câu lệnh nguyên tử hoặc transaction có kiểm soát ở kho dữ liệu có thẩm quyền.

## 8. Pessimistic locking và database row lock

Nếu xung đột thường xuyên hoặc nghiệp vụ yêu cầu tuần tự hóa thao tác trên một hàng, có thể dùng database row lock trong transaction.

Ví dụ:

~~~sql
BEGIN;

SELECT available
FROM inventory
WHERE product_id = :productId
FOR UPDATE;

-- Kiểm tra số lượng và cập nhật trong cùng transaction.

UPDATE inventory
SET available = available - 1
WHERE product_id = :productId;

COMMIT;
~~~

**SELECT ... FOR UPDATE** yêu cầu database khóa hàng phù hợp trong thời gian transaction. Transaction khác muốn khóa/cập nhật cùng hàng phải chờ hoặc xử lý theo isolation/timeout của hệ quản trị.

Lưu ý:

- Phải thực hiện thao tác đọc và ghi trong cùng transaction.
- Khóa chỉ có hiệu lực theo transaction và phạm vi row/table do database định nghĩa.
- Transaction dài làm giảm throughput và tăng nguy cơ deadlock.
- Cần đặt lock timeout và xử lý trường hợp chờ quá lâu.
- Dùng index phù hợp để tránh khóa phạm vi rộng ngoài ý muốn.
- Không giữ row lock trong lúc gọi API bên ngoài hoặc chờ người dùng.

Trong Spring, có thể dùng **@Transactional** kết hợp repository query có lock mode phù hợp. Hãy kiểm tra SQL thực tế được sinh ra và hành vi của database production.

### Khi nào database lock phù hợp?

- Cập nhật số dư hoặc tồn kho trong database đó.
- Một thao tác cần đọc trạng thái mới nhất rồi ghi trong cùng transaction.
- Có thể giữ transaction ngắn.
- Database là nguồn dữ liệu có thẩm quyền.

Nếu nghiệp vụ trải qua nhiều database hoặc dịch vụ ngoài, row lock của một database không thể khóa tài nguyên ở hệ thống khác.

## 9. Distributed lock khi cần phối hợp giữa nhiều node

Distributed lock là cơ chế nhiều tiến trình cùng tuân thủ để một tiến trình tại một thời điểm được phép thực hiện vùng công việc được bảo vệ.

Một distributed lock thường cần:

- Tên tài nguyên khóa ổn định.
- Thao tác acquire có tính nguyên tử.
- Thời hạn lease để khóa không tồn tại vô hạn.
- Định danh owner duy nhất cho lần acquire.
- Cách release chỉ cho owner hiện tại.
- Timeout chờ khóa.
- Xử lý lỗi mạng và trường hợp lease hết hạn.
- Cơ chế bảo vệ dữ liệu nếu worker cũ tiếp tục chạy sau khi mất lease.

Distributed lock là giao thức giữa các instance. Mọi worker cần sử dụng cùng giao thức và cùng lock service. Nếu một instance bỏ qua lock, khóa không thể ngăn nó ghi dữ liệu.

### Khóa Redis bằng SET NX PX

Một mẫu cơ bản trong Redis:

~~~text
SET lock:inventory:SKU-01 <owner-token> NX PX 10000
~~~

Ý nghĩa:

- **NX**: chỉ tạo key nếu key chưa tồn tại.
- **PX 10000**: lease tồn tại tối đa 10.000 millisecond.
- **owner-token**: giá trị ngẫu nhiên duy nhất cho lần acquire.

Nếu lệnh trả về thành công, client đã acquire lock. Nếu key đã tồn tại, client chưa có khóa và có thể chờ/retry theo chính sách.

Không dùng một giá trị owner cố định như worker-1 cho mọi lần acquire. Token phải phân biệt từng lần nắm giữ khóa để release không xóa nhầm lock của lần acquire khác.

### Release phải kiểm tra owner

Không thực hiện:

~~~text
DEL lock:inventory:SKU-01
~~~

Một worker có thể hết lease, worker khác acquire khóa mới, rồi worker cũ mới chạy đến lệnh DEL. Nếu xóa key vô điều kiện, worker cũ có thể xóa khóa của worker mới.

Hãy dùng thao tác so sánh token và xóa nguyên tử, thường qua Lua script:

~~~lua
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
end
return 0
~~~

Script chỉ xóa lock nếu token trong Redis vẫn khớp owner token của caller.

Ví dụ này giải quyết việc release nhầm owner. Nó chưa giải quyết hoàn toàn vấn đề worker cũ tiếp tục ghi dữ liệu sau khi lease hết hạn.

## 10. Lease hết hạn và fencing token

Một lease có thời hạn giúp hệ thống tự giải phóng khóa khi worker chết hoặc mất kết nối. Nhưng lease cũng tạo ra một tình huống nguy hiểm:

1. Worker A acquire lock với lease 10 giây.
2. A bị pause lâu hơn 10 giây, ví dụ do GC pause hoặc network stall.
3. Lease hết hạn.
4. Worker B acquire lock mới.
5. A tiếp tục chạy và tưởng rằng mình vẫn sở hữu khóa.
6. A và B cùng ghi dữ liệu.

Token owner ngăn A xóa lock của B, nhưng chưa ngăn A gửi một lệnh ghi cũ đến database.

### Fencing token

Fencing token là số tăng đơn điệu được cấp mỗi lần acquire thành công. Ví dụ:

- A nhận token 41.
- Lease A hết hạn.
- B nhận token 42.
- Hệ thống lưu dữ liệu chỉ chấp nhận token mới hơn token đã xử lý.

Nếu A quay lại với token 41 sau khi B đã ghi token 42, kho dữ liệu từ chối thao tác cũ.

Để fencing token có tác dụng, thành phần ghi dữ liệu phải kiểm tra token. Chỉ tạo số tăng dần trong Redis mà database không kiểm tra thì chưa bảo vệ được tài nguyên.

Một hệ thống có thể lưu **last_fencing_token** cùng bản ghi nghiệp vụ và cập nhật theo điều kiện:

~~~sql
UPDATE protected_resource
SET value = :newValue,
    last_fencing_token = :token
WHERE resource_id = :resourceId
  AND last_fencing_token < :token;
~~~

Nếu update 0 hàng, token đã cũ hoặc tài nguyên không còn hợp lệ.

Cấp fencing token cần được thiết kế sao cho tăng đơn điệu và gắn đúng với mỗi lần acquire thành công. Có thể dùng bộ đếm nguyên tử hoặc dịch vụ lock chuyên dụng. Cần kiểm thử khi lease hết hạn, worker pause và worker cũ quay lại.

## 11. Dùng thư viện distributed lock như Redisson

Thư viện như Redisson cung cấp abstraction **RLock** để phối hợp khóa Redis giữa nhiều JVM. Ví dụ:

~~~java
RLock lock = redissonClient.getLock("inventory:SKU-01");

boolean acquired = lock.tryLock(
        2,
        10,
        TimeUnit.SECONDS
);

if (!acquired) {
    throw new IllegalStateException("Resource is busy");
}

try {
    inventoryService.reserve("SKU-01");
} finally {
    if (lock.isHeldByCurrentThread()) {
        lock.unlock();
    }
}
~~~

Đoạn code minh họa việc chờ tối đa 2 giây và yêu cầu lease 10 giây. Cần chọn thời gian theo thời lượng công việc thực tế và semantics của phiên bản thư viện.

Một số cấu hình Redisson hỗ trợ watchdog gia hạn lease khi client còn sống và giữ lock. Nếu đặt lease time rõ ràng, hành vi hết hạn cần được hiểu đúng. Không giả định watchdog, lease và fencing token tự động giải quyết mọi kiểu stale worker.

Khi dùng thư viện:

- Tất cả instance phải dùng cùng lock service và cùng tên khóa.
- Không gọi **unlock()** từ thread không sở hữu khóa.
- Luôn release trong **finally**.
- Đặt wait timeout và giới hạn retry.
- Theo dõi thời gian giữ khóa và số lần contention.
- Xác định điều gì xảy ra nếu Redis failover hoặc client mất kết nối.
- Bảo vệ thao tác ghi bằng version/fencing token khi dữ liệu có giá trị cao.

Distributed lock không thay thế transaction. Nếu công việc chỉ là cập nhật một hàng trong database, database row lock hoặc optimistic locking thường trực tiếp hơn.

## 12. Deadlock, starvation và khóa quá rộng

Khóa phân tán có thể tạo deadlock nếu các worker lấy nhiều khóa theo thứ tự khác nhau.

Ví dụ:

- Worker A giữ lock X và chờ lock Y.
- Worker B giữ lock Y và chờ lock X.

Cả hai không thể tiến tiếp cho đến khi lease hoặc timeout kết thúc.

Giảm nguy cơ bằng cách:

- Lấy nhiều khóa theo một thứ tự toàn cục thống nhất.
- Giữ critical section ngắn.
- Tránh gọi dịch vụ ngoài khi đang giữ khóa.
- Đặt wait timeout.
- Không retry vô hạn.
- Dùng lock theo tài nguyên nhỏ nhất có thể.
- Ghi metric và log có correlation ID, không log token hoặc bí mật.

Starvation xảy ra khi một worker liên tục không lấy được khóa vì các worker khác chiếm khóa trước. Có thể cần hàng đợi công bằng hoặc cơ chế phân phối công việc khác nếu fairness là yêu cầu.

Khóa quá rộng làm giảm khả năng xử lý đồng thời. Ví dụ khóa toàn bộ user service chỉ để cập nhật một giỏ hàng sẽ khiến những tài nguyên không liên quan phải chờ nhau. Khóa theo **cartId** hoặc **productId** thường phù hợp hơn nếu đó là ranh giới nhất quán.

## 13. Không giữ distributed lock qua thao tác mạng dài

Giữ lock trong lúc gọi payment provider, gửi email hoặc chờ dịch vụ HTTP có thể khiến lease hết hạn hoặc giữ tài nguyên quá lâu.

Ví dụ luồng rủi ro:

1. Acquire lock.
2. Cập nhật dữ liệu local.
3. Gọi API bên ngoài mất 30 giây.
4. Lease 10 giây hết hạn.
5. Worker khác acquire lock.
6. Worker cũ vẫn nhận response và tiếp tục cập nhật.

Cách thiết kế tốt hơn là:

- Giữ critical section ngắn.
- Ghi ý định nghiệp vụ và trạng thái trong transaction.
- Dùng outbox để phát sự kiện sau commit.
- Gọi dịch vụ ngoài bằng idempotency key.
- Xử lý callback/retry bằng state machine.
- Dùng fencing/version ở nơi nhận nếu cần chống thao tác cũ.

Distributed lock chỉ bảo vệ phần công việc mà các bên cùng tuân thủ trong thời gian khóa có hiệu lực. Nó không tạo transaction nguyên tử xuyên qua Redis, database và dịch vụ HTTP.

## 14. Idempotency thường cần thiết hơn khóa

Nhiều request trùng nhau đến từ double-click, client retry, gateway retry hoặc message redelivery. Không phải lúc nào cũng cần khóa để xử lý. Idempotency cho phép cùng một thao tác được gửi nhiều lần nhưng chỉ tạo một kết quả nghiệp vụ.

Ví dụ client gửi **Idempotency-Key** cho thao tác tạo đơn hàng. Server lưu key cùng kết quả trong database với unique constraint:

~~~sql
CREATE TABLE idempotency_record (
    idempotency_key VARCHAR(100) PRIMARY KEY,
    request_hash VARCHAR(128) NOT NULL,
    response_body TEXT,
    status VARCHAR(30) NOT NULL
);
~~~

Khi request đến:

1. Kiểm tra idempotency key.
2. Nếu đã hoàn tất và request hash giống nhau, trả lại kết quả trước đó.
3. Nếu key đang xử lý, trả trạng thái đang xử lý hoặc chờ theo policy.
4. Nếu key mới, ghi nhận key và thực hiện nghiệp vụ trong transaction phù hợp.
5. Lưu kết quả để request retry nhận cùng kết quả.

Cần ràng buộc unique và transaction để hai request đồng thời không cùng tạo bản ghi idempotency mới. Không chỉ dùng một map trong bộ nhớ của JVM vì instance khác không nhìn thấy map đó.

Idempotency key không thay authorization. Người dùng không được phép lấy key của người khác để đọc kết quả không thuộc quyền của mình.

## 15. Spring Session và khóa nghiệp vụ: ranh giới trách nhiệm

Spring Session quản lý session identifier, thuộc tính, timeout, lưu trữ và vòng đời session. Nó không phải hệ thống khóa tổng quát cho mọi thao tác nghiệp vụ.

Không nên:

- Đồng bộ bằng **synchronized(session)** rồi cho rằng đã khóa trên mọi node.
- Dùng key Redis nội bộ của Spring Session làm lock key.
- Tự sửa key hoặc bảng Spring Session để tạo lock.
- Lưu một object **ReentrantLock** vào session.
- Giữ session attribute làm nguồn dữ liệu duy nhất cho tồn kho hoặc số dư.
- Dùng Session ID làm lock cho tài nguyên dùng chung giữa nhiều người dùng nếu phạm vi khóa thực sự là product/account/order.

Nên:

- Dùng Spring Session để duy trì trạng thái xác thực và dữ liệu giao diện nhỏ.
- Đưa trạng thái nghiệp vụ quan trọng vào database hoặc kho dữ liệu có cơ chế atomic update.
- Dùng optimistic/pessimistic locking theo record khi dữ liệu nằm trong database.
- Dùng Redis atomic operation cho phép tính phù hợp.
- Chỉ dùng distributed lock khi thao tác không thể biểu diễn đơn giản bằng atomic operation hoặc transaction.
- Gắn idempotency key với command có thể được retry.

### Ví dụ phân chia dữ liệu

| Dữ liệu | Nơi lưu/cơ chế phù hợp |
|---|---|
| Locale, theme, tab hiện tại | Session |
| ID giỏ hàng | Session có thể giữ tham chiếu |
| Chi tiết giỏ hàng cần nhất quán | Database nghiệp vụ |
| Số lượng tồn kho | Database atomic update/row lock |
| Trạng thái đăng nhập | Spring Security SecurityContext trong session theo cấu hình |
| Ngăn xử lý một command trùng | Idempotency record dùng chung |
| Khóa điều phối worker | Distributed lock service hoặc queue |

## 16. Kiểm thử khóa cục bộ thất bại giữa hai instance

Một test có giá trị cần chứng minh hai JVM độc lập có thể cùng đi vào vùng code được **synchronized** cục bộ.

### Thiết kế test

1. Khởi động hai instance A và B.
2. Mỗi instance có cùng code service dùng **synchronized**.
3. Cả hai kết nối cùng database hoặc Redis.
4. Đặt một tài nguyên ban đầu có số lượng 1.
5. Gửi hai request gần như đồng thời, một request đến A và một đến B.
6. Dùng barrier ở test để hai request cùng đọc trước khi ghi.
7. Quan sát xem cả hai có thể vượt qua kiểm tra local lock và cùng thực hiện nghiệp vụ hay không.
8. Thay local lock bằng atomic update hoặc distributed coordination.
9. Chạy lại test và xác minh chỉ một request thành công theo invariant.

Không dùng sleep cố định để giả định hai request đã chồng lấn. Dùng latch, barrier hoặc hook test ở điểm đọc và ghi để điều khiển interleaving.

### Test local lock trong một JVM

Một test với hai thread trong cùng một context có thể chứng minh **synchronized** tuần tự hóa hai thread. Nhưng nó không chứng minh khóa có phạm vi nhiều JVM.

Cần phân biệt:

- Unit test: xác minh local lock trong một process.
- Integration test: xác minh Redis/DB atomic operation hoặc lock service.
- Multi-instance test: xác minh request trên hai JVM cùng tuân thủ giao thức chia sẻ.

### Kiểm thử lease hết hạn

Nếu dùng distributed lock:

1. A acquire lock với lease ngắn.
2. Làm A pause lâu hơn lease.
3. B acquire lock sau khi lease hết hạn.
4. Cho A tiếp tục chạy.
5. Xác minh fencing/version ở kho dữ liệu từ chối thao tác stale của A.
6. Xác minh A không thể release lock thuộc B.

Test này giúp phát hiện lỗi mà một bài test acquire/release bình thường không thể tìm thấy.

## 17. Quan sát và vận hành khóa phân tán

Trong production, cần theo dõi cả trạng thái khóa và tác động đến nghiệp vụ.

Metric hữu ích:

- Số lần acquire thành công/thất bại.
- Thời gian chờ lock.
- Thời gian giữ lock.
- Số lần lease hết hạn.
- Số lần release không còn đúng owner.
- Số conflict optimistic locking.
- Số update atomic không khớp điều kiện.
- Số request bị retry hoặc trả conflict.
- Số command idempotent được nhận lại.
- Redis/database latency và connection error.

Log nên có:

- Resource key đã được che hoặc mã hóa định danh.
- Correlation ID của request/command.
- Node ID.
- Kết quả acquire/release.
- Thời gian giữ lock.
- Loại lỗi.

Không log Session ID, access token, owner token hoặc thông tin xác thực. Nếu cần nối các log theo session, dùng mã tham chiếu nội bộ đã được bảo vệ hoặc hash có chính sách rõ ràng.

Cảnh báo nên tập trung vào dấu hiệu bất thường: lock giữ lâu hơn ngưỡng, lease hết hạn thường xuyên, contention tăng đột ngột, conflict rate tăng hoặc nhiều request retry.

## 18. Chọn cơ chế theo bài toán

| Nhu cầu | Lựa chọn thường phù hợp | Vì sao |
|---|---|---|
| Bảo vệ biến trong một JVM | **synchronized** hoặc **ReentrantLock** | Không cần điều phối tiến trình khác |
| Tăng counter trong Redis | **INCR** hoặc Lua script | Thao tác nguyên tử tại Redis |
| Trừ tồn kho trong SQL | Conditional **UPDATE** hoặc row lock | Database kiểm tra và cập nhật cùng transaction |
| Sửa record ít xung đột | Optimistic locking | Phát hiện cập nhật trên version cũ |
| Sửa record xung đột cao | Pessimistic row lock | Tuần tự hóa thao tác trong transaction |
| Một tác vụ duy nhất trên nhiều worker | Distributed lock hoặc queue ownership | Điều phối nhiều tiến trình |
| Ngăn xử lý command trùng | Idempotency key với unique constraint | Retry không tạo hiệu ứng lặp |
| Nhiều bước qua nhiều hệ thống | Saga/outbox và idempotent consumer | Không thể dùng một JVM lock hay DB transaction đơn lẻ |

Không có một cơ chế khóa phù hợp cho mọi tình huống. Hãy bắt đầu từ invariant nghiệp vụ: điều gì tuyệt đối không được xảy ra? Sau đó đặt atomicity hoặc coordination ở nơi có thể thực thi invariant đó.

## 19. Những lỗi thường gặp

**Dùng synchronized trong service singleton và cho rằng toàn cụm được khóa.**  
Singleton là singleton trong một application context/JVM. Mỗi instance có bean và monitor riêng.

**Dùng synchronized(session).**  
Các request có thể có wrapper hoặc object session khác nhau. Dù cùng session ID, object Java không phải monitor dùng chung giữa request hoặc JVM.

**Bật sticky session để sửa race.**  
Sticky session không ngăn request song song trong cùng node và có thể mất hiệu lực khi failover.

**Cho rằng Redis/JDBC repository tự merge session.**  
Repository chia sẻ trạng thái nhưng không tự giải quyết mọi lost update hoặc thao tác nghiệp vụ không nguyên tử.

**Acquire lock bằng SET NX rồi release bằng DEL vô điều kiện.**  
Worker cũ có thể xóa lock của worker mới sau khi lease hết hạn. Release phải xác minh owner token.

**Dùng lease dài vô hạn.**  
Worker chết có thể giữ khóa mãi. Dùng lease, timeout và cơ chế phục hồi.

**Chỉ dùng owner token mà không nghĩ đến stale worker.**  
Owner token bảo vệ release; fencing token hoặc version check mới giúp kho dữ liệu từ chối thao tác cũ.

**Giữ distributed lock khi gọi API bên ngoài.**  
Lease có thể hết hạn giữa lúc chờ, dẫn đến hai worker cùng tiếp tục. Giữ critical section ngắn và dùng idempotency/outbox.

**Dùng distributed lock cho một phép cập nhật SQL đơn giản.**  
Conditional update hoặc row lock có thể trực tiếp và ít thành phần lỗi hơn.

**Không kiểm thử trên hai JVM.**  
Unit test hai thread trong một process chỉ chứng minh local synchronization.

## 20. Checklist thiết kế

Trước khi triển khai cơ chế đồng bộ, hãy xác định:

- Có bao nhiêu instance và worker cùng truy cập tài nguyên?
- Tài nguyên cần bảo vệ là session, account, cart, product hay command?
- Invariant nghiệp vụ nào phải luôn đúng?
- Có thể biểu diễn bằng một atomic update không?
- Dữ liệu có nằm trong một database transaction không?
- Optimistic locking có đủ khi xung đột hiếm không?
- Có cần row lock khi xung đột thường xuyên không?
- Distributed lock có thật sự cần thiết không?
- Lease, owner token và fencing token được quản lý thế nào?
- Worker stale có thể ghi sau khi mất lock không?
- Có idempotency cho retry và message redelivery không?
- Lock có thể deadlock hoặc starvation không?
- Có timeout, metric, alert và test hai instance không?
- Tất cả node có cùng lock protocol và repository configuration không?

Một thiết kế tốt chỉ khóa phần tài nguyên thực sự cần được tuần tự hóa và giữ vùng khóa càng ngắn càng tốt.

## 21. Tự kiểm tra

1. Vì sao **synchronized** chỉ bảo vệ thread trong một JVM?
2. Hai instance Spring có dùng cùng class service thì có dùng chung monitor không?
3. Spring Session Redis/JDBC chia sẻ dữ liệu gì và không chia sẻ điều gì?
4. Vì sao sticky session không giải quyết được request đồng thời?
5. Khi nào local **ReentrantLock** vẫn là lựa chọn phù hợp?
6. Vì sao conditional SQL update thường tốt hơn distributed lock cho tồn kho?
7. Optimistic locking phát hiện lost update bằng cách nào?
8. **SELECT ... FOR UPDATE** cần nằm trong phạm vi nào?
9. Redis **SET NX PX** cung cấp những thuộc tính nào cho một lease lock?
10. Vì sao không thể release lock bằng **DEL** vô điều kiện?
11. Owner token khác fencing token như thế nào?
12. Vì sao worker cũ có thể tiếp tục ghi sau khi lease hết hạn?
13. Khi nào nên dùng idempotency key thay cho lock?
14. Làm thế nào để test chứng minh local lock thất bại giữa hai node?
15. Những metric nào cần theo dõi trong production?

### Gợi ý trả lời

1. Monitor nằm trong bộ nhớ một JVM và chỉ điều phối các thread dùng cùng monitor đó.
2. Không. Mỗi application context/JVM có instance bean và monitor riêng.
3. Nó chia sẻ dữ liệu session trong repository; không chia sẻ heap, object Java, thread hoặc monitor.
4. Vì cùng node vẫn có thể xử lý nhiều request đồng thời và affinity không phải giao thức khóa.
5. Khi tài nguyên chỉ tồn tại trong một JVM, chẳng hạn cache hoặc cấu trúc dữ liệu local.
6. Vì database thực hiện kiểm tra điều kiện và cập nhật nguyên tử ngay trên bản ghi có thẩm quyền.
7. Cập nhật chỉ thành công nếu version vẫn bằng version đã đọc; nếu không, request phát hiện conflict.
8. Trong cùng transaction giữ row lock từ lúc đọc đến khi cập nhật và commit/rollback.
9. Acquire nếu key chưa tồn tại và tự hết hạn sau lease; token owner xác định lần nắm giữ khóa.
10. Vì owner cũ có thể xóa key của owner mới sau khi lease đã được cấp lại.
11. Owner token xác định ai đang giữ lock; fencing token tăng đơn điệu để kho dữ liệu từ chối thao tác stale.
12. JVM có thể pause, mất mạng hoặc chậm hơn lease; khi chạy lại nó vẫn có code tiếp tục thực thi.
13. Khi cùng một command có thể được gửi lại do retry nhưng chỉ nên tạo một hiệu ứng nghiệp vụ.
14. Chạy hai JVM, gửi request đồng thời đến hai node với cùng tài nguyên, điều khiển interleaving và so sánh với atomic/distributed coordination.
15. Acquire success/failure, wait/hold duration, lease expiry, release mismatch, optimistic conflict, retry rate và backend latency.

## Kết luận

Khóa Java như **synchronized** và **ReentrantLock** chỉ điều phối các thread trong cùng JVM. Khi Spring Session chạy trên nhiều instance, mỗi node có heap và đối tượng khóa riêng. Redis/JDBC giúp chia sẻ dữ liệu phiên, nhưng không làm các thao tác đọc-sửa-ghi trở thành nguyên tử và không tạo monitor dùng chung.

Hãy đặt cơ chế đồng bộ tại nơi có thẩm quyền với dữ liệu: dùng atomic operation hoặc transaction khi có thể, optimistic/pessimistic locking cho bản ghi database và distributed lock khi thật sự cần phối hợp nhiều tiến trình. Với distributed lock, cần lease, owner token, release có kiểm tra, fencing/version để chống stale worker và idempotency cho retry. Kiểm thử trên ít nhất hai JVM cùng repository để chứng minh invariant nghiệp vụ được giữ khi request đi đến bất kỳ node nào.

