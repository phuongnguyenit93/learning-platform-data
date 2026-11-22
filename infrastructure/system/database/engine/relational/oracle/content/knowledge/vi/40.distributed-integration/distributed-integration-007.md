# UTL_FILE, DIRECTORY và giới hạn truy cập filesystem

Trong các luồng tích hợp dữ liệu, Oracle đôi khi cần trao đổi tệp với hệ thống bên ngoài: đọc CSV do ứng dụng gửi đến, ghi kết quả xử lý ra tệp, hoặc tạo tệp trung gian để một tiến trình khác chuyển tiếp. PL/SQL cung cấp package `UTL_FILE` cho thao tác đọc và ghi tệp ở phía máy chủ cơ sở dữ liệu. Quyền truy cập được định tuyến qua các đối tượng `DIRECTORY`, kết hợp với quyền trong Oracle và quyền của hệ điều hành.

Điểm cần nhớ là `UTL_FILE` làm việc trên filesystem mà tiến trình Oracle Database nhìn thấy. Nó không mở thư mục trên máy tính của người đang chạy SQL Developer, ứng dụng web hay máy khách kết nối vào database. Vì vậy, khi thiết kế tích hợp phân tán, cần xác định rõ tệp nằm trên máy chủ database nào, ai tạo tệp, ai đọc tệp và cách các nút database cùng nhìn thấy vùng lưu trữ đó.

## 1. Vai trò của UTL_FILE và DIRECTORY

`UTL_FILE` là package PL/SQL dùng để mở, đọc, ghi, nối thêm, đóng, đổi tên, sao chép hoặc xóa tệp trong một thư mục được database cho phép. Package cung cấp các thao tác mức tệp; nó không phải API quản trị filesystem tổng quát và không thay thế một dịch vụ truyền tệp như SFTP hay middleware tích hợp.

Một đối tượng `DIRECTORY` là tên logic được lưu trong Oracle Data Dictionary, ánh xạ đến một đường dẫn vật lý trên máy chủ database. Ví dụ:

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| Đối tượng DIRECTORY | `INBOUND_DIR` | Tên logic mà PL/SQL truyền cho `UTL_FILE` |
| Đường dẫn vật lý | `/u01/app/oracle/inbound` | Thư mục thực trên máy chủ database |
| Tên tệp | `orders_20261114.csv` | Tệp nằm bên trong thư mục được ánh xạ |
| Schema ứng dụng | `INTEGRATION_APP` | Tài khoản được cấp quyền đọc hoặc ghi thư mục |

Khi gọi `UTL_FILE.FOPEN('INBOUND_DIR', 'orders.csv', 'r')`, Oracle tìm đối tượng `INBOUND_DIR`, lấy đường dẫn vật lý đã khai báo và yêu cầu tiến trình database mở tệp trong đường dẫn đó. Ứng dụng không truyền một đường dẫn tùy ý vào mỗi lần gọi.

Đối tượng `DIRECTORY` không tự tạo thư mục trên hệ điều hành. Thư mục vật lý phải được tạo trước, tồn tại trên máy chủ database và có quyền filesystem phù hợp. Một đối tượng DIRECTORY có thể được cấp quyền cho nhiều schema, vì vậy không cần tạo một đối tượng riêng cho từng schema nếu các schema thực sự dùng chung vùng lưu trữ.

## 2. Tạo DIRECTORY và cấp quyền

Quản trị viên hoặc tài khoản có system privilege phù hợp, thường là `CREATE ANY DIRECTORY`, tạo đối tượng ánh xạ:

```sql
CREATE OR REPLACE DIRECTORY inbound_dir
  AS '/u01/app/oracle/inbound';

CREATE OR REPLACE DIRECTORY outbound_dir
  AS '/u01/app/oracle/outbound';
```

Đường dẫn trong ví dụ là đường dẫn trên máy chủ chạy Oracle Database, không phải đường dẫn trên máy trạm của người dùng. Trên Windows, đường dẫn sẽ theo quy tắc của máy chủ Windows, chẳng hạn `D:\oracle\exchange\inbound`.

Sau khi tạo đối tượng, cấp đúng quyền cần thiết cho schema chạy chương trình:

```sql
GRANT READ ON DIRECTORY inbound_dir TO integration_app;
GRANT WRITE ON DIRECTORY outbound_dir TO integration_app;
```

