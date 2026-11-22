# JSON-Relational Duality và ranh giới với JSON_TABLE hoặc ORM trong Oracle

Oracle JSON-Relational Duality Views cung cấp một giao diện JSON document trên dữ liệu được lưu trữ theo mô hình quan hệ. Ứng dụng có thể đọc một document JSON lồng nhau đại diện cho một thực thể nghiệp vụ, đồng thời thực hiện các thay đổi thông qua giao diện document đó. Các bảng quan hệ vẫn là nơi lưu trữ dữ liệu; primary key, foreign key, constraint và transaction của Oracle tiếp tục bảo vệ tính toàn vẹn.

Khái niệm “duality” thể hiện hai cách nhìn trên cùng dữ liệu: ứng dụng document-oriented nhìn thấy JSON document; ứng dụng relational nhìn thấy các bảng và quan hệ. Không cần duy trì hai bản sao dữ liệu độc lập rồi tự đồng bộ giữa chúng. Một thay đổi qua duality view được chuyển thành thay đổi trên các bảng nền theo mapping và quyền DML đã khai báo.

JSON_TABLE giải quyết một bài toán khác: lấy JSON đầu vào và chiếu các thuộc tính/mảng JSON thành hàng và cột quan hệ trong một truy vấn SQL. JSON_TABLE không tự tạo ra một giao diện document có thể cập nhật hai chiều cho cả mô hình dữ liệu. ORM lại hoạt động ở tầng ứng dụng: ánh xạ object/class sang bảng, quản lý quan hệ, change tracking và persistence. ORM không phải một database view và thường cần ứng dụng điều phối SQL hoặc unit of work.

Ba công nghệ có thể cùng xuất hiện trong một hệ thống:

- Duality View: cung cấp giao diện document JSON trên dữ liệu quan hệ và hỗ trợ đọc/ghi theo khả năng view.
- JSON_TABLE: biến JSON payload thành relational row sources để join, filter, aggregate hoặc load dữ liệu.
- ORM: ánh xạ mô hình domain/object của ứng dụng với database và quản lý persistence ở tầng application.

Bài học thuộc chủ đề **Tính năng mở rộng** của *Database Engine Relational Oracle*. Nội dung tập trung vào:

- Mô hình và mục tiêu của JSON-Relational Duality Views.
- Cách document JSON được ánh xạ vào bảng, primary key và foreign key.
- Đọc, insert, update, delete qua duality view.
- Quyền DML theo từng table trong view và optimistic concurrency.
- Phân biệt duality view với JSON_TABLE, JSON_VALUE và JSON_QUERY.
- Phân biệt database-native duality với ORM.
- Tích hợp REST/GraphQL và application APIs ở mức kiến trúc.
- Thiết kế schema, validation, transaction và performance.
- Giới hạn phiên bản, bảo mật, migration và bài thực hành.

## 1. JSON document và relational model

### Relational model

Trong mô hình quan hệ, dữ liệu được chia thành bảng và liên kết qua key. Ví dụ một đơn hàng và các dòng hàng:

~~~sql
CREATE TABLE customers (
    customer_id NUMBER PRIMARY KEY,
    customer_name VARCHAR2(200) NOT NULL,
    email VARCHAR2(320)
);

CREATE TABLE orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    order_date TIMESTAMP NOT NULL,
    status VARCHAR2(30) NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
);

CREATE TABLE order_items (
    order_item_id NUMBER PRIMARY KEY,
    order_id NUMBER NOT NULL,
    product_code VARCHAR2(50) NOT NULL,
    quantity NUMBER NOT NULL,
    unit_price NUMBER(12,2) NOT NULL,
    CONSTRAINT fk_order_items_order
        FOREIGN KEY (order_id)
        REFERENCES orders(order_id)
);
~~~

Một đơn hàng có một customer và nhiều order items. Relational model biểu diễn quan hệ bằng foreign key; ứng dụng thường join các bảng để lấy một đơn hàng hoàn chỉnh.

### Document model

Một API document-oriented có thể muốn trả về:

~~~json
{
  "_id": 9001,
  "orderDate": "2026-11-14T09:30:00Z",
  "status": "CONFIRMED",
  "customer": {
    "customerId": 42,
    "name": "An Nguyen",
    "email": "an@example.test"
  },
  "items": [
    {
      "itemId": 1,
      "productCode": "KB-01",
      "quantity": 2,
      "unitPrice": 25.50
    },
    {
      "itemId": 2,
      "productCode": "MS-03",
      "quantity": 1,
      "unitPrice": 18.00
    }
  ]
}
~~~

Document gom các thuộc tính và collection liên quan thành một cấu trúc lồng nhau. Nếu ứng dụng tự ghép document bằng nhiều SELECT, nó phải tự xử lý joins, nested arrays, insert/update/delete và transaction consistency.

### Duality nối hai cách nhìn

JSON-Relational Duality View định nghĩa mapping giữa relational tables và JSON document. Khi đọc view, Oracle trả về document theo cấu trúc được định nghĩa. Khi ghi qua view, Oracle ánh xạ thay đổi về các bảng nền trong phạm vi thao tác được phép.

~~~text
         Application / JSON API
                  |
             JSON document
                  |
       JSON-Relational Duality View
                  |
        Relational tables and keys
          /         |          \
      customers   orders    order_items
~~~

Duality view không đồng nghĩa lưu thêm một bản JSON độc lập cho mỗi đơn hàng. Dữ liệu quan hệ vẫn là nguồn dữ liệu được quản lý; document là giao diện logic.

## 2. JSON-Relational Duality View là gì?

JSON-Relational Duality View là một loại view database chuyên biệt, định nghĩa cách một hoặc nhiều bảng quan hệ được biểu diễn thành JSON document. Khác với view SQL thông thường trả về các cột phẳng, duality view trả về document JSON theo cấu trúc và quan hệ được khai báo.

### Mục tiêu thiết kế

- Cung cấp API document-oriented trên relational data.
- Giữ constraint, transaction và tính nhất quán của relational database.
- Tránh duplicate data chỉ để phục vụ JSON API.
- Cho phép ứng dụng dùng JSON mà không phải tự ghép nhiều bảng.
- Hỗ trợ đọc và DML document trong giới hạn mapping/view capabilities.
- Cho phép relational applications và document applications cùng làm việc trên dữ liệu nền.

### Hai hướng truy cập

| Hướng | Cách nhìn |
| --- | --- |
| Relational | SELECT/INSERT/UPDATE/DELETE trên bảng và quan hệ |
| Document | Đọc hoặc thay đổi JSON document qua duality view |

Hai hướng cùng thao tác lên dữ liệu nền. Nếu một ứng dụng cập nhật bảng ORDERS trực tiếp, document đọc qua duality view sẽ phản ánh thay đổi đó theo transaction visibility. Nếu ứng dụng cập nhật document qua duality view, các bảng liên quan sẽ nhận thay đổi tương ứng.

### Duality view không phải JSON collection độc lập

Một JSON collection lưu document theo mô hình document store. Duality view tạo document view trên relational tables. Hai mô hình có thể cùng dùng JSON API, nhưng khác nơi lưu dữ liệu, cách enforce relational constraints, cách ánh xạ DML và khả năng tương thích với ứng dụng SQL hiện có.

### Phiên bản và khả năng hỗ trợ

JSON-Relational Duality Views được giới thiệu trong dòng Oracle Database 23c, sau đó được thương mại hóa/đổi tên theo dòng Oracle Database 23ai. Khả năng cụ thể, cú pháp, giới hạn object/type, REST/GraphQL integration và availability trên dịch vụ cloud phụ thuộc release update, deployment model và service. Trước khi triển khai, kiểm tra tài liệu SQL Language Reference và JSON Developer's Guide đúng phiên bản.

