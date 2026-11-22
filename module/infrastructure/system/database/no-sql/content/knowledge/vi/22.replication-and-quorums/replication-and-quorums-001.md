# Mục tiêu tạo bản sao và mô hình các miền lỗi trong NoSQL

Một cơ sở dữ liệu NoSQL lưu ba bản sao của cùng dữ liệu có thể chịu được lỗi một máy chủ — **nhưng chưa chắc chịu được lỗi một rack, một availability zone hoặc cả vùng triển khai**. Nếu cả ba bản sao đều nằm trên ba máy trong cùng một trung tâm dữ liệu có chung nguồn điện, một sự cố điện có thể làm cả ba mất kết nối đồng thời.

Ngược lại, đặt các bản sao ở những khu vực địa lý xa nhau có thể giảm rủi ro một sự cố vật lý chung, nhưng lại làm tăng độ trễ truyền dữ liệu, chi phí mạng và độ khó đạt quorum khi đường truyền giữa vùng bị gián đoạn.

Đó là lý do thiết kế **replication (sao chép dữ liệu)** không dừng ở câu hỏi “cần bao nhiêu replica?”. Cần trả lời thêm:

1. **Tạo bản sao để làm gì?** Tăng tính sẵn sàng, tránh mất dữ liệu, phục vụ đọc gần người dùng, bảo trì không gián đoạn hay hỗ trợ khôi phục thảm họa?
2. **Muốn chịu được lỗi gì?** Process, máy chủ, đĩa, rack, availability zone (AZ), region, mạng, thao tác nhầm hoặc lỗi phần mềm?
3. **Các replica có độc lập thật không?** Chúng có dùng chung nguồn điện, bộ điều khiển lưu trữ, switch mạng, khóa mã hóa, control plane hoặc một cơ chế xóa dữ liệu đồng loạt không?
4. **Khi một miền lỗi mất đi, quorum còn hoạt động không?** Hệ có tiếp tục phục vụ read/write theo mức nhất quán yêu cầu hay phải từ chối?
5. **Khi hồi phục, hệ lấy lại dữ liệu và tính đúng như thế nào?** Có log, snapshot, anti-entropy, repair, backup và quy trình failover đủ rõ không?

Bài học thuộc chương **Sao chép và quorum** của **Database No SQL**, tập trung vào mục tiêu tạo bản sao, mô hình các miền lỗi (*failure domains*) và cách biến các yêu cầu RPO, RTO, availability, latency thành một topology có thể kiểm chứng. Các ví dụ dùng MongoDB, Cassandra, Redis và một số nguyên tắc áp dụng cho dịch vụ NoSQL được quản lý như DynamoDB.

---

## 1. Sao chép dữ liệu là gì?

**Replication** là việc duy trì nhiều bản thể của dữ liệu hoặc những thông tin đủ để phục hồi/truy cập dữ liệu trên các node/vị trí khác nhau theo một giao thức.

Một sơ đồ khái niệm:

```text
                 Ứng dụng
                    |
                    v
             +--------------+
             | Node A       |
             | Primary      |
             +--------------+
                 |      |
         replicate      replicate
                 |      |
                 v      v
         +----------+ +----------+
         | Node B   | | Node C   |
         | Replica  | | Replica  |
         +----------+ +----------+
```

Mỗi bản sao có thể có:

- Dữ liệu hoặc log sao chép cần thiết để tái tạo dữ liệu.
- Chỉ mục và metadata phục vụ đường đọc.
- Trạng thái tiến độ sao chép, ví dụ log index, timestamp, version hoặc sequence.
- Vai trò trong giao thức: leader, follower, voter, read replica, witness/arbiter hoặc thành viên chỉ lưu dữ liệu.
- Chính sách lưu bền và mức xác nhận ghi riêng theo engine.

**Không phải mọi “thành viên” trong cụm đều chứa một bản sao dữ liệu đầy đủ.** Ví dụ, một arbiter hoặc witness có thể tham gia quyết định vai trò/quorum mà không giữ dữ liệu ứng dụng; node như vậy không được tính là một bản sao dữ liệu dùng để phục hồi.

### 1.1. Sao chép đồng bộ và bất đồng bộ

| Đặc điểm | Đồng bộ theo điều kiện ACK | Bất đồng bộ |
| --- | --- | --- |
| Phản hồi ghi | Chờ những node/điều kiện xác nhận đã chọn | Có thể ACK trước khi replica khác nhận dữ liệu |
| Latency | Có thể tăng theo mạng và replica chậm | Thường giảm độ trễ đường ghi |
| Rủi ro khi mất node nguồn | Phụ thuộc cam kết durability và những nơi đã ACK | Có thể mất các ghi mới chưa truyền đi |
| Khả dụng khi đường mạng lỗi | Có thể giảm nếu thiếu số ACK cần thiết | Có thể tiếp tục nhận ghi nhưng phải giải quyết lệch dữ liệu |
| Trường hợp dùng | Ghi quan trọng cần chịu lỗi nhất định | Cache, read replica, dữ liệu dẫn xuất, eventual propagation |

Bảng trên là **xu hướng tổng quát**, không phải định nghĩa đầy đủ của từng database. Có hệ có mức xác nhận cấu hình theo từng request; có hệ dùng đồng thuận và chỉ công bố ghi khi commit log đạt quorum; có hệ sao chép bất đồng bộ nhưng cung cấp một số session guarantees.

**Không được coi “replica đã nhận ghi” là đồng nghĩa “replica đã lưu bền xuống đĩa”** nếu không biết chính sách WAL/journal/fsync của sản phẩm.

---

## 2. Những mục tiêu khác nhau của replication

Replicate cùng một dataset có thể phục vụ nhiều mục tiêu; mỗi mục tiêu kéo theo topology và giao thức khác nhau.

### 2.1. Tăng availability

Nếu một node ngừng hoạt động, node khác có thể phục vụ yêu cầu hoặc được bầu thành leader mới.

Ví dụ:

```text
A (primary)   -- lỗi phần cứng
B (replica)   -- còn sống, đủ điều kiện trở thành primary
C (replica)   -- còn sống
```

Nếu giao thức bầu chọn và quorum còn đủ, cụm có thể tiếp tục hoạt động sau failover. Tuy nhiên:

- Failover cần thời gian để phát hiện lỗi, bầu chọn và thiết lập đường ghi.
- Một số request đang chạy có thể timeout.
- Read và write có thể có điều kiện khả dụng khác nhau.
- Đang có hai node “up” không tự bảo đảm cluster phục vụ được write, nếu quorum/voter cấu hình không phù hợp.

**Availability không chỉ là số node còn chạy**; nó còn là khả năng hoàn tất **operation theo đúng consistency/acknowledgment đã cam kết**.

### 2.2. Giảm rủi ro mất dữ liệu do hỏng node hoặc đĩa

Nếu một ổ đĩa bị hỏng hoàn toàn và replica khác giữ bản dữ liệu bền hợp lệ, hệ có cơ hội phục hồi mà không mất toàn bộ dataset.

Nhưng bảo vệ mất đĩa đơn lẻ khác với bảo vệ:

- Mất cả rack chứa nhiều ổ đĩa.
- Lỗi cả AZ.
- Lỗi logic khiến mọi replica cùng xóa dữ liệu.
- Mã độc/ransomware có quyền sửa mọi bản sao.
- Thao tác vận hành nhầm ở cluster.
- Lỗi corruption được nhân bản hoặc không phát hiện.

**Replication không thay backup và lưu trữ phiên bản độc lập.**

### 2.3. Phân phối tải đọc

Read replica có thể phục vụ nhiều request truy vấn:

```text
                 Write path
                     |
                 Primary A
                  /      \
                 v        v
            Read B       Read C
```

Tùy mô hình, ứng dụng có thể route read đến B/C để giảm tải A.

Đánh đổi: B/C có thể **trễ hơn trạng thái commit trên A**, hoặc yêu cầu những mức read concern nhất định trước khi trả lời. Vì vậy mở rộng đọc và bảo đảm read-your-writes là hai yêu cầu phải xử lý cùng lúc.

### 2.4. Đưa dữ liệu gần người dùng

Một ứng dụng có người dùng tại châu Á và châu Âu có thể đặt các read replica gần từng nhóm để giảm độ trễ mạng.

Nhưng nếu cần ghi được xác nhận trên nhiều vùng, hệ sẽ chịu độ trễ đường truyền giữa region. Nếu mỗi region tự nhận write, còn phải giải quyết conflict và bất biến nghiệp vụ nhiều vùng.

**Read locality không tự đồng nghĩa local write quorum**.

### 2.5. Bảo trì và nâng cấp giảm gián đoạn

Khi có nhiều replica độc lập và còn đủ quorum, có thể:

1. Đưa một node ra khỏi phục vụ.
2. Bảo trì hoặc nâng cấp.
3. Chờ node bắt kịp dữ liệu.
4. Khôi phục vai trò.
5. Chuyển sang node tiếp theo.

Đó là *rolling maintenance*. Nhưng nếu đang chỉ còn đúng số node tối thiểu để đạt quorum, mất thêm một node trong bảo trì có thể làm cụm ngừng ghi.

**Fault tolerance dưới điều kiện đầy đủ khác fault tolerance khi đang bảo trì.**

### 2.6. Hỗ trợ khôi phục thảm họa

Replica ở region khác có thể giảm phụ thuộc vào một vị trí địa lý. Tuy nhiên:

- Nó có thể chỉ là replica bất đồng bộ với RPO khác 0.
- Nó có thể chưa sẵn sàng nhận vai trò primary.
- Dữ liệu và khóa mã hóa có thể cùng phụ thuộc một control plane.
- Chuyển hướng DNS/client và xác thực có thể kéo dài RTO.
- Ghi vào hai region trong lúc partition có thể cần reconcile.

Vì thế **disaster recovery** phải được thiết kế và thử riêng, không chỉ “tạo một node ở region B”.

---

## 3. Failure domain là gì?

**Miền lỗi (failure domain)** là tập thành phần có khả năng cùng bị tác động bởi một sự cố chung.

Một miền lỗi có thể được xác định bởi phần cứng, mạng, nguồn điện, môi trường vật lý, phần mềm hoặc quản trị.

