# Neo4j CDC và điều kiện hỗ trợ theo phiên bản hoặc edition

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích **Change Data Capture (CDC)** trong Neo4j là gì, khác với nhập dữ liệu theo lô, truy vấn định kỳ và các cơ chế phát sự kiện của ứng dụng như thế nào.
- Xác định **phiên bản Neo4j, edition/gói Aura, tên procedure và quyền truy cập** trước khi thiết kế tích hợp CDC.
- Bật CDC ở chế độ `DIFF` hoặc `FULL`, kiểm tra cấu hình và đọc các thay đổi bằng Cypher.
- Thiết kế một consumer có **cursor/checkpoint**, xử lý retry, chống trùng, sự cố hết transaction log và phục hồi sau khôi phục database.
- Lựa chọn CDC hay phương án tích hợp khác khi phiên bản, edition hoặc yêu cầu vận hành chưa đáp ứng.

Chương **Tích hợp dữ liệu** của module **DATABASE_ENGINE_GRAPH_NEO4J** đặt Neo4j vào dòng dữ liệu giữa ứng dụng Java/Spring Data Neo4j, message broker và các hệ thống phân tích hoặc tìm kiếm. Neo4j mô hình hóa quan hệ qua **property graph** với node, relationship và thuộc tính; CDC giúp bên ngoài nhận biết sự thay đổi của các phần tử này khi giao dịch được commit.

> **Phạm vi phiên bản:** Bài sử dụng cú pháp CDC dành cho Neo4j 5.17 trở lên, cùng những lưu ý khi dùng phiên bản 5.13–5.16. Các tính năng của edition và dịch vụ đám mây có thể thay đổi; trước khi triển khai, luôn kiểm tra **version, edition/gói dịch vụ, quyền người dùng và tài liệu khớp phiên bản**. Ví dụ cấu hình mang tính minh họa và cần tài khoản quản trị phù hợp.

## 1. CDC là gì và giải quyết bài toán nào?

**Change Data Capture** là kỹ thuật nhận các thay đổi dữ liệu đã được commit để hệ thống khác có thể xử lý tiếp. Với Neo4j CDC chính thức, thông tin thay đổi được khai thác từ **transaction log đã được làm giàu** (*transaction-log enrichment*). Một thay đổi có thể liên quan tới:

- **Node:** tạo node mới, cập nhật label/thuộc tính, xóa node.
- **Relationship:** tạo, cập nhật thuộc tính, xóa relationship.
- **Thông tin giao dịch:** mã giao dịch, thứ tự sự kiện trong giao dịch, thời gian và metadata theo cấu trúc CDC cung cấp.

Ví dụ một ứng dụng dùng Neo4j quản lý quan hệ `Customer` —`PLACED`→ `Order`. Khi đơn hàng đổi từ `PENDING` thành `PAID`, hệ thống tìm kiếm có thể cập nhật chỉ mục tìm kiếm, bộ phận analytics có thể tính lại báo cáo và một dịch vụ downstream có thể phản ứng với thay đổi đó.

~~~mermaid
flowchart LR
    A["Ứng dụng Java / Spring Data Neo4j"] -->|Cypher transaction| N[("Neo4j")]
    N --> L["Transaction log<br/>CDC enrichment"]
    L --> C["CDC consumer<br/>checkpoint + retry"]
    C --> K["Kafka / event bus"]
    C --> D[("Search / Analytics")]
~~~

**Điểm phân biệt:** Neo4j CDC cung cấp **dòng thay đổi của Neo4j**. Nó không tự động tạo HTTP webhook, không tự đẩy vào Kafka nếu chưa có connector/consumer, và không thay thế một luồng snapshot ban đầu cho toàn bộ dữ liệu hiện hữu.

| Cách tích hợp | Thường dùng khi | Giới hạn chính |
| --- | --- | --- |
| **CDC từ transaction log** | Theo dõi create/update/delete đã commit, đồng bộ hệ thống downstream | Cần hỗ trợ version/edition, quyền, checkpoint và lưu giữ log |
| **Đọc định kỳ bằng Cypher** | Nhu cầu đơn giản, chấp nhận trễ, môi trường không hỗ trợ CDC | Khó phát hiện delete; phải tự quản lý watermark, bỏ sót/thừa dữ liệu |
| **Sự kiện từ ứng dụng / transactional outbox** | Muốn phát sự kiện nghiệp vụ như `OrderPaid` | Ứng dụng phải thiết kế phát sự kiện và xử lý publish đáng tin cậy |
| **Import CSV / batch / snapshot** | Nạp dữ liệu ban đầu hoặc tái dựng dữ liệu | Không theo dõi thay đổi liên tục sau lần nạp |

