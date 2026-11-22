# Đọc ghi CLOB/BLOB bằng DBMS_LOB

Oracle Database cung cấp kiểu dữ liệu LOB (*Large Object*) để lưu nội dung lớn như văn bản dài, tài liệu, hình ảnh, âm thanh hoặc dữ liệu nhị phân. Hai kiểu thường gặp là **CLOB** (*Character Large Object*) cho dữ liệu ký tự và **BLOB** (*Binary Large Object*) cho dữ liệu nhị phân. Trong PL/SQL, package `DBMS_LOB` cung cấp các thủ tục và hàm để đọc, ghi, nối, sao chép, cắt ngắn và kiểm tra nội dung LOB thông qua locator.

Khi làm việc với LOB, cần phân biệt locator với nội dung thực tế. Một locator là tham chiếu để Oracle truy cập giá trị LOB. Chương trình có thể lấy locator từ một cột, rồi truyền locator đó cho `DBMS_LOB.READ`, `WRITE`, `WRITEAPPEND` hoặc các thao tác khác. Với LOB lớn, cách làm này cho phép xử lý theo từng phần thay vì chuyển toàn bộ nội dung vào một biến PL/SQL.

## 1. CLOB và BLOB khác nhau thế nào?

| Đặc điểm | CLOB | BLOB |
|---|---|---|
| Nội dung | Văn bản và dữ liệu ký tự | Dữ liệu nhị phân tùy ý |
| Đơn vị độ dài, offset và amount trong DBMS_LOB | Ký tự | Byte |
| Bộ đệm PL/SQL thường dùng | VARCHAR2 | RAW |
| Ví dụ | JSON, XML, nội dung bài viết, văn bản dài | Ảnh, PDF, tệp nén, dữ liệu mã hóa |
| Chuyển đổi ký tự | Theo character set của CLOB và bộ đệm | Không tự hiểu nội dung là văn bản |

Oracle còn có NCLOB để lưu dữ liệu ký tự theo national character set. Phần này tập trung vào CLOB và BLOB; nguyên tắc xử lý tương tự nhưng cần dùng kiểu bộ đệm phù hợp cho NCLOB.

Không nên lưu dữ liệu nhị phân tùy ý vào CLOB chỉ vì dữ liệu đó có thể biểu diễn bằng một chuỗi. Ngược lại, nếu lưu văn bản trong BLOB, ứng dụng phải thống nhất encoding khi chuyển đổi giữa byte và ký tự. Với dữ liệu ảnh, PDF hoặc tệp nhị phân, hãy dùng BLOB để giữ nguyên byte.

## 2. LOB locator, NULL và LOB rỗng

Một cột LOB có thể có giá trị NULL hoặc chứa một LOB rỗng. Hai trường hợp này khác nhau:

- **NULL:** cột chưa có locator hợp lệ để truy cập nội dung.
- **LOB rỗng:** có locator hợp lệ nhưng độ dài bằng 0.

Trong SQL, Oracle cung cấp `EMPTY_CLOB()` và `EMPTY_BLOB()` để khởi tạo LOB rỗng. Đây là cách phổ biến khi INSERT một hàng rồi lấy locator bằng mệnh đề `RETURNING`.

Ví dụ tạo bảng lưu tài liệu:

~~~sql
CREATE TABLE document_store (
  document_id    NUMBER PRIMARY KEY,
  title          VARCHAR2(200) NOT NULL,
  text_content   CLOB,
  binary_content BLOB,
  created_at     TIMESTAMP DEFAULT SYSTIMESTAMP
);
~~~

Thêm một hàng với hai LOB rỗng:

~~~sql
INSERT INTO document_store (
  document_id,
  title,
  text_content,
  binary_content
)
VALUES (
  1,
  'Tài liệu mẫu',
  EMPTY_CLOB(),
  EMPTY_BLOB()
);

COMMIT;
~~~

Nếu cột LOB đang là NULL, hãy khởi tạo nó bằng `EMPTY_CLOB()` hoặc `EMPTY_BLOB()` trước khi gọi các thao tác ghi. Các thủ tục ghi cần một locator hợp lệ và có thể ghi được.

