# Xóa theo nhóm thời gian và chiến lược luân chuyển dữ liệu

## 1. Tại sao NoSQL cần chiến lược vòng đời dữ liệu?

Một hệ thống NoSQL có thể ghi hàng triệu sự kiện mỗi ngày, nhưng không phải dữ liệu nào cũng cần tồn tại mãi mãi ở cùng một tầng lưu trữ. Nhật ký ứng dụng, dữ liệu IoT, phiên hoạt động, truy cập API và các bản ghi thay đổi trạng thái thường có **giá trị và nhu cầu truy vấn giảm dần theo thời gian**.

Giả sử nền tảng thu thập dữ liệu cảm biến cần:

- Đọc **sự kiện thô trong 30 ngày** để điều tra lỗi gần đây.
- Xem **thống kê tổng hợp theo giờ trong 12 tháng**.
- Giữ một số hồ sơ có nghĩa vụ lưu giữ dài hạn để kiểm toán.
- Xóa dữ liệu đã hết hạn và không còn thuộc ngoại lệ cần giữ.
- Đảm bảo API không hiển thị dữ liệu hết hạn, kể cả khi hệ thống dọn dẹp vật lý chưa chạy xong.

Nếu tất cả sự kiện được đẩy vào một partition không giới hạn hoặc xóa bằng hàng triệu thao tác từng item, chi phí I/O, chỉ mục, tombstone, replication, backup và vận hành có thể tăng đáng kể.

**Xóa theo nhóm thời gian (time-bucket deletion)** tổ chức bản ghi thành các nhóm ứng với khoảng thời gian xác định, chẳng hạn giờ, ngày hoặc tháng. Khi **toàn bộ nhóm** đã đủ điều kiện xóa, hệ thống có thể xử lý theo đơn vị nhóm thay vì truy tìm từng bản ghi. Tuy nhiên, mức hiệu quả phụ thuộc nhóm đó là partition logic, collection, table hay đơn vị lưu trữ mà DBMS thật sự hỗ trợ loại bỏ.

**Luân chuyển dữ liệu (data rotation)** mở rộng ý tưởng này: dữ liệu có thể chuyển từ tầng truy cập nhanh sang tầng ít truy cập, được tổng hợp, lưu trữ dài hạn hoặc xóa theo chính sách.

Bài học tập trung vào cách thiết kế và vận hành vòng đời dữ liệu, không chỉ cú pháp lệnh `DELETE`.

### Mục tiêu

Sau bài học, người đọc có thể:

1. Phân biệt **retention**, **TTL**, **time bucket**, **archive**, **rollup**, **rotation** và **purge**.
2. Chọn trường thời gian và độ rộng bucket phù hợp với workload và thời hạn giữ.
3. So sánh xóa từng item với xóa cả collection/table theo kỳ.
4. Hiểu các giới hạn đặc thù trong MongoDB, Cassandra và DynamoDB.
5. Xử lý dữ liệu đến trễ, tombstone, backup, legal hold và yêu cầu xóa riêng lẻ.
6. Xây dựng quy trình rotation có kiểm chứng, retry, audit và cảnh báo.
7. Ước lượng chi phí và đánh đổi khi phải đọc dữ liệu xuyên nhiều bucket.

---

## 2. Các thuật ngữ quan trọng

| Khái niệm | Ý nghĩa | Điểm cần lưu ý |
|---|---|---|
| **Retention policy** | Quy tắc dữ liệu được hoặc phải giữ trong bao lâu | Phụ thuộc nghiệp vụ, hợp đồng và nghĩa vụ liên quan |
| **TTL – time to live** | Thời hạn tồn tại của một item/giá trị | Việc xóa vật lý có thể xảy ra bất đồng bộ |
| **Time bucket** | Nhóm dữ liệu trong một khoảng thời gian | Có thể là partition key, collection/table hoặc prefix của key |
| **Rotation** | Chuyển nhóm dữ liệu giữa các trạng thái/tầng | Thường có bước đóng kỳ, lưu trữ và dọn dẹp |
| **Archival** | Chuyển dữ liệu cần giữ sang kho lưu trữ ít truy cập | Cần kiểm tra khả năng phục hồi trước khi xóa nguồn |
| **Rollup** | Tổng hợp dữ liệu chi tiết thành chỉ số theo kỳ | Không thể suy ra đầy đủ mọi sự kiện gốc từ bản tổng hợp |
| **Purge** | Loại bỏ dữ liệu khi đủ điều kiện | Phải tính cả bản sao, chỉ mục, cache và backup |
| **Legal hold** | Ngoại lệ yêu cầu tạm giữ một phần dữ liệu | Có thể chặn việc drop cả bucket |
| **Tombstone** | Dấu vết xóa/hết hạn trong một số storage engine | Có thể tạo chi phí đọc và compaction trước khi được dọn |
| **Watermark** | Mốc dùng để kết luận dữ liệu cũ đã đến đủ theo hợp đồng | Không tự đảm bảo mọi nguồn đều tuân thủ |
| **Late arrival** | Sự kiện đến sau thời điểm phát sinh | Có thể cần ghi vào bucket cũ hoặc đường nhập riêng |

Điểm cốt lõi: **dữ liệu không còn hiển thị**, **đã hết hạn** và **được xóa vật lý khỏi các bản sao** là ba trạng thái khác nhau.

## 3. Viết chính sách vòng đời trước khi viết câu lệnh xóa

Một hệ thống có thể có nhiều lớp dữ liệu:

| Lớp | Mục đích | Ví dụ thời hạn minh họa |
|---|---|---|
| Raw events | Điều tra sự cố và truy vấn chi tiết | 30 ngày |
| Hourly aggregates | Biểu đồ xu hướng và so sánh | 12 tháng |
| Daily aggregates | Báo cáo dài hạn | 3 năm |
| Debug logs | Gỡ lỗi ngắn hạn | 7 ngày |
| Approved archives | Hồ sơ cần lưu theo chính sách | Phụ thuộc loại hồ sơ |
| Legal-hold records | Hồ sơ được giữ theo yêu cầu đặc biệt | Đến khi được phép giải tỏa |

**Những khoảng thời gian này chỉ là giả định cho bài học**, không phải thời hạn chuẩn áp dụng cho mọi tổ chức.

Một retention policy nên có:

- Tên, phiên bản và người chịu trách nhiệm.
- Loại dữ liệu, mức nhạy cảm và nơi nó đang được lưu.
- Thời hạn giữ, **điểm bắt đầu tính thời hạn** và cách hiểu “ngày”.
- Các API được phép truy cập dữ liệu trong giai đoạn nào.
- Có cần archive hoặc rollup trước purge không.
- Cách xử lý dữ liệu đến muộn.
- Ngoại lệ về legal hold, yêu cầu xóa cá nhân và kiểm toán.
- Những bản sao phải xử lý: search index, cache, snapshot, backup, export.
- Thời hạn mong muốn giữa mốc hết hạn và trạng thái đã purge.
- Cách chứng minh rằng quy trình đã thực hiện đủ bước.

