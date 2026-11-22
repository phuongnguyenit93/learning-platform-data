# Journal, checkpoint và khả năng khôi phục sau sự cố trong MongoDB

## 1. Bài toán cốt lõi: dữ liệu nằm ở đâu khi MongoDB bất ngờ dừng?

Khi ứng dụng gọi **insert**, **update** hoặc **delete**, MongoDB cần xử lý thay đổi nhanh, đồng thời phải bảo vệ dữ liệu trước những tình huống như tiến trình **mongod** bị dừng đột ngột, hệ điều hành gặp lỗi hoặc máy chủ mất điện. Nếu mỗi thay đổi đều buộc phải ghi toàn bộ các trang dữ liệu xuống đĩa trước khi trả lời ứng dụng, chi phí I/O sẽ lớn. Ngược lại, nếu chỉ giữ thay đổi trong RAM, dữ liệu có thể biến mất khi máy bị tắt.

MongoDB sử dụng **WiredTiger storage engine** với hai cơ chế bổ trợ nhau:

- **Journal (write-ahead log, WAL):** ghi nhận các thay đổi vào nhật ký bền vững trên đĩa để có thể phát lại sau khi máy chủ gặp lỗi.
- **Checkpoint:** ghi một trạng thái dữ liệu **nhất quán** từ bộ nhớ xuống các tệp dữ liệu và xác lập mốc khôi phục mới.

Hai cơ chế này là nền tảng cho **crash recovery** tại một instance MongoDB. Chúng không thay thế cho replica set, backup hoặc kế hoạch disaster recovery.

~~~text
                Ứng dụng Java / mongosh
                          |
                          | insert / update / delete
                          v
                    MongoDB mongod
                          |
                  WiredTiger engine
                 /                 \
                v                   v
       Bộ nhớ/cache            Journal buffer
       (trang đã sửa)               |
                |                   | flush/sync
                |                   v
                |              Journal trên đĩa
                |
                | checkpoint định kỳ
                v
          Tệp dữ liệu trên đĩa
          (checkpoint nhất quán)

       Nếu mongod crash: checkpoint + journal => recovery
~~~

Hình trên mô tả **vai trò logic** của các thành phần; thứ tự thực thi bên trong storage engine có thể gồm nhiều bước ghi và đồng bộ. Ý chính của WAL là các thay đổi cần khôi phục được ghi vào journal theo quy tắc bền vững trước khi một checkpoint mới được coi là nguồn dữ liệu an toàn.

### 1.1. Phân biệt ba mục tiêu dễ bị nhầm

| Mục tiêu | Câu hỏi cần trả lời | Cơ chế liên quan |
|---|---|---|
| **Durability (độ bền dữ liệu)** | Khi hệ thống đã xác nhận ghi thành công, thay đổi có chống chịu được loại sự cố yêu cầu không? | Journal, checkpoint, write concern, lưu trữ bền vững. |
| **High availability (tính sẵn sàng)** | Một node ngừng hoạt động, hệ thống có tiếp tục phục vụ trên node khác không? | Replica set, election/failover; với sharding còn phụ thuộc các thành phần cluster. |
| **Recoverability (khả năng khôi phục)** | Có thể đưa dữ liệu và dịch vụ trở lại trạng thái phù hợp sau sự cố không? | Crash recovery, backup/restore, replication, vận hành khôi phục. |

Ví dụ: một standalone MongoDB có journal có thể **khôi phục dữ liệu trên cùng ổ đĩa sau khi tiến trình crash** nhưng ứng dụng vẫn ngừng hoạt động trong lúc server khởi động lại. Nếu ổ đĩa hỏng hoàn toàn và mất cả journal lẫn data files, chỉ journal cũng không cứu được hệ thống.

## 2. WiredTiger và những lớp lưu trữ cần hiểu

WiredTiger là storage engine mặc định trong các phiên bản MongoDB hiện đại. Nó sử dụng cơ chế **Multi-Version Concurrency Control (MVCC)** cùng cache để hỗ trợ xử lý truy vấn đồng thời, giữ các phiên bản dữ liệu cần thiết và tạo snapshot nhất quán.

### 2.1. Cache và dirty pages

Khi một document được cập nhật, các cấu trúc dữ liệu/index liên quan có thể thay đổi trong bộ nhớ. Những trang đã được sửa nhưng chưa ghi ở dạng tương ứng xuống data files được gọi là **dirty pages**.

Không thể suy luận rằng:

> API trả về thành công = mọi trang dữ liệu đã xuất hiện ngay trong tệp collection trên đĩa.

Phản hồi ghi còn phụ thuộc **write concern**. WiredTiger không cần ghi ngay toàn bộ dirty pages thành checkpoint cho mỗi request. Journal đảm nhiệm việc ghi lại thông tin để khôi phục các thay đổi được bảo đảm bền vững trong khoảng giữa các checkpoint.

### 2.2. Tệp dữ liệu và journal khác nhau

| Thành phần | Vai trò chính | Đặc điểm |
|---|---|---|
| **WiredTiger cache** | Giữ những trang và dữ liệu đang xử lý, hỗ trợ đọc/ghi hiệu quả. | RAM là bộ nhớ mất dữ liệu khi máy tắt. |
| **Data files** | Chứa dữ liệu/index được storage engine duy trì trên đĩa. | Có trạng thái nhất quán được xác định bởi checkpoint hợp lệ. |
| **Journal files** | Lưu các bản ghi thay đổi cần thiết để recovery. | Là log nhị phân nội bộ của WiredTiger, được ghi/sync theo cơ chế journaling. |
| **Checkpoint metadata** | Chỉ ra checkpoint dữ liệu hợp lệ gần nhất. | Được cập nhật theo cách bảo toàn mốc nhất quán khi checkpoint đang được tạo. |

