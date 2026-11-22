# Kiểm tra tương thích dữ liệu khi chạy lại phiên bản ứng dụng cũ

## 1. Vì sao rollback ứng dụng có thể làm hỏng dữ liệu?

Khi một bản phát hành mới gây lỗi, nhóm vận hành thường muốn đưa ứng dụng về phiên bản ổn định trước đó. Thao tác này có thể khôi phục mã nguồn và binary, nhưng database, message queue, cache và dữ liệu bên ngoài thường vẫn giữ những thay đổi mà phiên bản mới đã tạo ra.

Đây là điểm rủi ro quan trọng: **phiên bản ứng dụng cũ có thể không hiểu dữ liệu được phiên bản mới ghi ra**.

Ví dụ:

- Phiên bản mới ghi trạng thái đơn hàng là REFUNDED, nhưng phiên bản cũ chỉ biết PENDING, PAID và CANCELLED.
- Phiên bản mới lưu JSON có cấu trúc khác; phiên bản cũ không đọc được trường bắt buộc hoặc kiểu dữ liệu mới.
- Migration đã đổi đơn vị lưu từ đồng sang đơn vị tiền tệ lớn hơn, trong khi phiên bản cũ vẫn coi giá trị là đồng.
- Phiên bản mới ghi một bản ghi vào bảng mới và ngừng cập nhật bảng cũ; phiên bản cũ quay lại chỉ đọc bảng cũ nên thấy dữ liệu thiếu hoặc cũ.
- Message do phiên bản mới phát ra có schema mà consumer cũ không giải mã được.
- Session hoặc cache chứa dữ liệu mới khiến phiên bản cũ lỗi khi deserialize.

Vì vậy, rollback ứng dụng không đồng nghĩa rollback database. Muốn chạy lại phiên bản cũ an toàn, cần xác minh rằng phiên bản đó vẫn có thể đọc, ghi và xử lý những dữ liệu hiện đang tồn tại.

Trong phạm vi **DEVOPS_CI_CD_FUNDAMENTALS**, kiểm tra tương thích dữ liệu là một phần của chiến lược quay lui và phục hồi. Quyết định rollback phải dựa trên quan hệ giữa phiên bản ứng dụng, schema hiện tại, dữ liệu đã phát sinh, artifact, message và các hệ thống phụ thuộc.

## 2. Tương thích dữ liệu gồm những gì?

Không chỉ cấu trúc bảng mới ảnh hưởng đến khả năng chạy lại phiên bản cũ. Cần xem xét nhiều lớp:

| Lớp | Câu hỏi cần kiểm tra | Ví dụ rủi ro |
|---|---|---|
| Schema database | Cột, bảng, index và constraint cũ còn tồn tại không? | Phiên bản cũ query một cột đã bị DROP |
| Giá trị dữ liệu | Phiên bản cũ có hiểu các giá trị mới không? | Enum mới gây lỗi khi parse |
| Ngữ nghĩa | Giá trị còn mang ý nghĩa mà phiên bản cũ giả định không? | Số tiền đổi đơn vị nhưng code cũ vẫn tính theo đơn vị cũ |
| Quan hệ dữ liệu | Khóa ngoại, tính duy nhất và quan hệ bản ghi còn đúng không? | Bảng cũ không còn được cập nhật |
| Serialization | JSON, binary hoặc document có còn đọc được không? | Field mới bắt buộc hoặc kiểu dữ liệu bị đổi |
| Event và message | Consumer cũ có giải mã được message mới không? | Event version mới thêm enum hoặc đổi field |
| Cache và session | Dữ liệu tạm có thể được code cũ đọc không? | Session object mới không deserialize được |
| External side effect | Hệ thống bên ngoài đã nhận thay đổi không thể đảo ngược chưa? | Đã gửi thanh toán, email hoặc webhook |
| Quyền và cấu hình | Phiên bản cũ còn quyền hoặc cấu hình cần thiết không? | Secret, role hoặc endpoint cũ đã bị thu hồi |

Một rollback chỉ an toàn khi các lớp liên quan đều được đánh giá. Kiểm tra database schema đơn thuần chưa đủ.

## 3. Phân biệt tương thích ngược và tương thích xuôi

Hai khái niệm thường được dùng khi thiết kế thay đổi:

- **Backward compatibility (tương thích ngược):** phiên bản cũ vẫn hoạt động với schema hoặc dữ liệu mới được tạo theo cách có kiểm soát.
- **Forward compatibility (tương thích xuôi):** phiên bản mới có thể đọc hoặc xử lý dữ liệu được tạo bởi phiên bản cũ.

Khi chuẩn bị rollback, điều quan trọng là backward compatibility: dữ liệu hiện tại không được khiến ứng dụng cũ lỗi hoặc diễn giải sai.