Các cấp độ thường gặp:

```text
Cloud provider / tổ chức vận hành
└── Region
    ├── Availability Zone A
    │   ├── Rack 1
    │   │   ├── Host A1
    │   │   │   ├── Process DB A
    │   │   │   └── Volume A
    │   │   └── Host A2
    │   └── Rack 2
    ├── Availability Zone B
    │   └── ...
    └── Availability Zone C
        └── ...
```

**Các nhánh trong sơ đồ không tự bảo đảm độc lập tuyệt đối.** Thực tế phải xem topology và hợp đồng hạ tầng. Hai AZ có thể được thiết kế tách biệt nhiều thành phần, nhưng cả region vẫn có thể chịu lỗi chung; hai region có thể cùng phụ thuộc dịch vụ DNS, IAM hoặc hệ quản trị ứng dụng.

### 3.1. Bảng mô hình miền lỗi

| Miền lỗi | Sự cố minh họa | Cách giảm phụ thuộc |
| --- | --- | --- |
| **Process** | Database process crash hoặc leak memory | Nhiều process trên những host độc lập, health check |
| **Container/VM** | VM bị dừng, hypervisor lỗi | Anti-affinity giữa host vật lý |
| **Ổ đĩa/volume** | SSD lỗi, filesystem hỏng | Replica trên volume/thiết bị khác, checksum/backup |
| **Host vật lý** | Mainboard, CPU, NIC hoặc nguồn host hỏng | Không đặt mọi replica trên cùng host |
| **Rack** | Switch top-of-rack hoặc nguồn rack hỏng | Phân tán replica qua rack độc lập |
| **AZ/datacenter** | Mất nguồn diện rộng trong AZ | Đặt replica qua nhiều AZ |
| **Region** | Khu vực hạ tầng không truy cập được | Multi-region/DR theo yêu cầu |
| **Đường truyền WAN** | Mất kết nối giữa region | Quorum/failover policy và trạng thái tạm phù hợp |
| **Control plane** | API quản trị cloud không hoạt động | Không phụ thuộc vào thao tác control plane để phục vụ request cần thiết |
| **Phần mềm/config** | Bug hoặc cấu hình sai áp cho mọi node | Canary, rollout theo đợt, version compatibility |
| **Bảo mật/quyền** | Key/KMS/IAM không truy cập được | Thiết kế phụ thuộc an toàn, phục hồi và kiểm soát quyền |
| **Con người** | Xóa nhầm dữ liệu, schema migration lỗi | Backup độc lập, versioning, kiểm tra quyền/phê duyệt |

Một replica ở host khác nhưng cùng rack chống tốt hơn lỗi một host; nó **không tự chống** lỗi switch hoặc nguồn rack.

### 3.2. Shared fate — nhiều replica cùng một số phận

*Shared fate* là tình huống nhiều thành phần cùng thất bại do một nguyên nhân chung.

Ví dụ:

```text
Replica A -> Host 1 -> Rack X
Replica B -> Host 2 -> Rack X
Replica C -> Host 3 -> Rack X

Rack X mất nguồn
         |
         v
    A, B, C đều mất
```

Ba replica không tương đương ba miền lỗi độc lập nếu chúng cùng nằm trong rack X.

Một lỗi ít hiển nhiên hơn:

```text
Replica A -> AZ 1
Replica B -> AZ 2
Replica C -> AZ 3

Tất cả:
  - dùng cùng một KMS key không thể giải mã khi dịch vụ phụ thuộc lỗi,
  - cùng nhận một bản cấu hình làm database không khởi động,
  - cùng chịu một thao tác DROP COLLECTION được replicate.
```

Phân bố vị trí giúp chống **lỗi hạ tầng vật lý**, không tự chống **common-mode software/operational failures**.

---

## 4. Replication factor (RF) không tự nói được khả năng chịu lỗi

**Replication factor (RF)** thường là số bản sao dữ liệu được duy trì theo phạm vi mà hệ thống định nghĩa.

Ví dụ RF=3:

```text
Dataset X
  -> Replica A
  -> Replica B
  -> Replica C
```

Nhưng có ba phương án đặt:

| Phương án | Vị trí 3 replica | Chịu lỗi một host? | Chịu lỗi mất một AZ? |
| --- | --- | --- | --- |
| **P1** | 3 process trên 1 host | Không | Không |
| **P2** | 3 host trong 1 AZ | Có thể, nếu các host độc lập | Không |
| **P3** | 3 AZ, mỗi AZ 1 replica | Có thể | Có thể, **nếu quorum và topology phù hợp** |

Từ “có thể” quan trọng: khi mất AZ, kết quả còn tùy **cách hệ bầu leader, mức ACK, số voter, sự độc lập của hạ tầng và trạng thái thực tế của node còn lại**.

### 4.1. Replication factor theo dataset hay theo cluster?

Trong hệ sharded/partitioned, RF thường áp dụng cho **một shard/partition/range**, không có nghĩa mọi node đều giữ toàn bộ database.

Ví dụ:

```text
Shard 1 -> A, B, C
Shard 2 -> B, C, D
Shard 3 -> C, D, E
```

Một node có thể giữ replica của nhiều shard. Khi node mất, **nhiều shard cùng bị ảnh hưởng**, nhưng số lượng replica còn lại khác nhau theo từng shard.

Phải kiểm tra **placement của mỗi shard** chứ không chỉ tổng số node của cluster.

### 4.2. RF tăng không đồng nghĩa tăng availability tuyến tính

RF=5 có thể giúp bảo vệ nhiều lỗi hơn RF=3 nếu các bản sao được đặt độc lập và quorum phù hợp. Nhưng nó cũng kéo theo:

- Thêm dung lượng lưu trữ.
- Thêm lưu lượng replication.
- Tăng thời gian và băng thông cho bootstrap/repair.
- Có thể tăng latency nếu mức ACK yêu cầu thêm replica.
- Nhiều thành viên cần quản lý, nâng cấp và thay thế.

Nếu cả năm replica cùng một miền lỗi chung, tăng RF từ 3 lên 5 **không bảo vệ** trước mất miền đó.

---

## 5. Mô hình lỗi độc lập và lỗi tương quan

Để thấy tác động của placement, có thể dùng một mô hình xác suất rất đơn giản.

Giả sử mỗi host có xác suất hỏng trong khoảng quan sát là \(p\). Nếu **thật sự độc lập**, xác suất cả ba host cùng hỏng là:

\[
P(\text{cả ba lỗi}) = p^3
\]

Ví dụ \(p=0.01\):

\[
p^3 = 0.000001
\]

Nhưng nếu cả ba host cùng một rack và rack có thể mất nguồn, xác suất toàn bộ replica mất **không chỉ** là \(p^3\). Cần tính thêm rủi ro chung của rack và các phụ thuộc khác.

### 5.1. Một biểu diễn cây lỗi

```text
Không còn replica khả dụng
        |
        +-- Lỗi chung của rack / AZ / region
        |
        +-- Tất cả host lỗi độc lập
        |
        +-- Lỗi config hoặc quyền làm mọi replica unusable
        |
        +-- Lỗi mạng khiến client không thể truy cập quorum
```

Đây là **fault tree định tính**. Không nên gán xác suất cụ thể cho từng nhánh khi chưa có dữ liệu đo và giả định độc lập.

### 5.2. Xác suất cùng hỏng khác xác suất không đạt quorum

Với ba replica, nếu phải có **majority 2/3** để ghi, cụm mất khả năng ghi trước khi cả ba replica đều hỏng: chỉ cần **hai thành viên không thể tham gia quorum** đã đủ gây gián đoạn ghi.

Do đó phải phân biệt:

- **Mất tất cả bản sao dữ liệu:** rủi ro mất toàn bộ dữ liệu nếu không còn nơi phục hồi.
- **Không đủ quorum:** có thể tạm thời ngừng ghi dù vẫn còn một bản sao nguyên vẹn.
- **Mất leader:** có thể cần failover dù đa số node còn sống.
- **Mất đường client–cluster:** node có thể vẫn chạy nhưng client không truy cập được.

Availability và durability có **các ngưỡng lỗi khác nhau**.

---

## 6. Quorum cơ bản và ý nghĩa với failure domain

Trong nhiều hệ có cơ chế majority voting, với \(N\) thành viên bỏ phiếu, số phiếu đa số là:

\[
Q = \left\lfloor \frac{N}{2} \right\rfloor + 1
\]

| Số voter \(N\) | Majority \(Q\) | Số voter không tham gia tối đa trước khi mất majority |
| ---: | ---: | ---: |
| 1 | 1 | 0 |
| 2 | 2 | 0 |
| 3 | 2 | 1 |
| 4 | 3 | 1 |
| 5 | 3 | 2 |
| 7 | 4 | 3 |

Bảng này là toán học của **majority tập voter**. Nó **không tự mô tả** quorum read/write của mọi NoSQL; ví dụ Cassandra có consistency level và chiến lược replica khác bầu leader của MongoDB/Raft.

### 6.1. Ba voter trải ba AZ

```text
AZ A: Voter 1
AZ B: Voter 2
AZ C: Voter 3

Majority = 2/3
```

Khi AZ A mất:

```text
AZ A: X
AZ B: Voter 2
AZ C: Voter 3

Còn 2/3 -> có thể giữ majority
```

Một cấu hình như vậy có thể chịu mất **một AZ** đối với các thao tác đòi majority, nếu mạng giữa hai AZ còn lại hoạt động và các điều kiện khác của giao thức được đáp ứng.

### 6.2. Ba voter đặt lệch 2–1 trên hai AZ

```text
AZ A: Voter 1, Voter 2
AZ B: Voter 3

Majority = 2/3
```

- Mất AZ B: còn hai voter ở A, có thể đạt majority.
- Mất AZ A: chỉ còn một voter ở B, **không đạt majority**.

Kết quả bất đối xứng. Hệ chịu lỗi một AZ cụ thể nhưng **không chịu được mất bất kỳ AZ nào**.

### 6.3. Hai voter trên hai AZ có thật sự tốt?

```text
AZ A: Voter 1
AZ B: Voter 2
Majority = 2/2
```

