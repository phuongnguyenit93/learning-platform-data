# Cleanup dữ liệu không còn thuộc phạm vi sở hữu

## 1. Tình huống: thêm node rồi, vì sao các node cũ vẫn đầy đĩa?

Trong **Apache Cassandra**, một partition được gán token dựa trên **partition key**. Token, replication strategy và topology của cluster quyết định **những replica nào phải giữ partition đó**. Khi thêm node, chuyển token hoặc điều chỉnh topology, tập replica chịu trách nhiệm có thể thay đổi.

Giả sử ban đầu N1, N2 và N3 lưu các partition phù hợp với RF = 2. Sau khi N4 tham gia cluster và nhận một số token ranges, nhiều partition trước đây thuộc phạm vi replica N3 có thể không còn cần lưu trên N3 nữa. Dù N4 đã nhận dữ liệu qua streaming và bắt đầu phục vụ đọc/ghi, **những byte cũ trên N3 không nhất thiết biến mất ngay**.

Đó là lý do có thao tác quản trị **cleanup**: dọn dữ liệu cục bộ không còn thuộc phạm vi mà node phải lưu theo trạng thái sở hữu hiện tại. Công cụ phổ biến là **`nodetool cleanup`**.

Nhưng cleanup **không phải** là lệnh “dọn mọi thứ cũ”, “xóa tombstone thật nhanh” hay “giải phóng đĩa bất chấp cluster”. Nếu dùng quá sớm, trước khi dữ liệu đã được chuyển đúng sang các replica mới, thao tác dọn có thể biến bản sao dư thừa thành **mất dữ liệu hoặc giảm khả năng chịu lỗi**.

**Mục tiêu bài học:**

- Giải thích sự khác nhau giữa **dữ liệu vật lý còn nằm trên node** và **dữ liệu node còn có trách nhiệm lưu**.
- Xác định khi nào cần cân nhắc cleanup sau thay đổi topology.
- Hiểu cleanup khác streaming, repair, compaction, TTL và xóa snapshot.
- Thực hành kiểm tra topology, dùng `nodetool cleanup` trên **lab có kiểm soát**, xác minh sau thao tác.
- Nêu các tình huống nguy hiểm, cách giám sát và checklist vận hành an toàn.

**Giới hạn:** bài dùng full replicas thông thường và `NetworkTopologyStrategy`. Những bước thay node, tăng/giảm RF, thao tác token và cú pháp tùy chọn có thể khác theo phiên bản Cassandra. Không dùng ví dụ này như runbook chạy trực tiếp trên production khi chưa kiểm tra trạng thái thực tế.

## 2. Quyền sở hữu token khác với sự hiện diện trên đĩa

### 2.1. Từ partition key đến replica hiện tại

Một bảng ví dụ lưu phép đo theo thiết bị:

~~~sql
CREATE KEYSPACE IF NOT EXISTS topology_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 2
};

