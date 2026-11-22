# gc_grace_seconds và điều kiện giữ lại dấu xóa

Trong Apache Cassandra, xóa một giá trị không đồng nghĩa lập tức loại bỏ mọi byte của giá trị đó trên đĩa. Dữ liệu cũ có thể vẫn tồn tại trong các SSTable hoặc trên replica chưa nhận được thao tác xóa. Cassandra dùng **tombstone** — dấu xóa có thông tin thời gian — để che những phiên bản cũ ấy trong quá trình đọc và hợp nhất dữ liệu.

Vậy **bao lâu Cassandra phải giữ tombstone?** Cấu hình `gc_grace_seconds` là một phần quan trọng của câu trả lời, nhưng không phải toàn bộ. Sau khi hết khoảng grace, tombstone chỉ **có thể đủ điều kiện** được thu hồi; Cassandra còn phải cân nhắc các SSTable chứa dữ liệu cũ, trạng thái replica, compaction và cơ chế garbage collection của phiên bản đang chạy. Việc dọn dấu xóa quá sớm có thể tạo **zombie data**: dữ liệu đã xóa bỗng xuất hiện trở lại khi một replica cũ được đưa vào hệ thống.

Bài học thuộc chương **Tombstone và thu hồi** của module Apache Cassandra, kết nối kiến trúc wide-column phân tán, partition key, replication, consistency level, repair, compaction, CQL và ứng dụng Java.

Sau bài học, bạn có thể:

1. Giải thích chính xác ý nghĩa của `gc_grace_seconds` và vì sao nó **không phải lịch hẹn xóa vật lý**.
2. Phân biệt **write timestamp**, **local deletion time**, **TTL expiry** và **thời gian compaction**.
3. Mô tả cách replica bỏ lỡ DELETE dẫn đến nguy cơ dữ liệu sống lại.
4. Nhận diện các điều kiện giữ tombstone dù đã quá khoảng grace.
5. Lập lịch repair và quản lý node offline/khôi phục phù hợp với chính sách thu hồi dấu xóa.
6. Đánh giá tác động của TTL, compaction, kích thước phân vùng và truy vấn đọc qua tombstone.
7. Thực hành xem/đổi cấu hình bằng CQL, quan sát vận hành và dùng Java Driver một cách an toàn.

## 1. Tại sao cần một khoảng giữ dấu xóa?

Giả sử một partition có ba replica **A, B, C** theo chiến lược replication của keyspace. Trước khi xóa, cả ba đều chứa giá trị:

```text
payload = "temperature=38.1"
write timestamp = 100
```

Replica C bị mất kết nối. Ứng dụng gửi một lệnh `DELETE`; A và B nhận và ghi dấu xóa có write timestamp 200, trong khi C vẫn giữ giá trị cũ.

```text
               Trước khi xóa
       A                  B                  C
  payload @100       payload @100       payload @100

               C bị gián đoạn
       A                  B                  C
  DELETE @200        DELETE @200        payload @100
  payload @100       payload @100       (không thấy DELETE)

               Khi đọc/hòa giải đúng trạng thái
   Tombstone @200 có thể che payload @100 còn tồn tại.
```

Nếu A và B loại bỏ tombstone trong khi C chưa học được việc xóa, sau đó C quay lại, bản `payload @100` có thể trở thành bản dữ liệu sống còn được thấy và lan truyền. Hiện tượng này được gọi là **zombie data**.

Cassandra cần **duy trì thông tin xóa đủ lâu** để các replica từng bỏ lỡ deletion có cơ hội được đồng bộ thông qua cơ chế phù hợp như anti-entropy repair. Khoảng giữ dấu xóa cho mục đích này được kiểm soát một phần bằng `gc_grace_seconds` ở cấp bảng.

**Kết luận:** tombstone không phải phần thừa vô ích; nó mang **ngữ nghĩa xóa phân tán**. Hạ thời gian giữ dấu xóa là một quyết định về tính đúng dữ liệu, không chỉ tối ưu đĩa.

## 2. `gc_grace_seconds` là gì?

`gc_grace_seconds` là **thuộc tính của bảng Cassandra**, biểu thị khoảng thời gian tính bằng giây liên quan đến thời điểm một tombstone được phép xem xét **garbage collection**. Nó tạo một cửa sổ bảo vệ để replica đã bỏ lỡ mutation xóa có cơ hội được sửa trạng thái trước khi dấu xóa biến mất khỏi những nguồn có thể che giá trị cũ.

Ví dụ một cấu hình thường gặp trong Cassandra là:

```cql
CREATE TABLE device_events_by_day (
    tenant_id   text,
    device_id   uuid,
    event_day   date,
    occurred_at timestamp,
    event_id    uuid,
    payload     text,
    PRIMARY KEY (
        (tenant_id, device_id, event_day),
        occurred_at,
        event_id
    )
) WITH gc_grace_seconds = 864000;
```

`864000` giây tương đương **10 ngày**. Đây là giá trị mặc định thường thấy trong nhiều phiên bản Cassandra, nhưng **phải kiểm tra cấu hình thực tế của bảng và phiên bản đang vận hành**, không suy từ ví dụ.

### Những khẳng định đúng và sai

| Nhận định | Đánh giá | Diễn giải |
| --- | --- | --- |
| “`gc_grace_seconds` được tính bằng giây.” | Đúng. | Là table option, không phải thời lượng truy vấn. |
| “Nó liên quan đến thời gian tombstone cần được giữ.” | Đúng. | Gắn với an toàn xóa và nguy cơ replica bỏ lỡ mutation. |
| “Hết 10 ngày thì Cassandra chắc chắn xóa tombstone ngay.” | **Sai.** | Còn tùy compaction, SSTable overlap và điều kiện thu hồi. |
| “Có thể hạ nó để giải quyết mọi truy vấn chậm vì tombstone.” | **Sai.** | Có nguy cơ zombie data và chưa giải quyết nguồn tạo dấu xóa. |
| “Tăng consistency level làm `gc_grace_seconds` không còn tác dụng.” | **Sai.** | Consistency không đồng bộ mọi replica và không purge tombstone. |
| “Repair đúng phạm vi và đúng lịch quan trọng với cấu hình này.” | Đúng. | Cần bảo đảm replica không giữ lại phiên bản cũ khi dấu xóa được thu hồi. |

**Giới hạn ý nghĩa:** `gc_grace_seconds` không đặt TTL cho các cell sống, không quy định thời gian một partition được phép tồn tại, và không bảo đảm xóa dữ liệu khỏi snapshot/backup.

## 3. Bốn loại thời gian không được nhầm lẫn

Khi phân tích một tombstone, cần tách các mốc:

| Khái niệm | Đơn vị/nguồn | Dùng để làm gì? |
| --- | --- | --- |
| **Event time** | Ví dụ `occurred_at timestamp` do nghiệp vụ xác định | Định tuyến time bucket, clustering order, truy vấn lịch sử. |
| **Write timestamp** | Thường ở độ chính xác microsecond; gắn với mutation/cell | Hòa giải các phiên bản sống và tombstone, xử lý xung đột. |
| **Local deletion time** | Thông tin thời gian xóa/hết hạn trong metadata tombstone, thường ở độ phân giải giây | Xem tuổi dấu xóa để xét điều kiện garbage collection. |
| **Compaction time** | Thời điểm tiến trình compaction thực sự chạy | Cơ hội hợp nhất SSTable và thu hồi dữ liệu đã đủ điều kiện. |

Ví dụ khái niệm:

```text
Sự kiện nghiệp vụ xảy ra 08:00 UTC.

Ghi vào Cassandra lúc 08:03.
  write timestamp: T_write

DELETE lúc 09:00.
  write timestamp: T_delete, lớn hơn T_write
  local deletion time: thời điểm xóa được ghi nhận

Sau khoảng gc_grace_seconds:
  tombstone có thể đủ tuổi để xét thu hồi

Sau đó, khi compaction phù hợp chạy và đủ điều kiện:
  SSTable có thể được tổ chức lại để loại dữ liệu/dấu xóa.
```

