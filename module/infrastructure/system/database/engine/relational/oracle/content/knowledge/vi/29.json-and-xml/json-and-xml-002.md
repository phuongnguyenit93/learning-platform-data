# Kiểu JSON gốc và khác biệt theo phiên bản hỗ trợ

Oracle Database hỗ trợ xử lý JSON qua nhiều thế hệ phiên bản. Điểm thay đổi quan trọng nhất là sự xuất hiện của **kiểu dữ liệu SQL JSON gốc** trong Oracle Database 21c. Trước phiên bản này, JSON thường được lưu dưới dạng văn bản trong các cột VARCHAR2, CLOB hoặc BLOB và được xác nhận bằng điều kiện `IS JSON`. Từ 21c, có thể khai báo cột kiểu `JSON`; Oracle lưu nội dung theo định dạng nhị phân OSON để xử lý JSON hiệu quả hơn.

Khi chọn cách lưu JSON, cần phân biệt ba khái niệm:

1. **JSON dạng văn bản:** nội dung JSON được lưu trong VARCHAR2, CLOB hoặc BLOB. Ứng dụng và SQL/JSON functions đọc nội dung văn bản đó.
2. **Kiểu dữ liệu SQL JSON gốc:** kiểu `JSON` được giới thiệu trong Oracle Database 21c, lưu biểu diễn nhị phân OSON và bảo đảm giá trị cột là JSON hợp lệ.
3. **Các kiểu đối tượng JSON trong PL/SQL:** như `JSON_ELEMENT_T`, `JSON_OBJECT_T` và `JSON_ARRAY_T`, dùng để phân tích và thao tác cấu trúc JSON trong bộ nhớ. Đây là API lập trình, không phải kiểu cột SQL JSON gốc.

Hiểu đúng khác biệt giữa ba khái niệm giúp chọn kiểu cột phù hợp, viết truy vấn tương thích với phiên bản đang chạy và lập kế hoạch nâng cấp dữ liệu.

## 1. JSON dạng văn bản trước Oracle Database 21c

Ở các phiên bản trước 21c, Oracle không có kiểu dữ liệu SQL JSON chuyên biệt. Ứng dụng lưu tài liệu JSON trong một kiểu dữ liệu ký tự hoặc nhị phân:

| Kiểu cột | Cách sử dụng | Khi phù hợp |
|---|---|---|
| VARCHAR2 | Lưu JSON dạng văn bản có kích thước giới hạn | Tài liệu nhỏ, kích thước được kiểm soát |
| CLOB | Lưu JSON dạng ký tự với nội dung lớn | Tài liệu lớn, văn bản Unicode và nội dung cần xử lý như ký tự |
| BLOB | Lưu byte JSON, thông thường dùng UTF-8 | Dữ liệu nhận từ hệ thống khác dưới dạng byte hoặc cần giữ biểu diễn byte |

Để Oracle kiểm tra nội dung của cột có phải JSON hợp lệ hay không, dùng điều kiện `IS JSON` trong CHECK constraint:

~~~sql
CREATE TABLE orders_text (
  order_id NUMBER PRIMARY KEY,
  payload  CLOB
    CONSTRAINT orders_payload_is_json
    CHECK (payload IS JSON)
);
~~~

Nếu cần áp dụng cú pháp JSON nghiêm ngặt theo chuẩn JSON, có thể dùng `IS JSON STRICT`:

~~~sql
CREATE TABLE customer_documents (
  customer_id NUMBER PRIMARY KEY,
  document    CLOB
    CONSTRAINT customer_document_json
    CHECK (document IS JSON STRICT)
);
~~~

Oracle mặc định chấp nhận cú pháp JSON ở chế độ lax trong nhiều ngữ cảnh SQL/JSON. Dùng `STRICT` khi hệ thống cần xác nhận nội dung theo cú pháp JSON nghiêm ngặt. Hãy thống nhất chính sách này giữa constraint, ứng dụng và dữ liệu nhập từ các nguồn khác.

Ví dụ thêm tài liệu JSON:

~~~sql
INSERT INTO orders_text (order_id, payload)
VALUES (
  1001,
  '{"orderId":1001,"customer":"An","total":125.5,"status":"NEW"}'
);
~~~

Nếu chuỗi không phải JSON hợp lệ theo điều kiện của constraint, câu lệnh INSERT hoặc UPDATE sẽ thất bại. Constraint giúp ngăn dữ liệu sai định dạng đi vào bảng ngay cả khi dữ liệu được ghi bởi một ứng dụng khác.

### Truy vấn JSON văn bản

Các SQL/JSON functions cho phép đọc và biến đổi dữ liệu mà không cần tự tách chuỗi:

- `JSON_VALUE`: lấy một giá trị vô hướng như chuỗi, số hoặc ngày được chuyển đổi theo kiểu trả về.
- `JSON_QUERY`: lấy một object hoặc array JSON.
- `JSON_EXISTS`: kiểm tra đường dẫn có khớp dữ liệu hay không.
- `JSON_TABLE`: chiếu các thuộc tính JSON thành các cột và hàng quan hệ.

