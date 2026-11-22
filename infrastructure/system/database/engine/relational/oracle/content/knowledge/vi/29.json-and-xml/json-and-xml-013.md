# Lựa chọn lưu trữ quan hệ, tài liệu hoặc mô hình kết hợp

Khi thiết kế dữ liệu trong Oracle Database, một quyết định quan trọng là chọn cách tổ chức dữ liệu theo **mô hình quan hệ**, **mô hình tài liệu** hay **mô hình kết hợp**. Mô hình quan hệ lưu dữ liệu trong bảng có cột, khóa và ràng buộc rõ ràng. Mô hình tài liệu lưu một đối tượng nghiệp vụ dưới dạng JSON hoặc XML, thường giữ các thuộc tính liên quan trong cùng một tài liệu. Mô hình kết hợp dùng bảng quan hệ cho phần dữ liệu cốt lõi và dùng JSON/XML cho phần mở rộng hoặc các cấu trúc có tính linh hoạt cao.

Không có một mô hình tối ưu cho mọi hệ thống. Lựa chọn nên dựa trên cấu trúc dữ liệu, quan hệ giữa các thực thể, quy tắc toàn vẹn, cách truy vấn, tần suất cập nhật, yêu cầu tích hợp và khả năng hỗ trợ của phiên bản Oracle đang vận hành.

## 1. Ba cách tổ chức dữ liệu

### Mô hình quan hệ

Mô hình quan hệ chia dữ liệu thành các bảng. Mỗi bảng mô tả một loại thực thể hoặc quan hệ; các hàng được nhận diện bằng khóa chính và liên kết bằng khóa ngoại. Các quy tắc dữ liệu có thể được thể hiện bằng NOT NULL, UNIQUE, CHECK, PRIMARY KEY và FOREIGN KEY.

Ví dụ một hệ thống bán hàng có thể có các bảng:

- CUSTOMERS: thông tin khách hàng.
- ORDERS: thông tin đơn hàng.
- ORDER_ITEMS: các dòng hàng trong đơn.
- PRODUCTS: danh mục sản phẩm.

Một đơn hàng có thể gồm nhiều dòng hàng. Quan hệ một-nhiều được thể hiện bằng khóa ngoại ORDER_ITEMS.order_id tham chiếu ORDERS.order_id.

~~~sql
CREATE TABLE customers (
  customer_id   NUMBER PRIMARY KEY,
  customer_name VARCHAR2(200) NOT NULL,
  email         VARCHAR2(320) UNIQUE
);

CREATE TABLE orders (
  order_id    NUMBER PRIMARY KEY,
  customer_id NUMBER NOT NULL,
  order_date  TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
  status      VARCHAR2(20) NOT NULL,
  CONSTRAINT orders_customer_fk
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
  CONSTRAINT orders_status_ck
    CHECK (status IN ('NEW', 'PAID', 'SHIPPED', 'CANCELLED'))
);

CREATE TABLE order_items (
  order_id   NUMBER NOT NULL,
  line_no    NUMBER NOT NULL,
  product_id NUMBER NOT NULL,
  quantity   NUMBER(10, 2) NOT NULL,
  unit_price NUMBER(12, 2) NOT NULL,
  CONSTRAINT order_items_pk PRIMARY KEY (order_id, line_no),
  CONSTRAINT order_items_order_fk
    FOREIGN KEY (order_id) REFERENCES orders(order_id),
  CONSTRAINT order_items_quantity_ck CHECK (quantity > 0),
  CONSTRAINT order_items_price_ck CHECK (unit_price >= 0)
);
~~~

Các dòng hàng có thể được truy vấn, lọc, tổng hợp và nối với sản phẩm hoặc đơn hàng mà không cần phân tích một tài liệu lớn. Cơ sở dữ liệu trực tiếp bảo vệ các quan hệ khóa và một số quy tắc toàn vẹn.

### Mô hình tài liệu

Mô hình tài liệu biểu diễn một đối tượng nghiệp vụ dưới dạng một tài liệu JSON hoặc XML. Thay vì tách mọi thuộc tính thành các bảng và cột, tài liệu thường nhóm dữ liệu theo ranh giới mà ứng dụng đọc hoặc ghi cùng nhau.

Ví dụ một đơn hàng dưới dạng JSON:

~~~json
{
  "orderId": 1001,
  "customer": {
    "customerId": 501,
    "name": "Nguyen An"
  },
  "status": "NEW",
  "items": [
    {
      "lineNo": 1,
      "productId": 10,
      "description": "Keyboard",
      "quantity": 2,
      "unitPrice": 45.5
    },
    {
      "lineNo": 2,
      "productId": 20,
      "description": "Mouse",
      "quantity": 3,
      "unitPrice": 18
    }
  ]
}
~~~

Tài liệu có thể được lưu trong CLOB, BLOB hoặc kiểu JSON gốc tùy phiên bản Oracle. Với XML, Oracle cung cấp XMLTYPE và các hàm SQL/XML để truy vấn hoặc chuyển đổi tài liệu.

Một cách lưu JSON dạng văn bản trên Oracle 19c:

~~~sql
CREATE TABLE order_documents (
  order_id NUMBER PRIMARY KEY,
  payload  CLOB NOT NULL,
  CONSTRAINT order_documents_json_ck CHECK (payload IS JSON)
);
~~~

Trên Oracle Database 21c trở lên, có thể dùng kiểu SQL JSON gốc:

~~~sql
CREATE TABLE order_documents_native (
  order_id NUMBER PRIMARY KEY,
  payload  JSON NOT NULL
);
~~~

Kiểu JSON gốc sử dụng biểu diễn nhị phân OSON. Với cột CLOB, CHECK IS JSON kiểm tra nội dung là JSON hợp lệ; nó không tự xác nhận mọi quy tắc nghiệp vụ như customerId phải tồn tại trong bảng CUSTOMERS hoặc quantity phải lớn hơn 0.

### Mô hình kết hợp

Mô hình kết hợp giữ dữ liệu có cấu trúc ổn định trong bảng quan hệ, đồng thời lưu các thuộc tính linh hoạt trong JSON/XML. Ví dụ, đơn hàng vẫn có order_id, customer_id, status và order_date trong bảng ORDERS; các thuộc tính mở rộng theo từng loại đơn hàng được lưu trong một cột JSON.

~~~sql
CREATE TABLE orders_hybrid (
  order_id    NUMBER PRIMARY KEY,
  customer_id NUMBER NOT NULL,
  order_date  TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
  status      VARCHAR2(20) NOT NULL,
  attributes  CLOB,
  CONSTRAINT orders_hybrid_customer_fk
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
  CONSTRAINT orders_hybrid_status_ck
    CHECK (status IN ('NEW', 'PAID', 'SHIPPED', 'CANCELLED')),
  CONSTRAINT orders_hybrid_attributes_json_ck
    CHECK (attributes IS JSON)
);
~~~

Ví dụ attributes có thể chứa thông tin giao hàng, tùy chọn quà tặng hoặc trường bổ sung theo kênh bán hàng. Khóa đơn hàng, khách hàng và trạng thái vẫn là cột quan hệ để dễ kiểm soát và truy vấn.

## 2. So sánh các mô hình

| Tiêu chí | Quan hệ | Tài liệu JSON/XML | Kết hợp |
|---|---|---|---|
| Cấu trúc dữ liệu | Bảng và cột được định nghĩa rõ | Cấu trúc nằm trong từng tài liệu | Cột ổn định kết hợp tài liệu mở rộng |
| Quan hệ giữa thực thể | Khóa chính, khóa ngoại, JOIN | Thường tham chiếu bằng mã hoặc lồng tài liệu | Quan hệ cốt lõi bằng khóa; phần linh hoạt nằm trong tài liệu |
| Kiểm tra toàn vẹn | Constraint và giao dịch quan hệ | Cần kiểm tra cú pháp và quy tắc ở nhiều lớp | Constraint cho phần cốt lõi, validation cho phần tài liệu |
| Thay đổi cấu trúc | Thay đổi schema khi thêm cột hoặc bảng | Có thể thêm trường trong tài liệu | Thêm trường linh hoạt mà không phải thay đổi mọi cột |
| Truy vấn phân tích | SQL JOIN, GROUP BY và index | SQL/JSON, XQuery, JSON_TABLE, XMLTABLE | Kết hợp SQL quan hệ và truy vấn tài liệu |
| Dữ liệu lặp/nhiều-nhiều | Biểu diễn bằng bảng liên kết | Có thể lồng mảng hoặc lưu tham chiếu | Dùng quan hệ cho liên kết cần kiểm soát, tài liệu cho dữ liệu phụ |
| Tích hợp API | Cần ánh xạ bảng thành DTO hoặc tài liệu | Tự nhiên với API JSON/XML | Dùng view hoặc tầng ứng dụng để tạo tài liệu |
| Phù hợp nhất | Dữ liệu cốt lõi có quan hệ và quy tắc chặt | Aggregate/document có ranh giới rõ, cấu trúc linh hoạt | Hệ thống vừa cần toàn vẹn quan hệ vừa cần linh hoạt tài liệu |

Không nên chọn mô hình chỉ dựa trên việc JSON/XML đang phổ biến hay vì một mô hình có vẻ ít bảng hơn. Cần xác định dữ liệu sẽ được truy vấn và cập nhật như thế nào trong suốt vòng đời hệ thống.

## 3. Khi nào nên chọn mô hình quan hệ?

Mô hình quan hệ thường phù hợp khi:

- Dữ liệu có cấu trúc ổn định và các thuộc tính quan trọng được biết trước.
- Nhiều thực thể có quan hệ một-nhiều hoặc nhiều-nhiều.
- Cần khóa ngoại để ngăn tham chiếu đến thực thể không tồn tại.
- Cần UNIQUE, CHECK, NOT NULL hoặc các ràng buộc khác được database thực thi.
- Ứng dụng cần truy vấn linh hoạt qua nhiều bảng, tổng hợp và báo cáo.
- Dữ liệu được nhiều ứng dụng hoặc nhiều nhóm nghiệp vụ cùng sử dụng.
- Giao dịch cần cập nhật nhiều thực thể có liên quan trong một đơn vị công việc.

Ví dụ: hệ thống kế toán, tồn kho, quản lý đơn hàng, nhân sự và thanh toán thường có nhiều quan hệ cần bảo vệ. Số dư, số lượng tồn, mã tài khoản và trạng thái nghiệp vụ cần có quy tắc rõ ràng. Đưa toàn bộ dữ liệu vào một JSON document có thể làm khó việc bảo vệ khóa ngoại và các quy tắc liên bảng.