**Write timestamp quyết định dữ liệu nào thắng**, còn **local deletion time** liên quan **tuổi tombstone để dọn**. Không lấy `occurred_at`, là clustering column nghiệp vụ, để tính tuổi tombstone.

### Đồng hồ và các timestamp do client chỉ định

Cassandra cho phép các mutation có write timestamp do client xác định trong các trường hợp được hỗ trợ. Việc dùng timestamp ở tương lai, dùng đồng hồ không đồng bộ hoặc ghi/xóa cạnh tranh với timestamp bất thường có thể làm kết quả hòa giải khó dự đoán.

Đừng tự ý đặt write timestamp cực lớn cho DELETE với ý định “xóa vĩnh viễn”. Dữ liệu hợp lệ ghi về sau có timestamp thấp hơn vẫn có thể bị dấu xóa che. Cần quản lý đồng hồ và semantics mutation có chủ đích.

## 4. Phân biệt xóa logic với thu hồi vật lý

Một lệnh xóa có hiệu lực logic ngay khi tombstone thắng các phiên bản liên quan theo semantics đọc và consistency. Nhưng tombstone và dữ liệu cũ có thể nằm trong memtable/SSTable đến lúc được dọn hợp lệ.

```text
DELETE / ghi NULL / TTL expiry
                 |
                 v
        Tombstone có hiệu lực
                 |
                 +--> Query không trả giá trị đã bị che
                 |
                 +--> SSTable/replica có thể vẫn có giá trị cũ
                 |
                 v
       Đủ tuổi theo gc_grace_seconds?
                 |
           Không / Có
                 |
           giữ lại / xét tiếp
                         |
                         v
        Có dữ liệu cũ ở SSTable chưa tham gia
        hoặc điều kiện an toàn khác ngăn purge?
                         |
                 Có / Không
                  |       |
                 giữ      v
                   Compaction có thể purge
                   dữ liệu/dấu xóa khi an toàn
```

Quy trình trên là **mô hình khái niệm**, không phải mô phỏng đầy đủ từng bước compaction của tất cả phiên bản Cassandra. Điều kiện purge phụ thuộc định dạng SSTable, cơ chế compaction, loại tombstone và chính sách của phiên bản.

### Bảng phân biệt

| Khía cạnh | Xóa logic | Thu hồi vật lý |
| --- | --- | --- |
| Bắt đầu từ | DELETE/NULL/TTL expiry và quy tắc timestamp | Compaction/garbage collection khi dữ liệu đủ điều kiện |
| Kết quả đối với SELECT | Giá trị cũ bị che, không còn sống nếu deletion thắng | Không nhất thiết làm kết quả SELECT thay đổi |
| Kết quả đối với byte SSTable | Có thể tạm **tăng** vì ghi dấu xóa | Có thể giảm sau khi tệp được hợp nhất/dọn |
| Liên hệ `gc_grace_seconds` | Không cần đợi hết grace để deletion có hiệu lực logic | Grace là một trong các điều kiện xét purge |
| Phụ thuộc replica/repair | Đọc/hòa giải có thể cần replica mới hơn | Phải tránh zombie khi replica còn dữ liệu cũ |

**Một lỗi vận hành phổ biến:** thấy `DELETE` thành công nhưng tổng `space used` chưa giảm, rồi cho rằng DELETE không hoạt động. Cassandra có thể đang giữ tombstone có chủ đích và đợi điều kiện thu hồi an toàn.

## 5. Những loại tombstone mà `gc_grace_seconds` liên quan

Không phải mọi tombstone cùng phạm vi. Cassandra có thể ghi dấu xóa ở các mức:

| Dạng dấu xóa | Ví dụ | Phạm vi |
| --- | --- | --- |
| **Cell tombstone** | `DELETE payload` với full primary key | Một regular cell |
| **Static-cell tombstone** | `DELETE note` với partition key | Một static cell thuộc partition |
| **Collection element tombstone** | `DELETE attributes['source']` | Một phần tử non-frozen collection |
| **Complex/collection deletion** | `DELETE attributes` trên map không frozen | Một collection và phần tử cũ |
| **Row tombstone** | `DELETE FROM ... WHERE full_primary_key` | Một hàng clustering |
| **Range tombstone** | Xóa một dải clustering được CQL/phiên bản hỗ trợ | Nhiều hàng trong một đoạn thuộc cùng partition |
| **Partition tombstone** | `DELETE FROM ... WHERE partition_key` | Hàng và static data trong toàn partition |
| **Expired cell / TTL tombstone** | Giá trị có TTL đã hết hạn | Cell/dữ liệu được ghi có TTL liên quan |

Mọi phạm vi đều có chức năng **che dữ liệu cũ** theo thông tin thời gian và cơ chế hòa giải. `gc_grace_seconds` là một tham số quan trọng cho việc xét dọn dữ liệu đã xóa, nhưng cách biểu diễn và xét điều kiện thu hồi có thể khác nhau giữa dạng tombstone và phiên bản.

**Không suy ra một lệnh DELETE = một tombstone vật lý = một hàng bị xóa.** Một range tombstone có thể che hàng nghìn clustering rows; một collection không frozen có thể sinh nhiều tombstone phần tử; và nhiều thao tác xóa có thể được hợp nhất qua compaction.

## 6. CQL lab: tạo bảng, DELETE và xem cấu hình grace

Các ví dụ sau dùng `app_ks` là keyspace **giả định đã được tạo phù hợp môi trường lab**; mọi câu lệnh có tác động dữ liệu phải chạy trên bảng thử nghiệm.

### Tạo bảng

```sql
CREATE TABLE app_ks.device_events_by_day (
    tenant_id   text,
    device_id   uuid,
    event_day   date,
    occurred_at timestamp,
    event_id    uuid,
    event_type  text,
    payload     text,
    PRIMARY KEY (
        (tenant_id, device_id, event_day),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    occurred_at DESC,
    event_id ASC
) AND gc_grace_seconds = 864000;
```

Partition key gồm `tenant_id`, `device_id` và `event_day`. Nếu hai sự kiện cùng thiết bị trong một ngày, chúng thuộc cùng partition; chỉ khác `occurred_at` và `event_id`.

### Ghi dữ liệu mẫu

```sql
INSERT INTO app_ks.device_events_by_day (
    tenant_id, device_id, event_day,
    occurred_at, event_id, event_type, payload
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T08:00:00Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    'reading',
    'temperature=38.1'
);

INSERT INTO app_ks.device_events_by_day (
    tenant_id, device_id, event_day,
    occurred_at, event_id, event_type, payload
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T08:05:00Z',
    7c2c4f75-5c44-4be4-99a0-08688b465200,
    'reading',
    'temperature=38.4'
);
```

### Xóa một cell

```sql
DELETE payload
FROM app_ks.device_events_by_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at = '2026-11-21T08:00:00Z'
  AND event_id = 8817a208-1858-4144-86e9-b24d9083e478;
```

Sau mutation, hàng lúc 08:00 **có thể còn sống** nhờ `event_type`; chỉ `payload` bị xóa theo write timestamp tương ứng.

### Xem table options trong cqlsh

```sql
DESCRIBE TABLE app_ks.device_events_by_day;
```

`DESCRIBE` là lệnh của **cqlsh**, không phải câu SELECT CQL do Java Driver tự thực thi. Nó giúp xem schema và các tùy chọn bảng, gồm `gc_grace_seconds`, theo môi trường đang dùng.

**Thực hành có kiểm soát:** không hạ grace của bảng production chỉ để nhìn tombstone biến mất nhanh; thao tác đó có thể thay đổi điều kiện an toàn xóa đối với các replica chưa đồng bộ.

## 7. `ALTER TABLE gc_grace_seconds` thực sự làm gì?

Thay đổi giá trị bảng bằng CQL:

```sql
ALTER TABLE app_ks.device_events_by_day
WITH gc_grace_seconds = 864000;
```

Ví dụ trên đặt **10 ngày**. Nếu trước đó bảng đã có giá trị này, thao tác không thay đổi chính sách mong muốn.

### Điều không xảy ra

