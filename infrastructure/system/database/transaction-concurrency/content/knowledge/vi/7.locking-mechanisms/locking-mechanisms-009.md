# Khóa do ràng buộc, chỉ mục và khóa ngoại phát sinh

Trong một giao dịch cơ sở dữ liệu, ứng dụng có thể không hề viết câu lệnh khóa tường minh như SELECT ... FOR UPDATE, nhưng hệ quản trị cơ sở dữ liệu vẫn phải lấy khóa để bảo vệ tính đúng đắn của dữ liệu. Những khóa này thường xuất hiện khi kiểm tra ràng buộc, tra cứu chỉ mục hoặc duy trì quan hệ khóa ngoại.

Ví dụ, khi thêm một tài khoản với email phải duy nhất, cơ sở dữ liệu cần bảo đảm không có giao dịch đồng thời nào thêm cùng email. Khi thêm một đơn hàng tham chiếu đến khách hàng, cơ sở dữ liệu cần bảo đảm khách hàng vẫn tồn tại tại thời điểm kiểm tra. Khi xóa một khách hàng, cơ sở dữ liệu phải xác định có đơn hàng nào đang tham chiếu đến khách hàng đó hay không. Mỗi thao tác có thể tạo ra khóa và thời gian chờ dù câu lệnh SQL nhìn rất đơn giản.

Hiểu các khóa phát sinh này giúp giải thích những tình huống thường gặp như INSERT bị treo, UPDATE chờ dù không sửa cùng một dòng, xóa bản ghi cha bị chặn bởi bản ghi con, hoặc hai giao dịch deadlock khi cùng duy trì các ràng buộc.

## 1. Khóa phát sinh là gì?

Có thể chia khóa trong một giao dịch thành hai nhóm theo cách chúng được yêu cầu:

- **Khóa tường minh:** ứng dụng yêu cầu trực tiếp qua câu lệnh hoặc cú pháp khóa, chẳng hạn SELECT ... FOR UPDATE, SELECT ... FOR SHARE hay các câu lệnh khóa bảng.
- **Khóa phát sinh từ hoạt động của hệ quản trị:** hệ quản trị tự lấy khóa để kiểm tra ràng buộc, tìm bản ghi có khóa duy nhất, kiểm tra khóa ngoại, thay đổi mục chỉ mục hoặc bảo vệ một phạm vi dữ liệu theo mức cô lập.

Khóa phát sinh vẫn là một phần của cơ chế điều khiển đồng thời. Chúng có thể khiến giao dịch khác phải chờ, tham gia vào chu trình deadlock và thường được giữ đến khi giao dịch kết thúc nếu đó là khóa giao dịch. Ứng dụng không cần biết tên khóa nội bộ thì khóa vẫn ảnh hưởng đến khả năng chạy đồng thời.

### 1.1. Phân biệt khóa giao dịch và khóa nội bộ ngắn hạn

Không phải mọi cơ chế đồng bộ bên trong hệ quản trị đều là khóa giao dịch mà ứng dụng có thể quan sát như một lần chờ khóa.

- **Khóa giao dịch** bảo vệ một bản ghi, mục chỉ mục hoặc phạm vi dữ liệu trước các thay đổi xung đột. Nhiều loại khóa được giữ đến COMMIT hoặc ROLLBACK.
- **Latch hoặc khóa nội bộ ngắn hạn** bảo vệ cấu trúc trong bộ nhớ, chẳng hạn trang chỉ mục đang được cập nhật. Chúng thường chỉ tồn tại trong một khoảng rất ngắn để tránh hai luồng làm hỏng cấu trúc vật lý.

Khi nói một thao tác chỉ mục tạo ra khóa, cần xác định đang nói đến khóa giao dịch hay cơ chế đồng bộ nội bộ. Một lần chạm vào trang B-tree không có nghĩa toàn bộ trang hoặc toàn bộ chỉ mục bị khóa cho đến khi giao dịch kết thúc.

### 1.2. Vì sao hệ quản trị phải tự lấy khóa?

Cơ sở dữ liệu phải bảo vệ các bất biến dữ liệu trước những lịch thực thi đồng thời. Nếu chỉ kiểm tra dữ liệu tại thời điểm một câu lệnh bắt đầu mà không phối hợp với các giao dịch khác, hai giao dịch có thể cùng nhìn thấy trạng thái hợp lệ rồi cùng ghi ra một trạng thái vi phạm ràng buộc.

Các bất biến phổ biến gồm:

- Một giá trị hoặc tổ hợp giá trị phải là duy nhất.
- Giá trị khóa ngoại phải tham chiếu đến một hàng cha đang tồn tại.
- Không được xóa hàng cha khi vẫn còn hàng con tham chiếu, trừ khi hành động xóa dây chuyền được cho phép.
- Các mục chỉ mục phải phản ánh chính xác những hàng đã được thêm, sửa hoặc xóa.
- Các giao dịch ở mức cô lập cao phải không tạo ra lịch thực thi vi phạm quy tắc nhất quán mà hệ quản trị cam kết.

Hệ quản trị phối hợp việc kiểm tra và ghi dữ liệu bằng khóa, kiểm tra xung đột, cơ chế phiên bản hoặc tổ hợp các cơ chế đó. Cách triển khai cụ thể phụ thuộc vào sản phẩm cơ sở dữ liệu, mức cô lập, loại chỉ mục và kế hoạch thực thi.

## 2. Khóa phát sinh từ UNIQUE và chỉ mục duy nhất

Ràng buộc UNIQUE bảo đảm một cột hoặc một tổ hợp cột không có hai hàng mang cùng giá trị khóa theo quy tắc so sánh của chỉ mục. Để duy trì điều kiện đó khi nhiều giao dịch ghi đồng thời, hệ quản trị phải kiểm tra cả những thay đổi chưa được giao dịch khác xác nhận.

