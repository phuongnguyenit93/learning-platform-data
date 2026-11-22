# Majority commit point và nguy cơ rollback sau sự cố trong MongoDB Replica Set

## 1. Một lệnh ghi thành công có đồng nghĩa dữ liệu sẽ sống sót sau failover?

Giả sử một ứng dụng đặt hàng ghi vào MongoDB:

~~~javascript
db.orders.insertOne({
  _id: "order-1001",
  tenantId: "t001",
  status: "created",
  amount: NumberDecimal("200.00")
});
~~~

Lệnh trả về kết quả thành công. Một giây sau, primary của **replica set** mất kết nối; các secondary bầu primary mới. Khi ứng dụng đọc lại, đơn hàng vừa tạo **không còn tồn tại**.

Điều này có thể xảy ra nếu lệnh ghi chỉ được xác nhận ở primary nhưng chưa trở thành một phần của lịch sử **đã được đa số thành viên sao chép (majority-committed)**. Khi một primary khác được bầu, những thao tác ghi nằm trên nhánh lịch sử không được chọn có thể phải **rollback**.

Bài này phân biệt bốn khái niệm rất dễ bị nhầm:

1. **Primary đã nhận/áp dụng ghi**: thao tác tồn tại trên primary tại thời điểm đó.
2. **Client đã nhận acknowledgment**: tùy **write concern**, đây có thể chỉ là xác nhận từ primary.
3. **Majority commit point đã đi qua thao tác ghi**: thao tác thuộc phần lịch sử oplog được đa số bản sao đủ điều kiện xác nhận.
4. **Ứng dụng quan sát được dữ liệu sau failover**: phụ thuộc commit, trạng thái replication, read concern và nơi đọc.

**Thông điệp chính:** một kết quả acknowledged với **w:1** không bảo đảm đã majority-committed. Một write được xác nhận thành công với **w:"majority"** có khả năng chống rollback trong các tình huống failover replica set thông thường, với các giả định triển khai và lưu trữ đúng.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích **oplog**, **optime**, **majority commit point** và quá trình election.
- Vẽ hai kịch bản: write **chưa majority-committed bị rollback** và write **đã majority-committed sống sót** sau failover bình thường.
- Phân biệt **w:1**, **w:"majority"**, **j:true** và **wtimeout**.
- Hiểu vì sao **writeConcernError** không đồng nghĩa “lệnh ghi chắc chắn chưa xảy ra”.
- Phân biệt **readConcern "local"**, **"majority"**, **"snapshot"** và tính mới nhất của kết quả.
- Quan sát **lastCommittedOpTime**, trạng thái thành viên và replication lag bằng các lệnh chỉ đọc.
- Thiết kế xử lý retry/idempotency và transaction phù hợp với yêu cầu chống rollback.
- Nhận diện giới hạn của majority trong tình huống mất quorum, sai cấu hình và sự cố nghiêm trọng ngoài failover bình thường.

> Các ví dụ chỉ minh họa trên **replica set thực hành**, tuyệt đối không cố tình tắt node, cắt mạng hoặc chạy các lệnh thay đổi cấu hình trên môi trường dùng chung. Phần rollback được trình bày bằng dòng thời gian và phân tích; bài lab thực hành bình thường không chủ động gây sự cố.

## 2. Cấu trúc replica set và replication

### 2.1. Primary, secondary và oplog

**Replica set** là nhóm các tiến trình MongoDB cùng duy trì những bản sao của một tập dữ liệu logic. Với mô hình điển hình ba thành viên có dữ liệu:

~~~text
                  Client ứng dụng
                        |
                ghi vào Primary P
                        |
                 +------+------+
                 |             |
                 v             v
           Secondary S1   Secondary S2
              sao chép       sao chép
              oplog          oplog
~~~

**Primary** thường nhận các thao tác ghi của ứng dụng. Những thay đổi được ghi vào **oplog** (operation log) theo thứ tự; **secondary** đọc và áp dụng các entry để duy trì bản sao dữ liệu.

Oplog không phải một nhật ký audit nghiệp vụ vô hạn. Nó là một cấu trúc replication có giới hạn lưu trữ và vòng đời riêng. Khi các node phân kỳ do failover, oplog là một thành phần quan trọng để xác định phần lịch sử chung và những thao tác phải đồng bộ hoặc rollback.

### 2.2. Ba trạng thái không đồng nghĩa

Giả sử một thao tác ghi tạo ra oplog entry **E101**. Nó có thể đi qua những giai đoạn khái niệm:

~~~text
Thời điểm A:
  Primary P  : ... E100 E101
  Secondary S1: ... E100
  Secondary S2: ... E100

Thời điểm B:
  Primary P  : ... E100 E101
  Secondary S1: ... E100 E101
  Secondary S2: ... E100

Thời điểm C:
  Primary P  : ... E100 E101
  Secondary S1: ... E100 E101
  Secondary S2: ... E100 E101
~~~

Ở **A**, chỉ primary có E101. Với ba thành viên có dữ liệu và quyền biểu quyết tương ứng, thao tác chưa đạt majority.

Ở **B**, P và S1 đã có E101; đây là **2/3** thành viên. Khi đáp ứng đúng các điều kiện replication/durability, entry có thể trở thành **majority-committed** dù S2 vẫn chưa nhận.

Ở **C**, cả ba đều đã có. Sao chép tới tất cả thành viên **không phải điều kiện bắt buộc** cho write concern majority trong cấu hình ba thành viên này.

**Replication là bất đồng bộ.** Phần mềm không thể giả định secondary đã nhận dữ liệu chỉ vì primary đã trả acknowledgment với w:1.

### 2.3. Optime và lịch sử oplog

MongoDB theo dõi vị trí các thao tác trong lịch sử replication bằng thông tin kiểu **OpTime**, thường gồm:

- **timestamp (ts)**: vị trí/thời điểm logic trong oplog.
- **term (t)**: nhiệm kỳ election gắn với lịch sử ghi.

Các thông tin như **appliedOpTime**, **durableOpTime**, **lastCommittedOpTime** giúp quan sát các mốc tương ứng; ý nghĩa và cấu trúc chi tiết tùy phiên bản MongoDB.

**Optime không đơn giản là thời gian đồng hồ treo tường của máy chủ.** Đừng lấy hai timestamp khác loại, trừ số mili giây rồi kết luận ngay “trễ chính xác N ms” nếu chưa hiểu chúng biểu diễn điều gì.

## 3. Majority commit point là gì?

### 3.1. Định nghĩa trực giác

**Majority commit point** là mốc oplog mới nhất mà MongoDB xem là đã được phần lớn các thành viên có quyền biểu quyết và lưu dữ liệu cần thiết sao chép, theo các quy tắc replication/durability của replica set.

Trong replica set ba data-bearing voting members:

~~~text
Primary P       : ... E100 E101 E102 E103
Secondary S1    : ... E100 E101 E102
Secondary S2    : ... E100 E101
                               ^
                             E101
~~~

Tại thời điểm giả định này:

- **E101** có mặt trên P, S1, S2.
- **E102** có mặt trên P và S1, đạt **2/3**.
- **E103** mới có trên P.

Giả sử các yêu cầu về tình trạng lưu bền vững tương ứng đều được đáp ứng, **majority commit point có thể ở E102**. E103 vẫn là thao tác **chưa majority-committed**.

~~~text
Oplog trên Primary:

... E100 -- E101 -- E102 || E103
                   ^
           majority commit point

Phía bên trái và tại mốc: lịch sử majority-committed.
Phía bên phải: ghi mới hơn có thể chưa đủ bản sao.
~~~

**Chú ý:** majority commit point là **mốc của một lịch sử oplog**, không phải số lượng document trong collection, không phải “lệnh mới nhất client đã nhận thành công”, và không nhất thiết trùng với điểm oplog mới nhất của primary.

### 3.2. Commit point có thể tiến dù ứng dụng dùng w:1

Giả sử client gửi E102 với write concern **w:1**. MongoDB có thể trả acknowledgment ngay sau khi primary áp dụng thao tác theo điều kiện w:1. Sau đó secondary tiếp tục sao chép E102; khi đủ majority, commit point tiến qua E102.

Vì vậy:

- **w:1 acknowledged** không chứng minh E102 đã majority-committed tại thời điểm response.
- Nhưng **w:1 không có nghĩa E102 chắc chắn sẽ bị rollback**. Nếu E102 kịp đến majority trước election, nó vẫn có thể sống sót.
- **w:"majority" acknowledged thành công** có ý nghĩa mạnh hơn: acknowledgment chờ điều kiện majority được đáp ứng theo cấu hình thực tế.

Write concern là **điều kiện xác nhận mà client yêu cầu**, còn majority commit point là **trạng thái replication của replica set**.

