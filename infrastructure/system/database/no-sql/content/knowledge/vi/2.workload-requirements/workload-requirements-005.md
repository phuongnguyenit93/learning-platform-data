# Phân biệt dữ liệu giao dịch, sự kiện, tài liệu, chuỗi thời gian và dữ liệu dẫn xuất

Khi thiết kế hệ thống lưu trữ, câu hỏi đầu tiên không nên là “dùng SQL hay NoSQL?”, mà là **dữ liệu này có ý nghĩa gì, phát sinh như thế nào, thay đổi ra sao và ứng dụng cần đọc nó theo cách nào?** Một hệ thống có thể đồng thời lưu đơn hàng, lịch sử các hành động, hồ sơ người dùng, số đo thiết bị và báo cáo tổng hợp. Những dữ liệu đó có yêu cầu rất khác nhau về tính nhất quán, tốc độ ghi, kiểu truy vấn và thời gian lưu giữ.

Năm khái niệm thường gặp là:

1. **Dữ liệu giao dịch** (*transactional data*): ghi nhận trạng thái nghiệp vụ và các thay đổi phải tuân theo quy tắc đúng đắn.
2. **Dữ liệu sự kiện** (*event data*): ghi lại một sự việc đã xảy ra tại một thời điểm.
3. **Dữ liệu tài liệu** (*document data*): biểu diễn thông tin thành các tài liệu có cấu trúc, thường là các đối tượng với trường và dữ liệu lồng nhau.
4. **Dữ liệu chuỗi thời gian** (*time-series data*): các quan sát hoặc số đo được tổ chức chủ yếu theo thời gian.
5. **Dữ liệu dẫn xuất** (*derived data*): kết quả được tính toán, biến đổi hoặc lập chỉ mục từ dữ liệu khác.

Đây **không phải năm nhóm loại trừ lẫn nhau**. Chúng mô tả những góc nhìn khác nhau: vai trò nghiệp vụ, nguồn phát sinh, hình thức biểu diễn, cách truy cập và quan hệ nguồn–kết quả. Chẳng hạn một đơn hàng có thể được lưu dưới dạng tài liệu JSON **và** đồng thời là dữ liệu giao dịch; một chuỗi số đo cảm biến có thể được thu nhận như các sự kiện; một báo cáo doanh thu theo ngày vừa là dữ liệu dẫn xuất vừa là chuỗi thời gian.

## 1. Bản đồ khái niệm: phân biệt theo câu hỏi cần trả lời

| Nhóm | Câu hỏi nhận diện | Ví dụ tiêu biểu | Đặc trưng thường gặp |
| --- | --- | --- | --- |
| **Giao dịch** | “Trạng thái nghiệp vụ nào phải được cập nhật chính xác?” | Đơn hàng, số dư, đặt chỗ, thanh toán | Quy tắc bất biến, thao tác cập nhật, tính nhất quán và xử lý đồng thời |
| **Sự kiện** | “Điều gì đã xảy ra, với ai và khi nào?” | `OrderPlaced`, `PaymentSucceeded`, `UserLoggedIn` | Bổ sung sự kiện, lưu thời điểm, định danh, phát lại và xử lý bất đồng bộ |
| **Tài liệu** | “Thông tin nào có thể đóng gói thành một đối tượng để đọc/ghi cùng nhau?” | Hồ sơ sản phẩm, thông tin người dùng, đơn hàng gồm nhiều dòng hàng | Trường linh hoạt, đối tượng/mảng lồng nhau, truy xuất theo tài liệu |
| **Chuỗi thời gian** | “Giá trị nào thay đổi theo thời gian?” | Nhiệt độ mỗi phút, CPU mỗi giây, giá theo giờ | Dấu thời gian, dải thời gian, lấy mẫu, tổng hợp theo cửa sổ |
| **Dẫn xuất** | “Kết quả nào được tạo từ dữ liệu nguồn để phục vụ một nhu cầu khác?” | Tổng doanh thu/ngày, search index, cache, bảng xếp hạng | Có nguồn gốc dữ liệu, công thức/luồng biến đổi và cơ chế làm mới |

Điểm cốt lõi: **“giao dịch”, “sự kiện”, “chuỗi thời gian” và “dẫn xuất” thường nói nhiều đến mục đích, nguồn gốc hoặc tải truy cập; “tài liệu” nhấn mạnh cách tổ chức dữ liệu**. Vì vậy, không thể dựa vào phần mở rộng `.json`, sự hiện diện của `timestamp`, hay tên một DBMS để tự động phân loại dữ liệu.

Để nhận diện đúng, hãy xét đồng thời bốn trục:

```text
                  DỮ LIỆU CẦN LƯU
                         │
          ┌──────────────┼────────────────┐
          ▼              ▼                ▼
    Ý nghĩa nghiệp vụ  Hình dạng       Cách phát sinh
    - trạng thái       - bảng          - nguồn gốc
    - sự việc          - tài liệu       - đo đạc
    - phép đo          - bản ghi        - biến đổi
          └──────────────┼────────────────┘
                         ▼
                Yêu cầu vận hành
          ghi/đọc, đồng thời, độ trễ,
          nhất quán, lưu giữ, phát lại
```

## 2. Dữ liệu giao dịch: trạng thái nghiệp vụ cần đúng

**Dữ liệu giao dịch** mô tả đối tượng và trạng thái mà hệ thống vận hành dựa vào để thực hiện các quy tắc nghiệp vụ. Ví dụ, đơn hàng có trạng thái hiện tại, kho hàng có số lượng còn lại, tài khoản có số dư và hệ thống đặt vé có số ghế còn trống.

