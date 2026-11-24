# Phân trang, đọc theo luồng và tính nhất quán dữ liệu

Một dịch vụ reactive có thể phải trả hàng trăm nghìn bản ghi, xuất dữ liệu cho báo cáo hoặc đọc một bảng sự kiện liên tục tăng. Nếu tải tất cả dữ liệu vào một danh sách trước khi trả kết quả, ứng dụng tiêu thụ bộ nhớ theo kích thước toàn bộ tập dữ liệu và phải chờ truy vấn hoàn tất. Nếu chia dữ liệu thành từng trang, mỗi lần đọc chỉ giữ một phần nhỏ trong bộ nhớ. Nếu dùng publisher để đọc theo luồng, dữ liệu có thể được xử lý dần theo nhu cầu của downstream.

Hai cách đọc này giải quyết các vấn đề khác nhau. Phân trang tạo ra những lát dữ liệu hữu hạn để API và client tiếp tục qua nhiều request. Đọc theo luồng giữ một pipeline mở để phần tử đi qua dần. Cả hai đều cần một thứ tự xác định và một chiến lược nhất quán khi dữ liệu thay đổi trong lúc đọc.

Trong Java reactive, Spring Data R2DBC và Reactor có thể biểu diễn kết quả truy vấn bằng Mono và Flux. Reactive Streams bổ sung cơ chế backpressure giữa publisher và subscriber. Tuy vậy, backpressure không tự bảo đảm database driver không buffer, và việc đọc từng trang không tự tạo một snapshot dữ liệu bất biến. Thiết kế phải xét đồng thời truy vấn, transaction, driver và vòng đời của subscriber.

## 1. Phân trang và đọc theo luồng khác nhau thế nào?

Phân trang chia một tập kết quả thành các phần hữu hạn. Client yêu cầu trang đầu, nhận một nhóm bản ghi và thông tin để lấy trang tiếp theo. Mỗi request thường kết thúc sau khi lấy một trang.

Đọc theo luồng phát từng bản ghi qua một publisher. Subscriber có thể xử lý bản ghi ngay khi nhận được, yêu cầu thêm dữ liệu theo demand và hủy khi không còn cần kết quả.

| Tiêu chí | Phân trang | Đọc theo luồng |
|---|---|---|
| Đơn vị trả về | Một trang hữu hạn | Chuỗi phần tử phát dần |
| Vòng đời | Thường một request cho mỗi trang | Một subscription có thể tồn tại lâu |
| Bộ nhớ ứng dụng | Giới hạn theo kích thước trang | Có thể thấp nếu xử lý từng phần tử và buffer có giới hạn |
| Tiếp tục sau gián đoạn | Dùng page number hoặc cursor | Thường cần checkpoint hoặc cursor riêng |
| Tài nguyên database | Có thể giải phóng sau từng trang | Cursor/connection có thể bị giữ trong lúc stream |
| Tính nhất quán | Các trang có thể nhìn thấy snapshot khác nhau | Một stream có thể nằm trong một transaction/snapshot dài |

Chọn phân trang cho API danh sách, màn hình có nút tiếp theo, tìm kiếm và tác vụ cần tiếp tục từ cursor. Chọn đọc theo luồng cho pipeline xử lý lớn, export có kiểm soát hoặc endpoint streaming khi client thực sự cần nhận dữ liệu dần.

Không nên mặc định dùng một Flux để đọc toàn bộ bảng rồi gọi collectList. Khi đó dữ liệu cuối cùng vẫn được giữ toàn bộ trong bộ nhớ, làm mất lợi ích của xử lý theo luồng.

## 2. Phân trang OFFSET/LIMIT

Phân trang offset chọn một số lượng bản ghi và bỏ qua một số lượng bản ghi đứng trước:

    SELECT id, created_at, payload
    FROM event_log
    WHERE tenant_id = :tenantId
    ORDER BY created_at ASC, id ASC
    LIMIT :pageSize
    OFFSET :offset;

Nếu pageSize bằng 50:

- Trang đầu dùng offset 0.
- Trang thứ hai dùng offset 50.
- Trang thứ ba dùng offset 100.