- Cassandra **không tự di chuyển dữ liệu** sang partition key khác.
- Mọi tombstone **không biến mất tức thì** chỉ vì giảm cấu hình.
- SSTable **không được viết lại toàn bộ ngay** sau ALTER.
- Repair **không tự chạy** để bảo đảm mọi replica đã nhận deletion.
- Cấu hình **không tạo SLA** rằng dữ liệu bị xóa vật lý trước một hạn định tuyệt đối.

Điều quan trọng là **đánh giá eligibility cho việc purge** có liên quan đến khoảng grace và trạng thái hiện hành khi cơ chế thu hồi thực hiện. Khi đổi cấu hình, các tombstone đã tồn tại có thể trở thành đối tượng cần được xét với điều kiện mới; vì vậy **giảm giá trị là thao tác có rủi ro**, không phải thay đổi chỉ ảnh hưởng những DELETE tương lai.

### Nếu tăng giá trị grace

Tăng `gc_grace_seconds` có thể làm nhiều tombstone cần được giữ lâu hơn trước khi đủ điều kiện xét dọn, kéo theo:

- Footprint SSTable và tombstone tồn tại lâu hơn.
- Truy vấn qua vùng đã xóa có thể phải xử lý thêm marker/phiên bản cũ.
- Compaction có thể chưa purge được dữ liệu dù có chạy.

Đây là đánh đổi để tạo biên an toàn phù hợp với thời gian replica có thể gián đoạn và lịch repair. Cần đo tác động theo workload; **tăng grace không tự giải quyết repair bị lỗi**.

## 8. Điều kiện thu hồi tombstone: không chỉ tuổi dấu xóa

Một cách hiểu quá đơn giản là “tuổi tombstone lớn hơn `gc_grace_seconds` thì xóa khỏi đĩa”. Trong thực tế, thu hồi còn phụ thuộc khả năng dữ liệu cũ có thể được thấy ở nơi khác.

### 8.1. Tombstone đủ tuổi

Cassandra xem các thông tin như thời gian xóa/hết hạn để đánh giá liệu dấu xóa đã qua khoảng bảo vệ tương ứng. Nếu chưa đủ tuổi, nó thường phải được giữ lại.

### 8.2. SSTable overlap và dữ liệu cũ chưa tham gia compaction

SSTable bất biến có thể chứa dữ liệu sống cũ cùng partition và clustering range. Nếu chỉ compact SSTable chứa tombstone nhưng còn một SSTable khác **chưa tham gia** chứa giá trị cũ, purge tombstone có thể khiến giá trị đó hiện lại ở lần đọc sau.

```text
SSTable-A: payload = "old" @100
SSTable-B: tombstone payload @200

Chỉ compact B rồi bỏ tombstone:
  A vẫn chứa "old" -> nguy cơ hồi sinh dữ liệu

Compaction an toàn:
  phải xét khả năng A hoặc nguồn khác còn dữ liệu cũ,
  và chỉ purge khi không làm mất thông tin che cần thiết.
```

Vì thế, **quá grace chưa đủ** để kết luận một tombstone trong một SSTable có thể purge độc lập. Cassandra có các kiểm tra overlap/safety phù hợp cơ chế compaction và phiên bản; quản trị viên không nên giả định tất cả trường hợp có cùng đường dọn.

### 8.3. Replica nào còn phiên bản cũ?

Một replica có thể bỏ lỡ mutation xóa do mất kết nối, lỗi phần cứng hoặc phục hồi từ snapshot cũ. `gc_grace_seconds` đặt một khoảng bảo vệ để hệ thống có thời gian **đồng bộ deletion thông qua repair/đường cập nhật thích hợp**.

Điểm tinh tế: compaction của một node **không tự chứng minh** tất cả replica khác đã nhận dấu xóa. Chính vì vậy không nên dựa vào việc “trên A đã compact thành công” để kết luận deletion toàn cluster an toàn.

### 8.4. Compaction cần thực sự xảy ra

Ngay cả khi tombstone đủ điều kiện, nếu chưa có compaction thích hợp thì dữ liệu có thể vẫn còn trong SSTable. Lịch compaction, strategy, backlog, dung lượng đĩa và tải hệ thống có thể làm chậm hoặc trì hoãn quá trình thu hồi.

### 8.5. Repaired/unrepaired SSTables và chính sách phiên bản

Trong một số phiên bản/cấu hình, trạng thái **repaired/unrepaired** của SSTable và các tùy chọn garbage collection liên quan cũng ảnh hưởng điều kiện compaction/purge. Không nên áp dụng quy tắc một chiều từ phiên bản khác; cần đọc cấu hình và semantics của **phiên bản Cassandra đang chạy** trước khi thay đổi chính sách thu hồi.

**Bảng tổng hợp:**

| Điều kiện | Câu hỏi phải trả lời |
| --- | --- |
| Tuổi deletion | Tombstone đã qua khoảng grace áp dụng chưa? |
| SSTable overlap | Có bản dữ liệu cũ nào có thể xuất hiện nếu bỏ marker? |
| Replica/repair | Có replica nào có thể giữ bản cũ chưa nhận deletion? |
| Compaction | Có compaction phù hợp được lên lịch và có tài nguyên chạy không? |
| Kiểu tombstone | Cell/row/range/partition hoặc expired TTL có điều kiện gì khác? |
| Phiên bản/cấu hình | Các tùy chọn tombstone garbage collection và repaired state được xử lý thế nào? |

## 9. Ba kịch bản thời gian: thu hồi an toàn và rủi ro zombie

### Kịch bản A — Replica đồng bộ đúng hạn

```text
Ngày 0:   A, B, C có giá trị cũ.
Ngày 1:   C offline; A, B nhận DELETE.
Ngày 2:   C phục hồi; repair/đồng bộ đưa deletion đến C.
Ngày 11+: Tombstone đủ tuổi theo cấu hình grace 10 ngày,
          compaction có thể xét purge nếu các điều kiện khác đạt.
```

Các mốc chỉ minh họa. Nếu repair thực sự đồng bộ mọi dữ liệu liên quan, không còn bản cũ bị bỏ sót trên C, rủi ro zombie từ kịch bản đó được giảm.

### Kịch bản B — Replica offline quá lâu

```text
Ngày 0:  C offline.
Ngày 1:  A, B nhận DELETE, tạo tombstone.
Ngày 11: Grace 10 ngày kể từ deletion đã qua.
Ngày 12: A/B có thể purge tombstone khi cơ chế cho phép.
Ngày 20: C quay lại mang bản giá trị cũ.
```

C **có nguy cơ** làm dữ liệu cũ được thấy hoặc lan truyền trở lại vì thông tin deletion đã biến mất khỏi các nguồn đủ để che nó. Đây là điều cần tránh khi xây dựng chính sách offline/repair.

### Kịch bản C — Tombstone quá grace nhưng chưa được purge

```text
Ngày 1:  DELETE tạo tombstone.
Ngày 11: Tombstone đủ tuổi theo grace.
Ngày 14: SSTable khác vẫn có dữ liệu cũ; điều kiện overlap
         hoặc trạng thái compaction khiến tombstone được giữ.
Ngày 18: Compaction phù hợp mới có thể dọn khi an toàn.
```

**Hết grace không ép dữ liệu bị xóa vật lý đúng ngày 11.** Bất kỳ dashboard nào hiển thị “thời hạn xóa = ngày tombstone + grace” phải ghi rõ đó là **mốc eligibility**, không phải SLA purge.

## 10. Repair phải phù hợp với thời gian grace

Repair giúp đồng bộ dữ liệu giữa replica, gồm các sai khác do node từng offline hoặc bỏ lỡ mutation. Đây là một trụ cột của quản trị tombstone.

### Quy tắc vận hành cơ bản

Trong các mô hình Cassandra truyền thống, một khuyến nghị phổ biến là bảo đảm các **replica/range liên quan được repair thành công trong cửa sổ ngắn hơn `gc_grace_seconds`** khi hệ thống có nguy cơ bỏ lỡ deletion. Không chỉ lập lịch một job: phải **xác minh job thành công trên phạm vi cần thiết** và có ngân sách xử lý lỗi, retry, node bị gián đoạn.