Giả sử hệ thống bán hàng có một bản ghi:

```json
{
  "orderId": "O-1042",
  "customerId": "C-08",
  "status": "PAID",
  "totalVnd": 350000,
  "updatedAt": "2026-10-12T09:15:00Z",
  "version": 3
}
```

Đối với dữ liệu này, câu hỏi không chỉ là “đọc được bản ghi hay không”, mà còn là **bản ghi có phản ánh đúng trạng thái được phép của nghiệp vụ hay không**. Ví dụ:

- Không được ghi nhận một khoản thanh toán hoàn tất hai lần chỉ vì client gửi lại yêu cầu.
- Không được bán vượt tồn kho nếu quy tắc hệ thống yêu cầu tồn kho không âm.
- Hai tác vụ cùng thay đổi một đơn hàng phải có cách phát hiện hoặc xử lý xung đột.
- Khi một nghiệp vụ liên quan đến nhiều bản ghi, hệ thống phải xác định rõ những thay đổi nào cần cùng thành công hoặc cùng thất bại.

### “Giao dịch” có hai cách dùng liên quan nhau

**Bản ghi giao dịch nghiệp vụ** là dữ liệu về một hoạt động vận hành, chẳng hạn đơn hàng hay chuyển khoản. **Giao dịch cơ sở dữ liệu** (*database transaction*) là cơ chế nhóm một hoặc nhiều thao tác đọc/ghi theo những bảo đảm nhất định. Hai khái niệm liên quan nhưng khác nhau: giao dịch cơ sở dữ liệu có thể cập nhật hồ sơ người dùng, dù bản ghi đó không phải “giao dịch tài chính”.

Các tính chất **ACID** thường được dùng để thảo luận về giao dịch cơ sở dữ liệu:

| Tính chất | Ý nghĩa trong thao tác cập nhật |
| --- | --- |
| **Atomicity** | Các thao tác thuộc cùng một giao dịch được xác nhận hoặc hủy bỏ theo đơn vị đã định. |
| **Consistency** | Giao dịch được thiết kế để bảo toàn các ràng buộc dữ liệu đã xác định; việc bảo vệ quy tắc nghiệp vụ còn cần logic ứng dụng phù hợp. |
| **Isolation** | Các giao dịch đồng thời được cô lập theo một mức bảo đảm cụ thể; từng mức cô lập cho phép những hiện tượng khác nhau. |
| **Durability** | Thay đổi đã xác nhận được lưu bền vững theo bảo đảm của hệ quản trị và cấu hình triển khai. |

Không nên suy luận rằng mọi hệ NoSQL đều thiếu giao dịch: nhiều DBMS tài liệu hoặc khóa–giá trị có thao tác nguyên tử và một số hệ hỗ trợ giao dịch nhiều tài liệu. Phạm vi, mức cô lập, chi phí và giới hạn của những bảo đảm này khác nhau theo sản phẩm.

### Mẫu truy cập và yêu cầu thường gặp

- Tra cứu trạng thái hiện tại theo `orderId`, `accountId` hoặc khóa nghiệp vụ.
- Cập nhật có điều kiện, kiểm tra phiên bản (*optimistic concurrency control*), kiểm tra ràng buộc.
- Đọc–ghi với độ trễ thấp, yêu cầu kết quả xác nhận rõ ràng.
- Chống xử lý lặp bằng mã yêu cầu hoặc *idempotency key* khi nhận lại cùng một lệnh.
- Lưu vết thay đổi khi cần kiểm toán, nhưng bản ghi trạng thái hiện tại không tự nó chứa toàn bộ lịch sử.

Các RDBMS như PostgreSQL hoặc MySQL thường được xem xét cho những yêu cầu nhiều ràng buộc và liên kết. Document DBMS như MongoDB cũng có thể quản lý trạng thái giao dịch khi mô hình dữ liệu và bảo đảm giao dịch phù hợp. **Nhãn “transactional” mô tả yêu cầu đúng đắn của dữ liệu, không buộc phải chọn một họ DBMS duy nhất.**

## 3. Dữ liệu sự kiện: một sự việc đã xảy ra

**Sự kiện** (*event*) là một bản ghi về sự việc được nhận biết là đã xảy ra. Tên sự kiện thường ở dạng quá khứ: `OrderPlaced`, `PaymentSucceeded`, `PackageDelivered`. Sự kiện khác **lệnh** (*command*): `PayOrder` yêu cầu thực hiện hành động, còn `OrderPaid` thông báo sự việc đã được ghi nhận thành công.

Ví dụ:

```json
{
  "eventId": "EVT-9008",
  "eventType": "OrderPaid",
  "schemaVersion": 1,
  "aggregateId": "O-1042",
  "occurredAt": "2026-10-12T09:15:00Z",
  "payload": {
    "paymentId": "P-77",
    "amountVnd": 350000
  }
}
```

Ở đây `orderId`/`aggregateId` giúp liên kết sự kiện với đơn hàng, `eventId` nhận diện riêng từng sự kiện, `eventType` diễn tả điều xảy ra và `occurredAt` thể hiện thời điểm sự việc. `schemaVersion` hỗ trợ người tiêu thụ xử lý khi cấu trúc sự kiện thay đổi theo thời gian.

### Sự kiện thường được ghi bổ sung và tiêu thụ bởi nhiều bên

