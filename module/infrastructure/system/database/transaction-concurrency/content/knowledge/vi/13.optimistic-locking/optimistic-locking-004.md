# Tăng phiên bản và cập nhật dữ liệu trong cùng thao tác nguyên tử

Khóa lạc quan (Optimistic Locking) cho phép nhiều giao dịch đọc cùng một dữ liệu mà không phải khóa trước hàng đó. Khi một giao dịch muốn ghi, nó kiểm tra dữ liệu vẫn ở phiên bản mà nó đã đọc hay không. Cách phổ biến là thêm một cột version vào bảng và thực hiện kiểm tra phiên bản cùng lúc với UPDATE.

Mẫu cốt lõi có dạng:

~~~sql
UPDATE product
SET price = 120.00,
    version = version + 1
WHERE id = 501
  AND version = 7;
~~~

Câu lệnh chỉ cập nhật hàng có id = 501 nếu phiên bản hiện tại vẫn bằng 7. Nếu cập nhật thành công, version được tăng lên 8 trong chính câu lệnh đó. Nếu một giao dịch khác đã cập nhật hàng và tăng version trước, điều kiện version = 7 không còn đúng; câu lệnh không cập nhật hàng nào.

Điểm quyết định là kiểm tra và tăng version phải nằm trong cùng một thao tác nguyên tử. Nếu ứng dụng SELECT version, so sánh ở bộ nhớ rồi chạy một UPDATE không có điều kiện version, hai giao dịch vẫn có thể cùng vượt qua bước kiểm tra và ghi đè dữ liệu của nhau.

## 1. Vì sao cần version?

### 1.1. Tình huống mất cập nhật

Giả sử bảng product lưu giá sản phẩm:

~~~sql
CREATE TABLE product (
    id BIGINT PRIMARY KEY,
    price DECIMAL(12, 2) NOT NULL
);

INSERT INTO product (id, price)
VALUES (501, 100.00);
~~~

Hai người dùng cùng mở màn hình chỉnh sửa sản phẩm. Cả hai đều đọc giá 100.00.

- Người dùng A đổi giá thành 120.00.
- Người dùng B đổi giá thành 110.00.
- A lưu trước.
- B lưu sau.

Nếu ứng dụng chỉ chạy UPDATE theo id, kết quả cuối cùng có thể là 110.00. Thay đổi 120.00 của A đã bị ghi đè mà B không biết dữ liệu đã thay đổi kể từ khi B mở màn hình.

~~~sql
-- A
UPDATE product
SET price = 120.00
WHERE id = 501;

-- B
UPDATE product
SET price = 110.00
WHERE id = 501;
~~~

Đây là lost update ở tầng nghiệp vụ. Cả hai câu UPDATE đều hợp lệ về mặt cú pháp, nhưng thao tác lưu của B dựa trên một bản dữ liệu cũ.

### 1.2. Gắn số phiên bản với hàng

Có thể thêm cột version:

~~~sql
ALTER TABLE product
ADD COLUMN version BIGINT NOT NULL DEFAULT 0;
~~~

Mỗi lần cập nhật thành công, version tăng lên một đơn vị. Ứng dụng đọc cả dữ liệu và version:

~~~sql
SELECT id, price, version
FROM product
WHERE id = 501;
~~~

Giả sử A và B đều đọc:

| id | price | version |
|---:|---:|---:|
| 501 | 100.00 | 7 |

Cả hai giữ version = 7 trong trạng thái chỉnh sửa của mình. Khi A lưu, câu lệnh kiểm tra version và tăng nó:

~~~sql
UPDATE product
SET price = 120.00,
    version = version + 1
WHERE id = 501
  AND version = 7;
~~~

Một hàng được cập nhật; version trở thành 8.

Khi B lưu với version cũ:

~~~sql
UPDATE product
SET price = 110.00,
    version = version + 1
WHERE id = 501
  AND version = 7;
~~~

Không có hàng nào được cập nhật vì version hiện tại đã là 8. Ứng dụng nhận biết dữ liệu đã thay đổi và có thể yêu cầu tải lại, hợp nhất hoặc báo xung đột cho người dùng.

### 1.3. Version là dấu mốc của trạng thái đã đọc

Version không nhất thiết mô tả số lần người dùng chỉnh sửa. Nó là dấu mốc để xác định một hàng đã thay đổi kể từ lần đọc mà thao tác ghi dựa vào hay chưa.

Một hàng có thể có:

~~~text
id = 501
price = 120.00
version = 8
~~~

Nếu một lần cập nhật khác thay đổi description nhưng không tăng version, một giao dịch đang giữ bản description cũ có thể ghi đè thay đổi đó mà không phát hiện. Vì vậy, version phải được tăng khi bất kỳ thay đổi nào thuộc phạm vi cần bảo vệ xảy ra.

Nếu nhiều bảng cùng tạo thành một đối tượng nghiệp vụ, version của một hàng riêng lẻ có thể chưa đủ. Phần sau sẽ giải thích giới hạn này.

## 2. Kiểm tra và tăng version trong cùng câu UPDATE

### 2.1. Mẫu compare-and-swap

Mẫu chuẩn là:

~~~sql
UPDATE table_name
SET column_a = :new_value,
    version = version + 1
WHERE id = :id
  AND version = :expected_version;
~~~

Ba việc xảy ra trong một câu lệnh:

1. Hệ quản trị tìm hàng có đúng định danh.
2. Điều kiện version phải khớp với phiên bản mà ứng dụng đã đọc.
3. Nếu điều kiện còn đúng, hệ quản trị cập nhật dữ liệu và tăng version.

Đây là một dạng compare-and-swap (CAS): chỉ ghi giá trị mới nếu trạng thái hiện tại vẫn bằng trạng thái mong đợi. Trong ví dụ này, giá trị được so sánh là version.

