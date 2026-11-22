# Viết thông báo lỗi rõ ràng và cân nhắc chi phí kiểm tra

Precondition là hàng rào xác minh trạng thái database trước khi Liquibase áp dụng một changeset hoặc xử lý changelog. Nhưng một hàng rào chỉ hữu ích khi **thông báo đủ rõ để người vận hành biết vấn đề là gì** và **chi phí kiểm tra đủ phù hợp để không làm chậm hoặc gây quá tải quy trình triển khai**. Một câu báo chung chung như “precondition failed” không giúp phân biệt database sai môi trường, bảng thiếu, dữ liệu vi phạm constraint, quyền đọc metadata thiếu hay một truy vấn kiểm tra quá nặng.

Bài này thuộc chương **Tiền điều kiện** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Mục tiêu của module là quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Trọng tâm của bài là thiết kế thông báo bằng onFailMessage/onErrorMessage, lựa chọn hành vi khi điều kiện không đạt, ước lượng chi phí các loại kiểm tra và biến chúng thành những bước kiểm chứng có thể quan sát trong pipeline.

## 1. Hai tiêu chí chất lượng của một precondition

Một precondition tốt phải thỏa đồng thời hai tiêu chí:

**Chẩn đoán được:** Khi không đạt, người xem log hiểu ngay điều kiện nào sai, đối tượng hoặc phạm vi nào liên quan, trạng thái nào được kỳ vọng và bước điều tra phù hợp. Thông báo không được gây nhầm giữa dữ liệu không phù hợp với lỗi kỹ thuật khi truy vấn.

**Đủ nhẹ và ổn định:** Precondition chỉ thực hiện phần kiểm tra cần thiết, không quét bảng rất lớn vô ích, không tạo thay đổi dữ liệu và không dựa vào điều kiện dễ thay đổi ngoài kiểm soát. Chi phí gồm truy vấn SQL, đọc metadata, tạo snapshot schema, tải database, bộ nhớ, thời gian giữ connection và ảnh hưởng đến pipeline.

Tối ưu một vế không được đánh đổi vế còn lại. Ví dụ, bỏ hết kiểm tra để giảm thời gian có thể khiến migration đổ vỡ muộn hơn với lỗi DDL khó khôi phục. Ngược lại, để một sqlCheck quét toàn bộ hàng trăm triệu bản ghi trước mọi lần khởi động ứng dụng có thể làm giảm tính sẵn sàng.

### 1.1. Những câu hỏi cần trả lời trước khi viết kiểm tra

- Điều kiện bảo vệ thao tác nào, ở cấp changelog hay changeset?
- Điều kiện có thực sự cần thiết hay Liquibase đã theo dõi trạng thái này bằng lịch sử changeset?
- Nếu sai, muốn dừng triển khai hay có trường hợp hợp lệ để bỏ qua?
- Người trực vận hành có thể thực hiện hành động nào an toàn sau khi đọc thông báo?
- Có cách kiểm tra cùng ý nghĩa nhưng ít đọc dữ liệu hoặc metadata hơn không?
- Chi phí tăng thế nào khi số đối tượng hoặc số dòng dữ liệu lớn lên?
- Trên database mới và database đã có dữ liệu, điều kiện có cùng ngữ nghĩa không?

## 2. Phân biệt lỗi điều kiện với lỗi khi đánh giá

Liquibase phân biệt hai tình huống, vì cách xử lý và thông báo phù hợp là khác nhau.

| Tình huống | Ý nghĩa | Ví dụ | Hướng điều tra |
|---|---|---|---|
| Precondition failed | Phép kiểm tra chạy được nhưng kết quả không thỏa yêu cầu | sqlCheck mong đợi 0 nhưng trả 12; bảng bắt buộc không tồn tại | Xác minh trạng thái schema/dữ liệu, migration tiền đề |
| Precondition error | Không đánh giá được phép kiểm tra như dự kiến | SQL sai cú pháp; thiếu quyền đọc metadata; lỗi kết nối | Kiểm tra cú pháp, quyền, JDBC, schema, DBMS và logs |

Ví dụ: trước khi thêm NOT NULL cho orders.shipping_address, một truy vấn đếm các bản ghi có shipping_address NULL trả về 8. Đó là **failed**: truy vấn hoạt động nhưng dữ liệu chưa sẵn sàng.

Nếu truy vấn tương tự lỗi vì bảng orders chưa tồn tại, đó là **error**: không thể tính kết quả đúng/sai theo cách mong đợi. Không nên biến lỗi này thành cảnh báo chung để migration tiếp tục.

Hai nhánh thường được cấu hình qua **onFail** và **onError**. Thông báo người dùng tương ứng là **onFailMessage** và **onErrorMessage**.

## 3. onFailMessage và onErrorMessage làm gì?

Các thuộc tính sau được khai báo trên khối preConditions trong các định dạng hỗ trợ, chẳng hạn XML và YAML:

- **onFail:** Hành vi khi điều kiện kiểm tra không đạt, ví dụ HALT hoặc WARN.
- **onError:** Hành vi khi có lỗi đánh giá điều kiện.
- **onFailMessage:** Văn bản chẩn đoán bổ sung cho tình huống điều kiện không đạt.
- **onErrorMessage:** Văn bản chẩn đoán bổ sung cho tình huống đánh giá điều kiện bị lỗi.