Luồng sự kiện được thiết kế phổ biến theo kiểu **append**: ghi thêm sự kiện mới thay vì âm thầm sửa lại nội dung sự kiện cũ. Dịch vụ gửi thông báo, cập nhật kho, phân tích dữ liệu hoặc tạo chỉ mục tìm kiếm có thể tiêu thụ cùng một loại sự kiện để thực hiện các việc khác nhau.

Ví dụ:

```text
OrderPaid
    │
    ├──> Notification consumer: gửi thông báo
    ├──> Analytics consumer: tăng số đơn đã thanh toán
    └──> Search projection: cập nhật trạng thái đơn để tìm kiếm
```

Trong hệ thống phân tán, xử lý sự kiện thường đòi hỏi các quyết định rõ ràng:

- **Có thể nhận lặp:** nhiều hệ thống phân phối sự kiện theo cơ chế *at-least-once*; consumer cần xử lý lặp an toàn theo `eventId` hoặc khóa nghiệp vụ.
- **Có thể đến trễ hoặc sai thứ tự:** thứ tự toàn cục thường tốn kém hoặc không được bảo đảm; cần xác định thứ tự theo từng đơn hàng, thiết bị hoặc partition nếu nghiệp vụ yêu cầu.
- **Cần xác định thời điểm:** `occurredAt` là lúc sự việc xảy ra; `ingestedAt` là lúc hệ thống nhận; `processedAt` là lúc consumer xử lý. Ba thời điểm có thể khác nhau.
- **Cần quản lý thay đổi schema:** consumer phiên bản cũ có thể không hiểu sự kiện phiên bản mới nếu thay đổi thiếu tương thích.
- **Cần xác định lưu giữ và phát lại:** thời gian retention, khả năng replay và phạm vi lịch sử phải được quy định theo nhu cầu nghiệp vụ/kiểm toán.

Sự kiện có thể được lưu trong bảng dữ liệu, document collection, event log hoặc nền tảng truyền sự kiện như Apache Kafka. **Nền tảng truyền sự kiện không tự động thay thế kho dữ liệu giao dịch**. Cần hiểu mỗi thành phần đang giữ nguồn dữ liệu gốc hay chỉ chuyển tiếp thông điệp.

### Event sourcing không đồng nghĩa với “có dùng sự kiện”

Trong một hệ thống thông thường, bản ghi đơn hàng hiện tại có thể là **nguồn dữ liệu chính**; sự kiện được phát để các dịch vụ khác phản ứng. Trong **event sourcing**, chuỗi sự kiện lại được chọn làm nguồn dữ liệu có thẩm quyền để tái dựng trạng thái, còn bản ghi trạng thái hiện tại là phép chiếu (*projection*) từ chuỗi đó.

```text
Mô hình lưu trạng thái thông thường:
    Current Order (nguồn chính) ──> OrderPaid event

Mô hình event sourcing:
    OrderPlaced + OrderConfirmed + OrderPaid (nguồn chính)
                       │
                       ▼
               Current Order projection
```

Hai mô hình có cách xử lý sửa lỗi, phát lại, lưu giữ sự kiện và trách nhiệm dữ liệu khác nhau. Việc ghi `OrderPaid` vào một topic không tự động biến hệ thống thành event-sourced.

## 4. Dữ liệu tài liệu: đóng gói thông tin theo đối tượng

**Dữ liệu tài liệu** (*document data*) mô tả hình thức tổ chức dữ liệu thành các tài liệu tự chứa tương đối nhiều trường, thường có **đối tượng và mảng lồng nhau**. JSON là dạng trình bày quen thuộc; MongoDB lưu tài liệu theo BSON, còn các document DBMS khác có biểu diễn vật lý và API riêng.

Ví dụ một tài liệu đơn hàng:

```json
{
  "_id": "O-1042",
  "customer": {
    "id": "C-08",
    "displayName": "An"
  },
  "items": [
    { "sku": "BOOK-1", "quantity": 2, "unitPriceVnd": 100000 },
    { "sku": "PEN-3", "quantity": 3, "unitPriceVnd": 50000 }
  ],
  "shippingAddress": {
    "city": "Da Nang",
    "country": "VN"
  },
  "status": "PAID",
  "totalVnd": 350000
}
```

Một màn hình xem chi tiết đơn hàng có thể tải hầu hết dữ liệu cần thiết bằng một lần đọc tài liệu. Điều này thuận tiện khi các trường con thường được **đọc và cập nhật như một nhóm**. Tuy nhiên, việc nhúng dữ liệu cũng tạo ra những đánh đổi:

- **Nhúng (*embedding*)** thông tin giúp đọc cùng nhau, nhưng nếu nhúng một giá trị dùng chung vào hàng nghìn tài liệu, cập nhật giá trị đó có thể cần sửa nhiều nơi.
- **Tham chiếu (*referencing*)** hạn chế nhân bản một số dữ liệu, nhưng khi đọc có thể cần thêm truy vấn hoặc cơ chế kết hợp.
- **Schema linh hoạt** cho phép tài liệu có các trường khác nhau, nhưng ứng dụng vẫn cần quy tắc xác thực, tương thích phiên bản và quản lý dữ liệu thiếu/trái kiểu.
- **Kích thước tài liệu và phạm vi cập nhật nguyên tử** phụ thuộc sản phẩm. Đối với mô hình tài liệu, đơn vị “được đọc/ghi cùng nhau” nên được cân nhắc cùng giới hạn thực tế của DBMS.