CREATE TABLE IF NOT EXISTS topology_lab.readings_by_device (
  device_id text,
  event_time timestamp,
  event_id uuid,
  reading decimal,
  PRIMARY KEY ((device_id), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

- `device_id` là **partition key**: với partitioner như `Murmur3Partitioner`, Cassandra tính token từ khóa này.
- `event_time`, `event_id` là **clustering columns**: sắp xếp/phân biệt các hàng **bên trong cùng một partition**, không tự thay đổi replica của partition.
- `NetworkTopologyStrategy` với `dc1: 2` đặt mục tiêu **hai full replica** cho mỗi partition trong DC đó, giả sử đủ node và topology hợp lệ.

Trong thực tế, Cassandra có thể dùng **virtual nodes (vnodes)**: mỗi node sở hữu nhiều token nên dữ liệu của nó trải trên nhiều đoạn không liền nhau. **Số token không bằng số bản sao**. Muốn biết node phải lưu partition nào, phải nhìn **token map + replication strategy + DC/rack placement**, không chỉ đếm số node hay số token.

### 2.2. Bốn khái niệm khác nhau

| Khái niệm | Ý nghĩa | Ví dụ sau khi thêm node |
| --- | --- | --- |
| **Natural replica/ownership hiện tại** | Node được topology và RF chọn để giữ một partition | N4 và N2 là hai replica mục tiêu mới của partition P. |
| **Dữ liệu thực còn trên disk** | SSTable cục bộ vẫn có byte từ các lần ghi/stream trước | N3 vẫn có SSTable chứa P dù không còn là replica mục tiêu. |
| **Coordinator** | Node nhận request và điều phối replica theo consistency level | N1 nhận truy vấn P nhưng không nhất thiết giữ P. |
| **Replica tạm/pending trong chuyển đổi** | Những vị trí liên quan khi topology chưa ổn định | Có thể có chuyển tiếp dữ liệu trong bootstrap; chưa nên kết luận sớm về bản sao dư. |

**Nhớ:** một node **có dữ liệu trên ổ** không chứng minh node ấy **vẫn là owner hiện tại**. Ngược lại, khi metadata cho biết N4 là owner mới, điều đó **không tự chứng minh N4 đã nhận đủ mọi dữ liệu cũ**; cần kiểm chứng quá trình streaming/bootstrap.

## 3. Ví dụ vòng token: node nào sẽ trở thành “không còn sở hữu”?

Để dễ hình dung, giả sử một DC có ba node **A, B, C** được đặt trên vòng token theo thứ tự:

~~~text
Vòng ban đầu: A → B → C → (quay về A)
RF = 2; bỏ qua các chi tiết rack/vnodes để minh họa.
~~~

Một partition P có token thuộc khoảng **ngay sau token A, trước token B**. Với quy tắc chọn replica theo chiều vòng trong mô hình đơn giản này, hai replica ban đầu là **B và C**.

Sau đó node **D** được thêm vào giữa A và B:

~~~text
Vòng mới: A → D → B → C → (quay về A)
Với P: replica mục tiêu mới = D và B.
~~~

| Giai đoạn | Replica mục tiêu của P | Dữ liệu có thể còn tồn tại |
| --- | --- | --- |
| Trước khi D tham gia | B, C | SSTable của P tại B và C. |
| D đang bootstrap/streaming | Đang chuyển tiếp sang topology mới | B, C vẫn có thể giữ P; D có thể mới nhận một phần. |
| D đã hoàn tất chuyển dữ liệu và topology ổn định | D, B | D và B phục vụ P; C vẫn **có thể** giữ byte cũ của P. |
| C chạy cleanup đúng điều kiện | D, B | P không còn trong tập dữ liệu hoạt động trên C, nếu C thực sự không còn là replica. |

~~~mermaid
flowchart TD
    S["Trước mở rộng: A - B - C, RF=2"] --> P["Partition P thuộc B và C"]
    P --> J["Thêm D giữa A và B"]
    J --> T["Bootstrap: stream dữ liệu P tới D"]
    T --> Q{"D đã sẵn sàng và topology đã ổn định?"}
    Q -->|Chưa| W["Không cleanup vội"]
    Q -->|Rồi| N["Replica mục tiêu P: D và B"]
    N --> X["C còn bản sao vật lý không cần giữ"]
    X --> Y["Cleanup trên C có thể loại P"]
~~~

Ví dụ minh họa một cách chọn replica đơn giản. Với **NTS, nhiều rack, nhiều DC và vnodes**, tập replica chính xác có thể khác sơ đồ; luôn kiểm tra theo topology thực tế trước khi chạy cleanup.

### Cleanup không làm đổi replication factor

Sau khi mở rộng, RF vẫn là **2**. `nodetool cleanup` không làm tăng hay giảm RF; nó chỉ xử lý **những phần dữ liệu trên node không còn thuộc trách nhiệm của node ấy**. Nâng RF từ 2 lên 3 là một công việc thay đổi replication khác, với yêu cầu bảo đảm replica mới nhận đủ dữ liệu trước khi kết luận trạng thái an toàn.

## 4. Cleanup thực sự làm gì bên trong một node?

Cassandra ghi mutation vào **memtable**, flush thành **SSTable bất biến**. Một SSTable có thể chứa nhiều partition thuộc nhiều token ranges. Sau khi thay đổi ownership, trong cùng một SSTable có thể tồn tại:

1. Partition vẫn thuộc phạm vi của node và **phải giữ**.
2. Partition đã chuyển sang tập replica khác và **có thể bỏ khỏi node này**.

Cleanup là hoạt động **lọc dữ liệu theo quyền sở hữu hiện tại**. Vì file SSTable không được sửa từng dòng tại chỗ theo cách của một bảng quan hệ, quá trình có thể phải đọc, giữ lại những dữ liệu thuộc phạm vi node, ghi SSTable mới hoặc loại bỏ SSTable không còn cần thiết, rồi giải phóng các file cũ khi an toàn.

~~~mermaid
flowchart LR
    A["SSTable cũ trên node C"] --> B{"Partition thuộc replica set hiện tại của C?"}
    B -->|Có| K["Giữ dữ liệu thuộc C"]
    B -->|Không| D["Loại khỏi tập dữ liệu hoạt động của C"]
    K --> N["SSTable kết quả sau cleanup"]
    D --> F["File cũ được giải phóng khi không còn tham chiếu"]
~~~

**Các giới hạn cần nhớ:**

- Cleanup **không gửi phần dữ liệu vừa bỏ sang node mới**; phần chuyển dữ liệu thuộc **bootstrap/streaming** và các quy trình đồng bộ riêng.
- Cleanup **không sửa khác biệt giữa replica**, không đối chiếu timestamp/tombstone giữa nhiều node như anti-entropy repair.
- Cleanup **không tạo thêm replica** và không đảm bảo mọi replica mục tiêu đã có dữ liệu nếu bước streaming trước đó lỗi.
- Cleanup **không đảm bảo dung lượng đĩa giảm ngay**: việc viết lại SSTable có thể cần không gian tạm; snapshot/backup, file đang tham chiếu hoặc tác vụ nền có thể giữ byte cũ.
- **Mất một bản sao “thừa”** không đồng nghĩa một thao tác `DELETE` CQL và cũng không tạo tombstone cho dữ liệu hiện đang thuộc node khác.

### Về “thu hồi”

Cleanup thu hồi dữ liệu vì **không còn trách nhiệm lưu theo token ownership**. Nó khác việc **TTL đã hết hạn** hoặc tombstone đủ điều kiện purge. Hai cơ chế có thể cùng tác động tới SSTable nhưng tiêu chí loại bỏ là khác nhau.

## 5. Cleanup khác những thao tác Cassandra hay bị nhầm

| Thao tác | Mục tiêu chính | Có thay thế cleanup không? |
| --- | --- | --- |
| **Bootstrap/streaming** khi thêm node | Chuyển dữ liệu cần thiết cho replica mới | **Không.** Node cũ vẫn có thể giữ những dữ liệu không còn thuộc sở hữu sau khi chuyển. |
| **`nodetool cleanup`** | Bỏ dữ liệu cục bộ mà node không còn là replica theo topology hiện tại | Là thao tác đang xét; không streaming dữ liệu cho replica khác. |
| **Anti-entropy repair** | Đồng bộ chênh lệch dữ liệu giữa các replica thuộc phạm vi repair | **Không.** Repair không có mục tiêu xóa mọi phần không còn thuộc node. |
| **Compaction thông thường** | Hợp nhất SSTable, tối ưu lưu trữ, purge dữ liệu/tombstone đủ điều kiện | **Không đồng nghĩa.** Nó không phải lệnh phân loại dữ liệu theo ownership mới. |
| **`nodetool decommission`** | Rút một node đang hoạt động khỏi vòng theo quy trình có chuyển dữ liệu/topology | **Không.** Cleanup được xét trên **node vẫn tham gia** nhưng có dữ liệu dư. |
| **`nodetool removenode`** | Xử lý thành viên không còn tồn tại theo quy trình của cluster | **Không.** Đây là thay đổi membership, không phải chỉ xóa SSTable cục bộ. |
| **TTL/tombstone** | Quyết định dữ liệu đã hết hiệu lực hoặc bị xóa về mặt logic | **Không.** TTL không có nghĩa node đã mất ownership. |
| **Snapshot/backup** | Có điểm phục hồi khi hỏng hóc/xóa nhầm | **Không.** File backup có thể vẫn chiếm disk dù cleanup thành công. |
| **`clearsnapshot`** | Loại snapshot theo chính sách retention | **Không.** Dọn snapshot không xác định đúng replica ownership. |

Một cách ngắn gọn:

~~~text
Topology change + streaming : bản sao cần thiết được chuyển tới nơi mới.
Cleanup                     : bản sao vật lý cũ không còn thuộc node được bỏ.
Repair                      : các replica cần giữ dữ liệu được đối chiếu/đồng bộ.
Compaction                  : SSTable cục bộ được tổ chức lại.
Backup                      : giữ khả năng khôi phục khi dữ liệu bị mất/xóa sai.
~~~

Các thao tác phục vụ các mục tiêu **bổ sung nhưng không hoán đổi được**.

## 6. Khi nào nên xem xét chạy cleanup?

Tình huống điển hình là **mở rộng cluster bằng bootstrap node mới**. Các node hiện hữu từng giữ những token ranges mà topology mới chuyển trách nhiệm cho replica khác; phần dữ liệu cũ có thể vẫn chiếm chỗ.

Một số thay đổi khác cũng có thể làm ownership dịch chuyển, nhưng **không được mặc định luôn phải chạy cleanup**:

- **Chuyển token hoặc di chuyển node** trong những phiên bản/quy trình có hỗ trợ: ownership có thể dịch chuyển; cần xem quy trình chính thức và bước streaming.
- **Thay đổi replication/topology giữa các DC hoặc rack**: có thể cần redistributing/repair và cleanup có điều kiện, nhưng thay metadata **không chứng minh đã có dữ liệu ở đủ replica mới**.
- **Decommission/replace/removenode**: có các bước điều phối và dọn dữ liệu riêng; phải thực hiện đúng quy trình tương ứng, không thay bằng `cleanup` một cách máy móc.

### Những điều *không phải* lý do đủ để cleanup

- `nodetool tablestats` báo dung lượng lớn nhưng **không có thay đổi ownership**.
- Bảng có nhiều **tombstone** hoặc TTL đã hết.
- Một replica vừa bị down, write timeout hoặc dữ liệu read khác nhau.
- Node còn ít disk trống và muốn “thử xem cleanup có giảm không”.

Với những trường hợp đó, hãy tìm nguyên nhân thật: thiết kế partition/bucket, compaction, repair, backup retention, disk growth hoặc lỗi node. Cleanup không phải công cụ dọn đĩa tổng quát.

## 7. Những điều kiện an toàn **trước** cleanup

**Không thực hiện cleanup trong khi đang chuyển ownership chưa hoàn tất.** Đây là quy tắc quan trọng nhất.

### Checklist tiền điều kiện

1. **Cluster ổn định:** các node cần thiết đã `UN` (Up/Normal) theo `nodetool status`, không còn node `UJ`/joining hoặc topology transition bất thường.
2. **Bootstrap/streaming hoàn tất:** xác nhận qua tiến trình bootstrap, `nodetool netstats`, logs/monitoring; không dựa duy nhất vào việc node mới đã xuất hiện trong danh sách.
3. **RF và placement hợp lệ:** `NetworkTopologyStrategy` có RF đúng cho từng DC; đủ node/rack theo yêu cầu fault tolerance.
4. **Tập replica mới đã nhận dữ liệu cần thiết:** kiểm tra trạng thái streaming và sự hội tụ dữ liệu; cân nhắc repair/validation theo quy trình nếu có lỗi chuyển dữ liệu hoặc write bị lỡ.
5. **Không có thay đổi topology đang chạy đồng thời:** không cleanup khi bootstrap, decommission, move, replace hoặc chỉnh RF đang dở.
6. **Có phương án khôi phục:** backup/snapshot theo chính sách và đã biết cách restore; hiểu rằng snapshot có thể khiến disk chưa giảm.
7. **Đủ tài nguyên:** disk free phù hợp, I/O/CPU/network và compaction backlog cho phép thực hiện bảo trì; cleanup có thể tạo file tạm.
8. **Giới hạn phạm vi:** xác định **node nào**, **keyspace/table nào** thực sự cần cleanup, cùng lịch chạy và kế hoạch rollback/ứng phó lỗi.

~~~mermaid
flowchart TD
    A["Vừa thay đổi topology"] --> B{"Streaming/bootstrap đã hoàn tất?"}
    B -->|Không| X["Dừng: chưa cleanup"]
    B -->|Có| C{"Ring, RF, DC/rack và replica ownership ổn định?"}
    C -->|Không| X
    C -->|Có| D{"Đã kiểm tra sức khỏe, repair cần thiết, backup và disk?"}
    D -->|Không| Y["Hoàn thiện tiền điều kiện"]
    D -->|Có| E["Chọn từng node cũ và phạm vi bảng"]
    E --> F["Chạy cleanup có giám sát"]
    F --> G["Xác minh dữ liệu, ownership, dung lượng và logs"]
~~~

Nếu một node vừa mất liên lạc hoặc cluster chưa đủ replica cho RF, vấn đề không nằm ở tốc độ cleanup mà ở **tính an toàn của việc xóa bản sao cũ**. Cần xử lý tình trạng replica trước.

## 8. Thực hành CQL và `nodetool` trong môi trường lab

### 8.1. Chuẩn bị bảng và dữ liệu

Ví dụ cần **một lab nhiều node** có data center thực tế tên `dc1`. Nên có tối thiểu ba node trước khi thử thêm node, RF = 2 như mục 2. Không dùng cùng thao tác trên cluster phục vụ production.

~~~sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO topology_lab.readings_by_device
  (device_id, event_time, event_id, reading)
VALUES
  ('device-7', '2026-11-21T08:00:00Z',
   123e4567-e89b-42d3-a456-426614174001, 21.50);

INSERT INTO topology_lab.readings_by_device
  (device_id, event_time, event_id, reading)
VALUES
  ('device-8', '2026-11-21T08:05:00Z',
   123e4567-e89b-42d3-a456-426614174002, 22.75);

SELECT device_id, event_time, event_id, reading
FROM topology_lab.readings_by_device
WHERE device_id = 'device-7';
~~~

`LOCAL_QUORUM` với RF = 2 trong `dc1` đòi `floor(2/2)+1 = 2` phản hồi replica. Nó **không bảo đảm mọi node trong cluster** đã lưu cùng dữ liệu; chỉ những replica mục tiêu theo RF của partition cần tham gia.

Nếu chạy CQL trước khi tạo keyspace/table, hãy tạo chúng theo mục 2. `CONSISTENCY` là lệnh của **cqlsh**, không phải một câu CQL mà Java Driver gửi trực tiếp.

### 8.2. Xem trạng thái trước bootstrap

Trên một node Cassandra phù hợp:

~~~bash
nodetool status
nodetool ring
nodetool netstats
nodetool help cleanup
~~~

- **`status`**: kiểm tra membership, DC/rack và trạng thái `UN`/joining/leaving.
- **`ring`**: xem token ownership; với vnodes, một node có nhiều token.
- **`netstats`**: xem streaming/reception khi có; hữu ích để xác nhận không còn công việc chuyển dữ liệu đang dở.
- **`help cleanup`**: kiểm tra **cú pháp đúng theo phiên bản Cassandra đang chạy**.

Với bảng ví dụ có partition key **một cột `device_id text`**, có thể tìm natural endpoints dự kiến của một giá trị khóa bằng lệnh thích hợp nếu phiên bản hỗ trợ:

~~~bash
nodetool getendpoints topology_lab readings_by_device device-7
~~~

Lệnh này giúp đối chiếu endpoint dự kiến **trước/sau thay đổi topology**. Nó không tự xác minh nội dung SSTable của từng node hay chứng minh streaming đã hoàn tất. Với partition key kép, cách đưa key cho công cụ có thể phức tạp hơn; ví dụ cố ý dùng partition key đơn cho dễ thực hành.

### 8.3. Hoàn tất việc mở rộng bằng runbook riêng

Thêm node mới là một quy trình độc lập: cấu hình đúng cluster name, seeds, DC/rack, partitioner, token, storage, networking và bảo mật; khởi động bootstrap, theo dõi streaming, xác nhận node đã tham gia bình thường và replica ownership mới hợp lệ.

Bài này **không** biến việc tạo node thành một lệnh CQL. Trước khi thực hành cleanup, lưu lại snapshot thông tin token map/endpoint trước–sau và xác nhận **dữ liệu đích đã được chuyển đầy đủ**.

### 8.4. Chạy cleanup **chỉ sau khi** tất cả tiền điều kiện đạt

Trên một **node cũ** mà ownership đã thay đổi, thử cleanup **phạm vi bảng cụ thể** trong lab:

~~~bash
# Chạy TRÊN node cũ đã xác minh an toàn và có dữ liệu không còn thuộc sở hữu.
nodetool cleanup topology_lab readings_by_device
~~~

Không chạy mù trên mọi node chỉ vì command thành công ở một node. Có thể cần cleanup ở nhiều node cũ, nhưng **mỗi node phải được xác định riêng** theo ring và tập replica mới. Node mới vừa bootstrap thường nhận dữ liệu chứ không phải nơi ưu tiên dọn bản sao dư sau mở rộng.

`nodetool cleanup` có thể chạy trên **keyspace hoặc một nhóm table**, tùy cú pháp phiên bản. Dùng `nodetool help cleanup` để xem cờ điều chỉnh mức song song nếu có; không tự tăng số job vì cleanup có thể tranh I/O với đọc/ghi.

### 8.5. Quan sát và đối chiếu sau cleanup

~~~bash
nodetool compactionstats
nodetool tablestats topology_lab.readings_by_device
nodetool status
nodetool getendpoints topology_lab readings_by_device device-7
~~~

Sau đó chạy lại câu truy vấn CQL theo partition key:

~~~sql
CONSISTENCY LOCAL_QUORUM;

SELECT event_time, event_id, reading
FROM topology_lab.readings_by_device
WHERE device_id = 'device-7';
~~~

**Điều cần xác minh** là truy vấn vẫn thấy dữ liệu hợp lệ, các natural endpoints sau thay đổi là những node mong đợi, không có streaming/repair lỗi chưa xử lý, và dung lượng/SSTable metrics thay đổi hợp lý theo thời gian.

**Điều không được suy ra:** một câu `SELECT` thành công tại `LOCAL_QUORUM` không chứng minh tất cả replica mục tiêu đã được repair hay không còn bản sao cũ ở bất kỳ node nào. Nó chỉ kiểm tra kết quả đọc theo CL tại thời điểm thử nghiệm.

## 9. Vì sao dung lượng có thể chưa giảm ngay?

Cleanup có thể phải tạo **SSTable mới chứa những partition còn thuộc node**, trong khi file cũ đang được tham chiếu bởi tác vụ đọc/compaction, snapshot hoặc backup. Do đó có thể thấy một khoảng thời gian disk sử dụng **không giảm**, thậm chí **tăng tạm thời**.

| Hiện tượng | Nguyên nhân cần điều tra | Cách hiểu |
| --- | --- | --- |
| Cleanup hoàn tất nhưng disk hầu như không đổi | Node vẫn sở hữu gần hết dữ liệu; dung lượng thừa ít; snapshot/backup giữ file | Không tự khẳng định cleanup thất bại. |
| Disk tăng trong lúc cleanup | Viết SSTable mới, còn file cũ cho tới khi thay thế an toàn | Cần headroom và theo dõi compaction. |
| `tablestats` thay đổi chậm | Hoạt động background, thống kê cập nhật theo thời gian | Quan sát xu hướng sau khi task thật sự kết thúc. |
| Snapshot vẫn chiếm nhiều dung lượng | Hard links/snapshot retention giữ file SSTable | Dọn snapshot theo **chính sách backup** riêng, không xóa tùy tiện. |
| Cleanup chạy lâu hoặc timeout | Nhiều SSTable lớn, I/O saturation, concurrency cao, tombstone/compaction backlog | Tìm bottleneck; không tăng đồng thời vô hạn. |
| Cleanup không làm mất dữ liệu ở node mục tiêu mới | Đúng kỳ vọng: node mới **cần** giữ partition theo RF | Cleanup không phải thao tác xóa dữ liệu toàn cluster. |

Tỷ lệ dữ liệu được thu hồi **không nhất thiết bằng 1 / số node vừa thêm**. Phân bố vnodes, RF, kích thước partition, lượng dữ liệu, rack/DC và tập replica mới làm mỗi node có tỉ lệ khác nhau.

## 10. Cleanup, consistency level và repair

Cassandra sử dụng CL cho yêu cầu đọc/ghi, ví dụ `LOCAL_ONE` hay `LOCAL_QUORUM`. Cleanup **không phải lệnh CQL có consistency level**; nó là thao tác quản trị trên dữ liệu lưu cục bộ của node.

Giả sử trước khi thêm N4, N3 là replica của P. Sau thay đổi, N4 phải nhận P và N3 trở thành non-owner:

- Nếu **N4 nhận đủ dữ liệu P**, N3 có thể dọn phần P không còn thuộc mình.
- Nếu **N4 bootstrap thiếu dữ liệu** nhưng N3 bị cleanup vội, hệ thống có thể mất một bản sao đúng hoặc mất những mutation chưa chuyển.
- Nếu **N4 có dữ liệu nhưng một replica mục tiêu khác bỏ lỡ write/delete**, cleanup không sửa sự khác biệt đó. **Repair** đúng phạm vi mới là cơ chế đồng bộ cần xem xét.
- Nếu **xóa/tombstone** chưa hội tụ và `gc_grace_seconds` bị cấu hình quá ngắn, việc đưa replica dữ liệu cũ trở lại có thể gây zombie; cleanup không thay thế quy trình repair và xử lý node offline lâu.

Một thao tác `LOCAL_QUORUM` thành công chỉ xác nhận ngưỡng phản hồi theo RF và DC; nó không kiểm chứng đầy đủ quá trình chuyển ownership hay cho phép loại bỏ mọi bản sao cũ ngay lập tức.

## 11. Tích hợp ứng dụng Java: cleanup không phải API ứng dụng

Ứng dụng **Apache Cassandra Java Driver 4.x** thường không cần thay mã khi cluster mở rộng đúng cách. Driver cập nhật metadata topology/token map, định tuyến các truy vấn có partition key tới những replica phù hợp theo chính sách. Dữ liệu được tìm theo cùng một khóa logic dù natural endpoints thay đổi.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.net.InetSocketAddress;

public final class ReadDeviceAfterTopologyChange {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement query = session.prepare(
                "SELECT event_time, event_id, reading " +
                "FROM topology_lab.readings_by_device " +
                "WHERE device_id = ? LIMIT 20");

            BoundStatement read = query.bind("device-7")
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

            for (Row row : session.execute(read)) {
                System.out.println(row.getInstant("event_time")
                    + " | " + row.getBigDecimal("reading"));
            }
        }
    }
}
~~~

