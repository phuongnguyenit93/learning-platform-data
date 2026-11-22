# Kích thước pool và quan hệ với năng lực xử lý phía máy chủ

Trong chương **Kết nối và tài nguyên** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**, một quyết định vận hành tưởng như đơn giản là đặt **kích thước connection pool** có thể ảnh hưởng trực tiếp đến độ trễ, thông lượng, sự ổn định và khả năng phục hồi của ứng dụng Java. Pool quá nhỏ khiến yêu cầu xếp hàng dù cơ sở dữ liệu còn khả năng xử lý. Pool quá lớn có thể dồn nhiều công việc xuống máy chủ database hơn khả năng phục vụ, tăng tranh chấp tài nguyên và làm cả hệ thống chậm đi.

Kích thước pool phải được chọn dựa trên **mức sử dụng kết nối thực tế của ứng dụng**, **năng lực xử lý và giới hạn kết nối của database**, **số lượng phiên bản ứng dụng đang chạy** và **mức độ trễ chấp nhận được**. Không có một con số đúng cho mọi hệ thống, và số HTTP request đồng thời cũng không phải số kết nối database cần thiết.

## 1. Connection pool là gì và nó giới hạn điều gì?

Mỗi kết nối JDBC tới database thường liên quan một phiên làm việc ở phía server, trạng thái giao thức, xác thực, bộ nhớ và các tài nguyên để thực hiện truy vấn. Việc tạo kết nối mới cũng tốn chi phí thiết lập mạng, TLS nếu sử dụng, đăng nhập và khởi tạo session.

**Connection pool** giữ một số kết nối đã tạo để ứng dụng mượn và trả lại. Ví dụ với HikariCP:

```text
                   Ứng dụng Java
        ┌───────────────────────────────┐
Request │  Mượn kết nối                │
   ────►│  ┌─────────────────────────┐  │
        │  │ HikariCP connection pool│  │
        │  │  Active: đang được mượn  │  │
        │  │  Idle: có thể mượn ngay  │  │
        │  │  Pending: đang chờ mượn  │  │
        │  └──────────┬──────────────┘  │
        │             │                 │
        └─────────────┼─────────────────┘
                      ▼
             Database server
        ┌───────────────────────────────┐
        │ CPU, RAM, I/O, lock, WAL,     │
        │ phiên kết nối và worker       │
        └───────────────────────────────┘
```

Khi gọi `DataSource.getConnection()`, ứng dụng mượn một kết nối. Khi gọi `close()` trên kết nối do pool cung cấp, phần lớn pool sẽ **trả kết nối về pool** để tái sử dụng, thay vì đóng phiên vật lý ngay lập tức. Pool có thể thay thế kết nối hỏng hoặc quá tuổi theo cấu hình.

Các khái niệm cần phân biệt:

| Khái niệm | Ý nghĩa | Không đồng nghĩa với |
| --- | --- | --- |
| **Maximum pool size** | Giới hạn số kết nối vật lý do **một pool** quản lý tại một thời điểm theo hợp đồng pool. | Giới hạn tổng kết nối của cả hệ thống nhiều instance. |
| **Active connections** | Số kết nối hiện đang được ứng dụng mượn. | Số truy vấn đang tiêu thụ CPU tại database. |
| **Idle connections** | Số kết nối còn mở và đang rảnh trong pool. | Tài nguyên hoàn toàn miễn phí ở server. |
| **Pending threads/requests** | Số tác vụ đang chờ để mượn kết nối. | Tất cả yêu cầu đang chờ trong hệ thống. |
| **Acquisition wait time** | Thời gian từ lúc xin mượn đến lúc nhận kết nối hoặc timeout. | Thời gian database thực thi câu SQL. |
| **Connection hold time** | Khoảng thời gian ứng dụng giữ kết nối sau khi mượn. | Chỉ thời gian CPU database xử lý truy vấn. |

Một kết nối **active trong pool** có thể đang thực thi SQL, chờ lock, chờ I/O, hoặc chỉ đang nằm trong một transaction mà Java chưa trả. Vì vậy, tăng số kết nối không chắc làm server xử lý được nhiều thao tác hữu ích hơn.

## 2. Vòng đời một request và nơi phát sinh hàng đợi

Giả sử request tạo đơn hàng cần truy cập database trong một đoạn ngắn:

```text
HTTP request
    │
    ├─ Xác thực và kiểm tra dữ liệu (chưa cần connection)
    │
    ├─ Mượn connection ─────────► Có thể chờ tại pool
    │
    ├─ BEGIN / SELECT / UPDATE / INSERT
    │                           Có thể chờ CPU, I/O, lock tại database
    ├─ COMMIT hoặc ROLLBACK
    │
    ├─ Trả connection
    │
    └─ Xây response và trả HTTP
```

Nếu pool đã cho mượn hết kết nối, request kế tiếp phải **chờ kết nối trống**, hoặc thất bại khi hết thời gian đợi. Nếu pool còn kết nối nhưng máy chủ database đã bão hòa, request vẫn có thể chậm **bên trong truy vấn**, do chờ CPU, ổ đĩa, khóa hay các hàng đợi khác.

Hai loại nghẽn này có cách xử lý khác nhau:

- **Nghẽn tại pool:** có kết nối ít hơn nhu cầu giữ kết nối trong thời điểm đó. Cần đo mức chờ mượn, thời gian giữ kết nối và liệu database còn năng lực phục vụ hay không.
- **Nghẽn phía database:** thêm kết nối có thể khiến nhiều truy vấn tranh chấp cùng CPU, I/O, bộ nhớ hoặc khóa; tăng pool thường chỉ đẩy thêm việc vào hàng đợi sâu hơn.

Độ trễ request có thể tách gần đúng:

```text
T_request =
    T_xử_lý_trước_DB
  + T_chờ_mượn_connection
  + T_giữ_connection
  + T_xử_lý_sau_DB

T_giữ_connection =
    T_SQL + T_chờ_lock/I/O/network + T_thời_gian_ứng_dụng_giữ_connection
```

