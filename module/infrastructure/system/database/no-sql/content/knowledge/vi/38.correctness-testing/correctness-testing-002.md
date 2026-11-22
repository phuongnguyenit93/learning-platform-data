# Thiết kế bộ dữ liệu tối thiểu, dữ liệu biên và dữ liệu không hợp lệ

Một dịch vụ Java sử dụng NoSQL có endpoint tìm đơn đặt chỗ theo khách hàng, cập nhật trạng thái booking và trả dữ liệu từ các bản sao tìm kiếm. Kiểm thử với một booking có đầy đủ trường, mã ngắn, thời gian bình thường và trạng thái hợp lệ có thể cho kết quả xanh. Nhưng hệ thống thực tế còn gặp **booking cùng mã ở hai tenant**, **hai bản ghi trùng thời điểm sắp xếp**, **một trường vắng mặt khác với giá trị null**, **số tiền vượt kiểu lưu trữ**, **bản ghi đã hết TTL**, **sự kiện CDC đến sai thứ tự** hoặc **hai writer cùng cập nhật một phiên bản**.

Nếu không chuẩn bị dữ liệu nhằm kích hoạt những khác biệt này, test có thể thành công ngay cả khi ứng dụng có lỗi nghiêm trọng. Ngược lại, sao chép hàng triệu bản ghi production vào môi trường kiểm thử không nhất thiết giúp tìm được lỗi; còn tạo rủi ro quyền riêng tư, hiệu năng và khả năng tái hiện.

Bài thuộc **Database No SQL → Kiểm thử tính đúng**, hướng dẫn thiết kế ba lớp dữ liệu:

1. **Dữ liệu tối thiểu:** số ít thực thể, quan hệ và sự kiện nhất có thể nhưng vẫn đủ chứng minh một hành vi/bất biến.
2. **Dữ liệu biên:** các giá trị ở, trước và sau ranh giới của kiểu, miền nghiệp vụ, khóa, thời gian, kích thước, phân trang, partition và mức nhất quán.
3. **Dữ liệu không hợp lệ:** input hoặc trạng thái sai schema, sai quyền, sai mối quan hệ, sai thứ tự phiên bản, sai định dạng hay vi phạm bất biến; test phải kiểm tra hệ **từ chối đúng và không tạo tác dụng phụ**.

> **Nguyên tắc:** Một fixture tốt không đo bằng số dòng mà bằng khả năng **phân biệt thực thi đúng với một lỗi cụ thể**. Mỗi trường hợp cần nêu: **mục tiêu**, **trạng thái ban đầu**, **thao tác**, **kết quả mong đợi**, **bằng chứng/assertion** và **cách reset để chạy lại**. Dữ liệu “đúng cú pháp” chưa chắc “đúng nghiệp vụ”, và kết quả “không có exception” chưa chắc “đúng”.

> **Phạm vi:** Ví dụ dùng Java 21 và JUnit Jupiter cùng các mô hình document, key–value, wide-column, graph. Từng engine như MongoDB, DynamoDB, Cassandra, HBase, Redis hoặc Neo4j có semantics khác nhau về kiểu, chỉ mục, transaction, consistency, TTL và index freshness. Các ví dụ JSON/CQL/Cypher và dữ liệu minh họa không mặc nhiên là script production; phải đối chiếu driver và engine version trước khi thực hiện.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

- Từ một yêu cầu nghiệp vụ, rút ra các **bất biến có thể assert**.
- Tạo một fixture tối thiểu thực sự bắt được lỗi sai tenant, truy vấn thiếu điều kiện, sorting, update phiên bản hoặc delete.
- Phân vùng giá trị thành **hợp lệ điển hình, hợp lệ sát biên, không hợp lệ sát biên và không hợp lệ rõ ràng**.
- Phân biệt **missing, explicit null, empty, wrong type và expired/deleted** trong một mô hình NoSQL.
- Chọn dữ liệu đủ kích hoạt partition, index, fan-out, pagination, cache/CDC và concurrency.
- Dùng seed, frozen clock, operation IDs, cleanup và version pinning để kiểm thử có thể chạy lại.
- Biết khi nào một bộ vài bản ghi là đủ và khi nào phải thêm **shape/scale/topology fixture**.
- Không dùng dữ liệu cá nhân thật hoặc secrets làm fixtures mặc định.

## 2. Dữ liệu kiểm thử bắt đầu từ hợp đồng, không từ random generator

Giả sử một API có bốn hành vi:

- Tìm booking theo tenant + bookingId.
- Liệt kê booking của một customer theo createdAt giảm dần, bookingId làm tie-breaker.
- Đổi trạng thái với expectedVersion.
- Không hiển thị booking đã bị xóa hoặc không thuộc quyền.

Một câu kiểm thử như “truy vấn trả về hai dòng” chưa đủ. Hai dòng đó có thể thuộc nhầm tenant hoặc sai thứ tự.

**Test oracle** phải mô tả sự thật mong đợi. Ví dụ:

- GET(T-A, B-001) trả đúng booking T-A/B-001, không phải T-B/B-001.
- List(T-A, C-9, limit=2) trả B-003 rồi B-002 với sort đã định, không lặp và không thiếu key khi sang trang.
- Conditional update expectedVersion=4 chỉ thành công khi version hiện tại là 4.
- Delete ở source version 7 khiến event upsert version 6 đến muộn không được hồi sinh record.

### 2.1. Từ yêu cầu đến dữ liệu và assertion

| Yêu cầu | Lỗi cần bắt | Fixture tối thiểu | Assertion chính |
| --- | --- | --- | --- |
| Không lộ dữ liệu tenant khác | Bỏ tenantId trong filter | Hai tenants cùng bookingId | Identity gồm tenantId chính xác |
| Sắp xếp ổn định | Chỉ sort createdAt | Ba booking có timestamp trùng | Thứ tự key cụ thể qua hai pages |
| Cập nhật có điều kiện | Lost update | Một record + hai writer cùng version | Một commit, một conflict |
| Không hồi sinh delete | Backfill ghi sau DELETE | Upsert v6 và delete v7 | Record tiếp tục bị xóa |
| Không vượt giới hạn trang | Không kiểm tra limit | 101 records hoặc limit=101 | Reject/cap theo hợp đồng |
| Đọc đúng kiểu | String bị coi như long | Một document kiểu string legacy | Decode/validation như contract |
| TTL | Dùng sai ranh giới | Bản ghi ở trước/sau expiry | Visibility đúng theo clock/engine |
| GSI/search eventual | Assert strong consistency giả | Source v5, index v4 | Test theo freshness contract |

### 2.2. “Tối thiểu” phụ thuộc lỗi cần phát hiện

Để kiểm tra point lookup, hai documents là đủ nếu một document thuộc tenant khác nhưng có cùng bookingId. Để kiểm tra pagination với page size=2, cần ít nhất ba records phù hợp. Để kiểm tra hot partition, 3 records **không đủ**: phải tái tạo phân phối keys, kích thước và tải gây hotspot.

Không dùng một fixture “chuẩn” cho mọi bài test. **Mỗi test có một tập phân biệt tối thiểu**.

## 3. Ba lớp dữ liệu và cách phối hợp

### 3.1. Dữ liệu tối thiểu — Minimal Distinguishing Fixture

Mục đích:
- Nói rõ giả thuyết.
- Tránh nhiễu.
- Cho test thất bại khi code có lỗi.
- Dễ đọc và sửa.
- Dễ tái hiện trong CI.

Ví dụ muốn phát hiện thiếu điều kiện tenant:

~~~~json
[
  {"tenantId":"T-A","bookingId":"B-001","status":"CONFIRMED"},
  {"tenantId":"T-B","bookingId":"B-001","status":"CANCELLED"}
]
~~~~

Một record duy nhất không thể phát hiện lỗi query chỉ theo bookingId nếu ID tình cờ không đụng nhau.

### 3.2. Dữ liệu biên — Boundary Fixture

Mục đích kiểm tra ranh giới:
- Độ dài 0/1/max/max+1.
- Số -1/0/1/long max/overflow.
- Timestamp ngay trước/bằng/ngay sau thời hạn.
- Page size nhỏ nhất/lớn nhất.
- Array/partition/document vừa đủ/đã vượt limit.
- Version 0/1/max hợp lệ.
- Missing/null/empty.
- Đồng thời hai thao tác trên cùng key.

### 3.3. Dữ liệu không hợp lệ — Invalid/Adversarial Fixture

Mục đích kiểm tra:
- Parse bị từ chối.
- Domain validation bị từ chối.
- Authorization chặn đúng.
- Conditional write không đổi state.
- NoSQL driver không nhận raw operator ngoài hợp đồng.
- Error không làm lộ dữ liệu nội bộ.
- Không gây side effects khi thao tác thất bại.

### 3.4. Kết hợp ba lớp không đồng nghĩa mọi test đều nhiều dữ liệu

Dùng:
- Unit tests nhỏ với 2–5 records.
- Boundary/negative tests theo bảng cases.
- Integration tests có database thật.
- Concurrency tests với event ordering được kiểm soát.
- Scale tests riêng có kích thước và skew đại diện.

Một test có 200.000 records để kiểm tra enum parsing là không cần thiết. Một test 2 records để kiểm tra compaction trên wide partitions cũng không thực tế.

## 4. Bộ dữ liệu nền minh họa cho booking

Định nghĩa business record:

| Field | Kiểu miền | Bắt buộc | Ý nghĩa |
| --- | --- | --- | --- |
| tenantId | String canonical | Có | Phạm vi sở hữu |
| bookingId | String canonical | Có | Định danh trong tenant |
| customerId | String canonical | Có | Chủ booking |
| propertyId | String canonical | Có | Nguồn đặt chỗ |
| status | Enum | Có | PENDING / CONFIRMED / CANCELLED |
| amountMinor | Long | Có | Tiền theo đơn vị nhỏ |
| createdAt | Instant | Có | Thời điểm tạo |
| version | Long không âm | Có | Optimistic version |
| deleted | Boolean | Có | Logical deletion flag |
| expiresAt | Instant hoặc null | Tùy model | Absolute expiry |
| items | List có giới hạn | Có theo contract | Các dòng chi tiết |
| schemaVersion | Integer | Có | Phiên bản định dạng |

### 4.1. Fixture hợp lệ điển hình

~~~~json
{
  "tenantId":"T-A",
  "bookingId":"B-001",
  "customerId":"C-9",
  "propertyId":"P-3",
  "status":"CONFIRMED",
  "amountMinor":1800000,
  "createdAt":"2026-11-14T09:00:00Z",
  "version":4,
  "deleted":false,
  "expiresAt":null,
  "items":[
    {"itemNo":1,"description":"NIGHT","amountMinor":1600000},
    {"itemNo":2,"description":"FEE","amountMinor":200000}
  ],
  "schemaVersion":3
}
~~~~

Đây là JSON minh họa API/fixture; khi ghi MongoDB, createdAt nên được chuyển sang BSON Date nếu schema yêu cầu. Khi đọc DynamoDB hoặc Cassandra, cần mapping đúng kiểu riêng của engine.

### 4.2. Bộ tối thiểu cho ba truy vấn

~~~~text
T-A/C-9/B-001 createdAt=2026-11-14T09:00:00Z version=4
T-A/C-9/B-002 createdAt=2026-11-14T09:00:00Z version=1
T-A/C-9/B-003 createdAt=2026-11-14T10:00:00Z version=2
T-B/C-9/B-001 createdAt=2026-11-14T11:00:00Z version=7
~~~~

Dữ liệu này kiểm tra được:
- Tenant scope với bookingId trùng.
- Sort createdAt giảm dần.
- Tie-breaker bookingId.
- Pagination limit=2.
- Không trả booking tenant B.

Với sort createdAt DESC, bookingId ASC, kết quả của T-A/C-9 phải là:
- B-003.
- B-001.
- B-002.

