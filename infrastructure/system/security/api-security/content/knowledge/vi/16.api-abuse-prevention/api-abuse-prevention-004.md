# Quota theo client plan và business rule

Một API có thể xác thực đúng client, kiểm tra scope và vẫn bị lạm dụng nếu không giới hạn lượng tài nguyên client được phép tiêu thụ. Ví dụ, một tích hợp có quyền `reports:export` có thể gửi hàng nghìn yêu cầu xuất báo cáo lớn; một tenant tạo nhiều API key để né giới hạn từng key; hoặc một client dùng endpoint tìm kiếm đắt tiền để làm cạn connection pool và tài nguyên database.

Quota (hạn mức sử dụng) giúp hệ thống quy định một client, tenant hoặc tài khoản được tiêu thụ bao nhiêu tài nguyên trong một khoảng thời gian hoặc một chu kỳ hợp đồng. Quota cần kết hợp **client plan** (gói dịch vụ và entitlement được cấp) với **business rule** (quy tắc nghiệp vụ theo chức năng, dữ liệu và rủi ro). Một gói dịch vụ có thể quy định số request hoặc dung lượng bao gồm; business rule có thể giới hạn số lần xuất báo cáo, số bản ghi mỗi lần, số giao dịch hoặc tổng giá trị thao tác.

Trong API Security, quota không chỉ là bộ đếm request. Thiết kế đúng cần xác định ai bị tính hạn mức, đơn vị tiêu thụ, chu kỳ, phạm vi áp dụng, cách xử lý request đồng thời, retry, nâng/hạ gói, ngoại lệ và phản hồi khi hết hạn mức. Quota cũng không thay thế authorization: client còn quota vẫn phải có quyền gọi chức năng và truy cập đúng object.

## 1. Quota theo client plan là gì?

Client plan là gói hoặc hợp đồng gắn với client, project, workspace, tenant hay tổ chức. Plan mô tả các entitlement mà khách hàng được sử dụng, ví dụ:

- Số request API được bao gồm trong một chu kỳ.
- Số bản ghi hoặc dung lượng dữ liệu được đọc/xuất.
- Số tác vụ chạy nền hoặc số tác vụ đồng thời.
- Các tính năng được phép dùng, như bulk import, export hoặc webhook.
- Hạn mức theo loại nghiệp vụ, ví dụ số hóa đơn, số lần đồng bộ hoặc số giao dịch.

Ví dụ minh họa:

| Plan | Request/tháng | Export/tháng | Số dòng/export | Tác vụ export đồng thời |
|---|---:|---:|---:|---:|
| Starter | 100.000 | 20 | 5.000 | 1 |
| Growth | 1.000.000 | 500 | 50.000 | 3 |
| Enterprise | Theo hợp đồng | Theo hợp đồng | Theo hợp đồng | Theo hợp đồng |

Các con số chỉ để minh họa cách biểu diễn entitlement, không phải bảng giá hay cam kết của một nhà cung cấp cụ thể. Plan thực tế cần được xác định từ hợp đồng, năng lực hệ thống và mô hình kinh doanh.

Quota theo plan cho phép hệ thống áp dụng giới hạn nhất quán cho nhiều client mà không phải hardcode điều kiện ở từng controller. Khi khách hàng nâng gói, entitlement có thể thay đổi qua policy/configuration; khi hết hạn hợp đồng hoặc thanh toán thất bại theo điều khoản, quyền sử dụng có thể bị giới hạn theo trạng thái subscription.

## 2. Phân biệt plan, entitlement, quota và rate limit

Các khái niệm này liên quan nhưng không đồng nghĩa:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Plan | Gói dịch vụ hoặc hợp đồng gắn với client | Growth, Enterprise hoặc hợp đồng riêng |
| Entitlement | Quyền sử dụng tính năng và giới hạn được plan cấp | Được export, tối đa 50.000 dòng mỗi lần |
| Quota | Lượng sử dụng tối đa trong một phạm vi/chu kỳ | 500 lần export mỗi tháng |
| Rate limit | Tốc độ request trong khoảng thời gian ngắn | 20 request/giây, burst tối đa 40 |
| Concurrency limit | Số tác vụ hoặc request đang chạy đồng thời | Tối đa 3 export đang xử lý |
| Resource limit | Giới hạn chi phí hoặc kích thước một thao tác | Tối đa 100 MB dữ liệu đầu vào |

Một client có thể còn quota tháng nhưng vẫn vượt rate limit trong một giây. Ngược lại, client có thể gửi chậm nhưng đã dùng hết quota tháng. Client có entitlement export nhưng không có scope tương ứng vẫn phải bị từ chối. Mỗi cơ chế giải quyết một loại rủi ro riêng.

## 3. Xác định chủ thể bị tính quota

Trước khi chọn con số, cần xác định quota được gắn với ai. Một API có thể có nhiều danh tính:

- API key nhận diện một integration hoặc credential.
- OAuth client ID nhận diện ứng dụng gọi API.
- User ID nhận diện người dùng cuối.
- Project/workspace/tenant nhận diện phạm vi dữ liệu và hợp đồng.
- Organization/account nhận diện khách hàng thanh toán.

Không nên mặc định quota chỉ theo API key. Nếu mỗi key có quota riêng, một tenant có thể tạo nhiều key để nhân hạn mức. Với quota thương mại, thường cần một bucket tổng theo tenant hoặc subscription, đồng thời có thể thêm bucket riêng theo key để phát hiện key bị lạm dụng.

Ví dụ, một request có thể phải thỏa đồng thời:

1. Bucket theo API key: tối đa 10 request/giây.
2. Bucket theo tenant: tối đa 1.000.000 request/tháng.
3. Bucket theo user: tối đa 100 lần tạo báo cáo/ngày.
4. Bucket theo endpoint: tối đa 5 export đang chạy đồng thời.
5. Bucket toàn hệ thống: tổng công suất export không vượt ngưỡng vận hành.

Chủ thể quota phải được lấy từ identity và subscription đã xác minh ở phía server. Không tin `plan=enterprise`, `tenantId` hoặc `clientId` do request body/query tự khai báo. Nếu gateway truyền metadata, backend chỉ được tin sau khi xác thực ranh giới gateway và loại bỏ header giả mạo từ client.

## 4. Thiết kế business rule theo hành động và tài nguyên

Một số nghiệp vụ không thể kiểm soát đầy đủ bằng số request. Một request có thể tạo một tác vụ nhỏ hoặc xuất hàng triệu bản ghi. Vì vậy, hãy chọn đơn vị tiêu thụ phản ánh chi phí và tác động thực tế.

| Chức năng | Đơn vị quota phù hợp | Business rule có thể áp dụng |
|---|---|---|
| Đọc API thông thường | Request hoặc điểm chi phí | Giới hạn theo client, tenant và endpoint |
| Tìm kiếm | Request có trọng số hoặc số kết quả | Giới hạn page size, độ sâu filter và thời gian truy vấn |
| Export | Tác vụ, số dòng hoặc byte | Giới hạn dòng/tệp, số export mỗi kỳ và concurrency |
| Import | Tệp, số dòng hoặc record hợp lệ | Giới hạn kích thước, số dòng và số lỗi cho phép |
| Gửi thông báo | Tin nhắn theo kênh | Giới hạn SMS/email theo ngày và chống gửi trùng |
| Tạo hóa đơn | Hóa đơn hoặc chứng từ | Giới hạn theo plan và kỳ kế toán |
| Thanh toán | Giao dịch hoặc giá trị tiền | Hạn mức số lần, giá trị mỗi giao dịch và tổng ngày |
| AI/compute | Token, giây CPU hoặc điểm tính phí | Hạn mức ngân sách và concurrency |
| Webhook | Lần gửi và số lần retry | Giới hạn endpoint, backoff và dead-letter policy |

Business rule nên xác định cả điều kiện được phép lẫn điều kiện từ chối. Ví dụ, plan có 500 export/tháng nhưng một lần export không được vượt 50.000 dòng; dữ liệu thuộc tenant khác không được tính vào phạm vi export; báo cáo chứa trường nhạy cảm có thể cần entitlement riêng hoặc approval.

Không để client tự khai báo chi phí tiêu thụ. Server phải tính quota cost từ thao tác, dữ liệu đã xác minh và policy. Nếu request chứa `estimatedRows=100`, nhưng truy vấn thực tế trả 50.000 dòng, không được chỉ trừ quota theo con số client gửi.

## 5. Tính hạn mức hiệu lực từ nhiều policy

Một client có thể chịu nhiều lớp giới hạn cùng lúc: plan, hợp đồng riêng, tenant, endpoint, key và chính sách chống lạm dụng. Hệ thống cần quy định cách kết hợp chúng.

Ví dụ:

| Nguồn policy | Giới hạn export/tháng |
|---|---:|
| Plan Growth | 500 |
| Hợp đồng tenant | 400 |
| Endpoint export dữ liệu nhạy cảm | 100 |
| Ngoại lệ đã phê duyệt | Tăng thêm 20 |

Không nên cộng mọi con số một cách máy móc. Một mô hình phổ biến là áp dụng tất cả bucket độc lập: request phải còn hạn mức ở plan, tenant và endpoint. Ngoại lệ chỉ thay đổi bucket cụ thể mà policy cho phép. Với một metric có nhiều giới hạn tối đa áp dụng đồng thời, giới hạn chặt nhất thường chi phối; nhưng cần phân biệt quota cộng thêm theo hợp đồng với quota độc lập theo endpoint.

Hãy biểu diễn policy có cấu trúc thay vì rải điều kiện trong code:

```yaml
planId: growth
features:
  report.export: true
quotas:
  api.requests:
    limit: 1000000
    period: calendar_month
  report.exports:
    limit: 500
    period: calendar_month
  report.export.rows_per_job:
    limit: 50000
concurrency:
  report.export.jobs:
    limit: 3
```

Đây là ví dụ cấu hình. Policy thực tế cần có version, nguồn cấp, thời gian hiệu lực, đơn vị, timezone, quy tắc rollover và cách xử lý ngoại lệ.

## 6. Chu kỳ quota và thời điểm reset

Quota có thể dùng nhiều loại chu kỳ:

- **Calendar period:** ngày, tuần hoặc tháng theo lịch, ví dụ reset đầu tháng UTC.
- **Rolling window:** tính lượng sử dụng trong 24 giờ hoặc 30 ngày gần nhất từ thời điểm hiện tại.
- **Billing cycle:** theo ngày bắt đầu và kết thúc chu kỳ hợp đồng của từng khách hàng.
- **Lifetime allowance:** tổng hạn mức trong toàn bộ vòng đời hoặc một chiến dịch.
- **Per-operation limit:** giới hạn trên từng request/tác vụ, không cần reset.

Ví dụ quota tháng theo lịch và quota rolling 30 ngày cho kết quả khác nhau. Nếu khách hàng bắt đầu gói vào ngày 18, billing cycle có thể từ ngày 18 đến ngày 17 tháng sau; reset vào ngày 1 sẽ không phản ánh đúng hợp đồng nếu hệ thống tính theo billing cycle.

Mỗi policy phải xác định:

- Múi giờ dùng để tính kỳ, nên lưu và xử lý timestamp theo UTC.
- Thời điểm bắt đầu/kết thúc và quy tắc tại ranh giới kỳ.
- Quota chưa dùng có được chuyển sang kỳ sau không.
- Nâng/hạ plan giữa kỳ xử lý hạn mức còn lại thế nào.
- Request bắt đầu trước reset nhưng hoàn tất sau reset được tính vào kỳ nào.
- Tác vụ bất đồng bộ được trừ quota lúc submit, lúc bắt đầu hay lúc hoàn tất.

Không reset bằng cách xóa toàn bộ bộ đếm mà không giữ dấu vết. Nên gắn counter với period key hoặc lưu ledger usage để có thể đối soát, giải thích và khôi phục khi xảy ra sự cố.

## 7. Phân biệt quota request với quota theo chi phí

Đếm mỗi request như nhau là dễ triển khai nhưng có thể không phản ánh chi phí. Ví dụ:

- `GET /health` gần như không tốn tài nguyên.
- `GET /orders?page=0&size=20` có chi phí trung bình.
- `POST /reports/export` có thể truy vấn hàng triệu bản ghi và tạo tệp lớn.
- `POST /search` với filter lồng sâu có thể tốn nhiều CPU và database.

Có thể dùng cost unit hoặc weighted quota:

| Hành động | Cost minh họa |
|---|---:|
| Đọc một object | 1 unit |
| Tìm kiếm tối đa 100 kết quả | 5 units |
| Tạo báo cáo nhỏ | 20 units |
| Export 10.000 dòng | 100 units |
| Export dữ liệu lớn | Tính theo số dòng/byte thực tế |

Cost phải được xác định từ đặc tính server-side và hiệu năng đo được. Tránh cho client gửi `cost=1` để giảm mức trừ. Nếu chi phí chỉ biết sau khi xử lý, hãy reserve mức dự kiến có giới hạn trước, đo mức tiêu thụ thực tế rồi settle hoặc điều chỉnh theo quy tắc rõ ràng.

## 8. Reserve, commit và hoàn quota

Với tác vụ bất đồng bộ hoặc thao tác có chi phí lớn, có thể cần tách việc giữ quota khỏi việc ghi nhận mức tiêu thụ cuối cùng.

1. **Reserve:** kiểm tra và giữ trước một lượng quota tối đa để tránh nhiều request đồng thời cùng dùng phần hạn mức còn lại.
2. **Execute:** thực hiện tác vụ với giới hạn tài nguyên đã định.
3. **Commit/settle:** ghi nhận mức tiêu thụ thực tế sau khi tác vụ hoàn thành.
4. **Release/refund:** giải phóng phần đã giữ nhưng không dùng hoặc hoàn lại quota khi tác vụ thất bại theo chính sách.

Ví dụ export 20.000 dòng dự kiến tiêu thụ 20.000 row units. Hệ thống reserve 20.000 units khi nhận job; sau khi export thực tế 18.500 dòng, settle 18.500 và giải phóng 1.500. Nếu job thất bại trước khi đọc dữ liệu, có thể release toàn bộ. Nếu job đã tiêu thụ tài nguyên đáng kể trước khi lỗi, business rule cần xác định phần nào vẫn được tính.

