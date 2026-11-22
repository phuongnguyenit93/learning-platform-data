# Quy tắc đặt tên, chữ hoa thường và objectQuotingStrategy trong Liquibase

## 1. Vì sao cách đặt tên ảnh hưởng trực tiếp đến migration?

Một migration có thể hợp lệ về cú pháp nhưng tạo bảng sai tên, không tìm thấy bảng đã tồn tại hoặc thất bại khi triển khai sang DBMS khác. Nguyên nhân đôi khi không nằm ở câu lệnh tạo bảng mà ở **cách định danh đối tượng (identifier) được viết và được cơ sở dữ liệu diễn giải**: chữ hoa và chữ thường, dấu ngoặc kép, từ khóa dành riêng, tên schema hoặc giá trị đã được thay thế từ tham số changelog.

Ví dụ, một người viết <code>CustomerOrder</code> với ý định lưu bảng có chữ C và O viết hoa. Trên PostgreSQL, định danh *không được trích dẫn* thường được gập về chữ thường; còn <code>"CustomerOrder"</code> được giữ đúng kiểu chữ. Trên Oracle, tên không được trích dẫn thường được gập thành chữ hoa. Cùng một tên trong changelog có thể tạo ra các tên vật lý hoặc cách tham chiếu khác nhau tùy SQL mà Liquibase sinh ra và DBMS đích.

Đây là bài thuộc chương **Tham số hóa** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Module giúp người học quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum, lịch sử triển khai; thực hành migration có kiểm chứng, rollback, làm việc trên nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Quy tắc đặt tên và <code>objectQuotingStrategy</code> là một phần thiết yếu của mục tiêu này, đặc biệt khi các schema được tham số hóa hoặc dự án hỗ trợ nhiều DBMS.

Sau bài học, người học cần có thể:

- Phân biệt tên logic khai báo trong changelog, tên vật lý trong database và định danh changeset trong lịch sử Liquibase.
- Giải thích ảnh hưởng của chữ hoa/thường và tên có hoặc không có dấu trích dẫn trên các DBMS phổ biến.
- Chọn quy ước tên ổn định cho bảng, cột, schema, chỉ mục, khóa và sequence.
- Hiểu ba giá trị <code>LEGACY</code>, <code>QUOTE_ALL_OBJECTS</code>, <code>QUOTE_ONLY_RESERVED_WORDS</code> của <code>objectQuotingStrategy</code>.
- Kết hợp cách đặt tên với tham số changelog, SQL xem trước, kiểm thử và rollback.

## 2. Identifier trong database là gì?

Identifier là tên dùng để xác định một đối tượng của cơ sở dữ liệu, chẳng hạn:

| Loại đối tượng | Ví dụ | Phần nào của Liquibase thường sử dụng? |
|---|---|---|
| Schema | <code>sales_app</code> | <code>schemaName</code>, default schema |
| Bảng | <code>customer_order</code> | <code>tableName</code> của <code>createTable</code>, <code>addColumn</code>, <code>dropTable</code> |
| Cột | <code>created_at</code> | <code>column.name</code>, <code>columnName</code> |
| Chỉ mục | <code>idx_customer_order_created_at</code> | <code>indexName</code> |
| Khóa ngoại | <code>fk_order_customer</code> | <code>constraintName</code> hoặc tên ràng buộc tương ứng |
| Sequence | <code>seq_customer_order_id</code> | <code>sequenceName</code> |
| View | <code>v_order_summary</code> | <code>viewName</code> |

Một identifier không giống **giá trị dữ liệu**. Trong câu lệnh SQL, <code>customer_order</code> ở vị trí tên bảng là identifier; chuỗi <code>'customer_order'</code> là một giá trị text. Hai khái niệm này có quy tắc trích dẫn hoàn toàn khác nhau.

Identifier cũng không đồng nhất với ba thành phần định danh changeset của Liquibase: <code>id</code>, <code>author</code> và đường dẫn changelog. Ba thành phần đó dùng để nhận diện bản ghi migration trong <code>DATABASECHANGELOG</code>. Cách đặt tên và quoting của bảng hoặc cột không tự đổi định danh changeset; ngược lại, sửa id/author/đường dẫn để “khớp tên bảng” có thể làm Liquibase nhận diện changeset đã chạy thành thay đổi mới.

### 2.1. Tên logic, SQL sinh ra và tên vật lý

Cần nhìn theo ba lớp:

1. **Changelog:** người viết điền <code>tableName: CustomerOrder</code> hoặc <code>schemaName: ${tenant.schema}</code>.
2. **SQL Liquibase sinh ra:** có thể chứa tên không trích dẫn hoặc đã trích dẫn theo DBMS và <code>objectQuotingStrategy</code>.
3. **Database catalog:** DBMS lưu và tra cứu identifier theo quy tắc của nó.

