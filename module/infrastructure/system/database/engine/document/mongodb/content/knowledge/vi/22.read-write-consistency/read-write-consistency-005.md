# Độ trễ sao chép và nguy cơ đọc dữ liệu cũ trong MongoDB

## 1. Tình huống mở đầu: vừa lưu thành công nhưng màn hình vẫn hiển thị dữ liệu cũ

Một ứng dụng quản lý đơn hàng dùng **MongoDB replica set** với một primary và hai secondary. Người dùng đổi địa chỉ giao hàng từ “Hà Nội” thành “Đà Nẵng”. API cập nhật thông báo **200 OK**, nhưng ngay khi tải lại trang, địa chỉ vẫn là “Hà Nội”. Vài giây sau, tải lại lần nữa mới thấy “Đà Nẵng”.

Một chuỗi sự kiện có thể xảy ra:

```text
Thời gian      API ghi                    Replica set              API đọc
   |
   |     PATCH /orders/123
   |          |                       PRIMARY: address = "Đà Nẵng"
   |          +----------------------> Ghi thành công
   |          |                                |
   |       200 OK                              | replication bất đồng bộ
   |                                           v
   |                                        SECONDARY A
   |                                        vẫn là "Hà Nội"
   |                                            |
   |      GET /orders/123 ---------------------+
   |                                            |
   |      Trả "Hà Nội" <------------------------+
   |
   |                                     SECONDARY A áp dụng oplog
   |                                     address = "Đà Nẵng"
   v
          GET lần tiếp theo thấy "Đà Nẵng"
```

Đây là một ví dụ của **stale read** — đọc dữ liệu **cũ hơn trạng thái mà ứng dụng hoặc người dùng kỳ vọng**. Không nhất thiết có lỗi ghi hoặc mất dữ liệu. Nguyên nhân có thể là yêu cầu đọc được định tuyến tới một secondary chưa áp dụng thao tác mới nhất.

Chủ đề **“Độ trễ sao chép và nguy cơ đọc dữ liệu cũ”** thuộc chương **Nhất quán đọc ghi** của MongoDB. Sau bài học, bạn sẽ:

- Hiểu quá trình replication bất đồng bộ và phân biệt độ trễ sao chép với độ trễ API.
- Giải thích vì sao một write thành công không đồng nghĩa mọi replica có ngay giá trị mới.
- Phân biệt **read preference**, **read concern** và **write concern**.
- Hiểu các mức cam kết của `w: 1`, `w: "majority"`, `readConcern: "local"` và `readConcern: "majority"`.
- Chọn cách đảm bảo *read-your-writes* bằng primary hoặc **causally consistent session** khi phù hợp.
- Hiểu giới hạn của `maxStalenessSeconds` và lý do nó không phải bảo đảm dữ liệu mới nhất.
- Phân tích những trường hợp failover, rollback, nhiều request đồng thời và dữ liệu đang thay đổi liên tục.
- Quan sát replication lag bằng `mongosh`, đọc metric và thiết kế cách xử lý an toàn.

## 2. Replica set sao chép như thế nào?

### 2.1. Primary và các secondary

Trong một replica set, **primary** là thành viên tiếp nhận những thao tác ghi thông thường của client. Các **secondary** sao chép và áp dụng thay đổi từ luồng **oplog** trên một sync source phù hợp; sync source có thể là primary hoặc một secondary khác trong cấu hình cho phép.

```text
                    Application
                       |
                insert / update
                       |
                       v
                    PRIMARY
                   +-------+
                   | Data  |
                   | Oplog |
                   +-------+
                    /    \
          replication    replication
             /              \
            v                v
       SECONDARY A       SECONDARY B
       +--------+        +--------+
       | Data   |        | Data   |
       | Oplog  |        | Oplog  |
       +--------+        +--------+
```

Các thao tác ghi có thể hoàn tất ở primary trước khi một hoặc nhiều secondary áp dụng xong. Replica set không duy trì trạng thái “mọi node luôn giống nhau tại từng mili giây”.

### 2.2. Oplog là cơ sở của việc bắt kịp

MongoDB duy trì một **operations log** trong collection nội bộ `local.oplog.rs` trên các thành viên lưu dữ liệu. Oplog chứa những thay đổi được dùng để sao chép; nó không phải bảng audit vĩnh viễn.

Một secondary theo dõi vị trí đã áp dụng, lấy các mục còn thiếu rồi cập nhật dữ liệu cục bộ. Nếu luồng thay đổi mới đến nhanh hơn khả năng nhận và áp dụng, secondary sẽ **tụt lại**.

Điều đáng chú ý:

- Secondary có thể **đã nhận** mục oplog nhưng **chưa áp dụng** xong.
- Secondary có thể áp dụng xong nhưng chưa đạt trạng thái **durable** theo tiêu chí giám sát đang xét.
- MongoDB có các thông tin về tiến độ **applied**, **durable** và **majority commit point**; không nên đánh đồng chúng.
- Dữ liệu được đọc tại một node phụ thuộc tiến độ mà node đó đã đạt và các tùy chọn nhất quán của lệnh đọc.

### 2.3. Độ trễ sao chép (*replication lag*)

Một cách theo dõi lag phổ biến là so chênh lệch thời điểm thao tác cuối được áp dụng giữa primary và một secondary:

\[
\text{Lag}_{i}\approx
T_{\text{optime(primary)}}-T_{\text{optime(secondary }i\text{)}}
\]

Ví dụ tại một lần quan sát:

```text
Primary:       last applied = 10:00:10 UTC
Secondary A:   last applied = 10:00:09 UTC
Secondary B:   last applied = 09:58:10 UTC

Lag A ≈   1 giây
Lag B ≈ 120 giây
```

Đó là **chênh lệch tiến độ**, không phải “mỗi truy vấn trên B luôn chậm 120 giây” và không phải thời gian thực thi một câu lệnh. Lag có thể tăng, giảm hoặc đột ngột thay đổi khi node gặp tải, thay sync source hoặc xảy ra election.

### 2.4. Oplog window khác replication lag

**Oplog window** là khoảng lịch sử còn giữ giữa mục oplog cũ nhất và mới nhất trên một thành viên. **Lag** là khoảng secondary đang tụt so với tiến độ tham chiếu.

```text
Sync source giữ lịch sử:
oldest 06:00 -------------------------------- newest 18:00
                  window ~12 giờ

Secondary A applied tới 17:58 -> lag ~2 phút
Secondary B applied tới 10:00 -> lag ~8 giờ
```

Secondary B còn có thể bắt kịp nếu các mục nó cần vẫn có trên sync source, khả năng xử lý đủ và topology cho phép. Nếu tốc độ ghi làm window co xuống còn 5 giờ trong khi B đang tụt 8 giờ, có nguy cơ **oplog không còn những thay đổi cần thiết**. Khi đó secondary có thể trở nên *too stale* và cần quy trình đồng bộ lại.

Nội dung trọng tâm của bài là **tác động của lag đến kết quả đọc và mức nhất quán**, không chỉ bài toán sizing oplog.

## 3. “Dữ liệu cũ” có thể có nhiều ý nghĩa

### 3.1. Cũ so với ghi gần nhất của chính người dùng

Người dùng vừa thay đổi tên rồi đọc lại tên cũ:

```text
write(name = "An")  -> thành công
read(name)          -> "Anh"  (giá trị trước đó)
```

Trường hợp này vi phạm kỳ vọng **read-your-writes**: một client muốn nhìn thấy các ghi mà chính nó đã xác nhận trong những lần đọc tiếp theo.

### 3.2. Cũ so với người dùng khác vừa ghi

Người A sửa trạng thái hàng tồn kho; người B đang dùng một dashboard đọc từ secondary và chưa thấy thay đổi. Có thể không có kỳ vọng đọc ngay lập tức trong dashboard đó, nhưng lại không chấp nhận được nếu B đang ra quyết định cấp phát hàng theo số tồn cũ.

