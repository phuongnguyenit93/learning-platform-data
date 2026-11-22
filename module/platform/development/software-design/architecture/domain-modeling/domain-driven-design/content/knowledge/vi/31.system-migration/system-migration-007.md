# Di chuyển lược đồ, chuyển đổi dữ liệu và kiểm tra đối soát

Di chuyển hệ thống thường không chỉ là đổi database hoặc sao chép các dòng dữ liệu từ bảng cũ sang bảng mới. Khi một tổ chức chuyển từ hệ thống legacy sang mô hình được thiết kế theo Domain-Driven Design (DDD), cấu trúc dữ liệu, ngôn ngữ nghiệp vụ, quyền sở hữu và các quy tắc bảo vệ dữ liệu có thể đều thay đổi.

Một bảng cũ có thể đang chứa nhiều khái niệm thuộc các Bounded Context khác nhau. Một cột trạng thái có thể mang nhiều ý nghĩa lịch sử. Một khóa ngoại có thể chỉ là quan hệ kỹ thuật, không phải quan hệ domain. Vì vậy, migration cần bảo toàn ý nghĩa nghiệp vụ, không chỉ bảo toàn số lượng bản ghi.

Bài học này trình bày cách lập kế hoạch di chuyển lược đồ, ánh xạ và chuyển đổi dữ liệu sang mô hình mới, nạp dữ liệu theo từng giai đoạn, kiểm tra đối soát, chuyển quyền ghi và xử lý sự cố khi cutover. Mục tiêu là giúp hệ thống chuyển đổi có kiểm soát, giữ được lịch sử cần thiết và chứng minh dữ liệu sau migration vẫn đáp ứng các invariant của domain.

## 1. Migration hệ thống gồm những gì?

Một đợt migration thường có ít nhất ba phạm vi liên quan nhưng khác nhau:

- **Schema migration:** thay đổi cấu trúc lưu trữ, chẳng hạn tạo bảng, đổi kiểu cột, thêm index, tách bảng hoặc thay đổi quan hệ.
- **Data migration:** chuyển dữ liệu hiện có sang cấu trúc mới, bao gồm làm sạch, chuẩn hóa, chuyển đổi mã và tái cấu trúc dữ liệu.
- **Application/domain migration:** thay đổi cách ứng dụng diễn giải và sở hữu dữ liệu, bao gồm Aggregate, Value Object, Bounded Context, use case và integration contract.

Ví dụ, hệ thống bán hàng cũ có bảng CUSTOMER_ORDER chứa thông tin khách hàng, địa chỉ, giá, trạng thái thanh toán và vận chuyển. Mô hình mới có thể tách trách nhiệm thành Order, Customer, Billing và Shipping. Khi đó migration phải quyết định dữ liệu nào thuộc context nào, giá trị nào là snapshot lịch sử, identity nào được giữ và invariant nào cần được kiểm tra lại.

### Migration không phải là copy database

Một thao tác copy có thể chuyển đủ số dòng nhưng vẫn làm sai nghĩa dữ liệu:

- Trạng thái PAID có thể bị ánh xạ nhầm thành payment đã settlement dù hệ thống cũ chỉ ghi nhận authorize.
- Giá tiền được lưu bằng số nguyên nhưng không rõ là đồng, xu hay đơn vị nhỏ nhất của currency.
- Ngày giao dịch được hiểu thành UTC trong khi nguồn lưu giờ địa phương.
- Một cột customer_name bị dùng như identity thay cho CustomerId.
- Những dòng mồ côi bị bỏ qua mà không có quyết định nghiệp vụ.
- Các đơn đã hoàn tất bị chuyển sang trạng thái hiện hành mà không giữ snapshot và lịch sử.

Migration thành công phải bảo toàn hoặc chuyển đổi có chủ đích cả dữ liệu lẫn semantics.

## 2. Vì sao migration cần tư duy DDD?

Trong hệ thống legacy, schema thường phản ánh lịch sử phát triển của ứng dụng, framework hoặc quyết định tối ưu database. Nó không nhất thiết phản ánh ranh giới domain hiện tại.

DDD giúp đặt các câu hỏi:

- Khái niệm nghiệp vụ nào đang được lưu?
- Context nào sở hữu dữ liệu và invariant?
- Một từ hoặc trạng thái trong hệ thống cũ có cùng nghĩa ở hệ thống mới không?
- Dữ liệu nào là reference hiện tại, dữ liệu nào là snapshot của giao dịch?
- Một bảng cũ cần được tách thành nhiều Aggregate hay nhiều Bounded Context không?
- Có cần giữ nguyên identity để đối chiếu với hệ thống ngoài không?

### Không ánh xạ một bảng thành một Aggregate theo mặc định

Một bảng legacy có thể chứa dữ liệu của nhiều Aggregate. Ngược lại, một Aggregate mới có thể được dựng từ nhiều bảng nguồn.

Ví dụ:

| Dữ liệu legacy | Khái niệm mới có thể thuộc |
|---|---|
| Order header | Order Aggregate |
| Order lines | Các entity con của Order |
| Customer name/address tại thời điểm mua | Historical snapshot trong Order |
| Customer profile hiện tại | Customer Management |
| Payment status và provider reference | Payment context |
| Shipment tracking | Shipping context |
| Product display name | Product Catalog hoặc snapshot của Order |

Bảng ánh xạ chỉ là điểm khởi đầu. Domain expert phải xác nhận semantics trước khi triển khai transform.

## 3. Xác định phạm vi và nguồn có thẩm quyền

Trước khi viết script, cần xác định rõ:

- Hệ thống nguồn và phiên bản schema nguồn.
- Hệ thống đích và phiên bản schema đích.
- Những bảng, file, stream hoặc API nằm trong phạm vi.
- Dữ liệu nào sẽ chuyển, lưu trữ lạnh, loại bỏ hoặc giữ lại ở hệ thống cũ.
- Bounded Context nào nhận ownership sau migration.
- Ai phê duyệt mapping và ngoại lệ dữ liệu.
- Mốc cutover, thời gian downtime được chấp nhận và tiêu chí rollback.
- Quy định retention, privacy và audit áp dụng.

### Xác định source of truth trong từng giai đoạn

