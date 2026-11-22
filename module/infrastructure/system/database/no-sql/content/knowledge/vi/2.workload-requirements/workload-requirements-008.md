# Vòng đời dữ liệu, tăng trưởng, lưu trữ dài hạn và yêu cầu xóa

Thiết kế cơ sở dữ liệu NoSQL không kết thúc khi hệ thống lưu thành công một document hoặc đọc nhanh một bản ghi. Dữ liệu còn tiếp tục được cập nhật, nhân bản, chuyển sang vùng lưu trữ khác, hết giá trị sử dụng và cuối cùng phải được xóa theo chính sách hoặc theo một yêu cầu hợp lệ. Mỗi giai đoạn thay đổi **lượng dữ liệu**, **kiểu truy cập**, **chi phí vận hành**, **mức độ nhất quán** và **rủi ro nếu dữ liệu còn tồn tại ngoài dự kiến**.

Bài học này đi từ yêu cầu nghiệp vụ đến các quyết định về vòng đời dữ liệu trong hệ NoSQL: phân loại dữ liệu; dự báo tăng trưởng và phân bố tải; xác định thời gian lưu; chọn cách lưu trữ nóng, lạnh và dài hạn; thiết kế cơ chế hết hạn; thực hiện yêu cầu xóa; rồi kiểm chứng rằng dữ liệu thật sự không còn được phục vụ ở các nơi cần xóa.

Các ví dụ dùng MongoDB để minh họa document và TTL index, đồng thời đối chiếu một số đặc điểm của Redis, DynamoDB và Cassandra. Không có một cơ chế TTL hay xóa duy nhất áp dụng giống nhau cho mọi hệ NoSQL.

## 1. Hiểu vòng đời dữ liệu như một yêu cầu nghiệp vụ

**Vòng đời dữ liệu** là chuỗi trạng thái của một nhóm dữ liệu từ lúc hình thành đến lúc không còn được phép hoặc không còn cần lưu giữ. Một vòng đời điển hình:

~~~mermaid
flowchart TD
    A["Tạo dữ liệu"] --> B["Đang sử dụng: đọc, ghi, cập nhật"]
    B --> C["Ít được truy cập: lưu trữ lạnh hoặc lưu trữ dài hạn"]
    C --> D{"Đã hết thời hạn lưu?"}
    D -->|Chưa| C
    D -->|Rồi| E{"Có nghĩa vụ bảo lưu hợp lệ?"}
    E -->|Có| F["Giữ trong phạm vi được phép, hạn chế truy cập"]
    F --> G["Đánh giá lại khi hết nghĩa vụ"]
    G --> E
    E -->|Không| H["Xóa khỏi các bản lưu cần xử lý"]
    H --> I["Xác nhận kết quả và xử lý bản sao, backup"]
    B --> J["Yêu cầu xóa hợp lệ từ người dùng"]
    J --> E
~~~

Đây là mô hình khái niệm, không khẳng định mọi loại dữ liệu đều phải qua vùng lạnh. Session có thể được xóa ngay khi hết hạn; hóa đơn có thể cần lưu lâu; hồ sơ tài khoản có thể bị yêu cầu xóa khi vẫn đang hoạt động.

Cần phân biệt các thời điểm thường bị nhập làm một:

| Mốc | Câu hỏi | Ví dụ |
|---|---|---|
| **createdAt / occurredAt** | Dữ liệu được tạo hoặc sự kiện thực sự xảy ra khi nào? | Một click xảy ra lúc 09:00 UTC |
| **updatedAt** | Bản ghi được thay đổi lần cuối khi nào? | Trạng thái đơn đổi lúc 09:05 |
| **hotUntil** | Đến khi nào cần truy vấn trực tuyến với độ trễ thấp? | Nhật ký hoạt động cần tìm kiếm nhanh trong 30 ngày |
| **retentionUntil / deleteAfter** | Sau thời điểm nào không còn lý do được giữ dữ liệu theo chính sách? | Dữ liệu sự kiện phải xóa khi đủ 180 ngày tuổi |
| **deletedAt** | Hệ thống ghi nhận thao tác xóa đã hoàn tất ở phạm vi nào? | Bản ghi đã được xóa khỏi kho chính lúc 11:00 |
| **backupExpiry** | Các bản backup chứa bản ghi còn tồn tại đến bao giờ? | Backup theo chính sách vòng đời riêng |

**Hết hạn sử dụng, bị ẩn khỏi giao diện và bị xóa vật lý là ba trạng thái khác nhau.** Một bản ghi không còn xuất hiện trong API vẫn có thể nằm trong index, backup, log, cache hoặc kho phân tích. Ngược lại, có dữ liệu đã hết thời hạn nhưng chưa được tác vụ nền dọn dẹp.

Vì vậy, phát biểu “giữ dữ liệu 180 ngày” chưa đủ. Cần làm rõ **180 ngày kể từ mốc nào**, dữ liệu còn được truy cập ở giai đoạn nào, có ngoại lệ nào và khi hết hạn hệ thống phải xóa đến mức nào.

## 2. Phân loại dữ liệu trước khi tính dung lượng hoặc bật TTL

Giả sử một nền tảng thương mại có lịch sử đặt hàng, phiên đăng nhập, sự kiện hành vi và báo cáo doanh thu. Những dữ liệu này có tuổi thọ rất khác nhau.