**Mức độ chấp nhận stale read là yêu cầu nghiệp vụ**, không phải chỉ số kỹ thuật chung cho mọi API.

### 3.3. Dữ liệu đi lùi giữa hai lần đọc

Giả sử ứng dụng dùng read preference `nearest` hoặc `secondary` và driver có thể chọn các secondary khác nhau:

```text
Lần 1 -> Secondary A đã tới version 12 -> trả version 12
Lần 2 -> Secondary B mới tới version 10 -> trả version 10
```

Ngay cả khi không có ghi mới giữa hai lần đọc, cùng người dùng có thể quan sát dữ liệu **lùi từ mới về cũ**. Điều này liên quan đến bảo đảm **monotonic reads**: các lần đọc trong một luồng có ngữ cảnh không được lùi về trạng thái trước lần đọc đã quan sát.

### 3.4. Cũ do cache không phải do replica set

Một giá trị cũ cũng có thể đến từ:

- Redis hoặc application cache chưa được vô hiệu hóa.
- CDN hoặc HTTP cache còn giữ response cũ.
- Client mobile hiển thị bản sao local/offline.
- Queue/event processor chưa xử lý sự kiện.
- MongoDB query đọc đúng database nhưng nhầm tenant, filter hoặc phiên bản document.
- Query phân trang/sort không ổn định làm kết quả có vẻ chưa cập nhật.

Không được kết luận “replication lag” chỉ từ một ảnh chụp màn hình cũ. Phải xác định **node đọc**, read preference, read concern, nguồn cache và thời điểm dữ liệu được ghi.

## 4. Read preference: ứng dụng đọc từ node nào?

### 4.1. Năm chế độ phổ biến

**Read preference** là chính sách chọn thành viên để thực hiện lệnh đọc. Nó **không tự quyết định mức commit** của dữ liệu được trả về.

| Read preference | Nguồn đọc thường được chọn | Nguy cơ đọc cũ |
| --- | --- | --- |
| `primary` | Primary hiện tại | Thường ít nguy cơ cũ do secondary lag; vẫn cần xét read concern, election và rollback |
| `primaryPreferred` | Ưu tiên primary; có thể dùng secondary khi primary không khả dụng | Khi fallback, có thể thấy dữ liệu cũ |
| `secondary` | Các secondary đủ điều kiện | Có, tùy tiến độ node được chọn |
| `secondaryPreferred` | Ưu tiên secondary; có thể dùng primary khi không có secondary phù hợp | Có, khi đọc từ secondary |
| `nearest` | Thành viên phù hợp về latency mạng, có thể gồm primary hoặc secondary | Có, vì mạng nhanh không đồng nghĩa dữ liệu mới |

Trong MongoDB driver, `primary` là read preference mặc định phổ biến. Tuy nhiên, một ứng dụng có thể đặt cấu hình ở URI, `MongoClient`, database, collection hoặc lệnh đọc cụ thể. Đừng suy luận node đọc chỉ từ một dòng code `findOne()`.

### 4.2. Vì sao “nearest” không có nghĩa “latest”?

Giả sử primary ở region A, secondary B gần ứng dụng hơn:

```text
Ứng dụng
   |
   +-- 5 ms --> Secondary B (lag 3 giây)
   |
   +-- 50 ms -> Primary (dữ liệu cập nhật mới)
```

Read preference `nearest` tối ưu lựa chọn theo độ trễ mạng trong các điều kiện driver, **không phải chọn node có dữ liệu mới nhất**. Thời gian đi về ít hơn có thể đổi lấy mức độ mới của dữ liệu kém hơn.

### 4.3. Tag sets và lựa chọn secondary

Trong replica set, quản trị viên có thể gắn **tags** cho member để phục vụ lựa chọn vị trí hoặc mục đích đọc. Ứng dụng có thể yêu cầu ưu tiên secondary ở một khu vực hay vai trò phù hợp.

Tuy nhiên:

- Tag không biến node thành bản sao đồng bộ tức thì.
- Secondary được chọn vẫn có lag thực tế.
- Một node “analytics” hoặc deliberately delayed không nhất thiết phù hợp cho API vừa ghi vừa đọc ngay.
- Nếu cấu hình tags quá chặt, thao tác có thể không tìm được node phù hợp.

Chọn vị trí đọc phải đi kèm yêu cầu **freshness** và **availability**, không chỉ locality.

### 4.4. `maxStalenessSeconds` có giải quyết stale read không?

MongoDB driver hỗ trợ tùy chọn `maxStalenessSeconds` trong những điều kiện phù hợp để **loại bớt các secondary được ước tính là quá cũ** so với ngưỡng chỉ định.

Ví dụ URI minh họa:

```text
mongodb://db1.example:27017,db2.example:27017,db3.example:27017/
?replicaSet=rs0&readPreference=secondary&maxStalenessSeconds=120
```

Trên thực tế URI phải được viết trên **một dòng**, kèm TLS/authentication đúng môi trường.

Những điểm cần nhớ:

1. `maxStalenessSeconds` dùng thông tin server/heartbeat để **ước tính độ cũ** cho mục đích server selection.
2. Đây **không phải hard guarantee** rằng mỗi document trả về mới tối đa đúng 120 giây.
3. Ngưỡng tối thiểu hợp lệ phổ biến là **90 giây**, đồng thời phải đáp ứng giới hạn liên quan heartbeat/server selection của driver.
4. Nếu không có secondary đáp ứng điều kiện, lựa chọn `secondary` có thể thất bại vì không tìm được server, thay vì âm thầm đọc từ primary.
5. Cấu hình không tương thích với read preference `primary` vì chính sách này không chọn secondary.
6. Nó không giải quyết stale reads từ cache, trình duyệt hoặc nguồn khác bên ngoài MongoDB.

Nếu nghiệp vụ đòi **phải thấy ngay ghi vừa được xác nhận**, chỉ đặt `maxStalenessSeconds: 90` không đủ.

## 5. Read concern: trạng thái dữ liệu nào được phép quan sát?

**Read concern** xác định ngữ nghĩa nhất quán/độ bền của dữ liệu mà một lệnh đọc có thể quan sát. Nó không chọn node; đó là vai trò của read preference.

### 5.1. `readConcern: "local"`

`local` là mức đọc thông thường và phổ biến. Nó cho phép đọc dữ liệu hiện có trên thành viên xử lý yêu cầu mà không bắt buộc dữ liệu đó đã được majority commit.

Nếu lệnh đọc đi đến secondary A, `local` trả kết quả dựa trên trạng thái A đã áp dụng. Nếu A đang lag, dữ liệu có thể cũ.

Nếu lệnh đọc đi đến primary, `local` có thể thấy dữ liệu mới vừa ghi trên primary, nhưng dữ liệu chưa majority commit có thể chịu rollback sau failover trong những tình huống phù hợp.

### 5.2. `readConcern: "majority"`

`majority` hướng tới dữ liệu đã được **majority commit** theo semantics MongoDB. Nó giúp tránh quan sát một số thay đổi chưa majority commit có nguy cơ rollback, trong các điều kiện triển khai hỗ trợ.

Tuy nhiên, **majority không đồng nghĩa latest**:

```text
Primary:     đã áp dụng tới order version 15
Secondary A: đã áp dụng tới order version 13

Read từ A với readConcern majority:
    có thể đọc một trạng thái majority-committed
    mà A đã có, nhưng không nhất thiết là version 15.
```

Điều này thường bị hiểu sai: `readConcern: "majority"` **không bắt mọi secondary phải chờ áp dụng tất cả ghi mới nhất trên primary** cho mọi lệnh đọc.

### 5.3. `readConcern: "linearizable"`

MongoDB hỗ trợ mức đọc `linearizable` với các điều kiện và giới hạn phù hợp, **chỉ áp dụng khi đọc từ primary**. Kết hợp với ghi majority theo yêu cầu, nó hỗ trợ semantics gần với một thứ tự thời gian thực: một thao tác đọc bắt đầu sau khi một ghi đã hoàn tất theo điều kiện bảo đảm sẽ không trả trạng thái trước ghi đó cho một document được đọc phù hợp.