Mất một AZ để lại 1/2, không đạt majority. Vì vậy topology 2 voter thường không cung cấp tính sẵn sàng ghi trước lỗi một voter trong cơ chế majority.

Một **witness/arbiter ở miền thứ ba** có thể hỗ trợ bầu chọn trong một số hệ, nhưng cần nhớ:

- Witness có thể **không chứa dữ liệu**.
- Nó không làm tăng số bản sao có thể phục hồi dataset.
- Giao thức và điều kiện durability/commit vẫn phải được xem riêng.
- Nếu dữ liệu nằm trên một node duy nhất còn sống, việc có phiếu bầu không nhất thiết giúp phục hồi ghi mới chưa bền.

**Không đếm witness như một data replica.**

---

## 7. Quorum đọc/ghi \(R + W > N\) và giới hạn của công thức

Trong mô hình quorums đơn giản:

- \(N\): số replica trong một tập cố định.
- \(R\): số replica cần tham gia đọc.
- \(W\): số replica cần tham gia ghi.

Nếu:

\[
R + W > N
\]

thì mọi read quorum và write quorum thuộc cùng tập \(N\) **phải có ít nhất một replica giao nhau**.

Ví dụ:

\[
N=3,\ R=2,\ W=2\ \Rightarrow\ R+W=4>3
\]

Nhưng **quorum intersection không tự bảo đảm linearizability**.

### 7.1. Cần thêm những giả định nào?

Để kết luận đọc được phiên bản đúng, còn cần biết:

1. Cách hệ chọn version mới nhất từ các phản hồi.
2. Cách xử lý nhiều write đồng thời và conflict.
3. Membership có thay đổi khi sự cố hay không.
4. Có **sloppy quorum**, hinted handoff hoặc tạm ghi ở replica ngoài tập gốc không.
5. Ghi được coi là committed khi nào.
6. Replica ACK trong RAM hay sau durability sync.
7. Khi failover, log/leader term bảo vệ thứ tự ra sao.
8. Một operation có phạm vi một key hay nhiều document.

**Đừng dùng một bất đẳng thức như bằng chứng hệ “strongly consistent trong mọi tình huống”.**

### 7.2. Majority cho election và quorum cho dữ liệu là hai câu hỏi

Trong một số engine, majority vote dùng để **bầu leader**. Một mức write concern có thể yêu cầu những **data-bearing members** hoặc điều kiện commit nhất định.

Một thành viên có phiếu bầu nhưng không chứa dữ liệu có thể giúp quyết định ai là leader, nhưng không tự tạo một bản ghi dữ liệu bền trên thêm một host.

Vì vậy phải phân biệt:

- **Election quorum:** ai được quyền làm leader.
- **Commit/write quorum:** khi nào ghi được công bố hoàn tất.
- **Read quorum:** dữ liệu đọc được xác định thế nào.
- **Data replica count:** nơi nào thật sự giữ dữ liệu phục hồi.

Tùy engine, các tập này có thể trùng nhau hoặc khác nhau.

---

## 8. Một ma trận lỗi cho topology ba AZ

Giả sử có ba **data-bearing replicas/voters**, mỗi replica đặt tại một AZ độc lập trong cùng region. Mô hình sử dụng majority 2/3.

| Sự cố | Data replica còn truy cập được | Majority? | Điều kỳ vọng |
| --- | ---: | --- | --- |
| Không có lỗi | 3 | Có | Đọc/ghi bình thường theo cấu hình |
| Mất process ở A | 2 | Có | Có thể failover/tiếp tục, sau đó phục hồi A |
| Mất cả AZ A | 2 | Có | Có thể tiếp tục majority operation nếu B–C kết nối |
| Mất đồng thời AZ A và B | 1 | Không | Ghi yêu cầu majority không thể hoàn tất |
| Mất network A ↔ B,C | 2 ở một phía, 1 phía còn lại | Chỉ phía 2/3 | Phía minority không được tự nhận là majority leader |
| Client không liên hệ được cluster | 3 node có thể vẫn chạy | Quorum nội bộ có thể còn | Client vẫn không hoàn tất request |
| Region mất hoàn toàn | 0 | Không | Cần DR ở region khác, không được giả định có sẵn |

Bảng chỉ đúng với **giả định sơ đồ**. Một phiên bản thực có thể có leader bị mất, re-election timeout, lease, fencing, read preference hoặc cấu hình voting khác làm hành vi quan sát chi tiết khác đi.

### 8.1. Vì sao mất một AZ không có nghĩa “không gián đoạn”?

Khi AZ chứa leader mất:

1. Client có thể gặp timeout hoặc lỗi kết nối.
2. Các node còn lại cần phát hiện sự cố.
3. Giao thức có thể bầu leader mới.
4. Driver/app cần cập nhật route.
5. Read/write tiếp tục sau một khoảng chuyển tiếp.

Do đó **khả năng tiếp tục hoạt động sau lỗi** không đồng nghĩa **zero downtime**. RTO và p99 latency trong failover vẫn cần đo.

### 8.2. Hai AZ còn sống nhưng bị cô lập với nhau

Nếu AZ B và C đều còn máy chạy nhưng network giữa chúng đứt, **không có một nhóm 2 voter kết nối được**, trừ khi có đường liên lạc thay thế. Cụm có thể mất majority dù không có thêm lỗi phần cứng.

**Số node “healthy” trong dashboard không đủ**; phải xét khả năng truyền thông giữa những thành viên cần thiết.

---

## 9. Mô hình leader–follower, multi-leader và leaderless

### 9.1. Leader–follower

Một node được phép chấp nhận write làm nguồn thứ tự, các follower sao chép theo.

```text
Client WRITE
    |
    v
Leader A ---- replicate ----> Follower B
    |
    +------- replicate ----> Follower C
```

Ưu điểm:

- Một nguồn điều phối thứ tự ghi rõ ràng.
- Dễ xác định primary write path.
- Phù hợp một số mô hình giao dịch và log replication.

Rủi ro/đánh đổi:

- Leader là điểm tập trung write.
- Cần election/fencing để tránh **hai leader cùng được tin**.
- Follower có thể stale nếu cho đọc bất đồng bộ.
- Failover cần xử lý write chưa commit và client retry.

### 9.2. Multi-leader

Nhiều region/node có thể chấp nhận write rồi đồng bộ.

```text
Region A leader <---- async sync ----> Region B leader
      ^                                 ^
      |                                 |
   Clients A                         Clients B
```

Ưu điểm: write gần người dùng và khả năng tiếp tục nhận thao tác cục bộ trong một số partition.

Đánh đổi:

- Hai leader có thể sửa cùng key hoặc tạo ràng buộc mâu thuẫn.
- Cần conflict resolution, version, merge hoặc coordinator.
- Hội tụ của replica không tự bảo vệ ghế duy nhất, quota hay thanh toán.

**Một chức năng cấp phát tài nguyên khan hiếm không nên trở thành multi-leader vô điều kiện chỉ vì muốn latency thấp.**

### 9.3. Leaderless/quorum-oriented

Client/coordinator gửi read/write đến nhiều replica theo consistency level. Hệ có thể dùng version, timestamp, repair và cơ chế hòa giải.

Không có leader cố định **không có nghĩa không cần giao thức đồng thuận cho các invariant nhất định**. Với Cassandra, các operation LWT có cơ chế riêng với regular reads/writes.

### 9.4. Chọn mô hình từ yêu cầu

| Bài toán | Một hướng có thể phù hợp |
| --- | --- |
| Ghi có thứ tự chặt và ít conflict | Leader–follower/consensus commit |
| Read nhiều vùng, write tại một vùng | Leader nguồn + read replicas ở các vùng |
| Ghi nhiều vùng chấp nhận hòa giải | Multi-leader/active-active có conflict policy |
| Event/counter có merge an toàn | Eventual/CRDT phù hợp |
| Ghế duy nhất đa vùng | Atomic authority, escrow/reservation hoặc giao thức tương đương |
| Transaction nhiều document | Engine có phạm vi atomicity/isolation được công bố |

---

## 10. Phân bố replica theo miền lỗi (replica placement)

Một nguyên tắc là **không đặt nhiều replica của cùng một shard trên cùng một miền lỗi nếu mục tiêu là chịu lỗi miền đó**.

### 10.1. Anti-affinity

*Anti-affinity* là quy tắc tránh xếp những replica cần độc lập lên cùng host/rack/AZ.

Ví dụ:

```text
Sai cho mục tiêu chịu lỗi một host:
  Shard S replica A -> Host X
  Shard S replica B -> Host X
  Shard S replica C -> Host Y

Tốt hơn:
  Shard S replica A -> Host X
  Shard S replica B -> Host Y
  Shard S replica C -> Host Z
```

Nếu mục tiêu là chịu lỗi **một AZ**, phải tiếp tục đặt Host X/Y/Z ở những AZ phù hợp; chỉ khác host chưa đủ.

### 10.2. Một bảng placement theo mục tiêu

| Mục tiêu chịu lỗi | Placement tối thiểu cần cân nhắc | Ràng buộc bổ sung |
| --- | --- | --- |
| Mất một process | Nhiều process độc lập | Không phụ thuộc cùng process manager lỗi |
| Mất một host | Replica trên host vật lý khác nhau | Tránh cùng ổ/VM host |
| Mất một rack | Trải qua các rack độc lập | Network/power rack thực sự tách biệt |
| Mất một AZ | Trải nhiều AZ, quorum vẫn còn sau mất AZ | Giao thức/leader/clients còn kết nối |
| Mất một region | Đặt dữ liệu/quorum/DR tại nhiều region | WAN latency, failover, data residency |
| Lỗi logic/xóa nhầm | Replica không đủ | Backup/PITR/retention tách quyền |
| Mã độc/credential compromise | Replica không đủ | Immutable backup, phân quyền/tách trust domain |

**Placement là phần của mô hình lỗi**, không phải “chi tiết hạ tầng” có thể giao tùy tiện rồi mới tối ưu sau.

### 10.3. Shard-aware placement

Nếu một cluster có 50 shard, cần tránh việc một AZ chứa **majority của các voter cho quá nhiều shard** theo cách khiến mất AZ đó làm nhiều shard không thể ghi.

