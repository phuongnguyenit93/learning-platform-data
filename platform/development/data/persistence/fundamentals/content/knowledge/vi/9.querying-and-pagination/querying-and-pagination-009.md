# Tính nhất quán của các trang khi có ghi đồng thời

Một API phân trang có thể hoạt động đúng khi dữ liệu đứng yên nhưng trả kết quả khó hiểu khi người dùng khác đồng thời thêm, sửa hoặc xóa bản ghi. Người xem danh sách có thể gặp **một mục xuất hiện hai lần**, **một mục bị bỏ qua**, hoặc **số lượng tổng không khớp với các hàng đang hiển thị**.

Đây là bài toán về **tính nhất quán của truy vấn và phân trang dưới cập nhật đồng thời**. Thiết kế cần xác định rõ người dùng đang duyệt một tập dữ liệu thay đổi liên tục hay một ảnh chụp dữ liệu tại một thời điểm, sau đó chọn thứ tự sắp xếp, kiểu phân trang, mức cô lập và hợp đồng API phù hợp.

Bài học thuộc chương **Truy vấn và phân trang** của module `DATA_PERSISTENCE_FUNDAMENTALS`. Nội dung liên hệ với thiết kế truy vấn và chỉ mục, giao dịch và MVCC, kiểm soát đồng thời, ranh giới persistence trong Java, xử lý lỗi kết nối, hiệu năng, bảo mật và độ nhất quán giữa các nguồn dữ liệu.

## 1. “Nhất quán khi phân trang” có nhiều nghĩa

Trước khi chọn `OFFSET` hay cursor, cần xác định điều người dùng cần được bảo đảm. Có ít nhất bốn khía cạnh:

1. **Thứ tự xác định (deterministic ordering):** cùng một trạng thái dữ liệu phải có thứ tự rõ ràng, không phụ thuộc thứ tự vật lý ngẫu nhiên của hàng.
2. **Duyệt không lặp và không bỏ sót do dịch chuyển trang:** khi tiếp tục từ trang trước, những hàng đã thấy không bất ngờ xuất hiện lại và hàng ở ranh giới không bị bỏ qua chỉ vì bản ghi khác được thêm/xóa phía trước.
3. **Ảnh chụp nhất quán (snapshot consistency):** mọi trang phản ánh cùng một trạng thái dữ liệu tại một thời điểm, dù nguồn vẫn tiếp tục được cập nhật.
4. **Nhất quán giữa dữ liệu và tổng số:** số hàng, tổng kết quả và các trang được tính từ cùng phạm vi dữ liệu hoặc cùng snapshot theo hợp đồng.

Các bảo đảm này **không đồng nghĩa**:

- Sắp xếp ổn định không tự tạo snapshot.
- Keyset pagination giảm lỗi dịch chuyển do offset nhưng không đóng băng dữ liệu.
- Một transaction snapshot có thể giữ dữ liệu ổn định nhưng không tự làm truy vấn rẻ hơn.
- Tổng số chính xác có thể tốn kém và có thể không cần thiết với mọi giao diện.

Ví dụ một bảng bài viết có hàng nghìn bản ghi. Người dùng mở trang đầu, sau đó một tác giả xuất bản bài mới và một quản trị viên xóa bài cũ. Trang thứ hai cần phản ánh dữ liệu theo cách nào? Không có một câu trả lời đúng cho mọi sản phẩm. **Hợp đồng phân trang phải nói rõ dữ liệu là live hay snapshot.**

## 2. Vì sao OFFSET pagination bị lặp hoặc bỏ sót?

Cách phân trang quen thuộc:

~~~sql
SELECT id, title, created_at
FROM articles
ORDER BY created_at DESC
LIMIT 3 OFFSET 0;
~~~

Trang tiếp theo:

~~~sql
SELECT id, title, created_at
FROM articles
ORDER BY created_at DESC
LIMIT 3 OFFSET 3;
~~~

Giả sử ban đầu thứ tự là:

~~~text
A, B, C, D, E, F, G, H, ...
~~~

Trang 1 lấy `A, B, C`. Trước khi người dùng tải trang 2, một bản ghi mới `X` được chèn lên đầu danh sách:

~~~text
X, A, B, C, D, E, F, G, H, ...
~~~

Trang 2 vẫn dùng `OFFSET 3` nên trả:

~~~text
C, D, E
~~~

Bản ghi `C` bị lặp lại vì vị trí của các hàng phía sau đã dịch chuyển.

Một tình huống ngược lại xảy ra khi hàng phía trước bị xóa. Ban đầu người dùng đã thấy `A, B, C`; sau đó `A` bị xóa:

~~~text
B, C, D, E, F, G, H, ...
~~~

Trang 2 với `OFFSET 3` bắt đầu từ `E`, nên `D` bị bỏ qua dù chưa từng xuất hiện trên trang 1.

| Thay đổi trước ranh giới trang | Hệ quả với OFFSET cố định |
| --- | --- |
| Chèn thêm hàng ở phía trước | Các hàng dịch xuống; có thể lặp hàng đã xem |
| Xóa hàng ở phía trước | Các hàng dịch lên; có thể bỏ qua hàng chưa xem |
| Cập nhật cột sắp xếp | Hàng có thể chuyển từ trang này sang trang khác |
| Thêm hoặc xóa hàng sau ranh giới | Có thể thay đổi nội dung trang sau và tổng số |

**OFFSET không sai về cú pháp.** Nó trả về các hàng ở vị trí tương đối trong kết quả truy vấn tại thời điểm câu lệnh chạy. Vấn đề xuất hiện khi ứng dụng kỳ vọng nhiều request độc lập sẽ cùng đại diện cho một danh sách bất biến trong khi dữ liệu đang thay đổi.

### OFFSET còn có vấn đề hiệu năng

Để lấy `LIMIT 20 OFFSET 100000`, database thường phải xác định và bỏ qua một lượng lớn hàng trước khi trả 20 hàng cuối; mức chi phí cụ thể phụ thuộc query plan, index, filter và engine. Offset càng sâu có thể càng tốn công.

OFFSET vẫn phù hợp khi:

- Tập dữ liệu nhỏ hoặc thay đổi ít.
- Người dùng cần nhảy tới trang số cụ thể.
- Giao diện quản trị chấp nhận danh sách live, không yêu cầu snapshot.
- Độ sâu phân trang bị giới hạn và đã đo hiệu năng.