Nếu sort tie-breaker là DESC thì thứ tự hai booking cùng thời điểm phải đổi tương ứng. **Expected output luôn phải gắn với sort contract thực tế.**

## 5. Tối giản có kiểm soát: một lỗi — một nhân tố phân biệt

Khi test query theo tenant, đừng cùng lúc thay:
- Status.
- Timestamp.
- Data type.
- Document size.
- Cache TTL.
- Driver version.

Nếu test thất bại, sẽ khó biết nguyên nhân. Tạo fixture baseline và thay **một thuộc tính mục tiêu**.

### 5.1. Delta debugging

Khi lỗi chỉ tái hiện trên dataset 10.000 records:
1. Giữ nguyên expected failure signature.
2. Cắt dataset thành các nhóm.
3. Chạy lại trên subsets.
4. Thu nhỏ dần.
5. Giữ các bản ghi/quan hệ làm lỗi xuất hiện.
6. Lưu seed và schema/version của tập tối thiểu cuối.

Cần cẩn trọng với lỗi phụ thuộc cardinality, ordering hoặc concurrent load: cắt quá nhỏ có thể làm lỗi biến mất không phải vì các records bị bỏ không liên quan, mà vì đã mất điều kiện trigger.

### 5.2. Chứng minh fixture không quá nhỏ

Một test “GET theo bookingId” chỉ có một booking sẽ vẫn pass nếu code quên tenantId. Thêm record trùng bookingId ở tenant khác mới khiến query sai bị phát hiện.

Một test pagination có đúng pageSize records không kiểm tra được hasNext/cursor. Cần ít nhất pageSize+1 bản ghi.

Một test sort không có hai giá trị bằng nhau không kiểm tra được tie-breaker.

## 6. Phân hoạch tương đương và giá trị biên

**Equivalence partitioning** là chia input thành những nhóm mà hệ kỳ vọng xử lý cùng quy tắc. **Boundary-value analysis** tập trung ở ranh giới chuyển từ hợp lệ sang không hợp lệ.

Ví dụ limit hợp lệ từ 1 đến 100:

| Nhóm | Giá trị | Kỳ vọng |
| --- | ---: | --- |
| Nhỏ hơn giới hạn | -1 | Reject |
| Biên dưới không hợp lệ | 0 | Reject |
| Biên dưới hợp lệ | 1 | Accept |
| Giá trị điển hình | 50 | Accept |
| Biên trên hợp lệ | 100 | Accept |
| Biên trên không hợp lệ | 101 | Reject |
| Sai kiểu | "50" | Reject nếu strict JSON type |
| Missing | Không gửi field | Default/reject theo contract |
| Explicit null | null | Default/reject theo contract |
| Overflow | 2147483648 | Reject nếu contract dùng int32 |

### 6.1. Không chỉ kiểm tra min/max

Cần xét:
- Giá trị đúng tại biên.
- Giá trị liền kề trước/sau.
- Null/missing.
- Wrong type.
- Giá trị quá lớn để parse.
- Các trường liên quan tạo quy tắc mới.

Một amountMinor >= 0 còn cần quy tắc currency/scale; một createdBefore hợp lệ riêng lẻ còn phải so với createdFrom.

### 6.2. Pairwise thay vì tích Descartes mọi trường hợp

Giả sử có 12 fields, mỗi field 8 cases: 8^12 tổ hợp là bất khả thi. Nên:
- Unit tests cho từng field/type.
- Pairwise/combinatorial testing cho các tương tác quan trọng.
- Directed tests cho invariants/authorization/transactions.
- Property-based generation.
- Một số end-to-end scenarios đại diện.

Không coi pairwise là đủ cho lỗi cần 3+ điều kiện đồng thời; giữ các regression tests cụ thể cho lỗi đã biết.

## 7. Missing, explicit null, empty và absent dữ liệu

Đây là một trong những khác biệt quan trọng nhất của NoSQL document models.

Bốn documents:

~~~~json
{}
~~~~

~~~~json
{"customerNote":null}
~~~~

~~~~json
{"customerNote":""}
~~~~

~~~~json
{"customerNote":[]}
~~~~

không nhất thiết cùng nghĩa, thậm chí document cuối có **sai kiểu** nếu customerNote phải là string.

### 7.1. Các test cần tách riêng

- Field không có: xử lý default/schema migration thế nào?
- Field có null: có được chấp nhận không?
- Field có chuỗi rỗng: business validation có coi là có nội dung không?
- Field có array rỗng: chỉ hợp lệ với fields kiểu list?
- Field có object: wrong type?
- Field có giá trị hợp lệ: read/write/serialization đúng?

### 7.2. MongoDB null query caveat

Trong MongoDB, filter equality với null có thể match cả field có null và field missing theo query semantics. Khi test phải phân biệt, sử dụng thêm tồn tại field hoặc BSON type check thích hợp; đừng assert rằng một query bằng null luôn chỉ lấy explicit null.

### 7.3. DynamoDB NULL khác thiếu attribute

Một item có thuộc tính kiểu NULL khác item không có thuộc tính. Test ConditionExpression, AttributeValue decoding và schema mapper theo contract, không tự xem hai trường hợp là tương đương.

### 7.4. Redis: key absent khác empty value

Một GET trả nil/absent khác key có value là chuỗi rỗng. Redis hash field absent cũng khác field có empty string. Đặt assertions đúng theo command semantics và serializer.

## 8. Numeric boundary: int32, int64, decimal và precision

Một field amountMinor là long không âm có thể có các cases:

| Case | Giá trị | Mục tiêu |
| --- | --- | --- |
| Negative | -1 | Reject business domain |
| Zero | 0 | Allow/reject theo contract |
| Minimum positive | 1 | Rounding |
| Typical | 1500000 | Baseline |
| Int32 maximum | 2147483647 | Boundary codec |
| Int32 max + 1 | 2147483648 | Đảm bảo không downcast |
| Long maximum | 9223372036854775807 | Kiểm tra overflow ở phép tính |
| Over long max | 9223372036854775808 | Parse reject |
| String number | "1500000" | Type strictness |
| Floating number | 1500000.5 | Không tự truncate |
| NaN/Infinity | Không hợp lệ trong JSON chuẩn | Reject |
| Decimal scale | 1.005 | Rounding policy |

### 8.1. Phép cộng có thể overflow dù từng số hợp lệ

Nếu line item amounts là long:
- A=Long.MAX_VALUE.
- B=1.

Từng field đều trong miền long, nhưng tổng overflow. Test phải assert hệ **từ chối hoặc xử lý bằng kiểu đủ rộng**, không tạo total âm.

### 8.2. Tiền không nên tự chuyển qua double

Ví dụ amountMinor có integer cents và currency riêng. Khi dùng Decimal128/BigDecimal:
- Preserve scale.
- Precision.
- Rounding mode.
- Currency compatibility.
- Không silently truncate.

### 8.3. So type trong fixture

Một document lưu BSON Long và một document lưu BSON String có cùng ký tự số không nên coi là giống nhau khi so raw values. Test mapper/type conversion cần tạo dữ liệu bằng typed writes, không chỉ dựa trên JSON strings.

## 9. Chuỗi, Unicode và định danh

Một bộ biên cho displayName hoặc search keyword có thể gồm:
- Empty.
- Một ký tự.
- Đúng max length.
- Dài max+1.
- Dấu tiếng Việt.
- Unicode combining marks.
- Emoji hoặc ký tự ngoài Basic Multilingual Plane.
- Whitespace đầu/cuối.
- Tab, newline, control characters.
- Ký tự separator trong ID/key.
- Ký tự nhìn giống nhau nhưng khác code points.
- Chuỗi có regex/query DSL metacharacters.

### 9.1. Length có nhiều nghĩa

Trong Java:
- String.length đếm UTF-16 code units.
- codePointCount đếm Unicode code points.
- Số grapheme clusters người dùng thấy có thể khác cả hai.
- Storage giới hạn bytes encoded còn khác nữa.

Nếu contract quy định max UTF-8 bytes, test một chuỗi ASCII dài 100 không đủ; cần chuỗi Unicode nhiều bytes.

### 9.2. Canonicalization phải nhất quán

Một customer ID có thể case-sensitive. Nếu authz/caching dùng lower-case còn DB query dùng raw, có thể xảy ra cache collision hoặc cross-tenant leakage. Fixtures nên có:
- "T-A" và "t-a" khi contract phân biệt.
- IDs chứa separator.
- Leading zeros.
- Unicode normalization variants nếu được hỗ trợ.
- Empty/malformed ID.

Không tự normalize mọi field; business IDs và display text có semantics khác nhau.

### 9.3. Giá trị giống operator không thành query syntax

Nếu API chỉ nhận status enum string, object có operator-like keys phải bị reject:

~~~~json
{"status":{"$ne":"CANCELLED"}}
~~~~

Test cần kiểm tra:
- HTTP/client validation outcome.
- Không có raw query được gửi.
- Không có dữ liệu tenant khác trong response.
- Không tạo side effects.
- Logs không chứa raw secret.

## 10. Thời gian: chính xác tại ranh giới

Giả sử filter:

~~~~text
createdFrom <= createdAt < createdBefore
~~~~

và khoảng:
- from = 2026-11-14T00:00:00Z.
- before = 2026-11-15T00:00:00Z.

Dữ liệu cần ít nhất:

~~~~text
R1 = 2026-11-13T23:59:59.999Z -> excluded
R2 = 2026-11-14T00:00:00.000Z -> included
R3 = 2026-11-14T12:00:00.000Z -> included
R4 = 2026-11-14T23:59:59.999Z -> included
R5 = 2026-11-15T00:00:00.000Z -> excluded
~~~~

Nếu code dùng <= upper bound thay cho <, R5 sẽ lọt vào kết quả. Không thể phát hiện bằng một record nằm giữa ngày.

### 10.1. Precision mismatch

SQL timestamp microseconds, BSON Date milliseconds và Java Instant nanoseconds có thể khác precision. Test:
- Giá trị cùng millisecond nhưng khác micro/nano.
- Conversion round/truncate.
- Equality/range tại biên precision.
- Không tự tạo timestamp test mà storage không thể lưu đúng.

### 10.2. UTC và timezone

Test:
- ISO timestamp có Z.
- Offset +07:00 quy đổi cùng instant.
- Date-only theo business timezone.
- UTC midnight.
- DST transition nếu hệ dùng timezone có DST.
- Leap day/ngày cuối tháng.

Không kiểm tra logic ngày tháng bằng string comparison mù.

### 10.3. Clock injection

Với domain code cần kiểm tra expiresAt:
- Inject java.time.Clock.
- Fixed clock cho unit tests.
- Advance clock một cách xác định.
- Test trước/bằng/sau expiry.

**Nhưng fake Clock trong JVM không tự điều khiển đồng hồ Redis/MongoDB/Cassandra server.** Integration tests TTL cần điều kiện/độ trễ phù hợp engine.

## 11. TTL, expired và tombstone là ba trạng thái khác nhau

Giả sử một key có expiry instant T.

Cases:
1. Read tại T-1 ms.
2. Read tại T.
3. Read tại T+1 ms.
4. Logical expired nhưng physical bytes chưa reclaim.
5. Explicit DELETE trước TTL.
6. Re-create key sau delete.
7. Old upsert event đến sau delete event.

### 11.1. Điều cần assert

Nếu contract nói record không còn visible khi now >= expiresAt:
- Test đơn vị domain bằng Clock.
- Integration test với engine theo semantics TTL thực tế.
- Không assert storage bytes được dọn ngay tại T.
- Không cho backfill cũ hồi sinh delete đã xảy ra sau snapshot.

### 11.2. Redis TTL tests

Nên test:
- Key không TTL.
- Key sắp hết TTL.
- Key hết TTL.
- Key bị evict do policy khác TTL.
- Key còn nhưng value là empty string.
- TTL được reset khi SET nếu có/không có option giữ TTL.
- Replica/failover behavior trong test phù hợp.

