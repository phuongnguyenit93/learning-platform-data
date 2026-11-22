# Tạo khóa ngoại và kiểm soát dữ liệu vi phạm trong Liquibase

## 1. Vấn đề: thêm ràng buộc vào cơ sở dữ liệu đang có dữ liệu

**Khóa ngoại (foreign key, FK)** bảo đảm một giá trị tham chiếu ở bảng con phù hợp với khóa được tham chiếu ở bảng cha, theo quy tắc mà DBMS áp dụng. Trong hệ thống đơn hàng, <code>customer_order.customer_id</code> tham chiếu <code>customer.id</code>: một đơn hàng gắn với khách hàng phải chỉ tới khách hàng có thật.

Khi hệ thống còn mới và các bảng trống, thêm FK có thể tương đối đơn giản. Nhưng trên cơ sở dữ liệu đã vận hành, có thể tồn tại:

- Đơn hàng mang <code>customer_id</code> không còn tồn tại trong bảng khách hàng (*orphan record*).
- Giá trị NULL dù nghiệp vụ yêu cầu bắt buộc có khách hàng.
- Cột cha chưa có PRIMARY KEY/UNIQUE phù hợp hoặc kiểu dữ liệu của hai cột không tương thích.
- Dữ liệu khác nhau giữa dev, staging và production vì các lần nhập liệu cũ.
- Ứng dụng đang ghi dữ liệu trong lúc thay đổi cấu trúc, làm kết quả kiểm tra trước migration nhanh chóng hết hiệu lực.

**Thêm FK không tự động sửa các bản ghi vi phạm.** Nếu DBMS phải kiểm tra dữ liệu hiện hữu lúc tạo ràng buộc, migration có thể thất bại và để lại một đợt triển khai dở dang tùy khả năng transaction của DBMS. Vì thế, nhiệm vụ không chỉ là viết <code>addForeignKeyConstraint</code>, mà còn là **phát hiện, phân loại, xử lý và ngăn dữ liệu vi phạm quay trở lại**.

Bài học nằm trong chương **Khóa và chỉ mục** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Module giúp nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Nội dung tập trung vào việc thêm FK an toàn vào dữ liệu thực, không coi một changeset chạy thành công là bằng chứng đầy đủ về tính đúng đắn nghiệp vụ.

Sau bài này, người học cần biết:

1. Thiết kế FK dựa trên đúng bảng, cột, khóa đích và hành vi xóa/cập nhật.
2. Dùng Liquibase để tạo và gỡ khóa ngoại theo changeset có lịch sử rõ ràng.
3. Viết truy vấn phát hiện dữ liệu mồ côi, phân biệt vi phạm FK với vi phạm NOT NULL.
4. Chọn phương án sửa dữ liệu có thể kiểm toán, thay vì xóa/đổi dữ liệu tùy tiện.
5. Sử dụng precondition, SQL xem trước, thử nghiệm và rollout nhiều bước để giảm rủi ro production.

## 2. Mô hình dữ liệu và nguyên tắc tham chiếu

Giả sử có hai bảng:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL
);

CREATE TABLE customer_order (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT,
    order_total DECIMAL(15, 2) NOT NULL
);
~~~

Chưa có FK, cơ sở dữ liệu có thể chứa những hàng như:

| customer_order.id | customer_id | Ý nghĩa |
|---|---|---|
| 101 | 10 | Hợp lệ nếu <code>customer.id = 10</code> tồn tại |
| 102 | 999 | Vi phạm nếu không có khách hàng 999 |
| 103 | NULL | Không vi phạm FK một cột thông thường, nhưng có thể vi phạm quy tắc nghiệp vụ |

Khi tạo FK từ <code>customer_order.customer_id</code> tới <code>customer.id</code>, DBMS bảo vệ quan hệ tham chiếu cho các thao tác DML thuộc phạm vi ràng buộc. FK không đồng nghĩa với việc mọi đơn hàng bắt buộc có khách hàng, vì điều kiện NULL được quyết định riêng bởi ràng buộc <code>NOT NULL</code> trên cột con.

### 2.1. Điều kiện để một FK hợp lệ

Trước khi viết migration, cần xác minh:

| Điều kiện | Câu hỏi kiểm tra |
|---|---|
| Bảng/cột tồn tại | Bảng con, cột con, bảng cha và cột được tham chiếu có đúng schema không? |
| Khóa được tham chiếu | Cột hoặc tập cột cha có khóa chính/unique key phù hợp theo yêu cầu DBMS không? |
| Kiểu dữ liệu | Kiểu, kích thước, signed/unsigned, collation hoặc các đặc tính so sánh có tương thích không? |
| Số cột và thứ tự | FK ghép có cùng số cột và thứ tự tương ứng với khóa đích không? |
| Dữ liệu hiện tại | Có bản ghi con tham chiếu tới giá trị không tồn tại không? |
| NULL và nghiệp vụ | NULL có hợp lệ? Nếu không, cần bổ sung NOT NULL bằng thay đổi riêng khi dữ liệu đã sẵn sàng |
| Quyền | Tài khoản migration được phép tạo constraint trên bảng/schema liên quan không? |
| DBMS | Loại FK, hành vi cập nhật/xóa, cách xác thực và transaction có được hỗ trợ không? |

Trong phần lớn thiết kế quan hệ, khóa được tham chiếu phải là PRIMARY KEY hoặc UNIQUE phù hợp. Không dựa vào các ngoại lệ hoặc hành vi mở rộng của một DBMS để triển khai cùng changelog trên nhiều hệ quản trị.

### 2.2. FK bảo vệ điều gì và không bảo vệ điều gì?

FK bảo vệ sự tồn tại của giá trị đích và các quy tắc liên quan khi xóa/cập nhật theo DBMS. FK **không** kiểm tra:

- Khách hàng còn hoạt động hay đã khóa tài khoản.
- Đơn hàng có thuộc đúng tổ chức/tenant của khách hàng không, nếu FK chỉ tham chiếu mỗi <code>customer_id</code>.
- Giá trị <code>customer_id</code> có bắt buộc khác NULL hay không.
- Các bản ghi cũ đã được làm sạch về mặt ngữ nghĩa, chứ không chỉ tham chiếu hợp lệ.

