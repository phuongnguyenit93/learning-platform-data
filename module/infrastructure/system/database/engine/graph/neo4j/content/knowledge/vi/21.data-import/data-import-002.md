# LOAD CSV: đọc tiêu đề, chuyển kiểu và xử lý giá trị thiếu

## 1. Bài toán: từ một bảng CSV thành property graph

Trong module **DATABASE_ENGINE_GRAPH_NEO4J**, Neo4j lưu dữ liệu bằng **node**, **relationship** và các **property** của chúng. Nhiều hệ thống có dữ liệu ban đầu ở dạng CSV xuất từ cơ sở dữ liệu quan hệ, hệ thống CRM, ERP hoặc kho dữ liệu. Trước khi tạo các node và liên kết, cần đọc đúng cột, chuyển chuỗi thành kiểu dữ liệu thích hợp, xử lý trường thiếu và ngăn dữ liệu không hợp lệ đi vào đồ thị.

Lệnh **LOAD CSV** của Cypher đọc các bản ghi CSV lần lượt và chuyển mỗi dòng thành một biến có thể dùng trong các mệnh đề như **WITH**, **WHERE**, **MERGE**, **CREATE** và **SET**. Bài học tập trung vào ba kỹ năng:

1. **Đọc CSV có hoặc không có tiêu đề**, lấy đúng trường theo tên hoặc vị trí.
2. **Chuyển kiểu** dữ liệu CSV, vốn chủ yếu được đọc dưới dạng chuỗi, sang số, boolean và ngày.
3. **Xử lý giá trị thiếu** theo quy tắc nghiệp vụ: bỏ dòng, thay mặc định, giữ nguyên dữ liệu cũ hoặc không tạo property.

Ví dụ dùng nhãn **ImportCustomer** để tách dữ liệu thực hành khỏi dữ liệu của ứng dụng thật. Các câu lệnh tạo dữ liệu chỉ nên chạy trên cơ sở dữ liệu **thử nghiệm**.

## 2. Chuẩn bị file CSV và xác định đường dẫn

Tạo file **customers.csv** có nội dung UTF-8:

~~~csv
customer_id,full_name,age,active,email,joined_on,credit_limit
C001,"Nguyễn, Văn An",29,true,an@example.com,2024-06-01,2500.50
C002,Trần Bình,,false,,,
C003,Phạm Chi,34,true,chi@example.com,2024-02-29,0
~~~

Ý nghĩa các cột:

| Cột | Giá trị ví dụ | Kiểu mong muốn trong Neo4j | Quy tắc |
|---|---|---|---|
| **customer_id** | C001 | STRING | Bắt buộc, định danh duy nhất; giữ chữ và số 0 đầu |
| **full_name** | Nguyễn, Văn An | STRING | Có thể thiếu, không đổi tên hiện có khi ô CSV rỗng |
| **age** | 29 | INTEGER | Rỗng thì không có hoặc giữ property; giá trị nhập phải không âm |
| **active** | true / false | BOOLEAN | Phân biệt **false** với thiếu dữ liệu |
| **email** | an@example.com | STRING | Tùy chọn; chuẩn hóa khoảng trắng |
| **joined_on** | 2024-06-01 | DATE | Chuỗi ngày ISO hợp lệ; để trống nếu chưa biết |
| **credit_limit** | 2500.50 | FLOAT trong ví dụ | Giá trị số; với tiền cần cân nhắc lưu đơn vị nhỏ nhất kiểu INTEGER |

Ở dòng C002, các ô **age**, **email**, **joined_on** và **credit_limit** không có giá trị. Ở dòng C003, **credit_limit = 0** là giá trị hợp lệ, **không** phải giá trị thiếu. Dấu ngoặc kép quanh **"Nguyễn, Văn An"** giữ dấu phẩy trong tên, không tách tên thành hai cột.

### 2.1. Đường dẫn file:/// và nơi thực sự đọc CSV

Với Neo4j tự quản lý, đặt file trong **thư mục import của máy chủ Neo4j**. Khi đó có thể gọi:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
RETURN row
LIMIT 3;
~~~

Đường dẫn **file:///customers.csv** được Neo4j xử lý ở **máy chủ database**, không phải thư mục đang mở của Neo4j Browser, Java Driver hay trình duyệt của người dùng. Theo cấu hình mặc định, vị trí tương ứng là thư mục **import** được chỉ định bằng **server.directories.import**. Khả năng đọc file cục bộ còn phụ thuộc thiết lập **dbms.security.allow_csv_import_from_file_urls** và quyền đọc nguồn dữ liệu.

