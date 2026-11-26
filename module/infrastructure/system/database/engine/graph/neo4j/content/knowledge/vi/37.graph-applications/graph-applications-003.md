# Phát hiện gian lận qua liên kết tài khoản, thiết bị và giao dịch

## 1. Từ giao dịch đơn lẻ đến mạng lưới dấu hiệu

Trong ứng dụng tài chính, thương mại điện tử hoặc ví điện tử, một giao dịch có thể trông hoàn toàn bình thường nếu chỉ xem **số tiền, thời gian và người gửi**. Tuy nhiên, rủi ro có thể lộ rõ khi kết nối giao dịch đó với **nhiều tài khoản sử dụng chung thiết bị**, một **tài khoản đã được xác minh liên quan gian lận** hoặc chuỗi chuyển tiền qua một số tài khoản trung gian.

**Neo4j** phù hợp với nhu cầu này vì mô hình **property graph** biểu diễn được các thực thể và liên kết:

- **Account:** tài khoản nghiệp vụ có khóa ổn định, thuộc một tenant/tổ chức.
- **Device:** thiết bị hoặc định danh thiết bị đã được chuẩn hóa theo chính sách bảo mật.
- **Transfer/Transaction:** sự kiện giao dịch có mã riêng, thời điểm và số tiền.
- **Relationship:** Account **USED_DEVICE** Device; Account **SENT** Transfer; Transfer **TO** Account.
- **RiskCase/Review:** bằng chứng, quyết định điều tra và thời điểm xác minh.

Bài thuộc chương **Ứng dụng đồ thị** của module **DATABASE_ENGINE_GRAPH_NEO4J**, minh họa cách dùng **Cypher**, constraint/index, truy vấn quan hệ/đường đi, và tùy chọn **Neo4j Graph Data Science (GDS)** để biến liên kết thành **tín hiệu điều tra có thể giải thích**. Cuối bài có hướng triển khai bằng **Java Driver/Spring Data Neo4j**, kiểm thử và kiểm soát sai lệch.

> **Giới hạn nghiệp vụ:** một tài khoản dùng chung thiết bị, IP hoặc người nhận tiền với tài khoản rủi ro **không tự chứng minh gian lận**. Thiết bị có thể là máy công cộng, thiết bị gia đình hoặc bị cấp chung ID; giao dịch có thể là giao dịch hợp pháp. Các quy tắc và điểm số trong bài chỉ là **minh họa kỹ thuật**, phải được đánh giá bằng dữ liệu có nhãn và quy trình rà soát phù hợp trước khi đưa ra quyết định thực tế.

### 1.1. Vì sao graph tốt hơn chỉ truy vấn từng bảng riêng rẽ?

Một cơ sở dữ liệu quan hệ vẫn có thể biểu diễn mọi thông tin trên, nhưng một truy vấn phát hiện **nhiều bước liên kết** có thể yêu cầu nối bảng nhiều lần. Trong graph, các bước quan hệ được biểu diễn trực tiếp:

~~~text
Account A-100 --USED_DEVICE--> Device D-SHARED
Account A-900 --USED_DEVICE--> Device D-SHARED

Account A-100 --SENT--> Transfer T-101 --TO--> Account A-200
Account A-200 --SENT--> Transfer T-102 --TO--> Account A-900
~~~

Từ mẫu trên có thể hỏi:

1. **Những tài khoản nào chia sẻ cùng thiết bị?**
2. **Tài khoản nào nằm cách một thiết bị so với tài khoản gian lận đã xác minh?**
3. **Có chuỗi chuyển tiền A → B → C trong cửa sổ thời gian ngắn hay không?**
4. **Những nhóm tài khoản nào hình thành một thành phần liên thông?**
5. **Tín hiệu nào đóng góp vào mức ưu tiên rà soát của một tài khoản?**

Graph không làm mọi câu hỏi tự động nhanh hay chính xác. **Mô hình đúng, ràng buộc định danh, giới hạn duyệt, dữ liệu đầu vào và cách giải thích kết quả** vẫn quyết định chất lượng hệ thống.

## 2. Thiết kế mô hình tài khoản – thiết bị – giao dịch

### 2.1. Ba node chính và hai loại cấu trúc liên kết

~~~mermaid
flowchart LR
  A["Account<br/>tenantId, accountId"] -->|"USED_DEVICE<br/>firstSeen, lastSeen"| D["Device<br/>tenantId, deviceKey, isPublic"]
  A -->|"SENT"| T["Transfer<br/>tenantId, transferId<br/>amountMinor, occurredAt"]
  T -->|"TO"| B["Account<br/>tenantId, accountId"]
  C["Account khác"] -->|"USED_DEVICE"| D
~~~

| Entity / relationship | Thuộc tính quan trọng | Tại sao cần |
|---|---|---|
| **DemoFraudAccount** | **tenantId**, **accountId**, confirmedFraud | Business key; nhãn gian lận chỉ từ kết quả xác minh |
| **DemoFraudDevice** | **tenantId**, **deviceKey**, **isPublic** | Nhận diện thiết bị trong phạm vi được phép; loại thiết bị công cộng |
| **DemoFraudTransfer** | **tenantId**, **transferId**, **amountMinor**, **occurredAt**, **status** | Mỗi lần chuyển tiền là một sự kiện độc lập |
| **DEMO_FR_USED_DEVICE** | **firstSeen**, **lastSeen** | Liên kết account–device có dấu thời gian quan sát |
| **DEMO_FR_SENT** | Không nhất thiết mang amount | Nối nguồn giao dịch tới Transfer cụ thể |
| **DEMO_FR_TO** | Không nhất thiết mang amount | Nối Transfer tới tài khoản nhận |

**Vì sao Transfer nên là node?** Một giao dịch có mã, tiền, trạng thái, thời điểm, khả năng tra cứu, thay đổi và cần truy nguyên. Dùng mô hình **Account → Transfer → Account** giúp lưu sự kiện với **transferId** duy nhất, đồng thời tránh nhầm nhiều giao dịch từ cùng người gửi tới cùng người nhận thành một relationship duy nhất.

Trong trường hợp đơn giản, cũng có thể lưu **(:Account)-[:TRANSFERRED {transactionId, amount, time}]->(:Account)**. Nhưng khi cần tích hợp refund, approval, dispute, merchant, session và nhiều trạng thái giao dịch, **node Transfer** thường thuận tiện cho quản trị vòng đời sự kiện.

### 2.2. Không nhầm “cùng ID thiết bị” với “cùng người”

**deviceKey** là kết quả của một cơ chế nhận diện được doanh nghiệp quản lý, ví dụ một mã thiết bị giả danh hoặc fingerprint đã được xử lý theo chính sách. Nó có thể thay đổi, bị reset, bị giả mạo, hoặc bị gán trùng. Vì vậy:

- Không dùng deviceKey làm **business key của Account**.
- Không tự hợp nhất hai Account chỉ vì cùng deviceKey.
- Không mặc định một deviceKey ứng với duy nhất một người.
- Cần có **nguồn quan sát**, độ tin cậy, TTL và thời điểm nhìn thấy.
- Các định danh nhạy cảm (IP, cookie, dấu vân tay thiết bị, số điện thoại) cần nguyên tắc thu thập và lưu giữ phù hợp pháp luật/chính sách.

**tenantId** xuất hiện trên cả ba nhãn vì ví dụ giả định hệ thống đa tenant. Một deviceKey có chuỗi giống nhau ở hai tenant **không được tự nối** nếu tổ chức không có quyền và căn cứ xử lý dữ liệu xuyên tenant.

### 2.3. Thời điểm quan sát và thời điểm giao dịch

Phân biệt:

| Thời gian | Ý nghĩa | Công dụng |
|---|---|---|
| **Transfer.occurredAt** | Thời gian nghiệp vụ xảy ra giao dịch | Sắp xếp dòng tiền, phát hiện chuyển nhanh |
| **USED_DEVICE.firstSeen** | Lần đầu tài khoản dùng thiết bị được ghi nhận | Đánh giá lịch sử liên kết |
| **USED_DEVICE.lastSeen** | Lần gần nhất tài khoản dùng thiết bị được ghi nhận | Loại liên kết quá cũ |
| **ingestedAt** (nếu có) | Thời điểm sự kiện tới hệ thống | Đánh giá trễ dữ liệu và replay |
| **confirmedAt** (nếu có) | Thời điểm kết luận vụ việc được xác minh | Tránh dùng nhãn tương lai khi huấn luyện/đánh giá quá khứ |

Không suy ra rằng một account dùng thiết bị **liên tục từ firstSeen đến lastSeen**. Hai mốc này không phải bản ghi mọi lần đăng nhập. Nếu cần độ chính xác theo phiên, hãy mô hình hóa **Login/DeviceObservation** như một sự kiện riêng với **eventId**.

## 3. Chuẩn bị dữ liệu thực hành và constraint

Toàn bộ ví dụ trong bài dùng nhãn bắt đầu bằng **DemoFraud** và relationship bắt đầu bằng **DEMO_FR_**. Chạy trên **database thử nghiệm mới hoặc sạch**, không trên database chứa dữ liệu thật. Những mã tài khoản/thiết bị dưới đây hoàn toàn giả lập.

### 3.1. Đảm bảo business key duy nhất