Đặc điểm:

- Dành cho những trường hợp cần bảo đảm mạnh, thường ở phạm vi **một document**.
- Có chi phí và ảnh hưởng availability/latency lớn hơn.
- Không dùng để bảo đảm rằng đọc từ một secondary sẽ luôn là mới nhất.
- Nên đặt `maxTimeMS` phù hợp để tránh chờ quá lâu khi môi trường không thể đáp ứng điều kiện.

Không chọn `linearizable` cho toàn bộ truy vấn phân tích lớn chỉ vì tên nghe “mạnh hơn”; phải hiểu yêu cầu và các giới hạn cụ thể.

### 5.4. `readConcern: "snapshot"`

`snapshot` cung cấp cách đọc một **snapshot nhất quán** trong các bối cảnh MongoDB hỗ trợ, đặc biệt là transaction và một số cách đọc ngoài transaction ở các phiên bản nhất định.

Snapshot nhất quán hữu ích khi cần các phép đọc thấy một trạng thái cơ sở thống nhất, nhưng nó **không mặc định có nghĩa snapshot mới nhất tại thời điểm client nhận response**.

Một báo cáo tổng hợp có thể cần snapshot để tránh các phần của kết quả thuộc những mốc thời gian không tương thích, trong khi API “vừa lưu xong phải nhìn thấy ngay” cần một chiến lược khác hoặc phối hợp thêm causal semantics.

### 5.5. `readConcern: "available"`

`available` là một mức read concern có các khác biệt nhất định trong bối cảnh sharded cluster, thiên về tính sẵn sàng đọc hơn bảo đảm dữ liệu majority-committed. Nó không phải lựa chọn mặc định để bảo vệ màn hình cần dữ liệu mới hoặc ngăn đọc các thay đổi có khả năng rollback.

### 5.6. Bảng tổng quan

| Read concern | Mục tiêu chính | Có tự bảo đảm secondary trả dữ liệu mới nhất? |
| --- | --- | --- |
| `local` | Đọc dữ liệu có trên node | Không |
| `majority` | Đọc dữ liệu majority-committed | Không |
| `linearizable` | Semantics mạnh về thứ tự thời gian thực trong phạm vi và điều kiện hỗ trợ | Không áp dụng cho đọc secondary |
| `snapshot` | Quan sát snapshot nhất quán trong bối cảnh hỗ trợ | Không đồng nghĩa latest |
| `available` | Mức đọc chú trọng availability trong một số bối cảnh | Không |

**Read preference chọn nơi đọc; read concern quy định điều kiện đọc.** Chọn một trong hai mà bỏ qua cái còn lại là nguồn gây nhiều giả định sai.

## 6. Write concern: lúc nào lệnh ghi được coi là đã xác nhận?

### 6.1. `w: 1`

Một thao tác:

```javascript
db.orders.updateOne(
  { orderId: "O-238" },
  { $set: { status: "PAID" } },
  { writeConcern: { w: 1 } }
);
```

`w: 1` thường yêu cầu primary xác nhận mức ghi tương ứng. Nó **không đợi tất cả secondary áp dụng xong**; thậm chí không yêu cầu thao tác đã majority commit.

Sau ghi, đọc từ secondary có thể thấy status cũ. Nếu xảy ra failover trước khi thay đổi được majority commit, ghi đã được xác nhận bằng mức yếu hơn có thể bị rollback trong những trường hợp phù hợp.

### 6.2. `w: "majority"`

```javascript
db.orders.updateOne(
  { orderId: "O-238" },
  { $set: { status: "PAID" } },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 10000
    }
  }
);
```

`w: "majority"` yêu cầu mức xác nhận theo **đa số thành viên voting data-bearing** đủ điều kiện trong replica set. Điều này thường giúp tăng bảo đảm rằng thao tác không dễ mất trong quá trình thay đổi primary.

Nhưng:

- **Không bắt tất cả secondary đã áp dụng xong**.
- Một secondary đang lag vẫn có thể trả status cũ.
- Majority write concern không thay thế read preference/read concern của lần đọc tiếp theo.
- Nếu timeout chờ majority, thao tác **có thể đã được áp dụng**; client không được suy ra “chưa có gì xảy ra”.

### 6.3. Journal và các giới hạn khác

Write concern có các yếu tố liên quan đến việc ghi bền vững vào journal/storage. Trường `j`, mặc định của hệ thống và tùy chọn `writeConcernMajorityJournalDefault` có thể ảnh hưởng chi tiết việc xác nhận majority đã bền vững đến mức nào trong cấu hình cụ thể.

Không tự diễn giải “`majority`” là mọi dữ liệu đã được lưu bền vững trên mọi disk của mọi node trong mọi topology. Với nghiệp vụ cần RPO/RTO chặt, kiểm tra tài liệu và cấu hình của phiên bản triển khai.

### 6.4. Minh họa ba node

```text
Ghi X tới Primary
     |
     +---- Primary áp dụng X
     |
     +---- Secondary A áp dụng X
     |
     +---- Secondary B vẫn chưa áp dụng X

Một majority của 3 voting data-bearing members = 2

Ghi có thể đã đạt điều kiện w:"majority"
nhưng đọc từ Secondary B vẫn thấy giá trị trước X.
```

Đây chính là lý do **“ghi majority thành công” và “mọi lần đọc đều thấy ngay” là hai mệnh đề khác nhau**.

### 6.5. Timeout không phải rollback tự động

Nếu `wtimeout` hết:

```text
Primary:    đã ghi X
Secondary:  chưa xác nhận đủ điều kiện majority
Client:     nhận write concern timeout/error
```

Tình trạng ghi có thể **chưa được xác định theo mức bảo đảm yêu cầu**. Không được:

- lập tức tạo thêm document với ID mới vì nghĩ lần trước chưa ghi;
- trả thành công bền vững chỉ vì một node đọc thấy document;
- bỏ qua error metadata;
- ghi lặp một thao tác tăng/trừ tiền không idempotent.

Hãy đối soát theo ID/operation ID và chính sách write/read concern thích hợp.

## 7. Ma trận kết hợp read preference, read concern và write concern

Giả sử ứng dụng vừa ghi document X và muốn đọc lại:

| Ghi | Đọc | Có thể thấy giá trị cũ ngay sau khi ghi? | Nhận xét |
| --- | --- | --- | --- |
| `w:1` | `primary + local` | Thường thấy ghi ở primary nếu primary không đổi; có rủi ro rollback sau failover | Không phải cam kết chống rollback ở mọi tình huống |
| `w:1` | `secondary + local` | Có | Secondary có thể chưa áp dụng |
| `w:"majority"` | `secondary + local` | Có | Majority ack không đồng nghĩa tất cả secondary đã đồng bộ |
| `w:"majority"` | `secondary + majority` | Có thể | Dữ liệu được đọc là majority-committed nhưng secondary có thể chưa tới phiên bản mới |
| `w:"majority"` | `primary + majority` | Thường đáp ứng read-after-write khi hai thao tác tuần tự và primary bình thường; vẫn xét session/failover | Không phải linearizability tổng quát cho mọi client |
| `w:"majority"` | `secondary + majority + causal session` | Có thể phải chờ; thiết kế để bảo đảm read-your-writes trong điều kiện được hỗ trợ | Dùng cùng session và thực hiện tuần tự |
| `w:"majority"` | `primary + linearizable` | Bảo đảm mạnh khi điều kiện hỗ trợ được đáp ứng | Chi phí latency/availability cao hơn |

Bảng này là định hướng thiết kế. Để khẳng định một bảo đảm cụ thể phải xét phiên bản MongoDB, topology, session semantics, write/read concern thực tế, failover và liệu các thao tác có hoàn tất thành công theo đúng mức yêu cầu không.