Với **Neo4j Aura**, không dùng **file:///...** để đọc file nằm trên máy cá nhân. Hãy đặt CSV ở một nguồn **HTTPS có thể truy cập từ môi trường Aura** và được cấp quyền, rồi thay URL trong truy vấn. Ví dụ minh họa:

~~~cypher
LOAD CSV WITH HEADERS
FROM 'https://example.org/data/customers.csv' AS row
RETURN row.customer_id
LIMIT 3;
~~~

URL ví dụ trên là **địa chỉ minh họa**, không phải tệp thật để chạy. Với nguồn thực tế, sử dụng HTTPS đáng tin cậy, quyền đọc phù hợp và tránh đưa thông tin xác thực nhạy cảm vào URL hoặc source code.

**Định dạng file:** Neo4j yêu cầu CSV ở **UTF-8**; dấu phân cách mặc định là dấu phẩy, dấu kết thúc dòng có thể là LF hoặc CRLF. Nên kiểm tra file trong trình soạn thảo hỗ trợ UTF-8 và tránh header có khoảng trắng, tên trùng hoặc ký tự vô hình từ quá trình xuất dữ liệu.

## 3. WITH HEADERS: lấy cột theo tên

Cú pháp cơ bản:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
RETURN
  row.customer_id AS id,
  row.full_name AS name,
  row.age AS rawAge,
  row.active AS rawActive
LIMIT 3;
~~~

Khi dùng **WITH HEADERS**, hàng đầu là tên cột và **không được xem là một bản ghi dữ liệu**. Mỗi dòng tiếp theo được đọc như một **map**, ví dụ dòng C001 tương đương về ý nghĩa với:

~~~text
{
  customer_id: "C001",
  full_name: "Nguyễn, Văn An",
  age: "29",
  active: "true",
  email: "an@example.com",
  joined_on: "2024-06-01",
  credit_limit: "2500.50"
}
~~~

**Chú ý:** các giá trị **"29"**, **"true"** và **"2500.50"** ở giai đoạn đọc CSV là **chuỗi**, chưa phải INTEGER, BOOLEAN hay FLOAT. Cypher không tự chuyển kiểu thuộc tính chỉ vì cột được đặt tên là **age** hoặc **active**.

### 3.1. Kiểm tra header trước khi import

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
RETURN
  keys(row) AS columnNames,
  row.customer_id AS sampleId,
  row.full_name AS sampleName,
  row.age AS sampleAge
LIMIT 3;
~~~

**keys(row)** cho biết những key có trong map của dòng CSV. Nếu header thực tế là **CustomerId** nhưng truy vấn dùng **row.customer_id**, Neo4j sẽ không tự đoán hai tên tương đương. Kiểm tra cách viết, chữ hoa/chữ thường và dấu cách ngay từ bước này.

### 3.2. CSV không có header

Nếu file **customers-no-header.csv** chứa:

~~~csv
C001,Nguyễn An,29
C002,Trần Bình,
~~~

thì đọc **không có WITH HEADERS**:

~~~cypher
LOAD CSV FROM 'file:///customers-no-header.csv' AS row
RETURN row[0] AS customerId,
       row[1] AS fullName,
       row[2] AS rawAge;
~~~

Khi đó mỗi dòng là **list** và cột được đánh chỉ số từ **0**. Nếu quên **WITH HEADERS** trong file có tiêu đề, dòng tiêu đề sẽ bị đọc thành dữ liệu và có thể gây lỗi chuyển kiểu hoặc tạo node rác.

### 3.3. File phân cách bằng dấu chấm phẩy

Với CSV dùng dấu **;** (thường gặp ở một số nguồn xuất dữ liệu):

~~~csv
customer_id;full_name;age
C001;"Nguyễn, Văn An";29
~~~

có thể khai báo:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customers-semicolon.csv'
AS row FIELDTERMINATOR ';'
RETURN row.customer_id, row.full_name, row.age;
~~~

**FIELDTERMINATOR** quyết định dấu ngăn cách các trường; nó không thay đổi cách truy cập header và không tự sửa file có dấu phân cách không nhất quán.

## 4. Chuyển chuỗi CSV thành kiểu dữ liệu có ý nghĩa

Với Neo4j property graph, định kiểu đúng giúp các truy vấn số học, so sánh, lọc và index hoạt động theo ngữ nghĩa mong đợi. Không nên lưu tuổi **"100"** và **"20"** dưới dạng chuỗi rồi kỳ vọng phép so sánh giống như trên số nguyên.