## 3. Các thao tác DBMS_LOB thường dùng

| API | Mục đích |
|---|---|
| `GETLENGTH` | Lấy độ dài LOB |
| `SUBSTR` | Lấy một đoạn nội dung thành VARCHAR2 hoặc RAW |
| `READ` | Đọc dữ liệu vào bộ đệm PL/SQL |
| `WRITE` | Ghi dữ liệu tại offset chỉ định |
| `WRITEAPPEND` | Ghi thêm dữ liệu vào cuối LOB |
| `APPEND` | Nối toàn bộ một LOB nguồn vào LOB đích |
| `COPY` | Sao chép một đoạn từ LOB nguồn sang LOB đích |
| `TRIM` | Cắt LOB về độ dài mới |
| `INSTR` | Tìm vị trí một mẫu trong LOB |
| `COMPARE` | So sánh nội dung hai LOB hoặc hai đoạn LOB |
| `CREATETEMPORARY` | Tạo LOB tạm trong bộ nhớ/tablespace tạm |
| `FREETEMPORARY` | Giải phóng LOB tạm |
| `OPEN`, `CLOSE` | Mở và đóng LOB khi cần quản lý một chuỗi thao tác |

Các API có overload cho nhiều loại LOB. Hãy truyền đúng kiểu locator và bộ đệm: CLOB thường đi với VARCHAR2, BLOB đi với RAW.

## 4. Lấy độ dài và đọc một đoạn bằng SUBSTR

`DBMS_LOB.GETLENGTH` trả về độ dài của LOB. Với CLOB, độ dài được tính theo ký tự; với BLOB, độ dài được tính theo byte.

~~~sql
DECLARE
  l_clob CLOB;
  l_blob BLOB;
  l_text VARCHAR2(32767);
  l_raw  RAW(32767);
  l_clob_length NUMBER;
  l_blob_length NUMBER;
BEGIN
  SELECT text_content, binary_content
    INTO l_clob, l_blob
    FROM document_store
   WHERE document_id = 1;

  IF l_clob IS NOT NULL THEN
    l_clob_length := DBMS_LOB.GETLENGTH(l_clob);
    DBMS_OUTPUT.PUT_LINE('CLOB characters: ' || l_clob_length);

    IF l_clob_length > 0 THEN
      l_text := DBMS_LOB.SUBSTR(l_clob, 4000, 1);
      DBMS_OUTPUT.PUT_LINE('CLOB prefix: ' || l_text);
    END IF;
  END IF;

  IF l_blob IS NOT NULL THEN
    l_blob_length := DBMS_LOB.GETLENGTH(l_blob);
    DBMS_OUTPUT.PUT_LINE('BLOB bytes: ' || l_blob_length);

    IF l_blob_length > 0 THEN
      l_raw := DBMS_LOB.SUBSTR(l_blob, 100, 1);
      DBMS_OUTPUT.PUT_LINE('BLOB prefix (hex): ' || RAWTOHEX(l_raw));
    END IF;
  END IF;
END;
/
~~~

Tham số thứ hai của `SUBSTR` là số ký tự đối với CLOB và số byte đối với BLOB. Tham số thứ ba là offset bắt đầu, tính từ 1. Giá trị trả về bị giới hạn bởi kích thước bộ đệm kiểu VARCHAR2 hoặc RAW; vì vậy `SUBSTR` phù hợp để lấy một đoạn nhỏ, không phải cách tải toàn bộ LOB lớn vào một biến.

## 5. Đọc LOB theo từng phần bằng READ

Khi nội dung lớn hơn giới hạn bộ đệm PL/SQL, hãy đọc theo từng phần. `DBMS_LOB.READ` nhận locator, số lượng cần đọc, offset và bộ đệm đầu ra. Tham số `amount` là IN OUT: truyền số lượng muốn đọc, sau lời gọi nó chứa số lượng thực tế đã đọc. Offset tiếp theo phải tăng theo số lượng thực tế này.

### Đọc CLOB