CDC phản ánh **thay đổi mức dữ liệu**, không phải mọi ý nghĩa nghiệp vụ. Một lần cập nhật thuộc tính `status` thành `PAID` có thể là tín hiệu, nhưng việc “đã thanh toán hợp lệ” còn phụ thuộc logic nghiệp vụ ngoài database.

## 2. Ma trận hỗ trợ theo version và edition

Phải kiểm tra **hai trục riêng biệt**: **phiên bản** và **edition/gói triển khai**. Chỉ nâng cấp version nhưng vẫn dùng edition không hỗ trợ sẽ không biến CDC thành tính năng sẵn có.

| Môi trường | Hỗ trợ CDC chính thức | Lưu ý |
| --- | --- | --- |
| **Neo4j Community Edition tự quản** | **Không** có CDC chính thức như Enterprise | Một procedure có tên tương tự hoặc plugin khác không tương đương hỗ trợ CDC |
| **Neo4j Enterprise Edition 5.13–5.16** | Có từ **5.13**, giai đoạn beta | Dùng procedure tên cũ `cdc.current`, `cdc.earliest`, `cdc.query`; kiểm tra ràng buộc cụ thể phiên bản |
| **Neo4j Enterprise Edition 5.17–5.22** | Có, vẫn trong giai đoạn beta | Procedure chuyển sang namespace `db.cdc.*` từ 5.17 |
| **Neo4j Enterprise Edition từ 5.23** | CDC đã ra khỏi beta | Tính năng vẫn cần bật theo database và cấu hình quyền/retention |
| **Neo4j 2025.x/2026.x Enterprise** | Kiểm tra tài liệu phát hành tương ứng; CDC tiếp tục có trong tài liệu hiện hành | Tên trường bổ sung trong procedure có thể phụ thuộc **phiên bản và Cypher version** |
| **AuraDB Business Critical / AuraDB Virtual Dedicated Cloud** | Có theo tài liệu CDC hiện hành | Bật qua **Edit CDC Mode** trong điều khiển Aura; không dùng lệnh quản trị của self-managed như một hướng dẫn phổ quát |
| **Các gói AuraDB khác** | **Không giả định** tính năng có sẵn | Kiểm tra ma trận tính năng chính thức và quyền quản trị của chính gói đang thuê |

Các mốc đáng nhớ:

1. **Neo4j 5.13:** CDC chính thức xuất hiện ở dạng **beta**, dành cho Enterprise và AuraDB Enterprise ở thời điểm phát hành.
2. **Neo4j 5.17:** đổi tên `cdc.earliest/current/query` thành `db.cdc.earliest/current/query`; mã ứng dụng cũ phải được rà soát khi nâng cấp.
3. **Neo4j 5.23:** CDC **không còn ở trạng thái beta**.
4. **Neo4j 2026.06, Cypher 25:** tài liệu hiện hành bổ sung trường `txCommitTime` vào kết quả `db.cdc.current()`; không giả định trường này tồn tại trong mọi phiên bản hoặc chế độ Cypher.

