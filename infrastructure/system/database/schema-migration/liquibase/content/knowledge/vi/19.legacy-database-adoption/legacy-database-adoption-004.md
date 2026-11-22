# Rà soát đối tượng bị bỏ sót, kiểu dữ liệu và phụ thuộc

## 1. Vì sao tiếp nhận database legacy cần rà soát nhiều hơn danh sách bảng?

Khi đưa một cơ sở dữ liệu đã tồn tại vào quản lý bằng Liquibase, nhóm thường bắt đầu bằng việc so sánh schema và tạo changelog nền. Tuy nhiên, một bản so sánh chỉ liệt kê bảng và cột có thể bỏ sót những thành phần đang giữ vai trò quan trọng: sequence, index, constraint, view, trigger, function, procedure, synonym, partition, extension, quyền truy cập hoặc đối tượng đặc thù của DBMS. Một số đối tượng không xuất hiện trong mô hình ORM nhưng vẫn được job nền, báo cáo hoặc ứng dụng tích hợp sử dụng.

Một rủi ro khác là **hai cột cùng tên và cùng kiểu hiển thị chưa chắc có cùng ý nghĩa dữ liệu**. Ví dụ, cột timestamp có thể lưu thời gian địa phương ở một database và thời điểm UTC ở database khác; cột decimal có thể khác precision/scale; chuỗi có thể khác collation hoặc quy tắc so sánh. Nếu chỉ nhìn tên cột và kiểu tổng quát, migration có thể làm tròn dữ liệu, thay đổi thứ tự sắp xếp, mất khả năng biểu diễn giá trị hoặc phá vỡ truy vấn.

Cuối cùng, các đối tượng không tồn tại độc lập. View phụ thuộc bảng; foreign key phụ thuộc khóa được tham chiếu; trigger phụ thuộc function; bảng có thể phụ thuộc sequence hoặc type riêng; ứng dụng lại phụ thuộc vào tên cột, quyền, view và thủ tục. Nếu tạo changelog không theo thứ tự phụ thuộc, việc triển khai có thể thất bại dù từng câu DDL riêng lẻ hợp lệ.

Bài học thuộc chương **Tiếp nhận CSDL** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Module hướng dẫn quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Trọng tâm ở đây là xây dựng một bức tranh đầy đủ về **đối tượng, kiểu dữ liệu và quan hệ phụ thuộc** trước khi coi database legacy là đã được tiếp nhận.

Sau bài học, người học có thể:

1. Lập inventory cho cả đối tượng hiển thị trong schema và đối tượng dễ bị bỏ sót.
2. Đối chiếu metadata giữa database thực tế, snapshot và changelog mà không mặc định công cụ phát hiện được mọi thứ.
3. Phân tích khác biệt về kiểu dữ liệu, độ chính xác, NULL, default, collation và ngữ nghĩa.
4. Xây dựng dependency graph và sắp xếp thứ tự tạo, thay đổi, xác minh đối tượng.
5. Xác định các phụ thuộc ngoài database như ứng dụng, batch, báo cáo, quyền và tích hợp.
6. Tạo baseline Liquibase có bằng chứng, sau đó tiếp tục quản lý thay đổi mà không làm sai lịch sử.

## 2. Phạm vi rà soát: inventory không chỉ có table và column

Một database legacy thường có nhiều lớp đối tượng. Nên lập danh sách theo nhóm, ghi rõ schema, owner, mục đích, trạng thái quản lý và nguồn xác minh.

| Nhóm | Đối tượng cần kiểm kê | Vì sao dễ bị bỏ sót |
|---|---|---|
| Cấu trúc dữ liệu | Table, column, partition, partitioned table, temporary table | Có thể nằm ở schema khác, được tạo động hoặc khác nhau giữa môi trường |
| Khóa và ràng buộc | Primary key, unique, foreign key, check, not null, exclusion constraint | Một số công cụ hiển thị constraint gắn với table; tên hoặc định nghĩa không giống mong đợi |
| Chỉ mục | Index thường, unique index, partial/filtered index, expression index, covering index | Không phải index nào cũng được biểu diễn giống nhau trên mọi DBMS |
| Sinh khóa | Sequence, identity, auto-increment, default next value | Có thể là đối tượng riêng hoặc thuộc tính của column |
| View | View thường, materialized view, indexed view | Có thể phụ thuộc nhiều bảng, function hoặc quyền thực thi |
| Logic trong DB | Trigger, function, stored procedure, package, event, rule | Có thể nằm ngoài tập change type phổ biến hoặc phụ thuộc ngôn ngữ riêng |
| Kiểu dữ liệu riêng | Domain, enum, composite type, array, user-defined type | Khó ánh xạ trực tiếp sang DBMS khác |
| Namespace và tích hợp | Schema, catalog, synonym, database link, extension | Phụ thuộc engine, cấu hình hoặc quyền |
| Bảo mật | User/role, grant, revoke, default privilege, row-level security, policy | Chuyển schema mà không chuyển quyền có thể làm ứng dụng mất truy cập hoặc thừa quyền |
| Vận hành | Partition maintenance, job scheduler, replication/CDC metadata, audit | Có thể được DBA hoặc công cụ khác quản lý ngoài changelog |

Không phải mọi đối tượng trong bảng đều được mọi phiên bản Liquibase hỗ trợ đầy đủ qua snapshot, diff hoặc change type. Mục tiêu inventory là ghi nhận **đối tượng thực sự tồn tại và vai trò của nó**, sau đó mới quyết định đối tượng nào được quản lý trực tiếp bằng Liquibase, cần SQL đặc thù, do công cụ khác quản lý hay nằm ngoài phạm vi.

### 2.1. Phân loại đối tượng sau khi phát hiện

Đối với mỗi đối tượng, gán một trạng thái quản lý:

