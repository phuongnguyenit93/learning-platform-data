# Truy vấn publication chưa xong

## 1. Tại sao cần truy vấn publication chưa hoàn tất?

Trong một ứng dụng **Spring Modulith**, module `orders` có thể phát `OrderConfirmed` để module `notifications` gửi thông báo, `loyalty` ghi điểm và `reporting` cập nhật dữ liệu báo cáo. Với listener xử lý sau commit, đơn hàng có thể đã được lưu thành công trong database nguồn **trước khi** các tác vụ phụ này hoàn tất.

Ví dụ một sự cố vận hành:

> Khách hàng thấy đơn hàng đã xác nhận nhưng chưa nhận được email. Module `orders` ghi nhận commit thành công. Vậy event có được phát tới `notifications` không, listener đã chạy chưa, hay việc gửi thất bại và chưa được phục hồi?

**Event Publication Registry** giúp theo dõi việc một application event được công bố cho những transactional listener nào và việc xử lý publication đã được ghi nhận hoàn tất hay chưa. Một **publication chưa xong** (*incomplete publication*) là bản ghi giao event đến **một listener đích** mà registry **chưa ghi nhận completion**.

Truy vấn các publication này giúp:

- Nhận diện các tác vụ sau commit còn chờ hoặc chưa hoàn tất.
- Tìm listener cụ thể đang gây tồn đọng, thay vì chỉ biết “một event có vấn đề”.
- Phân biệt giao nhận bình thường đang thực thi với những publication quá tuổi kỳ vọng.
- Điều tra các lần listener ném lỗi, JVM dừng giữa chừng, hoặc sự cố executor.
- Xác định **đối tượng cần phục hồi** mà không phát lại toàn bộ sự kiện nghiệp vụ một cách tùy tiện.
- Xây dựng cảnh báo và đối soát về độ tin cậy giao sự kiện giữa các module.

Trong học phần **SPRING_MODULITH_APPLICATION_EVENTS**, truy vấn registry là cầu nối giữa thiết kế publisher/listener sau commit với **quan sát, retry và kiểm thử giao sự kiện đáng tin cậy**. Bài tập trung vào cách đọc và diễn giải publication chưa hoàn tất, không coi registry là một workflow engine hay kho event-sourcing.

## 2. Publication không đồng nghĩa với domain event

Giả sử `orders` phát **một** event `OrderConfirmed` với `eventId = E-100`. Có ba listener:

~~~mermaid
flowchart TB
    E["OrderConfirmed<br/>eventId = E-100"]
    E --> P1["Publication: notifications"]
    E --> P2["Publication: loyalty"]
    E --> P3["Publication: reporting"]
    P1 --> D1["COMPLETED"]
    P2 --> D2["INCOMPLETE"]
    P3 --> D3["COMPLETED"]
~~~

Đây là **một event nghiệp vụ**, nhưng có thể có **ba publication** tương ứng với ba transactional listener được registry theo dõi. Nếu `loyalty` chưa hoàn tất, không thể kết luận `notifications` và `reporting` cũng thất bại.

| Khái niệm | Câu hỏi trả lời | Ví dụ |
| --- | --- | --- |
| Domain event | Điều gì đã xảy ra trong nghiệp vụ? | `OrderConfirmed(E-100)` |
| `eventId` do ứng dụng thiết kế | Đây là event logic nào? | `E-100` |
| Publication | Event này được giao tới listener nào? | `E-100 → LoyaltyListener` |
| Target identifier | Listener đích được registry nhận diện bằng gì? | Định danh listener do hạ tầng quản lý |
| Completion | Registry đã ghi nhận xử lý thành công ở đích chưa? | `LoyaltyListener` chưa có completion |
| `correlationId` | Event này thuộc chuỗi nghiệp vụ nào? | `C-42` |

Một số điểm dễ nhầm:

1. `eventId` trong record do bạn viết **không phải** ID bản ghi publication do registry cấp.
2. Một publication có **đích riêng**: cùng event nhưng listener khác có vòng đời completion khác.
3. Publication chưa hoàn tất **không tự khẳng định listener chưa bao giờ chạy**. Listener có thể đã thực hiện tác động rồi JVM dừng trước lúc ghi completion.
4. Một consumer thành công **không** làm toàn bộ publication của các consumer khác được đánh dấu hoàn tất.

Như vậy, câu hỏi vận hành chuẩn không chỉ là “event `E-100` lỗi chưa?” mà là **“publication dành cho listener nào của event `E-100` còn chưa được registry ghi nhận hoàn tất?”**

## 3. Vòng đời của một publication

Một luồng thông dụng khi dùng transactional listener và registry bền vững:

~~~mermaid
sequenceDiagram
    participant O as orders
    participant DB as Database
    participant R as Publication Registry
    participant N as notifications
    O->>DB: Đổi trạng thái đơn trong T1
    O->>R: Publish và đăng ký publication trong T1
    Note over O,R: Transaction T1 chưa commit
    O->>DB: COMMIT T1
    R-->>N: Giao OrderConfirmed sau commit
    N->>N: Xử lý tác động phụ
    alt Listener thành công
        N-->>R: Ghi nhận completion
    else Listener lỗi / process dừng
        Note over R,N: Publication vẫn có thể chưa hoàn tất
    end
~~~

Sơ đồ mô tả cơ chế **khái niệm**; thời điểm flush SQL, cách lưu trữ và callback cụ thể có thể thay đổi theo phiên bản, transaction manager và implementation registry.

