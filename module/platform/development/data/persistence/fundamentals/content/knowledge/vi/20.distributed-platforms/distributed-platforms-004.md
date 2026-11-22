# Nhân bản đồng bộ và bất đồng bộ

Một hệ thống bán hàng dùng PostgreSQL primary để ghi và một standby để dự phòng. Khách hàng tạo đơn, API trả **“Thành công”**, rồi primary hỏng. Nếu standby chưa nhận được thay đổi cuối cùng nhưng được nâng thành primary mới, đơn hàng có thể biến mất khỏi hệ thống đang phục vụ. Trái lại, nếu bắt mọi giao dịch đợi standby xác nhận trước khi trả kết quả, độ trễ và khả năng ghi khi standby gặp sự cố có thể thay đổi đáng kể.

Đó là sự đánh đổi trung tâm giữa **nhân bản đồng bộ (synchronous replication)** và **nhân bản bất đồng bộ (asynchronous replication)**: **thời điểm nào hệ thống được phép xác nhận một thao tác ghi**, bản sao đã đạt trạng thái nào ở thời điểm đó, và sẽ làm gì khi các nút hoặc đường truyền gặp lỗi.

Bài thuộc chương **Nền tảng phân tán** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Người học đang thiết kế persistence cho ứng dụng Java, từ lược đồ, truy vấn và chỉ mục đến giao dịch, cô lập, kiểm soát đồng thời, độ bền, lỗi kết nối, sao lưu và tối ưu hiệu năng. Các ví dụ dùng **PostgreSQL physical streaming replication, JDBC và Spring** làm điểm tựa. Thuật ngữ “đồng bộ” trong tài liệu của các cơ sở dữ liệu khác có thể chỉ một điều kiện xác nhận khác; luôn kiểm tra cơ chế thực tế thay vì suy ra chỉ từ tên chế độ.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích quan hệ giữa **primary/leader, standby/replica, WAL, commit acknowledgement** và khả năng khôi phục.
- Mô tả đúng luồng **ghi bất đồng bộ** và **ghi đồng bộ**, bao gồm mức **receive/write, flush, replay/apply** của bản sao.
- Phân biệt **độ bền commit trên primary**, **độ bền trên standby**, **khả năng nhìn thấy khi đọc standby** và **độ bền sau failover**.
- Phân tích tác động của replication lag tới **read-your-writes**, **RPO** và **RTO**.
- Hiểu các lựa chọn trong PostgreSQL: **synchronous_standby_names**, **synchronous_commit**, replication slot và các chỉ số LSN.
- Thiết kế đường đọc/ghi trong Java theo yêu cầu nghiệp vụ, có timeout, fallback, idempotency và quan sát được.
- Nhận diện các rủi ro như failover chọn sai replica, split-brain, nghẽn WAL, nhân bản lỗi xóa dữ liệu và nhầm replication với backup.

## 2. Nhân bản dữ liệu là gì, phục vụ mục tiêu nào?

**Replication** duy trì một hoặc nhiều bản sao của dữ liệu/chuỗi thay đổi tại những nút khác nhau. Các mục tiêu phổ biến:

1. **Tính sẵn sàng:** có standby để tiếp quản khi primary không thể phục vụ.
2. **Phân tải đọc:** những truy vấn có thể chấp nhận dữ liệu trễ đọc từ replica.
3. **Phân vùng lỗi:** đặt bản sao trên máy, khu vực sẵn sàng hoặc vùng địa lý khác nhau.
4. **Khả năng bảo trì:** nâng cấp, chuyển đổi hoặc kiểm thử một số kịch bản mà không bắt mọi ứng dụng dừng dài.
5. **Phục hồi:** hỗ trợ một số chiến lược khôi phục hoặc xây dựng bản sao, nhưng không thay thế backup độc lập.

Kiến trúc primary–standby cơ bản:

~~~text
               +-----------------------+
Java writers ->| PRIMARY / LEADER      |
               | INSERT/UPDATE/DELETE  |
               | WAL, COMMIT           |
               +-----------+-----------+
                           |
                  Replication stream
                           |
              +------------+-------------+
              |                          |
              v                          v
      +---------------+          +---------------+
      | STANDBY A     |          | STANDBY B     |
      | nhận/ghi WAL  |          | nhận/ghi WAL  |
      | replay dữ liệu|          | replay dữ liệu|
      +---------------+          +---------------+
              |                          |
         đọc tùy hợp đồng           ứng viên failover
~~~

**Primary–standby không đồng nghĩa mọi bản sao đều có thể ghi.** Trong mô hình PostgreSQL physical streaming replication thông thường, application ghi trên primary; hot standby có thể phục vụ một số truy vấn đọc nếu được cấu hình cho phép. Kiến trúc multi-primary là một bài toán khác, cần cơ chế giải quyết xung đột và thứ tự ghi riêng.

## 3. Hai câu hỏi khác nhau: “đã commit” và “bản sao đã bắt kịp chưa?”

Giả sử transaction T1 chuyển trạng thái đơn hàng từ **PENDING** thành **PAID**.

~~~text
Thời gian -->

Primary: UPDATE --> COMMIT --> trả 200 OK
                     |
Standby:       nhận WAL ----> flush WAL ----> replay WAL
~~~

Các cột mốc này không nhất thiết diễn ra cùng lúc:

- **COMMIT trên primary:** transaction đã đạt điều kiện xác nhận cục bộ và điều kiện replication nào được cấu hình.
- **Standby receive/write:** standby nhận được một phần WAL và có thể đã ghi tới bộ đệm của hệ điều hành.
- **Standby flush:** WAL đã được đồng bộ xuống lưu trữ của standby theo bảo đảm hệ thống.
- **Standby replay/apply:** thay đổi từ WAL được áp dụng tới trạng thái mà một truy vấn đọc mới trên standby có thể quan sát.

Một bản sao **đã nhận WAL nhưng chưa replay** có thể vẫn đọc ra trạng thái cũ. Ngược lại, commit đã bền vững trên primary không mặc định có bản sao bền vững ở nơi khác. Bốn sự kiện trên phải được phân biệt trong thiết kế và khi chẩn đoán.

## 4. Nhân bản bất đồng bộ: commit không chờ standby bắt kịp

Trong nhân bản **bất đồng bộ**, đường ghi thường được xác nhận trên primary theo bảo đảm cục bộ **mà không đợi standby xác nhận đã nhận/flush/replay transaction đó**.

~~~text
Client               Primary                    Standby
  |                     |                          |
  |--- UPDATE --------->|                          |
  |--- COMMIT --------->|                          |
  |                     | WAL local flush          |
  |<-- thành công ------|                          |
  |                     |--- gửi WAL ------------->|
  |                     |                          | write/flush
  |                     |                          | replay
~~~

Sơ đồ giả định primary có cơ chế local commit bền vững phù hợp, chẳng hạn PostgreSQL với **fsync** và chính sách đồng bộ local thông thường. Nhân bản bất đồng bộ **không có nghĩa primary cố ý bỏ qua WAL local**.

### Ưu điểm