- **Managed by Liquibase:** định nghĩa và thay đổi được lưu trong changelog.
- **Externally managed:** được một hệ thống khác quản lý, chẳng hạn provisioning role hoặc nền tảng database.
- **Generated/ephemeral:** được tạo tự động hoặc chỉ tồn tại tạm thời, không phải thành phần baseline ổn định.
- **Manual/DBA-controlled:** cần quy trình DBA hoặc SQL riêng vì tính đặc thù, quyền hay rủi ro.
- **Out of scope:** đã có lý do rõ ràng để không tiếp nhận, kèm owner và tác động.

Không được bỏ qua đối tượng chỉ vì công cụ diff không hiển thị nó. Mỗi mục “không quản lý” cần có lý do và người chịu trách nhiệm; nếu không, thay đổi tương lai có thể vô tình xóa hoặc làm hỏng thành phần mà không ai biết.

## 3. Nguồn dữ liệu để phát hiện đối tượng bị bỏ sót

Không có một nguồn duy nhất phản ánh đầy đủ database legacy. Hãy đối chiếu nhiều nguồn:

| Nguồn | Thông tin có thể thu được | Giới hạn |
|---|---|---|
| System catalog/metadata của DBMS | Đối tượng vật lý, kiểu, constraint, index, owner và trạng thái | Cần quyền đọc đủ; mỗi DBMS có catalog riêng |
| <code>information_schema</code> | Một tập metadata chuẩn hóa cho bảng, cột, constraint và view | Không bao phủ mọi tính năng riêng của DBMS |
| Liquibase snapshot/diff | So sánh các loại đối tượng mà Liquibase và snapshot generator hỗ trợ | Có thể bỏ qua loại object, quyền, metadata hoặc khác biệt đặc thù |
| Schema dump/DDL export | Định nghĩa được công cụ native xuất ra | Có thể chứa thông tin nhạy cảm, owner hoặc cấu hình không nên đưa thẳng vào changelog |
| Source code và ORM mapping | Cột, tên bảng, sequence, query native và mapping ứng dụng | Không thể hiện đầy đủ mọi đối tượng mà ứng dụng dùng gián tiếp |
| SQL trong repository | View, procedure, trigger, query báo cáo, script triển khai | Có thể đã lỗi thời hoặc không còn được chạy |
| Job/batch/ETL/BI | Các truy vấn ngoài luồng request chính | Thường nằm ở repository hoặc hệ thống khác |
| Tài liệu DBA và lịch sử vận hành | Quy tắc backup, phân vùng, quyền, extension và thao tác thủ công | Có thể thiếu cập nhật; cần đối chiếu với catalog thực tế |
| Log/telemetry truy vấn | Đối tượng được truy cập thực tế trong khoảng quan sát | Không chứng minh mọi luồng hiếm hoặc định kỳ đều đã xuất hiện |

Một truy vấn không xuất hiện trong log trong bảy ngày không có nghĩa không còn được sử dụng; có thể nó chỉ chạy cuối tháng hoặc cuối quý. Inventory cần bao quát chu kỳ nghiệp vụ phù hợp.

### 3.1. Kiểm tra phạm vi schema và quyền đọc

Trước khi so sánh, ghi lại:

- Database/catalog đang kết nối, host, DBMS và phiên bản.
- Các schema nằm trong phạm vi tiếp nhận.
- Schema mặc định và quy tắc chữ hoa/thường của identifier.
- User/role dùng để đọc metadata và quyền mà role đó có.
- Các filter include/exclude schema hoặc object được đặt trong công cụ.
- Đối tượng nằm trong schema hệ thống, schema ứng dụng hay schema tích hợp.

Nếu tài khoản snapshot không có quyền xem một schema hoặc object, kết quả “không tìm thấy” có thể chỉ phản ánh **thiếu quyền**, không phải object không tồn tại. Cần phân biệt kết quả empty với lỗi truy cập và chứng minh phạm vi metadata đã được đọc đầy đủ.

## 4. Dùng Liquibase snapshot, diff và changelog generation đúng cách

Liquibase có các chức năng giúp quan sát cấu trúc database và so sánh hai trạng thái. Tùy phiên bản CLI và cách tích hợp, tên lệnh và tham số có thể khác; các ví dụ sau minh họa nhóm thao tác phổ biến:

- **Snapshot:** ghi nhận trạng thái đối tượng mà snapshot generator hỗ trợ tại thời điểm chạy.
- **Diff:** so sánh database tham chiếu với database đích, liệt kê khác biệt được nhận diện.
- **Diff changelog:** tạo bản nháp changelog từ các khác biệt.
- **Generate changelog:** sinh changelog mô tả cấu trúc hiện có trong phạm vi công cụ có thể đọc.

Ví dụ lệnh tham khảo:

~~~bash
liquibase --defaults-file=./config/legacy.properties snapshot
liquibase --defaults-file=./config/legacy.properties diff
liquibase --defaults-file=./config/legacy.properties diff-changelog
liquibase --defaults-file=./config/legacy.properties generate-changelog
~~~

Hãy xác nhận cú pháp qua <code>liquibase --help</code> của đúng phiên bản dự án. Các lệnh minh họa không khẳng định mọi phiên bản có cùng tên hoặc cùng tham số.

### 4.1. Diff không phải bằng chứng đầy đủ về tính tương đương

Kết quả diff phụ thuộc vào:

1. Loại object mà snapshot generator hỗ trợ.
2. Schema và catalog được đưa vào phạm vi so sánh.
3. Quyền đọc metadata của tài khoản kết nối.
4. Cách chuẩn hóa identifier, default, type và biểu thức DBMS.
5. Filter include/exclude và cấu hình so sánh.
6. Khả năng biểu diễn khác biệt bằng change type của Liquibase.