Cần kiểm tra:

- Replica của **mỗi shard** phân bố ở đâu.
- Quorum mỗi shard còn không sau mất một AZ.
- Leader có tập trung quá nhiều vào một AZ không.
- Node nào giữ nhiều shard “hot” gây rủi ro tải.
- Quá trình rebalance có tạm làm placement xấu đi không.

---

## 11. Một hay nhiều region?

Một region thường có nhiều AZ; triển khai qua AZ và triển khai qua region có **mục tiêu khác nhau**.

### 11.1. Ba replica trên ba AZ của một region

```text
Region R1
  AZ A: Replica 1
  AZ B: Replica 2
  AZ C: Replica 3
```

Có thể đáp ứng yêu cầu chịu lỗi một AZ với majority 2/3, nhưng **mất toàn bộ region R1** vẫn có thể làm cluster không phục vụ.

Ưu điểm thường gặp: latency giữa AZ thấp hơn nhiều so với WAN liên vùng (phải đo theo nhà cung cấp và vị trí).

### 11.2. Ba replica trải hai region theo tỷ lệ 2–1

```text
Region R1:
  AZ A: Replica 1
  AZ B: Replica 2

Region R2:
  AZ C: Replica 3
```

Với majority 2/3:

- Mất R2: còn hai replica ở R1, có thể đạt majority.
- Mất R1: chỉ còn một replica ở R2, không đạt majority.

**Có replica trong hai region không có nghĩa hệ có thể chịu mất bất kỳ region nào mà vẫn ghi được.**

### 11.3. Ba replica ở ba region

```text
Region R1: Replica 1
Region R2: Replica 2
Region R3: Replica 3
```

Nếu các kết nối và giao thức phù hợp, majority 2/3 có thể còn sau mất một region.

Nhưng một write majority có thể cần **đợi mạng liên vùng**, ảnh hưởng p95/p99 latency và khả năng tiếp nhận write khi WAN chậm. Các ứng dụng latency thấp phải cân nhắc **địa lý của quorum**, không chỉ số replica.

### 11.4. Mô hình vùng chính và vùng DR

Một phương án khác:

```text
Region chính:
  Replica A, B, C -> phục vụ bình thường

Region DR:
  Async standby / backup / restore target
```

Phương án này có thể tách **availability AZ** khỏi **disaster recovery**. Nó không nhất thiết có RPO=0 khi region chính mất, bởi vùng DR có thể chưa nhận hết write.

Đây có thể là lựa chọn hợp lý nếu sản phẩm chấp nhận **RPO và RTO xác định**, thay vì trả latency đa vùng cho mọi commit.

---

## 12. RPO, RTO, availability và latency phải được diễn đạt thành mục tiêu cụ thể

### 12.1. RPO (Recovery Point Objective)

**RPO** là giới hạn mục tiêu về lượng dữ liệu có thể mất khi xảy ra loại sự cố được xác định.

Ví dụ:

> “Khi mất hoàn toàn region chính, chấp nhận mất tối đa những thay đổi chưa được sao chép trong 5 phút.”

Đây là **yêu cầu giả định**, không phải lời hứa tự động của replication.

Nếu ứng dụng không chấp nhận mất **bất kỳ ghi đã xác nhận nào** khi mất một region, cần một giao thức commit và durability đủ mạnh trên những miền lỗi mà failure model đề ra, cùng kiểm chứng thực tế.

### 12.2. RTO (Recovery Time Objective)

**RTO** là mục tiêu thời gian khôi phục lại dịch vụ.

Một replica DR có dữ liệu nhưng phải:

- Tạo primary mới.
- Cập nhật quyền truy cập, DNS, firewall/routing.
- Bảo đảm không còn writer cũ tiếp tục ghi.
- Xác nhận bản dữ liệu và thực thi recovery.
- Chờ ứng dụng/queue/cache sẵn sàng.

RTO có thể cao dù dữ liệu đã được sao chép đầy đủ.

### 12.3. Availability SLO

Ví dụ một hợp đồng có thể viết:

> “Trong mất một AZ, API đọc và ghi của những shard còn quorum phải có khả năng phục hồi trong thời gian mục tiêu được kiểm chứng.”

Cần định nghĩa:

- Read nào? Local, majority, snapshot hay linearizable?
- Write nào? Một document hay multi-document transaction?
- Có tính **thời gian failover** vào downtime không?
- Operation trả **PENDING** có được tính là available hay không?
- Khi thiếu quorum, API trả lỗi hay chấp nhận một mức consistency khác?

**Availability của thao tác** quan trọng hơn chỉ báo “máy chủ vẫn ping được”.

### 12.4. Latency SLO

Một write cần ACK từ replica ở region xa có thể phụ thuộc round-trip WAN. Chọn RF cao nhưng không thay mức ACK có thể ít ảnh hưởng write latency hơn chọn một write quorum trải nhiều region.

Không nên đánh đổi latency chỉ dựa trên **trung bình**. Cần đo p95/p99 khi packet loss, congestion, một replica chậm hoặc một AZ tạm mất kết nối.

---

## 13. Durability của replica và quorum không phải một thứ

Giả sử hai replica đều gửi ACK cho một write. Có ít nhất hai câu hỏi:

1. **ACK nghĩa là dữ liệu đã nhận trong RAM hay đã durable theo cơ chế log/journal?**
2. **Giao thức có đảm bảo write sẽ được giữ qua failover, thay leader và replay không?**

Một ACK từ hai node **không tự trả lời** cả hai câu hỏi.

### 13.1. Log, journal và đồng bộ lưu trữ

Một engine có thể:

```text
Client write
     |
     v
Append WAL/commit log
     |
     v
Cập nhật memory state
     |
     v
Sync log theo chính sách
     |
     v
ACK theo write concern
```

Thời điểm và thứ tự chính xác phụ thuộc engine.

Nếu WAL chưa được đồng bộ bền, một sự cố mất nguồn có thể làm mất những thay đổi mới theo fault model của hệ. Nếu hai replica cùng nằm trong một nguồn điện hỏng, hai ACK cũng không bảo vệ khỏi rủi ro chung đó.

### 13.2. Không đặt RPO=0 chỉ từ RF=3

Để đưa ra mục tiêu RPO, cần xác định:

- Ghi nào được coi là **đã commit/ACK**.
- Dữ liệu/log của ghi đó đã bền ở đâu.
- Những miền lỗi nào có thể mất đồng thời.
- Có được bảo vệ trước failover/leader rollback không.
- Quá trình recovery nhận diện đúng commit point ra sao.
- Có backup/PITR để phục hồi sự cố logic không.

RF là một **tham số placement**, không phải hợp đồng khôi phục hoàn chỉnh.

---

## 14. Replication không phải backup

Đây là một phân biệt quan trọng trong vận hành.

| Trường hợp | Replication có thể giúp? | Backup/PITR thường cần? |
| --- | --- | --- |
| Một node chết | Có, nếu replica khác đủ điều kiện | Nên có để bảo vệ rộng hơn |
| Một đĩa hỏng | Có, nếu dữ liệu ở nơi khác bền | Có |
| Mất một AZ | Có, nếu placement/quorum phù hợp | Có |
| Xóa nhầm collection | Replica thường sao chép **cả lệnh xóa** | **Có** |
| Ứng dụng ghi dữ liệu sai logic | Replica có thể lưu cùng dữ liệu sai | **Có**, kèm kiểm tra nghiệp vụ |
| Mã độc mã hóa dữ liệu trên nhiều node | Có thể không | **Immutable/offsite backup** |
| Corruption được phát tán | Có thể không | Backup có kiểm chứng và checksums |
| Mất cả region | Chỉ nếu có topology/DR thích hợp | Có, ở failure domain khác |
| Cần khôi phục về thời điểm hôm qua | Replica hiện tại không đủ | **PITR/snapshot lịch sử** |

### 14.1. Vì sao lỗi logic dễ được nhân bản?

```text
Admin vô tình DROP COLLECTION orders
            |
            v
Primary thực hiện
            |
            v
Replication lan thay đổi
            |
            v
Tất cả replica cùng mất collection
```

Hệ có thể **replicate rất chính xác một lỗi vận hành**. Đó không phải lỗi của replication protocol mà là lý do cần bảo vệ riêng trước deletion/corruption.

### 14.2. Một backup tốt phải kiểm chứng khả năng restore

Cần quan tâm:

- Snapshot/backup có nhất quán khi dữ liệu đang thay đổi không?
- Có PITR từ log hay chỉ snapshot định kỳ?
- Dữ liệu có được mã hóa và key còn phục hồi được không?
- Backup có nằm ngoài miền lỗi của cụm không?
- Có retention và immutable/versioned protection không?
- Có thể restore vào **môi trường riêng** và kiểm tra checksum/bất biến không?
- RTO thực tế của restore có đáp ứng yêu cầu không?

**Backup không kiểm thử khôi phục chỉ là một giả định chưa được chứng minh.**

---

## 15. MongoDB replica set: ví dụ placement qua ba AZ

MongoDB thường tổ chức replica set với primary và secondary, dùng cơ chế election và write concern theo cấu hình.

### 15.1. Sơ đồ triển khai

```text
Region chính
  AZ-a: db-a.example.test :27017  (data-bearing voter)
  AZ-b: db-b.example.test :27017  (data-bearing voter)
  AZ-c: db-c.example.test :27017  (data-bearing voter)

Số voter: 3
Majority: 2
```

Các hostname này chỉ dùng để minh họa. Để thực hành thật, cần ba tiến trình mongod đã được cấu hình và chạy trong **replica set thử nghiệm**, kết nối và bảo mật phù hợp.

### 15.2. Cấu hình khởi tạo minh họa

Chạy trong `mongosh` trên deployment **thử nghiệm đang chuẩn bị để khởi tạo**, không chạy lại trên replica set production đã tồn tại:

```javascript
rs.initiate({
  _id: "rsGeoLab",
  members: [
    {
      _id: 0,
      host: "db-a.example.test:27017",
      priority: 1
    },
    {
      _id: 1,
      host: "db-b.example.test:27017",
      priority: 1
    },
    {
      _id: 2,
      host: "db-c.example.test:27017",
      priority: 1
    }
  ]
});
```