| Dữ liệu gốc | Biểu thức Cypher | Kết quả mong muốn | Lưu ý |
|---|---|---|---|
| "29" | **toInteger("29")** | INTEGER 29 | Không giữ dấu 0 đầu; ID nên là STRING |
| "2500.50" | **toFloat("2500.50")** | FLOAT 2500.5 | Dấu thập phân chuẩn là dấu chấm |
| "true" | **toBoolean("true")** | BOOLEAN true | Không nhầm chuỗi không rỗng với true |
| "false" | **toBoolean("false")** | BOOLEAN false | False là dữ liệu hợp lệ |
| "2024-02-29" | **date("2024-02-29")** | DATE 2024-02-29 | Chuỗi phải là ngày hợp lệ |
| Chuỗi có dấu cách hai bên | **trim(value)** | Chuỗi đã chuẩn hóa | Giữ nguyên khoảng trắng có ý nghĩa ở giữa |

### 4.1. Dùng nhóm hàm chuyển kiểu

~~~cypher
RETURN
  toInteger('29') AS age,
  toFloat('2500.50') AS creditLimit,
  toBoolean('false') AS active,
  date('2024-02-29') AS joinedOn;
~~~

Kết quả lần lượt có kiểu **INTEGER**, **FLOAT**, **BOOLEAN**, **DATE**. **date()** nhận một ngày hợp lệ theo định dạng mà hàm hỗ trợ; **date('2025-02-30')** không phải ngày thực và có thể làm truy vấn thất bại. Không biến một chuỗi ngày bất kỳ thành DATE mà không xác nhận định dạng nguồn.

### 4.2. Hàm OrNull hữu ích khi kiểm tra dữ liệu

~~~cypher
RETURN
  toIntegerOrNull('29') AS validAge,
  toIntegerOrNull('abc') AS invalidAge,
  toFloatOrNull('2500.50') AS validCredit,
  toBooleanOrNull('false') AS validActive,
  toBooleanOrNull('yes') AS invalidActive;
~~~

Kết quả kỳ vọng: **29**, **null**, **2500.5**, **false**, **null**. Các hàm **toIntegerOrNull**, **toFloatOrNull**, **toBooleanOrNull** trả **null** nếu không chuyển được. Chúng giúp xác định dữ liệu lỗi, nhưng **không** chứng minh rằng chuỗi ban đầu trống; **"abc"** và ô rỗng có thể cùng trở thành null sau chuyển kiểu.

Vì thế, phải phân biệt **thiếu dữ liệu** với **dữ liệu không hợp lệ** trước khi ghi. Nếu lặng lẽ thay mọi dữ liệu lỗi bằng null, quá trình import có thể báo thành công trong khi làm mất thông tin mà không ai hay biết.

### 4.3. Không chuyển mã định danh sang INTEGER một cách máy móc

Giá trị **"00042"** nếu dùng **toInteger()** sẽ thành **42**. Với mã khách hàng, mã bưu chính, số định danh bên ngoài hoặc mã đơn hàng, các ký tự đầu có thể có nghĩa. Chỉ chuyển thành INTEGER khi trường đó thật sự là số phục vụ tính toán.

Đối với số tiền, **FLOAT** có sai số nhị phân ở một số phép tính. Trong ứng dụng tài chính, thường nên lưu **số đơn vị nhỏ nhất kiểu INTEGER** hoặc một biểu diễn chính xác được thiết kế riêng cho nghiệp vụ, thay vì lấy FLOAT làm mặc định.

## 5. Giá trị thiếu: null, chuỗi rỗng và mặc định

Neo4j **không lưu một property có giá trị null**. Đặt một property thành null sẽ khiến property đó **không còn tồn tại** trên node/relationship. Trong CSV, một ô trống có thể được bộ đọc biểu diễn như chuỗi rỗng hoặc null tùy ngữ cảnh dữ liệu; hãy chuẩn hóa cả hai.

### 5.1. Chuẩn hóa ô rỗng và khoảng trắng

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
WITH row,
     trim(coalesce(row.customer_id, '')) AS customerId,
     trim(coalesce(row.age, '')) AS ageText,
     trim(coalesce(row.email, '')) AS emailText
RETURN customerId, ageText, emailText;
~~~

Giải thích:

- **coalesce(value, '')** thay null bằng chuỗi rỗng để có thể dùng các hàm xử lý chuỗi.
- **trim(...)** bỏ khoảng trắng ở **đầu và cuối** chuỗi.
- Sau chuẩn hóa, **ageText = ''** nghĩa là không có giá trị có thể sử dụng; **ageText = '0'** là một giá trị riêng, không bị coi là rỗng.

