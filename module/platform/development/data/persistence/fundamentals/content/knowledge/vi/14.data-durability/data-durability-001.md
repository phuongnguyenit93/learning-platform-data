# Dữ liệu đi qua bộ đệm ứng dụng, hệ điều hành và thiết bị lưu trữ

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Mô tả đường đi của dữ liệu khi ứng dụng Java ghi và đọc thông qua JDBC/ORM, database, bộ đệm hệ điều hành và thiết bị lưu trữ.
2. Phân biệt thao tác **ghi vào bộ đệm**, **gửi câu SQL**, **flush**, **commit** và **ghi bền vững** khi gặp sự cố.
3. Giải thích vai trò của **write-ahead log (WAL)**, `fsync`, checkpoint và cơ chế khôi phục sau crash.
4. Chỉ ra điều gì có thể bị mất khi tiến trình Java, tiến trình database, hệ điều hành hoặc ổ đĩa gặp lỗi.
5. Thiết kế ranh giới transaction và cách xử lý kết quả commit không chắc chắn trong ứng dụng Java.
6. Đánh giá sự đánh đổi giữa độ trễ ghi, thông lượng, mức bảo đảm dữ liệu và chi phí sao lưu/khôi phục.

Bài thuộc chương **Độ bền dữ liệu** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Mục tiêu của module là hiểu cách lưu trữ dữ liệu bền vững trong ứng dụng, từ lược đồ, truy vấn, chỉ mục đến giao dịch, cô lập và kiểm soát đồng thời. Việc theo dõi đường đi của một lần ghi giúp người học thiết kế ranh giới persistence cho Java, xử lý lỗi kết nối và lựa chọn phương án sao lưu, bảo mật, phục hồi và tối ưu hiệu năng có căn cứ.

## 1. “Đã ghi” có thể mang nhiều ý nghĩa

Giả sử ứng dụng nhận lệnh tạo đơn hàng. Lập trình viên gọi một phương thức `saveOrder()` và nhận được giá trị trả về. Vậy đơn hàng đã an toàn sau khi máy chủ mất điện hay chưa?

Câu trả lời phụ thuộc vào **thao tác nào đã hoàn tất và tầng nào xác nhận nó**. Những trạng thái sau không tương đương:

| Quan sát từ ứng dụng | Điều chắc chắn có thể kết luận | Điều chưa chắc chắn |
| --- | --- | --- |
| Java tạo object `Order` trong RAM | Dữ liệu có trong bộ nhớ tiến trình | DB chưa chắc biết đến object |
| ORM `persist()` một entity | Entity được quản lý theo hợp đồng ORM | SQL có thể chưa được gửi; transaction chưa commit |
| ORM `flush()` thành công | Các thay đổi cần đồng bộ đã được đẩy qua SQL theo cơ chế ORM | Transaction vẫn có thể rollback |
| JDBC `executeUpdate()` trong transaction thành công | Statement đã được DB xử lý và trả kết quả của statement | Chưa phải commit của transaction |
| JDBC `commit()` trả về thành công | DB đã xác nhận commit theo cấu hình của nó | Không tự bảo đảm replica, backup hay sống sót khi mất toàn bộ ổ đĩa |
| Dữ liệu nằm trong OS page cache | Hệ điều hành đang giữ dữ liệu trong RAM | Nguồn điện mất có thể làm mất nội dung chưa được đẩy xuống lưu trữ bền |
| Hệ thống ghi đã xác nhận flush đến thiết bị | Có thêm cơ sở tin rằng dữ liệu đã qua các bộ đệm cần thiết | Mức độ an toàn thực còn phụ thuộc filesystem, controller, thiết bị và việc chúng tuân thủ lệnh flush |

**Độ bền (durability)** trong ACID thường được hiểu là: một transaction được thông báo đã commit thành công thì thay đổi của nó phải có khả năng tồn tại qua các sự cố **thuộc phạm vi cam kết của hệ quản trị và cấu hình triển khai**. Không nên hiểu đó là bảo đảm tồn tại bất chấp mọi sự cố, kể cả mất toàn bộ phương tiện lưu trữ cùng bản sao lưu.

Ví dụ xuyên suốt sẽ dùng **Java 17 + JDBC + PostgreSQL**, đồng thời chỉ rõ những phần có thể khác ở MySQL/InnoDB, SQL Server hoặc hệ thống lưu trữ khác.

## 2. Bản đồ đường đi của một thao tác ghi

Một lần ghi đi qua nhiều vùng nhớ và nhiều ranh giới phần mềm:

~~~text
  ỨNG DỤNG JAVA
  ┌────────────────────────────────────────────┐
  │ Object / persistence context / batch      │
  │ JDBC driver và bộ đệm gửi dữ liệu          │
  └──────────────────┬─────────────────────────┘
                     │ SQL qua kết nối mạng / socket
                     ▼
  TIẾN TRÌNH DATABASE
  ┌────────────────────────────────────────────┐
  │ Kiểm tra SQL, constraint, lock, transaction │
  │                                            │
  │          ┌──────────────┐ ┌─────────────┐ │
  │          │ WAL buffer   │ │ Buffer pool │ │
  │          │ ghi log      │ │ trang dữ liệu│ │
  │          └──────┬───────┘ └──────┬──────┘ │
  └─────────────────┼────────────────┼─────────┘
                    │                │
                    ▼                ▼
  HỆ ĐIỀU HÀNH / FILESYSTEM
           Trang cache WAL    Trang cache file dữ liệu
                    │                │
                    ▼                ▼
            Khối lưu trữ / bộ đệm controller
                    │
                    ▼
          SSD / HDD / lưu trữ bền theo cấu hình
~~~

Đây là **sơ đồ khái niệm**, không mô tả một dây chuyền tuần tự duy nhất. Trong một DBMS có WAL, có **hai đường ghi liên quan nhưng khác nhau**:

- Đường **WAL/redo log** ghi thông tin cần thiết để khôi phục thay đổi.
- Đường **trang dữ liệu** giữ các bản sao trang đã sửa ở buffer pool rồi ghi ra file dữ liệu khi thích hợp.

Một transaction có thể được xác nhận commit sau khi bản ghi log cần thiết đã được làm bền vững **mà các trang dữ liệu tương ứng vẫn còn ở RAM**. Cơ chế khôi phục sẽ sử dụng WAL để hoàn tất lại những thay đổi đó khi DB khởi động sau crash.

Chi tiết về buffer pool, WAL, direct I/O, file layout và tính bền vững thay đổi theo engine và cấu hình. Một DBMS có thể bỏ qua OS page cache cho một số loại file hoặc dùng cơ chế I/O riêng; vì vậy sơ đồ cần được đọc như **mô hình các tầng chịu trách nhiệm**, không phải khẳng định tất cả byte đều phải đi qua đúng mọi hộp.

### 2.1. Tầng ứng dụng: bộ nhớ Java và bộ đệm thư viện

Ở ứng dụng, dữ liệu có thể tồn tại dưới dạng:

- Field của một object trong Java heap.
- Queue, batch, cache hoặc buffer được lập trình viên tự tổ chức.
- Persistence context của ORM (ví dụ JPA/Hibernate).
- Buffer của driver, socket hoặc thư viện I/O.

Mỗi tầng có cơ chế “đẩy dữ liệu đi” riêng. Với JPA, gọi `persist()` có thể chỉ đưa entity vào persistence context; gọi `flush()` yêu cầu đồng bộ các thay đổi cần thiết xuống database bằng SQL. `flush()` **không phải `COMMIT`**: nếu transaction rollback sau đó, những SQL đã thực thi vẫn không trở thành một transaction thành công.

Với JDBC, `PreparedStatement.executeUpdate()` thực thi SQL theo ngữ cảnh connection. Khi `autoCommit=false`, statement có thể thành công nhưng transaction vẫn chưa kết thúc. Khi `autoCommit=true`, JDBC thường quản lý commit cho mỗi statement theo hợp đồng driver/database; nhưng không nên lấy hành vi tự động này làm lý do bỏ qua yêu cầu transaction nhiều bước.

### 2.2. Tầng database: buffer pool và log giao dịch

DBMS giữ những trang dữ liệu được đọc hoặc sửa trong bộ nhớ để tránh I/O không cần thiết. Ví dụ PostgreSQL có `shared_buffers`, InnoDB có `buffer pool`. Khi một trang trong RAM được sửa mà file dữ liệu chưa phản ánh đầy đủ thay đổi, trang đó thường được gọi là **dirty page**.

Ghi trực tiếp mọi dirty page xuống thiết bị mỗi lần UPDATE sẽ rất tốn I/O. Vì thế, nhiều DBMS dựa trên log ghi trước:

1. Ghi mô tả thay đổi cần phục hồi vào WAL/redo log.
2. Cho phép dirty page còn ở bộ nhớ một thời gian.
3. Đảm bảo thứ tự ghi cần thiết giữa log và dữ liệu.
4. Ghi trang dữ liệu ra file sau, thường qua tiến trình nền hoặc checkpoint.

Vì sao được phép làm như vậy? Nếu dữ liệu mới chưa nằm trong data file nhưng WAL đã bền vững, DB có thể **redo** phần thay đổi cần thiết sau sự cố. Đây là trọng tâm của việc tách **commit bền vững** khỏi **việc mọi trang dữ liệu đã được ghi hết xuống đĩa**.

### 2.3. Tầng hệ điều hành: page cache

Khi một chương trình gọi `write()` với I/O có bộ đệm, hệ điều hành có thể sao chép nội dung vào **page cache** rồi cho lời gọi trả về, trước khi thiết bị lưu trữ nhận được tất cả dữ liệu. Từ góc nhìn tiến trình, thao tác ghi đã hoàn tất; từ góc nhìn mất điện, nội dung còn ở bộ nhớ có thể mất.

Hệ điều hành có cơ chế ghi các trang bẩn theo thời gian hoặc khi áp lực bộ nhớ tăng. Việc này giúp gộp và sắp xếp I/O nhưng tạo một khoảng thời gian mà dữ liệu **có mặt trong RAM hệ điều hành** và **chưa chắc đã ổn định trên thiết bị**.

Trên một số đường I/O, database dùng direct I/O hoặc tùy chọn đồng bộ, nên tương tác với page cache thay đổi. Dù vậy, vẫn cần xác định rõ **tầng nào có quyền xác nhận dữ liệu đã được flush**.

### 2.4. Tầng thiết bị: controller cache và môi trường lưu trữ

SSD, HDD, bộ điều khiển RAID hoặc hệ thống lưu trữ mạng có thể có bộ đệm riêng. Một số bộ đệm mất dữ liệu khi mất nguồn; một số có pin hoặc tụ bảo vệ nguồn (*power-loss protection*, PLP), hoặc dùng cơ chế bảo đảm bền vững khác.

Lệnh flush từ hệ điều hành chỉ đáng tin nếu toàn bộ tầng dưới thực sự thực hiện cam kết tương ứng. Thiết bị hoặc controller báo thành công sai, cấu hình cache không an toàn, lỗi firmware, hệ thống lưu trữ từ xa hoặc phần cứng hỏng hoàn toàn đều có thể làm giảm mức bảo đảm.

**Không suy ra “đã nằm trên đĩa” chỉ vì lời gọi ghi của ứng dụng trả về thành công.** Cần hiểu hợp đồng của DBMS, filesystem, driver, controller và hạ tầng lưu trữ.

## 3. Write-ahead logging: dữ liệu được bảo vệ trước khi trang được ghi

**Write-ahead logging (WAL)** là nguyên tắc ghi thông tin phục hồi trước khi những trang dữ liệu tương ứng được lưu bền vững. PostgreSQL dùng WAL; InnoDB dùng redo log với các quy tắc riêng.