Phần thời gian giữ kết nối ngoài thực thi SQL rất quan trọng: nếu Java mượn kết nối rồi gọi API bên ngoài mất 300 ms, kết nối vẫn chiếm một chỗ trong pool suốt 300 ms dù server database có thể đang rảnh.

## 3. Vì sao pool lớn hơn không luôn xử lý nhanh hơn?

Hãy tưởng tượng một database có 8 lõi CPU và workload chủ yếu là các câu truy vấn tính toán nặng. Nếu ứng dụng gửi đồng thời 200 truy vấn dạng này, server **không có 200 lõi CPU** để thực thi tất cả cùng lúc. Các truy vấn phải chia sẻ CPU, bộ đệm, bộ nhớ và bộ lập lịch.

Khi tăng mức đồng thời:

1. Lúc tải còn thấp, có thêm truy vấn song song giúp tận dụng CPU và thiết bị tốt hơn.
2. Gần ngưỡng bão hòa, thông lượng có thể tăng chậm rồi đạt **điểm gối** (*knee*) của đường cong.
3. Sau ngưỡng đó, thêm truy vấn có thể làm tăng chuyển ngữ cảnh, tranh chấp khóa, áp lực bộ nhớ, I/O và độ trễ p95/p99; thông lượng có thể gần như không tăng, thậm chí giảm.

```text
Thông lượng
    ^
    |                     _________
    |                  __/
    |               __/
    |            __/
    |         __/
    |      __/
    |_____/
    +------------------------------------> Số truy vấn đồng thời
                 ↑
            Vùng cần đo
            điểm bão hòa

Độ trễ thường tăng mạnh nếu tiếp tục dồn việc sau điểm bão hòa.
```

Đây là **mô hình khái niệm**, không phải một đường cong đo được cho mọi database. Một workload chủ yếu chờ I/O có thể hưởng lợi từ số kết nối lớn hơn số lõi CPU, trong khi workload phụ thuộc khóa trên một hàng nóng có thể chậm dù chỉ vài giao dịch đồng thời.

Với PostgreSQL, mỗi kết nối client thông thường liên quan một backend process, tạo thêm chi phí về bộ nhớ và quản lý phiên. Một số vùng bộ nhớ phục vụ thao tác sort/hash có thể được cấp **theo phép toán của truy vấn** và số worker, chứ không đơn giản cố định theo kết nối; vì thế áp lực RAM có thể tăng mạnh với nhiều truy vấn phức tạp cùng chạy. DBMS khác có mô hình thread/session khác nhưng đều có giới hạn tài nguyên.

**Quy tắc quan trọng:** pool size giới hạn mức đồng thời có thể đi từ một ứng dụng tới database. Nó là một **van điều tiết tải** ở phía client, không phải công tắc tăng năng lực của database.

## 4. Ước lượng nhu cầu kết nối bằng Little's Law

Một điểm bắt đầu hữu ích là **Little's Law**:

\[
L = \lambda \times W
\]

Trong đó:

- **\(L\):** số công việc trung bình đồng thời trong **hệ thống đang xét**.
- **\(\lambda\):** tốc độ hoàn tất công việc trung bình, ví dụ số lượt mượn kết nối mỗi giây.
- **\(W\):** thời gian trung bình một công việc ở trong hệ thống đó.

Muốn ước lượng **số kết nối đang được mượn**, hãy chọn hệ thống đang xét là **khoảng từ lúc lấy được connection tới lúc trả về pool**. Khi đó:

\[
\text{Active connections trung bình}
\approx
\text{Connection borrows/giây}
\times
\text{Thời gian giữ connection trung bình (giây)}
\]

Đây là quan hệ trung bình trong một khoảng vận hành đủ ổn định, **không phải công thức trực tiếp cho pool tối ưu**, cũng không dùng latency HTTP toàn request thay cho thời gian giữ connection.

### Ví dụ định lượng

Một API nhận **240 request/giây**. Trong đó 20% request không truy cập database, còn 80% cần mượn connection **một lần**. Kết quả đo cho thấy mỗi lượt mượn giữ kết nối trung bình **40 ms**.

```text
Số lượt mượn connection mỗi giây
    = 240 × 0,80
    = 192 lượt/giây

Thời gian giữ trung bình
    = 40 ms
    = 0,040 giây

Active connections trung bình
    ≈ 192 × 0,040
    = 7,68
```

Như vậy workload này cần khoảng **8 kết nối được mượn đồng thời, tính theo trung bình toàn bộ nhóm instance phục vụ 240 request/giây**. Nhu cầu tại giờ cao điểm, burst, phân bổ tải không đều và p95 thời gian giữ kết nối có thể cao hơn. Không thể suy ra rằng pool size = 8 là tối ưu hoặc chắc chắn đủ.

Nếu **240 request/giây là tải của một instance**, con số 7,68 mô tả instance đó. Nếu 240 request/giây là tải **của cả 6 instance**, số kết nối trung bình cần được phân bổ theo lưu lượng từng instance; không nhân 7,68 với 6 một lần nữa.

Giả sử lập trình viên vô tình giữ connection thêm 200 ms trong khi gọi một HTTP service:

```text
Thời gian giữ tăng từ 40 ms lên 240 ms.
Active connections trung bình ≈ 192 × 0,240 = 46,08.
```

Nhu cầu kết nối tăng gần **6 lần** dù số câu SQL, tốc độ request và năng lực database không đổi. Đây là lý do **rút ngắn thời gian giữ connection** thường hiệu quả hơn tăng pool.

### Cách dùng kết quả ước lượng

Đầu tiên đo \(\lambda\) và \(W\) của **chính workload đang chạy**, sau đó thử một vài mức pool size có khoảng dự phòng cho độ biến động. Ví dụ có thể thăm dò 8, 12, 16 trên **một instance** nếu workload và ngân sách kết nối cho phép. Giá trị cuối phải được quyết định bằng thử tải, biểu đồ thời gian chờ mượn, throughput, độ trễ và mức bão hòa ở database.

**Không lấy p95 của W nhân với đỉnh \(\lambda\) rồi coi là công thức xác suất chính xác cho concurrency p95.** Phân phối burst, tương quan giữa tải và latency, nhiều lượt mượn trên một request, các hàng đợi khác và cách cân bằng tải đều ảnh hưởng kết quả. Công thức Little chỉ là điểm khởi đầu để hiểu số lượng trung bình.