Không dùng phép thử chỉ dựa trên *truthiness* để xử lý giá trị boolean: **false** phải được giữ là false chứ không bị thay bằng mặc định.

### 5.2. Bốn chính sách cho trường thiếu

| Chính sách | Khi nào dùng | Ví dụ |
|---|---|---|
| **Bỏ dòng** | Thiếu khóa nghiệp vụ bắt buộc | Không nhập Customer có **customer_id** rỗng |
| **Gán mặc định** | Có quy tắc rõ ràng của domain | Không có trạng thái thì mặc định **pending**, nếu hợp lệ |
| **Bỏ qua property** | Giá trị thực sự chưa biết | Không tạo **email** khi trống |
| **Giữ giá trị cũ** | Nhập bổ sung từ file không đầy đủ | CSV thiếu **email** thì không xóa email có sẵn |

Hai chính sách cuối khác nhau khi dùng **MERGE** để import lại: “trường trống sẽ xóa dữ liệu hiện có” và “trường trống không thay đổi dữ liệu hiện có” là hai hợp đồng nghiệp vụ khác nhau, cần chọn rõ ràng.

### 5.3. CASE và coalesce không có cùng ý nghĩa

**Gán mặc định khi thiếu:**

~~~cypher
RETURN coalesce(null, 'unknown') AS value;
~~~

**Chỉ chuyển số khi ô không trống:**

~~~cypher
WITH ' 29 ' AS rawValue
WITH trim(coalesce(rawValue, '')) AS ageText
RETURN CASE
         WHEN ageText = '' THEN null
         ELSE toIntegerOrNull(ageText)
       END AS age;
~~~

Khi import vào một node đã tồn tại, tránh lệnh **SET c.email = null** nếu ý định là giữ email trước đó. Dùng biểu thức **CASE WHEN emailText = '' THEN c.email ELSE emailText END** để bảo toàn property cũ khi CSV không cung cấp giá trị.

## 6. Kiểm tra dữ liệu nguồn trước khi ghi

Một pipeline import tốt nên có bước **preview**, bước **phát hiện dòng lỗi**, sau đó mới **ghi dữ liệu**. Các truy vấn dưới dùng file **customers.csv** ở mục 2.

### 6.1. Preview số dòng và các giá trị

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
RETURN
  linenumber() AS csvLine,
  row.customer_id AS id,
  row.full_name AS name,
  row.age AS rawAge,
  row.active AS rawActive,
  row.joined_on AS rawDate
LIMIT 20;
~~~

**linenumber()** cho biết số dòng CSV đang đọc trong ngữ cảnh **LOAD CSV**, thuận tiện để đối chiếu file nguồn. Chạy **RETURN** để kiểm tra dữ liệu trước sẽ không tạo node.

### 6.2. Phát hiện khóa bắt buộc và trường số/boolean không hợp lệ

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
WITH linenumber() AS csvLine,
     trim(coalesce(row.customer_id, '')) AS customerId,
     trim(coalesce(row.age, '')) AS ageText,
     trim(coalesce(row.active, '')) AS activeText,
     trim(coalesce(row.credit_limit, '')) AS creditText
WITH csvLine,
     [msg IN [
       CASE WHEN customerId = '' THEN 'Thiếu customer_id' END,
       CASE WHEN ageText <> ''
                   AND toIntegerOrNull(ageText) IS NULL
            THEN 'age không phải số nguyên' END,
       CASE WHEN ageText <> ''
                   AND toIntegerOrNull(ageText) < 0
            THEN 'age âm' END,
       CASE WHEN activeText <> ''
                   AND toBooleanOrNull(toLower(activeText)) IS NULL
            THEN 'active không phải true/false' END,
       CASE WHEN creditText <> ''
                   AND toFloatOrNull(creditText) IS NULL
            THEN 'credit_limit không phải số' END
     ] WHERE msg IS NOT NULL] AS errors
WHERE size(errors) > 0
RETURN csvLine, errors
ORDER BY csvLine;
~~~

Với ba dòng mẫu hợp lệ, truy vấn trên trả **0 hàng**. Nếu có thêm một dòng với **age = abc** hoặc **active = yes**, truy vấn sẽ báo lỗi ở dòng tương ứng. **toIntegerOrNull('abc')** trả null nên cần kiểm tra riêng trường hợp **ageText <> ''**.

**Giới hạn của bước này:** truy vấn minh họa kiểm tra khóa, số và boolean, **chưa** kiểm tra ngày có tồn tại thật hay không, định dạng email, số hàng trùng định danh hoặc giới hạn nghiệp vụ trên số tiền. Ví dụ **2025-02-30** vẫn có thể lọt qua các điều kiện này rồi làm **date()** thất bại ở bước import. Hãy xác nhận ngày ISO, trùng ID và những quy tắc khác trong bước làm sạch nguồn hoặc quy trình kiểm tra bổ sung trước khi ghi.

