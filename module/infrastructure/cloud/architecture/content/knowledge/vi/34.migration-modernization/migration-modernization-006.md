# Đồng bộ dữ liệu trong giai đoạn chạy song song

## 1. Bối cảnh và mục tiêu

Khi di chuyển hoặc hiện đại hóa ứng dụng lên đám mây, hiếm khi có thể tắt toàn bộ hệ thống cũ, chép dữ liệu một lần rồi bật hệ thống mới mà không ảnh hưởng đến người dùng. Thường cần một giai đoạn **chạy song song** (*parallel run/coexistence*): hệ thống cũ tiếp tục xử lý nghiệp vụ trong khi hệ thống mới được nạp dữ liệu, thử nghiệm và nhận dần lưu lượng.

Ví dụ, một nền tảng bán hàng đang chuyển từ ứng dụng nguyên khối dùng cơ sở dữ liệu tại trung tâm dữ liệu sang dịch vụ đơn hàng triển khai trên cloud. Trong nhiều tuần, đơn mới và thay đổi trạng thái vẫn phát sinh ở hệ thống cũ; hệ thống mới phải đọc được dữ liệu đủ mới để thử nghiệm, đối soát và cuối cùng tiếp quản. Nếu chỉ sao chép toàn bộ dữ liệu ở thời điểm đầu, hai bên sẽ lệch nhau ngay sau lần ghi tiếp theo.

Thiết kế đồng bộ tốt phải trả lời đồng thời năm nhóm yêu cầu kiến trúc:

- **Độ tin cậy:** không mất bản ghi, không áp dụng cùng một thay đổi hai lần theo cách gây tác dụng phụ, có đường phục hồi khi ngừng kết nối.
- **Bảo mật:** dữ liệu được truyền và lưu với quyền tối thiểu, mã hóa phù hợp, kiểm soát dữ liệu nhạy cảm trong log và môi trường kiểm thử.
- **Khả năng mở rộng:** tốc độ nạp và xử lý thay đổi theo kịp tốc độ ghi, kể cả giờ cao điểm.
- **Chi phí:** kiểm soát chi phí hạ tầng chạy song song, truyền dữ liệu, lưu log và lưu trữ tạm.
- **Vận hành:** biết độ trễ, mức sai lệch, vị trí lỗi, điều kiện chuyển đổi và khả năng quay lui.

Sau bài học, người học có thể chọn mô hình đồng bộ phù hợp, thiết kế luồng *snapshot + change data capture*, lập tiêu chí đối soát, xác định điều kiện *cutover/rollback*, và đánh giá lựa chọn theo tư duy **Well-Architected**.

## 2. Hiểu đúng “đồng bộ” trong giai đoạn chạy song song

### 2.1. Phân biệt các khái niệm

| Khái niệm | Ý nghĩa | Câu hỏi thiết kế cần trả lời |
| --- | --- | --- |
| *Initial load / snapshot* | Nạp trạng thái dữ liệu ban đầu từ nguồn sang đích. | Ảnh chụp nhất quán tại mốc nào? |
| *Change data capture* (CDC) | Thu thập các thay đổi phát sinh sau hoặc trong lúc nạp ban đầu, thường từ transaction log. | Làm sao không bỏ sót khoảng giao giữa snapshot và CDC? |
| *Replication* | Sao chép thay đổi liên tục; có thể ở mức cơ sở dữ liệu, bảng hoặc sự kiện. | Chiều sao chép, độ trễ và ngữ nghĩa áp dụng thay đổi ra sao? |
| *Dual write* | Một thao tác nghiệp vụ cố ghi sang hai hệ thống. | Điều gì xảy ra nếu chỉ một bên ghi thành công? |
| *Shadow read / shadow traffic* | Gửi lượt đọc hoặc yêu cầu kiểm thử sang hệ mới nhưng chưa dùng kết quả đó để quyết định nghiệp vụ. | Làm sao so sánh kết quả an toàn, tránh tác dụng phụ? |
| *Cutover* | Chuyển quyền xử lý hoặc quyền ghi chính sang hệ thống mới. | Mốc chuyển quyền được bảo vệ bằng cơ chế nào? |
| *Rollback / failback* | Trả quyền xử lý về hệ cũ sau cutover. | Dữ liệu được ghi mới có quay về hệ cũ đầy đủ không? |

**Đồng bộ không đồng nghĩa với hai cơ sở dữ liệu giống hệt nhau ở mọi thời điểm.** Với luồng bất đồng bộ, bản đích có thể trễ nguồn vài giây hoặc lâu hơn khi gặp sự cố. Cần quy định trước độ trễ có thể chấp nhận, loại dữ liệu nào đòi hỏi tính nhất quán mạnh và hệ thống nào được phép nhận lệnh ghi.

### 2.2. Ranh giới sở hữu dữ liệu là quyết định đầu tiên

Trong phần lớn cuộc di chuyển, lựa chọn dễ kiểm soát nhất là **một nguồn ghi có thẩm quyền cho mỗi thực thể hoặc miền nghiệp vụ tại một thời điểm** (*single write authority*). Ví dụ:

- Trước cutover, hệ cũ sở hữu quyền tạo và đổi trạng thái đơn hàng; hệ mới nhận bản sao chỉ đọc.
- Trong canary, có thể chuyển quyền ghi cho một nhóm tenant hoặc miền dữ liệu được phân vùng rõ ràng; mỗi đơn hàng vẫn chỉ có **một** nơi sở hữu quyền ghi.
- Sau cutover, hệ mới sở hữu quyền ghi; quyền ghi cũ bị chặn hoặc định tuyến về hệ mới.

Nếu cả hai hệ thống được phép ghi cùng một thực thể, kiến trúc phải giải quyết xung đột, thứ tự, khóa logic và quy tắc hòa giải. Chỉ bật đồng bộ hai chiều không tự tạo ra tính nhất quán.

**Lưu ý:** quyền sở hữu có thể khác nhau giữa các miền dữ liệu. Chẳng hạn, đơn hàng đã sang hệ mới nhưng dữ liệu khách hàng tham chiếu vẫn do hệ cũ quản lý qua API hoặc bản sao được đồng bộ.

## 3. Các mô hình đồng bộ và đánh đổi

| Mô hình | Phù hợp khi | Điểm mạnh | Rủi ro và giới hạn |
| --- | --- | --- | --- |
| Sao chép cơ sở dữ liệu/CDC một chiều | Di chuyển CSDL hoặc dựng bản sao phục vụ đọc; nguồn ghi được xác định rõ. | Ít sửa code ứng dụng; bắt được insert/update/delete theo log. | Trễ đồng bộ; phụ thuộc log, quyền truy cập và tương thích schema/kiểu dữ liệu. |
| Snapshot định kỳ hoặc ETL theo lô | Dữ liệu tham chiếu ít thay đổi, báo cáo chấp nhận trễ. | Dễ vận hành, có thể biến đổi dữ liệu. | Khoảng cách cập nhật lớn; khó đáp ứng nghiệp vụ giao dịch gần thời gian thực. |
| Sự kiện nghiệp vụ qua outbox | Hiện đại hóa dần thành dịch vụ; cần phát tán thay đổi có ý nghĩa nghiệp vụ. | Giảm phụ thuộc schema CSDL; hỗ trợ nhiều consumer. | Phải quản lý schema sự kiện, replay, idempotency và vòng đời outbox. |
| Đồng bộ qua API | Hệ nguồn không cho đọc transaction log, hoặc chỉ cung cấp giao diện nghiệp vụ. | Giữ nguyên quy tắc truy cập và phân quyền nguồn. | Giới hạn rate, phân trang, version/ETag và khó bắt mọi thay đổi/xóa. |
| Dual write trực tiếp từ ứng dụng | Trường hợp hẹp, hai đích không có phương án sự kiện/CDC khả thi. | Cập nhật cả hai gần thời điểm yêu cầu. | Ghi một bên thành công và một bên thất bại; khó rollback; thường không khuyến nghị làm chiến lược mặc định. |
| Đồng bộ hai chiều/active-active | Có yêu cầu kinh doanh rõ ràng về nhiều điểm ghi độc lập. | Có thể giảm phụ thuộc vào một điểm ghi. | Xung đột, vòng lặp cập nhật, phân vùng mạng, thứ tự xuyên vùng và độ phức tạp cao. |

Với di chuyển OLTP thông thường, **snapshot nhất quán + CDC một chiều + một nơi sở hữu ghi** thường là phương án khởi đầu hợp lý. Trường hợp tách microservice, *transactional outbox* giúp chuyển tiếp thay đổi nghiệp vụ mà không cần ghi cơ sở dữ liệu đích trực tiếp trong cùng request.

### Tại sao dual write trực tiếp dễ hỏng?

Giả sử API ghi đơn hàng vào A rồi vào B:

1. Ghi A thành công, B timeout. Client không biết B đã ghi hay chưa.
2. API retry, B có thể nhận trùng lệnh; A cũng có thể tạo thêm tác dụng phụ.
3. Không có giao dịch phân tán giữa hai hệ thống, “thành công ở cả hai” không được bảo đảm chỉ bởi hai lời gọi tuần tự.

Giải pháp thường an toàn hơn là **ghi dữ liệu nghiệp vụ và bản ghi outbox trong cùng một giao dịch ở hệ sở hữu**, sau đó tiến trình phát sự kiện chuyển đi. Consumer ở đích xử lý lặp lại được. Outbox bảo đảm bản ghi cần phát được commit cùng dữ liệu nguồn, nhưng **không tự bảo đảm exactly-once ở mọi tầng**: mạng và broker vẫn có thể giao sự kiện lặp.

## 4. Kiến trúc tham chiếu: snapshot kết hợp CDC

