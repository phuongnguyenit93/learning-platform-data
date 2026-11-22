# SCN, checkpoint và quan hệ giữa redo, undo, dữ liệu đã commit

## 1. Bài toán kiến trúc: một giao dịch đã `COMMIT` nằm ở đâu?

Giả sử ứng dụng chuyển 500.000 đồng từ tài khoản A sang tài khoản B. Oracle thực hiện hai lệnh `UPDATE` trong cùng transaction rồi nhận `COMMIT`. Ứng dụng nhận thông báo thành công; ngay sau đó máy chủ bị mất điện. Dù các data block của hai tài khoản có thể **chưa được ghi xuống datafile**, Oracle vẫn có thể khôi phục cả giao dịch đã commit nhờ **redo** được ghi bền vững. Ngược lại, một data block đã được ghi xuống datafile có thể chứa một thay đổi **chưa commit**; thay đổi đó không được người dùng khác nhìn thấy và sẽ bị hoàn tác khi cần.

Để giải thích đúng các hiện tượng này, cần phân biệt năm khái niệm:

1. **SCN (System Change Number)**: mốc thứ tự logic để Oracle sắp xếp thay đổi, commit và xây dựng ảnh dữ liệu nhất quán.
2. **Redo**: thông tin để **lặp lại** các thay đổi đối với database block, được LGWR ghi vào online redo log.
3. **Undo**: thông tin để **hoàn tác** thay đổi và tái tạo phiên bản dữ liệu trước đó cho read consistency.
4. **Checkpoint**: cơ chế điều phối DBWn đẩy dirty buffer xuống datafile và ghi nhận mốc phục hồi, giảm phần redo phải áp dụng khi instance bị lỗi.
5. **Commit**: mốc kết thúc transaction thành công; với commit đồng bộ thông thường, commit record cùng redo cần thiết đã bền vững trước khi Oracle trả thành công cho client.

Điểm quan trọng nhất: **`COMMIT` không có nghĩa là Oracle phải ghi ngay toàn bộ data block của transaction xuống datafile; `CHECKPOINT` cũng không phải là thao tác commit transaction.**

## 2. Bức tranh bộ nhớ và đĩa: nơi các thành phần gặp nhau

```text
                          ỨNG DỤNG / USER SESSION
                                  │
                             UPDATE/INSERT
                                  │
                                  ▼
                         Oracle server process
                                  │
                 ┌────────────────┴─────────────────┐
                 │                                  │
                 ▼                                  ▼
       Database Buffer Cache              Redo Log Buffer
       ┌────────────────────┐             ┌────────────────────┐
       │ Block dữ liệu đã   │             │ Redo change vectors│
       │ chỉnh sửa (dirty)  │             │ cho data + undo    │
       │ Undo blocks        │             │ + transaction info │
       └─────────┬──────────┘             └──────────┬─────────┘
                 │                                   │
                 │ DBWn                              │ LGWR
                 ▼                                   ▼
       ┌────────────────────┐             ┌────────────────────┐
       │ Datafiles          │             │ Online redo logs   │
       │ ├─ Table/index     │             │ Group 1/2/3...     │
       │ └─ Undo tablespace │             └────────────────────┘
       └────────────────────┘                       │
                 ▲                                  │ ARCn nếu
                 │                                  │ ARCHIVELOG
                 │                                  ▼
          CKPT điều phối                    Archived redo logs
          và cập nhật                       (phục vụ recovery)
          checkpoint metadata
          trong control file
          + datafile headers
```

**Ai ghi cái gì?**

| Thành phần | Vai trò chính | Không nên suy luận |
| --- | --- | --- |
| **Server process** | Thực hiện DML, tạo thay đổi ở buffer cache, tạo undo và redo liên quan | `UPDATE` luôn ghi datafile ngay |
| **Redo log buffer** | Lưu tạm redo trước khi LGWR flush | Redo còn trong RAM đã an toàn sau mất điện |
| **LGWR** (*Log Writer*) | Ghi redo tuần tự vào online redo logs; tham gia commit đồng bộ | LGWR ghi table block xuống datafile |
| **DBWn/DBWR** (*Database Writer*) | Ghi dirty buffer của data/undo xuống datafile khi cần | DBWn chỉ được ghi dữ liệu đã commit |
| **CKPT** (*Checkpoint Process*) | Cập nhật thông tin checkpoint ở control file/datafile header, thúc đẩy hoạt động checkpoint | CKPT trực tiếp ghi nội dung table block |
| **Undo segments** | Lưu dữ liệu cần để rollback, phục hồi transaction và xây ảnh đọc nhất quán | Undo là một text log đứng ngoài database |
| **ARCn** (*Archiver*) | Sao chép online redo log đã chuyển nhóm thành archived redo log trong `ARCHIVELOG` mode | Archive log thay thế hoàn toàn online redo đang hoạt động |

Các thành phần này làm việc **bất đồng bộ ở nhiều thời điểm khác nhau**. Tách luồng ghi redo tuần tự khỏi luồng ghi dirty data block giúp Oracle đạt tốc độ ghi và khả năng phục hồi tốt hơn.

## 3. SCN: đồng hồ logic của Oracle Database

### 3.1. SCN là gì?

**System Change Number (SCN)** là số thứ tự logic tăng theo tiến trình hoạt động của database. Oracle sử dụng SCN để theo dõi thứ tự thay đổi, xác định mốc commit, duy trì read consistency và điều phối checkpoint/recovery.

Không nên hiểu SCN như một timestamp Unix hoặc một bộ đếm “mỗi câu SQL tăng đúng 1”:

- SCN biểu diễn **thứ tự logic**, không phải thời gian đồng hồ theo số giây tuyệt đối.
- Có thể có khoảng nhảy; không có quan hệ một-một giữa SCN và số câu `INSERT`/`UPDATE`.
- Một transaction có thể có **nhiều thay đổi và redo record**, nhưng có **mốc commit SCN** xác định thời điểm logic transaction được commit.
- Trong RAC, Oracle phối hợp SCN trên các instance để bảo đảm thứ tự nhất quán; không thể so sánh hai giá trị SCN của các **database độc lập** như cùng một đồng hồ toàn cục.
- Khi phân tích backup/recovery còn phải xét **database incarnation và `RESETLOGS`**; một SCN đứng riêng không định danh đầy đủ toàn bộ lịch sử phục hồi.

Giả sử transaction A commit ở SCN `120500` và B commit ở `120540` trong cùng dòng lịch sử database. Với một snapshot tại SCN `120520`, Oracle có thể nhìn thấy hiệu ứng của A nhưng không nhìn thấy hiệu ứng của B, **nếu cả hai thay đổi thuộc tập dữ liệu đang truy vấn và đáp ứng điều kiện visibility**.

### 3.2. Những SCN thường thấy