## 7. Import hoàn chỉnh với MERGE và xử lý trường thiếu

### 7.1. Tạo constraint cho khóa nghiệp vụ

Chạy một lần trên database thử nghiệm:

~~~cypher
CREATE CONSTRAINT import_customer_id_unique IF NOT EXISTS
FOR (c:ImportCustomer)
REQUIRE c.customerId IS UNIQUE;
~~~

Constraint ngăn nhiều node **ImportCustomer** có cùng **customerId** không-null. Nó còn tạo index hỗ trợ tìm node cho **MERGE**. Tuy vậy, constraint duy nhất **không tự bắt buộc mọi node phải có thuộc tính customerId**; nếu cần cả tính tồn tại, phải chọn loại constraint phù hợp với edition và phiên bản, đồng thời bảo vệ đầu vào bằng truy vấn.

### 7.2. Ghi dữ liệu, giữ property cũ khi CSV để trống

Giả định file đã được kiểm tra như mục 6, đặc biệt các giá trị **joined_on** không rỗng đều là ngày ISO hợp lệ:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
WITH
  trim(coalesce(row.customer_id, '')) AS customerId,
  trim(coalesce(row.full_name, '')) AS fullName,
  trim(coalesce(row.age, '')) AS ageText,
  trim(coalesce(row.active, '')) AS activeText,
  trim(coalesce(row.email, '')) AS emailText,
  trim(coalesce(row.joined_on, '')) AS joinedText,
  trim(coalesce(row.credit_limit, '')) AS creditText
WHERE customerId <> ''
  AND (ageText = '' OR toIntegerOrNull(ageText) IS NOT NULL)
  AND (activeText = '' OR toBooleanOrNull(toLower(activeText)) IS NOT NULL)
  AND (creditText = '' OR toFloatOrNull(creditText) IS NOT NULL)
MERGE (c:ImportCustomer {customerId: customerId})
SET
  c.fullName = CASE WHEN fullName = ''
                    THEN c.fullName ELSE fullName END,
  c.age = CASE WHEN ageText = ''
               THEN c.age ELSE toIntegerOrNull(ageText) END,
  c.active = CASE WHEN activeText = ''
                  THEN c.active
                  ELSE toBooleanOrNull(toLower(activeText)) END,
  c.email = CASE WHEN emailText = ''
                 THEN c.email ELSE emailText END,
  c.joinedOn = CASE WHEN joinedText = ''
                    THEN c.joinedOn ELSE date(joinedText) END,
  c.creditLimit = CASE WHEN creditText = ''
                       THEN c.creditLimit ELSE toFloatOrNull(creditText) END;
~~~

Luồng xử lý:

1. **LOAD CSV WITH HEADERS** đọc từng dòng vào **row**.
2. **WITH** chuẩn hóa ô null/rỗng và bỏ dấu cách hai đầu.
3. **WHERE** loại dòng thiếu **customerId** hoặc không thể chuyển các trường số/boolean. Đây là **lọc để bảo vệ dữ liệu**, không thay thế báo cáo và lưu trữ bản ghi bị loại.
4. **MERGE** tìm hoặc tạo node theo **duy nhất customerId**. Không đưa **fullName** hoặc **email** vào khóa MERGE, vì các giá trị này có thể thay đổi theo thời gian.
5. **SET + CASE** chuyển kiểu dữ liệu có sẵn và **giữ property hiện tại khi file để trống**.

Nếu database ban đầu chưa có ba khách hàng, kết quả mong đợi là ba node:

| customerId | age | active | joinedOn | creditLimit |
|---|---:|---|---|---:|
| C001 | 29 | true | 2024-06-01 | 2500.5 |
| C002 | *không có property* | false | *không có property* | *không có property* |
| C003 | 34 | true | 2024-02-29 | 0.0 |

Kiểm tra lại:

~~~cypher
MATCH (c:ImportCustomer)
RETURN c.customerId AS customerId,
       c.fullName AS fullName,
       c.age AS age,
       c.active AS active,
       c.email AS email,
       c.joinedOn AS joinedOn,
       c.creditLimit AS creditLimit
ORDER BY customerId;
~~~

