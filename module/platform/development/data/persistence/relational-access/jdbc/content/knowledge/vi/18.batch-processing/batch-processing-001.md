# Khi nào nên gom nhiều thao tác thành một lô trong JDBC?

Khi làm việc với cơ sở dữ liệu quan hệ qua **JDBC (Java Database Connectivity)**, ứng dụng thường phải thực hiện nhiều câu lệnh có cấu trúc giống nhau: nhập hàng nghìn sản phẩm, ghi các sự kiện, cập nhật số lượng tồn kho, hoặc đồng bộ một danh sách bản ghi. Thực thi từng câu lệnh riêng lẻ tuy đơn giản nhưng có thể tạo ra nhiều lượt trao đổi giữa ứng dụng và cơ sở dữ liệu.

**Batch processing (xử lý theo lô)** cho phép gom nhiều lần thực thi câu lệnh thành một nhóm, sau đó gửi nhóm đó cho JDBC driver xử lý qua phương thức **executeBatch()**. Đây là cách có thể cải thiện hiệu suất khi khối lượng thao tác đủ lớn và mỗi thao tác không cần được đọc kết quả ngay lập tức.

Bài này tập trung vào câu hỏi thực tế: **khi nào nên dùng batch, khi nào không nên, chọn kích thước lô ra sao và cần lưu ý điều gì về lỗi và transaction?**

## 1. Lý do cân nhắc xử lý theo lô

Giả sử hệ thống cần cập nhật tồn kho cho 5.000 mã sản phẩm. Cách thực thi từng dòng:

~~~java
String sql = "UPDATE inventory SET quantity = quantity + ? WHERE sku = ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    for (StockAdjustment item : adjustments) {
        statement.setInt(1, item.getDelta());
        statement.setString(2, item.getSku());
        statement.executeUpdate(); // Thực thi sau mỗi lần bind
    }
}
~~~

Đoạn mã giả định biến connection và danh sách adjustments đã tồn tại. Với cách này, có 5.000 lời gọi executeUpdate(). Mỗi lời gọi có thể phát sinh chi phí giao tiếp, xử lý ở driver và cơ sở dữ liệu. Chi phí mạng đặc biệt đáng kể nếu ứng dụng và cơ sở dữ liệu ở các máy hoặc khu vực mạng khác nhau.

Với batch, ứng dụng thêm từng bộ tham số vào lô rồi gọi executeBatch():

~~~java
String sql = "UPDATE inventory SET quantity = quantity + ? WHERE sku = ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    for (StockAdjustment item : adjustments) {
        statement.setInt(1, item.getDelta());
        statement.setString(2, item.getSku());
        statement.addBatch();       // Thêm bộ tham số vào lô
    }
    int[] updateCounts = statement.executeBatch();
}
~~~

Các lần cập nhật dùng cùng **cấu trúc SQL**, nhưng có giá trị delta và sku khác nhau. JDBC driver nhận các bộ tham số để xử lý theo lô; tùy driver và DB, cách này có thể giảm chi phí so với nhiều lần gọi riêng lẻ.

**Lưu ý:** Batch không bảo đảm chính xác *một* lượt mạng hoặc một câu SQL duy nhất. Driver có thể gửi từng thao tác hoặc tối ưu/gộp chúng theo cách riêng. Vì vậy, cần đo hiệu năng với driver và hệ quản trị cơ sở dữ liệu thực tế.

## 2. Những trường hợp nên dùng batch

Batch thường phù hợp khi các thao tác có **cùng cấu trúc, độc lập về dữ liệu đầu ra và có số lượng đủ lớn**.

| Tình huống | Vì sao batch có ích? | Ví dụ |
| --- | --- | --- |
| Nhập dữ liệu hàng loạt | Nhiều hàng cùng mẫu INSERT, không cần xử lý ngay kết quả mỗi hàng. | Nhập 20.000 sản phẩm từ CSV đã được kiểm tra. |
| Cập nhật nhiều bản ghi | Cùng mẫu UPDATE, thay tham số theo từng bản ghi. | Điều chỉnh tồn kho của 2.000 mã hàng. |
| Ghi sự kiện nghiệp vụ | Ghi nhiều sự kiện theo một schema. | Lưu 1.000 sự kiện vận chuyển từ hàng đợi. |
| Đồng bộ dữ liệu định kỳ | Khối lượng lớn, có thể xử lý theo từng phần. | Đồng bộ trạng thái đơn hàng. |
| Xóa hàng loạt theo khóa | Cùng mẫu DELETE WHERE id = ?. | Dọn các bản ghi hết hạn theo danh sách ID. |

