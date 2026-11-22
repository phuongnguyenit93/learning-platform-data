# Oplog, cửa sổ lịch sử và độ trễ sao chép trong MongoDB replica set

## 1. Vì sao một secondary có thể không theo kịp primary?

Một hệ thống MongoDB triển khai **replica set** gồm một primary và các secondary. Ứng dụng ghi vào primary, các secondary nhận và áp dụng những thay đổi đó để duy trì bản sao dữ liệu.

Hãy tưởng tượng một secondary bị ngắt mạng trong 10 giờ. Sau khi kết nối lại, nó phải nhận các thay đổi đã xảy ra trong khoảng thời gian bị gián đoạn. Nhưng điều gì xảy ra nếu primary chỉ còn giữ lịch sử thay đổi của 6 giờ gần nhất?

Secondary có thể đã bỏ lỡ các thao tác mà nguồn đồng bộ không còn lưu. Nó không thể chỉ hỏi “cho tôi tất cả thay đổi kể từ 10 giờ trước” nếu phần lịch sử đó đã bị loại khỏi **oplog**. Khi không còn nguồn nào cung cấp chuỗi lịch sử cần thiết, secondary trở thành **quá cũ để đồng bộ bằng oplog** (*too stale*) và cần một quá trình khởi tạo đồng bộ lại phù hợp.

Đây là lý do khi vận hành replica set phải hiểu **ba đại lượng liên quan nhưng khác nhau**:

- **Oplog** (*operations log*): nhật ký nội bộ lưu chuỗi thao tác thay đổi dữ liệu để phục vụ replication.
- **Cửa sổ lịch sử oplog** (*oplog window*): khoảng thời gian giữa các bản ghi oplog cũ nhất và mới nhất còn giữ trên một thành viên.
- **Độ trễ sao chép** (*replication lag*): một cách đo mức secondary chậm hơn nguồn/primary về tiến độ áp dụng các thay đổi.

Chúng liên hệ với nhau, nhưng không thể thay thế nhau. Một replica set có lag nhỏ hôm nay vẫn có thể gặp sự cố trong ngày mai nếu tốc độ ghi tăng đột biến khiến cửa sổ oplog co lại.

Trong bài học thuộc chương **Replica set** của MongoDB, bạn sẽ:

1. Hiểu cách primary và secondary sử dụng oplog.
2. Phân biệt các timestamp, vị trí sao chép và mức xác nhận ghi.
3. Đọc và diễn giải oplog window cùng replication lag.
4. Nhận ra điều kiện khiến secondary không còn đủ lịch sử để bắt kịp.
5. Sử dụng các lệnh `mongosh` để quan sát replica set mà không sửa dữ liệu hệ thống.
6. Lập phương án tăng cửa sổ oplog, giảm lag và khôi phục secondary.
7. Hiểu ảnh hưởng đến read preference, write concern, failover, change streams và backup.

## 2. Luồng sao chép dữ liệu trong replica set

### 2.1. Primary nhận các thao tác ghi

Trong hoạt động thông thường, client gửi ghi đến primary. Những thay đổi được primary chấp nhận được ghi vào dữ liệu và biểu diễn trong **oplog**, để các thành viên khác có thể sao chép.

```text
                 MongoDB driver
                       |
                       | insert / update / delete
                       v
                   PRIMARY
                 +---------+
                 | Data    |
                 | Oplog   |
                 +---------+
                    |
            Các mục oplog mới
               /          \
              v            v
       SECONDARY A     SECONDARY B
       +---------+     +---------+
       | Data    |     | Data    |
       | Oplog   |     | Oplog   |
       +---------+     +---------+
```

Sơ đồ diễn tả luồng khái niệm. Trong thực tế, secondary có thể chọn **sync source** là primary hoặc một secondary khác đủ điều kiện (*chaining*), nên không phải tất cả thành viên luôn trực tiếp kéo oplog từ primary.

### 2.2. Secondary lấy và áp dụng oplog

Về bản chất:

1. Secondary xác định vị trí đồng bộ mà nó đã có.
2. Nó lấy các mục oplog tiếp theo từ sync source.
3. Nó áp dụng những thay đổi thích hợp lên dữ liệu cục bộ.
4. Tiến độ của secondary tiếp tục dịch về phía các thao tác mới trên replica set.

Replication trong replica set là **bất đồng bộ**: primary có thể tiếp nhận thao tác mới trước khi secondary áp dụng xong thao tác đó. Khoảng chênh giữa tiến độ các thành viên là nguyên nhân cơ bản của replication lag.

### 2.3. Oplog có mặt trên từng thành viên lưu dữ liệu

Mỗi thành viên dữ liệu của replica set duy trì một bản sao oplog trong database `local`, thường tại collection:

```javascript
local.oplog.rs
```

Database `local` chứa dữ liệu đặc thù của từng node và không được sao chép như database ứng dụng. Điều đó có nghĩa:

- Oplog của primary và secondary có thể có **điểm cũ nhất khác nhau**, tùy dung lượng và hoạt động tại từng thành viên.
- Muốn xem oplog của node nào, cần kết nối **trực tiếp** đến node đó bằng quyền phù hợp.
- Không nên giả định truy vấn `local.oplog.rs` qua một router `mongos` sẽ cho biết oplog của toàn cluster hoặc của một replica set cụ thể.

Oplog là cơ chế nội bộ phục vụ replication, không phải một collection nghiệp vụ mà ứng dụng được quyền tự ý chỉnh sửa.

## 3. Một mục trong oplog chứa thông tin gì?

### 3.1. Hình dạng khái niệm

Một mục oplog có thể trông giống:

```javascript
{
  ts: Timestamp({ t: 1794631200, i: 1 }),
  t: Long("9"),
  op: "i",
  ns: "shop.orders",
  ui: UUID("..."),
  o: {
    _id: ObjectId("66a000000000000000000001"),
    status: "NEW"
  },
  wall: ISODate("2026-11-14T03:20:00Z")
}
```

Đây là **ví dụ minh họa**, không phải cấu trúc mà mọi version MongoDB hoặc mọi loại thao tác bắt buộc có giống hệt. Một số trường quan trọng:

| Trường | Ý nghĩa khái quát |
| --- | --- |
| `ts` | BSON Timestamp dùng để định vị/thứ tự một mục trong luồng oplog |
| `t` | Term liên quan nhiệm kỳ primary/election trong replica set khi có mặt |
| `op` | Loại thao tác, ví dụ insert/update/delete/command/no-op |
| `ns` | Namespace liên quan, thường ở dạng `database.collection` |
| `ui` | UUID của collection khi được ghi trong mục oplog |
| `o` | Nội dung thao tác theo cách MongoDB biểu diễn |
| `o2` | Thông tin bổ sung trong một số kiểu update hoặc thao tác |
| `wall` | Thời gian tường (*wall clock*) của mục nếu được cung cấp |

Một vài giá trị `op` thường gặp:

```text
i  -> insert
u  -> update
d  -> delete
c  -> command
n  -> no-op
```

MongoDB có thể biểu diễn transaction hoặc nhiều thao tác bằng những cấu trúc nội bộ phức tạp hơn, chẳng hạn các bản ghi liên quan đến `applyOps`. **Không được suy luận rằng mỗi thay đổi nghiệp vụ luôn tương ứng đúng một dòng oplog có cùng cấu trúc**.

### 3.2. BSON Timestamp khác BSON Date

`ts` là kiểu **BSON Timestamp**, thường có thành phần thời gian theo giây và thành phần tăng thứ tự trong cùng khoảng thời gian. Nó đóng vai trò **vị trí logic** trong lịch sử replication.

`wall`, nếu có, là **BSON Date** mô tả thời gian theo đồng hồ.

Không nên:

- dùng một chuỗi ngày do client tạo thay thế `ts`;
- hiểu phần tăng của `Timestamp` là số mili giây;
- tự tạo hoặc sửa `ts` trong `local.oplog.rs`;
- dùng ngày tường làm cơ chế duy nhất để chứng minh thứ tự/nhân quả của các thao tác.

Hai node có thể có sai lệch đồng hồ nhỏ; khi đối soát tiến độ sao chép, dữ liệu `optime` và log replication có ý nghĩa khác so với phép đo latency phía ứng dụng.

### 3.3. Oplog không phải nhật ký kiểm toán đầy đủ

Oplog phục vụ **đồng bộ trạng thái dữ liệu** và có giới hạn lưu trữ. Nó không hứa sẽ lưu mọi sự kiện nghiệp vụ mãi mãi, không ghi đủ thông tin danh tính người thao tác như một hệ thống audit chuyên dụng và không nhất thiết có cấu trúc dễ đọc như dữ liệu ban đầu.

Nếu cần audit không thể sửa, truy vết thay đổi lâu dài hoặc phục hồi theo một thời điểm, cần thiết kế **audit log/backup/PITR** riêng theo yêu cầu. Không lấy `local.oplog.rs` làm hệ thống event bus hoặc kho dữ liệu lịch sử dài hạn mà không có chính sách lưu giữ độc lập.

## 4. Oplog window là gì?

### 4.1. Oplog được giữ trong một không gian hữu hạn

Oplog thường được quản lý như một **capped collection** với kích thước cấu hình. Khi có thêm mục mới, các mục cũ có thể bị loại để dành không gian. MongoDB còn có những cơ chế retention theo phiên bản và cấu hình, nên không nên hiểu “kích thước đạt ngưỡng thì ngay lập tức xóa đúng một lượng cố định”.

Đối với một thành viên đang hoạt động, ta quan tâm:

```text
Oplog cũ nhất vẫn còn                    Oplog mới nhất
         |                                     |
         v                                     v
  2026-11-12 06:00 UTC                2026-11-14 06:00 UTC
         +-------------------------------------+
                 Oplog window ~ 48 giờ
```

Cửa sổ lịch sử thường được ước tính:

\[
\text{Oplog window} \approx T_{\text{newest}}-T_{\text{oldest}}
\]

Trong đó `T` là thời điểm của mục oplog cũ nhất và mới nhất còn có thể đọc. Với ví dụ trên, window xấp xỉ **48 giờ**.

### 4.2. Kích thước oplog và thời lượng lưu giữ không giống nhau

Ví dụ cùng một oplog được cấu hình khoảng 20 GiB:

| Tốc độ tạo oplog trung bình | Thời lượng tương đương gần đúng |
| --- | --- |
| 0,5 GiB/giờ | 40 giờ |
| 1 GiB/giờ | 20 giờ |
| 4 GiB/giờ | 5 giờ |

Đây chỉ là phép chia dung lượng/thông lượng để hình dung, **không phải cam kết retention**. Kích thước thực của mục oplog, các thao tác ghi, cấu hình minimum retention, hoạt động của replica set và các giới hạn phiên bản ảnh hưởng đến window quan sát được.

Nếu write workload tăng mạnh, cùng lượng không gian phải chứa nhiều thao tác hơn trong mỗi giờ, khiến **window có xu hướng co lại**.

### 4.3. Tác động của burst write

Giả sử bình thường:

```text
Dung lượng oplog mục tiêu:  24 GiB
Tạo oplog:                 ~0,5 GiB/giờ
Window ước tính:           ~48 giờ
```

Một batch job chạy:

```text
Tạo oplog tăng lên:        ~6 GiB/giờ
Window tương đương:         ~4 giờ
```

Nếu secondary đang mất mạng 7 giờ, việc chỉ biết “ngày thường window là 48 giờ” không đủ. Tải đột biến có thể làm lịch sử cần thiết bị loại sớm hơn dự kiến, tùy chính sách giữ oplog.

Vì vậy cần theo dõi **oplog window theo thời gian**, đặc biệt trong thời điểm migration, import hoặc batch update/delete lớn.

### 4.4. Minimum oplog retention và các ngoại lệ

Một số phiên bản/cấu hình MongoDB hỗ trợ **thời gian giữ oplog tối thiểu**, thường được quản lý bằng thiết lập như `oplogMinRetentionHours`. Cơ chế retention cũng có thể phải giữ các mục oplog cần cho majority commit point trong những tình huống nhất định.

Điều cần hiểu:

- **Max size** là một giới hạn/quy mô cấu hình quan trọng nhưng không phải công thức chính xác cho thời gian giữ.
- **Minimum retention** có thể khiến oplog giữ lịch sử lâu hơn so với dự đoán chỉ bằng kích thước, với điều kiện phiên bản và tài nguyên cho phép.
- Không được biến một giá trị minimum retention thành bảo đảm vận hành tuyệt đối nếu disk, topology hoặc sự cố khác có thể ảnh hưởng.
- Tên tham số, khả năng thay đổi online và cách MongoDB xử lý dung lượng phụ thuộc phiên bản/loại dịch vụ; cần xem cấu hình triển khai thực tế.

**Luôn đo cửa sổ thực tế**, không chỉ đọc một giá trị “48 giờ” ghi trong tài liệu kiến trúc.

### 4.5. Window là đặc tính theo từng node

Replica set có thể có ba thành viên:

```text
Primary       oplog window: 36 giờ
Secondary A   oplog window: 42 giờ
Secondary B   oplog window: 30 giờ
```

Đây là ví dụ minh họa. Khi secondary cố gắng bắt kịp, điều quan trọng là **sync source được chọn có còn các mục oplog tiếp theo từ vị trí của secondary hay không**. Window của primary là chỉ số quan trọng, nhưng một secondary có thể đồng bộ từ một nguồn khác đủ điều kiện nếu cấu hình và cơ chế chọn nguồn cho phép.

Không suy luận rằng kích thước file oplog ở mỗi thành viên luôn giống nhau hoặc luôn giữ cùng thời gian.

## 5. Replication lag: độ trễ sao chép đo điều gì?

### 5.1. Chênh lệch giữa tiến độ primary và secondary

Trong giám sát thường ngày, **replication lag** có thể được ước tính bằng chênh lệch thời điểm thao tác cuối đã áp dụng trên primary và secondary:

\[
\text{Lag}_{i}\approx T_{\text{primary optime}}-T_{\text{secondary }i\text{ optime}}
\]

Ví dụ:

```text
Primary vừa áp dụng thay đổi tới:      12:00:10 UTC
Secondary A áp dụng tới:               12:00:08 UTC
Secondary B áp dụng tới:               11:57:10 UTC

Lag A: ~2 giây
Lag B: ~3 phút
```

Con số này thường được hiển thị trong `rs.status()` hoặc các công cụ monitoring. Đây là **độ chênh tiến độ được quan sát**, không nhất thiết bằng toàn bộ độ trễ client end-to-end.

### 5.2. Lag không phải luôn bằng “thời gian thao tác ghi được sao chép”

Một thao tác có thể mất:

1. Thời gian ghi vào primary.
2. Thời gian secondary nhận/tải oplog.
3. Thời gian secondary áp dụng thay đổi.
4. Thời gian xác nhận mức write concern mong muốn.
5. Thời gian ứng dụng đọc thấy dữ liệu, phụ thuộc read preference và read concern.

Các hệ thống giám sát có thể hiển thị số đo khác nhau như **applied optime**, **durable optime**, network delay, majority commit point hoặc thời gian một thao tác hoàn tất. Không gọi tất cả chúng là “lag” mà không ghi rõ định nghĩa.

Đặc biệt, một secondary có thể nhận oplog tương đối nhanh nhưng áp dụng chậm do CPU/đĩa thiếu tài nguyên. Khi đó cần phân tích luồng **fetch** và **apply**, không chỉ độ trễ mạng.