Không suy ra rằng mọi phiên bản Oracle có JSON datatype hoặc JSON_TABLE đều hỗ trợ duality views. JSON support tồn tại từ các release cũ hơn; duality view là tính năng riêng.

## 3. Mapping document với relational tables

Một duality view mô tả document root và các thành phần con dựa trên quan hệ giữa bảng.

### Root table

Root table đại diện thực thể chính của document, ví dụ ORDERS. Mỗi root row tạo một document có định danh ổn định. Primary key thường được dùng để tạo trường document identifier.

### Nested table

Các bảng con như ORDER_ITEMS được biểu diễn thành nested object hoặc array tùy quan hệ và mapping. Một order có nhiều item nên document thường chứa array items.

### Parent-child relationship

Foreign key từ ORDER_ITEMS.ORDER_ID tới ORDERS.ORDER_ID cho phép Oracle hiểu mối quan hệ giữa root và child. Mapping phải xác định rõ key và cardinality để document không nhân bản hoặc ghép sai hàng.

### Shared/reference data

CUSTOMERS có thể được lồng vào document order hoặc biểu diễn theo mapping tham chiếu phù hợp. Khi một customer xuất hiện trong nhiều order, ứng dụng cần hiểu cập nhật customer qua một document có thể ảnh hưởng dữ liệu customer được chia sẻ bởi các document khác.

### Một row hay nhiều row?

- Root row thường định danh một document.
- Child rows có thể được gom thành array.
- Một-to-one relationship có thể trở thành nested object.
- Quan hệ nhiều-nhiều thường cần mapping qua bảng junction và phải xác định rõ semantics.
- Một bảng có thể tham gia nhiều duality views; cần hiểu phạm vi cập nhật và quyền của từng view.

### Primary key là nền tảng của identity

Primary key ổn định giúp Oracle nhận diện row khi document được cập nhật. Không dùng thuộc tính có thể thay đổi như tên, email hoặc mô tả làm document identity nếu không có lý do đặc biệt. Thay đổi key có thể ảnh hưởng document identity, foreign keys và client caching.

## 4. Cú pháp tạo duality view

Cú pháp tạo duality view sử dụng CREATE JSON RELATIONAL DUALITY VIEW cùng một SELECT JSON expression. SELECT mô tả JSON fields và các quan hệ nested; table references có thể khai báo quyền INSERT, UPDATE, DELETE được phép qua view.

Ví dụ minh họa theo cú pháp duality view của Oracle 23ai:

~~~sql
CREATE JSON RELATIONAL DUALITY VIEW order_dv AS
SELECT JSON {
    '_id' : o.order_id,
    'orderDate' : o.order_date,
    'status' : o.status,
    'customerId' : o.customer_id,
    'items' :
        [
            SELECT JSON {
                'itemId' : i.order_item_id,
                'productCode' : i.product_code,
                'quantity' : i.quantity,
                'unitPrice' : i.unit_price
            }
            FROM order_items i WITH INSERT UPDATE DELETE
            WHERE i.order_id = o.order_id
        ]
}
FROM orders o WITH INSERT UPDATE DELETE;
~~~

Đây là ví dụ giản lược để minh họa cấu trúc. Cần kiểm tra chính xác cú pháp, annotation, datatype mapping, nested query restrictions và privilege requirements trong SQL Language Reference của release đang dùng trước khi chạy. Nếu thêm customer object, cần định nghĩa nested relationship và quyền DML phù hợp trên CUSTOMERS.

### JSON object constructor

JSON { ... } tạo object với các field được định nghĩa. Tên JSON field có thể khác tên cột relational. Ví dụ:

- order_id -> _id
- order_date -> orderDate
- product_code -> productCode

Đây là mapping API; đổi tên JSON field không đổi tên cột trong bảng.

### Nested array

Subquery trong array expression tạo collection con, ví dụ items. Điều kiện liên kết phải dùng foreign key/primary key phù hợp. Nếu join sai, document có thể thiếu child hoặc lặp child.

### DML annotations

Các annotation INSERT, UPDATE và DELETE trên table references xác định loại thay đổi nào được phép qua duality view. Quyền thực tế còn phụ thuộc khả năng updatable của mapping, table constraints và privileges của database user.

Không cấp quyền DML rộng hơn nhu cầu API. Một view chỉ đọc có thể được thiết kế bằng cách không cho phép các thao tác ghi tương ứng.

### Kiểm tra view sau khi tạo

Kiểm tra object trong USER_OBJECTS/USER_VIEWS và dùng DESC hoặc dictionary views theo release. Thử SELECT document, xác minh JSON shape, key identity và nested array. Không đánh dấu view production-ready chỉ vì CREATE statement thành công.

## 5. Đọc document qua duality view

Ứng dụng có thể query duality view bằng SQL. Cách lấy document và tên cột trả về phụ thuộc định nghĩa view và release.

Ví dụ khái quát:

~~~sql
SELECT data
FROM order_dv
WHERE JSON_VALUE(data, '$._id') = '9001';
~~~

Một số duality view được expose với cột JSON document tên DATA; xác nhận metadata thực tế bằng DESC ORDER_DV hoặc dictionary. Predicate có thể được viết theo cách phù hợp với datatype và JSON view definition.

### Lọc theo key

Document identifier nên được dùng để truy xuất một document cụ thể. Đối với API, định nghĩa endpoint theo stable key và tránh phải parse toàn document chỉ để tìm root row nếu view cung cấp relational key/filter phù hợp.

### Lọc nested field

JSON_VALUE, JSON_EXISTS hoặc các JSON SQL operators có thể dùng để filter theo field document. Optimizer có thể đẩy predicate hoặc rewrite tùy view definition và release; kiểm tra execution plan cho workload quan trọng.

### Truy vấn nested arrays

Khi cần phân tích child items như relational rows, có thể dùng JSON_TABLE trên document được trả về. Tuy nhiên, nếu dữ liệu đã có relational table phù hợp, query trực tiếp bảng có thể đơn giản hơn và tránh serialize/parse JSON không cần thiết.

### Document size

Document lớn có thể bao gồm nhiều child rows. API nên cân nhắc pagination, projection và giới hạn payload. Không phải mọi endpoint đều cần trả toàn bộ nested collection cho một order.

## 6. Insert, update và delete qua duality view

Điểm nổi bật của duality view là khả năng thực hiện DML qua document interface. Oracle ánh xạ document changes về các bảng nền theo cấu trúc view, DML annotations, key relationships và constraints.

### Insert document

Một INSERT tạo document mới có thể tạo root row và các child rows theo nested document:

~~~sql
INSERT INTO order_dv (data)
VALUES (
    JSON('{
      "_id": 9002,
      "orderDate": "2026-11-14T10:00:00",
      "status": "NEW",
      "customerId": 42,
      "items": [
        {
          "itemId": 21,
          "productCode": "KB-01",
          "quantity": 1,
          "unitPrice": 25.50
        }
      ]
    }')
);
~~~

Ví dụ minh họa kiểu cột document và cách truyền JSON; xác nhận tên cột, JSON constructor và datatype binding của view trong release đang dùng. Tất cả required fields, primary keys, foreign keys, defaults và DML permissions phải hợp lệ. Nếu document thiếu field NOT NULL không có default, insert có thể thất bại.

### Update document

Một update có thể thay đổi một field trong document:

~~~sql
UPDATE order_dv
SET data = JSON_TRANSFORM(
    data,
    SET '$.status' = 'CONFIRMED'
)
WHERE JSON_VALUE(data, '$._id') = '9002';
~~~

Đây là dạng minh họa cho update document bằng JSON_TRANSFORM. Kiểm tra hỗ trợ DML syntax và JSON_TRANSFORM trên đúng release. Với duality view, mapping phải cho phép UPDATE đối với table/field được thay đổi.

### Delete document

~~~sql
DELETE FROM order_dv
WHERE JSON_VALUE(data, '$._id') = '9002';
~~~

