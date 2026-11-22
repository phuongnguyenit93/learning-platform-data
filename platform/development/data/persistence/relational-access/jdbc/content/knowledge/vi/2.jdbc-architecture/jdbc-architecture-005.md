# Phân biệt kết nối vật lý và kết nối logic

## 1. Hai khái niệm trong kiến trúc JDBC

**JDBC (Java Database Connectivity)** là API của Java để truy cập cơ sở dữ liệu quan hệ. Khi ứng dụng gọi `Connection` để chạy SQL, điều nhìn thấy trong mã Java chưa chắc là toàn bộ kết nối đang tồn tại giữa ứng dụng và hệ quản trị cơ sở dữ liệu (DBMS).

Trong kiến trúc JDBC, đặc biệt khi có **connection pool** (bộ quản lý nhóm kết nối), cần phân biệt:

- **Kết nối vật lý (*physical connection*)**: tài nguyên kết nối thực sự do JDBC driver và hệ quản trị cơ sở dữ liệu duy trì để trao đổi yêu cầu SQL. Việc tạo kết nối vật lý thường đòi hỏi thiết lập giao tiếp, xác thực và cấp phát tài nguyên phía máy chủ.
- **Kết nối logic (*logical connection*)**: đối tượng `java.sql.Connection` mà mã ứng dụng nhận và sử dụng để thực thi SQL. Khi có pool, đối tượng này thường là một **handle/wrapper** đại diện cho quyền sử dụng tạm thời một kết nối vật lý.

Hai khái niệm này khác nhau ở **vòng đời và trách nhiệm quản lý**. Ứng dụng mở/đóng handle logic cho từng công việc; pool có thể giữ kết nối vật lý tồn tại lâu hơn để tái sử dụng. Một `Connection` trong Java chỉ công khai hợp đồng JDBC, nên **không thể kết luận nó là kết nối vật lý chỉ bằng kiểu `Connection`**.

> Cách ghi nhớ: kết nối vật lý là *tài nguyên có thể tái sử dụng*; kết nối logic là *lượt sử dụng tài nguyên đó của một đoạn mã ứng dụng*.

## 2. Khi không dùng pool: vòng đời gần như trùng nhau

Với cách kết nối trực tiếp thông thường qua `DriverManager` hoặc một `DataSource` không sử dụng pool, mỗi lần mở kết nối thường khiến driver thiết lập một kết nối thực sự tới DBMS:

```text
Ứng dụng Java
     │
     │ DriverManager.getConnection(...)
     ▼
java.sql.Connection ─── JDBC driver ─── Kết nối DB thực tế ─── DBMS
     │
     │ connection.close()
     ▼
  Driver giải phóng kết nối tương ứng
```

Ví dụ mở kết nối trực tiếp:

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;