### 3.3. Vì sao đa số giúp chống rollback trong failover bình thường?

Các nhóm đa số trong cùng một cấu hình biểu quyết phải giao nhau ở ít nhất một thành viên. Với ba node P/S1/S2, hai tập 2/3 bất kỳ có ít nhất một thành viên chung.

Nếu E102 được majority-committed, một primary mới hợp lệ phải được bầu theo các quy tắc election và độ mới của lịch sử oplog. Trong failover bình thường, các quy tắc này bảo vệ lịch sử đã được majority-committed khỏi bị bỏ đi khi bầu primary mới.

~~~text
P : E100 E101 E102  (sau đó lỗi)
S1: E100 E101 E102  (có thể trở thành primary mới)
S2: E100 E101       (chưa có E102)

E102 đã majority-committed trên P + S1.

Sau election hợp lệ, lịch sử mới phải tiếp nối các thao tác
đã được majority-committed; S2 sẽ bắt kịp thay vì khiến E102 mất.
~~~

**Đây là bảo đảm dưới các điều kiện hệ thống bình thường**, không nên diễn giải thành “không thể mất dữ liệu trong mọi thảm họa”. Nếu mất dữ liệu vật lý trên đa số node, khôi phục sai snapshot, cấu hình bị can thiệp hoặc có sự cố vượt ngoài giả định, vẫn cần backup và quy trình phục hồi.

## 4. Một phép ghi có thể bị rollback như thế nào?

### 4.1. Kịch bản E201 chỉ có trên primary

Giả sử replica set ba thành viên P, S1, S2, ban đầu đều có lịch sử đến E200:

~~~text
Trước khi có sự cố:

P  (PRIMARY)    : E198 E199 E200 E201
S1 (SECONDARY)  : E198 E199 E200
S2 (SECONDARY)  : E198 E199 E200

E201 chỉ có trên P; chưa majority-committed.
~~~

Tình huống:

1. Client ghi E201 vào P với **w:1** và nhận acknowledged.
2. P bị cô lập hoặc mất khả năng phục vụ trước khi S1/S2 kịp sao chép E201.
3. S1 và S2 hình thành đa số và bầu primary mới theo quy tắc election.
4. Primary mới tiếp tục lịch sử không có E201, có thể tạo các entry mới ở một term mới.
5. Khi P trở lại, MongoDB phải giải quyết nhánh lịch sử khác nhau. E201 có thể bị **rollback** khỏi P để đồng bộ với lịch sử hợp lệ của primary mới.

~~~text
          Client nhận ACK từ P theo w:1
                         |
                         v
P :  ... E200 -- E201     X  (P mất liên lạc)
S1:  ... E200 -------------- E202 -- E203 (lịch sử mới)
S2:  ... E200 -------------- E202 -- E203

Khi P quay lại:
          E201 nằm trên nhánh phân kỳ
          -> có thể bị rollback
          -> P đồng bộ theo lịch sử mới
~~~

**Điểm quan trọng:** ứng dụng có thể đã nhận response thành công và thậm chí đọc lại E201 trên P **trước** khi sự cố xảy ra, nhưng response ấy chỉ phản ánh mức write concern đã yêu cầu.

### 4.2. Rollback là gì ở cấp dữ liệu?

Rollback là quá trình MongoDB loại bỏ ảnh hưởng của các thao tác nằm trên nhánh lịch sử không thuộc chuỗi oplog của primary hợp lệ mới, trong phạm vi và điều kiện MongoDB hỗ trợ.

Một thao tác có thể:

- **Insert** một document rồi document ấy biến mất sau rollback.
- **Update** một document và giá trị cũ được khôi phục tương ứng với lịch sử chung.
- **Delete** một document nhưng document được khôi phục trở lại theo lịch sử hợp lệ.

Trong ứng dụng, hiện tượng này có thể giống “đơn đã tạo bị mất”, “trạng thái vừa đổi bị quay lại” hoặc “document đã xóa xuất hiện lại”. Đây không nhất thiết là lỗi application cache; có thể là kết quả của replication history chưa majority-committed trước failover.

Không được giả định tất cả trường hợp rollback có thể dễ dàng khôi phục thủ công từ một file. Một số phiên bản/cấu hình có thể lưu dữ liệu phục vụ điều tra rollback tại thư mục riêng, nhưng nó **không phải bản backup đáng tin cậy** và không thay thế thiết kế write concern, log nghiệp vụ hoặc PITR.

### 4.3. Vì sao không phải mọi w:1 write đều rollback?

Giả sử E201 được acknowledged với w:1 nhưng sau đó P và S1 đều ghi nhận E201 trước khi P mất kết nối. Khi E201 đã đủ điều kiện đi qua majority commit point, nó có thể vẫn tồn tại qua election. **Cách client yêu cầu acknowledgment không tự khóa vĩnh viễn trạng thái replication của entry.**

Hai câu sau khác nhau:

1. “Ứng dụng **không có bảo đảm chống rollback** ở thời điểm nhận acknowledgment w:1”.
2. “Dữ liệu đã xác nhận w:1 **chắc chắn sẽ bị rollback**”.

Chỉ câu đầu đúng trong trường hợp chung.

## 5. Kịch bản majority-committed sống sót sau failover

### 5.1. E301 đã được P và S1 xác nhận

Giả sử:

~~~text
P  (PRIMARY)    : ... E300 E301
S1 (SECONDARY)  : ... E300 E301
S2 (SECONDARY)  : ... E300

E301 được nhân bản tới 2/3 data-bearing voting nodes.
Các điều kiện durability đã thỏa.
Client nhận kết quả thành công của w:"majority".
~~~

Khi P gặp sự cố và S1/S2 vẫn hoạt động, S1 đang có lịch sử đủ mới để tham gia election và có thể trở thành primary. S2 bắt kịp E301. Dưới quy tắc election hợp lệ, lịch sử majority-committed E301 được bảo vệ.

Đối chiếu:

| Tiêu chí | E201 chỉ có ở P, w:1 ACK | E301 đã majority-committed, w:"majority" ACK |
| --- | --- | --- |
| Primary đã áp dụng? | Có | Có |
| Client đã nhận ACK? | Có | Có |
| Đã đạt đa số theo ví dụ? | **Chưa** | **Đã** |
| Nguy cơ rollback khi P lỗi và S1/S2 bầu mới | Có | Không trong failover replica set hợp lệ thông thường |
| Có thể bỏ backup? | Không | **Không** |
| Có nghĩa mọi secondary đã cập nhật? | Không | Không |

### 5.2. Majority không đòi tất cả secondary phải bắt kịp

Nếu S2 trễ hàng giây, P + S1 vẫn có thể đủ majority cho E301. Một read trực tiếp tới S2 có thể chưa thấy E301 **ngay tại thời điểm client nhận ACK**, tùy read preference/read concern và tiến độ áp dụng replication.

**Write concern majority không đồng nghĩa mọi bản sao đều đã cập nhật đồng thời.** Chống rollback và độ mới khi đọc từ một secondary cụ thể là hai vấn đề khác nhau.

### 5.3. Không lấy “ACK majority” làm bảo đảm trước mọi thảm họa

Trong phạm vi một replica set hoạt động đúng, majority giúp bảo vệ trước **failover/election thông thường**. Tuy nhiên, nó không thay thế:

- Backup có khả năng khôi phục theo thời điểm cần thiết.
- Kiểm tra cấu hình journaling và storage durability.
- Quy trình xử lý mất dữ liệu trên nhiều thành viên cùng lúc.
- Kế hoạch disaster recovery giữa region/cluster.
- Kiểm soát thao tác của người quản trị khi restore snapshot hoặc tái cấu hình replica set.

Nếu mọi bản sao chứa dữ liệu liên quan đều bị mất vật lý hoặc khôi phục từ bản backup cũ, không thể dựa riêng vào cụm từ “majority-committed” để tạo lại dữ liệu đã mất.

## 6. Write concern: mức xác nhận quyết định điều gì?

### 6.1. w:1

Ví dụ:

~~~javascript
db.events.insertOne(
  {
    _id: "event-1",
    type: "order-created"
  },
  {
    writeConcern: { w: 1 }
  }
);
~~~

Với **w:1**, client yêu cầu primary xác nhận thao tác theo semantics của write concern này. Nó không chờ đủ majority của replica set.

**Ưu điểm:** có thể có độ trễ acknowledgment thấp hơn trong nhiều tình huống.

**Đánh đổi:** write đã acknowledged có thể nằm ngoài majority commit point khi failover xảy ra và vì vậy có nguy cơ rollback.

