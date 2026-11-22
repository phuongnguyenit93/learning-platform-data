# Khóa chính: độ rộng, tính tăng dần và ảnh hưởng đến chỉ mục

Khóa chính (primary key, PK) xác định duy nhất mỗi hàng và là một phần quan trọng của thiết kế mô hình dữ liệu. Khi chọn khóa chính, cần xem xét nhiều hơn việc giá trị có duy nhất hay không. Độ rộng của khóa, tính ổn định, thứ tự sinh giá trị và cách hệ quản trị tổ chức chỉ mục có thể ảnh hưởng trực tiếp đến dung lượng lưu trữ, số trang phải đọc, tốc độ ghi, cache và mức tranh chấp khi nhiều giao dịch chèn dữ liệu đồng thời.

Trong tối ưu hiệu năng cơ sở dữ liệu, một khóa chính nhỏ và ổn định thường giúp giảm chi phí lưu trữ và so sánh. Khóa tăng dần có thể tạo tính cục bộ tốt cho cây B-tree, nhưng tốc độ ghi đồng thời cao có thể tập trung vào trang lá cuối và tạo điểm nóng. Khóa ngẫu nhiên phân tán vị trí chèn nhưng có thể làm tăng page split, phân mảnh và truy cập ngẫu nhiên. Không có một kiểu khóa tối ưu cho mọi hệ quản trị; phải hiểu cách InnoDB, SQL Server, PostgreSQL và các hệ khác lưu hàng và liên kết chỉ mục.

Bài học này phân tích độ rộng khóa chính, khóa tuần tự và khóa ngẫu nhiên, ảnh hưởng đến clustered index và secondary index, cách chọn khóa đơn hoặc khóa ghép, cùng quy trình đo kiểm trước khi thay đổi mô hình dữ liệu.

## 1. Vai trò của khóa chính trong mô hình dữ liệu

Khóa chính là ràng buộc xác định một hàng duy nhất trong bảng. Một khóa chính phải duy nhất và không NULL. Tùy hệ quản trị, khai báo primary key còn tạo hoặc sử dụng một chỉ mục để thực thi tính duy nhất.

Ví dụ:

~~~sql
CREATE TABLE customers (
    customer_id BIGINT NOT NULL,
    email VARCHAR(320) NOT NULL,
    display_name VARCHAR(200),
    created_at TIMESTAMP NOT NULL,
    PRIMARY KEY (customer_id),
    UNIQUE (email)
);
~~~

Trong ví dụ, customer_id là định danh kỹ thuật của hàng; email là một khóa ứng viên được bảo đảm duy nhất bởi ràng buộc UNIQUE. Việc tách định danh nội bộ khỏi thuộc tính nghiệp vụ có thể hữu ích khi email được phép thay đổi, khi quy tắc định danh thay đổi hoặc khi một khách hàng có nhiều địa chỉ liên hệ.

Một khóa chính tốt thường có các đặc điểm:

- **Duy nhất:** không có hai hàng hợp lệ dùng cùng khóa.
- **Không NULL:** mọi hàng đều có giá trị khóa.
- **Ổn định:** giá trị không thay đổi trong suốt vòng đời hàng.
- **Nhỏ gọn:** giảm dung lượng khóa trong chỉ mục và dữ liệu tham chiếu.
- **Dễ truyền và so sánh:** kiểu dữ liệu phù hợp với ứng dụng và các khóa ngoại.
- **Có thể tạo an toàn:** không phụ thuộc vào cách ứng dụng phân tán sinh giá trị nếu hệ thống cần ghi từ nhiều node.

Tính tăng dần có thể là lợi thế về thứ tự vật lý hoặc locality trong một số hệ quản trị, nhưng không phải yêu cầu bắt buộc của khóa chính. Một khóa tăng dần vẫn có thể gây tranh chấp ở trang cuối khi nhiều luồng ghi đồng thời. Ngược lại, một khóa ngẫu nhiên vẫn có thể phù hợp nếu hệ thống cần tạo ID độc lập trên nhiều node hoặc cần tránh lộ thứ tự tạo bản ghi.

## 2. Độ rộng của khóa chính

Độ rộng khóa là số byte cần để biểu diễn giá trị khóa và các thông tin liên quan trong chỉ mục. Kiểu dữ liệu, encoding, collation, cấu trúc chỉ mục và overhead của hệ quản trị đều ảnh hưởng đến dung lượng thực tế.

Một số kích thước dữ liệu thường gặp:

| Kiểu định danh | Kích thước giá trị điển hình | Nhận xét |
|---|---:|---|
| INT 32-bit | 4 byte | Gọn, nhưng miền giá trị hữu hạn |
| BIGINT 64-bit | 8 byte | Gọn hơn UUID 128-bit, miền số lớn |
| UUID/GUID nhị phân | 16 byte | Dễ tạo phân tán, cần chú ý thứ tự và locality |
| UUID dạng chuỗi ký tự | Thường lớn hơn nhiều so với 16 byte | Có thêm chi phí ký tự, collation và độ dài biến thiên tùy kiểu cột |
| Khóa ghép | Tổng độ rộng các thành phần cộng overhead | Có thể rất rộng nếu gồm nhiều cột chuỗi |

Các con số trên chỉ mô tả kích thước biểu diễn cơ bản, không phải tổng dung lượng một entry trong chỉ mục. Entry còn có thể chứa row locator, thông tin trang, null bitmap, header, alignment hoặc metadata riêng của hệ quản trị.

### 2.1. Vì sao khóa rộng làm tăng chi phí?