public class DirectConnectionExample {
    public static void connect(String url, String user, String password)
            throws SQLException {
        try (Connection connection =
                     DriverManager.getConnection(url, user, password)) {
            System.out.println("Đã nhận kết nối JDBC: " + !connection.isClosed());
            // Thực thi SQL bằng connection tại đây.
        } // Với kết nối trực tiếp, close() thường đóng kết nối DB tương ứng.
    }
}
```

Trong trường hợp này, **thời gian sử dụng đối tượng `Connection` và thời gian tồn tại của kết nối vật lý thường gần nhau**. Đóng `Connection` thường kéo theo giải phóng kết nối thực tế.

Tuy nhiên, `DriverManager` chỉ là cơ chế tìm driver và lấy `Connection`; bản thân API không bảo đảm mọi driver hoặc URL kết nối đều có đúng một socket mạng cho mỗi đối tượng Java. Một số hệ thống dùng proxy, transport đặc biệt hoặc cơ chế quản lý kết nối riêng. Vì vậy, nên hiểu “vật lý” theo nghĩa tài nguyên kết nối thực tế mà driver/DBMS quản lý, không đồng nhất máy móc với một socket TCP.

## 3. Khi có connection pool: vòng đời được tách riêng

**Connection pool** lưu trữ các kết nối vật lý đã được tạo, cấp quyền sử dụng chúng cho ứng dụng và nhận lại khi công việc kết thúc. Thay vì mỗi yêu cầu đều tạo rồi hủy kết nối DB, pool cố gắng dùng lại tài nguyên sẵn có.

```text
                        ỨNG DỤNG JDBC
                              │
                              │ dataSource.getConnection()
                              ▼
                      Kết nối LOGIC A
                        (Connection)
                              │ dùng trong công việc A
                              ▼
                  ┌──────────────────────┐
                  │   CONNECTION POOL    │
                  │                      │
                  │ Vật lý 1: ĐANG MƯỢN │ ────► DBMS
                  │ Vật lý 2: SẴN SÀNG   │ ────► DBMS
                  │ Vật lý 3: SẴN SÀNG   │ ────► DBMS
                  └──────────────────────┘
                              ▲
                              │ connection.close()
                              │ trả quyền sử dụng

      Công việc B sau đó có thể mượn Vật lý 1 qua kết nối LOGIC B.
```

Diễn biến của một lượt mượn kết nối:

1. Ứng dụng gọi `dataSource.getConnection()`.
2. Nếu pool có kết nối vật lý phù hợp đang rảnh, pool cấp một `Connection` logic cho ứng dụng. Nếu chưa có tài nguyên sẵn và còn khả năng mở thêm, pool có thể tạo kết nối vật lý mới.
3. Ứng dụng dùng `Connection` logic để tạo `PreparedStatement`, chạy SQL và xử lý kết quả.
4. Ứng dụng gọi `connection.close()`, thường bằng `try-with-resources`.
5. Pool nhận lại tài nguyên, thực hiện các thao tác thu dọn hoặc kiểm tra cần thiết, rồi có thể cho lượt mượn khác sử dụng.

**Điểm cốt lõi:** trong một pool hoạt động bình thường, `close()` của handle logic thường **kết thúc lượt mượn**, không đóng ngay kết nối vật lý. Kết nối vật lý có thể tiếp tục sống trong pool để phục vụ yêu cầu tiếp theo. Tuy nhiên, pool vẫn có thể thực sự đóng nó khi phát hiện lỗi, quá thời gian sống, cần giảm số kết nối nhàn rỗi hoặc khi pool dừng.

Một kết nối vật lý thường được dành cho **một lượt mượn tại một thời điểm**. Hai tác vụ không nên dùng đồng thời một handle `Connection` để chia sẻ trạng thái giao dịch; việc cấp phát độc quyền cho các lượt mượn thông thường là trách nhiệm của pool.

## 4. Bảng đối chiếu vật lý và logic

| Tiêu chí | Kết nối vật lý | Kết nối logic |
|---|---|---|
| Bản chất | Tài nguyên giao tiếp thực tế với cơ sở dữ liệu | Đối tượng/handle `Connection` được ứng dụng sử dụng |
| Thành phần quản lý | Driver, pool và DBMS | Mã ứng dụng trong phạm vi một công việc; pool có thể cung cấp wrapper |
| Chi phí tạo | Có thể tốn thời gian cho kết nối, xác thực, tài nguyên DB | Nếu mượn từ pool đang có tài nguyên rảnh, thường nhanh hơn mở kết nối vật lý mới |
| Thời gian tồn tại | Có thể kéo dài qua nhiều lượt mượn | Thường ngắn, giới hạn trong một thao tác/yêu cầu/giao dịch |
| Khi ứng dụng gọi `close()` | Có thể vẫn tồn tại khi dùng pool; thường bị đóng nếu không pool | Handle kết thúc hiệu lực sử dụng; không được tiếp tục truy vấn qua handle đó |
| Tái sử dụng | Pool có thể dùng lại cho lượt mượn mới | Một handle đã `close()` không được tái sử dụng |
| Quan sát từ mã Java | Không nhất thiết có đối tượng công khai biểu diễn trực tiếp | Thường được nhận qua `DataSource.getConnection()` hoặc `DriverManager.getConnection()` |

Ví dụ: một dịch vụ web xử lý tuần tự 100 yêu cầu đọc dữ liệu. Nếu các yêu cầu đều lấy và trả kết nối đúng cách, pool **có thể** phục vụ nhiều yêu cầu bằng số kết nối vật lý ít hơn rất nhiều so với 100. Không có nghĩa là pool luôn chỉ mở một kết nối: số kết nối cần thiết phụ thuộc **mức đồng thời**, cấu hình và trạng thái kết nối.

## 5. `DataSource`, `ConnectionPoolDataSource` và `PooledConnection`

Trong JDBC, ba giao diện/lớp sau liên quan trực tiếp đến kiến trúc này:

| API | Vai trò |
|---|---|
| `javax.sql.DataSource` | Điểm truy cập thông dụng để **mã ứng dụng** lấy `Connection` thông qua `getConnection()` |
| `javax.sql.ConnectionPoolDataSource` | API phía hạ tầng quản lý pool để tạo đối tượng `PooledConnection` |
| `javax.sql.PooledConnection` | Đại diện cho kết nối vật lý dùng trong cơ chế pooling chuẩn JDBC; có thể cấp một `Connection` logic qua `getConnection()` và thông báo sự kiện liên quan đến lượt sử dụng |

Trong mô hình JDBC pooling chuẩn, pool manager có thể nhận `PooledConnection` từ `ConnectionPoolDataSource`, giữ nó và cấp các handle `Connection` logic cho ứng dụng thông qua một `DataSource` có tích hợp pool. Pool lắng nghe sự kiện như đóng handle hoặc lỗi kết nối để quản lý tài nguyên.

```text
Ứng dụng
   │
   └── DataSource.getConnection() ─────► Connection logic
              ▲                                │
              │                                │ dùng SQL
         Pool manager                         ▼
              │                         Kết nối vật lý ───► DBMS
              │
              └── ConnectionPoolDataSource / PooledConnection
                         (cơ chế hạ tầng có thể sử dụng)