Điều kiện để publication có thể phục hồi sau restart là đã cấu hình **một backend registry bền vững** phù hợp, chẳng hạn JDBC hoặc JPA, và các bản ghi được đăng ký nhất quán với transaction nguồn. Registry chỉ nằm trong bộ nhớ **không** thể cung cấp cùng mức độ bền qua process restart.

### 3.1. Trạng thái không phải lúc nào cũng là cột `status`

Tùy implementation/phiên bản, trạng thái publication có thể được biểu diễn bằng:

- Bản ghi **chưa có thời điểm completion**.
- Bản ghi còn nằm trong **kho incomplete**.
- Bản ghi completed được đánh dấu, di chuyển tới kho completed hoặc bị xóa theo chính sách lưu trữ.

Vì vậy không được tự suy rằng mọi backend đều có bảng tên `event_publication` và cột `status = 'FAILED'`. Khi làm việc thực tế, ưu tiên **public API truy vấn** mà phiên bản Spring Modulith cung cấp; nếu cần SQL vận hành, đọc đúng schema chính thức của implementation đang chạy và kiểm tra quyền truy cập.

### 3.2. Incomplete ≠ failed ≠ đang chờ

| Điều quan sát từ registry | Có thể suy ra | Chưa thể suy ra |
| --- | --- | --- |
| Có publication incomplete mới tạo | Completion chưa được ghi nhận | Listener đã lỗi hay chỉ chưa kịp chạy |
| Publication incomplete đã tồn tại lâu | Có tồn đọng vượt thời gian kỳ vọng | Nguyên nhân chắc chắn là lỗi code |
| Không còn publication incomplete của listener | Registry không còn đánh dấu việc giao đó là chưa hoàn tất | Tác động bên ngoài đã thực hiện đúng một lần |
| Nhiều incomplete cùng listener | Có điểm tập trung cần điều tra | Có cần phát lại tất cả ngay hay không |

Ví dụ publication `OrderConfirmed(E-100) → NotificationListener` có tuổi 5 giây. Nếu gateway email đang xử lý bình thường trong 10 giây, nó có thể chưa hoàn tất **nhưng không có lỗi**. Ngược lại, publication đã 30 phút không hoàn tất khi SLO yêu cầu 60 giây là tín hiệu cần điều tra.

**Truy vấn chỉ là một ảnh chụp tại thời điểm đọc.** Ngay sau khi truy vấn, listener có thể hoàn tất. Các thao tác vận hành phải chấp nhận dữ liệu thay đổi đồng thời.

## 4. Điều kiện trước khi truy vấn

Trước khi truy vấn, xác nhận hệ thống thật sự có dữ liệu publication mà bạn kỳ vọng.

| Kiểm tra | Vì sao quan trọng? |
| --- | --- |
| Sử dụng application events trong Spring Modulith | Chỉ gọi `ApplicationEventPublisher` thuần Spring không tự có kho publication bền vững |
| Có transactional listeners phù hợp | Registry theo dõi việc giao tới các listener thuộc cơ chế transaction được hỗ trợ, không nhất thiết mọi `@EventListener` thông thường |
| Publisher chạy trong transaction hợp lệ | Cho phép đăng ký publication và commit dữ liệu nguồn theo cơ chế được thiết kế |
| Backend registry đã cấu hình | JDBC/JPA hoặc backend khác có đặc tính bền và schema/bean phù hợp |
| Transaction manager và database có tính nhất quán | Tránh trạng thái đơn commit nhưng publication không được đăng ký như mong đợi |
| Có chiến lược retention | Biết publication completed có còn lưu hay đã được dọn |
| Quyền truy vấn theo nguyên tắc ít quyền | Bản ghi có thể chứa payload, ID người dùng hoặc thông tin nhạy cảm |

Một ứng dụng chỉ có listener `@EventListener` đồng bộ thường **không** nhận cùng loại bảo đảm như transactional listener có publication registry. Nếu việc giao nhận đã xảy ra hoàn toàn trong bộ nhớ, việc “không thấy incomplete” không đủ bằng chứng rằng hệ thống không từng bỏ lỡ tác vụ.

Đặc biệt, **rollback nguồn** trước khi commit có thể khiến cả thay đổi nguồn lẫn bản ghi publication đăng ký trong transaction đó rollback. Trong trường hợp này, không nên mong tìm thấy một publication incomplete cho nghiệp vụ vốn chưa được commit.

## 5. Hai con đường truy vấn: API và cơ sở dữ liệu

Có hai cách tiếp cận thường dùng để tìm publication chưa hoàn tất:

1. **Public API của Spring Modulith:** phù hợp khi ứng dụng cần truy vấn/kiểm tra ngay trong Java và muốn hạn chế phụ thuộc vào schema lưu trữ.
2. **Truy vấn read-only tại backend registry:** phù hợp cho vận hành, dashboard hoặc điều tra database, với điều kiện dùng đúng implementation và lược đồ hiện hành.

**Ưu tiên API công khai** khi có thể. Các interface, cách tìm publication và khả năng lọc theo thời gian có thể khác nhau giữa phiên bản Spring Modulith. Đừng viết code production bằng cách đoán tên method hoặc xem một đoạn pseudo-code là API chính thức.

Mục tiêu của truy vấn thường là lấy được ít nhất:

| Thuộc tính quan sát | Ý nghĩa |
| --- | --- |
| Publication identifier | Bản ghi giao event cụ thể |
| Event type | Event nghiệp vụ được giao |
| Target/listener identifier | Consumer chưa hoàn tất |
| Publication/registration time | Mốc để tính tuổi publication |
| Completion (nếu có) | Publication đã được ghi nhận hoàn tất chưa |
| Event metadata có kiểm soát | `eventId`, `correlationId`, `orderId` để đối soát |

**Không mặc định** tất cả metadata đều được index thành cột SQL. Event có thể được serialize thành một payload opaque, và một số trường chỉ có thể lấy bằng deserialize qua codec phù hợp.

## 6. Truy vấn trong Java mà không khóa mình vào schema

Một cách thiết kế thuận tiện cho vận hành là đặt một **read-only inspection port** trong module hạ tầng/operations. Adapter cụ thể kết nối public registry API của phiên bản đang dùng; business module như `orders` không cần phụ thuộc vào chi tiết registry.

### 6.1. Định nghĩa dữ liệu quan sát an toàn

~~~java
// com/example/shop/operations/IncompletePublicationView.java
package com.example.shop.operations;

import java.time.Instant;

public record IncompletePublicationView(
        String publicationId,
        String eventType,
        String listenerTarget,
        Instant registeredAt,
        String eventId,
        String correlationId
) {}
~~~

Đây là **DTO do ứng dụng tự định nghĩa**, không phải lớp được Spring Modulith tạo sẵn. Các trường `eventId` và `correlationId` có thể vắng mặt nếu event cũ không mang metadata hoặc hạ tầng truy vấn không giải mã được; khi đó adapter cần biểu diễn “không biết” theo hợp đồng rõ ràng, không tạo ID giả.

### 6.2. Port cho truy vấn có giới hạn

~~~java
// com/example/shop/operations/IncompletePublicationReader.java
package com.example.shop.operations;

import java.time.Instant;
import java.util.List;

public interface IncompletePublicationReader {
    List<IncompletePublicationView> findRegisteredBefore(
            Instant cutoff, int limit);
}
~~~

Ý nghĩa `findRegisteredBefore(cutoff, limit)`:

- Chỉ trả publication **chưa hoàn tất**.
- Chỉ lấy publication được đăng ký trước `cutoff`.
- Có giới hạn số dòng để tránh quét vô hạn dưới tải.
- Không thay đổi completion, không kích hoạt retry khi chỉ muốn xem trạng thái.

Adapter thực tế có thể dùng API quản lý publication **do Spring Modulith phiên bản triển khai cung cấp**, hoặc một repository read-only dựa trên backend đã chọn. Nếu API cụ thể chỉ cho phép truy vấn toàn bộ trước khi lọc, phải cân nhắc chi phí và không dùng cách đó làm endpoint truy vấn tần suất cao khi registry lớn.

### 6.3. Service tính tuổi và phân nhóm

~~~java
// com/example/shop/operations/PublicationHealthService.java
package com.example.shop.operations;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class PublicationHealthService {
    private final IncompletePublicationReader reader;
    private final Clock clock;

    public PublicationHealthService(
            IncompletePublicationReader reader, Clock clock) {
        this.reader = reader;
        this.clock = clock;
    }

    public List<IncompletePublicationView> findStale(
            Duration threshold, int limit) {
        if (threshold.isNegative() || threshold.isZero()) {
            throw new IllegalArgumentException(
                    "threshold must be positive");
        }
        if (limit < 1 || limit > 500) {
            throw new IllegalArgumentException("limit out of range");
        }

        Instant cutoff = clock.instant().minus(threshold);
        return reader.findRegisteredBefore(cutoff, limit);
    }
}
~~~

**Giới hạn của ví dụ:** không có implementation cho `IncompletePublicationReader` vì cách truy cập publication phụ thuộc **phiên bản Spring Modulith, module persistence và schema** của hệ thống đang triển khai. Đây là port có thể chạy/kiểm thử độc lập sau khi bạn tự cung cấp adapter, không phải tuyên bố `IncompletePublicationReader` là API của framework.

Một ngưỡng “stale” như **2 phút** cần đến từ SLO và đặc điểm tác vụ. Listener xử lý báo cáo 10 phút có thể vẫn đang chạy hợp lệ; ngược lại, một tác vụ gửi email có deadline 30 giây có thể cần cảnh báo sớm hơn.

## 7. Truy vấn SQL: chỉ dựa trên schema đã xác minh

Trong vận hành, đôi khi người phụ trách có quyền đọc database nhưng không gọi trực tiếp Java API. Cách làm an toàn là tạo một **read-only view** do đội vận hành kiểm soát, ánh xạ dữ liệu từ bảng registry thật sang những tên cột thống nhất.

Ví dụ **SQL khái niệm**, giả định bạn đã tạo một view tên `ops.incomplete_publication_view` với các cột tương ứng:

~~~sql
-- Minh họa query read-only trên VIEW DO ỨNG DỤNG TỰ TẠO.
-- KHÔNG phải tên bảng/schema mặc định của Spring Modulith.
SELECT
    publication_id,
    event_type,
    listener_target,
    registered_at
FROM ops.incomplete_publication_view
WHERE completed_at IS NULL
  AND registered_at < :cutoff
ORDER BY registered_at ASC
LIMIT :max_rows;
~~~

Các bước triển khai:

1. **Xác nhận backend thực tế:** JDBC, JPA hay implementation khác; kiểm tra schema/định nghĩa tương ứng với phiên bản đang chạy.
2. **Kiểm tra biểu diễn completion:** có backend lưu timestamp hoàn tất, có backend tách completed/incomplete hoặc dọn bản ghi.
3. **Ánh xạ qua view riêng:** tên cột `registered_at`, `listener_target` trong ví dụ là tên **do ứng dụng đặt**, không phải cam kết API database của framework.
4. **Dùng quyền chỉ đọc và giới hạn kết quả.** Tránh query toàn bộ serialized event payload ở endpoint hoặc dashboard công khai.
5. **Dùng tham số bind (`:cutoff`, `:max_rows`)** để tránh SQL injection và dễ điều chỉnh ngưỡng.
6. **Kiểm thử query khi nâng cấp Spring Modulith.** Thay schema hoặc chiến lược lưu completed có thể đòi sửa view/adapter.

Để thống kê số publication theo listener, có thể tạo một query trên cùng view:

~~~sql
SELECT
    listener_target,
    COUNT(*) AS incomplete_count,
    MIN(registered_at) AS oldest_registered_at
FROM ops.incomplete_publication_view
WHERE completed_at IS NULL
GROUP BY listener_target
ORDER BY incomplete_count DESC;
~~~

Query này cung cấp tổng quan, không nói **tại sao** một listener còn incomplete. Phải ghép với log, các lần deploy, tình trạng executor và hệ thống phụ thuộc.

### 7.1. Khi completed được xóa khỏi bảng

Nếu implementation chỉ giữ những publication chưa hoàn tất, các dòng còn tồn tại **đã là incomplete**; điều kiện `completed_at IS NULL` có thể không tồn tại hoặc không có ý nghĩa. Tương tự, nếu dữ liệu đã được chuyển sang archive, query bảng active không cho biết đầy đủ lịch sử.

**Không áp dụng máy móc SQL minh họa vào bảng thật.** Hãy đọc schema của backend đã cấu hình, tạo adapter/view tương thích rồi mới dùng dashboard hoặc câu lệnh vận hành.

## 8. Tuổi publication và thời điểm commit

Một chỉ số trực quan là:

\[
\mathrm{age} = \mathrm{now} - \mathrm{registeredAt}
\]

Nếu registry ghi thời điểm đăng ký publication **trong transaction nguồn**, `registeredAt` có thể **sớm hơn** thời điểm commit thực sự. Vì vậy tuổi publication là thước đo **xấp xỉ độ lâu chưa hoàn tất tính từ lúc đăng ký**, không nhất thiết bằng `commit-to-completion latency` chính xác.

Giả sử:

~~~text
14:00:00  publisher publish OrderConfirmed (publication được đăng ký)
14:00:04  transaction nguồn commit
14:00:05  listener bắt đầu
14:00:08  listener hoàn tất
~~~

Tại `14:00:07`, publication có thể có **age ≈ 7 giây**, nhưng thời gian từ commit tới hiện tại mới khoảng **3 giây**. Điều này quan trọng khi đặt SLO tính từ thời điểm nguồn đã commit.

Nên phân biệt:

| Đại lượng | Cách hiểu | Dùng cho |
| --- | --- | --- |
| Publication age | Hiện tại trừ thời điểm đăng ký | Cảnh báo tồn đọng, điều tra lâu chưa completion |
| Queue wait | Listener bắt đầu trừ lúc được phép xử lý | Tìm executor/backpressure |
| Listener duration | Từ lúc listener bắt đầu đến kết thúc một attempt | Phát hiện logic chậm và network timeout |
| Commit-to-effect latency | Tác động thành công trừ lúc nguồn commit | Đo SLO nghiệp vụ |
| Recovery lag | Thời gian từ khi được xem là cần phục hồi đến khi hoàn tất | Đo hiệu quả retry/runbook |

Các mốc chỉ có thể tính chính xác nếu hệ thống đã instrument tương ứng. Không coi `occurredAt` trong payload tự động là `committedAt`, và không tự nhận registry chứa đầy đủ mọi timestamp ở tất cả backend.

## 9. Xác định một publication đã “quá hạn”

Không nên cảnh báo mỗi khi `incomplete_count > 0`. Một listener đang hoạt động bình thường vẫn có thể chưa ghi completion. Thay vào đó, xác định **ngưỡng theo loại tác vụ**:

| Listener | Kỳ vọng minh họa | Chính sách quan sát gợi ý |
| --- | --- | --- |
| `notifications` | Email hoàn tất trong 30 giây | Cảnh báo khi quá ngưỡng vận hành của email |
| `reporting` | Projection cập nhật trong 2 phút | Theo dõi số tồn đọng và tuổi lớn nhất |
| `loyalty` | Điểm thưởng có thể trễ 1 phút | Cảnh báo những publication quá hạn |
| `analytics` batch | Cho phép xử lý nhiều phút | Ngưỡng cao hơn, đo throughput và backlog |

**Các số trên chỉ là ví dụ**, không phải chuẩn có sẵn của Spring Modulith. Thực tế phải dựa trên SLO nghiệp vụ và độ trễ ghi registry/commit/executor quan sát được.

Nên xem đồng thời:

- Số lượng publication incomplete tại từng listener.
- Tuổi của publication incomplete lâu nhất.
- Tốc độ incomplete tăng/giảm trong cửa sổ thời gian.
- Số publication hoàn tất trên một khoảng thời gian.
- Số lỗi listener, executor rejection và số lần phục hồi.

Một backlog tăng liên tục có thể chỉ ra **tốc độ event đến lớn hơn khả năng xử lý**, không chỉ một exception tại một event. Nếu listener mỗi giây xử lý 10 event nhưng nhận 15 event, tuổi publication sẽ tăng dù code không có bug trực tiếp.

