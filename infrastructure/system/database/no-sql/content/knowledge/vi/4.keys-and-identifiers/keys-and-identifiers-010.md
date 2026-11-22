# Thời gian trong khóa, giới hạn thứ tự và ảnh hưởng đồng hồ

## 1. Thời gian có vai trò gì trong khóa NoSQL?

Trong hệ thống NoSQL, một khóa không chỉ phân biệt bản ghi. Hình dạng khóa có thể quyết định dữ liệu nằm ở partition nào, được truy vấn theo khoảng ra sao, có thể sắp theo thời gian hay không và việc bổ sung bản ghi mới ảnh hưởng thế nào đến tải hệ thống.

Xét một sự kiện học tập:

~~~json
{
  "eventId": "20261114T081527123Z-a18d6f",
  "userId": "student-42",
  "type": "LESSON_COMPLETED",
  "occurredAt": "2026-11-14T08:15:25.920Z",
  "ingestedAt": "2026-11-14T08:15:27.123Z",
  "lessonId": "nosql-08"
}
~~~

ID bắt đầu bằng thời gian ở dạng `yyyyMMdd'T'HHmmssSSS'Z'`. Người đọc có thể đoán bản ghi được cấp ID gần 08:15:27.123 UTC. Dù vậy, một khóa có chứa thời gian **không tự bảo đảm** rằng:

- Hai bản ghi không bao giờ trùng ID.
- ID lớn hơn chắc chắn được tạo sau trong thời gian thực.
- Thứ tự ID chính là thứ tự nghiệp vụ xảy ra.
- Thứ tự tạo ID trùng với thứ tự commit vào cơ sở dữ liệu.
- Mọi máy chủ đều có đồng hồ chính xác và đồng bộ.
- Hệ quản trị có thể truy vấn theo khoảng hiệu quả chỉ vì ký tự đầu của khóa là timestamp.

Trong môi trường nhiều nút, **thứ tự thời gian**, **thứ tự nhân quả**, **thứ tự cấp ID** và **thứ tự ghi/quan sát dữ liệu** là các khái niệm khác nhau. Phân biệt được chúng là nền tảng để chọn chiến lược định danh và khóa sắp xếp phù hợp.

## 2. Phân biệt ID, partition key, sort key và timestamp nghiệp vụ

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Record ID | Xác định duy nhất một bản ghi trong phạm vi đã quy định | `eventId` |
| Partition/shard key | Quyết định dữ liệu đi đến partition hoặc shard nào | `userId`, `tenantId` |
| Sort/clustering key | Sắp xếp bản ghi trong một partition nếu hệ quản trị hỗ trợ | `eventTime#eventId` |
| Composite key | Kết hợp nhiều thành phần để định danh và truy xuất | `tenantId#day#timestamp#suffix` |
| Thời gian nghiệp vụ | Khi một hành động được cho là xảy ra | `occurredAt` |
| Thời gian tiếp nhận | Khi dịch vụ nhận được sự kiện | `ingestedAt` |

Một sản phẩm NoSQL có thể chỉ có một primary key; sản phẩm khác phân biệt partition key và sort key. Có sản phẩm dùng index riêng để phục vụ lọc theo thời gian. Do đó, **thiết kế khóa phải dựa trên cơ chế của DBMS thực tế**, không dựa riêng vào chuỗi ID.

### 2.1. Một sự kiện có thể có nhiều thời điểm

~~~text
08:15:25.920  Người dùng thực sự hoàn thành bài học
08:15:27.123  Ứng dụng nhận sự kiện và cấp ID
08:15:27.150  DBMS xác nhận thao tác ghi
08:15:27.180  Replica khác nhận dữ liệu
08:15:27.240  Người dùng ở khu vực khác đọc thấy dữ liệu
~~~

Các con số chỉ minh họa. Khi mốc thời gian được ghi bởi **những đồng hồ khác nhau**, độ chênh lệch hiển thị không nhất thiết chính là độ chênh thời gian thực.

Các thuật ngữ thường dùng:

- **Event time (`occurredAt`):** thời điểm sự kiện xảy ra theo nghiệp vụ, có thể do thiết bị client ghi nhận.
- **Ingestion time:** thời điểm hệ thống nhận dữ liệu.
- **Generation time:** thời điểm bộ sinh ID chạy.
- **Commit time:** thời điểm thao tác được DBMS công nhận hoàn thành theo bảo đảm cấu hình.
- **Observation time:** thời điểm người đọc nhận thấy bản cập nhật.

Ví dụ, điện thoại hoàn thành bài học lúc 08:00 trong khi offline, đến 10:00 mới gửi sự kiện. Nếu server cấp ID khi nhận dữ liệu thì timestamp trong ID gần 10:00, còn `occurredAt` vẫn là 08:00. Ngược lại, nếu client cấp ID lúc offline, timestamp trong ID phụ thuộc độ đúng của đồng hồ điện thoại.

Vì thế, khi dữ liệu có giá trị nghiệp vụ theo thời gian, nên lưu trường thời gian có ý nghĩa rõ ràng bên cạnh ID, thay vì buộc ứng dụng phải suy đoán mọi thời điểm từ phần đầu của khóa.

## 3. Lợi ích của khóa có yếu tố thời gian

### 3.1. Sắp xếp gần đúng theo thời điểm cấp khóa

Một định dạng cố định có thể tạo các ID như:

~~~text
20261114T081527123Z-a9f1
20261114T081527124Z-012c
20261114T081528000Z-4bd2
~~~

Khi sử dụng cùng múi giờ UTC, cùng độ chính xác, cùng độ dài và bộ so sánh từ điển phù hợp, phần timestamp khiến các khóa được nhóm theo thứ tự tăng của thời gian đã mã hóa.

Nhưng **hai ID cùng mili giây** còn phụ thuộc phần suffix. Suffix ngẫu nhiên giúp phân biệt bản ghi, không chứng minh thứ tự tạo.

### 3.2. Truy vấn lịch sử theo khoảng

Với một mô hình lưu trữ như sau:

~~~text
Partition key = student-42
Sort key      = 20261114T081527123Z#a9f1
Sort key      = 20261114T081527124Z#012c
Sort key      = 20261114T081528000Z#4bd2
~~~