Quyền `READ` cho phép đọc tệp trong thư mục; quyền `WRITE` cho phép các thao tác ghi tệp được hỗ trợ. Nếu một tiến trình cần đọc và ghi cùng thư mục thì mới cấp cả hai quyền:

```sql
GRANT READ, WRITE ON DIRECTORY exchange_dir TO integration_app;
```

Có thể thu hồi quyền khi không còn nhu cầu:

```sql
REVOKE WRITE ON DIRECTORY outbound_dir FROM integration_app;
```

Tên đối tượng DIRECTORY thường được Oracle chuẩn hóa thành chữ hoa khi không dùng dấu ngoặc kép. Có thể kiểm tra các ánh xạ mà tài khoản hiện tại nhìn thấy:

```sql
SELECT directory_name, directory_path
FROM all_directories
WHERE directory_name IN ('INBOUND_DIR', 'OUTBOUND_DIR');
```

Tài khoản có quyền từ điển dữ liệu phù hợp có thể tra cứu `DBA_DIRECTORIES` để xem toàn bộ đối tượng DIRECTORY trong database.

Hai lớp quyền phải cùng cho phép thao tác:

1. **Oracle Database:** schema cần có quyền `READ` hoặc `WRITE` trên đúng đối tượng DIRECTORY.
2. **Hệ điều hành:** tài khoản dịch vụ hoặc tài khoản hệ điều hành mà tiến trình Oracle Database chạy dưới đó phải có quyền đọc, ghi, tạo hoặc xóa tệp tương ứng trên đường dẫn vật lý.

Chỉ cấp quyền trong Oracle không thể vượt qua quyền filesystem của hệ điều hành. Ngược lại, cấp quyền đọc/ghi cho tài khoản hệ điều hành cũng không tự cấp quyền cho schema trong database.

