# Xử lý tiến trình dừng, hệ điều hành dừng và thiết bị lỗi

Ứng dụng Java có thể ghi dữ liệu thành công rồi gặp sự cố ngay sau đó: tiến trình Java bị dừng, tiến trình cơ sở dữ liệu bị crash, hệ điều hành mất điện, hoặc ổ lưu trữ hỏng hoàn toàn. Các tình huống nghe giống nhau nhưng đòi hỏi **những cơ chế phục hồi khác nhau**. Một transaction đã **COMMIT** có thể sống sót qua việc khởi động lại DBMS nhờ nhật ký ghi trước; tuy nhiên, nhật ký nằm trên thiết bị đã hỏng cũng không tự cứu được dữ liệu nếu không có bản sao hoặc bản sao lưu ở nơi khác.

Đây là bài học thuộc chương **Độ bền dữ liệu** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**. Trong ranh giới persistence của Java, độ bền liên quan trực tiếp đến giao dịch, xác nhận commit, lỗi kết nối, cách xử lý request lặp, backup, khôi phục và lựa chọn cấu hình hiệu năng. Các ví dụ kỹ thuật dưới đây dùng **PostgreSQL** khi cần minh họa rõ cơ chế; một số nguyên tắc tương tự tồn tại trong MySQL/InnoDB hoặc DBMS khác nhưng tên cấu hình và bảo đảm có thể khác.

## 1. Độ bền (durability) thực sự cam kết điều gì?

**Durability** là chữ **D** trong **ACID**: khi DBMS xác nhận một transaction đã commit theo cấu hình độ bền đã chọn, các thay đổi được ghi nhận phải tồn tại qua những loại lỗi mà cơ chế lưu trữ của hệ thống được thiết kế để chịu đựng.

Câu hỏi quan trọng là **“tồn tại qua lỗi nào?”**, vì mức bảo đảm phụ thuộc:

- DBMS có ghi nhật ký và xác nhận commit theo chế độ đồng bộ hay không.
- Hệ điều hành và phần cứng lưu trữ có thực sự bảo đảm các lần yêu cầu ghi/flush hay không.
- Lỗi chỉ làm mất bộ nhớ của một tiến trình, làm mất RAM của toàn máy, hay làm mất **cả phương tiện chứa dữ liệu**.
- Dữ liệu có replica hoặc backup thuộc miền lỗi (failure domain) khác hay không.
- Có sẵn nhật ký hoặc backup đủ mới, toàn vẹn và có thể khôi phục hay không.

Ví dụ: PostgreSQL với cơ chế flush WAL thông thường có thể phục hồi những transaction đã commit sau khi tiến trình database bị crash hoặc máy mất điện, **với giả định thiết bị ghi bền vững theo đúng các yêu cầu flush**. Nhưng một ổ đĩa vật lý hỏng không đọc được, chứa cả data file lẫn WAL, có thể khiến bản ghi trên ổ ấy mất; muốn khôi phục phải dùng bản sao/backup độc lập.

**Durability khác availability:** sau khi crash, hệ thống có thể cần thời gian khởi động lại để đọc WAL và phục hồi trước khi truy vấn được. Dữ liệu có thể không mất, trong khi dịch vụ vẫn tạm thời gián đoạn.

## 2. Phân loại ba tầng sự cố

| Sự cố | Phần nào biến mất hoặc dừng? | Cơ chế xử lý chính | Điều không được tự suy ra |
|---|---|---|---|
| **Tiến trình ứng dụng Java dừng** | RAM của tiến trình, thread, connection phía client | DBMS giữ transaction đã commit; session chưa commit sẽ được kết thúc và rollback khi DB phát hiện ngắt kết nối | Không suy ra request đã thất bại nếu client chết ngay sau COMMIT |
| **Tiến trình DBMS dừng bất ngờ** | Bộ nhớ riêng của DBMS; OS có thể vẫn chạy, dữ liệu đĩa còn | DBMS khởi động lại, kiểm tra trạng thái và **crash recovery bằng WAL/redo** | Không suy ra mọi giao dịch đang chạy đều đã commit |
| **Hệ điều hành dừng/mất điện** | RAM và các bộ đệm chưa ghi bền vững của máy có thể mất | Khởi động máy, cơ chế WAL, fsync/flush và recovery của DBMS | Không suy ra mọi dữ liệu từng được ghi vào page cache đều sống sót |
| **Thiết bị lưu trữ lỗi hoặc mất** | Một phần hoặc toàn bộ data file, WAL, filesystem có thể không đọc được | Chuyển sang bản sao còn tin cậy, khôi phục **backup + WAL archive/PITR**, thay phần cứng | WAL trên chính thiết bị đã mất không phải một bản backup |

Ba mức được nêu trong tiêu đề bài học là **tiến trình dừng, hệ điều hành dừng và thiết bị lỗi**. Trong mức “tiến trình”, cần phân biệt **tiến trình Java** với **tiến trình DBMS**: chỉ DBMS bị crash mới kích hoạt crash recovery của chính DBMS.

### 2.1. Khi ứng dụng Java bị dừng

Giả sử Java service gọi:

~~~text
BEGIN -> INSERT order -> COMMIT -> gửi HTTP response
~~~

Có bốn thời điểm khác nhau:

1. Java chết **trước khi gửi COMMIT**: transaction chưa xác nhận sẽ không được ghi nhận; phía DB cần kết thúc/rollback phiên chưa commit khi nhận ra kết nối đã mất.
2. Java gửi COMMIT nhưng chết **trước khi nhận phản hồi**: DB có thể đã commit thành công hoặc chưa; phía ứng dụng **không biết kết quả chỉ từ sự cố tiến trình**.
3. Java **đã nhận COMMIT thành công** rồi chết trước khi trả HTTP response: dữ liệu có thể đã commit, dù người dùng thấy lỗi/timeout.
4. Java trả response thành công rồi chết: response không phải cơ chế lưu trữ; phải dựa vào bảo đảm commit đã được sử dụng trước đó.