Đây là lý do cần kết hợp FK với thiết kế khóa, NOT NULL, unique constraints, check constraints và quy tắc nghiệp vụ phù hợp.

## 3. Tạo khóa ngoại bằng addForeignKeyConstraint

Liquibase cung cấp change type <code>addForeignKeyConstraint</code> để mô tả FK ở mức khái niệm, cho phép công cụ sinh SQL tương ứng với DBMS đích.

Ví dụ YAML:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-add-order-customer-fk
      author: db-team
      changes:
        - addForeignKeyConstraint:
            baseTableName: customer_order
            baseColumnNames: customer_id
            referencedTableName: customer
            referencedColumnNames: id
            constraintName: fk_customer_order_customer
      rollback:
        - dropForeignKeyConstraint:
            baseTableName: customer_order
            constraintName: fk_customer_order_customer
~~~

Chú ý vai trò của các thuộc tính:

| Thuộc tính | Ý nghĩa |
|---|---|
| <code>baseTableName</code> | Tên bảng con đang chứa cột tham chiếu |
| <code>baseColumnNames</code> | Tên cột hoặc danh sách cột con |
| <code>referencedTableName</code> | Tên bảng cha được tham chiếu |
| <code>referencedColumnNames</code> | Tên cột hoặc danh sách cột thuộc khóa đích |
| <code>constraintName</code> | Tên FK, nên rõ nghĩa và ổn định giữa các lần triển khai |
| <code>baseTableSchemaName</code> | Schema của bảng con khi cần chỉ rõ |
| <code>referencedTableSchemaName</code> | Schema của bảng cha khi cần chỉ rõ |
| <code>onDelete</code>, <code>onUpdate</code> | Hành vi tham chiếu khi khóa cha bị xóa hoặc cập nhật, nếu DBMS hỗ trợ |
| <code>deferrable</code>, <code>initiallyDeferred</code> | Khả năng hoãn kiểm tra constraint trên DBMS hỗ trợ |
| <code>validate</code> | Tùy chọn kiểm tra dữ liệu hiện hữu, có ý nghĩa và cách hỗ trợ phụ thuộc DBMS/phiên bản |

**Không nhầm chiều tham chiếu:** <code>base*</code> luôn là phía chứa khóa ngoại; <code>referenced*</code> là phía có khóa được tham chiếu. Đảo chiều sẽ thay đổi quy tắc toàn vẹn hoặc làm DDL thất bại.

Trong ví dụ, <code>rollback</code> chỉ gỡ constraint. Nó **không xóa** các bản ghi con/cha, không hoàn nguyên các lần sửa dữ liệu trước đó và không bảo đảm ứng dụng quay lại trạng thái trước phát hành.

### 3.1. Ví dụ XML tương đương

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://www.liquibase.org/xml/ns/dbchangelog
                        https://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-latest.xsd">

    <changeSet id="001-add-order-customer-fk" author="db-team">
        <addForeignKeyConstraint
            baseTableName="customer_order"
            baseColumnNames="customer_id"
            referencedTableName="customer"
            referencedColumnNames="id"
            constraintName="fk_customer_order_customer"/>

        <rollback>
            <dropForeignKeyConstraint
                baseTableName="customer_order"
                constraintName="fk_customer_order_customer"/>
        </rollback>
    </changeSet>
</databaseChangeLog>
~~~

Cần dùng schema XSD tương thích với phiên bản Liquibase của dự án. Hai ví dụ YAML/XML biểu đạt cùng ý tưởng; không đưa cả hai changeset cùng định danh vào cùng một changelog chạy thực tế.

### 3.2. Tên khóa và schema phải ổn định

Nên đặt tên FK theo convention như <code>fk_[bang_con]_[bang_cha]</code> hoặc tên đủ ngắn, không trùng trong phạm vi quy định bởi DBMS. Tên rõ ràng giúp đọc log lỗi, tìm FK trong catalog, viết rollback và đánh giá ảnh hưởng.

Khi bảng nằm trong schema khác nhau:

~~~yaml
changes:
  - addForeignKeyConstraint:
      baseTableSchemaName: sales
      baseTableName: customer_order
      baseColumnNames: customer_id
      referencedTableSchemaName: crm
      referencedTableName: customer
      referencedColumnNames: id
      constraintName: fk_order_crm_customer
~~~

Đây là mảnh ví dụ đặt trong <code>changeSet</code>, không phải changelog hoàn chỉnh. FK xuyên schema chỉ có thể dùng nếu DBMS, quyền và kiến trúc triển khai cho phép. Khi làm sạch dữ liệu, truy vấn cũng phải chỉ rõ cùng các schema để tránh kiểm tra nhầm đối tượng.

## 4. Phát hiện bản ghi con mồ côi trước khi thêm FK

Phần khó nhất trong migration trên hệ thống đang hoạt động thường là **dữ liệu lịch sử**. Trước khi thêm ràng buộc, hãy kiểm tra tất cả giá trị khóa ngoại khác NULL hiện có cha tương ứng hay chưa.

### 4.1. Liệt kê bản ghi mồ côi

Ví dụ SQL có thể áp dụng theo cấu trúc phổ biến của nhiều RDBMS:

~~~sql
SELECT
    o.id AS order_id,
    o.customer_id
FROM customer_order o
LEFT JOIN customer c
    ON c.id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.id IS NULL
ORDER BY o.id;
~~~

Truy vấn tìm đơn hàng có <code>customer_id</code> nhưng không có khách hàng mang ID tương ứng. Điều kiện <code>o.customer_id IS NOT NULL</code> là chủ ý: ở FK đơn cột thông thường, NULL không phải là vi phạm tham chiếu.

Trong một bảng lớn, không nên mặc định chạy truy vấn lấy mọi dòng trực tiếp trong giờ cao điểm. Có thể dùng thống kê, phân trang hoặc xuất báo cáo theo batch; cách tối ưu truy vấn phụ thuộc DBMS, chỉ mục và dữ liệu thực tế.

### 4.2. Đếm số bản ghi vi phạm

~~~sql
SELECT COUNT(*) AS orphan_count
FROM customer_order o
LEFT JOIN customer c
    ON c.id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.id IS NULL;
~~~

