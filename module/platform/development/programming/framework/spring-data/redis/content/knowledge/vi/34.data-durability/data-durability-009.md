# Lập mục tiêu mất dữ liệu cho phép và thời gian phục hồi trong Spring Data Redis

## 1. Tại sao phải đặt mục tiêu độ bền dữ liệu trước khi cấu hình Redis?

Redis thường được giới thiệu là hệ lưu trữ có độ trễ thấp, nhưng một ứng dụng Spring Data Redis có thể dùng Redis cho rất nhiều loại thông tin: cache sản phẩm, phiên đăng nhập, giỏ hàng, trạng thái xử lý tạm, bộ đếm giới hạn tốc độ, Redis Stream hoặc dữ liệu nghiệp vụ có khả năng phát sinh tác động bên ngoài. **Không phải loại dữ liệu nào cũng cần mức độ bền và tốc độ khôi phục giống nhau.**

Giả sử ứng dụng có Redis phục vụ ba chức năng:

- Cache danh mục sản phẩm: mất toàn bộ key vẫn có thể tải lại từ cơ sở dữ liệu chính.
- Giỏ hàng chưa đồng bộ sang nguồn khác: mất key có thể khiến người dùng mất công sức.
- Stream chứa lệnh tạo đơn hàng chưa được xử lý: mất một entry có thể khiến một đơn hàng bị bỏ sót.

Cùng một sự cố mất Redis primary, tác động nghiệp vụ khác nhau hoàn toàn.

Vì thế, trước khi chọn Redis RDB, AOF, replication, Sentinel, Cluster hay backup, cần trả lời hai câu hỏi:

1. **Được phép mất tối đa bao nhiêu dữ liệu?** Đây là mục tiêu **RPO – Recovery Point Objective**.
2. **Được phép mất tối đa bao nhiêu thời gian để phục hồi dịch vụ?** Đây là mục tiêu **RTO – Recovery Time Objective**.

Lập RPO và RTO theo **tác động nghiệp vụ**, không chỉ theo khả năng mặc định của Redis, giúp tránh hai sai lầm đối lập: đầu tư giải pháp phức tạp cho cache có thể tái tạo, hoặc dùng cấu hình cache đơn giản cho dữ liệu mà mất vài giây đã gây hậu quả lớn.

Bài học trình bày cách xác định RPO/RTO, chuyển chúng thành lựa chọn về persistence và kiến trúc Redis, tổ chức kiểm thử phục hồi và tích hợp chính sách xử lý sự cố trong Spring Data Redis.

---

## 2. RPO là gì?

**RPO (Recovery Point Objective)** là lượng dữ liệu thay đổi gần nhất mà tổ chức có thể chấp nhận mất khi khôi phục sau sự cố. Có thể biểu diễn theo **thời gian** tính lùi từ thời điểm sự cố tới điểm khôi phục được chấp nhận.

Ví dụ hệ thống có:

```text
RPO mục tiêu = 5 phút

10:00  Điểm khôi phục được bảo đảm theo mục tiêu
10:01  Có ghi dữ liệu mới
10:02  Có ghi dữ liệu mới
10:03  Có ghi dữ liệu mới
10:04  Có ghi dữ liệu mới
10:05  Sự cố

Mục tiêu: dữ liệu phục hồi không được cũ hơn 10:00
(tức mất tối đa khoảng 5 phút thay đổi mới nhất).
```

**RPO không phải thời gian cần để khôi phục**. Nó là độ cũ tối đa được chấp nhận của dữ liệu đã khôi phục so với thời điểm sự cố.

Một số ví dụ:

| Loại dữ liệu | RPO có thể lựa chọn | Ý nghĩa |
|---|---|---|
| Cache sản phẩm có thể dựng lại | Không yêu cầu giữ cache | Có thể mất toàn bộ cache nếu nguồn chính vẫn đúng |
| Thống kê thời gian thực tạm | 5–15 phút | Một phần số liệu mới cần được tính lại |
| Giỏ hàng chỉ có trong Redis | 30–60 giây hoặc chặt hơn | Mất giỏ hàng có ảnh hưởng tới người dùng |
| Stream nghiệp vụ chưa có bản sao | Gần 0, hoặc cần nguồn bền vững hơn | Mất event có thể gây bỏ sót thao tác |
| Trạng thái thanh toán đã xác nhận | Thường yêu cầu không mất giao dịch | Không nên chỉ dựa vào một Redis lưu trữ có rủi ro mất ghi |

Các con số trong bảng là **ví dụ để thảo luận với nghiệp vụ**, không phải chuẩn áp dụng cho mọi sản phẩm.

### 2.1. RPO = 0 có nghĩa gì?

RPO bằng 0 có nghĩa **không chấp nhận mất bất kỳ thay đổi đã được xác nhận thành công nào**. Đây là yêu cầu rất mạnh.

Một Redis có persistence và replica **không tự động bảo đảm RPO = 0 trong mọi kiểu sự cố**. Ví dụ:

- Redis primary đã phản hồi thành công cho một lệnh ghi, nhưng dữ liệu chưa fsync bền vững lên disk.
- Primary và replica dùng replication bất đồng bộ; primary chết trước khi bản ghi mới được chuyển tới replica.
- Disk hoặc backup chứa bản ghi mới bị hỏng cùng lúc với node.
- Ứng dụng timeout sau khi gửi lệnh và không biết thao tác đã thực hiện hay chưa.

Nếu nghiệp vụ thật sự yêu cầu không mất dữ liệu đã commit, cần thiết kế kiến trúc lưu trữ, xác nhận ghi, khả năng chịu lỗi, khôi phục và kiểm chứng thích hợp; với một số loại giao dịch, nên dùng cơ sở dữ liệu bền vững làm nguồn sự thật và Redis làm lớp tăng tốc hoặc dẫn xuất.

### 2.2. RPO mục tiêu khác RPO thực tế

**RPO mục tiêu** là con số nghiệp vụ chấp nhận. **RPO đạt được** chỉ có thể đánh giá dựa trên kiến trúc, tình huống hỏng và bằng chứng kiểm thử.

Một bản backup được tạo mỗi giờ chưa chứng minh RPO trong mọi trường hợp là một giờ:

- Backup có thể chưa hoàn tất hoặc bị lỗi.
- Backup có thể chưa được sao chép sang vùng lưu trữ an toàn.
- Backup gần nhất có thể không đọc được.
- Nếu khôi phục chỉ từ backup trong khi AOF mới hơn còn tồn tại, RPO thực tế phụ thuộc nguồn phục hồi được chọn.

Vì thế cần xác định rõ **điểm khôi phục được bảo đảm** cho từng kịch bản sự cố.

---

## 3. RTO là gì?

**RTO (Recovery Time Objective)** là thời gian tối đa được phép để khôi phục một dịch vụ hoặc một năng lực nghiệp vụ sau khi bị gián đoạn.

Ví dụ:

```text
RTO mục tiêu = 10 phút

14:00  Redis primary không còn phục vụ
14:01  Hệ thống giám sát phát hiện lỗi
14:03  Replica được chuyển thành primary
14:04  Spring Boot kết nối lại
14:06  Các API chính hoạt động ổn định
14:07  Hệ thống xác minh khôi phục

Thời gian phục hồi quan sát ≈ 7 phút
=> nằm trong mục tiêu 10 phút của ví dụ.
```

RTO không chỉ là thời gian Redis process khởi động:

- Cần **phát hiện** sự cố.
- Cần **chuyển đổi** hoặc **khôi phục** Redis.
- Cần **khởi tạo lại kết nối** từ các service Spring Boot.
- Có thể cần **nạp lại dữ liệu** từ RDB/AOF hoặc nguồn chuẩn.
- Có thể cần **làm nóng cache** hoặc khôi phục trạng thái consumer.
- Cần **xác minh luồng nghiệp vụ** trước khi tuyên bố dịch vụ đã phục hồi.

### 3.1. Khác biệt với những khái niệm gần

| Thuật ngữ | Diễn giải |
|---|---|
| RPO | Mức mất dữ liệu tối đa cho phép |
| RTO | Thời gian gián đoạn tối đa cho phép |
| MTTD (Mean Time To Detect) | Thời gian trung bình để phát hiện sự cố |
| MTTR (Mean Time To Recover/Repair) | Thời gian trung bình để khôi phục/sửa chữa, theo cách tổ chức định nghĩa |
| Availability SLO | Mức khả dụng mong muốn trong một cửa sổ đo |
| Recovery time thực tế | Khoảng thời gian đo được trong một lần sự cố hoặc diễn tập |

MTTR là **giá trị thống kê trung bình**, không tự bảo đảm mọi lần sự cố đáp ứng RTO. Một hệ thống có MTTR 2 phút vẫn có thể có một lần ngừng 60 phút và vi phạm RTO 10 phút.

### 3.2. Nên đo RTO từ lúc nào?

Trong tài liệu khôi phục, phải nêu rõ:

```text
Bắt đầu: thời điểm dịch vụ không đạt tiêu chí phục vụ đã thỏa thuận.
Kết thúc: thời điểm các luồng nghiệp vụ bắt buộc hoạt động trở lại
          và đạt điều kiện xác minh phục hồi.
```

Nếu chỉ đo từ khi đội vận hành bắt đầu khởi động Redis mà bỏ qua 10 phút hệ thống chưa phát hiện sự cố, kết quả sẽ không phản ánh tác động tới khách hàng.

---

## 4. RPO và RTO không thể đánh đồng

Hai mục tiêu độc lập.

Một hệ thống có thể:

- **RTO ngắn, RPO chưa đủ chặt:** replica được promote nhanh, nhưng mất một số lệnh ghi cuối cùng vì replication chưa kịp.
- **RPO rất chặt, RTO dài:** bản ghi gần nhất nằm trong AOF an toàn, nhưng quá trình khôi phục dataset rất lớn mất nhiều thời gian.
- **Cả hai đều thoải mái:** cache có thể tái tạo, chấp nhận khởi động lại và nạp lại trong vài giờ.
- **Cả hai đều nghiêm ngặt:** yêu cầu cơ sở hạ tầng, vận hành và mô hình dữ liệu có chi phí cao hơn.

