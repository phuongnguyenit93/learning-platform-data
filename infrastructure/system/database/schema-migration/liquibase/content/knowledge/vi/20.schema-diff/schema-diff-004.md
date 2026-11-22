# Đọc kết quả đối tượng thiếu, thừa và thay đổi

## 1. Mục tiêu của việc đọc kết quả schema diff

Khi tiếp nhận một database legacy, chuẩn hóa môi trường hoặc kiểm tra drift sau nhiều lần phát hành, nhóm cần biết hai database có cùng cấu trúc ở mức nào. Liquibase cung cấp lệnh **diff** để so sánh một database tham chiếu (*reference*) với database đích (*target*), sau đó báo cáo các đối tượng được nhận diện là thiếu, thừa hoặc có khác biệt.

Kết quả diff rất hữu ích, nhưng dễ bị đọc sai nếu không xác định rõ chiều so sánh. Một đối tượng “missing” không có nghĩa là nó biến mất khỏi mọi database; nó có nghĩa đối tượng tồn tại trong reference nhưng không được tìm thấy trong target theo phạm vi và quy tắc so sánh hiện tại. Tương tự, “unexpected” chỉ ra đối tượng có ở target nhưng không có trong reference. Nếu đảo hai database, hai nhóm này đổi vai trò.

Bài thuộc chương **So sánh lược đồ** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Module hướng dẫn quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Đọc đúng kết quả missing/unexpected/changed giúp nhóm phân biệt drift thật, khác biệt có chủ ý và giới hạn của công cụ trước khi tạo hoặc áp dụng changeset.

Sau bài học, người đọc có thể:

1. Xác định đúng reference, target và chiều diễn giải của báo cáo diff.
2. Phân biệt đối tượng thiếu, thừa và thay đổi; hiểu các ví dụ ở cấp table, column, index, constraint và view.
3. Phân loại khác biệt thành lỗi drift, khác biệt theo môi trường, khác biệt được quản lý ngoài Liquibase hoặc kết quả do phạm vi/quyền so sánh.
4. Đọc chi tiết định nghĩa và đánh giá phụ thuộc thay vì chỉ nhìn tên object.
5. Dùng diff changelog như một bản đề xuất cần review, không phải lệnh tự động sửa database.
6. Xác minh kết quả bằng catalog, DDL, changelog và kiểm thử trên DBMS thực tế.

## 2. Reference và target: xác định chiều so sánh trước

Liquibase diff cần hai phía:

- **Reference database:** phía được dùng làm chuẩn để đối chiếu. Có thể là database nguồn đã được xác nhận, một môi trường chuẩn hoặc trạng thái schema mà nhóm muốn target đạt tới.
- **Target database:** phía được kiểm tra. Đây là database mà nhóm muốn hiểu đang thiếu, thừa hoặc khác gì so với reference.

Ví dụ:

~~~text
Reference: staging đã được phê duyệt
Target:    production cần kiểm tra

Missing   = có trong staging, không thấy trong production
Unexpected= có trong production, không thấy trong staging
Changed   = có ở cả hai phía nhưng định nghĩa khác nhau
~~~

Giả sử:

- Reference có bảng <code>orders</code>, cột <code>status_code</code> và index <code>idx_orders_status</code>.
- Target có bảng <code>orders</code>, chưa có <code>status_code</code>, nhưng có thêm bảng <code>orders_archive</code>.
- Cả hai có cột <code>orders.amount</code>, nhưng precision khác nhau.

Diễn giải theo chiều trên:

| Kết quả | Ví dụ | Ý nghĩa |
|---|---|---|
| Missing | <code>orders.status_code</code> hoặc index có trong reference nhưng không có ở target | Target chưa có đối tượng mong đợi |
| Unexpected | <code>orders_archive</code> chỉ có ở target | Target có đối tượng ngoài reference |
| Changed | <code>orders.amount</code> có ở cả hai nhưng định nghĩa khác | Cần xem chi tiết trường nào khác và khác biệt có chủ ý không |

Nếu đảo target và reference, bảng <code>orders_archive</code> sẽ trở thành missing theo chiều mới, còn cột/index chỉ có ở reference cũ sẽ trở thành unexpected. **Tên nhóm trong báo cáo không tự nói phía nào đúng**; điều đó do vai trò reference/target và mục tiêu của lần so sánh quyết định.

### 2.1. Reference không nhất thiết là production

Reference có thể là:

- Một database đã được phê duyệt làm chuẩn.
- Một môi trường chuẩn bị phát hành, nếu trạng thái của nó đã được kiểm tra.
- Database được tạo mới từ changelog baseline.
- Snapshot hoặc nguồn tham chiếu khác được công cụ hỗ trợ trong cấu hình phù hợp.

Không chọn reference chỉ vì nó mới hơn hoặc có nhiều object hơn. Nếu staging có thay đổi thủ công chưa được review, dùng staging làm chuẩn có thể biến drift thành “thiết kế mong muốn”. Cần xác định nguồn chuẩn trước khi chạy diff.

### 2.2. Diff không tự quyết định database nào đúng

Liquibase báo cáo khác biệt theo hai trạng thái được cung cấp. Công cụ không biết rằng một bảng archive là hợp lệ theo chính sách lưu trữ, hay một index ở production được DBA thêm để đáp ứng tải. Nhóm phải phân loại ý nghĩa của từng khác biệt dựa trên kiến trúc, nghiệp vụ và lịch sử triển khai.

Một báo cáo có nhiều missing không đồng nghĩa target chắc chắn sai. Có thể target là môi trường tối giản được thiết kế có chủ đích. Ngược lại, báo cáo “không có khác biệt” cũng không chứng minh hai hệ thống hoàn toàn tương đương ở mọi mặt.

## 3. Ba nhóm kết quả chính