### 2.1. Hai giao dịch cùng thêm một giá trị duy nhất

Giả sử bảng account có chỉ mục duy nhất trên email:

~~~sql
CREATE TABLE account (
    id BIGINT PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE
);
~~~

Hai phiên làm việc chạy gần như đồng thời:

**Giao dịch A**

~~~sql
BEGIN;

INSERT INTO account (id, email)
VALUES (101, 'linh@example.com');

-- Chưa COMMIT
~~~

**Giao dịch B**

~~~sql
BEGIN;

INSERT INTO account (id, email)
VALUES (102, 'linh@example.com');

-- Có thể phải chờ giao dịch A
~~~

Khi giao dịch B kiểm tra chỉ mục duy nhất, nó gặp một mục chỉ mục có cùng khóa do giao dịch A tạo nhưng chưa biết kết quả cuối cùng. Nếu A COMMIT, B không thể chèn thêm giá trị trùng và sẽ nhận lỗi vi phạm UNIQUE. Nếu A ROLLBACK, B có thể tiếp tục và chèn giá trị đó.

Điểm quan trọng là B có thể phải chờ dù A và B dùng hai giá trị id khác nhau. Xung đột nằm ở giá trị email trong chỉ mục duy nhất, không nằm ở khóa chính id.

Tình huống này cho thấy ràng buộc duy nhất không thể chỉ được triển khai bằng một câu SELECT kiểm tra trước khi INSERT. Một cách làm ở tầng ứng dụng như sau là không an toàn khi có nhiều giao dịch đồng thời:

~~~sql
SELECT 1
FROM account
WHERE email = 'linh@example.com';

-- Nếu không thấy hàng thì mới INSERT
INSERT INTO account (id, email)
VALUES (102, 'linh@example.com');
~~~

Hai giao dịch có thể cùng chạy SELECT, cùng không thấy hàng, rồi cùng INSERT. Ràng buộc UNIQUE tại cơ sở dữ liệu mới là lớp bảo vệ cuối cùng. Ứng dụng nên thực hiện thao tác ghi nguyên tử và xử lý lỗi hoặc nhánh xung đột theo chính sách nghiệp vụ.

### 2.2. Cập nhật một khóa duy nhất

Xung đột không chỉ xảy ra khi INSERT. Khi UPDATE làm thay đổi giá trị của cột duy nhất, hệ quản trị phải kiểm tra giá trị mới và bảo đảm không có hàng khác chiếm giá trị đó.

~~~sql
UPDATE account
SET email = 'new@example.com'
WHERE id = 101;
~~~

Nếu một giao dịch khác đang giữ hoặc đang tạo giá trị new@example.com, câu lệnh có thể phải chờ. Nếu giá trị đã được một hàng khác sử dụng, câu lệnh thất bại vì vi phạm UNIQUE.

Khi một câu lệnh cập nhật nhiều hàng, các giá trị duy nhất mới của từng hàng đều có thể phát sinh kiểm tra và khóa. Vì vậy, một UPDATE hàng loạt có thể chờ tại chỉ mục dù các hàng đích không trùng nhau theo khóa chính.

### 2.3. UNIQUE nhiều cột

Với chỉ mục duy nhất nhiều cột, đơn vị cần kiểm tra là tổ hợp giá trị theo thứ tự cột của chỉ mục:

~~~sql
CREATE UNIQUE INDEX uq_membership
ON membership (organization_id, user_id);
~~~

Hai hàng có cùng user_id nhưng khác organization_id vẫn có thể hợp lệ. Ngược lại, hai giao dịch thêm cùng cặp organization_id và user_id có thể xung đột tại chỉ mục duy nhất.

Khi điều tra chờ khóa, cần xem đầy đủ định nghĩa chỉ mục. Chỉ nhìn một cột trong câu lệnh INSERT có thể dẫn đến kết luận sai về nguyên nhân xung đột.

### 2.4. Các quy tắc về NULL

Cách chỉ mục UNIQUE xử lý NULL khác nhau giữa các hệ quản trị và có thể có tùy chọn riêng. Nhiều hệ quản trị cho phép nhiều hàng có NULL trong cột UNIQUE vì NULL không được xem là bằng một NULL khác theo quy tắc mặc định. Một số hệ quản trị hoặc cấu hình có thể áp dụng quy tắc khác.

Không nên suy luận rằng hai giá trị NULL chắc chắn gây xung đột hoặc chắc chắn không gây xung đột. Hãy kiểm tra hành vi của hệ quản trị đang dùng và định nghĩa chỉ mục thực tế.

### 2.5. UPSERT vẫn có thể chờ khóa

Các cú pháp như INSERT ... ON CONFLICT của PostgreSQL hoặc INSERT ... ON DUPLICATE KEY UPDATE của MySQL giúp xử lý xung đột trong một thao tác nguyên tử. Chúng không loại bỏ nhu cầu kiểm tra chỉ mục duy nhất.

Ví dụ với PostgreSQL:

~~~sql
INSERT INTO account (id, email)
VALUES (102, 'linh@example.com')
ON CONFLICT (email)
DO UPDATE SET email = EXCLUDED.email;
~~~

Nếu một giao dịch khác đang tạo hoặc sửa hàng có cùng khóa duy nhất, câu lệnh vẫn có thể chờ. Nhánh DO UPDATE còn có thể lấy khóa trên hàng xung đột. UPSERT giúp tránh khoảng trống giữa bước kiểm tra và bước ghi ở tầng ứng dụng, nhưng không đồng nghĩa thao tác luôn không chặn.

## 3. Khóa phát sinh từ khóa ngoại