Vì “tài liệu” chủ yếu nói về **hình dạng và ranh giới dữ liệu**, cùng một tài liệu có thể mang vai trò khác:

- Tài liệu `order` là **dữ liệu giao dịch** nếu đại diện cho trạng thái có thẩm quyền của đơn hàng.
- Tài liệu `auditEvent` là **dữ liệu sự kiện** nếu ghi một sự việc đã xảy ra.
- Tài liệu `dailySales` là **dữ liệu dẫn xuất** nếu được tổng hợp từ các đơn hàng.

Ngoài ra, một hệ quan hệ như PostgreSQL cũng có thể chứa cột JSON/JSONB. **Lưu JSON không đủ để kết luận một hệ thống là NoSQL**, và lưu tài liệu không bảo đảm dữ liệu đó không có ràng buộc nghiệp vụ.

## 5. Dữ liệu chuỗi thời gian: quan sát đặt trong dòng thời gian

**Dữ liệu chuỗi thời gian** là tập các quan sát có thời điểm gắn với giá trị, thường được phân biệt bởi nguồn đo, đối tượng hoặc nhãn. Ví dụ: nhiệt độ cảm biến theo phút, lượng request mỗi giây, độ trễ API, mức sử dụng CPU, giá cổ phiếu theo thời điểm hoặc số đơn hàng theo giờ.

Một điểm đo có thể được biểu diễn như sau:

```json
{
  "deviceId": "SENSOR-17",
  "measuredAt": "2026-10-12T09:15:00Z",
  "temperatureC": 28.4,
  "humidityPercent": 72.1,
  "locationId": "WAREHOUSE-2"
}
```

Cùng thiết bị có thể phát một bản ghi mỗi 10 giây, tạo thành chuỗi giá trị theo thời gian. Câu hỏi thường gặp không phải “bản ghi hiện tại là gì?” mà là:

- Trong một giờ gần nhất, nhiệt độ trung bình, thấp nhất và cao nhất là bao nhiêu?
- Có ngưỡng nào bị vượt quá liên tiếp trong 5 phút không?
- Nhiệt độ tăng nhanh như thế nào so với 30 phút trước?
- Có điểm đo bị thiếu, bị gửi trễ hoặc đến không đúng thứ tự không?
- Có thể xóa điểm đo chi tiết sau 30 ngày nhưng giữ kết quả tổng hợp theo giờ trong một năm không?

### Những thuộc tính quyết định thiết kế chuỗi thời gian

| Thuộc tính | Ý nghĩa thiết kế |
| --- | --- |
| **Event time / measurement time** | Thời điểm số đo thực sự được lấy hoặc sự việc phát sinh. |
| **Ingestion time** | Thời điểm hệ thống tiếp nhận dữ liệu; có thể trễ hơn measurement time. |
| **Tần suất lấy mẫu** | Ví dụ 1 điểm/giây/thiết bị; quyết định tổng tốc độ ghi và dung lượng. |
| **Nhãn và số lượng chuỗi** | `deviceId`, `region`, `metric`; nhãn có số lượng giá trị quá lớn có thể làm tăng chi phí chỉ mục và quản lý chuỗi. |
| **Truy vấn theo cửa sổ** | Lấy dữ liệu trong `[start, end)`, nhóm theo phút/giờ, tính trung bình, phần trăm vị hoặc biến thiên. |
| **Lưu giữ và giảm độ phân giải** | Retention, TTL, nén, *downsampling* và *rollup* để cân bằng chi tiết với chi phí. |

Ví dụ một phép tổng hợp theo giờ bằng SQL trên một bảng điểm đo (cú pháp cụ thể thay đổi theo DBMS):

```sql
SELECT date_trunc('hour', measured_at) AS hour_bucket,
       AVG(temperature_c) AS avg_temperature_c
FROM sensor_readings
WHERE device_id = 'SENSOR-17'
  AND measured_at >= TIMESTAMP '2026-10-12 00:00:00'
  AND measured_at <  TIMESTAMP '2026-10-13 00:00:00'
GROUP BY date_trunc('hour', measured_at)
ORDER BY hour_bucket;
```

Đoạn SQL minh họa **kiểu truy vấn theo cửa sổ thời gian**; không có nghĩa time-series bắt buộc dùng SQL hoặc một DBMS quan hệ. Những công nghệ có thể được cân nhắc gồm InfluxDB, TimescaleDB dựa trên PostgreSQL, các bộ lưu trữ metrics chuyên dụng hoặc DBMS khác có chỉ mục/phân vùng theo thời gian phù hợp.

### Phân biệt chuỗi thời gian với sự kiện

Sự kiện thường trả lời **“sự việc gì xảy ra?”**; chuỗi thời gian tập trung **“giá trị thay đổi ra sao qua thời gian?”**. Chúng có thể giao nhau nhưng không đồng nhất:

- `OrderPaid` tại 09:15 là một **sự kiện nghiệp vụ**.
- `temperatureC = 28.4` tại 09:15 là một **điểm đo chuỗi thời gian**.
- Một lần vượt ngưỡng nhiệt độ có thể tạo ra sự kiện `TemperatureThresholdExceeded`; sự kiện đó được suy ra từ chuỗi số đo.
- Chuỗi số lượng đơn hàng thanh toán mỗi giờ có thể được **dẫn xuất từ các sự kiện** `OrderPaid`.

Chỉ có trường `timestamp` trong tài liệu không đủ để gọi nó là time-series. Điều quan trọng là **mẫu dữ liệu lặp lại theo thời gian và truy vấn so sánh/tổng hợp theo trục thời gian**.