Không nên chỉ xem changelog rồi kết luận tên vật lý chắc chắn giống từng ký tự người viết. Hãy dùng SQL preview và kiểm tra metadata của DBMS thật để xác định kết quả.

## 3. Chữ hoa và chữ thường trong identifier

### 3.1. Identifier không trích dẫn

Các DBMS có thể chuẩn hóa cách viết tên không được trích dẫn. Ví dụ khái niệm:

~~~sql
CREATE TABLE CustomerOrder (
    id BIGINT PRIMARY KEY
);
~~~

| DBMS | Hành vi điển hình với identifier không trích dẫn | Điểm cần lưu ý |
|---|---|---|
| PostgreSQL | Gập thành chữ thường, như <code>customerorder</code> | <code>CustomerOrder</code>, <code>customerorder</code> không trích dẫn cùng tham chiếu một tên đã gập |
| Oracle Database | Gập thành chữ hoa, như <code>CUSTOMERORDER</code> | Các truy vấn không trích dẫn thường tra cứu tên chữ hoa |
| MySQL/MariaDB | Phụ thuộc kiểu đối tượng, hệ điều hành, filesystem và thiết lập như <code>lower_case_table_names</code> | Không suy ra hành vi case chung cho mọi cài đặt, đặc biệt tên bảng |
| SQL Server | Việc so khớp tên thường chịu ảnh hưởng collation và cấu hình | Không kết luận case-insensitive trên mọi database |

Bảng trên chỉ mô tả những quy tắc thông dụng. Một schema sử dụng identifier có dấu trích dẫn, driver hoặc cấu hình không tiêu chuẩn có thể tạo ra kết quả khác.

Điều quan trọng là **không đồng nhất “tên không phân biệt hoa thường” với “tên vật lý được lưu đúng kiểu chữ gốc”**. Chúng là hai chuyện khác nhau: database có thể gập chữ khi lưu hoặc so khớp bằng một collation không phân biệt chữ hoa/chữ thường.

### 3.2. Identifier có trích dẫn

PostgreSQL minh họa sự khác biệt:

~~~sql
CREATE TABLE "CustomerOrder" (
    "OrderID" BIGINT PRIMARY KEY
);

-- Tên có trích dẫn phải giữ đúng chữ hoa/thường:
SELECT "OrderID" FROM "CustomerOrder";

-- Tham chiếu không trích dẫn tới tên đã gập sẽ khác:
SELECT OrderID FROM CustomerOrder;
~~~

Câu SELECT cuối có thể không tìm thấy bảng hoặc cột vừa tạo, vì PostgreSQL hiểu tên không trích dẫn sau khi gập về chữ thường. Chú ý dấu ngoặc kép ở đây là cú pháp SQL identifier của PostgreSQL và các DBMS hỗ trợ quy ước tương tự.

Các DBMS khác có cú pháp quoting khác nhau. MySQL thường dùng dấu backtick; SQL Server có thể dùng ngoặc vuông; Liquibase chọn cách trích dẫn phù hợp khi chính nó sinh SQL cho DBMS đích. **Không nên viết thủ công dấu ngoặc kép, backtick hoặc ngoặc vuông vào các thuộc tính như <code>tableName</code> và <code>schemaName</code> rồi kỳ vọng chạy được trên mọi DBMS.**

### 3.3. “Đúng tên” còn phụ thuộc schema

Hai bảng <code>sales.customer_order</code> và <code>archive.customer_order</code> có cùng tên bảng nhưng là hai đối tượng khác nhau. Nếu migration chỉ dùng <code>tableName</code> mà không xác định schema, SQL có thể tác động lên schema mặc định của kết nối hoặc schema đã cấu hình cho Liquibase.

Khi kiểm tra migration, cần xác minh cả **schema/catalog + tên đối tượng + quoting**, đặc biệt nếu changelog dùng tham số <code>${app.schema}</code> để chọn schema theo môi trường.

## 4. Quy ước đặt tên nên áp dụng trong dự án

Nhóm nên có quy ước đủ đơn giản để người viết SQL, ORM, Liquibase và công cụ phân tích schema đều có thể dự đoán cùng một identifier.

### 4.1. Quy ước khuyến nghị

| Nhóm | Quy ước đề xuất | Ví dụ |
|---|---|---|
| Schema | Chữ thường, <code>snake_case</code>, mô tả miền nghiệp vụ | <code>billing_app</code> |
| Bảng | Danh từ rõ nghĩa, chữ thường, <code>snake_case</code> | <code>invoice_line</code> |
| Cột | Tên mô tả ý nghĩa, hậu tố nhất quán cho thời gian và ID | <code>created_at</code>, <code>customer_id</code> |
| Khóa chính | Tên nhất quán theo bảng khi cần đặt tên tường minh | <code>pk_invoice_line</code> |
| Khóa ngoại | Prefix <code>fk_</code> kèm đối tượng liên quan | <code>fk_invoice_line_invoice</code> |
| Chỉ mục | Prefix <code>idx_</code> hoặc <code>ux_</code> cho unique index | <code>idx_invoice_created_at</code> |
| Sequence | Prefix <code>seq_</code> | <code>seq_invoice_id</code> |
| View | Prefix <code>v_</code> nếu nhóm sử dụng | <code>v_invoice_summary</code> |

