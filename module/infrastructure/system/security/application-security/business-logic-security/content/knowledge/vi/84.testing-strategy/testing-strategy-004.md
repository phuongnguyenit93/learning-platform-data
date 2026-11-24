# Kiểm thử hồi quy cạnh tranh đồng thời (Concurrency regression tests)

Một API có thể kiểm tra đầy đủ quyền, số dư, trạng thái phê duyệt và khóa idempotency khi gọi riêng lẻ, nhưng vẫn vi phạm quy tắc nghiệp vụ khi nhiều yêu cầu chồng lấn. Hai yêu cầu cùng thấy một sản phẩm cuối cùng, hai người cùng phê duyệt một phiên bản, hoặc một webhook được gửi lại đúng lúc worker khởi động lại đều có thể tạo kết quả mà một người dùng đơn lẻ không được phép tạo.

Trong chương **Testing Strategy** của module Business Logic Security, kiểm thử hồi quy cạnh tranh đồng thời nhằm giữ những lỗi này không quay lại sau khi sửa code, thay transaction, tối ưu truy vấn hoặc bổ sung đường xử lý mới. Đích kiểm tra là **business invariant sau một lịch thực thi cạnh tranh**, bao gồm dữ liệu đã commit và tác dụng phụ, chứ không chỉ là số lượng phản hồi HTTP thành công.

## 1. Mục tiêu học tập và phạm vi

Sau bài học, bạn có thể:

- Chuyển một quy tắc nghiệp vụ thành điều kiện kiểm chứng được khi nhiều thao tác chồng lấn.
- Chọn các cặp thao tác cần kiểm thử theo trạng thái, đối tượng và quyền của chủ thể.
- Tái hiện một lịch xen kẽ từng gây lỗi bằng điểm đồng bộ có kiểm soát.
- Viết phép thử tích hợp có giới hạn thời gian, thu nhận đầy đủ lỗi từ các luồng.
- Kiểm tra cả database, outbox, kết quả gửi sang hệ thống ngoài và cơ chế idempotency.
- Phân biệt kiểm thử xác định một lịch nguy hiểm với stress test và kiểm thử tải.

Bài tập trung vào tính đúng đắn và khả năng chống lạm dụng nghiệp vụ. Các tình huống như SQL injection hay dò mật khẩu có cách kiểm thử riêng; ở đây người gửi có thể dùng yêu cầu hợp lệ về cú pháp và tài khoản đã đăng nhập để phá giới hạn nghiệp vụ bằng sự chồng lấn.

## 2. Vì sao luồng tuần tự không đủ?

Giả sử kho chỉ còn một đơn vị hàng. Mỗi yêu cầu đặt giữ chạy logic:

1. Đọc số hàng còn khả dụng.
2. Nếu còn hàng, tạo một bản ghi giữ hàng.
3. Cập nhật số hàng khả dụng.

Hai yêu cầu có thể xen kẽ như sau:

| Thời điểm | Yêu cầu A | Yêu cầu B |
|---|---|---|
| t1 | Đọc available = 1 | |
| t2 | | Đọc available = 1 |
| t3 | Tạo reservation A | |
| t4 | | Tạo reservation B |
| t5 | Ghi available = 0, commit | |
| t6 | | Ghi available = 0, commit |

Sau cùng, kho không âm nhưng có hai reservation cho một đơn vị hàng. Assertion duy nhất `available >= 0` vẫn đậu. Trong một triển khai khác dùng phép trừ riêng, kết quả có thể là số âm. Phép thử phải bắt được cả hai kiểu sai bằng invariant phản ánh đúng nghiệp vụ.

Ví dụ trên giả định các câu ghi không có điều kiện đủ hàng, ràng buộc hay khóa ngăn lịch này. Hành vi cụ thể còn phụ thuộc database, mức cô lập và cách cập nhật; không nên coi một lịch đọc/ghi là kết quả bắt buộc trên mọi hệ quản trị.

### 2.1. Ba điều dễ nhầm

**Race condition** là kết quả phụ thuộc vào thứ tự xen kẽ của các thao tác. Khi điều kiện được kiểm tra tại một thời điểm nhưng không còn được bảo đảm lúc sử dụng, đó là một dạng lỗi time-of-check to time-of-use, thường gọi là TOCTOU.

**Concurrency regression test** cố định một nguy cơ đã biết thành phép thử có thể lặp lại. Nó ghi rõ trạng thái ban đầu, thao tác cạnh tranh, lịch cần gây áp lực và invariant phải giữ.

**Stress test** tạo nhiều lần thực thi để tìm thêm lịch gây lỗi. Nó hữu ích nhưng một nghìn lượt chạy đều đậu không chứng minh tất cả lịch đều an toàn. Kiểm thử tải đo năng lực và độ trễ cũng không thay thế assertion về nghiệp vụ.

## 3. Viết invariant trước khi viết mã song song

Một invariant tốt mô tả điều luôn phải đúng ở ranh giới quan sát đã chọn. Đừng bắt đầu bằng “gửi 100 request xem có lỗi không”.

### 3.1. Ví dụ invariant cho giữ hàng

Trong fixture đơn giản, không nhập thêm hàng, không xuất hàng và không có reservation hết hạn trong thời gian phép thử:

```text
initialStock = availableStock + tổng(quantity của reservation ACTIVE)
availableStock >= 0
mỗi businessOperationId chỉ tạo tối đa một reservation
```

Reservation và thay đổi kho phải commit nguyên tử trong mô hình ví dụ này. Nếu hệ thống thực tế sử dụng saga, nhiều kho hoặc trạng thái pending, cần định nghĩa invariant tương ứng cho từng trạng thái và một mốc hội tụ có giới hạn. Không áp phương trình đơn giản này vào mô hình có thêm chuyển động hàng mà chưa tính chúng.

Với stock ban đầu bằng 1, hai thao tác hợp lệ dùng **hai operation ID khác nhau** cạnh tranh cùng một SKU:

- Chỉ một đơn vị được giữ thành công.
- Yêu cầu còn lại nhận kết quả nghiệp vụ được định nghĩa, chẳng hạn hết hàng.
- Database có đúng một reservation ACTIVE và available bằng 0.
- Có đúng một sự kiện nghiệp vụ tương ứng trong outbox nếu thiết kế dùng outbox.

Một lỗi timeout không được coi là “đã từ chối vì hết hàng”. Nó không cho biết thao tác có commit hay chưa.

