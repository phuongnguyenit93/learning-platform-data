# REPLACE/upsert và chuỗi trigger thực tế được kích hoạt

Trong MySQL, hai câu lệnh thường được dùng để ghi dữ liệu theo kiểu “nếu chưa có thì thêm, nếu đã có thì xử lý tiếp” là `REPLACE` và `INSERT ... ON DUPLICATE KEY UPDATE`. Cả hai đều có thể gặp khóa PRIMARY KEY hoặc UNIQUE, nhưng ý nghĩa dữ liệu và chuỗi trigger của chúng rất khác nhau.

`REPLACE` có ngữ nghĩa xóa hàng xung đột rồi chèn hàng mới. Vì vậy, một lần REPLACE có thể kích hoạt trigger INSERT và trigger DELETE. `INSERT ... ON DUPLICATE KEY UPDATE` thử chèn; nếu phát hiện duplicate key thì chuyển sang nhánh UPDATE. Với mỗi hàng đầu vào, MySQL luôn kích hoạt BEFORE INSERT trước, sau đó hoặc chạy AFTER INSERT, hoặc chạy cả BEFORE UPDATE và AFTER UPDATE.

Sự khác biệt này ảnh hưởng trực tiếp đến audit log, bảng tổng hợp, đồng bộ dữ liệu, khóa ngoại, AUTO_INCREMENT và các trigger được gọi gián tiếp trên bảng khác. Nếu chỉ nhìn tên câu lệnh hoặc số hàng bị ảnh hưởng, rất dễ hiểu sai dữ liệu cũ đã bị xóa, dữ liệu mới đã được cập nhật hay trigger nào thực sự chạy.

Bài học này đi theo từng nhánh thực thi, xây dựng một chuỗi trigger nhiều bảng có thể quan sát được, rồi đưa ra quy trình kiểm thử và các quy tắc vận hành an toàn.