OFFSET/LIMIT dễ hiểu, dễ tích hợp với giao diện hiển thị số trang và phù hợp khi tập dữ liệu nhỏ hoặc người dùng cần nhảy đến một trang cụ thể.

Nhưng offset lớn có thể tốn chi phí. Database vẫn phải tìm và đi qua các hàng bị bỏ qua trước khi trả phần dữ liệu cần thiết. Trang càng sâu, công việc bỏ qua càng lớn, tùy execution plan và index của database.

OFFSET cũng dễ bị ảnh hưởng khi dữ liệu thay đổi giữa các request. Giả sử trang đầu đã trả các hàng từ 1 đến 50. Trước khi client yêu cầu trang hai, một hàng mới được chèn vào đầu thứ tự. Khi offset 50 được áp dụng lần nữa, một hàng đã thấy có thể xuất hiện lặp lại. Nếu một hàng trước vị trí offset bị xóa, client có thể bỏ sót một hàng.

Vì vậy, OFFSET/LIMIT cần:

- Một ORDER BY xác định.
- Kích thước trang có giới hạn.
- Hiểu rõ rằng các request trang riêng biệt có thể quan sát dữ liệu ở những thời điểm khác nhau.
- Một chính sách rõ ràng nếu dữ liệu được thêm, xóa hoặc thay đổi trong lúc người dùng duyệt.

## 3. Thứ tự phải ổn định và có khóa phân biệt

Không phân trang trên truy vấn không có ORDER BY. Database không bảo đảm thứ tự hàng nếu câu truy vấn không yêu cầu một thứ tự cụ thể.

Chỉ sắp xếp theo một cột không duy nhất cũng chưa đủ. Ví dụ nhiều bản ghi có cùng created_at. Database có thể trả các bản ghi cùng timestamp theo thứ tự khác nhau ở những lần thực thi khác nhau.

Hãy thêm một khóa phân biệt duy nhất làm tie-breaker:

    ORDER BY created_at ASC, id ASC

Trong ví dụ này, cặp created_at và id xác định thứ tự toàn phần nếu id là duy nhất. Khi dùng phân trang, thứ tự này phải giống nhau giữa truy vấn trang đầu và các truy vấn tiếp theo.

Tốt nhất các cột sort key không nên nhận giá trị NULL. Nếu nghiệp vụ cho phép NULL, phải xác định rõ NULL đứng trước hay sau và viết điều kiện cursor tương ứng; phép so sánh thông thường với NULL không tạo ra điều kiện seek đúng. Quy tắc NULL ordering cũng phải giống nhau giữa mọi trang.

Nếu sắp xếp giảm dần, mọi điều kiện cursor cũng phải đổi theo cùng chiều:

    ORDER BY created_at DESC, id DESC

    WHERE created_at < :lastCreatedAt
       OR (
            created_at = :lastCreatedAt
            AND id < :lastId
       )

Không trộn chiều sắp xếp và điều kiện so sánh cursor. Với nhiều cột sort khác chiều, cần viết điều kiện seek tương ứng cho từng thành phần và kiểm thử biên.

## 4. Keyset pagination (seek pagination)

Keyset pagination lấy trang tiếp theo dựa trên giá trị của bản ghi cuối cùng ở trang trước. Thay vì nói “bỏ qua 10.000 hàng”, client nói “lấy các hàng đứng sau khóa này”.

Với thứ tự tăng dần theo created_at và id:

    SELECT id, created_at, payload
    FROM event_log
    WHERE tenant_id = :tenantId
      AND (
          created_at > :lastCreatedAt
          OR (
              created_at = :lastCreatedAt
              AND id > :lastId
          )
      )
    ORDER BY created_at ASC, id ASC
    LIMIT :pageSize;

Điều kiện này tìm các hàng sau cặp khóa cuối trang trước. Trang đầu chưa có cursor nên dùng truy vấn riêng chỉ có tenant, bộ lọc và ORDER BY.

Keyset pagination thường hiệu quả hơn offset ở các trang sâu nếu database có index phù hợp. Với truy vấn trên, index có thể bắt đầu bằng các cột lọc và thứ tự:

    CREATE INDEX idx_event_tenant_created_id
        ON event_log (tenant_id, created_at, id);

