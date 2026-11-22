# ACID và các thuộc tính cần bảo vệ trong một thao tác nghiệp vụ

Khi xây dựng ứng dụng trên cơ sở dữ liệu NoSQL, câu hỏi không chỉ là **lưu dữ liệu ở đâu** hay **truy vấn bằng khóa nào**. Một hệ thống còn phải bảo đảm rằng những thao tác như đặt hàng, trừ số dư, giữ chỗ, áp mã giảm giá hoặc chuyển trạng thái đơn **không tạo kết quả nghiệp vụ sai**, ngay cả khi nhiều người thao tác đồng thời, ứng dụng bị ngắt mạng hoặc máy chủ cơ sở dữ liệu gặp sự cố.

**ACID** là tập hợp bốn thuộc tính thường được dùng để diễn đạt những bảo đảm của một *transaction*:

- **A — Atomicity (tính nguyên tử):** các thay đổi trong phạm vi transaction được commit như một đơn vị, hoặc không được commit.
- **C — Consistency (tính nhất quán với ràng buộc):** nếu trạng thái ban đầu hợp lệ và mọi thao tác tuân thủ các điều kiện đã định nghĩa, transaction phải đưa hệ thống đến trạng thái hợp lệ tiếp theo.
- **I — Isolation (tính cô lập):** các transaction đồng thời phải được quan sát và phối hợp theo một mô hình cô lập đã cam kết, tránh những kiểu tương tác bị cấm.
- **D — Durability (tính bền vững):** khi một transaction đã được xác nhận commit, các thay đổi phải sống sót qua những loại lỗi nằm trong phạm vi bảo đảm của hệ thống.

Trong NoSQL, **không thể kết luận một hệ “có ACID” hoặc “không có ACID” chỉ từ nhãn NoSQL**. Nhiều hệ hỗ trợ thao tác nguyên tử trên một record/document, một số hỗ trợ transaction nhiều record; phạm vi, mức cô lập, tính bền vững, giới hạn và chi phí của từng cơ chế khác nhau. Muốn thiết kế đúng phải xác định **bất biến nghiệp vụ, tập dữ liệu cần thay đổi cùng nhau, ranh giới transaction và cấu hình bảo đảm thực tế**.

Bài học dùng tình huống giữ hàng cho đơn đặt mua để phân tích từng thuộc tính ACID, trình bày các lịch truy cập đồng thời và ví dụ MongoDB, sau đó đối chiếu với DynamoDB, Redis, Cassandra và những quy trình nhiều dịch vụ.

## 1. Bắt đầu từ thao tác nghiệp vụ, không bắt đầu từ câu lệnh

Giả sử cửa hàng còn **5 chiếc** sản phẩm `SKU-100`. Người dùng gửi yêu cầu:

> “Giữ 3 chiếc `SKU-100` cho đơn `O-501`.”

Trong một mô hình đơn giản, hệ thống có:

~~~text
inventory / SKU-100
  capacity      = 5
  available     = 5
  reservedTotal = 0

reservations
  Chưa có reservation cho O-501
~~~

Nếu giữ thành công, trạng thái mong muốn là:

~~~text
inventory / SKU-100
  capacity      = 5
  available     = 2
  reservedTotal = 3

reservations / O-501
  sku           = SKU-100
  quantity      = 3
  status        = RESERVED
~~~

Ở đây có ít nhất ba yêu cầu:

1. **Không cấp phát vượt lượng hàng có thể dùng:** `available >= 0`.
2. **Giữ hàng và ghi nhận reservation cùng thành công hoặc cùng thất bại:** nếu thiếu một trong hai, dữ liệu có thể mâu thuẫn.
3. **Hai request đồng thời không được cùng tiêu dùng một lượng hàng duy nhất:** kiểm tra tồn phải phối hợp với cập nhật.

Nếu đã phản hồi “giữ hàng thành công”, còn có yêu cầu thứ tư: **trạng thái đã commit phải đủ bền vững theo chính sách được công bố**. Đây là nơi ACID trở nên hữu ích.

### Viết bất biến có thể kiểm tra

Với mô hình không có nhập hàng, xuất hàng hoàn tất hoặc hủy reservation trong ví dụ ban đầu:

\[
\begin{aligned}
I_1 &: available \ge 0\\
I_2 &: reservedTotal \ge 0\\
I_3 &: available + reservedTotal = capacity
\end{aligned}
\]

Nếu `reservations` được dùng làm sổ ghi nguồn cho phần đã giữ thì còn có điều kiện:

\[
I_4:\quad
reservedTotal
=\sum_{\text{reservation đang RESERVED}} quantity
\]

`I_1`–`I_3` chỉ liên quan đến **một document inventory**; `I_4` còn liên quan đến **nhiều reservation**. Đây là sự khác biệt quyết định phạm vi transaction cần có.

**Lưu ý:** các điều kiện trên đúng với mô hình tối thiểu đã nêu. Khi thêm bán hàng thực, hủy giữ, hoàn tiền, nhập kho hoặc kiểm kê, phải định nghĩa thêm trạng thái và phép chuyển phù hợp; không thể dùng nguyên công thức cho mọi vòng đời tồn kho.

## 2. Transaction là gì và ranh giới của nó nằm ở đâu?

**Transaction** là một đơn vị công việc mà DBMS xử lý với những bảo đảm đã được định nghĩa. Nó có thể chỉ gồm một lần cập nhật một record, hoặc bao gồm nhiều câu lệnh làm thay đổi nhiều record.

Ví dụ:

~~~text
Transaction T1:
  - Kiểm tra available >= 3
  - Trừ available đi 3
  - Cộng reservedTotal thêm 3
  - Ghi reservation cho O-501
  - Commit
~~~

Ranh giới transaction quyết định:

- Những thay đổi nào được **commit cùng nhau**?
- Điều kiện kiểm tra nào có còn đúng lúc ghi?
- Các transaction đồng thời nhìn thấy trạng thái của nhau ra sao?
- Khi crash, các thay đổi nào được phục hồi?

Nếu inventory và reservation nằm trên **hai document**, một cập nhật nguyên tử riêng lẻ trên inventory **chưa đủ** để coi toàn bộ thao tác giữ hàng là nguyên tử.

### Đừng nhầm transaction của DB với toàn bộ hành trình người dùng

Một yêu cầu “đặt và thanh toán đơn hàng” có thể đi qua:

~~~text
Order API
   │
   ├── Database: tạo đơn
   ├── Inventory: giữ hàng
   ├── Payment provider: thu tiền
   └── Email provider: gửi xác nhận
~~~

Một transaction MongoDB chỉ có hiệu lực đối với những thao tác được thực thi **trong phạm vi cơ sở dữ liệu và session transaction tương ứng**. Nó không tự rollback giao dịch của cổng thanh toán hoặc email đã gửi.

Vì vậy phải xác định **thao tác nghiệp vụ nào cần tính nguyên tử tức thời trong một kho dữ liệu**, và **quy trình nhiều hệ thống** cần một giao thức phối hợp khác.

## 3. Atomicity — hoặc cùng commit, hoặc không commit

**Atomicity** bảo vệ hệ thống khỏi **trạng thái cập nhật một phần** trong ranh giới transaction đã khai báo.

Xét hai thay đổi:

~~~text
A. inventory.available: 5 → 2
B. Tạo reservation O-501 quantity=3
~~~

Nếu thực hiện bằng hai thao tác độc lập:

~~~text
T0: inventory available = 5
T1: giảm tồn thành 2 → thành công
T2: ghi reservation → lỗi kết nối

Trạng thái cuối:
  Hàng đã bị trừ
  Không có reservation tương ứng
~~~

Nếu đảo thứ tự:

~~~text
T1: ghi reservation RESERVED → thành công
T2: trừ inventory → không đủ hàng hoặc lỗi

Trạng thái cuối:
  Đơn tuyên bố đã giữ
  Tồn kho chưa được trừ tương ứng
~~~

Không thể giải quyết vấn đề bằng việc chỉ nói “đường gọi API sẽ chạy hai lệnh liên tiếp”. **Hai lệnh riêng lẻ thành công độc lập không tạo atomicity chung**.

### Khi có transaction nhiều document

~~~text
BEGIN TRANSACTION
  Conditional update inventory
  Insert reservation
COMMIT

Nếu có lỗi trước commit:
  ABORT / ROLLBACK toàn bộ transaction
~~~

Sau commit, không được có trạng thái database mà chỉ một trong hai thay đổi được xác nhận như phần còn lại của transaction. DBMS chịu trách nhiệm triển khai atomicity theo cơ chế riêng.

### Atomicity không đồng nghĩa “một HTTP request”

Một HTTP request có thể gọi nhiều dịch vụ. Ngược lại, một transaction trong DB có thể được tạo bởi nhiều câu lệnh trong cùng một session. **Ranh giới nguyên tử không được suy từ ranh giới request mạng**.

### Atomicity không bảo đảm đầu vào hợp lệ

Một transaction nguyên tử có thể ghi **sai cả hai trường cùng lúc**, chẳng hạn trừ tồn bằng số âm do lập trình viên truyền sai. Vì vậy vẫn cần:

- Validation: `quantity` là số nguyên dương, trong miền được hỗ trợ.
- Điều kiện dữ liệu: `available >= quantity`.
- Quyền truy cập và định danh sản phẩm/đơn.
- Ràng buộc uniqueness hoặc quy tắc idempotency khi cần.

Atomicity bảo đảm **không bị một phần**, chứ không tự chứng minh **toàn bộ thao tác là đúng nghiệp vụ**.

## 4. Consistency — bảo toàn những điều kiện nào?

Trong ACID, **Consistency** nói về việc chuyển từ một **trạng thái hợp lệ** sang một **trạng thái hợp lệ** theo các ràng buộc đã xác định.

