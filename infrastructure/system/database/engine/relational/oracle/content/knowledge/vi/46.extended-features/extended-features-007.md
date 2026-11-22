# SQL property graph, mô hình đồ thị và truy vấn theo phiên bản hỗ trợ

SQL Property Graph cho phép mô hình hóa dữ liệu quan hệ dưới dạng đồ thị gồm **đỉnh (vertex)**, **cạnh (edge)**, **nhãn (label)** và **thuộc tính (property)**, sau đó truy vấn các quan hệ bằng mẫu đồ thị ngay trong SQL. Từ Oracle Database 23ai, Oracle cung cấp cú pháp SQL Property Graph theo hướng SQL/PGQ với hai thành phần cốt lõi: `CREATE PROPERTY GRAPH` để định nghĩa graph trên các bảng quan hệ và `GRAPH_TABLE` để khớp mẫu đồ thị trong câu SELECT.

Mô hình này hữu ích khi câu hỏi nghiệp vụ tập trung vào quan hệ và đường đi: khách hàng liên quan tới tài khoản nào, tài khoản chuyển tiền qua những tài khoản trung gian nào, nhân viên báo cáo cho ai, thiết bị nào chia sẻ định danh, hoặc một sản phẩm được kết nối với những sản phẩm nào.

SQL Property Graph không thay thế mô hình quan hệ. Các bảng vẫn là nguồn dữ liệu; định nghĩa graph ánh xạ bảng và cột thành vertex/edge/property để truy vấn quan hệ theo cách tự nhiên hơn. Với hệ thống đã lưu dữ liệu trong Oracle Database, đây là cách bổ sung góc nhìn đồ thị mà không nhất thiết phải chuyển toàn bộ dữ liệu sang một graph database riêng.

## 1. Graph là gì?

Đồ thị là cấu trúc gồm các đỉnh và cạnh mô tả mối liên hệ giữa các thực thể.

- **Vertex:** đại diện một thực thể, ví dụ người dùng, tài khoản, sản phẩm hoặc thành phố.
- **Edge:** đại diện mối quan hệ giữa hai vertex, ví dụ chuyển tiền, kết bạn, mua hàng hoặc tuyến đường.
- **Label:** phân loại vertex/edge, ví dụ person, account, transfer, knows.
- **Property:** dữ liệu mô tả vertex/edge, ví dụ tên, số dư, thời điểm giao dịch hoặc trọng số.
- **Key:** xác định duy nhất một vertex hoặc edge trong graph.

Ví dụ mạng xã hội:

~~~text
       (An) --------knows--------> (Bình)
        |                            |
        | follows                    | knows
        v                            v
      (Chi) <---------knows--------- (Dũng)
~~~

Vertex là người dùng. Edge mô tả ai biết ai hoặc ai theo dõi ai. Thuộc tính của vertex có thể là tên, tuổi, thành phố; thuộc tính của edge có thể là thời điểm kết nối hoặc loại quan hệ.

### 1.1 Đồ thị có hướng

Edge có hướng xác định source và destination. Ví dụ:

~~~text
(Account A) --transfers--> (Account B)
~~~

Chuyển tiền từ A sang B không đồng nghĩa với chuyển tiền từ B sang A. Vì vậy, edge cần giữ hướng.

### 1.2 Đồ thị vô hướng

Một quan hệ như hai người là bạn có thể được xem là vô hướng ở tầng nghiệp vụ. Khi lưu bằng bảng quan hệ, có thể biểu diễn một quan hệ bằng một edge và truy vấn theo cú pháp phù hợp, hoặc lưu hai hướng nếu ứng dụng cần phân biệt chiều. Cần thống nhất quy ước để không đếm đôi quan hệ.

### 1.3 Đồ thị đa cạnh và self-loop

Hai vertex có thể có nhiều edge khác nhau. Ví dụ hai tài khoản có thể chuyển tiền nhiều lần. Mỗi lần chuyển tiền phải có edge key riêng, nếu không các giao dịch khác nhau sẽ bị gộp sai thành một quan hệ.

Một edge cũng có thể nối một vertex tới chính nó nếu mô hình nghiệp vụ cho phép. Ví dụ một node có quan hệ tự tham chiếu. Không tự loại self-loop nếu dữ liệu nguồn có ý nghĩa đó.

## 2. Property graph và dữ liệu quan hệ

Một property graph được tạo từ bảng quan hệ:

| Bảng quan hệ | Thành phần graph |
|---|---|
| Bảng PERSON | Vertex table |
| PERSON_ID | Vertex key |
| NAME, CITY, AGE | Vertex properties |
| Bảng KNOWS | Edge table |
| FRIENDSHIP_ID | Edge key |
| PERSON_A_ID | Source key |
| PERSON_B_ID | Destination key |
| SINCE_DATE, RELATION_TYPE | Edge properties |

Graph definition nói cho Oracle biết cách ánh xạ dữ liệu. Các hàng trong bảng vertex trở thành vertex; các hàng trong bảng edge trở thành mối liên hệ giữa vertex tương ứng.

~~~text
PERSON table                       KNOWS table
+-----------+------+               +---------------+------------+------------+
| PERSON_ID | NAME |               | FRIENDSHIP_ID | PERSON_A_ID| PERSON_B_ID|
+-----------+------+               +---------------+------------+------------+
| 1         | An   |               | 101           | 1          | 2          |
| 2         | Binh |               | 102           | 2          | 3          |
| 3         | Chi  |               | 103           | 1          | 3          |
+-----------+------+               +---------------+------------+------------+
        |                                    |
        +---------------+--------------------+
                        v
                Property graph

                 (An) ----101----> (Binh)
                   \                |
                    \               | 102
                     \              v
                      +----------> (Chi)
~~~

### 2.1 Property graph khác RDF graph

Property graph và RDF graph đều biểu diễn dữ liệu dạng đồ thị nhưng mô hình khác nhau.

| Tiêu chí | Property graph | RDF graph |
|---|---|---|
| Thành phần | Vertex, edge, label, property | Subject, predicate, object |
| Thuộc tính | Có thể gắn trực tiếp lên vertex và edge | Thường biểu diễn bằng triple |
| Mối quan hệ | Edge là đối tượng có thể có key/property | Predicate là quan hệ giữa subject/object |
| Truy vấn | SQL/PGQ, graph pattern | SPARQL |
| Phù hợp | Quan hệ nghiệp vụ, network, path | Knowledge graph, ontology, linked data |

Không nên dùng thuật ngữ property graph và RDF thay thế cho nhau. Oracle có các công nghệ graph khác nhau; phải chọn mô hình và ngôn ngữ truy vấn theo nguồn dữ liệu, ứng dụng và phiên bản.

### 2.2 Property graph khác bảng adjacency thuần

Một bảng có FROM_ID và TO_ID đã lưu quan hệ dạng cạnh, nhưng chưa tự nó là một SQL Property Graph. Graph object còn định nghĩa vertex/edge tables, keys, source/destination mapping, labels và properties. Định nghĩa này giúp câu truy vấn graph diễn đạt theo vertex/edge thay vì phải tự viết nhiều self-join.

## 3. Mô hình ví dụ: tài khoản và giao dịch

Xét hệ thống ngân hàng nhỏ:

- ACCOUNTS lưu tài khoản.
- TRANSFERS lưu giao dịch chuyển tiền.

Một tài khoản là vertex. Một giao dịch là edge có hướng từ tài khoản gửi sang tài khoản nhận.