**Giải thích:**

1. `WHERE device_id = ?` cung cấp đủ partition key, giúp driver dùng **token-aware routing** nếu cấu hình/topology phù hợp.
2. `LOCAL_QUORUM` với RF = 2 ở `dc1` yêu cầu hai phản hồi, nhưng **không khởi chạy cleanup** và không chứng minh các replica mới đã được stream đầy đủ.
3. `withLocalDatacenter("dc1")` phải khớp DC thật; `127.0.0.1` là ví dụ lab. Production cần contact points, auth/TLS và timeout phù hợp.
4. Khi bootstrap đang diễn ra, ứng dụng có thể gặp latency cao hơn hoặc sự cố routing/tải; không nên xử lý bằng cách cho ứng dụng tự chạy `nodetool cleanup`.
5. Cleanup thuộc **kênh vận hành có phân quyền riêng**; không nên cấp tài khoản API Java quyền thực thi các lệnh bảo trì cluster chỉ để giảm disk usage.

Nếu ứng dụng thấy dữ liệu không nhất quán sau mở rộng, hãy kiểm tra topology, streaming, CL, timeout và repair. Việc “chạy cleanup thêm lần nữa” **không phải biện pháp sửa dữ liệu thiếu trên replica**.

## 12. Xử lý sự cố khi cleanup không như mong đợi