Hãy xem một transaction đơn giản:

~~~sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE id = 101;

UPDATE accounts
SET balance = balance + 100
WHERE id = 202;

COMMIT;
~~~

Với cơ chế log phù hợp, DBMS không cần chờ ghi hết hai trang account thành dữ liệu cuối trong file bảng rồi mới có thể commit. Nó có thể bảo vệ thông tin cần thiết trong WAL, xác nhận commit sau khi đạt điều kiện flush WAL, và sau đó ghi các dirty page vào data file.

### 3.1. Thứ tự tối thiểu cần hiểu

~~~text
Thời gian →
UPDATE
  ├─ Thay đổi phiên bản/trang trong bộ nhớ database
  ├─ Tạo bản ghi WAL cần thiết
  │
COMMIT
  ├─ Ghi bản ghi commit vào WAL
  ├─ Flush phần WAL cần thiết theo cấu hình bền vững
  └─ Trả kết quả COMMIT thành công
          |
          |  Dirty page có thể vẫn nằm trong buffer pool
          v
     Checkpoint / background writer
          |
          v
     Ghi data page xuống thiết bị
~~~

Với cấu hình PostgreSQL thông thường có `fsync=on` và `synchronous_commit=on`, commit cục bộ được xác nhận sau khi WAL cần thiết đã được flush bền vững trên hệ lưu trữ cục bộ theo cam kết của tầng I/O. Điều đó **không có nghĩa** mọi data page đều đã ghi xong.

Nếu database crash sau khi COMMIT đã xác nhận nhưng trước khi data page được ghi, nó có thể đọc WAL khi khởi động lại để phục hồi trạng thái đã commit. Nếu WAL không còn vì ổ lưu trữ hỏng hoàn toàn, khả năng phục hồi phụ thuộc replica/backup và kiến trúc lưu trữ; WAL ở cùng ổ bị mất cũng không giúp được.

### 3.2. Checkpoint và lý do cần log đủ thông tin

**Checkpoint** là mốc tiến trình DB tổ chức việc đẩy các dirty page cần thiết ra lưu trữ, qua đó giới hạn lượng WAL phải quét/phát lại khi khởi động sau sự cố. Checkpoint không phải lúc duy nhất các trang được ghi; hệ quản trị cũng có thể ghi trang ở thời điểm khác.

Nếu hệ thống gặp **torn page** (một phần trang được ghi, phần khác chưa), dữ liệu có thể bị lỗi dù WAL tồn tại. PostgreSQL dùng cơ chế như `full_page_writes` để hỗ trợ phục hồi các trang bị ghi dở trong các trường hợp thiết kế của nó. Không nên tắt những cơ chế bảo vệ này chỉ để giảm lượng ghi khi chưa hiểu hậu quả và mô hình hỏng hóc.

### 3.3. Nhầm lẫn về trạng thái “dữ liệu ở bảng”

Một bản ghi mới có thể đọc được sau commit bởi các transaction phù hợp, dù trang của nó vẫn ở DB buffer. Khả năng nhìn thấy của một transaction chịu sự chi phối của **MVCC và mức cô lập**, còn khả năng tồn tại sau crash chịu sự chi phối của **WAL, flush và hạ tầng lưu trữ**. Đây là hai câu hỏi khác nhau.

Một truy vấn `SELECT` trả về hàng mới **không chứng minh** rằng bản ghi log đã được flush đủ để khôi phục sau mất điện; đặc biệt khi cấu hình commit bất đồng bộ được bật.

## 4. Flush, fsync, commit: cùng một từ “ghi” nhưng khác cam kết

### 4.1. Flush ở cấp ứng dụng

Trong Java, `BufferedOutputStream.flush()` đẩy các byte đang nằm trong bộ đệm của thư viện xuống stream tầng dưới. Tùy loại stream, điều này có thể chỉ đưa dữ liệu tới kernel hoặc qua một tầng đệm khác.

Với JPA/Hibernate, `EntityManager.flush()` tập trung vào đồng bộ trạng thái entity với SQL trong transaction. Nó **không hứa** dữ liệu đã commit và sống sót sau mất điện.

### 4.2. fsync/force ở cấp hệ điều hành

Trên hệ thống hỗ trợ, `fsync` yêu cầu hệ điều hành đồng bộ nội dung file đã thay đổi tới lưu trữ bền theo hợp đồng của hệ thống. `fdatasync` thường tập trung vào dữ liệu và metadata cần để truy cập dữ liệu; chi tiết thay đổi theo nền tảng. Trong Java NIO, `FileChannel.force(true)` đưa ra yêu cầu buộc cập nhật file xuống thiết bị lưu trữ; với file ở hệ thống lưu trữ từ xa, mức bảo đảm có thể phụ thuộc cấu hình và triển khai.

Ví dụ ghi một file bằng Java:

~~~java
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public final class DurableFileExample {
    public static void writeFile(Path path, String content)
            throws Exception {
        ByteBuffer data = StandardCharsets.UTF_8.encode(content);

        try (FileChannel channel = FileChannel.open(
                path,
                StandardOpenOption.CREATE,
                StandardOpenOption.WRITE,
                StandardOpenOption.TRUNCATE_EXISTING)) {

            while (data.hasRemaining()) {
                channel.write(data);
            }

            // Yêu cầu hệ thống lưu trữ đồng bộ dữ liệu và metadata
            // theo hợp đồng của nền tảng và FileChannel.
            channel.force(true);
        }
    }
}
~~~

Ví dụ thể hiện `force(true)` khi ghi file; nó **không** tạo một giao thức thay thế file nguyên tử. Nếu mục tiêu là cập nhật file cấu hình mà không làm mất bản cũ khi crash, thông thường cần thiết kế ghi file tạm, sync file mới, đổi tên nguyên tử khi filesystem hỗ trợ, và sync thư mục chứa trong những môi trường cần bảo vệ cập nhật tên file. Lời hứa chính xác phụ thuộc OS và filesystem; không nên đánh đồng `force(true)` với backup hay transaction DB.

