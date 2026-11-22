# RDB snapshot và khoảng dữ liệu có thể mất trong Spring Data Redis

## 1. Bối cảnh: Redis rất nhanh, nhưng ghi thành công chưa chắc đã nằm trên đĩa

Spring Data Redis cho phép ứng dụng Java ghi và đọc dữ liệu từ Redis qua `RedisTemplate`, `StringRedisTemplate`, Reactive Redis, Repository hoặc Spring Cache. Những API đó thường làm việc với **trạng thái Redis đang phục vụ tại thời điểm lệnh được xử lý**. Nhưng nếu Redis bị mất điện, process bị kill hoặc máy chủ gặp lỗi, câu hỏi khác xuất hiện:

> Redis có thể dựng lại bao nhiêu phần trạng thái đã ghi khi khởi động từ dữ liệu bền vững trên ổ đĩa?

Một trong các cơ chế persistence của Redis là **RDB snapshot** (*Redis Database snapshot*). RDB lưu ảnh chụp dữ liệu tại một thời điểm vào tệp nhị phân, thường mang tên `dump.rdb`. Khi Redis khởi động lại, tệp RDB hợp lệ có thể được tải để khôi phục trạng thái lưu trước đó.

Tuy nhiên, RDB là **snapshot theo từng mốc**, không phải nhật ký ghi lại từng lệnh. Nếu chỉ dùng RDB, các thay đổi xảy ra **sau thời điểm ảnh chụp cuối cùng phản ánh** có thể biến mất khi Redis phải phục hồi từ snapshot ấy.

Ví dụ:

```text
10:00:00  Bắt đầu snapshot, trạng thái có 1.000 orders
10:00:12  Snapshot hoàn thành và được lưu trên đĩa
10:00:15  Đơn hàng o-1001 được ghi vào Redis
10:00:20  Đơn hàng o-1002 được cập nhật trạng thái
10:00:25  Redis gặp sự cố, dữ liệu RAM mất
10:01:00  Redis khởi động lại từ snapshot 10:00:00

Kết quả có thể xảy ra:
  - o-1001 không có trong dữ liệu khôi phục
  - o-1002 quay về trạng thái tại 10:00:00
```

Cần phân biệt **thời điểm snapshot bắt đầu**, **thời điểm file snapshot hoàn tất**, **thời điểm Redis thông báo ghi thành công**, và **thời điểm dữ liệu được phục hồi**. Đây là nguồn gốc của nhiều hiểu nhầm về mức mất dữ liệu có thể chấp nhận khi dùng RDB.

Bài học này giải thích cơ chế RDB, khoảng mất dữ liệu (*data-loss window*), các yếu tố ảnh hưởng RPO/RTO, cách quan sát Redis và lựa chọn thiết kế ứng dụng Spring Data Redis phù hợp.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích RDB snapshot lưu gì và không lưu gì.
2. Phân biệt `SAVE`, `BGSAVE`, quy tắc tự động `save` và thời điểm ảnh chụp.
3. Hiểu cơ chế `fork` và **copy-on-write (COW)** khi tạo snapshot nền.
4. Dự đoán các thay đổi có nguy cơ mất sau sự cố, kể cả cập nhật và xóa dữ liệu.
5. Giải thích vì sao lịch snapshot không phải bảo đảm cứng về RPO.
6. Đọc các chỉ số `INFO persistence`, `LASTSAVE` và trạng thái `BGSAVE`.
7. So sánh RDB với AOF, replication, failover và backup độc lập.
8. Thiết kế kiểm thử sự cố, backup/restore, monitoring và chính sách retention.
9. Hiểu giới hạn của Spring Data Redis: lệnh `SET` trả thành công không đồng nghĩa RDB vừa được cập nhật.
10. Chọn mức durability phù hợp với cache, session, queue, counter và dữ liệu nghiệp vụ quan trọng.

## 2. RDB là gì?

**RDB (Redis Database)** là định dạng snapshot nhị phân của Redis. Một snapshot mô tả trạng thái dữ liệu Redis tại một thời điểm logic, gồm nhiều loại dữ liệu mà Redis đang lưu và metadata cần thiết, chẳng hạn thời hạn hết hạn của key.

RDB được Redis tạo ra để:

- Khởi động lại từ trạng thái đã lưu.
- Tạo bản sao dữ liệu phục vụ backup hoặc chuyển môi trường.
- Hỗ trợ một số quy trình replication/full synchronization theo cơ chế Redis.
- Giảm chi phí lưu trữ so với việc cần tái thực thi toàn bộ lịch sử lệnh trong một số workload.
- Phục hồi tương đối hiệu quả khi kích thước và tốc độ I/O của dữ liệu cho phép.

RDB **không** phải:

- Một event log chứa tất cả lệnh `SET`/`DEL` sau lần snapshot cuối.
- Một transaction log của ứng dụng.
- Một hệ thống ACK rằng nghiệp vụ đã được lưu bền vững xuyên mọi lỗi.
- Một backup an toàn nếu chỉ có duy nhất một tệp trên cùng ổ đĩa với Redis.
- Một phương án tự bảo vệ khỏi việc ứng dụng ghi/xóa sai dữ liệu rồi snapshot lại.
- Một cơ chế đồng bộ transaction giữa Redis và PostgreSQL, MySQL hoặc dịch vụ bên ngoài.

### 2.1. Snapshot không phải bản sao của từng request

Giả sử ứng dụng thực hiện:

```redis
SET cart:101:status OPEN
SET cart:101:status CHECKED_OUT
```

Nếu snapshot ở giữa hai lệnh, RDB có thể lưu `OPEN`; nếu snapshot sau lệnh thứ hai, nó có thể lưu `CHECKED_OUT`.

RDB lưu **trạng thái tại mốc snapshot**, không cần chứa cả hai lệnh trong file. Nếu một lệnh xảy ra sau mốc snapshot, nó không tự xuất hiện trong RDB trước khi snapshot tiếp theo được tạo.

### 2.2. RDB thường có tên dump.rdb

Một số cấu hình liên quan:

```conf
dbfilename dump.rdb
dir /var/lib/redis
```

Tệp được ghi ở thư mục Redis cấu hình. Tên và đường dẫn thực tế phụ thuộc container image, Redis distribution, managed service và cấu hình của môi trường.

Redis có thể có persistence khác như AOF cùng hoạt động. Đừng suy rằng `dump.rdb` là nguồn khôi phục duy nhất chỉ vì tệp đó tồn tại.

## 3. RDB snapshot phản ánh thời điểm nào?

Trọng tâm của RDB là **ảnh chụp nhất quán theo một mốc logic**. Khi Redis thực hiện `BGSAVE`, Redis thường tạo child process bằng cơ chế `fork` (trên hệ điều hành hỗ trợ), để child ghi snapshot trong khi parent tiếp tục xử lý lệnh của client.

```text
Trục thời gian
-------------------------------------------------------------------->

t0                    t1                  t2                t3
|                     |                   |                 |
BGSAVE bắt đầu        SET key=A           BGSAVE xong       crash
fork snapshot         SET key=B           RDB file mới      mất RAM
|                                         |
+------------------- child ghi RDB -------+
|
+------------------- parent tiếp tục nhận lệnh ---------------------->

RDB phản ánh trạng thái logic ở t0,
không tự ghi thêm các lệnh SET tại t1.
```

Điểm khó: **`LASTSAVE` thường thể hiện thời gian lần lưu thành công**, không nhất thiết chính là thời điểm trạng thái dữ liệu trong RDB được chụp. Nếu `BGSAVE` mất nhiều giây, có một khoảng thời gian giữa lúc bắt đầu và lúc hoàn tất ghi file.

Ví dụ cụ thể:

```text
10:00:00  Parent fork child để BGSAVE.
10:00:08  Ứng dụng ghi inventory:42 = 90.
10:00:19  Child hoàn tất RDB, Redis báo lưu thành công.
10:00:21  Redis crash, mất RAM.
10:01:00  Phục hồi từ RDB.

LASTSAVE có thể phản ánh khoảng 10:00:19.
Nhưng dữ liệu RDB được chụp ở khoảng 10:00:00.

Lệnh ghi lúc 10:00:08 có thể không được RDB đó chứa.
```

Đây là lý do **không được diễn giải `now - LASTSAVE` là giới hạn tuyệt đối của lượng dữ liệu có thể mất**. Một lần snapshot đang chạy hoặc mới hoàn thành có thể đại diện cho trạng thái cũ hơn thời điểm file hoàn tất.

### 3.1. Dữ liệu thay đổi trong khi BGSAVE có biến mất khỏi Redis đang chạy không?

Không. Parent vẫn tiếp nhận và áp dụng các lệnh trong RAM bình thường, tùy khả năng tài nguyên. Ví dụ:

```redis
SET cart:101:state CHECKED_OUT
GET cart:101:state
```

`GET` có thể trả `CHECKED_OUT` ngay sau khi `SET` được xử lý thành công. Nhưng child đang ghi snapshot dựa trên trạng thái tại lúc fork; phiên bản mới đó chưa chắc có trong tệp RDB đang được tạo.

Cần tách:

```text
Trạng thái live mà client đang đọc
    khác với
Trạng thái snapshot đang được ghi
```

### 3.2. RDB không liên tục đuổi theo trạng thái mới nhất

Child process không liên tục thêm mọi thay đổi phát sinh trong parent vào cùng snapshot. Redis có một thời điểm ảnh chụp logic để bảo đảm snapshot nhất quán. Các ghi tiếp theo cần một snapshot khác hoặc một cơ chế persistence bổ sung để được khôi phục sau crash.

## 4. BGSAVE hoạt động qua fork và copy-on-write

Hình dung cơ chế nền:

```text
Redis parent (đang phục vụ client)
         |
         | BGSAVE
         v
      fork()
         |
   +-----+----------------------------------+
   |                                        |
   v                                        v
Child process                           Parent process
ghi RDB dựa trên                        tiếp tục SET, GET,
ảnh chụp logic t0                       DEL, INCR, ...
   |                                        |
   | đọc các trang bộ nhớ                   | ghi thay đổi
   | cần ghi ra đĩa                         v
   |                                  Copy-on-write pages
   |                                        |
   +--> Tệp RDB tạm --> hoàn tất --> publish file RDB
```

Khi `fork` tạo child, parent và child ban đầu có thể chia sẻ nhiều trang bộ nhớ theo cơ chế quản lý của hệ điều hành. Khi parent sửa một trang sau fork, **copy-on-write** khiến hệ điều hành phải giữ bản cũ cho child và tạo/giữ bản mới cho parent.

Nhờ vậy, Redis tiếp tục xử lý client trong khi child tạo snapshot. Đổi lại, BGSAVE tiêu thụ thêm CPU, I/O, page tables và có thể tăng memory usage.

### 4.1. Vì sao BGSAVE có thể làm tăng RAM?

Một workload ghi rất nhiều trong lúc snapshot chạy có thể chạm vào nhiều trang bộ nhớ. Những trang bị thay đổi cần copy-on-write, làm tăng mức sử dụng bộ nhớ vật lý.

Ví dụ:

```text
Dữ liệu Redis trước BGSAVE       : 8 GiB
BGSAVE đang chạy                 : child cần ảnh chụp t0
Parent nhận lượng write lớn      : nhiều page bị thay đổi
Copy-on-write memory             : tăng thêm đáng kể
```

Không có công thức đơn giản “COW luôn bằng 10% RAM” hoặc “BGSAVE luôn cần gấp đôi RAM”. Mức tăng phụ thuộc pattern ghi, kích thước dataset, thời gian BGSAVE, allocator, OS và các biến động khác.

Cần có headroom về memory, nhất là trong container hoặc máy chủ dùng Redis làm data store quan trọng.

### 4.2. Fork có thể gây độ trễ ngắn trên parent

Tạo child bằng `fork` trên dataset lớn có thể tốn thời gian và gây độ trễ tạm thời cho Redis parent. Redis không cần khóa toàn bộ traffic trong suốt quá trình child ghi snapshot, nhưng **thời điểm fork** vẫn có overhead.

Nguy cơ lớn hơn khi:

- Dataset lớn.
- Máy thiếu RAM hoặc cài đặt memory overcommit không phù hợp.
- Có hàng triệu key.
- Disk quá chậm khiến snapshot chạy lâu.
- CPU bị tranh chấp với workload khác.
- Redis đang ở môi trường virtualization/container có giới hạn tài nguyên chặt.

BGSAVE giảm blocking so với `SAVE`, nhưng **không có nghĩa hoàn toàn miễn phí**.

