# Di chuyển dữ liệu giữa dịch vụ khi ranh giới nghiệp vụ thay đổi

Khi áp dụng microservices, mỗi dịch vụ thường sở hữu một phần dữ liệu, quy tắc nghiệp vụ và vòng đời của các thực thể. Nhưng mô hình nghiệp vụ có thể tiến hóa. Ví dụ Account Service ban đầu quản lý cả tài khoản đăng nhập lẫn địa chỉ khách hàng; sau này tổ chức quyết định tách Customer Profile Service để sở hữu thông tin hồ sơ và địa chỉ. Khi đó chỉ sao chép bảng từ database cũ sang database mới **chưa đủ**.

**Di chuyển dữ liệu giữa dịch vụ khi ranh giới nghiệp vụ thay đổi** là quá trình chuyển quyền sở hữu dữ liệu và các bất biến nghiệp vụ từ dịch vụ nguồn sang dịch vụ đích trong khi hệ thống tiếp tục hoạt động. Phải bảo đảm không mất bản ghi đã xác nhận, không áp dụng nhầm phiên bản cũ, không tạo hai nơi cùng ghi và không làm lộ dữ liệu giữa các tenant.

Một cuộc chuyển đổi thành công phải giải quyết đồng thời: nguồn sự thật sau chuyển đổi, khả năng tương thích giữa phiên bản cũ/mới, backfill dữ liệu lịch sử, đồng bộ những thay đổi phát sinh, đối soát tính đúng, cắt chuyển đường đọc/ghi, theo dõi hệ thống và kế hoạch rollback hoặc roll-forward.

Bài học này minh họa quy trình với Java/Spring Boot, PostgreSQL, message broker, transactional outbox và Change Data Capture (CDC). Nguyên tắc cốt lõi là **mỗi tập dữ liệu canonical chỉ có một quyền ghi chính thức tại một thời điểm được xác định rõ**.

## 1. Vì sao ranh giới dữ liệu cần thay đổi?

Những dấu hiệu thường gặp:

- Một service chịu nhiều trách nhiệm không liên quan, ví dụ vừa xác thực người dùng vừa tính tiền, quản lý hồ sơ và địa chỉ.
- Team phụ trách một quy tắc nghiệp vụ phải deploy cùng những chức năng khác không liên quan.
- Một nhóm dữ liệu có lưu lượng, retention, backup, bảo mật hoặc chi phí tăng trưởng hoàn toàn khác phần còn lại.
- Các dịch vụ dùng chung database và thay đổi schema làm hỏng consumer.
- Nhiều team cùng sửa một bảng, không ai có quyền sở hữu invariant rõ.
- Một khái niệm trước đây là thuộc tính đơn giản nay thành nghiệp vụ với trạng thái và workflow riêng.
- Yêu cầu về quyền riêng tư, audit hoặc data residency cần tách luồng xử lý.

Không nên tách service chỉ để tăng số lượng microservices. Nếu các thực thể phải được cập nhật atomically để giữ invariant, chia chúng thành hai service có thể tạo thêm consistency problem. Hãy ưu tiên ranh giới nghiệp vụ thay vì chia bảng một cách máy móc.

## 2. Bounded context và quyền sở hữu dữ liệu

Trong Domain-Driven Design, **bounded context** là phạm vi mà một mô hình và thuật ngữ có nghĩa nhất quán. Cùng tên Customer nhưng ý nghĩa có thể khác:

- Identity Context: danh tính đăng nhập, mật khẩu hash, quyền xác thực.
- Profile Context: tên hiển thị, địa chỉ liên hệ, tùy chọn giao tiếp.
- Order Context: người đặt hàng và snapshot địa chỉ tại lúc xác nhận đơn.
- Billing Context: người chịu trách nhiệm hóa đơn và tài chính.
- Support Context: thông tin khách hàng tối thiểu dành cho nhân viên có quyền.

Không cần buộc tất cả những thông tin này vào một bảng customer.

**Canonical data** là dữ liệu có nơi sở hữu quyết định trạng thái cuối cùng.

**Replicated read model** là bản sao phục vụ truy vấn nhanh; phải xác định nguồn cập nhật, độ trễ cho phép và cách dựng lại.

**Immutable snapshot** là dữ kiện nghiệp vụ đã chốt, ví dụ địa chỉ giao hàng của đơn hoàn tất. Nó không tự thay đổi khi khách sửa hồ sơ.

**Audit data** là thông tin phục vụ kiểm toán, có retention/integrity riêng, không được tự xóa chỉ vì một bảng nguồn chuyển owner.

Một service chỉ thật sự chuyển ownership khi quyền quyết định, API ghi, validation và invariants cũng được chuyển; database copy mới chỉ là một bước.

## 3. Ví dụ: tách địa chỉ từ Account sang Profile

Trước chuyển đổi:

    Account Service
      account_db:
        accounts
        credentials
        profiles
        addresses
        preferences

    Order Service
      -> truy vấn trực tiếp bảng addresses trong account_db
      -> giữ snapshot địa chỉ trên đơn đã xác nhận

    Support UI
      -> gọi Account API để sửa hồ sơ