Trong quá trình chuyển đổi, có thể có lúc cả hệ thống cũ và mới cùng tồn tại. Phải xác định hệ thống nào có quyền ghi chính thức tại từng giai đoạn.

Ví dụ:

| Giai đoạn | Nơi ghi chính thức | Nơi đọc phụ |
|---|---|---|
| Trước migration | Legacy | Không có |
| Backfill ban đầu | Legacy | New system đang nạp |
| Đồng bộ thay đổi | Legacy | New system nhận CDC/event |
| Sau cutover | New system | Legacy chỉ đọc hoặc lưu trữ |
| Sau khi kết thúc chuyển đổi | New system | Legacy được ngừng theo kế hoạch |

Không để hai hệ thống cùng ghi một business fact mà không có cơ chế phân xử. Nếu có dual-write tạm thời, phải xác định rõ mục đích, thời hạn và cách đối soát.

## 4. Khảo sát và profiling dữ liệu nguồn

Data profiling giúp biết dữ liệu thực tế khác schema hoặc tài liệu đến mức nào.

Một số phép khảo sát hữu ích:

- Tổng số bản ghi theo bảng và theo khoảng thời gian.
- Số lượng null, empty và giá trị mặc định.
- Phân bố trạng thái và enum.
- Giá trị nhỏ nhất, lớn nhất và outlier.
- Duplicate theo khóa nghiệp vụ.
- Foreign key không có bản ghi đích.
- Chuỗi sai format hoặc không chuẩn hóa.
- Ngày nằm ngoài khoảng hợp lệ.
- Tổng tiền, số lượng và số dư theo nhóm.
- Các bản ghi không thể ánh xạ sang mô hình mới.

Ví dụ, cột order_status có thể có các giá trị:

| Giá trị nguồn | Số lượng | Câu hỏi cần xác minh |
|---|---:|---|
| NEW | 18.200 | Có tương ứng Draft không? |
| CONFIRMED | 42.100 | Đã giữ hàng và chốt giá chưa? |
| PAID | 37.500 | Authorized, captured hay settled? |
| CLOSED | 11.300 | Đã giao, đã hủy hay chỉ đóng hồ sơ? |
| NULL | 420 | Thiếu dữ liệu hay mang nghĩa mặc định? |
| UNKNOWN | 17 | Có mã legacy chưa được tài liệu hóa? |

Không nên tự động ánh xạ CLOSED thành Delivered hoặc PAID thành Captured chỉ dựa trên tên. Cần tra cứu logic nguồn, lịch sử event, chứng từ và xác nhận từ chuyên gia nghiệp vụ.

### Lưu kết quả profiling

Kết quả khảo sát nên có thể chạy lại và so sánh giữa các lần. Ghi nhận thời điểm snapshot, bộ lọc, số lượng, nhóm ngoại lệ và phiên bản truy vấn. Điều này giúp biết dữ liệu nguồn đã thay đổi trong quá trình chuẩn bị migration hay chưa.

## 5. Xây dựng mapping từ schema cũ sang mô hình mới

Mapping cần mô tả ý nghĩa của từng field, quy tắc chuyển đổi và cách xử lý trường hợp không hợp lệ.

Một bảng mapping có thể gồm:

| Nguồn | Đích | Quy tắc | Xử lý ngoại lệ |
|---|---|---|---|
| order_id | OrderId | Giữ nguyên hoặc map qua ID registry | Từ chối nếu duplicate |
| customer_id | CustomerId | Giữ identity nguồn trong legacy reference | Đưa vào quarantine nếu không resolve |
| total_amount | Money.amount | Chuyển đơn vị tiền đã xác minh | Không đoán currency |
| currency_code | Money.currency | Ánh xạ mã currency chuẩn | Quarantine mã không hỗ trợ |
| order_status | OrderStatus | Bảng chuyển trạng thái theo semantics | Manual review trạng thái không rõ |
| created_time | placedAt/recordedAt | Chuyển timezone và ngữ nghĩa timestamp | Lưu raw value để truy vết |
| shipping_address | AddressSnapshot | Chuẩn hóa và giữ snapshot | Ghi nhận field thiếu |

### Mapping phải thể hiện cả semantics

Không chỉ ghi source column và target column. Cần ghi:

- Đơn vị đo và currency.
- Timezone và độ chính xác timestamp.
- Null, empty, unknown và not applicable.
- Quy tắc làm tròn.
- Enum mapping.
- Identity và quan hệ.
- Valid time và recorded time nếu cần.
- Nguồn chứng minh hoặc người phê duyệt mapping.
- Version của quy tắc chuyển đổi.

Mapping này là contract giữa domain expert, data engineer và đội phát triển.

## 6. Expand-Migrate-Contract cho schema evolution

Một cách an toàn để thay đổi schema khi hệ thống vẫn đang hoạt động là chia thành ba pha.

### Expand

Mở rộng schema để code cũ và code mới có thể cùng hoạt động:

- Thêm bảng hoặc cột mới.
- Thêm index hoặc constraint theo cách tương thích.
- Để cột mới nullable hoặc có default an toàn nếu cần.
- Triển khai code có thể đọc schema mới nhưng vẫn tương thích với dữ liệu cũ.
- Không xóa hoặc đổi nghĩa cột cũ ngay lập tức.

### Migrate

Chuyển dữ liệu và traffic từng bước:

- Backfill dữ liệu lịch sử.
- Đồng bộ thay đổi phát sinh trong lúc backfill.
- Chuyển đổi các consumer sang schema/API mới.
- Chạy reconciliation và kiểm tra invariant.
- Chuyển read path hoặc write ownership theo kế hoạch.

### Contract

Sau khi xác nhận không còn consumer phụ thuộc schema cũ:

- Ngừng ghi cột cũ.
- Xóa code tương thích tạm thời.
- Gỡ cột, bảng, index hoặc endpoint cũ.
- Xóa các adapter chỉ dùng trong giai đoạn migration.
- Cập nhật tài liệu vận hành và ownership.

Không nên contract quá sớm. Cần có khoảng quan sát và một quyết định rõ rằng rollback path không còn cần schema cũ.

### Ví dụ tiến hóa một cột