### 4.3. Child ghi RDB theo cách nào?

Ở mô hình thông thường, Redis ghi RDB vào tệp tạm rồi thay thế tệp snapshot đích sau khi tạo thành công, nhằm tránh để tệp mới chưa hoàn chỉnh thay thế ngay bản RDB hợp lệ cũ.

Tuy nhiên, đây không phải lý do bỏ qua:

- Kiểm tra file RDB sau backup.
- Kiểm tra disk space.
- Quyền ghi thư mục persistence.
- Tình trạng filesystem.
- Kế hoạch backup độc lập ngoài host.
- Khả năng crash giữa những bước liên quan tới ổ đĩa/hệ điều hành.

Để có phục hồi đáng tin cậy, cần kiểm thử backup và restore thực tế, không chỉ tin rằng một lệnh `BGSAVE` đã trả success.

## 5. SAVE và BGSAVE khác nhau thế nào?

Redis có hai lệnh quan trọng:

```redis
SAVE
BGSAVE
```

| Khía cạnh | `SAVE` | `BGSAVE` |
|---|---|---|
| Cách thực hiện | Lưu snapshot theo cách đồng bộ | Tạo child/background save |
| Ảnh hưởng xử lý lệnh | Có thể chặn server trong lúc thực hiện | Parent thường tiếp tục phục vụ lệnh |
| Cơ chế fork | Không có mô hình child BGSAVE thông thường | Dựa trên fork/COW trong triển khai điển hình |
| Độ trễ | Có thể rất dài với dataset lớn | Có overhead fork, COW, I/O |
| Phù hợp vận hành | Chỉ trong tình huống có chủ đích, hiểu blocking | Phương án phổ biến cho snapshot runtime |
| Trả về | Khi lệnh hoàn tất/lỗi | Thường xác nhận background save đã được khởi động, không có nghĩa child đã xong |
| Cần theo dõi sau lệnh | Trạng thái file/restore | `INFO persistence`, `LASTSAVE`, log BGSAVE |

### 5.1. Vì sao không chạy SAVE thường xuyên trên production?

`SAVE` có thể chặn Redis khi dataset được lưu. Với hệ thống có nhiều request có latency thấp, tác động này có thể rất lớn.

Tránh dùng `SAVE` như một cách “chắc chắn dữ liệu đã bền vững” cho từng request Java. Nếu phải tạo snapshot runtime, thông thường cần cân nhắc `BGSAVE` cùng cơ chế giám sát hoàn thành.

### 5.2. BGSAVE trả OK chưa có nghĩa file đã cập nhật xong

Khi gọi:

```redis
BGSAVE
```

Redis có thể phản hồi rằng tác vụ save nền đã bắt đầu. Cần tiếp tục kiểm tra:

```redis
INFO persistence
LASTSAVE
```

hoặc log của Redis để biết quá trình đã thành công hay thất bại.

Một ứng dụng không nên gọi `BGSAVE` rồi lập tức tuyên bố rằng toàn bộ lệnh vừa ghi đã an toàn trước mất điện, bởi:

1. Snapshot chưa chắc đã xong.
2. Snapshot phản ánh thời điểm fork, không tự chứa những ghi sau mốc ấy.
3. Kết quả khôi phục còn phụ thuộc tính toàn vẹn của tệp và hệ thống lưu trữ.
4. Nếu AOF cũng bật, quy tắc khôi phục có thể khác với chỉ RDB.

### 5.3. Gọi BGSAVE khi một lần khác đang chạy

Redis không tạo vô hạn child snapshot song song cho mọi request. Khi có tác vụ background save đang chạy, lệnh hoặc scheduler cần tuân theo ràng buộc thực thi của Redis và các tùy chọn liên quan.

Vì vậy, **không nên biến mỗi request nghiệp vụ thành một lần BGSAVE**. Làm như vậy không tạo durability tức thì, mà dễ gây overhead fork/disk, tranh chấp memory và trạng thái snapshot phức tạp.

## 6. Quy tắc tự động `save` trong redis.conf

Redis hỗ trợ cấu hình tạo RDB theo điều kiện thời gian và số lần thay đổi dữ liệu.

Ví dụ:

```conf
save 900 1
save 300 10
save 60 10000
```

Cách đọc:

- Sau khoảng **900 giây**, nếu có ít nhất **1** thay đổi dữ liệu theo điều kiện lưu, Redis có thể bắt đầu snapshot.
- Sau khoảng **300 giây**, nếu có ít nhất **10** thay đổi, Redis có thể bắt đầu snapshot.
- Sau khoảng **60 giây**, nếu có ít nhất **10.000** thay đổi, Redis có thể bắt đầu snapshot.

Các dòng là **những điều kiện kích hoạt độc lập**; chỉ cần một điều kiện được thỏa mãn và Redis có điều kiện thực thi tác vụ thích hợp thì có thể khởi động snapshot. Đây là bộ giá trị **minh họa**, không nên mặc định nó là cấu hình hiện hành của mọi phiên bản Redis.

### 6.1. Cấu hình không phải “chụp đúng mỗi 60 giây”

Ví dụ chỉ có:

```conf
save 60 10000
```

Nếu trong 10 phút hệ thống mới có 9.999 thay đổi kể từ mốc liên quan, điều kiện 10.000 thay đổi chưa đạt. Không có lý do từ cấu hình này để kết luận Redis bắt buộc chụp snapshot cứ đúng mỗi 60 giây.

Ngược lại, nếu hệ thống có 100.000 write/s, điều kiện 10.000 thay đổi có thể đạt rất nhanh, nhưng vẫn có yếu tố thời gian, background save hiện tại, scheduling, resource availability và failure.

**`save <seconds> <changes>` là điều kiện kích hoạt dựa trên cả thời gian lẫn thay đổi, không phải hard real-time snapshot interval.**

### 6.2. Thời điểm hoàn tất không trùng thời điểm điều kiện được thỏa mãn

Ngay cả khi điều kiện cho phép khởi động `BGSAVE`, Redis còn phải fork và ghi toàn bộ ảnh chụp ra disk. Với dataset lớn, quá trình này có thể kéo dài.

Khoảng có nguy cơ mất dữ liệu khi crash không chỉ phụ thuộc chu kỳ cấu hình, mà còn phụ thuộc:

```text
- Mốc logic của snapshot cuối có thể restore được
- Các thay đổi sau mốc snapshot đó
- Thời gian ghi file và I/O
- Có snapshot mới đang chạy/thất bại không
- Các điều kiện kích hoạt được đáp ứng hay chưa
```

### 6.3. Xem cấu hình đang áp dụng

Trong môi trường có quyền:

```redis
CONFIG GET save
CONFIG GET dbfilename
CONFIG GET dir
```

Kết quả `CONFIG GET save` phản ánh các quy tắc hiện hành, có thể khác file cấu hình khởi động nếu administrator thay đổi runtime.

Nếu cần thay đổi, phải theo quy trình quản trị production. Một thay đổi `CONFIG SET` có thể không tồn tại sau restart nếu cấu hình không được persist theo cách môi trường hỗ trợ.

### 6.4. Tắt RDB tự động

Một cấu hình như:

```conf
save ""
```

tắt những quy tắc tự động tạo snapshot RDB trong cấu hình thông thường. Nó **không có nghĩa dữ liệu đã trở nên an toàn hơn**.

Nếu không có AOF hoặc backup khác, việc tắt RDB có thể khiến Redis khởi động lại mà không khôi phục được dữ liệu RAM trước đó. Trong một số hệ thống cache thuần, điều này có thể chấp nhận; trong hệ thống lưu state quan trọng, nó rất nguy hiểm.

Tắt auto-save cũng không nhất thiết ngăn mọi cách chủ động tạo RDB hoặc mọi hành vi liên quan replication. Phải kiểm tra cấu hình persistence tổng thể.

## 7. Khoảng dữ liệu có thể mất: RPO là gì?

**Recovery Point Objective (RPO)** mô tả lượng dữ liệu theo thời gian mà hệ thống đặt mục tiêu có thể chấp nhận mất khi xảy ra sự cố.

Nếu hệ thống cho phép RPO 5 phút, nghĩa là kiến trúc phải được thiết kế và kiểm chứng sao cho các tình huống lỗi trong phạm vi yêu cầu không khiến mất hơn khoảng dữ liệu mà mục tiêu đặt ra.

Đối với Redis chỉ dùng RDB, **RPO thực tế phụ thuộc snapshot cuối cùng có thể restore và thời điểm ảnh chụp của nó**. Cấu hình `save` không tự trở thành cam kết RPO cứng.

### 7.1. Công thức tư duy

Giả sử:

```text
T_snapshot = thời điểm logic mà RDB phục hồi phản ánh
T_failure  = thời điểm Redis mất trạng thái volatile
```

Thì khoảng thay đổi không có trong RDB có thể nằm trong:

```text
(T_snapshot, T_failure]
```

Độ dài cửa sổ:

```text
LossWindow ≈ T_failure - T_snapshot
```

Đây là mô hình trực quan về dữ liệu trong RDB. Không nên hiểu nó là tính toán chính xác mọi trường hợp khi có AOF, replication, failover, clock skew, shutdown save hoặc storage failure.

Điểm mạnh của mô hình là buộc bạn xác định **mốc snapshot thực sự**, thay vì nhìn mỗi lúc file ghi xong.

### 7.2. Ví dụ RPO theo dòng thời gian

```text
10:00:00  BGSAVE #1 fork
10:00:20  BGSAVE #1 hoàn thành thành công
10:00:30  SET user:1 updated
10:01:15  DEL key:old
10:02:00  INCR counter:orders
10:03:00  Redis crash; chỉ có RDB #1 hợp lệ
```

Khi restart từ RDB #1:

- `user:1` có thể quay về phiên bản lúc 10:00:00.
- `key:old` có thể **xuất hiện trở lại** nếu nó tồn tại trong snapshot trước khi bị `DEL`.
- `counter:orders` có thể **giảm** so với giá trị cuối cùng người dùng từng quan sát.
- Các key tạo mới sau 10:00:00 có thể không tồn tại.
- Các thay đổi TTL sau 10:00:00 có thể không được khôi phục.

Vì snapshot phản ánh trạng thái ở khoảng 10:00:00, cửa sổ logic có thể xấp xỉ 3 phút, **không chỉ 2 phút 40 giây kể từ lúc BGSAVE hoàn thành**.

### 7.3. RPO phải tính cả write, update và delete

Nhiều người hình dung “mất dữ liệu” chỉ là mất key mới. Trên thực tế, restore snapshot cũ có thể gây:

| Thao tác sau snapshot | Trạng thái có thể thấy sau restore |
|---|---|
| `SET new:key value` | Key mới biến mất |
| `SET existing:key newValue` | Value quay về phiên bản cũ |
| `HSET user:1 status ACTIVE` | Hash field trở lại trạng thái cũ |
| `INCR counter` | Counter quay lùi |
| `LPUSH queue item` | Item mới không có |
| `XADD stream * ...` | Stream entry mới biến mất |
| `DEL sensitive:key` | Key bị xóa **có thể xuất hiện lại** |
| `EXPIRE session:key 300` | TTL thay đổi sau snapshot không được bảo toàn |
| `PERSIST key` | Deadline cũ có thể quay lại |
| `SADD membership item` | Thành viên mới có thể biến mất |
| `SREM membership item` | Thành viên đã xóa có thể quay lại |

Đặc biệt, **delete rollback** rất quan trọng với token, session, quyền truy cập và danh sách thu hồi. Nếu ứng dụng coi Redis là nguồn duy nhất xác nhận một token đã bị vô hiệu hóa, phục hồi snapshot cũ có thể khôi phục trạng thái mà nghiệp vụ tưởng đã xóa.

### 7.4. Không có hard bound chỉ từ `save`

Ngay cả nếu đặt:

```conf
save 60 1
```

cũng không nên tuyên bố “tối đa mất đúng 60 giây dữ liệu trong mọi sự cố” vì:

- Thời điểm bắt đầu snapshot và hoàn tất có thể khác.
- Redis có thể đang chạy background save khác.
- Fork hoặc ghi RDB có thể thất bại.
- Disk có thể đầy hoặc lỗi.
- Process có thể crash đúng lúc snapshot đang tạo.
- Snapshot mới có thể không tồn tại sau storage/system failure.
- Cấu hình save là điều kiện kích hoạt, không phải một commit protocol với client.
- Mô hình persistence/replication/restore có thể thay đổi thời điểm recover thực tế.

Một **RPO mục tiêu** cần gắn với kiểm thử fault injection, monitoring, backup strategy và mức độ bảo đảm của storage.