| Tên/mốc | Ý nghĩa | Dùng vào việc gì? |
| --- | --- | --- |
| **Current SCN** | Mốc hiện tại do database ghi nhận | Quan sát hoạt động, làm mốc tham chiếu logic |
| **Commit SCN** | Mốc logic đánh dấu transaction commit | Xác định thay đổi đã được commit hay chưa trước một snapshot |
| **Query/statement SCN** | Mốc snapshot của truy vấn nhất quán | Trả dữ liệu theo read consistency |
| **Checkpoint SCN** | Mốc tiến độ checkpoint đối với database/datafile | Xác định điểm bắt đầu cần redo cho crash recovery |
| **Data block SCN** | Thông tin thay đổi/commit liên quan được lưu trong header block | Kiểm tra phiên bản block, nhất quán và phục hồi |
| **`RESETLOGS_CHANGE#`** | SCN tại lần `OPEN RESETLOGS` | Định vị incarnation cho backup/recovery |

Các mốc trên có **ý nghĩa khác nhau**. Không thể nhìn thấy `CHECKPOINT_CHANGE#` thấp hơn `CURRENT_SCN` rồi kết luận dữ liệu mới nhất đã commit bị mất.

### 3.3. Xem SCN hiện tại bằng truy vấn chỉ đọc

```sql
-- Cần quyền đọc V$DATABASE (hoặc quyền phù hợp trong môi trường của bạn).
SELECT name,
       current_scn,
       checkpoint_change#,
       resetlogs_change#,
       log_mode
FROM   v$database;
```

Một cách khác dùng package có thể yêu cầu quyền thích hợp:

```sql
SELECT DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER AS current_scn
FROM   dual;
```

Kết quả SCN có thể thay đổi giữa hai lần truy vấn. Không xem giá trị này là “số dòng đã cập nhật”, “đơn vị mili-giây” hoặc bằng chứng mọi block ứng với SCN đã xuống datafile.

### 3.4. SCN và thời gian thực

Oracle hỗ trợ các hàm chuyển đổi **ước lượng** giữa SCN và timestamp khi còn thông tin ánh xạ trong khoảng thời gian hỗ trợ:

```sql
SELECT SCN_TO_TIMESTAMP(DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER)
       AS approximately_now
FROM   dual;
```

Không phải SCN lịch sử nào cũng chuyển được thành timestamp: ánh xạ có thời hạn lưu và chịu giới hạn Oracle; các giá trị quá cũ có thể gặp lỗi như `ORA-08181`. **SCN_TO_TIMESTAMP không biến SCN thành timestamp chính xác tuyệt đối.** Khi cần point-in-time recovery hoặc Flashback Query, phải biết dữ liệu/redo/undo tồn tại đủ và mốc tham chiếu có hợp lệ hay không.

## 4. Điều gì xảy ra với một lệnh `UPDATE` trước khi commit?

Giả sử row `accounts(id=1)` có `balance = 1_000_000`.

```sql
UPDATE accounts
SET    balance = balance - 500000
WHERE  id = 1;
```

Oracle thực hiện đại ý những việc sau:

1. Kiểm tra row, transaction/lock và đọc block cần thiết vào **database buffer cache** nếu chưa có.
2. Tạo **undo record** đủ để phục hồi ảnh trước thay đổi (ví dụ giá trị balance trước khi trừ); undo nằm trong undo segment của database.
3. Cập nhật bản sao data block và undo block ở cache; những block này trở thành **dirty buffers**.
4. Tạo **redo change vectors** cho các thay đổi đối với data block, undo block và metadata transaction liên quan; đưa redo vào **redo log buffer**.
5. Trả kết quả `1 row updated` cho câu `UPDATE` **mà chưa cần transaction commit**.

Ở thời điểm này, transaction vẫn đang mở:

- **Session đang sửa** nhìn thấy thay đổi của chính mình.
- **Session khác** không được thấy giá trị chưa commit qua truy vấn consistent read thông thường; Oracle sử dụng undo để tạo bản đọc thích hợp.
- DBWn **có thể** ghi dirty block xuống datafile nếu cần tài nguyên hoặc checkpoint; trên đĩa do đó có thể chứa một thay đổi **chưa commit**.
- LGWR **có thể** đã flush một phần redo của transaction trước `COMMIT`; redo được ghi không có nghĩa transaction đã commit.

### Bốn đường đời có thể khác nhau

```text
Thực hiện DML:
  Redo đã tạo?                  CÓ
  Undo đã tạo?                  CÓ (với DML thông thường trên bảng permanent)
  Data block dirty trong cache? CÓ
  Transaction đã commit?        CHƯA

Sau DML nhưng trước COMMIT:
  LGWR có thể ghi redo?         CÓ
  DBWn có thể ghi dirty block?  CÓ, sau khi bảo đảm redo cần thiết đã flush
  Session khác thấy row mới?    KHÔNG theo consistent read thông thường
```

Đây là nguồn gốc của hai nhận định rất dễ nhầm: **“redo đã nằm trên đĩa = đã commit”** và **“datafile đã có dữ liệu = đã commit”**. Cả hai đều sai.

## 5. `COMMIT`: SCN, commit record và LGWR

### 5.1. Luồng commit thông thường

```text
Client: COMMIT
     │
     ▼
Oracle gán commit SCN cho transaction
     │
     ▼
Tạo commit record và thông tin transaction liên quan trong redo
     │
     ▼
LGWR ghi phần redo cần thiết, gồm commit record, vào online redo logs
     │
     ▼
Redo đã bền vững (commit đồng bộ thông thường)
     │
     ▼
Oracle trả "Commit complete" cho client
     │
     └──────────────► DBWn có thể ghi datafile sau, khi thích hợp
```

Tại commit, Oracle cập nhật trạng thái logic của transaction và gán **commit SCN**. Với **`COMMIT` đồng bộ theo cấu hình thông thường**, LGWR ghi các redo record cần thiết cùng commit record xuống online redo log trước khi Oracle trả thành công. Đây là cơ sở của **fast commit**: không phải đợi DBWn ghi hết các data block của transaction vào datafile.

Một LGWR write có thể chứa **nhiều commit record của nhiều transaction** (*group commit*), giúp giảm số lần I/O nhưng không phá vỡ thứ tự và tính bền vững của commit.

### 5.2. Commit SCN khác checkpoint SCN

Giả sử tại thời điểm kiểm tra:

```text
Current SCN           = 135900
Transaction X commit  = 135880
Checkpoint SCN        = 135200
```

Điều này **không mâu thuẫn**. Transaction X đã commit và redo cần thiết có thể đang an toàn trong online redo log. DBWn có thể chưa ghi toàn bộ các data block ứng với transaction X; checkpoint chưa tiến đến mốc đó. Nếu instance lỗi, instance recovery áp dụng redo sau mốc checkpoint tương ứng để khôi phục X.

### 5.3. Ngoại lệ cần biết: `COMMIT WRITE NOWAIT`

Mệnh đề `COMMIT WRITE ... NOWAIT` cho phép Oracle **trả quyền điều khiển cho client trước khi redo commit hoàn tất ghi bền vững**; nếu instance hỏng đúng khoảng đó, client có thể đã nhận phản hồi trong khi redo vẫn có nguy cơ mất. Oracle khuyến cáo cần hiểu đổi chác độ bền trước khi dùng chế độ này. Vì vậy, câu “Oracle luôn flush redo trước khi báo commit thành công” chỉ đúng với **commit đồng bộ `WAIT` thông thường**, không phải mọi tùy chọn commit bất đồng bộ.