Đừng gắn `eventId` hoặc `correlationId` (UUID thay đổi theo từng event) làm metric label: cardinality tăng rất lớn. Dùng `listenerTarget`, `eventType`, `status`, `errorCategory` làm nhãn có số lượng giá trị kiểm soát; giữ ID cụ thể trong log/traces và trang truy vấn được bảo vệ.

## 10. Một publication incomplete không nhất thiết là lỗi

Để diễn giải đúng, hãy lập **giả thuyết nguyên nhân** rồi kiểm tra bằng bằng chứng:

| Hiện tượng | Khả năng | Cách kiểm tra |
| --- | --- | --- |
| Publication mới tạo, chưa hoàn tất | Listener đang chờ executor/đang chạy | Queue depth, active threads, log listener start |
| Publication cũ, không có log start | JVM dừng trước dispatch; executor rejection; startup chưa phục hồi | Log khởi động, executor, cấu hình recovery |
| Có log listener start và exception | Lỗi trong listener, dependency hay dữ liệu | Stack trace với event/listener, health downstream |
| Có log “đã gửi email” nhưng vẫn incomplete | Process chết trước completion hoặc completion ghi lỗi | Kiểm tra trạng thái gửi/idempotency và log registry |
| Nhiều publication cùng loại lỗi deserialize | Thay schema/event type sau deploy | So sánh phiên bản producer/consumer và serializer |
| Một listener nhiều publication cũ, listener khác bình thường | Hotspot tại consumer đó | Pool, lock, circuit breaker, cấu hình riêng |
| Incomplete đã biến mất khi đọc lại | Listener vừa hoàn tất, recovery đã xử lý hoặc dữ liệu được dọn | Đối chiếu completed history và log nếu có |

**Không suy luận “listener chưa chạy” chỉ vì publication chưa hoàn tất**. Hãy nhớ trường hợp khó nhất: side effect bên ngoài thành công nhưng completion chưa kịp được ghi. Đây là lý do việc phục hồi cần **idempotency**, không chỉ thao tác “gọi lại”.

## 11. Quy trình điều tra vận hành từng bước

Một quy trình điều tra có thể được mô tả như sau:

~~~mermaid
flowchart TD
    Q["Truy vấn incomplete publication theo tuổi"] --> S{"Quá ngưỡng kỳ vọng?"}
    S -->|"Không"| M["Theo dõi; tránh retry khi đang chạy"]
    S -->|"Có"| T["Xác định listener đích + event"]
    T --> L{"Có log listener / exception?"}
    L -->|"Có"| E["Phân loại lỗi: tạm thời hay vĩnh viễn"]
    L -->|"Không"| X["Kiểm tra executor, restart, recovery"]
    E --> C{"Side effect có thể đã xảy ra?"}
    X --> C
    C -->|"Có hoặc không chắc"| I["Đối soát + kiểm tra idempotency"]
    C -->|"Chắc chắn chưa"| I
    I --> R["Recovery/resubmit có kiểm soát"]
    R --> V["Truy vấn lại + kiểm tra tác động nghiệp vụ"]
~~~

**Bước 1 — Khoanh vùng.** Lọc publication quá tuổi, theo listener và loại event. Không dump hàng triệu dòng cùng serialized payload.

**Bước 2 — Xác minh sự thật nguồn.** Ví dụ với `OrderConfirmed`, kiểm tra đơn đã commit đúng trạng thái. Nếu nguồn rollback, cần xem lại giả định về việc publication được lưu trong transaction nguồn.

**Bước 3 — Xác định listener đích.** Cùng một event có thể hoàn tất tại `reporting` nhưng còn pending ở `notifications`. Đừng phát lại toàn bộ command xác nhận đơn để “sửa notification”.

**Bước 4 — Tìm dấu vết.** Dùng `eventId`, `correlationId`, `orderId`, target listener và khoảng thời gian để tìm log/traces. Nếu event được serialize thành payload, cần đường deserialize an toàn/được phân quyền; không lấy dữ liệu nhạy cảm ra log tùy tiện.

**Bước 5 — Phân loại lỗi.** Timeout mạng có thể phục hồi. Sai JSON schema, enum bị xóa, thiếu dữ liệu bắt buộc hoặc lỗi logic nghiệp vụ vĩnh viễn cần sửa code/migration hoặc điều tra thủ công trước khi retry.

**Bước 6 — Chọn hành động.** Có thể chờ listener tiếp tục, mở rộng năng lực xử lý, sửa phụ thuộc downstream, dùng API resubmit tương ứng với version, hoặc chuyển sang quy trình can thiệp.

**Bước 7 — Đối soát hoàn tất.** Sau recovery, xác minh publication có completion và **tác động nghiệp vụ thật** đã đúng. Chỉ thấy publication biến mất không đủ kết luận email đã tới hộp thư của khách.

## 12. Phân biệt resubmit publication với publish event mới

Một lỗi rất nguy hiểm là xử lý publication chưa xong bằng cách gọi lại business command. Ví dụ:

~~~text
T1: orders xác nhận đơn, phát OrderConfirmed(E1)
T1: commit thành công
notifications: xử lý E1 lỗi, publication chưa hoàn tất

Sai: gọi lại confirmOrder() để cố tạo OrderConfirmed(E2)
Đúng: phục hồi publication dành cho NotificationListener của E1
~~~

Tại sao?

