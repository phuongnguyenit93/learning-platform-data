# Xử lý không theo thứ tự

## Mục tiêu bài học

Trong một ứng dụng Spring Modulith, producer có thể phát `OrderPaid` trước `OrderRefunded`, nhưng module `reporting` hoặc `loyalty` **không được mặc định giả định rằng sẽ xử lý xong `OrderPaid` trước `OrderRefunded`**. Listener bất đồng bộ, transaction riêng, xử lý cạnh tranh và việc phát lại một publication thất bại có thể khiến một sự kiện cũ được xử lý muộn hơn một sự kiện mới.

Bài này thuộc chương **Đảm bảo tin cậy** của **SPRING_MODULITH_APPLICATION_EVENTS**, với mục tiêu tổ chức giao tiếp giữa các module qua application events, giảm phụ thuộc và bảo vệ ranh giới nghiệp vụ. Chủ đề trực tiếp là **xử lý không theo thứ tự (out-of-order event processing)**. Bên cạnh publisher và listener, bài liên hệ xử lý sau commit, Event Publication Registry, retry, idempotency, kiểm thử và khả năng quan sát quá trình giao sự kiện.

Sau bài học, bạn cần phân biệt **thứ tự phát**, **thứ tự commit**, **thứ tự nhận** và **thứ tự hoàn tất**; nhận diện một event cũ nhưng được giao lại là gì; lựa chọn giữa **ledger cộng dồn**, **version + conditional update**, **buffer chờ event thiếu**, **state machine guard** và **reconciliation**; đồng thời thiết kế kiểm thử chứng minh consumer không ghi lùi trạng thái.

## 1. Thế nào là xử lý event không theo thứ tự?

Xét vòng đời của một đơn hàng:

1. `OrderPlaced` — đơn được tạo, `aggregateVersion = 1`.
2. `OrderPaid` — đơn được xác nhận thanh toán, `aggregateVersion = 2`.
3. `OrderRefunded` — đơn được xác nhận hoàn tiền, `aggregateVersion = 3`.

Đây là **thứ tự chuyển trạng thái nghiệp vụ mong muốn**. Module nguồn `orders` sở hữu ý nghĩa của các transition và phải bảo vệ các điều kiện xảy ra của chúng. Nhưng một module khác, ví dụ `reporting`, có thể nhận hoặc hoàn tất phản ứng theo thứ tự `3 → 2`, đặc biệt khi event số 2 bị lỗi rồi retry.

~~~mermaid
sequenceDiagram
    participant Orders as orders / Producer
    participant Registry as Event publication
    participant Reporting as reporting / Consumer

    Orders->>Registry: OrderPaid (v2)
    Orders->>Registry: OrderRefunded (v3)
    Registry-->>Reporting: Giao OrderPaid (v2)
    Reporting--xRegistry: Lỗi tạm thời, chưa hoàn tất
    Registry-->>Reporting: Giao OrderRefunded (v3)
    Reporting->>Reporting: Xử lý v3
    Registry-->>Reporting: Resubmit OrderPaid (v2)
    Note over Reporting: V2 đến sau V3
~~~

Sơ đồ minh họa một **khả năng xảy ra**, không khẳng định Spring Modulith luôn đảo thứ tự. Dù các event được phát tuần tự, trình tự thực thi của asynchronous listener và retry không nhất thiết duy trì quan hệ tuần tự đó.

Nếu consumer chỉ viết:

~~~java
// Sai khi không có quy tắc bảo vệ thứ tự:
void on(OrderPaid event) {
    projection.setStatus("PAID");
}

void on(OrderRefunded event) {
    projection.setStatus("REFUNDED");
}
~~~

thì sau khi xử lý `OrderRefunded(v3)`, lần nhận muộn `OrderPaid(v2)` có thể ghi lùi trạng thái projection thành `PAID`. Người dùng sẽ nhìn thấy đơn “đã thanh toán” dù nguồn đã ghi nhận hoàn tiền.

### Tại sao lỗi này nghiêm trọng?

- Dashboard doanh thu có thể tính sai vì cập nhật trạng thái cũ ghi đè trạng thái mới.
- Module `loyalty` có thể cộng điểm sau khi điểm đã bị thu hồi.
- Module `tickets` có thể phát hành lại vé đã hủy.
- Module `notifications` có thể gửi email “thanh toán thành công” rất muộn, sau email “đã hoàn tiền”.
- Một consumer nhận lại event có thể tạo **tác động bên ngoài không thể rollback**, kể cả khi database của nó có trạng thái đúng.

Vì vậy, xử lý out-of-order không chỉ là sắp xếp danh sách theo thời gian. Đó là bài toán **đảm bảo tính đúng đắn của hiệu ứng consumer** khi lịch giao và xử lý không trùng với thứ tự nghiệp vụ.

## 2. Bốn thứ tự cần phân biệt

Một event có thể đi qua nhiều mốc khác nhau. Không nên gom tất cả thành khái niệm “thứ tự event”.

| Loại thứ tự | Nguồn xác định | Có thể bị đảo hoặc khác nhau? |
| --- | --- | --- |
| **Thứ tự nghiệp vụ/aggregate** | Quy tắc state transition của module nguồn, thường kèm version hoặc sequence | Cần được producer bảo vệ khi có ghi đồng thời |
| **Thứ tự publish** | Thời điểm gọi `ApplicationEventPublisher.publishEvent(...)` | Có thể khác thứ tự commit giữa các transaction cạnh tranh |
| **Thứ tự transaction commit** | Transaction manager/database xác nhận commit thành công | Hai transaction đồng thời không nhất thiết commit theo thứ tự chúng bắt đầu |
| **Thứ tự consumer nhận/hoàn tất** | Scheduler, executor, listener, lỗi, retry và transaction consumer | Có thể khác publish và commit; mỗi listener có lịch riêng |

Với một luồng có nhiều consumer, `reporting` có thể hoàn tất `v3` trước `v2`, trong khi `notifications` hoàn tất `v2` trước `v3`. **Không có một đồng hồ hoàn tất chung cho mọi module**.

~~~mermaid
flowchart LR
    Source["orders: lịch sử nguồn<br/>v1 → v2 → v3"] --> Dispatch["Spring application events<br/>Sau commit"]
    Dispatch --> Loyalty["loyalty<br/>v2 → v3"]
    Dispatch --> Reporting["reporting<br/>v3 → v2 (retry)"]
    Dispatch --> Notifications["notifications<br/>v2, v3 với độ trễ riêng"]
~~~

**`occurredAt` không phải bộ bảo đảm thứ tự.** Timestamp chỉ là thời điểm được producer hoặc nguồn bên ngoài ghi nhận; hai event có thể trùng độ phân giải thời gian, các máy có thể lệch đồng hồ, và một transaction có thể commit sau transaction bắt đầu muộn hơn. Nếu thứ tự là bất biến nghiệp vụ, cần **sequence/version được duy trì nhất quán bởi producer** chứ không chỉ `Instant.now()`.

## 3. Vì sao Spring Modulith có thể gặp out-of-order?

Spring application events là cơ chế trong một ứng dụng, không phải mặc nhiên là queue có thứ tự toàn cục. Một số nguyên nhân phổ biến:

### 3.1 Listener bất đồng bộ

`@ApplicationModuleListener` là tiện ích Spring Modulith tổ chức phản ứng sau commit, bất đồng bộ và trong transaction riêng. Khi hai event được publish gần nhau, chúng có thể được xử lý ở các luồng khác nhau hoặc cùng thời gian. Thời gian chạy, contention database và lịch executor có thể khiến event đến sau hoàn tất trước.

~~~text
T1 commit OrderPaid(v2)     → executor bắt đầu handler v2: mất 800 ms
T2 commit OrderRefunded(v3) → executor bắt đầu handler v3: mất 20 ms

Kết quả: handler v3 hoàn tất trước handler v2.
~~~

