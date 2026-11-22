# Nguồn dữ liệu chuẩn và trách nhiệm sở hữu dữ liệu

Trong mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**, việc chọn cơ sở dữ liệu, thiết kế lược đồ, truy vấn, chỉ mục, giao dịch và cơ chế đồng thời chỉ có ý nghĩa khi ứng dụng biết rõ **dữ liệu nào có thẩm quyền** và **thành phần nào được phép thay đổi dữ liệu đó**. Hai quyết định này tạo nền cho ranh giới persistence của ứng dụng Java, đồng thời chi phối cách xử lý lỗi kết nối, tiến hóa schema, bảo mật, sao lưu và tối ưu hiệu năng.

Sau bài học, người học có thể:

- Phân biệt nguồn dữ liệu chuẩn (source of truth) với bản sao, cache, mô hình đọc và dữ liệu tổng hợp.
- Chỉ định chủ sở hữu cho từng nhóm dữ liệu, quy tắc nghiệp vụ và thao tác ghi.
- Thiết kế luồng đọc/ghi qua ranh giới sở hữu, kể cả khi nhiều dịch vụ cùng tham gia một quy trình.
- Nhận diện rủi ro ghi trùng, cập nhật cạnh tranh, dữ liệu chậm đồng bộ và khôi phục sau sự cố.

## 1. Nguồn dữ liệu chuẩn là gì?

**Nguồn dữ liệu chuẩn** là nơi có thẩm quyền xác nhận giá trị đúng của **một sự kiện hoặc thuộc tính nghiệp vụ cụ thể**, tại một thời điểm và trong một phạm vi đã xác định. Khi hai bản sao không nhất quán, hệ thống phải biết tham chiếu nguồn nào để đối soát và sửa bản còn lại.

Ví dụ, một nền tảng bán hàng có thể lưu thông tin khách hàng trong nhiều nơi:

- Dịch vụ hồ sơ khách hàng quản lý **email liên hệ hiện tại**.
- Đơn hàng lưu **email nhận thông báo tại thời điểm đặt hàng** để giữ nguyên lịch sử giao dịch.
- Hệ thống tìm kiếm lưu một bản sao email nhằm hiển thị nhanh.
- Kho dữ liệu phân tích lưu lịch sử thay đổi để tạo báo cáo.

Các giá trị khác nhau chưa chắc là sai. Email hiện tại và email tại thời điểm đặt hàng là **hai sự kiện nghiệp vụ khác nhau**, có thể có hai chủ sở hữu khác nhau. Vì vậy, không thể chỉ hỏi “database nào là nguồn chuẩn?”; phải hỏi **“nguồn chuẩn cho trường dữ liệu nào, ở thời điểm nào, phục vụ quyết định nào?”**.

### 1.1. Phân biệt các loại nơi lưu dữ liệu

| Loại | Vai trò | Có được tự quyết định giá trị nghiệp vụ không? |
| --- | --- | --- |
| **Nguồn chuẩn** | Duy trì trạng thái có thẩm quyền và các bất biến nghiệp vụ | Có, theo quyền ghi và quy tắc đã công bố |
| **Bản sao đọc (read replica)** | Phục vụ truy vấn, giảm tải cho nơi ghi | Không; có thể trễ so với bản chính |
| **Cache** | Giảm độ trễ và số lần truy vấn | Không; có thời hạn hoặc cơ chế vô hiệu hóa |
| **Mô hình đọc / materialized view** | Tổng hợp dữ liệu để tìm kiếm, hiển thị, báo cáo | Không; phải có cách tạo lại từ nguồn |
| **Kho phân tích** | Phục vụ số liệu tổng hợp và lịch sử | Có thể là nguồn chuẩn cho *chỉ số đã định nghĩa*, nhưng không mặc nhiên là nguồn chuẩn cho trạng thái giao dịch |
| **Hệ thống bên ngoài** | Nắm giữ một sự kiện nằm ngoài quyền kiểm soát của ứng dụng | Có thể là nguồn chuẩn cho sự kiện đó, ví dụ kết quả thanh toán tại nhà cung cấp |