### 3.1 Tạo bảng vertex

~~~sql
CREATE TABLE accounts (
    account_id NUMBER
        CONSTRAINT accounts_pk PRIMARY KEY,
    account_name VARCHAR2(100) NOT NULL,
    account_type VARCHAR2(30),
    city VARCHAR2(80),
    opened_at TIMESTAMP
);
~~~

### 3.2 Tạo bảng edge

~~~sql
CREATE TABLE transfers (
    transfer_id NUMBER
        CONSTRAINT transfers_pk PRIMARY KEY,
    from_account_id NUMBER NOT NULL,
    to_account_id NUMBER NOT NULL,
    amount NUMBER(18,2) NOT NULL,
    transfer_time TIMESTAMP NOT NULL,
    transfer_status VARCHAR2(20),
    CONSTRAINT transfers_from_fk
        FOREIGN KEY (from_account_id)
        REFERENCES accounts(account_id),
    CONSTRAINT transfers_to_fk
        FOREIGN KEY (to_account_id)
        REFERENCES accounts(account_id),
    CONSTRAINT transfers_amount_ck
        CHECK (amount > 0)
);
~~~

Foreign key trong mô hình quan hệ bảo đảm source/destination trỏ tới tài khoản tồn tại. Graph definition cũng cần khai báo source và destination mapping tương ứng.

### 3.3 Nạp dữ liệu minh họa

~~~sql
INSERT INTO accounts VALUES
    (1, 'An', 'PERSONAL', 'Ha Noi', SYSTIMESTAMP - INTERVAL '3' YEAR);
INSERT INTO accounts VALUES
    (2, 'Binh', 'BUSINESS', 'Da Nang', SYSTIMESTAMP - INTERVAL '2' YEAR);
INSERT INTO accounts VALUES
    (3, 'Chi', 'PERSONAL', 'Ho Chi Minh City', SYSTIMESTAMP - INTERVAL '1' YEAR);
INSERT INTO accounts VALUES
    (4, 'Dung', 'BUSINESS', 'Ha Noi', SYSTIMESTAMP - INTERVAL '6' MONTH);

INSERT INTO transfers VALUES
    (1001, 1, 2, 1500000, SYSTIMESTAMP - INTERVAL '20' DAY, 'POSTED');
INSERT INTO transfers VALUES
    (1002, 2, 3, 500000, SYSTIMESTAMP - INTERVAL '18' DAY, 'POSTED');
INSERT INTO transfers VALUES
    (1003, 1, 3, 250000, SYSTIMESTAMP - INTERVAL '10' DAY, 'POSTED');
INSERT INTO transfers VALUES
    (1004, 3, 4, 700000, SYSTIMESTAMP - INTERVAL '5' DAY, 'POSTED');

COMMIT;
~~~

Các giá trị chỉ phục vụ lab; không đại diện dữ liệu ngân hàng thực tế.

## 4. Định nghĩa SQL Property Graph

Trong các phiên bản Oracle Database hỗ trợ SQL Property Graph, có thể tạo graph schema object bằng `CREATE PROPERTY GRAPH`.

Ví dụ:

~~~sql
CREATE PROPERTY GRAPH accounts_graph
    VERTEX TABLES (
        accounts
            KEY (account_id)
            LABEL account
            PROPERTIES (
                account_id,
                account_name,
                account_type,
                city,
                opened_at
            )
    )
    EDGE TABLES (
        transfers
            KEY (transfer_id)
            SOURCE KEY (from_account_id)
                REFERENCES accounts (account_id)
            DESTINATION KEY (to_account_id)
                REFERENCES accounts (account_id)
            LABEL transfer
            PROPERTIES (
                transfer_id,
                amount,
                transfer_time,
                transfer_status
            )
    );
~~~

Tên graph là ACCOUNTS_GRAPH. Bảng ACCOUNTS được ánh xạ thành vertex có label account. Bảng TRANSFERS được ánh xạ thành edge có label transfer.

### 4.1 VERTEX TABLES

Mệnh đề VERTEX TABLES xác định nguồn vertex:

~~~sql
VERTEX TABLES (
    accounts
        KEY (account_id)
        LABEL account
        PROPERTIES (account_id, account_name, city)
)
~~~

- ACCOUNTS: bảng nguồn.
- KEY (account_id): cột định danh duy nhất vertex.
- LABEL account: label của vertex.
- PROPERTIES: các cột được đưa thành property có thể truy cập trong graph query.

### 4.2 EDGE TABLES

Mệnh đề EDGE TABLES xác định nguồn edge:

~~~sql
EDGE TABLES (
    transfers
        KEY (transfer_id)
        SOURCE KEY (from_account_id)
            REFERENCES accounts (account_id)
        DESTINATION KEY (to_account_id)
            REFERENCES accounts (account_id)
        LABEL transfer
        PROPERTIES (transfer_id, amount, transfer_time)
)
~~~

- KEY (transfer_id): định danh một edge.
- SOURCE KEY: cột hoặc nhóm cột xác định vertex nguồn.
- DESTINATION KEY: cột hoặc nhóm cột xác định vertex đích.
- REFERENCES: bảng vertex và key được tham chiếu.
- LABEL transfer: phân loại edge.
- PROPERTIES: các thuộc tính của edge.

### 4.3 Key phải xác định duy nhất

Vertex key phải xác định duy nhất một hàng vertex. Edge key phải xác định duy nhất một hàng edge. Nếu key không duy nhất, graph có thể không ánh xạ đúng các thực thể hoặc quan hệ.

Nên dùng primary key/unique constraint trong bảng quan hệ và khai báo graph key khớp với các cột đó. Không chọn một cột chỉ vì nó có vẻ duy nhất trong dữ liệu hiện tại.

### 4.4 Source và destination phải cùng khớp key

Nếu vertex key là ACCOUNT_ID, source/destination columns trong TRANSFERS phải tham chiếu đúng kiểu và giá trị của ACCOUNT_ID. Với composite key, thứ tự các cột trong source/destination mapping phải tương ứng với thứ tự key được tham chiếu.

### 4.5 Properties là phần graph query nhìn thấy

Chỉ khai báo những cột cần thiết cho graph pattern và kết quả. Tránh đưa mọi cột nhạy cảm vào property graph nếu người truy vấn graph không cần truy cập chúng.

## 5. Truy vấn bằng GRAPH_TABLE

GRAPH_TABLE là table operator cho phép đưa graph pattern vào câu SQL. Kết quả graph pattern được trả về dưới dạng hàng quan hệ thông qua mệnh đề COLUMNS.

Ví dụ tìm giao dịch trực tiếp từ tài khoản An:

~~~sql
SELECT *
FROM GRAPH_TABLE (
    accounts_graph
    MATCH (a IS account) -[t IS transfer]-> (b IS account)
    WHERE a.account_name = 'An'
    COLUMNS (
        a.account_name AS sender,
        b.account_name AS receiver,
        t.amount AS amount,
        t.transfer_time AS transfer_time,
        t.transfer_status AS status
    )
);
~~~

Giải thích:

- ACCOUNTS_GRAPH: property graph đã tạo.
- (a IS account): vertex có label account, đặt biến là a.
- [t IS transfer]: edge có label transfer, đặt biến là t.
- ->: hướng từ source tới destination.
- (b IS account): vertex đích.
- WHERE: điều kiện lọc graph pattern theo property.
- COLUMNS: các giá trị trả về thành cột SQL.