Đừng ghi rằng “w:1 nghĩa ghi chỉ ở RAM”. Việc ghi đã có mặt trên storage/journal ở đâu còn phụ thuộc cơ chế lưu trữ, **j** và thời điểm áp dụng. Ý cốt lõi là **w:1 không yêu cầu đa số bản sao xác nhận**.

### 6.2. w:"majority"

~~~javascript
db.events.insertOne(
  {
    _id: "event-2",
    type: "payment-confirmed"
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 10000
    }
  }
);
~~~

**w:"majority"** yêu cầu điều kiện ghi được đa số thành viên đủ điều kiện đáp ứng trước khi client nhận acknowledgment thành công. Trong replica set 3 data-bearing voting members, điều này thường tương ứng với **ít nhất 2 thành viên**.

**Ưu điểm:** giúp bảo vệ write khỏi rollback do failover/election bình thường.

**Đánh đổi:** latency có thể tăng nếu secondary cần thêm thời gian sao chép/xác nhận; nếu không đủ các thành viên cần thiết, yêu cầu có thể không nhận được acknowledgment majority trong thời gian mong muốn.

### 6.3. w:0

**w:0** là unacknowledged write concern: client không chờ server xác nhận kết quả ghi theo cách thông thường. Không dùng mức này cho nghiệp vụ cần biết đơn hàng, tiền, tồn kho hoặc audit có thật sự được ghi hay không.

Unacknowledged không có nghĩa “ghi nhanh và chắc chắn tồn tại”; chính vì không chờ xác nhận, ứng dụng có ít thông tin hơn về kết quả.

### 6.4. So sánh

| Write concern | Điều kiện acknowledgment | Nguy cơ rollback của write chưa majority-committed | Dùng khi |
| --- | --- | --- | --- |
| **w:0** | Không chờ xác nhận ghi thông thường | Không có bảo đảm majority | Chỉ khi chấp nhận rủi ro và không cần biết kết quả |
| **w:1** | Primary xác nhận theo cơ chế w:1 | **Có** nếu failover trước majority commit | Dữ liệu có thể tái tạo, có đánh giá rủi ro |
| **w:"majority"** | Đa số bản sao đủ điều kiện xác nhận | Được bảo vệ trong failover thông thường sau ACK thành công | Đơn hàng, giao dịch, trạng thái quan trọng |
| **w:N** | Số lượng member theo cấu hình | Phụ thuộc N, topology và quy tắc acknowledgment | Trường hợp vận hành có yêu cầu đặc biệt |

Không có một giá trị write concern tốt cho mọi hệ thống. Chọn theo **mức mất dữ liệu chấp nhận được**, yêu cầu độ trễ, topology và quy trình khôi phục.

## 7. Journaling: durable trên đĩa khác gì majority?

### 7.1. j:true có vai trò gì?

Tùy chọn **j: true** yêu cầu điều kiện liên quan tới việc ghi vào journal trên những thành viên liên quan theo quy tắc write concern và storage engine. Nó nhấn mạnh **độ bền trên phương tiện lưu trữ**, khác với chỉ đếm số thành viên đã nhận dữ liệu.

Ví dụ:

~~~javascript
db.events.insertOne(
  { _id: "event-3", type: "important-state" },
  {
    writeConcern: {
      w: "majority",
      j: true,
      wtimeout: 10000
    }
  }
);
~~~

Tùy cấu hình, **w:"majority"** mặc định đã liên quan tới journal durability. Tham số **writeConcernMajorityJournalDefault** của replica set là một cấu hình quan trọng: thông thường nó là **true**, nhưng cần xác minh trên cụm thực tế thay vì mặc định trong đầu.

### 7.2. Majority và journaling là hai trục khác nhau

~~~text
Trục số bản sao:
    Primary duy nhất  -----------------  Majority

Trục độ bền cục bộ:
    Mới áp dụng trong memory -----------  Journal/durable
~~~

Một write có thể được xác nhận bởi primary nhưng chưa chờ majority. Một write có thể đã đến nhiều thành viên nhưng chính sách journal của triển khai ảnh hưởng thời điểm xác nhận bền vững. Khi nói “majority commit point bảo vệ chống rollback”, nên nêu **giả định về replication và durability hợp lệ**.

Không ghi tắt rằng “j:true = không rollback”. **Journal trên một primary đơn lẻ không ngăn nhánh lịch sử của primary ấy bị bỏ khi một primary mới được bầu**. Ngược lại, majority replication và journaling cùng phục vụ những failure mode khác nhau.

### 7.3. Phân biệt rollback và crash recovery

| Sự cố | Vấn đề chính |
| --- | --- |
| Primary mất điện, khởi động lại và tiếp tục cùng lịch sử | Khôi phục ghi đã bền vững trên storage |
| Primary tách khỏi quorum, primary mới được bầu | Có thể phải rollback oplog phân kỳ |
| Nhiều máy/đĩa mất dữ liệu vật lý | Cần backup hoặc cơ chế phục hồi ngoài các bản sao bị mất |
| Ứng dụng gửi cùng request hai lần | Cần idempotency; không phải vấn đề journaling |

Không dùng một thuật ngữ “durable” chung chung để lược bỏ sự khác nhau giữa các trường hợp.

## 8. wtimeout: timeout không có nghĩa lệnh ghi được hoàn tác

### 8.1. Chờ majority nhưng không đủ thời gian

Ví dụ:

~~~javascript
db.events.insertOne(
  {
    _id: "event-4",
    type: "order-accepted"
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 5000
    }
  }
);
~~~

**wtimeout: 5000** đặt thời hạn chờ điều kiện write concern, tính bằng mili giây. Nếu replication chậm hoặc các thành viên cần thiết không sẵn sàng, lệnh có thể nhận **write concern timeout/error**.

Điểm cực kỳ quan trọng:

**Write concern timeout không tự rollback thao tác ghi đã được primary áp dụng.**

Khi timeout xảy ra, có thể:

1. Primary đã áp dụng write nhưng nó **chưa majority-committed**.
2. Write sau đó đạt majority và trở thành bền vững theo chính sách.
3. Primary gặp failover trước majority commit, write nằm ngoài lịch sử được chọn và bị rollback.
4. Client không biết chính xác trạng thái cuối nếu response bị mất/lỗi mạng.

Do đó, không được đọc một lỗi write concern rồi lập tức kết luận “không có dữ liệu” hoặc tự gửi lại một thao tác không idempotent.

### 8.2. Phân biệt ba loại kết quả

| Tình huống client quan sát | Suy luận hợp lệ | Không được suy luận |
| --- | --- | --- |
| ACK thành công với w:"majority" | Đã thỏa điều kiện majority của lệnh theo cấu hình | Mọi secondary đã cập nhật; không cần backup |
| ACK thành công với w:1 | Primary đã xác nhận ở mức w:1 | Chắc chắn đã majority-committed |
| Write concern error/timeout | Điều kiện acknowledgment mong muốn không được xác nhận trong thời hạn | Lệnh chắc chắn chưa áp dụng, hoặc chắc chắn đã rollback |
| Network timeout/mất kết nối | Client không nhận kết quả đáng tin cậy | Server chưa thấy request |
| Duplicate key khi thử ghi lại | Đã có document/khóa trùng | Đương nhiên yêu cầu trước đã commit đúng payload |

**Unknown outcome** là trạng thái bình thường cần thiết kế trong hệ thống phân tán. Một API tin cậy phải có cách **đối chiếu** và **xử lý yêu cầu lặp**.

### 8.3. maxTimeMS, socket timeout và wtimeout

Các giới hạn thời gian không tương đương:

- **wtimeout:** thời gian chờ điều kiện write concern.
- **maxTimeMS:** giới hạn thời gian server xử lý thao tác hỗ trợ tham số này, với semantics riêng.
- **Socket timeout:** thời gian chờ I/O giữa client và server.
- **Deadline tổng của request:** ngân sách toàn bộ logic API, bao gồm kết nối, xử lý, database và response.

Một socket timeout ngắn hơn wtimeout có thể làm client bỏ cuộc trước khi nó thấy phản hồi majority. Đặt timeout cần đồng bộ với yêu cầu nghiệp vụ và cách xử lý kết quả không xác định.

## 9. Majority commit point và read concern

### 9.1. Read concern "local"

Với **readConcern: "local"**, MongoDB có thể trả dữ liệu mà node đang phục vụ đã áp dụng, dù dữ liệu chưa majority-committed. Nếu read từ primary ở ví dụ E201 trước failover, client có thể nhìn thấy E201; nhưng E201 vẫn có thể bị rollback.

~~~text
Primary P:
  last applied: E201
  majority commit point: E200

Read concern local:
  có thể nhìn thấy E201 trên P.

Read concern majority:
  không trả dữ liệu chưa được majority-committed theo quy tắc của mức đọc này.
~~~