```

Ứng dụng nghiệp vụ **thường chỉ cần `DataSource` và `Connection`**, không nên tự điều phối `PooledConnection` hoặc gọi `PooledConnection.close()` để trả tài nguyên của pool. Việc quản lý chúng thuộc về thư viện pool/container.

Đặc biệt, **`DataSource` không tự động đồng nghĩa với pooling**. Cùng một giao diện `DataSource` có thể được triển khai theo kiểu không pool hoặc có pool. Muốn biết `close()` sẽ trả tài nguyên vào pool hay đóng vật lý, phải kiểm tra **cấu hình và loại `DataSource` thực tế**.

## 6. Ví dụ sử dụng kết nối logic đúng cách

Giả sử ứng dụng đã cấu hình và truyền một `DataSource` vào lớp truy cập dữ liệu. Đoạn mã sau hoạt động với cả `DataSource` có pool lẫn không pool:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

public class CustomerReader {
    private final DataSource dataSource;

    public CustomerReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public List<String> findCustomerNames() throws SQLException {
        String sql = "SELECT full_name FROM customers ORDER BY id";
        List<String> names = new ArrayList<>();

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql);
             ResultSet resultSet = statement.executeQuery()) {

            while (resultSet.next()) {
                names.add(resultSet.getString("full_name"));
            }
        }

        return names;
    }
}
```

Giả định bảng `customers` có hai cột `id`, `full_name` và `DataSource` đã được cấu hình kết nối hợp lệ. Ý nghĩa đoạn mã:

- `dataSource.getConnection()` là thời điểm ứng dụng **nhận quyền sử dụng** một `Connection`. Với pool, đây thường là thao tác *borrow* (mượn).
- Các phương thức `prepareStatement`, `executeQuery` và `next` hoạt động qua chính handle logic đã mượn; ứng dụng không phải biết driver thực thi qua kết nối vật lý nào.
- Khi ra khỏi khối `try-with-resources`, Java đóng các tài nguyên theo thứ tự ngược: `ResultSet` → `PreparedStatement` → `Connection`.
- Nếu `DataSource` được quản lý bởi pool, lời gọi `Connection.close()` **thường trả quyền sử dụng cho pool**. Nếu `DataSource` không có pool, hành vi thường là đóng kết nối thực sự.

Không giữ `Connection` trong biến dùng chung lâu dài hoặc trả nó ra ngoài khi khối `try-with-resources` đã kết thúc. Một `Connection` đã đóng không còn là handle hợp lệ để thực thi câu lệnh, kể cả khi pool vẫn giữ kết nối vật lý phía dưới.

## 7. Điều gì xảy ra khi `close()` được gọi?

Tên phương thức giống nhau nhưng **hiệu ứng đối với tài nguyên vật lý có thể khác nhau**:

```text
KHÔNG POOL                          CÓ POOL

getConnection()                      getConnection()
   │                                    │
   ▼                                    ▼
Connection + DB connection          Connection logic → DB connection
   │                                    │
   │ close()                            │ close()
   ▼                                    ▼
Đóng/giải phóng kết nối DB          Trả handle về pool
                                        │
                                        ▼
                                   DB connection có thể
                                   tiếp tục tồn tại nhàn rỗi
```

Với kết nối có pool, pool còn phải giữ an toàn cho người mượn tiếp theo. Ví dụ, nếu công việc trước thay đổi `autoCommit`, mức cô lập giao dịch, chế độ chỉ đọc, schema hoặc giữ một giao dịch chưa kết thúc, lượt sử dụng sau có thể bị ảnh hưởng nếu trạng thái không được thu dọn đúng cách.

Một pool tốt thường triển khai cơ chế **reset trạng thái kết nối**, đóng tài nguyên còn sót lại, rollback giao dịch chưa hoàn tất khi cần và loại bỏ kết nối hỏng. Tuy nhiên, **những thuộc tính được reset và cách reset phụ thuộc thư viện pool, driver và cấu hình**; không nên giả định mọi trạng thái phiên SQL do ứng dụng tạo (chẳng hạn bảng tạm hoặc biến session đặc thù DB) đều sẽ tự động trở về mặc định.

Vì thế, trách nhiệm của mã ứng dụng vẫn là:

1. **Kết thúc rõ ràng giao dịch** bằng `commit()` hoặc `rollback()` trước khi trả kết nối.
2. **Đóng `ResultSet`, `Statement` và `Connection` đúng phạm vi**, ưu tiên `try-with-resources`.
3. **Không tái sử dụng handle logic đã đóng**, không chuyển handle đó giữa các tác vụ đang chạy đồng thời.
4. **Không dựa vào session state còn sót từ lần mượn trước**, ngay cả khi những lần mượn có thể cùng dùng một kết nối vật lý.

