# Nhập dữ liệu hàng loạt, mã hóa và định dạng theo công cụ hệ quản trị

Khi thêm vài hàng dữ liệu, ta thường dùng `INSERT INTO ... VALUES (...)`. Nhưng khi cần nhập **hàng trăm nghìn hoặc hàng triệu hàng** từ CSV, TSV, tệp xuất của hệ thống khác, kho lưu trữ đám mây hoặc một bản sao dữ liệu, việc gửi từng câu `INSERT` riêng lẻ thường tốn nhiều lần trao đổi với máy chủ và khó quản lý lỗi. Các hệ quản trị cơ sở dữ liệu cung cấp **công cụ nhập hàng loạt** (*bulk import/load*) để đọc dữ liệu hiệu quả hơn, đồng thời có các quy tắc riêng về **mã hóa ký tự, phân tách trường, dấu nháy, giá trị NULL, kiểu dữ liệu, phân quyền và xử lý lỗi**.

Chẳng hạn, một tệp có dòng:

```csv
order_id,customer_name,amount,note
WEB-001,"Trần, Bình",125000.50,"Khách nói ""giao sớm"""
```

không thể đọc đúng nếu chỉ `SPLIT` từng dòng theo dấu phẩy: tên `"Trần, Bình"` chứa một dấu phẩy **bên trong trường được bao nháy**, còn ghi chú dùng hai dấu `""` để biểu diễn một dấu `"`. Nếu chọn sai mã hóa, `Trần` có thể thành chuỗi lỗi dấu. Nếu ánh xạ NULL hoặc ngày/tháng không đúng, dữ liệu có thể vẫn được nhập nhưng sai ý nghĩa.

Bài học thuộc **Database SQL → Thêm dữ liệu**. Ta sẽ phân biệt nhập bằng SQL và tiện ích của hệ quản trị; thực hành một quy trình PostgreSQL tự chứa bằng `COPY`; so sánh `\copy`, MySQL `LOAD DATA`, SQL Server `BULK INSERT`/`bcp`, Oracle SQL*Loader, SQLite `.import` và công cụ kho dữ liệu; sau đó thiết kế một pipeline an toàn: **khai báo hợp đồng dữ liệu → nhập staging → kiểm tra/chuyển kiểu → ghi bảng đích → đối soát và vận hành**.

> **Nguyên tắc xuyên suốt:** nhập hàng loạt không chỉ là đưa bytes vào bảng. Muốn dữ liệu đáng tin, phải bảo đảm **đúng hàng, đúng cột, đúng ký tự, đúng kiểu, đúng nghĩa và có thể nhập lại một cách kiểm soát**.

## 1. Khi nào nên nhập dữ liệu hàng loạt?

Một số tình huống:

- Nạp dữ liệu khách hàng từ một tệp CSV do hệ thống CRM xuất.
- Nhập lịch sử giao dịch để chuyển đổi hệ thống.
- Đồng bộ danh mục sản phẩm từ đối tác hằng ngày.
- Nhập bảng giá, tồn kho hoặc đơn hàng từ các tệp theo lô.
- Nạp dữ liệu phân tích vào data warehouse từ object storage.
- Khôi phục một bảng từ bản xuất dữ liệu được quản lý.

Các phương pháp phổ biến:

| Phương pháp | Khi phù hợp | Lưu ý |
| --- | --- | --- |
| Một `INSERT` cho từng hàng | Ghi giao dịch nhỏ, logic từng hàng | Nhiều round-trip nếu hàng triệu dòng |
| `INSERT` nhiều hàng trong một câu | Lô vừa, ứng dụng tạo dữ liệu | Giới hạn tham số/câu lệnh, kích thước batch |
| Prepared statement + batch API | Ứng dụng xử lý từng record nhưng gửi theo lô | Xử lý batch failure, transaction, retry |
| Công cụ bulk load (`COPY`, `LOAD DATA`, `BULK INSERT`, ...) | Tệp lớn, định dạng ổn định, tốc độ quan trọng | Cần thống nhất encoding, CSV dialect, quyền truy cập tệp |
| Import vào staging rồi `INSERT ... SELECT`/`MERGE` | Dữ liệu bên ngoài chưa tin cậy, cần kiểm tra và dedup | Có bước trung gian và chính sách lỗi |
| Công cụ ETL/ELT/connector | Nguồn liên tục, nhiều hệ thống, lịch trình và giám sát | Cần hiểu cơ chế load underlying và idempotency |

**Không phải mọi bài toán đều nên dùng bulk load.** Nếu ứng dụng ghi vài đơn mỗi giây cần kiểm soát giao dịch chi tiết, prepared `INSERT` thông thường có thể phù hợp hơn. Bulk load đặc biệt hữu ích khi đầu vào đã là **một lô dữ liệu**.

### 1.1. Phân biệt import và backup/restore

Tệp **CSV** mô tả các hàng và cột, nhưng thường không lưu đầy đủ khóa chính, chỉ mục, trigger, quyền, sequence, kiểu riêng, logic schema và metadata. Các công cụ **backup/restore** chuyên dụng như PostgreSQL `pg_dump`/`pg_restore`, MySQL dump hoặc Oracle Data Pump phục vụ bài toán khác: khôi phục đối tượng và dữ liệu theo định dạng của hệ quản trị.

Không xem CSV là bản sao lưu hoàn chỉnh của database. Ngược lại, không dùng công cụ restore dump riêng của Oracle để nạp một CSV của đối tác nếu không có bước chuyển đổi phù hợp.

## 2. Hợp đồng nhập dữ liệu phải được định nghĩa trước

Trước khi chọn câu lệnh load, hãy lập một **hợp đồng định dạng** (*import contract*):

| Thuộc tính | Ví dụ minh họa | Vì sao quan trọng? |
| --- | --- | --- |
| Nguồn và phiên bản | `partner_orders_v2` | Biết schema và quy tắc của nhà cung cấp |
| Kiểu tệp | CSV, TSV, JSON Lines | Mỗi loại có parser khác nhau |
| Encoding | UTF-8 | Đọc đúng tiếng Việt, emoji, ký tự đặc biệt |
| BOM | Không BOM hoặc có UTF-8 BOM được xử lý rõ | BOM có thể lẫn vào tên cột/giá trị đầu |
| Kết thúc dòng | LF (`\n`) hoặc CRLF (`\r\n`) | Tránh ký tự `\r` dư hoặc gộp hàng |
| Field delimiter | Dấu phẩy `,` | Phân biệt dấu phẩy trong nội dung |
| Quote/escape | Quote `"`, nháy đôi `""` | Giữ dấu phẩy và xuống dòng trong giá trị |
| Header | Một dòng tên cột | Phải thống nhất có bỏ qua hay đối chiếu tên |
| NULL | Marker `__NULL__` chưa bao quote | Phân biệt dữ liệu thiếu với chuỗi rỗng |
| Định dạng ngày | `YYYY-MM-DD` | Tránh nhập nhầm tháng/ngày |
| Timestamp và timezone | ISO 8601 với offset `+07:00` | Không dịch sai thời điểm |
| Số tiền | `123456.78`, dấu chấm thập phân | Không dùng dấu phẩy làm phân cách nghìn khi dấu phẩy là delimiter |
| Khóa nghiệp vụ | `(source_system, source_order_id)` | Xử lý trùng và nhập lại |
| Kiểm tra hợp lệ | NOT NULL, range, status, FK | Ngăn dữ liệu lỗi đi vào bảng chính |
| Chính sách lỗi | Chặn lô hoặc cách ly hàng lỗi | Có thể đối soát nguyên nhân |
| Chính sách tải lại | Upsert, skip hoặc thay thế phân vùng | Chạy lại không cộng trùng |

Tên cột nhìn giống nhau chưa đủ. Cột `amount` có thể là **đồng** ở nguồn A nhưng **nghìn đồng** ở nguồn B; cột `created_at` có thể là giờ UTC ở nguồn A và giờ Việt Nam ở nguồn B. Cần chuẩn hóa **đơn vị và ý nghĩa** bên cạnh cú pháp.

### 2.1. Độ hạt của một hàng

Một hàng trong tệp là **một đơn hàng**, **một dòng sản phẩm** hay **một lần cập nhật trạng thái**? Nếu tệp chứa nhiều phiên bản của cùng đơn, khóa đơn không được mặc định là duy nhất trong tệp. Với mỗi nguồn phải xác định:

1. ID định danh hàng hoặc đối tượng ở phạm vi nào?
2. Hai hàng cùng ID là lỗi trùng, hai phiên bản hợp lệ hay hai sự kiện riêng?
3. Khi tải lại, giữ bản cũ, cập nhật bản mới hay lưu lịch sử?
4. Có cần khóa tenant, nguồn, ngày hiệu lực hoặc version không?

Các quyết định này không được giao phó cho câu lệnh `COPY` hoặc `LOAD DATA`: công cụ bulk thường chỉ **đọc và ghi hàng**, không suy luận quy tắc nghiệp vụ.

## 3. Encoding: dữ liệu đúng bắt đầu từ đúng bytes

**Encoding** là cách biểu diễn ký tự thành bytes. UTF-8 hiện là lựa chọn phổ biến cho trao đổi dữ liệu đa ngôn ngữ: có thể biểu diễn tiếng Việt, tiếng Nhật, emoji và nhiều hệ chữ trong một tệp.

Ví dụ, chuỗi:

```text
Nguyễn Ánh – Đơn hàng số 01
```

có thể được lưu bằng UTF-8. Nếu chương trình đọc các bytes UTF-8 bằng một bảng mã khác như Windows-1252, ký tự tiếng Việt có thể xuất hiện thành những đoạn khó đọc (*mojibake*). Sau khi dữ liệu đã bị giải mã sai rồi **ghi lại** dưới dạng mới, việc sửa có thể không đơn giản là đổi encoding của tệp.

### 3.1. Phân biệt ba lớp encoding

```text
Tệp nguồn trên đĩa
   --(file encoding)-->
Client / công cụ nhập / parser
   --(client-server encoding/protocol)-->
Database / cột lưu trữ
```

Tùy công cụ, có thể còn thêm lớp transport hoặc nén. Những điều cần kiểm tra:

- Bytes tệp gốc có thật là UTF-8 không?
- Công cụ nhập được báo đúng encoding nguồn chưa?
- Kết nối client–server dùng encoding gì?
- Database có hỗ trợ đầy đủ ký tự cần lưu không?
- Có bước xử lý nào vô tình chuyển ký tự không thể biểu diễn thành `?` hoặc ký tự thay thế `�`?

**Khai báo `UTF8` cho một tệp vốn đã bị hỏng encoding không tự sửa tệp.** Trước khi load phải xác định encoding thật hoặc chuyển mã bằng công cụ tin cậy, đồng thời giữ bản gốc để có thể đối soát.

### 3.2. UTF-8 BOM và tên cột đầu tiên