**Thông báo không thay thế hành vi.** Việc đặt onFailMessage dễ hiểu không làm một migration an toàn nếu onFail lại đặt thành WARN rồi tiếp tục thực thi DDL không đủ tiền đề. Ngược lại, HALT có thể dừng đúng nhưng nếu message mơ hồ, người vận hành vẫn phải lần mò lâu.

Tùy phiên bản Liquibase và cách gọi, log có thể trình bày thông báo tùy chỉnh cùng nội dung chẩn đoán từ engine. Không nên dựa vào một định dạng dòng log cố định để parse. Cần kiểm chứng cách thông báo xuất hiện với runtime và pipeline thật.

### 3.1. Ví dụ XML ở cấp changeset

~~~xml
<changeSet id="2026-001-require-shipping-address" author="database-team">
    <preConditions
        onFail="HALT"
        onError="HALT"
        onFailMessage="MIG-ADDR-001: Con don hang thieu shipping_address; hoan tat backfill truoc khi them NOT NULL."
        onErrorMessage="MIG-ADDR-002: Khong kiem tra duoc du lieu orders; xac minh bang, schema va quyen SELECT.">

        <tableExists tableName="orders"/>
        <columnExists tableName="orders" columnName="shipping_address"/>
        <sqlCheck expectedResult="0">
            SELECT COUNT(*) FROM orders WHERE shipping_address IS NULL
        </sqlCheck>
    </preConditions>

    <addNotNullConstraint
        tableName="orders"
        columnName="shipping_address"
        columnDataType="VARCHAR(255)"/>
</changeSet>
~~~

Thông điệp đã có mã lỗi, đối tượng liên quan, trạng thái mong đợi và hành động phù hợp. Trong ví dụ, message được viết không dấu để tránh sự cố encoding của các hệ thống log cũ; với dự án dùng UTF-8 đầu cuối có thể viết tiếng Việt có dấu hoàn toàn bình thường.

Nhưng vẫn có một hạn chế: nếu tableExists không đạt, thông điệp onFail ở trên lại chỉ nói về dữ liệu shipping_address NULL. Để thông báo chính xác hơn, hãy tách các giả định khác nhau thành những bước kiểm tra hoặc thiết kế thông báo đủ bao quát. Các thuộc tính onFailMessage/onErrorMessage gắn với khối preConditions, không tự tạo message riêng cho từng điều kiện con.

### 3.2. Ví dụ YAML

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-002-add-customer-email-index
      author: database-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - onFailMessage: "MIG-IDX-001: Khong the tao index; can bang customer va chua co index idx_customer_email."
        - onErrorMessage: "MIG-IDX-002: Loi kiem tra metadata index; xac minh schema, quyen va ket noi database."
        - tableExists:
            tableName: customer
        - not:
            - indexExists:
                tableName: customer
                indexName: idx_customer_email
      changes:
        - createIndex:
            tableName: customer
            indexName: idx_customer_email
            columns:
              - column:
                  name: email
~~~

Khi YAML chứa dấu hai chấm trong một giá trị thông báo, nên bao chuỗi trong dấu nháy để tránh parser hiểu sai. Với thông điệp dài, có thể dùng YAML block scalar và kiểm tra kết quả log ở runtime đang dùng.

### 3.3. Precondition ở cấp changelog

Nếu toàn bộ changelog chỉ được thiết kế cho PostgreSQL, có thể viết thông điệp ngay ở cấp changelog:

~~~xml
<preConditions
    onFail="HALT"
    onError="HALT"
    onFailMessage="MIG-ENV-001: Changelog nay chi ho tro PostgreSQL; xac nhan JDBC URL va DBMS truoc khi deploy."
    onErrorMessage="MIG-ENV-002: Khong xac dinh duoc DBMS; kiem tra ket noi va quyen truy cap.">
    <dbms type="postgresql"/>
</preConditions>
~~~

Thông điệp tại đây phù hợp vì điều kiện bảo vệ **toàn bộ phạm vi changelog**. Không nên dùng precondition cấp changelog để kiểm tra “bảng orders chưa tồn tại” trong một changelog còn phải triển khai các lần nâng cấp sau. Trên database đã chạy migration tạo orders, điều kiện đó sẽ không còn đúng và có thể chặn các changeset mới.

## 4. Công thức viết thông báo có thể hành động

Một thông báo tốt có thể theo cấu trúc:

~~~text
[Mã kiểm tra] Không thể <thao tác hoặc mục tiêu>.
Điều kiện yêu cầu: <trạng thái được mong đợi>.
Đối tượng/phạm vi: <tên schema, bảng, cột hoặc migration>.
Hành động: <bước xác minh hoặc khắc phục an toàn>.
~~~

Không cần ép mọi thông báo thành bốn câu dài. Một thông báo một hoặc hai câu vẫn tốt nếu đủ thông tin. Với điều kiện cấp changelog, nên nhắc DBMS hoặc phạm vi chung; với changeset, nhắc đối tượng và thao tác bị bảo vệ.

| Thông báo chưa tốt | Vấn đề | Thông báo tốt hơn |
|---|---|---|
| Precondition failed | Không biết điều kiện nào sai | MIG-ORD-001: Chưa thể thêm NOT NULL vào orders.shipping_address; còn bản ghi NULL. Hoàn tất backfill, kiểm tra lại rồi triển khai |
| Invalid database | Quá chung, có thể hiểu là kết nối hỏng | MIG-ENV-001: Changelog yêu cầu PostgreSQL; kiểm tra JDBC URL và profile triển khai |
| Cannot create index | Không biết đối tượng nào hoặc thiếu gì | MIG-IDX-001: Chưa tạo được idx_customer_email; xác nhận customer tồn tại và index cùng tên chưa có |
| Unknown SQL error | Không chỉ rõ khu vực điều tra | MIG-CHECK-002: Không chạy được truy vấn kiểm tra orders; kiểm tra schema, quyền SELECT và SQL theo phiên bản PostgreSQL |