```text
Grace giả định: 10 ngày

Không nên:
  repair 10 ngày một lần vào sát thời hạn,
  bỏ qua các lần fail và xem như đã được bảo vệ.

Nên:
  lên lịch repair có biên an toàn,
  giám sát tiến độ/range coverage và lỗi,
  xử lý node offline trước khi thời gian gián đoạn vượt cửa sổ an toàn.
```

### Vì sao repair một lần chưa chắc đủ?

- Một lần repair có thể **không bao phủ mọi token range hoặc bảng** nếu cấu hình/phạm vi job bị giới hạn.
- Job có thể bị hủy, timeout, lỗi mạng hoặc không hoàn tất trên một số node.
- Có thể tồn tại các yêu cầu bảo trì riêng khi data center mất kết nối lâu, node thay mới hoặc khôi phục snapshot.
- Cassandra có **full/incremental repair** và cơ chế được cải tiến theo phiên bản; không suy “repair đã bật” là “mọi deletion đã an toàn”.

### Ví dụ lệnh phục vụ bài lab

```bash
nodetool repair app_ks device_events_by_day
```

**Không chạy lệnh repair quy mô lớn trên production chỉ để thực hành.** Repair tiêu thụ CPU, mạng, disk I/O và có thể ảnh hưởng latency. Cú pháp, phạm vi mặc định và chiến lược full/incremental phải được xác minh cho phiên bản/topology đang dùng; lập runbook vận hành riêng trước khi áp dụng.

### Hinted handoff không thay thế repair

Hints có thể giúp chuyển tiếp các mutation mà replica bỏ lỡ trong những tình huống và giới hạn cấu hình nhất định. Tuy nhiên, **không được dùng hints làm bảo đảm một replica offline rất lâu chắc chắn sẽ nhận đủ mọi DELETE**. Thời gian giữ hints, sự cố coordinator và các giới hạn khác có thể khiến chúng không đầy đủ; anti-entropy repair vẫn có vai trò riêng.

## 11. Consistency level và replication factor có thay thế grace không?

**Không.** Replication factor (RF) quy định số bản sao logic theo replication strategy; consistency level (CL) quy định yêu cầu xác nhận/đọc phù hợp, không phải thời điểm có thể bỏ tombstone.

Ví dụ với RF = 3 trong một data center:

- Một mutation ở `LOCAL_QUORUM` cần xác nhận từ quorum của replica liên quan.
- Replica thứ ba có thể **chưa nhận mutation** tại lúc client được xác nhận.
- Sau đó node có thể offline, hints không đủ hoặc repair bị trễ.
- Khi đọc tại CL thấp trên một replica còn cũ, client có thể thấy trạng thái stale tùy đường đọc và thời điểm.
- Khi đọc và hòa giải đúng replica theo CL phù hợp, tombstone mới có thể che giá trị cũ, nhưng điều đó **không tương đương** deletion đã được truyền đến mọi replica hay đã được thu hồi an toàn.

| Cơ chế | Đảm nhiệm | Không bảo đảm |
| --- | --- | --- |
| RF | Số replica và độ bền theo topology | Không chia partition key hoặc dọn tombstone |
| `LOCAL_ONE` | Mức xác nhận/đọc một replica trong DC liên quan | Không chắc đọc phiên bản mới nhất |
| `LOCAL_QUORUM` | Mức quorum trong DC liên quan | Không đồng bộ ngay tất cả replica |
| Hints | Chuyển tiếp mutation bị bỏ lỡ trong giới hạn hỗ trợ | Không thay repair khi downtime dài |
| Repair | Đồng bộ sai khác giữa replica theo phạm vi đã chạy | Không tự chạy chỉ vì hết grace |
| Compaction | Tổ chức lại SSTable, có thể purge dữ liệu đã đủ điều kiện | Không tự sửa replica khác |
| `gc_grace_seconds` | Khoảng bảo vệ trước khi xét purge tombstone | Không phải hạn vật lý hoặc lịch repair |

**Không nên giảm grace chỉ vì đang dùng `LOCAL_QUORUM`.** Cần chứng minh topology, failure modes, lịch sửa chữa và chính sách khôi phục hỗ trợ mức an toàn mong muốn.

## 12. TTL hết hạn cũng liên quan đến việc giữ dấu xóa

TTL (*time to live*) khiến dữ liệu tự hết hạn sau số giây theo semantics của giá trị được ghi. Khi hết hạn, cell không còn sống trong kết quả đọc; trên SSTable, thông tin hết hạn được xử lý như trạng thái xóa cần được dọn khi an toàn.

### Ghi TTL bằng CQL

```sql
INSERT INTO app_ks.device_events_by_day (
    tenant_id, device_id, event_day,
    occurred_at, event_id, event_type, payload
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T09:00:00Z',
    142dd6ae-6706-4f2c-a5e8-61cdd9c22cad,
    'temporary',
    'expire-after-one-hour'
) USING TTL 3600;
```

Sau một giờ tính từ lúc ghi theo semantics TTL, những giá trị được ghi với TTL không còn sống. Nhưng:

1. **Không có job bắt buộc gửi một DELETE mới** vào đúng giây hết hạn.
2. **Không có bảo đảm SSTable thu nhỏ ngay** sau hết TTL.
3. TTL của `payload` không mặc nhiên xóa mọi cell khác không mang TTL hoặc toàn bộ partition.
4. Ghi lại cell với TTL mới có thể thay đổi hạn hết của phiên bản hiện hành.
5. Dữ liệu đến trễ/backfill với `USING TTL 3600` được tính theo thời điểm ghi, không tự tính từ `occurred_at` (event time).

### Xem TTL còn lại

```sql
SELECT occurred_at, event_id,
       payload,
       TTL(payload),
       WRITETIME(payload)
FROM app_ks.device_events_by_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at = '2026-11-21T09:00:00Z'
  AND event_id = 142dd6ae-6706-4f2c-a5e8-61cdd9c22cad;
```

`TTL(payload)` cho TTL còn lại khi cell sống và có TTL; `WRITETIME(payload)` phản ánh write timestamp của cell khi khả dụng. Không dùng chúng như công cụ đo **ngày chắc chắn tombstone được purge** hay đếm mọi marker trong SSTable.

### TTL + TWCS có cho phép hạ grace không?

Dữ liệu time-series append-mostly với TTL đồng đều có thể phù hợp để **đánh giá** `TimeWindowCompactionStrategy` (TWCS). Khi SSTable chứa dữ liệu có vòng đời tương tự, việc bỏ cả SSTable đã hết hạn có thể thuận lợi hơn một số trường hợp compaction thông thường.

Tuy nhiên, **TWCS không làm biến mất rủi ro replica bỏ lỡ deletion**. Ghi muộn, sửa dữ liệu cũ, TTL không đồng đều và SSTable overlap có thể làm việc thu hồi phức tạp. Không lấy “đã bật TWCS” làm lý do đủ để đặt `gc_grace_seconds = 0`.

## 13. SSTable overlap: ví dụ vì sao tombstone đã già vẫn tồn tại

Một partition có thể hiện diện ở nhiều SSTable:

```text
SSTable-1:
  E1.payload = "A"    @100
  E2.payload = "B"    @100

SSTable-2:
  DELETE E1.payload   @200

SSTable-3:
  E1.source_app = "gateway" @150

Ngày hôm nay:
  Tombstone @200 đã quá grace.
```

Nếu chỉ loại dấu xóa trong SSTable-2, SSTable-1 vẫn có `E1.payload = A`. Khi đọc, giá trị A có nguy cơ xuất hiện lại **ngay trong cùng replica**, không cần chờ node khác offline quay về.

Bởi vậy, compaction an toàn phải xét khả năng những phiên bản cũ ở **SSTable không tham gia** sẽ còn cần được che. Cơ chế chọn SSTable để compact và kiểm tra overlap có vai trò lớn. Trong những trường hợp thích hợp, compaction có thể hợp nhất dữ liệu bị che và dấu xóa rồi loại cả hai khi đủ điều kiện.