UTF-8 có thể có ba bytes mở đầu `EF BB BF`, gọi là **BOM**. Một số công cụ nhận ra và bỏ BOM, số khác không. Nếu parser không loại BOM, tên cột đầu tiên tưởng là `order_id` thực tế có thể có một ký tự vô hình đứng trước.

**Không mặc định mọi công cụ sẽ tự bỏ BOM.** Hãy thử tệp mẫu có BOM bằng đúng công cụ/version đích hoặc chuẩn hóa đầu vào về UTF-8 không BOM theo hợp đồng. Nếu cần loại BOM, làm trên bytes hoặc bằng thư viện hiểu encoding, không dùng thao tác xóa tùy tiện có thể làm mất ký tự hợp lệ.

### 3.3. Dấu tiếng Việt và chuẩn hóa Unicode

Hai chuỗi trông giống nhau có thể dùng cách biểu diễn Unicode khác nhau, ví dụ ký tự đã dựng sẵn và ký tự gốc cộng dấu kết hợp. Điều này có thể ảnh hưởng:

- So sánh, dedup và tạo khóa;
- Kích thước chuỗi tính theo bytes/ký tự;
- Tìm kiếm, sắp xếp và collation.

Nếu mã định danh hoặc đối chiếu văn bản yêu cầu một chuẩn chung (như NFC), hãy **quy định bước chuẩn hóa riêng** và thử tác động lên khóa. Đừng mặc định đổi collation hoặc encoding sẽ hợp nhất mọi chuỗi Unicode tương đương.

### 3.4. Không nhầm encoding với collation

Encoding quyết định **cách lưu/đọc ký tự**; collation quyết định **quy tắc so sánh/sắp xếp** của chuỗi trong những ngữ cảnh nhất định. Một tệp UTF-8 hoàn toàn hợp lệ vẫn có thể cho kết quả so sánh tên/ID khác nhau khi vào hai database có collation khác nhau. Đây là hai vấn đề riêng.

## 4. CSV không chỉ là “các cột ngăn bởi dấu phẩy”

Trong CSV, một trường có thể chứa dấu phân tách, dấu nháy hoặc ký tự xuống dòng. Bộ parser cần biết:

- **Delimiter**: ký tự phân tách các trường, thường là `,`; một số tệp dùng `;` hoặc tab.
- **Quote**: ký tự bao một trường, thường là `"`.
- **Escape**: cách biểu diễn dấu quote hoặc ký tự đặc biệt trong trường.
- **Record separator**: ký tự/ký tự đôi kết thúc một bản ghi ngoài vùng bao quote.
- **Header**: dòng tên cột có phải dữ liệu hay không.
- **NULL marker**: cách thể hiện giá trị SQL NULL.

Ví dụ CSV chuẩn theo cách nháy đôi dấu nháy:

```csv
id,name,note
1,"Trần, Bình","Khách nói ""giao lúc 8 giờ"""
2,An,"Ghi chú nhiều dòng:
đã xác nhận với khách"
```

Ở hàng 1:

- Trường tên là `Trần, Bình`, **không phải hai cột**.
- Trường note chứa một cặp dấu nháy thật xung quanh câu nói.

Ở hàng 2, note chứa **xuống dòng nằm trong dấu bao quote**, vì vậy bản ghi CSV có thể trải dài qua **hai dòng vật lý trong tệp**.

### 4.1. Số dòng vật lý không nhất thiết bằng số record

Do trường CSV có thể chứa newline, `wc -l` hoặc đếm `\n` không luôn bằng số hàng dữ liệu. Ngoài ra, tệp có header hoặc dòng rỗng. Nếu cần đối soát chắc chắn, dùng parser CSV tương ứng, đếm số **record đã phân tích**, và đối chiếu với số hàng staging.

### 4.2. Dấu phẩy, dấu chấm phẩy và dữ liệu bảng tính

Một ứng dụng bảng tính ở một locale có thể xuất CSV dùng `;`, đặc biệt khi dấu phẩy được dùng làm dấu thập phân. Không suy luận delimiter chỉ từ phần mở rộng `.csv`. Ví dụ:

```text
id;name;amount
1;"Trần, Bình";125000,50
```

Trong tệp này, delimiter là `;`, còn `125000,50` dùng dấu phẩy thập phân. Nếu bảng đích yêu cầu NUMERIC theo dấu chấm, phải **chuẩn hóa có kiểm soát** ở staging; không chỉ thay mọi dấu phẩy bằng dấu chấm vì dấu phẩy cũng có thể xuất hiện trong nội dung văn bản.

### 4.3. Dữ liệu `NULL`, chuỗi rỗng và marker

Ba tình huống có thể khác nhau:

| Nội dung nguồn | Có thể muốn biểu diễn | Phải xác nhận điều gì? |
| --- | --- | --- |
| Không có ký tự giữa hai dấu phân tách | Chuỗi rỗng hoặc NULL | Cấu hình parser |
| `""` | Chuỗi rỗng có quote | Quy tắc quote và NULL của công cụ |
| `__NULL__` | NULL được đánh dấu rõ | Marker này có thể là chuỗi thật không? |

Trong PostgreSQL CSV, có thể cấu hình:

```sql
NULL '__NULL__'
```

để giá trị **không bao quote** đúng bằng `__NULL__` được hiểu là SQL NULL. Nếu dữ liệu thật cần chuỗi văn bản `__NULL__`, có thể bao quote tùy quy tắc CSV của PostgreSQL để phân biệt. Không sử dụng marker dễ va chạm với giá trị hợp lệ nếu chưa có cách escape/quote rõ.

## 5. PostgreSQL thực hành: nhập nguyên bản vào bảng staging

Để chạy ví dụ mà **không cần tải thêm tệp bên ngoài**, ta dùng `COPY ... FROM STDIN` trong một phiên `psql`, truyền trực tiếp các record CSV phía dưới câu SQL. Cách viết này thích hợp trong script `.sql` chạy bằng `psql -f ...`; với công cụ SQL GUI, thao tác `COPY FROM STDIN` có thể cần tính năng stream riêng và không nhất thiết hiểu dấu kết thúc `\.` như psql.

### 5.1. Tạo bảng staging tất cả cột dạng TEXT

```sql
CREATE TEMP TABLE demo_bulk_raw (
    source_order_id TEXT,
    customer_name TEXT,
    order_day_text TEXT,
    amount_text TEXT,
    note_text TEXT
);
```

**Vì sao dùng TEXT ở staging?** Bảng tạm này lưu dữ liệu gần với cách nguồn gửi tới, để có thể quan sát giá trị tiền sai mà không bắt toàn bộ lô phải chuyển ngay sang NUMERIC. Sau đó ta sẽ phân loại record hợp lệ và record cần xử lý riêng.

Staging TEXT không có nghĩa có thể bỏ qua hoàn toàn cú pháp CSV: một hàng bị thiếu số cột, quote không đóng hoặc encoding không hợp lệ vẫn có thể khiến **parser CSV** báo lỗi trước khi tạo được hàng staging.

### 5.2. Nạp dữ liệu qua STDIN

Chạy nguyên đoạn sau **trong `psql`**; lệnh `\.` là dấu kết thúc dữ liệu COPY khi truyền qua giao thức nhập của psql, không phải một record CSV:

```sql
COPY demo_bulk_raw (
    source_order_id,
    customer_name,
    order_day_text,
    amount_text,
    note_text
)
FROM STDIN
WITH (
    FORMAT csv,
    HEADER true,
    DELIMITER ',',
    QUOTE '"',
    ESCAPE '"',
    NULL '__NULL__',
    ENCODING 'UTF8'
);
source_order_id,customer_name,order_day_text,amount_text,note_text
WEB-001,Nguyễn An,2026-10-05,125000.50,"Giao trước 18:00, gọi lại"
WEB-002,"Trần, Bình",2026-10-05,0,""
WEB-003,Lê Chi,2026-10-06,45000.00,__NULL__
WEB-004,Phạm Dũng,2026-10-06,khong_hop_le,Kiểm tra dữ liệu
WEB-005,Mai Em,2026-10-07,120000.00,"Ghi chú có ""dấu nháy"""
\.
```

Đặc điểm của năm hàng:

1. `WEB-001` có tên tiếng Việt và dấu phẩy trong note được bao quote.
2. `WEB-002` có dấu phẩy bên trong tên `"Trần, Bình"`; `note_text = ''` (chuỗi rỗng) vì trường `""`.
3. `WEB-003` có note **NULL** do marker `__NULL__` không quote.
4. `WEB-004` có amount **không hợp lệ**: `khong_hop_le`; nhập vào TEXT vẫn giữ được để kiểm tra.
5. `WEB-005` có dấu quote thật trong ghi chú nhờ cú pháp `""`.

Số hàng staging:

```sql
SELECT COUNT(*) AS raw_rows
FROM demo_bulk_raw;
-- 5
```

Quan sát trường đặc biệt:

```sql
SELECT
    source_order_id,
    customer_name,
    amount_text,
    note_text,
    note_text IS NULL AS note_is_null
FROM demo_bulk_raw
ORDER BY source_order_id;
```

Ở `WEB-002`, note là chuỗi rỗng **không phải NULL**; ở `WEB-003`, note là NULL. Kết quả có thể hiển thị giống nhau ở một số công cụ GUI, vì vậy cần cột `IS NULL` để phân biệt.

### 5.3. Những gì COPY đã và chưa làm

`COPY` đã đọc CSV theo cấu hình delimiter/quote/NULL và tạo **5 hàng TEXT**. Nó **chưa quyết định**:

- `khong_hop_le` có phải một số tiền hay không.
- `source_order_id` có bị nạp trùng từ lô trước hay không.
- Một ngày có hợp lệ theo lịch hay không.
- Một đơn ở trạng thái gì nếu tệp không gửi trạng thái.
- Có nên ghi đè một đơn đã tồn tại trong bảng đích.

Đó là lý do việc **load thành công** không đồng nghĩa **dữ liệu đã sẵn sàng cho nghiệp vụ**.

## 6. COPY FROM file và \copy khác nhau thế nào?

Trong PostgreSQL có hai cách thường bị nhầm:

```sql
COPY target_table FROM '/path/on/server/data.csv'
WITH (FORMAT csv, HEADER true);
```

và lệnh meta của **psql**:

```text
\copy target_table FROM './data.csv' WITH (FORMAT csv, HEADER true)
```