Trong cấu hình thông thường, journal files nằm tại thư mục **journal** dưới **dbPath**, có dạng tên như **WiredTigerLog.0000000001**. MongoDB tự quản lý, tạo và dọn các journal file cũ khi không còn cần cho recovery. **Không xóa hoặc chỉnh tay các tệp WiredTigerLog** để giải phóng dung lượng.

### 2.3. Journal MongoDB không phải application log hay oplog

Ba loại log có mục đích riêng:

| Loại | Nơi sử dụng | Có tác dụng gì? |
|---|---|---|
| **WiredTiger journal** | Storage engine ở từng instance. | Phát lại thay đổi cục bộ sau crash giữa các checkpoint. |
| **Replication oplog** | Collection **local.oplog.rs** của các thành viên replica set. | Cung cấp chuỗi thao tác để các member đồng bộ dữ liệu và làm cơ sở cho một số hình thức backup/PITR. |
| **MongoDB server log** | File log/console của **mongod**. | Ghi sự kiện vận hành, thông báo, cảnh báo, lỗi. |

Không được lấy server log thông thường để phát lại dữ liệu, cũng không xem journal như changelog nghiệp vụ phục vụ audit. Journal có định dạng và vòng đời nội bộ do MongoDB kiểm soát.

## 3. Journal (write-ahead logging) hoạt động ra sao?

### 3.1. Ý tưởng write-ahead log

**Write-ahead logging** cho phép storage engine làm việc hiệu quả trong RAM nhưng vẫn giữ một đường khôi phục có thể tin cậy. Với thao tác cập nhật document và index liên quan, WiredTiger tạo journal record thể hiện những thay đổi cần thiết. Các record ban đầu có thể nằm trong **journal buffer**, sau đó được ghi/sync tới journal trên đĩa.

Mô hình khái niệm:

~~~text
T0: Ứng dụng yêu cầu cập nhật
           |
           v
T1: WiredTiger xử lý thay đổi; tạo record trong journal buffer
           |
           +------> Dirty data/pages có thể đang nằm trong cache
           |
           v
T2: Journal record được flush/sync xuống đĩa
           |
           +------> Đủ cơ sở khôi phục thay đổi đã journal
           |
           v
T3: Checkpoint sau đó ghi snapshot nhất quán vào data files
           |
           +------> Checkpoint mới có thể trở thành mốc recovery
~~~

Điều quan trọng là **thời điểm client nhận acknowledgment không cố định bằng T2 hoặc T3**. Nó được quyết định bởi write concern và điều kiện thực tế. Một write chưa yêu cầu journal acknowledgment có thể được trả lời khi record vẫn chưa bền vững trên đĩa.

### 3.2. Journal được đồng bộ lúc nào?

Với WiredTiger, MongoDB có cơ chế sync journal định kỳ. Theo tài liệu MongoDB, chu kỳ mặc định của **storage.journal.commitIntervalMs** là khoảng **100 ms**; một số điều kiện có thể kích hoạt sync sớm hơn, điển hình là thao tác yêu cầu **write concern j: true**. Với secondary, cơ chế apply các lô oplog cũng tác động đến việc sync journal.

Điều đó dẫn đến một nguyên tắc:

**Một write mới chỉ ở bộ nhớ/journal buffer vẫn có thể mất khi xảy ra hard shutdown; một write đã được sync vào journal có cơ sở để phục hồi khi data files và journal vẫn nguyên vẹn.**

100 ms là **khoảng cấu hình mặc định của cơ chế flush**, không phải SLA rằng mọi thao tác đã bền vững chính xác trong 100 ms, cũng không phải thời gian khôi phục tối đa. Độ trễ đồng bộ thực tế còn phụ thuộc tải I/O và phần cứng.

### 3.3. Mỗi journal record chứa gì?

Một thao tác ghi của client có thể làm thay đổi không chỉ document mà cả index. Journal record của WiredTiger bao gồm các thay đổi nội bộ cần thiết gắn với thao tác đó. Nhờ vậy, recovery có thể đưa dữ liệu và index về trạng thái nhất quán tương ứng, thay vì chỉ phát lại một biểu thức update bề ngoài.

Chẳng hạn:

~~~javascript
db.customers.createIndex({ email: 1 }, { unique: true })

db.customers.insertOne({
  _id: "C-101",
  email: "lan@example.test",
  status: "ACTIVE"
})
~~~

Insert này ảnh hưởng đến dữ liệu collection và index **email**. WiredTiger journaling gắn các thay đổi storage cần thiết cho thao tác để recovery tái lập chúng nhất quán.

### 3.4. Journal không được giữ mãi

Checkpoint tiến triển thì các thay đổi trước mốc checkpoint không cần được giữ lại vô hạn trong journal để khôi phục từ mốc mới. MongoDB quản lý rotation và thu dọn log segment không còn cần thiết. Không thể dựa vào journal để tìm lại một trạng thái dữ liệu tùy ý từ nhiều ngày trước.

**Journal không phải lịch sử phiên bản dài hạn và không phải backup.**

## 4. Checkpoint: trạng thái dữ liệu nhất quán trên đĩa

### 4.1. Checkpoint giải quyết vấn đề nào?

Nếu chỉ có journal mà không có mốc dữ liệu nhất quán, mỗi lần khởi động lại có thể phải phát lại lịch sử rất dài. **Checkpoint** ghi snapshot dữ liệu nhất quán vào data files để rút ngắn phạm vi khôi phục và tạo một điểm xuất phát đáng tin cậy.

MongoDB cấu hình WiredTiger tạo checkpoint theo chu kỳ khoảng **60 giây**. Đây là nhịp mặc định của việc tạo checkpoint, không có nghĩa là mỗi 60 giây toàn bộ database được sao lưu ra một file độc lập, hay mọi write phải đợi tối đa 60 giây mới bền vững.