~~~cypher
CREATE CONSTRAINT demo_fraud_account_key IF NOT EXISTS
FOR (a:DemoFraudAccount)
REQUIRE (a.tenantId, a.accountId) IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT demo_fraud_device_key IF NOT EXISTS
FOR (d:DemoFraudDevice)
REQUIRE (d.tenantId, d.deviceKey) IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT demo_fraud_transfer_key IF NOT EXISTS
FOR (t:DemoFraudTransfer)
REQUIRE (t.tenantId, t.transferId) IS UNIQUE;
~~~

Constraint composite ngăn tạo **hai node cùng nhãn** có cùng tổ hợp khóa đầy đủ; Neo4j có index hỗ trợ. **Uniqueness không tự cấm node thiếu một phần khóa**. Ở production, cần validation bắt buộc trước ghi hoặc **node key constraint** nếu edition hỗ trợ.

### 3.2. Tạo nhóm tài khoản và thiết bị

~~~cypher
CREATE
  (a100:DemoFraudAccount {
    tenantId: 'bank-a', accountId: 'A-100', confirmedFraud: false
  }),
  (a200:DemoFraudAccount {
    tenantId: 'bank-a', accountId: 'A-200', confirmedFraud: false
  }),
  (a900:DemoFraudAccount {
    tenantId: 'bank-a', accountId: 'A-900', confirmedFraud: true
  }),
  (a300:DemoFraudAccount {
    tenantId: 'bank-a', accountId: 'A-300', confirmedFraud: false
  }),
  (a400:DemoFraudAccount {
    tenantId: 'bank-a', accountId: 'A-400', confirmedFraud: false
  }),
  (a500:DemoFraudAccount {
    tenantId: 'bank-a', accountId: 'A-500', confirmedFraud: false
  }),
  (b100:DemoFraudAccount {
    tenantId: 'bank-b', accountId: 'A-100', confirmedFraud: false
  }),
  (shared:DemoFraudDevice {
    tenantId: 'bank-a', deviceKey: 'D-SHARED', isPublic: false
  }),
  (publicDevice:DemoFraudDevice {
    tenantId: 'bank-a', deviceKey: 'D-PUBLIC', isPublic: true
  }),
  (private:DemoFraudDevice {
    tenantId: 'bank-a', deviceKey: 'D-PRIVATE', isPublic: false
  }),
  (other:DemoFraudDevice {
    tenantId: 'bank-a', deviceKey: 'D-OTHER', isPublic: false
  }),
  (bshared:DemoFraudDevice {
    tenantId: 'bank-b', deviceKey: 'D-SHARED', isPublic: false
  }),
  (a100)-[:DEMO_FR_USED_DEVICE {
    firstSeen: datetime('2026-11-19T08:00:00Z'),
    lastSeen: datetime('2026-11-20T08:00:00Z')
  }]->(shared),
  (a200)-[:DEMO_FR_USED_DEVICE {
    firstSeen: datetime('2026-11-19T08:30:00Z'),
    lastSeen: datetime('2026-11-20T08:30:00Z')
  }]->(shared),
  (a900)-[:DEMO_FR_USED_DEVICE {
    firstSeen: datetime('2026-11-19T09:00:00Z'),
    lastSeen: datetime('2026-11-20T09:00:00Z')
  }]->(shared),
  (a100)-[:DEMO_FR_USED_DEVICE {
    firstSeen: datetime('2026-11-20T07:00:00Z'),
    lastSeen: datetime('2026-11-20T07:00:00Z')
  }]->(private),
  (a300)-[:DEMO_FR_USED_DEVICE {
    firstSeen: datetime('2026-11-19T10:00:00Z'),
    lastSeen: datetime('2026-11-20T10:00:00Z')
  }]->(publicDevice),
  (a400)-[:DEMO_FR_USED_DEVICE {
    firstSeen: datetime('2026-11-19T10:30:00Z'),
    lastSeen: datetime('2026-11-20T10:30:00Z')
  }]->(publicDevice),
  (a500)-[:DEMO_FR_USED_DEVICE {
    firstSeen: datetime('2026-11-19T11:00:00Z'),
    lastSeen: datetime('2026-11-20T11:00:00Z')
  }]->(publicDevice),
  (a400)-[:DEMO_FR_USED_DEVICE {
    firstSeen: datetime('2026-11-20T09:00:00Z'),
    lastSeen: datetime('2026-11-20T09:00:00Z')
  }]->(other),
  (b100)-[:DEMO_FR_USED_DEVICE {
    firstSeen: datetime('2026-11-20T08:00:00Z'),
    lastSeen: datetime('2026-11-20T08:00:00Z')
  }]->(bshared);
~~~

**Cấu trúc thiết bị:**

| Thiết bị | Tenant | Tài khoản liên kết | Ngữ cảnh |
|---|---|---|---|
| **D-SHARED** | bank-a | A-100, A-200, A-900 | Thiết bị cần xem xét do liên kết với A-900 |
| **D-PUBLIC** | bank-a | A-300, A-400, A-500 | Thiết bị công cộng, không nên kết luận từ số tài khoản |
| **D-PRIVATE** | bank-a | A-100 | Thiết bị riêng khác của A-100 |
| **D-OTHER** | bank-a | A-400 | Thiết bị riêng khác của A-400 |
| **D-SHARED** | bank-b | A-100 | Node khác tenant, không nối với bank-a |

**confirmedFraud: true** trên A-900 chỉ là **nhãn đã được xác minh giả lập** để tạo bài test. Trong hệ thống thật, cần lưu nguồn xác minh, thời điểm quyết định, trạng thái khiếu nại/đính chính và phạm vi sử dụng nhãn. **A-100 và A-200 không bị gắn nhãn gian lận** chỉ vì có liên kết với A-900.

### 3.3. Tạo các giao dịch có thời gian và số tiền

~~~cypher
MATCH (a100:DemoFraudAccount {tenantId: 'bank-a', accountId: 'A-100'}),
      (a200:DemoFraudAccount {tenantId: 'bank-a', accountId: 'A-200'}),
      (a900:DemoFraudAccount {tenantId: 'bank-a', accountId: 'A-900'}),
      (a300:DemoFraudAccount {tenantId: 'bank-a', accountId: 'A-300'}),
      (a400:DemoFraudAccount {tenantId: 'bank-a', accountId: 'A-400'}),
      (a500:DemoFraudAccount {tenantId: 'bank-a', accountId: 'A-500'})
CREATE
  (t101:DemoFraudTransfer {
    tenantId: 'bank-a', transferId: 'T-101',
    amountMinor: 400000, status: 'SETTLED',
    occurredAt: datetime('2026-11-20T09:00:00Z')
  }),
  (t102:DemoFraudTransfer {
    tenantId: 'bank-a', transferId: 'T-102',
    amountMinor: 350000, status: 'SETTLED',
    occurredAt: datetime('2026-11-20T10:00:00Z')
  }),
  (t103:DemoFraudTransfer {
    tenantId: 'bank-a', transferId: 'T-103',
    amountMinor: 10000, status: 'SETTLED',
    occurredAt: datetime('2026-11-20T10:30:00Z')
  }),
  (t104:DemoFraudTransfer {
    tenantId: 'bank-a', transferId: 'T-104',
    amountMinor: 15000, status: 'SETTLED',
    occurredAt: datetime('2026-11-20T11:00:00Z')
  }),
  (t105:DemoFraudTransfer {
    tenantId: 'bank-a', transferId: 'T-105',
    amountMinor: 450000, status: 'SETTLED',
    occurredAt: datetime('2026-11-20T11:30:00Z')
  }),
  (a100)-[:DEMO_FR_SENT]->(t101)-[:DEMO_FR_TO]->(a200),
  (a200)-[:DEMO_FR_SENT]->(t102)-[:DEMO_FR_TO]->(a900),
  (a300)-[:DEMO_FR_SENT]->(t103)-[:DEMO_FR_TO]->(a400),
  (a500)-[:DEMO_FR_SENT]->(t104)-[:DEMO_FR_TO]->(a300),
  (a200)-[:DEMO_FR_SENT]->(t105)-[:DEMO_FR_TO]->(a900);
~~~

Bảng kiểm tra:

| Transfer | From | To | amountMinor | Thời điểm UTC |
|---|---|---|---:|---|
| T-101 | A-100 | A-200 | 400000 | 20/11, 09:00 |
| T-102 | A-200 | A-900 | 350000 | 20/11, 10:00 |
| T-103 | A-300 | A-400 | 10000 | 20/11, 10:30 |
| T-104 | A-500 | A-300 | 15000 | 20/11, 11:00 |
| T-105 | A-200 | A-900 | 450000 | 20/11, 11:30 |

**amountMinor** dùng đơn vị nhỏ nhất do nghiệp vụ quyết định; không có đơn vị tiền tệ cụ thể trong fixture. Đây không phải số tiền thực của ngân hàng. Nếu hệ thống có nhiều currency, phải lưu **currency** và quy đổi có kiểm soát trước khi cộng hoặc so ngưỡng.

**Kết quả mong đợi:** 7 Account, 5 Device, 5 Transfer, 9 cạnh USED_DEVICE, 5 SENT và 5 TO. Gồm một nhóm A-100/A-200/A-900 với thiết bị chung và chuyển tiền liên tiếp; một nhóm A-300/A-400/A-500 cùng thiết bị công cộng; một tài khoản bank-b độc lập.

## 4. Nạp dữ liệu an toàn: khóa ổn định, idempotency và dữ liệu đến trễ

### 4.1. MERGE theo business key, không theo property thay đổi

