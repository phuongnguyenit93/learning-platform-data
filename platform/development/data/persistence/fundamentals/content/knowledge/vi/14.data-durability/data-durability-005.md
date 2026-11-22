# Nguyên tắc ghi nhật ký trước (write-ahead logging)

Một giao dịch có thể báo **COMMIT thành công** trong khi một phần trang dữ liệu liên quan vẫn còn trong bộ nhớ. Nếu máy chủ mất điện ngay lúc đó, vì sao cơ sở dữ liệu vẫn có thể phục hồi những thay đổi đã được xác nhận? Câu trả lời nằm ở cơ chế **write-ahead logging (WAL)**: ghi thông tin cần thiết để phục hồi vào một nhật ký bền vững **trước** khi cho phép ghi trang dữ liệu tương ứng xuống nơi lưu trữ, và đồng bộ nhật ký commit theo mức bảo đảm đã chọn.

Bài học thuộc chương **Độ bền dữ liệu** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Người học đang xây dựng nền tảng persistence cho Java, từ lược đồ, truy vấn và chỉ mục đến giao dịch, cô lập, xử lý lỗi kết nối, sao lưu và tối ưu hiệu năng. Bài dùng **PostgreSQL** làm ví dụ kỹ thuật chính, đồng thời chỉ rõ những điểm khác nhau giữa các hệ quản trị như InnoDB. Không nên áp nguyên cấu trúc tệp log, thuật toán khôi phục hoặc ngữ nghĩa tùy chọn cấu hình của PostgreSQL cho mọi hệ lưu trữ.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích vì sao cơ sở dữ liệu không cần ghi đồng bộ tất cả trang dữ liệu ngay trong mỗi lần COMMIT.
- Phát biểu đúng **quy tắc ghi nhật ký trước** và phân biệt **ghi vào bộ đệm, ghi xuống hệ điều hành, đồng bộ tới lưu trữ bền vững**.
- Mô tả tác dụng của **log record, log sequence number (LSN), commit record, checkpoint và redo** khi khôi phục sau crash.
- Phân biệt bảo đảm độ bền của một giao dịch đã commit với **rollback**, **backup**, **replication**, **point-in-time recovery (PITR)** và **idempotency**.
- Nhận diện các đánh đổi giữa độ trễ commit, tính bền vững và lượng ghi WAL; biết những chỉ số nên quan sát trong PostgreSQL.
- Thiết kế cách xử lý lỗi Java khi kết nối mất trước lúc nhận được phản hồi COMMIT.

## 2. Vấn đề cốt lõi: bộ nhớ và đĩa không được cập nhật đồng thời

Một hệ quản trị cơ sở dữ liệu thường giữ các trang dữ liệu được truy cập trong **buffer pool/shared buffers**. Cập nhật một hàng có thể sửa trang trong bộ nhớ và đánh dấu trang ấy là **dirty page**. Cơ chế ghi trang dữ liệu xuống đĩa thường hoạt động theo lô, dựa trên áp lực bộ nhớ, checkpoint và quyết định của tiến trình nền.

Giả sử một giao dịch sửa hai trang dữ liệu:

~~~text
                  Bộ nhớ của database
                  +-------------------+
Transaction T1 -->| page A: đã đổi    |----> file dữ liệu trên đĩa
                  | page B: đã đổi    |----> file dữ liệu trên đĩa
                  +-------------------+

                        Có thể ghi ở các thời điểm khác nhau
~~~

Nếu buộc COMMIT phải chờ cả hai trang dữ liệu được ghi trực tiếp và đồng bộ tới đĩa, việc ghi có thể phân tán trên nhiều vị trí lưu trữ, tốn I/O và kéo dài độ trễ. Nếu trả lời COMMIT trước khi bất kỳ thông tin phục hồi nào được giữ bền vững, máy mất điện có thể khiến thay đổi biến mất.

**WAL giải quyết mâu thuẫn này bằng cách đưa một nhật ký thay đổi có thứ tự vào đường ghi.** Các bản ghi nhật ký cho phép hệ quản trị phát lại phần dữ liệu cần thiết khi file dữ liệu chưa theo kịp giao dịch đã commit.

Ví dụ hình dung:

~~~text
Ứng dụng Java              PostgreSQL                         Lưu trữ
     |                         |                                |
     |--- UPDATE ------------->| thay đổi trang trong memory    |
     |                         | tạo WAL record                 |
     |--- COMMIT ------------->| ghi/flush WAL cần thiết ------>| WAL bền vững
     |<-- COMMIT thành công ---|                                |
     |                         | có thể ghi data page sau ----->| file dữ liệu
~~~

Đây là mô hình cho một giao dịch được xác nhận đồng bộ theo cấu hình bền vững phù hợp. Thứ tự thực tế giữa cập nhật trang trong bộ nhớ, tạo bản ghi WAL, gửi lệnh ghi và flush có thể xen kẽ; điểm quyết định là các **ràng buộc về thứ tự và độ bền**, không phải từng ô trong sơ đồ bắt buộc diễn ra theo một thứ tự thời gian duy nhất.

## 3. Hai quy tắc cần nhớ của write-ahead logging

### 3.1. WAL phải bền vững trước khi trang dữ liệu chứa thay đổi tương ứng được ghi

**Quy tắc write-ahead:** trước khi một trang dữ liệu đã sửa được ghi xuống nơi lưu trữ bền vững, các bản ghi WAL cần thiết để phục hồi thay đổi trên trang ấy phải được đưa tới mức lưu trữ bền vững theo yêu cầu của hệ quản trị.

Trong thuật ngữ LSN:

~~~text
Data page P có pageLSN = 250
              |
              v
