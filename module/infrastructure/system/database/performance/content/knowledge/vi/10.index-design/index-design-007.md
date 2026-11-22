# Chi phí ghi, dung lượng và bộ đệm của mỗi chỉ mục

Chỉ mục giúp DBMS tìm hàng nhanh hơn, nhưng mỗi chỉ mục được tạo ra đều cần không gian lưu trữ, bộ nhớ đệm và công việc duy trì khi dữ liệu thay đổi. Một bảng có nhiều chỉ mục có thể phục vụ tốt nhiều truy vấn đọc, đồng thời làm INSERT, UPDATE và DELETE chậm hơn, tăng lượng log phải ghi và chiếm thêm cache. Vì vậy, thiết kế chỉ mục là bài toán cân bằng giữa lợi ích đọc và chi phí duy trì trong toàn bộ workload.

Trong module **DATABASE_PERFORMANCE**, tối ưu hiệu năng cần dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Chương **Thiết kế chỉ mục** giúp người học đánh giá chi phí ghi, dung lượng và bộ đệm của từng chỉ mục. Bài học giải thích cách DBMS cập nhật index khi dữ liệu thay đổi, vì sao index rộng hoặc dư thừa làm tăng write amplification, cách kích thước index ảnh hưởng đến cache và I/O, cũng như cách đo để quyết định nên giữ, điều chỉnh hay loại bỏ một chỉ mục.

Sau bài học, người học có thể:

- Mô tả công việc DBMS phải thực hiện khi INSERT, UPDATE và DELETE trên bảng có nhiều index.
- Giải thích tác động của số lượng, độ rộng, số tầng và mức phân mảnh của index đến dung lượng và cache.
- Phân biệt chi phí ghi dữ liệu, ghi index, ghi log và công việc dọn dẹp phiên bản cũ.
- Đánh giá ảnh hưởng của index đến HOT update, page split, buffer cache và write amplification.
- Nhận diện index dư thừa, ít được sử dụng hoặc có lợi ích thấp so với chi phí.
- Đo chi phí và lợi ích bằng thống kê của PostgreSQL cùng các chỉ số tương đương ở hệ quản trị khác.
- Đề xuất thay đổi có kiểm soát và xác nhận kết quả bằng workload đại diện.

## 1. Chỉ mục có chi phí trong toàn bộ vòng đời dữ liệu

### 1.1. Index không chỉ được sử dụng khi đọc

Khi một truy vấn SELECT dùng index, DBMS đọc cấu trúc index để tìm khóa và xác định vị trí hàng cần truy cập. Nhưng index cũng tham gia vào đường ghi. Mỗi khi dữ liệu thay đổi, DBMS phải bảo đảm mọi index liên quan vẫn phản ánh đúng trạng thái dữ liệu đã commit và đáp ứng các ràng buộc.

Với một bảng có nhiều index, một thao tác ghi có thể phải:

- Ghi hoặc sửa trang dữ liệu của bảng.
- Tìm vị trí thích hợp trong từng B-tree index.
- Chèn hoặc xóa entry trong các index liên quan.
- Tách trang nếu trang index không còn đủ chỗ.
- Ghi WAL, redo log hoặc transaction log để hỗ trợ phục hồi.
- Cập nhật thống kê và cấu trúc quản lý không gian theo cơ chế của engine.
- Tạo thêm công việc cho checkpoint, background writer, vacuum hoặc purge về sau.

Một câu INSERT đơn giản có thể tạo một hàng trong bảng nhưng đồng thời phải thêm entry vào primary index, unique index và nhiều secondary index. Khi số index tăng, số cấu trúc phải duy trì cũng tăng.

Không phải mọi index đều bị thay đổi trong mọi UPDATE. Nếu câu lệnh chỉ sửa một cột không liên quan đến index, một số engine có thể tránh sửa entry tương ứng. Tuy nhiên, nếu cập nhật cột khóa, cột INCLUDE, biểu thức index hoặc cột ảnh hưởng đến điều kiện của partial index, DBMS có thể phải cập nhật cấu trúc liên quan. Cần hiểu quy tắc cụ thể của hệ quản trị.

### 1.2. Ví dụ về chi phí của nhiều index

Giả sử bảng **orders** có các index sau:

~~~sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL
);

CREATE INDEX idx_orders_customer
    ON orders (customer_id);

CREATE INDEX idx_orders_status
    ON orders (status);

CREATE INDEX idx_orders_created
    ON orders (created_at);

CREATE INDEX idx_orders_customer_created
    ON orders (customer_id, created_at);
~~~

Một thao tác INSERT có thể phải tạo entry cho primary key và cả bốn index phụ. Nếu ứng dụng ghi 5.000 đơn hàng mỗi giây, DBMS phải duy trì hàng chục nghìn index entry mỗi giây, ngoài phần ghi bảng và log.

Một thao tác UPDATE chỉ đổi **status** có thể cần sửa index **idx_orders_status**, trong khi index theo customer_id hoặc created_at có thể không cần thay đổi. Tuy nhiên, nếu index có chứa cột được cập nhật như một cột INCLUDE hoặc biểu thức phụ thuộc vào cột đó, việc duy trì index vẫn có thể phát sinh.

Ví dụ này cho thấy số lượng index không phải chi phí trừu tượng. Nó gắn với tần suất ghi, số cột thay đổi và cấu trúc từng index.

### 1.3. Đọc nhanh hơn có thể làm ghi chậm hơn

Một index mới có thể giảm số dòng phải quét và số trang phải đọc cho truy vấn quan trọng. Nhưng index cũng có thể:

- Làm tăng thời gian INSERT do phải thêm entry.
- Làm tăng thời gian UPDATE nếu cột index thay đổi.
- Làm tăng thời gian DELETE do phải xóa hoặc đánh dấu entry cũ.
- Tăng WAL/redo/transaction log và lưu lượng replication.
- Chiếm dung lượng backup và thời gian khôi phục.
- Làm tăng áp lực lên cache vì có thêm trang index.
- Tăng công việc bảo trì như vacuum, purge, rebuild hoặc thống kê.

Không thể đánh giá một index chỉ bằng thời gian của truy vấn SELECT được hưởng lợi. Cần xem toàn bộ workload đọc/ghi và mục tiêu dịch vụ.

## 2. DBMS duy trì index khi ghi như thế nào?

### 2.1. INSERT

Với INSERT, DBMS tạo hàng mới trong bảng và thêm các entry cần thiết vào những index áp dụng cho hàng đó.