Ví dụ, nếu phiên bản mới thêm một trường JSON tùy chọn và phiên bản cũ bỏ qua trường không biết, thay đổi có thể tương thích. Nhưng nếu phiên bản mới bắt đầu ghi một giá trị enum mà code cũ không nhận diện, rollback có thể thất bại dù schema database không thay đổi.

Không nên suy luận rằng một thay đổi tương thích xuôi thì cũng tương thích ngược. Mỗi chiều cần được kiểm tra riêng.

## 4. Mô hình phiên bản ứng dụng và trạng thái dữ liệu

Giả sử phiên bản hiện tại là N và bản phát hành mới là N+1. Khi N+1 đã chạy, hệ thống có thể chứa dữ liệu do cả hai phiên bản tạo ra.

| Trạng thái | Phiên bản N | Phiên bản N+1 | Khả năng rollback |
|---|---|---|---|
| Trước migration | Đọc/ghi schema cũ | Chưa triển khai | Bình thường |
| Schema được mở rộng | Hoạt động nếu bỏ qua cấu trúc mới | Có thể dùng cấu trúc mới | Thường còn an toàn |
| N+1 ghi cả định dạng cũ và mới | Đọc được nếu dữ liệu cũ được duy trì đúng | Đọc/ghi cả hai | Có thể an toàn sau validation |
| N+1 chỉ ghi định dạng mới | Có thể không thấy dữ liệu mới hoặc đọc sai | Hoạt động | Cần adapter hoặc chuyển đổi trước rollback |
| Giá trị mới đã xuất hiện | Có thể lỗi hoặc xử lý sai | Hoạt động | Phải kiểm tra mapping và semantics |
| Schema cũ đã bị loại bỏ | Không hoạt động | Hoạt động | Không thể chỉ rollback binary |

Ma trận này cần được lập trước khi release. Nếu không có dữ liệu về phiên bản nào đã ghi loại dữ liệu nào, khi sự cố xảy ra nhóm sẽ phải điều tra trong lúc hệ thống đang chịu tác động.

## 5. Những thay đổi thường phá vỡ khả năng chạy lại phiên bản cũ

### 5.1. Xóa hoặc đổi tên cột

Phiên bản cũ vẫn có thể chứa query tham chiếu cột cũ. Nếu migration đã xóa hoặc đổi tên cột, ứng dụng sẽ lỗi ngay khi thực hiện query.

Cách an toàn là thêm cột mới trước, triển khai ứng dụng tương thích, chuyển dữ liệu và giữ cột cũ qua thời gian quan sát. Chỉ contract sau khi chắc chắn không còn consumer cũ.

### 5.2. Thêm giá trị enum mới

Một cột VARCHAR có thể chấp nhận giá trị mới mà database không báo lỗi, nhưng code cũ có thể dùng enum đóng. Ví dụ Java:

~~~java
enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}

OrderStatus status = OrderStatus.valueOf(databaseValue);
~~~

Nếu phiên bản mới ghi REFUNDED, lệnh parse của phiên bản cũ sẽ ném exception. Cần đánh giá cách code cũ xử lý giá trị chưa biết trước khi cho phép ghi giá trị mới.

Các lựa chọn gồm:

- Triển khai phiên bản cũ có khả năng xử lý unknown value trước khi phát hành giá trị mới.
- Giữ giá trị lưu trữ trong tập mà cả hai phiên bản hiểu được trong thời gian chuyển tiếp.
- Dùng mapping hoặc compatibility adapter.
- Trì hoãn bật tính năng tạo giá trị mới cho đến khi rollback window kết thúc.

Không nên tự động map mọi trạng thái chưa biết thành một trạng thái mặc định nếu điều đó có thể làm sai nghiệp vụ.

### 5.3. Thay đổi ý nghĩa của dữ liệu

Một cột vẫn có cùng tên và cùng kiểu nhưng ý nghĩa có thể đã đổi. Ví dụ:

- Giá trị tiền tệ từ đơn vị nhỏ sang đơn vị lớn.
- Timestamp từ local time sang UTC.
- Trạng thái từ "đã gửi" sang "đã được nhà cung cấp xác nhận".
- Boolean cũ được thay bằng ba trạng thái.
- Số lượng được lưu theo đơn vị đóng gói thay vì đơn vị cơ sở.

Phiên bản cũ có thể đọc được kiểu dữ liệu nhưng tính toán sai. Đây là lỗi nguy hiểm vì không nhất thiết tạo exception hoặc health check thất bại.

### 5.4. Thay đổi JSON hoặc document

Nếu ứng dụng lưu JSON trong database hoặc object store, phiên bản mới có thể đổi tên field, thay kiểu hoặc thêm field bắt buộc. Cần kiểm tra cấu hình serializer/deserializer của phiên bản cũ, bao gồm cách xử lý unknown field, missing field, null và default.

### 5.5. Thay đổi quan hệ hoặc tính duy nhất