| Nhóm dữ liệu | Mục đích chính | Mẫu truy cập | Ví dụ chính sách giả định |
|---|---|---|---|
| **Session đăng nhập** | Duy trì phiên còn hợp lệ | Tra theo token/session id, cập nhật lần hoạt động gần nhất | Hết hạn sau 30 phút không hoạt động, tối đa 24 giờ từ khi tạo |
| **Sự kiện hoạt động** | Phân tích hành vi và điều tra lỗi | Lọc theo tenant, thời gian, loại sự kiện | 30 ngày ở kho nóng; lưu lạnh tới tổng cộng 180 ngày kể từ sự kiện, sau đó xóa |
| **Đơn hàng và dòng hàng** | Xử lý giao dịch, tra cứu, giải quyết tranh chấp | Tra theo khách hàng, order id, thời gian | 90 ngày truy cập nhanh; tiếp tục lưu theo chính sách lưu chứng từ được phê duyệt |
| **Hồ sơ tài khoản** | Quản lý tài khoản, liên hệ | Tra theo user id/email | Còn cần trong thời gian hoạt động; xử lý riêng khi có yêu cầu xóa |
| **Số liệu tổng hợp** | Dashboard và lập kế hoạch | Truy vấn theo ngày, sản phẩm, khu vực | Lưu tùy mục đích và khả năng nhận diện cá nhân |
| **Backup** | Khôi phục sau lỗi, sự cố | Đọc hiếm khi cần restore | Chính sách lưu vòng đời riêng, ví dụ 35 ngày |

**Các con số trong bảng chỉ là giả định minh họa**, không phải thời hạn pháp lý hay khuyến nghị mặc định cho mọi ứng dụng. Thời hạn thực tế phải dựa vào mục đích xử lý, hợp đồng, quy định áp dụng, nghĩa vụ bảo lưu và chính sách của tổ chức.

Phân loại nên trả lời tối thiểu:

1. **Ai sở hữu và ai được truy cập?** Dữ liệu có chứa thông tin cá nhân, bí mật nghiệp vụ hoặc thông tin nhạy cảm không?
2. **Ai tạo, ai cập nhật?** Nguồn chính nằm ở dịch vụ nào? Có bản sao/đường dẫn sự kiện nào?
3. **Truy vấn nào cần chạy nhanh?** Theo khóa đơn, theo khách hàng, theo thời gian hay quét tổng hợp?
4. **Dữ liệu tăng theo cách nào?** Theo số người dùng, số sự kiện/giây, số thiết bị, số tenant hay kích thước từng document?
5. **Bao lâu còn cần thiết?** Có khoảng nóng, lạnh, thời hạn cuối và ngoại lệ bảo lưu không?
6. **Xóa nghĩa là gì?** Xóa bản ghi chính, dữ liệu dẫn xuất, bản sao, cache, tệp xuất và backup theo quy trình nào?
7. **Làm sao chứng minh?** Tín hiệu nào cho thấy chuyển vùng, xóa và ngăn phục hồi trái ý muốn đã xảy ra?

Không nên bật TTL hàng loạt chỉ vì dữ liệu “trông giống log”. Một log kiểm toán có thời hạn lưu bắt buộc khác với một cache; một hóa đơn có thể cần lưu lâu hơn hồ sơ liên hệ của người mua.

## 3. Định nghĩa retention policy thành hợp đồng có thể thực thi

Một **retention policy** (chính sách lưu giữ) phải đủ cụ thể để dịch vụ và tác vụ nền áp dụng nhất quán:

~~~yaml
# Ví dụ mô tả chính sách, không phải cấu hình tự động của MongoDB
dataset: activity_events
timeBasis: occurredAt
hotRetentionDays: 30
totalRetentionDays: 180
archiveAfterDays: 30
archiveRequiredBeforeHotPurge: true
deletionMethod: purge
legalHold: supported
owner: analytics_platform
~~~

Hợp đồng trên nói rõ rằng sự kiện đã xảy ra quá 30 ngày sẽ được chuyển sang kho dài hạn; quá **180 ngày tính từ occurredAt** thì phải xóa ở các kho thuộc phạm vi chính sách, nếu không có ngoại lệ bảo lưu hợp lệ.

Những điểm cần quyết định thêm:

- **Mốc thời gian:** thời điểm sự kiện xảy ra hay thời điểm hệ thống tiếp nhận? Một sự kiện được gửi muộn 3 ngày có thể đã gần hết hạn nếu tính theo occurredAt.
- **Độ chính xác:** “xóa ngay đúng giây hết hạn” và “xóa trong một khoảng trễ vận hành được chấp nhận” là hai yêu cầu khác nhau.
- **Múi giờ:** lưu mốc kỹ thuật ở UTC; chỉ chuyển sang múi giờ nghiệp vụ khi cần quy tắc theo ngày địa phương.
- **Cập nhật retention:** thay đổi chính sách có áp dụng cho dữ liệu cũ không? Ai phê duyệt, ai triển khai backfill giá trị hết hạn?
- **Ngoại lệ:** nếu cần bảo lưu phục vụ tranh chấp hoặc yêu cầu hợp lệ, phạm vi và người được phép gỡ bảo lưu là ai?
- **Xóa theo chủ thể:** một yêu cầu xóa tài khoản có thể đến trước ngày hết retention; nó phải chạy qua quy trình riêng.

**Bảo lưu vì lý do hợp lệ (legal hold)** không đồng nghĩa với cho phép truy cập tùy ý. Dữ liệu đang bảo lưu cần được giới hạn truy cập, ghi nhận căn cứ và được đánh giá lại khi điều kiện bảo lưu chấm dứt. Cách xử lý cụ thể phụ thuộc quy định áp dụng và quyết định có thẩm quyền.

## 4. Tính tăng trưởng theo lượng ghi, kích thước và thời gian giữ

Dung lượng của NoSQL thay đổi cùng tốc độ phát sinh dữ liệu. Với dữ liệu sự kiện append-only có tốc độ tương đối ổn định, phép ước lượng cơ sở là:

\[
\text{Raw bytes/day}
= \text{events/second} \times \text{average bytes/event} \times 86{,}400
\]

\[
\text{Raw bytes retained}
\approx \text{Raw bytes/day} \times \text{retention days}
\]

Giả sử có **2.000 sự kiện/giây** và trung bình **900 byte/sự kiện** trước nén:

~~~text
2.000 event/s × 900 B/event  = 1.800.000 B/s
1.800.000 B/s × 86.400 s/day = 155.520.000.000 B/day
                             = 155,52 GB/ngày (đơn vị thập phân)

Giữ 7 ngày  ≈ 1,08864 TB dữ liệu thô
Giữ 30 ngày ≈ 4,6656  TB dữ liệu thô
~~~

Nếu giả định lưu **3 bản sao đầy đủ** của 30 ngày dữ liệu đó, riêng phần bản sao dữ liệu thô tương đương khoảng **13,9968 TB** trước khi tính index, metadata, log ghi, khoảng trống, backup, nén hoặc cách hệ quản trị thực sự bố trí bản sao. Đây chỉ là phép tính lập ngân sách ban đầu; hệ thống có thể có cơ chế nén, mã hóa phân tán hoặc cấu hình replication khác.

Một kế hoạch dung lượng thực tế cần thêm:

| Yếu tố | Vì sao phép tính “số bản ghi × kích thước” chưa đủ |
|---|---|
| **Index** | Thêm dung lượng lưu và chi phí cập nhật cho mỗi lần ghi |
| **Replication** | Tạo thêm bản sao nhằm đáp ứng độ sẵn sàng và cách đọc/ghi |
| **WAL/oplog/commit log** | Bổ sung lưu trữ và I/O phục vụ phục hồi, đồng bộ |
| **Nén và định dạng lưu** | Có thể giảm dung lượng vật lý; hiệu quả phụ thuộc dữ liệu |
| **Backup/snapshot** | Có vòng đời và nơi lưu riêng, có thể giữ nhiều phiên bản |
| **Headroom** | Cần dự phòng cho spike, di chuyển shard, compaction, restore |
| **Tombstone và phân mảnh** | Dữ liệu hết hạn/xóa logic có thể còn chiếm chỗ đến khi dọn nền |
| **Bản ghi tăng kích thước** | Update, arrays tăng dần hoặc thêm trường làm kích thước trung bình thay đổi |

Đừng chỉ đo **tổng byte**. Tăng trưởng còn diễn ra ở số partition, số index entries, lượng dữ liệu đọc mỗi truy vấn và số thao tác ghi mỗi giây.

### Tải trung bình không mô tả giờ cao điểm

2.000 sự kiện/giây là trung bình; nếu chiến dịch khuyến mãi tạo đỉnh gấp 8 lần, đường ghi phải đối mặt với **16.000 sự kiện/giây** trong đợt cao điểm. Trường hợp một tenant chiếm phần lớn traffic còn có thể làm một partition hoặc một shard quá nóng, dù tổng dung lượng cluster vẫn còn nhiều.

Cần xem riêng:

- **Throughput:** số lần ghi/đọc trong giây ở trung bình và phân vị cao.
- **Kích thước truy cập:** số byte thực sự truyền về, không chỉ số document.
- **Cardinality:** số khách hàng, thiết bị, tenant, khóa phân vùng.
- **Skew:** một ít khóa nhận phần lớn traffic hay dữ liệu hay không.
- **Độ tăng trưởng:** dữ liệu tăng tuyến tính, tăng theo người dùng hay theo sự kiện tương tác giữa nhiều thực thể.
- **Truy vấn theo thời gian:** có thường đọc khoảng 24 giờ gần nhất hay quét nhiều năm?

Các phép ước tính nên được hiệu chỉnh bằng đo đạc sau triển khai: kích thước trung bình thực tế, số byte cho từng loại document, tốc độ thêm/xóa, p95/p99 latency, kích thước index, và tốc độ tăng của từng tenant.

## 5. Thiết kế mô hình NoSQL theo tuổi dữ liệu và đường truy cập

Với sự kiện hoạt động, mô hình document có thể là:

~~~javascript
{
  _id: "evt-1001",
  tenantId: "shop-a",
  userId: "user-71",
  eventType: "VIEW_PRODUCT",
  occurredAt: ISODate("2026-11-14T09:00:00Z"),
  ingestedAt: ISODate("2026-11-14T09:00:02Z"),
  payload: { productId: "p42" }
}
~~~

Hai trường thời gian có ý nghĩa khác nhau: **occurredAt** phù hợp để phân tích theo ngày xảy ra sự kiện; **ingestedAt** giúp quan sát độ trễ tiếp nhận và sự kiện gửi muộn. Nếu chính sách lưu dựa trên thời điểm xảy ra, việc chỉ lọc theo thời điểm nhập có thể giữ dữ liệu sai thời hạn.

Giả sử truy vấn thường gặp là “xem 100 sự kiện mới nhất của một tenant trong một khoảng thời gian”, một index ứng viên cho MongoDB:

~~~javascript
db.activityEvents.createIndex({
  tenantId: 1,
  occurredAt: -1,
  _id: -1
});

db.activityEvents
  .find({
    tenantId: "shop-a",
    occurredAt: {
      $gte: ISODate("2026-11-13T00:00:00Z"),
      $lt: ISODate("2026-11-15T00:00:00Z")
    }
  })
  .sort({ occurredAt: -1, _id: -1 })
  .limit(100);
~~~

Index cần xuất phát từ truy vấn thực tế. Index trên thời gian đơn lẻ có thể tiện cho dọn dữ liệu, nhưng không nhất thiết là index phù hợp nhất cho truy vấn được lọc theo tenant. Mỗi index bổ sung làm ghi tốn tài nguyên hơn.

Với dữ liệu phát sinh liên tục, nên đặt thêm câu hỏi:

**Có cần chia theo thời gian?** Nếu truy vấn chủ yếu theo ngày và dữ liệu cũ không cần ghi nữa, phân vùng/bucket theo thời gian có thể hỗ trợ lưu trữ, di chuyển và dọn dữ liệu. Tuy nhiên, một bucket “tất cả sự kiện của một ngày” có thể rất lớn. Cần xem thêm tenant, tốc độ tăng và khả năng phân bố tải.