Đối với B-tree, engine tìm trang lá phù hợp với khóa, chèn entry theo thứ tự và cập nhật cấu trúc nếu cần. Nếu trang đã đầy, có thể xảy ra page split. Nếu index có unique constraint, DBMS còn phải kiểm tra tính duy nhất theo quy tắc giao dịch và mức cô lập.

Các yếu tố ảnh hưởng chi phí INSERT:

- Số index cần cập nhật.
- Độ rộng của khóa và payload trong index.
- Phân bố khóa mới: tăng tuần tự hay ngẫu nhiên.
- Mức lấp đầy trang và khả năng xảy ra page split.
- Mức đồng thời và tranh chấp trên các trang nóng.
- Tốc độ ghi log và khả năng flush log bền vững.
- Cache hit của các trang index cần sửa.

Một khóa tăng tuần tự thường giúp vị trí chèn tập trung ở vùng cuối cây, có thể cải thiện tính cục bộ và giảm split ở các trang giữa. Tuy nhiên, ở tải ghi rất cao, vùng cuối có thể trở thành điểm nóng. Khóa ngẫu nhiên phân tán điểm chèn nhưng có thể làm nhiều trang bị sửa, tăng split và giảm locality. Không có lựa chọn tối ưu chung; cần đo với phân bố ghi thực tế.

### 2.2. UPDATE

UPDATE có thể ảnh hưởng đến index theo hai cách:

- Nếu cột không tham gia index thay đổi, engine có thể chỉ sửa dữ liệu hàng và tránh sửa một số index.
- Nếu cột khóa index hoặc dữ liệu được lưu trong index thay đổi, DBMS cần cập nhật entry để truy vấn tiếp tục nhìn thấy giá trị mới theo đúng quy tắc MVCC hoặc locking của engine.

Một UPDATE có thể làm hàng chuyển vị trí nếu kích thước hàng tăng và trang cũ không đủ chỗ. Với heap table, điều này có thể tạo một phiên bản hàng mới ở trang khác. Index có thể phải trỏ đến vị trí mới tùy engine và cơ chế cập nhật.

Trong PostgreSQL, HOT (Heap-Only Tuple) update có thể tránh sửa các index khi các cột được cập nhật không được tham chiếu bởi index và phiên bản mới có thể được đặt trong cùng heap page. HOT giảm lượng index maintenance và WAL. Việc có index trên nhiều cột làm giảm cơ hội HOT khi các cột đó thường xuyên được cập nhật. Giữ một phần không gian trống trong heap page có thể giúp HOT xảy ra, nhưng đổi lại tăng dung lượng bảng.

Không nên coi HOT là bảo đảm cho mọi UPDATE không đổi khóa chính. Cần kiểm tra điều kiện cụ thể, fillfactor, loại index và các cột được index tham chiếu.

### 2.3. DELETE và phiên bản dữ liệu cũ

DELETE thường không lập tức xóa vật lý mọi byte của hàng và index entry. Trong hệ quản trị dùng MVCC như PostgreSQL và InnoDB, phiên bản cũ có thể phải được giữ đến khi không còn transaction nào cần nhìn thấy nó.

Hệ quả có thể gồm:

- Index entry cũ tiếp tục chiếm trang trong một khoảng thời gian.
- Trang hoặc bảng có thể cần vacuum/purge để thu hồi không gian có thể tái sử dụng.
- Tỷ lệ dead tuple hoặc garbage trong cấu trúc tăng nếu công việc dọn dẹp không theo kịp.
- Index có thể lớn hơn mức cần thiết cho tập dữ liệu hiện tại.
- Truy vấn phải xử lý thêm entry không còn hữu ích tùy cơ chế engine.

Trong PostgreSQL, VACUUM giúp thu hồi không gian có thể tái sử dụng và cập nhật visibility information; VACUUM thông thường không nhất thiết thu nhỏ file index hoặc bảng về kích thước nhỏ hơn trên hệ thống tệp. Trong InnoDB, purge xử lý các phiên bản cũ khi không còn cần thiết. Cách thu hồi và tái sử dụng trang khác nhau theo engine.

Vì vậy, cần tách chi phí của lệnh DELETE khỏi công việc dọn dẹp về sau. Một workload xóa nhiều dữ liệu có thể tiếp tục tạo áp lực I/O và CPU trong giai đoạn vacuum hoặc purge.

### 2.4. Unique index và ràng buộc

Unique index vừa hỗ trợ truy cập vừa bảo đảm dữ liệu không trùng theo khóa. Khi ghi, DBMS phải xác minh không có giá trị xung đột theo quy tắc của engine. Điều này là chi phí cần thiết để giữ tính đúng đắn.

Không nên loại bỏ unique index chỉ để tăng tốc ghi nếu nó đang bảo vệ một ràng buộc nghiệp vụ. Nếu muốn thay đổi cách bảo đảm uniqueness, phải có thiết kế thay thế bảo toàn đúng ngữ nghĩa và xử lý đồng thời. Tương tự, index hỗ trợ khóa ngoại có thể giúp kiểm tra và thực hiện thao tác liên quan hiệu quả hơn, nhưng cách DBMS tự tạo hoặc không tự tạo index cho phía tham chiếu khác nhau. Cần kiểm tra đúng engine.

## 3. Số lượng và độ rộng index ảnh hưởng dung lượng ra sao?

### 3.1. Những thành phần chiếm dung lượng

Một index B-tree thường chứa:

- Khóa dùng để sắp xếp và tìm kiếm.
- Row locator, TID, RID hoặc khóa định danh hàng tùy DBMS.
- Các cột INCLUDE hoặc payload nếu index hỗ trợ.
- Header, metadata và thông tin quản lý trang.
- Khoảng trống được để lại theo fill factor.
- Các entry cũ hoặc vùng chưa được thu hồi hoàn toàn tùy cơ chế engine.

Dung lượng phụ thuộc vào số hàng, độ rộng khóa, độ rộng locator, số cột bổ sung, kiểu dữ liệu, mức nén, page size, fill factor và mức phân mảnh.

Một index trên BIGINT thường nhỏ hơn đáng kể so với index trên nhiều cột chuỗi dài. Nhưng khóa nhỏ không tự động có nghĩa index tốt: cần xét độ chọn lọc, thứ tự truy cập và workload.

### 3.2. Composite index và chi phí của mỗi cột

Một composite index trên (customer_id, created_at, status) lưu khóa kết hợp. Nó có thể phục vụ các truy vấn lọc theo tiền tố phù hợp, nhưng mọi entry phải chứa thông tin của các cột khóa. Nếu thêm một cột dài, toàn bộ index có thể lớn hơn.