## 5. Ngân sách tổng số kết nối phía database

Một ứng dụng production thường có **nhiều instance**, không chỉ một JVM. Mỗi instance tạo pool của riêng nó. Nếu có 8 pod, mỗi pod cấu hình `maximumPoolSize = 20`, thì chỉ riêng dịch vụ đó đã có thể đòi tới:

\[
8 \times 20 = 160 \text{ kết nối}
\]

Ngay cả khi mỗi pod chỉ sử dụng vài kết nối phần lớn thời gian, khi cùng tải cao chúng có thể mở số kết nối tới ngưỡng cấu hình. Các dịch vụ khác, migration, giám sát và quản trị cũng cần kết nối.

Một phép tính ngân sách đơn giản:

\[
C_{\text{app,max}} \le
\left\lfloor
\frac{
C_{\text{db,available}}
- C_{\text{reserved}}
- C_{\text{other services}}
}{
N_{\text{app,max}}
}
\right\rfloor
\]

Trong đó:

- \(C_{\text{db,available}}\) là giới hạn kết nối được phép sử dụng cho nhóm workload theo cấu hình/role và chính sách DB.
- \(C_{\text{reserved}}\) là phần để lại cho quản trị, kiểm tra sức khỏe, failover hoặc khẩn cấp.
- \(C_{\text{other services}}\) là ngân sách cho các tác nhân khác dùng chung server.
- \(N_{\text{app,max}}\) là **số instance tối đa có thể tồn tại đồng thời**, kể cả scale-out và thời điểm rolling deployment.

### Ví dụ phân bổ

Giả sử một PostgreSQL server có giới hạn kết nối tổng cộng 100, và tổ chức dự trù:

| Khoản | Số kết nối |
| --- | ---: |
| Tổng giới hạn trên server | 100 |
| Dự phòng cho tác vụ quản trị, giám sát và tình huống khẩn cấp | 12 |
| Ngân sách của các ứng dụng khác | 16 |
| **Còn cho dịch vụ đặt hàng** | **72** |
| Số instance có thể chạy đồng thời trong deployment/scale-out | 8 |
| **Giới hạn tối đa theo ngân sách cho mỗi instance** | **9** |

```text
(100 - 12 - 16) / 8 = 9 kết nối/instance
```

Nếu cấu hình `maximumPoolSize = 9`, toàn bộ 8 instance có thể cùng mở tối đa 72 kết nối, vừa khớp ngân sách của dịch vụ. Có thể chọn **ít hơn 9** nếu tải đo được thấp và cần thêm khoảng dự phòng cho biến động hoặc công cụ vận hành.

**Đây chỉ là giới hạn theo số phiên kết nối**, không chứng minh 72 truy vấn đồng thời sẽ chạy hiệu quả. Database có thể bão hòa ở mức thấp hơn nhiều vì CPU, I/O, khóa hoặc WAL. Ngược lại, nếu số kết nối còn dư nhưng nhu cầu request tăng, cần đánh giá năng lực máy chủ và kiến trúc trước khi tăng pool vượt ngân sách.

Trong PostgreSQL, có thể tham khảo:

```sql
SHOW max_connections;

SELECT
    application_name,
    state,
    COUNT(*) AS connections
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY application_name, state
ORDER BY connections DESC;
```

Các kết quả truy vấn là **ảnh chụp tại một thời điểm**; dùng monitoring theo thời gian để thấy đỉnh. Giới hạn kết nối thực tế còn chịu quy tắc dành riêng một số slot cho vai trò đặc biệt, quota tài khoản và cấu hình hạ tầng. Không nên dùng toàn bộ con số `max_connections` làm ngân sách tự do.

### Auto-scaling và rolling deployment

Nếu bình thường có 6 pod nhưng trong rolling update hai pod cũ còn chạy khi hai pod mới đã bắt đầu, database có thể thấy 8 pool cùng lúc. Ngân sách phải tính **8**, không phải 6. Nếu autoscaler có thể lên 12 pod, phải tính 12 hoặc thiết kế một tầng điều tiết khác.

Đối với kiến trúc có pool đọc và pool ghi riêng, hãy tính **ngân sách từng database endpoint**: primary, read replica, analytics database và các dịch vụ dùng chung. Không cộng một cách tùy tiện ngân sách của những server khác nhau, và cũng không mặc định replica dùng chung giới hạn connection với primary.

## 6. Pool size so với năng lực thực thi truy vấn ở phía máy chủ

Năng lực xử lý của database không chỉ đo bằng số phiên kết nối. Cần tìm tài nguyên đang giới hạn workload:

| Loại workload hoặc nút nghẽn | Dấu hiệu | Tác động của tăng pool |
| --- | --- | --- |
| **CPU-bound** | CPU server cao, truy vấn tính toán nhiều, run queue tăng. | Thường tăng tranh chấp CPU sau điểm bão hòa. |
| **I/O-bound** | Thời gian chờ đọc/ghi cao, throughput đĩa chạm giới hạn. | Có thể giúp tận dụng song song đến một ngưỡng rồi gây thêm hàng đợi I/O. |
| **Lock contention** | Nhiều transaction chờ cùng hàng/bảng, deadlock hoặc lock wait cao. | Có thể làm thời gian chờ và xác suất deadlock tăng. |
| **Memory pressure** | Sử dụng RAM tăng, swap hoặc spilling tệp tạm. | Nhiều truy vấn đồng thời có thể tăng áp lực bộ nhớ. |
| **WAL/commit latency** | Log flush chậm, commit p95 tăng. | Nhiều giao dịch song song không chắc giúp nếu thiết bị ghi là nút nghẽn. |
| **Application giữ connection quá lâu** | Pool active cao nhưng DB có ít query đang thực thi. | Tăng pool che dấu lỗi giữ connection và làm giảm hiệu quả điều tiết. |
| **Pool quá nhỏ trong khi DB rảnh** | Pending/acquire latency cao, DB CPU/I/O thấp và throughput tăng khi thử pool lớn hơn. | Có thể giúp, miễn còn ngân sách và thử tải chứng minh được. |

