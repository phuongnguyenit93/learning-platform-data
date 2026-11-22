# Kết hợp điều kiện bằng AND, OR và NOT trong Liquibase

## 1. Vì sao cần kết hợp nhiều tiền điều kiện?

Trong Liquibase, **precondition (tiền điều kiện)** là một phép kiểm tra được đánh giá trước khi thực hiện thay đổi được mô tả trong changelog hoặc changeset. Một migration có thể yêu cầu nhiều giả định cùng đúng: bảng đã tồn tại, cột chưa có, DBMS đang dùng được hỗ trợ, và dữ liệu cũ đã được chuẩn bị. Nếu chỉ kiểm tra một yếu tố, changeset vẫn có thể thất bại hoặc gây ra trạng thái ngoài dự kiến.

Ví dụ cần thêm cột <code>customer.phone_number</code>. Điều kiện an toàn tối thiểu có thể là:

- Bảng <code>customer</code> đã tồn tại.
- Cột <code>phone_number</code> **chưa** tồn tại.
- DBMS và schema được kết nối đúng như thiết kế.

Logic mà người viết muốn diễn đạt là: **bảng tồn tại AND NOT(cột tồn tại)**. Nếu cho phép chạy trên hai loại DBMS, có thể bổ sung **(DBMS = PostgreSQL OR DBMS = MySQL)**. Liquibase hỗ trợ ba toán tử logic <code>and</code>, <code>or</code> và <code>not</code> để diễn đạt các mối quan hệ như vậy ngay trong precondition.

Bài thuộc chương **Tiền điều kiện** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Phạm vi module là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Hiểu đúng điều kiện logic giúp changelog thể hiện rõ giả định, chặn thay đổi khi schema sai trạng thái, và đưa ra kết quả triển khai có thể kiểm chứng.

Sau bài này, người học có thể:

1. Viết biểu thức logic lồng nhau từ các precondition cơ bản.
2. Phân biệt kết quả điều kiện **sai** với lỗi **không đánh giá được**.
3. Chọn <code>onFail</code> và <code>onError</code> phù hợp với tính chất rủi ro.
4. Dự đoán khi nào một changeset được chạy, bị chặn, bỏ qua hoặc ghi nhận là đã xử lý.
5. Kiểm thử biểu thức logic trên từng môi trường trước khi triển khai thật.

## 2. Precondition được đánh giá ở đâu?

Trong changelog, precondition có thể được khai báo ở **mức changelog** hoặc **mức changeset**.

| Phạm vi | Ý nghĩa | Khi nên dùng |
|---|---|---|
| Changelog | Xác nhận điều kiện chung cho toàn bộ quá trình xử lý changelog | Kiểm tra DBMS, trạng thái nền tảng, hoặc một điều kiện bắt buộc trước khi áp dụng các thay đổi |
| Changeset | Xác nhận giả định ngay trước khi một changeset cụ thể được xét thực thi | Kiểm tra bảng/cột/chỉ mục và dữ liệu mà một thay đổi phụ thuộc |

Một precondition ở mức changeset không có nghĩa đã áp dụng cho mọi changeset còn lại. Ngược lại, một điều kiện ở mức changelog không thay thế được những kiểm tra riêng cho từng thay đổi. Tốt nhất đặt điều kiện ở phạm vi nhỏ nhất vẫn diễn đạt đúng ràng buộc.

Các loại precondition thường gặp:

| Precondition | Câu hỏi mà nó trả lời |
|---|---|
| <code>dbms</code> | Kết nối đang dùng loại DBMS cho phép hay không? |
| <code>tableExists</code> | Bảng đích có tồn tại không? |
| <code>columnExists</code> | Cột đã tồn tại trong bảng đích chưa? |
| <code>indexExists</code> | Chỉ mục có tên/cấu trúc được kiểm tra có tồn tại không? |
| <code>foreignKeyConstraintExists</code> | Khóa ngoại có tồn tại theo metadata DBMS không? |
| <code>primaryKeyExists</code> | Khóa chính đã tồn tại chưa? |
| <code>sqlCheck</code> | Kết quả của truy vấn SQL có bằng giá trị kỳ vọng không? |
| <code>runningAs</code> | Vai trò hoặc tài khoản kết nối có đúng người thực thi dự kiến không? |
| <code>changeSetExecuted</code> | Changeset phụ thuộc đã được ghi nhận trong lịch sử chưa? |

Các precondition có thể có khác biệt về thuộc tính được hỗ trợ hoặc cách đọc metadata giữa DBMS và phiên bản Liquibase. Đừng giả định mọi điều kiện đều rẻ, không phụ thuộc quyền, hoặc có thể chạy giống nhau trên mọi database.

## 3. Logic AND, OR, NOT: nguyên lý cốt lõi

Giả sử <code>A</code> và <code>B</code> là hai điều kiện trả về kết quả đúng (<code>true</code>) hoặc sai (<code>false</code>).

| A | B | A AND B | A OR B |
|---|---|---|---|
| Đúng | Đúng | Đúng | Đúng |
| Đúng | Sai | Sai | Đúng |
| Sai | Đúng | Sai | Đúng |
| Sai | Sai | Sai | Sai |