Phiên bản mới có thể chuyển quan hệ từ một bảng sang bảng khác, thay đổi khóa hoặc thay đổi quy tắc unique. Nếu phiên bản cũ vẫn giả định quan hệ cũ, nó có thể trả kết quả thiếu, tạo bản ghi trùng hoặc cập nhật sai đối tượng.

## 6. Dùng expand-contract để giữ cửa rollback

Expand-contract giúp schema mới tồn tại mà không phá khả năng hoạt động của phiên bản cũ.

~~~mermaid
flowchart TD
    A["Ứng dụng N và schema cũ"] --> B["EXPAND: thêm cột/bảng mới"]
    B --> C["Deploy N+1 tương thích cả hai"]
    C --> D["Ghi kép hoặc đồng bộ có kiểm soát"]
    D --> E["Backfill và đối soát dữ liệu"]
    E --> F["Switch sang cấu trúc mới"]
    F --> G["Giữ compatibility window"]
    G --> H{"Còn cần rollback N?"}
    H -- "Có" --> I["Giữ cấu trúc và dữ liệu cũ tương thích"]
    H -- "Không" --> J["CONTRACT: loại bỏ cấu trúc cũ"]
~~~

Các nguyên tắc:

1. Thêm cấu trúc mới mà không xóa cấu trúc cũ.
2. Triển khai code có thể xử lý cả trạng thái trước và sau migration.
3. Duy trì dữ liệu cần thiết cho phiên bản cũ trong rollback window.
4. Kiểm tra dữ liệu và consumer trước khi chuyển hoàn toàn.
5. Chỉ xóa cấu trúc cũ trong release riêng sau khi hết nhu cầu tương thích.

Nếu cần rollback N trong giai đoạn này, nhóm có thể đưa binary cũ trở lại mà schema cũ vẫn còn. Tuy nhiên, vẫn phải kiểm tra các giá trị mà N+1 đã ghi.

## 7. Duy trì dữ liệu tương thích khi N+1 ghi dữ liệu

Có nhiều cách giữ cho dữ liệu mới vẫn đọc được bởi phiên bản cũ. Không có một cách phù hợp cho mọi hệ thống; lựa chọn phụ thuộc vào việc dữ liệu nằm trong cùng database hay nhiều hệ thống.

### 7.1. Dual-write trong cùng transaction

Nếu dữ liệu cũ và mới nằm trong cùng database, ứng dụng có thể cập nhật cả hai biểu diễn trong cùng transaction:

~~~sql
UPDATE orders
SET legacy_status = :legacy_value,
    normalized_status = :normalized_value
WHERE id = :order_id;
~~~

Cách này giúp phiên bản cũ tiếp tục đọc cột cũ trong khi phiên bản mới dùng cột mới. Nhưng mọi đường ghi đều phải được cập nhật, bao gồm API, worker, batch job, admin tool và integration.

Nếu một đường ghi chỉ cập nhật cột mới hoặc chỉ cập nhật cột cũ, hai biểu diễn sẽ lệch nhau. Cần metric, reconciliation và kiểm thử cho tất cả writer.

### 7.2. Compatibility adapter

Một lớp chuyển đổi có thể biến dữ liệu mới về định dạng cũ khi phiên bản cũ cần sử dụng. Adapter có thể nằm trong ứng dụng, API hoặc một lớp truy cập dữ liệu.

Adapter cần có quy tắc rõ ràng cho từng giá trị. Nếu một trạng thái mới không có ý nghĩa tương đương trong mô hình cũ, không nên ép thành giá trị gần giống chỉ để tránh lỗi kỹ thuật. Cần quyết định nghiệp vụ: giữ tính năng ở trạng thái tắt, chặn rollback hay thực hiện roll-forward.

### 7.3. Read fallback

Trong thời gian chuyển tiếp, ứng dụng có thể ưu tiên đọc cấu trúc mới và fallback sang cấu trúc cũ khi dữ liệu mới chưa tồn tại. Cần tránh fallback che giấu dữ liệu hỏng: NULL do chưa backfill khác với NULL do lỗi ghi.

Nên ghi nhận nguồn dữ liệu được dùng và số lần fallback để biết khi nào có thể loại bỏ đường tương thích.

### 7.4. Không dual-write mù quáng giữa hai hệ thống

Nếu hai nơi lưu dữ liệu độc lập, dual-write có thể thành công ở một nơi nhưng thất bại ở nơi kia. Nên cân nhắc transactional outbox, CDC, retry idempotent và reconciliation. Cần biết rõ nơi nào là source of truth trong mỗi giai đoạn.

## 8. Kiểm tra enum, status và giá trị mới

Giá trị enum là một trong những nguyên nhân phổ biến làm phiên bản cũ không đọc được dữ liệu mới.

Cần lập bảng mapping:

| Giá trị được N+1 ghi | N hiểu được? | Cách xử lý khi rollback |
|---|---|---|
| PENDING | Có | Giữ nguyên |
| PAID | Có | Giữ nguyên |
| CANCELLED | Có | Giữ nguyên |
| REFUNDED | Không | Dừng phát sinh, adapter hoặc roll-forward |
| DISPUTED | Không | Xác định semantics; không map tùy tiện |

Cần kiểm tra cả database constraint và code. Database có thể chấp nhận một giá trị mà code cũ không biết. Ngược lại, code mới có thể biết giá trị nhưng constraint cũ không cho phép ghi.

Nếu phiên bản cũ dùng switch expression hoặc enum deserialization nghiêm ngặt, unknown value có thể gây exception. Nếu code có nhánh default, cần xác minh nhánh đó có bảo toàn nghiệp vụ hay chỉ che lỗi.

## 9. Kiểm tra JSON, serialized object và document

Dữ liệu có thể được lưu dưới dạng JSON trong database, file object storage, cache hoặc message.

Khi thay đổi schema JSON, cần kiểm tra:

- Field cũ có còn không.
- Field mới có bắt buộc không.
- Kiểu dữ liệu có đổi không.
- Null và missing field có ý nghĩa khác nhau không.
- Unknown field có bị serializer cũ từ chối không.
- Enum và timestamp có định dạng mới không.
- Version của document có được lưu không.

Một mẫu JSON tương thích có thể giữ field cũ trong thời gian chuyển tiếp:

~~~json
{
  "schemaVersion": 2,
  "status": "PAID",
  "legacyStatus": "settled"
}
~~~

Ví dụ này minh họa việc giữ thông tin cũ để code cũ hoặc adapter có thể sử dụng. Trước khi contract cần xác định không còn consumer nào phụ thuộc legacyStatus.

Với Java serialization hoặc serialized object phụ thuộc class name/serialVersionUID, thay đổi class có thể làm phiên bản cũ không deserialize được. Không nên dùng Java native serialization làm định dạng lưu trữ dài hạn nếu cần tương thích giữa nhiều phiên bản. Với format có schema như Avro hoặc Protobuf, cần kiểm tra compatibility rule và schema registry theo đúng chiều đọc/ghi.

## 10. Kiểm tra kiểu dữ liệu, precision và semantics

Các thay đổi kiểu dữ liệu cần được kiểm tra bằng giá trị thực tế, không chỉ bằng việc migration chạy thành công.

| Thay đổi | Rủi ro với phiên bản cũ | Kiểm tra cần có |
|---|---|---|
| Integer sang decimal | Tràn số hoặc mất phần thập phân | Giá trị biên và quy tắc làm tròn |
| Đồng sang đơn vị tiền khác | Sai hệ số khi tính toán | Unit conversion và tổng tiền |
| Local time sang UTC | Lệch ngày/giờ | Timezone, daylight saving và boundary |
| String sang enum | Unknown value | Mapping và nhánh xử lý mặc định |
| Nullable sang NOT NULL | Insert/update của code cũ thất bại | Tất cả writer và default |
| ID đổi định dạng | Parse hoặc so sánh sai | Định dạng, sort và quan hệ |
| Boolean sang nhiều trạng thái | Mất thông tin khi quy về true/false | Quy tắc mapping có chủ đích |

Nếu chuyển đổi mất thông tin, ví dụ nhiều trạng thái mới bị gộp vào một trạng thái cũ, rollback có thể không thể khôi phục ngữ nghĩa ban đầu. Cần nhận diện đây là giới hạn thiết kế và cân nhắc giữ dữ liệu gốc hoặc chọn roll-forward.

## 11. Kiểm tra message, event và consumer

Rollback ứng dụng có thể làm consumer cũ nhận message được phát bởi phiên bản mới. Đây là vấn đề tương thích độc lập với database.

Cần kiểm tra:

- Producer mới có thêm hoặc đổi field không.
- Consumer cũ có bỏ qua field không biết không.
- Enum mới có gây lỗi deserialize không.
- Có thay đổi partition key hoặc ordering không.
- Message cũ còn nằm trong queue bao lâu.
- Dead-letter queue có chứa message schema mới không.
- Consumer có thể đọc message đã phát sau khi rollback không.

Nếu message mới không tương thích với consumer cũ, có thể cần giữ producer ở schema cũ trong compatibility window, dùng versioned event hoặc triển khai consumer hỗ trợ cả hai trước khi phát event mới.

Không nên giả định rollback producer sẽ xóa message đã được publish. Queue có thể giữ message mới trong nhiều giờ hoặc nhiều ngày. Cần kiểm tra backlog và xử lý message tồn đọng trước khi đưa consumer cũ trở lại.

## 12. Cache, session và dữ liệu tạm

Cache và session thường bị bỏ qua khi lập kế hoạch rollback, nhưng chúng có thể giữ cấu trúc object hoặc giá trị do phiên bản mới tạo.

Ví dụ:

- Session mới có field bắt buộc mà phiên bản cũ không biết.
- Cache value đổi từ chuỗi sang JSON.
- Cache key thay đổi nhưng phiên bản cũ vẫn đọc key cũ.
- Object trong distributed cache được serialize theo class mới.
- Feature flag hoặc config snapshot được lưu trong cache.

Các cách giảm rủi ro:

- Version hóa cache key hoặc payload.
- Giữ serializer tương thích trong thời gian chuyển tiếp.
- Cho phép cache miss và tái tạo từ source of truth.
- Xóa có chọn lọc các cache không thể đọc an toàn trước khi rollback.
- Không xóa session đang hoạt động nếu làm người dùng bị đăng xuất ngoài dự kiến.
- Kiểm thử phiên bản cũ với cache value do phiên bản mới tạo.

Xóa cache có thể là biện pháp khôi phục phù hợp khi cache là dữ liệu dẫn xuất. Nhưng không được xóa dữ liệu duy nhất hoặc trạng thái nghiệp vụ đang lưu trong cache mà chưa hiểu tác động.

## 13. Tương thích với side effect và hệ thống bên ngoài

Một số thao tác của phiên bản mới không thể đơn giản đảo ngược bằng cách chạy lại binary cũ:

- Thanh toán đã được gửi tới payment provider.
- Email hoặc SMS đã được gửi.
- Webhook đã được chuyển tới đối tác.
- Message đã kích hoạt workflow downstream.
- File đã được xuất sang object storage.
- Giao dịch đã được ghi nhận ở hệ thống kế toán.

Cần phân biệt rollback code với compensation nghiệp vụ. Ví dụ, một giao dịch thanh toán đã capture có thể cần refund qua API của nhà cung cấp; việc deploy lại phiên bản cũ không tự hoàn tác khoản tiền đó.

Trước release, xác định side effect nào có thể bù trừ, thao tác nào idempotent và cách đối soát khi không biết request đã được xử lý hay chưa. Với workflow phân tán, cần có correlation ID và trạng thái giao dịch để tránh gửi lặp khi phục hồi.

## 14. Feature flag và giới hạn dữ liệu mới trong rollback window

Feature flag có thể kiểm soát thời điểm phiên bản mới bắt đầu tạo dữ liệu mà phiên bản cũ không hiểu.

Một chiến lược có thể là:

1. Deploy code mới nhưng giữ tính năng tạo giá trị mới ở trạng thái tắt.
2. Xác minh code và schema tương thích.
3. Bật tính năng cho cohort nhỏ.
4. Theo dõi dữ liệu mới và kiểm tra rollback compatibility.
5. Chỉ mở rộng khi đã chấp nhận rằng phiên bản cũ có thể không còn là phương án rollback.
6. Sau compatibility window, loại bỏ adapter và cấu trúc cũ theo kế hoạch.

Feature flag không tự làm cho dữ liệu tương thích. Nó chỉ giúp kiểm soát thời điểm bắt đầu tạo dữ liệu mới. Cần bảo đảm mọi đường ghi đều tôn trọng flag, bao gồm worker và job nền.

## 15. Xác định rollback có an toàn hay phải roll-forward

Không phải lúc nào rollback ứng dụng cũng là lựa chọn tốt nhất. Cần đánh giá dữ liệu đã được tạo và khả năng đọc của phiên bản cũ.

| Tình huống | Hướng xử lý thường phù hợp |
|---|---|
| Lỗi chỉ nằm trong code, schema và dữ liệu vẫn tương thích | Rollback binary/artifact |
| Schema được mở rộng, chưa xóa cấu trúc cũ | Thường có thể rollback sau compatibility check |
| N+1 đã ghi enum mới mà N không hiểu | Dừng tạo giá trị mới, chuyển đổi có kiểm soát hoặc roll-forward |
| Dữ liệu đã đổi semantics hoặc mất thông tin | Thường ưu tiên roll-forward hoặc compensation |
| Schema cũ đã bị DROP | Cần restore/recreate schema tương thích hoặc roll-forward; không chỉ rollback binary |
| External side effect đã xảy ra | Dùng quy trình compensation và đối soát |
| Không đủ dữ liệu để chứng minh tương thích | Giữ rollout/đánh giá thêm; không tuyên bố rollback an toàn |

Quyết định cần xét cả tác động người dùng, khả năng khôi phục dữ liệu, thời gian phục hồi và nguy cơ làm tình trạng tệ hơn. Roll-forward có thể an toàn hơn khi dữ liệu mới không thể được diễn giải đúng bởi phiên bản cũ.

## 16. Quy trình kiểm tra trước khi rollback

Trước khi đưa phiên bản cũ trở lại, cần thu thập thông tin:

1. **Xác định artifact cũ:** lấy đúng digest hoặc package đã chạy ổn định trước đó.
2. **Xác định trạng thái database:** migration nào đã chạy, schema hiện tại và constraint nào đã thay đổi.
3. **Xác định dữ liệu mới:** các giá trị, format hoặc quan hệ mà phiên bản mới đã ghi.
4. **Xác định writer:** API, worker, batch và consumer nào đã tạo dữ liệu đó.
5. **Kiểm tra đọc:** phiên bản cũ có thể đọc dữ liệu mới mà không lỗi hoặc diễn giải sai không?
6. **Kiểm tra ghi:** phiên bản cũ có thể tiếp tục ghi mà không làm mất hoặc phá dữ liệu mới không?
7. **Kiểm tra side effect:** message, payment, webhook và file đã phát sinh có được xử lý đúng không?
8. **Kiểm tra tương thích hạ tầng:** runtime, secret, permission, endpoint và cấu hình còn phù hợp không?
9. **Chọn hành động:** rollback trực tiếp, chuyển đổi dữ liệu, tắt tính năng mới hay roll-forward.
10. **Ghi quyết định:** lưu bằng chứng, người phê duyệt, artifact digest và kế hoạch xác minh.

Không nên chạy thử phiên bản cũ trực tiếp trên production data nếu chưa có biện pháp cô lập. Có thể dùng bản sao dữ liệu đã làm sạch hoặc môi trường rehearsal tương đương để xác minh trước.

## 17. Thực hiện rollback có kiểm soát

Khi đã xác nhận tương thích:

1. Dừng hoặc giới hạn các luồng ghi tạo thêm dữ liệu mới không tương thích.
2. Tạm dừng worker hoặc consumer liên quan nếu cần.
3. Lưu lại release ID, artifact digest, migration version và thời điểm.
4. Triển khai artifact cũ đã xác minh.
5. Giữ schema mở rộng nếu phiên bản cũ có thể bỏ qua cấu trúc mới.
6. Xác minh kết nối database, query quan trọng và health check.
7. Chạy smoke test trên các luồng nghiệp vụ trọng yếu.
8. Kiểm tra message backlog, cache, session và side effect.
9. Theo dõi error rate, latency, dữ liệu sai lệch và retry.
10. Chỉ mở lại traffic hoặc worker khi điều kiện đạt.

Không nên tự động chạy down migration cùng lúc rollback ứng dụng. Một migration phá hủy dữ liệu hoặc xóa cột có thể làm phiên bản cũ hoạt động kém hơn. Schema có thể được giữ ở trạng thái mở rộng cho đến khi nhóm xác định được bước tiếp theo.

## 18. Kiểm tra sau rollback

Rollback thành công về mặt triển khai chỉ là bước đầu. Cần xác minh rằng phiên bản cũ xử lý đúng dữ liệu hiện có.

Các kiểm tra nên gồm:

- Artifact digest đang chạy đúng phiên bản đã chọn.
- Ứng dụng khởi động và readiness ổn định.
- Không có lỗi deserialize hoặc enum parse tăng đột biến.
- Query cũ không tham chiếu cột đã mất.
- Không có bản ghi mới bị bỏ sót do chỉ ghi ở cấu trúc mới.
- Các invariant nghiệp vụ vẫn đúng.
- Worker và consumer xử lý được backlog.
- Không có side effect bị gửi trùng.
- Cache/session hoạt động hoặc đã được xử lý an toàn.
- SLI/SLO trở lại mức chấp nhận được.

Nên so sánh số liệu trước và sau rollback. Nếu error rate giảm nhưng số giao dịch thất bại hoặc mismatch tăng, hệ thống chưa thực sự phục hồi.

## 19. Kiểm thử rollback trong CI/CD

Rollback compatibility cần được kiểm thử trước khi release, không nên chỉ dựa vào runbook trên giấy.

Một ma trận kiểm thử có thể gồm:

| Bài kiểm thử | Đầu vào | Kết quả mong đợi |
|---|---|---|
| Old app + expanded schema | Schema đã thêm cột/bảng mới | Phiên bản cũ vẫn chạy |
| Old app + data from new app | Fixture có giá trị và JSON mới | Đọc đúng hoặc từ chối có kiểm soát theo policy |
| Old app + new enum | Bản ghi chứa giá trị mới | Không crash hoặc có hành động fallback rõ ràng |
| Old writer + expanded schema | Ghi từ phiên bản cũ | Không làm hỏng dữ liệu mới |
| Old consumer + new event | Message schema mới | Consumer đọc được hoặc routing được xử lý |
| Rollback after partial backfill | Một phần dữ liệu đã chuyển | Ứng dụng cũ vẫn hoạt động hoặc có quy trình phục hồi |
| Retry and replay | Message hoặc batch được xử lý lại | Không tạo duplicate hoặc sai trạng thái |

Các kỹ thuật hữu ích:

- Integration test với database migration thật.
- Contract test giữa producer và consumer.
- Test deserialization bằng binary của phiên bản cũ.
- Fixture đại diện cho dữ liệu trước và sau migration.
- Restore snapshot trong môi trường cô lập.
- Rollback rehearsal trên staging.
- Kiểm thử failure giữa chừng khi backfill hoặc cutover.