GRAPH_TABLE có thể được dùng trong FROM như một nguồn hàng; có thể kết hợp với các bảng quan hệ khác, CTE, GROUP BY, ORDER BY và các thành phần SQL thông thường theo cú pháp release hỗ trợ.

### 5.1 Tìm các giao dịch đi ra từ tài khoản

~~~sql
SELECT sender,
       receiver,
       amount
FROM GRAPH_TABLE (
    accounts_graph
    MATCH (a IS account) -[t IS transfer]-> (b IS account)
    COLUMNS (
        a.account_name AS sender,
        b.account_name AS receiver,
        t.amount AS amount
    )
)
ORDER BY sender, receiver;
~~~

### 5.2 Lọc theo thuộc tính edge

~~~sql
SELECT *
FROM GRAPH_TABLE (
    accounts_graph
    MATCH (a IS account) -[t IS transfer]-> (b IS account)
    WHERE t.amount >= 500000
      AND t.transfer_status = 'POSTED'
    COLUMNS (
        a.account_name AS sender,
        b.account_name AS receiver,
        t.amount AS amount
    )
);
~~~

Điều kiện trong graph pattern giúp giới hạn kết quả theo thuộc tính vertex/edge. Có thể tiếp tục lọc kết quả ở outer SQL nếu cần.

### 5.3 Kết hợp với SQL aggregation

~~~sql
SELECT receiver,
       COUNT(*) AS incoming_transfer_count,
       SUM(amount) AS total_received
FROM GRAPH_TABLE (
    accounts_graph
    MATCH (a IS account) -[t IS transfer]-> (b IS account)
    COLUMNS (
        b.account_name AS receiver,
        t.amount AS amount
    )
)
GROUP BY receiver
ORDER BY total_received DESC;
~~~

Đây là điểm mạnh của SQL Property Graph: kết quả graph pattern vẫn tham gia được vào phép tổng hợp SQL.

## 6. Đọc một path gồm nhiều edge

Graph pattern có thể mô tả nhiều bước quan hệ trong cùng một mẫu.

Ví dụ tìm đường chuyển tiền gồm hai giao dịch:

~~~sql
SELECT *
FROM GRAPH_TABLE (
    accounts_graph
    MATCH
        (a IS account)
        -[t1 IS transfer]->
        (b IS account)
        -[t2 IS transfer]->
        (c IS account)
    COLUMNS (
        a.account_name AS start_account,
        b.account_name AS intermediate_account,
        c.account_name AS end_account,
        t1.amount AS first_amount,
        t2.amount AS second_amount
    )
);
~~~

Mẫu này tìm ba vertex nối với nhau bởi hai edge có hướng. Mỗi lần xuất hiện của t1 và t2 là một giao dịch trong bảng TRANSFERS.

### 6.1 Tìm quan hệ trung gian

Một truy vấn nhiều bước có thể trả lời:

- Tài khoản A có thể chuyển tới C thông qua B không?
- Nhân viên A báo cáo qua những cấp quản lý nào?
- Sản phẩm A liên quan đến sản phẩm C qua một danh mục trung gian?
- Thiết bị nào có chung node mạng?

### 6.2 Kiểm soát độ dài đường đi

Đường đi dài có thể làm số lượng kết quả tăng rất nhanh. Trước khi dùng variable-length path hoặc pattern nhiều bước:

- Xác định giới hạn số hop cần thiết.
- Lọc vertex/edge theo thời gian hoặc trạng thái.
- Hạn chế label và property.
- Tránh trả toàn bộ path nếu chỉ cần endpoint.
- Đo execution plan trên dữ liệu gần production.

Các toán tử path, quantifier, path variable và tùy chọn match có thể có khác biệt giữa Oracle release. Dùng cú pháp SQL/PGQ được tài liệu đúng phiên bản công bố, không copy cú pháp PGQL hoặc Cypher sang GRAPH_TABLE.

## 7. Label và nhiều loại thực thể

Một graph có thể biểu diễn nhiều loại vertex/edge.

Ví dụ mạng thương mại điện tử:

- Vertex labels: customer, product, store.
- Edge labels: purchased, viewed, sold_by, located_in.

Mỗi label cho biết loại thực thể/quan hệ. Query có thể chỉ khớp một loại hoặc kết hợp nhiều loại theo mô hình được khai báo.

### 7.1 Nhiều vertex table

Một graph có thể khai báo nhiều vertex tables:

~~~sql
VERTEX TABLES (
    customers
        KEY (customer_id)
        LABEL customer
        PROPERTIES (customer_id, customer_name, city),
    products
        KEY (product_id)
        LABEL product
        PROPERTIES (product_id, product_name, category)
)
~~~

### 7.2 Nhiều edge table

Có thể khai báo các quan hệ khác nhau:

~~~sql
EDGE TABLES (
    purchases
        KEY (purchase_id)
        SOURCE KEY (customer_id)
            REFERENCES customers (customer_id)
        DESTINATION KEY (product_id)
            REFERENCES products (product_id)
        LABEL purchased
        PROPERTIES (purchase_id, purchased_at, quantity),
    recommendations
        KEY (recommendation_id)
        SOURCE KEY (source_product_id)
            REFERENCES products (product_id)
        DESTINATION KEY (target_product_id)
            REFERENCES products (product_id)
        LABEL recommends
        PROPERTIES (recommendation_id, score)
)
~~~

Ví dụ minh họa cấu trúc; trước khi chạy phải bảo đảm các bảng, khóa và tên cột tương ứng đã tồn tại và cú pháp nhiều table trong graph DDL khớp release.

### 7.3 Label là ngữ nghĩa, không phải index

Label giúp phân loại và chọn mẫu. Nó không tự bảo đảm truy vấn nhanh. Hiệu năng còn phụ thuộc vào key, index quan hệ, statistics, cardinality và cách optimizer thực thi graph pattern.

## 8. Property và kiểu dữ liệu

Property là giá trị được expose từ cột của bảng vertex hoặc edge.

| Graph property | Cột quan hệ | Thành phần |
|---|---|---|
| account_id | ACCOUNTS.ACCOUNT_ID | Vertex |
| account_name | ACCOUNTS.ACCOUNT_NAME | Vertex |
| city | ACCOUNTS.CITY | Vertex |
| amount | TRANSFERS.AMOUNT | Edge |
| transfer_time | TRANSFERS.TRANSFER_TIME | Edge |
| transfer_status | TRANSFERS.TRANSFER_STATUS | Edge |

Nên dùng tên property rõ nghĩa và thống nhất giữa schema, graph definition và query.

### 8.1 Chọn property tối thiểu

Không đưa dữ liệu không cần thiết vào graph. Ví dụ, nếu graph dùng để phân tích đường đi giữa tài khoản, có thể chỉ cần account ID, account type và city; không nhất thiết expose số định danh cá nhân hoặc thông tin nhạy cảm.

### 8.2 Kiểu dữ liệu

Chọn kiểu SQL phù hợp với ý nghĩa:

- NUMBER cho ID, số lượng và giá trị tiền.
- VARCHAR2 cho tên, mã và trạng thái.
- DATE/TIMESTAMP cho thời gian.
- RAW/UUID representation theo quy ước nếu cần định danh.

Kiểm tra các kiểu dữ liệu được hỗ trợ làm property theo phiên bản. Không giả định mọi kiểu Oracle như LOB, object type hoặc datatype đặc thù đều có thể dùng như property trong mọi release.