Với inventory:

~~~text
Trước:
  capacity=5, available=5, reservedTotal=0

Sau khi reserve(3):
  capacity=5, available=2, reservedTotal=3

Kiểm tra:
  available >= 0
  reservedTotal >= 0
  available + reservedTotal == capacity
~~~

Nhưng nếu hai request cùng muốn giữ 4 và 3 chiếc, hệ phải **từ chối ít nhất một request** khi tổng quá 5. Việc tất cả câu lệnh đều “thành công” không phải thước đo tính đúng đắn.

### Nguồn gốc của ràng buộc

| Cách thể hiện | Ví dụ | Ai chịu trách nhiệm? |
| --- | --- | --- |
| Kiểu/schema | `quantity` là số nguyên, `status` thuộc tập cho phép | Schema validation, ứng dụng, DBMS tùy hệ |
| Unique key/constraint | Mỗi `requestId` chỉ có một reservation | DBMS nếu có ràng buộc phù hợp; ứng dụng xác định phạm vi |
| Điều kiện cập nhật | Chỉ trừ tồn khi `available >= q` | Query/transaction được viết đúng |
| Bất biến nhiều record | Tổng reservation active khớp bộ đếm inventory | Thiết kế transaction hoặc giao thức phối hợp |
| Quy tắc vòng đời | `CANCELLED` không tự chuyển thành `PAID` | State machine/conditional update |
| Giới hạn tenant | Không lấy dữ liệu của tenant khác | Authorization và cách định danh khóa |

Không phải DBMS tự hiểu mọi điều kiện nghiệp vụ. **Ứng dụng phải phát biểu bất biến và triển khai chúng bằng cơ chế phù hợp**.

### Ba khái niệm “consistency” dễ bị nhầm

1. **ACID Consistency:** bảo toàn ràng buộc/invariant của transaction.
2. **Consistency model của hệ phân tán:** một client đọc từ replica thấy giá trị mới đến mức nào — strong, eventual, causal, v.v.
3. **Chữ C trong CAP:** trong cách dùng phổ biến của định lý CAP, liên quan đến mô hình nhất quán kiểu linearizability trong bối cảnh phân vùng mạng, **không phải** danh sách ràng buộc nghiệp vụ ACID.

Một DBMS có thể bảo vệ ràng buộc cục bộ của transaction nhưng vẫn cho phép một query trên read replica thấy dữ liệu cũ. Không được dùng từ “consistent” chung chung khi cần quyết định an toàn.

## 5. Isolation — transaction đồng thời không được làm sai cam kết

**Isolation** mô tả những cách các transaction đồng thời có thể quan sát và ảnh hưởng lẫn nhau. Nó đặc biệt quan trọng với thao tác kiểu **đọc–kiểm tra–ghi**.

Giả sử:

~~~text
available = 5
T1 muốn reserve(4)
T2 muốn reserve(3)
~~~

### Cách làm sai: đọc trước rồi ghi đè

~~~text
Thời điểm | T1                   | T2
--------- | -------------------- | --------------------
1         | Đọc available = 5    |
2         |                      | Đọc available = 5
3         | Kiểm tra 5 >= 4      |
4         |                      | Kiểm tra 5 >= 3
5         | Ghi available = 1    |
6         |                      | Ghi available = 2
7         | Báo thành công       | Báo thành công
~~~

Cả hai request đã chấp nhận tổng **7 chiếc**, dù kho chỉ có 5. Đây là một ví dụ **lost update** khi ghi đè dựa trên bản đã đọc cũ, đồng thời làm sai cam kết nghiệp vụ.

### Cách tốt hơn: điều kiện nằm trong thao tác ghi

~~~javascript
await db.collection("inventory").updateOne(
  {
    _id: "SKU-100",
    available: { $gte: quantity }
  },
  {
    $inc: {
      available: -quantity,
      reservedTotal: quantity
    }
  }
);
~~~

Với `quantity > 0` đã được validate và một document có dữ liệu hợp lệ, MongoDB kiểm tra điều kiện và cập nhật hai field **trong một thao tác nguyên tử trên document**. Chỉ một thứ tự cập nhật phù hợp được chấp nhận; không thể hai cập nhật 4 và 3 cùng tiêu dùng số lượng 5 ban đầu.

**Điểm tinh tế:** ở đây ta không cần một transaction nhiều document **nếu invariant chỉ liên quan hai bộ đếm trong một document**. Nhưng nếu còn cần tạo reservation ở document khác một cách nguyên tử, phạm vi bảo vệ lớn hơn.

## 6. Các bất thường đồng thời thường gặp

Việc chọn isolation level không nên bắt đầu bằng cách học tên mức cô lập, mà bắt đầu từ **những hành vi sai mà nghiệp vụ không được phép gặp**.

| Hiện tượng | Mô tả khái quát | Rủi ro nghiệp vụ |
| --- | --- | --- |
| **Dirty read** | Đọc thay đổi của transaction chưa commit | Ra quyết định theo trạng thái sau đó rollback |
| **Non-repeatable read** | Đọc cùng một record hai lần nhận hai giá trị do transaction khác commit | Quyết định thiếu ổn định trong cùng thao tác |
| **Phantom read** | Cùng điều kiện query nhưng lần sau thấy thêm/bớt record | Đếm, giới hạn số bản ghi hoặc predicate thay đổi |
| **Lost update** | Hai luồng ghi dựa trên cùng trạng thái cũ, một cập nhật đè kết quả kia | Mất phần thay đổi đã được chấp nhận |
| **Write skew** | Hai transaction đọc cùng tập ràng buộc, sau đó sửa những record khác nhau nhưng phá invariant chung | Vượt quota, không còn nhân sự trực, cấp trùng quyền |
| **Serialization anomaly** | Kết quả không tương đương với một lịch chạy tuần tự hợp lệ theo mô hình yêu cầu | Vi phạm invariant dù từng transaction tưởng mình đúng |

Các hiện tượng trên phụ thuộc định nghĩa formal của isolation, DBMS và cách viết transaction. Một mức cô lập có thể ngăn một số hiện tượng nhưng không ngăn tất cả.

### 6.1. Dirty read

~~~text
T1: sửa order.status = PAID (chưa commit)
T2: đọc order.status = PAID
T1: rollback
~~~

Nếu T2 đã gửi hàng vì tin vào trạng thái chưa commit, hệ thống có lỗi. Một isolation model ngăn dirty read không cho T2 dùng giá trị chưa commit đó theo đường đọc transaction đã cam kết.

### 6.2. Non-repeatable read

~~~text
T1: đọc available = 5
T2: giảm available xuống 3 và commit
T1: đọc lại available = 3
~~~

Trong một số mức cô lập, hai lần đọc trong T1 có thể khác nhau. Điều này không luôn là lỗi: có API chấp nhận dữ liệu mới giữa hai lần đọc. Nhưng nếu T1 giả định mình đang đọc một snapshot ổn định để ra quyết định, phải chọn mô hình cô lập tương ứng.

### 6.3. Phantom read

~~~text
T1: SELECT reservations WHERE status=ACTIVE → 9 dòng
T2: INSERT reservation ACTIVE → commit
T1: SELECT lại cùng điều kiện → 10 dòng
~~~

Nếu nghiệp vụ “không có quá 10 lượt đặt chỗ” dựa vào số bản ghi và T1 sắp thêm một dòng nữa, việc kiểm soát predicate và transaction concurrency trở nên quan trọng.

### 6.4. Write skew

Một lịch trực bệnh viện yêu cầu **luôn có ít nhất một bác sĩ trực**:

~~~text
Ban đầu:
  Doctor A = ON_CALL
  Doctor B = ON_CALL

T1:
  Đọc A và B đều trực
  Quyết định đưa A về OFF_CALL

T2:
  Đọc A và B đều trực
  Quyết định đưa B về OFF_CALL

Hai transaction sửa hai record khác nhau.
Kết quả cuối:
  A = OFF_CALL
  B = OFF_CALL
  → Không còn ai trực!
~~~

Trong một số hệ dùng **snapshot isolation**, hai transaction có thể không xung đột ghi trực tiếp vì chúng sửa hai document khác nhau. Snapshot nhất quán **chưa chắc tương đương serializability** cho bất biến trải nhiều record.

Cần cơ chế bảo vệ thực sự: transaction serializable nếu được hỗ trợ, dùng chung một record/aggregate làm điểm tranh chấp, khóa phù hợp hoặc thiết kế lại invariant để có cập nhật điều kiện tại một ranh giới nguyên tử.

## 7. Isolation level không đồng nghĩa hoàn toàn với tên ACID

Một số mô hình thường được nhắc đến:

| Mô hình/mức | Ý nghĩa khái quát | Cần cẩn thận |
| --- | --- | --- |
| **Read uncommitted** | Có thể cho phép quan sát thay đổi chưa commit theo định nghĩa hệ | Dirty read nếu DBMS thực sự cho phép |
| **Read committed** | Tránh dirty read theo ngữ nghĩa mức này | Giá trị/predicate có thể đổi giữa các lần đọc |
| **Repeatable read** | Duy trì các bảo đảm lặp lại việc đọc theo cách triển khai | Quy tắc phantom/write skew khác nhau giữa DBMS |
| **Snapshot isolation** | Transaction đọc một snapshot nhất quán theo mốc | Có thể vẫn gặp write skew nếu invariant trải record khác nhau |
| **Serializable** | Kết quả tương đương một thứ tự transaction tuần tự hợp lệ | Chi phí conflict, abort/retry; không tự xử lý side effect ngoài DB |
| **Linearizability** | Tính chất mạnh về quan sát thời gian thực của thao tác trên đối tượng/đường truy cập | Khác với serializability của tập transaction |