<code>NOT A</code> đảo kết quả của <code>A</code>: A đúng thì NOT A sai, A sai thì NOT A đúng.

Ba toán tử có ý nghĩa:

- **AND:** mọi điều kiện con đều phải đúng. Dùng khi migration có nhiều điều kiện bắt buộc đồng thời.
- **OR:** ít nhất một điều kiện con phải đúng. Dùng khi có nhiều trạng thái thay thế đều được chấp nhận.
- **NOT:** điều kiện con phải sai. Dùng để diễn đạt “chưa tồn tại”, “không thuộc nhóm”, hoặc phủ định một biểu thức phức hợp.

Ví dụ:

| Biểu thức | Diễn đạt bằng lời |
|---|---|
| <code>tableExists(customer) AND NOT columnExists(customer.email)</code> | Chỉ thêm cột khi có bảng và chưa có cột |
| <code>dbms(postgresql) OR dbms(mysql)</code> | Chỉ chấp nhận một trong hai loại DBMS |
| <code>NOT indexExists(idx_customer_email)</code> | Chỉ tiếp tục nếu chưa có chỉ mục tên đó |
| <code>A AND (B OR C)</code> | A bắt buộc; đồng thời phải có B hoặc C |
| <code>NOT (A OR B)</code> | Cả A lẫn B đều không được đúng |

Trong Liquibase, các điều kiện thông thường ở cùng cấp thường được kết hợp ngầm theo logic AND. Tuy nhiên, **khi cần diễn đạt ý định một cách rõ ràng hoặc lồng OR/NOT, nên viết các nhóm logic tường minh**.

### 3.1. Dùng dấu ngoặc trong tư duy, dùng cấu trúc lồng nhau trong changelog

Biểu thức toán học:

~~~text
DBMS_OK AND TABLE_EXISTS AND NOT COLUMN_EXISTS
~~~

Cách đọc:

~~~text
AND
├── OR
│   ├── DBMS = PostgreSQL
│   └── DBMS = MySQL
├── tableExists(customer)
└── NOT
    └── columnExists(customer.phone_number)
~~~

Trong YAML, XML hoặc JSON, cấp thụt lề và khối lồng nhau thay cho dấu ngoặc toán học. **Sai cấp thụt lề có thể đổi nghĩa của cả biểu thức**, cho dù từng điều kiện riêng lẻ đều hợp lý.

### 3.2. Các quy tắc biến đổi logic

Một vài đẳng thức hữu ích khi review:

- <code>NOT (A AND B)</code> tương đương <code>(NOT A) OR (NOT B)</code>.
- <code>NOT (A OR B)</code> tương đương <code>(NOT A) AND (NOT B)</code>.
- <code>NOT (NOT A)</code> tương đương <code>A</code>.

Đây là các quy tắc logic Boolean. Trong thực thi thật, một precondition còn có khả năng **lỗi khi đánh giá**. Các đẳng thức trên chỉ diễn tả quan hệ đúng/sai khi mọi điều kiện được đánh giá bình thường; chúng không đảm bảo hai cấu trúc sẽ có cùng chi phí, cùng số lần truy cập metadata hay cùng thứ tự phát sinh lỗi.

## 4. Mẫu YAML cơ bản cho các nhóm logic

Một changeset chỉ thêm cột khi bảng đã tồn tại và cột chưa tồn tại:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-add-customer-phone
      author: db-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - and:
            - tableExists:
                tableName: customer
            - not:
                - columnExists:
                    tableName: customer
                    columnName: phone_number
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: phone_number
                  type: varchar(30)
~~~

Đây là hình thức phổ biến trong YAML changelog: <code>preConditions</code> là danh sách, còn <code>and</code>, <code>not</code> cũng chứa các điều kiện con. Cần giữ chính xác cấu trúc list và mức thụt lề khi chuyển đổi từ XML sang YAML.

Giả sử:

- <code>customer</code> đã tồn tại;
- <code>phone_number</code> chưa tồn tại;
- Liquibase đang kết nối đúng database/schema.

Khi đó <code>tableExists</code> đúng, <code>columnExists</code> sai, <code>not</code> đảo thành đúng, và toàn bộ <code>and</code> đúng. Liquibase có thể tiếp tục thực thi changeset.

Nếu bảng không tồn tại, nhóm AND sai; <code>onFail: HALT</code> yêu cầu dừng xử lý. Nếu không thể đọc metadata vì lỗi quyền hoặc kết nối, đó có thể là **error** chứ không chỉ một phép kiểm tra sai; <code>onError: HALT</code> cũng yêu cầu dừng.

**Lưu ý:** mã ví dụ minh họa logic và cú pháp changelog. Cần validate bằng phiên bản Liquibase thực tế, xác minh schema đích, và đánh giá tính tương thích ứng dụng trước khi triển khai.

## 5. AND: tất cả giả định phải được thỏa mãn