Việc kiểm tra điều kiện và thay đổi hàng được thực hiện nguyên tử theo cơ chế giao dịch của hệ quản trị. Ứng dụng không có khoảng thời gian giữa bước đọc version hiện tại và bước ghi mà giao dịch khác có thể chen vào để làm điều kiện trở nên lỗi thời mà không bị phát hiện.

### 2.2. Vì sao phải tăng version ngay trong UPDATE?

Một cách làm sai thường gặp:

~~~sql
SELECT version
FROM product
WHERE id = 501;

-- Ứng dụng kiểm tra version = 7.

UPDATE product
SET price = 120.00
WHERE id = 501;

UPDATE product
SET version = version + 1
WHERE id = 501;
~~~

Có hai câu UPDATE riêng biệt và câu ghi giá không có điều kiện version. Một giao dịch khác có thể cập nhật giữa các bước hoặc trước khi câu ghi giá chạy. Việc tăng version sau đó không chứng minh rằng dữ liệu đã được ghi dựa trên phiên bản đúng.

Một biến thể khác cũng sai:

~~~sql
SELECT version
FROM product
WHERE id = 501;

-- So sánh ở ứng dụng.

IF version = expected_version THEN
    UPDATE product SET price = new_price WHERE id = 501;
END IF;
~~~

Ngay cả khi kiểm tra version đúng tại thời điểm SELECT, giao dịch khác vẫn có thể thay đổi hàng trước khi UPDATE. Đây là khoảng race condition giữa kiểm tra và ghi.

Hãy đưa điều kiện version vào chính WHERE của câu UPDATE làm thay đổi dữ liệu.

### 2.3. Cập nhật nhiều cột

Mọi cột cần thay đổi nên được cập nhật cùng version:

~~~sql
UPDATE product
SET name = :name,
    price = :price,
    description = :description,
    version = version + 1
WHERE id = :id
  AND version = :expected_version;
~~~

Nếu một giao dịch thay đổi price và giao dịch khác thay đổi description, cả hai vẫn cạnh tranh trên cùng version. Giao dịch đến sau sẽ phát hiện phiên bản đã đổi và phải xử lý xung đột.

Đây là cách bảo vệ toàn bộ hàng. Nếu nghiệp vụ cho phép cập nhật độc lập từng nhóm thuộc tính, có thể thiết kế version riêng cho từng phần hoặc dùng các câu lệnh cập nhật theo trường với quy tắc rõ ràng. Tuy nhiên, chia version làm tăng độ phức tạp và có thể khiến bất biến liên cột không còn được bảo vệ.

### 2.4. Tăng version kể cả khi giá trị nghiệp vụ không đổi

Giả sử câu lệnh cập nhật cùng giá trị hiện tại:

~~~sql
UPDATE product
SET price = 100.00,
    version = version + 1
WHERE id = 501
  AND version = 7;
~~~

Version vẫn tăng. Đây thường là hành vi mong muốn vì nó xác nhận một thao tác ghi dựa trên phiên bản 7 đã diễn ra và làm cho các bản đọc cũ bị lỗi thời.

Nếu câu lệnh chỉ gán price = 100.00 mà không tăng version, một số driver hoặc hệ quản trị có thể báo số hàng thay đổi bằng 0 khi giá trị không đổi. Điều đó làm cho việc diễn giải row count khó hơn và có thể khiến thay đổi không được nhận biết như một phiên bản mới.

Một số hệ quản trị phân biệt số hàng khớp điều kiện và số hàng thực sự thay đổi. Tăng version trong cùng UPDATE giúp có một thay đổi chắc chắn khi thao tác thành công, nhưng ứng dụng vẫn phải hiểu chính xác semantics của driver đang dùng.

## 3. Hai giao dịch chạy đồng thời

### 3.1. Lịch thực thi khi cả hai cùng đọc version 7

Giả sử giá hiện tại là 100.00 và version = 7.

~~~text
Thời gian       Giao dịch A                  Giao dịch B
----------------------------------------------------------------
t1              SELECT price, version
                -> 100.00, 7

t2                                          SELECT price, version
                                            -> 100.00, 7

t3              UPDATE ... WHERE version=7
                -> cập nhật 1 hàng
                -> version = 8

t4              COMMIT

t5                                          UPDATE ... WHERE version=7
                                            -> cập nhật 0 hàng
                                            -> xung đột
----------------------------------------------------------------
~~~

A và B không cần khóa hàng ngay từ lúc đọc. Chúng có thể cùng đọc version 7. Xung đột được phát hiện ở thời điểm ghi.

Khi B chạy UPDATE, hệ quản trị bảo đảm câu lệnh không thể ghi dựa trên điều kiện version cũ nếu hàng đã được A thay đổi. Tùy hệ quản trị và mức cô lập, B có thể phải chờ A kết thúc trước khi đánh giá lại điều kiện hoặc có thể nhận lỗi serialization. Kết quả quan trọng là B không được âm thầm ghi đè hàng dựa trên version 7.

### 3.2. Điều gì xảy ra nếu A rollback?

Nếu A thực hiện UPDATE nhưng sau đó ROLLBACK, giá trị và version của A không được xác nhận.

Khi B tiếp tục, nếu version vẫn là 7 và hàng vẫn tồn tại, điều kiện của B có thể đúng. B được phép cập nhật dựa trên phiên bản 7.

Điều này thể hiện version phải thay đổi cùng dữ liệu trong cùng transaction. Nếu ứng dụng tăng version bên ngoài giao dịch hoặc trong một giao dịch riêng, dữ liệu và version có thể mất đồng bộ.

### 3.3. Ai là người thắng?

Với optimistic locking, người thắng thường là giao dịch đầu tiên thực hiện thành công thao tác UPDATE có điều kiện và commit. Giao dịch khác phát hiện xung đột khi điều kiện version không còn đúng hoặc khi hệ quản trị trả lỗi xung đột.