Vì vậy, **“request HTTP không nhận 200” không có nghĩa “transaction không được commit”**. Đây là một nguồn gây tạo đơn hàng hai lần nếu retry không có idempotency key.

### 2.2. Khi tiến trình DBMS bị crash

DBMS có thể đã thay đổi trang dữ liệu trong **buffer pool**, nhưng chưa ghi tất cả trang đó vào data file trên ổ đĩa. Sau khi restart, DBMS đọc trạng thái checkpoint và nhật ký WAL để tái lập các thay đổi cần thiết, bảo đảm database trở lại trạng thái nhất quán.

Một số transaction đã commit được **redo** nếu dữ liệu trong trang chưa phản ánh đủ, còn transaction chưa được xác nhận commit không được trở thành thay đổi đã commit. Cách đánh dấu commit, quản lý rollback và phục hồi cụ thể khác nhau theo DBMS.

Trong mô hình PostgreSQL, cơ chế MVCC và WAL cho phép khôi phục trạng thái nhất quán mà không bắt buộc mọi dirty page đã được ghi xuống data file tại thời điểm COMMIT.

### 2.3. Khi hệ điều hành hoặc toàn máy dừng

Crash của OS, kernel panic hoặc mất điện nghiêm trọng hơn process crash vì **page cache của hệ điều hành và những dữ liệu chỉ còn trong RAM có thể biến mất**. Một lời gọi **write() thành công** thường chỉ chứng minh dữ liệu đã được chấp nhận vào các tầng bộ đệm thích hợp, không đủ để khẳng định dữ liệu tồn tại sau mất điện.

DBMS dùng cơ chế flush/sync và bảo đảm thứ tự ghi để buộc nhật ký cần thiết đến lớp lưu trữ được coi là bền vững trước khi xác nhận commit, theo cấu hình độ bền đã chọn. Bảo đảm ấy còn phụ thuộc ổ đĩa, controller, hệ thống tệp, máy ảo và phần cứng **thực thi đúng yêu cầu flush**.

### 2.4. Khi thiết bị lỗi

Tình huống này khác hẳn crash thông thường: hệ thống có thể không còn đọc được những byte cần thiết để phục hồi. Một ổ chứa cả WAL và data file bị hỏng có thể làm mất cả dữ liệu gốc lẫn nhật ký dùng để redo.

Khi đó cần **bản sao ở failure domain độc lập**, backup có thể restore, hoặc cơ chế replication/hạ tầng lưu trữ chịu lỗi được thiết kế phù hợp. Replication giảm thời gian gián đoạn và mất dữ liệu trong một số sự cố nhưng **không thay thế backup**, vì thao tác DELETE nhầm hoặc corruption logic có thể được sao chép sang replica.

## 3. Đường đi của một thay đổi: từ Java đến thiết bị

Một câu lệnh SQL không đi thẳng từ Java vào một ô “ổ cứng đã bền vững”. Có nhiều lớp:

~~~text
Java application
    |
    | JDBC PreparedStatement / transaction
    v
DBMS: thực thi SQL, kiểm tra ràng buộc, sửa buffer trong RAM
    |
    +--> WAL buffer (nhật ký các thay đổi cần thiết)
    |         |
    |         +--> WAL file / OS cache
    |                   |
    |                   +--> flush/sync đến tầng lưu trữ bền vững
    |
    +--> Data buffer (dirty pages)
              |
              +--> data files, thường ghi xuống sau qua background writer/checkpoint

COMMIT được xác nhận theo chế độ durability và điều kiện flush của DBMS.
~~~

**Write-Ahead Logging (WAL)** là nguyên tắc: thông tin nhật ký cần thiết để phục hồi một thay đổi phải được bảo đảm ghi trước khi trang dữ liệu liên quan được coi là ghi bền vững. Nó cho phép DBMS xác nhận commit mà không phải ngay lập tức ghi mọi trang dữ liệu bị thay đổi xuống data file.

Để hiểu sức mạnh của WAL, cần tách ba trạng thái:

- **Đã thực thi trong bộ nhớ DB:** câu UPDATE đã thay đổi một trang trong buffer; mất RAM trước khi log đủ bền vững có thể khiến thay đổi ấy không tồn tại sau restart.
- **WAL phục hồi cần thiết đã được flush:** DBMS có căn cứ để khôi phục sau crash theo cấu hình.
- **Data page đã ghi ra file:** không bắt buộc phải xảy ra ngay tại COMMIT; checkpoint và background writer thực hiện dần.

Đừng nhầm **WAL** với một hệ thống sao lưu độc lập. WAL là một phần của cơ chế đảm bảo nhất quán và phục hồi; nếu WAL cùng data bị mất, cần nguồn phục hồi ngoài thiết bị đó.

## 4. Crash recovery: WAL, checkpoint và redo

Giả sử transaction T1 ghi dữ liệu và commit lúc 10:00:00. Trước lúc dirty page được ghi xuống data file, tiến trình DBMS chết lúc 10:00:01.

~~~text
Trước crash:
  WAL:      [ghi thay đổi T1][commit T1] ---- flush bền vững
  Data file:          [trang còn phiên bản cũ]
                             |
                          DB crash
                             |
Khởi động lại:
  Đọc checkpoint + WAL cần thiết
  REDO các thay đổi đã có nhật ký hợp lệ
  Thiết lập trạng thái transaction đúng
  Database trở lại trạng thái nhất quán
~~~

### 4.1. Checkpoint là gì?

**Checkpoint** giúp DBMS có một mốc phục hồi và giảm lượng WAL phải đọc lại khi restart. Nó đưa các trang dữ liệu phù hợp ra hệ thống lưu trữ và ghi nhận thông tin cần thiết để xác định điểm bắt đầu recovery.

Checkpoint **không thay thế WAL** và không có nghĩa “mọi transaction chỉ bền vững khi checkpoint chạy”. Trong một cấu hình WAL đồng bộ đúng, transaction đã commit có thể được khôi phục nhờ WAL dù data page chưa kịp được checkpoint.