- Thời gian trả COMMIT ít phụ thuộc trực tiếp vào round-trip tới standby ở vùng khác.
- Một standby tạm mất kết nối không nhất thiết làm các giao dịch mới trên primary phải chờ standby đó.
- Thích hợp cho read replicas, phân tải đọc và nhiều hệ thống có thể chấp nhận khoảng mất dữ liệu khi chuyển primary trong sự cố nghiêm trọng.

### Nhược điểm

- Có **cửa sổ mất dữ liệu** nếu primary không thể phục hồi và hệ thống failover sang bản sao chưa nhận đủ các transaction đã được primary xác nhận.
- Truy vấn trên standby có thể trả dữ liệu cũ: **replication lag**.
- Nếu có nhiều standby, tiến độ giữa chúng có thể khác nhau; đọc luân phiên dễ gây “đọc lùi thời gian”.
- Khi standby chậm lâu, việc giữ WAL cho nó có thể tạo áp lực dung lượng trên primary, tùy thiết kế slot/archiving.

**Chú ý:** bất đồng bộ không đồng nghĩa *chắc chắn* mất dữ liệu mỗi lần primary hỏng. Nếu standby đã replay/flush đầy đủ transaction cần thiết, nó vẫn có thể giữ toàn bộ thay đổi. Vấn đề là **không có cam kết từ phía primary rằng standby đã đạt mốc đó tại thời điểm COMMIT trả thành công**.

## 5. Nhân bản đồng bộ: cam kết dựa vào phản hồi từ bản sao

Trong nhân bản **đồng bộ**, primary chờ điều kiện được cấu hình từ một hoặc nhiều standby trước khi trả kết quả COMMIT.

~~~text
Client               Primary                      Standby
  |                     |                            |
  |--- UPDATE --------->| WAL local                   |
  |--- COMMIT --------->|--- gửi WAL ---------------->|
  |                     |                            | ghi/flush hoặc replay
  |                     |<-- xác nhận mức yêu cầu ----|
  |<-- COMMIT OK -------|                            |
~~~

Điểm quan trọng là **“đồng bộ đến mức nào?”**. Một hệ quản trị có thể cho phép:

- Đợi standby **ghi WAL vào cache hệ điều hành**.
- Đợi standby **flush WAL bền vững**.
- Đợi standby **apply/replay** để truy vấn đọc phù hợp trên standby có thể thấy kết quả.

Các mức này có chi phí và ý nghĩa khác nhau. Đồng bộ không mặc nhiên có nghĩa mọi standby đã áp dụng dữ liệu, hay mọi bản sao ở mọi khu vực đều đồng nhất tại chính thời điểm client nhận phản hồi.

### Ưu điểm

- Có thể giảm cửa sổ mất những giao dịch **đã được xác nhận** trong một số kịch bản hỏng primary và chuyển sang standby đã xác nhận chúng.
- Tạo cơ sở rõ hơn cho chính sách RPO nghiêm ngặt nếu hạ tầng, cơ chế chọn standby và failover được thiết kế phù hợp.
- Ở mức chờ apply/replay, có thể hỗ trợ nhu cầu đọc thay đổi từ standby ngay sau commit trong các điều kiện xác định.

### Nhược điểm

- Độ trễ COMMIT có thêm chi phí truyền mạng, xử lý WAL và phản hồi từ standby.
- Khi các standby bắt buộc không sẵn sàng, transaction có thể **bị treo chờ xác nhận**, ảnh hưởng khả năng ghi.
- Sự cố mạng hoặc cross-region latency có thể kéo dài thời gian giữ transaction và tài nguyên.
- Nếu vận hành cho phép hạ mức đồng bộ để tiếp tục phục vụ, phải đánh giá lại bảo đảm độ bền và cửa sổ mất dữ liệu.

**Đồng bộ không tự bảo đảm không bao giờ mất dữ liệu.** Một quy trình failover chọn standby không đủ mới, mất đồng thời cả miền lỗi hoặc cấu hình lưu trữ không thực hiện đúng flush vẫn có thể phá hỏng mục tiêu.

## 6. So sánh nhanh hai chiến lược

| Khía cạnh | Bất đồng bộ | Đồng bộ |
| --- | --- | --- |
| Điều kiện trả COMMIT | Không chờ standby xác nhận thay đổi đó | Đợi đủ standby đạt mức xác nhận được cấu hình |
| Độ trễ ghi | Ít phụ thuộc trực tiếp vào độ trễ standby | Có thể tăng theo mạng, WAL write/flush/replay |
| Khi standby chậm/mất kết nối | Primary thường vẫn tiếp tục ghi nếu còn đủ tài nguyên | Commit có thể phải chờ nếu không đủ standby đồng bộ |
| Rủi ro failover sang standby thiếu dữ liệu | Có thể mất các ghi đã được xác nhận trên primary | Giảm theo mức bền vững đã chờ và cách chọn standby |
| Đọc từ standby ngay sau commit | Không mặc định thấy ghi vừa xong | Chỉ có thể dựa vào mức chờ **apply** hoặc fence cụ thể |
| Phù hợp điển hình | Phân tải đọc, hệ có RPO khác 0, WAN có độ trễ lớn | Ghi quan trọng, RPO rất thấp trong phạm vi lỗi đã phân tích |
| Chi phí vận hành | Cần đo lag và xử lý dữ liệu mới nhất | Cần quản lý tập standby đồng bộ, timeout và failover chính xác |

Từ **“phù hợp”** trong bảng không phải lời khuyên rằng mọi nghiệp vụ quan trọng phải bật đồng bộ. Quyết định còn phụ thuộc quy mô, xác suất sự cố, khả năng phục hồi, loại giao dịch, SLO, địa lý và chi phí.

## 7. PostgreSQL: physical streaming replication và WAL

PostgreSQL ghi thông tin phục hồi vào **Write-Ahead Log (WAL)**. Với physical streaming replication, một standby có thể nhận dòng WAL từ primary, lưu trữ và replay nó để xây dựng trạng thái vật lý tương ứng.

~~~text
PostgreSQL primary
  SQL transaction
        |
      WAL records
        |
  WAL sender (walsender) ----------------+
                                        |
                                        v
                                 Standby WAL receiver
                                        |
                                 nhận / ghi / flush WAL
                                        |
                                 Startup/replay process
                                        |
                                 data pages trên standby
~~~

Trong mô hình này:

- Primary là điểm nhận cập nhật ứng dụng.
- Standby cần cấu hình kết nối replication, quyền phù hợp và phương án khởi tạo trạng thái ban đầu (thường từ base backup thích hợp).
- Dòng WAL có thứ tự LSN, nhưng **đã gửi**, **đã ghi**, **đã flush**, **đã replay** là các mức tiến độ khác nhau.
- Hot standby có thể phục vụ SELECT khi được cấu hình phù hợp; SELECT còn chịu ảnh hưởng snapshot, xung đột recovery và tiến độ replay.
- Phục hồi sau crash cục bộ, physical replication và PITR đều sử dụng WAL theo các cách khác nhau; mục tiêu không đồng nhất.

Đây là mô hình khái niệm; thiết lập một cụm production còn đòi hỏi quản lý phiên bản PostgreSQL, backup, bảo mật kết nối, tường lửa, quyền replication, slot, archive, giám sát và quy trình chuyển vai trò.

## 8. PostgreSQL synchronous_commit: chính xác đang chờ điều gì?