Index thực tế cần dựa trên database, cardinality, điều kiện lọc và execution plan. Không thêm index chỉ theo mẫu chung mà không đo truy vấn.

### 4.1. Vì sao keyset ít bị dịch chuyển trang?

Giả sử client đã đọc đến created_at = 10:00 và id = 500. Một bản ghi mới được chèn ở đầu bảng với timestamp sớm hơn sẽ không làm thay đổi điều kiện “lớn hơn cursor”; client vẫn tiếp tục sau khóa 500.

Keyset tránh vấn đề offset bị đẩy đi khi có hàng mới đứng trước vị trí hiện tại. Tuy nhiên, nó không tạo snapshot tuyệt đối:

- Hàng mới được chèn sau cursor có thể xuất hiện ở trang sau.
- Hàng bị xóa trước khi đọc sẽ không còn được trả về.
- Nếu cột sắp xếp có thể thay đổi, một hàng có thể di chuyển từ trước cursor ra sau cursor hoặc ngược lại.
- Các thay đổi ở những cột lọc có thể làm bản ghi đi vào hoặc rời khỏi tập kết quả.

Vì vậy, nên dùng khóa sắp xếp bất biến như sequence tăng đơn điệu hoặc timestamp tạo cùng ID bất biến. Nếu nghiệp vụ cần một bản export phản ánh chính xác dữ liệu tại một thời điểm, cần thêm snapshot hoặc watermark.

## 5. Cursor là hợp đồng giữa API và client

API cursor thường trả danh sách phần tử cùng một token cho trang tiếp theo:

    {
      "items": [
        { "id": "e-101", "createdAt": "2026-01-01T10:00:00Z" },
        { "id": "e-102", "createdAt": "2026-01-01T10:00:01Z" }
      ],
      "nextCursor": "eyJjcmVhdGVkQXQiOi..."
    }

Client gửi token trong request tiếp theo. Server giải mã cursor để lấy khóa cuối, áp dụng lại bộ lọc và thứ tự tương ứng.

Một cursor an toàn nên mang đủ thông tin để tiếp tục cùng truy vấn:

- Giá trị sort key cuối cùng, ví dụ created_at và id.
- Phiên bản định dạng cursor.
- Bộ lọc hoặc fingerprint của truy vấn.
- Tenant hoặc phạm vi dữ liệu phù hợp với danh tính đã xác thực.
- Snapshot marker hoặc watermark nếu có.

Cursor thường được mã hóa hoặc encode Base64 để truyền thuận tiện, nhưng Base64 không phải cơ chế bảo mật. Nếu client có thể sửa token, hãy ký token bằng HMAC hoặc dùng token ngẫu nhiên tham chiếu đến trạng thái lưu ở server. Server vẫn phải kiểm tra quyền truy cập ở mỗi request; không tin tenant ID trong cursor thay cho xác thực.

Không đưa dữ liệu nhạy cảm vào cursor dạng đọc được. Đặt giới hạn độ dài token và từ chối cursor sai định dạng, hết hạn hoặc thuộc phiên bản không hỗ trợ.

## 6. Dùng pageSize + 1 để xác định còn trang tiếp

Nếu API chỉ cần biết có trang kế tiếp hay không, không nhất thiết phải chạy COUNT(*) cho toàn bộ tập dữ liệu. Có thể truy vấn thêm một bản ghi:

    SELECT id, created_at, payload
    FROM event_log
    WHERE tenant_id = :tenantId
      AND (
          created_at > :lastCreatedAt
          OR (
              created_at = :lastCreatedAt
              AND id > :lastId
          )
      )
    ORDER BY created_at ASC, id ASC
    LIMIT :pageSizePlusOne;

Nếu pageSize là 50, truy vấn lấy tối đa 51 hàng. Nếu nhận 51 hàng, trả 50 hàng đầu và đặt hasNext = true. Cursor tiếp theo phải dựa trên hàng thứ 50 đã trả cho client, không dựa trên hàng thứ 51 chỉ được dùng để xác định còn dữ liệu.

Nếu nhận tối đa 50 hàng, hasNext = false. Cách này tránh một truy vấn count riêng và phù hợp với giao diện dùng nút “Tải thêm”.