### 4.3. COMMIT ở cấp database

`COMMIT` đánh dấu kết thúc transaction và yêu cầu DBMS thực hiện cam kết của hệ thống giao dịch. Trên PostgreSQL với các cài đặt bền vững thích hợp, dữ liệu được xác nhận commit khi WAL cục bộ cần thiết đã được flush. Một hệ quản trị khác có thể dùng redo log, journal hoặc một cơ chế tương đương.

Đây là hợp đồng nghiệp vụ mạnh hơn việc một phương thức Java flush bộ đệm. Nhưng **commit thành công ở một node không tự bảo đảm** mọi replica đã nhận/áp dụng dữ liệu, WAL đã được archive, backup đã chạy hay ổ lưu trữ của cả datacenter không thể hỏng.

## 5. Phân tích các tình huống sự cố

Giả sử ứng dụng gửi lệnh tạo đơn hàng. Bảng sau tách **điều đã được xác nhận** và **sự cố xảy ra sau đó**:

| Tình huống | Quan sát/hậu quả khả dĩ | Cách hiểu đúng |
| --- | --- | --- |
| JVM crash trước khi gửi SQL | Object/batch chưa gửi có thể mất | RAM ứng dụng không phải kho bền vững |
| SQL đã chạy nhưng transaction chưa commit; JVM/connection mất | Transaction có thể bị rollback khi DB phát hiện ngắt kết nối | Statement thành công chưa đồng nghĩa commit |
| PostgreSQL DB crash sau commit được xác nhận với WAL đã flush an toàn | DB có thể redo WAL để phục hồi bản ghi commit | Dirty data page chưa ghi vẫn có thể được phục hồi |
| Hệ điều hành mất điện khi WAL chỉ còn ở page cache do cấu hình commit bất đồng bộ | Một số transaction đã báo thành công có thể mất | Cần biết chế độ xác nhận commit |
| Thiết bị xác nhận flush sai hoặc mất cả dữ liệu lẫn WAL không thể khôi phục | Không thể cam kết khôi phục chỉ nhờ WAL cục bộ | Cần thiết kế lưu trữ tin cậy, backup/replica |
| Client mất mạng đúng lúc `COMMIT` đang xử lý | Client không biết DB đã commit hay chưa | **Kết quả commit không xác định từ phía client** |
| Primary hỏng trước khi replica bất đồng bộ nhận dữ liệu | Replica có thể thiếu transaction mới nhất | Durability cục bộ khác với RPO khi failover |

Trong những tình huống trên, từ “có thể” phản ánh sự phụ thuộc vào thời điểm hỏng, cấu hình và DBMS. Không nên tuyên bố một giao dịch chắc chắn mất hoặc chắc chắn còn nếu không biết điểm commit, flush và trạng thái lưu trữ.

### 5.1. Vì sao mất kết nối khi COMMIT là trường hợp đặc biệt?

Giả sử client gửi `COMMIT`, DB đã ghi WAL bền vững và commit, nhưng phản hồi bị mất trên mạng. JDBC ném `SQLException` vì kết nối bị đóng. **Ứng dụng không thể suy ra** rằng transaction đã rollback: nó có thể đã commit thành công.

Nếu client lập tức gửi lại lệnh “tạo đơn” bằng request mới mà không có định danh idempotency, có thể tạo đơn hàng trùng. Cần một khóa yêu cầu nghiệp vụ duy nhất và cách truy vấn trạng thái sau lỗi; thông điệp “gặp SQLException thì thử lại nguyên xi” thường không đủ.

### 5.2. Crash của process khác mất toàn bộ máy chủ

Một DB process bị dừng trong khi OS và đĩa còn hoạt động khác với mất nguồn đột ngột. Trong trường hợp process crash, dữ liệu ở page cache của OS có thể vẫn còn và DB có thể phục hồi tương ứng. Trong trường hợp mất điện, cache chỉ ở RAM có thể mất. Vì vậy, kiểm thử “khởi động lại dịch vụ bình thường” không tương đương kiểm thử độ bền khi mất điện.

Cần đặt **mô hình sự cố** trước khi tuyên bố đạt durability: chỉ tính process crash, OS crash, mất nguồn, hỏng ổ, mất cả vùng triển khai, hay mất dữ liệu do thao tác người dùng nhầm?

## 6. PostgreSQL: cấu hình nào ảnh hưởng xác nhận commit?

Một số cấu hình thường được quan sát:

~~~sql
SHOW fsync;
SHOW synchronous_commit;
SHOW full_page_writes;
SHOW wal_level;
~~~

Ý nghĩa tổng quát:

| Cấu hình PostgreSQL | Vai trò và điều cần thận trọng |
| --- | --- |
| `fsync` | Cho phép PostgreSQL yêu cầu OS đồng bộ ghi cần thiết để đảm bảo crash safety. `off` có thể dẫn tới **mất dữ liệu hoặc hỏng không thể khôi phục** sau sự cố; không dùng cho hệ thống production có dữ liệu cần giữ |
| `synchronous_commit` | Quy định mức xác nhận commit và việc chờ WAL được ghi/flush/nhân bản, tùy chế độ cùng cấu hình standby |
| `full_page_writes` | Hỗ trợ bảo vệ phục hồi trước nguy cơ ghi dở trang dữ liệu |
| `wal_level` | Mức thông tin WAL phục vụ các nhu cầu như phục hồi, standby hoặc logical decoding; không tự thay thế `fsync` |

Với `fsync=on` và `synchronous_commit=on`, PostgreSQL thường đợi WAL cần thiết được flush **cục bộ** trước khi thông báo commit hoàn tất. Nếu có cấu hình synchronous standby, một số mức `synchronous_commit` còn chờ standby theo hợp đồng tương ứng.

