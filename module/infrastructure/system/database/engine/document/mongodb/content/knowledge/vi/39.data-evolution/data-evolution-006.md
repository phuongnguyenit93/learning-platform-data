# Chuyển từ dữ liệu quan hệ sang document theo mẫu truy cập trong MongoDB

Chuyển từ hệ quản trị quan hệ như PostgreSQL/MySQL sang MongoDB **không phải** đổi mỗi bảng thành một collection, mỗi hàng thành một document rồi giữ nguyên mọi JOIN. Làm như vậy thường chỉ mang mô hình truy cập cũ sang công nghệ mới, khiến ứng dụng phải xử lý nhiều truy vấn nhỏ mà không tận dụng ranh giới document.

Điểm xuất phát đúng là **mẫu truy cập (access pattern)**: người dùng cần đọc những dữ liệu nào cùng nhau, thao tác nào cần ghi nguyên tử, dữ liệu nào tăng trưởng không giới hạn, phần nào phải phản ánh trạng thái mới nhất, phần nào phải bảo toàn ảnh chụp lịch sử. Sau đó mới quyết định nhúng, tham chiếu, lưu snapshot hay tạo read model.

Bài học thuộc chương **Tiến hóa dữ liệu**, module **Database Engine Document MongoDB**, trình bày một cách tiếp cận thực tế để chuyển đổi mô hình, kèm ví dụ hệ thống đặt thuê xe, thiết kế index, xử lý nhất quán, backfill, CDC, kiểm chứng và cutover.

**Phạm vi an toàn:** SQL, mongosh và Java snippets là ví dụ cho môi trường thử nghiệm riêng. Không chạy lệnh migration, cập nhật hàng loạt hoặc đổi nguồn ghi trên production nếu chưa có change plan, backup, kế hoạch rollback và người phê duyệt.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Đọc relational schema theo góc nhìn API/read-write workloads.
2. Lập danh mục access patterns gồm filters, sort, cardinality, tần suất và yêu cầu nhất quán.
3. Chọn document boundary từ vòng đời và những gì thường được đọc/ghi cùng nhau.
4. Phân biệt embedding, referencing, snapshot và derived read models.
5. Tránh unbounded arrays, write amplification và giới hạn BSON document.
6. Chuyển một số SQL JOIN/GROUP BY thành MongoDB queries hoặc aggregation.
7. Thiết kế indexes theo access patterns và tenant isolation.
8. Phát hiện những invariant không được bảo vệ chỉ bằng single-document atomicity.
9. Map SQL identifiers, dates, numeric types, nulls và related rows sang BSON.
10. Thiết kế backfill + CDC có idempotency, ordering, reconciliation và rollback.
11. Lập kế hoạch tiến hóa schema bằng versioning và expand–migrate–contract.
12. Kiểm thử hiệu năng và hành vi nghiệp vụ trước và sau cutover.

## 2. Khác biệt giữa relational model và document model

RDBMS tập trung vào bảng, hàng, constraints và quan hệ qua foreign keys. Chuẩn hóa dữ liệu giúp tránh nhiều bản sao của một thông tin.

~~~text
customers ---- bookings ---- vehicles
                    |
                    +---- booking_addons
                    |
                    +---- payment_events
~~~

Khi cần trang chi tiết booking, SQL thường JOIN nhiều bảng.

MongoDB cho phép biểu diễn những thành phần **thường được truy cập cùng nhau** trong một document:

~~~text
bookings document
  |
  +-- booking ID, tenant, status
  +-- rental period
  +-- customer snapshot
  +-- vehicle snapshot
  +-- booked addons
  +-- agreed price
  +-- payment summary
~~~

Tuy nhiên, customer master, vehicle master và payment audit events vẫn có thể là các collections riêng.

### 2.1. Không có cuộc thi loại bỏ mọi JOIN

MongoDB có references và aggregation $lookup. Dùng khi đó là lựa chọn tốt cho correctness và workload. Mục đích là giảm complexity/round trips của **luồng phổ biến**, không phải đạt “0 JOIN”.

### 2.2. Không phải mọi bảng cần một collection

Các bảng join/line item có thể trở thành embedded arrays nếu bounded và cùng vòng đời. Ngược lại, một bảng lớn có thể được tách thành nhiều collections theo lifecycle, archival và query needs.

### 2.3. Một domain có thể có nhiều read models

Canonical booking data có thể ở bookings, còn dashboard của tenant có summary được materialize riêng. Cần định nghĩa rõ nguồn sự thật và cách đồng bộ.

## 3. Ví dụ relational schema ban đầu

Một hệ thống đặt thuê xe có schema rút gọn:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    display_name VARCHAR(200) NOT NULL
);

CREATE TABLE vehicles (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    plate VARCHAR(40) NOT NULL,
    category VARCHAR(40) NOT NULL,
    current_rate_minor BIGINT NOT NULL
);