**Cảnh báo:** readConcern local không đồng nghĩa “dữ liệu chắc chắn mất”, mà là mức đọc này **không đưa ra bảo đảm dữ liệu đã majority-committed**.

### 9.2. Read concern "majority"

**readConcern: "majority"** chỉ trả dữ liệu theo trạng thái đã được majority-committed mà node có thể cung cấp cho thao tác đọc trong ngữ cảnh tương ứng. Nó giúp tránh việc ứng dụng quan sát một write chưa majority-committed rồi sau đó write ấy bị rollback.

Ví dụ command:

~~~javascript
const lab = db.getSiblingDB("mongo_commit_lab");

const result = lab.runCommand({
  find: "lab_commit_events",
  filter: { dataset: "majority-commit-v1" },
  sort: { createdAt: 1, _id: 1 },
  batchSize: 20,
  readConcern: { level: "majority" }
});

printjson(result.cursor.firstBatch);
~~~

**readConcern majority không tự đảm bảo đọc dữ liệu mới nhất tại thời điểm hiện tại**. Một secondary có thể đang trễ replication; một operation đọc majority vẫn có thể thấy trạng thái cũ hơn primary.

### 9.3. Majority read không tự tạo read-your-writes xuyên mọi request

Giả sử:

1. Client ghi một document với w:"majority" vào primary.
2. Client chuyển sang đọc từ một secondary vừa được định tuyến.
3. Secondary ấy chưa áp dụng document mới nhất.

Một readConcern majority trên secondary không đồng nghĩa chắc chắn thấy write của client ngay lập tức trong mọi cấu hình/read preference. Nếu ứng dụng cần **causal consistency/read-your-writes** xuyên những lời gọi liên quan, hãy xem **causally consistent session** và kết hợp mức write concern/read concern tương ứng theo tài liệu driver.

Nếu cần kiểm tra trạng thái ngay sau ghi, đọc theo **_id** từ primary trong cùng luồng có thể là một lựa chọn thực dụng; nhưng tính chất nhất quán của toàn workflow vẫn phải được thiết kế rõ, không chỉ dựa vào trực giác “vừa insert xong thì node nào cũng thấy”.

### 9.4. Read concern snapshot và linearizable

**snapshot** cung cấp cách đọc một ảnh chụp dữ liệu nhất quán tại một mốc thích hợp, đặc biệt có ý nghĩa trong transaction. Nhưng snapshot không tự thay thế một **write concern majority** khi commit transaction.

**linearizable** (trong phạm vi được hỗ trợ, đặc biệt với thao tác đọc một document từ primary) có mục tiêu khác: bảo đảm mức nhất quán mạnh hơn theo thứ tự thời gian thực, với các điều kiện write concern và latency liên quan. Không dùng tên read concern thay thế nhau khi chưa xác định yêu cầu của API.

### 9.5. Bảng phân biệt

| Cơ chế | Vấn đề nó giải quyết | Điều nó không tự bảo đảm |
| --- | --- | --- |
| **w:"majority"** | Đợi write được đa số xác nhận | Mọi secondary lập tức thấy dữ liệu |
| **readConcern "majority"** | Tránh đọc dữ liệu chưa majority-committed theo semantics của mức đọc | Đọc trạng thái mới nhất trên mọi secondary |
| **readConcern "local"** | Đọc trạng thái node đang có | Dữ liệu được bảo vệ khỏi rollback |
| **readConcern "snapshot"** | Đọc một ảnh chụp nhất quán trong ngữ cảnh hỗ trợ | Tự bảo đảm commit của write bên ngoài |
| **Causally consistent session** | Duy trì một số quan hệ nhân quả giữa các thao tác của phiên khi cấu hình đúng | Không làm hệ thống độc lập ngoài phiên tự đồng bộ |
| **Transaction + majority write concern khi commit** | Nhóm nhiều thao tác cùng commit/abort và bảo vệ kết quả commit theo majority | Side effect bên ngoài MongoDB tự rollback |

## 10. Election, quorum và số thành viên

### 10.1. Ba data-bearing voting members

Một replica set đơn giản:

~~~text
P (1 vote, data-bearing)
S1 (1 vote, data-bearing)
S2 (1 vote, data-bearing)

Voting majority: 2/3
~~~

Nếu P mất, S1 và S2 vẫn có thể đạt majority phiếu để bầu primary mới, với điều kiện quorum và các yêu cầu election khác. Một write có trên P+S1 trước đó có thể đạt majority; một write chỉ có P thì chưa.

### 10.2. Arbiter không phải bản sao dữ liệu

Một cấu hình khác:

~~~text
P  (PRIMARY, data-bearing, vote)
S  (SECONDARY, data-bearing, vote)
A  (ARBITER, vote, KHÔNG lưu dữ liệu)
~~~

**Arbiter tham gia bầu cử nhưng không sao chép dữ liệu người dùng/oplog như data-bearing member.** Vì vậy, không được hiểu “P + Arbiter = hai node lưu write, vậy đã majority write concern”.

Đặc biệt trong cấu hình **Primary–Secondary–Arbiter (PSA)**, khi secondary duy nhất không sẵn sàng, primary có thể vẫn có đủ phiếu với arbiter cho một số hoạt động election, nhưng **không thể nhờ arbiter mà thỏa điều kiện sao chép dữ liệu cho write concern majority**.

Do đó, so sánh write concern và khả năng chịu lỗi cần xem:

- Số **voting members**.
- Số **data-bearing members**.
- Cấu hình priority/votes, thành viên hidden/delayed nếu có.
- Khả năng replication thực tế và durability.

Đừng chỉ lấy **tổng số process mongod** chia hai rồi kết luận số bản sao cần thiết.

### 10.3. Nếu mất quorum

Nếu replica set không còn quorum cần thiết để tiếp tục bầu/duy trì primary, các thao tác ghi bình thường có thể không được chấp nhận hoặc không thể được majority-acknowledged.

**Đây là sự đánh đổi giữa an toàn dữ liệu và khả dụng.** MongoDB không thể cung cấp đồng thời một lịch sử majority commit nhất quán và tiếp tục xác nhận majority write tùy ý khi không đủ các bản sao cần thiết.

Ứng dụng phải quyết định cách trả lỗi, retry có giới hạn, queue yêu cầu hoặc hiển thị chế độ tạm không ghi; **không tự động hạ write concern xuống w:1** chỉ để “hệ thống báo xanh” nếu dữ liệu không chịu được rollback.

## 11. Một lỗi hay gặp: “đã thấy trên secondary” nhưng vẫn chưa an toàn

### 11.1. Không nhầm một secondary với majority

Với replica set ba thành viên P/S1/S2, nếu một write xuất hiện trên **P và S1**, đây có thể là majority. Nhưng với replica set **năm data-bearing voting members**, **P và một secondary** chỉ là **2/5**, chưa phải majority.

Do đó, phát biểu “đã replicate sang một secondary thì chắc chắn không rollback” là sai trong cấu hình tổng quát.

### 11.2. Secondary có thể thấy bản ghi rồi mất nó khi đồng bộ lại

Một secondary có thể áp dụng entry thuộc nhánh không còn hợp lệ khi election thay đổi lịch sử. Khi đồng bộ lại với primary mới, entry chưa majority-committed ấy có thể bị rollback.

Việc **ứng dụng đọc được dữ liệu trên một secondary bằng readConcern local** không chứng minh entry đã qua majority commit point. Muốn bảo đảm theo đa số, phải kết hợp **write concern, read concern** và đúng phạm vi thao tác.

### 11.3. Replication lag và rollback risk

Replication lag tăng có thể kéo dài khoảng thời gian một write mới chỉ tồn tại trên primary hoặc chưa được đa số xác nhận. Nhưng replication lag và majority commit point **không phải cùng một metric**.

Ví dụ với P/S1/S2, S2 trễ 30 giây còn S1 gần như bắt kịp; P + S1 vẫn có thể majority-commit nhanh. Ngược lại, nếu cả S1/S2 đều không theo kịp, commit point có thể bị kẹt.

Vì vậy, quan sát lag cần kết hợp với **lastCommittedOpTime**, trạng thái node và số thành viên khả dụng, không chỉ một giá trị “secondary lag” trung bình.

## 12. Thực hành mongosh an toàn trên replica set riêng

Phần lab này **không tự gây failover**. Mục đích là quan sát cấu trúc replica set, so sánh cú pháp write concern và đọc thông tin commit point.

### 12.1. Điều kiện môi trường

