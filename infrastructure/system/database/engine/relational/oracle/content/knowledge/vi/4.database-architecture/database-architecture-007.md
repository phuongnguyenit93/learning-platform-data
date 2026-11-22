# DBWn, LGWR, CKPT, SMON, PMON và vai trò phối hợp

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** Kiến trúc  
> **Mục tiêu:** Hiểu năm nhóm tiến trình nền quan trọng của Oracle Database, biết tiến trình nào ghi dữ liệu, tiến trình nào ghi redo, ai điều phối checkpoint, ai hỗ trợ phục hồi sau sự cố và ai dọn dẹp khi tiến trình người dùng gặp lỗi.

## 1. Vị trí của các tiến trình nền trong kiến trúc Oracle

Một Oracle Database đang hoạt động không chỉ có các bảng và tệp dữ liệu. Ở mức khái quát, nó gồm hai phần phối hợp:

- **Database:** tập hợp các tệp vật lý, tiêu biểu là **datafile**, **control file** và **online redo log**.
- **Instance:** bộ nhớ chia sẻ **SGA (System Global Area)** cùng các **background processes** phục vụ việc vận hành database.

Khi ứng dụng kết nối và chạy SQL, một **server process** thực hiện công việc cho session: đọc và thay đổi block trong bộ nhớ, sinh thông tin undo/redo, xử lý transaction. Các background process làm những việc hậu trường như ghi block, ghi redo, checkpoint và dọn dẹp khi có lỗi. Phần bộ nhớ riêng của process được gọi là **PGA**; bài này tập trung vào SGA và các tiến trình nền liên quan trực tiếp.

Hai thành phần SGA cần nhận biết:

1. **Database Buffer Cache:** lưu bản sao các block dữ liệu đang được truy cập. Block đã bị thay đổi trong cache nhưng chưa được ghi vào datafile là **dirty buffer**.
2. **Redo Log Buffer:** chứa các **redo entries** mô tả thay đổi cần có để phát lại trong quá trình khôi phục. Các redo entries được LGWR ghi ra online redo log.

Một mô hình giản lược:

```text
          Ứng dụng / SQL Developer / JDBC
                        |
                        v
               Server process
                        |
              +---------+---------+
              |                   |
              v                   v
     Database Buffer Cache   Redo Log Buffer
        (SGA, data blocks)   (SGA, redo entries)
              |                   |
             DBWn                LGWR
              |                   |
              v                   v
          DATAFILES         ONLINE REDO LOGS
              ^
              |
       CKPT điều phối checkpoint,
       theo dõi mốc tiến độ và
       cập nhật thông tin checkpoint
       trong CONTROL FILE / datafile headers

     SMON: phục hồi instance sau sự cố
     PMON: theo dõi, xử lý tiến trình lỗi
```

Đây là **sơ đồ trách nhiệm**, không có nghĩa CKPT trực tiếp ghi data block hoặc một câu lệnh SQL luôn lần lượt kích hoạt từng process. Các tiến trình làm việc đồng thời, phụ thuộc vào loại hoạt động và trạng thái hệ thống.

### Sơ đồ đối chiếu nhanh

| Tiến trình | Tên đầy đủ thường dùng | Chịu trách nhiệm chính | Đích làm việc chính |
|---|---|---|---|
| **DBWn** | Database Writer | Ghi dirty buffers từ buffer cache ra datafiles | Datafiles |
| **LGWR** | Log Writer | Ghi redo từ redo log buffer ra online redo logs | Online redo logs |
| **CKPT** | Checkpoint Process | Điều phối và ghi nhận thông tin tiến độ checkpoint | Control file, datafile headers |
| **SMON** | System Monitor | Phối hợp phục hồi instance khi cần; một số tác vụ bảo trì hệ thống | Trạng thái database, redo/undo trong quá trình recovery |
| **PMON** | Process Monitor | Giám sát và xử lý hậu quả khi user/server process thất bại | Session và các tài nguyên liên quan |

Tên viết **DBWn** nhấn mạnh có thể có nhiều database writer, ví dụ `DBW0`, `DBW1`, tùy phiên bản và cấu hình. Những process này là thành phần nội bộ của Oracle instance; người dùng không cần và không nên tự tạo bằng script ứng dụng.

## 2. Trước khi đi sâu: data, redo và undo khác nhau thế nào?

Ba khái niệm dễ bị trộn lẫn nhất trong chủ đề này là **data block**, **redo** và **undo**.

| Thành phần | Dùng để làm gì? | Nằm ở đâu? | Quan hệ với tiến trình |
|---|---|---|---|
| **Data block** | Mang dữ liệu bảng, index, metadata... | Buffer cache và datafiles | DBWn đưa block bẩn từ cache xuống datafiles |
| **Redo** | Ghi nhận thay đổi để tái thực hiện khi cần recovery | Redo log buffer, online redo logs và archived redo logs khi bật archiving | LGWR ghi redo vào online redo logs |
| **Undo** | Cho phép rollback transaction và đọc nhất quán theo phiên bản cũ | Undo segments trong undo tablespace; block undo cũng đi qua cache | Server process tạo undo; thay đổi của undo block cũng sinh redo |

Điểm then chốt:

- **Redo không phải bản sao nguyên vẹn của toàn bộ bảng.** Redo ghi thông tin thay đổi đủ để Oracle thực hiện cơ chế phục hồi.
- **Undo không phải online redo log.** Undo giúp quay về trạng thái logic phù hợp khi rollback và hỗ trợ consistent read.
- **DBWn có thể ghi một block đã bị sửa bởi transaction chưa commit.** Điều này không làm transaction tự động commit, vì redo và undo giữ vai trò để Oracle phục hồi trạng thái đúng.
- **Commit không yêu cầu DBWn ghi ngay mọi dirty block xuống datafile.** Commit thông thường gắn với việc redo, kể cả bản ghi commit, được LGWR ghi bền vững.