Giả sử legacy lưu full_name, mô hình mới cần first_name và last_name.

1. Thêm hai cột mới.
2. Triển khai code có thể đọc dữ liệu cũ và mới.
3. Backfill first_name/last_name từ full_name theo quy tắc đã thống nhất.
4. Đồng bộ các thay đổi mới trong thời gian backfill.
5. Chuyển read/write sang hai field mới.
6. Đối soát và quan sát.
7. Sau khi mọi consumer chuyển đổi, loại bỏ full_name nếu không còn nghĩa vụ giữ.

Việc tách tên có thể không xác định chính xác với mọi văn hóa hoặc dữ liệu legacy. Cần có chính sách cho tên một phần, tên nhiều thành phần và trường hợp không thể tự động tách.

## 7. Chọn chiến lược migration

Không có một chiến lược phù hợp cho mọi hệ thống. Quyết định phụ thuộc quy mô dữ liệu, downtime, khả năng đồng bộ, rủi ro nghiệp vụ và năng lực vận hành.

| Chiến lược | Cách làm | Phù hợp khi | Đánh đổi |
|---|---|---|---|
| Big bang | Dừng ghi, chuyển toàn bộ, xác minh rồi mở hệ thống mới | Dữ liệu nhỏ hoặc downtime chấp nhận được | Cutover có rủi ro tập trung |
| Phased migration | Chuyển theo nhóm dữ liệu hoặc capability | Có thể chia phạm vi độc lập | Cần quản lý trạng thái lai |
| Strangler migration | Từng use case chuyển sang hệ thống mới | Thay hệ thống legacy dài hạn | Cần routing và ownership rõ |
| Snapshot + CDC | Nạp snapshot rồi phát lại thay đổi | Cần downtime ngắn | Cần offset, ordering và idempotency |
| Parallel run | Hai hệ thống cùng xử lý để so sánh kết quả | Cần tăng độ tin cậy trước cutover | Tăng chi phí và phải tránh side effect trùng |

### Big bang

Big bang có thể đơn giản nếu hệ thống nhỏ, ít tích hợp và có cửa sổ downtime rõ. Tuy nhiên, cần có rehearsal, backup, tiêu chí dừng và thời gian kiểm tra đủ lớn. Không nên chọn big bang chỉ vì script migration ngắn.

### Phased migration

Có thể chuyển từng tenant, khu vực, nhóm khách hàng hoặc capability. Cần đảm bảo mỗi nhóm có identity, ownership và routing nhất quán. Không để cùng một Aggregate bị ghi ở hai hệ thống tùy theo endpoint.

### Strangler migration

Từng use case được định tuyến sang mô hình mới. Legacy tiếp tục xử lý phần chưa chuyển. Đây là cách phù hợp khi không thể dừng toàn bộ hệ thống.

Cần tránh để hai implementation cùng quyết định một invariant. Gateway/adapter chỉ định tuyến; ownership dữ liệu phải có quy tắc rõ.

## 8. Snapshot và initial backfill

Backfill là quá trình nạp dữ liệu lịch sử vào hệ thống đích.

Một quy trình thường gồm:

1. Xác định snapshot nhất quán của nguồn.
2. Ghi nhận checkpoint hoặc log position.
3. Đọc dữ liệu theo batch có giới hạn.
4. Transform qua mapping version đã phê duyệt.
5. Ghi vào staging hoặc schema đích.
6. Ghi nhận số bản ghi thành công, bị bỏ qua và lỗi.
7. Commit checkpoint sau khi batch được lưu an toàn.
8. Có thể chạy lại mà không tạo duplicate.

### Snapshot cần có mốc nhất quán

Nếu source vẫn nhận ghi trong lúc export, snapshot có thể chứa dữ liệu ở các thời điểm khác nhau. Cần dùng cơ chế snapshot nhất quán của database hoặc ghi nhận watermark/log sequence phù hợp.

Khi kết hợp snapshot với CDC, phải xác định rõ snapshot tương ứng với offset nào. Consumer sẽ phát lại các thay đổi sau offset đó. Nếu không, có thể bỏ sót hoặc áp dụng lặp thay đổi.

Chi tiết snapshot và log position phụ thuộc database hoặc CDC platform, nhưng nguyên tắc chung là phải có mốc nối giữa dữ liệu ban đầu và các thay đổi phát sinh sau đó.

## 9. Chuyển đổi dữ liệu theo batch

Không nên nạp hàng triệu bản ghi trong một transaction không giới hạn. Batch nhỏ giúp kiểm soát memory, lock, retry và tiến độ.

Một batch processor thường có:

- Batch size được cấu hình theo tải.
- Cursor hoặc keyset pagination ổn định.
- Checkpoint theo source ID hoặc offset.
- Transaction cho từng chunk phù hợp.
- Idempotent upsert.
- Metrics và log cho mỗi batch.
- Retry có giới hạn.
- Quarantine cho record không xử lý được.

Ví dụ pseudocode:

~~~java
for (SourceRecord record : source.readAfter(checkpoint, batchSize)) {
    try {
        TargetRecord target = mapper.transform(record, mappingVersion);
        targetRepository.upsertIfNewer(target);
        migrationLog.markSuccess(record.id());
    } catch (MappingException error) {
        quarantine.store(record.id(), error.code());
    }
}

checkpointStore.advanceAfterCommittedBatch();
~~~

Đây là pseudocode minh họa. Trong implementation thật, migration log, target write và checkpoint cần có transaction hoặc cơ chế resume đủ an toàn. Không được tiến checkpoint trước khi dữ liệu tương ứng đã được commit.

### Idempotency

Một batch có thể được chạy lại sau timeout hoặc process crash. Cùng một source record và cùng mapping version phải tạo ra kết quả ổn định.

Có thể dùng khóa duy nhất gồm source system, source ID và migration version. Upsert phải có semantics rõ, không ghi đè một phiên bản mới hơn bằng kết quả cũ.

Nếu transform phụ thuộc dữ liệu tham chiếu, cần version hóa cả reference snapshot hoặc lưu lại dữ liệu tham chiếu đã dùng để kết quả có thể tái lập.

## 10. Đồng bộ thay đổi phát sinh trong khi backfill