Một số dấu hiệu cho thấy batch là lựa chọn hợp lý:

1. **Nhiều thao tác tương tự:** Phần SQL giữ nguyên, chỉ khác bộ giá trị bind vào dấu hỏi chấm (?).
2. **Không cần kết quả sau từng thao tác:** Ứng dụng có thể đợi xử lý xong lô mới kiểm tra số hàng bị ảnh hưởng.
3. **Chi phí lặp lại đáng kể:** Nhiều lời gọi JDBC hoặc độ trễ mạng là một phần đáng kể trong thời gian xử lý.
4. **Có thể quản lý lỗi theo nhóm:** Ứng dụng đã xác định rollback, bỏ qua, sửa hoặc thử lại thế nào khi một phần lô gặp lỗi.
5. **Có giới hạn tài nguyên rõ ràng:** Mỗi lô kiểm soát được bộ nhớ, khóa và thời gian thực thi.

**Ví dụ:** Một tác vụ nhập 50.000 hàng có thể thử lô 100, 500 hoặc 1.000 hàng. Mục tiêu là cân bằng thời gian thực thi, tải cơ sở dữ liệu và khả năng khôi phục khi lỗi, chứ không phải luôn chọn lô lớn nhất.

## 3. Khi nào không nên gom thành lô?

Batch không phải lựa chọn phù hợp cho mọi loại công việc:

- **Chỉ có một hoặc vài thao tác:** Chi phí tổ chức batch có thể không đem lại lợi ích rõ ràng.
- **Mỗi bước cần kết quả của bước trước:** Ví dụ phải lấy ID của bản ghi vừa tạo để quyết định câu lệnh kế tiếp. Một số driver hỗ trợ generated keys khi batch, nhưng không nên mặc định mọi driver trả về khóa theo cách và thứ tự ứng dụng cần.
- **Truy vấn cần đọc dữ liệu ngay:** executeBatch() chủ yếu dành cho các lệnh không trả về ResultSet; không dùng nó để gom nhiều SELECT rồi mong nhận nhiều ResultSet theo cách thông thường.
- **Các thao tác có nghiệp vụ khác nhau:** Nếu mỗi thao tác cần nhánh xử lý hoặc kiểm tra riêng, batch có thể khiến việc phân tích lỗi khó hơn.
- **Một câu SQL đã xử lý được toàn bộ tập bản ghi:** Ví dụ câu UPDATE có WHERE chung có thể hiệu quả và rõ ràng hơn cập nhật từng ID qua batch.
- **Transaction dài gây vấn đề:** Một lô quá lớn có thể giữ khóa lâu, tăng transaction log, chiếm bộ nhớ hoặc xung đột với giao dịch khác.

Đừng gom thao tác chỉ vì có vòng lặp. Cần xác định **nút thắt là số lần tương tác với DB hay là bản thân câu SQL**. Nếu một câu SQL xử lý tập dữ liệu đủ tốt, hãy cân nhắc câu SQL đó trước.

## 4. Statement hay PreparedStatement để xử lý theo lô?

JDBC hỗ trợ batch qua cả Statement và PreparedStatement:

| Tiêu chí | Statement | PreparedStatement |
| --- | --- | --- |
| Thêm thao tác | addBatch(sql) | Bind bằng setXxx(...), rồi gọi addBatch() không tham số. |
| Cấu trúc lệnh | Có thể thêm các chuỗi SQL khác nhau. | Một cấu trúc SQL, nhiều bộ tham số. |
| Truyền dữ liệu thay đổi | Lập trình viên xây dựng chuỗi SQL. | Bind giá trị bằng placeholder ?. |
| Đầu vào từ bên ngoài | Rủi ro SQL injection nếu nối chuỗi trực tiếp. | Tách giá trị khỏi cú pháp SQL ở các vị trí có thể bind. |
| Trường hợp thường gặp | Các câu SQL tĩnh, xác định trước. | Nhiều INSERT, UPDATE, DELETE cùng mẫu. |

Ví dụ batch với Statement dùng các câu SQL **cố định**:

~~~java
try (Statement statement = connection.createStatement()) {
    statement.addBatch(
            "DELETE FROM session_tokens WHERE expires_at < CURRENT_TIMESTAMP");
    statement.addBatch(
            "DELETE FROM temporary_exports WHERE expires_at < CURRENT_TIMESTAMP");
    int[] counts = statement.executeBatch();
}
~~~

Với dữ liệu thay đổi theo người dùng hoặc theo từng bản ghi, **ưu tiên PreparedStatement**. Placeholder chỉ đại diện cho *giá trị* tại vị trí cú pháp SQL cho phép: không thể dùng dấu ? thay thế tên bảng, tên cột hay từ khóa.

## 5. Quy trình batch với PreparedStatement

~~~mermaid
flowchart TD
    A[Chuẩn bị SQL với dấu ?] --> B[Tạo PreparedStatement]
    B --> C[Bind tham số của một bản ghi]
    C --> D[addBatch]
    D --> E{Đã đủ kích thước lô?}
    E -- Rồi --> F[executeBatch]
    F --> G{Còn dữ liệu?}
    G -- Có --> C
    G -- Không --> I[Kiểm tra kết quả và commit]
    E -- Chưa --> H{Còn dữ liệu?}
    H -- Có --> C
    H -- Không --> J[executeBatch lô cuối]
    J --> I
~~~

Các phương thức chính:

- **setXxx(index, value):** Gán tham số vào vị trí ?, chỉ số bắt đầu từ **1**.
- **addBatch():** Đưa bộ giá trị đã bind vào lô đang chờ.
- **executeBatch():** Thực thi lô, trả về mảng int[] biểu diễn kết quả từng thao tác.
- **clearBatch():** Loại bỏ các thao tác đang chờ nếu ứng dụng quyết định hủy lô.
- **executeLargeBatch():** Biến thể trả về long[] (JDBC 4.2), hữu ích khi số hàng có thể vượt giới hạn int; cần kiểm tra hỗ trợ của driver.

Khi tái sử dụng PreparedStatement, giá trị tham số có thể vẫn tồn tại từ lần bind trước. Vì vậy **luôn bind đủ các tham số cho từng bản ghi** trước khi addBatch(), kể cả khi một vài giá trị tình cờ trùng nhau.

## 6. Ví dụ đầy đủ: cập nhật tồn kho theo từng lô

Đoạn Java sau cập nhật từng lượng tăng/giảm tồn kho, gom tối đa batchSize thao tác vào mỗi lần executeBatch(), đồng thời sử dụng transaction để có thể rollback cả đợt nếu lỗi. DataSource được ứng dụng cấu hình sẵn; ví dụ giả định bảng inventory có cột sku và quantity.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.List;
import javax.sql.DataSource;

public final class InventoryBatchWriter {
    private static final String SQL =
            "UPDATE inventory SET quantity = quantity + ? WHERE sku = ?";

    public static void apply(
            DataSource dataSource,
            List<StockAdjustment> adjustments,
            int batchSize) throws SQLException {

        if (batchSize <= 0) {
            throw new IllegalArgumentException("batchSize phải lớn hơn 0");
        }
        if (adjustments == null) {
            throw new IllegalArgumentException("adjustments không được null");
        }
        if (adjustments.isEmpty()) {
            return;
        }

        try (Connection connection = dataSource.getConnection()) {
            boolean previousAutoCommit = connection.getAutoCommit();
            connection.setAutoCommit(false);

            try (PreparedStatement statement = connection.prepareStatement(SQL)) {
                int queued = 0;

                for (StockAdjustment item : adjustments) {
                    statement.setInt(1, item.getDelta());
                    statement.setString(2, item.getSku());
                    statement.addBatch();
                    queued++;

                    if (queued == batchSize) {
                        checkCounts(statement.executeBatch());
                        queued = 0;
                    }
                }

                // Không bỏ sót lô cuối khi số phần tử không chia hết batchSize.
                if (queued > 0) {
                    checkCounts(statement.executeBatch());
                }

                connection.commit();
            } catch (SQLException | RuntimeException error) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            } finally {
                connection.setAutoCommit(previousAutoCommit);
            }
        }
    }

    private static void checkCounts(int[] counts) throws SQLException {
        for (int count : counts) {
            if (count == Statement.EXECUTE_FAILED) {
                throw new SQLException("Có thao tác trong batch thất bại");
            }
        }
    }

    public static final class StockAdjustment {
        private final String sku;
        private final int delta;

        public StockAdjustment(String sku, int delta) {
            this.sku = sku;
            this.delta = delta;
        }

        public String getSku() {
            return sku;
        }

        public int getDelta() {
            return delta;
        }
    }
}
~~~