Ví dụ: một lệnh `UPDATE` thay đổi hàng trong buffer cache. Redo biểu diễn thay đổi được đặt vào redo log buffer; undo giữ thông tin cần để hoàn tác/đọc nhất quán. Tại một thời điểm, cả dữ liệu mới trong buffer cache và redo/undo có thể đang chờ những công việc ghi đĩa khác nhau.

### Nguyên tắc write-ahead logging (WAL)

Oracle tuân theo nguyên tắc **ghi redo cần thiết trước khi ghi block dữ liệu tương ứng xuống datafile**. Nếu DBWn ghi một dirty block, Oracle phải bảo đảm redo liên quan đã được ghi bền vững trước. Nhờ đó, một datafile có thể chứa block của giao dịch chưa commit mà database vẫn có đủ thông tin để xác định và hoàn tác trạng thái không hợp lệ sau sự cố.

WAL giúp giải thích vì sao **thứ tự ghi datafile không cần trùng thứ tự commit**, trong khi khả năng phục hồi vẫn được duy trì.

## 3. DBWn — Database Writer: ghi dirty buffers vào datafiles

### 3.1. Công việc chính

**DBWn** ghi các block đã thay đổi trong **Database Buffer Cache** xuống **datafiles**. Sau khi ghi thành công, những buffer phù hợp có thể được coi là sạch (clean) cho tới khi có thay đổi mới.

Dòng dữ liệu khái quát:

```text
Server process sửa block trong buffer cache
               |
               v
          Dirty buffer
               |
          DBWn ghi đĩa
               |
               v
            Datafile
```

DBWn phục vụ nhu cầu quản lý buffer cache và tiến trình checkpoint. Chẳng hạn, Oracle có thể cần DBWn làm việc khi:

- Cần có thêm buffer có thể tái sử dụng cho những block sắp đọc vào cache.
- Số lượng dirty buffer tăng, cần chủ động đưa một phần xuống datafiles.
- Có yêu cầu ghi liên quan checkpoint hoặc các hoạt động quản trị.
- Hệ thống cần duy trì tiến độ ghi nền để hạn chế lượng công việc phục hồi sau sự cố.

Các điều kiện kích hoạt, chiến lược ghi theo lô và số lượng writer tùy phiên bản/cấu hình; **không có quy tắc “mỗi COMMIT làm DBWn chạy một lần”**.

### 3.2. Điều DBWn không làm

DBWn **không phải** tiến trình quyết định transaction nào đã commit và không phải tiến trình ghi online redo log. DBWn có thể ghi dữ liệu của một transaction chưa commit: đây là hành vi bình thường trong một hệ quản trị giao dịch có redo/undo.

Ví dụ:

```sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;

-- Chưa COMMIT ở session này.
```

Trong lúc session đang giữ transaction chưa commit, block có thể bị ghi xuống datafile bởi DBWn. Transaction vẫn chưa được người dùng khác nhìn thấy như dữ liệu đã commit, và nếu transaction bị rollback thì Oracle sử dụng undo để xử lý đúng.

Điểm cần nhớ: **datafile đã chứa một thay đổi không đồng nghĩa thay đổi đó đã commit**.

### 3.3. Tại sao có nhiều DBWn?

Trên hệ thống có tải I/O hoặc cấu hình phù hợp, Oracle có thể dùng nhiều database writer (ví dụ `DBW0`, `DBW1`) để chia sẻ khối lượng công việc. Việc có bao nhiêu writer chịu ảnh hưởng của phiên bản, cấu hình, tài nguyên và cơ chế tự điều chỉnh. Không suy luận hiệu năng chỉ từ việc “nhiều DBWn hơn”.

## 4. LGWR — Log Writer: ghi redo và bảo đảm độ bền commit

### 4.1. LGWR làm gì?

**LGWR** chuyển redo entries từ **Redo Log Buffer** trong SGA sang các **online redo log files**.

```text
Các thay đổi của transaction
              |
              v
       Redo Log Buffer
              |
          LGWR ghi
              |
              v
      Online redo log(s)
```

Online redo log lưu chuỗi thay đổi phục vụ **instance recovery**; khi cơ sở dữ liệu ở `ARCHIVELOG` mode, các online redo log đầy được archiver sao lưu thành archived redo log để phục vụ các kịch bản recovery khác. Việc tạo archive thường liên quan **ARCn**, không thuộc trách nhiệm chính của LGWR.

LGWR thường ghi redo khi cần phục vụ commit, khi bộ đệm redo đạt điều kiện ghi, hoặc theo cơ chế ghi nền của Oracle. Chi tiết về ngưỡng và nhịp ghi là triển khai nội bộ và có thể khác giữa các phiên bản.

### 4.2. COMMIT gắn với LGWR như thế nào?

Giả sử session thực hiện:

```sql
INSERT INTO orders (order_id, amount)
VALUES (101, 250000);

COMMIT;
```

Diễn biến về mặt khái niệm:

1. Server process thay đổi block bảng/index/undo trong cache và tạo redo tương ứng.
2. Khi `COMMIT`, Oracle ghi nhận một **commit record** trong dòng redo và yêu cầu redo cần thiết được ghi ra online redo log.
3. Trong chế độ commit đồng bộ thông thường, **LGWR ghi redo cần thiết bền vững**, rồi session nhận thông báo commit thành công.
4. DBWn **không cần** ghi ngay block chứa đơn hàng `101` xuống datafile trước khi câu lệnh `COMMIT` kết thúc.