Trước khi ghi phiên bản đó của P xuống đĩa:
  WAL phải đã được flush tối thiểu qua LSN 250.
~~~

Điều này cần thiết vì một trang có thể được ghi trước khi giao dịch sửa nó commit. Nếu máy chủ crash và trang chứa thay đổi chưa commit, hệ quản trị vẫn phải có đủ thông tin nhật ký và trạng thái giao dịch để phục hồi nhất quán. Trong một số thuật toán, WAL còn đi cùng dữ liệu để **undo**; trong PostgreSQL, việc phiên bản hàng chưa commit có được nhìn thấy hay không phụ thuộc thông tin transaction/MVCC và các bước cleanup phù hợp, chứ không đơn giản là ghi trực tiếp phép trừ ngược lên mọi trang.

### 3.2. Commit được xác nhận theo mức đồng bộ nhật ký đã chọn

Ở chế độ commit bền vững đồng bộ, hệ quản trị cần ghi và **flush** bản ghi liên quan tới việc commit trước khi trả về kết quả thành công cho client. Trong PostgreSQL cấu hình bền vững thông thường, **synchronous_commit = on** yêu cầu WAL được flush cục bộ trước khi báo commit thành công; nếu cấu hình synchronous replication, điều kiện chờ máy dự phòng còn tùy chế độ và topology.

Điểm quan trọng:

- **UPDATE hoàn tất** không đồng nghĩa cả giao dịch đã commit.
- **WAL record được tạo trong RAM** không đồng nghĩa nó đã bền vững qua mất điện.
- **COMMIT được xác nhận** có độ bền phụ thuộc cấu hình đồng bộ log và các giả định về hệ điều hành, thiết bị lưu trữ.
- **Trang dữ liệu được ghi sau COMMIT** không làm mất độ bền nếu nhật ký cần thiết đã được lưu và có thể phục hồi.

Không nên giản lược WAL thành “ghi log trước lệnh UPDATE”: nguyên tắc chính liên quan tới **flush log so với flush data page** và **điều kiện xác nhận giao dịch**, chứ không nhất thiết một lệnh INSERT log bằng SQL diễn ra trước mọi thay đổi trong RAM.

## 4. Phân biệt write, flush và fsync

Từ “ghi” dễ gây nhầm vì dữ liệu có thể đi qua nhiều tầng:

| Tầng | Điều gì đã xảy ra? | Bảo đảm khi mất điện? |
| --- | --- | --- |
| **WAL buffer của DB** | WAL record tồn tại trong bộ nhớ tiến trình | Không đủ |
| **Đã gọi write tới hệ điều hành** | Dữ liệu có thể ở page cache của kernel hoặc thiết bị | Chưa thể coi là bền vững chỉ vì write trả thành công |
| **Đã đồng bộ theo cơ chế flush/fsync phù hợp** | Hệ điều hành/thiết bị được yêu cầu đưa dữ liệu qua ranh giới độ bền đã cam kết | Có cơ sở để xác nhận độ bền, trong giới hạn thiết bị và cấu hình |
| **Data page được ghi xuống file dữ liệu** | File dữ liệu đã theo kịp một số thay đổi | Không thay thế các quy tắc WAL/commit |

Trong thực tế, DB có thể sử dụng **fsync, fdatasync, open_datasync, open_sync** hoặc phương thức tương đương tùy hệ điều hành và tùy chọn. Thiết bị lưu trữ phải thực hiện đúng cam kết về cache, flush và thứ tự ghi. Khi thiết bị nói đã đồng bộ nhưng thực tế chỉ để dữ liệu trong cache dễ mất điện, bảo đảm của hệ quản trị cũng không thể tuyệt đối.

Hãy hình dung WAL là một cuốn nhật ký phục hồi có thứ tự. **Viết một dòng lên giấy nháp trong RAM** khác với **đưa dòng đó vào nơi lưu trữ được phép tin là vẫn còn sau crash**.

## 5. WAL record và LSN biểu diễn điều gì?

Mỗi bản ghi WAL mô tả thông tin phục hồi cho một hành động mà DB cần ghi nhớ, chẳng hạn thay đổi trang, metadata liên quan, hoặc trạng thái commit của một transaction. PostgreSQL dùng **log sequence number (LSN)** để xác định vị trí trong dòng WAL và để nói các thành phần đã tiến triển tới đâu.

Một ví dụ giả lập, **không phải định dạng WAL thật**:

~~~text
LSN       Transaction    Ý nghĩa minh họa
100       T1             UPDATE hàng tài khoản 101
130       T1             UPDATE hàng tài khoản 202
155       T2             INSERT bản ghi nhật ký truy cập
180       T1             COMMIT T1
210       T2             COMMIT T2
~~~

LSN tăng theo vị trí trong WAL; chúng không phải ID nghiệp vụ hoặc timestamp lịch. Các giá trị trong bảng chỉ để hình dung sự sắp xếp, không phải LSN PostgreSQL thực có dạng số thập phân đơn.

Một data page có thể được liên kết với LSN của bản ghi WAL mới nhất mô tả phiên bản trang ấy. Khi recovery, hệ quản trị có thể dùng trạng thái trang và WAL để quyết định thay đổi nào cần phát lại hoặc đã được áp dụng. Cách dùng page LSN, redo record, checksum, full-page image và bước khôi phục cụ thể thuộc về thuật toán của DBMS.

Không suy rằng WAL luôn lưu bản sao đầy đủ của cả hàng hoặc mọi câu SQL gốc. WAL ở PostgreSQL thường chứa thông tin phục hồi ở mức cấu trúc lưu trữ, có thể bao gồm ảnh trang đầy đủ trong tình huống thích hợp. **Logical replication** và **audit log SQL/nghiệp vụ** là những lớp thông tin khác với WAL phục hồi vật lý.