Ví dụ đặc tả logic:

~~~yaml
dataClass: sensor_raw
policyVersion: 3
retentionClock: ingestedAt
retentionDurationDays: 30
archiveBeforeDelete: false
legalHoldSupported: true
sourceOfTruth: sensor_event_store
owner: data-platform
~~~

Đây không phải file cấu hình chung của mọi DBMS. Nó minh họa việc **tách chính sách nghiệp vụ ra khỏi cách thực hiện xóa**.

## 4. Chọn đúng mốc thời gian để tính bucket và TTL

Dữ liệu sự kiện thường có ít nhất ba thời điểm:

- `eventAt`: sự kiện xảy ra tại thiết bị hoặc nguồn.
- `ingestedAt`: hệ thống nhận sự kiện.
- `expiresAt`: thời điểm bản ghi hết hạn theo chính sách.

Ví dụ:

~~~text
Thiết bị mất mạng, gửi bù phép đo cũ

eventAt    = 2026-11-10T08:00:00Z
ingestedAt = 2026-11-14T08:00:00Z
~~~

Nếu chính sách giữ 30 ngày **từ lúc sự kiện xảy ra**, thời hạn tính từ `eventAt`. Nếu giữ 30 ngày **từ lúc hệ nhận**, thời hạn tính từ `ingestedAt`. Hai cách này khác nhau bốn ngày ở ví dụ trên.

### 4.1. Bucket theo event time

~~~text
eventDay = UTC_DATE(eventAt)
partition = (deviceId, eventDay)
~~~

Ưu điểm: truy vấn lịch sử theo ngày phát sinh dễ định tuyến và tổng hợp. Nhược điểm: nguồn đến muộn có thể ghi trở lại bucket cũ; đồng hồ thiết bị sai có thể đưa dữ liệu vào quá khứ hoặc tương lai.

### 4.2. Bucket theo ingestion time

~~~text
ingestDay = UTC_DATE(ingestedAt)
partition = (deviceId, ingestDay)
~~~

Ưu điểm: dễ biết nhóm dữ liệu đến trong từng kỳ; thường thuận lợi cho vận hành luân chuyển theo ngày nhận.

Nhược điểm: một truy vấn theo ngày xảy ra có thể phải quét nhiều ngày nhận nếu độ trễ không được giới hạn.

### 4.3. Expiration time là quyết định riêng

Với chính sách 30 × 24 giờ từ lúc nhận:

\[
\mathrm{expiresAt} = \mathrm{ingestedAt} + 30 \times 86400\ \mathrm{seconds}.
\]

Nhưng “30 ngày theo lịch địa phương” không nhất thiết là 30 × 24 giờ nếu vùng thời gian có thay đổi giờ mùa hè. Cần quy định rõ **UTC, ranh giới ngày và quy tắc nghiệp vụ**.

Nếu timestamp từ client không đáng tin, nên lấy `ingestedAt` từ phía dịch vụ nhận dữ liệu và kiểm tra `eventAt` theo mức lệch đồng hồ cho phép.

**Không thể suy ra thời điểm xóa hợp lệ chỉ từ tên collection** nếu bản ghi trong collection có các `expiresAt` khác nhau.

---

## 5. Time bucketing: nhóm dữ liệu theo giờ, ngày hoặc tháng

Các hình thức time bucket:

~~~text
Một partition:
  (tenantId, deviceId, eventDay)

Một collection:
  events_2026_11

Một table:
  events_2026_q4

Một key:
  TENANT#7#DAY#2026-11-14#EVENT#9001
~~~

Đơn vị **bucket logic** không nhất thiết trùng đơn vị mà engine có thể drop nhanh.

### 5.1. Ước lượng kích thước theo tốc độ ghi

Một thiết bị ghi 10 sự kiện/giây, mỗi sự kiện trung bình 400 byte logic:

~~~text
Một phút: 10 × 60 × 400 = 240.000 byte
Một giờ: 10 × 3.600 × 400 = 14.400.000 byte
Một ngày: 10 × 86.400 × 400 = 345.600.000 byte
~~~

Khoảng **14,4 MB/giờ** hoặc **345,6 MB/ngày** ở đơn vị thập phân, chưa tính replication, index, metadata, tombstone và compression.

Với 1.000 thiết bị tương tự, dữ liệu logic khoảng **345,6 GB/ngày**. Giữ 90 ngày ở tải không đổi sẽ tương đương **31,104 TB** dữ liệu logic trước overhead.

Như vậy, bucket một ngày của một thiết bị có thể đã rất lớn. Bucket một ngày của toàn hệ sẽ còn lớn hơn nhiều. Không nên chọn bucket theo thói quen mà không tính tốc độ tăng.

### 5.2. Đánh đổi theo độ rộng bucket

| Tiêu chí | Bucket dài (tháng) | Bucket ngắn (giờ) |
|---|---|---|
| Kích thước mỗi nhóm | Lớn hơn | Nhỏ hơn |
| Số nhóm phải quản lý | Ít | Nhiều |
| Truy vấn nhiều ngày | Ít nhóm phải duyệt | Có thể phải ghép nhiều nhóm |
| Độ hạt xóa toàn nhóm | Thô | Chính xác hơn |
| Dữ liệu đến trễ | Có thể ghi lại một nhóm lớn | Có thể phải mở lại nhiều nhóm cũ |
| Metadata và chỉ mục | Ít đối tượng quản trị | Có thể rất nhiều đối tượng |
| Tải ghi tập trung | Có thể nóng | Vẫn có thể nóng ở bucket hiện tại |

Một bucket quá ngắn có thể tạo hàng triệu partition/collection nhỏ. Một bucket quá dài có thể làm đơn vị quản lý và xóa không phù hợp với độ chính xác retention.

### 5.3. Time bucket không tự giải quyết điểm nóng

Nếu một tenant tạo 50.000 event/giây, bucket theo giờ vẫn gom mọi ghi trong giờ vào cùng partition nếu khóa không có thành phần chia tải.

Có thể thêm:

~~~text
partition = (tenantId, eventHour, hashBucket)
hashBucket = stableHash(eventId) mod 16
~~~

Các bản ghi được trải qua 16 partition, nhưng API cần hợp nhất dữ liệu từ các bucket liên quan. Thuật toán hash và `eventId` phải ổn định khi retry, nếu không sự kiện gửi lại có thể đi vào partition khác và bị ghi trùng.

## 6. Xóa từng bản ghi và xóa cả nhóm thời gian

Có thể xóa theo nhiều mức:

| Mức xóa | Ví dụ | Đặc điểm |
|---|---|---|
| Item/document | Xóa một event có ID cụ thể | Linh hoạt, nhưng số lần ghi/xóa lớn |
| Nhiều item theo truy vấn | `deleteMany` hoặc batch API | Giảm công điều phối, không loại bỏ chi phí cập nhật từng item |
| Partition logic | Xóa dữ liệu của `(deviceId, eventDay)` | Không chắc tương đương xóa vật lý tức thì |
| Collection/table | Drop `events_2026_10` | Có thể loại cả nhóm ở mức cấu trúc, nhưng phải bảo đảm mọi item đủ điều kiện |
| Archive object | Xóa một gói xuất dữ liệu | Phải xử lý manifest, version và chính sách lưu trữ |