Vì thế, giao dịch vẫn có thể bền vững sau khi người dùng nhận “Commit complete”, dù datafile chưa chứa tất cả block mới. Nếu instance lỗi ngay sau đó, Oracle sử dụng redo để khôi phục phần thay đổi đã commit.

> **Điểm phân biệt:** Độ bền của commit thông thường dựa vào redo do LGWR ghi; việc ghi datafile là công việc riêng của DBWn. Oracle còn hỗ trợ các tùy chọn commit như `WRITE NOWAIT`/`BATCH` có thể thay đổi thời điểm session chờ redo được ghi, nên phát biểu trên mô tả **mặc định đồng bộ**.

### 4.3. Group commit

Khi nhiều session cùng commit gần nhau, Oracle có thể gom thông tin redo của nhiều transaction vào một đợt ghi của LGWR. Cơ chế **group commit** giảm số lần thao tác ghi riêng lẻ mà vẫn bảo đảm các commit được xác nhận theo ngữ nghĩa đồng bộ thông thường.

Đây là lý do không nên tưởng tượng “mỗi câu lệnh `COMMIT` tương đương một lần ghi đĩa riêng biệt cho một người dùng”.

### 4.4. Redo log switch có liên quan gì?

Online redo log thường gồm các **group** được sử dụng luân phiên. Khi nhóm redo hiện tại cần chuyển sang nhóm khác, Oracle thực hiện **log switch**. Log switch có liên quan đến tiến trình checkpoint và điều kiện có thể tái sử dụng redo group.

Nếu hệ thống ghi dirty buffers quá chậm, cảnh báo **`checkpoint not complete`** có thể xuất hiện khi một redo group chưa thể tái sử dụng an toàn. Trường hợp này cho thấy DBWn, CKPT và khả năng tái sử dụng redo có quan hệ vận hành, dù mỗi thành phần thực hiện một nhiệm vụ khác nhau. Trong chế độ archiving, việc group chưa được archive cũng có thể ngăn tái sử dụng; cần phân biệt nguyên nhân.

## 5. CKPT — Checkpoint Process: điều phối tiến độ checkpoint

### 5.1. Checkpoint giải quyết vấn đề gì?

Khi Oracle hoạt động lâu, nhiều data block đã thay đổi nhưng chưa được ghi hết xuống datafile. Nếu instance sập, Oracle phải xử lý redo để đưa database về trạng thái nhất quán. **Checkpoint** giúp Oracle ghi nhận một mốc tiến độ và giới hạn khối lượng phục hồi cần thực hiện.

**CKPT** phối hợp việc checkpoint và ghi nhận thông tin checkpoint trong **control file** và **datafile headers**. Theo các cơ chế nội bộ, CKPT báo cho DBWn biết tiến độ ghi cần thiết hoặc thúc đẩy hoạt động checkpoint.

Hai việc phải tách bạch:

- **DBWn ghi data block** xuống datafiles.
- **CKPT không trực tiếp ghi các data block đó.** Nó điều phối và cập nhật metadata checkpoint.

Không nên diễn giải “CKPT chạy” thành “CKPT chép mọi bảng xuống đĩa”.

### 5.2. SCN và checkpoint

**SCN (System Change Number)** là số thứ tự logic Oracle sử dụng để định vị và sắp xếp tiến độ thay đổi/trạng thái trong cơ sở dữ liệu. SCN không đơn giản là thời gian đồng hồ.

Checkpoint metadata và redo cho Oracle thông tin cần thiết để xác định **bắt đầu phục hồi từ đâu** và dữ liệu nào cần được cập nhật sau sự cố. Khi tiến độ checkpoint tiến lên, phạm vi redo phải xét cho instance recovery thường giảm; tuy nhiên hiệu quả còn phụ thuộc lưu lượng ghi và các hoạt động I/O khác.

### 5.3. Checkpoint “hoàn toàn” và checkpoint gia tăng

Có nhiều cách checkpoint được thực hiện tùy tình huống:

- **Checkpoint liên quan sự kiện** như thao tác quản trị hoặc log switch có thể yêu cầu DBWn tiến hành những công việc ghi nhất định.
- **Incremental checkpoint** giúp Oracle liên tục đẩy tiến độ ghi bẩn theo thời gian, thay vì dồn toàn bộ thành một đợt lớn.

Hệ thống đang chạy có thể tồn tại những dirty buffers chưa được ghi, ngay cả khi đã có checkpoint tiến độ. Vì vậy, **không phải checkpoint nào cũng đồng nghĩa toàn bộ cache sạch** hoặc mọi giao dịch được ghi hết vào datafile ngay lập tức.

### 5.4. Quan hệ với thời gian recovery

Nếu dirty buffers tồn đọng quá nhiều, phục hồi sau sự cố có thể cần đọc và áp dụng lượng redo lớn hơn. Nếu đẩy tiến độ checkpoint quá gấp, hoạt động ghi nền có thể tạo áp lực I/O cao.

Oracle có các cơ chế và tham số nhằm cân bằng **thời gian instance recovery mục tiêu** với **chi phí ghi trong lúc đang chạy**, tiêu biểu là `FAST_START_MTTR_TARGET` ở những bản/edition hỗ trợ. Người quản trị cần xem thống kê và tính chất workload trước khi thay đổi cấu hình.

**Không chỉnh các tham số checkpoint chỉ vì thấy có dirty buffers.** Dirty buffers tồn tại là bình thường; chẩn đoán cần dựa trên số liệu thực tế.

## 6. SMON — System Monitor: phục hồi instance và bảo trì hệ thống

### 6.1. Khi nào cần instance recovery?

Một **instance failure** xảy ra khi instance không thể hoàn tất chu trình đóng database bình thường, chẳng hạn host mất điện, tiến trình thiết yếu gặp lỗi hoặc hệ điều hành dừng đột ngột.