```sql
-- Minh họa cú pháp có liên quan đến rủi ro durability;
-- không dùng NOWAIT trong bài lab giao dịch tài chính.
COMMIT WRITE WAIT IMMEDIATE;
```

Ngoài ra, network failure ngay quanh commit tạo một tình huống đặc biệt: server **có thể đã commit** nhưng client chưa nhận phản hồi. Ứng dụng không nên vội phát lại transaction không idempotent mà không xác định kết quả cuối cùng; hệ thống có yêu cầu cao nên xem cơ chế xử lý kết quả commit không rõ ràng (*Transaction Guard* hoặc thiết kế idempotency phù hợp).

## 6. Redo: nhật ký giúp tiến lên sau sự cố

### 6.1. Redo lưu gì?

Redo không chỉ là một file text chứa lại câu SQL. Oracle ghi **redo records**, trong đó có những **change vectors** mô tả thay đổi đối với các data block. Một lệnh `UPDATE` có thể tạo redo cho:

- Data block của bảng và/hoặc index bị sửa.
- Undo block chứa thông tin có thể hoàn tác thay đổi.
- Transaction table và metadata liên quan.
- Các bước rollback cũng có thể sinh thêm redo do lại làm thay đổi block.

LGWR ghi redo theo thứ tự và về mặt ghi I/O thường thuận lợi hơn việc DBWn phải ghi các dirty block rải rác trong datafiles.

### 6.2. Write-ahead logging (WAL)

Một nguyên tắc sống còn của Oracle là **ghi redo cần thiết xuống đĩa trước khi ghi data block bẩn tương ứng xuống datafile**. Nếu DBWn muốn ghi một dirty block nhưng phần redo tương ứng chưa được LGWR flush, DBWn phải chờ LGWR hoàn tất phần redo cần thiết.

```text
UPDATE tạo redo R và dirty block B
                  │
                  ▼
         LGWR flush R trước
                  │
                  ▼
       DBWn được ghi block B
```

Từ đây hiểu được vì sao Oracle an toàn khi ghi một **uncommitted dirty block** xuống datafile: các thao tác cần thiết đã được ghi log để có thể phục hồi và, nếu transaction không commit, hoàn tác bằng undo được tái dựng.

### 6.3. Online redo và archived redo không phải một

| | Online redo log | Archived redo log |
| --- | --- | --- |
| Nguồn | LGWR ghi vào các log group theo vòng quay | ARCn sao chép nội dung log group sau log switch (khi `ARCHIVELOG`) |
| Mục đích cốt lõi | Bảo vệ và khôi phục hoạt động của instance; lưu redo mới nhất | Lưu lịch sử redo cho backup/media recovery, standby và phục hồi theo thời điểm |
| Có thể bị ghi đè theo vòng? | Có, khi Oracle xác định log đủ điều kiện tái sử dụng | Không theo chu kỳ group của online redo; cần chính sách lưu trữ riêng |
| Cần `ARCHIVELOG`? | Không | Có |

**Instance recovery** sau instance crash thông thường có thể sử dụng **online redo logs và current datafiles**, không nhất thiết đòi archived redo logs. Ngược lại, **media recovery** từ backup cũ hoặc sau khi mất datafile thường cần đủ archived redo (và có thể online redo mới nhất) để đưa dữ liệu đến mốc mong muốn. Một database `NOARCHIVELOG` vẫn có online redo để phục hồi instance, nhưng khả năng khôi phục từ backup có giới hạn nghiêm trọng hơn.

### 6.4. Redo đã ghi nhưng transaction rollback thì sao?

Redo của transaction không bị xóa khi rollback. Oracle dùng undo để đảo ngược các thay đổi chưa commit, và bản thân thao tác rollback còn có thể sinh redo. Khi đọc redo, phải xét **transaction state/commit marker**, không hiểu rằng mọi change vector đều đại diện cho một thay đổi cuối cùng được commit.

## 7. Undo: thông tin quay về ảnh trước và dựng phiên bản đọc

### 7.1. Undo nằm ở đâu?

Với các DML thông thường trên dữ liệu permanent, Oracle duy trì undo trong **undo segment** thuộc **undo tablespace**. Undo là các **database blocks**, được quản lý, cache và ghi datafile tương tự block dữ liệu khác. Vì block undo cũng bị sửa, thay đổi undo thường tạo **redo cho undo**.

Đây là điểm rất quan trọng: **undo không phải “một file đối lập với redo log”**. Undo là dữ liệu trong database phục vụ đảo ngược/versioning; redo là chuỗi mô tả các thay đổi, **bao gồm cả thay đổi trên undo blocks**, để tái dựng database sau crash.

Oracle có cơ chế quản lý riêng cho temporary undo của đối tượng temporary; một số thao tác đặc biệt như các chế độ no-logging hoặc deferred insert cũng có ngoại lệ. Bài này xét luồng **transaction DML bình thường trên bảng permanent, có redo và undo**.

### 7.2. Bốn vai trò của undo

1. **Rollback tường minh:** `ROLLBACK` hoặc `ROLLBACK TO SAVEPOINT` hoàn tác phần thay đổi chưa commit.
2. **Transaction recovery:** sau crash, Oracle hoàn tác transaction chưa có commit bền vững.
3. **Read consistency:** xây dựng ảnh dữ liệu tại SCN phù hợp cho truy vấn đang chạy, kể cả khi writer đã đổi block.
4. **Một số thao tác Flashback:** truy vấn lại dữ liệu của một SCN/thời điểm trước đó, nếu undo cần thiết vẫn tồn tại.

### 7.3. Undo không biến mất ngay sau commit

Sau `COMMIT`, undo của transaction vừa kết thúc **có thể còn được giữ lại** để phục vụ các truy vấn bắt đầu trước commit, Flashback Query và những nhu cầu consistent read khác. Oracle quản lý vòng đời undo extents và tái sử dụng khi phù hợp.

```text
Transaction đang chạy   → undo ACTIVE, cần cho rollback
Transaction đã commit   → undo không còn ACTIVE cho rollback của transaction
                         nhưng có thể còn được giữ cho consistent read
Hết thời hạn/điều kiện  → undo có thể được tái sử dụng
```

`UNDO_RETENTION` là cấu hình ảnh hưởng đến mục tiêu giữ undo; **không mặc nhiên bảo đảm mọi truy vấn quá khứ đều thành công** nếu không có đủ undo space và chế độ retention guarantee phù hợp. Khi undo cần cho snapshot đã bị ghi đè, truy vấn có thể nhận `ORA-01555: snapshot too old`.

### 7.4. Một row được cập nhật nhưng reader vẫn thấy giá trị cũ

```text
T0: Row balance = 1,000,000 đã commit.

T1: Session A UPDATE balance = 500,000; chưa COMMIT.
    ├─ Data block trong cache có thể chứa 500,000.
    ├─ Undo chứa đủ thông tin phục hồi về 1,000,000.
    └─ Redo mô tả các thay đổi cho data + undo.

T2: Session B SELECT balance ở READ COMMITTED.
    └─ Thấy 1,000,000 bằng consistent read; không dirty-read 500,000.

T3: Session A COMMIT (commit SCN = 120500).

T4: Session C bắt đầu SELECT mới với snapshot SCN > 120500.
    └─ Thấy 500,000.

T5: Session B có một câu SELECT bắt đầu từ trước T3 vẫn đang chạy.
    └─ Oracle tiếp tục đảm bảo ảnh phù hợp với SCN lúc câu SELECT đó bắt đầu.
```