**Cần hiểu giới hạn của đoạn import:** điều kiện WHERE loại một số dòng lỗi mà không tự ghi log reject; vì vậy phải **chạy truy vấn kiểm tra mục 6** hoặc quy trình validation trước đó và đối soát số bản ghi. Nó cũng không chặn tất cả giá trị trái nghiệp vụ (ví dụ tuổi quá lớn) hay chuỗi ngày sai lịch. Với sản phẩm thật, nên **từ chối file lỗi trước khi nhập** hoặc có bảng/bản ghi rejected rows riêng trong quy trình ingest.

### 7.3. Nếu ô trống nghĩa là xóa property

Một nghiệp vụ khác có thể yêu cầu file là **snapshot đầy đủ**, trong đó email trống có nghĩa là email đã được xóa khỏi nguồn. Khi đó có thể dùng:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
WITH trim(coalesce(row.customer_id, '')) AS customerId,
     trim(coalesce(row.email, '')) AS emailText
WHERE customerId <> ''
MATCH (c:ImportCustomer {customerId: customerId})
SET c.email = CASE
                WHEN emailText = '' THEN null
                ELSE emailText
              END;
~~~

**SET c.email = null** làm property **email biến mất** khỏi node, không lưu giá trị null. Đây là chính sách khác với truy vấn ở mục 7.2. Phải quyết định chính sách cùng chủ dữ liệu trước khi triển khai.

### 7.4. Nếu trường thiếu cần một giá trị mặc định

Ví dụ khi tạo node mới, nguồn rỗng **active** có thể được định nghĩa là **false**:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
WITH trim(coalesce(row.customer_id, '')) AS customerId,
     trim(coalesce(row.active, '')) AS activeText
WHERE customerId <> ''
MERGE (c:ImportCustomer {customerId: customerId})
ON CREATE SET
  c.active = CASE
               WHEN activeText = '' THEN false
               ELSE toBooleanOrNull(toLower(activeText))
             END;
~~~

**ON CREATE SET** chỉ thực hiện khi **MERGE tạo node mới**. Trong ví dụ, nếu node đã tồn tại thì lệnh này không thay đổi active. Gán mặc định **false** cho thiếu dữ liệu là **quyết định nghiệp vụ**, không phải quy tắc tự động của LOAD CSV. Ngoài ra, cần validation để chuỗi **yes/no** hoặc **unknown** không bị chuyển ngầm thành null.

## 8. LOAD CSV trên dữ liệu lớn: batch, tính lặp lại và hiệu năng

### 8.1. Vì sao nên chia transaction?

Một import với hàng trăm nghìn hoặc hàng triệu dòng trong **một** transaction có thể giữ nhiều thay đổi chưa commit, tăng áp lực bộ nhớ, thời gian khóa và chi phí rollback nếu gặp lỗi. Neo4j hỗ trợ **CALL { ... } IN TRANSACTIONS** để chia dòng đầu vào thành các nhóm transaction nhỏ hơn.

Ví dụ dưới dùng **variable scope clause** với dạng **CALL (row, customerId)**, được hỗ trợ từ **Neo4j 5.23**. Đoạn này chỉ cập nhật tên để minh họa cấu trúc batch; nếu cần toàn bộ thuộc tính, áp dụng phần chuẩn hóa/chuyển kiểu từ mục 7 trong subquery.

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
WITH row, trim(coalesce(row.customer_id, '')) AS customerId
WHERE customerId <> ''
CALL (row, customerId) {
  MERGE (c:ImportCustomer {customerId: customerId})
  SET c.fullName = CASE
    WHEN trim(coalesce(row.full_name, '')) = ''
    THEN c.fullName
    ELSE trim(row.full_name)
  END
} IN TRANSACTIONS OF 1000 ROWS;
~~~

**Quan trọng khi chạy:** **CALL { ... } IN TRANSACTIONS** cần được gọi trong **implicit transaction**. Trong Neo4j Browser, dùng lệnh **:auto** cho câu truy vấn; trong Java Driver, chạy bằng **session.run(...)** và tiêu thụ kết quả, không bọc nó vào callback **executeWrite(...)** hay transaction tự mở. Với ứng dụng dùng Spring Data Neo4j, không lồng truy vấn import kiểu này trong một transaction do **@Transactional** đang mở.

Với phiên bản Cypher cũ hơn chưa hỗ trợ dạng **CALL (row, customerId)**, có thể dùng cú pháp importing **WITH** trong subquery:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
WITH row, trim(coalesce(row.customer_id, '')) AS customerId
WHERE customerId <> ''
CALL {
  WITH row, customerId
  MERGE (c:ImportCustomer {customerId: customerId})
  ON CREATE SET c.fullName = row.full_name
} IN TRANSACTIONS OF 1000 ROWS;
~~~