## 8. RPO và RTO là hai mục tiêu khác nhau

**RTO (Recovery Time Objective)** là mục tiêu thời gian khôi phục dịch vụ hoạt động sau sự cố.

RDB ảnh hưởng cả hai:

- **RPO:** snapshot phản ánh trạng thái cũ tới đâu?
- **RTO:** mất bao lâu để tìm snapshot, tải tệp, khởi động Redis, làm nóng cache và cho ứng dụng chạy lại?

Ví dụ:

```text
Snapshot cuối cùng phản ánh dữ liệu từ 10:00.
Redis crash lúc 10:04.
Redis khởi động lại và phục vụ request lúc 10:07.
```

Mô tả khái niệm:

```text
Khoảng dữ liệu có thể mất ≈ 4 phút  (RPO thực tế của sự cố)
Thời gian ngừng phục vụ   ≈ 3 phút  (recovery time thực tế)
```

Hai đại lượng khác nhau. Snapshot rất thường xuyên có thể giảm mức thay đổi chưa được lưu, nhưng nếu tệp rất lớn và việc restore chậm, RTO vẫn có thể dài.

### 8.1. Redis phục hồi từ RAM, RDB hay nơi khác?

Khi process vừa crash, RAM của process không còn là nguồn bền vững. Redis khởi động lại có thể:

- Tải RDB nếu cơ chế đó được bật và file phù hợp.
- Tải AOF nếu AOF được bật và được Redis chọn làm nguồn phục hồi.
- Khởi động với dữ liệu rỗng nếu không có persistence hợp lệ.
- Nhận dữ liệu từ primary khác nếu instance khởi động như replica và đồng bộ theo cơ chế replication.
- Được thay thế bởi replica khác khi Sentinel/Cluster failover.

Muốn đo RPO/RTO đúng phải xác định **đường khôi phục thực tế của deployment**, không chỉ một tên tệp trong filesystem.

## 9. Cấu hình RDB thông dụng

Một cấu hình Redis minh họa:

```conf
# Tạo RDB khi điều kiện save được đáp ứng.
save 900 1
save 300 10
save 60 10000

# Tên tệp và thư mục persistence.
dbfilename dump.rdb
dir /var/lib/redis

# Nén RDB khi phù hợp.
rdbcompression yes

# Kiểm tra checksum cho RDB.
rdbchecksum yes

# Cách phản ứng khi background save lỗi.
stop-writes-on-bgsave-error yes
```

Đây là ví dụ cấu hình, không phải câu lệnh bắt buộc áp dụng và không khẳng định các giá trị tương đương default của mọi Redis version/distribution.

### 9.1. `rdbcompression`

RDB có thể sử dụng nén để giảm kích thước tệp. Điều này có thể đổi CPU lấy disk space và I/O. Tác động thực tế phụ thuộc data types, độ lặp dữ liệu, độ lớn payload và môi trường storage.

Không nên giả định RDB luôn nhỏ hơn dữ liệu RAM theo một tỷ lệ cố định. Dung lượng snapshot cần được đo trên workload thật.

### 9.2. `rdbchecksum`

Checksum giúp phát hiện một số lỗi/corruption trong tệp RDB khi kiểm tra/đọc. Checksum không thay thế:

- Backup ngoài host.
- Redundancy của storage.
- Giám sát disk.
- Test restore.
- Phân quyền và mã hóa dữ liệu nhạy cảm.
- Khả năng chống ransomware/human error.

Một tệp có checksum hợp lệ vẫn có thể chứa **trạng thái cũ nhưng hoàn toàn đúng về mặt định dạng**.

### 9.3. `stop-writes-on-bgsave-error`

Khi background save thất bại và Redis được cấu hình theo hướng bảo vệ dữ liệu, server có thể từ chối các lệnh ghi để tránh tiếp tục nhận write trong khi không có khả năng tạo snapshot đáng tin cậy.

Tình huống:

```text
BGSAVE thất bại vì disk full.
    |
    +--> Redis log lỗi persistence.
    |
    +--> Nếu stop-writes-on-bgsave-error được bật:
             một số lệnh write có thể bị từ chối
             thay vì âm thầm tiếp tục nhận dữ liệu.
```

Đây là một **cơ chế phát hiện/bảo vệ vận hành**, không phải bảo đảm dữ liệu chưa snapshot được lưu lại. Khi ứng dụng nhận lỗi write, cần xử lý như lỗi thật; không được giả định `SET` luôn thành công vì Redis vẫn trả lời `PING`.

Tắt tính năng này có thể phù hợp trong một số hệ thống chấp nhận mất dữ liệu và ưu tiên availability, nhưng phải là quyết định vận hành có hiểu RPO, không phải cách “sửa” lỗi disk full.

### 9.4. Disk space và quyền ghi thư mục

Nếu Redis không thể ghi thư mục `dir`:

- BGSAVE có thể thất bại.
- RDB mới không được tạo.
- `LASTSAVE` có thể dừng cập nhật.
- Một số lệnh ghi có thể bị từ chối tùy cấu hình.
- Ứng dụng Spring có thể quan sát exception từ Redis commands.
- Khi restart, hệ thống chỉ có thể dùng snapshot cũ hoặc không có snapshot hợp lệ.

Do đó, cần giám sát **tình trạng snapshot thành công**, không chỉ mức dùng RAM Redis.

## 10. Quan sát trạng thái RDB bằng redis-cli

Những lệnh thường dùng:

```redis
INFO persistence
LASTSAVE
CONFIG GET save
CONFIG GET dbfilename
CONFIG GET dir
```

Để đọc một nhóm chỉ số, có thể chạy:

```bash
redis-cli INFO persistence
```

Một số trường thường gặp trong `INFO persistence`:

| Trường | Cách hiểu |
|---|---|
| `rdb_bgsave_in_progress` | Có background RDB save đang chạy hay không |
| `rdb_last_save_time` | Thời gian Unix của lần RDB save thành công gần nhất theo thông tin Redis |
| `rdb_changes_since_last_save` | Số thay đổi được tính để theo dõi snapshot kể từ lần lưu gần đây theo Redis |
| `rdb_last_bgsave_status` | Kết quả lần background save gần nhất, ví dụ `ok` hoặc `err` |
| `rdb_last_bgsave_time_sec` | Thời gian chạy lần BGSAVE trước theo đơn vị giây |
| `rdb_current_bgsave_time_sec` | Thời gian BGSAVE hiện tại đã chạy, khi có |
| `rdb_last_cow_size` | Dung lượng copy-on-write ước tính/ghi nhận cho lần BGSAVE gần nhất |
| `rdb_saves` | Số lần RDB save được ghi nhận theo phiên bản hỗ trợ |
| Các trường AOF | Thể hiện tình trạng AOF nếu được bật |

Tên trường có thể khác theo Redis version và cách nhà cung cấp xuất metrics. Hãy xem thông tin thực tế từ Redis đang dùng.

### 10.1. Ví dụ diễn giải

Giả sử:

```text
rdb_bgsave_in_progress:0
rdb_last_bgsave_status:ok
rdb_last_save_time:1893456000
rdb_changes_since_last_save:15230
```

Ý nghĩa có thể rút ra:

- Không có BGSAVE đang chạy tại thời điểm quan sát.
- Lần BGSAVE được ghi nhận gần nhất thành công.
- Có một timestamp lưu thành công.
- Đã có lượng thay đổi kể từ mốc lưu mà Redis thống kê.

Nhưng **không thể suy ra chắc chắn**:

- Mọi write trước `rdb_last_save_time` đều nằm trong snapshot.
- Không có write nào có thể mất khi crash ngay lúc này.
- RDB đã được backup ngoài host.
- Tệp trên disk không bị corruption.
- 15.230 thay đổi tương đương 15.230 key hoặc 15.230 transaction nghiệp vụ.

`rdb_changes_since_last_save` là chỉ số hoạt động phục vụ persistence; nó không phải phép đếm chính xác số bản ghi nghiệp vụ có thể mất.

### 10.2. Sử dụng LASTSAVE

```redis
LASTSAVE
```

Trả một Unix timestamp biểu diễn thời điểm save thành công gần nhất theo Redis.

Ví dụ:

```text
1893456000
```

Có thể chuyển timestamp thành thời gian người đọc hiểu được bằng công cụ theo timezone phù hợp. Nhưng phải nhớ:

> **LASTSAVE là mốc hoàn thành/lưu thành công, không nhất thiết là mốc dữ liệu logic tại lúc BGSAVE fork.**

Khi tính khoảng mất dữ liệu, nếu chỉ có LASTSAVE mà không có thời điểm bắt đầu của snapshot thì kết luận sẽ có sai số. Có thể kết hợp logs Redis, lịch sử BGSAVE duration và metric để ước lượng có cơ sở hơn.

### 10.3. Giám sát tiến trình snapshot

Ví dụ:

```redis
BGSAVE
INFO persistence
```

Nếu `rdb_bgsave_in_progress:1`, snapshot vẫn đang được tạo. Đợi tác vụ hoàn tất và kiểm tra `rdb_last_bgsave_status`. Không nên tạo vòng polling quá dày hoặc liên tục gọi BGSAVE trong production.

Trong môi trường cần đảm bảo backup đúng mốc, quy trình phải xử lý cả trường hợp BGSAVE không bắt đầu hoặc fail.

## 11. Khi crash xảy ra giữa BGSAVE thì sao?

Giả sử:

```text
T0: RDB #1 đã có và hợp lệ.
T1: Redis bắt đầu BGSAVE #2.
T2: Parent ghi thêm nhiều dữ liệu mới.
T3: Máy chủ crash trước khi BGSAVE #2 hoàn tất.
```

Trong cơ chế bình thường, RDB #2 chưa hoàn chỉnh không trở thành một snapshot hoàn tất để restore. Redis có thể phải khôi phục từ **RDB #1**, khiến khoảng dữ liệu mất dài hơn dự đoán theo lúc BGSAVE #2 bắt đầu.

Minh họa:

```text
10:00   RDB #1 hoàn tất, trạng thái chụp khoảng 09:59:45
10:05   BGSAVE #2 bắt đầu
10:05+  Hàng nghìn write thành công trong RAM
10:06   Redis crash trước khi RDB #2 hoàn tất
10:07   Redis restore từ RDB #1
```

Dữ liệu thay đổi sau mốc ảnh chụp của #1 có thể mất, **không chỉ thay đổi sau 10:05**.

### 11.1. Nếu BGSAVE thất bại liên tục

Giả sử disk đầy từ 10:00 đến 11:00. Dù cấu hình:

```conf
save 60 1
```

vẫn không tạo được snapshot mới. Nếu ứng dụng tiếp tục ghi do cấu hình cho phép, cửa sổ dữ liệu chưa được lưu có thể tăng rất dài.

Vì vậy monitoring cần phát hiện:

```text
Thời gian kể từ lần save thành công đang tăng.
rdb_last_bgsave_status = err.
Disk free space thấp.
Redis write traffic vẫn tiếp tục.
```

Trong một hệ thống RDB-only có RPO chặt, đây là cảnh báo cấp cao, không chỉ log thông tin.

### 11.2. Storage failure khác process crash

Một process Redis crash nhưng ổ đĩa vẫn còn dữ liệu RDB là một nhóm sự cố. Mất toàn bộ disk/host, lỗi filesystem hoặc corruption là nhóm khác.

Nếu backup chỉ nằm ở cùng ổ đĩa đã hỏng, không có snapshot nào để phục hồi. Do đó, **RDB persistence** và **backup độc lập** phải được phân biệt rõ.

## 12. Tình huống mất dữ liệu sau khi key đã bị xóa

Đây là một rủi ro đáng chú ý khi dùng Redis chứa dữ liệu bảo mật hoặc trạng thái nghiệp vụ.

Giả sử snapshot lưu:

```text
session:token-42 = ACTIVE
```

Sau đó ứng dụng vô hiệu hóa session:

```redis
DEL session:token-42
```

Redis trả thành công và mọi `GET` sau lệnh xóa trên instance live trả `nil`. Tuy nhiên, nếu chưa có snapshot mới và Redis crash:

```text
Restore từ RDB cũ
    |
    v
session:token-42 = ACTIVE
```

Key có thể **quay trở lại**.

### 12.1. Vì sao đây không chỉ là lỗi cache?

Nếu Redis là cache của database và hệ thống xác thực luôn kiểm tra session revocation ở nguồn bền vững, key cũ có thể không gây sai lệch bảo mật nghiêm trọng nếu các lớp kiểm tra được thiết kế đúng.