Nếu sản phẩm cần tổng số chính xác, COUNT(*) vẫn có thể cần thiết. Nhưng count và truy vấn trang là hai câu lệnh khác nhau; ở mức isolation mặc định, chúng có thể nhìn thấy hai trạng thái dữ liệu khác nhau. Nếu cần total và items cùng phản ánh một snapshot, hãy thực hiện trong một transaction có isolation phù hợp với database.

## 7. Biểu diễn trang bằng kiểu dữ liệu rõ ràng

Một kiểu trang có thể chứa danh sách phần tử, cursor tiếp theo và cờ còn dữ liệu:

    record EventCursor(
        Instant createdAt,
        UUID id
    ) {}

    record EventPage(
        List<Event> items,
        String nextCursor,
        boolean hasNext
    ) {}

    interface EventRepository {
        Flux<Event> findFirstPage(
            String tenantId,
            Instant since,
            int limit
        );

        Flux<Event> findAfter(
            String tenantId,
            Instant since,
            EventCursor cursor,
            int limit
        );
    }

Hai phương thức repository minh họa hai truy vấn: trang đầu và trang có cursor. Cả hai trả Flux vì driver reactive phát các hàng theo luồng. Service chỉ gom tối đa pageSize + 1 hàng để xây dựng một trang hữu hạn:

    Mono<EventPage> loadPage(
        String tenantId,
        Instant since,
        EventCursor cursor,
        int pageSize
    ) {
        if (pageSize < 1 || pageSize > 500) {
            return Mono.error(
                new IllegalArgumentException("pageSize không hợp lệ")
            );
        }

        Flux<Event> rows = cursor == null
            ? repository.findFirstPage(
                tenantId, since, pageSize + 1
            )
            : repository.findAfter(
                tenantId, since, cursor, pageSize + 1
            );

        return rows.collectList()
            .map(found -> {
                boolean hasNext = found.size() > pageSize;
                int returnedCount =
                    Math.min(found.size(), pageSize);

                List<Event> items = List.copyOf(
                    found.subList(0, returnedCount)
                );

                String next = hasNext
                    ? cursorCodec.encode(
                        cursorOf(items.get(items.size() - 1))
                    )
                    : null;

                return new EventPage(items, next, hasNext);
            });
    }

Ví dụ giả định Event có các trường createdAt và id, còn cursorCodec là thành phần của ứng dụng chịu trách nhiệm encode/decode và ký cursor. Vì truy vấn chỉ lấy pageSize + 1 hàng, collectList ở đây có giới hạn rõ. Không áp dụng cách gom này cho toàn bộ bảng hoặc một stream không giới hạn.

List.copyOf tạo danh sách không thể sửa qua tham chiếu trả về. Điều này giúp DTO trang không bị thay đổi ngoài ý muốn sau khi được tạo.

## 8. Đọc dữ liệu theo luồng bằng Flux

Khi cần xử lý nhiều bản ghi liên tục, repository reactive có thể trả Flux:

    Flux<Event> events =
        eventRepository.findAllByTenantIdAndCreatedAtAfterOrderByCreatedAtAscIdAsc(
            tenantId,
            since
        );

Downstream có thể xử lý từng phần tử:

    Flux<ProcessedEvent> processed =
        events
            .filter(Event::isRelevant)
            .map(this::toProcessedEvent);

Nếu bước xử lý tiếp theo là I/O bất đồng bộ, dùng flatMap với concurrency giới hạn:

    Flux<DeliveryReceipt> receipts =
        processed.flatMap(
            event -> deliveryClient.send(event),
            16
        );

Concurrency giới hạn số publisher con được xử lý đồng thời. Nếu thứ tự xử lý phải giữ nguyên, dùng concatMap hoặc một chiến lược tuần tự phù hợp, chấp nhận thông lượng thấp hơn.

Một Flux có thể phát số lượng phần tử lớn mà không cần giữ toàn bộ chúng trong một List. Nhưng điều đó chỉ đúng nếu downstream cũng xử lý dần và các operator ở giữa không gom dữ liệu không giới hạn.

## 9. Backpressure và giới hạn bộ nhớ

Trong Reactive Streams, subscriber gửi request(n) để báo số phần tử có thể tiếp nhận. Publisher không được phát vượt quá nhu cầu đã cấp. Khi downstream chậm, demand có thể giảm hoặc ngừng tăng, giúp điều tiết luồng dữ liệu.