| Đặc điểm | SQL `COPY FROM 'file'` | psql `\copy ... FROM 'file'` |
| --- | --- | --- |
| Ai mở tệp? | **Tiến trình máy chủ PostgreSQL** | **Tiến trình psql/client** |
| Đường dẫn tính từ đâu? | Hệ thống file mà server nhìn thấy | Hệ thống file nơi psql đang chạy |
| Quyền file | Tài khoản hệ điều hành của server và quyền SQL phù hợp | Quyền đọc file của người chạy psql; DB quyền INSERT/COPY tương ứng |
| Quyền PostgreSQL đặc biệt | Đọc/ghi file server bị hạn chế theo role/quyền phù hợp | Không cần quyền đọc file ở server vì client stream dữ liệu |
| Dùng trong SQL gửi từ driver | `COPY` là câu lệnh SQL nhưng cần API stream phù hợp với STDIN | `\copy` **không phải SQL**, chỉ là lệnh psql |
| Rủi ro thường gặp | Nhầm path máy cá nhân là path trên server | Chạy psql trong container khác chỗ chứa tệp |

### 6.1. Ví dụ \copy từ máy chạy psql

Nếu đã có tệp CSV đúng cấu trúc:

```text
\copy demo_bulk_raw (source_order_id, customer_name, order_day_text, amount_text, note_text) FROM './orders.csv' WITH (FORMAT csv, HEADER true, NULL '__NULL__', ENCODING 'UTF8')
```

Lệnh `\copy` chạy trong **psql**, không chạy nguyên dạng đó trong một ứng dụng SQL chỉ hỗ trợ câu SQL. Một số công cụ GUI có tính năng import riêng và không hỗ trợ cú pháp backslash.

### 6.2. Quyền cho COPY phía server

`COPY FROM '/var/lib/postgresql/import/orders.csv'` yêu cầu file thực sự tồn tại **trên máy/chỗ lưu mà server truy cập được**, và tiến trình server có quyền đọc file. PostgreSQL còn giới hạn việc đọc file phía server theo vai trò có quyền đặc biệt phù hợp (ví dụ role được cấp quyền đọc server files hoặc quyền quản trị), vì có rủi ro truy cập tài nguyên trên máy DB.

Không cấp quyền file/server quá rộng chỉ để một người dùng thông thường nhập CSV. Với người dùng ứng dụng, `\copy` hoặc **COPY FROM STDIN** qua API client thường có mô hình quyền dễ kiểm soát hơn.

### 6.3. Không dùng COPY FROM PROGRAM tùy tiện

PostgreSQL có thể thực thi lệnh trên **máy chủ database** trong những chế độ COPY đặc biệt dành cho quản trị viên có quyền tương ứng. Đây là khả năng nhạy cảm về bảo mật: không xây dựng chức năng upload dữ liệu bằng cách ghép chuỗi lệnh shell người dùng vào `COPY FROM PROGRAM`. Với dữ liệu bên ngoài, chọn kênh upload/stream được phân quyền và kiểm tra trước.

## 7. Nhập từ file: chọn đúng delimiter, header và định dạng

Cú pháp COPY thường dùng:

```sql
COPY demo_bulk_raw (
    source_order_id,
    customer_name,
    order_day_text,
    amount_text,
    note_text
)
FROM '/var/lib/postgresql/import/orders.csv'
WITH (
    FORMAT csv,
    HEADER true,
    DELIMITER ',',
    QUOTE '"',
    ESCAPE '"',
    NULL '__NULL__',
    ENCODING 'UTF8'
);
```

Đường dẫn trên **chỉ là ví dụ cho máy chủ PostgreSQL có tệp tương ứng**; câu SQL không chạy thành công nếu server không có file hoặc thiếu quyền. Trong dự án thực tế, path và quyền phải theo cấu hình triển khai.

### 7.1. Header không tự bảo đảm khớp tên cột

Ở chế độ thông dụng `HEADER true`, công cụ **bỏ qua hàng header** khi đọc dữ liệu; không nên suy luận rằng nó tự ánh xạ cột theo tên file hoặc xác nhận đúng thứ tự. Dữ liệu được nạp theo **vị trí danh sách cột khai báo**. Nếu nhà cung cấp đổi vị trí `amount` và `order_day` nhưng cả hai đang là TEXT ở staging, parser vẫn có thể nhập thành công nhưng ý nghĩa bị đảo.

Một số phiên bản/công cụ có tùy chọn kiểm tra header riêng; hãy xác minh hỗ trợ ở DBMS/version sử dụng. Đối với pipeline quan trọng, **so sánh schema/header với hợp đồng đầu vào trước khi load**.

### 7.2. Delimiter phải phù hợp với dữ liệu

Với tệp TSV dùng tab, PostgreSQL có thể dùng:

```sql
COPY demo_bulk_raw
FROM '/var/lib/postgresql/import/orders.tsv'
WITH (
    FORMAT csv,
    HEADER true,
    DELIMITER E'\t',
    QUOTE '"',
    ENCODING 'UTF8'
);
```

Đây là **CSV parser với delimiter là tab**, có xử lý trường bao quote. Nó không đồng nhất với `FORMAT text` của PostgreSQL, vốn có **quy tắc escape và NULL riêng**. Đừng nhầm “file có tab” với “phải dùng COPY text”; hãy kiểm tra chính xác cú pháp file.

### 7.3. CSV và TSV vẫn có thể chứa newline trong trường

Một trường note bao quote có thể chứa newline thật. Công cụ theo đúng dialect CSV phải hiểu đó là **một trường** trong một record, không phải bản ghi mới. Một trình xử lý trước dùng thao tác `split('\n')` rồi `split(',')` dễ làm hỏng dữ liệu. Nếu cần tiền xử lý, dùng thư viện CSV có cấu hình delimiter/quote/encoding trùng hợp đồng.

### 7.4. Tránh tự nhận diện delimiter khi cần tính đúng

Tự đoán giữa `,`, `;`, `\t` bằng vài dòng đầu có thể sai nếu trường văn bản chứa các ký tự ấy. Với dữ liệu vận hành, nên **cấu hình theo nguồn và phiên bản schema**, ghi nhận thay đổi chính thức, và đưa tệp khác định dạng vào luồng lỗi thay vì nhập lẫn.

## 8. Kiểm tra staging trước khi chuyển sang bảng đích

Bảng raw cho phép ta **quan sát và phân loại dữ liệu chưa hợp lệ**. Ví dụ lượng tiền được yêu cầu là số không âm, tối đa 12 chữ số trước dấu chấm, tối đa 2 chữ số phần thập phân:

```sql
SELECT
    source_order_id,
    amount_text
FROM demo_bulk_raw
WHERE amount_text IS NULL
   OR amount_text !~ '^[0-9]{1,12}(\.[0-9]{1,2})?$'
ORDER BY source_order_id;
```

Kết quả phát hiện `WEB-004` có `khong_hop_le`. Regex này là **quy tắc định dạng số cho ví dụ**, không phải bộ parser tiền hoàn chỉnh của mọi quốc gia; nó không cho phép dấu âm, dấu phân nhóm nghìn, số dạng mũ hoặc hơn hai chữ số thập phân. Cần quy tắc định dạng riêng nếu nguồn có những giá trị đó.

### 8.1. Đừng chỉ “thử CAST rồi mong thành NULL”

Trong PostgreSQL, câu:

```sql
SELECT 'khong_hop_le'::NUMERIC;
```

**báo lỗi**, không tự trả NULL. Nếu câu `INSERT INTO target SELECT amount_text::NUMERIC FROM staging` gặp record ấy, statement có thể thất bại. Một số DBMS có hàm **TRY_CAST/SAFE_CAST** nhưng PostgreSQL không cung cấp đúng dạng hàm ấy mặc định trong mọi phiên bản.

Vì vậy thường cần:

1. Kiểm tra những mẫu dữ liệu không hợp lệ.
2. Cách ly record lỗi trước chuyển kiểu.
3. Chuyển kiểu trên tập được xác nhận hợp lệ; với ngày/giờ, kiểm tra cả tính hợp lệ **theo lịch**, không chỉ regex hình thức.
4. Ghi nguyên văn record lỗi cùng lý do và batch ID.

### 8.2. Ngày theo ISO 8601 nên được chuẩn hóa

Chuỗi `2026-10-05` rõ ràng hơn `05/10/26` hoặc `10/05/26` trong trao đổi nhiều locale. Tuy nhiên, kiểm tra regex:

```sql
order_day_text ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
```

chỉ xác minh **hình dạng**, không xác minh ngày có thật: `2026-02-30` cũng khớp regex nhưng không phải ngày hợp lệ. Trên dữ liệu lớn, nên có quy trình parse ngày an toàn hoặc kiểm tra tại tầng ứng dụng/ETL trước bước CAST; không coi regex là chứng minh có thể ép sang DATE.

### 8.3. Khóa trống, khoảng trắng và bản ghi lặp

```sql
SELECT source_order_id, COUNT(*) AS occurrences
FROM demo_bulk_raw
GROUP BY source_order_id
HAVING COUNT(*) > 1;
```

Nếu cùng ID xuất hiện nhiều lần trong một lô, cần xác định:

- Bản ghi bị gửi lặp cần bỏ?
- Hai phiên bản của cùng đơn cần lấy bản mới nhất?
- Có phải ID chỉ duy nhất trong một tenant/nguồn?
- Có lịch sử sự kiện hợp lệ mà không nên gộp?

Đừng tự `DISTINCT` toàn hàng để xử lý trùng theo ID. Hai phiên bản cùng ID nhưng khác số tiền vẫn **không trùng toàn hàng**; hai giao dịch độc lập cùng số tiền thì lại **không được gộp**.

## 9. Ghi vào bảng đích có kiểu và ràng buộc

Tạo bảng tạm đích có kiểu nghiệp vụ:

```sql
CREATE TEMP TABLE demo_bulk_orders (
    source_order_id TEXT PRIMARY KEY,
    customer_name TEXT NOT NULL,
    order_day DATE NOT NULL,
    amount NUMERIC(14, 2) NOT NULL CHECK (amount >= 0),
    note TEXT
);
```

Bảng này khác staging:

- `source_order_id` là khóa chính.
- `order_day` là DATE, không phải chuỗi tùy ý.
- `amount` là NUMERIC(14,2), không phải TEXT.
- `customer_name` và số tiền không được NULL.

### 9.1. Đưa record không hợp lệ vào bảng lỗi

Trong ví dụ, một bảng lỗi đơn giản có thể tạo từ các trường sai:

```sql
CREATE TEMP TABLE demo_bulk_rejects AS
SELECT
    source_order_id,
    customer_name,
    order_day_text,
    amount_text,
    note_text,
    'INVALID_AMOUNT'::TEXT AS reason
FROM demo_bulk_raw
WHERE amount_text IS NULL
   OR amount_text !~ '^[0-9]{1,12}(\.[0-9]{1,2})?$';
```

Kết quả bảng reject có record `WEB-004`. Trong pipeline thật nên có `batch_id`, `source_filename`, `source_record_number` (nếu parser cung cấp), `ingested_at`, `error_code`, `error_details` và dữ liệu raw hoặc tham chiếu tới bản gốc. Đừng xóa hàng lỗi trước khi có quy trình sửa hoặc thông báo cho bên cung cấp.

### 9.2. Chuyển bốn hàng hợp lệ trong bộ mẫu