### 6.1. Tại sao xóa hàng triệu item có thể đắt?

Nếu có 30 triệu document hết hạn cùng ngày:

- Mỗi thao tác xóa có thể phải cập nhật dữ liệu, index và replication.
- Cơ chế background purge/compaction có thể tụt lại.
- I/O dọn dẹp có thể tranh tài nguyên với query online.
- Dữ liệu có thể vẫn nằm trong snapshot/backup.
- Công việc retry/đối soát tăng khi xóa thất bại giữa chừng.

Một lệnh batch có thể giảm số round trip so với 30 triệu lệnh riêng, nhưng không tự khiến chi phí I/O nội bộ trở thành bằng không.

### 6.2. Xóa cả bucket không phải lúc nào cũng an toàn

Chỉ xóa toàn bộ một bucket khi:

1. **Mọi bản ghi** trong bucket đã đủ hạn theo chính sách phù hợp.
2. Không có bản ghi còn legal hold hoặc ngoại lệ phải giữ.
3. Dữ liệu cần archive/rollup đã được kiểm chứng.
4. Không còn ghi hợp lệ hoặc có cách xử lý late arrival riêng.
5. Không còn read path bắt buộc phải truy cập nhóm đó.
6. Các bản sao, backup và quyền truy cập được xử lý theo chính sách.
7. Tác vụ xóa được phân quyền, ghi audit và có cơ chế kiểm tra sau thao tác.

Nếu bucket tháng 10 còn một document có thời hạn giữ tới tháng 12, **không thể drop nguyên collection tháng 10** ở đầu tháng 11 mà không làm mất dữ liệu phải giữ.

### 6.3. DELETE một partition khác DROP TABLE

Một partition được tạo theo `eventDay` trong Cassandra vẫn chỉ là **partition logic**. Xóa partition qua CQL có thể tạo tombstone; không tương đương xóa nguyên table ở mức cấu trúc.

Đừng viết trong tài liệu thiết kế rằng “partition theo ngày cho phép xóa O(1)” nếu DBMS không cung cấp bảo đảm đó. Chi phí thực phải được đo theo engine, retention, số replica và workload.

---

## 7. Rotation theo tầng: hot, warm, cold, archive, purge

Một vòng đời thường gặp:

~~~mermaid
flowchart LR
    A["Ingestion"] --> B["Hot raw data"]
    B --> C["Warm data"]
    C --> D["Cold storage"]
    D --> E["Verified archive"]
    E --> F["Purge"]
    B --> G["Hourly rollup"]
    G --> H["Aggregated storage"]
~~~

Không phải hệ nào cũng cần đủ năm tầng.

### 7.1. Hot

Dữ liệu mới, ghi nhiều và được truy vấn thường xuyên. Có thể có index cho API thời gian thực, replica đáp ứng SLO và cache cho các truy vấn quan trọng.

### 7.2. Warm

Dữ liệu ít được thay đổi và truy cập thưa hơn. Có thể dùng ít index hoặc cấu hình lưu trữ phù hợp, nhưng phải tính dữ liệu đến trễ và cập nhật bổ sung.

### 7.3. Cold

Dữ liệu cần giữ nhưng không cần phục vụ API tức thời. Mục tiêu là tối ưu chi phí lưu trữ, chấp nhận thời gian truy xuất lâu hơn nếu hợp đồng cho phép.

### 7.4. Archive

Gói dữ liệu được xuất và xác minh với schema version, checksum, manifest, phân quyền, mã hóa và khả năng restore. Archive phục vụ lưu giữ/tra cứu dài hạn, **khác backup** nhằm khôi phục sau sự cố.

### 7.5. Rollup

Dữ liệu thô có thể được tổng hợp thành dữ liệu theo giờ/ngày:

~~~json
{
  "deviceId": "sensor-01",
  "hour": "2026-11-14T08:00:00Z",
  "sampleCount": 3600,
  "minTemperatureC": 26.1,
  "maxTemperatureC": 32.4,
  "sumTemperatureC": 105120.0,
  "avgTemperatureC": 29.2
}
~~~

Nếu raw được xóa, rollup không thể khôi phục toàn bộ 3.600 phép đo ban đầu. Vì thế cần phân biệt dữ liệu nào phải giữ **chi tiết** và dữ liệu nào chỉ cần số tổng hợp.

### 7.6. Purge

Dữ liệu đã hết hạn và không còn nghĩa vụ giữ được loại bỏ theo quy trình. Việc API không còn trả dữ liệu là điều kiện cần trong nhiều hệ thống, nhưng chưa đủ để chứng minh các bản sao vật lý đều bị xóa.

## 8. MongoDB: collection theo tháng và cơ chế rotation

Một cách tổ chức dữ liệu:

~~~text
sensor_events_2026_10
sensor_events_2026_11
sensor_events_2026_12
~~~

Tạo collection tháng 11 trong `mongosh`:

~~~javascript
db.createCollection("sensor_events_2026_11");

db.getCollection("sensor_events_2026_11").createIndex({
  tenantId: 1,
  deviceId: 1,
  eventAt: -1,
  eventId: -1
});
~~~

Ghi dữ liệu:

~~~javascript
db.getCollection("sensor_events_2026_11").insertOne({
  eventId: "event-9001",
  tenantId: "tenant-7",
  deviceId: "sensor-01",
  eventAt: ISODate("2026-11-14T08:15:27.123Z"),
  ingestedAt: ISODate("2026-11-14T08:15:30Z"),
  temperatureC: 29.1
});
~~~

### 8.1. Truy vấn đúng collection

~~~javascript
db.getCollection("sensor_events_2026_11").find(
  {
    tenantId: "tenant-7",
    deviceId: "sensor-01",
    eventAt: {
      $gte: ISODate("2026-11-14T00:00:00Z"),
      $lt: ISODate("2026-11-15T00:00:00Z")
    }
  },
  {
    _id: 0,
    eventId: 1,
    eventAt: 1,
    temperatureC: 1
  }
).sort({ eventAt: -1, eventId: -1 }).limit(100);
~~~

Nếu truy vấn đi qua hai tháng, ứng dụng phải đọc hai collection rồi **merge theo `eventAt DESC, eventId DESC`**. Cần lưu tie-breaker ổn định, vì hai event có thể trùng timestamp.

### 8.2. Xóa collection đã đủ hạn

Khi mọi document trong collection tháng 10 đã hết hạn và các điều kiện an toàn đã được xác minh, thao tác minh họa:

~~~javascript
db.getCollection("sensor_events_2026_10").drop();
~~~

**Đây là lệnh phá hủy toàn bộ collection**, không chạy trong môi trường thật nếu chưa có phê duyệt, dry run, đối soát và quy trình vận hành.

Kiểm tra trước khi drop:

- Collection chỉ chứa dữ liệu thuộc đúng kỳ và đúng chính sách.
- Không có legal hold.
- Đã archive hoặc rollup nếu cần.
- Bucket đã đóng ghi hoặc late event được định tuyến nơi khác.
- Không còn API bắt buộc đọc từ collection đó.
- Backup/snapshot và khả năng restore đã có chính sách rõ.
- Tên collection được lấy từ bucket registry đã xác thực, không từ chuỗi không tin cậy.

### 8.3. Vì sao không tạo collection cho từng tenant-ngày?

10.000 tenant với 90 ngày retention có thể tạo tới **900.000 collection** nếu mỗi tenant-ngày có dữ liệu. Mỗi collection/index đều có metadata và chi phí vận hành.

Do đó, collection theo tháng **cho toàn hệ** với index tenant bên trong có thể dễ quản lý hơn; hoặc chọn cấu trúc khác theo quy mô. Cần đo quota, overhead và cách truy vấn nhiều collection trước khi chọn hạt rotation.

## 9. MongoDB TTL: xóa theo deadline của từng document

MongoDB hỗ trợ TTL index trên trường thời gian có kiểu dữ liệu phù hợp.

### 9.1. TTL theo `expiresAt`

~~~javascript
db.sensor_events.createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0 }
);
~~~

Ghi:

~~~javascript
db.sensor_events.insertOne({
  eventId: "event-9001",
  eventAt: ISODate("2026-11-10T08:15:27Z"),
  ingestedAt: ISODate("2026-11-14T08:15:30Z"),
  expiresAt: ISODate("2026-12-14T08:15:30Z"),
  temperatureC: 29.1
});
~~~

`expireAfterSeconds: 0` cho phép document đủ hạn theo thời điểm `expiresAt`. Tuy nhiên, **TTL monitor chạy bất đồng bộ**, nên document có thể vẫn tồn tại sau khi đủ hạn. API có yêu cầu không hiển thị dữ liệu hết hạn cần tự lọc thời điểm hết hạn, không dựa hoàn toàn vào việc dọn nền.

Điều kiện kỹ thuật:

- Trường TTL phải có kiểu dữ liệu được TTL index hỗ trợ, thường là BSON Date.
- Document thiếu hoặc sai kiểu trường TTL có thể không bị xóa theo chính sách mong muốn.
- Nhiều document hết hạn cùng lúc có thể tạo backlog và tải dọn dẹp.
- Timezone và cách tính `expiresAt` phải được thống nhất.
- TTL index không tự xử lý ngoại lệ giữ dữ liệu hoặc toàn bộ backup.

### 9.2. TTL cố định từ thời điểm nhận

Khi mọi record trong collection giữ 30 × 24 giờ từ `ingestedAt`:

~~~javascript
db.sensor_events.createIndex(
  { ingestedAt: 1 },
  { expireAfterSeconds: 2592000 }
);
~~~

Cách này đơn giản nhưng không linh hoạt nếu một số record giữ 7 ngày, một số 90 ngày. Có thể tách collection theo policy hoặc dùng `expiresAt` theo từng document tùy yêu cầu.

### 9.3. MongoDB time-series collection

Ví dụ:

~~~javascript
db.createCollection("device_measurements", {
  timeseries: {
    timeField: "eventAt",
    metaField: "metadata",
    granularity: "hours"
  },
  expireAfterSeconds: 2592000
});
~~~

Bucket nội bộ của time-series collection do MongoDB quản lý; TTL time-series có ngữ nghĩa expiration/cleanup theo engine và không cam kết loại vật lý từng phép đo vào đúng giây thứ 30 ngày.

**Phân biệt ba loại bucket:**

1. Bucket nội bộ của time-series engine.
2. Bucket logic trong khóa, ví dụ `(deviceId, eventDay)`.
3. Collection theo kỳ do ứng dụng tạo và drop.

Chúng phục vụ những mục tiêu liên quan nhưng không tương đương.

---

## 10. Cassandra: TTL, partition và tombstone

Bảng CQL theo ngày:

~~~sql
CREATE TABLE sensor_events_by_day (
    tenant_id text,
    device_id text,
    event_day date,
    event_at timestamp,
    event_id text,
    temperature_c double,
    PRIMARY KEY (
      (tenant_id, device_id, event_day),
      event_at,
      event_id
    )
) WITH CLUSTERING ORDER BY (
    event_at DESC,
    event_id DESC
);
~~~

### 10.1. Ghi với TTL

~~~sql
INSERT INTO sensor_events_by_day (
  tenant_id, device_id, event_day,
  event_at, event_id, temperature_c
) VALUES (
  'tenant-7', 'sensor-01', '2026-11-14',
  '2026-11-14T08:15:27Z', 'event-9001', 29.1
) USING TTL 2592000;
~~~

`2592000` giây tương đương 30 × 24 giờ. Với cách áp TTL cố định lúc ghi, một event xảy ra nhiều ngày trước nhưng vừa được gửi bù có thể được giữ thêm 30 ngày từ lúc ghi, **không nhất thiết đúng yêu cầu 30 ngày từ `eventAt`**.

### 10.2. Tombstone và chi phí dọn vật lý

Cassandra sử dụng tombstone/thông tin hết hạn để bảo đảm các replica xử lý xóa theo cơ chế của hệ. Một bản ghi hết hạn có thể không còn hiển thị trong kết quả đọc nhưng vẫn có dữ liệu trong SSTable cho đến khi compaction và điều kiện an toàn được đáp ứng.

Hệ quả:

- Quét nhiều tombstone có thể tăng p95/p99 của query.
- Compaction phải xử lý phiên bản và bản ghi cũ.
- Repair và sự đồng bộ replica liên quan tới an toàn xóa.
- Không giảm tùy tiện những thiết lập như thời gian giữ tombstone để “dọn nhanh”.

### 10.3. Xóa partition không giống DROP TABLE

~~~sql
DELETE FROM sensor_events_by_day
WHERE tenant_id = 'tenant-7'
  AND device_id = 'sensor-01'
  AND event_day = '2026-10-01';
~~~

Đây là xóa partition logic theo khóa đầy đủ. Nó có thể tạo tombstone, **không đồng nghĩa drop một table theo kỳ với chi phí metadata nhỏ**.

Thiết kế partition theo ngày hỗ trợ truy vấn và giới hạn kích thước, nhưng không tự loại bỏ chi phí purge nội bộ. Nếu thiết kế nhiều table theo kỳ để drop, phải chấp nhận thêm schema, routing, index/metadata và công việc quản trị.

### 10.4. TimeWindowCompactionStrategy

Với workload time-series append phần lớn và retention phù hợp, có thể cân nhắc TWCS:

~~~sql
ALTER TABLE sensor_events_by_day
WITH compaction = {
  'class': 'TimeWindowCompactionStrategy',
  'compaction_window_unit': 'DAYS',
  'compaction_window_size': '1'
};
~~~

