# Phân biệt chữ hoa chữ thường, filesystem và lower_case_table_names

Một ứng dụng có thể chạy bình thường trên máy lập trình Windows nhưng lỗi khi triển khai lên Linux chỉ vì tên bảng khác chữ hoa, chữ thường. Ví dụ, code truy vấn `SELECT * FROM Customer` trong khi bảng được tạo là `customer`. Trên một máy chủ MySQL so sánh tên bảng không phân biệt hoa thường, câu lệnh vẫn chạy; trên máy chủ so sánh phân biệt hoa thường, câu lệnh có thể báo không tìm thấy bảng.

Nguyên nhân liên quan đến cách hệ điều hành và filesystem xử lý tên tệp, cùng cấu hình `lower_case_table_names` của MySQL. Trong module **DATABASE_MYSQL**, hiểu các quy tắc này giúp thiết kế tên schema/table có tính portable, tránh lỗi khi chuyển môi trường, restore backup hoặc cấu hình replication.

## 1. Phân biệt tên đối tượng và dữ liệu dạng chuỗi

Trước tiên, cần tách hai khái niệm thường bị nhầm:

- **Tên định danh (identifier)** là tên database, table, column, index, view hoặc đối tượng SQL khác. Quy tắc phân biệt chữ hoa/chữ thường của tên database và table phụ thuộc cấu hình MySQL và môi trường filesystem.
- **Giá trị dữ liệu dạng chuỗi** là nội dung được lưu trong cột `VARCHAR`, `TEXT` hoặc literal trong câu SQL. Việc so sánh `'Alice'` với `'alice'` chủ yếu do collation của biểu thức/cột quyết định, không phải do `lower_case_table_names`.

Ví dụ, hai vấn đề sau thuộc hai cơ chế khác nhau:

```sql
-- Tên bảng Customer/customer: chịu quy tắc identifier của MySQL.
SELECT * FROM Customer;

-- So sánh giá trị chuỗi: chịu collation của biểu thức.
SELECT 'Alice' = 'alice';
```

Trên MySQL 8.0, collation mặc định phổ biến `utf8mb4_0900_ai_ci` không phân biệt chữ hoa/chữ thường khi so sánh chuỗi. Nếu nghiệp vụ cần phân biệt, hãy chọn collation phù hợp, ví dụ collation có hậu tố `_cs` cho so sánh phân biệt hoa thường. Đừng thay `lower_case_table_names` để điều khiển cách so sánh nội dung cột.

## 2. Filesystem phân biệt chữ hoa/chữ thường như thế nào?

Tên tệp có thể được xử lý theo hai cách chính:

| Đặc tính | Cách xử lý | Ví dụ |
|---|---|---|
| Case-sensitive | `Customer` và `customer` là hai tên khác nhau | Filesystem Linux như ext4 thường phân biệt hai tên này |
| Case-insensitive | `Customer` và `customer` được xem là cùng một tên khi tra cứu | NTFS trên Windows thường không phân biệt hoa thường theo cấu hình mặc định; APFS trên macOS thường được tạo ở chế độ không phân biệt hoa thường |
| Case-preserving | Giữ cách viết hoa/thường ban đầu để hiển thị | Một filesystem có thể lưu tên hiển thị `Customer` nhưng vẫn tra cứu `customer` như cùng một tên |

Case-preserving và case-sensitive không phải cùng một đặc tính. Windows thường giữ nguyên kiểu chữ khi hiển thị tên tệp nhưng vẫn tra cứu tên không phân biệt hoa thường. macOS cũng có thể dùng volume APFS phân biệt hoa thường hoặc không phân biệt hoa thường tùy cách tạo volume. Vì vậy, không nên suy luận chỉ từ tên hệ điều hành; cần biết filesystem và cấu hình thực tế của datadir.

MySQL lưu trữ database và table theo cách gắn với hệ thống tệp. Dù MySQL 8.0 có data dictionary riêng để quản lý metadata, cách so sánh tên database/table vẫn phải tương thích với filesystem và được điều khiển bởi `lower_case_table_names`. Một cấu hình không phù hợp với đặc tính filesystem có thể khiến tên đối tượng bị xử lý không như mong đợi hoặc không được máy chủ hỗ trợ.

## 3. Quy tắc mặc định theo hệ điều hành