Với **đúng dữ liệu ví dụ** ở mục 5, mọi `order_day_text` đều là ngày ISO hợp lệ và customer_name không NULL. Ta có thể viết:

```sql
INSERT INTO demo_bulk_orders (
    source_order_id,
    customer_name,
    order_day,
    amount,
    note
)
SELECT
    source_order_id,
    customer_name,
    order_day_text::DATE,
    amount_text::NUMERIC(14, 2),
    note_text
FROM demo_bulk_raw
WHERE source_order_id IS NOT NULL
  AND BTRIM(source_order_id) <> ''
  AND customer_name IS NOT NULL
  AND BTRIM(customer_name) <> ''
  AND order_day_text IS NOT NULL
  AND order_day_text ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
  AND amount_text IS NOT NULL
  AND amount_text ~ '^[0-9]{1,12}(\.[0-9]{1,2})?$'
ON CONFLICT (source_order_id) DO NOTHING;
```

Với bộ mẫu, **4 hàng hợp lệ** được ghi; `WEB-004` không được ghi. `ON CONFLICT ... DO NOTHING` minh họa chính sách **bỏ qua đơn đã có cùng khóa** khi nhập lại, không nhất thiết là chính sách đúng cho mọi doanh nghiệp.

Kiểm tra:

```sql
SELECT COUNT(*) AS accepted_rows
FROM demo_bulk_orders;
-- 4

SELECT COUNT(*) AS rejected_rows
FROM demo_bulk_rejects;
-- 1

SELECT source_order_id, customer_name, order_day, amount, note
FROM demo_bulk_orders
ORDER BY source_order_id;
```

**Giới hạn cố ý của ví dụ:** regex ngày chưa chứng minh ngày hợp lệ; dữ liệu thực cần bước validate ngày an toàn trước CAST. Đồng thời, bảng reject ví dụ mới phát hiện lỗi amount; pipeline sản xuất phải định nghĩa và thu thập **tất cả loại lỗi**, gồm ID trống, ngày sai, trùng khóa và lỗi FK. Chỉ được tuyên bố lô “đối soát đủ” khi mọi hàng nguồn có một trạng thái rõ ràng.

### 9.3. `ON CONFLICT DO NOTHING` không phải sửa trùng phổ quát

Nếu một file cập nhật amount của đơn cũ, `DO NOTHING` giữ giá trị đang có và **bỏ cập nhật mới**. Nếu nghiệp vụ muốn cập nhật, có thể dùng `ON CONFLICT ... DO UPDATE`, nhưng cần:

- Chọn record nào thắng (version, updated_at, nguồn ưu tiên).
- Không ghi đè dữ liệu mới bằng file cũ.
- Kiểm tra một lô có nhiều dòng cùng khóa trước khi upsert.
- Ghi nhận audit các giá trị đã thay đổi.

Với bảng ledger/sổ cái, thường **không được tùy tiện sửa amount lịch sử**; cần chính sách ghi bút toán điều chỉnh. SQL có thể cho phép UPDATE nhưng nghiệp vụ có thể cấm.

## 10. Đối soát số hàng: nguồn, nhận, chấp nhận, từ chối

Một hệ thống nhập đáng tin cần trả lời:

```text
Bao nhiêu record trong tệp?
        |
        v
Bao nhiêu record parser đã đọc vào staging?
        |
        +-- Bao nhiêu hợp lệ?
        +-- Bao nhiêu bị từ chối?
        +-- Bao nhiêu bị bỏ vì trùng đã tồn tại?
        +-- Bao nhiêu được cập nhật/thay thế?
```

Với bộ dữ liệu mẫu:

| Chỉ số | Giá trị | Ý nghĩa |
| --- | ---: | --- |
| Record CSV (không tính header) | 5 | Dữ liệu do nguồn gửi |
| Hàng staging | 5 | Parser CSV đã đọc đủ |
| Hàng lỗi amount | 1 | `WEB-004` |
| Hàng đã chấp nhận trong lần nạp đầu | 4 | Sau validate và chuyển kiểu |
| Hàng bảng đích sau lần đầu | 4 | Chưa có dữ liệu cũ |

Nếu chạy lại lệnh `INSERT ... ON CONFLICT DO NOTHING`, bảng đích **vẫn có 4 hàng** chứ không tăng lên 8, nhưng **số hàng được INSERT mới** lần chạy lại là 0. Do đó, **đếm tổng hàng sau load** và **đếm hàng được chèn trong batch** là hai thước đo khác nhau.

### 10.1. Mã lô và khả năng truy vết

Với dữ liệu vận hành, nên có một bảng quản lý lô như:

```text
import_batches:
  batch_id
  source_system
  source_filename
  file_checksum
  file_size_bytes
  format_version
  received_at
  started_at
  finished_at
  source_record_count
  staged_record_count
  accepted_count
  rejected_count
  skipped_duplicate_count
  status
  error_details
```

Đây là mô hình khái niệm, không bắt buộc có đúng tên cột ấy. Checksum giúp nhận diện **tệp giống hệt nhau**, nhưng hai tệp khác bytes vẫn có thể chứa cùng giao dịch, và một tệp giống hệt nhau vẫn cần biết chính sách replay. Vì vậy, checksum **không thay thế khóa nghiệp vụ**.

### 10.2. Không bỏ qua cảnh báo

Một số công cụ có chế độ **bỏ qua hàng lỗi rồi tiếp tục**. Nếu chỉ đọc thông báo “load succeeded”, người vận hành có thể không nhận ra 2% hàng đã bị bỏ. Nên giám sát **số record lỗi và ngưỡng chấp nhận**, lưu nguyên nhân và xác định khi nào cần chặn toàn bộ lô.

## 11. Transaction, batch và khả năng nạp lại

Một câu lệnh bulk có thể gặp:

- CSV lỗi giữa file;
- Vi phạm kiểu/constraint;
- Mất kết nối;
- Hết không gian;
- Deadlock hoặc xung đột khóa;
- Lỗi ở bước chuyển staging sang bảng đích.

Vì vậy cần một **ranh giới giao dịch** và **chính sách retry** được thiết kế rõ ràng.

### 11.1. PostgreSQL COPY trong transaction

Ví dụ cấu trúc ý tưởng:

```sql
BEGIN;

-- 1. Nạp staging bằng COPY FROM STDIN hoặc cơ chế thích hợp.
-- 2. Ghi nhận reject/kiểm tra ngưỡng.
-- 3. INSERT/UPSERT những hàng hợp lệ vào bảng đích.
-- 4. Cập nhật trạng thái lô.

COMMIT;
```

Trong PostgreSQL, COPY tham gia transaction bình thường. Nếu câu COPY hoặc bước ghi đích thất bại, có thể `ROLLBACK` để tránh trạng thái đích nửa vời, với điều kiện các thao tác thuộc cùng transaction và không có side effect bên ngoài bị bỏ quên.

Nhưng đối với hàng triệu dòng, một transaction quá lớn có thể tạo WAL, lock, chi phí rollback hoặc tác động đến tài nguyên. Cần cân bằng **tính nguyên tử của lô** với kích thước batch và hạ tầng.

### 11.2. Dữ liệu lỗi trong PostgreSQL COPY

Trong chế độ chuẩn khi COPY trực tiếp vào bảng kiểu DATE/NUMERIC, một hàng sai có thể khiến cả statement bị lỗi. Nếu COPY giữa chừng tạo nhiều tuple trước khi lỗi, các tuple bị rollback có thể vẫn chiếm không gian vật lý tạm thời cho tới khi được dọn dẹp theo cơ chế PostgreSQL. Vì vậy:

- Không coi COPY trực tiếp vào bảng đích là lựa chọn duy nhất.
- Có thể dùng **TEXT staging** và validate trước chuyển kiểu.
- Đối với lô lớn, kiểm tra khả năng quan sát lỗi và quản lý dung lượng.
- Không suy luận rằng “COPY thất bại” luôn không có tác động tài nguyên.

Một số phiên bản PostgreSQL mới bổ sung tùy chọn xử lý lỗi cho COPY; hành vi và phạm vi hỗ trợ cần được xác nhận theo **phiên bản server**, không trộn cú pháp từ tài liệu bản mới vào cluster cũ.

### 11.3. Idempotency: nạp lại không được nhân dữ liệu

Một pipeline **idempotent** khi nhập lại đúng một lô không gây thay đổi ngoài ý muốn, ví dụ không tạo thêm các bản sao giao dịch hợp lệ. Các chiến lược:

- Ràng buộc khóa duy nhất và `ON CONFLICT DO NOTHING` nếu dữ liệu cũ phải được giữ.
- `ON CONFLICT DO UPDATE`/`MERGE` nếu muốn cập nhật theo version xác định.
- Xóa và nạp lại **một partition/phạm vi rõ ràng** trong transaction nếu dữ liệu được quản lý theo snapshot.
- Ghi bảng trung gian mới rồi đổi con trỏ/bảng đích một cách có kiểm soát cho mô hình full refresh.

Chỉ dựa vào `batch_id` để bỏ tệp đã nạp không đủ nếu **cùng giao dịch được gửi trong một batch khác**. Cần khóa nghiệp vụ và quy tắc trùng có ý nghĩa.

## 12. Nhập trực tiếp bảng đích hay dùng staging?

| Tiêu chí | Nhập trực tiếp bảng đích | Nhập staging rồi chuyển |
| --- | --- | --- |
| Nguồn đã sạch, schema ổn định | Có thể đơn giản hơn | Thêm bước |
| Nguồn ngoài không tin cậy | Lỗi kiểu/constraint có thể dừng load | Có nơi giữ record lỗi |
| Cần thống kê lỗi theo từng hàng | Khó tùy công cụ | Dễ xây bảng reject/audit |
| Cần dedup, version và upsert | Có thể phải kết hợp nhiều bước | Tách rõ raw và business rules |
| Cần kiểm soát kiểu/ngày/đơn vị | Dễ nhập sai nếu cấu hình | Chuyển đổi rõ ràng |
| Cần hiệu năng tuyệt đối | Ít bước hơn trong trường hợp sạch | Tốn thêm I/O nhưng đáng giá nếu tăng tính đúng |

**Staging không nhất thiết phải là TEMP TABLE.** Trong ví dụ dùng bảng tạm để tự chứa, nhưng trong hệ thật có thể cần **bảng staging bền vững** với `batch_id` và log lỗi để kiểm toán, xử lý bất đồng bộ hoặc tiếp tục sau sự cố.

Không nên để nhiều lô cùng ghi vào một staging chung mà không có `batch_id` hoặc cơ chế tách biệt. Một lô lỗi có thể làm ảnh hưởng lô khác nếu thiết kế không rõ.

## 13. MySQL/MariaDB: LOAD DATA INFILE

Trong MySQL, phương tiện nhập hàng loạt phổ biến là `LOAD DATA [LOCAL] INFILE`.