Ví dụ:

    Flux<Event> controlled =
        eventRepository.streamEvents()
            .limitRate(64);

limitRate điều tiết cách Reactor yêu cầu dữ liệu từ upstream theo các lô. Nó có thể giúp giới hạn lượng tín hiệu được đưa xuống các operator tiếp theo, nhưng không phải cam kết rằng database driver chỉ giữ đúng 64 hàng trong bộ nhớ.

Ở ranh giới database, cần hiểu thêm:

- Driver có dùng cursor hoặc fetch theo từng batch không?
- Statement có hỗ trợ fetch size không?
- Fetch size là cấu hình bắt buộc hay chỉ là hint của driver?
- Connector có buffer dữ liệu đã đọc từ socket không?
- Query có cần sort hoặc materialize toàn bộ kết quả ở database không?

R2DBC SPI và từng driver có mức hỗ trợ khác nhau. Một cấu hình fetch size có thể được driver xem như gợi ý hoặc không có tác dụng nếu database/driver không hỗ trợ cursor tương ứng. Hãy đọc tài liệu driver và đo bộ nhớ, số round trip cùng thời gian giữ connection trong môi trường thực tế.

Các operator có thể làm tăng bộ nhớ:

| Operator/cách dùng | Tác động |
|---|---|
| collectList | Giữ toàn bộ phần tử cho đến khi nguồn hoàn tất |
| buffer(n) | Giữ tối đa một nhóm n phần tử cho mỗi buffer đang hoạt động |
| sort | Thường phải giữ dữ liệu cần sắp xếp trước khi phát kết quả |
| flatMap với concurrency lớn | Có thể có nhiều inner publisher và dữ liệu đang chờ đồng thời |
| onBackpressureBuffer không giới hạn | Có thể tăng bộ nhớ liên tục nếu upstream không dừng |
| limitRate | Điều tiết request theo lô, không thay thế cấu hình driver |

Nếu nguồn không thể tạm dừng, cần chọn buffer có giới hạn, drop, latest hoặc ghi vào hàng đợi bền vững theo ý nghĩa dữ liệu. Không drop sự kiện nghiệp vụ quan trọng chỉ để tránh áp lực bộ nhớ.

## 10. Stream qua HTTP và vòng đời connection

Một controller WebFlux có thể trả Flux để phát response dần, ví dụ NDJSON:

    @GetMapping(
        value = "/events/stream",
        produces = MediaType.APPLICATION_NDJSON_VALUE
    )
    Flux<Event> streamEvents(
        @RequestParam String tenantId
    ) {
        return eventService.streamEvents(tenantId);
    }

Framework có thể ghi từng phần tử khi publisher phát tín hiệu. Nếu client chậm, backpressure có thể lan ngược một phần qua pipeline. Tuy nhiên, một database cursor hoặc transaction có thể phải được giữ mở trong suốt thời gian client nhận dữ liệu.

Đây là trade-off quan trọng:

- Streaming trực tiếp giảm việc gom dữ liệu trong bộ nhớ.
- Một client chậm có thể kéo dài thời gian giữ connection và transaction.
- Client disconnect cần truyền cancellation để đóng cursor và giải phóng tài nguyên.
- Nếu export kéo dài nhiều phút, một job nền có thể phù hợp hơn một HTTP stream giữ connection lâu.

Với export lớn, cân nhắc worker đọc theo từng trang, ghi file vào object storage rồi trả job ID hoặc link tải. Cách này tách thời gian xử lý dữ liệu khỏi thời gian kết nối của trình duyệt.

## 11. Transaction và tính nhất quán của một trang

Một trang thường được lấy bằng một truy vấn hoặc một nhóm truy vấn như lấy items và count. Nếu hai truy vấn phải phản ánh cùng trạng thái dữ liệu, hãy thực hiện chúng trong transaction có isolation phù hợp.

Với Spring reactive transaction, có thể dùng TransactionalOperator:

    Mono<EventPage> page =
        transactionalOperator.transactional(
            loadPage(tenantId, since, cursor, pageSize)
        );