Trong hệ thống dùng **event sourcing**, nhật ký sự kiện bất biến có thể là nguồn chuẩn và trạng thái hiện tại là kết quả dựng lại từ các sự kiện. Trong hệ thống CRUD thông thường, trạng thái được lưu trong các bảng giao dịch có thể là nguồn chuẩn; log hay thông điệp sự kiện không tự động thay thế vai trò đó.

**Nguồn chuẩn là một cam kết về quyền quyết định dữ liệu, không đồng nghĩa với việc toàn hệ thống chỉ có một máy chủ, một database hoặc một bản sao duy nhất.** Có thể triển khai replication, backup và cache mà vẫn duy trì một đường ghi có thẩm quyền rõ ràng.

## 2. Trách nhiệm sở hữu dữ liệu

**Chủ sở hữu dữ liệu (data owner)** chịu trách nhiệm định nghĩa ý nghĩa, các quy tắc hợp lệ, quyền thay đổi, vòng đời và chất lượng của một nhóm dữ liệu. Trong thiết kế phần mềm, trách nhiệm đó thường gắn với một **ngữ cảnh nghiệp vụ (bounded context)** hoặc một module có ranh giới rõ. Người vận hành cơ sở dữ liệu có thể quản trị hạ tầng nhưng không vì thế có quyền tự thay đổi quy tắc nghiệp vụ của mọi bảng.

Nên phân biệt ba trách nhiệm liên quan:

| Trách nhiệm | Quyết định chính |
| --- | --- |
| **Nghiệp vụ** | Trường dữ liệu có nghĩa gì; trạng thái nào hợp lệ; khi nào được sửa hoặc xóa |
| **Ứng dụng / kỹ thuật** | API hoặc command nào được ghi; giao dịch, kiểm tra, khóa và migration được thực thi ra sao |
| **Vận hành / quản trị** | Ai được truy cập; sao lưu, khôi phục, theo dõi, xử lý sự cố và kiểm toán như thế nào |

Trong một đội nhỏ, cùng một nhóm có thể đảm nhiệm cả ba vai trò; điều quan trọng là **trách nhiệm phải được nêu rõ và kiểm chứng được**.

### 2.1. Ví dụ phân định quyền sở hữu

| Dữ liệu / sự kiện | Thành phần có thẩm quyền | Quy tắc quan trọng | Thành phần khác tiếp cận ra sao |
| --- | --- | --- | --- |
| Hồ sơ khách hàng hiện tại | Customer | Email liên hệ phải hợp lệ; quản lý thay đổi thông tin | Truy vấn API hoặc nhận sự kiện cập nhật |
| Giá và điều kiện bán đang có hiệu lực | Catalog / Pricing | Giá áp dụng theo thời gian và chính sách | Đọc hợp đồng công bố giá; đơn hàng lưu giá đã chốt |
| Đơn hàng và trạng thái xử lý | Order | Chỉ cho phép các bước chuyển trạng thái hợp lệ | Truy vấn Order API, nhận sự kiện đơn hàng |
| Số lượng hàng khả dụng và phiếu giữ hàng | Inventory | Không giữ vượt số lượng khả dụng | Gửi lệnh giữ/hoàn hàng; không ghi trực tiếp bảng tồn kho |
| Kết quả giao dịch tại cổng thanh toán | Nhà cung cấp thanh toán | Mã giao dịch và kết quả được xác nhận từ nhà cung cấp | Payment xác minh webhook/API và đối soát |
| Trạng thái xử lý thanh toán nội bộ | Payment | Ghi nhận đúng một lần theo mã giao dịch, quản lý hoàn tiền | Order nhận kết quả nghiệp vụ đã xác minh |

Hai trường tưởng như giống nhau vẫn có thể có chủ sở hữu riêng: **giá niêm yết hiện tại** thuộc Pricing, còn **giá từng dòng đơn hàng đã xác nhận** thuộc Order. Đơn hàng không nên thay đổi lịch sử chỉ vì bảng giá hiện tại thay đổi.

### 2.2. Các câu hỏi cần trả lời khi giao quyền sở hữu

Với mỗi loại dữ liệu quan trọng, hãy xác định:

1. **Ý nghĩa và định danh:** bản ghi đại diện cho sự kiện nào, khóa duy nhất là gì, phiên bản hoặc mốc thời gian nào có ý nghĩa?
2. **Quyền tạo/sửa/xóa:** module nào kiểm tra và thực hiện thao tác; quyền nào dành cho tác vụ quản trị hoặc sửa dữ liệu?
3. **Bất biến nghiệp vụ:** điều kiện nào luôn phải đúng, chẳng hạn tồn kho không âm hoặc đơn hàng không được xác nhận hai lần?
4. **Hợp đồng truy cập:** bên khác đọc qua API, sự kiện, truy vấn được cấp quyền hay mô hình đọc nào?
5. **Mức nhất quán:** bên đọc cần kết quả mới nhất ngay lập tức hay chấp nhận trễ vài giây?
6. **Vòng đời và trách nhiệm khôi phục:** lưu bao lâu, ai giải quyết sai lệch, dữ liệu nào có thể dựng lại?

Nếu những câu hỏi này chưa có câu trả lời, việc chọn SQL hay NoSQL, thêm cache hoặc tách microservice sẽ khó giải quyết tận gốc xung đột dữ liệu.

## 3. Ranh giới persistence trong ứng dụng Java

Ranh giới sở hữu nên được thể hiện bằng **đường ghi có kiểm soát**. Dù chạy trong một monolith hay nhiều service, mã của module Order không được âm thầm sửa trạng thái Inventory bằng một truy vấn SQL trực tiếp chỉ vì hai module dùng chung hệ quản trị cơ sở dữ liệu.

Một cách tổ chức đơn giản:

- **Domain / application service** nhận command, kiểm tra quyền và điều phối quy tắc nghiệp vụ.
- **Repository** của module sở hữu chịu trách nhiệm đọc/ghi các bảng thuộc module đó.
- **Cơ sở dữ liệu giao dịch** duy trì khóa, ràng buộc, tính nguyên tử và cơ chế đồng thời.
- **API hoặc sự kiện** là hợp đồng để module khác yêu cầu hành động hay nhận thông tin.

Sơ đồ dưới đây mô tả quyền thay đổi theo từng miền dữ liệu:

~~~mermaid
flowchart LR
    UI["Ứng dụng / API"] --> O["Order"]
    O -->|"Yêu cầu giữ hàng"| I["Inventory"]
    O -->|"Yêu cầu thanh toán"| P["Payment"]
    I -->|"StockReserved"| O
    P -->|"PaymentConfirmed"| O
    O --> OD[("Order store")]
    I --> ID[("Inventory store")]
    P --> PD[("Payment store")]
    O -->|"Phát sự kiện"| RM["Mô hình đọc / báo cáo"]
~~~

Mỗi store trong sơ đồ tượng trưng cho **phạm vi dữ liệu sở hữu**, không bắt buộc là một máy chủ vật lý riêng. Trong monolith, có thể dùng cùng database với schema, repository, quyền truy cập và quy tắc thay đổi tách biệt. Khi triển khai thành các dịch vụ độc lập, không nên để dịch vụ này tự cập nhật bảng nội bộ của dịch vụ kia.

### 3.1. Bất biến phải được bảo vệ tại nơi sở hữu

Giả sử Inventory quản lý lượng hàng còn có thể giữ. Điều kiện “không giữ quá tồn kho khả dụng” phải được bảo vệ ngay tại nơi ghi, ngay cả khi hai yêu cầu đặt hàng đến đồng thời:

~~~sql
CREATE TABLE inventory_stock (
    sku VARCHAR(64) PRIMARY KEY,
    available INTEGER NOT NULL CHECK (available >= 0),
    version BIGINT NOT NULL DEFAULT 0
);

UPDATE inventory_stock
SET available = available - ?,
    version = version + 1
WHERE sku = ?
  AND available >= ?;
~~~

Ứng dụng truyền cùng một số lượng dương vào tham số thứ nhất và thứ ba. Nếu số dòng cập nhật bằng **1**, thao tác giảm tồn kho thành công; nếu bằng **0**, mã hàng không tồn tại hoặc số lượng không đủ. Câu lệnh cập nhật có điều kiện giúp kiểm tra và thay đổi trạng thái trong **một thao tác nguyên tử** tại cơ sở dữ liệu, thay vì “đọc số lượng rồi mới quyết định ghi” dựa trên giá trị có thể đã cũ.