~~~sql
DECLARE
  l_clob   CLOB;
  l_buffer VARCHAR2(32767);
  l_length NUMBER;
  l_offset NUMBER := 1;
  l_amount BINARY_INTEGER;
  c_chunk_chars CONSTANT PLS_INTEGER := 8000;
BEGIN
  SELECT text_content
    INTO l_clob
    FROM document_store
   WHERE document_id = 1;

  IF l_clob IS NULL THEN
    RETURN;
  END IF;

  l_length := DBMS_LOB.GETLENGTH(l_clob);

  WHILE l_offset <= l_length LOOP
    l_amount := LEAST(c_chunk_chars, l_length - l_offset + 1);

    DBMS_LOB.READ(
      lob_loc => l_clob,
      amount  => l_amount,
      offset  => l_offset,
      buffer  => l_buffer
    );

    -- Xử lý l_buffer tại đây, ví dụ chuyển cho bộ phân tích văn bản.
    DBMS_OUTPUT.PUT_LINE('Read characters: ' || l_amount);

    l_offset := l_offset + l_amount;
  END LOOP;
END;
/
~~~

### Đọc BLOB

~~~sql
DECLARE
  l_blob   BLOB;
  l_buffer RAW(32767);
  l_length NUMBER;
  l_offset NUMBER := 1;
  l_amount BINARY_INTEGER;
  c_chunk_bytes CONSTANT PLS_INTEGER := 32767;
BEGIN
  SELECT binary_content
    INTO l_blob
    FROM document_store
   WHERE document_id = 1;

  IF l_blob IS NULL THEN
    RETURN;
  END IF;

  l_length := DBMS_LOB.GETLENGTH(l_blob);

  WHILE l_offset <= l_length LOOP
    l_amount := LEAST(c_chunk_bytes, l_length - l_offset + 1);

    DBMS_LOB.READ(
      lob_loc => l_blob,
      amount  => l_amount,
      offset  => l_offset,
      buffer  => l_buffer
    );

    -- Xử lý l_buffer tại đây, ví dụ ghi vào luồng byte của ứng dụng.
    DBMS_OUTPUT.PUT_LINE('Read bytes: ' || l_amount);

    l_offset := l_offset + l_amount;
  END LOOP;
END;
/
~~~

Trong ví dụ CLOB, chunk được đặt là 8.000 ký tự để bộ đệm VARCHAR2 có đủ chỗ cho character set nhiều byte như AL32UTF8. Trong ví dụ BLOB, RAW được đọc tối đa 32.767 byte mỗi lần. Hãy chọn kích thước phù hợp với giới hạn bộ đệm và cách ứng dụng xử lý dữ liệu.

Không tăng offset theo kích thước chunk đã yêu cầu một cách cố định. Oracle có thể trả về ít hơn số lượng yêu cầu, chẳng hạn do giới hạn bộ đệm hoặc chuyển đổi ký tự. Dùng chính giá trị `l_amount` sau `READ` để cập nhật offset. Khi đọc theo vòng lặp dựa trên `GETLENGTH`, không cần cố đọc vượt quá cuối LOB.

## 6. Ghi mới CLOB và BLOB bằng WRITEAPPEND

Để ghi một LOB mới, có thể INSERT hàng với `EMPTY_CLOB()` và `EMPTY_BLOB()`, lấy locator bằng `RETURNING`, rồi ghi nội dung. Ví dụ:

~~~sql
DECLARE
  l_clob CLOB;
  l_blob BLOB;

  l_text VARCHAR2(1000) := 'Nội dung văn bản của tài liệu.';
  l_bytes RAW(32767) := UTL_RAW.CAST_TO_RAW('PDF hoặc byte mẫu');
BEGIN
  INSERT INTO document_store (
    document_id,
    title,
    text_content,
    binary_content
  )
  VALUES (
    2,
    'Tài liệu mới',
    EMPTY_CLOB(),
    EMPTY_BLOB()
  )
  RETURNING text_content, binary_content
       INTO l_clob, l_blob;

  DBMS_LOB.WRITEAPPEND(
    lob_loc => l_clob,
    amount  => LENGTH(l_text),
    buffer  => l_text
  );

  DBMS_LOB.WRITEAPPEND(
    lob_loc => l_blob,
    amount  => UTL_RAW.LENGTH(l_bytes),
    buffer  => l_bytes
  );

  COMMIT;
