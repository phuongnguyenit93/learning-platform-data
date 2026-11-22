# Vì sao lược đồ và định dạng lưu trữ phải thay đổi theo thời gian

Dữ liệu bền vững thường sống lâu hơn phiên bản ứng dụng Java đã tạo ra nó. Một hệ thống lúc mới vận hành chỉ bán hàng bằng đồng Việt Nam có thể sau này cần nhiều đồng tiền. Một bảng lưu địa chỉ trong một chuỗi văn bản có thể không còn phù hợp khi cần lọc theo quốc gia và mã bưu chính. Một sự kiện JSON đã lưu nhiều tháng trước có thể được phát lại cho một consumer mới. Các chỉ mục, ràng buộc, hình thức nén và yêu cầu mã hóa cũng phải thay đổi theo khối lượng dữ liệu, hành vi truy vấn và quy định bảo mật.

**Tiến hóa dữ liệu** (*data evolution*) là việc thay đổi một cách có kiểm soát mô hình, ràng buộc và biểu diễn dữ liệu qua nhiều phiên bản hệ thống, đồng thời giữ nguyên các bất biến nghiệp vụ và khả năng đọc/ghi dữ liệu lịch sử.

Trong bài này:

- **Lược đồ (schema)** chỉ định bảng, cột, kiểu dữ liệu, khóa, ràng buộc, quan hệ và các cấu trúc mà truy vấn phụ thuộc.
- **Định dạng lưu trữ (storage/serialization format)** xác định cách dữ liệu được mã hóa hoặc đóng gói, như JSON, Protobuf, Avro, file nhị phân, payload sự kiện, bản ghi cache và cấu trúc lưu trữ do DBMS quản lý.
- **Hợp đồng dữ liệu (data contract)** mô tả ý nghĩa, đơn vị đo, trường bắt buộc, quyền sở hữu, bảo đảm nhất quán và yêu cầu tương thích giữa các thành phần.

Bài thuộc chương **Tiến hóa dữ liệu** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**. Người học kết nối thiết kế persistence cho Java với mô hình quan hệ, truy vấn và chỉ mục, giao dịch, cô lập, bảo mật, sao lưu, tối ưu hiệu năng và vòng đời dữ liệu.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích các nguyên nhân nghiệp vụ, kỹ thuật và vận hành khiến schema và format phải đổi.
2. Phân biệt thay đổi **cấu trúc**, **ngữ nghĩa**, **kiểu dữ liệu**, **serialization** và **lưu trữ vật lý**.
3. Phân tích khả năng tương thích giữa code cũ, code mới, dữ liệu cũ và dữ liệu mới.
4. Lập kế hoạch **expand → deploy compatible readers/writers → backfill → verify → contract**.
5. Viết migration theo lô có thể chạy lại, không ghi đè dữ liệu mới và có checkpoint.
6. Thiết kế chuyển đổi event/cache/search index có version, không phá khả năng replay.
7. Nhận diện ảnh hưởng của DDL lên khóa, transaction, chỉ mục, rollback và backup.
8. Kiểm thử, giám sát và vận hành một thay đổi dữ liệu an toàn dưới tải thực.

## 2. Mã ứng dụng ngắn hạn; dữ liệu có vòng đời dài

Một bản Java có thể được nâng cấp trong một lượt deploy, nhưng:

- Hàng trong database có thể được tạo từ nhiều năm trước.
- Backup và transaction log có thể giữ dữ liệu theo cấu trúc cũ.
- Một số replica, worker hoặc client mobile còn dùng phiên bản trước.
- Event queue, cache, search index và báo cáo có thể chứa bản sao hoặc payload cũ.
- Dữ liệu lịch sử có thể từng hợp lệ nhưng không còn phù hợp quy tắc mới.

~~~text
Thời gian ------------------------------------------------------------>

Ứng dụng:  v1 --------- v2 --------- v3 --------- v4
Dữ liệu:   |v1 records|v1 + v2 records| dữ liệu v1 vẫn có thể còn |
Consumer:  c1 -------- c1 + c2 ---------- c2
Event log: E(v1), E(v1), E(v2), E(v3) ... có thể được replay
Backup:    snapshot s1        snapshot s2
~~~

Từ đó xuất hiện ba yêu cầu:

1. **Code mới phải hiểu dữ liệu cũ:** không thể giả định mọi hàng đã được viết theo schema mới.
2. **Code cũ và mới có thể cùng tồn tại:** rolling deployment và rollback không thể làm câu SQL cũ hỏng ngay.
3. **Dữ liệu mới phải phù hợp với đường khôi phục:** nếu code cũ không hiểu bản ghi mới, rollback code có thể làm sai nghiệp vụ dù không có lỗi SQL.

Một migration được đánh dấu là đã chạy trong Flyway/Liquibase **không chứng minh** mọi hàng đã được backfill; trạng thái schema và trạng thái dữ liệu là hai điều cần kiểm chứng riêng.

## 3. Vì sao hệ thống cần thay đổi lược đồ?

### 3.1. Nghiệp vụ phát triển

Ví dụ ban đầu bảng đơn hàng chỉ lưu tổng tiền:

~~~sql
CREATE TABLE orders (
    id           BIGINT PRIMARY KEY,
    total_amount NUMERIC(18, 2) NOT NULL CHECK (total_amount >= 0),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Khi mọi đơn đều là VND, ứng dụng có thể ngầm hiểu `total_amount = 250000` nghĩa là 250.000 đồng. Khi hỗ trợ USD, EUR và các loại tiền khác, chỉ giá trị `250000` không còn đủ nghĩa; cần thêm `currency` và xem lại quy tắc quy đổi, làm tròn, lập hóa đơn.

Các ví dụ khác:

- Từ một địa chỉ khách hàng sang nhiều địa chỉ giao hàng.
- Từ một lần thanh toán sang nhiều giao dịch thanh toán và hoàn tiền.
- Từ một trạng thái đơn giản sang lịch sử trạng thái có kiểm toán.
- Từ ứng dụng một tenant sang nhiều tenant với quyền truy cập riêng.
- Từ chỉ một ngôn ngữ sang nội dung đa ngôn ngữ.

**Thay schema thường chỉ là một phần của thay đổi nghiệp vụ.** Nếu đã có đơn lịch sử, cần xác định ý nghĩa của từng trường cũ trước khi chuyển đổi.

### 3.2. Dữ liệu tăng về kích thước và truy vấn đổi dạng

Một bảng vài nghìn hàng có thể chạy ổn khi thiếu chỉ mục. Khi có hàng trăm triệu hàng:

- Những câu `SELECT` quét bảng trở nên đắt.
- Cần index theo điều kiện lọc và `ORDER BY` thực tế.
- Có thể cần partition theo thời gian, tenant hoặc khóa phù hợp.
- Dữ liệu cũ có thể phải lưu ở tier giá rẻ, với quy tắc truy vấn và khôi phục mới.
- Báo cáo nặng có thể cần bảng tổng hợp, materialized view hoặc kho phân tích.

Đây là tiến hóa **cấu trúc truy cập hoặc lưu trữ**, có thể không đổi API công khai. Nhưng một chỉ mục mới cũng tốn chi phí ghi và bộ nhớ; partition không tự giải quyết mọi truy vấn chậm. Cần đo `EXPLAIN`, tải thực và chi phí vận hành trước khi đổi.

### 3.3. Cần bảo vệ dữ liệu tốt hơn

Một hệ thống có thể phát hiện cột đang cho phép trạng thái không hợp lệ:

- Thiếu `UNIQUE` nên có khách hàng trùng mã.
- Thiếu `FOREIGN KEY` nên tồn tại dòng con mồ côi.
- `NULL` từng được cho phép nhưng nghiệp vụ nay bắt buộc có giá trị.
- Kiểu `INTEGER` sắp vượt giới hạn.
- Cột timestamp không rõ múi giờ.
- Các thay đổi concurrent bị ghi đè do thiếu version/locking.

Tăng ràng buộc database giúp bảo vệ cả các đường ghi không đi qua Java. Tuy nhiên, nếu dữ liệu hiện tại đã vi phạm ràng buộc, trước tiên phải **phát hiện và làm sạch dữ liệu**; thêm constraint trực tiếp thường thất bại hoặc gây gián đoạn.

### 3.4. Tuân thủ bảo mật và vòng đời dữ liệu

Lúc đầu một trường có thể được lưu dạng văn bản thuần; sau đó phải được mã hóa, token hóa, giới hạn truy cập hoặc xóa theo thời hạn lưu trữ. Thay đổi này liên quan nhiều nơi:

- Bảng chính, bản sao đọc, materialized view.
- Log và sự kiện chứa snapshot.
- Backup và file xuất.
- Chỉ mục tìm kiếm và cache.
- Quy trình rotate khóa mã hóa.

Đổi từ `identity_number TEXT` sang giá trị mã hóa không chỉ là `ALTER COLUMN`. Cần giữ khả năng đọc dữ liệu cũ, chuyển dữ liệu theo lô, kiểm tra quyền truy cập và tránh ghi lại bản rõ trong log.

### 3.5. Sửa mô hình thiết kế ban đầu

Một ứng dụng có thể lưu địa chỉ thành JSON:

~~~sql
CREATE TABLE customer_profiles (
    customer_id BIGINT PRIMARY KEY,
    details     JSONB NOT NULL
);
~~~

Nếu sau này cần quan hệ một–nhiều, kiểm tra mã vùng hoặc tìm kiếm theo thành phố, có thể tạo bảng:

~~~sql
CREATE TABLE customer_addresses (
    id           BIGINT PRIMARY KEY,
    customer_id  BIGINT NOT NULL,
    city         TEXT NOT NULL,
    postal_code  TEXT,
    address_type TEXT NOT NULL
);
~~~

Nhưng dữ liệu JSON lịch sử có thể thiếu `city`, có nhiều địa chỉ hoặc chứa định dạng chưa chuẩn. Thao tác chuyển đổi cần logic nghiệp vụ và hàng đợi ngoại lệ; không thể chỉ copy toàn bộ JSON sang cột mới.

## 4. Phân biệt cấu trúc, định dạng và ngữ nghĩa

| Tầng | Ví dụ thay đổi | Điều cần giữ đúng |
|---|---|---|
| **Schema logic** | Thêm cột, tách bảng, thêm FK | Hợp đồng truy vấn và bất biến |
| **Ý nghĩa dữ liệu** | `amount` từ VND mặc định sang đa tiền tệ | Đơn vị tính, giải thích dữ liệu cũ |
| **Kiểu dữ liệu** | `INTEGER` → `BIGINT`; `DOUBLE` → `NUMERIC` | Miền giá trị, precision, overflow |
| **Serialization** | JSON v1 → v2, Protobuf thêm field | Khả năng đọc dữ liệu/event lịch sử |
| **Cơ chế truy cập** | Index, partition, materialized view | Hiệu năng, khóa, chi phí ghi |
| **Vật lý DBMS** | Nén, cấu trúc trang, file format sau nâng cấp | Khả năng backup/restore/upgrade |
| **Mã hóa** | Đổi key, thuật toán hoặc cách lưu ciphertext | Giải mã giá trị cũ, bảo mật |
| **Dữ liệu dẫn xuất** | Search document/cache DTO có trường mới | Đồng bộ và rebuild projection |

### 4.1. Không đổi schema mà đổi ý nghĩa vẫn nguy hiểm

Giả sử cột `amount BIGINT` trước đây lưu **đồng nhỏ nhất**, nhưng bản mới bắt đầu coi cùng số nguyên là **đơn vị tiền chính**. Database vẫn nhận giá trị hợp lệ, SQL không lỗi, nhưng nghiệp vụ tính sai theo hệ số 100 hoặc 1000.

**Schema validation không bắt được thay đổi ngữ nghĩa.** Cần mô tả đơn vị đo, quy tắc round, version, migration và các phép đối chiếu số liệu.

### 4.2. Format của DBMS khác format do ứng dụng sở hữu

PostgreSQL hay một DBMS khác quản lý cách lưu trang, WAL và index vật lý. Ứng dụng thường không trực tiếp viết từng trang dữ liệu. Khi nâng cấp engine, phải theo quy trình vendor hỗ trợ: compatibility của file, replication, backup, extension và tooling.

Ngược lại JSON/Avro/Protobuf là những format do ứng dụng và hệ tích hợp quản lý. **Schema migration SQL** và **upgrade định dạng vật lý của engine** là hai quy trình khác nhau, dù đều ảnh hưởng dữ liệu bền vững.

## 5. Tương thích giữa code cũ và mới

Trước khi deploy, xét ma trận:

| Reader | Writer / dữ liệu | Câu hỏi kiểm thử |
|---|---|---|
| v1 | v1 | Các chức năng cũ còn đúng? |
| v2 | v1 | Reader mới có hiểu hàng lịch sử? |
| v1 | v2 | Reader cũ có hiểu các giá trị mới trong lúc rolling deploy? |
| v2 | v2 | Chức năng mới có đúng với schema mới? |

Bổ sung một cột nullable thường dễ triển khai hơn xóa cột đang được dùng. Nhưng **thêm field JSON cũng không tự đảm bảo tương thích** nếu consumer cũ không cho phép field không biết.

Các thay đổi có nguy cơ phá vỡ:

- Xóa hoặc đổi tên cột mà instance cũ còn truy vấn.
- Siết `NOT NULL` trong khi writer cũ vẫn gửi thiếu trường.
- Thu hẹp kiểu số và làm mất dữ liệu cũ.
- Đổi ý nghĩa giá trị dù tên cột không đổi.
- Đổi tên field event bắt buộc.
- Thay enum ordinal khiến dữ liệu lưu số đổi nghĩa.
- Đổi khóa chính trong khi cache, URL, event và bảng con còn tham chiếu khóa cũ.

Thay vì nói đơn giản “backward compatible”, hãy ghi rõ **reader phiên bản nào đọc dữ liệu writer phiên bản nào**. Thuật ngữ backward/forward compatibility có thể khác cách diễn đạt giữa công nghệ và vai trò producer/consumer.

## 6. Case study: thêm tiền tệ vào hệ thống chỉ xử lý VND

Giả sử bảng `orders` đang có `total_amount NUMERIC(18,2)`; tất cả hàng lịch sử và writer v1 **đã được xác minh** chỉ tạo đơn VND. Nhu cầu mới là hỗ trợ đa tiền tệ.

### 6.1. Sai lầm: sửa schema và bật tính năng ngay

~~~text
App v1: đọc total_amount, luôn coi là VND
App v2: đọc total_amount + currency
DB chưa có currency -> v2 lỗi

Hoặc:
App v2 tạo USD trong khi v1 còn hoạt động.
App v1 đọc đơn USD nhưng diễn giải là VND -> sai nghiệp vụ.
~~~

Ngay cả khi SQL không lỗi, hệ thống đã vi phạm hợp đồng dữ liệu. Cần **gated rollout**: cấu trúc và code có thể nâng trước, hành vi tạo dữ liệu mới chỉ bật khi các consumer/reader đã sẵn sàng.

### 6.2. EXPAND: thêm cột nhưng giữ tương thích

PostgreSQL:

~~~sql
ALTER TABLE orders
ADD COLUMN currency VARCHAR(3);
~~~

Code cũ có thể tiếp tục đọc những cột đã biết. Code mới phải chấp nhận `currency IS NULL` ở các hàng cũ.

Nếu đã xác minh mọi writer cũ chỉ tạo đơn VND, có thể đặt default để các lệnh INSERT không cung cấp currency trong giai đoạn chuyển tiếp vẫn mang nghĩa đúng:

~~~sql
ALTER TABLE orders
ALTER COLUMN currency SET DEFAULT 'VND';
~~~

**Lưu ý:** `SET DEFAULT` không tự backfill các hàng đã tồn tại và còn null. Không áp dụng default VND nếu có bất kỳ đường ghi cũ nào có thể tạo đơn bằng loại tiền tệ khác.

DDL trên bảng lớn vẫn có thể đợi khóa của transaction khác; “thêm cột” không đồng nghĩa tuyệt đối không cần lập kế hoạch về lock. Cần đo theo DBMS, phiên bản và tải đang chạy.

### 6.3. Reader mới có fallback được kiểm chứng

~~~java
import java.math.BigDecimal;
import java.sql.ResultSet;
import java.sql.SQLException;

public record MonetaryAmount(BigDecimal amount, String currency) {}

public MonetaryAmount toMoney(ResultSet rows) throws SQLException {
    String currency = rows.getString("currency");

    if (currency == null) {
        // Chỉ an toàn nếu đã xác minh đơn cũ thực sự là VND.
        currency = "VND";
    }

    return new MonetaryAmount(
        rows.getBigDecimal("total_amount"),
        currency
    );
}
~~~

Đây là ví dụ logic ánh xạ; `toMoney` cần đặt trong class Java thích hợp. Với tiền, dùng `BigDecimal` thay vì ép qua `double` nếu cần biểu diễn thập phân chính xác. Danh mục currency được hỗ trợ, precision, rounding và quy tắc tính tiền phải được thiết kế ở tầng nghiệp vụ.

Khi còn reader v1 mặc định VND, **không cho ghi đơn USD**. Fallback không thay thế kiểm soát hành vi writer.

### 6.4. BACKFILL: chuyển dữ liệu lịch sử theo lô

Khi biết rõ toàn bộ đơn cũ là VND:

~~~sql
-- PostgreSQL: chạy nhiều lượt, mỗi lượt là một transaction ngắn.
WITH chunk AS (
    SELECT id
    FROM orders
    WHERE currency IS NULL
    ORDER BY id
    LIMIT 1000
    FOR UPDATE SKIP LOCKED
)
UPDATE orders AS o
SET currency = 'VND'
FROM chunk
WHERE o.id = chunk.id
RETURNING o.id;
~~~

Câu này chỉ cập nhật hàng còn `NULL` tại thời điểm lấy khóa. Các điểm vận hành quan trọng:

1. Chạy batch có giới hạn, không mặc định dùng một transaction cho hàng triệu hàng.
2. Chỉ sửa hàng cần chuyển, tránh ghi đè currency đã được writer mới điền.
3. Theo dõi số hàng còn thiếu, lock wait, WAL/redo, replication lag và độ trễ SQL.
4. Dừng, retry hoặc điều chỉnh batch size khi database có dấu hiệu quá tải.
5. Đảm bảo writer mới không còn tạo hàng null ngoài chủ ý; nếu không backfill sẽ không bao giờ hoàn tất.
6. Quét lại những hàng bị `SKIP LOCKED` bỏ qua hoặc phát sinh trong lúc chạy.

Nếu dữ liệu lịch sử có bản ghi **không xác định được currency**, đừng tự điền VND chỉ để đạt số hàng null bằng 0. Đây là ngoại lệ cần đối soát và quyết định nghiệp vụ.

### 6.5. VERIFY và CONTRACT

Sau khi backfill, kiểm tra:

~~~sql
SELECT COUNT(*) AS missing_currency
FROM orders
WHERE currency IS NULL;

SELECT currency, COUNT(*) AS row_count
FROM orders
GROUP BY currency
ORDER BY row_count DESC;
~~~

Nếu đã xác minh các writer đều ghi hợp lệ, có thể đưa ràng buộc vào schema:

~~~sql
ALTER TABLE orders
ADD CONSTRAINT orders_currency_format
CHECK (currency ~ '^[A-Z]{3}$') NOT VALID;

ALTER TABLE orders
VALIDATE CONSTRAINT orders_currency_format;
~~~

Trong PostgreSQL, `CHECK` theo biểu thức trên không từ chối `NULL`, bởi biểu thức kiểm tra trả UNKNOWN được chấp nhận. Để thực sự bắt buộc có currency:

~~~sql
ALTER TABLE orders
ALTER COLUMN currency SET NOT NULL;
~~~

Bước `SET NOT NULL` có yêu cầu lock/kiểm tra dữ liệu riêng; trên bảng lớn cần đánh giá trước. `NOT VALID` là kỹ thuật PostgreSQL dùng cho một số constraint, không có nghĩa nó bỏ kiểm tra tất cả hàng mới sau khi tạo. Chỉ thêm constraint tại thời điểm reader/writer và dữ liệu lịch sử đã sẵn sàng.

Khi không còn v1 hoặc consumer nào hiểu `total_amount` như VND mặc định, mới bật tính năng đa tiền tệ. Bỏ fallback/default cũ về sau là quyết định riêng, dựa trên hợp đồng với API và dữ liệu lịch sử.

### 6.6. Rollback có thể trở nên nguy hiểm sau điểm bật tính năng

Nếu v2 đã ghi đơn USD, đưa lại v1 mặc định mọi đơn là VND sẽ làm sai dữ liệu dù cột `total_amount` vẫn tồn tại. Vì vậy:

- Giữ feature flag trong giai đoạn còn khả năng rollback v1.
- Sau khi mở tính năng, chuẩn bị đường **roll-forward** sửa v2.
- Hoặc chỉ rollback về một phiên bản cũ đã được vá để xử lý currency mới đúng.
- Không dùng `DROP COLUMN currency` như cách “quay về trước” sau khi dữ liệu ngoại tệ đã tồn tại.

Đây là khác biệt giữa **rollback code** và **rollback ngữ nghĩa dữ liệu**.

## 7. Expand → migrate → contract cho thay đổi khác

~~~mermaid
flowchart LR
    A["Schema cũ"] --> B["Expand: thêm cấu trúc tương thích"]
    B --> C["Reader/writer mới hỗ trợ cả hai dạng"]
    C --> D["Backfill hoặc đồng bộ chuyển tiếp"]
    D --> E["Verify invariant và ngừng writer cũ"]
    E --> F["Contract: bỏ format/field cũ"]
~~~

Thay đổi từ `customers.full_name` sang `display_name` là ví dụ:

1. Thêm cột `display_name` nullable.
2. Reader mới ưu tiên cột mới, fallback cột cũ.
3. Xác định **một cơ chế đồng bộ có thẩm quyền** trong lúc writer cũ và mới cùng tồn tại; có thể dùng một write service hoặc trigger được kiểm soát.
4. Backfill không ghi đè thay đổi mới.
5. Kiểm tra hai trường tương đương về ngữ nghĩa, không còn consumer cũ.
6. Chỉ khi đó bỏ `full_name`.

Lệnh `ALTER TABLE ... RENAME COLUMN` trực tiếp có thể phá code cũ ngay trong rolling deploy. Nếu dual-write cả hai cột ở nhiều nơi mà không có quy tắc phân giải xung đột, cập nhật đồng thời có thể khiến hai bản sao khác nhau.

### 7.1. Chuyển chuỗi địa chỉ sang bảng quan hệ

Chuyển `orders.shipping_address_text` sang bảng địa chỉ riêng còn phức tạp hơn đổi tên cột:

- Chuỗi cũ có thể thiếu quốc gia, mã bưu chính hoặc có nhiều định dạng.
- Một đơn có thể cần nhiều loại địa chỉ.
- Cần quy định identity, khóa ngoại, unique và nguồn có thẩm quyền.
- Backfill cần phát hiện những hàng không thể parse chắc chắn.
- Nếu code cũ tiếp tục ghi chuỗi, dữ liệu mới phải được đồng bộ hoặc tái đọc phù hợp.

Không tự bịa thành phố hoặc mã bưu chính từ chuỗi lịch sử để đáp ứng constraint mới. Chấp nhận một trạng thái chuyển tiếp có kiểm soát thường tốt hơn “chuẩn hóa” sai dữ liệu.

## 8. Backfill là thao tác ghi có cạnh tranh

Backfill chạy trên database production là một **writer**: nó chịu rủi ro deadlock, lock wait, thay đổi đồng thời và mất kết nối giống như ứng dụng.

### 8.1. Lỗi ghi đè từ snapshot cũ

~~~text
T1 (backfill): đọc hàng 42 ở trạng thái cũ
T2 (API):      cập nhật hàng 42 với giá trị mới
T1 (backfill): ghi lại dữ liệu chuyển từ snapshot cũ

Rủi ro: T1 ghi đè thay đổi của T2 nếu không có điều kiện bảo vệ.
~~~

Các cách phòng tránh tùy quy tắc:

- Chỉ cập nhật khi cột đích vẫn null: `WHERE target IS NULL`.
- Kiểm tra version: `WHERE version = :observedVersion`.
- Tính từ cột nguồn **ngay trong SQL UPDATE** trên hàng đã khóa khi phù hợp.
- Dùng transaction ngắn và khóa rõ ràng cho dữ liệu phải cập nhật.
- Quy định writer mới cập nhật định dạng chuyển tiếp đúng cách.

Không có một truy vấn chung giải quyết mọi race: điều quan trọng là phát biểu **bất biến migration** và kiểm chứng với lịch chạy đồng thời.

### 8.2. Idempotent batching

Ví dụ chuyển sang bảng mới:

~~~sql
CREATE TABLE order_addresses_new (
    order_id BIGINT PRIMARY KEY,
    address_text TEXT NOT NULL
);
~~~

Một lượt chèn dữ liệu theo khoảng khóa:

~~~sql
INSERT INTO order_addresses_new (order_id, address_text)
SELECT id, shipping_address_text
FROM orders
WHERE id >= :start_id
  AND id < :end_id
  AND shipping_address_text IS NOT NULL
ON CONFLICT (order_id) DO NOTHING;
~~~

Các tham số `:start_id`, `:end_id` dùng ký hiệu của thư viện hỗ trợ named parameters; JDBC `PreparedStatement` thuần phải thay bằng `?` và bind đúng thứ tự. `ON CONFLICT DO NOTHING` giúp tránh nhân đôi khi chạy lại nhưng **không đồng bộ thay đổi mới của hàng đã chèn**. Vấn đề catch-up cần cơ chế riêng.

### 8.3. Checkpoint phải tương ứng công việc đã commit

Nếu job ghi “đã đến ID 5000” trước khi commit batch chứa ID 4900–5000, khi crash có thể bỏ qua hàng chưa chuyển. Checkpoint cần được ghi **sau khi batch commit** hoặc được thiết kế nhất quán cùng đơn vị ghi.

Cần xét cả:

- Tạo ID mới trong lúc quét.
- ID thấp được chèn muộn hoặc cập nhật trong lúc backfill.
- Hàng bị bỏ qua do `SKIP LOCKED`.
- Dữ liệu không thể chuyển vì không hợp lệ.
- Thao tác transform không idempotent cần operation ID/ledger.

Không dùng phân trang `OFFSET` thiếu tính ổn định trên bảng thường xuyên thay đổi để mặc định bảo đảm không bỏ sót. Keyset batching, snapshot + CDC, hoặc quét bù cần được lựa chọn theo mô hình dữ liệu thực.

### 8.4. Đánh đổi giữa một transaction lớn và nhiều batch

Một transaction lớn có thể đảo toàn bộ thay đổi nếu lỗi, nhưng có thể giữ khóa lâu, gây WAL lớn, tăng thời gian rollback và làm cạn connection pool. Chia thành nhiều batch giúp kiểm soát tài nguyên nhưng **không còn nguyên tử cho toàn bộ tập dữ liệu**.

Vì vậy trong giai đoạn backfill một phần, code đọc/ghi phải hiểu cả hai dạng dữ liệu. Không được đặt `NOT NULL` hoặc xóa đường đọc cũ trước khi backfill hoàn tất và được xác minh.


## 9. Đổi kiểu dữ liệu phải giữ nguyên ý nghĩa và precision

Thay đổi kiểu dữ liệu có thể rất dễ ở Java code nhưng khó ở dữ liệu lịch sử. Cần phân biệt **mở rộng miền giá trị** với **chuyển đổi cách diễn giải**.

### 9.1. `INTEGER` sang `BIGINT`

Khi ID hoặc bộ đếm tăng tới giới hạn `INTEGER`, có thể cần chuyển sang `BIGINT`. Nhưng tác động không chỉ nằm ở một cột:

- Field Java `int/Integer` phải được xem lại để dùng `long/Long`.
- Foreign key ở các bảng liên quan và sequence sinh ID phải tương thích.
- REST API, event, cache key và công cụ xuất dữ liệu có thể đang dùng kiểu số nhỏ.
- Consumer JavaScript có giới hạn chính xác cho số nguyên dưới cách biểu diễn `Number`.
- DDL có thể rewrite/index lại dữ liệu và lấy khóa theo cách riêng của DBMS.

Chỉ đổi `orders.id` thành `BIGINT` mà các repository vẫn ép về `int` không giải quyết vấn đề tràn số ở lớp ứng dụng.

### 9.2. `FLOAT/DOUBLE` sang `NUMERIC/DECIMAL`

Một hệ thống tiền tệ có thể cần chuyển từ số dấu phẩy động nhị phân sang biểu diễn thập phân. Với Java:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal amount = new BigDecimal("123.45");
BigDecimal tax = amount.multiply(new BigDecimal("0.10"))
                       .setScale(2, RoundingMode.HALF_UP);
~~~

Ví dụ `HALF_UP` chỉ minh họa một quy tắc làm tròn; nghiệp vụ tài chính/thuế thực tế phải định nghĩa rõ loại tiền tệ, precision, scale và rounding.

Trong migration cần:

1. Kiểm tra dữ liệu cũ có sai số từ phép tính `double` hay không.
2. Quy định cách chuyển về `NUMERIC(p,s)`, tránh làm tròn tùy tiện.
3. So sánh tổng và chi tiết theo đơn vị tiền tệ nhất quán.
4. Bảo vệ dữ liệu đã quyết toán hoặc đã xuất hóa đơn khỏi biến đổi không được phép.
5. Kiểm thử dữ liệu biên, số âm, overflow và số lẻ nhiều chữ số.

Một câu `CAST` thành công không chứng minh giá trị mới giữ nguyên ý nghĩa kế toán.

### 9.3. Timestamp và múi giờ

Nếu dữ liệu cũ lưu `TIMESTAMP WITHOUT TIME ZONE`, giá trị `2026-03-01 09:00:00` có thể biểu thị giờ địa phương nhưng không chứa thông tin vùng. Khi chuyển sang kiểu biểu diễn thời điểm tuyệt đối:

- Phải biết giá trị cũ thuộc múi giờ nào.
- Nếu hệ thống từng chạy ở nhiều vùng, có thể phải xét nguồn tạo dữ liệu.
- Quy tắc DST có thể làm một thời điểm địa phương không tồn tại hoặc xuất hiện hai lần.
- Java `LocalDate`, `LocalDateTime`, `Instant` và `OffsetDateTime` có ngữ nghĩa khác nhau.
- API và DB session có thể dùng timezone mặc định khác nhau.

Không mặc định gắn UTC cho mọi timestamp lịch sử nếu không có bằng chứng; một migration như vậy có thể dịch chuyển lịch sử giao dịch nhiều giờ.

### 9.4. Unicode và collation

Thay encoding, collation hoặc cách chuẩn hóa Unicode có thể ảnh hưởng tới:

- So sánh tên có dấu.
- Sắp xếp văn bản theo ngôn ngữ.
- Unique index trên email/tên/khóa văn bản.
- Tạo search key và index toàn văn.
- Tính tương thích khi export/import.

Một thay đổi collation có thể khiến hai giá trị trước đó được coi là khác nay trở thành tương đương theo một quy tắc mới. Cần rà soát duplicate và kiểm thử chỉ mục/ràng buộc trước khi áp dụng ở quy mô lớn.

## 10. JSON, Avro, Protobuf và sự kiện bền vững phải có chiến lược versioning

Không chỉ bảng quan hệ cần tiến hóa. Ứng dụng Java có thể ghi hàng triệu event JSON vào broker hoặc outbox; các sự kiện cũ được lưu để audit, replay, xây lại cache và projection.

### 10.1. Ví dụ sự kiện v1/v2

V1 chỉ hỗ trợ một đơn vị tiền:

~~~json
{
  "eventId": "evt-1001",
  "type": "OrderCreated",
  "schemaVersion": 1,
  "orderId": 42,
  "totalCents": 120000
}
~~~

V2 hỗ trợ nhiều loại tiền tệ:

~~~json
{
  "eventId": "evt-1002",
  "type": "OrderCreated",
  "schemaVersion": 2,
  "orderId": 43,
  "totalMinorUnits": 120000,
  "currency": "VND"
}
~~~

Chuyển từ `totalCents` sang `totalMinorUnits` không chỉ là đổi tên field. Tên mới phải đi cùng định nghĩa **đơn vị nhỏ nhất** và cách diễn giải theo từng currency, bởi mỗi loại tiền tệ có số chữ số thập phân/quy tắc xử lý khác nhau.

Nếu consumer v1 chỉ đọc `totalCents` và producer v2 không còn phát trường đó, consumer có thể thất bại hoặc âm thầm dùng giá trị mặc định sai. Hai event trên đều là JSON hợp lệ, nhưng chưa chắc tương thích về **hợp đồng đọc**.

### 10.2. Một số loại thay đổi cần xem xét

| Thay đổi | Rủi ro tương thích |
|---|---|
| Thêm field JSON tùy chọn | Consumer strict có thể từ chối field lạ |
| Bỏ field bắt buộc | Reader cũ có thể crash hoặc dùng default không đúng |
| Đổi tên field | Consumer cần alias, adapter hoặc nâng phiên bản |
| String → number | Parser, validator, precision và phép ép kiểu có thể khác |
| Bổ sung enum value | Consumer cũ cần xử lý unknown value có chủ đích |
| Đổi field number Protobuf | Payload nhị phân cũ có thể bị diễn giải sai |
| Thêm field Avro | Phải kiểm tra reader/writer schema và default tương ứng |
| Thay codec nén hoặc mã hóa | Reader cần codec/key version phù hợp |
| Thay ý nghĩa nhưng giữ kiểu | Schema validator có thể không phát hiện |

**Protobuf:** field number/tag là một phần hợp đồng nhị phân. Không nên tái sử dụng tag cũ cho field mới mang nghĩa khác; khi loại bỏ field, áp dụng quy tắc `reserved` theo công nghệ.

**Avro:** khả năng đọc được phụ thuộc cách ghép writer schema và reader schema, alias, default và quy tắc schema resolution. Một thay đổi chỉ nên được coi là tương thích sau khi kiểm tra chiều producer–consumer cần hỗ trợ.

**JSON:** bản thân format không bắt consumer bỏ qua trường lạ. Các thư viện deserialize Java có thể cấu hình strict hoặc lenient, nên phải kiểm thử với cấu hình thật.

### 10.3. Version là hợp đồng, không chỉ metadata

Một số hệ thống dùng một field `schemaVersion` và hàm chuyển đổi rõ ràng:

~~~java
public sealed interface OrderCreatedEvent
        permits OrderCreatedV1, OrderCreatedV2 {}

public record OrderCreatedV1(long orderId, long totalCents)
        implements OrderCreatedEvent {}

public record OrderCreatedV2(
        long orderId, long totalMinorUnits, String currency)
        implements OrderCreatedEvent {}
~~~

Đây là ví dụ mô tả khả năng quản lý nhiều phiên bản trong Java; để chạy thực tế cần serializer và logic chuyển đổi. Có thể chuẩn hóa các version về **một model nội bộ** cho consumer, nhưng phải giữ đúng ý nghĩa lịch sử.

Nếu một record thiếu currency mà hệ thống không thể chứng minh đơn vị cũ là gì, adapter không được tự giả định một currency ngẫu nhiên.

### 10.4. Replay khiến code mới phải hiểu format cũ

Một consumer mới có thể được yêu cầu chạy lại sự kiện đã lưu nhiều tháng trước. Vì vậy cần giữ:

- Schema/codec đủ để đọc những version còn trong phạm vi replay.
- Quy tắc chuyển đổi semantic giữa version cũ và model mới.
- Cách giải mã dữ liệu được mã hóa bằng key version cũ trong giới hạn chính sách bảo mật.
- Kiểm thử event cũ có dữ liệu hiếm hoặc thiếu field.
- Chính sách retention và xử lý thông tin nhạy cảm trong log sự kiện.

Một schema registry hoặc kiểm tra compatibility trong CI giúp phát hiện nhiều lỗi cấu trúc, nhưng **không thể thay thế kiểm thử ngữ nghĩa**. Giữ kiểu số nguyên nhưng đổi từ đồng nhỏ nhất sang đồng chính vẫn có thể làm sai số tiền.

## 11. Cache, projection và chỉ mục tìm kiếm cũng cần tiến hóa

Một thay đổi ở bảng nguồn có thể lan sang nhiều nơi:

~~~text
orders in PostgreSQL
    |
    +-- REST/GraphQL DTO
    +-- outbox events / message broker
    +-- Redis cache
    +-- search documents
    +-- reporting projections
    +-- export / backups
~~~

Nếu thêm `currency` vào `orders` nhưng bỏ quên báo cáo tổng doanh thu, một câu `SUM(total_amount)` trên các loại tiền khác nhau có thể tạo con số vô nghĩa. Cache vẫn lưu object cũ có thể không deserialize với class mới. Search index vẫn có mapping cũ và không chấp nhận field mới.

### 11.1. Tiến hóa read model

Một cách triển khai an toàn cho projection hoặc search index:

1. Tạo index/projection mới theo schema mới.
2. Backfill từ nguồn có thẩm quyền.
3. Bắt kịp thay đổi phát sinh trong lúc backfill bằng outbox, CDC hoặc cơ chế kiểm soát tương đương.
4. Kiểm tra ID, số lượng, source version, checksum hoặc nội dung mẫu.
5. Chuyển đường đọc/alias sang projection mới.
6. Theo dõi độ trễ, lỗi mapping và tình huống dữ liệu hiếm.
7. Chỉ dọn projection cũ sau khi không còn phụ thuộc.

Nếu rebuild đọc snapshot cũ mà không có bước catch-up, các thay đổi mới có thể bị **mất trên index vừa xây**, dù database nguồn vẫn đúng. Nếu event đến sai thứ tự, cần version check/idempotency ở consumer để tránh update cũ ghi đè tài liệu mới.

### 11.2. Dữ liệu xóa và tombstone

Một event delete có thể đến trước event update cũ bị gửi lại. Nếu projection đã xóa tài liệu nhưng không giữ dấu phiên bản xóa, update cũ có thể làm tài liệu “sống lại”.

Giải pháp có thể dùng tombstone/version, retention và cơ chế áp dụng thay đổi nguyên tử theo version của nguồn. Dọn tombstone quá sớm trong khi vẫn cho replay event cũ có thể phá khả năng chống hồi sinh.

Với dữ liệu cá nhân, retention của tombstone/outbox/log cần cân bằng với yêu cầu xóa và bảo mật; không giữ vô hạn payload nhạy cảm chỉ để dễ rebuild.

### 11.3. Cache và serialized Java object

Nếu Redis cache chứa object được serialize theo tên class/field cũ, code mới có thể không đọc được. Một chiến lược là namespace key mới theo version và để cache cũ hết hạn, nhưng cần tính tới **cache stampede** khi nhiều replica cùng phải tải lại từ DB.

TTL không bảo đảm tương thích ngay sau deploy. Trong cửa sổ còn entry cũ, code mới phải biết xử lý hoặc chọn bỏ qua/xóa cache cũ một cách có điều tiết.

## 12. Schema migration tools trong hệ sinh thái Java

**Flyway** và **Liquibase** là công cụ phổ biến để quản lý migration có thứ tự, lưu lịch sử và phối hợp triển khai. Chúng giải quyết việc **thực thi migration được kiểm soát**, không tự quyết định migration nào an toàn về nghiệp vụ.

Một chuỗi thay đổi điển hình:

~~~text
Pull request:
  migration EXPAND + schema/DDL review
  cập nhật entity/repository/DTO
  test dữ liệu lịch sử và test reader/writer cùng tồn tại
  thiết kế backfill, metric, rollback/roll-forward

Deploy:
  chạy EXPAND trước code mới cần cột mới
  deploy code có khả năng đọc dữ liệu cũ
  triển khai writer mới mà vẫn giữ hợp đồng phiên bản cũ
  backfill + verify
  bật tính năng mới khi đủ điều kiện
  CONTRACT sau khi mọi consumer cũ đã rời đi
~~~

### 12.1. Không phụ thuộc ORM auto-update để di chuyển production

Hibernate/JPA có thể sinh hoặc kiểm tra schema, nhưng tự thay đổi schema production có hạn chế:

- Không hiểu phép chuyển đổi có ý nghĩa nghiệp vụ.
- Không bảo đảm xử lý dữ liệu cũ bất thường.
- Có thể chạy DDL không đúng thời điểm trong lúc nhiều instance khởi động.
- Không quyết định batch size, lock và thời gian chạy.
- Không tự quản lý phối hợp với consumer ngoài DB.

Nên ưu tiên migration versioned có review và ứng dụng kiểm tra mapping phù hợp; dùng chức năng tự tạo schema phù hợp hơn trong thử nghiệm hoặc môi trường được kiểm soát.

### 12.2. DDL có thể gây khóa và không phải lệnh nào cũng chạy trong transaction

Trong PostgreSQL, thêm index lớn đôi khi cần:

~~~sql
CREATE INDEX CONCURRENTLY idx_orders_created_at
ON orders (created_at);
~~~

Tùy chọn `CONCURRENTLY` giảm một số dạng blocking so với tạo index thông thường, nhưng có chi phí I/O và thời gian riêng; đặc biệt **không được chạy bên trong transaction block tường minh**. Migration tool phải được cấu hình phù hợp cho bước này.

Cũng cần biết:

- Một `ALTER TABLE` có thể cần lock dù chỉ thay metadata.
- Một số phép đổi kiểu dữ liệu có thể rewrite bảng.
- Index unique có thể thất bại nếu dữ liệu đã trùng.
- Một bước DDL có thể làm replica lag hoặc tiêu thụ nhiều log.
- Cú pháp và chính sách lock khác nhau giữa PostgreSQL, MySQL/InnoDB, SQL Server và Oracle.

Không sao chép nguyên một runbook DDL giữa các DBMS mà không đánh giá engine/phiên bản.

### 12.3. Chuẩn bị câu hỏi trước migration

- Lệnh có cần table rewrite hay index rebuild?
- Chế độ khóa là gì? Có phải chờ transaction lâu?
- Có thể đặt `lock_timeout` và `statement_timeout` phù hợp để tránh làm treo workload không?
- Có phải chạy DDL ngoài transaction?
- Nếu lỗi giữa chừng, migration có thể retry và trạng thái trung gian là gì?
- Khi failover hoặc có replica lag, tác động lên ứng dụng ra sao?
- Có rollback/roll-forward hoặc runbook khôi phục nếu phát hiện sai dữ liệu không?

Một migration “chạy nhanh ở máy local” không đủ bằng chứng cho production có kích thước và tải khác biệt.

## 13. Ranh giới transaction, isolation và writer đồng thời

Migration có thể làm thay đổi trạng thái của nhiều hàng đang được API cập nhật. Cần thiết kế ranh giới transaction và điều kiện ghi không làm mất update.

### 13.1. Một transaction lớn hay nhiều transaction nhỏ?

Một transaction lớn có lợi thế atomicity cho toàn tập nhưng có thể giữ khóa lâu, tăng WAL/redo, tốn bộ nhớ và làm rollback chậm. Nhiều batch commit nhanh hơn về vận hành, nhưng nếu batch sau lỗi thì batch trước vẫn đã commit.

**Hệ quả:** ứng dụng phải chấp nhận giai đoạn dữ liệu đã chuyển một phần. Reader có fallback và writer duy trì hợp đồng mới/cũ là phần của thiết kế migration, không phải giải pháp tạm tùy ý.

### 13.2. Isolation không thay thế bất biến migration

Một transaction backfill có thể tự commit hợp lệ mà vẫn ghi đè dữ liệu mới nếu câu `UPDATE` không có điều kiện. Cần diễn đạt bất biến, ví dụ:

~~~text
Nếu currency đã có giá trị hợp lệ -> backfill không sửa.
Nếu currency NULL và đơn chắc chắn thuộc giai đoạn chỉ VND -> điền VND.
Nếu không xác minh được currency lịch sử -> cách ly và đối soát.
~~~

Từ bất biến đó mới chọn SQL, version check, locking và cách xử lý affected row count.

### 13.3. Constraint là hàng rào cuối, không phải phép màu

Sau khi dữ liệu hợp lệ, thêm `PRIMARY KEY`, `UNIQUE`, `FOREIGN KEY`, `CHECK` và `NOT NULL` giúp ngăn dữ liệu mới vi phạm. Tuy nhiên:

- Constraint không tự suy ra tiền tệ cho đơn cũ.
- Một ràng buộc chỉ được kiểm tra/validate theo quy tắc DBMS cụ thể.
- Dữ liệu lịch sử có thể chưa phù hợp; phải làm sạch trước.
- Một số bất biến liên bảng cần transaction/locking hoặc thiết kế riêng.

Không được xem một migration DDL thành công là bằng chứng tất cả quy tắc nghiệp vụ đã đúng.

## 14. Rollback code, roll-forward dữ liệu và backup

### 14.1. Rollback không phải lúc nào cũng an toàn

Thêm cột nullable thường dễ quay lại code cũ hơn so với:

- Bật tính năng ghi USD khi code cũ chỉ hiểu VND.
- Xóa cột gốc sau khi đã chuyển dữ liệu.
- Làm tròn số với precision thấp hơn, mất giá trị ban đầu.
- Hợp nhất hai bản ghi thành một và bỏ thông tin phân biệt.
- Mã hóa bằng khóa mà bản cũ không thể sử dụng.

Khi đã tồn tại dữ liệu mới mang ý nghĩa mà code cũ không hiểu, thường cần **roll-forward** để sửa phần mềm, hoặc một bản cũ đã được cập nhật tương thích. Không mặc định chạy `down migration` sẽ đưa toàn bộ hệ thống về trạng thái trước đó.

### 14.2. Backup cần kiểm thử khả năng restore

Trước migration rủi ro cao, nên có kế hoạch backup/restore phù hợp:

- Backup có nhất quán với transaction log không?
- RPO (mất dữ liệu cho phép) và RTO (thời gian phục hồi) là bao nhiêu?
- Restore về snapshot cũ sẽ làm gì với các đơn hợp lệ mới tạo sau snapshot?
- Ứng dụng, schema version và consumer có tương thích với database được restore không?
- Backup có chứa bí mật hoặc dữ liệu cá nhân cần bảo vệ không?

Restore toàn database về thời điểm cũ có thể làm mất công việc kinh doanh hợp lệ. Trong nhiều tình huống, một **migration bù có kiểm toán** phù hợp hơn so với restore đè toàn bộ dữ liệu.

### 14.3. Phân loại tính đảo ngược

| Loại thay đổi | Ví dụ | Cách phục hồi thường cần |
|---|---|---|
| Có thể đảo khi chưa ghi mới | Thêm cột nullable chưa dùng | Rollback code hoặc bỏ cột khi đã xác minh |
| Đảo được với dữ liệu bảo toàn | Đổi tên khi còn cả cột cũ/mới đúng | Chuyển read/write path trở lại có điều kiện |
| Mất thông tin | Thu hẹp kiểu, làm tròn, bỏ cột gốc | Cần nguồn sao lưu hoặc xử lý bù; không tự đảo |
| Đổi ngữ nghĩa | Bắt đầu ghi USD vào hệ chỉ VND | Roll-forward hoặc bản code cũ đã sửa tương thích |
| Thay vật lý/engine | Upgrade storage/DB version | Quy trình backup/restore/upgrade vendor hỗ trợ |

Đánh giá “có thể rollback” ở **mức dữ liệu và nghiệp vụ**, không chỉ xem script có lệnh đảo DDL hay không.

## 15. Kiểm thử tiến hóa dữ liệu

Một cơ sở dữ liệu trống không thể mô phỏng đầy đủ hành vi production có dữ liệu lịch sử.

### 15.1. Ma trận kiểm thử phiên bản

| Trường hợp | Điều cần kiểm tra |
|---|---|
| App v1 + schema cũ | Chức năng cũ còn đúng |
| App v1 + schema đã expand | Code cũ không lỗi khi cột mới xuất hiện |
| App v2 + schema expand + hàng cũ | Fallback/adapter đọc đúng dữ liệu lịch sử |
| App v1/v2 chạy song song | Không xuất hiện ghi hoặc hiểu sai ngữ nghĩa |
| App v2 + backfill một phần | Hàng chưa/đã chuyển đều đọc đúng |
| App v2 + schema đã contract | Không còn tham chiếu cột/format cũ |
| Consumer cũ + event mới | Có tương thích theo hợp đồng hoặc được nâng cấp trước |
| Consumer mới + event cũ | Có thể replay và chuyển đổi ngữ nghĩa |
| Restore backup cũ | App/schema được đưa về trạng thái tương thích |
| Backfill dừng rồi chạy lại | Không nhân đôi hoặc ghi đè dữ liệu mới |

### 15.2. Bộ dữ liệu thử có trường hợp khó

Nên có:

- Giá trị `NULL`, chuỗi rỗng và field thiếu.
- Số quá lớn, số thập phân nhiều chữ số, precision khác nhau.
- Unicode, dấu tiếng Việt và những ngôn ngữ khác.
- Ngày gần ranh giới múi giờ/DST.
- Mã trạng thái/enum cũ, giá trị chưa biết.
- Dữ liệu duplicate/orphan từng được hệ thống cũ chấp nhận.
- Bản ghi thay đổi đồng thời với backfill.
- Đơn lịch sử không thể suy ra trường mới một cách chắc chắn.

### 15.3. Failure injection và kiểm thử đồng thời

Điều khiển hai session:

~~~text
Migration: đọc hàng 42 có currency NULL
API mới:   điền currency USD cho hàng 42
Migration: cố backfill VND

Expected: migration không được ghi đè USD.
~~~

Tương tự, nên kiểm tra job crash sau commit batch nhưng trước khi ghi log, network failure quanh commit, lock timeout trong DDL, index rebuild trong lúc nguồn có cập nhật và consumer đọc event lịch sử.

Kiểm thử phải xác nhận **trạng thái cuối của DB và các bất biến**, không chỉ assert rằng một mock repository đã được gọi.

### 15.4. Đối chiếu dữ liệu trước và sau

Ví dụ:

~~~sql
SELECT COUNT(*) AS missing_currency
FROM orders
WHERE currency IS NULL;

SELECT currency, COUNT(*)
FROM orders
GROUP BY currency;

SELECT id, currency
FROM orders
WHERE currency IS NOT NULL
  AND currency NOT IN ('VND', 'USD', 'EUR');
~~~

Các mã currency ở ví dụ chỉ minh họa. Một phép đối chiếu số tiền phải dùng cùng currency/đơn vị và quy tắc làm tròn; không cộng đơn USD và VND thành một tổng không ghi đơn vị.

Ngoài row count, nên có checksum, tập khóa, dữ liệu mẫu, chênh lệch phiên bản hoặc phép kiểm tổng phù hợp với loại chuyển đổi.

## 16. Giám sát và runbook triển khai

### 16.1. Chỉ số quan trọng

| Chỉ số | Câu hỏi |
|---|---|
| Schema migration version | Schema nào đã được triển khai ở từng môi trường? |
| Backfill remaining/completed | Bao nhiêu hàng còn cần chuyển? |
| Backfill throughput/errors | Job chạy nhanh và ổn định không? |
| Rows requiring manual reconciliation | Có dữ liệu lịch sử mơ hồ hoặc sai không? |
| DDL/row lock wait | Migration có chặn request không? |
| DB CPU/I/O/WAL/replica lag | Chi phí chuyển đổi ảnh hưởng DB ra sao? |
| App error rate, p95/p99 | Code mới có làm lỗi/chậm hơn không? |
| Old-format read/write count | Còn client hoặc job phụ thuộc dữ liệu cũ không? |
| Projection/search lag | Bản sao đã bắt kịp thay đổi nguồn chưa? |
| Event deserialization failures | Consumer còn đọc được payload lịch sử không? |

Migration tool báo thành công mới chỉ là một mốc. Cần tiếp tục quan sát sau khi bật tính năng mới và khi các job/consumer ít chạy bắt đầu hoạt động.

### 16.2. Runbook trước, trong và sau

**Trước triển khai:**

1. Ghi rõ động lực thay đổi, hợp đồng cũ/mới và bất biến.
2. Liệt kê producer, consumer, báo cáo, cache, search, export và backup.
3. Lập ma trận phiên bản code/schema/format và thứ tự deploy.
4. Đo DDL lock/rewrite/index cost và dự phòng tải.
5. Chuẩn bị metric, alert, kill switch, backfill checkpoint và kế hoạch khôi phục.
6. Test với dữ liệu có đặc tính giống production.

**Trong triển khai:**

1. Chạy EXPAND trước khi code mới phụ thuộc cột mới.
2. Deploy reader/writer tương thích và giữ feature gate khi cần.
3. Backfill theo lô với ngưỡng tải được kiểm soát.
4. Xử lý các hàng lỗi, theo dõi độ lệch và khôi phục job sau failure.
5. Xác minh không còn writer/reader cũ trước khi bật hành vi mới hoặc contract.

**Sau triển khai:**

1. Kiểm tra ràng buộc, chỉ số lỗi và data reconciliation.
2. Kiểm tra consumer/event replay và projection.
3. Theo dõi qua đủ chu kỳ sử dụng, kể cả job chạy theo ngày/tuần.
4. Chỉ xóa cấu trúc cũ sau khi hết phụ thuộc và dữ liệu đã được bảo toàn.
5. Lưu quyết định migration và ý nghĩa dữ liệu để phục vụ thay đổi tương lai.

## 17. Sai lầm thường gặp

| Sai lầm | Hệ quả | Cách khắc phục |
|---|---|---|
| Sửa schema trong một deploy duy nhất | Phá các replica và job cũ | Expand–migrate–contract |
| Code mới chỉ đọc dữ liệu mới | Không đọc được hàng lịch sử | Fallback/adapter và backfill |
| Bật format/đơn vị mới khi reader cũ còn chạy | Sai ngữ nghĩa, đôi khi không phát sinh exception | Feature gate, ma trận compatibility |
| Backfill ghi đè từ snapshot cũ | Mất cập nhật concurrent | SQL có điều kiện/version check |
| Backfill mọi hàng trong một transaction | Lock/log lớn, khó phục hồi | Batch nhỏ, checkpoint, giám sát |
| Chỉ dùng default để lấp dữ liệu không biết | Tạo dữ liệu “hợp lệ” nhưng sai | Đối soát và cách ly ngoại lệ |
| Thấy migration version mới là đã hoàn tất | Backfill/consumer có thể chưa sẵn sàng | Theo dõi trạng thái dữ liệu riêng |
| Tin JSON schema hợp lệ là đủ | Consumer có thể hiểu sai field | Test producer–consumer và semantic contract |
| Tin ORM auto-update là migration production | Không kiểm soát chuyển đổi/DDL | Công cụ migration có review |
| Quên event/cache/search | Dữ liệu dẫn xuất bị lệch | Versioning, rebuild, replay |
| Tin down migration luôn đảo được dữ liệu | Mất thông tin đã ghi | Phân loại khả năng rollback, roll-forward |
| Không kiểm thử restore | Backup có thể không dùng được trong tình huống thật | Rehearsal và runbook |
| Dừng monitoring ngay sau deploy | Lỗi chỉ xuất hiện ở job/consumer chạy muộn | Quan sát nhiều chu kỳ |

## 18. Bài tập vận dụng

### Bài 1. Mã Java mới và dữ liệu cũ

Một service thêm trường bắt buộc `customerType` vào entity và DB. Vì sao không thể chỉ thay class rồi deploy?

**Gợi ý:** Hàng cũ còn thiếu, writer cũ còn ghi thiếu và consumer có thể chưa biết trường mới. Cần expand, reader tương thích, backfill rồi mới siết constraint.

### Bài 2. Thêm currency

Khi nào an toàn để bắt đầu ghi đơn USD trong case study?

**Gợi ý:** Khi tất cả reader/consumer liên quan đều hiểu currency và không còn đường code mặc định mọi đơn là VND; cột được thêm trước đó chưa đủ.

### Bài 3. Backfill cạnh tranh

Job đã đọc `currency IS NULL` trước khi API ghi USD, rồi chuẩn bị ghi VND. Cần làm gì?

**Gợi ý:** `UPDATE ... WHERE currency IS NULL` hoặc optimistic version check, cùng kiểm thử hai transaction đồng thời.

### Bài 4. Siết ràng buộc

Một bảng có 10.000 hàng null trong cột sắp đặt `NOT NULL`. Có thể chỉ chạy `ALTER COLUMN SET NOT NULL` không?

**Gợi ý:** Cần xác minh dữ liệu, backfill và writer trước. Đánh giá thời gian lock/validation trên DBMS và phiên bản thật.

### Bài 5. Đổi event JSON

Consumer cũ chỉ đọc `totalCents`, producer mới chỉ gửi `totalMinorUnits` và `currency`. Vì sao có thể hỏng dù JSON vẫn hợp lệ?

**Gợi ý:** Consumer không còn thấy field cũ và có thể hiểu sai đơn vị. Cần adapter/version hợp đồng và thử với cả hai phiên bản.

### Bài 6. Vấn đề khi rollback

Sau khi ghi một nghìn đơn USD, nhóm định rollback app về v1 chỉ hiểu VND. Có an toàn không?

**Gợi ý:** Không. Đây là điểm không tương thích ngữ nghĩa; cần roll-forward hoặc bản v1 đã biết xử lý currency mới.

### Bài 7. Protobuf field tags

Một field Protobuf không còn dùng; có nên tái sử dụng ngay tag number cho một ý nghĩa khác?

**Gợi ý:** Không. Payload cũ có thể bị giải mã sai; dùng cơ chế reserved field number/name.

### Bài 8. Backfill đã chạy xong, index chưa bắt kịp

Index mới được tạo từ snapshot trong lúc nguồn vẫn nhận cập nhật. Cần làm gì trước khi chuyển alias?

**Gợi ý:** Bắt kịp delta từ mốc snapshot bằng event/CDC hoặc quét bù và xác minh source version, dữ liệu và lag.

### Bài 9. Chuyển kiểu số tiền

Từ `DOUBLE PRECISION` sang `NUMERIC(18,2)` có phải chỉ là đổi DDL?

**Gợi ý:** Không. Cần kiểm tra precision lịch sử, rounding, đơn vị, dữ liệu đã quyết toán và cách Java dùng `BigDecimal`.

### Bài 10. Kế hoạch phục hồi

Một migration đã xóa cột chứa dữ liệu lịch sử không được sao chép ở đâu khác. Script down tạo lại cột đó có phục hồi được dữ liệu không?

**Gợi ý:** Không. Tạo lại cấu trúc không tạo lại giá trị đã mất; cần nguồn backup/đối soát hoặc giải pháp bù.

### Bài 11. Migration tool báo thành công

Flyway đã đánh dấu schema version mới, nhưng backfill còn 20% và consumer vẫn đọc format cũ. Có thể CONTRACT ngay không?

**Gợi ý:** Không. Schema version không chứng minh dữ liệu và mọi dependent system đã sẵn sàng. Chỉ contract sau khi hoàn tất điều kiện đã định.

### Bài 12. Dữ liệu lịch sử không rõ nghĩa

Một nhóm đơn cũ có `total_amount` nhưng không có nguồn xác nhận currency. Có nên điền VND mặc định để đạt 100% backfill?

**Gợi ý:** Không. Phải phân loại, đối soát và ghi lại quyết định nghiệp vụ có thể kiểm toán; không biến giả định không chắc thành dữ liệu “hợp lệ”.

## 19. Ghi nhớ

- **Dữ liệu sống lâu hơn mã nguồn.** Schema và format phải tiến hóa khi nghiệp vụ, quy mô, truy vấn, bảo mật và công nghệ thay đổi.
- **Tương thích gồm cả ngữ nghĩa.** Code cũ/mới cần hiểu đúng đơn vị, trạng thái, kiểu dữ liệu và các bản ghi lịch sử, chứ không chỉ parse được cấu trúc.
- **Thay đổi theo pha.** Expand schema, deploy reader/writer tương thích, backfill với kiểm soát cạnh tranh, verify rồi contract.
- **Backfill là ghi dữ liệu thật.** Transaction ngắn, idempotency, checkpoint, version/condition check và reconciliation là các công cụ thiết yếu.
- **Không dựa riêng vào tool.** Flyway/Liquibase, Hibernate và schema registry hỗ trợ kỹ thuật; tính đúng đắn phải được định nghĩa và kiểm thử.
- **Bản sao cũng phải tiến hóa.** Cache, event, search index, báo cáo và backup cần tương thích hoặc có kế hoạch rebuild/replay.
- **Rollback code khác rollback dữ liệu.** Khi đã ghi dữ liệu mang nghĩa mới, cần kế hoạch roll-forward và phục hồi có kiểm chứng.

Một migration thành công không chỉ là chạy xong câu `ALTER TABLE`; đó là quá trình **chuyển hệ thống từ hợp đồng dữ liệu cũ sang hợp đồng mới mà không đánh mất tính đúng đắn của dữ liệu đã lưu và các thao tác đang diễn ra**. Thiết kế có tương thích, thay đổi từng bước, đối soát trên dữ liệu thật và quan sát sau triển khai giúp lớp persistence Java phát triển cùng sản phẩm thay vì trở thành điểm nghẽn khi yêu cầu thay đổi.