- Có **MongoDB replica set thực hành** gồm các data-bearing members được cấu hình đúng; không dùng database production.
- Chuỗi kết nối mongosh trỏ tới **replica set**, không phải standalone.
- Tài khoản có quyền đọc/ghi database lab. Để xem **rs.status()**, có thể cần quyền vận hành/phân tích phù hợp.
- Không cần chạy lệnh **rs.stepDown()**, **rs.reconfig()**, dừng mongod, chặn mạng hoặc xóa file storage.
- Không cần cấu hình một failover thật để học ngữ nghĩa rollback; phần đó đã được mô phỏng bằng sơ đồ.

Nếu dùng một standalone mongod, các thí nghiệm majority replication/election **không đại diện** cho replica set; không cố tạo lỗi bằng cách dùng sai topology.

### 12.2. Xác nhận đang kết nối tới primary

~~~javascript
(() => {
  const info = db.hello();

  printjson({
    replicaSetName: info.setName,
    isWritablePrimary: info.isWritablePrimary,
    primary: info.primary,
    hosts: info.hosts
  });

  if (!info.setName) {
    throw new Error(
      "Kết nối hiện tại không phải replica set. Hãy dùng lab replica set."
    );
  }

  if (!info.isWritablePrimary) {
    print(
      "Node hiện tại không phải primary; kết nối lại qua replica set URI."
    );
  }
})();
~~~

**setName** giúp nhận diện replica set. **isWritablePrimary** cho biết node hiện tại có đang đóng vai trò primary có thể nhận write theo ngữ cảnh lệnh hello hay không. Với mongosh dùng URI đến replica set, driver có thể tự chọn primary cho writes; không cần sửa cấu hình hệ thống để tạo primary mới.

### 12.3. Tạo bộ dữ liệu test có scope cố định

Chạy trên primary của replica set lab:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_commit_lab");
  const coll = lab.getCollection("lab_commit_events");
  const tag = "majority-commit-v1";

  // Chỉ xóa document lab, với write concern phù hợp.
  const cleanup = coll.deleteMany(
    { dataset: tag },
    {
      writeConcern: {
        w: "majority",
        wtimeout: 10000
      }
    }
  );

  printjson({ cleaned: cleanup.deletedCount });

  const seed = coll.insertMany(
    [
      {
        _id: "commit-seed-001",
        dataset: tag,
        kind: "seed",
        createdAt: ISODate("2026-01-01T00:00:00.000Z")
      },
      {
        _id: "commit-seed-002",
        dataset: tag,
        kind: "seed",
        createdAt: ISODate("2026-01-02T00:00:00.000Z")
      }
    ],
    {
      writeConcern: {
        w: "majority",
        wtimeout: 10000
      }
    }
  );

  printjson({
    acknowledged: seed.acknowledged,
    insertedCount: seed.insertedCount,
    count: coll.countDocuments({ dataset: tag })
  });
})();
~~~

**Kết quả mong đợi khi replica set khỏe mạnh và có đủ majority:** hai document seed được insert. Nếu writeConcern bị timeout, **không chạy tiếp rồi mặc định seed đã commit**. Hãy kiểm tra lỗi và xác định trạng thái trước khi thử lại.

Sử dụng _id cố định và dataset giúp các ví dụ không động tới dữ liệu ngoài bài. **Lưu ý:** thao tác deleteMany và insertMany là những lệnh riêng; toàn khối không phải một transaction và không an toàn để chạy song song với một writer khác trên cùng nhãn dataset.

## 13. Quan sát lastCommittedOpTime và các trạng thái node

### 13.1. rs.status()

~~~javascript
const status = rs.status();

printjson({
  set: status.set,
  myState: status.myState,
  optimes: status.optimes
});
~~~

Các trường thường quan tâm trong **optimes** gồm:

- **lastCommittedOpTime**: mốc replication được majority-committed mà node đang báo.
- **appliedOpTime**: mốc operation node đã áp dụng.
- **durableOpTime**: mốc operation liên quan tới trạng thái lưu bền vững.

Tùy phiên bản, output còn có các mốc **WallTime** hoặc trường liên quan tới read concern. Không mặc định mọi server trả cùng một cấu trúc/đầy đủ trường. Khi rs.status thiếu quyền, cần dùng cơ chế quan sát phù hợp thay vì nâng quyền tùy ý.

### 13.2. Liệt kê thành viên và độ mới

~~~javascript
const status = rs.status();

printjson(
  status.members.map(member => ({
    name: member.name,
    state: member.stateStr,
    health: member.health,
    optime: member.optime,
    optimeDate: member.optimeDate,
    syncSourceHost: member.syncSourceHost
  }))
);
~~~

Ý nghĩa:

- **PRIMARY/SECONDARY/ARBITER**: vai trò hiện tại.
- **health**: thông tin khả dụng theo quan sát của node đang hỏi.
- **optime/optimeDate**: tiến độ replication của từng thành viên theo trường dữ liệu được cung cấp.
- **syncSourceHost**: nguồn đồng bộ mà secondary đang sử dụng trong các trường hợp phù hợp.

Các giá trị là **ảnh chụp tại thời điểm gọi** và có thể thay đổi sau đó. Một node báo SECONDARY và bắt kịp ở một thời điểm không bảo đảm nó luôn bắt kịp.

### 13.3. So sánh trước và sau một write majority

Để quan sát:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_commit_lab");
  const coll = lab.getCollection("lab_commit_events");

  print("Optimes trước write:");
  printjson(rs.status().optimes);

  const result = coll.insertOne(
    {
      _id: "commit-majority-001",
      dataset: "majority-commit-v1",
      kind: "ack-majority",
      createdAt: ISODate("2026-01-03T00:00:00.000Z")
    },
    {
      writeConcern: {
        w: "majority",
        j: true,
        wtimeout: 10000
      }
    }
  );

  printjson(result);
  print("Optimes sau write:");
  printjson(rs.status().optimes);
})();
~~~

**Kết quả mong đợi khi đủ majority:** insert được acknowledged; các mốc oplog có thể tiến. Tuy nhiên, một vài entry quản trị/ghi khác cũng có thể xen vào, và cách rs.status được cập nhật không phải lời hứa rằng mỗi lần gọi sẽ thấy đúng một timestamp tăng duy nhất. Không dùng chênh lệch các giá trị này như một phép đo latency hoàn hảo của write.

**Chạy lại ví dụ cùng _id** sẽ gặp duplicate key nếu document còn tồn tại. Đây là biện pháp giúp nhận diện lần thử trước, không phải chức năng tự xóa dữ liệu sau test.

### 13.4. So sánh cú pháp với w:1

~~~javascript
(() => {
  const coll = db.getSiblingDB("mongo_commit_lab")
    .getCollection("lab_commit_events");

  const result = coll.insertOne(
    {
      _id: "commit-w1-001",
      dataset: "majority-commit-v1",
      kind: "ack-primary-only",
      createdAt: ISODate("2026-01-04T00:00:00.000Z")
    },
    {
      writeConcern: { w: 1 }
    }
  );

  printjson(result);
})();
~~~

Nếu write được acknowledged, document thường tồn tại khi đọc lại ngay trên primary. **Điều đó không chứng minh document này chưa majority-committed**, bởi replication có thể diễn ra rất nhanh. Đồng thời nó cũng **không chứng minh document đã được bảo vệ khỏi rollback** tại thời điểm response. Khác biệt ở đây là **ngữ nghĩa acknowledgment**, không phải bạn bắt buộc nhìn thấy hai kiểu dữ liệu khác nhau trên một lab khỏe mạnh.

### 13.5. Đọc bằng readConcern majority

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_commit_lab");

  const result = lab.runCommand({
    find: "lab_commit_events",
    filter: {
      dataset: "majority-commit-v1"
    },
    sort: { createdAt: 1, _id: 1 },
    limit: 20,
    singleBatch: true,
    readConcern: { level: "majority" }
  });

  if (result.ok !== 1) {
    throw new Error(
      "Lệnh find majority thất bại: " + tojson(result)
    );
  }

  printjson(result.cursor.firstBatch);
})();
~~~

Khi replica set đã majority-commit mọi write trong bài, bạn sẽ thấy chúng trong kết quả. Việc một read majority trả dữ liệu không chứng minh chúng đã từng được client ghi với w:majority: **một write w:1 có thể trở thành majority-committed sau khi sao chép hoàn tất**.

## 14. Một thí nghiệm không làm: tự gây rollback trên máy dùng chung

Để quan sát rollback thực tế, người vận hành phải tạo tình huống oplog phân kỳ qua failover trước majority commit. Điều này có thể yêu cầu cô lập network, thay đổi trạng thái process hoặc topology, và có nguy cơ ảnh hưởng đến nhiều client.

**Bài học không yêu cầu và không hướng dẫn gây ra sự cố đó trên môi trường đang phục vụ người khác.** Thay vào đó, dùng sơ đồ E201/E301 ở mục 4–5 để xác định:

1. Entry có xuất hiện trên bao nhiêu data-bearing voting members?
2. Entry đã đi qua majority commit point chưa?
3. Client nhận acknowledgment theo write concern nào?
4. Primary mới hợp lệ sẽ chọn lịch sử nào?
5. Dữ liệu nào có nguy cơ rollback khi node cũ đồng bộ lại?

Nếu tổ chức thực sự cần diễn tập chaos/failover, hãy thực hiện trên **cụm cô lập có snapshot/backup, quy trình phê duyệt và người vận hành chịu trách nhiệm**, đo các tình trạng mong đợi và không dùng lệnh điều khiển failover tùy hứng trên production.

## 15. Majority và transaction: atomic commit không tự đồng nghĩa chống rollback

### 15.1. Một transaction có nhiều document

Giả sử chuyển 100 đơn vị giữa hai ví A và B, đồng thời ghi audit:

~~~text
Trong transaction:
  A.balance -= 100
  B.balance += 100
  INSERT transferAudit
COMMIT
~~~

Transaction giúp các thay đổi trong phạm vi MongoDB được commit/abort cùng nhau theo semantics giao dịch. Nhưng **mức write concern khi commit** vẫn quan trọng để xác định rủi ro lịch sử commit mới bị rollback khi failover.

Khi transaction commit được majority-acknowledged thành công, kết quả commit có bảo đảm mạnh hơn trước failover thông thường so với trường hợp chỉ dựa vào mức xác nhận yếu hơn.

### 15.2. Ví dụ Node.js driver: majority khi commit

Ví dụ tư duy triển khai (chỉ chạy trên replica set lab có hỗ trợ transactions):

~~~javascript
import { MongoClient } from "mongodb";

async function transferInTransaction(uri) {
  const client = new MongoClient(uri);
  await client.connect();

  const session = client.startSession();
  const lab = client.db("mongo_commit_lab");
  const wallets = lab.collection("lab_wallets");
  const audit = lab.collection("lab_transfer_audit");

  try {
    await session.withTransaction(async () => {
      const debit = await wallets.updateOne(
        {
          _id: "wallet-a",
          dataset: "majority-commit-v1",
          balance: { $gte: 100 }
        },
        { $inc: { balance: -100 } },
        { session }
      );

      if (debit.matchedCount !== 1) {
        throw new Error("Không đủ số dư");
      }

      const credit = await wallets.updateOne(
        {
          _id: "wallet-b",
          dataset: "majority-commit-v1"
        },
        { $inc: { balance: 100 } },
        { session }
      );

      if (credit.matchedCount !== 1) {
        throw new Error("Ví đích không tồn tại");
      }

      await audit.insertOne(
        {
          _id: "transfer-001",
          dataset: "majority-commit-v1",
          amount: 100
        },
        { session }
      );
    }, {
      readConcern: { level: "snapshot" },
      writeConcern: { w: "majority" },
      readPreference: "primary"
    });
  } finally {
    await session.endSession();
    await client.close();
  }
}

// Chỉ minh họa: phải tạo riêng 2 wallet ở lab trước khi gọi.
// await transferInTransaction(process.env.MONGODB_URI);
~~~

Đoạn này không thuộc phần seed mục 12 vì bộ seed tại đó chỉ tạo **lab_commit_events**. Bạn phải tự tạo đúng hai ví lab nếu muốn chạy nó; không chạy rồi kỳ vọng ví có sẵn. Nó minh họa vị trí **writeConcern: {w:"majority"} tại transaction options**, không nhằm thử nghiệm thành công trên database thiếu chuẩn bị.

### 15.3. Cảnh báo về retry transaction

Các helper transaction có thể retry callback hoặc commit trong trường hợp lỗi tạm thời. **Không gửi email, trừ tiền qua cổng thanh toán bên ngoài hoặc làm side effect không idempotent trực tiếp trong transaction callback**.

Nếu commit trả **UnknownTransactionCommitResult**, không được tự giả định transaction đã abort. Cần sử dụng cơ chế retry commit phù hợp của driver và idempotency key để nhận diện giao dịch nghiệp vụ đã xử lý.

Khi có hệ thống ngoài MongoDB, áp dụng outbox/event-driven workflow hoặc giao thức phân tán phù hợp; majority write concern không tạo transaction xuyên email/payment gateway.

## 16. Retry sau failover: yêu cầu có thể đã thực thi trước khi client biết

### 16.1. Lỗi “không nhận được response” là một trạng thái riêng

Ví dụ client gửi:

~~~javascript
db.wallets.updateOne(
  { _id: "wallet-a" },
  { $inc: { balance: -100 } }
);
~~~

Kết nối bị ngắt trước khi client nhận response. Các khả năng:

- Server chưa nhận được lệnh.
- Server đã nhận và áp dụng nhưng write chưa majority-committed.
- Write đã majority-committed, response bị mất trên mạng.
- Primary đã step down; trạng thái cuối cần được đối chiếu.

Nếu client tự gửi một request mới với **$inc -100**, nó có thể trừ thêm **100** trên một write đã thành công trước đó.

### 16.2. Retryable writes có giới hạn phạm vi

MongoDB driver hỗ trợ **retryable writes** cho một số thao tác đủ điều kiện trên topology/session phù hợp. Cơ chế này giúp xử lý một số lỗi mạng/failover theo cách tránh thực thi lặp **cùng một statement** trong ngữ cảnh retryable session khi được hỗ trợ.

Nhưng:

- Không phải mọi thao tác đều thuộc nhóm retryable.
- Lệnh **updateMany** và những quy trình nhiều lệnh khác không tự được bảo đảm giống một updateOne retryable.
- **Một HTTP request mới** với business operation mới không mặc nhiên dùng lại cùng session/statement identity.
- Retryable writes không thay thế thiết kế idempotency nghiệp vụ cho payment, chuyển tiền hay tạo đơn.

### 16.3. Mẫu idempotency key

Thay vì chỉ dựa vào số dư sau lỗi, mỗi nghiệp vụ quan trọng có một **requestId/transferId** duy nhất. Ứng dụng có thể:

1. Nhận requestId do server/client tạo theo hợp đồng tin cậy.
2. Ghi nhận requestId và tác động nghiệp vụ trong cùng transaction hoặc cấu trúc dữ liệu có invariant được bảo vệ.
3. Dùng **unique index** cho khóa nghiệp vụ.
4. Khi request lặp, kiểm tra trạng thái đã commit với read/write concern phù hợp.
5. Chỉ trả kết quả tương ứng, **không thực hiện lại side effect** nếu request đã hoàn thành.

Trong trường hợp xóa dữ liệu hoặc xử lý payment, có thể cần audit/outbox và cơ chế reconcile sau failover. Không tự coi “đã thấy document trùng _id” là bằng chứng nội dung trước hoàn toàn giống nội dung cần ghi nếu chưa đối chiếu.

### 16.4. Cần nhìn cả lỗi lẫn kết quả commit

| Triệu chứng | Hướng xử lý |
| --- | --- |
| NotPrimary/PrimarySteppedDown | Driver có thể chọn primary mới và retry thao tác đủ điều kiện |
| NetworkError sau write | Xác định outcome không chắc chắn; dùng retryable writes/idempotency |
| WriteConcernError hoặc wtimeout | Không kết luận write chưa xảy ra; đối chiếu majority-committed state |
| DuplicateKey sau retry | Kiểm tra idempotency key và payload; có thể request trước đã tạo bản ghi |
| UnknownTransactionCommitResult | Theo quy trình retry/đối chiếu commit của driver |
| Xem dữ liệu trên một secondary bị trễ | Kiểm tra read preference/read concern, không vội kết luận write bị rollback |

## 17. Ứng dụng thực tế: đơn hàng, tồn kho và event

### 17.1. Đơn hàng đã xác nhận với khách

Giả sử API trả “Đơn hàng đã được tạo” và gửi email xác nhận. Nếu việc insert Order chỉ acknowledged bằng **w:1**, sau đó Order bị rollback trong failover, người dùng có thể có email xác nhận nhưng database không có đơn.

Đối với dữ liệu quan trọng:

- Cân nhắc **w:"majority"** hoặc chính sách durability tương đương theo yêu cầu.
- Ghi **Order và OutboxEvent** trong transaction nếu chúng là nhiều document cần commit cùng nhau.
- Chỉ phát thông báo sau khi kết quả được xác nhận theo hợp đồng hệ thống.
- Dùng **requestId** để tránh tạo hai đơn khi client retry sau timeout.
- Có quy trình đối soát nếu một bước phụ bên ngoài thất bại.

**Majority giúp giảm rủi ro rollback**, nhưng việc gửi email chính xác một lần vẫn là một bài toán ứng dụng riêng.

### 17.2. Tồn kho