PostgreSQL có tham số **synchronous_commit**. Ý nghĩa liên quan đến replication phụ thuộc cả **synchronous_standby_names** và tình trạng standby đủ điều kiện.

| Giá trị | Ý nghĩa khái quát với transaction commit thông thường |
| --- | --- |
| **off** | Có thể trả kết quả trước khi WAL commit được flush cục bộ; crash có thể làm mất một số commit vừa xác nhận |
| **local** | Chờ WAL commit được flush cục bộ, **không đợi standby đồng bộ** |
| **remote_write** | Khi có standby đồng bộ được cấu hình, chờ standby xác nhận WAL đã được viết tới hệ điều hành, **chưa nhất thiết flush bền vững ở standby** |
| **on** | Chờ flush WAL cục bộ; khi có standby đồng bộ được cấu hình, còn chờ standby **flush** WAL theo điều kiện đồng bộ |
| **remote_apply** | Khi có standby đồng bộ được cấu hình, chờ xác nhận WAL được **replay/apply** trên standby đủ điều kiện, ngoài các điều kiện trước đó |

Trong cấu hình primary không có standby đồng bộ bắt buộc, các mức liên quan standby không tự tạo ra một cơ chế “chờ replica” chỉ nhờ tên giá trị. **synchronous_standby_names** mới quyết định yêu cầu xác nhận từ standby.

### 8.1. Synchronous_standby_names chọn standby nào?

Ví dụ cấu hình minh họa trên primary:

~~~conf
# Ví dụ minh họa, không phải cấu hình production đầy đủ.
wal_level = replica
max_wal_senders = 10

# Ưu tiên standby_a; có thể chọn standby_b khi thích hợp.
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
synchronous_commit = on
~~~

Ý nghĩa: primary chọn **một standby đồng bộ** theo chính sách ưu tiên (priority) trong danh sách, và ở mức **on** chờ WAL được flush ở standby được chọn trước khi báo commit thành công.

Tên **standby_a/standby_b** là giá trị **application_name** mà standby khai báo trong kết nối replication, không phải tên DNS tự suy từ hostname. Có thể chọn dạng quorum, ví dụ:

~~~conf
# Cần đủ hai standby bất kỳ trong danh sách xác nhận.
synchronous_standby_names = 'ANY 2 (standby_a, standby_b, standby_c)'
~~~

**FIRST** và **ANY** giải quyết yêu cầu xác nhận khác nhau: ưu tiên một số standby theo thứ tự hoặc đợi một quorum về số lượng. Chọn hai standby không tự biến hệ thống thành consensus database hay giải quyết tự động mọi nhánh split-brain.

### 8.2. Điều gì xảy ra nếu standby bắt buộc biến mất?

Nếu primary vẫn hoạt động nhưng không còn đủ standby đồng bộ, transaction có thể **chờ vô thời hạn từ góc nhìn ứng dụng nếu không có cơ chế timeout/cancel hoặc thay đổi cấu hình phù hợp**.

Cần thiết kế:

1. Giới hạn thời gian ở ứng dụng/transaction và cách báo lỗi cho caller.
2. Phương án vận hành khi standby đồng bộ không khả dụng: sửa cụm, thay standby, thay quorum hoặc chấp nhận giảm độ bền có kiểm soát.
3. Cơ chế nhận biết một COMMIT bị timeout nhưng **đã có thể hoàn tất** trên server; không tự retry thao tác không lũy đẳng.
4. Metrics đo commit latency, standby sync state và wait events.

Giảm yêu cầu đồng bộ để tiếp tục nhận ghi có thể làm thay đổi RPO. Đây phải là **quyết định chính sách**, không phải phản ứng tự động không được ghi nhận.

## 9. Receive, write, flush, replay và đọc dữ liệu

Giả sử transaction T1 có commit WAL record tại LSN giả lập **F**. Có các mốc:

~~~text
Primary flush_lsn >= F
        |
        v
Standby received / written_lsn >= F
        |
        v
Standby flush_lsn >= F
        |
        v
Standby replay_lsn >= F
        |
        v
Một truy vấn mới với snapshot thích hợp có thể thấy T1 trên standby
~~~

Những giá trị ở sơ đồ là **vị trí tiến độ**, không phải mỗi bước luôn diễn ra theo nhịp đều đặn. Hệ quản trị có thể gom nhiều WAL record và xử lý chúng theo đợt.

Trong PostgreSQL:

- **remote_write** không đồng nghĩa WAL bền vững trên standby nếu hệ điều hành standby crash trước khi flush.
- **on** cùng synchronous standby phù hợp yêu cầu standby flush nhưng **không mặc định chờ replay**; ngay sau commit, truy vấn standby có thể vẫn đọc bản cũ.
- **remote_apply** chờ standby được chọn replay tới commit tương ứng; một truy vấn mới trên standby phù hợp thường có thể nhìn thấy thay đổi, nhưng snapshot đọc đã được thiết lập sớm vẫn có thể cũ.
- Nếu còn cache/query projection ngoài PostgreSQL, standby replay không chứng minh cache đã được invalidated.

Vì vậy **synchronous replication** và **read-your-writes trên mọi đường đọc** là hai yêu cầu liên quan nhưng không giống nhau.

## 10. Đọc sau ghi: replication lag ảnh hưởng ứng dụng Java ra sao?

Giả sử API đổi địa chỉ:

~~~text
PUT /profiles/501
   -> ghi primary
   -> COMMIT
   -> trả 200 OK

GET /profiles/501
   -> routing chọn standby
   -> standby chưa replay thay đổi
   -> trả địa chỉ cũ
~~~

Đây là một vi phạm **read-your-writes (RYW)** nếu API đã hứa “lưu xong đọc lại sẽ thấy”. Nhân bản bất đồng bộ cho phép điều này; nhân bản đồng bộ ở mức **flush** cũng không tự loại bỏ hoàn toàn cửa sổ chưa replay.

Ba cách xử lý phổ biến:

1. **Đọc primary sau ghi** bằng request hoặc transaction mới có snapshot phù hợp. Đây thường là lựa chọn dễ kiểm chứng nhất.
2. **Đọc replica với version/watermark:** chỉ trả dữ liệu nếu replica đã đạt mức mới tối thiểu của yêu cầu.
3. **Chờ có deadline, sau đó fallback primary** nếu replica chưa bắt kịp; tuyệt đối không chờ mãi trong HTTP request.

Một time window như “trong 3 giây sau ghi thì đọc primary” có thể thực dụng, nhưng **không chứng minh replica đã bắt kịp** khi hết 3 giây. Muốn bảo đảm nghiêm ngặt, cần version/LSN fence hoặc chính sách chỉ đọc primary cho thao tác nhạy cảm.

## 11. PostgreSQL: kiểm tra vị trí WAL bằng LSN

**LSN (Log Sequence Number)** cho biết vị trí trong dòng WAL. Nó cho phép so sánh tiến độ trên những thành phần thuộc **cùng lịch sử WAL phù hợp**.

Sau khi transaction ghi đã **COMMIT thành công**, ứng dụng có thể lấy một mốc WAL bảo thủ trên primary:

~~~sql
-- Chạy trên primary SAU KHI COMMIT thành công:
SELECT pg_current_wal_flush_lsn();
~~~