## 6. Dữ liệu dẫn xuất: kết quả được tạo ra từ dữ liệu nguồn

**Dữ liệu dẫn xuất** (*derived data*) là dữ liệu được tính toán hoặc biến đổi từ một hay nhiều nguồn khác. Mục đích phổ biến là giúp đọc nhanh hơn, hỗ trợ truy vấn khác kiểu hoặc cung cấp một góc nhìn phù hợp cho ứng dụng.

Ví dụ từ những đơn hàng đã thanh toán, hệ thống tính doanh thu theo ngày:

```json
{
  "day": "2026-10-12",
  "paidOrderCount": 124,
  "totalRevenueVnd": 42800000,
  "computedAt": "2026-10-12T23:59:59Z",
  "sourceWatermark": "2026-10-12T23:58:00Z"
}
```

Đây là kết quả của một phép tổng hợp; `computedAt` cho biết thời điểm tính, còn `sourceWatermark` có thể mô tả mức thời gian nguồn đã được xử lý tới. Trường này chỉ có ý nghĩa nếu hệ thống định nghĩa và duy trì nó nhất quán; watermark không tự chứng minh rằng mọi sự kiện đến trễ đã được tính đủ.

Những dạng dữ liệu dẫn xuất thường gặp:

| Dạng | Nguồn | Công dụng |
| --- | --- | --- |
| **Materialized view / read model** | Bản ghi nghiệp vụ hoặc luồng sự kiện | Tạo cấu trúc đọc tối ưu cho một màn hình hoặc truy vấn. |
| **Bảng tổng hợp** | Các bản ghi chi tiết | Doanh thu/ngày, số đơn/giờ, chỉ số hoạt động. |
| **Search index** | Sản phẩm, đơn hàng, bài viết | Tìm toàn văn, lọc và xếp hạng nhanh. |
| **Cache** | DBMS hoặc dịch vụ nguồn | Giảm độ trễ và tải đọc lặp lại. |
| **Đặc trưng phân tích** | Dữ liệu thô và quy tắc biến đổi | Phục vụ báo cáo, phân tích, mô hình dự báo. |

Điểm quan trọng là biết **đâu là nguồn có thẩm quyền (*source of truth*)**. Nếu có thể tái tạo chính xác kết quả từ dữ liệu nguồn cùng phiên bản thuật toán/cấu hình, dữ liệu dẫn xuất thường có thể xóa và xây dựng lại. Nhưng khả năng tái tạo không mặc định có sẵn: nguồn có thể bị xóa vì retention, định nghĩa nghiệp vụ có thể thay đổi, hoặc kết quả có thể chứa chỉnh sửa thủ công chưa được ghi nhận ở nơi khác.

### Khi cập nhật dữ liệu dẫn xuất

Hai cách phổ biến:

1. **Đồng bộ:** thao tác cập nhật nguồn và các phần dữ liệu phục vụ đọc được phối hợp trong cùng phạm vi bảo đảm giao dịch, nếu DBMS/kiến trúc cho phép.
2. **Bất đồng bộ:** thay đổi nguồn phát sự kiện hoặc cung cấp bản ghi thay đổi; một tiến trình khác cập nhật bản dẫn xuất sau đó.

Với cách bất đồng bộ, **độ trễ cập nhật (*projection lag*)** là đặc tính phải được thiết kế và quan sát. Người dùng có thể vừa thanh toán đơn hàng thành công nhưng bảng thống kê chưa tăng ngay. Nếu màn hình cần tính chính xác tức thời, không nên âm thầm lấy một bản dẫn xuất có thể chậm làm nguồn quyết định nghiệp vụ.

Các vấn đề thường gặp gồm cập nhật lặp, sự kiện đến muộn, tính lại dữ liệu lịch sử (*backfill*), thay đổi quy tắc tổng hợp, xây lại chỉ mục, theo dõi vị trí tiến độ và kiểm tra đối soát với nguồn.

## 7. Cùng một nghiệp vụ có thể sinh đủ năm dạng dữ liệu

Xét thao tác khách hàng thanh toán đơn hàng `O-1042`. Một hệ thống có thể lưu các biểu diễn sau:

| Biểu diễn | Vai trò trong hệ thống | Nguồn có thẩm quyền? |
| --- | --- | --- |
| Bản ghi đơn `O-1042`, `status = PAID` | **Giao dịch:** trạng thái nghiệp vụ hiện tại | Có thể có, tùy kiến trúc. |
| Sự kiện `OrderPaid` với `eventId` duy nhất | **Sự kiện:** đã ghi nhận thanh toán thành công | Có thể là nguồn chính trong event sourcing, hoặc là thông báo từ trạng thái chính. |
| Tài liệu chi tiết đơn hàng, gồm `items`, địa chỉ, trạng thái | **Tài liệu:** cấu trúc phục vụ đọc cùng nhau | Có thể là bản gốc hoặc bản chiếu để đọc. |
| Số request thanh toán/phút và độ trễ xử lý | **Chuỗi thời gian:** theo dõi tải và chất lượng hệ thống | Các điểm đo gốc là nguồn cho việc quan sát tương ứng. |
| Doanh thu ngày, cache đơn đã thanh toán, chỉ mục tìm kiếm | **Dẫn xuất:** kết quả phục vụ báo cáo và tìm kiếm | Thường không phải nguồn chính của trạng thái thanh toán. |

Một luồng phổ biến khi **trạng thái giao dịch là nguồn chính**:

```text
Khách hàng xác nhận thanh toán
               │
               ▼
   Kiểm tra quy tắc nghiệp vụ
               │
               ▼
   Ghi trạng thái đơn hàng
   + ghi outbox trong cùng giao dịch
               │
               ▼
         COMMIT thành công
               │
               ▼
     Publisher chuyển outbox
        thành OrderPaid event
               │
      ┌────────┼───────────┐
      ▼        ▼           ▼
  Báo cáo   Read model   Search index
  doanh thu đơn hàng    phục vụ tra cứu

Luồng metrics độc lập:
  API/ứng dụng ──> latency, request count theo phút
                           │
                           ▼
                    Kho chuỗi thời gian
```

**Transactional outbox** giúp bảo đảm bản ghi nghiệp vụ và ý định phát sự kiện được lưu cùng giao dịch trong DBMS nguồn. Nó không có nghĩa mọi consumer đã nhận, xử lý đúng một lần hoặc cập nhật xong ngay lúc `COMMIT`; publisher vẫn có thể gửi lặp và consumer cần có phương án xử lý lặp. **Change Data Capture (CDC)** là một hướng khác để lấy thông tin thay đổi từ nguồn dữ liệu, thường từ nhật ký thay đổi của DBMS. Việc chọn outbox, CDC hay cơ chế khác phụ thuộc bảo đảm phát sự kiện và hạ tầng thực tế.

Trong kiến trúc **event sourcing**, chiều phụ thuộc có thể đổi: các sự kiện là nguồn có thẩm quyền, còn trạng thái hiện tại và màn hình đọc được tái dựng từ chúng. Vì vậy, phải xác định quyền sở hữu và nguồn dữ liệu chính trước khi phân loại một bản ghi là “gốc” hay “dẫn xuất”.

## 8. Liên hệ giữa loại dữ liệu và đặc tính tải

Trong chương **Yêu cầu và tải dữ liệu**, ý nghĩa của việc phân biệt năm dạng không nằm ở việc gán nhãn cho đẹp. Mục đích là suy ra **workload** và những bảo đảm phải đáp ứng. Bảng dưới nêu các mẫu thường gặp, không phải giới hạn tuyệt đối:

| Khía cạnh | Giao dịch | Sự kiện | Tài liệu | Chuỗi thời gian | Dẫn xuất |
| --- | --- | --- | --- | --- | --- |
| **Kiểu ghi** | Thêm/cập nhật có điều kiện | Thường ghi bổ sung | Thêm hoặc cập nhật toàn phần/từng trường | Ghi nhiều điểm theo thời gian | Ghi lại hoặc cập nhật theo nguồn |
| **Kiểu đọc** | Theo khóa, trạng thái, ràng buộc | Theo luồng, khóa, thời gian, offset | Theo tài liệu, thuộc tính, mảng | Khoảng thời gian, nhãn, phép tổng hợp | Theo giao diện đọc/báo cáo cụ thể |
| **Thứ tự và đồng thời** | Xung đột ghi, isolation, version | Thứ tự theo khóa, phát trùng, đến muộn | Phạm vi atomicity của tài liệu và cập nhật liên quan | Đến trễ, không đúng thứ tự, khung thời gian | Độ trễ làm mới, phát lại, tính lại |
| **Độ chính xác cần chú ý** | Bất biến nghiệp vụ, commit | Diễn giải sự kiện, không mất/lặp sai | Ràng buộc và tiến hóa schema | Timestamp, độ phân giải, dữ liệu thiếu | Đúng công thức và đồng bộ với nguồn |
| **Vòng đời dữ liệu** | Theo nghiệp vụ, pháp lý và lịch sử | Retention, replay, audit | Phụ thuộc đối tượng và nghiệp vụ | Retention, TTL, nén, downsampling | Có thể refresh/rebuild nếu nguồn còn |
| **Nút thắt hay gặp** | Tranh chấp khóa, giao dịch dài | Throughput, consumer lag, partition nóng | Tài liệu lớn, truy vấn/index không phù hợp | Write volume, cardinality, scan dài | Write amplification, stale data, backfill |

### Minh họa cách ước lượng tải

Giả sử có **2.000 cảm biến**, mỗi cảm biến gửi **1 điểm mỗi 10 giây**. Nếu hoạt động đều trong một ngày:

```text
Điểm/giây = 2.000 / 10 = 200 điểm
Điểm/ngày = 200 × 86.400 = 17.280.000 điểm
```

Đây là tải ghi chuỗi thời gian khá khác với một hệ thống có **20.000 đơn hàng/ngày**, dù mỗi đơn hàng chứa nhiều trường. Khi tính dung lượng, còn phải cộng kích thước mỗi bản ghi, metadata, chỉ mục, nhân bản, nén và thời gian lưu. Tốc độ ghi trung bình cũng không mô tả được đỉnh tải: ví dụ toàn bộ cảm biến gửi đồng loạt tại đầu mỗi phút có thể làm xuất hiện burst.

Đối với luồng sự kiện, một thao tác nghiệp vụ có thể phát **nhiều sự kiện**, và mỗi sự kiện có thể được **nhiều consumer** xử lý. Vì vậy, số giao dịch nghiệp vụ không đồng nghĩa số bản ghi trong event log hoặc tổng công việc downstream. Với dữ liệu dẫn xuất, một thay đổi nguồn cũng có thể cập nhật nhiều projection, gây **write amplification**.