### 5.3. Lag 0 giây có nghĩa tuyệt đối đồng bộ không?

Không. Có vài lý do:

- `optimeDate` thường có độ phân giải ở mức giây; hai node hiển thị cùng giây có thể vẫn khác vị trí oplog chi tiết.
- Giám sát dùng dữ liệu thu thập theo chu kỳ và có độ trễ heartbeat.
- Ngay sau thời điểm lấy số liệu, primary có thể nhận thêm ghi mới.
- “Đã áp dụng” khác với “đã ghi bền vững/xác nhận majority” tùy chỉ số.

**Lag thấp là tín hiệu tốt**, nhưng không thay thế lựa chọn write concern/read concern đúng theo yêu cầu nhất quán.

### 5.4. Secondary cố ý trễ

Một replica set có thể cấu hình thành viên **delayed secondary** để trì hoãn áp dụng oplog theo một khoảng được chỉ định. Lag lớn khi đó là **có chủ đích**, không nhất thiết do nghẽn hệ thống.

Tuy nhiên, secondary trễ vẫn phụ thuộc lịch sử oplog: nếu khoảng giữ oplog của sync source không đủ so với mức trễ và thời gian gián đoạn bổ sung, thành viên có thể gặp khó khăn khi duy trì vị trí.

Vì vậy ngưỡng cảnh báo và dung lượng oplog của delayed secondary cần được thiết kế riêng, không dùng cùng một cảnh báo “lag hơn 60 giây là lỗi” cho mọi thành viên.

## 6. Quan hệ giữa oplog window và replication lag

### 6.1. Còn đủ lịch sử để bắt kịp hay không?

Giả sử tại thời điểm quan sát:

```text
Oplog trên sync source:

  Oldest retained                  Newest
      08:00 ----------------------- 18:00
             window ~10 giờ

Secondary last applied = 15:00
      => Lag ~3 giờ, nguồn còn lịch sử tiếp theo.
```

Khi secondary có vị trí 15:00 và nguồn còn các thao tác kể từ đó, nó có khả năng **tiếp tục catch-up**, nếu dữ liệu và môi trường cho phép.

Trường hợp khác:

```text
Oplog trên sync source:

  Oldest retained                  Newest
      12:00 ----------------------- 18:00
             window ~6 giờ

Secondary last applied = 09:00
      => Lag ~9 giờ, lịch sử 09:00..12:00 đã mất trên nguồn.
```

Secondary không thể chỉ đọc những mục sau 12:00 rồi bỏ qua phần 09:00–12:00: làm vậy sẽ khiến dữ liệu thiếu những thay đổi cần thiết.

Nếu không có một sync source hợp lệ khác còn đủ lịch sử, secondary có thể rơi vào trạng thái **too stale**, phải được đồng bộ lại bằng quy trình thích hợp.

### 6.2. Ước lượng headroom

Một chỉ số vận hành đơn giản:

\[
\text{Headroom}\approx \text{Oplog window}-\text{Replication lag}
\]

Ví dụ:

```text
Window = 24 giờ
Lag    =  2 giờ
Margin = 22 giờ
```

Ngược lại:

```text
Window =  6 giờ
Lag    =  5 giờ
Margin =  1 giờ
```

Margin nhỏ là tín hiệu cần chú ý: nếu secondary tiếp tục tụt lại và nguồn tiếp tục ghi, cửa sổ giữ oplog có thể không còn đủ.

**Giới hạn của công thức:** đây là ước lượng theo thời gian, không phải điều kiện chính xác ở mức `optime` cho mọi topology. Muốn quyết định một thành viên còn catch-up được hay không, cần kiểm tra **vị trí oplog của chính thành viên đó**, **mục cũ nhất trên sync source khả dụng**, và trạng thái replication thực tế.

### 6.3. Lag tăng và window co cùng lúc là tình huống nguy hiểm

Một cuộc import lớn có thể:

1. Tạo rất nhiều thao tác trên primary.
2. Làm thông lượng tạo oplog tăng mạnh.
3. Khiến window trên sync source co lại.
4. Làm secondary chậm hơn do CPU/đĩa/network bão hòa.
5. Khiến secondary mất lịch sử cần thiết trước khi bắt kịp.

```text
           Burst write trên primary
                    |
           +--------+---------+
           |                  |
           v                  v
  Oplog sinh nhanh       Secondary xử lý
  -> Window co           không theo kịp
           |                  |
           +--------+---------+
                    |
                    v
           Headroom giảm nhanh
                    |
                    v
             Nguy cơ too stale
```

Chỉ theo dõi dung lượng oplog hoặc lag riêng lẻ có thể bỏ sót tình huống kết hợp này.

## 7. Quan sát replica set bằng `mongosh`

### 7.1. Điều kiện và quyền

Ví dụ sau dành cho **replica set thử nghiệm hoặc môi trường được phép giám sát**. Cần kết nối đến `mongod` là thành viên của replica set; không thực hiện thao tác thay đổi cấu hình hoặc xóa oplog.

URI minh họa:

```bash
mongosh "mongodb://localhost:27017,localhost:27018,localhost:27019/?replicaSet=rs0"
```

Thay host, tên replica set, TLS và cơ chế xác thực cho môi trường thật. Một số lệnh cần role như `clusterMonitor` hoặc những quyền đọc hệ thống liên quan; nếu bị từ chối, nhờ administrator cấp quyền phù hợp, **không sửa quyền tùy tiện**.

### 7.2. Kiểm tra node đang kết nối

```javascript
printjson(db.adminCommand({ hello: 1 }));
```

Phần kết quả đáng chú ý:

- `setName`: tên replica set.
- `isWritablePrimary`: node hiện đang nhận vai trò primary hay không.
- `secondary`: node có phải secondary không.
- `hosts` và các thông tin thành viên: hỗ trợ nhận biết topology.

Đừng cho rằng “node đầu tiên trong connection string là primary”. Driver có thể chọn thành viên thích hợp theo topology và read preference.

### 7.3. Xem trạng thái các thành viên

```javascript
const status = rs.status();
printjson(status);
```

`rs.status()` thường cho biết:

- `set` và `date` của trạng thái replica set.
- `members[].name`: địa chỉ thành viên.
- `members[].stateStr`: `PRIMARY`, `SECONDARY` hoặc trạng thái khác.
- `members[].health`, thông tin heartbeat và kết nối.
- `members[].optime`, `optimeDate` hoặc các trường tiến độ liên quan tùy phiên bản.
- `optimes`/last committed op time ở những phiên bản có báo cáo tương ứng.

Một thành viên ở trạng thái `SECONDARY` không đồng nghĩa độ trễ luôn nhỏ. Một node có thể đang healthy ở cấp heartbeat nhưng vẫn tụt tiến độ do áp dụng oplog chậm.

### 7.4. Tính lag ước lượng từ `optimeDate`

Ví dụ đọc dữ liệu `rs.status()` và tính chênh lệch thời gian giữa primary và từng secondary:

```javascript
const s = rs.status();
const primary = s.members.find((m) => m.stateStr === "PRIMARY");

if (!primary || !(primary.optimeDate instanceof Date)) {
  print("Không có optimeDate của primary để tính lag.");
} else {
  const rows = s.members
    .filter((m) => m.stateStr === "SECONDARY")
    .map((member) => ({
      name: member.name,
      state: member.stateStr,
      lastApplied: member.optimeDate ?? null,
      lagSeconds:
        member.optimeDate instanceof Date
          ? Math.max(
              0,
              (primary.optimeDate.getTime() -
                member.optimeDate.getTime()) / 1000
            )
          : null
    }));

  printjson(rows);
}
```

Kết quả là **ước lượng tại một lần lấy trạng thái**, không phải phép đo chính xác mọi thời điểm. Nếu member đang mất liên lạc, các trường có thể thiếu hoặc cũ; nếu primary vừa đổi vai trò, snapshot trạng thái có thể chưa đầy đủ. Không dùng phép tính này làm điều kiện duy nhất để tự động xóa/rebuild secondary.