Ví dụ lấy mã đơn hàng, khách hàng và tổng tiền:

~~~sql
SELECT order_id,
       JSON_VALUE(payload, '$.customer' RETURNING VARCHAR2(100)) AS customer_name,
       JSON_VALUE(payload, '$.total' RETURNING NUMBER) AS total_amount
  FROM orders_text
 WHERE JSON_VALUE(payload, '$.status' RETURNING VARCHAR2(20)) = 'NEW';
~~~

Lấy một object con:

~~~sql
SELECT JSON_QUERY(payload, '$.shipping' WITH WRAPPER) AS shipping_json
  FROM orders_text
 WHERE order_id = 1001;
~~~

Kiểm tra một thuộc tính có tồn tại:

~~~sql
SELECT order_id
  FROM orders_text
 WHERE JSON_EXISTS(payload, '$.discount');
~~~

Chuyển một mảng JSON thành các hàng quan hệ:

~~~sql
SELECT o.order_id,
       item.product_id,
       item.quantity
  FROM orders_text o,
       JSON_TABLE(
         o.payload,
         '$.items[*]'
         COLUMNS (
           product_id NUMBER PATH '$.productId',
           quantity   NUMBER PATH '$.quantity'
         )
       ) item;
~~~

Như vậy, dù dữ liệu được lưu trong CLOB hoặc VARCHAR2, ứng dụng vẫn có thể dùng SQL để lọc, chiếu, nối và tổng hợp. Điểm hạn chế là dữ liệu được lưu dưới dạng văn bản, nên Oracle có thể phải phân tích biểu diễn văn bản khi xử lý.

## 2. Kiểu JSON gốc trong Oracle Database 21c

Oracle Database 21c giới thiệu kiểu dữ liệu SQL `JSON`. Thay vì khai báo một cột CLOB hoặc VARCHAR2 rồi thêm CHECK constraint, có thể khai báo trực tiếp:

~~~sql
CREATE TABLE orders_native (
  order_id NUMBER PRIMARY KEY,
  payload  JSON
);
~~~

Kiểu JSON gốc lưu tài liệu theo định dạng nhị phân **OSON** (*Optimized Binary JSON*). OSON là biểu diễn nội bộ được tối ưu cho Oracle Database; nó không phải chuỗi JSON UTF-8 để gửi trực tiếp sang một hệ thống bên ngoài.

Các lợi ích chính:

- Oracle biết kiểu dữ liệu của cột là JSON, không cần CHECK constraint `IS JSON` để xác nhận tính hợp lệ của giá trị.
- Biểu diễn OSON được tối ưu cho việc truy cập và xử lý các thuộc tính JSON.
- SQL/JSON functions có thể làm việc trực tiếp với giá trị kiểu JSON.
- Giảm nhu cầu phân tích lại văn bản JSON trong nhiều thao tác.
- Có thể dùng kiểu JSON trong SQL và PL/SQL ở các phiên bản hỗ trợ.

Ví dụ chèn một tài liệu vào cột JSON:

~~~sql
INSERT INTO orders_native (order_id, payload)
VALUES (
  1001,
  JSON('{"orderId":1001,"customer":"An","total":125.5,"status":"NEW"}')
);
~~~

Hàm dựng `JSON(...)` chuyển biểu diễn JSON đầu vào thành giá trị kiểu JSON. Cột JSON nhận một giá trị JSON đã được Oracle phân tích và lưu trữ theo dạng nội bộ.

Truy vấn bằng SQL/JSON vẫn quen thuộc:

~~~sql
SELECT order_id,
       JSON_VALUE(payload, '$.customer' RETURNING VARCHAR2(100)) AS customer_name,
       JSON_VALUE(payload, '$.total' RETURNING NUMBER) AS total_amount
  FROM orders_native
 WHERE JSON_VALUE(payload, '$.status' RETURNING VARCHAR2(20)) = 'NEW';
~~~

Điều này có nghĩa việc chuyển sang kiểu JSON gốc không làm mất mô hình truy vấn SQL/JSON. Thay đổi lớn nằm ở kiểu dữ liệu và cách Oracle biểu diễn dữ liệu bên trong.

## 3. OSON và JSON văn bản

JSON văn bản là biểu diễn dễ trao đổi giữa các hệ thống. Ví dụ:

~~~json
{
  "orderId": 1001,
  "customer": "An",
  "total": 125.5,
  "status": "NEW"
}
~~~

OSON là biểu diễn nhị phân nội bộ được Oracle tối ưu để lưu và truy cập JSON. Không nên xem byte OSON là nội dung JSON văn bản thông thường.