Một số khác biệt có thể được công cụ chuẩn hóa hoặc bỏ qua vì không thể so sánh portable; một số object có thể không được snapshot. Vì vậy, không dùng thông báo “no differences” như một chứng nhận rằng hai database giống hệt nhau ở mọi khía cạnh.

### 4.2. Đọc diff theo ba nhóm

| Nhóm | Ví dụ | Việc cần làm |
|---|---|---|
| Thiếu ở database đích | Table, column, FK hoặc view chưa có | Xác minh có chủ đích hay do migration chưa chạy |
| Thừa ở database đích | Object không có trong reference/changelog | Xác định object do DBA, app hoặc công cụ khác tạo; tránh xóa tự động |
| Khác định nghĩa | Kiểu, precision, default, index, constraint hoặc view khác | Đối chiếu DDL và ngữ nghĩa, quyết định sửa hay ghi nhận ngoại lệ |

Diff changelog là **bản nháp để review**, không phải changelog production đã được phê duyệt. Generated changes có thể thiếu trigger, grant, function, đặc tính index hoặc phần định nghĩa đặc thù. Người review phải so với inventory và yêu cầu ứng dụng.

### 4.3. Không tạo baseline bằng cách “chạy thử update” trên database legacy

Nếu database đã có các bảng/đối tượng mà changelog mô tả, chạy <code>update</code> như một database trống có thể gây lỗi “object already exists” hoặc làm thay đổi dữ liệu/metadata không mong muốn.

Quy trình tiếp nhận thường gồm:

1. Chụp inventory và trạng thái schema thực tế.
2. Tạo changelog baseline mô tả trạng thái được chấp nhận.
3. Review baseline với catalog và DDL gốc.
4. Dùng cơ chế đồng bộ lịch sử như <code>changelog-sync</code> khi đã chứng minh database **đã ở đúng trạng thái mà các changeset baseline mô tả**.
5. Chạy diff/validation sau baseline để phát hiện khác biệt chưa được quản lý.

<code>changelog-sync</code> đánh dấu các changeset trong phạm vi được chọn là đã thực hiện trong lịch sử Liquibase mà không thực thi các change của chúng. Vì vậy, nếu baseline thiếu một index hoặc constraint nhưng vẫn sync, lịch sử sẽ nói changeset đã chạy dù object chưa có. Đây là sai lệch nguy hiểm.

Không dùng <code>changelog-sync</code> để né lỗi triển khai; phải xác minh schema trước, review filter/contexts/labels và hiểu chính xác những changeset nào được đánh dấu.

## 5. Rà soát đối tượng dễ bị bỏ sót theo từng nhóm

### 5.1. Constraint và index

Không chỉ ghi nhận “bảng có primary key”. Cần kiểm tra:

- Primary key gồm cột nào và thứ tự ra sao?
- Có unique constraint trên tổ hợp cột nào?
- Foreign key trỏ tới schema/table/column nào; có <code>ON DELETE</code>/<code>ON UPDATE</code> đặc biệt không?
- Check constraint có biểu thức gì, có bị disable hoặc chưa validate không?
- Index là unique, partial/filtered, expression, include/covering hay index theo operator class?
- Index có trạng thái valid/usable không? Có phải index phục vụ constraint hay được tạo riêng cho truy vấn?

Ví dụ, hai database đều có index tên <code>idx_orders_status</code> chưa chứng minh chúng tương đương. Một index có thể chỉ trên <code>status</code>, index kia trên <code>(tenant_id, status)</code>; một cái có predicate <code>WHERE deleted_at IS NULL</code>, cái còn lại không. Cần so định nghĩa và mục đích.

### 5.2. Sequence và cơ chế sinh giá trị

Kiểm tra xem khóa được sinh bằng:

- Sequence riêng và <code>nextval</code>.
- Identity column.
- Auto-increment.
- Default expression.
- Trigger tự gán khóa.
- Ứng dụng tự sinh UUID hoặc ID.

Đối chiếu cả giá trị hiện tại/next value và cách đồng bộ sau import dữ liệu. Nếu sequence đứng sau giá trị ID lớn nhất, lần insert tiếp theo có thể va chạm khóa. Ngược lại, tự đặt sequence về MAX(id)+1 trong lúc có writer hoạt động có thể tạo race condition.

### 5.3. View, materialized view và logic trong DB

Một view có thể phụ thuộc nhiều bảng, view khác, function, synonym hoặc schema khác. Cần ghi nhận:

- Định nghĩa SQL đầy đủ, schema và owner.
- Các bảng/view/function được tham chiếu.
- Quyền thực thi và chế độ security/invoker/definer theo DBMS.
- Có materialized data, index hoặc lịch refresh không?
- View có được ứng dụng dùng trực tiếp hay qua ORM?

Trigger và function thường bị bỏ sót vì không nằm trong danh sách bảng/cột. Một trigger ghi audit hoặc cập nhật cột dẫn xuất có thể là một phần của invariant nghiệp vụ. Nếu baseline bỏ nó, ứng dụng vẫn khởi động nhưng dữ liệu mới không còn được ghi audit hoặc tính toán như trước.

### 5.4. Partition và đối tượng phụ thuộc vận hành

Với bảng partition, inventory cần ghi:

- Bảng cha/partitioned table và từng partition hiện có.
- Quy tắc range/list/hash và partition key.
- Default partition, partition tương lai được tạo tự động hay thủ công.
- Index/constraint có được tạo trên parent và đồng bộ xuống partition không?
- Job tạo, detach, archive hoặc drop partition.

Không coi từng partition là bảng nghiệp vụ độc lập nếu Liquibase hoặc ứng dụng quản lý chúng thông qua parent. Cũng không bỏ qua partition chỉ vì một công cụ diff hiển thị parent table mà không trình bày đầy đủ các con.