END;
/
~~~

Trong ví dụ:

- `RETURNING` lấy locator của hai LOB vừa được khởi tạo.
- Với CLOB, `LENGTH(l_text)` đếm số ký tự cần ghi.
- Với BLOB, `UTL_RAW.LENGTH(l_bytes)` đếm số byte cần ghi.
- `UTL_RAW.CAST_TO_RAW` chuyển văn bản theo character set của cơ sở dữ liệu thành byte. Đây chỉ là minh họa cho một chuỗi byte; khi lưu tệp thực tế, ứng dụng cần cung cấp byte gốc của tệp thay vì chuyển nội dung tệp thành chuỗi.

Các thay đổi trên LOB lưu trong bảng thuộc giao dịch hiện tại. `COMMIT` xác nhận thay đổi; `ROLLBACK` hủy các thay đổi chưa commit theo quy tắc giao dịch thông thường của Oracle.

## 7. Ghi hoặc ghi đè tại offset bằng WRITE

`DBMS_LOB.WRITE` ghi buffer bắt đầu tại offset được chỉ định. Nó ghi đè dữ liệu hiện có tại vùng đó; thao tác không chèn thêm byte hoặc ký tự làm dịch chuyển phần nội dung phía sau.

Ví dụ thay một đoạn đầu của CLOB:

~~~sql
DECLARE
  l_clob CLOB;
  l_text VARCHAR2(100) := 'HEADER';
BEGIN
  SELECT text_content
    INTO l_clob
    FROM document_store
   WHERE document_id = 1
   FOR UPDATE;

  IF l_clob IS NULL THEN
    RAISE_APPLICATION_ERROR(-20001, 'CLOB is NULL');
  END IF;

  DBMS_LOB.WRITE(
    lob_loc => l_clob,
    amount  => LENGTH(l_text),
    offset  => 1,
    buffer  => l_text
  );

  COMMIT;
END;
/
~~~

Với CLOB, `amount` và `offset` tính theo ký tự. Với BLOB, hai tham số này tính theo byte. Khi ghi vào một LOB đã tồn tại, cần khóa hàng chứa LOB bằng `SELECT ... FOR UPDATE` trong giao dịch trước khi sửa locator.

Nếu ghi một chuỗi ngắn hơn phần nội dung cũ, phần đuôi cũ vẫn còn. Ví dụ ghi `ABC` vào offset 1 của CLOB `ABCDEFGHIJ` sẽ tạo nội dung `ABCDEFGHIJ`, vì ba ký tự đầu được ghi đè bằng chính giá trị cũ. Nếu ghi `XYZ` thì kết quả là `XYZDEFGHIJ`, không phải `XYZ`. Muốn thay toàn bộ nội dung, hãy cắt LOB về 0 trước rồi ghi phần mới, hoặc dùng một câu UPDATE phù hợp.

## 8. Nối thêm nội dung: WRITEAPPEND và APPEND

Hai API có mục đích gần nhau nhưng nhận đầu vào khác nhau:

- `WRITEAPPEND(dest_lob, amount, buffer)`: nối một buffer VARCHAR2 hoặc RAW vào cuối LOB.
- `APPEND(dest_lob, src_lob)`: nối toàn bộ nội dung từ một LOB nguồn tương thích vào LOB đích.

Ví dụ nối thêm một đoạn văn bản:

~~~sql
DECLARE
  l_clob CLOB;
  l_text VARCHAR2(200) := CHR(10) || 'Phần bổ sung.';
BEGIN
  SELECT text_content
    INTO l_clob
    FROM document_store
   WHERE document_id = 1
   FOR UPDATE;

  DBMS_LOB.WRITEAPPEND(
    lob_loc => l_clob,
    amount  => LENGTH(l_text),
    buffer  => l_text
  );

  COMMIT;
END;
/
~~~

Ví dụ nối một CLOB nguồn vào CLOB đích:

~~~sql
DECLARE
  l_destination CLOB;
  l_source      CLOB;
BEGIN
  SELECT text_content
    INTO l_destination
    FROM document_store
   WHERE document_id = 1
   FOR UPDATE;

  SELECT text_content
    INTO l_source
    FROM document_store
   WHERE document_id = 2;

  DBMS_LOB.APPEND(l_destination, l_source);

  COMMIT;
END;
/
~~~

Đích phải là locator có thể ghi. Nguồn và đích phải có kiểu LOB tương thích. Nếu cần nối dữ liệu nhị phân, dùng BLOB với buffer RAW hoặc một BLOB nguồn.

## 9. Sao chép một đoạn bằng COPY

`DBMS_LOB.COPY` sao chép một số lượng byte hoặc ký tự từ LOB nguồn sang LOB đích. Có thể chỉ định vị trí bắt đầu ở nguồn và vị trí ghi ở đích.

~~~sql
DECLARE
  l_destination CLOB;
  l_source      CLOB;
  l_amount      NUMBER;
BEGIN
  SELECT text_content
    INTO l_destination
    FROM document_store
   WHERE document_id = 1
   FOR UPDATE;

  SELECT text_content
    INTO l_source
    FROM document_store
   WHERE document_id = 2;

  l_amount := LEAST(100, DBMS_LOB.GETLENGTH(l_source));

  IF l_amount > 0 THEN
    DBMS_LOB.COPY(
      dest_lob    => l_destination,
      src_lob     => l_source,
      amount      => l_amount,
      dest_offset => DBMS_LOB.GETLENGTH(l_destination) + 1,
      src_offset  => 1
    );
  END IF;

  COMMIT;
END;
/
~~~

Ví dụ trên nối tối đa 100 ký tự đầu tiên của CLOB nguồn vào cuối CLOB đích. Với BLOB, `amount`, `dest_offset` và `src_offset` tính theo byte. Nếu mục tiêu là thay toàn bộ nội dung đích, hãy dùng `TRIM(dest_lob, 0)` trước khi COPY; COPY không tự xóa phần đuôi cũ nếu dữ liệu mới ngắn hơn.

## 10. Cắt ngắn LOB bằng TRIM

`DBMS_LOB.TRIM` thay đổi độ dài LOB về số byte hoặc ký tự được chỉ định. Nó thường được dùng để xóa phần đuôi hoặc chuẩn bị LOB trước khi ghi lại toàn bộ nội dung.

~~~sql
DECLARE
  l_clob CLOB;
BEGIN
  SELECT text_content
    INTO l_clob
    FROM document_store
   WHERE document_id = 1
   FOR UPDATE;

  DBMS_LOB.TRIM(l_clob, 0);

  COMMIT;
END;
/
~~~

Sau `TRIM(l_clob, 0)`, CLOB vẫn là một LOB rỗng có locator; nó không trở thành NULL. Với BLOB, độ dài truyền vào được tính bằng byte. Không nhầm `TRIM` với `ERASE`: TRIM loại bỏ phần vượt quá độ dài mới ở cuối, còn ERASE xóa nội dung trong một vùng nhưng không nhất thiết làm LOB ngắn đi.

## 11. Tạo và giải phóng LOB tạm

LOB tạm (*temporary LOB*) hữu ích khi cần xây dựng hoặc biến đổi nội dung trung gian mà chưa ghi vào cột LOB của bảng. Dùng `DBMS_LOB.CREATETEMPORARY` để tạo locator và `DBMS_LOB.FREETEMPORARY` để giải phóng khi không còn dùng.

~~~sql
DECLARE
  l_temp_clob CLOB;
  l_text      VARCHAR2(100) := 'Temporary content';
BEGIN
  DBMS_LOB.CREATETEMPORARY(
    lob_loc => l_temp_clob,
    cache   => TRUE,
    dur     => DBMS_LOB.SESSION
  );

  DBMS_LOB.WRITEAPPEND(
    lob_loc => l_temp_clob,
    amount  => LENGTH(l_text),
    buffer  => l_text
  );

  DBMS_OUTPUT.PUT_LINE(
    'Temporary CLOB length: ' || DBMS_LOB.GETLENGTH(l_temp_clob)
  );

  IF DBMS_LOB.ISTEMPORARY(l_temp_clob) = 1 THEN
    DBMS_LOB.FREETEMPORARY(l_temp_clob);
  END IF;