### 3.1. Missing objects — đối tượng thiếu ở target

Một object được báo cáo missing khi Liquibase nhận diện nó trong reference nhưng không tìm thấy object tương ứng trong target, theo scope và khả năng snapshot hiện tại.

Ví dụ:

- Reference có bảng <code>customer_address</code>, target không có.
- Reference có cột <code>orders.status_code</code>, target thiếu cột đó.
- Reference có foreign key <code>fk_order_customer</code>, target không có constraint tương ứng.
- Reference có view <code>v_monthly_revenue</code>, target chưa có view.

Những nguyên nhân có thể:

1. Migration chưa được chạy ở target.
2. Changeset đã bị bỏ qua bởi DBMS/context/label filter.
3. Target có schema nhưng cấu hình so sánh không đưa schema đó vào scope.
4. Object tồn tại dưới tên hoặc kiểu chữ khác do quy tắc identifier.
5. Snapshot không đọc được object do thiếu quyền hoặc không hỗ trợ loại object.
6. Object bị xóa thủ công hoặc một lần triển khai trước thất bại giữa chừng.

Không tạo ngay một changeset thêm object chỉ dựa trên chữ “missing”. Trước hết phải xác minh target có thực sự cần object đó và có đủ dependency hay không.

### 3.2. Unexpected objects — đối tượng thừa ở target

Một object được báo cáo unexpected khi Liquibase tìm thấy nó trong target nhưng không tìm thấy object tương ứng trong reference.

Ví dụ:

- Target có bảng <code>debug_event</code> mà reference không có.
- Target có index <code>idx_orders_created_tmp</code> chỉ được tạo thủ công để điều tra hiệu năng.
- Target có view hoặc trigger chưa được đưa vào changelog.
- Target có sequence riêng mà reference không có.

Unexpected có thể là:

- Drift do thao tác thủ công hoặc script ngoài Liquibase.
- Đối tượng đặc thù theo môi trường, ví dụ bảng audit/extension do nền tảng tạo.
- Đối tượng tạm còn sót lại từ một lần triển khai.
- Đối tượng được quản lý bởi DBA hoặc một hệ thống khác.
- Kết quả của việc chọn sai schema/reference hoặc filter.

**Unexpected không có nghĩa là “nên xóa”.** Một bảng target-only có thể đang chứa dữ liệu hợp lệ, một index có thể phục vụ tải production, hoặc một role/object thuộc trách nhiệm của nền tảng. Chỉ xóa sau khi xác định owner, dependency, retention và cách bảo toàn dữ liệu.

### 3.3. Changed objects — đối tượng có ở cả hai nhưng khác định nghĩa

Một object được coi là changed khi Liquibase nhận diện đối tượng tương ứng ở hai phía nhưng phát hiện khác biệt trong những thuộc tính mà snapshot/diff hỗ trợ.

Ví dụ:

- Cột <code>orders.amount</code> là <code>DECIMAL(12,2)</code> ở reference và <code>DECIMAL(10,2)</code> ở target.
- Cột <code>orders.created_at</code> nullable ở target nhưng NOT NULL ở reference.
- Index cùng tên nhưng thứ tự cột hoặc unique property khác.
- View cùng tên nhưng định nghĩa SQL khác.
- Constraint cùng tên nhưng biểu thức hoặc cột tham gia khác.

Changed cần được đọc chi tiết. Tên object giống nhau không chứng minh hai định nghĩa tương đương; một khác biệt nhỏ như precision, collation, predicate hoặc trạng thái validate có thể ảnh hưởng dữ liệu và truy vấn.

Không phải mọi khác biệt đều được mọi phiên bản Liquibase hiển thị như một mục “Changed Objects” theo cùng cách. Một số loại object/thuộc tính có thể được phân loại, chuẩn hóa hoặc bỏ qua tùy snapshot generator và DBMS. Hãy xem chi tiết đầu ra và tài liệu đúng phiên bản đang chạy.

## 4. Đọc báo cáo diff từ trên xuống

Kết quả diff thường cung cấp thông tin về hai database, số lượng object được so sánh và danh sách khác biệt theo nhóm. Cấu trúc chính xác của output phụ thuộc phiên bản và cách gọi CLI, nhưng cách đọc có thể theo thứ tự:

1. **Thông tin kết nối:** reference/target có đúng server, database, DBMS và schema không?
2. **Phạm vi so sánh:** những schema/object nào được đưa vào, filter nào đang hoạt động?
3. **Tổng quan object được so sánh:** Liquibase có nhận diện đủ loại object mong muốn không?
4. **Missing:** target thiếu gì so với reference?
5. **Unexpected:** target có thêm gì?
6. **Changed:** những object tương ứng có thuộc tính nào khác?
7. **Cảnh báo/lỗi:** có object không được hỗ trợ, không đọc được metadata hoặc không thể so sánh không?

Ví dụ đầu ra **giản lược để minh họa**:

~~~text
Reference Database: baseline_db
Target Database:    production_db

Compared Objects:
  Tables:  18
  Columns: 142
  Indexes: 27
  Views:   4

Missing Objects:
  Column: orders.status_code
  Index:  idx_orders_status

Unexpected Objects:
  Table:  debug_event
  Index:  idx_orders_created_tmp

Changed Objects:
  Column: orders.amount
    reference: DECIMAL(12,2), NOT NULL
    target:    DECIMAL(10,2), NULL
~~~

Trong ví dụ, baseline là reference và production là target. Như vậy production thiếu cột/index mong muốn, có thêm bảng/index riêng, và cột amount khác cả precision lẫn nullability. Chưa thể kết luận phải thêm, xóa hay sửa ngay: cần xem migration lịch sử, mục đích của object target-only và dữ liệu hiện hữu.

### 4.1. Kiểm tra phần “Compared Objects”