Ứng dụng có thể truy vấn lịch sử của một học viên trong một khoảng hoặc lấy N bản ghi mới nhất, **nếu DBMS hỗ trợ range scan trên sort key**. Nếu DBMS băm toàn bộ ID rồi phân phối ngẫu nhiên, không thể mặc nhiên dựa vào tiền tố timestamp để có truy vấn khoảng hiệu quả.

### 3.3. Dễ quan sát và truy vết

Khi đọc log, timestamp trong khóa có thể giúp suy đoán thời điểm cấp định danh, hỗ trợ phân tích sự cố và đối chiếu dữ liệu. Tuy nhiên, ID có thể sinh trước khi ghi, bị giữ lại trong hàng đợi, đến từ máy sai giờ hoặc được import từ dữ liệu cũ. Timestamp trong ID là **thông tin về quy trình cấp ID**, chưa chắc là thời gian phát sinh nghiệp vụ.

### 3.4. Tính cục bộ của dữ liệu mới

Trong một số cấu trúc chỉ mục có thứ tự, các khóa tăng dần có thể tạo mẫu ghi và quét thuận lợi. Nhưng có đánh đổi:

- Với chỉ mục có cấu trúc B-tree, key tăng có thể tập trung thao tác thêm ở gần một đầu.
- Với hệ dựa trên LSM-tree, lợi ích phụ thuộc phân bố truy vấn, memtable, SSTable, compaction và index.
- Với range sharding, các ghi mới liên tục dồn vào shard chứa khoảng khóa cuối, dễ tạo **hot shard**.

Không nên kết luận một ID có thời gian luôn giúp mọi NoSQL DBMS ghi nhanh hơn.

## 4. Các kiểu ID liên quan đến thời gian

| Cách tạo | Nội dung chính | Đặc điểm thứ tự | Giới hạn |
|---|---|---|---|
| UUIDv4 | Bit ngẫu nhiên | Không phản ánh thời gian | Không phù hợp làm khóa sắp thời gian |
| UUIDv1 | Thời gian và metadata của bộ sinh | Có thành phần thời gian | Bố cục không thuận tiện cho mọi phép so sánh; có rủi ro lộ metadata |
| UUIDv6 | Sắp xếp lại phần thời gian của v1 | Thuận lợi hơn cho sắp theo thời gian | Không loại bỏ clock skew |
| UUIDv7 | Timestamp Unix mili giây 48 bit và các bit bổ sung | Thường sắp gần đúng theo thời gian | Cùng mili giây phụ thuộc bộ sinh; không có thứ tự toàn cụm |
| ULID | Timestamp mili giây 48 bit và 80 bit ngẫu nhiên | Chuỗi mã hóa chuẩn thường sắp từ điển theo thời gian | Monotonicity chỉ thuộc phạm vi được thư viện bảo đảm |
| Snowflake-style | Thời gian + worker ID + sequence | Có thể tăng trong phạm vi nguồn cấp | Cần giải quyết worker trùng, clock rollback và sequence overflow |
| Timestamp + suffix | Timestamp ở tiền tố và phần phân biệt | Tùy định dạng/comparator | Phần ngẫu nhiên không mang thứ tự phát sinh |
| Sequence do DBMS cấp | Bộ đếm hoặc vị trí tuần tự | Tăng trong phạm vi sequence | Không tự biểu thị thời gian hoặc thứ tự commit toàn hệ thống |

Không có định dạng đáp ứng trọn vẹn mọi yêu cầu. Để chọn, cần biết dữ liệu được phân tán ở đâu, mức thứ tự phải bảo đảm là gì và có cần cấp ID khi offline hay không.

### 4.1. UUIDv7

UUIDv7 đặt timestamp Unix có độ phân giải mili giây ở phần bit cao của định danh theo bố cục chuẩn. Khi so sánh theo cách tương thích với định dạng UUID chuẩn, ID từ những mili giây sau thường xếp sau ID từ mili giây trước.

Giới hạn cần nhớ:

1. Hai máy có đồng hồ lệch có thể sinh UUIDv7 ngược thứ tự thời gian thực.
2. Nếu nhiều UUIDv7 cùng mili giây và phần còn lại sinh ngẫu nhiên, thứ tự giữa chúng không nhất thiết giống thứ tự được cấp.
3. Một bộ sinh có thể bổ sung cơ chế tăng đơn điệu cục bộ nhưng không tự đồng bộ với bộ sinh ở máy khác.
4. Phải kiểm tra cách DBMS và driver so sánh các giá trị UUID dạng binary, kiểu UUID chuyên biệt hoặc chuỗi; không suy ra thứ tự chỉ từ hình thức hiển thị.

UUIDv7 thường hữu ích cho **ID phân tán có tính cục bộ theo thời gian**, không phải bằng chứng về thứ tự nghiệp vụ.

### 4.2. ULID và monotonic ULID

ULID gồm thời gian mili giây và thành phần ngẫu nhiên, thường biểu diễn thành chuỗi 26 ký tự Crockford Base32. Dạng mã hóa chuẩn cho phép sắp xếp từ điển theo timestamp.

Một **monotonic ULID generator** có thể tăng phần bổ sung khi nhiều ID được cấp trong cùng mili giây, từ đó giữ thứ tự tăng **trong bộ sinh đó**. Nhưng nhiều tiến trình khác nhau không chia sẻ trạng thái bộ đếm; đồng hồ có thể đi lùi, và chính sách xử lý phải được xác định.

“Monotonic trong một process” và “mọi sự kiện trên toàn cụm được sắp đúng” là hai mức bảo đảm khác nhau.

### 4.3. Snowflake-style ID

Một thiết kế minh họa dùng số nguyên 64 bit không âm:

~~~text
1 bit dấu | 41 bit timestamp | 10 bit worker | 12 bit sequence
       0 | ms từ custom epoch | worker ID     | counter
~~~

- Timestamp: số mili giây từ một epoch riêng của hệ thống.
- Worker: mã phân biệt nguồn cấp ID, ví dụ 10 bit có 1.024 giá trị.
- Sequence: mã thứ tự trong một mili giây trên từng worker, ví dụ 12 bit có 4.096 giá trị.