Transaction được gắn với subscription reactive. Khi publisher hoàn tất, transaction manager xử lý commit; khi có lỗi, transaction được rollback theo cấu hình và semantics của manager. Khi subscription bị hủy, transaction/resource cleanup cũng phải được thực hiện bởi transaction manager.

Transaction chỉ bao phủ publisher nằm trong phạm vi được bọc. Nếu gọi một phương thức reactive rồi tự subscribe ở nơi khác, phần việc đó có thể nằm ngoài transaction ban đầu. Hãy trả publisher xuyên suốt và để transaction operator hoặc framework sở hữu subscription.

Một transaction cho mỗi trang giúp thời gian giữ connection ngắn. Nhưng nếu mỗi trang là một request riêng, transaction của trang trước không giữ snapshot cho trang sau. Hai trang có thể nhìn thấy hai trạng thái dữ liệu khác nhau.

## 12. Vì sao nhiều trang không tự tạo thành một snapshot?

Giả sử client lấy trang đầu lúc 10:00:00 và trang tiếp theo lúc 10:00:05. Trong khoảng thời gian đó, một transaction khác có thể thêm, xóa hoặc sửa dữ liệu. Ở mức isolation như READ COMMITTED, mỗi câu lệnh có thể nhìn thấy snapshot tại thời điểm thực thi câu lệnh đó.

Hệ quả:

- OFFSET/LIMIT có thể lặp hoặc bỏ sót bản ghi khi hàng đứng trước offset thay đổi.
- Keyset ổn định hơn khi thêm dữ liệu trước cursor, nhưng vẫn có thể thấy hàng mới sau cursor.
- Bản ghi đổi sort key có thể di chuyển qua ranh giới cursor.
- Bản ghi đổi điều kiện lọc có thể xuất hiện hoặc biến mất giữa các trang.
- COUNT(*) và danh sách items có thể phản ánh các thời điểm khác nhau nếu không dùng snapshot chung.

Phân trang và isolation giải quyết hai lớp khác nhau. Keyset xác định vị trí tiếp tục trong thứ tự dữ liệu. Isolation xác định những thay đổi nào được nhìn thấy trong transaction. Không có operator Reactor nào tự tạo snapshot nhất quán cho nhiều request độc lập.

## 13. Các chiến lược giữ tính nhất quán khi duyệt nhiều trang

Chọn chiến lược dựa trên yêu cầu nghiệp vụ:

### 13.1. Chấp nhận dữ liệu thay đổi theo từng trang

Đây là cách đơn giản cho màn hình danh sách thông thường. Dùng keyset với thứ tự ổn định, chấp nhận bản ghi mới có thể xuất hiện ở trang sau và bản ghi đã xóa sẽ không còn được trả về.

Hãy ghi rõ semantics cho người dùng nếu danh sách có thể thay đổi khi họ đang duyệt. Không hứa rằng toàn bộ các trang tạo thành một snapshot.

### 13.2. Dùng watermark hoặc cutoff

Khi bắt đầu export, hệ thống ghi nhận một mốc như created_at <= cutoff hoặc sequence <= highWatermark. Mọi trang sau tiếp tục dùng cùng mốc.

Watermark ngăn bản ghi mới hơn mốc lọt vào kết quả, miễn là cột/sequence được chọn có semantics đáng tin cậy và không bị sửa ngược. Nó không tự bảo vệ khỏi update hoặc delete trên bản ghi cũ.

Ví dụ:

    SELECT id, created_at, payload
    FROM event_log
    WHERE tenant_id = :tenantId
      AND created_at <= :cutoff
      AND (
          created_at > :lastCreatedAt
          OR (
              created_at = :lastCreatedAt
              AND id > :lastId
          )
      )
    ORDER BY created_at ASC, id ASC
    LIMIT :pageSize;

Cursor phải giữ cutoff cùng sort key cuối. Nếu cutoff được tạo từ đồng hồ ứng dụng, cần xem xét độ lệch đồng hồ và độ trễ ghi dữ liệu. Một sequence do database cấp hoặc một snapshot marker được tạo tại nguồn có thể phù hợp hơn.

### 13.3. Dùng snapshot isolation hoặc repeatable read

