# Sử dụng modifySql cho khác biệt SQL có kiểm soát

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, bạn học cách quản lý thay đổi schema và dữ liệu bằng Liquibase thông qua changelog, changeset, precondition, checksum và lịch sử triển khai; đồng thời thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài thuộc chương **Tham số hóa** này tập trung vào **modifySql**: một cơ chế chỉnh sửa văn bản SQL do Liquibase chuẩn bị thực thi để đáp ứng khác biệt có chủ đích giữa các hệ quản trị cơ sở dữ liệu (DBMS) hoặc môi trường.

Ví dụ, một changeset khai báo **createTable** chung có thể tạo bảng trên PostgreSQL và MySQL. Nếu MySQL cần chỉ định rõ **ENGINE=InnoDB**, bạn có thể bổ sung phần đó vào SQL được sinh ra thay vì nhân đôi cả changeset. Tuy nhiên, modifySql thao tác lên **câu SQL đầu ra**, nên cần giới hạn phạm vi chính xác và kiểm tra câu SQL dự kiến. Nó không thay thế việc chọn change type phù hợp, precondition, migration dữ liệu hay quy trình review.

## 1. Phân biệt tham số hóa và chỉnh sửa SQL đầu ra

Liquibase cho phép diễn đạt thay đổi theo hai tầng:

- **Tầng định nghĩa migration:** changelog, changeset, các change type như **createTable**, **addColumn**, **createIndex** và các tham số của chúng. Liquibase dùng dialect và bộ sinh SQL để tạo lệnh phù hợp với database đích.
- **Tầng SQL đã sinh:** trước khi thực thi, Liquibase có thể áp dụng các thao tác **modifySql** để thêm, bớt hoặc thay thế một đoạn trong câu SQL phù hợp với điều kiện của modifier.

Ví dụ, cùng một change type có thể sinh ra cú pháp tương đương nhưng khác nhau giữa MySQL và PostgreSQL. Với những khác biệt được Liquibase hỗ trợ trực tiếp như kiểu dữ liệu chung, auto-increment hoặc tên đối tượng, hãy ưu tiên change type và cấu hình có sẵn. **modifySql** phù hợp khi SQL đầu ra cần một điều chỉnh nhỏ, rõ ràng và có thể xác minh, nhưng không có thuộc tính khai báo trực tiếp thích hợp.

Một khái niệm khác dễ nhầm là **changelog property**. Thuộc tính như `${schemaName}` được thay thế trong cấu hình/changelog để chọn tên schema, tên tablespace hoặc giá trị khác; nó không phải thao tác tìm và thay thế trên SQL đã sinh. Nếu muốn thay đổi **giá trị tham số**, hãy xét property. Nếu muốn thay đổi **cú pháp SQL đầu ra**, mới xét modifySql.

### Khi nào nên chọn modifySql?

| Nhu cầu | Cơ chế nên cân nhắc | Lý do |
|---|---|---|
| Chọn tên schema hoặc tablespace theo môi trường | Changelog property, cấu hình CLI/Spring Boot | Rõ đầu vào và tránh sửa chuỗi SQL |
| Thêm hậu tố đặc thù vào câu CREATE TABLE của MySQL | **modifySql** có **dbms** và **append** | Chênh lệch SQL nhỏ, có thể xem trực tiếp bằng update-sql |
| Tạo bảng/cột/index theo cú pháp chuẩn mà Liquibase đã hỗ trợ | Change type khai báo | Dễ portable, dễ đọc và ít phụ thuộc định dạng SQL đầu ra |
| Chạy thay đổi riêng cho Oracle hay PostgreSQL | Changeset **dbms**, changelog được tổ chức theo DBMS, hoặc precondition | Phạm vi thực thi phải được giới hạn rõ; modifier chỉ sửa văn bản SQL |
| Thực hiện backfill hoặc DDL phức tạp phụ thuộc DBMS | Changeset mới hoặc **sqlFile** riêng được review | Cần kiểm soát giao dịch, dữ liệu, idempotence và rollback |
| Bảo đảm SQL chỉ chạy trên staging | Context/label của changeset và cấu hình triển khai | Đó là điều kiện thực thi, không phải chỉ là thay đổi cú pháp SQL |