### 3.2. Một số invariant khác

| Nghiệp vụ | Invariant cần kiểm tra khi cạnh tranh |
|---|---|
| Duyệt yêu cầu mua hàng | Một phiên bản chỉ có một chuyển trạng thái duyệt hợp lệ; người tạo không tự duyệt nếu quy tắc cấm |
| Tính giá khi checkout | Giá được chốt theo phiên bản báo giá mà server chấp nhận; không thanh toán theo dữ liệu đã bị thay thế ngoài chính sách |
| Hoàn tiền | Tổng tiền hoàn đã xác nhận không vượt số tiền đủ điều kiện; mỗi operation chỉ có một hiệu lực nghiệp vụ |
| Dùng mã ưu đãi | Mức sử dụng không vượt quota; không sinh thêm quyền lợi khi gửi lại cùng thao tác |
| Hủy và giao hàng | Không cùng đạt hai trạng thái cuối loại trừ nhau; tác dụng phụ tuân theo trạng thái thắng |
| Chuyển chủ sở hữu | Quyền sửa được quyết định theo chính sách phiên bản/quyền tại ranh giới đã xác định |
| Nhận webhook | Một sự kiện hợp lệ được xử lý lại mà không tạo thêm hiệu lực nghiệp vụ |

Đối với tiền, kiểm tra theo đơn vị nhỏ nhất hoặc kiểu số thập phân chính xác của domain; không dùng sai số của số thực để che một khoản hoàn dư.

### 3.3. Định nghĩa ranh giới hiệu lực

Câu “kiểm tra quyền trước khi cập nhật” chưa đủ rõ khi quyền có thể thay đổi đồng thời.

Ví dụ, hệ thống có thể quy định việc đổi chủ sở hữu và sửa đối tượng được sắp thứ tự tại lúc cập nhật có điều kiện theo `version`. Một thao tác sửa chỉ hợp lệ nếu cặp `ownerId/version` dùng để xét quyền còn hiệu lực lúc ghi. Khi đổi chủ thắng trước, thao tác dùng phiên bản cũ phải thất bại hoặc xét quyền lại trên trạng thái mới.

Một chính sách khác có thể cho phép yêu cầu đã được chấp nhận tiếp tục chạy. Khi đó phép thử phải thể hiện rõ mốc chấp nhận. Không dùng kỳ vọng mơ hồ rằng mọi thay đổi quyền đều phải hủy được mọi request đang bay.

Với một đối tượng đơn lẻ, phép thử thường mong kết quả quan sát được tương đương một thứ tự xử lý hợp lệ, dù các request chồng lấn. Điểm nghiệp vụ có hiệu lực có thể là một câu cập nhật có điều kiện, một ràng buộc duy nhất, hoặc commit của transaction giữ khóa phù hợp. Không mặc định đó là thời điểm trả HTTP.

## 4. Xây ma trận các thao tác cạnh tranh

Một phép thử chỉ gửi cùng một endpoint nhiều lần sẽ bỏ sót xung đột giữa các đường xử lý khác nhau. Hãy liệt kê các thao tác cùng đọc hoặc thay đổi một invariant.

| Cặp thao tác | Trạng thái khởi đầu | Lịch cần tạo áp lực | Kết quả phải giữ |
|---|---|---|---|
| reserve / reserve | Kho còn 1 | Hai thao tác cùng tranh đơn vị cuối | Chỉ giữ được một đơn vị |
| approve / approve | SUBMITTED, version v | Hai người duyệt cùng phiên bản | Một lần chuyển trạng thái, một sự kiện duyệt |
| approve / cancel | SUBMITTED | Hai thao tác cùng nhắm một phiên bản | Một trạng thái cuối hợp lệ theo chính sách |
| checkout / sửa giá | Báo giá version v | Giá thay đổi sau bước đọc | Chốt giá v hợp lệ hoặc yêu cầu báo giá lại |
| refund / refund | Còn hạn mức hoàn | Hai operation ID khác nhau | Tổng hoàn không vượt hạn mức |
| xử lý / gửi lại | Operation chưa hoàn tất | Cùng key xuất hiện khi đang xử lý | Một hiệu lực; trạng thái đang xử lý được xử lý rõ ràng |
| đổi owner / sửa dữ liệu | A đang sở hữu | Đổi owner xen giữa xét quyền và ghi | Không ghi trái chính sách quyền đã chọn |
| expire / confirm | Reservation gần hết hạn | Hai thao tác tranh trạng thái ACTIVE | Không vừa hết hạn vừa được xác nhận thành công |

Với mỗi hàng, bổ sung các chiều thật sự liên quan:

- Cùng tài khoản, hai tài khoản cùng tenant, và chủ thể không có quyền.
- Cùng đối tượng và hai đối tượng độc lập để phát hiện khóa quá rộng.
- Cùng key/cùng payload, cùng key/khác payload, khác key/cùng mục tiêu nghiệp vụ.
- Cùng instance và hai instance riêng nếu hệ thống chạy nhiều replica.
- Chạy lần đầu, retry sau xung đột, và retry khi lần đầu đã commit nhưng mất phản hồi.

Không nhất thiết lấy tích Descartes của mọi chiều. Chọn theo invariant bị đe dọa và đường xử lý đã từng lỗi. Hai nhân viên duyệt cùng yêu cầu kiểm tra cạnh tranh; một nhân viên không được quyền duyệt kiểm tra thêm việc cơ chế retry có vô tình bỏ qua phân quyền hay không.

## 5. Tái hiện lịch xen kẽ có chủ đích

### 5.1. Điểm xuất phát đồng thời chỉ tạo cơ hội

Một `CountDownLatch` cho hai worker khởi chạy gần nhau giúp gây áp lực lên database. Nó **không bảo đảm** cả hai đã đọc cùng dữ liệu cũ. Scheduler, connection pool và tốc độ truy vấn có thể khiến mọi lần chạy vẫn diễn ra tuần tự.

Phép thử cho một lỗi TOCTOU đã biết nên có một điểm đồng bộ test-only ở đúng khoảng nguy hiểm:

```text
A: đọc available = 1 -> tới hook "sau đọc, trước ghi" -> chờ
B: đọc available = 1 -> tới hook "sau đọc, trước ghi" -> chờ
Test: xác nhận cả hai đã tới hook -> cho cả hai tiếp tục
Test: thu kết quả -> đọc trạng thái đã commit -> kiểm tra invariant
```