Đây là một gợi ý thống nhất, không phải quy định bắt buộc của Liquibase. Điều quan trọng là có một convention dùng chung trên toàn repository và duy trì khi tạo changeset mới.

**Những nguyên tắc bổ sung:**

- Tránh ký tự khoảng trắng, dấu gạch ngang, dấu chấm nằm trong tên identifier đơn lẻ và ký tự có ý nghĩa đặc biệt với SQL.
- Tránh các từ khóa SQL phổ biến như <code>order</code>, <code>user</code>, <code>group</code>, <code>select</code>; bộ từ khóa dành riêng khác nhau giữa DBMS và phiên bản.
- Không dùng tên chỉ khác nhau ở chữ hoa/thường, như <code>Account</code> và <code>account</code>.
- Đặt tên ràng buộc và chỉ mục tường minh khi cần kiểm soát rollback, thao tác sau này hoặc chẩn đoán; tránh phụ thuộc hoàn toàn vào tên DBMS tự sinh.
- Quan tâm giới hạn độ dài identifier của DBMS đích. Một quy ước ghép toàn bộ bảng, cột và loại ràng buộc có thể vượt giới hạn; DBMS có thể từ chối hoặc cắt tên tùy hệ thống.
- Không đổi tên một đối tượng đang được ứng dụng sử dụng mà chưa đánh giá truy vấn SQL, ORM, view, stored procedure và luồng deploy cuốn chiếu.

Chữ thường <code>snake_case</code> giảm nhu cầu quoting bắt buộc và làm cho SQL viết tay dễ dự đoán hơn trên nhiều DBMS. Nó không thay thế việc kiểm thử SQL của từng hệ quản trị.

### 4.2. Đặt tên đủ rõ cho những schema lớn

Ví dụ hai bảng nghiệp vụ cùng có <code>status</code> và <code>created_at</code> là bình thường, vì cột được định danh trong phạm vi bảng. Nhưng chỉ mục hoặc ràng buộc có thể có ràng buộc tên duy nhất ở mức schema hoặc DBMS. Do đó, tên kiểu <code>idx_status</code> có thể gây va chạm.

Quy ước như <code>idx_invoice_status</code> và <code>idx_payment_status</code> giúp reviewer biết đối tượng nào được thay đổi và giảm nguy cơ xung đột.

## 5. objectQuotingStrategy dùng để làm gì?

Liquibase có thuộc tính **<code>objectQuotingStrategy</code>** để quyết định chiến lược trích dẫn tên đối tượng database trong SQL do Liquibase tạo. Đây là thiết lập có ảnh hưởng rộng tới cách tên bảng, cột, schema, ràng buộc và các identifier liên quan được biểu diễn.

Ba giá trị thường dùng:

| Giá trị | Ý nghĩa | Lợi ích | Rủi ro/chi phí |
|---|---|---|---|
| <code>LEGACY</code> | Hành vi tương thích lịch sử của Liquibase; dùng cơ chế quoting tự động cho những tên cần thiết theo cách công cụ/DBMS xử lý | Phù hợp khi duy trì changelog cũ và conventions hiện có | Hành vi cụ thể với tên đặc biệt/từ khóa có thể phụ thuộc phiên bản và DBMS |
| <code>QUOTE_ALL_OBJECTS</code> | Yêu cầu Liquibase trích dẫn tất cả identifier mà công cụ sinh ra | Giúp bảo toàn kiểu chữ và sử dụng tên đặc biệt trong nhiều tình huống | Dễ tạo lệch tên so với schema không trích dẫn, SQL viết tay hoặc ORM |
| <code>QUOTE_ONLY_RESERVED_WORDS</code> | Chỉ trích dẫn những identifier được Liquibase/DBMS nhận diện là từ khóa dành riêng | Giảm trích dẫn không cần thiết nếu tên đã theo quy ước đơn giản | Tên có khoảng trắng hoặc ký tự đặc biệt không phải reserved word có thể không được quote phù hợp |

Không có chiến lược nào tự biến một convention tên kém thành an toàn trên mọi DBMS. Liquibase vẫn phải biết DBMS và trình sinh SQL tương ứng, trong khi SQL thuần tùy chỉnh có thể không được viết lại bằng chiến lược quoting này.

### 5.1. LEGACY

<code>LEGACY</code> thường là lựa chọn tương thích với hành vi trước đây của Liquibase. Nó phù hợp khi một dự án có nhiều changeset đã chạy theo quy tắc cũ và chưa có lý do thay đổi toàn cục. Hành vi auto-quoting cho từ khóa, ký tự đặc biệt hoặc tên không hợp lệ có thể thay đổi theo tính năng và phiên bản; vì vậy phải đọc SQL preview của chính bản Liquibase đang dùng.