Nếu nhóm dự kiến so sánh 10 schema nhưng output chỉ cho thấy một schema, báo cáo missing/unexpected có thể không đáng tin. Hãy kiểm tra:

- URL và database name.
- Default schema/catalog của từng phía.
- Schema include/exclude.
- Case folding và quoting.
- Tài khoản đọc metadata.
- DBMS/version và snapshot capabilities.

Một báo cáo rất ngắn hoặc “không có khác biệt” đôi khi là dấu hiệu scope bị thu hẹp hoặc thiếu quyền, không phải bằng chứng database đã đồng bộ.

### 4.2. Đọc cảnh báo và object không so sánh được

Một số object đặc thù, metadata hoặc thuộc tính không được hỗ trợ đầy đủ có thể không xuất hiện như một khác biệt thông thường. Nếu công cụ cảnh báo không thể snapshot object hoặc bỏ qua loại object, cần ghi nhận phạm vi chưa được xác minh và bổ sung DDL/catalog inspection.

Đừng coi việc một object không xuất hiện trong Missing, Unexpected hay Changed là chứng minh object đó giống nhau. Có thể nó chưa được đưa vào phép so sánh.

## 5. Phân tích Missing theo loại object

### 5.1. Table hoặc column thiếu

Nếu reference có bảng/cột nhưng target thiếu, hãy kiểm tra:

- Bảng/cột có thuộc môi trường target theo thiết kế không?
- Changeset tạo nó đã được thực thi chưa? Có bị lọc bởi context/label/DBMS không?
- Target có object tương đương nhưng tên khác không?
- Ứng dụng hoặc view có phụ thuộc vào nó không?
- Có dữ liệu cần backfill trước khi thêm NOT NULL hoặc constraint không?
- DDL thêm object có cần lock/rewrite bảng lớn không?

Ví dụ, thêm cột nullable thường ít rủi ro hơn thêm cột NOT NULL với default trên một bảng lớn, nhưng hành vi thực tế phụ thuộc DBMS/version. Không suy từ báo cáo missing column để viết ngay một <code>addColumn</code> production.

### 5.2. Constraint thiếu

Nếu target thiếu primary key, unique, foreign key hoặc check constraint:

- Kiểm tra dữ liệu hiện có có duplicate/orphan/giá trị sai không.
- Xác nhận cột và khóa đích có đúng kiểu/đúng thứ tự không.
- Xem trạng thái constraint có enabled/validated hay không.
- Xem có cần index hỗ trợ và tác động khi tạo constraint trên bảng lớn.
- Xác định hành vi ON DELETE/ON UPDATE và tác động tới ứng dụng.

Ví dụ target thiếu FK không nhất thiết là do migration quên chạy. Có thể một DBMS không hỗ trợ cùng cú pháp, hoặc constraint được tạo ở schema khác. Cần xác minh catalog.

### 5.3. Index thiếu

Index thiếu có thể gây chậm truy vấn hoặc tăng chi phí thao tác trên bảng cha/con. Trước khi thêm:

- Xem index có cùng chức năng nhưng tên khác không.
- So column order, uniqueness, expression, predicate và included columns.
- Xem query plan và workload thực tế.
- Đánh giá online/concurrent index theo DBMS/version.
- Xác minh index cùng tên chưa tồn tại ở schema khác hoặc ở trạng thái invalid.

Không tạo duplicate index chỉ để làm diff “xanh”; index dư thừa có thể tăng chi phí ghi và lưu trữ.

### 5.4. View, sequence, trigger và function thiếu

Một view thiếu có thể kéo theo thiếu function hoặc quyền; sequence thiếu có thể khiến insert ID thất bại; trigger thiếu có thể làm mất audit hoặc logic cập nhật. Hãy lần theo dependency graph và thứ tự tạo, không chỉ thêm object thiếu ở cuối.

Nếu đối tượng có cú pháp đặc thù, có thể cần SQL/SQL file theo DBMS và rollback riêng. Kiểm tra định nghĩa gốc, owner, grants, security mode và những object phụ thuộc.

## 6. Phân tích Unexpected: giữ, quản lý hay loại bỏ?

Unexpected là nhóm dễ dẫn đến hành động phá hủy nếu đọc theo nghĩa “thừa thì xóa”. Cần phân loại trước:

| Nhóm unexpected | Ví dụ | Quyết định thường cần |
|---|---|---|
| Drift không được phê duyệt | DBA thêm column thủ công mà không có ticket | Xác minh mục đích, đưa vào changelog hoặc hoàn nguyên theo quy trình |
| Object đặc thù môi trường | Bảng audit riêng ở production | Ghi nhận ngoại lệ và scope; không xóa chỉ vì reference không có |
| Object do nền tảng quản lý | Extension, role hoặc metadata do managed database tạo | Xác định owner và cách provisioning |
| Object tạm/đã hết hạn | Bảng staging còn sót sau import | Kiểm tra retention, dữ liệu và dependency trước khi drop |
| Object được đổi tên | Bảng cũ vẫn còn trong target, reference dùng tên mới | Xác định đây là rename hay hai object độc lập |
| Object không thuộc phạm vi | Schema của service khác | Điều chỉnh scope/reference nếu đúng kiến trúc |

### 6.1. Không xóa unexpected một cách tự động

Giả sử target có bảng <code>debug_event</code> với vài triệu hàng. Diff báo unexpected vì reference không có. Nếu chạy diff changelog rồi áp vào target, công cụ có thể đề xuất thao tác drop theo chiều làm target giống reference, tùy object và nội dung sinh ra. Hành động đó có thể xóa dữ liệu production.

Trước khi drop:

1. Xác định object owner và người dùng thực tế.
2. Tìm ứng dụng, job, báo cáo, trigger hoặc consumer phụ thuộc.
3. Kiểm tra dữ liệu, retention và yêu cầu audit.
4. Xác định object có thể được một tool khác quản lý.
5. Lập phương án archive/backup và thời gian lưu.
6. Tạo changeset drop riêng, có precondition, rollback/restore plan và approval.