Ví dụ:

~~~sql
CREATE INDEX idx_orders_customer_created
ON orders (customer_id, created_at);
~~~

So với:

~~~sql
CREATE INDEX idx_orders_customer_created_status_amount
ON orders (customer_id, created_at, status, total_amount);
~~~

Index thứ hai có thể bao phủ nhiều truy vấn hơn, nhưng cũng chứa thêm status và total_amount. Điều này làm tăng dung lượng, số trang cần cache và công việc duy trì khi những cột đó thay đổi.

Không nên đưa mọi cột SELECT vào khóa chỉ để tránh lookup. Trong một số hệ quản trị, cột payload có thể được đặt ở phần INCLUDE để không tham gia thứ tự khóa; trong hệ khác, các cột thêm vào secondary index vẫn làm tăng cấu trúc index. Cần chọn đúng cú pháp và semantics của DBMS.

### 3.3. Khóa định danh được lặp trong secondary index

Một số hệ quản trị dùng khóa clustered hoặc primary key làm row locator trong các index phụ. Ví dụ:

- InnoDB lưu primary key trong mỗi secondary index entry.
- SQL Server dùng clustered key làm row locator cho nonclustered index khi bảng có clustered index.

Do đó, khóa chính rộng có thể làm tất cả index phụ tăng kích thước. Tác động nhân lên theo số index, chứ không chỉ nằm trong primary index.

Nếu bảng có nhiều secondary index, việc chọn khóa định danh gọn và ổn định có thể giảm dung lượng tổng. Tuy nhiên, thay đổi primary key có ảnh hưởng đến quan hệ, ứng dụng, replication và truy vấn. Cần đánh giá toàn bộ hệ thống trước khi thay đổi.

### 3.4. Số tầng B-tree và chi phí tìm kiếm

B-tree tăng chiều cao khi số entry và kích thước khóa tăng đến mức một trang nội bộ không thể tham chiếu đủ trang con ở tầng dưới. Nhiều tầng hơn có thể làm tăng số lần truy cập trang khi tìm kiếm, đặc biệt khi trang gốc hoặc tầng trên không nằm trong cache.

Tuy nhiên, không nên suy ra rằng index lớn hơn một chút sẽ lập tức thêm một tầng. Chiều cao phụ thuộc page size, fan-out, độ rộng khóa và số entry. DBMS thường giữ các trang trên cùng trong cache khá hiệu quả.

Cần đo số tầng hoặc thống kê cấu trúc khi hệ quản trị cung cấp, nhưng ưu tiên số liệu thực tế: logical reads, buffer hits, physical reads, thời gian truy vấn và số trang của index.

### 3.5. Dung lượng backup, replication và vận hành

Index là dữ liệu bền vững và thường được sao lưu hoặc tái tạo trong quá trình phục hồi. Index lớn làm tăng:

- Dung lượng backup và thời gian truyền backup.
- Thời gian restore hoặc rebuild index sau phục hồi.
- Dung lượng lưu trữ ở replica.
- Lượng log phát sinh khi index được duy trì.
- Thời gian tạo index mới hoặc thay đổi schema.
- Chi phí bảo trì, kiểm tra tính toàn vẹn và giám sát.

Trong môi trường có nhiều replica hoặc nhiều vùng, một index dư thừa có thể tạo chi phí nhân lên trên toàn bộ hạ tầng.

## 4. Bộ đệm cache và working set của index

### 4.1. Index cạnh tranh cache với dữ liệu bảng

DBMS giữ các trang dữ liệu và index trong buffer pool hoặc shared buffer. Khi thêm nhiều index hoặc mở rộng index, số trang có thể được cache tăng lên. Nếu tổng working set vượt bộ nhớ dành cho cache, các trang ít được dùng có thể bị đẩy ra và phải đọc lại khi truy cập.

Một index nhỏ, được dùng thường xuyên có thể nằm phần lớn trong cache và giúp truy vấn nhanh. Một index rất lớn, ít được dùng có thể chiếm chỗ của trang dữ liệu hoặc index quan trọng khác. Điều này tạo chi phí gián tiếp ngay cả với truy vấn không dùng index mới.

Cache không chỉ chứa index. Nó còn chứa trang heap/table, metadata, dữ liệu được đọc bởi các truy vấn khác và đôi khi các vùng phục vụ sort/hash. Vì thế, quyết định thêm index phải xem tác động lên working set toàn hệ thống.

### 4.2. Hit rate cần được đọc đúng ngữ cảnh

Tỷ lệ buffer hit cao thường là dấu hiệu tốt cho việc giảm đọc từ tầng lưu trữ, nhưng không thể đánh giá index chỉ bằng hit rate:

- Index có thể được hit thường xuyên nhưng chứa quá nhiều entry cần quét.
- Index có thể hit tốt trong khi truy cập heap tạo nhiều lần đọc rời rạc.
- Một index mới có thể tăng hit rate của truy vấn mục tiêu nhưng đẩy dữ liệu khác ra khỏi cache.
- Hit rate tổng thể có thể che giấu một workload cụ thể bị cache miss.
- Một index lớn nhưng cache hit cao vẫn tiêu tốn RAM và có thể làm giảm dung lượng dành cho phần khác.

Cần đo theo index hoặc theo truy vấn khi DBMS hỗ trợ, rồi đối chiếu với latency, số block đọc, CPU và I/O thiết bị.

### 4.3. Kích thước working set và tần suất truy cập

Working set là tập trang mà workload thường xuyên cần trong một khoảng thời gian. Nếu các index quan trọng và phần dữ liệu bảng thường dùng nằm vừa trong cache, nhiều truy vấn có thể được phục vụ với ít physical I/O.

Nếu index lớn hơn cache, các trang cần thiết có thể bị thay thế liên tục. Truy vấn có thể phải đọc lại root/branch/leaf hoặc trang heap. Tầng trên của B-tree thường được truy cập thường xuyên hơn tầng lá, nên có thể có hành vi cache khác nhau.

Hãy quan sát kích thước index, tần suất scan, buffer hit/read và độ trễ. Không nên lấy tổng dung lượng index so sánh trực tiếp với RAM rồi kết luận; mức độ nóng của từng trang và working set mới quyết định phần nào cần nằm trong cache.

### 4.4. Cache pressure do index dư thừa

Một index ít được sử dụng nhưng rất lớn có thể gây áp lực cache và tăng chi phí ghi. Nếu index tồn tại chỉ vì một truy vấn hiếm, cần so sánh:

- Lợi ích của truy vấn hiếm đó.
- Chi phí ghi phát sinh trên mọi INSERT/UPDATE/DELETE liên quan.
- Dung lượng và số trang cache có thể bị chiếm.
- Khả năng thay thế bằng index khác, truy vấn khác hoặc tác vụ nền.
- Ràng buộc uniqueness hoặc yêu cầu nghiệp vụ mà index đang bảo vệ.

Không xóa một unique index hoặc index phục vụ constraint chỉ vì số lần scan thấp. Một số index có giá trị chủ yếu ở việc bảo vệ tính đúng đắn, không phải phục vụ truy vấn đọc.

## 5. Write amplification và log

### 5.1. Vì sao một lần ghi logic tạo nhiều ghi vật lý?

Ứng dụng có thể gửi một INSERT hoặc UPDATE, nhưng DBMS phải thay đổi nhiều cấu trúc và ghi log để bảo đảm khả năng phục hồi. Một thao tác logic có thể dẫn đến:

- Ghi trang bảng.
- Ghi một hoặc nhiều trang index.
- Ghi WAL, redo log hoặc transaction log.
- Ghi metadata hoặc trang quản lý không gian.
- Ghi các trang tạm hoặc trang bị tách.
- Công việc ghi nền hoặc checkpoint ở thời điểm sau.

Write amplification mô tả quan hệ giữa lượng dữ liệu thực sự ghi xuống tầng lưu trữ và lượng dữ liệu logic mà ứng dụng yêu cầu ghi. Cách tính cụ thể phụ thuộc tầng đo và công nghệ lưu trữ. Nếu một lần ghi ứng dụng tạo nhiều lần sửa trang index và log, write amplification có thể tăng.

Không có một hệ số cố định áp dụng cho mọi DBMS. Cần đo byte ghi hoặc I/O ở các tầng khác nhau và xác định phạm vi của từng chỉ số.

### 5.2. Index làm tăng log như thế nào?

Khi index entry được chèn, xóa hoặc cập nhật, các thay đổi cần được ghi log theo cơ chế phục hồi của engine. Một bảng có nhiều index thường tạo thêm log khi ghi dữ liệu, đặc biệt nếu nhiều cột index thay đổi.

Hệ quả có thể là:

- Tăng dung lượng WAL/redo/transaction log.
- Tăng băng thông ghi và áp lực lên thiết bị log.
- Tăng replication lag nếu replica phải nhận và áp dụng nhiều thay đổi.
- Tăng thời gian checkpoint hoặc phục hồi.
- Tăng chi phí backup log và lưu trữ log.

Nếu một workload bị giới hạn bởi tốc độ ghi log hoặc commit flush, thêm index có thể làm transaction chậm hơn dù index không được truy vấn SELECT sử dụng nhiều.

### 5.3. Page split và ghi log

Khi một B-tree page đầy, việc chèn có thể gây page split. Engine cần phân phối entry sang trang mới và cập nhật các trang liên quan. Điều này làm tăng lượng trang bị sửa và log phải ghi.

Page split không phải lúc nào cũng là vấn đề nghiêm trọng. Một số split là bình thường khi index tăng trưởng. Cần quan sát tỷ lệ split, latency ghi, mức lấp đầy, kiểu khóa và phân bố chèn. Chỉ khi split tăng cùng với chi phí ghi hoặc fragmentation mới nên xem xét thay đổi fill factor, khóa hoặc cách nạp dữ liệu.

### 5.4. Chi phí của UPDATE trên nhiều index

Nếu một UPDATE thay đổi ba cột được index bởi ba cấu trúc khác nhau, DBMS có thể phải sửa entry tương ứng trong cả ba index. Nếu một cột xuất hiện trong nhiều index, chi phí duy trì có thể lặp lại.

Ví dụ:

~~~sql
UPDATE orders
SET status = 'SHIPPED',
    updated_at = CURRENT_TIMESTAMP
WHERE order_id = 10001;
~~~

Nếu status và updated_at đều nằm trong nhiều index, một UPDATE đơn hàng có thể tác động đến nhiều cấu trúc. Nếu status chỉ được dùng trong một báo cáo ít quan trọng, cần đánh giá xem index riêng trên status có xứng đáng với chi phí cập nhật mọi đơn hàng hay không.

Không phải lúc nào cũng nên bỏ index theo cột trạng thái. Một index có thể rất hữu ích nếu truy vấn lọc các đơn đang chờ xử lý và chỉ chọn một phần nhỏ bảng. Cần xem độ chọn lọc và tần suất truy vấn.

## 6. Những thuộc tính làm tăng chi phí index

### 6.1. Số lượng index

Mỗi index duy trì một cấu trúc riêng. Số lượng index tăng làm tăng số thao tác ghi, dung lượng và lượng trang có thể cạnh tranh cache.

Tuy nhiên, số lượng đơn thuần không đủ để kết luận. Một bảng có 10 index nhỏ và ổn định có thể vận hành tốt hơn bảng có 3 index rất rộng, nhiều cập nhật và thường xuyên split. Hãy xem kích thước và tần suất thay đổi của từng index.

### 6.2. Độ rộng khóa và payload

Khóa càng rộng thì mỗi entry thường càng lớn. Index trên chuỗi dài, nhiều cột hoặc dữ liệu có payload lớn làm giảm số entry trên một trang, tăng số trang và có thể tăng chiều cao B-tree.

Cần cân nhắc:

- Có thể dùng khóa ngắn hơn mà vẫn bảo toàn uniqueness không?
- Có cần đưa mọi cột trả về vào covering index không?
- Cột có độ rộng biến đổi lớn hay không?
- Có thể dùng INCLUDE hoặc cơ chế payload riêng của DBMS không?
- Index có đang trùng lặp tiền tố với index khác không?

Không thay đổi kiểu dữ liệu hoặc rút ngắn khóa nếu điều đó làm mất tính duy nhất hay gây lỗi nghiệp vụ. Độ rộng phải được cân bằng với ngữ nghĩa dữ liệu.

### 6.3. Cập nhật thường xuyên trên cột index

Một index trên cột thay đổi liên tục có thể phát sinh nhiều maintenance. Ví dụ, **last_seen_at** được cập nhật cho mỗi lần người dùng hoạt động. Nếu cột này được lập index trên bảng có hàng triệu người dùng, mỗi cập nhật có thể tạo công việc index đáng kể.

Hãy hỏi:

- Truy vấn nào thực sự cần index này?
- Truy vấn có thể dùng cách lọc khác hoặc dữ liệu tổng hợp không?
- Có thể giảm tần suất cập nhật hoặc ghi theo batch không?
- Index có cần độ chính xác tức thời hay có thể dùng bảng/tầng phụ?
- Tác động đến HOT update hoặc cơ chế tương tự là gì?

Một index có thể làm truy vấn hiếm nhanh hơn nhưng làm tất cả cập nhật thường xuyên chậm hơn.

### 6.4. Index có độ chọn lọc thấp

Index trên cột chỉ có vài giá trị như **is_active**, **status** hoặc **gender** có thể không hiệu quả nếu mỗi truy vấn chọn một tỷ lệ lớn bảng. DBMS có thể quyết định scan bảng thay vì index.

Tuy nhiên, index độ chọn lọc thấp vẫn có thể hữu ích khi:

- Truy vấn thường lọc một giá trị rất hiếm.
- Có partial/filtered index chỉ giữ những hàng cần quan tâm.
- Index bao phủ truy vấn và nhỏ hơn nhiều so với bảng.
- Index kết hợp với các cột có độ chọn lọc cao hơn.
- Workload cần sắp xếp hoặc phân trang theo thứ tự index.

Đừng đánh giá index chỉ bằng cardinality của một cột; xem phân bố dữ liệu và điều kiện truy vấn thực tế.

### 6.5. Trùng lặp và index tiền tố

Hai index có thể trùng lặp hoàn toàn hoặc một index có thể là tiền tố của index khác. Ví dụ:

~~~sql
CREATE INDEX idx_orders_customer
ON orders (customer_id);

CREATE INDEX idx_orders_customer_created
ON orders (customer_id, created_at);
~~~

Index thứ hai có thể hỗ trợ một số truy vấn chỉ lọc customer_id vì customer_id là tiền tố. Nhưng hai index không nhất thiết thay thế hoàn toàn cho nhau: index đơn có thể nhỏ hơn, có thể được dùng hiệu quả hơn trong một số tình huống, hoặc có khác biệt về uniqueness, INCLUDE, partial predicate và collation.

Trước khi xóa index tiền tố, kiểm tra:

- Index có UNIQUE hay không.
- Các truy vấn nào đang dùng index đơn.
- Index ghép có cùng thứ tự cột, điều kiện, collation và operator class không.
- Index đơn có nhỏ hơn đủ để tạo lợi ích cache không.
- Index có phục vụ constraint hoặc cơ chế đặc biệt không.

Chỉ xóa sau khi có bằng chứng và quy trình rollback.

## 7. Đo chi phí và lợi ích của từng index

### 7.1. Xây dựng đường cơ sở

Trước khi thêm hoặc xóa index, ghi nhận workload đại diện:

- Throughput INSERT, UPDATE, DELETE và SELECT.
- p50, p95, p99 của transaction quan trọng.
- Số lỗi, timeout, deadlock và retry.
- CPU, RAM, I/O latency, IOPS và byte đọc/ghi.
- Dung lượng bảng và từng index.
- Buffer hit/read hoặc logical reads.
- WAL/redo/transaction log generation.
- Replication lag và thời gian backup nếu có liên quan.

Cần ghi khoảng thời gian và mức tải. Thống kê tích lũy từ lúc khởi động DBMS có thể không đại diện cho một cửa sổ đo cụ thể. Nếu thống kê được reset, phải ghi lại thời điểm reset và quyền vận hành phù hợp.

### 7.2. Ví dụ đo index trong PostgreSQL

PostgreSQL cung cấp các view thống kê để quan sát việc sử dụng index. Ví dụ:

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    indexrelname AS index_name,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
ORDER BY pg_relation_size(indexrelid) DESC;
~~~

Các cột có ý nghĩa khái quát:

- **idx_scan:** số lần index được bắt đầu scan theo thống kê.
- **idx_tup_read:** số index entry được đọc.
- **idx_tup_fetch:** số hàng heap được lấy thông qua index scan theo định nghĩa thống kê của PostgreSQL.
- **pg_relation_size:** kích thước vật lý của index.

Không diễn giải idx_scan bằng 0 là index vô dụng nếu khoảng thống kê chưa bao phủ chu kỳ workload đầy đủ, thống kê vừa reset hoặc index được dùng cho constraint/uniqueness. Cũng cần lưu ý một số loại scan và cơ chế truy vấn có thể không phản ánh theo cách người đọc mong đợi trong một bộ đếm đơn giản.

Để xem buffer hit/read theo index:

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    indexrelname AS index_name,
    idx_blks_read,
    idx_blks_hit
FROM pg_statio_user_indexes
ORDER BY idx_blks_read DESC;
~~~

idx_blks_read là số block được đọc vào shared buffer theo thống kê; nó không nhất thiết tương đương số lần thiết bị vật lý đọc. idx_blks_hit là số block được tìm thấy trong shared buffers. Cần đối chiếu I/O timing và số liệu hệ điều hành.

### 7.3. Đo dung lượng bảng và index

Có thể xem kích thước bảng và các index trong PostgreSQL:

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    pg_size_pretty(pg_relation_size(relid)) AS table_size,
    pg_size_pretty(pg_indexes_size(relid)) AS indexes_size,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC;
~~~

pg_relation_size cho kích thước quan hệ bảng ở dạng chính; pg_indexes_size tổng hợp kích thước index; pg_total_relation_size bao gồm bảng, index và các thành phần liên quan như TOAST theo định nghĩa hàm. Đây là dung lượng trên đĩa, không phải số byte đang nằm trong cache.

Có thể xem kích thước từng index bằng pg_relation_size(indexrelid) như truy vấn ở phần trước. So sánh kích thước với idx_scan và workload giúp xác định index nào đang chiếm nhiều dung lượng so với tần suất sử dụng.

### 7.4. Kết hợp với thống kê truy vấn

Nếu pg_stat_statements được cài đặt và bật, có thể xem truy vấn tiêu thụ nhiều thời gian hoặc block:

~~~sql
SELECT
    calls,
    round(total_exec_time::numeric, 2) AS total_exec_ms,
    shared_blks_hit,
    shared_blks_read,
    temp_blks_written,
    left(query, 180) AS query_sample
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 30;
~~~

Dùng dữ liệu này để tìm truy vấn có lợi ích tiềm năng khi thêm index. Sau đó kiểm tra kế hoạch thực thi với tham số đại diện và đo lại. Một index có idx_scan thấp có thể vẫn cần thiết cho truy vấn rất quan trọng hoặc để bảo vệ unique constraint; một index có scan cao có thể vẫn đắt nếu mỗi lần ghi phải duy trì nhiều entry.