Không nên hiểu “legacy” là “không bao giờ trích dẫn”. Chỉ nhìn giá trị <code>LEGACY</code> không đủ để kết luận Liquibase sẽ sinh SQL nguyên văn tên bảng.

### 5.2. QUOTE_ALL_OBJECTS

Với <code>QUOTE_ALL_OBJECTS</code>, tên các đối tượng mà Liquibase sinh SQL cho sẽ được trích dẫn theo quy tắc quoting của DBMS đích.

Một thay đổi khai báo tên <code>CustomerOrder</code> có thể dẫn đến SQL tương tự trên PostgreSQL:

~~~sql
CREATE TABLE "CustomerOrder" (
    "OrderID" BIGINT NOT NULL
);
~~~

Khi đó câu truy vấn <code>SELECT OrderID FROM CustomerOrder</code> không thể được coi là tương đương với câu truy vấn đã trích dẫn. Việc bật chiến lược này trên hệ thống đã tồn tại các bảng không trích dẫn như <code>customerorder</code> có thể làm Liquibase tìm sai đối tượng, tạo đối tượng mới hoặc gặp lỗi.

<code>QUOTE_ALL_OBJECTS</code> phù hợp nhất khi dự án có quy tắc tên đã thống nhất, công cụ truy cập dữ liệu biết rõ identifier được quote, và migration đã được kiểm thử trên DBMS thực tế.

### 5.3. QUOTE_ONLY_RESERVED_WORDS

Chiến lược này hữu ích khi dự án tuân thủ convention tên đơn giản nhưng một số identifier xung đột với từ khóa dành riêng. Ví dụ bảng có tên <code>order</code> có thể cần trích dẫn khi dùng trong SQL.

Điểm dễ sai là tưởng chiến lược này sẽ tự động xử lý mọi tên bất thường. Tên <code>customer-order</code> có dấu gạch ngang không nhất thiết là từ khóa dành riêng; nếu không được trích dẫn, SQL có thể thất bại. Giải pháp tốt hơn là đổi tên thành <code>customer_order</code> theo convention.

Không dùng chiến lược này để hợp thức hóa việc tạo nhiều tên có khoảng trắng hoặc ký tự đặc biệt mà ứng dụng sau đó khó tham chiếu.

## 6. Cấu hình objectQuotingStrategy ở đâu?

Liquibase hỗ trợ khai báo chiến lược quoting ở mức changelog hoặc ở changeset tùy định dạng changelog và phiên bản. Cần xác định phạm vi hiệu lực thực tế: một khai báo ở changelog gốc có thể là mặc định cho các changeset trong phạm vi đó, còn changeset có thể chỉ định giá trị riêng.

### 6.1. Ví dụ XML ở mức changelog

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://www.liquibase.org/xml/ns/dbchangelog
                        https://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-latest.xsd"
    objectQuotingStrategy="QUOTE_ALL_OBJECTS">

    <changeSet id="001-create-invoice" author="db-team">
        <createTable tableName="Invoice">
            <column name="InvoiceID" type="bigint">
                <constraints primaryKey="true" nullable="false"/>
            </column>
        </createTable>
    </changeSet>
</databaseChangeLog>
~~~

Ví dụ minh họa sử dụng chiến lược quoting cho các tên được Liquibase sinh SQL từ changelog này. Tệp XML thật phải tuân theo XSD tương thích với phiên bản Liquibase được dự án sử dụng.

### 6.2. Ví dụ YAML ở mức changeset

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 002-create-invoice-note
      author: db-team
      objectQuotingStrategy: QUOTE_ALL_OBJECTS
      changes:
        - createTable:
            tableName: InvoiceNote
            columns:
              - column:
                  name: NoteID
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
~~~

Thiết lập trên cho thấy ý định áp dụng chiến lược tại changeset cụ thể. Khi kết hợp changelog gốc, include và thiết lập riêng, hãy kiểm tra chiến lược hiệu lực của từng changeset bằng cách sinh SQL. Không nên dự đoán precedence qua nhiều định dạng và phiên bản mà chưa thử.

### 6.3. Không coi đây là quy tắc escape dữ liệu

<code>objectQuotingStrategy</code> nhắm vào **identifier** do Liquibase quản lý. Nó không thay thế việc escape literal, chống SQL injection hoặc xây dựng tham số truy vấn an toàn. Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 003-manual-sql
      author: db-team
      objectQuotingStrategy: QUOTE_ALL_OBJECTS
      changes:
        - sql:
            sql: SELECT CustomerName FROM CustomerOrder
~~~