Đây là bảng định hướng. **Không được tự gán một isolation level chung cho mọi NoSQL DBMS**. Một hệ có thể cung cấp:

- Atomic update ở phạm vi một document.
- Transaction snapshot trên nhiều document.
- Conditional write hoặc compare-and-set trên một key.
- Transaction serializable trong một phạm vi cụ thể.
- Read replica/eventual query có độ mới yếu hơn đường primary.

### Serializable có nghĩa gì?

Giả sử hai transaction T1 và T2 cùng cạnh tranh. Nếu kết quả **serializable**, nó phải tương đương với **một thứ tự tuần tự nào đó**, ví dụ:

~~~text
T1 chạy xong trước T2
hoặc
T2 chạy xong trước T1
~~~

Nó **không yêu cầu** ứng dụng thực sự chạy từng transaction trên một thread duy nhất. DBMS có thể cho chạy đồng thời nhưng dùng locking, validation, MVCC hoặc cơ chế khác để tạo kết quả hợp lệ.

### Serializable khác strict serializability

Serializable tập trung vào tương đương với một lịch tuần tự hợp lệ. **Strict serializability** còn phải tôn trọng một số quan hệ thứ tự thời gian thực giữa transaction. Vì vậy, khi một hệ tuyên bố “serializable”, vẫn cần đọc kỹ **phạm vi** và **ngữ nghĩa chính xác** của bảo đảm đó.

Trong thao tác thanh toán hoặc quota, đừng dựa vào nhãn isolation chung nếu chưa hiểu đường đọc, transaction conflict và cách xử lý khi commit có kết quả không chắc chắn.

## 8. Durability — ACK thành công còn đúng sau sự cố không?

**Durability** nói về việc một transaction đã được xác nhận commit có còn được hệ thống bảo toàn qua những lỗi thuộc phạm vi cam kết hay không.

Ví dụ:

~~~text
T0: Order O-501 được commit với status=RESERVED
T1: Database trả ACK success cho API
T2: Process database bị crash
T3: Database khởi động lại

Kỳ vọng theo chính sách durability:
  Order O-501 vẫn ở trạng thái RESERVED
  Inventory vẫn phản ánh phần hàng đã giữ
~~~

Muốn đạt được điều đó, hệ có thể dùng WAL/journal/commit log, checkpoint, flush xuống thiết bị và replication. Nhưng **cách kết hợp và thời điểm ACK khác nhau theo DBMS và cấu hình**.

### Việc một thao tác đã được ghi vào RAM chưa đủ

~~~text
Request đến
    │
    ▼
Đổi dữ liệu trong RAM
    │
    ▼
ACK sớm
    │
    X mất điện trước khi thay đổi được lưu bền vững
~~~

Trong cấu hình có ACK sớm như vậy, dữ liệu có thể mất sau crash hoặc mất điện. Hệ có thể chấp nhận đánh đổi đó với dữ liệu cache có thể tái tạo, nhưng thường không phù hợp với một cam kết đã giữ tiền/hàng nếu nghiệp vụ yêu cầu độ bền cao.

### Replication và durability là hai chiều liên quan nhưng khác nhau

| Cơ chế | Đóng góp | Không tự bảo đảm |
| --- | --- | --- |
| WAL/journal durable | Phục hồi từ crash trên một thiết bị/node theo cơ chế engine | Sống sót khi toàn bộ thiết bị/node bị mất vật lý |
| Replica | Có thêm bản sao và khả năng failover | Không tự tránh xóa nhầm lan tới mọi bản sao |
| Majority/quorum acknowledgment | Có thể tăng mức bảo đảm ghi trên nhiều replica theo giao thức | Không tự thay thế backup, cũng không giống nhau ở mọi hệ |
| Backup/snapshot | Phục hồi sau sự cố hoặc thao tác sai ở mốc có bản sao | Không thường cung cấp commit mới nhất tức thời |
| Transaction log/audit | Theo dõi lịch sử và hỗ trợ một số dạng phục hồi | Không phải mọi audit log đều là nguồn khôi phục transaction |

**Điểm phải ghi trong thiết kế:** “commit thành công” có nghĩa **đã durable ở đâu, trên bao nhiêu bản sao, và chịu được loại lỗi nào**?

## 9. Kết nối ACID với một bất biến cụ thể

Trở lại thao tác giữ 3 chiếc `SKU-100` cho đơn `O-501`:

| Thuộc tính | Cần bảo vệ điều gì? | Nếu thiếu có thể xảy ra |
| --- | --- | --- |
| **Atomicity** | Trừ tồn và tạo reservation cùng commit | Tồn bị trừ nhưng không có đơn giữ hàng |
| **Consistency** | Không âm tồn, tổng bộ đếm đúng, reservation hợp lệ | Cấp vượt tồn hoặc reservation sai số lượng |
| **Isolation** | Hai request cạnh tranh không cùng tiêu dùng một số lượng còn lại | Oversell/lost update/write skew |
| **Durability** | Sau khi báo giữ hàng thành công, dữ liệu đã commit chịu được lỗi theo cam kết | Restart rồi mất reservation đã xác nhận |

Nhưng hãy quan sát: **ACID là khung bảo đảm cho transaction**, không phải đặc tả nghiệp vụ đầy đủ. Hệ thống còn cần xử lý:

- Một request gửi lặp lại sau timeout.
- Client không biết chắc transaction đã commit hay chưa.
- Reservation hết hạn.
- Cổng thanh toán ở ngoài database.
- Email hoặc thông báo đã gửi.
- Sự kiện đến trễ hoặc bị xử lý lặp.
- Các mức độ mới dữ liệu ở read model/index phụ.

Những vấn đề đó liên quan **idempotency, state machine, giao thức workflow và observability**, cần được thiết kế cùng ACID.

## 10. Tối ưu ranh giới transaction: một document hay nhiều document?

Nếu invariant chỉ là:

\[
available \ge 0,\quad available+reservedTotal=capacity
\]

và tất cả các trường ở **một document inventory**, một conditional update nguyên tử có thể đủ:

~~~javascript
db.inventory.updateOne(
  {
    _id: "SKU-100",
    available: { $gte: 3 }
  },
  {
    $inc: {
      available: -3,
      reservedTotal: 3
    }
  }
);
~~~

Nếu cần **reservation** ở document riêng, invariant được mở rộng:

~~~text
inventory.available + inventory.reservedTotal = capacity
reservation[requestId] tồn tại khi hàng đã được giữ thành công
Một requestId chỉ nhận đúng một kết quả cấp phát
~~~

Khi đó ranh giới atomicity có thể cần bao trùm **hai collection** hoặc dùng một thiết kế khác, chẳng hạn nhúng reservation vào cùng aggregate nếu nhỏ và có giới hạn.

### Không gom vô hạn vào một document

Một SKU nổi tiếng có thể có hàng triệu reservation. Nhúng tất cả vào một document chỉ để có atomicity một-document có thể dẫn đến:

- Document vượt giới hạn kích thước.
- Hot document gây tranh chấp ghi.
- Khó truy vấn, xóa và giới hạn vòng đời từng reservation.
- Phình chi phí đọc/ghi một record.

Vì vậy nên chọn **ranh giới nguyên tử nhỏ nhất đủ để giữ invariant nhưng vẫn vận hành được**, rồi dùng transaction nhiều record hoặc mô hình phối hợp khi vượt ranh giới.

## 11. Ví dụ MongoDB: reservation và tồn kho trong một transaction

MongoDB hỗ trợ **atomicity trong một document** và **multi-document transactions** trong những triển khai được hỗ trợ. Ví dụ sau minh họa một nghiệp vụ:

~~~text
Input:
  requestId = "REQ-501"
  sku       = "SKU-100"
  quantity  = 3

Transaction:
  1. Conditional update inventory
  2. Insert reservation với _id=requestId
  3. Commit
~~~

### 11.1. Schema tối thiểu

~~~javascript
// inventory
{
  _id: "SKU-100",
  capacity: 5,
  available: 5,
  reservedTotal: 0
}

// reservations (sau khi được chấp nhận)
{
  _id: "REQ-501",
  sku: "SKU-100",
  quantity: 3,
  status: "RESERVED"
}
~~~

Để đơn giản, dùng `_id` của reservation chính là `requestId`. MongoDB có uniqueness theo `_id` trong collection; điều đó giúp bảo vệ một phần cơ chế **không ghi hai reservation có cùng ID**. Trong hệ thật phải bổ sung tenant scope và quy tắc xác nhận request cũ có cùng payload.

### 11.2. Pseudocode MongoDB Node.js Driver

Đoạn mã này là **minh họa cấu trúc transaction**, giả định đã kết nối đến MongoDB có hỗ trợ transactions, collection và document nguồn được tạo hợp lệ. Không sử dụng mã như một dịch vụ đặt hàng production hoàn chỉnh.

~~~javascript
async function reserveInventory(client, input) {
  const { requestId, sku, quantity } = input;

  if (typeof requestId !== "string" || requestId.length === 0) {
    throw new Error("Invalid requestId");
  }
  if (typeof sku !== "string" || sku.length === 0) {
    throw new Error("Invalid sku");
  }
  if (!Number.isSafeInteger(quantity) || quantity <= 0) {
    throw new Error("quantity must be a positive safe integer");
  }

  const database = client.db("inventory_training");
  const inventory = database.collection("inventory");
  const reservations = database.collection("reservations");
  const session = client.startSession();

  try {
    const outcome = await session.withTransaction(
      async () => {
        const stockUpdate = await inventory.updateOne(
          {
            _id: sku,
            available: { $gte: quantity }
          },
          {
            $inc: {
              available: -quantity,
              reservedTotal: quantity
            }
          },
          { session }
        );

        if (stockUpdate.matchedCount !== 1) {
          throw new Error("INSUFFICIENT_STOCK");
        }

        // _id=requestId sẽ chặn tạo hai reservation trùng ID.
        await reservations.insertOne(
          {
            _id: requestId,
            sku,
            quantity,
            status: "RESERVED"
          },
          { session }
        );

        // Đây chỉ là giá trị tính toán, không phải response gửi
        // ra mạng trước khi transaction commit thành công.
        return {
          requestId,
          sku,
          quantity,
          status: "RESERVED"
        };
      },
      {
        readConcern: { level: "snapshot" },
        writeConcern: { w: "majority" }
      }
    );

    return outcome;
  } finally {
    await session.endSession();
  }
}
~~~