Một inventory document có thể được cập nhật nguyên tử bằng filter **available >= quantity** và toán tử **$inc**. Nhưng nếu stock write mới chỉ được acknowledged ở w:1 rồi bị rollback, ứng dụng có thể đã thông báo “đã giữ hàng” trong khi reservation không còn.

Với stock reservation quan trọng, kết hợp **conditional update, write concern đủ mạnh, business idempotency và đối soát reservation**.

Không dùng majority để thay thế điều kiện tồn kho: một lệnh được majority-committed vẫn có thể ghi số lượng âm nếu filter cho phép.

### 17.3. Log và telemetry có thể tái tạo

Không phải mọi event đều cần cùng mức bền vững như payment. Với dữ liệu telemetry không quan trọng, chi phí của majority write có thể không phù hợp. Chính sách có thể chấp nhận mất một ít event trong failover, với:

- Mức mất dữ liệu chấp nhận được đã định nghĩa.
- Nguồn có thể phát lại hoặc tái tạo event.
- Thông tin metric cảnh báo khi mất/quá tải.
- Không sử dụng dữ liệu ấy làm nguồn duy nhất cho audit tài chính.

Chọn write concern theo **ý nghĩa dữ liệu**, không dùng một khẩu hiệu “mọi thứ majority” hoặc “mọi thứ w:1” mà bỏ qua đặc thù.

## 18. Quan sát replication và nhận biết nguy cơ

### 18.1. Những metric nên theo dõi

| Metric / quan sát | Ý nghĩa |
| --- | --- |
| **lastCommittedOpTime** | Mốc majority commit mà node báo |
| **appliedOpTime / durableOpTime** | Các mốc áp dụng và lưu bền vững tại node |
| **Replication lag** | Secondary đang trễ so với nguồn replication bao nhiêu theo cách đo |
| **Tình trạng members** | PRIMARY/SECONDARY/ARBITER, health, sync source |
| **Election count và stepdown events** | Tần suất thay primary/failover |
| **w:majority latency** | Thời gian chờ acknowledgment phù hợp với ứng dụng |
| **Write concern timeout/errors** | Có khó đạt mức xác nhận yêu cầu hay không |
| **Rollback events/logs** | Dấu hiệu đã có lịch sử phân kỳ và thao tác phải rollback |
| **Connections/retry rate** | Failover có gây bão retry ở client không |
| **Replication oplog window** | Secondary bị trễ quá xa có còn kịp đồng bộ theo oplog không |

Theo dõi **sự chênh giữa mốc đã áp dụng và mốc majority-committed**, nhưng không suy diễn một khoảng thời gian chính xác từ hai giá trị logic nếu chưa có dữ liệu thời gian tương ứng.

### 18.2. rs.printSecondaryReplicationInfo()

Trên phiên mongosh hỗ trợ, có thể dùng:

~~~javascript
rs.printSecondaryReplicationInfo();
~~~

Lệnh này giúp xem tiến độ replication của các secondary và mức trễ ước lượng. Nó là thông tin quan sát, không phải thước đo trực tiếp về việc **một write cụ thể đã majority-committed hay chưa**.

### 18.3. Mốc commit quan sát được có thể thay đổi theo thời điểm hỏi

Giữa hai lần:

~~~javascript
printjson(rs.status().optimes);
~~~

các node có thể tiếp tục áp dụng oplog, secondary có thể bắt kịp, election có thể xảy ra, và commit point có thể tiến. Do vậy, kết luận về một lỗi cụ thể cần liên hệ với **thời điểm write**, **write concern**, **kết quả trả về** và **server logs**, không chỉ một ảnh chụp rs.status vào vài phút sau.

### 18.4. Không “sửa” sự cố bằng cách hạ write concern âm thầm

Nếu w:"majority" thường xuyên timeout:

1. Xác minh số data-bearing voting members và quorum thực tế.
2. Kiểm tra secondary health, replication lag và lỗi storage/network.
3. Đo resource pressure, journaling và các giới hạn hệ thống.
4. Kiểm tra đặc tính workload: write volume, document size, index update cost.
5. Điều chỉnh timeout/ngân sách chỉ khi có hiểu biết về độ trễ bình thường.
6. Có kế hoạch khôi phục replica set nếu một member không thể bắt kịp.

Đổi mọi thao tác thành **w:1** để loại lỗi timeout có thể làm tăng **nguy cơ mất dữ liệu đã acknowledged**, đặc biệt với các nghiệp vụ không thể tái tạo.

## 19. Các giới hạn và tình huống cần tư duy cẩn thận

### 19.1. Majority commit point không có nghĩa mọi ghi trên primary đã an toàn

Primary có thể đang giữ nhiều oplog entry **mới hơn** commit point. Đọc một document trên primary không tự cho biết entry nào của document đã qua majority commit point, nếu không xem read concern và lịch sử thao tác.

### 19.2. Majority acknowledgment không có nghĩa “không bao giờ phải backup”

Replica set giảm rủi ro khi một số member hỏng và có thể tự failover. Backup bảo vệ trước những tình huống khác: thao tác xóa nhầm được majority-committed, corruption, toàn bộ cụm mất dữ liệu, khôi phục lại một thời điểm trong quá khứ, yêu cầu lưu trữ lâu dài.

**Một lệnh deleteMany xóa nhầm với w:"majority" sẽ được sao chép bền vững rất tốt — nhưng đó vẫn là xóa nhầm.** Majority không kiểm tra tính đúng đắn của business logic.

### 19.3. Đọc majority không sửa được lỗi ứng dụng viết sai

Nếu hai client cùng cập nhật số dư theo kiểu đọc số cũ rồi $set, một lost update có thể được majority-committed. Write concern majority chỉ nói **write đã được xác nhận sao chép**, không nói giá trị tính toán của ứng dụng đúng.

Các biện pháp như **$inc**, filter có điều kiện, version/optimistic concurrency và transaction đúng ranh giới vẫn cần thiết.

### 19.4. Rollback không phải transaction abort

**Transaction abort** xảy ra khi transaction chưa commit thành công theo semantics transaction và bị hủy, không áp các thay đổi của transaction vào trạng thái committed.

**Replica set rollback** xảy ra khi oplog của một node phân kỳ với lịch sử được chọn sau failover và một số write không majority-committed bị loại khỏi lịch sử của node ấy.

Hai cơ chế này khác nguyên nhân, phạm vi và cách ứng dụng phải đối phó.

### 19.5. Sự cố đồng thời trên nhiều thành viên

Bảo đảm majority cần một lịch sử oplog được duy trì đúng và đủ dữ liệu trên các thành viên thích hợp. Khi nhiều node hỏng storage, backup bị lỗi hoặc cụm bị tái cấu hình không đúng, vẫn có thể gặp tình huống ngoài failure model bình thường.

**Không dùng câu “write majority tuyệt đối không bao giờ mất” như một phát biểu kỹ thuật không điều kiện.** Nên nói rõ: nó bảo vệ write đã majority-committed khỏi rollback trong những failover replica set hợp lệ và có điều kiện lưu trữ/triển khai đúng.

### 19.6. Đổi replica set config ảnh hưởng majority calculation

Số voting members, arbiter, votes/priority và cấu hình durability có thể ảnh hưởng cách xác định quorum và acknowledgment. Đặc biệt khi thay đổi cấu hình, không dựa vào sơ đồ ba node cố định để suy luận về mọi cluster.

Mọi thay đổi cấu hình cần được thực hiện bởi người vận hành có quyền với quy trình riêng. Bài này **không hướng dẫn reconfig replica set** và không yêu cầu thực hiện thao tác có thể gây mất quorum.