### 12.1. Checklist chẩn đoán

1. **Đã bootstrap hoàn tất chưa?** Kiểm tra trạng thái node và session streaming, không dựa vào trạng thái nhìn thấy từ một thời điểm ngắn.
2. **Token map có ổn định không?** Có node đang join/leave/move hay thay RF/rack/DC đồng thời?
3. **Dữ liệu cần chuyển đã đến replica mới chưa?** Kiểm tra endpoint mapping, logs streaming/repair, dữ liệu mẫu theo partition key và metrics.
4. **Cleanup chạy ở đúng node không?** Đây có phải node cũ đã mất ownership của một phần token range không?
5. **Đã chọn đúng keyspace/table chưa?** Lệnh trên một bảng không dọn mọi keyspace.
6. **Có thiếu disk headroom không?** Có compaction chồng chéo, snapshot giữ file hoặc backlog nặng?
7. **Các file vật lý còn được tham chiếu không?** Phân biệt active SSTable, snapshot/backup và file chưa được giải phóng.
8. **Kết quả repair và CL ra sao?** Một request thành công không thể thay thế kiểm tra replica convergence.

### 12.2. Các lỗi phổ biến và cách tránh

| Tình huống | Không nên làm | Hướng xử lý |
| --- | --- | --- |
| D mới đang bootstrap, N3 vẫn còn dữ liệu cũ | Cleanup ngay vì thấy bản sao thừa | Chờ bootstrap/streaming hoàn tất và kiểm chứng topology. |
| Sau cleanup, dung lượng node cũ chưa giảm | Xóa file SSTable thủ công | Kiểm tra active SSTable, compaction, snapshot và retention. |
| Thiếu disk, cleanup kéo dài | Chạy song song trên mọi node để xong nhanh | Tính disk headroom, throttle/schedule, giới hạn số node và công việc đồng thời. |
| D mới đọc thiếu một số hàng | Cleanup trên node khác để “đồng bộ” | Điều tra streaming/replica/repair; cleanup không chuyển dữ liệu. |
| Nhiều DC, NTS đặt RF theo DC | Dùng sơ đồ vòng một DC làm sự thật tuyệt đối | Xác minh natural endpoints theo token, rack và DC của cluster thật. |
| Một node đã offline lâu, tombstone chưa repair | Hạ `gc_grace_seconds` cho nhanh | Xử lý theo runbook repair/rebuild để tránh zombie data. |
| Topology lại thay đổi giữa cleanup | Tiếp tục với giả định token map cũ | Đánh giá tính an toàn, dừng/replan theo tình trạng mới. |

