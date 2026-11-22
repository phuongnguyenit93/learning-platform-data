# Phân biệt tính nhất quán trong ACID với nhất quán giữa các bản sao

Trong tài liệu cơ sở dữ liệu và hệ thống phân tán, từ **consistency (tính nhất quán)** được dùng theo nhiều nghĩa. Hai nghĩa dễ nhầm nhất là:

- **Consistency trong ACID:** Sau một giao dịch hợp lệ, dữ liệu có tiếp tục thỏa các ràng buộc và bất biến nghiệp vụ đã định nghĩa không?
- **Nhất quán giữa các bản sao (replica consistency):** Khi cùng một dữ liệu được lưu ở nhiều nút, các thao tác đọc/ghi trên các nút đó có thể quan sát phiên bản nào và theo thứ tự nào?

Một giao dịch chuyển tiền có thể thực hiện đúng, bảo toàn tổng số dư trên cơ sở dữ liệu chính, nhưng người dùng đọc ngay từ một bản sao vẫn thấy số dư cũ. Điều đó minh họa rằng **tính đúng đắn của giao dịch** và **độ mới của dữ liệu trên replica** là hai thuộc tính khác nhau.

## 1. Consistency trong ACID bảo vệ bất biến dữ liệu

ACID mô tả bốn thuộc tính của giao dịch:

| Thuộc tính | Ý nghĩa |
|---|---|
| **Atomicity** (nguyên tử) | Các thay đổi trong phạm vi một giao dịch được commit cùng nhau hoặc rollback theo cơ chế của DBMS. |
| **Consistency** (nhất quán) | Giao dịch hợp lệ đưa dữ liệu từ trạng thái thỏa bất biến sang trạng thái tiếp tục thỏa bất biến. |
| **Isolation** (cô lập) | Giới hạn cách các giao dịch chồng lấn tác động và nhìn thấy thao tác của nhau. |
| **Durability** (bền vững) | Thay đổi đã được xác nhận commit tồn tại bền vững theo cam kết của hệ quản trị. |

**Bất biến (invariant)** là điều kiện mà trạng thái dữ liệu phải thỏa, chẳng hạn:

- Mã đơn hàng là duy nhất.
- Mỗi dòng chi tiết đơn hàng phải tham chiếu đến một đơn hàng tồn tại.
- Số dư không được âm hoặc phải nằm trong hạn mức được cho phép.
- Một ghế ở cùng suất chiếu không thể có hai đặt chỗ đang hiệu lực.
- Một khoản chuyển tiền nội bộ phải ghi nợ và ghi có đúng số tiền theo quy tắc kế toán.

Ta có thể mô tả ACID Consistency:

```text
  S0: trạng thái hợp lệ, thỏa tập bất biến I
                  |
            Giao dịch T
                  |
  S1: trạng thái hợp lệ, vẫn thỏa tập bất biến I
                  (nếu T commit đúng)
```

Những bất biến cơ bản có thể được DBMS thực thi bằng `PRIMARY KEY`, `UNIQUE`, `FOREIGN KEY`, `CHECK`, khóa và các cơ chế giao dịch. Bất biến phức tạp có thể đòi hỏi thêm logic nghiệp vụ, lựa chọn mức isolation và xử lý các giao dịch cạnh tranh.

**DBMS không tự biết mọi quy tắc nghiệp vụ.** Nếu ứng dụng không mô hình hóa quy tắc “mỗi người chỉ sở hữu một vé cho một suất chiếu”, transaction có thể commit dù nghiệp vụ cho rằng kết quả sai. ACID Consistency là mục tiêu bảo toàn các ràng buộc đúng đắn; nó không phải phép kiểm tra ngữ nghĩa tự động cho mọi dữ liệu.

### Ví dụ: chuyển tiền trong một cơ sở dữ liệu

Giả sử tài khoản A có 500.000 đồng, tài khoản B có 200.000 đồng, và một giao dịch chuyển 100.000 đồng từ A sang B.

| Trạng thái | Số dư A | Số dư B | Tổng |
|---|---:|---:|---:|
| Trước khi chuyển | 500.000 | 200.000 | 700.000 |
| Chuyển đúng | 400.000 | 300.000 | 700.000 |
| Chỉ ghi nợ A rồi commit | 400.000 | 200.000 | 600.000 |