Nếu kết quả bằng 0, không phát hiện vi phạm kiểu “khóa con khác NULL không có cha” tại **thời điểm truy vấn**. Đây là một tín hiệu cần thiết, nhưng chưa đủ để kết luận rằng constraint sẽ được tạo thành công: có thể còn lỗi kiểu dữ liệu, quyền, khóa đích, tên schema hoặc thao tác ghi đồng thời.

Ngoài ra cần phân biệt:

~~~sql
SELECT COUNT(*) AS missing_customer_count
FROM customer_order
WHERE customer_id IS NULL;
~~~

Truy vấn thứ hai kiểm tra NULL theo quy tắc nghiệp vụ, **không phải truy vấn phát hiện vi phạm FK**. Nếu yêu cầu mọi đơn hàng phải có khách hàng, hãy xử lý NULL và bổ sung <code>NOT NULL</code> bằng một thay đổi có kế hoạch.

### 4.3. Một ví dụ phân loại dữ liệu

Giả sử bảng <code>customer</code> có ID 10 và 20; bảng <code>customer_order</code> chứa:

| order_id | customer_id | Kết quả kiểm tra |
|---|---|---|
| 501 | 10 | Hợp lệ |
| 502 | 20 | Hợp lệ |
| 503 | 999 | Mồ côi |
| 504 | NULL | Không vi phạm FK đơn cột, cần đánh giá nghiệp vụ |
| 505 | 10 | Hợp lệ |

Trước khi tạo FK, cần có quyết định xử lý bản ghi 503. Không nên sửa dữ liệu tùy tiện thành <code>customer_id = 10</code> chỉ vì ID 10 tồn tại: như vậy có thể biến vi phạm kỹ thuật thành thông tin nghiệp vụ sai.

## 5. Những chiến lược xử lý dữ liệu vi phạm

Không có một câu SQL “làm sạch” áp dụng đúng cho mọi hệ thống. Lựa chọn phụ thuộc nguồn gốc sai lệch và yêu cầu lưu vết.

| Chiến lược | Khi nào phù hợp? | Điều phải xác minh |
|---|---|---|
| **Khôi phục hoặc bổ sung bản ghi cha** | Khách hàng có thật nhưng dữ liệu master bị thiếu do chuyển đổi | Có nguồn dữ liệu đáng tin, không tạo bản ghi giả để lấp FK |
| **Đối chiếu lại khóa tham chiếu** | <code>customer_id</code> bị mapping sai trong quá trình import | Mapping có bằng chứng, tránh gán nhầm khách hàng |
| **Chuyển khóa con sang NULL** | Quan hệ được phép tùy chọn và không thể xác định cha hợp lệ | Nghiệp vụ đồng ý, cột nullable, ứng dụng xử lý NULL |
| **Lưu trữ rồi xóa bản ghi con** | Dữ liệu không còn giá trị, được phép xóa theo chính sách | Quy trình phê duyệt, lưu trữ, audit, khả năng phục hồi |
| **Tách dữ liệu bất thường để xử lý thủ công** | Quan hệ quan trọng nhưng chưa đủ bằng chứng sửa | Có báo cáo, owner, thời hạn và cơ chế chặn triển khai nếu cần |
| **Rollout nhiều giai đoạn** | Bảng lớn hoặc không thể dừng ghi lâu | Thiết kế hạn chế dữ liệu vi phạm mới và xác thực sau backfill |

### 5.1. Ví dụ cập nhật có kiểm soát

Giả sử bảng mapping được duyệt chỉ ra khách hàng 999 thực chất là 20. Khi đã có bằng chứng nghiệp vụ và bản ghi tương ứng, một thay đổi dữ liệu có thể cập nhật riêng:

~~~sql
-- Minh họa trên môi trường kiểm thử; cần giao dịch, backup và log audit phù hợp.
UPDATE customer_order
SET customer_id = 20
WHERE customer_id = 999;
~~~

Câu lệnh trên **không phải quy tắc làm sạch phổ quát**. Trong production, nên giới hạn tập hàng được sửa, kiểm tra số lượng bản ghi trước/sau, thiết lập điều kiện có thể chạy lại an toàn và ghi nhận nguồn dữ liệu được dùng để đối chiếu.

### 5.2. Không “sửa” dữ liệu bằng cách tắt constraint

Một số DBMS cho phép tạm thời vô hiệu hóa kiểm tra khóa ngoại hoặc thêm constraint ở trạng thái chưa xác thực. Đây có thể là công cụ chuyển đổi dữ liệu có kiểm soát, nhưng **không phải cách hoàn thành việc đảm bảo toàn vẹn tham chiếu**.

Nếu ràng buộc vẫn không được xác thực đối với dữ liệu cũ, hệ thống có thể chứa orphan records sau khi deployment báo thành công. Bản báo cáo phải phân biệt rõ:

- FK đã được khai báo và bật.
- FK có kiểm tra dữ liệu mới hay không.
- Dữ liệu lịch sử đã được xác thực hoàn toàn hay chưa.

Không ghi trạng thái “dữ liệu sạch” nếu chỉ mới thêm một constraint chưa validate.

## 6. Dùng precondition để chặn migration khi còn dữ liệu mồ côi

Liquibase hỗ trợ <code>preConditions</code> trên changeset. Ta có thể dùng <code>sqlCheck</code> để kiểm tra số orphan records trước khi chạy <code>addForeignKeyConstraint</code>.

Ví dụ YAML hoàn chỉnh:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 002-validate-and-add-order-customer-fk
      author: db-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            tableName: customer_order
        - tableExists:
            tableName: customer
        - columnExists:
            tableName: customer_order
            columnName: customer_id
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*)
              FROM customer_order o
              LEFT JOIN customer c
                ON c.id = o.customer_id
              WHERE o.customer_id IS NOT NULL
                AND c.id IS NULL
      changes:
        - addForeignKeyConstraint:
            baseTableName: customer_order
            baseColumnNames: customer_id
            referencedTableName: customer
            referencedColumnNames: id
            constraintName: fk_customer_order_customer
      rollback:
        - dropForeignKeyConstraint:
            baseTableName: customer_order
            constraintName: fk_customer_order_customer
~~~

Giải thích:

1. <code>tableExists</code> xác nhận hai bảng có trong phạm vi schema đang xét.
2. <code>columnExists</code> xác nhận cột con.
3. <code>sqlCheck</code> kỳ vọng chuỗi kết quả <code>"0"</code>, nghĩa là tại lúc kiểm tra không còn orphan records.
4. <code>onFail: HALT</code> yêu cầu dừng nếu điều kiện kiểm tra không đạt.
5. <code>onError: HALT</code> yêu cầu dừng khi có lỗi đánh giá, chẳng hạn không đọc được dữ liệu hay truy vấn lỗi.
6. Chỉ sau đó mới đến thao tác tạo FK.

**Giới hạn quan trọng:** precondition trên đây không kiểm tra hết mọi điều kiện cần cho FK: chưa xác nhận unique/primary key của bảng cha, mức tương thích kiểu dữ liệu và quyền tạo constraint. Đồng thời, giữa lúc <code>sqlCheck</code> chạy và lúc DBMS áp dụng constraint có thể có giao dịch ứng dụng tạo thêm dữ liệu vi phạm. Vì vậy, không coi <code>sqlCheck</code> là cơ chế ngăn race condition.

Đối với hệ thống nhiều schema, cần dùng <code>schemaName</code> ở các precondition và tên schema tường minh trong SQL tương ứng, đồng thời đặt <code>baseTableSchemaName</code>/<code>referencedTableSchemaName</code> cùng đích ở change. Tránh tình huống precondition đọc schema A nhưng change sửa schema B.

### 6.1. Vì sao chọn HALT thay vì MARK_RAN?

<code>MARK_RAN</code> có thể ghi nhận changeset như đã xử lý mà không thực hiện thay đổi của nó ở phạm vi được hỗ trợ. Trong một FK migration, dùng MARK_RAN chỉ vì dữ liệu mồ côi còn tồn tại có thể khiến lịch sử Liquibase thể hiện như constraint đã được triển khai, trong khi database thực tế chưa có FK.

Nếu dữ liệu cần sửa trước, <code>HALT</code> là lựa chọn an toàn hơn: dừng pipeline, làm sạch dữ liệu theo quy trình được duyệt, kiểm tra lại, rồi triển khai. Không sửa trực tiếp <code>DATABASECHANGELOG</code> để vượt qua precondition.

## 7. Lựa chọn ON DELETE và ON UPDATE

Khóa ngoại không chỉ kiểm tra khi thêm/sửa bản ghi con; nó còn quyết định những gì xảy ra khi khóa được tham chiếu ở bảng cha bị xóa hoặc thay đổi.

| Hành vi tham chiếu | Ý nghĩa khái quát | Rủi ro cần cân nhắc |
|---|---|---|
| <code>NO ACTION</code> | Không cho phép thao tác vi phạm ràng buộc ở thời điểm DBMS kiểm tra | Có thể khác <code>RESTRICT</code> khi DBMS hỗ trợ ràng buộc deferrable |
| <code>RESTRICT</code> | Ngăn hành động thay đổi/xóa cha khi còn tham chiếu không cho phép | Không phải DBMS nào cũng dùng cùng cú pháp |
| <code>CASCADE</code> | Xóa/cập nhật bản ghi con liên quan khi cha bị xóa/cập nhật | Có thể gây xóa dây chuyền dữ liệu quan trọng |
| <code>SET NULL</code> | Chuyển giá trị FK ở con thành NULL | Chỉ phù hợp nếu cột và nghiệp vụ cho phép NULL |
| <code>SET DEFAULT</code> | Gán giá trị mặc định cho cột FK | Giá trị mặc định vẫn phải đáp ứng FK; mức hỗ trợ phụ thuộc DBMS |

Ví dụ, nếu một khách hàng bị xóa mà các đơn hàng cần giữ nguyên vì yêu cầu kế toán, <code>ON DELETE CASCADE</code> thường là lựa chọn nguy hiểm. Có thể dùng hành vi ngăn xóa hoặc áp dụng cơ chế soft delete ở tầng nghiệp vụ. Ngược lại, với bảng con chỉ là chi tiết phụ thuộc hoàn toàn vào bảng cha, CASCADE có thể phù hợp sau khi đánh giá.

Ví dụ cấu hình:

~~~yaml
changes:
  - addForeignKeyConstraint:
      baseTableName: customer_order
      baseColumnNames: customer_id
      referencedTableName: customer
      referencedColumnNames: id
      constraintName: fk_customer_order_customer
      onDelete: RESTRICT
~~~

Mảnh YAML này nằm bên trong một <code>changeSet</code>. Cần xác minh Liquibase và DBMS đích hỗ trợ giá trị đã chọn, đặc biệt khi có nhiều môi trường dùng hệ quản trị khác nhau. Nếu không quy định <code>onDelete</code>/<code>onUpdate</code>, cần biết hành vi mặc định của DBMS; không giả định mọi DBMS xử lý mặc định hoàn toàn giống nhau.

### 7.1. Deferrable không có nghĩa là bỏ kiểm tra

Một số DBMS (ví dụ PostgreSQL) hỗ trợ constraint có thể hoãn kiểm tra tới cuối transaction khi cấu hình phù hợp. Liquibase có các thuộc tính như <code>deferrable</code> và <code>initiallyDeferred</code>, nhưng **không phải DBMS nào cũng hỗ trợ**.

Hoãn kiểm tra có thể hữu ích cho một transaction cập nhật nhiều bảng theo thứ tự tạm thời vi phạm quan hệ, sau đó khôi phục tính hợp lệ trước commit. Nó **không** hợp thức hóa dữ liệu vi phạm vĩnh viễn và không thay cho việc làm sạch dữ liệu cũ.

## 8. Foreign key ghép nhiều cột và quy tắc NULL

Trong hệ thống multi-tenant, chỉ tham chiếu <code>customer_id</code> có thể chưa đủ để bảo đảm đơn hàng thuộc đúng tenant. Khi bảng cha có khóa unique phù hợp trên cặp <code>(tenant_id, id)</code>, có thể tạo FK ghép:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 003-add-tenant-aware-fk
      author: db-team
      changes:
        - addForeignKeyConstraint:
            baseTableName: customer_order
            baseColumnNames: tenant_id, customer_id
            referencedTableName: customer
            referencedColumnNames: tenant_id, id
            constraintName: fk_order_customer_same_tenant
      rollback:
        - dropForeignKeyConstraint:
            baseTableName: customer_order
            constraintName: fk_order_customer_same_tenant