Sau sự cố, có thể tồn tại ba loại trạng thái:

1. Transaction **đã commit** và redo đã được ghi, nhưng data block tương ứng **chưa** xuống datafile.
2. Transaction **chưa commit**; một phần block của nó **có thể đã** được DBWn ghi xuống datafile.
3. Redo log và datafiles chứa những thông tin ở các thời điểm vật lý khác nhau, nên phải khôi phục tính nhất quán giao dịch.

**SMON** đóng vai trò quan trọng trong việc tổ chức/điều phối **instance recovery** khi database được mở trở lại sau một sự cố của instance. Oracle có thể dùng thêm các process phục hồi chuyên trách, tùy phiên bản và cấu hình.

### 6.2. Hai pha khái quát của instance recovery

Một cách dễ hiểu để mô tả instance recovery:

**Pha 1 — Roll forward (redo application):**

Oracle đọc redo cần thiết và tái áp dụng những thay đổi chưa có đầy đủ trong datafiles. Các thay đổi được phát lại có thể thuộc **cả giao dịch đã commit và chưa commit** tại thời điểm sự cố.

**Pha 2 — Transaction recovery (rollback):**

Oracle sử dụng thông tin undo để **hoàn tác các giao dịch chưa commit** theo ngữ nghĩa giao dịch. Nhờ đó, database không coi thay đổi chưa commit là dữ liệu hợp lệ.

```text
Instance sập bất ngờ
         |
         v
Oracle đọc trạng thái checkpoint/redo
         |
         v
Roll forward: áp dụng redo cần thiết
         |
         v
Undo/transaction recovery cho các
giao dịch chưa commit
         |
         v
Database trở về trạng thái giao dịch nhất quán
```

Trong hệ thống thực, các pha và công việc rollback có thể đan xen hoặc được song song hóa; một phần transaction recovery có thể tiếp tục khi database đã mở cho hoạt động. Đừng hiểu sơ đồ là một quy trình duy nhất luôn khóa mọi kết nối cho tới khi **tất cả** tác vụ hoàn tất.

**Điểm quan trọng:** Instance recovery dùng redo/undo để phục hồi database sau lỗi instance. Nó khác với **media recovery** khi datafile bị mất/hỏng và phải dùng backup cùng các nguồn redo phù hợp.

### 6.3. Ngoài instance recovery

SMON còn tham gia những hoạt động bảo trì hệ thống như dọn dẹp tài nguyên/tác vụ hậu trường trong một số tình huống, tùy phiên bản. Cơ chế quản lý segment và space trong Oracle hiện đại có nhiều process/chức năng chuyên dụng; không nên ghi nhớ máy móc rằng “SMON luôn hợp nhất mọi vùng trống” như các mô tả đời rất cũ.

### 6.4. SMON không thay cho LGWR và DBWn

SMON thực hiện phục hồi **dựa trên dữ liệu mà các thành phần khác đã duy trì**:

- LGWR đã ghi redo thì có nguồn để phát lại thay đổi trong điều kiện recovery phù hợp.
- DBWn đã ghi một phần block thì recovery xử lý phần chênh lệch còn lại.
- CKPT đã cập nhật thông tin tiến độ thì Oracle có cơ sở để định vị phạm vi phục hồi.

SMON không thể “đoán” lại một transaction nếu thông tin phục hồi cần thiết không tồn tại. Việc bảo vệ online redo, datafiles, control files, backup và archived logs là vấn đề vận hành rất quan trọng.

## 7. PMON — Process Monitor: xử lý khi tiến trình người dùng gặp lỗi

### 7.1. Khác biệt giữa process failure và instance failure

Không phải lỗi kết nối nào cũng khiến **toàn bộ Oracle instance** dừng.

- **Process failure:** một server/user process hoặc session gặp lỗi/thoát bất thường, trong khi instance vẫn chạy.
- **Instance failure:** cả instance không còn hoạt động bình thường, thường cần cơ chế instance recovery khi khởi động lại.

**PMON** là tiến trình theo dõi, phối hợp dọn dẹp tài nguyên liên quan các process thất bại. Trong những phiên bản hiện đại, một số công việc cleanup được phân công cho các process khác như **CLMN** và các cleanup workers; vì thế cần hiểu **PMON là vai trò giám sát/phối hợp**, không nhất thiết tự thực hiện từng thao tác nhỏ.

### 7.2. Những tài nguyên cần được xử lý

Nếu một server process mất đột ngột trong lúc đang phục vụ session, Oracle phải xử lý phù hợp các tài nguyên gắn với quá trình đó, ví dụ:

- Khôi phục hoặc giải phóng tài nguyên tiến trình/session không còn sử dụng.
- Xử lý transaction chưa hoàn tất, bao gồm việc đưa dữ liệu/khóa về trạng thái đúng theo cơ chế rollback/recovery.
- Dọn các cấu trúc nội bộ và khóa/tài nguyên gắn với process bị lỗi khi việc cleanup cho phép.

**Không đồng nhất “PMON dọn tài nguyên” với “mọi transaction rollback ngay lập tức”.** Với giao dịch lớn hoặc kết nối phức tạp, cleanup/rollback có thể diễn ra bất đồng bộ và mất thời gian; một số tài nguyên chỉ được giải phóng khi các bước cần thiết hoàn tất.

### 7.3. PMON và đăng ký listener: thay đổi theo phiên bản

Ở một số tài liệu Oracle đời cũ, PMON còn được mô tả là tiến trình **đăng ký instance/service với listener**.