Đổi lại, checkpoint quá dồn dập có thể gây I/O tăng đột ngột; checkpoint thưa hơn có thể kéo dài lượng WAL cần replay và thời gian recovery. Cấu hình phải dựa trên tải thực tế và mục tiêu phục hồi.

### 4.2. Redo khác rollback khi xử lý crash

- **Redo:** tái áp dụng các thay đổi đã được WAL ghi nhận cần thiết để database nhất quán và phản ánh commit đã bền vững.
- **Rollback/loại bỏ transaction chưa commit:** đảm bảo công việc dang dở không bị coi như đã commit.

Không nên hiểu một cách cơ học rằng DBMS luôn chạy một câu lệnh SQL **ROLLBACK** cho từng transaction trước crash. Cách xử lý phụ thuộc kiến trúc phục hồi, MVCC và metadata transaction. Đối với PostgreSQL, tính hiển thị theo trạng thái commit và phục hồi WAL cùng đảm bảo transaction chưa commit không hiển thị như dữ liệu đã xác nhận.

### 4.3. Vì sao có “torn page”?

Trang dữ liệu DB thường lớn hơn đơn vị ghi nguyên tử thực tế của phần cứng. Nếu mất điện khi đang ghi một trang, một phần trang có thể là dữ liệu mới, phần còn lại là dữ liệu cũ (**torn page**). Đây không đơn thuần là “thiếu một transaction” mà có thể làm trang mất tính toàn vẹn.

PostgreSQL có cơ chế **full_page_writes**: trong những điều kiện nhất định, WAL chứa ảnh trang đầy đủ để giúp khôi phục khi có nguy cơ ghi trang không trọn vẹn. Điều đó bổ trợ WAL và giả định I/O đáng tin, chứ không bảo vệ trước việc toàn bộ thiết bị chứa WAL/data bị mất.

## 5. Sự khác biệt giữa write, flush, fsync và COMMIT

Một hiểu lầm thường gặp: **lệnh INSERT trả thành công** đồng nghĩa dữ liệu đã bền vững sau mất điện.

| Khái niệm | Điều có thể hiểu | Giới hạn |
|---|---|---|
| **SQL INSERT/UPDATE thành công** | DBMS đã xử lý câu lệnh trong transaction hiện tại | Nếu transaction chưa COMMIT, có thể bị rollback |
| **write vào file/OS cache** | Hệ điều hành đã nhận dữ liệu ở lớp đệm | Dữ liệu có thể chưa đến thiết bị bền vững |
| **fsync/fdatasync/flush theo hệ quản trị** | Yêu cầu hệ lưu trữ làm bền vững dữ liệu cần thiết | Phụ thuộc OS/driver/controller/thiết bị thực hiện đúng cam kết |
| **COMMIT trả thành công** | Transaction được DBMS xác nhận theo cấu hình commit hiện hành | Một số chế độ ưu tiên hiệu năng có thể chấp nhận mất giao dịch mới commit khi crash |
| **Backup đã hoàn tất và kiểm tra restore** | Có nguồn phục hồi độc lập tại điểm backup | Không nhất thiết chứa mọi transaction sau thời điểm backup |

Khi dùng PostgreSQL với **fsync=on** và **synchronous_commit=on** trong cấu hình local bình thường, backend đợi WAL commit cần thiết được flush theo cơ chế bền vững trước khi trả COMMIT thành công. Điều này bảo vệ các transaction đã xác nhận trước nhiều loại process/OS crash **nếu phần cứng và tầng lưu trữ tuân thủ các yêu cầu ghi bền vững**.

Nếu bật chế độ ghi không đồng bộ, cần chấp nhận một cửa sổ mất các transaction mới được báo commit khi hệ thống crash. Đó là một đánh đổi có chủ đích giữa độ trễ ghi và độ bền, không phải một chi tiết “DB sẽ tự lo”.

## 6. Những cấu hình PostgreSQL liên quan

Có thể đọc cấu hình hiện tại bằng các câu lệnh chỉ đọc:

~~~sql
SHOW fsync;
SHOW synchronous_commit;
SHOW full_page_writes;
SHOW wal_level;
SHOW archive_mode;
~~~

### 6.1. fsync

Với **fsync=on**, PostgreSQL yêu cầu hệ điều hành flush dữ liệu và WAL tại các điểm cần thiết để bảo vệ tính bền vững và nhất quán sau crash. Đây là cấu hình cơ bản của hệ thống production sử dụng lưu trữ có bảo đảm.

**Tắt fsync** có thể làm tăng hiệu năng benchmark nhưng trong trường hợp OS crash hoặc mất điện có thể gây **mất hoặc hỏng dữ liệu ở mức không phục hồi được chỉ bằng WAL hiện có**. Vì vậy, không dùng **fsync=off** như một mẹo tăng tốc cho dữ liệu production quan trọng.

### 6.2. synchronous_commit

**synchronous_commit** điều khiển mức đợi của COMMIT đối với việc ghi WAL; các chế độ cụ thể còn tương tác với cấu hình replication đồng bộ.

- Với cấu hình thông thường **on**, local WAL liên quan transaction được flush theo mức đảm bảo của DBMS trước khi xác nhận commit.
- Với **off**, PostgreSQL có thể trả commit trước khi WAL được flush bền vững. Nếu server/OS crash trong cửa sổ đó, một số transaction đã được báo commit có thể **biến mất sau recovery**, dù PostgreSQL vẫn thiết kế để không làm hỏng cấu trúc database khi fsync còn được bật.
- Khi dùng **synchronous replication**, các chế độ như **remote_write**, **remote_apply** và **on** có ý nghĩa xác nhận khác nhau trên standby. Không suy luận chỉ từ tên “on” rằng mọi replica đã apply và hiển thị dữ liệu.

Không nên tự ý hạ synchronous_commit cho dữ liệu thanh toán, số dư hoặc nghiệp vụ không chấp nhận mất transaction đã xác nhận. Một số thao tác tạm thời có thể chấp nhận rủi ro, nhưng cần ghi rõ RPO và chính sách nghiệp vụ.