Nếu cần duyệt sâu trên luồng dữ liệu thay đổi thường xuyên, nên đánh giá keyset/cursor hoặc snapshot.

## 3. Trước hết phải có thứ tự sắp xếp toàn phần

Một truy vấn phân trang cần một **thứ tự toàn phần (total order)**. Chỉ sắp theo trường có thể trùng không đủ để xác định vị trí duy nhất của mỗi hàng.

Ví dụ:

~~~sql
SELECT id, title, created_at
FROM articles
ORDER BY created_at DESC
LIMIT 20;
~~~

Nếu nhiều bài có cùng `created_at`, database không được yêu cầu phải xếp chúng theo một thứ tự cố định. Một hàng có thể xuất hiện ở ranh giới trang khác nhau giữa các lần chạy, tùy kế hoạch thực thi và các thay đổi nội bộ.

Thêm một khóa duy nhất làm tiêu chí phân xử:

~~~sql
SELECT id, title, created_at
FROM articles
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

Ở đây `id` duy nhất, nên cặp `(created_at, id)` xác định thứ tự rõ ràng. Khi `created_at` trùng, `id` quyết định hàng nào đứng trước.

### Những nguyên tắc của ORDER BY dùng cho phân trang

- Thứ tự phải bao gồm **khóa phân xử duy nhất**, thường là primary key.
- Quy định rõ `ASC` hoặc `DESC` cho từng trường.
- Nếu trường sắp xếp có thể `NULL`, phải xác định `NULLS FIRST`/`NULLS LAST` và quy tắc cursor tương ứng; cách đơn giản là chọn trường sắp xếp `NOT NULL`.
- Trường dùng để tiếp tục cursor nên ổn định. Nếu người dùng có thể sửa `created_at` hoặc `priority` khiến hàng di chuyển, keyset vẫn có thể lặp hoặc bỏ qua.
- Bộ lọc và thứ tự phải giữ nguyên trong suốt một chuỗi phân trang; nếu người dùng đổi filter, cursor cũ không còn hợp lệ.

**Không có ORDER BY thì không có bảo đảm thứ tự.** Primary key cũng không đồng nghĩa kết quả tự động được trả theo thứ tự khóa chính.

## 4. Keyset pagination: tiếp tục từ khóa của hàng cuối

**Keyset pagination** (còn gọi là seek pagination) dùng giá trị sắp xếp của hàng cuối trang trước làm điểm tiếp tục. Thay vì nói “bỏ qua 20 hàng”, ứng dụng nói “lấy các hàng đứng sau khóa này trong thứ tự đã chọn”.

Giả sử thứ tự là:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

Trang đầu:

~~~sql
SELECT id, title, created_at
FROM articles
WHERE tenant_id = :tenant_id
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

Giả sử hàng cuối trang có:

~~~text
created_at = 2026-11-21T10:00:00Z
id         = 501
~~~

Trang kế tiếp dùng điều kiện nhỏ hơn cặp khóa đó:

~~~sql
SELECT id, title, created_at
FROM articles
WHERE tenant_id = :tenant_id
  AND (
      created_at < :last_created_at
      OR (
          created_at = :last_created_at
          AND id < :last_id
      )
  )
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

Cặp `(created_at, id)` được so sánh theo đúng thứ tự giảm dần. Một cách viết PostgreSQL ngắn hơn, khi hai trường đều `NOT NULL` và cùng hướng sắp xếp, là:

~~~sql
AND (created_at, id) < (:last_created_at, :last_id)
~~~

Với thứ tự tăng dần, điều kiện tiếp tục đổi thành `>`. Nếu thứ tự trộn ASC/DESC, có NULL hoặc nhiều trường, phải xây dựng điều kiện so sánh theo từng thành phần đúng với thứ tự; không dùng máy móc một phép so sánh tuple.

### Vì sao keyset tránh dịch chuyển offset?

Nếu có bản ghi mới đứng trước hàng cuối trang hiện tại, điều kiện “nhỏ hơn khóa cuối” không làm vị trí bắt đầu bị dịch chuyển. Trang sau tiếp tục từ **giá trị khóa đã lưu**, không phụ thuộc số lượng hàng đứng trước.

Tuy nhiên, keyset **không tự tạo snapshot**:

- Một bản ghi mới có khóa sắp xếp nằm sau cursor có thể xuất hiện ở trang sau.
- Một hàng đã xem bị xóa thì không còn xuất hiện trong lần đọc tiếp theo.
- Một hàng chưa xem bị cập nhật khóa sắp xếp để chuyển lên trước cursor có thể bị bỏ qua.
- Một hàng đã xem bị cập nhật khóa để chuyển xuống sau cursor có thể xuất hiện lần nữa.
- Bộ lọc thay đổi có thể làm hàng đi vào hoặc ra khỏi tập kết quả.

Do đó, keyset thường cung cấp **duyệt ổn định hơn trong luồng live** khi dùng khóa sắp xếp bất biến, nhưng không bảo đảm toàn bộ các trang là một ảnh chụp bất biến.

## 5. Cursor là hợp đồng tiếp tục, không phải số trang

API có thể trả:

~~~json
{
  "items": [
    { "id": 510, "title": "Bài viết A" },
    { "id": 509, "title": "Bài viết B" }
  ],
  "nextCursor": "eyJjcmVhdGVkQXQiOi..."
}
~~~

Cursor đại diện cho điểm tiếp tục, thường mã hóa:

- Giá trị các trường sắp xếp của hàng cuối cùng đã trả.
- Phiên bản định dạng cursor.
- Bộ lọc hoặc dấu vân tay của truy vấn.
- Hướng duyệt và có thể cả kích thước trang.
- Thông tin snapshot/high-water mark nếu thiết kế có hỗ trợ.

Cursor thường được serialize thành JSON rồi Base64 URL-safe để thuận tiện truyền qua HTTP. **Base64 không phải mã hóa bảo mật và không chống sửa đổi.** Nếu client có thể thay cursor, server cần kiểm tra chữ ký HMAC hoặc dùng token ngẫu nhiên tra cứu trạng thái phía server. Không đưa bí mật vào cursor chỉ vì nó khó đọc.

Ví dụ payload nội bộ:

~~~json
{
  "v": 1,
  "sort": "createdAtDescIdDesc",
  "lastCreatedAt": "2026-11-21T10:00:00Z",
  "lastId": 501,
  "filterHash": "..."
}
~~~

### Cursor không thay thế xác thực và phân quyền

Ngay cả khi cursor có `tenant_id` hoặc filter hash, server vẫn phải xác định tenant từ danh tính đã xác thực và kiểm tra quyền ở mỗi request. Không tin một tenant ID do client sửa trong token không có chữ ký. Nếu cursor được ký, chữ ký giúp phát hiện sửa đổi nhưng **không che giấu nội dung**; cần token opaque nếu dữ liệu cursor không nên bị nhìn thấy.

Khi cursor gắn với filter, nếu request kế tiếp thay đổi `status`, từ khóa tìm kiếm hoặc sort order, server nên từ chối cursor không tương thích hoặc yêu cầu bắt đầu chuỗi mới. Điều này tránh dùng một điểm tiếp tục trong tập kết quả khác.

## 6. So sánh OFFSET, keyset và snapshot

| Tiêu chí | OFFSET/LIMIT | Keyset/cursor | Snapshot pagination |
| --- | --- | --- | --- |
| Tiếp tục trang | Vị trí số hàng | Giá trị khóa cuối | Vị trí trong một tập dữ liệu đã chụp |
| Nhảy trực tiếp tới trang N | Thuận tiện | Khó; thường phải đi tuần tự | Có thể nếu snapshot có chỉ mục vị trí |
| Chèn/xóa phía trước | Có thể lặp/bỏ sót | Ít bị dịch chuyển ranh giới | Không làm thay đổi snapshot đã chụp |
| Cập nhật trường sắp xếp | Có thể đổi vị trí | Có thể đi qua cursor gây lặp/bỏ sót | Snapshot giữ giá trị tại thời điểm chụp nếu dữ liệu/version được giữ |
| Dữ liệu mới | Có thể làm dịch offset | Có thể xuất hiện nếu nằm sau cursor | Không xuất hiện trong snapshot cũ |
| Độ sâu lớn | Có thể tốn kém | Thường hiệu quả với index phù hợp | Phụ thuộc chi phí tạo/lưu snapshot |
| Độ phức tạp | Thấp | Trung bình; cursor và điều kiện phức hợp | Cao; quản lý snapshot, retention và cleanup |
| Hợp với | Bảng nhỏ, admin, trang số | Feed, lịch sử, danh sách lớn | Báo cáo, export, duyệt yêu cầu point-in-time |

Không có một phương án tốt nhất cho mọi API. Hãy chọn dựa trên yêu cầu người dùng: **trang live có thể thay đổi** hay **tập kết quả phải ổn định trong suốt quá trình duyệt**.

## 7. MVCC và snapshot của giao dịch

Nhiều database hiện đại dùng **Multi-Version Concurrency Control (MVCC)** để cho phép giao dịch đọc một phiên bản dữ liệu phù hợp trong khi giao dịch khác cập nhật. PostgreSQL là ví dụ cụ thể:

- Ở mức cô lập mặc định **READ COMMITTED**, mỗi câu lệnh SQL thường nhìn thấy một snapshot tại thời điểm câu lệnh bắt đầu.
- Ở mức **REPEATABLE READ**, các câu lệnh trong cùng transaction nhìn dữ liệu theo cùng snapshot được xác lập cho transaction, theo quy tắc MVCC của PostgreSQL.
- **SERIALIZABLE** bổ sung kiểm tra để kết quả giao dịch tương đương một thứ tự tuần tự hợp lệ; transaction có thể bị hủy với serialization failure và cần retry toàn bộ transaction theo chính sách.

Vì vậy, hai câu `SELECT` chạy ở hai request HTTP riêng, mỗi request có transaction riêng ở READ COMMITTED, có thể nhìn thấy hai trạng thái khác nhau dù đều dùng cùng filter và ORDER BY.

### Snapshot trong một transaction ngắn

Với báo cáo cần đọc nhiều phần dữ liệu như một snapshot nhất quán, có thể thực hiện các trang trong cùng transaction REPEATABLE READ:

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT id, created_at, title
FROM articles
WHERE tenant_id = 7
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 0;

-- Một request trang kế tiếp trong cùng transaction:
SELECT id, created_at, title
FROM articles
WHERE tenant_id = 7
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 20;

COMMIT;
~~~

Hai câu SELECT trong cùng transaction PostgreSQL REPEATABLE READ sử dụng cùng snapshot, nên các thay đổi commit sau khi snapshot được thiết lập không làm thay đổi tập dữ liệu nhìn thấy trong transaction đó.

**Điều kiện quan trọng:** cả hai câu lệnh phải chạy trong **cùng transaction và cùng connection/session**. Nếu mỗi trang là một HTTP request mở connection và transaction mới, không có bảo đảm tự động dùng lại snapshot trước đó.

### Ví dụ JDBC đọc nhiều trang trong cùng snapshot

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class ArticleSnapshotReader {
    private final DataSource dataSource;

    public ArticleSnapshotReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void readAllPages(long tenantId) throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            connection.setReadOnly(true);
            connection.setTransactionIsolation(
                Connection.TRANSACTION_REPEATABLE_READ
            );
            connection.setAutoCommit(false);

            try {
                int offset = 0;
                int pageSize = 100;

                while (true) {
                    String sql = """
                        SELECT id, created_at, title
                        FROM articles
                        WHERE tenant_id = ?
                        ORDER BY created_at DESC, id DESC
                        LIMIT ? OFFSET ?
                        """;

                    int rowsRead = 0;
                    try (PreparedStatement statement =
                             connection.prepareStatement(sql)) {
                        statement.setLong(1, tenantId);
                        statement.setInt(2, pageSize);
                        statement.setInt(3, offset);

                        try (ResultSet rows = statement.executeQuery()) {
                            while (rows.next()) {
                                rowsRead++;
                                // Xử lý/ghi kết quả trang hiện tại.
                            }
                        }
                    }

                    if (rowsRead < pageSize) {
                        break;
                    }
                    offset += pageSize;
                }

                connection.commit();
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }
}
~~~