Đoạn SQL viết tay vẫn chứa tên <code>CustomerName</code> và <code>CustomerOrder</code> không trích dẫn. Không được mặc định Liquibase sẽ phân tích và viết lại từng identifier trong khối SQL tùy chỉnh. Nếu đã chọn bảng/cột có tên yêu cầu quoting, người viết SQL thuần phải dùng cú pháp đúng DBMS hoặc cơ chế được công cụ hỗ trợ.

## 7. Khi nào chọn chiến lược nào?

Không cần đổi <code>objectQuotingStrategy</code> chỉ vì một migration gặp lỗi tên đối tượng. Trước tiên phải xác định schema hiện có, SQL được sinh ra và convention mà ứng dụng đang dùng.

| Bối cảnh | Hướng quyết định |
|---|---|
| Dự án mới, tên theo chữ thường <code>snake_case</code>, tránh reserved words | Có thể bắt đầu với hành vi mặc định/LEGACY, thử trên DBMS đích và giữ convention ổn định |
| Dự án có identifier chữ hoa/thường được giữ đúng và mọi truy vấn/ORM đã thống nhất dùng quoted names | Cân nhắc <code>QUOTE_ALL_OBJECTS</code> và kiểm thử kỹ khả năng tương thích |
| Tên thông thường hợp lệ, nhưng có một vài từ khóa dành riêng phải được trích dẫn | Cân nhắc <code>QUOTE_ONLY_RESERVED_WORDS</code>, đồng thời ưu tiên đổi tên nếu có thể |
| Hệ thống legacy có các bảng được tạo bằng nhiều convention khác nhau | Lập danh mục đối tượng vật lý rồi kiểm thử từng changeset; tránh chuyển chiến lược toàn cục đột ngột |
| Hệ thống dùng nhiều DBMS | Ưu tiên tên đơn giản, sinh SQL riêng cho mỗi DBMS và xác minh quoting thực tế |
| SQL tùy chỉnh hoặc stored procedures dùng nhiều identifier | Review SQL thủ công; chiến lược Liquibase không thay thế cú pháp trích dẫn trong SQL đó |

Với hệ thống đã triển khai, thay đổi chiến lược cho các changeset cũ có thể làm SQL cho lần chạy ở môi trường mới khác với lịch sử mà nhóm dự định. Không nên sửa ngược các changeset đã chạy chỉ để đồng nhất cách viết tên; hãy thiết kế changeset mới và kiểm chứng tương thích.

## 8. Kết hợp tham số changelog với quy tắc đặt tên

Trong chương **Tham số hóa**, một yêu cầu phổ biến là cùng changelog chạy trên schema khác nhau theo môi trường. Ví dụ, dùng thuộc tính <code>${app.schema}</code> để chọn schema nghiệp vụ.

~~~yaml
databaseChangeLog:
  - property:
      name: app.schema
      value: billing_dev

  - changeSet:
      id: 004-create-payment
      author: db-team
      changes:
        - createTable:
            schemaName: ${app.schema}
            tableName: payment
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: created_at
                  type: timestamp
~~~

Nếu <code>app.schema</code> có giá trị hiệu lực <code>billing_dev</code>, thay đổi sẽ nhắm tới schema đó khi Liquibase tạo SQL. Nếu pipeline cung cấp một giá trị khác, phải dùng giá trị đã được resolve ở thời điểm chạy để xác định đích.

Các quy tắc cần nhớ:

1. **Giá trị thay thế phải là identifier hợp lệ theo DBMS.** Tham số hóa không tự hợp thức hóa tên có khoảng trắng, từ khóa hoặc ký tự không hỗ trợ.
2. **Chỉ truyền giá trị tên, không truyền dấu quote bọc sẵn**, trừ khi đã xác minh rất rõ cơ chế xử lý của phiên bản/cách tích hợp. Ví dụ nên truyền <code>billing_prod</code>, không truyền <code>"billing_prod"</code> vào <code>schemaName</code>.
3. **Tên được tham số hóa và default schema là hai nguồn khác nhau.** Có thể đặt <code>schemaName: ${app.schema}</code> nhưng <code>defaultSchemaName</code> của Liquibase vẫn là schema khác.
4. **Phải kiểm tra thứ tự và ưu tiên property.** Một giá trị đã đăng ký từ CLI, Spring Boot hoặc pipeline có thể được ưu tiên hơn giá trị mặc định trong changelog.
5. **Không nhận identifier tùy ý từ người dùng ứng dụng.** Chỉ dùng giá trị nằm trong cấu hình triển khai được kiểm soát và kiểm tra theo whitelist/quy tắc tên.

### 8.1. Ví dụ tên schema có chữ hoa

Giả sử môi trường đã có schema PostgreSQL <code>"BillingProd"</code>. Truy cập nó có thể yêu cầu giữ nguyên chữ B và P kèm quoting phù hợp. Chỉ đổi tham số <code>app.schema=BillingProd</code> nhưng để Liquibase sinh SQL không trích dẫn có thể khiến SQL nhắm tới <code>billingprod</code>, là một tên khác.