Phép ghép về mặt ý tưởng:

~~~text
id = ((timestampMs - customEpochMs) << 22)
   | (workerId << 12)
   | sequence
~~~

Đây là một **bố cục ví dụ**, không phải định nghĩa bắt buộc của mọi biến thể Snowflake. Để không trùng ID, bộ sinh phải kiểm soát cấp worker ID, thao tác cạnh tranh giữa thread, trạng thái khi restart, giới hạn sequence và đồng hồ đi lùi.

Với JavaScript, các ID số nguyên 64 bit có thể vượt giới hạn số nguyên biểu diễn chính xác của `Number` là `2^53 - 1`. Nếu đưa vào JSON, phải cân nhắc chuỗi thập phân hoặc cách biểu diễn số nguyên lớn được hỗ trợ từ đầu tới cuối, tránh mất bit ở client.

### 4.4. Timestamp trong ObjectId không phải thứ tự tạo tuyệt đối

ObjectId của MongoDB có thành phần timestamp theo giây cùng các thành phần khác để phân biệt bản ghi. Có thể suy ra thời điểm tạo gần đúng, nhưng **không bảo đảm thứ tự nghiêm ngặt giữa các client** trong cùng giây hoặc khi đồng hồ lệch. ID cũng có thể được sinh trước lúc ghi thực tế.

Tương tự, đừng xem “ID có timestamp” là hợp đồng sắp xếp toàn hệ thống nếu DBMS không công bố bảo đảm đó.

## 5. Bốn loại thứ tự rất dễ bị nhầm

### 5.1. Thứ tự vật lý (wall-clock order)

Timestamp có thể mô tả thời điểm tương đối trong một hệ quy chiếu thời gian như UTC. Với hai timestamp được cấp ở **hai máy khác nhau**, độ lệch đồng hồ có thể làm thứ tự so sánh không trùng thứ tự xảy ra thực tế.

### 5.2. Thứ tự tạo định danh (generation order)

Một tiến trình có thể cấp ID A rồi mới cấp ID B. Nếu thuật toán bảo đảm tăng đơn điệu cục bộ, `idA < idB` trong phạm vi ấy. Tuy vậy, bản ghi A có thể bị trì hoãn trong hàng đợi còn B commit trước. **Thứ tự tạo ID không phải thứ tự commit**.

### 5.3. Thứ tự nhân quả (causal order)

Nếu sự kiện A gửi yêu cầu khiến dịch vụ tạo sự kiện B, ta nói `A → B` (*happens-before*). Quan hệ nhân quả đó vẫn tồn tại ngay cả khi đồng hồ máy B chạy chậm và timestamp ghi trên B nhỏ hơn A.

Timestamp vật lý trong ID **không phải causal clock**. Lamport clock, vector clock và hybrid logical clock phục vụ những yêu cầu khác nhau về thứ tự và nhân quả.

### 5.4. Thứ tự commit hoặc thứ tự quan sát

Một DBMS có thể duy trì thứ tự log hoặc thao tác trong một partition, transaction hay nhóm đồng thuận. Nhưng thứ tự đó không nhất thiết là sequence toàn cụm. Bản sao đọc trễ cũng có thể chưa thấy một cập nhật đã commit ở nơi khác.

**Linearizability** yêu cầu các thao tác có thể được xem là xảy ra nguyên tử, đồng thời tôn trọng thứ tự thực của các thao tác không chồng lấn. Sinh UUIDv7 hoặc Snowflake **không tự tạo ra** tính tuyến tính hóa cho cơ sở dữ liệu.

### 5.5. Ví dụ khi đồng hồ làm đảo ngược thứ tự

~~~text
Thời gian thực:

t0       Máy A tạo sự kiện X, gửi thông điệp đến B
t0+10ms  Máy B nhận thông điệp, tạo sự kiện Y

Đồng hồ A chạy nhanh hơn thời gian thực 80 ms.
Đồng hồ B chạy chậm hơn thời gian thực 40 ms.

Timestamp của X ≈ t0+80ms
Timestamp của Y ≈ t0-30ms

X → Y về mặt nhân quả,
nhưng timestamp(X) > timestamp(Y).
~~~

Nếu sort ID theo timestamp vật lý, Y có thể xuất hiện “trước” X dù X là nguyên nhân của Y. Đó là lý do phải xác định người dùng cần **timeline theo đồng hồ**, **trình tự xử lý** hay **chuỗi nhân quả**.

| Cơ chế | Thứ tự gần đúng theo thời gian cấp | Tăng đơn điệu trong một bộ sinh | Đúng thứ tự commit toàn hệ thống | Mang quan hệ nhân quả |
|---|---|---|---|---|
| UUIDv4 | Không | Không | Không | Không |
| Timestamp + random | Có, nếu clock/format đúng | Không khi timestamp trùng | Không | Không |
| UUIDv7 | Có | Tùy cách sinh | Không | Không |
| Monotonic ULID | Có | Có trong phạm vi/điều kiện bộ sinh | Không | Không |
| Snowflake-style | Có | Có nếu thuật toán và đồng hồ được quản lý đúng | Không | Không |
| Sequence được phối hợp | Không nhất thiết | Tùy phạm vi sequence | Không tự động | Không |
| Log tuần tự theo partition | Theo vị trí log | Theo hợp đồng của log | Chỉ trong phạm vi được bảo đảm | Có thể bảo toàn một số thứ tự qua giao thức |

Một bộ so sánh luôn có thể xếp ID thành một dãy. **Có kết quả sắp xếp không có nghĩa dãy đó mô tả đúng thứ tự nghiệp vụ.**

## 6. Những vấn đề đồng hồ thường gặp

### 6.1. Clock skew: lệch đồng hồ giữa các nút

~~~text
Thời gian thực:   10:00:00.500
Máy A báo:        10:00:00.450  (chậm 50 ms)
Máy B báo:        10:00:00.580  (nhanh 80 ms)
~~~