Trong các cài đặt MySQL phổ biến, giá trị mặc định thường là:

| Môi trường phổ biến | Giá trị mặc định thường gặp | Hệ quả |
|---|---:|---|
| Windows | `1` | Tên database/table được lưu ở dạng chữ thường và so sánh không phân biệt hoa thường |
| Linux/Unix | `0` | Tên được giữ như khai báo và so sánh phân biệt hoa thường |
| macOS | `2` | Tên được giữ như khai báo nhưng so sánh không phân biệt hoa thường; phù hợp với filesystem mặc định không phân biệt hoa thường |

Đây là mặc định phổ biến, không thay thế việc kiểm tra cấu hình trên máy chủ cụ thể. Bản phân phối, cách cài đặt, filesystem, volume và cấu hình khởi tạo có thể làm giá trị thực tế khác với giả định theo hệ điều hành.

Ví dụ, một nhóm phát triển dùng Windows có thể tạo bảng `Customer`. Môi trường Windows với `lower_case_table_names=1` vẫn chấp nhận tham chiếu `customer`. Khi triển khai cùng database lên Linux với `lower_case_table_names=0`, tên `customer` có thể không khớp bảng `Customer` và truy vấn thất bại.

## 4. Ba giá trị của `lower_case_table_names`

`lower_case_table_names` là biến cấu hình MySQL điều khiển cách xử lý chữ hoa/chữ thường của tên database và table. Có ba giá trị thường được mô tả:

| Giá trị | Cách lưu tên | Cách so sánh tên | Môi trường thường phù hợp |
|---:|---|---|---|
| `0` | Giữ nguyên chữ hoa/thường như khi tạo | Phân biệt hoa thường | Filesystem phân biệt hoa thường, thường gặp trên Linux/Unix |
| `1` | Chuyển tên thành chữ thường khi lưu | Không phân biệt hoa thường | Filesystem không phân biệt hoa thường, thường gặp trên Windows |
| `2` | Giữ nguyên chữ hoa/thường như khi tạo | Chuyển về chữ thường khi so sánh | Filesystem không phân biệt hoa thường, thường gặp trên macOS |

Có thể hình dung qua ví dụ tạo database `SalesDB` và bảng `Customer`:

- Với `0`, MySQL giữ tên như khai báo; tham chiếu `SalesDB.Customer` phải đúng kiểu chữ.
- Với `1`, tên được lưu thành `salesdb.customer`; các tham chiếu `SalesDB.Customer`, `salesdb.customer` hoặc `SALEsDB.CUSTOMER` được so sánh không phân biệt hoa thường.
- Với `2`, tên được giữ theo kiểu chữ đã khai báo nhưng phép tra cứu không phân biệt hoa thường.

Giá trị `2` không có nghĩa là mọi filesystem đều có thể dùng chế độ này. Nó được thiết kế cho filesystem không phân biệt hoa thường; trên filesystem phân biệt hoa thường, không nên chọn `2` như một cách để có cả hai lợi ích.

### Kiểm tra giá trị đang chạy

Kết nối đến đúng MySQL Server và chạy:

```sql
SELECT VERSION();
SELECT @@GLOBAL.lower_case_table_names;
SHOW VARIABLES LIKE 'lower_case_table_names';
SHOW VARIABLES LIKE 'datadir';
```

`@@GLOBAL.lower_case_table_names` cho biết giá trị cấu hình đang có hiệu lực. `datadir` giúp xác định thư mục dữ liệu mà MySQL sử dụng; nếu cần xác minh đặc tính filesystem, hãy kiểm tra volume chứa thư mục đó trên máy chủ.

Không dựa vào cấu hình của MySQL client hoặc hệ điều hành máy lập trình để kết luận giá trị trên server. Ứng dụng có thể kết nối đến một máy chủ từ xa chạy hệ điều hành và filesystem hoàn toàn khác.

## 5. Phạm vi ảnh hưởng của quy tắc hoa thường

`lower_case_table_names` chủ yếu điều khiển cách MySQL xử lý tên database và table. Không phải mọi identifier trong SQL đều chịu cùng quy tắc:

| Loại tên | Quy tắc cần nhớ |
|---|---|
| Database/schema name | Chịu ảnh hưởng của `lower_case_table_names` và cấu hình filesystem |
| Table name | Chịu ảnh hưởng của `lower_case_table_names` và cấu hình filesystem |
| Table alias | Có thể phân biệt hoa thường trên Unix; hành vi phụ thuộc nền tảng MySQL |
| Column name | Không phân biệt hoa thường trong MySQL |
| Index name | Không phân biệt hoa thường trong MySQL |
| Tên stored routine và event | Không phân biệt hoa thường trong MySQL |
| Giá trị chuỗi trong cột | Theo collation hoặc phép so sánh được sử dụng |

Ví dụ với tên cột, cách viết sau được xem là cùng tên cột:

```sql
SELECT CustomerID, customerid, CUSTOMERID
FROM customers;
```

Tuy nhiên, đừng áp dụng kết luận này cho tên bảng trên một server có `lower_case_table_names=0`. Ngoài ra, table alias có quy tắc riêng; nếu muốn SQL portable giữa các hệ điều hành, hãy dùng một kiểu viết thống nhất cho alias và tham chiếu alias nhất quán.

## 6. Thực nghiệm sự khác nhau trên schema riêng

Chỉ thực hiện trong môi trường thử nghiệm và với một schema dành riêng cho bài học. Không tạo các đối tượng chỉ khác nhau về chữ hoa/chữ thường trong database đang chứa dữ liệu thật.

Tạo schema và bảng mẫu:

```sql
CREATE DATABASE CaseLab;
USE CaseLab;

CREATE TABLE Customer (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL
);

INSERT INTO Customer (id, full_name)
VALUES (1, 'Nguyen An');

SHOW TABLES;
```

Thử truy vấn đúng kiểu chữ đã tạo:

```sql
SELECT * FROM Customer;
```

Sau đó thử tham chiếu bằng kiểu chữ khác:

```sql
SELECT * FROM customer;
```

Kết quả phụ thuộc `@@GLOBAL.lower_case_table_names`:

- Với `0`, trên filesystem phân biệt hoa thường, truy vấn thứ hai thường báo không tìm thấy bảng.
- Với `1` hoặc `2`, tên bảng được tra cứu không phân biệt hoa thường nên truy vấn thứ hai có thể thành công.

Để xem cách tên được hiển thị, so sánh `SHOW TABLES` và tên trong câu `SHOW CREATE TABLE`:

```sql
SHOW CREATE TABLE CaseLab.Customer;
```

Với giá trị `1`, MySQL lưu tên database/table ở dạng chữ thường. Với `0` và `2`, tên được giữ theo kiểu chữ khi khai báo. Hãy ghi lại cả giá trị cấu hình lẫn kết quả thực nghiệm; đừng chỉ ghi kết luận dựa trên máy phát triển của mình.

## 7. Vì sao không nên đặt tên chỉ khác chữ hoa/thường?

Trên một server dùng `lower_case_table_names=0` và filesystem phân biệt hoa thường, có thể tồn tại các đối tượng như `Customer` và `customer`. Nhưng khi chuyển sang server dùng `1` hoặc `2`, hai tên đó được xem là một tên. Điều này có thể tạo xung đột khi restore hoặc migration.

Các vấn đề thường gặp gồm:

- Script migration tạo `Customer`, trong khi code ORM truy cập `customer`.
- Máy phát triển Windows chấp nhận câu truy vấn sai kiểu chữ nhưng môi trường Linux production từ chối.
- Một dump chứa hai bảng chỉ khác kiểu chữ không thể restore nguyên trạng vào môi trường không phân biệt hoa thường.
- Công cụ triển khai, backup hoặc đồng bộ file xử lý tên đối tượng khác nhau giữa các nền tảng.
- Source và replica dùng cấu hình khác nhau có thể xử lý tên bảng không nhất quán, dẫn đến lỗi hoặc dữ liệu không được áp dụng như mong muốn.

Quy ước an toàn cho dự án đa môi trường là đặt database và table name bằng chữ thường, dùng `snake_case`, ví dụ `sales_order`, `customer_profile`, `order_item`. Không tạo hai bảng chỉ khác chữ hoa/chữ thường. Dùng cùng quy ước trong DDL, migration, code Java, ORM mapping, báo cáo và script vận hành.

## 8. `lower_case_table_names` trong MySQL 8.0

Một điểm vận hành rất quan trọng: trong MySQL 8.0, `lower_case_table_names` phải được xác định khi khởi tạo data directory. Sau khi server đã được khởi tạo, không thể đổi giá trị này như một biến cấu hình runtime thông thường.