Để xử lý đúng:

- Kiểm tra tên schema thực trong catalog.
- Xác định chiến lược quoting và cấu hình liên quan đến cách bảo toàn kiểu chữ của schema.
- Dùng SQL preview để xem tên schema sau khi đã thay tham số.
- Kiểm thử trên cùng loại và phiên bản DBMS với môi trường đích.
- Bảo đảm ứng dụng, ORM, SQL viết tay và lệnh rollback cũng tham chiếu cùng tên.

Một số phiên bản Liquibase có tùy chọn như <code>preserve-schema-case</code> để xử lý chữ hoa/thường của schema. Tên và khả năng áp dụng của tùy chọn này phụ thuộc phiên bản và cách chạy; nó không thay thế <code>objectQuotingStrategy</code> trong mọi tình huống. Không tự thêm tùy chọn khi chưa xác minh sự hỗ trợ và SQL thực tế.

## 9. Ảnh hưởng tới migration, checksum và rollback

### 9.1. Không đổi cách quote của changeset đã triển khai

Liquibase nhận diện changeset bằng bộ ba id, author và đường dẫn changelog (hoặc logical file path khi được cấu hình). Sau khi áp dụng, Liquibase ghi lịch sử và checksum vào <code>DATABASECHANGELOG</code>.

Nếu sửa tên đối tượng hoặc <code>objectQuotingStrategy</code> của changeset đã chạy, nội dung được sinh SQL cho một môi trường khác có thể thay đổi. Thay đổi này có thể gây lỗi checksum tùy nội dung/phiên bản, hoặc tạo khác biệt giữa các database, ngay cả khi có những thuộc tính không làm checksum thay đổi.

**Không dựa vào checksum như bằng chứng đầy đủ rằng tên vật lý, cách quoting và schema của mọi môi trường là giống nhau.** Checksum giúp phát hiện một số thay đổi nội dung changelog; còn trạng thái schema thực tế phải được kiểm tra tại DBMS đích.

Khi cần đổi tên bảng hoặc cột, nên viết changeset mới có chủ đích, lựa chọn thao tác rename phù hợp, rồi cập nhật mã ứng dụng và migration liên quan. Tránh sửa changeset lịch sử để thay đổi tên đối tượng đã tồn tại.

### 9.2. Rollback phải dùng cùng cách định danh

Giả sử changeset tạo bảng <code>"CustomerOrder"</code> dưới chiến lược trích dẫn toàn bộ identifier. Nếu rollback tự viết bằng SQL:

~~~sql
DROP TABLE CustomerOrder;
~~~

thì trên PostgreSQL, câu lệnh có thể nhắm tới <code>customerorder</code> thay vì <code>"CustomerOrder"</code>. Rollback có thể lỗi hoặc tác động nhầm đối tượng nếu schema thực tế tồn tại cả hai tên.

Một rollback được kiểm chứng cần:

- Dùng đúng schema, tên bảng/cột và kiểu chữ so với lần update.
- Cân nhắc dùng các loại change rollback của Liquibase thay vì SQL tự viết khi phù hợp.
- Kiểm tra SQL rollback dự kiến bằng chức năng preview của phiên bản Liquibase.
- Đánh giá tác động mất dữ liệu và tính tương thích với ứng dụng; rollback hợp lệ về cú pháp không đồng nghĩa rollback an toàn.

Đặc biệt với dữ liệu production, thay đổi chiến lược quoting không thể thay thế kế hoạch backup, restore hoặc forward fix.

### 9.3. Precondition và kiểm tra đối tượng

Precondition như <code>tableExists</code> hoặc <code>columnExists</code> giúp kiểm tra trạng thái trước khi thay đổi. Nhưng để có ý nghĩa, tên trong precondition cần khớp với schema và identifier thực tế, gồm cả cách xử lý chữ hoa/thường.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 005-add-payment-reference
      author: db-team
      preConditions:
        - onFail: HALT
        - tableExists:
            schemaName: billing_dev
            tableName: payment
      changes:
        - addColumn:
            schemaName: billing_dev
            tableName: payment
            columns:
              - column:
                  name: reference_code
                  type: varchar(64)
~~~

**Lưu ý cú pháp:** trong YAML, <code>preConditions</code> dùng các mục danh sách cho thuộc tính điều khiển và điều kiện theo cấu trúc mà phiên bản Liquibase hỗ trợ. Phải validate trước khi sử dụng. Khi schema được tham số hóa, cần áp dụng cùng tham số và convention cho precondition lẫn change để tránh precondition kiểm tra đối tượng này còn change tác động đối tượng khác.

## 10. Ví dụ thực hành trên PostgreSQL

Hãy so sánh hai tình huống tạo bảng để thấy tác động của quoting. Những ví dụ này là tài liệu minh họa, không yêu cầu chạy trên cơ sở dữ liệu production.