### 5.5. Role, grant và chính sách bảo mật

Một database legacy có thể dựa vào:

- Quyền SELECT/INSERT/UPDATE/DELETE trên table hoặc view.
- Quyền EXECUTE trên function/procedure.
- Default privileges cho object tạo mới.
- Role kế thừa, schema usage/create và quyền sequence.
- Row-level security policy hoặc view security.

Nếu chỉ tiếp nhận DDL mà bỏ quyền, ứng dụng có thể mất truy cập sau deploy. Ngược lại, cấp rộng hơn để “sửa lỗi permission” có thể tạo rủi ro bảo mật. Phải xác định owner của quyền và nơi quản lý chúng; không nhất thiết mọi role/user đều được đưa vào changelog ứng dụng.

## 6. Đối chiếu kiểu dữ liệu: tên kiểu giống nhau chưa chắc cùng ngữ nghĩa

Khi so sánh kiểu dữ liệu, không chỉ đọc tên tổng quát như <code>varchar</code>, <code>timestamp</code> hay <code>decimal</code>. Cần so:

- Kiểu vật lý thực tế theo DBMS.
- Precision, scale, độ dài và đơn vị đo.
- Signed/unsigned, range và biểu diễn NULL.
- Charset, collation và quy tắc so sánh.
- Default expression, generated/identity attribute.
- Quy tắc chuyển đổi, làm tròn, timezone và serialization của ứng dụng.

### 6.1. Số nguyên và kiểu số

| Khía cạnh | Ví dụ khác biệt | Rủi ro khi tiếp nhận |
|---|---|---|
| Range | SMALLINT/INTEGER/BIGINT | ID hoặc số đếm vượt miền kiểu đích |
| Signed/unsigned | BIGINT unsigned so với BIGINT signed | Một nửa miền giá trị hoặc giới hạn trên khác nhau |
| Decimal precision | <code>DECIMAL(10,2)</code> so với <code>DECIMAL(12,4)</code> | Mất phần thập phân, overflow hoặc làm tròn |
| Float | REAL/FLOAT/DOUBLE | Sai số biểu diễn, so sánh bằng tuyệt đối không an toàn |
| Identity/sequence | Cùng kiểu BIGINT nhưng cơ chế cấp ID khác | Va chạm ID, sequence lệch sau import |

Đối với tiền tệ, thường cần kiểu decimal với precision/scale đã thống nhất; không thay decimal bằng floating point chỉ vì ORM map cả hai về kiểu số trong ngôn ngữ ứng dụng. Trước khi thu hẹp precision, phải thống kê MIN/MAX, số chữ số phần nguyên và số chữ số thập phân đang tồn tại.

### 6.2. Chuỗi, charset và collation

Độ dài <code>VARCHAR(100)</code> có thể được tính theo ký tự hoặc byte tùy DBMS/kiểu cột. Charset và collation quyết định những ký tự nào biểu diễn được, cách so sánh, sắp xếp và tính duy nhất.

Những câu hỏi phải trả lời:

- Cột đang dùng UTF-8 hay charset khác?
- Độ dài giới hạn theo byte hay ký tự?
- So sánh có phân biệt hoa/thường, dấu hay không?
- Unique index có coi <code>ABC</code> và <code>abc</code> là trùng nhau không?
- Chuỗi có trailing spaces hoặc quy tắc chuẩn hóa Unicode đặc biệt không?

Một unique constraint có thể bắt đầu thất bại sau khi chuyển sang collation khác vì nhiều giá trị trước đây được coi là khác nhau nay được coi là bằng nhau. Hãy phát hiện duplicate theo **quy tắc so sánh đích** trước khi chuyển.

### 6.3. Date, time và timezone

Không coi các kiểu <code>DATE</code>, <code>TIME</code>, <code>TIMESTAMP</code> và <code>TIMESTAMP WITH TIME ZONE</code> là tương đương:

- <code>DATE</code> có thể chỉ chứa ngày, không có giờ.
- Timestamp không timezone có thể lưu thời gian địa phương theo quy ước ứng dụng.
- Timestamp có timezone có thể biểu diễn thời điểm tuyệt đối, nhưng cách lưu/hiển thị phụ thuộc DBMS.
- Một cột epoch integer có thể được ứng dụng chuyển đổi ở tầng code.

Trước khi thay kiểu, xác định dữ liệu là “thời điểm xảy ra” hay “giờ địa phương theo lịch”. Kiểm tra daylight saving, timezone session, dữ liệu lịch sử và cách ứng dụng serialize/deserialize. Không tự gắn UTC cho dữ liệu cũ nếu chưa biết timezone gốc.

### 6.4. Boolean, enum và kiểu riêng

Một DBMS có thể biểu diễn boolean bằng kiểu riêng; DBMS khác dùng số hoặc ký tự. Enum có thể là type riêng, CHECK constraint hoặc VARCHAR với quy tắc ứng dụng. Domain, composite, array, JSON, UUID, XML, spatial và binary cũng có mức hỗ trợ khác nhau.

Khi chuyển hệ quản trị hoặc chuẩn hóa schema:

- Liệt kê toàn bộ giá trị enum đang tồn tại, kể cả giá trị hiếm.
- Xác định cách lưu NULL, giá trị mặc định và giá trị chưa biết.
- Kiểm tra JSON schema/shape thực tế nếu ứng dụng dựa vào cấu trúc bên trong.
- Kiểm tra index/operator class hoặc truy vấn đặc thù cho JSON, array, spatial.
- Xác định có cần giữ nguyên kiểu riêng bằng SQL đặc thù hay chuyển thành kiểu portable.

Đừng đổi enum thành VARCHAR và bỏ constraint mà không ghi lại tập giá trị hợp lệ; làm như vậy có thể khiến dữ liệu không hợp lệ xuất hiện mà trước đó DBMS đã ngăn.