### 4.2. Snapshot và tính nhất quán

WiredTiger sử dụng MVCC để nhìn dữ liệu tại một thời điểm logic nhất định. Khi checkpoint hoàn thành, trạng thái lưu trên đĩa phải nhất quán theo snapshot đó. Điều này khác với việc sao chép ngẫu nhiên các tệp đang biến đổi trong lúc database chạy: những file được copy ở những thời điểm khác nhau có thể không cùng thuộc một trạng thái nhất quán.

~~~text
Checkpoint A (hợp lệ)
      |
      |    WiredTiger ghi các trang của checkpoint B
      |         [đang tiến hành]
      |                X  crash
      v
Recovery vẫn có thể bắt đầu từ checkpoint A
và replay journal phù hợp.

Checkpoint A (hợp lệ)
      |
      |   Ghi checkpoint B hoàn tất
      |   Metadata chuyển sang B một cách nguyên tử
      v
Checkpoint B (hợp lệ mới)
~~~

Trong thời gian checkpoint mới được tạo, checkpoint cũ vẫn có hiệu lực. Khi dữ liệu và metadata của checkpoint mới đã được ghi thành công, WiredTiger cập nhật metadata để trỏ tới mốc mới. Nếu crash xảy ra trong lúc xây dựng checkpoint, cơ chế này tránh phụ thuộc vào một checkpoint mới chưa hoàn chỉnh.

### 4.3. Checkpoint không có nghĩa dữ liệu sau mốc đó biến mất

Ví dụ:

~~~text
09:00:00   Checkpoint C0 hoàn tất
09:00:15   Update đơn hàng #A -> PAID, journal đã sync
09:00:40   Insert đơn hàng #B, journal đã sync
09:00:48   mongod crash
09:01:10   mongod khởi động lại
~~~

Nếu tệp dữ liệu và journal vẫn lành lặn, MongoDB có thể khởi tạo từ C0 và **replay các record sau C0 đã được journal bền vững**. Không có quy tắc rằng mọi thao tác từ 09:00:00 đến 09:00:48 đều bị mất chỉ vì checkpoint kế tiếp chưa chạy.

Ngược lại, nếu một thao tác được ứng dụng xác nhận nhưng **chưa bền vững vào journal** theo write concern đã dùng, crash vẫn có thể làm mất thao tác đó. Phải phân biệt **thời điểm acknowledgment** với **thời điểm journal sync**.

### 4.4. Checkpoint khác backup snapshot

Checkpoint là **cơ chế nội bộ của storage engine**, nằm trong hệ thống dữ liệu đang chạy. Backup snapshot là **bản sao dữ liệu được quản lý độc lập** nhằm khôi phục sau sự cố mất hoặc hỏng môi trường gốc. Không thể gọi checkpoint là bản backup để đem restore trên hệ thống khác mà không tuân thủ phương pháp backup MongoDB hỗ trợ.

## 5. Crash recovery: MongoDB phục hồi như thế nào?

**Crash recovery** là quá trình tự động tái tạo một trạng thái lưu trữ hợp lệ khi MongoDB khởi động lại sau khi dừng bất thường. Với WiredTiger, logic chính như sau:

1. Đọc metadata/data files để xác định **checkpoint hợp lệ gần nhất**.
2. Tìm vị trí journal record tương ứng với checkpoint đó.
3. **Replay** các thay đổi có trong journal cần áp dụng kể từ checkpoint.
4. Đưa storage engine trở lại trạng thái nhất quán để MongoDB có thể tiếp tục hoạt động.

~~~mermaid
flowchart TD
    A["mongod khởi động sau crash"] --> B["Xác định checkpoint cuối hợp lệ"]
    B --> C["Tìm bản ghi journal tương ứng"]
    C --> D["Replay thay đổi cần thiết sau checkpoint"]
    D --> E["Khôi phục trạng thái storage nhất quán"]
    E --> F["MongoDB hoàn tất khởi động để phục vụ request"]
~~~

Phần trên mô tả recovery storage cục bộ. Trong **replica set**, node còn có quá trình khôi phục trạng thái replication, xác định vai trò, đồng bộ và có thể áp dụng những thao tác khác theo trạng thái của tập sao chép. Vì vậy việc mongod khởi động và journal replay thành công **không đồng nghĩa node đó lập tức trở thành primary**.

### 5.1. Những tình huống điển hình

| Tình huống lúc xảy ra lỗi | Hành vi/kỳ vọng khôi phục |
|---|---|
| Dirty data chỉ còn trong RAM; journal record chưa sync. | Thay đổi chưa bền vững có thể mất sau hard crash. |
| Thay đổi đã sync vào journal nhưng chưa nằm trong checkpoint. | Recovery có thể replay record để khôi phục thay đổi. |
| Crash ngay lúc checkpoint mới đang ghi. | Dùng checkpoint cũ còn hợp lệ, sau đó replay journal phù hợp. |
| Checkpoint mới đã được ghi và metadata cập nhật thành công. | Mốc checkpoint mới được dùng, cần replay các thay đổi sau mốc đó. |
| Dừng bình thường (graceful shutdown). | Server có cơ hội hoàn tất các công việc đóng an toàn; lần khởi động sau thông thường thuận lợi hơn so với crash. |
| Mất/hỏng cả data files và journal, hoặc lỗi lưu trữ nghiêm trọng. | Crash recovery không đảm bảo khôi phục; cần replica khác và/hoặc backup hợp lệ. |

Các kết quả trên giả định thiết bị lưu trữ, hệ điều hành và việc sync cung cấp đặc tính bền vững như mong đợi. Lỗi phần cứng, mất toàn bộ ổ đĩa, ghi dữ liệu sai hoặc dữ liệu bị phá hủy có thể vượt quá phạm vi của WAL.

