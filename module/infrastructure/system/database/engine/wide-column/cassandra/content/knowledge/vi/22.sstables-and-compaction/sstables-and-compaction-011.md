# Điều kiện loại bỏ phiên bản cũ hoặc tombstone

> **Chương:** SSTable và compaction  
> **Phạm vi:** Apache Cassandra, cơ sở dữ liệu phân tán theo mô hình *wide-column*. Bài giải thích cách Cassandra hợp nhất các phiên bản trong SSTable, điều kiện thu hồi tombstone, rủi ro **zombie data**, và cách đánh giá bằng CQL, công cụ vận hành cùng ứng dụng Java.

## 1. Vì sao dữ liệu “đã thay” hoặc “đã xóa” vẫn còn trên đĩa?

Cassandra sử dụng kiến trúc **LSM-tree**. Ghi mới đi vào commit log và memtable; khi memtable flush, dữ liệu được ghi thành **SSTable bất biến**. Cassandra không sửa tại chỗ một SSTable cũ mỗi khi có lệnh `UPDATE` hoặc `DELETE`.

Vì vậy:

- Ghi `city = 'Huế'` sau `city = 'Hà Nội'` có thể làm **hai phiên bản của cùng cell** tồn tại trong các SSTable khác nhau.
- Lệnh `DELETE` thường ghi một **tombstone** — dấu xóa kèm timestamp — để những bản sao hoặc SSTable cũ không được xem là dữ liệu sống.
- Khi `SELECT`, Cassandra hòa giải các giá trị và dấu xóa nhìn thấy trên đường đọc để trả về trạng thái logic mới nhất theo quy tắc timestamp.
- **Compaction** đọc các SSTable đầu vào, hợp nhất những phiên bản liên quan và tạo SSTable mới, qua đó có thể bỏ dữ liệu thừa nếu việc bỏ đó an toàn.

Điểm khó không phải “Cassandra có thể xóa file khi nào?”, mà là:

> **Khi nào một phiên bản cũ chắc chắn đã bị che khuất, và khi nào một tombstone đã có thể biến mất mà không làm dữ liệu cũ sống lại?**

Hai câu hỏi này **không có cùng một điều kiện**.

## 2. Mô hình dữ liệu và hai loại “phiên bản cũ”

Một giá trị trong Cassandra mang timestamp ở mức vi giây; thông thường, mutation có timestamp lớn hơn sẽ thắng khi hòa giải cùng cell. Để dễ học, giả sử thời gian tăng và không có hai mutation cùng timestamp.

```text
Tại cùng khóa user_id='u-42', cột city

SSTable A: city='Hà Nội'   @ timestamp 100
SSTable B: city='Huế'      @ timestamp 200

SELECT city  ->  'Huế' (bản có timestamp thắng)
```

Phiên bản `'Hà Nội'` ở SSTable A là **phiên bản bị che khuất** (*shadowed/obsolete version*). Nó không còn là kết quả truy vấn khi bản `'Huế'` có hiệu lực và được hòa giải.

Nếu sau đó người dùng xóa cột:

```text
SSTable C: DELETE city     @ timestamp 300
           (tombstone)

SELECT city  ->  null / không có giá trị sống
```

Tombstone ở timestamp 300 **phải tiếp tục che khuất** cả phiên bản 200 và 100 ở những nơi chúng còn tồn tại. Nếu xóa dấu xóa quá sớm, Cassandra có thể “nhìn lại” giá trị cũ và cho rằng nó vẫn sống.

### Bảng phân biệt

| Đối tượng | Ý nghĩa | Điều kiện an toàn để loại bỏ |
| --- | --- | --- |
| Phiên bản dữ liệu cũ, ví dụ `city='Hà Nội' @100` | Bị phiên bản mới `@200` che khuất | Khi compaction có đủ thông tin để chứng minh phiên bản cũ không còn cần cho kết quả hòa giải; phụ thuộc những dữ liệu khác có thể còn ở SSTable ngoài lần compaction |
| Tombstone, ví dụ `DELETE city @300` | Dấu xóa các giá trị cùng phạm vi có timestamp cũ hơn | Ngoài đủ tuổi theo quy tắc GC, phải chứng minh việc bỏ dấu xóa không cho dữ liệu cũ ở SSTable khác hoặc replica khác quay lại |
| Giá trị sống mới, ví dụ `city='Đà Nẵng' @400` | Ghi sau dấu xóa `@300` | Dấu xóa cũ không che được dữ liệu mới này, nhưng có thể vẫn cần để che các giá trị `@100`/`@200` chưa được hợp nhất |