EXCEPTION
  WHEN OTHERS THEN
    IF DBMS_LOB.ISTEMPORARY(l_temp_clob) = 1 THEN
      DBMS_LOB.FREETEMPORARY(l_temp_clob);
    END IF;
    RAISE;
END;
/
~~~

Tham số `dur` quyết định thời gian sống của LOB tạm: `DBMS_LOB.SESSION` giữ nó trong session, còn `DBMS_LOB.CALL` giới hạn theo lần gọi. Khi ứng dụng không còn cần locator, hãy giải phóng LOB tạm để tránh giữ tài nguyên lâu hơn cần thiết. Với code thực tế, cần bảo đảm nhánh dọn dẹp được chạy cả khi có ngoại lệ.

LOB tạm khác LOB persistent trong bảng. LOB persistent được quản lý cùng hàng và giao dịch; LOB tạm được tạo riêng cho công việc trung gian và có vòng đời do ứng dụng quản lý.

## 12. OPEN và CLOSE

`DBMS_LOB.OPEN` và `DBMS_LOB.CLOSE` cho phép mở LOB ở chế độ đọc hoặc đọc-ghi khi cần thực hiện nhiều thao tác. Việc mở không thay thế yêu cầu khóa hàng đối với LOB persistent cần sửa.

~~~sql
DECLARE
  l_clob CLOB;
  l_text VARCHAR2(100) := 'Additional text';
BEGIN
  SELECT text_content
    INTO l_clob
    FROM document_store
   WHERE document_id = 1
   FOR UPDATE;

  DBMS_LOB.OPEN(l_clob, DBMS_LOB.LOB_READWRITE);

  DBMS_LOB.WRITEAPPEND(
    lob_loc => l_clob,
    amount  => LENGTH(l_text),
    buffer  => l_text
  );

  DBMS_LOB.CLOSE(l_clob);
  COMMIT;
EXCEPTION
  WHEN OTHERS THEN
    IF l_clob IS NOT NULL AND DBMS_LOB.ISOPEN(l_clob) = 1 THEN
      DBMS_LOB.CLOSE(l_clob);
    END IF;
    RAISE;
END;
/
~~~

OPEN/CLOSE là tùy chọn cho nhiều trường hợp thao tác LOB thông thường. Khi đã mở LOB, hãy đóng nó trước khi kết thúc giao dịch. Nếu có exception, đóng LOB trong phần xử lý lỗi rồi phát sinh lại lỗi. Với một lần ghi đơn giản, có thể gọi trực tiếp WRITE hoặc WRITEAPPEND trên locator đã được khóa mà không cần OPEN/CLOSE.

## 13. Tìm kiếm và so sánh nội dung

Ngoài đọc và ghi, DBMS_LOB còn có các hàm hỗ trợ tìm kiếm:

- `INSTR(lob_loc, pattern, offset, nth)` tìm lần xuất hiện thứ `nth` của mẫu từ offset chỉ định. Với CLOB, vị trí tính theo ký tự; với BLOB, mẫu và vị trí tính theo byte.
- `COMPARE(lob_1, lob_2, amount, offset_1, offset_2)` so sánh nội dung của hai LOB hoặc hai đoạn LOB. Giá trị 0 cho biết hai đoạn được so sánh giống nhau; giá trị khác 0 cho biết khác nhau.

Ví dụ tìm chuỗi trong CLOB:

~~~sql
DECLARE
  l_clob CLOB;
  l_pos  INTEGER;
BEGIN
  SELECT text_content
    INTO l_clob
    FROM document_store
   WHERE document_id = 1;

  l_pos := DBMS_LOB.INSTR(l_clob, 'Oracle', 1, 1);

  IF l_pos = 0 THEN
    DBMS_OUTPUT.PUT_LINE('Text not found');
  ELSE
    DBMS_OUTPUT.PUT_LINE('Text found at character ' || l_pos);
  END IF;