Không được dựa vào tên phương thức listener, thứ tự import Java hoặc thứ tự commit của các transaction consumer để suy ra tất cả sẽ chạy đúng thứ tự nghiệp vụ.

### 3.2 Retry hoặc resubmit publication cũ

Sau khi transaction nguồn commit, một consumer có thể gặp lỗi. Khi có **Event Publication Registry** với storage và cơ chế resubmit phù hợp, publication chưa hoàn tất có thể được phát lại. Trong thời gian đó các publication mới vẫn có thể được xử lý.

~~~text
10:00:00  OrderPaid(v2) đã commit, reporting lỗi
10:00:02  OrderRefunded(v3) đã commit, reporting xử lý được
10:01:00  OrderPaid(v2) được resubmit
~~~

Nếu consumer cập nhật projection bằng “event đến cuối cùng thắng”, `v2` sẽ ghi đè `v3`. Cơ chế retry **tăng độ tin cậy giao lại**, nhưng không tự bảo vệ thứ tự nghiệp vụ.

### 3.3 Ghi đồng thời ở producer

Hai request có thể cùng đọc một aggregate ở trạng thái cũ, cùng phát event, rồi cạnh tranh commit. Nếu producer không có **optimistic locking**, **pessimistic locking**, constraint hoặc một cơ chế serialize theo aggregate, ngay cả thứ tự trạng thái nguồn cũng có thể mơ hồ.

Gắn `aggregateVersion = 2` bằng cách tăng biến cục bộ **không đủ** khi hai transaction có thể cùng ghi version 2. Version phải được cấp và ghi **cùng giao dịch** với transition nghiệp vụ, có kiểm soát cạnh tranh và retry khi conflict.

### 3.4 Các con đường phân phối khác nhau

Trong một ứng dụng thực tế, consumer có thể nhận event từ listener trong JVM, một adapter tích hợp hoặc một luồng replay. Nếu nhiều đường đưa cùng event đến consumer, hoặc message đi qua broker/queue ngoài, thứ tự giao còn phụ thuộc cấu hình từng đường và cách phân vùng. Không suy ra rằng event internal Spring Modulith mặc nhiên có thứ tự như một partition Kafka hay một hàng đợi xử lý tuần tự.

### 3.5 Khác biệt về độ dài tác vụ

Một event đòi hỏi cập nhật báo cáo phức tạp có thể xử lý lâu hơn event sau đó chỉ cần đổi trạng thái. Ngay cả khi listener được gọi theo thứ tự, **thứ tự commit hiệu ứng** có thể khác nếu mỗi phản ứng chạy trong transaction độc lập.

## 4. Out-of-order không đồng nghĩa duplicate

Hai vấn đề này liên quan nhưng cần hai lớp bảo vệ khác nhau.

| Tình huống | Ví dụ | Câu hỏi cần giải quyết |
| --- | --- | --- |
| **Duplicate** | `OrderPaid(E2, v2)` được giao hai lần | Tác động của cùng event có được làm nhiều lần không? |
| **Out-of-order** | `OrderRefunded(E3, v3)` được xử lý trước `OrderPaid(E2, v2)` | Consumer có áp dụng sai transition hoặc bỏ lỡ tác động cần thiết không? |
| **Gap** | Consumer đã xử lý `v1`, nhận `v3` nhưng chưa thấy `v2` | Có được phép áp dụng `v3` mà thiếu `v2` không? |
| **Concurrent handling** | Hai worker cùng nhận `v2` hoặc `v3` | Có bảo vệ race condition trong database không? |
| **Stale event** | Consumer đang ở `v3`, nhận `v2` muộn | Có bỏ qua hoặc điều tra mà không ghi lùi không? |
| **Conflicting events** | Hai event cùng `orderId`, cùng `version` nhưng payload khác | Producer/contract có vi phạm tính nhất quán không? |

**Idempotency theo `eventId` giải quyết duplicate**, nhưng không tự giải quyết out-of-order. Ngược lại, quy tắc “chỉ nhận version tăng” có thể ngăn ghi lùi trạng thái, nhưng vẫn có thể **bỏ sót một khoản tiền hoặc một side effect** nếu event bị bỏ qua chỉ vì tới muộn.

Phải xác định rõ consumer đang xây dựng **projection ảnh chụp trạng thái cuối** hay xử lý **từng tác động độc lập**.

## 5. Chọn chiến lược theo đặc tính nghiệp vụ

Không có một giải pháp duy nhất thích hợp cho tất cả event.

| Loại phản ứng | Ví dụ | Hướng thiết kế |
| --- | --- | --- |
| **Projection snapshot** | Đồng bộ trạng thái hiện tại, số tiền đã hoàn lũy kế | Conditional update theo version mới hơn, nếu snapshot đủ thông tin |
| **Delta không thể bỏ sót** | Cộng/trừ doanh thu theo mỗi giao dịch | Ledger idempotent cho từng event hoặc áp dụng sequence liền kề |
| **State machine** | `PAID → REFUNDED`, `ISSUED → CANCELLED` | Validate transition và version; không ghi lùi |
| **Tác dụng không thể hoàn tác** | Gửi vé, email, gọi nhà cung cấp bên ngoài | Kiểm tra trạng thái hiện tại, idempotency và quy trình compensation/reconciliation |
| **Xử lý tuần tự nghiêm ngặt** | Mỗi event là một bước bắt buộc phải hoàn tất trước bước tiếp | Serialize theo aggregate hoặc orchestration rõ ràng |
| **Báo cáo có thể tái tạo** | Dashboard xây từ dữ liệu nguồn | Lưu cursor/version và có quy trình đối soát, rebuild |

Câu hỏi đầu tiên nên là: **Nếu nhận event version 3 trước version 2, có đủ thông tin để tạo ra kết quả đúng mà không cần version 2 không?** Nếu có, một snapshot mới hơn có thể thay thế snapshot cũ. Nếu không, phải giữ lại event đến sớm hoặc xử lý nó như một đơn vị tác động độc lập, không được âm thầm bỏ qua.

## 6. Thiết kế contract có version để bảo vệ thứ tự

Một contract có thể chứa **version tăng dần theo aggregate**. Với ví dụ `orders`, hai event công khai có thể là:

~~~java
package com.example.shop.orders.events;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record OrderPaid(
        UUID eventId,
        UUID orderId,
        UUID paymentId,
        long aggregateVersion,
        BigDecimal paidAmount,
        String currency,
        Instant occurredAt
) {}
~~~

~~~java
package com.example.shop.orders.events;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record OrderRefunded(
        UUID eventId,
        UUID orderId,
        UUID refundId,
        long aggregateVersion,
        BigDecimal refundedAmount,
        String currency,
        Instant occurredAt
) {}
~~~

Các contract này được module `orders` sở hữu. Các field có vai trò:

| Field | Ý nghĩa | Phòng tránh lỗi gì? |
| --- | --- | --- |
| `eventId` | Định danh một occurrence nghiệp vụ | Phát hiện cùng event được giao lại |
| `orderId` | Khóa aggregate nguồn | Tách dòng xử lý và version theo từng đơn |
| `paymentId` / `refundId` | Định danh giao dịch thực tế | Đối chiếu nghiệp vụ, xử lý callback lặp |
| `aggregateVersion` | Số thứ tự chuyển trạng thái nhất quán của aggregate | Nhận diện event cũ, event mới và khoảng trống |
| `paidAmount` / `refundedAmount` | Snapshot giá trị của tác động nghiệp vụ | Xây ledger hoặc bút toán tài chính |
| `currency` | Đơn vị tiền | Tránh cộng các khoản tiền khác đơn vị |
| `occurredAt` | Thời điểm nguồn tạo event theo contract | Truy vết và đo độ trễ, **không** làm khóa thứ tự |

### Version có thực sự đáng tin không?