Ví dụ ma trận:

| | RTO 1 phút | RTO 1 giờ |
|---|---|---|
| **RPO 0–1 giây** | Cần cả failover nhanh và cơ chế hạn chế mất ghi rất chặt; phải thử nghiệm thực tế | Dữ liệu gần như phải giữ đủ, nhưng có thể dành thời gian khôi phục |
| **RPO 15 phút** | Tập trung tính sẵn sàng, chấp nhận một phần dữ liệu mới mất | Có thể dùng backup/snapshot đơn giản hơn nếu nghiệp vụ cho phép |

**Không lấy con số `appendfsync everysec` rồi suy ra ứng dụng đương nhiên có RPO = 1 giây và RTO = 1 giây.** Thời gian fsync, thời gian replica nhận dữ liệu và thời gian phục hồi là các cơ chế khác nhau, chưa kể các kiểu sự cố vượt ngoài một node.

---

## 5. Phân loại dữ liệu Spring Data Redis trước khi đặt mục tiêu

Cùng một cụm Redis có thể phục vụ nhiều use case. Mỗi nhóm dữ liệu cần trả lời **Redis có phải nguồn sự thật cuối cùng không?**

### 5.1. Redis chỉ là cache

Ví dụ:

```java
@Cacheable(cacheNames = "productView", key = "#p0")
public ProductView getProduct(String sku) {
    return productRepository.findBySku(sku)
            .orElseThrow();
}
```

Nếu Redis cache bị xóa hoàn toàn, ứng dụng vẫn có thể tải lại dữ liệu từ database chuẩn. **Mất cache không tương đương mất dữ liệu nghiệp vụ**.

RPO của cache có thể được mô tả là “không yêu cầu giữ các entry đã cache”. Nhưng RTO của **dịch vụ đọc sản phẩm** vẫn quan trọng: database có đủ capacity phục vụ khi toàn bộ request trở thành cache miss không?

Như vậy có hai việc khác nhau:

- Khôi phục Redis cache service.
- Giữ API khả dụng khi cache mất dữ liệu.

Một ứng dụng có cơ chế bỏ qua cache khi Redis lỗi có thể duy trì hoạt động dù Redis chưa phục hồi, nhưng chỉ khi nguồn chuẩn đủ năng lực và lỗi cache được xử lý đúng.

### 5.2. Redis giữ session hoặc giỏ hàng

Nếu session đăng nhập chỉ tồn tại trong Redis, mất key có thể khiến người dùng bị đăng xuất. Nếu giỏ hàng chỉ lưu Redis, mất dữ liệu có thể mất toàn bộ danh sách sản phẩm người dùng chọn.

RPO cần được thảo luận theo trải nghiệm:

- Có chấp nhận tất cả người dùng phải đăng nhập lại khi Redis hỏng không?
- Có chấp nhận mất thay đổi giỏ hàng trong 30 giây gần nhất không?
- Giỏ hàng có bản sao ở database không?
- Có thể khôi phục từ lịch sử thao tác của người dùng không?

**TTL không phải cơ chế backup.** Một session hết TTL theo quy tắc là sự kiện vòng đời bình thường, không phải sự cố mất dữ liệu. Ngược lại, Redis bị mất disk làm mất session còn TTL là vấn đề độ bền.

### 5.3. Redis chứa Streams hoặc hàng đợi công việc

Một Stream có thể chứa event chưa được consumer xử lý. Nếu event mất do node hỏng trước khi replication hoặc persistence hoàn tất, consumer không thể khôi phục chỉ từ offset/PEL.

Phải xác định:

- Event đã được lưu trong nguồn bền vững nào khác chưa?
- Producer có thể phát lại event không?
- Consumer có thể xử lý trùng an toàn không?
- Có cơ chế đối soát để phát hiện event bị thiếu không?
- Redis Stream là nguồn sự thật hay chỉ là kênh truyền tạm?

Khi thông điệp bắt buộc không được mất, việc dùng Redis Stream cùng AOF/replication **cần được đánh giá theo failure model cụ thể**; trong một số thiết kế, transactional outbox trong cơ sở dữ liệu chính mới là cơ chế bảo đảm không mất ý định phát event.

### 5.4. Redis lưu kết quả liên quan tiền/quyền

Nếu Redis giữ trạng thái thanh toán, quyền sử dụng gói trả phí, hạn mức đã tiêu hoặc idempotency record, mất bản ghi có thể khiến giao dịch bị xử lý trùng hoặc quyền được cấp sai.

Trong nhiều kiến trúc, nên giữ **ledger nghiệp vụ bền vững** ở nguồn có tính nhất quán và ràng buộc phù hợp; Redis dùng để đọc nhanh, chống tải hoặc hỗ trợ phối hợp.

RPO cần xuất phát từ câu hỏi “mất một ghi đã xác nhận có gây sai tiền, sai quyền hoặc vi phạm quy định không?”, không phải “Redis có bật AOF chưa?”.

---

## 6. Thiết lập bảng mục tiêu theo chức năng

Một tài liệu RPO/RTO hữu dụng nên gắn mục tiêu với **năng lực người dùng**, không chỉ với tên node.

Ví dụ một bảng thảo luận:

| Chức năng | Vai trò của Redis | RPO ví dụ | RTO ví dụ | Hành vi khi Redis lỗi |
|---|---|---|---|---|
| Trang danh mục | Cache có thể dựng lại | Không cần giữ cache | API vẫn phục vụ trong 2 phút | Bỏ qua cache, giới hạn tải DB |
| Session | Kho session tạm | 1 phút | 5 phút | Thông báo đăng nhập lại hoặc tạm lỗi |
| Giỏ hàng | Trạng thái chưa đồng bộ | 30 giây | 10 phút | Tải bản lưu khác nếu có |
| Bộ đếm rate limit | Kiểm soát tải | Mất vài giây có thể chấp nhận tùy rủi ro | 1 phút | Fail-closed hoặc limiter dự phòng |
| Stream thông báo phi quan trọng | Truyền dữ liệu có thể dựng lại | 5 phút | 15 phút | Producer có thể replay |
| Stream đặt hàng không có nguồn khác | Event quan trọng | Gần 0, cần thiết kế bổ sung | 5 phút | Dừng tiếp nhận nếu không bảo đảm ghi |

**Đây là số liệu minh họa**, không phải cam kết kỹ thuật của Redis. Để sử dụng thật phải có owner nghiệp vụ phê duyệt, phân tích thiệt hại, khối lượng dữ liệu và phương án kiểm chứng.

Một hệ thống có thể có nhiều mức:

- **Tầng ứng dụng:** API nào được phép trả kết quả suy giảm?
- **Tầng dữ liệu:** bản ghi nào phải sống sót sau failover/disaster?
- **Tầng Redis:** persistence và replication nào đáp ứng yêu cầu?
- **Tầng vận hành:** ai khôi phục, mất bao lâu, chứng minh bằng gì?

---

## 7. Redis lưu dữ liệu chủ yếu trong bộ nhớ: cần phân biệt hai dạng khôi phục

Redis phục vụ phần lớn lệnh trên dữ liệu trong memory. Khi có sự cố, việc khôi phục phụ thuộc dữ liệu còn nằm ở đâu.

### 7.1. Restart cùng node và disk còn tốt

Nếu Redis process dừng hoặc server restart nhưng disk persistence vẫn nguyên vẹn, Redis có thể nạp RDB/AOF để khôi phục state.

Thời gian phục hồi gồm khởi động tiến trình, đọc dữ liệu từ disk, tái tạo state trong memory, kiểm tra service và kết nối lại client.

### 7.2. Mất node hoặc disk

Nếu disk của primary bị mất hoàn toàn, file persistence cục bộ cũng mất. Phải khôi phục từ:

- Replica còn dữ liệu phù hợp.
- Backup nằm ngoài node.
- Bản sao tại vùng lưu trữ khác.
- Nguồn dữ liệu nghiệp vụ có thể xây dựng lại Redis.

Hai tình huống trên có thể có RPO/RTO rất khác nhau. Cấu hình `appendonly yes` trên một disk không biến disk đó thành backup ngoại vi.

### 7.3. Mất cả cụm hoặc cả vùng

Một sự cố datacenter/availability zone có thể ảnh hưởng đồng thời primary, replica và backup nếu mọi bản sao đều nằm chung vùng lỗi.

RPO/RTO cho **disaster recovery** cần tính khả năng:

- Replica/backup được đặt ở failure domain khác.
- Dữ liệu có được chuyển tới vùng dự phòng trước sự cố hay không.
- Mạng, DNS, secret, cấu hình và hạ tầng Spring Boot có thể khởi động ở vùng dự phòng không.
- Có cơ chế xác nhận vùng mới không gây ghi đồng thời vào hai primary khác nhau không.

**Replication, persistence và backup là ba lớp bổ sung, không thay thế nhau.**

---

## 8. RDB snapshot và ảnh hưởng tới RPO

**RDB (Redis Database)** là cơ chế lưu snapshot của tập dữ liệu Redis tại một thời điểm. Redis có thể tạo snapshot theo lịch hoặc theo yêu cầu.

Ví dụ cấu hình tự quản lý trong `redis.conf`:

```conf
save 900 1
save 300 10
save 60 10000

dbfilename dump.rdb
dir /var/lib/redis
```

Ý nghĩa các dòng `save`:

- Sau khoảng 900 giây, nếu có ít nhất một thay đổi, Redis có thể tạo snapshot.
- Sau khoảng 300 giây với ít nhất 10 thay đổi, có thể tạo snapshot.
- Sau khoảng 60 giây với ít nhất 10.000 thay đổi, có thể tạo snapshot.

Các điều kiện là **quy tắc kích hoạt snapshot**, không phải bảo đảm rằng cứ đúng mốc là có một file RDB mới hoàn tất.

### 8.1. RPO với RDB-only

Giả sử snapshot thành công lúc 10:00, Redis tiếp tục nhận ghi, và process/disk hỏng lúc 10:04. Nếu chỉ có snapshot 10:00 có thể phục hồi, các thay đổi sau 10:00 có nguy cơ mất.