## 20. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế | Hệ quả thiết kế |
| --- | --- | --- |
| insertOne trả acknowledged nghĩa chắc chắn majority-committed | ACK phụ thuộc write concern | Kiểm tra w trước khi hứa dữ liệu sống sót failover |
| w:1 nghĩa write chắc chắn sẽ rollback | Write có thể đạt majority sau ACK | Không suy luận chắc chắn từ w đơn lẻ |
| w:"majority" nghĩa cả ba node đã nhận | Majority không nhất thiết là tất cả | Secondary chậm vẫn có thể chưa có write |
| Primary đã ghi journal là đủ chống rollback | Journal cục bộ khác majority history | Xem cả j và w |
| Arbiter là một bản sao dữ liệu | Arbiter chỉ tham gia election, không giữ dataset | Không tính arbiter như một secondary sao chép dữ liệu |
| Đã thấy dữ liệu bằng readConcern local thì an toàn | Local có thể thấy write chưa committed | Dùng majority read khi cần tránh dữ liệu có thể rollback |
| Majority read luôn mới nhất | Secondary có thể trễ và majority read có thể stale | Xem causal session/primary read theo yêu cầu |
| wtimeout nghĩa chưa ghi | Write có thể đã áp dụng rồi chưa được ACK đủ | Không retry mù quáng |
| Network timeout nghĩa server chưa thực thi | Response có thể mất sau khi ghi | Dùng retryable writes/idempotency |
| Có majority thì không cần backup | Majority không cứu xóa nhầm hay mất dữ liệu toàn cụm | Duy trì PITR/backup phù hợp |
| Transaction atomic nghĩa tự chống rollback | Commit vẫn có write concern riêng | Dùng majority tại commit khi cần |
| Rollback = transaction abort | Một cái là oplog phân kỳ, một cái là giao dịch chưa commit | Xử lý failure mode riêng |
| Một secondary lag 30s nghĩa mọi write trễ commit 30s | Primary + secondary khác có thể đủ majority | Xem commit point và topology |
| Hạ w:1 khi majority timeout không đổi rủi ro | Bảo đảm chống rollback giảm | Sửa replication/quorum thay vì hạ an toàn âm thầm |
| Majority bảo đảm business invariant đúng | Replication không kiểm tra logic | Filter/transaction/validation vẫn cần |
| Snapshot restore có thể bỏ qua majority | Restore sai thời điểm có thể mất dữ liệu | Quy trình khôi phục cần kiểm soát |

## 21. Bài tập tư duy và thực hành

### Bài 1 — Phân biệt acknowledged và committed

Với P/S1/S2:

~~~text
P : E100 E101 E102
S1: E100 E101
S2: E100
~~~

Giả sử các entry đã thỏa điều kiện lưu trữ tương ứng. Majority commit point có thể ở entry nào? E102 được ACK bằng w:1 có chắc chắn an toàn trước failover không? Nếu S1 bắt kịp E102, câu trả lời thay đổi thế nào?

### Bài 2 — Write bị rollback

Vẽ dòng thời gian: P ghi E201 với w:1, S1/S2 chưa có E201, P bị cô lập, S1/S2 bầu primary mới. Giải thích vì sao E201 có thể bị rollback khi P trở lại. Cho ví dụ hậu quả với một Order vừa insert.

### Bài 3 — Write đã majority-committed

Giả sử P và S1 đã có E301, client được ACK w:"majority", S2 chưa bắt kịp. Khi P lỗi, điều gì giúp giữ E301 trong lịch sử hợp lệ của replica set? Vì sao S2 chưa có E301 không có nghĩa write majority thất bại?

### Bài 4 — Sự khác nhau giữa w:1 và j:true

So sánh **w:1, j:true** với **w:"majority"** về khả năng chống rollback và độ bền cục bộ. Tại sao journal trên primary không đủ bảo vệ một entry chưa majority-committed khi election chọn lịch sử khác?

### Bài 5 — Timeout và unknown outcome

Một insert với w:"majority", wtimeout 5 giây trả WriteConcernError. Liệt kê ít nhất ba trạng thái có thể xảy ra sau đó. Đề xuất cách đối chiếu bằng idempotency key và read concern phù hợp thay vì gửi lại insert với một _id mới.

### Bài 6 — Đọc trên secondary

Client ghi một document với w:"majority" và ngay lập tức đọc ở S2 bằng readConcern majority nhưng không thấy document. Điều này có nhất thiết chứng minh write bị rollback? Giải thích replication lag, read preference và cơ chế cần dùng khi yêu cầu read-your-writes.

### Bài 7 — Arbiter và write concern

Một replica set gồm P, S, Arbiter. Khi S không hoạt động, P và Arbiter vẫn có thể đạt đa số phiếu trong một số trường hợp. Vì sao điều đó không có nghĩa write trên P đã được nhân bản tới majority data-bearing members?

### Bài 8 — Mô tả rs.status

Trên một replica set lab, dùng **rs.status()** xem members và optimes. Ghi tên các trường lastCommittedOpTime, appliedOpTime, durableOpTime nếu có. Mỗi trường trả lời câu hỏi gì, và tại sao không thể suy ra chính xác toàn bộ lịch sử một request cụ thể từ một ảnh chụp trạng thái?

### Bài 9 — So sánh kết quả write concern

Chạy những ví dụ **commit-majority-001** và **commit-w1-001** trên lab không gây failover. Có thể cả hai document đều được readConcern majority nhìn thấy sau đó. Giải thích vì sao kết quả này **không chứng minh w:1 tương đương majority**.

### Bài 10 — Thiết kế chính sách dữ liệu

Phân loại ba loại dữ liệu: event telemetry có thể gửi lại, Order đã xác nhận với khách, và Payment/Audit. Nêu write concern, read concern, idempotency, backup và độ trễ chấp nhận được cho từng loại, cùng lý do khác biệt.

### Bài 11 — Retry và double-charge

Một lệnh **$inc -100** trên ví có thể đã commit majority nhưng response mất. Nếu client gửi một HTTP request mới, rủi ro gì xảy ra? Đề xuất transferId duy nhất và transaction gồm điều chỉnh ví + audit record để nhận diện yêu cầu lặp.

### Bài 12 — Majority trong transaction

Giao dịch cập nhật hai document và ghi audit được commit với write concern yếu hơn yêu cầu durability của sản phẩm. Dù transaction đảm bảo all-or-nothing trong phạm vi commit, điều gì có thể xảy ra nếu commit chưa majority-committed trước failover? Nêu cách cấu hình write concern khi commit.

### Bài 13 — Khác nhau giữa election và rollback

Giải thích vì sao không phải **mọi election** đều có rollback. Điều kiện nào khiến xuất hiện nhánh lịch sử phân kỳ? Một entry đã majority-committed khác entry chỉ mới được primary áp dụng như thế nào?

### Bài 14 — Phân tích replication lag

Replica set P/S1/S2: S1 bắt kịp primary gần như ngay lập tức, S2 trễ 20 giây. Majority write có bắt buộc chờ S2 không? Nếu sau đó S1 cũng mất kết nối, điều gì thay đổi đối với khả năng acknowledged w:"majority"?

### Bài 15 — Khôi phục sai snapshot

Một quản trị viên restore toàn cluster từ backup cũ một ngày. Những entry majority-committed trong ngày hôm qua có tự xuất hiện lại không? Phân biệt bảo đảm của replication với quy trình backup, point-in-time restore và lưu lịch sử bên ngoài.

### Bài 16 — Nâng cấp chính sách API

Một API hiện dùng w:1 cho đặt hàng, trả response thành công rồi gửi email ngay. Đề xuất quy trình nâng cấp bao gồm:

1. Ghi Order với bảo đảm durability phù hợp.
2. Ghi outbox event cùng transaction nếu cần.
3. Thiết kế requestId/idempotency.
4. Xử lý wtimeout và unknown outcome.
5. Theo dõi majority latency, error rate và replication health.

Nêu điều kiện khiến API nên từ chối/tạm hoãn write thay vì tự hạ write concern.

## 22. Tài liệu tham khảo chính thức

- MongoDB Manual — [Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/).
- MongoDB Manual — [Replication](https://www.mongodb.com/docs/manual/replication/).
- MongoDB Manual — [Replica Set Elections](https://www.mongodb.com/docs/manual/core/replica-set-elections/).
- MongoDB Manual — [Replica Set Rollbacks](https://www.mongodb.com/docs/manual/core/replica-set-rollbacks/).
- MongoDB Manual — [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/).
- MongoDB Manual — [Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/).
- MongoDB Manual — [Read Concern "majority"](https://www.mongodb.com/docs/manual/reference/read-concern-majority/).
- MongoDB Manual — [db.hello()](https://www.mongodb.com/docs/manual/reference/method/db.hello/).
- MongoDB Manual — [replSetGetStatus / rs.status()](https://www.mongodb.com/docs/manual/reference/command/replSetGetStatus/).
- MongoDB Manual — [Transactions](https://www.mongodb.com/docs/manual/core/transactions/).
- MongoDB Manual — [Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/).

**Điều cần ghi nhớ:** **Majority commit point** đánh dấu phần lịch sử oplog đã được đa số các thành viên đủ điều kiện xác nhận. Một write **w:1 đã acknowledged** nhưng **chưa đi qua commit point** vẫn có thể **rollback** nếu primary mất vai trò trước khi secondary sao chép đủ và một lịch sử khác được bầu làm hợp lệ. Một write **w:"majority" được acknowledged thành công** được bảo vệ trước rollback do **failover replica set thông thường**, với cấu hình replication và durability đúng. Dù vậy, **majority không thay thế backup, idempotency, conditional updates hay transaction**. Khi xử lý lỗi mạng và wtimeout, cần chấp nhận khả năng **không biết ngay kết quả cuối**, đối chiếu theo định danh nghiệp vụ và không retry mù quáng các thao tác có side effect.