Khóa ngoại bảo đảm giá trị ở bảng con tham chiếu đến một hàng hợp lệ ở bảng cha. Khi ghi hoặc xóa dữ liệu, hệ quản trị phải phối hợp giữa hai phía của quan hệ.

Xét hai bảng:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customer(id)
);
~~~

customer là bảng cha; orders là bảng con. Mỗi orders.customer_id phải tham chiếu đến một customer.id đang tồn tại theo quy tắc của ràng buộc.

### 3.1. Thêm hoặc đổi khóa ngoại ở hàng con

Khi thêm một đơn hàng, hệ quản trị phải xác nhận khách hàng được tham chiếu tồn tại:

~~~sql
INSERT INTO orders (id, customer_id)
VALUES (5001, 42);
~~~

Việc kiểm tra này cần phối hợp với các giao dịch đang sửa hoặc xóa hàng customer có id = 42. Nếu chỉ đọc thấy hàng cha rồi bỏ qua trạng thái khóa, một giao dịch khác có thể xóa hàng cha trước khi giao dịch thêm hàng con hoàn tất, khiến quan hệ tham chiếu bị hỏng.

Vì vậy, hệ quản trị thường lấy một loại khóa bảo vệ hàng cha trong quá trình kiểm tra. Trong PostgreSQL, kiểm tra khóa ngoại thường sử dụng khóa hàng tương đương KEY SHARE trên hàng được tham chiếu. Trong InnoDB, việc kiểm tra khóa ngoại có thể lấy khóa chia sẻ trên bản ghi chỉ mục liên quan. Tên khóa và chi tiết tương thích khác nhau theo hệ quản trị.

Nếu giao dịch khác đang xóa hàng cha hoặc thay đổi khóa được tham chiếu bằng một thao tác xung đột, thao tác INSERT ở bảng con có thể phải chờ. Chiều ngược lại cũng đúng: giao dịch đang thêm hàng con có thể khiến thao tác xóa hàng cha phải đợi hoặc thất bại.

### 3.2. Xóa hàng cha

Giả sử giao dịch A đang thêm đơn hàng tham chiếu customer.id = 42. Đồng thời, giao dịch B muốn xóa khách hàng đó:

**Giao dịch A**

~~~sql
BEGIN;

INSERT INTO orders (id, customer_id)
VALUES (5001, 42);

-- Chưa COMMIT
~~~

**Giao dịch B**

~~~sql
BEGIN;

DELETE FROM customer
WHERE id = 42;
~~~

Hai thao tác có quan hệ phụ thuộc vì cùng tác động đến tính hợp lệ của khóa ngoại. Tùy thời điểm và hệ quản trị, B có thể phải chờ A kết thúc. Sau đó:

- Nếu A COMMIT và ràng buộc dùng hành động RESTRICT hoặc NO ACTION, B không thể xóa customer 42 khi hàng orders tham chiếu vẫn còn.
- Nếu A ROLLBACK, B có thể xóa hàng cha nếu không còn tham chiếu nào khác.
- Nếu ràng buộc dùng ON DELETE CASCADE, việc xóa hàng cha có thể kéo theo xóa các hàng con. Những hàng con bị tác động cũng cần được kiểm tra và khóa theo cơ chế của hệ quản trị.

Đối với ON DELETE SET NULL hoặc SET DEFAULT, hệ quản trị phải cập nhật các hàng con tương ứng. Những cập nhật đó cũng có thể phát sinh khóa, kiểm tra ràng buộc khác và chờ giao dịch đang truy cập các hàng con.

### 3.3. Cập nhật khóa được tham chiếu

Thay đổi giá trị khóa chính hoặc khóa duy nhất ở bảng cha cũng ảnh hưởng đến khóa ngoại:

~~~sql
UPDATE customer
SET id = 43
WHERE id = 42;
~~~

Nếu có hàng con tham chiếu id = 42, kết quả phụ thuộc vào hành động ON UPDATE của ràng buộc. Với RESTRICT hoặc NO ACTION, thao tác có thể bị từ chối. Với CASCADE, hệ quản trị cập nhật khóa ngoại ở các hàng con. Việc cập nhật dây chuyền có thể chạm đến nhiều hàng và chỉ mục, làm tăng số khóa và thời gian giữ khóa.

Trong thiết kế phổ biến, khóa định danh của hàng cha thường ổn định. Nếu một thuộc tính nghiệp vụ có thể thay đổi, nên cân nhắc dùng nó làm khóa thay thế thay vì dùng trực tiếp làm khóa tham chiếu của nhiều bảng.

### 3.4. Chỉ mục ở phía bảng con

Để kiểm tra một hàng cha có hàng con tham chiếu hay không, hệ quản trị cần tìm các giá trị tương ứng trong bảng con. Chỉ mục trên cột khóa ngoại có thể giúp tìm nhanh các hàng này:

~~~sql
CREATE INDEX idx_orders_customer_id
ON orders (customer_id);
~~~

Hành vi tạo chỉ mục tự động khác nhau:

- PostgreSQL yêu cầu khóa được tham chiếu ở bảng cha có chỉ mục phù hợp, thường là PRIMARY KEY hoặc UNIQUE. PostgreSQL không tự động tạo chỉ mục trên các cột khóa ngoại ở bảng con.
- InnoDB yêu cầu chỉ mục phù hợp ở phía bảng con và có thể tự tạo chỉ mục đó nếu chưa có chỉ mục đáp ứng yêu cầu.

Thiếu chỉ mục ở phía bảng con có thể khiến thao tác xóa hoặc cập nhật hàng cha phải tìm kiếm trên nhiều dữ liệu hơn. Với InnoDB, phạm vi bản ghi và khoảng chỉ mục bị khóa trong quá trình quét cũng có thể rộng hơn, tùy mức cô lập và kế hoạch thực thi. Chỉ mục phù hợp thường giảm thời gian tìm kiếm, số bản ghi phải xem xét và nguy cơ chặn giao dịch không liên quan.