Trong luồng ingestion, event **transferId** có thể được gửi lặp lại do retry hoặc message broker. Lệnh **CREATE** vô điều kiện có thể làm trùng giao dịch. Cần dùng uniqueness constraint và MERGE theo **(tenantId, transferId)**.

~~~cypher
// $tenantId, $transferId, $amountMinor, $occurredAt, $status
// đến từ payload đã validate và chuẩn hóa.
MERGE (t:DemoFraudTransfer {
  tenantId: $tenantId,
  transferId: $transferId
})
ON CREATE SET
  t.amountMinor = $amountMinor,
  t.occurredAt = datetime($occurredAt),
  t.status = $status,
  t.ingestedAt = datetime()
RETURN t.transferId AS transferId;
~~~

Nếu event đã tồn tại, **ON CREATE SET** không cập nhật lại amount hay occurredAt. Đây là chính sách minh họa **tạo một lần**; nếu một transaction thật có quyền sửa hoặc bị đảo ngược, phải quản lý version/event loại khác thay vì âm thầm bỏ qua cập nhật.

**Quan trọng:** cùng transferId nhưng payload khác phải được coi là **xung đột dữ liệu** nếu không có quy trình correction được định nghĩa. Chỉ MERGE mà không so payload có thể che lỗi do upstream tái sử dụng ID. Thiết kế production cần fingerprint/version, kiểm tra conflict và transaction nguyên tử cho node cùng hai cạnh nguồn/đích.

### 4.2. Giữ đúng identity của account và device

~~~cypher
MERGE (a:DemoFraudAccount {
  tenantId: $tenantId,
  accountId: $accountId
})
ON CREATE SET a.confirmedFraud = false
MERGE (d:DemoFraudDevice {
  tenantId: $tenantId,
  deviceKey: $deviceKey
})
ON CREATE SET d.isPublic = false
MERGE (a)-[u:DEMO_FR_USED_DEVICE]->(d)
ON CREATE SET
  u.firstSeen = datetime($observedAt),
  u.lastSeen = datetime($observedAt)
ON MATCH SET
  u.firstSeen = CASE
    WHEN datetime($observedAt) < u.firstSeen
      THEN datetime($observedAt) ELSE u.firstSeen END,
  u.lastSeen = CASE
    WHEN datetime($observedAt) > u.lastSeen
      THEN datetime($observedAt) ELSE u.lastSeen END;
~~~

Ví dụ giữ **một cạnh tổng hợp** cho mỗi cặp Account–Device, ghi firstSeen/lastSeen. Nếu cần tính số lần đăng nhập chính xác, thêm **DeviceObservation** theo eventId thay vì tăng counter trong một callback có thể retry. Đừng xem cạnh tổng hợp này là chứng cứ rằng hai tài khoản cùng hoạt động **đồng thời**.

Tạo node và cạnh liên quan bằng **một transaction** khi một sự kiện cần nhất quán trọn vẹn. Trong Java Driver, **executeWrite** có thể retry callback khi gặp lỗi transient: logic phải idempotent và không gọi thanh toán/email bên ngoài trong callback.

### 4.3. Dữ liệu đến trễ và thời gian sự kiện

Đừng dùng **datetime() lúc ingestion** làm thời điểm giao dịch nếu upstream đã cung cấp **occurredAt** đáng tin cậy. Một transfer xảy ra 09:00 nhưng được nhận lúc 12:00 phải nằm đúng vị trí thời gian trong chuỗi A → B → C.

Thiết kế nên có:

- **eventId/transferId** không trùng.
- **occurredAt** và **ingestedAt** tách biệt.
- **event version** hoặc correction events nếu dữ liệu có thể sửa.
- **watermark** cho các phép tổng hợp theo cửa sổ, phù hợp độ trễ nguồn.
- **cơ chế replay** không tạo node/cạnh trùng hoặc làm tăng điểm rủi ro hai lần.

Nếu transaction chỉ ở trạng thái **PENDING**, quyết định có tính nó vào “dòng tiền đã chuyển” phải được định nghĩa rõ. Các ví dụ sau chủ yếu xét **status = 'SETTLED'**.

## 5. Phát hiện tài khoản dùng chung thiết bị

### 5.1. Tìm các cặp account có thiết bị chung

~~~cypher
MATCH (a:DemoFraudAccount {tenantId: $tenantId})
      -[:DEMO_FR_USED_DEVICE]->
      (d:DemoFraudDevice {tenantId: $tenantId})
      <-[:DEMO_FR_USED_DEVICE]-
      (b:DemoFraudAccount {tenantId: $tenantId})
WHERE a.accountId < b.accountId
WITH a, b,
     count(DISTINCT d) AS sharedDeviceCount,
     collect(DISTINCT d.deviceKey) AS sharedDevices
RETURN a.accountId AS accountA,
       b.accountId AS accountB,
       sharedDeviceCount,
       sharedDevices
ORDER BY sharedDeviceCount DESC, accountA, accountB;
~~~

Đặt tham số **$tenantId = 'bank-a'**. Kết quả gồm các cặp:

| accountA | accountB | sharedDevices |
|---|---|---|
| A-100 | A-200 | D-SHARED |
| A-100 | A-900 | D-SHARED |
| A-200 | A-900 | D-SHARED |
| A-300 | A-400 | D-PUBLIC |
| A-300 | A-500 | D-PUBLIC |
| A-400 | A-500 | D-PUBLIC |

Điều kiện **a.accountId < b.accountId** tránh xuất cả hai chiều **(A,B)** và **(B,A)** và tự nối **(A,A)**. Vì cặp account đã được ràng buộc trong một tenant, so chuỗi accountId trong phạm vi đó có ý nghĩa. Trong graph thật có thể có nhiều loại thiết bị và nhiều cạnh từ cùng một nguồn: **count(DISTINCT d)** ngăn đếm trùng thiết bị khi một account có nhiều bản ghi quan sát.

**Cạm bẫy:** truy vấn phát hiện *mối liên hệ*, không phán định gian lận. Ba cặp trong nhóm **D-PUBLIC** có thể hoàn toàn hợp pháp.

### 5.2. Đo mức “phổ biến” của một thiết bị

~~~cypher
MATCH (d:DemoFraudDevice {tenantId: $tenantId})
      <-[:DEMO_FR_USED_DEVICE]-
      (a:DemoFraudAccount {tenantId: $tenantId})
WITH d, count(DISTINCT a) AS accountCount
RETURN d.deviceKey AS deviceKey,
       d.isPublic AS isPublic,
       accountCount
ORDER BY accountCount DESC, deviceKey;
~~~

Trong **bank-a**, **D-SHARED** và **D-PUBLIC** đều có **3 Account**, còn **D-PRIVATE** và **D-OTHER** có **1**. Một quy tắc “thiết bị có từ 3 account là gian lận” sẽ **đánh đồng** nhóm cần điều tra với nhóm máy công cộng.

**Cách cải thiện:** sử dụng metadata thiết bị (**isPublic**, loại thiết bị, nguồn cung cấp ID, độ tin cậy), tần suất thay đổi tài khoản, đồng thời hoạt động, số lần có xác minh bất thường và tỷ lệ nhãn gian lận đã xác nhận. Với hub có bậc cao như IP NAT công ty, sân bay hoặc Wi-Fi công cộng, cần **hạ trọng số, loại khỏi một số mô hình hoặc đặt ngưỡng phụ thuộc bối cảnh**.

### 5.3. Chỉ xét quan sát nằm trong cửa sổ thời gian

~~~cypher
MATCH (a:DemoFraudAccount {tenantId: $tenantId})
      -[u1:DEMO_FR_USED_DEVICE]->
      (d:DemoFraudDevice {tenantId: $tenantId})
      <-[u2:DEMO_FR_USED_DEVICE]-
      (b:DemoFraudAccount {tenantId: $tenantId})
WHERE a.accountId < b.accountId
  AND u1.firstSeen <= datetime($to)
  AND u1.lastSeen >= datetime($from)
  AND u2.firstSeen <= datetime($to)
  AND u2.lastSeen >= datetime($from)
RETURN a.accountId AS accountA,
       b.accountId AS accountB,
       d.deviceKey AS deviceKey,
       u1.lastSeen AS lastSeenA,
       u2.lastSeen AS lastSeenB
ORDER BY accountA, accountB, deviceKey;
~~~

Các tham số **$from**, **$to** là ISO-8601 có timezone, với **from <= to**; ví dụ **2026-11-20T00:00:00Z** đến **2026-11-21T00:00:00Z**. Điều kiện ở đây chỉ hỏi **hai khoảng firstSeen–lastSeen có giao với cửa sổ**, không bảo đảm hai lần đăng nhập thực sự xảy ra cùng giờ. Muốn chứng minh sự trùng thời gian, phải dùng **event-level observations**.

## 6. Tìm liên kết tới tài khoản đã được xác minh gian lận

Trong fixture, **A-900** thuộc bank-a có nhãn giả lập **confirmedFraud = true**. Một quy tắc điều tra có thể xem tài khoản nào dùng **thiết bị không công cộng** chung với A-900.

~~~cypher
MATCH (a:DemoFraudAccount {tenantId: $tenantId})
      -[:DEMO_FR_USED_DEVICE]->
      (d:DemoFraudDevice {tenantId: $tenantId})
      <-[:DEMO_FR_USED_DEVICE]-
      (known:DemoFraudAccount {tenantId: $tenantId})
WHERE known.confirmedFraud = true
  AND a <> known
  AND d.isPublic = false
RETURN a.accountId AS accountToReview,
       known.accountId AS confirmedAccount,
       collect(DISTINCT d.deviceKey) AS connectingDevices