~~~mermaid
flowchart LR
    U[Người dùng / API] --> R[Bộ định tuyến lưu lượng]
    R -->|Trước cutover: ghi| O[Ứng dụng cũ]
    O --> DB1[(CSDL nguồn)]
    DB1 -->|Snapshot nhất quán| L[Pipeline nạp ban đầu]
    DB1 -->|Transaction log / CDC| C[Pipeline thay đổi]
    L --> A[Biến đổi & áp dụng idempotent]
    C --> A
    A --> DB2[(CSDL đích trên cloud)]
    DB1 --> V[Đối soát tại mốc nhất quán]
    DB2 --> V
    R -.->|Shadow read / canary có kiểm soát| N[Ứng dụng mới]
    N --> DB2
    C --> M[Metrics, cảnh báo, DLQ]
    A --> M
    V --> M
~~~

Ở sơ đồ trên, đường ghi chủ đạo vẫn qua hệ cũ cho tới khi cutover. Pipeline dữ liệu gồm hai đường **phải phối hợp bằng một vị trí thay đổi có thể xác định**:

1. **Chuẩn bị nguồn:** thống kê bảng, khóa chính, quan hệ, transaction log, cơ chế xóa, phân quyền, khối lượng và tốc độ ghi; chọn mốc CDC tương ứng với snapshot.
2. **Chụp ảnh nhất quán:** lấy dữ liệu ban đầu theo snapshot transaction hoặc phương án có tính nhất quán tương đương. Với dữ liệu lớn, chia lô theo khóa ổn định; không mặc định nhiều câu truy vấn rời rạc sẽ cùng nhìn thấy một thời điểm.
3. **Ghi nhớ vị trí thay đổi:** giữ LSN, binlog position, resume token hoặc cursor do nền tảng hỗ trợ. Cách gắn mốc phụ thuộc engine; không đơn giản lấy thời gian đồng hồ làm bằng chứng rằng mọi thay đổi đã được đọc.
4. **Nạp vào đích:** ánh xạ kiểu dữ liệu, khóa và ràng buộc; hỗ trợ retry an toàn và không làm mất trạng thái sự kiện mới hơn.
5. **Phát lại thay đổi:** xử lý mọi insert/update/delete từ mốc đã chọn, kể cả thay đổi xảy ra khi snapshot đang chạy; khử trùng lặp và giữ thứ tự thích hợp.
6. **Theo kịp nguồn:** theo dõi backlog và độ trễ đầu cuối cho đến khi pipeline ổn định; bắt đầu đối soát và shadow read.

Hai cách triển khai phổ biến là: (a) công cụ CDC hỗ trợ sẵn snapshot kèm stream với cơ chế phối hợp mốc, hoặc (b) pipeline tự xây với snapshot nhất quán và watermark được quản lý chặt. Nếu tự xây, phải chứng minh không có *gap* giữa hai giai đoạn và không cho sự kiện cũ ghi đè trạng thái mới.

### Phân biệt di chuyển dữ liệu với thay đổi mô hình

Khi hệ mới dùng schema khác hệ cũ, cần một lớp chuyển đổi rõ ràng:

- Chuyển kiểu, múi giờ, precision số tiền, encoding, nullability và định danh.
- Chuẩn hóa dữ liệu trước khi áp constraint mới; phát hiện giá trị không hợp lệ bằng báo cáo thay vì lặng lẽ bỏ qua.
- Quản lý phiên bản mapping/schema vì trong thời gian chạy song song, cả hai ứng dụng có thể được triển khai phiên bản mới.
- Dùng mô hình **expand → migrate → contract**: mở rộng schema để cả mã cũ và mới hiểu dữ liệu, chuyển và xác minh, rồi chỉ loại bỏ field cũ sau khi không còn consumer phụ thuộc.

Ví dụ, cột trạng thái cũ kiểu chuỗi có thể tách thành mã trạng thái chuẩn và thời điểm cập nhật ở đích. Khi đó, so sánh byte-to-byte giữa hai bảng là không đủ; cần so sánh theo **quy tắc nghiệp vụ tương đương**.

## 5. Bảo đảm tính đúng đắn của từng thay đổi

### 5.1. Idempotency, thứ tự và giao dịch

CDC/broker thường thiết kế theo kiểu *at-least-once*: cùng một sự kiện có thể được phát lại sau khi consumer crash, timeout hoặc checkpoint thất bại. Đích phải xử lý an toàn khi nhận trùng.

Mỗi thay đổi nên mang một định danh sự kiện, định danh thực thể, phiên bản hoặc sequence thích hợp, loại thao tác và vị trí trong stream. Một consumer có thể dùng thuật toán:

~~~text
nhận change(event_id, entity_id, entity_version, operation, payload, stream_position)

BEGIN TRANSACTION trên hệ đích
  nếu event_id đã được xử lý:
      bỏ qua tác dụng lên dữ liệu
  ngược lại:
      đọc version hiện lưu của entity_id (kể cả tombstone nếu đã xóa)
      nếu entity_version mới hơn version đang lưu:
          nếu operation = DELETE: ghi tombstone với version mới
          nếu operation = UPSERT: áp dụng payload và version mới
      ghi dấu event_id đã xử lý
  cập nhật checkpoint chỉ cho đoạn stream đã xử lý liên tục, đúng partition
COMMIT
~~~