Sau chuyển đổi:

    Identity Service
      identity_db:
        accounts, credentials

    Customer Profile Service
      profile_db:
        profiles, addresses, preferences
      Profile REST API
      AddressChanged events

    Order Service
      -> gọi Profile API khi xác nhận địa chỉ
      -> lưu snapshot của đơn

    Analytics
      -> projection/ETL theo hợp đồng dữ liệu

Mục tiêu cuối cùng: Profile Service nhận lệnh tạo/sửa/xóa địa chỉ; Account không còn ghi bảng địa chỉ; Order không được truy vấn trực tiếp database của Profile mà dùng API hoặc read model phù hợp.

Phải phân biệt **địa chỉ hiện tại** thuộc Profile với **địa chỉ trên đơn đã chốt** thuộc Order. Nếu không, migration có thể làm sai lịch sử giao hàng khi khách đổi thông tin.

## 4. Kiểm kê toàn bộ readers và writers

Trước khi viết migration, lập bản đồ phụ thuộc:

- REST/gRPC endpoints.
- Mobile/Web clients còn gọi endpoint cũ.
- Background jobs, cron, ETL và report.
- Direct SQL connections từ service khác.
- Search index, cache và materialized views.
- Kafka/RabbitMQ publishers và consumers.
- BI dashboards và admin/support tools.
- Các transaction đang mở, retry queues, DLQ.
- Audit logs, backup và quyền truy cập dữ liệu.

Một ma trận minh họa:

| Consumer | Hiện tại | Sau migration | Consistency |
| --- | --- | --- | --- |
| Profile UI | Account API | Profile API | Read-your-writes |
| Checkout | Account DB trực tiếp | Profile API khi chốt | Dữ liệu đúng tại thời điểm xác nhận |
| Shipping | Order snapshot | Giữ Order snapshot | Immutable |
| Analytics | SQL bảng cũ | Event/ETL mới | Eventual |
| Support | Account API | Profile API theo quyền | Read-your-writes |
| Legacy export | SQL trực tiếp | Pipeline có kiểm soát | Batch |

Không thể xóa bảng chỉ vì luồng người dùng chính đã đổi thành công. Một report hoặc batch job chạy hằng tháng vẫn có thể phụ thuộc schema cũ.

## 5. Thiết lập hợp đồng dữ liệu đích

Trước backfill, thống nhất:

| Thuộc tính | Giá trị minh họa |
| --- | --- |
| Entity | Current Customer Address |
| New owner | Customer Profile Service |
| Canonical key | tenant_id + customer_id + address_id |
| Writer sau cutover | Profile Service duy nhất |
| API write | PUT /customers/{id}/addresses/{addressId} |
| API read | GET /customers/{id}/addresses |
| Event types | AddressCreated, AddressUpdated, AddressDeleted |
| Event ID | UUID cho mỗi thay đổi đã commit |
| Business version | data_version tăng đơn điệu theo aggregate |
| Consumer model | Eventual projection hoặc immutable snapshot |
| Access control | Tenant membership và quyền hành động |
| Delete policy | Tombstone/version + retention hợp lệ |
| Rollback boundary | Phụ thuộc việc target đã nhận write hay chưa |

Tên endpoint chỉ mang tính ví dụ. Quan trọng là định nghĩa ai làm owner, cách khóa dữ liệu, quy tắc validation, exception semantics và mức nhất quán.

## 6. Phân loại dữ liệu cần chuyển

Không nên chuyển nguyên một database mà không phân tích:

| Loại dữ liệu | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Canonical | Địa chỉ liên hệ hiện tại | Chuyển owner |
| Snapshot | Địa chỉ đã chốt trên đơn | Giữ với Order |
| Projection | Customer search index | Rebuild từ owner |
| Cache | Profile cache | Invalidate/rewarm |
| Audit | Ai sửa, lúc nào | Giữ retention và integrity |
| PII | Email, số điện thoại | Data minimization, encryption, deletion |
| Objects | Avatar, tệp | Copy metadata/object, checksum, ACL |
| Integration state | Event offset, idempotency key | Giữ để replay an toàn |
| Mapping | Legacy customer ID → new ID | Dùng mapping bền vững |

Một bảng có thể chứa nhiều nhóm khác nhau. Chuyển ownership dựa trên ngữ nghĩa của field, transaction và invariant; không mặc định mỗi bảng phải chuyển nguyên vẹn.

## 7. Xác định bất biến nghiệp vụ và consistency

Ví dụ bất biến:

- Một địa chỉ chỉ thuộc một tenant/customer hợp lệ.
- Một customer chỉ có một địa chỉ mặc định theo loại, nếu nghiệp vụ quy định.
- Record đã xóa không được hồi sinh bởi event cũ.
- Update version 10 không thể ghi đè version 11.
- Order đã xác nhận giữ snapshot địa chỉ hợp lệ.
- Người dùng A không truy cập được dữ liệu của tenant B.
- Khi API báo cập nhật thành công, đọc qua owner thấy dữ liệu theo cam kết.

Phân biệt:

**Strong/read-your-writes:** Profile API đảm bảo nhìn thấy cập nhật đã xác nhận theo contract.

**Eventual:** read model Search/Analytics chấp nhận lag; cần đo lag và replay.

**Immutable:** Order snapshot không đổi theo cập nhật hồ sơ sau đó.