### Lợi thế của chuẩn hóa

Chuẩn hóa giúp giảm trùng lặp và tránh cập nhật không nhất quán. Ví dụ, nếu tên khách hàng được lặp lại trong mọi đơn hàng, khi khách đổi tên phải cập nhật nhiều tài liệu. Nếu thông tin khách hàng nằm trong CUSTOMERS và đơn hàng chỉ lưu customer_id, thông tin có một nguồn chính.

Chuẩn hóa không có nghĩa mọi truy vấn đều phải JOIN thật nhiều bảng hoặc mọi dữ liệu đều phải tách thành bảng riêng. Mức chuẩn hóa cần phù hợp với tính chất dữ liệu, hiệu năng và quy tắc nghiệp vụ. Có thể dùng view, materialized view hoặc bảng tổng hợp khi cần tối ưu đọc.

## 4. Khi nào nên chọn mô hình tài liệu?

Mô hình tài liệu phù hợp khi:

- Dữ liệu được đọc và ghi theo một aggregate có ranh giới rõ.
- Các thuộc tính thay đổi theo loại đối tượng hoặc theo phiên bản API.
- Nhiều trường là tùy chọn và không cần JOIN với các thực thể khác.
- Ứng dụng thường lấy toàn bộ tài liệu hoặc một phần lớn của tài liệu cùng lúc.
- Cần lưu payload từ hệ thống bên ngoài để xử lý, kiểm tra hoặc lưu dấu vết.
- Tài liệu có cấu trúc lồng nhau tự nhiên, chẳng hạn cấu hình, sự kiện, hồ sơ hoặc biểu mẫu.

Ví dụ, một hệ thống quản lý cấu hình có thể có các loại thiết bị khác nhau. Thiết bị mạng có thuộc tính VLAN, router có thuộc tính routingProtocol, còn thiết bị lưu trữ có thuộc tính capacity và RAID. Nếu các trường này thay đổi thường xuyên và không cần truy vấn quan hệ sâu, một tài liệu JSON cho phần cấu hình có thể đơn giản hơn việc thêm nhiều cột NULL vào một bảng chung.

~~~sql
CREATE TABLE device_profiles (
  device_id NUMBER PRIMARY KEY,
  device_type VARCHAR2(30) NOT NULL,
  profile JSON
);
~~~

Ví dụ dữ liệu profile của thiết bị mạng:

~~~json
{
  "hostname": "edge-01",
  "managementIp": "10.10.0.10",
  "vlans": [10, 20, 30],
  "snmp": {
    "enabled": true,
    "version": "v3"
  }
}
~~~

Ví dụ profile của thiết bị lưu trữ:

~~~json
{
  "hostname": "storage-01",
  "capacityTb": 120,
  "raidLevel": "RAID6",
  "replication": {
    "enabled": true,
    "target": "dc-2"
  }
}
~~~

Mỗi profile có thể có cấu trúc riêng. Các trường dùng chung như device_id và device_type vẫn nằm ở bảng quan hệ.

### Giới hạn cần hiểu

Lưu tài liệu không tự động giải quyết việc xác thực nghiệp vụ. `CHECK (profile IS JSON)` chỉ xác nhận cú pháp JSON hợp lệ. Nó không bảo đảm:

- hostname là duy nhất trên toàn hệ thống.
- managementIp thuộc một subnet được phép.
- device_type tương ứng với đúng cấu trúc profile.
- replication.target tham chiếu đến một trung tâm dữ liệu tồn tại.
- capacityTb không vượt giới hạn của hợp đồng.

Những quy tắc này có thể cần validation trong ứng dụng, trigger, procedure hoặc một thiết kế quan hệ bổ sung. Nếu một thuộc tính trở thành khóa tìm kiếm, khóa liên kết hoặc quy tắc nghiệp vụ quan trọng, hãy cân nhắc đưa thuộc tính đó ra cột quan hệ.

## 5. Khi nào nên chọn mô hình kết hợp?

Mô hình kết hợp thường phù hợp với hệ thống nghiệp vụ có phần lõi ổn định nhưng phần mở rộng thay đổi theo sản phẩm, đối tác hoặc kênh tích hợp.

Ví dụ một đơn hàng có các thuộc tính cốt lõi:

- order_id
- customer_id
- order_date
- status
- total_amount

Các thuộc tính mở rộng có thể khác nhau:

- Đơn hàng giao hàng: deliveryWindow, deliveryInstructions.
- Đơn hàng quà tặng: giftMessage, giftWrap.
- Đơn hàng doanh nghiệp: purchaseOrderReference, costCenter.
- Đơn hàng quốc tế: customsCode, importNotes.

Không nhất thiết phải thêm tất cả các trường tùy chọn vào bảng ORDERS. Có thể giữ trường thường xuyên truy vấn trong cột quan hệ, còn dữ liệu đặc thù trong JSON.

~~~sql
CREATE TABLE orders (
  order_id      NUMBER PRIMARY KEY,
  customer_id   NUMBER NOT NULL,
  order_date    TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
  status        VARCHAR2(20) NOT NULL,
  total_amount  NUMBER(14, 2) NOT NULL,
  extra_data    CLOB,
  CONSTRAINT orders_customer_fk
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
  CONSTRAINT orders_total_ck CHECK (total_amount >= 0),
  CONSTRAINT orders_extra_json_ck CHECK (extra_data IS JSON)
);
~~~