Đây là **mã giả**, không phải một thư viện triển khai sẵn. Điều kiện quan trọng là dữ liệu, dấu khử trùng lặp và checkpoint (nếu lưu được cùng kho/giao dịch) phải nhất quán. Nếu checkpoint ở hệ khác, cần quy trình xử lý lại an toàn sau crash. Phiên bản phải tăng đơn điệu **cho cùng thực thể**; không được tự tiện so sánh sequence từ các partition hoặc nguồn độc lập.

Các tình huống cần kiểm thử:

- **Lặp sự kiện:** nhận cùng event hai lần, trạng thái không đổi lần thứ hai.
- **Đảo thứ tự:** UPDATE version 8 đến trước version 7; bản version 7 không được ghi đè version 8.
- **Xóa rồi tạo lại:** nếu chỉ xóa vật lý mà không giữ version/tombstone, một UPDATE cũ có thể làm sống lại dữ liệu đã xóa.
- **Nhiều bảng trong một giao dịch:** một giao dịch nguồn thay đổi order và order_item; đích cần đảm bảo không lộ trạng thái nửa chừng nếu nghiệp vụ cần quan sát tính nguyên tử.
- **Tác dụng phụ ngoài dữ liệu:** phát email, thanh toán và điều chỉnh tồn kho không được tự động chạy chỉ vì sự kiện lịch sử được replay.

### 5.2. Quyết định mức nhất quán theo nghiệp vụ

| Dữ liệu / thao tác | Mức nhất quán thường cần | Thiết kế gợi ý |
| --- | --- | --- |
| Đặt hàng, ghi nhận thanh toán, giữ hàng tồn | Cần quyết định trên trạng thái có thẩm quyền, tránh hai nơi cùng chốt giao dịch. | Lệnh ghi đi qua một owner; thao tác xuyên dịch vụ dùng API/transaction hoặc saga có bù trừ được thiết kế rõ. |
| Tìm kiếm đơn hàng, dashboard vận hành | Có thể chấp nhận trễ vài giây theo SLO. | Bản sao CDC, chỉ số lag, hiển thị thời điểm dữ liệu cập nhật. |
| Danh mục sản phẩm, cấu hình ít đổi | Có thể chấp nhận trễ lớn hơn tùy rủi ro. | CDC hoặc đồng bộ định kỳ với version. |
| Báo cáo kế toán, đối soát doanh thu | Cần đầy đủ và tái lập theo mốc chốt số. | Watermark, snapshot hoặc cửa sổ kỳ kế toán; kiểm tổng và dữ liệu chi tiết. |

Không sử dụng một bản sao bất đồng bộ làm nguồn quyết định giao dịch quan trọng nếu yêu cầu nghiệp vụ đòi đọc dữ liệu mới nhất từ nơi sở hữu quyền ghi.

### 5.3. Xung đột nếu bắt buộc ghi hai chiều

Trước khi chấp nhận kiến trúc hai chiều, cần xác định: ai là owner của mỗi trường; khóa nhận diện xung đột; xử lý sự kiện trùng hoặc tự dội lại; thời hạn phát hiện; ai duyệt xung đột không giải được. Các chính sách thường gặp:

- **Phân vùng quyền ghi:** tenant/aggregate A chỉ ở vùng 1, B chỉ ở vùng 2 — ưu tiên khi khả thi.
- **Version có điều kiện:** bản ghi mới chỉ thay đổi khi thỏa điều kiện version/ETag.
- **Hòa giải theo nghiệp vụ:** ví dụ tình trạng thanh toán lấy từ sổ cái có thẩm quyền; không ghép tùy ý hai bản ghi.
- **Last-write-wins:** đơn giản nhưng dễ làm mất cập nhật nếu đồng hồ lệch hoặc hai thao tác cùng xảy ra; không phù hợp mặc định cho dữ liệu tài chính.

Nếu không chứng minh được quy tắc xử lý xung đột, nên quay về thiết kế một chủ ghi và định tuyến lệnh qua chủ đó.

## 6. Độ trễ, năng lực xử lý và điểm lỗi

Độ trễ đồng bộ không chỉ là thời gian message nằm trong broker. Một phép đo hữu ích là từ lúc giao dịch nguồn **commit** tới khi thay đổi đã được áp dụng và đọc thấy ở đích. Theo dõi cả trung vị, p95/p99 và thời gian trễ lớn nhất theo bảng/partition.

Giả sử nguồn trung bình sinh 200 thay đổi/giây, pipeline xử lý bền vững 500 thay đổi/giây. Sau gián đoạn 10 phút, backlog xấp xỉ **120.000 thay đổi**. Khi nguồn vẫn ghi 200 thay đổi/giây, công suất bắt kịp thực là 500 − 200 = **300 thay đổi/giây**, nên cần khoảng **400 giây** để xóa backlog nếu các tốc độ ổn định và không có điểm nghẽn khác. Khi công suất xử lý nhỏ hơn hoặc bằng tốc độ phát sinh, backlog sẽ không tự giảm.