## 6. Dòng thời gian một giao dịch và các điểm có thể crash

Giả sử chuyển 100 đơn vị tiền giữa hai tài khoản bằng transaction T1. Ứng dụng gửi:

~~~sql
BEGIN;
UPDATE accounts SET balance = balance - 100
WHERE id = 101 AND balance >= 100;
UPDATE accounts SET balance = balance + 100
WHERE id = 202;
COMMIT;
~~~

**Đây là minh họa ranh giới giao dịch**, không phải script sản xuất hoàn chỉnh: phải kiểm tra mỗi UPDATE tác động đúng một hàng, kiểm tra quyền và các ràng buộc trước khi COMMIT.

Có thể hình dung các bước liên quan tới WAL:

~~~text
t0  BEGIN T1
t1  Sửa trang trong bộ nhớ, tạo WAL record cho UPDATE #1
t2  Sửa trang trong bộ nhớ, tạo WAL record cho UPDATE #2
t3  Tạo WAL record ghi nhận commit T1
t4  Flush WAL qua vị trí cần thiết cho T1
t5  DB trả COMMIT thành công (với cấu hình commit đồng bộ phù hợp)
t6  Data pages có thể tiếp tục được ghi xuống đĩa trong nền
~~~

Các mốc trên là mô hình học tập: WAL có thể được ghi/flush sớm hơn t4, từng trang dữ liệu có thể được ghi sớm sau khi WAL tương ứng đã bền vững, và nhiều transaction có thể dùng chung một đợt flush. Vì vậy, điều cần kiểm tra là **các điều kiện trước-sau**, không phải bắt DB đi đúng từng dòng của sơ đồ.

### 6.1. Nếu crash trước khi commit được xác nhận?

Không thể chỉ nhìn từ phía client để kết luận transaction đã commit hay rollback. Nếu crash trước khi DB thực sự có commit record bền vững, recovery sẽ xử lý nó như transaction chưa hoàn tất theo cơ chế của hệ. Nhưng nếu commit đã được flush và chỉ **phản hồi mạng** bị mất, transaction có thể đã bền vững dù client thấy lỗi.

### 6.2. Nếu crash sau khi commit được xác nhận?

Với cấu hình đảm bảo commit đồng bộ trên lưu trữ hoạt động đúng, WAL cần thiết đã bền vững. Sau khởi động lại, DB có thể **redo** những thay đổi đã được commit nhưng data pages chưa kịp ghi. Ứng dụng không cần ép cả hai data page xuống đĩa trong transaction chỉ để có cơ chế khôi phục này.

## 7. Recovery: tại sao cần redo, và undo được thực hiện thế nào?

Sau crash, phần RAM của DB mất đi. File dữ liệu trên đĩa có thể ở các thời điểm khác nhau:

- Trang A đã chứa thay đổi mới, trang B chưa được cập nhật.
- Một trang có thể chứa dữ liệu từ transaction chưa commit vì nó đã được ghi ra trước khi transaction kết thúc.
- WAL đã bền vững chứa các record đủ để hệ quản trị đưa cấu trúc lưu trữ về trạng thái nhất quán theo thuật toán.

### Redo

**Redo** là việc phát lại thay đổi cần thiết từ nhật ký để tái lập trạng thái lưu trữ sau crash. Một trang chưa theo kịp WAL có thể được cập nhật qua redo, kể cả khi trang đó chưa từng được ghi ra file dữ liệu trước crash.

### Undo và trạng thái transaction

**Undo** là logic hủy ảnh hưởng của thao tác chưa commit. Nhưng không phải mọi DBMS thực hiện undo vật lý theo cùng một cơ chế:

- Trong các mô hình recovery kiểu **ARIES**, thường học ba pha analysis, redo và undo; các thông tin log hỗ trợ phát lại và hoàn tác các transaction chưa commit.
- **PostgreSQL** dùng WAL cùng cơ chế transaction status, MVCC và xử lý phiên bản hàng. Trong crash recovery, nó phát lại các WAL record cần thiết và dùng trạng thái commit/abort để quyết định phiên bản nào hợp lệ với truy vấn; những phiên bản không còn cần được cơ chế dọn dẹp xử lý. Không nên mô tả PostgreSQL như thể luôn có một pha undo WAL vật lý giống hệt ARIES.
- **InnoDB** có các cấu trúc redo và undo riêng phục vụ phục hồi và MVCC; không đồng nhất tệp redo log của InnoDB với WAL segment của PostgreSQL.

Khái niệm chung là **chỉ các kết quả transaction đủ điều kiện commit mới trở thành trạng thái dữ liệu hợp lệ sau recovery**. Cách đạt được điều đó phụ thuộc thiết kế nội bộ của từng hệ quản trị.

## 8. Checkpoint: giới hạn công việc khôi phục

Nếu khởi động lại phải đọc toàn bộ WAL từ ngày hệ thống được tạo, recovery sẽ quá tốn thời gian. Cơ sở dữ liệu vì vậy sử dụng **checkpoint** để ghi nhận tiến độ đồng bộ trạng thái dữ liệu và tạo mốc phục hồi phù hợp.

~~~text
Dòng WAL:
  ---- cũ ---- [CHECKPOINT] ---- các WAL record mới ----> hiện tại
                         |
             recovery có thể bắt đầu
             từ mốc phù hợp được ghi nhận
~~~

Checkpoint trong PostgreSQL không nên hiểu đơn giản là một lệnh “ngừng mọi giao dịch, rồi ghi mọi thứ cùng lúc”. Hệ thống có thể trải việc ghi trang bẩn theo thời gian. Checkpoint còn ghi metadata cần thiết để xác định điểm bắt đầu redo phù hợp; **checkpoint record** và **redo start LSN** không nhất thiết là cùng một vị trí.