### 7.5. Xem thông tin replication bằng helper

Trên các phiên bản `mongosh` hỗ trợ:

```javascript
rs.printReplicationInfo();
rs.printSecondaryReplicationInfo();
```

`rs.printReplicationInfo()` thường hiển thị kích thước cấu hình/được dùng và khoảng thời gian giữa mục oplog đầu–cuối trên thành viên liên quan.

`rs.printSecondaryReplicationInfo()` thường cho biết thông tin tiến độ của secondary so với primary, giúp quan sát lag; chi tiết output và khả năng dùng tùy phiên bản shell/server.

Nếu helper không có hoặc không phù hợp phiên bản, sử dụng `rs.status()`, lệnh `replSetGetStatus` và hệ thống monitoring chính thức. **Không dựa vào chuỗi output cố định để viết parser production**, vì cách hiển thị có thể đổi giữa phiên bản.

### 7.6. Đọc collection `local.oplog.rs` trực tiếp: chỉ quan sát

Khi cần xem oplog của **một node cụ thể**, kết nối trực tiếp đến node đó bằng quyền phù hợp:

```bash
mongosh "mongodb://localhost:27018/?directConnection=true"
```

Ví dụ trong shell kết nối trực tiếp:

```javascript
const oplog = db.getSiblingDB("local").getCollection("oplog.rs");

// Chỉ đọc metadata collection.
const stats = oplog.stats();
printjson({
  capped: stats.capped,
  maxSizeBytes: stats.maxSize,
  currentSizeBytes: stats.size,
  storageSizeBytes: stats.storageSize,
  count: stats.count
});

// Lấy mục cũ nhất theo thứ tự tự nhiên.
const oldest = oplog.find(
  {},
  { ts: 1, wall: 1, op: 1, ns: 1 }
).sort({ $natural: 1 }).limit(1).toArray()[0];

// Lấy mục mới nhất.
const newest = oplog.find(
  {},
  { ts: 1, wall: 1, op: 1, ns: 1 }
).sort({ $natural: -1 }).limit(1).toArray()[0];

printjson({ oldest, newest });
```

`$natural` ở đây dùng để xem thứ tự lưu trữ của oplog. Đối với oplog, đây là cách khảo sát phổ biến; không tổng quát hóa thành quy tắc truy vấn index cho mọi collection.

Nếu `wall` có dạng Date trên cả hai mục:

```javascript
const windowHours =
  oldest?.wall instanceof Date && newest?.wall instanceof Date
    ? (newest.wall.getTime() - oldest.wall.getTime()) / 3600000
    : null;

print("Oplog window (ước lượng giờ): " + windowHours);
```

Ở phiên bản/dữ liệu không có `wall`, hãy dùng helper hoặc cách chuyển `ts` thích hợp với phiên bản BSON. Không lấy `ts.i` chia 1.000 rồi coi đó là mili giây.

**Tuyệt đối không thực hiện** `insertOne`, `updateOne`, `deleteMany`, `drop`, `compact` hoặc bất cứ thao tác sửa trực tiếp nào trên `local.oplog.rs`. Đây là vùng dữ liệu replication nội bộ, không phải collection test.

### 7.7. Cần xem thêm gì ngoài thời gian oplog?

Nếu có quyền giám sát, có thể khảo sát:

```javascript
printjson(
  db.adminCommand({ replSetGetStatus: 1 })
);

printjson(
  db.adminCommand({ serverStatus: 1 })
);
```

`serverStatus` có thể trả khối lượng dữ liệu lớn; trong môi trường thật chỉ trích xuất metrics liên quan thay vì log toàn bộ output. Các nhóm metrics replication, network, storage/cache, operation counters và ticket/flow control có thể khác nhau theo phiên bản MongoDB.

Một công cụ monitoring tập trung (MongoDB Atlas hoặc hệ thống giám sát nội bộ) thường hữu ích hơn việc chạy thủ công các lệnh mỗi vài giây.

## 8. Bài thực hành ghi một document an toàn và quan sát sao chép

### 8.1. Chuẩn bị môi trường

Phần này là **tùy chọn**, chỉ chạy trên replica set thử nghiệm được phép ghi. Không cần tạo hoặc phá replica set hiện có.

Trong `mongosh` kết nối đến replica set với quyền tạo document trong một database test:

```javascript
const lab = db.getSiblingDB("mongo_oplog_row225_lab");
const events = lab.getCollection("events_demo");

const runId = "row225-" + new ObjectId().toHexString();
const eventId = new ObjectId();

print("database=" + lab.getName());
print("runId=" + runId);
print("eventId=" + eventId);
```

Không dùng collection nghiệp vụ thật hoặc các lệnh tạo hàng triệu document để “thử làm oplog đầy”. Việc này có thể làm ảnh hưởng secondary và thậm chí khiến oplog window rút ngắn trên môi trường dùng chung.

### 8.2. Ghi có xác nhận majority

```javascript
const result = events.insertOne(
  {
    _id: eventId,
    runId,
    kind: "REPLICA_SET_LAB",
    message: "Quan sát replication",
    createdAt: new Date()
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 10000
    }
  }
);

printjson(result);
printjson(events.findOne({ _id: eventId, runId }));
```

`w: "majority"` yêu cầu mức xác nhận ghi theo đa số voting data-bearing members phù hợp với cấu hình replica set. `wtimeout` giới hạn thời gian chờ mức xác nhận; nếu hết thời gian, thao tác **có thể đã được áp dụng**, nhưng client chưa nhận được xác nhận đúng mức yêu cầu.

**Không giải thích `writeConcernError` là insert chắc chắn không xảy ra**, và không tự retry bằng `_id` mới khi chưa đối soát.

### 8.3. Quan sát trạng thái sau ghi

```javascript
printjson(
  rs.status().members.map((member) => ({
    node: member.name,
    state: member.stateStr,
    optimeDate: member.optimeDate
  }))
);
```

Với một document rất nhỏ và replica set khỏe, lag có thể không đủ lớn để nhìn thấy bằng mắt. **Không thấy lag không có nghĩa MongoDB không dùng oplog**, và không cần cố gây lỗi mạng hoặc làm nghẽn node để minh họa.

Nếu có môi trường test được cấp quyền truy cập trực tiếp vào secondary, có thể đọc `local.oplog.rs` trên secondary để khảo sát các thao tác gần đây. Nhưng không dựa vào việc một item có trong oplog là bằng chứng duy nhất về mức xác nhận majority, và không lấy toàn bộ nội dung oplog của cluster thật ra log công khai.

### 8.4. Dọn đúng document đã tạo

Trước khi xóa:

```javascript
print("database=" + lab.getName());
print("runId=" + runId);
printjson(events.findOne({
  _id: eventId,
  runId
}));
```

Chỉ khi đúng document vừa tạo:

```javascript
const deletion = events.deleteOne({
  _id: eventId,
  runId
});

printjson(deletion);
print("remaining=" + events.countDocuments({
  _id: eventId,
  runId
}));
```

Xóa cũng tạo ra hoạt động replication bình thường. Không xóa toàn bộ test database hoặc `local.oplog.rs` để “dọn oplog”; oplog được quản lý bởi chính MongoDB.

## 9. Cách sizing oplog để đủ thời gian phục hồi

### 9.1. Bắt đầu từ thời gian secondary có thể bị ngắt

Một câu hỏi thiết kế thực tế:

> “Nếu một secondary mất kết nối 12 giờ để bảo trì hoặc gặp sự cố network, chúng ta muốn nó vẫn có khả năng bắt kịp mà không phải initial sync?”

Để trả lời, cần ước tính:

1. Khoảng thời gian gián đoạn lớn nhất chấp nhận được.
2. Thời gian cần để secondary **bắt kịp** sau khi kết nối lại.
3. Tốc độ sinh oplog bình thường và trong đợt cao điểm.
4. Dung lượng disk/capacity cho oplog trên các sync source.
5. Các đợt migration, bulk import, TTL delete hoặc cập nhật hàng loạt.
6. Khả năng chọn sync source khác và các thành viên intentionally delayed.

Chỉ lấy “thời gian downtime” làm mục tiêu window có thể quá sát: khi node quay lại, nó còn cần thời gian để đọc và áp dụng backlog trong lúc primary tiếp tục ghi.

### 9.2. Công thức ước lượng dung lượng

Một phép tính bước đầu:

\[
\text{Dung lượng oplog ước tính}
\approx
\text{Tốc độ sinh oplog theo giờ}
\times
\text{Số giờ lịch sử muốn giữ}
\times
\text{Hệ số dự phòng}
\]

Ví dụ đo được hệ thống tạo khoảng **1,2 GiB oplog/giờ** trong giai đoạn tham chiếu. Muốn lịch sử khoảng **24 giờ**, với hệ số dự phòng 2 cho biến động:

```text
1,2 GiB/giờ × 24 giờ × 2
= 57,6 GiB
```

Đây là **ước lượng phục vụ capacity planning**, không phải kết luận MongoDB tự bảo đảm 24 giờ khi oplog có kích thước 57,6 GiB. Khi workload thay đổi mạnh, phải đo lại cửa sổ thực tế và tốc độ tạo oplog.

### 9.3. Dữ liệu nào cần thu thập?

| Số liệu | Vì sao quan trọng |
| --- | --- |
| Dung lượng oplog được cấu hình trên từng member | Giới hạn lưu trữ ban đầu |
| Dung lượng dùng thực tế và kích thước lưu trên disk | Hiểu áp lực disk/cache |
| Oplog window hiện tại và lịch sử theo thời gian | Biết retention thực tế |
| Tốc độ sinh oplog/giờ trong giờ bình thường và peak | Dự đoán window khi tải biến động |
| Lag applied/durable trên mỗi secondary | Biết tiến độ bắt kịp |
| Network throughput, disk IOPS/latency, CPU, cache | Xác định điểm nghẽn |
| Số lần election, sync source changes, replication error | Tìm nguyên nhân gián đoạn |
| Thời lượng initial sync/maintenance đã xảy ra | Đặt mục tiêu headroom có dữ liệu |

Nên ghi nhận **p95/peak của tốc độ sinh oplog** hoặc các đợt tải đặc biệt, không chỉ tính trung bình cả tuần.

### 9.4. Tăng dung lượng oplog có tác dụng gì?

Khi tăng dung lượng oplog hợp lý, hệ thống có khả năng giữ nhiều lịch sử hơn để secondary bắt kịp sau thời gian gián đoạn. Nhưng:

- Tăng oplog **không tự làm secondary áp dụng nhanh hơn**.
- Nó **không khôi phục những mục đã bị loại khỏi lịch sử**.
- Nó tiêu tốn thêm dung lượng storage và cần theo dõi disk.
- Thay đổi có thể cần thực hiện/đánh giá **theo từng thành viên**.
- Cú pháp, quyền, giới hạn kích thước và khả năng thay đổi online phụ thuộc phiên bản MongoDB/managed service.

Trong môi trường tự quản lý, MongoDB có lệnh quản trị `replSetResizeOplog` ở những phiên bản hỗ trợ; không nên chạy thử trên replica set production chỉ vì thấy window ngắn. Với MongoDB Atlas/managed service, thay đổi cấu hình qua cơ chế nhà cung cấp hỗ trợ.

Một phương án tăng kích thước cần gắn với **mức disk còn trống, chính sách backup và việc theo dõi window sau khi thay đổi**.

### 9.5. Không dùng window làm mục tiêu duy nhất

Nếu secondary lag tăng liên tục do disk chậm, tăng oplog chỉ **mua thêm thời gian** trước khi quá cũ. Cần xử lý nguyên nhân apply chậm hoặc network chậm. Sizing oplog là biện pháp tăng độ chịu lỗi, không phải thay thế capacity planning và xử lý bottleneck.

## 10. Điều gì xảy ra khi secondary quá cũ?

### 10.1. Khoảng oplog cần thiết không còn ở nguồn

Để tiếp tục incremental sync, secondary phải lấy được các mục tiếp theo từ vị trí đã áp dụng. Nếu sync source không còn giữ những mục đó, MongoDB có thể báo tình trạng stale/too stale hoặc thông báo không tìm thấy lịch sử cần thiết.

Ví dụ:

```text
Secondary đã áp dụng tới:          06:00
Primary/sync source cũ nhất còn:   09:00
Primary mới nhất:                  14:00

Các thao tác 06:00–09:00 không còn ở nguồn.
```

Secondary không được bỏ qua khoảng này. Cách khôi phục phụ thuộc vào những sync source khác và tình trạng thực tế của replica set.

### 10.2. Có thể đổi sync source không?

Một secondary có thể có lựa chọn sync source khác còn lưu lịch sử dài hơn. Nhưng không nên mặc định luôn có nguồn như vậy:

- Các thành viên có kích thước oplog và window khác nhau.
- Khả năng chọn sync source bị ảnh hưởng bởi topology, health, cấu hình và phiên bản.
- Một thành viên có history dài nhưng không còn healthy hoặc không đủ điều kiện làm nguồn có thể không giúp được.

Nếu không có nguồn hợp lệ giữ đủ chuỗi oplog, cần đồng bộ lại dữ liệu của secondary bằng quy trình **initial sync/resync** được MongoDB hỗ trợ.

### 10.3. Initial sync là gì?

**Initial sync** xây dựng lại dữ liệu trên một thành viên từ một nguồn phù hợp rồi đưa thành viên về trạng thái có thể tiếp tục replication. Về mặt khái niệm, nó có thể gồm:

1. Chọn sync source.
2. Sao chép dữ liệu và cấu trúc cần thiết của database.
3. Sử dụng oplog để bắt kịp các thay đổi phát sinh trong lúc copy.
4. Hoàn tất đồng bộ và trở về trạng thái secondary đủ điều kiện.

Initial sync cần tài nguyên đáng kể: đọc dữ liệu trên nguồn, network, CPU, disk và thời gian. Nếu trong quá trình copy nguồn tạo oplog quá nhanh và phần lịch sử cần cho catch-up không còn, initial sync cũng có thể bị gián đoạn/phải thực hiện lại tùy tình huống.

### 10.4. Tuyệt đối không “sửa nhanh” bằng xóa oplog

Các thao tác **không nên làm** khi gặp secondary quá cũ:

- Tự `deleteMany` hoặc `drop` `local.oplog.rs`.
- Sửa giá trị `ts` để secondary “nhảy” tới thao tác mới.
- Xóa data directory khi chưa có backup, kế hoạch recovery và kiểm tra đúng member.
- Loại hoặc tái thêm thành viên theo cảm tính mà chưa đánh giá quorum/election.
- Reset oplog của primary để “tạo lịch sử mới”.

Đây là tác vụ vận hành có tác động lớn. Nếu cần resync, phải dùng quy trình chính thức theo **phiên bản MongoDB**, kiểm tra dữ liệu/backup, trạng thái primary, số thành viên voting và ảnh hưởng tới availability.

### 10.5. Tăng oplog sau khi stale có đủ không?

Nếu các mục cần thiết **đã bị loại**, tăng dung lượng oplog từ thời điểm đó **không tạo lại lịch sử đã mất**. Việc tăng kích thước có thể giúp ngăn sự cố tái diễn sau resync, nhưng không tự đưa stale secondary trở lại trạng thái nhất quán.

## 11. Nguyên nhân replication lag cao

### 11.1. Network và sync source