Các timing tests phải có bounded polling thay vì sleep chính xác 1 ms rồi suy động cơ server luôn phản hồi tức thời.

### 11.3. Cassandra/HBase tombstones

Test không chỉ absence:
- Write v1.
- Delete/tombstone v2.
- Late write/replay v1.
- Repair/compaction.
- TTL expiry.
- Reinsert v3 được cho phép.

Đặc biệt với timestamp-based conflict semantics, một write có timestamp ưu tiên cao có thể làm dữ liệu cũ “thắng”. Fixture cần kiểm soát timestamps và không tự giả định application version là storage timestamp.

## 12. Key và partition boundary

Một key phù hợp truy vấn có thể gồm:

~~~~text
tenantId#customerId#bucketDay
~~~~

Fixtures nên gồm:
- Hai tenants cùng customerId.
- Một customer ở ngày sát biên.
- Một bucket rỗng.
- Một bucket có 1 row.
- Một bucket có đúng pageSize rows.
- Một bucket có pageSize+1 rows.
- Một bucket gần max partition size mục tiêu.
- Một tenant tạo nhiều hot requests.
- Một ID có separator cần encoding.

### 12.1. Cross-tenant duplicate IDs là dữ liệu hữu ích

Một số test fixtures cố tình để bookingId unique toàn database, nhưng production chỉ yêu cầu unique **trong tenant**. Nếu vậy sẽ không bắt được query thiếu tenant filter. Tạo cùng bookingId ở T-A và T-B.

### 12.2. Hot key và hot partition không giống nhau

Một hot key có thể nhận vô số reads/writes. Một partition rộng có thể chứa hàng triệu clustering rows. Hai vấn đề có resource profile khác.

- Unit fixture nhỏ chứng minh key routing.
- Load fixture có skew chứng minh capacity/hotspot.
- Không dùng dữ liệu random uniform để giả lập tenant rất lớn.

### 12.3. Salt/hash buckets

Nếu schema dùng hashed bucket:
- Test cùng key luôn cùng bucket theo version.
- Không mất records khi số bucket thay đổi.
- Query fan-out gom đúng keys.
- Không lặp dữ liệu khi rebalancing.
- Boundary bucketId 0 và N-1.
- Không dùng Java String.hashCode tùy tiện cho routing xuyên hệ nếu contract đòi hash ổn định khác.

## 13. Array và document nesting boundaries

Các trường hợp với booking items:
- List absent.
- List null.
- Empty list.
- Một item.
- Max allowed items.
- Max+1 items.
- Duplicate itemNo.
- Item với amount âm.
- Item nested object sai kiểu.
- Item missing mandatory field.
- Tổng items không khớp totalMinor.
- Dữ liệu lớn làm document chạm size limit.

### 13.1. Atomic aggregate test

Nếu MongoDB document nhúng items và tổng tiền:
- Sau update, items và total phải nhất quán.
- Một conditional version update đảm bảo cạnh tranh theo contract.
- Không chỉ assert array size; assert sum/invariant.
- Không giả định multi-document consistency từ single-document atomicity.

### 13.2. Nested path khác flat field

Document có:

~~~~json
{"metadata":{"channel":"web"}}
~~~~

khác:

~~~~json
{"metadata.channel":"web"}
~~~~

tùy storage và query semantics. Test mapping nếu ứng dụng sử dụng nested paths, không để raw request tự chọn operator/path.

### 13.3. BSON/document size

Một fixture vừa dưới/vượt document-size limit cần được tạo với loại driver/codec và engine thực tế. Đừng tự ước tính dựa vào độ dài JSON UTF-8 rồi coi chính xác BSON overhead. Kiểm tra giới hạn qua integration test có budget.

## 14. Dữ liệu biên cho chỉ mục và truy vấn

Một index theo:

~~~~text
tenantId, customerId, createdAt DESC, bookingId ASC
~~~~

có thể hỗ trợ timeline. Fixtures cần:
- Các rows trùng createdAt.
- Tenant/customer khác nhưng cùng timestamp.
- Một row ở lower/upper date boundary.
- Một row có field sort missing nếu schema legacy cho phép.
- Records có giá trị null nếu engine hỗ trợ.
- Số rows bằng pageSize và pageSize+1.
- Concurrent insert giữa pages.
- Index absent hoặc khác ở môi trường test khi cần kiểm tra query-plan fallback.

### 14.1. Một test chỉ assert count không đủ

Nếu kỳ vọng B-003, B-001, B-002, test nên so **ID sequence**. Cùng số records nhưng sai tenant/thứ tự là lỗi.

### 14.2. Negative filter input

Các cases:
- Unsupported sort field.
- Unknown filter operator.
- Time range đảo.
- Page size quá lớn.
- Page cursor bị sửa.
- Cursor từ tenant khác.
- Invalid ID type.

Test đảm bảo reject theo contract, không tự bỏ filter làm query rộng hơn.

### 14.3. Tìm kiếm qua secondary index

Một GSI hoặc search index có thể eventual:
- Dữ liệu test cần sourceVersion.
- Test có thể poll bounded tới khi target thấy version yêu cầu.
- Ghi freshness lag.
- Không assert instant visibility nếu contract chỉ eventual.

### 14.4. Query plan là tính chất của dữ liệu và môi trường

Một fixture 10 records thường không đủ để phát hiện full scan cost. Nếu mục tiêu là kiểm chứng truy vấn dùng index và hiệu năng, cần dataset đủ cardinality/selectivity và examine/explain theo engine.

## 15. Dữ liệu không hợp lệ: phân tầng để xác định trách nhiệm

Không hợp lệ có nhiều loại:

| Tầng | Ví dụ | Kỳ vọng |
| --- | --- | --- |
| JSON syntax | Thiếu dấu đóng ngoặc | Reject parse |
| JSON type | status là object thay string | Reject type |
| JSON structure | Duplicate/unknown fields | Reject theo strict policy |
| Domain | amountMinor âm | Reject |
| Relationship | customerId không tồn tại | Reject hoặc policy-defined |
| Authorization | booking thuộc tenant khác | Deny/not found theo policy |
| Concurrency | expectedVersion cũ | Conflict |
| State machine | CANCELLED → CONFIRMED trái luật | Reject |
| Query resource | IN 100.000 values | Reject/throttle |
| Storage constraint | Document vượt max bytes | Failure không corrupt |
| Event ordering | Apply upsert v6 sau delete v7 | Skip stale |
| External system | Payment callback duplicate | Idempotent no duplicate |

### 15.1. “Không hợp lệ” không nhất thiết là exception

Nếu một stale CDC event v5 đến sau v6, **bỏ qua event** có thể là hành vi đúng. Nếu user không có quyền đọc tenant khác, 404 concealment có thể phù hợp policy. Nếu optimistic version mismatch, 409/conflict là đúng hơn 500.

Test phải biết expected outcome theo contract, không mặc định invalid == throw RuntimeException.

### 15.2. Không kiểm tra mỗi status code

Khi input bị reject:
- Không có write.
- Không đổi version.
- Không có outbox/notification/payment side effect.
- Không làm lộ existence của tài nguyên khác.
- Không log secret/raw PII.
- Metrics reject reason hợp lý.

### 15.3. Invalid storage state khác invalid request

Production có thể chứa legacy record sai schema. Khi test reader:
- Decode fail theo chính sách hay fallback?
- Quarantine record?
- Return partial result?
- Alert?
- Không tự thay dữ liệu bằng default gây sai tiền/trạng thái.

Dữ liệu đã lưu không tự trở nên đáng tin chỉ vì ở database.

## 16. Đầu vào nguy hiểm cho query builders

Một public API cho phép status enum không được nhận object:

~~~~json
{"status":{"$ne":"CANCELLED"}}
~~~~

Một API chỉ cho sort theo CREATED_AT không được nhận:

~~~~json
{"sortBy":"internalRiskScore"}
~~~~

Một endpoint rename displayName không được nhận:

~~~~json
{
  "displayName":"Test",
  "tenantId":"T-OTHER",
  "role":"ADMIN"
}
~~~~

Fixtures invalid cần bảo vệ:
- Wrong types.
- Unknown fields.
- Operator-like objects.
- Nested paths.
- Raw update operators.
- Injection-like strings (được xử lý như literal hoặc reject theo contract).
- Deeply nested JSON.
- Very large arrays.
- Cross-tenant IDs.

**Đừng đưa payload có mục đích kiểm thử vào production service không được phép.** Sử dụng test cluster và synthetic tenants.

## 17. Java 21: record mô tả một fixture có ý nghĩa

Một kiểu dữ liệu thuần Java giúp giảm nhầm lẫn khi tạo inputs:

~~~~java
import java.time.Instant;

public enum Status {
    PENDING, CONFIRMED, CANCELLED
}

public record BookingCase(
        String tenantId,
        String bookingId,
        String customerId,
        Status status,
        long amountMinor,
        Instant createdAt,
        long version,
        boolean deleted
) {
    public BookingCase {
        if (tenantId == null || tenantId.isBlank()
                || bookingId == null || bookingId.isBlank()
                || customerId == null || customerId.isBlank()
                || status == null || createdAt == null
                || version < 0 || amountMinor < 0) {
            throw new IllegalArgumentException("invalid fixture");
        }
    }
}
~~~~

### 17.1. Đừng dùng typed record để cố chứa mọi invalid JSON

Record này ngăn wrong-type trong Java nên phù hợp cho **valid domain fixtures**. Để test JSON parser nhận status là object hoặc amount là string, cần lưu **raw HTTP/JSON input** hoặc typed representations khác.

Nếu chỉ tạo BookingCase luôn hợp lệ, sẽ không kiểm tra được deserialization boundary.

### 17.2. Fixture factory nên đặt tên theo tình huống

~~~~java
import java.time.Instant;

public final class BookingFixtures {
    private BookingFixtures() {}

    public static BookingCase confirmed(
            String tenant, String id, long version
    ) {
        return new BookingCase(
                tenant,
                id,
                "C-9",
                Status.CONFIRMED,
                1800000L,
                Instant.parse("2026-11-14T09:00:00Z"),
                version,
                false
        );
    }

    public static BookingCase deleted(
            String tenant, String id, long version
    ) {
        BookingCase base = confirmed(tenant, id, version);
        return new BookingCase(
                base.tenantId(),
                base.bookingId(),
                base.customerId(),
                base.status(),
                base.amountMinor(),
                base.createdAt(),
                base.version(),
                true
        );
    }
}
~~~~

### 17.3. Tránh fixture defaults che bug

Nếu mọi fixture đều có:
- Cùng tenant.
- Cùng status.
- Cùng timestamp.
- version=1.
- Không có delete.
- Không có null.

thì rất nhiều path sai vẫn pass. Factory có thể tạo baseline tiện lợi nhưng mỗi test cần **dữ liệu phân biệt** đúng mục tiêu.

## 18. JUnit 5: test miền giá trị với ParameterizedTest

Một validator mẫu:

~~~~java
public final class PageLimit {
    private PageLimit() {}

    public static int validate(Integer value) {
        if (value == null) {
            return 50;
        }
        if (value < 1 || value > 100) {
            throw new IllegalArgumentException("limit");
        }
        return value;
    }
}
~~~~

JUnit Jupiter:

~~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.junit.jupiter.api.Test;

final class PageLimitTest {
    @ParameterizedTest
    @ValueSource(ints = {-1, 0, 101, Integer.MAX_VALUE})
    void rejectsOutsideRange(int input) {
        assertThrows(
                IllegalArgumentException.class,
                () -> PageLimit.validate(input)
        );
    }

    @ParameterizedTest
    @ValueSource(ints = {1, 50, 100})
    void acceptsBoundariesAndTypicalValues(int input) {
        assertEquals(input, PageLimit.validate(input));
    }