Để thiết kế đúng, cần đo hoặc ước lượng riêng:

1. **Tần suất và tính bùng nổ của ghi:** bản ghi/giây, đỉnh/giây, batch size, số consumer.
2. **Mẫu đọc:** đọc theo ID, theo tập trường, toàn văn, kết hợp nhiều thực thể, theo khoảng thời gian, theo cửa sổ tổng hợp.
3. **Yêu cầu nhất quán:** sau khi ghi phải đọc thấy ngay ở đâu, phần nào được phép trễ và được phép trễ bao lâu.
4. **Ràng buộc và đồng thời:** thay đổi một hay nhiều bản ghi, giới hạn phiên bản, khả năng xử lý lặp.
5. **Kích thước và tăng trưởng:** số thực thể, số trường, kích thước tài liệu, cardinality của khóa/nhãn, thời gian giữ dữ liệu.
6. **Khả năng phục hồi:** cần replay, rebuild projection, backfill, khôi phục từ backup và đối soát nguồn–đích như thế nào.

## 9. Dữ liệu quyết định lựa chọn mô hình và công nghệ, không phải ngược lại

Không có ánh xạ cứng “giao dịch → SQL”, “sự kiện → Kafka”, “tài liệu → MongoDB”, “chuỗi thời gian → InfluxDB”, “dẫn xuất → Redis”. Mỗi tên công nghệ trả lời một phần của bài toán; cùng một loại dữ liệu có thể dùng nhiều DBMS, và một DBMS có thể lưu nhiều loại dữ liệu.

| Nhu cầu chính | Một số hướng kỹ thuật để khảo sát | Điều vẫn cần đánh giá |
| --- | --- | --- |
| Ghi trạng thái đơn hàng có nhiều ràng buộc | RDBMS, document DBMS có giao dịch phù hợp | Atomicity, isolation, khóa/phiên bản, khả năng phục hồi |
| Thu thập, truyền và phát lại sự kiện | Event log/stream platform, bảng sự kiện, document store | Delivery semantics, thứ tự, độ bền, retention, replay, schema |
| Truy xuất nhanh một đối tượng có cấu trúc lồng nhau | Document DBMS, JSON trong RDBMS | Mẫu truy vấn, kích thước document, chỉ mục, thay đổi schema |
| Ghi điểm đo số lượng lớn và truy vấn theo thời gian | Time-series DBMS, RDBMS có time partition, wide-column store | Throughput, phân vùng, compression, downsampling, cardinality |
| Tìm kiếm, thống kê hoặc cache từ nguồn chính | Search engine, materialized view, Redis/cache, analytics store | Refresh lag, backfill, độ lệch với nguồn, chi phí vận hành |

Một số hệ thống có thể triển khai nhiều kho dữ liệu theo **polyglot persistence**: mỗi kho tối ưu cho một nhóm truy vấn và yêu cầu. Nhưng nhiều kho đồng nghĩa có thêm chi phí vận hành, đồng bộ, quan sát, xử lý lỗi và bảo mật. Với quy mô nhỏ hoặc yêu cầu đơn giản, **một DBMS đủ khả năng** có thể hợp lý hơn nhiều thành phần chuyên dụng.

### Tình huống bổ sung: nền tảng IoT

Một hệ thống theo dõi kho lạnh có thể dùng:

- **Tài liệu** để lưu cấu hình thiết bị: `deviceId`, vị trí, ngưỡng nhiệt độ, thông tin hiệu chuẩn.
- **Chuỗi thời gian** để lưu nhiệt độ/độ ẩm liên tục và truy vấn theo khoảng.
- **Sự kiện** để ghi `TemperatureThresholdExceeded` hoặc `DeviceDisconnected` khi điều kiện được phát hiện.
- **Giao dịch** để quản lý đặt mua thiết bị, hợp đồng, quyền truy cập hay thao tác xác nhận xử lý cảnh báo khi có quy tắc nghiệp vụ cần bảo vệ.
- **Dẫn xuất** để tạo bảng “nhiệt độ cao nhất theo ngày” hoặc danh sách thiết bị cần chú ý.

Các dạng này phục vụ mục đích khác nhau; cố nhét mọi thứ vào một cấu trúc chung có thể khiến truy vấn khó tối ưu, ràng buộc lỏng lẻo hoặc dữ liệu tăng trưởng không kiểm soát.

## 10. Những nhầm lẫn phổ biến cần tránh

**Nhầm lẫn 1 — “Bản ghi có `createdAt` thì là time-series.”** Hầu hết dữ liệu nghiệp vụ có timestamp. Chỉ khi phân tích biến thiên theo thời gian là mục tiêu quan trọng, ta mới xem đặc tính chuỗi thời gian là trọng tâm thiết kế.

**Nhầm lẫn 2 — “Một document không thể là dữ liệu giao dịch.”** Tài liệu đơn hàng vẫn có thể là nguồn dữ liệu nghiệp vụ có ràng buộc nhất quán; “document” nói về cách biểu diễn.

**Nhầm lẫn 3 — “Sự kiện chính là trạng thái hiện tại.”** `OrderPaid` diễn tả một sự việc trong lịch sử; để trả lời trạng thái đơn hàng **hiện nay**, cần đọc trạng thái hiện tại hoặc tính trạng thái từ toàn bộ sự kiện có thẩm quyền theo quy tắc hệ thống.

**Nhầm lẫn 4 — “Có event stream nghĩa là mọi bản ghi đều có thể replay vô hạn.”** Khả năng phát lại phụ thuộc retention, snapshot, độ bền, thay đổi schema và cách giữ trạng thái của consumer.