```text
10:00  RDB snapshot hoàn tất
10:01  Write A
10:02  Write B
10:03  Write C
10:04  Redis mất disk

Khôi phục từ RDB 10:00
=> A, B, C không tồn tại trong bản khôi phục.
```

Nếu cần RPO thấp hơn khoảng cách snapshot, chỉ RDB định kỳ có thể không đáp ứng.

**RDB phù hợp khi:**

- Dữ liệu có thể khôi phục từ nguồn khác.
- Có thể chấp nhận mất thay đổi từ snapshot gần nhất.
- Cần backup snapshot tương đối dễ lưu trữ/di chuyển.
- Muốn khởi động từ một hình ảnh dataset đã được tạo.

### 8.2. Chi phí snapshot

Redis có thể tạo snapshot ở tiến trình nền bằng `BGSAVE`. Trong quá trình snapshot, cơ chế fork/copy-on-write có thể tạo áp lực tài nguyên, đặc biệt với dataset lớn và tốc độ ghi cao.

Cần dự toán:

- Memory có dư địa cho copy-on-write không?
- Disk có đủ dung lượng và I/O throughput không?
- Snapshot hoàn thành trong bao lâu?
- Có thất bại do thiếu disk/permission không?
- Việc chụp snapshot có làm latency tăng vượt SLO không?

Một cấu hình “snapshot mỗi 60 giây” không hữu ích nếu Redis liên tục không thể lưu snapshot thành công.

### 8.3. Quan sát tình trạng RDB

Một số lệnh Redis có thể dùng trong môi trường được cấp quyền:

```redis
INFO persistence
LASTSAVE
```

Những trường như thời điểm save thành công gần nhất, tình trạng `rdb_bgsave_in_progress` và kết quả lần save trước giúp hiểu khoảng trống bảo vệ dữ liệu.

Không lấy riêng `LASTSAVE` làm bằng chứng RPO cho toàn hệ thống: nó không cho biết backup đã được chuyển sang vùng an toàn hay chưa, và một snapshot cũ không đại diện những ghi mới sau thời điểm snapshot.

---

## 9. AOF và ảnh hưởng tới RPO

**AOF (Append Only File)** ghi lại các thao tác thay đổi dữ liệu theo dạng log để Redis có thể phát lại khi khởi động. Với cấu hình phù hợp, AOF giúp giảm khoảng dữ liệu có nguy cơ mất so với chỉ snapshot định kỳ.

Ví dụ:

```conf
appendonly yes
appendfsync everysec
```

### 9.1. Các chế độ appendfsync

| Cấu hình | Hành vi tổng quát | Đánh đổi |
|---|---|---|
| `appendfsync always` | Yêu cầu fsync cho mỗi lần ghi/nhóm ghi theo cơ chế thực thi | Có khả năng giảm cửa sổ mất ghi ở lỗi process/OS, nhưng tốn disk I/O và latency hơn |
| `appendfsync everysec` | Redis thường fsync khoảng mỗi giây | Cân bằng phổ biến giữa hiệu năng và độ bền, nhưng vẫn có cửa sổ dữ liệu chưa bền vững |
| `appendfsync no` | Để hệ điều hành quản lý thời điểm fsync | Ít kiểm soát hơn về lượng dữ liệu có thể mất khi crash |

**Không diễn giải `everysec` thành cam kết RPO tuyệt đối đúng 1 giây.** Thời gian fsync thực tế chịu ảnh hưởng của disk, hệ điều hành, tải, việc AOF rewrite, tình huống crash và môi trường lưu trữ. Ngay cả chế độ `always` cũng không bảo đảm chống mọi lỗi đồng thời như mất toàn bộ disk hoặc lỗi ngoài phạm vi một node.

### 9.2. AOF rewrite và restart

Nếu mọi lệnh ghi được append mãi, file AOF có thể tăng rất lớn. Redis hỗ trợ **AOF rewrite** để tạo biểu diễn ngắn gọn hơn của trạng thái hiện tại mà vẫn giữ khả năng phục hồi theo cơ chế của phiên bản Redis.

Ví dụ các tham số thường gặp:

```conf
auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb
```

Các tham số này không trực tiếp đặt RPO; chúng điều chỉnh điều kiện rewrite nhằm kiểm soát kích thước log. Một file AOF lớn có thể tăng thời gian replay khi khởi động, ảnh hưởng RTO.

Trong các phiên bản Redis mới, AOF có thể gồm nhiều file và **manifest**. Khi backup/restore, không nên chỉ sao chép tùy tiện một file có tên giống `appendonly.aof` mà bỏ qua cấu trúc AOF thực tế của phiên bản đang chạy.

### 9.3. Khi bật đồng thời RDB và AOF

Redis có thể được cấu hình cả RDB và AOF. Với cách thiết lập thông thường, nếu AOF được bật và hợp lệ, Redis ưu tiên dữ liệu từ AOF để phục hồi vì có thể chứa các thay đổi gần thời điểm dừng hơn RDB.

Tuy nhiên, **ưu tiên nguồn nạp** không thay thế quy trình kiểm tra tính toàn vẹn, bản backup và dữ liệu đang có. Khi AOF bị lỗi/corrupt, cần kế hoạch khôi phục thích hợp dựa trên các bản sao và hướng dẫn của phiên bản Redis.

### 9.4. Chọn AOF có đáp ứng RPO không?

Quy trình nên là:

1. Xác định RPO tối đa mà nghiệp vụ chấp nhận.
2. Xác định các failure mode cần chống: crash process, mất OS, mất disk, mất node, mất zone.
3. Đánh giá chế độ fsync và vùng lưu trữ thật sự.
4. Đánh giá replication và bản sao độc lập.
5. Đo kết quả khôi phục trong diễn tập, gồm các ghi gần thời điểm sự cố.
6. Ghi lại những tình huống chưa được bảo vệ.

Không chọn `appendfsync always` chỉ bằng cách so sánh số giây mà bỏ qua mức chịu tải, disk latency và topology.

---

## 10. Replication: cải thiện tính sẵn sàng nhưng không bảo đảm mọi ghi

Redis replication thường **bất đồng bộ**. Primary nhận lệnh ghi, xử lý và phát dữ liệu tới replica theo cơ chế replication. Replica có thể chưa nhận được những ghi mới nhất vào đúng thời điểm primary gặp sự cố.

Ví dụ:

```text
Client          Primary            Replica
  | SET A -------->|                  |
  |<------ OK ------|                  |
  |                 | ---- replicate A -->  (chưa tới)
  |                 X Primary chết
  |
  |                     Replica mới được promote
  |                     nhưng chưa có A
```

Kết quả: ứng dụng đã nhận phản hồi thành công cho `SET A`, nhưng primary mới sau failover có thể chưa chứa A. Đây là rủi ro RPO từ **replication lag**.

### 10.1. Redis Sentinel và Redis Cluster

- **Sentinel** hỗ trợ theo dõi primary/replica và điều phối failover của Redis deployment phù hợp. Nó không tự biến replication thành đồng bộ tuyệt đối.
- **Redis Cluster** phân phối hash slot và có khả năng failover theo cơ chế cluster. Với một shard, việc promote replica vẫn chịu rủi ro mất phần dữ liệu chưa replication.
- **Managed Redis** có thể cung cấp failover tự động, backup và công cụ vận hành. Cam kết độ bền cụ thể phải xem chính sách triển khai/SLA, không suy ra chỉ từ tên dịch vụ.

### 10.2. WAIT không đồng nghĩa ghi bền trên disk

Redis cung cấp lệnh `WAIT` để đợi một số replica xác nhận đã nhận dữ liệu replication trước đó từ kết nối đang gửi lệnh:

```redis
SET demo:critical-key value
WAIT 1 1000
```

Ý nghĩa khái quát: sau khi ghi, yêu cầu đợi tối đa khoảng 1.000 mili giây để có ít nhất một replica xác nhận tiến độ replication tương ứng. Giá trị trả về cho biết số replica đạt điều kiện xác nhận.

**Quan trọng:**

- `WAIT` không tự bảo đảm dữ liệu đã fsync bền vững lên disk của replica.
- Phản hồi của `WAIT` phải được kiểm tra; nếu trả về số replica thấp hơn yêu cầu, ứng dụng phải quyết định xử lý.
- `WAIT` không thay Redis replication thành một hệ thống consensus có bảo đảm strong consistency trong mọi tình huống failover.
- Nếu ứng dụng dùng connection pooling hoặc pipeline, phải hiểu mối liên hệ giữa lệnh ghi và lệnh `WAIT` trên **cùng client connection** theo semantics Redis, thay vì gọi `WAIT` bất kỳ ở một connection khác rồi suy ra đã bảo vệ lệnh ghi trước đó.

Trong các phiên bản Redis có hỗ trợ, `WAITAOF` bổ sung khả năng đợi xác nhận fsync AOF theo tham số thích hợp; vẫn cần xem hướng dẫn phiên bản và failure model trước khi coi nó là đáp án RPO của cả hệ thống.

### 10.3. min-replicas-to-write và min-replicas-max-lag

Redis có các tham số cấu hình giúp primary **từ chối ghi** khi không có đủ replica đáp ứng điều kiện về số lượng và độ trễ phản hồi:

```conf
min-replicas-to-write 1
min-replicas-max-lag 10
```

Ví dụ này yêu cầu ít nhất một replica được xem là đủ gần về trạng thái liên lạc để primary cho phép ghi, theo ngưỡng lag 10 giây.

Nhưng đây **không phải synchronous replication**: nó không chứng minh **mỗi lệnh ghi vừa nhận OK** đã được xác nhận bởi replica cụ thể trước khi trả lời. Thiết lập này chuyển một phần rủi ro sang **giảm khả dụng ghi** khi replica gặp sự cố.

Cần quyết định chính sách có chấp nhận từ chối request ghi để hạn chế rủi ro mất dữ liệu hay không.

---

## 11. Backup khác replication như thế nào?

Replica giúp tiếp tục phục vụ khi primary hỏng, nhưng không bảo vệ đầy đủ trước các sự cố làm thay đổi dữ liệu hợp lệ theo cách không mong muốn:

```text
Operator vô tình chạy FLUSHDB
            |
            v
Primary xóa key
            |
            v
Replica nhận cùng thao tác xóa
            |
            v
Cả hai đều không còn dữ liệu
```

Nếu không có backup được lưu tách biệt, replication không giúp quay lại thời điểm trước thao tác xóa.

Backup phục vụ khả năng khôi phục từ một **điểm lịch sử** và bảo vệ trước một số lỗi logic/vận hành. Khi thiết kế backup cho Redis cần quyết định:

- Backup **dữ liệu gì**: RDB, bộ file AOF hợp lệ hoặc cơ chế snapshot do nhà cung cấp cung cấp.
- Backup **khi nào** và tần suất bao nhiêu.
- Backup có **tồn tại sau khi mất node/region** không.
- Backup có thể **đọc được** và khôi phục trong thời gian mong muốn không.
- Dữ liệu backup có được **mã hóa** và kiểm soát quyền truy cập không.
- Thời gian lưu bao lâu và ai có quyền xóa.
- Nếu dataset nhiều shard, có cần checkpoint nhất quán cho toàn bộ dữ liệu hay không.

### 11.1. Không sao chép tùy tiện file persistence đang thay đổi

Trong quá trình Redis đang tạo snapshot, rewrite AOF hoặc ghi log, việc copy một tập file không được phối hợp có thể tạo bản sao thiếu nhất quán hoặc không đủ thành phần.

Nên dùng cơ chế backup được hỗ trợ của Redis/managed service, hoặc quy trình snapshot ở tầng lưu trữ có tính nhất quán và được kiểm chứng; với AOF nhiều file, phải giữ cả cấu trúc cần thiết.

Không dừng hoặc di chuyển file persistence đang dùng trong production chỉ để thử backup mà thiếu kế hoạch.

### 11.2. Backup cũng có RPO và RTO riêng

Ví dụ:

```text
Backup RDB mỗi 15 phút
Sao chép ra storage ngoài zone mất thêm tối đa 5 phút
Restore 80 GB dữ liệu mất 25 phút
Khởi động lại ứng dụng và xác minh mất 5 phút
```

Nếu mất toàn bộ node và chỉ backup ngoài zone sống sót, dữ liệu an toàn có thể **cũ hơn thời điểm sự cố tới nhiều phút**. RTO cũng phải tính ít nhất việc tải backup, phục hồi Redis và kiểm tra API.

Con số “backup mỗi 15 phút” không đủ làm cam kết RPO 15 phút nếu backup hoàn tất muộn, copy thất bại hoặc không có bản hợp lệ.

### 11.3. Nên kiểm tra phục hồi chứ không chỉ kiểm tra file tồn tại

Một backup được tạo thành công theo log chưa chứng minh có thể khôi phục. Cần thử:

1. Chọn backup hiện có.
2. Phục hồi vào **môi trường cách ly**, không ghi đè production.
3. Khởi động Redis bằng cấu hình, secret và version phù hợp.
4. Đọc những key mẫu và kiểm tra dữ liệu nghiệp vụ.
5. Đo thời gian hoàn tất tới trạng thái có thể phục vụ.
6. Ghi lại lỗi, độ cũ dữ liệu và thao tác thủ công cần thiết.

---

## 12. Xây dựng failure model cho Redis

Muốn RPO/RTO có nghĩa, cần xác định những sự cố mà mục tiêu áp dụng.

| Kịch bản | Dữ liệu có thể mất? | Cơ chế khôi phục chính | Điểm cần đo |
|---|---|---|---|
| Redis process crash, disk còn | Ghi chưa bền vững có thể mất | Restart và nạp RDB/AOF | Data age, restart/replay time |
| OS/kernel crash hoặc power loss | Phụ thuộc fsync/disk | Restart từ persistence | Ghi cuối trước crash, tính toàn vẹn |
| Primary chết, replica còn | Ghi chưa replicate có thể mất | Sentinel/Cluster failover | Replication lag, failover time |
| Disk primary hỏng hoàn toàn | Mất file local | Promote replica hoặc restore backup | Replica gap, restore time |
| Xóa nhầm key / FLUSHDB | Replica cũng có thể bị ảnh hưởng | Restore backup hoặc nguồn chuẩn | Point-in-time backup còn được |
| Hết bộ nhớ/eviction | Key có thể biến mất theo policy | Capacity mitigation, restore/rebuild | Tỉ lệ eviction, khả năng phục hồi |
| Network partition | Client có thể không ghi/đọc; split behavior | Failover, điều phối ghi, reconnect | Thời gian lỗi, khả năng mất ghi |
| Mất cả zone | Primary/replica cùng vùng đều có thể mất | Replica/backup khác zone | RPO/RTO xuyên zone |
| Mất cả region | Cần bản sao ngoài region | Disaster recovery site | Thời gian kích hoạt DR, dữ liệu lệch |
| Sai cấu hình/serializer app | Dữ liệu không đọc được hoặc bị ghi sai | Rollback code/schema, restore | Kế hoạch rollback và migration |

**Không đặt một RPO/RTO chung chỉ cho sự cố process crash nếu business yêu cầu phục hồi cả khi mất region.** Mỗi kịch bản có thể cần mục tiêu riêng, sau đó chọn mức nghiêm ngặt tổng thể phù hợp.

---

## 13. Chuyển mục tiêu nghiệp vụ thành lựa chọn Redis

Một ma trận thiết kế tham khảo:

| Mức mục tiêu | Ví dụ nhu cầu | Lựa chọn thường xem xét | Cảnh báo |
|---|---|---|---|
| Không yêu cầu giữ cache | Có thể đọc lại DB | Redis không persistence hoặc persistence tối thiểu, cache TTL, khả năng fallback | RTO của API phụ thuộc sức tải DB |
| Có thể mất nhiều phút | Dữ liệu tạm/analytics | RDB snapshot và backup phù hợp | Khoảng cách snapshot không phải bảo đảm RPO |
| Muốn giảm mất ghi gần thời điểm crash | Session/giỏ hàng quan trọng hơn cache | AOF `everysec`, replica và backup | Không được quảng bá như RPO tuyệt đối 1 giây |
| Muốn giảm sâu cửa sổ mất ghi trên node | Dữ liệu quan trọng, latency cho phép | AOF `always`, replica và cơ chế đợi xác nhận thích hợp | Phải đo latency, disk và tình huống failover |
| Cần gần như không mất giao dịch | Ledger/side effect bắt buộc | Nguồn dữ liệu bền vững có ràng buộc transaction; Redis hỗ trợ cache/coordination | Không dựa chỉ vào Redis persistence + async replica |
| RTO giây/phút thấp | API quan trọng | Failover tự động, monitoring, client reconnect, warm standby | Failover nhanh có thể kèm mất một số ghi |
| RTO hàng giờ | Công cụ nội bộ | Restore từ backup, runbook thủ công | Cần kiểm tra restore thực tế |

Đây không phải bảng cấu hình máy móc. **Một lựa chọn persistence có thể tốt cho một kịch bản nhưng không đủ cho kịch bản khác**; hãy đánh giá đồng thời chi phí, mục tiêu và failure domain.

### Câu hỏi cần chốt trong thiết kế

1. Redis là nguồn sự thật hay bản sao?
2. Một write được coi là “thành công với người dùng” khi nào?
3. Nếu mất write đó thì có thể phát lại/idempotent không?
4. Sự cố nào phải chịu đựng: process, disk, node, zone hay region?
5. Ai chịu trách nhiệm phục hồi và có quyền cần thiết không?
6. Dữ liệu nhiều shard có yêu cầu snapshot nhất quán toàn hệ thống không?
7. Đã có bằng chứng diễn tập gần đây chưa?

---

## 14. RTO bao gồm khôi phục hạ tầng và khôi phục ứng dụng Spring

Một hệ thống Spring Boot có thể mất khả dụng lâu hơn Redis server vì connection pool, retry hoặc quy trình khởi động chưa sẵn sàng.

Ví dụ:

```text
Sự cố Redis bắt đầu                          00:00
Monitoring phát hiện                         00:25
Hệ thống quyết định failover                  00:55
Replica được promote                         01:20
Client Spring Boot tìm primary mới            01:45
Ứng dụng vượt qua giai đoạn timeout/retry      02:05
Cache nóng dần, API đạt latency mục tiêu       03:15
Kiểm tra read/write, cảnh báo đóng lại         03:35

Recovery time quan sát: khoảng 3 phút 35 giây
```

Nếu RTO mục tiêu là 2 phút, tuy Redis primary mới phục vụ sau 1 phút 20 giây, toàn bộ dịch vụ vẫn vi phạm mục tiêu. Cần cải thiện các khâu:

- Phát hiện lỗi nhanh hơn.
- Failover tự động và cấu hình Sentinel/Cluster/managed Redis đúng.
- Client Redis có cơ chế topology discovery/reconnect phù hợp.
- Timeout không kéo dài request bất hợp lý.
- Readiness/health checks phản ánh khả năng thực sự phục vụ nghiệp vụ.
- Cache warmup hoặc fallback để API đạt SLA sau khi Redis trở lại.

### 14.1. Phân biệt readiness và liveness

Nếu Redis tạm thời không hoạt động:

- Một endpoint **chỉ phục vụ được khi Redis còn** có thể cần readiness báo không sẵn sàng.
- Một endpoint **có thể bỏ qua cache** thì service chưa chắc cần bị loại khỏi load balancer.
- Liveness không nên làm ứng dụng bị restart vô hạn chỉ vì Redis lỗi vài giây.

Không dùng duy nhất Redis `PING` để kết luận mọi nghiệp vụ đã phục hồi: một server có thể đáp ứng PING nhưng đang tải persistence chậm, không có dữ liệu cần thiết, kết nối nhầm cluster hoặc không thể ghi.

### 14.2. Không đặt retry vô hạn

Khi failover, việc retry có thể giúp vượt lỗi tạm thời. Nhưng retry không giới hạn với cùng delay ngắn có thể tạo **retry storm** lên Redis vừa phục hồi.