Trong bản lỗi có đọc kiểm tra rồi ghi không bảo vệ, lịch này làm cửa sổ lỗi trở nên có thể lặp lại. Khi sửa sang câu cập nhật nguyên tử, thiết kế điểm đồng bộ phải phản ánh đường xử lý mới; không giữ một hook buộc kiến trúc đúng phải thực hiện lại cách đọc cũ.

### 5.2. Không tạo deadlock bằng chính test hook

Nếu A đang giữ khóa hàng còn B phải chờ khóa đó, đặt barrier bắt cả A lẫn B đến một điểm **sau khi lấy khóa** sẽ làm A chờ B mãi. Đây là lỗi của harness, không tự động là lỗi nghiệp vụ.

Với cách sửa dùng khóa:

1. Cho A lấy khóa và dừng tại một hook chỉ dành cho A.
2. Cho B bắt đầu thử thao tác trên cùng đối tượng.
3. Thu tín hiệu đủ để biết B đã được gửi vào đường xử lý; chỉ khẳng định nó đang chờ khóa khi có bằng chứng thích hợp từ adapter hoặc database.
4. Cho A tiếp tục và commit.
5. Chờ B hoàn tất, rồi kiểm tra B xử lý trên trạng thái hợp lệ sau A.

Để tránh phụ thuộc sâu vào chi tiết khóa, có thể giữ một phép thử cạnh tranh ở ranh giới service và dùng phép thử tích hợp database riêng cho cơ chế tranh khóa. Mọi điểm chờ đều phải có timeout và phải được giải phóng trong `finally`.

### 5.3. Quy tắc cho điểm đồng bộ

- Hook chỉ tồn tại trong fixture, adapter hoặc dependency dành cho test; không mở endpoint công khai để dừng transaction.
- Không mock bỏ transaction, điều kiện cập nhật, unique constraint hay đường kiểm tra quyền mà phép thử cần xác minh.
- Nếu cần thấy lỗi trên hai replica, cơ chế điều phối phải bao phủ cả hai; barrier trong JVM không tự đồng bộ với process khác.
- Tín hiệu “đã tới bước X” phải gắn với bước thật, không suy từ việc đã sleep một khoảng thời gian.
- Ghi rõ lịch nào đã được tạo và lịch nào chỉ được gây áp lực.

`Thread.sleep(100)` thường khiến test chậm và vẫn không bảo đảm A đã đọc xong trước B. Sleep có thể dùng làm khoảng polling có giới hạn cho hệ thống bất đồng bộ, nhưng điều kiện kết thúc phải là một trạng thái quan sát được.

## 6. Ví dụ Java: hai request tranh sản phẩm cuối

Ví dụ dưới dùng Java 17 và JUnit 5 để minh họa cấu trúc một phép thử tích hợp. Các kiểu fixture là hợp đồng cần nối với ứng dụng thật; đoạn mã không bao gồm repository, cấu hình database hay HTTP client.

### 6.1. Helper khởi chạy hai tác vụ và giữ nguyên lỗi

```java
import java.time.Duration;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

final class ConcurrentCalls {
    record Pair<T>(T first, T second) {}

    static <T> Pair<T> runTwo(
            Callable<T> first,
            Callable<T> second,
            Duration timeout) throws Exception {

        if (timeout.isZero() || timeout.isNegative()) {
            throw new IllegalArgumentException("timeout must be positive");
        }

        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);
        long deadline = System.nanoTime() + timeout.toNanos();
        Future<T> a = null;
        Future<T> b = null;

        try {
            a = pool.submit(gated(first, ready, start, deadline));
            b = pool.submit(gated(second, ready, start, deadline));

            if (!ready.await(remaining(deadline), TimeUnit.NANOSECONDS)) {
                throw new TimeoutException("Workers did not become ready");
            }
            start.countDown();

            T firstResult = a.get(remaining(deadline), TimeUnit.NANOSECONDS);
            T secondResult = b.get(remaining(deadline), TimeUnit.NANOSECONDS);
            return new Pair<>(firstResult, secondResult);
        } finally {
            start.countDown();
            if (a != null) a.cancel(true);
            if (b != null) b.cancel(true);
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Workers still running; do not reuse their fixture");
            }
        }
    }

    private static <T> Callable<T> gated(
            Callable<T> action,
            CountDownLatch ready,
            CountDownLatch start,
            long deadline) {

        return () -> {
            ready.countDown();
            if (!start.await(remaining(deadline), TimeUnit.NANOSECONDS)) {
                throw new TimeoutException("Start gate was not released");
            }
            return action.call();
        };
    }

    private static long remaining(long deadline) throws TimeoutException {
        long nanos = deadline - System.nanoTime();
        if (nanos <= 0) {
            throw new TimeoutException("Concurrent test deadline exceeded");
        }
        return nanos;
    }
}
```

Helper này chờ kết quả của cả hai tác vụ trong một ngân sách thời gian chung. Ngoại lệ từ worker được truyền qua `Future.get`; nó không biến exception bất kỳ thành kết quả “thất bại nghiệp vụ”. Nếu cần chẩn đoán đầy đủ lỗi của cả hai phía, harness thực tế có thể thu kết quả và ngoại lệ của từng worker rồi báo chung.

Lệnh `cancel(true)` chỉ yêu cầu ngắt luồng; không bảo đảm hủy được JDBC query hay request phía server. Cần thêm timeout kết nối, câu lệnh, lock và request phù hợp với môi trường kiểm thử. Nếu worker không dừng, phải đánh dấu fixture không thể dùng lại và xử lý tài nguyên của lần chạy đó. Không xóa dữ liệu trong khi tác vụ cũ vẫn có thể commit.

### 6.2. Hợp đồng fixture và assertion

Quy ước của ví dụ:

- Hai người mua hợp lệ cùng tenant, mỗi người thao tác trên tài nguyên thuộc quyền của mình.
- Hai lệnh dùng operation ID và idempotency key khác nhau để thật sự tranh kho.
- `reserve` chỉ trả `CREATED` sau khi transaction đã commit.
- `OUT_OF_STOCK` là kết quả nghiệp vụ cuối cùng trong hợp đồng ví dụ; lỗi hạ tầng phải ném exception.
- Snapshot đọc từ nguồn dữ liệu có thẩm quyền sau khi hai lời gọi kết thúc, bằng transaction đọc mới.