"Đầu tiên" ở đây không nhất thiết là người dùng bấm nút trước. Nó phụ thuộc thứ tự các thao tác ghi thực tế và cách hệ quản trị điều phối xung đột.

Optimistic locking không bảo đảm mọi thao tác ghi đều không phải chờ. Hai câu UPDATE cùng hàng vẫn có thể phải chờ nhau ở tầng cơ sở dữ liệu. Khác biệt nằm ở chỗ ứng dụng không khóa hàng từ đầu trong suốt thời gian đọc và tính toán; nó dùng version để phát hiện dữ liệu đã thay đổi trước khi ghi.

## 4. Diễn giải số hàng được cập nhật

### 4.1. Một hàng được cập nhật

Nếu câu UPDATE nhắm đến một khóa chính duy nhất và trả về số hàng được cập nhật là 1, thao tác compare-and-swap đã thành công.

~~~sql
UPDATE product
SET price = 120.00,
    version = version + 1
WHERE id = 501
  AND version = 7;
~~~

Ứng dụng có thể coi thao tác ghi đã vượt qua kiểm tra phiên bản. Nếu đang ở trong một transaction lớn, vẫn cần COMMIT thành công trước khi thông báo thay đổi đã được xác nhận.

### 4.2. Không có hàng nào được cập nhật

Nếu row count bằng 0, một trong các tình huống có thể xảy ra:

- Hàng id = 501 không còn tồn tại.
- Hàng vẫn tồn tại nhưng version không còn bằng 7.
- Người dùng không có quyền cập nhật hàng và chính sách bảo mật khiến hàng không được chọn.
- Điều kiện bổ sung trong WHERE không còn đúng.
- Hệ quản trị hoặc driver báo row count theo semantics khác với giả định của ứng dụng.

Với câu lệnh chỉ dùng khóa chính và expected version, hai nguyên nhân phổ biến nhất là hàng đã bị xóa hoặc phiên bản đã thay đổi.

Ứng dụng có thể thực hiện SELECT mới để phân biệt, nếu việc phân biệt có ý nghĩa nghiệp vụ:

~~~sql
SELECT id, price, version
FROM product
WHERE id = 501;
~~~

Nếu không còn hàng, trả về kết quả "không tồn tại". Nếu hàng còn nhưng version khác, trả về "dữ liệu đã thay đổi". Cần lưu ý kết quả SELECT sau đó chỉ là trạng thái tại thời điểm đọc mới; một giao dịch khác vẫn có thể thay đổi dữ liệu tiếp theo.

Một số API cố tình không phân biệt hai trường hợp để tránh tiết lộ sự tồn tại của tài nguyên hoặc để đơn giản hóa giao diện. Đây là quyết định nghiệp vụ và bảo mật.

### 4.3. Không dùng row count như bằng chứng commit

Row count bằng 1 cho biết câu UPDATE đã khớp và thực hiện cập nhật trong transaction hiện tại. Nếu transaction sau đó ROLLBACK hoặc COMMIT thất bại, thay đổi không trở thành dữ liệu đã xác nhận.

Luồng xử lý nên phân biệt:

1. UPDATE trả về một hàng.
2. Transaction COMMIT thành công.
3. Ứng dụng phát thông báo thành công hoặc thực hiện tác dụng phụ sau commit.

Nếu gửi email hoặc phát sự kiện trước COMMIT rồi transaction rollback, hệ thống bên ngoài có thể nhận thông báo về thay đổi chưa từng được xác nhận. Có thể dùng transactional outbox để ghi sự kiện cùng transaction rồi phát sau commit.

### 4.4. UPDATE ... RETURNING

Một số hệ quản trị hỗ trợ trả về hàng sau khi cập nhật. Ví dụ PostgreSQL:

~~~sql
UPDATE product
SET price = 120.00,
    version = version + 1
WHERE id = 501
  AND version = 7
RETURNING id, price, version;
~~~

Nếu có hàng trả về, ứng dụng nhận được trạng thái mới trong cùng thao tác. Nếu không có hàng trả về, điều kiện không khớp.

SQL Server có cú pháp OUTPUT:

~~~sql
UPDATE product
SET price = 120.00,
    version = version + 1
OUTPUT inserted.id, inserted.price, inserted.version
WHERE id = 501
  AND version = 7;
~~~

Cú pháp và cách đọc kết quả phụ thuộc hệ quản trị. MySQL thường dùng affected rows và có thể thực hiện SELECT tiếp theo trong cùng transaction nếu cần lấy phiên bản mới.

## 5. Tăng version cho INSERT và DELETE

### 5.1. INSERT hàng mới

Khi tạo hàng mới, ứng dụng khởi tạo version theo một quy ước nhất quán, thường là 0 hoặc 1:

~~~sql
INSERT INTO product (id, name, price, version)
VALUES (501, 'Keyboard', 100.00, 0);
~~~

Có thể để DEFAULT ở schema:

~~~sql
ALTER TABLE product
ALTER COLUMN version SET DEFAULT 0;
~~~

Cú pháp ALTER COLUMN khác nhau giữa các hệ quản trị. Hãy xác định default ngay trong schema hoặc trong câu INSERT để mọi đường tạo dữ liệu đều tuân theo cùng quy tắc.

Nếu dùng version = 0 khi tạo mới, lần cập nhật đầu tiên sẽ chuyển lên 1. Nếu dùng version = 1, lần cập nhật đầu tiên chuyển lên 2. Giá trị bắt đầu không quan trọng bằng việc nhất quán giữa mọi thành phần ứng dụng.

### 5.2. DELETE có điều kiện version

Xóa hàng cũng cần kiểm tra phiên bản đã đọc:

~~~sql
DELETE FROM product
WHERE id = 501
  AND version = 7;
~~~

Nếu hàng đã được cập nhật thành version 8, câu DELETE không khớp. Ứng dụng phát hiện rằng người dùng đang xóa một bản dữ liệu cũ.