Tách service làm một transaction local thành các giao tiếp phân tán có thể ảnh hưởng consistency. Trước khi tách, xác định invariant nào cần nằm cùng aggregate và invariant nào có thể kiểm soát bằng workflow/reconciliation.

## 8. Phương pháp Expand – Backfill – Catch up – Cutover – Contract

    DISCOVER
      Bounded contexts, consumers, business invariants
        |
        v
    EXPAND
      New schema, API, events, compatibility
        |
        v
    BACKFILL
      Copy historical snapshot in batches
        |
        v
    CATCH UP
      Apply ongoing changes through CDC/outbox
        |
        v
    RECONCILE
      Compare keys, values, versions and deletions
        |
        v
    CUTOVER
      Drain/fence old writer, transfer routing
        |
        v
    STABILIZE
      Observe business SLO, mismatches and failures
        |
        v
    CONTRACT
      Remove legacy contract/schema after safe window

**Backfill xong không đồng nghĩa hệ thống mới đã bắt kịp những thay đổi mới nhất.** **Read API chạy tốt không chứng minh new write owner đúng.** Vì vậy các bước cần điều kiện chuyển trạng thái rõ và không nên gộp thành một deploy phá hủy.

## 9. Expand: chuẩn bị database đích

Ví dụ PostgreSQL:

    create table customer_addresses (
      tenant_id uuid not null,
      customer_id uuid not null,
      address_id uuid not null,
      recipient_name varchar(200) not null,
      street_text text not null,
      city_code varchar(40) not null,
      status varchar(30) not null,
      data_version bigint not null,
      updated_at timestamptz not null,
      primary key (tenant_id, customer_id, address_id)
    );

    create index address_by_customer
      on customer_addresses
      (tenant_id, customer_id, updated_at);

Đây là schema minh họa, phải điều chỉnh theo miền thật. Khi chuẩn bị:

- Chạy Flyway/Liquibase migration vào target DB sạch.
- Kiểm tra NOT NULL, UNIQUE, FK, index và query plan.
- Định nghĩa chuyển đổi các field legacy và enum.
- Đặt idempotency constraints và version.
- Chuẩn bị backup, secrets, encryption, database roles.
- Kiểm tra API/event version của consumer cũ/mới.
- Chuẩn bị quota source/target và resource monitoring.
- Bảo đảm target có thể hỗ trợ đồng thời schema hợp lệ qua các phiên bản triển khai.

Không xóa bảng/cột cũ trong phase expand.

## 10. ID mapping và anti-corruption layer

Có thể giữ canonical business ID, hoặc tạo ID mới nếu ngữ nghĩa và vòng đời thay đổi. Một bảng ánh xạ:

    create table profile_id_mapping (
      tenant_id uuid not null,
      legacy_customer_id uuid not null,
      profile_id uuid not null,
      migrated_at timestamptz not null,
      primary key (tenant_id, legacy_customer_id),
      unique (tenant_id, profile_id)
    );

**Anti-corruption layer** chuyển kiểu, enum, mã và thuật ngữ legacy sang domain model mới. Nó giúp target không phải lưu toàn bộ semantics cũ mãi mãi.

Lưu ý:

- Mapping phải duy nhất, không trộn tenant.
- Một record source có thể được hợp nhất/tách theo quy tắc miền mới.
- Cần version hóa transform và kiểm thử dữ liệu biên.
- Không biến foreign key xuyên database thành ràng buộc vật lý giữa service.
- Nếu invariant bắt buộc cập nhật atomically, xem lại ranh giới aggregate thay vì dùng cross-database FK.

## 11. Chuẩn hóa dữ liệu legacy

Dữ liệu cũ thường có:

- NULL ở field bắt buộc của schema mới.
- Enum đã hết dùng.
- Địa chỉ hoặc mã vùng không thống nhất.
- Customer đã đóng hoặc hợp nhất.
- Khóa trùng do schema cũ thiếu constraint.
- Timestamp khác timezone hoặc precision.
- Dữ liệu tham chiếu không còn tồn tại.

Ba cách xử lý:

**Preserve with status:** lưu dữ liệu mà không làm mất thông tin, đánh dấu cần sửa.

**Deterministic transform:** quy tắc chuyển đổi rõ ràng, cùng input cho cùng output; có version.

**Quarantine:** dữ liệu không thể quyết định an toàn được đưa vào quy trình xử lý ngoại lệ.

Không chèn giá trị giả chỉ để vượt validation, đặc biệt với dữ liệu tài chính và thông tin định danh. Mỗi record lỗi cần key, reason, trạng thái và người phụ trách, không đưa PII trần vào log.

## 12. Backfill theo batch có checkpoint

Backfill copy snapshot lịch sử theo khóa ổn định.

    Source DB
      |
      +--> consistent snapshot
      |         |
      |         v
      |     keyset reader
      |         |
      |         v
      |     validate / transform
      |         |
      |         v
      |     idempotent target upsert
      |
      +--> delta stream from checkpoint
                |
                v
           target consumer

Nguyên tắc:

1. Ghi snapshot checkpoint có ý nghĩa với transaction log/CDC.
2. Đọc theo keyset hoặc shard để tránh OFFSET lớn thiếu ổn định.
3. Giới hạn batch size và concurrency để không gây overload production.
4. Upsert theo unique key và version, an toàn khi chạy lại.
5. Commit transaction target rồi **mới lưu checkpoint**.
6. Ghi lỗi vào quarantine và có cách xử lý.
7. Cho phép pause/resume nếu source/target DB bão hòa.
8. Ghi progress, rate và remaining estimate bằng metrics.
9. Đồng bộ các cập nhật mới bằng delta cho đến cutover.