| Tiêu chí | JSON dạng văn bản | JSON gốc (OSON) |
|---|---|---|
| Biểu diễn lưu trữ | Ký tự hoặc byte JSON | Nhị phân OSON |
| Khả năng đọc trực tiếp bằng trình soạn thảo | Có, nếu giải mã đúng character set | Không phải dạng văn bản JSON thông thường |
| Kiểm tra tính hợp lệ | Thường dùng `IS JSON` constraint | Được bảo đảm bởi kiểu dữ liệu JSON |
| Trao đổi qua HTTP hoặc file JSON | Có thể gửi trực tiếp sau khi lấy văn bản | Cần serialize thành JSON văn bản |
| Xử lý thuộc tính | SQL/JSON phân tích nội dung văn bản | Oracle làm việc với biểu diễn nhị phân được tối ưu |

Khi cần xuất giá trị JSON gốc thành văn bản, dùng `JSON_SERIALIZE`:

~~~sql
SELECT JSON_SERIALIZE(
         payload
         RETURNING CLOB
         PRETTY
       ) AS payload_text
  FROM orders_native
 WHERE order_id = 1001;
~~~

Kết quả là JSON văn bản có thể gửi đến ứng dụng, ghi vào file hoặc trao đổi với hệ thống không hiểu OSON. Có thể chọn kiểu trả về phù hợp như VARCHAR2, CLOB hoặc BLOB theo yêu cầu của ứng dụng và phiên bản.

## 4. Kiểu JSON gốc khác với JSON_OBJECT_T

Một nhầm lẫn thường gặp là xem `JSON_OBJECT_T` như kiểu dữ liệu cột JSON gốc. Hai khái niệm này có mục đích khác nhau:

| Thành phần | Vai trò | Nơi sử dụng |
|---|---|---|
| `JSON` | Kiểu dữ liệu SQL lưu giá trị JSON, có biểu diễn OSON từ 21c | Cột bảng, biểu thức SQL và PL/SQL trong phiên bản hỗ trợ |
| `JSON_ELEMENT_T` | Kiểu cơ sở đại diện cho một phần tử JSON bất kỳ | PL/SQL |
| `JSON_OBJECT_T` | Đại diện cho JSON object, hỗ trợ đọc và sửa thuộc tính | PL/SQL |
| `JSON_ARRAY_T` | Đại diện cho JSON array, hỗ trợ thao tác phần tử | PL/SQL |

Các kiểu đối tượng PL/SQL này được giới thiệu từ Oracle Database 12.2, tức là có thể dùng chúng ngay cả khi database chưa hỗ trợ kiểu cột SQL JSON gốc. Chúng hỗ trợ phân tích văn bản, thao tác cấu trúc JSON trong bộ nhớ rồi chuyển kết quả trở lại dạng văn bản.

Ví dụ phân tích và cập nhật JSON bằng `JSON_OBJECT_T`:

~~~sql
DECLARE
  l_document JSON_OBJECT_T;
BEGIN
  l_document := JSON_OBJECT_T.parse(
    '{"orderId":1001,"customer":"An","status":"NEW"}'
  );

  DBMS_OUTPUT.PUT_LINE(
    'Customer: ' || l_document.get_string('customer')
  );

  l_document.put('status', 'PAID');
  l_document.put('verified', TRUE);

  DBMS_OUTPUT.PUT_LINE(l_document.to_string());
END;
/
~~~

Trong ví dụ:

- `parse` chuyển chuỗi JSON thành object trong bộ nhớ.
- `get_string` lấy thuộc tính customer dưới dạng VARCHAR2.
- `put` thêm hoặc thay thế thuộc tính.
- `to_string` serialize object về JSON văn bản.

Nếu cần cập nhật cột trong bảng, hãy ghi kết quả serialize vào cột VARCHAR2/CLOB/BLOB hoặc dùng giá trị kiểu JSON trong phiên bản hỗ trợ. Việc tạo một `JSON_OBJECT_T` trong PL/SQL không tự động thay đổi dữ liệu trong bảng.

## 5. Lịch sử hỗ trợ JSON theo phiên bản

Các phiên bản Oracle bổ sung khả năng JSON theo từng giai đoạn. Bảng dưới đây tóm tắt những mốc quan trọng đối với cách lưu và xử lý JSON:

| Phiên bản | Khả năng đáng chú ý | Kiểu lưu JSON |
|---|---|---|
| 12.1.0.2 | Bắt đầu hỗ trợ JSON trong SQL; `IS JSON`, các hàm truy vấn như JSON_VALUE, JSON_QUERY, JSON_EXISTS và JSON_TABLE | VARCHAR2, CLOB hoặc BLOB |
| 12.2 | Bổ sung các hàm tạo JSON, các kiểu đối tượng JSON trong PL/SQL và nhiều cải tiến SQL/JSON | Vẫn là VARCHAR2, CLOB hoặc BLOB |
| 18c | Tiếp tục mở rộng và hoàn thiện khả năng JSON của SQL/JSON | Vẫn là JSON văn bản trong các kiểu cột hiện có |
| 19c | Bổ sung và hoàn thiện nhiều khả năng JSON, được dùng rộng rãi trong hệ thống sản xuất | Không có kiểu dữ liệu SQL JSON gốc |
| 21c | Giới thiệu kiểu dữ liệu SQL `JSON` và lưu trữ nhị phân OSON; có thêm các thao tác JSON như JSON_TRANSFORM | Có thể dùng kiểu JSON gốc bên cạnh kiểu văn bản |
| 23c / 23ai | Tiếp tục mở rộng JSON; giới thiệu JSON Relational Duality Views để làm việc với dữ liệu quan hệ qua giao diện tài liệu JSON | Hỗ trợ kiểu JSON gốc và các kiểu văn bản |