```java
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.List;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

enum ReserveStatus { CREATED, OUT_OF_STOCK }

record ReserveCommand(
        String buyerId, String sku, String operationId, String idempotencyKey) {}

record ReserveResult(ReserveStatus status, String reservationId) {}

record InventorySnapshot(
        int initialStock,
        int availableStock,
        int activeReservations,
        int activeQuantity,
        int reservationCreatedEvents) {}

interface InventoryFixture extends AutoCloseable {
    String sku();
    String buyerA();
    String buyerB();
    ReserveResult reserve(ReserveCommand command) throws Exception;
    InventorySnapshot committedSnapshot() throws Exception;
    boolean reservationBelongsTo(String reservationId, String buyerId)
            throws Exception;
    @Override void close() throws Exception;
}

abstract class LastItemConcurrencyTest {
    // Ứng dụng cung cấp subclass và fixture tích hợp database thật.
    // Mỗi fixture tạo namespace dữ liệu riêng, stock ban đầu bằng 1.
    protected abstract InventoryFixture newFixture() throws Exception;

    @Test
    void twoBuyersCannotReserveTheSameLastUnit() throws Exception {
        try (InventoryFixture fixture = newFixture()) {
            ReserveCommand a = new ReserveCommand(
                    fixture.buyerA(), fixture.sku(),
                    UUID.randomUUID().toString(), UUID.randomUUID().toString());
            ReserveCommand b = new ReserveCommand(
                    fixture.buyerB(), fixture.sku(),
                    UUID.randomUUID().toString(), UUID.randomUUID().toString());

            var pair = ConcurrentCalls.runTwo(
                    () -> fixture.reserve(a),
                    () -> fixture.reserve(b),
                    Duration.ofSeconds(10));

            List<ReserveResult> results = List.of(pair.first(), pair.second());
            assertEquals(1L, results.stream()
                    .filter(r -> r.status() == ReserveStatus.CREATED).count());
            assertEquals(1L, results.stream()
                    .filter(r -> r.status() == ReserveStatus.OUT_OF_STOCK).count());

            InventorySnapshot state = fixture.committedSnapshot();
            assertAll(
                    () -> assertEquals(1, state.initialStock()),
                    () -> assertEquals(0, state.availableStock()),
                    () -> assertEquals(1, state.activeReservations()),
                    () -> assertEquals(1, state.activeQuantity()),
                    () -> assertEquals(
                            state.initialStock(),
                            state.availableStock() + state.activeQuantity()),
                    () -> assertEquals(1, state.reservationCreatedEvents())
            );

            if (pair.first().status() == ReserveStatus.CREATED) {
                assertNotNull(pair.first().reservationId());
                assertTrue(fixture.reservationBelongsTo(
                        pair.first().reservationId(), fixture.buyerA()));
            } else {
                assertNotNull(pair.second().reservationId());
                assertTrue(fixture.reservationBelongsTo(
                        pair.second().reservationId(), fixture.buyerB()));
            }
        }
    }
}
```

`activeReservations` đếm bản ghi, còn `activeQuantity` cộng số lượng. Chúng đều bằng 1 trong fixture này nhưng không thể hoán đổi khi một reservation có quantity lớn hơn 1. Việc kiểm tra chủ sở hữu cũng giúp phát hiện lỗi trả nhầm kết quả giữa hai request.

Fixture phải ánh xạ danh tính sang security context thực sự của từng request. Một trường `buyerId` trong command không tự chứng minh caller đã được xác thực; nếu API không cho client tự chọn người mua thì adapter test cũng không được vượt qua quy tắc đó.

Đây là phép thử **xuất phát đồng thời**, chưa phải tái hiện xác định lịch “cả hai cùng đọc 1”. Khi hồi quy cho lỗi đó, bổ sung hook thích hợp theo mục 5 hoặc thêm một test database chuyên biệt. Không ghi nhận một test start-gate đã chứng minh mọi lịch xen kẽ.

## 7. Ghép phép thử với transaction và cơ chế bảo vệ thật

Một cách triển khai giữ hàng trong một database có thể dùng cập nhật có điều kiện:

```sql
BEGIN;

UPDATE inventory
SET available = available - :quantity
WHERE tenant_id = :tenant_id
  AND sku = :sku
  AND :quantity > 0
  AND available >= :quantity;

-- Adapter kiểm tra affected_rows.
-- Nếu bằng 0: kết thúc theo nhánh thất bại nghiệp vụ thích hợp.
-- Nếu bằng 1: mới tạo reservation và outbox trong cùng transaction.

INSERT INTO reservation (
    tenant_id, operation_id, buyer_id, sku, quantity, status
) VALUES (
    :tenant_id, :operation_id, :buyer_id, :sku, :quantity, 'ACTIVE'
);

INSERT INTO outbox (
    tenant_id, event_id, operation_id, event_type
) VALUES (
    :tenant_id, :event_id, :operation_id, 'ReservationCreated'
);

COMMIT;
```

Đây là phác thảo luồng, không phải script chạy nguyên xi: placeholder và cách lấy số dòng ảnh hưởng phụ thuộc adapter. Khi không cập nhật được hàng, code không được tiếp tục hai câu INSERT. Trong fixture bảo đảm SKU tồn tại và caller hợp lệ, không đủ hàng có thể là kết quả mong đợi; ở hệ thống thật, 0 dòng còn có thể do sai tenant, không tìm thấy hoặc điều kiện khác.

Điều kiện cập nhật phải đi cùng ràng buộc phù hợp cho operation ID và transaction bao quanh toàn bộ thay đổi. Nếu INSERT reservation lỗi, thay đổi kho phải rollback. Nếu dùng unique constraint để chống trùng, phạm vi khóa duy nhất phải khớp định danh nghiệp vụ, chẳng hạn tenant và operation ID.

Phép thử tích hợp cần giữ nguyên:

- Loại database, mức cô lập và ràng buộc liên quan với môi trường đích.
- Transaction riêng cho mỗi yêu cầu cạnh tranh, cùng truy cập một tập dữ liệu đã commit.
- Connection pool đủ cho số worker và kết nối điều phối đang cần; hai worker dùng chung một connection không thể đại diện hai transaction cạnh tranh độc lập.
- Cơ chế retry thật đối với optimistic conflict, serialization failure hoặc deadlock nếu ứng dụng có hỗ trợ.