Hai lệnh cập nhật phải được thực hiện trong **cùng một giao dịch cục bộ**:

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 100000
WHERE id = 'A' AND balance >= 100000;
-- Ứng dụng phải kiểm tra đã cập nhật đúng 1 dòng.
-- Nếu không đúng: ROLLBACK, báo không đủ tiền hoặc tài khoản không tồn tại.

UPDATE accounts
SET balance = balance + 100000
WHERE id = 'B';
-- Nếu không cập nhật đúng 1 dòng: ROLLBACK toàn bộ.

COMMIT;
```

Một ràng buộc hỗ trợ là:

```sql
ALTER TABLE accounts
ADD CONSTRAINT balance_must_be_nonnegative
CHECK (balance >= 0);
```

`CHECK` giúp bảo vệ bất biến cục bộ “số dư của một tài khoản không âm”. Tuy nhiên, **tổng số tiền được bảo toàn qua cả hai tài khoản** là bất biến nhiều dòng, cần giao dịch bao trọn các bước và logic kiểm tra thành công trước commit. Hệ thống thanh toán thật còn cần chống yêu cầu trùng, ghi nhận bút toán, kiểm soát quyền hạn và đối soát.

### Vì sao Consistency phụ thuộc Atomicity và Isolation?

Nếu hệ thống chỉ ghi nợ A thành công rồi commit mà quên ghi có B, bất biến bảo toàn tiền bị phá vỡ. **Atomicity** cho phép rollback các cập nhật thuộc cùng giao dịch khi phát hiện lỗi trước commit.

Khi có nhiều giao dịch đồng thời, **Isolation** giúp ngăn những lịch xen kẽ gây ra dữ liệu sai. Ví dụ, hai bác sĩ đang trực; quy định phải luôn còn ít nhất một bác sĩ trực. Hai giao dịch đồng thời cùng đọc thấy hai bác sĩ đang trực, rồi mỗi giao dịch cho một người nghỉ. Chúng ghi hai dòng khác nhau, nhưng kết quả cuối có thể không còn ai trực (*write skew*). Việc từng câu SQL hợp lệ không đủ: phải bảo vệ **bất biến liên dòng** bằng cơ chế điều khiển đồng thời phù hợp, chẳng hạn giao dịch serializable cùng xử lý retry hoặc một thiết kế khóa/ràng buộc tương đương.

**Durability** lại trả lời câu hỏi khác: trạng thái đã commit được giữ lại như thế nào sau sự cố. Cả ba thuộc tính bổ trợ cho việc bảo toàn trạng thái hợp lệ, nhưng không đồng nghĩa với Consistency.

## 2. Nhất quán giữa các bản sao nói về phiên bản được quan sát

Khi một hệ thống sử dụng **replication**, cùng tập dữ liệu có thể được lưu trên nhiều nút. Một thiết kế thường gặp là **single-leader replication**:

- **Primary/leader:** nhận thao tác ghi và quyết định thứ tự cập nhật.
- **Secondary/follower/read replica:** nhận luồng thay đổi từ primary rồi áp dụng vào dữ liệu bản sao; có thể phục vụ đọc hoặc làm nút dự phòng.

```text
                  Ứng dụng
                     |
               UPDATE / COMMIT
                     |
                     v
                PRIMARY DB
                version 105
                /         \
       replication         replication
              /             \
             v               v
         REPLICA A       REPLICA B
         version 104     version 105
```

Trong lúc primary ở phiên bản 105, Replica A có thể mới áp dụng đến phiên bản 104. Replica B đã bắt kịp nhưng Replica A chưa. Hiện tượng này thường gặp khi sao chép **bất đồng bộ**: primary có thể trả kết quả commit mà chưa cần chờ mọi replica nhận và áp dụng bản ghi mới.

**Replica consistency** mô tả những bảo đảm về dữ liệu mà client có thể thấy khi đọc hoặc ghi qua các nút: độ mới của phiên bản, thứ tự cập nhật, hội tụ, quan hệ nhân quả và giới hạn dữ liệu cũ. Các bảo đảm cụ thể thay đổi theo thiết kế hệ thống.

### Ví dụ: giao dịch đúng nhưng đọc được trạng thái cũ

Một đơn hàng đang ở trạng thái `PENDING`. Ứng dụng cập nhật trên primary:

```sql
BEGIN;

UPDATE orders
SET status = 'PAID'
WHERE id = 501 AND status = 'PENDING';
-- Chỉ commit như một chuyển trạng thái thành công
-- khi cập nhật đúng 1 dòng.