Một hàng có thể chứa:

~~~json
{
  "giftWrap": true,
  "giftMessage": "Happy birthday!",
  "deliveryWindow": {
    "from": "2026-11-20T09:00:00+07:00",
    "to": "2026-11-20T12:00:00+07:00"
  }
}
~~~

Truy vấn trường quan hệ và trường JSON:

~~~sql
SELECT order_id,
       customer_id,
       status,
       JSON_VALUE(
         extra_data,
         '$.deliveryWindow.from'
         RETURNING VARCHAR2(40)
       ) AS delivery_from
  FROM orders
 WHERE status = 'NEW'
   AND JSON_VALUE(extra_data, '$.giftWrap' RETURNING VARCHAR2(5)) = 'true';
~~~

Trong thực tế, cần thống nhất cách biểu diễn boolean và kiểu trả về theo phiên bản Oracle. Với các thuộc tính được truy vấn thường xuyên, hãy xem xét function-based index hoặc JSON search index phù hợp với workload.

## 6. Phân biệt dữ liệu cốt lõi, dữ liệu mở rộng và dữ liệu dẫn xuất

Một cách hữu ích để phân chia mô hình là phân loại thuộc tính theo vai trò:

| Loại thuộc tính | Ví dụ | Vị trí thường phù hợp |
|---|---|---|
| Định danh và quan hệ | order_id, customer_id, product_id | Cột quan hệ và khóa |
| Trạng thái nghiệp vụ | status, approved_at, total_amount | Cột quan hệ, có constraint/index |
| Thuộc tính ổn định, truy vấn thường xuyên | order_date, region_code | Cột quan hệ |
| Thuộc tính mở rộng, tùy chọn | giftMessage, partnerMetadata | JSON/XML nếu phù hợp |
| Nội dung tài liệu gốc | Payload nhận từ đối tác | CLOB/BLOB/XMLTYPE hoặc JSON gốc |
| Dữ liệu tổng hợp/dẫn xuất | số đơn theo ngày, tổng doanh thu | View, materialized view hoặc bảng tổng hợp |

Đừng đưa một trường vào JSON chỉ vì nó ít xuất hiện. Nếu trường đó quyết định khóa, quyền truy cập, trạng thái, ràng buộc hoặc báo cáo quan trọng, cột quan hệ có thể phù hợp hơn.

Ngược lại, đừng tạo hàng chục cột nullable cho các thuộc tính đặc thù chỉ xuất hiện ở một vài loại đối tượng nếu chúng không cần được truy vấn quan hệ thường xuyên. JSON có thể giúp biểu diễn phần mở rộng tự nhiên hơn.

## 7. Dữ liệu tham chiếu và quan hệ giữa tài liệu

Trong mô hình tài liệu, có thể lồng toàn bộ dữ liệu liên quan hoặc chỉ lưu mã tham chiếu. Quyết định này nên dựa trên quyền sở hữu dữ liệu và cách cập nhật.

### Lồng dữ liệu khi nó thuộc cùng một aggregate

Ví dụ các dòng hàng của đơn hàng thường được tạo và đọc cùng đơn hàng. Có thể lồng chúng trong một JSON document:

~~~json
{
  "orderId": 1001,
  "items": [
    {"lineNo": 1, "productId": 10, "quantity": 2},
    {"lineNo": 2, "productId": 20, "quantity": 3}
  ]
}
~~~

Việc lồng giúp lấy một tài liệu trong một lần đọc. Tuy nhiên, nếu sản phẩm là thực thể độc lập có giá, mô tả và tồn kho được nhiều đơn hàng dùng chung, không nên sao chép toàn bộ bản ghi sản phẩm vào mọi đơn hàng như thể đó là dữ liệu chính.

### Dùng tham chiếu khi thực thể được quản lý độc lập

Ví dụ JSON chỉ lưu productId. Khi cần thông tin hiện tại của sản phẩm, truy vấn bảng PRODUCTS. Nếu cần lưu lại mô tả và giá tại thời điểm đặt hàng, có thể lưu snapshot các giá trị đó trong ORDER_ITEMS vì đây là thông tin lịch sử của giao dịch.

Điểm quan trọng là phân biệt:

- **Tham chiếu:** trỏ đến thực thể đang được quản lý ở nơi khác.
- **Snapshot:** bản sao giá trị tại một thời điểm để bảo toàn lịch sử.
- **Dữ liệu lồng:** thành phần thuộc cùng vòng đời và thường được đọc/ghi cùng aggregate.

Nếu tham chiếu phải được bảo đảm tồn tại, khóa ngoại quan hệ là cách trực tiếp và mạnh. Một mã nằm bên trong JSON không tự có FOREIGN KEY constraint đến bảng khác.

## 8. JSON hay XML cho mô hình tài liệu?

Nếu chọn lưu tài liệu, định dạng cũng cần phù hợp với hệ thống:

| Tiêu chí | JSON | XML |
|---|---|---|
| Cấu trúc | Object, array, scalar | Element, attribute, text node |
| Tích hợp API web | Phổ biến trong REST và ứng dụng hiện đại | Thường gặp trong SOAP và tích hợp doanh nghiệp |
| Namespace | Không có namespace theo mô hình XML | Hỗ trợ namespace URI và prefix |
| Schema | Có thể xác thực theo JSON Schema ở tầng ứng dụng hoặc cơ chế phù hợp | Có XML Schema (XSD) và các công cụ xác thực |
| Truy vấn Oracle | SQL/JSON, JSON_VALUE, JSON_QUERY, JSON_TABLE | XMLTYPE, XQuery, XMLTABLE, XMLQUERY |
| Kiểu lưu | VARCHAR2/CLOB/BLOB; kiểu JSON gốc từ 21c | XMLTYPE hoặc văn bản/LOB theo thiết kế |