AND phù hợp với các migration yêu cầu **nhiều điều kiện bắt buộc** cùng đúng. Chẳng hạn, tạo chỉ mục cho cột <code>order_number</code> chỉ an toàn khi bảng và cột đã tồn tại, nhưng chỉ mục chưa có.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 002-index-orders-order-number
      author: db-team
      preConditions:
        - onFail: HALT
        - and:
            - tableExists:
                tableName: orders
            - columnExists:
                tableName: orders
                columnName: order_number
            - not:
                - indexExists:
                    tableName: orders
                    indexName: idx_orders_order_number
      changes:
        - createIndex:
            tableName: orders
            indexName: idx_orders_order_number
            columns:
              - column:
                  name: order_number
~~~

Thứ tự diễn giải:

1. Phải có bảng <code>orders</code>.
2. Phải có cột <code>orders.order_number</code>.
3. Phải **chưa** có chỉ mục <code>idx_orders_order_number</code>.
4. Nếu tất cả đều đúng, changeset mới được phép tạo chỉ mục.

AND bảo vệ khỏi lỗi “tạo chỉ mục cho cột chưa tồn tại” và “trùng tên chỉ mục”. Tuy vậy, nó **không chứng minh** rằng cột có kiểu dữ liệu phù hợp, chỉ mục sẽ được tạo không khóa bảng quá lâu, hay database còn đủ tài nguyên. Một số thông tin cần được xác minh bằng công cụ khác hoặc thử nghiệm trên DBMS đích.

### 5.1. AND ngầm và AND tường minh

Trong nhiều changelog, các điều kiện đặt liền nhau cùng cấp có nghĩa kết hợp AND, ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 003-example-implicit-and
      author: db-team
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: customer
        - columnExists:
            tableName: customer
            columnName: id
      changes:
        - tagDatabase:
            tag: customer-schema-checked
~~~

Chỉ nên dựa vào cách viết ngắn khi cả nhóm đều có nghĩa **tất cả phải đúng**. Nếu sau này yêu cầu trở thành “A và (B hoặc C)”, hãy bổ sung khối <code>and</code>/<code>or</code> rõ ràng để tránh người đọc hiểu sai.

## 6. OR: chấp nhận một trong nhiều khả năng

OR đúng nếu **ít nhất một** điều kiện con đúng. Một ví dụ hợp lý là cho phép một changeset chạy khi DBMS là PostgreSQL hoặc MySQL.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 004-create-import-batch
      author: db-team
      preConditions:
        - onFail: HALT
        - or:
            - dbms:
                type: postgresql
            - dbms:
                type: mysql
      changes:
        - createTable:
            tableName: import_batch
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
~~~

Nếu đang chạy trên PostgreSQL, điều kiện thứ nhất đúng; trên MySQL, điều kiện thứ hai đúng. Nếu là SQL Server, cả hai sai, nên nhóm OR sai và changeset bị dừng theo <code>onFail: HALT</code>.

**Lưu ý về thiết kế:** nếu một changeset chỉ phù hợp với một DBMS, thuộc tính <code>dbms</code> ở mức changeset có thể thể hiện mục đích gọn hơn. Nhóm OR hữu ích khi phải diễn đạt một điều kiện kết hợp nhiều khả năng, đặc biệt có thêm các điều kiện về schema hoặc dữ liệu.

### 6.1. OR là phép lựa chọn, không phải “thử điều kiện đầu rồi bỏ lỗi”

Giả sử hệ thống đang chuyển đổi từ cấu trúc cũ, có thể lưu thông tin trạng thái tại <code>customer.legacy_state</code> **hoặc** <code>customer.state_code</code>. Một precondition OR có thể kiểm tra:

~~~yaml
preConditions:
  - onFail: HALT
  - or:
      - columnExists:
          tableName: customer
          columnName: legacy_state
      - columnExists:
          tableName: customer
          columnName: state_code
~~~

Đoạn trên chỉ có nghĩa **ít nhất một cột tồn tại**. Nó không đảm bảo changeset SQL sau đó biết tự chọn cột nào. Nếu câu lệnh thay đổi luôn tham chiếu <code>state_code</code>, OR cho phép tình huống chỉ có <code>legacy_state</code> đi qua nhưng SQL vẫn thất bại.

Do đó, một biểu thức OR chỉ chính xác khi **mọi trạng thái được chấp nhận đều đủ điều kiện cho cùng một hành động phía sau**, hoặc logic changeset có nhánh xử lý phù hợp. Không dùng OR để che giấu việc schema giữa các môi trường đã lệch nhau mà chưa có kế hoạch hợp nhất.

### 6.2. Một lỗi thường gặp khi đặt OR sai cấp

Yêu cầu: “Chỉ chạy nếu A đúng và ít nhất một trong B, C đúng.”

Đúng: <code>A AND (B OR C)</code>.

Sai ý định: <code>(A AND B) OR C</code>, vì trường hợp C đúng cho phép đi qua ngay cả khi A sai.

Với một changeset quan trọng, nên viết biểu thức bằng lời và tạo bảng tình huống trước khi chuyển sang YAML. Điều này đặc biệt hữu ích khi nhóm OR chứa nhiều truy vấn metadata hoặc điều kiện dữ liệu.

## 7. NOT: yêu cầu một điều kiện không được đúng

NOT nhận một biểu thức con và phủ định kết quả đúng/sai của nó. Trong migration, NOT thường dùng với các điều kiện tồn tại:

~~~yaml
preConditions:
  - onFail: HALT
  - not:
      - columnExists:
          tableName: customer
          columnName: phone_number
~~~

Ý nghĩa: tiếp tục nếu cột <code>phone_number</code> **chưa** tồn tại.

Điểm quan trọng là **NOT không biến lỗi thành kết quả sai một cách tự động**. Nếu <code>columnExists</code> không thể đọc metadata vì kết nối bị ngắt hoặc thiếu quyền, đó có thể là lỗi đánh giá. <code>onError</code> xử lý trường hợp này; không được diễn giải thành “không đọc được thì chắc chắn cột không tồn tại”.

### 7.1. Phủ định một nhóm

Ví dụ: yêu cầu cả hai bảng thử nghiệm <code>temp_orders</code> và <code>temp_customers</code> **đều không tồn tại** trước khi bắt đầu một quy trình khởi tạo:

~~~yaml
preConditions:
  - onFail: HALT
  - not:
      - or:
          - tableExists:
              tableName: temp_orders
          - tableExists:
              tableName: temp_customers
~~~

Biểu thức tương ứng là <code>NOT (A OR B)</code>, tức <code>NOT A AND NOT B</code>. Nếu **bất kỳ** bảng nào đang tồn tại, điều kiện thất bại.

Không nhầm với:

~~~text
NOT (A AND B)
~~~

Biểu thức thứ hai chỉ yêu cầu **không phải cả hai cùng tồn tại**: vẫn cho phép một bảng tồn tại. Khác biệt nhỏ về cấu trúc cây logic có thể tạo khác biệt lớn về hành vi migration.

### 7.2. NOT và tính tái thực thi

Điều kiện <code>NOT tableExists</code> có thể giúp chặn chạy thay đổi tạo bảng khi bảng đã tồn tại, nhưng không tự mang lại “idempotence” cho toàn bộ hệ thống. Liquibase vốn dùng bảng lịch sử để quyết định changeset đã chạy hay chưa. Nếu bảng đã tồn tại do thao tác ngoài Liquibase, điều kiện sai và hệ thống phải xử lý sai lệch một cách chủ động.

Không nên mặc định “bảng đã có” nghĩa là nội dung bảng đúng với schema mong muốn. Bảng có thể thiếu ràng buộc, sai kiểu cột hoặc được tạo theo phiên bản khác. Đánh dấu changeset là đã chạy mà không xác minh trạng thái tương đương sẽ làm lịch sử khó tin cậy.

## 8. Lồng AND, OR, NOT trong cùng một cây điều kiện

Ví dụ một migration cho phép **PostgreSQL hoặc MySQL**, chỉ thực hiện khi bảng <code>customer</code> tồn tại, nhưng cột <code>external_ref</code> chưa tồn tại.

Viết dưới dạng toán:

~~~text
(DBMS = PostgreSQL OR DBMS = MySQL)
AND tableExists(customer)
AND NOT columnExists(customer.external_ref)
~~~

Changelog YAML:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 005-add-external-ref
      author: db-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - and:
            - or:
                - dbms:
                    type: postgresql
                - dbms:
                    type: mysql
            - tableExists:
                tableName: customer
            - not:
                - columnExists:
                    tableName: customer
                    columnName: external_ref
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: external_ref
                  type: varchar(64)
~~~

Ở đây, AND bao bọc toàn bộ. OR giới hạn loại DBMS được hỗ trợ, NOT xác nhận cột chưa có. Nếu hệ thống thực tế sử dụng schema riêng, cần bổ sung <code>schemaName</code> nhất quán vào precondition và change hoặc cấp default schema rõ ràng; nếu không, điều kiện có thể kiểm tra đối tượng khác với đối tượng mà SQL sẽ thay đổi.

### 8.1. Kiểm thử biểu thức bằng bảng tình huống

| DBMS | Bảng customer | Cột external_ref | Kết quả precondition |
|---|---|---|---|
| PostgreSQL | Có | Chưa có | Đúng: có thể chạy changeset |
| MySQL | Có | Chưa có | Đúng: có thể chạy changeset |
| PostgreSQL | Có | Đã có | Sai: HALT |
| PostgreSQL | Không | Chưa có | Sai: HALT |
| SQL Server | Có | Chưa có | Sai: HALT |
| MySQL | Không đọc được metadata | Không xác định | Có thể là ERROR: xử lý theo onError |

Bảng này là công cụ review quan trọng. Nó giúp kiểm tra liệu điều kiện được viết có chấp nhận đúng **những trạng thái mà change thật sự có thể xử lý** hay không.

## 9. Viết cùng biểu thức bằng XML

Liquibase hỗ trợ nhiều định dạng changelog. Trong XML, nhóm logic được biểu diễn bằng phần tử lồng nhau, còn <code>onFail</code> và <code>onError</code> thường là thuộc tính của <code>preConditions</code>.