SQL đọc keyset:

    select tenant_id, customer_id, address_id,
           recipient_name, street_text, city_code,
           status, data_version, updated_at
      from legacy_customer_addresses
     where (tenant_id, customer_id, address_id)
           > (:last_tenant, :last_customer, :last_address)
     order by tenant_id, customer_id, address_id
     limit :batch_size;

Cú pháp tuple comparison yêu cầu DB/kiểu dữ liệu hỗ trợ. Keyset giảm rủi ro dịch chuyển offset nhưng không tự giải quyết snapshot consistency khi record đang được cập nhật.

## 13. Bắt delta: CDC, outbox, freeze writes và dual-write

Dữ liệu vẫn thay đổi trong khi backfill chạy.

| Giải pháp | Ưu điểm | Rủi ro |
| --- | --- | --- |
| Freeze writes rồi copy | Đơn giản về consistency | Có downtime |
| CDC qua transaction log | Bắt thay đổi đã commit | Offset, schema, lag, delete |
| Transactional outbox | Event intent cùng transaction business | Replay và idempotency |
| Poll theo updated_at | Dễ ở dữ liệu ít biến động | Thiếu delete, timestamp không tin cậy |
| App dual-write | Có thể tích hợp nhanh | Partial failure giữa hai DB |

### CDC

CDC đọc WAL/transaction log và phát INSERT/UPDATE/DELETE. Phải bảo đảm:

- Snapshot checkpoint và log stream liên tục không có gap.
- CDC offset và recovery checkpoint bền vững.
- Log retention đủ khi connector chậm.
- Schema DDL thay đổi được xử lý có version.
- Tombstone/delete không bị bỏ qua.
- Event được xử lý lặp hoặc đảo thứ tự theo policy.
- Pipeline có quyền tối thiểu và bảo vệ PII.

Một row change chưa phải domain event đầy đủ. Consumer cần biết ngữ nghĩa, mapping và invariant.

### Transactional outbox

Business record và outbox event cùng commit:

    BEGIN
      UPDATE customer_addresses ...
      INSERT INTO outbox_events (
        event_id, aggregate_id, data_version, payload
      )
    COMMIT

    Outbox publisher -> Broker -> Target consumer

Nếu publisher crash sau khi gửi nhưng trước khi mark sent, event có thể được gửi lại. Consumer cần idempotent. Outbox tránh thất lạc intent sau commit; không tự đảm bảo exactly-once side effects giữa nhiều hệ thống.

### Dual-write không atomic

    Write source DB: SUCCESS
    Write target DB: TIMEOUT
    Client retry: trạng thái không rõ

Đảo thứ tự ghi không giải quyết vấn đề. Nếu phải dual-write tạm thời, cần một owner canonical, reconciliation, idempotency, retry budget và thời hạn kết thúc. Không để hai bên tự quyết định trạng thái đồng thời.

## 14. Data version và chống event cũ ghi đè

Một event có thể đến không đúng thứ tự:

    v10: address = A
    v11: address = B

    Target nhận v11 trước.
    Target nhận v10 do retry sau đó.
    Nếu update không kiểm tra -> cuối cùng A (sai).

Dùng monotonic data_version theo aggregate và target upsert khi version mới hơn.

    insert into customer_addresses (
      tenant_id, customer_id, address_id,
      recipient_name, street_text, city_code,
      status, data_version, updated_at
    )
    values (
      :tenant, :customer, :address,
      :recipient, :street, :city,
      :status, :version, :updated_at
    )
    on conflict (tenant_id, customer_id, address_id)
    do update set
      recipient_name = excluded.recipient_name,
      street_text = excluded.street_text,
      city_code = excluded.city_code,
      status = excluded.status,
      data_version = excluded.data_version,
      updated_at = excluded.updated_at
    where customer_addresses.data_version
          < excluded.data_version;

Không dựa duy nhất vào updated_at vì clock skew, precision và concurrent updates. Nếu cần mọi transition, consumer phải xử lý version gaps/replay chứ không chỉ lấy bản mới nhất.

**Schema version** mô tả hình dạng payload; **data version** mô tả thứ tự thay đổi một aggregate. Hai mục đích không thay thế nhau.

## 15. Idempotency và inbox

Message broker có thể giao lại sau retry, consumer restart hoặc acknowledgment thất bại.

    create table processed_events (
      consumer_name varchar(100) not null,
      event_id uuid not null,
      handled_at timestamptz not null default now(),
      primary key (consumer_name, event_id)
    );

Consumer có thể ghi processed_event và cập nhật state trong cùng local transaction. Event lặp không tạo business side effect thêm. Với API ngoài như payment, cần idempotency key được nhà cung cấp hỗ trợ hoặc reconciliation theo giao dịch; local inbox không bảo vệ tuyệt đối tác động bên ngoài.

Idempotency cũng cần cho migration batch: crash trước lưu checkpoint không được tạo row trùng hoặc phát email lần nữa khi chạy lại.

## 16. DELETE và tombstone