Đây là ví dụ đọc liên tục trong **một lần chạy**, không phải mô hình khuyến nghị giữ transaction suốt thời gian người dùng bấm trang. Nó minh họa rằng snapshot phải tồn tại xuyên tất cả các câu lệnh. Với PostgreSQL, driver và transaction manager phải được cấu hình phù hợp; không gọi API theo cách làm transaction tự commit giữa các trang.

### Vì sao không nên giữ transaction qua nhiều lần người dùng bấm trang?

Một transaction REPEATABLE READ sống lâu có chi phí:

- Giữ connection trong pool trong suốt thời gian duyệt.
- Giữ snapshot cũ, có thể cản trở vacuum dọn các phiên bản hàng không còn cần thiết.
- Tăng rủi ro timeout, ngắt kết nối và giữ tài nguyên nếu người dùng bỏ trang.
- Khó quản lý khi người dùng mở nhiều tab hoặc tiếp tục sau nhiều phút.
- Không phù hợp với các phiên phân trang kéo dài hoặc client không đáng tin cậy.

Do đó, **transaction snapshot ngắn** phù hợp cho một báo cáo/export có kiểm soát thời gian hơn là giữ một transaction mở trong suốt hành trình duyệt HTTP nhiều phút.

## 8. Các cách giữ snapshot qua nhiều request HTTP

Nếu yêu cầu thực sự là “tất cả trang phải phản ánh đúng dữ liệu tại thời điểm bắt đầu”, cần một cơ chế snapshot có vòng đời độc lập với một câu SQL.

### Cách A — materialize danh sách ID hoặc kết quả

Khi người dùng bắt đầu export:

1. Tạo một `snapshot_id`.
2. Chạy truy vấn trong transaction nhất quán và ghi các ID theo thứ tự vào bảng snapshot.
3. Mỗi request tiếp theo đọc ID từ bảng snapshot theo số thứ tự.
4. Nếu cần giá trị nội dung cũng bất biến, phải lưu phiên bản hoặc dữ liệu cần thiết tại thời điểm chụp; chỉ lưu ID không đóng băng nội dung hàng.
5. Hết hạn snapshot thì dọn các hàng snapshot theo TTL.

Bảng minh họa:

~~~sql
CREATE TABLE export_snapshot_items (
    snapshot_id UUID NOT NULL,
    ordinal     BIGINT NOT NULL,
    article_id  BIGINT NOT NULL,
    PRIMARY KEY (snapshot_id, ordinal),
    UNIQUE (snapshot_id, article_id)
);
~~~

Trang 2 có thể truy vấn:

~~~sql
SELECT ordinal, article_id
FROM export_snapshot_items
WHERE snapshot_id = :snapshot_id
  AND ordinal > :last_ordinal
ORDER BY ordinal
LIMIT 100;
~~~

Cách này cố định **tập ID và thứ tự**, nhưng nếu nội dung bài viết thay đổi sau khi snapshot được tạo, đọc lại bảng `articles` vẫn có thể thấy nội dung mới. Muốn nội dung nhất quán, cần snapshot giá trị cần xuất, lưu version ID và truy xuất phiên bản đó, hoặc dùng một read model/versioned data có khả năng đọc tại thời điểm chụp.

### Cách B — dữ liệu có version hoặc temporal history

Nếu hệ thống lưu phiên bản dữ liệu với mốc hiệu lực, truy vấn có thể đọc trạng thái tại một version/time cụ thể. Mỗi cursor mang snapshot version hoặc mốc thời gian theo hợp đồng. Cách này cần mô hình lưu lịch sử, quy tắc retention và truy vấn đúng version; chỉ thêm `updated_at` không tự tạo khả năng truy vấn lịch sử.

### Cách C — xuất dữ liệu bất đồng bộ

Với export rất lớn:

- Client tạo yêu cầu export.
- Worker chạy truy vấn snapshot trong transaction hoặc dùng cơ chế nhất quán phù hợp.
- Worker ghi kết quả thành file ở kho lưu trữ.
- Client phân trang/tải file đã tạo hoặc nhận trạng thái tiến độ.
- File export có thời hạn, quyền truy cập và checksum.

Đây thường là cách dễ quản lý hơn việc giữ một transaction database mở trong suốt quá trình client tải hàng triệu bản ghi.

### Cẩn trọng với exported database snapshot

Một số database, trong đó có PostgreSQL, có cơ chế export/import snapshot giữa các transaction theo điều kiện cụ thể. Cơ chế này yêu cầu transaction giữ snapshot tồn tại trong thời gian các transaction khác import và có giới hạn vòng đời; nó **không biến snapshot thành token HTTP bền vững miễn phí**. Cần đánh giá kỹ việc giữ transaction, connection và tài nguyên vacuum trước khi chọn.

## 9. Tổng số kết quả cũng có thể không nhất quán

API thường trả:

~~~json
{
  "items": [],
  "total": 12540,
  "page": 1,
  "pageSize": 20
}
~~~

Nếu câu `COUNT(*)` và câu lấy dữ liệu chạy ở hai transaction/statement READ COMMITTED khác thời điểm, tổng số có thể không khớp với danh sách.

Ví dụ:

1. Query COUNT trả `100`.
2. Một transaction khác thêm 2 hàng.
3. Query trang đầu trả dữ liệu thuộc tập có `102` hàng.

Đây không nhất thiết là lỗi database; mỗi câu lệnh đã nhìn snapshot khác nhau. Nếu API cam kết total và items cùng phản ánh một snapshot, phải tính chúng trong cùng snapshot transaction hoặc cùng một truy vấn có cấu trúc phù hợp.

### Có thật sự cần total chính xác?

Nhiều giao diện chỉ cần biết **có trang kế tiếp hay không**. Khi đó, truy vấn `LIMIT pageSize + 1` giúp xác định `hasNext` mà không cần chạy COUNT toàn bộ:

~~~sql
SELECT id, title, created_at
FROM articles
WHERE tenant_id = :tenant_id
ORDER BY created_at DESC, id DESC
LIMIT 21;
~~~

Nếu page size là 20:

- Trả tối đa 20 hàng.
- Nếu truy vấn trả 21 hàng, đặt `hasNext = true` và bỏ hàng thứ 21 khỏi response.
- Cursor tiếp theo được tạo từ **hàng thứ 20 đã trả**, không phải hàng phụ thứ 21.