Cú pháp **CALL { WITH ... } IN TRANSACTIONS** được dùng trong các phiên bản hỗ trợ batching trước khi có variable scope clause; một số dạng cũ có cảnh báo deprecated trên server mới. Kiểm tra phiên bản Neo4j/Cypher thực tế và kế hoạch nâng cấp trước khi chọn cú pháp.

### 8.2. Batch có thể commit một phần

Nếu batch đầu gồm 1.000 dòng đã **commit** và batch thứ hai gặp lỗi ngày tháng, Neo4j **không tự rollback** batch đầu. Vì vậy:

- **MERGE theo khóa định danh có constraint** giúp chạy lại import mà không tạo trùng node theo ID.
- Các trường **SET** phải có quy tắc ghi đè/giữ nguyên nhất quán. Nếu hai dòng CSV có cùng ID nhưng giá trị khác nhau, cần giải quyết xung đột ở nguồn.
- Lưu nhật ký số bản ghi đọc, hợp lệ, bị loại, tạo mới, cập nhật và lỗi ở hệ thống ingest.
- Chọn kích thước batch theo đo đạc, chẳng hạn thử **500**, **1.000**, **5.000** dòng và quan sát bộ nhớ, độ trễ, thông lượng; không có cỡ batch tối ưu cho mọi graph.

**USING PERIODIC COMMIT** là cú pháp nhập liệu cũ. Trong Neo4j hiện đại nên dùng **CALL { ... } IN TRANSACTIONS** cho trường hợp cần chia batch.

### 8.3. Quan hệ và nhiều file CSV

Khi import đồ thị từ bảng quan hệ, thường có hai lượt: (1) import các node và khóa nghiệp vụ; (2) đọc CSV liên kết, **MATCH** các node đích rồi **MERGE/CREATE relationship** phù hợp. Không nên **MERGE** cả cụm node–relationship phức tạp khi chưa bảo đảm endpoint có định danh rõ ràng.

Ví dụ nếu đã có node Customer và một file **customer_follows.csv** chứa cột **from_id,to_id**, một đoạn Cypher minh họa là:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customer_follows.csv' AS row
WITH trim(coalesce(row.from_id, '')) AS fromId,
     trim(coalesce(row.to_id, '')) AS toId
WHERE fromId <> '' AND toId <> ''
MATCH (a:ImportCustomer {customerId: fromId})
MATCH (b:ImportCustomer {customerId: toId})
MERGE (a)-[:IMPORT_FOLLOWS]->(b);
~~~

Nếu một endpoint không tồn tại, **MATCH** không trả hàng tương ứng; phải đối soát các liên kết bị bỏ qua. Tên loại **IMPORT_FOLLOWS** trong ví dụ chỉ có ý nghĩa thực hành.

## 9. Lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| **Couldn't load external resource** | File không nằm ở import dir, URL không truy cập được hoặc thiếu quyền | Kiểm tra file:/// theo server, cấu hình load, kết nối HTTPS, quyền |
| **row.customer_id** trả null | Header viết sai, khác hoa/thường, có khoảng trắng hoặc file không có header | RETURN **keys(row)** và dòng mẫu |
| Import tạo một node tên **"customer_id"** | Quên **WITH HEADERS** | Chuyển sang WITH HEADERS và xử lý dữ liệu rác |
| Tuổi, hạn mức được lưu dạng STRING | Dùng **row.age** hoặc **row.credit_limit** trực tiếp trong SET | Dùng **toIntegerOrNull**, **toFloatOrNull** sau validation |
| Boolean **false** biến thành thiếu dữ liệu | Logic xử lý null hoặc default quá rộng | Kiểm tra **activeText = ''** riêng với **'false'** |
| Thiếu khóa khiến MERGE lỗi | Đưa null vào property định danh của mẫu MERGE | Lọc **customerId <> ''** và báo rejected row |
| Giá trị **abc** trở thành null | Hàm OrNull chuyển giá trị lỗi về null | Kiểm tra riêng giá trị không rỗng nhưng chuyển không được |
| Truy vấn dừng ở **date()** | Chuỗi không đúng ngày lịch/định dạng | Chuẩn hóa ISO, kiểm tra ngày hợp lệ trước khi ghi |
| Import lại tạo node trùng | Dùng CREATE hoặc MERGE với nhiều property thay đổi, thiếu constraint | MERGE theo khóa ổn định và tạo uniqueness constraint |
| Batch lỗi nhưng một số node đã xuất hiện | Các batch trước đã commit | Kiểm tra batch, kết quả đối soát, thực hiện chạy lại an toàn |
| CSV có dấu **;** nhưng cột dồn thành một | Dấu phân cách không đúng | Dùng **FIELDTERMINATOR ';'** |