Ví dụ **MySQL 8.x**, giả sử bảng `stg_orders` có năm cột văn bản tương ứng:

```sql
LOAD DATA LOCAL INFILE '/path/on/client/orders.csv'
INTO TABLE stg_orders
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
       OPTIONALLY ENCLOSED BY '"'
       ESCAPED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(
    source_order_id,
    customer_name,
    order_day_text,
    amount_text,
    note_text
);
```

**Đây là ví dụ phụ thuộc cách escape của tệp.** Nhiều CSV dùng dấu quote lặp `""`, nhưng MySQL có các tùy chọn `ENCLOSED BY` và `ESCAPED BY` có quy tắc riêng. Cần thử file mẫu chứa dấu phẩy, dấu quote, xuống dòng và NULL trước khi dùng trên tệp sản xuất. Không mặc định cú pháp escape của PostgreSQL và MySQL giống hệt nhau.

### 13.1. LOCAL và non-LOCAL

| Dạng | Ai truy cập tệp? | Ghi chú |
| --- | --- | --- |
| `LOAD DATA INFILE '...'` | Máy chủ MySQL | Chịu quyền đọc file phía server, ràng buộc `secure_file_priv` và quyền phù hợp |
| `LOAD DATA LOCAL INFILE '...'` | Client mở tệp rồi gửi nội dung đến server | Cần tính năng LOCAL được cho phép ở cả client và server; có rủi ro nếu bật rộng |

`LOCAL INFILE` có các cân nhắc bảo mật riêng. Không tự bật `local_infile` trên hệ thống production chỉ để xử lý một tệp nếu chính sách vận hành đang cấm; cần xác minh phiên bản driver, cơ chế TLS, cấu hình và quyền.

### 13.2. Đặc biệt chú ý encoding khi dùng LOAD DATA

MySQL có tùy chọn:

```sql
CHARACTER SET utf8mb4
```

để nói rõ mã hóa tệp đầu vào. Không xem `SET NAMES utf8mb4` là biện pháp thay thế hoàn toàn cho việc khai báo đúng encoding nguồn khi dùng LOAD DATA. `utf8mb4` cần cho đầy đủ Unicode trong những hệ MySQL dùng các character set tương ứng; `utf8` có thể mang nghĩa lịch sử khác theo phiên bản.

### 13.3. Dấu dòng Windows

Tệp Windows thường dùng `CRLF` (`\r\n`). Nếu cấu hình:

```sql
LINES TERMINATED BY '\n'
```

nhưng công cụ không loại phần `\r` còn lại theo cách kỳ vọng, trường cuối có thể chứa ký tự carriage return. Với tệp dùng CRLF một cách nhất quán, cân nhắc:

```sql
LINES TERMINATED BY '\r\n'
```

và thử đúng tệp thật. Đối với CSV có newline **trong trường quote**, parser phải nhận biết quy tắc bao quote; đừng tách dòng trước bằng script đơn giản.

### 13.4. Khi cần chuyển đổi bằng biến người dùng

MySQL cho phép nạp trường vào user variables rồi chuyển đổi bằng `SET`, ví dụ mẫu:

```sql
LOAD DATA LOCAL INFILE '/path/on/client/orders.csv'
INTO TABLE stg_orders
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
       OPTIONALLY ENCLOSED BY '"'
       ESCAPED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(@source_id, @customer_name, @order_day, @amount, @note)
SET
    source_order_id = @source_id,
    customer_name = @customer_name,
    order_day_text = @order_day,
    amount_text = @amount,
    note_text = @note;
```

Đoạn này chỉ minh họa ánh xạ các trường text; có thể thêm bước chuẩn hóa phù hợp. Trong nhập tiền/ngày phức tạp, dùng staging giúp phát hiện record lỗi thay vì dựa vào chuyển kiểu ngầm trong LOAD DATA.

**Lưu ý:** MariaDB phát triển độc lập với MySQL và có thể có các khác biệt về cú pháp/hành vi phiên bản. Luôn kiểm tra engine và release thực tế.

## 14. SQL Server: BULK INSERT, bcp và OPENROWSET(BULK)

Trong Microsoft SQL Server, các công cụ phổ biến gồm:

- `BULK INSERT`: câu lệnh T-SQL tải tệp mà **server/instance** có thể truy cập.
- `bcp`: tiện ích dòng lệnh thực hiện bulk copy giữa tệp và SQL Server từ phía client.
- `OPENROWSET(BULK ...)`: truy cập dữ liệu nguồn hàng loạt trong một số trường hợp và tùy cấu hình.
- Các phương tiện tích hợp như SSIS, Azure Data Factory hoặc dịch vụ import/ETL khác.

### 14.1. BULK INSERT theo CSV

Mẫu SQL Server 2017+ khi tính năng `FORMAT='CSV'` được hỗ trợ:

```sql
BULK INSERT dbo.import_orders_stage
FROM 'C:\imports\orders.csv'
WITH (
    FORMAT = 'CSV',
    FIRSTROW = 2,
    FIELDTERMINATOR = ',',
    FIELDQUOTE = '"',
    ROWTERMINATOR = '0x0a',
    CODEPAGE = '65001',
    TABLOCK
);
```

Đây là **mẫu**: bảng `dbo.import_orders_stage` phải có cột phù hợp và SQL Server phải đọc được tệp theo đường dẫn trên **máy/chỗ lưu của instance**. Nếu tệp dùng CRLF, có cách cấu hình row terminator tương ứng; cần thử thực tế vì cách xử lý LF/CRLF và hành vi escape có thể khác theo phiên bản và nguồn.

Giải thích:

| Tùy chọn | Mục đích |
| --- | --- |
| `FORMAT = 'CSV'` | Dùng parser CSV của phiên bản hỗ trợ |
| `FIRSTROW = 2` | Bắt đầu đọc dữ liệu từ hàng thứ hai, thường để bỏ header |
| `FIELDTERMINATOR = ','` | Trường phân cách bằng dấu phẩy |
| `FIELDQUOTE = '"'` | Dấu bao quote CSV |
| `ROWTERMINATOR = '0x0a'` | Ký tự LF theo biểu diễn hex |
| `CODEPAGE = '65001'` | UTF-8 theo code page 65001, khi hỗ trợ |
| `TABLOCK` | Có thể ảnh hưởng khóa/hiệu năng của thao tác bulk; phải cân nhắc concurrency |

Không giả định mọi bản SQL Server hỗ trợ CSV parser hoặc UTF-8 với cùng tùy chọn và hành vi. Tùy bản Windows/Linux/Azure SQL và phiên bản, đường dẫn file, quyền và lựa chọn công cụ nạp có thể khác nhau.

### 14.2. Công cụ bcp chạy ở phía client

Ví dụ khái niệm:

```text
bcp MyDatabase.dbo.import_orders_stage in orders.csv -S server_name -T -c -C 65001 -t, -r 0x0a -F 2
```

Đây là mẫu cú pháp **bcp**, không phải T-SQL. Ý nghĩa chính:

- `in`: nhập từ file vào bảng.
- `-S`: SQL Server đích.
- `-T`: dùng xác thực tích hợp khi môi trường hỗ trợ.
- `-c`: character mode.
- `-C 65001`: code page UTF-8 khi được hỗ trợ.
- `-t,`: delimiter dấu phẩy; `-r 0x0a`: row terminator.
- `-F 2`: bắt đầu từ dòng dữ liệu thứ hai.

**Quan trọng:** dùng `-t,` ở bcp character mode **không tự đồng nghĩa với parser CSV nhận biết dấu quote** trong mọi cách vận hành. Với tệp chứa `"Trần, Bình"` hoặc newline bên trong quote, phải dùng định dạng/tiện ích hỗ trợ CSV đúng nghĩa, hoặc chuẩn hóa staging bằng công cụ có parser CSV. Đây là khác biệt lớn giữa **bulk character-delimited** và **CSV parser**.

### 14.3. Từ staging sang bảng typed trong SQL Server

SQL Server có `TRY_CONVERT`/`TRY_CAST` để thử chuyển kiểu một cách kiểm soát:

```sql
SELECT
    source_order_id,
    TRY_CONVERT(date, order_day_text, 23) AS parsed_order_day,
    TRY_CONVERT(decimal(14, 2), amount_text) AS parsed_amount
FROM dbo.import_orders_stage;
```

Style `23` liên quan đến định dạng ngày `yyyy-mm-dd`; cần kiểm tra dữ liệu đầu vào và phiên bản. Khi `TRY_CONVERT` không chuyển được, thường trả NULL cho các phép chuyển được phép thử; tuy nhiên vẫn có trường hợp **phép chuyển không được phép hoặc cấu trúc khác** dẫn tới lỗi. Không xem NULL từ TRY_CONVERT là đồng nghĩa với nguồn gửi NULL nếu chưa kiểm tra nguyên văn.

## 15. Oracle Database: SQL*Loader, external table và Data Pump

Oracle có các công cụ khác nhau theo nhu cầu:

- **SQL*Loader (`sqlldr`)**: tiện ích nạp dữ liệu từ tệp, thường điều khiển bằng **control file**.
- **External table**: mô tả một nguồn dữ liệu ngoài như một đối tượng có thể truy vấn theo cấu hình access driver và directory.
- **Data Pump (`expdp`/`impdp`)**: công cụ export/import theo định dạng và mô hình đối tượng Oracle, không phải “CSV importer chung”.

### 15.1. SQL*Loader control file

Ví dụ control file minh họa:

```text
LOAD DATA
CHARACTERSET AL32UTF8
INFILE 'orders.csv'
INTO TABLE import_orders_stage
APPEND
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
TRAILING NULLCOLS
(
    source_order_id,
    customer_name,
    order_day_text,
    amount_text,
    note_text
)
```

Control file mô tả **bảng đích, delimiter, dấu bao quote, character set và cách xử lý cột cuối thiếu**. Thực tế SQL*Loader có nhiều tùy chọn về fixed-width, direct/conventional path, date format, bad/discard file và logging; cần cấu hình theo Oracle release và đặc điểm tệp.

Ở đây `orders.csv` chỉ là tên file minh họa. Khi chạy trong tổ chức, đường dẫn file, tài khoản và cấu hình connect cần theo quy định. **Không đặt mật khẩu thực vào tài liệu hoặc script lưu trong Git**; dùng cơ chế xác thực an toàn mà môi trường Oracle cung cấp.

### 15.2. Dữ liệu lỗi và bản ghi bị loại

SQL*Loader có thể tạo log, bad file hoặc discard file tùy cấu hình. Hai loại cần phân biệt:

- **Bad record**: record không thể nạp vì lỗi định dạng/chuyển kiểu hoặc lỗi liên quan.
- **Discard record**: record không thỏa điều kiện chọn nạp do control file quy định (khi có cấu hình).

Quy trình cần biết **hàng nào bị loại và tại sao**, không chỉ số hàng tải thành công. Khi cần đối soát tài chính, giữ tệp gốc, log và các bản ghi lỗi theo chính sách.