Ví dụ một bảng có một hàng `counter` bị cập nhật bởi mọi transaction. Dù pool có 5 hay 100 kết nối, các giao dịch vẫn phải điều phối cập nhật **cùng một hàng**. Vấn đề thực sự có thể là thiết kế dữ liệu hoặc độ dài transaction, chứ không phải số connection.

Ngược lại, với nhiều truy vấn độc lập chờ I/O trên dữ liệu phân tán, một số lượng lớn hơn số lõi CPU có thể hữu ích. Vì vậy công thức kiểu **“pool size = số CPU × 2”** không phải quy tắc phổ quát. Những gợi ý đơn giản theo số lõi chỉ là giả thuyết để thử nghiệm và không thay thế benchmark theo workload.

## 7. Thiết lập connection pool trong ứng dụng Java

**HikariCP** là một lựa chọn thường gặp trong hệ sinh thái Java/Spring. Ví dụ cấu hình Spring Boot dưới đây minh họa pool của **một instance**. Các con số chỉ là điểm thử ban đầu, giả định ngân sách của ví dụ ở phần 5 đã được phân bổ.

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/orders
    username: ${DB_USER}
    password: ${DB_PASSWORD}
    hikari:
      pool-name: orders-pool
      maximum-pool-size: 9
      minimum-idle: 3
      connection-timeout: 2000
      validation-timeout: 1000
```

Ý nghĩa:

- **`maximum-pool-size: 9`:** một pool này không chủ động vượt ngưỡng 9 kết nối theo hợp đồng của HikariCP, bao gồm cả kết nối đang mượn và nhàn rỗi.
- **`minimum-idle: 3`:** HikariCP cố gắng duy trì số kết nối rảnh tối thiểu này khi có thể; pool vẫn có thể mở thêm đến 9 nếu nhu cầu tăng. Một số hệ thống chọn bỏ cấu hình `minimumIdle` để pool có cách hoạt động gần như cố định; cần cân đối thời gian khởi tạo/nhu cầu burst và ngân sách kết nối.
- **`connection-timeout: 2000`:** thời gian chờ tối đa khoảng **2 giây** để mượn được một connection trước khi báo lỗi, khác với timeout của một câu SQL đang chạy.
- **`validation-timeout: 1000`:** giới hạn thời gian cho kiểm tra tình trạng kết nối theo cách HikariCP áp dụng; không bảo vệ mọi query khỏi chạy lâu.

Những giá trị này **không phải khuyến nghị mặc định cho mọi môi trường**. Độ trễ mạng, tải peak, SLO của API và giới hạn server có thể đòi lựa chọn khác. Không nên tăng `connection-timeout` rất cao chỉ để che đi tình trạng quá tải, vì request sẽ chờ lâu và tiêu thụ thêm tài nguyên ở tầng ứng dụng.

### Thời gian sống và các timeout khác

Một kết nối có thể bị proxy, firewall hoặc server đóng khi quá tuổi hoặc nhàn rỗi. HikariCP có các cơ chế như `maxLifetime` và `keepaliveTime` để quản lý tuổi đời và sức khỏe kết nối theo khả năng của pool. Nếu có giới hạn kết nối từ hạ tầng, đặt thời gian sống phía pool **thấp hơn giới hạn hạ tầng một khoảng thích hợp** để giảm trường hợp mượn đúng lúc kết nối bị ngắt.

Đừng nhầm:

| Timeout | Nó giới hạn gì? |
| --- | --- |
| **Pool acquisition timeout** | Chờ mượn connection đang sẵn sàng hoặc được tạo. |
| **Connect timeout** | Thiết lập kết nối mạng/đăng nhập database, tùy driver. |
| **Socket/read timeout** | Chờ dữ liệu từ server trên kết nối mạng, tùy driver và thao tác. |
| **Statement/query timeout** | Thời gian một câu SQL được phép thực thi/chờ theo cơ chế driver hoặc DBMS. |
| **Lock timeout** | Thời gian chờ lấy khóa, nếu DBMS hỗ trợ. |
| **Transaction timeout** | Thời gian transaction được phép tồn tại theo framework/DBMS. |
| **Connection lifetime/idle timeout** | Vòng đời hoặc thời gian không sử dụng của kết nối vật lý. |

Một query bị khóa suốt 30 giây vẫn có thể giữ connection 30 giây dù `connectionTimeout = 2000ms`, vì timeout này chỉ áp dụng **lúc mượn connection**. Cần đặt thời gian chờ truy vấn, giao dịch và khóa phù hợp ở đúng tầng, sau đó xử lý rollback nếu transaction thất bại.

## 8. Mượn muộn và trả sớm: cách giảm nhu cầu pool trực tiếp

Giảm thời gian **giữ connection** thường giúp tăng khả năng xử lý mà không cần tạo thêm phiên ở database.

Ví dụ lỗi thiết kế:

```text
Mượn connection
  ├─ Đọc dữ liệu từ DB                  15 ms
  ├─ Gọi HTTP đến dịch vụ bên ngoài   250 ms
  ├─ Xử lý nghiệp vụ trong Java        20 ms
  ├─ Cập nhật DB                       15 ms
  └─ Trả connection

Connection bị giữ khoảng 300 ms.
```

Nếu không có ràng buộc nghiệp vụ đòi giữ một transaction xuyên suốt, có thể bố trí lại:

```text
Đọc dữ liệu cần thiết bằng kết nối ngắn
  └─ Trả connection

Gọi HTTP / tính toán không giữ connection

Mượn connection cho transaction ghi ngắn
  ├─ Kiểm tra lại điều kiện quan trọng bằng SQL/lock/version
  ├─ UPDATE/INSERT
  ├─ COMMIT
  └─ Trả connection