Cần cấu hình tương thích trước đó ở từng node, ví dụ replica set name và network/authentication theo tài liệu MongoDB. Đoạn mã không tự khởi chạy server và không bảo đảm hostname tồn tại.

### 15.3. Một thao tác ghi với majority concern

```javascript
const lab = db.getSiblingDB("nosql_replication_lab");

lab.orders.insertOne(
  {
    _id: "order-01",
    status: "CONFIRMED",
    createdAt: new Date()
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 10000
    }
  }
);
```

`wtimeout` là thời hạn chờ mức write concern trong ví dụ, **không phải bảo đảm rằng khi hết hạn write chưa được áp dụng**. Khi gặp write concern error, dữ liệu có thể đã được ghi một phần hoặc chưa đạt mức xác nhận; ứng dụng cần **đối soát trạng thái** và retry an toàn.

### 15.4. Khi mất AZ chứa primary

- Primary có thể mất kết nối.
- Hai voter còn lại có thể giữ majority, bầu primary mới.
- Driver cần phát hiện topology mới.
- Những request đang chạy có thể gặp lỗi/timeout và cần retry theo semantics được hỗ trợ.

Để nói **không mất dữ liệu đã ACK**, phải xét đúng **write concern, journal/durability, trạng thái majority commit và fault model**. Không nên đồng nhất `w:1` với `w:"majority"`.

### 15.5. Arbiter không thay cho data-bearing replica

Một arbiter có thể giúp bỏ phiếu trong một số topology nhưng không chứa dữ liệu ứng dụng.

Ví dụ hai data nodes + một arbiter ở AZ thứ ba có thể cải thiện một số tình huống election, **nhưng không có ba bản sao dữ liệu**. Đồng thời phải xét khả năng mất node giữ dữ liệu, điều kiện write concern và tính sẵn sàng của ứng dụng.

Không nên dùng arbiter như cách duy nhất để “đạt RF=3”.

---

## 16. Cassandra: topology, replication factor và network topology strategy

Cassandra là ví dụ của hệ NoSQL phân tán kiểu wide-column, nơi các replica được đặt theo partition/token range và topology. Cách xác định consistency khác với majority election của replica set leader–follower.

### 16.1. Cấu hình replication theo datacenter

Ví dụ CQL:

```sql
CREATE KEYSPACE geo_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3,
  'dc2': 3
};
```

Ý nghĩa: keyspace sử dụng replication factor 3 trong `dc1` và 3 trong `dc2`, theo topology và các điều kiện Cassandra hỗ trợ.

**Điều này không nghĩa có tổng cộng sáu node giữ toàn bộ keyspace.** Replicas được phân phối theo partitions và token ranges.

### 16.2. Rack awareness và snitch

Cassandra dùng thông tin datacenter/rack do snitch/topology cung cấp để hỗ trợ việc phân bố replica.

Nếu cấu hình topology khai báo sai — ví dụ ba node thực sự chung một rack nhưng được gắn nhãn khác — thì placement logic không thể bảo vệ trước một sự cố rack thật.

Phải đối chiếu metadata topology với **hạ tầng vật lý**.

### 16.3. LOCAL_QUORUM và QUORUM

Với RF=3 trong một datacenter, `LOCAL_QUORUM` thường yêu cầu mức đa số của replica trong datacenter cục bộ cho operation tương ứng.

Ví dụ ý tưởng:

```sql
CONSISTENCY LOCAL_QUORUM;
SELECT * FROM geo_lab.orders
WHERE order_id = 'order-01';
```

Nhưng:

- `LOCAL_QUORUM` không nhất thiết đợi replica ở datacenter khác.
- Một read/write được xác nhận cục bộ không tự cung cấp RPO=0 khi **mất toàn bộ datacenter/region cục bộ**.
- `QUORUM`, `EACH_QUORUM` và các mức khác có điều kiện/phạm vi riêng; đọc tài liệu đúng version.
- Regular CQL write không mặc nhiên là transaction serializable nhiều partition.

### 16.4. Repair, hinted handoff và anti-entropy

Khi replica tạm offline, hệ cần có cách đưa dữ liệu bắt kịp hoặc sửa lệch theo chính sách.

Những cơ chế như hinted handoff và repair/anti-entropy **không nên hiểu là bảo đảm vĩnh viễn mọi bản ghi còn có thể phục hồi**. Tombstone retention, lịch repair và trạng thái các replica liên quan ảnh hưởng đến khả năng tránh dữ liệu cũ tái xuất hiện.

Sự bền vững dài hạn đòi **vận hành repair và backup**, không chỉ đặt RF.

---

## 17. Redis replication và Sentinel: cần tách vai trò

Redis thường có primary và replica với cơ chế replication riêng. Redis Sentinel có thể giúp giám sát và điều phối failover trong những deployment sử dụng nó.

### 17.1. Replica bất đồng bộ

```text
Redis primary
     |
     +----> Replica A
     |
     +----> Replica B
```

Một replica có thể trễ. Khi primary lỗi, các ghi mới **chưa đến replica được chọn** có thể không còn sau failover, theo cơ chế và thời điểm.

Đừng mặc định nhiều replica Redis đồng nghĩa **durability mạnh của mỗi write đã ACK**.

### 17.2. Sentinel quorum khác số bản sao dữ liệu

Sentinel quorum dùng trong **phát hiện/điều phối failover**, không tự là data write quorum tương đương một transaction majority-committed.

Cần phân biệt:

- Số Redis server giữ dữ liệu.
- Số Sentinel tham gia giám sát/bầu chọn theo thuật toán.
- Dữ liệu replica đã bắt kịp tới đâu.
- AOF/RDB persistence và mức fsync.
- Client được route sang primary mới như thế nào.

Có “ba Sentinel” **không nghĩa có ba bản sao dữ liệu bền**.

### 17.3. Redis Cluster và placement

Với Redis Cluster, cần xem cách master/replica được phân bố trên host/AZ, cùng phạm vi hash slots và failover. Một cluster có nhiều node nhưng mỗi slot không có replica ở miền lỗi độc lập vẫn có thể mất dữ liệu/khả dụng của slot đó khi một miền lỗi hỏng.

---

## 18. Dịch vụ NoSQL được quản lý: đừng đoán số replica

Với một dịch vụ được quản lý như DynamoDB, nhà cung cấp có thể tự quản lý replication và lưu trữ đa AZ theo kiến trúc dịch vụ. Khách hàng không nhất thiết nhìn thấy hoặc điều khiển từng replica như trong một replica set tự quản.

Cần phân biệt:

- **Replication nội vùng** do dịch vụ quản lý.
- **Replication đa vùng** qua tính năng/global table hoặc giải pháp tương đương.
- **Consistency của API đọc** ở một tài nguyên/region cụ thể.
- **Xung đột write đa vùng** và cách hòa giải.
- **Backup/PITR** ở phạm vi được dịch vụ hỗ trợ.
- **Failover và SLA**: có tự động ở mọi tình huống không, có cần đổi route/DNS không?

### 18.1. Không suy diễn từ nhãn “multi-AZ”

Một dịch vụ quảng bá multi-AZ có thể bảo vệ mất một AZ theo những điều kiện cụ thể. Nhưng không thể tự kết luận:

- Mất toàn region vẫn phục vụ không gián đoạn.
- Global tables có strong consistency xuyên mọi region.
- Một transaction local bao trùm mọi bản sao đa vùng.
- Ghi ACK ở region A không thể mất trong bất kỳ loại sự cố nào.
- Backup và PITR mặc nhiên bảo vệ trước tài khoản bị xâm phạm.

**SLA và phạm vi API cụ thể mới là nguồn xác định bảo đảm.**

---

## 19. Placement và mức nhất quán ảnh hưởng latency thế nào?

### 19.1. Một phép so sánh định tính

| Topology | Read gần người dùng | Write cần quorum | Khả năng chịu lỗi |
| --- | --- | --- | --- |
| 3 replica cùng AZ, khác host | Thường nhanh cục bộ | Ít network giữa AZ | Không chống mất AZ |
| 3 replica ở 3 AZ cùng region | Phụ thuộc route | Phải qua AZ trong region | Có thể chống mất một AZ |
| 3 replica ở 3 region | Có replica địa phương mỗi region | Quorum có thể qua WAN | Có thể chống mất một region theo giao thức |
| Region chính + DR async | Read/write chính nhanh hơn | Không cần WAN trên mỗi ACK chính | DR có thể có RPO khác 0 |

Bảng không chứa số latency cụ thể vì chúng phụ thuộc hạ tầng, vị trí, tải, read/write concern và thời điểm quan sát.

### 19.2. Follower phục vụ read nhanh nhưng có thể cũ

Một read gửi tới follower gần người dùng có thể giảm network latency. Nếu người dùng vừa ghi vào primary ở xa, cần thêm cơ chế:

- Read-your-writes trong session.
- Causal consistency/version token.
- Route read về primary trong một khoảng/phạm vi thích hợp.
- Chờ follower đạt minimum version.

**Tối ưu khoảng cách mạng không tự đáp ứng freshness.**

### 19.3. Tail latency của quorum

Nếu quorum cần ACK từ hai trong ba replica, write có thể phụ thuộc vào **replica nhanh thứ hai** theo một mô hình đơn giản. Khi một replica rất chậm hoặc network có packet loss, p95/p99 có thể tăng.

Cần đo dưới nhiều tải và sự cố, không chỉ benchmark khi tất cả node khỏe mạnh.

---

## 20. Capacity planning: mỗi replica có giá thật

Replication factor thường nhân nhu cầu lưu trữ logic lên theo số bản sao, nhưng chi phí thực còn gồm log, index, compaction, snapshot, network và overhead.

Một phép tính sơ bộ:

\[
\text{Dung lượng dữ liệu replication thô} \approx
D_{\text{logical}} \times RF
\]

Nếu có 2 TiB dữ liệu logic và RF=3:

\[
2 \text{ TiB} \times 3 = 6 \text{ TiB}
\]