## 7. Đối chiếu dữ liệu và ngữ nghĩa, không chỉ kiểu cột

Hai cột có cùng kiểu vật lý vẫn có thể khác nghĩa:

- <code>amount</code> là tiền VND ở database này, nhưng là đơn vị cent ở database khác.
- <code>status</code> dùng mã số 1/2/3 ở nơi này và chuỗi <code>NEW/PAID/CANCELLED</code> ở nơi khác.
- <code>created_at</code> lưu UTC ở một hệ thống, giờ địa phương ở hệ thống khác.
- <code>is_deleted</code> có thể dùng 0/1 hoặc NULL mang nghĩa chưa xác định.
- <code>customer_id</code> có thể là ID toàn cục hoặc chỉ duy nhất trong từng tenant.

Lập data dictionary ghi rõ:

| Thuộc tính | Nội dung cần ghi |
|---|---|
| Tên cột và object | Schema/table/column chính xác |
| Kiểu vật lý | DBMS type, precision/scale/length |
| Nullability/default | Có thể NULL không, default expression là gì |
| Miền giá trị | Enum, range, pattern hoặc constraint |
| Đơn vị/ý nghĩa | Tiền tệ, timezone, mã trạng thái, tenant scope |
| Nguồn ghi | API, batch, ETL, trigger, import |
| Nguồn đọc | Service, báo cáo, BI, tích hợp |
| Quy tắc chuyển đổi | Mapping, rounding, normalization, fallback |
| Người xác nhận | Owner kỹ thuật/nghiệp vụ và bằng chứng |

Nếu chưa xác định được ngữ nghĩa, không nên thay đổi kiểu hoặc chuẩn hóa dữ liệu trong cùng đợt tiếp nhận baseline. Ghi nhận thành ngoại lệ có owner và xử lý trong một migration riêng có kiểm chứng.

## 8. Xây dựng dependency graph giữa các đối tượng

Một dependency graph mô tả đối tượng nào cần tồn tại trước đối tượng nào. Ví dụ:

~~~text
schema
  ├── custom type / domain
  ├── sequence
  └── table cha
        ├── primary key / unique
        ├── table con
        │     └── foreign key tới bảng cha
        ├── index
        └── trigger → function
              └── view / procedure có thể sử dụng bảng
~~~

Đây là sơ đồ khái niệm; quan hệ cụ thể tùy DBMS và object. Một số dependency có thể tạo thành chu trình: hai bảng tham chiếu lẫn nhau, view/function gọi qua lại hoặc procedure phụ thuộc đối tượng được tạo sau. Khi đó cần chiến lược tạo trước rồi bổ sung constraint/definition sau, hoặc dùng cú pháp placeholder phù hợp DBMS.

### 8.1. Những loại phụ thuộc cần ghi nhận

| Quan hệ | Ví dụ | Thứ tự/điều cần chú ý |
|---|---|---|
| Namespace → object | Schema chứa table, sequence, view | Namespace phải tồn tại trước |
| Type → column | Domain/enum/composite type được dùng trong column | Type cần được tạo trước table/column |
| Sequence → default/column | Default gọi next value từ sequence | Sequence và quyền phải sẵn sàng |
| Parent key → FK | Bảng con tham chiếu PK/UNIQUE của bảng cha | Khóa đích phải tồn tại và phù hợp |
| Table/column → index | Index trên một hoặc nhiều cột | Bảng/cột phải tồn tại |
| Table → trigger → function | Trigger gọi function khi INSERT/UPDATE/DELETE | Function phải tồn tại trước trigger |
| Table/view → view | View tham chiếu bảng hoặc view khác | Tạo theo dependency order |
| Function → function | Function gọi function khác | Xử lý chu trình và signature |
| Object → grant | Role cần quyền trên table/view/sequence | Object tồn tại trước grant; role phải được provision |
| Partition parent → partition | Partition thuộc bảng phân vùng | Parent, partition key và quy tắc phải phù hợp |

### 8.2. Phụ thuộc vòng và cách tách migration

Giả sử <code>employee.manager_id</code> tham chiếu <code>employee.id</code> trong cùng bảng. Tự tham chiếu thường có thể được tạo sau khi bảng và khóa chính tồn tại. Với hai bảng A/B tham chiếu lẫn nhau, có thể:

1. Tạo cả hai bảng trước, ban đầu chưa tạo FK.
2. Tạo primary key/unique key cần thiết.
3. Thêm FK ở changeset sau khi cả hai phía đã tồn tại.
4. Kiểm tra dữ liệu và thứ tự triển khai.

Không cố tạo tất cả đối tượng và constraint trong một changeset khổng lồ để tránh xử lý dependency. Tách theo các trạng thái có thể kiểm tra giúp xác định chính xác điểm thất bại.

### 8.3. Phụ thuộc ngoài database

Dependency graph không chỉ có node là object DB. Cần thêm:

- API/service đọc hoặc ghi table.
- ORM entity và mapping.
- Job ETL, batch import, scheduled task.
- Dashboard, stored report và BI query.
- CDC, replication, data warehouse và consumer.
- Quyền của runtime user và migration user.
- Script backup, archive, partition maintenance.

Một bảng có thể không được service chính dùng trực tiếp nhưng vẫn được hệ thống báo cáo cuối tháng đọc. Bỏ sót loại phụ thuộc này có thể không phát hiện ở staging nhưng gây sự cố sau ngày chốt sổ.

## 9. Định nghĩa SQL của object và khác biệt do DBMS

Khi tiếp nhận database, cần lưu lại DDL thực tế hoặc một dạng mô tả tương đương đủ chi tiết để reviewer xác nhận. Với object đặc thù, snapshot/diff có thể không phản ánh toàn bộ định nghĩa.