Các ví dụ dùng cú pháp SQL phía server. Khi tạo trigger có thân BEGIN ... END bằng mysql command-line client, hãy đổi delimiter của client (chẳng hạn sang //) trước câu CREATE rồi khôi phục delimiter sau đó. DELIMITER là lệnh của mysql client, không phải SQL gửi đến server. Với driver ứng dụng, gửi toàn bộ câu CREATE TRIGGER như một statement theo API của driver.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt REPLACE với INSERT ... ON DUPLICATE KEY UPDATE.
- Giải thích vì sao REPLACE mang ngữ nghĩa DELETE + INSERT.
- Liệt kê trigger được kích hoạt trong nhánh insert, duplicate-update và replace.
- Đọc chuỗi BEFORE/AFTER theo từng hàng của một câu lệnh nhiều hàng.
- Hiểu cách một trigger ghi sang bảng khác có thể kích hoạt trigger tiếp theo.
- Phân biệt trigger UPDATE với trigger DELETE/INSERT trong hai kiểu upsert.
- Nhận biết tác động của nhiều UNIQUE index đối với REPLACE và upsert.
- Đánh giá tác động của REPLACE lên AUTO_INCREMENT và khóa ngoại.
- Dùng row alias trong ON DUPLICATE KEY UPDATE thay cho VALUES() đã deprecated.
- Hiểu FOLLOWS và PRECEDES khi có nhiều trigger cùng thời điểm/sự kiện.
- Xác định giới hạn trigger, tính nguyên tử và hành vi khi trigger lỗi.
- Kiểm tra metadata trigger và thiết kế ma trận kiểm thử cho từng nhánh.

## 1. Trigger phản ứng với thao tác trên hàng, không chỉ với tên câu lệnh

MySQL định nghĩa trigger theo ba loại thao tác trên hàng:

- INSERT: có một hàng mới được đưa vào bảng.
- UPDATE: một hàng hiện có được sửa.
- DELETE: một hàng hiện có bị xóa.

Trigger còn có thời điểm:

- BEFORE: chạy trước thao tác trên hàng.
- AFTER: chạy sau khi thao tác trên hàng thành công.

Mỗi trigger có FOR EACH ROW. MySQL không hỗ trợ statement-level trigger chạy đúng một lần cho toàn bộ câu SQL. Nếu một câu INSERT thêm 500 hàng, trigger tương ứng có thể chạy 500 lần cho mỗi loại trigger được kích hoạt.

Ma trận cơ bản:

| Câu lệnh | Thao tác trên hàng | Chuỗi trigger cơ bản |
|---|---|---|
| INSERT thành công | Insert | BEFORE INSERT → AFTER INSERT |
| UPDATE | Update | BEFORE UPDATE → AFTER UPDATE |
| DELETE | Delete | BEFORE DELETE → AFTER DELETE |
| REPLACE, không có duplicate | Insert | BEFORE INSERT → AFTER INSERT |
| REPLACE, có duplicate | Delete hàng cũ rồi insert hàng mới | BEFORE INSERT → BEFORE DELETE/AFTER DELETE cho hàng xung đột → AFTER INSERT |
| INSERT ... ON DUPLICATE KEY UPDATE, không duplicate | Insert | BEFORE INSERT → AFTER INSERT |
| INSERT ... ON DUPLICATE KEY UPDATE, có duplicate | Update hàng cũ | BEFORE INSERT → BEFORE UPDATE → AFTER UPDATE |

Điểm mấu chốt: REPLACE không chuyển sang UPDATE trigger. INSERT ... ON DUPLICATE KEY UPDATE không chuyển sang DELETE trigger. Hai câu lệnh giải quyết duplicate theo hai cách khác nhau.

## 2. REPLACE là xóa hàng xung đột rồi chèn hàng mới

REPLACE là phần mở rộng của MySQL. Khi hàng mới có giá trị trùng với PRIMARY KEY hoặc UNIQUE index, MySQL xóa hàng đang xung đột rồi thử chèn hàng mới.

Cú pháp thường dùng:

    REPLACE INTO product (
        product_id,
        product_name,
        price
    )
    VALUES (
        101,
        'Keyboard',
        49.90
    );

Nếu product_id 101 chưa tồn tại, đây là một thao tác insert thông thường. Nếu đã tồn tại, hàng cũ bị xóa và hàng mới được chèn.

### 2.1. Chuỗi trigger khi REPLACE gặp duplicate

Với một hàng đầu vào, thứ tự logic có thể đọc như sau:

1. MySQL thử chèn hàng mới; BEFORE INSERT chạy cho hàng đang được thử.
2. Nếu PRIMARY KEY hoặc UNIQUE index bị trùng, MySQL tìm hàng xung đột.
3. BEFORE DELETE chạy cho hàng cũ sắp bị xóa.
4. Hàng cũ bị xóa; AFTER DELETE chạy.
5. MySQL thử lại thao tác chèn hàng mới.
6. Khi hàng mới được chèn thành công, AFTER INSERT chạy.

Sơ đồ:

    REPLACE
       |
       v
    BEFORE INSERT
       |
       v
    Có duplicate key?
       |
       +---- Không ----------------------+
       |                                 |
       |                                 v
       |                            Insert row
       |                                 |
       |                                 v
       |                            AFTER INSERT
       |
       +---- Có
             |
             v
        BEFORE DELETE
             |
             v
          Delete old row
             |
             v
        AFTER DELETE
             |
             v
        Retry insert new row
             |
             v
        AFTER INSERT

Vì vậy, khi REPLACE thay thế một hàng, audit có thể ghi nhận cả việc xóa hàng cũ và thêm hàng mới. Không nên chỉ tạo trigger AFTER INSERT rồi kết luận rằng thao tác thay thế đã được ghi nhận đầy đủ.

Nếu BEFORE INSERT phát lỗi, thao tác trên hàng chưa diễn ra và không có AFTER INSERT. Nếu BEFORE DELETE hoặc AFTER DELETE phát lỗi, REPLACE thất bại theo quy tắc lỗi trigger; với bảng transactional, các thay đổi của statement được rollback.

### 2.2. REPLACE dùng giá trị mới cho toàn bộ hàng

REPLACE lấy giá trị cho hàng mới từ các cột được chỉ định. Cột bị bỏ qua nhận DEFAULT như khi INSERT. Nó không tự giữ các cột cũ không có trong danh sách.

Ví dụ:

    CREATE TABLE product (
        product_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
        product_name VARCHAR(100) NOT NULL,
        price DECIMAL(12,2) NOT NULL,
        description VARCHAR(500) DEFAULT 'No description',
        updated_at TIMESTAMP NOT NULL
            DEFAULT CURRENT_TIMESTAMP
    ) ENGINE = InnoDB;

Hàng cũ:

    INSERT INTO product (
        product_id, product_name, price, description
    )
    VALUES (
        101, 'Keyboard', 49.90, 'Mechanical keyboard'
    );

REPLACE chỉ truyền ba cột:

    REPLACE INTO product (
        product_id, product_name, price
    )
    VALUES (
        101, 'Keyboard Pro', 59.90
    );

Hàng mới có description = 'No description' theo DEFAULT. Giá trị description cũ không được giữ lại.

Nếu muốn giữ cột hiện có và chỉ thay đổi một vài cột khi duplicate, INSERT ... ON DUPLICATE KEY UPDATE thường phù hợp hơn.

### 2.3. REPLACE có thể xóa nhiều hàng

Một bảng có nhiều UNIQUE index có thể khiến một hàng REPLACE xung đột với nhiều hàng cũ khác nhau.

Ví dụ:

    CREATE TABLE account_alias (
        account_id BIGINT NOT NULL PRIMARY KEY,
        email VARCHAR(200) NOT NULL,
        external_ref VARCHAR(100) NOT NULL,
        UNIQUE KEY uq_email (email),
        UNIQUE KEY uq_external_ref (external_ref)
    ) ENGINE = InnoDB;

Dữ liệu ban đầu:

    INSERT INTO account_alias
        (account_id, email, external_ref)
    VALUES
        (1, 'a@example.test', 'EXT-A'),
        (2, 'b@example.test', 'EXT-B');

Lệnh:

    REPLACE INTO account_alias
        (account_id, email, external_ref)
    VALUES
        (3, 'a@example.test', 'EXT-B');

Hàng mới xung đột email với account 1 và external_ref với account 2. Thuật toán REPLACE có thể xóa từng hàng xung đột rồi thử insert lại cho đến khi chèn được hàng mới. Vì thế cả hai hàng cũ có thể bị xóa trước khi account 3 được chèn.

Đây là rủi ro dữ liệu rất lớn nếu dùng REPLACE trên bảng có nhiều unique key đại diện cho các thực thể khác nhau. Không coi REPLACE là “update hàng có cùng business key” khi có nhiều UNIQUE index.

### 2.4. Quyền cần có cho REPLACE

Tài khoản chạy REPLACE cần cả:

- INSERT trên bảng đích.
- DELETE trên bảng đích.

Đây là hệ quả của ngữ nghĩa delete-and-insert. Một account chỉ có INSERT nhưng không có DELETE có thể chạy INSERT thường nhưng không đủ quyền cho REPLACE.

### 2.5. Số hàng bị ảnh hưởng

REPLACE trả số hàng bị ảnh hưởng bằng tổng số hàng bị xóa và số hàng được chèn:

| Kết quả | Affected rows điển hình |
|---|---:|
| Chèn mới, không xóa hàng nào | 1 |
| Xóa một hàng cũ rồi chèn một hàng mới | 2 |
| Xóa hai hàng cũ rồi chèn một hàng mới | 3 |

Không dùng con số này như một mã nghiệp vụ ổn định. Một hàng mới có thể thay thế nhiều hàng cũ do nhiều UNIQUE index; ngoài ra chi tiết implementation của storage engine có thể ảnh hưởng một số status counters nội bộ.

## 3. INSERT ... ON DUPLICATE KEY UPDATE là nhánh INSERT hoặc UPDATE

INSERT ... ON DUPLICATE KEY UPDATE thử insert hàng mới. Nếu PRIMARY KEY hoặc UNIQUE index bị trùng, MySQL cập nhật hàng cũ tương ứng.

Ví dụ:

    INSERT INTO product (
        product_id,
        product_name,
        price
    )
    VALUES (
        101,
        'Keyboard Pro',
        59.90
    ) AS incoming
    ON DUPLICATE KEY UPDATE
        product_name = incoming.product_name,
        price = incoming.price;

Nếu product_id 101 chưa tồn tại, hàng được insert. Nếu đã tồn tại, các cột được liệt kê trong UPDATE clause được cập nhật trên hàng cũ.

### 3.1. Chuỗi trigger khi upsert insert thành công

Khi không có duplicate key:

1. BEFORE INSERT chạy.
2. Hàng được insert.
3. AFTER INSERT chạy.

Không có BEFORE UPDATE hoặc AFTER UPDATE trong nhánh này.

### 3.2. Chuỗi trigger khi upsert gặp duplicate

Khi hàng đầu vào vi phạm PRIMARY KEY hoặc UNIQUE index:

1. BEFORE INSERT vẫn chạy cho hàng đầu vào.
2. MySQL xác định có duplicate key.
3. BEFORE UPDATE chạy cho hàng sẽ được cập nhật.
4. Hàng cũ được cập nhật theo UPDATE clause và các thay đổi trong BEFORE UPDATE.
5. AFTER UPDATE chạy.

Không có AFTER INSERT trong nhánh duplicate. Cũng không có BEFORE DELETE hoặc AFTER DELETE.

Sơ đồ:

    INSERT ... ON DUPLICATE KEY UPDATE
       |
       v
    BEFORE INSERT
       |
       v
    Có duplicate key?
       |
       +---- Không ----------------------+
       |                                 |
       |                                 v
       |                            Insert row
       |                                 |
       |                                 v
       |                            AFTER INSERT
       |
       +---- Có
             |
             v
        BEFORE UPDATE
             |
             v
          Update old row
             |
             v
         AFTER UPDATE

Một trigger BEFORE INSERT có thể chạy dù cuối cùng không có hàng mới nào được insert. Vì thế, không đặt logic “đã tạo hàng mới” trong BEFORE INSERT nếu câu lệnh upsert có thể đi vào nhánh UPDATE.

### 3.3. OLD và NEW trong từng trigger

Các pseudo-row có ý nghĩa theo event:

| Trigger | OLD | NEW |
|---|---|---|
| BEFORE INSERT | Không có hàng cũ | Giá trị hàng đang định insert |
| AFTER INSERT | Không có hàng cũ | Hàng vừa insert |
| BEFORE UPDATE | Hàng trước khi cập nhật | Giá trị dự kiến sau cập nhật |
| AFTER UPDATE | Hàng trước khi cập nhật | Hàng sau khi cập nhật |
| BEFORE DELETE | Hàng sắp xóa | Không có hàng mới |
| AFTER DELETE | Hàng đã xóa | Không có hàng mới |

Trong BEFORE INSERT của upsert, NEW mô tả hàng đầu vào. Nếu có duplicate, BEFORE UPDATE tiếp tục chạy với OLD là hàng đang tồn tại và NEW là giá trị dự kiến sau UPDATE. Do đó, một giá trị đã được sửa trong BEFORE INSERT có thể tham gia vào quá trình upsert; nếu cần chuẩn hóa business key, phải kiểm tra kỹ cách nó ảnh hưởng đến duplicate detection và điều kiện UPDATE.

Trong BEFORE UPDATE, có thể gán NEW.column = value để thay đổi giá trị sắp ghi. OLD chỉ đọc được. Trong AFTER trigger, hàng đã được ghi nên không thể sửa NEW bằng SET.

## 4. So sánh REPLACE và ON DUPLICATE KEY UPDATE

| Tiêu chí | REPLACE | INSERT ... ON DUPLICATE KEY UPDATE |
|---|---|---|
| Khi không duplicate | INSERT | INSERT |
| Khi duplicate | Xóa hàng xung đột rồi INSERT hàng mới | UPDATE hàng xung đột |
| Trigger nhánh duplicate | BEFORE INSERT, BEFORE/AFTER DELETE, AFTER INSERT | BEFORE INSERT, BEFORE/AFTER UPDATE |
| UPDATE trigger khi duplicate | Không | Có |
| DELETE trigger khi duplicate | Có | Không |
| Giữ cột cũ không được chỉ định | Không, nhận DEFAULT | Có, nếu không gán trong UPDATE clause |
| Quyền cơ bản | INSERT + DELETE | INSERT + UPDATE |
| Affected rows điển hình khi duplicate một hàng | 2 | 2 nếu có thay đổi; 0 nếu không thay đổi |
| Có thể xóa nhiều hàng do nhiều unique key | Có | Chỉ cập nhật một hàng; kết quả có thể mơ hồ |

Chọn câu lệnh theo ý nghĩa dữ liệu:

- Dùng REPLACE khi chủ đích thật sự là xóa hàng xung đột và tạo hàng mới theo toàn bộ giá trị được cung cấp.
- Dùng INSERT ... ON DUPLICATE KEY UPDATE khi muốn giữ thực thể hiện có và cập nhật các cột được chọn.
- Dùng INSERT IGNORE khi muốn bỏ qua hàng duplicate hoặc một số lỗi được chuyển thành warning; đây không phải upsert.

Đừng chọn REPLACE chỉ vì từ “replace” nghe giống cập nhật. Nó có thể kích hoạt delete trigger, foreign key cascade và xóa nhiều hàng.

## 5. Dùng row alias trong ON DUPLICATE KEY UPDATE

Từ MySQL 8.0.19, có thể đặt row alias sau phần VALUES để tham chiếu giá trị của hàng đầu vào:

    INSERT INTO product (
        product_id,
        product_name,
        price
    )
    VALUES (
        101,
        'Keyboard Pro',
        59.90
    ) AS incoming
    ON DUPLICATE KEY UPDATE
        product_name = incoming.product_name,
        price = incoming.price;

Có thể đặt column aliases:

    INSERT INTO product (
        product_id,
        product_name,
        price
    )
    VALUES (
        101,
        'Keyboard Pro',
        59.90
    ) AS incoming(id, name, amount)
    ON DUPLICATE KEY UPDATE
        product_name = name,
        price = amount;

Row alias phải khác tên bảng. Column alias cần không xung đột với tên alias row và phải được dùng nhất quán.

### 5.1. VALUES(column) đã deprecated

Cách cũ:

    INSERT INTO product(product_id, price)
    VALUES (101, 59.90)
    ON DUPLICATE KEY UPDATE
        price = VALUES(price);

Hàm VALUES(column) trong ON DUPLICATE KEY UPDATE đã deprecated từ MySQL 8.0.20. Dùng row alias hoặc column alias trong code mới để tránh warning và chuẩn bị cho các phiên bản tương lai.

## 6. Nhiều UNIQUE index làm upsert khó dự đoán

ON DUPLICATE KEY UPDATE không có cú pháp chỉ định rõ unique index nào là “business key” dùng để xác định hàng cần cập nhật. Nếu bảng có nhiều unique index, một hàng đầu vào có thể xung đột theo nhiều cách.

Ví dụ:

    CREATE TABLE customer_identity (
        customer_id BIGINT NOT NULL PRIMARY KEY,
        email VARCHAR(200) NOT NULL,
        external_ref VARCHAR(100) NOT NULL,
        display_name VARCHAR(100) NOT NULL,
        UNIQUE KEY uq_customer_email (email),
        UNIQUE KEY uq_customer_external (external_ref)
    ) ENGINE = InnoDB;

Nếu email trùng hàng A nhưng external_ref trùng hàng B, MySQL chỉ cập nhật một hàng phù hợp theo quy tắc duplicate-key của statement; kết quả có thể tương tự UPDATE ... WHERE email = ... OR external_ref = ... LIMIT 1. Không được coi upsert này là thao tác merge hai thực thể.

Ngoài ra, MySQL đánh dấu một số dạng INSERT ... ON DUPLICATE KEY UPDATE trên bảng có nhiều unique/primary key là không an toàn cho statement-based replication.

Khuyến nghị:

- Thiết kế một business key rõ ràng cho upsert.
- Nếu cần hợp nhất nhiều định danh, thực hiện logic xác định thực thể riêng bằng transaction và locking phù hợp.
- Không dùng nhiều unique key như một điều kiện OR ngầm để chọn hàng.
- Kiểm tra warning và replication safety khi triển khai.

## 7. REPLACE, AUTO_INCREMENT và khóa ngoại

### 7.1. AUTO_INCREMENT

REPLACE có thể tạo ra giá trị AUTO_INCREMENT mới khi hàng bị thay thế do một unique key khác, trong khi cột auto increment không được cung cấp. Nếu REPLACE xung đột trên chính primary key và gửi lại cùng giá trị id, hàng mới có thể giữ giá trị đó; nhưng không nên dựa vào khoảng trống sequence để suy ra số lần insert/delete.

Với INSERT ... ON DUPLICATE KEY UPDATE, InnoDB có thể tăng bộ đếm AUTO_INCREMENT ngay cả khi statement đi vào nhánh UPDATE do duplicate. Vì vậy, khoảng trống trong dãy ID không chứng minh có hàng đã bị xóa.

Nếu cần ID được sinh ra, hãy dùng cơ chế trả ID thích hợp và hiểu rõ LAST_INSERT_ID() theo câu lệnh, thay vì suy diễn từ số lượng affected rows.

### 7.2. ON DELETE CASCADE có thể xóa hàng con

Nếu REPLACE xóa hàng cha cũ, hành động ON DELETE CASCADE của foreign key có thể xóa hàng con liên quan. Khi hàng cha mới được insert, các hàng con đã cascade-delete không tự được tạo lại.

Ví dụ:

    CREATE TABLE customer (
        customer_id BIGINT NOT NULL PRIMARY KEY,
        email VARCHAR(200) NOT NULL UNIQUE
    ) ENGINE = InnoDB;

    CREATE TABLE customer_order (
        order_id BIGINT NOT NULL PRIMARY KEY,
        customer_id BIGINT NOT NULL,
        FOREIGN KEY (customer_id)
            REFERENCES customer(customer_id)
            ON DELETE CASCADE
    ) ENGINE = InnoDB;

Nếu REPLACE một customer trùng email nhưng dùng customer_id mới, MySQL xóa customer cũ. Các order của customer cũ có thể bị xóa do ON DELETE CASCADE, sau đó customer mới được insert. Đây là lý do REPLACE có thể gây mất dữ liệu liên quan dù câu lệnh trông giống một thao tác ghi lại customer.

### 7.3. Foreign key cascade không kích hoạt trigger

MySQL không kích hoạt trigger cho các thao tác được thực hiện bởi hành động foreign key cascade. Nếu ON DELETE CASCADE xóa hàng trong customer_order, trigger DELETE trên customer_order không chạy cho các hàng bị cascade xóa.

Vì vậy, nếu hệ thống cần audit mọi thay đổi hàng con, không thể chỉ dựa vào DELETE trigger của bảng con khi có foreign key cascade. Hãy thiết kế audit ở cấp nghiệp vụ hoặc ghi nhận thao tác cha theo cách phù hợp.

## 8. Xây dựng chuỗi trigger thực tế qua nhiều bảng

Một trigger có thể ghi vào bảng khác. Nếu thao tác đó làm thay đổi bảng có trigger, trigger ở bảng đích cũng có thể được kích hoạt. Chuỗi này giúp tách audit và tổng hợp, nhưng cũng khiến một câu SQL ban đầu tạo ra nhiều thao tác hơn dự kiến.

Ta xây dựng ví dụ:

- inventory: bảng tồn kho.
- inventory_audit: lịch sử insert/update/delete.
- daily_inventory_activity: bộ đếm hoạt động theo ngày.

Luồng:

    INSERT / UPDATE / REPLACE / UPSERT
                    |
                    v
              inventory trigger
                    |
                    v
             INSERT audit row
                    |
                    v
          inventory_audit trigger
                    |
                    v
       UPDATE daily activity counter

### 8.1. Tạo các bảng

    CREATE TABLE daily_inventory_activity (
        activity_date DATE NOT NULL PRIMARY KEY,
        insert_count BIGINT NOT NULL DEFAULT 0,
        update_count BIGINT NOT NULL DEFAULT 0,
        delete_count BIGINT NOT NULL DEFAULT 0
    ) ENGINE = InnoDB;

    CREATE TABLE inventory (
        product_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
        sku VARCHAR(40) NOT NULL,
        quantity INT NOT NULL,
        updated_at TIMESTAMP NOT NULL
            DEFAULT CURRENT_TIMESTAMP
            ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_inventory_sku (sku)
    ) ENGINE = InnoDB;

    CREATE TABLE inventory_audit (
        audit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        product_id BIGINT UNSIGNED NOT NULL,
        event_type VARCHAR(10) NOT NULL,
        old_quantity INT NULL,
        new_quantity INT NULL,
        event_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_audit_event_time (event_time)
    ) ENGINE = InnoDB;

### 8.2. Trigger ghi audit khi insert

    CREATE TRIGGER inventory_after_insert
    AFTER INSERT ON inventory
    FOR EACH ROW
    INSERT INTO inventory_audit (
        product_id,
        event_type,
        old_quantity,
        new_quantity
    )
    VALUES (
        NEW.product_id,
        'INSERT',
        NULL,
        NEW.quantity
    );

### 8.3. Trigger ghi audit khi update

    CREATE TRIGGER inventory_after_update
    AFTER UPDATE ON inventory
    FOR EACH ROW
    INSERT INTO inventory_audit (
        product_id,
        event_type,
        old_quantity,
        new_quantity
    )
    VALUES (
        NEW.product_id,
        'UPDATE',
        OLD.quantity,
        NEW.quantity
    );

### 8.4. Trigger ghi audit khi delete

    CREATE TRIGGER inventory_after_delete
    AFTER DELETE ON inventory
    FOR EACH ROW
    INSERT INTO inventory_audit (
        product_id,
        event_type,
        old_quantity,
        new_quantity
    )
    VALUES (
        OLD.product_id,
        'DELETE',
        OLD.quantity,
        NULL
    );

### 8.5. Trigger tổng hợp khi audit row được insert

    CREATE TRIGGER inventory_audit_after_insert
    AFTER INSERT ON inventory_audit
    FOR EACH ROW
    BEGIN
        INSERT INTO daily_inventory_activity (
            activity_date,
            insert_count,
            update_count,
            delete_count
        )
        VALUES (
            DATE(NEW.event_time),
            NEW.event_type = 'INSERT',
            NEW.event_type = 'UPDATE',
            NEW.event_type = 'DELETE'
        )
        AS incoming
        ON DUPLICATE KEY UPDATE
            insert_count =
                insert_count + incoming.insert_count,
            update_count =
                update_count + incoming.update_count,
            delete_count =
                delete_count + incoming.delete_count;
    END;

Trigger cuối dùng upsert để tạo dòng tổng hợp theo ngày hoặc tăng bộ đếm nếu ngày đã tồn tại. Đây là chuỗi trigger lồng qua các bảng khác nhau. Nó không phải vòng lặp tự gọi lại chính trigger inventory.

### 8.6. Thứ tự khi INSERT thường

Chạy:

    INSERT INTO inventory (
        product_id, sku, quantity
    )
    VALUES (
        501, 'SKU-501', 20
    );

Chuỗi:

1. BEFORE INSERT trên inventory nếu có.
2. Insert hàng inventory.
3. AFTER INSERT trên inventory.
4. Trigger inventory_after_insert insert một hàng vào inventory_audit.
5. AFTER INSERT trên inventory_audit chạy.
6. Trigger inventory_audit_after_insert upsert daily_inventory_activity.
7. Nếu daily_inventory_activity có trigger phù hợp, trigger đó cũng có thể chạy tiếp.

Một câu INSERT vào inventory do đó có thể tạo nhiều thao tác trên các bảng khác.

### 8.7. Thứ tự khi UPSERT gặp duplicate

Giả sử inventory đã có product_id 501. Chạy:

    INSERT INTO inventory (
        product_id, sku, quantity
    )
    VALUES (
        501, 'SKU-501', 25
    ) AS incoming
    ON DUPLICATE KEY UPDATE
        quantity = incoming.quantity;

Chuỗi:

1. BEFORE INSERT trên inventory.
2. MySQL phát hiện duplicate product_id.
3. BEFORE UPDATE trên inventory.
4. Hàng inventory được cập nhật.
5. AFTER UPDATE trên inventory.
6. Trigger AFTER UPDATE insert audit row với event_type UPDATE.
7. AFTER INSERT trên inventory_audit chạy.
8. Bộ đếm update_count được tăng.

Không có DELETE trigger và không có AFTER INSERT của inventory trong nhánh duplicate.

### 8.8. Thứ tự khi REPLACE gặp duplicate

Giả sử inventory đã có product_id 501. Chạy:

    REPLACE INTO inventory (
        product_id, sku, quantity
    )
    VALUES (
        501, 'SKU-501', 30
    );

Chuỗi logic:

1. BEFORE INSERT trên inventory.
2. MySQL phát hiện duplicate product_id.
3. BEFORE DELETE trên inventory.
4. Hàng cũ bị xóa.
5. AFTER DELETE trên inventory.
6. Trigger AFTER DELETE insert audit row event_type DELETE.
7. AFTER INSERT trên inventory_audit cập nhật delete_count.
8. MySQL chèn hàng inventory mới.
9. AFTER INSERT trên inventory.
10. Trigger AFTER INSERT insert audit row event_type INSERT.
11. AFTER INSERT trên inventory_audit cập nhật insert_count.

Trong bảng audit, một lần REPLACE có thể tạo hai bản ghi: DELETE hàng cũ và INSERT hàng mới. Bộ đếm delete_count và insert_count đều tăng.

### 8.9. Vì sao phải quan sát cả chuỗi?

Nếu dashboard chỉ đếm AFTER INSERT trên inventory, một REPLACE có thể làm số insert tăng nhưng không phản ánh việc hàng cũ đã bị xóa. Nếu chỉ đếm UPDATE, upsert duplicate không được ghi nhận là update nếu code chỉ theo dõi insert trigger. Cần thiết kế audit theo event thực tế, không theo tên câu SQL mà ứng dụng gọi.

## 9. Trigger BEFORE có thể thay đổi hàng đầu vào

Trong BEFORE INSERT và BEFORE UPDATE, có thể gán giá trị cho NEW column:

    CREATE TRIGGER inventory_before_insert
    BEFORE INSERT ON inventory
    FOR EACH ROW
    SET NEW.sku = UPPER(TRIM(NEW.sku));

Với upsert, BEFORE INSERT chạy cho mỗi hàng đầu vào, kể cả khi sau đó chuyển sang nhánh UPDATE. BEFORE UPDATE cũng có thể chuẩn hóa giá trị của hàng cũ khi duplicate branch được chọn.

Không đặt cùng một phép chuẩn hóa ở nhiều trigger mà không có thứ tự rõ ràng. Nếu nhiều BEFORE INSERT trigger cùng sửa NEW.sku, kết quả phụ thuộc thứ tự trigger.

Lưu ý:

- OLD là read-only.
- Trong BEFORE trigger, NEW có thể được thay đổi nếu có quyền UPDATE phù hợp.
- AFTER trigger không thể thay đổi hàng đã được ghi bằng SET NEW.
- NEW của AUTO_INCREMENT column trong BEFORE INSERT là 0, chưa phải số sequence cuối cùng được cấp.
- Trigger không thể tham chiếu generated column bằng OLD/NEW theo cách thông thường.

## 10. Nhiều trigger cùng event và timing

MySQL 8.4 cho phép nhiều trigger trên cùng bảng có cùng event và timing, ví dụ hai BEFORE UPDATE trigger.

Mặc định, các trigger cùng event và timing chạy theo thứ tự tạo. Có thể điều khiển bằng:

- FOLLOWS other_trigger_name: trigger mới chạy sau trigger được chỉ định.
- PRECEDES other_trigger_name: trigger mới chạy trước trigger được chỉ định.

Ví dụ:

    CREATE TRIGGER inventory_before_insert_validate
    BEFORE INSERT ON inventory
    FOR EACH ROW
    SET NEW.quantity = GREATEST(NEW.quantity, 0);

    CREATE TRIGGER inventory_before_insert_normalize
    BEFORE INSERT ON inventory
    FOR EACH ROW FOLLOWS inventory_before_insert_validate
    SET NEW.sku = UPPER(TRIM(NEW.sku));

FOLLOWS và PRECEDES chỉ sắp xếp các trigger có cùng event và timing trên cùng bảng. Chúng không tạo thứ tự tổng quát giữa BEFORE INSERT và AFTER INSERT hoặc giữa trigger trên hai bảng khác nhau.

Khi thêm trigger mới vào hệ thống đã có nhiều trigger, hãy kiểm tra thứ tự thực tế và kiểm thử tất cả nhánh REPLACE/upsert.

## 11. Multi-row INSERT/REPLACE/UPSERT chạy theo từng hàng

Ví dụ:

    INSERT INTO inventory (
        product_id, sku, quantity
    )
    VALUES
        (501, 'SKU-501', 10),
        (502, 'SKU-502', 20),
        (503, 'SKU-503', 30)
    AS incoming
    ON DUPLICATE KEY UPDATE
        quantity = incoming.quantity;

Mỗi hàng đầu vào được xử lý theo nhánh của riêng nó:

- Hàng 501 có thể insert.
- Hàng 502 có thể duplicate và update.
- Hàng 503 có thể insert.

Do đó, cùng một statement có thể kích hoạt cả chuỗi INSERT và chuỗi UPDATE. Với REPLACE nhiều hàng, mỗi hàng có thể không duplicate, duplicate một hàng hoặc xung đột nhiều hàng. Tổng số lần trigger chạy phụ thuộc các hàng thực sự bị tác động, không phải chỉ số câu lệnh SQL.

Khi trigger ghi audit, hãy thiết kế bảng audit để lưu từng row event. Không giả định một câu lệnh nhiều hàng tạo đúng một audit record.

## 12. Trigger lỗi và tính nguyên tử của statement

MySQL xử lý lỗi trigger theo các nguyên tắc:

- Nếu BEFORE trigger lỗi, thao tác trên hàng tương ứng không được thực hiện.
- AFTER trigger chỉ chạy khi BEFORE trigger và thao tác hàng thành công.
- Lỗi trong BEFORE hoặc AFTER trigger làm statement gọi trigger thất bại.
- Với bảng transactional như InnoDB, lỗi statement làm rollback các thay đổi của statement, bao gồm thay đổi transactional do trigger thực hiện.
- Với bảng nontransactional, không thể rollback các thay đổi đã xảy ra trước điểm lỗi.

Ví dụ, AFTER INSERT trên inventory insert audit row rồi trigger audit cập nhật summary. Nếu trigger summary lỗi và tất cả bảng đều là InnoDB, toàn bộ statement ban đầu thất bại và thay đổi liên quan trong transaction của statement được rollback.

Không trộn bảng InnoDB với MyISAM trong chuỗi trigger nếu yêu cầu atomicity. Nếu một trigger đã ghi vào bảng nontransactional rồi statement sau đó lỗi, thay đổi nontransactional có thể vẫn còn.

### 12.1. Trigger không tự quản lý transaction

Trigger không được chạy các câu lệnh bắt đầu hoặc kết thúc transaction như:

- START TRANSACTION
- COMMIT
- ROLLBACK

Trigger chạy như một phần của statement kích hoạt nó. Không tạo transaction độc lập bên trong trigger.

ROLLBACK TO SAVEPOINT có quy tắc riêng và được phép trong một số ngữ cảnh, nhưng không biến trigger thành chủ sở hữu transaction độc lập.

### 12.2. Không sửa bảng đang được statement gọi trigger sử dụng

Stored function hoặc trigger không được sửa một bảng đang được statement gọi trigger sử dụng để đọc hoặc ghi. Ví dụ trigger trên inventory không thể thực hiện một UPDATE khác lên chính inventory trong khi statement gốc đang sửa inventory.

Thiết kế trigger chain qua các bảng riêng như inventory → inventory_audit → daily_inventory_activity sẽ dễ kiểm soát hơn. Tránh tạo vòng lặp A → B → A hoặc phụ thuộc lẫn nhau giữa nhiều trigger.

## 13. Trigger chain có thể phát sinh từ thao tác trên bảng khác

Trigger không chỉ chạy cho bảng ban đầu. Nếu trigger A thực hiện DML trên bảng B và B có trigger phù hợp, thao tác trên B có thể kích hoạt trigger của B.

Ví dụ:

    CREATE TRIGGER order_after_insert
    AFTER INSERT ON orders
    FOR EACH ROW
    INSERT INTO order_audit(order_id, event_type)
    VALUES (NEW.order_id, 'INSERT');

    CREATE TRIGGER order_audit_after_insert
    AFTER INSERT ON order_audit
    FOR EACH ROW
    UPDATE daily_order_count
    SET total_count = total_count + 1
    WHERE activity_date = CURRENT_DATE();

Chuỗi thực tế:

    INSERT orders
      -> AFTER INSERT orders
        -> INSERT order_audit
          -> AFTER INSERT order_audit
            -> UPDATE daily_order_count

Mỗi bước có thể thêm lock, I/O, trigger execution và khả năng lỗi. Hãy lập sơ đồ phụ thuộc để người vận hành biết một lệnh INSERT đơn giản có thể chạm những bảng nào.

Không để trigger chain phụ thuộc vào thứ tự ngẫu nhiên. Nếu cần thứ tự giữa nhiều trigger trên cùng event/timing, dùng FOLLOWS/PRECEDES và ghi lại trong migration.

## 14. Những thao tác không kích hoạt trigger như nhiều người nghĩ

| Thao tác | Trigger liên quan |
|---|---|
| INSERT | INSERT trigger |
| LOAD DATA | INSERT trigger cho hàng được nạp |
| REPLACE | INSERT và DELETE trigger theo nhánh thực tế |
| INSERT ... ON DUPLICATE KEY UPDATE | BEFORE INSERT, rồi INSERT hoặc UPDATE trigger |
| UPDATE | UPDATE trigger |
| DELETE | DELETE trigger |
| TRUNCATE TABLE | Không kích hoạt DELETE trigger |
| DROP TABLE | Không kích hoạt DELETE trigger |
| Drop partition | Không kích hoạt DELETE trigger cho từng hàng |
| Foreign key cascade | Không kích hoạt trigger trên bảng con do cascade |
| Thay đổi dữ liệu qua API không gửi SQL tới MySQL | Không kích hoạt SQL trigger |

Nếu hệ thống dùng TRUNCATE để dọn dữ liệu, không thể dựa vào DELETE trigger để audit từng hàng bị xóa. Nếu cần audit, hãy thiết kế quy trình riêng trước khi truncate.

## 15. Trigger và replication

Hành vi trigger trên replica phụ thuộc replication format:

- Statement-based replication: statement được thực thi trên replica; trigger tương ứng trên replica cũng có thể chạy.
- Row-based replication: trigger trên source đã tạo ra các thay đổi hàng; các row changes này được ghi và áp dụng trên replica, nên trigger trên replica không chạy lại cho các thay đổi do statement source gây ra.
- Mixed mode: MySQL chọn cách ghi log phù hợp theo statement và quy tắc an toàn.

Không giả định audit trigger sẽ chạy hai lần trên replica. Ngược lại, cũng không tạo cấu hình trigger khác nhau giữa source và replica khi dùng row-based replication nếu kết quả dữ liệu cần nhất quán.

Một số câu lệnh REPLACE ... SELECT và INSERT ... SELECT ... ON DUPLICATE KEY UPDATE có thể bị đánh dấu unsafe cho statement-based replication vì kết quả phụ thuộc thứ tự hàng hoặc điều kiện unique key. Kiểm tra warning, binlog format và kế hoạch replication trước khi dùng các dạng này trong workload quan trọng.

## 16. Quyền và security context của trigger

Trigger có DEFINER. Khi trigger chạy, quyền được kiểm tra theo security context của DEFINER, không phải chỉ theo tài khoản ứng dụng đã phát INSERT/UPDATE/DELETE.

Các quyền cần xem xét:

- TRIGGER trên bảng được gắn trigger để tạo trigger.
- SELECT nếu body đọc OLD/NEW hoặc bảng cần đọc.
- UPDATE nếu gán SET NEW.column = value.
- Quyền DML cần thiết trên các bảng audit, summary hoặc bảng khác mà trigger truy cập.

Không dùng root làm DEFINER chỉ để trigger có thể ghi vào mọi bảng. Tạo account chuyên dụng có quyền tối thiểu. Tài khoản ứng dụng có thể chỉ cần quyền DML trên bảng nghiệp vụ; trigger thực hiện thao tác audit theo quyền DEFINER.

Kiểm tra DEFINER bằng:

    SHOW CREATE TRIGGER inventory_after_insert;

    SELECT
        TRIGGER_NAME,
        EVENT_MANIPULATION,
        EVENT_OBJECT_TABLE,
        ACTION_TIMING,
        DEFINER,
        ACTION_ORDER,
        SQL_MODE
    FROM information_schema.TRIGGERS
    WHERE TRIGGER_SCHEMA = DATABASE()
    ORDER BY EVENT_OBJECT_TABLE,
             EVENT_MANIPULATION,
             ACTION_TIMING,
             ACTION_ORDER;

## 17. Giới hạn trong trigger body

Trigger chạy đồng bộ trong statement gọi nó. Các giới hạn quan trọng:

- Trigger không trả result set cho client.
- Trigger không dùng dynamic SQL như PREPARE/EXECUTE.
- Trigger không gọi procedure trả result set cho client hoặc dùng dynamic SQL.
- Trigger không START TRANSACTION, COMMIT hoặc ROLLBACK.
- Trigger không được sửa bảng đang được statement gọi trigger sử dụng.
- Trigger không có RETURN để trả giá trị; dùng LEAVE để thoát block được gắn label khi cần.
- Trigger gắn với bảng thường, không gắn trực tiếp vào view hoặc TEMPORARY table.

Vì trigger chạy đồng bộ, tránh gọi logic dài, truy cập dịch vụ ngoài hoặc xử lý nặng. Hãy giữ body ngắn và có chi phí dự đoán được.

## 18. Khi nào chọn REPLACE, khi nào chọn upsert?

| Nhu cầu | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Tạo hàng nếu chưa có, nếu có thì cập nhật vài cột | INSERT ... ON DUPLICATE KEY UPDATE | Giữ hàng hiện có và chỉ sửa cột chỉ định |
| Thay toàn bộ hàng theo payload mới, chấp nhận delete/insert semantics | REPLACE | Hàng cũ bị xóa, hàng mới được tạo |
| Chỉ bỏ qua duplicate | INSERT IGNORE | Không update và không delete hàng cũ |
| Hợp nhất theo nhiều business key | Transaction và logic tường minh | Tránh lựa chọn hàng mơ hồ từ nhiều UNIQUE index |
| Cần audit chính xác insert/update/delete | Upsert có trigger và audit được thiết kế theo từng event | Mỗi nhánh có event trigger riêng |

Trước khi dùng REPLACE, hãy trả lời:

- Có foreign key tham chiếu hàng bị thay thế không?
- Có DELETE trigger ghi audit hoặc xóa dữ liệu liên quan không?
- Có nhiều UNIQUE index có thể khớp nhiều hàng khác nhau không?
- Các cột bỏ qua có bị reset về DEFAULT không?
- Có cần giữ created_at, owner_id, version hoặc trạng thái hiện tại không?
- Affected rows và AUTO_INCREMENT có được ứng dụng hiểu đúng không?

Trước khi dùng upsert, hãy trả lời:

- Duplicate key nào xác định hàng được update?
- Bảng có nhiều UNIQUE index không?
- BEFORE INSERT có chạy logic phụ dù cuối cùng update không?
- BEFORE/AFTER UPDATE có ghi audit đúng không?
- UPDATE clause có vô tình ghi đè cột mà caller không định thay đổi không?
- VALUES() đã được thay bằng row alias trong code mới chưa?

## 19. Quy trình kiểm thử chuỗi trigger

Không chỉ kiểm tra kết quả cuối của bảng chính. Hãy kiểm tra cả bảng audit, summary, foreign key và affected rows.

### 19.1. Chuẩn bị dữ liệu nền

    DELETE FROM inventory;
    DELETE FROM inventory_audit;
    DELETE FROM daily_inventory_activity;

    INSERT INTO inventory(product_id, sku, quantity)
    VALUES (501, 'SKU-501', 10);

Kiểm tra audit có một sự kiện INSERT.

### 19.2. Kiểm thử INSERT mới

    INSERT INTO inventory(product_id, sku, quantity)
    VALUES (502, 'SKU-502', 15);

Kỳ vọng:

- inventory có hàng 502.
- audit có một sự kiện INSERT cho 502.
- summary tăng insert_count.
- Không có UPDATE hoặc DELETE audit cho 502.

### 19.3. Kiểm thử UPSERT duplicate

    INSERT INTO inventory(product_id, sku, quantity)
    VALUES (501, 'SKU-501', 18) AS incoming
    ON DUPLICATE KEY UPDATE
        quantity = incoming.quantity;

Kỳ vọng:

- Hàng 501 vẫn là cùng thực thể theo product_id.
- quantity đổi thành 18.
- audit có sự kiện UPDATE.
- summary tăng update_count.
- Không có DELETE audit cho 501.
- BEFORE INSERT và BEFORE UPDATE có thể đều đã chạy.

### 19.4. Kiểm thử REPLACE duplicate

    REPLACE INTO inventory(product_id, sku, quantity)
    VALUES (501, 'SKU-501', 25);

Kỳ vọng:

- Hàng cũ 501 bị xóa theo ngữ nghĩa REPLACE.
- Hàng mới 501 được insert.
- audit có DELETE và INSERT.
- summary tăng delete_count và insert_count.
- UPDATE trigger không chạy cho nhánh duplicate REPLACE.

### 19.5. Kiểm thử duplicate qua UNIQUE phụ

Tạo hàng có product_id khác nhưng SKU đã tồn tại. Thử REPLACE và xác nhận đúng hàng xung đột bị xóa. Nếu có nhiều unique index, tạo dữ liệu khiến hai index xung đột với hai hàng khác nhau để kiểm tra nguy cơ nhiều hàng bị xóa.

### 19.6. Kiểm thử lỗi trigger

Tạm thời thêm một trigger cố ý phát SIGNAL khi quantity âm. Kiểm tra:

- BEFORE trigger lỗi thì hàng không được ghi.
- AFTER trigger lỗi làm statement thất bại.
- Với InnoDB, audit và summary do statement đó tạo cũng được rollback.
- Ứng dụng nhận lỗi và không đánh dấu request thành công.

Không kiểm thử bằng cách sửa trigger production. Dùng schema thử nghiệm hoặc database sandbox.

## 20. Các sai lầm thường gặp

- Nghĩ REPLACE tương đương UPDATE.
- Nghĩ duplicate branch của REPLACE chạy UPDATE trigger.
- Nghĩ duplicate branch của upsert chạy DELETE trigger.
- Nghĩ BEFORE INSERT không chạy khi upsert chuyển sang UPDATE.
- Chỉ audit AFTER INSERT nên bỏ sót update branch của upsert.
- Chỉ audit UPDATE nên bỏ sót delete/insert của REPLACE.
- Nghĩ REPLACE giữ các cột cũ không được truyền vào.
- Không nhận ra REPLACE có thể xóa nhiều hàng do nhiều UNIQUE index.
- Không cấp DELETE privilege cho account dùng REPLACE.
- Bỏ qua ON DELETE CASCADE khi REPLACE hàng cha.
- Mong trigger bảng con chạy khi foreign key cascade xóa hàng.
- Dùng affected rows để suy ra chính xác một loại nghiệp vụ mà không xét nhánh.
- Dùng VALUES(column) trong code mới dù đã deprecated.
- Upsert trên bảng nhiều UNIQUE index mà không xác định rõ hàng đích.
- Quên trigger chạy FOR EACH ROW cho từng hàng trong statement nhiều hàng.
- Không kiểm soát FOLLOWS/PRECEDES khi có nhiều trigger cùng event/timing.
- Tạo vòng lặp trigger giữa các bảng hoặc sửa lại bảng đang được statement sử dụng.
- Ghi audit vào bảng nontransactional rồi giả định rollback sẽ xóa audit.
- Dựa vào DELETE trigger để audit TRUNCATE hoặc foreign key cascade.
- Không kiểm tra khác biệt statement-based và row-based replication.

## 21. Checklist trước khi đưa REPLACE/upsert vào production

- Đã xác định chính xác câu lệnh cần insert, update hay delete-and-insert.
- Đã kiểm tra toàn bộ PRIMARY KEY và UNIQUE index.
- Đã đánh giá trường hợp nhiều unique key trùng với nhiều hàng khác nhau.
- Đã kiểm tra trigger INSERT, UPDATE và DELETE trên bảng đích.
- Đã mô tả chuỗi BEFORE/AFTER cho cả nhánh insert và duplicate.
- Đã kiểm tra trigger ghi sang bảng khác và trigger chain tiếp theo.
- Đã kiểm tra thứ tự nhiều trigger cùng event/timing.
- Đã đánh giá cột không truyền vào REPLACE sẽ nhận DEFAULT.
- Đã kiểm tra AUTO_INCREMENT và LAST_INSERT_ID().
- Đã kiểm tra foreign key cascade và tác động đến hàng con.
- Đã biết trigger bảng con không chạy cho foreign key cascade.
- Đã xác nhận tất cả bảng trong chuỗi cần atomicity đều là transactional.
- Đã kiểm tra DEFINER và grants của trigger.
- Đã thay VALUES(column) bằng row alias trong code mới.
- Đã kiểm tra affected rows, warnings và replication format.
- Đã kiểm thử insert mới, duplicate update, replace duplicate và lỗi trigger.
- Đã kiểm tra bảng chính, audit và summary sau từng test.
- Đã đo chi phí của trigger chain trên workload nhiều hàng.

## 22. Tài liệu tham khảo

- MySQL 8.4 Reference Manual — REPLACE Statement: https://dev.mysql.com/doc/refman/8.4/en/replace.html
- MySQL 8.4 Reference Manual — INSERT ... ON DUPLICATE KEY UPDATE: https://dev.mysql.com/doc/refman/8.4/en/insert-on-duplicate.html
- MySQL 8.4 Reference Manual — CREATE TRIGGER Statement: https://dev.mysql.com/doc/refman/8.4/en/create-trigger.html
- MySQL 8.4 Reference Manual — Trigger Syntax and Examples: https://dev.mysql.com/doc/refman/8.4/en/trigger-syntax.html
- MySQL 8.4 Reference Manual — Restrictions on Stored Programs: https://dev.mysql.com/doc/refman/8.4/en/stored-program-restrictions.html
- MySQL 8.4 Reference Manual — Replication and Triggers: https://dev.mysql.com/doc/refman/8.4/en/replication-features-triggers.html

REPLACE xử lý duplicate bằng cách xóa hàng xung đột rồi chèn hàng mới, vì vậy có thể kích hoạt BEFORE INSERT, DELETE triggers cho hàng cũ và AFTER INSERT. INSERT ... ON DUPLICATE KEY UPDATE luôn chạy BEFORE INSERT, sau đó hoặc AFTER INSERT, hoặc BEFORE UPDATE và AFTER UPDATE. Trigger ghi sang bảng khác có thể tạo thêm một chuỗi trigger tiếp theo; foreign key cascade lại không kích hoạt trigger bảng con. Muốn audit và tổng hợp chính xác, hãy thiết kế theo event thực tế trên từng hàng, kiểm tra tất cả UNIQUE index, thứ tự trigger, transaction engine và replication format. Chỉ dùng REPLACE khi thật sự muốn delete-and-insert; nếu cần giữ thực thể và cập nhật có chọn lọc, upsert thường diễn đạt đúng ý định hơn.