TWCS có các giả định về cách ghi, timestamp và SSTable window. Dữ liệu đến muộn, ghi lại giá trị cũ, TTL hỗn hợp và sửa/xóa thường xuyên có thể làm giảm hiệu quả. **Không phải cứ có cột thời gian là TWCS luôn tốt.** Cần đánh giá theo phiên bản DBMS, chính sách repair và workload thật.

## 11. DynamoDB: TTL bất đồng bộ và table rotation

DynamoDB TTL dùng một thuộc tính **Number chứa Unix epoch time tính bằng giây**.

Ví dụ item logic:

~~~json
{
  "PK": "TENANT#7#DEVICE#sensor-01#DAY#2026-11-14",
  "SK": "EVENT#2026-11-14T08:15:27.123Z#event-9001",
  "eventId": "event-9001",
  "temperatureC": 29.1,
  "expiresAtEpoch": 1790000000
}
~~~

Con số `1790000000` **chỉ để minh họa định dạng số**; khi triển khai phải tính đúng deadline từ retention policy, không sao chép giá trị ví dụ.

Hai bước cần thiết:

1. Bật TTL cho bảng trên thuộc tính `expiresAtEpoch`.
2. Ghi đúng epoch seconds cho mỗi item.

Một thuộc tính chỉ được đặt tên `expiresAtEpoch` nhưng **chưa bật TTL** sẽ không khiến DynamoDB tự xóa.

TTL cleanup của DynamoDB là **bất đồng bộ**. Item đủ hạn có thể vẫn xuất hiện qua truy vấn cho tới khi được dọn; nếu API không cho phép trả item hết hạn, phải áp dụng kiểm tra thời gian phù hợp.

### 11.1. Bảng theo kỳ

Có thể tổ chức:

~~~text
sensor_events_2026_10
sensor_events_2026_11
sensor_events_2026_12
~~~

Khi toàn bộ bảng cũ đủ điều kiện xóa, drop table là một lựa chọn vận hành. Đánh đổi:

- Thuận tiện để dọn nguyên kỳ.
- Cần quản lý nhiều table, quyền, billing mode, quota và monitoring.
- Query xuyên kỳ phải đọc nhiều table rồi hợp nhất.
- Data đến trễ có thể phải mở lại kỳ cũ hoặc định tuyến sang late stream.
- Backup/PITR và GSI có chính sách riêng; xóa bảng không tự chứng minh mọi bản sao backup đã biến mất.

So sánh:

| Một bảng + TTL | Nhiều bảng theo kỳ |
|---|---|
| Định tuyến đơn giản | Có đơn vị drop rõ |
| Hỗ trợ deadline theo item | Chỉ drop khi mọi item đã đủ hạn |
| TTL có độ trễ dọn | Có overhead tạo/quản trị bảng |
| Query cùng một bảng | Query nhiều kỳ cần fan-out/merge |
| Có thể hỗ trợ nhiều policy bằng `expiresAt` | Cần nhất quán policy trên từng bảng |

Không có mô hình tối ưu tuyệt đối; chọn theo retention, truy vấn và chi phí vận hành.

## 12. Những hệ theo dải khóa và garbage collection

Trong các hệ như HBase hoặc Bigtable, row key có thể theo:

~~~text
sensor-01#2026-11-14T08:15:27Z#event-9001
~~~

Các row key gần nhau được lưu/định tuyến theo cơ chế dải khóa. Cần lưu ý:

- Khóa bắt đầu bằng timestamp tăng liên tục có thể tạo hotspot ở một số mô hình phân vùng.
- Giới hạn tuổi hoặc số version của cell có thể được cấu hình theo sản phẩm.
- Xóa/garbage collection vật lý không nhất thiết xảy ra ngay tại thời điểm dữ liệu hết hạn.
- Không thể giả định có lệnh “drop arbitrary key range” rẻ và nguyên tử trên mọi hệ.

Nếu dùng hash prefix để phân tán ghi, truy vấn một khoảng thời gian có thể phải quét nhiều dải khóa. Đây là đánh đổi giữa **phân phối tải** với **khả năng quản lý/đọc theo thời gian**.

---

## 13. Late arrival: điều gì xảy ra khi bucket đã đóng?

Giả sử cảm biến offline 5 ngày rồi gửi bù dữ liệu.

Nếu bucket theo `eventAt`, các event có thể phải vào bucket đã cũ. Nếu bucket đó đã `SEALED` hoặc `ARCHIVED`, ghi mới có thể phá giả định “dữ liệu không còn thay đổi”.

Các chiến lược:

| Chiến lược | Cách xử lý | Đánh đổi |
|---|---|---|
| Ghi vào bucket cũ | Chấp nhận late event theo kỳ gốc | Khó biết khi nào bucket thực sự bất biến |
| Late-arrival collection | Lưu event cũ vào nơi riêng | Query và rollup phải ghép nhiều nguồn |
| Từ chối quá muộn | Có hạn chót rõ | Có thể mất event nghiệp vụ cần thiết |
| Bucket theo ingestion | Lưu trong kỳ hệ nhận | Truy vấn theo event time phức tạp hơn |

### 13.1. Watermark

Nếu producer cam kết **đến muộn tối đa 48 giờ**, một bucket ngày 10 có thể được xem là đủ điều kiện đóng sau khi đã qua ranh giới ngày và 48 giờ tương ứng, **nếu queue/backfill/clock skew cũng đáp ứng hợp đồng**.

Watermark phải gắn với:

- Khả năng producer tuân thủ độ trễ.
- Thời gian lưu trong queue và retry.
- Đồng hồ từ nguồn.
- Luồng nhập lại dữ liệu lịch sử.
- Cách xử lý sự kiện ngoài giới hạn.

Không được nhầm:

- **Allowed lateness**: thời gian cho phép nhận event thuộc kỳ cũ.
- **Retention**: dữ liệu cần hoặc được phép giữ bao lâu.
- **Purge lag**: thời gian từ khi đủ hạn tới khi được loại theo chính sách.

Ba giá trị này có thể khác nhau.

### 13.2. Bucket sealed chưa phải bucket được xóa

Có thể kết thúc ghi bình thường nhưng vẫn đọc bucket trong 30 ngày. Bucket chỉ được purge khi retention và mọi điều kiện ngoại lệ được kiểm tra riêng.

## 14. State machine cho rotation

Một bucket có thể đi qua các trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> OPEN
    OPEN --> CLOSING
    CLOSING --> SEALED
    SEALED --> ARCHIVING
    ARCHIVING --> ARCHIVED
    ARCHIVED --> PURGE_ELIGIBLE
    PURGE_ELIGIBLE --> PURGED
    CLOSING --> OPEN: Mở lại có kiểm soát
    ARCHIVING --> ARCHIVING: Retry
    PURGE_ELIGIBLE --> SEALED: Phát hiện hold
~~~