Ví dụ với JDBC, lớp truy cập dữ liệu có thể đưa thao tác vào một giao dịch:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class InventoryRepository {
    private final DataSource dataSource;

    public InventoryRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean decreaseIfAvailable(String sku, int quantity)
            throws SQLException {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        String sql = "UPDATE inventory_stock "
                + "SET available = available - ?, version = version + 1 "
                + "WHERE sku = ? AND available >= ?";

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                int changed;
                try (PreparedStatement statement =
                        connection.prepareStatement(sql)) {
                    statement.setInt(1, quantity);
                    statement.setString(2, sku);
                    statement.setInt(3, quantity);
                    changed = statement.executeUpdate();
                }

                if (changed != 1) {
                    connection.rollback();
                    return false;
                }

                connection.commit();
                return true;
            } catch (SQLException error) {
                connection.rollback();
                throw error;
            }
        }
    }
}
~~~

Đoạn mã minh họa cách chủ sở hữu bảo vệ **một lần cập nhật cục bộ**. Nó **chưa cung cấp tính idempotent cho yêu cầu nghiệp vụ**: nếu client gửi lại cùng một lệnh sau khi mất kết nối, số lượng có thể bị trừ lần nữa. Trong hệ thống thật, cần bổ sung định danh yêu cầu và bản ghi giữ hàng như phần tiếp theo.

Một số hệ quản trị có cú pháp, hỗ trợ ràng buộc hoặc hành vi khóa khác nhau; cần kiểm chứng theo loại database và mức cô lập giao dịch đang dùng. Không nên thay câu lệnh có điều kiện bằng chuỗi đọc rồi ghi mà không có cơ chế khóa hoặc kiểm tra phiên bản phù hợp.

## 4. Nhiều thành phần cùng tham gia: ai là nơi xác nhận?

Quy trình đặt hàng thường đi qua Order, Inventory và Payment. **Mỗi module chỉ xác nhận sự kiện thuộc trách nhiệm của mình**:

1. Order tạo đơn ở trạng thái đang xử lý, lưu mã đơn duy nhất.
2. Order gửi yêu cầu giữ hàng đến Inventory, kèm một **request ID** ổn định.
3. Inventory kiểm tra tồn kho và lưu phiếu giữ hàng; chỉ Inventory được xác nhận kết quả giữ hàng.
4. Payment thực hiện hoặc xác minh giao dịch với nhà cung cấp; chỉ Payment công bố kết quả đã được xác minh.
5. Order nhận các kết quả cần thiết và chuyển trạng thái đơn theo quy tắc của Order.

Nếu giao dịch thanh toán thành công nhưng sự kiện gửi về Order bị trễ, Payment có thể đã ghi nhận thanh toán trong khi Order vẫn hiển thị “đang xử lý”. Đây là **độ trễ nhất quán giữa các nguồn có thẩm quyền**, không phải lý do để Order tự sửa bản ghi của Payment.

### 4.1. Nhất quán mạnh trong một phạm vi, đồng bộ có kiểm soát giữa các phạm vi

**Trong một giao dịch cục bộ**, nên đảm bảo dữ liệu và bất biến cần đi cùng nhau được cập nhật nguyên tử. Ví dụ, Inventory có thể ghi cả lượng hàng còn lại và phiếu giữ hàng trong cùng giao dịch.

**Giữa các module hoặc dịch vụ độc lập**, không nên giả định có một giao dịch database chung. Quy trình thường cần trạng thái trung gian, sự kiện, retry, timeout và hành động bù (compensation) khi bước tiếp theo thất bại. Nếu giữ hàng thành công nhưng thanh toán không thành công, Order có thể yêu cầu Inventory giải phóng phiếu giữ; Inventory vẫn là chủ thể thực hiện thay đổi đó.

Ba kỹ thuật thường cần phối hợp:

| Kỹ thuật | Mục đích | Điểm cần lưu ý |
| --- | --- | --- |
| **Idempotency key** | Gửi lại cùng yêu cầu mà không lặp tác động nghiệp vụ | Khóa duy nhất gắn với kết quả và nội dung yêu cầu; phải xử lý cả trường hợp hai lần gửi đến đồng thời |
| **Transactional outbox** | Ghi thay đổi nghiệp vụ và ý định phát sự kiện trong cùng giao dịch | Bộ phát có thể gửi lặp; bên nhận vẫn phải chống xử lý trùng |
| **Đối soát (reconciliation)** | Phát hiện và xử lý thông tin lệch hoặc sự kiện thất lạc | Quy tắc phân xử phải dựa trên nguồn có thẩm quyền và nhật ký kiểm toán |

Ví dụ, phiếu giữ hàng có thể dùng khóa duy nhất theo yêu cầu:

~~~sql
CREATE TABLE inventory_reservation (
    request_id VARCHAR(80) PRIMARY KEY,
    sku VARCHAR(64) NOT NULL REFERENCES inventory_stock(sku),
    quantity INTEGER NOT NULL CHECK (quantity > 0)
);
~~~

Trong **cùng giao dịch**, Inventory kiểm tra xem request ID đã được xử lý chưa, cập nhật tồn kho có điều kiện, ghi phiếu giữ và ghi thông tin cần phát vào outbox. Nếu hai giao dịch cùng dùng một request ID, ràng buộc khóa duy nhất ngăn ghi hai phiếu; giao dịch thua phải rollback các thay đổi liên quan, rồi đọc kết quả đã lưu để trả lời nhất quán. Một request ID tái sử dụng với SKU hoặc số lượng khác phải bị từ chối như lỗi xung đột. Nếu giao dịch commit thành công nhưng kết nối đứt trước khi client nhận phản hồi, client có thể tra cứu kết quả theo request ID thay vì tạo một tác động mới.

Không nên thiết kế thao tác ghi dữ liệu rồi gọi broker như hai bước độc lập mà thiếu cơ chế phục hồi: nếu database đã commit nhưng publish thất bại, các bên đọc có thể không bao giờ biết bản ghi đã đổi. Với outbox, tiến trình gửi sự kiện đọc dữ liệu đã commit, gửi lại khi cần, và chỉ đánh dấu đã gửi theo cơ chế đáng tin cậy.

### 4.2. Độ mới của dữ liệu phải được nói rõ

Một màn hình có thể đọc từ cache hoặc mô hình đọc đã được cập nhật bằng sự kiện. Khi đó, kết quả **có thể trễ**, dù nguồn chuẩn vẫn đúng. Hợp đồng đọc nên mô tả mức trễ chấp nhận được, ví dụ “danh sách đơn hàng có thể cập nhật chậm vài giây”, và xác định thao tác nào cần đọc trực tiếp nguồn có thẩm quyền.

Không được dùng bản sao chậm để ra quyết định đòi hỏi trạng thái mới nhất, chẳng hạn kiểm tra còn đủ hàng để trừ kho, trừ khi có cơ chế đồng thời bảo đảm tính đúng đắn tại nơi ghi. Phân biệt rõ:

- **Đọc để hiển thị:** có thể chấp nhận dữ liệu trễ theo mục tiêu sản phẩm.
- **Ghi để quyết định:** phải được chủ sở hữu xác nhận theo dữ liệu và ràng buộc có thẩm quyền.

## 5. Hợp đồng dữ liệu và thay đổi schema

Chỉ định “Customer sở hữu khách hàng” là chưa đủ. Một **hợp đồng dữ liệu** cần nói rõ các bên khác được hiểu và sử dụng dữ liệu đó thế nào. Ví dụ cho tồn kho:

| Thuộc tính hợp đồng | Quy định minh họa |
| --- | --- |
| Dữ liệu | Số lượng còn khả dụng theo SKU, không phải tổng lượng đã nhập |
| Chủ sở hữu | Inventory |
| Nguồn chuẩn | Bảng tồn kho và phiếu giữ trong kho giao dịch của Inventory |
| Định danh | SKU, request ID duy nhất cho lệnh giữ hàng |
| Ghi | Lệnh giữ/giải phóng hàng qua giao diện Inventory |
| Đọc | API tồn kho; sự kiện để dựng mô hình đọc |
| Bất biến | Không giữ số lượng âm; không xử lý một request ID hai lần |
| Độ mới | Quyết định giữ hàng kiểm tra nguồn ghi; màn hình có thể sử dụng dữ liệu trễ |
| Khôi phục | Đối soát phiếu giữ, tồn kho và sự kiện; có log kiểm toán |