Ví dụ tương đương với logic ở phần trước:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://www.liquibase.org/xml/ns/dbchangelog
                        https://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-latest.xsd">

    <changeSet id="005-add-external-ref" author="db-team">
        <preConditions onFail="HALT" onError="HALT">
            <and>
                <or>
                    <dbms type="postgresql"/>
                    <dbms type="mysql"/>
                </or>
                <tableExists tableName="customer"/>
                <not>
                    <columnExists
                        tableName="customer"
                        columnName="external_ref"/>
                </not>
            </and>
        </preConditions>

        <addColumn tableName="customer">
            <column name="external_ref" type="varchar(64)"/>
        </addColumn>
    </changeSet>
</databaseChangeLog>
~~~

Tương quan:

| YAML | XML |
|---|---|
| <code>and:</code> và một danh sách điều kiện con | <code>&lt;and&gt;...&lt;/and&gt;</code> |
| <code>or:</code> và một danh sách điều kiện con | <code>&lt;or&gt;...&lt;/or&gt;</code> |
| <code>not:</code> chứa điều kiện con | <code>&lt;not&gt;...&lt;/not&gt;</code> |
| <code>- onFail: HALT</code> | <code>onFail="HALT"</code> trên <code>&lt;preConditions&gt;</code> |

Ở cả hai định dạng, **cấu trúc cây** quyết định ý nghĩa; tên file hoặc thứ tự trình bày không thay thế được nhóm logic. XML thật phải khớp schema XSD phù hợp với phiên bản Liquibase đang dùng; YAML phải được parser của cùng phiên bản chấp nhận.

## 10. Failure khác Error: onFail và onError

Một precondition có ít nhất ba kết quả vận hành đáng phân biệt:

1. **Đúng (pass):** nhóm điều kiện đủ điều kiện, Liquibase có thể tiếp tục.
2. **Sai (fail):** phép kiểm tra được đánh giá bình thường nhưng kết quả không đạt. Ví dụ <code>tableExists</code> trả về không có bảng.
3. **Lỗi (error):** không thể hoàn thành việc đánh giá. Ví dụ kết nối mất, thiếu quyền đọc metadata, hoặc truy vấn trong <code>sqlCheck</code> gặp lỗi cú pháp.

Hai thuộc tính:

- <code>onFail</code> xử lý **fail**.
- <code>onError</code> xử lý **error**.

Không được dùng <code>NOT</code> như một cách thay thế cho <code>onError</code>. Một lỗi truy cập metadata không chứng minh đối tượng không tồn tại.

### 10.1. Các hành vi phổ biến

| Hành vi | Mục đích | Lưu ý |
|---|---|---|
| <code>HALT</code> | Dừng migration khi điều kiện không đạt | Thường phù hợp với thay đổi có nguy cơ sai schema hoặc hỏng dữ liệu |
| <code>WARN</code> | Phát cảnh báo và vẫn tiếp tục theo quy tắc của công cụ | Không an toàn nếu condition là điều kiện bắt buộc để change chạy đúng |
| <code>CONTINUE</code> | Bỏ qua changeset trong lần xử lý hiện tại | Chỉ áp dụng ở phạm vi được Liquibase hỗ trợ, thường là changeset-level |
| <code>MARK_RAN</code> | Ghi nhận changeset như đã xử lý mà không chạy các change của nó | Cần xác minh schema thực tế đã tương đương với kết quả mong muốn |

**Không dùng MARK_RAN để giấu lỗi hoặc bỏ qua một điều kiện quan trọng.** Nếu bảng có tên đúng nhưng cấu trúc không đúng, việc đánh dấu changeset đã chạy có thể khiến các migration sau phụ thuộc vào một trạng thái không tồn tại.

Ở mức changelog, các tùy chọn xử lý không nhất thiết hỗ trợ toàn bộ các lựa chọn giống mức changeset. Các lựa chọn <code>CONTINUE</code> và <code>MARK_RAN</code> chỉ nên dùng khi tài liệu phiên bản xác nhận hợp lệ tại phạm vi đó.

### 10.2. Chọn onFail như một quyết định nghiệp vụ

Giả sử changeset phải thêm ràng buộc <code>NOT NULL</code> chỉ khi mọi bản ghi đều có giá trị. Nếu precondition phát hiện còn bản ghi NULL, đây là trạng thái dữ liệu chưa đáp ứng yêu cầu. Trong tình huống này:

- <code>HALT</code> giúp chặn triển khai cho đến khi backfill hoàn tất.
- <code>WARN</code> có thể khiến câu lệnh DDL chạy tiếp và thất bại, hoặc tác động dữ liệu khác dự kiến.
- <code>MARK_RAN</code> có thể tạo lịch sử “đã triển khai” dù ràng buộc chưa được áp dụng.

Chiến lược phù hợp thường là HALT, khắc phục dữ liệu bằng quy trình được kiểm soát, rồi chạy lại theo lịch sử đúng. Cần đặt precondition sao cho nó kiểm tra **đúng trạng thái mà SQL phía sau yêu cầu**.

## 11. Kết hợp với sqlCheck để kiểm tra dữ liệu

Không phải điều kiện nào cũng có precondition chuyên dụng. <code>sqlCheck</code> cho phép so sánh kết quả một truy vấn SQL vô hướng với giá trị mong đợi.