CREATE TABLE bookings (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    customer_id BIGINT NOT NULL,
    vehicle_id BIGINT NOT NULL,
    start_at TIMESTAMP NOT NULL,
    end_at TIMESTAMP NOT NULL,
    status VARCHAR(40) NOT NULL,
    total_minor BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE booking_addons (
    id BIGINT PRIMARY KEY,
    booking_id BIGINT NOT NULL,
    addon_code VARCHAR(50) NOT NULL,
    quantity INT NOT NULL,
    unit_minor BIGINT NOT NULL
);

CREATE TABLE payment_events (
    id BIGINT PRIMARY KEY,
    booking_id BIGINT NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    provider_ref VARCHAR(128),
    event_type VARCHAR(40) NOT NULL,
    amount_minor BIGINT NOT NULL,
    happened_at TIMESTAMP NOT NULL
);
~~~

Đây là ví dụ, chưa thể hiện tất cả FKs/indexes/unique constraints thật.

### 3.1. Từ ERD chưa suy ra mô hình MongoDB được

Cần biết số add-ons tối đa mỗi booking, cách ứng dụng đọc booking details, mức biến động giá xe, tần suất thanh toán/refund, cách quản lý orphan references và yêu cầu audit.

### 3.2. Đọc schema để phát hiện invariants

- Booking phải thuộc tenant xác định.
- Customer/vehicle phải thuộc tenant được phép.
- start_at < end_at.
- Giá trị amount phải tính được và đúng kiểu số.
- Không được double-book xe theo quy tắc nghiệp vụ.
- Payment records phải đối chiếu được với bên thanh toán.

Foreign keys và transactions trong SQL có thể đang bảo vệ một số điều kiện. Khi sang MongoDB, phải chỉ ra ai/cơ chế nào bảo vệ từng invariant.

## 4. Lập access-pattern inventory trước khi thiết kế

Ví dụ:

| Pattern | Truy vấn hoặc thao tác | Tần suất | Cần dữ liệu | Đặc tính |
| --- | --- | --- | --- | --- |
| AP1 | GET booking detail | Rất cao | Booking, xe, khách, add-ons | By ID |
| AP2 | Customer booking history | Cao | Ngày, status, tiền | Filter/sort/page |
| AP3 | Tenant booking feed | Cao | Summary, trạng thái | Filter/sort/page |
| AP4 | Check vehicle availability | Cao | Khoảng thuê, các holds | Race-sensitive |
| AP5 | Change booking status | Cao | State/version | Conditional write |
| AP6 | Update customer profile | Trung bình | Current customer | Independent write |
| AP7 | Payment event audit | Trung bình | Event history | Unbounded |
| AP8 | Revenue report | Trung bình | Amount by day/status | Aggregate |
| AP9 | Update vehicle list price | Thấp | Current rate | Master data |
| AP10 | Investigate refund/dispute | Thấp | Payment lifecycle | Strong audit |

Các mức tần suất là minh họa. Trong dự án thực tế hãy đo bằng logs/tracing/DB metrics.

### 4.1. Mẫu mô tả một access pattern

~~~yaml
id: AP1
name: "Booking detail"
input:
  tenantId: "verified auth context"
  bookingId: "path parameter"
output:
  - dates
  - status
  - vehicle snapshot
  - customer snapshot
  - selected addons
  - agreed total
consistency: "current booking state"
cardinality: 1
readFrequency: high
writeFrequency: medium
latencyObjective: "per API SLO"
~~~

### 4.2. Ghi cả write patterns

Nếu chỉ tối ưu reads, bạn dễ nhúng quá nhiều master data, khiến mỗi cập nhật profile phải sửa hàng nghìn bookings. Cần biết mỗi field có owner nào, thời điểm nào, tần suất bao nhiêu.

### 4.3. Truy vấn hiếm nhưng quan trọng

Audit/hoàn tiền tuân thủ có thể ít dùng nhưng có yêu cầu dữ liệu và retention nghiêm ngặt. Đừng loại chúng khỏi mô hình.

## 5. Phân tích một SQL JOIN nóng

Trang booking details có thể chạy:

~~~sql
SELECT b.id, b.tenant_id, b.status,
       b.start_at, b.end_at, b.total_minor,
       c.display_name, v.plate, v.category
FROM bookings b
JOIN customers c ON c.id = b.customer_id
JOIN vehicles v ON v.id = b.vehicle_id
WHERE b.tenant_id = :tenantId
  AND b.id = :bookingId;
~~~

Sau đó service tải danh sách booking_addons.

Nếu API dùng các trường này ở hầu hết requests, có lý do đưa **những snapshot hợp đồng và bounded add-ons** vào booking document.

### 5.1. Đừng nhúng toàn bộ customer

Profile có thể chứa email, preferences, addresses và sensitive details không cần cho booking detail. Sao chép chỉ fields cần thiết cho hợp đồng/lịch sử.

### 5.2. Đừng nhúng toàn bộ vehicle

Xe có thể có telemetry, lịch bảo trì và hàng nghìn booking references. Booking chỉ cần vehicleId + thông tin đã chốt lúc đặt.

### 5.3. Dữ liệu lịch sử và dữ liệu hiện tại

Tên hiển thị hoặc bảng giá **tại thời điểm đặt** có thể cần giữ nguyên. Nếu giao diện yêu cầu trạng thái master hiện tại, truy vấn reference thêm hoặc dùng derived field có synchronization contract.

## 6. Booking document đề xuất

~~~javascript
{
  _id: "tenant-a:booking:1001",
  tenantId: "tenant-a",
  sourceBookingId: NumberLong(1001),
  bookingNumber: "BK-2026-1001",

  customerId: "tenant-a:customer:42",
  customerSnapshot: {
    displayName: "Khách hàng Mẫu"
  },

  vehicleId: "tenant-a:vehicle:7",
  vehicleSnapshot: {
    category: "sedan",
    plate: "TEST-123",
    dailyRateMinor: NumberLong(700000)
  },

  period: {
    startAt: ISODate("2026-11-18T02:00:00Z"),
    endAt: ISODate("2026-11-20T02:00:00Z")
  },

  addons: [
    {
      code: "baby-seat",
      quantity: 1,
      unitMinor: NumberLong(100000)
    }
  ],

  amount: {
    subtotalMinor: NumberLong(1400000),
    addonMinor: NumberLong(100000),
    totalMinor: NumberLong(1500000),
    currency: "VND"
  },

  status: "CONFIRMED",
  paymentSummary: {
    status: "AUTHORIZED"
  },

  version: 1,
  schemaVersion: 2,
  createdAt: ISODate("2026-11-14T03:00:00Z"),
  updatedAt: ISODate("2026-11-14T03:00:00Z")
}
~~~

### 6.1. Những fields canonical

- booking status, dates, addons và agreed amount thuộc booking.
- Current customer profile thuộc customers.
- Current vehicle attributes/rate thuộc vehicles.
- Verified payment events thuộc paymentEvents hoặc payment ledger.
- paymentSummary là read model/derived field nếu được định nghĩa như vậy.

### 6.2. Snapshot có chủ đích

Giá niêm yết xe đổi vào tháng sau không làm đổi giá đã cam kết ở booking cũ. Giữ vehicleSnapshot.dailyRateMinor là đúng nếu đó là quy tắc nghiệp vụ.

### 6.3. MongoDB không tự enforce cross-collection foreign keys

Một booking có customerId sang tenant khác có thể được lưu nếu application/transaction/workflow không ngăn. Phải thiết kế reference validation.

## 7. Nhúng (embedding): khi nào có lợi?

Ưu tiên cân nhắc nhúng khi:

- Dữ liệu thường xuyên được đọc cùng parent.
- Số phần tử nhỏ và có giới hạn thật.
- Child gắn với vòng đời parent.
- Cập nhật child và parent cần single-document atomicity.
- Child ít khi được query độc lập.
- Kích thước document không tăng vô hạn.

Ví dụ addons bounded trong booking.

~~~javascript
{
  _id: "bk-1001",
  addons: [
    { code: "baby-seat", quantity: 1 },
    { code: "insurance-plus", quantity: 1 }
  ]
}
~~~

### 7.1. Atomic update ở mức document

Một updateOne có thể đổi status và amount của cùng booking trong một single-document atomic write.

### 7.2. Nhúng làm giảm round trips

AP1 không cần hỏi collection bookingAddons riêng ở lần đọc phổ biến.

### 7.3. Nhúng có trade-off

Mỗi update có thể làm document lớn hơn, ảnh hưởng index/multikey và write contention. Nếu add-ons có lifecycle và quyền truy cập riêng, reference có thể tốt hơn.

## 8. Tham chiếu (referencing): khi nào tốt hơn?

Ưu tiên reference khi:

- Dữ liệu tăng không giới hạn.
- Được truy vấn/phân trang riêng.
- Được cập nhật thường xuyên và có nhiều parent trỏ tới.
- Có retention và security riêng.
- Cần một bản canonical current state.
- Fan-out updates khi sao chép sẽ quá lớn.

Ví dụ:

~~~javascript
// customers
{
  _id: "tenant-a:customer:42",
  tenantId: "tenant-a",
  displayName: "Tên hiện tại"
}

// bookings
{
  _id: "tenant-a:booking:1001",
  tenantId: "tenant-a",
  customerId: "tenant-a:customer:42",
  customerSnapshot: {
    displayName: "Tên khi đặt"
  }
}
~~~

### 8.1. Reference và snapshot tồn tại đồng thời

Hai fields trả lời câu hỏi khác nhau: current customer vs lịch sử booking. Không nhất thiết là dữ liệu thừa đáng xóa.

### 8.2. Không đồng bộ snapshot bất biến bằng master update

Nếu khách đổi tên, không tự đổi tên trong hàng nghìn hợp đồng lịch sử. Chọn quy định riêng nếu privacy/anonymization yêu cầu xử lý dữ liệu cá nhân.

### 8.3. Tham chiếu có thể cần $lookup

Đó là chi phí chấp nhận được khi yêu cầu current profile, dữ liệu lớn hoặc cập nhật độc lập.

## 9. Cardinality quyết định giới hạn mô hình

| Quan hệ | Hướng cân nhắc |
| --- | --- |
| 1:1, cùng lifecycle | Embed thường thuận tiện |
| 1:few, bounded | Embed nếu thường đọc/ghi cùng |
| 1:many, có upper bound | Xem kích thước/frequency |
| 1:many, unbounded | Reference hoặc child collection |
| Many:many | Bounded IDs, association collection hoặc hybrid |

### 9.1. Average nhỏ chưa chứng minh bounded

Average hai bookings/customer không loại trừ một customer có hàng triệu bookings. Nếu array có thể tăng không giới hạn, không đặt toàn bộ trong customer document.

### 9.2. Giới hạn 16 MiB

Một BSON document thông thường tối đa 16 MiB. Một document chứa toàn bộ lịch sử payment, logs hoặc telemetry có thể vượt giới hạn khi hệ thống phát triển.

### 9.3. Trường hợp dữ liệu lớn

File attachments thường dùng GridFS hoặc object storage, chỉ lưu metadata/reference trong business document nếu phù hợp.

## 10. Tách paymentEvents ra khỏi booking

Relational payment_events có 1:N với booking. Có thể tạo collection riêng:

~~~javascript
{
  _id: "payevt-901",
  tenantId: "tenant-a",
  bookingId: "tenant-a:booking:1001",
  providerRef: "sandbox-ref-901",
  eventType: "AUTHORIZED",
  amountMinor: NumberLong(1500000),
  happenedAt: ISODate("2026-11-14T04:00:00Z")
}
~~~

### 10.1. Vì sao không nhúng mọi events?

Một booking có thể phát sinh nhiều attempts, refunds, webhook retries, disputes và manual adjustments. Event history có thể tăng và có retention/audit độc lập.

### 10.2. Summary vẫn có thể nhúng

booking.paymentSummary.status dùng cho UI nhanh, nhưng không được tự coi là ledger nếu payment events/provider là nguồn có thẩm quyền.

### 10.3. Đồng bộ summary

Khi payment event được xác minh/ghi, workflow cập nhật summary qua outbox/consumer với idempotency và reconciliation. Chấp nhận eventual consistency nếu business cho phép.

### 10.4. Truy vấn payment audit

~~~javascript
db.paymentEvents.find({
  tenantId: "tenant-a",
  bookingId: "tenant-a:booking:1001"
}).sort({
  happenedAt: -1,
  _id: -1
});
~~~

## 11. Many-to-many không nhất thiết cần một collection JOIN y hệt

Ví dụ vehicles ↔ features.

Relational có thể dùng bảng vehicle_features. MongoDB:

~~~javascript
{
  _id: "tenant-a:vehicle:7",
  tenantId: "tenant-a",
  featureCodes: [
    "gps",
    "child-seat",
    "insurance-eligible"
  ]
}
~~~

### 11.1. Bounded codes

Nếu số featureCodes nhỏ, thường đọc cùng vehicle và ít metadata, nhúng codes hợp lý.

### 11.2. Master metadata

Tên/giá/mô tả feature thay thường xuyên có thể giữ ở features collection, không sao chép toàn bộ vào mọi xe.

### 11.3. Association có business lifecycle riêng

Nếu quan hệ có effective dates, pricing rules, history hoặc trạng thái riêng, collection liên kết vẫn có thể là lựa chọn tốt.

## 12. Một mô hình hybrid theo access patterns

~~~text
customers:
  current profile

vehicles:
  current attributes, current rates

bookings:
  main booking state
  customer/vehicle snapshot
  bounded addons
  agreed amount

paymentEvents:
  separate append-only history

bookingStatusEvents:
  optional audit timeline

availabilityAllocations:
  overlap/concurrency-specific model

dailyRevenue:
  optional derived aggregate
~~~

### 12.1. Mỗi collection có lý do

Không tạo collections vì chúng từng là SQL tables; tạo vì query/update/lifecycle/retention của chúng cần sự độc lập.

### 12.2. Nguồn sự thật phải rõ

paymentSummary, dailyRevenue và search view có thể là derived. Nếu cho phép mọi nơi sửa chúng trực tiếp, rất khó reconciliation.

## 13. Atomicity và document boundary

MongoDB single-document writes là atomic ở cấp document.

~~~javascript
db.bookings.updateOne(
  {
    _id: "tenant-a:booking:1001",
    tenantId: "tenant-a",
    status: "PENDING"
  },
  {
    $set: { status: "CONFIRMED" },
    $inc: { version: 1 },
    $currentDate: { updatedAt: true }
  }
);
~~~

### 13.1. Conditional update bảo vệ state transition

Nếu request CANCEL đã đổi status trước, request CONFIRM với filter PENDING không match. Không đọc status rồi set vô điều kiện.

### 13.2. Không mặc định nhiều documents atomic

Nếu cùng lúc phải tạo booking, ghi payment event và cập nhật availability, một updateOne không giải quyết tất cả.

### 13.3. Transaction khi phù hợp

Multi-document transaction trên topology được hỗ trợ có thể giúp một tập writes commit cùng nhau. Tuy nhiên, thiết kế business workflow, idempotency và xử lý external effects vẫn cần độc lập.

### 13.4. Không nhúng mọi business records chỉ để tránh transaction

Nhúng customer, vehicle và toàn bộ payment histories vào một booking gây dữ liệu không giới hạn, contention và duplicated master data.

## 14. Availability và khoảng thời gian bị chồng lấn

Một xe không nên có hai booking đang hiệu lực với khoảng thuê chồng lấn theo business rule.

Hai khoảng giao nhau khi:

~~~text
existing.startAt < requested.endAt
AND
existing.endAt > requested.startAt
~~~

Ví dụ filter overlap:

~~~javascript
db.bookings.find({
  tenantId: "tenant-a",
  vehicleId: "tenant-a:vehicle:7",
  status: { $in: ["HELD", "CONFIRMED"] },
  "period.startAt": {
    $lt: ISODate("2026-11-22T00:00:00Z")
  },
  "period.endAt": {
    $gt: ISODate("2026-11-19T00:00:00Z")
  }
});
~~~

### 14.1. Query-then-insert có race

Hai requests có thể cùng đọc “không có overlap” rồi cùng insert booking. Unique index trên vehicleId/startAt/endAt **không chặn mọi khoảng chồng lấn** vì start/end có thể khác nhau.

### 14.2. Hướng giải quyết

- Slot allocation với khóa unique cho từng đơn vị thời gian.
- Một shared allocation/availability document làm điểm contention.
- Transaction kết hợp write trên contention record.
- Reservation holds, expiry và conflict resolution có chủ đích.

### 14.3. Không coi transaction đơn thuần là thuốc chữa

Nếu hai transactions chỉ cùng query **sự vắng mặt** của record rồi insert các documents khác nhau, vẫn phải thiết kế contention/uniqueness phù hợp để ngăn write skew.

## 15. Chuyển SQL JOIN sang MongoDB find khi đã có snapshot

AP1 đọc booking:

~~~javascript
db.bookings.findOne({
  _id: "tenant-a:booking:1001",
  tenantId: "tenant-a"
});
~~~

Nếu document chứa status, periods, snapshots, addons và amount, nhiều API detail không cần JOIN tại thời điểm đọc.

### 15.1. Lợi ích

Giảm số round trips và số collections tham gia vào hot path.

### 15.2. Chi phí

Dữ liệu snapshot tăng storage và cần định nghĩa retention/PII policy. Điều này là trade-off, không phải miễn phí.

### 15.3. API cần profile hiện tại

Khi business thực sự yêu cầu live customer, có thể truy vấn customers riêng hoặc $lookup. Không dùng customerSnapshot của thời điểm đặt thay cho current data.

## 16. Sử dụng $lookup khi cần dữ liệu hiện hành

Ví dụ lấy customer hiện tại theo tenant:

~~~javascript
db.bookings.aggregate([
  {
    $match: {
      tenantId: "tenant-a",
      _id: "tenant-a:booking:1001"
    }
  },
  {
    $lookup: {
      from: "customers",
      let: {
        customerKey: "$customerId",
        tenantKey: "$tenantId"
      },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$_id", "$$customerKey"] },
                { $eq: ["$tenantId", "$$tenantKey"] }
              ]
            }
          }
        },
        {
          $project: {
            _id: 0,
            displayName: 1
          }
        }
      ],
      as: "currentCustomer"
    }
  }
]);
~~~