Hai đánh đổi quan trọng:

1. **Checkpoint quá thường xuyên** có thể tạo áp lực I/O, thúc đẩy ghi dirty pages sớm và tăng lượng **full-page images** cần ghi theo cấu hình, làm tăng write amplification.
2. **Checkpoint quá thưa** có thể khiến nhiều dữ liệu cần redo hơn khi crash, ảnh hưởng thời gian khởi động phục hồi và lượng WAL cần giữ.

Các tham số PostgreSQL như **checkpoint_timeout**, **max_wal_size** và **checkpoint_completion_target** ảnh hưởng nhịp checkpoint và phân bổ I/O; nhưng **max_wal_size là mục tiêu mềm**, WAL có thể vượt mức này trong một số điều kiện như replication slot, archiving hoặc tăng tải. Không dùng việc xóa tệp thủ công trong **pg_wal** để giải quyết dung lượng.

## 9. Tại sao WAL có thể ghi nhanh hơn ghi data page?

WAL tổ chức các record theo **một dòng thứ tự ghi**. Việc gom dữ liệu thành các lượt ghi tương đối tuần tự có thể thân thiện với thiết bị lưu trữ hơn cập nhật trực tiếp nhiều data pages nằm rải rác.

Một kỹ thuật quan trọng là **group commit**:

~~~text
T1 COMMIT ----+
T2 COMMIT ----+--> cùng một đợt WAL flush --> trả kết quả cho các transaction
T3 COMMIT ----+
~~~

Thay vì mỗi transaction đều phải yêu cầu một lượt đồng bộ vật lý riêng, DB có thể gom nhiều transaction để chia sẻ chi phí flush. Điều này đặc biệt có lợi khi rất nhiều transaction ngắn cùng commit.

**WAL không miễn phí**: mỗi thay đổi còn có chi phí tạo record, ghi WAL, đồng bộ, ghi data page về sau, và có thể tạo thêm I/O do full-page image hoặc chỉ mục được cập nhật. Lợi ích là cơ chế điều phối độ bền, khôi phục và hiệu năng tổng thể, không phải mọi workload sẽ tự động nhanh hơn chỉ vì có WAL.

## 10. Full-page writes và nguy cơ trang bị ghi dở

Một số thiết bị hoặc hệ điều hành có thể ghi một trang dữ liệu thành nhiều thao tác vật lý. Nếu mất điện giữa lúc ghi, trang trên đĩa có thể chứa một phần dữ liệu cũ và một phần dữ liệu mới, thường gọi là **torn page**.

PostgreSQL có cơ chế **full_page_writes**: ở những thời điểm phù hợp, đặc biệt khi một trang được sửa lần đầu sau checkpoint, WAL có thể chứa **full-page image** để giúp phục hồi trang khi cần. Điều này tăng lượng WAL nhưng bảo vệ trước một lớp lỗi ghi dở.

Lưu ý:

- **full_page_writes** không phải sao lưu từng trang tại mọi lần UPDATE.
- Tắt nó để giảm WAL có thể làm tăng nguy cơ không thể phục hồi sau crash nếu hạ tầng lưu trữ không cung cấp bảo đảm tương đương.
- Checksum, page images và khôi phục WAL có mục đích liên quan nhưng khác nhau; không thể chọn ngẫu nhiên một trong các cơ chế rồi coi mọi nguy cơ hỏng dữ liệu đã được loại bỏ.

Quyết định đổi thiết lập độ bền phải dựa trên tài liệu DBMS, hệ điều hành, thiết bị lưu trữ và chính sách phục hồi của hệ thống.

## 11. Đọc cấu hình và thống kê WAL trong PostgreSQL

Trên môi trường được phép quan sát, có thể truy vấn các tham số:

~~~sql
SHOW fsync;
SHOW synchronous_commit;
SHOW full_page_writes;
SHOW wal_level;
SHOW archive_mode;
SHOW checkpoint_timeout;
SHOW max_wal_size;
~~~

Ý nghĩa tổng quát:

| Thiết lập | Vai trò |
| --- | --- |
| **fsync** | Có yêu cầu đồng bộ dữ liệu cần thiết tới lưu trữ bền vững bằng cơ chế hệ điều hành hay không |
| **synchronous_commit** | Điều kiện ghi/flush WAL và, khi có cấu hình, điều kiện đồng bộ với standby trước khi trả COMMIT |
| **full_page_writes** | Hỗ trợ phục hồi an toàn trước nguy cơ torn page bằng ảnh trang trong WAL ở những tình huống phù hợp |
| **wal_level** | Lượng thông tin WAL để đáp ứng nhu cầu phục hồi/replication/logical decoding; không phải công tắc duy nhất bật hoặc tắt độ bền |
| **archive_mode** | Có bật cơ chế lưu trữ WAL để phục hồi/sử dụng ngoài vòng đời WAL trực tiếp hay không |
| **checkpoint_timeout** | Khoảng thời gian mục tiêu giữa checkpoint |
| **max_wal_size** | Mục tiêu dung lượng WAL để kích hoạt checkpoint; không phải giới hạn cứng |

Có thể xem thống kê tổng hợp (các cột phụ thuộc phiên bản PostgreSQL):

~~~sql
SELECT wal_records,
       wal_fpi,
       wal_bytes,
       wal_write,
       wal_sync,
       stats_reset
FROM pg_stat_wal;
~~~