### 5.2. “Khôi phục sau sự cố” không có nghĩa “không mất một thao tác nào”

Số lượng thao tác có thể mất không thể suy ra chỉ từ checkpoint interval. Để xác định bảo đảm cho một write cụ thể, cần xem:

- Write đó đã được **acknowledge** theo write concern nào?
- Có yêu cầu **j: true** hay không?
- Chỉ một node bị crash, hay cả nhóm replica set gặp lỗi?
- Đĩa và journal có còn toàn vẹn không?
- Có xảy ra **election/rollback** sau khi node được khởi động lại không?

Điều kiện “MongoDB dùng journal mặc định” khác với điều kiện “mọi request đều được xác nhận sau khi journal bền vững”. Chính sách acknowledgment quyết định điều ứng dụng được quyền giả định.

## 6. Write concern quyết định khi nào client được báo thành công

MongoDB cung cấp **write concern** để ứng dụng mô tả mức xác nhận ghi mong muốn. Hai yếu tố quan trọng là:

- **w:** số lượng/thành viên replica set phải xác nhận thao tác, hoặc quy tắc **majority**.
- **j:** có yêu cầu chờ xác nhận đã ghi bền vững vào **on-disk journal** hay không.

### 6.1. Bảng mức bảo đảm thường gặp

| Write concern | Mong muốn | Lưu ý |
|---|---|---|
| **{ w: 1 }** | Primary xác nhận ghi theo cơ chế của nó. | Nếu không yêu cầu journal acknowledgment, một write được xác nhận có thể chưa được sync vào journal; cũng có nguy cơ rollback khi đổi primary. |
| **{ w: 1, j: true }** | Chờ ghi bền vững ở journal trên node xác nhận. | Bảo vệ tốt hơn trước crash **cục bộ của node đó**; không bảo đảm chống mất ổ đĩa hoặc rollback do replica set election. |
| **{ w: "majority" }** | Chờ quy tắc majority trong replica set. | Mặc định liên quan đến journal phụ thuộc **writeConcernMajorityJournalDefault**; cấu hình thông thường là **true**, khiến majority acknowledgment chờ mức journal phù hợp. |
| **{ w: "majority", j: true }** | Yêu cầu rõ cả mức majority và journal durability. | Phù hợp khi nghiệp vụ cần bảo vệ dữ liệu tốt hơn trước failover; có thể tăng độ trễ hoặc timeout khi không đủ node/đĩa chậm. |

**Hai câu hỏi khác nhau:** **w** trả lời “cần bao nhiêu node xác nhận?”, còn **j** trả lời “đã được ghi bền vững vào journal chưa?”. Chỉ **j: true** trên một primary không đảm bảo majority replication; chỉ có nhiều replica cũng không tự khẳng định mọi ACK đều đã journaled trên tất cả node.

### 6.2. Ví dụ insert với journaling acknowledgment

Trên một MongoDB standalone hoặc node thích hợp, thử insert qua mongosh:

~~~javascript
use journal_lab

db.orders.insertOne(
  {
    _id: "ORD-J-001",
    customerId: "CUS-100",
    status: "CREATED",
    amount: 450000
  },
  {
    writeConcern: {
      w: 1,
      j: true,
      wtimeout: 5000
    }
  }
)
~~~

Trong ví dụ này, **j: true** yêu cầu acknowledgment sau khi write đã được đồng bộ bền vững vào journal theo quy tắc của MongoDB. Đây là ví dụ **local durability**, không phải lời hứa về high availability. Nếu service cần chịu lỗi primary và đang kết nối replica set, có thể yêu cầu rõ majority:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-J-001" },
  { $set: { status: "PAID" } },
  {
    writeConcern: {
      w: "majority",
      j: true,
      wtimeout: 5000
    }
  }
)
~~~

**wtimeout** giới hạn thời gian đợi write concern. Nếu client gặp **writeConcernError** hoặc timeout, không được suy ra máy chủ chắc chắn chưa thực hiện thao tác: thay đổi có thể đã được áp dụng nhưng chưa đạt đủ điều kiện xác nhận. Khi retry, nghiệp vụ cần ràng buộc unique, idempotency key hoặc một quy trình xác minh trạng thái thích hợp.

### 6.3. Cấu hình tại URI

Đối với một replica set tự quản lý, ứng dụng có thể cung cấp các tham số dưới dạng URI:

~~~text
mongodb://db1.example.test:27017,db2.example.test:27017,db3.example.test:27017/orders?replicaSet=rs0&w=majority&journal=true&retryWrites=true
~~~

Địa chỉ trên chỉ là **minh họa**. Trong Spring Boot, có thể đặt URI thực tế vào biến môi trường dùng bởi cấu hình ứng dụng:

~~~yaml
spring:
  data:
    mongodb:
      uri: ${MONGODB_URI}
~~~

Không hardcode tài khoản/mật khẩu vào repository. Phiên bản Spring Boot/MongoDB driver và cơ chế cấu hình có thể khác nhau; cần kiểm tra tại hệ thống đích. **journal=true** trong URI liên quan write concern, không phải công tắc bật/tắt storage-engine journaling.

### 6.4. Phân biệt write concern với read concern

**Read concern** quyết định mức nhất quán mà truy vấn đọc nhìn thấy, ví dụ **local** hoặc **majority** trong các trường hợp được hỗ trợ. Nó không thay thế yêu cầu journal của thao tác ghi. Nếu ứng dụng cần đọc lại chính dữ liệu vừa ghi khi có failover, phải xét đồng thời write concern, read concern, read preference và session semantics.

## 7. Journal, oplog và phục hồi trong replica set

Đây là điểm quan trọng trong kiến trúc MongoDB nhiều node:

~~~text
Ứng dụng
   |
   v