Nếu nguồn tiếp tục nhận ghi sau snapshot, hệ thống đích phải nhận các thay đổi đó.

Các cách thường dùng:

- Change Data Capture từ transaction log.
- Transactional outbox ở ứng dụng nguồn.
- Integration event đã được phát hành.
- Delta export theo watermark.
- Tạm dừng ghi trong một cửa sổ ngắn.

CDC có thể bắt thay đổi ở database level, nhưng cần tránh để schema database trở thành contract domain lâu dài. Adapter nên chuyển thay đổi thành model hoặc contract ổn định trước khi đưa vào context đích.

### Ordering và version

Với mỗi Aggregate hoặc entity nguồn, cần xác định cách phát hiện thay đổi cũ:

- Source version tăng theo từng entity.
- Sequence hoặc log offset.
- Event ID để nhận diện duplicate.
- Timestamp chỉ dùng khi semantics và độ chính xác đủ rõ.

Không nên chỉ dựa vào timestamp nếu hai thay đổi có thể cùng timestamp hoặc clock giữa hệ thống không đồng bộ.

Với snapshot event, consumer có thể áp dụng version mới hơn và bỏ qua version cũ. Với delta event, cần phát hiện gap vì bỏ qua một delta có thể làm state sai.

## 11. Cẩn trọng với dual-write

Dual-write là việc ứng dụng ghi cùng một thay đổi vào hai hệ thống hoặc hai schema.

Ví dụ:

1. Ghi Order vào legacy database.
2. Ghi Order vào new database.
3. Nếu bước thứ hai thất bại sau khi bước đầu thành công, hai hệ thống lệch nhau.

Nếu không có transaction phân tán hoặc cơ chế phối hợp đáng tin cậy, dual-write dễ tạo partial success.

### Các lựa chọn an toàn hơn

- Một hệ thống giữ quyền ghi chính thức; hệ thống kia nhận CDC/event.
- Dùng transactional outbox để ghi business change và message trong cùng local transaction.
- Consumer dùng inbox/idempotency và version để áp dụng event.
- Tạm thời serialize hoặc freeze writes trong cutover nếu cần.
- Reconciliation phát hiện chênh lệch và có quy trình sửa.

Nếu bắt buộc dual-write trong một giai đoạn, phải có record trạng thái cho từng lần ghi, retry có kiểm soát, reconciliation và ngày kết thúc. Không nên để dual-write trở thành trạng thái vĩnh viễn.

## 12. Transform dữ liệu theo semantics

Data transformation thường bao gồm nhiều loại chuyển đổi.

### Enum và trạng thái

Không ánh xạ enum chỉ bằng tên gần giống. Cần bảng mapping được domain expert phê duyệt.

Ví dụ:

| Legacy code | New concept | Điều kiện |
|---|---|---|
| NEW | Draft | Chưa xác nhận |
| CONFIRMED | Confirmed | Đã thỏa điều kiện xác nhận |
| PAID | PaymentRecorded | Phải xác minh đã capture hay settlement |
| CANCEL | Cancelled | Cần giữ reason và thời điểm |
| CLOSED | ReviewRequired | Nếu không xác định được trạng thái thực |

Giá trị unknown không nên bị map âm thầm thành trạng thái mặc định. Hãy quarantine hoặc yêu cầu manual review.

### Tiền tệ và độ chính xác

Cần xác minh:

- Currency code.
- Đơn vị nguồn là major unit hay minor unit.
- Precision và scale.
- Quy tắc rounding.
- Giá đã gồm thuế hay chưa.
- Tỷ giá và thời điểm quy đổi nếu có.

Ví dụ 1250 có thể là 1.250 VND, 12,50 USD nếu lưu cent, hoặc 1.250,00 nếu lưu major unit theo convention khác. Không thể suy luận từ con số.

### Ngày giờ và timezone

Cần phân biệt:

- LocalDate: ngày lịch không có giờ.
- LocalDateTime: ngày giờ địa phương chưa xác định timezone.
- Instant: một thời điểm tuyệt đối.
- OffsetDateTime/ZonedDateTime: có offset hoặc zone.

Không tự gắn UTC cho mọi timestamp. Hãy xác định timezone nguồn, timezone nghiệp vụ và cách xử lý DST nếu liên quan.

### Đơn vị đo và mã tham chiếu

Nếu hệ thống cũ lưu trọng lượng bằng gram và hệ thống mới dùng kilogram, phải chuyển đổi chính xác và quy định rounding. Với mã quốc gia, đơn vị đo hoặc mã sản phẩm, cần dùng danh mục có version thay vì hard-code mapping không được quản lý.

### Null, default và unknown

Null trong legacy có thể có nhiều nghĩa: chưa nhập, không áp dụng, không biết hoặc lỗi migration. Không nên thay mọi null bằng chuỗi rỗng, 0 hoặc một enum mặc định.

Hãy phân loại semantics và ghi lại quy tắc cho từng field.

## 13. Giữ identity và ánh xạ quan hệ

Identity thường là điểm khó khi chuyển từ hệ thống legacy sang mô hình mới.

Có thể:

- Giữ nguyên ID nguồn nếu format và semantics phù hợp.
- Tạo ID mới và duy trì bảng mapping source ID → target ID.
- Giữ cả legacy ID như external reference để đối soát và hỗ trợ tích hợp.
- Dùng composite key nếu identity nguồn chỉ duy nhất trong một tenant hoặc hệ thống.

Không dùng tên, email hoặc các field có thể thay đổi làm identity thay thế cho khóa nghiệp vụ.

### ID mapping registry

Một registry có thể lưu:

| Trường | Ý nghĩa |
|---|---|
| sourceSystem | Hệ thống nguồn |
| sourceType | Loại entity nguồn |
| sourceId | Identity nguồn |
| targetContext | Context đích |
| targetType | Loại entity đích |
| targetId | Identity đích |
| migrationVersion | Phiên bản migration |
| migratedAt | Thời điểm chuyển đổi |

Unique constraint nên bảo vệ cặp sourceSystem/sourceType/sourceId trong phạm vi phù hợp.

### Quan hệ không resolve được