### 16.1. Tenant-aware lookup

Không join chỉ trên business ID nếu ID có thể trùng giữa tenants. Quyền truy cập phải được bảo vệ ở service/repository.

### 16.2. $lookup trả mảng

Với zero/one matching record, kết quả vẫn ở array. Dùng $first/$unwind hoặc mapper phù hợp nếu muốn object và xử lý trường hợp thiếu.

### 16.3. Query plan

$lookup qua dataset lớn không index có thể tốn chi phí. Dùng explain, đo latency, cân nhắc snapshot hoặc derived read model cho hot path.

## 17. Customer booking history và pagination

Truy vấn theo tenant + customer và sort:

~~~javascript
db.bookings.find(
  {
    tenantId: "tenant-a",
    customerId: "tenant-a:customer:42"
  },
  {
    _id: 1,
    status: 1,
    period: 1,
    amount: 1,
    createdAt: 1
  }
).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
~~~

### 17.1. Vì sao có _id tie-breaker?

Nhiều bookings có thể cùng createdAt. Một sort chỉ theo timestamp không đủ ổn định cho pagination.

### 17.2. Skip lớn

Phân trang sâu bằng skip có thể phải đi qua nhiều records. Dùng keyset với lastCreatedAt và lastId khi phù hợp.

### 17.3. Keyset condition