Delete document có thể xóa root row và các child rows theo mapping/cascade semantics được định nghĩa và constraints. Không giả định mọi bảng nested đều tự động cascade; kiểm tra foreign key ON DELETE behavior, delete permissions và view definition.

### Transaction

DML qua duality view vẫn tham gia transaction Oracle:

~~~sql
UPDATE order_dv
SET data = JSON_TRANSFORM(
    data,
    SET '$.status' = 'SHIPPED'
)
WHERE JSON_VALUE(data, '$._id') = '9002';

-- Có thể thực hiện các DML khác trong cùng transaction.
COMMIT;
~~~

COMMIT làm thay đổi bền vững; ROLLBACK trước COMMIT có thể hủy DML chưa commit theo transaction semantics. Khác biệt quan trọng với DDL migration là DML qua duality view không tự tạo implicit commit.

### Không phải mọi JSON patch đều updatable

Một document có thể chứa field được tính toán, derived hoặc chỉ đọc. Nếu field không ánh xạ tới cột có thể cập nhật, Oracle có thể từ chối thay đổi. Cấu trúc nested, key mapping, table annotation và constraints giới hạn thao tác hợp lệ.

### Kiểm tra số hàng

Sau DML, kiểm tra SQL%ROWCOUNT trong PL/SQL hoặc số hàng affected từ driver. Với API, trả status phù hợp khi document không tồn tại, update không khớp hoặc conflict xảy ra. Không trả HTTP success chỉ vì request JSON parse thành công.

## 7. Quyền ghi theo từng bảng và ranh giới của view

Duality view có thể cho phép hoặc hạn chế thao tác DML ở các table references. Điều này giúp một document API chỉ cho phép cập nhật các phần dữ liệu đã được thiết kế.

### Root và child permissions

Ví dụ một order API có thể cho phép:

- INSERT/UPDATE root order.
- INSERT/UPDATE/DELETE order items.
- Chỉ đọc customer details.

Khi đó CUSTOMER data không nên được phép thay đổi chỉ vì customer object xuất hiện trong document. Quyền của từng table trong view cần được khai báo rõ.

### View capability không thay thế database privileges

Người dùng cần privilege phù hợp trên duality view và các quyền nền theo quy tắc Oracle. Các table DML annotations xác định capability của view; GRANT/REVOKE xác định user nào được truy cập view. Least privilege vẫn phải áp dụng.

### Read-only duality view

Nếu API chỉ đọc, không khai báo quyền ghi hoặc thiết kế view không updatable. Dùng user riêng cho read-only workload và không cấp UPDATE/INSERT/DELETE chỉ để tránh lỗi tích hợp.

### Không bypass constraints

DML qua duality view vẫn phải tuân thủ relational constraints trên bảng nền. Ví dụ foreign key, unique key, check constraint và NOT NULL vẫn bảo vệ dữ liệu. JSON document hợp lệ về cú pháp không có nghĩa dữ liệu hợp lệ theo nghiệp vụ.

### Shared child/reference data

Nếu document lồng thông tin customer, product hoặc account được chia sẻ bởi nhiều root documents, cập nhật object đó có thể tác động các document khác. Thiết kế API cần phân biệt embedded representation với ownership thực sự. Không cho phép update shared entity qua document root nếu nghiệp vụ không muốn quyền ghi lan sang entity dùng chung.

## 8. Optimistic concurrency và ETag

Nhiều client có thể đọc cùng một document rồi cập nhật gần như đồng thời. Nếu client B ghi sau client A mà không phát hiện dữ liệu đã thay đổi, update của A có thể bị ghi đè hoặc client B làm mất thay đổi mới.

### Optimistic concurrency

Optimistic concurrency cho phép nhiều client đọc song song, sau đó khi ghi kiểm tra document vẫn ở version mà client đã đọc. Nếu document đã đổi, update cũ bị từ chối để client đọc lại và hợp nhất thay đổi.

### ETag trong duality document

Duality view có thể cung cấp metadata ETag được Oracle tính từ dữ liệu document theo cơ chế của feature. ETag đại diện trạng thái document và hỗ trợ phát hiện thay đổi giữa lúc đọc và ghi. REST layer có thể sử dụng ETag/If-Match để thực hiện conditional update tùy API integration/version.

Luồng khái quát:

~~~text
Client A                  Database
   |                         |
   |---- GET document ------>|
   |<--- JSON + ETag --------|
   |                         |
Client B updates document    |
   |                         |
   |---- PUT with old ETag ->|
   |<--- conflict/stale -----|
   |                         |
Client A rereads latest      |
and merges intended change   |
   |                         |
   |---- conditional PUT --->|
   |<--- success + new ETag -|
~~~

### ETag không phải business version

ETag là token concurrency/representation; không nên dùng thay cho order version nghiệp vụ, audit sequence hoặc event number nếu ứng dụng cần các semantics đó. Có thể duy trì cột version riêng cho business logic.

### Xử lý conflict

Khi ETag không còn khớp:

1. Không retry nguyên payload cũ một cách mù quáng.
2. Đọc document mới nhất.
3. Xác định field nào do người khác thay đổi.
4. Merge theo business rule hoặc yêu cầu người dùng giải quyết.
5. Gửi update có điều kiện với ETag mới.

### Atomicity của document update

Một document có thể bao gồm nhiều bảng. DML qua duality view được xử lý trong transaction Oracle; nếu một constraint hoặc thao tác child thất bại, transaction cần rollback để không giữ một phần thay đổi ngoài ý muốn. Ứng dụng phải xử lý exception và commit boundary đúng cách.

## 9. JSON_TABLE: chiếu JSON thành hàng và cột

JSON_TABLE là SQL row source function. Nó nhận một biểu thức JSON (JSON column, CLOB/BLOB/VARCHAR2 có nội dung JSON hoặc JSON value phù hợp) cùng JSON path và trả về một tập hàng/cột quan hệ để SQL join, filter, aggregate hoặc insert vào bảng.

### Chiều dữ liệu

~~~text
JSON payload / JSON column
          |
       JSON_TABLE
          |
   Relational rows/columns
          |
 SELECT / JOIN / GROUP BY / INSERT
~~~

JSON_TABLE giải quyết câu hỏi: “Tôi có JSON và muốn xử lý các thuộc tính của nó như dữ liệu quan hệ trong SQL.” Duality view giải quyết câu hỏi: “Tôi có dữ liệu quan hệ và muốn cung cấp nó như một document JSON có cấu trúc, có thể cập nhật theo mapping.”

### Ví dụ JSON_TABLE cơ bản

~~~sql
SELECT jt.order_id,
       jt.status,
       jt.order_date
FROM inbound_orders src,
     JSON_TABLE(
         src.payload,
         '$'
         COLUMNS (
             order_id   NUMBER        PATH '$.orderId',
             status     VARCHAR2(30)  PATH '$.status',
             order_date TIMESTAMP     PATH '$.orderDate'
         )
     ) jt;
~~~

JSON_TABLE đọc payload của mỗi row trong INBOUND_ORDERS và trả về các cột relational. Kết quả có thể join với CUSTOMERS, filter theo STATUS hoặc insert vào bảng đích.

### NESTED PATH cho array

~~~sql
SELECT jt.order_id,
       jt.status,
       item.item_id,
       item.product_code,
       item.quantity
FROM inbound_orders src,
     JSON_TABLE(
         src.payload,
         '$'
         COLUMNS (
             order_id NUMBER PATH '$.orderId',
             status VARCHAR2(30) PATH '$.status',
             NESTED PATH '$.items[*]'
             COLUMNS (
                 item_id NUMBER PATH '$.itemId',
                 product_code VARCHAR2(50) PATH '$.productCode',
                 quantity NUMBER PATH '$.quantity'
             )
         )
     ) jt