ORDER BY accountToReview;
~~~

Với **bank-a**, kết quả:

~~~text
A-100  A-900  ["D-SHARED"]
A-200  A-900  ["D-SHARED"]
~~~

**Diễn giải đúng:** A-100/A-200 có liên kết qua thiết bị với một account đã xác minh. Đây là **lý do để đánh giá thêm**, không phải một kết luận về ý định hay trách nhiệm của chủ tài khoản.

### 6.1. Đường liên kết không biểu diễn quan hệ nhân quả

Đường:

~~~text
A-100 -> D-SHARED <- A-900
~~~

cho thấy hai tài khoản được quan sát trên cùng deviceKey. Nó **không** chứng minh A-100 điều khiển A-900, giao dịch tiền đã liên quan, hoặc cả hai account dùng thiết bị cùng một thời điểm.

Đánh giá rủi ro tốt hơn cần nhiều nhóm tín hiệu độc lập: dữ liệu xác thực, xác minh chủ tài khoản, hành vi giao dịch, lịch sử và khả năng bị chiếm đoạt tài khoản. Tránh nhân đôi bằng chứng: **cùng một lần đăng nhập** không nên bị tính là ba tín hiệu độc lập chỉ vì nó xuất hiện trong ba bảng/quan hệ.

### 6.2. Liên kết độ sâu lớn cần được giới hạn

Một truy vấn quá rộng như duyệt hàng chục bước qua tất cả **Account/Device/Transfer** dễ sinh **graph explosion**: một IP công cộng có thể nối hàng triệu account. Trong yêu cầu điều tra trực tuyến, thường bắt đầu từ **1–2 bước liên kết rõ nghĩa** rồi mới mở rộng có điều kiện.

Không dùng **shortestPath()** như một phương tiện khẳng định “đường rủi ro thấp nhất”: Cypher shortest path tối ưu **số hop**, không tự cộng trọng số độ tin cậy. Nếu cần thuật toán đường đi có trọng số, phải định nghĩa chi phí từng cạnh và dùng phương pháp phù hợp (ví dụ GDS) trước khi diễn giải.

## 7. Truy vết chuỗi chuyển tiền qua tài khoản trung gian

### 7.1. Giao dịch trực tiếp tới account đã xác minh

~~~cypher
MATCH (src:DemoFraudAccount {tenantId: $tenantId})
      -[:DEMO_FR_SENT]->
      (t:DemoFraudTransfer {tenantId: $tenantId})
      -[:DEMO_FR_TO]->
      (dest:DemoFraudAccount {tenantId: $tenantId})
WHERE dest.confirmedFraud = true
  AND t.status = 'SETTLED'
RETURN src.accountId AS sender,
       dest.accountId AS recipient,
       t.transferId AS transferId,
       t.amountMinor AS amountMinor,
       t.occurredAt AS occurredAt
ORDER BY occurredAt;
~~~

Với **bank-a**, có **T-102** và **T-105**, đều từ **A-200** tới **A-900**. Đây là một **tín hiệu về dòng tiền** khác với liên kết dùng chung thiết bị.

### 7.2. Hai bước chuyển A → B → C theo thời gian

~~~cypher
MATCH (src:DemoFraudAccount {
        tenantId: $tenantId, accountId: $sourceId
      })
      -[:DEMO_FR_SENT]->(t1:DemoFraudTransfer)
      -[:DEMO_FR_TO]->(mid:DemoFraudAccount)
      -[:DEMO_FR_SENT]->(t2:DemoFraudTransfer)
      -[:DEMO_FR_TO]->(dest:DemoFraudAccount {
        tenantId: $tenantId
      })
WHERE dest.confirmedFraud = true
  AND mid.tenantId = $tenantId
  AND t1.tenantId = $tenantId
  AND t2.tenantId = $tenantId
  AND t1.status = 'SETTLED'
  AND t2.status = 'SETTLED'
  AND t1.occurredAt < t2.occurredAt
  AND t2.occurredAt <= t1.occurredAt + duration({hours: 24})
RETURN src.accountId AS source,
       mid.accountId AS intermediary,
       dest.accountId AS destination,
       t1.transferId AS firstTransfer,
       t2.transferId AS secondTransfer,
       t1.occurredAt AS firstAt,
       t2.occurredAt AS secondAt
ORDER BY firstAt, secondAt;
~~~

Đặt **$tenantId = 'bank-a'** và **$sourceId = 'A-100'**. Kết quả có hai chuỗi:

~~~text
A-100 -> T-101 -> A-200 -> T-102 -> A-900
A-100 -> T-101 -> A-200 -> T-105 -> A-900
~~~

Hai chuỗi có **cùng T-101**, nên không được đếm là **hai lần A-100 chuyển tiền độc lập** tới A-200. Chúng chỉ là **hai tổ hợp đường** qua hai giao dịch khác nhau của A-200.

Trong nghiệp vụ chống rửa tiền, mô hình này **chưa chứng minh** số tiền từ T-101 đã được dùng để tài trợ T-102/T-105. Cần thêm dòng tiền chi tiết, số dư, thời gian, kênh và các điều kiện nghiệp vụ. “Có đường đi” chỉ cung cấp một giả thuyết điều tra.

### 7.3. Phát hiện hoạt động chuyển nhiều lần trong một cửa sổ

~~~cypher
MATCH (src:DemoFraudAccount {tenantId: $tenantId})
      -[:DEMO_FR_SENT]->
      (t:DemoFraudTransfer {tenantId: $tenantId})
      -[:DEMO_FR_TO]->
      (dest:DemoFraudAccount {tenantId: $tenantId})
WHERE t.status = 'SETTLED'
  AND t.occurredAt >= datetime($from)
  AND t.occurredAt < datetime($to)
WITH DISTINCT src, dest, t
WITH src, dest,
     count(t) AS transferCount,
     sum(t.amountMinor) AS totalAmountMinor,
     collect(t.transferId) AS transferIds
WHERE transferCount >= $minTransfers
RETURN src.accountId AS sender,
       dest.accountId AS receiver,
       transferCount,
       totalAmountMinor,
       transferIds
ORDER BY transferCount DESC, sender, receiver;
~~~

Với **bank-a**, cửa sổ **2026-11-20T00:00:00Z → 2026-11-21T00:00:00Z** và **minTransfers = 2**, kết quả có A-200 → A-900: **2 giao dịch**, tổng **800000** đơn vị tiền nhỏ nhất, IDs **T-102, T-105**.

**Chú ý:** tổng tiền chỉ có nghĩa khi tất cả giao dịch cùng currency và trạng thái phù hợp; fixture chưa có currency nên chỉ minh họa phép cộng. Trên hệ thống đa tiền tệ, cần tách theo currency hoặc chuyển đổi bằng tỷ giá và thời điểm có kiểm toán.

**Vì sao có WITH DISTINCT src, dest, t trước SUM?** Nếu dữ liệu bất thường có nhiều cạnh SENT/TO cho cùng Transfer, phép MATCH có thể tạo nhiều hàng cho một giao dịch. Chỉ dùng **count(DISTINCT t)** nhưng vẫn **sum(t.amountMinor)** sẽ thổi phồng tổng tiền. Khử trùng theo **bộ (nguồn, đích, Transfer)** trước khi SUM giúp phép tổng hợp theo cặp có ngữ nghĩa nhất quán; hệ thống vẫn phải phát hiện và sửa graph sai invariant.

## 8. Kết hợp tín hiệu thành điểm ưu tiên điều tra

### 8.1. Từ dấu hiệu đến feature có giải thích

Một kết quả điều tra có ích khi trả được **lý do**:

| Feature | Ý nghĩa | Giá trị mong đợi ở fixture |
|---|---|---|
| **knownFraudSharedDeviceNeighbors** | Số account đã xác minh rủi ro dùng chung **thiết bị không công cộng** | A-100 = 1; A-200 = 1 |
| **transfersToConfirmedCount** | Số giao dịch SETTLED trực tiếp tới account đã xác minh trong cửa sổ | A-200 = 2; A-100 = 0 |
| **sharedDeviceDegree** | Một thiết bị có bao nhiêu account | D-SHARED = 3; D-PUBLIC = 3 |
| **twoStepTransferPaths** | Số chuỗi chuyển hai bước trong cửa sổ | A-100 tới A-900 có 2 đường ví dụ |
| **recentAccountAge / newDevice** | Tài khoản/thiết bị mới xuất hiện gần đây? | Chưa có đủ dữ liệu trong fixture |

**Feature không phải kết luận.** Một biến có thể mang tín hiệu mạnh trong một nhóm sản phẩm nhưng yếu trong nhóm khác. Chỉ dùng khi có định nghĩa chính xác về cửa sổ, dữ liệu nguồn, độ tin cậy, độ trễ và cách loại trùng.

### 8.2. Tạo điểm minh họa từ hai tín hiệu độc lập

Ví dụ đặt **40 điểm** khi có ít nhất một account gian lận đã xác minh dùng chung thiết bị không công cộng, và **30 điểm** khi có ít nhất một giao dịch trực tiếp tới account đó trong ngày. Điểm nằm trong khoảng **0–70** vì chỉ có hai tín hiệu; đây **không phải xác suất gian lận**.