~~~javascript
db.bookings.find({
  tenantId: "tenant-a",
  customerId: "tenant-a:customer:42",
  $or: [
    {
      createdAt: {
        $lt: ISODate("2026-11-12T10:00:00Z")
      }
    },
    {
      createdAt: ISODate("2026-11-12T10:00:00Z"),
      _id: {
        $lt: "tenant-a:booking:1001"
      }
    }
  ]
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
~~~

Keyset không tự tạo snapshot bất biến nếu writes đang diễn ra; cần xác định read semantics theo use case.

## 18. Chuyển SQL GROUP BY sang aggregation

Relational:

~~~sql
SELECT tenant_id, status,
       COUNT(*) AS cnt,
       SUM(total_minor) AS amount
FROM bookings
GROUP BY tenant_id, status;
~~~

MongoDB:

~~~javascript
db.bookings.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        status: "$status"
      },
      count: { $sum: 1 },
      amountMinor: {
        $sum: "$amount.totalMinor"
      }
    }
  },
  {
    $sort: {
      "_id.tenantId": 1,
      "_id.status": 1
    }
  }
]);
~~~

### 18.1. Báo cáo tenant phải lọc tenant

Đây là ví dụ cross-tenant aggregate cho backend đã được ủy quyền. Tenant-facing API cần $match tenantId theo authenticated context.

### 18.2. Booking revenue khác payment received

Booking.amount là tổng đã chốt, không nhất thiết là tiền thực thu. Accounting report cần nguồn payment ledger/finance phù hợp.

### 18.3. Derived analytics collection

Nếu aggregation chạy liên tục trên dữ liệu rất lớn, cân nhắc daily summaries với event replay/idempotency và reconciliation.

## 19. Indexes theo truy vấn, không theo danh sách fields

Các candidate indexes:

~~~javascript
// Customer history
db.bookings.createIndex({
  tenantId: 1,
  customerId: 1,
  createdAt: -1,
  _id: -1
});

// Tenant status feed
db.bookings.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
});

// Payment audit
db.paymentEvents.createIndex({
  tenantId: 1,
  bookingId: 1,
  happenedAt: -1,
  _id: -1
});

// Business booking number
db.bookings.createIndex(
  {
    tenantId: 1,
    bookingNumber: 1
  },
  { unique: true }
);
~~~

### 19.1. Index trên _id có sẵn

MongoDB tạo unique index cho _id của collection thông thường. Query detail theo _id đã có access path, nhưng tenant filter vẫn cần theo authorization.

### 19.2. Đừng copy mọi index từ SQL

SQL indexes phục vụ normalized joins và table patterns; MongoDB indexes phải phục vụ document queries mới.

### 19.3. Mỗi index có chi phí

Index tăng disk/memory và write amplification. Dùng explain, nReturned, docsExamined, latency, selectivity để chọn.

### 19.4. Đặt tenant trong compound index khi cần

Tenant-scoped filters thường hưởng lợi từ index có tenantId, tùy query shape và cardinality.

## 20. Identity và khóa chính từ SQL sang MongoDB

SQL BIGINT id có thể unique toàn hệ thống hoặc chỉ trong tenant/partition.

MongoDB `_id` unique trong collection, vì thế cần một ánh xạ ổn định.

Ví dụ:

~~~text
tenant-a / booking SQL id 1001
    -> MongoDB _id "tenant-a:booking:1001"

tenant-b / booking SQL id 1001
    -> MongoDB _id "tenant-b:booking:1001"
~~~

### 20.1. Không dùng ObjectId ngẫu nhiên trong mỗi retry migration

Nếu cùng source row map thành `_id` mới mỗi lần, re-run tạo duplicates. Stable IDs hoặc một mapping table bền vững là bắt buộc cho idempotency.

### 20.2. Giữ source ID làm metadata

Có thể giữ sourceBookingId và sourceSystem để trace/reconcile. Nhưng không nên để field trace quyết định tenant authorization.

### 20.3. Business keys và uniqueness

bookingNumber có thể cần unique theo tenant. Dùng compound unique index và kiểm tra dữ liệu cũ trước khi tạo.

### 20.4. Sharded collection có ràng buộc unique

Khi sharding, các unique index và shard key có rules riêng theo phiên bản. Đừng mặc định index áp được y nguyên lên mọi sharded topology.

## 21. Mapping SQL types sang BSON

| SQL | BSON/Java thường chọn | Lưu ý |
| --- | --- | --- |
| BIGINT | Int64 / Java long | Giữ range và sign |
| INT | Int32 / int | Không trộn với string |
| DECIMAL | Decimal128 hoặc integer minor units | Precision/rounding |
| TIMESTAMP | BSON Date / Instant mapping | Timezone |
| VARCHAR | String | Collation, normalization |
| BOOLEAN | BSON Boolean | Không lưu "true" string |
| NULL | null hoặc missing theo contract | Query semantics khác |
| BLOB | Binary/GridFS/object ref | 16 MiB và lifecycle |
| JOIN table | Embedded array hoặc collection | Access pattern và cardinality |

### 21.1. SQL TIMESTAMP không luôn UTC

Một cột không có timezone có thể đã được diễn giải theo timezone ứng dụng. Cần xác định nguồn trước khi chuyển thành BSON Date.

### 21.2. Không chuyển tiền sang double tùy tiện

Money precision nên được bảo vệ bằng Decimal128 hoặc integer minor unit với scale/currency rules cụ thể.

### 21.3. NULL và missing

Trong MongoDB, field null và field missing có semantics truy vấn khác ở nhiều operators. Migration cần quyết định giữ explicit null hay bỏ field.

### 21.4. Document size

Trước khi nhúng dữ liệu con, tính worst-case size, không chỉ average.

## 22. Schema validation cho document mới

Một validator minh họa:

~~~javascript
db.createCollection("bookings", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "tenantId",
        "customerId",
        "vehicleId",
        "period",
        "status",
        "amount"
      ],
      properties: {
        tenantId: { bsonType: "string" },
        customerId: { bsonType: "string" },
        vehicleId: { bsonType: "string" },
        status: {
          enum: [
            "PENDING",
            "HELD",
            "CONFIRMED",
            "CANCELLED",
            "COMPLETED"
          ]
        },
        period: {
          bsonType: "object",
          required: [
            "startAt",
            "endAt"
          ],
          properties: {
            startAt: { bsonType: "date" },
            endAt: { bsonType: "date" }
          }
        },
        schemaVersion: { bsonType: "int" }
      }
    }
  }
});
~~~

### 22.1. Validator không thay foreign key

Cross-collection references, amount calculation và interval overlap cần application/transaction/validation workflow khác.

### 22.2. Không enforce schema chặt trong một bước trên dữ liệu legacy

Có thể cần expand/migrate/contract để không làm old documents/old writers lỗi đột ngột.

### 22.3. Schema rõ là lợi ích

MongoDB không bắt buộc mọi document có field giống nhau, nhưng team phải giữ contract về required fields, types, versions và nullable states.

## 23. Schema evolution: expand–migrate–contract

Giả sử v1:

~~~javascript
{
  _id: "bk-1",
  totalMinor: NumberLong(1200000),
  schemaVersion: 1
}
~~~

V2:

~~~javascript
{
  _id: "bk-1",
  amount: {
    totalMinor: NumberLong(1200000),
    currency: "VND"
  },
  schemaVersion: 2
}
~~~