**Nếu cleanup lỗi giữa chừng**, không tự kết luận dữ liệu mất hoặc sạch hoàn toàn. Cần kiểm tra logs, số SSTable và trạng thái topology/replica trước khi quyết định thử lại; các bản Cassandra khác nhau có thể xử lý tiến độ/lỗi theo cách khác nhau.

## 13. Bài tập tự kiểm tra có đáp án

**Bài 1.** Một partition P từng có replica B và C. Sau thêm node D, theo topology mới P thuộc B và D. Streaming vào D đã hoàn tất. C có thể giữ dữ liệu P trên SSTable không?

**Đáp án:** **Có.** Dữ liệu vật lý có thể tồn tại trên C dù C không còn là natural replica. Cleanup trên C có thể loại dữ liệu không còn thuộc trách nhiệm, khi điều kiện an toàn được xác minh.

**Bài 2.** Sau khi thêm node, `nodetool cleanup` có tự nhân bản dữ liệu từ node cũ sang node mới không?

**Đáp án:** **Không.** Bootstrap/streaming và các cơ chế đồng bộ đảm nhiệm việc chuyển dữ liệu. Cleanup chỉ dọn dữ liệu cục bộ không còn thuộc sở hữu.

**Bài 3.** RF = 3 ở `dc1`; cluster có sáu node trong DC. Một partition có bao nhiêu natural replicas và `LOCAL_QUORUM` cần bao nhiêu phản hồi?