Nếu object hợp lệ theo kiến trúc, hãy đưa nó vào reference thích hợp hoặc điều chỉnh phạm vi so sánh, thay vì xóa để khớp một baseline không đại diện cho target.

### 6.2. Unexpected index có thể vẫn cần thiết

Một index production-only có thể được DBA thêm để xử lý truy vấn mới trong khi changelog chưa cập nhật. Xóa index chỉ để loại bỏ unexpected có thể làm p99 latency tăng. Cần so định nghĩa, workload và kế hoạch thực hiện; nếu index được chấp nhận lâu dài, ghi nhận nguồn gốc và quản lý nó qua một changeset có review.

## 7. Phân tích Changed theo thuộc tính

### 7.1. Column: type, nullability, default

Ví dụ:

| Thuộc tính | Reference | Target | Câu hỏi cần trả lời |
|---|---|---|---|
| Type | <code>DECIMAL(12,2)</code> | <code>DECIMAL(10,2)</code> | Giá trị hiện tại có vượt precision target không? |
| Nullability | NOT NULL | NULL | Có hàng NULL? Ứng dụng có phụ thuộc vào việc cho phép NULL không? |
| Default | <code>0</code> | Không có default | INSERT từ app cũ có hành vi khác không? |
| Length | <code>VARCHAR(120)</code> | <code>VARCHAR(80)</code> | Có dữ liệu dài hơn giới hạn mới không? |
| Collation | Phân biệt hoa/thường | Không phân biệt | Unique/lookup có đổi kết quả không? |
| Time type | Timestamp có timezone | Timestamp không timezone | Có cần chuyển đổi thời điểm lịch sử không? |

Trước khi thu hẹp kiểu, truy vấn thống kê giá trị và thử trên bản sao dữ liệu. Trước khi thêm NOT NULL, đếm NULL và bảo đảm writer không tạo NULL mới. Trước khi đổi default, kiểm tra các đường INSERT bỏ qua cột.

### 7.2. Index: cùng tên không có nghĩa cùng định nghĩa

Khi một index được báo changed, so:

- Unique hay non-unique.
- Danh sách cột và thứ tự.
- Expression/function index.
- Predicate/partial index.
- Included/covering columns.
- Access method, operator class, collation hoặc tablespace nếu DBMS hỗ trợ.
- Trạng thái valid/usable.

Hai index cùng tên và cùng cột nhưng một cái unique có thể làm thay đổi hoàn toàn tính hợp lệ dữ liệu. Không drop/create chỉ dựa trên tên.

### 7.3. Constraint: biểu thức và trạng thái

Với FK, so bảng/cột con, bảng/cột cha, thứ tự cột ghép và ON DELETE/ON UPDATE. Với CHECK, so biểu thức và quy tắc NULL. Với unique, so tập cột và collation. Cần xem constraint đã enabled/validated hay mới được khai báo nhưng chưa kiểm tra toàn bộ dữ liệu cũ.

Một constraint tồn tại nhưng chưa validate có thể bảo vệ dữ liệu mới theo một số DBMS mà chưa chứng minh dữ liệu lịch sử hợp lệ. Kết quả diff và catalog phải được đọc cùng nhau.

### 7.4. View/function/procedure: nội dung định nghĩa

Khác biệt trong view hoặc function có thể là:

- Thay đổi biểu thức tính toán.
- Thay đổi join/filter hoặc schema được tham chiếu.
- Thay đổi quyền thực thi hoặc security mode.
- Thay đổi language, volatility hoặc signature.
- Khác biệt do DBMS chuẩn hóa cú pháp khi lưu metadata.

Không coi một khác biệt văn bản nhỏ chắc chắn là thay đổi nghiệp vụ; cũng không coi cùng tên object là tương đương. Đọc DDL đã chuẩn hóa và kiểm thử kết quả truy vấn trên dữ liệu đại diện.

## 8. Phân biệt drift thật với khác biệt theo môi trường

Không phải mọi môi trường phải có schema giống hệt nhau ở mọi object. Có thể có khác biệt được thiết kế:

- Production có index phục vụ workload riêng.
- Test có bảng dữ liệu mẫu hoặc extension test-only.
- Mỗi tenant có schema và object riêng.
- Managed database có object hệ thống do nhà cung cấp tạo.
- Một môi trường chưa được bật tính năng nên chưa có object liên quan.

Để không bỏ sót drift thật, cần ghi **quy tắc khác biệt hợp lệ** theo từng môi trường.

| Câu hỏi | Nếu câu trả lời là “có” | Cách xử lý |
|---|---|---|
| Object có nằm ngoài scope được quản lý không? | Có thể là khác biệt hợp lệ | Ghi rõ scope/filter và owner |
| Object do nền tảng/DBA quản lý không? | Không nhất thiết thuộc changelog ứng dụng | Xác định nguồn provisioning và kiểm tra quyền |
| Object chỉ khác vì DBMS? | Có thể cần nhánh changeset riêng | So sánh theo engine và kiểm thử từng nhánh |
| Khác biệt được phê duyệt theo workload? | Có thể giữ lại | Lưu ticket/owner, bổ sung tài liệu và baseline phù hợp |
| Không ai biết object được tạo khi nào? | Có thể là drift không kiểm soát | Điều tra audit/log, không xóa vội |

### 8.1. Scope phải tương đương

Trước khi so sánh, bảo đảm hai phía dùng phạm vi tương đương:

- Cùng tập schema nghiệp vụ, hoặc có mapping schema rõ ràng.
- Cùng quy tắc default schema/catalog.
- Cùng cách xử lý case sensitivity và quoted identifiers.
- Cùng include/exclude filters cho object types.
- Tài khoản đọc metadata có quyền tương đương.
- DBMS/version được ghi nhận.