**wal_records** là số record, **wal_fpi** là số full-page images, **wal_bytes** là lượng WAL tạo ra, còn **wal_write/wal_sync** giúp quan sát tần suất tương ứng. Đây là **bộ đếm tích lũy từ lần reset thống kê**; để đo tốc độ, cần lấy độ chênh ở hai thời điểm và chia cho khoảng thời gian, không chỉ đọc một giá trị lớn rồi kết luận hệ thống đang có lỗi.

Ví dụ có thể xem vị trí WAL hiện tại:

~~~sql
SELECT pg_current_wal_lsn();
~~~

Hàm trên cho biết vị trí WAL hiện tại ở primary theo ngữ nghĩa của PostgreSQL; **không được coi giá trị này là bằng chứng mọi WAL đến vị trí đó đã được flush bền vững hoặc một standby đã replay tới đó**. Khi cần đo độ trễ replication, phải sử dụng các vị trí write/flush/replay và số liệu standby tương ứng.

Các thao tác chỉ đọc nói trên có thể bị giới hạn bởi quyền DB hoặc phiên bản. Không tự ý thay đổi **fsync**, **synchronous_commit**, **full_page_writes** hay xóa WAL segment trong lúc quan sát hệ thống thật.

## 12. synchronous_commit và mức độ bền vững của COMMIT

PostgreSQL có các tùy chọn để thay đổi mức độ chờ trước khi xác nhận transaction. Một cách so sánh thực dụng:

| Tình huống | Khi COMMIT trả về thành công |
| --- | --- |
| **synchronous_commit = on**, cấu hình local thông thường | WAL cần thiết đã được flush cục bộ; điều kiện standby tùy cấu hình replication đồng bộ |
| **synchronous_commit = off** | DB có thể trả thành công trước khi WAL của transaction đó được flush; crash có thể làm mất một số commit vừa được xác nhận |
| **Remote replication đồng bộ được cấu hình** | Có thể chờ standby nhận, flush hoặc apply, tùy mức đồng bộ chọn; cần xem chính xác chế độ |

**synchronous_commit = off** có thể giảm độ trễ một số transaction nhưng cho phép mất các transaction vừa được xác nhận khi database crash. Thông thường PostgreSQL vẫn giữ tính nhất quán của cơ sở dữ liệu sau crash; rủi ro ở đây là **mất độ bền của một số commit**, không phải lời hứa rằng mọi dữ liệu khác chắc chắn nguyên vẹn dưới mọi lỗi hạ tầng.

Ngược lại, **fsync = off** làm yếu đi nền tảng đồng bộ dữ liệu trên lưu trữ và có thể dẫn đến **hỏng dữ liệu không phục hồi được** khi gặp crash. Không xem hai tùy chọn này như hai cách tăng tốc có rủi ro giống nhau.

Đối với nghiệp vụ khác nhau, yêu cầu độ bền cũng khác:

- **Chuyển tiền, sổ cái, thanh toán:** thường yêu cầu xác nhận commit bền vững, idempotency và quy trình đối soát.
- **Thống kê lượt xem hoặc telemetry có thể tái tạo:** có thể chấp nhận mất một phần nhỏ dữ liệu gần nhất nếu được quy định rõ.
- **Quá trình nhập dữ liệu theo lô:** có thể thiết kế điểm tiếp tục (checkpoint ở tầng ứng dụng) và khả năng chạy lại, nhưng phải kiểm soát tác động lặp.

Không dùng việc giảm bảo đảm đồng bộ để chữa một truy vấn chậm mà nguyên nhân là chỉ mục, khóa hoặc thiết kế transaction.

## 13. WAL, replication, archiving và backup khác nhau thế nào?

WAL là thành phần quan trọng của nhiều cơ chế khác, nhưng mỗi cơ chế giải quyết một mục tiêu:

| Cơ chế | Mục đích chính | Giới hạn cần nhớ |
| --- | --- | --- |
| **WAL cục bộ** | Khôi phục nhất quán sau crash và hỗ trợ các cơ chế liên quan | Không tự thay thế backup khi ổ đĩa mất hoàn toàn |
| **Streaming replication** | Chuyển thay đổi đến standby phục vụ tính sẵn sàng/đọc | Replication có thể có độ trễ; xóa nhầm và lỗi nghiệp vụ cũng có thể được sao chép |
| **WAL archiving** | Giữ lịch sử WAL cần thiết ngoài vòng quay tệp cục bộ | Cần archive hoạt động đúng và kiểm tra liên tục |
| **Base backup + chuỗi WAL phù hợp** | Phục hồi dữ liệu tới thời điểm/điểm log mong muốn trong phạm vi được lưu | Thiếu WAL hoặc backup không tương thích sẽ làm phục hồi thất bại |
| **Backup độc lập, ngoại tuyến** | Bảo vệ trước mất máy, hỏng thiết bị, thao tác xóa, ransomware theo chính sách | Phải có kiểm thử restore và kiểm soát truy cập |

### 13.1. Point-in-time recovery (PITR)

Một quy trình PostgreSQL có thể dùng **base backup** và **WAL archive** để khôi phục đến thời điểm phù hợp:

~~~text
Base backup lúc 01:00
       |
       +--- WAL archive 01:00 ... 01:30 ... 02:00
                                         |
                           Có thể chọn mốc phục hồi
                           trong phạm vi WAL liên tục có sẵn
~~~

WAL không tự là bản sao độc lập của toàn bộ dữ liệu. Base backup tạo nền, các WAL record cho phép đưa nền đó tiến tới mục tiêu; thiếu đoạn WAL quan trọng trong chuỗi có thể làm phương án PITR không thực hiện được.

### 13.2. RPO và RTO

- **RPO (Recovery Point Objective):** mức mất dữ liệu tối đa mà doanh nghiệp chấp nhận sau sự cố, ví dụ tối đa vài phút thay đổi.
- **RTO (Recovery Time Objective):** thời gian tối đa mục tiêu để khôi phục dịch vụ.

