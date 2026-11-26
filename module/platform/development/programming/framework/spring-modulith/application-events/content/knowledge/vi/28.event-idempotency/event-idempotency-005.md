# Upsert an toàn

Trong hệ thống xử lý application events, cùng một event có thể được giao lại khi listener timeout, process khởi động lại hoặc consumer chưa xác nhận offset. Vì vậy, projection và read model phải chịu được việc một event được xử lý nhiều lần. **Upsert** giúp tạo mới hoặc cập nhật một bản ghi theo khóa xác định, nhưng bản thân câu lệnh upsert không tự bảo đảm idempotency. Muốn an toàn, cần kết hợp khóa duy nhất, event identity, transaction và quy tắc version phù hợp với ý nghĩa dữ liệu.

Bài này tập trung vào cách dùng upsert để cập nhật projection từ event mà không tạo bản ghi trùng, không nhân đôi phép cộng dồn và không để event cũ ghi đè trạng thái mới.

## 1. Upsert và idempotency

Upsert là thao tác kết hợp insert và update: nếu bản ghi theo khóa chưa tồn tại thì tạo mới; nếu đã tồn tại thì cập nhật theo quy tắc được chỉ định.

Một thao tác được xem là idempotent khi thực hiện một lần hay nhiều lần với cùng đầu vào đều dẫn tới cùng kết quả quan sát được. Ví dụ, đặt trạng thái đơn hàng thành PAID là phép gán trạng thái; thực hiện lại thường vẫn cho kết quả PAID. Ngược lại, tăng số lượng đã bán thêm 1 là phép cộng dồn; chạy lại sẽ tăng thêm lần nữa.

| Thao tác | Chạy lại cùng event | Idempotent tự nhiên? |
|---|---|---|
| Đặt trạng thái thành PAID | Trạng thái vẫn là PAID | Thường có, nếu không ghi đè trạng thái mới hơn |
| Ghi địa chỉ giao hàng theo giá trị event | Cùng địa chỉ được ghi lại | Thường có |
| Tăng counter thêm 1 | Counter tăng thêm lần nữa | Không |
| Cộng amount vào tổng doanh thu | Tổng tăng lặp | Không |
| Ghi một dòng lịch sử mới | Tạo thêm dòng | Không, trừ khi có khóa duy nhất theo event |

Do đó, cần xác định semantics của projection trước khi chọn câu lệnh upsert. Với dữ liệu trạng thái hiện tại, upsert theo aggregate key và version thường phù hợp. Với phép cộng dồn, cần deduplicate event trước khi áp dụng hiệu ứng.

## 2. Chọn đúng khóa duy nhất

Khóa duy nhất xác định một bản ghi projection đại diện cho thực thể nào. Ví dụ, bảng trạng thái đơn hàng thường có một dòng cho mỗi order ID:

~~~sql
CREATE TABLE order_projection (
    order_id UUID PRIMARY KEY,
    status VARCHAR(30) NOT NULL,
    total_amount DECIMAL(19, 4) NOT NULL,
    version BIGINT NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
~~~

Trong ví dụ này, order ID là khóa nghiệp vụ của read model. Nếu projection có phạm vi theo tenant, khóa có thể là cặp tenant ID và order ID:

~~~sql
CREATE TABLE tenant_order_projection (
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    status VARCHAR(30) NOT NULL,
    version BIGINT NOT NULL,
    PRIMARY KEY (tenant_id, order_id)
);
~~~

Chọn khóa dựa trên identity nghiệp vụ, không dựa vào dữ liệu có thể thay đổi như tên, email hoặc trạng thái. Nếu cùng một order ID có thể tồn tại ở nhiều tenant, chỉ dùng order ID sẽ gây xung đột giữa các tenant.

Cần phân biệt hai loại khóa:

- **Aggregate/business key** xác định dòng projection cần tạo hoặc cập nhật, ví dụ order ID.
- **Event identity** xác định một lần thay đổi nghiệp vụ, ví dụ event ID. Khóa này dùng để nhận biết cùng event đã được xử lý hay chưa.

Không dùng một loại khóa thay cho loại còn lại. Một order có nhiều event khác nhau trong suốt vòng đời; vì vậy order ID không thể dùng để deduplicate mọi event của order đó.

## 3. Upsert trạng thái với version guard

Giả sử mỗi event mang aggregate version tăng đơn điệu. Projection lưu version mới nhất đã áp dụng. Khi event tới, chỉ cập nhật nếu version của event lớn hơn version đang có.

Ví dụ PostgreSQL:

~~~sql
INSERT INTO order_projection (
    order_id,
    status,
    total_amount,
    version,
    updated_at
)
VALUES (
    :order_id,
    :status,
    :total_amount,
    :event_version,
    :occurred_at
)
ON CONFLICT (order_id) DO UPDATE
SET
    status = EXCLUDED.status,
    total_amount = EXCLUDED.total_amount,
    version = EXCLUDED.version,
    updated_at = EXCLUDED.updated_at
WHERE order_projection.version < EXCLUDED.version;
~~~

Câu lệnh này có các đặc tính:

- Nếu order chưa có projection, tạo bản ghi với version của event.
- Nếu projection đã tồn tại và event mới hơn, cập nhật trạng thái.
- Nếu event có version bằng hoặc thấp hơn, không ghi đè dữ liệu hiện tại.
- Ràng buộc PRIMARY KEY khiến việc cạnh tranh insert trên cùng order ID được database xử lý theo cơ chế xung đột duy nhất.

Điều kiện version guard ngăn event cũ tới muộn ghi đè trạng thái mới. Đây là điều kiện quan trọng khi listener bất đồng bộ, nhiều instance xử lý song song hoặc message được replay.

Câu lệnh trên là cú pháp PostgreSQL. Các database khác có cú pháp upsert và semantics khóa khác nhau; hãy dùng cú pháp tương ứng và kiểm tra hành vi cạnh tranh trên database thực tế. Không giả định một câu SQL portable cho mọi hệ quản trị.

Nếu event không có aggregate version hoặc sequence đáng tin cậy, không nên tự tạo version bằng timestamp rồi coi nó là thứ tự tuyệt đối. Đồng hồ giữa các instance có thể lệch và nhiều event có thể có cùng timestamp. Hãy bổ sung sequence từ nguồn có thẩm quyền hoặc xác định một quy tắc xử lý khác.

## 4. Xử lý cùng version nhưng payload khác nhau

Version guard thường bỏ qua event có version bằng version hiện tại. Tuy nhiên, nếu cùng một aggregate version lại mang payload khác nhau, đó có thể là lỗi contract hoặc lỗi phát event. Bỏ qua âm thầm có thể che giấu dữ liệu bất thường.

Có thể lưu hash của nội dung projection hoặc event để phát hiện trường hợp này:

~~~sql
ALTER TABLE order_projection
ADD COLUMN source_event_id UUID,
ADD COLUMN payload_hash VARCHAR(64);
~~~

Khi nhận event:

1. Nếu event version thấp hơn version hiện tại, bỏ qua như event cũ theo policy.
2. Nếu version cao hơn, áp dụng update và lưu event ID/hash.
3. Nếu version bằng và event ID/hash giống nhau, coi là redelivery của cùng thay đổi.
4. Nếu version bằng nhưng payload hash khác, ghi nhận conflict và chuyển sang điều tra.

Hash phải được tạo từ biểu diễn canonical đã thống nhất. Nếu thứ tự field JSON, định dạng timestamp hoặc decimal thay đổi, hash byte thô có thể khác dù dữ liệu có cùng ý nghĩa. Có thể hash các trường nghiệp vụ đã chuẩn hóa thay vì JSON tùy ý.

## 5. Deduplicate event trước khi áp dụng hiệu ứng

Upsert theo order ID bảo vệ số lượng dòng projection, nhưng không tự ngăn phép cộng dồn chạy hai lần. Để xử lý event lặp, tạo inbox table với khóa duy nhất gồm consumer và event ID:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(150) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Khi xử lý event, thử insert event ID trước. Nếu insert thành công, event chưa được consumer này xử lý; tiếp tục cập nhật projection. Nếu insert bị xung đột, event đã được ghi nhận và có thể bỏ qua lần giao lại.

Với PostgreSQL, có thể dùng:

~~~sql
INSERT INTO processed_events (
    consumer_name,
    event_id,
    processed_at
)
VALUES (
    :consumer_name,
    :event_id,
    :processed_at
)
ON CONFLICT (consumer_name, event_id) DO NOTHING;
~~~

Ứng dụng kiểm tra số dòng bị ảnh hưởng. Nếu là 1, insert mới thành công và có thể tiếp tục xử lý. Nếu là 0, khóa đã tồn tại và event là duplicate đối với consumer đó.

Không dùng mẫu kiểm tra trước rồi mới insert như sau:

~~~java
if (!repository.existsByEventId(event.eventId())) {
    repository.save(new ProcessedEvent(event.eventId()));
    projection.apply(event);
}
~~~

Hai instance có thể cùng kiểm tra và đều thấy event chưa tồn tại trước khi một instance kịp insert. Đây là race condition kiểu check-then-act. Ràng buộc unique ở database mới là điểm phân xử cuối cùng; thao tác insert phải nguyên tử và code cần xử lý kết quả duplicate.

## 6. Đặt inbox và projection update trong cùng transaction

Để tránh trạng thái một phần, việc ghi event ID vào inbox và cập nhật projection cần thuộc cùng transaction database khi chúng dùng chung database.

Luồng xử lý:

~~~text
Begin database transaction
          |
          v
Insert (consumer, eventId) into inbox
          |
          +---- duplicate ----> no-op / commit
          |
          v
Apply projection upsert
          |
          v
Commit transaction
~~~

Nếu projection update thất bại, transaction phải rollback cả inbox insert. Khi event được giao lại, consumer có thể thử lại từ đầu. Nếu transaction commit, cả inbox và projection cùng được ghi; lần redelivery tiếp theo sẽ gặp khóa đã tồn tại và không áp dụng hiệu ứng lần nữa.

Ví dụ service dùng Spring:

~~~java
@Service
class OrderProjectionUpdater {

    private final JdbcTemplate jdbc;

    OrderProjectionUpdater(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void apply(OrderPaid event) {
        int inserted = jdbc.update("""
            INSERT INTO processed_events (
                consumer_name, event_id, processed_at
            )
            VALUES (?, ?, ?)
            ON CONFLICT (consumer_name, event_id) DO NOTHING
            """,
            "order-summary",
            event.eventId(),
            Timestamp.from(Instant.now())
        );

        if (inserted == 0) {
            return;
        }

        jdbc.update("""
            INSERT INTO order_projection (
                order_id, status, total_amount, version, updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (order_id) DO UPDATE
            SET status = EXCLUDED.status,
                total_amount = EXCLUDED.total_amount,
                version = EXCLUDED.version,
                updated_at = EXCLUDED.updated_at
            WHERE order_projection.version < EXCLUDED.version
            """,
            event.orderId(),
            "PAID",
            event.totalAmount(),
            event.aggregateVersion(),
            Timestamp.from(event.occurredAt())
        );
    }
}
~~~

Ví dụ dùng PostgreSQL và JdbcTemplate; tên event, schema và repository là minh họa. Listener có thể gọi service này:

~~~java
@Component
class OrderPaidListener {

    private final OrderProjectionUpdater updater;

    OrderPaidListener(OrderProjectionUpdater updater) {
        this.updater = updater;
    }

    @ApplicationModuleListener
    void on(OrderPaid event) {
        updater.apply(event);
    }
}
~~~

Transaction manager phải quản lý cùng DataSource mà JdbcTemplate sử dụng. Nếu inbox và projection nằm ở hai database khác nhau, một local transaction không thể bảo đảm atomicity cho cả hai; cần thiết kế khác như outbox, workflow bù trừ hoặc một cơ chế phối hợp giao dịch phù hợp.

## 7. Upsert phép cộng dồn cần deduplication

Một projection tổng hợp có thể lưu số đơn hoặc tổng doanh thu. Câu lệnh cộng dồn:

~~~sql
INSERT INTO daily_sales (
    sales_day,
    currency_code,
    total_amount
)
VALUES (
    :sales_day,
    :currency_code,
    :amount
)
ON CONFLICT (sales_day, currency_code) DO UPDATE
SET total_amount =
    daily_sales.total_amount + EXCLUDED.total_amount;
~~~

Câu lệnh này xử lý cạnh tranh update một dòng tốt hơn mẫu đọc giá trị rồi ghi lại trong ứng dụng, nhưng nó không idempotent. Nếu cùng event được gửi lại, amount vẫn được cộng lần nữa.

Để an toàn, phải đặt phép cộng dồn sau bước inbox deduplication trong cùng transaction. Unique key của inbox ngăn event ID đó tác động lần thứ hai. Có thể thiết kế một bảng ledger có event ID là khóa duy nhất rồi tính tổng từ ledger; cách này tăng khả năng audit nhưng cần cân nhắc chi phí lưu trữ và truy vấn.

Đừng nhầm atomicity của upsert với idempotency. Atomic update ngăn mất cập nhật do hai transaction ghi đồng thời, còn deduplication ngăn cùng một event tạo hiệu ứng lặp. Hai yêu cầu khác nhau.

## 8. Cập nhật từng phần và tránh ghi đè null

Một số event chỉ mang các trường thay đổi, ví dụ event chỉ cập nhật địa chỉ giao hàng. Nếu upsert gán mọi trường từ payload, các trường không có trong event có thể bị ghi thành null và làm mất dữ liệu.

Có thể chọn một trong các cách:

- Event mang đầy đủ snapshot trạng thái và version; upsert thay thế toàn bộ projection theo snapshot.
- Event mang delta; câu lệnh chỉ cập nhật các trường có trong event.
- Dùng DTO riêng biểu diễn rõ trường được cung cấp và trường có chủ ý xóa.
- Dùng patch semantics có quy ước phân biệt “không gửi trường” với “gửi null để xóa”.

Ví dụ cập nhật một trường có chủ đích:

~~~sql
UPDATE customer_projection
SET delivery_address = :delivery_address,
    version = :event_version
WHERE customer_id = :customer_id
  AND version < :event_version;
~~~

Nếu event cần vừa tạo vừa cập nhật, có thể dùng upsert nhưng phải xác định rõ các trường thuộc snapshot hay delta. Không dùng biểu thức COALESCE một cách máy móc nếu null là giá trị hợp lệ để xóa trường.

## 9. Xử lý đồng thời và isolation

Khi nhiều event của cùng aggregate được xử lý song song, có thể xảy ra:

- Hai transaction cùng insert một dòng chưa tồn tại.
- Hai event version khác nhau cùng cập nhật một dòng.
- Một transaction đọc version cũ rồi ghi đè kết quả của transaction khác.
- Inbox insert và projection update tranh chấp trên cùng khóa.

Ràng buộc unique và upsert nguyên tử giúp database phân xử cạnh tranh insert. Version guard ngăn event cũ ghi đè event mới. Với logic phức tạp hơn, có thể cần optimistic locking, row-level lock hoặc isolation level phù hợp.

Không giữ transaction mở trong lúc gọi HTTP hoặc chờ một dịch vụ ngoài. Giao dịch dài làm tăng thời gian giữ lock và có thể gây nghẽn. Nếu cần side effect bên ngoài, ghi ý định gửi vào outbox trong cùng transaction rồi worker riêng gửi đi; downstream nên hỗ trợ idempotency key.

Cũng cần xác định hành vi khi version bị nhảy cóc. Nếu projection đang ở version 5 nhưng nhận version 7, chỉ cập nhật snapshot version 7 có thể hợp lệ nếu event chứa trạng thái đầy đủ. Nếu event là delta cần áp dụng lần lượt, version 6 đang thiếu và phải chờ, retry hoặc đọc lại nguồn. Không áp dụng một policy chung cho snapshot event và delta event.

## 10. Giữ inbox và dữ liệu deduplication trong thời gian phù hợp

Inbox table có thể tăng liên tục. Chính sách lưu giữ phải phù hợp với thời gian tối đa event có thể được replay hoặc redeliver.

Nếu xóa event ID quá sớm, một lần replay cũ có thể được xem như event mới và tạo hiệu ứng nghiệp vụ lặp. Nếu giữ vô hạn, bảng sẽ tăng kích thước và index tốn dung lượng.

Một số cách quản lý:

- Giữ inbox theo thời hạn dài hơn retention và replay window của nguồn event.
- Partition bảng theo thời gian nếu database hỗ trợ và lượng dữ liệu lớn.
- Lưu checkpoint hoặc watermark theo consumer khi có thể chứng minh event cũ không còn được replay.
- Giữ ledger nghiệp vụ lâu dài với event ID unique nếu cần audit tài chính.
- Chỉ xóa dữ liệu deduplication sau khi có chính sách phục hồi và kiểm tra replay rõ ràng.

Không chỉ dựa vào timestamp để quyết định xóa nếu nguồn có thể phát lại event cũ ngoài dự kiến. Cần phối hợp retention của Kafka, event store, backup và quy trình vận hành.

## 11. Kiểm thử upsert an toàn

Kiểm thử cần xác minh kết quả dữ liệu sau nhiều lần xử lý và trong điều kiện cạnh tranh:

1. Event đầu tiên tạo projection nếu chưa có dòng.
2. Gửi lại cùng event không tạo dòng mới hoặc lặp side effect.
3. Event version mới cập nhật projection.
4. Event version cũ tới sau không ghi đè projection mới.
5. Cùng version và cùng event ID được coi là redelivery.
6. Cùng version nhưng payload khác được phát hiện như conflict.
7. Hai event khác nhau của cùng aggregate cập nhật theo đúng thứ tự hoặc version policy.
8. Hai instance đồng thời xử lý cùng event chỉ tạo một hiệu ứng nghiệp vụ.
9. Projection update thất bại làm inbox insert rollback trong cùng transaction.
10. Event delta bị thiếu version trước được xử lý theo policy gap, không âm thầm nhảy qua.
11. Event có null hoặc patch field được xử lý đúng semantics.
12. Replay trong thời hạn lưu giữ inbox không tạo side effect lặp.

Dùng database integration test với đúng hệ quản trị được triển khai để kiểm tra cú pháp upsert, unique constraint, lock và isolation. Mock repository không thể chứng minh hành vi cạnh tranh của database. Với phép cộng dồn, kiểm tra tổng sau nhiều lần gửi cùng event phải bằng kết quả sau một lần gửi.

## 12. Quan sát và vận hành

Nên theo dõi:

| Chỉ số | Ý nghĩa |
|---|---|
| Duplicate event count | Số lần event đã xử lý được giao lại |
| Upsert insert/update/no-op count | Tỷ lệ tạo mới, cập nhật và bỏ qua do version |
| Version conflict count | Số event cùng version nhưng nội dung không khớp |
| Out-of-order/gap count | Event đến sai thứ tự hoặc thiếu version |
| Inbox table size | Tốc độ tăng của dữ liệu deduplication |
| Transaction rollback count | Lỗi khi áp dụng projection |
| Projection lag | Độ trễ từ event tới trạng thái read model |
| Repair/replay count | Số lần phục hồi hoặc phát lại dữ liệu |

Log nên có consumer name, event ID, aggregate ID, aggregate version, action (insert/update/no-op), transaction outcome và correlation ID. Không ghi payload nhạy cảm hoặc thông tin xác thực. Khi gặp duplicate, thường chỉ cần ghi ở mức debug hoặc tăng metric; tránh tạo log error cho một redelivery hợp lệ.

Khi version conflict hoặc gap tăng bất thường, cảnh báo cần dẫn tới kiểm tra partition key, producer ordering, consumer concurrency và event contract. Nếu upsert no-op tăng cao nhưng nguồn event không có replay dự kiến, có thể listener đang nhận nhiều event cũ hoặc retry loop.

## 13. Checklist thiết kế

Trước khi triển khai upsert cho projection, xác nhận:

- Khóa nghiệp vụ xác định duy nhất dòng projection.
- Event ID ổn định qua retry, redelivery và replay.
- Inbox có unique constraint theo consumer và event ID.
- Inbox insert và projection update nằm trong cùng transaction khi cùng database.
- Snapshot và delta event có semantics cập nhật rõ ràng.
- Aggregate version hoặc sequence có nguồn đáng tin cậy.
- Upsert có điều kiện để event cũ không ghi đè trạng thái mới.
- Phép cộng dồn được bảo vệ bởi deduplication hoặc ledger.
- Null, patch field, rounding và decimal được định nghĩa rõ.
- Retention inbox dài hơn replay window cần hỗ trợ.
- Có kiểm thử database thực tế cho concurrency và rollback.
- Metric, log và quy trình xử lý conflict được xác định.

Upsert an toàn không chỉ là chọn cú pháp insert-or-update. Nó là sự kết hợp giữa identity của aggregate, identity của event, ràng buộc duy nhất, version guard và transaction. Khi những phần này được thiết kế cùng nhau, projection trong ứng dụng Spring Modulith có thể chịu được redelivery và retry mà không tạo dữ liệu trùng, nhân đôi hiệu ứng hoặc làm trạng thái lùi về phiên bản cũ.