**Không dùng một mốc “đã đủ 10 ngày” để quyết định xóa tất cả phiên bản cũ.** `gc_grace_seconds` chủ yếu liên quan đến tính đủ điều kiện thu hồi **tombstone**, còn phiên bản sống cũ bị ghi đè được xử lý theo logic hợp nhất và che khuất của compaction.

## 3. Compaction nhìn thấy gì, và điều gì còn ở ngoài?

Giả sử một partition xuất hiện trong ba SSTable:

```text
SSTable S1                  SSTable S2                SSTable S3
city='Hà Nội' @100          city='Huế' @200           DELETE city @300
          \                      |                        /
           \                     |                       /
            +---- đọc hợp nhất theo timestamp ---------+
                                    |
                         Trạng thái logic: đã xóa
```

Nếu compaction chọn **cả S1, S2 và S3**, nó có thể xét các phiên bản và dấu xóa trong cùng lần hợp nhất. Sau khi đủ điều kiện GC và được chứng minh không còn dữ liệu bị che khuất ngoài tập đầu vào, Cassandra có thể thu hồi các giá trị obsolete cùng tombstone.

Nếu compaction **chỉ chọn S3**, thì:

- S1 và S2 vẫn nằm ngoài lần compaction.
- Xóa tombstone trong S3 sẽ để lại những giá trị cũ ở S1/S2.
- Khi đọc lại partition, giá trị cũ có thể trở thành kết quả nếu không còn dấu xóa nào bảo vệ nó.

Bởi vậy, Cassandra không thể chỉ dựa vào tuổi của tombstone hoặc thực tế “S3 đã được compact” để kết luận nó được phép bỏ dấu xóa. Việc kiểm tra **SSTable chồng lấp/khả năng chứa dữ liệu cũ** là một phần quan trọng của quyết định thu hồi.

### “Chồng lấp” không chỉ là cùng tên partition nhìn thấy bằng mắt

Hệ thống phải xét metadata liên quan đến phạm vi token, khóa, timestamp và các SSTable có thể chứa dữ liệu bị dấu xóa che khuất. Một tombstone có thể áp dụng cho:

- **Cell**: xóa một cột.
- **Row**: xóa một hàng.
- **Range**: xóa một khoảng clustering rows.
- **Partition**: xóa dữ liệu trong cả partition thuộc phạm vi dấu xóa.

Do phạm vi khác nhau, một ví dụ chỉ có một cell không thể thay thế kiểm tra an toàn cho tombstone hàng, range hoặc partition. Những cơ chế cụ thể để xác định SSTable đầu vào/đầu ra và ngưỡng GC thay đổi theo phiên bản và compaction strategy.

## 4. Điều kiện loại bỏ phiên bản dữ liệu bị ghi đè

Khi compaction đọc đồng thời một giá trị cũ và một giá trị mới ở cùng cell, Cassandra hòa giải timestamp rồi có thể không ghi phiên bản cũ vào SSTable kết quả.

Ví dụ:

```text
Trước compaction:
  S1: nickname='An'  @100
  S2: nickname='Bình' @200

Compaction S1 + S2:
  Output: nickname='Bình' @200
  Phiên bản 'An' @100 không cần giữ trong output.
```

Tuy nhiên, chỉ được nói “cũ hơn là bỏ được” khi **ngữ cảnh đầy đủ**:

1. Hai giá trị thực sự thuộc cùng khóa/cell và có quan hệ timestamp xác định.
2. Lần hợp nhất đã thấy dữ liệu cần thiết để xác nhận phiên bản bị che khuất.
3. Không có dữ liệu/dấu xóa hoặc ràng buộc ngoài tập SSTable đầu vào khiến lựa chọn bỏ phiên bản trở nên không an toàn.
4. Compaction hoàn tất thành công; SSTable đầu ra được tạo và thay thế đầu vào theo quy trình lưu trữ.

Các bản ghi bị ghi đè không có yêu cầu “chờ `gc_grace_seconds` như tombstone” chỉ vì chúng cũ. Nhưng việc loại bỏ vật lý vẫn có thể **bị trì hoãn vô hạn** nếu compaction phù hợp không diễn ra. SSTable là bất biến, nên nếu không compact, có thể tồn tại nhiều phiên bản trên đĩa dù `SELECT` chỉ trả một giá trị.

### Timestamp không phải đồng hồ thời gian thực tuyệt đối