### Oracle Database 12.1.0.2

Đây là mốc quan trọng khi Oracle đưa SQL/JSON vào Database. Dữ liệu vẫn được lưu trong các kiểu cột hiện có. Constraint `IS JSON` giúp xác nhận nội dung và các hàm SQL/JSON cho phép truy vấn cấu trúc.

Ở môi trường 12.1, không thể khai báo cột kiểu `JSON` như trong 21c. Nếu ứng dụng cần lưu JSON, hãy chọn VARCHAR2, CLOB hoặc BLOB và áp dụng constraint phù hợp.

### Oracle Database 12.2

12.2 mở rộng khả năng tạo JSON trong SQL và đưa các kiểu đối tượng JSON vào PL/SQL. Ứng dụng có thể tạo JSON bằng các hàm như `JSON_OBJECT`, `JSON_ARRAY`, `JSON_OBJECTAGG`, `JSON_ARRAYAGG`, đồng thời phân tích và sửa JSON bằng `JSON_OBJECT_T` hoặc `JSON_ARRAY_T`.

Các kiểu đối tượng PL/SQL giúp xử lý cấu trúc lồng nhau thuận tiện hơn, nhưng chưa thay thế kiểu cột văn bản. Cột lưu JSON vẫn là VARCHAR2, CLOB hoặc BLOB.

### Oracle Database 18c và 19c

Hai phiên bản này tiếp tục mở rộng SQL/JSON và các khả năng lập chỉ mục, truy vấn, sinh JSON. Tuy vậy, Oracle Database 19c vẫn chưa có kiểu dữ liệu SQL JSON gốc. Đây là điểm cần nhớ khi làm việc với hệ thống 19c: dù có thể dùng nhiều hàm JSON hiện đại, không thể dùng cú pháp cột `payload JSON` của 21c.

Với hệ thống 19c, một thiết kế phổ biến là lưu tài liệu lớn trong CLOB, thêm CHECK constraint `IS JSON`, rồi dùng SQL/JSON functions để truy vấn. Nếu cần thao tác trong PL/SQL, có thể dùng các kiểu `JSON_OBJECT_T` và `JSON_ARRAY_T`.

### Oracle Database 21c

21c giới thiệu kiểu SQL JSON gốc và OSON. Đây là thay đổi về mô hình lưu trữ chứ không chỉ là bổ sung một hàm truy vấn. Có thể dùng cột kiểu JSON, sau đó đọc thuộc tính bằng SQL/JSON functions và serialize khi cần trao đổi dưới dạng văn bản.

21c cũng bổ sung các thao tác cập nhật JSON như `JSON_TRANSFORM`, giúp thay đổi một phần tài liệu ngay trong SQL mà không cần ứng dụng tải toàn bộ tài liệu về, sửa chuỗi rồi ghi lại.

Ví dụ thay đổi trạng thái đơn hàng:

~~~sql
UPDATE orders_native
   SET payload = JSON_TRANSFORM(
                   payload,
                   SET '$.status' = 'PAID'
                 )
 WHERE order_id = 1001;
~~~

### Oracle Database 23c / 23ai

Dòng 23c, được phát hành rộng rãi dưới tên Oracle Database 23ai, tiếp tục mở rộng mô hình JSON. Một điểm đáng chú ý là **JSON Relational Duality Views**: ứng dụng có thể làm việc với một tài liệu JSON trong khi dữ liệu được lưu và quản lý trong các bảng quan hệ bên dưới.

Duality View không có nghĩa mọi dữ liệu JSON phải được lưu trong một cột CLOB hay một cột JSON duy nhất. Nó cung cấp một cách trình bày dữ liệu quan hệ dưới dạng tài liệu JSON, đồng thời hỗ trợ các thao tác đọc và ghi theo mô hình tài liệu. Cách tổ chức bảng, khóa, quan hệ và quyền ghi vẫn cần được thiết kế rõ ràng.

## 6. So sánh cùng một bài toán trên 19c và 21c trở lên

Giả sử ứng dụng cần lưu đơn hàng với mã, khách hàng, tổng tiền và trạng thái.

### Cách triển khai trên Oracle 19c

~~~sql
CREATE TABLE orders_19c (
  order_id NUMBER PRIMARY KEY,
  payload  CLOB
    CONSTRAINT orders_19c_payload_json
    CHECK (payload IS JSON)
);

INSERT INTO orders_19c (order_id, payload)
VALUES (
  1001,
  '{"customer":"An","total":125.5,"status":"NEW"}'
);