Ngay cả khi A tạo sự kiện trước B, ID được tạo từ đồng hồ hai nút có thể đưa ra thứ tự ngược, tùy khoảng cách giữa hai sự kiện. Mức lệch lớn làm màn hình “mới nhất” và phân tích log khó tin cậy.

### 6.2. Clock rollback: đồng hồ đi lùi

Một worker vừa cấp ID ở mili giây 500, sau đó đồng hồ trả 490. Nếu dùng cơ chế `timestamp + workerId + sequence` và cấp lại một dải timestamp/sequence từng được dùng, nguy cơ **trùng ID** xuất hiện.

Những chiến lược có thể dùng, tùy bài toán:

- **Tạm dừng hoặc từ chối cấp ID** khi phát hiện thời gian lùi, đồng thời cảnh báo.
- **Chờ đồng hồ bắt kịp** nếu khoảng chờ nhỏ và mức độ sẵn sàng cho phép.
- **Dùng cơ chế thời gian logic/sequence được kiểm chứng** để không dùng lại tổ hợp ID đã cấp.
- **Dùng phần ngẫu nhiên đủ mạnh** để giảm xác suất va chạm, nếu yêu cầu thứ tự có thể nới lỏng.

Không có chính sách xử lý rollback nào miễn phí. Chờ có thể ảnh hưởng latency; ngừng cấp ID ảnh hưởng availability; thời gian logic có thể không phản ánh chính xác giờ thực; random không giữ thứ tự.

Một giải pháp tự viết chỉ đơn giản gán `now = lastTimestamp + 1` có thể làm ID “đi trước thời gian thực” và vẫn gặp vấn đề khi restart hoặc nhiều tiến trình cùng cấp ID.

### 6.3. NTP, điều chỉnh nhảy và đồng hồ đi nhanh

NTP và các cơ chế đồng bộ giúp giảm lệch đồng hồ nhưng có thể điều chỉnh tốc độ chạy hoặc nhảy tới giá trị khác tùy cấu hình. VM khôi phục từ snapshot, thay đổi giờ thủ công hoặc hạ tầng sai cấu hình cũng gây ra sai lệch.

Một máy cấp ID mang timestamp **tương lai quá xa** có thể khiến bản ghi của nó đứng ở đầu bảng tin “mới nhất” một thời gian dài. Đồng bộ thời gian là yêu cầu vận hành quan trọng, nhưng không thay thế thiết kế ID chịu được lỗi clock.

### 6.4. Độ phân giải mili giây và tải cao

Hàng nghìn sự kiện có thể cùng rơi vào một mili giây:

~~~text
08:15:27.123  Worker A tạo 12 ID
08:15:27.123  Worker B tạo 21 ID
08:15:27.123  Worker C tạo  8 ID
~~~

Timestamp một mình không phân biệt được 41 ID đó. Cần random, worker ID hoặc sequence. Nếu sequence có 12 bit, một worker có tối đa 4.096 giá trị cho cùng một mili giây theo bố cục ví dụ. Khi dùng hết, phải chờ mốc tiếp theo hoặc có chính sách xử lý quá tải; **không được âm thầm quay vòng sequence**.

### 6.5. Time zone, daylight saving và leap second

UTC là lựa chọn thuận tiện để lưu timestamp chung. Giờ địa phương `2026-11-14 08:15:27` không có offset hoặc múi giờ là mơ hồ giữa các khu vực. Daylight saving time (DST) có thể làm giờ địa phương lặp hoặc bỏ qua một khoảng; các hệ thống cũng có thể xử lý leap second khác nhau.

Nên lưu thời gian dạng UTC hoặc epoch cùng đơn vị rõ ràng, sau đó chuyển sang múi giờ người dùng khi hiển thị. **Dùng UTC không đồng nghĩa hai máy có đồng hồ hoàn toàn đồng bộ.**

### 6.6. Đồng hồ client, offline và import lịch sử

Một thiết bị offline có thể báo thời gian sai hoặc cố tình gửi timestamp trong quá khứ/tương lai. Dữ liệu import từ hệ cũ cũng có thể mang timestamp lúc import trong khóa, khác thời gian nghiệp vụ ban đầu.

Nếu cần tin thời gian do client cấp, hãy quy định chính sách chấp nhận, giới hạn độ lệch hoặc gắn cờ bất thường. Thường nên lưu cả `clientOccurredAt` và `serverReceivedAt` để đối chiếu, đồng thời không coi timestamp client là bằng chứng tuyệt đối về trình tự xử lý.

## 7. Khi cần thứ tự logic thay cho đồng hồ vật lý

### 7.1. Lamport clock

Lamport clock là một bộ đếm logic, tăng theo sự kiện và được cập nhật khi nhận thông điệp. Nếu `A → B` thì `L(A) < L(B)`, nhưng chiều ngược lại không đúng: `L(A) < L(B)` không chứng minh A gây ra B. Hai sự kiện không liên hệ vẫn có thể được xếp thứ tự theo quy tắc phá hòa.

Lamport clock thể hiện một phần quan hệ thứ tự, **không phải đồng hồ giờ thực**.

### 7.2. Vector clock

Vector clock lưu thông tin tiến triển của nhiều nguồn, có thể phát hiện phiên bản nào xảy ra sau theo quan hệ nhân quả và phiên bản nào đồng thời về mặt nhân quả.

~~~text
A = [2, 1]
B = [2, 3]   => A xảy ra trước B
C = [3, 1]   => B và C không so sánh được theo nhân quả
~~~

Vector clock có chi phí metadata, nhất là khi số nguồn phát lớn. Không cần đưa vector clock vào mọi định danh khi hệ thống chỉ cần ID duy nhất.

### 7.3. Hybrid logical clock (HLC)

HLC kết hợp thời gian vật lý và thành phần logic để duy trì một thứ tự hữu ích cho hệ phân tán khi các nút trao đổi sự kiện, đồng thời giữ giá trị thời gian gần đồng hồ thực.

HLC không phải bằng chứng rằng toàn bộ cụm biết thời gian chính xác tuyệt đối; bảo đảm của nó phụ thuộc thuật toán, giả định về clock và giao thức sử dụng HLC.

### 7.4. Sequence hoặc log theo phạm vi