### 15.3. External table và Data Pump không thay thế nhau

External table giúp truy vấn dữ liệu ngoài bằng SQL và có thể áp dụng bước biến đổi trước ghi bảng đích; tuy nhiên quyền truy cập directory và access parameters là phần cấu hình hệ thống, không phải mọi user có thể tự tạo.

Data Pump chủ yếu giải quyết việc xuất/nhập dữ liệu và metadata theo hệ sinh thái Oracle. Khi nguồn là **CSV từ đối tác**, SQL*Loader hoặc external table thường phù hợp hơn so với `impdp` trực tiếp.

## 16. SQLite: `.import` thuộc CLI, không phải câu SQL

SQLite có công cụ dòng lệnh `sqlite3`. Trong **sqlite3 shell** hiện đại, có thể dùng:

```text
.mode csv
.import --csv --skip 1 orders.csv import_orders_stage
```

Đây là **lệnh của sqlite3 CLI**, không phải SQL gửi trực tiếp qua driver. `--skip 1` dùng để bỏ dòng header theo cú pháp phiên bản hỗ trợ; nếu bản sqlite3 cũ không có tùy chọn này, cần chọn cách import tương ứng hoặc chuẩn hóa file.

### 16.1. Kiểu dữ liệu trong SQLite

SQLite có cơ chế type affinity linh hoạt hơn nhiều hệ quản trị quan hệ truyền thống. Việc `.import` tải một trường thành công **không bảo đảm** nó đã trở thành DECIMAL/DATE theo quy tắc ứng dụng mong muốn. Với dữ liệu tiền, nếu cần chính xác tuyệt đối có thể lưu số nguyên đơn vị nhỏ nhất (ví dụ xu) hoặc dùng mô hình/extension xử lý decimal phù hợp; không mặc định REAL float an toàn cho mọi phép đối soát tài chính.

Sau import, cần validate và chuyển đổi theo schema, constraint và cách lưu ngày/giờ đã thống nhất. Lệnh `.mode csv` chủ yếu điều khiển xử lý/hiển thị CSV ở CLI; nó không tự thay thế quy tắc kiểm tra dữ liệu nguồn.

### 16.2. DuckDB và dữ liệu phân tích cục bộ

DuckDB là một lựa chọn khi cần đọc tệp CSV/Parquet để phân tích:

```sql
SELECT *
FROM read_csv('orders.csv', header = true);
```

hoặc dùng `COPY`/`INSERT` theo schema và phiên bản DuckDB. Đặc điểm hữu ích là có thể truy vấn tệp và chuyển đổi kiểu trước khi ghi bảng; nhưng cơ chế tự suy luận kiểu cũng có thể đoán sai **mã có số 0 đầu, tiền, ngày hoặc cột có dữ liệu lạ ở cuối tệp**. Với pipeline ổn định, khai báo kiểu/cấu hình rõ thay vì phụ thuộc hoàn toàn vào tự động nhận diện.

## 17. Kho dữ liệu đám mây: BigQuery, Snowflake và Redshift

Trong data warehouse, file thường nằm ở **object storage** trước khi nạp vào bảng. Công cụ tải có mô hình khác với đọc một path ổ đĩa cục bộ.

### 17.1. BigQuery load job

Một ví dụ khái niệm qua `bq` CLI, sau khi dữ liệu đã nằm trong Google Cloud Storage:

```text
bq load --source_format=CSV --skip_leading_rows=1 --field_delimiter=',' --encoding=UTF-8 my_dataset.import_orders_stage gs://my-bucket/import/orders.csv source_order_id:STRING,customer_name:STRING,order_day_text:STRING,amount_text:STRING,note_text:STRING
```

`bq` là công cụ client, không phải SQL `INSERT`. Tên bucket/dataset chỉ là ví dụ; cần thay bằng tài nguyên thực tế và quyền IAM phù hợp. Với CSV có **newline trong trường bao quote**, cần cấu hình lựa chọn quoted-newline theo khả năng của load job, không mặc định mọi trường hợp được nhận.

Đối với dữ liệu lớn, BigQuery hỗ trợ load jobs và nhiều định dạng khác như Parquet/Avro. Schema, quy tắc lỗi, partition/clustering và chính sách WRITE_APPEND/WRITE_TRUNCATE cần được quyết định theo pipeline.

### 17.2. Snowflake COPY INTO

Một ví dụ ý tưởng của Snowflake:

```sql
COPY INTO import_orders_stage
FROM @orders_stage
FILE_FORMAT = (
    TYPE = CSV
    SKIP_HEADER = 1
    FIELD_DELIMITER = ','
    FIELD_OPTIONALLY_ENCLOSED_BY = '"'
    ENCODING = 'UTF8'
)
ON_ERROR = 'ABORT_STATEMENT';
```

`@orders_stage` là một stage đã được tạo và phân quyền trước; đây không phải đường dẫn tệp bất kỳ. Snowflake có cơ chế file format, stage, load history và các phương án kiểm tra lỗi. Nếu lô có quote, NULL, escape và newline đặc biệt, cần cấu hình file format tương ứng để parser diễn giải đúng.

### 17.3. Amazon Redshift COPY

Redshift thường tải dữ liệu từ Amazon S3:

```sql
COPY import_orders_stage
FROM 's3://example-bucket/import/orders.csv'
IAM_ROLE 'arn:aws:iam::123456789012:role/RedshiftLoadRole'
CSV
IGNOREHEADER 1
ENCODING UTF8;
```

Bucket, ARN và tên bảng là **giá trị minh họa**, không phải tài nguyên được truy cập trong bài học. Phải cấu hình IAM, region và lựa chọn CSV theo bản Redshift hiện hành. Không nhúng access key bí mật trực tiếp trong script hoặc tài liệu.

### 17.4. Tại sao cloud load cũng cần staging?

Hệ thống lưu trữ đám mây có thể nạp file rất nhanh, nhưng **file nhanh chóng thành bảng không có nghĩa dữ liệu đã đúng**. Các vấn đề vẫn còn:

- Thay đổi schema mà không báo trước;
- Tiền tệ/định dạng số khác nhau;
- ID trùng giữa nguồn;
- Thiếu dữ liệu trong một lô;
- Giao dịch bị upload lại;
- File đến muộn hoặc sai phân vùng ngày.

Vì vậy, bảng landing/raw và bước validate vẫn là thực hành quan trọng ngay cả khi nền tảng có import/load job được quản lý.

## 18. Bảng đối chiếu công cụ theo hệ quản trị

| Hệ quản trị | Công cụ/nền tảng | File đọc ở đâu? | Vấn đề cần kiểm tra |
| --- | --- | --- | --- |
| PostgreSQL | SQL `COPY FROM` | Server hoặc stream STDIN | CSV/TEXT, ENCODING, quyền server file |
| PostgreSQL | psql `\copy` | Client chạy psql | Quyền file client, encoding, kết nối |
| MySQL/MariaDB | `LOAD DATA INFILE` | Server | `secure_file_priv`, quyền và CHARACTER SET |
| MySQL/MariaDB | `LOAD DATA LOCAL INFILE` | Client | Cấu hình LOCAL và bảo mật |
| SQL Server | `BULK INSERT` | Server/nguồn mà instance truy cập | CSV parser, code page, terminator, quyền |
| SQL Server | `bcp` | Client | Character-delimited khác parser CSV đầy đủ |
| Oracle | SQL*Loader | File do tiện ích truy cập | Control file, charset, log/bad/discard |
| Oracle | External table | Directory/nguồn ngoài được cấp quyền | Access parameters, parser và quyền |
| SQLite | `.import` | Máy chạy sqlite3 CLI | Phiên bản CLI, header, type affinity |
| DuckDB | `read_csv` / `COPY` | Theo môi trường DuckDB | Auto-detect type, quote, delimiter |
| BigQuery | Load job / `bq load` | GCS hoặc nguồn được hỗ trợ | Schema, UTF-8, quoted newline, write mode |
| Snowflake | `COPY INTO` | Stage | File format, role, validation, load history |
| Redshift | `COPY` | S3 hoặc nguồn hỗ trợ | IAM, CSV options, error log |

Không cần học thuộc mọi cú pháp của mọi hệ. Nên học **bốn câu hỏi bất biến**: **ai đọc file**, **parser hiểu file thế nào**, **dữ liệu được chuyển kiểu ra sao**, và **hệ thống kiểm chứng những hàng đã nhận như thế nào**.

## 19. Tốc độ và tối ưu hóa khi nạp lô lớn

Các yếu tố ảnh hưởng hiệu năng:

- **Số lần trao đổi mạng:** gửi từng INSERT có overhead cao hơn stream theo lô.
- **Băng thông và nén:** đọc tệp đã nén có thể tiết kiệm I/O/mạng nhưng thêm CPU giải nén.
- **WAL/transaction log:** nhiều hệ cần ghi log phục vụ phục hồi và replication.
- **Số chỉ mục:** mỗi hàng mới có thể phải cập nhật nhiều index.
- **Khóa ngoại/trigger/constraint:** kiểm tra logic và khóa có chi phí.
- **Kích thước transaction:** quá lớn làm rollback và chiếm tài nguyên; quá nhỏ tạo overhead commit.
- **Phân vùng bảng/partition:** nạp theo ngày hoặc tháng có thể hiệu quả nhưng phải đúng khóa phân vùng.
- **Song song:** nhiều loader cùng ghi có thể nhanh hơn hoặc gây tranh chấp khóa/I/O.
- **Bảng staging, chuyển kiểu và dedup:** tăng số bước nhưng cải thiện kiểm soát chất lượng.

### 19.1. Có nên tắt index hoặc constraint để tăng tốc?

Không mặc định. Tạm bỏ index, tắt trigger hay vô hiệu hóa kiểm tra khóa ngoại trên bảng sản xuất có thể tạo dữ liệu sai và gây gián đoạn. Nếu dùng chiến lược nạp vào **bảng rỗng mới**, xây index sau load có thể phù hợp ở một số hệ; nếu nạp cập nhật lên bảng đang phục vụ giao dịch, chi phí và tính an toàn khác hẳn.

Chỉ quyết định sau khi có:

1. Sao lưu/khả năng khôi phục phù hợp.
2. Kế hoạch dừng ghi hoặc cách ly bảng/partition.
3. Đối soát dữ liệu trước khi đưa vào phục vụ.
4. Đánh giá tác động replication, FK, trigger, unique và các ứng dụng khác.

**Nhanh hơn nhưng bỏ kiểm tra dữ liệu sai** không phải tối ưu thành công.

### 19.2. Chunking và batch size

Một file 10 GB có thể được xử lý thành các chunk, nhưng phải chia theo **ranh giới record CSV hợp lệ**, không cắt ở một newline bên trong trường quote. Mỗi chunk cần:

- ID lô và ID chunk;
- Số record/source checksum;
- Trạng thái nhập/chuyển kiểu;
- Cách replay chunk thất bại;
- Quy tắc không nạp trùng khi retry.

Nếu mục tiêu là transaction nguyên tử toàn file, chia chunk rồi commit từng phần làm mất tính nguyên tử ấy, trừ khi dùng staging và bước publish cuối có kiểm soát. Cần quyết định rõ liệu **partial success** có được phép không.

### 19.3. Đo bằng công cụ đúng ngữ cảnh

Trên PostgreSQL, có thể dùng `EXPLAIN (ANALYZE, BUFFERS)` cho truy vấn **chuyển từ staging sang đích** dạng `INSERT ... SELECT` khi phù hợp, nhưng lưu ý nó **thực sự thực thi câu lệnh**. Với bulk load bằng tiện ích, nên đo thêm:

- Throughput: record/s, MB/s.
- Thời gian parse, load, validate, commit.
- Số hàng lỗi và số lần retry.
- CPU, I/O, WAL/log, lock waits và độ trễ replication.
- Thời gian từ lúc file sẵn sàng đến lúc dữ liệu được publish.

Không dùng một ví dụ 5 hàng để kết luận công cụ nào nhanh nhất trên production.

## 20. Bảo mật khi nhận tệp từ bên ngoài

Một chức năng upload CSV có thể trở thành điểm rủi ro nếu cho phép người dùng chọn tùy ý path server hoặc cấu hình load:

1. **Không ghép trực tiếp đường dẫn shell và lệnh hệ thống** từ input của người dùng.
2. **Không cấp role quyền đọc mọi file server** chỉ để import.
3. Lưu tệp upload trong khu vực tách biệt, chỉ đọc bởi dịch vụ được phân quyền.
4. Giới hạn kích thước file, số record, độ dài field và tài nguyên parser.
5. Kiểm tra nội dung/encoding; không tin phần mở rộng `.csv` là bảo đảm file hợp lệ.
6. Dùng tham số truy vấn/prepared statements khi tạo câu `INSERT` hoặc chuyển dữ liệu; không nối giá trị cell thành SQL.
7. Không dùng `COPY FROM PROGRAM`/shell invocation dựa trên tên file do người dùng nhập.
8. Không in dữ liệu cá nhân hoặc token vào log lỗi không được bảo vệ.
9. Mã hóa đường truyền và giới hạn quyền object storage/stage.
10. Có chính sách lưu giữ và xóa tệp gốc, file lỗi và log sau thời gian cần thiết.

### 20.1. CSV formula injection khi mở file bằng bảng tính

Nếu một field do người dùng cung cấp bắt đầu bằng `=`, `+`, `-` hoặc `@`, một số ứng dụng bảng tính có thể diễn giải nó như công thức khi **mở CSV**, tùy phần mềm và phiên bản. Đây chủ yếu là nguy cơ **khi export/mở dữ liệu ở spreadsheet**, không phải SQL parser tự chạy công thức trong DB.

Khi dùng CSV làm trung gian cho báo cáo người dùng tải về, cần chính sách escape phù hợp công cụ đích. Không biến đổi bừa nội dung nghiệp vụ trong database chỉ vì một file có thể được mở bằng spreadsheet; xử lý ở **biên xuất dữ liệu** theo chính sách an toàn.

### 20.2. SQL injection từ giá trị cell

Dữ liệu như:

```text
O'Brien
```

hoàn toàn có thể là tên hợp lệ. Không tự sinh:

```sql
INSERT INTO customers(name) VALUES ('O'Brien');
```

bằng nối chuỗi. Điều này vừa gây lỗi quote vừa mở ra rủi ro injection. Bulk parser hoặc prepared statements sẽ truyền **giá trị dữ liệu** theo giao thức thích hợp; các câu SQL chuyển đổi cũng nên dùng tham số khi có dữ liệu/điều kiện từ người dùng.

## 21. Lỗi thời gian, số và mã định danh: có thể chạy mà vẫn sai

### 21.1. Ngày tháng không thống nhất locale

```text
03/04/2026
```

có thể là **03 tháng 04** hoặc **04 tháng 03**. Nếu nguồn gửi định dạng mơ hồ, không để DBMS tự đoán theo session date format. Yêu cầu ngày ISO `2026-04-03` hoặc khai báo **format theo nguồn** rõ ràng.

Đối với timestamp, nên dùng ISO 8601 có offset/timezone rõ. Chuyển dữ liệu `2026-10-05 08:00` không có múi giờ thành TIMESTAMPTZ có thể phụ thuộc cấu hình session. Cần xác nhận thời gian trong file là **UTC, giờ địa phương hay giờ đã có offset**.

### 21.2. Dấu thập phân và phân cách nghìn

```text
1,234.56
1.234,56
1234.56
```

có thể biểu diễn cùng một số trong các locale khác nhau, nhưng không được mặc định. Khi CSV dùng dấu phẩy làm delimiter, `1,234.56` **nếu không quote** thành hai trường. Nếu quote, parser giữ thành một chuỗi `"1,234.56"` nhưng CAST sang NUMERIC có thể vẫn không phù hợp định dạng DBMS.

Hãy quy định chuỗi tiền **không có phân cách nghìn**, dùng dấu chấm thập phân, ví dụ `1234.56`, hoặc chuyển đổi tại staging bằng quy tắc theo nguồn được kiểm chứng.

### 21.3. Số có số 0 đầu là mã, không phải số lượng

```text
postal_code = 00120
account_code = 000123
```

Nếu tự chuyển sang INTEGER, các giá trị sẽ thành `120` và `123`. Với mã định danh, số 0 đầu có thể mang ý nghĩa. Chọn TEXT/VARCHAR cho mã, không dựa vào bộ tự suy luận kiểu của CSV importer.

### 21.4. Decimal và floating point

Tiền cần tránh sai số nhị phân của floating point trong nhiều bài toán đối soát. PostgreSQL có `NUMERIC(p,s)`, SQL Server có `DECIMAL(p,s)`, MySQL có DECIMAL; việc lưu vào DOUBLE/REAL có thể dẫn tới kết quả không đúng chính xác sau nhiều phép cộng.

**Không mặc định NUMERIC(14,2) là đủ cho mọi hệ**: phải xét biên giá trị, số chữ số thập phân và đơn vị tiền. Một số nguồn dùng tiền ở **đơn vị nhỏ nhất** dưới dạng integer để tránh lỗi làm tròn.

### 21.5. Không tự tin vào kiểu suy luận

Một công cụ import có thể đọc 100 dòng đầu không thấy NULL/giá trị lạ rồi suy luận cột là INTEGER; đến dòng 101 có mã `"001A"` thì lỗi hoặc cắt mất thông tin. Với schema ổn định, nên chỉ định **kiểu cột đích** hoặc nạp raw TEXT rồi chuyển có kiểm soát.

## 22. Những lỗi và ngộ nhận thường gặp

| Ngộ nhận/lỗi | Hệ quả | Cách phòng tránh |
| --- | --- | --- |
| CSV chỉ cần `split(',')` | Tách sai giá trị có dấu phẩy trong quote | Dùng parser CSV đúng dialect |
| Mỗi newline là một record | Phá trường nhiều dòng | Parser nhận biết quote và record separator |
| `HEADER true` luôn kiểm tra tên cột | Thứ tự cột đổi có thể nhập nhầm | Kiểm tra header/schema độc lập |
| UTF-8 được khai báo thì tệp luôn UTF-8 | Mojibake hoặc lỗi decode | Kiểm tra bytes/nguồn và chuyển mã đúng |
| UTF-8 BOM luôn được tự bỏ | Ký tự BOM lẫn vào cột đầu | Thử phiên bản hoặc chuẩn hóa BOM |
| Chuỗi rỗng và NULL luôn giống nhau | Mất phân biệt thiếu dữ liệu với giá trị rỗng | Khai báo NULL marker và quote |
| Ngày `03/04/2026` có nghĩa duy nhất | Đảo ngày/tháng | Dùng ISO và quy định format |
| `1,234.56` luôn được parse thành số | Tách cột hoặc lỗi CAST | Chuẩn hóa phân cách nghìn |
| Cột mã `"00123"` là INTEGER | Mất số 0 đầu | Dùng TEXT/VARCHAR |
| `COPY FROM '/tmp/x.csv'` đọc file trên laptop | SQL COPY mở file từ server | Dùng `\copy` hoặc STDIN từ client |
| `\copy` là SQL chuẩn | SQL driver không hiểu backslash command | Dùng psql hoặc API COPY |
| `LOAD DATA LOCAL` giống non-LOCAL | Khác vị trí file, quyền và nguy cơ | Kiểm tra LOCAL và chính sách bảo mật |
| bcp `-t,` hiểu mọi quy tắc CSV | Dấu phẩy trong quote có thể gây sai | Dùng parser/format CSV thực sự |
| Import thành công = dữ liệu đúng | Không chứng minh định dạng số/khóa/đơn vị | Staging, validate, typed target |
| Một lỗi CAST luôn biến thành NULL | Nhiều DBMS sẽ báo lỗi | Dùng validate/TRY_CAST theo dialect |
| COPY thất bại nghĩa là không có chi phí | Có thể đã dùng I/O/WAL/space | Transaction và quan sát tài nguyên |
| COUNT file lines = số record CSV | Có header và quoted newline | Đếm record bằng parser |
| `DISTINCT` chữa mọi dữ liệu trùng | Trùng theo khóa không giống trùng toàn hàng | Chính sách dedup theo business key |
| Load lại batch sẽ không nhân dữ liệu | Không có unique/upsert thì có thể thêm bản sao | Thiết kế idempotent |
| Không cần log hàng reject | Không biết record nào biến mất | Reject table, error reason, audit |
| Tắt constraint để nhanh hơn luôn an toàn | Bảng đích có thể nhận dữ liệu sai | Quy trình nạp có kiểm soát |
| Chỉ cần checksum file để dedup giao dịch | Khác file có thể chứa cùng ID | Key nghiệp vụ + version |
| Tệp trên S3/GCS giống path máy DB | Quyền/công cụ load khác | Dùng stage/load job phù hợp |

## 23. Bài tập thực hành

Các bài dùng dữ liệu staging ở mục 5 hoặc những tệp mẫu tự tạo với **dữ liệu giả**. Trước khi chạy import vào database thật, thực hành trong môi trường không có dữ liệu nhạy cảm.

### Bài 1 — Nhận diện vấn đề CSV

Cho dòng:

```csv
101,"Trần, Bình","Ghi chú ""ưu tiên"", giao trước 9h"
```

Dòng này có **mấy trường**? Nội dung trường tên và ghi chú sau khi parser CSV giải mã là gì? Vì sao thao tác tách theo dấu phẩy thuần túy cho số trường sai?

### Bài 2 — NULL khác rỗng

Dùng CSV:

```csv
id,note
1,""
2,__NULL__
3,"__NULL__"
```