### 8.3 NULL property

Property có thể mang NULL nếu cột nguồn cho phép. Query phải xác định rõ cách xử lý NULL, đặc biệt trong filter, equality và tính toán số liệu. Nếu một thuộc tính bắt buộc cho graph logic, đặt NOT NULL ở bảng nguồn hoặc kiểm tra dữ liệu trước khi tạo graph.

## 9. Khóa vertex, khóa edge và tính toàn vẹn

### 9.1 Vertex key

Vertex key xác định một vertex. Ví dụ ACCOUNT_ID:

~~~sql
KEY (account_id)
~~~

Key nên được bảo vệ bằng PRIMARY KEY hoặc UNIQUE constraint trong bảng quan hệ.

### 9.2 Edge key

Edge key xác định từng edge. Ví dụ TRANSFER_ID:

~~~sql
KEY (transfer_id)
~~~

Không dùng cặp source/destination làm edge key nếu cùng hai tài khoản có thể giao dịch nhiều lần.

### 9.3 Source/destination mapping

Source và destination phải tham chiếu key của vertex table:

~~~sql
SOURCE KEY (from_account_id)
    REFERENCES accounts (account_id)
DESTINATION KEY (to_account_id)
    REFERENCES accounts (account_id)
~~~

Nếu bảng edge chứa ID không có vertex tương ứng, graph mapping có thể không thỏa điều kiện hoặc query không thể ánh xạ đúng endpoint. Dùng foreign key constraint ở relational schema để bảo vệ tính toàn vẹn từ đầu.

### 9.4 Composite key

Nếu vertex được định danh bằng nhiều cột, khai báo key ghép và source/destination key ghép theo đúng thứ tự. Kiểm tra tài liệu SQL Property Graph của release về cú pháp và giới hạn composite key.

## 10. Property graph và truy vấn SQL truyền thống

Không phải mọi truy vấn quan hệ đều cần graph.

Truy vấn join phù hợp khi số bước quan hệ cố định và ít:

~~~sql
SELECT a.account_name AS sender,
       b.account_name AS receiver,
       t.amount
FROM transfers t
JOIN accounts a
  ON a.account_id = t.from_account_id
JOIN accounts b
  ON b.account_id = t.to_account_id;
~~~

Graph pattern hữu ích khi cần diễn tả nhiều bước hoặc cấu trúc đường đi:

~~~sql
SELECT *
FROM GRAPH_TABLE (
    accounts_graph
    MATCH
        (a IS account)
        -[t1 IS transfer]->
        (b IS account)
        -[t2 IS transfer]->
        (c IS account)
    COLUMNS (
        a.account_name AS source_account,
        c.account_name AS destination_account
    )
);
~~~

| Trường hợp | Cách tiếp cận phù hợp |
|---|---|
| Join 2-3 bảng cố định | SQL JOIN |
| Tìm quan hệ qua nhiều hop | Graph pattern |
| Tổng hợp theo nhóm | SQL GROUP BY |
| Phân tích centrality/community/shortest path nâng cao | Graph analytics engine/API phù hợp |
| Báo cáo bảng thông thường | SQL truyền thống |
| Quan hệ thay đổi theo mẫu | SQL Property Graph có thể rõ nghĩa hơn |

SQL Property Graph vẫn chạy trong Oracle Database và optimizer. Không mặc định mọi graph query nhanh hơn join. Hãy so sánh execution plan, thời gian và tài nguyên trên workload thực tế.

## 11. Property graph và PGQL/Cypher/SPARQL

Các ngôn ngữ graph có cú pháp và môi trường thực thi riêng:

- SQL/PGQ: graph pattern được nhúng trong SQL, trong Oracle dùng GRAPH_TABLE và MATCH.
- PGQL: ngôn ngữ truy vấn graph theo cú pháp riêng, được Oracle Graph ecosystem hỗ trợ trong các cấu hình tương ứng.
- Cypher: ngôn ngữ graph phổ biến trong hệ sinh thái Neo4j và một số nền tảng khác.
- SPARQL: ngôn ngữ truy vấn RDF.

Không sao chép nguyên câu query từ PGQL hoặc Cypher sang GRAPH_TABLE. Khái niệm vertex/edge có thể giống nhau nhưng grammar, path syntax, function và execution environment khác nhau.

### 11.1 SQL/PGQ phù hợp khi

- Dữ liệu nguồn đã ở Oracle Database.
- Ứng dụng cần kết hợp graph pattern với SQL.
- Muốn trả kết quả graph query như một bảng quan hệ.
- Muốn dùng cùng transaction/security/data governance của database.

### 11.2 Graph server/analytics phù hợp khi

- Cần thuật toán graph analytics chuyên sâu.
- Cần xử lý graph trong memory hoặc phân tích quy mô lớn theo API.
- Cần môi trường graph riêng cho workload phân tích.
- Cần các thuật toán/engine không được cung cấp trực tiếp bởi SQL query.

SQL Property Graph và Oracle Graph Server/PGX có thể bổ sung cho nhau. Kiểm tra tài liệu, license và phiên bản của từng thành phần trước khi triển khai.

## 12. Ví dụ graph cho mạng xã hội

### 12.1 Bảng nguồn

~~~sql
CREATE TABLE people (
    person_id NUMBER PRIMARY KEY,
    full_name VARCHAR2(100) NOT NULL,
    city VARCHAR2(80)
);

CREATE TABLE friendships (
    friendship_id NUMBER PRIMARY KEY,
    person_a_id NUMBER NOT NULL,
    person_b_id NUMBER NOT NULL,
    since_date DATE,
    CONSTRAINT friendships_a_fk
        FOREIGN KEY (person_a_id) REFERENCES people(person_id),
    CONSTRAINT friendships_b_fk
        FOREIGN KEY (person_b_id) REFERENCES people(person_id)
);
~~~

### 12.2 Graph definition

~~~sql
CREATE PROPERTY GRAPH social_graph
    VERTEX TABLES (
        people
            KEY (person_id)
            LABEL person
            PROPERTIES (person_id, full_name, city)
    )
    EDGE TABLES (
        friendships
            KEY (friendship_id)
            SOURCE KEY (person_a_id)
                REFERENCES people (person_id)
            DESTINATION KEY (person_b_id)
                REFERENCES people (person_id)
            LABEL knows
            PROPERTIES (friendship_id, since_date)
    );
~~~

### 12.3 Tìm bạn trực tiếp

~~~sql
SELECT *
FROM GRAPH_TABLE (
    social_graph
    MATCH (p IS person) -[e IS knows]-> (friend IS person)
    WHERE p.full_name = 'An'
    COLUMNS (
        p.full_name AS person_name,
        friend.full_name AS friend_name,
        e.since_date AS since_date
    )
);
~~~

### 12.4 Tìm bạn của bạn

~~~sql
SELECT *
FROM GRAPH_TABLE (
    social_graph
    MATCH
        (p IS person)
        -[e1 IS knows]->
        (friend IS person)
        -[e2 IS knows]->
        (second_degree IS person)
    WHERE p.full_name = 'An'
    COLUMNS (
        p.full_name AS start_person,
        friend.full_name AS intermediate_person,
        second_degree.full_name AS second_degree_person
    )
);
~~~

Nếu nghiệp vụ coi friendship là vô hướng nhưng bảng chỉ lưu một chiều, pattern có hướng ở trên chỉ đi theo hướng được lưu. Cần thiết kế biểu diễn hoặc cú pháp match vô hướng được hỗ trợ để phản ánh đúng quy tắc.