    @Test
    void missingUsesDocumentedDefault() {
        assertEquals(50, PageLimit.validate(null));
    }
}
~~~~

**Giới hạn:** Đây là unit test cho giá trị đã thành Integer. Nó không kiểm tra JSON string "50", JSON null hay overflow trong decoder. Cần test API/parser riêng.

### 18.1. ParameterizedTest theo kiểu case có expected outcome

Với nhiều biến, dùng MethodSource và một record test case có:
- Name.
- Raw input.
- Expected status/error.
- Expected data state.
- Expected events.

Tránh một test chứa nhiều assertions không liên quan khiến thất bại khó chẩn đoán.

## 19. JUnit 5: kiểm tra tính đúng tenant bằng dữ liệu tối thiểu

Một test ở cấp repository nên seed:

~~~~text
(T-A, B-001, CONFIRMED)
(T-B, B-001, CANCELLED)
~~~~

và assert:

~~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

final class BookingLookupTest {
    private final BookingRepository repository =
            createIsolatedTestRepository();

    @Test
    void sameBookingIdAcrossTenantsIsNeverConfused() {
        repository.insert(BookingFixtures.confirmed("T-A", "B-001", 1));
        repository.insert(BookingFixtures.confirmed("T-B", "B-001", 1));

        BookingCase result = repository
                .findByTenantAndId("T-A", "B-001")
                .orElseThrow();

        assertAll(
                () -> assertEquals("T-A", result.tenantId()),
                () -> assertEquals("B-001", result.bookingId()),
                () -> assertEquals(Status.CONFIRMED, result.status())
        );
    }

    // Repository/factory are test-specific interfaces/adapters.
}
~~~~

Đây là mẫu bố cục test; createIsolatedTestRepository và BookingRepository phải được định nghĩa trong dự án. Nếu repository query chỉ theo bookingId và ID được unique toàn test DB, test sẽ pass sai. Hai tenants cùng ID làm lỗi lộ ra.

### 19.1. Verify cả negative path

- T-A không tìm được B chỉ tồn tại ở T-B.
- T-A không thể update/delete B của T-B.
- Không lộ field count/sort chỉ tenant khác có.
- Không log tenant khác trong error.

## 20. Test phân trang với ba records, không cần hàng nghìn

Giả sử pageSize=2 và sort:
- createdAt DESC.
- bookingId ASC.

Dữ liệu:

~~~~text
B-003 @ 2026-11-14T10:00Z
B-001 @ 2026-11-14T09:00Z
B-002 @ 2026-11-14T09:00Z
~~~~

Kỳ vọng:
- Page 1: B-003, B-001.
- Page 2: B-002.
- Không duplicate/missing.

Nếu chỉ có hai records, test không thể chứng minh cursor đúng.

### 20.1. Tại sao cần tie-breaker?

Hai records cùng createdAt không có thứ tự toàn phần nếu chỉ sort theo thời gian. Keyset cursor phải mang đủ sort keys để biết vị trí tiếp theo.

### 20.2. Test với concurrent insert

Trong một test riêng:
1. Đọc page 1.
2. Insert một booking có createdAt nằm giữa các records.
3. Đọc page 2.
4. So hành vi với contract: snapshot consistency hay live pagination?

Không khẳng định sẽ không có duplicate/missing giữa các trang khi nguồn thay đổi nếu API không cung cấp snapshot/cursor semantics tương ứng.

### 20.3. Page token không là quyền

Dùng token của tenant B cho tenant A phải bị reject theo chính sách; ngay cả khi token được ký, nó phải gắn với tenant/query scope.

## 21. Dữ liệu để kiểm tra optimistic concurrency

Một record:

~~~~json
{
  "tenantId":"T-A",
  "bookingId":"B-001",
  "status":"PENDING",
  "version":4
}
~~~~

Hai writers:
- A muốn PENDING → CONFIRMED với expectedVersion=4.
- B muốn PENDING → CANCELLED với expectedVersion=4.

Kỳ vọng tùy state machine, nhưng nếu both updates được thực hiện bằng compare-and-set chính xác, **không thể cả hai cùng thành công từ cùng version 4**.

### 21.1. Fixture tối thiểu khác với timing ngẫu nhiên

Một record + hai actors + barrier là đủ để tạo cạnh tranh. Không cần 100.000 records. Dùng CountDownLatch/CyclicBarrier/test hooks thay sleep ngẫu nhiên.

### 21.2. Chứng cứ cần

- Mỗi attempt ID.
- Expected version.
- Outcome.
- Resulting version.
- Final source state.
- Side effects/outbox event counts.
- Có đúng một transition hợp lệ.

### 21.3. Concurrency test không phải mọi timeouts đều rollback

Nếu write timeout sau khi server đã commit, client outcome là **UNKNOWN**. Test nên dùng operationId/ledger để reconcile, không assert timeout == no-write.

## 22. Java 21: tạo lịch hai actors có thể tái hiện

~~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public final class TwoWriterSchedule {
    private final CountDownLatch bothReady =
            new CountDownLatch(2);
    private final CountDownLatch release =
            new CountDownLatch(1);

    public void awaitStart() throws InterruptedException {
        bothReady.countDown();
        if (!release.await(5, TimeUnit.SECONDS)) {
            throw new AssertionError("start barrier timeout");
        }
    }

    public void releaseBoth() throws InterruptedException {
        if (!bothReady.await(5, TimeUnit.SECONDS)) {
            throw new AssertionError("writers not ready");
        }
        release.countDown();
    }
}
~~~~

Test runner:
- Seed entity version 4.
- Chạy hai threads gọi awaitStart rồi conditional update.
- Thread chính gọi releaseBoth.
- Chờ cả futures/threads với timeout.
- Assert một success, một conflict và final version 5.
- Dọn fixture.

### 22.1. Giới hạn của cùng lúc “thả barrier”

Release cùng thời điểm không buộc từng DB operation interleave đúng một cách duy nhất. Nếu cần tái hiện race tại một critical boundary, dùng test hook kiểm soát chính xác “read version”, “pause”, “write”, “resume” trong môi trường thử nghiệm. Không đưa những hooks này vào production route không kiểm soát.

### 22.2. Không phụ thuộc vào sleep chính xác

Thread.sleep(50) chỉ tạo một khoảng trễ tương đối, không chứng minh thứ tự thực thi. GC pause, CI load và OS scheduler có thể làm test flaky.

## 23. Dữ liệu cho event ordering và CDC

Một nguồn phát:

~~~~text
UPSERT B-001 v5 status=PENDING
UPSERT B-001 v6 status=CONFIRMED
DELETE B-001 v7
~~~~

Test các thứ tự nhận:
- 5,6,7 (bình thường).
- 6,5,7 (out-of-order).
- 6,6,7 (duplicate).
- 7,5,6 (delete tới trước update cũ).
- 5,7,6 (late upsert sau delete).
- 5,6,5,7 (backfill replay).

### 23.1. Oracle

Sau khi đã apply v7 DELETE, một upsert v6 không được hồi sinh B-001. Nếu v8 UPSERT hợp lệ là nghiệp vụ re-create được phép, target xử lý theo policy rõ.

### 23.2. Không chỉ giữ payload, phải giữ metadata

Mỗi event:
- Stable entity key.
- TenantId.
- EventId.
- SourceVersion.
- SchemaVersion.
- Deleted/tombstone flag.
- Source commit position/epoch nếu có.
- Payload.
- Correlation/operationId.

Nếu không có version/order field đủ tin cậy, fixture phải làm rõ cách engine/consumer xác định thứ tự.

### 23.3. Backfill race

Test:
1. Snapshot reader lấy v5.
2. CDC cập nhật target lên v6.
3. Backfill v5 ghi sau.
4. Verify target giữ v6.

Một test seed chỉ v5 và chạy backfill một mình sẽ không bắt được lỗi ghi đè.

### 23.4. Lost event

Dữ liệu nguồn là v7 nhưng target v5. Nếu một event v6 bị mất:
- Có thể reconcile bằng snapshot/backfill hiện trạng.
- Không tự coi snapshot hiện tại đủ để phục dựng mọi historical notifications/audit.
- Test phải phân biệt current-state projection với event-sourced history.

## 24. Kiểm thử nhất quán: đừng dùng dữ liệu kiểu “đọc ngay chắc đúng”

Với NoSQL phân tán, expected outcome phụ thuộc:
- Read/write consistency level.
- Primary/replica selection.
- Session tokens.
- Transaction boundary.
- GSI/index freshness.
- CDC lag.
- Cache policy.

### 24.1. Strong vs eventual

Nếu API cam kết read-your-writes:
- Sau write ACK, read trong session phải đạt minVersion theo contract.
- Test assert sourceVersion >= committedVersion.

Nếu API chỉ eventual:
- Không assert read ngay luôn thấy v mới.
- Assert **hội tụ trong freshness bound** đã công bố.
- Ghi thời gian từ ACK đến visibility.
- Nếu quá hạn, test fail.

### 24.2. Bounded polling thay sleep cố định

Pseudo-flow:

~~~~text
write source -> version 8
deadline = now_monotonic + allowedLag
repeat until deadline:
    read projection
    if version >= 8: PASS
    wait bounded interval
if deadline: FAIL with sourceVersion, targetVersion, elapsed
~~~~

Không dùng một sleep 500 ms rồi assert cho tất cả environments; test sẽ vừa flaky vừa có thể chậm không cần thiết.

### 24.3. Không coi eventual lag là luôn hợp lệ

Eventual phải có monitoring và policy. Một projection trễ 30 phút khi SLO là 5 giây không “đúng” chỉ vì mô hình mang tên eventual consistency.

### 24.4. Test theo phân vùng network

Khi replica lag/network partition:
- Ghi failure mode.
- Không nhầm 503/timeout với NOT_FOUND.
- Không suy R+W>N luôn bảo đảm linearizability trong mọi engine mà không xét membership/repair/semantics.
- Đối chiếu consistency guarantees cụ thể của nhà cung cấp.

## 25. Key–value: bộ dữ liệu tối thiểu và biên

Một key–value store được dùng cho booking cache:

~~~~text
booking:T-A:B-001 -> serialized booking v4
booking:T-B:B-001 -> serialized booking v7
booking:T-A:B-002 -> empty string (invalid for booking schema)
booking:T-A:B-003 -> absent
~~~~

Tests:
- Tenant namespacing.
- Key exists/absent.
- Empty/corrupted value decode.
- Version-aware fill.
- TTL before/after expiration.
- Eviction vs expiry.
- Large value near storage limit.
- Multi-key operation across shard/slot boundary.

### 25.1. Một cache stampede cần dataset/tải khác

Một hot key hết hạn + nhiều concurrent callers:
- Assert origin load bị giới hạn nếu có singleflight.
- Assert stale fill không đè version mới.
- Đo 429/timeouts nếu admission.
- Không dùng chỉ một thread.

### 25.2. Redis cụ thể

Với Redis:
- GET nil vs string empty.
- Hash field absent vs empty.
- Key type mismatch.
- TTL semantics.
- Sorted-set scores tie.
- Cluster key placement.
- Eviction policy.
- Lua script key/arg validation.

Không dùng giả định của Redis như đặc tả chung cho mọi KV engine.

## 26. Document: schema linh hoạt vẫn phải test schema

Một collection MongoDB có thể chứa nhiều thế hệ:

~~~~json
{"bookingId":"B-v1","amountMinor":"1500000","schemaVersion":1}
~~~~

~~~~json
{"bookingId":"B-v2","amountMinor":1500000,"schemaVersion":2}
~~~~

~~~~json
{"bookingId":"B-v3","amountMinor":1500000,"currency":"VND","schemaVersion":3}
~~~~

Đây là JSON minh họa; khi thử kiểu BSON chính xác, phải ghi typed values qua driver.

### 26.1. Test schema evolution