~~~cypher
MATCH (a:DemoFraudAccount {tenantId: $tenantId})
WHERE a.confirmedFraud = false
CALL (a) {
  MATCH (a)-[:DEMO_FR_USED_DEVICE]->(d:DemoFraudDevice)
        <-[:DEMO_FR_USED_DEVICE]-(known:DemoFraudAccount)
  WHERE d.tenantId = a.tenantId
    AND d.isPublic = false
    AND known.tenantId = a.tenantId
    AND known.confirmedFraud = true
    AND known <> a
  RETURN count(DISTINCT known) AS knownNeighbors
}
CALL (a) {
  MATCH (a)-[:DEMO_FR_SENT]->(t:DemoFraudTransfer)
        -[:DEMO_FR_TO]->(known:DemoFraudAccount)
  WHERE t.tenantId = a.tenantId
    AND known.tenantId = a.tenantId
    AND known.confirmedFraud = true
    AND t.status = 'SETTLED'
    AND t.occurredAt >= datetime($from)
    AND t.occurredAt < datetime($to)
  RETURN count(DISTINCT t) AS transfersToKnown
}
WITH a, knownNeighbors, transfersToKnown,
     (CASE WHEN knownNeighbors > 0 THEN 40 ELSE 0 END) +
     (CASE WHEN transfersToKnown > 0 THEN 30 ELSE 0 END)
       AS reviewScore
RETURN a.accountId AS accountId,
       knownNeighbors,
       transfersToKnown,
       reviewScore
ORDER BY reviewScore DESC, accountId;
~~~

**Yêu cầu phiên bản:** dạng **CALL (a) { ... }** (variable scope clause) được hỗ trợ từ **Neo4j 5.23**; với bản cũ hơn có thể dùng importing **WITH a** theo cú pháp của phiên bản, nhưng cách cũ đã deprecated trên bản hiện đại.

Với tenant **bank-a** và cửa sổ ngày 20/11/2026:

| Account | knownNeighbors | transfersToKnown | reviewScore |
|---|---:|---:|---:|
| **A-200** | 1 | 2 | **70** |
| **A-100** | 1 | 0 | **40** |
| A-300 | 0 | 0 | 0 |
| A-400 | 0 | 0 | 0 |
| A-500 | 0 | 0 | 0 |

**Không đưa A-900 vào bảng đánh giá account chưa được xác minh** vì nó là label đã xác nhận trong fixture. **Không** hiểu 70 điểm là 70% gian lận. Hệ số 40/30 là quy tắc dạy học, không được hiệu chỉnh từ dữ liệu và không có nghĩa thống kê.

### 8.3. Vì sao tách subquery?

Nếu trong một MATCH nối nhiều device, nhiều transfer và nhiều account đích, số hàng trung gian có thể nhân chéo: **3 thiết bị × 5 giao dịch** tạo 15 hàng dù chỉ có 3 và 5 sự kiện riêng. Đếm/sum ngay sau join này dễ **thổi phồng feature**.

Hai subquery **CALL (a)** tính mỗi nhóm bằng chứng riêng, dùng **count(DISTINCT ...)**, rồi ghép kết quả theo account. Cách này giúp kiểm soát bùng nổ hàng và làm rõ nguồn điểm.

Với dữ liệu rất lớn, cân nhắc tính feature trong các pipeline theo cửa sổ thay vì truy vấn toàn bộ quan hệ cho mỗi request. Tuy nhiên, lưu feature cache đòi hỏi **TTL, version, freshness và kiểm tra khả năng tái hiện**.

## 9. Mở rộng bằng Graph Data Science: component và similarity

**Neo4j Graph Data Science (GDS)** là thư viện thuật toán cần được cài đặt/cấp quyền riêng (hoặc được môi trường hỗ trợ). Nó không phải tính năng mặc định của Cypher lõi trong mọi deployment.

### 9.1. Weakly Connected Components (WCC) để tìm cụm liên kết

Trong một mạng Account–Device, **WCC** tìm những nhóm node có thể nối với nhau nếu **bỏ qua chiều** của các cạnh. Nó phù hợp với câu hỏi “những account này thuộc cùng một cụm liên kết qua device nào?”, nhưng **không** kết luận cụm đó là một nhóm gian lận.

Ví dụ project graph chỉ từ Account, Device và quan hệ USED_DEVICE:

~~~cypher
CALL gds.graph.project(
  'demoFraudSignals',
  ['DemoFraudAccount', 'DemoFraudDevice'],
  {
    DEMO_FR_USED_DEVICE: {
      orientation: 'UNDIRECTED'
    }
  }
)
YIELD graphName, nodeCount, relationshipCount
RETURN graphName, nodeCount, relationshipCount;
~~~

Vì orientation **UNDIRECTED** nạp cả hai chiều, số relationship của named graph có thể gấp đôi số cạnh Neo4j gốc. Dữ liệu mẫu có **12 node** thuộc hai nhãn và **9 cạnh USED_DEVICE trong database**; không suy luận số relationship project luôn bằng 9.

Chạy WCC:

~~~cypher
CALL gds.wcc.stream('demoFraudSignals')
YIELD nodeId, componentId
WITH componentId, gds.util.asNode(nodeId) AS n
WHERE n:DemoFraudAccount
  AND n.tenantId = 'bank-a'
RETURN componentId,
       count(n) AS accountCount,
       collect(n.accountId) AS accountIds
ORDER BY accountCount DESC, componentId;
~~~

Ở tenant bank-a, hai nhóm tài khoản có ba thành viên:

- **{A-100, A-200, A-900}**: liên kết qua **D-SHARED**.
- **{A-300, A-400, A-500}**: liên kết qua **D-PUBLIC**.

**componentId là ID kỹ thuật**, không có nghĩa phân loại rủi ro và không cần giữ ổn định khi projection được tạo lại. Mẫu còn có một thành phần riêng của tenant bank-b; truy vấn kết quả trên chỉ hiển thị account bank-a.

**Quan trọng:** projection ví dụ lấy cả hai tenant vì dùng native projection theo nhãn. Chỉ nên chạy như vậy ở **môi trường thử nghiệm có quyền đối với toàn bộ dữ liệu**. Trong sản phẩm đa tenant, phải cô lập dữ liệu **trước khi đưa vào named graph**, bằng database riêng, Cypher projection được lọc theo tenant hoặc cơ chế tương đương được kiểm chứng; lọc ở phần **RETURN** không bảo đảm mô hình tính toán đã cô lập dữ liệu.

### 9.2. Node Similarity: account giống nhau theo lân cận device

**Node Similarity** có thể so sánh hai account dựa trên tập thiết bị liên kết. Ví dụ, với tập device:

\[
D(A\!-\!100)=\{D\!-\!SHARED,D\!-\!PRIVATE\},
\quad D(A\!-\!200)=\{D\!-\!SHARED\}
\]

Jaccard similarity:

\[
J(A,B)=\frac{|D(A)\cap D(B)|}{|D(A)\cup D(B)|}
\]

Theo đó **J(A-100, A-200) = 1/2 = 0,5**, còn **J(A-200, A-900) = 1** vì cả hai chỉ có D-SHARED trong fixture. Tương tự, ba account dùng **D-PUBLIC** cũng có thể đạt similarity cao nhưng không đồng nghĩa gian lận.

Tài liệu GDS hỗ trợ **gds.nodeSimilarity.stream** với các metric như **JACCARD**, **OVERLAP**, **COSINE** và các tham số **topK**, **similarityCutoff**, **upperDegreeCutoff**. Để so sánh **tập device mà account đi tới**, projection nên giữ **hướng Account → Device** và giới hạn tập node so sánh là Account; không dùng projection **UNDIRECTED** cho WCC rồi mặc định kết quả similarity có ngữ nghĩa tương tự.

Trên graph lớn, Node Similarity có thể tốn nhiều bộ nhớ/tính toán. Hãy đọc ước lượng tài nguyên, lọc tenant trước projection, loại hoặc giảm trọng số các hub công cộng, và chọn topK phù hợp. Điểm similarity là **mức tương đồng cấu trúc**, không phải xác suất cùng chủ sở hữu hay một kết luận pháp lý.

### 9.3. Giải phóng named graph sau bài tập

~~~cypher
CALL gds.graph.drop('demoFraudSignals')
YIELD graphName
RETURN graphName;
~~~

Thao tác này **xóa projection GDS trong bộ nhớ**, không xóa node hoặc relationship gốc trong database. Trong ứng dụng sản phẩm, named graph phải có chính sách lifecycle/refresh vì **không tự đồng bộ** khi database phát sinh account/transfer mới.

## 10. Kiểm soát false positives và tính đúng của tín hiệu

### 10.1. Những nguyên nhân một liên kết không đáng nghi

| Tình huống | Điều dễ bị hiểu sai | Cách giảm nhiễu |
|---|---|---|
| **Máy/thiết bị công cộng** | Hàng chục account cùng deviceKey | Metadata isPublic, device degree cutoff, chính sách theo phân khúc |
| **NAT/Wi-Fi chung** | Nhiều account có cùng IP | Không coi IP như định danh thiết bị cá nhân |
| **Gia đình/doanh nghiệp** | Nhiều người dùng máy hợp lệ | Phân tích lịch sử, owner context có căn cứ, xác minh bổ sung |
| **Thiết bị bị reset/tái sử dụng** | Mã thiết bị xuất hiện ở người khác | TTL, firstSeen/lastSeen, nguồn ID |
| **Tài khoản bị chiếm đoạt** | Liên kết với fraud không phản ánh chủ tài khoản có lỗi | Quy trình account takeover và hỗ trợ người dùng |
| **Giao dịch hoàn tiền/thu hồi** | Một Transfer nhìn như dòng tiền mới | Trạng thái và loại giao dịch có ý nghĩa |
| **Hai đường graph dùng chung một event** | Đếm thành nhiều bằng chứng độc lập | count(DISTINCT transferId/eventId), dedupe theo nguồn |
| **Dữ liệu chưa cập nhật** | Một label gian lận đã bị hủy nhưng feature còn giữ | Version, refresh, quy trình đính chính và TTL |

