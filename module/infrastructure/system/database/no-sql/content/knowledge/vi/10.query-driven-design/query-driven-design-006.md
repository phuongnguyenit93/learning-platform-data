# Thiết kế sắp xếp trong nhóm và truy vấn theo khoảng

## 1. Bài toán: biết nhóm dữ liệu rồi lấy một đoạn có thứ tự

Trong nhiều hệ NoSQL, câu hỏi quan trọng nhất không phải “cần lưu những thuộc tính nào?”, mà là **ứng dụng sẽ đọc nhóm bản ghi nào, theo thứ tự gì và trong khoảng nào?**

Một hệ thống giám sát có thể ghi hàng triệu sự kiện từ thiết bị. Các yêu cầu thường gặp:

1. Lấy **20 sự kiện mới nhất** của thiết bị D17 thuộc khách hàng T01.
2. Lấy sự kiện của D17 từ **08:00 đến trước 09:00** ngày 14/11/2026.
3. Tiếp tục lấy **trang kế tiếp** mà không lặp sự kiện trang trước.
4. Lấy sự kiện của D17 trong **ba ngày** hoặc liệt kê tất cả sự kiện của tenant T01.

Hai yêu cầu đầu có thể rất nhanh khi dữ liệu được nhóm và sắp theo khóa phù hợp. Nhưng yêu cầu thứ tư có thể phải truy cập **nhiều nhóm/partition**, dù các bản ghi được lưu rất gần nhau về mặt ý nghĩa nghiệp vụ.

Ta sẽ dùng **group key** để gọi tập thành phần xác định một nhóm dữ liệu thường được đọc cùng nhau và **order key** để gọi thành phần định thứ tự trong nhóm. Đây là hai tên khái niệm phục vụ thiết kế, **không phải cú pháp chung** cho mọi cơ sở dữ liệu.

~~~text
Group = (tenantId=T01, deviceId=D17, day=2026-11-14)

Các bản ghi trong group theo eventTime DESC:

08:59:35  EV009  WARN
08:47:12  EV008  OK
08:30:00  EV007  OK
08:00:04  EV006  WARN
07:59:58  EV005  OK
~~~

Nếu ứng dụng hỏi “sự kiện từ 08:00 đến trước 09:00”, có thể xác định một **dải có thứ tự** gồm EV006–EV009. Nếu chỉ hỏi “mọi sự kiện WARN của T01”, chưa chắc có một dải liên tục nào trên cấu trúc khóa này.

## 2. Phân biệt nhóm, thứ tự và phạm vi truy vấn

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Group key** | Những bản ghi nào cần gần nhau về đường truy cập? | tenantId + deviceId + day |
| **Partition key** | Hệ phân tán định tuyến một nhóm dữ liệu tới vùng lưu trữ logic nào? | (T01, D17, 2026-11-14) trong Cassandra |
| **Order key** | Thứ tự các bản ghi trong một nhóm được xác định bằng gì? | eventTime, eventId |
| **Range predicate** | Cần lấy đoạn từ đâu đến đâu? | eventTime ≥ 08:00 và < 09:00 |
| **Sort direction** | Đọc tăng dần hay giảm dần? | Mới nhất trước: DESC |
| **Tie-breaker** | Khi trùng giá trị sắp xếp, xác định thứ tự ổn định bằng gì? | eventId |
| **Cursor** | Lần đọc tiếp theo bắt đầu sau bản ghi nào? | (eventTime, eventId) cuối trang |

Lợi ích của việc tổ chức dữ liệu theo nhóm và thứ tự là giảm số bản ghi cần quét. Nhưng nó kéo theo giới hạn: **truy vấn chỉ hiệu quả khi điều kiện tìm kiếm phù hợp với cấu trúc nhóm và thứ tự đã chọn**.

### 2.1. Sắp xếp trong nhóm không phải sắp xếp toàn bộ dữ liệu

Giả sử ta có:

~~~text
Group D17:
  08:59, 08:47, 08:30

Group D18:
  08:58, 08:55, 08:20
~~~

Mỗi nhóm đều sắp xếp giảm dần theo thời gian. Tuy nhiên, hệ thống **không tự có** một danh sách toàn tenant như:

~~~text
08:59 D17
08:58 D18
08:55 D18
08:47 D17
08:30 D17
08:20 D18
~~~

Muốn lấy “20 sự kiện mới nhất của cả tenant”, cần một đường truy cập riêng, hoặc đọc nhiều nhóm rồi **merge** theo thời gian. Mức chi phí sẽ khác truy vấn một nhóm.

### 2.2. Định danh bản ghi khác điều kiện lọc