## 8. Đảm bảo read-your-writes trong một luồng nghiệp vụ

### 8.1. Phương án đơn giản: đọc lại trên primary

Một luồng:

```text
Client -> write lên primary
Client <- write acknowledged
Client -> read từ primary
Client <- dữ liệu mới
```

Thường phù hợp với UI:

- vừa cập nhật hồ sơ cần hiển thị ngay;
- sau khi xác nhận thanh toán muốn xem trạng thái mới;
- sau khi đổi mật khẩu/quyền truy cập phải kiểm tra kết quả hiện hành;
- sau khi chỉnh giỏ hàng cần thấy kết quả vừa lưu.

Nhưng đọc từ primary **không tự động giải quyết mọi rủi ro**. Nếu ghi chỉ `w:1` rồi election/rollback xảy ra, hoặc lệnh đọc đi đến primary mới trước khi ghi được majority commit, kết quả có thể khác kỳ vọng. Khi yêu cầu độ bền và ordering mạnh, cần kết hợp write concern, read concern và session phù hợp.

### 8.2. Đọc từ secondary nhưng muốn thấy ghi của chính mình

Để giữ lợi ích đọc secondary trong khi cần một số bảo đảm về thứ tự, MongoDB hỗ trợ **causally consistent sessions**. Trong điều kiện được hỗ trợ, thực hiện các thao tác có quan hệ nhân quả **trong cùng session** với:

- write concern `"majority"`;
- read concern `"majority"`;
- các thao tác thực hiện tuần tự trong session;

có thể cung cấp các bảo đảm như **read-your-writes** và **monotonic reads**.

Ý tưởng:

```text
Session S:

  write X (majority)
        |
        v
  nhận operationTime / causal context
        |
        v
  read từ secondary (majority, cùng S)
        |
        +-- Nếu secondary chưa đủ tiến độ:
        |      chờ tới mốc phù hợp hoặc lỗi/timeout
        |
        +-- Khi thỏa điều kiện:
               có thể thấy X theo semantics causal
```

Đây không phải phép màu “đọc ở bất kỳ secondary nào cũng tức thì”: secondary chậm có thể khiến **latency tăng** hoặc khiến thao tác không thể hoàn tất trong timeout. Để có semantics, driver/server phải chuyển đúng **causal metadata**, không chỉ dùng chung một connection string.

### 8.3. Causal consistency không phải transaction

Causal session giúp bảo toàn quan hệ thứ tự giữa những thao tác liên quan. Nó **không tự biến nhiều lệnh ghi trên nhiều document thành một transaction nguyên tử**.

Ví dụ:

```text
Update order
Insert audit
Update inventory
```

Ba thao tác riêng lẻ dùng cùng session vẫn có thể **thành công một phần** nếu không nằm trong transaction. Nếu nghiệp vụ đòi cả ba cùng commit hoặc cùng rollback, phải thiết kế transaction đa document hoặc mô hình khác phù hợp.

### 8.4. Các thao tác phải được tuần tự hóa khi dùng cùng session

Không dùng một session cho nhiều thao tác đồng thời theo cách driver không hỗ trợ. Causal ordering cần một thứ tự rõ:

```javascript
await collection.updateOne(..., { session });
const value = await collection.findOne(..., { session });
```

Thay vì:

```javascript
// Không minh họa read-after-write; hai thao tác bắt đầu đồng thời.
await Promise.all([
  collection.updateOne(..., { session }),
  collection.findOne(..., { session })
]);
```

Hai thao tác trong `Promise.all` không có quan hệ “read xảy ra sau khi write được xác nhận”. Không có read-your-writes theo thứ tự mong muốn chỉ bằng cách truyền cùng session vào chúng.

### 8.5. Causal session của request A không tự truyền sang request B

Trên web, người dùng có thể gọi:

```text
PATCH /profile   -> server instance 1
GET   /profile   -> server instance 2
```

Nếu hai request dùng session độc lập không có causal context, một bảo đảm của session thứ nhất **không tự lan sang** request thứ hai.

Ứng dụng có thể chọn:

- Route các read-after-write nhạy cảm sang primary.
- Duy trì session nhất quán trong một chuỗi công việc do server điều phối.
- Thiết kế cơ chế truyền causal token/operation time theo cách driver và giao thức hỗ trợ, khi thực sự cần.
- Hiển thị kết quả write vừa được xác nhận trong UI, đồng thời làm mới từ nguồn phù hợp.

Không chuyển raw session ID hoặc thông tin nội bộ MongoDB tùy tiện qua client rồi gọi đó là bảo đảm nhất quán; thiết kế session, xác thực và lifetime phải đúng với driver/server.

## 9. Ví dụ Node.js: write majority rồi đọc secondary trong cùng causal session

### 9.1. Mục tiêu

Tạo một document trong collection thử nghiệm, ghi với `w:"majority"`, sau đó đọc từ secondary bằng **cùng causally consistent session** với read concern `majority`.

Chỉ chạy trên replica set thử nghiệm có **ít nhất một secondary đủ điều kiện**; nếu không có secondary, việc chọn `secondary` sẽ không thành công. Đoạn code minh họa dùng MongoDB Node.js driver; không chạy trên database nghiệp vụ thật.

### 9.2. Cấu hình client và session

```javascript
import {
  MongoClient,
  ObjectId,
  ReadPreference
} from "mongodb";

const uri = process.env.MONGODB_URI; // URI replica set được cấp.
const client = new MongoClient(uri, {
  serverSelectionTimeoutMS: 10000
});

await client.connect();

const database = client.db("mongo_read_consistency_row238_lab", {
  readConcern: { level: "majority" },
  writeConcern: { w: "majority", wtimeoutMS: 10000 }
});

const collection = database.collection("orders_demo");
const session = client.startSession({
  causalConsistency: true
});

const runId = "row238-" + new ObjectId().toHexString();
const orderId = new ObjectId();

try {
  const written = await collection.insertOne(
    {
      _id: orderId,
      runId,
      orderNo: "ORDER-238",
      status: "PAID",
      version: 1,
      createdAt: new Date()
    },
    {
      session,
      writeConcern: { w: "majority", wtimeoutMS: 10000 }
    }
  );

  console.log("insertedId:", written.insertedId.toString());

  const readBack = await collection.findOne(
    { _id: orderId, runId },
    {
      session,
      readPreference: new ReadPreference("secondary"),
      maxTimeMS: 10000
    }
  );

  console.log("readBack:", readBack);
} finally {
  await session.endSession();
  await client.close();
}
```

Trong ví dụ, read concern `majority` được cấu hình ở database và áp dụng cho collection. Lần đọc chọn `secondary`, còn session giữ ngữ cảnh causal.

Những điểm cần đọc đúng:

1. Ghi và đọc dùng **cùng session**.
2. Lệnh đọc chỉ bắt đầu **sau** khi `insertOne` đã được xác nhận thành công theo write concern yêu cầu.
3. Nếu secondary đang lag, lệnh đọc có thể phải chờ để phục vụ ngữ nghĩa causal hoặc kết thúc bằng lỗi/timeout.
4. Nếu chỉ có standalone `mongod` hoặc không có secondary phù hợp, không thể dùng ví dụ để chứng minh stale read.
5. Đây không phải benchmark latency; phép thử nhỏ chỉ làm rõ contract consistency.

### 9.3. Lỗi và dọn dữ liệu khi thực hành

Code production nên phân loại:

- `server selection timeout`: không tìm được secondary phù hợp.
- `maxTimeMS`/timeout: chưa hoàn tất trong thời hạn; không đồng nghĩa read concern không hoạt động.
- `writeConcernError`: ghi có thể đã được áp dụng nhưng chưa được xác nhận ở mức yêu cầu.
- `network error`: kết quả có thể chưa rõ; không tự insert lại với `_id` mới.

Để dọn document do chính lượt thử nghiệm tạo, sau khi kiểm tra `runId` và `orderId`, dùng một **lệnh riêng** qua client mới/phiên phù hợp:

```javascript
const doc = await collection.findOne(
  { _id: orderId, runId },
  { readPreference: new ReadPreference("primary") }
);

if (doc && doc.runId === runId) {
  const removed = await collection.deleteOne({
    _id: orderId,
    runId
  });
  console.log("deletedCount:", removed.deletedCount);
}
```

Đoạn dọn này mang tính minh họa cho **scope xóa an toàn** và cần thực hiện trước khi đóng client hoặc trong một script riêng đã thiết lập lại các biến. Không dùng `deleteMany({})` hoặc `dropDatabase()` chỉ để dọn bài test.

## 10. Thực hành `mongosh`: đo replication lag thay vì cố tình gây lỗi

### 10.1. Quan sát replica set

Kết nối `mongosh` với replica set mà bạn có quyền giám sát:

```bash
mongosh "mongodb://localhost:27017,localhost:27018,localhost:27019/?replicaSet=rs0"
```

Đây là URI local minh họa; thay host, tên replica set, TLS và xác thực theo môi trường thật.

```javascript
const status = rs.status();

printjson(
  status.members.map((m) => ({
    name: m.name,
    state: m.stateStr,
    health: m.health,
    optimeDate: m.optimeDate,
    syncSourceHost: m.syncSourceHost
  }))
);
```

Với những phiên bản cung cấp các field liên quan, kết quả cho biết:

- member nào là `PRIMARY` và `SECONDARY`;
- thời điểm applied optime được báo cáo;
- sức khỏe/heartbeat;
- sync source của từng secondary nếu có.

Output cụ thể thay đổi giữa MongoDB version. Trên một primary đang thay đổi, một lần gọi `rs.status()` cũng chỉ là **snapshot quan sát**, không thay thế monitoring liên tục.

### 10.2. Ước lượng lag từ tiến độ thành viên

```javascript
const s = rs.status();
const primary = s.members.find((m) => m.stateStr === "PRIMARY");

if (!primary || !(primary.optimeDate instanceof Date)) {
  print("Không đủ dữ liệu optimeDate của primary.");
} else {
  const rows = s.members
    .filter((m) => m.stateStr === "SECONDARY")
    .map((m) => ({
      member: m.name,
      lastApplied: m.optimeDate ?? null,
      estimatedLagSeconds:
        m.optimeDate instanceof Date
          ? Math.max(
              0,
              (primary.optimeDate.getTime() -
                m.optimeDate.getTime()) / 1000
            )
          : null
    }));

  printjson(rows);
}
```

Phép trừ dùng các field được server báo cáo; các timestamp có thể có độ phân giải và tuổi dữ liệu khác nhau. Không coi `estimatedLagSeconds: 0` là bằng chứng chắc chắn mọi document đã giống nhau trên mọi member.

### 10.3. Helper và thông tin oplog

```javascript
rs.printReplicationInfo();
rs.printSecondaryReplicationInfo();
```

Tùy phiên bản shell/server, các helper này có thể hiển thị kích thước/cửa sổ oplog và độ trễ secondary.

Các thông tin khác có thể thu từ lệnh quản trị:

```javascript
printjson(db.adminCommand({ replSetGetStatus: 1 }));
```

Nếu thiếu quyền, không thay cấu hình hoặc vô hiệu hóa bảo mật để xem kết quả. Nhờ DBA/SRE cung cấp metric từ Atlas hoặc hệ thống quan sát đã được phê duyệt.

### 10.4. Tại sao không cố làm replication lag tăng để minh họa?

Các thao tác như ngắt network, làm đầy disk, tạm dừng secondary, bắn hàng triệu write hoặc xóa oplog có thể ảnh hưởng **availability, election, oplog window, dữ liệu và backup** của cả replica set.

Bài thực hành nên:

1. Quan sát trên cluster test.
2. Ghi một document nhỏ theo `runId`.
3. Đọc từ primary và secondary theo quyền phù hợp.
4. Ghi nhận cả trường hợp **không nhìn thấy sai khác** vì replication quá nhanh.
5. Nếu muốn tái tạo lag có kiểm soát, làm theo bài lab riêng có tài nguyên cô lập và runbook được quản trị viên cho phép.

Không cần gây lỗi thật trên replica set dùng chung để hiểu semantics.

## 11. Failover, rollback và tính mới của dữ liệu

### 11.1. Khi primary đổi vai trò

Replica set có thể bầu primary mới khi primary cũ không còn phù hợp. Quá trình election/failover làm thay đổi node tiếp nhận ghi và có thể ảnh hưởng đến những đọc/ghi đang diễn ra.

```text
Trước election:
  Primary P  : có write X
  Secondary A: đã sao chép X
  Secondary B: chưa sao chép X

Sau sự cố:
  Một secondary phù hợp được bầu làm primary mới.
```

Việc write X có được duy trì hay không phụ thuộc các điều kiện như tiến độ replication, majority commit, cấu hình và diễn biến election.

### 11.2. Vì sao `w:1` có rủi ro?

Một write được primary xác nhận ở mức `w:1` **có thể chưa được majority commit**. Nếu primary đó mất vai trò trước khi các member khác có thay đổi, MongoDB có thể rollback những thao tác không thuộc lịch sử đã commit của replica set.

Điều này khác stale read thông thường:

- **Stale read do lag**: dữ liệu mới đã tồn tại ở một số member, secondary đọc chưa theo kịp.
- **Rollback**: một thao tác chưa được commit theo mức yêu cầu có thể không còn là một phần của lịch sử được giữ sau failover.

Ứng dụng không nên diễn giải một response `w:1` là bảo đảm ghi bền vững trong mọi trường hợp thay primary.

### 11.3. Ghi majority và đọc primary có đủ không?

Đó là lựa chọn phù hợp cho nhiều luồng read-after-write thông thường. Nhưng nếu hệ thống cần **linearizability** hoặc các bảo đảm liên quan thời gian thực rất chặt, phải xét read concern tương ứng, thực hiện thao tác theo đúng thứ tự và chính sách session.

Không dùng tên “primary” như một lời hứa tuyệt đối rằng mọi truy vấn vào primary luôn có đầy đủ bảo đảm về commit/durability mà ứng dụng muốn.

### 11.4. Những đọc/ghi đang chạy có thể lỗi

Khi có election, driver có thể:

- phát hiện primary đã đổi;
- chọn server khác;
- retry một số thao tác đủ điều kiện;
- trả network/server selection/transient error.

Nếu client retry toàn bộ business operation sau khi mất phản hồi ghi, cần **idempotency key** khi thao tác có side effect không được phép lặp, ví dụ trừ tồn kho hoặc tạo thanh toán.

## 12. Causal consistency, monotonic reads và thứ tự quan sát

### 12.1. Bốn bảo đảm được nhắc đến trong causal consistency

MongoDB mô tả các bảo đảm causal cho những thao tác có quan hệ nhân quả dưới các điều kiện thích hợp:

| Bảo đảm | Ý nghĩa trực giác |
| --- | --- |
| **Read-your-writes** | Sau khi ghi X trong ngữ cảnh có quan hệ nhân quả, lần đọc tiếp theo không quay về trạng thái trước X |
| **Monotonic reads** | Một luồng đọc không quan sát lịch sử đi lùi |
| **Monotonic writes** | Các write có quan hệ nhân quả được thực hiện theo thứ tự thích hợp |
| **Writes-follow-reads** | Write sau một read tôn trọng những thay đổi đã được quan sát trước đó |

Các bảo đảm này gắn với **session**, read concern, write concern và thứ tự thực thi. Không thể suy ra chúng chỉ từ việc MongoDB là “NoSQL” hoặc dùng một connection pool duy nhất.

### 12.2. Một ví dụ về monotonic reads

```text
Session S:
  Read lần 1 ở Secondary A -> version 20
  Read lần 2 ở Secondary B -> cần không đi lùi về version 18
```