- Reader v3 đọc v1/v2 thế nào?
- Có data migration hay lazy upgrade?
- Unknown field bị bỏ qua hay reject?
- Missing currency được default ra sao?
- Amount string có được chuyển chính xác hoặc quarantined?
- Re-serialize có làm mất unknown historical data?
- Unique/index/filter hoạt động với wrong type không?

### 26.2. Embedded arrays

Tests:
- Array rỗng.
- One item.
- Max items.
- Duplicate itemNo.
- Nested missing.
- Document growth vượt policy.
- Atomic update items + total.

### 26.3. Index đa trường

Tests:
- Query sort.
- Collation.
- Null/missing.
- Multikey index khi array.
- Sparse/partial indexes nếu dùng.
- Index build status và version.

### 26.4. Referential consistency

Booking chứa customerId không có FK tự động trong nhiều document models. Fixture có:
- Customer tồn tại.
- Customer missing.
- Customer bị delete.
- Cross-tenant customerId.
- Customer rename.
- Booking với embedded historical displayName.

Expected behavior phải theo contract: reject, eventual repair, render snapshot hoặc fallback.

## 27. DynamoDB: partition, sort key và item types

Một table có:

~~~~text
PK = TENANT#T-A#CUSTOMER#C-9
SK = BOOKING#20261114#B-001
~~~~

Fixtures:
- Same PK, multiple SK values.
- Different PK but same SK.
- Empty partition.
- Page limit boundary.
- LastEvaluatedKey behavior.
- Item near size policy.
- Attributes S vs N.
- Conditional write match/mismatch.
- GSI lag.
- Batch partial/unprocessed items.
- TTL expiry.

### 27.1. Query vs Scan

Một filter giống SQL WHERE nhưng không nằm trong KeyCondition có thể không giúp giới hạn items đọc như mong đợi. Dữ liệu kiểm thử cost phải có partition đủ lớn và phân phối thực tế.

### 27.2. DynamoDB GSI

Source item v5 có thể đã commit nhưng GSI chưa thấy. Test:
- Thao tác qua table point read theo consistency được hỗ trợ.
- Thao tác qua GSI.
- So version và lag.
- Không assert strong GSI read nếu dịch vụ không cung cấp.

### 27.3. ConditionalCheckFailed

Nếu expectedVersion sai, test cần:
- Không thay đổi item.
- Không phát side effect nghiệp vụ.
- Trả conflict phù hợp.
- Không retry vô hạn như lỗi network.

## 28. Wide-column: Cassandra và HBase

### 28.1. Cassandra fixtures theo partition

Một table:

~~~~sql
CREATE TABLE booking_by_customer_day (
    tenant_id text,
    customer_id text,
    bucket_day date,
    created_at timestamp,
    booking_id text,
    status text,
    PRIMARY KEY (
      (tenant_id, customer_id, bucket_day),
      created_at,
      booking_id
    )
);
~~~~

Test:
- Một partition rỗng.
- Một partition một row.
- Một partition có rows bằng page size.
- Một partition có page size+1.
- Nhiều rows cùng timestamp nhưng khác bookingId.
- Bucket ở 23:59:59.999 vs 00:00.
- Partition rất rộng.
- Tombstones/TTL.
- Missing/legacy columns.
- Read consistency variations.

### 28.2. Không biến consistency test thành unit test thuần bộ nhớ

Cassandra read/write consistency, replica repair và tombstones đòi integration/distributed tests. Unit tests giúp kiểm tra key calculator và mapper, không chứng minh cluster-level guarantees.

### 28.3. HBase row keys

Ví dụ row key:

~~~~text
T-A#C-9#20261114#B-001
~~~~

Test:
- Prefix scan boundaries.
- Byte encoding/lexicographic ordering.
- Leading zeros.
- Unicode keys.
- Region splits/hot prefixes ở scale test.
- Cell versions/timestamps.
- Tombstone/delete markers.
- TTL của column family.
- Qualifier missing vs empty.

### 28.4. Thứ tự version khác nhau

Cassandra write timestamps/HBase cell timestamps không tự tương đương domain sourceVersion. Fixture phải ghi rõ:
- Storage timestamp.
- Business version.
- Event ID.
- Expected visibility.

## 29. Graph: dữ liệu tối thiểu và case fan-out

Một graph nghiệp vụ:

~~~~text
(Customer C-1)-[:BOOKED]->(Booking B-1)
(Booking B-1)-[:FOR]->(Property P-1)
(Property P-1)-[:HAS_TAG]->(Tag T-SEA)
(Customer C-2)-[:VIEWED]->(Property P-1)
~~~~

### 29.1. Test traversal tối thiểu

Để kiểm tra “find properties matching tag viewed by same-tenant customers”, cần:
- Start node có tồn tại.
- Một path hợp lệ.
- Một path không hợp lệ (khác tenant).
- Một path có edge type không được phép.
- Một graph không có path.

Chỉ có một path hợp lệ không bắt lỗi query đi quá xa hoặc thiếu tenant filter.

### 29.2. Hướng cạnh

Nếu BOOKED là directed edge Customer→Booking:
- Test traversal đúng hướng.
- Test chiều ngược nếu query contract cho phép.
- Không coi directed edge như undirected nếu semantics không vậy.

### 29.3. Chu trình và duplicate paths

Thêm:
- A→B→A cycle.
- Hai đường khác nhau cùng tới P-1.
- Một self-loop nếu schema có thể gặp.
- Nodes không kết nối.

Assert:
- Không infinite traversal.
- Distinct semantics đúng.
- Max depth.
- Path ordering khi có.
- Authorization của từng node/edge.

### 29.4. Supernode

Một Tag phổ biến nối rất nhiều properties. Để test truy vấn chi phí cao phải dựng degree distribution đại diện, không chỉ graph 4 nodes. Nhưng một graph 4 nodes vẫn đủ kiểm tra correctness của path/edge types.

## 30. Dữ liệu sai quan hệ và tính toàn vẹn

Mô hình NoSQL có thể không dùng foreign keys. Test nên dựng:
- Booking trỏ tới customer không có.
- Booking trỏ customer ở tenant khác.
- Payment có bookingId không tồn tại.
- Booking đã deleted nhưng read projection vẫn visible.
- Inventory count âm.
- Hai bookings cùng slot khi chính sách cấm.
- Payment state CONFIRMED nhưng ledger thiếu operationId.

### 30.1. Dữ liệu nguồn lỗi hay derived copy lỗi?

Nếu một read model thiếu customer displayName:
- Source customer missing thật?
- CDC event chưa đến?
- Projection transformer bỏ field?
- Schema migration không tương thích?

Fixtures khác nhau cho từng nguyên nhân, không chỉ assert màn hình thiếu tên là lỗi.

### 30.2. Test sửa chữa dữ liệu

Một repair job phải:
- Nhận diện orphan.
- Không sửa nhầm tenant.
- Không ghi đè version mới.
- Có dry-run và audit.
- Có idempotency.
- Không tạo notification/payment side effect lần nữa.

## 31. Xác thực và phân quyền trong test data

Một bộ data đúng schema nhưng không kiểm tra authorization có thể bỏ sót lỗi cross-tenant.

Fixtures tối thiểu:
- Tenant A, user A1.
- Tenant A, user A2 có quyền khác.
- Tenant B, user B1.
- Booking A1 thuộc A.
- Booking A2 thuộc A nhưng private.
- Booking B1 thuộc B.
- Một ID trùng giữa A/B nếu contract cho phép.

Test các operations:
- Read by ID.
- Query/list.
- Sort/projection.
- Update.
- Delete.
- Aggregate/count.
- Export.
- Graph traversal.
- Cache lookup.
- Cursor reuse.

### 31.1. Authorization oracle

Không chỉ nhìn HTTP status. Kiểm tra:
- Identity của mọi result.
- Số liệu tổng hợp không bao gồm dữ liệu ngoài quyền.
- Không bị lộ thông qua sort order.
- Không có write.
- Error không xác nhận existence trái policy.

### 31.2. Không lưu token thật trong fixtures

Tạo test principals/claims nhân tạo; không commit access tokens, secrets, email hoặc địa chỉ khách hàng thật.

## 32. Snapshot, backup, restore và dữ liệu biên

Nếu mục tiêu là test restore correctness:
- Snapshot chứa record v5.
- Live v6 sau snapshot.
- Record bị xóa v7.
- TTL expiry giữa snapshot và restore.
- Schema version khác.
- Index/permissions chưa khôi phục.
- Selected restore chỉ 3 records.

### 32.1. Không blind replace

Test một selective restore patch:
- Bảo tồn fields mới hợp lệ.
- Không hồi sinh deleted record.
- Dùng expected live version.
- Conflict khi dữ liệu đã đổi.
- Không duplicate side effects.
- Verify per-key membership/value/version.

### 32.2. Backup checksum không đủ

Một checksum đúng không chứng minh dữ liệu nghiệp vụ đã đúng lúc sao lưu. Test restore cần cả schema, transaction invariant, key set và query paths.

### 32.3. Dữ liệu có PITR gap

Nếu log chain thiếu segment, system không được tuyên bố đã restore nhất quán tới mốc vượt gap. Test error reporting và recovery state UNKNOWN/BLOCKED rõ ràng.

## 33. Java 21: Clock injection để kiểm tra expiry policy

Một policy thuần ứng dụng:

~~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

public final class ExpiryPolicy {
    private final Clock clock;

    public ExpiryPolicy(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public boolean isExpired(Instant expiresAt) {
        return expiresAt != null
                && !clock.instant().isBefore(expiresAt);
    }
}
~~~~

JUnit:

~~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

final class ExpiryPolicyTest {
    @Test
    void expiresExactlyAtDeadline() {
        Instant deadline =
                Instant.parse("2026-11-14T12:00:00Z");

        ExpiryPolicy before = new ExpiryPolicy(
                Clock.fixed(deadline.minusMillis(1), ZoneOffset.UTC)
        );
        ExpiryPolicy at = new ExpiryPolicy(
                Clock.fixed(deadline, ZoneOffset.UTC)
        );
        ExpiryPolicy after = new ExpiryPolicy(
                Clock.fixed(deadline.plusMillis(1), ZoneOffset.UTC)
        );

        assertFalse(before.isExpired(deadline));
        assertTrue(at.isExpired(deadline));
        assertTrue(after.isExpired(deadline));
        assertFalse(at.isExpired(null));
    }
}
~~~~

### 33.1. Hạn chế

Unit test này không xác nhận:
- Redis server TTL.
- MongoDB TTL monitor.
- Cassandra TTL/tombstone.
- HBase physical compaction.

Những phần đó phải test bằng engine thật với thời gian chờ có tolerance và visibility semantics phù hợp.

## 34. Integration test: dùng NoSQL thật trong môi trường cách ly

Một hướng phổ biến là Testcontainers hoặc isolated test deployment, với:
- Engine version được pin.
- Startup readiness.
- Schema/index migration.
- Synthetic fixtures.
- Cleanup per test.
- Không dùng production credentials.
- Network/account isolation.
- Test timeout rõ.

Một mẫu khởi tạo MongoDB bằng Testcontainers (API cụ thể tùy phiên bản thư viện):

~~~~java
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
final class MongoBoundaryIntegrationTest {
    @Container
    static final MongoDBContainer mongo =
            new MongoDBContainer("mongo:7.0");