| Trạng thái | Ý nghĩa | Hành vi |
|---|---|---|
| `OPEN` | Bucket đang nhận ghi | Ghi và đọc bình thường |
| `CLOSING` | Sắp kết thúc kỳ | Chờ queue, kiểm tra late data |
| `SEALED` | Đã đóng với luồng ghi bình thường | Cho đọc, chuẩn bị archive/rollup |
| `ARCHIVING` | Đang xuất và xác minh dữ liệu | Không purge nếu export thất bại |
| `ARCHIVED` | Archive đã được xác minh | Có thể giảm nhu cầu dữ liệu nóng |
| `PURGE_ELIGIBLE` | Đủ điều kiện chính sách | Kiểm tra lần cuối trước thao tác phá hủy |
| `PURGED` | Tác vụ purge đã được hoàn tất theo định nghĩa hệ | Ghi audit; theo dõi bản sao theo hợp đồng khác |

### 14.1. Bucket registry

Metadata:

~~~json
{
  "bucketId": "sensor_events_2026_10",
  "intervalStart": "2026-10-01T00:00:00Z",
  "intervalEnd": "2026-11-01T00:00:00Z",
  "policyVersion": 3,
  "retentionClock": "eventAt",
  "state": "SEALED",
  "legalHoldCount": 0,
  "archiveManifestId": "archive-202610",
  "archiveVerified": false,
  "pendingWrites": 0
}
~~~

Đây là registry logic do ứng dụng xây dựng, không phải object có sẵn trong mọi hệ NoSQL.

### 14.2. Điều kiện purge

~~~text
canPurge(bucket) =
  bucket.state == PURGE_ELIGIBLE
  AND bucket.intervalEnd <= retentionCutoff
  AND bucket.archiveVerifiedIfRequired
  AND bucket.legalHoldCount == 0
  AND bucket.pendingWrites == 0
  AND bucket.deletionApproved
~~~

Trong hệ thật phải kiểm tra lại metadata ở thời điểm thực hiện và có cơ chế chống worker khác cập nhật bucket đồng thời. Một snapshot registry cũ có thể không còn chính xác.

## 15. Archive trước khi xóa: hai pha có đối soát

### 15.1. Pha 1 — Sao chép và xác minh

1. Chỉ chọn bucket đã sealed và phù hợp chính sách.
2. Xuất theo snapshot hoặc phương pháp có ngữ nghĩa nhất quán rõ.
3. Ghi dữ liệu với schema version, compression, encryption và manifest.
4. Tính checksum, số record, khoảng khóa và metadata.
5. Kiểm tra định dạng và khả năng đọc/giải mã file.
6. Đối soát ID/count/checksum theo mức rủi ro.
7. Chỉ đánh dấu archive thành công sau khi kiểm chứng.

**Upload thành công chưa chứng minh archive chính xác hoặc phục hồi được.**

### 15.2. Pha 2 — Xóa nguồn

1. Kiểm tra policy, deadline, legal hold và late writes lần cuối.
2. Xác minh manifest/rollup đã hoàn thành.
3. Dừng đường đọc/ghi tới nguồn dự kiến drop.
4. Thực hiện theo quyền đã cấp, có dry run và audit.
5. Xác minh kết quả thao tác.
6. Theo dõi backup/snapshot và dọn vật lý theo chính sách riêng.

Nếu archive lỗi checksum hoặc chưa đủ record, **không purge**. Worker có thể retry mà không nhân bản sai dữ liệu, hoặc giữ trạng thái thất bại cho người vận hành xử lý.

### 15.3. Archive khác backup

Backup thường nhằm phục hồi sự cố và giữ khả năng quay lại trạng thái hệ thống trong một thời gian. Archive nhằm lưu dữ liệu theo chính sách dài hạn hoặc truy vấn hiếm. Một backup gần nhất không mặc nhiên là archive đạt yêu cầu về schema, tính toàn vẹn và khả năng tra cứu.

## 16. Rollup và việc xóa dữ liệu raw

Giả sử trong một giờ có 3.600 phép đo. Rollup cần ghi:

~~~text
count = 3600
sum = tổng giá trị
min = nhỏ nhất
max = lớn nhất
average = sum / count
~~~

Nếu event trễ hoặc bị gửi lại:

- Một event phải có ID ổn định.
- Pipeline cần idempotency hoặc có thể tính lại bucket.
- Sự kiện đến sau khi rollup đã sealed cần đường cập nhật rõ.
- Không xóa raw khi bản tổng hợp chưa được xác minh.
- Nếu thống kê cần chính xác theo đơn vị đo, phải lưu metadata/quy tắc chuyển đổi.

Rollup có thể được giữ lâu hơn raw, nhưng không mặc nhiên là dữ liệu vô danh; tổng hợp có thể vẫn liên quan đến một cá nhân hoặc đối tượng nhạy cảm.

## 17. Legal hold và yêu cầu xóa theo người dùng

### 17.1. Legal hold chặn drop nguyên bucket

Một collection tháng 10 có một record đang được yêu cầu giữ. Nếu drop toàn collection, record đó sẽ bị xóa sai.

Các lựa chọn có thể cân nhắc:

- Chuyển record cần giữ vào kho có chính sách riêng **nếu được phép**.
- Giữ cả bucket và ghi lý do, chi phí ngoại lệ.
- Thiết kế bucket theo thời hạn/policy hạt nhỏ hơn cho các kỳ sau.

Không thể áp dụng máy móc cách “copy record hold rồi drop” nếu chính sách không cho phép chuyển vị trí/định dạng hoặc bản sao.

### 17.2. Yêu cầu xóa một cá nhân trước deadline

Một người dùng yêu cầu xóa dữ liệu khi bucket tháng vẫn còn trong thời hạn giữ chung. Không thể chờ drop toàn tháng nếu quy định yêu cầu xử lý sớm.

Cần đường xóa chọn lọc và khả năng tìm mọi bản liên quan:

~~~text
userId
  ├── raw events
  ├── aggregates có liên quan
  ├── search index
  ├── cache
  ├── exports / archives
  └── backup / snapshots theo chính sách
~~~

Một hệ nên ghi nhận deletion request để khi restore backup cũ, những bản ghi đã bị xóa theo yêu cầu không được đưa trở lại phục vụ người dùng trái chính sách.

### 17.3. Xóa logic và xóa vật lý

Ba trạng thái:

1. **Expired**: đã qua deadline.
2. **Not visible**: API không còn trả dữ liệu.
3. **Physically purged**: engine và những bản sao trong phạm vi chính sách đã được loại bỏ.

Một cờ `deleted: true` hoặc kết quả query rỗng chỉ mô tả một phần trạng thái. Không được báo hoàn tất xóa vật lý nếu backup, cache hoặc archive vẫn còn nằm ngoài phạm vi đã kiểm tra.

## 18. Scheduler rotation phải an toàn

Một job định kỳ có thể chạy hàng ngày, nhưng không nên tự tính tên collection bằng cách lấy “tháng hiện tại trừ một” rồi drop.

### 18.1. Quy trình đề xuất