Ví dụ muốn đảm bảo **không còn khách hàng có email NULL** trước khi thêm ràng buộc:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 006-customer-email-not-null
      author: db-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - and:
            - tableExists:
                tableName: customer
            - columnExists:
                tableName: customer
                columnName: email
            - sqlCheck:
                expectedResult: "0"
                sql: SELECT COUNT(*) FROM customer WHERE email IS NULL
      changes:
        - addNotNullConstraint:
            tableName: customer
            columnName: email
            columnDataType: varchar(320)
~~~

Điều kiện trên được hiểu là:

~~~text
tableExists(customer)
AND columnExists(customer.email)
AND (COUNT(customer.email IS NULL) = 0)
~~~

Nếu COUNT bằng 0, dữ liệu đáp ứng giả định trước khi thêm <code>NOT NULL</code>. Nếu COUNT lớn hơn 0, <code>sqlCheck</code> sai và <code>HALT</code> ngăn change được thực thi. Nếu câu SQL không thể chạy, <code>onError: HALT</code> ngăn tiếp tục.

**Những giới hạn cần biết:**

- <code>sqlCheck</code> thường yêu cầu một kết quả đơn để đối chiếu. Viết câu truy vấn trả nhiều cột hoặc nhiều dòng có thể khiến việc đánh giá thất bại.
- Giá trị <code>expectedResult</code> cần phù hợp với chuỗi kết quả mà driver và Liquibase trả về; với COUNT có thể so với chuỗi <code>"0"</code>.
- SQL có thể phụ thuộc DBMS, schema mặc định và quyền của tài khoản kết nối.
- COUNT trên bảng lớn có thể tốn thời gian/tài nguyên; phải đánh giá chi phí.
- Giữa thời điểm check và lúc DDL chạy, một tiến trình khác có thể thay đổi dữ liệu. Precondition không phải cơ chế khóa nghiệp vụ hay bảo đảm tính nguyên tử cho toàn bộ chuỗi kiểm tra–thay đổi.

Nếu ứng dụng vẫn ghi dữ liệu NULL trong khi migration chạy, cần phối hợp phát hành ứng dụng, quy tắc ghi dữ liệu, backfill và transaction phù hợp; không chỉ thêm một sqlCheck là đủ.

### 11.1. Tránh hai sai lầm với OR và sqlCheck

Biểu thức:

~~~text
tableExists(customer) OR (COUNT(email IS NULL) = 0)
~~~

không bảo vệ được <code>addNotNullConstraint</code>: chỉ cần bảng tồn tại là OR đúng, bất kể còn bao nhiêu bản ghi NULL. Phải là <code>tableExists(customer) AND columnExists(email) AND (COUNT(...) = 0)</code>.

Tương tự, <code>NOT sqlCheck(expectedResult=0, ...)</code> sẽ đảo nghĩa: nó chấp nhận trường hợp còn bản ghi NULL. Phải viết rõ điều kiện mục tiêu bằng lời trước khi phủ định một sqlCheck.

## 12. Thứ tự đánh giá, short-circuit và chi phí kiểm tra

Những nhóm logic <code>AND</code> và <code>OR</code> của Liquibase được thiết kế theo cách đánh giá điều kiện con phù hợp với logic Boolean; trong các triển khai thông dụng, AND có thể dừng khi gặp kết quả sai và OR có thể dừng khi gặp kết quả đúng (short-circuit).

Tuy nhiên, **không thiết kế migration dựa trên việc mọi precondition đều phải chạy**, cũng không dựa vào thứ tự chạy để tạo tác dụng phụ. Một precondition nên là phép kiểm tra chỉ đọc. Không viết SQL làm thay đổi dữ liệu trong <code>sqlCheck</code>.

Một quy tắc sắp xếp hữu ích:

1. Kiểm tra nhẹ, rộng trước, chẳng hạn <code>dbms</code>.
2. Kiểm tra tồn tại bảng/cột trước khi viết sqlCheck phụ thuộc vào các đối tượng đó.
3. Đặt các truy vấn metadata hoặc COUNT tốn kém sau các điều kiện có thể loại trừ sớm.
4. Dùng <code>AND</code>/<code>OR</code> để diễn đạt **đúng logic nghiệp vụ**, không đổi logic chỉ vì tối ưu hiệu năng.

Ví dụ, nếu <code>sqlCheck</code> đọc bảng chưa tồn tại, nó có thể phát lỗi thay vì trả false. Đặt <code>tableExists</code> trước trong cùng nhóm AND giúp ý định rõ ràng và có thể tránh một truy vấn không cần thiết. Dù vậy, nếu việc không tồn tại bảng phải làm migration dừng, hãy giữ <code>onFail/onError</code> phù hợp thay vì dựa hoàn toàn vào short-circuit.

## 13. Preconditions không thay thế tính nhất quán của các môi trường

Giả sử staging có bảng <code>orders</code> với cột <code>legacy_status</code>, còn production có <code>status_code</code>. Một biểu thức OR có thể chấp nhận cả hai, nhưng nếu changeset ngay sau đó chỉ cập nhật <code>status_code</code>, staging vẫn thất bại.

Để dùng Liquibase an toàn trong nhiều môi trường:

- Xác định schema đích và tên đối tượng được kiểm tra bằng cấu hình thực tế; tránh precondition nhìn sang schema khác.
- Dùng changeset có điều kiện DBMS/context/label khi cần tách logic rõ ràng, đồng thời kiểm chứng bộ lọc hiệu lực.
- Không biến OR thành cơ chế hợp thức hóa nhiều trạng thái schema không tương thích.
- Trên cơ sở dữ liệu có dữ liệu thật, kiểm tra trạng thái trước và sau migration, không chỉ kiểm tra lệnh không trả lỗi.
- Dùng chính changelog đã được review trong Spring Boot hoặc job CI/CD, tránh hai nơi chạy hai phiên bản khác nhau.

Khi ứng dụng được deploy cuốn chiếu, precondition đạt không chứng minh các instance cũ đã tương thích với schema mới. Phải thiết kế giai đoạn mở rộng, chuyển dữ liệu và thu hẹp (expand–contract) độc lập với điều kiện chạy migration.

### 13.1. Hạn chế khi chỉ dựa vào update-sql

Các lệnh <code>validate</code>, <code>status</code> và sinh SQL trước bằng <code>update-sql</code> giúp review changelog, pending changesets và SQL dự kiến. Tuy nhiên:

- <code>validate</code> không chứng minh tất cả điều kiện SQL/data sẽ đạt trên production.
- <code>status</code> dựa vào lịch sử triển khai và danh sách changeset, không phải thử thực thi toàn bộ migration.
- Khi sinh SQL offline hoặc dùng luồng <code>update-sql</code>, hành vi đánh giá precondition có thể phụ thuộc cấu hình như <code>onSqlOutput</code>, trạng thái kết nối và phiên bản Liquibase.

Do đó, một bản SQL preview không đủ để khẳng định mọi precondition đều đã được kiểm chứng trên database đích. Muốn bảo đảm, cần chạy kiểm thử với cấu hình và DBMS thực tế trên môi trường an toàn, đối chiếu kết quả khi chuẩn bị triển khai.

## 14. Lỗi phổ biến khi kết hợp AND, OR, NOT

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng OR trong khi mọi điều kiện đều bắt buộc | Một trạng thái thiếu điều kiện vẫn được phép đi qua | Viết biểu thức bằng lời, chọn AND và lập bảng tình huống |
| Viết <code>NOT (A AND B)</code> thay cho <code>NOT (A OR B)</code> | Có thể cho phép một đối tượng không mong muốn đang tồn tại | Áp dụng quy tắc De Morgan, kiểm thử đủ bốn trường hợp A/B |
| Đặt <code>not</code> sai cấp trong YAML | Đảo nghĩa toàn bộ nhóm thay vì một điều kiện con | Review cấu trúc cây và thụt lề; dùng XML khi cần nhìn cấu trúc rõ |
| Nhầm fail và error | Thiếu quyền metadata được hiểu sai là đối tượng không tồn tại | Xử lý riêng <code>onFail</code> và <code>onError</code> |
| Dùng <code>MARK_RAN</code> khi một phần schema đã tồn tại | Lịch sử có thể ghi nhận changeset mà kết quả mong muốn chưa đầy đủ | HALT, kiểm tra schema thực và chọn hướng sửa có kiểm chứng |
| Precondition kiểm tra bảng ở schema A, change sửa bảng ở schema B | Migration vẫn chạy vào sai đích | Dùng schemaName nhất quán, kiểm tra default schema và SQL preview |
| sqlCheck trả nhiều dòng/cột | Lỗi đánh giá precondition hoặc kết quả không như mong đợi | Viết truy vấn một giá trị và thử trên DBMS đích |
| OR chấp nhận DBMS A/B nhưng SQL chỉ hỗ trợ A | Lỗi cú pháp hoặc behavior trên DBMS B | Thử cả hai DBMS, tách changeset nếu cần |
| Chỉ kiểm tra “cột đã tồn tại” để cho MARK_RAN | Cột có thể sai kiểu hoặc thiếu ràng buộc | Xác minh trạng thái schema tương đương, không bỏ qua thay đổi cần thiết |
| Coi precondition là cách chống race condition | Dữ liệu có thể đổi sau thời điểm check | Thiết kế transaction, khóa, quy trình deploy và ứng dụng phù hợp |
| Chỉ thử trường hợp happy path | Không phát hiện lỗi nhóm NOT/OR khi thiếu bảng/cột | Kiểm thử cả trường hợp pass, fail và error |

## 15. Bài thực hành thiết kế và kiểm chứng

### Bài A: Thêm cột khi đủ điều kiện

Yêu cầu: chỉ thêm <code>customer.loyalty_tier</code> nếu bảng đã có và cột chưa có.

Biểu thức:

~~~text
tableExists(customer) AND NOT columnExists(customer.loyalty_tier)
~~~

Kiểm thử tối thiểu:

| Bảng customer | Cột loyalty_tier | Kỳ vọng |
|---|---|---|
| Có | Chưa có | PASS |
| Có | Đã có | FAIL |
| Không | Không | FAIL |
| Không đọc được metadata | Chưa xác định | ERROR |