CQL cho phép chỉ định timestamp mutation; timestamp quyết định thứ tự hòa giải, không phải lúc nào cũng tương ứng thứ tự nhận request. Đồng hồ client hoặc node lệch lớn có thể tạo bản ghi mang timestamp bất thường. Vì vậy:

- Một `UPDATE` gửi sau chưa chắc thắng một `UPDATE` trước nếu timestamp của nó nhỏ hơn.
- Một tombstone có timestamp không đúng có thể che dữ liệu ngoài dự kiến.
- Đừng tự đọc “mới nhất” thành “request đến cuối cùng” nếu ứng dụng đặt timestamp tùy ý.

Khi hai mutation có cùng timestamp, Cassandra có quy tắc giải quyết xung đột riêng, bao gồm ưu tiên dấu xóa trong một số trường hợp. Đối với bài thực hành, hãy dùng các thời điểm khác nhau để không phụ thuộc vào tie-breaking.

## 5. Tombstone được sinh ra bằng cách nào?

Tombstone không chỉ đến từ câu lệnh `DELETE`. Nó có thể phát sinh bởi:

| Nguồn | Ví dụ | Khi nào trạng thái logic bị xóa? |
| --- | --- | --- |
| Xóa cột | `DELETE city FROM ...` | Khi mutation xóa có hiệu lực theo timestamp |
| Xóa hàng/partition | `DELETE FROM ... WHERE ...` | Khi dấu xóa che các dữ liệu thuộc phạm vi |
| Xóa khoảng clustering | `DELETE ... WHERE clustering >= ... AND ...` ở schema/cú pháp phù hợp | Khi dấu xóa range che các rows thuộc khoảng |
| TTL hết hạn | `INSERT ... USING TTL 60` | Khi TTL hết hạn; dữ liệu trở thành không còn sống và cần metadata xóa |
| Ghi `null` vào cột được phép qua driver/CQL | Mutation xóa cell tương ứng trong các trường hợp hỗ trợ | Có thể tạo tombstone thay vì ghi một giá trị sống `null` |

Cần phân biệt **kết quả đọc logic** và **thu hồi lưu trữ vật lý**. Ngay sau khi một câu `DELETE` có hiệu lực, `SELECT` có thể không trả dữ liệu cũ nữa. Nhưng tombstone có thể phải tồn tại nhiều ngày trên đĩa để bảo vệ hệ thống phân tán.

### Hai loại thời gian quan trọng trong một tombstone

Tombstone mang thông tin phục vụ hai nhiệm vụ:

- **Timestamp xóa** (thường gọi là `markedForDeleteAt` trong mô tả nội bộ): dùng khi hòa giải xem dấu xóa có che một phiên bản dữ liệu hay không.
- **Thời điểm xóa cục bộ / local deletion time** (đơn vị giây): dùng để đánh giá tuổi tombstone so với ngưỡng thu hồi trong quá trình compaction.

Với dữ liệu TTL, thời điểm hết hạn cũng liên quan đến mốc nó trở thành dữ liệu chết và đủ tuổi cho GC. **Không nhầm timestamp mutation tính bằng microsecond với bộ đếm giây `gc_grace_seconds`.**

## 6. `gc_grace_seconds` thực chất bảo vệ điều gì?

`gc_grace_seconds` là thuộc tính cấp bảng quy định khoảng thời gian tối thiểu Cassandra giữ metadata xóa trước khi xem tombstone là **ứng viên** để thu hồi. Ví dụ:

```cql
CREATE TABLE lab.profile_by_user (
    user_id text PRIMARY KEY,
    nickname text,
    city text
) WITH gc_grace_seconds = 864000;
```

Ở đây `864000` giây tương đương 10 ngày, dùng làm **cấu hình minh họa**, không phải khuyến nghị chỉnh mọi hệ thống về 10 ngày.

Khi một tombstone vượt qua mốc grace, điều đó chỉ trả lời được:

> “Dấu xóa đã **đủ tuổi để xem xét** loại bỏ chưa?”

Nó **không** khẳng định:

- Tombstone sẽ biến mất ngay khi đồng hồ qua mốc.
- Dữ liệu cũ ở các SSTable khác đã được che khuất hoàn toàn.
- Mọi replica đã nhận hoặc được repair để biết về thao tác xóa.
- Tất cả bảng trong cluster đều có mức `gc_grace_seconds` giống nhau.
- `SELECT` sẽ ngừng gặp tombstone ngay sau khi kết thúc grace.