WAL là một phần của câu trả lời, nhưng **RPO/RTO phụ thuộc toàn bộ kiến trúc**: backup, archive, replication, vùng lỗi chung, tốc độ restore, lượng WAL phải replay, quy trình failover và năng lực vận hành. Không kết luận “đã bật WAL nên RPO = 0, RTO = 0”.

### 13.3. Không quản lý WAL bằng cách xóa thủ công

WAL segment có thể cần cho crash recovery, archiving, replication slot hoặc standby đang chậm. Nếu thư mục WAL tăng nhanh, cần tìm nguyên nhân như archive thất bại, slot giữ WAL quá lâu, checkpoint, replication lag hoặc tải ghi tăng. **Xóa trực tiếp tệp đang được PostgreSQL quản lý có thể phá hỏng khả năng khôi phục.** Hãy dùng các công cụ và quy trình chính thức của hệ quản trị, với đánh giá tác động trước khi thay đổi.

## 14. WAL và xử lý lỗi kết nối trong ứng dụng Java

WAL giải quyết khả năng khôi phục của database, nhưng không đảm bảo một client Java luôn biết được **COMMIT đã thành công hay chưa**. Hai chuỗi sự kiện có thể đem lại cùng một lỗi phía ứng dụng:

~~~text
Trường hợp A:
  Java gửi COMMIT -> kết nối đứt -> DB chưa commit

Trường hợp B:
  Java gửi COMMIT -> DB flush WAL -> COMMIT thành công
  -> phản hồi bị mất -> Java nhận lỗi kết nối
~~~

Sau khi nhận lỗi mạng, ứng dụng không thể chỉ dùng exception để phân biệt A và B. Nếu tự động chạy lại thao tác cộng điểm, trừ tiền hoặc tạo đơn, nó có thể thực hiện **hai lần**.

Giải pháp cần có ở tầng nghiệp vụ:

1. Gắn một **request_id** ổn định cho một thao tác có ý nghĩa nghiệp vụ.
2. Dùng **UNIQUE constraint** trên phạm vi định danh thích hợp, ví dụ (**tenant_id**, **request_id**).
3. Ghi kết quả xử lý yêu cầu và các thay đổi dữ liệu trong **cùng transaction**.
4. Khi timeout/commit không rõ trạng thái, kết nối mới có thể **đối chiếu request_id** và quyết định trả kết quả đã tồn tại hay thực hiện lại một cách an toàn.
5. Nếu payload của cùng request ID khác nội dung gốc, phải báo xung đột hoặc xử lý theo chính sách, không coi đó là cùng một yêu cầu.