Nếu cần cùng một hành vi về mặt nghiệp vụ, hãy cố mô tả hành vi đó ở tầng thay đổi. Nếu chỉ khác một token SQL được DBMS yêu cầu, modifier có thể là lựa chọn phù hợp.

## 2. modifySql nằm ở đâu trong changelog?

Trong changelog XML, **modifySql** được đặt trong **changeset**, bên cạnh các change type tạo ra câu SQL cần sửa. Ví dụ một changeset chỉ có một thao tác tạo bảng:

~~~xml
<changeSet id="001-create-audit-event" author="db-team">
    <createTable tableName="audit_event">
        <column name="id" type="bigint" autoIncrement="true">
            <constraints primaryKey="true" nullable="false"/>
        </column>
        <column name="event_type" type="varchar(80)">
            <constraints nullable="false"/>
        </column>
        <column name="created_at" type="timestamp"/>
    </createTable>

    <modifySql dbms="mysql" applyToRollback="false">
        <append value=" ENGINE=InnoDB"/>
    </modifySql>

    <rollback>
        <dropTable tableName="audit_event"/>
    </rollback>
</changeSet>
~~~

Đây là **nội dung bên trong một changelog XML hợp lệ**; file hoàn chỉnh vẫn cần phần tử gốc **databaseChangeLog** cùng khai báo namespace/schema phù hợp với phiên bản Liquibase của dự án.

Ý nghĩa của ví dụ:

1. Liquibase đọc **createTable** và sinh SQL tạo bảng cho DBMS đích.
2. Khi DBMS là **MySQL**, modifier có thể gắn thêm chuỗi **ENGINE=InnoDB** vào câu SQL tạo bảng.
3. Khi DBMS là **PostgreSQL**, điều kiện **dbms="mysql"** không khớp nên phần append không áp dụng.
4. **applyToRollback="false"** nêu rõ không áp dụng sửa đổi SQL này cho câu rollback; câu **DROP TABLE** không được gắn thêm hậu tố ENGINE vốn không hợp lệ.
5. Việc bảng được tạo hoặc rollback được ghi nhận theo lịch sử changeset thông thường trong **DATABASECHANGELOG**.

Ví dụ chỉ dùng để minh họa cách điều chỉnh SQL. Cú pháp SQL thực tế do Liquibase sinh ra có thể khác về kiểu dữ liệu, dấu nháy, tên schema và câu lệnh phụ trợ tùy phiên bản Liquibase, JDBC driver và DBMS. Cần quan sát SQL thực tế bằng **update-sql** trước khi dùng trong hệ thống thật.

### SQL trước và sau khi chỉnh sửa

Có thể hình dung kết quả theo dạng giản lược:

~~~sql
-- SQL sinh ra trước khi áp dụng modifier (minh họa)
CREATE TABLE audit_event (
    id BIGINT NOT NULL AUTO_INCREMENT,
    event_type VARCHAR(80) NOT NULL,
    created_at TIMESTAMP,
    PRIMARY KEY (id)
);