Các giới hạn thường gặp gồm transaction log retention không đủ, kết nối mạng hybrid không ổn định, biến đổi schema tốn CPU, ghi đích bị throttling, bảng thiếu khóa chính và partition lệch tải. Nâng số consumer không luôn giải quyết được nếu phải giữ thứ tự cho một khóa hoặc đích có giới hạn throughput.

**Quy hoạch dung lượng** nên xem xét tốc độ ghi đỉnh, dung lượng backfill, độ lớn sự kiện, retry, thời gian giữ log, khả năng replay, kết nối site-to-site và dung lượng đích. Throttling và retry cần có backoff/jitter; sự kiện lỗi bất thường cần cách ly vào *dead-letter queue* (DLQ) hoặc hàng xử lý lỗi có quy trình sửa và phát lại, không được âm thầm bỏ.

### Chỉ số và cảnh báo nên có

| Tín hiệu | Ý nghĩa vận hành | Khi vượt ngưỡng |
| --- | --- | --- |
| Source commit → target applied lag | Độ mới dữ liệu thực tế. | Kiểm tra queue, network, consumer, DB đích; tạm dừng cutover. |
| Backlog / tuổi sự kiện cũ nhất | Khả năng bắt kịp khi tải tăng. | Tăng công suất đúng điểm nghẽn, giảm tải backfill, điều chỉnh partition. |
| Sự kiện lỗi, retry, DLQ | Dữ liệu có thể đã không được áp dụng. | Phân loại, khắc phục, replay có kiểm soát; đối soát vùng ảnh hưởng. |
| Vị trí CDC và log retention còn lại | Nguy cơ mất cửa sổ replay. | Can thiệp trước khi log bị dọn, có phương án resnapshot. |
| Chênh lệch số lượng/checksum/bất biến nghiệp vụ | Khả năng thiếu, trùng hoặc sai biến đổi. | Khoanh vùng theo mốc, tenant, khóa, đối chiếu chi tiết. |
| Latency và lỗi ứng dụng mới | Ảnh hưởng người dùng khi thử traffic mới. | Giảm canary hoặc trả read traffic về nguồn cũ. |

Ngưỡng cảnh báo phải bắt nguồn từ **SLO nghiệp vụ** và khả năng khôi phục đã thử nghiệm, không lấy một giá trị cố định áp dụng mọi hệ thống. **RPO** mô tả mức mất dữ liệu tối đa chấp nhận khi có sự cố; **RTO** mô tả thời gian khôi phục. Độ trễ CDC là chỉ số quan trọng để đánh giá RPO nhưng bản thân nó không bảo đảm RPO nếu log bị mất hoặc có thay đổi bỏ sót.

## 7. Đối soát: chứng minh dữ liệu đủ và đúng

Một pipeline “đang chạy” chưa chứng minh dữ liệu ở đích chính xác. Đối soát cần kết hợp:

1. **Đủ dữ liệu:** số lượng theo bảng, tenant, trạng thái và thời gian; không có khóa bị thiếu hoặc phát sinh ngoài quy tắc.
2. **Đúng nội dung:** so sánh trường quan trọng, hash đã chuẩn hóa, tổng tiền, tổng số lượng, quan hệ khóa ngoại, null và timezone.
3. **Đúng theo nghiệp vụ:** tổng tiền đơn = tổng dòng hàng sau quy tắc thuế/giảm giá; đơn đã thanh toán phải có tham chiếu thanh toán hợp lệ; trạng thái không đi ngược quy trình.
4. **Đúng thời điểm:** so sánh cả hai phía ở **cùng watermark/mốc dữ liệu** hoặc sau khi bảo đảm đích đã bắt kịp mốc đã chốt; tránh kết luận “lệch” chỉ vì nguồn vừa nhận thêm giao dịch.
5. **Có thể kiểm toán:** lưu mốc, phạm vi, phiên bản quy tắc mapping, kết quả, mẫu lỗi và người/phần mềm xác nhận.

Ví dụ, sau khi chặn ghi cho một tập đơn hàng thử nghiệm và bảo đảm CDC đã áp dụng tới watermark W, có thể so sánh:

~~~sql
-- Chạy logic tương ứng ở cả nguồn và đích trên CÙNG phạm vi đã chốt.
-- Đây là mẫu minh họa: điều chỉnh tên cột, timezone và currency precision.
SELECT
    tenant_id,
    status,
    COUNT(*) AS order_count,
    SUM(total_amount_minor_unit) AS amount_minor_unit
FROM orders
WHERE tenant_id = :tenant_id
GROUP BY tenant_id, status
ORDER BY tenant_id, status;
~~~

Dùng đơn vị tiền nhỏ nhất (ví dụ xu) hoặc decimal đủ chính xác; không so sánh tiền bằng floating point. Tổng hợp giống nhau vẫn có thể che giấu lỗi hai bản ghi bù trừ, vì vậy cần kiểm tra theo khóa và lấy mẫu hoặc kiểm toàn bộ ở nhóm dữ liệu có rủi ro cao. Khi dữ liệu quá lớn, có thể chia phạm vi thành các đoạn khóa ổn định và tính hash chuẩn hóa trên cùng bộ trường để khoanh vùng, sau đó so chi tiết đoạn bị lệch.