### 9.1. Các thuộc tính cần so

| Đối tượng | Nội dung phải đối chiếu |
|---|---|
| Table | Column order khi có ý nghĩa, type, nullability, default, generated/identity, partition, storage option |
| Constraint | Loại, cột, thứ tự, biểu thức, tên, trạng thái enabled/validated |
| Index | Unique, column/expression, thứ tự ASC/DESC, predicate, include, method, tablespace |
| View | SQL đầy đủ, dependency, security mode, check option |
| Trigger | Event, timing, row/statement, condition, function/body, enabled state |
| Function/procedure | Signature, return type, language, body, volatility/security/execute privilege |
| Sequence | Start, increment, min/max, cache, cycle, current value và liên kết với cột |
| Grant/policy | Principal, quyền, scope, inheritance và predicate |

Tên giống nhau không đủ chứng minh định nghĩa giống nhau. Ví dụ, trigger có thể tồn tại nhưng bị disable; index có thể tồn tại nhưng invalid; FK có thể tồn tại nhưng chưa validate dữ liệu lịch sử.

### 9.2. Identifier và chữ hoa/thường

Quy tắc identifier khác nhau theo DBMS. PostgreSQL gập identifier không trích dẫn về chữ thường; Oracle thường gập về chữ hoa; MySQL phụ thuộc hệ điều hành, filesystem và cấu hình; SQL Server chịu ảnh hưởng collation. Một tên hiển thị từ công cụ có thể đã được chuẩn hóa.

Trong inventory, nên ghi cả:

- Tên schema/table/column hiển thị trong catalog.
- Tên được viết trong SQL/ORM.
- Cách quoting được sử dụng.
- Quy tắc <code>objectQuotingStrategy</code> nếu changelog dùng Liquibase.

Đừng tự đổi CamelCase sang snake_case ngay khi baseline nếu chưa kiểm tra các truy vấn và ứng dụng hiện tại. Đổi tên đối tượng là một migration riêng có tác động tới mọi dependency.

## 10. Ví dụ rà soát kiểu dữ liệu và dữ liệu thực tế

### 10.1. Decimal precision/scale

Giả sử database legacy có cột <code>invoice.amount DECIMAL(18,4)</code>, còn mô hình mới định nghĩa <code>DECIMAL(12,2)</code>. Trước khi thu hẹp:

~~~sql
SELECT
    MAX(ABS(amount)) AS max_abs_amount,
    COUNT(*) AS row_count
FROM invoice;
~~~

Truy vấn này giúp xem độ lớn, nhưng chưa đủ để xác định có mất phần thập phân hay không. Cần thống kê số chữ số sau dấu thập phân và kiểm tra giá trị có vượt precision đích. Cách viết truy vấn chính xác để đo số chữ số phụ thuộc DBMS và kiểu dữ liệu.

Không chuyển kiểu bằng một câu ALTER TABLE đơn giản nếu có nguy cơ làm tròn hoặc overflow. Nên thử trên bản sao dữ liệu, so sánh trước/sau và có phương án lưu giá trị gốc khi cần phục hồi.

### 10.2. Phát hiện giá trị chuỗi không thuộc miền hợp lệ

Giả sử ứng dụng mới chỉ chấp nhận <code>NEW</code>, <code>PAID</code>, <code>CANCELLED</code>, nhưng database legacy có thể chứa mã khác:

~~~sql
SELECT status, COUNT(*) AS row_count
FROM customer_order
GROUP BY status
ORDER BY status;
~~~

Đối chiếu kết quả với data dictionary và code ứng dụng. Không xóa hoặc tự map giá trị lạ thành <code>NEW</code> chỉ để thêm CHECK constraint. Những giá trị không rõ nghĩa cần được owner nghiệp vụ xác nhận.

### 10.3. Phát hiện NULL và default

~~~sql
SELECT
    COUNT(*) AS total_rows,
    SUM(CASE WHEN created_at IS NULL THEN 1 ELSE 0 END) AS null_created_at
FROM customer_order;
~~~

Phải phân biệt:

- Cột nullable và dữ liệu hiện không có NULL.
- Cột NOT NULL ở metadata.
- Cột có default ở database.
- Ứng dụng tự điền giá trị nhưng DB không có default.

Những trạng thái trên khác nhau khi ứng dụng cũ/new, ETL hoặc script SQL trực tiếp thực hiện INSERT.

## 11. Từ inventory tới baseline Liquibase

Một quy trình tiếp nhận an toàn nên có các bước sau:

### Bước 1 — Đóng băng phạm vi và ghi nhận trạng thái gốc

Chốt database/schema, DBMS/version, danh sách owner và quyền đọc metadata. Lưu snapshot, DDL export hoặc báo cáo catalog có thời điểm, đồng thời ghi nhận những thao tác thủ công đang diễn ra.

Nếu database tiếp tục thay đổi trong lúc kiểm kê, phải có cách xác định thời điểm snapshot và những thay đổi xảy ra sau đó. Không so một bản DDL cũ với trạng thái hiện tại rồi kết luận không có drift.

### Bước 2 — Lập inventory và dependency graph

Ghi tất cả object, kiểu dữ liệu, trạng thái, owner, dependency và nguồn xác minh. Đánh dấu object không được Liquibase snapshot hoặc không có change type tương ứng.

### Bước 3 — So sánh và phân loại khác biệt

Dùng snapshot/diff trong phạm vi hỗ trợ, sau đó đối chiếu với catalog, DDL export, source code và job. Phân biệt:

- Khác biệt có chủ ý.
- Drift do thao tác thủ công.
- Object bị thiếu khỏi changelog.
- Object không còn sử dụng nhưng chưa có quyết định xóa.
- Khác biệt kiểu dữ liệu có thể gây mất mát.

### Bước 4 — Thiết kế baseline theo dependency order