Nếu cần total chính xác, hãy công bố rõ đó là total của snapshot nào. Nếu chấp nhận ước lượng hoặc dữ liệu trễ, ghi rõ semantics để client không coi nó là con số đồng bộ tuyệt đối.

## 10. Keyset và dữ liệu có thể thay đổi

Keyset hoạt động tốt nhất khi trường sắp xếp là **bất biến và có thứ tự rõ ràng**, ví dụ `created_at` do server cấp cùng `id` duy nhất. Nhưng có nhiều feed sắp theo trường có thể đổi:

~~~sql
ORDER BY priority DESC, updated_at DESC, id DESC
~~~

Một bản ghi chưa được xem có thể tăng `priority` và di chuyển lên phía trước cursor. Một bản ghi đã xem có thể giảm priority và chuyển xuống phía sau cursor. Khi người dùng tải trang tiếp theo, có thể gặp bỏ sót hoặc lặp.

Các lựa chọn:

- Dùng thứ tự bất biến như `created_at, id` nếu nghiệp vụ chấp nhận.
- Định nghĩa feed live: cho phép dữ liệu mới hoặc thay đổi xuất hiện theo quy tắc đã công bố.
- Nếu cần snapshot, dùng transaction snapshot hoặc materialize/versioned result.
- Nếu dùng `updated_at`, chấp nhận rằng hàng được cập nhật có thể xuất hiện lại theo phiên bản mới hoặc phải thiết kế một feed theo sự kiện.
- Với dữ liệu có trạng thái, quyết định một hàng chuyển ra khỏi filter giữa lúc duyệt sẽ bị bỏ khỏi trang sau hay vẫn được giữ trong snapshot.

### High-water mark có giải quyết mọi thay đổi không?

Một cách giới hạn feed là lấy ID lớn nhất ở trang đầu và thêm:

~~~sql
AND id <= :initial_max_id
~~~

Điều này có thể chặn một số bản ghi mới có ID lớn hơn mốc ban đầu. Nhưng **không phải snapshot tổng quát**:

- Sequence/identity thường cấp ID trước khi transaction commit; transaction có ID nhỏ hơn vẫn có thể commit sau khi mốc được đọc.
- ID không đảm bảo thứ tự commit hoặc thời điểm nghiệp vụ.
- Hàng cũ có thể bị sửa hoặc xóa.
- Một hàng có ID nhỏ hơn mốc có thể được chèn sau đó nếu ứng dụng tự cấp ID.
- Các bộ lọc khác vẫn có thể thay đổi.

High-water mark hữu ích như **giới hạn phạm vi** cho một số feed, nhưng không thay thế snapshot khi cần point-in-time consistency nghiêm ngặt.

## 11. Thiết kế chỉ mục cho keyset pagination

Giả sử query luôn lọc theo tenant và sắp xếp bài mới nhất:

~~~sql
SELECT id, title, created_at
FROM articles
WHERE tenant_id = :tenant_id
  AND (
      created_at < :last_created_at
      OR (created_at = :last_created_at AND id < :last_id)
  )
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

Một index ứng viên trong PostgreSQL:

~~~sql
CREATE INDEX idx_articles_tenant_created_id
ON articles (tenant_id, created_at DESC, id DESC);
~~~

Vì `tenant_id` là điều kiện bằng, các cột tiếp theo hỗ trợ điều kiện seek và thứ tự. Nếu có filter trạng thái phổ biến:

~~~sql
WHERE tenant_id = ?
  AND status = 'PUBLISHED'
ORDER BY created_at DESC, id DESC
~~~

có thể đánh giá index:

~~~sql
CREATE INDEX idx_articles_tenant_status_created_id
ON articles (tenant_id, status, created_at DESC, id DESC);
~~~

Không nên tạo mọi index có thể nghĩ ra. Mỗi index làm tăng dung lượng và chi phí ghi; chọn theo workload, độ chọn lọc, tần suất query và kế hoạch thực thi. Kiểm tra bằng `EXPLAIN (ANALYZE, BUFFERS)` trong môi trường phù hợp.

### Thứ tự cột trong index phải khớp đường truy cập

Một index `(created_at, id, tenant_id)` không nhất thiết thay thế tốt index `(tenant_id, created_at, id)` cho truy vấn lọc tenant rồi seek theo thời gian. Quy tắc leftmost prefix và cách optimizer dùng index phụ thuộc engine; cần kiểm tra plan thực tế.

Nếu dùng nhiều kiểu sort, mỗi kiểu có thể cần index riêng hoặc đánh đổi giữa số lượng index và độ linh hoạt của API. Hạn chế client chọn tùy ý hàng chục cột sắp xếp vì khó bảo đảm hiệu năng và cursor semantics.

## 12. Triển khai keyset bằng Java JDBC

Ví dụ dưới đây lấy trang tiếp theo trong PostgreSQL, sắp xếp giảm dần theo `created_at` và `id`. Giả định:

- `created_at` là `TIMESTAMPTZ NOT NULL`.
- `id` là khóa duy nhất và không đổi.
- `tenant_id` được lấy từ ngữ cảnh đã xác thực.
- Cursor đã được xác minh và giải mã trước khi gọi repository.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import javax.sql.DataSource;

public final class ArticlePageRepository {
    public record Article(long id, OffsetDateTime createdAt, String title) {}

    public record Cursor(OffsetDateTime createdAt, long id) {}

    public record Page(List<Article> items, Optional<Cursor> nextCursor,
                       boolean hasNext) {}

    private final DataSource dataSource;

    public ArticlePageRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Page nextPage(long tenantId, Cursor cursor, int pageSize)
            throws SQLException {
        if (tenantId <= 0 || pageSize < 1 || pageSize > 100) {
            throw new IllegalArgumentException("Tham số phân trang không hợp lệ");
        }

        String sql = """
            SELECT id, created_at, title
            FROM articles
            WHERE tenant_id = ?
              AND (
                  created_at < ?
                  OR (created_at = ? AND id < ?)
              )
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """;

        List<Article> rows = new ArrayList<>();

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, tenantId);
            statement.setObject(2, cursor.createdAt());
            statement.setObject(3, cursor.createdAt());
            statement.setLong(4, cursor.id());
            statement.setInt(5, pageSize + 1);