- `OrderConfirmed(E1)` diễn tả một sự thật đã xảy ra. Sự cố giao event **không làm sự thật ấy xảy ra lần hai**.
- Gọi lại command có thể không phát event vì đơn đã xác nhận, hoặc tạo event mới sai nghĩa nếu code thiếu idempotency.
- Resubmit **cùng publication/event logic** giữ được thông tin phục hồi và không làm các consumer đã thành công bị khởi động lại không cần thiết.
- Nếu listener đã có side effect nhưng completion lỗi, nó vẫn phải chống trùng ngay cả khi chỉ resubmit event cũ.

Spring Modulith có những cơ chế hỗ trợ quản lý/khôi phục publication, nhưng **tên API, phạm vi resubmit và chính sách tự động hay thủ công phụ thuộc phiên bản/cấu hình**. Khi triển khai, dùng đúng tài liệu và hợp đồng API của phiên bản đang chạy; không viết trực tiếp câu SQL `UPDATE completed_at = NOW()` để “sửa trạng thái”.

**Tự đánh dấu completed không thực hiện side effect.** Đó chỉ là thay metadata, có thể che mất tác vụ chưa xử lý. Tương tự, xóa publication incomplete khiến bằng chứng và đường khôi phục biến mất; không dùng xóa dữ liệu để làm dashboard “xanh”.

## 13. Idempotency và khả năng hoàn tất nhiều lần

Registry giúp theo dõi việc giao event nhưng không tạo bảo đảm **exactly-once end-to-end** cho mọi side effect.

Tình huống điển hình:

~~~mermaid
sequenceDiagram
    participant R as Registry
    participant N as NotificationListener
    participant G as Email Gateway
    R-->>N: OrderConfirmed(E1)
    N->>G: Gửi email (idempotency key K1)
    G-->>N: Đã nhận / thành công
    Note over N,R: JVM dừng trước khi completion được ghi
    R-->>N: Resubmit OrderConfirmed(E1)
    N->>G: Gửi với CÙNG key K1
    G-->>N: Trả kết quả đã xử lý trước
    N-->>R: Completion
~~~

Nếu gateway hỗ trợ idempotency key, giữ cùng khóa giữa các attempt. Nếu không, có thể dùng bảng trạng thái/outbox thông báo, unique constraint và cơ chế đối soát; tuy vậy việc “chỉ gửi đúng một email” với một cổng ngoài không hỗ trợ idempotency vẫn cần xử lý giới hạn của giao dịch phân tán.

| Tác động | Khóa idempotency gợi ý | Lưu ý |
| --- | --- | --- |
| Một email xác nhận cho mỗi đơn | `(orderId, notificationType)` | Nếu được phép gửi lại email hợp lệ, phải có khóa khác |
| Một lần áp dụng event vào projection | `(eventId, projectionName)` | Ghi dấu và cập nhật projection cùng transaction |
| Cộng một khoản thưởng cho mỗi đơn | `(orderId, rewardType)` | Phụ thuộc chính sách thưởng |
| Thực thi một command ngoài | `commandId` hoặc business idempotency key ổn định | Bên nhận phải tôn trọng cùng khóa khi retry |

`correlationId` không phải khóa deduplicate mặc định: một quy trình có nhiều event hợp lệ dùng cùng correlation ID.

## 14. Đọc dữ liệu trong lúc recovery đang chạy

Publication registry là dữ liệu **thay đổi đồng thời**. Có thể xảy ra:

1. Một tiến trình đang xử lý listener.
2. Dashboard truy vấn thấy publication chưa hoàn tất.
3. Một job recovery đồng thời chọn cùng publication để resubmit.
4. Hai attempt có thể chạy gần nhau nếu không có cơ chế claim/lock phù hợp.

Vì vậy:

- Không resubmit mọi incomplete ngay khi vừa thấy trong query, đặc biệt publication còn rất mới.
- Cần quy tắc **tuổi tối thiểu** hoặc phát hiện attempt bị treo và chính sách recovery rõ ràng.
- Nếu nhiều instance ứng dụng chia sẻ registry, đảm bảo cơ chế chọn/claim publication an toàn theo implementation đang dùng; không tự giả định API đọc làm nhiệm vụ lock.
- Listener vẫn phải idempotent vì lock/lease không loại bỏ tất cả trường hợp crash sau side effect.
- Ghi lại ai đã kích hoạt recovery, theo điều kiện nào, kết quả và thời điểm; tránh thao tác thủ công trùng với job tự động mà không biết.
- Tránh transaction đọc kéo dài trên bảng registry dưới tải, đặc biệt query toàn bảng và serialize payload lớn.

**Query là quan sát, không phải claim.** Đọc một publication incomplete không trao độc quyền xử lý nó cho người đọc. Cần dùng cơ chế recovery của framework hoặc coordination mà ứng dụng triển khai có bảo đảm đồng thời rõ ràng.

## 15. Bảo mật, retention và tương thích phiên bản

### 15.1. Payload có thể chứa thông tin nhạy cảm

Publication có thể lưu serialized event. Dù event nên chỉ chứa dữ liệu tối thiểu, nó vẫn có thể chứa `customerId`, `orderId` hoặc thông tin nghiệp vụ nhạy cảm. Vì vậy:

- Chỉ cấp quyền đọc registry cho vai trò vận hành đủ thẩm quyền.
- Tách màn hình tổng quan (count, age, listener) khỏi đường xem payload chi tiết.
- Không hiển thị toàn bộ event payload trong logs/metrics hoặc gửi tới dashboard không có kiểm soát truy cập.
- Lọc, che dữ liệu khi xuất báo cáo và tuân thủ chính sách lưu giữ dữ liệu của tổ chức.