Reservation phải có ID, trạng thái, thời hạn và cơ chế cleanup nếu worker chết. Không để reservation treo vô hạn làm khách hàng mất quota. Khi retry cùng job, dùng cùng idempotency key để không reserve hai lần.

## 9. Rate limit, quota và concurrency cần phối hợp

Một policy hoàn chỉnh thường có nhiều lớp:

| Cơ chế | Bảo vệ | Ví dụ |
|---|---|---|
| Rate limit | Burst và tải tức thời | 20 request/giây |
| Daily/monthly quota | Tổng mức sử dụng theo kỳ | 1 triệu request/tháng |
| Concurrency | Tác vụ đang chạy | Tối đa 3 export đồng thời |
| Payload/page limit | Chi phí mỗi request | Tối đa 100 MB hoặc 1.000 record |
| Timeout | Tài nguyên bị giữ quá lâu | Query tối đa 10 giây |
| Budget limit | Chi phí dịch vụ hoặc tiền | Không vượt ngân sách compute tháng |

Không tăng quota tháng để giải quyết lỗi burst; cũng không tăng rate limit để cho phép một job lớn chạy đồng thời quá nhiều. Chọn cơ chế phù hợp với nguyên nhân cần kiểm soát.

Concurrency limit nên dùng lease hoặc semaphore phân tán có thời hạn, vì worker có thể crash trước khi giải phóng slot. Lease cần gia hạn khi job còn hoạt động và có cơ chế hết hạn an toàn. Nếu chỉ dùng counter tăng/giảm, lỗi worker có thể khiến slot bị chiếm vĩnh viễn hoặc bị giải phóng hai lần.

## 10. Thuật toán thực thi quota

### Fixed window

Đếm số lần sử dụng trong một cửa sổ cố định, ví dụ mỗi phút hoặc mỗi tháng. Cách này đơn giản và tiết kiệm trạng thái. Nhược điểm là burst ở ranh giới cửa sổ: client có thể gửi gần hết quota ngay trước khi reset rồi gửi tiếp ngay sau reset.

### Sliding window

Tính số request hoặc lượng sử dụng trong cửa sổ trượt. Có thể dùng log sự kiện hoặc counter theo các bucket thời gian nhỏ. Cách này mượt hơn nhưng cần nhiều trạng thái hoặc phép tính hơn.

### Token bucket

Bucket chứa token, token được bổ sung theo tốc độ xác định đến mức tối đa. Mỗi request tiêu thụ một hoặc nhiều token. Cơ chế này cho phép burst có giới hạn nhưng duy trì tốc độ trung bình. Token bucket phù hợp với rate limit; quota tháng vẫn thường cần counter riêng.

### Leaky bucket

Request được xử lý hoặc đưa ra khỏi bucket theo tốc độ ổn định. Cơ chế này giúp làm phẳng lưu lượng và phù hợp khi cần kiểm soát tốc độ xử lý tác vụ.

Không có thuật toán duy nhất phù hợp cho mọi metric. Có thể dùng fixed/calendar counter cho quota tháng, token bucket cho rate limit và lease/semaphore cho concurrency. Việc chọn thuật toán phải tính đến tính chính xác, lưu lượng, chi phí trạng thái và khả năng chịu lỗi.

## 11. Thực thi phân tán và cập nhật nguyên tử

Trong môi trường nhiều application instance, bộ đếm trong bộ nhớ của một instance không thể đảm bảo quota toàn hệ thống. Nếu 5 instance mỗi instance cho phép 100 request/phút, client có thể đạt gần 500 request/phút khi lưu lượng được phân phối đều.

Các lựa chọn thường gặp:

- API gateway hoặc rate-limit service dùng kho trạng thái dùng chung.
- Redis với atomic operation hoặc Lua script cho phép kiểm tra và tăng counter trong một thao tác.
- Database transaction với row lock hoặc conditional update cho quota có yêu cầu kiểm toán cao.
- Usage ledger/event stream kết hợp counter materialized cho billing và đối soát.

Kiểm tra quota rồi tăng counter bằng hai thao tác tách rời có race condition:

```text
Request A: đọc remaining = 1
Request B: đọc remaining = 1
Request A: thấy còn quota -> cho phép
Request B: thấy còn quota -> cho phép
Request A: tăng counter
Request B: tăng counter
```

Hai request đã cùng sử dụng đơn vị cuối cùng. Hãy thực hiện check-and-consume nguyên tử bằng transaction, conditional update hoặc script phía kho trạng thái. Với nhiều bucket, cần bảo đảm tất cả bucket được reserve nhất quán hoặc có cơ chế bù trừ nếu một bucket thành công còn bucket khác thất bại.

### Ví dụ atomic counter với Redis Lua

Script minh họa cho một fixed window counter:

```lua
local current = redis.call('GET', KEYS[1])
local used = tonumber(current or '0')
local cost = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local ttl = tonumber(ARGV[3])

if used + cost > limit then
  return {0, used, limit - used}
end

local updated = redis.call('INCRBY', KEYS[1], cost)
if updated == cost then
  redis.call('EXPIRE', KEYS[1], ttl)
end

return {1, updated, limit - updated}
```

Script chạy nguyên tử trên Redis. Ứng dụng cần tạo key có namespace chứa tenant/client/metric/period, kiểm tra cost là số nguyên không âm, đặt TTL phù hợp và xử lý lỗi Redis. Nếu dùng Redis Cluster, các key cần được bố trí cùng hash slot khi một script phải thao tác nhiều key. Đây là ví dụ fixed window đơn giản; hệ thống billing có yêu cầu đối soát cần thêm ledger và quy trình reconciliation.

Không dùng một key counter chung cho tất cả tenant. Phải phân vùng theo chủ thể, metric và kỳ để tránh khách hàng này tiêu thụ quota của khách hàng khác.

## 12. Nhiều quota bucket trong cùng một request

Một request export có thể cần kiểm tra:

1. Plan có entitlement `report.export` không?
2. Tenant còn quota export trong billing cycle không?
3. API key có rate limit riêng còn không?
4. User có quota cá nhân nếu nghiệp vụ yêu cầu không?
5. Endpoint có slot concurrency không?
6. Dữ liệu truy vấn có nằm trong tenant và object scope không?

Nên định nghĩa thứ tự kiểm tra để giảm chi phí: xác thực identity và entitlement trước, sau đó kiểm tra scope/object, payload/page limit, rate limit, quota và concurrency trước khi tạo side effect. Một số kiểm tra phải nằm trong transaction hoặc bước reserve để tránh trạng thái thay đổi giữa lúc check và consume.

Nếu một bucket đã bị trừ nhưng bucket khác từ chối, hệ thống cần rollback hoặc release phần đã reserve. Không để client bị trừ quota dù request không được nhận theo hợp đồng, trừ khi policy công bố rõ phí cho request thất bại hoặc tài nguyên đã tiêu thụ.

## 13. Plan upgrade, downgrade và thay đổi hợp đồng

Subscription có thể thay đổi giữa chu kỳ. Cần quy định rõ cách cập nhật entitlement:

- **Upgrade ngay lập tức:** tăng giới hạn hoặc bật feature từ thời điểm hiệu lực; phần quota đã dùng được giữ lại hay tính lại theo hợp đồng.
- **Downgrade cuối kỳ:** tiếp tục dùng plan hiện tại đến ngày kết thúc; plan mới áp dụng khi chu kỳ tiếp theo bắt đầu.
- **Downgrade tức thời:** nếu usage hiện tại vượt hạn mức mới, có thể chặn request mới, cho phép đọc dữ liệu cũ hoặc chuyển sang trạng thái chỉ đọc theo chính sách.
- **Subscription hết hạn hoặc payment issue:** xác định grace period, tính năng bị khóa và hành vi API.
- **Hợp đồng tùy chỉnh:** lưu nguồn phê duyệt, người thay đổi, effective date và expiry của override.

Không lấy plan từ cache lâu đến mức một client đã bị hạ gói vẫn được dùng quyền cũ vô thời hạn. Cache cần có TTL và cơ chế invalidation khi subscription thay đổi. Với thao tác nhạy cảm hoặc có chi phí cao, có thể đọc entitlement mới nhất hoặc dùng version policy để phát hiện cache cũ.

Nếu usage hiện tại vượt quota sau khi downgrade, không tự xóa lịch sử usage. Hãy áp dụng quy tắc rõ ràng: chặn thao tác mới, cho phép hoàn tất job đã reserve, hoặc yêu cầu nâng gói. Mọi ngoại lệ phải có audit và thời hạn.

## 14. Ngoại lệ quota và override có kiểm soát

Khách hàng có thể cần tăng hạn mức tạm thời trong chiến dịch hoặc khi di chuyển dữ liệu. Không nên sửa trực tiếp counter hoặc hardcode `if (clientId == ...)` trong controller.

Một quota override nên có:

- Chủ thể và metric được áp dụng.
- Giá trị tăng thêm hoặc giới hạn thay thế.
- Lý do và ticket/contract tham chiếu.
- Người yêu cầu và người phê duyệt.
- Thời điểm bắt đầu, hết hạn và timezone.
- Phạm vi endpoint, tenant và environment.
- Audit event khi tạo, sửa, dùng hoặc thu hồi.

Override phải có expiry; không tạo ngoại lệ vĩnh viễn chỉ vì hỗ trợ khách hàng từng cần tăng quota. Hãy xác định override cộng thêm vào plan, thay thế plan hay chỉ áp dụng cho một endpoint. Cách kết hợp phải rõ để không vô tình cấp quyền vượt hợp đồng.

## 15. API response khi hết quota hoặc rate limit