Các điểm đáng chú ý:

1. **Kiểm tra `quantity` trước transaction** để tránh trừ tồn bằng số âm hoặc số không phải nguyên.
2. Điều kiện `available >= quantity` nằm **ngay trong update**, không chỉ trong một lệnh `findOne` ở client.
3. Cả `updateOne` và `insertOne` nhận **cùng `session`**.
4. Nếu insert reservation bị lỗi và transaction không commit, thay đổi tồn trong transaction cũng bị hủy theo atomicity của transaction.
5. `withTransaction` xử lý commit/abort và có thể thực hiện retry theo các điều kiện của driver; callback không được chứa side effect ngoài DB không idempotent.
6. Chỉ coi thao tác được chấp nhận sau khi transaction **commit thành công theo kết quả driver**, không gửi “success” trước đó.
7. `readConcern: snapshot` và `writeConcern: majority` là những lựa chọn có ý nghĩa cụ thể trong MongoDB; chúng **không biến mọi transaction thành serializable** và không thay thế việc đánh giá conflict, retry và durability của deployment.

### 11.3. Hai request giữ hàng đồng thời

Giả sử:

~~~text
Available ban đầu: 5

REQ-A muốn 4
REQ-B muốn 3
~~~

Cả hai có thể bắt đầu transaction gần như cùng lúc. Nhưng vì chúng đều phải **sửa cùng document inventory** theo điều kiện đủ hàng, DBMS cần xử lý tranh chấp tương ứng; một transaction có thể bị abort/retry hoặc điều kiện cập nhật không còn đúng sau retry.

Không được thiết kế logic “đọc được available=5 trên snapshot nên chắc chắn commit thành công”. **Commit và conflict handling** mới quyết định yêu cầu nào được xác nhận. Một kết quả đúng có thể là:

~~~text
REQ-A commit 4:
  available=1, reservedTotal=4

REQ-B thử lại hoặc kiểm tra điều kiện:
  available=1 < 3
  → không chấp nhận
~~~

Hoặc ngược lại, REQ-B commit 3 rồi REQ-A bị từ chối.

### 11.4. Giới hạn của ví dụ

Đoạn mã chưa xử lý đầy đủ:

- Một request ID **đã commit** nhưng client gọi lại.
- Phân biệt “không đủ tồn” với “SKU không tồn tại”.
- Một request ID trùng nhưng payload khác.
- Reservation bị hủy hoặc hết hạn.
- Conflict/retry/backoff ở mọi lỗi triển khai.
- Telemetry, auditing, validation schema và quyền theo tenant.
- Đơn hàng, thanh toán, outbox và hệ thống kho bên ngoài.

Những giới hạn này cần được ghi rõ, thay vì tuyên bố rằng vài dòng transaction đã giải quyết toàn bộ đặt hàng.

## 12. Chứng minh invariant cho phép cấp phát

Một bài thiết kế tốt không chỉ có code; nó cần giải thích **vì sao các phép chuyển bảo toàn điều kiện**.

Giả sử trạng thái trước một reservation:

\[
available \ge 0,\qquad
reservedTotal \ge 0,\qquad
available+reservedTotal=capacity
\]

Với một yêu cầu `q > 0`:

**Trường hợp A — không đủ hàng:**

\[
available < q
\]

Điều kiện update không khớp, transaction không commit reservation. Trạng thái hợp lệ trước đó không đổi.

**Trường hợp B — đủ hàng và transaction commit:**

\[
\begin{aligned}
available' &= available-q\\
reservedTotal' &= reservedTotal+q
\end{aligned}
\]

Khi `available >= q`, ta có:

\[
available' \ge 0
\]

Và:

\[
\begin{aligned}
available'+reservedTotal'
&=(available-q)+(reservedTotal+q)\\
&=available+reservedTotal\\
&=capacity
\end{aligned}
\]

Do đó `I_1`–`I_3` được bảo toàn nếu mọi đường ghi liên quan tuân thủ cùng quy tắc.

Nếu transaction còn thêm đúng một reservation `quantity=q` và không có thao tác khác làm sai bộ đếm, điều kiện tổng `I_4` cũng được duy trì qua một bước commit.

**Giả định cần nêu:** trạng thái ban đầu đúng; không có admin script ghi riêng `available`, `reservedTotal`; không có giá trị tràn kiểu số; cùng một request không bị áp dụng lặp mà không kiểm soát; các thao tác huỷ/nhập kho được chứng minh riêng.

Atomicity, isolation và constraint đúng là những điều kiện để lập luận quy nạp này có hiệu lực khi có nhiều transaction đồng thời.

## 13. Idempotency: ACID chưa bảo đảm “mỗi request chỉ xử lý một lần”

Xét tình huống mạng:

~~~text
Client gửi REQ-501 reserve(3)
        │
        ▼
Database transaction commit thành công
        │
        X  Phản hồi bị mất
        │
        ▼
Client timeout, không biết đã commit chưa
        │
        ▼
Client retry REQ-501
~~~

Nếu server coi lần retry là một yêu cầu mới, hệ có thể giữ thêm 3 chiếc dù mỗi transaction riêng lẻ vẫn **ACID**.

**Idempotency** là yêu cầu bổ sung: cùng một ý định nghiệp vụ với cùng `requestId` không được tạo thêm kết quả tác động lặp.

### Cách tiếp cận

- Client tạo **idempotency key/request ID ổn định** cho một yêu cầu.
- DB ghi một record định danh request cùng với phần cập nhật nghiệp vụ trong ranh giới nguyên tử phù hợp.
- Nếu cùng ID xuất hiện lần nữa, server đọc **kết quả đã commit** và trả lại thay vì cấp phát lại.
- Nếu cùng ID nhưng payload khác, báo **xung đột** thay vì mặc định coi là request cũ hợp lệ.
- Giữ ID và trạng thái đủ lâu so với thời gian mà client có thể retry.

Trong ví dụ MongoDB, `_id=requestId` ngăn **hai reservation cùng ID** được commit thành công trong collection. Nếu transaction thứ hai cố ghi trùng ID, nó phải thất bại và rollback; phần giảm inventory của transaction đó không được commit một mình.

Nhưng code mẫu chưa **trả lại kết quả đã commit của yêu cầu cũ**. Muốn hoàn chỉnh, tầng API phải xử lý lỗi trùng, truy vấn reservation có thẩm quyền, so sánh `sku/quantity` và trả trạng thái đã lưu. Với lỗi kết quả commit không rõ, client phải dùng cùng ID khi truy vấn lại hoặc retry.

### Lưu trạng thái thất bại có cần không?

Nếu request hợp lệ nhưng **không đủ hàng**, một hệ có thể:

- Trả thất bại nhưng **không lưu kết quả**; retry sau khi có hàng có thể thành công.
- Hoặc lưu kết quả `REJECTED_INSUFFICIENT_STOCK` theo request ID và lần retry phải nhận cùng kết quả.

Hai ngữ nghĩa đều có thể hợp lệ tùy sản phẩm, nhưng khác nhau. Hãy xác định idempotency contract trước khi triển khai.

### “Exactly once” cần được diễn đạt cẩn thận

Mạng, client retry và crash khiến một lời gọi có thể được gửi nhiều lần. Thay vì tuyên bố chung “mọi message xử lý exactly once”, hãy thiết kế **effectively-once business effect** trong phạm vi rõ, nhờ unique ID, conditional update, transaction và xử lý lặp.

**ACID bảo vệ một transaction; idempotency bảo vệ tác động của một ý định qua nhiều lần gửi/nhận.**

## 14. Những trạng thái kết quả khi commit không rõ ràng

Một API gọi database có thể gặp:

| Trạng thái từ góc nhìn client | Thực tế có thể xảy ra | Hướng xử lý |
| --- | --- | --- |
| Nhận success | Commit đã được xác nhận theo chính sách | Trả kết quả nghiệp vụ đã chốt |
| Nhận lỗi validation | Request không hợp lệ | Sửa input, không retry nguyên xi |
| Điều kiện không khớp | Không đủ tồn hoặc không thỏa ràng buộc | Trả từ chối theo hợp đồng |
| Transaction conflict | Có thao tác cạnh tranh | Retry cả transaction theo chính sách, có giới hạn |
| Timeout khi đang commit | Có thể commit hoặc chưa | Tra cứu theo request ID, retry idempotently |
| Mất kết nối trước khi nhận phản hồi | Kết quả chưa chắc chắn | Không tự suy luận là thất bại hoàn toàn |

Điểm quan trọng là **timeout không tương đương rollback**. Một lần ghi đã commit có thể không gửi được phản hồi về client.

Nếu ứng dụng thấy timeout rồi gọi lại bằng **request ID mới**, tính nguyên tử của từng lần gọi không ngăn được tác động trùng. Nếu ứng dụng gửi email “thành công” trước commit, transaction abort sau đó cũng không thể thu hồi email.

## 15. Trạng thái nghiệp vụ và các phép chuyển có điều kiện

ACID hữu ích khi bảo vệ **state machine**. Ví dụ:

~~~text
PENDING → RESERVED → PAID → SHIPPED
   │          │
   ▼          ▼
CANCELLED  CANCELLED
~~~

Không phải mọi mũi tên đều hợp lệ. Ví dụ một đơn `CANCELLED` không được chuyển thẳng thành `SHIPPED` chỉ vì client gửi lại request cũ.

Một conditional update có thể dùng:

~~~javascript
const result = await db.collection("orders").updateOne(
  {
    _id: "O-501",
    status: "RESERVED"
  },
  {
    $set: {
      status: "PAID"
    },
    $inc: {
      revision: 1
    }
  }
);

if (result.matchedCount !== 1) {
  // Trạng thái đã thay đổi, đơn không tồn tại hoặc điều kiện sai.
}
~~~

Thao tác một document này giúp ngăn hai request cùng tùy tiện áp dụng một chuyển trạng thái từ bản cũ, miễn tất cả writer đều tuân thủ state machine.

### Optimistic concurrency bằng revision

Nếu application đọc order `revision=7` rồi muốn sửa:

~~~javascript
db.orders.updateOne(
  {
    _id: "O-501",
    revision: 7
  },
  {
    $set: { deliveryNote: "Giao giờ hành chính" },
    $inc: { revision: 1 }
  }
);
~~~

Chỉ một writer đã đọc revision 7 có thể cập nhật nó thành 8 theo cùng phép so khớp; writer khác cần đọc lại và quyết định merge/retry.

**Compare-and-set/conditional update** thường là cơ chế đủ đơn giản cho invariant trên một record. Không nhất thiết dùng transaction nhiều record cho mọi lần đổi một field.

## 16. DynamoDB: conditional write và transaction nhiều item

**Amazon DynamoDB** có các thao tác ghi với **ConditionExpression** và hỗ trợ **transaction nhiều item** qua các API như `TransactWriteItems`/`TransactGetItems` theo các giới hạn hiện hành của dịch vụ.

### Một item: conditional update

Giả sử item:

~~~json
{
  "pk": "SKU#100",
  "available": 5,
  "reservedTotal": 0
}
~~~

Yêu cầu trừ 3 có thể được diễn đạt bằng một conditional update (ví dụ cấu trúc mức thấp):

~~~javascript
const updateInventory = {
  TableName: "Inventory",
  Key: {
    pk: { S: "SKU#100" }
  },
  UpdateExpression:
    "SET available = available - :q, " +
    "reservedTotal = reservedTotal + :q",
  ConditionExpression:
    "attribute_exists(pk) AND available >= :q",
  ExpressionAttributeValues: {
    ":q": { N: "3" }
  }
};
~~~

Nếu điều kiện không đúng, yêu cầu update thất bại thay vì trừ tồn âm. Đây là đường bảo vệ invariant cục bộ trên **một item**, với điều kiện kiểu số và trạng thái ban đầu hợp lệ.

### Nhiều item: TransactWriteItems

Nếu còn phải tạo một reservation riêng, một transaction logic có thể gồm:

~~~javascript
const request = {
  TransactItems: [
    {
      Update: {
        TableName: "Inventory",
        Key: {
          pk: { S: "SKU#100" }
        },
        UpdateExpression:
          "SET available = available - :q, " +
          "reservedTotal = reservedTotal + :q",
        ConditionExpression:
          "attribute_exists(pk) AND available >= :q",
        ExpressionAttributeValues: {
          ":q": { N: "3" }
        }
      }
    },
    {
      Put: {
        TableName: "Reservations",
        Item: {
          pk: { S: "REQ#501" },
          sku: { S: "SKU#100" },
          quantity: { N: "3" },
          status: { S: "RESERVED" }
        },
        ConditionExpression: "attribute_not_exists(pk)"
      }
    }
  ]
};
~~~

Đây là **ví dụ payload để minh họa API**, không phải một lần gọi SDK đầy đủ. Phải dùng đúng kiểu request, quyền, quota, validation, và cách xử lý lỗi/cancellation của thư viện tương ứng.

Trong cùng một transaction DynamoDB ở phạm vi được hỗ trợ, hệ không được commit chỉ thao tác update inventory mà bỏ thao tác put reservation.

**Những giới hạn cần nhớ:**

- DynamoDB transactions có **phạm vi và quota cụ thể**, không phải transaction tùy ý trên mọi tài nguyên toàn thế giới.
- Transaction cấp bảo đảm mạnh cho đường thao tác được hỗ trợ **không khiến GSI trở thành strongly consistent**; GSI vẫn có cơ chế cập nhật bất đồng bộ.
- Global tables và replication giữa các vùng có ngữ nghĩa riêng; không được suy luận một transaction ở một Region là atomic/serializable theo nghĩa toàn bộ các Region.
- Các thao tác có thể cạnh tranh, bị hủy và cần retry/idempotency.
- Không thay transaction bằng “Query GSI không thấy reservation thì Put” nếu cần uniqueness mạnh.

## 17. Redis: lệnh nguyên tử, MULTI/EXEC và điều không được giả định

Redis thường xử lý một lệnh theo ngữ nghĩa nguyên tử của lệnh tương ứng trong phạm vi instance thực thi. Nó còn có **`MULTI`/`EXEC`**, **`WATCH`** và scripting để phối hợp nhiều thao tác.

### Một lệnh nguyên tử không bằng toàn bộ workflow

~~~redis
DECRBY inventory:SKU-100:available 3
INCRBY inventory:SKU-100:reserved 3
~~~

Hai lệnh riêng lẻ không tự cung cấp một kiểm tra “đủ hàng” nguyên tử với cả hai thay đổi. Nếu không có điều kiện và phối hợp phù hợp, số tồn có thể âm hoặc trạng thái bị cập nhật giữa hai lệnh.

### MULTI/EXEC

~~~redis
MULTI
DECRBY inventory:SKU-100:available 3
INCRBY inventory:SKU-100:reserved 3
EXEC
~~~

Những lệnh bên trong được thực thi thành một nhóm **không bị các lệnh của client khác chen vào giữa** trên Redis instance theo ngữ nghĩa của `MULTI/EXEC`. Tuy nhiên:

- Chỉ nhóm lệnh đó **không kiểm tra** tồn có đủ 3.
- `MULTI/EXEC` **không phải transaction SQL với rollback toàn bộ khi có lỗi thực thi của một lệnh**. Một số lỗi runtime trong nhóm không làm các lệnh đã chạy được đảo ngược.
- Durability của kết quả vẫn phụ thuộc persistence/AOF/sync/replication và cấu hình.

Vì vậy không được coi `MULTI/EXEC` là ACID đầy đủ tương đương mọi DBMS giao dịch.

### WATCH để kiểm soát tranh chấp

Một luồng có thể:

~~~text
WATCH inventory key(s)
GET available
Nếu available < q:
    UNWATCH
    trả không đủ hàng
Ngược lại:
    MULTI
    DECRBY available q
    INCRBY reserved q
    EXEC
Nếu EXEC không thực hiện vì key đã đổi:
    retry từ bước đọc, có giới hạn
~~~

Đây là **pseudocode**; dùng `WATCH` chính xác thế nào phải xét khóa nào có thể đổi, kiểu dữ liệu, retry và tình huống lỗi. Một Lua script được viết cẩn thận cũng có thể kiểm tra và cập nhật trong một lần chạy nguyên tử trên Redis, nhưng **script bị lỗi sau khi đã ghi không mặc định rollback những thay đổi đã thực hiện**.

Không nên lưu số dư tiền hoặc reservation quan trọng trên một Redis cache có eviction policy cho phép mất key rồi tự coi nó là nguồn dữ liệu bền vững, trừ khi kiến trúc đã chủ động chấp nhận và xử lý rủi ro đó.

## 18. Cassandra: LWT khác transaction nhiều record kiểu SQL

**Apache Cassandra** dùng mô hình phân tán theo partition và replica. Những khái niệm cần phân biệt:

- **Ghi bình thường** theo mô hình consistency level của Cassandra.
- **Batch** để gom các mutation với ngữ nghĩa/đảm bảo riêng.
- **Lightweight transaction (LWT)** dựa trên cơ chế compare-and-set/Paxos theo phạm vi hỗ trợ, thường dùng `IF`.

### Conditional update với LWT

Giả sử bảng:

~~~sql
CREATE TABLE stock_by_sku (
    sku text PRIMARY KEY,
    available int,
    reserved_total int,
    revision int
);
~~~

Ứng dụng đọc:

~~~text
sku = SKU-100
available = 5
reserved_total = 0
revision = 7
~~~

Rồi muốn trừ 3 bằng một compare-and-set:

~~~sql
UPDATE stock_by_sku
SET available = 2,
    reserved_total = 3,
    revision = 8
WHERE sku = 'SKU-100'
IF revision = 7;
~~~

**Ý nghĩa:** chỉ áp dụng update nếu revision còn khớp. Nếu một writer khác đã cập nhật revision, điều kiện `IF` không khớp; ứng dụng phải đọc lại và tính phép chuyển mới, không được cố ghi giá trị dựa trên snapshot cũ.

Đây là ví dụ **LWT trên một row/partition** để bảo vệ invariant cục bộ, không phải cú pháp transaction tùy ý trên các row thuộc nhiều partition.

### Batch không tự tạo isolation nhiều partition

Một Cassandra `BATCH` có thể gom nhiều mutation, nhưng **không được suy luận rằng logged batch = một transaction ACID SQL với isolation và rollback nhiều record**. Logged batch có mục tiêu bảo đảm giao các mutation theo cơ chế của Cassandra, có chi phí batchlog và tính chất atomicity cụ thể; nó không cho phép ứng dụng tự động dựa vào snapshot nhất quán và kiểm tra ràng buộc xuyên nhiều partition như một transaction serializable.