Nếu reference so schema <code>sales</code> nhưng target lại dùng <code>sales_prod</code>, cần cấu hình mapping hoặc xác định cách so sánh phù hợp. Không đổi tên object chỉ để làm báo cáo hết missing/unexpected khi khác biệt thực ra là khác tên schema.

### 8.2. Chú ý object hệ thống và object do extension tạo

Managed database hoặc extension có thể tạo object mà ứng dụng không sở hữu. Nếu đưa toàn bộ object đó vào baseline ứng dụng, changeset có thể phụ thuộc quyền hoặc tính năng mà môi trường khác không có. Nếu loại bỏ khỏi scope, phải bảo đảm không bỏ sót object nghiệp vụ nằm cùng schema.

Quyết định include/exclude nên được lưu thành quy tắc có thể review, không chỉnh filter tùy tiện cho tới khi báo cáo “đẹp”.

## 9. Những gì schema diff không chứng minh

Schema diff chủ yếu giúp so sánh **định nghĩa đối tượng mà Liquibase có thể snapshot**. Không nên dùng nó làm bằng chứng đầy đủ cho:

1. **Nội dung dữ liệu:** hai bảng cùng cấu trúc không có nghĩa các hàng hoặc giá trị nghiệp vụ giống nhau.
2. **Tính đúng nghiệp vụ:** cùng kiểu <code>VARCHAR</code> không chứng minh tập mã trạng thái có cùng ý nghĩa.
3. **Hiệu năng:** index tồn tại không chứng minh query plan tốt, thống kê cập nhật hay latency đạt SLO.
4. **Quyền hiệu lực đầy đủ:** object có thể tồn tại nhưng user ứng dụng không có quyền hoặc bị policy chặn.
5. **Tính hợp lệ của mọi constraint:** trạng thái enabled/validated có thể cần kiểm tra riêng theo DBMS.
6. **Phụ thuộc ngoài database:** code, job, BI, queue consumer hoặc script có thể tham chiếu object.
7. **Tính tương thích ứng dụng:** schema giống nhau vẫn có thể khác dữ liệu hoặc cấu hình khiến ứng dụng hoạt động khác.
8. **Khả năng rollback:** báo cáo diff không tự cung cấp kế hoạch phục hồi dữ liệu.

Đặc biệt, **không dùng kết quả schema diff để kết luận hai database có cùng dữ liệu**. Nếu cần kiểm tra dữ liệu, phải dùng quy trình đối soát riêng với khóa nghiệp vụ, checksum dữ liệu hoặc thống kê phù hợp; phạm vi đó có yêu cầu bảo mật và hiệu năng riêng.

## 10. Dùng diff và diff-changelog đúng mục đích

### 10.1. diff: quan sát và phân tích

Lệnh <code>diff</code> tạo báo cáo khác biệt giữa reference và target. Nó phục vụ điều tra, review và ra quyết định. Bản thân việc chạy diff không có nghĩa Liquibase đã thay đổi schema target.

Ví dụ CLI tham khảo:

~~~bash
liquibase \
  --reference-url=jdbc:postgresql://reference-host:5432/app \
  --url=jdbc:postgresql://target-host:5432/app \
  diff
~~~

Cách truyền URL, credential, schema và các tùy chọn khác phụ thuộc phiên bản/cấu hình. Trong môi trường thực, không đặt mật khẩu trực tiếp vào lịch sử shell hoặc log; dùng cơ chế secrets được tổ chức phê duyệt.

### 10.2. diff-changelog: tạo bản đề xuất thay đổi

<code>diff-changelog</code> có thể tạo changelog chứa các change cần thiết để đưa target gần với reference hơn, trong phạm vi object và thao tác mà Liquibase hỗ trợ.

Ví dụ:

~~~bash
liquibase \
  --reference-url=jdbc:postgresql://reference-host:5432/app \
  --url=jdbc:postgresql://target-host:5432/app \
  diff-changelog \
  --changelog-file=generated-diff.yaml
~~~

Đây là cú pháp minh họa cho CLI hiện đại; cần kiểm tra trợ giúp của phiên bản dự án. Tệp được tạo chỉ là **bản nháp cần review**. Không đưa thẳng vào pipeline production chỉ vì lệnh sinh file kết thúc thành công.

### 10.3. Chiều của diff-changelog

Khi reference là trạng thái mong muốn và target là database cần thay đổi, mục tiêu của diff-changelog là sinh những change để target tiến gần tới reference. Vì vậy:

- Object missing ở target có thể dẫn tới change tạo object.
- Object unexpected ở target có thể dẫn tới change loại bỏ object, nếu loại object và generator hỗ trợ.
- Object changed có thể dẫn tới change điều chỉnh định nghĩa, nếu có change type/SQL biểu diễn được.

Không phải mọi khác biệt đều được tự động chuyển thành changeset hoàn chỉnh. Một số object có thể không hỗ trợ, không thể tạo rollback, cần SQL đặc thù hoặc cần xử lý dữ liệu trước. Generated changelog cũng không hiểu đầy đủ ý nghĩa nghiệp vụ của object unexpected.

### 10.4. Checklist review generated changelog

- [ ] Reference và target đã đúng chiều chưa?
- [ ] Có đúng database, schema, DBMS và version không?
- [ ] Changeset tạo object có đúng thứ tự dependency không?
- [ ] Có thao tác drop dữ liệu hoặc object target-only không?
- [ ] Kiểu dữ liệu/precision/default/nullability có gây mất dữ liệu không?
- [ ] Có thiếu SQL cho trigger, function, grant hoặc object đặc thù không?
- [ ] Có tên constraint/index trùng hoặc quá dài không?
- [ ] Rollback có phục hồi được dữ liệu/định nghĩa trước đó không?
- [ ] Preconditions có bảo vệ trạng thái và ngăn chạy sai môi trường không?
- [ ] Changeset đã được test trên database trống và database có trạng thái tương tự target chưa?