COMMIT;
```

Giả sử transaction commit thành công và ràng buộc dữ liệu đều hợp lệ:

```text
 Thời gian  ──────────────────────────────────────────>

 PRIMARY:  PENDING ── commit PAID ───────────────── PAID
 REPLICA:  PENDING ─────────── PENDING ── apply ── PAID
                               ^
                               |
                   GET /orders/501 ở replica
                    trả về PENDING (stale read)
```

Ứng dụng vừa trả “thanh toán thành công”, nhưng một lần đọc lập tức từ replica vẫn trả `PENDING`. Đây là **stale read** do *replication lag*, không tự chứng minh giao dịch cập nhật vi phạm ACID Consistency.

Trong ví dụ trên, cả trạng thái cũ `PENDING` và trạng thái mới `PAID` đều có thể hợp lệ theo ràng buộc nghiệp vụ. Vấn đề là **người đọc quan sát trạng thái ở thời điểm nào**.

Một lưu ý kỹ thuật: replica **nhận bản ghi**, **ghi bền bản ghi** và **áp dụng bản ghi để truy vấn thấy được** có thể là ba thời điểm khác nhau. Vì thế, xác nhận “replica đã nhận log” chưa chắc có nghĩa mọi truy vấn trên replica ấy đã nhìn thấy giao dịch vừa commit.

## 3. Đặt hai nghĩa của Consistency cạnh nhau

| Tiêu chí | **ACID Consistency** | **Replica consistency** |
|---|---|---|
| Mục tiêu | Bảo vệ bất biến và tính hợp lệ của trạng thái | Bảo đảm cách đọc/ghi quan sát các phiên bản trên nhiều nút |
| Câu hỏi | “Giao dịch đã làm dữ liệu sai quy tắc chưa?” | “Nút này đã thấy thay đổi mới chưa, theo thứ tự nào?” |
| Đơn vị thường xét | Transaction và tập dữ liệu/ràng buộc liên quan | Lịch sử thao tác đọc/ghi và các replica |
| Lỗi minh họa | Hai người sở hữu cùng một ghế dù nghiệp vụ cấm | Đọc thấy đơn `PENDING` sau khi đã được xác nhận `PAID` |
| Công cụ thường dùng | Constraint, transaction logic, isolation, locking, validation | Giao thức replication, định tuyến đọc, session guarantee, quorum, đồng bộ |
| Có yêu cầu tất cả replica giống nhau ngay? | Không, chỉ từ thuộc tính ACID C không suy ra điều đó | Tùy mô hình consistency đã chọn |
| Có bảo đảm nghiệp vụ tự động đúng? | Chỉ với bất biến được định nghĩa và bảo vệ đúng | Không, kể cả mọi replica có cùng giá trị |

Hai dạng consistency có thể được phân tích thành hai trục độc lập:

| | Replica đã bắt kịp | Replica chưa bắt kịp |
|---|---|---|
| **Bất biến hợp lệ** | Giao dịch đúng, các bản sao đọc được kết quả mới | Giao dịch đúng trên primary, bản sao còn dữ liệu cũ |
| **Bất biến bị vi phạm** | Các bản sao đồng bộ cùng một trạng thái sai | Primary đã có trạng thái sai, replica còn giữ trạng thái trước đó |

Ví dụ, nếu ứng dụng sai logic và ghi tồn kho `quantity = -3` vào bảng không có ràng buộc chống số âm, tất cả replica có thể sao chép chính xác giá trị ấy. **Các bản sao giống nhau nhưng dữ liệu vẫn sai theo nghiệp vụ.**

Ngược lại, primary và replica tạm thời khác nhau không nhất thiết làm trạng thái của riêng từng bản sao vi phạm ràng buộc. Tuy nhiên, một quyết định nghiệp vụ dựa trên replica cũ vẫn có thể gây hậu quả nếu ứng dụng không kiểm tra lại tại điểm ghi có thẩm quyền.

## 4. Các mức nhất quán thường gặp khi đọc từ replica

Những cụm từ dưới đây mô tả **bảo đảm quan sát**, không phải những biến thể của chữ C trong ACID.

### 4.1. Eventual consistency — nhất quán cuối cùng

Nếu không có cập nhật mới, mạng hoạt động đủ lâu và cơ chế truyền/giải quyết xung đột hoàn thành, các bản sao cuối cùng sẽ **hội tụ** về trạng thái tương ứng.

Mô hình này có thể cho phép stale read. **Eventual consistency tự nó không cam kết một lần đọc sẽ bắt kịp trong chính xác bao nhiêu giây.** Ví dụ, một hệ thống thống kê lượt xem có thể chấp nhận số liệu hiển thị chậm.

### 4.2. Read-your-writes — đọc thấy thay đổi mình vừa ghi

Sau khi một phiên người dùng ghi thành công, các lần đọc kế tiếp trong phiên phải thấy thay đổi ấy hoặc phiên bản mới hơn.

```text
POST /profile  -> cập nhật tên thành "Lan" -> thành công
GET  /profile  -> thấy "Lan" (hoặc phiên bản mới hơn)
```

Nếu `GET` bị chuyển tới replica chưa bắt kịp, hệ thống có thể vi phạm read-your-writes. Cách giải quyết có thể là đọc từ primary sau ghi, gắn phiên với bản sao đủ mới hoặc mang theo token/offset phiên bản để chờ bản sao đạt phiên bản cần thiết.

### 4.3. Monotonic reads — đọc không quay về phiên bản cũ

Một phiên đã thấy phiên bản mới thì các lần đọc sau không được nhìn thấy phiên bản cũ hơn:

```text
GET lần 1 trên Replica B: PAID
GET lần 2 trên Replica A: PENDING  <- vi phạm monotonic reads
```

Điều này có thể xảy ra khi load balancer chuyển người dùng giữa các replica có độ trễ khác nhau. Ứng dụng cần duy trì ngưỡng phiên bản đã quan sát hoặc định tuyến phiên tới replica đủ mới.

### 4.4. Causal consistency — nhất quán nhân quả

Nếu sự kiện B phụ thuộc nhân quả vào sự kiện A, người đọc không nên quan sát B mà thiếu quan hệ cần thiết với A. Ví dụ, một bình luận phản hồi bài viết phụ thuộc vào việc bài viết đã tồn tại. Những thao tác độc lập có thể được quan sát theo thứ tự khác nhau.

Causal consistency bảo vệ thứ tự có quan hệ nhân quả; nó không bắt mọi thao tác độc lập trên toàn hệ thống tuân theo một thứ tự thời gian toàn cục.

### 4.5. Bounded staleness — có giới hạn dữ liệu cũ

Một hệ thống có thể cam kết bản sao không bị tụt quá một khoảng thời gian hoặc số phiên bản nhất định, dưới những điều kiện xác định. Ví dụ, số liệu dashboard chậm tối đa 30 giây có thể chấp nhận được, trong khi API quyết định thanh toán không nên dựa vào trạng thái có khả năng chậm 30 giây.

### 4.6. Linearizability — thao tác trông như có hiệu lực tức thời

**Linearizability** đòi hỏi mỗi thao tác đọc/ghi trên đối tượng có vẻ có hiệu lực tại một thời điểm duy nhất giữa lúc bắt đầu và kết thúc, đồng thời **tôn trọng thứ tự thời gian thực** của các thao tác đã hoàn tất.

Nếu một thao tác cập nhật sang `PAID` đã kết thúc thành công **trước khi** một thao tác đọc bắt đầu, thao tác đọc linearizable không thể trả về `PENDING` chỉ vì nó gặp replica chậm, giả sử không có cập nhật hợp lệ khác sau đó đưa trạng thái về `PENDING`.

Một hệ thống muốn bảo đảm kiểu đọc này có thể phải chờ đồng bộ hoặc từ chối phục vụ một số yêu cầu trong sự cố mạng. Cụm từ **strong consistency** trong tài liệu sản phẩm có thể chỉ linearizability hoặc một bảo đảm khác: luôn cần xem định nghĩa cụ thể.

## 5. Sao chép đồng bộ, bất đồng bộ và quorum khác gì nhau?

| Cơ chế | Tác động phổ biến | Không thể tự suy ra |
|---|---|---|
| **Asynchronous replication** | Primary có thể xác nhận ghi trước khi replica bắt kịp | Mọi replica đều thấy ngay dữ liệu mới; failover không mất ghi đã xác nhận |
| **Synchronous replication** | Primary đợi một điều kiện xác nhận từ một hay nhiều replica trước khi trả commit | Mọi replica đã áp dụng log để đọc thấy; mọi đường đọc đều linearizable |
| **Quorum read/write** | Đòi hỏi đủ số nút tham gia một thao tác | Chỉ cần đủ số nút là mặc nhiên có linearizability trong mọi tình huống |

Với synchronous replication, cần phân biệt replica đã **nhận log**, **flush log xuống lưu trữ**, hay **apply log để đọc thấy**. Chúng là những mốc có tính sẵn sàng và độ trễ khác nhau.

Trong mô hình quorum đơn giản gồm `N` bản sao, người ta hay nhắc điều kiện `R + W > N` để tập đọc và tập ghi có phần giao nhau. Nhưng **điều kiện số học chưa đủ để chứng minh linearizability**: giao thức còn phải xác định cách xử lý phiên bản, ghi đồng thời, chuyển leader, lỗi mạng và các thao tác đọc bị trễ.

### Failover có thể ảnh hưởng cả consistency và durability

Giả sử primary xác nhận một lệnh ghi nhưng replica được chọn lên làm primary mới chưa có lệnh ghi ấy. Nếu kiến trúc cho phép tình huống này, sau failover client có thể không còn thấy cập nhật từng được trả là thành công.

Sự việc có thể đồng thời liên quan đến:

- **Replica consistency:** lịch sử các thao tác đọc/ghi trước và sau failover có thể không đáp ứng bảo đảm quan sát đã công bố.
- **Durability:** nếu hợp đồng bền vững cam kết lệnh ghi đã xác nhận sẽ sống sót sau loại lỗi đó, mất ghi còn là vi phạm bảo đảm durability.

Việc triển khai cụ thể phụ thuộc mức xác nhận commit, tập replica được yêu cầu xác nhận, log bền vững và chính sách bầu/chọn primary mới. Số lượng bản sao lớn tự nó không quyết định độ an toàn.

## 6. Những thuật ngữ thường bị đánh đồng

| Thuật ngữ | Điều nó yêu cầu |
|---|---|
| **ACID Consistency** | Giữ đúng các bất biến dữ liệu qua giao dịch hợp lệ |
| **Isolation** | Kiểm soát sự tương tác giữa các giao dịch chồng lấn |
| **Serializability** | Kết quả các giao dịch đồng thời tương đương một thứ tự thực thi tuần tự |
| **Linearizability** | Các thao tác trên đối tượng tuân thủ thứ tự thời gian thực của các thao tác đã hoàn tất |
| **Strict serializability** | Kết hợp hiệu ứng giao dịch tuần tự với thứ tự thời gian thực |
| **Replica consistency** | Các bảo đảm về thứ tự, độ mới, hội tụ và dữ liệu có thể quan sát qua nhiều bản sao |

**Serializable** và **linearizable** không đồng nghĩa. Serializability yêu cầu kết quả tương đương một thứ tự tuần tự nào đó nhưng không tự đòi hỏi thứ tự ấy tôn trọng thời gian thực giữa các giao dịch hoàn thành trước/sau nhau. Linearizability trực tiếp quan tâm tới thứ tự thời gian thực của các thao tác trên đối tượng; strict serializability ghép hai yêu cầu ở mức giao dịch.

Ngay cả khi replica chỉ cho đọc dữ liệu **đã commit**, nó vẫn có thể trả dữ liệu cũ. Ví dụ, mức isolation `READ COMMITTED` ngăn một số kiểu đọc thay đổi chưa commit theo ngữ nghĩa DBMS, nhưng không có nghĩa “mọi read replica luôn cho dữ liệu mới nhất từ primary”.

### C của ACID khác C của CAP

Trong định lý **CAP**, chữ C thường chỉ *consistency* theo nghĩa có một lịch sử đọc/ghi mạnh như **linearizability/single-copy consistency** trong hệ thống phân tán. Khi mạng phân hoạch, không thể bảo đảm cả tính sẵn sàng theo định nghĩa CAP lẫn mức consistency đó cho mọi yêu cầu.

**C của ACID** nói về **bất biến dữ liệu**; **C của CAP** nói về **ngữ nghĩa quan sát một dữ liệu được chia sẻ qua nhiều nút**. Một hệ thống ưu tiên CAP consistency vẫn có thể sai nghiệp vụ nếu không bảo vệ các bất biến. Một DB hỗ trợ eventual consistency giữa replica vẫn có thể cung cấp transaction ACID đầy đủ bên trong từng nút hoặc phân vùng.

## 7. Áp dụng vào thiết kế API và giao dịch

Giả sử hệ thống bán vé gồm primary xử lý đặt chỗ và replica phục vụ giao diện:

```text
           Người mua
               |
          POST /booking
               |
               v
          PRIMARY DB  --------> commit booking ACTIVE
               |
           replication
               |
               v
          READ REPLICA --------> GET /seats: còn trống (cũ)