Không bọc cả test trong một transaction cha rồi giả định worker khác nhìn thấy dữ liệu seed chưa commit. Không chia sẻ `EntityManager`, persistence context hoặc transaction gắn với thread giữa các worker. Bước đọc kết quả phải tránh cache hoặc read replica trễ làm sai phép đo.

Một annotation transaction hoặc mức cô lập cao không tự chứng minh invariant đúng. Với serialization failure, ứng dụng vẫn cần xử lý retry hoặc trả kết quả đã định nghĩa. Nếu tự retry, phải chạy lại đủ phần đọc trạng thái, xét quyền và kiểm tra nghiệp vụ trên phiên bản mới.

## 8. Kiểm thử idempotency dưới cạnh tranh

Idempotency trả lời câu hỏi “gửi lại cùng một ý định có tạo thêm hiệu lực không?”. Nó không tự giải quyết câu hỏi “hai ý định khác nhau có vượt giới hạn chung không?”.

Ví dụ hai yêu cầu hoàn tiền dùng hai key khác nhau vẫn phải tranh cùng hạn mức hoàn. Ngược lại, hai request cùng key có thể là cùng một thao tác và cần trả cùng kết quả hoặc trạng thái đang xử lý theo hợp đồng.

### 8.1. Những trường hợp phải tách riêng

| Trường hợp | Dữ liệu gửi | Kỳ vọng |
|---|---|---|
| Gửi lại đồng thời | Cùng scope, key, payload | Một hiệu lực nghiệp vụ; cùng kết quả cuối hoặc trạng thái đang xử lý được định nghĩa |
| Tái sử dụng key sai | Cùng scope và key, khác payload có ý nghĩa | Từ chối xung đột; không thực hiện payload thứ hai |
| Hai ý định riêng | Khác key, cùng đối tượng | Mỗi ý định vẫn phải tuân invariant chung |
| Trùng chuỗi key ở scope khác | Hai tenant hoặc hai operation scope hợp lệ | Không lấy kết quả của scope này trả cho scope kia |
| Mất phản hồi | Lần đầu commit, client không nhận được kết quả rồi retry | Không tạo thêm reservation, khoản hoàn hoặc sự kiện nghiệp vụ |
| Hai instance | Cùng thao tác đi vào hai replica | Không phụ thuộc khóa hoặc bộ nhớ riêng của một process |

Scope phải được định nghĩa rõ, ví dụ `tenant + operationType + idempotencyKey`, có thể kèm principal tùy hợp đồng. Fingerprint nên bao gồm các trường mang ý nghĩa nghiệp vụ sau khi chuẩn hóa theo chính sách. Không tự coi mọi byte khác nhau là ý định khác nhau, cũng không bỏ qua trường quantity, đối tượng hoặc số tiền.

### 8.2. Lịch kiểm thử khi request đầu chưa hoàn tất

```text
1. A nhận key K, xác thực và bắt đầu xử lý.
2. Dừng A tại một điểm mà thao tác chưa hoàn tất.
3. B gửi cùng key K và cùng payload.
4. Cho A tiếp tục.
5. Thu kết quả cả hai.
6. Nếu B nhận trạng thái đang xử lý, dùng đường tra cứu/retry được phép
   để quan sát kết quả cuối trong deadline.
7. Kiểm tra một operation, một reservation và một event nghiệp vụ.
```

Điểm dừng phụ thuộc thiết kế. Nếu bản ghi idempotency nằm trong transaction chưa commit, B có thể đang chờ unique constraint thay vì đọc được trạng thái “đang xử lý”. Phép thử phải quan sát đúng cơ chế thật. Đừng buộc cả hai request đều phải đi qua cùng một điểm sau khi một phía đã giữ khóa.

Các assertion quan trọng gồm:

- Kết quả cuối cùng tham chiếu cùng định danh nghiệp vụ và payload hợp lệ.
- Thao tác chỉ tiêu thụ quota, số dư hoặc tồn kho một lần.
- Không có operation treo vĩnh viễn ở trạng thái PROCESSING trong kịch bản có phục hồi.
- Bản ghi idempotency không chứa kết quả của tenant hay người dùng khác.
- Caller vẫn phải có quyền truy cập kết quả được trả về theo chính sách hiện tại.

Không mặc định cả hai phản hồi phải cùng HTTP status. Một hợp đồng có thể trả kết quả đã hoàn thành cho một phía và trạng thái đang xử lý cho phía còn lại. Assertion phải chặt ở hiệu lực nghiệp vụ và tuân theo hợp đồng API cụ thể.

### 8.3. Commit thành công nhưng phản hồi bị mất

Một phép thử hồi quy riêng cần gây lỗi **sau commit nhưng trước khi client nhận kết quả**:

1. Gửi yêu cầu với key K.
2. Xác nhận bằng tín hiệu nội bộ đáng tin cậy rằng transaction đã commit.
3. Cắt hoặc làm mất phản hồi tại adapter/proxy test.
4. Client gửi lại cùng key và payload.
5. Đọc kết quả cuối và kiểm tra không có hiệu lực mới.

Nếu chỉ gây exception trước commit, bạn đang thử rollback, chưa kiểm tra tình huống kết quả đã có nhưng client chưa biết. Với hệ thống ngoài, giữ nguyên external idempotency key khi retry nếu giao thức đó là phần của thiết kế.

## 9. Hồi quy state machine và quyền theo đối tượng

### 9.1. Hai người cùng phê duyệt

Đặt yêu cầu ở trạng thái SUBMITTED, version 7. Hai người duyệt hợp lệ cùng gửi quyết định dựa trên version này.

Một cập nhật có điều kiện có thể yêu cầu:

```sql
UPDATE approval_request
SET status = 'APPROVED',
    approved_by = :reviewer_id,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND id = :request_id
  AND status = 'SUBMITTED'
  AND version = :expected_version;
```

Câu SQL minh họa kiểm soát trạng thái và phiên bản, **chưa thể hiện đầy đủ phân quyền**. Quyền của reviewer, quy tắc không tự duyệt và các thuộc tính liên quan vẫn phải được kiểm tra theo chính sách, với cơ chế bảo vệ khỏi thay đổi cạnh tranh nếu cần.

Sau hai lời gọi, phép thử nên xác nhận:

- Một lần chuyển SUBMITTED sang APPROVED theo hợp đồng ví dụ.
- Version tăng đúng một lần; người duyệt được ghi nhận thuộc tập caller hợp lệ.
- Có một sự kiện `ApprovalGranted` cho chuyển trạng thái đó.
- Không thực thi hai lần bước tiếp theo như cấp quyền chi tiêu.
- Yêu cầu thua nhận stale version/conflict, hoặc kết quả đã duyệt nếu hợp đồng cho phép việc đó.