Nên chọn:

- Timeout theo ngân sách của request.
- Backoff và jitter.
- Giới hạn số lần thử.
- Giới hạn số lệnh in-flight/concurrency.
- Chính sách fail-open/closed theo dữ liệu.
- Idempotency nếu thao tác ghi có thể được thực thi trước khi client timeout.

**Timeout không có nghĩa Redis chắc chắn chưa nhận lệnh ghi.** Một lệnh như `INCR` hoặc `XADD` có thể đã thực thi trong lúc client mất kết nối. Tự retry có thể làm tăng bộ đếm hoặc tạo event trùng, ảnh hưởng tính đúng đắn sau phục hồi.

---

## 15. Thiết kế fail-open/fail-closed trong kế hoạch RTO

Khi Redis lỗi, không nhất thiết mọi endpoint phải ngừng cùng nhau.

Ví dụ:

| Chức năng | Redis có vai trò gì? | Chính sách khi lỗi | Ảnh hưởng RTO |
|---|---|---|---|
| Tìm kiếm sản phẩm | Cache | Fail-open có giới hạn tải DB | API có thể đạt RTO thấp dù Redis chưa hồi phục |
| Session đăng nhập | Kho session | Trả lỗi tạm thời/đăng nhập lại tùy security | RTO phụ thuộc phục hồi kho session |
| Giới hạn tốc độ login | Kiểm soát bảo mật | Fail-closed hoặc limiter dự phòng | Không để sự cố Redis bỏ qua bảo vệ |
| Checkout | Cache giá tạm | Đọc giá chuẩn trước khi chốt | Có thể tiếp tục nếu nguồn chuẩn khỏe |
| Stream nhận lệnh thanh toán | Kênh xử lý quan trọng | Tạm từ chối nhận mới nếu không bảo đảm bền vững | RTO của chức năng nhận lệnh phụ thuộc cơ chế bền vững |

Một chính sách “Redis down thì tất cả HTTP trả 500” có thể khiến RTO nghiệp vụ dài hơn cần thiết. Ngược lại, nuốt mọi lỗi Redis để API luôn trả 200 có thể che giấu mất dữ liệu, mất idempotency hoặc bỏ qua kiểm tra quyền.

**RTO không được cải thiện bằng cách giả vờ chức năng đã phục hồi khi dữ liệu cần thiết không đáng tin cậy.** Phải đặt tiêu chí phục hồi gắn với hành vi nghiệp vụ đúng.

---

## 16. Tích hợp với Spring Data Redis: khả năng kết nối không đồng nghĩa dữ liệu bền vững

Spring Data Redis cung cấp các abstraction như:

- `StringRedisTemplate` và `RedisTemplate` cho lệnh Redis imperative.
- `ReactiveRedisTemplate` cho thao tác reactive với driver hỗ trợ.
- Redis Repository cho entity hash và TTL trong phạm vi tính năng của repository.
- Redis Streams, Pub/Sub và các API chuyên biệt.

Những API này **không tự chọn RPO/RTO**. Kết quả độ bền phụ thuộc cấu hình Redis server, topology, storage, cách xác nhận ghi và logic khôi phục nghiệp vụ.

Ví dụ đơn giản:

```java
@Service
public class CartStateService {

    private final StringRedisTemplate redis;

    public CartStateService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void saveCart(String userId, String serializedCart) {
        redis.opsForValue().set(
                "cart:v1:" + userId,
                serializedCart,
                Duration.ofDays(7)
        );
    }

    public String loadCart(String userId) {
        return redis.opsForValue().get("cart:v1:" + userId);
    }
}
```

Imports tương ứng:

```java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;
```

Code này ghi giá trị và TTL, nhưng **không bảo đảm**:

- AOF đã fsync.
- Replica đã nhận write.
- Backup mới nhất chứa write.
- Sau failover cart chắc chắn tồn tại.
- Khôi phục toàn bộ cart mất dưới 5 phút.

Nếu `saveCart` phải đem lại bảo đảm “không được mất giỏ hàng đã lưu”, cần kiến trúc và quy trình xác nhận phù hợp chứ không chỉ thêm `try/catch` quanh `set`.

### 16.1. Redis transactions không giải quyết RPO một mình

`MULTI`/`EXEC` cho phép gom lệnh Redis thực thi theo thứ tự, nhưng không biến lệnh thành dữ liệu bền vững trước mọi kiểu crash. Tương tự, `@Transactional` trong Spring không có nghĩa Redis và SQL cùng commit nguyên tử.

Khi một entity liên quan cả Redis và database:

```text
1. SQL commit thành công.
2. Ứng dụng ghi Redis cache.
3. Redis failover làm mất write mới nhất.
```

Nếu Redis chỉ là cache, có thể tái tạo. Nếu Redis giữ trạng thái nghiệp vụ duy nhất, cần giải pháp bền vững khác hoặc đối soát.

### 16.2. Chú ý TTL sau restore

Một tập key có TTL được phục hồi từ snapshot/AOF vẫn chịu ngữ nghĩa expiration. Redis lưu thời hạn theo mốc thời gian phù hợp với cơ chế persistence. Trong quá trình phục hồi, key đã hết hạn có thể không còn được khôi phục dưới dạng key còn sống.

Vì vậy, số lượng key sau restore có thể nhỏ hơn trước khi sự cố, ngay cả khi backup không bị hỏng. Cần phân biệt:

- Dữ liệu **mất ngoài ý muốn** do điểm khôi phục cũ.
- Dữ liệu **hết hạn hợp lệ** theo TTL.
- Dữ liệu **bị eviction** trước snapshot.
- Dữ liệu **bị trim/xóa** theo logic ứng dụng.

Đối với session hoặc token, không nên kéo dài hạn dùng chỉ để đạt RTO ngắn: hạn bảo mật vẫn phải được tôn trọng.

---

## 17. Thiết kế checkpoint và khả năng phát lại cho Redis Streams

Nếu dùng Redis Streams cho event nghiệp vụ, RPO không chỉ liên quan phần dữ liệu có trên server, mà còn liên quan khả năng xác định **event nào đã được xử lý**.

Ví dụ:

```text
Producer phát OrderCreated
    |
    v
XADD orders:events *
    |
    v
Consumer đọc event
    |
    v
Ghi vào database đơn hàng
    |
    v
XACK sau khi xử lý thành công
```

Những rủi ro:

1. Redis mất event sau khi `XADD` được xác nhận nhưng trước khi event được lưu bền vững theo failure model.
2. Consumer xử lý xong nhưng crash trước `XACK` → event có thể được xử lý lại.
3. Event chưa xử lý bị `XTRIM` quá sớm → không còn trên Stream.
4. Backup chỉ bao gồm Stream ở thời điểm cũ, nhưng database đã có tác động mới hơn.
5. Một producer bị timeout rồi thử lại `XADD` → có thể tạo event trùng.

Các yêu cầu cần được thiết kế:

- **Idempotent consumer:** xử lý lại cùng event không gây side effect sai.
- **Checkpoint/ack hợp lý:** không ack trước khi logic nghiệp vụ thành công.
- **Retention:** giữ event đủ lâu để consumer chậm có thể bắt kịp.
- **Replay:** có nguồn phát lại event nếu Redis Stream bị mất hoặc trim.
- **Reconciliation:** có cách đối chiếu trạng thái nguồn chuẩn và trạng thái tiêu thụ event.

Với giao dịch rất quan trọng, một **transactional outbox** ở database nguồn có thể giảm rủi ro “business commit thành công nhưng ý định phát event vào Redis bị mất”. Outbox được commit cùng dữ liệu nghiệp vụ, sau đó worker phát lại cho tới khi xử lý hoàn tất.

Không đồng nhất Redis Stream với cơ chế archive vĩnh viễn; Stream cũng có thể bị xóa/trim và chịu rủi ro persistence/replication như những Redis key khác.

---

## 18. Xây dựng kế hoạch backup/restore theo RPO và RTO

Một kế hoạch khôi phục cần chỉ rõ **điểm phục hồi**, **nguồn phục hồi**, **thao tác** và **điều kiện thành công**.

### 18.1. Định nghĩa kịch bản

Ví dụ:

```text
Sự cố: mất toàn bộ Redis primary VM và disk.
Còn lại: replica ở zone B, backup ngoài zone.
Mục tiêu:
  RPO <= 60 giây đối với session store.
  RTO <= 10 phút cho API đăng nhập.

Chiến lược dự kiến:
  Ưu tiên failover sang replica hợp lệ.
  Nếu replica cũng không khả dụng, restore từ backup.
  Đo dữ liệu cuối được bảo vệ và thời gian phục vụ lại.
```

Mục tiêu trên là **giả định minh họa**, không thể được xác nhận nếu chưa đo replication lag, hành vi failover và kết quả restore backup.

### 18.2. Runbook cần có gì?

Một runbook thực thi được nên nêu:

1. **Điều kiện kích hoạt:** metric/alert nào xác nhận lỗi thật?
2. **Người chịu trách nhiệm:** ai xử lý Redis, ai xử lý Spring Boot, ai quyết định failover?
3. **Lệnh kiểm tra an toàn:** lấy trạng thái Redis, persistence, replication, topology.
4. **Cơ chế failover:** do Sentinel/Cluster/managed service tự động hay thao tác thủ công?
5. **Cách chọn dữ liệu phục hồi:** replica nào mới nhất, backup nào hợp lệ?
6. **Cách ngăn ghi vào primary cũ:** tránh hai nguồn nhận write đồng thời khi network partition.
7. **Cách khôi phục kết nối client:** endpoint, DNS, credentials, TLS và driver reconnect.
8. **Kiểm tra sau phục hồi:** thử read/write, kiểm tra TTL, key mẫu, event backlog, latency.
9. **Đối soát dữ liệu:** phát hiện những thao tác nghiệp vụ có thể bị mất/trùng.
10. **Thời gian và kết quả:** ghi mốc phát hiện, bắt đầu khôi phục, phục vụ lại và kết thúc xác minh.

Không đặt mật khẩu Redis, backup access key hoặc dữ liệu nhạy cảm trực tiếp trong runbook lưu công khai. Sử dụng secret manager và quyền truy cập giới hạn.