**Oracle không cần chặn mọi reader bằng khóa trên row writer đang sửa**. Oracle tạo **consistent read (CR) clone** của block khi cần và áp dụng undo để dựng ảnh tại SCN mà câu query được phép thấy. Ngoại lệ cần nhận diện: `SELECT ... FOR UPDATE` là truy vấn có mục đích khóa row, khác truy vấn SELECT nhất quán thông thường.

## 8. Checkpoint thực chất là gì?

### 8.1. Mục tiêu: rút ngắn đoạn redo phải áp dụng khi instance recovery

Database buffer cache chứa nhiều dirty buffers. Nếu instance đột ngột chết, các dirty buffer chưa được DBWn ghi sẽ biến mất khỏi RAM; Oracle cần redo để áp dụng lại các thay đổi. **Checkpoint** đánh dấu tiến độ các dirty buffer đã được ghi và xác lập vị trí redo bắt đầu cần xét cho instance recovery.

Theo tài liệu Oracle, checkpoint position là một **vị trí trong redo thread** và liên quan đến **oldest dirty buffer**; SCN checkpoint cho biết một mốc phục hồi có bảo đảm tương ứng. Oracle có thể tiếp tục hoạt động và thay đổi block trong lúc checkpoint tiến hành: checkpoint không đóng băng toàn database thành một snapshot vật lý đơn giản.

```text
Redo timeline (SCN chỉ minh họa)

1000      1100      1200      1300      1400      1500
 |---------|---------|---------|---------|---------|
                          ▲                         ▲
                  checkpoint SCN                current SCN
                          │
                redo trước mốc đã được
                bao phủ bởi checkpoint
                tương ứng cho recovery
                          │
                          └────► cần xem redo sau mốc này
                                 nếu instance bị crash
```

Tài liệu **Oracle Database Concepts 19c** mô tả checkpoint position bảo đảm rằng các thay đổi đã **commit** có SCN nhỏ hơn checkpoint SCN đã được ghi xuống datafiles, đối với checkpoint tương ứng. Tuy vậy, **datafile còn có thể chứa block có SCN mới hơn checkpoint** (thậm chí thay đổi chưa commit), vì DBWn không bắt buộc ghi mọi block theo thứ tự từng transaction.

### 8.2. CKPT khác DBWn

- **DBWn** trực tiếp ghi dirty data/undo blocks từ database buffer cache vào datafiles.
- **CKPT** cập nhật thông tin checkpoint trong control file và datafile headers, đồng thời báo/điều phối DBWn tiến checkpoint.
- **LGWR** ghi redo vào online redo logs; CKPT không thay LGWR ghi redo.

```text
                 ┌────────────────┐
                 │ CKPT           │
                 │ điều phối và   │
                 │ ghi checkpoint │
                 │ metadata       │
                 └───────┬────────┘
                         │
             ┌───────────┴────────────┐
             ▼                        ▼
       Control file +           Tín hiệu cho
       datafile header          DBWn đẩy buffers
             ▲                        │
             │                        ▼
             │                 Datafile contents
             │                 do DBWn ghi
             └────────────────────────┘
```

### 8.3. Incremental checkpoint và full checkpoint

Oracle hiện đại thực hiện **incremental checkpoint** liên tục để đẩy mốc cần phục hồi tiến lên mà không phải đợi mọi dirty buffer của database cùng được ghi. DBA có thể cấu hình mục tiêu thời gian khôi phục thông qua cơ chế **Fast-Start Checkpointing**/`FAST_START_MTTR_TARGET` trong những môi trường phù hợp.

**Full checkpoint** hoặc checkpoint có phạm vi rộng hơn xuất hiện trong các tình huống cụ thể, chẳng hạn một số hoạt động đóng database, thay đổi trạng thái file/tablespace và các sự kiện quản trị. Các điều kiện checkpoint chi tiết phụ thuộc phiên bản và loại thao tác; đừng tự suy rằng mỗi lệnh `COMMIT` hoặc mọi lần **log switch** đều chờ ghi xong toàn bộ dirty buffer của database.

Một log switch có thể phát sinh hoạt động/nhu cầu checkpoint, nhưng có thể hoàn tất việc đổi log trong khi checkpoint/DBWn tiếp tục chạy. Nếu checkpoint chưa tiến đủ, Oracle có thể chưa được phép tái sử dụng một online redo log group còn cần cho crash recovery, tạo ra thông báo chờ kiểu **checkpoint not complete**.

### 8.4. Checkpoint SCN không nhất thiết bằng nhau trên mọi datafile

Oracle quản lý thông tin checkpoint ở **database và từng datafile**. File offline/read-only, tablespace có trạng thái khác hoặc quá trình backup/recovery có thể khiến mốc checkpoint ở các file không giống nhau. Cần so sánh với đúng file và trạng thái; không lấy `V$DATABASE.CURRENT_SCN` trừ `V$DATAFILE_HEADER.CHECKPOINT_CHANGE#` rồi suy ra ngay số giây mất dữ liệu hay thời gian recovery.

Trong backup **online**, datafile copy có thể ở trạng thái **fuzzy**, vì các block được chép tại những thời điểm khác nhau. Muốn khôi phục thành trạng thái nhất quán, cần redo thích hợp; chỉ xem file header không đủ để tuyên bố backup có thể mở trực tiếp không cần recovery.

## 9. Tại sao một datafile có thể chứa dữ liệu chưa commit?

Một chuỗi sự kiện hợp lệ:

```text
1. Transaction T1 UPDATE row R từ 'A' sang 'B'.
2. Oracle tạo undo cho ảnh 'A' và redo cho data/undo changes.
3. LGWR flush phần redo liên quan theo write-ahead protocol.
4. DBWn ghi dirty data block đang chứa 'B' xuống datafile.
5. T1 CHƯA COMMIT; trên đĩa vẫn đã có block chứa 'B'.
6. Session khác SELECT row R → nhận 'A' nhờ read consistency.
7. T1 ROLLBACK → Oracle áp dụng undo để phục hồi 'A'.
```

Do đó, datafile **không thể tự được diễn giải như một tập chỉ chứa dữ liệu đã commit tại một timestamp đồng nhất**. Trạng thái transaction, undo và redo là một phần của cơ chế xác định dữ liệu cuối cùng hợp lệ.

Ngược lại, cũng có chuỗi hợp lệ:

```text
1. T2 UPDATE row S từ 'X' sang 'Y'.
2. T2 COMMIT; commit record bền vững trong redo log.
3. DBWn chưa ghi block S xuống datafile.
4. Instance crash; buffer cache bị mất.
5. Oracle đọc online redo và reapply update đã commit.
6. Recovery xong: 'Y' được bảo toàn.
```

**Durability của commit đồng bộ thông thường phụ thuộc redo đã bền vững**, không phụ thuộc việc DBWn đã ghi hết datafile ngay tại giây commit.

## 10. Instance recovery: REDO đi tới, UNDO đi lui

### 10.1. Hai giai đoạn cơ bản