SELECT order_id,
       JSON_VALUE(payload, '$.customer' RETURNING VARCHAR2(100)) AS customer_name,
       JSON_VALUE(payload, '$.total' RETURNING NUMBER) AS total_amount
  FROM orders_19c;
~~~

Ở đây CLOB lưu văn bản JSON. Constraint kiểm tra dữ liệu và JSON_VALUE lấy các trường cần thiết.

### Cách triển khai trên Oracle 21c trở lên

~~~sql
CREATE TABLE orders_21c (
  order_id NUMBER PRIMARY KEY,
  payload  JSON
);

INSERT INTO orders_21c (order_id, payload)
VALUES (
  1001,
  JSON('{"customer":"An","total":125.5,"status":"NEW"}')
);

SELECT order_id,
       JSON_VALUE(payload, '$.customer' RETURNING VARCHAR2(100)) AS customer_name,
       JSON_VALUE(payload, '$.total' RETURNING NUMBER) AS total_amount
  FROM orders_21c;
~~~

Hai câu SELECT gần như giống nhau. Điểm khác nằm ở khai báo cột và cách nạp dữ liệu: 19c lưu văn bản trong CLOB và xác nhận bằng constraint; 21c có thể dùng kiểu JSON gốc.

## 7. Chọn VARCHAR2, CLOB, BLOB hay JSON?

Không phải mọi hệ thống đều cần chuyển sang kiểu JSON gốc. Hãy chọn kiểu cột theo kích thước tài liệu, phiên bản database, cách trao đổi dữ liệu và yêu cầu tương thích.

| Tiêu chí | VARCHAR2 | CLOB | BLOB | JSON gốc |
|---|---|---|---|---|
| Dữ liệu chính | Văn bản JSON nhỏ | Văn bản JSON lớn | Byte JSON, thường UTF-8 | JSON được Oracle quản lý |
| Giới hạn kích thước | Theo giới hạn VARCHAR2 của cấu hình | Phù hợp tài liệu lớn | Phù hợp dữ liệu byte lớn | Theo giới hạn của kiểu JSON và cấu hình Oracle |
| Đọc bằng trình soạn thảo | Có | Có | Cần giải mã UTF-8 | Cần serialize |
| Kiểm tra JSON | CHECK `IS JSON` | CHECK `IS JSON` | CHECK `IS JSON` với nội dung JSON hợp lệ | Kiểu dữ liệu tự bảo đảm JSON hợp lệ |
| Yêu cầu phiên bản | Có trong các phiên bản cũ | Có trong các phiên bản cũ | Có trong các phiên bản cũ | Oracle Database 21c trở lên |
| Tình huống thường gặp | Thuộc tính nhỏ, tài liệu ngắn | API payload, cấu hình, tài liệu lớn | Nhận hoặc lưu biểu diễn byte UTF-8 | Hệ thống mới cần xử lý JSON trực tiếp trong Oracle |

### Khi nên dùng VARCHAR2

Dùng VARCHAR2 khi tài liệu nhỏ, có kích thước giới hạn rõ ràng và ứng dụng cần lưu hoặc trao đổi nội dung dạng chuỗi. Cần xem xét `MAX_STRING_SIZE` và giới hạn kiểu VARCHAR2 của database. Không nên chọn VARCHAR2 chỉ vì dữ liệu JSON hiện tại đang ngắn nếu kích thước tài liệu có thể tăng đáng kể.

### Khi nên dùng CLOB

CLOB phù hợp khi JSON là nội dung văn bản lớn, có thể vượt giới hạn VARCHAR2 hoặc cần xử lý theo ngữ nghĩa ký tự. Đây là lựa chọn phổ biến cho Oracle 19c và các phiên bản cũ hơn khi cần lưu JSON lớn.

### Khi nên dùng BLOB

BLOB phù hợp khi ứng dụng làm việc với byte JSON, ví dụ nhận payload UTF-8 từ một hệ thống khác và cần giữ biểu diễn byte. Khi dùng BLOB để lưu JSON, nội dung phải dùng UTF-8 (AL32UTF8) theo yêu cầu của Oracle. BLOB không tự động giải mã byte thành ký tự cho ứng dụng.

### Khi nên dùng kiểu JSON gốc

Trên 21c trở lên, kiểu JSON gốc phù hợp khi ứng dụng truy vấn và cập nhật cấu trúc JSON thường xuyên trong database. OSON là biểu diễn nội bộ, giúp Oracle thao tác với các thuộc tính mà không cần coi tài liệu như một chuỗi văn bản trong mọi bước.

Nếu hệ thống phải tương thích với database hoặc client cũ, cần kiểm tra khả năng hỗ trợ kiểu JSON gốc trước khi đổi schema. Trong nhiều hệ thống, giữ CLOB và SQL/JSON functions vẫn là lựa chọn thực tế.

## 8. Chỉ mục và hiệu năng truy vấn JSON