## 13. Ví dụ graph cho quản lý nhân sự

Một bảng EMPLOYEES có thể vừa là vertex table vừa chứa cột MANAGER_ID tham chiếu đến EMPLOYEE_ID. Edge table riêng có thể lưu quan hệ báo cáo:

~~~sql
CREATE TABLE reporting_lines (
    reporting_id NUMBER PRIMARY KEY,
    employee_id NUMBER NOT NULL,
    manager_id NUMBER NOT NULL,
    effective_from DATE NOT NULL,
    effective_to DATE,
    CONSTRAINT reporting_employee_fk
        FOREIGN KEY (employee_id) REFERENCES employees(employee_id),
    CONSTRAINT reporting_manager_fk
        FOREIGN KEY (manager_id) REFERENCES employees(employee_id)
);
~~~

Vertex là nhân viên; edge là quan hệ báo cáo. Property của edge có thể chứa ngày bắt đầu/kết thúc hiệu lực.

Mô hình edge riêng hữu ích khi một nhân viên có lịch sử đổi quản lý, quan hệ có thuộc tính, có nhiều loại quan hệ báo cáo hoặc cần lưu thời gian hiệu lực.

Nếu chỉ lưu MANAGER_ID trong bảng EMPLOYEES, có thể ánh xạ self-reference theo khả năng của graph DDL phiên bản đang dùng. Edge table riêng thường rõ ràng hơn khi quan hệ có nhiều thuộc tính hoặc lịch sử.

## 14. Ví dụ graph cho fraud detection

Graph có thể liên kết:

- Customer.
- Bank account.
- Device.
- Phone number.
- IP address.
- Merchant.

Edge có thể biểu diễn:

- Customer owns account.
- Account uses device.
- Customer shares phone.
- Account transfers to account.
- Device connects from IP.

Một truy vấn graph có thể tìm các tài khoản liên quan qua một thiết bị hoặc số điện thoại dùng chung. Đây là tín hiệu điều tra, không phải bằng chứng tự động về gian lận.

### 14.1 Thiết kế dữ liệu

Không nên gộp mọi loại ID vào một cột không phân biệt. Dùng label/vertex table riêng hoặc mô hình có namespace rõ ràng để tránh xung đột giữa customer_id, account_id và device_id.

### 14.2 Time-aware graph

Quan hệ fraud có thể chỉ đúng trong một khoảng thời gian. Đưa valid_from, valid_to, observed_at hoặc event timestamp vào edge properties và lọc theo cửa sổ phân tích.

### 14.3 Tránh false positive

Hai khách hàng dùng chung IP công cộng hoặc thiết bị gia đình không tự động là gian lận. Kết quả graph cần kết hợp rule, score, thời gian, nguồn dữ liệu và đánh giá của chuyên viên.

## 15. Truy vấn graph và SQL filter

Một graph query có thể lọc vertex/edge property, sau đó outer SQL tiếp tục xử lý kết quả.

Ví dụ tổng giá trị chuyển tiền từ tài khoản cá nhân:

~~~sql
SELECT sender_city,
       SUM(amount) AS total_amount
FROM GRAPH_TABLE (
    accounts_graph
    MATCH (a IS account) -[t IS transfer]-> (b IS account)
    WHERE a.account_type = 'PERSONAL'
      AND t.transfer_status = 'POSTED'
    COLUMNS (
        a.city AS sender_city,
        t.amount AS amount
    )
)
GROUP BY sender_city
ORDER BY total_amount DESC;
~~~

### 15.1 Bind variable

Trong ứng dụng, dùng bind variable cho điều kiện động:

~~~sql
SELECT *
FROM GRAPH_TABLE (
    accounts_graph
    MATCH (a IS account) -[t IS transfer]-> (b IS account)
    WHERE a.account_id = :source_account_id
    COLUMNS (
        a.account_name AS sender,
        b.account_name AS receiver,
        t.amount AS amount
    )
);
~~~

Bind variable giúp tránh ghép dữ liệu đầu vào trực tiếp vào SQL text, giảm nguy cơ SQL injection và hỗ trợ cursor reuse.

### 15.2 Kết hợp CTE

~~~sql
WITH transfer_edges AS (
    SELECT *
    FROM GRAPH_TABLE (
        accounts_graph
        MATCH (a IS account) -[t IS transfer]-> (b IS account)
        COLUMNS (
            a.account_id AS source_id,
            b.account_id AS target_id,
            t.amount AS amount
        )
    )
)
SELECT source_id,
       COUNT(*) AS outgoing_count,
       SUM(amount) AS outgoing_amount
FROM transfer_edges
GROUP BY source_id;
~~~

### 15.3 Kết hợp bảng relational

~~~sql
SELECT g.sender,
       g.receiver,
       g.amount,
       c.customer_segment
FROM GRAPH_TABLE (
    accounts_graph
    MATCH (a IS account) -[t IS transfer]-> (b IS account)
    COLUMNS (
        a.account_id AS sender_id,
        b.account_id AS receiver_id,
        a.account_name AS sender,
        b.account_name AS receiver,
        t.amount AS amount
    )
) g
JOIN account_customers c
  ON c.account_id = g.sender_id;
~~~

Graph result có thể kết hợp với bảng relational để lấy thông tin bổ sung. Chọn đúng cardinality và index cho join phía ngoài.

## 16. Hiệu năng và tối ưu

Graph query vẫn tiêu tốn CPU, memory và I/O. Đường đi nhiều hop có thể mở rộng số lượng tổ hợp rất nhanh.

### 16.1 Index cho key và join columns

Nên có index phù hợp trên vertex key, edge key, source key, destination key và các property thường xuyên được lọc.

Primary key/unique constraint thường đã tạo index cho key. Source/destination foreign key không tự động có index trong mọi thiết kế; cân nhắc index trên edge table để truy cập theo endpoint.

Ví dụ:

~~~sql
CREATE INDEX transfers_from_ix
ON transfers(from_account_id);

CREATE INDEX transfers_to_ix
ON transfers(to_account_id);

CREATE INDEX transfers_time_ix
ON transfers(transfer_time);
~~~

Không tạo mọi index một cách máy móc. Mỗi index làm tăng dung lượng và chi phí INSERT/UPDATE/DELETE.

### 16.2 Statistics

Optimizer cần statistics phù hợp để ước lượng cardinality. Sau khi load nhiều dữ liệu hoặc thay đổi phân bố, thu thập statistics theo chính sách database:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'TRANSFERS',
        cascade => TRUE
    );
END;
/
~~~

Đối với production, dùng quy trình statistics hiện hành của DBA; không tự gather với mọi bảng trong giờ cao điểm.

### 16.3 Giới hạn phạm vi

- Lọc theo thời gian trước khi mở rộng path.
- Giới hạn label cần match.
- Chọn property tối thiểu trong COLUMNS.
- Hạn chế độ dài path.
- Dùng endpoint có selectivity tốt.
- Tránh truy vấn toàn graph khi chỉ cần một vùng nhỏ.

### 16.4 Đọc execution plan

Graph query được thực thi trong SQL engine. Có thể dùng công cụ SQL plan phù hợp để xem kế hoạch:

~~~sql
EXPLAIN PLAN FOR
SELECT *
FROM GRAPH_TABLE (
    accounts_graph
    MATCH (a IS account) -[t IS transfer]-> (b IS account)
    WHERE a.account_id = 1
    COLUMNS (
        a.account_name AS sender,
        b.account_name AS receiver,
        t.amount AS amount
    )
);

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Chi tiết operator trong plan phụ thuộc release và query. Không suy luận chỉ từ một operator hoặc estimated rows; so sánh actual runtime statistics trong môi trường test phù hợp.

## 17. Quản lý thay đổi bảng nguồn

Property graph tham chiếu bảng và cột nguồn. Nếu đổi tên/xóa cột, thay đổi datatype, key hoặc cấu trúc bảng, graph definition có thể không còn hợp lệ hoặc truy vấn không còn hoạt động như dự kiến.

Trước khi chạy DDL:

- Kiểm tra graph nào tham chiếu bảng.
- Kiểm tra property nào phụ thuộc cột sắp đổi.
- Kiểm tra key/source/destination mapping.
- Thử DDL trong môi trường test.
- Cập nhật graph definition theo migration.
- Chạy smoke query sau deployment.

Không drop/rename cột chỉ vì ứng dụng relational hiện tại không dùng; graph query hoặc báo cáo khác có thể đang phụ thuộc.

## 18. Quản lý graph object

Property graph là schema object có metadata. Quản trị cần biết ai tạo graph, graph dựa trên những bảng nào, cột nào được expose, ai được phép query, migration nào tạo/thay đổi graph và graph nào không còn được sử dụng.

Các lệnh DDL cơ bản có thể gồm CREATE, ALTER hoặc DROP theo khả năng release. Cú pháp thay đổi graph definition và các view metadata cần tra trong SQL Language Reference đúng phiên bản.

### 18.1 Xóa graph

Khi bỏ graph object, cần phân biệt xóa định nghĩa graph với xóa các bảng quan hệ nguồn. Không xóa bảng ACCOUNTS hoặc TRANSFERS chỉ vì không còn cần graph object.

Trước khi drop:

- Xác nhận không còn query phụ thuộc.
- Kiểm tra application code/report.
- Lưu DDL definition nếu cần rollback.
- Thực hiện qua migration có kiểm soát.

### 18.2 Version control

Lưu graph DDL trong repository cùng schema migration. Đặt tên migration có thứ tự, ví dụ:

~~~text
V042__create_accounts_graph.sql
V043__add_transfer_status_property.sql
V044__update_graph_edge_mapping.sql
~~~

Tên file là ví dụ. Quy ước phụ thuộc Flyway/Liquibase hoặc công cụ migration của dự án.

## 19. Quyền và bảo mật

Graph query không nên mở rộng quyền truy cập dữ liệu vượt quá chính sách relational schema.

Khi triển khai:

- User tạo graph cần quyền tạo graph object theo release.
- User định nghĩa graph cần quyền phù hợp trên các bảng nguồn.
- User truy vấn cần quyền truy cập graph và dữ liệu theo cơ chế Oracle của release.
- Không cấp quyền quản trị database chỉ để query graph.
- Giới hạn property nhạy cảm.
- Dùng schema owner riêng cho graph definition nếu phù hợp.
- Audit các thao tác tạo/thay đổi/drop graph.

Các tên system/object privilege và cách GRANT có thể thay đổi theo release. Tra Security Guide/SQL Language Reference tương ứng trước khi áp dụng câu GRANT trong production; không đoán quyền chỉ từ tên feature.

### 19.1 Row-level security

Nếu bảng nguồn dùng Virtual Private Database (VPD), Real Application Security hoặc policy bảo mật khác, cần xác minh graph query có tuân theo policy như mong đợi trong release và execution context. Không mặc định rằng việc expose bảng thành graph làm mất hiệu lực policy, cũng không giả định mọi policy có hành vi giống nhau mà chưa thử.

### 19.2 Data masking

Không đưa PII hoặc dữ liệu bí mật vào graph property nếu query không cần. Với môi trường lab, dùng synthetic hoặc masked data.

### 19.3 SQL injection

Ứng dụng gọi GRAPH_TABLE qua JDBC vẫn phải dùng bind variables. Không nối chuỗi đầu vào người dùng vào graph pattern, label hoặc SQL text.

## 20. Kiểm tra phiên bản Oracle hỗ trợ SQL Property Graph

Yêu cầu theo phiên bản hỗ trợ rất quan trọng vì không phải mọi Oracle Database release đều hiểu cú pháp CREATE PROPERTY GRAPH và GRAPH_TABLE.

### 20.1 Mốc phiên bản

| Database release | Hướng dẫn áp dụng |
|---|---|
| Oracle Database 19c và các release cũ hơn 23ai | Không giả định có native SQL Property Graph DDL/GRAPH_TABLE. Kiểm tra graph option/server riêng hoặc dùng mô hình relational/giải pháp khác. |
| Oracle Database 23ai | Có hỗ trợ SQL Property Graph và SQL/PGQ core như CREATE PROPERTY GRAPH và GRAPH_TABLE. |
| Oracle Database 26ai và release mới hơn | Kiểm tra SQL Language Reference/Graph documentation đúng release để xác nhận core syntax, enhancement và restriction. |

Tên marketing release, version number nội bộ, Release Update và compatibility setting không phải lúc nào cũng thể hiện giống nhau. Xác minh trên database đang kết nối, không dựa vào tên image hoặc tài liệu của môi trường khác.

### 20.2 Kiểm tra database version

~~~sql
SELECT banner
FROM v$version;
~~~

Trên release có hỗ trợ cột BANNER_FULL:

~~~sql
SELECT banner_full
FROM v$version;
~~~

Hoặc:

~~~sql
SELECT product,
       version,
       status
FROM product_component_version;
~~~

Các cột có thể khác nhau theo phiên bản. Dùng DESC V$VERSION hoặc DESC PRODUCT_COMPONENT_VERSION nếu cần viết script tương thích nhiều release.

### 20.3 Kiểm tra container/PDB

Trong multitenant, xác định container hiện tại:

~~~sql
SELECT sys_context('USERENV', 'CON_NAME') AS con_name,
       sys_context('USERENV', 'SERVICE_NAME') AS service_name
FROM dual;
~~~

Một câu query thành công trên PDB này không chứng minh PDB khác có cùng version, patch hoặc quyền.

### 20.4 Kiểm tra COMPATIBLE

~~~sql
SHOW PARAMETER compatible;
~~~

COMPATIBLE ảnh hưởng khả năng sử dụng một số tính năng và định dạng tương thích. Tuy nhiên, không dùng riêng giá trị COMPATIBLE để kết luận SQL Property Graph chắc chắn được hỗ trợ. Cần đối chiếu release, RU, platform/service và tài liệu feature prerequisite.

### 20.5 Kiểm tra cú pháp tối thiểu

Trong lab hoặc schema thử nghiệm trên database đã xác nhận hỗ trợ, tạo graph tối thiểu từ hai bảng nhỏ và chạy một GRAPH_TABLE query. Đây là cách kiểm chứng kỹ thuật tốt hơn việc chỉ nhìn version banner.

Không tạo graph thử trên production nếu chưa có kế hoạch object cleanup và quyền được duyệt.

## 21. Database service, cloud và platform restrictions

Không suy luận mọi Oracle Database deployment có cùng feature set chỉ vì cùng tên release.

Kiểm tra:

- On-premises hay cloud service.
- Autonomous Database hay Base Database Service.
- Exadata hay nền tảng khác.
- Region và service version.
- Release Update/patch level.
- PDB configuration.
- Feature restrictions theo service tier.
- Quyền và license của thành phần graph/analytics liên quan.