**6 TiB không phải dự báo dung lượng ổ đĩa cuối cùng.** Còn overhead:

- Index và metadata.
- WAL/commit log hoặc journal.
- MVCC versions/tombstone.
- Dung lượng trống để compaction/rebalance.
- Hệ số nén khác nhau.
- Temporary files và snapshot.
- Backup độc lập.

### 20.1. Băng thông replication

Nếu tốc độ ingest logic là 100 MiB/s, nhiều replica có thể tạo lưu lượng mạng đáng kể, nhất là khi qua region.

Không nên đơn giản nói **network cost = 100 MiB/s × RF** trong mọi kiến trúc: topology fanout, compression, batching, chain replication và data transfer billing có thể khác nhau.

### 20.2. Khôi phục một node có thể làm tăng tải

Khi thay node hỏng, replica mới cần:

1. Nhận snapshot/bootstrap state.
2. Nhận delta/log phát sinh trong lúc copy.
3. Xây dựng/đồng bộ index hoặc metadata nếu engine yêu cầu.
4. Bắt kịp tiến độ.
5. Được phép phục vụ/nhận vai trò theo giao thức.

Quá trình này tiêu thụ I/O, CPU và network của những replica đang sống. Nếu cluster chỉ còn đúng quorum, quá trình rebuild là thời điểm **rủi ro cao trước lỗi tiếp theo**.

---

## 21. Quá trình phục hồi sau mất miền lỗi

Một runbook cần rõ từng bước.

### 21.1. Khi một host chết

```text
1. Phát hiện host/process không còn phục vụ.
2. Phân loại lỗi host hay network.
3. Xác nhận quorum và những shard bị ảnh hưởng.
4. Nếu cần, failover sang replica hợp lệ.
5. Không cho node cũ hoạt động như writer trái phép.
6. Thay host/volume, tạo replica mới.
7. Bootstrap dữ liệu, catch up và kiểm tra state.
8. Xác nhận placement trở lại mức chịu lỗi yêu cầu.
```

Không tự động khởi tạo một cụm rỗng khi network tách và các node còn giữ dữ liệu hợp lệ nhưng tạm không truy cập được.

### 21.2. Khi mất một AZ

Cần kiểm tra:

- Có quorum của từng shard/replica set ở các AZ còn lại không?
- Leader mới có thể được bầu từ thành viên đủ điều kiện không?
- Cấu hình load balancer/DNS có route tới AZ còn sống không?
- Read preference có vô tình buộc client phải đọc AZ đã mất không?
- Các dependency như KMS, secrets, network gateway có nằm cùng AZ không?
- Có còn đủ headroom để gánh tải khi chỉ còn ít replica hơn không?

**Quorum đủ nhưng capacity thiếu** vẫn có thể khiến dịch vụ không đạt SLO.

### 21.3. Khi region bị cô lập

Một region có thể vẫn chạy nhưng không liên lạc với region khác. Nếu cả hai phía đều tin mình là primary, rủi ro **split brain** có thể dẫn đến ghi mâu thuẫn.

Giao thức cần có:

- Membership/election/term hoặc fencing phù hợp.
- Quy tắc xác định bên nào được chấp nhận ghi.
- Cơ chế ngăn primary cũ tiếp tục nhận write khi không còn quyền.
- Chính sách xử lý write đã xác nhận và write chưa commit.
- Quy trình failback tránh overwrite phiên bản mới hơn.

Không nên bật write ở region DR **thủ công theo suy đoán** khi chưa chứng minh primary cũ đã bị cô lập/fenced theo runbook.

---

## 22. Reconfiguration và rủi ro trong giai đoạn chuyển đổi

Replication topology có thể thay đổi khi:

- Thêm/xóa node.
- Thay ổ đĩa hoặc host.
- Nâng cấp phiên bản.
- Chuyển từ hai AZ sang ba AZ.
- Mở region mới.
- Rebalance shard.
- Di chuyển primary để bảo trì.

### 22.1. “Đã tạo node mới” chưa đồng nghĩa an toàn

Một node mới có thể đang ở trạng thái:

```text
CREATED -> BOOTSTRAPPING -> CATCHING_UP -> READY -> VOTING/READING
```

Không nên tính nó vào khả năng phục hồi dữ liệu trước khi nó **đã chứa state đầy đủ và đạt điều kiện tham gia** theo engine.

Nếu chuyển role/quorum quá sớm, cluster có thể có nhiều voter hơn nhưng dữ liệu thực tế chưa được nhân bản theo yêu cầu.

### 22.2. Membership change phải bảo vệ quorum intersection

Trong hệ consensus-based, thay membership an toàn thường cần một giao thức đặc biệt để tránh hai cấu hình cũ/mới đều có thể tạo các quorum không giao nhau và commit những lịch mâu thuẫn.

Không thay nhiều thành viên voting một lúc bằng cách chỉ sửa file cấu hình nếu engine yêu cầu tiến trình reconfiguration an toàn.

### 22.3. Cửa sổ rủi ro khi bảo trì

Ví dụ topology 3 AZ có majority 2/3. Nếu một replica đang bảo trì và một AZ khác mất, chỉ còn một voter → mất majority.

Lịch bảo trì cần:

- Xác nhận tất cả node khỏe mạnh và dữ liệu bắt kịp.
- Giới hạn số node đồng thời không phục vụ.
- Tạm dừng khi phát hiện replication lag hoặc topology bất thường.
- Có kế hoạch rollback.
- Không chạy những thay đổi nguy hiểm khi dự báo hạ tầng đang bất ổn.

---

## 23. Những phụ thuộc ngoài database tạo failure domain ẩn

Ngay cả ba replica được đặt qua ba AZ có thể cùng không phục vụ vì một phụ thuộc chung.

### 23.1. KMS và khóa mã hóa

Nếu dữ liệu được mã hóa và các node không thể lấy hoặc dùng khóa để khởi động/đọc file, chúng có thể không phục vụ dù bản dữ liệu vật lý còn nguyên.

Cần thiết kế key availability, key rotation, quyền, backup/recovery của khóa theo fault model.

### 23.2. DNS, service discovery và load balancer

Database còn khỏe nhưng ứng dụng vẫn không truy cập được nếu:

- Tên miền không phân giải.
- Load balancer chỉ có backend của AZ đã mất.
- Service discovery lưu topology cũ.
- Driver không xử lý lại kết nối/primary election.

**Availability đo từ client** mới phản ánh chất lượng thực tế.

### 23.3. Cấu hình và rollout đồng loạt

Một config lỗi được phát tới mọi node có thể khiến tất cả database process crash. Placement nhiều AZ không chữa được một bug common-mode.

Cần canary, rollout theo đợt, kiểm thử compatibility, feature flags và rollback plan.

### 23.4. Quyền quản trị và lỗi vận hành

Một tài khoản có quyền xóa mọi collection có thể gây mất dữ liệu ở toàn cluster dù có nhiều replica.

Cần least privilege, duyệt thay đổi nguy hiểm, immutable backups, audit, tách trust domain và diễn tập restore.

### 23.5. Monitoring và automation

Một automation coi network partition là “node chết” rồi tự xóa/thay toàn bộ node có thể khiến sự cố trầm trọng hơn.

Health check nên phân biệt **node không phản hồi**, **quorum không đủ**, **control plane lỗi** và **khả năng đọc dữ liệu còn tồn tại**.

---

## 24. Thiết kế từ fault model: ví dụ ứng dụng đặt xe

Một hệ thống cho thuê xe có thể có:

- Truy vấn xe gần vị trí người dùng.
- Xem chi tiết xe.
- Giữ một xe theo khoảng thời gian.
- Xác nhận thanh toán/đơn thuê.
- Lịch sử chuyến đi.
- Báo cáo sử dụng xe.

### 24.1. Không phải mọi dữ liệu cần cùng topology/consistency

| Luồng | Bất biến nghiệp vụ | Mục tiêu replication/failure |
| --- | --- | --- |
| Danh sách xe gần tôi | Hiển thị dữ liệu phù hợp quyền | Read locality, eventual index có freshness SLO |
| Vị trí xe GPS | Chấp nhận độ trễ có giới hạn tùy hợp đồng | Ingest cao, partitioning/retention, replay |
| Giữ xe | Không có hai reservation hợp lệ chồng lấn | Atomic reservation/transaction, write availability rõ |
| Thanh toán | Một paymentId chỉ áp dụng một lần | Durable commit, idempotency, audit, DR |
| Thông tin xe | Đảm bảo ID/tenant/permission đúng | Read-your-writes sau chỉnh sửa, replica phù hợp |
| Lịch sử hóa đơn | Số liệu đúng và có thể kiểm toán | Backup/PITR, snapshot/reporting watermark |
| Bảng thống kê | Chấp nhận cập nhật trễ | Async projection, replica đọc |

### 24.2. Fault model cho thao tác giữ xe

Ví dụ yêu cầu:

> “Mất một AZ trong region chính không được khiến hai yêu cầu giữ cùng một xe và khoảng thời gian đều được xác nhận hợp lệ.”

Để đạt mục tiêu:

1. Bất biến reservation phải được thực thi ở đường ghi.
2. Các thành viên cần cho commit/election phải được bố trí sao cho mất một AZ không tạo hai nhóm writer có quyền.
3. Driver cần xử lý failover và kết quả commit không rõ.
4. Reservation phải có operation ID và kiểm tra thời gian giao nhau đúng.
5. Nếu không có quorum, API có thể trả `PENDING/UNAVAILABLE`, **không được giả xác nhận**.
6. Hệ phải thử hai request cạnh tranh trong lúc failover.

**Replication không thay thế quy tắc không đặt trùng**, nhưng quorum/fencing cần thiết để quy tắc đó được thực thi nhất quán dưới lỗi hạ tầng.

### 24.3. Fault model cho tìm kiếm xe gần tôi

Một read index ở region gần có thể trễ vài giây. Nếu chỉ dùng để gợi ý xe, đây có thể là đánh đổi chấp nhận được.

Khi người dùng bấm giữ xe, hệ **kiểm tra lại trạng thái tại nguồn có thẩm quyền**. Như vậy có thể tối ưu read locality mà không để một read stale cấp phát tài nguyên khan hiếm.