Không cần tăng version trước khi xóa vì hàng sẽ không còn tồn tại. Điều kiện version trong DELETE là phần compare-and-swap.

Nếu xóa thất bại do version không khớp, ứng dụng có thể tải lại và yêu cầu người dùng xác nhận xóa trạng thái mới. Tự động xóa lại với version mới có thể xóa thay đổi của người khác mà người dùng chưa xem.

### 5.3. Soft delete

Nếu dùng cột deleted_at hoặc trạng thái DELETED, thao tác này là UPDATE và cần tăng version:

~~~sql
UPDATE product
SET deleted_at = CURRENT_TIMESTAMP,
    version = version + 1
WHERE id = 501
  AND version = 7;
~~~

Mọi truy vấn đọc dữ liệu đang hoạt động cần áp dụng điều kiện soft delete phù hợp. Việc xóa mềm vẫn là thay đổi trạng thái và phải tham gia optimistic locking như các thay đổi khác.

## 6. Cập nhật có điều kiện cho tồn kho và số dư

Version không phải cách duy nhất để kiểm tra điều kiện trước khi ghi. Có thể kết hợp version với điều kiện nghiệp vụ trong cùng UPDATE.

### 6.1. Giảm tồn kho không âm

Giả sử bảng inventory có:

~~~sql
CREATE TABLE inventory (
    sku VARCHAR(50) PRIMARY KEY,
    available INT NOT NULL,
    version BIGINT NOT NULL DEFAULT 0
);
~~~

Một giao dịch muốn đặt 3 sản phẩm, chỉ khi tồn kho đủ:

~~~sql
UPDATE inventory
SET available = available - 3,
    version = version + 1
WHERE sku = 'BOOK-01'
  AND version = 12
  AND available >= 3;
~~~

Thao tác này đồng thời kiểm tra:

- Đúng sản phẩm.
- Version vẫn là 12.
- Tồn kho vẫn đủ 3.
- Nếu tất cả điều kiện đúng, giảm tồn kho và tăng version nguyên tử.

Nếu row count bằng 0, có thể do version đã đổi, hàng không tồn tại hoặc tồn kho không đủ. Ứng dụng cần xác định cách xử lý theo nghiệp vụ.

### 6.2. Atomic conditional update không nhất thiết cần version

Nếu chỉ cần bảo vệ điều kiện số dư/tồn kho, một UPDATE có điều kiện có thể đủ:

~~~sql
UPDATE inventory
SET available = available - 3
WHERE sku = 'BOOK-01'
  AND available >= 3;
~~~

Hệ quản trị đánh giá điều kiện và cập nhật hàng nguyên tử. Nếu row count bằng 1, đã giảm tồn kho; nếu bằng 0, hàng không tồn tại hoặc không đủ hàng.

Thêm version hữu ích khi ứng dụng đã đọc một trạng thái cụ thể và cần phát hiện bất kỳ thay đổi nào trên hàng kể từ lần đọc đó. Nếu nghiệp vụ chỉ cần bảo đảm available không âm, điều kiện available >= 3 có thể diễn đạt bất biến trực tiếp hơn.

Có thể kết hợp cả hai nếu ứng dụng cần cả hai đảm bảo. Không nên thêm version chỉ vì mọi câu UPDATE đều phải có version; hãy xác định điều kiện nào thực sự cần bảo vệ.

### 6.3. Cập nhật số dư

Một ví dụ chuyển tiền có thể kiểm tra số dư không âm:

~~~sql
UPDATE account
SET balance = balance - 100,
    version = version + 1
WHERE id = 10
  AND version = 5
  AND balance >= 100;
~~~

Nếu câu lệnh thành công, hàng được cập nhật dựa trên version 5 và số dư đủ. Tuy nhiên, chuyển tiền còn cần cập nhật tài khoản nhận trong cùng transaction, xử lý thứ tự khóa giữa hai tài khoản và bảo đảm cả hai thay đổi cùng commit hoặc cùng rollback.

Version trên từng hàng không thay thế transaction cho nghiệp vụ nhiều hàng.

## 7. Ví dụ với JDBC

### 7.1. Đọc version và dữ liệu

~~~java
String selectSql = """
    SELECT id, price, version
    FROM product
    WHERE id = ?
    """;

try (PreparedStatement statement = connection.prepareStatement(selectSql)) {
    statement.setLong(1, productId);

    try (ResultSet resultSet = statement.executeQuery()) {
        if (!resultSet.next()) {
            throw new ProductNotFoundException(productId);
        }

        BigDecimal price = resultSet.getBigDecimal("price");
        long expectedVersion = resultSet.getLong("version");

        // Dùng dữ liệu này để tính toán hoặc hiển thị.
    }
}
~~~

Ứng dụng giữ expectedVersion cùng dữ liệu đã đọc. Nếu người dùng chỉnh sửa trên một màn hình lâu, expectedVersion vẫn là version của lần tải ban đầu.

### 7.2. Cập nhật và kiểm tra row count

~~~java
String updateSql = """
    UPDATE product
    SET price = ?,
        version = version + 1
    WHERE id = ?
      AND version = ?
    """;

try (PreparedStatement statement = connection.prepareStatement(updateSql)) {
    statement.setBigDecimal(1, newPrice);
    statement.setLong(2, productId);
    statement.setLong(3, expectedVersion);

    int updatedRows = statement.executeUpdate();

    if (updatedRows == 0) {
        throw new OptimisticLockConflictException(productId);
    }

    if (updatedRows != 1) {
        throw new IllegalStateException(
            "Expected to update one product, got " + updatedRows
        );
    }
}
~~~

Với khóa chính duy nhất, số hàng hợp lệ thường là 0 hoặc 1. Nếu câu lệnh có điều kiện trên nhiều hàng, cần định nghĩa rõ cách diễn giải row count.