Tài liệu Oracle cho đúng cloud service là nguồn quyết định. Một tính năng SQL trong database có thể khả dụng khác nhau theo service, trong khi Graph Server/Graph Studio/analytics có yêu cầu triển khai riêng.

## 22. JDBC và SQL Property Graph

GRAPH_TABLE là một phần của SQL statement. Ứng dụng Java có thể gửi câu SQL này qua JDBC như các câu SELECT khác nếu database hỗ trợ cú pháp và driver tương thích với database release.

Ví dụ:

~~~java
String sql =
    "SELECT * " +
    "FROM GRAPH_TABLE (" +
    "  accounts_graph " +
    "  MATCH (a IS account) -[t IS transfer]-> (b IS account) " +
    "  WHERE a.account_id = ? " +
    "  COLUMNS (" +
    "    a.account_name AS sender, " +
    "    b.account_name AS receiver, " +
    "    t.amount AS amount" +
    "  )" +
    ")";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, sourceAccountId);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            String sender = rs.getString("sender");
            String receiver = rs.getString("receiver");
            BigDecimal amount = rs.getBigDecimal("amount");
        }
    }
}
~~~

### 22.1 Không cần graph-specific JDBC API cho SELECT cơ bản

Ứng dụng có thể dùng PreparedStatement và ResultSet. Không cần một driver graph riêng chỉ để gửi SQL GRAPH_TABLE.

### 22.2 Driver/database compatibility

Driver vẫn phải tương thích với JDK và database release. Một driver cũ có thể kết nối được database mới nhưng không có nghĩa mọi datatype, metadata hoặc protocol feature mới đều được hỗ trợ. Đối chiếu JDBC certification matrix.

### 22.3 Bind variables

Không nối giá trị đầu vào vào SQL. Dùng bind variable cho ID và giá trị filter. Label và cấu trúc pattern thường là một phần SQL text; không cho người dùng tùy ý điều khiển graph name/label bằng cách nối chuỗi. Nếu cần lựa chọn graph pattern, ánh xạ từ danh sách cấu hình allowlist do ứng dụng kiểm soát.

## 23. Tối ưu mô hình graph

Graph model nên phản ánh câu hỏi nghiệp vụ, không chỉ sao chép mọi bảng vào vertex/edge.

### 23.1 Chọn vertex đúng

Vertex thường là thực thể có định danh ổn định: Person, Account, Product, Device, Location hoặc Organization. Không biến mọi bảng lookup thành vertex nếu không có truy vấn quan hệ cần tới nó.

### 23.2 Chọn edge đúng

Edge nên thể hiện một quan hệ có ý nghĩa: Owns, Transfers, Knows, Reports_to, Purchased hoặc Connected_to. Nếu quan hệ có thuộc tính riêng hoặc nhiều lần xảy ra, dùng edge table có key riêng.

### 23.3 Edge event hay edge relationship

Một giao dịch chuyển tiền là event edge: mỗi giao dịch là một sự kiện có thời điểm, số tiền và trạng thái.

Quan hệ bạn bè có thể là relationship edge: tồn tại trong khoảng thời gian và có thể thay đổi trạng thái.

Phân biệt hai kiểu giúp thiết kế retention, event history và query thời gian đúng hơn.

### 23.4 Temporal graph

Nếu quan hệ có hiệu lực theo thời gian, lưu thời điểm bắt đầu/kết thúc hoặc timestamp event trong edge properties. Khi truy vấn, lọc theo mốc thời gian nghiệp vụ.

Không xóa lịch sử edge nếu cần điều tra trạng thái graph tại quá khứ.

## 24. Những giới hạn cần xem xét

Các hạn chế cụ thể phụ thuộc database release và graph DDL, nhưng khi thiết kế cần kiểm tra:

- Datatype nào được dùng làm vertex/edge key.
- Datatype nào được expose làm property.
- Hỗ trợ composite key.
- Hỗ trợ bảng, view hoặc các nguồn relational nào.
- Quy tắc với partitioned table.
- Cách xử lý NULL key/property.
- Giới hạn tên label/property và identifier.
- DDL dependency khi rename/drop cột.
- Quyền tạo và query graph.
- Hành vi với VPD/row-level security.
- Hỗ trợ pattern/path syntax.
- Khả năng optimizer và index usage.

Không suy luận giới hạn từ một phiên bản khác. SQL Language Reference và Graph Developer's Guide của đúng release là nguồn cần đối chiếu.

## 25. Troubleshooting

### CREATE PROPERTY GRAPH không nhận diện

Nguyên nhân có thể:

- Database release chưa hỗ trợ SQL Property Graph.
- Kết nối nhầm PDB/service.
- Release Update hoặc platform không đáp ứng prerequisite.
- User thiếu quyền tạo graph.
- Cú pháp được lấy từ tài liệu phiên bản khác.

Hướng xử lý:

1. Xác nhận V$VERSION.
2. Xác nhận CON_NAME/SERVICE_NAME.
3. Kiểm tra tài liệu đúng release.
4. Kiểm tra privilege.
5. Thử cú pháp tối thiểu trong lab.

### GRAPH_TABLE không được nhận diện

Kiểm tra database parser/release hỗ trợ SQL/PGQ chưa. Đừng nhầm cú pháp GRAPH_TABLE với PGQL chạy trên graph server.

### Vertex/edge mapping không hợp lệ

Kiểm tra:

- Vertex key có unique không?
- Edge key có unique không?
- Source/destination columns có cùng kiểu và giá trị với vertex key?
- Composite key có đúng thứ tự?
- Có endpoint không tồn tại?
- Có cột bị rename/drop?

### Query trả ít hoặc không có hàng

Kiểm tra:

- Label có đúng?
- Hướng edge có đúng?
- Source/destination mapping có đảo chiều?
- Filter property có quá chặt?
- Dữ liệu edge có endpoint hợp lệ?
- Đang query đúng PDB/schema?

### Query chậm

Kiểm tra:

- Độ dài path và số lượng kết quả trung gian.
- Index trên key/source/destination.
- Statistics.
- Filter selectivity.
- Execution plan.
- Số property được trả về.
- Có thể dùng SQL JOIN đơn giản hơn không?

### Privilege error

Xác định user thực thi query, graph owner và quyền trên base tables. Cấp đúng privilege theo tài liệu release, không giải quyết bằng DBA role mặc định.

## 26. Best practices

- Bắt đầu từ câu hỏi nghiệp vụ cần trả lời bằng graph.
- Giữ bảng quan hệ làm nguồn dữ liệu rõ ràng.
- Chọn vertex key/edge key ổn định và unique.
- Đặt tên label/property có ý nghĩa.
- Khai báo source/destination mapping đúng hướng.
- Chỉ expose property cần thiết.
- Dùng foreign key để bảo vệ endpoint integrity.
- Index key và endpoint columns theo workload.
- Thu thập statistics phù hợp.
- Giới hạn path và filter sớm.
- Kết hợp GRAPH_TABLE với SQL khi cần aggregation/join.
- Dùng bind variable qua JDBC.
- Quản lý graph DDL trong migration/version control.
- Kiểm tra version, RU, PDB và cloud service.
- Kiểm tra security policy và quyền truy vấn.
- Benchmark với dữ liệu đại diện.