END;
/
~~~

Nếu LOB lớn, hãy cân nhắc số lần tìm kiếm và kích thước vùng dữ liệu. `INSTR` tìm trong LOB theo mẫu được truyền vào; nó không thay thế một công cụ tìm kiếm toàn văn có chỉ mục và khả năng phân tích ngôn ngữ.

## 14. Quy tắc về offset, amount và kích thước buffer

Đây là phần dễ gây lỗi nhất khi thao tác LOB:

| Loại LOB | Offset | Amount | Buffer phổ biến |
|---|---|---|---|
| CLOB | Ký tự, bắt đầu từ 1 | Ký tự | VARCHAR2 |
| BLOB | Byte, bắt đầu từ 1 | Byte | RAW |

Một số nguyên tắc cần nhớ:

1. Offset trong DBMS_LOB bắt đầu từ 1, không phải 0.
2. CLOB tính offset và amount theo ký tự; BLOB tính theo byte.
3. Kích thước buffer PL/SQL bị giới hạn. VARCHAR2 và RAW trong PL/SQL có giới hạn tối đa 32.767 byte.
4. Với CLOB dùng character set nhiều byte, số ký tự có thể chiếm nhiều byte trong buffer. Vì vậy, chunk theo ký tự phải được chọn đủ nhỏ.
5. Với READ, cập nhật offset bằng amount thực tế được trả về sau mỗi lần đọc.
6. Không chuyển toàn bộ LOB lớn vào VARCHAR2 hoặc RAW chỉ để xử lý; hãy dùng vòng lặp theo chunk hoặc truyền locator cho tầng ứng dụng có khả năng stream.

Ngoài ra, không dùng `LENGTHB` để tính amount cho CLOB. `LENGTHB` đếm byte của chuỗi trong khi API CLOB yêu cầu đơn vị ký tự. Tương tự, không dùng `LENGTH` thay cho số byte khi ghi BLOB; với RAW, dùng `UTL_RAW.LENGTH`.

## 15. Lỗi thường gặp và cách phòng tránh

**Locator NULL:** gọi READ hoặc WRITE trên locator NULL không tương đương thao tác trên một LOB rỗng. Hãy kiểm tra NULL và khởi tạo LOB bằng EMPTY_CLOB/EMPTY_BLOB hoặc INSERT/UPDATE phù hợp.

**Không khóa hàng khi sửa LOB persistent:** khi sửa locator lấy từ một cột, hãy khóa hàng bằng `SELECT ... FOR UPDATE` trong giao dịch. Điều này giúp tránh cập nhật đồng thời không được kiểm soát.

**Nhầm ký tự với byte:** dùng LENGTHB cho CLOB hoặc LENGTH cho RAW có thể làm amount sai. Luôn chọn đơn vị theo loại LOB.

**Buffer quá lớn:** yêu cầu quá nhiều dữ liệu trong một lần READ hoặc SUBSTR có thể vượt giới hạn VARCHAR2/RAW. Chia nhỏ dữ liệu và tăng offset sau từng lần đọc.

**Ghi đè nhưng mong muốn chèn:** WRITE thay thế vùng dữ liệu tại offset, không dịch phần phía sau. Muốn nối, dùng WRITEAPPEND hoặc APPEND.

**Quên phần đuôi cũ:** ghi một đoạn ngắn ở đầu LOB không xóa phần còn lại. Nếu muốn thay toàn bộ, TRIM về 0 trước khi ghi hoặc thay locator bằng một LOB mới theo thiết kế phù hợp.

**Không giải phóng LOB tạm:** gọi FREETEMPORARY khi đã xử lý xong và cả trong nhánh ngoại lệ.

**Xử lý dữ liệu nhị phân như văn bản:** BLOB có thể chứa byte không hợp lệ với một character set. Không ép RAW sang VARCHAR2 để xử lý nếu chưa xác định encoding.