Vì mốc lấy **sau COMMIT**, nó bao gồm ít nhất WAL cần thiết cho giao dịch vừa xác nhận ở cấu hình local flush phù hợp; mốc còn có thể bao gồm WAL của transaction khác. Do vậy, nó là một **fence bảo thủ**, không phải một transaction ID riêng.

Trên physical standby:

~~~sql
SELECT pg_is_in_recovery();
SELECT pg_last_wal_receive_lsn();
SELECT pg_last_wal_replay_lsn();
~~~

Có thể yêu cầu standby đã replay qua mốc F:

~~~sql
-- Dấu ? biểu diễn tham số bind do ứng dụng cung cấp.
SELECT COALESCE(
    pg_last_wal_replay_lsn() >= CAST(? AS pg_lsn),
    FALSE
);
~~~

Chỉ khi **replay_lsn >= F** và một câu SELECT mới dùng snapshot thích hợp, đường đọc standby mới có cơ sở quan sát commit tới mốc F. Nếu dùng connection với transaction REPEATABLE READ đã lấy snapshot cũ, LSN tiến lên không tự làm snapshot đó đổi.

Những giới hạn:

- LSN của **hai cluster không có chung lịch sử/timeline phù hợp** không thể so sánh bừa. Sau failover, cần xác thực nguồn và generation của token.
- Đảm bảo standby đã replay WAL **không đồng nghĩa một cache, Elasticsearch index hoặc projection khác đã cập nhật**.
- LSN có thể dùng làm rào chắn cho một transaction đã biết thành công, **không tự giải quyết trường hợp ứng dụng không biết commit đã xảy ra hay chưa**.
- Standby đang dùng **logical replication** hoặc hệ quản trị khác có thể cần offset/version tương ứng; không thể áp nguyên phương pháp physical replay LSN.

## 12. Spring/JDBC: chính sách chọn nguồn đọc theo tính nhất quán

Một thiết kế Java thực dụng nên diễn đạt **yêu cầu mới nhất** ở API/application service, thay vì giả định mọi SELECT được phép đến replica.

Ví dụ giả định bảng **customer_profiles(tenant_id, customer_id, display_name, version)**, trong đó version tăng theo mọi lần cập nhật có ý nghĩa:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class ProfileReadRepository {
    private final DataSource primary;
    private final DataSource replica;

    public ProfileReadRepository(DataSource primary, DataSource replica) {
        this.primary = primary;
        this.replica = replica;
    }

    public record Profile(long id, String name, long version) {}

    public Profile readEventually(long tenantId, long customerId)
            throws SQLException {
        return read(replica, tenantId, customerId);
    }

    public Profile readAtLeastVersion(
            long tenantId, long customerId, long minimumVersion
    ) throws SQLException {
        Profile candidate = read(replica, tenantId, customerId);
        if (candidate != null && candidate.version() >= minimumVersion) {
            return candidate;
        }

        // Replica chưa đủ mới hoặc chưa có bản ghi: đọc primary.
        Profile source = read(primary, tenantId, customerId);
        if (source == null || source.version() < minimumVersion) {
            throw new IllegalStateException(
                    "Nguồn chính chưa đáp ứng version yêu cầu");
        }
        return source;
    }

    private static Profile read(
            DataSource source, long tenantId, long customerId
    ) throws SQLException {
        String sql = """
            SELECT display_name, version
            FROM customer_profiles
            WHERE tenant_id = ? AND customer_id = ?
            """;
        try (Connection connection = source.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(sql)) {
            statement.setLong(1, tenantId);
            statement.setLong(2, customerId);
            try (ResultSet rs = statement.executeQuery()) {
                if (!rs.next()) {
                    return null;
                }
                return new Profile(
                        customerId, rs.getString(1), rs.getLong(2));
            }
        }
    }
}
~~~

Ví dụ cố ý cho thấy **router chọn DataSource** và **version gate**, không phải một mô hình bảo mật đầy đủ. Trước khi gọi, service phải xác định tenant từ danh tính đã xác thực, kiểm tra quyền truy cập hồ sơ, và xử lý kết quả **null/không tồn tại** theo hợp đồng API.

Điểm cần nhớ:

- **readEventually** có thể thấy dữ liệu cũ.
- **readAtLeastVersion** không trả bản có version thấp hơn yêu cầu; nó fallback primary bằng một SELECT mới.
- Cơ chế này chỉ bảo đảm mức mới tối thiểu **cho một bản ghi có version đơn điệu**. Nó không tự tạo snapshot nhất quán cho nhiều bảng hay xử lý xóa bản ghi không có tombstone.
- Nếu primary vừa failover, source mới, version reset hoặc cache cũ có thể làm so sánh không còn đúng; cần **epoch/generation**, chính sách routing và đối soát.
- Nếu replica không kết nối được, code trên sẽ ném **SQLException** thay vì fallback; production có thể thêm nhánh fallback có giới hạn, metrics và circuit breaker.

### 12.1. Spring @Transactional(readOnly=true) không tự bảo đảm freshness

Trong Spring, một method:

~~~java
@Transactional(readOnly = true)
public Profile load(long tenantId, long customerId) {
    return repository.readEventually(tenantId, customerId);
}
~~~

chỉ mô tả thuộc tính transaction theo cơ chế Spring; **readOnly không mặc định có nghĩa đọc replica**, và càng không bảo đảm replica đã replay bản mới nhất. Routing cần được cấu hình rõ, đồng thời transaction đã bind connection có thể không chuyển DataSource giữa chừng. Với JPA, persistence context cũ còn có thể trả entity managed stale.

Đặt transaction boundary trong application service và xác định có cần RYW hay không trước khi chọn đường đọc.

## 13. Độ bền sau failover và định nghĩa RPO

**RPO (Recovery Point Objective)** là mức mất dữ liệu tối đa mà nghiệp vụ đặt mục tiêu chấp nhận sau sự cố; **RTO (Recovery Time Objective)** là thời gian mục tiêu để khôi phục dịch vụ.

Ví dụ hai tình huống:

~~~text
ASYNC
  T1 COMMIT OK trên primary
  standby mới replay tới trước T1
  primary mất hoàn toàn
  failover chọn standby
  --> T1 có thể không tồn tại trên primary mới

SYNC flush tới standby đủ điều kiện
  T1 COMMIT OK
  standby được chọn đã flush WAL của T1
  primary mất
  failover chọn đúng standby có WAL đó
  --> có cơ sở phục hồi T1 khi replay được thực hiện đúng
~~~

Trong ví dụ thứ hai, từ **“có cơ sở”** quan trọng: mất đồng thời cả primary và standby, hỏng lưu trữ, failover sai nút hoặc hành vi phá vỡ giả định đồng bộ đều có thể làm kết quả khác.

### 13.1. RPO = 0 là một mục tiêu gắn với mô hình sự cố

Không nên viết “đã bật sync nên RPO = 0 trong mọi trường hợp”. Cần xác định:

- RPO=0 đối với **sự cố nào**: mất một máy, một availability zone, một region hay lỗi thao tác con người?
- Transaction nào được coi là **đã xác nhận** và tại mức chờ nào?
- Khi failover, standby mới có **chứa đúng WAL đã được xác nhận** hay không?
- Có tình huống vận hành hạ mức đồng bộ để tiếp tục ghi không?
- Thiết bị, backup và lưu trữ ở các vùng có chia sẻ miền lỗi chung không?