**Đáp án:** Mục tiêu **ba replica**, không phải sáu. `LOCAL_QUORUM = floor(3/2)+1 = 2`. Cleanup không thay con số này.

**Bài 4.** Khi `nodetool status` vẫn cho thấy node mới `UJ` và `netstats` đang streaming, có nên cleanup các node cũ để giảm disk ngay?

**Đáp án:** **Không.** Chuyển dữ liệu và topology chưa ổn định. Xóa bản sao cũ quá sớm có thể làm thiếu dữ liệu/giảm khả năng chịu lỗi.

**Bài 5.** Vì sao cleanup đã thành công nhưng filesystem vẫn chiếm gần như cũ?

**Đáp án:** Có thể node mất rất ít ownership, SSTable cần giữ nhiều partition, công việc nền còn đang xử lý, hoặc snapshot/backup và file tham chiếu vẫn giữ byte trên đĩa. Cần đối chiếu metrics trước khi kết luận.

**Bài 6.** Một nhóm đề xuất dùng `nodetool cleanup` để xóa các tombstone cũ sau TTL và thay cho repair. Đề xuất này có đúng không?

**Đáp án:** **Không.** Cleanup dựa trên ownership hiện tại; việc purge tombstone tuân theo compaction và các điều kiện an toàn, còn repair đối chiếu replica. Ba mục tiêu khác nhau.