~~~text
1. Đọc policy và policyVersion đang hiệu lực.
2. Tính retentionCutoff trong UTC.
3. Liệt kê bucket trong registry.
4. Chọn bucket có intervalEnd <= cutoff.
5. Loại bucket chưa sealed, còn hold hoặc pending writes.
6. Kiểm tra archive/rollup đã được xác minh.
7. Xuất dry run: bucket, kỳ, size, owner, lý do đủ hạn.
8. Kiểm tra phê duyệt/điều kiện an toàn.
9. Claim bucket bằng lease hoặc conditional transition.
10. Revalidate rồi thực hiện drop/delete theo DBMS.
11. Ghi audit và đối soát kết quả.
12. Cảnh báo nếu dọn thất bại hoặc purge lag vượt ngưỡng.
~~~

### 18.2. Pseudocode

~~~python
def rotate_buckets(registry, policy, now_utc):
    cutoff = policy.retention_cutoff(now_utc)

    for bucket in registry.list_candidates(cutoff):
        if bucket.interval_end > cutoff:
            continue
        if not bucket.is_sealed:
            continue
        if bucket.has_legal_hold or bucket.has_pending_writes:
            continue
        if not bucket.archive_verified_if_required:
            continue

        # Claim phải là thao tác cạnh tranh an toàn.
        if not registry.claim_for_purge(bucket.id):
            continue

        try:
            registry.revalidate(bucket.id, policy)
            delete_or_drop_bucket(bucket)
            verify_purge_request(bucket)
            registry.mark_purged(bucket.id)
        except Exception as exc:
            registry.mark_failed(bucket.id, str(exc))
            raise
~~~

Đây là **pseudocode**, không phải script chạy production. `verify_purge_request` cần có định nghĩa phù hợp với DBMS: lệnh được chấp nhận không nhất thiết đồng nghĩa mọi bản sao vật lý đã được xóa.

### 18.3. Tránh hai worker đụng nhau

Cần lease/lock hoặc cập nhật trạng thái có điều kiện. Nếu một worker nhìn thấy bucket đủ hạn rồi worker khác đặt legal hold trước khi drop, việc kiểm tra cũ không còn đủ. **Revalidation phải nằm sát thao tác phá hủy** và có cơ chế điều phối để trạng thái không bị thay đổi đồng thời.

Retry phải idempotent ở mức mục tiêu: không drop nhầm một collection mới tái tạo cùng tên hoặc xóa bucket sai version.

## 19. Quan sát và kiểm soát chi phí

Không nên chỉ giám sát cron có exit code 0. Một rotation thành công về mặt lệnh vẫn có thể để dữ liệu quá hạn tồn tại lâu, hoặc làm query chậm vì tombstone.

| Metric | Ý nghĩa |
|---|---|
| `oldestLiveRecordAge` | Độ tuổi dữ liệu còn phục vụ |
| `purgeLagP95/P99` | Thời gian từ deadline đến dọn theo hợp đồng |
| `archiveLag` | Bucket sealed nhưng chưa archive |
| `rawBytesByAge` | Dung lượng raw theo tuổi |
| `bucketCount` | Số bucket/collection đang được quản lý |
| `largestBucketBytes` | Nhóm có nguy cơ quá lớn |
| `lateArrivalRate` | Mức lệch so với watermark |
| `legalHoldBucketCount` | Số nhóm bị giữ ngoại lệ |
| `tombstoneScan/CompactionBacklog` | Chi phí dọn ở hệ dùng tombstone |
| `readFanoutBuckets` | Số bucket phải đọc cho một API |
| `archiveVerificationFailures` | Sai checksum/thiếu dữ liệu |
| `purgeRetryRate` | Sự cố dọn dẹp |
| `restoreTestSuccess` | Bản archive có thực sự phục hồi được không |

### 19.1. Retention drift

Ví dụ:

~~~text
Policy: raw hết hạn sau 30 ngày
Observed: còn raw 36 ngày tuổi
~~~

Sự chênh lệch có thể do TTL monitor backlog, bucket còn hold, sai `expiresAt`, archive thất bại hoặc scheduler ngừng hoạt động.

Cần phân biệt **ngoại lệ hợp lệ** với **vi phạm chính sách**; một số bucket quá hạn có thể được giữ đúng vì hold, không phải lỗi tự động hóa.

### 19.2. Đo chi phí đọc xuyên bucket

Truy vấn “100 sự kiện mới nhất” có thể phải đọc bucket hôm nay, hôm qua và nhiều bucket khác khi thiết bị ít hoạt động. Nếu dùng hash bucket, một kỳ còn có nhiều partition cần merge.

Theo dõi p95/p99 **end-to-end**, số bucket được truy vấn, số hàng phải xét và độ lớn response. Rotation theo thời gian không nên làm API đọc trở nên không dự đoán được.

---

## 20. Ma trận lựa chọn chiến lược

| Tiêu chí | TTL theo item | Bucket trong khóa + TTL | Collection/table theo kỳ |
|---|---|---|---|
| Deadline riêng cho từng item | Linh hoạt | Linh hoạt nếu áp TTL phù hợp | Khó drop nếu một kỳ có nhiều deadline |
| Đơn vị dọn | Item | Item/partition tùy engine | Toàn collection/table |
| Truy vấn thời gian | Cần index phù hợp | Định tuyến theo kỳ | Định tuyến qua collection/table |
| Late arrival | Dễ ghi nếu item chưa bị từ chối | Có thể phải ghi bucket cũ | Có thể phải mở lại kỳ hoặc dùng late stream |
| Metadata quản trị | Thường ít hơn | Nhiều partition logic | Có thể nhiều schema/index/object |
| Tombstone/cleanup | Phụ thuộc DBMS | Không tự miễn tombstone | Drop có semantics riêng |
| Legal hold | Có thể quản lý từng item | Có thể chặn xóa partition | Một hold có thể chặn cả collection |
| Hạt xóa thời gian | Tùy TTL, cleanup không tức thời | Tùy TTL và khóa | Theo độ rộng kỳ |
| Truy vấn xuyên kỳ | Một query/index phù hợp | Có thể phải đọc nhiều partition | Có thể phải đọc nhiều collection |
| Chi phí triển khai | Chính sách TTL/monitor | Bucket router, partition sizing | Bucket registry, tạo/drop/index/backup |

Có thể kết hợp các phương án: TTL cho deadline cá biệt, bucket theo ngày để truy vấn, collection theo tháng để archive và drop, rollup theo giờ để giữ lịch sử dài hơn. Nhưng mỗi lớp tạo thêm chi phí vận hành; chỉ thêm khi có lợi ích rõ.

## 21. Bài tập: vòng đời dữ liệu của nền tảng IoT

Hệ thống giả định:

- 50.000 thiết bị.
- Mỗi thiết bị tạo trung bình 1 event/giây.
- 1% thiết bị có thể lên tới 100 event/giây.
- Một event logic trung bình 300 byte.
- Raw online giữ 30 ngày.
- Hourly rollup giữ 18 tháng.
- Đến trễ tối đa 48 giờ theo hợp đồng; backfill lịch sử đi luồng riêng.
- Có legal hold cho một số sự kiện.
- API đọc 100 event mới nhất hoặc event trong 24 giờ.
- Dữ liệu quá hạn không được hiển thị dù việc xóa vật lý chưa xong.