**Document có tăng vô hạn không?** Tránh gom toàn bộ sự kiện của một user vào một array ngày càng lớn; document lớn gây khó cập nhật, khó phân trang và có thể chạm giới hạn kích thước của database.

**Có cần truy vấn lịch sử thường xuyên không?** Nếu người dùng cần mở lịch sử nhiều năm trong vài trăm mili giây, kho lạnh có độ trễ phục hồi nhiều giờ sẽ không đáp ứng hợp đồng ấy. Quyết định hot/cold là quyết định về trải nghiệm sản phẩm, không chỉ chi phí ổ đĩa.

**Dữ liệu có thể được xóa theo user không?** Nếu sự kiện chứa **userId**, kiến trúc cần một cách định vị các bản ghi của một người ở kho nóng, kho lạnh và các bản sao dẫn xuất. Chia theo thời gian giúp dọn từng đợt tuổi dữ liệu nhưng chưa đủ để thực hiện xóa riêng một người.

## 6. Ba nhóm giải pháp lưu trữ theo độ nóng

| Vùng | Đặc điểm và mục tiêu | Thường phù hợp với |
|---|---|---|
| **Hot / online** | Truy vấn thường xuyên, độ trễ thấp, có index phục vụ sản phẩm | Phiên còn hiệu lực, đơn gần đây, sự kiện 30 ngày gần nhất |
| **Warm** | Ít truy cập hơn nhưng vẫn cho phép đọc tương đối thuận tiện | Lịch sử cần tra cứu không thường xuyên |
| **Cold / archive** | Tối ưu chi phí lưu dài hạn, đọc chậm hơn hoặc cần quy trình phục hồi | Sự kiện cũ, chứng từ lưu giữ, bản xuất phân tích lịch sử |

Một hệ NoSQL có thể cung cấp nhiều lớp lưu trữ trong cùng nền tảng, hoặc dùng database cho vùng nóng và object storage cho vùng lạnh. Không bắt buộc mọi kiến trúc phải có đủ ba lớp.

Trong ví dụ sự kiện, quy trình chuyển kho cần có trình tự an toàn:

~~~mermaid
flowchart TD
    A["Sự kiện trong kho nóng"] --> B["Đủ 30 ngày: chọn batch theo thời gian"]
    B --> C["Xuất dữ liệu sang archive"]
    C --> D["Kiểm chứng manifest, số bản ghi, checksum"]
    D -->|Lỗi| E["Giữ dữ liệu nguồn, retry an toàn"]
    E --> C
    D -->|Hợp lệ| F["Ghi nhận checkpoint archive"]
    F --> G["Xóa bản nguồn khỏi kho nóng"]
    G --> H["Archive còn giữ đến ngày thứ 180"]
    H --> I["Hết hạn và không có hold: purge archive"]
~~~

**Không được xóa bản nóng trước khi chắc chắn bản lưu dài hạn đã được ghi và có thể khôi phục/đọc theo hợp đồng.** Việc “file đã được upload” chỉ là một phần của kiểm chứng; cần kiểm tra số bản ghi, tính toàn vẹn, định dạng, metadata, quyền đọc và cơ chế truy vấn hoặc restore.

Khi xuất theo batch, nên có:

- **Định danh batch và khoảng thời gian:** xác định chính xác dữ liệu nào được xử lý, tránh bỏ sót ranh giới ngày hoặc xử lý trùng không kiểm soát.
- **Checkpoint bền vững:** nếu tác vụ chết giữa chừng, lần chạy sau có thể tiếp tục an toàn.
- **Tính idempotent:** xuất lại cùng batch không tạo thêm bản dữ liệu khó kiểm soát hoặc làm sai tổng hợp.
- **Kiểm chứng manifest:** số lượng, checksum, schema version, mốc thời gian và nơi lưu đã ghi.
- **Quy tắc dữ liệu đến muộn:** sự kiện đến sau khi đã đóng batch phải được đưa vào đường backfill hoặc batch bổ sung.
- **Quy tắc xóa bản nóng:** chỉ xóa phần đã được xác minh, đồng thời tính đến thay đổi phát sinh trong lúc xuất.
- **Quan sát chi phí và thời gian phục hồi:** lưu rẻ không tự đảm bảo có thể tìm kiếm nhanh.

Với kho object, cần xác định chính sách lifecycle cho từng lớp/phiên bản, quyền truy cập, mã hóa, khả năng truy vấn, giới hạn thời gian phục hồi và xử lý các bản copy do job phân tích tạo ra.

## 7. TTL: công cụ hết hạn tự động, không phải toàn bộ chính sách xóa

**Time To Live (TTL)** giúp khai báo khi nào dữ liệu đủ điều kiện hết hạn. Tùy database, TTL có thể được áp dụng ở key, item, document, column hay hàng dữ liệu; thực tế có thể được dọn theo lịch nền.

Một session thường phù hợp với TTL vì không cần archive. Ta mô hình hóa session với hạn tuyệt đối và hạn do không hoạt động:

~~~javascript
{
  _id: "session-8f3",
  userId: "user-71",
  createdAt: ISODate("2026-11-14T09:00:00Z"),
  lastActivityAt: ISODate("2026-11-14T09:10:00Z"),
  absoluteExpiresAt: ISODate("2026-11-15T09:00:00Z"),
  expiresAt: ISODate("2026-11-14T09:40:00Z")
}
~~~

Ở ví dụ này, **expiresAt = min(lastActivityAt + 30 phút, absoluteExpiresAt)**. Khi có hoạt động hợp lệ, ứng dụng có thể cập nhật **lastActivityAt** và tính lại **expiresAt**, không được đẩy quá mốc tuyệt đối 24 giờ.

Với MongoDB, một TTL index minh họa:

~~~javascript
db.sessions.createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0 }
);
~~~