Primary mongod
   |          \
   |           +--> WiredTiger journal của PRIMARY
   |
   +--> replication oplog
             |
             v
      Secondary mongod
             |
             +--> WiredTiger journal của SECONDARY
~~~

**Mỗi thành viên** có storage engine, journal và checkpoint riêng. **Oplog** là cơ chế replication để secondaries sao chép thao tác từ primary; oplog không đồng nghĩa với journal. Replica set có thể tiếp tục cung cấp dịch vụ khi một node hỏng nhờ election/failover, trong khi journal giúp từng node phục hồi bản thân sau một crash cục bộ.

### 7.1. Hai trường hợp không được đánh đồng

**Trường hợp A — primary crash rồi khởi động lại, topology không thay đổi đáng kể:** storage engine của node dùng checkpoint/journal để khôi phục local data, sau đó node tiếp tục quá trình tham gia replica set theo trạng thái phù hợp.

**Trường hợp B — primary mất liên lạc, secondary được bầu làm primary mới:** ghi chỉ tồn tại ở primary cũ và chưa được replicate tới mức majority có thể bị **rollback** khi primary cũ trở lại. Dù write đó đã nằm trong **journal cục bộ** của primary cũ, replica set vẫn có thể loại bỏ nó để đồng bộ theo nhánh lịch sử được chấp nhận.

~~~text
T0: Node A là PRIMARY
T1: Client ghi X; A đã journal, nhưng X chưa đạt majority
T2: A mất kết nối
T3: Node B được bầu PRIMARY mới
T4: A trở lại, đồng bộ với lịch sử hợp lệ của replica set

=> X có thể bị rollback mặc dù journal cục bộ của A tồn tại.
~~~

Từ đây rút ra nguyên tắc thiết kế: **j: true không thể thay thế w: "majority" khi cần bảo vệ dữ liệu trước failover**. Đồng thời w: "majority" với đặc tính journal tùy cấu hình vẫn không thay thế backup trước lỗi người dùng hoặc lỗi lưu trữ diện rộng.

### 7.2. Tại sao “có ba node” chưa đủ để kết luận không mất dữ liệu?

Replica set ba data-bearing member thường cho phép bầu primary mới khi một node gặp lỗi, nhưng mức an toàn một write phụ thuộc thời điểm write đạt majority, journal và loại sự cố. Thêm replica là tăng khả năng sống sót và availability; việc API chấp nhận ghi có mức durability nào vẫn do write concern quyết định.

## 8. Journal và checkpoint trong sharded cluster

Ở sharded cluster, mỗi shard thường là một replica set có nhiều node. Do đó **mỗi mongod thuộc từng shard vẫn có journal/checkpoint riêng**. Config server replica set cũng có cơ chế lưu trữ và phục hồi của các member.

~~~text
                       mongos
                    /     |     \
                   v      v      v
                Shard A Shard B Shard C
                  |       |       |
               Replica Replica Replica
                 Set     Set     Set
                  |       |       |
           Mỗi mongod có WiredTiger journal/checkpoint
~~~

Khi một mongod trên shard gặp crash, node ấy có thể thực hiện WiredTiger recovery. Nhưng nếu một shard mất khả năng phục vụ, các truy vấn cần shard đó vẫn có thể thất bại dù các shard khác hoạt động. **Journal không định tuyến lại dữ liệu và không thay thế cơ chế replication trong từng shard.**

Ngoài ra, một thao tác nhiều shard có thể cần các cơ chế điều phối transaction của MongoDB. Không nên suy luận rằng “từng shard có checkpoint hợp lệ” tức là có thể ghép các bản copy ở những thời điểm khác nhau thành một **backup nhất quán toàn cluster**. Backup và restore sharded cluster cần công cụ/quy trình hỗ trợ trạng thái phân tán.

## 9. Khi nào crash recovery là đủ, khi nào cần backup?

Crash recovery tự động hữu ích đối với lỗi tiến trình/hệ điều hành khi phần cứng và các tệp storage còn lành lặn. Một số sự cố khác cần chiến lược phục hồi riêng:

| Sự cố | Journal + checkpoint | Cần bổ sung |
|---|---|---|
| **mongod crash**, ổ đĩa còn nguyên | Thông thường hỗ trợ recovery tự động khi khởi động lại. | Giám sát lỗi, khả năng restart, kiểm tra ứng dụng. |
| **Mất điện**, ổ đĩa và journal còn nhất quán | Có thể recovery theo mức write concern được bảo đảm. | Hạ tầng lưu trữ tin cậy, shutdown/restart chuẩn, kiểm thử. |
| **Một node replica set hỏng** | Hỗ trợ local recovery nếu node phục hồi. | Majority/quorum, failover, replacement và resync. |
| **Hỏng/mất ổ đĩa chứa data và journal** | Không thể bảo đảm phục hồi riêng từ dữ liệu đã mất. | Replica khỏe mạnh và/hoặc backup có thể restore. |
| **Delete nhầm, update sai logic** | Có thể ghi bền vững chính thay đổi sai đó. | Backup/PITR, quyền hạn, xác nhận thao tác nguy hiểm. |
| **Mã độc/ransomware, hỏng toàn môi trường** | Không giải quyết được mức độ phá hủy bên ngoài engine. | Backup cách ly, DR ở vùng/hạ tầng khác, kiểm thử restore. |
| **Cần trở về thời điểm trong quá khứ** | Journal không phải bộ lưu lịch sử lâu dài. | Backup + cơ chế point-in-time recovery phù hợp. |

### 9.1. Backup và point-in-time recovery

**Backup** là bản sao có thể phục hồi độc lập với dữ liệu đang chạy. **Point-in-time recovery (PITR)** là khả năng phục hồi gần đến một thời điểm xác định, thường dựa trên backup nền và lịch sử thay đổi phù hợp, ví dụ oplog trong quy trình backup replica set. Đây là bài toán khác với journal replay khi mongod restart.