Từ **Oracle Database 12c**, công việc đăng ký động với listener được giao chủ yếu cho **LREG (Listener Registration Process)**. Khi nghiên cứu Oracle 19c, 21c, 23ai hoặc 26ai, không nên gắn chức năng listener registration trực tiếp cho PMON như một đặc điểm cố định.

Đây là một ví dụ cho thấy tên process và phân chia trách nhiệm nền có thể phát triển theo phiên bản; hãy đối chiếu tài liệu của phiên bản đang dùng.

## 8. Dòng thời gian phối hợp: từ DML đến COMMIT

Xét câu lệnh mô phỏng ứng dụng ngân hàng:

```sql
-- Đang kết nối trong schema ứng dụng, với bảng minh họa ACCOUNTS.
UPDATE accounts
SET balance = balance - 500
WHERE account_id = 10;

UPDATE accounts
SET balance = balance + 500
WHERE account_id = 20;

COMMIT;
```

Đây là một transaction gồm hai thay đổi và một commit. Luồng phối hợp ở mức kiến trúc:

```text
Bước 1: Server process thực hiện hai UPDATE
    |
    +--> Đọc/sửa block trong Database Buffer Cache
    |         -> buffer liên quan trở thành dirty
    |
    +--> Tạo undo để có thể rollback/consistent read
    |
    +--> Tạo redo entries trong Redo Log Buffer

Bước 2: COMMIT
    |
    +--> Tạo commit record và yêu cầu redo cần thiết được ghi
    |
    +--> LGWR ghi redo bền vững vào online redo logs
    |
    +--> Session nhận xác nhận COMMIT (chế độ đồng bộ thông thường)

Song song/không phụ thuộc trực tiếp COMMIT:
    |
    +--> DBWn có thể ghi dirty buffers ra datafiles
    |
    +--> CKPT điều phối tiến độ checkpoint
    |
    +--> SMON/PMON bình thường không phải xử lý sự cố session
```

### Sau khi commit, datafiles chưa được ghi thì sao?

Giả sử LGWR đã ghi đủ redo cho transaction chuyển tiền và session nhận thông báo commit, nhưng DBWn chưa ghi đủ block dữ liệu của hai tài khoản. Nếu instance mất điện ngay:

1. Online redo logs chứa thông tin thay đổi đã commit.
2. Khi khởi động lại, Oracle thực hiện instance recovery với vai trò của SMON và các thành phần phục hồi.
3. Những thay đổi còn thiếu trong datafiles được tái tạo từ redo cần thiết.
4. Giao dịch chuyển tiền đã commit có thể được bảo toàn theo bảo đảm durability của cấu hình commit và lưu trữ.

Đây là biểu hiện thực tế của **D trong ACID (Durability)**.

### Nếu session chỉ UPDATE rồi ngắt đột ngột?

Giả sử client phát ra một `UPDATE` nhưng chưa `COMMIT`, sau đó server process chết trong khi instance vẫn hoạt động:

1. PMON/các cleanup process liên quan phát hiện và phối hợp xử lý tiến trình/session lỗi.
2. Database đưa transaction chưa commit về trạng thái đúng bằng cơ chế rollback/undo.
3. Datafile có thể đã chứa một số block dirty từ transaction đó; việc này vẫn không biến transaction thành committed.
4. Session mới không được coi kết quả chưa commit của transaction thất bại là thay đổi đã hoàn tất.

Vì instance không bị sập, tình huống này khác với **SMON khôi phục cả instance khi startup**.

## 9. Dòng thời gian phối hợp: checkpoint và mất điện

Một cách nhìn khác lấy trọng tâm là **thời điểm ghi**.

| Thời điểm | Điều đã xảy ra | Ý nghĩa |
|---|---|---|
| T1 | Ứng dụng sửa block A, tạo redo | A dirty trong cache; redo đang được tạo |
| T2 | Transaction chứa thay đổi A commit; LGWR đã ghi redo | Thay đổi đã commit có đường khôi phục mà chưa cần DBWn ghi A |
| T3 | DBWn ghi một số dirty blocks, trong đó có thể có A | Datafiles tiến gần trạng thái mới hơn |
| T4 | CKPT cập nhật tiến độ checkpoint phù hợp | Giúp định vị/phạm vi recovery khi có sự cố |
| T5 | Transaction khác sửa block B nhưng chưa commit; DBWn có thể đã ghi B theo WAL | Datafile có thể chứa dữ liệu chưa commit |
| T6 | Host mất điện, instance dừng không sạch | Cần instance recovery khi khởi động lại |
| T7 | SMON/các recovery workers hỗ trợ phát lại redo cần thiết, hoàn tác transaction chưa commit | Giữ A đã commit; loại bỏ kết quả chưa commit của B |

Dòng thời gian chỉ nhằm giải thích khả năng xảy ra. Trong hệ thống thực, redo flush, datafile write, checkpoint và transaction recovery có thể diễn ra đồng thời với nhiều session và nhiều buffer.

### Điều sẽ hỏng nếu không có nguyên tắc ghi redo trước

Giả sử DBWn có thể đưa block chưa commit xuống datafile nhưng redo liên quan lại bị mất. Khi sự cố xảy ra, database có thể thiếu thông tin cần thiết để khôi phục nhất quán. Chính vì vậy Oracle phối hợp **WAL, redo, undo, DBWn và recovery** thay vì chỉ yêu cầu “ghi mọi block khi commit”.

## 10. Quan sát tiến trình và số liệu thực tế bằng SQL

Phần này chỉ sử dụng truy vấn **đọc trạng thái**. Trên Oracle, quyền xem các dynamic performance views (như `V$PROCESS`, `V$BGPROCESS`, `V$SYSSTAT`) thường do DBA cấp; tài khoản ứng dụng thông thường có thể gặp `ORA-00942` hoặc lỗi quyền tương ứng. Có thể dùng tài khoản quản trị trong môi trường thực hành được cấp phép để quan sát, nhưng không cấp `DBA` rộng rãi chỉ để chạy ví dụ.