Cần có **compaction diễn ra sau đó** và các kiểm tra an toàn tương ứng mới có thể thu hồi dấu xóa trên SSTable.

### Ba điều kiện tư duy để GC một tombstone

| Điều kiện | Câu hỏi cần hỏi |
| --- | --- |
| **Đủ tuổi** | Tombstone đã vượt ngưỡng GC tương ứng với `gc_grace_seconds`/cơ chế GC của phiên bản chưa? |
| **An toàn trong tập SSTable trên node** | Nếu bỏ dấu xóa, liệu có phiên bản cũ còn nằm trong SSTable khác mà nó đang che không? |
| **An toàn trong cụm replica** | Các replica vắng mặt hoặc chưa được sửa có còn cơ hội đưa lại phiên bản cũ sau khi dấu xóa bị purge không? |

Hai điều kiện đầu thuộc kiểm tra/đường xử lý trên node; điều kiện cuối là **trách nhiệm vận hành của hệ phân tán**. Cassandra không thể tự suy ra tất cả replica ngoại tuyến đã nhận xóa chỉ từ tuổi một tombstone trên node đang hoạt động.

Một số phiên bản có thêm cơ chế hoặc cấu hình liên quan đến repair-aware tombstone GC. Không nên giả định cùng hành vi trên mọi bản Cassandra 3.x/4.x/5.x hoặc dịch vụ tương thích CQL; luôn đối chiếu tài liệu và cấu hình của cluster thực tế.

## 7. Vì sao xóa tombstone sớm có thể tạo “zombie data”?

Hãy xét keyspace có RF=3 với replica A, B, C:

```text
Thời điểm T0
  A: city='Hà Nội'     B: city='Hà Nội'     C: city='Hà Nội'

T1 — C ngừng hoạt động
  A, B đang online, C offline

T2 — DELETE city, được xác nhận bởi A và B
  A: tombstone @200    B: tombstone @200    C: bản cũ @100

T3 — Quá thời gian giữ tombstone, chưa repair thành công với C
  A/B compact và bỏ tombstone, không còn chứng cứ xóa
  C vẫn giữ bản cũ @100

T4 — C trở lại và đồng bộ/đọc dữ liệu
  Giá trị cũ @100 có thể được truyền lại hoặc thắng vì
  không còn tombstone nào đại diện cho thao tác xóa
              -> ZOMBIE DATA (dữ liệu sống lại)
```

Tại T2, nếu client dùng consistency level cho phép thành công khi một replica vẫn offline, C có thể bỏ lỡ xóa. Sau đó, **hint** có thể hỗ trợ chuyển tiếp mutation nhưng hint có thời hạn và không thay thế quy trình repair định kỳ. Nếu C vắng quá lâu, nó vẫn có thể giữ giá trị cũ.

Một lần repair hợp lệ trong khoảng thời gian bảo vệ giúp đưa dấu xóa đến replica đang thiếu nó hoặc hòa giải tình trạng dữ liệu trước khi dấu xóa bị purge. Nếu tombstone đã bị loại bỏ khỏi các replica lành trước khi C đồng bộ, rất khó phân biệt giá trị cũ trên C với một giá trị còn sống chỉ bằng dữ liệu hiện tại.

**Do đó, quản lý `gc_grace_seconds` gắn liền với lịch repair và thời gian replica có thể offline.** Giảm grace để sớm dọn dung lượng mà không bảo đảm repair/khôi phục node là quyết định rủi ro cao.

### Phân biệt repair, compaction và consistency level

- **Compaction:** gom SSTable **trên một node** và có thể loại bỏ dữ liệu thừa theo quy tắc.
- **Repair:** so sánh/đồng bộ dữ liệu giữa **các replica** cho phạm vi token tương ứng.
- **Consistency level (CL):** quy định số phản hồi replica cần thiết để một request hoàn tất; không chứng minh rằng mọi replica đã nhận DELETE.
- **Hinted handoff:** hỗ trợ giao mutation tới replica vắng mặt trong một cửa sổ nhất định; không thay thế repair khi node vắng lâu.

Một truy vấn `QUORUM` có thể nhất quán đủ cho lần đọc/ghi cụ thể, nhưng **không bảo đảm xóa đã đến toàn bộ replica trong thời gian dài**. Chính vì thế không thể xem CL cao là lý do duy nhất để đặt grace rất thấp.

## 8. Điều kiện SSTable chồng lấp: cạm bẫy “đủ ngày là xóa”