Các thông tin hỗ trợ trên dựa vào [Neo4j CDC Introduction](https://neo4j.com/docs/cdc/current/), [CDC Changelog](https://neo4j.com/docs/cdc/current/changelog/), [CDC on Neo4j DBMS](https://neo4j.com/docs/cdc/current/get-started/self-managed/) và [CDC on Aura](https://neo4j.com/docs/cdc/current/get-started/aura/). Khi viết ứng dụng cho bản đang chạy, ưu tiên tài liệu có **cùng dòng version** thay vì sao chép máy móc ví dụ từ bản mới nhất.

### 2.1. Tự kiểm tra phiên bản và môi trường đang kết nối

Trên database cho phép chạy procedure kiểm tra hệ thống:

~~~cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions, edition;
~~~

Ví dụ kết quả có thể cho biết phiên bản `5.2x` và edition `enterprise`. Hãy đối chiếu với ma trận; **không suy đoán từ tên ứng dụng Neo4j Browser** hoặc version của Java Driver.

Kiểm tra các procedure CDC xuất hiện trong catalog:

~~~cypher
SHOW PROCEDURES
YIELD name
WHERE name STARTS WITH 'db.cdc.'
RETURN name
ORDER BY name;
~~~

Với phiên bản 5.13–5.16, tên procedure có thể bắt đầu bằng `cdc.`. **Thấy tên procedure chưa đủ** để kết luận CDC đã bật và user có quyền đọc sự kiện. Trong Aura, một số truy vấn hệ thống có thể bị hạn chế; khi đó dùng thông tin phiên bản/gói và màn hình quản trị chính thức.

### 2.2. Một checklist điều kiện bắt buộc

| Câu hỏi | Kết quả cần xác nhận |
| --- | --- |
| Neo4j là edition/gói nào? | Enterprise tự quản hoặc gói Aura hiện được liệt kê hỗ trợ |
| Version chính xác? | Đúng procedure/cú pháp cho version đó |
| CDC đã bật cho **database đích**? | `DIFF` hoặc `FULL`, không phải `OFF` |
| Quyền của user? | Được truy cập database và chạy procedure CDC theo nguyên tắc ít đặc quyền |
| Log retention? | Đủ để consumer phục hồi sau ngừng hoạt động |
| Cơ chế lưu cursor? | Bền vững, theo từng database/consumer |
| Hệ thống đích? | Có khóa nghiệp vụ, chống trùng và phục hồi lỗi |

## 3. Cách Neo4j lưu thay đổi: OFF, DIFF và FULL

Neo4j cần **làm giàu transaction log** để CDC có đủ thông tin mô tả phần tử thay đổi. Mặc định, CDC **tắt**; việc tạo graph hoặc bật constraint/index không tự bật CDC.

| Mode | Ý nghĩa | Phù hợp |
| --- | --- | --- |
| `OFF` | Không ghi enrichment phục vụ CDC; đây là giá trị mặc định | Database không dùng CDC |
| `DIFF` | Với update, ghi phần thay đổi giữa trạng thái trước/sau của entity | Đồng bộ từng thay đổi, giảm dữ liệu so với FULL trong nhiều trường hợp |
| `FULL` | Ghi trạng thái đầy đủ trước/sau của entity đã thay đổi | Audit, hệ tiêu thụ cần bản ghi đầy đủ |

**Ví dụ:** Node `(:Customer {customerId:'C-101', city:'Hà Nội', tier:'SILVER'})` được cập nhật `tier` thành `GOLD`. Trong `DIFF`, phần thông tin trạng thái update chủ yếu thể hiện thay đổi của `tier`; trong `FULL`, trạng thái trước/sau có thể gồm toàn bộ các thuộc tính cần thiết để mô tả node. Với thao tác **create** và **delete**, CDC có những ngoại lệ theo bản chất sự kiện: create có dữ liệu `after`, delete có dữ liệu `before`, ngay cả trong `DIFF`.

Đổi `DIFF` ↔ `FULL` khi consumer đang chạy có thể làm **cấu trúc sự kiện thay đổi**; bộ giải mã và logic downstream phải xử lý đúng cả hai. Bật CDC tạo thêm dữ liệu transaction log, làm tăng lưu trữ, I/O và tần suất rotate/prune. Hãy đo chi phí theo workload; không dùng một tỷ lệ overhead cố định để dự trù cho mọi hệ thống.

## 4. Bật và kiểm tra CDC trên Neo4j Enterprise tự quản

> Các lệnh DDL trong phần này chỉ áp dụng khi có quyền quản trị và môi trường self-managed hỗ trợ CDC. Thực thi từ ngữ cảnh **database `system`**, theo cách client/driver của bạn lựa chọn database. Không chạy tùy tiện trên môi trường sản xuất.

### 4.1. Xem cấu hình hiện tại

~~~cypher
SHOW DATABASES
YIELD name, options
RETURN name, options
ORDER BY name;
~~~

Nếu chưa cấu hình cho database `neo4j`, `options` có thể không chứa `txLogEnrichment`, nghĩa là CDC ở chế độ mặc định `OFF`. Cần kiểm tra tên database thực tế; không phải mọi hệ thống đều sử dụng database có tên `neo4j`.

### 4.2. Bật DIFF trên database đang có

~~~cypher
// Ví dụ lệnh quản trị; chạy trên database system.
ALTER DATABASE neo4j
SET OPTION txLogEnrichment 'DIFF';
~~~

Muốn ghi nội dung đầy đủ cho các thay đổi tiếp theo, dùng `'FULL'`:

~~~cypher
ALTER DATABASE neo4j
SET OPTION txLogEnrichment 'FULL';
~~~

Sau đó chạy lại `SHOW DATABASES YIELD name, options` để xác nhận `txLogEnrichment` đúng mode. Nếu tạo **database mới** và muốn bật ngay:

~~~cypher
// Chỉ chạy khi thực sự muốn tạo database ví dụ.
CREATE DATABASE graph_events IF NOT EXISTS
OPTIONS {txLogEnrichment: 'DIFF'};
~~~

**Không tạo một bản sao dữ liệu lịch sử:** Khi bật CDC, các thay đổi **từ thời điểm bật trở đi** mới có thông tin CDC thích hợp. Muốn đồng bộ toàn bộ dữ liệu hiện hữu cần một quy trình **snapshot/backfill** riêng và cơ chế giao thoa nhất quán với phần CDC mới.

### 4.3. Tắt CDC và ảnh hưởng tới cursor

~~~cypher
// Ví dụ lệnh quản trị; không thực hiện trong bài thực hành nếu cần giữ dòng sự kiện.
ALTER DATABASE neo4j
SET OPTION txLogEnrichment 'OFF';
~~~

Tắt CDC sẽ **cắt đứt tính liên tục của change identifier**. Nếu sau đó bật lại, cursor cũ không tiếp tục được như trước; consumer phải thực hiện quy trình bootstrap/recovery. Trên self-managed cũng có thể `REMOVE OPTION txLogEnrichment` để quay về mặc định tắt.

## 5. Bật CDC trên Aura

Trên các gói AuraDB được hỗ trợ, quản trị viên dùng tùy chọn **Edit CDC Mode** trong phần quản lý instance để đặt `OFF`, `DIFF` hoặc `FULL`. Không giả định có thể sử dụng `ALTER DATABASE` như self-managed; quy trình quản trị trên Aura do dịch vụ kiểm soát.

Tài liệu Aura lưu ý:

- Instance **mới**, **clone**, **pause** hoặc **khôi phục snapshot** có thể khiến CDC trở về `OFF`.
- Khi **tắt rồi bật lại**, change identifier cũ không còn thuộc cùng chuỗi sự kiện.
- Mỗi lần đổi `DIFF`/`FULL`, consumer phải hiểu định dạng phần thay đổi tương ứng.
- Cần kiểm tra lại thiết lập sau thao tác quản trị lifecycle của instance và trước khi khởi động lại connector.

Không dùng tên gói cũ trong một bài hướng dẫn để suy luận mọi cấp độ Aura hiện hành đều có CDC. Với Aura, kiểm tra **thực tế tính năng ở instance và gói thuê**.

Nguồn: [CDC on Neo4j Aura](https://neo4j.com/docs/cdc/current/get-started/aura/).

## 6. Truy vấn change event bằng procedure

Khi đã bật CDC, Neo4j cung cấp các procedure liên quan tới **change identifier** (cursor) và tập các change event.

| Procedure từ 5.17 | Công dụng |
| --- | --- |
| `db.cdc.earliest()` | Lấy identifier ở đầu vùng thay đổi hiện còn được giữ |
| `db.cdc.current()` | Lấy identifier gần thời điểm hiện tại, phù hợp để bắt đầu theo dõi **thay đổi mới** |
| `db.cdc.query(from, selectors)` | Lấy những thay đổi **sau** identifier `from`; `selectors` tùy chọn |

Trên bản 5.13–5.16, thay `db.cdc.` bằng `cdc.` theo tài liệu của bản đó. Không tự trộn các tên procedure giữa các phiên bản.

### 6.1. Lấy cursor ban đầu

~~~cypher
CALL db.cdc.current()
YIELD id
RETURN id;
~~~

Lưu `id` trả về vào nơi an toàn tại ứng dụng. Identifier là **chuỗi opaque**: không giải mã thành số, không chỉnh sửa, không tự tính `id + 1`. Trên một số version/chế độ Cypher mới có thể có trường kết quả bổ sung; ví dụ trên cố ý chỉ `YIELD id` để phù hợp rộng hơn.

Nếu ứng dụng muốn đọc những thay đổi **còn được giữ trong log**, thay bằng:

~~~cypher
CALL db.cdc.earliest()
YIELD id
RETURN id;
~~~

`earliest` **không có nghĩa** là toàn bộ lịch sử từ ngày tạo database; nó chỉ phản ánh vùng thay đổi hiện còn sử dụng được theo cấu hình và vòng đời log.

### 6.2. Ghi dữ liệu mẫu trong transaction khác

Chạy ở một transaction riêng sau khi đã ghi lại cursor ở bước trên:

~~~cypher
MERGE (c:Customer {customerId: 'C-101'})
SET c.city = 'Hà Nội',
    c.tier = 'GOLD';
~~~

Nếu node đã tồn tại và các thuộc tính không đổi, database có thể không tạo sự kiện update như kỳ vọng. Để quan sát chắc chắn trên môi trường bài tập, hãy thay đổi một thuộc tính thực sự hoặc tạo node mới với ID bài tập riêng.

### 6.3. Đọc thay đổi từ cursor

Trong transaction đọc **thứ ba**, truyền đúng chuỗi `id` đã lưu:

~~~cypher
CALL db.cdc.query($fromId, [])
YIELD id, txId, seq, metadata, event
RETURN id, txId, seq, metadata, event;
~~~

Ví dụ tham số từ ứng dụng (thay chuỗi bằng identifier thực tế):

~~~json
{
  "fromId": "opaque-change-identifier-from-db-cdc-current"
}
~~~

**Ngữ nghĩa rất quan trọng:** `fromId` là điểm bắt đầu **exclusive**. `db.cdc.query` trả những event **sau** identifier đó, không trả lại event ngay tại điểm chỉ định. Mỗi event có `id` mới để tiếp tục đọc từ đó. Nếu gọi procedure mà không lưu/đưa đúng cursor, có thể bắt đầu từ vị trí hiện tại và **bỏ qua sự kiện trước đó**.

Đọc cursor, ghi thay đổi và gọi `db.cdc.query` là **ba transaction riêng biệt** trong ví dụ này. Không mở một transaction dài chứa cả ba rồi chờ để biến nó thành bộ thu sự kiện: CDC đọc giao dịch đã commit.

### 6.4. Nhận dạng các trường của event

Một hàng CDC thường có cấu trúc:

~~~text
id           : opaque change identifier của sự kiện
txId         : định danh transaction
seq          : vị trí sự kiện trong transaction đó
metadata     : thông tin transaction (ví dụ thời điểm commit)
event        : phần tử thay đổi, operation và trạng thái trước/sau
~~~

Ví dụ **minh họa rút gọn**, không phải output đầy đủ của procedure:

~~~json
{
  "id": "<opaque-id>",
  "txId": 42,
  "seq": 0,
  "metadata": { "captureMode": "DIFF" },
  "event": {
    "eventType": "n",
    "operation": "u",
    "labels": ["Customer"],
    "keys": {},
    "state": {
      "before": { "properties": { "tier": "SILVER" } },
      "after": { "properties": { "tier": "GOLD" } }
    }
  }
}
~~~

Trong đó:

- `eventType = 'n'` là **node**, `'r'` là **relationship**.
- `operation = 'c'` / `'u'` / `'d'` tương ứng **create / update / delete**.
- `state.before` và `state.after` chứa nội dung tùy mode và loại thao tác; bên không tồn tại (before của create, after của delete) là `null`.
- `keys` có thể hỗ trợ **định danh logic** của entity khi schema có key constraint tương ứng; `elementId` không phải khóa nghiệp vụ xuyên backup hoặc vòng đời database.
- `txId` kết hợp `seq` có thể giúp xác định vị trí sự kiện trong transaction. Đừng suy luận thứ tự thao tác ứng dụng chỉ từ `seq`; thứ tự event quan sát không nhất thiết phản ánh đúng thứ tự lệnh Cypher trong transaction.

Trong ví dụ JSON trên, `<opaque-id>` chỉ là placeholder để giải thích. Consumer phải dùng identifier do Neo4j trả về. Tham khảo [Format of change events](https://neo4j.com/docs/cdc/current/procedures/output-schema/).

## 7. Thiết kế consumer: cursor, retry và chống trùng

CDC thường được **đọc bởi consumer** theo chu kỳ/polling hoặc qua connector. Một kiến trúc đơn giản:

~~~mermaid
flowchart TB
    A["Đọc cursor đã commit"] --> B["db.cdc.query(cursor)"]
    B --> C{"Có event mới?"}
    C -->|Không| W["Chờ/poll tiếp theo"]
    W --> B
    C -->|Có| D["Giải mã + validate event"]
    D --> E["Upsert/delete downstream bằng khóa ổn định"]
    E --> F{"Sink xác nhận bền vững?"}
    F -->|Không| R["Retry, chưa tiến cursor"]
    R --> E
    F -->|Có| G["Lưu cursor của event vừa xử lý"]
    G --> B
~~~

### 7.1. Những nguyên tắc bắt buộc

1. **Lưu cursor bền vững** theo đúng database và consumer/subscription; không chỉ giữ trong RAM.
2. **Xử lý và xác nhận downstream trước khi tiến cursor**. Nếu tiến cursor trước rồi crash khi đang ghi sink, sự kiện có thể mất.
3. **Chấp nhận xử lý lặp**: nếu sink đã commit nhưng consumer crash trước khi lưu cursor, cùng event sẽ đến lại sau restart.
4. **Deduplication/idempotency:** dùng khóa event `id` hoặc danh tính nghiệp vụ ổn định kết hợp version/quy tắc ghi để không nhân đôi dữ liệu.
5. **Chỉ dùng một consumer chủ động cho một cursor**, hoặc thiết kế partition/điều phối rõ ràng. Nhiều instance tự ghi chồng checkpoint có thể bỏ qua sự kiện.
6. **Đo backlog/lag:** theo dõi thời gian từ commit đến xử lý, thời điểm checkpoint cuối, số lỗi và độ dài vùng log còn giữ được.

Nếu sink và cursor nằm ở **cùng database downstream**, có thể lưu cả tác dụng của event và checkpoint trong một transaction downstream. Nếu nằm ở hai hệ thống khác nhau, không tự giả định có giao dịch phân tán; dùng cơ chế idempotent, checkpoint có thể phát lại và xử lý lỗi.

### 7.2. Pseudocode phía Java Driver

Đoạn sau minh họa ý tưởng, **không phải một ứng dụng chạy độc lập**. `checkpointStore` và `sink` là các thành phần do dự án triển khai; mỗi giao dịch đọc CDC phải dùng database đã bật CDC và session có quyền:

~~~java
String cursor = checkpointStore.load(databaseName, consumerName);
if (cursor == null) {
    // Chọn chính sách bootstrap có chủ đích:
    // current() -> chỉ theo dõi event mới;
    // earliest() -> các event còn trong log.
    cursor = readCurrentCdcId(driver, databaseName);
    checkpointStore.save(databaseName, consumerName, cursor);
}

for (CdcChange change : readChanges(driver, databaseName, cursor)) {
    // Xử lý có khả năng lũy đẳng. Crash có thể khiến event này đọc lại.
    sink.applyIdempotently(change.id(), change.event());

    // Chỉ xác nhận cursor SAU khi sink đã ghi thành công, bền vững.
    checkpointStore.save(databaseName, consumerName, change.id());
    cursor = change.id();
}
~~~

Phần `readChanges` có thể dùng `Session.executeRead` cùng Cypher:

~~~cypher
CALL db.cdc.query($cursor, [])
YIELD id, txId, seq, metadata, event
RETURN id, txId, seq, metadata, event;
~~~

Không lưu `elementId` như định danh nghiệp vụ vĩnh viễn. Với cập nhật/xóa, consumer cần khóa phù hợp từ dữ liệu nguồn. **Node key/relationship key constraints** (nếu edition/phiên bản hỗ trợ) cung cấp thông tin key trong CDC; cũng có thể dùng thuộc tính ID nghiệp vụ có hợp đồng ổn định và kiểm tra dữ liệu theo yêu cầu của sink.

### 7.3. Mô hình tích hợp với Kafka

Nếu cần đưa sự kiện ra Apache Kafka, có thể dùng **Neo4j Connector for Apache Kafka** với **source mode** khai thác CDC trên phiên bản/edition phù hợp. Kafka Connect sẽ giúp vận hành luồng publish và lưu offset theo khả năng của connector, nhưng vẫn cần cấu hình topic, quyền, serialization, retention và chính sách lỗi. **Source connector** đọc thay đổi từ Neo4j rồi đẩy ra Kafka; **sink connector** đi chiều ngược lại (Kafka → Neo4j). Hai hướng không được đánh đồng.

Khi downstream consume Kafka, **offset Kafka** và **CDC change identifier** là hai khái niệm khác nhau; thiết kế recovery phải dựa vào connector và các checkpoint thực tế. Tham khảo [Kafka source CDC quickstart](https://neo4j.com/docs/kafka/current/source/quickstart-cdc/).

## 8. Transaction log retention và các tình huống mất liên tục

CDC dựa vào transaction log. Nó **không phải lịch sử vô hạn**; log có thể được rotate/prune theo cấu hình. Nếu consumer ngừng lâu hơn thời gian giữ log, cursor có thể trỏ tới phần đã bị xóa.

| Tình huống | Rủi ro | Cách ứng phó |
| --- | --- | --- |
| Consumer ngừng lâu, log bị prune | `db.cdc.query` không còn đọc được từ cursor cũ | Theo dõi lag, tăng retention phù hợp hoặc bootstrap lại |
| CDC đang `OFF` | Procedure báo CDC bị vô hiệu hóa | Kiểm tra edition, mode, cấu hình DB |
| Tắt rồi bật CDC | Identifier cũ không còn hợp lệ | Khởi tạo chuỗi cursor mới, khôi phục đồng bộ nếu cần |
| Restore backup/snapshot, clone | Database đích không còn cùng nguồn identifier | Đánh giá quy trình khôi phục và ánh xạ/rebootstrap theo docs |
| Đổi từ `DIFF` sang `FULL` | Định dạng event thay đổi | Consumer hỗ trợ cả hai dạng, triển khai có kiểm soát |
| Sink trả lỗi rồi consumer restart | Event có thể được đọc lại | Idempotent upsert/delete; chỉ tiến cursor sau sink success |

Theo tài liệu lỗi CDC, những mã như `Neo.DatabaseError.ChangeDataCapture.Disabled`, `Neo.DatabaseError.ChangeDataCapture.ScanFailure` và `Neo.ClientError.ChangeDataCapture.InvalidIdentifier` có thể giúp phân biệt CDC tắt, thiếu entry trong transaction log và identifier không hợp lệ. Ứng dụng không nên chỉ retry vô hạn cùng cursor khi nguyên nhân là log đã bị prune. Nên báo cảnh báo, dừng tiến trình hoặc chạy lại quy trình bootstrap phù hợp.

### 8.1. Snapshot ban đầu + CDC mới

Muốn một hệ thống downstream có **toàn bộ dữ liệu hiện tại** và tiếp tục nhận thay đổi, phải thiết kế hai pha:

~~~text
Pha 1: Dựng snapshot/backfill toàn bộ graph hoặc tập dữ liệu liên quan.
Pha 2: Tiếp tục áp dụng các CDC event sau mốc nhất quán đã xác định.
~~~

Điểm khó là **khoảng giao thoa** giữa snapshot và CDC. Nếu xuất snapshot trước rồi mới lấy `db.cdc.current()`, các giao dịch phát sinh ở giữa có thể bị bỏ sót. Nếu lấy cursor trước rồi mới export snapshot, sẽ có event bị lặp/giao thoa và cần giải quyết bằng version hoặc upsert lũy đẳng. Trong cả hai trường hợp, cần có **mốc cắt nhất quán/chiến lược đối soát** theo kiến trúc triển khai; không chỉ ghép hai script với nhau rồi mặc định không mất dữ liệu.

### 8.2. Dung lượng log và độ trễ

Bật CDC làm transaction log chứa nhiều thông tin hơn. Điều này có thể tác động disk space, I/O, throughput ghi và tốc độ prune. Chọn retention bằng cách xét **thời gian downtime tối đa + thời gian backlog + biên an toàn**, sau đó đo trên dữ liệu thật. Theo [hướng dẫn self-managed](https://neo4j.com/docs/cdc/current/get-started/self-managed/), chi phí log có thể tăng đáng kể khi bật `DIFF` hoặc `FULL`; tỷ lệ thực tế phụ thuộc kiểu transaction và dữ liệu.

## 9. Bảo mật và giới hạn quyền

CDC có thể trả **thay đổi của toàn database**, không tự lọc mọi event theo quyền xem từng node hoặc property của người dùng thông thường. Vì vậy quyền đọc CDC cần được cấp hết sức thận trọng:

- `db.cdc.query` yêu cầu **quyền quản trị tương ứng**, hoặc tổ hợp quyền **execute procedure** và **execute boosted procedure** cho role đã được cho phép; ngoài ra user phải có quyền truy cập database.
- `db.cdc.current` và `db.cdc.earliest` thường chỉ cần quyền truy cập database và execute procedure thông thường.
- Chỉ cấp quyền cho service account chuyên dụng; kiểm soát thông tin cá nhân, secret và dữ liệu nhạy cảm có thể nằm trong event.
- Tách rõ quyền **bật/tắt CDC** (DDL quản trị) với quyền **đọc event** trong ứng dụng.
- Nếu phân phối tiếp qua Kafka hoặc analytics, kiểm soát truy cập cả broker/topic và hệ thống đích; tránh in nguyên event vào log ứng dụng không được bảo vệ.

Tham khảo [CDC self-managed: Security](https://neo4j.com/docs/cdc/current/get-started/self-managed/). Cú pháp `GRANT` và điều kiện hỗ trợ phụ thuộc edition/quyền hiện có; ví dụ quyền từ tài liệu dành cho quản trị viên, không phải thao tác mọi developer tự chạy.

## 10. Bài thực hành kiểm tra tương thích và đọc event

### Bối cảnh

Bạn nhận một môi trường Neo4j chưa biết edition và được yêu cầu đưa thay đổi `Customer` ra một hệ thống analytics. Hãy làm theo quy trình kiểm tra không phá dữ liệu sau:

1. **Xác nhận version/edition:** chạy `CALL dbms.components()` nếu có quyền hoặc xem thông tin quản trị; ghi rõ phiên bản.
2. **Xác nhận CDC có được hỗ trợ:** đối chiếu ma trận Enterprise/Aura, version và namespace procedure.
3. **Xác nhận trạng thái CDC:** xem `SHOW DATABASES YIELD name, options` trên self-managed hoặc **Edit CDC Mode** trên Aura.
4. **Với môi trường được cấp phép và ủy quyền**, bật `DIFF` hoặc `FULL` cho database thực hành.
5. **Lấy current ID** bằng `db.cdc.current()`; sao chép nguyên chuỗi `id`.
6. **Thay đổi dữ liệu trong transaction khác**, dùng ID test riêng và thao tác update có thay đổi thật.
7. **Đọc event sau ID** bằng `db.cdc.query($fromId, [])`, xác nhận loại entity, operation, `state` và metadata.
8. **Lặp lại thử nghiệm retry:** xử lý event thành công nhưng cố ý chưa lưu checkpoint; sau khi đọc lại, dữ liệu downstream không được trùng.
9. **Kiểm tra biên vận hành:** ghi lại log retention, quyền dịch vụ và cách báo cảnh báo khi consumer tụt quá xa.

Ví dụ ghi dữ liệu để thử, chỉ sử dụng trên môi trường bài tập:

~~~cypher
MERGE (c:CdcPractice {practiceId: 'CDC-001'})
SET c.value = 'FIRST';

MATCH (c:CdcPractice {practiceId: 'CDC-001'})
SET c.value = 'SECOND';
~~~

Nếu hai câu lệnh được gửi trong cùng transaction hoặc client gộp chúng, event có thể không giống kỳ vọng “một create + một update” theo từng câu. Để thấy các thay đổi phân tách, chạy các **transaction đã commit riêng**.

### Câu hỏi kiểm tra hiểu biết

**Câu 1.** Server Neo4j 5.25 Community có bật được CDC chính thức chỉ bằng `ALTER DATABASE` không?

**Trả lời:** Không. Phiên bản đủ mới không thay đổi giới hạn edition; CDC chính thức trong tài liệu này là tính năng Enterprise/các gói Aura được hỗ trợ.

**Câu 2.** Vì sao ứng dụng viết cho Neo4j 5.15 có thể không tương thích khi dùng nguyên procedure `cdc.query` ở bản mới?

**Trả lời:** Namespace đổi từ `cdc.*` sang `db.cdc.*` từ 5.17. Cần kiểm tra tên và chữ ký procedure theo version.

**Câu 3.** Với một consumer chỉ cần xử lý thay đổi từ bây giờ, chọn `current` hay `earliest`?

**Trả lời:** Thường chọn `db.cdc.current()` và lưu cursor trước khi bắt đầu nhận thay đổi; `earliest` phục vụ đọc từ đầu vùng log đang được giữ, không mặc nhiên là từ đầu lịch sử database.

**Câu 4.** Tại sao cursor phải được lưu sau khi sink xác nhận?

**Trả lời:** Tiến cursor trước có thể bỏ mất event nếu ghi sink lỗi. Lưu sau có thể dẫn tới xử lý lại khi crash, nên sink phải hỗ trợ idempotency.

**Câu 5.** `FULL` có đồng nghĩa mỗi event có ý nghĩa nghiệp vụ như `OrderPaid` không?

**Trả lời:** Không. `FULL` là mức thông tin trạng thái entity trước/sau; ý nghĩa nghiệp vụ phải được suy luận từ mô hình, hợp đồng sự kiện hoặc phát ra từ ứng dụng.

**Câu 6.** Sau khi restore database, có thể sử dụng trực tiếp mọi change ID cũ không?

**Trả lời:** Không được giả định. Identifier gắn với database/vòng đời transaction log; phải áp dụng quy trình phục hồi được tài liệu Neo4j hỗ trợ.

## 11. Checklist quyết định trước khi triển khai

- [ ] Xác nhận **version, edition/gói Aura** và tài liệu CDC khớp bản thực tế.
- [ ] Kiểm tra tên procedure: `cdc.*` ở 5.13–5.16 hay `db.cdc.*` từ 5.17.
- [ ] Bật CDC trên **đúng database** với `DIFF` hoặc `FULL`, kiểm tra mode sau thao tác.
- [ ] Chọn chế độ event và xây consumer xử lý format `before/after` tương ứng.
- [ ] Cấp quyền CDC tối thiểu, bảo vệ event chứa dữ liệu nhạy cảm.
- [ ] Thiết kế snapshot/bootstrap và mốc chuyển sang CDC có đối soát.
- [ ] Lưu cursor bền vững, xử lý **exclusive ID**, retry và idempotency trong sink.
- [ ] Thiết lập log retention, cảnh báo lag và phương án khôi phục khi log đã prune.
- [ ] Thử tắt/bật, restore/clone/pause, thay mode và nâng cấp version trên môi trường thử nghiệm.
- [ ] Đo chi phí transaction log/I/O, ảnh hưởng ghi, throughput và độ trễ consumer.

## Tài liệu tham khảo chính thức

- [Neo4j Change Data Capture — Introduction](https://neo4j.com/docs/cdc/current/)
- [Neo4j CDC — Changelog và mốc phiên bản](https://neo4j.com/docs/cdc/current/changelog/)
- [CDC on Neo4j DBMS — Cấu hình tự quản](https://neo4j.com/docs/cdc/current/get-started/self-managed/)
- [CDC on Neo4j Aura — Gói dịch vụ và bật mode](https://neo4j.com/docs/cdc/current/get-started/aura/)
- [Use CDC to query changes — Procedures](https://neo4j.com/docs/cdc/current/procedures/)
- [Format of change events](https://neo4j.com/docs/cdc/current/procedures/output-schema/)
- [CDC troubleshooting](https://neo4j.com/docs/cdc/current/troubleshooting/)
- [Neo4j Connector for Kafka — CDC source quickstart](https://neo4j.com/docs/kafka/current/source/quickstart-cdc/)

**Kết luận:** Neo4j CDC là cơ chế theo dõi các thay đổi node/relationship đã commit dựa trên transaction log được làm giàu. Thiết kế tích hợp chỉ đúng khi **version và edition/gói dịch vụ hỗ trợ**, CDC được bật trên đúng database, consumer có quyền phù hợp và vòng đời cursor được quản lý chặt chẽ. Muốn đồng bộ đáng tin cậy, hãy kết hợp CDC với **checkpoint bền vững, xử lý lũy đẳng, log retention, bootstrap dữ liệu ban đầu và kế hoạch phục hồi**.