JSON thường phù hợp với payload API, cấu hình và dữ liệu dạng object/array. XML phù hợp khi hợp đồng tích hợp yêu cầu XSD, namespace, tài liệu có cấu trúc phức tạp hoặc hệ thống SOAP hiện hữu.

Không nên chuyển đổi XML sang JSON chỉ vì JSON gọn hơn nếu hệ thống nhận yêu cầu XML có schema và namespace cụ thể. Tương tự, không nên tạo XML mới nếu tất cả bên tích hợp đã thống nhất JSON và không có yêu cầu XML.

## 9. Oracle hỗ trợ lưu trữ và truy vấn như thế nào?

### JSON dạng văn bản

Trên các phiên bản trước 21c, JSON có thể được lưu trong VARCHAR2, CLOB hoặc BLOB. Dùng CHECK constraint `IS JSON` để kiểm tra cú pháp:

~~~sql
CREATE TABLE api_messages (
  message_id NUMBER PRIMARY KEY,
  payload    CLOB NOT NULL,
  CONSTRAINT api_messages_json_ck CHECK (payload IS JSON)
);
~~~

SQL/JSON functions cho phép trích xuất dữ liệu:

~~~sql
SELECT message_id,
       JSON_VALUE(payload, '$.eventType' RETURNING VARCHAR2(50)) AS event_type,
       JSON_VALUE(payload, '$.createdAt' RETURNING VARCHAR2(40)) AS created_at
  FROM api_messages;
~~~

### JSON gốc

Từ Oracle Database 21c, có thể khai báo kiểu SQL JSON:

~~~sql
CREATE TABLE api_messages_native (
  message_id NUMBER PRIMARY KEY,
  payload    JSON NOT NULL
);
~~~

Kiểu JSON gốc dùng OSON và có thể truy vấn bằng các SQL/JSON functions. Khi trao đổi với hệ thống ngoài, serialize thành JSON văn bản; không gửi byte OSON như payload JSON thông thường.

### XMLTYPE

Với XML, có thể lưu dữ liệu trong cột XMLTYPE:

~~~sql
CREATE TABLE partner_xml_messages (
  message_id NUMBER PRIMARY KEY,
  payload    XMLTYPE
);
~~~

XMLTABLE có thể ánh xạ nút XML thành hàng và cột SQL. XMLSERIALIZE có thể xuất XMLTYPE thành CLOB hoặc BLOB khi cần truyền ra ngoài.

Việc chọn kiểu lưu XMLTYPE, CLOB/BLOB hay JSON gốc còn phụ thuộc phiên bản Oracle, cấu hình lưu trữ, công cụ tích hợp và nhu cầu giữ nguyên byte đầu vào.

## 10. Truy vấn và chỉ mục trong mô hình kết hợp

Một lợi ích của mô hình kết hợp là các trường quan hệ vẫn có thể dùng chỉ mục B-tree và constraint truyền thống, trong khi thuộc tính JSON được truy vấn bằng SQL/JSON.

Ví dụ tạo chỉ mục trên trạng thái quan hệ:

~~~sql
CREATE INDEX orders_status_ix ON orders(status);
~~~

Nếu thường xuyên lọc theo thuộc tính `deliveryWindow.from` trong JSON, có thể cân nhắc function-based index:

~~~sql
CREATE INDEX orders_delivery_from_ix
ON orders (
  JSON_VALUE(
    extra_data,
    '$.deliveryWindow.from'
    RETURNING VARCHAR2(40)
  )
);
~~~

Truy vấn cần dùng biểu thức tương thích với chỉ mục:

~~~sql
SELECT order_id, customer_id
  FROM orders
 WHERE JSON_VALUE(
         extra_data,
         '$.deliveryWindow.from'
         RETURNING VARCHAR2(40)
       ) >= '2026-11-20T00:00:00+07:00';
~~~

Đây là ví dụ minh họa cho giá trị thời gian được lưu dưới dạng chuỗi ISO 8601. So sánh chuỗi chỉ an toàn khi định dạng và timezone được chuẩn hóa. Với nghiệp vụ thời gian cần tính toán, nên cân nhắc trích xuất sang kiểu DATE/TIMESTAMP phù hợp hoặc lưu trường quan trọng thành cột quan hệ.

Với JSON có nhiều đường dẫn được tìm kiếm, JSON search index có thể phù hợp. Với XML, XMLIndex có thể hỗ trợ truy vấn XQuery/XMLTABLE. Chỉ mục làm tăng chi phí ghi và dung lượng, vì vậy hãy tạo theo mẫu truy vấn thực tế và xác nhận bằng execution plan.

## 11. Giao dịch, tính nhất quán và cập nhật đồng thời

Mô hình dữ liệu ảnh hưởng đến cách bảo vệ tính nhất quán:

**Trong mô hình quan hệ**, một giao dịch có thể INSERT/UPDATE nhiều bảng, với khóa ngoại và constraint được Oracle kiểm tra. Nếu một bước thất bại, có thể rollback toàn bộ giao dịch.