-- SQL dành cho MySQL sau modifier (minh họa)
CREATE TABLE audit_event (
    id BIGINT NOT NULL AUTO_INCREMENT,
    event_type VARCHAR(80) NOT NULL,
    created_at TIMESTAMP,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
~~~

Điểm khác biệt nằm ở hậu tố cuối lệnh. Đây là ví dụ về **thay đổi cú pháp có giới hạn**, không phải thay đổi mô hình dữ liệu nghiệp vụ. Định dạng thực tế và vị trí dấu kết thúc câu lệnh phải được xác nhận trên đầu ra Liquibase.

## 3. Các thao tác của modifySql

Liquibase cung cấp các thao tác chỉnh SQL thường gặp: **append**, **prepend**, **replace** và **regExpReplace**. Chúng có mục đích khác nhau và mức độ rủi ro khác nhau.

| Thao tác | Ý nghĩa | Phù hợp với | Rủi ro cần kiểm tra |
|---|---|---|---|
| **append** | Thêm văn bản vào cuối câu SQL đích | Hậu tố tùy DBMS như tùy chọn của CREATE TABLE | Có thể gắn vào nhiều câu lệnh trong changeset |
| **prepend** | Thêm văn bản vào đầu câu SQL đích | Chú thích/hint hoặc tiền tố cú pháp có chủ đích | Tiền tố có thể không hợp lệ với từng loại câu SQL |
| **replace** | Thay thế chuỗi văn bản khớp chính xác | Chênh lệch token xác định sau khi đã xem SQL | Có thể thay nhiều vị trí hoặc không khớp vì chữ hoa/thường/định dạng |
| **regExpReplace** | Thay thế theo biểu thức chính quy | Mẫu có biến thể được xác định, cần kiểm soát | Biểu thức quá rộng có thể thay sai nhiều đoạn |

Ví dụ cấu trúc XML cho từng thao tác, trình bày như các modifier **độc lập** để minh họa cú pháp:

~~~xml
<!-- Chọn một thao tác phù hợp cho mỗi tình huống đã kiểm chứng -->
<modifySql dbms="mysql">
    <append value=" ENGINE=InnoDB"/>
</modifySql>

<modifySql dbms="postgresql">
    <prepend value="/* generated by Liquibase */ "/>
</modifySql>

<modifySql dbms="mysql">
    <replace replace="SOME_EXACT_TOKEN" with="SOME_VENDOR_TOKEN"/>
</modifySql>

<modifySql dbms="mysql">
    <regExpReplace replace="SOME_PATTERN" with="REPLACEMENT"/>
</modifySql>
~~~

Các chuỗi **SOME_EXACT_TOKEN**, **SOME_VENDOR_TOKEN**, **SOME_PATTERN** và **REPLACEMENT** là giá trị minh họa, chưa phải SQL có thể áp dụng. **replace** và **regExpReplace** chỉ có ý nghĩa sau khi bạn đã biết chính xác SQL được sinh ra và đã xác định phạm vi thay thế. Đặc biệt, regex phải được kiểm tra với bản SQL thật, kể cả escape khi viết trong XML/YAML.

Một lỗi thường gặp là cố thay **VARCHAR** thành một kiểu dữ liệu khác bằng biểu thức quá rộng. Nếu changeset có nhiều cột, việc thay có thể tác động đến cả các cột không mong muốn. Khi muốn đổi kiểu dữ liệu một cột, sửa trực tiếp thuộc tính **type** của change type ở migration chưa chạy, hoặc tạo migration **modifyDataType** mới nếu changeset cũ đã triển khai, sẽ dễ kiểm soát hơn.

## 4. Giới hạn phạm vi theo DBMS và môi trường

Thuộc tính **dbms** trên **modifySql** quyết định **khi nào modifier được áp dụng**. Ví dụ:

~~~xml
<modifySql dbms="mysql" applyToRollback="false">
    <append value=" ENGINE=InnoDB"/>
</modifySql>
~~~

Ở database MySQL, Liquibase có thể sinh SQL được bổ sung hậu tố. Ở database khác, **changeset vẫn có thể được chạy**, chỉ là modifier MySQL không áp dụng. Đây là khác biệt rất quan trọng so với đặt **dbms** ở mức changeset hoặc dùng precondition hạn chế cả changeset.

Nếu một changeset chứa lệnh chỉ hỗ trợ PostgreSQL, việc đặt **dbms="postgresql"** trên modifySql **không ngăn** Liquibase chạy nội dung gốc trên MySQL. Để giới hạn toàn bộ changeset, cần thiết lập ràng buộc thực thi ở mức changeset hoặc tổ chức changelog phù hợp.

**Context** và **label** có thể dùng để kiểm soát việc áp dụng modifier theo cấu hình được Liquibase hỗ trợ trong phiên bản dự án. Cần phân biệt điều kiện của modifier với context/label của changeset:

- **Điều kiện changeset** quyết định changeset có nằm trong phạm vi được chạy hay không.
- **Điều kiện modifier** quyết định có sửa SQL của changeset đã được chọn hay không.
- **Tham số lệnh triển khai** quyết định context/label expression nào đang được bật trong lần update.

Ví dụ, bạn có thể muốn một hậu tố tùy chọn chỉ xuất hiện với database MySQL ở môi trường kiểm thử. Khi đó cần kiểm tra cả điều kiện DBMS lẫn điều kiện môi trường, đồng thời tránh dựa vào modifier như biện pháp duy nhất ngăn thao tác nghiệp vụ chạy sai môi trường.

Các khóa điều kiện và cú pháp cụ thể của context/label cần đối chiếu tài liệu của **phiên bản Liquibase đang chạy**. Không nên dùng một thuộc tính ít phổ biến theo suy đoán rồi bỏ qua **validate** và việc xem SQL trước triển khai.

## 5. Vì sao nên giữ changeset nhỏ khi dùng modifySql?

**modifySql** tác động lên văn bản SQL do các thay đổi trong changeset tạo ra theo phạm vi modifier. Nếu một changeset tạo bảng, thêm index và cập nhật dữ liệu, một thao tác append chung có thể làm hỏng các câu SQL khác.

Ví dụ không nên áp dụng:

~~~xml
<changeSet id="bad-mixed-changes" author="db-team">
    <createTable tableName="audit_event">
        <column name="id" type="bigint"/>
    </createTable>
    <createIndex tableName="audit_event" indexName="idx_audit_id">
        <column name="id"/>
    </createIndex>
    <modifySql dbms="mysql">
        <append value=" ENGINE=InnoDB"/>
    </modifySql>
</changeSet>
~~~

Mục tiêu ban đầu chỉ là thêm **ENGINE=InnoDB** cho câu **CREATE TABLE**. Nhưng changeset còn sinh **CREATE INDEX**, vốn không nhận hậu tố ENGINE theo cách này. Câu SQL kết quả có thể không hợp lệ.

Cách an toàn hơn là **tách thành hai changeset có nhiệm vụ rõ ràng**:

~~~xml
<changeSet id="010-create-audit-event" author="db-team">
    <createTable tableName="audit_event">
        <column name="id" type="bigint">
            <constraints primaryKey="true" nullable="false"/>
        </column>
    </createTable>
    <modifySql dbms="mysql" applyToRollback="false">
        <append value=" ENGINE=InnoDB"/>
    </modifySql>
</changeSet>

<changeSet id="011-index-audit-event" author="db-team">
    <createIndex tableName="audit_event" indexName="idx_audit_id">
        <column name="id"/>
    </createIndex>
</changeSet>
~~~

Đây là các ví dụ minh họa, không phải đề xuất chạy hai ví dụ xung đột lên cùng database. Khi xây dự án thực tế, chỉ đưa một phiên bản được review vào changelog, cùng rollback theo nhu cầu và DBMS đích.

Việc tách nhỏ giúp giới hạn câu SQL chịu ảnh hưởng, đơn giản hóa review, dễ đọc log và giảm rủi ro của **replace** hoặc **regExpReplace**. Nó cũng giúp rollback được thiết kế riêng cho từng thay đổi.

## 6. modifySql và rollback: chiều xuôi không đương nhiên đúng chiều ngược

Rollback là thao tác riêng được Liquibase sinh hoặc được bạn khai báo trong changeset. SQL rollback có thể khác hoàn toàn SQL update. Hậu tố hợp lệ với **CREATE TABLE** chưa chắc hợp lệ với **DROP TABLE**; tiền tố/hint dành cho **UPDATE** chưa chắc áp dụng được cho câu SQL rollback.

Ví dụ:

~~~xml
<modifySql dbms="mysql" applyToRollback="false">
    <append value=" ENGINE=InnoDB"/>
</modifySql>
~~~

Ở đây đặt **applyToRollback="false"** để thể hiện rõ không sửa SQL rollback theo cùng quy tắc. Khi có nhu cầu sửa rollback, chỉ bật cơ chế đó sau khi đã kiểm tra **SQL rollback** thực tế và chứng minh việc chỉnh sửa hợp lệ với từng loại lệnh.

Một quy trình review phù hợp gồm: kiểm tra SQL update có hậu tố đúng, kiểm tra rollback vẫn là câu lệnh hợp lệ, xác nhận tác động dữ liệu của rollback và thử trên database dùng một lần hoặc bản sao phù hợp. Không coi việc rollback thực thi thành công là bằng chứng dữ liệu hoàn toàn trở về trạng thái cũ: việc xóa cột/bảng vẫn có thể làm mất dữ liệu được ghi sau migration.

Nếu DBMS không hỗ trợ transaction cho một số DDL hoặc SQL có hiệu ứng ngoài transaction, rollback có thể không tự động đảo ngược mọi tác động của một lần triển khai thất bại. Khi đó cần kế hoạch phục hồi hoặc changeset sửa tiến về phía trước.

## 7. modifySql, checksum và lịch sử triển khai

**DATABASECHANGELOG** là nơi Liquibase ghi nhận changeset đã được xử lý, cùng các thông tin như **ID**, **AUTHOR**, **FILENAME**, **MD5SUM**, **DATEEXECUTED** và **EXECTYPE**. Checksum được Liquibase dùng để phát hiện nội dung changeset đã ghi nhận có khác với định nghĩa hiện tại hay không.

Điều quan trọng là **modifySql nằm trong định nghĩa migration**. Nếu thay đổi thao tác **append**, **replace** hoặc điều kiện áp dụng sau khi changeset đã chạy, bạn đang thay đổi cách sinh SQL của một bước lịch sử. Không được mặc định rằng lần update kế tiếp sẽ chạy lại câu SQL mới hay rằng mọi môi trường sẽ cập nhật giống nhau.

Tùy cách Liquibase tạo checksum và loại thay đổi liên quan, tác động của việc sửa modifier lên checksum cần được **kiểm chứng bằng đúng phiên bản Liquibase thực tế**. Dù checksum có phát hiện khác biệt hay không, một changeset đã đánh dấu thực thi thường sẽ không tự chạy lại chỉ vì bạn đổi nội dung SQL. Vì vậy, hãy tuân theo quy tắc:

1. **Chưa triển khai ở môi trường dùng chung:** có thể sửa modifier theo quy trình review, rồi kiểm tra lại SQL cho từng DBMS mục tiêu.
2. **Đã triển khai ở môi trường dùng chung:** ưu tiên tạo changeset mới thể hiện yêu cầu sửa đổi; giữ nguyên lịch sử đã được áp dụng.
3. **Cần điều chỉnh một changeset đặc biệt được thiết kế chạy lại:** đánh giá riêng tính idempotent, runOnChange/runAlways, phiên bản Liquibase và quy trình triển khai. Không dùng hai cờ đó để hợp thức hóa mọi sửa đổi.
4. **Gặp lỗi checksum:** xác minh file changelog, id/author, đường dẫn và lịch sử triển khai trước khi xử lý. Không sử dụng **clear-checksums** như bước mặc định để ép pipeline chạy tiếp.

Checksum không xác nhận rằng câu SQL sau modifySql đã đạt trạng thái schema mong muốn. Đó là việc của kiểm thử migration, so sánh schema và các kiểm tra dữ liệu sau triển khai.

## 8. Kịch bản thực tế: một changelog cho PostgreSQL và MySQL

Giả sử ứng dụng lưu bản ghi audit trên hai hệ cơ sở dữ liệu:

- **PostgreSQL:** tạo bảng audit_event với cú pháp mặc định do Liquibase sinh.
- **MySQL:** cũng tạo bảng audit_event nhưng nhóm vận hành muốn chỉ định InnoDB một cách tường minh cho bảng mới.

Thay vì viết hai phiên bản changeset tạo bảng (dễ lệch tên cột hoặc constraint), dùng một change type chung và thêm modifier nhỏ có **dbms="mysql"**.

<text>Quy trình diễn giải:</text>

~~~text
             Changelog chung
                   |
                   v
           createTable audit_event
                   |
                   v
          Liquibase sinh SQL theo DBMS
                   |
              +----+----+
              |         |
        PostgreSQL     MySQL
              |         |
        Giữ SQL      append
        đã sinh      ENGINE=InnoDB
              |         |
              +----+----+
                   |
                   v
        Xem SQL dự kiến / kiểm tra
                   |
                   v
           Chạy trên môi trường đích
                   |
                   v
          Đối chiếu lịch sử và schema
~~~

Trước khi đưa vào pipeline, kiểm tra **cùng changelog** bằng kết nối PostgreSQL thử nghiệm và MySQL thử nghiệm. Kết quả mong đợi là SQL PostgreSQL không có hậu tố ENGINE, SQL MySQL có hậu tố đó, và cả hai đều tạo bảng đáp ứng schema mong muốn. Kiểm tra cả câu rollback nếu có định nghĩa.

Dù hai database cùng ghi nhận một changeset có **id/author/đường dẫn** tương ứng, câu SQL thực thi thực tế vẫn có thể khác nhau. Vì vậy, việc tổ chức changelog chung không loại bỏ trách nhiệm kiểm tra trên từng DBMS được hỗ trợ.

### Khi giải pháp này không còn phù hợp

Nếu MySQL yêu cầu một cấu trúc dữ liệu khác hoàn toàn, ví dụ kiểu bảng, partition hay chuỗi thao tác khác không thể mô tả bằng một thay đổi chung nhỏ, đừng xây chuỗi **replace** dài để “biến” một SQL thành loại khác. Khi đó nên dùng các changeset DBMS-specific được quản lý rõ hoặc SQL riêng có kiểm chứng. Mục tiêu là sự khác biệt có thể đọc và review, không phải tối đa hóa số lệnh replace.

## 9. Kiểm tra SQL trước khi cập nhật database

**validate** kiểm tra các lỗi cấu trúc changelog mà Liquibase có thể phát hiện; nó không chứng minh SQL sau modifier hợp lệ trên DBMS. **update-sql** giúp xem SQL dự kiến tạo ra, còn **update** mới thực thi migration. Với công cụ CLI đã có cấu hình kết nối và driver, quy trình cơ bản là:

~~~shell
liquibase validate
liquibase update-sql
liquibase update
liquibase status --verbose
~~~

Các lệnh ở trên giả định đã cung cấp **changeLogFile**, URL, credential, JDBC driver và tùy chọn môi trường qua cấu hình tương ứng. Không chạy các lệnh update trên production chỉ để “xem thử”. Hãy dùng database thử nghiệm phù hợp và quy trình phê duyệt trước môi trường thật.

Trước khi gọi **update**, đọc kỹ đầu ra **update-sql** với những câu hỏi sau:

- Modifier có được áp dụng đúng DBMS mong muốn không?
- SQL tạo bảng có được thêm hậu tố tại đúng vị trí không? Có bị lặp hậu tố không?
- Có câu **CREATE INDEX**, **ALTER TABLE**, **UPDATE** hoặc SQL metadata nào bị sửa ngoài ý định không?
- Phần thay thế có ảnh hưởng đến tên bảng/cột hoặc literal string không?
- Mệnh đề dành riêng cho DBMS có đúng với phiên bản database đang chạy không?
- Nếu dùng context/label, kết quả có thay đổi đúng khi bật/tắt filter không?
- SQL rollback, nếu có, có hợp lệ và có tác động dữ liệu chấp nhận được không?

Sau khi chạy trên database thử nghiệm, kiểm tra schema thực tế chứ không chỉ dựa vào thông báo **update thành công**. Với MySQL, có thể xem metadata bảng để xác nhận storage engine thực tế; với PostgreSQL, kiểm tra cột, constraint và index tương ứng. Ghi lại kết quả theo phiên bản Liquibase, DBMS, driver và changelog để người review có thể tái hiện.

## 10. Những lỗi dễ mắc và cách sửa

### Lỗi 1: chỉ định dbms cho modifier nhưng nghĩ đã chặn changeset

Ví dụ changeset có câu SQL chỉ chạy trên MySQL, còn modifier được đặt **dbms="mysql"**. Trên PostgreSQL, modifier bị bỏ qua nhưng changeset gốc vẫn có thể được xét thực thi. Giải pháp là đặt điều kiện DBMS ở mức **changeset**, dùng precondition hoặc tách changeset cho từng DBMS phù hợp. Modifier chỉ quyết định sửa câu SQL, không tự giới hạn toàn bộ migration.

### Lỗi 2: append vào changeset có nhiều kiểu câu SQL

Một changeset tạo bảng và thêm index nhận cùng hậu tố **ENGINE=InnoDB**, khiến câu index có nguy cơ sai cú pháp. Cách sửa là chia changeset để chỉ câu **CREATE TABLE** chịu append, rồi xác minh update-sql trên MySQL.

### Lỗi 3: replace chuỗi quá rộng

Một replace nhắm **VARCHAR(255)** có thể đổi toàn bộ cột cùng kiểu, trong khi chỉ một cột cần khác. Hãy mô tả kiểu của từng cột ở tầng change type, hoặc dùng thay đổi riêng. Nếu buộc dùng replace, cần kiểm tra số lần match và toàn bộ câu SQL đầu ra.

### Lỗi 4: không quan sát thay đổi sau nâng cấp Liquibase

Một phiên bản Liquibase có thể thay đổi cách biểu diễn SQL hoặc quy tắc định dạng, làm mẫu **replace** không còn khớp. Việc SQL mới vẫn chạy thành công không chứng minh modifier đã áp dụng. Giải pháp là giữ phiên bản Liquibase ổn định trong CI và luôn so sánh SQL dự kiến khi nâng cấp.

### Lỗi 5: modifier làm SQL update hợp lệ nhưng rollback sai

Đặt append mà không giới hạn rollback có thể khiến câu **DROP TABLE** nhận hậu tố bất hợp lệ. Xác định rõ **applyToRollback**, xem SQL rollback và thử trên môi trường phù hợp.

### Lỗi 6: sửa changeset cũ để “fix” production

Nếu một changeset đã triển khai, việc chỉnh modifier trong file cũ có thể làm môi trường mới và cũ có lịch sử khác nhau. Tạo changeset mới để chuyển từ trạng thái đã triển khai sang trạng thái mong muốn, hoặc xây dựng kế hoạch reconciliation có bằng chứng xác minh.

### Lỗi 7: dùng modifySql để che giấu vấn đề thiết kế migration

Một thay đổi bảng lớn cần giảm lock, backfill theo batch hoặc deploy expand–contract không thể được giải quyết chỉ bằng thay thế chuỗi SQL. Cần thiết kế chiến lược triển khai, transaction, thời điểm chạy, kiểm tra dữ liệu và rollback/forward-fix.

## 11. Bài thực hành có kiểm chứng

Bạn có thể tự tạo một changelog XML thử nghiệm theo kịch bản bảng **audit_event** với MySQL và PostgreSQL. Không dùng chung database production làm nơi thử.

**Bước 1 — Tạo changeset chung.** Khai báo createTable với id, event_type, created_at. Đặt **modifySql dbms="mysql"** với **append ENGINE=InnoDB**. Tách change index thành changeset khác nếu cần.

**Bước 2 — Kiểm tra PostgreSQL.** Cấu hình Liquibase kết nối PostgreSQL thử nghiệm. Chạy **validate**, sau đó **update-sql**. Xác minh SQL không chứa hậu tố ENGINE. Chạy **update**, kiểm tra bảng và **DATABASECHANGELOG**.

**Bước 3 — Kiểm tra MySQL.** Chuyển URL/driver/credential sang MySQL thử nghiệm mà không sửa changelog. Chạy lại **validate** và **update-sql**, kiểm tra hậu tố InnoDB chỉ xuất hiện trên CREATE TABLE tương ứng. Chạy **update**, xác nhận storage engine của bảng và lịch sử changeset.

**Bước 4 — Kiểm tra chạy lại.** Chạy **update** lần thứ hai trên từng database. Với changeset mặc định đã chạy, Liquibase thường không áp dụng lại change type và modifySql. Thay đổi cấu trúc sau đó phải được mô tả bằng changeset mới.

**Bước 5 — Kiểm tra rollback.** Trên database dùng một lần, xem SQL rollback (bằng lệnh rollback-sql phù hợp với phiên bản CLI). Đảm bảo SQL không bị gắn hậu tố dành cho createTable. Nếu thực hiện rollback thử, xác minh bảng bị xóa đúng và đánh giá tác động mất dữ liệu.

**Bước 6 — Kiểm tra thay đổi modifier.** Trên một bản sao thử nghiệm, điều chỉnh cú pháp modifier rồi quan sát lại **update-sql** và hành vi checksum. Không đem phép thử sửa changeset đã chạy lên staging/production. Kết quả giúp bạn hiểu thay đổi văn bản SQL tác động ra sao trong phiên bản Liquibase thực tế.

**Bước 7 — Ghi kết quả.** Lưu bằng chứng trong hệ thống review/CI: phiên bản Liquibase, DBMS, SQL trước khi áp dụng, kết quả trên database và cách rollback. Đó là căn cứ để chấp nhận một khác biệt SQL có kiểm soát.

## 12. Tiêu chí chấp nhận một modifySql trong dự án

Một modifier nên được review theo các tiêu chí sau:

1. **Lý do rõ ràng:** yêu cầu khác biệt DBMS là gì? Liquibase change type hoặc property có xử lý trực tiếp được không?
2. **Phạm vi nhỏ:** changeset chỉ sinh các câu SQL mà modifier được phép tác động; không làm thay đổi câu không liên quan.
3. **Điều kiện đúng:** dbms/context/label được cấu hình phù hợp; không lẫn điều kiện modifier với điều kiện thực thi changeset.
4. **Tính ổn định:** chuỗi thay thế hoặc regex được kiểm tra trên SQL thực tế của đúng phiên bản Liquibase và DBMS.
5. **Rollback rõ ràng:** applyToRollback được lựa chọn có chủ đích, SQL rollback được xem riêng.
6. **Lịch sử không bị viết lại:** changeset đã triển khai được giữ ổn định; thay đổi mới có changeset mới khi cần.
7. **Kiểm chứng nhiều môi trường:** validate, update-sql, thử update/rollback, kiểm tra schema thực tế và lịch sử DATABASECHANGELOG.
8. **Tích hợp triển khai:** phiên bản công cụ, cấu hình và secret được cấp nhất quán trong Spring Boot hoặc CI/CD; có log để truy vết và kế hoạch xử lý thất bại.

Trong **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, **modifySql** là công cụ xử lý khác biệt **cú pháp SQL đầu ra** ở phạm vi hẹp. Khi dùng với dbms rõ ràng, changeset nhỏ, rollback có kiểm soát và bước xem SQL trước khi chạy, nó giúp một changelog chung phục vụ nhiều môi trường mà vẫn giữ thay đổi minh bạch. Khi khác biệt trở thành thay đổi hành vi hoặc cấu trúc lớn, hãy chọn changeset chuyên biệt và quy trình migration phù hợp thay vì mở rộng chuỗi thao tác văn bản.