### 4.1. Nên có gì trong message?

- **Mã chẩn đoán ổn định:** ví dụ MIG-ORD-001 để tìm trong log, runbook và PR.
- **Mục tiêu bị chặn:** chẳng hạn thêm constraint, tạo index, backfill hay tạo bảng.
- **Điều kiện mong đợi:** không có NULL, bảng tồn tại, DBMS là PostgreSQL.
- **Phạm vi an toàn:** tên bảng/cột/schema, ID changeset nếu hữu ích.
- **Hướng xử lý:** kiểm tra trạng thái trước, sau đó sửa dữ liệu hoặc migration rồi chạy lại có kiểm soát.

### 4.2. Không nên có gì trong message?

- Mật khẩu, token, chuỗi JDBC chứa credentials hoặc giá trị nhạy cảm từ dữ liệu thật.
- Toàn bộ bản ghi khách hàng hoặc email/địa chỉ thực tế.
- Khẳng định dữ liệu đã được tự động sửa nếu precondition chỉ đọc.
- Khuyến nghị nguy hiểm như xóa DATABASECHANGELOG, đổi checksum hoặc đổi sang MARK_RAN để bỏ qua lỗi.
- Kết quả số liệu được đoán trước mà runtime không tự cung cấp.

**Thông điệp tùy chỉnh thường là văn bản tĩnh.** Đừng mặc định rằng onFailMessage có thể thay biến thành kết quả thực tế của sqlCheck, thời gian truy vấn hoặc giá trị database. Nếu muốn log số bản ghi lỗi, hãy có bước kiểm tra/quan sát riêng được phân quyền phù hợp; đừng sao chép dữ liệu nhạy cảm vào thông báo.

## 5. Chọn hành vi đi kèm: HALT, WARN, CONTINUE, MARK_RAN

Thông báo rõ ràng phải đi cùng hành vi đúng khi điều kiện không đạt.

| Hành vi | Kết quả | Phù hợp khi | Rủi ro nếu dùng sai |
|---|---|---|---|
| HALT | Dừng triển khai | Điều kiện bắt buộc trước DDL/DML, dữ liệu nhạy cảm, ràng buộc schema | Làm chậm phát hành nhưng giúp tránh thay đổi sai |
| WARN | Cảnh báo và tiếp tục | Kiểm tra chỉ mang tính thông tin; tiếp tục là chủ đích đã được duyệt | DDL/DML có thể chạy trong trạng thái không phù hợp |
| CONTINUE | Bỏ qua changeset tại lần chạy hiện tại | Changeset tùy chọn, độc lập, có thể xét lại | Bước sau có thể chạy trong khi phụ thuộc chưa được tạo |
| MARK_RAN | Không chạy change nhưng ghi lịch sử changeset đã được xử lý | Baseline được kiểm chứng đầy đủ | Tạo lịch sử “đã xong” trong khi schema thực tế thiếu |

Ở cấp changelog, các lựa chọn phổ biến được hỗ trợ là HALT và WARN; CONTINUE và MARK_RAN dành cho cấp changeset. Tương tự, phân biệt onFail và onError thay vì đặt WARN cho mọi trường hợp.

Nếu một kiểm tra có nhiệm vụ ngăn một migration phá dữ liệu, **HALT là lựa chọn nên được cân nhắc đầu tiên**. WARN chỉ phù hợp khi cả điều kiện sai lẫn việc chạy tiếp đều đã được thiết kế trước.

### Ví dụ nguy hiểm

Giả sử changeSet cần bảng customer, nhưng precondition tableExists không đạt và onFail=WARN. Tên bảng chưa tồn tại nhưng changeSet addColumn vẫn được thực hiện; lỗi DDL xảy ra muộn hơn với ít ngữ cảnh hơn.

Ngược lại, onFail=MARK_RAN có thể khiến changeset được ghi lịch sử mà cột không được thêm. Những changeset về sau phụ thuộc cột đó sẽ có nguy cơ thất bại hoặc tạo dữ liệu sai.

## 6. Chi phí kiểm tra đến từ đâu?

Precondition không miễn phí. Tổng chi phí có thể được hiểu theo các lớp:

~~~text
Tổng chi phí kiểm tra
  = chi phí xác định changeset cần xét
  + chi phí lấy metadata / snapshot database
  + chi phí truy vấn SQL hoặc đọc dữ liệu
  + chi phí truyền dữ liệu qua JDBC
  + chi phí phối hợp quyền, transaction và trạng thái DB
  + chi phí ghi log / chẩn đoán lỗi
~~~

Đây là mô hình để phân tích, không phải công thức đo chính xác. Mức ảnh hưởng phụ thuộc DBMS, phiên bản Liquibase, driver, kích thước catalog, số lượng bảng/cột/index, độ trễ mạng và tình trạng database.

Đặc biệt, nhiều precondition dựa trên metadata có thể yêu cầu Liquibase tạo hoặc truy cập **database snapshot** để xác minh đối tượng. Snapshot catalog trên database lớn có thể tốn thời gian đáng kể, ngay cả khi biểu thức kiểm tra nhìn rất ngắn.