Ví dụ: nhân viên vô tình xóa đơn hàng lúc 15:00 nhưng đến 15:10 mới phát hiện. Journal không có nhiệm vụ “hoàn tác” thao tác xóa đã hợp lệ; khi đã ghi bền vững, thao tác xóa sẽ được khôi phục như các ghi khác. Một kế hoạch backup/PITR mới phục vụ tình huống cần phục hồi dữ liệu **trước 15:00**.

### 9.2. RPO và RTO

- **RPO — Recovery Point Objective:** tối đa bao nhiêu dữ liệu/thời gian thay đổi mà doanh nghiệp chấp nhận mất.
- **RTO — Recovery Time Objective:** tối đa bao lâu dịch vụ được phép chưa khôi phục về trạng thái sử dụng được.

Hai chỉ số này quyết định mức đầu tư cho replication, backup frequency, off-site copies, PITR và quy trình diễn tập. Không thể tự tuyên bố RPO = 0 hoặc RTO = vài giây chỉ dựa vào mặc định journal 100 ms và checkpoint 60 giây.

### 9.3. Không sao chép tùy tiện thư mục dbPath đang chạy

Một bản copy các file data được thực hiện trong lúc mongod đang biến đổi có thể chụp các tệp ở những mốc không nhất quán. **Không dùng lệnh copy thư mục dbPath đang hoạt động như một phương án backup chuẩn** nếu không có cơ chế snapshot/backup MongoDB hỗ trợ và yêu cầu khóa/quiesce/phối hợp phù hợp.

Với MongoDB Atlas, các loại deployment và gói dịch vụ cung cấp những tính năng backup, restore và PITR khác nhau; cần xác nhận khả năng thực tế của cấu hình được dùng. Với hệ tự quản lý, chọn công cụ và quy trình backup được MongoDB hỗ trợ, sau đó **thử restore** để xác minh backup có giá trị.

## 10. Quan sát journal và checkpoint bằng công cụ MongoDB

### 10.1. Kiểm tra serverStatus

Trên một instance WiredTiger có quyền phù hợp, chạy trong mongosh:

~~~javascript
const stats = db.serverStatus()

printjson(stats.storageEngine)
printjson(stats.wiredTiger?.log)
printjson(stats.wiredTiger?.transaction)
~~~

Đối tượng **wiredTiger.log** chứa thống kê liên quan journaling/logging; **wiredTiger.transaction** có thể chứa thống kê liên quan transaction/checkpoint. **Tên field chi tiết và khả năng xuất hiện phụ thuộc phiên bản MongoDB**, nên nên xem toàn bộ object thay vì mã hóa cứng một field chưa xác minh.

Có thể kiểm tra cấu hình khởi động server:

~~~javascript
db.adminCommand({ getCmdLineOpts: 1 })
~~~

Kết quả có thể phản ánh các giá trị cấu hình do tiến trình nhận lúc khởi động, nhưng không nên suy ra mọi mặc định đều được in ra. Trong môi trường production, các metric còn cần kết hợp với hệ giám sát, log hệ thống và tình trạng I/O.

### 10.2. Các tín hiệu cần theo dõi

| Tín hiệu | Ý nghĩa và cách đọc |
|---|---|
| **Journal sync / log write activity** | Lưu lượng journaling và chi phí ghi log; bất thường có thể liên quan workload hoặc I/O. |
| **Checkpoint duration / checkpoint activity** | Checkpoint kéo dài có thể cần khảo sát storage throughput, dirty cache và tải chung. |
| **WiredTiger cache / dirty bytes** | Áp lực trên cache và lượng dữ liệu đang chờ được ghi vào data files. |
| **Disk latency và IOPS** | Tác động đến journal sync, checkpoint và thời gian xác nhận write concern. |
| **Disk free space** | Journal và data files đều cần dung lượng; hết đĩa có thể làm dịch vụ ngừng hoạt động. |
| **Replication lag, majority write latency** | Bổ sung góc nhìn độ trễ và khả năng xác nhận ghi khi chạy replica set. |
| **Startup/recovery logs** | Giúp xác định server đang crash recovery, khởi tạo storage hay gặp lỗi nghiêm trọng. |

Không nên chỉ quan sát một con số journal log size để kết luận hệ thống an toàn. Dung lượng journal thay đổi theo tốc độ ghi, thời gian checkpoint, compression và thao tác recovery.

### 10.3. Cấu hình và hiệu năng

MongoDB cho phép cấu hình **storage.journal.commitIntervalMs** trong những điều kiện được hỗ trợ. Giảm khoảng commit có thể làm tăng tần suất I/O; tăng khoảng commit có thể tăng cửa sổ những write chưa được journal sync nếu ứng dụng không yêu cầu **j: true**. Việc thay đổi tham số này phải dựa vào workload, độ bền yêu cầu và tài liệu phiên bản.

**Lưu ý về phiên bản:** từ **MongoDB 6.1**, journaling được bật thường trực trong các cấu hình liên quan; tùy chọn **storage.journal.enabled** cùng các cờ **--journal** và **--nojournal** đã bị loại bỏ. Không dùng hướng dẫn cũ yêu cầu “bật journaling bằng --journal” cho các bản phát hành hiện đại.

## 11. Ví dụ thực hành an toàn

Bài lab dưới đây chỉ quan sát dữ liệu và thống kê của **mongod local**; không cần gây crash thật cho môi trường đang chạy.

### 11.1. Khởi động một instance dành riêng cho lab

Ví dụ trên Linux/macOS (cần cài MongoDB Server và mongosh):

~~~bash
mkdir -p ./mongo-journal-lab
mongod --dbpath ./mongo-journal-lab --port 27019 --bind_ip 127.0.0.1
~~~

Mở terminal khác:

~~~bash
mongosh "mongodb://127.0.0.1:27019"
~~~

Trên Windows có thể tạo một thư mục dữ liệu tương ứng và chạy mongod bằng đường dẫn phù hợp. **127.0.0.1** ở ví dụ giúp hạn chế truy cập từ máy khác; lab không đại diện cho cấu hình bảo mật production.

### 11.2. Ghi dữ liệu với journal acknowledgment

~~~javascript
use journal_lab

db.events.insertOne(
  {
    _id: "EVT-001",
    type: "PAYMENT_RECEIVED",
    amount: 200000,
    createdAt: new Date()
  },
  { writeConcern: { w: 1, j: true, wtimeout: 5000 } }
)

db.events.findOne({ _id: "EVT-001" })

db.serverStatus().wiredTiger.log
~~~

Lệnh insert yêu cầu acknowledgment gắn với journal local. Quan sát phần log statistics giúp nhận biết WiredTiger đang duy trì cơ chế journaling, nhưng **không chứng minh một thao tác cụ thể sẽ sống sót qua mọi loại sự cố**.

### 11.3. Đọc lại sau shutdown bình thường

Đóng **mongod** bằng cách graceful shutdown theo cách phù hợp với môi trường đang chạy, rồi khởi động lại instance trên **cùng thư mục dbPath**. Kết nối lại:

~~~javascript
db.getSiblingDB("journal_lab").events.findOne({ _id: "EVT-001" })
~~~

Document phải tiếp tục tồn tại nếu thao tác đã được hoàn thành đúng và không có thay đổi/xóa sau đó. Đây chỉ là kiểm tra cơ bản sau restart; **shutdown bình thường không phải phép thử crash recovery**.

Nếu muốn nghiên cứu recovery sau kill/process crash, chỉ thực hiện ở **môi trường thí nghiệm hoàn toàn riêng**, có dữ liệu không quan trọng, snapshot/backup và quyền quản lý tiến trình; không thử dừng cưỡng bức trên server thật.

### 11.4. Thử thay đổi write concern để hiểu ý nghĩa

So sánh logic, không cần đo tốc độ từ một request đơn lẻ:

~~~javascript
const database = db.getSiblingDB("journal_lab")

database.events.insertOne(
  { _id: "EVT-W1", type: "NORMAL" },
  { writeConcern: { w: 1 } }
)

database.events.insertOne(
  { _id: "EVT-J", type: "JOURNALED" },
  { writeConcern: { w: 1, j: true } }
)
~~~

Hai write đều có thể thành công. Khác biệt là **điều kiện acknowledgment**, không phải định dạng document. Không nên khẳng định write có **w: 1** chắc chắn bị mất khi crash; nó **có khả năng** chưa journal sync vào đúng thời điểm gặp lỗi.

## 12. Các tình huống phân tích lỗi thực tế

### 12.1. Một write trả về success nhưng không thấy sau khi máy khởi động lại

Hướng phân tích:

1. Kiểm tra write concern của thao tác: **w: 1**, **j** đã yêu cầu hay chưa.
2. Xác minh mongod có crash cục bộ, mất điện hay chuyển primary.
3. Nếu replica set có election, xác định write đã đạt **majority** hay có thể bị rollback.
4. Xác minh client có đang đọc từ secondary bị lag hoặc môi trường/cluster khác không.
5. Phân tích logs, trạng thái replication và bằng chứng ứng dụng; không kết luận “journal hỏng” chỉ từ kết quả query thiếu dữ liệu.

### 12.2. Máy chủ restart lâu hơn dự kiến

Trong quá trình khởi động, recovery có thể cần xử lý journal, khôi phục storage metadata và trạng thái replication. Thời gian bị ảnh hưởng bởi khối lượng ghi chưa checkpoint, tốc độ I/O, workload và tình trạng dữ liệu/đĩa. Kiểm tra startup logs, disk health, thời gian chờ driver và trạng thái node thay vì suy đoán từ mốc checkpoint mặc định.

### 12.3. Journal files chiếm nhiều dung lượng

MongoDB tạo và dọn journal files theo nhu cầu. Tăng trưởng log có thể liên quan tốc độ ghi lớn, checkpoint và quá trình recovery. **Không xóa file trực tiếp** vì có thể phá khả năng recovery. Trước tiên kiểm tra disk free space, hoạt động WiredTiger, checkpoint, lỗi I/O và hướng dẫn vận hành phù hợp.

### 12.4. Cả primary và secondary đều đồng bộ một thao tác xóa nhầm

Replica set và journal thực hiện đúng vai trò khi lưu giữ và replicate thao tác. Để phục hồi dữ liệu trước lúc xóa, cần backup hoặc PITR. Đây là lý do phải thiết kế chính sách backup độc lập với replication.

## 13. Các nguyên tắc vận hành quan trọng

1. **Không tắt journaling để “tăng tốc” theo tài liệu cũ.** Với MongoDB từ 6.1, journaling được bật thường trực trong những cấu hình tương ứng; hãy tối ưu index, query, schema và storage trước.
2. **Chọn write concern theo yêu cầu nghiệp vụ.** Ghi dữ liệu quan trọng trong replica set thường cần xem xét **w: "majority"** và mức journal durability tương ứng.
3. **Không dựa vào một node duy nhất để đáp ứng HA.** Journal giúp một node tự phục hồi, không có khả năng tự tạo node dự phòng.
4. **Dùng backup có thể phục hồi và thử restore.** Journal/replication không bảo vệ đầy đủ trước mất ổ đĩa, xóa nhầm hay sự cố diện rộng.
5. **Đảm bảo đủ dung lượng và I/O.** Journal sync và checkpoint đều cần storage ổn định; thiếu dung lượng có thể khiến mongod gặp sự cố.
6. **Giám sát latency, checkpoint và replication.** Không chỉ quan sát CPU/RAM; vấn đề durability thường thể hiện ở storage và điều kiện ghi.
7. **Thiết kế retry có idempotency.** Khi timeout, kết quả thao tác có thể chưa chắc chắn; retry mù dễ dẫn tới trùng đơn hàng, trùng giao dịch hay cập nhật hai lần.
8. **Kiểm thử theo RPO/RTO.** Khả năng recovery chỉ có ý nghĩa khi đã đo trong môi trường tương đồng thực tế.