Nếu cần invariant “không vượt quota toàn tenant” trải nhiều partition, phải thiết kế cơ chế phối hợp, cách nhóm dữ liệu hoặc nguồn có thẩm quyền phù hợp; **không chỉ bọc nhiều UPDATE trong BATCH** rồi tuyên bố ACID.

### Khi nào LWT hợp lý?

- Unique claim/compare-and-set trên một key.
- Chuyển trạng thái có điều kiện.
- Bảo vệ một phiên bản trên phạm vi mà Cassandra cho phép.

**Đánh đổi:** LWT tốn thêm phối hợp/round trip và có thể tăng latency so với ghi thông thường. Không nên dùng LWT cho mọi event ghi khối lượng lớn nếu không có invariant tương ứng cần bảo vệ.

## 19. Một bảng đối chiếu các đường bảo vệ invariant

| Hệ hoặc cơ chế | Ranh giới nổi bật | Có thể giúp bảo vệ điều gì? | Cần chú ý |
| --- | --- | --- | --- |
| **MongoDB single-document update** | Một document | Trừ tồn có điều kiện, state transition | Không tự cập nhật record khác |
| **MongoDB multi-document transaction** | Các thao tác cùng session transaction trong phạm vi hỗ trợ | Inventory + reservation cùng commit | Snapshot không tự thành serializable, conflict/retry, chi phí |
| **DynamoDB conditional write** | Một item/thao tác | Không ghi nếu điều kiện sai | Không tự bảo đảm nhiều item cùng commit |
| **DynamoDB TransactWriteItems** | Transaction nhiều item theo giới hạn dịch vụ | Atomicity/điều kiện nhiều item | Quota, contention, GSI eventual, phạm vi Region |
| **Redis một lệnh/script/MULTI** | Instance/khóa và ngữ nghĩa của lệnh | Atomic read-modify-write được thiết kế đúng | MULTI không rollback runtime error, durability riêng |
| **Cassandra LWT** | Conditional mutation trên phạm vi được hỗ trợ | Compare-and-set và tranh chấp cập nhật | Coordination cost, không là transaction tùy ý nhiều partition |
| **Read model/event-driven projection** | Đường đồng bộ khác nguồn | Truy vấn nhanh theo access pattern | Có lag/retry/duplicate; không tự có invariant tức thời |
| **Saga/workflow nhiều service** | Nhiều local transactions | Tiến trình nghiệp vụ và bù trừ | Có trạng thái trung gian, không tương đương một ACID transaction toàn cục |

Mục tiêu của bảng không phải xếp hạng DBMS. Cùng một invariant có thể được bảo vệ bằng **một record có điều kiện**, **transaction** hoặc **thiết kế dữ liệu khác** tùy phạm vi và workload.

## 20. Khi thao tác đi qua nhiều dịch vụ: vì sao ACID của một DB không đủ?

Hệ thống đặt hàng thường kết hợp:

~~~text
Order service DB
Inventory service DB
Payment provider
Notification service
~~~

Giả sử:

~~~text
1. Order DB tạo O-501
2. Inventory DB giữ 3 chiếc
3. Payment provider thu tiền
4. Email service gửi xác nhận
~~~

Một transaction của Order DB không thể mặc định rollback số tiền đã trừ ở Payment provider. Đó là bài toán **distributed workflow**, không đơn giản là một transaction trong một DBMS.

### Mẫu saga/trạng thái nghiệp vụ

~~~text
PENDING
   │
   ▼
RESERVING_STOCK
   │ thành công
   ▼
AWAITING_PAYMENT
   │ thành công
   ▼
CONFIRMED

Nếu thất bại ở một bước:
  → CANCELED hoặc COMPENSATING
  → giải phóng reservation khi phù hợp
~~~

Saga gồm các **local transactions** và những bước bù trừ, retry hoặc trạng thái chờ. Nó không bảo đảm toàn bộ quy trình **không bao giờ có trạng thái trung gian**. Thay vào đó, nghiệp vụ phải xác định:

- Trạng thái nào được người dùng nhìn thấy?
- Một reservation được giữ tối đa bao lâu?
- Khi payment thành công nhưng order chưa cập nhật, retry/đối soát ra sao?
- Nếu refund thất bại, ai có trách nhiệm xử lý?
- Làm sao để không giải phóng tồn hai lần?

### Compensation không phải rollback vật lý

Đã gửi email thì không thể “thu hồi” chắc chắn email khỏi hộp thư. Đã thanh toán thì có thể tạo **refund** như một giao dịch mới, nhưng không phải xóa lịch sử thanh toán cũ.

Do đó, **compensation là một thao tác nghiệp vụ mới**, có thể có lỗi và cần idempotency riêng. Không gọi saga là ACID toàn cục chỉ vì cuối cùng một số bước có thể bù trừ.

## 21. Transactional outbox: commit dữ liệu và sự kiện cùng nhau

Một lỗi hay gặp:

~~~text
1. Commit order=PAID vào DB → thành công
2. Publish OrderPaid event → process crash

Kết quả:
  Order đã PAID
  Hệ thống khác không biết có sự kiện
~~~

Đảo thứ tự cũng nguy hiểm:

~~~text
1. Publish OrderPaid event → thành công
2. Commit order=PAID → thất bại

Kết quả:
  Consumer hành động dựa trên event không có trạng thái nguồn tương ứng
~~~

**Transactional outbox** là một hướng giải quyết khi DB hỗ trợ transaction trên những record liên quan:

~~~text
BEGIN TRANSACTION
  Update order=PAID
  Insert outbox event OrderPaid(orderId, eventId, version)
COMMIT
           │
           ▼
Outbox publisher đọc event đã commit
           │
           ▼
Gửi tới broker, retry nếu cần
           │
           ▼
Consumer xử lý idempotently
~~~

Ưu điểm: cập nhật trạng thái nguồn và việc ghi một event **để phát đi** được commit cùng nhau trong DB. Nhưng outbox **không tự bảo đảm broker chỉ nhận event đúng một lần**; publisher có thể gửi lại sau timeout. Consumer phải dùng `eventId`, version hoặc deduplication để tránh tác động trùng.

Nếu DBMS không hỗ trợ transaction phù hợp, cần cơ chế khác như change data capture/streaming gắn với commit log hoặc một protocol trạng thái có thể phục hồi. Không chỉ thêm collection `outbox` bằng hai lệnh ghi độc lập rồi gọi đó là transactional outbox.

## 22. Khi nào không nên mở một transaction thật dài?

Giao dịch nhiều record thường có chi phí:

- Giữ snapshot/metadata/lock hoặc tài nguyên concurrency.
- Tăng nguy cơ conflict khi nhiều request sửa cùng dữ liệu.
- Tăng thời gian chờ và latency p95/p99.
- Gây áp lực lên storage engine, replication hoặc transaction coordinator.
- Có thể có giới hạn thời gian, số item hoặc kích thước do DBMS quy định.

Vì vậy tránh dạng:

~~~text
BEGIN TRANSACTION
  Đọc inventory
  Chờ gọi HTTP đến payment provider 8 giây
  Chờ gửi email 3 giây
  Update order
COMMIT
~~~

Thời gian chờ mạng ngoài DB có thể làm transaction kéo dài, tăng tranh chấp và khiến lỗi phức tạp hơn. Nên cố gắng:

1. **Chuẩn bị dữ liệu đầu vào và validation** trước transaction nếu không làm mất tính đúng đắn.
2. Trong transaction chỉ thực hiện **những đọc/ghi thực sự cần atomicity/isolation**.
3. Commit nhanh.
4. Thực hiện tác vụ ngoài DB qua trạng thái/outbox/workflow phù hợp.
5. Nếu conflict, retry có giới hạn, backoff và giữ cùng idempotency ID.

Đừng tách một bước **bắt buộc cùng commit** ra ngoài chỉ để giảm thời gian transaction; phải xác định invariant trước, tối ưu sau.

## 23. Những nhầm lẫn khi dùng ACID trong NoSQL

| Nhận định | Vấn đề | Cách hiểu chính xác hơn |
| --- | --- | --- |
| “NoSQL không có transaction.” | Nhiều hệ có atomic update và một số có transaction nhiều record | Xem phạm vi và bảo đảm cụ thể |
| “Có ACID thì không cần validation.” | Transaction có thể commit dữ liệu sai nghiệp vụ | Phát biểu và cưỡng chế invariant |
| “Một lệnh update là nguyên tử nên toàn bộ request nguyên tử.” | Request có thể sửa nhiều record/hệ | Định nghĩa ranh giới transaction |
| “Consistency của ACID giống eventual consistency.” | Hai khái niệm thuộc tầng khác nhau | Phân biệt invariant với độ mới replica |
| “Snapshot isolation luôn ngăn write skew.” | Hai transaction có thể sửa hai record riêng | Kiểm tra serializability hoặc thiết kế điểm xung đột |
| “Durable nghĩa là không bao giờ mất dữ liệu.” | Có phạm vi lỗi, sync, replication, backup | Mô tả failure model và ACK |
| “Timeout nghĩa là rollback.” | Commit có thể thành công nhưng phản hồi mất | Truy vấn/retry idempotently |
| “Mọi transaction retry là an toàn.” | Callback có thể gửi email/thu tiền lặp | Không có side effect không idempotent trong callback |
| “Có unique index phụ thì check-then-insert an toàn ở mọi DBMS.” | Index/đường đọc có thể eventual hoặc không unique | Dùng cơ chế uniqueness/conditional write thực |
| “Redis MULTI có rollback như SQL.” | Một số runtime error không rollback các lệnh đã chạy | Đọc đúng semantics của Redis |
| “Cassandra BATCH tương đương multi-row ACID serializable.” | Batch và LWT có phạm vi/bảo đảm khác | Xác định partition, điều kiện và consistency |
| “GSI DynamoDB vừa ghi xong phải đọc thấy ngay.” | GSI eventual | Dùng đường đọc có bảo đảm phù hợp |
| “Saga là transaction ACID xuyên dịch vụ.” | Có trạng thái trung gian, bước bù trừ | Thiết kế state machine/retry/đối soát |
| “Outbox bảo đảm event đến consumer đúng một lần.” | Publish có thể retry và duplicate | Consumer idempotency |
| “Chỉ cần ACID để tránh oversell.” | Cần điều kiện tồn, kiểu số, retry, đường ghi khác | Bảo vệ invariant end-to-end |