Nếu link giữa secondary và nguồn đồng bộ bị nghẽn hoặc có packet loss, oplog mới không được truyền kịp. Các chỉ báo cần xem:

- RTT và băng thông network giữa các node.
- Retry/connection reset hoặc lỗi kết nối.
- Thay đổi sync source liên tục.
- Độ trễ tăng trong một vùng dữ liệu hoặc một availability zone.

Không khẳng định network là nguyên nhân chỉ vì hai node ở khu vực địa lý khác nhau; cần số liệu thực tế.

### 11.2. Storage I/O và khả năng áp dụng oplog

Secondary cần đọc và ghi dữ liệu cục bộ khi áp dụng các thay đổi. Disk quá chậm, latency cao, cache thiếu hoặc quá nhiều operation phải áp dụng có thể khiến secondary tụt lại dù network vẫn tốt.

Một backup nặng hoặc truy vấn đọc lớn chạy trên secondary cũng có thể cạnh tranh tài nguyên với replication. Khi đó cần:

- Quan sát disk latency/IOPS và CPU.
- Xem cache pressure và throughput.
- Đánh giá workload đọc/backup trên secondary.
- Cân nhắc nâng cấp tài nguyên hoặc di chuyển công việc đọc nặng.

### 11.3. Primary tạo thay đổi nhanh hơn năng lực secondary

Một batch update, data import hoặc thao tác bulk lớn có thể tạo lượng oplog rất cao. Secondary dù hoạt động bình thường vẫn tụt lại nếu tốc độ apply nhỏ hơn tốc độ sinh oplog trong một khoảng dài.

Giải pháp có thể gồm giảm/constrain tốc độ batch, chia nhỏ công việc, thêm capacity hoặc điều chỉnh lịch bảo trì. Không tự động dừng mọi write nghiệp vụ khi lag tăng nếu chưa đánh giá tác động và ngưỡng an toàn.

### 11.4. Thành viên delayed hoặc đang initial sync

Lag chủ đích của delayed secondary, hoặc trạng thái initial sync, có mục đích và quy luật khác secondary bình thường. Monitoring nên phân loại vai trò của member trước khi phát cảnh báo.

### 11.5. Election và thay đổi topology

Khi primary đổi vai trò, những member có tiến độ khác nhau có thể bị ảnh hưởng bởi quá trình election/catch-up và điều kiện majority. Lag tăng ngắn hạn quanh election có thể đi cùng sự kiện failover.

Khi điều tra, cần kết hợp **timeline election, log server, majority commit point và trạng thái các thành viên**, không chỉ một số lag tại một thời điểm.

## 12. Oplog, write concern và mức nhất quán đọc

### 12.1. `w: 1` không chờ tất cả secondary

Ví dụ:

```javascript
db.orders.insertOne(
  { orderId: "EXAMPLE-1", status: "NEW" },
  { writeConcern: { w: 1 } }
);
```

Lệnh với `w:1` thường được xác nhận khi primary đáp ứng mức ghi yêu cầu; không cần đợi tất cả secondary sao chép xong. Nếu ngay sau đó đọc từ một secondary đang lag, document mới có thể **chưa xuất hiện**.

Do vậy, read preference chỉ tới secondary có thể gây **stale reads** so với trạng thái mới nhất trên primary. Đây là đặc tính cần được API và người sử dụng hiểu.

### 12.2. `w: "majority"` khác với lag bằng 0

```javascript
db.orders.insertOne(
  { orderId: "EXAMPLE-2", status: "NEW" },
  { writeConcern: { w: "majority" } }
);
```

`w:"majority"` yêu cầu thao tác được xác nhận theo majority của các voting data-bearing members phù hợp cấu hình. Nó giúp bảo đảm mức xác nhận mạnh hơn `w:1`, nhưng **không có nghĩa tất cả secondary đã áp dụng thao tác** tại thời điểm client nhận phản hồi.

Một secondary vẫn có thể lag dù write majority đã được xác nhận bởi các thành viên khác.

### 12.3. Read preference và stale reads

| Lựa chọn đọc | Hệ quả cần quan tâm |
| --- | --- |
| `primary` | Đọc từ primary theo chính sách driver; thường phù hợp khi cần dữ liệu mới nhất của node nhận ghi |
| `secondary` | Có thể giảm tải primary nhưng đọc dữ liệu chậm hơn |
| `secondaryPreferred` | Có thể chọn secondary khi khả dụng; độ mới phụ thuộc node được chọn |
| `nearest` | Ưu tiên thành viên có độ trễ network thích hợp; không đồng nghĩa dữ liệu mới nhất |

Một số driver cho phép thiết lập mức `maxStalenessSeconds` để tránh chọn secondary bị trễ vượt ngưỡng ước lượng, với các giới hạn tối thiểu và điều kiện hỗ trợ của MongoDB. Đây là **điều kiện lựa chọn node**, không phải cam kết rằng đọc luôn thấy đúng thao tác mới nhất.

### 12.4. Read concern majority có giải quyết mọi stale read?

Không. `readConcern: "majority"` hướng tới dữ liệu đã được majority commit theo semantics MongoDB, nhưng đọc trên một secondary đang chậm vẫn có thể chưa phản ánh những ghi mới nhất đã xảy ra sau thời điểm mà secondary đó có thể phục vụ.

Phân biệt:

- **Committed/majority**: dữ liệu đáp ứng một mức nhất quán/độ bền cụ thể.
- **Fresh/latest**: dữ liệu phản ánh những thao tác vừa được ghi mới nhất.

Ứng dụng cần chọn read/write concern, read preference và session semantics (nếu cần causal consistency) theo mục tiêu; không dùng một chỉ số lag đơn lẻ để suy ra tất cả bảo đảm.

### 12.5. Rollback và quá trình đổi primary

Một thao tác được xác nhận với write concern yếu hơn có thể chưa được majority commit trước election. Trong những điều kiện failover, một số thay đổi chưa majority commit có thể bị **rollback** để replica set trở về lịch sử nhất quán.

Oplog liên quan trực tiếp tới tiến độ và lịch sử replication, nhưng **tính hiện diện của một mục oplog trên một node không tự chứng minh thao tác đó sẽ tồn tại sau mọi election**. Khi thiết kế dữ liệu quan trọng, xem xét write concern majority và các giới hạn của replication/rollback.

## 13. Ảnh hưởng tới change streams, backup và khôi phục

### 13.1. Change streams phụ thuộc lịch sử thay đổi

MongoDB change streams cho phép ứng dụng theo dõi các thay đổi được hỗ trợ từ collection, database hoặc deployment trong những điều kiện phù hợp. Cơ chế này có liên hệ với oplog và các mức bảo đảm replication.

Một consumer có thể nhận một **resume token** và dùng nó để tiếp tục sau khi mất kết nối. Nhưng nếu consumer ngừng xử lý quá lâu và lịch sử cần thiết đã rời khỏi oplog, thao tác resume có thể thất bại do **change stream history lost** hoặc điều kiện tương tự.

Vì thế:

- Oplog window ảnh hưởng tới khoảng thời gian consumer có cơ hội resume.
- Resume token không phải lời hứa lịch sử được giữ mãi mãi.
- Consumer nên lưu checkpoint bền vững, quản lý lỗi resume và có chiến lược full rescan/reconciliation khi history đã mất.
- Nếu cần event retention dài hạn, nên đồng bộ sang một hệ thống lưu sự kiện chuyên dụng thay vì phụ thuộc hoàn toàn vào oplog.

### 13.2. Oplog không thay thế backup

Oplog giúp secondary bắt kịp và hỗ trợ một số mô hình point-in-time recovery khi kết hợp với backup phù hợp. Nhưng bản thân `local.oplog.rs` **không phải một bản backup đầy đủ**:

- Nó chỉ là các thay đổi trong một cửa sổ hữu hạn.
- Không chứa đầy đủ một snapshot cơ sở của mọi dữ liệu.
- Có thể bị xoay vòng/truncated theo chính sách retention.
- Khả năng phục hồi cần backup nhất quán và chuỗi lịch sử liên tục phù hợp.

Với yêu cầu khôi phục đến một thời điểm, thiết kế backup/PITR theo khả năng của dịch vụ MongoDB và kiểm tra phục hồi định kỳ. Không dựa vào việc “oplog đang còn 24 giờ” để coi hệ thống đã có khả năng phục hồi 24 giờ.

### 13.3. Một sự cố có thể ảnh hưởng nhiều hệ thống tiêu thụ lịch sử

Nếu oplog window rút ngắn mạnh:

1. Secondary ngắt lâu có nguy cơ trở nên quá cũ.
2. Change stream consumer bị ngắt lâu có nguy cơ không resume được.
3. Quy trình backup/PITR phụ thuộc lịch sử liên tục có thể cần đánh giá lại theo thiết kế.

Điều này khiến oplog window trở thành **chỉ số vận hành quan trọng của cả hệ sinh thái dữ liệu**, không chỉ cho riêng replication.

## 14. Quy trình xử lý sự cố khi lag tăng

### 14.1. Xác định mức độ khẩn cấp

Trước tiên thu thập:

- Thành viên nào đang lag? Bao nhiêu?
- Member là secondary bình thường, delayed secondary hay đang initial sync?
- Oplog window trên sync source hiện là bao nhiêu?
- Lag đang **tăng, ổn định hay giảm**?
- Có lỗi heartbeat, election, network hoặc disk không?
- Primary có đang chạy batch import/migration hoặc cập nhật hàng loạt?
- Các thành viên còn healthy đủ quorum không?

Thứ tự ưu tiên xử lý phụ thuộc availability, RPO/RTO, mô hình cụm và headroom còn lại.

### 14.2. Mô hình phân loại nhanh

| Quan sát | Cách diễn giải ban đầu | Hướng điều tra |
| --- | --- | --- |
| Lag nhỏ, window dài, ổn định | Khả năng bình thường | Tiếp tục monitoring |
| Lag tăng, window vẫn đủ lớn | Secondary đang chậm nhưng còn khoảng đệm | Network, disk, CPU, apply throughput |
| Lag tăng nhanh, window co nhanh | Nguy cơ thiếu lịch sử | Burst writes, backlog, capacity và headroom |
| Lag lớn đúng bằng độ trễ cấu hình | Có thể là delayed secondary | Kiểm tra member config và mục tiêu delayed |
| Member không liên lạc nhiều giờ | Nguy cơ không có oplog cần thiết | Health/network, vị trí optime, sync source |
| Member báo too stale | Incremental catch-up có thể không còn khả thi | Xem nguồn có lịch sử khác hoặc quy trình resync |
| Một số node election liên tục | Topology không ổn định | Quorum, network, disk, log election |
| Lag nhỏ nhưng API đọc dữ liệu cũ | Có thể chọn secondary hoặc read semantics không phù hợp | Read preference/read concern/session |

Đây là bảng định hướng điều tra, không phải cây quyết định để tự động can thiệp cụm.

### 14.3. Những bước giảm rủi ro ít xâm lấn

Tùy môi trường và quyền vận hành, có thể:

1. Theo dõi cửa sổ oplog thường xuyên hơn trong lúc tăng tải.
2. Giảm tốc độ **batch không cấp thiết** tạo nhiều oplog, nếu được phép và không gây rủi ro nghiệp vụ.
3. Xử lý sự cố network, I/O hoặc thiếu capacity của secondary.
4. Kiểm tra tác vụ đọc/backup đang chiếm quá nhiều tài nguyên trên secondary.
5. Đánh giá tăng dung lượng oplog để tránh thiếu lịch sử về sau.
6. Lập kế hoạch resync nếu member đã mất khả năng catch-up.

Đừng tùy tiện dừng primary, thay voting config hoặc xóa thư mục dữ liệu khi chưa hiểu tác động tới majority.

### 14.4. Chứng minh secondary đang bắt kịp

Không chỉ quan sát “lag đã giảm một lần”. Nên theo dõi **chuỗi số liệu**:

```text
Time      Lag    Window    Headroom
-----------------------------------
10:00     45m     10h       9h15m
10:10     39m      9h       8h21m
10:20     27m      9h       8h33m
10:30     15m      9h       8h45m
```

Ví dụ này cho thấy secondary có xu hướng catch-up. Nhưng nếu window co từ 10 giờ xuống 20 phút chỉ trong thời gian ngắn thì tình hình rủi ro sẽ khác; cần luôn kết hợp lag và window.

### 14.5. Sau sự cố, cập nhật capacity planning

Một postmortem nên trả lời:

- Điều gì tạo ra lag? Network, disk, spike ghi hay election?
- Oplog window nhỏ nhất quan sát được là bao nhiêu?
- Headroom có bị xuống mức nguy hiểm không?
- Alert có phát sớm và đủ ngữ cảnh không?
- Thành viên có cần initial sync không? Mất bao lâu?
- Change stream consumer hoặc backup có bị ảnh hưởng không?
- Có cần thay kích thước oplog, lịch batch, phân bổ tài nguyên hoặc topology không?

Những kết luận này phải dựa trên log và metric thực tế, không chỉ dựa vào thông số cấu hình tối đa.

## 15. Thiết kế cảnh báo: không chỉ đặt một ngưỡng lag cố định

### 15.1. Ba nhóm cảnh báo quan trọng

**Nhóm 1 — Tiến độ secondary**

- Lag hiện tại.
- Tốc độ tăng lag.
- Thời gian secondary mất liên lạc.
- Trạng thái member (SECONDARY, RECOVERING, STARTUP2, v.v.).

**Nhóm 2 — Lịch sử còn giữ**

- Oplog window hiện tại.
- Mức window thấp nhất trong các đợt ghi cao điểm.
- Ước lượng headroom theo thành viên và sync source.
- Tốc độ tăng kích thước dữ liệu/oplog.

**Nhóm 3 — Năng lực và tính sẵn sàng**

- Disk I/O và latency.
- Network health.
- Số thành viên healthy, majority/quorum.
- Election/rollback/initial sync errors.
- Lỗi change stream resume hoặc backup.

Một alert “lag trên 30 giây” có thể hợp lý với API cần đọc gần realtime, nhưng không đủ bảo vệ member nếu window đột ngột co xuống vài phút. Ngược lại, delayed secondary có thể cố ý lag nhiều giờ mà không cần alert kiểu secondary bình thường.

### 15.2. Cảnh báo theo tỷ lệ headroom

Một mô hình đánh giá rủi ro:

```text
Risk indicators:

 - lag tăng liên tục
 - window giảm liên tục
 - lag tiến gần window
 - secondary mất kết nối
 - catch-up throughput < new oplog throughput
```

Không áp dụng một ngưỡng toán học duy nhất cho mọi replica set. Khi window chỉ còn sát lag, chỉ số đo theo giây, sync source và backlog thực tế đều có sai số/độ trễ. Nên cảnh báo **sớm hơn mức 0 headroom**, với biên an toàn do SRE/DBA xác định từ kinh nghiệm vận hành.

### 15.3. Đo theo mỗi thành viên

Mỗi node có:

- Tài nguyên riêng.
- Kết nối network riêng.
- Vị trí oplog/optime riêng.
- Kích thước và window oplog có thể khác.
- Vai trò và cấu hình đặc biệt có thể khác.

Vì vậy monitoring nên hiển thị **theo thành viên** và theo replica set tổng thể. Một số trung bình toàn cụm có thể che một secondary đang nguy cấp.