```

Trong trường hợp này có **hai trách nhiệm riêng**:

1. **Bảo vệ bất biến tại điểm ghi:** không cho hai booking đang ACTIVE sở hữu cùng ghế.
2. **Bảo đảm kỳ vọng hiển thị:** sau khi đặt thành công, người mua phải thấy ghế đã được giữ, dù replica có thể chậm.

Đối với bất biến trên PostgreSQL, có thể tạo ràng buộc duy nhất cho booking đang hiệu lực:

```sql
CREATE UNIQUE INDEX one_active_booking_per_seat
ON bookings (show_id, seat_id)
WHERE status = 'ACTIVE';
```

Đây là một **unique index có điều kiện**: tại thời điểm ghi trên DB quản lý dữ liệu đó, hai booking ACTIVE cùng ghế sẽ bị từ chối theo quy tắc uniqueness. API đọc “còn trống” từ replica chỉ giúp hiển thị, **không thể thay thế kiểm tra và ràng buộc tại điểm ghi**.

Để người mua thấy chính đặt chỗ của mình, có thể:

- Đọc từ primary trong một khoảng sau khi ghi, hoặc cho các API trạng thái quan trọng.
- Giữ thông tin phiên bản/offset sau commit và chỉ đọc từ replica đã apply đủ mới.
- Dùng dữ liệu xác nhận từ phản hồi ghi để cập nhật giao diện, rồi đối soát với nguồn có bảo đảm đọc phù hợp.
- Theo dõi độ trễ apply log, tránh định tuyến yêu cầu đòi dữ liệu mới đến bản sao quá chậm.

Ví dụ mã giả cho chiến lược đọc với phiên bản tối thiểu:

```text
result = primary.commit(change)
requiredVersion = result.commitVersion