Nhưng nếu Redis là nguồn dữ liệu duy nhất quyết định token có còn hiệu lực, mất lệnh `DEL` có thể làm phiên bị thu hồi sống lại sau restart.

Với logout, quyền truy cập, khóa tài nguyên, số dư hoặc quyền sử dụng có hậu quả, cần chọn storage/consistency strategy thích hợp. RDB-only với các snapshot cách quãng không tự là lựa chọn đủ mạnh.

### 12.2. TTL có giải quyết hoàn toàn vấn đề không?

RDB lưu thông tin deadline của key theo cơ chế của Redis. Khi restore, Redis đánh giá thời hạn dựa trên thời gian hiện tại; những key đã quá deadline có thể bị loại khi load hoặc khi truy cập theo cơ chế expiration.

Nhưng một key bị `DEL` sau snapshot **có thể vẫn còn deadline trong tương lai** trong bản RDB cũ, nên việc restore vẫn có thể làm nó xuất hiện trở lại cho tới khi hết hạn.

TTL giúp giới hạn thời gian sống, **không bảo đảm lệnh xóa mới nhất đã được snapshot**.

## 13. RDB và TTL khi restore

Một snapshot Redis không nên hiểu là “đóng băng thời gian TTL” rồi cho key tiếp tục sống từ thời điểm restore.

Ví dụ:

```text
10:00  SET otp:123 value EX 300
10:01  Snapshot chụp OTP còn hạn
10:15  Redis khởi động lại từ RDB của 10:01
```

Đến 10:15, deadline 5 phút từ 10:00 đã qua. Key OTP không nên được cấp thêm 5 phút chỉ vì Redis mới khởi động lại. Redis lưu expiration metadata theo deadline, nên các key đã hết hạn theo đồng hồ hiện tại có thể bị bỏ qua/xóa trong quá trình load hoặc khi được kiểm tra.

Cần nhớ:

- Restore snapshot không đồng nghĩa gia hạn mọi TTL về giá trị ban đầu.
- Key quá deadline có thể không hiện diện sau restore.
- Nếu ứng dụng thay đổi TTL sau snapshot, thay đổi đó có thể mất.
- Chênh lệch đồng hồ hệ thống có thể ảnh hưởng hành vi expiration.
- `PERSIST` sau snapshot có thể bị mất, làm TTL cũ xuất hiện lại.
- Key bị `DEL` sau snapshot có thể được phục hồi nếu snapshot trước đó vẫn chứa nó và deadline chưa qua.

### 13.1. Đồng hồ hệ thống ảnh hưởng dữ liệu như thế nào?

Redis expiration dựa trên mốc thời gian. Nếu hệ thống có vấn đề clock skew hoặc cấu hình thời gian bất thường khi chuyển snapshot giữa máy, dữ liệu có thể hết hạn sớm/muộn so với kỳ vọng.

Nên đồng bộ đồng hồ vận hành, đặc biệt khi backup/restore qua môi trường khác hoặc khi ứng dụng dùng deadline cho token/session/lease.

### 13.2. Spring Data Redis @TimeToLive

Một Redis Repository có thể sử dụng `@TimeToLive` hoặc `@RedisHash(timeToLive = ...)` để gắn TTL cho entity. Cơ chế RDB lưu thông tin key và expiry metadata như những Redis keys khác.

Nhưng `@TimeToLive` **không làm tăng tần suất snapshot** và không bảo đảm method `repository.save(...)` đã được ghi bền vững lên disk. Nó chỉ điều khiển TTL theo khả năng Spring Data Redis Repository.

## 14. RDB và Spring Data Redis: ý nghĩa của một lệnh SET thành công

Ví dụ service đơn giản:

```java
package com.example.session;

import java.time.Duration;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class SessionCache {

    private final StringRedisTemplate redis;

    public SessionCache(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void save(String sessionId, String userId) {
        redis.opsForValue().set(
            "session:" + sessionId,
            userId,
            Duration.ofMinutes(30)
        );
    }

    public String get(String sessionId) {
        return redis.opsForValue().get(
            "session:" + sessionId
        );
    }
}
```

Khi `save` trả về bình thường, ứng dụng biết lời gọi Redis ở mức API đã hoàn tất mà không báo lỗi theo đường call đó. Điều này **không chứng minh**:

- Redis vừa tạo xong RDB mới.
- RDB đang chứa key này.
- Tệp đã được backup tới nơi độc lập.
- Replica khác chắc chắn đã nhận lệnh.
- Một transaction database liên quan đã commit.
- Dữ liệu không thể mất trong một crash/failover.

`StringRedisTemplate` chỉ là client thao tác Redis. Tính bền vững phụ thuộc cấu hình Redis và hạ tầng persistence.

### 14.1. Reactive Redis cũng có giới hạn tương tự

Ví dụ:

```java
public Mono<Boolean> save(String key, String value) {
    return reactiveStringRedisTemplate
        .opsForValue()
        .set(key, value, Duration.ofMinutes(5));
}
```

Khi `Mono` phát kết quả thành công, lệnh Redis đã hoàn tất theo contract của client. Nhưng `Mono` thành công **không phải bằng chứng một RDB snapshot mới có chứa write đó**.

Reactive vs blocking là quyết định về mô hình I/O, **không phải mức bảo đảm durability**.

### 14.2. `@Cacheable` không làm cache bền vững hơn

Ví dụ:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public ProductDto findProduct(String productId) {
    return repository.findProduct(productId);
}
```

Spring Cache có thể dùng `RedisCacheManager`. Nếu Redis crash và phục hồi từ snapshot cũ, cache có thể mất những entry mới hoặc hồi sinh entry cũ. Điều này thường có thể chấp nhận vì cache được tái tạo từ nguồn dữ liệu gốc.

Nhưng nếu ứng dụng **ghi dữ liệu nghiệp vụ duy nhất vào cache** rồi không có nguồn bền vững khác, việc dùng annotation cache và RDB-only tạo rủi ro mất dữ liệu khó kiểm soát.

### 14.3. RDB và serializer là hai vấn đề khác nhau

`RedisTemplate` có thể ghi Java String, JSON hoặc binary object. RDB lưu dữ liệu Redis ở dạng Redis internal structures cùng metadata cần thiết, không tự biết Java class của ứng dụng.

Nếu thay serializer giữa trước và sau restore:

```text
Trước crash: Spring ghi JSON bằng serializer A
Sau restore: Spring đọc bằng serializer B
```

ứng dụng có thể không giải mã được dù dữ liệu đã được RDB phục hồi nguyên vẹn.

Vì vậy, **khôi phục thành công Redis process** chưa chắc đồng nghĩa **ứng dụng đọc được dữ liệu nghiệp vụ**. Cần kiểm thử cả serializer, schema và version của code Spring Data Redis.

## 15. Chọn durability theo loại dữ liệu

Không phải mọi key Redis đều cần cùng mức bảo vệ.

| Loại dữ liệu | Nếu mất phần ghi sau snapshot | Mức chấp nhận thường gặp |
|---|---|---|
| Cache của dữ liệu PostgreSQL | Cache miss, phải tải lại | Có thể chấp nhận nếu nguồn gốc còn đầy đủ |
| Cache kết quả API tốn kém | Tăng latency/tải nguồn sau restart | Phụ thuộc chi phí tái tạo |
| Session tạm | Người dùng có thể phải đăng nhập lại | Tùy sản phẩm, yêu cầu bảo mật |
| OTP ngắn hạn | OTP vừa tạo có thể mất, user phải yêu cầu lại | Cần đảm bảo chính sách xác thực đúng |
| Rate limit counter | Counter có thể quay lùi sau restore | Rủi ro lạm dụng nếu là lớp bảo vệ duy nhất |
| Inventory reservation | Có thể mất hoặc hồi sinh reservation | Thường cần nguồn giao dịch bền vững |
| Payment ledger | Mất hoặc đảo ngược số dư/giao dịch | RDB-only thường không phù hợp làm nguồn duy nhất |
| Redis Stream queue | Entry mới hoặc trạng thái ACK có thể quay lùi | Cần đánh giá durability/replication/idempotency |
| Feature flags | Flag mới có thể mất, flag cũ quay lại | Phụ thuộc quy trình vận hành |
| Distributed lock | Khóa có thể mất hoặc hồi sinh sau restore | Không dùng RDB làm chứng nhận an toàn của lock |
| Token revocation | Lệnh thu hồi có thể mất | Rủi ro bảo mật, cần biện pháp bổ sung |

Bảng mô tả rủi ro thiết kế, không thay thế việc đánh giá SLA và security requirements thực tế.

### 15.1. Nếu Redis chỉ là cache

Khi Redis có thể mất toàn bộ dữ liệu mà ứng dụng vẫn phục vụ đúng nghiệp vụ sau khi tải lại từ nguồn, RDB có thể được chọn vì:

- Tăng tốc khởi động sau restart.
- Giảm đợt cache miss sau sự cố.
- Giảm tải database khi phục hồi.
- Không cần log từng mutation để duy trì một bản cache có thể tái tạo.

Nhưng vẫn phải tính hiện tượng **cache stampede** khi nhiều key không có trong snapshot, nhất là sau restart cả cluster.

### 15.2. Nếu Redis là source of truth

Khi dữ liệu chỉ tồn tại trong Redis, phải đánh giá:

- Mức dữ liệu mất tối đa chấp nhận được.
- Có thể xác nhận write đã được ghi xuống storage trước khi trả thành công không.
- Có cơ chế replication/failover đến đâu.
- Có snapshot backup ngoài host không.
- Có AOF hay persistence khác không.
- Recovery từ snapshot cũ có thể làm vi phạm invariant hay không.
- Tác động của missing, rollback và resurrected keys.
- Các yêu cầu audit, pháp lý, kế toán, bảo mật.

Không nên mặc định “đã bật RDB” nghĩa là Redis đủ điều kiện làm hệ thống ghi sổ cho mọi nghiệp vụ.

## 16. RDB và AOF: hai cách lưu khác nhau

Redis còn có **AOF (Append Only File)** để ghi lại các thao tác thay đổi dữ liệu theo cơ chế persistence của Redis.

Hình dung:

```text
RDB:
    t0 snapshot  -> [ảnh chụp đầy đủ của state tại t0]
    t1 writes    -> chưa có trong RDB t0
    t2 crash     -> restore state t0

AOF:
    SET a 1      -> append theo cơ chế AOF
    INCR b       -> append
    DEL c        -> append
    ...
    crash        -> replay dữ liệu AOF có thể phục hồi