### Tại sao chỉ nhìn SSTable count là chưa đủ?

- Một bảng có ít SSTable nhưng chứa một partition rất lớn hoặc nhiều marker cũng có thể đọc chậm.
- Một bảng có nhiều SSTable không nhất thiết mọi truy vấn đều đọc tất cả chúng.
- Cần so `SSTables per read`, tombstones per slice, partition size và latency cho truy vấn thực.
- Trạng thái compaction/repaired của các tệp cũng có thể tác động khả năng thu hồi tùy phiên bản.

**Mục tiêu là bảo toàn deletion khi thu hồi**, không phải xóa nhiều byte nhất có thể trong một lần compaction.

## 14. Các chiến lược compaction và thời gian giữ tombstone

Compaction strategy ảnh hưởng cách SSTable được chọn để hợp nhất và tốc độ dữ liệu cũ/tombstone có cơ hội được thu hồi.

| Strategy | Mẫu sử dụng thường cân nhắc | Quan hệ với tombstone |
| --- | --- | --- |
| **STCS** (*SizeTieredCompactionStrategy*) | Một số workload ghi nhiều, dữ liệu nhiều kích thước | Nhiều SSTable có thể cùng chứa phiên bản một partition trước khi hợp nhất. |
| **LCS** (*LeveledCompactionStrategy*) | Một số workload đọc nhiều cần giảm overlap | Hướng tới giới hạn overlap theo level; có write amplification và compaction I/O riêng. |
| **TWCS** (*TimeWindowCompactionStrategy*) | Time-series append-mostly, TTL gần đồng đều | Có thể thuận lợi dọn cửa sổ dữ liệu đã hết hạn, nhưng nhạy với late writes và updates vào dữ liệu cũ. |

Không có chiến lược nào **tự thay thế** logic grace/repair. Một tombstone đã hết `gc_grace_seconds` nhưng chưa được compact đúng điều kiện vẫn có thể nằm trên SSTable. Trái lại, việc ép compaction quá mạnh có thể làm tăng I/O, chiếm disk headroom, ảnh hưởng p99 và không mang lại lợi ích mong muốn.

### Cảnh giác với “chạy compaction để sửa lỗi dữ liệu”

`nodetool compact` (khi được hỗ trợ theo cú pháp phiên bản) yêu cầu công việc compaction; **nó không chứng minh deletion đã tới mọi replica**. Nếu dữ liệu không thống nhất giữa replica, cần phân tích repair và nguồn mutation; ép compaction không phải cơ chế thay thế anti-entropy.

Đặc biệt khi một node vừa hồi phục sau downtime dài, hãy đánh giá tính an toàn của dữ liệu trước khi thực hiện các thao tác bảo trì có thể thay đổi khả năng giữ tombstone.

## 15. Cách quan sát `gc_grace_seconds` và tombstone trong vận hành

Không có một câu CQL đơn giản trả về “toàn bộ tombstone trong mọi SSTable kèm ngày purge chính xác”. Cần phối hợp schema, nodetool, metrics và logs.

### Kiểm tra bảng

Trong `cqlsh`:

```sql
DESCRIBE TABLE app_ks.device_events_by_day;
```

Xác nhận:

- `gc_grace_seconds` thật của bảng.
- Compaction strategy và các options liên quan.
- `default_time_to_live` nếu bảng sử dụng TTL mặc định.
- Partition key và clustering columns để biết truy vấn nào có thể gặp tombstone trên một phân vùng lớn.

### Kiểm tra trạng thái node/bảng

```bash
nodetool status
nodetool tablestats app_ks.device_events_by_day
nodetool tablehistograms app_ks device_events_by_day
nodetool compactionstats
```

Các trường hữu ích, phụ thuộc phiên bản:

| Nhóm chỉ số | Dùng để trả lời |
| --- | --- |
| **Node status và downtime** | Có replica nào offline, vừa rejoin hoặc bị thay thế không? |
| **Repair completion/range coverage** | Các range liên quan đã được đồng bộ trong cửa sổ an toàn chưa? |
| **Tombstones per slice** | Truy vấn đọc có gặp nhiều dấu xóa không? |
| **SSTables per read, SSTable count** | Có nhiều nguồn/phiên bản cần merge không? |
| **Partition size/cell histogram** | Có partition rất lớn hoặc dày dữ liệu không? |
| **Pending/active compactions** | Có backlog khiến tombstone khó được dọn không? |
| **Disk headroom, CPU/I/O, p95/p99 latency** | Hệ thống có dư tài nguyên để repair/compact không? |
| **Timeout/error và warning logs** | Truy vấn có chạm ngưỡng bảo vệ tombstone không? |

`tablestats` và `tablehistograms` thường là số liệu **mức bảng/node**, không phải phép đếm tombstone chính xác cho một key đang sống. Khi so kết quả giữa node hoặc giữa các ngày, cần ghi rõ **phiên bản, node, thời gian và phạm vi**.

### Tracing một truy vấn nghi ngờ

```sql
TRACING ON;

SELECT occurred_at, event_id, event_type, payload
FROM app_ks.device_events_by_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
LIMIT 20;

TRACING OFF;
```

Tracing có thể giúp phát hiện chi phí đọc và các tombstone đã được xét khi phiên bản cung cấp thông tin; nó **không thay thế phép kiểm kê SSTable**. Tracing tạo overhead nên chỉ dùng mẫu nhỏ và tắt sau khi thu thập.

## 16. Vì sao một SELECT chậm không nhất thiết do grace quá dài?

Trường hợp thường gặp: API lấy 20 event mới nhất chậm mặc dù query đã có `LIMIT 20`.

Giả sử:

```text
Đầu dải clustering:
  expired expired deleted deleted deleted ...
  hàng nghìn cell/row đã hết hạn hoặc bị xóa
  ...
  live #1
  ...
  live #20
```

Cassandra phải xét các deletion markers khi hợp nhất memtable/SSTable để tìm hàng sống. `LIMIT 20` ràng buộc **số hàng kết quả**, không ràng buộc số tombstone phải duyệt.

Tombstone tích lũy có thể liên quan grace dài, nhưng cũng có thể do:

1. Nhiều UPDATE/DELETE hoặc write NULL không cần thiết.
2. TTL quá ngắn so với tốc độ ghi.
3. Query đọc slice rộng hoặc đầu dải có nhiều hàng hết hạn.
4. Partition rất lớn hoặc nóng.
5. Nhiều SSTable cùng chứa dữ liệu cũ, compaction backlog.
6. Replica/đĩa/mạng quá tải hoặc consistency level làm phải chờ nhiều nguồn.

Do đó, **hạ `gc_grace_seconds` không phải bước đầu tiên**. Chẩn đoán nguồn tạo tombstone, khả năng compaction, thiết kế partition key và phạm vi truy vấn trước. Nếu điều kiện an toàn repair không đủ, giảm grace có thể đổi một vấn đề latency thành lỗi dữ liệu nghiêm trọng hơn.

## 17. Khi nào cân nhắc thay `gc_grace_seconds`?

Thay giá trị này là một **quyết định vận hành có đánh giá rủi ro**, không phải một mẹo tối ưu tự động. Mọi thay đổi nên có văn bản nêu:

- Phiên bản/distribution Cassandra và cơ chế tombstone garbage collection đang sử dụng.
- Replication factor, số data center và thời gian replica có thể offline.
- Bằng chứng lịch repair, khả năng hoàn tất trong grace và mức lỗi dự kiến.
- Chiến lược compaction, TTL, update/delete, SSTable overlap.
- Yêu cầu dữ liệu được xóa không xuất hiện lại.
- Kịch bản khôi phục node/snapshot/backup cũ.
- SLO đọc/ghi, disk capacity và ngân sách I/O cho repair/compaction.
- Kế hoạch theo dõi, ngừng thay đổi và xử lý sự cố nếu dữ liệu có dấu hiệu zombie.

### Giảm grace

Trước khi giảm, cần hỏi:

1. **Tất cả replica/range có được sửa chữa đủ thường xuyên và thành công không?**
2. **Có trường hợp node offline lâu hơn giá trị mới không?**
3. **Có khả năng phục hồi snapshot hoặc SSTable cũ không?**
4. **Có DELETE hoặc TTL trong workload không?**
5. **Có cơ chế bảo vệ phiên bản khác hỗ trợ thu hồi an toàn theo phiên bản không?**

Giảm grace trên một bảng có RF lớn hơn 1 và khả năng replica offline dài có thể tăng rủi ro zombie. Những triển khai đặc thù có lý do kỹ thuật để dùng grace ngắn hoặc bằng 0 phải được đánh giá riêng; **không dùng 0 như cấu hình mặc định để xử lý cảnh báo tombstone**.

### Tăng grace

Tăng grace có thể là một biện pháp thận trọng nếu lịch repair hoặc đặc tính failure đòi hỏi biên lớn hơn. Nhưng cũng có thể làm dữ liệu đã xóa và dấu xóa tồn tại lâu hơn, kéo theo chi phí đọc/đĩa/compaction. Vẫn cần sửa lỗi repair/downtime nếu chúng vượt cả cửa sổ mới.

### Thay đổi không hồi tố được dữ liệu đã mất

Nếu tombstone đã bị purge trước đó, **tăng `gc_grace_seconds` sau này không tự tái tạo dấu xóa đã biến mất**. Điều này quan trọng khi xử lý sự cố hoặc đánh giá rollback cấu hình.

## 18. Node offline quá grace: không đơn giản bật lại

Một node chứa dữ liệu replica cũ rồi offline lâu hơn cửa sổ an toàn là tình huống cần **runbook riêng**.

Trước khi cho node đó phục vụ truy vấn/streaming như một replica bình thường:

1. Xác định **ngày giờ cuối cùng node thực sự đồng bộ dữ liệu**, thời điểm offline và các mutation DELETE/TTL có thể đã bỏ lỡ.
2. Kiểm tra bảng/keyspace tương ứng có `gc_grace_seconds` nào; không mặc định cả cluster dùng một giá trị.
3. Xác định các replica khác đã repair/compact và có thể đã purge deletion nào trong thời gian node vắng mặt.
4. Đánh giá quy trình **thay thế/rebuild/rebootstrap hoặc đồng bộ được phê duyệt** cho node cũ theo phiên bản/topology; tránh đưa dữ liệu cũ trực tiếp trở lại nếu có rủi ro zombie.
5. Giữ node ngoài luồng production đến khi người vận hành xác nhận tính đúng dữ liệu và điều kiện an toàn.
6. Theo dõi replication health, repair, read/write latency và dấu hiệu dữ liệu đã xóa xuất hiện lại sau khôi phục.

Không có một câu lệnh `nodetool repair` chạy muộn nào **tự bảo đảm** hồi phục đúng nếu các replica đang hoạt động đã mất tombstone cần thiết. Repair đồng bộ trạng thái hiện có; khi thông tin deletion đã bị purge không an toàn, cần đánh giá tình trạng dữ liệu và kế hoạch khôi phục cụ thể.

**Không khuyến nghị khởi động lại node cũ một cách tự động chỉ vì `nodetool status` cho thấy cluster hiện còn đủ RF.** An toàn dữ liệu phụ thuộc lịch sử mutation và deletion.

## 19. Java Driver 4.x: DELETE, TTL và timeout không xác nhận thất bại

Một ứng dụng Java nên thể hiện rõ ba điều:

- Xóa cell nào bằng **full primary key**.
- Ghi dữ liệu có TTL nào theo chính sách retention.
- Khi timeout, thao tác **có thể đã áp dụng ở một số replica**; retry không được tạo primary key khác hoặc thay đổi ngữ nghĩa retention ngoài ý muốn.

Ví dụ dùng Java Driver 4.x với bảng `app_ks.device_events_by_day`:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public final class DeviceEventRepository {
    private final CqlSession session;
    private final PreparedStatement deletePayload;
    private final PreparedStatement insertWithTtl;

    public DeviceEventRepository(CqlSession session) {
        this.session = session;

        this.deletePayload = session.prepare(
            "DELETE payload FROM app_ks.device_events_by_day " +
            "WHERE tenant_id = ? AND device_id = ? AND event_day = ? " +
            "AND occurred_at = ? AND event_id = ?"
        );

        this.insertWithTtl = session.prepare(
            "INSERT INTO app_ks.device_events_by_day " +
            "(tenant_id, device_id, event_day, occurred_at, " +
            "event_id, event_type, payload) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?) USING TTL ?"
        );
    }

    public void removePayload(
            String verifiedTenantId,
            UUID deviceId,
            LocalDate eventDay,
            Instant occurredAt,
            UUID eventId) {

        session.execute(deletePayload.bind(
            verifiedTenantId, deviceId, eventDay, occurredAt, eventId
        ));
    }

    public void writeTemporaryEvent(
            String verifiedTenantId,
            UUID deviceId,
            LocalDate eventDay,
            Instant occurredAt,
            UUID eventId,
            String eventType,
            String payload,
            int ttlSeconds) {

        if (ttlSeconds < 1) {
            throw new IllegalArgumentException("TTL must be positive");
        }

        // eventDay phải được caller tính nhất quán từ event time UTC.
        session.execute(insertWithTtl.bind(
            verifiedTenantId, deviceId, eventDay, occurredAt,
            eventId, eventType, payload, ttlSeconds
        ));
    }
}
```

### Ý nghĩa vận hành của code

1. `removePayload` xóa **một cell**, không xóa hàng hoặc cả partition; muốn phạm vi khác phải dùng prepared CQL riêng.
2. `eventDay` phải thống nhất với thời điểm nghiệp vụ/bucket UTC; không tính lại từ thời gian retry.
3. `eventId` và `occurredAt` cần giữ nguyên khi retry để không tạo full primary key khác.
4. Retry `INSERT` mang TTL có thể làm **dịch thời điểm hết hạn** so với ghi ban đầu nếu ngữ nghĩa thao tác thay đổi; phải kiểm soát khi retention nghiêm ngặt.
5. Timeout của DELETE/INSERT không chứng minh mutation chưa được ghi; cần retry/backoff, quan sát CL và idempotency.
6. `verifiedTenantId` phải lấy từ ngữ cảnh đã xác thực/ủy quyền, không chỉ tin client truyền ID.
7. Java Driver **không tự thực thi repair, compaction hoặc tombstone garbage collection** khi có DELETE; đó là trách nhiệm server/vận hành.

**Chú ý:** ví dụ minh họa không tự áp đặt consistency level đặc biệt. Trong hệ thống thật, CL phải được chọn có chủ đích theo topology, latency và yêu cầu đọc/ghi; nhưng không nên coi CL là cách thay thế lịch repair khi thiết lập grace.

## 20. Lab an toàn: quan sát DELETE và TTL mà không giảm grace

Một bài thực hành tốt **không cần chỉnh `gc_grace_seconds` xuống 0** và không cần đợi đủ 10 ngày trong buổi học.

### Bước 1 — Chuẩn bị bảng lab

Tạo bảng `app_ks.device_events_by_day` như phần 6, xác nhận `gc_grace_seconds` bằng `DESCRIBE TABLE`. Dùng keyspace, replica và dữ liệu **không mang tính production**.

### Bước 2 — Ghi và đọc hai hàng

Chạy các `INSERT` ở phần 6 và đọc:

```sql
SELECT occurred_at, event_id, event_type, payload
FROM app_ks.device_events_by_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
LIMIT 20;
```

Mục tiêu: kiểm chứng full partition key và clustering order.

### Bước 3 — Xóa một cell

Chạy `DELETE payload` ở phần 6. Đọc lại: hàng tương ứng vẫn có thể hiển thị nhờ `event_type`, trong khi `payload` không còn giá trị sống.

Mục tiêu: thấy **xóa logic** mà không cần quan sát biến động dung lượng đĩa tức thì.

### Bước 4 — Ghi TTL ngắn

Ghi một event với TTL 60 giây trên một **full primary key mới**, đo `TTL(payload)` khi cell còn sống và đọc lại sau khi TTL hết hạn.

Mục tiêu: thấy TTL làm cell hết hạn **mà không cần gửi lệnh DELETE mới**. Không kết luận timestamp của sự kiện là thời điểm TTL tính bắt đầu.

### Bước 5 — Xem thống kê/tracing

Dùng `tablestats`, `tablehistograms` hoặc tracing cho một vài truy vấn lab. Với lượng dữ liệu rất nhỏ, metrics có thể không đổi đáng kể; đó không phải lỗi thí nghiệm.

Nếu muốn đo read amplification, cần workload có đủ hàng, TTL/xóa và phân bố SSTable đại diện, thử trong môi trường riêng, với giới hạn I/O và không áp dụng vào production.

### Bước 6 — Trả lời câu hỏi về điều kiện purge

Trước khi quan sát hay yêu cầu compaction, học viên phải trả lời:

- Tombstone đã đủ tuổi theo grace chưa?
- Có dữ liệu cũ ở SSTable/replica khác không?
- Replica có thể đã bỏ lỡ deletion chưa được repair không?
- Compaction đang chạy loại nào và có đủ tài nguyên không?
- Việc dọn tombstone lúc này có làm dữ liệu cũ xuất hiện lại không?

Không chạy compaction hoặc thay grace chỉ để “hoàn thành bài lab”; hiểu **điều kiện an toàn** là mục tiêu học chính.

## 21. Case study: grace ngắn, repair trễ và dữ liệu sống lại

Một hệ thống lưu lịch sử sự kiện có RF = 3. Nhóm vận hành thấy nhiều tombstone và đọc chậm. Họ đổi `gc_grace_seconds` từ **10 ngày** xuống **2 ngày** nhưng vẫn chỉ repair **mỗi 7 ngày**. Một replica bị mất kết nối **4 ngày** trong đợt bảo trì.

### Diễn biến có thể xảy ra

```text
Ngày 0: Replica C offline; A/B vẫn ghi DELETE cho một số key.
Ngày 2: Tombstone tại A/B bắt đầu đủ tuổi theo grace mới.
Ngày 3: Compaction có thể purge một số tombstone nếu các điều kiện
        cục bộ và cơ chế phiên bản cho phép.