**Không đối soát trực tiếp hai bảng đang thay đổi tự do rồi xem chênh lệch tức thời là lỗi.** Phải ghi mốc quan sát, độ trễ và phạm vi của phép so sánh.

## 8. Quy trình triển khai từ thử nghiệm tới cutover

### Giai đoạn A — Khảo sát và đặt tiêu chí chấp nhận

Lập danh mục dữ liệu và luồng phụ thuộc: bảng nào là dữ liệu giao dịch, bảng nào có thể tái tạo, nguồn nào ghi, consumer nào đọc, thao tác nào có tác dụng phụ. Ghi nhận số lượng dữ liệu, tải ghi theo thời điểm, yêu cầu lưu trữ, phân loại dữ liệu nhạy cảm, đường mạng, ràng buộc pháp lý và các khoảng bảo trì cho phép.

Đặt tiêu chí đo được trước khi chọn công cụ. Một ví dụ **giả định** cho hệ thống đơn hàng:

- Độ trễ CDC p95 không quá 5 giây khi hoạt động bình thường; cảnh báo nếu vượt 30 giây liên tục 5 phút.
- 100% giao dịch đến mốc cutover được áp dụng và đối soát ở đích trước khi cấp quyền ghi; không có sự kiện lỗi chưa xử lý.
- Không sai lệch tổng tiền trong kỳ đối soát; mọi sai lệch khóa hoặc trạng thái phải được điều tra.
- Thời gian chuyển tuyến dự kiến không quá 10 phút; có cách phục hồi trong 15 phút **nếu** đường dữ liệu quay lui đã được kiểm chứng.

Các ngưỡng này chỉ để minh họa cách viết tiêu chí; giá trị thật phải do tải, SLO, nghiệp vụ và thử nghiệm quyết định.

### Giai đoạn B — Dựng pipeline và nạp ban đầu

Thiết lập kết nối có mã hóa, credential riêng, quyền chỉ đọc log ở nguồn và quyền áp dụng tối thiểu ở đích; bảo vệ secret trong kho bí mật. Bật snapshot/CDC với mốc phù hợp, chạy nạp theo lô được giới hạn để không làm nghẽn nguồn. Thử dừng, restart, mất kết nối, duplicate, schema drift và sự kiện delete. Đảm bảo source log không bị xoá trước khi consumer đọc và checkpoint được lưu bền.

### Giai đoạn C — Chạy song song có quan sát

Tiếp tục để hệ cũ sở hữu ghi; hệ mới nhận dữ liệu. Chạy shadow read và so sánh logic nghiệp vụ bằng request không gây tác dụng phụ. Bật traffic đọc canary theo phạm vi có thể cô lập (ví dụ nhóm người dùng nội bộ hoặc một số tenant), nhưng định tuyến các lệnh ghi nhất quán về owner. Theo dõi độ trễ, lỗi, chi phí, tải nguồn/đích và kết quả đối soát trong nhiều chu kỳ tải, kể cả đỉnh.

### Giai đoạn D — Chốt quyền ghi và chuyển đổi

Một cutover có kiểm soát thường gồm các bước sau:

1. Kiểm tra điều kiện *go/no-go*: mapping ổn định, đối soát đạt, lag trong ngưỡng, công cụ giám sát và nhân sự trực sẵn sàng.
2. Đặt **write fence** tại hệ cũ hoặc cổng lệnh, tạm ngưng/chuyển hàng đợi ghi cho phạm vi cần chuyển; xác định mốc thay đổi cuối cùng W. Mục tiêu là không còn lệnh ghi ngoài kiểm soát vào owner cũ.
3. Chờ stream áp dụng đến W, xác nhận không có sự kiện lỗi chưa xử lý và đối soát dữ liệu quan trọng tại W. Không chỉ dựa vào một chỉ số “lag = 0” nếu mốc, lỗi và thứ tự chưa được xác minh.
4. Chuyển quyền ghi, tuyến API, secret/quyền truy cập và cấu hình ứng dụng về hệ mới; mở nhận ghi ở owner mới. Bảo đảm fence ngăn hệ cũ tiếp tục nhận ghi cho cùng phạm vi.
5. Chạy smoke test giao dịch thật có kiểm soát, kiểm tra đọc sau ghi trên owner mới, quan sát chặt lỗi ứng dụng, chỉ số dữ liệu và hiệu năng.

Một số kiến trúc có thể giảm thời gian ngưng ghi bằng hàng đợi lệnh, phân vùng tenant hoặc cơ chế chuyển chủ chuyên dụng, nhưng **zero downtime/zero data loss** là yêu cầu cần chứng minh qua thử nghiệm. Không nên tự suy ra từ việc dùng CDC.

### Giai đoạn E — Ổn định, rollback và kết thúc

Trước cutover, quyết định rõ **điều kiện quay lui** và dữ liệu phát sinh sau cutover sẽ được xử lý thế nào. Có hai tình huống rất khác nhau:

- **Chưa mở ghi ở hệ mới:** có thể trả tuyến về hệ cũ tương đối đơn giản nếu fence/mốc không làm mất lệnh đang chờ.
- **Đã có ghi ở hệ mới:** trả tuyến về hệ cũ mà không đồng bộ ngược sẽ mất hoặc làm phân nhánh giao dịch mới. Cần reverse sync đã thử nghiệm, cơ chế replay lệnh có kiểm soát, hoặc chiến lược *roll forward* sửa lỗi trên hệ mới. Không gọi chuyển DNS về cũ là một rollback dữ liệu an toàn.

Giữ bản nguồn cũ ở chế độ bảo vệ/read-only theo chính sách trong giai đoạn ổn định; chỉ tháo bỏ pipeline và hạ tầng song song sau khi hết thời hạn quan sát, hoàn tất đối soát, lưu trữ/kiểm toán, sao lưu, diễn tập phục hồi và xác nhận các consumer đã chuyển hết.

## 9. Lỗi điển hình và cách xử lý

| Sự cố | Dấu hiệu | Hành động thiết kế/vận hành |
| --- | --- | --- |
| Snapshot chạy lâu; nguồn tiếp tục đổi dữ liệu | Bản ghi cũ ghi đè thay đổi mới hoặc thiếu thay đổi. | Phối hợp snapshot với mốc CDC, version và cơ chế áp dụng đúng thứ tự. |
| Mất kết nối hybrid vài giờ | Backlog tăng, lag vượt SLO. | Retry có backoff, giữ log đủ lâu, capacity để catch up; nếu mất log phải lập kế hoạch resnapshot. |
| Schema nguồn thay đổi bất ngờ | Consumer không parse được, DLQ tăng. | Hợp đồng schema có version, kiểm tra tương thích trước deploy, runbook tạm dừng và xử lý replay. |
| Delete không được truyền | Bản đích chứa dữ liệu đã xóa. | Bật capture delete, tombstone/version, kiểm tra chính sách retention và xóa dữ liệu cá nhân. |
| Trùng sự kiện sau restart | Đếm gấp đôi, phát lại tác dụng phụ. | Inbox/dedup, idempotent upsert, tránh kích hoạt side effect từ replay. |
| Bản đích đọc thấy nửa giao dịch | Order tồn tại nhưng order_item chưa có. | Giữ transaction boundary hoặc thiết kế read model chỉ công bố sau khi aggregate hoàn tất. |
| Người dùng vẫn ghi về hệ cũ sau cutover | Hai nhánh dữ liệu bắt đầu tách nhau. | Write fence ở lớp thực thi, kiểm tra mọi entry point và quyền ghi; không chỉ sửa DNS. |
| Rollback sau khi đã có ghi mới | Giao dịch mới không có ở hệ cũ. | Reverse replication/replay được kiểm thử hoặc roll forward; luôn đối soát trước chuyển chủ. |

Các bài kiểm thử nên bao gồm sự kiện lặp, đảo thứ tự, mất kết nối, crash trước/sau commit, thay đổi schema, xóa, tải đỉnh, và cutover thất bại. Một lần demo nạp thành công không đủ chứng minh hệ thống có thể phục hồi.

## 10. Thiết kế theo Well-Architected

| Khía cạnh | Câu hỏi đánh giá cho giai đoạn chạy song song |
| --- | --- |
| **Operational Excellence (Vận hành hiệu quả)** | Có dashboard lag, backlog, đối soát, cảnh báo, runbook replay/cutover và người chịu trách nhiệm cho từng nguồn dữ liệu không? |
| **Reliability (Độ tin cậy)** | Khi mạng đứt hoặc consumer restart có replay được từ checkpoint không? Log retention và write fence có được thử nghiệm không? |
| **Security (Bảo mật)** | Kết nối có TLS, dữ liệu lưu có mã hóa, credential được xoay vòng, audit log có tránh rò rỉ PII và quyền ghi/đọc được phân tách không? |
| **Performance Efficiency (Hiệu quả hiệu năng)** | Pipeline chịu được tải ghi đỉnh, tốc độ catch up, giới hạn IOPS/CPU/network và skew giữa partition không? |
| **Cost Optimization (Tối ưu chi phí)** | Chi phí chạy hai hệ, egress liên vùng, lưu log lâu, stream/queue, đối soát và tài nguyên tạm có được đo và có ngày kết thúc không? |
| **Sustainability (Bền vững)** | Có tránh replay và backfill không cần thiết, chọn kích thước tài nguyên phù hợp và dỡ hạ tầng thừa khi hoàn tất không? |

Ngoài ra, dữ liệu có tính nhạy cảm cần đánh giá quyền truy cập theo vai trò, vị trí lưu trữ, sao lưu, thời hạn giữ, yêu cầu xóa và quy định xuyên biên giới áp dụng cho tổ chức. Đường đồng bộ có thể vô tình nhân bản dữ liệu nhạy cảm sang môi trường dùng thử nếu không thiết kế trước.

## 11. Bài tập thiết kế: di chuyển hệ thống đơn hàng