Khi phiên causal được dùng đúng, server/driver phải đáp ứng causal ordering hoặc lệnh đọc có thể chờ/thất bại nếu member chưa đủ tiến độ. Nếu không duy trì causal context, hai lần đọc chọn secondary khác nhau có thể trả trạng thái ở các điểm khác nhau.

### 12.3. Những điều causal session không làm

Nó không:

- làm mọi secondary luôn đồng bộ tức thì;
- thay thế transaction đa document;
- tự tạo unique index;
- bảo đảm dữ liệu của mọi client độc lập được sắp theo một trật tự thời gian thực toàn cục trong mọi trường hợp;
- ngăn một request HTTP khác dùng session mới đọc cũ;
- sửa dữ liệu đã bị cache ở phía ứng dụng.

**Causal consistency là một mô hình bảo đảm cụ thể**, không phải nút bật “strong consistency cho mọi thứ”.

## 13. Chọn mức nhất quán theo loại API

Không có một cặp read/write settings tối ưu cho tất cả ứng dụng. Hãy mô tả **tác hại của stale read** trước rồi chọn chính sách.

### 13.1. Hồ sơ người dùng: yêu cầu thấy thay đổi ngay

Sau `PATCH /profile`, người dùng muốn thấy tên/ảnh mới:

- Ghi theo mức write concern phù hợp độ bền nghiệp vụ.
- Đọc lại từ primary hoặc dùng causal session khi đọc secondary.
- Cập nhật state giao diện bằng kết quả server trả về; đồng thời quản lý cache invalidation.
- Nếu GET điều hướng tới server khác, cần nhất quán session/token hoặc route phù hợp.

Một GET đi tới secondary bất kỳ ngay sau PATCH có thể gây hiện tượng “tôi đã lưu nhưng dữ liệu lại quay về cũ”.

### 13.2. Số dư hoặc tồn kho: yêu cầu đúng để ra quyết định

Với số dư, hạn mức thanh toán hoặc phân bổ tồn kho, **không đưa quyết định quan trọng chỉ dựa trên bản sao có thể stale**.

Tốt hơn:

- Thực hiện điều kiện nghiệp vụ trong chính thao tác ghi nguyên tử trên primary, như `updateOne` với filter còn đủ tồn kho.
- Dùng transaction nếu invariant trải nhiều document.
- Chọn write concern và các phép đọc cần thiết theo yêu cầu tính đúng đắn.
- Không coi việc hiển thị một số dư từ secondary là nguồn sự thật cho phép trừ tiền.

Ví dụ bảo vệ không trừ quá số lượng trong một document:

```javascript
db.inventory.updateOne(
  {
    _id: "SKU-238",
    available: { $gte: 2 }
  },
  {
    $inc: {
      available: -2
    }
  }
);
```

Điều kiện `available >= 2` được kiểm trong cùng thao tác ghi nguyên tử. Nếu client trước đó đọc tồn kho cũ, MongoDB vẫn kiểm lại số tồn hiện tại khi update, thay vì tin một giá trị chụp từ secondary.

### 13.3. Feed, bảng xếp hạng, báo cáo: có thể chấp nhận trễ

Một dashboard KPI cập nhật mỗi phút hoặc feed tổng hợp có thể chấp nhận dữ liệu trễ vài giây:

- Có thể đọc secondary để giảm tải.
- Cấu hình read preference và max staleness theo mức phù hợp.
- Hiển thị “cập nhật lúc ...” để người dùng hiểu độ mới.
- Không dùng dữ liệu phân tích đó làm điều kiện duy nhất cho thao tác tài chính hoặc kiểm soát tồn kho.

Phải xác định **SLO về freshness** bằng số đo thực tế, thay vì chỉ viết “eventually consistent”.

### 13.4. Audit/kiểm toán: mới nhất chưa chắc là mục tiêu duy nhất

Một báo cáo kiểm toán thường quan tâm dữ liệu đã commit và snapshot nhất quán hơn là thấy mọi write chưa xác nhận ngay tức thì. Khi đó có thể cần:

- `readConcern: "majority"` hoặc snapshot semantics thích hợp;
- định nghĩa một mốc thời gian chốt báo cáo;
- materialized view hoặc bản sao báo cáo có nguồn gốc rõ;
- lưu lịch sử ngoài oplog để audit lâu dài.

Đọc “mới nhất trên primary” đơn thuần không tự cung cấp một snapshot ổn định cho nhiều phép truy vấn trải nhiều collection.

### 13.5. Ma trận lựa chọn

| Nghiệp vụ | Có chấp nhận stale read? | Cách tiếp cận ban đầu |
| --- | --- | --- |
| Người dùng vừa sửa hồ sơ và tải lại | Không mong muốn | Primary read hoặc causally consistent session |
| Kiểm tra điều kiện trừ tồn kho | Không | Điều kiện trong atomic write/transaction |
| Trang báo cáo theo giờ | Có, nếu giới hạn rõ | Secondary + monitoring freshness |
| Bảng xếp hạng gần realtime | Có thể | Secondary + cache + công bố thời điểm cập nhật |
| Xem đơn ngay sau tạo | Thường không | Đọc primary, hoặc causal majority session |
| Báo cáo nhiều collection theo một mốc | Cần snapshot đúng hơn là tức thời | Snapshot/read concern và kiến trúc báo cáo |
| Đọc thông tin công khai ít thay đổi | Thường có | Secondary, cache, TTL hợp lý |
| Kiểm tra quyền truy cập trước ghi nhạy cảm | Không tin bản sao cũ | Xác thực/quyền và điều kiện tại bước ghi |

Đây là gợi ý kiến trúc, không thay thế kiểm thử và tài liệu MongoDB theo phiên bản.

## 14. Một ứng dụng đa vùng (*multi-region*) sẽ đánh đổi thế nào?

### 14.1. Khoảng cách mạng và replication

Đặt secondary gần người dùng ở một châu lục khác giúp giảm network latency khi đọc. Nhưng:

- độ trễ mạng giữa các vùng có thể tăng thời gian secondary nhận thay đổi;
- tải và jitter mạng có thể làm lag dao động;
- một vùng có thể gặp sự cố riêng;
- đọc “nearest” có thể trả dữ liệu cũ hơn primary ở vùng khác.

Ví dụ:

```text
Primary tại region A
    |
    +-- Secondary trong A: RTT thấp, lag ~0-1 giây
    |
    +-- Secondary ở B:   RTT liên vùng, lag ~2-5 giây

Người dùng tại B:
    đọc local nhanh hơn, nhưng có thể stale.
```

Con số chỉ minh họa. Không dùng độ trễ mạng làm phép đo chính xác replication lag; cần theo dõi metric oplog/optime và hành vi ứng dụng.

### 14.2. Chiến lược read routing theo độ quan trọng

Một phương án:

```text
GET /public-catalog        -> secondaryPreferred
GET /dashboard             -> secondary
GET /profile/after-update  -> primary
POST /checkout             -> primary/atomic operation
GET /order/just-created    -> primary hoặc causal session
```

Không phải route nào cũng phải dùng cùng read preference; nếu driver/framework cho phép, cấu hình theo collection hoặc từng operation với quy tắc đơn giản, dễ kiểm toán.

### 14.3. Fallback có thể thay đổi freshness

`secondaryPreferred` có thể fallback về primary khi không có secondary phù hợp. Kết quả là một API có thể chuyển giữa các nguồn với độ mới khác nhau khi topology thay đổi. Việc “đang đọc được” không chứng minh dữ liệu thỏa hợp đồng freshness.

Nếu một API quan trọng không được phép dùng secondary lag, hãy đặt chính sách rõ rằng nếu không có nguồn đáp ứng yêu cầu thì **trả lỗi/chờ có giới hạn** thay vì âm thầm đọc dữ liệu cũ.

## 15. Khả năng quan sát và cảnh báo stale reads

### 15.1. Theo dõi replication lag theo từng member