Nếu nghiệp vụ yêu cầu hai cấp duyệt, invariant phải tính các cấp và danh tính độc lập; không áp quy tắc “một người duyệt” của ví dụ lên quy trình đó.

### 9.2. Duyệt và sửa dữ liệu được duyệt

Một lỗi đáng chú ý là duyệt báo giá hoặc đề nghị thanh toán rồi một yêu cầu khác sửa số tiền ở khoảng giữa.

Kịch bản:

```text
A đọc yêu cầu version 7, số tiền 1.000.000, chuẩn bị duyệt.
B sửa số tiền thành 10.000.000 và commit version 8.
A tiếp tục thao tác duyệt dựa trên version 7.
```

Kỳ vọng có thể là A thất bại vì phiên bản cũ, hoặc bản sửa của B làm mất hiệu lực phê duyệt và đưa quy trình trở về trạng thái cần duyệt lại. Kết quả “số tiền 10.000.000 đã được duyệt bởi quyết định chỉ xem 1.000.000” vi phạm ràng buộc giữa dữ liệu và quyết định.

Phép thử phải đọc cả phiên bản dữ liệu đã duyệt, trạng thái hiện tại và tác dụng phụ. Chỉ nhìn `status = APPROVED` không đủ để biết đúng nội dung đã được phê duyệt.

### 9.3. Đổi quyền xen giữa kiểm tra và cập nhật

Với chính sách quyền gắn phiên bản như mục 3:

1. A đang là owner của đối tượng version 12, gửi lệnh sửa.
2. Dừng lệnh của A sau khi đọc trạng thái dùng để xét quyền.
3. B thực hiện thao tác đổi owner hợp lệ sang C, commit version 13.
4. Cho A tiếp tục.
5. Xác nhận A không ghi dựa trên quyền của version 12; nếu retry, phải đọc lại và xét quyền lại.

B phải có quyền đổi owner trong fixture. Không dùng một caller tùy ý để tạo dữ liệu mà ứng dụng thật không thể tạo qua đường đang kiểm thử.

Khi có retry tự động, thêm assertion rằng hệ thống không chỉ làm mới `version` rồi tiếp tục với quyết định phân quyền cũ. Đây là điểm giao giữa optimistic locking và object-level authorization.

## 10. Kiểm tra tác dụng phụ và xử lý bất đồng bộ

Giữ invariant trong database chính chưa đủ nếu hai worker cùng gửi lệnh thanh toán hoặc cùng cấp một quyền lợi ở hệ thống ngoài.

Tách rõ các đơn vị đếm:

| Đơn vị | Ý nghĩa |
|---|---|
| Request đầu vào | Có thể nhiều lần do người dùng hoặc retry |
| Operation nghiệp vụ | Ý định được định danh theo hợp đồng |
| Event logic | Sự kiện của một chuyển trạng thái đã commit |
| Lần giao thông điệp | Có thể lặp khi broker hoặc publisher retry |
| Hiệu lực bên ngoài | Khoản thu/hoàn, quyền truy cập hoặc thay đổi tại hệ thống nhận |

Một outbox event có thể được giao nhiều lần trong mô hình at-least-once. Vì vậy “chỉ một HTTP call tới bên nhận” không phải assertion đúng cho mọi thiết kế. Cần kiểm tra một event logic ổn định và một hiệu lực nghiệp vụ tại bên nhận thông qua deduplication hoặc idempotency phù hợp.

### 10.1. Các ranh giới lỗi cần mô phỏng

- Transaction tạo operation rollback: không còn outbox đã commit cho operation đó.
- Operation và outbox đã commit, publisher chưa gửi: sau phục hồi, event được xử lý trong deadline.
- Publisher gửi thành công nhưng chưa đánh dấu đã gửi: giao lại không tạo hiệu lực lần hai.
- Hai consumer nhận cùng event đồng thời: cơ chế dedupe và thay đổi nghiệp vụ phải phối hợp an toàn.
- Hệ thống ngoài đã thực hiện nhưng phản hồi bị mất: retry/reconcile không tạo hiệu lực bổ sung.

Không thể dùng rollback database cục bộ để tự động thu hồi một cuộc gọi mạng đã có hiệu lực. Phép thử cần phản ánh thiết kế outbox, idempotency phía nhận, trạng thái trung gian hoặc cơ chế bù thực tế.

### 10.2. Assertion theo điều kiện hội tụ

Với tác vụ bất đồng bộ, thay vì chờ cố định hai giây rồi kiểm tra:

```text
Trong deadline:
    đọc trạng thái operation theo correlation ID
    đọc hiệu lực tại adapter hệ thống ngoài
    nếu đã đến trạng thái cuối đúng: kết thúc chờ
    nếu có trạng thái lỗi không được phép: fail ngay
    nếu chưa hội tụ: chờ một khoảng polling ngắn rồi kiểm tra lại

Hết deadline mà chưa hội tụ: fail và xuất dấu vết của operation.
```

Đạt một giá trị đúng trong khoảnh khắc chưa đủ nếu vẫn còn công việc có thể tạo bản sao. Trước khi kết luận, cần hoàn tất nhóm worker đã khởi tạo hoặc có bằng chứng đường xử lý cho operation đã đến trạng thái cuối và dedupe có hiệu lực. Trong fixture kiểm thử có thể drain hàng đợi theo correlation ID rồi xác minh lại kết quả.

## 11. Từ lỗi đã xảy ra đến test hồi quy lâu dài

Một test hồi quy hữu ích cần giữ được bản chất lỗi mà không gắn cứng vào chi tiết không còn ý nghĩa.

### Bước 1: Viết phát biểu lỗi bằng ngôn ngữ nghiệp vụ

Ví dụ: “Hai request hoàn tiền độc lập cùng đọc hạn mức còn lại và tạo hai khoản hoàn vượt tổng tiền được phép”.

Thông tin tối thiểu gồm invariant, dữ liệu ban đầu, chủ thể và phạm vi quyền, hai thao tác, cùng kết quả sai đã quan sát. Không chỉ ghi “race ở hàm refund”.

### Bước 2: Thu nhỏ fixture