Khóa rộng có thể ảnh hưởng theo nhiều cách:

1. **Giảm số entry trên mỗi trang chỉ mục.** Với cùng kích thước trang, khóa lớn chiếm nhiều chỗ hơn, làm giảm fan-out của cây B-tree.
2. **Tăng chiều cao hoặc số trang của cây.** Khi mỗi trang chứa ít entry hơn, chỉ mục có thể cần nhiều trang hơn để lưu cùng số khóa.
3. **Tăng I/O và cache footprint.** Nhiều trang hơn có thể làm tăng số lần đọc và giảm khả năng giữ các trang hữu ích trong buffer pool.
4. **Tăng chi phí so sánh.** So sánh chuỗi dài hoặc khóa ghép có thể tốn nhiều CPU hơn so với số nguyên ngắn.
5. **Tăng kích thước khóa ngoại và chỉ mục liên quan.** Các bảng con phải lưu khóa tham chiếu; chỉ mục trên khóa ngoại cũng mang độ rộng đó.
6. **Tăng chi phí cập nhật và truyền dữ liệu.** Khóa rộng xuất hiện trong join, sort, hash, log, replication hoặc payload của ứng dụng.

Ví dụ, một bảng orders có 100 triệu hàng và khóa chính UUID 16 byte thay vì BIGINT 8 byte. Phần giá trị khóa cơ bản đã tăng thêm khoảng 800 MB trước khi tính overhead và các cấu trúc phụ. Với hệ quản trị sao chép khóa chính vào nhiều secondary index, chênh lệch tổng dung lượng có thể lớn hơn đáng kể.

Không nên chỉ nhìn vào kích thước cột trong bảng. Hãy xác định hệ quản trị lưu row locator như thế nào và khóa chính có được mang vào các chỉ mục khác hay không.

## 3. Khóa chính ảnh hưởng đến secondary index ra sao?

Đây là điểm khác biệt quan trọng giữa các hệ quản trị.

### 3.1. InnoDB của MySQL: khóa chính là clustered index

Trong InnoDB, dữ liệu hàng được tổ chức theo clustered index. Nếu bảng có primary key, primary key là khóa của clustered index. Các leaf page của clustered index chứa dữ liệu hàng.

Secondary index của InnoDB lưu khóa secondary cùng với giá trị primary key để xác định hàng tương ứng. Khi truy vấn cần cột không có trong secondary index, InnoDB có thể dùng primary key trong secondary index để tra lại clustered index.

Hệ quả:

- Primary key rộng làm mỗi secondary index rộng thêm vì giá trị PK được lưu kèm.
- Bảng có nhiều secondary index sẽ khuếch đại chi phí của PK rộng.
- Thay đổi primary key có thể gây chi phí lớn vì khóa clustered và các secondary index liên quan cần được cập nhật.
- Khóa chính ổn định giúp tránh việc di chuyển hàng và cập nhật nhiều cấu trúc chỉ mục.

Ví dụ, bảng có sáu secondary index và primary key UUID 16 byte. So với BIGINT 8 byte, mỗi entry secondary index có thể cần thêm khoảng 8 byte cho phần khóa tham chiếu, chưa kể overhead. Với hàng trăm triệu entry, chênh lệch có thể đáng kể.

### 3.2. SQL Server: clustered key là row locator cho nonclustered index

SQL Server có thể tổ chức bảng thành heap hoặc clustered index. Nếu bảng có clustered index, khóa clustered được dùng làm row locator trong nonclustered index. Với clustered index không duy nhất, SQL Server có thể bổ sung uniqueifier để phân biệt các hàng có cùng khóa clustered.

Vì vậy, clustered key rộng có thể làm các nonclustered index lớn hơn. Chọn clustered key cần xem:

- Độ rộng và tính ổn định.
- Tính tăng dần và mẫu ghi đồng thời.
- Các truy vấn thường dùng thứ tự nào.
- Số lượng và kích thước nonclustered index.
- Khả năng phát sinh page split hoặc last-page contention.

Nếu bảng là heap, nonclustered index dùng RID để định vị hàng thay vì clustered key. Do đó, không nên áp dụng nhận định về việc PK được sao chép vào mọi chỉ mục cho mọi cấu trúc bảng SQL Server.

### 3.3. PostgreSQL: secondary index tham chiếu tuple ID

PostgreSQL lưu bảng theo heap. Một secondary index thông thường chứa khóa chỉ mục và tuple identifier (TID) để xác định vị trí hàng trong heap; nó không tự động sao chép toàn bộ primary key vào mọi secondary index như InnoDB.

Vì vậy, PK rộng trong PostgreSQL không làm mọi secondary index tăng trực tiếp theo cùng cơ chế của InnoDB. Tuy nhiên, PK vẫn có chi phí:

- Chỉ mục duy nhất được tạo để thực thi primary key sẽ lớn hơn.
- Các bảng con lưu khóa ngoại vẫn phải lưu giá trị khóa tham chiếu.
- Join, sort, hash và truyền khóa rộng vẫn tốn tài nguyên.
- Nếu ứng dụng chủ động đưa PK vào nhiều chỉ mục hoặc truy vấn, chi phí vẫn tăng.

PostgreSQL có lệnh CLUSTER để sắp xếp vật lý heap theo một chỉ mục tại thời điểm chạy, nhưng thứ tự này không được duy trì tự động sau các lần ghi. Không nên coi PostgreSQL có clustered index duy trì thứ tự hàng như InnoDB hoặc clustered table của SQL Server.

### 3.4. So sánh khái quát