Nếu Order tham chiếu CustomerId không tồn tại ở Customer context, không nên tự tạo một Customer giả chỉ để thỏa foreign key. Cần quyết định nghiệp vụ: giữ external reference, tạo placeholder có semantics rõ, quarantine Order hay sửa dữ liệu nguồn trước cutover.

## 14. Dựng lại Aggregate từ dữ liệu legacy

Schema mới nên phản ánh Aggregate boundary và invariant, không nhất thiết phản ánh bảng nguồn.

Ví dụ, Order Aggregate có thể gồm:

- OrderId.
- CustomerId.
- OrderLines.
- ShippingAddressSnapshot.
- PricingSnapshot.
- OrderStatus.
- PlacedAt.

Migration cần dựng Aggregate theo đúng quy tắc:

1. Gom header và line theo identity.
2. Chuyển các field thành Value Object.
3. Xác định snapshot lịch sử.
4. Ánh xạ trạng thái và lifecycle.
5. Kiểm tra invariant của Aggregate.
6. Ghi Aggregate hoặc cấu trúc persistence tương ứng.
7. Ghi nguồn và mapping version để truy vết.

Không nên gọi các behavior tạo ra side effect nghiệp vụ như gửi email, giữ hàng hoặc capture payment chỉ vì đang dựng lại Aggregate lịch sử. Data migration phải phân biệt việc khôi phục trạng thái đã xảy ra với việc thực hiện một hành động mới.

### Migration factory hoặc reconstitution

Có thể có factory chuyên biệt để tái tạo state đã tồn tại, với validation phù hợp. Factory này không nên là đường vòng cho application bình thường để bỏ qua invariant. Nếu dữ liệu legacy không thỏa invariant mới, phải có policy xử lý rõ: sửa, quarantine, giữ trạng thái legacy có đánh dấu hoặc tạo case review.

## 15. Dữ liệu không hợp lệ và quarantine

Không phải mọi record đều có thể chuyển tự động. Cần phân loại lỗi:

- **Fatal:** không thể tiếp tục migration an toàn, ví dụ identity duplicate trong phạm vi phải duy nhất.
- **Record-level:** một bản ghi lỗi nhưng các bản ghi khác có thể tiếp tục.
- **Recoverable:** lỗi có thể sửa bằng rule xác định hoặc dữ liệu tham chiếu.
- **Manual review:** cần domain expert quyết định.
- **Out of scope:** dữ liệu không còn thuộc phạm vi chuyển đổi nhưng phải có quyết định lưu trữ.

Quarantine nên lưu:

- Source identity.
- Migration run và mapping version.
- Error code.
- Field hoặc rule vi phạm.
- Timestamp.
- Cách xử lý đề xuất.
- Trạng thái review và người quyết định.

Không nên chỉ ghi log text rồi bỏ qua record. Khi cutover, cần biết rõ số lượng và giá trị nghiệp vụ của record chưa xử lý.

### Không tự sửa dữ liệu một cách âm thầm

Ví dụ, nếu postal code thiếu, không tự điền mã phổ biến nhất. Nếu currency không rõ, không gán currency mặc định. Nếu trạng thái CLOSED mơ hồ, không đoán thành Delivered.

Một default chỉ hợp lệ khi policy nghiệp vụ quy định rõ, có thể truy vết và được phê duyệt.

## 16. Bảo toàn lịch sử và thời gian

Migration có thể phải giữ nhiều loại thời gian:

- occurredAt: thời điểm sự kiện thực sự xảy ra.
- effectiveAt: thời điểm dữ kiện có hiệu lực.
- recordedAt: thời điểm hệ thống nguồn ghi nhận.
- migratedAt: thời điểm bản ghi được chuyển sang hệ thống mới.

Không nên thay recordedAt của nguồn bằng migratedAt. Hai thời điểm trả lời hai câu hỏi khác nhau.

Với giao dịch đã hoàn tất, cần giữ snapshot và chứng từ lịch sử. Ví dụ Order đã đặt có thể cần giữ tên sản phẩm, giá, currency và địa chỉ tại thời điểm đặt, dù các dữ liệu hiện tại đã thay đổi.

Nếu hệ thống mới hỗ trợ bitemporal data, cần xác định cách nạp valid time và transaction time. Không nên tạo lịch sử giả bằng cách gán migratedAt thành effectiveAt.

### Event history và audit

Nếu legacy có audit log hoặc event history, cần quyết định:

- Chuyển toàn bộ event hay chỉ snapshot hiện tại?
- Event có đủ identity và thứ tự không?
- Có thể replay an toàn không?
- Có event nào chỉ là technical log, không phải domain event?
- Dữ liệu nhạy cảm trong lịch sử có retention riêng không?

Không nên biến mọi row change trong database thành Domain Event. Chỉ những fact có ý nghĩa nghiệp vụ mới nên đi vào event model.

## 17. Reconciliation là gì và vì sao cần thiết?

Reconciliation là quá trình đối chiếu dữ liệu nguồn và dữ liệu đích để xác nhận migration đã bảo toàn đúng thông tin và ý nghĩa.

Chỉ kiểm tra số dòng là chưa đủ. Hai hệ thống có thể có cùng số bản ghi nhưng khác identity, amount, trạng thái hoặc quan hệ.

Một bộ reconciliation tốt kiểm tra nhiều lớp:

1. **Completeness:** bản ghi cần chuyển có đầy đủ ở đích không?
2. **Uniqueness:** có duplicate hoặc identity collision không?
3. **Referential integrity:** các reference có resolve đúng không?
4. **Semantic correctness:** giá trị sau transform có đúng nghĩa không?
5. **Aggregate invariants:** state mới có hợp lệ không?
6. **Financial/business totals:** tổng tiền, số lượng, số dư có khớp theo quy tắc không?
7. **Temporal correctness:** timestamp và khoảng hiệu lực có được giữ đúng không?
8. **Operational readiness:** dữ liệu mới có được consumer đọc và xử lý đúng không?

### Reconciliation theo nhiều cấp