    @Test
    void containerIsAvailableForIsolatedTests() {
        assertTrue(mongo.isRunning());
        // Connect a MongoClient to mongo.getReplicaSetUrl(),
        // seed scoped synthetic docs, execute query,
        // assert exact tenant/key order, then clean up.
    }
}
~~~~

**Đây chỉ là skeleton môi trường**, không phải một test dữ liệu hoàn chỉnh. Một integration test đầy đủ phải tạo MongoClient, unique namespace và fixtures, gọi repository rồi assert kết quả. Pin image digest hoặc version chính xác trong CI để tránh môi trường tự thay đổi.

### 34.1. Unit fake vs engine thật

In-memory Map fake có ích để test business logic, nhưng có thể không mô phỏng:
- BSON type comparisons.
- Null/missing query semantics.
- Sort/index collation.
- Transaction isolation.
- TTL.
- Driver retries.
- Quorum/replica lag.
- Cassandra tombstones.
- DynamoDB conditional failures.

Do đó cần cả **unit**, **integration**, **distributed fault** và **scale** tests theo mục tiêu.

### 34.2. Cleanup

Một test không được phụ thuộc dữ liệu do test trước để lại:
- Per-test namespace/tenant IDs.
- Truncate/drop only isolated test namespace.
- Cleanup trong finally/afterEach.
- Không tự xóa production data bằng wildcard.
- Confirm test target environment before destructive operations.

## 35. Test data seeding và reproducibility

Một fixture có thể mô tả bằng YAML:

~~~~yaml
fixtureId: booking-search-boundary-v1
seed: 538001
schemaVersion: 3
clockUtc: "2026-11-14T10:00:00Z"
tenantIds:
  - T-A
  - T-B
records:
  - tenantId: T-A
    bookingId: B-001
    createdAt: "2026-11-14T09:00:00Z"
    status: CONFIRMED
    version: 4
  - tenantId: T-A
    bookingId: B-002
    createdAt: "2026-11-14T09:00:00Z"
    status: PENDING
    version: 1
  - tenantId: T-A
    bookingId: B-003
    createdAt: "2026-11-14T10:00:00Z"
    status: CANCELLED
    version: 2
  - tenantId: T-B
    bookingId: B-001
    createdAt: "2026-11-14T11:00:00Z"
    status: CONFIRMED
    version: 7
expected:
  listTenantACustomerC9:
    orderedBookingIds: [B-003, B-001, B-002]
  tenantBRecordExcluded: true
~~~~

YAML mô tả ý tưởng; khi xây thật cần điền customerId và những mandatory fields của schema. Không để fixtures thiếu fields cần thiết khiến kết quả bị lỗi unrelated.

### 35.1. Seed không phải chỉ một con số

Lưu:
- Generator version.
- Random algorithm.
- Seed.
- Schema and codec version.
- Input distribution.
- Clock/timezone.
- Engine/driver version.
- Region/topology.
- Test execution mode.
- Exact failure assertion.

Một seed không bảo đảm reproduction nếu generator code hoặc environment thay đổi.

### 35.2. Random generator có seed

~~~~java
import java.util.SplittableRandom;

public final class DeterministicIds {
    public static String[] makeIds(long seed, int count) {
        if (count < 0 || count > 10_000) {
            throw new IllegalArgumentException("count");
        }

        SplittableRandom random = new SplittableRandom(seed);
        String[] ids = new String[count];

        for (int i = 0; i < count; i++) {
            ids[i] = "B-" + i + "-" +
                    Long.toUnsignedString(random.nextLong(), 36);
        }

        return ids;
    }
}
~~~~

Seed reproducibility hữu ích, nhưng generator này **không đảm bảo** dữ liệu đủ test sorting tie, rare null types hoặc hot partition. Phải chủ động thêm targeted boundary cases.

### 35.3. Snapshot fixture version

Một fixture phải được versioned khi:
- Schema đổi.
- Serializer đổi.
- Sort/filter contract đổi.
- Partition key thay.
- New authorization policy.
- New engine behavior cần test.

Không sửa lặng lẽ fixture kỳ vọng của regression test đã từng bắt bug.

## 36. Golden datasets, golden outputs và oracle drift

Một **golden dataset** là tập đầu vào được lưu có version; **golden output** là kết quả mong đợi.

Rủi ro:
- Golden output được tạo từ chính implementation lỗi.
- Khi code thay đổi, developer update snapshot output mà không xem business contract.
- Serialization order làm diff giả.
- Engine version/index plan làm output thay đổi dù semantics không đổi.

### 36.1. Golden assertions nên ở mức nghiệp vụ

Tốt:
- TenantId/key/status/version.
- Ordered IDs nếu sort contract có.
- AmountMinor exact.
- Deleted absent.
- Error category.

Thận trọng:
- Raw JSON bytes.
- Internal driver exception text.
- Physical partition/node ID.
- Nanosecond latency.
- Query plan string chi tiết, trừ khi test version-bound.

### 36.2. Khi golden thay đổi

Cần ghi:
- Vì sao output thay.
- Contract version.
- Dữ liệu nào đổi.
- Có security/consistency regression không?
- Test cũ bắt lỗi gì?

Không tự động accept mọi snapshot diff để CI xanh.

## 37. Property-based testing

Thay vì chỉ chọn vài ví dụ, sinh nhiều input theo miền giá trị với các bất biến.

Ví dụ:
- Với mọi amountMinor >= 0 trong miền hợp lệ, serialize/deserialize phải giữ nguyên số tiền.
- Với mọi booking thuộc T-B, query scoped T-A không trả booking đó.
- Với mọi event version nhỏ hơn watermark, target không lùi version.
- Với mọi page size hợp lệ, ghép pages không tạo duplicate keys khi source không đổi.
- Với mọi malformed enum/object input, API reject mà không write.

### 37.1. Generator hợp lệ và không hợp lệ phải tách

Nếu generator luôn tạo dữ liệu hợp lệ, nó không kiểm tra rejection. Nếu toàn dữ liệu invalid, nó không kiểm tra business functionality. Thiết kế generators:
- Valid domain values.
- Boundary values.
- Invalid inputs.
- Schema versions.
- Large/skew distributions.

### 37.2. Shrinking

Khi property fails trên 1.000 records, công cụ property-based có thể shrink về:
- Hai tenants cùng bookingId.
- Một time tie.
- Một null/missing.
- Một version inversion.

Bản thu nhỏ nên được lưu thành regression fixture.

### 37.3. Metamorphic testing

Khi khó biết toàn bộ expected output, dùng quan hệ biến đổi:
- Thêm record của tenant B không được thay kết quả query tenant A.
- Đảo thứ tự insert không được đổi sort output khi sort toàn phần.
- Duplicate delivery của cùng event không được nhân side effects.
- Thêm field không thuộc projection không được thay response public.
- Rebuild read model từ same source snapshot phải cho canonical-equivalent result.
- Tăng max page size không được làm thay tập kết quả tổng khi nguồn đứng yên.

Những quan hệ này giúp bắt lỗi không cần tạo một output lớn bằng tay.

## 38. Mutation testing và khả năng phát hiện lỗi

Một bài test thực sự hữu ích khi nó thất bại với lỗi code gần thực tế. Các mutation có thể xét:
- Bỏ điều kiện tenantId.
- Đổi < thành <= ở upper boundary.
- Bỏ tie-breaker sort.
- Bỏ version guard.
- Đổi OR thành AND.
- Bỏ event delete.
- Cho unknown enum thành null rồi bỏ filter.
- Bỏ giới hạn page size.
- Upsert stale event bất kể sourceVersion.
- Không kiểm tra resource authorization.

### 38.1. Mutation score không là mục tiêu duy nhất

Một test có thể “kill” nhiều mutations nhưng vẫn thiếu:
- Lost ACK/unknown commit.
- Cross-store invariants.
- TTL/replica lag.
- Privacy deletes.
- Hot partition.

Dùng mutation testing bổ sung cho threat model và business invariants, không thay thế chúng.

## 39. Dữ liệu scale và shape: tối thiểu logic chưa đủ cho hiệu năng

Nếu lỗi là query chậm trên partition rộng, fixture 3 rows không kích hoạt cùng access path. Cần hai cấp:

- **Logic fixture:** nhỏ, deterministic, bắt semantics.
- **Shape fixture:** đủ partition width, item size, tombstone density, skew, indexes và concurrent load.

### 39.1. Shape khác raw production dump

Một shape fixture có thể tạo:
- 100 tenants.
- Một tenant chiếm 60% writes.
- 10% records thiếu field legacy.
- 2% documents cực lớn.
- Một partition có 500.000 rows.
- TTL/delete churn theo tỷ lệ rõ.
- Query mix point/range/scan.
- Keys theo phân phối skew.

Các giá trị là ví dụ; chọn từ telemetry thực nhưng dùng **synthetic data**.

### 39.2. Chỉ giữ đặc tính gây lỗi

Nếu đang test hot partition, không cần tên khách hàng thật; cần key distribution và item size. Nếu đang test BSON type mismatch, không cần 500.000 records; cần one wrong-typed record.

### 39.3. Không dùng uniform random làm đại diện mặc định

Nếu production có heavy-hitter tenants, data generator uniform dễ che hotspots. Ghi phân phối Zipfian/hotset hoặc explicit tenant weights, đồng thời kiểm tra generator thực tế đã tạo đúng tỉ lệ.

### 39.4. Đo offered load

Với stress fixture:
- Planned/sent/completed operations.
- Rejected/timeout/unknown.
- Generator lag.
- p99 theo operation.
- DB CPU/IO/compaction.
- Connection pool wait.
- Source read/write errors.

Nếu generator tự chậm, completion p99 có thể đẹp giả; không suy hệ chịu được desired arrival rate khi thực tế không phát đủ tải.

## 40. Ma trận bao phủ toàn hệ NoSQL

| Thành phần | Tối thiểu | Biên | Không hợp lệ |
| --- | --- | --- | --- |
| KV lookup | 2 tenants cùng ID | Key dài, hot key, TTL | Wrong key namespace/type |
| Document | 1 booking + items | Large array, null/missing, decimal | Wrong BSON type/schema |
| Wide-column | 1 partition + 3 rows | Bucket boundary, wide partition, tombstones | Missing partition key/invalid query |
| Graph | Một valid path + một invalid path | Cycle, supernode, max depth | Cross-tenant edge/forbidden relation |
| Pagination | pageSize+1 records | Equal sort keys, concurrent insert | Tampered/cross-tenant cursor |
| Versioned update | 1 record + 2 writers | Max version, retry after timeout | Stale expectedVersion |
| CDC | v5, v6, delete v7 | Out-of-order, duplicate, log gap | Malformed event/schema |
| Index | Tập keys có chọn lọc | Index lag/large scan | Forbidden dynamic field |
| TTL | Một key với expiry | Before/at/after deadline | Invalid/negative TTL |
| Authorization | Hai tenants | Roles, field-level permissions | Unauthenticated/outside scope |
| Backup | Snapshot + updated key | PITR boundary, deleted records | Missing log segment/checksum |
| Cache | Hit/miss | Stampede, stale fill | Corrupted payload/token |

Ma trận không có nghĩa mọi trường hợp là một test duy nhất. Tách theo loại fixture và tầng kiểm thử để kết quả dễ giải thích.

## 41. Fixtures cho API và storage phải khớp nhưng không giống hệt

Một hệ có hai boundary:
1. HTTP JSON request → Java DTO.
2. Java DTO → BSON/AttributeValue/CQL/Redis bytes.

Input sai ở tầng một có thể chưa từng tới storage. Storage corrupt record có thể bypass mọi validation từ HTTP.

### 41.1. Test API

Gửi raw JSON:
- Wrong type.
- Missing/unknown fields.
- Malformed date.
- Wrong enum.
- Duplicate keys.
- Unauthorized tenant.
- Too-large body.

Assert status/error, không query hoặc write.

### 41.2. Test repository/codec

Ghi typed data trực tiếp trong isolated test database:
- BSON Int32 vs Int64 vs Decimal128.
- AttributeValue S vs N.
- CQL timestamp vs text.
- Redis bytes không decode được.
- HBase cell versions.
- Graph property absent vs null semantics.

Assert domain mapping/fallback/quarantine đúng.

### 41.3. Test end-to-end

Chạy API qua driver và DB:
- Correctness, scope, concurrency.
- Response projection.
- Event publication.
- Read model consistency.
- Error handling.

Một mock API success không chứng minh actual database indexing/transaction semantics.

## 42. Tránh kiểm thử không quyết định

Các nguyên nhân flaky:
- Dùng real wall-clock.
- Thread.sleep để điều khiển race.
- Database shared state từ test khác.
- Random không có seed.
- Index build chưa xong.
- Read replica chưa bắt kịp.
- CI resource contention.
- TTL monitor không quét đúng mili giây.
- Background compaction.
- Poll interval không có deadline.
- Test container image tự đổi.

### 42.1. Nguyên tắc ổn định

- Fixed Clock cho domain logic.
- Monotonic deadlines cho polling.
- Latches/barriers cho concurrency.
- Unique test namespace.
- Explicit schema/index readiness.
- Version-pinned engine.
- Bounded waits.
- Structured failure diagnostics.
- Repeatable seeds.
- Per-test cleanup.

### 42.2. Không “sửa” flaky test bằng sleep dài vô hạn

Tăng sleep từ 100 ms lên 10 giây có thể che vấn đề và làm CI chậm. Với eventual system, nên:
- Ghi observed version.
- Poll cho điều kiện convergence.
- Có deadline từ freshness SLO.
- Phân biệt timeout của test fixture với lỗi sản phẩm.

## 43. Kiểm soát tính độc lập và dọn dẹp test data

### 43.1. Mỗi test sở hữu namespace của mình

Có thể tạo:
- Database/collection riêng.
- Tenant ID riêng.
- Table prefix hoặc key prefix.
- Unique runId.
- Cleanup được giới hạn.

Không dùng hard-coded shared tenant "test" trong một staging cluster đông người nếu tests chạy song song.

### 43.2. Cleanup không phá chứng cứ khi test fail

Một hướng:
- Log synthetic fixture ID/seed/namespace.
- Chụp failure diagnostics đã redacted.
- Sau đó cleanup theo policy.
- Không để data test vô hạn trong shared environment.

### 43.3. Test data lifecycle

- TTL test records.
- Test account credentials giới hạn.
- Không gửi email/payment thật.
- Không gây notification bên ngoài.
- Không đọc production backup nếu không có quy trình phê duyệt.
- Không commit secrets/PII vào repo.

### 43.4. Một fixture cho một mục đích

Đừng tạo một “God fixture” có hàng chục nghìn records được mọi test dùng chung. Một test thêm record có thể làm hàng loạt tests khác hỏng bất ngờ. Sử dụng reusable small builders, nhưng dựng state riêng theo test.

## 44. Dữ liệu thật, synthetic và quyền riêng tư

Để kiểm thử:
- Ưu tiên synthetic.
- Dùng giả lập tên, email, payment IDs không thể dùng thật.
- Bảo tồn type/shape/length/distribution cần thiết.
- Không dùng production credentials.
- Không sao chép full customer records vô cớ.

### 44.1. Hash không đủ để ẩn danh

Hash email/phone/ID ít entropy có thể bị đoán. Khi cần correlate một subject qua nhiều records, dùng tokenization/HMAC có kiểm soát và chính sách bảo vệ key, hoặc thay bằng synthetic consistent identifiers.

### 44.2. Dữ liệu lỗi thực tế

Nếu production incident do một chuỗi Unicode/legacy type:
- Ghi shape và đặc tính tối thiểu.
- Xây synthetic value gây cùng behavior.
- Dùng raw data chỉ trong evidence store được cấp phép nếu thật sự không thể thay.
- Xóa theo retention.

### 44.3. Kiểm tra quyền ở test infrastructure

Nếu fixture chứa PII, môi trường test có thể có quyền rộng hơn production. Đó là rủi ro. Thiết kế least privilege, encryption, access audit và data minimization.

## 45. Test oracle cho từng loại dữ liệu không hợp lệ

Một bộ test invalid nên có outcome cụ thể:

| Trường hợp | API/DB outcome | State sau test |
| --- | --- | --- |
| amountMinor âm | Domain validation reject | Không có booking mới |
| Unknown status enum | Parse/validation reject | Không bỏ status filter |
| Object thay status string | Wrong-type reject | Không phát raw operator tới DB |
| tenantId giả trong body | Reject/ignore theo policy có kiểm soát | Không truy cập tenant khác |
| expectedVersion cũ | Conditional conflict | Record không đổi |
| Duplicate operationId | Trả canonical result | Một logical effect |
| Bản ghi đã xóa | NOT_FOUND/denied theo contract | Không hồi sinh |
| CDC upsert version cũ | Skip stale | Target không rollback |
| Page size 101 | Reject | Không chạy query rất rộng |
| Cursor thuộc tenant B | Reject | Không trả dữ liệu B |
| Query timeout | Timeout/UNKNOWN theo loại operation | Có reconcile nếu write |
| Data codec sai | Error/quarantine | Không trả tiền sai hoặc silent default |

### 45.1. Kiểm tra side effects

Ngoài source state, theo dõi:
- Outbox events.
- Payment operations.
- Inventory holds.
- Cache invalidations.
- Search updates.
- Audit trails.
- Metrics.

Một mutation bị reject nhưng đã gửi payment webhook là lỗi nghiêm trọng dù response đúng 400.

## 46. Quy trình thiết kế fixture từ một bug report

Giả sử báo lỗi:

> “Đôi lúc danh sách booking bị lặp một booking ở cả trang 1 và trang 2.”

Một quy trình:

1. **Viết điều kiện lỗi:** cùng bookingId xuất hiện hai lần trong một traversal pagination.
2. **Thu query contract:** sort createdAt DESC, bookingId ASC; cursor theo hai keys.
3. **Tạo baseline:** ba bookings, page size hai.
4. **Tạo boundary:** hai bookings cùng createdAt.
5. **Thử bug:** nếu cursor chỉ lưu createdAt, một record có thể bị lặp/bỏ.
6. **Assert sequence:** page1+page2 bằng expected ordered unique IDs.
7. **Thêm concurrency case:** insert giữa pages nếu contract cần.
8. **Giữ seed và expected output.**
9. **Tạo failing regression test trước fix.**
10. **Sau fix, chạy cả deterministic và integration variant.**

### 46.1. Nếu bug không tái hiện

So sự khác biệt:
- Engine/driver version.
- Index/collation.
- Page token.
- Dataset cardinality.
- Timestamp precision.
- Concurrent writes.
- Read consistency.
- Query sort.
- Projection/serialization.

Không tự suy bug report sai chỉ vì fixture chưa đủ.

## 47. Một ví dụ tổng hợp: tạo fixture 12 records đúng mục tiêu

Không cần hàng triệu dòng để bắt nhiều lỗi logic. Một tập 12 records có thể được **phân nhóm độc lập theo case**, không dùng tất cả làm một test chung:

| Record | Điểm khác biệt | Test |
| --- | --- | --- |
| B-001/T-A | Happy path | Point read |
| B-001/T-B | Same ID, khác tenant | Tenant isolation |
| B-002/T-A | Same createdAt như B-001 | Sort tie |
| B-003/T-A | Mốc createdAt mới hơn | Pagination |
| B-004/T-A | Missing optional field | Missing mapping |
| B-005/T-A | Explicit null | Null semantics |
| B-006/T-A | Empty array | Collection behavior |
| B-007/T-A | Legacy schema v1 | Codec/migration |
| B-008/T-A | Logical deleted | Delete filtering |
| B-009/T-A | ExpiresAt gần ranh giới | TTL |
| B-010/T-A | Max amount hợp lệ | Numeric boundary |
| B-011/T-A | Mức version sát ranh giới update | Conditional write |

### 47.1. Một test phải dùng subset phù hợp

Pagination test chỉ seed các records đủ phục vụ sorting. TTL test riêng dùng frozen clock. Invalid JSON tests gửi request raw, không cố đưa invalid record vào BookingCase hợp lệ.

### 47.2. Mức tối thiểu không tuyệt đối

Một fixture nhỏ nhất cho test A có thể quá nhỏ cho test B. Một test correctness ở scale/consistency đôi khi cần nhiều nodes/partitions để tái hiện.

## 48. Bài tập thực hành: thiết kế ba lớp dữ liệu

Giả sử dịch vụ Booking API:
- Java 21, MongoDB source.
- Redis cache.
- DynamoDB bảng tra cứu phụ.
- Cassandra timeline cho customer.
- OpenSearch search.
- Graph projection cho recommendation.
- Multi-tenant.
- Booking có amountMinor long, status enum, version, createdAt, expiresAt, items.
- Một số records legacy còn thiếu currency.
- CDC cập nhật các projections bất đồng bộ.
- Booking creation không được double-book.
- Search freshness SLO tối đa 5 giây.

### Phần A — Tối thiểu theo query

Thiết kế fixture nhỏ nhất phát hiện:
1. Query thiếu tenantId.
2. Query thiếu bookingId.
3. Pagination thiếu tie-breaker.
4. Filtering nhầm status.
5. Update không có expectedVersion.

Với mỗi fixture, nêu IDs, các giá trị tạo khác biệt và assertions.

### Phần B — Số tiền

Tạo test cases:
- -1.
- 0.
- 1.
- Int32 max.
- Int32 max+1.
- Long max.
- Long max+1.
- String number.
- Decimal fraction.

Nêu output theo domain contract và nguy cơ overflow/precision.

### Phần C — Null/missing

Tạo cùng một field ở các trạng thái:
- Absent.
- Explicit null.
- Empty string.
- Wrong type.
- Correct value.

Giải thích khác biệt khi:
1. Deserialization vào Java record.
2. Filter MongoDB.
3. DynamoDB AttributeValue.
4. Redis cache value.

### Phần D — Thời gian/TTL

Giả sử filter [2026-11-14T00:00Z, 2026-11-15T00:00Z) và expiry 12:00Z:
1. Thiết kế năm timestamp cần kiểm tra.
2. Dùng Clock.fixed cho domain TTL.
3. Vì sao fake Clock không điều khiển TTL Redis?
4. Cần bounded polling khi test expiration server như thế nào?

### Phần E — Cạnh tranh

Hai users confirm/cancel booking v4 cùng lúc:
1. Fixture tối thiểu?
2. Dùng barrier để dựng race?
3. Expected outcomes?
4. Nếu một write timeout sau commit, kết luận gì?
5. Kiểm tra side effects thế nào?

### Phần F — CDC

Tạo v5/v6/delete v7:
1. Test out-of-order.
2. Test duplicate.
3. Test delete arrives first.
4. Test stale backfill.
5. Test schemaVersion chưa hỗ trợ.

Viết assertions về sourceVersion và tombstone.

### Phần G — Wide-column

Thiết kế:
- Empty partition.
- One row.
- pageSize rows.
- pageSize+1 rows.
- Bucket boundary.
- Hot partition.

Nêu trường hợp nào dùng small fixture và trường hợp nào cần scale fixture.

### Phần H — Graph

Dựng graph có:
- Một valid path.
- Một cross-tenant path.
- Một cycle.
- Một duplicate path tới cùng node.
- Một supernode.

Viết expected results cho truy vấn giới hạn depth=2 và quyền tenant.

### Phần I — Invalid input

Thiết kế ít nhất 20 cases:
1. Malformed JSON.
2. Status là object.
3. Status là array.
4. Unknown enum.
5. Amount âm.
6. Long overflow.
7. Amount string.
8. CreatedBefore <= createdFrom.
9. Bad timezone.
10. Null mandatory tenant.
11. Missing bookingId.
12. Unknown field.
13. Duplicate JSON keys.
14. Raw operator-like object.
15. Tenant khác.
16. Cursor bị sửa.
17. Page size quá lớn.
18. Max array+1.
19. Duplicate itemNo.
20. Invalid state transition.
21. Stale expectedVersion.
22. CDC event malformed.
23. TTL negative theo API policy.
24. Corrupt cache bytes.

Với mỗi case ghi:
- Input.
- Lớp từ chối.
- Status/error.
- Không có side effects.
- Test setup và cleanup.

### Phần J — Property/metamorphic testing

Viết ba properties:
1. Thêm dữ liệu tenant B không đổi kết quả tenant A.
2. Delivery CDC duplicate không nhân logical effect.
3. Upsert sourceVersion thấp không làm target lùi.

Nêu generator, seed, shrink strategy và expected invariant.

### Phần K — Tính đại diện

Production có:
- Một tenant chiếm 70% writes.
- 10% documents legacy.
- 1% keys rất lớn.
- Nhiều TTL tombstones.
- Một graph tag có degree cao.

Thiết kế synthetic scale fixture bảo tồn phân phối nhưng không chứa PII. Nêu vì sao uniform random không đủ.

### Phần L — CI pipeline

Thiết kế thứ tự:
- Unit parsing/domain.
- Parameterized boundary tests.
- Integration database container.
- CDC/outbox tests.
- Authorization/cross-tenant tests.
- Concurrency/fault tests.
- Scheduled scale/distributed tests.

Định nghĩa version/seed/cleanup/artifact khi thất bại.

### Hướng giải

Một phương án chặt chẽ sẽ:

- Tạo **fixture nhỏ có dữ liệu phân biệt**, không chỉ happy path.
- Viết **oracle rõ**: exact key/order/version/field/error, không chỉ số lượng.
- Dùng **boundary tables** cho numeric, timestamp, pagination, TTL, string, array và partition.
- Kiểm tra **missing/null/empty/wrong type** độc lập.
- Xây **invalid raw JSON** riêng với valid Java domain records.
- Test **tenant scope và authorization** bằng IDs trùng ở hai tenants.
- Dùng **barriers và version guards** cho concurrency, không phụ thuộc sleep.
- Dùng **CDC events out-of-order/duplicate/delete/backfill** với version-aware assertions.
- Phân biệt **small logic fixture** và **large shape fixture** cho hot partitions/index performance.
- Sử dụng **fixed Clock, deterministic seed, pinned engine, per-test namespace và cleanup**.
- Tránh production PII/credentials, kiểm tra cả **side effects** khi thao tác bị từ chối.

## 49. Runbook thiết kế và duy trì bộ dữ liệu kiểm thử

### Bước 1 — Viết bất biến

Ví dụ:
- Không cross-tenant.
- Không double-book.
- Không version rollback.
- Không resurrect deleted record.
- Amount total chính xác.
- Pagination không lặp trong snapshot contract.

### Bước 2 — Chọn fixture tối thiểu

Tạo records/sự kiện ít nhất khiến implementation sai bị phát hiện. Gắn tên case và mô tả khác biệt.

### Bước 3 — Liệt kê ranh giới

- Min/max.
- Null/missing.
- Type/precision.
- Time/TTL.
- Partition/key.
- Page size.
- Schema version.
- Version/CDC order.

### Bước 4 — Sinh invalid cases

Test parser/domain/auth/concurrency/query resource riêng. Không đưa raw invalid payload vào valid domain factory.

### Bước 5 — Chọn tầng test

- Unit cho validation/mapping/Clock.
- Integration cho codec/query/index/storage semantics.
- Distributed/fault cho consistency/retry/failover.
- Scale cho partition/cardinality/hotset.

### Bước 6 — Định nghĩa oracle/observability

Ghi expected keys, order, versions, errors, business side effects và dữ liệu không được trả.

### Bước 7 — Cố định môi trường

Pin versions, seed, timezone, schema, index readiness, namespace và feature flags.

### Bước 8 — Chạy và thu bằng chứng

Lưu:
- Test case ID.
- Seed.
- Engine/driver.
- Fixture version.
- Expected vs actual.
- Query shape.
- Error category.
- Sanitized trace.
- Không chứa secrets/PII.

### Bước 9 — Thu nhỏ lỗi và lưu regression

Shrink dataset nhưng giữ failure signature. Tách test mới khỏi shared fixture nếu lỗi phụ thuộc setup khác.

### Bước 10 — Đánh giá lại khi schema/engine đổi

Mỗi lần đổi:
- Schema/codec.
- Query sort/index.
- Partition key.
- Consistency mode.
- Authorization.
- TTL/retention.
- Driver version.

cần xem các fixture/assertions liên quan có còn đúng hợp đồng không.

## 50. Những sai lầm cần tránh

1. **Chỉ có một happy-path record.** Không bắt thiếu tenant/filter.
2. **Random nhiều dữ liệu nhưng không có oracle.** Không biết kết quả đúng.
3. **Assert count thay exact IDs.** Có thể trả nhầm records.
4. **Không có duplicate sort keys.** Không bắt pagination tie-breaker.
5. **Page size đúng bằng số records.** Không kiểm tra cursor tiếp theo.
6. **Chỉ kiểm tra limit 50.** Bỏ lỡ 0/1/100/101.
7. **Gộp null và missing.** Có semantics khác.
8. **Biến mọi numeric JSON thành double.** Mất type/precision.
9. **Không kiểm tra Long overflow khi cộng.** Có thể tạo giá trị âm.
10. **Không có legacy schema fixture.** Production codec fail.
11. **Chỉ dùng ASCII.** Bỏ lỡ Unicode/UTF-8 length.
12. **Dùng String.length như số ký tự người dùng nhìn thấy.** Có thể sai.
13. **Dùng wall-clock thật cho mọi TTL unit test.** Flaky.
14. **Tin fake Clock điều khiển server TTL.** Sai.
15. **Assert TTL physical deletion đúng từng mili giây.** Khác engine.
16. **Không xét delete/tombstone.** Có thể resurrection.
17. **Không tạo same ID ở hai tenants.** Tenant filter bug bị che.
18. **Chỉ dữ liệu uniform.** Không bắt hot tenant.
19. **Test chỉ một partition khi cần cross-partition query.** Thiếu fan-out.
20. **Không xét pageSize+1 trong wide-column table.** Bỏ sót paging.
21. **Không dùng trường wrong-type trong BSON.** Chỉ test JSON shape.
22. **Mock DB nhưng kết luận về query planner.** Không có cơ sở.
23. **Chỉ test valid input.** Không biết rejection behavior.
24. **Chỉ assert 400, không assert no-write.** Có thể side effects.
25. **Cho unknown enum thành null rồi bỏ filter.** Kết quả quá rộng.
26. **Không tạo stale expectedVersion.** Bỏ lỡ lost update.
27. **Dùng sleep để tạo race.** Không deterministic.
28. **Timeout là rollback.** Có UNKNOWN commit.
29. **Không test duplicate CDC event.** Có thể duplicate effects.
30. **Không test out-of-order CDC.** Có thể version rollback.
31. **Không có tombstone watermark.** Backfill cũ hồi sinh delete.
32. **Assert eventual index thấy ngay.** Test sai contract.
33. **Dùng sleep cố định thay bounded polling.** Flaky và chậm.
34. **Không ghi event IDs/versions.** Không đủ kiểm chứng.
35. **Tạo graph không có cycle/path duplicate.** Không bắt traversal bug.
36. **Tạo graph nhỏ rồi kết luận supernode tốt.** Không đủ degree.
37. **Dùng một giant fixture cho mọi test.** Dễ phụ thuộc lẫn nhau.
38. **Không pin engine image.** Test thay đổi vô hình.
39. **Không ghi seed/generator version.** Không tái hiện được.
40. **Update golden output mà không review contract.** Che regression.
41. **Dùng raw JSON bytes làm mọi oracle.** Serialization order gây false diff.
42. **So dữ liệu ở hai thời điểm khác nhau.** Báo stale mismatch sai.
43. **Không bảo vệ test namespace.** Dễ đụng test khác.
44. **Cleanup bằng wildcard production-like.** Nguy cơ xóa nhầm.
45. **Dùng PII thật làm fixture.** Privacy/security risk.
46. **Hash email rồi coi anonymous.** Dễ bị suy ra.
47. **Không kiểm tra output fields.** Có thể lộ nội bộ.
48. **Không test query cost bounds.** DoS từ input hợp lệ.
49. **Dùng throughput thành công để suy tải phát.** Có thể generator chậm.
50. **Gọi test xanh là bằng chứng mọi consistency guarantee đúng.** Cần đúng tầng, topology và invariant.

## 51. Checklist thiết kế fixture trước khi merge

1. **Có nêu rõ bất biến mà test muốn bảo vệ?**
2. **Fixture có một khác biệt làm lỗi cần tìm lộ ra?**
3. **Tập dữ liệu nhỏ nhất hợp lý cho loại lỗi này?**
4. **Đã định nghĩa expected exact IDs/order/versions?**
5. **Có test empty dataset và one-record dataset?**
6. **Có two-tenant same-ID case khi áp dụng?**
7. **Có lower/upper numeric boundaries và overflow?**
8. **Có null, missing, empty, wrong type?**
9. **Có schema legacy và unknown enum?**
10. **Có timestamp before/at/after boundaries?**
11. **Có precision/timezone tests?**
12. **Có TTL trước/bằng/sau expiry?**
13. **Có delete/tombstone/reinsert scenarios?**
14. **Có duplicate sort keys và pageSize+1?**
15. **Có cursor bound với tenant/filter?**
16. **Có bounded arrays và document-size cases?**
17. **Có partition/bucket boundary cases?**
18. **Có scale/skew fixture nếu test hotspot?**
19. **Có typed DB writes kiểm tra BSON/AttributeValue/CQL semantics?**
20. **Có concurrency version-guard tests?**
21. **Có retry/UNKNOWN commit/idempotency case?**
22. **Có CDC duplicate/out-of-order/backfill race?**
23. **Có eventual consistency freshness policy test?**
24. **Có cross-tenant read/write/aggregation checks?**
25. **Invalid input có assert no side effects?**
26. **Test unit vs integration vs fault vs scale đúng mục tiêu?**
27. **Có fixed Clock hoặc timing controls?**
28. **Có deterministic seed và generator version?**
29. **Engine/driver/container versions được pin?**
30. **Index/schema readiness xác định?**
31. **Per-test namespaces và cleanup an toàn?**
32. **Có data minimization, không PII/secret thật?**
33. **Có diagnostics rõ khi test fail?**
34. **Có property/metamorphic cases ở nơi hữu ích?**
35. **Có shrink/regression fixture cho bug đã phát hiện?**
36. **Oracle dựa business contract thay vì implementation hiện tại?**
37. **Test bao gồm failure/error/timeout paths?**
38. **Có xác minh result fields không lộ private values?**
39. **Đã xem lại fixtures khi đổi schema/consistency/engine?**
40. **Không xem một fixture nhỏ là bằng chứng cho tải phân tán nếu chưa test scale?**

**Kết luận:** Thiết kế dữ liệu để kiểm thử tính đúng NoSQL là bài tập **chọn những khác biệt có thể làm lộ sai sót**, chứ không phải đổ thật nhiều records vào database. Dữ liệu **tối thiểu** phải có đủ đối chứng để kiểm tra tenant, key, sort, update và bất biến. Dữ liệu **biên** phải chạm ranh giới số, kiểu, thời gian, TTL, phân trang, độ lớn document, partition và concurrency. Dữ liệu **không hợp lệ** phải thử parser, schema, quyền, state machine và query budgets, đồng thời xác minh **không có side effects**. Với replication, CDC, cache và read model, fixture cần cả **versions, deletes, event ordering và freshness contract**. Dùng **typed Java fixtures cho dữ liệu hợp lệ, raw inputs cho dữ liệu sai kiểu, fixed clocks, deterministic seeds, engine tích hợp thật và cleanup cách ly**, rồi lưu những trường hợp tối giản bắt được lỗi làm regression tests. Một bộ test tốt cho biết chính xác **dữ liệu nào, điều kiện nào và bất biến nào** đã được bảo vệ — cũng như giới hạn mà nó chưa thể chứng minh.