Điều này có nghĩa là:

- Không thể an toàn đổi một server đang chạy từ `0` sang `1` chỉ bằng `SET GLOBAL` hoặc sửa cấu hình rồi restart.
- Nếu cần đổi chế độ, phải lập kế hoạch tạo instance mới với cấu hình phù hợp, sau đó migrate dữ liệu theo quy trình có kiểm soát.
- Giá trị phải tương thích với đặc tính filesystem nơi đặt datadir. MySQL có thể từ chối khởi động nếu cấu hình không được hỗ trợ trên filesystem đó.
- Cần xem xét tất cả tên database/table hiện tại để tìm xung đột trước khi chuyển dữ liệu.

Để kiểm tra file cấu hình khởi động, người quản trị có thể xem cấu hình MySQL server đang sử dụng. Ví dụ trong file cấu hình:

```ini
[mysqld]
lower_case_table_names=1
```

Đây chỉ là ví dụ cấu hình cho một instance mới trên filesystem không phân biệt hoa thường. Không thêm hoặc đổi dòng này trên datadir đã khởi tạo rồi kỳ vọng MySQL sẽ tự chuyển đổi metadata. Hãy xác minh hướng dẫn theo đúng phiên bản và quy trình cài đặt trước khi tạo instance.

## 9. Di chuyển dữ liệu giữa Windows, macOS và Linux

Khi chuyển môi trường, không chỉ kiểm tra phiên bản MySQL và charset. Cần kiểm tra cả giá trị `lower_case_table_names` ở nguồn và đích.

Quy trình chuẩn bị migration:

1. Ghi lại `SELECT VERSION()` và `SELECT @@GLOBAL.lower_case_table_names` trên server nguồn và server đích.
2. Liệt kê database/table name từ metadata, tìm các cặp chỉ khác nhau về chữ hoa/chữ thường.
3. Kiểm tra script DDL, migration và mapping entity trong ứng dụng có dùng một cách viết thống nhất không.
4. Nếu đích không phân biệt hoa thường, xử lý xung đột tên trước khi import; đổi tên có kế hoạch và cập nhật toàn bộ tham chiếu.
5. Restore vào môi trường thử nghiệm, chạy kiểm tra schema và integration test từ đúng nền tảng đích.
6. Chỉ chuyển production sau khi backup, kế hoạch rollback và thời gian downtime hoặc cơ chế đồng bộ đã được thống nhất.

Ví dụ truy vấn metadata để rà tên bảng trong một schema:

```sql
SELECT TABLE_SCHEMA, TABLE_NAME
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'CaseLab'
ORDER BY TABLE_NAME;
```

Truy vấn này liệt kê tên bảng đúng như metadata cung cấp. Để tìm tên có khả năng xung đột khi chuyển sang chế độ không phân biệt hoa thường, có thể xuất danh sách và chuẩn hóa về chữ thường trong công cụ kiểm tra migration. Cần giữ nguyên tên gốc để xác định đối tượng cần đổi; không tự động đổi tên khi chưa kiểm tra khóa ngoại, view, trigger, routine và code tham chiếu.

Không đổi tên thư mục hoặc file trong `datadir` bằng File Explorer, `mv` hay công cụ đồng bộ. MySQL quản lý metadata và các file lưu trữ; thao tác trực tiếp trên thư mục dữ liệu có thể làm hỏng instance hoặc khiến data dictionary không còn khớp với file. Dùng DDL hoặc quy trình dump/restore, migration được hỗ trợ.

## 10. Replication và môi trường nhiều máy chủ

Với replication, source và replica nên có cùng quy tắc chữ hoa/chữ thường cho tên database/table. Nếu source cho phép hai bảng `Customer` và `customer` nhưng replica xem chúng là cùng một tên, thao tác DDL hoặc DML được sao chép có thể gặp xung đột.

Khi thiết kế topology MySQL, cần:

- Chuẩn hóa tên database và table trước khi bật replication.
- Kiểm tra `@@GLOBAL.lower_case_table_names` trên tất cả node liên quan.
- Không tạo tên đối tượng chỉ khác hoa/thường trên source nếu replica hoặc nền tảng đích không thể biểu diễn riêng hai tên đó.
- Kiểm tra DDL và quy trình restore trên một replica thử nghiệm trước khi áp dụng thay đổi lớn.
- Giữ quy tắc nhất quán giữa môi trường phát triển, kiểm thử, staging và production.