Dùng một giao dịch với hạn mức hoàn còn 100 đơn vị và hai yêu cầu hoàn 80 đơn vị, có operation ID khác nhau. Không cần dữ liệu của hàng nghìn giao dịch khác để kiểm tra invariant này.

Hai khoản 80 cùng thành công phải làm test thất bại. Một thành công và một từ chối vượt hạn mức có thể là kết quả hợp lệ. Nếu hệ thống cho hoàn một phần tự động, phải đổi kỳ vọng theo chính sách đó.

### Bước 3: Chọn lịch cần tái hiện

Nếu lỗi bắt nguồn từ hai lần đọc cùng hạn mức cũ, dùng hook sau đọc trước ghi trong bản tái hiện. Ghi rõ điều kiện đồng bộ và timeout. Với cách sửa dùng cập nhật nguyên tử, giữ phép thử invariant ở ranh giới phù hợp và bổ sung kiểm tra cơ chế database khi cần.

### Bước 4: Chứng minh test có khả năng phát hiện lỗi

Trên bản lỗi đã biết hoặc một biến thể cục bộ được kiểm soát, cùng lịch thử phải làm invariant thất bại. Trên bản sửa, phép thử phải đậu với kết quả nghiệp vụ đúng.

Không sửa code production hoặc bỏ ràng buộc trong môi trường dùng chung chỉ để chứng minh test. Việc chạy trên bản lỗi cần workspace và database kiểm thử cô lập. Một test luôn đậu cả khi cơ chế bảo vệ bị bỏ có thể đang không đi qua cửa sổ lỗi.

### Bước 5: Bổ sung các trường hợp gần kề có ý nghĩa

Ví dụ, sau lỗi hoàn tiền, thêm cùng key, khác key, mất phản hồi và hai instance nếu những đường này dùng chung cơ chế bảo vệ. Không biến một test nhỏ thành bộ ngẫu nhiên khó giải thích.

### Bước 6: Lưu dấu vết có thể tái hiện

Mỗi lần thất bại nên có:

- Tên invariant và mã kịch bản.
- Seed ngẫu nhiên nếu có; operation ID, correlation ID và namespace fixture.
- Thứ tự các mốc trước/sau điểm đồng bộ của từng worker.
- Kết quả hoặc ngoại lệ của từng request, số lần retry.
- Snapshot trước và sau từ nguồn có thẩm quyền.
- Version, số dòng cập nhật, event ID, trạng thái outbox/dedupe liên quan.

Thời gian trên hai process khác nhau không tự tạo được một thứ tự toàn cục đáng tin cậy. Ưu tiên các quan hệ nhân quả như “B commit xong rồi gate A mới mở”, cùng sequence cục bộ và correlation ID. Không ghi token, khóa bí mật hay toàn bộ dữ liệu cá nhân vào log test.

## 12. Tổ chức bộ kiểm thử trong CI

Một cấu trúc thực tế có thể gồm các lớp bổ sung cho nhau:

| Lớp | Mục đích | Nơi chạy phù hợp |
|---|---|---|
| Unit/domain | Kiểm tra invariant và chuyển trạng thái trên một luồng | Mỗi thay đổi code |
| Tích hợp có điều phối | Tái hiện lịch nguy hiểm qua transaction/database thật | Các thay đổi liên quan và nhánh tích hợp |
| Nhiều instance | Kiểm tra giả định về khóa cục bộ, dedupe, worker | Pipeline có môi trường tương ứng |
| Stress với seed | Mở rộng lịch và thứ tự thao tác để tìm lỗi mới | Định kỳ hoặc theo phạm vi thay đổi |

Tần suất cụ thể tùy ngân sách CI và mức rủi ro. Khi đã có lỗi nghiêm trọng với phép thử xác định, nên ưu tiên đưa kịch bản đó vào đường kiểm tra thường xuyên.

### 12.1. Giữ fixture độc lập

- Mỗi test dùng tenant, SKU, operation ID hoặc schema riêng theo khả năng hệ thống.
- Chỉ dọn dữ liệu thuộc namespace của test đó.
- Commit dữ liệu khởi tạo trước khi mở worker.
- Bảo đảm test harness đủ connection cho lịch dự kiến; tách phép thử cạn pool thành kịch bản khác.
- Chỉ cleanup sau khi biết tác vụ phía client, server và worker liên quan đã dừng hoặc được cô lập.
- Với kịch bản hết hạn, dùng clock có kiểm soát ở các thành phần cần thiết; không phụ thuộc sát ranh giới giây của đồng hồ thật.

Chạy test song song trong CI không thay thế việc tạo cạnh tranh có chủ đích bên trong một test. Nếu hai test tình cờ sửa cùng fixture, đó thường là nhiễu giữa test.

### 12.2. Không biến flaky test thành “xanh”

Những cách sau làm mất giá trị hồi quy:

- Retry cả test đến khi đậu mà không giữ kết quả lần thất bại.
- Bắt mọi exception và tính là request bị từ chối hợp lệ.
- Nới deadline vô hạn để che deadlock.
- Tăng số request thay cho việc đặt đúng điểm điều phối.
- Bỏ assertion tác dụng phụ vì phản hồi HTTP trông hợp lệ.

Khi test thất bại, phân loại theo bằng chứng: invariant bị phá, lỗi hạ tầng, lịch điều phối không đạt, worker rò rỉ hay timeout chưa rõ nguyên nhân. Cả nhóm cuối vẫn cần xử lý; chúng không phải lý do tự động đánh dấu nghiệp vụ an toàn.

### 12.3. Stress test có thể tái lập

Sau các kịch bản xác định, có thể sinh chuỗi reserve/cancel/confirm với seed, số worker và số bước giới hạn. Lưu lịch thực thi quan sát được và kiểm tra invariant sau các mốc thích hợp.

Seed chỉ tái tạo dữ liệu và lựa chọn thao tác; nó không bảo đảm scheduler hay database tái hiện cùng lịch. Khi tìm được lỗi, thu nhỏ thành một kịch bản điều phối cụ thể rồi bổ sung vào bộ hồi quy.

Nếu kiểm tra lịch sử thao tác theo mô hình tuần tự, cần ghi thời điểm gọi/trả và hiệu lực được quan sát đủ để đánh giá có tồn tại một thứ tự hợp lệ hay không. Với hệ thống nhất quán cuối cùng, dùng mô hình được định nghĩa cho hệ thống đó; không tự yêu cầu mọi quan sát đều nhất quán tức thời.