Chỉ kiểm thử phiên bản mới với schema mới là chưa đủ. Cần chạy binary cũ trên dữ liệu mà phiên bản mới có thể tạo.

## 20. Ví dụ: phiên bản mới thêm trạng thái REFUNDED

Giả sử phiên bản N chỉ hiểu các trạng thái PENDING, PAID, CANCELLED. Phiên bản N+1 bổ sung REFUNDED và bắt đầu ghi giá trị này sau khi refund thành công.

Nếu N+1 gặp lỗi và nhóm triển khai lại N:

- Query database vẫn chạy vì cột status vẫn là VARCHAR.
- Nhưng code N gọi enum parser và lỗi với REFUNDED.
- Một số API trả 500 khi đọc đơn hàng đã refund.
- Worker cũ có thể retry message liên tục.
- Dashboard có thể chỉ phát hiện lỗi sau khi request của nhóm dữ liệu này tăng lên.

Các phương án:

**Trước khi mở tính năng:** nếu cần giữ khả năng quay về dòng N, hãy chuẩn bị một bản vá tương thích trên dòng phiên bản đó hoặc một adapter để xử lý unknown status. Nếu không thể thay đổi binary cũ và không có adapter an toàn, chưa bật tính năng tạo giá trị mới trong rollback window.

**Khi đã có dữ liệu REFUNDED:** xác định xem có thể ánh xạ về trạng thái cũ mà vẫn giữ được ý nghĩa nghiệp vụ không. Nếu không, không được gán tùy tiện thành CANCELLED hoặc PAID. Có thể giữ N+1, phát hành bản sửa tương thích hoặc roll-forward.

**Nếu cần khôi phục ngay:** tắt luồng tạo trạng thái mới, giữ nguyên dữ liệu refund và dùng phiên bản có thể đọc nó. Xử lý các request và báo cáo cần thiết bằng adapter hoặc phiên bản tương thích. Không xóa dữ liệu refund chỉ để làm cho enum cũ parse được.

## 21. Tự động hóa kiểm tra tương thích trong pipeline

Pipeline có thể tạo một compatibility gate trước khi cho phép phát hành:

~~~mermaid
flowchart TD
    A["Pull request và migration"] --> B["Schema compatibility tests"]
    A --> C["Data mapping tests"]
    A --> D["Event/API contract tests"]
    B --> E["Build artifact N+1"]
    C --> E
    D --> E
    E --> F["Tạo fixture dữ liệu do N+1 ghi"]
    F --> G["Chạy binary N trên schema và fixture mới"]
    G --> H{"Rollback compatibility đạt?"}
    H -- "Không" --> I["Chặn release hoặc yêu cầu kế hoạch roll-forward"]
    H -- "Có" --> J["Publish artifact và compatibility evidence"]
    J --> K["Deploy theo chiến lược"]
~~~

Gate có thể ghi các thuộc tính:

- Phiên bản ứng dụng cũ được kiểm thử.
- Phiên bản schema được kiểm thử.
- Migration đã áp dụng.
- Bộ fixture và data format version.
- Kết quả đọc/ghi của phiên bản cũ.
- Consumer và event schema liên quan.
- Các giới hạn tương thích đã biết.
- Quyết định rollback hoặc roll-forward.

Ví dụ policy dạng mã giả:

~~~yaml
rollback_compatibility:
  old_application: "release-N"
  candidate_application: "release-N-plus-1"
  database_schema: "schema-after-expand"

  checks:
    - old_binary_reads_new_records
    - old_binary_writes_without_data_loss
    - old_enum_parser_handles_unknown_values
    - old_consumer_reads_new_events
    - cache_and_session_compatibility
    - business_invariants_pass

  on_failure:
    release_action: BLOCK_OR_REQUIRE_FORWARD_RECOVERY_PLAN
~~~

Đây là cấu trúc minh họa, không phải schema chuẩn của một nền tảng CI. Trong hệ thống thật, cần chạy đúng binary cũ và database engine/version mục tiêu, không chỉ mô phỏng bằng unit test.

## 22. Lưu bằng chứng và quản lý rollback window

Mỗi release nên lưu:

- Artifact digest của phiên bản hiện tại và phiên bản trước.
- Migration ID/version và trạng thái đã chạy.
- Schema version hoặc schema fingerprint.
- Data format/version liên quan.
- Feature flag và thời điểm bật.
- Event schema version.
- Kết quả rollback compatibility test.
- Những giá trị hoặc thao tác chưa tương thích ngược.
- Người phê duyệt và thời hạn rollback window.

Rollback window là khoảng thời gian nhóm cam kết có thể đưa phiên bản trước trở lại theo một quy trình đã kiểm chứng. Hết thời gian này, một số thay đổi contract hoặc dữ liệu mới có thể làm rollback trực tiếp không còn an toàn.