## 27. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách làm đúng |
|---|---|---|
| Nghĩ bảng có FROM_ID/TO_ID tự động là property graph | Thiếu graph metadata và key/label mapping | Tạo graph definition |
| Nhầm vertex với edge | Mô hình hóa sai thực thể và quan hệ | Xác định entity và relationship |
| Dùng source/destination đảo chiều | Path query trả kết quả sai hướng | Khai báo đúng SOURCE KEY/DESTINATION KEY |
| Edge key không unique | Gộp hoặc nhận diện sai quan hệ | Dùng khóa riêng cho mỗi edge |
| Dùng cặp endpoint làm edge key cho event nhiều lần | Mất phân biệt nhiều giao dịch | Dùng event/relationship ID riêng |
| Không bảo vệ vertex key | Mapping không ổn định | PRIMARY KEY/UNIQUE ở bảng nguồn |
| Không có foreign key endpoint | Edge trỏ tới vertex không hợp lệ | Bảo vệ source/destination bằng FK |
| Đưa mọi cột vào properties | Lộ dữ liệu và tăng bề mặt truy cập | Chỉ expose property cần thiết |
| Nghĩ graph query luôn nhanh hơn JOIN | Tốn CPU/memory và path expansion | So sánh plan/runtime |
| Quên hướng edge | Bỏ sót đường đi | Xác định directed/undirected semantics |
| Dùng cú pháp Cypher/PGQL trong GRAPH_TABLE | Syntax error | Dùng SQL/PGQ đúng Oracle release |
| Nghĩ 19c hỗ trợ native GRAPH_TABLE | Không parse được cú pháp | Kiểm tra mốc 23ai+ và service |
| Chỉ nhìn V$VERSION | Bỏ qua PDB/RU/platform/privilege | Kiểm tra toàn bộ deployment context |
| Không cập nhật graph khi rename cột | Graph definition/query lỗi | Đưa graph DDL vào migration |
| Không index endpoint | Path traversal tốn kém | Đo và tạo index phù hợp |
| Dùng graph result như bằng chứng fraud | False positive | Kết hợp rule và điều tra nghiệp vụ |
| Dùng literal input trong SQL | SQL injection | Bind variable và allowlist pattern |

## 28. Bài thực hành tự kiểm tra

Thực hiện trên Oracle Database release hỗ trợ SQL Property Graph, trong schema lab.

### Bài 1 — Thiết kế vertex và edge

Từ bài toán tài khoản, xác định vertex table, edge table, key, source key, destination key và properties.

### Bài 2 — Tạo bảng nguồn

Tạo ACCOUNTS và TRANSFERS có primary key, foreign key và dữ liệu giả.

### Bài 3 — Tạo property graph

Tạo ACCOUNTS_GRAPH bằng CREATE PROPERTY GRAPH. Kiểm tra DDL hoàn tất.

### Bài 4 — Query edge trực tiếp

Dùng GRAPH_TABLE tìm tất cả giao dịch từ một tài khoản.

### Bài 5 — Query hai hop

Tìm đường đi hai giao dịch từ tài khoản nguồn tới tài khoản đích.

### Bài 6 — Lọc property

Lọc theo amount, status, city và transfer_time.

### Bài 7 — Aggregation

Tính tổng tiền nhận theo account bằng GROUP BY ngoài GRAPH_TABLE.

### Bài 8 — Composite key

Thiết kế graph có vertex key ghép và xác nhận source/destination mapping.

### Bài 9 — Data integrity

Thử tạo edge trỏ tới vertex không tồn tại. Xác định foreign key bảo vệ dữ liệu ở tầng relational.

### Bài 10 — Index và execution plan

So sánh query trước/sau khi tạo index endpoint. Ghi actual runtime và plan.

### Bài 11 — JDBC

Gọi GRAPH_TABLE bằng PreparedStatement và bind source account ID.

### Bài 12 — Version compatibility

Ghi database version, RU, PDB, service và kiểm tra tài liệu SQL Property Graph đúng release. So sánh hành vi trên môi trường cũ nếu có.

## 29. Checklist trước khi triển khai

**Mô hình**

- Đã xác định vertex/edge theo nghiệp vụ?
- Vertex key và edge key duy nhất?
- Source/destination đúng hướng?
- Label và property có tên rõ?
- Edge event và edge relationship đã phân biệt?

**Database**

- Release có SQL Property Graph?
- Release Update và COMPATIBLE đã kiểm tra?
- Đang kết nối đúng PDB/service?
- Cú pháp đúng SQL Language Reference?
- Datatype/key/property được hỗ trợ?

**Bảo mật**

- User tạo graph có quyền tối thiểu?
- User query có quyền phù hợp?
- Property nhạy cảm đã được loại?
- Row-level security đã được kiểm chứng?
- JDBC dùng bind variable?

**Hiệu năng**

- Endpoint indexes đã đánh giá?
- Statistics phù hợp?
- Path length có giới hạn?
- Filter được áp dụng sớm?
- Execution plan và actual runtime đã đo?

**Vận hành**

- Graph DDL nằm trong version control?
- Có migration/rollback?
- Có smoke query sau deployment?
- Có theo dõi graph object dependency?
- Có test khi thay đổi bảng nguồn?

## 30. Ghi nhớ

| Khái niệm | Điều cần nhớ |
|---|---|
| Property graph | Đồ thị gồm vertex, edge, label và property |
| Vertex | Thực thể trong graph |
| Edge | Quan hệ có hướng giữa hai vertex |
| Label | Phân loại vertex/edge |
| Property | Thuộc tính của vertex/edge |
| Vertex key | Định danh duy nhất vertex |
| Edge key | Định danh duy nhất edge |
| SOURCE KEY | Ánh xạ endpoint nguồn |
| DESTINATION KEY | Ánh xạ endpoint đích |
| CREATE PROPERTY GRAPH | Tạo graph schema object trên bảng quan hệ |
| GRAPH_TABLE | Truy vấn graph pattern trong SQL |
| MATCH | Mô tả pattern vertex/edge |
| COLUMNS | Chọn giá trị trả về thành cột SQL |
| SQL/PGQ | SQL Property Graph Queries |
| PGQL | Ngôn ngữ truy vấn graph riêng |
| RDF/SPARQL | Mô hình/ngôn ngữ graph khác |
| Oracle Database 23ai | Mốc hỗ trợ native SQL Property Graph core |
| V$VERSION | Kiểm tra version database |
| TNS/service/PDB | Xác định đúng môi trường kết nối |
| Endpoint index | Hỗ trợ truy cập quan hệ theo source/destination |

SQL Property Graph bổ sung cách nhìn đồ thị trên dữ liệu quan hệ: vertex biểu diễn thực thể, edge biểu diễn quan hệ, label phân loại và property mô tả dữ liệu. CREATE PROPERTY GRAPH ánh xạ bảng/key/cột; GRAPH_TABLE dùng MATCH để tìm các mẫu quan hệ rồi trả kết quả về SQL qua COLUMNS. Mốc hỗ trợ native SQL Property Graph là Oracle Database 23ai; với release cũ hơn, cloud service hoặc RU khác nhau, phải kiểm tra tài liệu và môi trường thực tế trước khi dùng. Thiết kế key và hướng edge chính xác, bảo vệ endpoint bằng constraint, chỉ expose property cần thiết và đo execution plan trên workload thật. SQL/PGQ, PGQL, Cypher và SPARQL là các ngôn ngữ/môi trường khác nhau; không trộn cú pháp giữa chúng.