Chủ sở hữu còn chịu trách nhiệm **tiến hóa schema** mà không làm hỏng bên đọc. Một quy trình an toàn thường là:

1. **Mở rộng:** thêm trường/bảng/API phiên bản mới theo cách tương thích với bản đang chạy.
2. **Chuyển đổi:** cập nhật mã ghi, di chuyển hoặc backfill dữ liệu, xác minh cả giá trị cũ và mới.
3. **Thu hẹp:** chỉ xóa trường hay đường đọc cũ sau khi tất cả bên sử dụng đã chuyển xong.

Hợp đồng sự kiện cũng cần quản lý phiên bản, ý nghĩa field và khả năng xử lý event cũ. Tránh để nhiều module cùng phụ thuộc vào cấu trúc bảng nội bộ của module chủ sở hữu: một lần đổi schema nếu không sẽ trở thành thay đổi bắt buộc trên toàn hệ thống.

## 6. Bảo mật, vận hành và khôi phục thuộc trách nhiệm ai?

Quyền sở hữu dữ liệu bao gồm cả trách nhiệm khi có sự cố. Mỗi nhóm dữ liệu quan trọng nên có người phụ trách các công việc sau:

- **Phân quyền:** chỉ tài khoản dịch vụ hoặc người vận hành được ủy quyền mới có quyền ghi; cấp quyền tối thiểu. Các hệ thống phân tích hoặc báo cáo ưu tiên đường đọc phù hợp.
- **Bảo vệ dữ liệu nhạy cảm:** phân loại trường dữ liệu, kiểm soát truy cập, mã hóa khi truyền và lưu trữ khi cần, che thông tin nhạy cảm trong log, xác định thời gian lưu và quy trình xóa theo yêu cầu áp dụng.
- **Giám sát chất lượng:** phát hiện giá trị không hợp lệ, thao tác ghi thất bại, số lần retry, độ trễ bản sao/sự kiện, số bản ghi cần đối soát.
- **Kiểm toán:** lưu dấu vết ai hoặc hệ thống nào thay đổi dữ liệu, nguyên nhân nghiệp vụ, request ID và thời điểm; tránh cho phép chỉnh sửa thủ công không có kiểm soát.
- **Sao lưu và phục hồi:** xác định **RPO** (mức mất dữ liệu tối đa có thể chấp nhận) và **RTO** (thời gian khôi phục tối đa), thử khôi phục định kỳ và xác minh tính toàn vẹn sau phục hồi.

Replication giúp tăng sẵn sàng và khả năng đọc nhưng **không thay thế backup**: xóa nhầm hay dữ liệu hỏng vẫn có thể lan sang bản sao. Cache và mô hình đọc thường có thể tái dựng từ nguồn chuẩn, nhưng nếu không có pipeline, sự kiện hoặc bản ghi gốc đủ đầy thì việc tái dựng có thể thất bại.

Sau lỗi kết nối, cần phân biệt **lệnh chắc chắn thất bại** với **lệnh đã commit nhưng phản hồi bị mất**. Với trường hợp chưa biết kết quả, ưu tiên truy vấn theo định danh nghiệp vụ/idempotency key rồi mới quyết định retry. Không được tùy tiện chạy lại một phép trừ tiền hoặc trừ tồn kho không idempotent.

## 7. Những cách thiết kế dễ gây sai lệch