Tạo changelog theo thứ tự hợp lý: schema/type/sequence, table và khóa cơ bản, index/constraint, view/function/trigger và quyền theo chính sách quản lý. Với phụ thuộc vòng, tách phần tạo object và phần thêm constraint.

### Bước 5 — Review baseline và xác minh với database thực

Review SQL sinh ra và DDL tương ứng. Chạy trên một database trống hoặc bản sao kiểm thử để xác nhận baseline có thể tái tạo trạng thái dự kiến. So sánh kết quả sau khi triển khai với database nguồn bằng diff và truy vấn catalog bổ sung.

### Bước 6 — Đồng bộ lịch sử cho database legacy

Chỉ sau khi chứng minh database hiện tại khớp với baseline, mới dùng cơ chế như <code>changelog-sync</code> để đánh dấu các changeset nền đã được áp dụng. Kiểm tra kỹ contexts, labels, DBMS filters và các changeset được chọn.

### Bước 7 — Tiếp tục quản lý thay đổi

Changelog baseline trở thành mốc lịch sử. Các thay đổi mới nên được thêm bằng changeset mới; không sửa changeset đã triển khai để phản ánh drift. Duy trì kiểm tra diff định kỳ để phát hiện thay đổi ngoài Liquibase.

## 12. Cấu trúc báo cáo inventory có thể kiểm toán

Một báo cáo tiếp nhận tối thiểu nên có:

| Trường | Nội dung |
|---|---|
| Object ID | DBMS, schema, object type và tên đầy đủ |
| Definition | DDL hoặc metadata đủ để tái dựng/so sánh |
| Data type details | Kiểu, precision/scale/length, collation, timezone, default, NULL |
| Dependencies | Object DB và service/job/app phụ thuộc |
| Runtime usage | Nguồn đọc/ghi, tần suất, thời điểm cao điểm/định kỳ |
| Ownership | Team/owner nghiệp vụ và DBA chịu trách nhiệm |
| Management method | Liquibase, SQL đặc thù, DBA, nền tảng khác hoặc ngoài phạm vi |
| Snapshot evidence | Thời điểm, tool/version, schema scope, principal và filter |
| Risk | Mất dữ liệu, lock, incompatibility, security hoặc drift |
| Decision | Giữ nguyên, đưa vào baseline, chuyển đổi, thay thế hay loại bỏ |
| Validation | Cách chứng minh object/type/dependency đúng sau triển khai |

Không ghi secret, mật khẩu hoặc thông tin xác thực trong báo cáo. Với object nhạy cảm, lưu DDL/metadata theo chính sách truy cập của tổ chức.

### 12.1. Ví dụ một mục inventory

| Trường | Giá trị minh họa |
|---|---|
| Object | <code>sales.customer_order.status</code> |
| Type | <code>VARCHAR(16)</code>, nullable, không có DB default |
| Values | <code>NEW</code>, <code>PAID</code>, <code>VOID</code>, <code>UNKNOWN_LEGACY</code> |
| Dependencies | API Orders, job settlement, báo cáo cuối ngày |
| Risk | Ứng dụng mới không nhận <code>UNKNOWN_LEGACY</code> |
| Decision | Giữ nguyên trong baseline; mapping nghiệp vụ là migration riêng |
| Evidence | Catalog, DDL export, query phân bố giá trị và source references |

Mục này cho thấy một cột không chỉ là type và name. Giá trị hiếm và job cuối ngày có thể quyết định khả năng tương thích của toàn bộ đợt tiếp nhận.

## 13. Các lỗi thường gặp khi rà soát

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ inventory table/column | Bỏ trigger, sequence, view, procedure, grants | Dùng checklist theo loại object và xác minh catalog |
| Snapshot bằng role thiếu quyền | Kết quả thiếu schema/object nhưng bị hiểu là không tồn tại | Kiểm tra quyền đọc metadata và phạm vi schema |
| Tin tuyệt đối vào diff “no differences” | Bỏ qua object không được snapshot hoặc khác biệt không biểu diễn | Đối chiếu DDL export, catalog và dependency ngoài DB |
| Chạy generated changelog ngay trên legacy DB | Lỗi object exists hoặc thay đổi ngoài dự kiến | Review baseline và dùng quy trình đồng bộ lịch sử có kiểm chứng |
| Changelog baseline thiếu index/constraint | Liquibase tưởng trạng thái đã được quản lý nhưng DB khác thực tế | Đối chiếu định nghĩa, không chỉ tên object |
| So type bằng tên tổng quát | Mất precision, timezone, collation hoặc signed range | So thuộc tính đầy đủ và thử chuyển dữ liệu |
| Bỏ qua sequence hiện tại | Insert sau import va chạm ID | Kiểm tra current/next value và quy trình đồng bộ |
| Bỏ trigger/function | Logic audit hoặc cập nhật dữ liệu ngừng hoạt động | Kiểm tra DDL và nguồn gọi thực tế |
| Bỏ quyền hoặc RLS policy | App không truy cập được hoặc bị cấp quyền quá rộng | Quản lý grants/policy theo ownership rõ |
| Không ghi dependency của job định kỳ | Lỗi chỉ xuất hiện cuối tháng/quý | Bao quát chu kỳ vận hành và telemetry đủ dài |
| Sắp xếp changeset sai dependency | Tạo FK/view/trigger thất bại | Xây dependency graph, tách create và attach |
| Đồng nhất NULL với default | INSERT từ app cũ hoạt động khác | Xác minh metadata và thử từng luồng ghi |
| Đổi tên/kiểu trong lúc baseline | Nhiều thay đổi khó phân biệt với trạng thái gốc | Baseline trước; chuyển đổi là changeset riêng |
| Dùng changelog-sync khi baseline chưa khớp | DATABASECHANGELOG lệch với schema thực | Chỉ sync sau khi xác minh từng nhóm object |