### Bài B: Giới hạn DBMS hỗ trợ

Yêu cầu: thay đổi chạy trên PostgreSQL hoặc MySQL, và phải có bảng <code>payment</code>.

Biểu thức:

~~~text
(dbms(postgresql) OR dbms(mysql)) AND tableExists(payment)
~~~

Nếu viết <code>dbms(postgresql) OR (dbms(mysql) AND tableExists(payment))</code>, PostgreSQL có thể được phép đi qua ngay cả khi không có bảng <code>payment</code>. Đây là ví dụ điển hình về **OR ở sai cấp**.

### Bài C: Không cho phép bất kỳ bảng tạm nào tồn tại

Yêu cầu: không có <code>tmp_invoice</code> và không có <code>tmp_payment</code>.

Hai biểu thức tương đương:

~~~text
NOT (tableExists(tmp_invoice) OR tableExists(tmp_payment))

NOT tableExists(tmp_invoice) AND NOT tableExists(tmp_payment)
~~~

Chỉ cần một bảng tồn tại là phải FAIL. Hãy thử cả bốn tổ hợp tồn tại/không tồn tại của hai bảng.

### Bài D: Kiểm tra dữ liệu trước NOT NULL

Yêu cầu: chỉ thêm NOT NULL cho <code>account.email</code> khi bảng/cột đã có và số bản ghi email NULL bằng 0.

Biểu thức:

~~~text
tableExists(account)
AND columnExists(account.email)
AND (SELECT COUNT(*) FROM account WHERE email IS NULL) = 0
~~~

Ngoài bài kiểm tra logic, phải xác định dữ liệu có thể thay đổi trong khi triển khai không, và bản SQL có phù hợp DBMS đích không.

### 15.1. Cách tự kiểm chứng bài thực hành

Trong database phục vụ học tập, không ảnh hưởng hệ thống thật:

1. Tạo schema ở trạng thái mà biểu thức dự kiến PASS; chạy Liquibase và kiểm tra lịch sử.
2. Chuẩn bị trạng thái FAIL (ví dụ thêm trước một cột hoặc thiếu bảng); xác nhận hành vi <code>onFail</code>.
3. Thử một tình huống ERROR an toàn (ví dụ quyền truy vấn metadata bị hạn chế hoặc SQL không hợp lệ trong môi trường thử); xác nhận <code>onError</code>.
4. Đối chiếu schema thực tế với thay đổi kỳ vọng sau mỗi lần chạy.
5. Không sửa <code>DATABASECHANGELOG</code> bằng tay để tái diễn thử nghiệm; dùng database thử mới hoặc quy trình reset/rollback có kiểm soát.

## 16. Checklist trước khi phát hành changeset có nhóm logic

- [ ] Diễn đạt được điều kiện dưới dạng câu ngắn rõ nghĩa và biểu thức Boolean.
- [ ] AND được dùng cho tất cả điều kiện bắt buộc; OR chỉ chấp nhận các trạng thái thực sự tương đương; NOT phủ định đúng đối tượng.
- [ ] Cấu trúc lồng nhau và thụt lề YAML hoặc thẻ XML thể hiện đúng nhóm mong muốn.
- [ ] Precondition kiểm tra đúng schema/catalog, tableName và columnName mà change phía sau sẽ sử dụng.
- [ ] Có chiến lược rõ ràng cho FAIL và ERROR, nhất là khi thiếu quyền hoặc kết nối.
- [ ] Không dùng MARK_RAN/CONTINUE để che dấu sai lệch schema chưa được giải thích.
- [ ] Các truy vấn sqlCheck không làm thay đổi dữ liệu, trả một kết quả dự đoán được và có chi phí chấp nhận được.
- [ ] Những trạng thái PASS, FAIL và ERROR quan trọng đã được thử nghiệm với đúng DBMS/phiên bản.
- [ ] Changelog, context/label, phiên bản Liquibase và cấu hình kết nối được giữ nhất quán từ kiểm thử đến deploy.
- [ ] Rollback/forward fix, khả năng tương thích ứng dụng và xác minh sau triển khai đã có kế hoạch.

## 17. Ghi nhớ

Trong Liquibase, **AND** yêu cầu mọi giả định cùng đúng, **OR** cho phép một trong các trạng thái hợp lệ và **NOT** yêu cầu một điều kiện không được đúng. Các toán tử có thể lồng nhau để diễn đạt điều kiện phức hợp như <code>(PostgreSQL OR MySQL) AND tableExists(customer) AND NOT columnExists(customer.external_ref)</code>. Điều quyết định tính chính xác là **cấu trúc cây logic**, không phải số lượng precondition được thêm vào.

Precondition giúp phát hiện môi trường không đúng giả định và ngăn migration không phù hợp, nhưng không thay thế kiểm thử dữ liệu, quản lý quyền, chiến lược transaction, tương thích ứng dụng hay rollback. Hãy kết hợp biểu thức đúng với <code>onFail/onError</code> rõ ràng, SQL preview, kiểm thử từng trường hợp và kiểm tra lịch sử triển khai để thay đổi schema có thể dự đoán, lặp lại và truy vết được.