CROSS APPLY JSON_TABLE(
    src.payload,
    '$.items[*]'
    COLUMNS (
        item_id NUMBER PATH '$.itemId',
        product_code VARCHAR2(50) PATH '$.productCode',
        quantity NUMBER PATH '$.quantity'
    )
) item;
~~~

Đoạn này chỉ minh họa khả năng nested projection; trong thực tế không cần đồng thời khai báo cùng array hai lần như ví dụ ghép trên. Dùng một JSON_TABLE với NESTED PATH khi cần giữ parent/child columns trong cùng row source, hoặc dùng CROSS APPLY riêng khi cần xử lý độc lập. Chọn một dạng phù hợp với output shape.

### Dạng nested projection thông dụng

~~~sql
SELECT jt.order_id,
       jt.status,
       jt.item_id,
       jt.product_code,
       jt.quantity
FROM inbound_orders src,
     JSON_TABLE(
         src.payload,
         '$'
         COLUMNS (
             order_id NUMBER PATH '$.orderId',
             status VARCHAR2(30) PATH '$.status',
             NESTED PATH '$.items[*]'
             COLUMNS (
                 item_id NUMBER PATH '$.itemId',
                 product_code VARCHAR2(50) PATH '$.productCode',
                 quantity NUMBER PATH '$.quantity'
             )
         )
     ) jt;
~~~

Kết quả thường có một hàng cho mỗi array element. Khi array rỗng hoặc thiếu, semantics của nested columns và parent row phụ thuộc JSON path/error handling; kiểm tra NULL/empty behavior theo yêu cầu.

### FOR ORDINALITY

JSON_TABLE có thể tạo cột số thứ tự array element:

~~~sql
SELECT jt.order_id,
       jt.item_position,
       jt.product_code
FROM inbound_orders src,
     JSON_TABLE(
         src.payload,
         '$'
         COLUMNS (
             order_id NUMBER PATH '$.orderId',
             NESTED PATH '$.items[*]'
             COLUMNS (
                 item_position FOR ORDINALITY,
                 product_code VARCHAR2(50) PATH '$.productCode'
             )
         )
     ) jt;
~~~

Ordinality hữu ích để giữ thứ tự trong array input. Nó không thay thế primary key ổn định cho item; vị trí có thể đổi khi client sắp xếp hoặc xóa phần tử.

### JSON_TABLE với DML

Một payload có thể được biến thành rows rồi insert vào bảng relational:

~~~sql
INSERT INTO order_stage (
    order_id,
    status,
    product_code,
    quantity
)
SELECT jt.order_id,
       jt.status,
       jt.product_code,
       jt.quantity
FROM inbound_orders src,
     JSON_TABLE(
         src.payload,
         '$'
         COLUMNS (
             order_id NUMBER PATH '$.orderId',
             status VARCHAR2(30) PATH '$.status',
             NESTED PATH '$.items[*]'
             COLUMNS (
                 product_code VARCHAR2(50) PATH '$.productCode',
                 quantity NUMBER PATH '$.quantity'
             )
         )
     ) jt;
~~~

JSON_TABLE ở đây là nguồn rows cho INSERT SELECT. Nó không tự cập nhật document gốc và không tự cung cấp duality semantics.

### Error handling và datatype conversion

JSON_TABLE hỗ trợ các lựa chọn ERROR ON ERROR, NULL ON ERROR, DEFAULT ... ON ERROR và các clause liên quan theo cú pháp JSON SQL. Chọn behavior rõ ràng:

- JSON path không tồn tại.
- Giá trị JSON có kiểu không chuyển được sang NUMBER/DATE/TIMESTAMP.
- Array element thiếu field bắt buộc.
- JSON malformed hoặc vi phạm format.
- Giá trị vượt precision/length của cột đích.

Không dùng NULL ON ERROR cho mọi field nếu NULL có thể che giấu dữ liệu lỗi. Với dữ liệu nghiệp vụ quan trọng, ưu tiên reject hoặc ghi error details vào quarantine table.

### JSON_VALUE và JSON_QUERY

- JSON_VALUE lấy scalar (string, number, date-like scalar theo conversion rules) từ JSON path.
- JSON_QUERY lấy object/array JSON theo path.
- JSON_TABLE lấy nhiều giá trị và nested arrays thành relational rowset.

Chúng có thể phối hợp trong cùng query; lựa chọn phụ thuộc số field, cardinality và output mong muốn.

## 10. ORM: ánh xạ object ở tầng ứng dụng

Object-relational mapper (ORM) ánh xạ các class/object trong ngôn ngữ lập trình sang relational tables và relationships. ORM thường quản lý entity identity, change tracking, lazy/eager loading, SQL generation, transaction scope và mapping datatype.

Ví dụ ứng dụng Java có thể có:

~~~java
class Order {
    Long id;
    Customer customer;
    List<OrderItem> items;
    OrderStatus status;
}
~~~

ORM map Order tới ORDERS, Customer tới CUSTOMERS và OrderItem tới ORDER_ITEMS. Khi application load Order, ORM có thể phát sinh một hoặc nhiều SQL queries để lấy root và related entities.

### ORM làm gì?

- Mapping class/property với table/column.
- Mapping one-to-one, one-to-many và many-to-many.
- Quản lý primary key và identity map.
- Theo dõi object changes và phát sinh INSERT/UPDATE/DELETE.
- Quản lý unit of work và transaction boundary.
- Hỗ trợ lazy/eager loading.
- Có thể cung cấp schema migration tooling.
- Chuyển đổi datatype giữa database và language runtime.

### ORM không phải database-native JSON view

ORM hoạt động trong process ứng dụng. Nó cần mapping metadata và runtime library. Nếu một ứng dụng khác không dùng cùng ORM, nó không tự động có cùng object model hoặc change tracking. ORM-generated SQL vẫn là SQL trên các bảng; database không nhất thiết biết object graph của ứng dụng.

### ORM và document API

Ứng dụng có thể serialize ORM entities thành JSON để trả REST API. Nhưng serialization không tự tạo ra database-native duality view. Application phải kiểm soát:

- Mapping JSON field names.
- Nested collection loading.
- Circular references.
- Lazy loading ngoài transaction.
- N+1 query problem.
- Optimistic locking/version fields.
- Validation và authorization.
- Partial updates và merge semantics.

### ORM có thể dùng duality view không?

Có thể, nhưng phụ thuộc ORM và driver có hỗ trợ mapping một JSON document column/value như một entity hoặc custom type hay không. ORM thường tối ưu cho row/entity mapping, trong khi duality view cung cấp document interface. Một kiến trúc có thể dùng ORM cho relational workflows và gọi duality view qua native SQL/JSON APIs cho document endpoints.

## 11. So sánh Duality View, JSON_TABLE và ORM

| Tiêu chí | JSON-Relational Duality View | JSON_TABLE | ORM |
| --- | --- | --- | --- |
| Tầng hoạt động | Database | SQL query engine | Application runtime |
| Chiều dữ liệu chính | Relational tables thành JSON document; DML document về relational rows | JSON thành relational rows/columns | Object/class thành relational SQL |
| Mục tiêu | Document API trên relational source of truth | Phân tích/ingest/project JSON trong SQL | Persistence cho domain objects |
| Mapping | Định nghĩa trong database view | JSON path/columns trong query | Mapping metadata/config/code |
| Nested structure | Có thể biểu diễn nested objects/arrays | NESTED PATH chiếu nested JSON thành rows | Object graph/collections |
| Ghi dữ liệu | Có thể hỗ trợ DML qua view theo annotations/capabilities | Chủ yếu là row projection; DML thực hiện qua INSERT/UPDATE/MERGE khác | ORM sinh DML theo unit of work |
| Transaction | Oracle transaction trên các bảng nền | Transaction của SQL statement/session | Phụ thuộc application transaction và ORM |
| Concurrency | Có thể dùng metadata/ETag và database transaction | Do query/DML design quản lý | Thường dùng version column/optimistic locking hoặc locks |
| JSON input | Document interface của view | Input JSON được parse/project | Serialize/deserialize trong application |
| Quan hệ relational | Dùng PK/FK và mapping của duality view | SQL joins sau khi project | ORM relationship mapping |
| Dùng khi | API/document access cần relational consistency | Load, transform, query JSON payload | Domain model phức tạp và persistence trong app |