Nếu tất cả truy vấn phải nhìn cùng một snapshot, có thể thực hiện chúng trong một transaction với isolation như REPEATABLE READ hoặc cơ chế snapshot tương đương của database. Chi tiết phụ thuộc hệ quản trị và cấu hình transaction manager.

Giữ transaction mở trong toàn bộ quá trình duyệt nhiều trang có thể giữ connection, snapshot và phiên bản hàng lâu. Điều này làm tăng áp lực lên connection pool và cơ chế vacuum/cleanup của database. Không nên mở transaction kéo dài qua nhiều request HTTP của người dùng.

Với export lớn cần snapshot nghiêm ngặt, cân nhắc cơ chế database-specific để export/import snapshot, tạo bảng staging hoặc materialize tập ID cần xử lý. Các cách này cần thiết kế riêng cho database và thời gian lưu snapshot.

### 13.4. Dùng dữ liệu versioned hoặc immutable

Nếu nghiệp vụ lưu lịch sử thay vì sửa tại chỗ, có thể truy vấn theo version hoặc thời điểm hiệu lực. Ví dụ bảng event append-only với sequence tăng đơn điệu giúp cursor và watermark ổn định hơn.

Với dữ liệu mutable, có thể lưu phiên bản, valid_from/valid_to hoặc audit log để truy vấn trạng thái tại một mốc. Đổi lại, schema và truy vấn phức tạp hơn.

## 14. Chọn cách đọc theo nhu cầu

| Nhu cầu | Cách tiếp cận |
|---|---|
| Màn hình nhỏ, cần số trang và nhảy trang | OFFSET/LIMIT với ORDER BY ổn định |
| Danh sách lớn, tải tiếp theo từ vị trí trước | Keyset pagination |
| Không cần tổng số chính xác | Lấy pageSize + 1 để tính hasNext |
| Xử lý nhiều hàng trong một pipeline | Flux và xử lý từng phần tử |
| Export lớn cần giải phóng connection giữa các batch | Job nền đọc theo trang |
| Export phải phản ánh một mốc dữ liệu | Watermark, versioned data hoặc snapshot database |
| Client cần nhận kết quả ngay khi có | HTTP streaming với lifecycle và timeout rõ |

Không có lựa chọn nào tối ưu cho mọi trường hợp. OFFSET thuận tiện nhưng có thể tốn chi phí ở trang sâu. Keyset hiệu quả cho tiếp tục theo thứ tự nhưng không hỗ trợ nhảy đến số trang tùy ý. Stream tiết kiệm bộ nhớ khi xử lý dần nhưng có thể giữ tài nguyên lâu. Snapshot mạnh về tính nhất quán nhưng có chi phí vận hành.

## 15. Kiểm thử phân trang và tính nhất quán

Kiểm thử nên xác nhận các invariant của truy vấn:

- Mỗi trang có tối đa pageSize phần tử.
- Thứ tự giữa các phần tử được xác định bằng sort key và tie-breaker.
- Cursor tiếp theo lấy từ phần tử cuối cùng đã trả.
- Trang cuối có hasNext = false và không phát cursor tiếp.
- Cursor sai định dạng, hết hạn hoặc không khớp bộ lọc bị từ chối.
- Hai hàng cùng timestamp vẫn được phân trang đủ nhờ khóa tie-breaker.
- Hành vi khi có insert, update hoặc delete giữa hai request đúng với semantics đã công bố.

Ví dụ kiểm thử service phân trang bằng StepVerifier:

    StepVerifier.create(
            eventService.loadPage(
                "tenant-A",
                cutoff,
                null,
                2
            )
        )
        .assertNext(page -> {
            assertEquals(2, page.items().size());
            assertTrue(page.hasNext());
            assertNotNull(page.nextCursor());
        })
        .verifyComplete();

Để kiểm tra keyset, tạo nhiều bản ghi có cùng created_at nhưng id khác nhau. Lấy trang liên tiếp và xác nhận mỗi ID xuất hiện đúng một lần theo thứ tự. Sau đó chèn một bản ghi trước cursor giữa hai lần đọc để kiểm tra rằng trang tiếp theo không bị dịch chuyển như offset.