Ví dụ chỉ minh họa phần thao tác. Trong ứng dụng thật, cần quản lý transaction, rollback khi có lỗi và chỉ báo thành công sau commit.

### 7.3. Dùng transaction rõ ràng

~~~java
connection.setAutoCommit(false);

try {
    // Đọc dữ liệu và expectedVersion nếu cần.
    // Chạy UPDATE có điều kiện version.
    // Kiểm tra số hàng được cập nhật.

    connection.commit();
} catch (SQLException | RuntimeException ex) {
    connection.rollback();
    throw ex;
}
~~~

Nếu giao dịch chỉ cập nhật một hàng và câu UPDATE là toàn bộ thao tác nghiệp vụ, auto-commit có thể đủ. Nếu có nhiều câu lệnh phải cùng thành công, cần transaction bao quanh.

Khi dùng connection pool, không được để connection ở trạng thái transaction mở hoặc autoCommit=false sau khi trả về pool. Hãy kết thúc transaction và khôi phục trạng thái connection theo quản lý của pool/framework.

## 8. Optimistic locking với JPA và Hibernate

### 8.1. Dùng @Version

JPA hỗ trợ optimistic locking thông qua thuộc tính được đánh dấu @Version:

~~~java
@Entity
@Table(name = "product")
public class Product {

    @Id
    private Long id;

    private BigDecimal price;

    @Version
    private Long version;

    // getters/setters
}
~~~

Khi entity được đọc, persistence provider giữ version hiện tại. Khi entity thay đổi và được flush, provider phát ra UPDATE có điều kiện version theo cơ chế của nó, đồng thời tăng version.

SQL được sinh ra thường có hình dạng tương tự:

~~~sql
UPDATE product
SET price = ?,
    version = ?
WHERE id = ?
  AND version = ?;
~~~

Tên cột, cách tăng version và thời điểm flush phụ thuộc provider và mapping. Không nên giả định SQL sinh ra giống hệt ví dụ minh họa.

### 8.2. OptimisticLockException

Nếu hàng đã được giao dịch khác thay đổi, UPDATE của Hibernate/JPA có thể không cập nhật được hàng mong đợi. Provider báo lỗi optimistic locking, thường thông qua OptimisticLockException hoặc exception cụ thể của Hibernate/Spring.

Lỗi có thể xuất hiện tại thời điểm:

- Gọi flush.
- Thực hiện query khiến persistence context phải flush.
- Commit transaction.

Vì vậy, nếu chỉ bắt exception quanh lệnh save mà không bao quanh transaction commit, ứng dụng có thể bỏ sót thời điểm lỗi thực sự được ném ra.

### 8.3. Không tự sửa version khi dùng @Version

Khi provider quản lý @Version, không nên tự tăng trường version trong mã nghiệp vụ:

~~~java
product.setVersion(product.getVersion() + 1); // Không nên tự làm
~~~

Provider cần kiểm soát giá trị version cũ và mới để phát hiện xung đột. Thay đổi version thủ công có thể gây lỗi, làm sai kỳ vọng của persistence context hoặc phá cơ chế optimistic locking.

Nếu cần cập nhật trực tiếp bằng JPQL bulk update hoặc native SQL, phải hiểu rằng các câu lệnh bulk thường bỏ qua lifecycle và dirty checking của từng entity. Chúng có thể không tự tăng @Version hoặc đồng bộ trạng thái entity đang nằm trong persistence context.

### 8.4. Bulk update và native SQL

Một câu JPQL bulk update như:

~~~java
@Modifying
@Query("""
    update Product p
    set p.price = :price
    where p.id = :id
    """)
int updatePrice(Long id, BigDecimal price);
~~~

có thể cập nhật dữ liệu mà không áp dụng quy trình optimistic locking tự động của từng entity. Nếu muốn bảo vệ version, hãy đưa version vào điều kiện và tăng version trong cùng câu lệnh:

~~~java
@Modifying
@Query("""
    update Product p
    set p.price = :price,
        p.version = p.version + 1
    where p.id = :id
      and p.version = :expectedVersion
    """)
int updatePrice(
    Long id,
    Long expectedVersion,
    BigDecimal price
);
~~~

Sau đó kiểm tra số hàng được cập nhật. Nếu persistence context đang giữ Product cùng id, cần làm mới hoặc clear context phù hợp để tránh tiếp tục dùng entity với version cũ.

Không nên trộn cập nhật native SQL và entity managed trong cùng transaction mà không có chiến lược đồng bộ trạng thái rõ ràng.

## 9. Phạm vi bảo vệ và giới hạn của version

### 9.1. Version một hàng bảo vệ một hàng

Giả sử giao dịch đọc hai hàng:

~~~sql
SELECT available FROM inventory WHERE sku = 'A';
SELECT available FROM inventory WHERE sku = 'B';
~~~

Nó kiểm tra version của A khi cập nhật A, nhưng lại không kiểm tra version của B. Nếu B thay đổi sau lần đọc, kết quả nghiệp vụ được tính từ cả A và B có thể đã lỗi thời.

Nếu giao dịch phụ thuộc vào nhiều hàng, cần bảo vệ tất cả dữ liệu ảnh hưởng đến quyết định hoặc dùng cơ chế cô lập/ràng buộc phù hợp.

### 9.2. Version không tự bảo vệ predicate

Giả sử một phòng không được có hai lịch đặt chồng lấn. Ứng dụng truy vấn và nhận về 0 hàng, sau đó thêm một lịch.

Không có hàng nào trong kết quả để lấy version. Hai giao dịch cùng đọc rỗng và cùng thêm lịch vẫn có thể vi phạm quy tắc nếu chỉ dùng version trên hàng mới.

Các lựa chọn bảo vệ gồm:

- Ràng buộc exclusion phù hợp nếu hệ quản trị hỗ trợ.
- Khóa hàng đại diện cho phòng trước khi kiểm tra và thêm lịch.
- SERIALIZABLE với xử lý serialization failure.
- Một cấu trúc dữ liệu hoặc hàng tổng hợp đại diện cho phạm vi cần bảo vệ.

Version trên hàng đại diện cũng có thể dùng được nếu mọi giao dịch liên quan đều cập nhật hoặc tăng version của hàng đó theo cùng một giao thức. Nếu có luồng ghi bỏ qua hàng đại diện, đảm bảo không còn hiệu lực.

### 9.3. Nhiều bảng trong một aggregate

Một đối tượng nghiệp vụ có thể gồm bảng order và order_item. Nếu người dùng đọc toàn bộ đơn hàng rồi sửa một dòng chi tiết, version ở bảng order chỉ bảo vệ được các thay đổi nếu mọi đường cập nhật order_item đều phối hợp với version của order.

Có thể dùng một version ở hàng gốc aggregate và tăng nó trong cùng transaction mỗi khi bất kỳ thành phần nào thay đổi. Hoặc dùng version riêng cho từng hàng và bảo vệ các bất biến liên hàng bằng một cơ chế khác.

Thiết kế phải xác định rõ ranh giới aggregate và mọi đường ghi. Một version field chỉ có ý nghĩa khi mọi writer liên quan tuân thủ cùng quy tắc.

### 9.4. Version không thay thế ràng buộc dữ liệu

Optimistic locking giải quyết xung đột giữa các giao dịch dựa trên phiên bản cũ. Nó không thay thế:

- PRIMARY KEY và UNIQUE để ngăn dữ liệu trùng.
- FOREIGN KEY để bảo vệ quan hệ tham chiếu.
- CHECK để bảo vệ điều kiện trên hàng.
- Transaction để bảo vệ nhóm thay đổi phải cùng thành công.
- SERIALIZABLE hoặc cơ chế bảo vệ phạm vi khi cần bất biến liên hàng.

Ví dụ, hai giao dịch thêm cùng email vẫn cần UNIQUE constraint. Một version field trên hai hàng mới khác nhau không thể ngăn chúng tạo email trùng.

## 10. Chọn kiểu version và quy tắc tăng

### 10.1. Số nguyên tăng dần

Kiểu BIGINT thường là lựa chọn đơn giản:

~~~sql
version BIGINT NOT NULL DEFAULT 0
~~~

Ưu điểm:

- So sánh chính xác.
- Dễ tăng bằng version = version + 1.
- Không phụ thuộc độ chính xác đồng hồ.
- Dễ ánh xạ trong JDBC và ORM.

Cần cân nhắc giới hạn số nguyên nếu một hàng được cập nhật với tần suất cực cao trong thời gian dài. BIGINT có miền rất lớn, nhưng phép tăng vẫn có giới hạn và có thể lỗi khi tràn.

### 10.2. Timestamp

Một số hệ thống dùng updated_at hoặc timestamp làm dấu phiên bản. Cách này có rủi ro:

- Độ chính xác timestamp có thể thấp hơn tốc độ cập nhật.
- Hai lần cập nhật có thể nhận cùng giá trị thời gian.
- Đồng hồ hệ thống có thể lệch hoặc bị điều chỉnh.
- Múi giờ và cách chuẩn hóa giá trị có thể gây nhầm lẫn.
- So sánh timestamp cần thống nhất độ chính xác giữa ứng dụng và database.

Nếu dùng timestamp, phải bảo đảm mỗi lần ghi tạo ra một giá trị khác biệt đủ để phát hiện xung đột. Số nguyên tăng dần thường đơn giản và đáng tin cậy hơn cho optimistic locking trên một hàng.

### 10.3. UUID hoặc token phiên bản

Một số thiết kế thay version bằng token ngẫu nhiên mới mỗi lần cập nhật:

~~~sql
UPDATE document
SET content = :content,
    version_token = :new_token
WHERE id = :id
  AND version_token = :expected_token;
~~~

Token phải được tạo mới đủ duy nhất và thay đổi nguyên tử cùng dữ liệu. Cách này có thể phù hợp khi client truyền opaque ETag hoặc version token, nhưng không thuận tiện để tính số lần cập nhật.

### 10.4. Không cho phép NULL

Version nên NOT NULL. Nếu version là NULL, phép so sánh:

~~~sql
WHERE version = NULL
~~~

không đúng như so sánh bằng thông thường trong SQL; kết quả là UNKNOWN. Điều này có thể khiến UPDATE không khớp hoặc buộc ứng dụng xử lý các trường hợp đặc biệt.

Hãy khởi tạo version cho mọi hàng và dùng DEFAULT phù hợp. Khi thêm cột vào bảng hiện có, cần migration điền giá trị cho các hàng cũ trước khi áp đặt NOT NULL nếu hệ quản trị yêu cầu.

## 11. Retry và hợp nhất xung đột

### 11.1. Không tự động ghi lại với version mới mà không đọc lại

Khi UPDATE trả về 0 hàng, ứng dụng có thể tải lại dữ liệu mới. Nhưng không nên chỉ thay expectedVersion thành version mới rồi gửi lại cùng giá trị đã tính từ bản cũ.

Ví dụ, B đọc balance = 1000 và muốn giảm 200. A đã giảm 100, nên balance hiện tại là 900. Nếu B chỉ thay expectedVersion từ 7 sang 8 rồi gửi lại lệnh đặt balance = 800, kết quả có thể đúng nếu nghiệp vụ là giảm 200. Nhưng nếu B đã tính một giá trị tuyệt đối hoặc ghi đè nhiều trường dựa trên trạng thái cũ, việc gửi lại có thể xóa mất thay đổi của A.

Quy trình an toàn:

1. Tải dữ liệu và version mới.
2. Xác định thay đổi của người dùng còn hợp lệ hay không.
3. Tính lại giá trị dẫn xuất từ dữ liệu mới nếu cần.
4. Yêu cầu người dùng hợp nhất nếu hai thay đổi không thể tự động kết hợp.
5. Gửi UPDATE mới với expectedVersion mới.
6. Nếu lại xung đột, áp dụng chính sách retry có giới hạn.

### 11.2. Phân biệt thao tác tương đối và tuyệt đối

Thao tác tương đối:

~~~sql
UPDATE account
SET balance = balance - 100,
    version = version + 1
WHERE id = 10
  AND version = 7;
~~~

Thao tác tuyệt đối:

~~~sql
UPDATE product
SET price = 120.00,
    version = version + 1
WHERE id = 501
  AND version = 7;
~~~

Thao tác tương đối có thể được tính lại trên trạng thái mới nếu nghiệp vụ cho phép. Thao tác tuyệt đối thường thể hiện ý định đặt một giá trị cụ thể; nếu dữ liệu đã đổi, cần cân nhắc xung đột với chỉnh sửa của người khác.

Không phải mọi thao tác đều có thể tự động merge. Quyết định phụ thuộc ý nghĩa nghiệp vụ, không chỉ khả năng kỹ thuật của SQL.

### 11.3. Retry toàn bộ transaction khi cần

Nếu transaction có nhiều bước đọc và ghi, lỗi optimistic locking có thể làm mất tính hợp lệ của toàn bộ phép tính. Khi đó, phải tải lại dữ liệu và chạy lại toàn bộ đơn vị nghiệp vụ.

Không chỉ retry câu UPDATE cuối cùng nếu các quyết định trước đó phụ thuộc vào dữ liệu cũ.

Nếu lỗi xuất hiện tại commit, transaction hiện tại có thể đã rollback-only. Hãy bắt đầu transaction mới cho lần thử tiếp theo.

### 11.4. Giới hạn retry và backoff

Retry vô hạn có thể làm một tài nguyên nóng trở nên tệ hơn. Nên:

- Giới hạn số lần thử.
- Dùng backoff tăng dần và jitter khi có nhiều client cạnh tranh.
- Ghi nhận số lần xung đột.
- Trả lỗi có thể thử lại khi vượt giới hạn.
- Chuyển sang khóa tường minh hoặc hàng đợi nếu một tài nguyên liên tục xung đột.

Nếu người dùng đang chỉnh sửa một biểu mẫu, phản hồi "dữ liệu đã được người khác cập nhật" và cho phép tải lại/hợp nhất thường tốt hơn việc retry tự động nhiều lần mà người dùng không biết.

## 12. Tích hợp với HTTP ETag và If-Match

Optimistic versioning có thể mở rộng ra API. Server trả về một version hoặc ETag:

~~~http
HTTP/1.1 200 OK
ETag: "product-501-v7"
Content-Type: application/json
~~~

Client gửi yêu cầu cập nhật kèm If-Match:

~~~http
PUT /products/501
If-Match: "product-501-v7"
Content-Type: application/json

{
  "price": 120.00
}
~~~

Server dùng version trong ETag làm expectedVersion:

~~~sql
UPDATE product
SET price = 120.00,
    version = version + 1
WHERE id = 501
  AND version = 7;
~~~

Nếu không có hàng nào được cập nhật do version đã thay đổi, API có thể trả HTTP 412 Precondition Failed khi điều kiện If-Match không còn đúng. Một số API dùng 409 Conflict cho xung đột nghiệp vụ. Cần chọn semantics nhất quán và tài liệu hóa rõ.

ETag nên là token đại diện cho trạng thái tài nguyên cần bảo vệ. Nếu response chứa dữ liệu từ nhiều bảng nhưng ETag chỉ phản ánh version của một bảng, nó có thể không phát hiện các thay đổi ở bảng khác.

ETag cũng có thể là weak hoặc strong theo HTTP semantics. Với If-Match, nên dùng validator mạnh khi yêu cầu điều kiện phiên bản chính xác.

## 13. Kiểm thử optimistic locking

### 13.1. Kiểm tra xung đột bằng hai transaction

Một kiểm thử cần chứng minh hai giao dịch cùng đọc version cũ nhưng chỉ một giao dịch ghi thành công.

Trình tự:

1. Tạo product với version = 7.
2. Mở transaction A và transaction B.
3. Cả A và B đọc version = 7.
4. A UPDATE với điều kiện version = 7; xác nhận row count = 1.
5. A COMMIT.
6. B UPDATE với điều kiện version = 7; xác nhận row count = 0 hoặc lỗi đồng thời theo DB/isolation.
7. Đọc lại hàng và xác nhận giá trị của A cùng version = 8 được giữ.

Không nên chỉ kiểm tra một transaction đơn lẻ vì không chứng minh được race condition đã được ngăn.

### 13.2. Dùng barrier để điều khiển thứ tự

Trong kiểm thử đa luồng, dùng CountDownLatch, CyclicBarrier hoặc công cụ đồng bộ tương đương để bảo đảm cả hai luồng đã đọc version trước khi cho phép một luồng ghi.

Nếu chỉ dùng Thread.sleep, lịch thực thi có thể khác giữa các lần chạy và kiểm thử dễ flaky.

### 13.3. Kiểm tra rollback

Một kiểm thử khác cần xác nhận nếu A UPDATE rồi ROLLBACK, version và dữ liệu trở lại trạng thái cũ. B đang giữ expectedVersion cũ phải có thể cập nhật thành công nếu không có thay đổi nào khác.

### 13.4. Kiểm tra mọi đường ghi

Nếu ứng dụng có nhiều đường cập nhật:

- REST API.
- Batch job.
- Admin tool.
- Scheduled task.
- Native SQL.
- ORM entity update.
- Trigger hoặc stored procedure.

Hãy bảo đảm tất cả đường ghi đều tăng version theo cùng quy tắc. Chỉ một luồng bỏ qua version cũng có thể làm các luồng còn lại không phát hiện được thay đổi.