```

Việc tách đoạn đọc và ghi làm trạng thái có thể thay đổi trong khoảng giữa, vì vậy phải **kiểm tra lại điều kiện nghiệp vụ trong transaction ghi**. Có thể dùng `UPDATE ... WHERE ...`, cột `version`, khóa hàng hoặc mức cô lập thích hợp. Không được đổi sự đúng đắn lấy việc tiết kiệm connection.

Với JDBC, sử dụng `try-with-resources` giúp trả kết nối đúng khi hoàn thành, kể cả có exception:

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class AccountRepository {
    private final DataSource dataSource;

    public AccountRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public BigDecimal loadBalance(long accountId) throws SQLException {
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(
                     "SELECT balance FROM accounts WHERE id = ?")) {
            statement.setLong(1, accountId);

            try (ResultSet rows = statement.executeQuery()) {
                if (!rows.next()) {
                    throw new SQLException("Tai khoan khong ton tai");
                }
                return rows.getBigDecimal("balance");
            }
        } // close() trả connection về pool theo cơ chế DataSource.
    }
}
```

Nếu dùng `@Transactional` của Spring, chú ý transaction manager có thể mượn và giữ connection cho **toàn bộ phạm vi transaction**. Đừng đặt một method `@Transactional` bao quanh lời gọi API chậm rồi kỳ vọng `JdbcTemplate` tự trả connection sau từng câu SQL. Với JPA/Hibernate, thời điểm lấy connection có thể phụ thuộc transaction và cấu hình, nên phải **đo hold time thực tế**, không suy đoán từ vị trí annotation.

Ngoài ra, các nguồn làm giữ connection lâu bao gồm:

- Đọc `ResultSet` lớn bằng streaming nhưng xử lý từng dòng rất chậm.
- Giữ cursor mở khi gọi thêm dịch vụ ngoài.
- Transaction ở trạng thái **idle in transaction**: không chạy SQL nhưng chưa commit/rollback.
- Bị khóa trên một hàng nóng hoặc truy vấn quét toàn bảng.
- Quên đóng connection/statement/result set ở đường lỗi, dẫn đến **connection leak**.

Trong PostgreSQL, transaction để mở quá lâu còn có thể giữ snapshot hoặc khóa, cản trở một số công việc dọn phiên bản cũ của MVCC. Vì thế quản lý vòng đời connection còn liên quan tính ổn định của cơ sở dữ liệu ngoài việc đếm số slot pool.

## 9. Đo đồng thời pool và database, tránh tối ưu mù

Chỉ nhìn một biểu đồ “pool active = max” chưa đủ để quyết định tăng kích thước. Cần ghép số liệu **phía ứng dụng** và **phía database** trên cùng trục thời gian.

### Chỉ số từ connection pool

Với HikariCP và một hệ thống metrics phù hợp, nên theo dõi:

| Chỉ số | Cách diễn giải |
| --- | --- |
| **Active / idle / total connections** | Mức sử dụng và số kết nối đã mở trong pool. |
| **Pending threads** | Có tác vụ đang phải chờ mượn connection hay không. |
| **Acquisition duration** | p50/p95/p99 thời gian chờ mượn kết nối. |
| **Usage / hold duration** | Kết nối bị giữ bao lâu sau khi mượn. |
| **Connection timeout count** | Bao nhiêu lần không mượn được đúng hạn. |
| **Connection creation / validation failures** | Pool có gặp lỗi mở hoặc tái sử dụng kết nối không. |
| **Leak detection warnings** | Dấu hiệu mượn quá lâu cần điều tra; cảnh báo không tự chứng minh một leak thật. |

Khi dùng Spring Boot/Micrometer, các metric của Hikari thường có thể được xuất qua hệ thống quan sát. Tên cụ thể, nhãn và khả năng thu thập thay đổi theo phiên bản và cách tích hợp. Quan trọng là đo **thời gian chờ mượn** và **thời gian giữ** chứ không chỉ tổng số kết nối.

### Chỉ số phía PostgreSQL

Những truy vấn chẩn đoán đơn giản:

```sql
-- Phân bổ kết nối theo trạng thái và loại chờ hiện tại.
SELECT
    state,
    wait_event_type,
    COUNT(*) AS sessions
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY state, wait_event_type
ORDER BY sessions DESC;
```

```sql
-- Những session đang mở transaction và nhàn rỗi.
SELECT
    pid,
    application_name,
    state,
    now() - xact_start AS transaction_age,
    wait_event_type
FROM pg_stat_activity
WHERE datname = current_database()
  AND state = 'idle in transaction'
ORDER BY transaction_age DESC NULLS LAST;
```

Ngoài số phiên kết nối, còn cần đo CPU server, I/O latency/throughput, buffer cache, temp file usage, query execution time, số lượng deadlock/lock wait, WAL flush latency và replication lag (nếu có). Việc xem `pg_stat_activity` có thể bị giới hạn bởi quyền truy cập thông tin các session khác; không nên tự nâng quyền ứng dụng chỉ để lấy toàn bộ dữ liệu giám sát.

### Bảng suy luận khi tải cao

| Quan sát kết hợp | Khả năng cần kiểm tra trước | Hướng xử lý |
| --- | --- | --- |
| Pool pending cao; DB CPU/I/O thấp; thời gian hold ngắn | Pool chưa đủ để tận dụng database, hoặc phân bổ không đều giữa instance. | Thử tăng nhẹ trong ngân sách và đo lại. |
| Pool pending cao; DB CPU 100% và query latency tăng | Database đang bão hòa CPU. | Tối ưu query/index, giảm chi phí mỗi request, giới hạn tải hoặc tăng năng lực server. |
| Active cao; rất nhiều session `idle in transaction` | Transaction bị giữ mở. | Rút ngắn transaction, sửa code/timeout, tìm đường không trả kết nối. |
| Active cao; DB chờ lock nhiều | Contention trên dữ liệu. | Phân tích transaction, thứ tự khóa, điểm nóng, chia tách thao tác. |
| Active thấp; acquisition timeout cao | Có thể pool không tạo được kết nối, server từ chối hoặc có sự cố mạng. | Kiểm tra lỗi tạo kết nối, giới hạn server, driver, mạng và proxy. |
| Tăng pool nhưng throughput không tăng, p99 tăng | Đã qua điểm bão hòa hoặc contention tăng. | Giảm pool về vùng có hiệu năng tốt hơn; tìm nút nghẽn server. |