### 10.1. Xem các tiến trình nền Oracle nhận biết

```sql
SELECT name, description
FROM v$bgprocess
WHERE name IN ('LGWR', 'CKPT', 'SMON', 'PMON')
   OR name LIKE 'DBW%'
ORDER BY name;
```

Ở đây:

- `LGWR`: Log Writer.
- `CKPT`: Checkpoint Process.
- `SMON`: System Monitor.
- `PMON`: Process Monitor.
- `DBW0`, `DBW1`, ...: các Database Writer khi môi trường có nhiều writer.

`V$BGPROCESS` có thể thể hiện metadata của các loại background process; kết quả một dòng mô tả **không tự khẳng định mọi tiến trình đều đang bận ghi**. Tên process phụ trợ và cấu trúc view có thể thay đổi theo phiên bản.

Muốn xem process thực tế của instance (khi có quyền):

```sql
SELECT pname, program
FROM v$process
WHERE pname IN ('LGWR', 'CKPT', 'SMON', 'PMON')
   OR pname LIKE 'DBW%'
ORDER BY pname;
```

Cột `PNAME` và thông tin process phụ thuộc phiên bản; trên một số môi trường có thể cần sử dụng công cụ của hệ điều hành hoặc đối chiếu view thích hợp.

### 10.2. Xem trạng thái instance/database

```sql
SELECT instance_name, status, startup_time
FROM v$instance;

SELECT name, open_mode
FROM v$database;
```

Với multitenant, quan sát PDB:

```sql
SELECT name, open_mode
FROM v$pdbs
ORDER BY name;
```

Dữ liệu này giúp phân biệt “process nền đang chạy” với “PDB phục vụ người dùng đã mở”.

### 10.3. Xem thống kê ghi và redo

```sql
SELECT name, value
FROM v$sysstat
WHERE name IN ('redo size', 'redo writes', 'physical writes')
ORDER BY name;
```

Giải thích ý nghĩa quan sát:

- `redo size`: tổng lượng redo được tạo theo đơn vị thống kê của Oracle.
- `redo writes`: thống kê số hoạt động ghi redo.
- `physical writes`: thống kê I/O ghi vật lý ở phạm vi instance.

Các giá trị thường là **tích lũy** theo thời gian hoạt động của instance. Một snapshot đơn lẻ chưa đủ để suy ra tốc độ; muốn ước lượng tốc độ phải so sánh giá trị ở hai thời điểm trong cùng instance. Đồng thời, **physical writes không phải lúc nào cũng chỉ do DBWn thực hiện**; không dùng chỉ số đó để suy diễn chính xác số lần DBWn ghi mà không xét thêm ngữ cảnh.

### 10.4. Xem trạng thái online redo log groups

```sql
SELECT group#, sequence#, status
FROM v$log
ORDER BY group#;
```

Một số trạng thái thường gặp:

- `CURRENT`: nhóm redo log đang được sử dụng để ghi redo.
- `ACTIVE`: nhóm log còn cần cho instance recovery, chưa thể coi là không còn cần.
- `INACTIVE`: nhóm log không còn cần cho instance recovery; để tái sử dụng vẫn có thể phải đáp ứng thêm yêu cầu archiving/cấu hình.

Kết quả này hỗ trợ hiểu liên hệ log switch và checkpoint; nó **không** trực tiếp chỉ ra transaction nào đã commit.

### 10.5. Tìm thông tin checkpoint/recovery

Trong những phiên bản có view này và quyền phù hợp:

```sql
SELECT target_mttr, estimated_mttr
FROM v$instance_recovery;
```

- `TARGET_MTTR`: mục tiêu thời gian instance recovery theo cơ chế tính toán của Oracle.
- `ESTIMATED_MTTR`: ước lượng thời gian instance recovery tại thời điểm quan sát.

Đây là **ước lượng hệ thống**, không phải bảo đảm database luôn mở lại trong chính xác số giây được hiển thị. Các chỉ số có thể phụ thuộc thiết lập và phiên bản.

> **Lưu ý thực hành:** Các truy vấn quan sát không làm dirty block “lập tức được DBWn ghi hết”, không ép LGWR ghi thêm ngoài cơ chế thông thường và không thay thế việc xem alert log khi có lỗi thực tế.

## 11. Phân biệt vai trò trong những tình huống hay nhầm

| Tình huống | Tiến trình có vai trò chính | Vì sao? |
|---|---|---|
| Buffer cache chứa nhiều dirty blocks; Oracle cần giải phóng buffer | **DBWn** | Ghi dirty block từ cache ra datafiles |
| Người dùng `COMMIT`, yêu cầu xác nhận giao dịch bền vững | **LGWR** | Ghi redo bao gồm thông tin commit vào online redo logs |
| Oracle ghi nhận mốc checkpoint và cập nhật metadata | **CKPT** (phối hợp **DBWn**) | CKPT điều phối checkpoint; DBWn thực hiện ghi data block |
| Instance sập rồi khởi động lại, cần áp dụng redo và hoàn tác giao dịch chưa commit | **SMON** cùng recovery workers | Thực hiện/điều phối instance recovery |
| Một server process của session chết, nhưng instance vẫn hoạt động | **PMON** cùng cleanup workers | Theo dõi, dọn dẹp tiến trình/session lỗi |
| Listener không thấy service do instance chưa đăng ký | **LREG** trên Oracle 12c+ | Đăng ký động service với listener, khác vai trò ghi redo/checkpoint |
| Online redo log group đầy, cần chuyển nhóm đang ghi | **LGWR** và các cơ chế log switch/checkpoint liên quan | Nhóm log chuyển vòng, điều kiện tái sử dụng chịu tác động của checkpoint/archiving |
| Application chạy `SELECT` thông thường | Chủ yếu **server process** và cơ chế đọc/cache | Năm process nền không thay thế việc server process thực thi SQL |