## 13. Những assertion dễ tạo cảm giác an toàn sai

| Assertion hoặc cách làm | Điều bị bỏ sót | Cách kiểm tra tốt hơn |
|---|---|---|
| “Stock không âm” | Hai reservation nhưng lần ghi sau đè stock | Kiểm tra bảo toàn stock và tổng quantity ACTIVE |
| “Có một phản hồi thành công” | Request báo lỗi vẫn commit tác dụng phụ | Đọc dữ liệu cuối và hiệu lực theo operation |
| “Hai request đều trả 200” | Có thể đã tạo hai operation | Kiểm tra định danh và số hiệu lực; diễn giải theo hợp đồng |
| “Có unique key là đủ” | Key đặt sai scope hoặc nhiều key vượt cùng hạn mức | Kiểm tra cả scope dedupe và invariant chung |
| “Lock trong service đã ngăn race” | Lock chỉ có tác dụng trong một process | Chạy hai instance qua kho dữ liệu chung |
| “Test database in-memory đậu” | Khóa, isolation, constraint khác môi trường đích | Chạy tích hợp bằng database tương ứng |
| “Retry là an toàn” | Retry dùng lại giá, quyền hoặc trạng thái cũ | Buộc xung đột rồi kiểm tra đánh giá lại toàn bộ điều kiện |
| “Tất cả request đã trả lời” | Consumer phía sau vẫn đang tạo hiệu lực | Chờ trạng thái cuối và kiểm tra pipeline liên quan |
| “Timeout tính là request thua” | Request có thể commit sau deadline | Fail, truy vết trạng thái và cô lập tác vụ còn chạy |
| “Barrier luôn làm test xác định” | Barrier đặt trong khóa khiến test tự kẹt | Đặt điểm đồng bộ theo lịch và cơ chế bảo vệ thật |

## 14. Bài thực hành: chống hoàn tiền vượt hạn mức

Xây fixture với một giao dịch đã thanh toán 100.000 đơn vị tiền nhỏ nhất, chưa hoàn tiền. Chính sách không cho hoàn một phần tự động; mỗi lệnh yêu cầu đúng số tiền hoặc bị từ chối.

### Tình huống A: hai ý định hoàn độc lập

Hai người có quyền hoàn tiền cùng gửi lệnh hoàn 80.000, dùng hai operation ID và hai key khác nhau.

Kỳ vọng:

- Chỉ một operation hoàn 80.000 có hiệu lực.
- Operation còn lại bị từ chối do không đủ hạn mức, theo hợp đồng.
- Tổng hoàn đã xác nhận bằng 80.000 và không vượt 100.000.
- Hệ thống ngoài có một hiệu lực hoàn tương ứng.

Nếu ứng dụng giữ hạn mức ở trạng thái pending trước khi gọi hệ thống ngoài, còn phải kiểm tra tổng phần đã xác nhận cộng phần đang giữ không vượt hạn mức. Chỉ cộng phần đã xác nhận có thể bỏ sót hai khoản pending đều sẽ được thực hiện.

### Tình huống B: cùng một ý định bị gửi hai lần

Hai request cùng key và payload yêu cầu hoàn 80.000. Một request bị làm mất phản hồi sau khi hoàn tiền có hiệu lực.

Kỳ vọng:

- Retry tìm về đúng operation cũ và kết quả cuối hợp lệ.
- Không hoàn thêm 80.000.
- Event logic và thông tin dedupe gắn đúng operation.
- Nếu có nhiều lần gọi hệ thống ngoài, tất cả dùng cơ chế idempotency đúng và chỉ tạo một hiệu lực.

### Tình huống C: quyền thay đổi trong lúc retry

Cho lệnh hoàn gặp xung đột phiên bản, sau đó thu hồi quyền của caller trước khi lần retry xét quyền. Định nghĩa chính sách là mọi lần thử ghi mới phải dùng quyền còn hiệu lực.

Kỳ vọng:

- Lần retry không tiếp tục bằng kết quả phân quyền cũ.
- Không có khoản hoàn mới được tạo sau quyết định từ chối.
- Nếu trước đó đã có hiệu lực, đường tra cứu/trả kết quả cũ phải theo chính sách truy cập kết quả; không tạo thao tác mới để “thử lại”.

Khi làm bài, nộp mô tả invariant, ma trận lịch cạnh tranh, vị trí đồng bộ, assertion dữ liệu/tác dụng phụ và dấu vết một lần chạy thất bại trên bản lỗi cô lập. Chỉ nộp đoạn code tạo thread chưa đủ để thể hiện đã kiểm tra được quy tắc nghiệp vụ.

## 15. Checklist hoàn thành một test hồi quy cạnh tranh

- [ ] Invariant được viết bằng dữ liệu và trạng thái nghiệp vụ có thể quan sát.
- [ ] Chủ thể, tenant, quyền theo đối tượng và phiên bản đầu vào được thiết lập rõ.
- [ ] Phân biệt cùng ý định bị gửi lại với hai ý định độc lập.
- [ ] Lịch nguy hiểm được mô tả; mức bảo đảm của cách điều phối được ghi đúng.
- [ ] Worker dùng request/transaction độc lập và cùng tranh tài nguyên dự kiến.
- [ ] Điểm đồng bộ không yêu cầu một worker đi xuyên qua khóa đang bị worker khác giữ.
- [ ] Mọi chờ đợi có deadline; exception và timeout không bị đổi thành kết quả nghiệp vụ.
- [ ] Dữ liệu cuối được đọc sau commit từ nguồn có thẩm quyền.
- [ ] Kiểm tra cả số lượng, tổng giá trị, version, chủ sở hữu và trạng thái liên quan.
- [ ] Outbox, dedupe và hiệu lực hệ thống ngoài được kiểm tra theo mô hình giao nhận thực tế.
- [ ] Worker còn sống hoặc request chưa rõ kết quả khiến test thất bại và fixture được cô lập.
- [ ] Kịch bản có khả năng phát hiện bản lỗi đã biết, không chỉ tạo nhiều request.

Giá trị của một concurrency regression test nằm ở việc biến một lịch tấn công logic cụ thể thành bằng chứng kiểm chứng được: yêu cầu có thể chồng lấn, bị gửi lại hoặc gặp xung đột, nhưng quy tắc nghiệp vụ, quyền theo đối tượng và hiệu lực cuối cùng vẫn nằm trong giới hạn đã định nghĩa.