Các chỉ số nên thu thập:

| Metric | Mục đích |
| --- | --- |
| Applied optime lag trên từng secondary | Chênh tiến độ áp dụng |
| Durable optime và majority commit point | Phân biệt applied và các mốc commit/bền vững |
| Oplog window trên sync source | Lịch sử còn lại để member bắt kịp |
| Rate tạo oplog và rate áp dụng | Xác định backlog đang tăng hay giảm |
| Network RTT/bandwidth/packet loss | Điều tra nguyên nhân network |
| Disk IOPS, latency, CPU, cache pressure | Điều tra secondary apply chậm |
| Election/rollback/sync source changes | Đối chiếu sự kiện topology |
| Server selection errors | Biết khi không có node thỏa read preference |
| Thời gian chờ causal read/timeout | Phát hiện latency tăng do chờ tiến độ |
| Độ cũ cache/response ở tầng ứng dụng | Tách lag MongoDB khỏi stale do cache |

Không chỉ xem lag trung bình cả replica set: một secondary có thể tụt nhiều phút trong khi các member khác khỏe.

### 15.2. Cảnh báo theo yêu cầu của ứng dụng

Một ứng dụng có:

- API hồ sơ yêu cầu read-after-write rõ ràng.
- Dashboard cho phép dữ liệu cũ tối đa khoảng 1 phút theo SLO nội bộ.
- Secondary delayed 2 giờ với mục tiêu khôi phục.

Ba đường dữ liệu này cần **ba chính sách cảnh báo khác nhau**. Đặt một ngưỡng “lag trên 60 giây là sự cố” cho tất cả member có thể gây báo động sai ở delayed secondary và bỏ sót sự cố read-after-write trên API nhạy cảm khi lag chỉ vài giây.

### 15.3. Headroom so với oplog window

Một ước lượng:

\[
\text{Headroom} \approx \text{Oplog window}-\text{Lag}
\]

Nếu window còn 6 giờ và lag đã 5 giờ, secondary có thể sắp thiếu lịch sử để bắt kịp. Đừng chờ đến khi lag vượt window mới cảnh báo; cửa sổ có thể co nhanh khi primary tạo nhiều oplog.

Headroom theo thời gian là **chỉ số thô**, còn khả năng catch-up thực tế phụ thuộc vị trí oplog cụ thể và sync source hợp lệ.

### 15.4. Log đúng thông tin để debug

Với request liên quan consistency, nếu quy trình cho phép, lưu:

- correlation ID và tên API;
- thời điểm và kết quả write;
- write concern/read concern/read preference thực tế;
- server được chọn cho read (qua tracing/driver command monitoring);
- session/causal context ở mức metadata an toàn, không log credentials;
- document version hoặc business revision trả về;
- dấu hiệu cache hit/miss và độ tuổi cache;
- thời gian thực thi/các lỗi timeout.

Không log full URI có mật khẩu, access token hoặc dữ liệu cá nhân chỉ để chứng minh request đọc từ secondary.

## 16. Quy trình điều tra “tôi vừa lưu nhưng vẫn thấy dữ liệu cũ”

### 16.1. Bước 1: xác minh lệnh ghi

Đặt các câu hỏi:

1. API có nhận acknowledgment hay write concern error?
2. `matchedCount`/`modifiedCount`/`upsertedId` cho biết gì?
3. Filter ghi có đúng ID, tenant và trạng thái không?
4. Có worker nào có thể ghi đè bằng snapshot cũ sau đó không?
5. Có duplicate request hoặc retry gây tác dụng ngoài dự kiến không?

Đừng vội quy trách nhiệm cho replication nếu update thực sự không khớp document hoặc đã bị request khác ghi đè.

### 16.2. Bước 2: xác minh nguồn đọc

Kiểm tra:

- Read preference ở URI/client/database/collection/operation.
- Read concern đang dùng.
- Lần đọc có diễn ra trong causal session theo đúng thứ tự không?
- Secondary nào được chọn, có tags/max staleness không?
- Response có đi qua Redis/CDN/browser cache không?

Nếu đọc trên secondary, so tiến độ của node đó với primary tại cùng khoảng thời gian.

### 16.3. Bước 3: xem dữ liệu tại primary và secondary

Trong môi trường được phép, kiểm tra cùng một business key và projection trên các nguồn khác nhau với quyền đọc phù hợp. Nếu primary có version 9 nhưng secondary đang có version 8, đó là bằng chứng trực tiếp về **khác biệt tiến độ quan sát** tại lúc kiểm tra.

Nếu cả primary và secondary đều có version 9 mà API vẫn trả version 8, xem lại cache, API response mapping, database/tenant được chọn hoặc node mà request thực tế đi tới.

Không chạy lệnh ghi thử trên production hay thay election config chỉ để kiểm tra.

### 16.4. Bước 4: phân loại nguyên nhân

| Dấu hiệu | Nghi ngờ ban đầu | Hành động phù hợp |
| --- | --- | --- |
| Ghi không khớp filter | Version/state/ID sai | Kiểm tra query và xử lý conflict |
| Ghi thành công, primary mới, secondary cũ | Replication lag | Điều chỉnh read routing/causal consistency, theo dõi lag |
| Mọi node mới, API trả cũ | Cache hoặc ứng dụng | Kiểm tra TTL, invalidation, response caching |
| Sau failover giá trị biến mất | Ghi chưa majority-committed/rollback hoặc logic khác | Xem write concern, election logs, đối soát |
| Causal read chờ rồi timeout | Secondary chưa đủ tiến độ hoặc unavailable | Xem server selection, lag, timeout, phương án đọc primary |
| Secondary lag tăng liên tục | Năng lực áp dụng không theo kịp | Network/disk/CPU/workload |
| Dữ liệu “đi lùi” giữa các GET | Đọc các secondary có tiến độ khác nhau hoặc cache | Dùng causal session/chọn nguồn theo contract |

### 16.5. Bước 5: sửa nguyên nhân, không chỉ che triệu chứng

Nếu API có yêu cầu read-your-writes, chỉnh routing hoặc session, đừng chỉ thêm `sleep(1000)` rồi hy vọng secondary luôn theo kịp. Chờ cố định:

- có thể thừa khi replica set khỏe;
- có thể **không đủ** khi lag tăng cao;
- làm tăng latency mà không tạo một bảo đảm nhất quán rõ ràng.

Nếu cần chờ dữ liệu đạt một mốc nhất định, sử dụng cơ chế causal/consistency của MongoDB hoặc kiểm tra có điều kiện theo version với timeout và policy phù hợp, không phụ thuộc “ngủ một giây”.