### 7.5. Giới hạn của thống kê sử dụng index

Các bộ đếm sử dụng index thường là thống kê tích lũy, có thể bị reset, không nhất thiết phân biệt mọi lý do truy cập và không tự đo được toàn bộ chi phí ghi do index tạo ra.

Cần kết hợp:

- Thống kê sử dụng index.
- Kích thước index.
- Số lượng và loại câu lệnh ghi.
- Tần suất cập nhật cột index.
- Execution plan và số logical/physical reads.
- Thời gian truy vấn và transaction.
- Log generation, I/O và replication.
- Yêu cầu constraint và nghiệp vụ.

Đừng xóa index tự động chỉ dựa trên một cột thống kê.

## 8. Theo dõi chi phí trong các hệ quản trị khác

### 8.1. MySQL InnoDB

InnoDB lưu bảng theo clustered index và secondary index. Secondary index mang primary key, vì vậy kích thước primary key có ảnh hưởng đến toàn bộ index phụ.

Các nguồn quan sát có thể gồm:

- SHOW TABLE STATUS hoặc metadata trong INFORMATION_SCHEMA để xem kích thước bảng và index theo cách engine báo cáo.
- Performance Schema và các view trong schema sys để xem thống kê truy cập index, tùy phiên bản và cấu hình instrumentation.
- InnoDB buffer pool metrics để xem page reads, page gets và tình trạng cache.
- Thống kê redo log, dirty pages, checkpoint và purge để đánh giá chi phí ghi.
- EXPLAIN ANALYZE để xem access path, actual rows và thời gian thực thi.

Tên view, cột và mức độ chi tiết phụ thuộc phiên bản MySQL. Hãy tra tài liệu của phiên bản đang chạy và không so sánh trực tiếp bộ đếm của MySQL với idx_scan hoặc idx_blks_read của PostgreSQL như thể chúng có cùng định nghĩa.

### 8.2. SQL Server

SQL Server có thể dùng các nguồn sau:

- sys.dm_db_index_usage_stats để xem số lần seek, scan, lookup và update được ghi nhận.
- sys.dm_db_index_operational_stats để xem hoạt động ở mức vận hành như leaf insert, update, delete và page latch.
- sys.indexes, sys.index_columns và sys.partitions để xem cấu trúc và metadata index.
- Actual execution plan và SET STATISTICS IO, TIME ON để xem logical reads, physical reads và thời gian.
- Log usage, wait statistics và replication metrics để đánh giá tác động ghi.

Các DMV có phạm vi và vòng đời bộ đếm riêng. Một số thống kê có thể mất khi instance khởi động lại, database offline hoặc metadata thay đổi. Cần ghi thời điểm và phạm vi đo.

### 8.3. Oracle

Oracle cung cấp thống kê trong data dictionary và dynamic performance views, tùy quyền truy cập:

- DBA_INDEXES, ALL_INDEXES hoặc USER_INDEXES để xem metadata và dung lượng liên quan.
- DBA_IND_STATISTICS hoặc view tương ứng để xem thống kê index.
- V$SEGMENT_STATISTICS để quan sát một số hoạt động theo segment.
- AWR/ASH hoặc các công cụ chẩn đoán phù hợp để liên hệ I/O, buffer gets, physical reads và thời gian SQL.

Một số tính năng như AWR phụ thuộc edition, license và chính sách của tổ chức. Chỉ dùng các nguồn mà môi trường được cấp quyền và cho phép. Cần đọc tài liệu đúng phiên bản để hiểu bộ đếm.

### 8.4. So sánh đúng phạm vi

Mỗi DBMS có định nghĩa riêng về scan, logical read, physical read, update count và cache hit. Trước khi so sánh, phải xác định:

- Bộ đếm là theo statement, index, table, database hay instance.
- Bộ đếm tích lũy từ lúc nào và có reset không.
- Có tính thao tác nền hoặc truy cập nội bộ không.
- Một lượt scan có thể đọc bao nhiêu entry.
- Physical read có được phục vụ từ cache tầng dưới hay không.
- Số liệu có được lấy cùng cửa sổ tải hay không.

Mục tiêu là tìm quan hệ giữa chi phí index và workload trong cùng hệ quản trị, không phải tạo một bảng xếp hạng bộ đếm giữa các engine.

## 9. Rà soát index dư thừa và ít được sử dụng

### 9.1. Index không được dùng trong khoảng đo

Một index có số scan thấp có thể là ứng viên rà soát, nhưng trước khi kết luận, hãy kiểm tra:

- Khoảng thời gian thống kê có bao phủ chu kỳ nghiệp vụ không?
- Có tác vụ cuối tháng, báo cáo định kỳ hoặc truy vấn khẩn cấp chỉ chạy ít lần không?
- Index có phục vụ unique constraint, primary key hoặc kiểm tra quan hệ không?
- Có truy vấn dùng index thông qua execution path đặc biệt không?
- Thống kê có bị reset sau restart hoặc thao tác bảo trì không?
- Index có được dùng ở replica hoặc môi trường khác không?

Index chỉ dùng vài lần trong tháng có thể vẫn có giá trị nếu truy vấn đó quan trọng và không có phương án thay thế.

### 9.2. Index trùng lặp hoặc bao hàm

Hai index có cùng các cột khóa và thứ tự có thể là trùng lặp nếu không có khác biệt về unique, predicate, collation, operator class hoặc INCLUDE. Một index có thể là tiền tố của index khác, nhưng không phải lúc nào cũng thay thế hoàn toàn.

Ví dụ:

~~~sql
CREATE INDEX idx_customer
ON orders (customer_id);

CREATE INDEX idx_customer_created
ON orders (customer_id, created_at);
~~~

Index thứ hai có thể hỗ trợ một số truy vấn lọc theo customer_id, nhưng index đầu tiên nhỏ hơn và có thể có ích khi chỉ cần quét customer_id. Cần xem kế hoạch và chi phí thực tế của cả hai trước khi gộp hoặc xóa.

### 9.3. Partial hoặc filtered index

Nếu truy vấn chỉ quan tâm một tập con nhỏ của bảng, partial index trong PostgreSQL hoặc filtered index trong SQL Server có thể giảm dung lượng và chi phí duy trì so với index bao phủ toàn bảng.

Ví dụ PostgreSQL:

~~~sql
CREATE INDEX idx_orders_pending_created
ON orders (created_at)
WHERE status = 'PENDING';
~~~