| Cấp | Ví dụ kiểm tra |
|---|---|
| Dataset | Tổng số record nguồn/đích |
| Partition | Số record theo ngày, tenant hoặc trạng thái |
| Aggregate | Tổng tiền và số line của từng Order |
| Field | So sánh từng giá trị sau normalization |
| Relationship | CustomerId, ProductId và các reference |
| Business invariant | Không có payment refund vượt số tiền capture |
| Event stream | Không mất sequence hoặc version cần thiết |

## 18. Reconciliation bằng count, sum và checksum

Các phép đối soát tổng hợp giúp phát hiện sai lệch nhanh:

- COUNT(*) theo nhóm.
- SUM(amount) theo currency và kỳ.
- SUM(quantity) theo warehouse/product.
- MIN/MAX timestamp.
- Số lượng null hoặc unknown status.
- Số lượng duplicate key.
- Checksum/hash trên dữ liệu canonicalized.

Ví dụ, tổng tiền phải nhóm theo currency. Cộng 100 USD và 100 EUR thành 200 mà không quy đổi là sai về nghiệp vụ.

Checksum chỉ hữu ích khi hai phía dùng cùng canonicalization, cùng thứ tự và cùng field set. Hash giống nhau không chứng minh mọi invariant domain đều đúng; hash khác nhau cũng cần drill down để tìm record gây lệch.

### So sánh theo key

Khi phát hiện chênh lệch, so sánh theo business identity hoặc mapping registry:

- Record chỉ có ở nguồn.
- Record chỉ có ở đích.
- Record có ở cả hai nhưng field khác.
- Record có reference không resolve.
- Record được quarantine.

Một báo cáo reconciliation cần cung cấp số lượng và danh sách identity để có thể điều tra.

## 19. Reconciliation theo invariant nghiệp vụ

Các kiểm tra domain thường quan trọng hơn kiểm tra cấu trúc.

Ví dụ:

- Mỗi Order Confirmed phải có ít nhất một OrderLine.
- Tổng line amount cộng discount/tax phải khớp total theo rounding policy.
- Payment đã refund không vượt captured amount.
- Reservation không vượt on-hand inventory.
- Một Invoice chỉ thuộc một Order theo quy tắc domain.
- Mọi shipment phải tham chiếu một Order hợp lệ.
- Một Aggregate không có hai child cùng identity nếu quy tắc cấm.

Các invariant phải được diễn đạt bằng ngôn ngữ của context sở hữu. Không gom mọi kiểm tra vào một query SQL tổng quát nếu nó không thể thể hiện semantics.

Nếu invariant bị vi phạm trong dữ liệu lịch sử, cần quyết định record được sửa, quarantine, giữ dưới dạng legacy exception hay cần một adjustment nghiệp vụ. Không nên bỏ qua chỉ vì dữ liệu đã tồn tại lâu.

## 20. Đối soát thay đổi trong lúc migration

Snapshot ban đầu không bao gồm những thay đổi xảy ra sau mốc snapshot. Vì vậy cần đối soát cả phần delta.

Một cách làm:

1. Chọn consistent snapshot và ghi source offset/watermark.
2. Backfill snapshot vào đích.
3. Consume CDC/event bắt đầu từ offset tương ứng.
4. Áp dụng thay đổi theo version hoặc sequence.
5. Đo consumer lag.
6. Chờ đích bắt kịp nguồn.
7. So sánh delta count và trạng thái theo partition.
8. Chốt watermark cuối trước cutover.

Cần xử lý duplicate và out-of-order. Nếu consumer nhận version 12 rồi version 11, snapshot projection có thể bỏ qua version 11. Với delta event, phải phát hiện gap và replay hoặc lấy snapshot mới.

### Watermark không chỉ là timestamp

Watermark nên dùng một mốc có semantics rõ như log sequence number, offset hoặc version. Timestamp có thể trùng hoặc bị ảnh hưởng bởi clock skew, nên không phải lúc nào cũng đủ để xác định chính xác ranh giới thay đổi.

## 21. Cutover: chuyển quyền ghi sang hệ thống mới

Cutover là thời điểm chuyển traffic hoặc ownership từ hệ thống cũ sang hệ thống mới.

Một checklist cutover thường gồm:

1. Xác nhận backup và restore đã được thử.
2. Xác nhận mapping version và migration artifact đã được khóa.
3. Xác nhận backfill hoàn tất.
4. Xác nhận CDC/event lag nằm trong ngưỡng cho phép.
5. Thông báo và mở maintenance/read-only window nếu cần.
6. Ngừng nhận hoặc tạm giữ write command ở nguồn theo kế hoạch.
7. Drain queue và ghi final watermark.
8. Áp dụng delta cuối cùng.
9. Chạy reconciliation cuối.
10. Kiểm tra invariant và smoke test trên hệ thống mới.
11. Chuyển routing và quyền ghi sang owner mới.
12. Theo dõi metric và lỗi trong giai đoạn hypercare.
13. Chỉ contract schema cũ sau khi đủ điều kiện.

### Cutover theo tenant hoặc cohort

Nếu migration theo từng nhóm, cần có routing rõ theo tenant/customer/order partition. Một identity phải luôn được định tuyến đến đúng nơi có quyền ghi.

Tránh trường hợp cùng một customer có một số request ghi vào legacy, số khác vào hệ thống mới vì cache hoặc routing không đồng nhất.

### Tiêu chí Go/No-Go

Trước cutover cần có ngưỡng định lượng đã thống nhất:

- Tỷ lệ record được migrate.
- Số lượng và giá trị record quarantine.
- Reconciliation mismatch còn lại.
- CDC lag.
- Error rate và latency.
- Kết quả smoke test.
- Khả năng restore/forward recovery.
- Người có quyền quyết định Go/No-Go.

Không quyết định chỉ dựa trên cảm giác rằng migration gần xong.

## 22. Rollback và forward recovery

Rollback ứng dụng và rollback dữ liệu là hai việc khác nhau.

Nếu hệ thống mới chưa nhận write và chưa tạo side effect, có thể chuyển routing về legacy tương đối đơn giản. Nhưng sau khi hệ thống mới đã nhận giao dịch, quay lại legacy có thể làm mất dữ liệu mới hoặc tạo hai nguồn sự thật.

### Trước cutover

Có thể hủy migration run, sửa mapping và chạy lại từ checkpoint hoặc snapshot mới nếu dữ liệu đích chưa được công bố.