Khi Oracle instance bị chấm dứt bất thường nhưng **current datafiles và online redo logs cần thiết vẫn còn nguyên**, Oracle thực hiện instance recovery:

**Giai đoạn A — Roll forward / cache recovery.** Oracle đọc redo cần thiết tính từ checkpoint position phù hợp và **áp dụng lại các thay đổi** chưa phản ánh đầy đủ vào datafiles. Vì redo ghi cả thay đổi trên undo blocks, quá trình này cũng có thể tái dựng undo cần cho bước sau. Roll forward có thể làm datafiles tạm thời chứa cả thay đổi của transaction đã và chưa commit.

**Giai đoạn B — Rollback / transaction recovery.** Oracle xác định transaction chưa commit thành công tại thời điểm lỗi và **dùng undo** để hoàn tác các thay đổi của chúng. Recovery/rollback có thể được thực hiện song song hoặc theo nhu cầu truy cập block, tùy cơ chế Oracle.

```text
                  Instance mất điện
                          │
                          ▼
        Đọc checkpoint position và redo thread
                          │
                          ▼
           ROLL FORWARD bằng REDO
       ┌────────────────────────────────┐
       │ Phục hồi thay đổi data + undo │
       │ của cả transaction đã commit  │
       │ và chưa commit cần thiết      │
       └────────────────┬───────────────┘
                        │
                        ▼
          Xác định transaction còn mở
                        │
                        ▼
             ROLLBACK bằng UNDO
       ┌────────────────────────────────┐
       │ Gỡ các thay đổi chưa commit   │
       └────────────────┬───────────────┘
                        │
                        ▼
         Database nhất quán về transaction
         (committed retained, uncommitted undone)
```

### 10.2. Ví dụ ba transaction tại thời điểm crash

Giả sử dữ liệu ban đầu đã commit:

```text
A = 10
B = 20
C = 30
```

Tại thời điểm trước crash:

| Transaction | Hành động | Redo trên online log? | Commit record bền vững? |
| --- | --- | --- | --- |
| **T1** | Đổi `A=11` | Có | **Có**, commit SCN 7100 |
| **T2** | Đổi `B=21` | Có | **Không** |
| **T3** | Đổi `C=31` | Có | **Có**, commit SCN 7200 |

DBWn có thể đã ghi block `B=21` nhưng chưa ghi `A=11` hoặc `C=31`. Điều đó hoàn toàn hợp lệ và không nói lên transaction nào đã commit. Sau instance recovery:

```text
A = 11  ← T1 đã commit, redo phục hồi nếu block chưa xuống datafile.
B = 20  ← T2 chưa commit, undo gỡ thay đổi.
C = 31  ← T3 đã commit, redo phục hồi nếu cần.
```

Với kiểu commit đồng bộ thông thường, thành công được định nghĩa bằng commit record bền vững trong redo. Trường hợp `NOWAIT` hoặc lỗi đặc biệt làm mất redo cần thiết phải được phân tích riêng; không lấy ví dụ này để cam kết một mức phục hồi bất chấp hư hỏng storage.

### 10.3. Vì sao cần cả redo của undo?

Nếu chỉ có redo cho data block, Oracle có thể reapply một thay đổi chưa commit rồi lại **không còn undo** trong RAM sau mất điện. Vì undo cũng nằm trong database và thay đổi undo có redo tương ứng, Oracle có thể dựng lại undo segment khi roll forward, sau đó undo transaction thất bại.

Đây là mối quan hệ kiến trúc **redo bảo đảm các thay đổi cần thiết có thể được tái hiện, undo bảo đảm trạng thái giao dịch cuối cùng đúng**. Chúng bổ sung nhau, không thay thế nhau.

### 10.4. Instance recovery khác media recovery

| Trường hợp | Tập dữ liệu còn lại | Cơ chế chính |
| --- | --- | --- |
| Instance bị crash; datafile và online redo còn nguyên | Current datafiles + online redo | **Instance recovery**: roll forward và rollback |
| Mất hoặc hỏng datafile, phải restore từ backup | Backup datafile cũ hơn, các redo cần thiết | **Media recovery**: restore + apply archived/online redo thích hợp |
| Muốn quay về thời điểm trước một thao tác nhầm | Backup/redo hoặc tính năng Flashback phù hợp | Point-in-time recovery hoặc Flashback, tùy tình huống |
| Mất tất cả bản sao online redo cần thiết trong khi datafile chưa chứa các commit mới nhất | Có thể không đủ thông tin để khôi phục hoàn toàn | Cần đánh giá backup/archives/cấu hình bảo vệ; **không** được hứa dữ liệu luôn khôi phục đủ |

Checkpoint giúp giảm phần phải reapply ở **instance recovery**, nhưng **không thay thế backup, archived redo, Data Guard hay kế hoạch DR**.

## 11. SCN và read consistency: dữ liệu “đã commit” còn phụ thuộc mốc nhìn

### 11.1. Snapshot của một SELECT

Ở mức cô lập `READ COMMITTED` mặc định, một truy vấn Oracle có snapshot **statement-level**: câu `SELECT` nhìn dữ liệu đã commit phù hợp **với SCN khi query bắt đầu**, đồng thời thấy các thay đổi riêng của transaction đang truy vấn nếu có.

```text
SCN 8000: A commit giá sản phẩm = 100.
SCN 8010: Session B bắt đầu SELECT chạy 20 giây.
SCN 8020: A commit UPDATE giá sản phẩm = 120.
SCN 8030: B vẫn đang đọc phần cuối của SELECT cũ.

B không thể tùy tiện đọc nửa truy vấn giá=100 và nửa còn lại giá=120.
Oracle dùng undo khi cần để tạo ảnh consistent tại snapshot SCN 8010.
```

Ở isolation `READ COMMITTED`, **câu SELECT kế tiếp** trong cùng transaction có thể thấy phiên bản mới được commit sau câu SELECT trước. Vì vậy `READ COMMITTED` đảm bảo **statement-level consistency**, không có nghĩa lặp SELECT luôn trả cùng kết quả.

### 11.2. `SERIALIZABLE` và `READ ONLY`

Ở mức cô lập `SERIALIZABLE`, các truy vấn trong cùng transaction nhìn snapshot nhất quán theo mốc transaction (vẫn nhìn thay đổi do chính transaction tạo). Cần hiểu thêm xung đột update và lỗi như `ORA-08177` khi Oracle không thể tuần tự hóa transaction đang cố thay đổi dữ liệu. Một read-only transaction cũng có thể dùng snapshot nhất quán xuyên nhiều truy vấn theo semantics Oracle.

SCN snapshot giúp giải thích đồng thời **dữ liệu đã commit nhưng chưa xuất hiện trong truy vấn đang chạy**: commit xảy ra **sau** snapshot SCN của truy vấn, chứ không phải vì dữ liệu chưa được DBWn ghi xuống datafile.

### 11.3. `ORA-01555: snapshot too old`

Một query dài cần đọc ảnh tại SCN cũ. Khi nhiều transaction tiếp tục sửa dữ liệu, undo cần để dựng ảnh đó có thể bị tái sử dụng nếu không còn được giữ đủ. Query có thể gặp `ORA-01555`. Đây là vấn đề **khả năng giữ ảnh lịch sử**, không đồng nghĩa transaction mới commit bị mất hoặc redo sai.