Với `synchronous_commit=off`, PostgreSQL có thể phản hồi commit **trước khi WAL commit record được flush bền vững**. Tắt chờ flush có thể cải thiện độ trễ nhưng tạo cửa sổ mất những transaction vừa được xác nhận nếu server gặp crash. Điều này không tự biến transaction thành không nguyên tử; nó thay đổi **độ bền của các commit gần sự cố**. Không sử dụng chế độ này cho giao dịch cần cam kết không mất dữ liệu mà chưa có phân tích rủi ro.

**Không lấy một tùy chọn đơn lẻ làm toàn bộ bảo đảm.** Cấu hình hạ tầng lưu trữ, standby, WAL archive và failover cũng phải được xem xét. Nếu `fsync` bị tắt hoặc thiết bị không tuân thủ flush, chỉ đặt `synchronous_commit=on` không đủ để tạo bảo đảm mạnh.

### 6.1. Một ví dụ transaction với xác nhận cục bộ

Tạo bảng đơn hàng mẫu trong môi trường thực hành:

~~~sql
CREATE TABLE durable_orders (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    BIGINT NOT NULL,
    request_key  TEXT NOT NULL,
    total_amount NUMERIC(14, 2) NOT NULL CHECK (total_amount >= 0),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, request_key)
);
~~~

Ví dụ thực thi:

~~~sql
BEGIN;

-- Áp dụng trong transaction hiện tại; giả định fsync của server
-- và tầng lưu trữ được cấu hình để bảo vệ durability.
SET LOCAL synchronous_commit = on;

INSERT INTO durable_orders (tenant_id, request_key, total_amount)
VALUES (42, 'checkout-20261122-0001', 750000.00);

COMMIT;
~~~

Sau khi nhận kết quả `COMMIT` thành công, ứng dụng có thể coi transaction được DB xác nhận theo cấu hình đã kiểm tra. **Đừng đánh đồng** điều này với lời hứa rằng dữ liệu đã xuất hiện trên mọi bản sao dự phòng hoặc sẽ tồn tại nếu toàn bộ ổ chứa cả data file và WAL bị phá hủy.

Ràng buộc `UNIQUE (tenant_id, request_key)` giúp thiết kế xử lý retry và kết quả commit không xác định: hai request cùng một khóa không thể tạo hai hàng với cùng cặp giá trị. Tuy nhiên, hệ thống còn phải kiểm tra payload có khớp với request ban đầu và xác định phản hồi phù hợp khi khóa đã tồn tại.

### 6.2. Đo hiệu năng khi giữ cam kết durability

Các chỉ số hữu ích gồm:

- Độ trễ `COMMIT` p50/p95/p99 khi ít và nhiều transaction chạy đồng thời.
- Số transaction/giây, số byte WAL phát sinh và tốc độ ghi/flush log.
- Thời gian chờ I/O, tốc độ checkpoint, số dirty page, tình trạng thiết bị.
- Độ trễ replica và WAL archive nếu kiến trúc có nhân bản/phục hồi theo thời điểm.
- Thời gian khôi phục từ crash trong môi trường kiểm thử và kết quả đối soát bản ghi đã được xác nhận.

Một lệnh `INSERT` đơn lẻ nhanh không chứng minh rằng `COMMIT` bền vững nhanh dưới tải. Ngược lại, đo tổng thời gian transaction mà không tách thời gian xử lý nghiệp vụ, chờ khóa, ghi WAL và mạng có thể khiến tối ưu nhầm vị trí.

## 7. Vì sao ghi đồng bộ thường chậm hơn và cách cải thiện an toàn

Làm bền vững dữ liệu có thể phát sinh **flush latency**: chờ các tầng dưới xác nhận dữ liệu đã được ghi bền. Nếu mỗi transaction cần một lần flush riêng, giới hạn độ trễ của thiết bị có thể giới hạn thông lượng.

**Group commit** cho phép DBMS gộp việc flush WAL cần thiết cho nhiều transaction thành ít đợt flush hơn. Cơ chế này giúp tăng thông lượng khi có nhiều transaction đồng thời mà vẫn duy trì mức cam kết phù hợp. Vì vậy, không nên suy ra “một transaction bằng một lần ghi thiết bị riêng lẻ” hay “tắt bền vững là cách duy nhất để tăng tốc”.

Các hướng tối ưu cần cân nhắc:

1. **Giữ transaction ngắn**, giảm xử lý bên ngoài và chờ khóa trước khi commit.
2. **Dùng batch hợp lý** cho workload có thể gom nhiều ghi vào một transaction; cân bằng độ trễ, kích thước log và phạm vi rollback.
3. **Đặt WAL trên tầng lưu trữ có độ trễ ổn định**, kiểm tra IOPS và đặc tính flush dưới tải; tách log và data nếu kiến trúc, chi phí và ràng buộc vận hành cho phép.
4. **Giảm ghi không cần thiết** từ các bản cập nhật lặp, chỉ mục dư thừa hoặc thiết kế schema chưa phù hợp.
5. **Đo cả đường backup, replica và recovery**, vì hiệu năng ghi lúc bình thường không phải mục tiêu duy nhất.
6. **Chỉ giảm mức cam kết durability** với những dữ liệu có thể tái tạo và khi nghiệp vụ đã chấp nhận rõ cửa sổ mất dữ liệu.

Ví dụ log thống kê tạm có thể chấp nhận mất vài giây, nhưng giao dịch thanh toán hoặc sổ cái kế toán thường cần cam kết chặt chẽ hơn. Hai loại dữ liệu có thể dùng chiến lược xử lý khác nhau; quyết định phải xuất phát từ RPO và bất biến nghiệp vụ.

## 8. Java/JDBC: commit là ranh giới quan trọng của ứng dụng