Chỉ mục không làm mất nhu cầu kiểm tra khóa ngoại. Nó giúp hệ quản trị tìm các hàng cần kiểm tra hiệu quả hơn.

## 4. Chỉ mục và phạm vi khóa

Chỉ mục không chỉ phục vụ truy vấn đọc. Khi INSERT, UPDATE hoặc DELETE, hệ quản trị phải duy trì các cấu trúc chỉ mục tương ứng. Việc này có thể tạo ra xung đột tại mục chỉ mục, tại hàng dữ liệu hoặc tại khoảng khóa, tùy hệ quản trị và câu lệnh.

### 4.1. Thêm, sửa và xóa mục chỉ mục

Giả sử bảng account có:

~~~sql
CREATE INDEX idx_account_status
ON account (status);
~~~

Khi thêm một hàng, hệ quản trị phải thêm mục mới vào chỉ mục. Khi sửa status, hệ quản trị phải loại bỏ hoặc đánh dấu mục cũ không còn hợp lệ và tạo mục phản ánh giá trị mới. Khi xóa hàng, các mục chỉ mục liên quan cũng phải được xử lý.

Các thay đổi này thường được thực hiện cùng giao dịch với thay đổi hàng dữ liệu. Nếu một thao tác chạm vào mục chỉ mục đang có xung đột với giao dịch khác, nó có thể phải chờ. Tuy nhiên, không nên suy ra rằng mọi INSERT hoặc UPDATE đều giữ khóa độc quyền trên toàn bộ chỉ mục. Phạm vi khóa phụ thuộc loại chỉ mục, cách triển khai MVCC, mức cô lập và đường truy cập được chọn.

Một UPDATE trên cột không được lập chỉ mục vẫn có thể cần khóa hàng để bảo vệ dữ liệu. Một UPDATE trên cột có chỉ mục còn cần duy trì mục chỉ mục liên quan. Nếu cột được lập chỉ mục duy nhất, việc kiểm tra giá trị mới có thể tạo thêm điểm chờ như phần UNIQUE đã trình bày.

### 4.2. Khóa bản ghi và khóa khoảng trong InnoDB

InnoDB dùng chỉ mục để thực hiện nhiều thao tác khóa. Khi một câu lệnh khóa hoặc thay đổi dữ liệu quét chỉ mục, phạm vi bản ghi được khóa phụ thuộc vào các mục chỉ mục mà câu lệnh tìm thấy và mức cô lập.

Một số khái niệm thường gặp:

- **Record lock:** khóa một bản ghi chỉ mục cụ thể.
- **Gap lock:** khóa một khoảng giữa các bản ghi chỉ mục, ngăn giao dịch khác chèn giá trị mới vào khoảng đó trong những tình huống áp dụng.
- **Next-key lock:** kết hợp khóa bản ghi chỉ mục và khoảng ngay trước bản ghi đó.

Ví dụ, bảng có chỉ mục trên amount và các giá trị 10, 20, 40. Một truy vấn khóa theo khoảng có thể cần bảo vệ các mục đã tìm thấy và các khoảng liên quan để ngăn thao tác chèn làm thay đổi kết quả theo mức cô lập đang dùng.

~~~sql
START TRANSACTION;

SELECT *
FROM payment
WHERE amount >= 20 AND amount < 40
FOR UPDATE;
~~~

Trong InnoDB ở mức REPEATABLE READ, truy vấn khóa theo phạm vi có thể lấy next-key lock trên các mục chỉ mục được quét. Một giao dịch khác muốn chèn giá trị nằm trong khoảng bị khóa có thể phải chờ, dù nó chưa cập nhật hàng nào đang tồn tại.

Đây là lý do một INSERT đôi khi bị chặn bởi giao dịch đang chạy SELECT ... FOR UPDATE trên một khoảng dữ liệu. Hai giao dịch có thể không định sửa cùng một hàng hiện hữu; xung đột xuất hiện ở khoảng chỉ mục được bảo vệ.

Ở mức READ COMMITTED, InnoDB thường giảm việc dùng gap lock cho các thao tác tìm kiếm và quét chỉ mục thông thường, nhưng vẫn có ngoại lệ quan trọng, chẳng hạn kiểm tra khóa ngoại và kiểm tra khóa duy nhất. Không nên dự đoán phạm vi khóa chỉ từ câu SQL; cần xét mức cô lập, chỉ mục được dùng và kế hoạch thực thi.

### 4.3. PostgreSQL và khóa phạm vi

PostgreSQL dùng MVCC để cho phép các giao dịch đọc những phiên bản dữ liệu phù hợp với snapshot. Ở READ COMMITTED và REPEATABLE READ, một SELECT thông thường không lấy khóa hàng chỉ để đọc dữ liệu. Khóa hàng thường xuất hiện khi câu lệnh khóa tường minh hoặc khi INSERT, UPDATE, DELETE và kiểm tra ràng buộc cần bảo vệ dữ liệu.

PostgreSQL không dùng gap lock theo cách InnoDB thường dùng ở REPEATABLE READ. Tuy vậy, PostgreSQL vẫn có cơ chế khóa chỉ mục, khóa hàng và cơ chế bảo vệ tuần tự hóa ở mức SERIALIZABLE.