### 15.2. Retention của completed và incomplete

Các implementation có thể xóa/di chuyển completed publications theo cấu hình. Điều đó không đồng nghĩa mất sự kiện; registry **không nhất thiết là audit log đầy đủ**. Với incomplete, xóa sớm có thể làm mất cơ hội phục hồi.

Tổ chức cần quy định:

1. Completed publication giữ bao lâu để hỗ trợ điều tra?
2. Incomplete vượt ngưỡng nào thì cảnh báo hoặc chuyển xử lý thủ công?
3. Sau khi xác minh lỗi vĩnh viễn, ai có quyền đóng sự cố và theo dõi kết quả?
4. Bằng chứng đối soát (ID, target, loại lỗi, hành động recovery) lưu ở đâu?

Không tùy tiện chỉnh chính sách retention chỉ để giảm kích thước bảng. Registry đang giữ **công việc cần hoàn tất**; dọn sai dữ liệu có thể gây bỏ sót nghiệp vụ.

### 15.3. Nâng cấp Spring Modulith và đổi tên listener

Publication thường cần lưu định danh target listener để có thể xác định người nhận khi resubmit. Nếu refactor bean, tên method/package, event type hoặc cấu hình serialization, một publication cũ có thể **không còn ánh xạ được vào listener mới**.

Trước deploy có thay đổi contract:

- Kiểm tra incomplete publications đang tồn tại và loại event liên quan.
- Xác minh bản ghi event cũ deserialize được với code mới.
- Xác minh target identifier cũ còn được nhận diện hoặc có migration/đường xử lý tương thích.
- Lên kế hoạch xử lý những publication tồn từ phiên bản trước thay vì mất dấu do rename.
- Kiểm tra adapter/SQL dashboard khi thay implementation registry hoặc schema.

## 16. Kiểm thử truy vấn publication chưa xong

Để kiểm thử đúng chủ đề, chỉ assert rằng listener được gọi là chưa đủ. Cần **kiểm tra registry phản ánh trạng thái incomplete và completed** theo từng listener.

### 16.1. Ma trận kiểm thử

| Kịch bản | Kết quả kỳ vọng |
| --- | --- |
| Event được publish trong transaction rồi commit; listener thành công | Publication của listener được ghi completion |
| Transaction nguồn rollback trước commit | Không có publication đã commit để phục hồi cho thay đổi nguồn ấy |
| Listener A thành công, B ném exception | A completed; B vẫn incomplete theo cơ chế registry đang dùng |
| Listener lỗi mạng tạm thời | B còn incomplete, có thể xử lý lại sau khi sửa lỗi |
| Listener đã side effect nhưng completion không được ghi | Recovery không tạo tác động trùng nhờ idempotency |
| Tạo nhiều publication cùng target | Query phân biệt theo publication/event và tuổi |
| Publication mới vừa được đăng ký | Không được kết luận lỗi nếu chưa quá ngưỡng |
| Lỗi deserialize event sau nâng cấp | Truy vấn vẫn xác định tồn đọng; cần xử lý compatibility trước khi resubmit |
| Hai instance cùng chạy recovery | Không gây trùng side effect, cơ chế claim/lock phù hợp |
| Backend dọn completed | Dashboard không coi “không thấy bản ghi completed” là “chưa từng xử lý” |

### 16.2. Unit test cho logic lọc tuổi

Ví dụ JUnit 5 + Mockito + AssertJ kiểm tra service quan sát mà không cần kết nối registry thực:

~~~java
package com.example.shop.operations;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import org.junit.jupiter.api.Test;

class PublicationHealthServiceTest {

    @Test
    void selectsOnlyPublicationsOlderThanThreshold() {
        var reader = mock(IncompletePublicationReader.class);
        var clock = Clock.fixed(
                Instant.parse("2026-02-01T12:00:00Z"),
                ZoneOffset.UTC);
        var service = new PublicationHealthService(reader, clock);
        var cutoff = Instant.parse("2026-02-01T11:58:00Z");
        var older = new IncompletePublicationView(
                "P1", "OrderConfirmed", "notifications",
                Instant.parse("2026-02-01T11:55:00Z"), "E1", "C1");

        when(reader.findRegisteredBefore(cutoff, 50))
                .thenReturn(List.of(older));

        var results = service.findStale(Duration.ofMinutes(2), 50);

        assertThat(results).containsExactly(older);
        verify(reader).findRegisteredBefore(cutoff, 50);
    }
}
~~~

Test này chỉ chứng minh **logic ứng dụng chọn cutoff/limit**. Nó không chứng minh adapter trả đúng incomplete từ Spring Modulith. Cần integration test cho đường truy vấn thật.

### 16.3. Integration test với publication registry thật

Một test tích hợp đáng tin nên:

1. Khởi tạo Spring context có transaction manager, backend registry bền vững, cấu trúc bảng và các listener đã cấu hình.
2. Tạo event `OrderConfirmed` từ transaction nguồn **thực sự commit**.
3. Để `NotificationListener` thành công và `LoyaltyListener` chủ động lỗi ở lần đầu.
4. Chờ async có timeout; truy vấn registry/adapter trong điều kiện ổn định.
5. Xác nhận publication của `LoyaltyListener` vẫn incomplete; của `NotificationListener` đã được ghi nhận hoàn tất theo implementation.
6. Sửa lỗi và kích hoạt recovery của phiên bản đang dùng; xác nhận publication được ghi completion.
7. Kiểm tra sổ điểm và thông báo không bị nhân đôi nếu cùng event được giao lại.