```

### 16.1. So sánh RDB và AOF

| Tiêu chí | RDB | AOF |
|---|---|---|
| Dữ liệu được ghi | Ảnh chụp trạng thái tại mốc logic | Nhật ký/biểu diễn các thay đổi để replay |
| Kích hoạt | `save` rules, `BGSAVE`, thao tác quản trị | Theo thao tác ghi và cấu hình AOF |
| RPO thường kỳ vọng | Có thể mất các thay đổi sau snapshot cuối | Có thể giảm cửa sổ mất dữ liệu tùy `appendfsync` |
| Kích thước/chi phí | Snapshot thường gọn cho nhiều workload | Có overhead append và rewrite |
| Recovery | Tải ảnh chụp | Nạp/replay AOF theo cấu trúc và version |
| Ảnh hưởng hiệu năng | Fork/COW và I/O khi snapshot | I/O thường xuyên, fsync/rewrite |
| Cấu hình quan trọng | `save`, `dbfilename`, `dir` | `appendonly`, `appendfsync`, rewrite |
| Ngữ nghĩa một write thành công | Không đồng nghĩa snapshot chứa write | Phụ thuộc chính sách flush/fsync và hệ thống lưu trữ |
| Tình huống thường dùng | Backup, restart nhanh từ snapshot, cache | Khi cần hạn chế cửa sổ dữ liệu mất |

Bảng là khái niệm. Redis có khả năng dùng cả RDB và AOF; cách ghi/restore phụ thuộc Redis version.

### 16.2. appendfsync always, everysec và no

Ví dụ cấu hình:

```conf
appendonly yes
appendfsync everysec
```

Một số lựa chọn AOF:

- `always`: cố gắng đồng bộ dữ liệu xuống hệ thống lưu trữ thường xuyên hơn, có chi phí latency/throughput cao hơn.
- `everysec`: thường được dùng để cân bằng hiệu năng và durability, có thể mất dữ liệu khoảng một giây trong một số failure scenario, **không phải bảo đảm cứng đúng tối đa một giây trong mọi trường hợp**.
- `no`: dựa nhiều hơn vào lịch flush của hệ điều hành, có thể tăng cửa sổ mất dữ liệu.

Không nên chuyển một nhận định phổ biến “everysec mất tối đa khoảng 1 giây” thành SLA pháp lý/kế toán mà không kiểm thử phần cứng, OS, Redis version và quy trình failover/restore.

### 16.3. Bật cả RDB và AOF

Redis có thể có cả RDB snapshot và AOF. Khi cả hai được bật, Redis thường ưu tiên nguồn khôi phục AOF phù hợp vì nó có thể phản ánh dữ liệu mới hơn RDB, nhưng hành vi cụ thể phụ thuộc version và trạng thái persistence.

Redis 7 có mô hình multi-part AOF và những cấu hình phục vụ rewrite/manifest; không nên giả định chỉ có một file `appendonly.aof` phẳng ở mọi triển khai.

Do đó, để đánh giá data-loss window thật, cần hỏi:

```text
RDB đang bật không?
AOF đang bật không?
appendfsync theo policy nào?
Có replica/failover không?
Tệp persistence nằm ở storage nào?
Khởi động lại thực sự đã tải nguồn nào?
```

**Không suy từ tên file `dump.rdb` tồn tại rằng hệ thống đang restore từ RDB.**

## 17. RDB và replication/failover

**Persistence** và **replication** giải quyết những rủi ro khác nhau:

- Persistence cố gắng giữ dữ liệu khi instance khởi động lại.
- Replication sao chép trạng thái/thao tác từ primary tới replica để có nhiều bản sao.
- Sentinel/Redis Cluster có thể hỗ trợ tự động chọn replica thay primary khi lỗi.
- Backup giữ bản sao độc lập để khôi phục sau lỗi dữ liệu hoặc mất cả hệ thống.

Redis replication thông thường là **bất đồng bộ**. Một primary có thể trả kết quả ghi thành công cho client trước khi mọi replica nhận được lệnh ấy.

Ví dụ:

```text
t0: Primary xử lý SET counter 100.
t1: Primary trả OK cho Spring client.
t2: Primary chết trước khi replica nhận write đó.
t3: Replica thiếu write được promote.

Kết quả: giá trị cuối client đã thấy có thể không có trên primary mới.
```

Điều này có thể xảy ra dù RDB/AOF cấu hình một cách nào đó. Phải phân tích topology và khả năng đảm bảo của toàn hệ thống.

### 17.1. WAIT không phải fsync disk mặc định

Redis có lệnh `WAIT` để chờ một số replica xác nhận đã nhận các write trước đó theo cơ chế replication.

Nhưng `WAIT` **không biến Redis thành hệ thống consensus có exactly-once commit**, cũng không mặc nhiên chứng minh write đã được fsync bền vững trên tất cả replica.

Một số Redis version có `WAITAOF` cho những khả năng chờ AOF persistence theo điều kiện cụ thể; cần xem version, cấu hình và giới hạn bảo đảm thực tế. Không nên dùng một lệnh phụ như `WAIT` như lời cam kết tuyệt đối rằng không thể mất dữ liệu.

### 17.2. Một replica có RDB mới hơn primary cũ?

Trong hệ thống có replica, từng node có quá trình persistence riêng và dữ liệu được đồng bộ theo replication state. Khi failover hoặc restart, đường khôi phục có thể liên quan tới replica đang giữ trạng thái mới hơn snapshot cũ trên một primary.

Tuy vậy, điều này không phải bảo đảm rằng toàn bộ client-acknowledged writes đều tồn tại. Các tình huống partition, async replication lag và thời điểm failover vẫn có thể gây mất dữ liệu được thấy là thành công.

### 17.3. Redis Cluster có nhiều tập RDB

Redis Cluster có nhiều primary phụ trách những slot khác nhau. Backup RDB của một node **không phải ảnh chụp toàn bộ cluster**.

Nếu ứng dụng cập nhật dữ liệu trên các slot khác nhau, từng node có thể tạo snapshot ở các mốc khác nhau:

```text
Primary A: RDB tại T1
Primary B: RDB tại T2
Primary C: RDB tại T3
```

Khôi phục từ ba snapshot đó có thể cho một hệ thống tổng hợp trạng thái thuộc **nhiều thời điểm logic**. Redis Cluster không tự tạo một snapshot transactionally consistent toàn cục chỉ bằng cách bật RDB trên từng node.

Nếu nghiệp vụ cần point-in-time recovery nhất quán qua nhiều shard, cần kiến trúc backup/restore và source-of-truth được thiết kế riêng.

## 18. Redis Streams và pending state có bị ảnh hưởng khi restore RDB không?

Có. Redis Streams cũng là dữ liệu Redis; thông tin Stream, consumer group và trạng thái pending được thể hiện trong dữ liệu phục hồi theo khả năng và phiên bản.

Giả sử:

```text
10:00 Snapshot có Stream entry E1, group đã nhận E1 (pending).
10:01 Worker xử lý E1 thành công và gọi XACK.
10:02 Redis crash.
10:03 Restore snapshot 10:00.
```

Sau restore, trạng thái có thể thể hiện E1 **vẫn pending** theo snapshot cũ, dù nghiệp vụ xử lý bên ngoài Redis đã hoàn thành trước crash.

Recovery worker có thể claim và xử lý E1 thêm lần nữa. Đây là một dạng rollback trạng thái ACK do RDB cũ.

Tình huống ngược:

```text
10:00 Snapshot có Stream đến E1.
10:01 Producer XADD E2.
10:02 Worker xử lý E2 và ghi vào database.
10:03 Redis crash.
10:04 Restore snapshot 10:00.
```

E2 có thể không còn trong Redis Stream mặc dù database đã có kết quả của E2. Tùy hệ thống, cần nguồn bền vững hoặc outbox/reconciliation để giải quyết sự lệch này.

### 18.1. XACK không có nghĩa dữ liệu đã được snapshot

`XACK` xóa trạng thái pending của group tại Redis live. Nếu Redis chỉ có RDB cũ, lần phục hồi có thể quay lại PEL trước ACK.

Do đó, idempotent consumer là yêu cầu quan trọng không chỉ vì crash **giữa business commit và ACK**, mà còn vì **persistence rollback** khi Redis phục hồi từ mốc cũ.

### 18.2. RDB-only không thay thế message broker durability

Nếu Redis Streams là hệ thống giao việc quan trọng, cần thiết kế:

- Persistence phù hợp, có thể kết hợp AOF.
- Replication và failover với hiểu biết về async semantics.
- Transactional outbox ở nguồn business data khi cần.
- Idempotency key.
- Retention đủ dài.
- Pending recovery.
- DLQ và reconciliation.

Không nên coi “có Stream ID và XACK” là bảo đảm mọi message client đã nhận đều sống sót qua mất toàn bộ trạng thái RAM nếu persistence không đáp ứng.

## 19. RDB và distributed lock

Một lock Redis thường dùng:

```redis
SET lock:resource:42 unique-token NX PX 30000
```

Redis trả thành công khi lock được tạo trên instance live, nhưng nếu Redis mất RAM và restore từ snapshot cũ, trạng thái lock có thể:

- **Biến mất:** lock được tạo sau snapshot không còn.
- **Xuất hiện lại:** lock đã được xóa sau snapshot nhưng tồn tại trong RDB cũ, nếu deadline chưa qua.
- **Có deadline không còn phù hợp:** do thông tin TTL được khôi phục theo mốc cũ.

Trong một số trường hợp, việc mất lock có thể khiến hai worker cùng nghĩ họ sở hữu quyền xử lý một tài nguyên.

Nếu lock bảo vệ tài nguyên bên ngoài Redis và correctness phụ thuộc exclusivity, cần xem cơ chế lease, token ownership, fencing/version và hệ thống sở hữu tài nguyên, không chỉ rely vào Redis RDB.

Một Redis TTL lock có thể hữu ích cho best-effort coordination, nhưng **RDB không cung cấp bảo đảm linearizability xuyên failover**.

## 20. RDB backup không giống chỉ bật RDB persistence

Một instance Redis có thể tạo `dump.rdb` trên cùng ổ đĩa dùng để chạy dịch vụ. Điều đó giúp restart trong một số trường hợp, nhưng không đủ chống:

- Mất disk/host.
- Ransomware.
- Người vận hành xóa nhầm thư mục.
- Lỗi filesystem.
- Snapshot bị ghi đè bởi dữ liệu đã bị ứng dụng làm hỏng logic.
- Môi trường container bị thay thế mà không dùng persistent volume.
- Disaster recovery cần restore ở region khác.

Một chính sách backup thực tế nên có bản sao **độc lập** với primary Redis.

### 20.1. Tạo snapshot phục vụ backup

Một cách tiếp cận có kiểm soát:

1. Yêu cầu `BGSAVE` nếu môi trường và chính sách cho phép.
2. Theo dõi để biết BGSAVE thành công.
3. Xác định file RDB ổn định và đúng phiên bản.
4. Sao chép tệp sang vị trí backup.
5. Ghi metadata: thời điểm yêu cầu, lúc bắt đầu, khi hoàn tất, node, Redis version, checksum.
6. Lưu bản sao ngoài host/volume hoặc sang backup service phù hợp.
7. Kiểm tra integrity.
8. Định kỳ restore lên Redis thử nghiệm và chạy bài kiểm tra ứng dụng.

Đừng đơn giản `cp dump.rdb backup.rdb` vào một thời điểm ngẫu nhiên mà không hiểu Redis có đang thay file và backup tool đang nhìn thấy phiên bản nào.

Trong một số môi trường, `redis-cli --rdb <path>` có thể hỗ trợ lấy RDB qua cơ chế đồng bộ dữ liệu. Khi dùng cách này cũng cần hiểu load phát sinh, permissions, topology và mốc ảnh chụp; không thể chỉ dựa vào việc CLI kết thúc mà bỏ test restore.

### 20.2. Ví dụ kiểm tra file bằng công cụ Redis

Trên một bản sao của tệp backup, có thể dùng:

```bash
redis-check-rdb /secure/backup/dump.rdb
```

Công cụ này hữu ích để kiểm tra định dạng và phát hiện một số lỗi RDB theo version tương ứng. Nhưng **file pass kiểm tra định dạng chưa bảo đảm dữ liệu nghiệp vụ đúng hoặc đã mới nhất**.

Bước xác thực mạnh hơn là **restore vào môi trường cách ly** rồi kiểm tra những key/metadata nghiệp vụ đại diện.

### 20.3. Backup cũng có điểm thời gian

Khi tạo backup từ RDB, metadata cần ghi rõ:

- Node/instance được backup.
- Thời điểm fork/ảnh chụp nếu xác định được.
- Thời điểm file hoàn tất.
- Thời điểm sao chép và upload hoàn tất.
- Redis server version.
- Storage location/checksum.
- Cấu hình RDB/AOF đi kèm.
- Tên cluster/shard và slot ownership ở thời điểm backup nếu liên quan.

Không nên đặt tên file `backup-10h00.rdb` rồi mặc định nó chứa mọi write trước đúng 10:00:00 nếu snapshot được fork trước đó và việc copy diễn ra sau.

## 21. Restore từ RDB: quy trình và giới hạn

Một quy trình thử nghiệm restore có thể:

1. Dừng Redis thử nghiệm hoặc dùng một instance Redis mới, cách ly với production.
2. Đặt file RDB hợp lệ vào thư mục persistence của instance thử nghiệm.
3. Cấu hình đúng `dir`, `dbfilename` và chính sách AOF cần thiết để bảo đảm startup đọc đúng file dự định.
4. Khởi động Redis.
5. Kiểm tra logs và `INFO persistence`.
6. Kiểm tra số key, data types, TTL và các bản ghi mẫu.
7. Chạy integration checks qua Spring Data Redis để xác minh serializers/schema.
8. Đo thời gian từ bắt đầu restore tới khi ứng dụng sẵn sàng phục vụ.
9. Ghi nhận những key mới hoặc các thao tác xóa sau snapshot đã mất theo kịch bản thử.
10. Không dùng kết quả restore thử nghiệm để ghi đè production nếu chưa có quy trình được phê duyệt.

Ví dụ cấu hình khởi động một instance Redis cách ly:

```bash
redis-server \
  --port 6380 \
  --dir /path/to/isolated-restore \
  --dbfilename dump.rdb \
  --appendonly no