Ở mức SERIALIZABLE, PostgreSQL sử dụng Serializable Snapshot Isolation (SSI). Hệ quản trị theo dõi các phụ thuộc đọc/ghi bằng predicate lock, thường được hiển thị với loại SIReadLock. Những khóa theo dõi này không hoạt động như khóa chặn thông thường; chúng giúp phát hiện lịch thực thi có nguy cơ không tuần tự hóa được. Một giao dịch có thể bị hủy với lỗi serialization failure và ứng dụng phải chạy lại giao dịch theo chính sách phù hợp.

Vì vậy, khi thấy thông tin về khóa phạm vi, cần phân biệt khóa chặn giao dịch khác với khóa theo dõi phụ thuộc phục vụ SERIALIZABLE.

### 4.4. Kế hoạch thực thi ảnh hưởng đến phạm vi khóa

Cùng một câu SQL có thể tạo phạm vi khóa khác nhau nếu hệ quản trị chọn chỉ mục hoặc kế hoạch quét khác nhau.

Ví dụ:

~~~sql
UPDATE orders
SET status = 'PROCESSING'
WHERE customer_id = 42;
~~~

Nếu có chỉ mục phù hợp trên customer_id, hệ quản trị có thể tìm các hàng cần cập nhật trực tiếp hơn. Nếu thiếu chỉ mục, hệ quản trị có thể phải quét nhiều hàng. Trong InnoDB, phạm vi bản ghi được quét và khóa có thể lớn hơn đáng kể đối với câu lệnh cập nhật hoặc truy vấn khóa.

Điều này không có nghĩa cứ thêm chỉ mục là luôn tốt. Mỗi chỉ mục làm tăng chi phí ghi, dung lượng lưu trữ và công việc duy trì chỉ mục. Cần lập chỉ mục theo điều kiện truy vấn, khóa ngoại và mẫu truy cập thực tế.

## 5. Ràng buộc CHECK và các ràng buộc khác

Không phải mọi ràng buộc đều tạo cùng loại khóa.

Ràng buộc NOT NULL và CHECK thông thường kiểm tra giá trị của chính hàng đang được thêm hoặc cập nhật:

~~~sql
CREATE TABLE product (
    id BIGINT PRIMARY KEY,
    price DECIMAL(12, 2) NOT NULL,
    stock INT NOT NULL CHECK (stock >= 0)
);
~~~

Khi cập nhật stock, hệ quản trị xác thực giá trị mới không âm. Thao tác UPDATE vốn đã cần bảo vệ hàng được cập nhật; bản thân CHECK không nhất thiết phải khóa các hàng khác.

Cần phân biệt điều kiện trên một hàng với quy tắc nghiệp vụ liên quan nhiều hàng. Ví dụ, yêu cầu tổng số tiền phân bổ không vượt quá ngân sách của một dự án là quy tắc liên hàng. Một CHECK thông thường không thể bảo đảm quy tắc đó bằng cách chỉ kiểm tra giá trị của hàng hiện tại.

Nếu cần bảo vệ quy tắc liên hàng, hãy cân nhắc:

- Biểu diễn quy tắc bằng UNIQUE, FOREIGN KEY hoặc EXCLUDE constraint nếu mô hình dữ liệu phù hợp.
- Dùng một hàng tổng hợp hoặc hàng đại diện để các giao dịch cùng khóa và cập nhật nguyên tử.
- Dùng giao dịch ở mức SERIALIZABLE và sẵn sàng chạy lại khi gặp serialization failure.
- Dùng trigger hoặc thủ tục giao dịch có thiết kế đồng thời rõ ràng, tránh chỉ SELECT kiểm tra rồi mới INSERT/UPDATE.

Một số ràng buộc như exclusion constraint trong PostgreSQL cần kiểm tra xung đột giữa các giá trị hoặc phạm vi. Cơ chế kiểm tra có thể sử dụng chỉ mục và phối hợp với các giao dịch đang ghi. Vì vậy, không thể đánh đồng mọi ràng buộc với CHECK đơn giản.

## 6. Thời điểm kiểm tra và thời gian giữ khóa

Khóa phát sinh có thể xuất hiện ở nhiều thời điểm:

1. Khi câu lệnh bắt đầu tìm hàng hoặc mục chỉ mục cần thay đổi.
2. Khi kiểm tra giá trị duy nhất hoặc xác thực khóa ngoại.
3. Khi cập nhật dây chuyền các hàng con.
4. Khi kiểm tra ràng buộc được trì hoãn đến cuối câu lệnh hoặc cuối giao dịch.
5. Khi COMMIT cần xác nhận các thay đổi và hoàn tất kiểm tra còn lại.

Một số ràng buộc có thể được khai báo DEFERRABLE trong những hệ quản trị hỗ trợ. Với ràng buộc được trì hoãn, kiểm tra có thể diễn ra muộn hơn thời điểm câu lệnh ghi dữ liệu. Điều này thay đổi thời điểm lỗi xuất hiện và có thể thay đổi thời gian giao dịch phải chờ. Không nên mặc định mọi ràng buộc đều được kiểm tra đúng tại thời điểm thực hiện từng câu INSERT hoặc UPDATE.

Với các khóa giao dịch, thời điểm lấy khóa và thời điểm nhả khóa là hai việc khác nhau. Nhiều khóa hàng và khóa chỉ mục được giữ đến COMMIT hoặc ROLLBACK. Vì vậy, một câu lệnh đã chạy xong vẫn có thể giữ khóa và tiếp tục chặn giao dịch khác nếu giao dịch bao ngoài chưa kết thúc.

Ví dụ:

~~~sql
BEGIN;

UPDATE customer
SET name = 'Linh Nguyen'
WHERE id = 42;

-- Câu UPDATE đã kết thúc nhưng giao dịch chưa kết thúc.
-- Các khóa cần thiết có thể vẫn được giữ ở đây.

-- Một số xử lý ứng dụng khác...

COMMIT;
~~~