Trong Java JDBC, ranh giới giao dịch nên rõ ràng:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class PaymentRepository {
    private final DataSource dataSource;

    public PaymentRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void recordPayment(long paymentId, long amount) throws SQLException {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount phải dương");
        }

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try (PreparedStatement statement = connection.prepareStatement(
                    """
                    INSERT INTO payments(payment_id, amount)
                    VALUES (?, ?)
                    """)) {
                statement.setLong(1, paymentId);
                statement.setLong(2, amount);
                statement.executeUpdate();
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

Ví dụ trên **chỉ minh họa transaction boundary**, giả định bảng **payments** đã có và **payment_id** là khóa duy nhất. Nó chưa triển khai cơ chế idempotency đầy đủ, đối soát sau commit không rõ kết quả hoặc các kiểm tra nghiệp vụ thanh toán. Nếu lỗi xảy ra ở **connection.commit()**, cố gắng rollback có thể thất bại, hoặc không thể thu hồi một commit server đã thực hiện. Vì vậy, lớp điều phối vẫn cần **định danh yêu cầu và kiểm tra trạng thái từ kết nối mới** trước khi retry.

Với Spring **@Transactional**, transaction manager làm nhiệm vụ commit/rollback cho các repository tham gia cùng tài nguyên. Khi method trả thành công mà phản hồi HTTP bị mất, phía client vẫn có thể gửi lại request. **@Transactional không tự cung cấp exactly-once cho API**, cũng không thay thế định danh yêu cầu.

## 15. Khi WAL đủ và khi phải có thêm cơ chế khác

| Yêu cầu | WAL có hỗ trợ không? | Cần thêm gì? |
| --- | --- | --- |
| Khôi phục sau tiến trình DB crash | Có, cùng checkpoint và quy trình recovery | Cấu hình flush đúng, lưu trữ đáng tin cậy, kiểm thử restart |
| Không mất giao dịch vừa commit thành công trong crash cục bộ | Có theo cấu hình commit đồng bộ thích hợp | fsync và thiết bị thực hiện đúng bảo đảm |
| Không mất dữ liệu khi mất toàn bộ ổ đĩa/máy chủ | WAL cục bộ đơn lẻ không đủ | Backup ngoài vùng lỗi, replica hoặc WAL archive phù hợp |
| Không mất dữ liệu do xóa nhầm hàng đã commit | WAL cục bộ không tự hoàn tác sau commit | Backup/PITR hoặc nghiệp vụ khôi phục có kiểm soát |
| Không thực hiện thanh toán hai lần khi client retry | Không | Idempotency key, unique constraint, đối soát |
| DB và message broker ghi thành công cùng nhau | Không với local transaction đơn lẻ | Transactional outbox hoặc cơ chế phối hợp thích hợp |
| Đọc ngay kết quả mới nhất trên read replica | Không tự bảo đảm | Chọn read consistency, quan sát replication lag |
| Không lộ dữ liệu nhạy cảm từ tệp WAL/backup | Không | Quyền truy cập, mã hóa, quản lý khóa và vòng đời dữ liệu |

WAL còn là nguồn thông tin phục hồi có thể chứa dữ liệu nhạy cảm ở mức lưu trữ. Vì vậy, bảo mật backup, archive và nơi đặt WAL phải được xem là một phần của bảo mật dữ liệu, không phải chỉ là nhiệm vụ hiệu năng.

## 16. Hiệu năng, dung lượng và dấu hiệu cần quan sát

Việc tạo và flush WAL tiêu tốn băng thông ghi, CPU, thiết bị lưu trữ và thời gian commit. Những biểu hiện thường gặp:

- **Commit latency cao:** có thể do flush WAL chậm, fsync, tranh chấp I/O, transaction rất nhỏ nhưng commit liên tục, hoặc chờ synchronous standby; cần đo trước khi kết luận.
- **wal_bytes tăng đột biến:** có thể do cập nhật hàng loạt, tạo chỉ mục, bulk load, nhiều full-page images sau checkpoint, hoặc workload thay đổi.
- **WAL segment không được tái sử dụng như kỳ vọng:** có thể do archiving, replication slot, standby chậm, checkpoint hoặc các cơ chế giữ WAL.
- **Thời gian recovery tăng:** có thể liên quan lượng WAL cần replay, tốc độ thiết bị, số thay đổi đang chờ khôi phục và cấu hình checkpoint.
- **I/O tăng vào giờ cao điểm:** có thể do checkpoint, flush data pages và áp lực WAL cùng tranh thiết bị.

Quy trình xử lý đáng tin cậy:

1. Ghi nhận sự cố hoặc SLO: commit p95/p99, tần suất timeout, thời gian startup recovery, lượng WAL sinh mỗi phút.
2. Đối chiếu số liệu DB với hệ điều hành và thiết bị: IOPS, write latency, dung lượng, hiệu năng flush, lỗi storage.
3. Phân biệt **WAL generation**, **WAL write/flush**, **data-page write**, **archiving** và **replication lag**; một chỉ số đơn lẻ không nói hết nguyên nhân.
4. Kiểm tra pattern ứng dụng: transaction quá dài, batch quá nhỏ, câu SQL cập nhật thừa, chỉ mục không cần thiết hoặc làm việc ngoài DB trong transaction.
5. Chỉ thay đổi cấu hình độ bền sau khi xác định yêu cầu mất dữ liệu chấp nhận được, đo tác động và có kế hoạch rollback cấu hình rõ ràng.

**WAL không nên bị xem là log ứng dụng để in ra mọi câu SQL.** Để quan sát hành vi nghiệp vụ, hãy dùng metrics, tracing, query logging có kiểm soát và audit phù hợp; thao tác đọc/giải mã WAL cần công cụ và quyền chuyên biệt.

## 17. Thực hành phân tích tình huống crash

Xét một database có thể khôi phục bằng WAL. Giả sử một giao dịch T1 ghi một hàng rồi commit, nhưng trang dữ liệu liên quan chưa được ghi xuống file. Trong một giao dịch T2 khác, một hàng bị cập nhật rồi DB crash trước khi T2 commit.

~~~text
WAL bền vững:
  T1: UPDATE record
  T1: COMMIT
  T2: UPDATE record
  (không có COMMIT bền vững của T2)

File dữ liệu:
  Một số trang đã theo kịp WAL, một số trang còn cũ
~~~

Hệ quản trị cần:

- Khôi phục các thay đổi cần thiết để trạng thái transaction T1 đã commit được duy trì.
- Không cho kết quả chưa commit của T2 trở thành dữ liệu hợp lệ sau recovery.
- Phục hồi tính toàn vẹn cấu trúc lưu trữ ngay cả khi các data pages đã được ghi ở các thời điểm khác nhau.

Trong PostgreSQL, cơ chế WAL redo, trạng thái giao dịch và MVCC phối hợp để đạt các mục tiêu trên. Không nên suy rằng cơ chế khôi phục sẽ dùng đúng hai lệnh SQL UPDATE gốc hoặc thực thi lại logic Java. **Khôi phục vật lý ở tầng DB không phải gọi lại API nghiệp vụ.**

Khi học thực hành, có thể so sánh **LSN, thống kê WAL, thời gian commit và kết quả truy vấn** trên một môi trường thử nghiệm được phép. Không tắt fsync, cắt điện hoặc xóa WAL trên môi trường có dữ liệu quan trọng chỉ để tái hiện một kịch bản.

## 18. Sai lầm phổ biến

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “COMMIT phải ghi tất cả data pages xuống đĩa.” | Thông thường có thể flush WAL đủ trước và ghi data pages sau |
| “Có WAL record trong RAM là đã bền vững.” | Phải phân biệt WAL buffer, write và flush tới lưu trữ bền vững |
| “WAL chỉ cần ghi khi transaction đã commit.” | Data pages có thể được ghi từ transaction chưa commit; thông tin WAL tương ứng phải có trước khi flush page |
| “WAL nghĩa là DB luôn dùng cùng một thuật toán undo.” | PostgreSQL, InnoDB và ARIES có cơ chế recovery khác nhau |
| “Checkpoint xóa mọi WAL cũ ngay lập tức.” | Giữ/tái sử dụng WAL còn phụ thuộc archive, slot, replica và các nhu cầu phục hồi |
| “WAL cục bộ thay thế được backup.” | Mất ổ đĩa hay xóa dữ liệu đã commit vẫn cần backup/PITR hoặc cơ chế phù hợp |
| “synchronous_commit=off chỉ thay đổi tốc độ, không đổi độ bền.” | Có thể mất những commit đã được client nhận xác nhận nếu crash trước flush |
| “fsync=off chỉ giống commit bất đồng bộ.” | Có thể dẫn tới hỏng dữ liệu không phục hồi được khi crash |
| “COMMIT trả SQLException chắc chắn transaction rollback.” | Kết nối có thể hỏng sau khi server đã commit; cần đối soát qua request ID |
| “WAL tự bảo đảm exactly-once cho request.” | Cần idempotency và ràng buộc nghiệp vụ |
| “Có synchronous replica là không bao giờ mất dữ liệu.” | Phụ thuộc điểm chờ replication, failover, vùng lỗi chung và chính sách vận hành |
| “Có WAL thì không cần kiểm thử restore.” | Khôi phục có thể thất bại vì thiếu WAL archive, backup hoặc cấu hình sai |

## 19. Bài tập và gợi ý đáp án

### Bài 1. Thứ tự flush

Một data page đã được cập nhật đến pageLSN = 500, nhưng WAL chỉ mới được flush bền vững đến LSN = 450. Có được ghi phiên bản hiện tại của data page đó xuống đĩa không?

**Gợi ý:** **Chưa được** theo nguyên tắc write-ahead; trước hết phải flush WAL cần thiết tối thiểu qua LSN 500, hoặc DB phải dùng cơ chế tương đương bảo đảm thông tin khôi phục đã bền vững. Bản ghi WAL mới chỉ nằm trong bộ nhớ không đủ.

### Bài 2. Commit thành công, data page chưa ghi

T1 sửa trang P, commit được xác nhận ở chế độ đồng bộ bền vững; ngay sau đó hệ thống crash trước khi P được ghi xuống file dữ liệu. Tại sao có thể khôi phục T1?

**Gợi ý:** WAL cần thiết và commit record đã bền vững; recovery có thể **redo** thay đổi mà P chưa kịp nhận. Không cần chờ P được ghi trước khi xác nhận commit.

### Bài 3. Lỗi kết nối trong lúc commit

Client Java gửi COMMIT rồi nhận lỗi mạng. Có thể kết luận database đã rollback để retry việc chuyển tiền ngay không?

**Gợi ý:** **Không**. Server có thể đã commit và mất phản hồi. Cần request ID duy nhất, dữ liệu kết quả được lưu trong transaction, và kiểm tra lại trạng thái trước khi retry.

### Bài 4. Bật synchronous_commit = off

Một dịch vụ ghi thống kê lượt xem muốn giảm độ trễ. Thay đổi **synchronous_commit** từ on sang off làm thay đổi bảo đảm nào?

**Gợi ý:** Có thể xác nhận commit trước khi WAL liên quan được flush bền vững; mất điện/crash có thể làm mất những commit vừa báo thành công. Quyết định chỉ phù hợp khi nghiệp vụ chấp nhận mất dữ liệu gần nhất, có đánh giá rõ và vẫn bảo vệ các thao tác quan trọng.

### Bài 5. WAL archive không liên tục

Có base backup tại 01:00 và WAL archive từ 01:00 đến 03:00 nhưng thiếu một đoạn ở 02:00. Có thể chắc chắn phục hồi PITR đến 02:30 không?

**Gợi ý:** **Không**. PITR cần chuỗi WAL phù hợp liên tục từ nền backup tới mục tiêu. Đoạn thiếu có thể chặn recovery trước mốc mong muốn.

### Bài 6. WAL tăng nhanh

Thư mục **pg_wal** tăng dung lượng, trong khi một standby đang mất kết nối và vẫn còn replication slot. Nên xóa các tệp WAL cũ bằng tay không?

**Gợi ý:** **Không**. WAL có thể đang bị giữ để standby bắt kịp; xóa thủ công có nguy cơ phá khả năng replication/recovery. Cần kiểm tra slot, độ trễ, archive, dung lượng và dùng quy trình quản trị chính thức.

### Bài 7. So sánh hai cơ chế

Một hệ thống có WAL cục bộ, nhưng toàn bộ máy chủ cùng ổ đĩa bị phá hủy. Hệ thống khác có base backup ở vùng khác và WAL archive đủ. Khả năng phục hồi có gì khác?

**Gợi ý:** WAL cục bộ bị mất cùng máy không giúp phục hồi khi không còn bản sao. Hệ có backup ngoài vùng lỗi và chuỗi WAL thích hợp có thể khôi phục từ backup rồi replay WAL tới điểm cho phép.

## 20. Ghi nhớ khi thiết kế độ bền dữ liệu

**Write-ahead logging** đặt thông tin phục hồi bền vững lên trước việc ghi trang dữ liệu liên quan. Nhờ vậy, một database có thể **xác nhận transaction bằng cách flush WAL** theo chính sách bền vững rồi trì hoãn ghi các data pages, đồng thời có cơ sở để **redo** sau crash. **Checkpoint** giúp giới hạn công việc phục hồi; **full-page images** và cơ chế đồng bộ tới storage giúp xử lý thêm các rủi ro ở tầng trang và thiết bị.

Đối với ứng dụng Java, hãy phân biệt rõ ba câu hỏi: **DB có thể phục hồi sau crash không**, **một COMMIT đã xác nhận có thể bị mất theo cấu hình không**, và **client có biết chính xác COMMIT đã xảy ra không**. WAL hỗ trợ hai câu hỏi đầu trong phạm vi bảo đảm của hệ quản trị và hạ tầng; câu hỏi thứ ba đòi hỏi thêm **idempotency, đối soát và xử lý lỗi kết nối**. Khi cần phục hồi sau mất máy, xóa nhầm hoặc sự cố diện rộng, kết hợp WAL với **backup, archiving, replication và diễn tập restore**, thay vì coi một file nhật ký là toàn bộ chiến lược bảo vệ dữ liệu.