### Sau cutover nhưng trước write mới

Có thể quay routing về nguồn nếu schema và dữ liệu vẫn đồng bộ, đồng thời xác nhận không có request đang xử lý.

### Sau khi hệ thống mới đã nhận write

Cần có chiến lược rõ:

- Reverse replication có kiểm soát nếu mô hình cho phép.
- Export các thay đổi mới về legacy qua mapping ngược đã kiểm thử.
- Giữ write freeze trong lúc xác định chênh lệch.
- Forward recovery bằng cách sửa lỗi ở hệ thống mới.
- Compensation cho side effect đã xảy ra.
- Manual reconciliation nếu không thể tự động đảo.

Mapping ngược không phải lúc nào cũng tồn tại. Nếu mô hình mới giàu semantics hơn legacy, có thể không thể biểu diễn đầy đủ thay đổi trong schema cũ.

### Ưu tiên forward recovery khi rollback không an toàn

Một khi hệ thống mới đã là nơi phát sinh giao dịch chính thức, sửa lỗi tiến về phía trước có thể an toàn hơn đưa dữ liệu quay lại mô hình cũ. Quyết định phải được chuẩn bị trước cutover, không chờ sự cố mới nghĩ đến.

## 23. Ví dụ: chuyển Order từ schema legacy sang Aggregate mới

Giả sử legacy có hai bảng:

~~~sql
CREATE TABLE legacy_order (
    order_no VARCHAR(40) PRIMARY KEY,
    customer_no VARCHAR(40),
    status VARCHAR(20),
    total_amount BIGINT,
    currency_code CHAR(3),
    created_at TIMESTAMP,
    ship_to TEXT
);

CREATE TABLE legacy_order_line (
    order_no VARCHAR(40),
    line_no INTEGER,
    product_no VARCHAR(40),
    quantity INTEGER,
    unit_price BIGINT
);
~~~

Mô hình mới có thể gồm Order Aggregate, OrderLine và các Value Object. Bảng legacy không quyết định trực tiếp cấu trúc Aggregate.

Mapping cần làm rõ:

| Field legacy | Khái niệm mới | Cần xác minh |
|---|---|---|
| order_no | OrderId hoặc legacy reference | Identity có duy nhất toàn hệ thống không? |
| customer_no | CustomerId | Có mapping sang Customer context không? |
| status | OrderStatus | Semantics từng trạng thái là gì? |
| total_amount | Money | Đơn vị minor/major unit nào? |
| currency_code | Currency | Có mã nào chưa hỗ trợ không? |
| created_at | placedAt hoặc recordedAt | Timestamp có timezone nào? |
| ship_to | AddressSnapshot | Có thể parse và giữ raw value không? |
| quantity | Quantity | Có giá trị 0/âm không? |
| unit_price | Money snapshot | Precision và currency có nhất quán không? |

Một transform có thể diễn đạt như sau:

~~~java
Order migrate(LegacyOrder source, List<LegacyOrderLine> lines) {
    OrderId orderId = orderIdMapper.map(source.orderNo());
    CustomerId customerId = customerIdMapper.resolve(source.customerNo());

    Currency currency = currencyMapper.map(source.currencyCode());
    Money total = moneyMapper.fromLegacy(
            source.totalAmount(),
            currency
    );

    List<OrderLine> orderLines = lines.stream()
            .map(line -> new OrderLine(
                    productIdMapper.map(line.productNo()),
                    new Quantity(line.quantity()),
                    moneyMapper.fromLegacy(line.unitPrice(), currency)
            ))
            .toList();

    return Order.reconstitute(
            orderId,
            customerId,
            orderLines,
            total,
            addressMapper.toSnapshot(source.shipTo()),
            orderStatusMapper.map(source.status()),
            timestampMapper.toInstant(source.createdAt())
    );
}
~~~

Đây là ví dụ khái niệm. Implementation cần xử lý lỗi mapping, null, duplicate, version, snapshot và invariant. Reconstitute là factory tái tạo dữ liệu đã tồn tại, không tự động phát các side effect như confirm order hoặc reserve stock.

### Kiểm tra sau khi chuyển

Với mỗi Order:

- Tổng số line khớp nguồn.
- Mỗi line có product reference hợp lệ hoặc trạng thái ngoại lệ được ghi nhận.
- Quantity dương.
- Currency nhất quán theo policy.
- Tổng tiền khớp phép tính theo rounding rule.
- Status mapping hợp lệ.
- Timestamp giữ đúng semantics.
- Customer reference có thể truy vết về source ID.

## 24. Kiểm thử migration trước khi chạy production

Migration cần được kiểm thử như một phần mềm có input, transform, state và failure mode.

Các loại test:

| Loại test | Mục tiêu |
|---|---|
| Mapping unit test | Field được chuyển đúng semantics |
| Boundary test | Null, empty, max, negative, timestamp biên |
| Golden dataset test | Bộ dữ liệu mẫu có kết quả đích đã xác nhận |
| Property test | Tính chất tổng quát của transform |
| Idempotency test | Chạy lại không tạo duplicate hoặc làm sai state |
| Resume test | Process restart từ checkpoint không bỏ sót |
| Reconciliation test | Báo cáo mismatch chính xác |
| Volume/performance test | Batch xử lý đạt throughput và lock budget |
| CDC ordering test | Duplicate, out-of-order và gap được xử lý |
| Cutover rehearsal | Thực hiện đầy đủ runbook trong môi trường tương đương |
| Recovery test | Restore, rollback hoặc forward recovery hoạt động |

### Golden dataset

Tạo một tập record đại diện gồm cả trường hợp bình thường và khó:

- Đơn có nhiều line.
- Đơn không có customer reference.
- Currency khác nhau.
- Timestamp ở timezone khác nhau.
- Status legacy đã ngừng dùng.
- Duplicate identity.
- Record thiếu field bắt buộc.
- Giao dịch đã hoàn tất có snapshot lịch sử.
- Bản ghi có audit/correction.

Domain expert xác nhận kết quả mong đợi của golden dataset. Khi mapping thay đổi, chạy lại để phát hiện regression.