Nếu ứng dụng gọi dịch vụ bên ngoài, chờ người dùng hoặc xử lý dữ liệu lớn trong khi giao dịch còn mở, thời gian giữ khóa có thể tăng lên. Điều này làm tăng xác suất chờ và deadlock.

## 7. Deadlock từ khóa phát sinh

Deadlock xảy ra khi các giao dịch tạo thành một chu trình chờ: mỗi giao dịch giữ tài nguyên mà giao dịch khác cần, nên không giao dịch nào có thể tiếp tục.

Khóa phát sinh từ chỉ mục và khóa ngoại có thể tham gia chu trình ngay cả khi ứng dụng không dùng câu lệnh khóa tường minh.

### 7.1. Hai giao dịch cập nhật các hàng theo thứ tự ngược nhau

Giả sử hai hàng cha có id = 1 và id = 2. Một luồng xử lý cập nhật hàng 1 rồi hàng 2; luồng còn lại cập nhật hàng 2 rồi hàng 1.

**Giao dịch A**

~~~sql
BEGIN;
UPDATE customer SET name = 'A1' WHERE id = 1;
-- Sau đó muốn cập nhật id = 2
~~~

**Giao dịch B**

~~~sql
BEGIN;
UPDATE customer SET name = 'B2' WHERE id = 2;
-- Sau đó muốn cập nhật id = 1
~~~

Nếu A đang giữ khóa hàng 1 và chờ hàng 2, trong khi B giữ khóa hàng 2 và chờ hàng 1, hệ quản trị phát hiện deadlock và chọn một giao dịch làm nạn nhân để rollback. Ứng dụng phải xử lý lỗi và có thể chạy lại toàn bộ giao dịch.

### 7.2. Deadlock qua khóa ngoại và chỉ mục

Một giao dịch có thể khóa hàng cha rồi cập nhật các hàng con. Giao dịch khác có thể bắt đầu từ hàng con, kiểm tra khóa ngoại rồi cần khóa hàng cha. Nếu hai giao dịch đi theo thứ tự tài nguyên khác nhau, chúng có thể tạo chu trình chờ.

Tình huống cụ thể phụ thuộc vào câu lệnh, hành động ON DELETE/ON UPDATE, loại chỉ mục và cách hệ quản trị triển khai kiểm tra ràng buộc. Không nên kết luận deadlock chỉ từ việc hai giao dịch cùng dùng một bảng; cần xem toàn bộ chuỗi tài nguyên đang giữ và đang chờ.

### 7.3. Giảm nguy cơ deadlock

Một số nguyên tắc thực tế:

- Thống nhất thứ tự truy cập tài nguyên giữa các luồng nghiệp vụ. Ví dụ, luôn xử lý hàng cha trước hàng con hoặc luôn xử lý các hàng theo thứ tự khóa chính tăng dần.
- Giữ giao dịch ngắn. Thực hiện xử lý không cần tính nhất quán giao dịch ở ngoài khối BEGIN/COMMIT.
- Tạo chỉ mục phù hợp cho điều kiện cập nhật và cột khóa ngoại để giảm phạm vi quét.
- Tránh cập nhật hàng loạt theo thứ tự không ổn định khi nhiều giao dịch có thể chạm cùng tập dữ liệu.
- Xử lý deadlock ở tầng ứng dụng bằng cách chạy lại toàn bộ giao dịch khi nhận đúng loại lỗi có thể retry. Cần giới hạn số lần thử và có backoff phù hợp.
- Không retry riêng câu lệnh cuối cùng nếu các câu lệnh trước đã bị rollback cùng giao dịch.

Deadlock là tình huống hệ quản trị phải xử lý để bảo đảm tiến triển. Mục tiêu thiết kế là giảm tần suất, giảm số giao dịch bị ảnh hưởng và bảo đảm ứng dụng phục hồi đúng.

## 8. Ví dụ tổng hợp: xóa khách hàng và thêm đơn hàng

Xét lại quan hệ customer và orders. Giả sử chỉ mục orders(customer_id) tồn tại và khóa ngoại dùng ON DELETE RESTRICT.

Một giao dịch thêm đơn hàng:

~~~sql
BEGIN;

INSERT INTO orders (id, customer_id)
VALUES (7001, 42);

-- Chưa COMMIT
~~~

Một giao dịch khác xóa khách hàng:

~~~sql
BEGIN;

DELETE FROM customer
WHERE id = 42;
~~~

Hệ quản trị phải bảo vệ tính hợp lệ của quan hệ trong suốt hai thao tác. Giao dịch thêm đơn hàng cần xác nhận hàng customer 42 tồn tại và bảo vệ tham chiếu trong lúc giao dịch còn hiệu lực. Giao dịch xóa khách hàng cần xác định có hàng orders nào tham chiếu hay không.

Có thể xảy ra các kết quả sau:

| Trạng thái giao dịch thêm đơn hàng | Kết quả có thể có của giao dịch xóa |
|---|---|
| Đơn hàng được COMMIT | Lệnh xóa bị từ chối vì còn hàng con tham chiếu |
| Đơn hàng được ROLLBACK | Lệnh xóa có thể tiếp tục nếu không còn tham chiếu khác |
| Giao dịch thêm đơn hàng chưa kết thúc | Lệnh xóa có thể phải chờ khóa hoặc kết quả kiểm tra của giao dịch đó |

Nếu đổi ràng buộc sang ON DELETE CASCADE, kết quả nghiệp vụ thay đổi: xóa khách hàng có thể xóa các đơn hàng liên quan. Khi đó, hệ quản trị phải xử lý thêm các hàng con, các chỉ mục của chúng và những ràng buộc tiếp theo. CASCADE không phải cách khắc phục chờ khóa; nó thay đổi phạm vi dữ liệu bị tác động.