Version phải được producer **cấp phát tuần tự theo cùng aggregate**, bảo vệ trong transaction nguồn. Một phương án là lock aggregate khi đọc, cập nhật trạng thái và version rồi publish event **trong cùng transaction**. Một phương án khác là dùng optimistic locking với retry transaction thất bại và phát lại event chỉ cho transition cuối cùng được commit.

Ví dụ thuật toán producer, không phải API Spring Modulith:

~~~text
BEGIN T1
  lock Order(orderId) hoặc kiểm soát optimistic version
  xác nhận transition nghiệp vụ hợp lệ
  version mới = version đã lưu + 1
  lưu trạng thái và version mới trong T1
  publish Event(orderId, version mới, ...)
COMMIT T1
~~~

Nếu transaction rollback, cả trạng thái/version và publication bền vững cùng T1 (khi registry được cấu hình phù hợp) phải rollback. **Đừng lấy giá trị `@Version` JPA trước khi Hibernate thực sự cập nhật làm bảo đảm version sau commit** nếu chưa xác minh thời điểm tăng version/flush của provider. Nên có một quy ước cấp version rõ ràng và integration test với database thật.

### Version là theo aggregate, không phải toàn hệ thống

`OrderPaid(orderId=A, v2)` và `OrderPaid(orderId=B, v2)` hoàn toàn có thể cùng version. Consumer phải so version trong phạm vi **`orderId`**. Không so một counter toàn cục không có trong contract, cũng không dùng `eventId` UUID để suy ra trình tự.

Nếu chỉ một phần event của aggregate được công bố cho consumer, version có thể **nhảy số** do các transition khác không liên quan. Khi cần áp dụng tuần tự, hãy quyết định dùng **sequence dành riêng cho event stream đó** hoặc cho consumer truy xuất snapshot công khai; không giả định mọi version thiếu đều là event phải nhận.

## 7. Chiến lược A — Latest snapshot wins, nhưng phải dùng version

Khi consumer chỉ cần **trạng thái mới nhất** của một aggregate và mỗi event chứa **snapshot đầy đủ**, consumer có thể áp dụng phiên bản lớn nhất. Ví dụ `OrderStateSnapshotChanged` chứa:

~~~java
package com.example.shop.orders.events;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record OrderStateSnapshotChanged(
        UUID eventId,
        UUID orderId,
        long aggregateVersion,
        String currentStatus,
        BigDecimal paidTotal,
        BigDecimal refundedTotal,
        String currency,
        Instant occurredAt
) {}
~~~

Ví dụ này giả định `currentStatus`, `paidTotal`, `refundedTotal` được tính và đưa vào event tại **cùng phiên bản trạng thái nguồn**, không phải lấy rời rạc qua API không có snapshot nhất quán.

Khi `OrderStateSnapshotChanged(v3)` đến trước `v2`, `reporting` có thể cập nhật ngay snapshot v3. Khi v2 đến muộn, consumer nhận ra **version thấp hơn** và bỏ qua cập nhật để không ghi lùi.

Câu lệnh SQL minh họa cho một row đã tồn tại:

~~~sql
UPDATE reporting_order_state
SET status = :status,
    paid_total = :paid_total,
    refunded_total = :refunded_total,
    currency = :currency,
    last_version = :incoming_version
WHERE order_id = :order_id
  AND last_version < :incoming_version;
~~~

Điều kiện `last_version < :incoming_version` cần được thực hiện **nguyên tử ở database**, không tách thành một `SELECT` rồi `UPDATE` không có khóa. Với row chưa tồn tại, cần upsert/insert có kiểm soát xung đột và cùng nguyên tắc version, chẳng hạn dùng cú pháp `ON CONFLICT` riêng của database.

### Vì sao version quan trọng hơn timestamp?

Giả sử v3 xử lý lúc 11:00:05, v2 được retry lúc 11:01:00. Nếu dùng **thời gian nhận gần nhất thắng**, v2 trở thành “mới hơn” một cách sai lầm. Nhưng so version thì `2 < 3` cho thấy v2 là trạng thái cũ, nên không được ghi đè.

### Điều kiện để latest-wins là an toàn

- Event chứa **đủ snapshot** để tái tạo trạng thái consumer cần, không chỉ một delta.
- Version được cấp đáng tin cậy theo aggregate và phản ánh thứ tự trạng thái nguồn.
- Consumer chỉ cần **trạng thái cuối**; không có yêu cầu phải thực hiện riêng mọi tác động trung gian.
- Update có điều kiện/version là nguyên tử khi nhiều consumer thread cùng ghi.
- Có cách sửa chữa khi một event mới nhất bị mất hoặc không thể áp dụng, ví dụ reconciliation.

**Phản ví dụ:** nếu `v2` là “cộng 100.000 đồng doanh thu” và `v3` là “trừ 30.000 đồng hoàn tiền”, **chỉ giữ v3** sẽ bỏ mất khoản cộng 100.000 đồng. Đó không phải projection snapshot; phải dùng chiến lược delta khác.

## 8. Chiến lược B — Ledger độc lập, tác động cộng dồn có tính giao hoán

Đối với điểm thưởng hoặc doanh thu phát sinh từ từng giao dịch, đôi khi **thứ tự đến không cần quyết định tổng cuối** nếu từng tác động có thể biểu diễn bằng bút toán độc lập và áp dụng theo phép cộng đúng quy tắc.

Ví dụ một payment +100 điểm, một refund -30 điểm:

~~~text
Áp dụng paid(+100) rồi refund(-30) = +70
Áp dụng refund(-30) rồi paid(+100) = +70
~~~

Phép cộng có tính **giao hoán** về mặt số học, nhưng điều kiện nghiệp vụ không tự giao hoán. Nếu “không được trừ điểm khi chưa có điểm”, “không cho số dư âm” hoặc “refund không vượt paid” là bất biến thực thi ở thời điểm ghi, thì thứ tự vẫn quan trọng. Cần thiết kế chính sách tạm giữ/chờ, hoặc một ledger cho phép bút toán âm có đối soát.

~~~sql
CREATE TABLE loyalty_event_ledger (
    source_event_id VARCHAR(36) PRIMARY KEY,
    order_id VARCHAR(36) NOT NULL,
    event_type VARCHAR(60) NOT NULL,
    points_delta INTEGER NOT NULL,
    source_version BIGINT NOT NULL,
    processed_at TIMESTAMP WITH TIME ZONE NOT NULL
);
~~~

Ý tưởng:

~~~text
on OrderPaid(E2):
    ghi ledger(E2, +100) nếu E2 chưa tồn tại

on OrderRefunded(E3):
    ghi ledger(E3, -30) nếu E3 chưa tồn tại

số điểm phát sinh = SUM(points_delta) theo chính sách
~~~

`source_event_id` bảo vệ **duplicate event**, còn `refundId` hoặc khóa nghiệp vụ khác có thể cần thêm ràng buộc để phòng producer phát **nhiều eventId cho cùng refund**.

Nếu áp dụng theo ledger, event cũ đến sau không được phép thay thế một snapshot mới bằng “trạng thái đã thanh toán”. Nó chỉ bổ sung **bút toán đã có căn cứ nghiệp vụ**, theo quy tắc kế toán/điểm đã định nghĩa.

### Trường hợp ledger không được tùy tiện bỏ qua thứ tự

Đối với vé, việc “phát hành vé” và “hủy vé” không thể coi như hai phép cộng số học độc lập. Nếu event hủy đến trước phát hành, consumer cần tránh phát hành lại vé sau đó. Tương tự, email đã gửi không thể được trừ bằng “email -1”. Khi side effect **không giao hoán** hoặc **không đảo ngược**, phải dùng state machine, version/fencing, hoặc quy trình chờ/đối soát.

## 9. Chiến lược C — Áp dụng tuần tự theo version và buffer khi có gap

Một consumer có thể yêu cầu **không bỏ qua bất kỳ transition nào**. Ví dụ một process manager cần nhìn thấy `OrderPaid(v2)` trước khi có thể xử lý `OrderRefunded(v3)`.