## 11. Đọc diff theo dependency order

Không xử lý missing/changed từng dòng độc lập. Các object thường có quan hệ phụ thuộc:

~~~text
Schema / type / sequence
          |
          v
        Table
       /  |  \
      v   v   v
   Column PK/UK Index
             |
             v
        Foreign key
             |
             v
       View / Trigger
             |
             v
      Function / Grant
~~~

Đây là sơ đồ đơn giản; dependency thật có thể phức tạp và có vòng. Ví dụ:

- Missing table có thể kéo theo missing column, index, FK và view.
- Changed type ở bảng cha có thể làm FK hoặc function phụ thuộc thất bại.
- Unexpected column có thể được trigger hoặc view đang sử dụng.
- Changed view có thể chỉ là khác biệt định dạng SQL, nhưng cũng có thể thay đổi filter nghiệp vụ.

Nên nhóm diff theo **đối tượng gốc và dependency**, rồi tạo kế hoạch migration theo thứ tự. Nếu chỉ xử lý theo thứ tự alphabet hoặc thứ tự xuất hiện trong báo cáo, changeset có thể chạy trước khi đối tượng phụ thuộc sẵn sàng.

### 11.1. Ví dụ dependency khi cột bị thiếu

Reference có:

- <code>customer.id</code> là primary key.
- <code>orders.customer_id</code> có foreign key tới <code>customer.id</code>.
- Index trên <code>orders.customer_id</code>.

Target thiếu cột <code>orders.customer_id</code> và thiếu FK/index tương ứng. Kế hoạch không thể bắt đầu bằng tạo FK hoặc index. Cần:

1. Xác định cột cần thêm, kiểu dữ liệu và nullability.
2. Thêm cột với chiến lược tương thích dữ liệu.
3. Backfill/mapping dữ liệu nếu cần.
4. Phát hiện orphan records.
5. Tạo index phù hợp.
6. Thêm FK sau khi dữ liệu và khóa cha đã đạt yêu cầu.

Một diff báo ba object missing có thể chỉ phản ánh **một thay đổi gốc** chưa được thực hiện. Xử lý theo dependency giúp tránh tạo changeset trùng hoặc không cần thiết.

## 12. So sánh thay đổi kiểu dữ liệu có nguy cơ mất dữ liệu

Khi diff báo changed column, hãy phân loại mức độ:

| Thay đổi | Rủi ro cần kiểm tra |
|---|---|
| <code>VARCHAR(80)</code> → <code>VARCHAR(120)</code> | Thường mở rộng nhưng cần kiểm tra charset/index/DBMS |
| <code>VARCHAR(120)</code> → <code>VARCHAR(80)</code> | Dữ liệu dài hơn có thể bị lỗi hoặc cắt |
| <code>DECIMAL(10,2)</code> → <code>DECIMAL(12,2)</code> | Mở rộng miền giá trị nhưng vẫn phải xem DBMS/DDL |
| <code>DECIMAL(12,4)</code> → <code>DECIMAL(10,2)</code> | Có thể overflow hoặc mất phần thập phân |
| NULL → NOT NULL | Phải xử lý hàng NULL và các writer còn hoạt động |
| NOT NULL → NULL | Thay đổi hợp đồng dữ liệu, ứng dụng có thể phải xử lý NULL |
| Timestamp không timezone → có timezone | Phải xác định timezone gốc và cách chuyển đổi |
| Collation A → B | So sánh, unique và order by có thể thay đổi |
| Integer → text | Mapping và format dữ liệu có thể không đảo ngược |

Ví dụ trước khi thu hẹp decimal:

~~~sql
SELECT
    MAX(ABS(amount)) AS max_abs_amount,
    COUNT(*) AS total_rows
FROM orders;
~~~

Truy vấn này chưa đủ để chứng minh scale có thể giảm an toàn; cần kiểm tra các chữ số thập phân thực tế và precision đích. Với thay đổi timezone/collation, cần test dữ liệu biên và truy vấn ứng dụng. Không tự động chấp nhận generated <code>modifyDataType</code> nếu chưa đánh giá tác động.

## 13. Đối chiếu diff với changelog và lịch sử triển khai

Diff so sánh trạng thái object mà snapshot đọc được. <code>DATABASECHANGELOG</code> ghi nhận những changeset Liquibase đã thực thi hoặc được đồng bộ. Hai nguồn trả lời các câu hỏi khác nhau:

- **Diff:** trạng thái cấu trúc vật lý hiện tại khác reference như thế nào?
- **DATABASECHANGELOG:** Liquibase cho rằng changeset nào đã được áp dụng, với định danh và checksum nào?

Một changeset có thể được ghi nhận là đã chạy nhưng object đã bị DBA xóa thủ công; khi đó lịch sử và trạng thái vật lý lệch nhau. Ngược lại, object có thể được tạo thủ công nhưng không có changeset tương ứng; diff thấy object nhưng history không ghi nhận nguồn gốc.

### 13.1. Bốn tình huống cần phân biệt

| Lịch sử changeset | Diff object | Diễn giải có thể |
|---|---|---|
| Đã chạy | Khớp reference | Trạng thái có vẻ nhất quán; vẫn cần kiểm tra object ngoài scope |
| Đã chạy | Missing/changed | Drift sau triển khai, thay đổi thủ công, lỗi partial hoặc khác cách snapshot |
| Chưa chạy | Missing | Có thể migration còn pending; kiểm tra filter và dependency |
| Chưa chạy | Object đã tồn tại | Có thể được tạo thủ công, baseline chưa đồng bộ hoặc thay đổi từ tool khác |