Với PostgreSQL `FORMAT csv, NULL '__NULL__'`, ba giá trị note được hiểu như thế nào? Tự viết câu `SELECT note IS NULL`, `LENGTH(note)` để quan sát chuỗi rỗng, NULL và chuỗi marker thật.

### Bài 3 — COPY FROM STDIN

Tạo `demo_bulk_raw` với năm cột TEXT và chạy đoạn `COPY ... FROM STDIN` ở mục 5 bằng psql. Kiểm tra số hàng staging bằng **5**. Tìm `WEB-002` có dấu phẩy trong tên và `WEB-005` có dấu quote trong ghi chú.

### Bài 4 — Phát hiện amount lỗi

Viết truy vấn chọn hàng có `amount_text` không phù hợp mẫu số không âm, tối đa hai chữ số thập phân. Vì sao `WEB-004` bị loại? Nếu nguồn có số âm hợp lệ như hoàn tiền, phải sửa hợp đồng định dạng và business rule như thế nào?

### Bài 5 — Chuyển typed target

Tạo `demo_bulk_orders` với `source_order_id PRIMARY KEY`, `order_day DATE` và `amount NUMERIC(14,2)`. Chỉ chuyển bốn record hợp lệ của bộ mẫu. Vì sao COPY thẳng vào cột NUMERIC có thể thất bại ở `WEB-004`?

### Bài 6 — Nhập lại và khóa trùng

Chạy lại `INSERT ... ON CONFLICT DO NOTHING` trên cùng staging. Bảng đích có bao nhiêu hàng? Vì sao kết quả đúng là **4**, không phải 8? Nếu có phiên bản đơn mới cần cập nhật amount, tại sao `DO NOTHING` không đáp ứng quy tắc ấy?

### Bài 7 — Date không hợp lệ nhưng đúng regex

Thêm record có `order_day_text = '2026-02-30'`. Regex `YYYY-MM-DD` có phát hiện lỗi lịch không? Khi CAST sang DATE, vì sao câu có thể thất bại? Đề xuất một bước parse/validate ngày an toàn trước khi chuyển vào bảng đích.

### Bài 8 — Thử BOM và encoding

Tạo hai tệp CSV tiếng Việt: UTF-8 không BOM và UTF-8 có BOM. Dùng cùng công cụ bulk của môi trường thực hành, quan sát header và ký tự tiếng Việt. Tại sao không nên chỉ nhìn hậu tố `.csv` để kết luận encoding?

### Bài 9 — Khác biệt COPY và \copy

Giả sử PostgreSQL server ở container còn file CSV nằm trên laptop. SQL `COPY FROM 'C:\Downloads\orders.csv'` có đọc được file laptop không? Lệnh nào trong psql phù hợp? Nếu psql cũng chạy trong container khác, đường dẫn phải được hiểu theo đâu?

### Bài 10 — Khác biệt dấu xuống dòng

Chuẩn bị một CSV LF và một CSV CRLF. Nhập chúng với cấu hình phù hợp, rồi kiểm tra trường cuối có chứa carriage return không. Điều gì xảy ra nếu một trường note có newline **bên trong quote**?

### Bài 11 — MySQL LOAD DATA

Viết câu `LOAD DATA LOCAL INFILE` tương ứng với file UTF-8, delimiter dấu phẩy, quote `"` và header một hàng. Nêu vì sao phải kiểm tra `local_infile`, thiết lập client/server và `CHARACTER SET utf8mb4`.

### Bài 12 — SQL Server bulk

Viết `BULK INSERT` với `FORMAT='CSV'`, `FIRSTROW=2`, `CODEPAGE='65001'` trên môi trường SQL Server hỗ trợ. Vì sao tiện ích `bcp -t,` kiểu character-delimited chưa chắc xử lý đúng một CSV có dấu phẩy trong quote?

### Bài 13 — Oracle SQL*Loader

Đọc control file minh họa ở mục 15 và giải thích `CHARACTERSET AL32UTF8`, `OPTIONALLY ENCLOSED BY`, `TRAILING NULLCOLS`, `APPEND`. Tại sao phải kiểm tra bad/discard file thay vì chỉ xem số hàng nhập thành công?

### Bài 14 — SQLite và type affinity

Nhập một file CSV vào SQLite bằng `.import` trong CLI. Sau đó kiểm tra cột mã `00123` và số tiền `125000.50`. Nếu importer tự đoán cột số hoặc schema không kiểm soát, những sai lệch dữ liệu nào có thể xảy ra?

### Bài 15 — Chọn công cụ cloud

Giả sử file nằm trong GCS hoặc S3, không có trên ổ đĩa PostgreSQL server. Hãy mô tả cách dùng load job BigQuery hoặc COPY của Redshift theo quyền truy cập storage. Vì sao path và cơ chế IAM là một phần của phương án import?

### Bài 16 — Thiết kế batch audit

Đề xuất bảng `import_batches` lưu file name, checksum, batch ID, số record nguồn, staging, accepted, rejected, duplicate và status. Khi một batch có 10.000 record, 9.980 accepted, 15 rejected và 5 duplicate, cần ghi nhận những chỉ số nào để tổng khớp 10.000?

### Bài 17 — Bảo mật chức năng upload

Một API nhận tên file CSV từ người dùng rồi nối thẳng vào câu `COPY FROM PROGRAM` hoặc lệnh shell. Những rủi ro nào xuất hiện? Hãy đề xuất cơ chế upload an toàn tới thư mục/cổng stream được giới hạn và không cần quyền đọc mọi file máy chủ.

### Bài 18 — Nạp hai file có trùng ID

File A và file B cùng gửi đơn `WEB-001`, nhưng amount khác nhau, bản B có `updated_at` mới hơn. Nếu nghiệp vụ chỉ lưu trạng thái mới nhất, `UNION ALL` và `ON CONFLICT DO NOTHING` có đủ không? Thiết kế quy tắc chọn theo `(source_id, updated_at)` và cập nhật có điều kiện để batch cũ không ghi đè dữ liệu mới.

### Bài 19 — Tính tốc độ nạp

Một lô có 2.000.000 record, thời gian từ bắt đầu load đến commit là 100 giây. Tốc độ trung bình theo record/giây là bao nhiêu? Phân biệt thời gian **parser**, **load vào staging**, **validate**, **ghi đích** và **publish**; tại sao chỉ đo lệnh COPY chưa phản ánh toàn bộ thời gian pipeline?

### Bài 20 — Thiết kế pipeline chuyển đổi hệ thống

Một doanh nghiệp chuyển từ hệ cũ sang PostgreSQL, dữ liệu gồm đơn hàng, dòng sản phẩm và thanh toán. Hãy thiết kế thứ tự: snapshot nguồn, hợp đồng định dạng, nạp staging, kiểm tra khóa ngoại, chuẩn hóa số tiền/timestamp, dedup, đối soát count/sum, commit/publish và phương án rollback. Khi nào cần dừng ghi hệ cũ hoặc có chiến lược đồng bộ bù?

## 24. Quy trình nhập file đáng tin cậy

Một trình tự gợi ý:

1. **Nhận tệp**: ghi `batch_id`, nguồn, phiên bản, kích thước, checksum, thời điểm và phạm vi tenant; kiểm soát quyền.
2. **Xác minh bytes**: encoding UTF-8 hoặc bảng mã đã khai báo; BOM, newline và kích thước trường.
3. **Xác minh cấu trúc**: header, số trường, thứ tự cột, delimiter, quote, escape, marker NULL.
4. **Nạp raw staging**: dùng công cụ của DBMS với đường dẫn/quyền đúng; giữ dữ liệu chưa chuẩn hóa có kiểm soát.
5. **Ghi nhận lỗi parser**: record thiếu cột, quote không đóng, bytes không hợp lệ, tệp lỗi.
6. **Validate nghiệp vụ**: ID, ngày, timestamp, số/đơn vị tiền, status, quan hệ FK và khóa duy nhất.
7. **Cách ly reject**: lưu record gốc, batch và mã lỗi để có thể sửa hoặc trả phản hồi.
8. **Chọn chính sách trùng**: insert-only, upsert theo version, snapshot replace hoặc giữ lịch sử.
9. **Ghi bảng typed**: trong transaction hoặc cơ chế publish phù hợp; không làm gián đoạn dữ liệu đang phục vụ.
10. **Đối soát**: record nguồn = record đã phân loại; đếm accepted/updated/rejected/duplicate, so sánh tổng tiền và kỳ dữ liệu.
11. **Publish và giám sát**: chỉ đánh dấu batch thành công khi đạt điều kiện; cảnh báo khi sai ngưỡng.
12. **Hỗ trợ retry/backfill**: có thể chạy lại mà không sinh bản sao, và biết dữ liệu nào được thay đổi.

```text
       FILE CSV / TSV / SOURCE EXPORT
                     |
                     v
      Encoding + CSV dialect + schema
                     |
                     v
             BULK LOAD / STREAM
         COPY, \copy, LOAD DATA,
          BULK INSERT, sqlldr ...
                     |
                     v
             RAW / STAGING TABLE
                     |
              +------+------+
              |             |
              v             v
         VALID RECORD   INVALID RECORD
              |             |
              |             +--> REJECT + reason
              v
       Typed conversion + constraint
              |
              v
       Business key / version policy
              |
              v
       INSERT / UPSERT / MERGE
              |
              v
        Reconcile + audit + publish
```

## 25. Kết luận

**Nhập dữ liệu hàng loạt** giúp giảm overhead và xử lý tập dữ liệu lớn hiệu quả hơn so với gửi từng câu INSERT, nhưng tính đúng phụ thuộc vào **cấu hình công cụ hệ quản trị**. PostgreSQL phân biệt `COPY` phía server và `\copy` phía psql client; MySQL có `LOAD DATA [LOCAL] INFILE`; SQL Server có `BULK INSERT` và `bcp`; Oracle có SQL*Loader và external tables; SQLite dùng `.import` trong CLI; các data warehouse thường tải qua stage/object storage.

Ở mọi nền tảng, hãy bắt đầu bằng một **hợp đồng dữ liệu rõ ràng**: encoding, delimiter, quote/escape, header, NULL, ngày/giờ, số tiền, định danh và phạm vi quyền. Một tệp hợp lệ về bytes chưa chắc hợp lệ về nghiệp vụ. Mẫu nhập vào **staging TEXT**, kiểm tra/cách ly hàng lỗi rồi chuyển sang bảng typed với **khóa và chính sách nhập lại** giúp tránh lỗi thầm lặng, hỗ trợ đối soát và khả năng khôi phục.

Một quy trình bulk load đáng tin không kết thúc khi công cụ thông báo “import thành công”. Nó kết thúc khi hệ thống chứng minh được **mọi record nguồn đã được xử lý theo một quy tắc xác định, dữ liệu đích giữ đúng nghĩa, số liệu đối soát được và lô có thể chạy lại an toàn**.