Ví dụ tiếp tục dùng bảng `durable_orders`. Mục tiêu là **chỉ trả kết quả tạo đơn thành công sau khi `commit()` đã trả về thành công**.

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class DurableOrderRepository {
    private final DataSource dataSource;

    public DurableOrderRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public long createOrder(
            long tenantId, String requestKey, BigDecimal totalAmount)
            throws SQLException {

        if (requestKey == null || requestKey.isBlank()) {
            throw new IllegalArgumentException("Missing request key");
        }
        if (totalAmount == null || totalAmount.signum() < 0) {
            throw new IllegalArgumentException("Invalid total amount");
        }

        String sql = """
                INSERT INTO durable_orders
                    (tenant_id, request_key, total_amount)
                VALUES (?, ?, ?)
                RETURNING id
                """;

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try {
                long id;
                try (PreparedStatement statement =
                             connection.prepareStatement(sql)) {
                    statement.setLong(1, tenantId);
                    statement.setString(2, requestKey);
                    statement.setBigDecimal(3, totalAmount);

                    try (ResultSet rs = statement.executeQuery()) {
                        if (!rs.next()) {
                            throw new SQLException(
                                    "Insert returned no row");
                        }
                        id = rs.getLong("id");
                    }
                }

                connection.commit();
                return id;
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

Đây là ví dụ Java 17 cho PostgreSQL. Nó cố ý giữ toàn bộ một lần INSERT và COMMIT trên **một connection**. Đoạn mã làm rõ đường gọi JDBC; nó chưa hiện thực toàn bộ xử lý idempotency, ghi đơn hàng nhiều bảng hoặc điều phối API.

Ba điểm đặc biệt quan trọng:

- `executeQuery()` nhận `id` sau INSERT nhưng **transaction vẫn có thể rollback**; vì vậy return nằm sau `connection.commit()`.
- Nếu `commit()` ném lỗi do mất mạng, gọi `rollback()` ở nhánh lỗi là nỗ lực dọn dẹp, **không chứng minh DB chưa commit**. Ứng dụng cần kiểm tra `request_key` qua kết nối mới và xử lý trạng thái chưa xác định.
- Nếu `commit()` thành công, bảo đảm bền vững thực tế vẫn phụ thuộc DBMS, tùy chọn commit, filesystem và thiết bị; Java không thể dùng `synchronized` hoặc `flush()` để tăng cam kết của database.

### 8.1. Tình huống timeout ngay lúc commit

Giả sử API gửi `POST /orders` với idempotency key là `checkout-20261122-0001`. Client timeout sau khi server gửi COMMIT nhưng trước khi nhận câu trả lời.

Quy trình phục hồi có chủ đích:

1. Client gửi lại request với **cùng key và cùng nội dung nghiệp vụ**.
2. Server dùng key và `tenant_id` để kiểm tra bản ghi đã tồn tại, hoặc cố ghi theo một giao thức upsert/unique nhất quán.
3. Nếu có đơn tương ứng cùng payload, trả lại kết quả đã tạo; nếu key đã tồn tại nhưng payload khác, báo xung đột.
4. Nếu chưa có, thử transaction mới và chỉ trả thành công sau khi có kết quả commit xác định.
5. Với giao dịch có bước gọi hệ thống ngoài, thêm cơ chế idempotency/outbox để tránh phát sinh tác dụng phụ lặp lại.

Một cặp cột UNIQUE đơn thuần là **nền tảng** cho chống trùng, chưa phải toàn bộ giao thức retry. Ví dụ này giải thích vì sao lỗi kết nối nằm trong phạm vi thiết kế persistence và durability.

### 8.2. Trong JPA/Spring, flush và commit nằm ở đâu?

Ví dụ khái niệm:

~~~java
import jakarta.persistence.EntityManager;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final EntityManager entityManager;

    public OrderService(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Transactional
    public void create(OrderEntity order) {
        entityManager.persist(order);
        entityManager.flush();

        // Lệnh flush không tương đương transaction đã commit.
        // Transaction manager sẽ xử lý COMMIT khi phương thức
        // kết thúc thành công qua cơ chế quản lý transaction.
    }
}
~~~

`OrderEntity` là entity do ứng dụng tự định nghĩa; mã minh họa này không phải chương trình hoàn chỉnh. Trong cấu hình Spring phổ biến, commit được transaction interceptor thực hiện **sau khi thân phương thức được gọi qua proxy hoàn tất**. Thế nên mã chạy ở cuối phương thức `@Transactional` chưa tự bảo đảm commit đã xảy ra. Việc phát sự kiện bên ngoài hoặc trả trạng thái đã commit cần được thiết kế phù hợp với ranh giới transaction thật, ví dụ thông qua transaction synchronization sau commit hoặc outbox.

## 9. Đường đọc dữ liệu: nhiều tầng cache và ý nghĩa của cache hit

Bên cạnh đường ghi, dữ liệu đọc cũng có nhiều tầng bộ đệm:

~~~text
Java service / ORM 1st-level cache hoặc cache nghiệp vụ
            |
            v
      JDBC / SQL SELECT
            |
            v
     DB buffer pool (các trang đã đọc)
            |
            v
     OS page cache (nếu đường I/O sử dụng)
            |
            v
     Thiết bị lưu trữ
~~~

Một `SELECT` có thể được trả lời nhanh vì dữ liệu đã ở DB buffer pool; điều đó không nói gì về việc lần ghi trước đã bền vững hay chưa. Cache có vai trò **giảm độ trễ đọc**. Mức isolation/MVCC có vai trò quyết định phiên bản dữ liệu được đọc. WAL và cơ chế flush có vai trò **phục hồi dữ liệu sau crash**.

Nếu có cache ở ứng dụng hoặc tầng dịch vụ khác, dữ liệu trong đó có thể cũ sau commit của transaction khác. Đây là vấn đề **cache consistency/invalidation**, không thể giải quyết chỉ bằng `fsync`. Cũng không nên lấy việc sau restart vẫn đọc được dữ liệu để chứng minh rằng dữ liệu sẽ sống sót sau mất toàn bộ thiết bị lưu trữ.

## 10. Durability, replication và backup là ba lớp bảo vệ khác nhau

Một transaction đã bền vững trên đĩa của primary vẫn có thể mất khi ổ hoặc datacenter đó bị phá hủy. Vì vậy phải phân biệt:

| Cơ chế | Bảo vệ trước tình huống nào? | Không tự giải quyết tình huống nào? |
| --- | --- | --- |
| WAL + flush cục bộ phù hợp | Crash process/OS và mất điện trong mô hình hạ tầng được hỗ trợ | Mất toàn bộ ổ chứa WAL và dữ liệu; xóa nhầm có chủ đích |
| Replication bất đồng bộ | Có bản sao dự phòng sau khi cập nhật đã đến replica | Primary hỏng trước khi replica nhận transaction mới |
| Replication đồng bộ | Có thể giảm rủi ro mất các transaction đã xác nhận khi failover, tùy mức chờ và quy trình failover | Không mặc định bảo vệ xóa nhầm cùng được nhân bản, lỗi logic, hỏng đồng loạt |
| Backup định kỳ | Phục hồi từ bản sao lịch sử sau hỏng hóc hoặc xóa nhầm | Những thay đổi sau bản backup gần nhất nếu không có WAL/binlog để phát lại |
| Point-in-time recovery (PITR) | Phục hồi đến một mốc thời gian với backup và chuỗi WAL phù hợp | Không hữu ích nếu backup/WAL thất lạc hoặc chưa được kiểm tra khả năng restore |

Trong PostgreSQL, các mức `synchronous_commit` như `remote_write`, `on` và `remote_apply` có những điểm chờ khác nhau khi dùng synchronous standby. Việc replica đã nhận log, đã flush log hoặc đã áp dụng và sẵn sàng cho truy vấn là ba trạng thái khác nhau. Cần xem cấu hình `synchronous_standby_names`, số standby và quy trình promotion/failover trước khi tuyên bố mức RPO của cả hệ thống.

Để lượng hóa mục tiêu phục hồi:

- **RPO (Recovery Point Objective):** mức mất dữ liệu tối đa nghiệp vụ chấp nhận được, thường diễn đạt bằng khoảng thời gian hoặc tập thay đổi chưa được bảo toàn.
- **RTO (Recovery Time Objective):** thời gian khôi phục dịch vụ tối đa nghiệp vụ chấp nhận được.

RPO bằng 0 đối với một loại sự cố chỉ khả thi khi kiến trúc và quy trình failover thật sự bảo đảm không mất commit đã xác nhận trong **phạm vi loại sự cố đó**. Một cấu hình `synchronous_commit=on` trên primary đơn lẻ không tự chứng minh RPO = 0 khi ổ cứng bị mất.

### 10.1. Dữ liệu nhạy cảm xuất hiện ở nhiều lớp

Trang bảng, WAL, temporary file, cache, replica và backup đều có thể chứa dữ liệu nghiệp vụ nhạy cảm. Mã hóa và kiểm soát quyền truy cập phải xét đến toàn bộ vòng đời dữ liệu: đường truyền, file dữ liệu, WAL, bản sao, backup, khóa mã hóa và quy trình hủy dữ liệu. Xóa một hàng trong bảng không đồng nghĩa lập tức xóa mọi bản sao byte trong WAL hoặc backup.

## 11. Thực hành: quan sát trạng thái và lập bảng cam kết

### 11.1. Chuẩn bị quan sát, không thay đổi cấu hình nguy hiểm

Trên một PostgreSQL dùng để thực hành, đọc:

~~~sql
SHOW fsync;
SHOW synchronous_commit;
SHOW full_page_writes;

SELECT now() AS observed_at,
       pg_current_wal_lsn() AS wal_position;
~~~

`pg_current_wal_lsn()` trả về vị trí log hiện tại; nó không tự chứng minh toàn bộ WAL đến vị trí đó đã flush lên ổ và không phải bằng chứng duy nhất về durability. Để đo lượng WAL theo thời gian, có thể theo dõi thống kê WAL tương ứng phiên bản PostgreSQL và kết hợp công cụ giám sát I/O của hệ điều hành.

Chạy transaction tạo một đơn hàng mẫu bằng SQL ở phần 6. Sau khi commit, truy vấn:

~~~sql
SELECT id, tenant_id, request_key, total_amount, created_at
FROM durable_orders
WHERE tenant_id = 42
  AND request_key = 'checkout-20261122-0001';
~~~

Giá trị trả về chứng minh hàng **hiện có thể truy vấn** theo kết nối và snapshot đó; chưa phải một phép thử mất điện. Không thử nghiệm độ bền bằng cách cưỡng bức tắt nguồn máy sản xuất.

### 11.2. Thiết kế fault-injection có kiểm soát

Trong môi trường disposable/staging, nhóm kỹ thuật có thể chuẩn bị bộ kiểm thử:

1. Ghi một danh sách `request_key` duy nhất và chỉ đánh dấu “acknowledged” sau khi client nhận `COMMIT` thành công.
2. Tạo sự cố tại những điểm đã lên kế hoạch: trước khi gửi SQL, sau SQL trước COMMIT, trong lúc chờ COMMIT, sau COMMIT.
3. Khởi động DB hoặc tiến trình liên quan theo quy trình đã được môi trường thử nghiệm hỗ trợ.
4. Dùng kết nối mới tra cứu từng key và phân loại: có commit, rollback, hoặc **client không chắc kết quả**.
5. Đối chiếu các giao dịch được xác nhận với mức cam kết dự kiến; đo thời gian recovery và xem log DB.
6. Thực hành phục hồi backup/PITR và kiểm tra RPO, RTO riêng cho sự cố mất ổ hoặc mất node.

Khởi động lại DB bằng thao tác dừng dịch vụ bình thường có thể flush các trang và đóng file sạch sẽ; nó **không mô phỏng crash mất điện**. Muốn chứng minh cam kết trong tình huống mất nguồn, cần cơ chế fault injection phù hợp và sự phối hợp của đội vận hành trên hạ tầng thử nghiệm.

### 11.3. Bảng phân tích một yêu cầu tạo đơn

Giả định một API có ba mốc:

~~~text
A. ORM persist() / JDBC executeUpdate()
B. DB nhận COMMIT và đưa thông tin vào log
C. DB trả COMMIT thành công cho client
~~~

Hãy trả lời:

- Crash JVM giữa A và B: có quyền trả kết quả “đơn đã bền vững” không?
- Crash database sau C nhưng data page chưa được ghi hết: vì sao WAL có thể giúp?
- Network timeout giữa B và C: server có thể làm gì để biết request đã commit?
- Mất cả data file lẫn WAL cục bộ sau C: cần lớp bảo vệ nào khác?

**Đáp án gợi ý:** Chưa được xác nhận commit ở mốc A; sau C, WAL đã được flush theo cấu hình phù hợp nên phục hồi có thể redo; khi timeout trong khoảng B/C cần kiểm tra bằng idempotency key qua kết nối mới; khi mất toàn bộ phương tiện lưu trữ phải dựa vào bản sao/backup và chính sách RPO.

## 12. Những ngộ nhận thường gặp

**“Thấy JDBC trả về số hàng cập nhật là đã an toàn sau mất điện.”** Nếu transaction chưa commit thì vẫn có thể rollback. Độ bền của commit còn phụ thuộc cấu hình DB và lưu trữ.

**“Gọi `EntityManager.flush()` là ghi bền vững.”** Flush đồng bộ trạng thái ORM với SQL; transaction vẫn có thể thất bại hoặc rollback.

**“Khi DB trả COMMIT, mọi data page đã có trên SSD.”** Với WAL, DB có thể xác nhận commit sau khi log cần thiết bền vững, còn data page được ghi ra sau và phục hồi bằng redo khi cần.

**“`write()` hoặc `BufferedOutputStream.flush()` là giống `fsync()`.”** Các thao tác đẩy bộ đệm ở mức khác nhau và có cam kết khác nhau.

**“Cứ bật `synchronous_commit=on` là tuyệt đối không bao giờ mất dữ liệu.”** Bảo đảm còn phụ thuộc `fsync`, thiết bị, replication, backup và mô hình sự cố.

**“Nếu `commit()` ném exception thì chắc chắn đã rollback.”** Mất kết nối khi nhận phản hồi commit có thể khiến client không biết giao dịch đã commit hay chưa.

**“Replication là backup.”** Replica thường sao chép thay đổi, kể cả xóa nhầm; backup lịch sử và restore có vai trò khác.

**“Dữ liệu SELECT nhìn thấy là dữ liệu đã flush xuống thiết bị.”** Visibility, cache hit và durability là các khái niệm độc lập.

## 13. Bài tập vận dụng

**Bài 1 — vẽ đường ghi.** Vẽ hai nhánh từ PostgreSQL buffer pool và WAL buffer xuống hệ điều hành, rồi thiết bị. Đánh dấu nơi có thể trả `COMMIT` thành công trước khi data page được ghi. Giải thích mỗi tầng buffer đem lại lợi ích gì và tạo rủi ro gì khi mất điện.

**Bài 2 — khẳng định nào đúng?** Một lập trình viên gọi `entityManager.persist(order)`, `entityManager.flush()`, gửi email “đơn hàng thành công”, rồi transaction rollback do lỗi UNIQUE ở câu lệnh sau. Giải thích trạng thái DB và email. Đề xuất dùng outbox hoặc phát thông báo theo cơ chế sau commit.

**Bài 3 — mất phản hồi COMMIT.** Client có idempotency key `k-731` bị timeout đúng lúc commit. Đề xuất schema UNIQUE theo tenant và thuật toán truy vấn trạng thái trước khi retry. Giải thích vì sao gọi lại `INSERT` với request key mới có thể tạo đơn trùng.

**Bài 4 — phân tích yêu cầu RPO.** Một hệ thống ghi thanh toán đặt mục tiêu không mất commit đã xác nhận ngay cả khi một node lưu trữ hỏng. Chỉ dùng WAL của primary có đủ không? Cần xem xét kiểu replication nào, mức chờ nào, chính sách failover, backup và kiểm thử restore nào? Nêu rõ loại sự cố được bao phủ.

**Bài 5 — đo đánh đổi hiệu năng.** Trên hệ thống test, so sánh p95 `COMMIT`, WAL throughput, I/O latency và kết quả crash recovery ở các cấu hình được đội vận hành chấp thuận. Tránh dùng production làm nơi thử thay đổi `fsync` hoặc cưỡng bức mất điện. Đánh giá bằng mục tiêu RPO/RTO và chi phí phục hồi, không chỉ bằng throughput.

## Ghi nhớ

Dữ liệu bền vững đi qua **nhiều tầng bộ đệm**: object và ORM/JDBC trong Java, bộ nhớ của database, page cache của hệ điều hành và tầng lưu trữ vật lý. **Flush của ứng dụng, thực thi statement, COMMIT và flush bền vững không phải cùng một sự kiện.** Với PostgreSQL dùng WAL và cấu hình an toàn, commit có thể được xác nhận khi log cần thiết đã bền vững, dù trang dữ liệu còn ở RAM; WAL cho phép phục hồi sau crash.

Thiết kế persistence cho Java cần đặt ranh giới xác nhận nghiệp vụ sau commit, xử lý trạng thái không chắc chắn khi mất kết nối bằng idempotency, và phối hợp WAL, thiết bị lưu trữ, replication, backup cùng thử nghiệm restore theo đúng mô hình sự cố và yêu cầu RPO/RTO.