Ví dụ sử dụng:

~~~java
List<InventoryBatchWriter.StockAdjustment> items =
        java.util.Arrays.asList(
                new InventoryBatchWriter.StockAdjustment("SKU-101", 5),
                new InventoryBatchWriter.StockAdjustment("SKU-102", -2),
                new InventoryBatchWriter.StockAdjustment("SKU-103", 8));

InventoryBatchWriter.apply(dataSource, items, 2);
~~~

Với ba thao tác và batchSize = 2, đoạn mã gọi executeBatch() **hai lần**: lô đầu có hai thao tác, lô sau có một thao tác; sau đó mới commit(). Ví dụ phân biệt **kích thước lô** với **phạm vi transaction**: hai lô JDBC vẫn thuộc cùng một transaction vì chúng dùng cùng Connection với autoCommit = false.

checkCounts() chỉ phát hiện mã EXECUTE_FAILED; nó không yêu cầu số hàng cập nhật phải bằng 1. Nếu mỗi sku bắt buộc phải tồn tại, ứng dụng cần thêm quy tắc nghiệp vụ để xử lý kết quả cập nhật 0 hàng. Nếu driver trả về SUCCESS_NO_INFO, không thể suy ra chính xác số hàng từ kết quả đó.

Ví dụ sử dụng transaction giả định cơ sở dữ liệu/bảng có **hỗ trợ transaction và rollback** cho các lệnh UPDATE này. Việc khôi phục autoCommit trong finally giúp trả cấu hình về trạng thái trước đó khi kết nối được đóng/trả cho pool.

## 7. Transaction và batch là hai khái niệm khác nhau

Batch liên quan đến **cách nhóm các lời gọi thực thi**; transaction liên quan đến **phạm vi thành công hoặc rollback của thay đổi dữ liệu**.

| Cách chạy | Điều gì xảy ra khi có lỗi giữa chừng? | Phù hợp khi |
| --- | --- | --- |
| Nhiều lệnh riêng, auto-commit bật | Những lệnh đã commit thường không bị rollback cùng lệnh sau. | Tác vụ đơn giản, mỗi lệnh độc lập. |
| Batch, auto-commit bật | Không mặc định rollback toàn bộ các thao tác đã thành công; hành vi tùy driver/DB. | Chấp nhận thành công từng phần và có cơ chế xử lý lại. |
| Batch trong một transaction | Có thể rollback các thay đổi nếu DB hỗ trợ. | Yêu cầu **toàn bộ cùng thành công hoặc thất bại**. |
| Nhiều batch, commit sau mỗi lô | Lô đã commit là một phần tiến độ; lỗi ở lô sau không đảo ngược lô trước. | Nhập dữ liệu rất lớn và có cơ chế tiếp tục an toàn. |

Nếu nghiệp vụ yêu cầu **all-or-nothing**, có thể chạy nhiều batch nhỏ trong **một transaction** rồi commit một lần như ví dụ ở trên. Tuy nhiên, transaction quá lớn có thể tăng thời gian giữ khóa và chi phí phục hồi.

Nếu tác vụ đồng bộ có thể chia thành các lô độc lập, một chiến lược khác là **commit sau từng lô**, ghi nhận tiến độ và xử lý tiếp từ lô chưa thành công. Khi đó cần cơ chế tránh ghi trùng khi chạy lại: khóa duy nhất, idempotency key hoặc cập nhật có điều kiện phù hợp với nghiệp vụ.

**Quan trọng:** addBatch() không tự commit; executeBatch() cũng không tự tạo ranh giới transaction độc lập với thiết lập của Connection.

## 8. Nếu một phần lô thất bại thì sao?

Khi gặp lỗi trong quá trình thực thi batch, JDBC có thể ném **BatchUpdateException**, một lớp con của SQLException. Ngoại lệ có thể cung cấp mảng kết quả từ getUpdateCounts() (hoặc getLargeUpdateCounts() với long[]):