Nếu mọi thay đổi trong **một tài khoản** phải được xử lý theo đúng thứ tự, có thể dùng sequence, transaction, log hoặc một đầu mối điều phối **theo tài khoản/partition**. Nếu yêu cầu một thứ tự duy nhất cho **toàn cụm**, cần cơ chế đồng thuận hoặc tuần tự hóa toàn cụm với chi phí mở rộng và độ trễ tương ứng.

Một ID có timestamp không thể tự thay thế log hoặc transaction mang hợp đồng thứ tự.

## 8. Định dạng khóa thời gian đúng cách

### 8.1. Timestamp cố định và chuẩn hóa UTC

Ví dụ một định dạng chuỗi phù hợp với sắp xếp từ điển theo thời gian:

~~~text
yyyyMMdd'T'HHmmssSSS'Z'

20261114T081527123Z
20261114T081527124Z
20261114T081528000Z
~~~

Các khóa phải có cùng số chữ số, đủ số 0 ở đầu, cùng UTC và cùng đơn vị mili giây. Có thể ghép:

~~~text
tenant-7#20261114T081527123Z#f5c19d
tenant-7#20261114T081527123Z#f68b02
tenant-7#20261114T081527124Z#83a011
~~~

Trong cùng tenant, thứ tự chuỗi phản ánh timestamp, còn phần suffix chỉ tạo thứ tự ổn định giữa các khóa có cùng thời gian. Nếu suffix được sinh ngẫu nhiên thì thứ tự giữa chúng **không mang ý nghĩa sớm/muộn**.

### 8.2. Những kiểu mã hóa dễ làm sai thứ tự

**Độ rộng thay đổi:** `event#10` có thể sắp trước `event#9` khi so sánh chuỗi. Nếu lưu số trong chuỗi và muốn sắp theo trị số, cần chuẩn hóa độ rộng hoặc dùng kiểu số và comparator phù hợp.

**Phân số giây không thống nhất:**

~~~text
2026-11-14T10:00:00Z
2026-11-14T10:00:00.100Z
~~~

Trong so sánh chuỗi, dấu chấm `.` nằm trước `Z` nên timestamp muộn hơn có thể sắp trước timestamp sớm hơn. ISO 8601 là chuẩn biểu diễn thời gian, nhưng **không phải mọi biến thể ISO 8601 đều sắp từ điển đúng khi trộn độ chính xác**.

**Trộn offset múi giờ:**

~~~text
2026-11-14T09:00:00+01:00
2026-11-14T08:30:00Z
~~~

Giá trị đầu tương đương 08:00 UTC và xảy ra trước giá trị sau, dù phần giờ tại địa phương lớn hơn. Vì vậy cần chuẩn hóa về một hệ quy chiếu trước khi so sánh.

**Trộn epoch seconds và milliseconds:** `epochSeconds` và `epochMillis` khác đơn vị 1.000 lần. Một số như `1763108127` và `1763108127000` không thể so sánh như hai timestamp cùng đơn vị.

**Comparator không tương thích:** chuỗi UUID chuẩn, byte UUID, số nguyên và khóa nhị phân có thể được DBMS so sánh khác nhau. Thứ tự “nhìn thấy bằng mắt” chưa chắc trùng thứ tự thực tế của index.

### 8.3. Reverse timestamp

Một số hệ thống muốn bản ghi mới nhất xuất hiện đầu tiên trong chiều quét tăng, nên tính:

~~~text
reverseTime = MAX_SUPPORTED_TIME - epochMillis
key = userId + "#" + fixedWidth(reverseTime) + "#" + uniqueSuffix
~~~

Cách này có thể đảo thứ tự thời gian nhưng cần định nghĩa rõ giới hạn số nguyên, độ rộng, khoảng thời gian hợp lệ và hành vi khi vượt giới hạn. Nếu DBMS đã hỗ trợ sort giảm dần hiệu quả, **không nhất thiết phải mã hóa đảo thời gian**.

## 9. Ví dụ Java 21 tạo khóa có tiền tố thời gian

Đoạn mã dưới đây tạo khóa theo tenant, UTC tới mili giây và UUIDv4. Việc truyền `Clock` từ bên ngoài giúp ứng dụng chủ động chọn nguồn thời gian khi triển khai hoặc mô phỏng:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
import java.util.UUID;

public final class TimeBasedKeyFactory {
    private static final DateTimeFormatter UTC_MILLIS =
            DateTimeFormatter
                    .ofPattern("uuuuMMdd'T'HHmmssSSS'Z'", Locale.ROOT)
                    .withZone(ZoneOffset.UTC);

    private TimeBasedKeyFactory() {
    }

    public static String create(String tenantId, Clock clock) {
        if (tenantId == null || !tenantId.matches("[A-Za-z0-9_-]+")) {
            throw new IllegalArgumentException("Invalid tenantId");
        }

        Instant generatedAt = clock.instant();
        String timePart = UTC_MILLIS.format(generatedAt);
        return tenantId + "#" + timePart + "#" + UUID.randomUUID();
    }
}
~~~

Cách gọi:

~~~java
String id = TimeBasedKeyFactory.create("tenant-7", Clock.systemUTC());
System.out.println(id);

// Ví dụ hình dạng đầu ra:
// tenant-7#20261114T081527123Z#550e8400-e29b-41d4-a716-446655440000
~~~

Phân tích tính chất:

- Phần thời gian có độ rộng cố định, dùng UTC và phù hợp sắp xếp chuỗi theo timestamp **trong cùng tenant**.
- Phần UUID ngẫu nhiên giúp giảm mạnh khả năng đụng độ.
- Hai khóa được tạo cùng mili giây **không có thứ tự cấp đáng tin cậy** vì suffix ngẫu nhiên.
- Đầu ra trên các máy khác nhau vẫn bị ảnh hưởng bởi clock skew.
- ID dạng chuỗi dài hơn một số kiểu số nguyên hoặc binary ID, gây chi phí lưu trữ/index cần cân nhắc.
- Kiểm tra ký tự tenant tránh phá cấu trúc ngăn bằng `#`, nhưng vẫn cần authorization để bảo đảm người dùng chỉ truy cập đúng tenant.