Không chỉnh sửa trực tiếp <code>DATABASECHANGELOG</code> để làm cho diff “hết khác biệt”. Hãy điều tra nguyên nhân, xác minh object và chọn quy trình baseline/sync hoặc changeset khắc phục có kiểm soát.

### 13.2. Checksum không chứng minh schema hiện tại

Checksum giúp Liquibase phát hiện thay đổi nội dung changeset trong phạm vi cơ chế của nó. Checksum không chứng minh rằng:

- Object vẫn tồn tại sau khi changeset đã chạy.
- DDL thủ công không thay đổi object.
- Mọi thuộc tính của object đã được snapshot và so sánh.
- Dữ liệu có cùng giá trị.
- Reference và target có cùng behavior.

Vì vậy, khi diff và history mâu thuẫn, phải dùng catalog/DDL thực tế và log triển khai để giải thích. Không xóa checksum hoặc sửa changeset lịch sử chỉ để dập cảnh báo.

## 14. Quy trình xử lý kết quả diff theo từng bước

### Bước 1 — Chốt mục tiêu và chiều so sánh

Viết rõ: “Reference là trạng thái chuẩn X; target là database Y cần kiểm tra.” Ghi database, schema, DBMS/version và thời điểm chạy.

### Bước 2 — Xác nhận scope và quyền

So sánh cùng phạm vi schema/object; kiểm tra default schema, case sensitivity, include/exclude filter và quyền đọc metadata. Nếu scope không đầy đủ, dừng kết luận.

### Bước 3 — Đọc tổng quan và cảnh báo

Kiểm tra số object được so sánh, loại object được hỗ trợ, lỗi snapshot và cảnh báo. Xác nhận báo cáo thực sự bao phủ phần kiến trúc cần quản lý.

### Bước 4 — Phân loại từng khác biệt

Với mỗi missing/unexpected/changed, ghi:

- Object và định nghĩa cụ thể.
- Reference value và target value.
- Nguyên nhân giả định.
- Owner và phụ thuộc.
- Mức rủi ro dữ liệu, lock, security và application compatibility.
- Quyết định: thêm, sửa, giữ, loại bỏ, exclude hoặc điều tra thêm.

### Bước 5 — Nhóm theo dependency

Tách khác biệt gốc và khác biệt kéo theo. Xác định thứ tự tạo/đổi/xóa, đặc biệt với type, table, key, index, FK, view, trigger và function.

### Bước 6 — Xem xét diff-changelog

Chỉ sinh bản nháp sau khi đã thống nhất mục tiêu và chiều. Đọc từng change, bổ sung precondition, SQL đặc thù và rollback cần thiết. Xóa các thao tác không được phê duyệt.

### Bước 7 — Kiểm thử trên database phù hợp

Thử với đúng DBMS/version và dữ liệu đại diện. Kiểm tra trạng thái trước/sau, SQL preview, dữ liệu, lock, rollback và ứng dụng.

### Bước 8 — Phê duyệt và triển khai

Dùng artifact đã review, cố định filter/parameters và kết nối; chạy một đường migration được điều phối. Sau triển khai, chạy lại diff và xác minh các ngoại lệ còn lại.

### Bước 9 — Lưu bằng chứng

Lưu báo cáo diff, phiên bản Liquibase, cấu hình scope, reference/target identity, quyết định từng khác biệt, changeset được tạo và kết quả kiểm tra. Không ghi mật khẩu/secret vào artifact hoặc log.

## 15. Bảng phân loại quyết định

Một mẫu bảng giúp reviewer không hành động theo tên nhóm một cách máy móc:

| Kết quả diff | Câu hỏi xác minh | Quyết định có thể có |
|---|---|---|
| Missing table/column | Có thật sự cần ở target? Có dependency/data migration? | Thêm theo changeset hoặc ghi nhận môi trường không cần |
| Missing constraint | Có dữ liệu vi phạm? Khóa đích hợp lệ? | Làm sạch rồi enforce, hoặc điều tra thiết kế |
| Missing index | Workload cần index? Có index tương đương? | Tạo theo kỹ thuật phù hợp DBMS hoặc giữ ngoại lệ |
| Unexpected table | Có owner/dữ liệu/job phụ thuộc? | Giữ và quản lý, archive hoặc drop sau phê duyệt |
| Unexpected index | Có phục vụ hiệu năng? Có trùng index khác? | Giữ, đưa vào changelog hoặc loại bỏ có kiểm soát |
| Changed column type | Có mất dữ liệu/đổi semantics? | Chuyển đổi theo giai đoạn, giữ nguyên hoặc sửa reference |
| Changed nullability/default | Writer cũ có tương thích? Dữ liệu hiện tại ra sao? | Backfill, cập nhật app rồi enforce |
| Changed view/function | Logic kết quả và quyền có đổi? | Review SQL, test kết quả và rollback definition |
| Changed object chỉ do DBMS | Khác biệt có chủ ý theo engine/version? | Tách nhánh hoặc điều chỉnh cách so sánh có tài liệu |
| Không có khác biệt nhưng scope đáng ngờ | Đã đọc đủ schema/object chưa? | Chưa kết luận; mở rộng quyền/phạm vi và kiểm tra lại |

## 16. Ví dụ phân tích một báo cáo tổng hợp

Giả sử báo cáo có:

~~~text
Missing:
  Column: customer_order.external_ref
  Foreign Key: fk_order_customer

Unexpected:
  Table: import_staging

Changed:
  Column: customer_order.amount
    Reference: DECIMAL(14,2) NOT NULL
    Target:    DECIMAL(12,2) NULL
  Index: idx_order_created
    Reference: (created_at, id)
    Target:    (id, created_at)
~~~

Một cách phân tích có trách nhiệm:

1. **external_ref missing:** hỏi ứng dụng target có cần cột mới không, nguồn dữ liệu sẽ backfill thế nào và cột có nên nullable trong giai đoạn đầu không.
2. **FK missing:** kiểm tra bảng cha, khóa unique/PK, orphan records, schema và hành vi xóa/cập nhật trước khi tạo.
3. **import_staging unexpected:** xác định có phải bảng tạm do import job tạo, có dữ liệu cần giữ và job có còn dùng không. Không drop tự động.
4. **amount changed:** kiểm tra giá trị lớn nhất, số chữ số thập phân, NULL, đơn vị tiền và writer. Chuyển từ DECIMAL(12,2) sang DECIMAL(14,2) có thể mở rộng miền nhưng NOT NULL cần xử lý riêng.
5. **index order changed:** thứ tự cột ảnh hưởng query plan; xem query thực tế và explain plan. Không tự tạo lại chỉ để khớp thứ tự reference nếu index target đang phục vụ workload.

Kết quả cuối có thể là một kế hoạch nhiều changeset, một ngoại lệ có chủ ý và một thay đổi reference cần được xem xét. Mục tiêu là schema được quản lý và phù hợp ứng dụng, không phải ép mọi dòng diff về 0 bằng mọi giá.

## 17. Lỗi thường gặp khi đọc diff

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Đảo reference và target trong suy luận | Thêm/xóa nhầm đối tượng | Ghi chiều so sánh trước khi đọc missing/unexpected |
| Coi missing luôn là lỗi | Thêm object không cần ở môi trường đó | Kiểm tra kiến trúc và scope |
| Coi unexpected là object phải drop | Mất dữ liệu hoặc phá workload | Xác định owner/dependency/retention |
| Chỉ nhìn tên object | Bỏ qua type, precision, predicate hoặc constraint definition | Đọc chi tiết thuộc tính |
| Tin báo cáo không khác biệt tuyệt đối | Bỏ sót object ngoài scope hoặc không được hỗ trợ | Kiểm tra Compared Objects, quyền và cảnh báo |
| Dùng reference chưa được phê duyệt | Hợp thức hóa drift thành chuẩn | Chọn nguồn chuẩn và lưu quyết định |
| Sinh diff-changelog rồi áp ngay | Có thể drop dữ liệu hoặc sai dependency | Review mọi changeset và test |
| Không kiểm tra case/schema | Object tồn tại nhưng bị báo missing | Xác minh identifier, schema mapping và default schema |
| Bỏ qua DBMS/version | Khác biệt do tính năng engine bị hiểu sai | So theo engine/version, tách nhánh khi cần |
| Nhầm schema diff với data diff | Kết luận dữ liệu hai bên giống nhau | Đối soát dữ liệu riêng |
| Nhầm DATABASECHANGELOG với trạng thái vật lý | Bỏ qua drift sau migration | Đọc history cùng catalog và diff |
| Sửa checksum hoặc history để làm sạch kết quả | Lịch sử mất độ tin cậy | Điều tra và tạo changeset khắc phục |
| Xóa index target-only không xem query plan | Hiệu năng production suy giảm | Đánh giá workload và owner |
| Bỏ qua dependency | Tạo object theo sai thứ tự | Xây dependency graph và nhóm changeset |

## 18. Checklist trước khi chấp nhận kết quả schema diff

- [ ] Reference và target được ghi rõ, đúng chiều so sánh.
- [ ] Đúng host/database/DBMS/version và thời điểm snapshot.
- [ ] Scope schema/catalog và include/exclude filters tương đương.
- [ ] Tài khoản có đủ quyền đọc metadata; không nhầm thiếu quyền với thiếu object.
- [ ] Đã xem tổng quan object được so sánh và mọi cảnh báo/loại object không hỗ trợ.
- [ ] Missing được xác minh là cần bổ sung ở target.
- [ ] Unexpected có owner, dependency, dữ liệu và quyết định giữ/xóa rõ ràng.
- [ ] Changed được đọc chi tiết về type, nullability, default, precision, collation, constraint, index và definition.
- [ ] Khác biệt được phân loại thành drift thật, khác biệt môi trường hoặc giới hạn công cụ.
- [ ] Đã kiểm tra dependency order và ảnh hưởng tới ứng dụng/job.
- [ ] Không coi diff là so sánh nội dung dữ liệu.
- [ ] Generated diff-changelog đã được review, đặc biệt các change drop/modify.
- [ ] Rollback và khả năng phục hồi dữ liệu đã được xem xét.
- [ ] Đã thử trên DBMS/version và dữ liệu đại diện.
- [ ] Sau triển khai có diff/metadata verification và lưu báo cáo cùng quyết định.

## 19. Ghi nhớ

Khi đọc kết quả Liquibase diff, hãy bắt đầu bằng câu hỏi **reference là gì và target là gì**. Missing nghĩa là có ở reference nhưng không thấy ở target; unexpected nghĩa là có ở target nhưng không thấy ở reference; changed nghĩa là hai phía có object tương ứng nhưng khác thuộc tính mà công cụ nhận diện được. Các nhóm này chỉ mô tả khác biệt, không tự đưa ra quyết định thêm, sửa hay xóa.

Một quy trình đáng tin cậy là **xác nhận chiều và scope → đọc tổng quan → phân tích từng object → phân loại drift và ngoại lệ → kiểm tra dependency/dữ liệu → review diff-changelog → thử nghiệm → triển khai có kiểm soát → xác minh lại**. Diff, snapshot và lịch sử changeset cần được đọc cùng nhau, nhưng không nguồn nào thay thế catalog thực tế, kiểm tra dữ liệu, kiểm thử ứng dụng hoặc quyết định của owner. Cách làm này giúp duy trì schema nhất quán và lịch sử migration có thể truy vết trong quy trình Liquibase, Spring Boot và CI/CD.