| Hệ quản trị | Cách tổ chức chính | Ảnh hưởng của khóa chính rộng |
|---|---|---|
| MySQL InnoDB | Primary key là clustered index; secondary index mang PK | Có thể làm tất cả secondary index rộng hơn đáng kể |
| SQL Server với clustered index | Clustered key định vị hàng trong nonclustered index | Clustered key rộng có thể làm nonclustered index lớn hơn |
| SQL Server heap | Nonclustered index dùng RID để định vị hàng | Không có cơ chế nhân bản clustered key vì bảng không có clustered index |
| PostgreSQL | Heap + index; secondary index thông thường lưu TID | PK làm chỉ mục PK và khóa tham chiếu rộng hơn, nhưng không tự động được chép vào mọi secondary index |

Khi thiết kế khóa, hãy dùng đúng mô hình lưu trữ của DBMS đang vận hành. Một lời khuyên về InnoDB không thể áp dụng nguyên xi cho PostgreSQL.

## 4. Khóa tăng dần và tính cục bộ ghi

Khóa tăng dần thường được tạo bằng identity, auto-increment, sequence hoặc bộ sinh ID có thành phần thời gian. Giá trị mới thường lớn hơn giá trị đã sinh trước đó.

Với B-tree, nếu khóa tăng dần và dữ liệu được chèn theo thứ tự đó, nhiều lần chèn mới có xu hướng đi vào vùng cuối của cây. Điều này có thể tạo locality tốt:

- Trang lá mới thường gần các trang vừa được sử dụng.
- Giảm việc chèn ngẫu nhiên vào nhiều vùng của cây.
- Có thể giảm page split so với phân phối ngẫu nhiên trong một số workload.
- Scan theo thời gian hoặc ID có thể thuận lợi nếu thứ tự khóa phù hợp với truy vấn.

Tuy nhiên, tính tuần tự tạo ra một đánh đổi: nhiều giao dịch đồng thời có thể cùng chèn vào trang lá cuối hoặc một vùng rất hẹp. Đây có thể là **last-page contention** hoặc hot page.

### 4.1. Last-page contention

Khi nhiều worker chèn các khóa lớn hơn khóa hiện tại, chúng thường tập trung vào trang cuối của chỉ mục. Hệ quản trị phải đồng bộ hóa việc sửa trang và quản lý latch/lock nội bộ. Ở tải ghi rất cao, trang cuối có thể trở thành điểm tranh chấp dù các giao dịch không cập nhật cùng một hàng.

Dấu hiệu cần điều tra:

- Throughput insert không tăng tương ứng với số writer.
- Wait hoặc latch contention tập trung ở trang cuối của chỉ mục.
- CPU không nhất thiết bão hòa nhưng thời gian chờ đồng bộ tăng.
- Phân phối khóa ghi dồn vào một vùng hẹp.
- Khi tăng số luồng ghi, p95/p99 insert xấu đi.

Không phải mọi khóa tăng dần đều gây vấn đề. Với tải vừa phải hoặc trang cuối đủ khả năng phục vụ, sequential insert thường có lợi. Cần đo trên tốc độ ghi và mức đồng thời thực tế.

### 4.2. Phân biệt khóa tăng dần với thứ tự commit

Sequence hoặc auto-increment thường cấp giá trị trước khi transaction commit. Vì vậy, ID lớn hơn không nhất thiết có nghĩa giao dịch commit sau hoặc hàng được nhìn thấy sau. Hai transaction có thể lấy ID theo thứ tự, nhưng commit theo thứ tự ngược lại.

Không dùng khóa tăng dần như bằng chứng tuyệt đối về thứ tự commit hoặc thời điểm nghiệp vụ. Nếu cần thứ tự sự kiện chính xác, hãy thiết kế timestamp/sequence nghiệp vụ và quy tắc đồng bộ phù hợp.

## 5. Khóa ngẫu nhiên và UUID

UUID v4 được tạo ngẫu nhiên, không mang thứ tự thời gian. Khi dùng làm khóa B-tree, các giá trị mới có thể được chèn vào nhiều vị trí khác nhau trong cây thay vì tập trung ở trang cuối.

Ưu điểm:

- Có thể sinh độc lập trên nhiều ứng dụng hoặc node mà không cần một sequence trung tâm.
- Khó đoán hơn ID tăng dần đơn giản, giảm khả năng suy ra số lượng bản ghi hoặc thứ tự tạo.
- Dễ tạo ID trước khi ghi dữ liệu hoặc khi đồng bộ offline.

Nhược điểm:

- Giá trị 16 byte lớn hơn BIGINT 8 byte.
- Thứ tự ngẫu nhiên có thể làm page split và phân mảnh tăng trong một số cấu trúc B-tree.
- Ghi phân tán trên nhiều trang có thể làm cache locality kém.
- Trong InnoDB và SQL Server clustered index, khóa ngẫu nhiên có thể làm dữ liệu hàng được chèn vào nhiều vùng khác nhau.
- UUID được truyền trong join và khóa ngoại có thể làm payload lớn hơn.

UUID không mặc nhiên chậm. Kết quả phụ thuộc số lượng hàng, buffer pool, mức đồng thời, cách biểu diễn UUID, cấu trúc chỉ mục và tỷ lệ đọc/ghi. Một hệ thống phân tán cần sinh ID độc lập có thể chấp nhận chi phí này để đổi lấy tính tự chủ và khả năng tạo ID không va chạm thực tế.

### 5.1. UUID dạng nhị phân và dạng chuỗi