### Chọn Duality View khi

- Ứng dụng cần JSON document API trên dữ liệu quan hệ.
- Nhiều clients/language muốn dùng cùng một document contract.
- Muốn tránh tự ghép nested JSON bằng nhiều query.
- Muốn database quản lý mapping và transaction trên các bảng nền.
- Muốn relational apps và document apps cùng làm việc trên một source of truth.

### Chọn JSON_TABLE khi

- Có JSON payload từ REST, file, queue hoặc JSON column.
- Cần chuyển JSON thành rows để join với relational tables.
- Cần load JSON vào staging/target tables.
- Cần kiểm tra/aggregate dữ liệu JSON bằng SQL.
- Cần extract nested arrays thành nhiều rows.

### Chọn ORM khi

- Domain model nằm ở application layer.
- Ứng dụng cần identity map, unit of work và relationship navigation.
- Persistence logic gắn với language classes và application transaction.
- Team muốn quản lý SQL mapping thông qua ORM conventions/configuration.
- Có nhiều database tables nhưng API không cần database-native document interface.

### Có thể dùng cả ba

Ví dụ:

1. REST endpoint nhận JSON payload.
2. JSON_TABLE kiểm tra/chiếu payload vào staging rows.
3. Business service dùng ORM để xử lý domain entities.
4. Một endpoint đọc order document qua duality view.
5. Batch SQL dùng bảng relational trực tiếp cho aggregation.

Không cần ép một công nghệ xử lý mọi loại workload.

## 20. Bài thực hành: tạo document view trên relational tables

Bài lab cần Oracle Database release hỗ trợ JSON-Relational Duality Views và schema lab có quyền tạo bảng/view. Cú pháp duality view thay đổi theo release update; dùng SQL Language Reference của đúng môi trường trước khi chạy.

### Bước 1: tạo relational tables

~~~sql
CREATE TABLE lab_customers (
    customer_id NUMBER PRIMARY KEY,
    customer_name VARCHAR2(100) NOT NULL
);

CREATE TABLE lab_orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    status VARCHAR2(20) NOT NULL,
    CONSTRAINT fk_lab_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES lab_customers(customer_id)
);

CREATE TABLE lab_order_items (
    item_id NUMBER PRIMARY KEY,
    order_id NUMBER NOT NULL,
    product_code VARCHAR2(30) NOT NULL,
    quantity NUMBER NOT NULL,
    CONSTRAINT fk_lab_items_order
        FOREIGN KEY (order_id)
        REFERENCES lab_orders(order_id)
);
~~~

### Bước 2: nạp dữ liệu mẫu

~~~sql
INSERT INTO lab_customers VALUES (10, 'Customer A');
INSERT INTO lab_orders VALUES (1001, 10, 'NEW');
INSERT INTO lab_order_items VALUES (1, 1001, 'P-01', 2);
INSERT INTO lab_order_items VALUES (2, 1001, 'P-02', 1);
COMMIT;
~~~

### Bước 3: tạo duality view

Ví dụ khái quát:

~~~sql
CREATE JSON RELATIONAL DUALITY VIEW lab_order_dv AS
SELECT JSON {
    '_id' : o.order_id,
    'status' : o.status,
    'customerId' : o.customer_id,
    'items' : [
        SELECT JSON {
            'itemId' : i.item_id,
            'productCode' : i.product_code,
            'quantity' : i.quantity
        }
        FROM lab_order_items i WITH INSERT UPDATE DELETE
        WHERE i.order_id = o.order_id
    ]
}
FROM lab_orders o WITH INSERT UPDATE DELETE;
~~~

Đây là mẫu mapping tối giản, không lồng customer object để tập trung vào root-child relationship. Cần xác nhận syntax và mọi annotation/requirements theo release đang cài.

### Bước 4: đọc document

~~~sql
DESC lab_order_dv;

SELECT data
FROM lab_order_dv;
~~~

Xác nhận JSON có _id, status, customerId và items array. Nếu tên cột document khác DATA, dùng tên thực tế từ DESC.

### Bước 5: cập nhật relational table

~~~sql
UPDATE lab_orders
SET status = 'CONFIRMED'
WHERE order_id = 1001;

COMMIT;
~~~

Đọc lại duality view và xác nhận document phản ánh status mới. Điều này minh họa relational DML và document view cùng nhìn một dữ liệu nền.

### Bước 6: cập nhật qua duality view

Nếu view và column document hỗ trợ DML theo release:

~~~sql
UPDATE lab_order_dv
SET data = JSON_TRANSFORM(
    data,
    SET '$.status' = 'SHIPPED'
)
WHERE JSON_VALUE(data, '$._id') = '1001';

COMMIT;
~~~

Đọc trực tiếp LAB_ORDERS để xác nhận status đã đổi. Nếu cú pháp hoặc column name khác, theo documentation của release.

### Bước 7: dùng JSON_TABLE để project items

~~~sql
SELECT jt.order_id,
       jt.item_id,
       jt.product_code,
       jt.quantity
FROM lab_order_dv d,
     JSON_TABLE(
         d.data,
         '$'
         COLUMNS (
             order_id NUMBER PATH '$._id',
             NESTED PATH '$.items[*]'
             COLUMNS (
                 item_id NUMBER PATH '$.itemId',
                 product_code VARCHAR2(30) PATH '$.productCode',
                 quantity NUMBER PATH '$.quantity'
             )
         )
     ) jt;
~~~

Ví dụ này cho thấy JSON_TABLE có thể tiêu thụ document được tạo bởi duality view để trả child items thành relational rows. Trong workload thực tế, nếu chỉ cần item data và bảng LAB_ORDER_ITEMS có sẵn, query bảng trực tiếp có thể hiệu quả hơn.

### Bước 8: kiểm tra constraints và quyền

~~~sql
SELECT constraint_name, constraint_type, status, validated
FROM user_constraints
WHERE table_name IN (
    'LAB_CUSTOMERS',
    'LAB_ORDERS',
    'LAB_ORDER_ITEMS'
)
ORDER BY table_name, constraint_name;

SELECT table_name, privilege, grantee
FROM user_tab_privs
WHERE table_name = 'LAB_ORDER_DV';
~~~

Thử insert document với customer_id không tồn tại để xác nhận foreign key bảo vệ dữ liệu nếu view cho phép insert. Thử cập nhật field không được phép để quan sát DML capability enforcement.

### Bước 9: kiểm tra concurrency

1. Session A đọc document và ETag/metadata nếu view/API trả về.
2. Session B cập nhật status.
3. Session A thử update theo token/version cũ qua API hoặc cơ chế conditional update được hỗ trợ.
4. Xác nhận conflict được phát hiện và application không ghi đè thay đổi của Session B.

Không giả định một UPDATE SQL thuần tự động kiểm tra ETag nếu chưa dùng đúng cơ chế concurrency của duality view/API.

### Bước 10: dọn lab

~~~sql
DROP VIEW lab_order_dv;
DROP TABLE lab_order_items PURGE;
DROP TABLE lab_orders PURGE;
DROP TABLE lab_customers PURGE;
~~~

DROP VIEW syntax/object type cần xác nhận theo cách duality view được đăng ký trong release. Chỉ xóa object lab do bài thực hành tạo.