### 6.1. So sánh định tính

| Loại kiểm tra | Chi phí tiềm năng | Điều cần đánh giá |
|---|---|---|
| dbms | Thường thấp | Lấy thông tin DBMS từ kết nối |
| runningAs | Thường thấp | Đọc thông tin tài khoản/kết nối |
| changeSetExecuted | Thường tập trung vào lịch sử Liquibase | Số lượng bản ghi DATABASECHANGELOG, tần suất |
| tableExists / columnExists | Có thể cần đọc metadata/snapshot | Số lượng đối tượng trong schema, quyền metadata |
| indexExists / foreignKeyConstraintExists | Có thể cần snapshot chi tiết hơn | Số lượng index/FK, cấu trúc schema |
| sqlCheck theo khóa có index | Có thể thấp nếu kế hoạch truy vấn phù hợp | Index, selectivity, locking, mạng |
| sqlCheck bằng COUNT trên bảng rất lớn | Có thể cao | Phạm vi quét, điều kiện lọc, thống kê, dữ liệu |
| customPrecondition | Phụ thuộc hoàn toàn implementation | I/O, truy vấn, timeout, side effect |

Bảng này không đưa ra thứ hạng cứng cho mọi database. Một sqlCheck tối ưu trên index đôi khi nhẹ hơn snapshot metadata; một sqlCheck viết tệ có thể đắt hơn rất nhiều. Phải đo trên hệ thống đại diện.

### 6.2. Không nhân chi phí sai cách

Không phải cứ changelog có 500 changeset thì 500 precondition cấp changeset sẽ luôn chạy mỗi lần deploy. Trong chế độ update thông thường, những changeset đã ghi nhận là hoàn thành thường được Liquibase bỏ qua; precondition cục bộ chủ yếu liên quan đến changeset đang được xét để chạy. runAlways, runOnChange và các lựa chọn thực thi khác có ngữ nghĩa riêng.

Trong khi đó, precondition cấp changelog có phạm vi chung nên không được giả định nó chỉ kiểm tra một lần suốt vòng đời ứng dụng. Với một changelog được xử lý nhiều lần và có nhiều pipeline, chi phí của kiểm tra chung vẫn đáng được xem xét.

## 7. COUNT(*) và EXISTS: cùng mục tiêu, chi phí có thể khác

Giả sử cần đảm bảo không có đơn hàng với shipping_address NULL trước khi thêm NOT NULL. Cách trực tiếp:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE shipping_address IS NULL;
~~~

Ưu điểm: trả chính xác số bản ghi vi phạm, hữu ích khi muốn báo cáo hoặc lập kế hoạch backfill. Nhược điểm: để tính chính xác tổng số dòng, DBMS có thể phải đọc tất cả dòng phù hợp, dù chỉ cần biết có ít nhất một dòng vi phạm.

Nếu chỉ cần câu trả lời **có vi phạm hay không**, có thể dùng EXISTS. Trên PostgreSQL, chuyển boolean về 0/1 để thuận tiện cho sqlCheck:

~~~sql
SELECT CASE
         WHEN EXISTS (
           SELECT 1
           FROM orders
           WHERE shipping_address IS NULL
         )
         THEN 1
         ELSE 0
       END;
~~~

Khi không có bản ghi vi phạm, kết quả là 0. Nếu có ít nhất một bản ghi, kết quả là 1. Đây là điều kiện đủ để chặn addNotNullConstraint mà không cần biết chính xác số dòng vi phạm.

EXISTS thường cho phép engine dừng tìm kiếm khi đã thấy bản ghi phù hợp. Nhưng **không có bảo đảm truy vấn sẽ rẻ**: nếu không có index và dữ liệu phù hợp nằm ở cuối bảng, engine có thể vẫn phải quét nhiều trang. Trình tối ưu hóa, thống kê và phân bố dữ liệu quyết định kế hoạch thực tế.

### 7.1. Ví dụ precondition nhẹ hơn bằng sqlCheck

~~~xml
<changeSet id="2026-003-orders-address-required" author="database-team">
    <preConditions
        onFail="HALT"
        onError="HALT"
        onFailMessage="MIG-ORD-003: orders.shipping_address con gia tri NULL; can backfill truoc khi them NOT NULL."
        onErrorMessage="MIG-ORD-004: Khong danh gia duoc kiem tra orders.shipping_address; xem quyen, schema va SQL.">

        <sqlCheck expectedResult="0"><![CDATA[
            SELECT CASE
                     WHEN EXISTS (
                       SELECT 1
                       FROM orders
                       WHERE shipping_address IS NULL
                     )
                     THEN 1
                     ELSE 0
                   END
        ]]></sqlCheck>
    </preConditions>

    <addNotNullConstraint
        tableName="orders"
        columnName="shipping_address"
        columnDataType="VARCHAR(255)"/>
</changeSet>
~~~

Ví dụ này giả định bảng orders và cột shipping_address đã tồn tại do những changeset tiền đề. Nếu cần thông báo khác nhau cho “thiếu cột” và “còn dữ liệu NULL”, nên tách kiểm tra hoặc có bước preflight riêng thay vì gộp tất cả vào một message không chính xác.

### 7.2. Khi nào COUNT(*) vẫn phù hợp?