## 9. Quan sát và chẩn đoán chờ khóa

Khi một câu lệnh bị treo, cần xác định giao dịch nào đang chờ, giao dịch nào đang chặn và tài nguyên xung đột là gì. Chỉ nhìn câu SQL của giao dịch bị chặn thường không đủ, vì nguyên nhân có thể nằm ở một giao dịch khác đã mở từ trước.

### 9.1. PostgreSQL

Có thể xem các phiên đang chạy, thời gian bắt đầu giao dịch và các phiên đang chặn:

~~~sql
SELECT
    pid,
    usename,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    query
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
~~~

Hàm pg_blocking_pids giúp tìm các PID đang chặn một phiên:

~~~sql
SELECT
    pid AS blocked_pid,
    pg_blocking_pids(pid) AS blocking_pids,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE cardinality(pg_blocking_pids(pid)) > 0;
~~~

Có thể kiểm tra thông tin khóa trong pg_locks:

~~~sql
SELECT
    locktype,
    mode,
    granted,
    relation::regclass AS relation,
    page,
    tuple,
    transactionid,
    pid
FROM pg_locks
WHERE pid IN (
    SELECT pid
    FROM pg_stat_activity
    WHERE datname = current_database()
)
ORDER BY pid, granted;
~~~

Không phải mọi khóa phát sinh đều hiện ra như một khóa hàng đơn giản. Chẳng hạn, giao dịch có thể chờ transaction ID của giao dịch khác khi kiểm tra xung đột phiên bản hoặc chỉ mục. Cần kết hợp pg_stat_activity, pg_locks, pg_blocking_pids và log deadlock để dựng lại chuỗi chờ.

### 9.2. MySQL InnoDB

Trong MySQL, có thể xem thông tin khóa đang được giữ và yêu cầu khóa đang chờ qua Performance Schema:

~~~sql
SELECT *
FROM performance_schema.data_locks;
~~~

~~~sql
SELECT *
FROM performance_schema.data_lock_waits;
~~~

Để xem thông tin chẩn đoán InnoDB, có thể dùng:

~~~sql
SHOW ENGINE INNODB STATUS;
~~~

Phần TRANSACTIONS và LATEST DETECTED DEADLOCK thường hữu ích khi điều tra giao dịch đang chờ hoặc deadlock gần nhất. Nội dung chi tiết phụ thuộc phiên bản MySQL và cấu hình Performance Schema.

Khi điều tra InnoDB, nên kiểm tra thêm mức cô lập, chỉ mục mà câu lệnh sử dụng và kế hoạch EXPLAIN. Những thông tin này giúp giải thích vì sao một truy vấn khóa theo điều kiện hẹp lại quét hoặc khóa phạm vi rộng.

### 9.3. Quy trình điều tra thực tế

Có thể đi theo trình tự sau:

1. Xác định câu lệnh và phiên đang chờ. Ghi nhận thời điểm bắt đầu, thời gian chờ và loại sự kiện chờ.
2. Tìm giao dịch đang chặn. Xem câu lệnh gần nhất của nó và thời điểm bắt đầu giao dịch; câu lệnh hiện tại có thể không phải câu lệnh đã lấy khóa.
3. Xác định bảng, hàng, chỉ mục hoặc khoảng dữ liệu liên quan. Đối chiếu định nghĩa UNIQUE, FOREIGN KEY, CHECK và các chỉ mục.
4. Kiểm tra kế hoạch thực thi và mức cô lập. Một lần quét rộng hoặc một next-key lock có thể giải thích phạm vi chờ.
5. Kiểm tra chuỗi phụ thuộc nếu có nhiều giao dịch. Nếu các giao dịch chờ vòng tròn, xem log deadlock hoặc thông tin detector của hệ quản trị.
6. Điều chỉnh chỉ mục, thứ tự truy cập hoặc thời lượng giao dịch; sau đó quan sát lại cùng mẫu tải để xác nhận tác động.

Không nên chỉ tăng lock timeout để che giấu vấn đề. Timeout có thể giúp ứng dụng thoát khỏi việc chờ quá lâu, nhưng không sửa nguyên nhân xung đột.

## 10. Thiết kế để giảm chờ khóa

### 10.1. Thiết kế ràng buộc đúng ở cơ sở dữ liệu

Dùng PRIMARY KEY, UNIQUE và FOREIGN KEY để bảo vệ bất biến dữ liệu ở nơi có thể kiểm soát mọi giao dịch. Kiểm tra trước ở tầng ứng dụng có thể cải thiện thông báo hoặc trải nghiệm, nhưng không thay thế được ràng buộc nguyên tử tại cơ sở dữ liệu.

Với quy tắc liên hàng, cần chọn cơ chế thực sự bảo vệ được quy tắc khi chạy đồng thời. Một câu SELECT kiểm tra tổng hoặc số lượng rồi mới ghi có thể gặp race condition.

### 10.2. Tạo chỉ mục cho khóa ngoại và điều kiện ghi

Đặc biệt chú ý chỉ mục ở phía bảng con. Khi xóa hoặc đổi khóa hàng cha, hệ quản trị cần tìm các hàng con liên quan. Chỉ mục phù hợp giúp giảm số hàng phải quét và thời gian giữ khóa.

Cũng cần lập chỉ mục cho điều kiện UPDATE/DELETE thường xuyên. Nếu câu lệnh chỉ nhắm đến một tập hàng nhỏ nhưng phải quét phần lớn bảng, phạm vi khóa và thời gian thực thi có thể tăng lên.

### 10.3. Giữ giao dịch ngắn và có thứ tự