~~~java
try {
    int[] counts = statement.executeBatch();
    // Đọc counts nếu cần thống kê từng lệnh.
} catch (java.sql.BatchUpdateException e) {
    int[] partialCounts = e.getUpdateCounts();
    System.err.println("Số kết quả nhận được: " + partialCounts.length);
    throw e; // Để tầng quản lý transaction quyết định rollback.
}
~~~

| Giá trị phần tử | Ý nghĩa |
| --- | --- |
| Số nguyên không âm | Số hàng bị tác động được driver báo cho thao tác tương ứng. |
| Statement.SUCCESS_NO_INFO (-2) | Thành công, nhưng không biết/không trả về số hàng chính xác. |
| Statement.EXECUTE_FAILED (-3) | Thao tác thất bại; có thể xuất hiện khi driver tiếp tục sau lỗi. |

Sau khi một lệnh thất bại, driver **có thể dừng ngay hoặc tiếp tục những lệnh còn lại**. Vì vậy, mảng từ ngoại lệ có thể ngắn hơn số thao tác trong lô hoặc chứa các mã EXECUTE_FAILED. Không được mặc định mọi thao tác trước lỗi đều đã commit hay mọi thao tác sau lỗi đều chưa chạy.

Chiến lược xử lý thường là:

1. **Rollback transaction** nếu toàn bộ công việc phải cùng thành công và cơ sở dữ liệu hỗ trợ rollback.
2. **Ghi log thông tin cần thiết** (loại thao tác, vị trí lô, SQLState, error code), tránh ghi nguyên văn dữ liệu nhạy cảm.
3. **Phân loại lỗi:** Vi phạm khóa duy nhất hoặc dữ liệu sai cần sửa đầu vào; lỗi kết nối hoặc deadlock có thể cần retry theo chính sách.
4. **Thử lại có kiểm soát:** Xác định trạng thái commit và bảo đảm thao tác an toàn khi lặp lại, tránh cộng tồn kho hoặc ghi sự kiện hai lần.

Không nên coi việc executeBatch() ném ngoại lệ là bằng chứng mọi thay đổi đã được tự động hoàn tác; ứng dụng phải quản lý transaction đúng cách.

## 9. Chọn kích thước lô như thế nào?

Không có batchSize tối ưu cho mọi ứng dụng. Lô quá nhỏ có thể làm mất lợi ích giảm lời gọi; lô quá lớn có thể tăng bộ nhớ, thời gian chạy, tải cơ sở dữ liệu và chi phí khôi phục khi lỗi.

| Kích thước | Ưu điểm có thể có | Đánh đổi cần chú ý |
| --- | --- | --- |
| Nhỏ, ví dụ 20–100 | Dễ kiểm soát lỗi, ít dữ liệu chờ trong bộ nhớ. | Nhiều lời gọi executeBatch() hơn. |
| Vừa, ví dụ 200–1.000 | Điểm bắt đầu hợp lý để benchmark. | Cần xem giới hạn thực tế của driver/DB. |
| Lớn, vài nghìn trở lên | Có thể giảm thêm overhead ở một số hệ thống. | Nguy cơ timeout, giới hạn packet/parameter, khóa lâu, tốn bộ nhớ. |

Những khoảng trên chỉ là **giá trị thử nghiệm**, không phải chuẩn JDBC. Hãy benchmark với dữ liệu và môi trường gần sản xuất:

- Thử nhiều batchSize, đo tổng thời gian, throughput (bản ghi/giây), độ trễ, CPU và bộ nhớ.
- Theo dõi giới hạn câu lệnh, kích thước gói tin, số tham số, transaction log và mức tranh chấp khóa.
- Thử lỗi giữa lô, rollback, retry và khôi phục sau khi tiến trình bị gián đoạn.
- Quan sát tác động lên truy vấn khác: lô lớn có thể tăng tốc import nhưng cũng tăng độ trễ của người dùng đang giao dịch.

Nếu dữ liệu lớn hơn bộ nhớ sẵn có, hãy **đọc theo luồng/chunk**, tạo một lô có giới hạn, thực thi rồi đọc chunk tiếp theo. Không cần tải hàng triệu bản ghi cùng lúc vào List mới có thể dùng JDBC batch.

## 10. Batch không đồng nghĩa với SQL bulk operation

Có ba cách xử lý nhiều bản ghi, cần chọn theo yêu cầu:

~~~sql
-- (A) Chạy nhiều lần, mỗi lần một bộ tham số:
INSERT INTO products (id, name) VALUES (?, ?);

-- (B) Một SQL chứa nhiều hàng, nếu DB hỗ trợ:
INSERT INTO products (id, name)
VALUES (?, ?), (?, ?), (?, ?);

-- (C) Một SQL tác động đến cả tập dữ liệu:
UPDATE products SET active = FALSE WHERE expired_at < ?;
~~~

Với cách (A), ứng dụng có thể dùng PreparedStatement.addBatch() để xử lý nhiều bộ tham số cho cùng một SQL. Cách (B) là **multi-row insert**: một câu SQL có nhiều hàng, cần tạo số placeholder tương ứng và kiểm tra giới hạn DB; một số driver có thể tự chuyển batch thành dạng tương tự. Cách (C) là **set-based SQL**: cơ sở dữ liệu tự thao tác trên tập hàng thỏa điều kiện.

Nếu có thể mô tả nghiệp vụ bằng một câu SQL tác động trên tập dữ liệu, cách (C) thường đáng cân nhắc trước vì cơ sở dữ liệu tối ưu cho xử lý tập hợp. Batch đặc biệt hữu ích khi mỗi hàng có các giá trị tham số khác nhau hoặc dữ liệu đến theo từng bản ghi từ ứng dụng.

## 11. Những sai lầm thường gặp

| Sai lầm | Cách khắc phục |
| --- | --- |
| Gọi executeBatch() sau **mỗi** addBatch() | Chỉ chạy khi đạt kích thước lô hoặc hết dữ liệu. |
| Không chạy lô cuối khi số phần tử không chia hết | Sau vòng lặp, nếu còn dữ liệu chờ thì gọi executeBatch(). |
| Cho rằng batch tự tạo transaction nguyên tử | Quản lý autoCommit, commit và rollback rõ ràng. |
| Dùng một lô khổng lồ vì nghĩ luôn nhanh nhất | Đặt giới hạn số thao tác và đo hiệu năng thực tế. |
| Mặc định updateCounts[i] luôn là số hàng | Xử lý SUCCESS_NO_INFO và EXECUTE_FAILED. |
| Bỏ qua trạng thái thành công từng phần khi có lỗi | Xử lý BatchUpdateException, transaction và phương án retry. |
| Nối dữ liệu người dùng vào SQL bằng Statement.addBatch(sql) | Dùng PreparedStatement và bind tham số cho dữ liệu biến đổi. |
| Chạy lại lô không kiểm soát sau lỗi kết nối | Kiểm tra trạng thái transaction và tính idempotent trước khi retry. |
| Mong nhận nhiều ResultSet từ executeBatch() | Dùng cơ chế truy vấn phù hợp nếu cần đọc từng SELECT. |
| Phụ thuộc tuyệt đối vào generated keys trong batch | Kiểm tra hỗ trợ driver/DB và cách ánh xạ khóa về từng bản ghi. |

## 12. Câu hỏi tự kiểm tra

1. Vì sao 10.000 lần executeUpdate() riêng lẻ có thể chậm hơn việc gom thành các lô?
2. Khi nào nên dùng một câu UPDATE tác động nhiều hàng thay vì batch nhiều UPDATE theo ID?
3. addBatch() và executeBatch() khác nhau ở điểm nào?
4. Nếu muốn rollback **toàn bộ** 20 lô khi lô thứ 18 thất bại, cần tổ chức transaction ra sao?
5. SUCCESS_NO_INFO và EXECUTE_FAILED có ý nghĩa gì?
6. Tại sao không nên chọn batchSize = 100000 chỉ vì dữ liệu có 100.000 bản ghi?
7. Nếu mất kết nối sau khi gửi một lô tăng tồn kho, vì sao chạy lại lô ngay có thể gây sai số?

**Ghi nhớ:** Nên gom nhiều thao tác JDBC thành batch khi chúng có cấu trúc tương tự, số lượng đủ lớn và có thể xử lý kết quả theo nhóm. Batch giúp giảm overhead lặp lại nhưng hiệu quả phụ thuộc driver và DB. Hãy dùng PreparedStatement, giới hạn kích thước lô, xác định rõ phạm vi transaction, xử lý kết quả từng phần và đo hiệu năng trước khi đưa vào vận hành.