**Lưu ý:** biểu đồ pool là dữ liệu gộp của một process; nếu nhiều pod, cần xem cả theo **từng pod** lẫn tổng số, vì một pod nóng có thể timeout trong khi pod khác gần như rảnh.

## 10. Phương pháp chọn và kiểm chứng pool size bằng thử tải

Một quy trình có thể lặp lại giúp tìm cấu hình dựa trên dữ liệu thực:

1. **Xác định workload.** Phân biệt đọc/ghi, tỷ lệ request có DB, số lượt mượn trên mỗi request, truy vấn nhanh/chậm và giao dịch dài.
2. **Đặt mục tiêu rõ ràng.** Ví dụ thông lượng yêu cầu, p95/p99 latency, tỷ lệ lỗi, thời gian chờ mượn và giới hạn CPU/RAM/I/O phía database.
3. **Lập ngân sách toàn hệ thống.** Tính tất cả pool và số instance tối đa, kể cả scaling và rolling deployment.
4. **Đo hiện trạng.** Thu thập connection hold time, acquisition wait, pending, throughput, timeout và server wait events.
5. **Ước lượng sơ bộ bằng Little's Law.** Dùng trung bình trên cùng một khoảng thời gian và đúng đơn vị; kiểm tra mức burst.
6. **Thử nhiều kích thước trong ngân sách.** Ví dụ 4, 6, 9 kết nối/pod trên cùng workload, đồng thời giữ ổn định số pod, cấu hình DB và nguồn tải.
7. **So sánh đường cong, không chỉ một số trung bình.** Đo throughput, p95/p99, timeout, CPU/I/O, lock wait, WAL và thời gian giữ connection.
8. **Chọn vùng ổn định.** Tránh cấu hình sát ngưỡng bão hòa và vẫn cần khoảng đệm cho độ biến động, failover hoặc giao dịch quản trị.
9. **Kiểm thử sự cố.** Xem hệ thống phản ứng ra sao khi một pod chết, DB chậm, mất kết nối, autoscale hoặc thay đổi topology.

Ví dụ bảng kết quả **giả định để minh họa cách đọc**, không phải benchmark thực tế:

| Pool/pod | Throughput (req/s) | p95 API (ms) | Pool wait p95 (ms) | DB CPU | Nhận xét |
| ---: | ---: | ---: | ---: | ---: | --- |
| 4 | 420 | 320 | 95 | 48% | Hàng đợi tại pool tương đối lớn. |
| 6 | 505 | 250 | 24 | 67% | Cải thiện cả throughput và latency. |
| 9 | 515 | 270 | 5 | 89% | Thông lượng tăng rất ít, server gần bão hòa. |
| 12 | 510 | 410 | 3 | 98% | Đẩy nhiều việc xuống DB, độ trễ xấu hơn. |

Nếu các con số này đến từ cùng một phép thử hợp lệ, pool 6 có thể là ứng viên tốt hơn 9 hoặc 12 cho mục tiêu latency và độ ổn định; cần xét thêm SLO, burst, ngân sách và cách workload thay đổi. **Không được chọn 12 chỉ vì thời gian chờ mượn pool thấp nhất:** phần chờ có thể đã chuyển xuống máy chủ database.

### Load test cần tái hiện gì?

- **Tải đều:** xác định ngưỡng thông lượng ổn định trước khi hàng đợi tăng vô hạn.
- **Burst ngắn:** xem pending và acquisition timeout trong vài giây tăng tải.
- **Transaction dài bất thường:** kiểm tra cơ chế timeout, release và tác động của một vài request giữ connection lâu.
- **Triển khai đồng thời:** nhiều instance khởi động có thể cùng mở kết nối; xem giới hạn server và các pool khác.
- **Server suy giảm:** I/O chậm hoặc một số query bị khóa có làm request xếp hàng quá lâu hay không?

Một bài thử ảo không phản ánh tỷ lệ request và phân phối thời gian giữ kết nối thật có thể dẫn tới cấu hình sai. Nếu workload sản xuất thay đổi sau khi thêm index, tách service hay tăng lượng dữ liệu, cần đo lại.

## 11. Khi pool đầy: timeout, hàng đợi và backpressure

Giới hạn pool giúp tránh gửi số lượng truy vấn **không có giới hạn** tới database. Nhưng khi tải vượt khả năng phục vụ, việc để mọi request chờ nhiều giây trong ứng dụng cũng có thể gây cạn thread, heap, connection tới các dịch vụ khác hoặc timeout dây chuyền.

Một hệ thống chịu tải tốt thường có **nhiều tầng bảo vệ phối hợp**:

```text
Lưu lượng HTTP tăng đột biến
         │
         ▼
Giới hạn request đang xử lý / điều tiết hàng đợi
         │
         ▼
Giới hạn số tác vụ DB đồng thời (pool size)
         │
         ├─ Mượn được → transaction ngắn → trả connection
         │
         └─ Chờ quá hạn → thất bại có kiểm soát
         │
         ▼
Database trong giới hạn năng lực đã đo
```

Các thành phần cần cân nhắc:

- **Thời hạn tổng request:** thời gian chờ connection, query, lock và các bước khác phải phù hợp ngân sách latency của API.
- **Connection acquisition timeout:** đủ để hấp thụ dao động bình thường, nhưng không che giấu tình trạng quá tải kéo dài.
- **Admission control / backpressure:** giới hạn request đang thực thi, hàng đợi có kích thước hữu hạn, trả lỗi quá tải hoặc dùng retry-after theo chính sách API.
- **Query và transaction timeout:** ngăn một số truy vấn kẹt lâu chiếm toàn bộ pool.
- **Retry có kiểm soát:** tránh nhiều client đồng loạt thử lại ngay khi database đang quá tải; dùng giới hạn, jitter và idempotency.

Nếu 1000 request cùng chờ một pool 10 kết nối, tăng HTTP worker lên 1000 không tạo thêm năng lực database. Cần điều tiết đầu vào để tránh hình thành hàng đợi không giới hạn.

Trong thiết kế bất đồng bộ, một request có thể không chiếm thread xuyên suốt, nhưng **vẫn cần slot kết nối** trong lúc truy vấn; thread model của Java không làm mất giới hạn vật lý của database.