Đây là **ví dụ về cách tạo khóa chứa thời gian**, không phải bộ sinh khóa có thứ tự toàn cục.

### 9.1. Nếu cần sequence trong cùng mili giây

Một bộ sinh kiểu Snowflake có thể duy trì `lastTimestamp` và `sequence` trong trạng thái được bảo vệ đồng thời. Pseudocode:

~~~text
lock generator state
now = read wall clock

if now < lastTimestamp:
    apply an explicit clock-rollback policy
    (e.g. reject, wait, or use a verified logical-time approach)

if now == lastTimestamp:
    sequence = sequence + 1
else:
    lastTimestamp = now
    sequence = 0

if sequence exceeds its configured maximum:
    wait until the next permitted tick or reject the request

id = encode(lastTimestamp, workerId, sequence)
unlock generator state
return id
~~~

Pseudocode cố ý không ấn định một chính sách xử lý đồng hồ đi lùi. Triển khai thực tế còn cần xử lý cấp worker ID duy nhất, trạng thái khi restart, giới hạn thời gian, lỗi đồng thời và chi phí chờ khi hết sequence.

**Sequence cục bộ giúp định thứ tự trong phạm vi bộ sinh**; nó không tự bảo đảm thứ tự commit giữa nhiều shard.

## 10. Ảnh hưởng đến partitioning và sharding

### 10.1. Time prefix có thể gây hot shard

Giả sử tất cả bản ghi dùng khóa:

~~~text
20261114T081527123Z#...
20261114T081527124Z#...
20261114T081527125Z#...
~~~

Với **range partitioning**, gần như mọi ghi mới có thể đi đến shard chứa vùng khóa cuối cùng. Shard này trở thành điểm nóng khi tải tăng. Ngược lại, nếu DBMS băm toàn bộ khóa để chia tải, các sự kiện cùng ngày có thể nằm rải rác, khiến truy vấn theo khoảng trên toàn cụm khó hơn.

### 10.2. Đặt phạm vi truy vấn quan trọng vào partition key

Một cách thiết kế cho lịch sử học viên:

~~~text
Partition key = studentId
Sort key      = createdAt#eventId
~~~

Truy vấn 50 sự kiện mới nhất của một học viên có thể chạy trong một partition nếu DBMS hỗ trợ sort key và index phù hợp.

Nhưng một học viên có hàng triệu sự kiện hoặc một tenant có tải rất lớn vẫn có thể tạo partition quá lớn hay quá nóng.

### 10.3. Time bucket và hash bucket

Giới hạn dung lượng theo kỳ:

~~~text
Partition key = studentId#2026-11
Sort key      = 20261114T081527123Z#eventId
~~~

Chia thêm bucket để tăng khả năng phân tải:

~~~text
Partition key = tenantId#2026-11#bucket-03
Sort key      = 20261114T081527123Z#eventId
~~~

**Time bucket** theo ngày/tháng giúp quản lý khoảng lưu trữ, nhưng truy vấn qua nhiều kỳ phải ghép dữ liệu từ các partition. **Hash bucket** giúp phân tải, nhưng muốn lấy dòng thời gian toàn tenant có thể phải đọc nhiều bucket rồi merge theo thứ tự.

Kích thước bucket, số bucket, index phụ và chi phí truy vấn xuyên partition phải được chọn từ mẫu truy cập và số liệu thực tế. Không có bố cục nào tối ưu tất cả truy vấn đồng thời.

## 11. Sắp xếp, phân trang và dữ liệu đến trễ

### 11.1. Timestamp bằng nhau cần tie-breaker

~~~text
createdAt                 eventId
2026-11-14T08:15:27.123Z  A1
2026-11-14T08:15:27.123Z  B2
2026-11-14T08:15:27.123Z  C3
~~~

Nếu chỉ sort theo `createdAt`, ba sự kiện cùng timestamp có thể xuất hiện theo thứ tự không ổn định. Thường cần sort theo cặp **`(createdAt, eventId)`** với `eventId` duy nhất và comparator xác định.

Cặp khóa này bảo đảm thứ tự **hiển thị**, không chứng minh thứ tự xảy ra trong cùng mili giây.

### 11.2. Keyset pagination

Giả sử sắp giảm theo `createdAt DESC, eventId DESC`. Sau trang đầu, lưu cursor của bản ghi cuối:

~~~json
{
  "createdAt": "2026-11-14T08:15:27.123Z",
  "eventId": "B2"
}
~~~

Trang tiếp theo tìm các bản ghi mà cặp khóa nhỏ hơn cursor theo cùng bộ lọc:

~~~text
(createdAt < cursor.createdAt)
OR
(createdAt == cursor.createdAt AND eventId < cursor.eventId)
~~~

Đây là điều kiện logic, cú pháp triển khai tùy DBMS. Cần dùng index phục vụ thứ tự này.

Một sự kiện **đến trễ** với timestamp nằm phía trước hoặc phía sau cursor có thể làm tập kết quả thay đổi giữa các trang. Nếu sản phẩm cần một danh sách ổn định như ảnh chụp, có thể cần snapshot consistency, watermark hoặc quy tắc đồng bộ riêng.

### 11.3. Event time và ingestion time cho thứ tự khác nhau

~~~text
Sự kiện X xảy ra 08:00, bị chậm mạng, nhận lúc 08:10.
Sự kiện Y xảy ra 08:05, nhận lúc 08:06.
~~~

Sắp theo `occurredAt`: X rồi Y. Sắp theo `ingestedAt`: Y rồi X.

Cần chọn đúng ngữ nghĩa:

- Timeline hành vi người dùng thường ưu tiên event time, có thể chấp nhận hiển thị lại khi sự kiện đến muộn.
- Nhật ký xử lý tiếp nhận thường quan tâm ingestion order hoặc vị trí trong log.
- Đơn hàng, thanh toán và tác vụ có tác động nghiệp vụ quan trọng cần ràng buộc transaction/sequence theo phạm vi xử lý, không thể dựa riêng vào timestamp trong ID.

### 11.4. Tách ID bất biến khỏi timestamp có thể được sửa