Các yếu tố nên điều tra: độ dài query, tốc độ sinh undo, kích thước undo tablespace, chính sách retention, vòng đời transaction và cách ứng dụng fetch dữ liệu. Không coi việc tăng `UNDO_RETENTION` đơn độc là cách chữa mọi tình huống khi không có đủ undo space.

### 11.4. Flashback Query `AS OF SCN`

Khi cần xem ảnh của một thời điểm trước đó và còn đủ undo:

```sql
-- SCN bên dưới là ví dụ; phải chọn SCN còn hợp lệ trên DB thực.
SELECT account_id, balance
FROM   accounts AS OF SCN 8000
WHERE  account_id = 1;
```

`AS OF SCN` yêu cầu quyền truy vấn và lịch sử undo đủ, có các giới hạn theo loại object/DDL và thời gian lưu. **Redo/archived redo không phải bộ nhớ trực tiếp để Flashback Query tự tra tùy ý mọi SCN quá khứ**. Đừng kỳ vọng có `ARCHIVELOG` thì mọi `AS OF SCN` rất cũ sẽ chạy được.

## 12. So sánh redo, undo, checkpoint và commit trên một bảng

| Câu hỏi | **Redo** | **Undo** | **Checkpoint** | **Commit** |
| --- | --- | --- | --- | --- |
| Trả lời điều gì? | Làm lại thay đổi thế nào? | Quay về ảnh trước thế nào? | Phần nào đã được ghi đủ để giảm recovery? | Transaction đã kết thúc thành công chưa? |
| Nơi lưu chính | Online redo log; bản archived khi bật archive | Undo segment trong undo tablespace | Metadata trong control file/datafile headers và tiến độ dirty buffer | Transaction state/commit record trong redo, gắn commit SCN |
| Tác nhân chính | LGWR ghi log | Server process tạo; undo được dùng bởi rollback/consistent read/recovery | DBWn ghi block, CKPT cập nhật mốc | Server/LGWR phối hợp transaction commit |
| Có thể tồn tại trước commit? | **Có** | **Có** | **Có, không phụ thuộc từng commit** | Không, đây là sự kiện commit |
| Có thể tác động sau commit? | Redo đã ghi dùng để recovery | Undo còn có thể dùng cho reader cũ | Tiếp tục đẩy mốc lên | Commit SCN dùng cho visibility |
| Có tương đương datafile đã ghi? | Không | Không | Cho biết tiến độ ghi theo mốc checkpoint | Không |
| Vai trò khi crash | Roll forward | Roll back transaction chưa commit | Xác định điểm bắt đầu recovery thích hợp | Phân biệt transaction bền vững đã commit |

**Ví dụ diễn giải một dòng:** `T1 COMMIT tại SCN 9000; checkpoint đang ở SCN 8800` nghĩa là transaction có thể đã durable qua redo nhưng các dirty block của nó chưa chắc đã được DBWn flush. Nếu instance crash, Oracle có thể dùng redo sau checkpoint và undo cho các transaction khác chưa commit.

## 13. Bài thực hành hai session: nhìn visibility và rollback

> **Chỉ thực hiện trên database lab và schema bạn được phép sửa**. Các lệnh DDL có implicit commit; không dùng bảng dữ liệu thật hoặc tài khoản production. SQL bên dưới minh họa DML thông thường với bảng permanent.

### 13.1. Chuẩn bị ở session A

```sql
-- Session A, trong schema lab.
CREATE TABLE scn_checkpoint_lab (
    id      NUMBER PRIMARY KEY,
    balance NUMBER NOT NULL
);

INSERT INTO scn_checkpoint_lab(id, balance) VALUES (1, 1000);
COMMIT;

SELECT id, balance FROM scn_checkpoint_lab;
-- 1 | 1000
```

DDL `CREATE TABLE` có implicit commit trước/sau DDL thành công. Do đó không trộn các bước DDL vào transaction đang dùng để quan sát rollback.

### 13.2. Session A sửa nhưng chưa commit

```sql
-- Session A
UPDATE scn_checkpoint_lab
SET    balance = 900
WHERE  id = 1;

SELECT balance FROM scn_checkpoint_lab WHERE id = 1;
-- Session A thấy 900 (read-your-own-writes).

-- CHƯA COMMIT.
```

Mở session B, đăng nhập vào đúng schema hoặc có quyền xem bảng của A:

```sql
-- Session B (READ COMMITTED mặc định)
SELECT balance FROM scn_checkpoint_lab WHERE id = 1;
-- Thấy 1000; không thấy 900 chưa commit.
```

Thời điểm này undo cần cho rollback/consistent read đã được tạo; redo cũng đã được tạo cho các thay đổi data/undo. Không có SQL thuần nghiệp vụ nào chứng minh chính xác buffer data nào đã được DBWn flush ở từng mili-giây.

### 13.3. Session A commit, session B đọc lại

```sql
-- Session A
COMMIT;

-- Session B, một SELECT MỚI
SELECT balance FROM scn_checkpoint_lab WHERE id = 1;
-- Thấy 900.
```

Điều này kiểm chứng **read consistency** và **commit visibility**, nhưng **không chứng minh** Oracle đã ghi data block vào datafile ngay lúc commit.

### 13.4. Rollback: thay đổi đã tạo redo vẫn không thành kết quả cuối

```sql
-- Session A
UPDATE scn_checkpoint_lab SET balance = 700 WHERE id = 1;
SELECT balance FROM scn_checkpoint_lab WHERE id = 1;
-- 700

ROLLBACK;

SELECT balance FROM scn_checkpoint_lab WHERE id = 1;
-- 900
```

Ở đây Oracle dùng undo để gỡ update chưa commit. Redo từng phát sinh cho `UPDATE` không bị xóa khỏi online redo log. Phục hồi lại `900` là logic transaction, không phải thao tác xóa vật lý mọi dấu vết redo.

### 13.5. Dọn lab sau khi hoàn tất

```sql
-- Chỉ trong schema lab, sau khi xác nhận đúng bảng cần dọn.
DROP TABLE scn_checkpoint_lab PURGE;
```

Không dùng thử `SHUTDOWN ABORT`, `ALTER SYSTEM SWITCH LOGFILE` hoặc `ALTER SYSTEM CHECKPOINT` trên database đang phục vụ workload chỉ để quan sát bài học. Những thao tác quản trị đó có tác động thực sự đến hệ thống và không cần thiết để hiểu cơ chế.

## 14. Truy vấn quan sát kiến trúc bằng SQL (chỉ đọc)

Các view động `V$...` yêu cầu quyền phù hợp (thường DBA hoặc quyền đọc view cụ thể). Trong CDB/PDB và RAC, kết quả còn phụ thuộc container/instance mà session đang truy vấn. Các câu sau **chỉ xem thông tin**, không làm checkpoint hay điều chỉnh cấu hình.

### 14.1. Current SCN, checkpoint, archive mode

```sql
SELECT name,
       current_scn,
       checkpoint_change#,
       resetlogs_change#,
       log_mode,
       open_mode
FROM   v$database;
```