### 21.1. Yêu cầu phân tích

1. Chọn `eventAt` hay `ingestedAt` cho bucket, và trường nào quyết định expiration.
2. Tính kích thước bucket giờ/ngày của thiết bị bình thường và thiết bị tải cao.
3. Thiết kế partition key/clustering key cho Cassandra.
4. Đề xuất TTL index hoặc collection rotation cho MongoDB.
5. Giải thích DynamoDB TTL có thể trả dữ liệu đã hết hạn nếu chưa lọc.
6. Định nghĩa trạng thái của bucket và watermark 48 giờ.
7. Xử lý legal hold trước thao tác drop.
8. Xác minh rollup trước khi xóa raw.
9. Thiết kế API query nhiều bucket với thứ tự ổn định.
10. Ghi ba metric quan trọng nhất để phát hiện retention drift và chi phí cao.

### 21.2. Tính dung lượng bình quân

~~~text
50.000 thiết bị × 1 event/giây
= 50.000 event/giây

50.000 × 86.400 × 300 byte
= 1.296.000.000.000 byte/ngày
≈ 1,296 TB/ngày dữ liệu logic
~~~

Giữ 30 ngày tương đương **38,88 TB** dữ liệu logic thô trước index, replica, compression, backup và tải đỉnh. Vì vậy lựa chọn retention/bucket ảnh hưởng trực tiếp đến capacity.

### 21.3. Tính thiết bị tải đỉnh

~~~text
100 event/giây × 86.400 × 300 byte
= 2.592.000.000 byte/ngày
≈ 2,592 GB/ngày cho một thiết bị
~~~

Partition theo thiết bị/ngày có thể quá lớn cho một số workload. Bucket theo giờ giảm kích thước một nhóm nhưng không tự chia lưu lượng trong giờ; khi cần có thể thêm hash bucket, chấp nhận fan-out lúc đọc.

### 21.4. Phương án thiết kế tham khảo

~~~text
Raw:
  partition = (deviceId, eventDay)
  sort = (eventAt DESC, eventId DESC)

Policy:
  retention 30 ngày từ mốc đã được định nghĩa
  expiresAt/TTL áp dụng đúng mốc

Late arrivals:
  trong 48 giờ -> cập nhật bucket hợp lệ
  ngoài 48 giờ -> late stream hoặc quy tắc xử lý riêng

Rollup:
  (deviceId, eventHour) -> count, sum, min, max
  eventId dùng để tránh đếm trùng

Rotation:
  OPEN -> SEALED -> ROLLUP_VERIFIED
       -> ARCHIVE_VERIFIED_IF_REQUIRED
       -> PURGE_ELIGIBLE -> PURGED
~~~

Điểm cần thảo luận: nếu bucket theo `eventAt` nhưng retention theo `ingestedAt`, những event cùng bucket có thể có deadline khác nhau. Không thể suy ra thời điểm drop nguyên bucket chỉ từ tên ngày sự kiện nếu độ trễ không được giới hạn và kiểm chứng.

## 22. Những ngộ nhận phổ biến

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| “TTL xóa đúng giây hết hạn.” | Cleanup vật lý có thể bất đồng bộ. |
| “Query không thấy tức đã xóa khỏi backup.” | Trạng thái đọc và dọn vật lý các bản sao khác nhau. |
| “Partition theo ngày nghĩa là DROP partition miễn phí.” | Partition logic và table/collection là các đơn vị khác nhau. |
| “DELETE partition trong Cassandra không có tombstone.” | DELETE/TTL có thể tạo tombstone và chi phí compaction. |
| “Collection càng ngắn kỳ càng tốt.” | Nhiều collection/index gây overhead và fan-out. |
| “Đến trễ chỉ cần ghi lại bucket cũ.” | Bucket có thể đã đóng, archive hoặc purge. |
| “Retention luôn dựa trên event time.” | Có thể dựa trên ingestion, commit hoặc mốc nghiệp vụ. |
| “Rollup không còn thông tin nhạy cảm.” | Dữ liệu tổng hợp vẫn có thể thuộc chính sách bảo vệ. |
| “Upload archive thành công là có thể xóa nguồn.” | Cần xác minh schema, count, checksum và khả năng restore. |
| “Cuối tháng là drop được collection tháng trước.” | Phải xét deadline, legal hold, late arrivals và archive. |
| “Chỉ cần giảm thời gian giữ tombstone để Cassandra sạch nhanh.” | Thay đổi có thể ảnh hưởng an toàn xóa/repair, cần hiểu hệ. |
| “Xóa cả bucket xử lý được yêu cầu xóa một người.” | Có thể cần xóa chọn lọc trước deadline của cả bucket. |
| “Cron báo thành công nghĩa là retention đúng.” | Cần đo độ tuổi dữ liệu, backlog và purge lag thực tế. |
| “Backup và archive là cùng một thứ.” | Mục đích, chính sách và khả năng truy vấn thường khác nhau. |

## 23. Kết luận

**Xóa theo nhóm thời gian và luân chuyển dữ liệu** là bài toán liên kết giữa **retention policy, cách chọn khóa, khả năng xóa của DBMS và quy trình vận hành an toàn**.

Các nguyên tắc trọng tâm:

1. **Xác định chính sách trước khi chọn TTL:** dữ liệu nào, giữ đến khi nào, tính từ đồng hồ nào và có ngoại lệ nào.
2. **Chọn bucket theo workload:** tốc độ ghi, độ lệch giữa các tenant, kích thước partition, số bucket phải đọc và độ hạt xóa mong muốn.
3. **Phân biệt TTL với drop nhóm:** TTL theo item thường dọn bất đồng bộ; drop collection/table chỉ hợp lệ nếu toàn bộ dữ liệu đã đủ điều kiện.
4. **Hiểu đặc điểm DBMS:** MongoDB TTL/time-series, Cassandra tombstone/TWCS, DynamoDB TTL và table rotation có cơ chế khác nhau.
5. **Xử lý late events:** watermark, bucket sealed và luồng backfill phải được định nghĩa.
6. **Archive/rollup có đối soát:** không xóa raw trước khi dữ liệu cần giữ đã được xác minh.
7. **Tôn trọng ngoại lệ:** legal hold, yêu cầu xóa cá nhân, phân quyền và backup có thể chặn drop.
8. **Tự động hóa có kiểm soát:** registry, dry run, lease, checkpoint, audit và cơ chế retry.
9. **Đo kết quả thực:** tuổi dữ liệu, purge lag, chi phí dung lượng, tombstone và p95/p99 query xuyên bucket.

Một thiết kế vòng đời dữ liệu tốt không chỉ ghi nhanh và đọc nhanh; nó phải **giữ đúng dữ liệu cần giữ, chuyển sang đúng tầng khi dữ liệu già đi và xóa đúng dữ liệu được phép xóa bằng quy trình có thể kiểm chứng**.