Ngày 4: C quay lại, vẫn mang giá trị cũ chưa nhận DELETE.
Ngày 7: Repair dự kiến mới chạy.
```

Có nguy cơ một số giá trị cũ của C được nhìn thấy hoặc lan truyền trở lại nếu dấu xóa cần thiết ở A/B đã bị purge không an toàn. **Không khẳng định zombie chắc chắn xảy ra:** điều đó còn phụ thuộc dữ liệu nào được purge, replica nào đã nhận deletion, SSTable overlap, read/repair timing và cơ chế phiên bản.

### Vì sao biện pháp ban đầu sai hướng?

- Repair mỗi 7 ngày **không nằm trong biên an toàn** của grace 2 ngày nếu một replica có thể bỏ lỡ xóa.
- Một replica mất kết nối 4 ngày vượt grace 2 ngày.
- Số lượng tombstone cao có thể bắt nguồn từ TTL ngắn, xóa từng cell hoặc collection update, không phải grace “đặt sai”.
- Giảm grace không bảo đảm giải quyết p99; tombstone có thể vẫn còn vì compaction/overlap.

### Phương án khắc phục và phòng ngừa

1. Đánh giá tính đúng dữ liệu và **quy trình xử lý node quay lại sau grace**; không tự động rejoin dữ liệu cũ vào production.
2. Khôi phục chính sách grace/repair có biên an toàn phù hợp với failure model.
3. Xác định nguyên nhân tombstone-heavy reads và cải thiện schema/time bucket/TTL/compaction/query.
4. Xác minh repair coverage, thất bại, node outage duration và cảnh báo ngay khi nguy cơ vượt ngưỡng.
5. Theo dõi p95/p99 latency, tombstones per slice, compaction backlog và tính nhất quán dữ liệu.
6. Có runbook thay node/rebuild/khôi phục dữ liệu cũ theo phiên bản để tránh zombie.

**Bài học:** giá trị grace chỉ có ý nghĩa khi đặt trong **toàn bộ quy trình replication, repair và vận hành sự cố**.

## 22. Những hiểu lầm phổ biến

| Nhận định | Vấn đề | Cách hiểu đúng |
| --- | --- | --- |
| “Grace 10 ngày nghĩa là DELETE phải đợi 10 ngày mới có hiệu lực.” | Xóa logic và thu hồi vật lý khác nhau. | Tombstone che dữ liệu khi deletion thắng theo timestamp/CL. |
| “Đúng ngày thứ 10, Cassandra tự xóa toàn bộ tombstone.” | Grace chỉ liên quan điều kiện đủ tuổi. | Còn compaction, overlap, repair và cấu hình phiên bản. |
| “`gc_grace_seconds` chính là TTL.” | TTL áp dụng cho giá trị sống, grace cho garbage collection của dấu xóa. | Hai vòng đời khác nhau. |
| “Tăng RF sẽ tự ngăn zombie data.” | Replica vẫn có thể bỏ lỡ mutation khi downtime. | Cần repair và retention an toàn. |
| “`LOCAL_QUORUM` bảo đảm mọi replica đã nhận DELETE.” | Quorum không phải tất cả replicas. | Quản trị replica và repair riêng. |
| “Hints đủ, không cần repair.” | Hints có giới hạn và có thể bị mất/bỏ lỡ. | Đảm bảo anti-entropy trong cửa sổ grace. |
| “Sau grace, cứ xóa SSTable chứa tombstone là được.” | SSTable khác có thể chứa dữ liệu cũ. | Cần xét overlap và điều kiện purge. |
| “`nodetool compact` sửa được replica stale.” | Compaction không phải repair giữa replica. | Phân biệt compaction và anti-entropy. |
| “TWCS cho phép grace = 0 trong mọi bảng TTL.” | Kiểu ghi, late write, replica failure và version vẫn có rủi ro. | Chỉ thay đổi sau đánh giá chuyên sâu. |
| “Giảm grace luôn làm hết tombstone warning.” | Marker có thể chưa được compact và query vẫn scan nhiều dữ liệu. | Sửa nguồn tombstone và read path. |
| “COUNT(*) cho số dấu xóa trong partition.” | COUNT trả số hàng logic được nhìn thấy. | Dùng metrics/tracing/công cụ SSTable phù hợp. |
| “Tăng grace sau sự cố sẽ tái tạo tombstone đã purge.” | Dữ liệu thu hồi không tự xuất hiện lại. | Cần đánh giá khôi phục dữ liệu và đồng bộ. |
| “Có thể bật node offline 20 ngày lại khi grace 2 ngày mà không kiểm tra.” | Node có thể chứa bản cũ đã bị xóa. | Runbook an toàn cho rejoin/replacement. |

## 23. Bài tập tình huống và đáp án

Một cluster Cassandra có ba replica trong một data center. Bảng `events_by_account_day` có `gc_grace_seconds = 432000`, tức **5 ngày**. Ứng dụng lưu sự kiện với TTL 30 ngày và thỉnh thoảng xóa những event theo yêu cầu người dùng. Repair định kỳ **mỗi 4 ngày**, nhưng trong tháng vừa rồi một số job thất bại. Replica C offline **7 ngày**.

**Câu hỏi:**

1. `gc_grace_seconds` bằng bao nhiêu ngày? Nó có nghĩa gì với tombstone?
2. Một DELETE được xác nhận hôm nay có cần đợi 5 ngày trước khi SELECT không thấy giá trị cũ không?
3. TTL 30 ngày và grace 5 ngày có phải một hạn giữ dữ liệu 35 ngày cố định không?
4. Nếu C offline 7 ngày, vượt khoảng grace, có nguy cơ gì?
5. Việc repair có lịch 4 ngày nhưng thất bại một số lần đã bảo đảm an toàn chưa?
6. Nếu tombstone đã đủ tuổi nhưng còn một SSTable chứa dữ liệu cũ chưa tham gia compaction, có thể dọn dấu xóa tùy ý không?
7. Nếu `nodetool tablestats` báo nhiều tombstone per slice, có chứng minh grace 5 ngày là nguyên nhân duy nhất không?
8. Vì sao `LOCAL_QUORUM` chưa đủ để khẳng định C có DELETE?
9. `nodetool compact` có thay thế repair để đồng bộ C không?
10. Nếu C có bản cũ và A/B đã purge deletion, điều gì có thể xảy ra khi C quay lại?
11. Đặt grace = 0 có phải cách giải quyết an toàn cho mọi bảng time-series TTL không?
12. Nếu một event xảy ra tuần trước nhưng hôm nay mới INSERT với TTL 30 ngày, thời điểm hết hạn mặc định theo event time hay lúc ghi?
13. Một bảng mới chia bucket ngày có tự loại bỏ mọi tombstone không?
14. Những chỉ số và thông tin vận hành nào cần xem trước khi thay grace?
15. Hãy đề xuất một kế hoạch ưu tiên ba bước để khôi phục độ an toàn và giảm query latency.

**Đáp án:**

1. `432000 / 86400 = 5` ngày. Đây là khoảng bảo vệ liên quan điều kiện **xét purge** tombstone, không phải mốc chắc chắn dữ liệu biến mất.
2. **Không.** Xóa logic có thể có hiệu lực ngay theo write timestamp, replica và consistency level; grace liên quan thu hồi vật lý.
3. **Không.** TTL tính theo semantics của giá trị được ghi; grace là một điều kiện dọn dấu xóa. Compaction/overlap có thể kéo dài footprint vật lý hơn.
4. Có **nguy cơ zombie data** nếu C bỏ lỡ DELETE và tombstone ở replica khác bị purge không an toàn.
5. **Chưa.** Phải xác minh phạm vi/range đã repair thành công trong cửa sổ bảo vệ, tính cả lần thất bại và downtime.
6. **Không.** Cần giữ thông tin che giá trị cũ cho đến khi có cơ chế purge an toàn xét overlap.
7. **Không.** DELETE nhiều, TTL ngắn, collection replacement, truy vấn range rộng và compaction backlog cũng có thể gây chi phí.
8. Quorum chỉ cần một tập con replica; C có thể không nằm trong tập xác nhận thành công.
9. **Không.** Compaction trong một node không đồng bộ trạng thái giữa replica.
10. Dữ liệu cũ có thể được thấy/lan truyền lại vì tombstone cần thiết đã bị mất: **zombie**.
11. **Không.** Cần đánh giá phiên bản, topology, repair, update/delete, TTL và cơ chế thu hồi chuyên biệt.
12. **Theo thời điểm ghi**, trừ khi ứng dụng chủ động tính TTL còn lại từ deadline nghiệp vụ.
13. **Không.** Bucket thay đổi hình dạng partition và phạm vi query, không xóa tombstone vốn có hay thay repair.
14. Cần xem RF, DC, node outage, repair coverage, compaction strategy/backlog, SSTable overlap, TTL/update/delete rate, p95/p99, read timeouts, cảnh báo zombie và phiên bản.
15. Ưu tiên: **(i)** xử lý an toàn node đã offline quá grace, xác minh dữ liệu/repair; **(ii)** chốt grace/repair với biên an toàn theo failure model; **(iii)** đo và giảm tombstone-heavy reads qua query/bucket/TTL/compaction thử tải được.

### Bài toán định lượng

Một hệ thống có `gc_grace_seconds = 604800` và một replica offline trong **11 ngày**. Hãy tính:

```text
Grace:     604800 / 86400 = 7 ngày
Downtime:                       11 ngày
Chênh lệch: 11 - 7 = 4 ngày vượt grace
```

**Kết luận đúng:** replica vượt cửa sổ bảo vệ 4 ngày; phải kiểm tra nguy cơ deletion bị bỏ lỡ và cách phục hồi an toàn. **Kết luận sai:** “Dữ liệu chắc chắn sống lại sau 11 ngày.” Zombie là **rủi ro có điều kiện**, không phải kết quả tất yếu từ phép trừ thời gian.

## 24. Checklist vận hành trước khi thay grace

- [ ] Xác minh **đúng table option `gc_grace_seconds`** và phiên bản Cassandra.
- [ ] Hiểu đầy đủ **replication strategy, RF, data center** và hành vi consistency của luồng đọc/ghi.
- [ ] Có số liệu **repair hoàn tất**, không chỉ lịch trên giấy; theo dõi lỗi và range coverage.
- [ ] Ghi nhận thời gian **replica offline dài nhất** và chính sách xử lý node đã vượt grace.
- [ ] Kiểm tra **khả năng restore/rejoin từ snapshot hoặc SSTable cũ**.
- [ ] Phân biệt xóa do **DELETE, NULL, collection update và TTL expiry**.
- [ ] Xem compaction strategy, SSTable overlap, repaired state và tombstone garbage collection options theo phiên bản.
- [ ] Đo tombstones per slice, SSTables per read, partition size, p95/p99 và timeout.
- [ ] Không lấy `COUNT(*)` hoặc số hàng còn sống làm phép đếm tombstone vật lý.
- [ ] Có phương án giảm read amplification ở **schema/query/TTL/mutation** trước khi hạ grace.
- [ ] Thử nghiệm thay đổi trong môi trường tương đồng production; có backup và quy trình rollback phù hợp.
- [ ] Hiểu rằng **tăng grace sau khi đã purge không tái tạo được thông tin xóa**.
- [ ] Không ép compaction/repair hàng loạt mà không có ngân sách CPU, I/O, mạng và disk headroom.
- [ ] Không đưa replica offline quá grace trở lại production nếu chưa đánh giá rủi ro zombie.
- [ ] Chỉ triển khai sau khi đánh giá được **tính đúng dữ liệu và SLO**, có owner, lịch giám sát, ngưỡng dừng.

## 25. Ghi nhớ

- `gc_grace_seconds` là **khoảng bảo vệ liên quan đến việc xét garbage collection của tombstone**, không phải TTL và không phải lịch xóa vật lý chắc chắn.
- **Xóa logic** có hiệu lực khi deletion thắng theo write timestamp/consistency; **thu hồi vật lý** là quá trình khác thông qua compaction và điều kiện an toàn.
- Replica bỏ lỡ DELETE có thể giữ **bản dữ liệu cũ**; nếu tombstone bị thu hồi quá sớm, dữ liệu đó có nguy cơ trở lại dưới dạng **zombie data**.
- **Repair đầy đủ và đúng hạn** trong quan hệ với grace là yếu tố quan trọng; hints và consistency level không thay thế hoàn toàn.
- Tombstone quá grace vẫn có thể cần giữ do **SSTable overlap**, compaction backlog, repaired state hoặc cơ chế phiên bản.
- TTL hết hạn tạo trạng thái xóa cần được dọn an toàn; **hết TTL không đồng nghĩa giải phóng ngay dung lượng**.
- **STCS, LCS và TWCS** thay đổi cách SSTable được hợp nhất, không miễn trừ các điều kiện an toàn của deletion.
- Giảm grace để hết cảnh báo tombstone là cách xử lý nguy hiểm nếu chưa có bằng chứng repair/topology và hiểu nguồn tạo dấu xóa.
- Trước khi sửa cấu hình, cần quan sát **node health, repair coverage, tombstones per slice, SSTables per read, p99, compaction backlog** và rủi ro khôi phục dữ liệu cũ.
- Thiết kế đúng partition key/bucket, thao tác DELETE/NULL/TTL có chủ đích và ứng dụng Java retry ổn định giúp **giảm số tombstone phải đọc**, song hành với chính sách grace an toàn.

Hiểu `gc_grace_seconds` và điều kiện giữ lại dấu xóa giúp vận hành Cassandra một cách có trách nhiệm: giảm chi phí đọc và compaction mà không đánh đổi tính đúng của các thao tác xóa trong hệ thống phân tán. Đây là nền tảng để phối hợp replication, consistency, repair, recovery và Java application khi dữ liệu cũ vẫn hiện diện trên nhiều replica và SSTable.