Consumer duy trì `lastAppliedVersion` **cho từng aggregate**:

- Nếu `incomingVersion == lastAppliedVersion + 1`: được phép áp dụng event kế tiếp.
- Nếu `incomingVersion <= lastAppliedVersion`: kiểm tra trùng/stale và xử lý an toàn, không ghi lùi.
- Nếu `incomingVersion > lastAppliedVersion + 1`: có **gap**; không áp dụng ngay nếu bước trước là điều kiện cần thiết.

~~~mermaid
flowchart TD
    Start["Nhận event E với aggregateVersion = v"] --> Lock["Lock state của orderId"]
    Lock --> Compare{"So với lastAppliedVersion"}
    Compare -->|"v = last + 1"| Apply["Áp dụng event trong transaction"]
    Apply --> Update["Ghi lastAppliedVersion = v"]
    Update --> Drain["Kiểm tra pending event version kế tiếp"]
    Compare -->|"v <= last"| Old["Xác minh duplicate/stale, không ghi lùi"]
    Compare -->|"v > last + 1"| Pending["Lưu pending hoặc báo lỗi để retry"]
    Pending --> Wait["Phát hiện gap, đối soát, chờ event thiếu"]
    Drain --> Lock
~~~

Một bảng state và bảng pending có thể có dạng:

~~~sql
CREATE TABLE consumer_order_cursor (
    order_id VARCHAR(36) PRIMARY KEY,
    last_applied_version BIGINT NOT NULL
);

CREATE TABLE pending_order_event (
    event_id VARCHAR(36) PRIMARY KEY,
    order_id VARCHAR(36) NOT NULL,
    aggregate_version BIGINT NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    payload TEXT NOT NULL,
    first_seen_at TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR(30) NOT NULL,
    UNIQUE (order_id, aggregate_version)
);
~~~

Đây là schema **minh họa**. Với hệ thống thật, cần cân nhắc version của schema, encoding của payload, retention, chỉ mục, bảo mật và việc **không lưu dữ liệu nhạy cảm** không cần thiết.

### Khi nhận version bị thiếu

Giả sử cursor đang ở `v1`, consumer nhận `v3`. Hai cách xử lý hợp lệ nhưng có trách nhiệm khác nhau:

**Cách 1 — Giữ publication chưa hoàn tất:** ném một lỗi có phân loại `MissingPredecessor` hoặc trả về đường xử lý lỗi để publication của listener còn dang dở, sau đó retry khi `v2` đã xử lý. Cần retry có **backoff**, tránh lặp quá nhanh và giới hạn thời gian chờ. Nếu `v2` không bao giờ xuất hiện, phải cảnh báo và điều tra, không treo vô hạn.

**Cách 2 — Nhận trách nhiệm vào inbox/pending bền vững:** consumer **ghi event v3 vào bảng pending trong transaction riêng**, sau đó trả về thành công cho listener. Từ thời điểm này, **ứng dụng consumer phải bảo đảm có worker/quy trình phục hồi pending**; registry có thể coi publication đã hoàn tất. Nếu pending chỉ nằm trong bộ nhớ hoặc không có worker phục hồi, việc “ACK rồi để đó” sẽ làm mất khả năng xử lý.

Điều quan trọng: `pending` phải được ghi **trước** khi consumer công bố đã tiếp nhận trách nhiệm. Không được log “đã cache event” rồi return trong khi không có storage bền vững.

### Thuật toán áp dụng tuần tự có khóa

~~~text
BEGIN transaction consumer T2
  lock consumer_order_cursor(orderId)

  nếu eventId đã APPLIED:
      COMMIT, kết thúc idempotent

  nếu incomingVersion = lastAppliedVersion + 1:
      kiểm tra transition nghiệp vụ
      ghi hiệu ứng + dấu APPLIED theo eventId
      tăng lastAppliedVersion
      thử drain pending theo version liền kề
  nếu incomingVersion > lastAppliedVersion + 1:
      ghi PENDING bền vững hoặc thất bại có chủ đích để retry
  nếu incomingVersion <= lastAppliedVersion:
      xác minh event thực sự đã xử lý;
      nếu không có dấu vết, phát cảnh báo dữ liệu không nhất quán

COMMIT transaction consumer T2
~~~

Đây là pseudocode, không phải API có sẵn của Spring Modulith. Transaction lock và unique constraint là phần quan trọng khi hai listener thread xử lý **cùng `orderId`**. Nếu chỉ so version trên bộ nhớ rồi ghi bằng hai thread, cả hai có thể vượt qua kiểm tra và gây lỗi.

### Một bẫy của gap detection

Nếu event stream chỉ gồm `OrderPaid(v2)` và `OrderRefunded(v5)`, các version v3/v4 có thể thuộc transition **không phát event cho consumer này**. Khi đó consumer áp dụng quy tắc `last + 1` một cách máy móc sẽ treo mãi. Hãy dùng **sequence chuyên biệt cho stream consumer cần**, công bố tất cả event liên quan, hoặc chuyển sang snapshot/cách đối soát phù hợp.

## 10. Chiến lược D — State machine guard, không ghi lùi trạng thái

Với một projection hoặc quy trình phát hành vé, có thể giới hạn các transition hợp lệ:

~~~text
CREATED → PAID → REFUNDED
   |
   └────→ CANCELLED
~~~

Khi nhận `OrderPaid(v2)` sau `OrderRefunded(v3)`, consumer không được chuyển `REFUNDED → PAID` chỉ vì handler nhận event cũ. State machine guard kiểm tra **trạng thái hiện tại** và **version hợp lệ**.

Ví dụ Java minh họa cho một projection **chỉ phản ánh trạng thái**, không tự phát hành side effect:

~~~java
enum OrderState {
    CREATED, PAID, REFUNDED, CANCELLED
}

final class OrderProjection {
    private OrderState state;
    private long lastVersion;

    // Method giả định gọi khi row đã được khóa trong transaction consumer.
    void applyPaid(long incomingVersion) {
        if (incomingVersion <= lastVersion) {
            return;
        }
        if (state != OrderState.CREATED
                || incomingVersion != lastVersion + 1) {
            throw new IllegalStateException("Missing or invalid transition");
        }
        state = OrderState.PAID;
        lastVersion = incomingVersion;
    }

    void applyRefunded(long incomingVersion) {
        if (incomingVersion <= lastVersion) {
            return;
        }
        if (state != OrderState.PAID
                || incomingVersion != lastVersion + 1) {
            throw new IllegalStateException("Missing or invalid transition");
        }
        state = OrderState.REFUNDED;
        lastVersion = incomingVersion;
    }
}
~~~

Lớp minh họa này **không tự đủ an toàn cho concurrent processing**: cần lock/optimistic concurrency và transaction khi đọc-ghi `OrderProjection`; cần phân loại duplicate, gap, dữ liệu sai và khi nào retry. Nó cũng cố ý giả định **mỗi version liền kề có event tương ứng**. Nếu không có giả định đó, cần chỉnh thiết kế sequence.

Không nên biến mọi transition không hợp lệ thành retry vô hạn. Ví dụ `OrderRefunded` đến khi đơn `CANCELLED` vì producer phát event trái quy tắc thì phải điều tra hoặc chuyển sang đường sửa dữ liệu, không chỉ chạy lại liên tục.

### Side effect không thể đảo ngược

Với module `tickets`, `TicketIssued` sau `TicketCancelled` không chỉ làm sai một trường trạng thái: nó có thể tạo mã vé và gửi cho khách. Cần lưu dấu **effect key** (`reservationId` hoặc `eventId`), kiểm tra trạng thái nghiệp vụ ngay trước side effect, có fencing/version và chính sách xử lý khi thao tác ngoài database đã xảy ra. Nếu yêu cầu “không bao giờ phát hành sau khi hủy” là bất biến mạnh, có thể cần điều phối đồng bộ hoặc workflow chuyên dụng thay vì chỉ đăng ký hai listener async.