            try (ResultSet result = statement.executeQuery()) {
                while (result.next()) {
                    rows.add(new Article(
                        result.getLong("id"),
                        result.getObject("created_at", OffsetDateTime.class),
                        result.getString("title")
                    ));
                }
            }
        }

        boolean hasNext = rows.size() > pageSize;
        if (hasNext) {
            rows.remove(rows.size() - 1);
        }

        Optional<Cursor> next = rows.isEmpty()
            ? Optional.empty()
            : Optional.of(new Cursor(
                rows.get(rows.size() - 1).createdAt(),
                rows.get(rows.size() - 1).id()
            ));

        return new Page(List.copyOf(rows), next, hasNext);
    }
}
~~~

Phương thức trên minh họa **trang kế tiếp**, không phải trang đầu: trang đầu cần query riêng không có điều kiện cursor và cũng lấy `pageSize + 1` hàng. Nếu `rows` rỗng, không tạo cursor tiếp theo. Cursor được lấy từ hàng cuối **đã trả cho client**.

Trong triển khai thật, cần thêm:

- Kiểm tra cursor đúng version, đúng sort order và đúng filter.
- Chữ ký hoặc token opaque để chống sửa cursor.
- Timeout, metrics, cancellation và xử lý lỗi kết nối.
- Giới hạn page size phía server.
- Quy tắc null và timezone/precision thống nhất.
- Trả cursor rỗng khi không còn trang tiếp theo theo hợp đồng API.
- Đảm bảo không giữ connection trong lúc client đọc response lâu hơn cần thiết.

Đoạn code dùng `OffsetDateTime` cho `TIMESTAMPTZ` với driver PostgreSQL hỗ trợ JDBC tương ứng. Kiểu mapping thời gian phải được xác minh theo phiên bản driver và schema thực tế.

### Trang đầu và trang kế tiếp

Trang đầu:

~~~sql
SELECT id, created_at, title
FROM articles
WHERE tenant_id = :tenant_id
ORDER BY created_at DESC, id DESC
LIMIT :page_size_plus_one;
~~~

Trang tiếp theo:

~~~sql
SELECT id, created_at, title
FROM articles
WHERE tenant_id = :tenant_id
  AND (created_at, id) < (:last_created_at, :last_id)
ORDER BY created_at DESC, id DESC
LIMIT :page_size_plus_one;
~~~

Cả hai truy vấn phải dùng cùng filter, cùng thứ tự và cùng định nghĩa dữ liệu. Nếu tenant, trạng thái hoặc từ khóa tìm kiếm thay đổi, hãy bắt đầu cursor mới.

## 13. Phân trang ngược và điều hướng giao diện

Keyset thường được mô tả theo chiều “next”. Nếu giao diện cần nút “previous”, có thể lưu cursor ở đầu trang hiện tại hoặc đảo hướng truy vấn.

Với thứ tự hiển thị giảm dần `created_at DESC, id DESC`, để lấy các hàng **mới hơn** hàng đầu tiên hiện tại, truy vấn có thể dùng điều kiện lớn hơn và đảo ORDER BY:

~~~sql
SELECT id, title, created_at
FROM articles
WHERE tenant_id = :tenant_id
  AND (created_at, id) > (:first_created_at, :first_id)
ORDER BY created_at ASC, id ASC
LIMIT :page_size_plus_one;
~~~

Kết quả được đọc theo chiều ngược để lấy trang gần nhất, sau đó ứng dụng đảo danh sách trước khi trả về theo thứ tự giảm dần. Chi tiết cursor đầu/cuối và cách xử lý trang đầu tiên cần được quy định rõ.

Nếu UI cần nhảy từ trang 2 sang trang 17, keyset không cung cấp vị trí số trang miễn phí. Có thể dùng OFFSET cho các tập nhỏ, lưu checkpoint cursor theo mốc, hoặc materialize thứ tự. Đừng thêm tính năng nhảy trang tùy ý mà không tính chi phí truy cập sâu.

## 14. Đọc từ replica và tính nhất quán sau ghi

Một nguồn khác gây bất ngờ là **read replica**. Ứng dụng ghi dữ liệu vào primary rồi đọc trang tiếp theo từ replica chưa bắt kịp. Người dùng có thể không thấy bản ghi vừa tạo hoặc nhìn thấy dữ liệu cũ hơn.

Cần xác định hợp đồng:

- **Eventual consistency:** chấp nhận replica trễ trong một khoảng được đo/giám sát.
- **Read-your-writes:** sau khi ghi thành công, người dùng phải thấy thay đổi của chính họ; có thể đọc từ primary trong một thời gian, định tuyến theo session/LSN hoặc cơ chế tương đương do hệ quản trị hỗ trợ.
- **Monotonic reads:** một người dùng không nên thấy trạng thái quay ngược khi chuyển giữa replica có độ trễ khác nhau; cần định tuyến/session consistency phù hợp.
- **Snapshot across pages:** các trang cần cùng phiên bản dữ liệu; chỉ pin cùng một replica cũng chưa chắc giữ cùng snapshot nếu mỗi request là transaction mới.

Cursor có thể chứa một mốc version/LSN nếu hệ thống có cơ chế đảm bảo replica đã replay đến mốc đó. Nhưng **chỉ nhét timestamp vào cursor không làm replica nhất quán**; server phải biết cách chờ hoặc định tuyến theo khả năng thực tế của hệ thống.

Với nghiệp vụ quan trọng, không nên mặc định đọc từ replica là tương đương đọc primary ngay sau commit. Cần đo replication lag và xác định cách xử lý khi replica chưa đạt yêu cầu.

## 15. Bảo mật và độ bền của cursor

Cursor là dữ liệu đầu vào từ client ở các request sau. Các kiểm soát cần có:

1. **Ký hoặc tra cứu token:** HMAC bảo vệ tính toàn vẹn; token ngẫu nhiên tra cứu server-side có thể ẩn nội dung.
2. **Ràng buộc filter:** cursor chỉ dùng cho tenant, quyền, filter và sort mà nó được tạo ra.
3. **Không thay quyền:** cursor không phải access token và không cấp quyền đọc hàng.
4. **Giới hạn kích thước:** từ chối token quá dài hoặc payload không hợp lệ trước khi truy vấn database.
5. **Versioning:** khi đổi cách sort hoặc schema cursor, xử lý token cũ theo quy tắc rõ ràng.
6. **Expiry:** cursor có thể hết hạn nếu gắn với snapshot hoặc trạng thái lưu phía server; với cursor thuần keyset có thể không cần expiry dài ngắn giống nhau, nhưng vẫn nên có chính sách.
7. **Không lộ thông tin nhạy cảm:** HMAC không mã hóa; tránh nhúng email, thông tin cá nhân hoặc dữ liệu nội bộ không cần thiết.