UUID có 128 bit, thường được hiển thị thành chuỗi có dấu gạch nối. Lưu dưới kiểu nhị phân 16 byte thường gọn hơn lưu dạng chuỗi 36 ký tự trong VARCHAR/CHAR, nhưng hỗ trợ kiểu dữ liệu và cách so sánh khác nhau theo DBMS.

Khi lưu UUID dạng chuỗi, cần xem:

- Character set và collation.
- Độ dài cột và overhead của kiểu chuỗi.
- So sánh chữ hoa/thường và biểu diễn canonical.
- Cách driver bind parameter.
- Khả năng dùng native UUID hoặc BINARY(16).

Nếu dùng dạng nhị phân, ứng dụng và DBMS phải thống nhất cách chuyển đổi byte order. Không trộn nhiều quy ước encoding giữa các dịch vụ.

## 6. Khóa có thứ tự theo thời gian: UUID v7 và các ID tương tự

UUID v7 đặt timestamp Unix millisecond ở phần bit cao, phần còn lại chứa các bit ngẫu nhiên hoặc trường theo đặc tả. Nhờ vậy, UUID v7 có thứ tự từ điển gần với thời gian tạo hơn UUID v4, giúp cải thiện locality khi chèn vào B-tree trong nhiều tình huống.

Lợi ích có thể có:

- Giá trị được tạo gần nhau về thời gian thường nằm gần nhau trong thứ tự khóa.
- Ít phân tán ngẫu nhiên toàn cây hơn UUID v4.
- Có thể sinh phân tán mà không cần sequence duy nhất tập trung.
- Giữ định dạng UUID 128-bit và khả năng tương thích với hệ thống dùng UUID.

Nhưng UUID v7 không nhất thiết tăng nghiêm ngặt từng giá trị trong mọi tiến trình. Nhiều ID có thể được sinh trong cùng millisecond; thứ tự phần random có thể không trùng với thứ tự phát sinh. Một số thư viện dùng bộ đếm hoặc cơ chế monotonic trong phạm vi tiến trình, nhưng không thể giả định mọi implementation đều giống nhau.

Các ID dạng Snowflake thường kết hợp timestamp, worker/node ID và sequence trong cùng khoảng thời gian. Chúng có thể có thứ tự gần thời gian và kích thước nhỏ hơn UUID, nhưng cần quản lý đồng hồ, ID worker, rollback thời gian và giới hạn sequence.

| Kiểu khóa | Thứ tự gần thời gian | Sinh phân tán | Rủi ro/đánh đổi chính |
|---|---|---|---|
| BIGINT sequence | Thường tăng theo cấp phát | Cần sequence hoặc dịch vụ cấp ID | Có thể tạo điểm ghi nóng ở trang cuối; ID có thể lộ thứ tự |
| UUID v4 | Không | Có | Ghi ngẫu nhiên, khóa rộng |
| UUID v7 | Có, theo timestamp | Có | Không nhất thiết monotonic tuyệt đối; vẫn rộng 16 byte |
| Snowflake-like ID | Thường có | Có nếu quản lý node/clock tốt | Cần vận hành worker ID và xử lý clock drift |
| Khóa tự nhiên | Phụ thuộc dữ liệu nghiệp vụ | Tùy nguồn dữ liệu | Có thể rộng, thay đổi hoặc mang ý nghĩa nhạy cảm |

Chọn UUID v7 hoặc Snowflake không tự động giải quyết last-page contention. Các giá trị có thứ tự thời gian vẫn có thể tập trung vào một vùng ghi. Cần đo concurrency và wait events.

## 7. Khóa tự nhiên và khóa thay thế

**Khóa tự nhiên (natural key)** là thuộc tính hoặc tổ hợp thuộc tính vốn có ý nghĩa nghiệp vụ, chẳng hạn mã quốc gia + mã số thuế, mã sản phẩm hoặc số hợp đồng.

**Khóa thay thế (surrogate key)** là định danh được tạo chủ yếu để định vị hàng, chẳng hạn BIGINT identity hoặc UUID.

### 7.1. Khi khóa tự nhiên phù hợp

Khóa tự nhiên có thể phù hợp khi:

- Ngắn và có kích thước ổn định.
- Không thay đổi trong suốt vòng đời dữ liệu.
- Quy tắc duy nhất được xác định rõ và được bảo đảm bởi ràng buộc.
- Được sử dụng thường xuyên trong nghiệp vụ và join.
- Không chứa thông tin nhạy cảm cần tránh lan truyền.

Ví dụ, mã ISO quốc gia gồm hai ký tự có thể là khóa tự nhiên gọn và ổn định cho bảng country. Ngược lại, email, số điện thoại hoặc địa chỉ thường không phù hợp làm PK lâu dài vì có thể thay đổi, chuẩn hóa phức tạp hoặc được tái sử dụng.

### 7.2. Khi khóa thay thế phù hợp

Surrogate key hữu ích khi khóa nghiệp vụ dài, có thể thay đổi, gồm nhiều cột hoặc cần định danh độc lập với quy tắc nghiệp vụ. Bảng vẫn có thể giữ unique constraint trên khóa tự nhiên để bảo đảm không có dữ liệu trùng.

~~~sql
CREATE TABLE products (
    product_id BIGINT NOT NULL,
    sku VARCHAR(80) NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    PRIMARY KEY (product_id),
    UNIQUE (sku)
);
~~~

Trong ví dụ, product_id là PK gọn; sku vẫn được bảo đảm duy nhất. Nếu SKU thay đổi theo chiến lược kinh doanh, các bảng tham chiếu product_id không cần cập nhật theo.