### 6.3. full_page_writes

**full_page_writes=on** giúp PostgreSQL phục hồi trong tình huống ghi trang bị xé sau crash. Tắt cấu hình này chỉ vì muốn ít WAL hơn có thể gia tăng nguy cơ mất tính nhất quán khi thiết bị không bảo đảm ghi trang nguyên tử.

Cấu hình đúng không khắc phục ổ lưu trữ **báo đã flush nhưng thực tế vẫn giữ dữ liệu trong cache dễ mất điện**. Cần xem hệ thống tệp, RAID/controller, ổ đĩa, SAN/cloud volume và cơ chế bảo vệ điện năng.

### 6.4. WAL archive và wal_level

**wal_level**, **archive_mode** và cấu hình archive liên quan đến việc cung cấp WAL cho phục hồi/replication. **archive_mode=on** một mình **chưa đủ** để có PITR: phải có cơ chế archive hoạt động, lưu WAL an toàn, kết hợp base backup phù hợp và phải kiểm thử quy trình restore.

Cũng cần phân biệt **crash recovery sau restart** với **point-in-time recovery (PITR)**: crash recovery dùng WAL cục bộ để đưa một database đang có trở lại trạng thái nhất quán; PITR thường phục hồi từ base backup rồi replay WAL đã lưu để quay tới thời điểm hoặc LSN mong muốn.

## 7. Mất thiết bị: vì sao WAL và RAID chưa đủ?

Giả sử data file, WAL và các bản backup đều nằm trên **cùng một ổ**. Ổ hỏng hoàn toàn. Không còn byte để đọc WAL, không còn dữ liệu gốc để áp dụng WAL, cũng không còn backup để restore.

~~~text
Cấu hình có điểm lỗi chung:

  [Ổ X]
    ├── Database data files
    ├── Local WAL
    └── Backup cùng ổ
               |
          Ổ X hỏng
               |
      Mất cả dữ liệu và nguồn phục hồi
~~~

Một thiết kế có nhiều lớp giảm rủi ro:

~~~text
             PostgreSQL Primary
                    |
          +---------+----------+
          |                    |
   Standby/replica       Base backups
  miền lỗi độc lập       nơi lưu độc lập
                               |
                        Archived WAL
                       kèm retention
                               |
                       Restore/PITR test
~~~

**Replica**: giữ bản sao tương đối mới, có thể giảm thời gian chuyển dịch vụ sang máy khác khi primary lỗi. Nhưng replica có thể bị chậm, mất kết nối hoặc nhận DELETE nhầm từ primary. Cơ chế replication đồng bộ có thể giảm cửa sổ mất dữ liệu, song failover và bảo đảm RPO cụ thể còn phụ thuộc kiến trúc.

**RAID**: có thể chịu được một số lỗi ổ đĩa và tăng availability. RAID **không** thay thế backup: không chống được xóa nhầm, lỗi phần mềm hoặc nhiều ổ bị mất ngoài ngưỡng chịu lỗi.

**Backup độc lập**: giúp phục hồi sau mất thiết bị, sai thao tác, lỗi phần mềm hoặc hỏng dữ liệu. Backup cần tách failure domain, chính sách lưu giữ, phân quyền, kiểm tra tính toàn vẹn và **diễn tập restore**.

**Bảo vệ trước ransomware/lỗi quản trị:** nếu cùng tài khoản có thể xóa cả DB và backup, một sự cố hoặc sai thao tác có thể phá tất cả bản sao. Cân nhắc storage bất biến/không cho sửa và tài khoản backup riêng theo mức độ quan trọng của hệ thống.

## 8. Khái niệm RPO và RTO khi phục hồi

Hai mục tiêu cần được thống nhất với nghiệp vụ trước khi chọn kiến trúc:

- **RPO — Recovery Point Objective:** lượng dữ liệu hoặc khoảng thời gian mất dữ liệu tối đa có thể chấp nhận khi phục hồi.
- **RTO — Recovery Time Objective:** thời gian tối đa nghiệp vụ chấp nhận để phục hồi dịch vụ.

Ví dụ:

| Mô hình vận hành | RPO có thể đạt | RTO có thể đạt | Ràng buộc |
|---|---|---|---|
| Chỉ một máy DB, WAL local | Có thể bảo vệ commit qua crash của máy theo cấu hình, nhưng mất thiết bị có thể mất tất cả | Tùy restart/recovery; khi hỏng máy có thể kéo dài | Không có bản sao độc lập |
| Backup mỗi đêm, chưa lưu liên tục WAL archive | Có thể mất thay đổi từ lần backup cuối đến lúc lỗi | Tải bản backup + restore có thể tốn thời gian | Cần kiểm thử khả năng phục hồi và kiểm tra backup hợp lệ |
| Base backup + WAL archive liên tục cho PITR | Có thể phục hồi gần thời điểm mong muốn trong giới hạn WAL đã archive | Tùy dung lượng backup và lượng WAL replay | WAL chưa kịp archive có thể mất; archive phải toàn vẹn |
| Replica ở failure domain khác | RPO/RTO phụ thuộc replication lag, kiểu đồng bộ và quy trình failover | Có thể rút ngắn so với restore lớn | Không thay thế backup hoặc bảo vệ lỗi logic |

Các dòng trên là **mô tả định tính**, không phải SLA tự động. Không thể hứa “RPO=0” chỉ vì có một standby hoặc chỉ vì đặt **synchronous_commit=on** trên primary. Cần mô tả chính xác commit được xác nhận ở đâu, replication đồng bộ tới mức nào và failover xử lý các trường hợp mất liên lạc ra sao.

Nếu nghiệp vụ yêu cầu **RPO nhỏ hơn 5 phút**, chỉ backup mỗi đêm có thể không đáp ứng. Nếu yêu cầu **RTO dưới 10 phút**, phải kiểm tra quy trình failover và startup thay vì giả định restore bản backup lớn sẽ đủ nhanh.