## 11. Chiến lược E — Serialize theo aggregate, nhưng phải rõ phạm vi

Một cách giảm out-of-order là chỉ cho **một luồng xử lý** cập nhật consumer state của **cùng `orderId`** tại một thời điểm.

Những lựa chọn tùy hạ tầng:

- **Lock database theo `orderId`** hoặc optimistic concurrency khi áp dụng event.
- **Keyed executor/queue**: các event cùng aggregate đi qua cùng một worker hoặc partition có thứ tự.
- **Broker có partition theo khóa aggregate** nếu đã externalize event; phải kiểm tra semantics thực tế khi retry và consumer rebalance.
- **Workflow/process manager** điều phối các bước liên quan chặt chẽ.

Quan trọng: **serialize execution không tự phục hồi đúng thứ tự nếu event v2 bị thiếu hoặc được resubmit sau v3**. Một worker tuần tự vẫn có thể nhận chuỗi `v3, v2` và áp dụng sai nếu không có version/transition guard. Vì vậy serialize thường cần đi cùng **kiểm soát version, idempotency và cơ chế gap/recovery**.

Không nên cấu hình toàn hệ thống chỉ dùng một thread để “giải quyết thứ tự” vì sẽ tạo nút thắt cổ chai. Mục tiêu là **tuần tự theo aggregate cần bảo vệ**, cho phép các `orderId` độc lập xử lý song song.

## 12. Spring Modulith: publish, after commit và registry trong bài toán thứ tự

Producer phát event bằng `ApplicationEventPublisher` khi transaction nguồn đang hoạt động. Consumer thường dùng `@ApplicationModuleListener` để phản ứng sau commit, bất đồng bộ và trong transaction riêng.

### Producer và contract công khai

Một cấu trúc package minh họa:

~~~text
com.example.shop
├── orders
│   ├── events
│   │   ├── package-info.java
│   │   ├── OrderPaid.java
│   │   └── OrderRefunded.java
│   └── internal
│       └── OrderLifecycleService.java
├── loyalty
│   └── internal
│       └── LoyaltyEventListener.java
└── reporting
    └── internal
        └── OrderProjectionListener.java
~~~

Trong `orders/events/package-info.java`:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.orders.events;
~~~

Trong `reporting/package-info.java`:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "orders::events"
)
package com.example.shop.reporting;
~~~

Đây là cách bảo vệ **phụ thuộc mã nguồn**. Annotation `@NamedInterface` hoặc `allowedDependencies` không làm event được giao đúng thứ tự, không tạo hàng đợi và không thay thế idempotency.

### Consumer có hai handler và một policy xử lý chung

~~~java
package com.example.shop.reporting.internal;

import com.example.shop.orders.events.OrderPaid;
import com.example.shop.orders.events.OrderRefunded;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderProjectionListener {

    private final OrderProjectionProcessor processor;

    OrderProjectionListener(OrderProjectionProcessor processor) {
        this.processor = processor;
    }

    @ApplicationModuleListener
    void on(OrderPaid event) {
        processor.applyPaid(
                event.eventId(),
                event.orderId(),
                event.aggregateVersion(),
                event.paidAmount(),
                event.currency()
        );
    }

    @ApplicationModuleListener
    void on(OrderRefunded event) {
        processor.applyRefunded(
                event.eventId(),
                event.orderId(),
                event.aggregateVersion(),
                event.refundedAmount(),
                event.currency()
        );
    }
}
~~~

`OrderProjectionProcessor` là service **minh họa** của `reporting`, không phải API Spring Modulith. Hai method phải chọn đúng một trong các chiến lược đã trình bày: snapshot versioned, ledger, hoặc ordered state machine. Ví dụ này sử dụng **tác động delta theo event**, nên **không được chỉ bỏ qua event cũ dựa vào version nếu vẫn cần ghi khoản tiền của event đó**.

Với `@ApplicationModuleListener`, mỗi handler phản ứng trong một transaction consumer riêng theo cơ chế annotation chuẩn. Một handler thất bại không rollback được transaction nguồn đã commit. Nếu consumer cần tự lưu pending hoặc ledger, mọi thao tác đọc khóa, chống trùng và ghi hiệu ứng phải được tổ chức nguyên tử trong transaction xử lý phù hợp.

### Registry giúp giao lại, không thay thế thứ tự nghiệp vụ

**Event Publication Registry** của Spring Modulith giúp theo dõi publication dành cho các transactional listener được hỗ trợ. Với repository bền vững đã cấu hình và việc publish trong transaction nguồn phù hợp, publication có thể được ghi cùng transaction với dữ liệu nguồn. Nếu listener không hoàn tất, hệ thống có thể phát hiện và **resubmit** theo chiến lược vận hành.

~~~mermaid
flowchart TD
    T1["T1 commit OrderPaid v2"] --> Pub2["Publication v2 cho reporting"]
    T2["T2 commit OrderRefunded v3"] --> Pub3["Publication v3 cho reporting"]
    Pub2 --> Fail2["Handler v2 lỗi, publication chưa hoàn tất"]
    Pub3 --> Success3["Handler v3 được gọi"]
    Fail2 --> Retry2["Resubmit v2 sau đó"]
    Success3 --> Policy["Policy ordering của consumer"]
    Retry2 --> Policy
    Policy --> Correct["Không ghi lùi hoặc bỏ sót tác động"]
~~~

Registry có thể giúp khôi phục **lần giao chưa hoàn tất**, nhưng không cung cấp một hợp đồng chung rằng các event cùng aggregate luôn được giao đúng version hoặc commit theo thứ tự mong muốn. Khi có retry, **v2 có thể được xử lý muộn hơn v3**. Consumer vẫn phải thực hiện version guard, gap handling, idempotency hoặc ledger phù hợp.

Ngoài ra, registry **không bảo đảm exactly-once side effect**. Consumer có thể ghi hiệu ứng rồi crash trước khi completion của publication được lưu. Một lần resubmit của **cùng eventId** phải không nhân đôi tác dụng.

### Hai đường phục hồi phải được theo dõi tách biệt

| Trường hợp | Ai giữ trách nhiệm? | Cần theo dõi gì? |
| --- | --- | --- |
| Listener ném lỗi trước khi nhận trách nhiệm xử lý | Registry nếu configured/persisted | Publication chưa hoàn tất, retry/error |
| Consumer ghi event vào inbox/pending bền vững rồi return thành công | Chính consumer | Pending age, gap, worker drain, dead-letter/reconciliation |
| Consumer commit effect nhưng registry chưa ghi completion | Cả registry và consumer | Resubmit + idempotency |
| Contract sai khiến không thể áp dụng | Quy trình xử lý lỗi có kiểm soát | Sự kiện độc, cảnh báo, manual repair |

Không nên vừa **ACK registry** vừa giữ event chỉ trong `ConcurrentHashMap`: nếu JVM dừng, pending biến mất trong khi registry có thể không còn publication chưa hoàn tất để replay.

## 13. Thiết kế transaction và idempotency tránh race condition

Một implementation out-of-order đúng về mặt ý tưởng vẫn có thể sai khi có hai thread xử lý cùng `orderId`.

Giả sử `lastAppliedVersion = 1`; hai thread đồng thời nhận `v2` và `v3`:

~~~text
Thread A đọc last = 1, định áp dụng v2
Thread B đọc last = 1, thấy gap ở v3
Thread A ghi v2 và commit
Thread B cần re-check hoặc lưu v3 pending rồi drain đúng lúc
~~~

Nếu thread B kiểm tra trước khi thread A commit và chỉ bỏ qua v3 mà không có pending/retry, v3 có thể **mất tác động** dù event đã được “nhận”.

### Mô hình ghi nguyên tử

Với ordered delta consumer, một transaction xử lý có thể bao gồm:

1. Khóa row cursor của `orderId` hoặc dùng optimistic CAS.
2. Tra khóa idempotency cho `(consumerName, eventId)`.
3. So version với cursor **ở trạng thái đã được khóa**.
4. Nếu đủ predecessor và transition hợp lệ, ghi tác động và advance cursor trong cùng transaction.
5. Nếu thiếu, ghi pending bền vững **hoặc** trả lỗi có chủ đích để registry giữ publication chưa hoàn tất.
6. Commit; một worker drain/reconciliation có nhiệm vụ theo dõi pending sau đó.

Cần xử lý concurrency với **unique constraint** và retry transaction khi gặp conflict. Chỉ `synchronized` trong một instance JVM có thể không đủ khi có nhiều instance ứng dụng hoặc nhiều tiến trình triển khai.

### Đừng trộn duplicate key với order key

`eventId` dùng để chống **cùng occurrence** được xử lý lại. `aggregateVersion` dùng để quyết định **trình tự trạng thái**. `paymentId`/`refundId` dùng để chống **trùng nghiệp vụ nguồn**. Mỗi khóa giải một vấn đề khác nhau; không nên dùng `orderId` làm khóa duy nhất cho ledger của cả vòng đời, vì một đơn có nhiều event hợp lệ.

## 14. Những chiến lược dễ sai

### Sai 1 — “Event đến cuối cùng là mới nhất”

~~~java
void on(OrderPaid event) {
    projection.setStatus("PAID");
}
~~~

Không có version/guard, một event cũ được retry có thể viết đè trạng thái mới. Luôn định nghĩa cách nhận diện **cũ/mới theo aggregate**, hoặc bảo đảm mỗi delta được ghi như bút toán riêng.

### Sai 2 — “Có timestamp nên cứ sort theo occurredAt”

`occurredAt` không nhất thiết phản ánh thứ tự transaction commit, có thể bị trùng, lệch đồng hồ hoặc thay đổi nghĩa giữa các nguồn. Dùng sequence/version đáng tin cậy; timestamp phục vụ truy vết và đo độ trễ.

### Sai 3 — “Version nhỏ hơn thì bỏ qua tất cả”

Với **snapshot toàn phần**, bỏ qua bản cũ có thể đúng. Với **delta**, bỏ qua v2 sau khi v3 đã được áp dụng có thể bỏ sót doanh thu, điểm hoặc bút toán bắt buộc. Phải phân loại consumer trước khi chọn policy.

### Sai 4 — “Idempotency là đủ”

Unique `eventId` chỉ chống nhận trùng. Nó không bảo đảm `OrderRefunded` phải đến sau `OrderPaid`, không phát hiện gap và không bảo vệ state machine nếu event khác nhau nhưng đến sai thứ tự.

### Sai 5 — “Registry giữ thứ tự”

Registry phục vụ theo dõi publication chưa hoàn tất và khôi phục. Retry event cũ có thể xảy ra sau khi event mới được xử lý. Không tự suy luận registry là một ordered durable queue toàn cục.

### Sai 6 — “Nhận gap thì return thành công, rồi tính sau”

Nếu consumer chỉ giữ event trong memory rồi trả thành công, JVM crash có thể làm mất event mà registry không còn retry. Chỉ ACK khi consumer **đã chuyển trách nhiệm sang storage bền vững có đường xử lý tiếp** hoặc thực sự hoàn tất tác động.

### Sai 7 — “Serialize một thread là giải quyết xong”

Một worker đơn luồng có thể vẫn nhận v3 trước v2. Cần version/gap/reconciliation và chống trùng dù chỉ có một thread.

### Sai 8 — “Tạo bút toán hoàn tiền trước khi payment là sai tuyệt đối”

Đối với ledger **phép cộng giao hoán**, một bút toán refund âm có thể được lưu trước paid để cuối cùng hội tụ đúng, **nếu bất biến nghiệp vụ cho phép trạng thái tạm thời đó**. Với chính sách không cho điểm âm hoặc side effect không đảo ngược, phải chờ/điều phối. Không có một luật chung áp cho mọi miền nghiệp vụ.

### Sai 9 — “Consumer hỏi thẳng repository nội bộ của producer cho nhanh”

Điều này phá ranh giới Spring Modulith và có thể đọc một trạng thái khác với snapshot mà event mô tả. Nếu cần tái đồng bộ, dùng **public query API** hoặc snapshot event được module nguồn công bố có chủ đích, không truy cập `orders.internal`.

## 15. Kiểm thử out-of-order: đừng phụ thuộc vào timing ngẫu nhiên

Cần kiểm thử **logic xử lý thuần**, **transaction/data concurrency** và **phân phối thực tế** bằng các tầng riêng. Một test chỉ publish `v2` rồi đợi `v3` trong luồng bình thường có thể không bao giờ tạo race condition cần tìm.

### Ma trận kiểm thử

| Kịch bản | Đầu vào | Kỳ vọng |
| --- | --- | --- |
| **Đúng thứ tự** | v1 → v2 → v3 | Projection/ledger cuối đúng |
| **Đảo thứ tự** | v1 → v3 → v2 | Không ghi lùi, không bỏ sót tác động |
| **Giao trùng** | v1 → v2 → v2 → v3 | v2 chỉ có một hiệu ứng |
| **Gap không bao giờ được lấp** | v1 → v3 | Pending còn dấu vết, có cảnh báo/reconciliation |
| **Retry event cũ** | Hoàn tất v3 rồi resubmit v2 | Không ghi lùi trạng thái, ledger vẫn đúng |
| **Hai event cùng version khác payload** | `v2-A` và `v2-B` | Phát hiện vi phạm version/contract, không ghi đè mù quáng |
| **Hai thread cùng eventId** | v2 được xử lý đồng thời | Unique constraint ngăn nhân đôi tác dụng |
| **Hai thread khác version** | v2 và v3 cạnh tranh lock | Cấu trúc khóa/CAS bảo vệ cursor và dữ liệu |
| **Rollback consumer** | Lỗi giữa insert inbox và update projection | Không có trạng thái “đã xử lý” giả nếu chưa commit hiệu ứng |
| **Source rollback** | Producer publish trong T1 rồi rollback | Listener AFTER_COMMIT không xử lý transition chưa commit |
| **Crash trước registry completion** | Effect đã commit, publication chưa hoàn tất | Resubmit idempotent, không nhân đôi |
| **Pending bị bỏ quên** | Một gap tồn đọng quá SLA | Metric và cảnh báo kích hoạt |

### Kiểm thử core ordering độc lập Spring

Với logic version guard trong consumer, có thể test trực tiếp bằng JUnit mà không phụ thuộc executor.

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

class OrderProjectionOrderingTest {

    @Test
    void rejectsRefundWhenPaidVersionIsMissing() {
        OrderProjection projection = new OrderProjection(
                OrderState.CREATED, 1
        );

        assertThatThrownBy(() -> projection.applyRefunded(3))
                .isInstanceOf(IllegalStateException.class);

        assertThat(projection.version()).isEqualTo(1);
    }

    @Test
    void stalePaidDoesNotOverwriteRefunded() {
        OrderProjection projection = new OrderProjection(
                OrderState.CREATED, 1
        );

        projection.applyPaid(2);
        projection.applyRefunded(3);
        projection.applyPaid(2); // Retry event cũ.

        assertThat(projection.status())
                .isEqualTo(OrderState.REFUNDED);
        assertThat(projection.version()).isEqualTo(3);
    }
}
~~~

`OrderProjection`, `OrderState`, `version()` và `status()` là domain test fixture minh họa: hiện thực theo policy của consumer, không phải class từ Spring Modulith. Trong bài test ở mục 10, có thể thêm các getter cần thiết hoặc tạo fixture riêng. Mục đích là **ép xử lý sai thứ tự một cách xác định**, không phụ thuộc lịch thread.

### Kiểm thử integration Spring Modulith