RPO và RTO phải được kiểm chứng bằng diễn tập khôi phục, không chỉ dựa vào một cờ cấu hình.

### 13.2. Độ trễ replica không trực tiếp là lượng mất dữ liệu tuyệt đối

Một standby chậm vài giây có thể giữ một lượng WAL lớn hoặc nhỏ tùy tốc độ ghi. Nếu không còn giao dịch mới, một phép đo “thời gian từ lần replay cuối” có thể tăng dù standby đã theo kịp. Để đánh giá cửa sổ mất dữ liệu, cần biết **vị trí WAL, trạng thái flush/replay và các commit đã được xác nhận**, không chỉ một đồng hồ lag.

## 14. Failover, fencing và nguy cơ split-brain

**Failover** là quá trình chuyển vai trò phục vụ từ primary cũ sang một nút khác khi xảy ra sự cố. Replication chỉ cung cấp bản sao; để chuyển vai trò an toàn còn cần **điều phối quyền ghi**.

Sơ đồ nguy hiểm:

~~~text
    Mạng bị phân vùng

Primary A (cũ)           Standby B được promote
  vẫn nhận ghi             cũng nhận ghi
         \                 /
          \               /
           hai nguồn ghi độc lập
                |
           SPLIT-BRAIN
~~~

Nếu A và B đều tin mình là primary, các transaction có thể đi theo hai lịch sử WAL khác nhau. Chỉ bật synchronous replication trước sự cố không tự loại bỏ kịch bản này.

Các yêu cầu vận hành chính:

1. **Fencing:** ngăn primary cũ tiếp tục nhận ghi khi primary mới được công nhận (ví dụ qua điều phối failover, tách kết nối, cơ chế hạ tầng hoặc kiểm soát truy cập thích hợp).
2. **Leader election/quorum và lease phù hợp:** chỉ một nút có quyền nhận ghi theo mô hình hệ thống.
3. **Chọn standby đủ mới:** ưu tiên vị trí WAL/điều kiện đã cam kết, không đơn thuần chọn máy phản hồi ping nhanh nhất.
4. **Routing chuyển đổi nhất quán:** ứng dụng/pool/proxy phải biết primary mới và không giữ đường ghi đến nút cũ.
5. **Rejoin có kiểm soát:** primary cũ không thể tùy tiện quay lại cụm với dữ liệu đã phân kỳ; có thể cần phục hồi/rebuild hoặc phương án phù hợp của DBMS.

Trong PostgreSQL, dùng một thành phần quản lý HA như một hệ điều phối chuyên dụng thường cần thiết nếu muốn failover tự động an toàn. Các bước cụ thể phụ thuộc topology, không nên tự viết một script “ping lỗi thì promote” cho production.

## 15. Nhân bản không đồng nghĩa backup

Nếu một lập trình viên chạy nhầm:

~~~sql
DELETE FROM orders WHERE created_at < DATE '2026-01-01';
~~~

thì thay đổi hợp lệ về mặt SQL vẫn có thể được replicate tới standby. **Đồng bộ hay bất đồng bộ đều có thể nhân bản cả lỗi con người**.

| Khả năng | Replication | Backup/PITR |
| --- | --- | --- |
| Giữ một nút có trạng thái gần hiện tại để chuyển vai trò | Mục đích chính | Không nhất thiết |
| Phân tải đọc | Có thể với standby thích hợp | Không |
| Khôi phục sau xóa nhầm đã replicate | Thường không tự giải quyết | Cần backup/PITR hoặc quy trình phục hồi nghiệp vụ |
| Khôi phục sau mất toàn bộ cụm | Chỉ được nếu còn bản sao ngoài vùng lỗi | Backup độc lập ngoài vùng lỗi là lớp phòng vệ quan trọng |
| Lưu lịch sử có thể chọn mốc thời gian | Không tự bảo đảm | Base backup + chuỗi WAL archive phù hợp có thể hỗ trợ PITR |

Với PostgreSQL, **WAL archiving**, **base backup**, kiểm thử restore và chính sách lưu bản sao ngoài vùng lỗi cần được tổ chức độc lập với việc các standby đang hoạt động bình thường.

## 16. Physical replication và logical replication không giống nhau

Trong hệ sinh thái PostgreSQL:

- **Physical streaming replication** truyền và replay thông tin WAL ở mức vật lý để duy trì một bản sao tương ứng của cluster. Nó phù hợp các mô hình standby/failover nhất định.
- **Logical replication** phát các thay đổi logic của bảng/publication tới subscriber, có thể hỗ trợ lựa chọn tập dữ liệu và những kiến trúc tích hợp khác. Nó có cơ chế slot, thứ tự apply, schema/DDL và hạn chế riêng.

Không được mặc định:

1. Một logical subscriber có đầy đủ mọi dữ liệu và WAL trạng thái vật lý để **promote như physical standby**.
2. Chọn **synchronous_commit=remote_apply** trên primary sẽ biến một logical subscriber tùy ý thành bản sao đồng bộ có hành vi giống physical standby ở mọi cấu hình.
3. LSN physical replay trên một standby có thể được dùng nguyên xi làm watermark cho Kafka, search index hoặc một database khác.
4. Một DDL thay đổi schema sẽ luôn được logical replication tự phát đúng như dữ liệu hàng.

Khi cần thay đổi schema, nâng cấp hoặc tích hợp nhiều hệ, phải kiểm chứng cơ chế replication cụ thể trước khi hứa tính nhất quán.

## 17. Ứng dụng Java xử lý timeout và kết quả COMMIT không chắc chắn

Hãy xét Java gửi COMMIT:

~~~text
Trường hợp A:
  Client gửi COMMIT -> primary chưa hoàn tất -> kết nối lỗi

Trường hợp B:
  Client gửi COMMIT -> primary/standby đạt điều kiện ack
  -> primary đã commit -> phản hồi tới client bị mất
~~~

Cùng một **SQLException/timeout** ở phía client có thể đại diện cả A và B. Điều này đúng với cả chế độ đồng bộ lẫn bất đồng bộ. **Replication mode không cho ứng dụng biết chắc commit đã thất bại khi mất phản hồi.**

Đối với một thao tác không lũy đẳng như tạo đơn hoặc trừ tiền:

1. Client giữ **request_id** ổn định qua mọi lần thử.
2. Database có **UNIQUE (tenant_id, request_id)** hoặc khóa nghiệp vụ tương ứng.
3. Dữ liệu tác động và kết quả nhận request được commit **trong một transaction**.
4. Sau timeout, service đối chiếu trạng thái theo request ID trên **nguồn đáng tin cậy và đủ mới**, không mù quáng gửi lại với ID mới.
5. Nếu chưa thể kết luận vì failover/replica lag, trả trạng thái phù hợp như **UNKNOWN/PENDING** hoặc tra lại có kiểm soát, không báo rollback chắc chắn.