- Cần số lượng chính xác để quyết định backfill theo batch hoặc hiển thị dashboard chẩn đoán.
- Bảng nhỏ, truy vấn đã được đo và thời gian phù hợp.
- Kiểm tra phân bố dữ liệu là yêu cầu có chủ đích.
- Câu truy vấn sử dụng index/kế hoạch tối ưu và đáp ứng giới hạn thời gian của môi trường.

Không tối ưu dựa trên tên toán tử một cách máy móc. Đo kế hoạch truy vấn và tài nguyên sử dụng mới là cơ sở ra quyết định.

## 8. Dùng EXPLAIN và phép đo thay vì phỏng đoán

Trên PostgreSQL, kiểm tra kế hoạch truy vấn bằng EXPLAIN trước khi đưa sqlCheck vào pipeline:

~~~sql
EXPLAIN
SELECT CASE
         WHEN EXISTS (
           SELECT 1
           FROM orders
           WHERE shipping_address IS NULL
         )
         THEN 1 ELSE 0
       END;
~~~

Các tín hiệu cần quan sát:

- Seq Scan, Index Scan hay Index Only Scan?
- Số dòng ước lượng và điều kiện lọc có hợp lý không?
- Truy vấn đọc bao nhiêu bảng, join hay subquery?
- Kế hoạch có thay đổi đáng kể giữa database mới và dữ liệu production-like không?
- Khi chạy thật trên môi trường thử nghiệm, thời gian, CPU, I/O và lock có nằm trong ngân sách triển khai không?

EXPLAIN không chạy truy vấn theo cách EXPLAIN ANALYZE làm trên PostgreSQL. EXPLAIN ANALYZE có thể thực thi truy vấn và phát sinh chi phí thật, vì vậy chỉ dùng trên môi trường được phép với câu lệnh chỉ đọc và hiểu rõ tác động. Không chạy thử một truy vấn nặng trên production chỉ để tìm hiểu vì sao precondition chậm.

**Ngân sách thời gian:** Dự án nên định nghĩa mức thời gian chấp nhận được cho bước kiểm tra dựa trên quy mô và cửa sổ deploy thực tế. Không có ngưỡng cố định phù hợp cho mọi bảng và mọi hệ thống. Một kiểm tra 2 giây có thể chấp nhận được khi chạy một lần trong deploy, nhưng không phù hợp nếu chạy lặp nhiều lần trong đường khởi động của các replica.

## 9. Giảm chi phí metadata snapshot

Những precondition như tableExists, columnExists, indexExists, foreignKeyConstraintExists rất dễ đọc, nhưng trên một số DBMS chúng có thể sử dụng metadata lookup hoặc snapshot. Một snapshot có thể phải liệt kê nhiều đối tượng hơn phần mà điều kiện cần.

Các biện pháp cần cân nhắc:

1. **Chỉ kiểm tra những gì thật sự cần:** Không lặp lại mười lần kiểm tra cùng một bảng nếu lịch sử changeset đã bảo đảm nó được tạo.
2. **Giới hạn schema rõ ràng:** Với điều kiện hỗ trợ schemaName, truyền schema phù hợp; không để mặc định vô tình quét hoặc tìm nhầm schema khác.
3. **Phân biệt điều kiện tiền đề và kiểm tra drift:** Precondition không phải hệ thống giám sát toàn bộ schema sau mỗi deploy.
4. **Đo trên database có catalog lớn:** Một kiểm tra nhanh trên lab với hai bảng không đại diện cho production có hàng nghìn đối tượng.
5. **Cân nhắc truy vấn catalog đặc thù có kiểm chứng:** Khi một metadata check tốn kém và dự án chỉ hỗ trợ một DBMS, sqlCheck tối ưu trên catalog hệ thống có thể là lựa chọn, nhưng phải đánh đổi khả năng di động và kiểm soát quyền.

Không nên thay thế hàng loạt precondition built-in bằng truy vấn SQL tùy tiện chỉ vì nghe nói snapshot chậm. Built-in thường giúp biểu diễn ý định rõ và hỗ trợ nhiều DBMS. Chỉ tối ưu sau khi có bằng chứng về chi phí.

### Ví dụ truy vấn catalog trên PostgreSQL

Trong trường hợp có lý do kỹ thuật được kiểm chứng, PostgreSQL có hàm to_regclass để kiểm tra sự tồn tại của quan hệ theo tên được cung cấp:

~~~sql
SELECT CASE
         WHEN to_regclass('app.customer') IS NULL
         THEN 0 ELSE 1
       END;
~~~

Đây là ví dụ **đặc thù PostgreSQL**, không thay thế phổ quát cho tableExists: loại đối tượng được nhận diện, schema và quyền phải được kiểm tra đúng yêu cầu. Hãy dùng khi đã đo chi phí/độ chính xác và có thử nghiệm ở các môi trường liên quan.

## 10. Thứ tự điều kiện và cơ chế dừng sớm

Liquibase cho phép kết hợp điều kiện bằng AND, OR và NOT. Các nhóm logic có thể dừng đánh giá khi đã xác định được kết quả.

- Với AND, nếu một điều kiện không đạt, các điều kiện còn lại có thể không cần đánh giá.
- Với OR, nếu một điều kiện đạt, các điều kiện còn lại có thể không cần đánh giá.
- NOT đảo kết quả của điều kiện bên trong.

Ví dụ, trước khi đếm dữ liệu, xác nhận đúng DBMS và bảng hiện hữu:

~~~xml
<preConditions onFail="HALT" onError="HALT">
    <and>
        <dbms type="postgresql"/>
        <tableExists tableName="orders"/>
        <sqlCheck expectedResult="0">
            SELECT COUNT(*) FROM orders WHERE shipping_address IS NULL
        </sqlCheck>
    </and>
</preConditions>
~~~

Đặt phép kiểm tra đơn giản trước phép kiểm tra nặng là nguyên tắc hợp lý trong nhiều tình huống. Nhưng không nên coi đó là bảo đảm tiết kiệm chi phí tuyệt đối: cách engine đánh giá điều kiện, truy vấn metadata và việc xử lý lỗi phụ thuộc phiên bản và runtime. Đặc biệt, tableExists cũng có thể kéo theo chi phí snapshot.

Một ràng buộc quan trọng: **thứ tự kiểm tra phải phục vụ tính đúng đắn trước rồi mới tới tối ưu**. Nếu một lỗi thiếu bảng cần thông báo riêng, việc gộp vào một onFailMessage chung có thể đánh mất ý nghĩa chẩn đoán. Nếu thứ tự làm hệ thống bỏ qua lỗi mà reviewer muốn phát hiện, cần thiết kế lại.

### 10.1. Đừng dựa vào side effect của precondition

Precondition nên là phép kiểm tra. Không dùng SQL trong sqlCheck để INSERT, UPDATE, DELETE hoặc tạo đối tượng với hy vọng nó sẽ “chuẩn bị dữ liệu”. Những thao tác làm thay đổi trạng thái thuộc về changeset được version control, có lịch sử và rollback/forward-fix thích hợp.

## 11. Khi nào nên tách điều kiện thành nhiều changeset?

Một khối preConditions chỉ có một onFailMessage và một onErrorMessage áp dụng cho nhóm điều kiện trong khối. Nếu nhóm chứa “bảng tồn tại”, “cột tồn tại”, “dữ liệu sạch” và “index chưa tồn tại”, một thông báo chung sẽ khó đủ chính xác.

Có thể giải quyết bằng:

- Tách những thay đổi có trách nhiệm riêng thành nhiều changeset nhỏ.
- Đặt mỗi precondition sát với thao tác được bảo vệ.
- Đưa bước kiểm tra dữ liệu phức tạp thành preflight ở CI trước khi chạy update, có log/chẩn đoán chi tiết hơn, sau đó vẫn giữ precondition ngắn gọn để chặn trạng thái không an toàn.
- Dùng mã kiểm tra tĩnh gắn với changeset để tra cứu runbook.

Ví dụ quy trình thay đổi email:

~~~text
Bước 1: thêm cột email mới (nếu chưa có)
Bước 2: backfill dữ liệu cũ theo batch
Bước 3: kiểm tra không còn NULL
Bước 4: áp NOT NULL
Bước 5: chuyển ứng dụng sang schema mới
~~~

Một quy trình lớn như vậy không nên ép toàn bộ vào một precondition và một thông báo. Tách giai đoạn còn giúp kiểm soát khả năng tương thích giữa phiên bản ứng dụng cũ và mới theo chiến lược expand–migrate–contract.

## 12. Chi phí và độ chính xác trên các môi trường

Precondition có thể chạy tốt ở local nhưng có đặc tính khác ở staging hoặc production:

| Khác biệt môi trường | Rủi ro | Cách xác minh |
|---|---|---|
| Dữ liệu ít ở local, nhiều ở production | COUNT hoặc quét bảng quá chậm | Thử trên dữ liệu đại diện, kiểm tra EXPLAIN và thời gian |
| Schema public ở local, app ở production | Kiểm tra nhầm đối tượng hoặc không thấy bảng | Khai báo đúng schema, kiểm tra search_path |
| Tài khoản DDL khác nhau | onError do thiếu quyền metadata hoặc SELECT | Thử bằng tài khoản thực tế của pipeline |
| DBMS hoặc phiên bản khác | SQL đặc thù không chạy hoặc cho kết quả khác | Xác minh trên các DBMS được hỗ trợ |
| Nhiều replica khởi động | Kiểm tra được kích hoạt trong nhiều tiến trình nếu cấu hình migration không rõ | Quy định tiến trình migration, quan sát log |
| Dữ liệu vẫn thay đổi trong deploy | Điều kiện đúng lúc kiểm tra nhưng sai trước khi DDL | Phối hợp rollout ứng dụng, transaction, khóa và data migration |

Precondition kiểm tra trạng thái tại thời điểm đánh giá. Giữa phép kiểm tra và thao tác tiếp theo có thể có **race condition**. Ví dụ không có email NULL lúc sqlCheck chạy nhưng ứng dụng ghi thêm dòng NULL ngay trước khi addNotNullConstraint. Bảng khóa DATABASECHANGELOGLOCK điều phối các tiến trình Liquibase, không thay thế cơ chế kiểm soát ghi dữ liệu của ứng dụng.

Vì vậy, việc kiểm tra rẻ và kết quả đúng vẫn cần đi cùng kế hoạch tương thích ngược, giới hạn ghi hoặc giai đoạn chuyển đổi rõ ràng.

## 13. Tác động đến lịch sử changeset và checksum

Liquibase nhận diện changeset chủ yếu qua ID, author và đường dẫn changelog (hoặc logicalFilePath khi được cấu hình). DATABASECHANGELOG ghi lịch sử thực thi và checksum.