## 9. Kịch bản ứng dụng Java: COMMIT thành công nhưng client bị dừng

Một API tạo đơn hàng nhận **request_id** từ client. Đơn được chèn vào DB, ứng dụng gọi **commit()**, nhưng JVM bị dừng trước khi trả HTTP response. Khi client gửi lại, cần tránh tạo đơn thứ hai.

### 9.1. Thiết kế schema hỗ trợ idempotency

~~~sql
CREATE TABLE order_requests (
    request_id VARCHAR(80) PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    amount NUMERIC(14, 2) NOT NULL CHECK (amount > 0),
    status VARCHAR(20) NOT NULL CHECK (status IN ('CREATED', 'CANCELLED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

**request_id** là khóa duy nhất của một yêu cầu nghiệp vụ; client dùng **cùng request_id** khi gửi lại cùng yêu cầu, không tạo mã mới mỗi lần gặp timeout. Dữ liệu ở hàng phải bao gồm đủ thông tin để đối chiếu các tham số nghiệp vụ; không được coi cùng một mã mà khác customer/amount là cùng một yêu cầu hợp lệ.

Ví dụ truy vấn đối soát:

~~~sql
SELECT customer_id, amount, status, created_at
FROM order_requests
WHERE request_id = ?;
~~~

Ký hiệu **?** là placeholder của JDBC, không phải cú pháp thực thi trực tiếp trong trình SQL console.

### 9.2. Mẫu JDBC: nhận biết kết quả commit không rõ

Đoạn Java sau minh họa tách lỗi xảy ra **trước** lúc gửi COMMIT và lỗi xảy ra **trong** lúc gọi COMMIT. Mã giả định service sở hữu một Connection mới do DataSource cấp và dùng PostgreSQL/JDBC 4.x.

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class DurableOrderService {
    private final DataSource dataSource;

    public DurableOrderService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void createOrder(
            String requestId, long customerId, BigDecimal amount
    ) throws SQLException {
        if (requestId == null || requestId.isBlank()
                || customerId <= 0 || amount == null
                || amount.signum() <= 0) {
            throw new IllegalArgumentException("Thông tin đơn hàng không hợp lệ");
        }

        try (Connection connection = dataSource.getConnection()) {
            if (!connection.getAutoCommit()) {
                throw new SQLException("Connection đã ở trong transaction khác");
            }
            connection.setAutoCommit(false);

            boolean commitAttempted = false;
            boolean transactionEnded = false;
            try {
                try (PreparedStatement insert = connection.prepareStatement(
                        "INSERT INTO order_requests "
                        + "(request_id, customer_id, amount, status) "
                        + "VALUES (?, ?, ?, 'CREATED')")) {
                    insert.setString(1, requestId);
                    insert.setLong(2, customerId);
                    insert.setBigDecimal(3, amount);
                    if (insert.executeUpdate() != 1) {
                        throw new SQLException("Không lưu được đơn hàng");
                    }
                }

                commitAttempted = true;
                connection.commit();
                transactionEnded = true;
            } catch (SQLException failure) {
                if (commitAttempted) {
                    // COMMIT đã được gọi; có thể DB đã commit rồi mất phản hồi.
                    // Không tự kết luận rollback sẽ hủy được giao dịch.
                    // Tầng gọi cần đối soát bằng requestId trên connection mới.
                    throw new CommitOutcomeUnknownException(
                            "Không xác định kết quả COMMIT của " + requestId,
                            failure);
                }

                try {
                    connection.rollback();
                    transactionEnded = true;
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            } finally {
                if (transactionEnded) {
                    connection.setAutoCommit(true);
                }
                // Nếu commit/rollback chưa rõ trạng thái, KHÔNG tự ý bật
                // autoCommit. Pool/driver phải dọn hoặc loại connection này.
            }
        }
    }

    public static final class CommitOutcomeUnknownException
            extends SQLException {
        public CommitOutcomeUnknownException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
~~~

**Diễn giải:** một lỗi ngay trong **executeUpdate()** được xử lý bằng rollback. Nếu lỗi phát sinh **trong connection.commit()**, mã chuyển sang trạng thái **không xác định**, vì có thể commit đã hoàn tất ở server nhưng phản hồi bị mất. Đóng connection là việc dọn tài nguyên; ứng dụng vẫn phải cấu hình connection pool/driver để rollback hoặc loại bỏ connection có transaction chưa rõ trạng thái. Nếu bước đóng/khôi phục cấu hình gặp lỗi thì cần giữ log/nguyên nhân và coi kết nối không an toàn để tái sử dụng.

Ví dụ không giải quyết mọi nhánh retry và UNIQUE conflict; phần đó thuộc giao thức idempotency của toàn hệ thống. Nếu client gửi lại cùng requestId và gặp **unique violation**, có thể tra hàng đã commit để xác minh customer_id, amount, status và trả lại kết quả cũ nếu khớp; nếu dữ liệu khác nhau thì báo xung đột nghiệp vụ. Không retry bằng **requestId mới** để “né” ràng buộc duy nhất.

### 9.3. Hai truy vấn đối soát

Một service có thể dùng connection mới để kiểm tra:

~~~sql
SELECT customer_id, amount, status
FROM order_requests
WHERE request_id = ?;
~~~

- **Có hàng và dữ liệu khớp:** DB có bằng chứng transaction đã commit; có thể trả kết quả tương ứng.
- **Có hàng nhưng dữ liệu khác:** khóa đã được sử dụng cho yêu cầu khác; trả lỗi xung đột.
- **Chưa thấy hàng:** chưa đủ để khẳng định chắc chắn yêu cầu cũ không thể commit nếu có transaction đang tiến hành hoặc replica còn trễ; cần phối hợp với trạng thái server, ràng buộc UNIQUE trên primary, timeout và chính sách đối soát đã thiết kế.

Khi đối soát, nên ưu tiên đọc **nguồn có thẩm quyền** (primary hoặc chế độ đọc có bảo đảm phù hợp); nếu đọc replica bất đồng bộ, có thể chưa nhìn thấy transaction mới commit.

## 10. Kiểm tra sức khỏe và quan sát PostgreSQL

Các câu lệnh sau có tính chất **đọc trạng thái**, phục vụ người vận hành có quyền phù hợp.

Kiểm tra cấu hình durability cơ bản:

~~~sql
SHOW fsync;
SHOW synchronous_commit;
SHOW full_page_writes;
SHOW archive_mode;
~~~

Kiểm tra PostgreSQL đang ở vai trò primary hay standby phục hồi:

~~~sql
SELECT pg_is_in_recovery() AS is_in_recovery;
~~~

Theo dõi số giao dịch commit/rollback ở mức database:

~~~sql
SELECT datname, xact_commit, xact_rollback, deadlocks
FROM pg_stat_database
WHERE datname = current_database();
~~~

**xact_commit** là một chỉ số thống kê về transaction commit, không phải phép kiểm tra tất cả commit đã bền vững trên mọi thiết bị. Nó cũng không thay thế thử nghiệm failover hoặc khôi phục.

Kiểm tra trạng thái archive WAL tổng quát (khi hệ thống dùng WAL archiving):

~~~sql
SELECT archived_count,
       last_archived_wal,
       last_archived_time,
       failed_count,
       last_failed_wal,
       last_failed_time
FROM pg_stat_archiver;
~~~

Nếu **failed_count** tăng, hoặc **last_archived_time** không theo kịp lưu lượng WAL khi hệ thống có transaction ghi thường xuyên, cần chẩn đoán pipeline lưu trữ WAL. Nhưng sự vắng mặt của WAL archive mới **không tự chứng minh lỗi** nếu database không tạo segment mới hoặc archive đang được tắt. Phải quan sát cùng tốc độ tạo WAL và cấu hình archive.

### 10.1. Những dấu hiệu cần cảnh báo

- Đĩa gần hết dung lượng, đặc biệt vùng lưu WAL.
- I/O latency tăng cao, flush/fsync mất thời gian bất thường.
- Process DB thường xuyên restart hoặc thông báo crash recovery kéo dài.
- WAL archive lỗi lặp lại, khoảng trống backup hoặc retention không đáp ứng PITR.
- Replica lag tăng hoặc standby không thể theo kịp primary.
- Backup không chạy, backup lỗi, hoặc lâu không có **restore test** thành công.
- Số request Java trả lỗi sau COMMIT tăng, tạo nhiều tình huống phải đối soát.

Hệ thống quan sát cần thu thập metric, log DB và log ứng dụng với **correlation_id/request_id**. Tránh ghi mật khẩu, token, thông tin thanh toán nhạy cảm hay payload cá nhân không cần thiết.

## 11. Quy trình phục hồi theo từng kiểu lỗi

### 11.1. Tiến trình Java dừng

1. Kiểm tra service còn instance khác hay không, restart ứng dụng bằng quy trình bình thường.
2. Xác định các request có phản hồi bị gián đoạn, đặc biệt quanh COMMIT.
3. Đối soát theo **request_id/operation_id** trên DB; tránh gửi lại không có idempotency.
4. Kiểm tra trạng thái pool, connection và transaction đang mở; DB sẽ xử lý phiên bị ngắt khi phát hiện connection kết thúc.
5. Đảm bảo outbox/event liên quan được gửi dựa trên dữ liệu đã commit, tránh phát hai lần.

### 11.2. Tiến trình DBMS dừng hoặc OS crash

1. Kiểm tra thiết bị và filesystem còn hoạt động an toàn, không có dấu hiệu hỏng phần cứng.
2. Khởi động DBMS theo quy trình vận hành; theo dõi **recovery log**, WAL replay và trạng thái sẵn sàng.
3. Không bỏ qua cảnh báo thiếu WAL hoặc yêu cầu phục hồi đặc biệt; một khởi động lại thành công không thay thế việc kiểm tra tính toàn vẹn.
4. Chạy truy vấn kiểm tra nghiệp vụ sau recovery: số dư, đơn hàng, ràng buộc khóa chính, dữ liệu quan trọng.
5. Ứng dụng xử lý lỗi kết nối theo policy; giao dịch trước crash chưa được xác nhận cần đối soát, nhất là nếu COMMIT outcome không rõ.
6. Ghi nhận thời gian khôi phục thực tế để so với RTO đã đặt ra.

### 11.3. Thiết bị lưu trữ lỗi hoặc database không thể đọc dữ liệu

1. **Khoanh vùng sự cố:** xác định đĩa/volume nào mất, dữ liệu và WAL còn ở đâu, replica/backup nào độc lập.
2. **Tránh làm hỏng nguồn phục hồi:** không tự ý ghi đè file dữ liệu lỗi hoặc thao tác khiến các bản backup còn tốt bị xóa.
3. Chọn phương án phù hợp với RPO/RTO: failover sang standby tin cậy hoặc **restore backup và WAL/PITR**.
4. Kiểm tra độ toàn vẹn của backup, WAL liên tục, thứ tự replay và điểm phục hồi mục tiêu; ghi nhận transaction có thể bị mất.
5. Kiểm chứng nghiệp vụ sau khi hệ thống phục vụ trở lại, đối soát những thao tác ở cửa sổ gián đoạn với hệ thống bên ngoài.
6. Sau sự cố, khắc phục nguyên nhân phần cứng, storage và cập nhật quy trình backup, monitoring, cảnh báo.

**Không phát lệnh “reset WAL” hoặc xóa file nhật ký để ép DB khởi động chỉ vì startup thất bại**. Các thao tác cứu dữ liệu ở cấp storage cần chuyên gia vận hành đánh giá trên bản sao được bảo vệ; bỏ WAL có thể làm database không nhất quán và mất cơ hội khôi phục đúng.

## 12. Backup, WAL archive và diễn tập restore

Một backup chưa được restore thành công **chưa chứng minh** có thể cứu dữ liệu khi hỏng thiết bị. Kế hoạch phục hồi nên nêu:

- **Base backup toàn vẹn:** thu thập data theo công cụ phù hợp, có metadata/thời điểm và kiểm tra tính hợp lệ.
- **WAL cần thiết cho khôi phục:** lưu liên tục và bảo đảm không thiếu các segment cần để replay tới điểm mục tiêu.
- **Vị trí độc lập:** không đặt tất cả backup trên cùng ổ, cùng máy hoặc cùng quyền quản trị dễ bị xóa đồng loạt.
- **Retention:** giữ bản backup và WAL đủ dài theo yêu cầu RPO, yêu cầu pháp lý và kế hoạch phục hồi.
- **Mã hóa và phân quyền:** backup cũng chứa dữ liệu thật; cần bảo vệ truy cập và khóa mã hóa.
- **Tài liệu restore:** nêu máy đích, thứ tự bước, credentials, cấu hình cần thiết và cách kiểm thử.
- **Restore drill định kỳ:** phục hồi vào môi trường riêng, xác nhận database mở được, chạy kiểm tra dữ liệu và đo RTO/RPO thực tế.

### 12.1. PITR làm được và không làm được gì?

**Point-in-Time Recovery (PITR)** có thể khôi phục database từ một base backup hợp lệ, sau đó replay chuỗi WAL đủ liên tục tới một mốc trước lỗi logic, ví dụ trước khi ai đó xóa nhầm hàng.

Tuy nhiên:

- PITR chỉ tới được mốc mà backup và WAL sẵn có cho phép.
- WAL archive bị trễ hoặc thiếu segment có thể giới hạn thời điểm phục hồi.
- Phục hồi toàn database về quá khứ có thể làm mất những transaction hợp lệ sau mốc đó; cần kế hoạch đối soát hoặc khôi phục riêng đối tượng tùy nghiệp vụ.
- PITR không tự phục hồi những hiệu ứng đã xảy ra **ngoài DB**, như thanh toán đã thực hiện hoặc email đã gửi.

Vì vậy, cùng với WAL và backup, hệ thống nghiệp vụ cần có **mã yêu cầu**, log kiểm toán phù hợp và cơ chế đối chiếu với hệ thống ngoài.

## 13. Kiểm thử sự cố một cách có kiểm soát

Không nên đợi mất điện hoặc hỏng ổ thật để lần đầu biết ứng dụng có phục hồi được không. Một kế hoạch kiểm thử có thể dùng môi trường **staging tách biệt, dữ liệu giả và backup được bảo vệ**.

| Kịch bản | Điều muốn kiểm tra | Bằng chứng đạt |
|---|---|---|
| Dừng tiến trình Java trước COMMIT | Request chưa commit không thành dữ liệu đã hoàn tất | Không xuất hiện bản ghi đã commit không hợp lệ |
| Dừng Java ngay sau khi gửi COMMIT | Client không tạo nghiệp vụ trùng khi gửi lại | Đối soát idempotency key trả đúng một tác dụng |
| Dừng DBMS đột ngột trên staging | DB khởi động lại bằng crash recovery | Dữ liệu đã commit hợp lệ còn; dữ liệu chưa commit không hiển thị |
| Mô phỏng OS/power loss bằng hạ tầng test được thiết kế | Xác minh flush và recovery trên nền tảng thực tế | Startup và kiểm tra dữ liệu đạt, không hứa chắc nếu storage không hỗ trợ mô phỏng |
| Mất volume/ổ dữ liệu thử nghiệm | Phục hồi từ replica/backup độc lập | DB phục hồi trên môi trường mới, có đo RPO/RTO |
| Mất một đoạn WAL archive giả lập | Xác định giới hạn của PITR và cảnh báo | Quy trình nhận ra gap và không báo restore thành công sai |
| Restore backup gần nhất | Kiểm tra backup đọc được và thao tác phục hồi đầy đủ | DB mở được, kiểm tra ràng buộc/ứng dụng thành công |

**Nguyên tắc an toàn:** không chạy thử kill DB hay mô phỏng phá storage trên production. Nếu thử nghiệm liên quan I/O nguy hiểm, phải cô lập môi trường và xác nhận có đường phục hồi cho chính môi trường test.

### 13.1. Bài thử nhỏ về durability logic

Trong staging, có thể tạo bảng ghi nhận request_id và trạng thái đã commit:

~~~sql
CREATE TABLE durability_probe (
    request_id VARCHAR(80) PRIMARY KEY,
    note TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

BEGIN;
INSERT INTO durability_probe (request_id, note)
VALUES ('probe-001', 'committed sample');
COMMIT;
~~~

Sau khi staging database được restart theo quy trình test, kiểm tra:

~~~sql
SELECT request_id, note
FROM durability_probe
WHERE request_id = 'probe-001';
~~~

Việc bản ghi xuất hiện sau **một lần restart bình thường** chỉ chứng minh một kịch bản cụ thể; không chứng minh khả năng chống mọi lỗi thiết bị hoặc lỗi phần cứng. Cần kết hợp fault injection được kiểm soát và diễn tập restore để đánh giá mục tiêu thực tế.

## 14. Sai lầm thường gặp

| Hiểu nhầm | Giải thích chính xác |
|---|---|
| “SQL INSERT thành công nghĩa là tồn tại qua mất điện.” | Nếu chưa commit hoặc chế độ WAL/flush chưa đáp ứng, không có bảo đảm đó. |
| “COMMIT trả thành công chứng minh mọi replica đã có dữ liệu.” | Phụ thuộc cấu hình đồng bộ và mức xác nhận của replication. |
| “Java timeout là database rollback.” | Kết quả COMMIT có thể đã xảy ra; cần idempotency và đối soát. |
| “WAL chính là backup.” | WAL cục bộ phục vụ recovery; mất cùng thiết bị thì có thể mất cả WAL. |
| “Có RAID thì không cần backup.” | RAID không chống xóa nhầm, lỗi logic hoặc mất nhiều thiết bị. |
| “Checkpoint chạy mới làm transaction bền vững.” | WAL được flush đúng cách cho phép redo commit trước khi dirty page được checkpoint. |
| “fsync chỉ ảnh hưởng tốc độ, tắt cũng không sao.” | Tắt fsync có thể khiến dữ liệu mất/hỏng không thể recovery sau OS crash. |
| “Replica sẽ chống được xóa dữ liệu nhầm.” | DELETE hợp lệ hoặc lỗi ứng dụng thường được nhân bản sang replica. |
| “Backup hiện trạng tốt vì job trả success.” | Phải kiểm thử restore và xác thực dữ liệu. |
| “Data file còn thì WAL hỏng không ảnh hưởng.” | DB có thể không khôi phục được trạng thái nhất quán; phải đánh giá recovery. |
| “Restart DBMS thành công nghĩa là API không cần xử lý request lặp.” | Client có thể chưa biết transaction đã commit; phải xử lý retry an toàn. |
| “RPO bằng 0 và RTO gần 0 chỉ cần một máy DB.” | Không thể suy ra mục tiêu đó từ một máy; cần kiến trúc và kiểm thử đáp ứng rõ ràng. |

## 15. Bài tập tự kiểm tra

### Bài 1 — Tiến trình Java bị dừng

API gọi **commit()** cho đơn hàng 1001. JVM chết trước khi trả response. Client gửi lại cùng yêu cầu. Tại sao không được chèn một đơn mới với request_id mới ngay lập tức?

**Gợi ý:** giao dịch đầu có thể đã commit. Dùng request_id ổn định để tra trạng thái và áp dụng giao thức idempotent nhằm tránh ghi kép.

### Bài 2 — Process crash với dirty page

Một transaction đã commit, WAL cần thiết được flush an toàn nhưng dirty page chưa được ghi vào data file. Tiến trình DBMS crash. Cơ chế nào có thể phục hồi thay đổi?

**Gợi ý:** crash recovery dùng WAL đã bền vững và checkpoint để redo, nên commit không cần đợi ghi mọi dirty page xuống data file.

### Bài 3 — OS crash và dữ liệu trong cache

DBMS đã gọi write vào file WAL nhưng chưa hoàn tất flush theo bảo đảm bền vững. Máy mất điện. Có thể khẳng định transaction ấy tồn tại sau restart không?

**Gợi ý:** không. Dữ liệu có thể chỉ nằm trong RAM/OS cache. Cần cấu hình fsync/flush phù hợp và storage thật sự tuân thủ.

### Bài 4 — Mất thiết bị

Ổ duy nhất chứa data, WAL và backup bị hỏng. WAL có thể tự phục hồi dữ liệu không?

**Gợi ý:** không có nguồn WAL/data để đọc. Cần backup hoặc replica ở failure domain độc lập; mọi nguồn phục hồi trên cùng ổ đều có thể mất.

### Bài 5 — Thiết kế RPO/RTO

Hệ thống có yêu cầu **RPO tối đa 5 phút** và **RTO tối đa 15 phút**, nhưng chỉ chạy backup mỗi 24 giờ. Thiết kế này có đủ không?

**Gợi ý:** không đủ để bảo đảm RPO; cần cơ chế ghi nhận dữ liệu ngoài đĩa hỏng, như WAL archive/replica có cấu hình đáp ứng. RTO phải đo qua restore/failover thực nghiệm.

### Bài 6 — synchronous_commit

Một bảng dữ liệu tạm chấp nhận mất vài transaction mới nhất, nhưng hệ thống thanh toán không chấp nhận mất giao dịch được xác nhận. Có nên bật synchronous_commit=off cho toàn database?

**Gợi ý:** không nên áp dụng chung khi nghiệp vụ có yêu cầu độ bền khác nhau. Phải chọn chính sách theo nghiệp vụ và hiểu mất dữ liệu đã báo commit là rủi ro có thật với chế độ off.

### Bài 7 — Backup và replica

Sau khi một lệnh DELETE nhầm được commit, replica cũng đã nhận DELETE. Có thể chỉ failover sang replica để lấy lại hàng đã xóa không?

**Gợi ý:** thông thường không, vì replica đã sao chép thay đổi. Cần backup/PITR hoặc cơ chế lịch sử phù hợp, rồi đối soát những thay đổi hợp lệ sau thời điểm phục hồi.

### Bài 8 — Kết quả COMMIT không rõ

Ứng dụng Java bắt SQLException đúng lúc commit, sau đó gọi rollback thành công. Có được kết luận giao dịch chắc chắn chưa commit không?

**Gợi ý:** không. Nếu DB đã commit trước khi phản hồi bị mất, rollback sau đó không thể hoàn tác commit đã xảy ra; phải đối soát trên nguồn dữ liệu có thẩm quyền.

## 16. Ghi nhớ và áp dụng

**Tiến trình dừng** thường đòi hỏi khởi động lại và đối soát transaction chưa rõ kết quả. **Hệ điều hành dừng hoặc mất điện** đòi hỏi WAL, flush/fsync, checkpoint và recovery hoạt động đúng, cùng phần cứng lưu trữ tuân thủ bảo đảm ghi. **Thiết bị lỗi hoặc mất** đòi hỏi nguồn phục hồi ở failure domain độc lập như replica phù hợp hoặc backup có thể restore, có thể kết hợp WAL archive/PITR.

Trong Java, lớp persistence phải coi COMMIT là ranh giới dữ liệu và **không suy ra thành bại chỉ từ HTTP timeout hoặc mất kết nối**. Thiết kế request_id/idempotency, quản lý transaction rõ ràng, quan sát lỗi recovery và đối soát nghiệp vụ khi kết quả chưa xác định. Về vận hành, hãy quy đổi yêu cầu độ bền thành **RPO/RTO**, theo dõi backup/WAL/replica, và diễn tập khôi phục để xác nhận hệ thống thật sự có thể quay lại trạng thái đúng sau sự cố.