Khi vượt rate limit hoặc quota, API thường trả `429 Too Many Requests`. Response nên giúp client hiểu giới hạn và thời điểm có thể thử lại mà không tiết lộ dữ liệu nội bộ.

Ví dụ:

```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/problem+json
Retry-After: 3600
RateLimit-Limit: 1000000
RateLimit-Remaining: 0
RateLimit-Reset: 3600

{
  "type": "https://api.example.com/problems/quota-exceeded",
  "title": "Quota exceeded",
  "status": 429,
  "code": "MONTHLY_EXPORT_QUOTA_EXCEEDED",
  "detail": "The export quota for the current billing period has been reached.",
  "resetAt": "2026-11-19T00:00:00Z"
}
```

Tên header và format trong ví dụ cần khớp với chuẩn/API contract mà hệ thống chọn; `RateLimit-*` là các trường RateLimit phổ biến được định nghĩa cho HTTP. Trong ví dụ này, `RateLimit-Reset` biểu diễn số giây còn lại tới lúc reset; `resetAt` trong body biểu diễn thời điểm tuyệt đối theo UTC. `Retry-After` có thể biểu diễn số giây hoặc HTTP date. Với quota theo chu kỳ, cả thời gian chờ và thời điểm reset cần phản ánh đúng bucket thực tế.

Phân biệt lỗi:

| Tình huống | Response thường dùng |
|---|---|
| Thiếu hoặc key/token không hợp lệ | `401 Unauthorized` |
| Client không có entitlement hoặc scope | `403 Forbidden` |
| Vượt rate limit hoặc quota sử dụng | `429 Too Many Requests` |
| Payload vượt kích thước tối đa | `413 Content Too Large` |
| Trạng thái subscription không cho phép thao tác | `403` hoặc mã lỗi nghiệp vụ theo hợp đồng |
| Hệ thống quota tạm thời không khả dụng | `503 Service Unavailable` nếu không thể đánh giá an toàn |

Không trả `429` cho mọi lỗi phân quyền vì client sẽ retry sai cách. Cũng không trả `403` cho quota hết nếu hợp đồng cần client chờ reset hoặc nâng plan. Error code nên ổn định để SDK có thể xử lý tự động.

## 16. Retry, idempotency và cách tính quota

Client có thể retry khi timeout hoặc nhận lỗi tạm thời. Nếu mỗi retry đều bị tính như một thao tác mới, quota có thể bị trừ nhiều lần dù server chỉ tạo một job. Với endpoint có side effect hoặc tác vụ tốn kém, hãy kết hợp idempotency key.

Quy tắc nên nêu rõ:

- Cùng idempotency key và cùng request fingerprint có trả lại kết quả cũ hay không.
- Request bị từ chối trước khi tạo tác vụ có bị tính quota không.
- Request đã được nhận nhưng worker thất bại có hoàn quota hay không.
- Một lần retry của job đã tạo có tạo reservation mới không.
- Key được lưu trong phạm vi client/tenant nào và giữ trong bao lâu.
- Cùng key nhưng payload khác phải bị từ chối.

Idempotency key không thay thế quota. Một client có thể tạo nhiều key khác nhau để né hạn mức. Quota phải được tính theo business identity và usage ledger, còn idempotency ngăn xử lý trùng cùng một thao tác.

## 17. Fail-open hay fail-closed khi quota service gặp lỗi?

Nếu kho quota hoặc policy service không khả dụng, hệ thống phải chọn hành vi phù hợp với rủi ro. Không có một lựa chọn đúng cho mọi endpoint.

| Loại thao tác | Hành vi thường phù hợp | Lý do |
|---|---|---|
| Đọc công khai, chi phí thấp | Có thể fail-open có giới hạn cục bộ | Ưu tiên khả dụng, rủi ro chi phí thấp |
| Export lớn, compute đắt | Fail-closed hoặc từ chối nhận job | Không biết quota còn có thể gây cạn tài nguyên |
| Thanh toán, chuyển tiền | Fail-closed với quota/risk policy bắt buộc | Tránh vượt hạn mức nghiệp vụ hoặc tài chính |
| Health check | Thường bỏ qua quota khách hàng | Phục vụ kiểm tra vận hành, cần bảo vệ riêng khỏi lạm dụng |

Nếu dùng fallback local, phải có hard cap, thời gian hiệu lực ngắn và telemetry. Không để mỗi instance tự cho phép toàn bộ quota khi Redis mất kết nối; tổng mức vượt có thể tăng theo số instance. Với quota tính phí, cần ghi usage event bền vững và có reconciliation sau sự cố.

## 18. Tránh quota bypass và lạm dụng theo nhiều danh tính

Attacker có thể cố tình chia nhỏ lưu lượng hoặc thay đổi thông tin nhận diện:

- Tạo nhiều API key cho cùng tenant.
- Dùng nhiều user account trong cùng project.
- Thay IP, proxy hoặc địa chỉ mạng.
- Gọi các endpoint alias hoặc phiên bản API khác nhau để né counter.
- Chia một tác vụ lớn thành nhiều request nhỏ.
- Gửi request song song ngay trước thời điểm reset.
- Tạo nhiều job rồi hủy sau khi hệ thống đã tiêu thụ tài nguyên.

Biện pháp:

- Áp dụng bucket tổng theo tenant/account, ngoài bucket theo key/user.
- Tính quota theo business action hoặc resource cost, không chỉ route URL.
- Chuẩn hóa endpoint aliases về cùng metric/policy.
- Giới hạn batch size, page size, số job và concurrency.
- Dùng risk signal như tốc độ tăng usage, nhiều key mới, pattern truy vấn và lỗi bất thường.
- Có quota tổng hệ thống và circuit breaker để bảo vệ hạ tầng.
- Không dựa duy nhất vào IP; IP có thể dùng chung hoặc thay đổi hợp lệ.

Với thao tác có giá trị tiền, hãy tính cả tổng giá trị trong một khoảng thời gian và các giao dịch liên quan. Ví dụ, hạn mức 100 triệu đồng/ngày không nên bị né bằng cách gửi 100 giao dịch một triệu nếu policy dự kiến giới hạn tổng giá trị.

## 19. Ví dụ thiết kế policy và service trong Spring Boot

Controller nên nhận diện hành động, còn policy/quota service chịu trách nhiệm tính hạn mức và ghi nhận sử dụng. Ví dụ minh họa:

```java
@PostMapping("/api/v1/reports/exports")
public ExportJobResponse createExport(
        @Valid @RequestBody ExportRequest request,
        @AuthenticationPrincipal Jwt jwt,
        @RequestHeader("Idempotency-Key") String idempotencyKey) {

    UUID tenantId = tenantResolver.requireTenant(jwt);
    UUID userId = UUID.fromString(jwt.getSubject());

    return exportService.create(
        tenantId, userId, request, idempotencyKey);
}
```

Service kiểm tra entitlement, scope/object và reserve quota:

```java
@Transactional
public ExportJobResponse create(
        UUID tenantId,
        UUID userId,
        ExportRequest request,
        String idempotencyKey) {

    var existing = idempotencyStore.find(tenantId, idempotencyKey);
    if (existing.isPresent()) {
        existing.get().requireSameFingerprint(request);
        return existing.get().response();
    }

    PlanEntitlement plan = entitlementService.requireFeature(
        tenantId, "report.export");

    reportPolicy.requireReadableScope(tenantId, userId, request);
    int rowsToReserve = reportPolicy.maxRowsAllowed(plan, request);

    QuotaReservation reservation = quotaService.reserve(
        tenantId, "report.export.rows", rowsToReserve);

    ExportJob job = exportJobRepository.save(
        ExportJob.create(tenantId, userId, request, reservation.id()));

    idempotencyStore.save(tenantId, idempotencyKey, request, job);
    return ExportJobResponse.from(job);
}
```

Đây là code khung để minh họa luồng, không phải implementation hoàn chỉnh có thể biên dịch trực tiếp. Cần bảo đảm idempotency record, reservation và job được tạo nguyên tử hoặc có cơ chế outbox/compensation. `maxRowsAllowed` không được dựa vào số dòng client tự khai báo; service phải giới hạn truy vấn và đo usage thực tế. `quotaService.reserve` phải cập nhật bucket nguyên tử trong kho trạng thái dùng chung, không chỉ kiểm tra rồi tăng counter ở hai bước.

Worker hoàn tất job và settle quota:

```java
public void completeExport(UUID jobId, long actualRows) {
    ExportJob job = exportJobRepository.claimForCompletion(jobId);

    quotaService.settle(
        job.quotaReservationId(),
        actualRows,
        "report.export.rows");

    exportJobRepository.markCompleted(jobId, actualRows);
}
```

Trong thực tế, cập nhật trạng thái job và settle reservation cần idempotent, có transaction/outbox hoặc state transition nguyên tử. Nếu worker retry, không settle hai lần. Nếu worker chết, reservation có TTL và reconciliation job phải xử lý reservation treo.

## 20. Kiểm thử quota theo plan và business rule

Kiểm thử cần xác minh không chỉ counter mà cả entitlement, chủ thể, chu kỳ và side effect:

| Nhóm test | Tình huống |
|---|---|
| Plan entitlement | Plan không có feature thử gọi endpoint; plan hợp lệ dùng đúng tính năng |
| Identity | Tenant tạo nhiều key; quota tổng không bị nhân lên; tenant A không ảnh hưởng tenant B |
| Boundary | Request cuối vừa chạm quota; request tiếp theo bị từ chối; kiểm tra đúng thời điểm reset |
| Window | Fixed window burst ở ranh giới; rolling window và billing cycle khác nhau |
| Cost | Request nhỏ và export lớn bị tính theo cost/rows đúng policy |
| Concurrency | Nhiều request cùng tiêu thụ đơn vị cuối; không vượt quota do race condition |
| Multi-bucket | Một bucket hết hạn mức; các bucket khác được rollback/release đúng |
| Reservation | Job hoàn tất, thất bại, timeout, worker crash và reservation hết TTL |
| Retry | Cùng idempotency key không bị trừ hai lần; cùng key với payload khác bị từ chối |
| Upgrade/downgrade | Plan đổi giữa kỳ; cache cũ; usage đã vượt quota mới |
| Override | Ngoại lệ đúng scope và expiry; hết hạn thì policy gốc có hiệu lực |
| Failure mode | Redis/policy service unavailable; fallback không làm quota tăng theo số instance |
| Response | `429`, `Retry-After`, reset time và error code chính xác |
| Bypass | Nhiều key, endpoint alias, batch chia nhỏ, thay IP hoặc user |

Test phân tán nên chạy với nhiều application instance và nhiều request đồng thời. Test đơn luồng trong một JVM không phát hiện được lỗi counter cục bộ hoặc race condition giữa instance.

## 21. Giám sát và đối soát usage

Metric và audit nên cho biết client nào đang sử dụng quota nào, tốc độ ra sao và vì sao request bị từ chối. Các trường có thể ghi nhận:

- Tenant/client/project ID và key ID ở dạng định danh không bí mật.
- Plan ID, version policy và entitlement được áp dụng.
- Metric, đơn vị cost, period key và usage trước/sau.
- Reservation ID, job ID, idempotency key fingerprint và trạng thái settle.
- Route template, method, status code, request ID và thời gian xử lý.
- Lý do từ chối: feature disabled, quota exhausted, rate limit, concurrency hoặc payload limit.

Không ghi raw API key, access token, secret hoặc payload nhạy cảm vào log. Dùng identifier hoặc fingerprint đã được bảo vệ để nối các sự kiện.

Nên có dashboard cho usage theo plan, tenant, endpoint và chu kỳ; cảnh báo khi usage tăng đột biến, client gần hết quota, reservation treo, counter lệch với usage ledger hoặc override sắp hết hạn. Với quota tính phí, cần đối soát giữa usage ledger, counter vận hành và dữ liệu billing; counter Redis có thể phục vụ enforcement nhưng không nhất thiết là nguồn sự thật duy nhất cho hóa đơn.

## 22. Checklist thiết kế quota

- [ ] Chủ thể quota được xác định từ identity/subscription phía server, không lấy plan hoặc tenant từ client.
- [ ] Plan, entitlement, quota, rate limit, concurrency và resource limit được phân biệt rõ.
- [ ] Đơn vị tiêu thụ phản ánh chi phí hoặc tác động nghiệp vụ, không chỉ đếm request nếu chi phí khác nhau.
- [ ] Có bucket phù hợp theo key, user, tenant/project, endpoint và toàn hệ thống.
- [ ] Chu kỳ, timezone, reset, rollover và billing cycle được định nghĩa rõ.
- [ ] Request đồng thời được check-and-consume hoặc reserve nguyên tử.
- [ ] Tác vụ dài có reservation, commit/settle, release và TTL/reconciliation.
- [ ] Retry và idempotency không làm trừ quota trùng hoặc tạo nhiều job.
- [ ] Plan upgrade/downgrade, subscription hết hạn và grace period có quy tắc cụ thể.
- [ ] Override có người phê duyệt, phạm vi, lý do, thời hạn và audit.
- [ ] Hành vi fail-open/fail-closed được chọn theo rủi ro và có hard cap khi fallback.
- [ ] Response hết quota có status/error code và thời điểm reset/retry rõ ràng.
- [ ] Test bao gồm boundary, concurrency, multi-instance, bypass, failure và side effect.
- [ ] Usage được giám sát và đối soát; log không chứa credential hoặc dữ liệu nhạy cảm.

## Kết luận

Quota theo client plan quy định entitlement khách hàng được mua hoặc được cấp; business rule xác định cách giới hạn từng hành động và tài nguyên thực tế. Một thiết kế an toàn phải xác định đúng chủ thể tính quota, đơn vị tiêu thụ, chu kỳ, nhiều bucket áp dụng đồng thời và cách xử lý request song song, retry, plan change cùng ngoại lệ. Rate limit bảo vệ tốc độ, quota bảo vệ tổng mức sử dụng, concurrency và resource limit bảo vệ công suất của từng thao tác. Khi enforcement được thực hiện nguyên tử, response minh bạch, usage được giám sát và authorization vẫn được kiểm tra độc lập, hệ thống có thể bảo vệ hạ tầng đồng thời thực thi đúng quyền lợi và giới hạn của từng khách hàng.
