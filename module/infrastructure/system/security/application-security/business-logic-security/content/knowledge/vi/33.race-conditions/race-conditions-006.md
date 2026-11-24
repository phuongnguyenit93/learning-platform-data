# Race detection test

## Mục tiêu bài học

Race detection test là kiểm thử chủ động tạo những lịch thực thi cạnh tranh để phát hiện trường hợp kết quả phụ thuộc vào thứ tự chạy và làm vi phạm quy tắc nghiệp vụ. Trong bảo mật logic nghiệp vụ, mục tiêu là chứng minh một tình huống không hợp lệ có thể xảy ra hoặc kiểm chứng rằng cơ chế bảo vệ vẫn giữ được bất biến trong lịch đó.

Một hệ thống có thể xử lý đúng từng request khi chạy riêng nhưng tạo hai lượt dùng ưu đãi, hai lần giữ chỗ hoặc một quyết định phê duyệt sai khi request chạy đồng thời. Chỉ gửi nhiều request và quan sát vài mã HTTP thành công chưa đủ để phát hiện hoặc loại trừ các lỗi này.

Sau bài học, bạn có thể:

- Chuyển quy tắc nghiệp vụ thành bất biến có thể kiểm tra sau cạnh tranh.
- Dựng lịch đọc, kiểm tra, ghi và commit bằng điểm đồng bộ có chủ đích.
- Kiểm tra trên transaction và connection độc lập, với dữ liệu cô lập.
- Phân biệt kiểm thử race ở tầng nghiệp vụ với phát hiện data race trong bộ nhớ.
- Kiểm tra cả response, dữ liệu bền vững, idempotency và hiệu ứng ngoài transaction.
- Nhận diện những cách kiểm thử có thể đạt dù lỗi vẫn tồn tại.

## 1. Phát hiện race ở tầng nào?

Thuật ngữ race thường được dùng cho nhiều vấn đề khác nhau:

| Phạm vi | Ví dụ | Bằng chứng cần quan sát |
|---|---|---|
| Bộ nhớ trong một tiến trình | Hai thread cùng cập nhật một biến không được bảo vệ | Truy cập bộ nhớ và giá trị quan sát theo mô hình bộ nhớ |
| Transaction cơ sở dữ liệu | Hai yêu cầu cùng vượt qua kiểm tra còn tồn kho | Lịch đọc/ghi, kết quả commit và bất biến lưu trữ |
| Nhiều instance hoặc worker | Hai tiến trình cùng nhận quyền xử lý một nghiệp vụ | Quyền thực thi, trạng thái bền vững và hiệu ứng trùng |
| Quy trình nhiều bước | Nội dung thay sau kiểm tra nhưng trước phê duyệt | Snapshot, version, trạng thái và quyết định đã ghi |
| Giao tiếp bất đồng bộ | Event cũ đến sau event mới | Thứ tự áp dụng và trạng thái cuối ở consumer |

Một chương trình Java không có data race trên biến dùng chung vẫn có thể mắc race nghiệp vụ giữa hai transaction. Ngược lại, dùng `synchronized` trong một instance không tự bảo vệ dữ liệu khi request được xử lý bởi instance khác.

Vì vậy, phải chọn kiểm thử theo ranh giới đang bảo vệ. Công cụ kiểm tra thread trong bộ nhớ không thay thế kiểm thử tích hợp với cơ sở dữ liệu và luồng nghiệp vụ thực.

## 2. Bắt đầu từ bất biến, không bắt đầu từ số lượng thread

Giả sử một SKU có một đơn vị khả dụng. Hai người có quyền đặt hàng cùng yêu cầu giữ một đơn vị.

Chính sách của ví dụ:

- Không bổ sung, giải phóng hoặc hủy giữ chỗ trong thời gian kiểm thử.
- Mỗi lệnh yêu cầu số lượng bằng 1.
- Chỉ reservation ở trạng thái `CONFIRMED` mới tiêu thụ tồn kho trong mô hình này.
- Ghi tồn kho và reservation thuộc cùng một transaction.
- Hai lệnh có khóa idempotency khác nhau, đại diện hai ý định độc lập.

Bất biến cần kiểm tra:

```text
available >= 0
confirmedReservedQuantity <= initialAvailable
available + confirmedReservedQuantity = initialAvailable
```

Với `initialAvailable=1`, khi hai lệnh đã kết thúc theo hợp đồng:

```text
1 lệnh thành công
1 lệnh bị từ chối vì không còn hàng
available = 0
confirmedReservedQuantity = 1
confirmedReservationCount = 1
```

Các điều kiện trên chỉ đúng trong mô hình đã giới hạn. Nếu hệ thống còn có tồn kho theo kho, giữ chỗ đang chờ, hết hạn hoặc nguồn cấp bổ sung, phải mở rộng phương trình và phạm vi dữ liệu tương ứng.

Không chỉ kiểm tra `available >= 0`. Một lỗi lost update có thể để lại `available=0` nhưng tạo hai reservation, nghĩa là tồn kho không âm mà quy tắc vẫn bị phá vỡ.

## 3. Dựng một lịch thực thi làm lộ lỗi

### 3.1. Cách triển khai có khoảng trống kiểm tra rồi ghi

Một luồng không an toàn có thể là:

```text
bắt đầu transaction
    availableSnapshot = SELECT available
    nếu availableSnapshot >= requestedQuantity:
        INSERT reservation CONFIRMED
        UPDATE inventory
            SET available = availableSnapshot - requestedQuantity
commit
```

Mỗi transaction là nguyên tử đối với các thay đổi của chính nó, nhưng điều đó không làm phép kiểm tra và cập nhật dựa trên snapshot cũ an toàn trước transaction khác.

Lịch cạnh tranh:

| Bước | Transaction A | Transaction B | Dữ liệu đã commit |
|---|---|---|---|
| 1 | Đọc `available=1` | | Tồn kho 1, chưa có reservation |
| 2 | | Đọc `available=1` | Tồn kho 1, chưa có reservation |
| 3 | Kiểm tra 1 đủ cho yêu cầu 1 | | Chưa đổi |
| 4 | | Kiểm tra 1 đủ cho yêu cầu 1 | Chưa đổi |
| 5 | Tạo reservation A, ghi `available=0`, commit | | Tồn kho 0, một reservation |
| 6 | | Tạo reservation B, ghi lại `available=0`, commit | Tồn kho 0, hai reservation |

Ở một số mức isolation hoặc thiết kế lưu trữ, một transaction có thể bị chặn hoặc hủy thay vì cả hai cùng commit. Kiểm thử phải chạy trên cấu hình thực tế của hệ thống, không giả định mọi hệ quản trị tạo cùng một kết quả.

Trong cấu hình cho phép lịch trên, constraint chỉ kiểm tra tồn kho không âm vẫn không phát hiện hai reservation. Oracle của kiểm thử phải kiểm tra quan hệ giữa tồn kho và hiệu ứng nghiệp vụ.

### 3.2. Cơ chế bảo vệ cần được kiểm chứng

Một hướng xử lý là giành tồn kho bằng cập nhật có điều kiện:

```sql
UPDATE inventory
SET available = available - :validatedQuantity,
    version = version + 1
WHERE tenant_id = :authenticatedTenantId
  AND sku_id = :skuId
  AND available >= :validatedQuantity;
```

Máy chủ phải xác minh `validatedQuantity > 0`. Nếu cập nhật không đúng một dòng, không tạo reservation thành công. Nếu cập nhật thành công, việc tạo reservation, kết quả idempotency và audit/outbox cần nhất quán với transaction đó.

Kiểm thử không chỉ xác nhận câu SQL xuất hiện trong mã. Nó phải đưa hai ý định cạnh tranh vào đường thực thi và kiểm tra rằng chỉ một hiệu ứng tiêu thụ đơn vị tồn kho được commit.

## 4. Chọn điểm đồng bộ theo khoảng trống cần kiểm tra

Muốn tái hiện lỗi ở trên, cần bảo đảm hai yêu cầu cùng đọc giá trị ban đầu trước khi cho chúng ghi. Một start gate chỉ giúp hai thread bắt đầu gần nhau, chưa bảo đảm chúng đến cùng vị trí nguy hiểm.

Có thể dùng các điểm kiểm soát trong môi trường kiểm thử:

```text
BEFORE_TRANSACTION
AFTER_SNAPSHOT_READ
BEFORE_ATOMIC_CLAIM
AFTER_CLAIM_BEFORE_DEPENDENT_WRITE
BEFORE_COMMIT
AFTER_COMMIT_BEFORE_RESPONSE
```

Mỗi điểm phục vụ một câu hỏi khác nhau:

| Điểm điều khiển | Tình huống cần quan sát |
|---|---|
| Sau đọc snapshot, trước ghi | Hai quyết định cùng dựa trên dữ liệu cũ |
| Trước cập nhật có điều kiện | Hai lệnh cùng cạnh tranh quyền tạo hiệu ứng |
| Sau cập nhật root, trước ghi dữ liệu con | Lỗi giữa chừng có rollback đầy đủ không? |
| Trước commit | Thao tác khác nhìn thấy gì khi transaction chưa kết thúc? |
| Sau commit, trước response | Retry có lấy kết quả cũ thay vì tạo hiệu ứng lần nữa không? |

Điểm kiểm soát nên là một giao diện nội bộ hoặc adapter phục vụ test, mặc định không làm gì khi chạy thông thường. Không cho người dùng điều khiển hook, chèn độ trễ hoặc bỏ qua kiểm tra thông qua API sản phẩm.

Hook chỉ thay đổi lịch thực thi, không thay đổi kết quả kiểm tra nghiệp vụ. Nếu hook ném lỗi hoặc bị hủy trước commit, transaction phải được xử lý theo chính sách rollback đúng như các lỗi tương ứng khác.

### Không dùng một lịch cho mọi cơ chế khóa

Nếu cách sửa dùng `SELECT ... FOR UPDATE`, transaction B có thể chưa đọc được vì A đang giữ khóa. Một barrier yêu cầu cả hai đã đọc xong rồi mới cho A tiếp tục sẽ tự tạo bế tắc trong kiểm thử.

Với cơ chế đó, đặt gate trước lần lấy khóa và điều khiển một transaction giữ khóa trong khi transaction còn lại chờ. Sau khi transaction thắng kết thúc, kiểm tra transaction kia đọc trạng thái mới hoặc thất bại theo hợp đồng.

Không sửa cơ chế bảo vệ của production chỉ để nó phù hợp với một hook được đặt sai vị trí. Lịch kiểm thử phải phản ánh thiết kế cần kiểm chứng.

## 5. Chuẩn bị môi trường để kết quả có ý nghĩa

Một kiểm thử tích hợp cần làm rõ các yếu tố sau:

- Mỗi worker sử dụng connection, transaction và ngữ cảnh lưu trữ riêng.
- Fixture ban đầu đã commit trước khi hai worker bắt đầu.
- Pool có đủ connection cho worker và các thao tác quan sát cần thiết.
- Dùng engine và mức isolation phù hợp với môi trường cần bảo vệ.
- Dữ liệu được cô lập theo tenant, SKU hoặc test run để kiểm thử khác không can thiệp.
- Đọc kết quả cuối bằng nguồn dữ liệu chuẩn và connection mới sau khi các transaction đã kết thúc.
- Các actor đều có quyền hợp lệ trong ca kiểm thử tồn kho; lỗi quyền không được vô tình thay thế lỗi cạnh tranh cần kiểm tra.
- Khóa idempotency của hai ý định cạnh tranh phải khác nhau.

Một database in-memory hoặc một mock repository có thể có đặc tính khóa khác môi trường thật. Chúng hữu ích cho logic cục bộ nhưng không đủ để kết luận về race ở transaction production.

Nếu framework bọc toàn bộ test trong một transaction chưa commit, các worker có thể không nhìn thấy fixture. Nếu hai lời gọi vô tình dùng chung connection hoặc cùng một ngữ cảnh transaction, kiểm thử cũng không tạo ra hai transaction độc lập như dự định.

Không giữ khóa ngoài ý muốn trong bước setup, chẳng hạn cập nhật fixture rồi chờ worker chạy trước khi commit setup. Khi đó, timeout có thể đến từ cách dựng test chứ không phải service.

## 6. Khung Java 17 điều khiển lịch đọc rồi ghi

Ví dụ dưới đây là khung điều phối cho một service có bước đọc snapshot không khóa trước khi giành tồn kho. Hook được gọi sau bước đọc đó và trước thao tác ghi có hiệu lực. Với phiên bản được sửa bằng cập nhật có điều kiện, snapshot có thể vẫn phục vụ kiểm tra sớm, nhưng quyết định giành tồn kho phải nằm ở câu ghi nguyên tử.

Nếu service không có bước đọc như vậy, dùng seam phù hợp trước thao tác giành quyền; không thêm một lần đọc thừa vào production chỉ để sử dụng nguyên khung này.

Các interface fixture và service phải được nối với cơ sở dữ liệu và transaction thật của ứng dụng. Đoạn mã không tự cung cấp schema, datasource hoặc implementation nghiệp vụ.