Giả sử tombstone ở SSTable S2 đã đủ tuổi:

```text
S1: order.status='PENDING' @100
S2: DELETE order.status    @200  (đã quá gc_grace)
S3: order.total=150000     @150

Compaction chỉ chọn S2:
  Nếu xóa tombstone @200 mà S1 vẫn ở ngoài compaction:
  SELECT order.status có thể trả lại 'PENDING' @100.
```

Điều kiện grace **không tự xử lý** vấn đề này. Cassandra phải xét các SSTable có thể chứa dữ liệu bị tombstone che khuất, phạm vi khóa và timestamp khi quyết định purge.

Các tình huống cần phân biệt:

1. **Tombstone và mọi giá trị bị che nằm trong cùng lần compaction, không có nguồn cũ nguy hiểm ở ngoài:** sau khi đủ điều kiện GC, dấu xóa và dữ liệu bị che có thể được bỏ khỏi output.
2. **Tombstone đủ tuổi nhưng có SSTable ngoài lần compaction vẫn có khả năng chứa giá trị cũ:** phải giữ dấu xóa hoặc dùng cơ chế kiểm tra an toàn tương ứng; không được xóa máy móc.
3. **Tombstone chưa đủ tuổi:** thường tiếp tục được giữ để hỗ trợ đồng bộ replica ngay cả nếu đọc hiện tại không còn giá trị sống.
4. **Không có compaction phù hợp:** cả tombstone lẫn phiên bản cũ có thể tồn tại trên đĩa lâu hơn grace.

**SSTable bị xóa khỏi thư mục sau compaction không đồng nghĩa tombstone đã biến mất.** Một SSTable đầu ra mới có thể vẫn chứa tombstone cần thiết.

## 9. Tác động của từng chiến lược compaction

Các compaction strategy ảnh hưởng **SSTable nào được chọn để hợp nhất** và **khi nào có cơ hội loại bỏ dữ liệu cũ**, chứ không xóa bỏ quy tắc an toàn của tombstone.

| Chiến lược | Cách nhìn ở bài toán này | Cần chú ý |
| --- | --- | --- |
| **STCS — SizeTieredCompactionStrategy** | Gom các SSTable có kích thước tương đương; nhiều thế hệ có thể tiếp tục chồng lấp | Tombstone nằm trong các file ngoài nhóm đang compact có thể chưa được dọn dù đã hết grace |
| **LCS — LeveledCompactionStrategy** | Tổ chức SSTable theo level và quản lý chồng lấp giữa các level | Hợp nhất theo level tạo cơ hội giảm dữ liệu thừa, nhưng không bảo đảm tombstone được GC tức thì |
| **TWCS — TimeWindowCompactionStrategy** | Gom SSTable theo cửa sổ thời gian, thường dùng cho time-series với TTL | Hữu ích khi dữ liệu có vòng đời tương đối đồng đều; dữ liệu đến muộn và ghi lại dữ liệu cũ có thể phá giả định về cửa sổ |
| **UCS — UnifiedCompactionStrategy (phiên bản hỗ trợ)** | Tùy chỉnh ưu tiên compaction theo workload và lựa chọn lưu trữ | Vẫn phải tôn trọng điều kiện che khuất và tuổi tombstone; không có lối tắt bảo đảm xóa ngay |

### TWCS và TTL: trường hợp đặc biệt dễ tối ưu nhưng cũng dễ sai

Với luồng sự kiện **chỉ ghi thêm**, TTL khá đồng nhất và không cập nhật dữ liệu cũ, SSTable thuộc một cửa sổ thời gian có thể dần chứa toàn dữ liệu đã hết hạn. Khi hội đủ điều kiện an toàn, việc bỏ cả SSTable đã hết hạn có thể tiết kiệm chi phí so với xử lý từng cell.

Nhưng không được suy ra:

> “Đã hết TTL và qua một cửa sổ TWCS thì có thể xóa file ngay.”

Nếu có bản ghi mới được ghi vào partition cũ, dữ liệu đến trễ, TTL không đồng nhất hoặc timestamp bất thường, SSTable có thể chứa dữ liệu còn sống. Ngoài ra tombstone còn liên quan đến repair và bảo vệ replica. Các cấu hình thúc đẩy xóa SSTable hết hạn theo cách thiếu kiểm tra an toàn có thể gây mất dữ liệu hoặc làm sống lại giá trị cũ; chỉ dùng khi đã chứng minh phù hợp với workload.

## 10. Thực hành CQL: xem trạng thái logic sau UPDATE và DELETE