Một sự kiện có thể được định danh toàn cục bằng \`eventId\`; nhưng API thường đọc theo \`tenantId\`, \`deviceId\` và thời gian. Vì vậy, lưu theo khóa \`eventId\` là tốt cho tìm đúng một sự kiện nhưng chưa đủ cho lịch sử thiết bị.

Thiết kế NoSQL thường cần **nhiều đường truy cập** cho cùng dữ liệu:

~~~text
eventId                      -> tìm trực tiếp một event
(tenantId, deviceId, day)    -> lịch sử một thiết bị trong ngày
(tenantId, status, day)      -> sự kiện theo trạng thái toàn tenant
~~~

Các đường truy cập bổ sung có thể là secondary index, bảng theo truy vấn hoặc bản chiếu được cập nhật riêng. Mỗi lựa chọn làm tăng chi phí ghi, đồng bộ và vận hành.

## 3. Vì sao thứ tự các thành phần của khóa quyết định truy vấn?

Giả sử một chỉ mục có thứ tự từ điển theo bộ:

~~~text
(tenantId, deviceId, eventTime, eventId)
~~~

Ta có thể hình dung dữ liệu được sắp:

~~~text
T01 | D17 | 08:00 | E1
T01 | D17 | 08:10 | E2
T01 | D17 | 08:20 | E3
T01 | D18 | 08:05 | E4
T01 | D18 | 08:30 | E5
T02 | D17 | 08:00 | E6
~~~

Nếu đã biết **T01 và D17**, các hàng liên quan nằm trong một đoạn kế tiếp nhau. Khi thêm khoảng **eventTime từ 08:00 đến trước 08:15**, chỉ còn E1 và E2 thuộc đoạn cần đọc.

Ngược lại, điều kiện **tenantId = T01, eventTime từ 08:00 đến trước 08:15** nhưng không biết deviceId không xác định một đoạn nhỏ duy nhất vì dữ liệu được chia theo thiết bị trước khi xét thời gian.

### 3.1. Quy tắc tiền tố trái trong cấu trúc có thứ tự

Với thứ tự **(A, B, C)**, các tiền tố trái là:

~~~text
(A)
(A, B)
(A, B, C)
~~~

Thiết kế hay gặp là:

~~~text
Điều kiện bằng nhau: A = x, B = y
Điều kiện khoảng:   C >= lower, C < upper
~~~

Khi A và B đã được cố định, dải C có thể được truy cập liên tục theo thứ tự đã lưu. Đây là lý do nhiều hướng dẫn gợi ý **equality trước, range sau** khi thiết kế chỉ mục ghép.

Nhưng cần hiểu phạm vi của quy tắc:

- Với **compound index có thứ tự** trong MongoDB, thứ tự trường của index rất quan trọng.
- Với **Cassandra**, partition key phải thỏa những quy tắc cụ thể; các clustering columns mới xác định thứ tự hàng **bên trong partition**.
- Với **DynamoDB**, \`Query\` cần biết **đầy đủ giá trị partition key**, rồi mới lọc theo sort key.
- Với **hash key–value store**, tên khóa chứa tiền tố giống nhau không có nghĩa dữ liệu có chỉ mục để quét theo tiền tố.

Không thể lấy quy tắc cho một B-tree/compound index rồi áp nguyên xi cho mọi loại partition key được băm.

### 3.2. Sau điều kiện khoảng, các trường phía sau còn tác dụng gì?

Xét chỉ mục:

~~~text
(tenantId, deviceId, eventTime, status)
~~~

Truy vấn:

~~~text
tenantId = T01
deviceId = D17
eventTime từ 08:00 tới trước 09:00
status = WARN
~~~

Hệ có thể tìm đúng dải thời gian cho nhóm T01/D17, nhưng các bản ghi có \`status = WARN\` **không chắc nằm trong một đoạn liên tục nhỏ** vì \`status\` đứng sau thành phần thời gian biến thiên.

Tùy engine, \`status\` có thể được kiểm tra ngay trong index, dùng để lọc sau khi đọc hoặc có những tối ưu khác. Tuy nhiên, điều kiện này không tương đương một chỉ mục với thứ tự **(tenantId, deviceId, status, eventTime)**.

Nếu người dùng chủ yếu hỏi **“WARN trong một giờ”**, thiết kế theo status trước thời gian có thể tốt hơn. Nếu chủ yếu hỏi **“mọi sự kiện trong một giờ bất kể status”**, thứ tự thời gian trước status thường tự nhiên hơn.

## 4. Thiết kế sắp xếp tăng dần và giảm dần

### 4.1. ASC và DESC phản ánh thao tác đọc chính

Hai API có thể cần thứ tự khác nhau:

~~~text
Lịch sử mới nhất: eventTime DESC
Xử lý chuỗi sự kiện: eventTime ASC
~~~

Một chỉ mục có thứ tự thường hỗ trợ duyệt theo một hoặc hai hướng, tùy hệ. Ví dụ **DynamoDB Query** có \`ScanIndexForward\` để đọc thứ tự tăng/giảm trên sort key; Cassandra có clustering order và quy tắc \`ORDER BY\` tương ứng; MongoDB có thể sử dụng chỉ mục để trả kết quả theo một số mẫu sort nhất định.

Không nên mặc định “chọn DESC sẽ lưu dữ liệu mới vào đầu ổ đĩa” hoặc “đổi hướng đọc không có chi phí”. Hành vi vật lý và khả năng duyệt ngược cần được kiểm tra theo engine.

### 4.2. Khóa sắp xếp phải có thứ tự xác định

Nếu hai sự kiện cùng timestamp:

~~~text
08:30:00.000  EV100
08:30:00.000  EV101
~~~

Chỉ dùng \`eventTime\` có thể khiến hai bản ghi xung đột về khóa trong một số mô hình, hoặc khiến thứ tự kết quả không ổn định khi phân trang. Nên dùng một **tie-breaker** duy nhất:

~~~text
Sort tuple = (eventTime DESC, eventId DESC)
~~~

Khi sắp xếp theo timestamp rồi ID, ta có một thứ tự toàn phần *trong nhóm* nếu ID thực sự duy nhất và cả hai trường có cách so sánh nhất quán.

### 4.3. Nên dùng timestamp của sự kiện hay thời điểm nhận?

Hai thời điểm có ý nghĩa khác nhau:

- **eventTime**: thời điểm sự kiện thực sự xảy ra tại nguồn.
- **ingestedAt**: thời điểm hệ thống nhận/lưu sự kiện.

Nếu thiết bị mất mạng rồi gửi bù, một event với \`eventTime = 08:00\` có thể đến lúc 12:00. Sắp theo eventTime sẽ chèn event vào lịch sử quá khứ, trong khi sắp theo ingestedAt sẽ cho thứ tự tiếp nhận.

Hãy chọn theo câu hỏi nghiệp vụ:

| Nhu cầu | Thời gian nên ưu tiên |
| --- | --- |
| Biểu đồ nhiệt độ theo diễn biến thực tế | eventTime |
| Theo dõi bản ghi vừa tới hệ thống | ingestedAt |
| Phát hiện sự kiện đến muộn | Cần cả eventTime và ingestedAt |
| Replay dữ liệu theo thứ tự ghi nhận | ingestedAt hoặc sequence của log |

Nếu cần cả hai kiểu truy vấn thường xuyên, có thể phải tạo hai đường đọc hoặc lưu hai chỉ mục.

## 5. Chọn biên của truy vấn khoảng

Một cách diễn đạt bền vững cho khoảng thời gian là:

\[
[t_{start},t_{end})
\]

Nghĩa là **bao gồm** thời điểm bắt đầu và **không bao gồm** thời điểm kết thúc:

~~~text
eventTime >= 2026-11-14T08:00:00Z
eventTime <  2026-11-14T09:00:00Z
~~~

Ưu điểm của khoảng nửa mở:

- Hai cửa sổ liên tiếp \`[08:00,09:00)\` và \`[09:00,10:00)\` không chồng biên.
- Không cần đoán “thời điểm cuối” của một giây/phút/ngày khi dữ liệu có độ chính xác milliseconds, microseconds hay nanoseconds.
- Dễ tổng hợp theo giờ, ngày, tháng khi tính khoảng ở tầng ứng dụng.

Một số API chỉ cung cấp phép **BETWEEN bao gồm cả hai đầu**, hoặc chỉ cho một điều kiện range trên sort key. Khi đó phải chuyển đổi cận đúng theo kiểu khóa và semantics hệ quản trị; **không nên mặc định mọi sản phẩm nhận cú pháp \`>= from AND < to\` trong cùng điều kiện khóa**.

### 5.1. Chuẩn hóa thời gian và múi giờ

Đừng tạo khóa bằng chuỗi địa phương tùy ý:

~~~text
14/11/2026 08:00
2026-11-14 08:00+07
2026-11-14T01:00:00Z
~~~

Ba dạng biểu diễn có thể nói về cùng thời điểm hoặc không, tùy timezone. Nếu cần so sánh từ điển, phải dùng định dạng thống nhất, ví dụ ISO 8601 UTC với độ rộng cố định:

~~~text
2026-11-14T01:00:00.000Z
2026-11-14T02:00:00.000Z
~~~

Khi mọi chuỗi có cùng định dạng UTC và độ chính xác, thứ tự từ điển thường tương ứng thứ tự thời gian. Nếu trộn timezone, độ rộng phần giây hoặc định dạng ngày, điều này có thể sai. Khi engine có kiểu **timestamp/date** thực, thường nên dùng kiểu đó thay vì tự ép chuỗi.

### 5.2. Truy vấn “một ngày” phải xác định timezone nghiệp vụ

“Ngày 14/11/2026” theo UTC khác “ngày 14/11/2026” tại Việt Nam.

Nếu ứng dụng lưu timestamp UTC nhưng người dùng chọn ngày theo \`Asia/Ho_Chi_Minh\`, tầng API phải chuyển đúng:

~~~text
Ngày địa phương 2026-11-14:
  [2026-11-14 00:00+07, 2026-11-15 00:00+07)

Khoảng UTC tương ứng:
  [2026-11-13T17:00:00Z, 2026-11-14T17:00:00Z)
~~~

Với những timezone có chuyển đổi giờ mùa hè, không được luôn cộng cứng 24 giờ vào một thời điểm UTC rồi cho là ngày địa phương kế tiếp. Hãy xác định **đầu ngày tiếp theo trong timezone nghiệp vụ**, sau đó chuyển thành UTC.

## 6. Một thiết kế theo nhóm và thời gian: dữ liệu thiết bị

Xét tập sự kiện:

~~~json
{
  "tenantId": "T01",
  "deviceId": "D17",
  "eventId": "EV009",
  "eventTime": "2026-11-14T08:59:35.000Z",
  "ingestedAt": "2026-11-14T09:00:02.000Z",
  "status": "WARN",
  "temperature": 39.2
}
~~~

Các truy vấn có thể lập thành bảng:

| Truy vấn | Điều kiện bằng nhau | Khoảng / sort | Mức ưu tiên |
| --- | --- | --- | --- |
| Q1: 20 sự kiện mới nhất của D17 | tenantId, deviceId | eventTime DESC | Rất cao |
| Q2: lịch sử D17 trong một giờ | tenantId, deviceId, ngày/bucket | eventTime trong khoảng | Rất cao |
| Q3: lịch sử D17 trong một tuần | tenantId, deviceId | Nhiều bucket ngày | Trung bình |
| Q4: mọi sự kiện WARN của T01 hôm nay | tenantId, status, ngày | eventTime DESC | Trung bình |
| Q5: tra một sự kiện theo ID | eventId | Không cần sắp xếp | Thấp |

Một nhóm \`(tenantId, deviceId)\` chứa toàn bộ lịch sử có thể tăng không giới hạn. Thêm **bucket thời gian** vào group giúp giới hạn số bản ghi:

~~~text
group = (tenantId, deviceId, eventDayUTC)
order = (eventTime DESC, eventId)
~~~

Hệ quả:

1. Q2 tìm nhanh nếu biết group đúng ngày.
2. Q1 có thể cần xem ngày hiện tại và những ngày trước nếu ngày hiện tại có ít sự kiện.
3. Q3 phải đọc nhiều group rồi ghép kết quả.
4. Q4 cần đường truy vấn khác, vì dữ liệu đã được chia theo device trước.

Đây là **sự đánh đổi có chủ đích**: giới hạn kích thước và tải mỗi group để đổi lấy chi phí fan-out khi hỏi khoảng dài.

## 7. Cassandra: partition key và clustering order

Cassandra thể hiện rõ mô hình “nhóm rồi sắp trong nhóm”. Ví dụ:

~~~sql
CREATE TABLE events_by_device_day (
    tenant_id text,
    device_id text,
    event_day date,
    event_time timestamp,
    event_id uuid,
    status text,
    temperature double,
    PRIMARY KEY (
        (tenant_id, device_id, event_day),
        event_time,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    event_time DESC,
    event_id ASC
);
~~~

Trong khóa:

- **(tenant_id, device_id, event_day)** là **composite partition key**. Cả ba trường cùng xác định một partition logic.
- **event_time** là clustering column thứ nhất, dùng để sắp theo thời gian.
- **event_id** phân biệt những sự kiện xảy ra cùng timestamp.
- **status** và **temperature** là cột dữ liệu, không tự tạo đường truy vấn theo status.

### 7.1. Truy vấn khoảng trong một partition

~~~sql
SELECT event_time, event_id, status, temperature
FROM events_by_device_day
WHERE tenant_id = 'T01'
  AND device_id = 'D17'
  AND event_day = '2026-11-14'
  AND event_time >= '2026-11-14T08:00:00Z'
  AND event_time <  '2026-11-14T09:00:00Z'
LIMIT 100;
~~~

Truy vấn xác định đầy đủ partition key và đặt khoảng lên clustering column đầu, nên tương thích với cấu trúc đã thiết kế. Giới hạn \`LIMIT\` giúp API không cố trả mọi sự kiện trong một lần.

Nếu muốn thứ tự đã khai báo:

~~~sql
SELECT event_time, event_id, status
FROM events_by_device_day
WHERE tenant_id = 'T01'
  AND device_id = 'D17'
  AND event_day = '2026-11-14'
ORDER BY event_time DESC, event_id ASC
LIMIT 20;
~~~

Trong Cassandra, \`ORDER BY\` trên clustering columns có những giới hạn riêng và yêu cầu partition key phù hợp. Không thể dùng nó như một phép \`ORDER BY\` tùy ý trên toàn bộ tập partition kiểu SQL quan hệ.

### 7.2. Vì sao không thể bỏ một phần partition key?

Truy vấn này **không phải đường đọc thiết kế cho table trên**:

~~~sql
-- Không phải truy vấn hiệu quả dựa vào khóa chính đã chọn.
SELECT * FROM events_by_device_day
WHERE tenant_id = 'T01'
  AND event_day = '2026-11-14';
~~~

Nó thiếu \`device_id\`, thành phần của partition key ghép. Cassandra cần đủ thông tin khóa phù hợp để định vị partition; không thể coi composite partition key đã băm là một compound B-tree cho phép bỏ thành phần giữa.

Nếu cần “mọi sự kiện của tenant trong ngày” thường xuyên, hãy cân nhắc table khác như \`events_by_tenant_day\` với bucket phù hợp hoặc pipeline phân tích. Không nên thêm \`ALLOW FILTERING\` chỉ để làm cho truy vấn chạy được mà không xem chi phí đọc rộng.

### 7.3. Truy vấn qua nhiều partition

API muốn lấy ba ngày liên tiếp của D17:

~~~text
group (T01, D17, 2026-11-12)
group (T01, D17, 2026-11-13)
group (T01, D17, 2026-11-14)
~~~

Ứng dụng có thể đọc ba partition rồi merge theo thời gian. Nếu dữ liệu nằm trong ngày không trùng nhau và cần mới nhất trước, có thể đọc các ngày theo thứ tự từ mới đến cũ rồi tiếp tục khi hết dữ liệu; nếu có trùng/khác timezone hoặc nhiều bucket cùng một khoảng, phải merge theo khóa sắp xếp thực tế.

Không nên nhận định “các partition có ngày gần nhau nên nằm liền trên đĩa”. Cassandra phân phối partition theo token băm; các giá trị ngày liên tiếp không mặc định nằm cạnh nhau về mặt vật lý.

### 7.4. Độ lớn và độ nóng của partition

Một thiết bị tạo 2 sự kiện/giây:

~~~text
2 × 60 × 60 × 24 = 172.800 sự kiện/ngày
~~~

Với event có nhiều cột, partition theo ngày vẫn có thể lớn. Nếu một gateway phát hàng nghìn sự kiện mỗi giây, partition ngày có thể trở thành điểm nóng. Có thể dùng partition theo giờ hoặc thêm bucket:

~~~text
(tenantId, deviceId, day, hour)
~~~

Nhưng đổi lại truy vấn cả ngày cần truy cập nhiều partition. Cần đo với **thiết bị lớn nhất và tải cao nhất**, không chỉ lấy số trung bình. Không có ngưỡng kích thước partition an toàn chung cho mọi workload, phiên bản và phần cứng.

### 7.5. Clustering không thay transaction

Các hàng trong cùng partition dễ được đọc theo một khoảng, nhưng “nằm cùng nhóm” không đồng nghĩa các cập nhật nhiều hàng có đầy đủ ngữ nghĩa transaction của RDBMS. Nếu nghiệp vụ cần đảm bảo nhiều bản ghi cùng đúng, phải kiểm tra phạm vi hỗ trợ write atomicity, batch, lightweight transaction và cách khôi phục của phiên bản Cassandra cụ thể.

## 8. DynamoDB: partition key bằng nhau, điều kiện trên sort key

DynamoDB hỗ trợ primary key dạng **partition key + sort key**. Ví dụ bảng phục vụ sự kiện theo thiết bị và ngày:

~~~text
PK = "TENANT#T01#DEVICE#D17#DAY#2026-11-14"
SK = "EVENT#2026-11-14T08:59:35.000Z#EV009"

Attributes:
  status = WARN
  temperature = 39.2
~~~

Các item chung PK tạo một **item collection theo khóa phân vùng**; SK xác định thứ tự logic của các item có cùng PK. Với sort key kiểu chuỗi, DynamoDB so sánh theo thứ tự byte của chuỗi UTF-8; vì vậy cần mã hóa timestamp nhất quán.

### 8.1. Query một khoảng bằng BETWEEN

Ví dụ mô tả lệnh Query theo API kiểu DynamoDB:

~~~json
{
  "TableName": "DeviceEvents",
  "KeyConditionExpression": "PK = :pk AND SK BETWEEN :from AND :to",
  "ExpressionAttributeValues": {
    ":pk": {
      "S": "TENANT#T01#DEVICE#D17#DAY#2026-11-14"
    },
    ":from": {
      "S": "EVENT#2026-11-14T08:00:00.000Z"
    },
    ":to": {
      "S": "EVENT#2026-11-14T08:59:59.999Z#~"
    }
  },
  "ScanIndexForward": false,
  "Limit": 20
}
~~~

Điểm cần hiểu:

- **PK = :pk** là điều kiện bắt buộc để Query bảng theo partition key chính.
- **SK BETWEEN ... AND ...** sử dụng một điều kiện trên sort key với **hai cận đều bao gồm**.
- **ScanIndexForward = false** yêu cầu trả các item phù hợp theo thứ tự SK giảm dần.
- **Limit** giới hạn số item được đánh giá trong một lần Query; nếu có filter sau đọc, số item thực trả có thể ít hơn limit.
- Phân trang dùng thông tin khóa trang tiếp theo mà dịch vụ trả về, không nên dùng offset tùy ý.

Ví dụ cận trên \`#~\` chỉ minh họa một ý tưởng bao phủ hậu tố ID theo quy tắc khóa giả định. **Không sử dụng ký tự này làm “giá trị lớn nhất” chung**: thứ tự UTF-8, ký tự ID hợp lệ và độ chính xác thời gian phải được định nghĩa chính xác. Trong hệ thật, có thể chọn khóa thời gian dạng số, prefix tháng/giờ, hoặc cận chuẩn hóa đã được xác minh.

Nếu chỉ cần các sự kiện trong tháng và SK có prefix đều đặn, một lựa chọn khác là:

~~~json
{
  "KeyConditionExpression": "PK = :pk AND begins_with(SK, :prefix)",
  "ExpressionAttributeValues": {
    ":pk": {
      "S": "TENANT#T01#DEVICE#D17#MONTH#2026-11"
    },
    ":prefix": {
      "S": "EVENT#2026-11-14T08:"
    }
  }
}
~~~

Điều kiện \`begins_with\` ở ví dụ này áp dụng **trên SK**, với giá trị PK đã xác định. Nếu PK ban đầu đã gồm **DAY#2026-11-14** thì phải dùng đúng PK ngày, không tự thay thành PK tháng trừ khi thiết kế lưu trữ đã chọn bucket tháng.

### 8.2. Không thể Query bằng prefix của partition key

Giả sử:

~~~text
PK = TENANT#T01#DEVICE#D17#DAY#2026-11-14
PK = TENANT#T01#DEVICE#D17#DAY#2026-11-15
~~~

Dù hai PK có chung prefix, lệnh \`Query\` trên bảng **không** cho phép hỏi “PK bắt đầu bằng TENANT#T01#DEVICE#D17” để tự tìm mọi ngày. Truy vấn cần đủ một giá trị PK. Muốn đọc hai ngày, ứng dụng phải biết các PK cần truy vấn và gộp kết quả, hoặc tạo index/bản chiếu khác.

### 8.3. FilterExpression không thay đường truy cập

Nếu Query lấy mọi sự kiện trong giờ rồi dùng \`FilterExpression\` với \`status = WARN\`, filtering xảy ra **sau khi item đã được đọc theo điều kiện khóa**. Vì vậy, nó không tự tiết kiệm toàn bộ chi phí đọc mà một GSI hoặc bản chiếu theo status có thể giúp.

Nếu truy vấn theo status rất phổ biến, một đường truy cập có thể là:

~~~text
GSI-PK = TENANT#T01#STATUS#WARN#DAY#2026-11-14
GSI-SK = EVENT#2026-11-14T08:59:35.000Z#EV009
~~~

Đổi lại, GSI tốn dung lượng và chi phí cập nhật; các GSI của DynamoDB có đặc tính đọc nhất quán cuối cùng, không cung cấp strongly consistent reads. Với dữ liệu quan trọng, cần xác định thời điểm cập nhật và cơ chế kiểm tra lại khi cần.

### 8.4. Một điểm phân trang quan trọng

DynamoDB có thể giới hạn dữ liệu trả về trong một Query theo dung lượng trang, ngay cả khi đã đặt Limit lớn. Kết quả có thể có \`LastEvaluatedKey\`. Tầng ứng dụng cần dùng giá trị này làm \`ExclusiveStartKey\` cho truy vấn cùng điều kiện ở trang tiếp theo.

Không nên suy luận rằng “trang nhận 20 item nghĩa là đã đọc hết dữ liệu” hoặc “trang nhận 0 item sau filter nghĩa là không còn trang nào”. Chỉ kết luận hết khi API cho biết không còn continuation key theo hợp đồng của dịch vụ.

## 9. MongoDB: compound index kết hợp equality, sort và range

MongoDB có thể tạo một **compound index**:

~~~javascript
db.events.createIndex({
  tenantId: 1,
  deviceId: 1,
  eventTime: -1,
  _id: -1
});
~~~

Thứ tự trường và hướng index tạo đường đọc phù hợp cho:

~~~javascript
db.events
  .find({
    tenantId: "T01",
    deviceId: "D17",
    eventTime: {
      $gte: ISODate("2026-11-14T08:00:00Z"),
      $lt: ISODate("2026-11-14T09:00:00Z")
    }
  })
  .sort({ eventTime: -1, _id: -1 })
  .limit(20);
~~~

Hai trường đầu được lọc bằng nhau, sau đó dùng khoảng thời gian và sắp xếp theo **eventTime DESC**. Trường **_id** là tie-breaker để các sự kiện trùng thời điểm vẫn có thứ tự xác định.

### 9.1. Một chỉ mục không tối ưu cho mọi thứ tự

Với index trên:

| Yêu cầu | Đánh giá sơ bộ |
| --- | --- |
| Lịch sử theo tenant + device, mới nhất trước | Phù hợp |
| Lịch sử theo tenant + device trong một giờ | Phù hợp |
| Mọi sự kiện theo tenant, mới nhất trước, không biết device | Không được phục vụ tối ưu trực tiếp vì thiếu trường deviceId đứng giữa |
| Sự kiện theo status, mới nhất trước | Cần đánh giá index khác hoặc phương án đọc khác |
| Một sự kiện theo _id | Có đường index _id mặc định, không phải nhờ index lịch sử |

Trong MongoDB, **ESR (Equality, Sort, Range)** là một nguyên tắc hữu ích để cân nhắc thứ tự trường của compound index, nhưng không phải công thức áp dụng cứng cho mọi truy vấn. Khi truy vấn vừa có sort vừa có range trên nhiều field khác nhau, cần cân nhắc tính chọn lọc, độ rộng khoảng và cách index hỗ trợ sort. Kiểm tra bằng \`explain()\` trên dữ liệu đại diện để thấy index scan, số key/document được đọc và thao tác sort còn lại.

### 9.2. Keyset pagination với hai khóa sắp xếp

Giả sử trang đầu kết thúc tại:

~~~text
eventTime = 2026-11-14T08:30:00Z
_id       = 6736f123456789abcdef0010   (ObjectId giả định)
~~~

Với thứ tự **eventTime DESC, _id DESC**, trang tiếp theo cần các bản ghi nhỏ hơn tuple cuối trang theo thứ tự từ điển:

~~~javascript
const cursorTime = ISODate("2026-11-14T08:30:00Z");
const cursorId = ObjectId("6736f123456789abcdef0010");

db.events.find({
  tenantId: "T01",
  deviceId: "D17",
  $or: [
    { eventTime: { $lt: cursorTime } },
    { eventTime: cursorTime, _id: { $lt: cursorId } }
  ]
})
.sort({ eventTime: -1, _id: -1 })
.limit(20);
~~~

Đây là **seek/keyset pagination**: lấy dữ liệu *sau* tuple cuối của trang trước, thay vì bỏ qua hàng nghìn kết quả bằng \`skip()\`. Với tập dữ liệu có cập nhật đồng thời, cần hiểu rằng cursor giúp xác định ranh giới thứ tự nhưng **không tự tạo một snapshot nhất quán cho toàn bộ phiên phân trang**.

Truy vấn dùng \`$or\` cần được kiểm tra kế hoạch thực thi; hiệu quả phụ thuộc index và optimizer. Nếu dữ liệu dùng ID kiểu khác, cách so sánh tie-breaker phải theo kiểu thực tế chứ không sao chép ObjectId máy móc.

## 10. Redis sorted set: sắp theo điểm số trong một nhóm

Redis là key–value store nhưng có kiểu dữ liệu **sorted set (ZSET)**: các **member** duy nhất có **score** dạng số, được duy trì theo thứ tự score. Một thiết kế có thể gán một key cho mỗi thiết bị:

~~~text
Key: events:T01:D17

Member  Score (timestamp)
EV006   1000
EV007   2000
EV008   3000
EV009   4000
~~~

Các giá trị score đơn giản ở đây minh họa thứ tự thời gian; hệ thực có thể dùng epoch milliseconds nếu miền giá trị và độ chính xác phù hợp.

Thao tác minh họa:

~~~redis
ZADD events:T01:D17 1000 EV006
ZADD events:T01:D17 2000 EV007
ZADD events:T01:D17 3000 EV008
ZADD events:T01:D17 4000 EV009

ZRANGE events:T01:D17 1500 3500 BYSCORE
~~~

Kết quả là các member có score từ **1500 đến 3500**, tức EV007 và EV008 theo dữ liệu đã thêm. Truy vấn mới nhất trước theo cú pháp Redis hiện đại:

~~~redis
ZRANGE events:T01:D17 +inf -inf BYSCORE REV LIMIT 0 20
~~~

Điều này khác cơ chế \`Query\` của DynamoDB hoặc clustering của Cassandra:

- Key Redis \`events:T01:D17\` xác định một sorted set.
- **Score** điều khiển thứ tự bên trong set.
- Member phải **duy nhất**; thêm lại cùng member có thể cập nhật score thay vì tạo bản ghi mới.
- Nếu nhiều member trùng score, Redis dùng thứ tự từ điển của member để phân định theo semantics sorted set.
- Score là số thực dấu phẩy động; phải kiểm tra độ chính xác. Epoch milliseconds trong miền thông dụng có thể biểu diễn nguyên chính xác dưới giới hạn 53-bit; epoch nanoseconds cỡ \(10^{18}\) không thể được bảo toàn nguyên chính xác bằng IEEE-754 double.

Ví dụ giá trị chi tiết sự kiện có thể nằm ở key khác:

~~~text
events:T01:D17                    -> ZSET(score=eventTime, member=eventId)
event:EV009                       -> HASH/JSON chứa status, nhiệt độ, nội dung
~~~

Nhưng lúc này có hai cấu trúc cần phối hợp: index theo thời gian và nội dung sự kiện. Nếu chỉ cập nhật ZSET mà không ghi value hoặc ngược lại, kết quả tìm kiếm có thể tham chiếu tới dữ liệu thiếu. Cần thiết kế atomic write/transaction hoặc cơ chế sửa sai lệch theo khả năng của Redis.

**Không nhầm ZSET với quét khóa có tiền tố.** \`SCAN MATCH events:T01:*\` lặp qua tên key và không tự trả lịch sử toàn tenant được sắp theo thời gian. Muốn kiểu truy vấn đó phải tổ chức một sorted set/index khác hoặc fan-out trên nhiều key.

## 11. Ordered key–value store: mã hóa khóa và quét theo tiền tố

Một số kho key–value có thứ tự hỗ trợ **range scan theo bytes**. Khi đó ứng dụng có thể mã hóa khóa:

~~~text
T01|D17|2026-11-14T08:00:04.000Z|EV006
T01|D17|2026-11-14T08:30:00.000Z|EV007
T01|D17|2026-11-14T08:47:12.000Z|EV008
T01|D17|2026-11-14T08:59:35.000Z|EV009
T01|D18|2026-11-14T08:50:00.000Z|EV010
~~~

Với mã hóa giữ thứ tự và phân cách không mơ hồ, khoảng cần đọc có thể là:

~~~text
start = "T01|D17|2026-11-14T08:00:00.000Z|"
end   = "T01|D17|2026-11-14T09:00:00.000Z|"

read [start, end)
~~~

Truy vấn đọc một dải byte liên tiếp **chỉ khi engine thật sự lưu/truy cập khóa theo thứ tự byte và hỗ trợ range scan**. Việc ghép tiền tố chuỗi trong một hash map hoặc key–value store phân vùng theo hash không tạo ra năng lực đó.

### 11.1. Mã hóa phải không va chạm

Ghép hai giá trị mà không có quy tắc:

~~~text
(tenant="AB", device="C") -> "ABC"
(tenant="A", device="BC") -> "ABC"
~~~

Đây là hai cặp khác nhau nhưng trùng khóa. Ngay cả dùng dấu \`|\` cũng có thể va chạm nếu một thành phần tự chứa dấu \`|\`. Cần escape delimiter, length-prefix hoặc một tuple encoding có thể giải mã một cách duy nhất.

### 11.2. Thứ tự số khác thứ tự chuỗi

Nếu lưu số thứ tự dạng chuỗi:

~~~text
"1", "10", "100", "2"
~~~

Thứ tự từ điển không tương đương thứ tự số. Với số nguyên không âm trong miền giới hạn, có thể pad độ rộng:

~~~text
"000001", "000002", "000010", "000100"
~~~

Số âm, số thực, binary key và kiểu thời gian cần cơ chế mã hóa giữ thứ tự phù hợp hơn. Không nên chỉ “thêm vài số 0” mà không định nghĩa miền giá trị.

### 11.3. Prefix successor không phải cộng ký tự tùy ý

Nếu API range cần cận trên để lấy mọi khóa bắt đầu bằng \`T01|D17|\`, cần dùng **prefix successor** theo thứ tự byte của engine. Việc thêm ký tự \`~\`, \`z\` hay byte giả định “lớn nhất” có thể bỏ sót khóa chứa Unicode hoặc byte lớn hơn giá trị đó. Nên sử dụng hàm prefix-range của SDK hoặc một quy tắc byte encoding được chứng minh đúng.

## 12. Thiết kế các nhóm bằng bucket thời gian

Bucket là cách chia một luồng dữ liệu liên tục thành các nhóm hữu hạn:

~~~text
Không bucket:
  group = (tenantId, deviceId)

Bucket theo tháng:
  group = (tenantId, deviceId, YYYY-MM)

Bucket theo ngày:
  group = (tenantId, deviceId, YYYY-MM-DD)

Bucket theo giờ:
  group = (tenantId, deviceId, YYYY-MM-DD-HH)
~~~

### 12.1. Bucket nhỏ và bucket lớn

| Thiết kế | Lợi ích | Chi phí |
| --- | --- | --- |
| Theo thiết bị, không bucket | Một group cho cả lịch sử | Có thể phình to vô hạn, nóng |
| Theo tháng | Ít group cho truy vấn dài | Group lớn với thiết bị ghi nhiều |
| Theo ngày | Giới hạn kích thước rõ hơn | Truy vấn nhiều ngày phải fan-out |
| Theo giờ | Giảm số bản ghi mỗi group | Truy vấn một ngày chạm nhiều group |
| Ngày + shard/bucket hash | Phân tán ghi cho nguồn rất nóng | Đọc phải lấy nhiều shard và merge |

Chọn bucket từ **tần suất ghi thực tế, kích thước bản ghi, retention, độ rộng khoảng thường query và ngưỡng độ trễ mục tiêu**. Không có một bucket “ngày” mặc định đúng cho mọi hệ.

### 12.2. Ví dụ ước lượng kích thước nhóm

Giả sử một thiết bị tạo 5 event/giây:

\[
5 \times 60 \times 60 \times 24 = 432{,}000\ \text{event/ngày}
\]

Nếu mỗi event sau khi tính cả metadata và overhead lưu trữ chiếm trung bình 500 byte, dữ liệu logic thô ước tính:

\[
432{,}000 \times 500 = 216{,}000{,}000\ \text{byte/ngày}
\]

Đây chỉ là **ước lượng minh họa**, chưa tính compression, index, tombstone, replication, write amplification, log hoặc chi phí lưu trữ engine. Với lưu lượng như vậy, partition theo ngày có thể cần đánh giá kỹ; một giờ có khoảng 18.000 event theo mức trung bình đã cho.

Điểm quan trọng là quan sát **thiết bị lớn nhất** và lúc lưu lượng đỉnh. Một nhóm lớn không chỉ tốn dung lượng mà còn ảnh hưởng compaction, repair, pagination và thời gian phục hồi tùy sản phẩm.

### 12.3. Group nóng và group lớn là hai vấn đề khác nhau

- **Group lớn:** tích lũy rất nhiều bản ghi, dù hiện tại ít truy cập.
- **Group nóng:** chịu tốc độ đọc/ghi quá cao tại một thời điểm, dù dung lượng chưa lớn.

Thêm bucket theo ngày giúp giới hạn dung lượng lịch sử, nhưng **không giải quyết hoàn toàn** một nguồn ghi 100.000 event/giây vào group của ngày hiện tại. Có thể phải thêm shard, phân tách nguồn, phân phối khóa hoặc điều chỉnh hạ tầng. Mỗi giải pháp tăng độ phức tạp khi đọc.

## 13. Range scan trong một group và truy vấn xuyên nhiều group

### 13.1. Một group

Truy vấn:

~~~text
Get events of T01/D17
where eventDay = 2026-11-14
and 08:00 <= eventTime < 09:00
order by eventTime desc
limit 20
~~~

Nếu khóa đúng, đây là một **range scan trong group** có giới hạn. Hệ có thể định vị group, tìm đầu khoảng và duyệt theo thứ tự.

### 13.2. Nhiều group

Truy vấn “lấy 20 sự kiện mới nhất của T01 trong toàn bộ 10 thiết bị” cần dữ liệu từ:

~~~text
T01/D01  T01/D02  ...  T01/D10
~~~

Một cách làm là **k-way merge**:

1. Lấy phần đầu của mỗi luồng đã sắp giảm dần.
2. Đưa bản ghi đầu mỗi luồng vào cấu trúc ưu tiên theo \`(eventTime, eventId)\`.
3. Lấy bản ghi mới nhất toàn cục, sau đó lấy tiếp phần tử ở luồng vừa dùng.
4. Dừng khi đủ 20 bản ghi hoặc tất cả các luồng đã hết.

~~~mermaid
flowchart TD
    A["Group D01: sorted DESC"] --> M["Merge theo (time, ID)"]
    B["Group D02: sorted DESC"] --> M
    C["Group D03: sorted DESC"] --> M
    M --> O["Top 20 mới nhất của tenant"]
~~~

Đây là cách ghép các luồng **đã có thứ tự**, không tự giải quyết chi phí đọc quá nhiều nhóm. Nếu tenant có hàng triệu thiết bị, fan-out trực tiếp có thể không chấp nhận được.

Khi truy vấn toàn tenant là đường đọc chính, nên thiết kế **bản chiếu riêng** có group theo tenant, ngày và bucket, hoặc pipeline phân tích phù hợp. Một index duy nhất tối ưu cho lịch sử từng thiết bị không bắt buộc phải đáp ứng mọi nhu cầu truy vấn khác.

### 13.3. Đừng sắp xếp toàn bộ ở tầng ứng dụng

Cách kém hiệu quả:

~~~text
Lấy 1.000.000 sự kiện trong ngày
    -> tải tất cả về API
    -> sort trên RAM
    -> lấy 20 sự kiện đầu
~~~

Cách tốt hơn khi workload cho phép:

~~~text
Thiết kế group + order key đúng
    -> query dải hẹp có limit
    -> chỉ merge số luồng cần thiết
    -> trả 20 kết quả
~~~

Thiết kế dữ liệu theo truy vấn giảm công việc đọc và truyền dữ liệu, nhưng có thể tăng số index/bản chiếu. Quyết định tối ưu phải xét cả chi phí ghi và đồng bộ.

## 14. Phân trang theo khoảng và cursor

### 14.1. Vì sao OFFSET sâu là vấn đề?

Một truy vấn kiểu:

~~~text
sort eventTime DESC
skip 100000
take 20
~~~

có thể cần xét một số lượng lớn bản ghi trước khi tới trang mong muốn. Không phải NoSQL nào cũng có OFFSET; kể cả khi có, chi phí trang sâu có thể tăng đáng kể.

**Cursor/keyset pagination** dùng khóa của bản ghi cuối trang trước:

~~~text
Order = eventTime DESC, eventId DESC

Page 1:
  (09:10, E9)
  (09:05, E7)
  (09:00, E5)   <- cursor

Page 2:
  chỉ lấy các tuple < (09:00, E5)
~~~

Với hai thành phần đều giảm dần, điều kiện seek logic là:

~~~text
eventTime < lastTime
OR
(eventTime = lastTime AND eventId < lastEventId)
~~~

Phép so sánh này là **mô hình logic**; API CQL/DynamoDB/Redis có cách biểu đạt cụ thể khác nhau. Không nên chép nguyên điều kiện OR vào tất cả các hệ.

### 14.2. Cursor cần chứa những gì?

Một cursor cho lịch sử thiết bị có thể cần:

~~~json
{
  "tenantId": "T01",
  "deviceId": "D17",
  "bucket": "2026-11-14",
  "lastEventTime": "2026-11-14T08:30:00.000Z",
  "lastEventId": "EV007",
  "sort": "eventTime_desc_eventId_desc",
  "version": 1
}
~~~

Đây là ví dụ **nội dung logic**, không nhất thiết nên gửi JSON thô cho client. Trong ứng dụng thực tế, có thể mã hóa và ký cursor để tránh bị sửa dữ liệu điều khiển truy vấn. Cursor phải được ràng buộc với bộ lọc/tenant/quyền của người dùng và có vòng đời phù hợp.

Nếu dùng phân trang gốc của engine như DynamoDB \`LastEvaluatedKey\` hoặc paging state của driver Cassandra, cần dùng đúng token tiếp tục của engine và điều kiện query ban đầu. Token này không mặc định có thể dùng cho mọi truy vấn khác hoặc mọi phiên bản index.

### 14.3. Chuyển bucket khi hết dữ liệu

Giả sử API lấy 20 sự kiện mới nhất trong ngày 14 nhưng chỉ có 5 sự kiện. Ứng dụng có thể:

1. Lấy 5 sự kiện ngày 14.
2. Tiếp tục ngày 13 cho tới khi đủ 20.
3. Nếu cần, lặp sang ngày 12.
4. Trả một cursor ghi nhận bucket đang đọc và vị trí tiếp theo.

Nếu có dữ liệu đến muộn cho ngày 14 sau khi client đã chuyển sang ngày 13, nó có thể không xuất hiện trong các trang cũ. Cần làm rõ **ngữ nghĩa phân trang khi dữ liệu thay đổi**: muốn một snapshot cố định, đọc gần thời gian thực, hay chấp nhận kết quả biến động?

### 14.4. Dữ liệu chèn/xóa khi đang phân trang

Cursor theo khóa sắp xếp giúp giảm hiện tượng dịch trang do offset, nhưng không tự giải quyết mọi thay đổi đồng thời:

- Bản ghi mới hơn cursor xuất hiện sau trang 1 có thể không nằm trong các trang tiếp theo.
- Một bản ghi cũ đến muộn có thể xuất hiện ở trang sau dù nó mới được ghi.
- Một bản ghi bị xóa trước khi đọc trang sau sẽ không còn trong kết quả.
- Nếu thứ tự khóa bị sửa (ví dụ eventTime thay đổi), bản ghi có thể di chuyển qua ranh giới cursor.

Khi yêu cầu đọc snapshot nhất quán, cần dùng cơ chế snapshot/point-in-time của hệ hoặc cố định một mốc truy vấn phù hợp, sau đó định nghĩa rõ cách xử lý late arrivals.

## 15. Sắp xếp và truy vấn theo khoảng khi có các trường bổ sung

Một truy vấn thực tế thường kết hợp nhiều điều kiện:

~~~text
tenant = T01
device = D17
time ∈ [08:00, 09:00)
status = WARN
temperature >= 38
sort time DESC
~~~

Không phải mọi điều kiện đều cần nằm trong khóa chính. Ta có thể phân loại:

| Vai trò | Trường ví dụ | Cách xử lý cân nhắc |
| --- | --- | --- |
| Xác định nhóm | tenantId, deviceId, day | Partition/group key |
| Xác định đoạn và thứ tự | eventTime, eventId | Sort/clustering/index keys |
| Lọc bổ sung | status, temperature | Filter sau truy xuất, index riêng hoặc bản chiếu |
| Hiển thị | message, payload | Field dữ liệu đọc cùng bản ghi |

Nếu khoảng thời gian đã hẹp và chỉ có tối đa vài chục event, lọc \`status\` và \`temperature\` sau khi đọc có thể hoàn toàn hợp lý. Nếu khoảng chứa hàng triệu event nhưng chỉ 0,1% là WARN, một đường truy cập theo status có thể cần thiết.

**Không có một quy tắc rằng mọi điều kiện WHERE đều phải là khóa.** Cần cân bằng độ chọn lọc, chi phí index, cập nhật và tần suất truy vấn.

### 15.1. Khi nào tạo chỉ mục thứ cấp hoặc bản chiếu?

Trả lời:

- Truy vấn đó chiếm bao nhiêu phần trăm lưu lượng đọc?
- Trên đường hiện tại, cần đọc trung bình và p99 bao nhiêu bản ghi để trả 20 kết quả?
- Dữ liệu nguồn thay đổi thường xuyên không?
- Bản chiếu có được phép trễ vài giây?
- Có cần cập nhật nhiều bản chiếu theo transaction không?
- Chi phí lưu trữ, reindex và recovery tăng bao nhiêu?

Ví dụ:

~~~text
Base:
  (tenant, device, day) -> eventTime DESC

Read model:
  (tenant, status, day, bucket) -> eventTime DESC
~~~

Nếu mỗi event được ghi vào cả hai nơi, cần quy định nguồn sự thật, retry, idempotency và phát hiện bản chiếu thiếu.

## 16. Thiết kế khóa và truy vấn khi dữ liệu có độ lệch

Trong hệ phân tán, một partition/group có thể cực kỳ lớn hoặc nóng do một số khóa phổ biến.

Ví dụ:

~~~text
Tenant T01:
  Device D17: 5 events/s
  Device D18: 8 events/s
  Device GATEWAY: 50,000 events/s
~~~

Nếu nhóm theo thiết bị và ngày, GATEWAY tạo lưu lượng khác hẳn phần còn lại. Cần mô phỏng phân bố thực thay vì chỉ thử với dữ liệu đều.

### 16.1. Bucket theo thời gian và shard theo tải có mục tiêu khác nhau

- **Bucket thời gian** giới hạn khối lượng lịch sử trong một khoảng.
- **Shard/bucket hash** phân phối một khóa đang có lưu lượng rất cao ra nhiều nhóm.

Một thiết kế có thể là:

~~~text
group = (tenantId, deviceId, day, shardNumber)
order = (eventTime DESC, eventId)
~~~

Với \`shardNumber = hash(eventId) mod N\`, ghi được phân phối qua N group. Nhưng đọc lịch sử thiết bị phải truy vấn N group, rồi merge theo thời gian. Việc thay N về sau làm thay đổi cách tìm dữ liệu cũ; cần version hoặc quy tắc migration.

### 16.2. Khóa bị nóng do một thời điểm

Nếu mỗi bản ghi gắn ngày bằng timezone và mọi luồng ghi đều đặt ngày hiện tại vào partition key duy nhất:

~~~text
partitionKey = "2026-11-14"
~~~

toàn bộ dữ liệu trong ngày có thể dồn vào một partition nóng. Thêm thành phần nguồn/thiết bị hoặc shard mới giúp phân bố tải, nhưng làm truy vấn toàn ngày phức tạp hơn.

Mục tiêu thiết kế là tìm được **điểm cân bằng giữa số nhóm phải đọc và lượng tải trên từng nhóm**, không chỉ tối thiểu hóa một trong hai.

## 17. Một số rủi ro tính đúng đắn thường bị bỏ qua

### 17.1. Trùng timestamp và ghi đè

Nếu dùng timestamp làm toàn bộ khóa sắp xếp và hệ yêu cầu khóa \`(partition, sort)\` phải duy nhất, hai event cùng thời điểm có thể ghi đè cùng item/hàng. Cần thêm \`eventId\` duy nhất trong khóa hoặc một sequence được tạo đúng cách.

### 17.2. Dữ liệu đến muộn

Event tạo lúc 08:00 nhưng đến 12:00 có thể chèn ngược vào vùng thời gian 08:00. Nếu ứng dụng chỉ quét “dữ liệu mới theo eventTime lớn nhất” rồi cập nhật watermark, nó có thể bỏ sót event đến muộn. Cần watermark, độ trễ chấp nhận, scan theo ingestedAt hoặc xử lý event-time đúng với bài toán.

### 17.3. Sửa giá trị dùng làm khóa

Trong nhiều hệ, đổi partition key/sort key thực chất cần **xóa bản ghi cũ và tạo bản ghi mới**; không phải sửa tại chỗ như một thuộc tính bình thường. Nếu thời gian hoặc nhóm có thể thay đổi, phải thiết kế cập nhật và chống bản ghi “mồ côi”.

### 17.4. TTL và dữ liệu hết hạn

Khi dữ liệu sự kiện có TTL, chỉ mục có thể vẫn phải xử lý dấu vết xóa/tombstone trong một thời gian tùy engine. Truy vấn qua vùng dữ liệu đã hết hạn có thể chịu chi phí khác với truy vấn trên dữ liệu còn sống. Bucket thời gian và chính sách compaction/retention cần được thiết kế tương thích với workload thực.

### 17.5. Đồng bộ nhiều bản chiếu

Khi viết một event vào:

~~~text
events_by_device_day
errors_by_tenant_day
events_by_id
~~~

một lần lỗi mạng có thể khiến các bản chiếu không đồng bộ. Nên có ID ổn định, xử lý retry idempotent, theo dõi lag và cơ chế đối soát. Việc các bảng cùng chứa eventId không tự làm cập nhật nhiều bảng thành transaction xuyên hệ.

### 17.6. Phân trang và quyền truy cập

Cursor không được cho phép người dùng tự sửa \`tenantId\` để đọc nhóm của tenant khác. API phải xác thực quyền trên dữ liệu/nhóm được yêu cầu và ràng buộc cursor với query context. Không nên xem cursor là cơ chế ủy quyền.

## 18. Quy trình thiết kế theo truy vấn có thể áp dụng lại

### Bước 1: Viết chính xác truy vấn nóng

Không chỉ ghi “tìm sự kiện” mà viết:

~~~text
Input:
  tenantId, deviceId, fromInclusive, toExclusive, pageSize

Output:
  events trong [fromInclusive, toExclusive)
  order by eventTime DESC, eventId DESC
  pageSize tối đa 20

Latency target:
  đo p95/p99 với dữ liệu lớn nhất dự kiến
~~~

Nêu rõ yêu cầu **độ chính xác thời gian, timezone, độ mới dữ liệu và quyền truy cập**.

### Bước 2: Xác định nhóm tự nhiên và kích thước của nó

Những điều kiện nào luôn biết trước? Nếu luôn có tenant và device, chúng là ứng viên cho group key. Chọn bucket thời gian dựa vào retention và quy mô thực, không đoán.

### Bước 3: Chọn order key và tie-breaker

Chọn \`(eventTime, eventId)\` hoặc thứ tự khác phù hợp cách đọc. Nếu sử dụng encoded string, bảo đảm timestamp, số và ID có encoding ổn định và giữ thứ tự.

### Bước 4: Biểu diễn khoảng và kiểm tra API thực tế

Xác định:

~~~text
Start inclusive
End exclusive
Ascending/descending
Limit
Cursor
~~~

Sau đó ánh xạ sang khả năng của sản phẩm: Cassandra clustering range, DynamoDB sort-key condition, MongoDB compound index, Redis ZSET score range hoặc ordered KV range scan.

### Bước 5: Phân tích các truy vấn ngoài đường đọc chính

Nếu truy vấn vượt qua nhiều group, có chấp nhận fan-out và merge không? Nếu không, lập đường đọc riêng và dự toán chi phí ghi/đồng bộ.

### Bước 6: Đo trên trường hợp xấu có cơ sở

Kiểm tra:

- Group lớn nhất và group nóng nhất.
- Truy vấn một giờ, một ngày và nhiều tháng.
- Tỷ lệ dữ liệu thực khớp filter sau range.
- Thời gian xử lý merge giữa nhiều group.
- Truy vấn trang 1 và trang sâu.
- Tài liệu/sự kiện đến muộn, timestamp trùng, cập nhật/xóa.
- Độ trễ p95/p99, số key/item đã đọc, I/O và chi phí vận hành.

### Bước 7: Thiết kế lifecycle và khả năng sửa đổi

Quy định cách đổi kích thước bucket, bổ sung index, backfill dữ liệu cũ, giữ phiên bản cursor và giám sát các bản chiếu. Nếu đổi thứ tự khóa, cần biết cách di chuyển dữ liệu và thời điểm chuyển truy vấn, thay vì chỉ đổi mã tạo key.

## 19. Các lỗi thiết kế điển hình

| Lỗi | Hệ quả | Hướng xử lý |
| --- | --- | --- |
| Chỉ chọn khóa duy nhất theo eventId | Không đọc nhanh lịch sử một thiết bị | Thêm đường đọc theo tenant/device/time |
| Nhóm mọi event của tenant vào một partition | Partition nóng/lớn | Chia theo nguồn, thời gian hoặc bucket |
| Để status sau eventTime nhưng thường xuyên lọc status | Có thể phải lọc nhiều bản ghi trong dải thời gian | Cân nhắc index theo status trước time |
| Chỉ dùng timestamp làm sort key | Trùng thời điểm có thể gây ghi đè/không ổn định | Thêm ID duy nhất |
| Dùng BETWEEN nhưng hiểu như [start, end) | Trùng dữ liệu ở biên hai cửa sổ | Đổi cận đúng semantics API |
| Dùng ngày địa phương làm khóa nhưng query bằng UTC | Sai nhóm tại ranh giới ngày | Chuẩn hóa và ghi rõ timezone |
| Cho rằng prefix PK tự Query được DynamoDB | Truy vấn không hợp lệ/không đúng đường đọc | Query từng PK đầy đủ hoặc thêm đường đọc |
| Dùng \`ALLOW FILTERING\` thay khóa Cassandra | Đọc rộng, trễ khó dự đoán | Mô hình lại theo truy vấn |
| Dùng \`skip\` rất lớn trong MongoDB | Truy vấn trang sâu tốn kém | Seek/cursor theo khóa sắp xếp |
| Dùng Redis SCAN thay range query | Quét nhiều key và không có thứ tự nghiệp vụ | ZSET/index theo nhóm phù hợp |
| Quên late arrivals và dữ liệu thay đổi khi phân trang | Thiếu/lặp bản ghi hoặc hiển thị thiếu | Định nghĩa cursor, watermark, snapshot |
| Dựa vào index phụ mà quên độ trễ đồng bộ | Kết quả cũ hoặc chưa đủ | Theo dõi lag, retry, đối soát |

## 20. Bài tập thực hành

### Bài 1: Chọn thứ tự khóa

Một ứng dụng quản lý đơn cần truy vấn thường xuyên nhất:

> Lấy 20 đơn gần nhất của khách C08 thuộc tenant T01.

Chọn giữa:

~~~text
A. (orderId, tenantId, customerId, createdAt)
B. (tenantId, customerId, createdAt DESC, orderId)
C. (tenantId, createdAt DESC, customerId, orderId)
~~~

**Gợi ý:** Với một chỉ mục ghép có thứ tự, **B** thường phù hợp nhất vì cố định tenant và customer trước, sau đó đọc thời gian giảm dần; orderId giúp ổn định khi trùng timestamp. **A** thuận lợi hơn cho lookup theo orderId, còn **C** phù hợp hơn với lịch sử toàn tenant.

### Bài 2: Phát hiện sai biên

Hai batch lần lượt lấy:

~~~text
Batch 1: eventTime BETWEEN 08:00 AND 09:00
Batch 2: eventTime BETWEEN 09:00 AND 10:00
~~~

**Câu hỏi:** Nếu BETWEEN bao gồm hai đầu, event đúng 09:00 xuất hiện mấy lần?

**Gợi ý:** Xuất hiện ở cả hai batch. Dùng khoảng nửa mở \`[08:00, 09:00)\` và \`[09:00, 10:00)\` nếu engine/API hỗ trợ trực tiếp, hoặc chuyển cận đúng cách theo loại dữ liệu.

### Bài 3: Xác định partition Cassandra

Cho:

~~~sql
PRIMARY KEY ((tenant_id, device_id, day), event_time, event_id)
~~~

Bốn hàng:

~~~text
(T01, D17, 2026-11-14, 08:00, E1)
(T01, D17, 2026-11-14, 08:01, E2)
(T01, D17, 2026-11-15, 08:00, E3)
(T01, D18, 2026-11-14, 08:00, E4)
~~~

**Gợi ý:** Có ba partition logic. E1 và E2 ở cùng partition; E3 và E4 thuộc hai partition khác. Event time và eventId phân biệt hàng trong một partition.

### Bài 4: DynamoDB và sort-key prefix

Table có:

~~~text
PK = TENANT#T01#DEVICE#D17#DAY#2026-11-14
SK = EVENT#<UTC timestamp>#<eventId>
~~~

**Câu hỏi:** Có thể Query mọi ngày bằng \`begins_with(PK, "TENANT#T01#DEVICE#D17")\` không? Có thể truy vấn sự kiện giờ 08 bằng sort-key prefix không?

**Gợi ý:** Không thể dùng prefix PK như điều kiện Query trên primary key của bảng. Query cần một giá trị PK đầy đủ. Với PK đã biết, \`begins_with(SK, "EVENT#2026-11-14T08:")\` có thể phù hợp nếu SK là chuỗi có định dạng thời gian thống nhất.

### Bài 5: Cursor khi trùng timestamp

Một trang có:

~~~text
09:00 E9
08:30 E8
08:30 E7
08:30 E6
~~~

Sắp theo \`time DESC, id DESC\`. Trang đầu gồm ba dòng, kết thúc tại **(08:30, E7)**.

**Câu hỏi:** Trang sau phải bắt đầu từ đâu để lấy E6 mà không lặp E7?

**Gợi ý:** Chỉ lấy tuple **nhỏ hơn (08:30, E7)** theo thứ tự đã định, tức thời gian nhỏ hơn 08:30 hoặc cùng thời gian nhưng ID nhỏ hơn E7. Cursor chỉ chứa timestamp sẽ không đủ để phân biệt E7 và E6.

### Bài 6: Fan-out từ nhiều nhóm

Hệ có 1.000 thiết bị trong tenant T01, mỗi thiết bị có các sự kiện sắp mới nhất trước. API phải lấy **50 sự kiện mới nhất toàn tenant**.

**Câu hỏi:** Vì sao đọc 50 sự kiện từ mỗi thiết bị rồi sort không phải lúc nào cũng tốt? Nêu một giải pháp khi truy vấn này rất thường xuyên.

**Gợi ý:** Đọc 50 × 1.000 = 50.000 event chỉ để lấy top 50 gây tốn I/O/mạng. Có thể dùng merge có kiểm soát, nhưng fan-out 1.000 nhóm vẫn đắt. Nếu đây là đường đọc nóng, thiết kế bản chiếu theo tenant/ngày/bucket với thứ tự thời gian và cơ chế đồng bộ rõ ràng.

### Bài 7: Chọn bucket

Một thiết bị bình thường ghi 100 sự kiện/ngày, nhưng một gateway ghi 500.000 sự kiện/ngày. Hầu hết truy vấn xem **60 phút gần nhất**.

**Gợi ý:** Cân nhắc group theo giờ cho gateway hoặc bucket linh hoạt theo nguồn; đo kích thước/độ nóng và số group API phải đọc. Không cần ép mọi thiết bị dùng cùng bucket nếu mô hình và vận hành cho phép phân tầng hợp lý.

### Bài 8: Sự kiện đến muộn

Sự kiện E1 xảy ra lúc 08:00 nhưng gửi đến hệ thống lúc 12:00. Job theo dõi chỉ đọc event có \`eventTime > 11:59\` mỗi phút.

**Câu hỏi:** E1 có được xử lý không?

**Gợi ý:** Không, nếu job chỉ duyệt eventTime lớn dần theo watermark 11:59. Cần dùng luồng tiếp nhận, ingestedAt, độ trễ chờ, replay hoặc cơ chế late-event riêng, tùy tính chất nghiệp vụ.

## 21. Kết luận

Trong thiết kế NoSQL theo truy vấn, **sắp xếp trong nhóm** cho phép đọc nhanh một tập bản ghi có chung khóa truy cập theo thứ tự đã chọn. **Truy vấn theo khoảng** giúp giới hạn phần dữ liệu cần đọc, thường bằng cách cố định các thành phần group/partition rồi truy cập dải sort/clustering key.

Hiệu quả thực tế phụ thuộc vào **thứ tự khóa, tính duy nhất của tie-breaker, cận khoảng, timezone, kích thước và độ nóng của nhóm, số nhóm cần fan-out và cách phân trang**. Cassandra, DynamoDB, MongoDB, Redis sorted set và ordered key–value có cơ chế khác nhau; không thể áp một cú pháp hay quy tắc tiền tố cho tất cả.

Hãy bắt đầu bằng các truy vấn cụ thể và số liệu tải, chọn nhóm cùng thứ tự phù hợp, rồi xác định rõ những truy vấn nào cần index/bản chiếu bổ sung. Một cấu trúc tốt phải cho kết quả đúng ở ranh giới thời gian, khi có timestamp trùng, dữ liệu đến muộn và nhiều trang đọc liên tiếp, đồng thời giữ chi phí đọc/ghi trong khả năng vận hành.