## 24. Ma trận sự cố: thao tác giữ hàng phản ứng thế nào?

Giả sử transaction gồm **giảm inventory** và **tạo reservation**:

| Tình huống | Kết quả kỳ vọng theo thiết kế đúng | Vấn đề cần xử lý |
| --- | --- | --- |
| Sai `quantity=-3` | Từ chối trước ghi | Validation |
| Tồn chỉ còn 2, yêu cầu 3 | Không commit reservation | Conditional write |
| Hai request cùng giữ 4 và 3 khi còn 5 | Không thể cùng được chấp nhận | Isolation/atomic condition |
| Crash trước commit | Không để trạng thái nửa chừng được coi đã commit | Atomicity/recovery |
| Crash sau commit và ACK | Phục hồi trạng thái theo durability đã hứa | WAL/sync/replication |
| Insert reservation lỗi sau khi update inventory trong transaction | Toàn transaction abort | Atomicity |
| Request ID trùng nhưng payload khác | Báo xung đột, không cấp phát thêm | Uniqueness/idempotency |
| Response mất sau commit | Client tra theo ID hoặc retry cùng ID | Unknown outcome |
| Payment thành công nhưng order chưa xác nhận | Workflow/đối soát/bù trừ | Cross-service consistency |
| Event publish lỗi sau order commit | Outbox/CDC và retry | Reliable event delivery |
| Replica/index phụ chưa cập nhật | Không dùng đường stale để kết luận invariant mạnh | Read consistency |
| Admin sửa `available` trực tiếp | Ngăn bằng quyền/ràng buộc và quy trình sửa | Mọi write path phải giữ invariant |

### Một phản ví dụ thường bị bỏ sót

Giả sử transaction giữ hàng đã đúng nhưng script quản trị có thể chạy:

~~~javascript
db.inventory.updateOne(
  { _id: "SKU-100" },
  { $set: { available: 1000 } }
);
~~~

Trạng thái này phá `available+reservedTotal=capacity` nếu `capacity` vẫn là 5. Không có transaction nào bảo vệ invariant khi **một đường ghi khác cố ý bỏ qua quy tắc** và vẫn được cấp quyền.

Vì vậy, chứng minh đúng đắn phải nói rõ **những thao tác nào được phép cập nhật dữ liệu**, kể cả migration, job batch, admin và quy trình recovery.

## 25. Chọn mức bảo đảm theo rủi ro nghiệp vụ

Không phải mọi thao tác đều cần cùng mức transaction.

| Thao tác | Yêu cầu thường gặp | Hướng kỹ thuật |
| --- | --- | --- |
| Cập nhật nickname người dùng | Không ghi đè thay đổi bất ngờ | Atomic single-record update, optional revision |
| Thêm lượt xem trang | Có thể chấp nhận vài sai lệch nếu nghiệp vụ cho phép | Counter/batch/event stream tùy SLO |
| Trừ tồn để giữ đơn | Không oversell, không giữ trùng | Conditional update, transaction với reservation |
| Chuyển tiền giữa hai tài khoản | Bảo toàn tổng tiền và dấu vết bút toán | Transaction trên ledger/tài khoản hoặc giao thức tài chính phù hợp |
| Áp mã giảm giá giới hạn 100 lượt | Không cấp vượt quota, một đơn không dùng lặp | Atomic quota + unique usage record |
| Gửi email xác nhận | Chấp nhận xử lý bất đồng bộ, chống gửi trùng khi cần | Outbox/event + idempotent worker |
| Xây bảng tìm kiếm | Chấp nhận độ trễ đồng bộ nhất định | Eventual read model, replay/rebuild |
| Tạo báo cáo tổng hợp tháng | Đối soát tại một mốc dữ liệu | Batch/snapshot/cutoff version |

Một số workload **thực sự cần consistency mạnh và transaction**, một số chấp nhận **eventual convergence** có cơ chế đối soát. Không có lý do dùng transaction nhiều record cho một counter best-effort nếu chi phí vượt yêu cầu; cũng không thể dùng counter eventually consistent để bảo vệ quota tiền tệ nghiêm ngặt mà không có thiết kế bổ sung.

## 26. Ví dụ chuyển tiền: ACID bảo vệ những gì?

Giả sử ví A chuyển **300 đơn vị tiền nhỏ nhất** sang ví B, với tổng ban đầu:

~~~text
Wallet A: 1000
Wallet B: 500
Total:    1500
~~~

Trạng thái sau:

~~~text
Wallet A: 700
Wallet B: 800
Total:    1500
~~~

**Bất biến:** số dư không âm nếu nghiệp vụ cấm thấu chi; tổng không đổi khi chỉ chuyển nội bộ; có một bản ghi giao dịch đối chiếu được.

Một transaction đúng có thể cần:

~~~text
BEGIN
  Debit A if balance >= 300
  Credit B by 300
  Insert ledger transferId=TR-001
COMMIT
~~~

- **Atomicity:** không thể chỉ trừ A mà quên cộng B trong phạm vi transaction.
- **Consistency:** giữ tổng tiền và các giới hạn số dư.
- **Isolation:** hai lệnh chuyển đồng thời không dùng cùng số dư cũ để chi quá mức.
- **Durability:** sau ACK commit, các bút toán và số dư sống sót theo bảo đảm.

Nếu ví A và B ở **hai dịch vụ/DB khác nhau** mà không có transaction xuyên cả hai, workflow cần cơ chế phối hợp riêng; không thể tuyên bố cùng semantics ACID chỉ vì mỗi DB địa phương hỗ trợ transaction.

### Ledger làm nguồn có thẩm quyền

Nhiều hệ tài chính chọn sổ bút toán (*ledger*) với các entry đối ứng và invariant tổng debit/credit, thay vì coi hai trường số dư được sửa tùy ý là toàn bộ sự thật. Đó là quyết định mô hình dữ liệu và kiểm toán, không được giải quyết bởi ACID một cách tự động.

Nếu dùng integer minor units, vẫn phải kiểm tra overflow và currency. Số học chính xác và transaction isolation là **hai yêu cầu khác nhau, đều cần có**.

## 27. Ví dụ đặt vé: vì sao kiểm tra số ghế riêng lẻ chưa đủ?

Một sự kiện có 100 ghế. Bảng `seats` gồm mỗi ghế `AVAILABLE/RESERVED`.

Yêu cầu:

> “Đặt ghế A12 đúng một lần.”

Nếu mỗi ghế có một record:

~~~text
Seat A12 = AVAILABLE
~~~

một conditional update:

~~~text
UPDATE seat A12
IF status == AVAILABLE
SET status = RESERVED, reservationId = R1
~~~

có thể đủ để ngăn hai request cùng chiếm một ghế, nếu DBMS có cơ chế atomic condition phù hợp.

Nhưng yêu cầu:

> “Đặt liên tiếp ghế A12, A13, A14; hoặc không đặt ghế nào.”

cần **atomicity nhóm ba ghế** hoặc một giao thức bù trừ/giữ tạm có trạng thái rõ. Ba lần update độc lập có thể giữ được A12 và A13 rồi thất bại ở A14.

**Ranh giới transaction xuất phát từ lời hứa nghiệp vụ**, không phải mặc định “một record” hay “một request”.

## 28. Các bài tập thực hành

### Bài 1 — Phân loại A, C, I, D

Xác định thuộc tính ACID liên quan nhất trong từng tình huống:

1. Đơn hàng có reservation nhưng inventory chưa trừ.
2. Hai client cùng trừ số dư dựa vào một snapshot cũ.
3. Hệ trả commit thành công rồi restart và mất dữ liệu.
4. Ghi số lượng giữ hàng là `-5` làm tổng bộ đếm sai.

**Gợi ý:** lần lượt tập trung vào Atomicity, Isolation, Durability và Consistency/validation. Một tình huống thực tế có thể liên quan nhiều thuộc tính.

### Bài 2 — Bất biến cấp phát hàng

Một kho có `capacity=20`, `available=20`, `reservedTotal=0`. Hãy phát biểu invariant và viết công thức cập nhật cho `reserve(q)`. Chứng minh vì sao điều kiện `available >= q` và cập nhật nguyên tử bảo toàn `available + reservedTotal = capacity`.

**Gợi ý:** xét hai trường hợp điều kiện khớp/không khớp và dùng phép cộng đại số.

### Bài 3 — Hai document có cần transaction không?

Hệ lưu `inventory` trong một document và `reservations` trong collection khác. Nếu yêu cầu “mỗi reservation đã được chấp nhận phải tương ứng lượng hàng đã trừ”, liệu một `updateOne` trên inventory đủ chưa? Đề xuất ranh giới và các bước commit.

**Gợi ý:** một-document atomicity không tự bao phủ insert ở collection khác; cần multi-document transaction hoặc mô hình dữ liệu/giao thức khác.

### Bài 4 — Write skew

Hai nhân viên A/B đều đang ở trạng thái `ON_DUTY`. Mỗi người chỉ được nghỉ nếu vẫn còn ít nhất một người trực. Hai transaction cùng thấy có hai người và sửa hai record khác nhau.