Nếu người dùng xóa một địa chỉ trong lúc migration, snapshot cũ có thể tới sau.

    t0: Address v7 = ACTIVE.
    t1: User xóa -> v8 = DELETED.
    t2: Target xử lý tombstone v8.
    t3: Backfill snapshot v7 tới muộn.
    t4: Target từ chối v7 vì version thấp hơn.

Nếu xóa cứng target mà không ghi nhận version đã xóa, snapshot v7 có thể làm bản ghi hồi sinh. Thiết kế tombstone hoặc delete journal có TTL/retention phù hợp và cơ chế không tái nhập record đã xóa.

Cần xét GDPR/quyền riêng tư và quy định liên quan nếu áp dụng: xóa/ẩn danh phải tới cả projections, cache, backups trong phạm vi chính sách. Audit record đôi khi có retention pháp lý riêng; không tùy tiện xóa hoặc lưu vô hạn.

## 17. Java/Spring Boot: transactional outbox

Ví dụ code ở service nguồn:

    import java.util.UUID;
    import org.springframework.stereotype.Service;
    import org.springframework.transaction.annotation.Transactional;

    @Service
    public class AddressCommandService {
        private final AddressRepository addresses;
        private final OutboxRepository outbox;

        public AddressCommandService(
            AddressRepository addresses,
            OutboxRepository outbox
        ) {
            this.addresses = addresses;
            this.outbox = outbox;
        }

        @Transactional
        public void changeAddress(
            UUID tenantId,
            UUID customerId,
            UUID addressId,
            AddressChange change
        ) {
            AddressEntity address = addresses.findForUpdate(
                tenantId, customerId, addressId
            ).orElseThrow();

            address.apply(change);
            long version = address.incrementVersion();

            addresses.save(address);
            outbox.save(OutboxEvent.of(
                UUID.randomUUID(),
                "AddressUpdated",
                tenantId, customerId, addressId,
                version, address.toSafePayload()
            ));
        }
    }

AddressRepository, AddressChange, AddressEntity và OutboxEvent là thành phần miền giả định, không phải lớp sẵn có của Spring Boot. Mẫu nhấn mạnh record thay đổi và event intent cùng commit/rollback. Publisher gửi event sau transaction, có thể retry/replay nên consumer phải idempotent.

Không đưa credential, token hoặc dữ liệu nhạy cảm không cần thiết vào event. Nếu payload chứa PII, bảo đảm truy cập broker, retention, encryption và DLQ tuân thủ chính sách.

## 18. Java/Spring Boot: target upsert theo version