**Trong mô hình tài liệu**, một tài liệu thường được cập nhật như một giá trị thuộc một hàng. Việc cập nhật tài liệu không tự bảo vệ các tham chiếu đến bảng khác hoặc quy tắc giữa nhiều tài liệu. Ứng dụng cần quản lý các quy tắc đó hoặc đưa chúng về phần quan hệ.

**Trong mô hình kết hợp**, giao dịch có thể cập nhật các cột quan hệ và cột JSON trong cùng hàng. Nếu cần cập nhật nhiều bảng liên quan, hãy thực hiện trong cùng giao dịch và dùng khóa/ràng buộc phù hợp.

Ví dụ, khi xác nhận đơn hàng, trạng thái đơn hàng và việc trừ tồn kho cần được bảo vệ như một đơn vị nghiệp vụ. Không nên chỉ cập nhật trường status trong JSON nếu tồn kho và thanh toán vẫn nằm ở bảng quan hệ. Hãy xác định rõ nguồn dữ liệu có thẩm quyền và phạm vi giao dịch.

Nếu nhiều tiến trình cùng cập nhật một tài liệu lớn, có thể xảy ra xung đột trên cùng hàng. Việc chia tài liệu thành các aggregate nhỏ hơn hoặc đưa các phần được cập nhật độc lập thành bảng riêng có thể giảm tranh chấp và lượng dữ liệu phải ghi lại.

## 12. Schema evolution và quản lý phiên bản tài liệu

Một ưu điểm của JSON là có thể thêm trường tùy chọn mà không phải thay đổi cấu trúc bảng. Tuy nhiên, linh hoạt không có nghĩa là không cần quản lý schema.

Ví dụ tài liệu phiên bản 1:

~~~json
{
  "schemaVersion": 1,
  "customerId": 501,
  "preferences": {
    "language": "vi"
  }
}
~~~

Tài liệu phiên bản 2 bổ sung múi giờ:

~~~json
{
  "schemaVersion": 2,
  "customerId": 501,
  "preferences": {
    "language": "vi",
    "timeZone": "Asia/Ho_Chi_Minh"
  }
}
~~~

Ứng dụng có thể đọc cả hai phiên bản và gán giá trị mặc định khi trường mới không tồn tại. Nên có `schemaVersion` khi tài liệu có khả năng thay đổi cấu trúc theo thời gian.

Một kế hoạch schema evolution nên xác định:

- Trường nào bắt buộc và trường nào tùy chọn.
- Kiểu dữ liệu và quy ước tên trường.
- Giá trị mặc định khi trường chưa tồn tại.
- Quy tắc tương thích ngược và tương thích xuôi.
- Cách chuyển đổi tài liệu cũ.
- Thời điểm ngừng hỗ trợ phiên bản cũ.
- Cách kiểm tra dữ liệu trước và sau migration.

Với dữ liệu quan hệ, schema evolution thường cần ALTER TABLE, thêm bảng hoặc thay đổi constraint. Với JSON/XML, cấu trúc có thể thay đổi theo từng tài liệu nhưng ứng dụng vẫn cần hợp đồng phiên bản để tránh các client hiểu khác nhau.

## 13. JSON Relational Duality Views trong Oracle Database 23ai

Oracle Database 23c, được phát hành với tên 23ai, giới thiệu JSON Relational Duality Views. Cơ chế này cho phép trình bày dữ liệu được lưu trong các bảng quan hệ dưới dạng tài liệu JSON. Ứng dụng có thể làm việc với giao diện tài liệu, trong khi dữ liệu nền vẫn được tổ chức theo bảng và quan hệ.

Duality View hữu ích khi:

- Database cần giữ dữ liệu cốt lõi trong mô hình quan hệ.
- Ứng dụng muốn đọc hoặc cập nhật theo cấu trúc JSON document.
- Nhiều ứng dụng cần các cách biểu diễn khác nhau trên cùng dữ liệu.
- Muốn tránh sao chép cùng một dữ liệu vào một kho JSON riêng chỉ để phục vụ API.

Đây là mô hình kết hợp ở cấp độ truy cập dữ liệu. Duality View không làm mất các bảng quan hệ bên dưới; khóa, quan hệ và quy tắc dữ liệu vẫn cần được thiết kế. Khả năng ghi qua view còn phụ thuộc cấu trúc view và các quy tắc mà Oracle hỗ trợ. Cần kiểm tra tài liệu đúng release và thử các thao tác insert/update/delete trước khi dùng trong ứng dụng.

Duality View cũng không có nghĩa mọi tài liệu JSON trong hệ thống đều nên chuyển thành relational duality. Nếu tài liệu là payload gốc từ đối tác, có vòng đời độc lập hoặc cần giữ nguyên nội dung, cột JSON/XML riêng vẫn có thể phù hợp.

## 14. Các anti-pattern cần tránh

**Lưu mọi thứ trong một JSON document duy nhất:** tài liệu quá lớn, nhiều phần được cập nhật độc lập và nhiều quan hệ tham chiếu sẽ khiến việc truy vấn, cập nhật và kiểm soát tính nhất quán khó khăn.

**Lặp lại dữ liệu dùng chung trong nhiều tài liệu:** sao chép tên khách hàng, thông tin sản phẩm hoặc trạng thái dùng chung vào nhiều tài liệu có thể tạo dữ liệu không nhất quán. Chỉ snapshot khi cần giữ giá trị lịch sử tại một thời điểm.