Một ví dụ transaction JDBC tối giản:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class OrderWriter {
    private final DataSource primary;

    public OrderWriter(DataSource primary) {
        this.primary = primary;
    }

    public void create(long tenantId, String requestId, long productId)
            throws SQLException {
        try (Connection connection = primary.getConnection()) {
            connection.setAutoCommit(false);
            try {
                try (PreparedStatement st = connection.prepareStatement(
                        """
                        INSERT INTO orders(tenant_id, request_id, product_id)
                        VALUES (?, ?, ?)
                        """)) {
                    st.setLong(1, tenantId);
                    st.setString(2, requestId);
                    st.setLong(3, productId);
                    st.executeUpdate();
                }
                connection.commit();
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }
}
~~~

Giả định **orders** tồn tại với unique constraint phù hợp cho **(tenant_id, request_id)**. Đoạn code chỉ minh họa transaction và kết nối **primary**; việc đối chiếu request trùng, kiểm tra payload, trả kết quả cũ và quản lý idempotency ở tầng API vẫn phải được xây dựng. Unique violation không mặc nhiên có nghĩa lần trước thành công với cùng payload; cần đọc lại và xác nhận.

Nếu primary bị thay đổi do failover, **DataSource, DNS/proxy, pool và chính sách kết nối** phải được cập nhật/refresh tương thích. Connection cũ tới node bị hạ vai trò có thể thất bại hoặc không đáp ứng yêu cầu ghi.

## 18. Quan sát replication và WAL trên PostgreSQL

Trên primary, có thể xem tiến độ của các standby được kết nối:

~~~sql
SELECT application_name,
       client_addr,
       state,
       sync_state,
       sync_priority,
       sent_lsn,
       write_lsn,
       flush_lsn,
       replay_lsn,
       write_lag,
       flush_lag,
       replay_lag
FROM pg_stat_replication;
~~~

Các cột quan trọng:

| Trường | Ý nghĩa khái quát |
| --- | --- |
| **state** | Tình trạng kết nối replication |
| **sync_state** | Trạng thái tham gia đồng bộ: ví dụ sync, quorum, potential, async tùy cấu hình |
| **sent_lsn** | WAL primary đã gửi đến đâu |
| **write_lsn** | Standby báo đã write đến đâu |
| **flush_lsn** | Standby báo đã flush đến đâu |
| **replay_lsn** | Standby báo đã replay đến đâu |
| **write_lag / flush_lag / replay_lag** | Thống kê trễ liên quan các mốc xác nhận; không phải đồng hồ dự báo chính xác mọi transaction |

Trên primary có thể xem số byte chênh lệch WAL so với mốc replay báo cáo:

~~~sql
SELECT application_name,
       pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn)
           AS replay_bytes_behind
FROM pg_stat_replication;
~~~

Giá trị tính ra là **khoảng cách byte trong dòng WAL**, không trực tiếp là số giây hoặc số transaction mất nếu failover. WAL có thể gồm nhiều loại record ngoài thay đổi hàng của một bảng. Khi standby ngắt kết nối, nó có thể không còn xuất hiện trong **pg_stat_replication**; không coi “không có dòng” là “đã theo kịp”.

Trên physical standby:

~~~sql
SELECT pg_is_in_recovery() AS standby_mode,
       pg_last_wal_receive_lsn() AS receive_lsn,
       pg_last_wal_replay_lsn() AS replay_lsn,
       pg_last_xact_replay_timestamp() AS last_commit_replay_time;
~~~

Lưu ý **pg_last_xact_replay_timestamp()** có thể đứng yên khi không có transaction mới; chênh lệch với thời gian hiện tại tăng lên **không tự chứng minh replica đang bị lag**.

### 18.1. Metrics ở tầng ứng dụng

Nên đo thêm:

- **Commit latency p50/p95/p99**, số transaction timeout và lý do chờ.
- Số lượt **primary read fallback** khi replica chưa đủ mới.
- **Lag theo LSN**, số lượng standby sẵn sàng, trạng thái sync/quorum.
- Tỷ lệ **read-your-writes violation**, cache stale hit, request bị chờ fence.
- **Failover duration**, lỗi routing/connection và số commit có trạng thái chưa xác định.
- **WAL generation rate**, dung lượng giữ WAL vì slot/archive và áp lực I/O.

Không log thô mật khẩu replication, token kết nối hoặc payload nhạy cảm chỉ để chẩn đoán lag.

## 19. Replication slot, WAL retention và nguy cơ đầy đĩa

Standby có thể mất kết nối trong lúc primary tiếp tục tạo WAL. Nếu các WAL segment cần thiết bị xóa/tái sử dụng trước khi standby bắt kịp, standby có thể không tiếp tục streaming từ vị trí cũ.

Trong PostgreSQL, **replication slot** là một cơ chế giữ lại WAL và các tài nguyên liên quan để phục vụ một consumer. Nó giúp giảm nguy cơ bị mất WAL cần thiết, nhưng có thể khiến WAL **tích tụ nhiều** khi consumer ngừng xử lý.

Ví dụ chẩn đoán:

~~~sql
SELECT slot_name,
       slot_type,
       active,
       restart_lsn,
       confirmed_flush_lsn
FROM pg_replication_slots;
~~~

**confirmed_flush_lsn** đặc biệt liên quan một số logical slots và có thể NULL ở physical slot; không coi mọi cột áp dụng giống nhau cho cả hai loại.

Các điểm vận hành:

- **max_slot_wal_keep_size** có thể đặt giới hạn giữ WAL theo slot trong những điều kiện cụ thể, nhưng nếu WAL cần thiết không còn, consumer có thể phải được khởi tạo lại.
- **wal_keep_size** không phải giới hạn cứng cho toàn bộ thư mục WAL và không thay thế quản lý archive/slot.
- **Archive failure**, **checkpoint**, replication slots và tải ghi đều có thể ảnh hưởng dung lượng WAL.
- Không xóa trực tiếp tệp trong **pg_wal** để cứu dung lượng. Phải điều tra nguyên nhân và xử lý theo quy trình quản trị được hỗ trợ.

Sự tồn tại của slot không tự bảo đảm standby đã replay giao dịch mới; nó chủ yếu hỗ trợ duy trì dữ liệu WAL cần cho việc bắt kịp.

## 20. Đánh đổi hiệu năng và tính sẵn sàng khi mạng bất ổn

Giả sử primary ở vùng A, standby đồng bộ ở vùng B. Mỗi commit có thể phải chờ đường truyền liên vùng và tình trạng flush/replay của standby. Độ trễ tăng do:

1. Khoảng cách mạng và round-trip time.
2. Standby thiếu CPU, I/O hoặc đang recovery/replay chậm.
3. WAL flush hoặc đồng bộ lưu trữ chậm.
4. Các transaction commit rất nhỏ nhưng nhiều, hoặc bị gom theo đợt không hiệu quả với tải hiện tại.
5. Sự thay đổi sync standby khi một nút mất kết nối.

Một số chiến lược thường được cân nhắc:

- **Standby đồng bộ trong cùng vùng lỗi gần** để giảm commit latency, và **standby bất đồng bộ ở vùng xa** để dự phòng địa lý. Tuy nhiên, nếu primary và standby đồng bộ cùng mất theo một sự cố vùng, mục tiêu RPO liên vùng chưa chắc đạt.
- **Quorum nhiều standby** để tăng khả năng có đủ xác nhận khi một nút hỏng, đánh đổi số nút cần đồng bộ và topology.
- **Những transaction thật sự nhạy cảm** có thể dùng chính sách đồng bộ mạnh hơn khi DBMS cho phép, nhưng phải bảo đảm chính sách được áp dụng đúng ở ranh giới giao dịch và hiểu thay đổi điều kiện commit.
- **Giảm số transaction, batch theo use case hợp lệ**, rút ngắn transaction và tránh làm việc ngoài DB khi đang giữ transaction.
- **Đặt timeout/backpressure** và chính sách degrade được phê duyệt trước; không để toàn bộ ứng dụng tự retry commit liên tục làm cụm quá tải.

Độ trễ ghi và tính bền vững không phải trục đánh đổi duy nhất. Đọc từ standby có thể tiết kiệm tải primary, nhưng **freshness, cache invalidation, snapshot và retry** vẫn cần hợp đồng riêng.

## 21. Bảo mật và quản trị cụm replication

Replication truyền dữ liệu có thể bao gồm nội dung nhạy cảm. Một số nguyên tắc:

- **Kết nối replication:** dùng xác thực, tài khoản với quyền hạn phù hợp, giới hạn địa chỉ mạng và TLS theo yêu cầu; kiểm tra danh tính server thay vì chỉ bật mã hóa không xác thực.
- **Quản lý secret:** không đưa password vào ví dụ cấu hình commit, log hoặc repository. Sử dụng secret manager và chính sách xoay credential.
- **Giới hạn quyền:** tài khoản ứng dụng thường không cần quyền thay đổi cấu hình replication, promote standby hoặc quản lý slot.
- **Dữ liệu ở standby:** mã hóa lưu trữ/backup, giới hạn quyền truy cập và xử lý khi giải thể bản sao.
- **Quản lý failover:** theo dõi ai có quyền promote và cách fencing primary cũ; bảo vệ endpoint quản trị để tránh split-brain do thao tác sai.
- **Audit:** lưu lịch sử chuyển vai trò, thay đổi synchronous_standby_names hoặc hạ mức đồng bộ vì các thao tác này ảnh hưởng cam kết dữ liệu.

Nếu ứng dụng dùng read replica để phục vụ tenant, mọi đường đọc vẫn phải áp kiểm tra ủy quyền và ranh giới tenant; bản sao dữ liệu không tự là cơ chế phân quyền.

## 22. Kiểm thử trước khi khẳng định hệ thống đạt SLA

Không chỉ kiểm tra “standby đang chạy”. Nên có các kịch bản:

1. **Async bình thường:** ghi trên primary, đo thời gian standby receive/flush/replay. Xác minh replica có thể thấy dữ liệu chậm hơn.
2. **Async mất primary:** tại các mốc WAL khác nhau, thử nghiệm failover trong môi trường test; đối chiếu những transaction đã được API xác nhận.
3. **Sync flush:** xác minh primary chỉ xác nhận COMMIT khi điều kiện standby đồng bộ thực sự đạt, không nhầm với local-only.
4. **Sync remote_apply:** xác minh SELECT mới ở standby được chọn có thể thấy commit phù hợp sau xác nhận; kiểm tra ảnh hưởng của snapshot cũ.
5. **Mất standby bắt buộc:** đo thời gian COMMIT bị chờ, timeout, phản hồi API và quy trình vận hành thay thế/quorum.
6. **Mạng phân vùng:** đảm bảo có fencing và không để hai primary tiếp tục nhận ghi song song.
7. **Failover routing:** sau promote, pool/driver/router không giữ kết nối viết sai node; các request đang chạy xử lý lỗi đúng.
8. **Commit response bị mất:** client retry cùng request ID và không tạo tác động nghiệp vụ hai lần.
9. **Đọc sau ghi:** GET với minVersion/fence không trả bản cũ từ standby/cache; fallback primary hoạt động.
10. **WAL retention:** khi standby chậm hoặc dừng, phát hiện slot giữ WAL và có cảnh báo dung lượng.
11. **Khôi phục từ backup:** thực hành restore/PITR khi thao tác xóa nhầm đã replicate; không chỉ thử failover.
12. **Bảo mật:** xác thực replication, quyền quản trị và log không lộ secret.

Mỗi test phải quan sát **các transaction đã được xác nhận** và so sánh với dữ liệu trên primary mới, không chỉ nhìn HTTP status hoặc sự tồn tại của một hàng. Ghi lại topology, cấu hình, thời điểm xác nhận và LSN để kết quả có thể tái hiện.

## 23. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Bất đồng bộ nghĩa là dữ liệu trên primary không bền.” | Primary vẫn có cơ chế local WAL/commit durability; rủi ro nằm ở standby chưa bắt kịp khi failover |
| “Đồng bộ nghĩa là tất cả replica đã có dữ liệu để SELECT.” | Cần phân biệt remote_write, flush và remote_apply; có thể chỉ đợi một số standby |
| “synchronous_commit=on luôn đợi standby.” | Phải có synchronous_standby_names và standby phù hợp; nếu không, on chờ WAL flush cục bộ |
| “remote_write tương đương bền vững trên standby.” | Write có thể chỉ tới cache hệ điều hành, chưa flush khi OS crash |
| “Standby nhận WAL xong là đọc được dữ liệu.” | WAL cần được replay; transaction đọc có thể giữ snapshot cũ |
| “Một standby sync bảo đảm RPO=0 trong mọi sự cố.” | Cần mô hình lỗi, lựa chọn failover đúng nút, fencing và hạ tầng lưu trữ phù hợp |
| “Đồng bộ không làm giảm availability.” | Khi thiếu standby bắt buộc, commit có thể chờ lâu hoặc timeout |
| “Replica có WAL là backup.” | Xóa nhầm/ghi sai có thể được replicate; vẫn cần backup và PITR |
| “LSN ở hai cụm bất kỳ đều so sánh được.” | Chỉ so sánh trong lịch sử WAL/timeline phù hợp |
| “Không có dòng trong pg_stat_replication nghĩa là standby đã bắt kịp.” | Standby có thể đang mất kết nối và không xuất hiện |
| “Replication slot luôn tốt, không có chi phí.” | Slot giữ WAL và có thể làm đầy đĩa khi consumer đứng |
| “Commit timeout chắc chắn transaction rollback.” | Server có thể đã commit nhưng mất phản hồi; cần idempotency/đối soát |
| “Failover chỉ cần promote máy còn sống.” | Phải chọn bản đủ mới, fencing primary cũ và điều chỉnh routing |
| “Đọc replica sau một giây thì chắc có RYW.” | Lag không bị chặn bởi một thời gian cố định; cần fence hoặc fallback primary |

## 24. Bài tập tự kiểm tra

### Bài 1. Nhận diện async

T1 COMMIT trên primary được trả thành công ngay khi WAL đã flush cục bộ. Standby ở vùng khác nhận WAL sau đó 200 ms. Đây là cơ chế đồng bộ hay bất đồng bộ? Nếu primary mất ngay trước khi standby nhận WAL thì sao?

**Gợi ý:** Đó là **bất đồng bộ** với standby vì primary không đợi standby xác nhận. Nếu failover sang standby chưa có commit của T1 và primary không thể phục hồi, T1 có thể không tồn tại trên primary mới.

### Bài 2. Flush khác replay

Primary dùng PostgreSQL synchronous_commit=on cùng một synchronous standby. COMMIT đã được xác nhận, nhưng một truy vấn mới trên standby vẫn nhìn thấy giá trị cũ trong khoảnh khắc ngắn. Điều này có mâu thuẫn không?

**Gợi ý:** Không. Mức **on** với sync standby đợi standby **flush WAL**, không mặc định đợi **replay**. Cần **remote_apply**, fence hoặc primary read nếu muốn bảo đảm thấy ngay.

### Bài 3. Lựa chọn FIRST và ANY

Một cấu hình dùng FIRST 1 với hai standby; một cấu hình khác dùng ANY 2 với ba standby. Cả hai yêu cầu mức xác nhận nào?

**Gợi ý:** FIRST 1 ưu tiên chọn một standby đủ điều kiện theo thứ tự. ANY 2 cần **hai** standby bất kỳ trong danh sách xác nhận. Cả hai vẫn phải kết hợp với synchronous_commit để xác định chờ write/flush/apply.

### Bài 4. Không có standby sync

PostgreSQL primary cấu hình synchronous_commit=on, nhưng synchronous_standby_names rỗng. Giao dịch có bắt buộc đợi WAL flush trên replica không?

**Gợi ý:** Không. Ở cấu hình này **on** chờ WAL flush cục bộ, không đặt điều kiện xác nhận từ standby.

### Bài 5. RPO và tính sẵn sàng

Một hệ thống yêu cầu không mất giao dịch đã xác nhận khi một máy chủ hỏng, nhưng cũng cần tiếp tục ghi khi một standby đang bảo trì. Những quyết định thiết kế nào cần làm?

**Gợi ý:** Xác định mô hình lỗi và quorum/standby đủ điều kiện, failover chọn đúng nút, chính sách thay thế standby, timeout/backpressure và có chấp nhận hạ mức đồng bộ hay không. Không thể chỉ bật một cờ rồi coi cả RPO lẫn availability được bảo đảm.

### Bài 6. Replica nhận nhưng chưa replay

Standby có receive_lsn cao hơn fence F nhưng replay_lsn thấp hơn F. GET từ standby có thể được coi là đáp ứng read-your-writes tới F không?

**Gợi ý:** Chưa. Phải đợi standby replay qua F và sử dụng snapshot đọc thích hợp, hoặc fallback primary.

### Bài 7. Primary cũ quay trở lại

Sau khi standby B được promote, primary A cũ bất ngờ kết nối mạng trở lại và tiếp tục nhận ghi. Hệ quả là gì?

**Gợi ý:** Nguy cơ split-brain và dữ liệu phân kỳ. Cần fencing A, chỉ một leader có quyền ghi, điều chỉnh routing và đưa A quay lại bằng quy trình tái đồng bộ an toàn.

### Bài 8. WAL đầy đĩa

Standby bất đồng bộ mất kết nối ba ngày; primary dùng replication slot giữ WAL. Thư mục pg_wal tăng rất lớn. Có nên xóa WAL segment bằng tay?

**Gợi ý:** Không. Cần kiểm tra slot, WAL retention, archiving, dung lượng và chiến lược khôi phục standby; xóa thủ công có thể phá replication/recovery.

### Bài 9. Đồng bộ có thay backup không?

Một lệnh DELETE thiếu WHERE đã commit và được replicate tới mọi standby. Có thể chuyển sang standby để lấy lại dữ liệu không?

**Gợi ý:** Thường không, vì thay đổi xóa cũng đã được nhân bản. Cần backup/PITR hoặc giải pháp phục hồi nghiệp vụ riêng.

### Bài 10. Commit không rõ kết quả

Client Java gửi COMMIT rồi nhận SQLException do mất mạng. Lần retry đầu tiên nên có ID mới hay giữ ID cũ?

**Gợi ý:** **Giữ request ID cũ**, đối soát trạng thái trên nguồn đáng tin cậy và dùng unique constraint/idempotency. Mất phản hồi không chứng minh commit đã rollback.

## 25. Checklist thiết kế replication cho tầng persistence

Trước khi triển khai primary/replica trong hệ thống Java:

1. **Mục tiêu:** replication phục vụ HA, read scaling, RPO hay kết hợp? Use case nào cần RYW?
2. **Mô hình lỗi:** cần chịu được mất một node, một AZ hay toàn vùng? Có backup ngoài miền lỗi không?
3. **Commit contract:** chế độ async hay sync; sync đợi write, flush hay apply; đủ bao nhiêu standby?
4. **Primary durability:** fsync/synchronous_commit cục bộ và thiết bị lưu trữ có bảo đảm phù hợp không?
5. **Topology:** ai có quyền ghi, ai có quyền promote, dùng priority hay quorum nào?
6. **Failover:** có fencing, chọn standby đủ mới, rejoin an toàn và routing cập nhật không?
7. **Read policy:** truy vấn nào đọc replica; cách phát hiện dữ liệu cũ; có version/LSN fence và primary fallback không?
8. **Transaction:** các bước nghiệp vụ có commit cùng một nguồn không; kết quả commit mơ hồ được đối soát thế nào?
9. **Idempotency:** retry sau lỗi kết nối/failover có tạo lặp đơn hàng, điểm thưởng hoặc thanh toán không?
10. **WAL retention:** slot, archive, checkpoint và dung lượng có cảnh báo trước khi đầy không?
11. **Metrics:** có quan sát send/write/flush/replay LSN, sync state, commit latency và failover duration không?
12. **Bảo mật:** replication account, TLS, secret, quyền quản trị và dữ liệu standby có được bảo vệ không?
13. **Backup:** có base backup/WAL archive và diễn tập restore/PITR độc lập với replica không?
14. **Thử nghiệm:** có diễn tập mất primary, mất standby, network partition, lag và commit response loss không?

## 26. Tổng kết

**Nhân bản bất đồng bộ** ưu tiên khả năng xác nhận ghi trên primary mà không đợi standby, đổi lại có cửa sổ replica chưa bắt kịp và nguy cơ mất một số commit đã được xác nhận khi phải failover sang bản sao thiếu WAL. **Nhân bản đồng bộ** buộc commit chờ đủ phản hồi của standby theo mức xác nhận đã chọn, giúp giảm rủi ro mất dữ liệu trong phạm vi sự cố được thiết kế, nhưng có thể tăng độ trễ và giảm khả năng tiếp tục ghi khi không còn đủ standby.

Đối với PostgreSQL, hãy tách rõ **local commit, remote_write, remote flush và remote_apply**; đọc tiến độ bằng **LSN** và không nhầm standby đã nhận WAL với đã replay. Khi xây dựng persistence Java, định nghĩa hợp đồng read-your-writes, route đọc mới nhất tới primary hoặc dùng fence/fallback; giữ idempotency để xử lý commit không rõ kết quả. Cuối cùng, replication phải đi cùng **fencing, failover, backup/PITR, bảo mật, metrics và kiểm thử sự cố**. Có bản sao là một điều kiện hữu ích; **có chiến lược nhất quán và phục hồi đã kiểm chứng** mới là mục tiêu vận hành.