Nếu timestamp trong primary key bị phát hiện sai, việc sửa timestamp có thể đồng nghĩa **đổi khóa**. Thao tác này thường phức tạp, có thể phải tạo bản ghi mới, xóa bản cũ và cập nhật mọi tham chiếu.

Khi sự kiện có thể được hiệu chỉnh thời điểm, nên cân nhắc dùng **ID bất biến** với trường `occurredAt` có thể cập nhật, cùng audit trail để truy nguyên.

## 12. Timestamp trong ID không giải quyết idempotency hoặc bảo mật

### 12.1. Retry có thể tạo thao tác nghiệp vụ trùng

Giả sử client gửi yêu cầu đặt hàng, server tạo `orderId` có timestamp. Client timeout rồi gửi lại; nếu lần hai sinh ID mới, hai ID đều duy nhất nhưng **có thể cùng đại diện một đơn hàng**.

Cần dùng **idempotency key** ổn định cho cùng một yêu cầu nghiệp vụ, cùng unique constraint hoặc giao thức chống xử lý trùng phù hợp. Timestamp + random không tự nhận diện hai lần gửi cùng một hành động.

### 12.2. ID có thứ tự dễ đoán hơn định danh bí mật

Một số ID chứa timestamp hoặc sequence nên người khác có thể dự đoán dải giá trị hoặc suy ra thông tin hoạt động của hệ thống. Vì thế, **không dùng khả năng khó đoán của ID để thay thế authorization**.

API phải luôn kiểm tra người gọi có quyền truy cập bản ghi. Token bí mật, nếu cần, nên có mô hình tạo và lưu riêng phù hợp với yêu cầu bảo mật.

## 13. Liên quan đến TTL và retention

TTL (time-to-live) và retention là chính sách hết hạn dữ liệu, khác mục tiêu “ID có chứa timestamp”.

Ví dụ:

~~~json
{
  "sessionId": "20261114T080000000Z-a18d6f",
  "createdAt": "2026-11-14T08:00:00Z",
  "expiresAt": "2026-11-14T08:30:00Z"
}
~~~

Không nên mặc định DBMS xóa session lúc 08:30 chỉ vì ID chứa thời gian. Phải cấu hình TTL hoặc quy trình dọn dữ liệu theo cơ chế DBMS, có thể dựa vào trường thời gian, timestamp ghi hoặc thuộc tính riêng.

Cần biết rằng:

- Xóa hết hạn không nhất thiết xảy ra ngay lập tức ở mọi DBMS.
- Clock skew có thể ảnh hưởng đến đánh giá hết hạn trong hệ phân tán.
- Sự kiện đến trễ có `occurredAt` cũ nhưng `ingestedAt` mới, nên retention tính từ lúc xảy ra khác retention tính từ lúc nhận.
- Yêu cầu lưu trữ và xóa dữ liệu theo pháp lý/nghiệp vụ phải độc lập với hình thức khóa.

## 14. Bảng tình huống lỗi và cách tiếp cận

| Tình huống | Hậu quả | Điều cần thiết kế |
|---|---|---|
| Nhiều ID trong cùng mili giây | Timestamp trùng | Random/sequence, kiểm soát collision |
| Hai worker dùng chung mã worker | Có thể sinh cùng timestamp + sequence | Cấp worker ID duy nhất, lease/fencing khi phù hợp |
| Đồng hồ đi lùi | Có thể sinh lại ID hoặc đảo thứ tự | Phát hiện rollback và chính sách minh bạch |
| Worker khởi động lại hoặc restore VM | Trạng thái bộ sinh có thể lặp | Cơ chế cấp nguồn và phục hồi trạng thái đúng |
| Client gửi thời gian tương lai | Timeline sai | Lưu thời gian server, giới hạn/đánh dấu lệch |
| Hết sequence một mili giây | Nguy cơ quay vòng và trùng | Chờ tick tiếp theo hoặc báo quá tải |
| Nhiều bản ghi cùng timestamp | Phân trang/hiển thị không ổn định | Tie-breaker duy nhất |
| Dữ liệu đến trễ | Bản ghi xuất hiện ngoài vị trí mong đợi | Xác định event time, ingestion time, watermark |
| Time prefix và range sharding | Hot shard ở dải khóa mới nhất | Partition theo thực thể, time/hash bucket |
| Timestamp được sửa sau ghi | Khó đổi primary key và tham chiếu | Tách ID bất biến với trường thời gian |
| Sử dụng ID thời gian làm chứng cứ thứ tự giao dịch | Kết luận nghiệp vụ sai | Sequence/log/transaction theo phạm vi bảo đảm |

## 15. Quy trình chọn khóa theo yêu cầu

Đặt câu hỏi theo thứ tự trước khi chọn thuật toán ID.

| Yêu cầu nghiệp vụ | Thiết kế thường cân nhắc | Điều không được tự suy ra |
|---|---|---|
| Chỉ cần ID phân tán duy nhất | UUIDv4 hoặc ID phù hợp | Có thứ tự theo thời gian |
| Muốn ID gần theo lúc cấp | UUIDv7, ULID, Snowflake-style, timestamp prefix | Thứ tự thực tế toàn cụm |
| Muốn lịch sử theo người dùng | Partition theo user và sort key thời gian + tie-breaker | Tối ưu truy vấn mọi user cùng lúc |
| Muốn chống retry tạo bản ghi trùng | Idempotency key/unique constraint | Timestamp + random tự chống trùng nghiệp vụ |
| Muốn xử lý theo thứ tự một tài khoản | Log, sequence, transaction trong phạm vi tài khoản | ID tăng tự tạo serialization |
| Muốn phát hiện xung đột phân tán | Version hoặc causal metadata phù hợp | Timestamp đủ xử lý mọi conflict |
| Muốn tự hết hạn dữ liệu | Trường expiresAt và TTL/retention cấu hình | ID có thời gian tự xóa dữ liệu |

Một cách triển khai có trách nhiệm là:

1. **Định nghĩa chính xác thứ tự cần thiết:** theo thời gian cấp, thời gian sự kiện, thứ tự commit hay quan hệ nhân quả.
2. **Xác định phạm vi bảo đảm:** một process, một worker, một partition, một tài khoản hay toàn cụm.
3. **Chọn ID và partition key từ truy vấn chính**, xem tải ghi có gây hot partition không.
4. **Chọn timestamp và tie-breaker có định dạng rõ ràng**, chuẩn hóa UTC và đơn vị.
5. **Quy định cách xử lý clock skew, rollback, retry, overflow và restart**.
6. **Đo mức độ phù hợp với hệ quản trị cụ thể:** kiểu comparator, index, điều kiện phân trang, transaction và read consistency.
7. **Lưu các mốc nghiệp vụ riêng** khi sự khác nhau giữa `occurredAt` và `ingestedAt` có ý nghĩa.

## 16. Bài tập thực hành: nhật ký thiết bị IoT

Một nền tảng có 20.000 cảm biến. Một thiết bị có thể offline nhiều giờ, ghi lại mẫu đo và gửi bù sau khi kết nối lại. Hệ ingestion chạy trên nhiều máy, dữ liệu lưu vào NoSQL.

~~~json
{
  "deviceId": "sensor-101",
  "sampleId": "boot-9#seq-1052",
  "measuredAt": "2026-11-14T08:10:00Z",
  "receivedAt": "2026-11-14T09:02:16.321Z",
  "temperatureC": 29.1
}
~~~

Yêu cầu:

1. Hiển thị 100 lần đo gần nhất **theo thời gian đo** cho từng thiết bị.
2. Truy vấn mẫu đo trong một khoảng ngày.
3. Không ghi hai lần khi thiết bị retry.
4. Chịu được thiết bị sai giờ vài phút.
5. Không tạo partition quá lớn khi một thiết bị có hàng triệu mẫu.

### Gợi ý phân tích

- **Partition key:** `deviceId#timeBucket` có thể hỗ trợ truy vấn theo thiết bị/kỳ và kiểm soát kích thước; cần đánh giá nếu có thiết bị phát tải quá cao.
- **Sort key:** `measuredAt#sampleId` cho lịch sử theo thời gian đo, nhưng phải chấp nhận đo sai giờ và các mẫu đến trễ. Có thể cần index hoặc cấu trúc riêng để truy vấn theo thời gian tiếp nhận.
- **Idempotency:** dùng `sampleId` ổn định qua retry kết hợp `deviceId`, thiết kế cả trường hợp sequence reset sau reboot. Số đếm mỗi lần gửi mới không đủ.
- **Đối chiếu đồng hồ:** lưu cả `measuredAt` và `receivedAt`, gắn cờ lệch bất thường theo chính sách nghiệp vụ.
- **Dữ liệu cần chỉnh giờ:** cân nhắc ID bất biến độc lập với `measuredAt` để tránh đổi primary key.
- **Phân trang:** thêm tie-breaker duy nhất để tránh lặp/bỏ sót giữa các mẫu có timestamp trùng; nếu cần ảnh chụp ổn định thì xét consistency của dữ liệu đang thay đổi.

Bài toán này cho thấy timestamp là một thông tin hữu ích, nhưng lựa chọn **ngữ nghĩa thời gian, phạm vi duy nhất và chiến lược truy vấn** mới quyết định chất lượng thiết kế.

## 17. Các ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| “Có timestamp trong khóa là có thứ tự thực tế chính xác.” | Đồng hồ nhiều nút có thể lệch; ID chỉ chứa timestamp do nguồn cấp ghi lại. |
| “UUIDv7/ULID luôn tăng trên toàn bộ cụm.” | Monotonicity phụ thuộc bộ sinh và đồng hồ, thường có phạm vi cục bộ. |
| “Một mili giây chỉ có một sự kiện.” | Hàng nghìn sự kiện có thể chung timestamp; cần phần phân biệt. |
| “Snowflake không bao giờ trùng.” | Worker ID trùng, rollback, restart hoặc sequence sai có thể làm va chạm. |
| “Thứ tự cấp ID là thứ tự commit.” | Queue, transaction, mạng và replica có thể làm thứ tự khác nhau. |
| “UTC nghĩa là đồng hồ đã đồng bộ.” | UTC là hệ quy chiếu; đồng hồ mỗi máy vẫn có sai lệch. |
| “ISO 8601 luôn sắp chuỗi đúng.” | Phải thống nhất timezone, độ rộng, phân số giây và comparator. |
| “Time prefix tự làm sharding đều tải.” | Range sharding có thể nóng ở dải khóa mới; hash sharding ảnh hưởng range scan. |
| “ID chứa ngày hết hạn giúp bản ghi tự bị xóa.” | TTL phải được cấu hình riêng theo khả năng DBMS. |
| “ID mới trên mỗi retry bảo đảm không tạo trùng.” | ID khác nhau vẫn có thể đại diện cùng một hành động nghiệp vụ. |

## 18. Kết luận

Thời gian trong khóa NoSQL hữu ích cho định danh có tính cục bộ theo thời gian, truy vấn khoảng, hiển thị lịch sử và phân tích log. Tuy nhiên, ba ranh giới cần nhớ là:

1. **Tính duy nhất khác với thứ tự:** timestamp cần random, sequence hoặc cơ chế cấp ID phù hợp; suffix phân biệt không nhất thiết mô tả trước–sau.
2. **Thứ tự ID khác thứ tự thực tế:** clock skew, rollback, độ phân giải timestamp, hàng đợi, commit và replica đều có thể làm hai thứ tự khác nhau.
3. **Phải thiết kế khóa theo phạm vi truy vấn và tính nhất quán cần thiết:** xác định partition key, sort key, time bucket, tie-breaker và các loại thời gian nghiệp vụ trước khi chọn UUIDv7, ULID hay Snowflake.

Nếu chỉ cần thứ tự tạo **gần đúng**, ID có timestamp là lựa chọn thực dụng. Nếu nghiệp vụ bắt buộc thứ tự **nhân quả hoặc xử lý nghiêm ngặt**, cần sequence, transaction, log hoặc giao thức đồng thuận mang bảo đảm cụ thể trong đúng phạm vi hệ thống.