Nếu thao tác được gọi từ stored procedure chạy với quyền của chủ sở hữu (definer's rights), hãy cấp quyền DIRECTORY trực tiếp cho schema sở hữu chương trình. Không nên dựa vào quyền được nhận thông qua role trong trường hợp quyền đó cần được kiểm tra khi biên dịch hoặc thực thi chương trình PL/SQL lưu trữ.

## 3. Ghi tệp bằng UTL_FILE

Ví dụ sau tạo một tệp CSV trong thư mục `OUTBOUND_DIR`:

```sql
DECLARE
  l_file UTL_FILE.FILE_TYPE;
BEGIN
  l_file := UTL_FILE.FOPEN(
    location     => 'OUTBOUND_DIR',
    filename     => 'orders_20261114.csv',
    open_mode    => 'w',
    max_linesize => 32767
  );

  UTL_FILE.PUT_LINE(l_file, 'order_id,amount');
  UTL_FILE.PUT_LINE(l_file, '1001,250.00');
  UTL_FILE.PUT_LINE(l_file, '1002,175.50');

  UTL_FILE.FCLOSE(l_file);
EXCEPTION
  WHEN OTHERS THEN
    IF UTL_FILE.IS_OPEN(l_file) THEN
      BEGIN
        UTL_FILE.FCLOSE(l_file);
      EXCEPTION
        WHEN OTHERS THEN
          NULL; -- Giữ lại ngoại lệ ban đầu; ứng dụng nên ghi nhận lỗi đóng tệp nếu cần.
      END;
    END IF;
    RAISE;
END;
/
```

`FOPEN` nhận tên đối tượng DIRECTORY ở tham số `location`, tên tệp ở tham số `filename` và chế độ mở ở `open_mode`. Trong ví dụ, chế độ `w` tạo tệp mới hoặc ghi đè nội dung tệp cùng tên đã tồn tại. Vì vậy, không dùng tên tệp cố định nếu nhiều lần chạy cần giữ lại các kết quả trước đó.

Các chế độ văn bản thường dùng:

| Chế độ | Ý nghĩa |
|---|---|
| `r` | Mở tệp để đọc; tệp phải tồn tại và đọc được |
| `w` | Mở để ghi; tạo tệp hoặc ghi đè tệp hiện có |
| `a` | Mở để nối dữ liệu vào cuối tệp |

Các chế độ nhị phân tương ứng là `rb`, `wb` và `ab`. Khi làm việc ở chế độ nhị phân, dùng các thủ tục như `GET_RAW` và `PUT_RAW` thay vì xử lý từng dòng văn bản.

Một số thủ tục văn bản thường gặp:

- `PUT` ghi chuỗi vào bộ đệm của tệp.
- `PUT_LINE` ghi chuỗi và kết thúc dòng.
- `NEW_LINE` ghi ký tự kết thúc dòng.
- `FFLUSH` đẩy dữ liệu đang đệm ra tệp.
- `FCLOSE` đóng tệp và hoàn tất thao tác ghi.
- `IS_OPEN` kiểm tra handle còn mở hay không.

Luôn đóng handle sau khi hoàn tất. Khi có ngoại lệ, cần có nhánh dọn dẹp để tránh giữ handle mở trong phiên làm việc. Không nên mở nhiều tệp cùng lúc nếu không cần thiết.

## 4. Đọc tệp bằng UTL_FILE

Ví dụ sau đọc từng dòng của tệp đầu vào. Khi đã đến cuối tệp, `GET_LINE` phát sinh `NO_DATA_FOUND`; vòng lặp bắt ngoại lệ này để kết thúc:

```sql
DECLARE
  l_file UTL_FILE.FILE_TYPE;
  l_line VARCHAR2(32767);
BEGIN
  l_file := UTL_FILE.FOPEN(
    location     => 'INBOUND_DIR',
    filename     => 'orders.csv',
    open_mode    => 'r',
    max_linesize => 32767
  );

  LOOP
    BEGIN
      UTL_FILE.GET_LINE(l_file, l_line);
    EXCEPTION
      WHEN NO_DATA_FOUND THEN
        EXIT;
    END;

    -- Thay bằng bước phân tích và nạp dữ liệu phù hợp với định dạng CSV.
    DBMS_OUTPUT.PUT_LINE(l_line);
  END LOOP;

  UTL_FILE.FCLOSE(l_file);
EXCEPTION
  WHEN OTHERS THEN
    IF UTL_FILE.IS_OPEN(l_file) THEN
      UTL_FILE.FCLOSE(l_file);
    END IF;
    RAISE;
END;
/
```

Ví dụ chỉ minh họa cách đọc từng dòng. Trong chương trình thực tế, cần phân tích CSV đúng quy tắc: dấu phẩy có thể xuất hiện bên trong trường được đặt trong dấu ngoặc kép, trường có thể chứa dấu xuống dòng, và dữ liệu có thể có quy tắc escape riêng. Không nên dùng phép `SPLIT` đơn giản theo dấu phẩy nếu định dạng đầu vào cho phép các trường CSV phức tạp.

Ngoài đọc và ghi, package còn có các thủ tục như `FGETATTR` để lấy thông tin thuộc tính tệp, `FCOPY` để sao chép, `FRENAME` để đổi tên và `FREMOVE` để xóa tệp. Các thao tác này vẫn chịu cùng các giới hạn quyền DIRECTORY và quyền filesystem của hệ điều hành.

## 5. Giới hạn truy cập filesystem

### 5.1. Chỉ truy cập đường dẫn đã được ánh xạ

Ứng dụng PL/SQL dùng tên DIRECTORY đã được quản trị viên tạo và cấp quyền. Thiết kế này giúp kiểm soát các vùng filesystem mà schema được phép truy cập. Khi gọi `FOPEN`, truyền tên tệp nằm trong thư mục đó; không nhận một đường dẫn tuyệt đối tùy ý từ người dùng rồi ghép trực tiếp vào lời gọi.

Ví dụ, nếu ứng dụng nhận tên tệp từ thông điệp tích hợp, cần kiểm tra tên tệp theo allowlist hoặc quy tắc định dạng đã định nghĩa. Loại bỏ các thành phần đường dẫn, tên thư mục con không được phép và các giá trị có thể làm thay đổi vị trí tệp. Không dùng dữ liệu bên ngoài để quyết định đường dẫn DIRECTORY hoặc để truy cập vùng lưu trữ rộng hơn quyền nghiệp vụ cho phép.

### 5.2. Quyền Oracle và quyền hệ điều hành là hai điều kiện độc lập

Một lời gọi có thể thất bại dù đối tượng DIRECTORY tồn tại:

- Schema chưa được cấp `READ` hoặc `WRITE` trên đối tượng đó.
- Stored procedure chạy dưới schema khác với schema đã được cấp quyền.
- Đường dẫn vật lý không tồn tại trên máy chủ database.
- Tài khoản dịch vụ Oracle không có quyền đọc, ghi hoặc tạo tệp tại thư mục.
- Tệp đã tồn tại nhưng quyền hoặc thuộc tính của tệp không cho phép thao tác được yêu cầu.
- Hệ thống tệp đã hết dung lượng hoặc đạt giới hạn tài nguyên của hệ điều hành.

Vì vậy, khi điều tra lỗi, hãy kiểm tra cả tên DIRECTORY, quyền object trong Oracle, đường dẫn thực trên đúng máy chủ và quyền của tài khoản chạy database.

### 5.3. Giới hạn về vị trí thực thi

`UTL_FILE` chạy ở phía database server. Nếu người dùng kết nối từ máy cá nhân có thư mục `C:\data`, đường dẫn đó không tự động có nghĩa đối với database chạy trên Linux hoặc một máy chủ khác. Tệp phải được chuyển đến vùng lưu trữ mà máy chủ database truy cập được.

Đối tượng DIRECTORY cũng không phải một kết nối mạng hay một giao thức truyền tệp. Nó ánh xạ đến đường dẫn mà máy chủ database nhìn thấy, chẳng hạn ổ đĩa cục bộ hoặc một filesystem được mount. Muốn truyền tệp đến một máy chủ từ xa, cần một cơ chế truyền tệp hoặc middleware phù hợp; không thể coi `UTL_FILE` như một lệnh SFTP.

Trong Oracle RAC, các instance có thể chạy trên nhiều node. Nếu các node cần đọc cùng một bộ tệp, đường dẫn được ánh xạ phải tồn tại và có quyền nhất quán trên mọi node liên quan. Thông thường cần một vùng lưu trữ dùng chung hoặc cơ chế phân phối tệp được vận hành rõ ràng. Nếu mỗi node có filesystem cục bộ riêng, một tệp được tạo trên node này có thể không tồn tại khi phiên xử lý tiếp theo chạy trên node khác.

Trong môi trường multitenant, hãy tạo và kiểm tra DIRECTORY trong đúng container/PDB mà ứng dụng sử dụng, đồng thời xác minh đường dẫn trên máy chủ database thực tế. Việc một đối tượng DIRECTORY tồn tại trong một PDB không tự đảm bảo đường dẫn đó tồn tại hoặc có quyền trên mọi máy chủ.

### 5.4. Giới hạn kích thước dòng và số handle

Tham số `max_linesize` của `FOPEN` có giá trị từ 1 đến 32767; giá trị mặc định là 1024. Đây là giới hạn kích thước dòng mà các thao tác văn bản của `UTL_FILE` xử lý. Khi xử lý dòng dài, cần chỉ định kích thước phù hợp và kiểm tra giới hạn 32767 byte. Với bộ ký tự nhiều byte, số ký tự thực tế có thể ít hơn số byte cho phép.

Số tệp được mở đồng thời còn chịu giới hạn cấu hình của Oracle, trong đó có tham số `UTL_FILE_MAX_OPEN_FILES`, cùng giới hạn tài nguyên của tiến trình và hệ điều hành. Đóng handle ngay khi xong, tránh mở một handle cho mỗi bản ghi và không giữ tệp mở trong thời gian xử lý nghiệp vụ dài.

Nếu dữ liệu có dòng dài hơn giới hạn, cấu trúc bản ghi lớn hoặc yêu cầu xử lý nhị phân, hãy cân nhắc thiết kế định dạng và cơ chế nạp phù hợp thay vì cố tăng `max_linesize` vượt giới hạn của package.

### 5.5. Bộ ký tự và dữ liệu nhị phân

`FOPEN` xử lý tệp văn bản theo chế độ ký tự thông thường của package. Với dữ liệu Unicode cần chế độ tương ứng, có thể dùng `FOPEN_NCHAR` cùng các thủ tục NCHAR như `GET_LINE_NCHAR` và `PUT_LINE_NCHAR`. Không trộn lẫn handle mở theo chế độ NCHAR với các thủ tục không tương thích; Oracle có thể phát sinh lỗi `CHARSETMISMATCH`.

Với nội dung nhị phân, dùng chế độ mở nhị phân và các thủ tục RAW. Không xử lý tệp nhị phân như văn bản vì việc chuyển đổi ký tự hoặc ký tự xuống dòng có thể làm thay đổi byte dữ liệu.

### 5.6. Tệp không nằm trong giao dịch database

Ghi tệp bằng `UTL_FILE` không tham gia cơ chế rollback của giao dịch Oracle. Nếu chương trình ghi được một phần tệp rồi phát sinh lỗi và rollback dữ liệu database, phần tệp đã ghi không tự động bị hoàn tác. Tương tự, commit một giao dịch không bảo đảm hệ thống bên ngoài đã nhận hoặc xử lý tệp.

Với luồng tích hợp quan trọng, nên quản lý trạng thái xuất/nhập bằng bảng điều khiển trong database. Có thể tạo tệp với tên tạm, ghi hết dữ liệu, đóng tệp rồi đổi tên sang tên công bố để tiến trình nhận chỉ đọc tệp đã hoàn tất. Cách này giảm nguy cơ bên nhận đọc một tệp đang được ghi, nhưng thao tác filesystem vẫn cần được giám sát và xử lý khi lỗi. Thiết kế thêm mã giao dịch, tên tệp duy nhất, kiểm tra trùng lặp và cơ chế chạy lại an toàn để tránh nạp hoặc gửi dữ liệu hai lần.

### 5.7. Ghi đồng thời và ghi đè

`UTL_FILE` không cung cấp cơ chế khóa nghiệp vụ cho nhiều tiến trình cùng ghi một tệp. Hai phiên cùng mở một tên tệp để ghi hoặc nối thêm có thể tạo ra dữ liệu không đúng thứ tự mong muốn hoặc ghi đè kết quả của nhau. Dùng tên tệp duy nhất theo lô, mã giao dịch hoặc thời điểm; nếu cần một tệp dùng chung, hãy điều phối quyền ghi bằng cơ chế khóa hoặc hàng đợi ở tầng ứng dụng.

Đặc biệt chú ý chế độ `w`: mở tệp hiện có ở chế độ này sẽ ghi đè nội dung. Trước khi dùng tên tệp cố định, phải xác định rõ chính sách lưu lịch sử, thay thế, lưu trữ và phục hồi.

## 6. UTL_FILE trong kiến trúc tích hợp phân tán

Một mô hình trao đổi tệp thường có ba phần:

1. **Vùng inbound:** hệ thống ngoài chuyển tệp đến một thư mục được database server truy cập. Schema ứng dụng chỉ có quyền `READ` nếu chỉ cần nhận dữ liệu.
2. **Xử lý trong database:** PL/SQL đọc tệp, kiểm tra cấu trúc và dữ liệu, ghi kết quả vào bảng staging, sau đó chuyển dữ liệu hợp lệ vào bảng nghiệp vụ. Lưu lại tên tệp, mã lô, thời điểm nhận, số dòng và trạng thái xử lý.
3. **Vùng outbound:** chương trình tạo tệp kết quả trong thư mục riêng. Tiến trình truyền tệp bên ngoài đọc tệp đã hoàn tất và chuyển đến hệ thống đích. Schema chỉ có quyền `WRITE` nếu không cần đọc lại hoặc xóa tệp.

Nên tách inbound và outbound để giới hạn quyền theo chiều dữ liệu. Có thể dùng schema chuyên trách cho tích hợp, chỉ cấp quyền trên những DIRECTORY cần thiết và giới hạn quyền hệ điều hành vào đúng các thư mục đó. Không cấp quyền DIRECTORY cho `PUBLIC` nếu không có yêu cầu rõ ràng.

Nếu database có nhiều node, cần quyết định một trong các cách: dùng filesystem chia sẻ, định tuyến công việc đến node sở hữu tệp, hoặc để dịch vụ truyền tệp đưa tệp đến đúng node. Nếu tích hợp với database từ xa qua database link, cần nhớ rằng database link cho phép truy vấn database từ xa; nó không biến DIRECTORY cục bộ thành đường dẫn filesystem của máy chủ từ xa.

Đối với nhu cầu truyền tệp qua mạng, retry, mã hóa, xác thực đối tác, kiểm soát tốc độ hoặc theo dõi giao nhận, nên giao trách nhiệm truyền tải cho middleware hay dịch vụ managed file transfer. Database có thể tạo và tiêu thụ tệp ở vùng staging, còn lớp tích hợp xử lý việc chuyển tệp qua mạng và phản hồi trạng thái.

## 7. Các lỗi thường gặp và cách khoanh vùng

| Lỗi Oracle | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| `ORA-29280: invalid directory path` | Tên DIRECTORY không tồn tại hoặc đường dẫn ánh xạ không hợp lệ | Kiểm tra `ALL_DIRECTORIES`/ `DBA_DIRECTORIES`, đúng PDB và đường dẫn trên máy chủ |
| `ORA-29289: directory access denied` | Schema thiếu quyền trên DIRECTORY | Kiểm tra và cấp đúng quyền `READ` hoặc `WRITE` |
| `ORA-29283: invalid file operation` | Tệp không tồn tại, tên tệp không hợp lệ hoặc filesystem từ chối thao tác | Kiểm tra tên tệp, thư mục vật lý, quyền OS và trạng thái filesystem |
| `ORA-29284: file read error` | Lỗi trong lúc đọc tệp | Kiểm tra tệp, quyền đọc, định dạng và trạng thái filesystem |
| `ORA-29285: file write error` | Lỗi trong lúc ghi tệp | Kiểm tra quyền ghi, dung lượng, quota và giới hạn filesystem |
| `CHARSETMISMATCH` | Dùng handle NCHAR với thủ tục không tương thích hoặc ngược lại | Dùng nhất quán `FOPEN` hoặc `FOPEN_NCHAR` và nhóm thủ tục tương ứng |

Một trình tự kiểm tra hiệu quả:

1. Xác nhận chương trình đang chạy dưới schema nào và trong PDB/service nào.
2. Kiểm tra tên DIRECTORY và đường dẫn ánh xạ trong Data Dictionary.
3. Xác nhận schema có quyền object cần thiết; với stored procedure definer's rights, kiểm tra quyền được cấp trực tiếp cho owner.
4. Đăng nhập hoặc nhờ quản trị viên kiểm tra trên đúng máy chủ/node database để xác nhận thư mục tồn tại và tài khoản dịch vụ Oracle có quyền phù hợp.
5. Kiểm tra tên tệp, chế độ mở, kích thước dòng, encoding, dung lượng đĩa và số handle đang mở.
6. Ghi nhận mã lô và tên tệp để có thể chạy lại hoặc xử lý thủ công mà không tạo dữ liệu trùng.

## 8. Lưu ý về cấu hình cũ và thực hành an toàn

`UTL_FILE_DIR` là tham số khởi tạo cũ từng cho phép cấu hình các thư mục mà `UTL_FILE` có thể truy cập. Tham số này đã bị deprecated và bị desupported từ Oracle Database 18c. Với thiết kế mới, sử dụng DIRECTORY object và cấp quyền rõ ràng thay vì dựa vào `UTL_FILE_DIR`.

Các thực hành nên áp dụng:

- Tạo DIRECTORY riêng cho từng luồng hoặc vùng dữ liệu có ranh giới bảo mật khác nhau.
- Chỉ cấp `READ` hoặc `WRITE` đúng nhu cầu; hạn chế cấp cả hai quyền.
- Không cấp quyền DIRECTORY cho `PUBLIC` và không dùng tài khoản có quyền filesystem quá rộng.
- Giữ đường dẫn vật lý do quản trị viên cấu hình; không lấy đường dẫn tùy ý từ dữ liệu đầu vào.
- Kiểm tra và chuẩn hóa tên tệp đến từ hệ thống ngoài; không cho phép thành phần đường dẫn không được phê duyệt.
- Đặt giới hạn kích thước tệp, số dòng, thời gian xử lý và dung lượng vùng staging ở tầng tích hợp.
- Dùng tên tệp duy nhất, lưu trạng thái xử lý và thiết kế thao tác chạy lại an toàn.
- Đóng tệp trong cả nhánh thành công và nhánh lỗi; ghi log đủ thông tin để truy vết.
- Dọn tệp cũ theo chính sách lưu trữ được thống nhất với nhóm vận hành.
- Bảo vệ dữ liệu nhạy cảm trong filesystem bằng quyền truy cập, mã hóa và chính sách lưu trữ phù hợp.

`UTL_FILE` phù hợp khi database cần đọc hoặc tạo tệp trong một vùng filesystem đã được quản trị và kiểm soát. DIRECTORY object xác định vùng mà schema được phép yêu cầu truy cập; quyền hệ điều hành quyết định tiến trình Oracle có thực hiện được thao tác hay không. Trong hệ thống phân tán, cần bổ sung thiết kế về vị trí lưu trữ trên các node, truyền tệp, trạng thái giao nhận, chạy lại và tính nhất quán vì thao tác filesystem không nằm trong giao dịch database.