### 9.1. Checklist trước khi nạp production

1. Xác nhận encoding **UTF-8**, dấu phân cách, quote và số cột khớp header.
2. Xem mẫu bằng **LOAD CSV ... RETURN**; kiểm tra **keys(row)** và số dòng.
3. Xác định các cột **bắt buộc**, kiểu đích và chính sách cho null/chuỗi rỗng.
4. Dùng validation để phát hiện lỗi số, boolean, ngày tháng, định danh trùng và giá trị ngoài phạm vi.
5. Chuẩn bị index/constraint cho khóa MERGE; định nghĩa rõ cập nhật, xóa hoặc giữ property khi thiếu.
6. Chọn transaction batch phù hợp; chạy thử trên dữ liệu đại diện và đánh giá việc import có thể tiếp tục sau lỗi.
7. Đối soát số dòng nguồn, số dòng hợp lệ, số node/relationship và các giá trị quan trọng sau import.

## 10. Bài tập thực hành

**Bài 1 — Đọc header.** Cho CSV có các cột **customer_id,full_name,age**. Viết truy vấn dùng **WITH HEADERS** để trả cột theo tên, rồi viết lại truy vấn đọc đúng dữ liệu khi file **không có header**.

**Bài 2 — Giữ giá trị boolean.** Với ba chuỗi **"true"**, **"false"**, **""**, hãy chuyển sang boolean hoặc null. Giải thích vì sao không được xem false là tương đương thiếu dữ liệu.

**Bài 3 — Phát hiện dữ liệu lỗi.** Bổ sung các dòng có **age = abc**, **active = yes**, **customer_id rỗng** vào file nguồn thử nghiệm. Chạy câu truy vấn phát hiện lỗi mục 6.2 và giải thích lý do không nên chỉ dùng **toIntegerOrNull** rồi ghi ngay.

**Bài 4 — Snapshot và partial update.** Một node C001 đã có email, file nhập mới để trống email. Hãy viết hai truy vấn tương ứng với chính sách **giữ email cũ** và **xóa email**. Giải thích khác biệt của **SET property = null**.

**Bài 5 — Import nhiều lần.** Chạy lại truy vấn MERGE mục 7 trên file không đổi. Dự đoán số node có nhãn **ImportCustomer**. Sau đó thay tên một khách hàng và chạy lại; nêu điểm khác nhau giữa **MERGE theo ID** và **MERGE theo ID + fullName**.

**Bài 6 — Batch lỗi giữa chừng.** Batch đầu đã commit 1.000 dòng, batch hai gặp ngày không hợp lệ. Đề xuất cách xác định dòng lỗi, khôi phục nguồn và chạy lại an toàn mà không tạo node trùng.

## 11. Ghi nhớ

**LOAD CSV WITH HEADERS** giúp truy cập trường bằng **tên cột**, còn cú pháp không có headers dùng **chỉ số cột**. Giá trị CSV cần được **chuẩn hóa**, **xác thực** và **chuyển kiểu có chủ đích** trước khi đưa vào property graph. Phải tách bạch **null**, **chuỗi rỗng**, **0**, **false** và **giá trị không hợp lệ**, vì mỗi trường hợp có thể dẫn đến kết quả nghiệp vụ khác nhau.

Với dữ liệu lớn, hãy dùng **khóa định danh có constraint**, **MERGE** theo khóa ổn định, **batch transaction** và quy trình đối soát. Kết quả import đúng không chỉ là truy vấn chạy thành công, mà còn là **đúng số thực thể, đúng loại property và đúng chính sách xử lý dữ liệu thiếu**.

### Tài liệu chính thức

- [Neo4j Cypher Manual – LOAD CSV](https://neo4j.com/docs/cypher-manual/current/clauses/load-csv/)
- [Neo4j Getting Started – Import CSV data using LOAD CSV](https://neo4j.com/docs/getting-started/data-import/csv-import/)
- [Neo4j Getting Started – Working with CSV files](https://neo4j.com/docs/getting-started/data-import/csv-files/)
- [Neo4j Cypher Manual – Scalar functions and type conversion](https://neo4j.com/docs/cypher-manual/current/functions/scalar/)
- [Neo4j Cypher Manual – CALL subqueries in transactions](https://neo4j.com/docs/cypher-manual/current/subqueries/subqueries-in-transactions/)
- [Neo4j Cypher Manual – Constraint syntax](https://neo4j.com/docs/cypher-manual/current/constraints/syntax/)