**In toàn bộ LOB bằng DBMS_OUTPUT:** DBMS_OUTPUT có giới hạn kích thước dòng và bộ đệm; đây không phải phương thức truyền tải nội dung lớn. Hãy chỉ in độ dài, đoạn nhỏ để debug hoặc chuyển dữ liệu sang tầng ứng dụng.

## 16. Giao dịch và lưu trữ LOB

LOB persistent nằm trong một hàng của bảng và chịu sự điều khiển của giao dịch. Nếu dùng `SELECT ... FOR UPDATE` để lấy locator rồi gọi WRITE, WRITEAPPEND, TRIM hoặc COPY, thay đổi sẽ được commit hoặc rollback cùng giao dịch chứa hàng đó.

Không nên commit giữa chừng chỉ để giải phóng bộ nhớ khi đang xây dựng một LOB persistent nếu điều đó làm sai ranh giới giao dịch nghiệp vụ. Hãy để tầng gọi quyết định thời điểm commit phù hợp.

Oracle hỗ trợ lưu trữ LOB bằng SecureFiles và BasicFiles tùy phiên bản, cấu hình và tablespace. SecureFiles là lựa chọn hiện đại cho nhiều hệ thống vì hỗ trợ các tính năng lưu trữ LOB nâng cao. Việc chọn cách lưu trữ, nén, khử trùng lặp, mã hóa và cache cần dựa trên đặc điểm dữ liệu, phiên bản Oracle và chính sách vận hành; nó không thay đổi nguyên tắc sử dụng locator và các API DBMS_LOB trong PL/SQL.

## 17. Mẫu xử lý tổng quát

Khi cần đọc hoặc ghi CLOB/BLOB, có thể triển khai theo trình tự sau:

1. Lấy locator từ cột LOB hoặc tạo LOB rỗng/tạm.
2. Kiểm tra locator có NULL hay không.
3. Với LOB persistent cần sửa, khóa hàng chứa LOB trong giao dịch.
4. Xác định đúng loại LOB để chọn buffer và đơn vị offset/amount.
5. Đọc bằng READ theo từng chunk, hoặc ghi bằng WRITE/WRITEAPPEND.
6. Nếu cần sao chép hoặc nối hai LOB, dùng COPY hoặc APPEND.
7. Đóng LOB nếu đã OPEN; giải phóng LOB tạm nếu đã tạo.
8. Commit hoặc rollback ở ranh giới giao dịch phù hợp.

Ví dụ, ứng dụng tải một tệp PDF lên có thể nhận byte từ HTTP request, tạo một hàng tài liệu với EMPTY_BLOB, lấy locator bằng RETURNING, ghi từng chunk RAW vào BLOB bằng WRITEAPPEND, rồi commit khi toàn bộ tệp đã được ghi thành công. Khi tải xuống, ứng dụng đọc BLOB theo chunk và gửi từng phần byte về client. Với nội dung mô tả hoặc JSON lớn, quy trình tương tự được áp dụng cho CLOB nhưng bộ đệm là VARCHAR2 và offset/amount được tính theo ký tự.

## 18. Kết luận

`DBMS_LOB` là API chính trong PL/SQL để thao tác có kiểm soát với CLOB và BLOB. CLOB lưu văn bản và dùng đơn vị ký tự; BLOB lưu byte nhị phân và dùng đơn vị byte. Locator cho phép đọc ghi trực tiếp trên LOB mà không cần đưa toàn bộ dữ liệu vào một biến PL/SQL.

Hãy dùng GETLENGTH và SUBSTR cho đoạn nhỏ, READ để đọc theo chunk, WRITE để ghi tại offset, WRITEAPPEND hoặc APPEND để nối, COPY để sao chép, TRIM để cắt ngắn và CREATETEMPORARY/FREETEMPORARY để quản lý dữ liệu trung gian. Khi sửa LOB persistent, cần khóa hàng phù hợp và quản lý giao dịch; khi dùng LOB tạm, phải giải phóng tài nguyên. Phân biệt chính xác ký tự với byte và chọn buffer đúng loại sẽ giúp tránh lỗi offset, amount và giới hạn bộ nhớ khi xử lý dữ liệu lớn.