Mở giao dịch ngay trước các thao tác cần tính nguyên tử, rồi COMMIT sớm khi đã hoàn thành. Tránh giữ giao dịch trong lúc chờ mạng, gọi dịch vụ ngoài, chờ nhập liệu hoặc xử lý tệp lớn.

Nếu một nghiệp vụ cần cập nhật nhiều bảng, xác định thứ tự truy cập ổn định và áp dụng nhất quán ở mọi luồng. Điều này giảm khả năng hai giao dịch lấy cùng tài nguyên theo thứ tự ngược nhau.

### 10.4. Chọn mức cô lập theo yêu cầu

Mức cô lập cao hơn có thể bảo vệ các quy tắc đọc/ghi phức tạp nhưng cũng làm tăng khả năng giao dịch phải chờ hoặc bị hủy để bảo đảm tính tuần tự hóa. Mức cô lập thấp hơn có thể tăng thông lượng nhưng không được bỏ qua các ràng buộc dữ liệu.

Hãy chọn mức cô lập theo bất biến nghiệp vụ cần bảo vệ, hành vi cụ thể của hệ quản trị và khả năng retry của ứng dụng. Không nên thay đổi mức cô lập chỉ để loại bỏ một lần chờ mà chưa hiểu cơ chế xung đột.

### 10.5. Xử lý lỗi xung đột và retry đúng cách

Ứng dụng cần phân biệt các lỗi như vi phạm UNIQUE, vi phạm FOREIGN KEY, lock timeout, deadlock và serialization failure. Chúng có ý nghĩa nghiệp vụ khác nhau:

- Vi phạm UNIQUE thường có nghĩa giá trị đã được sử dụng; ứng dụng có thể báo trùng hoặc chạy nhánh xử lý xung đột.
- Vi phạm FOREIGN KEY thường có nghĩa hàng được tham chiếu không tồn tại hoặc không thể bị xóa trong trạng thái hiện tại.
- Deadlock và serialization failure thường có thể retry toàn bộ giao dịch nếu nghiệp vụ cho phép.
- Lock timeout cần chính sách riêng: trả lỗi, thử lại có giới hạn hoặc đưa công việc vào hàng đợi.

Khi retry, cần bảo đảm các thao tác ngoài cơ sở dữ liệu có tính idempotent hoặc được điều phối phù hợp. Không gửi email, trừ tiền hoặc phát sự kiện không thể đảo ngược nhiều lần chỉ vì giao dịch được chạy lại.

## 11. Những nhầm lẫn thường gặp

**“Không dùng SELECT FOR UPDATE thì không thể bị chờ khóa.”**  
Sai. UNIQUE, FOREIGN KEY, thao tác ghi và các cơ chế bảo vệ mức cô lập có thể tạo khóa hoặc chờ xung đột tự động.

**“Hai giao dịch cập nhật hai hàng khác nhau thì chắc chắn không xung đột.”**  
Sai. Chúng có thể cùng ghi một giá trị duy nhất, cùng tác động đến hàng cha/con, hoặc cùng chạm một khoảng chỉ mục được khóa.

**“Có chỉ mục thì không còn chờ khóa.”**  
Sai. Chỉ mục giúp tìm dữ liệu nhanh hơn và có thể thu hẹp phạm vi quét, nhưng chỉ mục UNIQUE và kiểm tra khóa ngoại chính là nơi phát sinh một số xung đột cần thiết.

**“Khóa ngoại chỉ kiểm tra khi INSERT ở bảng con.”**  
Sai. UPDATE khóa ngoại, DELETE hàng cha, UPDATE khóa được tham chiếu và các hành động CASCADE đều có thể cần kiểm tra hoặc thay đổi dữ liệu ở cả hai phía.

**“Một câu lệnh đã chạy xong thì khóa của nó đã được nhả.”**  
Không đúng với nhiều khóa giao dịch. Khóa có thể được giữ đến COMMIT hoặc ROLLBACK.

**“Mọi hệ quản trị đều khóa khoảng giống nhau.”**  
Sai. InnoDB có record lock, gap lock và next-key lock trong các trường hợp phù hợp. PostgreSQL dùng MVCC và có cơ chế SSI riêng; không thể áp dụng nguyên xi mô hình khóa khoảng của InnoDB cho PostgreSQL.

**“Tăng timeout sẽ giải quyết deadlock.”**  
Sai. Deadlock là chu trình chờ; hệ quản trị thường phát hiện và hủy một giao dịch để phá chu trình. Tăng timeout không loại bỏ chu trình đó.

## 12. Cách suy luận khi gặp một lần chờ khóa

Khi một câu INSERT, UPDATE hoặc DELETE bị chặn, hãy lần lượt đặt các câu hỏi:

- Câu lệnh có ghi một cột hoặc tổ hợp cột UNIQUE không?
- Câu lệnh có thêm hoặc đổi giá trị FOREIGN KEY không?
- Có giao dịch nào đang xóa hoặc thay đổi hàng cha được tham chiếu không?
- Có hành động CASCADE khiến nhiều hàng con bị cập nhật hoặc xóa không?
- Câu lệnh có quét chỉ mục theo một phạm vi rộng không?
- Hệ quản trị đang dùng mức cô lập nào, và mức đó có tạo khóa phạm vi hoặc theo dõi phụ thuộc không?
- Giao dịch giữ khóa đã mở bao lâu và còn thực hiện công việc gì trước khi COMMIT?

Câu trả lời giúp phân biệt chờ do xung đột dữ liệu thực sự với chờ do phạm vi quét quá rộng hoặc giao dịch giữ khóa quá lâu. Từ đó có thể chọn cách xử lý phù hợp: sửa dữ liệu đầu vào, điều chỉnh ràng buộc, bổ sung chỉ mục, thay đổi thứ tự cập nhật, rút ngắn giao dịch hoặc thiết kế retry.