## 14. Những nhầm lẫn phổ biến

**“Checkpoint 60 giây nghĩa là MongoDB có thể mất 60 giây dữ liệu.”** Không đúng. Checkpoint tạo mốc data files; journal có thể bảo vệ các thay đổi sau checkpoint. Mức mất dữ liệu phụ thuộc thao tác nào đã journal bền vững và write concern.

**“Journal chạy mỗi 100 ms nghĩa là mọi write đều được xác nhận sau 100 ms.”** Không đúng. 100 ms là chu kỳ đồng bộ mặc định, không phải quy tắc ACK cho tất cả write hoặc thời gian phản hồi cố định.

**“Có journal là không cần backup.”** Sai. Journal phục vụ recovery cục bộ từ checkpoint, không phục vụ restore dữ liệu bị xóa nhầm hoặc bị mất cả thiết bị lưu trữ.

**“Một write có j: true chắc chắn không rollback khi bầu primary mới.”** Sai. Journal chỉ xác lập độ bền cục bộ của write; replica set vẫn có thể rollback write chưa được xác nhận theo majority phù hợp.

**“Oplog chính là journal.”** Sai. Oplog phục vụ replication, trong khi WiredTiger journal phục vụ crash recovery trên từng node.

**“Crash trong lúc checkpoint đang ghi sẽ làm toàn bộ database hỏng.”** Không phải hành vi mong đợi. WiredTiger bảo toàn checkpoint trước đó cho đến khi checkpoint mới được hoàn tất và metadata được cập nhật hợp lệ.

**“Có nhiều shard thì chỉ cần backup từng shard vào bất kỳ thời điểm nào.”** Sai. Backup toàn cluster cần dữ liệu và metadata có quan hệ nhất quán theo thời điểm; sharding làm vấn đề backup phân tán phức tạp hơn.

## 15. Bài tập tư duy và câu hỏi tự kiểm tra

**Bài tập 1 — Thời điểm crash:** checkpoint lúc 10:00:00, write A ở 10:00:20 đã sync journal, write B ở 10:00:21 chỉ mới được xử lý trong bộ nhớ, mongod crash ở 10:00:22. Hãy giải thích vì sao A có cơ sở được replay nhưng B có thể mất.

**Bài tập 2 — Giao dịch đơn hàng:** API tạo đơn hàng cần tránh mất dữ liệu khi primary lỗi và ứng dụng nhận retry. Hãy đề xuất write concern, unique business identifier và cách xử lý trạng thái timeout chưa rõ kết quả.

**Bài tập 3 — Khôi phục lỗi người dùng:** một operator chạy update sai làm đổi giá của 10.000 sản phẩm. Giải thích tại sao checkpoint/journal không tự đưa giá trở về ban đầu và nên sử dụng backup/PITR như thế nào.

**Bài tập 4 — Chỉ số vận hành:** khi write latency tăng, bạn quan sát những chỉ số nào để phân biệt bottleneck journal sync, checkpoint, replication majority và client connection pool?

**Bài tập 5 — Chọn công cụ:** với mỗi sự cố **mongod crash**, **mất một primary**, **mất cả ổ đĩa** và **delete nhầm 2 giờ trước**, hãy xác định vai trò của journal, checkpoint, replica set và backup.

## 16. Tổng kết mô hình ghi nhớ

~~~text
             WRITE của ứng dụng
                     |
               WiredTiger cache
                     |
              Journal record
                     |
       j: true yêu cầu journal durability
                     |
                     v
               Journal trên đĩa
                     |
         Checkpoint định kỳ ~60 giây
                     |
                     v
          Data files ở trạng thái
              nhất quán mới

CRASH:
  checkpoint cuối hợp lệ + journal replay => recovery cục bộ

FAILOVER:
  replica set + majority semantics       => duy trì service/bảo vệ ghi

MẤT DỮ LIỆU/VÙNG:
  backup + restore/PITR                  => phục hồi độc lập
~~~

**Journal** bảo vệ những thay đổi đã được ghi bền vững giữa các checkpoint; **checkpoint** cung cấp mốc dữ liệu nhất quán để recovery bắt đầu. Hai cơ chế kết hợp giúp WiredTiger phục hồi sau crash, nhưng việc ứng dụng nhận đảm bảo gì còn phụ thuộc **write concern**, topology, thiết bị lưu trữ và loại sự cố.

### Tài liệu MongoDB chính thức để đọc tiếp

- [Journaling](https://www.mongodb.com/docs/manual/core/journaling/) — cách hoạt động của journal, thời điểm sync, vòng đời journal files.
- [WiredTiger Storage Engine](https://www.mongodb.com/docs/manual/core/wiredtiger/) — MVCC, snapshots, checkpoints và journal.
- [Configure Journaling for Self-Managed Deployments](https://www.mongodb.com/docs/manual/tutorial/manage-journaling/) — cấu hình và durability.
- [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — các mức acknowledgment, j và majority.
- [Write Operation Performance](https://www.mongodb.com/docs/manual/core/write-performance/) — mối liên hệ giữa journaling, I/O và hiệu năng ghi.

Khi áp dụng vào hệ thống thực tế, luôn đối chiếu tài liệu của **phiên bản MongoDB đang vận hành**, cấu hình replica set/sharding và khả năng backup cụ thể của môi trường.