## 14. Tích hợp với Spring Boot và CI/CD

Trong Spring Boot, ứng dụng thường truy cập database qua ORM, JDBC, native query, stored procedure hoặc nhiều datasource. ORM mapping là một nguồn inventory, nhưng không thể thay thế kiểm kê DB: nó không nhất thiết biết về trigger, view, index đặc thù, quyền, job DBA hoặc bảng chỉ được báo cáo sử dụng.

### 14.1. Các nguồn phụ thuộc ứng dụng cần rà soát

- Entity, embeddable, relationship và naming strategy của ORM.
- Native SQL, JPQL, stored procedure call và view mapping.
- Batch job, scheduled task, migration script bên ngoài.
- Report, BI, ETL, CDC và consumer dữ liệu.
- Cấu hình datasource, schema mặc định, search path và migration user.
- Các phiên bản ứng dụng còn chạy trong rolling deployment.

Nếu ứng dụng có nhiều datasource, cần biết changelog nào quản lý database nào. Không để một baseline được chạy nhầm lên datasource chỉ vì profile Spring đã resolve sai URL.

### 14.2. Pipeline tiếp nhận

~~~text
Chốt database + DBMS/version + phạm vi schema
                 |
                 v
Đọc catalog / export DDL / snapshot
                 |
                 v
Inventory object + kiểu dữ liệu + dependency
                 |
                 v
Đối chiếu source code / job / quyền / báo cáo
                 |
                 v
Diff + phân loại thiếu/thừa/khác định nghĩa
                 |
                 v
Thiết kế baseline + review theo dependency order
                 |
                 v
Test tái tạo trên database kiểm thử
                 |
                 v
So sánh trạng thái sau test + phê duyệt
                 |
                 v
Changelog-sync trên database legacy đã xác minh
                 |
                 v
Diff/validation định kỳ để phát hiện drift
~~~

Pipeline nên lưu phiên bản Liquibase, JDBC driver, DBMS version, artifact/changelog digest, thời điểm snapshot và danh sách schema/filter. Không chỉ lưu file generated changelog rồi coi đó là bằng chứng tiếp nhận hoàn tất.

### 14.3. Sau khi baseline: phát hiện drift

Có thể chạy diff định kỳ giữa database đang vận hành và reference/changelog hoặc schema chuẩn theo cách phù hợp. Kết quả cần phân loại:

- Drift được phê duyệt nhưng chưa được ghi vào changelog.
- Drift do DBA thao tác khẩn cấp.
- Drift do ứng dụng hoặc tool tạo object tự động.
- Sai khác ngoài dự kiến hoặc dấu hiệu can thiệp trái quy trình.

Không tự động tạo changeset và áp lên production chỉ vì diff phát hiện khác biệt. Trước tiên phải xác định object nào là nguồn chuẩn và ai sở hữu thay đổi.

## 15. Checklist hoàn tất tiếp nhận database legacy

- [ ] DBMS, phiên bản, database/catalog, schema và quyền đọc metadata đã được ghi nhận.
- [ ] Inventory bao gồm table, column, partition, constraint, index, sequence, view, trigger, function, procedure, type, synonym, extension và grant phù hợp.
- [ ] Object không được snapshot/diff hỗ trợ đã có cách kiểm kê bổ sung.
- [ ] Đối tượng tạm, generated, externally managed và out-of-scope có owner/lý do.
- [ ] Kiểu dữ liệu đã so precision/scale/length, signedness, collation, charset, timezone, default, identity và NULL.
- [ ] Data dictionary ghi miền giá trị, đơn vị và ngữ nghĩa nghiệp vụ quan trọng.
- [ ] Đã kiểm tra giá trị hiếm, duplicate, NULL, orphan và dữ liệu có thể mất khi chuyển kiểu.
- [ ] Dependency graph bao gồm quan hệ DB và ứng dụng/job/báo cáo/tích hợp.
- [ ] Baseline sắp xếp theo dependency order và đã xử lý chu trình phụ thuộc.
- [ ] DDL đặc thù, trigger/function, quyền và trạng thái constraint/index đã được review.
- [ ] Generated changelog không được coi là hoàn chỉnh nếu chưa đối chiếu catalog và source.
- [ ] Database kiểm thử có thể được tái tạo từ baseline và so sánh với trạng thái kỳ vọng.
- [ ] Changelog-sync chỉ được thực hiện sau khi schema legacy đã khớp baseline được duyệt.
- [ ] Sau đồng bộ, DATABASECHANGELOG và object vật lý nhất quán.
- [ ] Có quy trình diff/drift định kỳ, owner xử lý và lưu bằng chứng.

## 16. Kết luận

Tiếp nhận database legacy bằng Liquibase không dừng ở việc tạo changelog từ danh sách bảng. Cần kiểm kê **toàn bộ đối tượng**, so sánh **kiểu dữ liệu và ngữ nghĩa**, đồng thời hiểu **phụ thuộc giữa DB object và những ứng dụng/job đang sử dụng chúng**. Snapshot, diff và generated changelog giúp tăng tốc nhưng có giới hạn về quyền, phạm vi, loại object và khả năng biểu diễn; chúng phải được đối chiếu với catalog, DDL, source code và bằng chứng vận hành.

Quy trình đáng tin cậy là **xác định phạm vi → inventory → phân tích type/data → lập dependency graph → review baseline → thử tái tạo → xác minh schema legacy → đồng bộ lịch sử → theo dõi drift**. Chỉ khi các đối tượng quan trọng, kiểu dữ liệu và phụ thuộc đã được giải thích thì database mới thực sự sẵn sàng được quản lý lâu dài bằng changelog, changeset, precondition, checksum và quy trình CI/CD.