Nếu chỉ 2% đơn hàng đang ở trạng thái PENDING và workload thường xuyên lấy các đơn này, index có thể nhỏ hơn đáng kể so với index trên toàn bộ status hoặc created_at. Khi trạng thái thay đổi, hàng có thể được thêm vào hoặc loại khỏi partial index, vì vậy vẫn có chi phí ghi đối với những thay đổi làm điều kiện predicate đúng/sai.

Optimizer chỉ dùng partial index khi có thể chứng minh điều kiện truy vấn phù hợp với predicate. Cần kiểm tra kế hoạch với câu SQL thực tế và tham số thực tế.

### 9.4. Đừng xóa index theo cảm tính

Trước khi xóa, hãy lập kế hoạch an toàn:

1. Xác định index có ràng buộc hoặc vai trò bảo vệ dữ liệu không.
2. Thu thập thống kê trong một khoảng đại diện.
3. Xem các truy vấn và execution plan phụ thuộc vào index.
4. Kiểm tra index có trùng lặp hoặc có thể thay thế bằng index khác không.
5. Đánh giá chi phí rebuild nếu cần khôi phục.
6. Dùng cơ chế vô hiệu hóa hoặc đánh dấu không sử dụng nếu DBMS hỗ trợ và phù hợp.
7. Theo dõi workload sau thay đổi trong thời gian đủ dài.
8. Xóa chính thức chỉ khi không có suy giảm và có phương án khôi phục.

Không vô hiệu hóa unique index hoặc constraint index nếu điều đó làm mất bảo đảm dữ liệu.

## 10. Ví dụ đánh giá một index theo workload

### 10.1. Bối cảnh

Một hệ thống thương mại có bảng **orders** nhận nhiều INSERT và UPDATE. Đội kỹ thuật tạo index riêng trên **status** để hỗ trợ dashboard:

~~~sql
CREATE INDEX idx_orders_status
ON orders (status);
~~~

Dashboard chạy nhiều lần mỗi phút:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE status = 'PENDING'
ORDER BY created_at
LIMIT 100;
~~~

Trong khi đó, ứng dụng cập nhật status nhiều lần khi đơn được xử lý. Index giúp dashboard tìm đơn PENDING nhưng mỗi lần trạng thái thay đổi có thể phải duy trì index.

### 10.2. Câu hỏi cần đo

- Bao nhiêu phần trăm bảng đang ở trạng thái PENDING?
- Dashboard có thực sự chọn một tập nhỏ dữ liệu không?
- Index scan có phải đọc nhiều heap page không?
- Có thể dùng index ghép (status, created_at) để tránh sort hoặc giảm lookup không?
- Status thay đổi bao nhiêu lần mỗi giây?
- Index hiện tại lớn bao nhiêu?
- INSERT/UPDATE p95 và WAL generation thay đổi thế nào?
- Có thể dùng partial index chỉ cho PENDING không?

### 10.3. Một giả thuyết tối ưu

Nếu chỉ một tỷ lệ nhỏ đơn hàng ở trạng thái PENDING và dashboard chủ yếu đọc các đơn đó, partial index có thể giảm dung lượng:

~~~sql
CREATE INDEX idx_orders_pending_created
ON orders (created_at)
WHERE status = 'PENDING';
~~~

Index này chỉ chứa những hàng thỏa điều kiện. Khi đơn chuyển khỏi PENDING, entry tương ứng được loại khỏi index; khi đơn chuyển vào PENDING, entry được thêm. Vì vậy, index có thể nhỏ hơn nhưng vẫn chịu chi phí ghi cho các lần chuyển trạng thái.

Cần thử trong môi trường đại diện và so sánh với index status hiện tại. Nếu dashboard cần nhiều cột khác, có thể xem xét covering index hoặc cơ chế INCLUDE tùy DBMS, nhưng phải tính thêm dung lượng và chi phí duy trì.

### 10.4. Bảng kết quả minh họa

| Chỉ số | Index status | Partial index | Nhận xét |
|---|---:|---:|---|
| Kích thước index | 1,8 GB | 140 MB | Partial index nhỏ hơn do chỉ giữ hàng PENDING |
| Dashboard p95 | 120 ms | 55 ms | Truy vấn mục tiêu cải thiện |
| UPDATE status p95 | 9 ms | 10 ms | Chi phí cập nhật gần tương đương trong lần thử |
| WAL/giây | 42 MB | 38 MB | Giảm trong workload giả định |
| Buffer reads | 4.200 | 900 | Ít trang được đọc hơn |

Các số liệu chỉ minh họa, không phải dự đoán cho hệ thống thực tế. Kết quả thực phụ thuộc tỷ lệ trạng thái, số cột truy vấn, tốc độ thay đổi trạng thái, cấu hình và cách DBMS thực hiện index.

Nếu partial index cải thiện dashboard nhưng làm UPDATE status chậm đáng kể trong tải đỉnh, cần cân nhắc tỷ lệ đọc/ghi và mục tiêu dịch vụ. Không quyết định chỉ từ kích thước index.

## 11. Quy trình thiết kế index có tính đến chi phí

Một quy trình thực tế có thể thực hiện theo các bước:

1. **Xác định truy vấn mục tiêu:** lấy từ log, APM hoặc thống kê truy vấn; ghi tần suất, tham số và mục tiêu latency.
2. **Mô tả workload ghi:** số INSERT/UPDATE/DELETE mỗi giây, cột thường thay đổi và transaction size.
3. **Đọc execution plan:** xem access path, actual rows, loops, lookup, sort, buffer và I/O.
4. **Đề xuất index tối thiểu:** chọn cột khóa, thứ tự, INCLUDE hoặc predicate dựa trên điều kiện lọc và thứ tự truy cập.
5. **Ước lượng chi phí:** xem số entry, độ rộng, kích thước, số index hiện có và mức cập nhật cột.
6. **Thử nghiệm trước/sau:** giữ dữ liệu, tham số, cache policy, concurrency và thời lượng đo tương đương.
7. **Đo cả đọc lẫn ghi:** latency, throughput, lỗi, log generation, I/O và cache.
8. **Kiểm tra tác dụng phụ:** bloat, page split, replication lag, backup, build/rebuild và dung lượng.
9. **Quyết định:** giữ, điều chỉnh hoặc loại bỏ index theo lợi ích tổng thể và yêu cầu đúng đắn.
10. **Theo dõi sau triển khai:** xác nhận xu hướng trong workload thật và giữ phương án rollback.

### 11.1. Bảng đánh giá từng index