Có thể dùng `@ApplicationModuleTest`, `PublishedEvents`, `Scenario` và `ApplicationModules.verify()` tùy phiên bản/dependency của dự án.

Cần ít nhất:

1. Producer phát event đúng contract và version trong một transaction nguồn **thực sự commit**.
2. Listener `@ApplicationModuleListener` chạy hậu commit; dữ liệu consumer được ghi trong transaction riêng.
3. Một consumer lỗi sau commit để lại publication chưa hoàn tất khi registry bền vững đã cấu hình.
4. Event mới hơn hoàn tất trước; publication cũ được resubmit và policy ordering xử lý đúng.
5. Trùng `eventId` và xử lý song song được chống bằng database constraint.
6. Không truy cập package nội bộ của `orders`, kiểm chứng bằng `ApplicationModules.verify()`.

**Tránh hai bẫy:** test `@Transactional` thường tự rollback nên listener AFTER_COMMIT không chạy; `Thread.sleep(100)` cố định không bảo đảm async đã hoàn tất. Hãy dùng transaction commit thật và chờ điều kiện nghiệp vụ có timeout.

### Kiểm thử cạnh tranh bằng database thật

Một in-memory mock của repository khó phát hiện race `SELECT exists` rồi insert ở hai transaction. Dùng database tương đương production để chạy nhiều transaction cùng `orderId`, kiểm tra lock, unique constraint, optimistic conflicts, deadlock retry và kết quả cuối. Không kết luận “an toàn khi chạy song song” chỉ vì test tuần tự pass.

## 16. Quan sát và xử lý sự cố out-of-order

Một hệ thống có retry nhưng không có quan sát version/gap sẽ khó phân biệt **consumer chậm bình thường** với **sự kiện thất lạc hoặc xử lý sai thứ tự**.

| Tín hiệu | Mục đích |
| --- | --- |
| `eventId`, `eventType`, `orderId` | Tra cứu từng occurrence và aggregate |
| `aggregateVersion` hoặc `streamSequence` | So với cursor của consumer |
| `lastAppliedVersion` | Biết consumer hiện ở đâu |
| `receivedAt`, `processedAt`, `occurredAt` | Phân tích độ trễ và lịch giao lại |
| `outOfOrderDetected` | Số lần nhận version không phải version tiếp theo |
| `gapPendingCount`, `oldestGapAge` | Công việc chờ predecessor và thời gian tồn đọng |
| `staleIgnored` | Số event cũ đã bị ngăn ghi lùi |
| `duplicateSuppressed` | Số lần cùng eventId bị xử lý lại |
| `publicationIncomplete` | Publication chưa hoàn tất trong registry |
| `resubmitAttempt`, `errorCategory` | Lần retry và nguyên nhân thất bại |
| `reconciliationRun`, `reconciliationMismatch` | Khả năng tự sửa khác biệt với nguồn |

`eventId` là dữ liệu phù hợp để tra log hoặc tracing, **không nên làm label metric có cardinality vô hạn**. Với số lượng aggregate lớn, log chi tiết có sampling/quy tắc lưu trữ và chính sách bảo vệ dữ liệu cá nhân; metric aggregate theo module, handler, event type và outcome.

### Quy trình điều tra ví dụ

Người dùng báo rằng đơn `O-100` đã hoàn tiền nhưng báo cáo vẫn ở `PAID`:

1. Xác nhận trạng thái nguồn từ public API của `orders`, cùng version đã commit.
2. Tra `OrderRefunded` và `OrderPaid` theo `orderId`, `eventId`, `aggregateVersion`.
3. Kiểm tra registry cho **publication của reporting**, không chỉ trạng thái publication của loyalty.
4. Xem cursor `lastAppliedVersion`, inbox/pending và lịch xử lý thực tế của reporting.
5. Xác định đó là stale overwrite, gap chưa lấp, duplicate, lỗi dữ liệu hay consumer chưa chạy.
6. Trước khi resubmit, xác nhận idempotency và xem effect nào đã commit.
7. Khi cần, đối soát/rebuild projection từ snapshot công khai hoặc lịch sử sự kiện có thẩm quyền.
8. Xác nhận trạng thái cuối, đóng pending và cảnh báo chỉ sau khi dữ liệu đã đúng.

Không “chữa” bằng cách cập nhật thủ công cột status rồi bỏ qua ledger/cursor: lần retry tiếp theo có thể lại làm sai projection nếu policy ordering vẫn lỗi.

## 17. Đối soát (reconciliation) khi không thể tin vào thứ tự đã nhận

Dù có version và registry, một consumer vẫn cần cách **phục hồi khi thiếu event lâu ngày**, khi schema thay đổi hoặc khi có bug cũ đã tạo projection sai. Reconciliation là việc so sánh trạng thái consumer với nguồn có thẩm quyền và sửa khác biệt theo chính sách rõ ràng.

Một workflow minh họa:

~~~mermaid
flowchart TD
    A["Định kỳ hoặc có cảnh báo gap"] --> B["Lấy snapshot công khai của orders"]
    B --> C["So version nguồn với consumer cursor"]
    C --> D{"Có khác biệt?"}
    D -->|"Không"| E["Ghi nhận trạng thái hội tụ"]
    D -->|"Có"| F{"Consumer là snapshot hay ledger?"}
    F -->|"Snapshot"| G["Cập nhật bằng version guard, không ghi lùi"]
    F -->|"Ledger"| H["Tìm thiếu bút toán và đối soát theo giao dịch"]
    G --> I["Xác nhận lại sau cập nhật"]
    H --> I
~~~

**Snapshot projection** có thể cập nhật lại bằng trạng thái mới nhất và source version, với kiểm soát concurrency. **Ledger tài chính/điểm** thường không được “đặt lại tổng” mà không có dấu vết; cần so từng giao dịch, thêm bút toán điều chỉnh có audit trail hoặc replay theo nguồn đúng. Không tự coi “cập nhật cho bằng tổng ở orders” là đủ cho lịch sử kế toán.

Reconciliation nên dùng **public query contract** mà producer công bố, hoặc dữ liệu sự kiện có thẩm quyền; không phá modular boundary bằng cách import `orders.internal.OrderRepository`. Cũng phải tránh tạo vòng phụ thuộc module khi tổ chức adapter đối soát.

## 18. Bài thực hành: hoàn tiền đến trước thanh toán

### Bối cảnh

Ứng dụng bán vé có bốn module:

- `payments`: xác nhận thanh toán và hoàn tiền, phát `PaymentCompleted`, `PaymentRefunded`.
- `tickets`: phát hành hoặc hủy vé theo trạng thái payment.
- `loyalty`: cộng điểm hoặc ghi điều chỉnh hoàn tiền.
- `reporting`: xây projection doanh thu và trạng thái giao dịch.

`payments` sở hữu thứ tự version cho từng `paymentId` hoặc `reservationId` phù hợp miền nghiệp vụ. Giả định phiên bản `v2` là thanh toán thành công và `v3` là hoàn tiền.

### Yêu cầu