Ở đây **expiresAt** là trường ngày; TTL index cho phép MongoDB xem các document đã qua thời điểm đó là đối tượng dọn dẹp. Cơ chế TTL chạy bất đồng bộ, nên **không bảo đảm document biến mất đúng tại giây expiresAt**. Vì vậy, ứng dụng phải từ chối một phiên hết hạn ngay khi đọc hoặc xác thực, kể cả khi document chưa được TTL dọn:

~~~javascript
const now = new Date();

db.sessions.findOne({
  _id: "session-8f3",
  expiresAt: { $gt: now }
});
~~~

Ví dụ chỉ minh họa điều kiện thời gian; triển khai xác thực thực tế còn phải kiểm tra token, quyền, trạng thái tài khoản và thao tác thu hồi phiên. Truy vấn cần được thiết kế để không tạo race condition ngoài hợp đồng xác thực.

**Không áp dụng TTL xóa bản nóng sau 30 ngày cho sự kiện còn phải lưu archive tới ngày thứ 180 nếu chưa có bước archive an toàn.** TTL tự động không biết việc xuất dữ liệu sang kho khác đã thành công hay chưa. Khi bài toán yêu cầu “archive rồi mới xóa bản nóng”, cần một workflow có kiểm chứng và checkpoint, hoặc kiến trúc đảm bảo điều kiện tương đương.

### TTL ở các NoSQL khác nhau

| Hệ thống | Cơ chế minh họa | Giới hạn cần hiểu |
|---|---|---|
| **MongoDB** | TTL index trên trường thời gian của document | Dọn nền; không bảo đảm xóa đúng thời điểm; vẫn cần kiểm tra hết hạn ở lớp đọc |
| **Redis** | Thời gian hết hạn gắn với key bằng lệnh như **EXPIRE** | Hữu ích cho cache/session; không mặc nhiên xử lý các bản sao dữ liệu ở database nguồn hay backup |
| **DynamoDB** | TTL attribute lưu timestamp Unix theo **giây**, item được dọn bất đồng bộ | Item đã hết hạn có thể vẫn tồn tại và được đọc một thời gian; ứng dụng cần tự lọc nếu bắt buộc không phục vụ sau hạn |
| **Cassandra** | TTL có thể gắn với dữ liệu khi ghi, sử dụng cơ chế tombstone/compaction | Hết hạn logic không đồng nghĩa không còn byte vật lý ngay; nhiều tombstone có thể ảnh hưởng hiệu năng đọc |

Điểm chung: TTL giúp thực thi một phần chính sách lưu giữ, nhưng **không thay thế thiết kế quyền truy cập, yêu cầu xóa theo chủ thể, quản lý backup và quan sát hoàn tất**.

## 8. Soft delete, hard delete, tombstone và dữ liệu vật lý

Một thao tác “xóa” có thể mang những ngữ nghĩa khác nhau:

| Hình thức | Ý nghĩa | Rủi ro nếu hiểu nhầm |
|---|---|---|
| **Soft delete** | Đánh dấu bản ghi đã xóa, chặn hiển thị theo truy vấn | Dữ liệu nhạy cảm vẫn có trong kho nếu chưa được purge |
| **Hard delete ở lớp API/database** | Yêu cầu database loại bỏ bản ghi khỏi tập kết quả hiện hành | Bản sao, snapshot, log hoặc dung lượng vật lý có thể tồn tại thêm |
| **Tombstone** | Dấu mốc xóa để hệ phân tán hợp nhất/đồng bộ trạng thái | Dấu xóa và dữ liệu cũ có thể còn tồn tại đến khi dọn nội bộ |
| **Purge dữ liệu nguồn và dẫn xuất** | Xóa qua toàn bộ phạm vi lưu giữ đã liệt kê | Thiếu một kho dẫn xuất có thể để dữ liệu tiếp tục phục vụ |
| **Cryptographic erasure** | Làm mất khả năng giải mã bằng cách hủy khóa phù hợp | Chỉ có ý nghĩa nếu phạm vi khóa được cô lập và mọi bản sao đều thực sự phụ thuộc vào khóa đó |

Ví dụ MongoDB soft delete:

~~~javascript
db.userProfiles.updateOne(
  { _id: "user-71", deletedAt: { $exists: false } },
  { $set: { deletedAt: new Date(), status: "DELETION_PENDING" } }
);
~~~

Lệnh này **không phải xóa dữ liệu cá nhân**; nó chỉ đánh dấu trạng thái. Nếu API còn một truy vấn quên điều kiện trạng thái, hồ sơ có thể vẫn bị đọc. Khi mục tiêu là xóa dữ liệu cá nhân, cần cơ chế xử lý dữ liệu nguồn và mọi dữ liệu dẫn xuất thuộc phạm vi, chứ không được coi một cờ **deletedAt** là bằng chứng hoàn thành.

Trong hệ phân tán, cần phân biệt **xóa hiển thị** với **thu hồi dung lượng**. Các database có thể giải phóng file vật lý sau compaction, garbage collection, checkpoint hoặc tác vụ bảo trì. Số byte trên ổ đĩa không giảm ngay không nhất thiết chứng minh thao tác xóa logic thất bại; nhưng cũng không được lấy một phản hồi xóa thành công từ API để khẳng định mọi bản sao đã bị loại bỏ.

## 9. Yêu cầu xóa của người dùng là một workflow xuyên hệ thống

Giả sử người dùng yêu cầu xóa tài khoản **user-71**. Hồ sơ của họ có thể được dùng ở nhiều nơi:

~~~text
                       user-71
                          |
          +---------------+----------------+
          |               |                |
          v               v                v
    userProfiles       sessions       activityEvents
          |               |                |
          v               v                v
     search index      Redis cache     analytics warehouse
          |                                |
          +-----------+--------------------+
                      |
                      v
                 archive/exports
                      |
                      v
                backups/snapshots
~~~