## 12. Pool phía ứng dụng khác pool/proxy phía database

Ở kiến trúc có nhiều ứng dụng, đôi khi một **database connection pooler/proxy** như PgBouncer được đặt giữa các JVM và PostgreSQL:

```text
Nhiều application instance
    ├─ HikariCP: 8 client connections
    ├─ HikariCP: 8 client connections
    └─ HikariCP: 8 client connections
                      │
                      ▼
                 PgBouncer
                      │
                      ▼
             PostgreSQL server
          (ít server connections hơn
           trong một số chế độ pooling)
```

Cần hiểu **hai giới hạn khác nhau**:

- **Pool trong ứng dụng** giới hạn số JDBC connection mà một JVM mượn và tái sử dụng, đồng thời kiểm soát hàng đợi ở ứng dụng.
- **Pooler phía database** có thể quản lý số connection thật từ proxy đến DBMS; nó có thể chia sẻ chúng giữa nhiều client nếu chế độ pooler cho phép.

Ví dụ PgBouncer có các cách pooling phổ biến:

| Chế độ | Gán server connection cho client đến khi nào? | Hệ quả |
| --- | --- | --- |
| **Session pooling** | Trong suốt session client. | Ít thay đổi giả định session của ứng dụng, nhưng khả năng multiplex thấp hơn khi có nhiều client nhàn rỗi. |
| **Transaction pooling** | Trong thời gian transaction; trả server connection sau khi transaction kết thúc. | Có thể giảm số server connection cần cho client nhàn rỗi; các thao tác phụ thuộc **trạng thái session** phải được đánh giá lại. |

Trong transaction pooling, không được mặc định trạng thái session như temporary table, một số kiểu prepared statement, session-level lock, `SET` cấp session hay biến trạng thái tồn tại trên cùng backend qua nhiều transaction. Khả năng hỗ trợ prepared statement còn phụ thuộc phiên bản và cấu hình của pooler/driver; cần thử nghiệm tích hợp thật, nhất là với ORM.

**Pooler không biến database 8 lõi thành server xử lý vô hạn truy vấn.** Nó giúp giảm chi phí số lượng session/backend và điều tiết số kết nối thật, nhưng query vẫn chia sẻ tài nguyên CPU, I/O, WAL và lock. Hàng đợi có thể chỉ chuyển từ HikariCP sang PgBouncer. Phải đo cả hai tầng nếu cùng tồn tại.

Nếu ứng dụng giữ một transaction mở lâu, transaction pooling cũng phải giữ server connection cho transaction đó, nên vẫn chịu hậu quả của giao dịch dài. Bài toán rút ngắn phạm vi transaction và xử lý timeout không mất đi.

## 13. Kết nối rò rỉ, kết nối hỏng và những sai lầm thường gặp

### Rò rỉ connection

Một đường lỗi bỏ qua `close()` có thể khiến pool active tăng dần đến maximum và mọi request mới chờ timeout. Vì vậy:

- Dùng `try-with-resources` trong JDBC hoặc ranh giới transaction/framework quản lý đáng tin cậy.
- Đóng `ResultSet`, `Statement` và kết nối theo thứ tự/khối tài nguyên hợp lý.
- Giám sát hold time và cảnh báo kết nối bị mượn quá lâu.
- Với HikariCP, có thể dùng cơ chế **leak detection threshold** trong môi trường phù hợp để hỗ trợ chẩn đoán; cảnh báo mượn lâu không nhất thiết là leak (có thể là query/transaction hợp lệ nhưng chậm).

### Kết nối đã bị server đóng

Pool giữ kết nối lâu có thể gặp firewall, proxy hoặc database đóng kết nối khi nhàn rỗi. Sau đó lần mượn tiếp theo gặp lỗi validation hoặc SQLException. Cần:

1. Hiểu timeout phía server và thiết bị mạng.
2. Cấu hình lifetime/keepalive/validation phù hợp với môi trường.
3. Xử lý lỗi transient connection ở ranh giới nghiệp vụ, rollback khi còn có thể và tạo transaction mới nếu an toàn.
4. Không tự động chạy lại một giao dịch **không rõ đã commit hay chưa** nếu chưa có cơ chế idempotency.

### Các ngộ nhận dễ dẫn đến chọn sai pool

| Nhận định | Điều cần hiểu |
| --- | --- |
| “200 request đồng thời thì cần 200 connection.” | Chỉ những request **đang giữ** kết nối mới chiếm slot; nhiều request có thể chưa cần DB. |
| “Pool càng lớn thì database càng nhanh.” | Sau điểm bão hòa, tăng pool có thể tăng contention và độ trễ. |
| “Có 8 core CPU nên bắt buộc pool bằng 8.” | Nhu cầu phụ thuộc thời gian chờ I/O, lock và đặc tính truy vấn. |
| “`max_connections = 100` thì mỗi pod dùng pool 100 được.” | Tổng các pool và dịch vụ có thể vượt giới hạn server. |
| “Active = max luôn nghĩa là pool quá nhỏ.” | Có thể DB đang chậm hoặc ứng dụng giữ connection lâu. |
| “Tăng connection timeout sẽ sửa lỗi thiếu connection.” | Chỉ làm request chờ lâu hơn; không tăng năng lực phục vụ. |
| “Đóng JDBC connection do pool cấp sẽ mở một kết nối TCP mới ở request kế tiếp.” | Thông thường `close()` trả lại connection logic cho pool để tái sử dụng. |
| “Có PgBouncer thì khỏi quan tâm transaction dài.” | Transaction dài vẫn chiếm server connection và có thể giữ lock/snapshot. |
| “Read replica luôn giải quyết hết vấn đề pool.” | Mỗi replica có năng lực và giới hạn riêng; đọc sau ghi và tính nhất quán còn cần đánh giá. |

## 14. Bài toán thực hành: thiết kế pool cho dịch vụ đặt hàng

Một dịch vụ Java có các điều kiện giả định:

- Nhận khoảng **360 request/giây** ở giờ cao điểm trên toàn cụm.
- Có **75% request** cần một lượt mượn connection; trung bình giữ **55 ms**.
- Cụm có thể có **8 instance** đồng thời khi autoscale hoặc rolling update.
- PostgreSQL giới hạn **120 connection**, trong đó dự trù **20** cho quản trị/giám sát và **28** cho các hệ thống khác.

**Bước 1: Ước lượng nhu cầu active trung bình của toàn cụm.**

```text
Lượt mượn mỗi giây = 360 × 0,75 = 270
Hold time trung bình = 0,055 giây
Active trung bình toàn cụm ≈ 270 × 0,055 = 14,85
```

Nếu tải cân bằng trên 8 instance, trung bình mỗi instance giữ khoảng **1,86 connection**, nhưng burst và phân phối không đều có thể khiến một pod cần nhiều hơn. Đây **không** phải căn cứ để đặt pool = 2.

**Bước 2: Tính ngân sách kết nối tối đa của dịch vụ.**

```text
Ngân sách dịch vụ = 120 - 20 - 28 = 72
Giới hạn tối đa theo ngân sách mỗi instance = floor(72 / 8) = 9
```

**Bước 3: Chọn các cấu hình cần đo.** Có thể thử `maximumPoolSize` = 4, 6 và 9 trên môi trường có đầy đủ 8 instance. Với mỗi cấu hình, xác nhận tổng các kết nối của toàn bộ dịch vụ không vượt ngân sách, rồi tăng tải dần và đo acquisition p95, throughput, API p99, DB CPU/I/O, wait events và timeout.

**Bước 4: Nhìn vào nguyên nhân nếu pool chờ nhiều.** Nếu pool 4 chờ lâu nhưng DB rảnh, thử 6 có thể hợp lý. Nếu pool 6 đã khiến CPU DB bão hòa và pool 9 chỉ làm SQL chậm hơn, cần tối ưu câu truy vấn, chỉ mục, transaction hoặc năng lực server trước khi mở rộng pool.

**Bước 5: Xác minh kịch bản 8 instance thật sự cùng tồn tại.** Khi deployment hoặc autoscaling, một JVM mới có thể mở thêm kết nối trong khi JVM cũ vẫn chạy. Đừng tính ngân sách theo số pod trung bình rồi để database từ chối kết nối đúng lúc rollout.

Từ các dữ kiện giả định trên, **chưa thể kết luận pool 4, 6 hay 9 là tối ưu**. Công việc còn lại là một phép thử có đo lường với workload tương ứng. Điểm đáng tin cậy đã có là: nhu cầu active trung bình và **giới hạn cứng theo ngân sách kết nối** thuộc hai phép tính khác nhau, cả hai đều cần được xét.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Có 10.000 kết nối HTTP đang mở nhưng chỉ 50 request thực hiện SQL cùng lúc. Có cần pool 10.000 connection không?

**Không.** Số HTTP connection/keep-alive không phải số JDBC connection đang được mượn. Cần đo số lượt mượn, thời gian giữ, phân phối tải và năng lực DB.

**Câu 2.** Pool thường xuyên active=max, pending tăng và DB CPU cũng gần 100%. Việc đầu tiên có phải tăng pool không?

**Không thể kết luận như vậy.** Database có thể đã bão hòa. Cần đo query latency, CPU, I/O và wait events; tăng pool có thể khiến nghẽn nặng hơn.

**Câu 3.** Một dịch vụ có 6 pod, mỗi pod đặt pool 15. Khi rollout có thể tạm có 9 pod. Database cần dự trù tối đa bao nhiêu kết nối từ dịch vụ này?

**Tới 135 kết nối** nếu cả 9 pool có thể cùng mở đủ 15 kết nối, cộng thêm các dịch vụ khác. Không được chỉ tính 6 × 15 = 90.

**Câu 4.** Little's Law với 100 lượt mượn connection/giây và hold time trung bình 30 ms cho kết quả gì?

**Khoảng 3 kết nối active trung bình**: 100 × 0,030 = 3. Đây chưa phải kích thước pool phải chọn vì chưa xét burst và giới hạn hạ tầng.

**Câu 5.** `connectionTimeout = 2s` có tự ngắt một câu SQL đang chờ khóa 30 giây không?

**Không.** Nó chủ yếu giới hạn thời gian mượn connection. Cần query/statement/lock/transaction timeout tùy cơ chế driver, DBMS và framework.

**Câu 6.** Vì sao giảm thời gian giữ connection từ 200 ms xuống 50 ms có thể giúp nhiều hơn việc tăng pool?

Với cùng số lượt mượn mỗi giây, theo Little's Law, số connection active trung bình cần thiết giảm **4 lần**. Nó giải phóng tài nguyên server và giảm chờ pool, miễn là việc rút ngắn transaction vẫn bảo vệ đúng các bất biến nghiệp vụ.

**Câu 7.** Sau khi thêm PgBouncer transaction pooling, có thể mặc định dùng lại toàn bộ state theo session PostgreSQL như trước không?

**Không.** Server connection có thể được gán lại sau mỗi transaction. Những cơ chế dựa vào session phải được kiểm tra với pooler, driver và ORM trong cấu hình thật.

## Kết luận

**Kích thước connection pool là giới hạn mức đồng thời mà ứng dụng chuyển đến database**, trong khi database chỉ có một lượng CPU, bộ nhớ, I/O, khóa, bộ ghi log và slot kết nối hữu hạn. Pool quá nhỏ tạo hàng đợi ở ứng dụng; pool quá lớn có thể đẩy hàng đợi và tranh chấp xuống server. Vì thế lựa chọn đúng cần kết hợp **ước lượng số kết nối được giữ trung bình**, **ngân sách tổng mọi instance**, **đặc điểm workload** và **thử tải quan sát cả hai phía**.

Đối với Java, cách cải thiện nền tảng là mượn kết nối khi cần, trả ngay khi xong, giữ transaction ngắn và kiểm soát timeout/connection leak. Sau đó mới điều chỉnh pool size theo metric và năng lực máy chủ. Một cấu hình được đo và kiểm chứng dưới tải thực tế sẽ đáng tin cậy hơn bất kỳ công thức “số CPU × hệ số” hoặc việc tăng pool mỗi khi thấy request chậm.