Quy trình:

1. Reader hỗ trợ cả v1 và v2.
2. Writer bắt đầu tạo v2.
3. Background migration chuyển old documents.
4. Kiểm tra counts và fields.
5. Khi clients cũ được loại bỏ, bỏ legacy reads/writes.
6. Siết validation/schema contract sau khi dữ liệu được chuẩn hóa.

### 23.1. Idempotent migration

Đặt giá trị từ source bằng $set hoặc deterministic transform; không dùng $inc nếu re-run có thể cộng tiền hai lần.

### 23.2. Có thể cần dual fields trong giai đoạn chuyển tiếp

Nếu old app đọc totalMinor ở root, có thể cần giai đoạn tương thích có giới hạn thời gian, không xóa field ngay.

### 23.3. Không dùng schemaVersion thay business version

schemaVersion mô tả shape, còn version cho optimistic concurrency/state transition có ý nghĩa khác.

## 24. Từ relational schema thành mapping specification

Trước ETL, lập bảng rõ nguồn và đích:

| Nguồn SQL | Trường đích MongoDB | Biến đổi |
| --- | --- | --- |
| bookings.id + tenant_id | bookings._id | Stable composite string |
| bookings.tenant_id | tenantId | String |
| bookings.customer_id | customerId | Stable mapped reference |
| customers.display_name | customerSnapshot.displayName | Snapshot policy |
| bookings.vehicle_id | vehicleId | Stable mapped reference |
| vehicles.category | vehicleSnapshot.category | Snapshot policy |
| booking_addons rows | addons array | Group + bounded |
| bookings.total_minor | amount.totalMinor | Int64 |
| bookings.status | status | Valid enum |
| bookings.created_at | createdAt | UTC BSON Date |
| payment_events rows | paymentEvents collection | Separate documents |
| n/a | schemaVersion | Target version |

### 24.1. Historical snapshots có thể thiếu ở SQL source

Nếu RDBMS chỉ giữ current vehicle rate, không thể tái tạo contracted rate lúc booking một cách đáng tin nếu không có archived rates/order amounts. Phải xác định policy và ghi data-quality caveat.

### 24.2. Không lặng lẽ mất fields

Mapping cần phân loại: retained, transformed, intentionally dropped, deferred hoặc externally stored. Có owner sign-off.

### 24.3. Chuyển references cần nhất quán

Nếu booking.customerId map sang string key nhưng customers._id giữ long, joins sẽ fail. Mapping phải thống nhất toàn domain.

## 25. Data profiling trước migration

Đo:

- Counts theo từng table/tenant/status/thời gian.
- Foreign-key orphans.
- Duplicate business keys.
- Missing/null/invalid enum values.
- Max và percentile add-ons/booking.
- Max events/booking.
- Money precision và outliers.
- Timestamp range, timezone anomalies.
- Largest text/blob fields.
- Soft-deleted records và retention policies.
- Existing schema/data corruption.

### 25.1. Relational data thực tế có thể không đúng ERD

Legacy migrations hoặc disabled constraints có thể tạo orphan records. Không tự giả định mọi FK luôn hợp lệ.

### 25.2. Quarantine bad rows

Nếu transform lỗi, ghi source IDs, lý do và corrective action vào dead-letter/quarantine. Không âm thầm bỏ rồi báo SUCCESS.

### 25.3. Baseline phục vụ reconciliation

Counts/totals/invariants theo một watermark làm cơ sở so với MongoDB target.

## 26. Offline migration

Quy trình đơn giản:

~~~text
Block or stop source writes
        |
        v
Export consistent source snapshot
        |
        v
Transform + load MongoDB
        |
        v
Reconcile and smoke test
        |
        v
Switch application
~~~

### 26.1. Ưu điểm

Ít vấn đề ordering giữa backfill và live updates; dễ xác định recovery point.

### 26.2. Nhược điểm

Downtime lớn nếu data volume lớn hoặc transform/index build lâu. Không phù hợp với SLO yêu cầu thời gian dừng ngắn.

### 26.3. Không hứa chỉ cần dump/import

Một migration gồm cả model, indexes, validation, application behavior và external integrations.

## 27. Online migration: backfill kết hợp CDC

~~~text
SQL source of truth
   |
   +---- Consistent snapshot at watermark T0
   |           |
   |           v
   |        Backfill target
   |
   +---- Change Data Capture (after T0)
               |
               v
       Ordered/idempotent apply
               |
               v
            MongoDB
               |
               v
       Reconcile / shadow reads
               |
               v
             Cutover
~~~

### 27.1. Source of truth trước cutover

SQL vẫn canonical. MongoDB target là bản đang được xây dựng và đối chiếu.

### 27.2. CDC cần capture deletes

Một SQL DELETE sau snapshot cần được map thành tombstone/hard delete/soft delete theo business policy, không bỏ qua khiến target có ghost records.

### 27.3. Events có thể phát lại

CDC thường cần idempotency vì duplicate/retry/rebalance. Đừng thiết kế dựa trên giả định delivery exactly once ở mọi tầng.

## 28. Backfill theo batch và checkpoint

Pseudo SQL:

~~~sql
SELECT id, tenant_id, customer_id,
       vehicle_id, status, total_minor,
       created_at
FROM bookings
WHERE id > :lastId
ORDER BY id
LIMIT :batchSize;
~~~

### 28.1. Keyset thay OFFSET lớn

OFFSET lớn có thể tốn tài nguyên và nhạy cảm với concurrent inserts. Cursor/keyset theo stable unique key giúp resume.

### 28.2. Composite source key

Nếu id chỉ unique trong tenant, cần composite checkpoint chứ không chỉ lastId.

### 28.3. N+1 SQL queries

Không truy vấn customer, vehicle, addons riêng lẻ cho mỗi booking nếu có hàng triệu rows. Batch joins/prefetch, stream và giới hạn memory.

### 28.4. Checkpoint chỉ ghi sau confirmed writes

Nếu đánh dấu batch xong trước khi target ghi thành công, crash có thể làm mất một đoạn dữ liệu.

### 28.5. Throttle

Backfill không nên làm SQL/MongoDB production nghẽn CPU/IOPS. Theo dõi throughput, queue lag, resource usage và có cơ chế pause/resume.

## 29. Deterministic và idempotent target writes

Một record SQL phải luôn map về cùng MongoDB ID:

~~~javascript
db.bookings.replaceOne(
  { _id: "tenant-a:booking:1001" },
  {
    _id: "tenant-a:booking:1001",
    tenantId: "tenant-a",
    sourceBookingId: NumberLong(1001),
    status: "PENDING",
    schemaVersion: 2
  },
  { upsert: true }
);
~~~

### 29.1. Phạm vi an toàn của replaceOne

Ví dụ chỉ phù hợp khi target chưa có newer writes từ CDC/ứng dụng hoặc có ordering policy bảo đảm freshness.

### 29.2. Backfill ghi đè CDC là bug lớn

Nếu CDC đã ghi CONFIRMED nhưng một batch backfill tới muộn ghi PENDING, target bị **regress**. Phải ngăn bằng snapshot barrier, sequencing hoặc monotonic source version.

### 29.3. Conditional upsert khó hơn vẻ ngoài

Upsert với filter `_id` và `sourceVersion < incoming` có thể cố insert trùng `_id` khi target đang có version mới hơn. Cần chiến lược insert/update rõ và xử lý conflict, không nghĩ chỉ thêm version filter là đủ.

### 29.4. Idempotency không đồng nghĩa không cần auditing

Job cần log source IDs, changed/unchanged counts và conflicts để điều tra.

## 30. CDC ordering và duplicate events

~~~text
Source transaction committed
      |
      v
SQL log / connector
      |
      v
Event keyed by booking ID
      |
      v
Transform
      |
      v
Apply only when appropriate source sequence
      |
      v
MongoDB target
~~~

### 30.1. Per-entity ordering