replica = selectReplica(appliedVersion >= requiredVersion)
if replica is available:
    return replica.read(id)
else:
    return readFromAuthoritativeSource(id)
```

Đây chỉ là **thuật toán minh họa**. Cách lấy và so sánh commit version phụ thuộc DBMS; không thể mặc định mọi hệ thống, nhất là hệ thống nhiều shard, cùng sử dụng một bộ đếm phiên bản đơn giản.

### Khi dữ liệu còn nằm ở nhiều cơ sở dữ liệu độc lập

Nếu nghiệp vụ yêu cầu cập nhật Order DB và Payment DB, còn có bài toán **phối hợp giao dịch phân tán**: mỗi DB có thể commit tại thời điểm khác nhau, một dịch vụ có thể lỗi sau commit cục bộ. Tùy yêu cầu, hệ thống cần một giao thức atomic commit thực sự được hỗ trợ hoặc một quy trình nghiệp vụ như Saga kèm idempotency, retry và bù trừ.

Việc bật synchronous replication **bên trong từng DB** không tự bảo đảm “Order DB và Payment DB cùng commit hoặc cùng rollback”. Ngược lại, dù có một cơ chế phối hợp giao dịch đúng, bản sao đọc của từng DB vẫn có thể có các bảo đảm quan sát riêng.

## 8. Multi-leader và cập nhật xung đột

Ở hệ thống cho nhiều nút cùng nhận ghi, hai replica có thể nhận hai thay đổi khác nhau khi mất kết nối:

```text
Ban đầu: profile.name = "An"