### Những nhận định sai cần loại bỏ

**“COMMIT xong là datafile phải được ghi xong.”** Không đúng. Trong commit đồng bộ thông thường, LGWR bảo đảm redo cần thiết được ghi bền vững, còn DBWn ghi dirty buffers theo cơ chế riêng.

**“DBWn chỉ ghi block đã commit.”** Không đúng. DBWn có thể ghi block liên quan transaction chưa commit; undo/redo giữ database nhất quán.

**“LGWR ghi dữ liệu bảng trực tiếp vào datafile.”** Không đúng. LGWR ghi redo vào online redo logs.

**“CKPT chính là process ghi toàn bộ dirty buffer.”** Không đúng. CKPT điều phối checkpoint và cập nhật metadata; DBWn ghi data blocks. Checkpoint gia tăng cũng không có nghĩa tất cả block của database lập tức sạch.

**“SMON và PMON đều làm cùng một việc.”** Không đúng. SMON nổi bật ở **instance recovery**; PMON nổi bật ở **xử lý process failure khi instance còn chạy**.

**“PMON luôn đăng ký service với listener.”** Không còn đúng như một phát biểu chung trên Oracle hiện đại; từ 12c cơ chế đăng ký động chủ yếu thuộc LREG.

**“Redo và undo là hai tên của một loại log.”** Không đúng. Redo giúp tái thực hiện thay đổi trong recovery; undo giúp hoàn tác và đọc nhất quán.

## 12. Chẩn đoán các hiện tượng hiệu năng và sự cố liên quan

Khi vận hành, các process này thường xuất hiện gián tiếp qua thống kê, wait event hoặc thông điệp trong alert log.

### 12.1. Nhiều session chờ commit lâu

Nếu ứng dụng báo thao tác `COMMIT` chậm, một hướng điều tra là độ trễ liên quan ghi redo. Wait event như **`log file sync`** thường thể hiện thời gian foreground chờ hoàn tất commit; **`log file parallel write`** liên quan hoạt động ghi redo của LGWR.

Hướng xác minh: kiểm tra thời gian chờ, tốc độ ghi/latency của thiết bị lưu online redo logs, tải hệ thống và nhịp commit. Một wait event đơn lẻ chưa đủ để kết luận phần cứng hỏng hoặc cần tăng tham số.

### 12.2. Buffer cache thiếu buffer có thể tái sử dụng

Nếu các session phải chờ buffer được giải phóng và workload sinh nhiều dirty buffers, cần xem tốc độ ghi của DBWn, hiệu suất I/O của datafiles và cấu hình bộ nhớ. Các wait event như **`free buffer waits`** có thể gợi ý vấn đề liên quan khả năng cung cấp buffer sạch. Không mặc định rằng cứ tăng số lượng DBWn là giải quyết được.

### 12.3. Alert log xuất hiện “checkpoint not complete”

Thông điệp này gợi ý tiến độ checkpoint có thể chưa cho phép tái sử dụng một redo log group. Cần kiểm tra kích thước/số lượng redo groups, tốc độ đổi log, tiến độ ghi DBWn/CKPT và nguyên nhân gây chậm lưu trữ. Trên hệ thống bật ARCHIVELOG, kiểm tra thêm tình trạng lưu trữ/archiving khi liên quan.

### 12.4. Startup sau mất điện lâu

Nếu instance bị dừng đột ngột, startup có thể cần thời gian cho instance recovery. Lượng redo cần áp dụng, trạng thái checkpoint, tốc độ I/O và transaction recovery đều có thể ảnh hưởng thời gian hoàn tất. Kiểm tra alert log và các thông tin recovery trước khi can thiệp.

### 12.5. Một session biến mất nhưng database vẫn hoạt động

Nếu một process ứng dụng/server gặp lỗi, Oracle có thể cần cleanup và rollback transaction chưa hoàn tất. Đây là tình huống liên quan PMON/cleanup workers, không nhất thiết là instance recovery. Việc transaction lớn chưa được rollback xong có thể khiến khóa/tài nguyên chưa giải phóng ngay.

> Trên môi trường production, không chủ động giết tiến trình nền LGWR, DBWn, CKPT, SMON hoặc PMON để “thử recovery”. Những process thiết yếu bị lỗi có thể làm instance bị dừng. Thực hành phục hồi phải dùng môi trường cô lập và quy trình quản trị đã chuẩn bị.

## 13. Bài thực hành: đọc sơ đồ và giải thích đúng tiến trình

### Bài 1 — Phân công nhiệm vụ

Với mỗi mô tả sau, xác định tiến trình phù hợp:

1. Dirty buffer trong buffer cache được ghi xuống datafile.
2. Redo trong SGA được ghi vào online redo log.
3. Metadata checkpoint được cập nhật trong control file và datafile headers.
4. Instance bị mất điện, khi khởi động phải áp dụng redo và xử lý transaction chưa commit.
5. Một server process chết bất ngờ nhưng toàn bộ instance vẫn hoạt động.

**Đáp án:** (1) DBWn; (2) LGWR; (3) CKPT (phối hợp DBWn); (4) SMON và cơ chế recovery; (5) PMON và các process cleanup liên quan.

### Bài 2 — Phân tích transaction chưa commit

Một session chạy:

```sql
UPDATE products
SET price = price + 1000
WHERE product_id = 42;

-- Không COMMIT, session vẫn đang mở.
```