---

## 25. Cách lập ma trận fault domain cho hệ thực

Bắt đầu bằng sơ đồ topology thực, không chỉ sơ đồ mong muốn.

### 25.1. Mẫu bảng

| Component | Region | AZ | Rack/host | Dữ liệu giữ | Voter? | Vai trò | Phụ thuộc chung |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DB-A | R1 | AZ-a | host-a | Shard X | Có | Primary | KMS-1, DNS-1 |
| DB-B | R1 | AZ-b | host-b | Shard X | Có | Secondary | KMS-1, DNS-1 |
| DB-C | R1 | AZ-c | host-c | Shard X | Có | Secondary | KMS-1, DNS-1 |
| DR-D | R2 | AZ-d | host-d | Async standby | Tùy | DR | DNS-1 hoặc khác |

Dữ liệu trong bảng là **ví dụ giả định**, không phải cấu hình một dịch vụ đang tồn tại.

### 25.2. Phương pháp kiểm tra

1. Tập hợp các replica/voter của từng shard.
2. Gắn nhãn failure domain thực tế.
3. Lập danh sách sự cố: mất host, rack, AZ, region, WAN.
4. Với mỗi sự cố, loại các node bị ảnh hưởng.
5. Tính **quorum còn có thể kết nối** và nơi giữ dữ liệu bền.
6. Kiểm tra vai trò leader/election, đường đọc, route client.
7. Kiểm tra capacity sau lỗi, không chỉ số node.
8. Xác định RPO và RTO kỳ vọng.
9. Thiết kế bài test diễn tập.
10. Ghi kết quả đo và cập nhật runbook.

### 25.3. Một câu hỏi khó nhưng bắt buộc

Nếu cả region chính mất, region DR còn dữ liệu thì:

- Dữ liệu đã bắt kịp tới mốc nào?
- Có những ghi ACK nào chưa đến DR?
- Ai được phép công bố DR là primary?
- Primary cũ được fencing bằng cơ chế nào?
- Làm sao tránh duplicate write khi client retry?
- Ứng dụng, secrets, mạng và DNS ở DR đã sẵn sàng chưa?
- Sau khi region cũ trở lại, failback được làm an toàn thế nào?

Nếu chưa trả lời được, chưa nên tuyên bố hệ “tự động chống mất region” chỉ vì có replica DR.

---

## 26. Chỉ số vận hành và cảnh báo

| Nhóm | Chỉ số | Câu hỏi |
| --- | --- | --- |
| **Placement** | Replica count per shard/AZ/region | Có đúng cấu hình chống miền lỗi không? |
| **Membership** | Voting/eligible members | Quorum có thể hình thành ở đâu? |
| **Health** | Node availability | Thành viên nào đang mất? |
| **Replication** | Lag theo byte/time/oplog index | Replica có bắt kịp nguồn không? |
| **Durability** | WAL/journal sync status | ACK đã đạt chính sách bền chưa? |
| **Failover** | Election duration/count | Chuyển leader tốn bao lâu? |
| **Quorum** | Write/read concern errors | Có đang thiếu ACK? |
| **Performance** | Read/write p95/p99 | SLO có bị ảnh hưởng khi một node mất? |
| **Repair** | Rebuild/repair progress | Mất bao lâu khôi phục RF? |
| **Capacity** | CPU, disk, network, headroom | Tải sau lỗi còn chịu được không? |
| **Availability** | Error rate từ phía client | Người dùng còn hoàn tất operation không? |
| **DR** | Backup age, RPO watermark, restore time | Mất region sẽ mất gì, phục hồi bao lâu? |

### 26.1. Không chỉ cảnh báo “node down”

Với RF3, báo “một node down” là cần thiết nhưng không đủ. Cần biết:

- Node này có thuộc cùng AZ với một node đang bảo trì không?
- Shard nào vừa mất majority?
- Replica còn lại có bắt kịp và có thể làm leader không?
- Có bao nhiêu replication backlog?
- Đang có write concern timeout nhưng client vẫn coi là thành công không?
- SLO độ trễ sau failover tăng bao nhiêu?

Các chỉ số phải gắn với **tính sẵn sàng và đúng đắn của operation**, không chỉ trạng thái cơ sở hạ tầng.

---

## 27. Thử nghiệm resilience có kiểm soát

Không nên tuyên bố fault tolerance chỉ từ sơ đồ. Cần test theo fault model trong môi trường phù hợp.

### 27.1. Bài test mất một process

1. Tạo tải read/write với operation ID và version.
2. Dừng một database process trong môi trường thử.
3. Ghi nhận read/write latency, error rate và quorum.
4. Cho node khởi động lại.
5. Kiểm tra nó replay/catch up.
6. So sánh dữ liệu được ACK với trạng thái cuối.

Mất process khác với mất điện: OS cache có thể còn. Không suy ra power-loss durability chỉ từ test process stop.

### 27.2. Bài test mất một host

Thực hiện mô phỏng lỗi host/VM trong môi trường disposable để kiểm tra anti-affinity, failover và rebuild.

Kiểm tra riêng:

- Sự cố có đồng thời làm mất replica khác cùng host không?
- Driver/ingress có route lại được không?
- Số shard vẫn có majority?
- Có data loss hoặc write rollback vượt hợp đồng không?

### 27.3. Bài test mất một AZ

- Cô lập nhóm node ở AZ A.
- Kiểm tra B/C còn hình thành majority.
- Thực thi read và write theo mức nhất quán yêu cầu.
- Ghi độ trễ failover và số lỗi.
- Xác nhận dữ liệu sau khi AZ A trở lại.
- Kiểm tra cụm không đón nhận một primary cũ trái phép.

Chỉ thực hiện ở môi trường thử được phép và có rollback/runbook.

### 27.4. Bài test network partition

```text
Partition 1: A
Partition 2: B + C
```

Với majority 2/3, phần B+C có thể tiếp tục ghi theo giao thức hợp lệ. Phần A không được tự tạo một leader majority cạnh tranh.

Nếu một request đã được gửi lúc mất mạng và client nhận timeout, kết quả có thể **unknown**. Ứng dụng cần idempotency/đối soát, không tạo operation mới tùy ý.

### 27.5. Bài test mất region và khôi phục

Một DR drill đầy đủ nên kiểm tra:

1. Ứng dụng có chuyển route sang vùng DR được không?
2. Thời gian khôi phục (RTO) bao lâu?
3. Độ lệch dữ liệu tại điểm phục hồi (RPO) là gì?
4. Những ghi ACK nào có mặt/vắng mặt?
5. Các service phụ thuộc như IAM/KMS/DNS/queue có hoạt động không?
6. Thực thi read/write thật với dữ liệu thử có an toàn không?
7. Failback khi region cũ trở lại có tránh split brain không?

Không làm bài test phá hủy trên production khi chưa có môi trường và quy trình được phê duyệt.

---

## 28. Những sai lầm phổ biến

### 28.1. “RF=3 nghĩa là chịu được ba lỗi”

Sai. Số replica không bằng số lỗi độc lập có thể chịu; còn placement, loại lỗi và quorum.

### 28.2. “Ba replica trên ba VM nghĩa là ba failure domain”

Chưa chắc. Ba VM có thể nằm trên cùng host vật lý, rack, AZ hoặc shared storage.

### 28.3. “Có một replica ở region khác là chống được mất region chính”

Không nếu region DR chỉ có một voter và majority còn nằm ở region chính, hoặc chưa có quy trình promote/restore.

### 28.4. “Mất một AZ thì không có downtime”

Không nhất thiết. Election, DNS/routing, driver retry và tải chuyển tiếp có thể gây gián đoạn tạm thời.

### 28.5. “Có hai voter là đã chịu được lỗi một voter”

Với majority 2/2, mất một voter là không đủ majority.

### 28.6. “Arbiter được tính là bản sao dữ liệu bền”

Sai. Arbiter/witness thường không giữ user data.

### 28.7. “Quorum intersection bảo đảm hệ linearizable”

Không tự động. Cần giao thức ordering/commit và xử lý conflict, reconfiguration, durability.

### 28.8. “Một node còn sống nghĩa là dữ liệu vẫn available”

Có thể còn dữ liệu nhưng không đủ quorum để ghi hoặc client không truy cập được.

### 28.9. “Node đã nhận ghi nghĩa là đã fsync”

Không thể suy từ ACK nếu chưa biết durability policy.

### 28.10. “Replication có thể thay backup”

Sai. Xóa nhầm, corruption, ransomware và nhiều lỗi logic được nhân bản cùng dữ liệu.

### 28.11. “Có nhiều AZ là hết common-mode failure”

Không. Vẫn có lỗi control plane, DNS, IAM, KMS, phần mềm hoặc thao tác vận hành.

### 28.12. “Quorum local ở một datacenter bảo đảm không mất ghi nếu cả datacenter mất”

Không mặc nhiên. Nếu các replica ở datacenter khác chưa nhận/sync, RPO có thể khác 0.

### 28.13. “Một DR replica có dữ liệu tức là failover nhanh”

Không chắc. Cần promote, fencing, secrets, route ứng dụng, capacity và validation.

### 28.14. “Có RF cao thì chi phí chỉ tăng dung lượng”

Còn network, WAL, compaction, repair, lag, CPU và yêu cầu capacity dự phòng.

### 28.15. “Maintenance không tính là lỗi”

Bảo trì làm giảm redundancy và có thể khiến cluster dễ mất quorum khi xảy ra lỗi tiếp theo.

### 28.16. “Có 2 node còn sống nên chắc chắn có quorum”

Không nếu hai node không liên lạc được, hoặc membership/voting eligibility khác giả định.

### 28.17. “Replica giống nhau nghĩa là business state đúng”

Không. Tất cả replica có thể cùng lưu số tồn kho âm do write path sai. Replication không thay transaction/constraint.

### 28.18. “Backup chạy thành công nghĩa là chắc chắn restore được”

Chưa. Phải kiểm tra khôi phục, key/permissions, checksum, RPO/RTO và dữ liệu thực tế.

---

## 29. Bài tập tự kiểm tra

### Bài 1: ba process cùng host