**Không lấy số hop hay số lượng thiết bị làm một “risk score” độc lập** nếu chưa định nghĩa căn cứ thống kê. Nhiều edge có thể chỉ xuất phát từ một nguyên nhân chung (thiết bị cộng đồng), còn một đường ngắn tới account gian lận có thể là tình cờ.

### 10.2. Tránh leakage khi huấn luyện hoặc đánh giá offline

Nếu model được đánh giá ở mốc **20/11**, không được dùng **confirmedFraud** chỉ được xác minh vào **25/11** làm feature đã biết ở ngày 20. Điều đó tạo ra **temporal leakage**: kết quả đánh giá rất đẹp nhưng không tái lập trong production.

Cần lưu:

- Thời điểm **event xảy ra** và thời điểm **hệ thống biết event**.
- Thời điểm **label fraud được xác minh**, nguồn và trạng thái có thể thay đổi.
- Snapshot/phiên bản đồ thị, feature definition và khoảng dữ liệu dùng cho test.
- Chia tập train/validation/test theo **thời gian và thực thể**, tránh account/thiết bị/cụm xuất hiện chéo theo cách làm lộ thông tin.

Trong vận hành, không cập nhật một label gian lận “ngược thời gian” rồi đánh giá như thể nó đã được biết trước.

### 10.3. Đo precision, recall và tải điều tra

Đối với cảnh báo cần con người rà soát:

\[
\text{Precision}=\frac{TP}{TP+FP},\qquad
\text{Recall}=\frac{TP}{TP+FN}
\]

Ở đây TP/FP/FN chỉ có nghĩa khi đã có **ground truth đủ đáng tin cậy**, bao gồm quy tắc xác nhận một trường hợp thật sự gian lận. Tập “các account từng được đội điều tra xem xét” **không nhất thiết là** tập gian lận đã xác minh.

Ngoài precision/recall, cần đo:

- **Alert volume** mỗi ngày/tenant và tỷ lệ trùng cảnh báo.
- **False-positive rate** theo phân khúc có cơ sở đánh giá hợp lệ.
- **Thời gian từ sự kiện đến phát hiện**, thời gian điều tra và kết quả vụ việc.
- **Độ mới của dữ liệu**, số event thiếu và số lần phải sửa nhãn.
- **Tỷ lệ override** của người rà soát, tỷ lệ khiếu nại/đính chính và ảnh hưởng tới người dùng hợp pháp.

Mục tiêu không phải tối đa số account bị gắn cờ, mà là **phân bổ nguồn lực điều tra vào các trường hợp có bằng chứng đủ tốt và hạn chế thiệt hại do cảnh báo sai**.

## 11. Bảo mật và quản trị dữ liệu liên kết

Các thuộc tính về tài khoản, thiết bị và dòng tiền có độ nhạy cảm cao. Graph có thể tăng khả năng suy luận về người dùng, vì vậy cần hạn chế cả **dữ liệu lưu**, **độ sâu truy vấn** và **quyền xem kết quả**.

### 11.1. Tối thiểu hóa dữ liệu

- Dùng **pseudonymous ID/deviceKey** thay cho định danh thiết bị thô khi có thể.
- Không lưu mật khẩu, access token, dữ liệu thẻ thanh toán đầy đủ hoặc sinh trắc học trong graph điều tra.
- Coi **IP và device fingerprint** là tín hiệu có sai số, không phải sự thật tuyệt đối về nhân thân.
- Thiết kế retention theo mục đích xử lý; định nghĩa việc xóa/đính chính dữ liệu và propagation tới cache/projection.
- Ghi nhận **căn cứ, mục đích, quyền truy cập và audit trail** của những người xem case.

**Hash không mặc nhiên làm dữ liệu vô danh**: nếu chuỗi gốc có entropy thấp, có thể bị đoán lại; nếu chỉ thay bằng token có thể liên kết giữa nhiều nguồn, rủi ro tái nhận dạng vẫn tồn tại. Cần bảo vệ khóa/salt, phân quyền và phạm vi chia sẻ theo chính sách bảo mật.

### 11.2. Cô lập tenant ở mọi bước

Chỉ kiểm tra **WHERE a.tenantId = ...** ở câu cuối là chưa đủ nếu query trước đó đã kéo dữ liệu của tenant khác vào một phép tính chung. Với hệ thống đa tenant:

1. Constraint dùng khóa tenant phù hợp.
2. Quan hệ Account–Device và Account–Transfer–Account phải được **xác nhận cùng tenant** hoặc có quy tắc cross-tenant được phê duyệt.
3. Query Cypher được tham số hóa và giới hạn tenant **tại điểm xuất phát và khi mở rộng**.
4. GDS projection và feature computation phải được cô lập **trước khi tính**, không chỉ lúc hiển thị.
5. Các role cần quyền tối thiểu; người điều tra chỉ được xem tập dữ liệu thuộc vụ việc được giao.

Một lỗi đặc biệt nguy hiểm là tạo Device node theo **deviceKey** toàn cục trong khi chính sách yêu cầu tenant-scoped. Khi đó hai tổ chức có cùng chuỗi deviceKey có thể bị nối chung và tạo kết luận sai.

### 11.3. Quyền con người và trách nhiệm giải thích

Tín hiệu graph nên đưa ra **danh sách bằng chứng**: thiết bị nào, vào thời điểm nào, giao dịch nào, đường đi nào, vì sao chúng được liên kết và có dữ liệu bị thiếu không. Các quyết định ảnh hưởng lớn như **đóng băng tài khoản, từ chối dịch vụ hoặc báo cáo sai phạm** cần kiểm soát bằng quy trình nghiệp vụ/pháp lý thích hợp, đánh giá tác động và khả năng kháng nghị.

**Không dùng đặc điểm nhạy cảm hoặc các proxy dễ gây phân biệt đối xử** làm feature thiếu cơ sở. Cần giám sát tính công bằng, tỷ lệ cảnh báo sai và tính nhất quán giữa các nhóm người dùng bằng phương pháp tuân thủ quy định bảo vệ dữ liệu.

## 12. Kiến trúc triển khai: phát hiện theo sự kiện và batch

### 12.1. Luồng xử lý gợi ý

~~~mermaid
flowchart LR
  E["Transaction/Login events"] --> V["Validate + normalize + deduplicate"]
  V --> G["Neo4j: Account/Device/Transfer"]
  G --> C["Cypher features / GDS batch"]
  C --> R["Rules / scoring / ranking"]
  R --> Q["Case review queue"]
  Q --> H["Human review + outcomes"]
  H --> F["Feedback, audit và model monitoring"]
~~~

**Luồng giao dịch** và **luồng phát hiện** nên có ranh giới lỗi rõ: một request thanh toán thành công không nên tự coi việc ghi graph cảnh báo là đã hoàn tất khi consumer còn trễ. Nếu sử dụng message queue, cần **eventId**, trạng thái xử lý, retry và monitoring để biết dữ liệu ở graph đang trễ đến đâu.

### 12.2. Hai kiểu tính toán

| Kiểu | Phù hợp với | Điểm cần chú ý |
|---|---|---|
| **Online Cypher** | Kiểm tra account hiện tại, chia sẻ device, truy vấn 1–2 bước | Cần index, giới hạn thời gian/độ sâu và dự phòng fan-out |
| **Batch graph analytics / GDS** | Tính connected components, similarity, feature toàn mạng | Cần bộ nhớ projection, dữ liệu có thể stale, làm mới định kỳ |
| **Hybrid** | Phát hiện nhanh bằng rules, bổ sung feature batch | Phải ghi feature timestamp/version và fallback khi feature chưa có |

Không nhất thiết dùng GDS cho mọi yêu cầu API. Một rule đơn giản “account nào cùng thiết bị không công cộng với account đã xác minh?” có thể chạy bằng Cypher ở độ sâu cố định, với các index thích hợp. GDS hữu ích khi bài toán chuyển sang **phân tích toàn mạng lưới** và cần đo được chi phí/tài nguyên.

### 12.3. Java Driver: đọc tín hiệu theo tham số

~~~java
import java.util.List;
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.SessionConfig;

public final class FraudSignalQueries {

    public record SharedDeviceEvidence(
            String otherAccountId, String deviceKey) {}

    public static List<SharedDeviceEvidence> findAccountsSharingDevices(
            Driver driver,
            String database,
            String tenantId,
            String accountId) {

        try (var session = driver.session(
                SessionConfig.forDatabase(database))) {
            return session.executeRead(tx -> tx.run("""
                MATCH (a:DemoFraudAccount {
                  tenantId: $tenantId, accountId: $accountId
                })-[:DEMO_FR_USED_DEVICE]->
                (d:DemoFraudDevice {tenantId: $tenantId})
                <-[:DEMO_FR_USED_DEVICE]-
                (other:DemoFraudAccount {tenantId: $tenantId})
                WHERE other <> a
                  AND d.isPublic = false
                RETURN DISTINCT other.accountId AS otherAccountId,
                       d.deviceKey AS deviceKey
                ORDER BY otherAccountId, deviceKey
                LIMIT 100
                """, Map.of(
                    "tenantId", tenantId,
                    "accountId", accountId
                )).list(row -> new SharedDeviceEvidence(
                    row.get("otherAccountId").asString(),
                    row.get("deviceKey").asString()
                )));
        }
    }
}
~~~