### 18.3. Lệnh quan sát không phá hủy

Trên Redis có quyền đọc phù hợp:

```redis
PING
INFO server
INFO persistence
INFO replication
INFO memory
INFO stats
ROLE
```

Các lệnh này giúp hiểu trạng thái server, replication, persistence và memory ở thời điểm kiểm tra. Trong Redis Cluster còn cần xác nhận phân bố slot/topology theo deployment.

**Không chạy** `FLUSHALL`, `FLUSHDB`, `DEBUG SEGFAULT`, `SHUTDOWN NOSAVE` hoặc phá hủy Redis production để “thử RPO” khi chưa có môi trường cách ly và kế hoạch được phê duyệt. Diễn tập có thể dùng môi trường staging mô phỏng failure mode và các công cụ hạ tầng được kiểm soát.

---

## 19. Đo RPO thực tế trong diễn tập như thế nào?

RPO khó đo nếu chỉ nhìn Redis đang chạy hay không. Cần có **bằng chứng về thứ tự/timestamp của các ghi đã xác nhận** và kiểm tra chúng sau khi khôi phục.

Một phương pháp an toàn trong môi trường thử nghiệm:

1. Tạo workload ghi các record probe có ID tăng dần và timestamp từ nguồn đáng tin cậy.
2. Ghi lại bên ngoài Redis **những ID đã được ứng dụng nhận xác nhận thành công**.
3. Tạo sự cố có kiểm soát trong môi trường thử nghiệm.
4. Khôi phục bằng chính quy trình dự kiến dùng khi sự cố thật.
5. Đọc dữ liệu Redis sau phục hồi.
6. Xác định ID mới nhất đã được bảo vệ và những ID/ghi nào bị mất.
7. So sánh thời điểm ghi gần nhất bị thiếu với thời điểm sự cố theo cách đo đã thống nhất.
8. Ghi kết quả theo failure mode, không chỉ một con số trung bình.

Ví dụ:

```text
Sự cố bắt đầu        : 12:10:00
Ghi được xác nhận cuối: 12:09:59.900
Ghi mới nhất còn lại : 12:09:58.700

Ước tính cửa sổ mất dữ liệu ≈ 1,2 giây
(theo luồng probe và điều kiện diễn tập).
```

Không thể dùng một lần thử được 1,2 giây để quảng bá Redis “bảo đảm RPO 1,2 giây”. Phải lặp lại dưới nhiều mức tải, loại sự cố, cấu hình disk/network và version, đồng thời xem các trường hợp xấu nhất có ý nghĩa với mục tiêu nghiệp vụ.

### 19.1. Ghi cuối cùng có thể không liền mạch

Khi ghi đồng thời từ nhiều client, thứ tự xác nhận và thứ tự dữ liệu không đơn giản như một biến đếm tăng đều. Probe nên dùng ID có thể đối soát, phân biệt **lệnh gửi đi**, **lệnh được Redis xử lý** và **lệnh đã được ứng dụng báo thành công**.

Một số lệnh timeout vẫn có thể đã thực thi, vì thế không lấy mỗi HTTP 500 làm bằng chứng rằng Redis chưa ghi.

---

## 20. Đo RTO thực tế trong diễn tập như thế nào?

RTO phải đo từ sự cố cho tới khi **chức năng được xác định là phục vụ lại**.

Một phép đo đầy đủ:

```text
T0  Redis primary không còn phục vụ đúng yêu cầu.
T1  Alert được phát.
T2  Nhóm vận hành/automation bắt đầu hành động.
T3  Redis primary mới hoặc instance restore hoạt động.
T4  Spring Boot kết nối lại và bắt đầu read/write được.
T5  Luồng nghiệp vụ mục tiêu hoạt động đúng và latency đạt ngưỡng.
T6  Xác minh khôi phục hoàn tất.

RTO quan sát = T6 - T0  (theo định nghĩa mục tiêu).
```

Có thể ghi riêng:

- **Detection time = T1 − T0**.
- **Response time = T2 − T1**.
- **Infrastructure recovery = T3 − T2**.
- **Application recovery = T5 − T3**.
- **Validation time = T6 − T5**.

Nếu 80% thời gian nằm ở phục hồi ứng dụng, việc tăng tốc Redis snapshot chưa chắc cải thiện RTO nhiều. Ngược lại, nếu nạp AOF 100 GB chiếm phần lớn thời gian, phải xem chi phí replay, capacity disk và kiến trúc warm standby.

### 20.1. Cache warmup có tính trong RTO không?

Tùy định nghĩa nghiệp vụ. Nếu API trả đúng dữ liệu nhưng latency tăng lên 10 giây trong 20 phút vì Redis trống, trong khi SLO latency là dưới 1 giây, thì nói “đã phục hồi” ngay khi Redis `PING` thành công là không chính xác.

Cần nêu rõ điều kiện kết thúc:

```text
Phục vụ lại 95% request trong latency mục tiêu,
không có lỗi dữ liệu nghiêm trọng,
các API quan trọng được xác minh,
tốc độ lỗi dưới ngưỡng đã thỏa thuận.
```

Nếu ứng dụng có thể phục vụ từ nguồn chính, có thể chọn khôi phục hoạt động cơ bản trước, rồi warmup cache dần; nhưng cần bảo vệ nguồn chính để tránh cache stampede.

---

## 21. Dự toán thời gian phục hồi và dung lượng dữ liệu

RTO có một giới hạn vật lý quan trọng: **dữ liệu càng lớn, khôi phục càng cần I/O và xử lý**.

Ví dụ có dataset cần tải 40 GiB từ backup. Giả sử thông lượng tải hiệu dụng trung bình là 200 MiB/giây, thời gian tải dữ liệu lý thuyết riêng bước truyền là:

\[
40 \times 1024 / 200 \approx 204{,}8\text{ giây}
\]

Đây mới là **ước tính cho bước truyền** trong điều kiện thông lượng giả định. RTO thực tế còn có:

- Thời gian chọn/tải metadata backup.
- Kiểm tra tính toàn vẹn và giải mã.
- Thời gian nạp/parse dữ liệu vào memory.
- Chi phí khởi động process, áp dụng cấu hình.
- Kết nối lại client.
- Kiểm tra và làm nóng cache.
- Độ trễ do giới hạn IOPS, CPU, network và source backup.

Vì vậy không thể cam kết RTO 2 phút cho dataset lớn chỉ dựa trên việc “đã có backup”. Cần đo tổng quy trình trên hạ tầng gần với production.

### 21.1. AOF lớn có thể ảnh hưởng RTO

AOF ghi log giúp bảo vệ những ghi gần nhất, nhưng quá trình restore có thể phải replay nhiều lệnh hoặc sử dụng cấu trúc AOF rewrite theo version Redis.

Một mục tiêu RPO chặt hơn có thể làm tăng chi phí I/O trong khi hoạt động hoặc khôi phục. Cần cân bằng giữa:

- Write latency bình thường.
- CPU/disk để tạo snapshot và rewrite.
- Dung lượng lưu trữ và backup.
- Tốc độ load state khi restart.
- Failover sang replica đang nóng so với cold restore.

**RPO thấp không tự động kéo theo RTO thấp**; cần thiết kế và đo cả hai.

---

## 22. Những lựa chọn kiến trúc cải thiện RTO

### 22.1. Replica sẵn sàng để failover

Một replica có trạng thái tương đối gần primary giúp hệ thống tránh phải đọc toàn bộ backup từ storage chậm khi một node chết. Khi failover phù hợp, RTO có thể giảm đáng kể.

Nhưng đây vẫn là replication bất đồng bộ, nên RPO có nguy cơ xấu hơn nếu replica thiếu những ghi mới nhất.

### 22.2. Tách failure domain

Đặt primary và replica ở các availability zone khác nhau giúp tránh việc một sự cố vật lý đơn lẻ làm mất cả hai.

Cần xem trade-off:

- Độ trễ mạng và chi phí truyền dữ liệu.
- Khả năng sự cố mạng tách cụm thành nhiều phía.
- Chính sách tự động promote replica.
- Bảo đảm chỉ primary hợp lệ nhận write.
- Vị trí backup ngoài phạm vi lỗi chung.

### 22.3. Backup có thể phục hồi và chạy diễn tập

Một bản backup ở xa có ý nghĩa khi có khả năng khôi phục thực tế. Cần thử thông lượng và thời gian tạo instance mới, nạp dataset và xác minh dữ liệu.

### 22.4. Cache có thể dựng lại

Nếu Redis là cache, xây dựng cơ chế cache-aside và kiểm soát tải nguồn chính có thể giúp API đạt RTO rất thấp ngay cả khi Redis chưa phục hồi đầy đủ.

Nhưng cache warmup không được làm database quá tải; cần bulkhead, concurrency limit hoặc preload các key quan trọng theo thứ tự ưu tiên.

### 22.5. Tách những workload có RPO/RTO khác nhau

Không nên luôn trộn:

```text
cache tạm có thể xóa bất kỳ lúc nào
+
stream sự kiện quan trọng
+
session chưa đồng bộ
```

trên một Redis instance mà áp dụng chung một policy persistence, eviction, backup và failover, trừ khi đã đánh giá và chấp nhận mọi trade-off.

Có thể tách Redis deployment/namespace theo mức độ quan trọng để:

- Tránh cache tạo áp lực bộ nhớ lên Stream nghiệp vụ.
- Cho phép cache dùng chính sách eviction phù hợp.
- Cho phép dữ liệu quan trọng có persistence/backup nghiêm ngặt hơn.
- Có runbook và mục tiêu phục hồi riêng.
- Giảm phạm vi tác động khi cấu hình hoặc vận hành sai.

---

## 23. Tránh nhầm eviction, TTL và mất dữ liệu do sự cố

Trong Redis, một key biến mất có thể vì nhiều nguyên nhân:

| Nguyên nhân | Tình huống | Đánh giá |
|---|---|---|
| TTL hết hạn | Session hết 30 phút theo policy | Vòng đời bình thường |
| Redis eviction | maxmemory-policy loại bỏ key | Có thể là bình thường với cache, nguy hiểm với state |
| `DEL` / `UNLINK` | Ứng dụng xóa chủ động | Có thể đúng hoặc lỗi nghiệp vụ |
| `FLUSHDB` / `FLUSHALL` | Xóa hàng loạt | Rủi ro vận hành |
| `XTRIM` | Stream bị giới hạn độ dài | Hành vi retention |
| Restore từ snapshot cũ | Thiếu những ghi mới hơn snapshot | Mất dữ liệu do RPO chưa đáp ứng |
| Failover sang replica chậm | Thiếu write chưa replicate | Mất dữ liệu theo replication gap |
| Lỗi serializer/schema | Key tồn tại nhưng app không đọc được | Vấn đề khả năng truy cập, không nhất thiết key bị mất |

Nếu đếm mọi key missing thành sự cố RPO, số liệu sẽ sai. Ngược lại, nếu gọi mọi mất key là “do TTL”, có thể che giấu lỗi độ bền.

Với Redis lưu dữ liệu nghiệp vụ cần giữ, chọn `maxmemory-policy` rất quan trọng. Cơ chế eviction tùy loại policy có thể xóa key trước TTL; điều đó có thể vi phạm yêu cầu dữ liệu nếu key không có bản sao. Những workload này cần capacity, chính sách memory và cảnh báo phù hợp.

---

## 24. RPO khi dùng Redis làm distributed lock hoặc idempotency store

Không phải mọi trạng thái quan trọng đều là data record truyền thống. Ví dụ Redis giữ:

- Distributed lock.
- Token chống xử lý trùng.
- Rate limit và quota tạm.
- Trạng thái giao dịch đang chạy.
- Cursor/checkpoint của worker.

### 24.1. Distributed lock

Nếu Redis mất lock state trong failover, hai worker có thể nghĩ mình được phép xử lý cùng tài nguyên tại những thời điểm chồng lấn.

Với thao tác quan trọng, nên có **fencing token** hoặc cơ chế kiểm tra tại nguồn ghi cuối cùng; không dựa duy nhất vào việc một key lock còn tồn tại trong Redis sau failover.

### 24.2. Idempotency token

Nếu API đã xử lý thanh toán và chỉ Redis lưu idempotency key, việc mất key sau crash có thể khiến cùng request được xử lý lại.

Đối với idempotency quan trọng, có thể cần lưu ID giao dịch duy nhất và trạng thái đã hoàn tất trong database bền vững với unique constraint, để Redis chỉ hỗ trợ tăng tốc đọc.

### 24.3. Rate limit

Mất bộ đếm Redis có thể làm quota reset và tạo cơ hội gửi thêm request. Với endpoint ít rủi ro có thể chấp nhận, nhưng với login/OTP cần đánh giá failover và cơ chế giới hạn thay thế.

### 24.4. Worker checkpoint

Mất checkpoint có thể dẫn đến đọc lại nhiều event hoặc bỏ sót nếu ứng dụng mặc định chuyển sang offset mới nhất. Checkpoint cần có chính sách lưu bền, retry và khôi phục phù hợp với nguồn sự kiện và tính idempotent.

**Điểm chung:** RPO cần được đánh giá theo **hậu quả mất state**, không chỉ theo kích thước key hoặc thời gian sống.

---

## 25. Giám sát các tín hiệu liên quan RPO/RTO

Một dashboard độ bền không chỉ hiển thị `Redis UP`. Nên theo dõi tối thiểu:

| Nhóm | Tín hiệu | Liên quan |
|---|---|---|
| Persistence | Thời điểm RDB save gần nhất, trạng thái save, AOF fsync/rewrite | RPO, nguy cơ mất ghi |
| Replication | Primary/replica role, trạng thái kết nối, lag/offset replication | RPO khi failover |
| Memory | Used memory, eviction, fragmentation, số key | Mất key ngoài ý muốn và capacity |
| Disk | Dung lượng còn lại, IOPS, latency, lỗi ghi | RPO và thời gian restart |
| Backup | Thời điểm backup thành công, tuổi backup, kết quả sao chép ngoại vi | Khả năng restore |
| Restore drill | Thời gian tải backup, load data, xác minh ứng dụng | RTO thực tế |
| Redis client | Timeout, reconnect, lỗi command, pool saturation | RTO ứng dụng |
| API | Error rate, latency, fallback, cache stampede | RTO nghiệp vụ |
| Streams | Pending, consumer lag, trim/retention, event replay | Mất hoặc trùng sự kiện |
| Operations | MTTD, thời gian failover, số lần diễn tập | Khả năng đáp ứng RTO |

### 25.1. Cảnh báo nên bám vào mục tiêu

Ví dụ nếu RPO mục tiêu cho một chức năng là 60 giây, việc replication lag tăng bất thường hoặc nhiều lần AOF fsync lỗi phải được coi là tín hiệu rủi ro, kể cả khi Redis vẫn trả lời PING.

Nếu backup bắt buộc có mỗi 15 phút nhưng bản thành công gần nhất cách đây 3 giờ, dashboard không thể chỉ hiển thị “Backup job đang chạy” là đủ.

### 25.2. Kiểm tra chất lượng giám sát

Một alert tốt cần dẫn tới hành động rõ:

- Ai nhận alert?
- Ngưỡng nào là warning, ngưỡng nào là incident?
- Có bỏ qua khi Redis đang restart theo kế hoạch không?
- Cần thực hiện lệnh kiểm tra nào mà không gây tác động phá hủy?
- Khi nào phải khóa chức năng ghi quan trọng?
- Có quy trình thông báo khách hàng và trạng thái dịch vụ không?

Giám sát không thay thế diễn tập; nhưng diễn tập không có giám sát cũng khó phát hiện sự cố thật sớm để đạt RTO.

---

## 26. Mẫu tài liệu RPO/RTO cho một Redis workload

Một bản ghi quyết định có thể viết như sau:

```yaml
workload: cart-session-store
owner: checkout-team
redisRole: primary-temporary-state
sourceOfTruth: redis-with-periodic-database-sync
businessImpact:
  dataLoss: "Nguoi dung co the mat thay doi gio hang chua dong bo"
  downtime: "Khong the xem/sua gio hang"
objectives:
  rpo: "60s"
  rto: "10m"
failureScenarios:
  - process-crash
  - primary-node-loss
  - zone-loss
persistence:
  rdb: enabled
  aof: enabled
  appendfsync: everysec
availability:
  replication: enabled
  failover: automatic
backup:
  offNode: required
  restoreTest: quarterly
applicationBehavior:
  whenRedisUnavailable: "Display temporary error / use safe fallback"
  retryPolicy: "Bounded retry with backoff"
verification:
  dataProbe: "Compare acknowledged-write IDs with restored IDs"
  serviceReady: "Cart reads/writes and latency target verified"
openRisks:
  - "Async replica can miss latest acknowledged write"
  - "Backup restore alone may exceed 10-minute RTO"
```

**Đây là tài liệu mẫu, không phải cấu hình có thể nạp trực tiếp vào Redis hay bằng chứng mục tiêu đã đạt.** Các trường `rpo`, `rto` và `appendfsync` phải được chứng minh bằng thử nghiệm theo topology thực tế.

Đối với một workload chỉ là cache, trường `sourceOfTruth` nên trỏ tới database/API chuẩn, còn RPO của nội dung cache có thể ghi “không yêu cầu giữ”.

### Điều kiện chấp nhận trước production

Bên sở hữu nghiệp vụ nên xác nhận:

- RPO/RTO là mục tiêu chính thức.
- Có mô tả cụ thể failure mode mà mục tiêu bao phủ.
- Có người chịu trách nhiệm triển khai và vận hành.
- Có dữ liệu diễn tập hoặc bằng chứng đánh giá.
- Có giới hạn/rủi ro còn tồn tại được chấp nhận.
- Có lịch kiểm tra định kỳ và cập nhật sau thay đổi cấu hình.

---

## 27. Tình huống phân tích

### Tình huống A — Cache sản phẩm mất sạch

Redis cache sản phẩm mất mọi key, nhưng PostgreSQL vẫn đầy đủ và API đọc từ PostgreSQL khi cache miss.

**Phân tích:** dữ liệu sản phẩm không bị mất. RPO của **cache** không phải vấn đề lớn, nhưng RTO của chức năng đọc và nguy cơ quá tải PostgreSQL sau cache cold start phải được kiểm soát. Có thể dùng preload hoặc warmup có giới hạn.

### Tình huống B — AOF everysec nhưng primary và replica cùng mất

Ứng dụng bật AOF `everysec` và một replica cùng zone. Một sự cố toàn zone làm mất cả hai node; backup xa nhất được tạo 20 phút trước.

**Phân tích:** không được coi RPO disaster là 1 giây. Với failure mode mất zone, nguồn khôi phục thực tế là backup ngoài zone, và lượng dữ liệu có nguy cơ mất phụ thuộc tuổi/độ tin cậy của backup đó.

### Tình huống C — Failover chỉ mất 20 giây nhưng Redis thiếu ghi cuối

Primary trả OK cho một event `XADD`, chết trước khi replica nhận lệnh. Replica được promote trong 20 giây nhưng thiếu event.

**Phân tích:** RTO có thể rất tốt, trong khi RPO không đạt nếu event đó không được phép mất. Cần thiết kế giảm mất ghi, replay/đối soát hoặc nguồn sự thật bền vững hơn.

### Tình huống D — AOF đầy đủ nhưng restore rất lâu

AOF và backup còn đủ dữ liệu, không mất write theo kiểm thử. Tuy nhiên Redis cần 45 phút để nạp dataset, trong khi RTO nghiệp vụ là 10 phút.

**Phân tích:** RPO đạt nhưng RTO không đạt. Cần xem warm standby, tốc độ restore, kích thước dataset, persistence rewrite và khả năng fallback của ứng dụng.

### Tình huống E — Replica bắt kịp nhưng dữ liệu bị xóa nhầm

Operator chạy `FLUSHDB` trên primary, lệnh xóa được replicate sang replica.