### 13.5. Kiểm tra delete và bulk update

Kiểm thử riêng:

- DELETE có điều kiện version cũ.
- Soft delete tăng version.
- Bulk update tăng version và kiểm tra expected version.
- Cập nhật không đổi giá trị nghiệp vụ vẫn tăng version nếu đó là quy ước.
- Row count khi không tồn tại và khi version không khớp.
- Tác động đến entity đang được quản lý trong persistence context.

## 14. Những lỗi thiết kế thường gặp

**Chỉ SELECT version rồi so sánh ở ứng dụng.**

Kiểm tra và ghi không nguyên tử. Giao dịch khác có thể thay đổi hàng sau SELECT. Đưa expectedVersion vào WHERE của UPDATE.

**Cập nhật dữ liệu rồi tăng version ở câu lệnh riêng.**

Một thao tác khác có thể chen vào giữa hoặc một câu lệnh có thể thất bại khiến version và dữ liệu lệch nhau. Cập nhật cả hai trong cùng câu UPDATE và cùng transaction.

**Có một số đường ghi không tăng version.**

Một batch job hoặc native SQL bỏ qua version khiến client cũ vẫn ghi thành công. Chuẩn hóa quy tắc ở tất cả writer.

**Chỉ kiểm tra version của một hàng trong quy tắc nhiều hàng.**

Một version không đại diện cho toàn bộ tập dữ liệu mà nghiệp vụ đã đọc. Cần bảo vệ mọi phụ thuộc hoặc dùng SERIALIZABLE/ràng buộc/guard row.

**Tự động retry bằng version mới nhưng giữ nguyên phép tính cũ.**

Có thể ghi đè thay đổi của người khác. Phải đọc lại và tính lại hoặc yêu cầu hợp nhất.

**Thông báo thành công ngay sau UPDATE trước COMMIT.**

Commit có thể thất bại. Chỉ công bố thành công sau khi transaction kết thúc thành công.

**Dùng timestamp có độ chính xác thấp làm version.**

Hai lần cập nhật gần nhau có thể tạo cùng timestamp. Dùng số nguyên tăng dần hoặc token có tính duy nhất đủ mạnh.

**Tự sửa trường @Version trong JPA.**

Provider quản lý version. Không tự tăng trường này trong entity nếu dùng cơ chế @Version.

**Bỏ qua số hàng được cập nhật.**

Không phát hiện xung đột và tiếp tục báo thành công. Hãy kiểm tra row count hoặc exception theo hợp đồng của driver/provider.

## 15. Quy trình triển khai trong một ứng dụng

Một luồng cập nhật có optimistic locking có thể tổ chức như sau:

~~~text
Client yêu cầu đọc tài nguyên
        |
        v
Server đọc dữ liệu và version
        |
        v
Client chỉnh sửa dữ liệu
        |
        v
Client gửi dữ liệu + expectedVersion
        |
        v
Server chạy UPDATE có điều kiện
        |
        +---- row count = 1 ----> COMMIT thành công
        |                              |
        |                              v
        |                         Trả kết quả mới
        |
        +---- row count = 0 ----> Xung đột hoặc tài nguyên không tồn tại
                                       |
                                       v
                               Tải lại / hợp nhất / báo lỗi
~~~

Các quyết định quan trọng:

1. Xác định những cột và quan hệ nào được bảo vệ bởi version.
2. Thêm version NOT NULL với giá trị khởi tạo thống nhất.
3. Đưa expectedVersion vào WHERE của mọi UPDATE/DELETE cần bảo vệ.
4. Tăng version trong cùng thao tác nguyên tử thay đổi dữ liệu.
5. Kiểm tra row count hoặc exception.
6. Commit trước khi trả kết quả thành công.
7. Xử lý xung đột bằng reload, merge hoặc retry có giới hạn.
8. Bảo đảm mọi đường ghi đều tuân thủ quy tắc.
9. Kiểm thử bằng hai transaction thực sự chạy đồng thời.

Version field tạo ra một giao thức giữa các writer. Nó chỉ hoạt động khi tất cả writer tuân theo cùng quy ước.

## 16. Khi nào nên dùng version-based optimistic locking?

Cách này thường phù hợp khi:

- Nhiều giao dịch đọc cùng dữ liệu nhưng ít giao dịch ghi đồng thời.
- Người dùng có thể giữ biểu mẫu chỉnh sửa trong thời gian dài.
- Không muốn khóa hàng trong suốt thời gian người dùng suy nghĩ.
- Cần phát hiện một bản ghi đã bị người khác sửa trước khi lưu.
- Xung đột có thể được xử lý bằng tải lại, hợp nhất hoặc yêu cầu xác nhận.
- Phần lớn thao tác ghi nhắm đến một hàng hoặc một aggregate có ranh giới rõ.

Cần cân nhắc khóa tường minh hoặc cơ chế khác khi:

- Một hàng nóng bị cập nhật liên tục.
- Giao dịch thường xuyên phải retry.
- Phép tính trước commit tốn kém và thường bị vô hiệu.
- Nghiệp vụ phụ thuộc vào predicate hoặc nhiều hàng mà version một hàng không bảo vệ được.
- Có quy tắc liên hàng cần được bảo vệ bằng SERIALIZABLE, constraint hoặc guard row.

Optimistic locking không làm cho mọi thao tác ghi không chờ. Nó chuyển một phần phát hiện xung đột sang thời điểm ghi và cho phép các lần đọc trước đó diễn ra mà không giữ khóa hàng trong suốt quá trình xử lý.

Điều kiện version, thay đổi dữ liệu và tăng version phải nằm trong cùng câu lệnh nguyên tử. Đó là điểm bảo đảm rằng một giao dịch chỉ ghi được khi trạng thái hiện tại vẫn là trạng thái mà nó đã đọc và dựa vào.