Trên fixture, gọi **findAccountsSharingDevices(driver, "neo4j", "bank-a", "A-100")** cho **A-200** và **A-900** qua D-SHARED, không đưa bank-b vào kết quả. **LIMIT 100** bảo vệ số bản ghi trả về, nhưng **không bảo đảm chi phí duyệt phía trước LIMIT thấp** nếu một hub tạo rất nhiều đường: cần profile và thiết kế lọc/degree cutoff.

Giữ một **Driver** dùng chung ở ứng dụng; **Session** tạo/đóng theo công việc và không dùng đồng thời giữa nhiều luồng. Không nối chuỗi Cypher từ **tenantId/accountId** do client gửi; truyền bằng tham số như ví dụ. Quản lý timeout, connection pool, quyền đọc và định nghĩa hành vi khi graph/feature service tạm thời không có.

### 12.4. Spring Data Neo4j và mapping sự kiện

Với Spring Data Neo4j, cần phân biệt:

- **@Node** cho Account, Device và Transfer.
- **@Relationship** cho USED_DEVICE, SENT và TO, bảo toàn chiều liên kết.
- **Business ID** và uniqueness constraint khác với ID nội bộ framework.
- **@Transactional** có thể gộp các thao tác tạo Transfer + endpoints trong một transaction nếu cấu hình đúng.
- Những truy vấn phức tạp về số đường, điểm rủi ro hoặc GDS có thể dùng **Neo4jClient/custom Cypher** thay vì ép mọi phép phân tích thành entity mapping.

Tránh load toàn bộ subgraph thành object Java chỉ để đếm một số feature; nhiều relationship có thể gây truy vấn lớn và áp lực heap. Trả về **DTO kết quả đã tổng hợp** và chỉ tải đường bằng chứng khi nhà điều tra thực sự mở case.

## 13. Tối ưu truy vấn trên graph lớn

### 13.1. Bắt đầu từ node có khóa chọn lọc

~~~cypher
EXPLAIN
MATCH (a:DemoFraudAccount {
  tenantId: $tenantId,
  accountId: $accountId
})-[:DEMO_FR_USED_DEVICE]->(d:DemoFraudDevice)
RETURN d.deviceKey AS deviceKey;
~~~

Với composite uniqueness constraint cho Account, planner có thể dùng **index seek** để định vị node nguồn trước khi mở rộng sang device. Kiểm tra **EXPLAIN** trên dữ liệu thử nghiệm và **PROFILE** với query đọc an toàn để so **Rows**, **DB Hits** và độ rộng fan-out thực tế.

**EXPLAIN không chạy truy vấn**, **PROFILE có chạy**; không dùng PROFILE trên câu CREATE/MERGE production nếu chỉ muốn xem kế hoạch.

### 13.2. Giới hạn số bước, cửa sổ và hub

- Khởi đầu bằng **tenantId + accountId** hoặc **transferId** có constraint.
- Duyệt **đúng loại relationship**; không dùng **[*1..]** không giới hạn trên graph sản xuất.
- Phân biệt **device công cộng/NAT** với thiết bị có độ tin cậy cao; có quy tắc cutoff riêng.
- Đặt **cửa sổ occurredAt** khi truy vết dòng tiền và loại trạng thái giao dịch không phù hợp.
- Dùng **DISTINCT** theo entity/event ID khi một sự kiện tạo ra nhiều đường.
- Ước lượng chi phí query GDS projection và chi phí làm mới trước khi đưa feature vào API.
- Dùng **timeout**, pagination và quota truy vấn điều tra để không ảnh hưởng phần giao dịch lõi.

Chú ý quan hệ **Account–Device** có thể có bậc rất lớn. Một device nối với \(n\) account tạo khoảng \(n(n-1)/2\) **cặp account không thứ tự**: với 10.000 account là **49.995.000 cặp**. Hệ thống nên phát hiện hub và xử lý bằng cơ chế chuyên biệt, không xuất toàn bộ cặp cho dashboard.

### 13.3. Chỉ mục phục vụ truy vấn thời gian

Nếu truy vấn thường lấy nhiều Transfer trong một tenant theo khoảng **occurredAt**, cân nhắc range index tương ứng:

~~~cypher
CREATE RANGE INDEX demo_fraud_transfer_time IF NOT EXISTS
FOR (t:DemoFraudTransfer)
ON (t.tenantId, t.occurredAt);
~~~

Index không thay thế constraint theo **transferId**, và không đảm bảo mọi truy vấn sẽ dùng index thời gian. Hãy kiểm tra **SHOW INDEXES** (phải ONLINE), **EXPLAIN/PROFILE**, độ chọn lọc và tần suất ghi. Thêm index làm tăng chi phí cập nhật/đĩa, nên chỉ tạo theo workload có bằng chứng.

### 13.4. Projection/feature cache có thể cũ

Named graph trong GDS **không tự cập nhật** sau mỗi transaction Cypher trong database. Nếu account mới dùng một device sau lúc project, phép WCC chạy trên graph cũ không thấy liên kết đó. Phải định nghĩa:

- Chu kỳ tạo/refresh projection.
- Thời điểm và phiên bản feature được tính.
- Cửa sổ dữ liệu/retention.
- Cách xử lý yêu cầu khi feature không có hoặc quá cũ.
- Cách chứng minh feature theo đúng dữ liệu có sẵn tại thời điểm ra quyết định.

## 14. Kiểm thử tính đúng và chống cảnh báo sai

### 14.1. Assertion trên fixture

Sau khi tạo dữ liệu mẫu:

~~~cypher
MATCH (a:DemoFraudAccount)
RETURN count(a) AS accounts;
~~~

~~~cypher
MATCH (d:DemoFraudDevice)
RETURN count(d) AS devices;
~~~

~~~cypher
MATCH (t:DemoFraudTransfer)
RETURN count(t) AS transfers;
~~~

Kỳ vọng **7, 5, 5**. Kiểm tra thêm các cạnh:

~~~cypher
MATCH ()-[u:DEMO_FR_USED_DEVICE]->()
RETURN count(u) AS usageLinks;
~~~

~~~cypher
MATCH ()-[s:DEMO_FR_SENT]->()
RETURN count(s) AS sendLinks;
~~~

~~~cypher
MATCH ()-[r:DEMO_FR_TO]->()
RETURN count(r) AS receiveLinks;
~~~

Kỳ vọng **9, 5, 5**. Count chỉ là một phần của test: cùng số lượng vẫn có thể chứa **liên kết sai tenant hoặc sai endpoint**.

### 14.2. Kiểm tra invariant về tenant và endpoint

~~~cypher
MATCH (a:DemoFraudAccount)-[:DEMO_FR_USED_DEVICE]->
      (d:DemoFraudDevice)
WHERE a.tenantId IS NULL
   OR d.tenantId IS NULL
   OR a.tenantId <> d.tenantId
RETURN a.accountId AS accountId, d.deviceKey AS deviceKey;
~~~

~~~cypher
MATCH (src:DemoFraudAccount)-[:DEMO_FR_SENT]->
      (t:DemoFraudTransfer)-[:DEMO_FR_TO]->
      (dest:DemoFraudAccount)
WHERE src.tenantId IS NULL OR dest.tenantId IS NULL
   OR t.tenantId IS NULL
   OR src.tenantId <> t.tenantId
   OR dest.tenantId <> t.tenantId
RETURN t.transferId AS transferId,
       src.tenantId AS sourceTenant,
       dest.tenantId AS destinationTenant;
~~~

Hai truy vấn phải **không trả hàng**. Đồng thời cần test một Transfer có **đúng một** SENT đi vào và **đúng một** TO đi ra:

~~~cypher
MATCH (t:DemoFraudTransfer)
OPTIONAL MATCH (:DemoFraudAccount)-[s:DEMO_FR_SENT]->(t)
WITH t, count(s) AS senders
OPTIONAL MATCH (t)-[r:DEMO_FR_TO]->(:DemoFraudAccount)
WITH t, senders, count(r) AS receivers
WHERE senders <> 1 OR receivers <> 1
RETURN t.transferId AS transferId, senders, receivers;
~~~

Kết quả phải **0 hàng**. Đây là hợp đồng của ví dụ; nếu Transfer có nhiều bên tham gia, cần sửa model và assertion.

### 14.3. Các ca thử cần có trước production

| Ca kiểm thử | Kỳ vọng |
|---|---|
| Hai account cùng D-SHARED | Được phát hiện là cặp liên kết, không tự gắn nhãn gian lận |
| Nhóm D-PUBLIC | Có liên kết cấu trúc nhưng **không** tăng feature shared-with-confirmed non-public |
| A-100 và A-200 với A-900 | Có evidence từ D-SHARED |
| A-200 gửi T-102 và T-105 | **2** transfer, tổng tiền minh họa 800000 |
| A-100 qua A-200 tới A-900 | Hai đường theo event, không coi T-101 là hai giao dịch |
| bank-b cũng có A-100 và D-SHARED | Không nối vào bank-a khi scope tenant đúng |
| Cùng transferId được nạp lại | Không tạo Transfer node thứ hai |
| Cùng transferId có amount khác | Báo conflict/correction, không âm thầm chấp nhận |
| Event đến trễ | Tính theo occurredAt; có watermark/correction phù hợp |
| Thêm account vào D-PUBLIC | Không làm đội điều tra bị ngập alert chỉ do một hub |
| confirmedFraud bị đính chính | Feature/case phản ánh trạng thái có hiệu lực mới |
| GDS graph chưa refresh | Kết quả có timestamp staleness, không được giả là thời gian thực |