Việc xóa document ở **userProfiles** không tự động xóa session, chỉ mục tìm kiếm, dữ liệu trong kho phân tích, object archive hoặc file xuất đã phát sinh. Trước khi thiết kế thao tác xóa, nhóm phát triển phải biết **dữ liệu đã đi những đâu**.

Một workflow có thể gồm:

1. **Nhận và xác thực yêu cầu.** Xác minh người yêu cầu, quyền và phạm vi dữ liệu; ghi nhận mã yêu cầu để tránh xử lý trùng.
2. **Đánh giá chính sách.** Tách dữ liệu phải xóa, dữ liệu phải tiếp tục lưu vì căn cứ hợp lệ và dữ liệu có thể chuyển thành thống kê đã ẩn danh thực sự. Việc giữ lại phải được phê duyệt theo chính sách phù hợp.
3. **Chặn phát sinh dữ liệu mới.** Thu hồi session, vô hiệu hóa tài khoản hoặc đặt trạng thái xử lý. Các dịch vụ cần kiểm tra trạng thái này trước khi tái tạo hồ sơ hoặc gửi thêm sự kiện có định danh.
4. **Xóa hoặc vô hiệu hóa dữ liệu trực tuyến.** Xử lý hồ sơ, session, các bộ dữ liệu dùng trực tiếp cho API và index phục vụ tìm kiếm.
5. **Lan truyền tới các kho dẫn xuất.** Xử lý cache, analytics, archive, event-derived views, dữ liệu đồng bộ tới hệ thống liên quan và bản xuất nằm trong phạm vi quản lý.
6. **Xử lý backup và restore.** Ghi nhận phạm vi backup không thể sửa ngay và cơ chế không để dữ liệu đã xóa sống lại khi khôi phục.
7. **Đối chiếu và kết thúc.** Chỉ đánh dấu hoàn tất khi từng nơi bắt buộc đã xác nhận; ngoại lệ hoặc việc còn chờ phải được thể hiện rõ.

Trong hệ có nhiều dịch vụ, workflow này thường bất đồng bộ và cần **idempotency**: nếu một bước bị retry, yêu cầu không được tạo lại dữ liệu, gây lỗi dây chuyền hoặc âm thầm bỏ qua một kho chưa xử lý.

### Phân loại dữ liệu trước khi xóa

Không phải mọi thông tin liên quan một tài khoản đều có cùng quy tắc:

| Loại | Câu hỏi ra quyết định | Hướng xử lý minh họa |
|---|---|---|
| Tên, email, số điện thoại hồ sơ | Còn mục đích giữ hợp lệ sau khi đóng tài khoản không? | Xóa khi không còn căn cứ lưu |
| Session/token | Có còn được phép đăng nhập không? | Thu hồi ngay về mặt xác thực, dọn bản lưu |
| Clickstream có userId | Có thể định vị và xóa hết bản ghi của user này không? | Xóa ở hot, archive và dữ liệu dẫn xuất |
| Đơn hàng/hóa đơn | Có nghĩa vụ lưu chứng từ hoặc tranh chấp còn hiệu lực không? | Tách dữ liệu cần giữ tối thiểu, hạn chế truy cập và áp dụng thời hạn hợp lệ |
| Số liệu đã tổng hợp | Có thể tái định danh hoặc suy ra cá nhân không? | Đánh giá mức độ nhận diện trước khi quyết định giữ |
| Bản log yêu cầu xóa | Giữ gì để chứng minh đã xử lý mà không duy trì dữ liệu cá nhân thừa? | Chỉ giữ metadata tối thiểu, thời hạn riêng, quyền kiểm soát chặt |

**Pseudonymization không tự động bằng anonymization.** Thay **userId** bằng mã giả vẫn có thể là dữ liệu liên hệ được với cá nhân nếu còn bảng ánh xạ hoặc các trường có thể suy ngược. Không nên tuyên bố “đã xóa dữ liệu cá nhân” chỉ vì đã băm một trường khóa.

Yêu cầu xóa có thể chịu các nghĩa vụ pháp lý và ngoại lệ khác nhau theo nơi hoạt động. Bài học chỉ đưa ra tư duy kỹ thuật; thời hạn phản hồi, phạm vi ngoại lệ và nghĩa vụ lưu phải xác định theo quy định và chính sách thực tế.

## 10. Đừng để dữ liệu đã xóa xuất hiện lại

Xóa thành công ở kho chính hôm nay chưa chắc đủ. Dữ liệu có thể “sống lại” từ:

- **Cache:** một bản đã cache trước khi xóa vẫn có thể được trả về nếu không vô hiệu hóa hoặc chặn ở lớp đọc.
- **Search index:** pipeline indexing chậm hơn hoặc một batch cũ có thể ghi lại document sau khi nguồn đã xóa.
- **Event replay:** tái phát sự kiện gốc có thể dựng lại hồ sơ hoặc materialized view.
- **Backup restore:** khôi phục snapshot trước thời điểm xóa đưa bản ghi cũ trở lại.
- **Offline export:** file CSV, Parquet hoặc bản sao đối tác chưa nằm trong quy trình hủy.
- **Đồng bộ nhiều khu vực:** replica hoặc consumer xử lý trễ có thể nhận thao tác theo thứ tự khác với dự kiến.

Một thiết kế có thể duy trì **deletion ledger** hoặc trạng thái xóa bền vững để ngăn việc tái tạo dữ liệu trong các luồng đồng bộ/khôi phục. Ledger chỉ nên chứa định danh và bằng chứng tối thiểu đủ phục vụ mục tiêu, được bảo vệ và có chính sách lưu riêng; chính bản ledger cũng cần được đánh giá về dữ liệu cá nhân.

Ví dụ bản ghi theo dõi tối giản ở mức khái niệm:

~~~json
{
  "requestId": "delete-2026-001",
  "subjectKey": "internal-subject-reference",
  "requestedAt": "2026-11-14T09:00:00Z",
  "status": "IN_PROGRESS",
  "steps": {
    "primaryStore": "DONE",
    "sessions": "DONE",
    "searchIndex": "DONE",
    "analytics": "PENDING",
    "archive": "PENDING",
    "backupPolicy": "RECORDED"
  }
}
~~~

Đây là ví dụ minh họa trạng thái; **DONE** phải tương ứng với một xác nhận kiểm chứng thực tế, không chỉ là “đã gửi message”. Các yêu cầu chờ quá thời hạn, lỗi một phần và lần thử lại cần hiển thị cho người vận hành.

Đối với backup bất biến không thể chỉnh từng bản ghi, một cách quản lý là xác định thời hạn hết hạn của từng snapshot và **bắt buộc áp dụng lại các yêu cầu xóa liên quan trước khi mở hệ thống đã restore cho truy cập**. Bản backup trong thời gian tồn tại phải được cô lập và có quyền truy cập chặt chẽ. Phải đảm bảo chính sách này phù hợp với nghĩa vụ xóa thực tế; việc chỉ trông chờ backup hết hạn về sau có thể không đáp ứng mọi yêu cầu.

Nếu dùng mã hóa với khóa riêng theo phạm vi dữ liệu, việc phá hủy khóa có thể hỗ trợ xóa bằng mật mã. Tuy nhiên, chỉ kết luận dữ liệu không thể đọc khi đã kiểm chứng không còn bản rõ, bản sao dùng khóa khác hoặc đường tái tạo khóa còn tồn tại.

## 11. Xóa theo thời gian khác xóa theo chủ thể

Đây là một phân biệt quan trọng khi chọn partition key và chiến lược lưu lâu dài.

**Xóa theo thời gian:** “Xóa toàn bộ event trước ngày X.” Nếu dữ liệu được tổ chức theo bucket thời gian, tác vụ có thể tìm và dọn từng bucket đủ điều kiện. Phải kiểm tra sự kiện gửi muộn, ranh giới thời gian, dữ liệu cùng bucket còn cần giữ và ngoại lệ bảo lưu.

**Xóa theo chủ thể:** “Xóa mọi event thuộc user-71, dù nằm ở ngày nào.” Nếu dữ liệu chỉ phân vùng theo ngày mà không có đường tra cứu user hiệu quả, thao tác có thể phải quét rất nhiều file hoặc partition. Ngược lại, phân vùng chỉ theo **userId** có thể làm xóa theo ngày và phân tích toàn hệ thống khó khăn.

Vì vậy, khi biết trước cần xóa theo user, nên cân nhắc:

- Index hoặc danh mục giúp định vị dữ liệu theo **userId**.
- Metadata trong archive đủ để xác định file/bucket bị ảnh hưởng.
- Cách viết lại file archive khi chỉ một phần bản ghi cần xóa; không mặc nhiên xóa cả file chứa dữ liệu người khác.
- Khả năng xử lý các bảng/collection dẫn xuất và aggregate đã tính.
- Kiểm chứng rằng dữ liệu bị xóa không còn trả về ở cả truy vấn theo thời gian lẫn truy vấn theo chủ thể.

Thiết kế vật lý thường phải cân bằng giữa **truy vấn hằng ngày**, **xóa theo thời hạn** và **xóa theo người dùng**. Không tồn tại một partition key tối ưu đồng thời cho mọi đường truy cập.

## 12. Quan sát và kiểm chứng chính sách lưu giữ

Một hệ thống làm đúng vòng đời dữ liệu phải cung cấp bằng chứng ở các lớp:

| Điều cần quan sát | Chỉ số/bằng chứng gợi ý | Điều cần tránh kết luận vội |
|---|---|---|
| Tăng trưởng | Bytes/day, documents/day, index bytes, phân bố theo tenant | Tổng dung lượng thấp không có nghĩa không có hot partition |
| Chuyển archive | Batch đã xuất, checksum, số bản ghi, checkpoint và lỗi retry | Upload file thành công chưa chứng minh dữ liệu phục hồi được |
| Truy cập kho lạnh | Thời gian truy xuất/restore, tỷ lệ yêu cầu thành công, chi phí | Lưu lâu không đồng nghĩa truy vấn thời gian thực |
| Dọn TTL | Số bản ghi quá hạn vẫn còn, độ trễ dọn, hàng đợi tác vụ | TTL đã cấu hình chưa chứng minh đã xóa đúng hạn |
| Xóa theo user | Trạng thái từng hệ, tác vụ chưa xác nhận, thời gian hoàn tất | Một API trả 200 chưa chứng minh mọi bản sao đã xử lý |
| Không tái xuất hiện | Thử đọc sau xóa, kiểm thử restore/replay, dấu vết đối soát | Một lần tìm kiếm không có kết quả chưa chứng minh mọi nơi đều sạch |
| Backup | Tuổi backup cao nhất, ngày hết hạn, kiểm thử phục hồi có áp dụng deletion ledger | Xóa kho chính không tự dọn các snapshot cũ |

Ví dụ một yêu cầu nghiệm thu có thể viết như sau:

> Với một session đã qua **expiresAt**, mọi yêu cầu xác thực phải bị từ chối ngay theo thời gian hiện tại, kể cả khi tác vụ dọn TTL chưa chạy. Tác vụ nền sau đó dọn dữ liệu vật lý theo độ trễ vận hành đã quy định và phải có chỉ số theo dõi lượng session quá hạn.

Một yêu cầu nghiệm thu khác:

> Với một batch sự kiện chuyển sang archive, hệ thống chỉ xóa batch tương ứng khỏi kho nóng sau khi manifest được xác minh; thử đọc dữ liệu archive phải đạt kết quả theo hợp đồng, và khi cần retry không sinh ra bản trùng ngoài chính sách.

Hai ví dụ kiểm tra **hành vi có thể quan sát**, thay vì chỉ kiểm tra đã chạy lệnh TTL hay export.