**Bài 7.** Vì sao không nên chỉ nhìn token count khi quyết định node nào cần cleanup?

**Đáp án:** Token count không cho biết đủ replica ownership của từng partition. Cần xem token ranges, vnodes, `NetworkTopologyStrategy`, RF theo DC và rack placement. Hai node có cùng số token vẫn có thể thay đổi ownership khác nhau.

**Bài 8.** Sau mở rộng cluster, ứng dụng Java vẫn dùng `SELECT ... WHERE device_id=?`. Có cần sửa partition key để Cassandra định tuyến đến node mới không?

**Đáp án:** Thường **không**, nếu schema và mô hình truy vấn không đổi. Cassandra và driver dựa trên token map/topology cập nhật để định tuyến. Nếu có lỗi sau mở rộng, kiểm tra metadata, streaming, replica/CL và health thay vì đổi primary key một cách tùy tiện.

## 14. Quy trình quyết định trước và sau cleanup

~~~mermaid
flowchart TD
    A["Thay đổi topology Cassandra"] --> B["Kiểm tra RF, DC/rack, token map"]
    B --> C{"Node mới/chuyển token đã ổn định và stream xong?"}
    C -->|Không| D["Không cleanup; xử lý bootstrap/streaming"]
    C -->|Có| E{"Có node cũ đang giữ dữ liệu ngoài ownership?"}
    E -->|Không / chưa rõ| F["Quan sát thêm; không chạy theo thói quen"]
    E -->|Có| G{"Có backup, disk headroom, repair/health OK?"}
    G -->|Không| H["Hoàn thành điều kiện an toàn"]
    G -->|Có| I["Cleanup có kiểm soát trên node/table phù hợp"]
    I --> J["Theo dõi compaction, SSTable và errors"]
    J --> K["Xác minh natural endpoints, đọc CQL và dung lượng"]
    K --> L["Lưu log, cập nhật runbook và kết quả bảo trì"]
~~~

**Ghi nhớ:** sau một thay đổi topology, **quyền sở hữu dữ liệu** có thể chuyển sang những replica mới, nhưng **SSTable trên node cũ vẫn có thể chứa bản sao vật lý không còn cần thiết**. `nodetool cleanup` giúp thu hồi những phần đó **sau khi** topology và streaming đã ổn định. Nó không thay streaming, repair, compaction hay backup. Sự an toàn của cleanup phụ thuộc việc xác minh **ai đang phải lưu dữ liệu, dữ liệu đã đến nơi mới chưa và khả năng phục hồi còn đủ hay không**, chứ không phụ thuộc mong muốn giải phóng đĩa càng sớm càng tốt.