```

Tệp `/path/to/isolated-restore/dump.rdb` phải được đặt ở đó trước khi start. `--appendonly no` trong ví dụ giúp môi trường thử tập trung vào RDB; không được áp dụng mù quáng cho production đang dựa trên AOF.

### 21.1. Kiểm tra kết quả thực tế

Trong môi trường thử:

```redis
DBSIZE
GET cart:101:state
TTL session:token-42
TYPE orders:events
XLEN orders:events
```

Các command chỉ hợp lệ nếu key/type tương ứng. `DBSIZE` là số key của logical DB hiện tại, không phải bằng chứng toàn bộ business transactions đã được phục hồi.

Nên kiểm tra:

- Đối tượng quan trọng còn hợp lệ không.
- Có stale key bất ngờ không.
- TTL có phù hợp deadline không.
- Stream/group offsets có đúng kỳ vọng snapshot không.
- Spring Data Redis có deserialize được dữ liệu không.
- Các index phụ/metadata có nhất quán với key chính không.
- Các job phụ thuộc message có xử lý trùng hoặc bỏ sót không.

### 21.2. Restore không phải rollback nghiệp vụ an toàn

Dùng RDB cũ để quay lui production có thể đảo ngược những thao tác đã được hệ thống bên ngoài ghi nhận.

Ví dụ:

```text
10:00  RDB có order status=PENDING
10:03  Database thanh toán ghi order=PAID
10:04  Redis status=PAID
10:05  Redis crash và restore RDB 10:00
```

Redis có thể báo `PENDING`, trong khi database thanh toán ghi `PAID`. Ứng dụng phải có cơ chế đối chiếu với nguồn dữ liệu có thẩm quyền, thay vì coi snapshot Redis là câu trả lời đúng nhất về trạng thái thanh toán.

Đối với cache, nhiều khi giải pháp an toàn hơn là **xóa cache cũ và rebuild từ database** thay vì phục hồi cache có khả năng stale.

## 22. Ảnh hưởng đến Redis Repository, chỉ mục và TTL

Spring Data Redis Repository có thể lưu:

```text
Entity Hash
Secondary index Sets
Expiration metadata
Shadow/phantom copies cho expiry event
```

Nếu RDB bị phục hồi về thời điểm cũ, không chỉ entity Hash mà cả index state và expiration metadata cũng trở về trạng thái của snapshot đó.

Có thể xảy ra:

- Entity đã cập nhật sau snapshot trở về giá trị cũ.
- Entity vừa tạo sau snapshot biến mất.
- Entity đã xóa sau snapshot xuất hiện lại.
- Index entries được cập nhật sau snapshot không còn.
- TTL được reset sau snapshot quay về deadline cũ.
- Expiration listeners không được replay mọi sự kiện đã xảy ra khi Redis offline.

**Không dùng keyspace expiration notifications làm hệ thống giao event bền vững để bù mọi sai lệch sau restore.** Pub/Sub notifications không có log ACK/replay mặc định.

Nếu các index và entities có tính nghiệp vụ quan trọng, cần nguồn dữ liệu có thể rebuild index hoặc quy trình reconcile sau sự cố.

### 22.1. Shadow copy không cứu được write chưa snapshot

Shadow copy trong Redis Repository có thể phục vụ việc mang theo giá trị entity khi key chính hết hạn, tùy cấu hình. Nhưng nếu cả key chính và shadow copy được tạo sau snapshot cuối, phục hồi RDB cũ có thể không chứa chúng.

Shadow copy giải quyết một bài toán **expiration event payload**, không phải một hệ thống WAL để giảm RPO.

## 23. Cách tính khoảng mất dữ liệu qua ba kịch bản

### Kịch bản A — Cache thuần, RDB mỗi khi có thay đổi và đủ điều kiện

```text
09:00  Snapshot chứa 50.000 product cache entries.
09:15  Cache nhận thêm 5.000 key mới.
09:20  Redis crash.
09:22  Redis restore snapshot 09:00.
```

Các key mới có thể mất, tạo cache misses. Nếu sản phẩm gốc còn trong database/API, ứng dụng có thể tái tạo cache. Rủi ro chính là spike tải nguồn, latency và khả năng database bị quá tải.

Biện pháp:

- Có rate limit/bulkhead cho cache loader.
- Dùng prewarm hot keys.
- Chống cache stampede.
- Theo dõi miss rate sau restart.
- Không biến cache dữ liệu thành nguồn duy nhất của các business updates.

### Kịch bản B — Session store, mất lệnh thu hồi

```text
12:00  Snapshot: session:s-7 = ACTIVE, TTL còn đủ dài.
12:04  User logout -> DEL session:s-7 thành công.
12:06  Redis crash.
12:07  Restore snapshot 12:00.
```

Session có thể trở lại `ACTIVE` nếu deadline vẫn chưa qua. Đây là rủi ro lớn hơn “user cần login lại”.

Biện pháp:

- Thiết kế xác thực dựa trên state bền vững/epoch/version phù hợp.
- Coi Redis session state là cache khi có thể.
- Không dựa duy nhất vào Redis RDB-only cho token revocation có yêu cầu bảo mật chặt.
- Kiểm thử hành vi của authentication system sau rollback.

### Kịch bản C — Counter hoặc queue

```text
13:00  Snapshot: counter:orders = 120.
13:01  50 request INCR thành công, counter live = 170.
13:02  Redis crash.
13:03  Restore snapshot 13:00 -> counter = 120.
```

Nếu counter dùng cấp ID đơn điệu không được phép trùng, giá trị quay lùi có thể gây lỗi nghiêm trọng. Nếu nó chỉ là metric có thể tính lại, mức mất có thể chấp nhận.

Biện pháp:

- Không dùng Redis RDB-only làm nguồn duy nhất cấp ID phải unique/monotonic xuyên crash.
- Dùng nguồn ID/sequence được bảo đảm phù hợp.
- Nếu dữ liệu có thể tính lại, có quy trình recompute.
- Nếu là queue, xem xét ACK, idempotency, persistence mạnh hơn và dữ liệu nguồn.

## 24. Giới hạn của việc ép tạo snapshot ngay sau mỗi ghi

Một ý tưởng sai thường gặp:

```java
redis.opsForValue().set("order:101", "PAID");
// Sau mỗi request, gọi Redis BGSAVE để "an toàn".
```

Cách này có nhiều vấn đề:

- `BGSAVE` có chi phí fork/I/O lớn.
- Nhiều request cùng lúc không thể tạo vô hạn snapshot hữu ích.
- `BGSAVE` trả khi bắt đầu, không phải luôn chờ file hoàn tất.
- Những lệnh phát sinh sau fork không có trong snapshot đang tạo.
- Snapshot có thể thất bại vì disk/memory.
- Latency và throughput Redis bị ảnh hưởng đáng kể.
- Không giải quyết tính nguyên tử với database khác.

Nếu cần một write được ghi bền vững trước khi trả thành công, phải lựa chọn **mô hình persistence và transactional storage phù hợp**. RDB snapshots định kỳ không được thiết kế như per-request durable commit.

### 24.1. Cần xác định yêu cầu trước khi chọn Redis

Hãy hỏi:

```text
Dữ liệu có tái tạo được từ nguồn khác không?
Được phép mất bao nhiêu giây/phút write?
Có được phép hồi sinh key đã DEL?
Có cần audit mỗi mutation?
Có cần exactly-once side effect?
Redis là cache hay database chính?
Khi failover, có được phép đọc phiên bản cũ?
RTO là bao nhiêu?
```

Nếu câu trả lời thể hiện không được mất hoặc hồi sinh trạng thái giao dịch, nên xem lại cả kiến trúc dữ liệu, không chỉ rút ngắn `save` interval.

## 25. Tối ưu BGSAVE cho vận hành

Một số vấn đề chính cần quan sát:

### 25.1. Kích thước dữ liệu và disk throughput

Dataset càng lớn, snapshot càng tốn thời gian ghi. Disk có throughput thấp hoặc latency cao có thể kéo dài `BGSAVE`, tăng thời gian COW tồn tại và ảnh hưởng I/O khác.

Nên đo:

```text
RDB file size
BGSAVE duration
Disk throughput / latency
Remaining disk space
CoW memory size
Fork latency
Redis command latency
```

### 25.2. Memory headroom

Nếu Redis gần chạm giới hạn RAM, một đợt write-heavy BGSAVE có thể gây áp lực memory. Cần tính cả headroom khi fork và COW; cấu hình `maxmemory` không phải tất cả nguồn memory OS của process.

Đối với container, memory limit và việc hệ điều hành OOM-kill child/parent có thể ảnh hưởng khả năng save.

### 25.3. Không dùng Redis RDB làm cơ chế export online tùy tiện

Việc tạo snapshot lớn có thể làm tăng tải Redis. Nếu muốn backup thường xuyên mà production primary đang chịu nhiều write, có thể cân nhắc backup từ replica phù hợp, với sự hiểu biết về replication lag và trạng thái snapshot của replica.

Backup từ replica có thể giảm tải primary trong một số mô hình, nhưng replica có thể **tụt sau** so với primary; bản backup có thể cũ hơn các write client đã nhận xác nhận.

### 25.4. Tối ưu không có nghĩa tăng frequency vô hạn

Snapshot thường xuyên hơn có thể giảm cửa sổ dữ liệu chưa có snapshot mới, nhưng tăng:

- Tần suất fork.
- I/O disk.
- COW memory.
- CPU.
- Số tình huống background save overlap/thất bại.
- Ảnh hưởng đến latency lệnh Redis.

Cần cân bằng RPO, RTO, throughput, dataset size và chi phí vận hành. Một workload ghi cực lớn có thể thích hợp với AOF hoặc persistence strategy khác thay vì ép RDB save quá thường xuyên.

## 26. Redis Cloud/managed service có thể thay đổi cơ chế backup

Khi dùng Redis qua dịch vụ managed, nhà cung cấp có thể:

- Có chính sách snapshot/backup riêng.
- Giới hạn lệnh `CONFIG SET`, `BGSAVE`, `SAVE`.
- Có persistence on/off khác nhau theo gói hoặc topology.
- Cung cấp point-in-time restore/backup scheduler riêng.
- Dùng storage và replication được quản lý.
- Có yêu cầu maintenance/failover khác.

Không nên giả định file `dump.rdb` tồn tại trên filesystem mà application có thể truy cập trực tiếp, hay `redis-cli --rdb` luôn được phép.

Khi đánh giá durability, cần xác định rõ:

```text
Tần suất backup do ai kiểm soát?
Snapshot được tạo từ primary hay replica?
Cấu hình RDB/AOF có hiệu lực trong phiên bản dịch vụ này?
Khả năng restore tới mốc thời gian nào?
SLA nhà cung cấp phân biệt failover và disaster recovery thế nào?
Có kiểm tra application data sau restore không?
```

Một dashboard hiển thị “backup completed” chưa đủ chứng minh RPO nghiệp vụ nếu không có quy trình restore được thử nghiệm.

## 27. Monitoring và cảnh báo RDB trong production

Monitoring nên trả lời ít nhất bốn nhóm câu hỏi.

**(1) Snapshot có đang chạy đúng lịch và thành công?**

- `rdb_bgsave_in_progress`.
- `rdb_last_bgsave_status`.
- `rdb_last_save_time` và logs.
- Số lần thất bại liên tiếp.

**(2) Snapshot có gây áp lực tài nguyên?**

- `rdb_last_bgsave_time_sec`.
- `rdb_current_bgsave_time_sec`.
- `rdb_last_cow_size`.
- CPU, RSS, memory limit, disk I/O.

**(3) Cửa sổ dữ liệu chưa được lưu có tăng quá mục tiêu?**

- Thời gian từ mốc snapshot được quan sát gần nhất.
- Số thay đổi từ lần lưu gần nhất.
- Độ dài BGSAVE.
- Có lỗi fork/disk/permissions không.
- Có AOF/replication backup bổ sung không.

**(4) Backup/restore có thực sự dùng được?**

- Timestamp backup ngoài host cuối cùng.
- Tình trạng checksum.
- Restore test gần nhất.
- RTO đo được.
- Kiểm tra dữ liệu với Spring Data Redis sau restore.

### 27.1. Ví dụ mức cảnh báo theo chính sách nội bộ

Giả sử đội vận hành **đặt mục tiêu** RDB backup không cũ quá 15 phút cho một cache quan trọng:

```text
WARNING:
    Không có snapshot hoàn tất mới hơn 15 phút.

CRITICAL:
    BGSAVE thất bại nhiều lần hoặc disk sắp đầy.

CRITICAL:
    Không có bản backup ngoài host gần đây.

INVESTIGATE:
    BGSAVE duration, COW hoặc fork latency tăng bất thường.