### 14.4. Không dùng dữ liệu thực để tạo ví dụ

Trong test/CI, dùng **dữ liệu tổng hợp** như fixture này. Nếu cần đo trên dữ liệu production đã ẩn danh, phải kiểm chứng biện pháp loại nhận dạng cá nhân, cách bảo vệ mối liên hệ nhạy cảm và quyền truy cập. Việc thay tên bằng ID giả nhưng vẫn giữ mọi kết nối thật **không bảo đảm dữ liệu đã vô danh**.

## 15. Vận hành cảnh báo và quy trình điều tra

### 15.1. Một cảnh báo nên chứa gì?

Thay vì trả chỉ:

~~~json
{"accountId":"A-200","riskScore":70}
~~~

hãy lưu bằng chứng có thể tái dựng, ví dụ:

~~~json
{
  "tenantId": "bank-a",
  "accountId": "A-200",
  "reviewPriorityScore": 70,
  "ruleVersion": "demo-1",
  "features": {
    "confirmedNeighborsOnNonPublicDevice": 1,
    "transfersToConfirmedInWindow": 2
  },
  "evidenceRefs": ["D-SHARED", "T-102", "T-105"],
  "needsHumanReview": true
}
~~~

Đây là **đầu ra mẫu**, không phải kết quả từ một hệ thống gian lận thật và không thay thế audit trail. Với dữ liệu thật, evidence reference cần quyền xem chi tiết và phải có cơ chế **đính chính, thời gian lưu, lưu snapshot và version rule**.

### 15.2. Đánh giá và phản hồi

Một quy trình thường gồm:

1. **Detect:** rule tạo tín hiệu và bằng chứng, không tự kết luận.
2. **Prioritize:** sắp xếp theo độ chắc chắn, thiệt hại tiềm năng và năng lực điều tra.
3. **Review:** nhà phân tích xem đường liên kết, nguồn và thời điểm.
4. **Decide:** quyết định theo quy trình phù hợp, có người chịu trách nhiệm và căn cứ.
5. **Feedback:** cập nhật kết quả xác minh, xử lý cảnh báo trùng và version feature.
6. **Audit:** lưu lịch sử truy cập và mọi thay đổi quyết định.

Không được dùng một rule do bài học đặt ra để **tự động khóa người dùng thật**. Ngoài false positives, một đối tượng tấn công cũng có thể cố tình tạo liên kết thiết bị để “đầu độc graph” và khiến người khác bị đánh dấu nhầm.

### 15.3. Runbook khi tín hiệu đột ngột tăng

| Triệu chứng | Nguyên nhân cần kiểm tra | Hành động |
|---|---|---|
| Alert device-sharing tăng gấp nhiều lần | Dùng nhầm IP NAT làm deviceKey, ingestion duplicate | Kiểm tra schema/nguồn, không kết luận tăng gian lận ngay |
| Một cụm WCC quá lớn | Thiết bị công cộng/độ lớn hub | Phân tích degree, tenant filter, lọc hub phù hợp |
| Chỉ có count, không có evidence | Rule thiếu event ID hoặc metadata | Bổ sung provenance và đường giải thích |
| Nhiều Transfer thiếu sender/receiver | Ingestion nửa chừng, transaction boundary sai | Kiểm tra constraint, workflow idempotent, replay |
| Điểm rủi ro thay đổi sau khi refresh | GDS named graph/cached feature cũ | Kiểm tra version, timestamp và lịch refresh |
| Tỷ lệ false positive tăng | Ngưỡng không phù hợp phân khúc, dữ liệu thiết bị kém | Hiệu chỉnh bằng ground truth, giám sát và review |
| Kết quả lẫn tenant | Device không scope, query/projection lọc quá muộn | Dừng pipeline liên quan, cô lập và điều tra quyền dữ liệu |
| API chậm khi mở rộng graph | Hub degree lớn, duyệt nhiều hop, index thiếu | PROFILE đọc, giới hạn fan-out và đặt budget |

## 16. Bài tập vận dụng

### Bài 1 — Mô hình hóa đúng nghiệp vụ

Thiết kế graph cho Account, Device và Transfer với business key ổn định. Giải thích vì sao Transfer có thể cần một **node riêng** thay vì quan hệ trực tiếp Account → Account, và tại sao **tenantId** phải thuộc khóa trong fixture.

### Bài 2 — Phát hiện thiết bị dùng chung

Viết truy vấn Cypher trả các cặp account cùng dùng một device của **bank-a**, không lặp cả (A,B) và (B,A). Đối chiếu sáu cặp trong mục 5; giải thích tại sao riêng **D-PUBLIC** không nên tự tạo cảnh báo gian lận.

### Bài 3 — Đường tới account đã xác minh

Tìm A-100 và A-200 liên kết tới A-900 qua **D-SHARED**, loại **isPublic = true**. Trình bày bằng chứng thu được, những thông tin chưa biết và cách lưu chúng trong một case review.

### Bài 4 — Chuỗi chuyển hai bước

Viết lại truy vấn A-100 → A-200 → A-900 với cửa sổ tối đa **2 giờ** từ transfer thứ nhất tới thứ hai. Trong fixture, những cặp T-101/T-102 và T-101/T-105 có còn hợp lệ không? Vì sao một transfer đầu được dùng trong hai đường không được đếm hai lần?

### Bài 5 — Tính feature không nhân chéo

So sánh feature **knownNeighbors** và **transfersToKnown** của A-100 và A-200. Hãy giải thích tại sao cần tách từng phép đếm trước khi ghép chúng thành điểm, và tại sao 70 điểm không phải xác suất gian lận.

### Bài 6 — Đánh giá GDS WCC

Chạy projection và WCC trên đồ thị mẫu. Giải thích vì sao hai nhóm account của bank-a đều có ba thành viên nhưng **một nhóm dùng device công cộng**. Đề xuất cách lọc hoặc hạ trọng số hub, và chỉ ra rủi ro nếu projection chưa cô lập tenant.

### Bài 7 — Replay và correction

Message broker gửi lại cùng transferId **T-105** với payload giống lần đầu; sau đó gửi một event sửa số tiền có version cao hơn. Thiết kế khóa, transaction, chính sách idempotency và correction để không tạo Transfer thứ hai hoặc âm thầm che xung đột.

### Bài 8 — Quy trình an toàn cho người dùng

Một account mới bị liên kết tới D-SHARED nhưng chủ tài khoản thông báo đã dùng máy tính công cộng. Hãy lập checklist điều tra, cách ghi bằng chứng phản bác, quy trình cập nhật nhãn và các chỉ số đo false positive. Phân biệt rõ **tín hiệu graph** với **kết luận điều tra**.

## 17. Tổng kết

**Phát hiện gian lận bằng đồ thị không phải phép đếm xem ai có bao nhiêu liên kết.** Giá trị của Neo4j là biểu diễn được **mạng lưới Account – Device – Transfer**, truy vấn các mẫu dùng chung thiết bị, đường chuyển tiền qua trung gian và nhóm liên thông với nguồn bằng chứng có thể kiểm tra lại.

Một pipeline đáng tin cậy cần đi qua:

**Khóa định danh đúng → dữ liệu giao dịch có thời gian/event ID → constraint và ingestion lũy đẳng → Cypher quan hệ/đường đi có giới hạn → feature tách biệt, không nhân chéo → GDS khi cần → chấm điểm minh bạch → rà soát và đính chính bởi con người.**

Các nguyên tắc bắt buộc là **cô lập tenant trước khi tính toán**, **giảm nhiễu từ thiết bị công cộng/hub**, **tránh temporal leakage**, **đo false positives** và **bảo vệ dữ liệu cá nhân**. Trong ứng dụng thật, một đường liên kết chỉ là **giả thuyết cần xác minh**, không phải bằng chứng đủ để quy trách nhiệm.

### Tài liệu chính thức

- [Neo4j Cypher Manual – MATCH và graph patterns](https://neo4j.com/docs/cypher-manual/current/clauses/match/)
- [Neo4j Cypher Manual – MERGE](https://neo4j.com/docs/cypher-manual/current/clauses/merge/)
- [Neo4j Cypher Manual – Create uniqueness constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/create-constraints/)
- [Neo4j Cypher Manual – CALL subqueries](https://neo4j.com/docs/cypher-manual/current/subqueries/call-subquery/)
- [Neo4j Cypher Manual – EXPLAIN and PROFILE](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/)
- [Neo4j GDS – Native graph projection](https://neo4j.com/docs/graph-data-science/current/management-ops/graph-creation/graph-project/)
- [Neo4j GDS – Weakly Connected Components](https://neo4j.com/docs/graph-data-science/current/algorithms/wcc/)
- [Neo4j GDS – Node Similarity](https://neo4j.com/docs/graph-data-science/current/algorithms/node-similarity/)
- [Neo4j Java Driver Manual – Transactions and retries](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Java Driver Manual – Bookmarks and causal consistency](https://neo4j.com/docs/java-manual/current/bookmarks/)
- [Spring Data Neo4j Reference](https://docs.spring.io/spring-data/neo4j/reference/)