### 10.1. Bảng chữ thường theo convention

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 010-create-customer-order
      author: db-team
      changes:
        - createTable:
            schemaName: sales_app
            tableName: customer_order
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: created_at
                  type: timestamp
~~~

Với tên chữ thường và gạch dưới, SQL sinh ra thường dễ đọc và ít phụ thuộc vào quoting. Nếu thay đổi strategy sang <code>QUOTE_ALL_OBJECTS</code>, SQL có thể trích dẫn <code>"sales_app"</code>, <code>"customer_order"</code> và <code>"created_at"</code>, nhưng trên PostgreSQL chúng vẫn tương ứng với cùng kiểu chữ thường nếu schema/tên đã tồn tại như vậy.

### 10.2. Bảng CamelCase

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 011-create-camelcase-order
      author: db-team
      objectQuotingStrategy: QUOTE_ALL_OBJECTS
      changes:
        - createTable:
            schemaName: sales_app
            tableName: CustomerOrder
            columns:
              - column:
                  name: OrderID
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
~~~

Với chiến lược trích dẫn toàn bộ, trên PostgreSQL ta kỳ vọng SQL tương đương:

~~~sql
CREATE TABLE "sales_app"."CustomerOrder" (
    "OrderID" BIGINT NOT NULL,
    CONSTRAINT "..." PRIMARY KEY ("OrderID")
);
~~~

Dấu ba chấm ở tên ràng buộc chỉ là ký hiệu minh họa; tên và cách thể hiện thực tế phụ thuộc Liquibase/DBMS. Trước khi chạy, cần xem bản SQL thật, không sao chép SQL minh họa để triển khai.

### 10.3. Kiểm tra tên vật lý sau thử nghiệm

Trên database PostgreSQL dùng riêng cho học tập, có thể xem tên bảng:

~~~sql
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'sales_app'
  AND lower(table_name) = lower('CustomerOrder')
ORDER BY table_name;
~~~

Nếu tồn tại cả <code>customerorder</code> và <code>CustomerOrder</code> (hai tên khác nhau khi quoting), truy vấn này có thể trả về hai bản ghi. Cần so sánh chính xác giá trị <code>table_name</code>, không chỉ so khớp không phân biệt hoa/thường.

Để quan sát SQL migration trước khi thực hiện, dùng những lệnh phù hợp với phiên bản CLI đang sử dụng:

~~~bash
liquibase --defaults-file=./liquibase-test.properties validate
liquibase --defaults-file=./liquibase-test.properties status --verbose
liquibase --defaults-file=./liquibase-test.properties update-sql
~~~

Các lệnh trên minh họa quy trình preflight; với một số phiên bản, lệnh sinh SQL có thể có cách viết khác như <code>updateSQL</code>. Cần cố định phiên bản CLI và kiểm tra trợ giúp tương ứng.

**Mục tiêu của thử nghiệm:** xem sự khác nhau giữa identifier không trích dẫn và có trích dẫn, đồng thời chứng minh liệu ứng dụng và rollback có truy cập đúng bảng hay không.

## 11. Tình huống lỗi và hướng khắc phục

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| PostgreSQL báo relation không tồn tại dù bảng có trong catalog | Bảng được tạo với chữ hoa/thường có trích dẫn, truy vấn dùng tên không trích dẫn | Đối chiếu <code>table_schema</code>, <code>table_name</code> và SQL được sinh |
| Migration tạo bảng ở schema không mong muốn | Schema mặc định hoặc property <code>${app.schema}</code> được resolve sai | Kiểm tra schema/config hiệu lực, tham số changelog và SQL preview |
| Tên trùng trên một DBMS nhưng không trùng trên DBMS khác | Quy tắc gập chữ, collation hoặc cài đặt case khác nhau | Thử trên đúng DBMS, tránh chỉ phân biệt tên bằng hoa/thường |
| Dùng <code>QUOTE_ALL_OBJECTS</code> rồi ứng dụng không đọc được bảng | App/ORM dùng identifier không trích dẫn hoặc naming strategy khác | Kiểm tra SQL của ứng dụng và mapping tên vật lý |
| <code>QUOTE_ONLY_RESERVED_WORDS</code> không xử lý được tên có gạch ngang | Tên đặc biệt không nhất thiết là reserved word | Đổi tên theo <code>snake_case</code> hoặc cấu hình quoting có kiểm chứng |
| Liquibase không tìm thấy đối tượng có tên CamelCase | Tên được lưu với quoted identifier, precondition/change tham chiếu kiểu chữ khác | Xác minh tên trong catalog, schema và strategy |
| SQL viết tay lỗi dù <code>QUOTE_ALL_OBJECTS</code> đã bật | Chiến lược không tự rewrite toàn bộ SQL tự do | Viết đúng SQL theo DBMS hoặc thay bằng change type của Liquibase |
| Chỉ mục/ràng buộc có tên quá dài | Quy ước ghép tên vượt giới hạn DBMS | Rút ngắn tên, kiểm tra collision và chuẩn đặt tên |
| Các môi trường có bảng khác nhau sau cùng release | Giá trị parameter, quoting hoặc DBMS khác nhau | Đối chiếu manifest, SQL preview và trạng thái schema thực |
| Rollback xóa sai bảng hoặc thất bại | Tên/schema/quote trong rollback không khớp change đã chạy | Review rollback SQL, kiểm tra đối tượng trước khi thực thi |
| Checksum bất thường sau sửa tên | Changelog đã phát hành bị thay đổi | So sánh bản đã phát hành, tạo changeset mới thay vì sửa lịch sử |