- `CURRENT_SCN` cho mốc SCN hiện tại theo view.
- `CHECKPOINT_CHANGE#` là mốc checkpoint được control file báo cáo.
- `RESETLOGS_CHANGE#` liên quan database incarnation.
- `LOG_MODE` là `ARCHIVELOG` hoặc `NOARCHIVELOG` (cũng có giá trị khác trong tình huống đặc biệt).

**Không** dùng `CURRENT_SCN - CHECKPOINT_CHANGE#` làm công thức dự đoán trực tiếp thời gian phục hồi, số transaction chưa xuống datafile hay số dữ liệu có thể mất.

### 14.2. Checkpoint của từng datafile và file header

```sql
-- Dữ liệu metadata từ control file.
SELECT file#,
       name,
       checkpoint_change#,
       status
FROM   v$datafile
ORDER BY file#;

-- Metadata thực tế đọc từ header datafile.
SELECT file#,
       name,
       checkpoint_change#,
       fuzzy,
       recover
FROM   v$datafile_header
ORDER BY file#;
```

`V$DATAFILE` đọc thông tin về file trong **control file**, còn `V$DATAFILE_HEADER` đọc thông tin trong **datafile headers**. Đối chiếu hai nguồn khi chẩn đoán restore/recovery; khác biệt không đủ để tự kết luận cần restore hay recover. Trạng thái `FUZZY`/`RECOVER` phải được DBA diễn giải trong ngữ cảnh file open/backup/recovery cụ thể.

### 14.3. Redo log group và dải SCN

```sql
SELECT group#,
       thread#,
       sequence#,
       status,
       archived,
       first_change#,
       next_change#
FROM   v$log
ORDER BY thread#, group#;
```

`V$LOG` cho thấy redo thread, log sequence, trạng thái `CURRENT`/`ACTIVE`/`INACTIVE` và ranh giới SCN của log group. `NEXT_CHANGE#` trên log **CURRENT** có thể là giá trị sentinel rất lớn thay vì mốc tương lai thực tế. Không coi `ACTIVE` đồng nghĩa transaction trong nhóm đó chưa commit; `ACTIVE` có thể nghĩa là log còn cần cho crash recovery. Với RAC, mỗi instance có redo thread riêng và cần xem đủ các thread liên quan.

### 14.4. Thông tin undo và những truy vấn kéo dài

```sql
SELECT begin_time,
       end_time,
       undoblks,
       maxquerylen,
       ssolderrcnt,
       tuned_undoretention
FROM   v$undostat
ORDER BY begin_time DESC
FETCH FIRST 20 ROWS ONLY;
```

`V$UNDOSTAT` hỗ trợ điều tra hoạt động undo theo khoảng thời gian: lượng undo phát sinh, độ dài truy vấn và số lần phát sinh **snapshot too old** quan sát được. Nó không trả trực tiếp toàn bộ record undo của một transaction cụ thể. Giá trị thống kê, cách tổng hợp và phạm vi instance cần được đọc cùng tài liệu release đang dùng.

Quan sát cấu hình:

```sql
SELECT name, value
FROM   v$parameter
WHERE  name IN (
           'undo_management',
           'undo_tablespace',
           'undo_retention',
           'fast_start_mttr_target'
       )
ORDER BY name;
```

Tham số `FAST_START_MTTR_TARGET` liên quan mục tiêu thời gian instance recovery và nhịp incremental checkpoint; **không phải một cam kết chính xác mỗi lần crash sẽ hồi phục sau đúng N giây**.

### 14.5. Phân biệt “chỉ đọc metadata” với “ép checkpoint”

| Hành động | Phạm vi tác động |
| --- | --- |
| `SELECT ... FROM V$DATABASE` | Quan sát SCN và metadata |
| `SELECT ... FROM V$DATAFILE_HEADER` | Quan sát metadata header, không ép full checkpoint |
| `SELECT ... FROM V$UNDOSTAT` | Quan sát thống kê undo |
| `ALTER SYSTEM CHECKPOINT` | **Hành động quản trị**, ép hoạt động checkpoint, tạo I/O; không cần cho lab này |
| `ALTER SYSTEM SWITCH LOGFILE` | **Hành động quản trị**, đổi redo group, có thể ảnh hưởng archiving/checkpoint |
| `SHUTDOWN ABORT` | **Gây dừng instance bất thường**; chỉ dùng trong thử nghiệm có kiểm soát và có quyền |

Đừng chạy lệnh quản trị chỉ để nhìn con số SCN đổi. Bản chất commit/recovery đã thể hiện được qua session lab và dynamic views chỉ đọc.

## 15. Các trường hợp nâng cao cần tách riêng

### 15.1. Data Guard: SCN và redo vận chuyển sang standby

Ở Data Guard, primary tạo redo; standby tiếp nhận và có thể apply redo để duy trì bản sao dữ liệu. Những khái niệm **redo sequence**, **thread**, **transport lag**, **apply lag**, **commit SCN** và **checkpoint** có quan hệ nhưng không giống nhau. `COMMIT` thành công trên primary không tự khẳng định standby đã **apply** đến commit SCN đó: điều này tùy mode bảo vệ, đồng bộ vận chuyển, apply và kiến trúc cấu hình.

Khi hỏi “standby đã có giao dịch X chưa?”, cần xác định **redo đã chuyển tới? redo đã apply? standby đã mở cho loại query nào?**. Không chỉ nhìn `CURRENT_SCN` trên primary.

### 15.2. RAC: nhiều redo thread, một database logic

Trong RAC, các instance dùng chung database nhưng mỗi instance có redo thread riêng. Oracle phối hợp SCN và các cơ chế cache fusion để giữ thứ tự và dữ liệu nhất quán. Khi instance recovery cần xử lý một instance thất bại, Oracle phải xét **redo thread tương ứng** và các trạng thái phục hồi liên quan; không suy rằng một file online redo duy nhất mô tả toàn bộ hoạt động cluster.

### 15.3. CDB/PDB: snapshot và undo theo container

Trong multitenant, service đưa session đến PDB; undo có thể được cấu hình ở **shared undo** hoặc **local undo mode**, tùy release và cách triển khai. Bài học về SCN, redo và consistency vẫn áp dụng; nhưng phạm vi của các dynamic views, quyền xem metadata và vị trí undo cần xác định theo container thực tế. Với RAC/PDB, không áp dụng ví dụ single-instance như một sơ đồ topology chính xác tuyệt đối.

### 15.4. `NOLOGGING` và tối ưu ghi đặc biệt

Một số thao tác direct-path hoặc hoạt động có chế độ `NOLOGGING` **không ghi đầy đủ redo cho data changes** như DML thông thường; vẫn có thể phát sinh redo cho dictionary/metadata và các thành phần bắt buộc. Điều này tạo rủi ro khi cần media recovery từ backup, nhất là khi archived redo không chứa đủ block change để khôi phục nội dung. `FORCE LOGGING`, chính sách backup và đặc tính thao tác cụ thể phải được thiết kế bởi DBA.

Tương tự, một số cơ chế tối ưu cho temporary objects hoặc deferred writes có luật redo/undo/durability riêng. **Không lấy các ngoại lệ đó để bác bỏ mô hình DML permanent thông thường** đang được giải thích ở đây.