Để kiểm tra transaction và snapshot, cần integration test với database thật hoặc Testcontainers phù hợp. Mock repository có thể xác nhận cách service truyền cursor, nhưng không mô phỏng đầy đủ isolation, index, cursor fetch và hành vi concurrent commit của database.

Với stream, kiểm thử cancellation để xác nhận publisher upstream bị hủy và tài nguyên được giải phóng. Có thể dùng TestPublisher hoặc nguồn kiểm thử có hook onCancel. Với driver R2DBC, bổ sung integration test để xác nhận connection được trả về pool sau complete, error và cancel.

## 16. Những lỗi thường gặp

**Phân trang không có ORDER BY.** Database không cam kết thứ tự ổn định; trang có thể lặp hoặc thiếu dữ liệu ngay cả khi bảng không đổi.

**Sắp xếp theo cột không duy nhất.** Các hàng cùng giá trị sort có thể đổi thứ tự. Thêm tie-breaker duy nhất.

**Dùng OFFSET cho trang rất sâu mà không đo chi phí.** Database có thể phải bỏ qua nhiều hàng. Xem xét keyset và index phù hợp.

**Dùng keyset với sort key có thể thay đổi.** Bản ghi có thể di chuyển qua cursor và xuất hiện lặp hoặc bị bỏ sót. Ưu tiên khóa bất biến hoặc snapshot.

**Cho rằng keyset tạo snapshot.** Keyset chỉ định vị trí tiếp tục; nó không ngăn insert, update hoặc delete.

**Gọi collectList trên toàn bộ stream.** Bộ nhớ tăng theo tổng số hàng. Chỉ gom một trang có kích thước giới hạn.

**Cho rằng backpressure kiểm soát mọi buffer của database.** Driver và connector có thể buffer riêng. Đọc tài liệu và đo hành vi thực tế.

**Giữ transaction mở trong lúc client tải dữ liệu rất chậm.** Connection và snapshot có thể bị giữ lâu. Cân nhắc batch hoặc job nền.

**Chạy count và query trang mà không xét isolation.** Hai kết quả có thể phản ánh hai snapshot khác nhau.

**Dùng cursor như một cơ chế phân quyền.** Cursor phải được kiểm tra chữ ký và phạm vi; server vẫn phải xác thực và kiểm tra quyền ở mỗi request.

## 17. Checklist trước khi triển khai

Trước khi đưa phân trang hoặc streaming vào production, hãy trả lời:

1. Client cần nhảy đến số trang hay chỉ cần tiếp tục từ vị trí trước?
2. ORDER BY có xác định và chứa khóa tie-breaker duy nhất không?
3. Các cột dùng làm cursor có bất biến trong suốt vòng đời bản ghi không?
4. Truy vấn có index phù hợp với filter và thứ tự không?
5. Có thể dùng pageSize + 1 thay cho COUNT(*) không?
6. Cursor có gắn với filter, tenant, sort version và watermark phù hợp không?
7. Server có xác thực và kiểm tra quyền ở mỗi request tiếp tục không?
8. Dữ liệu có thể thay đổi giữa các trang theo cách nào?
9. Nghiệp vụ cần eventual consistency, watermark hay snapshot nghiêm ngặt?
10. Transaction được mở trong bao lâu và ai sở hữu connection?
11. Flux và các operator trung gian có buffer không giới hạn hoặc gom toàn bộ không?
12. Driver R2DBC có hỗ trợ cursor/fetch size như mong đợi không?
13. Cancellation, timeout và disconnect có giải phóng tài nguyên không?
14. Test đã bao phủ insert, update, delete, cursor boundary và transaction isolation chưa?

Phân trang, đọc theo luồng và tính nhất quán dữ liệu cần được thiết kế cùng nhau. OFFSET/LIMIT phù hợp với tập nhỏ và điều hướng theo số trang; keyset phù hợp với tập lớn và tiếp tục theo thứ tự ổn định; Flux giúp xử lý dữ liệu dần theo demand. Transaction, watermark hoặc snapshot xác định dữ liệu nào được nhìn thấy trong quá trình đọc. Khi chọn rõ semantics, giới hạn buffer và quyền sở hữu tài nguyên, ứng dụng reactive Java có thể xử lý tập dữ liệu lớn mà vẫn kiểm soát được bộ nhớ và tính đúng đắn của kết quả.