| Dấu hiệu | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Hai module cùng ghi một trường trạng thái | “Ghi cuối thắng”, khó xác định ai đúng | Chọn một chủ sở hữu; bên còn lại gửi command hoặc đề nghị thay đổi |
| Giao diện sửa trực tiếp cache khi bản chính không đổi | Dữ liệu mất hoặc bị ghi đè khi cache làm mới | Thực hiện ghi tại nguồn chuẩn, sau đó cập nhật/vô hiệu hóa cache |
| Đọc tồn kho rồi ghi mà không khóa/kiểm tra đồng thời | Bán vượt tồn kho khi nhiều yêu cầu đến | Dùng cập nhật có điều kiện, ràng buộc database và giao dịch phù hợp |
| Ghi database và phát sự kiện không có cơ chế phục hồi | Mô hình đọc bỏ lỡ thay đổi | Dùng outbox, retry có kiểm soát và consumer idempotent |
| Nhận webhook thanh toán rồi tin ngay vào trạng thái đơn hàng | Dễ cập nhật sai hoặc xử lý lặp | Xác minh tính xác thực, định danh giao dịch, đối soát nguồn thanh toán |
| Cấp quyền ghi bảng nội bộ cho nhiều dịch vụ | Migration gây hỏng phụ thuộc, mất quyền kiểm soát | Giới hạn quyền và công bố hợp đồng truy cập ổn định |
| Xem bản sao hoặc backup là nguồn chuẩn thay thế vô điều kiện | Nguy cơ ghi vào dữ liệu trễ hoặc phục hồi sai | Có chính sách failover, đồng bộ và đối soát rõ ràng |

## 8. Tình huống thực hành: hai con số tồn kho khác nhau

Một khách hàng thấy “còn 5 sản phẩm” trên trang tìm kiếm nhưng khi đặt hàng, Inventory trả về “không đủ hàng”. Cách đánh giá đúng:

1. **Xác định ý nghĩa dữ liệu:** “còn 5” là số lượng tìm kiếm lưu từ lần đồng bộ trước; “không đủ hàng” là kết quả kiểm tra tại thời điểm giữ hàng.
2. **Xác định nguồn chuẩn:** Inventory sở hữu số lượng khả dụng; hệ thống tìm kiếm chỉ giữ mô hình đọc.
3. **Giữ quyết định đúng tại nơi ghi:** không thay kết quả giữ hàng bằng con số đang hiển thị. Nếu chưa đủ hàng, trả thông báo phù hợp cho người dùng.
4. **Tìm nguyên nhân trễ:** kiểm tra outbox, consumer, độ trễ xử lý sự kiện, cache TTL và mã SKU.
5. **Sửa bản sao:** phát lại sự kiện hợp lệ hoặc tái dựng mô hình đọc từ Inventory; không cập nhật ngược số “5” vào bảng Inventory.
6. **Ngăn tái diễn:** theo dõi thời gian trễ tối đa và hiển thị mức độ cập nhật; khi cần, trang chi tiết có thể hỏi Inventory để có giá trị mới hơn.

Nếu chính Inventory sai, cần kiểm tra phiếu giữ, phiếu hoàn, giao dịch rollback, lịch sử thay đổi và đối soát nguồn nhập/xuất hàng trước khi điều chỉnh. Mọi lệnh sửa dữ liệu phải đi qua quy trình có kiểm toán của chủ sở hữu.

## 9. Checklist khi thiết kế một nhóm dữ liệu mới

Trước khi triển khai bảng, repository hoặc service mới, kiểm tra:

- [ ] Đã mô tả chính xác sự kiện/thuộc tính và thời điểm mà dữ liệu biểu diễn.
- [ ] Có một chủ sở hữu xác nhận quy tắc và quyết định ghi cho mỗi sự kiện/thuộc tính.
- [ ] Có khóa định danh, ràng buộc dữ liệu và bất biến được bảo vệ tại nơi ghi.
- [ ] Đã xác định ranh giới transaction, mức cô lập và cách chống cập nhật cạnh tranh.
- [ ] Các bên đọc biết nguồn, hợp đồng truy cập và độ trễ dữ liệu được phép.
- [ ] Retry, idempotency, xuất sự kiện và đối soát được thiết kế cho lỗi từng phần.
- [ ] Có quy trình migration, phân quyền, kiểm toán, sao lưu và thử khôi phục.
- [ ] Có khả năng dựng lại cache/mô hình đọc mà không biến chúng thành nguồn ghi thứ hai.

**Ghi nhớ:** Thiết kế persistence tốt bắt đầu từ việc xác định *ai có quyền nói điều gì là đúng*. Database, transaction, index, cache và kiến trúc dịch vụ là các công cụ để hiện thực hóa cam kết đó. Khi phạm vi sở hữu rõ ràng, hệ thống Java dễ duy trì tính đúng đắn, xử lý lỗi và tiến hóa mà không tạo ra nhiều phiên bản “sự thật” cạnh tranh nhau.