```java
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class ReservationRaceHarness {
    public record Actor(UUID tenantId, UUID userId) {}

    public record Command(
            UUID skuId, int quantity, String idempotencyKey) {}

    public enum Outcome {
        APPLIED, NOT_AVAILABLE
    }

    public record Context(
            Actor actorA, Actor actorB, UUID skuId, int initialAvailable) {}

    public record StoredState(
            int available,
            long confirmedQuantity,
            long confirmedReservations) {}

    public interface RaceProbe {
        void afterSnapshotRead(int observedAvailable) throws Exception;
    }

    public interface ReservationService {
        // Mỗi lần gọi phải chạy transaction độc lập.
        // Chỉ trả APPLIED sau khi commit đã được xác nhận.
        Outcome reserve(Actor actor, Command command, RaceProbe probe)
                throws Exception;
    }

    public interface Fixture {
        Context prepareSingleUnitAndCommit() throws Exception;

        // Đọc sau khi worker kết thúc, dùng connection/ngữ cảnh mới.
        StoredState readFreshCommittedState(Context context) throws Exception;
    }

    private static final class AfterReadGate implements RaceProbe {
        private final CountDownLatch bothRead = new CountDownLatch(2);
        private final CountDownLatch allowWrites = new CountDownLatch(1);
        private final ConcurrentLinkedQueue<Integer> observations =
                new ConcurrentLinkedQueue<>();

        @Override
        public void afterSnapshotRead(int observedAvailable) throws Exception {
            observations.add(observedAvailable);
            bothRead.countDown();
            if (!allowWrites.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timed out waiting for release");
            }
        }

        boolean awaitBothReads() throws InterruptedException {
            return bothRead.await(5, TimeUnit.SECONDS);
        }

        List<Integer> observedValues() {
            return List.copyOf(observations);
        }

        void releaseWrites() {
            allowWrites.countDown();
        }
    }

    public static void verifyNoOversell(
            Fixture fixture, ReservationService service) throws Exception {
        Context context = fixture.prepareSingleUnitAndCommit();
        require(context.initialAvailable() == 1, "Fixture must contain one unit");

        AfterReadGate gate = new AfterReadGate();
        ExecutorService workers = Executors.newFixedThreadPool(2);

        try {
            Future<Outcome> resultA = workers.submit(() -> service.reserve(
                    context.actorA(),
                    new Command(context.skuId(), 1, "race-intent-A"), gate));
            Future<Outcome> resultB = workers.submit(() -> service.reserve(
                    context.actorB(),
                    new Command(context.skuId(), 1, "race-intent-B"), gate));

            require(gate.awaitBothReads(),
                    "Both requests must reach the intended read checkpoint");
            require(gate.observedValues().equals(List.of(1, 1)),
                    "Both requests must observe the initial unit");

            gate.releaseWrites();

            List<Outcome> outcomes = List.of(
                    resultA.get(10, TimeUnit.SECONDS),
                    resultB.get(10, TimeUnit.SECONDS));

            long applied = outcomes.stream()
                    .filter(value -> value == Outcome.APPLIED).count();
            long rejected = outcomes.stream()
                    .filter(value -> value == Outcome.NOT_AVAILABLE).count();
            require(applied == 1, "Exactly one request must apply");
            require(rejected == 1, "Exactly one request must find no stock");

            StoredState state = fixture.readFreshCommittedState(context);
            require(state.available() == 0, "Available stock must be zero");
            require(state.confirmedQuantity() == 1,
                    "Only one unit may be reserved");
            require(state.confirmedReservations() == 1,
                    "Only one confirmed reservation may exist");
            require(state.available() + state.confirmedQuantity()
                    == context.initialAvailable(), "Conservation must hold");
        } finally {
            // Giải phóng worker cả khi một assertion ở phía điều phối thất bại.
            gate.releaseWrites();
            workers.shutdownNow();
            if (!workers.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Workers did not terminate safely");
            }
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

### Ý nghĩa của những điều kiện trong khung

- Gate sau đọc bảo đảm cả hai đã quan sát cùng trạng thái, không chỉ bắt đầu gần nhau.
- Hai khóa khác nhau ngăn idempotency vô tình hợp nhất hai ý định và che lỗi tồn kho.
- Exception từ worker đi qua `Future.get()` làm test thất bại; không được chuyển mọi exception thành `NOT_AVAILABLE`.
- Response thành công chỉ được trả sau commit. Nếu service trả sớm, assertion về dữ liệu cuối không còn có cùng ý nghĩa.
- Kiểm tra reservation cùng tồn kho phát hiện trường hợp hai hiệu ứng nhưng số dư cuối vẫn không âm.
- Thời hạn chờ làm kiểm thử có điểm kết thúc; timeout không được coi là bằng chứng cơ chế bảo vệ đã hoạt động.
- Fixture cần cấp phạm vi dữ liệu mới cho mỗi lần chạy vì khóa minh họa trong mã là cố định trong phạm vi đó.

Khung yêu cầu hợp đồng kết thúc gồm đúng một `APPLIED` và một `NOT_AVAILABLE`. Nếu hệ thống công bố kết quả khác, chẳng hạn serialization failure có retry ở tầng trên, cần adapter đi tới kết quả cuối theo chính sách có giới hạn hoặc viết assertion riêng cho đúng hợp đồng. Không làm test đạt bằng cách coi mọi lỗi kỹ thuật là từ chối nghiệp vụ hợp lệ.

Fixture chỉ được dọn sau khi các worker và transaction đã kết thúc. Nếu worker chưa dừng, phải xử lý hủy câu lệnh hoặc connection theo hạ tầng test và giữ dữ liệu để chẩn đoán; không xóa dữ liệu trong khi worker còn có thể commit.

## 7. Assertion cần kiểm tra những gì?

### 7.1. Response và dữ liệu bền vững phải tương ứng

Một response thành công nhưng transaction rollback là lỗi. Một response thất bại nhưng dữ liệu đã thay đổi một phần cũng là lỗi, trừ trường hợp hợp đồng rõ ràng đang thông báo kết quả chưa xác định và có đường phục hồi.

Với mỗi command, có thể đối chiếu:

```text
commandId hoặc khóa idempotency
outcome đã trả
reservationId nếu có
kết quả transaction đã xác nhận
bản ghi hiệu ứng nghiệp vụ
```

Không chỉ đếm số response `2xx`: các response có thể là đang xử lý, replay một kết quả cũ hoặc trả thành công quá sớm.

### 7.2. Kiểm tra audit, idempotency và outbox theo thiết kế

Nếu một reservation thành công phải tạo một audit và một event bền vững, kiểm thử cần kiểm tra các quan hệ đó. Transaction bị từ chối không được tạo một event thành công làm consumer tiếp tục giao hàng.

Phân biệt bản ghi outbox với số lần consumer được gọi. Một event có thể được giao lại hợp lệ, nhưng consumer phải bảo vệ hiệu ứng của mình trước trùng lặp. Test ở producer và test ở consumer có oracle khác nhau.

Nếu consumer có thể xóa hoặc chuyển bản ghi outbox trong khi test đang đọc, cần kiểm soát vòng đời consumer hoặc quan sát một nguồn lưu kết quả phù hợp. Không dùng số hàng outbox rỗng làm bằng chứng rằng event chưa từng tồn tại.

### 7.3. Kiểm tra bất biến chưa thay thế toàn bộ ngữ nghĩa

Trạng thái cuối hợp lệ là điều kiện quan trọng nhưng chưa đủ cho mọi lịch. Hai response cùng tuyên bố đã giữ chỗ trong khi chỉ có một reservation vẫn vi phạm hợp đồng với người dùng.

Với thao tác cần ngữ nghĩa mạnh hơn, ghi lịch bắt đầu, kết thúc, đầu vào và kết quả để đối chiếu với những thứ tự thực thi tuần tự hợp lệ của đặc tả. Nếu hợp đồng yêu cầu tôn trọng thứ tự thực tế giữa những thao tác không chồng lấn, oracle cần kiểm tra cả điều đó.

Một số lịch vượt qua không chứng minh mọi lịch đều an toàn. Cần kết hợp bằng chứng kiểm thử với thiết kế transaction và ràng buộc lưu trữ.

## 8. Các lịch cần thử ngoài “hai request cùng bắt đầu”

| Lịch điều khiển | Rủi ro cần phát hiện |
|---|---|
| A và B cùng đọc trước khi ghi | Lost update, check-then-act |
| A giành tài nguyên rồi lỗi trước khi tạo dữ liệu con | Thiếu rollback, giữ chỗ ma |
| A tạo dữ liệu con rồi lỗi trước commit | Hiệu ứng một phần hoặc audit sai |
| A commit nhưng mất response; client gửi lại | Tạo hiệu ứng trùng khi retry |
| A đang xử lý; B gửi cùng khóa idempotency | Hai executor cùng thực thi một ý định |
| Cùng khóa nhưng payload khác | Ghi đè ý định hoặc trả nhầm kết quả |
| A đọc quyền; quyền bị thu hồi trước khi ghi | TOCTOU trong quyền theo chính sách của hệ thống |
| A đọc trạng thái nháp; B nộp hoặc duyệt trước | Bỏ qua state machine |
| A quét file; B làm nội dung thay đổi trước kích hoạt | Dùng kết quả kiểm tra cho sai phiên bản |
| A và B sửa bản ghi khác nhau nhưng chung hạn mức | Write skew ở bất biến nhiều bản ghi |
| Event mới được áp dụng trước event cũ | Trạng thái ở consumer quay lùi |

Mỗi lịch cần mô tả rõ điều gì được biết tại điểm đồng bộ, thao tác nào được phép tiếp tục và kết quả nào được coi là đúng. Không dùng một chuỗi độ trễ cố định làm đặc tả ngầm cho lịch thực thi.

## 9. Tách kiểm thử tranh chấp tài nguyên khỏi kiểm thử idempotency

Hai ca sau trông giống nhau ở số request nhưng kiểm tra hai bất biến khác nhau.

### Ca A: hai ý định độc lập cùng tranh một tài nguyên

```text
Command A: quantity=1, key=K-A
Command B: quantity=1, key=K-B
```

Oracle: không bán hoặc giữ chỗ vượt tài nguyên. Một thao tác thành công không có nghĩa thao tác kia là retry của nó.

### Ca B: cùng một ý định được gửi hai lần

```text
Command A: quantity=1, key=K
Command B: quantity=1, key=K
```

Oracle: chỉ có một hiệu ứng nghiệp vụ; phản hồi có thể là cùng kết quả cuối hoặc một kết quả đang xử lý theo hợp đồng. Không bắt buộc “một thành công, một hết hàng”, vì request thứ hai đại diện cùng ý định và có thể hợp lệ khi nhận replay thành công.

Cần thêm ca cùng khóa nhưng khác payload. Máy chủ phải phát hiện khác fingerprint, không chọn một payload ngẫu nhiên và coi cả hai request đều cùng ý định.

Nếu chỉ chạy Ca B, cơ chế chống trùng có thể làm test tồn kho đạt trong khi Ca A vẫn vượt giới hạn. Nếu chỉ chạy Ca A, race tạo hai bản ghi cùng idempotency key có thể chưa được phát hiện.

## 10. Kiểm thử write skew và phạm vi aggregate

Giả sử một dự án còn hạn mức 100, hai chứng từ độc lập cùng xin giữ 80. Mỗi chứng từ có version riêng nên cập nhật cả hai có thể không xung đột ở cấp bản ghi.

Lịch kiểm thử cần bảo đảm:

1. A và B đều đọc tổng cam kết ban đầu trước khi một bên tạo cam kết mới.
2. Mỗi bên ghi vào chứng từ riêng, không vô tình dùng chung một khóa khiến chúng tuần tự hóa ngoài ý muốn.
3. Sau khi kết thúc, tổng cam kết được đọc lại từ dữ liệu bền vững.
4. Tổng không vượt hạn mức và kết quả từng command đúng với hợp đồng.

Cách sửa có thể dùng root ngân sách chung, cập nhật số dư có điều kiện, khóa tài nguyên chung hoặc cơ chế isolation thích hợp. Test phải đi qua cả đường tạo mới và các đường cập nhật, import, tác vụ nền liên quan tới cùng bất biến.

Một kiểm thử chỉ sửa cùng một dòng không thể chứng minh hệ thống chống write skew giữa các dòng khác nhau.

## 11. Từ một instance tới nhiều instance và nhiều hệ thống

### 11.1. Phát hiện khóa chỉ có hiệu lực trong bộ nhớ

Một service có thể vượt qua kiểm thử hai thread vì dùng mutex trong cùng tiến trình. Nếu production chạy nhiều instance, cần kiểm thử hai yêu cầu qua các instance độc lập, cùng trỏ tới nguồn dữ liệu chuẩn.

Không để router luôn đưa cả hai request vào cùng một instance rồi kết luận khóa cục bộ bảo vệ toàn hệ thống. Ghi nhận instance xử lý trong dữ liệu chẩn đoán của môi trường test nếu cần xác minh lịch.

### 11.2. Kiểm tra hết hạn quyền thực thi

Với worker dùng lease, có thể tạo lịch:

```text
A nhận lease rồi bị tạm dừng.
Lease hết hạn.
B nhận quyền mới và thực thi.
A tiếp tục với quyền cũ.
```

Oracle cần ngăn executor cũ tạo hiệu ứng không hợp lệ. Chỉ kiểm tra rằng một khóa phân tán đã từng tồn tại không đủ; phải kiểm tra cách quyền thực thi cũ bị từ chối hoặc hiệu ứng được chống trùng ở nơi ghi.

### 11.3. Kiểm tra ranh giới không có transaction chung

Nếu giữ chỗ trong database nhưng gọi một dịch vụ ngoài để tạo hiệu ứng, transaction database không tự rollback dịch vụ đó. Test cần mô tả thất bại trước và sau từng ranh giới cùng giao thức idempotency, outbox hoặc bù trừ tương ứng.

Không giả định “hai lần gọi cùng key” luôn an toàn nếu hệ thống bên ngoài không thực thi ngữ nghĩa chống trùng đó.

## 12. Những cách kiểm thử dễ cho kết quả đạt giả

| Cách kiểm thử | Điều có thể bị bỏ sót | Cách cải thiện |
|---|---|---|
| Gửi hai request nối tiếp | Không có cửa sổ cạnh tranh | Dùng worker độc lập và gate đúng điểm |
| Chỉ đặt start gate | Một request có thể đọc và commit trước request còn lại | Điều khiển điểm sau đọc hoặc trước thao tác cần tranh chấp |
| Dùng `sleep` để mong hai luồng gặp nhau | Phụ thuộc tốc độ máy, dễ chập chờn | Dùng latch, barrier hoặc tín hiệu xác nhận trạng thái |
| Dùng chung connection | Có thể không tạo hai transaction độc lập | Cấp connection riêng cho mỗi worker |
| Pool chỉ có một connection | Request bị tuần tự hóa trước đoạn cần kiểm tra | Cấp đủ tài nguyên và xác minh worker đã tới checkpoint |
| Dùng cùng idempotency key cho hai ý định | Chống trùng che lỗi tranh tài nguyên | Tách ca độc lập và ca retry |
| Chỉ kiểm tra tồn kho không âm | Hai reservation có thể tồn tại dù số dư không âm | Kiểm tra phương trình và ledger hiệu ứng |
| Nuốt exception thành kết quả bị từ chối | Lỗi triển khai bị coi là bảo vệ thành công | Phân loại lỗi, để exception không mong đợi làm test thất bại |
| Đọc kết quả bằng cache hoặc transaction cũ | Quan sát dữ liệu không phản ánh trạng thái cuối | Đọc mới từ nguồn chuẩn sau khi worker kết thúc |
| Test chỉ đi qua một API | Import hoặc job nền vẫn có đường ghi bỏ qua bảo vệ | Ma trận các đường thực thi chung bất biến |
| Hai thread trong một instance | Mutex cục bộ làm test đạt | Thêm ca nhiều instance khi kiến trúc yêu cầu |
| Dọn fixture khi worker còn chạy | Worker commit vào dữ liệu đã bị xóa hoặc tái sử dụng | Dừng và xác nhận kết thúc trước cleanup |

Timeout, deadlock và starvation cũng cần phân tích. Một test kết thúc bằng timeout chưa chứng minh bất biến bị phá, nhưng cũng không được đánh dấu đạt vì không thấy dữ liệu sai. Phải phân biệt lỗi điều phối của test với vấn đề liveness của hệ thống.

## 13. Kiểm tra độ nhạy của oracle

Một bộ test đáng tin cần có khả năng thất bại khi cơ chế bảo vệ tương ứng bị thiếu.

Trong môi trường thử nghiệm cô lập, có thể dùng một implementation đối chứng cố ý giữ khoảng trống đọc rồi ghi, hoặc một biến thể bỏ điều kiện giành tài nguyên. Với fixture một đơn vị và gate sau đọc, oracle phải phát hiện hai hiệu ứng hoặc sai lệch kết quả.

Sau đó, implementation có bảo vệ phải giữ được các bất biến dưới lịch phù hợp với thiết kế của nó. Không bắt mọi implementation dùng cùng một vị trí hook nếu điều đó mâu thuẫn với cách khóa.

Cách đối chứng này giúp phát hiện test chỉ đang kiểm tra một đường không bao giờ tới đoạn nguy hiểm, fixture đã vô tình tuần tự hóa request hoặc assertion không đủ mạnh.

Không tắt cơ chế bảo vệ trên môi trường thật để kiểm tra độ nhạy. Cũng không đưa endpoint phá lịch, bỏ khóa hoặc bỏ kiểm tra vào luồng người dùng.

## 14. Stress test bổ sung cho lịch có kiểm soát

Kiểm thử có gate giúp tái hiện một lịch cụ thể. Stress test mở rộng số request, actor, tài nguyên và lịch thực thi để tìm những trường hợp chưa dự đoán.

Một chiến lược bổ sung có thể gồm:

- Lặp lại lịch hai transaction có kiểm soát để bảo đảm sửa lỗi không bị hồi quy.
- Chạy nhiều ý định trên cùng SKU để tăng tranh chấp.
- Chạy trên nhiều SKU để phát hiện khóa quá rộng hoặc tranh chấp không cần thiết.
- Kết hợp tạo, hủy và hết hạn reservation theo một mô hình bất biến đầy đủ hơn.
- Ghi seed, command ID, thời điểm checkpoint và kết quả để hỗ trợ tái hiện.

Stress test cần giới hạn thời gian, số lượng dữ liệu và phạm vi môi trường. Chạy ít lần không thấy lỗi không phải bằng chứng mọi lịch an toàn; chạy rất nhiều request cũng không thay thế lịch điều khiển đúng cửa sổ kiểm tra rồi sử dụng.

Nếu phát hiện một lịch lỗi từ stress, nên rút gọn thành ca hồi quy có ít thao tác và điểm đồng bộ rõ ràng. Mục tiêu là giữ lại bằng chứng tái hiện được, không chỉ giữ một tỷ lệ thất bại chập chờn.

## 15. Bằng chứng cần giữ khi test thất bại

Một báo cáo hữu ích nên ghi:

```text
Bất biến: tổng reservation xác nhận không vượt tồn kho ban đầu
Fixture: một đơn vị, không có giải phóng hoặc bổ sung
Môi trường: engine, isolation, số instance, cấu hình pool liên quan
Lịch: A đọc 1; B đọc 1; giải phóng gate; A/B thực hiện ghi
Kết quả command: định danh và outcome của từng lệnh
Dữ liệu cuối: available, tổng quantity, số reservation
Dấu vết: transaction, audit/outbox và lỗi kỹ thuật liên quan
```

Không ghi token, mật khẩu, dữ liệu khách hàng thật hoặc toàn bộ payload nhạy cảm chỉ để tăng chi tiết báo cáo. Dùng fixture tổng hợp và correlation ID trong môi trường có kiểm soát.

Phân biệt rõ “tái hiện được vi phạm bất biến”, “gặp lỗi kỹ thuật chưa phân loại” và “timeout do checkpoint không đạt”. Ba kết quả này đòi hỏi hướng xử lý khác nhau.

Khi sửa xong, báo cáo cần chỉ ra bất biến được bảo vệ, ranh giới transaction và đường ghi nào tham gia cơ chế đó. Một thay đổi làm test chậm hơn nên ít gặp lỗi chưa phải là cách sửa đáng tin.

## 16. Áp dụng vào một quy tắc nghiệp vụ khác

Để thiết kế một race detection test mới:

1. Viết bất biến trên dữ liệu bền vững và định nghĩa đúng các trạng thái được tính vào nó.
2. Chọn ít nhất hai ý định hợp lệ nếu chạy riêng nhưng có khả năng tranh chấp khi chạy đồng thời.
3. Xác định ranh giới đọc, kiểm tra, ghi, commit và phản hồi cần điều khiển.
4. Dựng fixture đã commit với ngữ cảnh quyền, idempotency và dữ liệu cô lập rõ ràng.
5. Dùng connection và transaction độc lập, có thời hạn chờ và cơ chế kết thúc worker.
6. Kiểm tra outcome từng command cùng trạng thái cuối, audit và hiệu ứng liên quan theo hợp đồng.
7. Xác nhận oracle đủ nhạy bằng đối chứng trong môi trường thử nghiệm và giữ lại lịch hồi quy ngắn gọn.

Race detection test có giá trị khi nó biến một giả thuyết cạnh tranh thành lịch thực thi và kết quả có thể quan sát. Kết hợp lịch có kiểm soát, bất biến đúng phạm vi và ràng buộc lưu trữ phù hợp giúp phát hiện những đường lạm dụng mà kiểm thử tuần tự thường bỏ qua.