~~~

Đây là mô tả change; nó giả định cả hai bảng có các cột tương ứng và bảng cha có khóa đích phù hợp. **Thứ tự cột rất quan trọng**: cột thứ nhất của bảng con khớp với cột thứ nhất của khóa đích, cột thứ hai khớp với cột thứ hai.

Với nhiều DBMS, FK ghép theo quy tắc mặc định tương đương <code>MATCH SIMPLE</code>: một số giá trị NULL ở phía con có thể khiến hàng không phải thỏa kiểm tra tham chiếu toàn bộ. Một số DBMS hỗ trợ <code>MATCH FULL</code> với quy tắc NULL khác, nhưng không nên giả định Liquibase/DBMS nào cũng hỗ trợ như nhau.

Do đó, nếu hai cột <code>tenant_id</code> và <code>customer_id</code> phải cùng có giá trị, cần kiểm soát NULL riêng và xây dựng truy vấn phát hiện dữ liệu vi phạm phù hợp với quy tắc NULL của DBMS.

### 8.1. Kiểm tra dữ liệu mồ côi cho khóa ghép

Giả sử cả hai cột con bắt buộc NOT NULL. Truy vấn kiểm tra:

~~~sql
SELECT
    o.id,
    o.tenant_id,
    o.customer_id
FROM customer_order o
LEFT JOIN customer c
  ON c.tenant_id = o.tenant_id
 AND c.id = o.customer_id
WHERE c.id IS NULL;
~~~

Nếu cột con cho phép NULL, cần tách quy tắc NULL thành kiểm tra riêng; truy vấn trên có thể liệt kê cả các hàng có NULL mà FK theo mặc định không coi là vi phạm. Đừng gộp kết quả truy vấn “không có cha” với định nghĩa vi phạm constraint nếu chưa xét đầy đủ ngữ nghĩa NULL.

## 9. Validate dữ liệu cũ và chiến lược triển khai theo giai đoạn

Trên bảng lớn, việc kiểm tra toàn bộ dữ liệu khi thêm constraint có thể tốn tài nguyên hoặc giữ khóa ở mức ảnh hưởng tới ứng dụng. DBMS có các chiến lược và mức hỗ trợ khác nhau.

### 9.1. Hai hướng triển khai

**Hướng A — dọn dữ liệu trước, thêm FK được xác thực ngay**

1. Kiểm kê số lượng bản ghi vi phạm.
2. Sửa lỗi dữ liệu theo quy trình nghiệp vụ.
3. Ngăn dữ liệu vi phạm mới qua logic ứng dụng hoặc quy trình ghi được kiểm soát.
4. Chạy precondition và tạo FK trong cửa sổ triển khai phù hợp.
5. Xác minh FK tồn tại, có trạng thái hợp lệ và ứng dụng hoạt động bình thường.

Hướng này đơn giản về trạng thái cuối nhưng có thể đòi hỏi kiểm tra trên bảng rất lớn trong lúc tạo constraint.

**Hướng B — bật bảo vệ dữ liệu mới, sau đó xác thực dữ liệu cũ**

Một số DBMS hỗ trợ thêm FK chưa xác thực toàn bộ dữ liệu lịch sử, trong khi vẫn áp dụng ràng buộc với thao tác dữ liệu mới. Sau đó nhóm dọn dữ liệu cũ và yêu cầu DBMS xác thực constraint.

Tùy chọn Liquibase <code>validate</code> trên <code>addForeignKeyConstraint</code> có **ngữ nghĩa và mức hỗ trợ phụ thuộc DBMS/phiên bản**. Không mặc định rằng <code>validate: false</code> sẽ sinh chính xác cú pháp tương đương <code>NOT VALID</code> trên mọi DBMS hoặc tất cả các công cụ tích hợp.

### 9.2. Ví dụ đặc thù PostgreSQL: NOT VALID và VALIDATE CONSTRAINT

PostgreSQL hỗ trợ quy trình tách giai đoạn ở mức SQL:

~~~sql
-- Giai đoạn 1: tạo FK nhưng chưa kiểm tra toàn bộ hàng cũ.
ALTER TABLE customer_order
ADD CONSTRAINT fk_customer_order_customer
FOREIGN KEY (customer_id)
REFERENCES customer (id)
NOT VALID;

-- Giai đoạn 2: sau khi xử lý dữ liệu vi phạm, xác thực hàng cũ.
ALTER TABLE customer_order
VALIDATE CONSTRAINT fk_customer_order_customer;
~~~

Đây là cú pháp PostgreSQL, **không phải SQL dùng chung cho MySQL, Oracle hoặc SQL Server**. Với FK <code>NOT VALID</code> ở PostgreSQL, constraint mới thường được áp dụng cho các thao tác ghi tiếp theo, còn việc xác thực toàn bộ dữ liệu cũ được trì hoãn. Quy trình này hữu ích cho bảng lớn, nhưng phải đo thời gian, khóa và chi phí thực tế của từng giai đoạn.

Nếu cần đưa thao tác DBMS-specific vào Liquibase, có thể dùng changeset SQL kèm điều kiện DBMS và rollback rõ ràng. Cần phân biệt:

- “Đã tạo FK nhưng chưa validate” là **trạng thái trung gian**, chưa phải hoàn tất mục tiêu dữ liệu.
- “Đã validate FK” mới chứng minh dữ liệu thuộc phạm vi kiểm tra đã được DBMS xác thực tại thời điểm đó.
- Nếu dữ liệu vẫn còn orphan records, câu lệnh VALIDATE có thể thất bại và cần một bước sửa dữ liệu tiếp theo.

Không coi việc nhận mã thoát thành công ở giai đoạn 1 là bằng chứng rằng toàn bộ migration đã hoàn thành.

### 9.3. Tránh đua tranh giữa kiểm tra và triển khai

Giả sử truy vấn orphan count trả 0 lúc 10:00:00, nhưng một ứng dụng khác ghi <code>customer_id=999</code> lúc 10:00:01 trước khi FK được tạo. Migration vẫn có thể thất bại vì dữ liệu vi phạm mới xuất hiện.

Cách giảm nguy cơ:

- Điều chỉnh logic ghi và API trước khi triển khai FK, đặc biệt ở quy trình import hoặc đồng bộ.
- Dùng transaction, lock hoặc cơ chế DBMS phù hợp với kích thước và SLA; không khóa tùy tiện bảng lớn.
- Cân nhắc chiến lược <code>NOT VALID</code> rồi xác thực về sau khi DBMS hỗ trợ.
- Chạy kiểm tra gần thời điểm áp dụng constraint, sau đó kiểm tra lại trạng thái constraint của DBMS.
- Phân công chỉ một job migration chịu trách nhiệm triển khai, tránh nhiều pipeline cạnh tranh.

Precondition là công cụ bảo vệ quan trọng nhưng **không phải cơ chế đồng bộ hóa giao dịch của mọi writer**.

## 10. Khóa ngoại và chỉ mục: liên quan nhưng không đồng nhất

FK và index có vai trò khác nhau:

- **FK:** đảm bảo quan hệ tham chiếu hợp lệ theo quy tắc của DBMS.
- **Index:** giúp DBMS tìm kiếm, join, kiểm tra hoặc cập nhật dữ liệu hiệu quả hơn trong những tình huống nhất định.

Khóa được tham chiếu ở bảng cha thông thường cần được hỗ trợ bởi PRIMARY KEY/UNIQUE phù hợp. Còn **index trên cột FK phía bảng con không phải lúc nào cũng tự sinh** khi thêm constraint. Ví dụ, PostgreSQL không tự tạo index trên cột con chỉ vì có FK; một số DBMS khác có yêu cầu/hành vi tự tạo index khác nhau.

Với truy vấn tìm đơn hàng theo khách hàng hoặc thao tác xóa/cập nhật cha, index trên <code>customer_order.customer_id</code> thường đáng xem xét:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 004-index-order-customer
      author: db-team
      changes:
        - createIndex:
            tableName: customer_order
            indexName: idx_customer_order_customer_id
            columns:
              - column:
                  name: customer_id
      rollback:
        - dropIndex:
            tableName: customer_order
            indexName: idx_customer_order_customer_id
~~~

Index có chi phí lưu trữ và ghi dữ liệu, vì vậy cần đo bằng query plan, khối lượng dữ liệu và yêu cầu vận hành. Trên PostgreSQL, tạo index đồng thời (<code>CREATE INDEX CONCURRENTLY</code>) có quy tắc transaction riêng; không tự suy rằng change type <code>createIndex</code> mặc định đã dùng cách xây dựng không chặn ghi.

### 10.1. Thứ tự tạo index và FK

Với bảng lớn, có thể cần tạo index hỗ trợ trước rồi thêm FK. Tuy nhiên, thứ tự tối ưu phụ thuộc DBMS, kiểu constraint và tải hệ thống. Một kế hoạch hợp lý phải kiểm tra:

- Cha đã có khóa unique/PK và cấu trúc index hợp lệ.
- Có nên tạo index riêng cho cột con hay không.
- Chi phí backfill và orphan scan.
- Thời gian giữ khóa khi tạo index/FK.
- Tình huống retry nếu job gián đoạn.

Không tạo index chỉ vì một quy tắc máy móc; và cũng không bỏ qua index phía bảng con khi truy vấn hoặc thao tác cha có nguy cơ chậm nghiêm trọng.

## 11. Preconditions để kiểm tra trạng thái constraint

Trong migration thật, cần phân biệt ba tình huống:

1. Bảng/cột chưa đủ điều kiện — phải HALT và sửa schema hoặc dữ liệu.
2. FK đã tồn tại đúng yêu cầu — có thể release đã được áp dụng hoặc có thao tác ngoài Liquibase; cần đối chiếu lịch sử.
3. FK đã tồn tại nhưng sai cột, sai <code>ON DELETE</code> hoặc sai schema — không được coi là đúng chỉ vì trùng tên.

Liquibase có các precondition liên quan như <code>foreignKeyConstraintExists</code>, nhưng **chỉ kiểm tra sự tồn tại theo tên chưa chứng minh định nghĩa FK tương đương với yêu cầu**.

Ví dụ minh họa kiểm tra điều kiện FK chưa tồn tại:

~~~yaml
preConditions:
  - onFail: HALT
  - onError: HALT
  - not:
      - foreignKeyConstraintExists:
          foreignKeyName: fk_customer_order_customer
          foreignKeyTableName: customer_order
~~~

Đây là mảnh YAML dùng trong changeset, không phải changelog hoàn chỉnh. Các tên thuộc tính và mức hỗ trợ điều kiện nên được validate bằng phiên bản Liquibase đang chạy.

Nếu FK đã tồn tại do thao tác thủ công, thay vì <code>MARK_RAN</code> ngay, hãy kiểm tra định nghĩa thực tế qua catalog DBMS, xác định owner của thay đổi và quyết định cách đồng bộ lịch sử theo quy trình quản trị.

## 12. Tác động tới Spring Boot, CI/CD và nhiều môi trường

### 12.1. Spring Boot

Ứng dụng Spring Boot có thể kích hoạt Liquibase khi startup nếu cấu hình tương ứng được bật. Việc thêm FK có thể khiến ứng dụng đang ghi dữ liệu vi phạm gặp lỗi ngay sau khi constraint có hiệu lực.

Do đó, cần chuẩn bị theo thứ tự:

1. Rà soát mọi luồng ghi <code>customer_order</code>, gồm API, batch import, job nền và hệ thống tích hợp.
2. Triển khai ứng dụng tương thích trước, tránh ghi orphan records.
3. Làm sạch dữ liệu cũ hoặc dùng cơ chế rollout theo giai đoạn được DBMS hỗ trợ.
4. Triển khai FK bằng một đường migration được kiểm soát.
5. Theo dõi lỗi ràng buộc và kết quả truy vấn ứng dụng sau khi triển khai.

Nếu CI/CD chạy migration chuyên trách, cần đánh giá có nên tắt auto-run Liquibase ở các instance ứng dụng production để tránh nhiều cơ chế thực thi trùng lặp. Bảng khóa <code>DATABASECHANGELOGLOCK</code> giúp phối hợp các tiến trình Liquibase nhưng không ngăn ứng dụng ghi dữ liệu nghiệp vụ vi phạm trước khi FK được áp dụng.

### 12.2. Pipeline CI/CD đề xuất