### Các tình huống lỗi nên mô phỏng

1. **Tác vụ archive bị dừng** sau khi xuất một nửa dữ liệu: chạy lại có hoàn tất đúng không, và bản nóng có bị xóa trước khi đủ dữ liệu không?
2. **Một user yêu cầu xóa** trong lúc batch export đang chạy: batch có vô tình đưa dữ liệu đã đánh dấu xóa vào archive không?
3. **Một consumer xử lý chậm** nhận sự kiện tạo hồ sơ sau yêu cầu xóa: có ngăn tái tạo không?
4. **Khôi phục snapshot cũ:** dữ liệu đã xóa có được xử lý lại trước khi phục vụ người dùng không?
5. **Sự kiện đến muộn:** một sự kiện xảy ra từ nhiều tháng trước vừa được gửi lên; chính sách retention sẽ áp dụng từ mốc nào?
6. **Một tenant có tải đột biến:** bucket hoặc partition có nóng lên gây chậm truy vấn và làm backlog dọn dữ liệu tăng không?

Các tình huống này nối chính sách dữ liệu với thiết kế workload: khi tải tăng, tác vụ TTL, archive và purge phải có năng lực theo kịp tốc độ phát sinh mới duy trì được thời hạn mong muốn.

## 13. Từ yêu cầu đến phương án vận hành: một bản thiết kế thu gọn

Tổng hợp trường hợp **activity_events** có 2.000 sự kiện/giây trung bình:

| Quyết định | Phương án minh họa | Lý do |
|---|---|---|
| Đường đọc chính | Lọc theo tenantId và occurredAt, lấy sự kiện mới nhất | Phù hợp điều tra và tra cứu gần đây |
| Vùng nóng | 30 ngày | Phạm vi thường xuyên truy vấn trực tuyến |
| Vùng dài hạn | Sau khi export và verify, lưu đến đủ 180 ngày tính từ occurredAt | Đáp ứng truy vấn lịch sử ít thường xuyên |
| Điều kiện xóa bản nóng | Archive đã ghi, kiểm chứng và checkpoint thành công | Tránh mất dữ liệu khi tác vụ chuyển vùng lỗi |
| Điều kiện xóa archive | Hết hạn tổng, không có bảo lưu hợp lệ | Tôn trọng retention và ngoại lệ |
| Xóa theo user | Định vị cả hot, archive, các bản sao và dữ liệu dẫn xuất | Không bỏ sót dữ liệu do copy/transform |
| Tải và tăng trưởng | Dự báo theo tốc độ ghi, kích thước và phân bố tenant | Quy hoạch dung lượng, partition và khả năng chạy job nền |
| Kết quả có thể kiểm chứng | Số liệu tính nhất quán batch, xác nhận purge, latency, backlog | Biết chính sách có thật sự được thực thi |

Quy trình quyết định có thể dùng lại cho các hệ NoSQL:

~~~text
Mục đích và nghĩa vụ với dữ liệu
              |
              v
Nhóm dữ liệu + mốc thời gian + ngoại lệ
              |
              v
Đường đọc/ghi + tốc độ tăng + phân bố tải
              |
              v
Chọn cấu trúc lưu, key/partition, index
              |
              v
Chọn hot/warm/cold + cách archive + thời hạn cuối
              |
              v
Thiết kế TTL/purge + xóa theo chủ thể + backup/restore
              |
              v
Đo hiệu năng, đối chiếu kết quả, quan sát độ trễ xóa
              |
              +------> Điều chỉnh khi dữ liệu hoặc yêu cầu thay đổi
~~~

## 14. Bài tập áp dụng

**Bài tập 1 — Tính tốc độ tăng.** Một hệ thống ghi trung bình 750 event/giây, mỗi event 1.200 byte. Hãy ước lượng dữ liệu thô cho 1 ngày, 14 ngày và 90 ngày theo đơn vị thập phân. Sau đó nêu những khoản cần bổ sung trước khi chọn dung lượng cluster.

**Bài tập 2 — Xử lý sự kiện đến muộn.** Chính sách giữ sự kiện 30 ngày kể từ **occurredAt**, nhưng một thiết bị offline gửi dữ liệu sau 20 ngày. Hãy giải thích vì sao lấy **ingestedAt** làm mốc dọn tự động sẽ khác hợp đồng, và cần làm gì nếu sự kiện đến sau cả hạn 30 ngày.

**Bài tập 3 — TTL và quyền truy cập.** Session có **expiresAt** đã qua 5 giây nhưng document vẫn còn vì job TTL chưa chạy. Trình bày điều kiện đọc đúng, trải nghiệm mong đợi của người dùng và chỉ số vận hành để theo dõi việc dọn nền.

**Bài tập 4 — Xóa tài khoản.** Người dùng yêu cầu xóa dữ liệu sau khi hệ thống đã xuất lịch sử 6 tháng sang object storage và tạo báo cáo tổng hợp. Hãy liệt kê các nguồn và bản dẫn xuất cần kiểm tra, cách ngăn một job replay phục hồi dữ liệu, và những bằng chứng cần có trước khi báo hoàn tất.

**Bài tập 5 — Archive thất bại.** Job đã xuất 80% dữ liệu ngày cũ thì mất kết nối. Hãy đề xuất cách đặt checkpoint, kiểm tra bản xuất, retry và thời điểm được phép xóa bản nóng sao cho không mất dữ liệu.

Khi trả lời, luôn nối các quyết định với nhau theo chuỗi **mục đích lưu dữ liệu → chính sách thời gian → tốc độ tăng và access pattern → cách lưu/di chuyển/xóa → bằng chứng quan sát**. Đó là cách xem vòng đời dữ liệu như một phần của thiết kế NoSQL, thay vì coi lưu trữ dài hạn và xóa là việc dọn dẹp bổ sung sau khi ứng dụng đã hoạt động.