Một cursor hợp lệ chỉ chứng minh token phù hợp hợp đồng phân trang; repository vẫn phải áp dụng filter tenant và quyền truy cập trong câu truy vấn.

## 16. Kiểm thử tính nhất quán khi có ghi đồng thời

Kiểm thử phân trang chỉ với một dataset đứng yên sẽ không phát hiện các lỗi dịch chuyển. Nên tạo kịch bản có đồng thời:

### Kịch bản A — insert trước ranh giới

1. Tạo 100 hàng có thứ tự xác định.
2. Lấy trang đầu với page size 20.
3. Chèn một hàng mới đứng trước tất cả các hàng hiện tại.
4. Lấy trang 2 bằng OFFSET.
5. Kiểm tra hàng cuối trang 1 có bị lặp hay không.
6. Chạy lại cùng tình huống bằng keyset.

Kỳ vọng: OFFSET có thể lặp hàng; keyset không bị dịch ranh giới bởi hàng mới nằm trước cursor, nếu sort key của các hàng hiện tại không đổi.

### Kịch bản B — delete trước ranh giới

1. Lấy trang đầu.
2. Xóa một hàng đứng trước trang 2.
3. Tiếp tục OFFSET.
4. So sánh với keyset.

Kỳ vọng: OFFSET có thể bỏ qua hàng kế tiếp; keyset vẫn tiếp tục theo khóa cuối, trừ khi chính hàng mục tiêu bị xóa hoặc thay đổi khóa/filter.

### Kịch bản C — cập nhật trường sắp xếp

Một hàng chưa xem đổi `priority` hoặc `created_at` để di chuyển qua cursor. Kiểm tra lặp/bỏ sót và xác định đây là hành vi được chấp nhận của feed live hay vi phạm snapshot contract.

### Kịch bản D — snapshot transaction

1. Mở transaction REPEATABLE READ.
2. Đọc trang đầu.
3. Transaction khác insert/update/delete rồi commit.
4. Đọc trang hai trong transaction đầu.
5. Xác minh các hàng nhìn thấy vẫn theo snapshot ban đầu.
6. Thử chạy trang hai bằng connection/transaction mới và quan sát khác biệt.

### Kịch bản E — COUNT và trang dữ liệu

Chạy COUNT và query page trong các transaction khác nhau, đồng thời chèn/xóa bản ghi. Xác minh API có thể trả total và items không cùng snapshot. Sau đó thử cùng transaction snapshot nếu sản phẩm yêu cầu total chính xác.

### Kịch bản F — tenant và cursor bị sửa

Sửa filter, sort hoặc tenant trong cursor, thay đổi byte token, gửi token quá dài và gửi token hết hạn. Server phải từ chối theo hợp đồng và không trả dữ liệu ngoài phạm vi quyền.

Các test nên kiểm tra **ID thực tế của các hàng đã trả, thứ tự, tính duy nhất, số lượng, snapshot/version và quyền truy cập**. Chỉ kiểm tra HTTP 200 không chứng minh phân trang đúng.

## 17. Chỉ số vận hành cần theo dõi

| Nhóm | Chỉ số |
| --- | --- |
| Trải nghiệm | p50/p95/p99 latency theo page size và kiểu truy vấn |
| Thông lượng | Số trang/giây, số hàng trả về/giây |
| Database | Rows scanned/returned, buffer hit/read, CPU và I/O |
| Truy vấn | Query plan, index usage, số lần sort, offset depth |
| Đồng thời | Lock wait, deadlock, transaction duration |
| Snapshot | Tuổi transaction lâu nhất, snapshot giữ lâu, tác động vacuum |
| Cursor | Token lỗi/hết hạn, cursor không tương thích filter/sort |
| Replica | Replication lag, read-after-write miss |
| Độ đúng | ID lặp, khoảng khóa bị bỏ, số chênh lệch giữa total và items theo snapshot |

Phân tích theo **loại truy vấn và page depth**. Một trang đầu nhanh không chứng minh trang 5.000 nhanh; một p99 tổng thể cũng có thể che khuất truy vấn sâu hoặc filter hiếm.

Không đưa token cursor, tenant ID nhạy cảm, email hoặc nội dung filter tự do vào nhãn metrics có cardinality cao. Dùng tracing và log có kiểm soát để điều tra mà không làm lộ dữ liệu người dùng.

## 18. Chọn hợp đồng phân trang cho từng use case

| Use case | Hướng tiếp cận thường phù hợp | Điều phải công bố |
| --- | --- | --- |
| Danh sách quản trị nhỏ, có nhảy trang | OFFSET/LIMIT + ORDER BY toàn phần | Danh sách live; có thể thay đổi giữa các trang |
| Feed bài viết mới | Keyset theo created_at + ID | Bản ghi mới có thể xuất hiện tùy vị trí khóa; không phải snapshot |
| Lịch sử giao dịch bất biến | Keyset theo thời gian/ID ổn định | Quy tắc lưu giữ và thứ tự |
| Báo cáo cần tổng chính xác | Snapshot transaction ngắn hoặc materialized snapshot | Thời điểm chụp và phạm vi dữ liệu |
| Export hàng triệu dòng | Job export bất đồng bộ từ snapshot | Trạng thái job, file, expiry, checksum |
| Danh sách đọc từ replica | Keyset hoặc offset cùng chính sách consistency | Replica lag, read-your-writes và định tuyến |
| Search index đồng bộ bất đồng bộ | Cursor theo sort key của index | Độ trễ đồng bộ và xử lý tài liệu thay đổi |

Không nên dùng một loại phân trang duy nhất cho mọi API chỉ vì framework có sẵn một interface `Pageable`. Một abstraction tốt cần cho phép sản phẩm chọn semantics và giới hạn phù hợp.

## 19. Những nhầm lẫn thường gặp

**“ORDER BY created_at là đủ để phân trang ổn định.”** Không nếu nhiều hàng có cùng timestamp. Thêm khóa duy nhất làm tiêu chí phân xử.