Dù dữ liệu nằm trong CLOB hay kiểu JSON gốc, truy vấn JSON vẫn cần được thiết kế và đo hiệu năng. Nếu ứng dụng thường xuyên lọc theo một thuộc tính, có thể cân nhắc function-based index trên biểu thức JSON_VALUE.

Ví dụ với cột CLOB trên phiên bản hỗ trợ:

~~~sql
CREATE INDEX orders_text_status_ix
ON orders_text (
  JSON_VALUE(payload, '$.status' RETURNING VARCHAR2(20))
);
~~~

Truy vấn có biểu thức tương ứng:

~~~sql
SELECT order_id
  FROM orders_text
 WHERE JSON_VALUE(payload, '$.status' RETURNING VARCHAR2(20)) = 'NEW';
~~~

Với tài liệu có nhiều đường dẫn được tìm kiếm, Oracle còn hỗ trợ JSON search index. Cách tạo và khả năng cụ thể phụ thuộc phiên bản, kiểu cột và yêu cầu tìm kiếm. Không nên tạo chỉ mục chỉ vì cột có dữ liệu JSON; hãy xác định các đường dẫn và mẫu truy vấn thực tế.

Khi so sánh CLOB với JSON gốc, nên đo:

- Thời gian truy vấn các thuộc tính thường dùng.
- Chi phí cập nhật một thuộc tính trong tài liệu.
- Dung lượng lưu trữ và chỉ mục.
- Số lượng tài liệu, kích thước trung bình và kích thước lớn nhất.
- Tỷ lệ truy vấn trả về toàn bộ tài liệu so với truy vấn một vài thuộc tính.
- Chi phí serialize khi gửi dữ liệu sang ứng dụng.

OSON có thể cải thiện một số thao tác, nhưng không tự động làm mọi câu truy vấn nhanh hơn. Thiết kế đường dẫn, chỉ mục, selectivity và execution plan vẫn quan trọng.

## 9. Cập nhật JSON: sửa chuỗi, PL/SQL object hay JSON_TRANSFORM?

Có nhiều cách cập nhật nội dung JSON:

**Sửa văn bản ở ứng dụng:** phù hợp khi ứng dụng đã sở hữu toàn bộ tài liệu và cần ghi lại tài liệu sau khi thay đổi. Cần cẩn thận khi nhiều tiến trình cùng cập nhật vì có thể ghi đè thay đổi của nhau.

**Dùng JSON_OBJECT_T trong PL/SQL:** phù hợp khi cần thao tác cấu trúc lồng nhau, duyệt object hoặc array, áp dụng logic có điều kiện rồi serialize lại.

**Dùng JSON_TRANSFORM:** phù hợp khi muốn thay đổi một hoặc một số thuộc tính ngay trong SQL ở các phiên bản hỗ trợ, tránh chuyển tài liệu về ứng dụng chỉ để sửa một trường.

Ví dụ cập nhật trạng thái đơn hàng:

~~~sql
UPDATE orders_native
   SET payload = JSON_TRANSFORM(
                   payload,
                   SET '$.status' = 'PAID'
                 )
 WHERE order_id = 1001;
~~~

Hãy kiểm tra kiểu giá trị JSON cần ghi. Boolean JSON là giá trị `true` hoặc `false`, khác với chuỗi văn bản `'true'`. Khi cập nhật thuộc tính kiểu boolean bằng SQL, cú pháp biểu thức phụ thuộc phiên bản và kiểu giá trị mà JSON_TRANSFORM nhận; cần đối chiếu tài liệu đúng release. Với dữ liệu quan trọng, nên kiểm tra kết quả bằng JSON_VALUE hoặc JSON_QUERY sau cập nhật.

## 10. Nâng cấp từ JSON văn bản lên kiểu JSON gốc

Khi nâng cấp database từ 19c lên 21c trở lên, không cần chuyển đổi mọi cột JSON ngay lập tức. Có thể thực hiện theo từng bước:

1. **Kiểm kê schema:** xác định cột VARCHAR2, CLOB và BLOB chứa JSON, các CHECK constraint, function-based index, JSON search index, view, trigger và ứng dụng phụ thuộc.
2. **Kiểm tra dữ liệu:** tìm các hàng không hợp lệ, xác định chính sách strict/lax và xử lý dữ liệu sai trước khi chuyển đổi.
3. **Xác nhận phiên bản và client:** kiểm tra database release, mức tương thích, driver JDBC/ODP.NET và các công cụ ETL, backup, export có hỗ trợ kiểu JSON gốc.
4. **Tạo cột JSON mới trong môi trường thử nghiệm:** có thể thêm một cột JSON bên cạnh cột văn bản để thử chuyển đổi và so sánh.
5. **Chuyển đổi dữ liệu:** chuyển nội dung văn bản hợp lệ thành giá trị JSON gốc bằng hàm dựng JSON phù hợp với phiên bản.
6. **Đối chiếu:** so sánh các giá trị nghiệp vụ qua JSON_VALUE/JSON_QUERY, số lượng hàng, dữ liệu NULL, mảng và object lồng nhau.
7. **Tạo lại chỉ mục và điều chỉnh SQL:** kiểm tra các biểu thức chỉ mục, truy vấn, view và thao tác ghi.
8. **Chuyển ứng dụng:** cập nhật cách bind/fetch dữ liệu nếu driver dùng API riêng cho kiểu JSON. Nếu ứng dụng cần văn bản, serialize về CLOB/VARCHAR2 hoặc BLOB theo giao diện.
9. **Triển khai có kiểm soát:** chuyển luồng ghi và đọc theo kế hoạch, theo dõi lỗi chuyển đổi, hiệu năng và dung lượng.