**Đề bài.** Hệ cũ xử lý đơn hàng tại data center. Hệ mới trên cloud dùng schema đã tách thành order và order_item. Trung bình có 200 thay đổi/giây, đỉnh 700 thay đổi/giây. Hệ cũ phải tiếp tục phục vụ ba tuần. Bộ phận vận hành muốn thử tính năng tra cứu đơn từ hệ mới trước khi chuyển ghi. Dữ liệu thanh toán không được ghi nhận hai lần; có đường truyền hybrid đôi lúc gián đoạn.

**Một phương án tham khảo:**

1. Xác định hệ cũ là owner ghi cho đơn hàng cho đến cutover; cấm hệ mới tự ghi trạng thái thanh toán từ dữ liệu replay. Chọn CDC một chiều và mapping có version cho schema đích.
2. Nạp snapshot nhất quán và phát lại CDC từ mốc đã chọn; xác thực khóa đơn, dòng hàng, phép chuyển đổi tiền và delete. Consumer áp dụng theo khóa đơn để giữ thứ tự và có bảng/khóa idempotency.
3. Sizing cho tải **đỉnh 700 thay đổi/giây** cộng công suất catch up sau gián đoạn; thử mạng mất kết nối đủ lâu, xác định log retention và cảnh báo trước khi hết cửa sổ replay.
4. Chạy shadow read; so sánh trạng thái, tổng tiền và số lượng dòng theo mốc. Khi phục vụ canary read, hiển thị hoặc xử lý lag theo yêu cầu UX; thao tác cần tính nhất quán mạnh truy vấn owner.
5. Ở cutover, fence ghi cũ, chốt watermark, đợi áp dụng hết, đối soát, rồi chuyển owner. Chuẩn bị sẵn chiến lược roll forward hoặc reverse sync đã kiểm chứng cho các giao dịch phát sinh sau chuyển quyền.

**Câu hỏi tự kiểm tra:**

1. Nếu consumer xử lý được 600 thay đổi/giây khi tải nguồn đang 700 thay đổi/giây, backlog sẽ biến đổi thế nào?
2. Vì sao hai bảng có cùng số dòng chưa đủ chứng minh di chuyển thành công?
3. Nếu CDC báo lag bằng 0 nhưng DLQ vẫn có lỗi, đã đủ điều kiện cutover chưa?
4. Khi người dùng đã tạo đơn mới ở cloud, có thể chỉ trỏ DNS về hệ cũ để rollback an toàn không?
5. Nếu dữ liệu tham chiếu có thể trễ 10 phút nhưng xác nhận thanh toán yêu cầu quyết định tức thời, bạn sẽ phân chia owner và luồng đọc/ghi thế nào?

**Gợi ý đáp án:** (1) backlog tăng khoảng 100 thay đổi/giây nếu các tốc độ duy trì; (2) còn phải đối chiếu nội dung, bất biến nghiệp vụ và cùng mốc; (3) chưa, cần xử lý và replay dữ liệu lỗi; (4) không, phải bảo toàn dữ liệu ghi mới hoặc chọn roll forward; (5) dữ liệu tham chiếu có thể nhận bản sao trễ, còn lệnh thanh toán phải đi qua hệ thống có thẩm quyền và chống trùng ở mức nghiệp vụ.

## 12. Checklist trước khi cho phép cutover

- [ ] Owner ghi và phạm vi dữ liệu đã được xác định, có cơ chế write fence thực thi được.
- [ ] Snapshot và CDC dùng mốc nhất quán; đã thử replay sau gián đoạn và restart.
- [ ] Insert, update, delete, schema change, duplicate và out-of-order được xử lý hoặc có giới hạn được ghi rõ.
- [ ] Backlog, lag, DLQ và vị trí stream có giám sát/cảnh báo; capacity đáp ứng tải đỉnh.
- [ ] Đối soát cùng watermark đạt tiêu chí đã thống nhất; không còn lỗi dữ liệu quan trọng chưa điều tra.
- [ ] Bảo mật đường truyền, quyền truy cập, lưu log, dữ liệu nhạy cảm và chi phí chạy song song đã được kiểm tra.
- [ ] Runbook cutover có bước chặn ghi, chốt mốc, xác minh, chuyển quyền, smoke test và điều kiện dừng.
- [ ] Kế hoạch rollback/roll forward xử lý được **mọi ghi phát sinh sau cutover**; đã diễn tập với dữ liệu thử.
- [ ] Có người chịu trách nhiệm, bằng chứng nghiệm thu, thời hạn giữ hệ cũ và kế hoạch thu hồi tài nguyên.

Điểm mấu chốt của đồng bộ trong giai đoạn chạy song song là **quản trị quyền ghi, vị trí thay đổi và bằng chứng đối soát**. Công cụ CDC giúp vận chuyển dữ liệu, còn kiến trúc phải chứng minh được dữ liệu không bị mất hoặc áp dụng sai, nghiệp vụ vẫn nhất quán, và tổ chức có thể chuyển đổi hoặc phục hồi theo các điều kiện đã kiểm thử.