```

Các ngưỡng chỉ minh họa. Nếu snapshot đang chạy 4 phút, file hoàn tất ở một thời điểm có thể vẫn phản ánh state lúc bắt đầu, nên alert tuổi ảnh chụp phải phân tích được chênh lệch này.

### 27.2. Đừng chỉ dựa vào LASTSAVE

Một dashboard chỉ hiển thị:

```text
Time since last save = now - LASTSAVE
```

có thể hữu ích để biết Redis lần cuối báo save thành công từ bao giờ. Nhưng nó có thể **đánh giá thiếu** tuổi dữ liệu logic của snapshot nếu thời gian BGSAVE dài.

Cần kết hợp duration/log hoặc metadata quá trình backup khi đánh giá RPO thực tế.

## 28. Lập kế hoạch backup theo môi trường

Một kế hoạch ví dụ:

| Môi trường/loại dữ liệu | Đặc điểm | Định hướng RDB |
|---|---|---|
| Dev local | Dữ liệu dễ tái tạo | Snapshot đơn giản hoặc tắt persistence có chủ đích |
| Test integration | Cần lặp lại state để test | Snapshot có seed dữ liệu và restore thử |
| Cache production | Có nguồn bền vững khác | RDB hỗ trợ warm restart nếu lợi ích vượt chi phí |
| Redis session | Có rủi ro trải nghiệm và bảo mật | Cân nhắc persistence, nguồn xác thực, chính sách reset |
| Queue/Stream quan trọng | Cần không mất event và ACK | RDB-only có thể chưa đủ; thêm persistence/backup/recovery phù hợp |
| Financial/ledger state | Không được rollback ghi nhận | Thường cần nguồn transactional bền vững ngoài RDB-only |

Đây là bảng định hướng; mức SLA thực tế thuộc yêu cầu kinh doanh và rủi ro hệ thống.

### 28.1. Chính sách giữ nhiều phiên bản snapshot

Giữ một snapshot duy nhất có thể đủ cho restart gần nhất nhưng không đủ để phục hồi khi dữ liệu đã bị xóa nhầm rồi snapshot mới ghi đè trạng thái cũ.

Với yêu cầu backup:

- Giữ nhiều thế hệ snapshot.
- Lưu ngoài host hoặc vùng lỗi khác.
- Gắn timestamp và metadata.
- Kiểm tra checksum/tính toàn vẹn.
- Hạn chế quyền truy cập.
- Có thời hạn retention hợp lý.
- Diễn tập restore một bản cũ lẫn một bản mới.
- Phân biệt backup recovery với backup archival.

### 28.2. Bảo mật dữ liệu RDB

RDB có thể chứa dữ liệu nhạy cảm từ Redis:

```text
Tokens, sessions, user information,
counters, cached API responses, feature flags...
```

Dù Redis key TTL ngắn, snapshot từng được tạo có thể chứa dữ liệu vẫn còn hợp lệ tại mốc snapshot. Phải áp dụng encryption at rest, hạn chế quyền đọc, bảo vệ storage và quy trình tiêu hủy backup.

Không gửi tệp RDB production có dữ liệu nhạy cảm vào kênh chat/log/debug công khai. Khi cần chia sẻ để phân tích, nên tạo dữ liệu giả hoặc bản đã được kiểm soát theo quy định.

## 29. Thực hành 1 — Quan sát BGSAVE và LASTSAVE

**Mục đích:** phân biệt thao tác yêu cầu snapshot với việc snapshot hoàn tất.

Trên Redis thử nghiệm:

```redis
CONFIG GET save
INFO persistence
LASTSAVE
```

Tạo một số dữ liệu:

```redis
SET lab:profile:1 Alice
SET lab:profile:2 Bob
HSET lab:cart:1 total 120000 status OPEN
```

Nếu môi trường cho phép:

```redis
BGSAVE
```

Sau đó theo dõi:

```redis
INFO persistence
LASTSAVE
```

Ghi lại:

- Thời điểm yêu cầu BGSAVE.
- Giá trị `rdb_bgsave_in_progress`.
- Thời điểm BGSAVE hoàn tất.
- `rdb_last_bgsave_status`.
- `rdb_last_save_time`.
- `rdb_last_bgsave_time_sec`.

Giải thích vì sao kết quả `BGSAVE` bắt đầu thành công khác với xác nhận tệp snapshot đã lưu xong.

Không chạy các thao tác thay đổi persistence trên Redis production nếu không được phép.

## 30. Thực hành 2 — Mất key tạo sau snapshot

Dùng Redis thử nghiệm có volume lưu RDB, tắt AOF cho bài lab nếu muốn quan sát đúng RDB-only:

```conf
appendonly no
save ""
dbfilename dump.rdb
dir /path/to/lab-data
```

Các giá trị chỉ dành cho môi trường lab cô lập. Với `save ""`, snapshot phải được kích hoạt thủ công khi cần.

Các bước:

1. Ghi `SET lab:before 1`.
2. Gọi `BGSAVE`, đợi thành công.
3. Ghi `SET lab:after 2`.
4. Dừng Redis theo kịch bản **không tạo snapshot mới** trong một môi trường thử nghiệm được kiểm soát.
5. Khởi động lại từ RDB.
6. Kiểm tra `lab:before` và `lab:after`.

Dự đoán `lab:after` có thể mất vì nó được tạo sau mốc snapshot. Kịch bản chỉ an toàn trong lab không chứa dữ liệu quan trọng.

**Lưu ý:** shutdown graceful có thể có hành vi lưu dữ liệu theo cấu hình. Nếu thử nghiệm khoảng mất dữ liệu do crash, cần phân biệt rõ shutdown có save với failure không có cơ hội save. Không được dùng `SHUTDOWN SAVE` để mô phỏng mất điện.

## 31. Thực hành 3 — Delete rollback và token revocation

Trong Redis thử nghiệm:

```redis
SET lab:token:42 ACTIVE EX 3600
BGSAVE
```

Sau khi BGSAVE hoàn tất:

```redis
DEL lab:token:42
GET lab:token:42
```

Tại thời điểm live, `GET` trả nil. Sau đó mô phỏng phục hồi **từ bản RDB trước lệnh DEL** trong môi trường cô lập.

Kiểm tra xem key có xuất hiện lại hay không, tùy deadline còn hiệu lực.

Trả lời:

- Vì sao khôi phục snapshot cũ có thể đảo ngược lệnh `DEL`?
- Nếu token là khóa xác thực thật, rủi ro bảo mật là gì?
- Những nguồn bền vững hoặc version/revocation check nào cần bổ sung?
- Tại sao TTL không giải quyết hoàn toàn vấn đề?

## 32. Thực hành 4 — BGSAVE trong khi dữ liệu đang thay đổi

Trong lab:

1. Chuẩn bị dataset đủ lớn để có thể quan sát một `BGSAVE` kéo dài hơn mức không đáng kể.
2. Trước khi gọi BGSAVE, ghi `lab:marker = BEFORE`.
3. Gọi `BGSAVE`.
4. Khi BGSAVE đang chạy, ghi `lab:marker = AFTER`.
5. Sau khi BGSAVE hoàn tất, không tạo snapshot mới.
6. Copy/restore bản RDB vào một Redis thử nghiệm khác.
7. Đọc `lab:marker` trên instance restore.

Giải thích vì sao RDB có thể chứa `BEFORE` dù việc ghi `AFTER` đã được Redis live xác nhận **trước thời điểm `LASTSAVE` của lần BGSAVE ấy**.

Trong một dataset rất nhỏ, BGSAVE có thể hoàn tất trước khi bạn ghi `AFTER`, nên kịch bản không tái hiện được khoảng chênh. Đó là vấn đề thời điểm quan sát, không phải phản ví dụ của cơ chế snapshot.

## 33. Thực hành 5 — Tính cửa sổ mất dữ liệu

Cho timeline giả định:

```text
14:00:00 BGSAVE #1 bắt đầu.
14:00:15 BGSAVE #1 hoàn tất.
14:00:20 SET A = 1.
14:01:00 DEL B.
14:02:00 BGSAVE #2 bắt đầu.
14:02:10 SET C = 3.
14:02:30 Redis crash, BGSAVE #2 chưa hoàn tất.
```

Hãy trả lời:

1. Snapshot nào có khả năng là bản hoàn tất mới nhất?
2. Mốc dữ liệu logic của snapshot đó nằm khoảng thời điểm nào?
3. Thay đổi `SET A`, `DEL B`, `SET C` nào có thể mất?
4. Vì sao không thể tính loss window chỉ bằng `14:02:30 - 14:00:15` nếu không biết mốc fork?
5. Nếu BGSAVE #2 hoàn tất lúc `14:02:25`, thay đổi `SET C` lúc 14:02:10 có nhất thiết nằm trong RDB #2 không?

Câu cuối là trọng tâm: **không**, vì BGSAVE #2 đại diện cho trạng thái tại lúc bắt đầu khoảng 14:02:00.

## 34. Thực hành 6 — So sánh RDB-only và AOF

Dùng hai Redis instance thử nghiệm:

```text
Instance A: RDB enabled, AOF disabled.
Instance B: AOF enabled theo policy đã chọn.
```

Tạo cùng một tập write sau mốc snapshot cuối. Trong môi trường kiểm thử có kiểm soát, khôi phục từng instance sau một failure scenario được thiết kế trước.

Ghi nhận:

- Dữ liệu nào còn?
- Dữ liệu nào mất?
- Thời gian restart/restore.
- Disk footprint.
- Latency write.
- Chi phí CPU/I/O.
- Mức độ chắc chắn của write trước sự cố.

Không suy từ một lần benchmark rằng RDB hoặc AOF luôn nhanh hơn cho mọi workload; kích thước dataset, cấu hình fsync, disk và Redis version ảnh hưởng lớn.

## 35. Thực hành 7 — Spring Data Redis và sự khác biệt giữa ACK lệnh với persistence

Tạo service:

```java
@Service
public class CounterService {

    private final StringRedisTemplate redis;

    public CounterService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long increment() {
        return redis.opsForValue().increment(
            "lab:counter"
        );
    }