Ví dụ minh họa chuyển một cột CLOB sang cột JSON trên phiên bản hỗ trợ kiểu JSON:

~~~sql
ALTER TABLE orders_text
  ADD (payload_native JSON);

UPDATE orders_text
   SET payload_native = JSON(payload);

COMMIT;
~~~

Đoạn mã trên giả định toàn bộ giá trị khác NULL trong `payload` đều là JSON hợp lệ và database hỗ trợ hàm dựng JSON cùng kiểu dữ liệu JSON. Trong môi trường thực tế, hãy xử lý riêng các hàng NULL, dữ liệu không hợp lệ và các trường hợp chuyển đổi lỗi trước khi chạy cập nhật hàng loạt. Nên thử với bản sao dữ liệu và đo tác động giao dịch trước khi chuyển bảng lớn.

Sau khi xác nhận, có thể xuất nội dung văn bản bằng:

~~~sql
SELECT order_id,
       JSON_SERIALIZE(payload_native RETURNING CLOB) AS payload_text
  FROM orders_text;
~~~

Việc giữ cột văn bản trong giai đoạn chuyển đổi giúp so sánh và rollback dễ hơn. Chỉ xóa cột cũ sau khi mọi ứng dụng, báo cáo và quy trình tích hợp đã chuyển sang mô hình mới.

## 11. Tương thích giữa các phiên bản và hệ thống bên ngoài

Kiểu JSON gốc tạo ra một yêu cầu tương thích mới: database đích và client phải hiểu kiểu JSON. Oracle Database 19c không có kiểu SQL JSON gốc, vì vậy không thể giả định một schema có cột JSON từ 21c sẽ được triển khai nguyên trạng trên 19c.

Khi trao đổi dữ liệu giữa các môi trường:

- Nếu cả nguồn và đích đều hỗ trợ kiểu JSON gốc, có thể dùng cơ chế chuyển dữ liệu tương thích với phiên bản và công cụ đang dùng.
- Nếu đích là phiên bản cũ, serialize giá trị JSON gốc thành JSON văn bản rồi nạp vào CLOB/VARCHAR2/BLOB có CHECK constraint phù hợp.
- Khi gửi qua HTTP, message queue hoặc file, gửi JSON văn bản theo encoding đã thống nhất, thường là UTF-8.
- Không gửi byte OSON như thể đó là JSON văn bản.
- Kiểm tra driver có hỗ trợ bind và fetch kiểu JSON hay cần nhận dữ liệu dưới dạng CLOB/VARCHAR2.
- Kiểm tra Data Pump, database link, ETL và công cụ quản trị theo đúng cặp phiên bản nguồn/đích; khả năng tương thích không chỉ phụ thuộc câu SQL.

Nếu hệ thống có nhiều phiên bản Oracle cùng hoạt động, một hợp đồng API trao đổi bằng JSON văn bản thường dễ tương thích hơn việc yêu cầu tất cả các bên hiểu OSON. Database có thể dùng kiểu lưu trữ nội bộ phù hợp, sau đó serialize tại ranh giới tích hợp.

## 12. Những hiểu lầm thường gặp

**Có JSON_OBJECT_T nghĩa là database đã có kiểu cột JSON:** không đúng. JSON_OBJECT_T là kiểu đối tượng PL/SQL, được hỗ trợ từ 12.2; kiểu SQL JSON gốc chỉ có từ 21c.

**Oracle 19c không hỗ trợ JSON:** không đúng. 19c hỗ trợ nhiều SQL/JSON functions, constraint IS JSON, các kiểu đối tượng PL/SQL và nhiều khả năng JSON khác. Điều 19c thiếu là kiểu dữ liệu SQL JSON gốc.

**CLOB có CHECK IS JSON giống hệt kiểu JSON gốc:** cả hai đều giúp bảo đảm nội dung là JSON hợp lệ, nhưng cách lưu trữ khác nhau. CLOB lưu văn bản; kiểu JSON gốc dùng biểu diễn nhị phân OSON.

**OSON là định dạng JSON để gửi qua REST:** không đúng. OSON là định dạng nhị phân nội bộ của Oracle. Khi trao đổi với hệ thống ngoài, hãy serialize thành JSON văn bản.