**Đưa khóa nghiệp vụ vào JSON:** nếu một trường là khóa chính, khóa ngoại, khóa tìm kiếm thường xuyên hoặc cần UNIQUE, hãy cân nhắc cột quan hệ.

**Dùng mô hình quan hệ cho mọi thuộc tính tùy chọn:** hàng chục cột chỉ có ý nghĩa với một loại bản ghi có thể tạo schema khó hiểu và nhiều NULL. Phần mở rộng có thể phù hợp với JSON.

**Xem IS JSON là validation nghiệp vụ:** constraint này xác nhận cú pháp JSON, không thay thế kiểm tra kiểu, miền giá trị, quan hệ và quy tắc nghiệp vụ.

**Không có phiên bản schema cho tài liệu:** thêm hoặc đổi tên trường mà không có kế hoạch tương thích khiến các client cũ có thể đọc sai dữ liệu.

**Truy vấn JSON mà không có chiến lược chỉ mục:** lọc liên tục trên các đường dẫn JSON có thể tốn tài nguyên. Hãy đo workload và cân nhắc function-based index hoặc JSON search index.

**Dùng XML/JSON chỉ để né thiết kế bảng:** nếu nghiệp vụ cần khóa ngoại, join và tổng hợp thường xuyên, đưa mọi dữ liệu vào một document có thể làm tăng logic ứng dụng và giảm khả năng kiểm soát.

## 15. Quy trình lựa chọn mô hình cho một miền nghiệp vụ

Khi thiết kế một thực thể, hãy trả lời lần lượt:

1. **Ranh giới dữ liệu:** dữ liệu nào luôn được tạo, đọc và cập nhật cùng nhau?
2. **Quan hệ:** dữ liệu có tham chiếu đến thực thể độc lập hay có quan hệ nhiều-nhiều không?
3. **Tính toàn vẹn:** quy tắc nào phải được database bảo vệ bằng khóa, constraint hoặc giao dịch?
4. **Truy vấn:** người dùng lọc, join, group và báo cáo theo những trường nào?
5. **Tần suất thay đổi:** trường nào ổn định, trường nào thay đổi theo sản phẩm hoặc đối tác?
6. **Kích thước:** tài liệu có thể lớn đến mức nào và có cần đọc theo luồng không?
7. **Tích hợp:** hệ thống nhận/gửi JSON, XML hay dữ liệu quan hệ?
8. **Phiên bản Oracle:** database có hỗ trợ kiểu JSON gốc, SQL/JSON hoặc tính năng XML cần dùng không?
9. **Vận hành:** backup, restore, replication, export/import và client driver có hỗ trợ cách lưu được chọn không?
10. **Đo lường:** thử truy vấn và cập nhật trên dữ liệu đại diện, kiểm tra execution plan, dung lượng và mức tranh chấp.

Sau khi trả lời, phân loại trường thành cốt lõi, mở rộng, snapshot và dữ liệu dẫn xuất. Chọn mô hình quan hệ cho phần cốt lõi cần toàn vẹn và truy vấn liên bảng; chọn JSON/XML cho aggregate hoặc payload có cấu trúc linh hoạt; kết hợp hai cách khi hệ thống có cả hai loại nhu cầu.

## 16. Ví dụ thiết kế kết hợp hoàn chỉnh

Giả sử hệ thống quản lý đơn hàng cần:

- Khách hàng được quản lý độc lập.
- Đơn hàng có trạng thái, thời gian và tổng tiền.
- Mỗi đơn hàng có nhiều dòng hàng.
- Một số kênh bán hàng có metadata riêng.
- Ứng dụng cần xuất đơn hàng dưới dạng JSON.

Thiết kế quan hệ:

~~~sql
CREATE TABLE customers (
  customer_id NUMBER PRIMARY KEY,
  full_name   VARCHAR2(200) NOT NULL,
  email       VARCHAR2(320) UNIQUE
);

CREATE TABLE products (
  product_id   NUMBER PRIMARY KEY,
  product_name VARCHAR2(200) NOT NULL
);

CREATE TABLE orders (
  order_id     NUMBER PRIMARY KEY,
  customer_id  NUMBER NOT NULL,
  order_date   TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
  status       VARCHAR2(20) NOT NULL,
  total_amount NUMBER(14, 2) NOT NULL,
  metadata     CLOB,
  CONSTRAINT orders_customer_fk
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
  CONSTRAINT orders_status_ck
    CHECK (status IN ('NEW', 'PAID', 'SHIPPED', 'CANCELLED')),
  CONSTRAINT orders_total_ck CHECK (total_amount >= 0),
  CONSTRAINT orders_metadata_json_ck CHECK (metadata IS JSON)
);

CREATE TABLE order_items (
  order_id   NUMBER NOT NULL,
  line_no    NUMBER NOT NULL,
  product_id NUMBER NOT NULL,
  quantity   NUMBER(10, 2) NOT NULL,
  unit_price NUMBER(14, 2) NOT NULL,
  CONSTRAINT order_items_pk PRIMARY KEY (order_id, line_no),
  CONSTRAINT order_items_order_fk
    FOREIGN KEY (order_id) REFERENCES orders(order_id),
  CONSTRAINT order_items_product_fk
    FOREIGN KEY (product_id) REFERENCES products(product_id),
  CONSTRAINT order_items_quantity_ck CHECK (quantity > 0),
  CONSTRAINT order_items_price_ck CHECK (unit_price >= 0)
);
~~~