## 21. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| CREATE JSON RELATIONAL DUALITY VIEW không nhận diện | Database release/service chưa hỗ trợ hoặc cú pháp không đúng | Xác nhận version, RU, SQL Language Reference và feature availability. |
| Table mapping bị từ chối | Thiếu primary key, relationship không rõ hoặc table/type không được hỗ trợ | Kiểm tra PK/FK, cardinality và supported object restrictions. |
| DML qua view bị từ chối | Table annotation/capability không cho phép thao tác | Xem view definition, DML privileges và constraints. |
| Insert document thất bại | Thiếu field NOT NULL, key hoặc foreign key không hợp lệ | Validate JSON shape và relational constraints trước insert. |
| Nested array thiếu hoặc lặp phần tử | Mapping join/cardinality sai hoặc child key không phù hợp | Kiểm tra FK, join condition và child identity. |
| Update shared customer từ order document | Shared entity nằm trong mapping có quyền ghi | Tách ownership/API boundary và giới hạn table DML permissions. |
| JSON_TABLE trả NULL | Path không tồn tại, datatype conversion hoặc error handling | Kiểm tra JSON payload, path, ON ERROR và datatype. |
| JSON_TABLE nhân số hàng | Nested array cardinality hoặc nhiều nested paths | Xác định row pattern và join cardinality mong muốn. |
| ORM phát sinh quá nhiều query | Lazy loading/N+1 hoặc fetch plan không phù hợp | Dùng fetch join, batch fetching, projection và query logging. |
| Document update ghi đè thay đổi mới | Không kiểm tra optimistic concurrency | Dùng ETag/version và xử lý conflict. |
| REST API trả lỗi không rõ | Exception mapping/authorization chưa được thiết kế | Map database errors thành API status an toàn, log request ID. |
| Document response quá lớn | Nested arrays không giới hạn | Pagination, projection, endpoint child collection hoặc filter. |

### Checklist chẩn đoán

1. Oracle Database release và service có hỗ trợ duality view không?
2. View được tạo từ đúng root table và relationships chưa?
3. Root/child tables có key phù hợp không?
4. Table DML annotations có cho phép thao tác không?
5. Database user có privilege cần thiết không?
6. JSON document có field/type phù hợp constraints không?
7. Nested path/join có tạo đúng cardinality không?
8. ETag/version có được kiểm tra khi concurrent update không?
9. Execution plan có truy cập đúng keys/indexes không?
10. API authorization và tenant filter có được enforce không?

## 22. Checklist triển khai production

### Data model

- Root document có stable primary key.
- Child relationships có foreign keys rõ ràng.
- Shared entities có ownership và update boundary rõ.
- Relational constraints bảo vệ invariants.
- Document shape chỉ expose fields cần thiết.

### Duality view

- View syntax được xác nhận theo release.
- Root/nested mapping và cardinality đã test.
- INSERT/UPDATE/DELETE capability được giới hạn.
- Read-only fields và derived fields được xác định.
- ETag/optimistic concurrency được hiểu và test.

### Application/API

- REST/GraphQL layer có authentication/authorization.
- Request validation, payload size và pagination.
- Error mapping cho missing document, constraint và conflict.
- Retry/idempotency và transaction boundaries.
- Document contract versioning và backward compatibility.

### Performance

- Index trên root/foreign keys phù hợp.
- Nested arrays không tạo document quá lớn.
- Query plan và actual runtime đã đo.
- JSON_TABLE chỉ project field cần thiết.
- ORM fetch strategy tránh N+1 và over-fetching.
- Load test với document size và concurrency thực tế.

### Operations

- Database version/RU và service entitlement được xác nhận.
- DDL migration và rollback/roll-forward plan có sẵn.
- Audit/log redaction và monitoring.
- Backup/recovery và schema export.
- Deployment/rollback được diễn tập trên môi trường clone.

## 23. Câu hỏi tự kiểm tra

1. **JSON-Relational Duality View là gì?** View database tạo document JSON trên relational tables và có thể hỗ trợ DML theo mapping.
2. **Dữ liệu có được lưu thành bản JSON duplicate không?** Không nhất thiết; relational tables vẫn là nơi lưu dữ liệu nền.
3. **Vì sao gọi là duality?** Cùng dữ liệu có thể được nhìn qua relational model và JSON document model.
4. **Root table có vai trò gì?** Định danh thực thể/document gốc.
5. **Foreign key dùng để làm gì?** Mô tả parent-child relationship trong relational model và hỗ trợ mapping.
6. **DML annotations có ý nghĩa gì?** Xác định thao tác INSERT/UPDATE/DELETE được phép qua table reference trong view.
7. **Duality view có bỏ qua constraint không?** Không; relational constraints trên bảng nền vẫn áp dụng.
8. **ETag giúp gì?** Phát hiện document đã thay đổi kể từ lần client đọc.
9. **ETag có phải business version không?** Không; business version có semantics riêng.
10. **JSON_TABLE làm gì?** Chiếu JSON fields/arrays thành relational rows và columns.
11. **JSON_TABLE có tạo document API updatable không?** Không; nó là row source trong SQL.
12. **NESTED PATH dùng để làm gì?** Project nested JSON arrays/objects thành cột/hàng con.
13. **FOR ORDINALITY dùng để làm gì?** Tạo số thứ tự cho array elements.
14. **JSON_VALUE khác JSON_QUERY thế nào?** JSON_VALUE lấy scalar; JSON_QUERY lấy object/array JSON.
15. **ORM làm gì?** Ánh xạ application objects/classes với tables và quản lý persistence/unit of work.
16. **ORM có phải database view không?** Không; ORM hoạt động ở application runtime.
17. **Duality view có thể dùng cùng ORM không?** Có, nếu ORM/driver hỗ trợ hoặc application gọi view qua native SQL/API.
18. **Khi nào nên dùng JSON_TABLE?** Khi cần ingest, validate, query hoặc transform JSON thành relational rows.
19. **Khi nào nên dùng duality view?** Khi cần document interface trên relational source of truth.
20. **Khi nào ORM phù hợp?** Khi application domain model và object lifecycle cần persistence mapping.
21. **Có thể dùng cả ba trong một hệ thống không?** Có; mỗi công nghệ giải quyết một chiều truy cập/tầng khác nhau.
22. **Duality view có tự tạo REST API không?** Không; cần API integration/configuration.
23. **Một customer được lồng trong nhiều order có thể gây gì?** Update qua một document có thể ảnh hưởng shared customer data.
24. **Vì sao cần pagination cho nested arrays?** Tránh document payload lớn và tốn tài nguyên.
25. **JSON_TABLE NULL ON ERROR có rủi ro gì?** Có thể che giấu payload malformed hoặc datatype conversion lỗi.
26. **Duality view thay thế relational schema design không?** Không; keys, constraints và data ownership vẫn cần thiết.
27. **V$OPTION hoặc feature availability có chứng minh entitlement không?** Không; phải kiểm tra contract/license documents.
28. **Điều gì phải test trước production?** Version support, mapping, DML capability, concurrency, security, performance và recovery.

JSON-Relational Duality Views cung cấp document interface trên relational tables, cho phép ứng dụng document-oriented và relational cùng dùng một source of truth. JSON_TABLE có chiều khác: chiếu JSON input thành rows/columns cho SQL; ORM ánh xạ application objects và quản lý persistence ở tầng ứng dụng. Chọn duality view khi cần JSON document CRUD trên relational data, JSON_TABLE khi cần ingest/query JSON payload, và ORM khi cần domain object lifecycle. Ba công nghệ có thể phối hợp. Trước production, xác nhận release support, keys/relationships, DML permissions, constraints, ETag concurrency, API authorization, payload size và query performance.

## 12. Duality View so với JSON column và JSON collection

Oracle hỗ trợ lưu JSON trong relational columns (ví dụ native JSON type ở các release hỗ trợ hoặc VARCHAR2/CLOB/BLOB với IS JSON constraint). Điều này khác duality view.

### JSON column

JSON column lưu document như một giá trị trong một row:

~~~sql
CREATE TABLE api_events (
    event_id NUMBER PRIMARY KEY,
    payload JSON
);
~~~

Datatype JSON native và cú pháp cụ thể phụ thuộc release. Ở các release cũ hơn, JSON thường được lưu trong VARCHAR2/CLOB/BLOB và có constraint/validation tương ứng.

JSON column phù hợp khi document là dữ liệu được lưu trực tiếp, cấu trúc linh hoạt và relational decomposition không cần thiết cho từng field.

### Duality view

Duality view trình bày document được tạo từ nhiều relational rows/tables. Dữ liệu vẫn được lưu theo schema quan hệ và chịu các constraints relational.

### JSON collection/document store

Document collection quản lý JSON documents theo mô hình document store, có APIs/indexing/operations riêng theo sản phẩm và release. Duality view không phải collection độc lập; nó là view trên relational tables.

### Bảng so sánh

| Mô hình | Dữ liệu lưu ở đâu? | Điểm mạnh | Cần chú ý |
| --- | --- | --- | --- |
| Relational tables | Các cột và rows quan hệ | Constraint, joins, SQL, normalization | Ứng dụng có thể phải tự tạo JSON |
| JSON column | Một JSON value trong row | Lưu payload linh hoạt, schema evolution | Validation/indexing và query path |
| JSON collection | Document store | Document CRUD và document APIs | Relational constraints/joins khác mô hình bảng |
| Duality view | Các relational tables nền | JSON interface trên relational source of truth | Mapping, DML capability và feature/version limits |

## 13. Tích hợp REST và GraphQL

Duality views có thể được dùng làm nền cho document APIs. Tầng API có thể expose document read/write qua REST hoặc GraphQL theo công cụ và release hỗ trợ.

### Vai trò của database và API layer

- Duality view định nghĩa document shape và relational mapping.
- Database kiểm tra constraints, transaction và DML capability.
- API layer xử lý authentication, authorization, routing, HTTP semantics và payload limits.
- Client quản lý ETag/version và retry/conflict behavior.

### REST endpoint

Một endpoint conceptual:

~~~text
GET    /orders/9002
POST   /orders
PUT    /orders/9002
PATCH  /orders/9002
DELETE /orders/9002
~~~

REST service có thể map endpoint tới duality view, nhưng URL/method behavior không tự sinh ra chỉ vì view tồn tại. Cần cấu hình REST service/ORDS hoặc application middleware phù hợp.

### HTTP status

API cần phân biệt:

- 200/201: đọc hoặc tạo thành công.
- 204: update/delete thành công không cần response body.
- 400: JSON invalid hoặc request shape sai.
- 401/403: authentication/authorization failure.
- 404: document không tồn tại.
- 409: conflict theo business rule hoặc concurrency.
- 412: precondition failed, ví dụ ETag không khớp nếu API dùng If-Match.
- 500: lỗi server/database không dự kiến.

Mapping status cụ thể phụ thuộc API framework. Không để lỗi SQL thô hoặc database credentials xuất hiện trong response.

### GraphQL

GraphQL cho phép client yêu cầu một shape cụ thể. Duality view có thể là nguồn dữ liệu document cho resolver/service, nhưng GraphQL schema, authorization, pagination và mutation semantics vẫn cần được thiết kế. Một duality view không tự động trở thành GraphQL API nếu chưa có integration layer.

### Không đưa mọi child array vào một response

Một order có thể có hàng chục nghìn items. API nên hỗ trợ pagination/filtering hoặc endpoint riêng cho child collection nếu view/API integration cho phép. Document aggregate quá lớn làm tăng memory, network payload và latency.

## 14. Performance và query planning

Duality view giúp đơn giản hóa document access nhưng không làm chi phí relational work biến mất. Oracle vẫn phải đọc root/child rows, thực hiện joins, tạo JSON representation và áp dụng predicate.

### Các yếu tố ảnh hưởng

- Số bảng và độ sâu nested structure.
- Số child rows trên mỗi root document.
- Primary/foreign key indexes.
- Predicate selectivity và cách filter theo root ID.
- Kích thước document được trả về.
- Số field được serialize.
- Concurrent updates và lock contention.
- Network payload và application JSON parsing.

### Index trên relational keys

Primary key trên root table giúp tìm document. Index trên foreign key child thường hỗ trợ join, child lookup và DML behavior. Không tạo index theo mọi JSON field một cách máy móc; xác định query predicates thực tế và kiểm tra plan.

### Tránh document quá lớn

Một document có thể gom nhiều child records. Nếu mỗi order có hàng chục nghìn items, việc luôn trả toàn bộ array có thể tốn CPU/memory và tăng network transfer. Cân nhắc:

- Document aggregate chỉ chứa child data cần cho use case.
- Endpoint riêng để phân trang items.
- Giới hạn số phần tử trả về.
- Filter theo root key trước khi assemble document.
- Không query toàn bộ duality view rồi lọc ở application.

### Kiểm tra execution plan

~~~sql
EXPLAIN PLAN FOR
SELECT data
FROM order_dv
WHERE JSON_VALUE(data, '$._id') = '9002';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

EXPLAIN PLAN là estimated plan. Với workload thực tế, thu actual cursor plan và runtime statistics theo phương pháp phù hợp. Xác nhận optimizer có dùng key access path và không scan/assemble quá nhiều documents.

### So sánh với query relational trực tiếp

Nếu báo cáo cần SUM quantity theo product trên hàng triệu order items, query trực tiếp ORDER_ITEMS thường tự nhiên và hiệu quả hơn việc assemble JSON document rồi parse lại bằng JSON_TABLE. Duality view phù hợp cho document access; không phải mọi analytical SQL đều nên đi qua document representation.

### JSON_TABLE performance

JSON_TABLE có chi phí parse/path evaluation và tạo row source. Tối ưu bằng cách:

- Chỉ project field cần dùng.
- Chọn JSON path cụ thể.
- Tránh parse cùng payload nhiều lần trong cùng query nếu có thể.
- Dùng datatype phù hợp để tránh conversion lặp.
- Kiểm tra cardinality estimate cho nested arrays.
- Lưu JSON đã validate theo datatype/constraint phù hợp.

### ORM performance

ORM có thể phát sinh N+1 queries, load quá nhiều columns hoặc tạo SQL không phù hợp. Dùng fetch plans, batching, projections, query logging và execution plan review. ORM không tự động nhanh hơn SQL trực tiếp.

## 15. Consistency, transaction và locking

Duality view là một database interface trên relational data. Các thao tác DML qua view tuân theo transaction và constraint semantics của Oracle.

### Một document, nhiều bảng

Nếu document chứa root row và child rows, một lần DML document có thể ảnh hưởng nhiều bảng. Database phải thực hiện các thay đổi theo mapping và transaction. Ứng dụng cần commit sau khi toàn bộ thao tác thành công; nếu lỗi, rollback transaction chưa commit.

### Concurrent update

Hai client có thể cập nhật cùng document hoặc các child records liên quan. Dùng ETag/optimistic concurrency hoặc version control phù hợp để phát hiện stale update. Không giả định mọi field-level update đều merge tự động.

### Row locks

DML qua duality view có thể lock các relational rows được thay đổi. Một document lớn với nhiều child rows có thể tăng số row locks và thời gian transaction. Giữ transaction ngắn và tránh gọi external API khi đang giữ locks.

### Relational application đồng thời

Một ứng dụng có thể cập nhật ORDERS trực tiếp, trong khi một ứng dụng khác cập nhật ORDER_DV. Cả hai làm việc trên cùng bảng nền. Cần thống nhất business rules, versioning và transaction boundaries; duality view không tạo một vùng dữ liệu cô lập riêng.

### Read consistency