Việc giữ cùng giá trị cấu hình không tự giải quyết mọi vấn đề replication, nhưng là điều kiện quan trọng để tên đối tượng được diễn giải nhất quán. Nếu đang có topology chạy khác cấu hình, cần đánh giá và lập kế hoạch di chuyển riêng thay vì thay đổi biến trên một node đang hoạt động.

## 11. Quy ước đặt tên cho ứng dụng Java

Ứng dụng Java thường truy cập database qua JDBC, JPA hoặc ORM như Hibernate. Mapping tên bảng có thể được khai báo trực tiếp hoặc sinh từ naming strategy. Nếu code và DDL không thống nhất kiểu chữ, lỗi có thể chỉ xuất hiện khi chạy trên môi trường có quy tắc phân biệt hoa thường.

Ví dụ entity:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer_profile")
public class CustomerProfile {
    @Id
    private Long id;

    private String fullName;
}
```

DDL tương ứng:

```sql
CREATE TABLE customer_profile (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL
);
```

Trong ví dụ này, tên bảng trong `@Table` và DDL đều dùng `customer_profile`. Hãy áp dụng nhất quán cho các entity khác, native query, stored procedure và script migration. Nếu dùng naming strategy tự động, hãy xác nhận tên SQL cuối cùng mà ORM phát ra bằng log SQL hoặc integration test.

## 12. Checklist kiểm tra khi gặp lỗi sai chữ hoa/thường

Khi nhận lỗi `Table doesn't exist` hoặc `Unknown database` chỉ xuất hiện ở một môi trường, hãy kiểm tra theo thứ tự:

1. Xác nhận ứng dụng đang kết nối đúng server và database bằng `SELECT @@hostname, DATABASE(), VERSION();`.
2. Đọc `SELECT @@GLOBAL.lower_case_table_names;` trên chính server đó.
3. Dùng `SHOW TABLES` hoặc `INFORMATION_SCHEMA.TABLES` để lấy tên đối tượng thực tế.
4. So sánh kiểu chữ trong DDL, migration, ORM mapping và SQL đang chạy.
5. Xác định filesystem/datadir và chế độ case-sensitive hay case-insensitive của môi trường máy chủ.
6. Kiểm tra có hai tên chỉ khác chữ hoa/thường trong schema hoặc trong dump không.
7. Nếu liên quan đến migration/replication, so sánh cấu hình trên cả nguồn và đích trước khi sửa.

Không sửa lỗi bằng cách đổi `lower_case_table_names` trên một instance đã khởi tạo hoặc đổi tên file trực tiếp trong datadir. Hãy thống nhất quy ước tên, chuẩn bị migration và kiểm chứng trên môi trường thử nghiệm.

## 13. Bài tập thực hành

1. Chạy `SELECT VERSION(), @@GLOBAL.lower_case_table_names;` trên MySQL local và ghi lại kết quả.
2. Tạo schema `CaseLab` và bảng `Customer` trong một môi trường thử nghiệm riêng.
3. Thử truy vấn bảng bằng đúng và khác kiểu chữ; giải thích kết quả dựa trên giá trị `lower_case_table_names`.
4. Xem tên đối tượng bằng `SHOW TABLES` và `INFORMATION_SCHEMA.TABLES`.
5. So sánh cách viết tên bảng trong DDL với `@Table` hoặc mapping của ORM trong một ứng dụng Java.
6. Mô phỏng một migration có bảng `Customer` và `customer`; xác định vì sao có thể xung đột khi restore sang môi trường không phân biệt hoa thường.
7. Đề xuất quy ước tên database/table có thể dùng nhất quán trên Windows, macOS và Linux.

Bạn hoàn thành bài khi giải thích được filesystem ảnh hưởng thế nào đến tên database/table, phân biệt được ba giá trị `lower_case_table_names`, biết cách kiểm tra cấu hình của server và dự đoán rủi ro khi di chuyển dữ liệu. Quy ước tên chữ thường, `snake_case` và thống nhất cấu hình giữa các node giúp tránh phần lớn lỗi portability liên quan đến chữ hoa/chữ thường.