Trong chế độ update thông thường, changeset đã ghi nhận là hoàn thành thường không được chạy lại, và precondition cục bộ của nó không phải một kiểm tra drift liên tục. Những cơ chế runAlways hoặc runOnChange có ngữ nghĩa riêng, cần hiểu trước khi sử dụng.

Điều cần nhớ:

- Precondition failed không đồng nghĩa với checksum mismatch.
- Một sqlCheck thành công không chứng minh nội dung changeset trước đây không bị sửa.
- MARK_RAN có thể để lại lịch sử khác với thay đổi đã thực hiện thật.
- CONTINUE có thể khiến thay đổi chưa được áp dụng và được xét lại vào lần chạy sau.
- Không tự sửa DATABASECHANGELOG để cho qua lỗi, cũng không tùy tiện clear checksum hoặc đổi định danh tệp để ép chạy lại.

Trên PostgreSQL có thể xem lịch sử:

~~~sql
SELECT id, author, filename, exectype, dateexecuted, orderexecuted
FROM databasechangelog
ORDER BY orderexecuted;
~~~

Nếu một message nói đối tượng đã tồn tại nhưng changeset chưa được ghi nhận, cần điều tra khả năng tạo thủ công, baseline, migration chồng lấn hoặc tệp đã đổi path. Không biến onFail thành MARK_RAN nếu chưa xác nhận toàn bộ đối tượng và ràng buộc tương ứng đã đúng.

## 14. Thông báo lỗi trong Spring Boot và pipeline CI/CD

Khi Spring Boot được cấu hình chạy Liquibase lúc khởi động, precondition HALT có thể làm ứng dụng không khởi động thành công. Đây thường là hành vi nên có nếu schema chưa đạt trạng thái an toàn. Tuy nhiên, log phải cho người vận hành biết rõ vấn đề thuộc database/migration chứ không phải lỗi HTTP hay ứng dụng nghiệp vụ.

Một pipeline nên ghi được:

- Tên môi trường và job/deployment ID được phép công bố.
- Định danh changelog và changeset liên quan.
- Mã thông báo do nhóm quy ước.
- onFail hay onError được kích hoạt.
- Kết quả triển khai và bước đối chiếu DATABASECHANGELOG.
- Đường dẫn tới runbook hoặc quy trình điều tra tương ứng.

Không đưa mật khẩu, token hoặc toàn bộ JDBC URL có credentials vào log. Nếu muốn log truy vấn kiểm tra, hãy kiểm soát việc truy vấn có chứa literal nhạy cảm hay không.

### Trình tự kiểm chứng khuyến nghị

1. Review thông báo: người trực on-call có hiểu và biết hành động tiếp theo không?
2. Chạy Liquibase validate với runtime/cấu hình thực tế.
3. Xem status --verbose và update-sql trước khi thực thi, nhưng không mặc định preview sẽ đo đủ chi phí precondition.
4. Thử trên database trống và database đã chạy phiên bản trước.
5. Chủ động tạo trường hợp **fail** và **error** để xác nhận hai message khác nhau.
6. Đo chi phí các sqlCheck/metadata check trên dữ liệu đại diện.
7. Chạy update trong lab và đối chiếu schema, dữ liệu và DATABASECHANGELOG.
8. Kiểm tra log CI/CD và xác minh mã lỗi cùng hướng dẫn xử lý xuất hiện đúng.

Một số lệnh CLI thường dùng sau khi đã cấu hình kết nối:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
liquibase update
~~~

Tên lệnh/tùy chọn cần đối chiếu phiên bản Liquibase đang dùng. Lệnh update áp dụng thay đổi thật, nên chỉ chạy trên database đích đã được xác minh. Mức độ đánh giá precondition trong các chế độ validate, status và preview có thể khác nhau; không xem các chế độ đó là bản sao hoàn hảo của update.

## 15. Troubleshooting: chậm, sai thông báo hay lỗi quyền?

| Hiện tượng | Khả năng gây ra | Hướng xử lý |
|---|---|---|
| Log chỉ nói precondition failed | Thiếu onFailMessage hoặc message quá chung | Thêm mã kiểm tra, trạng thái mong đợi và hành động khắc phục |
| Báo dữ liệu NULL nhưng thực tế bảng không tồn tại | Gộp nhiều điều kiện cùng một onFailMessage | Tách bước hoặc viết message bao quát đúng sự thật |
| Chỉ production chậm | Dữ liệu/catalog lớn, mạng chậm, lock | Đo query plan và snapshot/metadata trên môi trường đại diện |
| sqlCheck đếm hàng rất lâu | COUNT(*) quét quá nhiều dòng | Xem xét EXISTS/CASE và index khi chỉ cần biết có vi phạm |
| onError xuất hiện thay vì onFail | SQL/metadata check bị lỗi, thiếu quyền, sai schema | Kiểm tra exception, truy vấn và user kết nối |
| tableExists nhanh ở lab nhưng chậm ở hệ lớn | Metadata snapshot/độ lớn catalog khác biệt | Giới hạn schema, tránh lặp, cân nhắc tối ưu có đo đạc |
| WARN nhưng migration vẫn thất bại | Điều kiện bắt buộc bị biến thành cảnh báo | Dùng HALT và khắc phục trạng thái tiền đề |
| MARK_RAN khiến migration sau lỗi | Changeset được ghi lịch sử mà đối tượng chưa được tạo | Đối chiếu thực trạng database và xử lý bằng quy trình migration sửa chữa |
| CI pass, Spring Boot startup fail | Khác JDBC profile, quyền hoặc context/label | Dùng cùng cấu hình kiểm chứng và artifact |
| Precondition pass nhưng DDL fail | Race condition, dữ liệu thay đổi, quyền/transaction | Kiểm tra thời gian triển khai, khóa, tương thích ứng dụng |