## 16. Các hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
| --- | --- |
| “Oplog là toàn bộ lịch sử thay đổi từ ngày tạo collection” | Oplog được giữ có giới hạn và có thể xoay vòng |
| “Oplog 20 GiB nghĩa là giữ đúng 20 giờ” | Window phụ thuộc tốc độ sinh oplog và retention |
| “Lag 0 nghĩa là mọi node giống hệt tại mọi thời điểm” | Số đo lag có độ phân giải, trễ lấy mẫu và semantics riêng |
| “Replica set sao chép đồng bộ ngay lập tức tới tất cả node” | Replication thường bất đồng bộ |
| “Secondary luôn kéo oplog trực tiếp từ primary” | Có thể chọn secondary khác làm sync source |
| “Primary có oplog window 48 giờ thì mọi member đều có window 48 giờ” | Oplog cục bộ và cấu hình mỗi member có thể khác |
| “Secondary lag 8 giờ, window 6 giờ chắc chắn còn catch-up vì primary healthy” | Có nguy cơ không còn lịch sử; cần kiểm tra vị trí oplog và sync source |
| “Chỉ tăng kích thước oplog là lag sẽ giảm” | Lag do tốc độ fetch/apply; resize chỉ tăng khả năng giữ lịch sử |
| “Tăng oplog sẽ phục hồi mục đã mất” | Mục đã loại không tự được tạo lại |
| “Xóa `local.oplog.rs` để reset replication” | Có thể làm hỏng dữ liệu/trạng thái replication; không được thao tác thủ công |
| “`w:majority` nghĩa tất cả secondary đã cập nhật” | Chỉ yêu cầu mức xác nhận theo majority phù hợp |
| “Đọc với `readConcern:majority` luôn là đọc mới nhất” | Dữ liệu majority-committed không đồng nghĩa freshest trên secondary lag |
| “Oplog có thể thay event store hoặc audit log vĩnh viễn” | Oplog không được thiết kế cho retention dài hạn |
| “Change stream resume token luôn dùng được” | Có thể mất lịch sử cần resume khi oplog bị rotate |
| “Chỉ nhìn lag là đủ đánh giá sức khỏe replication” | Cần window, headroom, tài nguyên, topology và write rate |
| “Một `mongosh` qua mongos có thể xem trực tiếp `local.oplog.rs` của mọi shard” | Cần kết nối và quyền phù hợp trên từng replica set member |

## 17. Tình huống thực hành suy luận

### 17.1. Bài A: đánh giá catch-up

Cho:

```text
Oplog cũ nhất trên sync source: 14:00
Oplog mới nhất:               20:00
Secondary đã áp dụng tới:     18:00
```

Hãy xác định:

1. Window xấp xỉ bao nhiêu giờ?
2. Lag xấp xỉ bao nhiêu giờ?
3. Headroom xấp xỉ bao nhiêu giờ?
4. Nếu primary tăng write rate gấp 10, cần theo dõi dấu hiệu gì?

Gợi ý: window ~6 giờ; lag ~2 giờ; headroom ~4 giờ. Đây là ước lượng, còn khả năng catch-up thực tế phụ thuộc lịch sử và tốc độ apply.

### 17.2. Bài B: secondary mất kết nối quá lâu

```text
Secondary last applied: 07:00
Sync source oldest:     10:00
Sync source newest:     17:00
```

Hãy giải thích:

- Vì sao không thể chỉ lấy các mục oplog từ 10:00 đến 17:00 để tiếp tục?
- Có thể kiểm tra điều gì ở một sync source khác?
- Khi nào cần initial sync?
- Vì sao tăng oplog ngay lúc này không tự phục hồi lịch sử 07:00–10:00?

### 17.3. Bài C: burst migration

Replica set thường có window 30 giờ và lag dưới 10 giây. Trong một đợt import lớn, window co còn 4 giờ, secondary lag 3 giờ 30 phút.

Hãy thiết kế phản ứng:

1. Metric nào cần kiểm tra ngay?
2. Batch import có thể được giảm tốc an toàn không?
3. Disk và network trên secondary có đủ không?
4. Khi nào cân nhắc tăng oplog?
5. Alert nào lẽ ra cần phát trước?

Không đề xuất xóa oplog, resync vô điều kiện hoặc giảm write concern để “làm sạch lag” mà chưa hiểu tác động nghiệp vụ.

### 17.4. Bài D: majority write nhưng secondary đọc cũ

Một ứng dụng ghi order với `w:"majority"`, sau đó đọc với read preference `secondary` và không thấy order ngay.

Hãy giải thích vì sao điều này có thể xảy ra dù ghi đã được majority acknowledged. Nếu API cần read-your-writes, cần xem những chính sách nào liên quan đến session, read preference và read concern?

### 17.5. Bài E: change stream consumer bị ngắt

Một consumer lưu resume token, ngừng hoạt động 36 giờ, trong khi oplog window ngắn nhất trong thời gian đó chỉ 12 giờ.

Hãy giải thích vì sao consumer có thể không tiếp tục được từ token cũ. Nêu phương án đối soát dữ liệu, checkpoint và chiến lược event retention nếu yêu cầu business là xử lý không mất sự kiện.

## 18. Tài liệu tham khảo chính thức

Các chi tiết vận hành chịu ảnh hưởng của phiên bản MongoDB, cấu hình cluster và dịch vụ quản lý. Khi thao tác thật, tham khảo tài liệu **của đúng phiên bản đang triển khai**:

- [Replica Set Oplog — MongoDB Manual](https://www.mongodb.com/docs/manual/core/replica-set-oplog/): vai trò oplog, size và retention.
- [Replica Set Data Synchronization](https://www.mongodb.com/docs/manual/core/replica-set-sync/): đồng bộ dữ liệu và catch-up.
- [rs.status()](https://www.mongodb.com/docs/manual/reference/method/rs.status/): quan sát thành viên và tiến độ.
- [rs.printReplicationInfo()](https://www.mongodb.com/docs/manual/reference/method/rs.printReplicationInfo/): quan sát oplog window và kích thước.
- [rs.printSecondaryReplicationInfo()](https://www.mongodb.com/docs/manual/reference/method/rs.printSecondaryReplicationInfo/): thông tin replication của secondary.
- [replSetGetStatus](https://www.mongodb.com/docs/manual/reference/command/replSetGetStatus/): trạng thái replica set.
- [replSetResizeOplog](https://www.mongodb.com/docs/manual/reference/command/replSetResizeOplog/): quản trị kích thước oplog trong môi trường hỗ trợ.
- [Read Concern "majority"](https://www.mongodb.com/docs/manual/reference/read-concern-majority/): semantics dữ liệu majority-committed.
- [Change Streams](https://www.mongodb.com/docs/manual/changeStreams/): stream thay đổi và resume.

## 19. Kết luận

**Oplog** là lịch sử thao tác nội bộ giúp các secondary của MongoDB replica set sao chép những thay đổi từ sync source. Vì lịch sử được giữ có giới hạn, **oplog window** quyết định khoảng thời gian còn có thể truy xuất từ một nguồn; còn **replication lag** cho biết secondary đang chậm hơn bao nhiêu so với tiến độ được quan sát.

Khi **lag tăng** trong lúc **window co lại**, khả năng secondary bắt kịp trở nên nguy hiểm. Nếu những mục cần thiết đã không còn trên bất kỳ sync source phù hợp nào, secondary có thể phải initial sync lại; tăng oplog sau đó không hồi sinh lịch sử đã mất. Để vận hành an toàn, cần theo dõi window, lag, headroom, thông lượng sinh và áp dụng oplog, sức khỏe từng node và mức xác nhận ghi — đồng thời phân biệt những chỉ số này với read freshness, majority commit và khả năng phục hồi backup.

**Thông điệp quan trọng nhất:** đừng chỉ hỏi “secondary đang chậm bao nhiêu giây?”, mà hãy hỏi **“nguồn còn giữ đủ lịch sử để secondary bắt kịp, với biên an toàn trước tải cao điểm, hay không?”**