Nếu events status=PENDING → CONFIRMED → CANCELLED tới sai thứ tự, target có thể hiện sai state. Thiết kế ordering/watermark rõ theo source log semantics.

### 30.2. App timestamp không luôn là thứ tự chuẩn

createdAt/updatedAt có thể trùng hoặc lệch clock. Source log sequence, row version hoặc transaction ordering thường đáng tin hơn khi được hỗ trợ.

### 30.3. Cross-table changes

Một transaction SQL có thể đổi booking và addons. Nếu CDC xử lý hai tables riêng, cần dựng target document từ một trạng thái nhất quán hoặc có cách reconcile sau khi cả hai changes đã được áp dụng.

### 30.4. Payment event append

Event IDs ổn định và unique index giúp bỏ duplicates do retry. Nhưng business side effects ngoài database vẫn cần idempotency.

## 31. Dual-write không tự atomic

Một service ghi hai stores:

~~~text
Write SQL succeeds
Write MongoDB fails
~~~

hoặc:

~~~text
Write MongoDB succeeds
Write SQL fails
~~~

### 31.1. Try/catch không giải quyết distributed commit

Một local transaction ở SQL không thể rollback write đã commit ở MongoDB và ngược lại.

### 31.2. Outbox pattern

Một hướng phổ biến: lưu business change và outbox row trong cùng SQL transaction, sau đó background consumer đẩy thay đổi sang MongoDB với retry/dedup.

### 31.3. Không có hai authoritative writers

Trước cutover, SQL authoritative. Sau cutover, MongoDB authoritative theo kế hoạch. Tránh cả hai cùng nhận independent writes không có reconciliation.

## 32. Shadow reads trước cutover

~~~text
Client
  |
  v
Application
  |
  +--> SQL authoritative query ---> response to client
  |
  +--> MongoDB shadow query ------> compare / log diff
~~~

### 32.1. Không phản hồi shadow results khi chưa tin cậy

Ban đầu chỉ dùng để đối chiếu, không ảnh hưởng user-facing logic.

### 32.2. Canonicalize trước khi so

Dates, numeric types, field order, null/missing và derived fields có thể khác biểu diễn. So các business fields có contract.

### 32.3. Sampling có chủ đích

Bao phủ tenants, statuses, dates, large bookings, cancelled/refunded, missing references. Đừng chỉ test happy path.

### 32.4. Shadow load

Đọc thêm từ MongoDB làm tăng tải. Có throttling/sampling, theo dõi p95 và resource impact.

## 33. Reconciliation: số lượng chưa đủ

| Kiểm tra | Lỗi có thể phát hiện |
| --- | --- |
| Count tổng | Thiếu/trùng records |
| Count theo tenant/status | Lệch cục bộ |
| Sum amount theo ngày/tenant | Sai tiền |
| Deep sample compare | Snapshot/addons sai |
| Duplicate business keys | ID mapping lỗi |
| Orphan references | Thiếu master |
| Schema validator failures | Sai BSON types |
| CDC watermark/lag | Target chưa bắt kịp |
| API shadow diff | Behavior mismatch |
| Index/query plan | Sẵn sàng performance |

### 33.1. So cùng recovery point

SQL tại T2 không được so trực tiếp với MongoDB mới backfill tới T1 mà kết luận sai. Đồng bộ watermark hoặc diễn giải CDC events rõ.

### 33.2. Canonical hash

Nếu dùng checksums, thống nhất record ordering, BSON type/date, Decimal128, Unicode normalization và những fields intentionally derived.

### 33.3. Không log raw PII

Báo cáo nên lưu counts, masked IDs và sanitized diffs. Môi trường thử vẫn phải tôn trọng privacy policy.

## 34. MongoDB aggregation đối chiếu

~~~javascript
db.bookings.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        status: "$status"
      },
      count: {
        $sum: 1
      },
      amountMinor: {
        $sum: "$amount.totalMinor"
      }
    }
  },
  {
    $sort: {
      "_id.tenantId": 1,
      "_id.status": 1
    }
  }
]);
~~~

### 34.1. So count và sum

Hai groups có thể cùng số bookings nhưng amount khác. Luôn kiểm chứng những business invariants cần thiết.

### 34.2. Aggregation này là cross-tenant

Chỉ dùng cho backend migration validation được ủy quyền. API của một tenant phải thêm $match tenantId.

### 34.3. Dữ liệu payment riêng

Một report thanh toán nên đối chiếu ledger/payment events với provider, không mặc định booking amount bằng tiền đã nhận.

## 35. Cutover gates

Trước khi chuyển traffic:

1. Backfill hoàn thành theo scope.
2. CDC lag/watermark đạt giới hạn đã chốt.
3. Counts/totals/invariants được đối chiếu.
4. Critical shadow reads đạt.
5. Read/write/transaction workflows pass.
6. Unique indexes/schema validations sẵn sàng.
7. Network/TLS/auth/roles phù hợp.
8. Query plans/p95 ở mức SLO.
9. Source-of-truth chuyển theo kế hoạch được duyệt.
10. Rollback/forward-fix strategy sẵn sàng.

### 35.1. Có thể tạm freeze writes

Một short write pause giúp CDC catch up tới final watermark và kiểm tra cutover consistency. Chỉ dùng khi SLA cho phép.

### 35.2. Canary rollout

Có thể chuyển một tỷ lệ nhỏ read traffic trước, rồi tăng dần. Write cutover cần đồng bộ các services để tránh SQL/MongoDB diverge.

### 35.3. Không đánh dấu PASS chỉ vì copy job SUCCESS

Dữ liệu có thể thiếu, indexes chưa có hoặc application chưa hoạt động với model mới.

## 36. Rollback sau khi MongoDB đã nhận writes

~~~text
SQL frozen at T0
        |
        v
MongoDB receives new bookings at T1
        |
        v
Problem detected at T2
~~~

Đổi application trở về SQL cũ ngay sẽ làm mất writes được ghi sau T0 nếu SQL không được đồng bộ ngược.

### 36.1. Rollback hay forward-fix?

- Rollback khi dữ liệu có thể được bảo toàn và hợp đồng cho phép.
- Forward-fix khi MongoDB đã là nguồn sự thật và giữ nhiều writes mới.
- Reverse replication/reconciliation khi cần trở lại SQL mà không mất dữ liệu.

### 36.2. Không tạo split-brain

Không cho SQL và MongoDB nhận independent authoritative writes cùng lúc mà không có conflict/consistency design.

### 36.3. Đặt rollback gate trước cutover

Ai phê duyệt, thời hạn, dữ liệu mới xử lý thế nào, outbox/payment queues đi đâu — phải định nghĩa trước.

## 37. Java Sync Driver: đọc booking một lượt

Ví dụ Java command-line demo:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import org.bson.Document;
import org.bson.conversions.Bson;

public class BookingReadDemo {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                "MONGODB_URI is required"
            );
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db =
                client.getDatabase("rental_demo");
            MongoCollection<Document> bookings =
                db.getCollection("bookings");

            String trustedTenant = "tenant-a";

            Bson filter = Filters.and(
                Filters.eq(
                    "_id", "tenant-a:booking:1001"
                ),
                Filters.eq(
                    "tenantId", trustedTenant
                )
            );

            Bson projection = Projections.include(
                "customerSnapshot",
                "vehicleSnapshot",
                "period",
                "addons",
                "amount",
                "status"
            );

            Document doc = bookings.find(filter)
                .projection(projection)
                .first();

            if (doc == null) {
                System.out.println("Not found");
            } else {
                System.out.println(doc.toJson());
            }
        }
    }
}
~~~

### 37.1. MongoClient lifecycle

Web services thường tái sử dụng MongoClient theo vòng đời service. Ví dụ dùng try-with-resources vì chạy một lần.

### 37.2. Không lộ dữ liệu trực tiếp

Trong production, map Document thành DTO với fields được phép, không trả raw internal JSON.

### 37.3. Tenant ID từ auth

trustedTenant được backend xác minh, không đến từ tham số tùy ý do user tự khai.