| Thuộc tính | Câu hỏi |
|---|---|
| Mục tiêu truy vấn | Index phục vụ truy vấn hoặc constraint nào? |
| Tần suất đọc | Truy vấn chạy bao nhiêu lần trong cửa sổ đo? |
| Lợi ích đọc | Có giảm rows scanned, logical reads, lookup hoặc latency không? |
| Tần suất ghi | Các cột index được INSERT/UPDATE/DELETE bao nhiêu lần? |
| Độ rộng | Khóa và payload chiếm bao nhiêu byte/entry? |
| Dung lượng | Index chiếm bao nhiêu đĩa và trang cache? |
| Log | Index làm thay đổi WAL/redo/log generation ra sao? |
| Bảo trì | Có page split, bloat, vacuum/purge hoặc rebuild đáng kể không? |
| Trùng lặp | Có index khác bao phủ cùng truy vấn hoặc tiền tố không? |
| Ràng buộc | Index có bảo vệ uniqueness hoặc yêu cầu nghiệp vụ không? |
| Quyết định | Giữ, điều chỉnh, thay thế hay xóa? Bằng chứng là gì? |

### 11.2. Chọn chỉ số bảo vệ

Ngoài latency truy vấn mục tiêu, hãy xác định các chỉ số bảo vệ (guardrails) trước khi thử:

- p95/p99 của transaction ghi không vượt mục tiêu.
- Throughput ghi không giảm vượt giới hạn.
- WAL/redo log và replication lag không tăng quá mức cho phép.
- RAM và buffer cache vẫn đủ cho workload quan trọng.
- Không tăng lỗi, deadlock hoặc timeout.
- Dung lượng và thời gian backup vẫn trong ngân sách.
- Kết quả nghiệp vụ và constraint không thay đổi.

Chỉ số bảo vệ giúp tránh một tối ưu cục bộ làm hệ thống tổng thể xấu đi.

## 12. Những sai lầm thường gặp

**Tạo index cho mọi cột được dùng trong WHERE.**  
Một index có chi phí ghi và cache. Cần xét tần suất truy vấn, độ chọn lọc, kế hoạch và các index đã có.

**Chỉ đo SELECT sau khi thêm index.**  
INSERT, UPDATE, DELETE, log generation, replication và cache có thể chịu chi phí lớn hơn.

**Cho rằng index ít được scan là vô dụng.**  
Index có thể bảo vệ uniqueness, constraint hoặc phục vụ tác vụ hiếm nhưng quan trọng. Phải xem đủ chu kỳ workload.

**Bỏ qua độ rộng của khóa chính.**  
Trong các engine lưu clustered key trong secondary index, khóa rộng làm tăng dung lượng của mọi index phụ.

**Thêm mọi cột SELECT vào index.**  
Covering index có thể giảm lookup nhưng tăng kích thước, ghi và cache footprint.

**Tăng số index để chữa mọi truy vấn chậm.**  
Nhiều index có thể tăng write amplification, log và cache pressure. Trước tiên cần đọc execution plan và xác định access path.

**Xóa index ngay khi bộ đếm scan bằng không.**  
Bộ đếm có thể bị reset hoặc chưa bao phủ chu kỳ nghiệp vụ. Kiểm tra constraint và workload định kỳ.

**Tăng fill factor hoặc rebuild theo lịch cố định mà không đo.**  
Khoảng trống trang làm index lớn hơn; rebuild tiêu thụ I/O và tài nguyên. Chỉ điều chỉnh khi có bằng chứng page split hoặc fragmentation ảnh hưởng hiệu năng.

**So sánh bộ đếm khác định nghĩa giữa các DBMS.**  
Logical read, physical read, index scan và update count không đồng nhất giữa engine. Đọc tài liệu đúng phiên bản và phạm vi đo.

## 13. Kết luận

Mỗi index mang lại một access path nhưng đồng thời tạo chi phí duy trì, dung lượng và áp lực bộ đệm. INSERT có thể phải thêm entry vào nhiều index; UPDATE trên cột index có thể tạo thêm công việc sửa cấu trúc; DELETE có thể để lại phiên bản cũ cần vacuum hoặc purge. Index rộng và nhiều index phụ làm tăng số trang, write amplification, log generation và cạnh tranh cache.

Thiết kế index cần bắt đầu từ workload thực tế. Hãy đo truy vấn đọc, khối lượng ghi, độ rộng index, kích thước, buffer usage và chi phí log. Dùng thống kê của DBMS để nhận diện index ít dùng hoặc trùng lặp, nhưng luôn kiểm tra ràng buộc và chu kỳ nghiệp vụ trước khi xóa. Partial index, composite index hoặc covering index có thể giảm chi phí ở một số trường hợp, nhưng cần kiểm chứng cả đọc lẫn ghi.

Một index chỉ nên được giữ khi lợi ích của nó đối với truy vấn hoặc ràng buộc xứng đáng với chi phí duy trì và vận hành. Quyết định cuối cùng phải được xác nhận bằng phép đo lặp lại dưới workload đại diện, đồng thời bảo đảm dữ liệu vẫn đúng và hệ thống còn đủ tài nguyên cho các hoạt động khác.

## Câu hỏi tự kiểm tra

1. Vì sao INSERT trên một bảng có nhiều index phải thực hiện nhiều công việc hơn INSERT trên bảng ít index?
2. UPDATE một cột không được index có thể khác UPDATE một cột nằm trong nhiều index như thế nào?
3. HOT update của PostgreSQL giúp giảm chi phí nào và điều kiện chính là gì?
4. Vì sao DELETE trong hệ quản trị dùng MVCC có thể chưa giải phóng ngay toàn bộ không gian index?
5. Độ rộng primary key ảnh hưởng đến secondary index của InnoDB và SQL Server ra sao?
6. Một index có kích thước lớn nhưng buffer hit cao có thể vẫn tạo áp lực cache theo cách nào?
7. Write amplification liên quan thế nào đến index maintenance và log?
8. Vì sao không nên xóa index chỉ dựa trên idx_scan bằng 0?
9. Partial index có thể giảm dung lượng như thế nào và vẫn tạo chi phí ghi trong tình huống nào?
10. Hãy lập kế hoạch đo trước/sau khi thêm covering index, bao gồm latency đọc, latency ghi, kích thước, cache và log generation.

Một thiết kế chỉ mục hiệu quả là thiết kế đáp ứng được truy vấn và ràng buộc quan trọng với tổng chi phí đọc, ghi, dung lượng, bộ đệm và bảo trì nằm trong giới hạn vận hành.