Replica A: profile.name = "Bình"   (thiết bị 1)
Replica B: profile.name = "Chi"    (thiết bị 2)

Kết nối phục hồi: phải hợp nhất hoặc giải quyết xung đột.
```

Một quy tắc *last-write-wins* có thể giúp các replica hội tụ nhưng làm mất một cập nhật. Cơ chế merge hoặc kiểu dữ liệu hội tụ phù hợp (ví dụ CRDT cho một số loại trạng thái) có thể giải quyết những lớp xung đột nhất định. Dù vậy, **hội tụ về cùng một giá trị không chứng minh được các bất biến như “không bán quá số hàng trong kho” đã được giữ**.

Các quy tắc nghiệp vụ liên quan tới nhiều nơi ghi cần được bảo vệ bằng thiết kế phù hợp; không nên giả định “dữ liệu cuối cùng giống nhau” thì giao dịch đã đúng.

## 9. Cách chọn bảo đảm theo yêu cầu thực tế

| Tình huống | Điều cần giữ đúng | Bảo đảm đọc/replication cần xem xét |
|---|---|---|
| Chuyển tiền | Ghi nợ và ghi có đúng, không vượt hạn mức | Xác nhận kết quả từ nguồn có thẩm quyền; không suy luận thất bại chỉ vì replica còn số dư cũ |
| Bán ghế cuối cùng | Không có hai booking ACTIVE cùng ghế | Unique/atomic check tại nơi ghi; giao diện có thể cần read-your-writes |
| Sửa hồ sơ cá nhân | Dữ liệu theo schema và quy tắc tài khoản | Read-your-writes để vừa lưu xong thấy thay đổi |
| Thống kê lượt xem | Quy tắc ghi nhận số liệu được thực hiện đúng | Có thể chấp nhận eventual consistency hoặc bounded staleness |
| Khôi phục sau failover | Những ghi đã xác nhận đáp ứng cam kết durability | Chính sách đồng bộ, commit acknowledgement, lựa chọn leader và đọc sau failover |
| Nghiệp vụ qua nhiều DB | Bất biến nhiều tài nguyên hoặc trạng thái bù hợp lệ | Cơ chế giao dịch phân tán; mỗi DB vẫn cần thiết kế đọc từ replica phù hợp |

Khi phân tích một tính năng, hãy lần lượt trả lời:

1. **Bất biến phải đúng là gì?** Chẳng hạn, không bán trùng một ghế.
2. **Ai bảo vệ bất biến ở thời điểm commit?** Constraint, transaction, khóa, mức cô lập hay giao thức qua nhiều tài nguyên?
3. **Ghi được xác nhận vào lúc nào?** Primary commit, replica đã nhận log, đã flush hay đã apply?
4. **Người đọc cần dữ liệu mới đến mức nào?** Chấp nhận eventual consistency, cần read-your-writes hay linearizability?
5. **Khi replica trễ hoặc mạng phân hoạch thì ứng xử ra sao?** Chờ có giới hạn, đổi nguồn đọc, trả lỗi hay chấp nhận dữ liệu cũ theo hợp đồng API?

Các chỉ số hữu ích gồm độ trễ replication, độ trễ apply log, tuổi của phiên bản mới nhất trên từng replica, khoảng cách tới commit index hoặc log position nếu DBMS hỗ trợ, cũng như hành vi đọc/ghi trong quá trình đổi leader.

## 10. Ba phản ví dụ để tự phân biệt

**Trường hợp A — ACID đúng, replica cũ.** Primary commit chuyển 100.000 đồng từ A sang B trong một transaction hợp lệ. Follower chưa nhận thay đổi, nên hiển thị số dư cũ. Đây là vấn đề **replica lag/stale read**, không tự chứng minh bất biến chuyển tiền bị phá vỡ.

**Trường hợp B — replica đồng bộ, nghiệp vụ sai.** Ứng dụng ghi tồn kho âm do thiếu constraint và kiểm tra nghiệp vụ. Mọi replica sao chép chính xác số âm đó. Đây là lỗi **ACID Consistency theo quy tắc nghiệp vụ được mong đợi**, dù dữ liệu giữa các replica giống nhau.

**Trường hợp C — hai loại lỗi cùng tồn tại.** Hai giao dịch đồng thời cùng đặt một ghế vì thiếu ràng buộc ghi có thẩm quyền; bản sao đọc lại vẫn hiển thị ghế trống. Hệ thống vừa có **lỗi bảo vệ bất biến trong concurrency**, vừa có **vấn đề độ mới trên replica**. Sửa replication lag không tự tạo ràng buộc uniqueness; thêm uniqueness cũng không làm follower lập tức bắt kịp.

Khi dùng từ **“nhất quán”**, cần nói rõ đang đánh giá **tính hợp lệ của trạng thái sau giao dịch** hay **bảo đảm quan sát giữa các bản sao**. Từ đó mới chọn đúng cơ chế: constraint, transaction và isolation để giữ bất biến; replication protocol, read consistency level và định tuyến đọc để kiểm soát thứ tự và độ mới của dữ liệu.