## 38. Java Sync Driver: cập nhật state có điều kiện

~~~java
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.conversions.Bson;

Bson filter = Filters.and(
    Filters.eq(
        "_id", "tenant-a:booking:1001"
    ),
    Filters.eq(
        "tenantId", "tenant-a"
    ),
    Filters.eq(
        "status", "PENDING"
    )
);

Bson update = Updates.combine(
    Updates.set(
        "status", "CONFIRMED"
    ),
    Updates.inc(
        "version", 1
    ),
    Updates.currentDate(
        "updatedAt"
    )
);

UpdateResult result = bookings.updateOne(
    filter, update
);

if (result.getMatchedCount() == 0) {
    throw new IllegalStateException(
        "Booking not found or state changed"
    );
}
~~~

### 38.1. Single-document atomicity

status và version được cập nhật cùng một write trên booking.

### 38.2. Không đồng bộ payment tự động

Một booking status update không tự cập nhật payment ledger ở collection khác hoặc provider bên ngoài.

### 38.3. Tenant isolation

Tất cả update/delete/read của repository cần scope theo trusted tenant.

## 39. Multi-tenant security trong document model

Mọi API cần:

- Tenant context đã xác thực.
- Filter tenantId ở document root hoặc access-control rule tương ứng.
- Cross-reference validation.
- Tenant-aware $lookup khi cần.
- Không chấp nhận arbitrary BSON filters từ client.
- Indexes phục vụ tenant-scoped queries.
- Monitoring audit với masked identifiers.

### 39.1. Snapshot có PII

Không sao chép toàn bộ profile nếu màn hình chỉ cần displayName. Dữ liệu nhạy cảm có retention/anonymization policy riêng.

### 39.2. Field-level access

Projection giảm payload, nhưng không tự bảo đảm authorization. Dùng DTO/role policy.

### 39.3. Không giả định `_id` đủ để cấp quyền

Dù `_id` là UUID không đoán được, ứng dụng vẫn cần kiểm tra tenant/owner.

## 40. Sharding và tăng trưởng dài hạn

Nếu hệ thống cần sharded cluster, chọn shard key theo query patterns, cardinality và phân phối write load.

### 40.1. TenantId có thể vừa hữu ích vừa nguy hiểm

Phần lớn queries theo tenant giúp locality, nhưng một tenant lớn chiếm đa số writes có thể gây hotspot tùy shard-key design.

### 40.2. Không chọn chỉ vì field xuất hiện ở mọi documents

Đánh giá distribution, growth, query targeting, unique-index restrictions và resharding considerations theo MongoDB version.

### 40.3. Denormalization không thay sharding design

Một collection bookings với snapshots vẫn cần shard targeting và indexes đúng khi scale.

## 41. Đánh giá mô hình bằng metrics

Đo trước và sau:

- P50/p95/p99 API latency.
- Number of DB round trips/request.
- Documents examined vs returned.
- Winning plans và index use.
- Document size distribution.
- Write latency và write amplification.
- Storage/index cost.
- Multi-document transaction frequency.
- CDC lag/read-model staleness.
- Data reconciliation diffs.
- Business error rates và availability.

### 41.1. Không chỉ đếm JOIN giảm

Một mô hình “1 document” nhưng write p95 xấu hoặc document quá lớn có thể không tốt hơn.

### 41.2. Fixture nhỏ khác performance dataset

Test correctness dùng vài documents có chủ đích; load test dùng dataset representative và phân phối tenants/requests thực tế.

### 41.3. Thử negative cases

Booking với zero addons, missing customer, tenant mismatch, duplicate business ID, payment retry và booking interval overlap.

## 42. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Một table thành một collection y nguyên | JOIN/round trips vẫn nhiều | Thiết kế theo access patterns |
| Nhúng mọi booking vào customer | Unbounded array, 16 MiB | Booking collection riêng |
| Nhúng mọi payment event | Audit history phình | Separate append-only |
| Đồng bộ current vehicle rate vào booking cũ | Sai lịch sử giá | Immutable price snapshot |
| Sao chép master vào mọi record | Fan-out updates | Reference/snapshot có mục đích |
| Cùng field có hai authoritative writers | Drift/conflicts | Ownership contract |
| Bỏ tenant filter ở lookup | Cross-tenant leak | Tenant-aware access |
| Không có unique business index | Duplicate bookings | Stable ID + uniqueness |
| Chuyển Date thành string | Range/sort sai | BSON Date |
| Chuyển Decimal thành double | Precision loss | Decimal128/minor units |
| SQL NULL thành missing vô ý | Query semantics đổi | Mapping policy |
| Không có schemaVersion | Khó mixed reads | Expand–migrate–contract |
| Backfill không có checkpoint | Retry tốn kém, mất dữ liệu | Batched resumable job |
| Random IDs khi retry | Duplicates | Deterministic mapping |
| CDC đến trước, backfill ghi sau | Stale overwrite | Watermark/source version |
| Không xử lý deletes | Ghost records | Tombstone/delete mapping |
| Dual-write không outbox | Partial commits | One canonical store + CDC |
| Reconcile chỉ total count | Bỏ sót sai tenant/amount | Group counts + invariants |
| So dữ liệu khác timestamp | False diffs | Common watermark |
| Cutover khi CDC còn lag | Stale/missing writes | Cutover gates |
| Rollback bằng đổi URI sau new writes | Mất writes mới | Reverse sync/forward-fix |
| Query absence rồi insert booking | Double booking race | Slot/contended allocation |
| Unique start/end tưởng chặn overlap | Interval collision | Real concurrency design |
| Không index theo feed | Sort/scan chậm | Explain/index design |
| Dùng tiny fixture để kết luận scale | Kết luận sai | Separate performance suite |
| Đưa raw PII vào test migration | Privacy risk | Synthetic/anonymized data |

## 43. Quy tắc ra quyết định nhúng hay tham chiếu

~~~text
Is the child always read with the parent?
    |
    +-- No --> Reference likely
    |
    v
Is cardinality strictly bounded?
    |
    +-- No --> Separate collection likely
    |
    v
Does it share lifecycle and consistency?
    |
    +-- Yes --> Embedding candidate
    |
    +-- No --> Reference / historical snapshot
    |
    v
Is it updated independently or widely shared?
    |
    +-- Yes --> Reference or derived model
    |
    v
Will max document size stay reasonable?
    |
    +-- No --> Reconsider
    |
    v
Prototype, index and measure workload
~~~

Đây là **heuristic**, không phải quy tắc tuyệt đối. Historical snapshot có thể nằm trong booking dù master data được cập nhật độc lập.

## 44. Bài tập phân tích relational schema

### Bài 1 — Inventory

Từ bảng customers/vehicles/bookings/booking_addons/payment_events, liệt kê 8 access patterns, filter/sort và số round trips dự kiến.

### Bài 2 — Booking detail

Thiết kế booking document tối ưu AP1. Những fields nào nên snapshot, fields nào chỉ reference?

### Bài 3 — Giá thuê lịch sử

Vehicle đổi current rate từ 700000 thành 900000. Booking đã xác nhận cần hiển thị giá nào? Vì sao?

### Bài 4 — One-to-many

Add-ons tối đa 10 phần tử vs payment events vô hạn. Chọn embed/reference và giải thích.

### Bài 5 — Many-to-many

Vehicle/features có nhiều metadata thay đổi. Thiết kế featureCodes và features master.

### Bài 6 — Current vs snapshot

Customer đổi displayName. Khi nào bookingSnapshot giữ tên cũ, khi nào API cần current name?

## 45. Bài tập truy vấn và indexes

### Bài 7 — Tenant history

Viết filter/sort/index để đọc 20 bookings mới nhất của customer thuộc tenant-a.

### Bài 8 — Keyset

Với sort createdAt desc, _id desc, viết điều kiện trang tiếp theo.

### Bài 9 — $lookup

Dùng $lookup lấy current customer, bảo đảm tenantId match.

### Bài 10 — Group by

Viết aggregation đếm bookings và sum amount theo tenant/status.