**“OFFSET luôn trả đúng trang tiếp theo.”** Nó trả vị trí tương đối trong kết quả hiện tại; insert/delete phía trước có thể làm lặp hoặc bỏ sót.

**“Keyset đảm bảo tất cả trang cùng một snapshot.”** Không. Nó tiếp tục theo khóa, còn dữ liệu phía sau cursor vẫn có thể được thêm, sửa hoặc xóa.

**“Giữ cùng replica là đủ để có snapshot.”** Không. Hai transaction riêng trên cùng replica vẫn có thể nhìn snapshot khác nhau.

**“REPEATABLE READ có thể giữ mở cho tới khi người dùng duyệt xong.”** Có thể làm về mặt kỹ thuật trong một số kiến trúc nhưng thường giữ connection và snapshot quá lâu; cần cân nhắc vacuum, pool, timeout và vòng đời session.

**“Cursor Base64 không thể bị sửa.”** Sai. Base64 chỉ là encoding; cần HMAC hoặc token opaque nếu phải bảo vệ tính toàn vẹn.

**“Có total chính xác là trải nghiệm tốt hơn.”** Không phải lúc nào cũng vậy. COUNT có thể tốn kém và lệch snapshot; nhiều UI chỉ cần `hasNext`.

**“High-water mark ID là snapshot.”** Không. ID không đảm bảo thứ tự commit, và hàng cũ vẫn có thể đổi hoặc bị xóa.

**“Keyset loại bỏ nhu cầu index.”** Sai. Keyset cần index phù hợp để seek và sort hiệu quả.

**“Mọi thay đổi đồng thời đều là lỗi phân trang.”** Không. Nếu API công bố feed live, một bản ghi mới xuất hiện ở trang sau có thể là hành vi đúng. Lỗi nằm ở việc semantics không được xác định hoặc không được thực hiện như đã cam kết.

## 20. Câu hỏi tự kiểm tra và bài tập

**Câu 1.** Trang đầu dùng `ORDER BY created_at DESC LIMIT 20` nhưng không có khóa phụ. Vì sao hàng ở ranh giới trang có thể xuất hiện không ổn định?

**Đáp án:** Nhiều hàng có thể cùng `created_at`, nên thứ tự giữa chúng không được xác định duy nhất. Thêm khóa duy nhất, ví dụ `ORDER BY created_at DESC, id DESC`.

**Câu 2.** Một hàng mới được chèn lên đầu danh sách sau khi người dùng xem trang 1. Vì sao trang 2 với OFFSET có thể lặp hàng cuối trang 1?

**Đáp án:** Vị trí của các hàng cũ dịch xuống một vị trí, nhưng offset vẫn bỏ qua cùng số hàng như trước; do đó một hàng đã thấy có thể nằm lại trong phần được trả.

**Câu 3.** Keyset theo `(created_at, id)` có đảm bảo dữ liệu ở trang sau đúng như lúc người dùng bắt đầu duyệt không?

**Đáp án:** Không. Nó tránh dịch chuyển offset khi hàng mới nằm trước cursor, nhưng hàng phía sau có thể được thêm, sửa hoặc xóa. Cần snapshot nếu muốn point-in-time consistency.

**Câu 4.** PostgreSQL READ COMMITTED chạy hai câu SELECT trong cùng transaction có chắc dùng cùng snapshot không?

**Đáp án:** Không. Ở READ COMMITTED, mỗi statement có snapshot riêng. REPEATABLE READ trong cùng transaction mới giữ snapshot nhất quán theo semantics PostgreSQL.

**Câu 5.** Vì sao không nên giữ transaction REPEATABLE READ mở trong vài phút khi client bấm từng trang?

**Đáp án:** Nó giữ connection và snapshot lâu, có thể làm tăng áp lực lên connection pool và cản vacuum dọn phiên bản cũ. Nên cân nhắc cursor live, materialized snapshot hoặc export job.

**Câu 6.** API cần tổng số chính xác và các hàng thuộc cùng snapshot. Có thể chạy COUNT và SELECT page trong hai request riêng với transaction mặc định không?

**Đáp án:** Không bảo đảm. Cần cùng snapshot transaction hoặc một snapshot/materialization được quản lý cho cả total và dữ liệu.

**Bài tập A — mô phỏng OFFSET:** Tạo 60 bài viết, page size 10. Lấy trang 1, chèn một bài có sort key lớn nhất rồi lấy trang 2 bằng OFFSET. Ghi lại ID lặp. Làm lại với xóa một bài trước ranh giới và xác định ID bị bỏ.

**Bài tập B — xây keyset:** Tạo query PostgreSQL với `tenant_id`, `status` và `created_at DESC, id DESC`. Viết cursor gồm lastCreatedAt, lastId, sort version và filter fingerprint. Tạo index ghép phù hợp và kiểm tra plan với dữ liệu đủ lớn.

**Bài tập C — snapshot export:** Thiết kế một job export 1 triệu đơn hàng sao cho mọi hàng và total phản ánh cùng thời điểm. So sánh giữ một transaction read-only trong worker với materialize ID/giá trị, nêu chi phí và cách cleanup.

**Bài tập D — test concurrency:** Dùng hai connection JDBC độc lập. Connection A đọc trang đầu; connection B chèn, xóa hoặc sửa khóa sắp xếp; connection A tiếp tục trang 2. Chạy các biến thể READ COMMITTED, REPEATABLE READ, OFFSET và keyset; ghi lại khác biệt và giải thích theo hợp đồng API.

**Bài tập E — đọc từ replica:** Giả lập replica lag sau khi người dùng tạo bài viết. Thiết kế cách đảm bảo read-your-writes hoặc giải thích rõ thời gian trễ được chấp nhận. Không dùng timestamp cursor như một cơ chế đồng bộ giả định.

Khi thiết kế phân trang, hãy trả lời trước **người dùng đang duyệt một luồng live hay một snapshot cố định**. Sau đó chọn thứ tự toàn phần, OFFSET hoặc keyset, mức snapshot, cursor, index và chính sách đọc replica phù hợp. Sự nhất quán không đến chỉ từ câu SQL có LIMIT; nó đến từ hợp đồng dữ liệu được xác định rõ và được duy trì trong toàn bộ vòng đời truy vấn.