Khi điều tra, tuyệt đối không dùng việc xóa bảng lịch sử hoặc sửa checksum như một cách che giấu sai khác tên đối tượng. Trước tiên phải tìm ra chính xác Liquibase đã tạo hoặc muốn truy cập đối tượng nào.

## 12. Quy trình kiểm tra trước triển khai

Mỗi migration có tác động tới tên đối tượng nên qua quy trình sau:

1. **Lập danh sách identifier.** Ghi rõ schema/catalog, tên bảng, cột, chỉ mục, ràng buộc, view và sequence sẽ bị ảnh hưởng.
2. **Kiểm tra quy ước.** Tên có tuân thủ chữ thường <code>snake_case</code>, không trùng, không quá dài và tránh reserved words không?
3. **Đối chiếu schema hiện có.** Truy vấn catalog của DBMS thật để xác nhận tên vật lý và chữ hoa/thường.
4. **Kiểm tra nguồn tham số.** Xác định giá trị của các placeholder <code>${...}</code>, nguồn thắng và khác biệt giữa local/test/staging/production.
5. **Xác định quoting strategy.** Ghi lại chiến lược hiệu lực ở changelog/changeset; không dựa vào giả định về mặc định.
6. **Sinh SQL.** Review schema, quote, tên đối tượng, từ khóa dành riêng, tên ràng buộc và cú pháp theo DBMS.
7. **Kiểm tra ứng dụng.** Xác nhận JDBC/ORM/SQL viết tay, truy vấn báo cáo và thao tác quản trị có thể tham chiếu identifier mới.
8. **Kiểm thử rollback.** Đọc SQL rollback hoặc chạy thử ở môi trường an toàn; bảo đảm không nhắm sai đối tượng.
9. **Kiểm thử nhiều môi trường.** Với dự án đa DBMS hoặc nhiều schema, chạy trên đúng engine/version và bộ tham số tương ứng.
10. **Lưu bằng chứng.** Ghi changelog version, checksum/historical state khi phù hợp, bộ tham số, strategy và kết quả review trong pipeline.

Một checklist ngắn để reviewer đối chiếu:

- [ ] Tên identifier không chỉ khác nhau bởi chữ hoa/thường.
- [ ] Tên và schema trong changelog khớp catalog database dự kiến.
- [ ] Changelog parameters không chứa quote thừa và không lấy từ đầu vào không đáng tin cậy.
- [ ] <code>objectQuotingStrategy</code> có giá trị chủ đích, được kiểm chứng trong SQL preview.
- [ ] SQL viết tay không dựa vào giả định Liquibase tự thêm quote.
- [ ] Changeset đã triển khai không bị đổi tên đối tượng hoặc strategy tùy tiện.
- [ ] Preconditions và rollback trỏ đúng đối tượng theo tên/schema/kiểu chữ.
- [ ] Cùng artifact và tham số được dùng từ preview đến update.
- [ ] Có phương án xử lý khi database dùng legacy mixed-case names.

## 13. Những kết luận cần nhớ

**Quy tắc đặt tên** quyết định khả năng duy trì sự nhất quán giữa changelog, DBMS và mã ứng dụng. **Chữ hoa/thường** quyết định việc một identifier không trích dẫn sẽ được lưu hoặc tra cứu thế nào. **<code>objectQuotingStrategy</code>** quyết định cách Liquibase trích dẫn identifier khi sinh SQL, nhưng không tự sửa SQL viết tay hoặc giải quyết xung đột giữa các môi trường.

Với dự án mới, tên chữ thường <code>snake_case</code>, không dùng từ khóa dành riêng và quy ước nhất quán thường là xuất phát điểm dễ bảo trì. Với hệ thống legacy hoặc có quoted identifiers, cần xác minh tên vật lý và chọn strategy theo thực tế. Trước mọi migration, hãy kiểm tra **giá trị tham số → SQL sinh ra → đối tượng trong catalog → tương thích ứng dụng/rollback**. Đây là cách duy trì lịch sử thay đổi schema và dữ liệu rõ ràng, kiểm chứng được và an toàn khi Liquibase chạy qua Spring Boot hoặc CI/CD.