Một hệ có ba database process giữ ba bản sao nhưng đều nằm trên một máy vật lý. Nếu mainboard máy đó hỏng, hệ còn bao nhiêu bản sao truy cập được?

**Gợi ý:** Có thể mất cả ba cùng lúc. Đây không phải ba failure domain độc lập.

### Bài 2: ba host cùng rack

Replica ở ba máy khác nhau nhưng cùng dùng một switch top-of-rack và nguồn rack. Cần thay placement thế nào để chịu lỗi một rack?

**Gợi ý:** Phân tán replica qua các rack độc lập và giữ quorum sau khi mất một rack.

### Bài 3: RF=3, majority=2

Ba replica ở ba AZ. Mất AZ A nhưng B và C liên lạc được. Majority còn không?

**Gợi ý:** Còn hai trong ba voter, có thể đạt majority theo giả định.

### Bài 4: RF=3, 2–1 region

R1 có hai voter, R2 có một voter. Khi R1 mất hoàn toàn, R2 còn một voter. Có thể tiếp tục majority write ngay không?

**Gợi ý:** Không; 1/3 không đạt majority=2.

### Bài 5: hai voter

Một hệ có đúng hai voter trên hai AZ, cần cả hai để đạt majority. Mất một AZ thì sao?

**Gợi ý:** Không đủ quorum; hai voter không chịu được mất một voter với majority.

### Bài 6: witness

Hệ có hai data nodes và một witness. Có ba bản sao dữ liệu không?

**Gợi ý:** Không. Witness không phải data replica nếu chỉ tham gia bầu chọn.

### Bài 7: quorum intersection

Với N=5, R=3, W=3, chứng minh R+W>N và nói điều gì **chưa thể** kết luận.

**Gợi ý:** 3+3=6>5 nên có giao nhau trong tập cố định. Chưa đủ để kết luận linearizable, durability hay invariant đa key.

### Bài 8: mất hai AZ

Ba voter ở ba AZ, mất đồng thời hai AZ. Có còn majority không?

**Gợi ý:** Chỉ còn 1/3; thiếu majority.

### Bài 9: network partition

A nằm một phía, B+C nằm phía kia. Theo majority 2/3, phía nào có thể được quyền tiếp tục commit?

**Gợi ý:** Phía B+C nếu giao thức và các điều kiện khác thỏa. A không được tự làm primary majority.

### Bài 10: read replica cũ

Primary đã ghi `PAID`, secondary vẫn trả `PENDING`. Có nhất thiết dữ liệu transaction đã sai không?

**Gợi ý:** Không. Có thể replica lag; cần xem read preference/consistency và business invariant riêng.

### Bài 11: replication và xóa nhầm

Lệnh xóa nhầm collection đã được replicate sang mọi node. Tăng RF có giúp lấy lại bản hôm qua không?

**Gợi ý:** Không. Cần backup, snapshot lịch sử hoặc PITR độc lập.

### Bài 12: RPO và RTO

Có một DR replica bất đồng bộ đang chậm 30 giây; khôi phục DNS/ứng dụng cần nhiều phút. Hãy phân biệt RPO và RTO.

**Gợi ý:** RPO liên quan dữ liệu có thể mất; RTO liên quan thời gian dịch vụ hoạt động trở lại. Con số quan sát không phải bảo đảm cứng.

### Bài 13: local quorum

Một keyspace có RF3 trong datacenter dc1 và RF3 ở dc2. Write được xác nhận theo LOCAL_QUORUM tại dc1. Có thể tự kết luận write đã durable ở dc2 không?

**Gợi ý:** Không. Cần xem replication tiến độ và chính sách durability/consistency từng datacenter.

### Bài 14: Cassandra rack awareness

Ba node thực ở cùng rack nhưng metadata topology khai báo ba rack khác nhau. Nếu rack hỏng thì điều gì xảy ra?

**Gợi ý:** Placement thực không chống được lỗi rack; metadata sai không tạo tách biệt vật lý.

### Bài 15: Redis Sentinel

Ba Sentinel bỏ phiếu failover, nhưng chỉ có một Redis instance giữ dữ liệu. Có được coi là có ba data replica không?

**Gợi ý:** Không. Voting/monitoring members khác data-bearing replicas.

### Bài 16: capacity rebuild

Mất một node chứa 2 TiB dữ liệu. Replica mới cần bootstrap từ các node còn sống. Những chỉ số nào cần theo dõi để không làm ứng dụng nghẽn?

**Gợi ý:** Network, disk throughput, CPU, backlog, replication lag, write/read p95/p99, remaining free space và thời gian rebuild.

### Bài 17: DR mà không có fencing

Region chính mất kết nối WAN, đội vận hành bật writer ở region DR. Region chính chưa bị dừng và vẫn nhận write cục bộ. Rủi ro chính?

**Gợi ý:** Split brain và dữ liệu mâu thuẫn. Cần fencing/authority protocol.

### Bài 18: common-mode software bug

Replica đặt ở ba AZ độc lập nhưng cùng bản nâng cấp có bug khiến cả ba process crash. Tăng số AZ có đủ không?

**Gợi ý:** Không. Cần canary, rollout theo đợt, rollback và phân tách failure domain phần mềm.

### Bài 19: xác định miền lỗi cho hệ đặt xe

Một hệ chỉ chấp nhận một reservation cho mỗi xe và khoảng thời gian. Mất AZ chứa primary phải không tạo hai reservation CONFIRMED.

**Hỏi:** Replication/quorum và business constraint mỗi phần bảo vệ điều gì?

**Gợi ý:** Quorum/fencing ngăn hai nguồn ghi có thẩm quyền cạnh tranh; unique/transaction/reservation protocol bảo vệ bất biến cụ thể.

### Bài 20: viết fault matrix

Hãy thiết kế topology RF3 hoặc RF5 cho một hệ phải chịu mất một AZ và yêu cầu RPO/RTO rõ ràng. Lập bảng cho lỗi host, rack, AZ, WAN và region.

**Gợi ý:** Với từng lỗi, đếm quorum còn kết nối, nơi có dữ liệu bền, đường route client, capacity và khả năng restore. Không chỉ ghi “OK/FAIL” mà không nêu giả định.

---

## 30. Quy trình thiết kế topology replication từ yêu cầu

Một quy trình có thể dùng cho cả NoSQL tự vận hành và managed service:

1. **Xác định mục tiêu nghiệp vụ.** Mỗi operation có yêu cầu availability, RPO, RTO và freshness gì?
2. **Liệt kê loại sự cố cần chịu.** Process, host, rack, AZ, region, WAN, corruption, thao tác nhầm.
3. **Vẽ dependency graph.** Node, volume, network, KMS, DNS, IAM, monitoring, control plane.
4. **Phân loại failure domains.** Tìm những tài nguyên có thể cùng lỗi do shared fate.
5. **Xác định replication semantics.** Leader/follower, quorum, đa leader, async hay sync.
6. **Chọn số replica và voter.** Tính quorum theo protocol cụ thể, không dùng một công thức chung cho mọi hệ.
7. **Đặt replica theo miền lỗi.** Anti-affinity trên mỗi shard/partition với rack/AZ/region phù hợp.
8. **Kiểm tra những sự cố đã chọn.** Loại node trong từng fault domain và xác định quorum có còn kết nối không.
9. **Kiểm tra dữ liệu thực sự durable ở đâu.** WAL/journal sync, majority commit và failover logs.
10. **Kiểm tra bất biến nghiệp vụ.** Replication không thay atomic condition, unique constraint, transaction hoặc idempotency.
11. **Thiết kế backup và DR riêng.** PITR, immutable backup, retention, restore drill, fencing và failback.
12. **Dự tính capacity khi lỗi.** Cụm còn sống phải đủ tài nguyên để phục vụ và rebuild.
13. **Viết runbook.** Phân biệt node chết, network partition, mất AZ và mất region.
14. **Kiểm thử có điều phối.** Đo failover, stale reads, data loss, RPO/RTO và kết quả client nhìn thấy.
15. **Giám sát theo shard và theo operation.** Không chỉ xem node up/down.
16. **Lặp lại sau mọi reconfiguration.** Thêm node, migrate shard hoặc đổi region có thể thay đổi failure domain.

### Bảng chốt quyết định nhanh

| Yêu cầu | Điều phải kiểm tra |
| --- | --- |
| Chịu mất một host | Replica thực sự trên nhiều host vật lý và còn đủ quorum |
| Chịu mất một rack | Placement khác rack, switch/power independence |
| Chịu mất một AZ | Replica/voter trải AZ, majority còn kết nối, app route và capacity |
| Chịu mất một region | Quorum/DR ở region khác, RPO/RTO, WAN, fencing và failback |
| Không mất ghi ACK | Write concern, journal/log sync, commit protocol, fault model |
| Đọc gần người dùng | Read locality, staleness/session guarantees |
| Không ghi trùng nghiệp vụ | Unique/conditional/transaction/idempotency, **không chỉ replication** |
| Chống xóa nhầm/corruption | Backup/PITR, immutable storage, restore test |
| Rolling upgrade không gián đoạn | Quorum headroom, lag, one-at-a-time maintenance |
| Cụm tự hồi phục sau node loss | Bootstrap, catch-up, placement validation và đủ capacity |

**Kết luận:** Tạo nhiều bản sao trong NoSQL là cách xây **khả năng chịu lỗi và phục hồi**, nhưng hiệu quả của replication phụ thuộc mạnh vào **mục tiêu cần bảo vệ** và **miền lỗi thực tế của từng bản sao**. Ba replica trên cùng một miền lỗi có thể cùng biến mất; ba replica ở ba AZ có thể giữ majority sau mất một AZ nhưng chưa chống được mất cả region; một replica DR có thể phục hồi dữ liệu mà vẫn cần thời gian, fencing và failback. Thiết kế đáng tin phải kết hợp **replica placement, quorum semantics, durability, RPO/RTO, khả năng tiếp cận từ client, capacity và backup độc lập**. Chỉ khi phân tích và thử nghiệm từng failure domain, ta mới có cơ sở nói rằng hệ NoSQL thực sự chịu được loại sự cố đã cam kết.