Ví dụ khung quản lý giao dịch trên một handle được mượn từ `DataSource`:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        // Thực thi các câu lệnh của cùng một giao dịch tại đây.
        // Mỗi Statement/ResultSet vẫn cần được đóng đúng cách.
        connection.commit();
    } catch (SQLException | RuntimeException error) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            error.addSuppressed(rollbackError);
        }
        throw error;
    }
} // Handle được đóng/trả về pool sau khi giao dịch kết thúc.
```

Đoạn mã giả định nằm trong phương thức có khai báo `throws SQLException`. Khi dùng framework quản lý giao dịch, hãy tuân theo cơ chế transaction của framework thay vì tự can thiệp trái với phạm vi giao dịch đã được framework điều phối.

## 8. Pool có bao nhiêu kết nối vật lý, bao nhiêu lượt mượn logic?

Giả sử một pool được cấu hình **tối đa 3 kết nối vật lý**. Có ba yêu cầu độc lập đang thực thi SQL cùng lúc:

| Thời điểm | Kết nối vật lý đang mượn | Kết nối vật lý còn rảnh | Diễn giải |
|---|---:|---:|---|
| A mượn | 1 | Tùy pool | A nhận một handle logic |
| B và C cùng mượn | 3 | 0 | Ba handle có thể sử dụng ba kết nối vật lý |
| D cũng yêu cầu kết nối | 3 | 0 | D thường phải đợi tài nguyên trả về hoặc chạm timeout của pool |
| A đóng handle | 2 | 1 | Pool có thể cấp lại tài nguyên cho D |
| B, C và D lần lượt hoàn tất | 0 | Tùy cấu hình | Pool có thể giữ các kết nối nhàn rỗi hoặc đóng bớt |

Đây chỉ là **kịch bản minh họa** của một pool giới hạn ba kết nối. Thời điểm mở kết nối ban đầu, số kết nối tối thiểu, timeout, validation và chính sách đóng kết nối nhàn rỗi do thư viện pool quyết định.

Các hệ quả thực tế:

- Pool giúp **giảm số lần thiết lập kết nối vật lý**, nên thường cải thiện độ trễ và hiệu quả sử dụng DB đối với ứng dụng có nhiều yêu cầu.
- Pool **không loại bỏ giới hạn kết nối của DBMS**. Tăng kích thước pool quá mức có thể tăng áp lực lên máy chủ.
- Nếu mã ứng dụng quên `close()` một handle, pool có thể dần **hết kết nối sẵn sàng** (*connection leak*), dù một số handle không còn làm việc hữu ích.
- Với nhiều instance ứng dụng, tổng kết nối vật lý ở phía DB có thể xấp xỉ tổng các pool đang hoạt động, chứ không chỉ là kích thước pool của một instance.

Đặc biệt, **không thể nhìn số đối tượng `Connection` logic được tạo trong một khoảng thời gian rồi suy trực tiếp ra số kết nối vật lý**. Mười nghìn lượt mượn tuần tự vẫn có thể dùng đi dùng lại một số ít kết nối vật lý; ngược lại nhiều yêu cầu đồng thời có thể buộc pool mở thêm kết nối trong giới hạn cấu hình.

## 9. Khi kết nối vật lý gặp sự cố

Việc có pool không đảm bảo kết nối vật lý luôn còn sử dụng được. Máy chủ DB có thể restart; mạng có thể bị ngắt; proxy hoặc DBMS có thể chủ động đóng kết nối nhàn rỗi. Pool có thể kiểm tra tính hợp lệ khi mượn hoặc khi kết nối nhàn rỗi, loại bỏ kết nối lỗi và tạo kết nối mới theo chính sách cấu hình.

JDBC cung cấp `Connection.isValid(int timeout)` để yêu cầu driver kiểm tra một kết nối có còn hợp lệ hay không. Tuy nhiên, kết quả kiểm tra tại một thời điểm **không bảo đảm kết nối sẽ còn hoạt động ở câu SQL kế tiếp**. Ứng dụng vẫn phải xử lý `SQLException` khi thao tác thất bại.

Khi xảy ra lỗi kết nối:

- **Handle logic đang dùng** có thể không thực hiện được câu SQL tiếp theo và cần kết thúc theo quy trình xử lý lỗi.
- **Kết nối vật lý tương ứng** có thể bị pool đánh dấu hỏng và loại bỏ thay vì tái sử dụng.
- **Lượt mượn mới** có thể nhận một kết nối vật lý khác hoặc chờ pool tạo lại tài nguyên.
- **Trạng thái thực hiện của thao tác ghi hoặc transaction** có thể chưa chắc chắn nếu lỗi xảy ra trong lúc giao tiếp; không tự động chạy lại lệnh ghi chỉ vì đã có một `Connection` mới.

Đó là lý do việc ghi log thời gian mượn/trả handle, số kết nối đang dùng/nhàn rỗi, số yêu cầu phải chờ và số lỗi kết nối thường hữu ích hơn việc so sánh địa chỉ hay `hashCode()` của các đối tượng `Connection`. **Hai handle khác nhau có thể lần lượt dùng cùng kết nối vật lý; hai handle trông giống nhau cũng không chứng minh đang dùng cùng phiên DB.**

## 10. Những hiểu lầm thường gặp

| Nhận định sai | Giải thích đúng |
|---|---|
| “Gọi `getConnection()` là tạo kết nối TCP mới.” | Với pool, thường chỉ là mượn một handle logic trên kết nối vật lý có sẵn. |
| “`Connection.close()` luôn đóng socket tới DB.” | Với pool, thông thường là trả handle; việc đóng kết nối vật lý do pool quản lý. |
| “Dùng `DataSource` là chắc chắn có connection pool.” | `DataSource` chỉ là giao diện; phải kiểm tra triển khai và cấu hình cụ thể. |
| “Handle đã `close()` vẫn dùng được vì kết nối vật lý còn mở.” | Handle logic đã kết thúc lượt sử dụng và không được thực thi SQL tiếp. |
| “Một `Connection` có thể lưu làm biến toàn cục để mọi thread cùng dùng.” | Handle chứa trạng thái giao dịch/session và nên được quản lý theo phạm vi công việc; không chia sẻ đồng thời một handle. |
| “Pool tự sửa mọi trạng thái SQL nên không cần `rollback()`.” | Ứng dụng phải kết thúc giao dịch đúng cách; mức reset phụ thuộc pool và driver. |
| “`hashCode()` giống nhau nghĩa là dùng cùng kết nối vật lý.” | Hash hoặc định danh wrapper Java không phải bằng chứng về phiên DB vật lý. |
| “Pool có 20 kết nối thì DB luôn có đúng 20 session.” | Số vật lý thực tế thay đổi tùy chính sách tạo, giữ nhàn rỗi và loại bỏ kết nối. |

## 11. Tự kiểm tra bằng một tình huống

Giả sử ứng dụng dùng `DataSource` có pool và thực hiện:

```java
Connection first = dataSource.getConnection();
first.close();