Vì sao snapshot isolation có thể chưa đủ? Hãy đề xuất cách tạo một điểm tranh chấp chung hoặc dùng isolation phù hợp.

**Gợi ý:** hai transaction sửa record khác nhau, nên có thể tránh write-write conflict nhưng vẫn phá invariant “ít nhất một người trực”.

### Bài 5 — Retry sau timeout

API `reserve(2)` đã commit nhưng response bị mất. Client gửi lại với `requestId` mới. Vì sao từng transaction có ACID vẫn không chặn giữ hàng hai lần? Đề xuất contract idempotency.

**Gợi ý:** ID phải ổn định cho một ý định; cần record kết quả gắn ID và transaction/conditional write phù hợp.

### Bài 6 — Redis MULTI/EXEC

Đọc đoạn:

~~~redis
MULTI
DECRBY available 3
INCRBY reserved 3
EXEC
~~~

Nêu ít nhất ba điều còn thiếu để gọi đây là nghiệp vụ đặt hàng an toàn.

**Gợi ý:** chưa kiểm tra tồn đủ, chưa có reservation ID/idempotency, chưa có định nghĩa durability, và MULTI không có rollback kiểu SQL khi một lệnh runtime lỗi.

### Bài 7 — DynamoDB GSI

Một đơn vừa được ghi `PAID` vào base table. Query GSI theo trạng thái chưa tìm thấy đơn. Có thể kết luận transaction ghi base đã rollback không? Vì sao?

**Gợi ý:** GSI có độ trễ eventual; phải phân biệt transaction commit của nguồn và freshness của chỉ mục phụ.

### Bài 8 — Cassandra BATCH và LWT

Một ứng dụng cần bảo vệ quota theo một key trong Cassandra. Khi nào compare-and-set với `IF` hữu ích? Vì sao gom nhiều lệnh ở các partition khác nhau vào logged `BATCH` không tự tạo transaction ACID serializable?

**Gợi ý:** CAS kiểm tra revision/giá trị trong một phạm vi được hỗ trợ; batch không tự thêm snapshot isolation và predicate consistency xuyên partition.

### Bài 9 — Outbox

Order service commit `status=SHIPPED` rồi crash trước khi publish `OrderShipped`. Hãy mô tả transactional outbox giải quyết điểm đứt này ra sao. Vì sao consumer vẫn cần deduplication?

**Gợi ý:** trạng thái và outbox event được commit cùng nhau, publisher retry; gửi lại có thể tạo duplicate.

### Bài 10 — Chọn transaction boundary

Phân tích ba yêu cầu:

1. Đổi tên hiển thị trong một user document.
2. Trừ số dư một ví và ghi đúng một ledger entry.
3. Thu tiền qua cổng thanh toán và gửi email xác nhận.

Với từng yêu cầu, chỉ ra phạm vi nguyên tử cần xét và liệu một transaction DBMS duy nhất có đủ không.

**Gợi ý:** một-document update có thể đủ cho (1); (2) phụ thuộc nơi lưu ledger; (3) đi qua hệ ngoài DB, cần workflow/outbox/idempotency.

### Bài 11 — Kiểm tra cấu hình durability

Một hệ ghi WAL nhưng trả ACK trước khi WAL được sync; hệ khác chờ WAL durable và majority replica theo chính sách. Vì sao không thể chỉ nói cả hai “có WAL nên durable như nhau”?

**Gợi ý:** thời điểm ACK và failure model khác nhau; sync và replication cung cấp mức cam kết khác nhau.

### Bài 12 — Viết ma trận sự cố

Với nghiệp vụ dùng mã giảm giá tối đa 100 lượt, hãy liệt kê:

- Invariant tổng số lượt và mỗi đơn chỉ áp một lần.
- Những bước phải commit cùng nhau.
- Hai request đồng thời cần điều kiện gì.
- Xử lý retry sau timeout.
- Điều gì xảy ra nếu báo cáo dùng read model eventual.

**Gợi ý:** có thể dùng quota record với conditional update, usage record unique theo order/request và transaction trong phạm vi phù hợp; read model chỉ phục vụ hiển thị nếu được phép trễ.

## 29. Checklist thiết kế một thao tác nghiệp vụ có ACID

Trước khi triển khai, hãy ghi rõ:

### 29.1. Phạm vi nghiệp vụ

- Đầu vào hợp lệ và miền giá trị?
- Những trạng thái được phép, những chuyển trạng thái nào bị cấm?
- Bất biến nào phải **luôn đúng ngay sau commit**?
- Bất biến nào có thể hội tụ cuối cùng theo chính sách?

### 29.2. Phạm vi dữ liệu

- Tập record/document/item liên quan?
- Chúng có nằm trong một ranh giới cập nhật nguyên tử tự nhiên không?
- Có cần transaction nhiều record?
- Có dữ liệu nằm ở dịch vụ ngoài transaction DB không?

### 29.3. Đồng thời và retry

- Request cùng key có thể cạnh tranh thế nào?
- Điều kiện kiểm tra có nằm trong atomic update/transaction không?
- Isolation level có ngăn anomaly nguy hiểm không?
- Transaction có thể abort và được retry an toàn không?
- Mỗi ý định có requestId/idempotency key ổn định không?

### 29.4. Commit và sự cố

- Khi nào DB trả ACK?
- WAL/journal đã durable chưa?
- Có bao nhiêu replica xác nhận?
- Client xử lý unknown commit outcome thế nào?
- Recovery, backup, failover và đối soát thực hiện ra sao?

### 29.5. Hệ thống ngoài DB

- Có side effect nào không thể rollback?
- Có outbox/CDC để phát sự kiện sau commit không?
- Consumer có idempotency không?
- Workflow thất bại ở giữa thì bù trừ hay chờ xử lý?

### 29.6. Vận hành và kiểm chứng

- Có metric transaction conflicts/aborts/retries/latency?
- Có theo dõi invariant violations và job đối soát?
- Có kịch bản crash, failover, timeout và message duplicate?
- Tất cả đường ghi, kể cả admin, migration, batch, có tuân thủ invariant?
- Ranh giới tenant/authorization có được giữ trong transaction và query?

## 30. Mẫu đặc tả cho transaction giữ hàng

Một nhóm phát triển có thể viết tài liệu thiết kế:

~~~yaml
operation: ReserveInventory
input:
  - requestId
  - tenantId
  - sku
  - quantity
preconditions:
  - "quantity is a positive supported integer"
  - "tenant and sku are valid"
  - "available >= quantity"
businessInvariants:
  - "available >= 0"
  - "reservedTotal >= 0"
  - "available + reservedTotal = capacity"
  - "reservedTotal matches committed active reservations"
  - "one accepted effect per requestId"
transactionBoundary:
  - "conditional inventory update"
  - "reservation insert with unique requestId"
commitPolicy:
  isolation: "Explicitly selected for the DBMS and invariant"
  durability: "Explicit write concern / acknowledgment policy"
retryPolicy:
  transientConflicts: "Retry whole transaction with bounded backoff"
  unknownCommit: "Resolve using requestId"
  duplicateRequest: "Return existing result if payload matches"
excludedExternalEffects:
  - "Payment provider call"
  - "Email/SMS delivery"
events:
  publication: "Transactional outbox or approved equivalent"
  consumers: "Idempotent by eventId"
verification:
  - "Concurrent reservations exceeding available"
  - "Failure between writes before commit"
  - "Timeout after commit"
  - "Duplicate requestId"
  - "Crash/failover under configured durability"
  - "Invariant reconciliation"
~~~

Đây là **mẫu đặc tả**, không phải cấu hình trực tiếp của MongoDB, DynamoDB hay Cassandra. Những mục như isolation và durability phải được điền bằng bảo đảm của DBMS đã chọn, không viết chung chung “ACID: true”.

## 31. Tổng kết

**ACID có giá trị khi gắn từng chữ với một lời hứa nghiệp vụ cụ thể:**

1. **Atomicity** giúp những thay đổi phải đi cùng nhau không bị commit nửa chừng. Phải biết ranh giới là một document, một item hay nhiều record.
2. **Consistency** yêu cầu trạng thái sau transaction giữ các **bất biến** đã định nghĩa. Bản thân DBMS không tự biết những quy tắc nghiệp vụ chưa được biểu diễn.
3. **Isolation** quyết định cách những transaction đồng thời tương tác. Atomic update có điều kiện, compare-and-set, snapshot hoặc serializable transaction cần được chọn theo anomaly phải ngăn; snapshot không tự loại mọi write skew.
4. **Durability** là cam kết về các thay đổi đã commit qua những loại lỗi xác định. WAL, sync, replication và backup có vai trò khác nhau; tên cấu trúc lưu trữ hoặc nhãn NoSQL không tự quyết định độ bền.
5. **ACID không tự giải quyết retry, duplicate và hệ thống ngoài DB.** Idempotency key, trạng thái request, transactional outbox, saga và đối soát bổ sung tính đúng đắn cho toàn bộ quy trình.
6. **Không nên dùng transaction lớn hơn mức cần thiết**, nhưng cũng không được tách những thay đổi phải cùng commit chỉ để tăng tốc. Cần cân bằng invariant, contention, độ trễ và khả năng vận hành.

**Nguyên tắc thực hành:** trước mỗi thao tác quan trọng, hãy hỏi **“điều gì tuyệt đối không được sai?”**, viết nó thành invariant, tìm **nhóm dữ liệu tối thiểu phải thay đổi cùng nhau**, rồi kiểm tra DBMS có cung cấp đúng **atomicity, isolation và durability trong phạm vi đó** hay không. Đó là cách dùng ACID để bảo vệ tính đúng đắn của nghiệp vụ trên NoSQL, thay vì coi ACID chỉ là một khẩu hiệu kỹ thuật.