Nếu lỗi đến từ database đang có dữ liệu sai, không nên chỉ thay onFailMessage để thông báo biến mất. Cần sửa dữ liệu hoặc migration và thử lại. Nếu bottleneck là chi phí kiểm tra, tối ưu hóa phải giữ nguyên ý nghĩa điều kiện; một phép kiểm tra nhanh nhưng bỏ sót dữ liệu vi phạm không còn là precondition hữu ích.

## 16. Bài thực hành: viết message và đo chi phí

Dùng một PostgreSQL lab tách biệt khỏi production.

**Bài A — Kiểm tra thông báo fail và error.** Tạo bảng orders có cột shipping_address. Viết changeset addNotNullConstraint với sqlCheck expectedResult=0 và onFailMessage/onErrorMessage khác nhau. Chèn một dòng NULL để kích hoạt fail; sau đó trên database lab khác, cố tình dùng sai tên cột trong sqlCheck để quan sát error. Ghi lại nội dung log xuất hiện và giải thích tại sao đây là hai nguyên nhân khác nhau.

**Bài B — So sánh COUNT và EXISTS.** Tạo dữ liệu thử có số dòng đủ đại diện, chạy EXPLAIN cho COUNT(*) và CASE WHEN EXISTS, xem kế hoạch. Đo thời gian trong môi trường thử nghiệm, thử cả khi không có bản ghi vi phạm và khi có một bản ghi vi phạm. Không đặt sẵn kết luận EXISTS luôn nhanh; phân tích điều kiện thực tế làm một truy vấn tiết kiệm hơn.

**Bài C — Đánh giá metadata.** Trên schema có nhiều bảng và index trong lab, dùng precondition tableExists hoặc indexExists và so sánh thời gian tổng thể của lần kiểm chứng. Quan sát log/timing ở cùng phiên bản Liquibase. Thử giới hạn schemaName và kiểm tra nó còn đánh giá đúng đối tượng không.

**Bài D — Kiểm tra rủi ro WARN và MARK_RAN.** Trên một changeset hoàn toàn tùy chọn và độc lập, thử WARN, CONTINUE, MARK_RAN ở cấp phù hợp. So sánh SQL thực sự chạy, lịch sử DATABASECHANGELOG và kết quả update lần tiếp theo. Không dùng thử nghiệm này để bỏ qua constraint cốt lõi.

**Bài E — Review như một người trực on-call.** Đưa log fail (đã loại bỏ dữ liệu nhạy cảm) cho một người khác không viết migration. Họ cần xác định đúng đối tượng, điều kiện mong đợi và bước điều tra đầu tiên mà không cần mở toàn bộ source. Nếu không làm được, hãy sửa thông điệp.

## 17. Checklist trước khi merge changeset có precondition

| Câu hỏi | Điều kiện đạt |
|---|---|
| Phân biệt fail và error rõ ràng? | onFailMessage/onErrorMessage đúng ý nghĩa |
| Thông báo đủ chẩn đoán? | Có đối tượng, kỳ vọng, hành động và mã kiểm tra phù hợp |
| Có rò rỉ bí mật hoặc dữ liệu khách hàng? | Không có credentials, PII, token trong message/log |
| onFail/onError có hợp lý? | Điều kiện bắt buộc dùng HALT hoặc hành vi được duyệt |
| Thông báo nhóm điều kiện có chính xác với mọi nhánh fail? | Không quy sai nguyên nhân cho một điều kiện khác |
| Chi phí metadata có được cân nhắc? | Tránh snapshot/lặp không cần thiết, có đo trên catalog đại diện |
| sqlCheck có truy vấn đủ nhẹ? | Query plan và timing phù hợp với cửa sổ deploy |
| Có kiểm tra schema và quyền đúng đích? | JDBC URL, schemaName, user được xác minh |
| Đã thử fail, error và success? | Có bằng chứng từng kịch bản, log rõ ràng |
| Đã thử fresh install và upgrade? | Không tạo khác biệt ngoài dự kiến giữa môi trường mới/cũ |
| Race condition/transaction/rollback được xem xét? | Có kế hoạch vận hành và phục hồi khi cần |
| Lịch sử Liquibase được giữ nguyên? | Không sửa checksum/ID/path bừa bãi để bỏ qua lỗi |

**Kết luận:** Precondition chất lượng không chỉ trả true/false; nó cung cấp một **lời giải thích đáng tin cậy** khi không thể triển khai và thực hiện phép kiểm tra với **chi phí hợp lý**. Hãy dùng onFailMessage/onErrorMessage để biến lỗi thành hành động cụ thể, ưu tiên HALT cho điều kiện bắt buộc, đo chi phí thay vì suy đoán, và giữ các phép kiểm tra tập trung, chỉ đọc. Khi kết hợp với lịch sử changeset, kiểm chứng trên dữ liệu đại diện, rollback và quy trình CI/CD được điều phối, những thông báo rõ ràng cùng kiểm tra hiệu quả sẽ giảm đáng kể rủi ro vận hành Liquibase.