**Nhầm lẫn 5 — “Mọi dữ liệu dẫn xuất có thể xóa thoải mái.”** Chỉ an toàn khi nguồn, quy tắc tính toán và thông tin cần thiết để xây lại còn đầy đủ; một index bị bỏ lỡ sự kiện hoặc một projection chứa thao tác sửa thủ công có thể không tái tạo như mong muốn.

**Nhầm lẫn 6 — “Một loại dữ liệu tương ứng duy nhất một sản phẩm NoSQL.”** Nhãn loại dữ liệu giúp đặt câu hỏi về tải và bảo đảm; quyết định DBMS cần dựa trên hành vi, giới hạn, chi phí và năng lực vận hành cụ thể.

**Nhầm lẫn 7 — “Eventual consistency có nghĩa là dữ liệu sai cũng được.”** Nhất quán cuối cùng chỉ mô tả thời điểm các bản sao/projection hội tụ theo bảo đảm hệ thống. Nó không miễn trừ yêu cầu xử lý lặp, mất dữ liệu, sai công thức hoặc vi phạm bất biến nghiệp vụ.

## 11. Bài tập phân loại theo ngữ cảnh

Hãy xác định **vai trò nổi bật** của mỗi dữ liệu dưới đây; lưu ý một trường hợp có thể mang nhiều nhãn:

| Trường hợp | Vai trò nổi bật | Lý do |
| --- | --- | --- |
| Số ghế còn trống của một chuyến bay, được cập nhật khi đặt vé | **Giao dịch** | Cần bảo đảm không có nhiều người chiếm cùng ghế theo quy tắc đặt chỗ. |
| Thông điệp `SeatReserved` phát sau khi đặt ghế thành công | **Sự kiện** | Ghi nhận việc đã xảy ra để các consumer xử lý tiếp. |
| Hồ sơ sản phẩm gồm mô tả, thuộc tính kỹ thuật và mảng hình ảnh | **Tài liệu** | Các trường cấu trúc lồng nhau thường được truy xuất cùng nhau. |
| Số request/giây của API trong 24 giờ | **Chuỗi thời gian** | Trọng tâm là giá trị và xu hướng theo các khoảng thời gian. |
| Bảng doanh thu theo tháng tính từ đơn hàng thành công | **Dẫn xuất**, đồng thời có trục thời gian | Kết quả tổng hợp từ bản ghi nguồn, được nhóm theo tháng. |
| JSON lưu một sự kiện `SeatReserved` | **Tài liệu + sự kiện** | JSON là cách biểu diễn; nội dung mang ý nghĩa sự việc đã xảy ra. |
| Read model chi tiết đơn hàng được consumer dựng từ `OrderPlaced`, `OrderPaid` | **Tài liệu + dẫn xuất** | Cấu trúc tài liệu để đọc, được dựng từ sự kiện nguồn. |

Khi gặp một trường hợp gây tranh luận, đừng cố chọn một nhãn duy nhất. Hãy hỏi thêm: **“Đây có phải nguồn có thẩm quyền không?”, “Bản ghi có được chỉnh sửa hay chủ yếu bổ sung?”, “Truy vấn quan trọng nhất là gì?”, “Nếu mất bản ghi này thì có dựng lại được không?”** Câu trả lời giúp mô tả đúng yêu cầu kỹ thuật hơn tên nhóm đơn lẻ.

## 12. Cách đưa phân loại vào tài liệu yêu cầu

Với mỗi tập dữ liệu dự kiến lưu, một bản mô tả ngắn nên có các mục sau:

```text
Tên tập dữ liệu: Order status
Vai trò chính: Giao dịch
Hình dạng: Có thể là bảng hoặc document
Nguồn có thẩm quyền: Order service
Đơn vị định danh: orderId
Mẫu ghi: Tạo đơn, cập nhật trạng thái có điều kiện
Mẫu đọc: Theo orderId, danh sách đơn theo customerId/status
Yêu cầu nhất quán: Không xác nhận thanh toán hai lần
Xử lý lặp/xung đột: Idempotency key, version/concurrency control
Tăng trưởng: Số đơn/ngày, kích thước bản ghi, tải giờ cao điểm
Lưu giữ: Theo yêu cầu nghiệp vụ/pháp lý
Phụ thuộc downstream: OrderPaid event, search projection, báo cáo
```

Đối với dữ liệu sự kiện, bổ sung event key, thứ tự, delivery semantics, thời gian retention và cách replay. Đối với chuỗi thời gian, bổ sung tần suất lấy mẫu, nhãn, cardinality, watermark, dữ liệu đến trễ và chính sách giảm độ phân giải. Đối với dữ liệu dẫn xuất, ghi rõ nguồn, cách tính, tiến độ xử lý, độ trễ chấp nhận được và phương án rebuild.

**Điểm cần nhớ:** *Giao dịch* nhấn mạnh trạng thái nghiệp vụ đúng; *sự kiện* nhấn mạnh điều đã xảy ra; *tài liệu* nhấn mạnh cấu trúc đối tượng; *chuỗi thời gian* nhấn mạnh các quan sát theo thời gian; *dẫn xuất* nhấn mạnh quan hệ biến đổi từ nguồn. Năm góc nhìn này giúp diễn tả đúng **yêu cầu và tải dữ liệu** trước khi lựa chọn mô hình lưu trữ, DBMS hay công nghệ truyền dữ liệu.