Connection second = dataSource.getConnection();
try {
    // Chạy SQL với second.
} finally {
    second.close();
}
```

Các kết luận đúng là:

1. `first` và `second` đại diện cho **hai lượt mượn logic** khác nhau.
2. Sau `first.close()`, không được dùng `first` để tiếp tục thực thi SQL.
3. Pool **có thể** cấp cho `second` cùng kết nối vật lý mà `first` từng dùng, nhưng không có bảo đảm đó là kết nối vật lý cũ.
4. Khi `second.close()` hoàn tất, kết nối vật lý phía dưới có thể vẫn tồn tại để phục vụ lượt mượn tiếp theo.
5. Chỉ bằng `first == second` hoặc `hashCode()` không thể kết luận kết nối vật lý có được tái sử dụng hay không.

Trong mã ứng dụng thực tế, nên dùng `try-with-resources` cho **cả hai** lượt mượn để việc trả kết nối diễn ra ngay cả khi có ngoại lệ.

**Ghi nhớ:** `Connection` là giao diện thao tác JDBC mà ứng dụng nhìn thấy. Trong cơ chế connection pooling, **kết nối logic** là handle có vòng đời theo công việc, còn **kết nối vật lý** là tài nguyên kết nối thật do pool/driver quản lý và có thể phục vụ nhiều lượt mượn nối tiếp nhau. Hiểu rõ sự khác biệt giúp đóng tài nguyên đúng cách, quản lý transaction an toàn và cấu hình pool phù hợp với tải ứng dụng.