| Giai đoạn | Bằng chứng cần thu |
|---|---|
| Chuẩn bị | Release ID, artifact changelog, DBMS/driver version, schema đích |
| Khảo sát | Số orphan records, NULL, loại dữ liệu, khóa unique/PK, số hàng bảng cha/con |
| Sửa dữ liệu | Quyết định nghiệp vụ, script được review, kết quả before/after, backup/audit |
| Validate | Liquibase validate, tiền điều kiện và trạng thái changeset |
| Preview | SQL add FK, SQL rollback, quyền, thời gian khóa dự kiến |
| Test | Chạy trên DBMS/phiên bản và bộ dữ liệu đại diện |
| Deploy | Chỉ một job triển khai, bộ tham số và artifact giữ nguyên từ bước review |
| Verify | FK có đúng định nghĩa/trạng thái validate, không còn orphan, ứng dụng hoạt động |

Ví dụ lệnh kiểm tra với Liquibase CLI (cần đối chiếu cú pháp theo phiên bản):

~~~bash
liquibase --defaults-file=./liquibase-staging.properties validate
liquibase --defaults-file=./liquibase-staging.properties status --verbose
liquibase --defaults-file=./liquibase-staging.properties update-sql
~~~

<code>validate</code> kiểm tra changelog trong phạm vi công cụ; <code>status</code> so sánh changeset với lịch sử; <code>update-sql</code> giúp review SQL. **Không lệnh nào trong ba lệnh này thay thế việc kiểm tra dữ liệu vi phạm, quyền, khóa, ảnh hưởng lên ứng dụng và trạng thái FK sau triển khai.**

### 12.3. Môi trường khác nhau có dữ liệu khác nhau

Staging không có orphan records không chứng minh production cũng sạch. Không nên chỉ dựa vào database test trống để xác nhận FK migration. Cần đánh giá mẫu dữ liệu đại diện, thống kê vi phạm và kế hoạch khắc phục tại từng môi trường.

Khi dùng tham số hóa schema, hãy kiểm tra giá trị hiệu lực và SQL thực tế sau thay thế; không để precondition đọc bảng ở schema mặc định trong khi FK được tạo ở schema khác.

## 13. Rollback, khôi phục và failure recovery

### 13.1. Gỡ FK không hoàn nguyên dữ liệu

Rollback cơ bản:

~~~yaml
rollback:
  - dropForeignKeyConstraint:
      baseTableName: customer_order
      constraintName: fk_customer_order_customer
~~~

Đây là mảnh rollback nằm trong changeset. Việc gỡ FK thường chỉ loại bỏ ràng buộc, không:

- Phục hồi các bản ghi đã bị xóa trong quá trình làm sạch.
- Khôi phục customer_id đã thay đổi do backfill.
- Đưa ứng dụng về version cũ.
- Hoàn tác các hành vi cascade đã xảy ra khi FK đang có hiệu lực.

Vì thế, việc sửa dữ liệu phải có kế hoạch rollback/forward fix và backup riêng. Những thay đổi dữ liệu không thể phục hồi bằng phép đảo đơn giản cần được ghi nhận như một rủi ro phát hành.

### 13.2. Khi add FK thất bại

Hành động nên làm:

1. Lưu mã lỗi, log Liquibase, SQL đã phát sinh và trạng thái transaction.
2. Kiểm tra FK có tồn tại hay không và được validate đến đâu; không suy chỉ từ exit code.
3. Xác định nguyên nhân: orphan, kiểu không tương thích, quyền, khóa cha, schema sai hay DBMS không hỗ trợ tùy chọn.
4. Không sửa changeset đã phát hành hoặc xóa bảng lịch sử để “thử lại cho qua”.
5. Sửa nguyên nhân gốc, kiểm tra lại dữ liệu và chọn retry/changeset mới theo trạng thái database thực tế.

Trên một số DBMS, DDL có thể commit độc lập hoặc không rollback hoàn toàn theo transaction ứng dụng. Vì vậy, sau lỗi phải **đọc trạng thái thực tế của DBMS**, không giả định toàn bộ migration đã được hoàn tác.

## 14. Các lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Tạo FK báo vi phạm tham chiếu | Còn đơn hàng có customer_id không có cha | Dùng anti-join/COUNT, xử lý orphan theo quy trình được duyệt |
| FK tạo thành công nhưng vẫn có hàng NULL | FK không đồng nghĩa với NOT NULL | Xem quy tắc nghiệp vụ, backfill và thêm NOT NULL khi thích hợp |
| Lỗi không tìm thấy bảng/cột | Sai schema, tên, chữ hoa/thường hoặc tham số | Kiểm tra catalog, SQL preview và tên vật lý |
| FK không tạo được do khóa đích | Bảng cha thiếu PRIMARY KEY/UNIQUE phù hợp | Thiết kế khóa đích, xử lý duplicate, tạo unique constraint |
| Lỗi không tương thích kiểu | Kiểu, độ rộng, signed/unsigned hoặc collation khác nhau | Chuẩn hóa kiểu với migration riêng được kiểm chứng |
| FK ghép vẫn cho hàng có một cột NULL | Quy tắc NULL của composite FK theo DBMS | Bổ sung NOT NULL hoặc chọn thiết kế constraint phù hợp |
| DELETE khách hàng thất bại | FK đang ngăn xóa khi còn đơn hàng | Điều chỉnh quy trình nghiệp vụ; không tự chuyển sang CASCADE |
| Xóa cha kéo theo mất nhiều bản ghi con | ON DELETE CASCADE được chọn sai mục tiêu | Đánh giá retention, backup, rollback và chính sách xóa |
| Pipeline dừng ở precondition | Dữ liệu vi phạm hoặc lỗi đánh giá | Phân biệt onFail và onError, xem SQL count và quyền |
| FK validate trên staging, fail production | Chênh lệch dữ liệu/khối lượng giữa môi trường | Khảo sát trên từng môi trường, không suy từ test trống |
| Sau preview có thêm orphan | Concurrent writer tạo dữ liệu trước DDL | Điều chỉnh luồng ghi, khóa/transaction thích hợp, rollout staged |
| Thêm FK làm ứng dụng chậm | Thiếu index phía con, khóa khi DDL/validation | Xem query plan, đo khóa, cân nhắc index/tách giai đoạn |
| Báo deploy thành công nhưng vẫn có dữ liệu cũ vi phạm | Constraint chưa validate dữ liệu lịch sử | Kiểm tra trạng thái validation của DBMS, lên kế hoạch VALIDATE |
| Rollback gỡ FK nhưng dữ liệu không hồi phục | Rollback chỉ drop constraint | Có backup/restore hoặc forward fix cho data cleanup |