## 16. Chẩn đoán hiện tượng thực tế bằng mô hình SCN–redo–undo–checkpoint

### Hiện tượng 1: “Ứng dụng báo commit thành công, datafile chưa thấy timestamp thay đổi”

Thường **không phải lỗi**. LGWR flush redo cho commit theo giao thức đồng bộ; DBWn có thể ghi datafile sau. Mtime của file trên filesystem không phải công cụ xác định commit SCN hay trạng thái giao dịch.

### Hiện tượng 2: “Một query rất dài vẫn thấy giá trị cũ dù session khác đã commit”

Có thể đúng theo **statement-level read consistency**. Query dùng snapshot SCN khi bắt đầu, Oracle dựng CR version từ undo. Nếu query mới ở `READ COMMITTED`, kết quả có thể khác; nếu thiếu undo, có thể gặp `ORA-01555`.

### Hiện tượng 3: “Datafile đã chứa một giá trị mới nhưng rollback vẫn phục hồi giá trị cũ”

Hoàn toàn có thể. DBWn được phép ghi dirty buffer của transaction chưa commit sau khi redo liên quan đã bền vững. Undo phục hồi logic của transaction; datafile đã có block vật lý mới không làm dữ liệu đó trở thành committed.

### Hiện tượng 4: “Sau `SHUTDOWN ABORT`, Oracle cần recovery dù đã có nhiều checkpoint”

Checkpoint chỉ **giảm** đoạn redo phải xét, không loại bỏ mọi dirty block chưa flush và transaction chưa commit. Instance recovery roll forward redo cần thiết từ checkpoint, rồi rollback các transaction chưa commit. Một controlled shutdown nhất quán có quy trình khác với crash.

### Hiện tượng 5: “Redo log switch bị chờ checkpoint not complete”

DBWn/CKPT chưa đẩy mốc phục hồi đủ xa để nhóm redo cần tái sử dụng trở nên an toàn. Cần xem kích cỡ/số lượng redo groups, tốc độ sinh redo, I/O ghi datafile, mục tiêu MTTR và trạng thái archiving. **Không khắc phục bằng cách ép commit**; commit không phải thao tác hoàn tất checkpoint.

### Hiện tượng 6: “Có archived redo nhưng `AS OF SCN` cũ vẫn thất bại”

Flashback Query dùng undo để dựng ảnh cũ trong phạm vi được hỗ trợ; archived redo chủ yếu phục vụ recovery/standby và không tự thay thế undo đã bị tái sử dụng. Với truy vấn quá khứ xa, xem khả năng Flashback Data Archive (khi phù hợp) hoặc chiến lược lưu lịch sử/backup khác.

### Hiện tượng 7: “Session crash làm mất dữ liệu dù đã nhận thông báo commit”

Cần xác minh **commit mode** (`WAIT` hay `NOWAIT`), độ tin cậy và cấu hình storage, loại failure, trạng thái online redo và bản ghi giao dịch. Nếu server có commit đồng bộ bền vững nhưng client mất kết nối trước phản hồi, kết quả có thể **không rõ với client** chứ không nhất thiết là database mất commit. Không đánh đồng timeout của application với rollback.

## 17. Câu hỏi củng cố

**Câu 1.** Sau `UPDATE` nhưng trước `COMMIT`, điều nào có thể đúng?

A. Chưa có redo vì transaction chưa commit.  
B. DBWn không được ghi block trước commit.  
C. Redo có thể đã nằm trong online redo log và datafile có thể chứa dirty block chưa commit.  
D. Session khác luôn nhìn thấy giá trị mới.

**Câu 2.** `CURRENT_SCN=50000`, `CHECKPOINT_CHANGE#=49200` nhưng transaction X đã commit tại 49900. Có suy ra X không bền vững?

**Câu 3.** Vì sao recovery không chỉ roll forward redo mà còn cần undo?

**Câu 4.** Trong `READ COMMITTED`, SELECT đầu tiên thấy `A=100`; session khác commit `A=110`; SELECT thứ hai trong cùng transaction có thể thấy `110` không?

**Câu 5.** Một query `AS OF SCN` rất cũ báo lỗi mặc dù database bật `ARCHIVELOG`. Thiếu thông tin gì để kết luận?

<details>
<summary>Gợi ý đáp án</summary>

1. **C.** Redo thường được tạo khi thay đổi block, có thể được LGWR ghi trước commit; DBWn có thể ghi block chưa commit sau khi redo cần thiết được ghi.
2. **Không.** Commit SCN và checkpoint SCN khác vai trò; transaction có thể đã durable qua online redo nhưng chưa cần datafile ghi đủ.
3. Vì roll forward tái dựng cả thay đổi của transaction chưa commit; cần undo để trả chúng về ảnh hợp lệ và khôi phục atomicity.
4. **Có.** Trong `READ COMMITTED`, mỗi câu SELECT có snapshot riêng; SELECT thứ hai bắt đầu sau commit có thể thấy `110`.
5. Cần biết undo cho snapshot còn không, SCN có hợp lệ, bảng có DDL thay đổi không, quyền Flashback và loại thao tác. Archived redo không đảm bảo Flashback Query mọi SCN.

</details>

## 18. Tài liệu Oracle chính thức

1. [Oracle Database 19c Concepts — Process Architecture](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/process-architecture.html): LGWR, fast commit, group commit, write-ahead protocol, DBWn và CKPT.
2. [Oracle Database 19c Concepts — Oracle Database Instance](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/oracle-database-instance.html): checkpoint, mục đích instance recovery, roll forward và rollback.
3. [Oracle Database 19c Concepts — Data Concurrency and Consistency](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-concurrency-and-consistency.html): SCN của query, MVCC/consistent read, undo và transaction isolation.
4. [Oracle Database 19c Concepts — Logical Storage Structures](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/logical-storage-structures.html): undo segments, undo tablespace, rollback và lịch sử phiên bản block.
5. [Oracle Database 19c Concepts — Physical Storage Structures](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/physical-storage-structures.html): online/archived redo log, redo record và change vectors.
6. [Oracle Database 19c SQL Language Reference — COMMIT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/COMMIT.html): commit, `WAIT`/`NOWAIT`, `IMMEDIATE`/`BATCH` và độ bền dữ liệu.
7. [Oracle Database 19c Database Reference — V$DATABASE](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-DATABASE.html), [V$DATAFILE](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-DATAFILE.html), [V$DATAFILE_HEADER](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-DATAFILE_HEADER.html) và [V$LOG](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-LOG.html): ý nghĩa các metadata SCN/redo/checkpoint.
8. [Oracle Database 19c Database Reference — V$UNDOSTAT](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-UNDOSTAT.html): thống kê undo và read-consistency troubleshooting.

**Chuỗi nguyên nhân cần nhớ khi đọc hệ thống Oracle:** DML thay đổi data và tạo undo/redo → LGWR ghi redo theo write-ahead protocol → commit đồng bộ thành công khi commit redo bền vững → DBWn ghi dirty blocks khi thích hợp → CKPT ghi nhận tiến độ checkpoint → nếu crash, redo làm lại những thay đổi cần thiết và undo gỡ các transaction chưa commit → snapshot SCN quyết định phiên bản dữ liệu mà mỗi query được phép nhìn thấy.