Giả sử DBWn có thể đã ghi block liên quan thay đổi này. Hỏi:

- Dữ liệu đó đã trở thành **committed** chưa?
- Vì sao sau khi session rollback hoặc instance recovery, Oracle vẫn có thể khôi phục trạng thái nhất quán?
- Tiến trình nào chịu trách nhiệm ghi redo trong khi transaction đang thực hiện?

**Gợi ý:** Chưa commit; undo/redo và quy tắc WAL bảo vệ ngữ nghĩa transaction; LGWR là tiến trình ghi redo từ log buffer ra online redo log.

### Bài 3 — Giải thích commit thành công trước khi datafile được cập nhật

Một ứng dụng gọi `COMMIT` và nhận thành công. Sau đó instance sập trước khi DBWn ghi hết các block đã sửa. Hãy mô tả:

1. Điều gì đã được LGWR ghi để commit đồng bộ thông thường được xác nhận?
2. Vai trò của SMON lúc khởi động lại là gì?
3. Vì sao không cần DBWn ghi tất cả data blocks ngay khi `COMMIT`?

**Gợi ý:** LGWR bảo đảm redo cần thiết, bao gồm commit record, được lưu bền vững; instance recovery áp dụng redo để phục hồi thay đổi đã commit; cơ chế ghi redo và ghi datafile được tách nhằm duy trì hiệu suất và tính bền vững.

### Bài 4 — Quan sát một instance thật

Trong môi trường lab có quyền đọc các dynamic performance views:

```sql
SELECT name, description
FROM v$bgprocess
WHERE name IN ('LGWR', 'CKPT', 'SMON', 'PMON')
   OR name LIKE 'DBW%';

SELECT name, value
FROM v$sysstat
WHERE name IN ('redo size', 'redo writes', 'physical writes');

SELECT group#, sequence#, status
FROM v$log
ORDER BY group#;
```

Yêu cầu báo cáo ngắn:

- Tên DBWn được instance liệt kê là gì?
- Chỉ số nào liên quan redo? Chỉ số nào liên quan ghi vật lý?
- Vì sao các thống kê không đủ để nói một transaction cụ thể đã commit hay chưa?
- Nếu thấy log group `CURRENT`, điều đó nói gì về LGWR; nếu group `ACTIVE`, nó còn có ý nghĩa gì với instance recovery?

**Lưu ý:** Đây là bài quan sát, không cần ép checkpoint, log switch hoặc gây lỗi database.

## 14. Mối liên hệ với ACID và độ tin cậy của Oracle

Năm process nêu trong bài giúp giải thích một số tính chất quan trọng của hệ quản trị quan hệ:

- **Atomicity:** transaction được xem như một đơn vị logic; nếu chưa commit và phải rollback, Oracle dùng undo/recovery để hoàn tác thích hợp.
- **Consistency:** database duy trì các ràng buộc và trạng thái hợp lệ thông qua cơ chế transaction cùng kiểm soát của SQL.
- **Isolation:** các session không mặc định nhìn thấy thay đổi chưa commit của nhau; Oracle dùng cơ chế đọc nhất quán dựa trên undo và kiểm soát đồng thời.
- **Durability:** với commit đồng bộ thông thường, redo đã được LGWR ghi bền vững giúp phục hồi các transaction đã commit dù datafile chưa kịp cập nhật.

Các tính chất này là kết quả của **nhiều cơ chế phối hợp**, không phải một process duy nhất “bảo đảm tất cả”.

Khi gặp câu hỏi **“Vì sao COMMIT thành công dù DBWn chưa ghi datafile?”**, hãy nhớ **LGWR + redo + recovery**. Khi gặp câu hỏi **“Vì sao database vẫn nhất quán nếu datafile đã có block chưa commit?”**, hãy nhớ **undo + redo + WAL + transaction recovery**. Khi hỏi **“Ai điều phối checkpoint, ai phục hồi instance, ai dọn lỗi session?”**, lần lượt nghĩ đến **CKPT, SMON, PMON** trong phạm vi vai trò của chúng và các process phụ trợ của Oracle hiện đại.

---

### Thuật ngữ cốt lõi

| Thuật ngữ | Ý nghĩa |
|---|---|
| **SGA** | Bộ nhớ chia sẻ của Oracle instance |
| **Database Buffer Cache** | Nơi lưu data blocks được truy cập trong bộ nhớ |
| **Dirty buffer** | Buffer đã thay đổi nhưng phiên bản sửa chưa được ghi tương ứng xuống datafile |
| **Redo Log Buffer** | Bộ đệm redo trong SGA |
| **Online redo log** | Tệp ghi redo do LGWR ghi để phục vụ recovery |
| **Undo** | Thông tin hỗ trợ rollback và consistent read |
| **Checkpoint** | Cơ chế theo dõi/điều phối tiến độ ghi và mốc phục hồi |
| **SCN** | System Change Number, thứ tự logic của thay đổi/trạng thái |
| **Instance recovery** | Phục hồi trạng thái hợp lệ sau instance failure bằng redo và undo |
| **Process cleanup** | Thu dọn tài nguyên liên quan tiến trình/session gặp lỗi |

**Tài liệu tham khảo theo phiên bản:** Bộ tài liệu *Oracle Database Concepts* (kiến trúc instance, background processes, redo, undo, checkpoints) và *Oracle Database Administrator's Guide* (instance startup/recovery, redo log management) trên [Oracle Database Documentation](https://docs.oracle.com/en/database/). Khi quan sát một phiên bản cụ thể như 19c, 21c hoặc Oracle AI Database 26ai, cần đối chiếu tên process phụ trợ và view với bộ tài liệu chính xác của phiên bản đó.