**Lưu ý:** test method `@Transactional` mặc định rollback ở cuối có thể khiến callback `AFTER_COMMIT` không chạy. Tổ chức test sao cho transaction nguồn commit thật; dùng polling/assertion với timeout thay cho `Thread.sleep` tùy ý. Nếu registry có cơ chế dọn completed, assert theo hợp đồng backend thay vì mặc định mọi completed row còn nằm trong cùng bảng.

## 17. Checklist vận hành

Trước khi kết luận một publication cần được xử lý lại, tự kiểm tra:

- [ ] Backend Event Publication Registry đang sử dụng là gì và đã cấu hình bền vững chưa?
- [ ] Publication này thuộc **event nào** và **listener đích nào**?
- [ ] Tuổi publication đã vượt ngưỡng hợp lý cho listener đó chưa?
- [ ] Listener có đang chạy, bị queue, đang giữ lock hay có exception?
- [ ] Transaction nguồn đã commit và event payload có còn đọc được không?
- [ ] Side effect có thể đã xảy ra trước khi completion bị mất không?
- [ ] Consumer có idempotency key/unique constraint phù hợp không?
- [ ] Phiên bản application mới có còn nhận đúng event type và listener target cũ không?
- [ ] Resubmit dựa trên API/khả năng của framework đã kiểm chứng, không chỉnh tay trạng thái SQL?
- [ ] Sau recovery, có kiểm tra **cả completion lẫn tác động nghiệp vụ thật** không?

Checklist này nhằm tránh hai sai lầm đối nghịch: **bỏ mặc publication tồn đọng** và **retry quá sớm khiến cùng tác động được thực hiện trùng**.

## 18. Bài thực hành: điều tra một listener chưa hoàn tất

Xây dựng ứng dụng Spring Modulith có module `orders`, `notifications` và `loyalty`. `orders` phát `OrderConfirmed(eventId, correlationId, orderId, occurredAt)` trong transaction. Hai module còn lại dùng `@ApplicationModuleListener`.

Tình huống: lần đầu `notifications` gửi thành công; `loyalty` gặp lỗi database và chưa ghi được điểm. Đơn đã commit.

Yêu cầu thực hành:

1. Cấu hình một Event Publication Registry bền vững thích hợp với database ứng dụng.
2. Thiết kế DTO `IncompletePublicationView` chứa publication ID, target listener, event type và registration time; không đưa payload nhạy cảm vào API quan sát.
3. Viết adapter đọc incomplete bằng **API hoặc schema thực tế đã kiểm chứng**. Thêm giới hạn số kết quả và bộ lọc tuổi.
4. Truy vấn và chứng minh publication của `loyalty` còn incomplete trong khi `notifications` đã hoàn tất.
5. Mô phỏng ứng dụng restart rồi kiểm tra xem bản ghi incomplete có còn để phục hồi không.
6. Sửa lỗi `loyalty` và kích hoạt cơ chế resubmit phù hợp với phiên bản đang dùng. Không gọi lại `orders.confirm(...)`.
7. Chạy lại truy vấn, kiểm tra completion và bảo đảm không cộng điểm hai lần khi event bị giao lại.
8. Thiết kế cảnh báo theo `incomplete_count`, `oldest_age` và listener target; giải thích tại sao `incomplete_count > 0` chưa chắc là lỗi.
9. Mô phỏng refactor tên listener hoặc cấu trúc event để nhận diện rủi ro compatibility với publication cũ.

**Câu hỏi tự đánh giá:**

- Một `OrderConfirmed` có hai transactional listener tương ứng mấy publication?
- Vì sao incomplete không chứng minh listener chưa từng chạy?
- Có thể truy vấn trực tiếp bảng tên `event_publication` trên mọi backend Spring Modulith không?
- Tuổi tính từ registration time có luôn bằng độ trễ từ commit không?
- Khi listener lỗi, vì sao không nên gọi lại lệnh xác nhận đơn để phát event mới?
- Vì sao cần idempotency dù đã dùng registry và recovery?
- Truy vấn incomplete có tự khóa bản ghi để chống hai instance resubmit cùng lúc không?

## 19. Ghi nhớ

**Truy vấn publication chưa xong** là cách nhìn vào **trạng thái giao application event theo từng listener**, không phải chỉ tra một cờ thành công chung của domain event. Trong Spring Modulith, registry bền vững giúp phát hiện publication chưa được ghi nhận hoàn tất sau khi transaction nguồn commit và hỗ trợ điều tra/khôi phục; nhưng **incomplete chỉ cho biết thiếu completion**, không tự xác định nguyên nhân hay bảo đảm side effect chưa từng xảy ra.

Hãy ưu tiên API công khai của phiên bản Spring Modulith đang dùng, hoặc adapter/read-only view được xác minh theo backend. Lọc theo listener, loại event và tuổi; kết hợp log, trace, executor, transaction, retry, idempotency và SLO. Việc phục hồi phải nhắm đúng publication, không phát sinh sự kiện nghiệp vụ giả hay cập nhật tay completion chỉ để loại bỏ cảnh báo. **Quan sát đúng, điều tra đúng và resubmit an toàn** là ba bước để application events giảm coupling mà vẫn vận hành đáng tin cậy.

**Tài liệu tham khảo chính thức:**

- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html)
- [Spring Modulith — Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Modulith — API Documentation](https://docs.spring.io/spring-modulith/docs/current/api/)