Ví dụ repository dùng JDBC:

    import java.util.UUID;
    import org.springframework.jdbc.core.JdbcTemplate;
    import org.springframework.stereotype.Repository;

    record AddressChanged(
        UUID eventId, UUID tenantId,
        UUID customerId, UUID addressId,
        long version, String recipient,
        String street, String city, String status
    ) {}

    @Repository
    public class AddressProjectionRepository {
        private final JdbcTemplate jdbc;

        public AddressProjectionRepository(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        public int upsertIfNewer(AddressChanged event) {
            return jdbc.update(
                """
                insert into customer_addresses (
                  tenant_id, customer_id, address_id,
                  recipient_name, street_text, city_code,
                  status, data_version, updated_at
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, now())
                on conflict (tenant_id, customer_id, address_id)
                do update set
                  recipient_name = excluded.recipient_name,
                  street_text = excluded.street_text,
                  city_code = excluded.city_code,
                  status = excluded.status,
                  data_version = excluded.data_version,
                  updated_at = excluded.updated_at
                where customer_addresses.data_version
                      < excluded.data_version
                """,
                event.tenantId(), event.customerId(),
                event.addressId(), event.recipient(),
                event.street(), event.city(),
                event.status(), event.version()
            );
        }
    }

Đây là ví dụ projection trong lúc nguồn vẫn canonical, chưa chứa toàn bộ validation, delete, inbox và authorization. Khi target trở thành owner, nó phải có business commands và invariants riêng, không mãi chỉ là nơi sao chép raw events.

## 19. Checkpoint và khả năng resume

Một worker migration nên có trạng thái:

    migration_run:
      run_id
      source_owner
      target_owner
      entity_type
      phase
      snapshot_checkpoint
      last_backfill_key
      last_applied_delta_checkpoint
      read_count
      applied_count
      failed_count
      quarantine_count
      started_at
      updated_at

Quy tắc:

- Commit batch target trước khi save cursor.
- Nếu save cursor lỗi, chạy lại batch phải an toàn.
- Nhiều worker dùng shard/lease để không xử lý chồng chéo ngoài ý muốn.
- Có giới hạn retry, timeout và pause/resume.
- Phân biệt lỗi tạm thời với data error cần quarantine.
- Nếu CDC log đã hết retention, không nhảy mốc và tuyên bố đã bắt kịp; phải có resnapshot/repair.

Pseudo-code:

    while (hasMore) {
        batch = source.readAfter(cursor, limit);
        target.beginTransaction();
        for (row in batch) {
            target.upsertIfNewer(transform(row));
        }
        target.commitTransaction();
        storeCheckpoint(batch.lastKey);
        throttleBasedOnDatabaseLoad();
    }

Tính đúng không đến từ việc job chạy một lần không lỗi, mà từ khả năng chạy lại/recover mà không mất dữ liệu.

## 20. Reconciliation trước cutover

Đối soát không chỉ so tổng số hàng:

**Coverage:** keyset theo tenant/shard, missing/extra records.

**Content:** so các field sau normalization (timezone, Unicode, enum, địa chỉ).

**Version:** không còn record target thấp hơn checkpoint yêu cầu.

**Deletion:** record đã xóa không xuất hiện lại.

**Invariants:** mỗi customer có trạng thái/quan hệ hợp lệ.

**Audit/security:** không trộn tenant, đầy đủ quyền truy cập và history.

**Pipeline:** CDC lag/offset, DLQ, pending events, quarantine.

**Performance:** target có đủ throughput, index và connection budget.

Checksum theo chunk có thể giúp tìm mismatch, nhưng phải thống nhất serialization và normalization; hai JSON tương đương có thể khác thứ tự key. Sau khi tìm chunk lỗi, cần tra các record cụ thể.

Một mismatch dữ liệu quan trọng hoặc cross-tenant là điều kiện dừng, không được giảm tiêu chí để tiếp tục rollout.

## 21. Cutover: chuyển quyền ghi với fencing

Một quy trình:

1. Chọn tenant/cohort ổn định.
2. Tạm dừng hoặc route writes mới vào bounded holding path.
3. Drain các source transactions còn đang chạy.
4. Lấy checkpoint source commit cuối cùng.
5. Đợi target apply delta đến checkpoint.
6. Đối soát key/version/delete/invariants tại điểm đó.
7. **Fencing**: ngăn source tiếp tục commit write của cohort.
8. Chuyển owner routing sang target.
9. Cho target nhận lệnh mới với idempotency.
10. Kiểm tra nghiệp vụ thật và theo dõi SLO/mismatch.
11. Chỉ mở rộng cohort khi tất cả điều kiện đạt.

Fencing là cơ chế kỹ thuật: DB privileges, write gate, lease/epoch, owner registry và protocol phù hợp. Một feature flag ở Gateway không đủ nếu cron job cũ vẫn giữ quyền cập nhật DB.

### In-flight transaction

    10:00:00  Request X bắt đầu ghi ở source.
    10:00:01  Router chuyển lệnh mới sang target.
    10:00:02  Request Y ghi cùng address ở target.
    10:00:03  X commit source.

Đây là split-writer race. Phải drain/fence hoặc dùng ownership epoch đủ mạnh, không chuyển ngẫu nhiên request của cùng aggregate giữa hai nơi.

## 22. Chuyển từng tenant thay vì big bang

Hệ thống có hàng nghìn tenants có thể dùng owner registry:

    tenant_A -> SOURCE
    tenant_B -> TARGET
    tenant_C -> SOURCE

Và state machine:

    NOT_STARTED
      -> BACKFILLING
      -> CATCHING_UP
      -> READY_FOR_CUTOVER
      -> CUTOVER_IN_PROGRESS
      -> TARGET_OWNED
      -> STABILIZING
      -> COMPLETED

Mỗi bước có preconditions, audit và quyền chuyển trạng thái. Không sửa thẳng một boolean mà bỏ qua checkpoint. Routing nên ổn định theo tenant/aggregate; với workflow dài, định nghĩa cách xử lý các giao dịch đang chạy.

Một nhóm tenant nhỏ có thể phát hiện lỗi trước khi rollout rộng; vẫn phải theo dõi shared DB/broker resources vì một cohort cũng có thể làm quá tải nền tảng.

## 23. Đường đọc sau khi chuyển ownership

Có ba lựa chọn:

**Owner API:** cần dữ liệu mới nhất, ví dụ Profile UI hoặc Checkout lúc chọn địa chỉ. Phải đo latency, timeout và impact của dependency.

**Projection:** dùng event để cập nhật read model cho Search/Analytics. Có eventual consistency, lag và cơ chế rebuild.

**Immutable snapshot:** Order và Shipping giữ địa chỉ đã chốt; không query ngược Profile để sửa lịch sử đơn.

Một compatibility adapter tại Account Service có thể proxy các API cũ sang Profile trong giai đoạn chuyển tiếp, nhưng **không tiếp tục ghi source DB**. Có sunset date và metrics để biết client nào còn dùng API cũ.

## 24. Shadow read và so sánh trước release

    Request
       |
       +--> Source -> Response chính
       |
       +--> Target -> Normalize/compare
                          |
                          v
                     Mismatch metrics

Shadow read chỉ được dùng cho thao tác không có side effect. Giới hạn traffic, quyền truy cập và PII; không làm tăng gấp đôi tải production không kiểm soát. Phân biệt chênh lệch hợp lệ do eventual consistency với lỗi transform hoặc thiếu record.

Shadow read giúp kiểm tra đường đọc và chất lượng dữ liệu, không chứng minh new write owner hoặc transaction mới đã đúng.

## 25. Rollback khác roll-forward

**Trước cutover:** nguồn vẫn canonical; có thể dừng backfill/delta, sửa rồi chạy lại.

**Ngay sau fencing nhưng chưa có target writes:** có thể đưa routing về source nếu không có phân kỳ và quyền ghi được chuyển an toàn.

**Sau target đã nhận writes:** chỉ đổi flag về source có thể làm mất thay đổi mới. Cần reverse migration/reconciliation hoặc roll-forward trên target.

**Sau khi xóa schema cũ:** có thể không còn phương án rollback nhanh; cần backup/PITR và kế hoạch riêng.

Không giữ dual-write vô hạn chỉ để “dễ rollback”. Nếu reverse sync được lựa chọn, phải định nghĩa ai là nguồn sự thật, conflict resolution và giới hạn thời gian.

## 26. Consistency khi nghiệp vụ đi qua nhiều service

Sau khi tách, một thao tác trước đây nằm trong cùng database transaction có thể trở thành workflow phân tán.

Cần hỏi:

- Invariant nào thực sự phải atomic?
- Một service có thể quyết định và phát event cho service khác không?
- Trạng thái pending/retry được biểu diễn ở đâu?
- Khi downstream lỗi, cần compensation hay chỉ retry?
- Snapshot nào phải bất biến?
- Có nguy cơ double side effect khi event replay không?

Saga phù hợp với workflow có nhiều bước và compensation rõ; không bắt buộc mọi thay đổi Profile đều cần Saga. Trong nhiều trường hợp, Profile làm writer, Order lưu snapshot và Analytics nhận projection là đủ.

## 27. Kiểm thử tích hợp và failure scenarios

Dùng PostgreSQL engine thật và broker thật trong môi trường test cô lập khi kiểm tra SQL/transaction/event semantics.

Các nhóm test:

- Flyway/Liquibase schema và constraints đúng trên PostgreSQL.
- Backfill đầy đủ, chạy lại batch không tạo trùng.
- Crash trước/ sau target commit và checkpoint.
- Delta đến trước snapshot; snapshot cũ không ghi đè version mới.
- Delete/tombstone và event cũ không hồi sinh dữ liệu.
- CDC lag/gap hoặc WAL retention hết hạn được phát hiện.
- Message duplicate, out-of-order, retry/DLQ.
- Cutover và fencing writer cũ, kể cả cron job.
- Client cũ qua adapter không tạo write ở source.
- Tenant isolation, ID mapping và authorization.
- Order snapshot vẫn đúng khi Profile đổi địa chỉ.
- Hệ thống phục hồi khi target/broker tạm mất.
- PII không bị ghi vào log ngoài chính sách.

Với async assertions, chờ trạng thái cuối bằng polling có timeout (ví dụ Awaitility), không dùng sleep cố định. Kiểm tra **state đã commit và business invariant**, không chỉ mock method được gọi.

## 28. Observability của migration

| Metric | Ý nghĩa |
| --- | --- |
| migration_rows_read_total | Số record đã đọc |
| migration_rows_applied_total | Số record đã apply |
| migration_rows_skipped_total | Bản ghi trùng/cũ |
| migration_rows_failed_total | Lỗi chuyển đổi/ghi |
| migration_backfill_cursor | Tiến độ theo shard/cohort |
| migration_delta_lag_seconds | CDC/outbox lag |
| migration_reconcile_mismatches | Mismatch chưa giải quyết |
| migration_quarantine_size | Record lỗi cần xử lý |
| migration_legacy_write_attempts | Dấu hiệu writer cũ sau cutover |
| migration_target_p95 | Latency API/DB target |
| migration_source_db_load | Ảnh hưởng sản xuất tại nguồn |
| migration_target_db_load | Mức tải đích |

Các metric chỉ là ví dụ. Không gắn tenant_id có hàng triệu giá trị vào mọi time series; có thể phân theo shard/tier và drilldown qua logs/traces có quyền.

Alert khi mismatch tăng, CDC gap, lag vượt ngưỡng, target DB quá tải hoặc source vẫn nhận write sau fencing.

## 29. Bảo mật, privacy và vận hành

Di chuyển dữ liệu là hoạt động nhạy cảm:

- Migration worker dùng identity riêng với least privilege.
- TLS, database encryption và key management theo chính sách.
- Không ghi token, số điện thoại, địa chỉ hoặc PII vào log/debug không cần thiết.
- DLQ và quarantine được bảo vệ như dữ liệu production.
- Audit mọi thay đổi owner registry, quyền ghi và cutover.
- Giữ data residency, retention và quyền xóa theo policy.
- Tenant ID lấy từ danh tính đã xác thực; không tin header tùy ý.
- Checkpoint, mapping, backups và object copies có quyền truy cập chặt.
- Có runbook và người được phép pause/restart migration.

Nếu phát hiện dữ liệu tenant A bị gắn nhầm sang B, phải dừng và xử lý như security/data integrity incident, không chờ batch hoàn thành.

## 30. Runbook cutover

Một runbook thực thi được phải có mục tiêu, phạm vi tenant, người phụ trách, preconditions, thời gian, checkpoint, fencing, rollback boundary, hành động và bằng chứng.

    PREPARE
      Verify target schema and API.
      Record snapshot/CDC checkpoints.
      Reconcile data and approve cohort.
      Ensure backups and recovery options.

    CUTOVER
      Hold new writes in bounded path.
      Drain source transactions.
      Record final source checkpoint.
      Wait target catch-up.
      Verify business invariants.
      Fence source writers.
      Switch canonical owner routing.
      Release held writes to target.

    VERIFY
      Authorized test write/read on target.
      Order snapshot still correct.
      Legacy successful writes = zero.
      Monitor p95, errors, lag, mismatches.

    STABILIZE
      Expand cohort gradually.
      Preserve source read-only temporarily.
      Remove legacy contracts after sign-off.

Routing switch và DB fencing không tự atomic chỉ vì chạy trong cùng script; phải có protocol ownership chuyển giao phù hợp.

## 31. Bài tập thực hành

Nền tảng SaaS có Account Service quản lý 10 triệu địa chỉ của 50.000 tenants. Order Service query Account DB trực tiếp; Shipping dùng snapshot; Analytics dùng batch SQL. Mục tiêu chuyển hồ sơ và địa chỉ sang Profile Service mà không gián đoạn checkout.

**Yêu cầu:**

1. Vẽ bounded contexts mới và xác định owner từng tập dữ liệu.
2. Lập inventory toàn bộ direct readers/writers.
3. Thiết kế schema Profile DB và ID mapping.
4. Chọn CDC hoặc outbox; mô tả cách nối snapshot và delta không có gap.
5. Thiết kế backfill theo keyset, checkpoint sau commit.
6. Xử lý AddressUpdated v12 đến trước snapshot v11.
7. Xử lý delete v13 để snapshot v11 không làm sống lại record.
8. Phân biệt Profile canonical với Order snapshot và Analytics projection.
9. Thiết kế owner routing theo tenant và fencing writer cũ.
10. Đề xuất metrics và điều kiện chuyển READY → TARGET_OWNED.
11. Kiểm thử duplicate events, crash, malformed data và tenant isolation.
12. Giữ client cũ qua adapter nhưng không duy trì hai writers.
13. Mô tả rollback sau khi target đã nhận write.
14. Áp dụng privacy, audit, data residency và retention.
15. Nêu thời điểm an toàn để xóa bảng, quyền DB và API cũ.

**Hướng giải:** Account là canonical writer trong giai đoạn đầu, phát delta CDC/outbox; Profile được backfill idempotent với version guard; Order giữ snapshot bất biến; chuyển từng tenant sau reconciliation và fencing; adapter chuyển lệnh cũ tới Profile; chỉ contract nguồn khi mọi consumers đã được chuyển và có recovery plan.

## 32. Những sai lầm thường gặp

**“Copy đủ số hàng là đã chuyển service.”** Quyền sở hữu, API ghi, sự kiện và invariants chưa thay đổi.

**“Hai database ghi song song để dễ rollback.”** Dual-write thiếu atomicity dễ phân kỳ.

**“Dùng updated_at là đủ bắt delta.”** Không bảo đảm bắt delete, clock skew và mọi transaction.

**“Broker có thứ tự nên khỏi cần version.”** Retry/replay và topology có thể làm sự kiện tới không đúng thứ tự dự kiến.

**“Feature flag bật ngược là rollback được.”** Target writes có thể không tồn tại ở source cũ.

**“Chuyển API rồi xóa bảng cũ ngay.”** Batch jobs, client legacy và replay có thể vẫn phụ thuộc.

**“Một bảng phải thuộc một service riêng.”** Bounded context là ranh giới nghiệp vụ, không phải phép đếm bảng.

**“Mọi cross-service transaction cần Saga.”** Nhiều trường hợp một owner và read model là đủ.

**“Backfill càng nhanh càng tốt.”** Có thể làm nguồn production thiếu CPU/IO và gây outage.

**“Chỉ dữ liệu đang tồn tại mới quan trọng.”** Tombstone, history và audit quan trọng với integrity/privacy.

**“Tenant ID trong header là quyền truy cập.”** Tenant context phải được xác thực và kiểm tra authorization.

## 33. Checklist hoàn tất

- Bounded context và owner mới được nghiệp vụ chấp thuận?
- Canonical records, projections, snapshots và audit được phân biệt?
- Tất cả readers/writers/ETL được kiểm kê?
- Target schema/API/event contract tương thích qua rollout?
- Key mapping và tenant constraints rõ?
- Backfill có snapshot checkpoint, batch, idempotency và quarantine?
- Delta không có gap, có version/delete semantics và retention?
- Reconciliation theo key, value, version và invariant đạt tiêu chí?
- Các integration/failure tests chạy với engine thật?
- Cutover có drain, fencing và routing ổn định?
- Không còn source writers sau chuyển owner?
- Rollback boundary được mô tả đúng, không hứa hoàn tác dữ liệu bằng flag?
- SLO, lag, mismatch, source/target load được theo dõi?
- Privacy, audit, authorization và retention được bảo vệ?
- Contract legacy được loại bỏ chỉ khi mọi phụ thuộc đã hết?

---

**Điểm cốt lõi:** Di chuyển dữ liệu khi ranh giới nghiệp vụ thay đổi là **chuyển quyền sở hữu và bảo toàn ý nghĩa nghiệp vụ**, không chỉ copy byte. Cần hợp đồng rõ, snapshot/backfill và delta không có khoảng trống, idempotency/version/tombstone, reconciliation, single-writer cutover có fencing và kế hoạch rollback hoặc roll-forward thực tế. Kết quả chỉ thực sự thành công khi hệ thống mới giữ đúng invariants và phục vụ người dùng ổn định trong toàn bộ quá trình chuyển đổi.