**Phân tích:** replication phản ánh sự thay đổi hợp lệ về mặt Redis, kể cả thay đổi sai về nghiệp vụ. Muốn quay về dữ liệu cũ cần backup/restore hoặc nguồn chuẩn khác.

### Tình huống F — Redis UP nhưng checkout vẫn lỗi

Redis đã được promote, nhưng Spring Boot giữ endpoint cũ hoặc timeout do kết nối chưa khôi phục. API checkout vẫn trả 503.

**Phân tích:** RTO nghiệp vụ chưa kết thúc. Phải tính cả thời gian client reconnect và xác minh nghiệp vụ, không dừng đồng hồ khi Redis process trả PING.

### Tình huống G — Giỏ hàng tự hết TTL sau khi restore

Bản backup có nhiều key giỏ hàng còn TTL khi snapshot được chụp. Sau khi restore, một số key đã hết thời hạn hiệu lực.

**Phân tích:** cần phân biệt key hết hạn theo quy tắc với key bị mất vì backup quá cũ. Khôi phục không nên tự gia hạn những giỏ hàng hoặc session đã hết hạn bảo mật chỉ để có nhiều key hơn.

### Tình huống H — Ứng dụng retry lệnh ghi sau timeout

Client gửi `INCR`, không nhận phản hồi do network lỗi, rồi retry. Sau khi khôi phục, bộ đếm đã tăng hai lần.

**Phân tích:** độ bền lưu trữ không tự giải quyết idempotency mạng. Cần thiết kế theo request ID, thao tác có điều kiện hoặc cơ chế đối soát phù hợp.

### Tình huống I — Redis Stream giữ dữ liệu nhưng consumer bị trễ

Redis không mất record, nhưng consumer chỉ xử lý được 50 event/s trong khi producer ghi 500 event/s. Sau khi restart, backlog cần nhiều giờ để xử lý.

**Phân tích:** đây là vấn đề **thời gian khôi phục năng lực nghiệp vụ** và capacity xử lý, dù persistence đã bảo vệ dữ liệu. RTO cần tính thời gian tiêu thụ backlog nếu quy trình nghiệp vụ chưa hoạt động bình thường cho tới khi bắt kịp.

---

## 28. Sai lầm thường gặp và cách khắc phục

| Sai lầm | Vì sao sai | Hướng xử lý |
|---|---|---|
| “Bật AOF everysec là RPO chắc chắn 1 giây” | Fsync và failure mode không có bảo đảm tuyệt đối như vậy | Xác định tình huống, đo và nêu giới hạn |
| “Có replica là không mất ghi” | Replication thường bất đồng bộ | Đo lag, xem các cơ chế đợi xác nhận, replay |
| “Sentinel/Cluster bảo đảm RPO 0” | Failover nhanh không bảo đảm mọi write mới đã replicate | Đánh giá RPO độc lập với RTO |
| “Có backup là RTO ngắn” | Restore dataset lớn có thể mất rất lâu | Diễn tập restore end-to-end |
| “RDB snapshot mỗi 60 giây là backup xa nhất 60 giây” | Snapshot có thể lỗi/trễ hoặc chưa chuyển ra nơi an toàn | Giám sát backup thành công và tuổi backup |
| “Replica thay thế backup” | Lỗi logic/xóa nhầm có thể replicate | Lưu backup có version ngoài failure domain |
| “PING thành công là đã phục hồi” | Ứng dụng có thể chưa đọc/ghi, latency cao hoặc dữ liệu thiếu | Xác minh luồng nghiệp vụ và latency |
| “Cache mất cũng là mất dữ liệu doanh nghiệp” | Cache có thể tái tạo từ nguồn chuẩn | Phân loại source of truth |
| “Redis chỉ là cache nên không cần RTO” | Cache mất có thể làm DB quá tải và API ngừng | Đặt RTO cho chức năng, không chỉ node |
| “TTL là sao lưu” | TTL là thời hạn xóa tự nhiên | Tách lifecycle với persistence/backup |
| “Giữ Redis phục hồi bằng cách bỏ qua mọi lỗi” | Có thể vi phạm quyền, tài chính, idempotency | Fail-open/closed theo nghiệp vụ |
| “WAIT chắc chắn đã fsync toàn bộ replica” | WAIT xác nhận replication, không phải bảo đảm disk | Hiểu semantics và giới hạn |
| “min-replicas-to-write là synchronous replication” | Chỉ hạn chế ghi dựa trên trạng thái replica | Không hứa mỗi write đã ack trên replica |
| “RTO không tính thời gian phát hiện” | Người dùng đã bị ảnh hưởng trước khi có alert | Đo từ sự cố tới khi phục hồi nghiệp vụ |
| “Một lần diễn tập thành công là đủ” | Tải, size, topology và failure mode thay đổi | Diễn tập định kỳ và sau thay đổi lớn |
| “Lỗi timeout tức là lệnh chưa thực hiện” | Redis có thể đã xử lý trước khi kết nối đứt | Idempotency và đối soát |
| “RPO=0 có thể đạt chỉ bằng cấu hình Redis server” | Còn disk, replication, failover, ứng dụng, vùng lỗi | Thiết kế toàn hệ thống và nguồn chuẩn |

---

## 29. Quy trình 10 bước để lập mục tiêu và xác minh

Một nhóm phát triển Spring Data Redis có thể làm theo quy trình:

1. **Liệt kê workload trên Redis.** Cache, session, cart, stream, lock, rate limiter, state nghiệp vụ.
2. **Xác định source of truth.** Đánh dấu dữ liệu nào có thể tái tạo, dữ liệu nào mất sẽ gây thiệt hại.
3. **Ước lượng tác động.** Nếu mất 1 giây/1 phút/1 giờ dữ liệu thì hậu quả gì? Nếu ngừng 1 phút/10 phút/1 giờ thì sao?
4. **Đặt RPO và RTO có owner.** Dùng số đo được và định nghĩa rõ thời điểm bắt đầu/kết thúc.
5. **Chọn failure model.** Process crash, disk loss, node loss, zone loss, thao tác sai, mất region.
6. **Thiết kế cơ chế bảo vệ.** RDB, AOF, replication, failover, backup, tách vùng lỗi, replay.
7. **Thiết kế ứng dụng.** Timeout, reconnect, retry/idempotency, cache fallback, Stream checkpoint, fail-open/closed.
8. **Viết runbook.** Nguồn backup, quy trình promote/restore, secret, chủ sở hữu, kiểm tra sau khôi phục.
9. **Diễn tập và đo.** Dùng probe đã ghi nhận xác nhận để ước tính lost writes; đo tới khi nghiệp vụ ổn định.
10. **Theo dõi và cập nhật.** Đặt cảnh báo, diễn tập lại khi dữ liệu tăng, Redis upgrade, topology đổi hoặc traffic thay đổi.

Sau mỗi diễn tập, lưu lại:

```text
Ngày diễn tập:
Workload và phiên bản Redis:
Failure mode:
Dung lượng và tốc độ ghi:
Điểm ghi cuối đã xác nhận:
Điểm ghi mới nhất phục hồi:
RPO đo được:
Mốc bắt đầu outage:
Mốc nghiệp vụ phục vụ lại:
RTO đo được:
Hành động thủ công:
Rủi ro chưa xử lý:
Người phê duyệt:
```

Các trường này giúp biến RPO/RTO từ khẩu hiệu kiến trúc thành quyết định có bằng chứng.

---

## 30. Tổng kết

Trong Spring Data Redis, **RPO** trả lời câu hỏi *có thể mất tối đa bao nhiêu dữ liệu gần nhất*, còn **RTO** trả lời câu hỏi *có thể mất tối đa bao lâu để khôi phục chức năng*. Hai mục tiêu cần được chọn theo tác động nghiệp vụ và kiểm chứng theo từng kịch bản sự cố.

- **RDB** bảo vệ bằng snapshot; RPO phụ thuộc khoảng và độ tin cậy của điểm snapshot thực sự khôi phục được.
- **AOF** giúp giảm cửa sổ mất ghi trong một số kiểu sự cố; `appendfsync always/everysec/no` là các lựa chọn độ bền/hiệu năng, không phải cam kết RPO tuyệt đối.
- **Replication, Sentinel, Cluster** cải thiện khả năng tiếp tục phục vụ, nhưng replication bất đồng bộ có thể mất những ghi mới nhất khi failover.
- **Backup ngoài failure domain** cần cho lỗi disk, zone và xóa dữ liệu ngoài ý muốn; chỉ bản backup đã được thử restore mới tạo cơ sở tin cậy.
- **Spring Data Redis client** phải reconnect, xử lý timeout/retry/idempotency và phục hồi các luồng xử lý, nếu không RTO ứng dụng có thể dài hơn RTO Redis server.
- **Redis chỉ là cache** có thể chấp nhận mất toàn bộ key; **Redis giữ trạng thái nghiệp vụ duy nhất** thường cần mục tiêu và cơ chế bảo vệ nghiêm ngặt hơn.
- **RPO/RTO đạt được** phải được đo bằng diễn tập, quan sát dữ liệu đã xác nhận, thời gian phục hồi từ đầu tới cuối và tiêu chí phục vụ nghiệp vụ.

Một phương án đáng tin cậy không phải phương án có nhiều cờ Redis nhất, mà là phương án **có mục tiêu đã được nghiệp vụ chấp nhận, biết rõ giới hạn và chứng minh được khả năng khôi phục trong điều kiện thực tế**.

### Tài liệu tham khảo

- [Redis — Persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/)
- [Redis — Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/)
- [Redis — High Availability with Sentinel](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/)
- [Redis — Redis Cluster](https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/)
- [Redis — WAIT](https://redis.io/docs/latest/commands/wait/)
- [Redis — WAITAOF](https://redis.io/docs/latest/commands/waitaof/)
- [Redis — CONFIG SET](https://redis.io/docs/latest/commands/config-set/)
- [Redis — INFO](https://redis.io/docs/latest/commands/info/)
- [Redis — BGSAVE](https://redis.io/docs/latest/commands/bgsave/)
- [Spring Data Redis — Reference Documentation](https://docs.spring.io/spring-data/redis/reference/)
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