## 25. Bảo mật, privacy và audit trong migration

Dữ liệu migration có thể chứa thông tin cá nhân, payment reference hoặc dữ liệu nhạy cảm. Cần áp dụng nguyên tắc tối thiểu hóa:

- Chỉ đọc và chuyển dữ liệu nằm trong phạm vi.
- Mã hóa dữ liệu khi truyền và khi lưu staging.
- Giới hạn quyền truy cập theo vai trò.
- Không ghi payload nhạy cảm vào log.
- Có retention cho staging, file export và quarantine.
- Audit ai chạy migration, khi nào, với mapping version nào.
- Có kiểm soát xóa hoặc ẩn dữ liệu theo policy.
- Kiểm tra backup và restore theo yêu cầu bảo vệ dữ liệu.

Không nên để file CSV chứa dữ liệu khách hàng nằm lại vô thời hạn trên máy chạy migration.

## 26. Observability và runbook cho migration

Một migration cần có dashboard hoặc báo cáo vận hành:

| Metric | Ý nghĩa |
|---|---|
| Source records scanned | Số record nguồn đã đọc |
| Target records written | Số record đích đã ghi |
| Transform success/failure | Kết quả transform |
| Quarantine count | Số record cần review |
| Batch throughput | Số record xử lý mỗi giây/phút |
| Checkpoint position | Tiến độ có thể resume |
| CDC lag | Khoảng trễ đồng bộ thay đổi |
| Duplicate/old event count | Event lặp hoặc cũ |
| Reconciliation mismatch | Sai lệch giữa nguồn và đích |
| Cutover readiness | Mức đáp ứng tiêu chí Go/No-Go |

Runbook nên chỉ rõ:

- Ai có quyền bắt đầu/dừng migration.
- Cách xác định migration run và checkpoint.
- Khi nào retry một batch.
- Khi nào quarantine hoặc dừng toàn bộ.
- Cách chạy reconciliation.
- Cách xử lý record ngoại lệ.
- Ai quyết định cutover.
- Điều kiện rollback hoặc forward recovery.
- Cách liên hệ owner của từng Bounded Context.

Không chạy lại toàn bộ job chỉ vì một batch thất bại nếu checkpoint và idempotency cho phép resume an toàn.

## 27. Quy trình migration theo từng giai đoạn

Một quy trình có thể được tổ chức như sau:

1. **Discovery:** xác định hệ thống nguồn, đích, data owner và phạm vi.
2. **Profiling:** khảo sát chất lượng, phân bố và ngoại lệ dữ liệu.
3. **Domain mapping:** thống nhất semantics, identity, invariant và lịch sử.
4. **Schema expand:** tạo cấu trúc mới tương thích với hệ thống đang chạy.
5. **Migration tooling:** xây transform, checkpoint, quarantine và audit.
6. **Dry run:** chạy trên snapshot đại diện và đo throughput.
7. **Initial backfill:** nạp dữ liệu lịch sử.
8. **Change capture:** đồng bộ delta sau snapshot.
9. **Reconciliation:** kiểm tra completeness, semantics và invariant.
10. **Cutover rehearsal:** diễn tập routing, write freeze và recovery.
11. **Cutover:** chuyển quyền ghi và traffic theo cohort hoặc toàn hệ thống.
12. **Hypercare:** theo dõi lỗi, latency, mismatch và workflow.
13. **Contract:** loại bỏ schema và adapter cũ khi đã an toàn.
14. **Closure:** lưu báo cáo, mapping version, audit và quyết định ngoại lệ.

Mỗi giai đoạn cần có exit criteria rõ. Không chuyển sang giai đoạn tiếp theo chỉ vì script đã chạy hết.

## 28. Checklist di chuyển lược đồ và dữ liệu

Trước khi cutover, hãy kiểm tra:

- Source và target schema đã được version hóa chưa?
- Ownership của từng business fact đã rõ chưa?
- Mapping có mô tả semantics chứ không chỉ tên cột không?
- Identity và mapping registry có unique constraint chưa?
- Currency, unit, timezone và precision đã xác minh chưa?
- Null, empty, unknown và default có policy rõ chưa?
- Enum mapping có được domain expert phê duyệt chưa?
- Aggregate được dựng lại theo invariant mới chưa?
- Historical snapshot và audit có được giữ đúng không?
- Backfill có consistent snapshot và checkpoint không?
- CDC/delta có offset, ordering, version và idempotency không?
- Dual-write có tránh được hoặc có thời hạn và reconciliation không?
- Quarantine có lưu source identity và reason code không?
- Reconciliation có kiểm tra count, sum, reference và invariant không?
- Cutover có final watermark và write ownership rõ không?
- Rollback/forward recovery đã được diễn tập chưa?
- Backup/restore đã được thử trong môi trường tương đương chưa?
- Privacy, encryption và retention được áp dụng chưa?
- Dashboard và runbook đã sẵn sàng chưa?
- Go/No-Go criteria và người phê duyệt đã xác định chưa?
- Legacy schema chỉ bị contract sau khi consumer đã chuyển hết chưa?

## 29. Kết luận

Di chuyển lược đồ và dữ liệu trong một hệ thống DDD là quá trình chuyển đổi cả cấu trúc lẫn ý nghĩa nghiệp vụ. Một migration chỉ copy đủ record chưa chứng minh hệ thống mới đúng. Cần xác định ownership, mapping semantics, identity, thời gian, snapshot và invariant; sau đó backfill và đồng bộ thay đổi bằng quy trình có checkpoint, idempotency và khả năng resume.

Reconciliation phải kiểm tra nhiều cấp: completeness, uniqueness, relationship, business totals, temporal correctness và invariant của Aggregate. Cutover cần có watermark, tiêu chí Go/No-Go, quyền ghi rõ ràng và kế hoạch recovery. Sau khi hệ thống mới ổn định, mới loại bỏ schema và đường tích hợp cũ.

Khi migration được thiết kế như một quy trình nghiệp vụ có thể quan sát, kiểm chứng và truy vết, đội ngũ có thể chuyển đổi từng phần mà vẫn giữ được tính đúng đắn của dữ liệu và quyền sở hữu rõ ràng giữa các Bounded Context.