**Dùng kiểu JSON gốc sẽ tự động làm mọi truy vấn nhanh hơn:** không đúng. Hiệu năng còn phụ thuộc đường dẫn truy vấn, chỉ mục, kích thước tài liệu, execution plan và cách ứng dụng đọc dữ liệu.

**Mọi cột JSON cũ phải được chuyển đổi khi nâng cấp:** không bắt buộc. Cột VARCHAR2/CLOB/BLOB với IS JSON vẫn có thể tiếp tục hoạt động. Chuyển đổi nên dựa trên lợi ích và yêu cầu tương thích.

**JSON Relational Duality View thay thế hoàn toàn thiết kế quan hệ:** không đúng. Duality View cung cấp cách nhìn và thao tác dữ liệu quan hệ dưới dạng JSON; các bảng, khóa và ràng buộc quan hệ bên dưới vẫn đóng vai trò quan trọng.

## 13. Cách xác định khả năng hỗ trợ trong môi trường đang chạy

Trước khi dùng cú pháp hoặc kiểu dữ liệu mới, hãy xác nhận phiên bản database:

~~~sql
SELECT *
  FROM product_component_version;
~~~

Hoặc xem thông tin phiên bản trong `V$VERSION` nếu tài khoản có quyền truy cập:

~~~sql
SELECT banner
  FROM v$version;
~~~

Sau đó đối chiếu tài liệu Oracle đúng phiên bản và Release Update đang cài đặt. Cần kiểm tra:

- Kiểu dữ liệu JSON có được hỗ trợ ở release đó không.
- Các hàm SQL/JSON và cú pháp được dùng có tồn tại không.
- PL/SQL JSON object types có hỗ trợ phương thức cần dùng không.
- Các tính năng như JSON_TRANSFORM hoặc JSON Relational Duality Views có được hỗ trợ không.
- Client driver và công cụ triển khai có hiểu kiểu dữ liệu mới không.
- Cấu hình tương thích database và chính sách vận hành có cho phép sử dụng tính năng đó không.

Không nên suy ra khả năng hỗ trợ chỉ từ tên phiên bản lớn. Release Update, cấu hình và nền tảng triển khai có thể ảnh hưởng đến tính năng cụ thể.

## 14. Quy trình lựa chọn cho dự án

Khi bắt đầu thiết kế một bảng chứa JSON, có thể đi theo trình tự:

1. Xác định phiên bản Oracle thấp nhất mà hệ thống phải hỗ trợ.
2. Ước lượng kích thước tài liệu và tốc độ tăng dữ liệu.
3. Xác định ứng dụng cần thao tác bằng văn bản, byte hay cấu trúc JSON.
4. Chọn VARCHAR2 cho tài liệu nhỏ, CLOB cho văn bản lớn, BLOB cho byte JSON UTF-8 hoặc JSON gốc khi database hỗ trợ và ứng dụng được chuẩn bị.
5. Thiết lập kiểm tra JSON cho cột văn bản.
6. Chọn SQL/JSON functions hoặc PL/SQL JSON object types theo loại xử lý.
7. Thiết kế chỉ mục theo các đường dẫn được truy vấn thường xuyên.
8. Thử serialize, tích hợp, backup/restore và chuyển dữ liệu giữa các phiên bản.
9. Đo hiệu năng bằng dữ liệu đại diện trước khi chốt lựa chọn.

Ví dụ, một hệ thống đang chạy Oracle 19c và có nhiều ứng dụng cũ có thể tiếp tục lưu JSON trong CLOB với CHECK IS JSON. Khi nâng cấp lên 21c hoặc mới hơn, nhóm phát triển có thể thử cột JSON gốc cho các bảng có truy vấn JSON nhiều, trong khi giữ CLOB cho những luồng tích hợp cần tương thích với hệ thống cũ.

## 15. Kết luận

Oracle hỗ trợ JSON từ 12.1.0.2 thông qua các kiểu cột văn bản và SQL/JSON functions. 12.2 bổ sung các hàm tạo JSON và kiểu đối tượng JSON trong PL/SQL. Các phiên bản 18c và 19c tiếp tục mở rộng khả năng JSON nhưng vẫn chưa có kiểu dữ liệu SQL JSON gốc. Từ 21c, có thể khai báo cột `JSON` và sử dụng biểu diễn nhị phân OSON. Dòng 23c/23ai tiếp tục mở rộng khả năng làm việc với tài liệu JSON, trong đó có JSON Relational Duality Views.

Khi thiết kế, hãy phân biệt kiểu JSON gốc với JSON lưu trong CLOB/VARCHAR2/BLOB và với các kiểu JSON_OBJECT_T/JSON_ARRAY_T trong PL/SQL. Chọn cách lưu theo phiên bản thấp nhất cần hỗ trợ, kích thước tài liệu, kiểu truy cập và yêu cầu tích hợp. JSON gốc là lựa chọn hữu ích trên phiên bản mới, nhưng JSON văn bản với SQL/JSON vẫn là phương án hợp lệ và cần thiết trong nhiều hệ thống tương thích ngược.