1. **Contract:** thiết kế event có `eventId`, aggregate ID, version/sequence, payment/refund ID, số tiền, currency và `occurredAt`. Định nghĩa rõ aggregate nào cấp version.
2. **Producer:** publish trong transaction nguồn sau transition hợp lệ, cấp version nguyên tử với cập nhật dữ liệu; không phát lại occurrence mới cho cùng callback.
3. **Consumer snapshot:** thử gửi `PaymentRefunded(v3)` trước `PaymentCompleted(v2)`. Nếu payload chứa snapshot đầy đủ, reporting chỉ giữ version mới hơn và không ghi lùi.
4. **Consumer delta:** triển khai ledger doanh thu/điểm với khóa idempotency, gửi v3 trước v2 rồi xác nhận tổng cuối đúng theo chính sách.
5. **Consumer stateful:** với tickets, xây state machine hoặc pending gap để tránh phát hành lại sau khi đã hủy.
6. **Gap:** consumer ở v1 nhận v3; lưu pending bền vững hoặc làm publication chưa hoàn tất, sau đó đưa v2 đến và drain theo thứ tự.
7. **Retry:** giả lập lỗi khi xử lý v2, cho v3 được xử lý trước hoặc lưu pending; resubmit v2 và xác nhận không tạo hiệu ứng trùng.
8. **Concurrency:** chạy hai transaction cùng xử lý một aggregate, kiểm tra unique constraint, row lock hoặc optimistic CAS.
9. **Registry:** cấu hình kho publication bền vững phù hợp phiên bản Spring Modulith; kiểm tra nhánh listener còn pending và hoàn tất.
10. **Observability:** hiển thị lastAppliedVersion, gap age, stale ignored, duplicate suppressed và incomplete publications.
11. **Reconciliation:** làm projection sai có chủ đích, sau đó đọc snapshot công khai để sửa đúng mà không ghi lùi.
12. **Kiểm thử ranh giới:** dùng `ApplicationModules.verify()` để kiểm tra consumer không import nội bộ module nguồn.

### Dữ liệu thực nghiệm

| Thứ tự đưa vào consumer | Kỳ vọng projection snapshot | Kỳ vọng ledger delta |
| --- | --- | --- |
| v2 → v3 | Giữ trạng thái v3 | Có hai bút toán đúng |
| v3 → v2 | Không ghi lùi từ v3 về v2 | Có hai bút toán đúng khi cả hai hợp lệ |
| v3 → v2 → v2 | Không ghi lùi, không xử lý trùng | Không có bút toán v2 thứ hai |
| v3, thiếu v2 vĩnh viễn | Cần kiểm tra snapshot/version đầy đủ | Không được coi là đủ tác động; cảnh báo gap hoặc đối soát |
| v2 xử lý thành công, registry chưa ghi completion | Resubmit không làm thay đổi sai trạng thái | Không ghi thêm bút toán |
| v2/v3 xử lý cạnh tranh | DB/version guard tránh ghi đè bất hợp lệ | Unique constraint, transaction đảm bảo đúng số bút toán |

### Câu hỏi tự đánh giá

**1. Vì sao `OrderPaid(v2)` có thể được xử lý sau `OrderRefunded(v3)`?**

Vì listener chạy bất đồng bộ, transaction consumer có thời gian khác nhau, hoặc publication v2 gặp lỗi rồi được resubmit sau khi v3 đã xử lý. Spring Modulith không tự cung cấp thứ tự hoàn tất toàn cục cho các listener.

**2. Có nên luôn bỏ qua event version nhỏ hơn `lastAppliedVersion`?**

Không. Với snapshot đầy đủ, việc bỏ qua bản cũ có thể đúng. Với delta, mỗi event có tác động độc lập và cần được ghi trong ledger; chỉ bỏ qua vì version thấp có thể khiến thiếu tác động.

**3. Vì sao `occurredAt` không thay thế được version?**

Vì timestamp không nhất thiết phản ánh thứ tự commit, có thể trùng hoặc lệch đồng hồ, và không cung cấp một thứ tự nghiệp vụ tin cậy theo aggregate.

**4. Nếu gặp v3 khi cursor đang ở v1, vì sao không return thành công sau khi lưu vào Map trong RAM?**

Vì JVM có thể dừng và mất Map, trong khi registry có thể đã xem handler hoàn tất. Nếu chuyển trách nhiệm sang consumer, pending phải bền vững và có cơ chế drain/recovery.

**5. Registry có bảo đảm v2 được xử lý trước v3 không?**

Không. Registry lưu dấu và hỗ trợ xử lý lại publication chưa hoàn tất theo cấu hình, nhưng consumer cần tự xử lý version, gap, idempotency và trạng thái nghiệp vụ.

**6. Có thể đạt đúng tổng điểm khi refund được ghi trước paid không?**

Có thể nếu các bút toán là delta giao hoán và chính sách cho phép trạng thái trung gian; nếu có điều kiện “không được trừ khi chưa có khoản cộng” thì phải lưu chờ hoặc điều phối thứ tự.

**7. Thế nào là giải pháp an toàn cho side effect không thể hoàn tác?**

Xác định bất biến nghiệp vụ, dùng idempotency và state guard/fencing trước side effect, kiểm soát concurrency, lưu yêu cầu bền vững và có quy trình reconciliation/compensation khi cần. Không chỉ đổi thứ tự xử lý trên một thread rồi cho rằng đã đủ.

## 19. Checklist thiết kế xử lý không theo thứ tự

- [ ] Phân biệt thứ tự nghiệp vụ, publish, commit, nhận và hoàn tất consumer.
- [ ] Không giả định `@ApplicationModuleListener` bảo đảm thứ tự hoàn tất.
- [ ] Producer sở hữu quy tắc transition và cấp version/sequence đáng tin cậy trong transaction.
- [ ] Có cơ chế kiểm soát cạnh tranh khi cập nhật cùng aggregate.
- [ ] Phân biệt event ID, aggregate ID, business reference và aggregate version.
- [ ] Không dùng `occurredAt` làm khóa thứ tự duy nhất.
- [ ] Xác định consumer là snapshot, delta ledger hay stateful process manager.
- [ ] Chỉ dùng latest-version-wins khi snapshot đủ thông tin và được apply bằng update nguyên tử.
- [ ] Không bỏ qua delta cần thiết chỉ vì version thấp.
- [ ] Có idempotency bền vững theo event/handler hoặc khóa hiệu ứng.
- [ ] Với ordered handler, có cách xử lý version gap và predecessor bị thiếu.
- [ ] Không ACK rồi chỉ lưu pending trong bộ nhớ.
- [ ] Có worker drain, timeout, retry/backoff và cảnh báo cho pending bền vững.
- [ ] Có state machine guard hoặc fencing cho side effect không giao hoán.
- [ ] Không xem serialize một thread là bảo đảm đủ mọi loại thứ tự.
- [ ] Hiểu Event Publication Registry hỗ trợ khôi phục, không tự bảo đảm strict ordering hoặc exactly-once.
- [ ] Có test đảo thứ tự, duplicate, gap, concurrency và crash trước completion.
- [ ] Có telemetry cho version, gap age, stale/duplicate và incomplete publications.
- [ ] Có quy trình reconciliation từ hợp đồng công khai của module nguồn.
- [ ] Giữ ranh giới Spring Modulith, không gọi repository nội bộ module nguồn.

## Ghi nhớ

**Xử lý không theo thứ tự** là khả năng một consumer nhận hoặc hoàn tất một event cũ **sau** event mới, dù module nguồn đã công bố các transition nghiệp vụ theo thứ tự. Trong Spring Modulith, listener hậu commit bất đồng bộ và cơ chế retry/resubmit từ Event Publication Registry là những lý do thực tế khiến tình huống này phải được thiết kế ngay từ đầu.

Không có một mẹo “sort theo timestamp” hay một annotation duy nhất giải quyết được mọi trường hợp. **Snapshot đầy đủ** có thể dùng *latest-version-wins* với update nguyên tử. **Delta nghiệp vụ** cần ledger idempotent hoặc xử lý đủ predecessor. **State machine và side effect không đảo ngược** cần transition guard, version/fencing, điều phối hoặc đối soát. Với gap, phải lưu pending bền vững hoặc giữ publication chưa hoàn tất để retry có kiểm soát.

Một hệ thống đáng tin cậy không phải hệ thống “không bao giờ gặp event đến sai thứ tự”, mà là hệ thống **phát hiện được sự bất thường, không ghi sai trạng thái, không làm trùng tác động, không làm mất công việc đang chờ và có thể hội tụ lại đúng nghiệp vụ**. Những tính chất đó đến từ contract rõ ràng, transaction, version, idempotency, kiểm thử nghịch cảnh và quan sát theo từng module.