    public String read() {
        return redis.opsForValue().get(
            "lab:counter"
        );
    }
}
```

Các bước:

1. Tạo snapshot chứa `lab:counter = 10`.
2. Gọi `increment` nhiều lần để giá trị live thành `20`.
3. Quan sát kết quả Java đã nhận xác nhận tăng.
4. Phục hồi một Redis thử nghiệm từ RDB cũ.
5. So sánh `lab:counter` trước và sau restore.

Trả lời:

- Method Java đã trả thành công ở những lần `increment` có sai không?
- Vì sao lệnh Redis thành công mà trạng thái sau restore vẫn quay lùi?
- Nếu counter là số ID nghiệp vụ phải tăng đơn điệu, nên thiết kế source-of-truth thế nào?

## 36. Thực hành 8 — Thiết kế backup/restore

Bạn vận hành Redis chứa cache sản phẩm và thông tin cart tạm.

Hãy xây dựng runbook:

1. Xác định chính sách RPO/RTO cho từng loại key.
2. Chọn cơ chế snapshot và phương án backup ngoài host.
3. Kiểm tra `BGSAVE` hoàn tất.
4. Sao chép tệp và metadata.
5. Kiểm tra checksum/định dạng.
6. Restore vào Redis thử nghiệm.
7. Xác nhận Spring Data Redis deserialize được những key mẫu.
8. Kiểm tra TTL và các key đã bị xóa.
9. Đo thời gian dịch vụ sẵn sàng.
10. Định nghĩa ứng xử của ứng dụng khi dữ liệu cache sau restore bị stale.

Runbook tốt cần mô tả cả trường hợp backup lỗi, restore không thành công và quy trình rollback vận hành.

## 37. Thực hành 9 — Redis Cluster và backup không đồng thời

Giả sử Redis Cluster có hai primary:

```text
Primary A: keys order:{o-101}:...
Primary B: keys inventory:{sku-42}:...
```

Bản RDB của A phản ánh T1, của B phản ánh T2. Trong khoảng T1–T2, checkout cập nhật inventory và order bằng hai bước khác nhau.

Hãy:

- Mô tả các trạng thái bất nhất có thể xuất hiện khi restore hai snapshot không cùng mốc.
- Giải thích vì sao same-slot hash tag giải quyết atomicity trong **một aggregate** nhưng không biến toàn cluster thành một transaction.
- Đề xuất dùng database transaction/outbox hoặc reconciliation nếu checkout là nghiệp vụ quan trọng.
- Phân biệt restore RDB từng shard với failover sang replica có trạng thái mới hơn.

## 38. Thực hành 10 — Quan sát lỗi BGSAVE

Trong một môi trường lab có thể kiểm soát và không chứa dữ liệu quan trọng, mô phỏng một tình huống không thể ghi snapshot (ví dụ filesystem test chỉ đọc hoặc môi trường thiếu disk được tạo có kiểm soát).

Quan sát:

```redis
INFO persistence
CONFIG GET stop-writes-on-bgsave-error
```

Lưu ý: cách điều chỉnh permission/disk phải được thực hiện an toàn; không gây ảnh hưởng đến Redis production hoặc dữ liệu thật.

Các câu hỏi:

1. `rdb_last_bgsave_status` thể hiện gì?
2. `LASTSAVE` có tiếp tục tiến không?
3. Ứng dụng có còn ghi được dữ liệu không?
4. `stop-writes-on-bgsave-error` tác động thế nào đến availability?
5. Nếu lỗi kéo dài, vì sao RPO có thể vượt xa các khoảng thời gian trong `save` rules?
6. Hệ thống monitoring nên cảnh báo ở ngưỡng nào?

## 39. Những lỗi và ngộ nhận thường gặp

### 39.1. “Bật save 60 1 nghĩa là mất tối đa một phút”

Không có cam kết cứng. Điều kiện save còn phụ thuộc khởi động/hoàn tất snapshot, resource availability và sự cố persistence. Dữ liệu logic phản ánh thời điểm fork, không nhất thiết lúc LASTSAVE.

### 39.2. “BGSAVE trả OK nghĩa là tất cả dữ liệu hiện tại đã xuống disk”

Không đúng. Lệnh thường xác nhận background save bắt đầu; phải theo dõi hoàn tất. Những ghi sau fork không thuộc snapshot ấy.

### 39.3. “LASTSAVE là lúc mọi write trước đó chắc chắn bền vững”

Không đúng. Với BGSAVE, mốc state logic có thể ở trước thời điểm hoàn tất, đôi khi cách nhiều giây/phút nếu snapshot lớn.

### 39.4. “Mất dữ liệu chỉ là mất key mới”

Không đúng. Update có thể quay lui, delete có thể bị đảo ngược, counter có thể giảm, TTL có thể quay lại thời hạn cũ.

### 39.5. “DEL thành công rồi thì key không thể xuất hiện lại”

Không đúng nếu restore snapshot có key đó và deadline vẫn còn hợp lệ. Đây là rủi ro đặc biệt với dữ liệu revocation.

### 39.6. “Redis có replica nên không thể mất write”

Replication thường bất đồng bộ, và failover có thể promote replica chưa nhận write mới nhất. Không suy ra tính bền vững tuyệt đối từ việc có replica.

### 39.7. “WAIT tức là fsync trên mọi replica”

Không. `WAIT` liên quan đến xác nhận replication, không tự trở thành durability guarantee của storage và cũng không biến Redis thành consensus system.

### 39.8. “Bật AOF thì RDB không còn ý nghĩa”

Không nhất thiết. RDB có thể vẫn phục vụ backup, startup, full sync hoặc công việc vận hành khác. Khi cả hai bật, cần hiểu nguồn khôi phục thực tế.

### 39.9. “Tôi dùng ReactiveRedisTemplate nên write chắc chắn an toàn hơn”

Reactive API điều khiển mô hình I/O trong Java; nó không làm thay đổi các cơ chế snapshot/disk của Redis.

### 39.10. “Spring Cache/Redis Repository tự ghi một bản copy bền vững khác”

Không. Chúng có thể tạo Redis keys hoặc index phụ theo mapping, nhưng nếu cùng nằm trên một instance và đều sau snapshot cuối, chúng cũng có thể mất sau crash.

### 39.11. “Chỉ cần giữ dump.rdb trên volume là đủ backup”

Persistent volume có thể giúp restart, nhưng không bảo vệ khỏi mất volume, corruption hoặc xóa nhầm. Backup độc lập và test restore vẫn cần thiết.

### 39.12. “File RDB pass redis-check-rdb thì dữ liệu chắc chắn mới nhất”

Kiểm tra định dạng không phải kiểm tra tính mới và correctness nghiệp vụ. Một snapshot cũ hoàn toàn hợp lệ vẫn có thể thiếu các write gần đây.

### 39.13. “Restore RDB tự động khôi phục Pub/Sub events đã mất”

Không. Pub/Sub events không có log replay như Streams. Restore RDB không tạo lại mọi notification đã xảy ra khi subscriber vắng mặt.

### 39.14. “RDB có thể làm snapshot atomic toàn Redis Cluster”

Mỗi primary có vùng slot và quá trình persistence riêng; không mặc nhiên có ảnh chụp toàn cục đồng thời của nhiều node.

### 39.15. “Snapshot xong rồi có thể xóa data source bên ngoài”

Nếu Redis chỉ là cache và còn cần khôi phục từ nguồn gốc, xóa source-of-truth sẽ thay đổi hoàn toàn rủi ro. Cần đánh giá Redis trở thành dữ liệu chính với yêu cầu durability mới, không được tự suy từ RDB.

## 40. Checklist thiết kế và vận hành

Trước khi chọn RDB-only, xác định:

- [ ] Redis đang chứa cache tái tạo được hay state duy nhất?
- [ ] RPO mục tiêu đã được mô tả bằng **mức chấp nhận mất dữ liệu**, không chỉ cấu hình `save`?
- [ ] RTO đã được đo bằng restore thực tế?
- [ ] Đã phân biệt BGSAVE start time và completion time?
- [ ] `INFO persistence` và BGSAVE errors được giám sát?
- [ ] Disk, RAM headroom, COW và fork latency được theo dõi?
- [ ] Có backup ngoài host/volume và retention nhiều phiên bản?
- [ ] Backup được kiểm tra integrity và restore định kỳ?
- [ ] AOF/replication/failover được hiểu đầy đủ, không nhầm lẫn các bảo đảm?
- [ ] Khi restore snapshot cũ, application xử lý key stale/rollback thế nào?
- [ ] Token revocation, session, counter và queue có yêu cầu consistency riêng?
- [ ] Redis Repository serializers, schema và TTL được kiểm tra sau restore?
- [ ] Redis Cluster backups được đánh giá theo từng shard và consistency tổng thể?
- [ ] Có runbook khi disk full, BGSAVE fail, timeout, corruption hoặc data loss?
- [ ] Có idempotency/reconciliation cho side effect không thể lặp lại?
- [ ] Thao tác thử nghiệm crash được cô lập khỏi production?

Danh sách này là gợi ý triển khai; mục tiêu cuối cùng là một **quy trình khôi phục đã được thử nghiệm**, không chỉ một dòng cấu hình.

## 41. Câu hỏi tự đánh giá

1. RDB lưu trạng thái Redis theo những mốc nào?
2. Vì sao `SET` trả OK không chứng minh key đã có trong `dump.rdb`?
3. `BGSAVE` khác `SAVE` ở điểm gì?
4. Vì sao BGSAVE có overhead fork/COW?
5. Nếu Redis ghi dữ liệu trong lúc BGSAVE chạy, snapshot có bắt buộc chứa các ghi đó không?
6. Vì sao `LASTSAVE` không nhất thiết là mốc logic của dữ liệu RDB?
7. `save 300 10` có nghĩa Redis chắc chắn chụp đúng mỗi 5 phút không?
8. Dữ liệu nào có thể mất khi crash giữa hai snapshot?
9. Làm sao lệnh `DEL` có thể bị đảo ngược sau restore?
10. Vì sao key có TTL không được “sống lại” thêm nguyên thời hạn từ lúc restore?
11. Trường hợp nào RDB-only phù hợp với cache?
12. Vì sao RDB-only có thể không phù hợp làm payment ledger?
13. `rdb_last_bgsave_status` và `rdb_bgsave_in_progress` giúp quan sát gì?
14. Nếu background save thất bại nhiều lần, RPO có thể thay đổi thế nào?
15. `stop-writes-on-bgsave-error` tác động gì đến availability?
16. `SAVE` nên được dùng thế nào trên hệ thống latency nhạy cảm?
17. RPO và RTO khác nhau ra sao?
18. AOF khác RDB về cách ghi và khôi phục như thế nào?
19. `WAIT` có phải bằng chứng fsync ổ đĩa không?
20. Replica/failover có tự loại bỏ mọi khả năng mất write không?
21. Vì sao một Redis Cluster cần chiến lược backup cho nhiều primary?
22. RDB có bảo đảm một consumer group không bao giờ phải xử lý trùng event không?
23. Vì sao một file backup có checksum đúng vẫn có thể chứa trạng thái cũ?
24. Nếu key bị `DEL` sau snapshot và có deadline chưa tới, restore có thể xảy ra điều gì?
25. Bạn sẽ kiểm tra gì để chứng minh một RDB backup thực sự restore được với Spring Data Redis?

## 42. Ghi nhớ

- **RDB là ảnh chụp trạng thái Redis tại một mốc logic**, không phải nhật ký của từng write sau mốc ấy.
- `BGSAVE` thường dùng fork và copy-on-write để ghi snapshot nền. Parent tiếp tục phục vụ lệnh, nhưng những write sau lúc fork **không tự được thêm vào snapshot đang tạo**.
- **Thời gian `LASTSAVE` có thể là lúc BGSAVE hoàn tất**, trong khi dữ liệu trong RDB phản ánh lúc BGSAVE bắt đầu. Không dùng `now - LASTSAVE` làm hard upper bound của data loss.
- Các dòng `save <seconds> <changes>` xác định **điều kiện kích hoạt**, không bảo đảm một chu kỳ snapshot cứng hoặc RPO tuyệt đối.
- Crash có thể khiến mất **key mới, update, delete, counter increments, Stream entries, ACK state và TTL changes** sau snapshot. Lệnh `DEL` đã thành công có thể bị đảo ngược khi restore snapshot cũ.
- `SAVE` có thể block server; `BGSAVE` thường thích hợp hơn cho snapshot runtime nhưng có chi phí fork, I/O, RAM COW và nguy cơ thất bại.
- Quan sát `INFO persistence`, `LASTSAVE`, logs, disk và COW. Khi BGSAVE fail, cửa sổ dữ liệu chưa được lưu có thể tăng vượt cấu hình `save`.
- **RPO** nói về lượng dữ liệu chấp nhận mất; **RTO** nói về thời gian khôi phục. Cần đo cả hai bằng kịch bản restore thật.
- **AOF, replication, failover và backup độc lập** là các cơ chế khác RDB; mỗi cơ chế giảm một nhóm rủi ro nhưng không tự tạo exactly-once hay transaction xuyên hệ thống.
- Với Spring Data Redis, thành công của `StringRedisTemplate`, `ReactiveRedisTemplate`, Spring Cache hoặc Repository **không đồng nghĩa vừa có snapshot chứa write**.
- Redis cache có thể chấp nhận mất dữ liệu nếu tái tạo được, nhưng dữ liệu tài chính, revocation, lock, queue hoặc counter quan trọng phải có thiết kế durability và idempotency riêng.
- **Backup đáng tin cậy là backup có thể restore và kiểm chứng**, không chỉ là có một file `dump.rdb` trên cùng máy.
- Chọn cấu hình persistence từ **yêu cầu mất dữ liệu thực tế của nghiệp vụ**, không chỉ từ số giây trong `redis.conf`.

### Tài liệu tham khảo chính thức

- [Redis — Persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/)
- [Redis — Redis configuration](https://redis.io/docs/latest/operate/oss_and_stack/management/config/)
- [Redis — SAVE](https://redis.io/docs/latest/commands/save/)
- [Redis — BGSAVE](https://redis.io/docs/latest/commands/bgsave/)
- [Redis — LASTSAVE](https://redis.io/docs/latest/commands/lastsave/)
- [Redis — INFO](https://redis.io/docs/latest/commands/info/)
- [Redis — CONFIG GET](https://redis.io/docs/latest/commands/config-get/)
- [Redis — EXPIRE](https://redis.io/docs/latest/commands/expire/)
- [Redis — PERSIST](https://redis.io/docs/latest/commands/persist/)
- [Redis — WAIT](https://redis.io/docs/latest/commands/wait/)
- [Redis — WAITAOF](https://redis.io/docs/latest/commands/waitaof/)
- [Redis — Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/)
- [Redis — Redis Cluster](https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/)
- [Redis — Redis Streams](https://redis.io/docs/latest/develop/data-types/streams/)
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html)
- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html)
- [Spring Data Redis — Reactive Redis](https://docs.spring.io/spring-data/redis/reference/redis/reactive.html)