Giả sử có keyspace `lab` được tạo sẵn và chỉ dùng trong môi trường học tập. Dùng bảng một partition/row để tập trung vào phiên bản cell:

```cql
CREATE TABLE IF NOT EXISTS lab.profile_by_user (
    user_id text PRIMARY KEY,
    nickname text,
    city text
) WITH gc_grace_seconds = 864000;
```

### Bước A — Ghi một phiên bản, rồi thay thế

```cql
INSERT INTO lab.profile_by_user (user_id, nickname, city)
VALUES ('u-42', 'Lan', 'Hà Nội');

UPDATE lab.profile_by_user
SET city = 'Huế'
WHERE user_id = 'u-42';

SELECT user_id, nickname, city
FROM lab.profile_by_user
WHERE user_id = 'u-42';
```

Sau hai mutation, Cassandra thường đọc ra `city='Huế'` nếu timestamp lần `UPDATE` lớn hơn timestamp cũ. Điều đó **không chứng minh SSTable cũ đã bị xóa vật lý**.

Bạn có thể kiểm tra timestamp logic của cell hiện hành:

```cql
SELECT city, WRITETIME(city)
FROM lab.profile_by_user
WHERE user_id = 'u-42';
```

`WRITETIME(city)` trả timestamp mutation của giá trị cell được chọn, không cho biết chính xác giá trị hiện đang nằm trong memtable hay SSTable nào.

### Bước B — Xóa một cell

```cql
DELETE city
FROM lab.profile_by_user
WHERE user_id = 'u-42';

SELECT user_id, nickname, city
FROM lab.profile_by_user
WHERE user_id = 'u-42';
```

`nickname` vẫn có thể còn sống, còn `city` được xem là không có giá trị. Lệnh `DELETE` tạo metadata xóa phù hợp, và log/compaction xử lý việc lưu trữ vật lý về sau.

Một sai lầm phổ biến là sau `SELECT` thấy `city=null` thì cho rằng SSTable không còn chứa giá trị `'Huế'`. Thực tế có thể còn cả giá trị cũ và tombstone ở các SSTable khác nhau.

### Bước C — TTL tạo dữ liệu sẽ hết hạn

Để quan sát TTL mà không cần xóa thủ công:

```cql
INSERT INTO lab.profile_by_user (user_id, nickname, city)
VALUES ('u-ttl', 'An', 'Đà Nẵng')
USING TTL 120;

SELECT nickname, TTL(nickname), WRITETIME(nickname)
FROM lab.profile_by_user
WHERE user_id = 'u-ttl';
```

Ngay sau khi ghi, `TTL(nickname)` phản ánh số giây sống còn lại (xấp xỉ). Sau khi TTL hết, dữ liệu không còn sống về mặt logic nhưng metadata expiration/deletion có thể còn trong SSTable cho tới khi đủ điều kiện GC và compaction.

Đừng xem thời điểm hết TTL là mốc phải có file bị xóa ngay: **TTL expiration**, **gc_grace** và **compaction vật lý** là ba khái niệm khác nhau.

### Bước D — Quan sát flush và compaction có kiểm soát

Ở môi trường lab trên node phù hợp:

```bash
nodetool tablestats lab.profile_by_user
nodetool compactionstats
```

Các thống kê này giúp quan sát số SSTable, tombstone/đọc, kích thước dữ liệu và công việc compaction đang chạy, tùy phiên bản Cassandra.

Nếu cần thí nghiệm về SSTable, có thể flush bảng trong **lab**:

```bash
nodetool flush lab profile_by_user
```

Lặp lại ghi/cập nhật/xóa, flush và quan sát qua thời gian để tạo các thế hệ SSTable. **Không đòi một số SSTable cố định hoặc tombstone biến mất ngay**; background compaction và chính sách tự động khiến kết quả khác nhau giữa các lần chạy.

Có thể dùng các công cụ như `sstablemetadata` hoặc `sstabledump` **trên bản sao môi trường lab với tệp cụ thể**, theo hướng dẫn của phiên bản, để quan sát metadata. Đó là cách phân biệt dữ liệu vật lý với kết quả `SELECT`. Tránh thao tác sửa/xóa trực tiếp file SSTable đang được Cassandra sử dụng.

## 11. Từ góc nhìn ứng dụng Java

Driver Java gửi mutation và truy vấn theo partition key; driver **không điều khiển việc purge tombstone**. Với bài toán ghi theo truy vấn và nhất quán đọc/ghi, ứng dụng nên:

1. Dùng partition key phù hợp để tránh đọc rộng tạo nhiều tombstone.
2. Phân biệt “xóa thành công theo consistency level” với “đã xóa vật lý ở mọi replica”.
3. Thận trọng khi retry `DELETE`/`UPDATE` trong bối cảnh timestamp và thao tác đồng thời; xác nhận tính idempotent của logic nghiệp vụ.
4. Nếu cần xóa dữ liệu trong thời hạn pháp lý hoặc bảo mật nghiêm ngặt, thiết kế quy trình xóa/retention/backup phù hợp; đừng dựa duy nhất vào `DELETE` hoặc gc_grace như lời bảo đảm xóa vật lý tức thì.

Ví dụ Java Driver 4.x:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class ProfileService {
    private final CqlSession session;
    private final PreparedStatement deleteCity;
    private final PreparedStatement readCity;

    public ProfileService(CqlSession session) {
        this.session = session;
        this.deleteCity = session.prepare(
            "DELETE city FROM lab.profile_by_user WHERE user_id = ?"
        );
        this.readCity = session.prepare(
            "SELECT city FROM lab.profile_by_user WHERE user_id = ?"
        );
    }

    public String removeAndReadCity(String userId) {
        BoundStatement delete = deleteCity.bind(userId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
        session.execute(delete);

        Row row = session.execute(
                readCity.bind(userId)
                    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM))
            .one();

        return row == null ? null : row.getString("city");
    }
}
```

Ví dụ giả định keyspace/table đã tồn tại, session được cấu hình topology đúng và RF thích hợp. Trả về `null` sau `DELETE` không có nghĩa commit log, SSTable hoặc mọi replica đã loại bỏ tombstone. Nó chỉ là kết quả đọc logic theo mức nhất quán và trạng thái nhìn thấy tại thời điểm đọc.

## 12. Chẩn đoán tombstone tồn tại lâu hoặc dữ liệu bị “sống lại”

| Hiện tượng | Kiểm tra đầu tiên | Hướng xử lý |
| --- | --- | --- |
| `DELETE` đã lâu, vẫn thấy tombstone khi đọc/tracing | Tuổi tombstone, `gc_grace_seconds`, SSTable overlap, lịch compaction | Xác định compaction phù hợp và lượng dữ liệu bị che; tránh ép GC vô điều kiện |
| Số lượng tombstone scanned cao trong một truy vấn | Partition key, clustering range, TTL/mô hình dữ liệu, số cell bị xóa | Giảm phạm vi đọc, điều chỉnh schema/TTL và access pattern |
| Disk không giảm dù nhiều dữ liệu đã TTL-expire | SSTable còn chứa dữ liệu sống, chính sách compaction, SSTable chồng lấp | Đo phần dữ liệu có thể thu hồi và chiến lược compaction trước khi thay cấu hình |
| Giá trị đã xóa xuất hiện trở lại sau node offline | Thời gian node offline, repair, hints, gc grace, timestamp | Điều tra zombie data và đồng bộ replica theo quy trình khôi phục; không tự xóa log hoặc SSTable |
| Repair không hoàn tất trước grace | Repair window, phạm vi token, node vắng và lỗi repair | Khôi phục lịch repair an toàn trước khi cân nhắc rút ngắn grace |
| Dọn tombstone bằng compaction gây tải I/O cao | Disk headroom, pending compactions, p99 đọc/ghi | Lập kế hoạch compaction, ưu tiên ổn định cluster và đo hiệu quả |

### Những bước kiểm tra an toàn

1. Xác định **keyspace, table, partition key** và kiểu tombstone (cell, row, range, partition, TTL).
2. Lấy thông tin **`gc_grace_seconds`** từ schema thực tế; đừng dựa vào giá trị mặc định truyền miệng.
3. Đo tuổi dữ liệu và dấu xóa, phân phối TTL, số SSTable và công việc compaction.
4. Xem lịch sử node offline/repair/hinted handoff và topology RF/CL.
5. Thử lại trên lab hoặc bản sao tải tương đương trước khi điều chỉnh compaction/GC ở production.

**Không xóa file SSTable hoặc ép `gc_grace_seconds = 0` như một mẹo dọn đĩa.** Nếu dữ liệu chưa được đồng bộ giữa replica hoặc tombstone còn che dữ liệu cũ, can thiệp như vậy có thể làm sai lệch dữ liệu và gây zombie.

## 13. Những phát biểu thường sai

**“Giá trị mới đã thắng trong SELECT, vậy giá trị cũ đã được xóa khỏi đĩa.”** Sai. Phiên bản cũ có thể tồn tại tới khi các SSTable được compact thích hợp.

**“Tombstone quá `gc_grace_seconds` là xóa ngay.”** Sai. Đó là ngưỡng xét đủ tuổi, không phải lịch hẹn xóa; cần compaction và kiểm tra an toàn.

**“GC tombstone chỉ cần nhìn một SSTable đang compact.”** Sai. Dữ liệu cũ bên ngoài tập đầu vào có thể bị lộ ra nếu tombstone biến mất.

**“Repair và compaction là cùng một bước.”** Sai. Compaction hợp nhất file trên node; repair đồng bộ replica. Cả hai liên quan đến an toàn xóa nhưng có vai trò khác nhau.

**“Dùng consistency QUORUM cho DELETE bảo đảm mọi replica đã nhận xóa.”** Sai. QUORUM không yêu cầu mọi replica phản hồi; replica vắng lâu có thể cần repair.

**“TTL hết thì dữ liệu bị xóa vật lý lập tức.”** Sai. TTL khiến dữ liệu hết hiệu lực logic; tombstone/metadata và GC vẫn có vòng đời riêng.

**“Dữ liệu cũ có timestamp thấp sẽ không bao giờ sống lại.”** Sai. Nếu tombstone mới đã bị purge khi còn replica giữ bản cũ, có thể phát sinh zombie data.

**“Compaction mạnh hơn luôn dọn được mọi tombstone.”** Sai. Compaction không thể bỏ qua điều kiện bảo vệ dữ liệu, và ép compaction có thể tiêu thụ I/O/disk lớn.

## 14. Bài tập phân tích

1. SSTable S1 có `nickname='A' @100`, S2 có `nickname='B' @200`. Khi compaction chọn cả hai và không có dữ liệu liên quan ở nơi khác, điều gì xảy ra với phiên bản `'A'`?
2. S1 có `city='Hà Nội' @100`, S2 có tombstone `DELETE city @200` đã vượt grace. Vì sao chỉ compact S2 chưa đủ để kết luận có thể xóa tombstone?
3. RF=3: replica C offline khi A và B nhận DELETE. Nếu A/B purge tombstone trước khi C được repair, tình huống nào có thể xảy ra khi C quay lại?
4. Giải thích khác nhau giữa *tombstone không còn hiển thị trong SELECT* và *tombstone được loại bỏ vật lý khỏi SSTable*.
5. Vì sao `gc_grace_seconds`, tần suất repair và thời gian node tối đa offline cần được xem xét cùng nhau?
6. Dữ liệu TTL đã hết hạn trên bảng dùng TWCS nhưng dung lượng đĩa chưa giảm. Hãy nêu ít nhất ba nguyên nhân hợp lý trước khi sửa cấu hình.
7. Nếu query quét nhiều tombstone, bạn sẽ xem lại partition key, TTL, delete pattern và compaction như thế nào?
8. Trong ứng dụng Java, sau lệnh `DELETE` trả thành công, bạn có thể khẳng định điều gì về kết quả đọc logic? Điều gì **chưa** thể khẳng định về SSTable và replica?

## 15. Tóm tắt quyết định

```text
Muốn bỏ PHIÊN BẢN CŨ?
    |
    +-- Có phiên bản mới che khuất cùng cell?
    |       |
    |       +-- Compaction đủ ngữ cảnh để hòa giải an toàn?
    |               -> Có thể bỏ phiên bản cũ khỏi SSTable đầu ra
    |
Muốn bỏ TOMBSTONE?
    |
    +-- Đủ tuổi theo chính sách GC?
            |
            +-- Không có dữ liệu cũ nguy hiểm ở SSTable khác?
                    |
                    +-- Đã xử lý rủi ro replica bỏ lỡ xóa
                         (repair/offline/hints trong cửa sổ an toàn)?
                             -> Có thể thu hồi khi compaction phù hợp
```

**Ghi nhớ:** Phiên bản sống bị ghi đè có thể bị loại bỏ khi compaction chứng minh nó không còn cần thiết. Tombstone phải được giữ lâu hơn vì nó là **bằng chứng của việc xóa** đối với cả SSTable cũ và replica phân tán. `gc_grace_seconds` chỉ là một phần của quyết định; **SSTable overlap, compaction, lịch repair và tình trạng replica** mới làm nên tính an toàn của việc thu hồi.