Không nên đặt rollback window chỉ theo lịch. Cần dựa trên thời gian quan sát, chu kỳ nghiệp vụ, thời gian tồn tại của message, batch và các consumer ít chạy. Ví dụ, một báo cáo chạy hàng tuần có thể vẫn phụ thuộc cột cũ dù hệ thống API đã chuyển đổi từ lâu.

## 23. Những anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách cải thiện |
|---|---|---|
| Cho rằng rollback binary sẽ đảo database | Schema và dữ liệu vẫn ở trạng thái mới | Kiểm tra schema và data compatibility riêng |
| Xóa cột cũ cùng release chuyển đổi | Phiên bản cũ không thể query | Dùng expand-contract và compatibility window |
| Ghi enum mới trước khi old app hiểu | Lỗi parse hoặc xử lý sai | Kiểm tra unknown value và kiểm soát feature |
| Chỉ test schema, không test dữ liệu | Code cũ vẫn có thể đọc sai semantics | Dùng fixture do phiên bản mới tạo |
| Chỉ kiểm tra web service | Worker hoặc consumer cũ có thể lỗi | Kiểm tra mọi writer và reader |
| Hạ giá trị mới về default tùy tiện | Mất ý nghĩa nghiệp vụ | Mapping có kiểm soát hoặc roll-forward |
| Down migration tự động khi rollback | Có thể xóa dữ liệu mới | Giữ schema mở rộng và đánh giá riêng |
| Bỏ qua queue và cache | Consumer/session lỗi sau rollback | Kiểm tra message backlog, cache và session |
| Không lưu artifact cũ | Phải build lại trong sự cố | Giữ artifact bất biến theo digest |
| Không diễn tập rollback | Runbook không phản ánh thực tế | Rehearsal với binary cũ và dữ liệu mới |

## 24. Checklist trước khi cho phép rollback ứng dụng cũ

**Schema và dữ liệu**

- [ ] Schema cũ mà phiên bản cũ cần vẫn còn.
- [ ] Không có cột, bảng hoặc constraint bị thay đổi ngoài khả năng tương thích.
- [ ] Phiên bản cũ hiểu các enum và giá trị mới.
- [ ] Kiểu dữ liệu, đơn vị, timezone và semantics không bị hiểu sai.
- [ ] JSON/document và serialized payload được kiểm thử.
- [ ] Quan hệ, unique constraint và invariant vẫn đúng.

**Writer, reader và message**

- [ ] Tất cả API, worker, batch và admin tool đã được xem xét.
- [ ] Dữ liệu mới được ghi vào cấu trúc cũ khi cần rollback.
- [ ] Message mới tương thích với consumer cũ hoặc có kế hoạch xử lý.
- [ ] Queue backlog và dead-letter đã được đánh giá.
- [ ] Cache và session có thể được đọc hoặc làm mới an toàn.
- [ ] External side effect có quy trình compensation/đối soát.

**Thực hiện và xác minh**

- [ ] Artifact cũ đã được lưu và xác định bằng digest.
- [ ] Binary cũ đã được thử với schema và fixture dữ liệu mới.
- [ ] Có quyết định rõ rollback hay roll-forward.
- [ ] Không chạy down migration phá hủy dữ liệu một cách tự động.
- [ ] Có runbook dừng writer/worker và chuyển traffic.
- [ ] Sau rollback có smoke test, invariant và SLI/SLO.
- [ ] Có bằng chứng và người chịu trách nhiệm cho quyết định.

## 25. Kết luận

Chạy lại phiên bản ứng dụng cũ chỉ an toàn khi dữ liệu hiện tại vẫn nằm trong phạm vi mà phiên bản đó có thể đọc, ghi và diễn giải đúng. Rủi ro có thể đến từ schema đã thay đổi, enum mới, JSON mới, semantics khác, event backlog, cache/session hoặc side effect ở hệ thống ngoài.

Expand-contract, compatibility adapter, ghi dữ liệu theo định dạng tương thích và kiểm thử binary cũ trên fixture do phiên bản mới tạo giúp giữ cửa rollback. Trước khi rollback cần xác định migration đã chạy, dữ liệu mới đã phát sinh và mọi consumer liên quan. Khi dữ liệu đã thay đổi không thể đảo ngược mà vẫn giữ đúng nghiệp vụ, roll-forward hoặc compensation thường phù hợp hơn việc ép phiên bản cũ xử lý một trạng thái mà nó không hiểu.

Một release có khả năng phục hồi cần giữ artifact cũ, version hóa schema và dữ liệu, lưu bằng chứng kiểm thử tương thích, đồng thời xác minh sau khi chuyển phiên bản. Nhờ đó, quyết định rollback dựa trên khả năng tương thích thực tế thay vì giả định rằng đổi binary là đủ.