## 17. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Ghi thành công rồi đọc secondary bất kỳ và kỳ vọng dữ liệu mới | Thấy giá trị cũ | Primary read hoặc causal session khi cần |
| Coi `w:"majority"` là tất cả secondary đã cập nhật | Đọc thiếu thay đổi ở secondary chậm | Hiểu majority không phải all |
| Coi `readConcern:"majority"` là luôn mới nhất | Nhầm dữ liệu committed với dữ liệu freshest | Phối hợp read preference/causal |
| Chọn `nearest` vì muốn dữ liệu “gần nhất về thời gian” | Node gần về mạng nhưng có thể lag | Hiểu nearest là network latency |
| Chọn `maxStalenessSeconds` rồi coi là hard TTL | Có thể đọc cũ hơn ngưỡng trực giác | Hiểu là server selection ước tính |
| Thêm `sleep` cố định sau mọi write | Tăng latency, không đảm bảo | Dùng cơ chế nhất quán rõ ràng |
| Chỉ nhìn `rs.status()` một lần rồi khẳng định hệ thống healthy | Bỏ qua lag thay đổi và election | Theo dõi chuỗi thời gian/metrics |
| Coi `lag=0` là mọi thao tác đã durable/majority | Nhầm chỉ số khác nhau | Phân biệt optime applied/durable/commit |
| Chỉ lấy timestamp ứng dụng để đo replication | Đồng hồ khác nhau, cache, latency khác | Dùng metric replication và tracing |
| Sau write timeout tự insert lại với `_id` mới | Có thể tạo duplicate nghiệp vụ | ID ổn định, idempotency/đối soát |
| Dùng secondary read để quyết định trừ tồn kho | Có thể dựa trên số tồn cũ | Kiểm điều kiện trong atomic write |
| Tin cache stale là lag MongoDB | Chẩn đoán sai, điều chỉnh DB vô ích | Xác định cache layer và node đọc |
| Nghĩ session tự truyền qua mọi HTTP request | Bỏ bảo đảm causal giữa request | Duy trì context hoặc route đọc phù hợp |
| Dùng cùng session với thao tác song song | Không xác lập thứ tự nhân quả mong muốn | Thực hiện tuần tự |
| Dùng snapshot để đồng nghĩa latest | Báo cáo nhất quán nhưng vẫn cũ theo thời điểm hiện tại | Chọn đúng mức consistency |
| Dùng `w:1` cho dữ liệu không được rollback trong bất kỳ hoàn cảnh nào | Khả năng mất thay đổi sau failover | Xem xét majority và thiết kế durability |
| Giảm write concern để “cải thiện lag” mà không xét nghiệp vụ | Làm yếu bảo đảm ghi, không chữa bottleneck | Xử lý nguyên nhân replication/capacity |
| Không theo dõi oplog window khi lag tăng | Secondary có thể mất lịch sử catch-up | Theo dõi window/headroom và workload |

## 18. Bài thực hành suy luận

### Bài A. Majority ghi thành công nhưng đọc vẫn cũ

Replica set gồm primary P, secondary A và B. Một thao tác ghi X được P và A xác nhận; B đang trễ 90 giây.

1. Với voting config thông thường gồm ba data-bearing member, điều kiện `w:"majority"` có thể đã đạt chưa?
2. Nếu `GET` được route đến B với `readConcern:"local"`, có chắc thấy X không?
3. Nếu đổi sang `readConcern:"majority"` trên B, có chắc thấy X ngay không?
4. Phương án nào để API vừa ghi vừa đọc lại bảo đảm read-your-writes?

**Gợi ý:** majority không đồng nghĩa mọi member; B có thể chậm dù đã có majority acknowledgment. Read concern majority không tự ép B tới mốc ghi X; cân nhắc primary hoặc causal session majority khi phù hợp.

### Bài B. Read preference nearest

Ứng dụng ở region B:

```text
Primary A:         RTT 70 ms, lag tham chiếu 0
Secondary B:       RTT  4 ms, lag 8 giây
```

1. Vì sao `nearest` có thể chọn B?
2. Màn hình nào có thể chấp nhận kết quả đó?
3. Màn hình nào không nên dựa vào nó?
4. Nếu người dùng vừa cập nhật profile, nên đổi routing hay dùng cơ chế causal nào?

### Bài C. Đọc dữ liệu đi lùi

Một client đọc profile lần 1 từ secondary A thấy `version: 12`, lần 2 từ B thấy `version: 10`.

1. Hiện tượng vi phạm kỳ vọng nào?
2. Có phải dữ liệu trên primary đã tự động rollback không?
3. Vì sao dùng causal context và majority read có thể hữu ích?
4. Nếu GET nằm ở hai HTTP request khác server, cần chú ý yếu tố gì?

### Bài D. Giới hạn của `maxStalenessSeconds`

Ứng dụng đặt:

```text
readPreference=secondary
maxStalenessSeconds=120
```

1. Đây là giới hạn cứng cho tuổi của **từng document** hay tiêu chí chọn secondary?
2. Nếu tất cả secondary bị đánh giá quá cũ, request sẽ làm gì?
3. Có nên coi cấu hình trên là thay thế cho một điều kiện đọc “sau ghi X” không?
4. Vì sao không thể cấu hình ngưỡng tùy ý nhỏ tới 1 giây?

### Bài E. Thao tác tồn kho

Hai request cùng đọc `available: 3` từ một secondary. Mỗi request muốn trừ 2.

1. Nếu cả hai tính `newAvailable=1` rồi `$set` theo `_id`, có thể xảy ra lost update không?
2. Dùng `updateOne({available:{$gte:2}},{$inc:{available:-2}})` giúp gì?
3. Nếu retry request sau timeout, điều kiện tồn kho có thay thế operation ID để chống trừ lặp không?
4. Khi invariant trải nhiều document, cần cơ chế nào?

### Bài F. Triage sau failover

Người dùng thấy một đơn hàng đã tạo biến mất sau khi replica set bầu primary mới.

Hãy phân biệt:

- stale read từ secondary;
- write chưa majority-committed bị rollback;
- request write từng bị timeout;
- cache đã giữ kết quả cũ;
- sự cố chọn sai tenant/namespace.

Đề xuất những metric/log cần thu trước khi kết luận.

## 19. Tài liệu tham khảo chính thức

Khi áp dụng vào hệ thống thật, kiểm tra tài liệu **phù hợp phiên bản MongoDB và Node.js driver đang dùng**:

- [Replica Set Data Synchronization](https://www.mongodb.com/docs/manual/core/replica-set-sync/) — cách secondary sao chép dữ liệu.
- [Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/) — lịch sử oplog và cửa sổ retention.
- [Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/) — chọn primary/secondary và các chế độ.
- [Read Preference maxStalenessSeconds](https://www.mongodb.com/docs/manual/reference/read-preference/#maxstalenessseconds) — điều kiện chọn secondary theo độ cũ ước tính.
- [Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/) — các mức nhất quán đọc.
- [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — xác nhận ghi.
- [Causal Consistency and Read and Write Concerns](https://www.mongodb.com/docs/manual/core/causal-consistency-read-write-concerns/) — bảo đảm trong causally consistent sessions.
- [Linearizable Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern-linearizable/) — giới hạn và semantics đọc tuyến tính.
- [rs.status()](https://www.mongodb.com/docs/manual/reference/method/rs.status/) — quan sát tiến độ replica set.
- [MongoDB Node.js Driver Sessions](https://www.mongodb.com/docs/drivers/node/current/fundamentals/transactions/#causal-consistency) — cách làm việc với session và causal consistency trong driver.

## 20. Kết luận

**Replication lag** khiến các secondary có thể chưa chứa những ghi mới nhất đã được primary xử lý. Vì thế **stale read** có thể xuất hiện ngay cả khi API ghi vừa báo thành công, đặc biệt khi ứng dụng sử dụng `secondary`, `secondaryPreferred` hoặc `nearest` để chọn node đọc. Khi đọc từ nhiều secondary, một người dùng còn có thể thấy dữ liệu “đi lùi” giữa các lần đọc.

Để thiết kế đúng, cần phân biệt ba lớp: **write concern** xác định mức xác nhận ghi; **read preference** xác định node đọc; **read concern** xác định semantics dữ liệu có thể đọc. `w:"majority"` không có nghĩa tất cả secondary đã bắt kịp, còn `readConcern:"majority"` không tự bảo đảm một secondary trả đúng dữ liệu mới nhất. Khi cần **read-your-writes**, nên chọn đọc primary với mức bảo đảm phù hợp hoặc dùng **causally consistent session** với các điều kiện majority và thứ tự thao tác được hỗ trợ.

Độ mới cần được định nghĩa theo **nghiệp vụ**: một dashboard có thể chấp nhận vài giây trễ, còn kiểm tra tồn kho, quyền hoặc trạng thái thanh toán phải tránh ra quyết định dựa trên snapshot cũ. Hãy theo dõi lag, oplog window, tiến độ từng member, kết quả election và cache layer, đồng thời đặt điều kiện đúng **tại thao tác ghi** đối với invariant quan trọng. **Không xử lý stale read bằng một khoảng sleep cố định hoặc bằng giả định rằng “ghi thành công” luôn đồng nghĩa “mọi replica đã cập nhật”.**