Trong thiết kế này:

- CUSTOMERS và PRODUCTS là thực thể độc lập.
- ORDERS giữ các thuộc tính cốt lõi và quan hệ đến khách hàng.
- ORDER_ITEMS biểu diễn quan hệ một-nhiều và có khóa ngoại đến sản phẩm.
- METADATA chứa thuộc tính đặc thù theo kênh bán hàng, được xác nhận cú pháp JSON.

Truy vấn đơn hàng và các dòng hàng bằng SQL:

~~~sql
SELECT o.order_id,
       o.order_date,
       o.status,
       c.full_name,
       i.line_no,
       p.product_name,
       i.quantity,
       i.unit_price
  FROM orders o
  JOIN customers c
    ON c.customer_id = o.customer_id
  JOIN order_items i
    ON i.order_id = o.order_id
  JOIN products p
    ON p.product_id = i.product_id
 WHERE o.order_id = 1001
 ORDER BY i.line_no;
~~~

Lấy một thuộc tính mở rộng từ JSON:

~~~sql
SELECT order_id,
       JSON_VALUE(
         metadata,
         '$.salesChannel'
         RETURNING VARCHAR2(30)
       ) AS sales_channel
  FROM orders
 WHERE order_id = 1001;
~~~

Xuất đơn hàng thành JSON bằng SQL:

~~~sql
SELECT JSON_OBJECT(
         'orderId' VALUE o.order_id,
         'orderDate' VALUE o.order_date,
         'status' VALUE o.status,
         'customer' VALUE JSON_OBJECT(
           'customerId' VALUE c.customer_id,
           'name' VALUE c.full_name
         ),
         'items' VALUE (
           SELECT JSON_ARRAYAGG(
                    JSON_OBJECT(
                      'lineNo' VALUE i.line_no,
                      'productId' VALUE i.product_id,
                      'productName' VALUE p.product_name,
                      'quantity' VALUE i.quantity,
                      'unitPrice' VALUE i.unit_price
                    )
                    ORDER BY i.line_no
                    RETURNING CLOB
                  )
             FROM order_items i
             JOIN products p
               ON p.product_id = i.product_id
            WHERE i.order_id = o.order_id
         ) FORMAT JSON
         RETURNING CLOB
       ) AS order_json
  FROM orders o
  JOIN customers c
    ON c.customer_id = o.customer_id
 WHERE o.order_id = 1001;
~~~

Đoạn SQL tạo JSON từ bảng quan hệ để trả cho API. Cú pháp và các tùy chọn RETURNING phụ thuộc phiên bản Oracle; hãy đối chiếu release khi triển khai. Nếu ứng dụng có nhiều kiểu tài liệu đầu ra, có thể tạo view hoặc API query riêng để tách hợp đồng JSON khỏi cấu trúc bảng.

## 17. Kiểm tra trước khi quyết định

Trước khi chốt mô hình, nên thử các tình huống thực tế:

- Thêm một thuộc tính mới vào tài liệu và kiểm tra client cũ.
- Truy vấn theo các trường quan hệ và trường JSON/XML.
- JOIN dữ liệu tài liệu với thực thể độc lập.
- Cập nhật đồng thời cùng một aggregate.
- Cập nhật nhiều bảng trong một giao dịch và rollback khi một bước lỗi.
- Nạp tài liệu sai định dạng hoặc thiếu trường bắt buộc.
- Kiểm tra dữ liệu trùng lặp và tham chiếu không tồn tại.
- Đo thời gian truy vấn, cập nhật, dung lượng và chi phí chỉ mục.
- Xuất/nhập dữ liệu qua các phiên bản Oracle và client driver được sử dụng.

Kết quả thử nghiệm giúp xác định phần nào nên là quan hệ, phần nào nên là tài liệu và phần nào cần được biểu diễn ở cả hai dạng qua view hoặc dữ liệu dẫn xuất.

## 18. Kết luận

Mô hình quan hệ phù hợp với dữ liệu cốt lõi có cấu trúc ổn định, quan hệ giữa thực thể rõ ràng và quy tắc toàn vẹn cần database bảo vệ. Mô hình tài liệu phù hợp với aggregate được đọc/ghi cùng nhau, payload tích hợp và cấu trúc linh hoạt. Mô hình kết hợp giữ khóa, trạng thái và dữ liệu thường xuyên truy vấn trong bảng quan hệ, đồng thời dùng JSON/XML cho phần mở rộng có vòng đời phù hợp.

Trong Oracle Database, SQL/JSON, kiểu JSON gốc từ 21c, XMLTYPE và các hàm SQL/XML cho phép kết hợp dữ liệu tài liệu với SQL quan hệ. Trên 23ai, JSON Relational Duality Views còn cung cấp cách làm việc với dữ liệu quan hệ qua giao diện JSON. Dù chọn cách nào, hãy xác định ranh giới aggregate, nguồn dữ liệu có thẩm quyền, quy tắc toàn vẹn, mẫu truy vấn và khả năng tương thích trước khi triển khai. Mô hình tốt là mô hình làm cho dữ liệu nhất quán, truy vấn dễ hiểu và thay đổi có kiểm soát trong suốt vòng đời hệ thống.