Không nên chọn surrogate key chỉ vì nó có vẻ nhanh hơn. Nếu khóa tự nhiên đã ngắn, bất biến và có ý nghĩa rõ, dùng trực tiếp có thể đơn giản hóa mô hình. Hãy so sánh chi phí thực tế và yêu cầu nghiệp vụ.

## 8. Khóa ghép và độ rộng của khóa ngoại

Khóa ghép gồm nhiều cột:

~~~sql
CREATE TABLE order_items (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    PRIMARY KEY (order_id, line_no)
);
~~~

Khóa ghép có thể mô tả đúng định danh tự nhiên của hàng con: một dòng được xác định bởi đơn hàng và số thứ tự dòng. Tuy nhiên, nếu nhiều bảng khác tham chiếu đến order_items, chúng phải lưu cả hai thành phần của khóa.

Những điều cần cân nhắc:

- Mỗi thành phần tăng thêm dung lượng khóa và chi phí so sánh.
- Chỉ mục trên khóa ghép có thứ tự theo các cột khai báo.
- Truy vấn chỉ lọc cột không phải tiền tố có thể không tận dụng toàn bộ khả năng tìm kiếm của B-tree.
- Khóa ngoại ghép cần truyền nhiều giá trị trong join và index.
- Thay đổi một thành phần khóa có thể gây cập nhật nhiều bảng tham chiếu.

Một phương án là dùng surrogate key gọn cho hàng, đồng thời giữ unique constraint trên cặp nghiệp vụ:

~~~sql
CREATE TABLE order_items (
    order_item_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    PRIMARY KEY (order_item_id),
    UNIQUE (order_id, line_no)
);
~~~

Phương án này làm tăng thêm một chỉ mục unique và một cột, nhưng các bảng tham chiếu order_item có thể chỉ cần một BIGINT. Cần cân nhắc số lượng bảng tham chiếu, kích thước dữ liệu và truy vấn thường dùng.

## 9. Thứ tự cột trong khóa ghép và chỉ mục B-tree

Với B-tree tổng hợp, thứ tự cột ảnh hưởng đến cách tìm kiếm. Chỉ mục:

~~~sql
CREATE INDEX orders_customer_created_id_idx
ON orders (customer_id, created_at, order_id);
~~~

có thể hỗ trợ tốt các truy vấn lọc bằng customer_id, sau đó theo created_at và order_id. Nó không nhất thiết hiệu quả cho truy vấn chỉ lọc order_id mà không có điều kiện trên các cột dẫn đầu.

Khi chọn thứ tự khóa ghép:

- Xác định các predicate bằng thường gặp.
- Xem các điều kiện phạm vi và ORDER BY.
- Xem join key và các truy vấn tra cứu từ bảng con.
- Đánh giá NDV, selectivity và phân bố dữ liệu.
- Xem các prefix của chỉ mục có được nhiều truy vấn sử dụng không.
- Tránh tạo nhiều chỉ mục gần giống nhau nếu một chỉ mục có thể đáp ứng nhiều workload.

Đối với primary key ghép trong InnoDB, thứ tự cột còn quyết định thứ tự clustered data và cách secondary index lưu khóa chính. Vì vậy, lựa chọn thứ tự PK có thể ảnh hưởng đến locality và kích thước của toàn bộ secondary index.

## 10. Khóa tăng dần và khóa ngẫu nhiên trong các cấu trúc lưu trữ

### 10.1. InnoDB

Vì primary key là clustered index, chèn hàng theo khóa tăng dần thường ghi vào vùng cuối của clustered B-tree. Cách này có thể tạo locality tốt, nhưng ở tải ghi rất cao có thể tập trung tranh chấp tại trang cuối.

Khóa UUID v4 có thể chèn vào nhiều vùng của clustered B-tree, làm tăng ghi ngẫu nhiên và page split. Vì clustered leaf chứa toàn bộ hàng, việc chèn ngẫu nhiên có thể ảnh hưởng trực tiếp đến bố trí dữ liệu và cache.

UUID v7 có thứ tự gần thời gian, thường cải thiện locality so với UUID v4. Tuy nhiên, cần benchmark với thư viện sinh ID thực tế, số writer và phân phối timestamp.

### 10.2. SQL Server

Nếu clustered index dùng khóa tăng dần, insert thường đi vào vùng cuối. Điều này có thể gây last-page latch contention trong workload ghi đồng thời cao. SQL Server có các tùy chọn như OPTIMIZE_FOR_SEQUENTIAL_KEY ở phiên bản hỗ trợ để điều tiết tranh chấp ở một số trường hợp; đây không phải giải pháp thay thế cho việc đo wait statistics và kiểm tra thiết kế chỉ mục.

Clustered key ngẫu nhiên có thể làm page split và fragmentation tăng. Fill factor thấp hơn có thể tạo chỗ trống cho insert trong một số mẫu ghi, nhưng đổi lại làm chỉ mục lớn hơn và tăng số trang đọc. Cần đánh giá theo workload.

### 10.3. PostgreSQL

Primary key trong PostgreSQL tạo unique B-tree index, nhưng heap không tự tổ chức theo thứ tự PK. Chèn UUID ngẫu nhiên ảnh hưởng chủ yếu đến trang của chỉ mục PK và các index khác có khóa tương ứng, không tự động làm heap được sắp xếp lại theo PK.