### Bài 11 — Unique ID

SQL booking id chỉ unique trong tenant. Đề xuất MongoDB _id và unique business key.

### Bài 12 — BSON conversion

Chuyển SQL BIGINT, DECIMAL, TIMESTAMP và NULL theo semantics rõ.

### Bài 13 — Validator

Viết JSON Schema validator cho tenantId, period Date, status enum.

## 46. Bài tập consistency

### Bài 14 — Status transition

Hai requests CONFIRM và CANCEL cùng bắt đầu từ PENDING. Viết conditional update và expected outcome.

### Bài 15 — Interval overlap

Hai requests cùng kiểm tra xe trống rồi insert. Vì sao xảy ra double booking? Đề xuất slot hoặc contention record design.

### Bài 16 — Payment summary

Payment event đến hai lần. Làm sao update summary không cộng amount hai lần?

### Bài 17 — External effects

Booking confirmed cần gửi email và charge payment. MongoDB transaction có tự rollback hai tác vụ ngoài database không?

## 47. Bài tập migration

### Bài 18 — Mapping

Lập SQL-to-BSON mapping đầy đủ với stable IDs, snapshots, addons, dates, money, schemaVersion.

### Bài 19 — Data profiling

Những baseline counts, orphan checks, duplicate checks và max cardinality nào cần trước migration?

### Bài 20 — Batch checkpoint

Thiết kế backfill keyset theo source ID, resume sau crash và ghi checkpoint đúng lúc.

### Bài 21 — CDC ordering

Backfill PENDING tới sau CDC CONFIRMED. Thiết kế ngăn regression.

### Bài 22 — SQL DELETE

Một booking bị xóa/soft-delete trong SQL trong lúc CDC chạy. Target cần xử lý thế nào?

### Bài 23 — Dual-write

SQL commit thành công nhưng MongoDB write fail. Hãy thiết kế outbox/canonical source strategy.

### Bài 24 — Reconciliation

Total count bằng nhau nhưng 100 bookings bị sai tenant. Dùng gì để phát hiện?

### Bài 25 — Shadow read

Thiết kế shadow queries cho booking details và feed, lưu sanitized diffs.

### Bài 26 — Cutover

Đặt go/no-go gates cho CDC lag, reconciliation, indexes, auth và application smoke.

### Bài 27 — Rollback

MongoDB đã nhận 500 bookings sau cutover. Vì sao không thể chỉ đổi URI về SQL? Đề xuất forward-fix/reverse sync.

### Bài 28 — Mixed schema

Chuyển totalMinor root sang amount.totalMinor. Thiết kế expand–migrate–contract và idempotent backfill.

## 48. Checklist trước khi chuyển dữ liệu

### Phân tích

1. Danh mục read/write access patterns được xác nhận.
2. Cardinality, growth và lifecycle được đo.
3. Invariants/constraints và transaction boundaries rõ.
4. Master, snapshot, events và derived models được phân biệt.
5. Data privacy và retention requirements rõ.
6. Document-size/headroom được ước lượng.

### Thiết kế

7. Embed/reference choice có lý do theo AP.
8. Không có unbounded arrays không kiểm soát.
9. Stable IDs và tenant scope hợp lệ.
10. Money/dates/null BSON mapping thống nhất.
11. Status/availability concurrency được thiết kế.
12. Indexes theo filter/sort/unique pattern.
13. Schema validation và versioning được chuẩn bị.
14. Derived field ownership/synchronization được ghi lại.

### Migration

15. Có source profile và baseline.
16. Có deterministic transform, checkpoint và retry.
17. Có consistent snapshot/watermark.
18. CDC ordering/deletes/duplicate handling rõ.
19. Không có hai authoritative writers.
20. Có reconciliation theo tenant/status/amount/invariants.
21. Shadow reads và concurrency tests pass.
22. Có cutover/rollback owner và gates.

### Vận hành

23. Monitoring p95, errors, CDC lag và throughput.
24. Backup/restore/DR plan cho MongoDB target.
25. Security/roles/TLS được kiểm chứng.
26. Old SQL writes được retired theo plan.
27. Data/credentials cũ được xử lý đúng retention policy.
28. Evidence và corrective actions có owner.

## 49. Runbook migration minh họa

~~~text
DISCOVER:
  Inventory SQL tables and constraints
  Record hot reads, writes, cardinalities
  Identify historical snapshot requirements

DESIGN:
  Choose aggregate/document boundaries
  Embed bounded, reference unbounded data
  Define canonical/derived ownership
  Specify BSON mapping, indexes and schemaVersion
  Test interval concurrency and tenant isolation

PREPARE:
  Verify source/target and backups
  Capture baseline and CDC watermark
  Define deterministic IDs
  Approve cutover/rollback plan

BACKFILL:
  Extract consistent batches
  Transform and write idempotently
  Save checkpoints after confirmations
  Monitor throughput, quarantine failures

SYNC:
  Consume ordered CDC events
  Deduplicate and handle deletes
  Prevent stale backfill overwrites
  Monitor lag and reconcile

VALIDATE:
  Counts by tenant/status
  Money totals and business invariants
  Deep sample comparison
  Shadow API reads
  Index plans, performance and security

CUTOVER:
  Quiesce source writes if needed
  Catch up CDC to agreed watermark
  Verify readiness and switch traffic
  Monitor application and data quality

RECOVER:
  Stop rollout if gates fail
  Choose rollback or forward-fix
  Reconcile all writes after cutover

CLOSE:
  Preserve sanitized evidence
  Retire old write path and secrets safely
  Update monitoring, backups and runbooks
~~~

## 50. Kết luận

Chuyển từ quan hệ sang document là một **quá trình thiết kế lại mô hình theo cách ứng dụng sử dụng dữ liệu**:

- **Không chuyển bảng máy móc:** bắt đầu với access patterns, vòng đời và consistency requirements.
- **Nhúng khi hợp lý:** các child records nhỏ, bounded và thường được đọc/ghi cùng parent.
- **Tham chiếu khi cần:** master data, audit histories và quan hệ tăng không giới hạn.
- **Snapshot có chủ đích:** bảo vệ giá, tên và điều khoản đã chốt tại thời điểm giao dịch.
- **Giữ source of truth rõ:** derived summaries và read models có ownership, event ordering và reconciliation.
- **Thiết kế concurrency:** single-document atomicity không tự giải quyết mọi giao dịch nhiều collections hay interval overlap.
- **Map dữ liệu chính xác:** stable IDs, money types, dates, NULL và schema versions.
- **Migration phải repeatable:** backfill checkpoints, CDC, idempotency, shadow reads, validation và cutover gates.
- **Rollback phải tính đến new writes:** sau cutover, đổi connection string chưa đủ để bảo toàn dữ liệu.

Một document model được thiết kế tốt làm luồng phổ biến đơn giản hơn, dữ liệu lịch sử chính xác hơn và hệ thống dễ mở rộng hơn. Thành công của migration không nằm ở số bảng được xóa, mà ở **sự đúng đắn nghiệp vụ, hiệu năng đo được và khả năng tiến hóa an toàn**.

## Tài liệu tham khảo

- [MongoDB Manual — Data Modeling](https://www.mongodb.com/docs/manual/data-modeling/)
- [MongoDB Manual — Embedded Data and References](https://www.mongodb.com/docs/manual/data-modeling/concepts/embedding-vs-references/)
- [MongoDB Manual — Schema Design Patterns](https://www.mongodb.com/docs/manual/data-modeling/design-patterns/)
- [MongoDB Manual — BSON Documents](https://www.mongodb.com/docs/manual/core/document/)
- [MongoDB Manual — Aggregation](https://www.mongodb.com/docs/manual/aggregation/)
- [MongoDB Manual — $lookup](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/)
- [MongoDB Manual — Indexes](https://www.mongodb.com/docs/manual/indexes/)
- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB Manual — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB Manual — Atomicity](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [MongoDB Manual — Sharding](https://www.mongodb.com/docs/manual/sharding/)
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/)