SELECT document tuân theo Oracle read consistency. Khi query nhiều documents hoặc nhiều endpoint riêng, chúng có thể được đọc ở các statement snapshots khác nhau. Nếu nghiệp vụ cần một snapshot thống nhất xuyên nhiều request, phải thiết kế transaction/SCN strategy phù hợp.

### Shared entities

Một customer được tham chiếu bởi nhiều orders. Update customer qua document order có thể thay đổi thông tin được hiển thị ở các order khác. Nếu nghiệp vụ muốn customer chỉ được quản lý qua endpoint riêng, thiết kế view permissions và API boundary để tránh update shared entity từ order document.

## 16. Security và authorization

JSON document interface không làm giảm yêu cầu bảo mật. Cần bảo vệ cả database objects lẫn API endpoints.

### Least privilege

- Tạo database user riêng cho từng service/application role.
- Chỉ GRANT quyền cần thiết trên duality view.
- Không cấp SYSDBA/DBA cho API account.
- Hạn chế trực tiếp DML trên bảng nền nếu ứng dụng phải đi qua view/API contract.
- Dùng read-only account cho reporting.

### Row-level security

Nếu user chỉ được xem orders của tenant/customer mình, cần áp dụng authorization ở API và/hoặc database row-level security (VPD/FGAC) theo thiết kế. Không giả định document ID khó đoán là security boundary.

### Tenant isolation

Document key cần được kết hợp với tenant predicate/authorization. API phải kiểm tra tenant identity trên mỗi request; không cho client tự gửi tenant_id rồi tin tưởng giá trị đó.

### Field-level access

Không expose password hash, internal flags, PII hoặc sensitive columns chỉ vì chúng có trong relational table. Document mapping chỉ nên chứa field cần cho API. Với field nhạy cảm, dùng view riêng hoặc policy kiểm soát.

### SQL injection và JSON path

Không nối chuỗi JSON path, filter hoặc SQL fragment từ input không tin cậy. Dùng bind variables và validation. JSON payload cũng cần giới hạn size, nesting depth và các giá trị hợp lệ theo business schema.

### Audit

Audit API principal, database user, action, document key, request ID và thời điểm. Không log toàn bộ JSON document nếu chứa dữ liệu nhạy cảm. Dùng redaction và retention policy phù hợp.

## 17. Schema evolution và versioning document

Relational schema và JSON document contract có thể thay đổi độc lập theo từng release. Một thay đổi cột không nên tự động phá vỡ client JSON.

### Additive changes

Thêm field JSON optional thường dễ tương thích hơn đổi tên/xóa field hiện có. Client cũ nên bỏ qua field chưa biết; client mới cần xử lý field có thể vắng mặt.

### Rename field

Nếu JSON field name đổi, cân nhắc duy trì alias/compatibility layer hoặc version API. Không đổi field contract mà không phối hợp client release.

### Required field

Thêm field bắt buộc có thể làm client cũ không gửi field đó bị lỗi insert. Cần default, server-side derivation hoặc API version mới.

### Relational migration

Khi thay đổi bảng nền:

1. Expand schema theo cách tương thích.
2. Cập nhật duality view mapping.
3. Deploy client/server code tương thích.
4. Backfill dữ liệu nếu cần.
5. Validate document shape và relational constraints.
6. Chỉ contract cấu trúc cũ sau khi mọi consumer chuyển đổi.

### View DDL và dependent objects

Thay đổi duality view có thể ảnh hưởng REST endpoint, client document schema, grants và application code. Lưu DDL, kiểm tra dependencies, version document contract và test insert/update/delete sau mỗi migration.

### Backward compatibility

Không xóa JSON field, đổi type hoặc thay nested array thành object trong một release nếu client cũ còn dùng contract cũ. Dùng versioned endpoint hoặc migration period.

## 18. Những giới hạn và điều cần xác minh

Khả năng duality view phụ thuộc Oracle Database release và release update. Trước production, xác minh:

- Feature có được hỗ trợ trong đúng database version/service không.
- Syntax của CREATE JSON RELATIONAL DUALITY VIEW và table annotations.
- Các table types, datatype, constraints và relationships được hỗ trợ.
- DML support cho nested insert/update/delete và shared tables.
- Quy tắc key generation và document identity.
- ETag/optimistic concurrency semantics.
- REST/GraphQL integration và ORDS version.
- Security policies, privileges và audit behavior.
- Partitioning, replication, standby và cloud-service restrictions.

### Không coi duality view như view updatable thông thường

Khả năng DML của duality view được quản lý theo feature-specific rules. Không suy luận rằng mọi SQL view updatable đều có thể chuyển thành duality view, hoặc mọi JSON patch đều được chuyển thành arbitrary table DML.

### Không dùng duality view để thay relational schema design

Primary keys, foreign keys, unique constraints, normalization và data ownership vẫn cần được thiết kế tốt. Document representation không sửa được relational schema có key yếu, duplicate dữ liệu hoặc business rules không rõ.

### Không dùng JSON_TABLE như duality view

JSON_TABLE không định nghĩa một persistent document API và không cung cấp duality DML semantics. Nó là row source trong SQL statement.

### Không dùng ORM như authorization boundary duy nhất

Database privileges, row-level security và API authorization vẫn cần thiết. ORM mapping có thể bị bypass bởi native SQL, batch jobs hoặc ứng dụng khác.

## 19. Chọn công nghệ theo use case

### API order document trên relational database

Nếu order, customer và items đã được chuẩn hóa trong relational tables nhưng REST API cần một JSON aggregate có thể đọc/ghi, duality view là lựa chọn đáng xem xét. Database giữ constraints và transaction; ứng dụng làm việc với document shape.

### Import JSON từ đối tác

Nếu hệ thống nhận file/HTTP payload chứa hàng nghìn orders và cần validate rồi load vào bảng staging, JSON_TABLE phù hợp. Nó biến JSON arrays thành rows để join reference data, phát hiện lỗi và insert vào relational tables.

### Domain model phức tạp trong Java

Nếu ứng dụng có domain entities, business methods, relationships và unit of work phức tạp, ORM có thể phù hợp. Dùng ORM để quản lý persistence; các endpoint document có thể gọi duality view qua native SQL nếu cần.

### Reporting và analytics

Nếu workload cần group, sum, join và window functions trên nhiều triệu rows, ưu tiên SQL relational trực tiếp. Không serialize document rồi dùng JSON_TABLE để tái tạo quan hệ đã có.

### Event payload

Nếu payload là event bất biến, schema linh hoạt và chủ yếu lưu/tra cứu toàn document, JSON column hoặc document collection có thể phù hợp hơn duality view. Nếu cần enforce relational constraints và join với master data, cân nhắc relational tables + JSON_TABLE hoặc duality view tùy hướng truy cập.

### Decision table

| Câu hỏi | Nếu câu trả lời là có | Công nghệ cần xem |
| --- | --- | --- |
| Dữ liệu đã chuẩn hóa thành nhiều relational tables? | Có | Duality view nếu cần document API |
| Đầu vào hiện tại là JSON và cần thành rows? | Có | JSON_TABLE |
| Cần object graph và unit of work trong application? | Có | ORM |
| Cần document CRUD trên relational source of truth? | Có | Duality view |
| Cần SQL aggregation trên nested JSON payload? | Có | JSON_TABLE |
| Cần API document nhưng không cần DML qua database? | Có | View/query JSON hoặc API serialization; duality view có thể không cần thiết |
| Cần lưu event JSON nguyên trạng? | Có | JSON column/document store |

### Có thể dùng cả ba

Ví dụ:

1. REST endpoint nhận JSON payload.
2. JSON_TABLE kiểm tra/chiếu payload vào staging rows.
3. Business service dùng ORM để xử lý domain entities.
4. Một endpoint đọc order document qua duality view.
5. Batch SQL dùng bảng relational trực tiếp cho aggregation.

Không cần ép một công nghệ xử lý mọi loại workload.