Một sequence tăng dần có thể giúp index locality, nhưng vẫn có thể tập trung cập nhật trang lá cuối. PostgreSQL có cơ chế quản lý page split và fillfactor cho index, nhưng việc điều chỉnh cần dựa trên page split, cache hit, WAL và wait/I/O thực tế.

### 10.4. Không suy luận chỉ từ tên kiểu ID

BIGINT tăng dần, UUID v4 và UUID v7 chỉ là các mẫu sinh giá trị. Hiệu năng thực tế còn phụ thuộc:

- Kiểu index và cách DBMS tổ chức row.
- Số lượng secondary index.
- Tỷ lệ insert/update/delete.
- Số writer đồng thời.
- Kích thước trang và fill factor.
- Cache/buffer pool.
- Phân phối key theo tenant hoặc shard.
- Kích thước payload và tỷ lệ đọc/ghi.

## 11. Khóa chính và khóa ngoại trong quan hệ bảng

Khóa chính thường được sao chép vào bảng con dưới dạng foreign key. Nếu PK rộng, mỗi hàng con phải lưu giá trị tham chiếu rộng tương ứng. Khi bảng con rất lớn, chi phí có thể đáng kể.

Ví dụ:

~~~sql
CREATE TABLE orders (
    order_id BIGINT NOT NULL PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE order_events (
    event_id BIGINT NOT NULL PRIMARY KEY,
    order_id BIGINT NOT NULL,
    event_type VARCHAR(40) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
);
~~~

Nếu order_id được đổi từ BIGINT sang UUID, mọi bảng con cần lưu UUID tương ứng. Chỉ mục trên order_id của bảng con cũng rộng hơn. Truy vấn join, replication và payload truyền giữa dịch vụ có thể tăng.

Một số hệ quản trị không tự tạo index trên cột foreign key khi khai báo ràng buộc. Cần kiểm tra DBMS và tạo index phù hợp cho thao tác join, delete/update ở bảng cha hoặc truy vấn tìm hàng con. Index trên foreign key không chỉ phục vụ SELECT; nó còn có thể giúp kiểm tra tham chiếu và tránh quét bảng con khi thay đổi hàng cha.

Không nên rút ngắn khóa ngoại bằng cách chỉ lưu một phần UUID hoặc hash không có cơ chế xử lý va chạm. Nếu dùng hash để tra cứu, phải giữ định danh đầy đủ và xác minh tính duy nhất bằng một ràng buộc thích hợp.

## 12. Khóa có tính tăng dần và bảo mật

ID tuần tự dễ đoán có thể làm lộ số lượng tương đối của bản ghi hoặc cho phép người dùng thử các ID kế tiếp. Điều này không phải lỗi của bản thân khóa nếu API kiểm tra quyền đúng, nhưng không nên dùng tính khó đoán của ID như một cơ chế phân quyền.

Các nguyên tắc:

- Kiểm tra quyền truy cập theo chủ thể và tài nguyên ở mọi request.
- Không coi UUID ngẫu nhiên là thay thế cho authorization.
- Tránh để ID tuần tự tiết lộ thông tin nghiệp vụ nếu đó là dữ liệu nhạy cảm.
- Có thể dùng public identifier riêng với internal primary key nếu cần tách định danh nội bộ và mã hiển thị.
- Nếu dùng public token, cần đủ entropy và kiểm tra quyền độc lập.

Ví dụ, bảng có BIGINT PK nội bộ và public_id UUID cho URL công khai. Cách này tăng thêm một chỉ mục và một cột, nhưng cho phép giữ khóa nội bộ nhỏ trong quan hệ cơ sở dữ liệu. Chỉ nên dùng khi yêu cầu bảo mật, tích hợp hoặc phân tán biện minh cho chi phí bổ sung.

## 13. Di trú từ khóa ngẫu nhiên sang khóa có thứ tự

Thay PK của bảng lớn là thay đổi rủi ro cao. Có thể phải cập nhật bảng con, chỉ mục, foreign key, ORM mapping, API và dữ liệu tích hợp. Không nên đổi trực tiếp chỉ vì benchmark một truy vấn cho thấy UUID v4 chậm.

Một kế hoạch di trú có kiểm soát có thể gồm:

1. Xác định vấn đề đo được: dung lượng index, page split, random I/O, cache miss hay insert contention.
2. Xác định các bảng con, foreign key, index, view, trigger, ETL và dịch vụ đang dùng PK.
3. Chọn khóa thay thế phù hợp với DBMS và yêu cầu sinh ID phân tán.
4. Thêm cột khóa mới và cơ chế sinh giá trị, giữ PK cũ trong giai đoạn chuyển tiếp.
5. Backfill theo batch có giới hạn để kiểm soát WAL/redo, lock và replication lag.
6. Tạo unique index và index cho khóa mới; xác minh không có NULL hoặc trùng.
7. Đồng bộ khóa mới sang bảng con bằng chiến lược nhất quán, có thể dual-write hoặc migration theo từng đợt.
8. Chuyển ứng dụng và truy vấn sang khóa mới, theo dõi lỗi join và dữ liệu mồ côi.
9. Chuyển ràng buộc PK/FK theo kế hoạch bảo trì và khả năng online DDL của hệ quản trị.
10. Giữ đường rollback và đối chiếu số hàng, quan hệ tham chiếu trước khi loại bỏ khóa cũ.

Tên lệnh và khả năng đổi constraint online khác nhau theo hệ quản trị. Với bảng lớn, cần kiểm tra lock duration, transaction log/WAL, replication lag và dung lượng tạm trước khi thực hiện.

## 14. Đo hiệu năng của chiến lược khóa

Không nên đánh giá khóa chỉ bằng thời gian INSERT đơn lẻ. Cần kiểm tra toàn bộ workload gồm ghi, đọc, join và bảo trì chỉ mục.

### 14.1. Chuẩn bị benchmark

So sánh ít nhất các cấu hình có ý nghĩa:

- BIGINT tăng dần.
- UUID v4.
- UUID v7 hoặc ID có thứ tự thời gian.
- Khóa ghép hoặc natural key nếu đó là phương án thực tế.

Dùng cùng số hàng, phân phối dữ liệu, số secondary index, kích thước payload, cấu hình cache và số writer. Đo cả khi dữ liệu vừa với cache và khi working set lớn hơn cache nếu điều kiện vận hành có thể xảy ra.

### 14.2. Chỉ số cần thu thập

| Nhóm | Chỉ số |
|---|---|
| Ghi | Insert throughput, p50/p95/p99 latency, số hàng ghi/giây |
| Chỉ mục | Kích thước PK index, secondary index, page split, fragmentation hoặc mức sử dụng trang |
| I/O | Logical reads, physical reads, page reads/writes, WAL/redo và temp I/O |
| Cache | Buffer/cache hit ratio, working set và eviction |
| Đồng thời | Latch/lock waits, wait events, deadlocks và số writer hoạt động |
| Lưu trữ | Dung lượng bảng, index, backup và replication traffic |
| Đọc | Join latency, range scan, point lookup và p95/p99 của truy vấn phổ biến |
| Bảo trì | Thời gian tạo/rebuild index, vacuum/analyze hoặc tác vụ tương đương |

### 14.3. Thử tải nhiều mức đồng thời

Chạy cùng workload với 1, 4, 16, 32 hoặc số writer phù hợp với hệ thống. Nếu khóa tăng dần nhanh ở một writer nhưng throughput không tăng khi tăng writer, hãy kiểm tra last-page contention. Nếu UUID v4 tăng page split và random I/O, hãy xem index size, cache hit và physical reads.

Không chỉ đo tổng throughput. Một cấu hình có thể đạt throughput cao hơn nhưng p99 insert hoặc read latency xấu hơn. Hãy ghi nhận phân phối độ trễ và wait events.

### 14.4. Kiểm tra tác động đến truy vấn đọc

Khóa chính được dùng trong point lookup, join và foreign key. Chạy các truy vấn thực tế:

- Tra cứu một hàng theo PK.
- Join bảng cha-con.
- Lấy các hàng theo khoảng ID hoặc thời gian.
- Lọc theo secondary index rồi lấy hàng.
- Sắp xếp hoặc phân trang theo khóa.

Khóa tuần tự có thể hỗ trợ range scan theo thời gian nếu thứ tự khóa phản ánh yêu cầu truy vấn. UUID v4 không có thứ tự thời gian; truy vấn theo khoảng tạo UUID không đại diện cho khoảng thời gian nghiệp vụ.

## 15. Ví dụ thiết kế cho hệ thống đơn hàng

Giả sử hệ thống có:

- 50 triệu customers.
- 500 triệu orders.
- 2 tỷ order_events.
- Nhiều bảng con tham chiếu order_id.
- Tải ghi cao vào orders và order_events.

Hai phương án:

**Phương án A — UUID v4 làm PK**

~~~sql
CREATE TABLE orders (
    order_id BINARY(16) NOT NULL,
    customer_id BIGINT NOT NULL,
    created_at DATETIME(6) NOT NULL,
    total_amount DECIMAL(18,2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY orders_customer_created_idx (customer_id, created_at)
) ENGINE=InnoDB;
~~~

**Phương án B — BIGINT tăng dần làm PK**

~~~sql
CREATE TABLE orders (
    order_id BIGINT NOT NULL AUTO_INCREMENT,
    customer_id BIGINT NOT NULL,
    created_at DATETIME(6) NOT NULL,
    total_amount DECIMAL(18,2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY orders_customer_created_idx (customer_id, created_at)
) ENGINE=InnoDB;
~~~

Trong InnoDB, secondary index mang theo PK. Vì vậy, phương án A có thể làm secondary index lớn hơn phương án B. Khóa UUID v4 cũng phân tán vị trí insert trong clustered index. Phương án B có locality ghi tốt hơn trong nhiều trường hợp, nhưng có thể tạo vùng ghi cuối tập trung khi số writer lớn.

Nếu hệ thống cần sinh ID phân tán, UUID v7 có thể là phương án thứ ba:

~~~sql
-- Kiểu lưu binary 16 byte; ID được ứng dụng sinh theo UUID v7
CREATE TABLE orders (
    order_id BINARY(16) NOT NULL,
    customer_id BIGINT NOT NULL,
    created_at DATETIME(6) NOT NULL,
    total_amount DECIMAL(18,2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY orders_customer_created_idx (customer_id, created_at)
) ENGINE=InnoDB;
~~~

DDL không tự sinh UUID v7; ứng dụng hoặc thư viện được kiểm soát phải tạo đúng định dạng. Cần thống nhất byte order và xác minh thứ tự lưu trữ phù hợp với cách DBMS so sánh giá trị nhị phân.

Quyết định không thể dựa vào DDL. Hãy benchmark cùng số hàng, cùng secondary index, cùng workload và số writer. Đo kích thước toàn bộ index, insert p95/p99, page split, cache miss, join latency và replication traffic. Nếu UUID v4 là yêu cầu tích hợp bắt buộc, lợi ích về khả năng sinh ID phân tán có thể đáng giá phần chi phí lưu trữ.

## 16. Những sai lầm thường gặp

- **Chỉ chọn PK vì nó duy nhất.** Cần xem độ rộng, tính ổn định, cách sinh và ảnh hưởng đến index.
- **Cho rằng UUID luôn chậm.** UUID có nhiều phiên bản và cách lưu khác nhau; hiệu năng phụ thuộc DBMS và workload.
- **Cho rằng UUID v7 tăng nghiêm ngặt từng ID.** Timestamp giúp thứ tự gần thời gian, nhưng phần còn lại và implementation có thể không monotonic tuyệt đối.
- **Cho rằng BIGINT tăng dần luôn nhanh nhất.** Nó có thể gây last-page contention ở tải ghi đồng thời cao.
- **Cho rằng mọi DBMS đều chép PK vào secondary index.** InnoDB, SQL Server clustered index và PostgreSQL heap có cách định vị hàng khác nhau.
- **Dùng chuỗi UUID thay cho binary mà không đo.** Biểu diễn chuỗi có thể làm tăng kích thước và chi phí so sánh.
- **Dùng khóa nghiệp vụ có thể thay đổi làm PK.** Cập nhật khóa có thể lan sang bảng con và chỉ mục.
- **Dùng composite PK rộng ở mọi bảng con.** Mỗi bảng tham chiếu phải lưu toàn bộ thành phần khóa.
- **Dùng ID tăng dần như bằng chứng thứ tự commit.** Giá trị được cấp phát và transaction commit là hai sự kiện khác nhau.
- **Tăng fill factor hoặc giảm page split mà không đo.** Trang có nhiều khoảng trống làm index lớn hơn và tăng chi phí đọc.
- **Thay PK của bảng lớn mà không lập kế hoạch di trú.** Ràng buộc, ứng dụng và hàng tỷ khóa ngoại có thể cần cập nhật.

## 17. Quy trình lựa chọn khóa chính

1. **Xác định yêu cầu định danh.** Khóa cần duy nhất toàn cục, trong tenant hay chỉ trong bảng? ID có cần sinh offline hoặc từ nhiều node không?
2. **Xác định tính ổn định.** Thuộc tính có thể thay đổi, tái sử dụng hoặc chứa thông tin nhạy cảm không?
3. **Đo độ rộng và fan-out.** Ước lượng dung lượng PK, secondary index, foreign key và dữ liệu truyền qua join.
4. **Hiểu cấu trúc DBMS.** Xác định clustered index, heap, row locator và cách secondary index lưu khóa tham chiếu.
5. **Phân tích mẫu ghi.** Số writer, tốc độ insert, phân phối khóa, page split và last-page contention.
6. **Phân tích mẫu đọc.** Point lookup, range scan, join, sort, pagination và thứ tự nghiệp vụ.
7. **Chọn cơ chế sinh ID.** Sequence, identity, UUID v4/v7, Snowflake-like hoặc natural key; kiểm tra clock, node ID và khả năng va chạm.
8. **Thiết kế khóa ngoại.** Xem các bảng con và chỉ mục tham chiếu; cân nhắc surrogate key khi khóa tự nhiên quá rộng hoặc dễ thay đổi.
9. **Benchmark nhiều mức tải.** So sánh latency, throughput, index size, I/O, cache và wait events.
10. **Đánh giá chi phí vòng đời.** Backup, replication, migration, index rebuild, API và khả năng vận hành lâu dài.

## 18. Checklist kiểm chứng

- [ ] Khóa chính duy nhất, NOT NULL và ổn định trong vòng đời hàng.
- [ ] Đã so sánh kích thước biểu diễn và overhead của từng phương án.
- [ ] Đã xác định DBMS lưu row locator và secondary index theo cách nào.
- [ ] Đã tính tác động của PK đến secondary index và foreign key.
- [ ] Đã đánh giá natural key, surrogate key và composite key theo nghiệp vụ.
- [ ] Đã kiểm tra thứ tự cột và prefix của chỉ mục ghép.
- [ ] Đã đo insert throughput và p95/p99 ở nhiều mức đồng thời.
- [ ] Đã theo dõi page split, fragmentation, last-page contention và wait events.
- [ ] Đã kiểm tra point lookup, range scan, join và pagination.
- [ ] Đã xem dung lượng index, buffer/cache hit, WAL/redo và replication.
- [ ] Nếu dùng UUID/ID phân tán, đã kiểm tra implementation, byte order, clock và worker identity.
- [ ] Nếu đổi PK, đã lập kế hoạch cập nhật foreign key, index, ứng dụng và rollback.
- [ ] Đã xác nhận tính duy nhất, tính toàn vẹn tham chiếu và kết quả nghiệp vụ sau thay đổi.

Khóa chính ảnh hưởng đến hiệu năng thông qua kích thước, thứ tự sinh giá trị và cách hệ quản trị tổ chức hàng cùng chỉ mục. Khóa nhỏ có thể giảm dung lượng index và foreign key; khóa tăng dần có thể cải thiện locality nhưng tập trung ghi vào vùng cuối; khóa ngẫu nhiên hỗ trợ sinh phân tán nhưng có thể làm truy cập và chèn kém cục bộ. Ảnh hưởng cụ thể khác nhau giữa InnoDB, SQL Server và PostgreSQL. Hãy lựa chọn theo yêu cầu định danh và cấu trúc lưu trữ thực tế, sau đó benchmark cả workload đọc/ghi, dung lượng chỉ mục và mức tranh chấp trước khi kết luận.