## 15. Bài thực hành có kiểm chứng

### Bài A — Từ bảng chưa có FK tới schema hợp lệ

Trên một database học tập, thực hiện:

1. Tạo hai bảng <code>customer</code> và <code>customer_order</code> như phần 2.
2. Thêm khách hàng ID 10, 20 và đơn hàng tham chiếu 10, 20, 999.
3. Chạy truy vấn orphan ở phần 4; xác nhận tìm thấy ID 999.
4. Thử changeset có <code>sqlCheck</code> và <code>onFail: HALT</code>; xác nhận migration dừng.
5. Chọn cách sửa 999 có chứng cứ trong dữ liệu thử, rồi chạy lại truy vấn orphan count.
6. Sau khi count bằng 0, chạy changeset tạo FK và kiểm tra metadata constraint.
7. Thử INSERT một đơn hàng với customer_id không tồn tại; DBMS phải từ chối nếu FK đã được bật và áp dụng.
8. Thử INSERT với customer_id NULL, quan sát sự khác biệt giữa FK và NOT NULL.
9. Review SQL rollback, thực hiện rollback trên database thử, xác nhận chỉ constraint bị gỡ.

Không cần và không nên thao tác trực tiếp vào <code>DATABASECHANGELOG</code> để tái hiện các trường hợp; sử dụng cơ sở dữ liệu thử mới hoặc reset/rollback theo quy trình.

### Bài B — Kiểm tra tính đúng của ON DELETE

Giả sử một khách hàng có ba đơn hàng. Hãy dự đoán trước kết quả của lệnh DELETE khách hàng theo:

| FK action | Dự đoán cần kiểm tra |
|---|---|
| Không khai báo action | DBMS có thể chặn xóa theo mặc định; xác minh theo engine |
| <code>RESTRICT</code> | Xóa bị ngăn nếu vẫn còn đơn hàng tham chiếu |
| <code>CASCADE</code> | Những đơn hàng phụ thuộc có thể bị xóa theo |
| <code>SET NULL</code> | customer_id ở đơn hàng có thể thành NULL nếu cột cho phép |

Chạy thử từng phương án **trong database cô lập** với dữ liệu có thể tạo lại. Không dùng DELETE để thực hành trên hệ thống thật.

### Bài C — Khóa ghép tenant_id và customer_id

Thiết kế bảng khách hàng có khóa unique <code>(tenant_id, id)</code>, bảng đơn hàng có cả <code>tenant_id</code> và <code>customer_id</code>. Hãy:

- Tạo một đơn hàng có tenant A nhưng customer thuộc tenant B.
- Chứng minh FK chỉ tham chiếu <code>customer_id</code> có thể không phát hiện lỗi ngữ nghĩa tenant.
- Viết FK ghép đúng thứ tự cột và truy vấn phát hiện sai quan hệ.
- Kiểm tra trường hợp NULL và quyết định có cần NOT NULL hay không.

Mục đích là hiểu rằng **thiết kế khóa được tham chiếu quyết định độ mạnh của ràng buộc**; một FK hợp lệ không mặc nhiên bảo vệ mọi quy tắc miền nghiệp vụ.

## 16. Checklist trước khi đưa FK lên production

- [ ] Bảng cha và con đúng database/schema, tên thực tế và kiểu dữ liệu.
- [ ] Khóa cha là PRIMARY KEY/UNIQUE phù hợp, không có duplicate cản trở.
- [ ] Quy tắc NULL của cột con được thống nhất với nghiệp vụ.
- [ ] Orphan count đã được kiểm tra trên chính môi trường đích và có bằng chứng.
- [ ] Dữ liệu vi phạm được phân loại, owner nghiệp vụ duyệt cách khắc phục.
- [ ] Không tạo bản ghi cha giả hoặc xóa bản ghi con chỉ để làm FK “xanh”.
- [ ] Luồng ghi ứng dụng, batch import và tích hợp ngoài không còn tạo orphan mới.
- [ ] Chỉ mục phía con và chi phí tạo FK/validate đã được đánh giá.
- [ ] <code>onDelete</code>, <code>onUpdate</code>, deferrable và hành vi DBMS được hiểu rõ.
- [ ] Tiền điều kiện dùng HALT khi giả định bắt buộc không đạt; không MARK_RAN tùy tiện.
- [ ] Nếu thêm FK ở trạng thái chưa validate, có bước và thời điểm validate rõ ràng.
- [ ] Changelog đã được validate, xem status, SQL preview và test với dữ liệu đại diện.
- [ ] Có kế hoạch rollback constraint, backup dữ liệu và hướng forward fix.
- [ ] Bộ tham số và artifact không thay đổi giữa preview và update.
- [ ] Sau triển khai, đã xác minh định nghĩa FK, trạng thái validation, dữ liệu và lỗi ứng dụng.

## 17. Ghi nhớ

Khóa ngoại là cơ chế toàn vẹn tham chiếu do database bảo vệ; Liquibase giúp khai báo và quản lý lịch sử triển khai FK bằng các changeset có thể kiểm chứng. Phần quyết định chất lượng migration không chỉ là cú pháp <code>addForeignKeyConstraint</code>, mà là **trạng thái dữ liệu hiện hữu, tính đúng của khóa đích, quy tắc NULL, hành vi ON DELETE/ON UPDATE, khả năng validate và kế hoạch rollback**.

Một quy trình đáng tin cậy là: **thiết kế quan hệ → kiểm kê orphan/NULL → xử lý dữ liệu có chứng cứ → ngăn lỗi mới → precondition và review SQL → tạo FK → xác thực trạng thái constraint → giám sát ứng dụng**. Quy trình đó giúp schema migration bằng Liquibase có thể lặp lại, truy vết và triển khai an toàn hơn qua các môi trường, kể cả khi tích hợp Spring Boot hoặc CI/CD.
