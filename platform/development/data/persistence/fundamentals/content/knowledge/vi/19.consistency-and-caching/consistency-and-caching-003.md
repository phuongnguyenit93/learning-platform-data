# Đọc từ nguồn sau ghi và yêu cầu thấy dữ liệu vừa cập nhật

Một người dùng đổi tên hồ sơ, nhận thông báo **“Lưu thành công”**, nhưng ngay khi tải lại trang lại thấy tên cũ. Lỗi này có thể xuất hiện ngay cả khi câu UPDATE chạy đúng, giao dịch đã COMMIT và cơ sở dữ liệu chính không mất dữ liệu. Nguyên nhân thường nằm ở **đường đọc**: request tiếp theo được chuyển tới read replica chưa bắt kịp hoặc cache vẫn giữ phiên bản trước khi ghi.

Trong hệ thống có nhiều bản sao và nhiều tầng lưu trữ, một yêu cầu nghiệp vụ thường cần bảo đảm **read-your-writes**: sau khi ghi được xác nhận, cùng người dùng hoặc phiên làm việc có thể đọc được ít nhất trạng thái chứa thay đổi của mình, trừ khi một thay đổi mới hơn đã thay thế nó. Bài thuộc chương **Nhất quán và cache** của module **DATA_PERSISTENCE_FUNDAMENTALS**, nơi người học thiết kế persistence cho Java từ lược đồ, truy vấn và chỉ mục đến giao dịch, cô lập, xử lý lỗi kết nối, sao lưu và tối ưu hiệu năng. Ví dụ dùng **PostgreSQL, JDBC, Spring và mô hình cache-aside**; chi tiết về LSN, replication và routing phụ thuộc hệ quản trị, driver, hạ tầng triển khai thực tế.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

- Diễn giải chính xác **read-your-writes**, phân biệt với eventual consistency, monotonic reads và linearizability.
- Xác định vì sao một COMMIT thành công trên primary chưa bảo đảm request đọc qua replica hoặc cache thấy ngay thay đổi.
- Thiết kế đường đọc sau ghi bằng **đọc từ primary**, **primary affinity**, **consistency token/replication watermark** hoặc **chờ replica bắt kịp có giới hạn**.
- Phân biệt trạng thái **trong transaction**, **sau COMMIT**, **trong persistence context** và **trên các bản sao dữ liệu**.
- Phối hợp cache invalidation, TTL và version để tránh dữ liệu cũ được nạp lại sau khi đã xóa cache.
- Viết code Java/JDBC và tổ chức transaction/routing trong Spring theo một hợp đồng nhất quán rõ ràng.
- Kiểm thử tình huống replica chậm, cache cũ, hai request đồng thời, commit không rõ kết quả và failover.

## 2. Chính xác thì “thấy dữ liệu vừa cập nhật” có nghĩa gì?

Giả sử người dùng U sửa một bản ghi:

~~~text
t0  GET profile            --> name = "An"
t1  PUT profile            --> name = "Bình"
t2  Server trả 200 OK      --> giao dịch đã COMMIT
t3  GET profile bởi U      --> phải thấy "Bình" hoặc phiên bản mới hơn
~~~

Điều người dùng mong đợi tại **t3** là một ví dụ của **read-your-writes (RYW)**. Bảo đảm này nói về **thứ tự quan sát của chính một người dùng/phiên**, không tự yêu cầu mọi người trên toàn cầu thấy thay đổi ngay cùng một thời điểm.

Cần tách các khái niệm:

| Bảo đảm | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- |
| **Eventual consistency** | Nếu không có ghi mới, các bản sao có hội tụ sau một khoảng thời gian không? | Replica bắt kịp primary về sau |
| **Read-your-writes** | Sau khi chính tôi ghi thành công, lần đọc tiếp theo của tôi có thấy thay đổi không? | Lưu hồ sơ rồi xem lại |
| **Monotonic reads** | Các lần đọc tiếp theo của tôi có tránh quay về phiên bản cũ hơn lần đã đọc không? | Trang A thấy version 8, trang B không quay lại version 6 |
| **Monotonic writes** | Các ghi của cùng phiên có được áp dụng theo đúng thứ tự cần thiết không? | Đổi địa chỉ rồi xác nhận địa chỉ mới |
| **Linearizability** | Mỗi thao tác có vẻ xảy ra tức thời tại một điểm giữa lúc gọi và lúc trả kết quả, tôn trọng thứ tự thời gian thực trên toàn hệ thống không? | Một thao tác đọc sau ghi hoàn tất phải phù hợp thứ tự toàn cục |

RYW và monotonic reads là những **session guarantees** thường dùng để xây dựng trải nghiệm nhất quán trên hệ phân tán. Một hệ thống có thể cung cấp RYW cho người vừa ghi nhưng cho những người khác đọc dữ liệu cũ tạm thời từ replica.

**RYW không cam kết giá trị luôn đúng bằng dữ liệu mình vừa gửi.** Nếu người dùng U ghi version 8 rồi một người khác ghi hợp lệ version 9 trước lần GET của U, việc đọc version 9 có thể hoàn toàn đúng: nó đã chứa trạng thái mới hơn. Để bảo vệ ý định chỉnh sửa trước cạnh tranh, cần thêm **optimistic locking, kiểm tra version hoặc quy tắc hợp nhất**, không chỉ thay đổi nơi đọc.

## 3. Bài toán khi có primary, replica và cache

Kiến trúc thường gặp:

~~~text
                    API Java
                       |
          +------------+------------+
          |                         |
     Đường ghi                   Đường đọc
          |                         |
          v                         v
       Primary ----------------> Read replica
          |       replication       |
          |         có độ trễ        |
          +-----> Cache <-----------+
                 (có thể chứa
                  bản cũ hơn)
~~~

Một lịch thực thi gây lỗi:

~~~text
Thời gian      Primary              Replica                 Cache
t0             name = "An"          name = "An"             "An"
t1  UPDATE     name = "Bình"        name = "An"             "An"
t2  COMMIT     xác nhận             đang chậm                "An"
t3  GET        không được đọc       có thể trả "An"         có thể trả "An"
t4             ...                  replay thay đổi          cache vẫn có thể cũ
t5             name = "Bình"        name = "Bình"           chưa chắc đã đổi
~~~

**Hai độ trễ khác nhau** đang xuất hiện:

1. **Replication lag:** standby/replica chưa nhận, flush hoặc replay đủ thay đổi từ primary.
2. **Cache staleness:** bản ghi trong cache chưa bị xóa hoặc cập nhật; ngay cả khi replica đã bắt kịp, cache vẫn có thể trả giá trị cũ.

Ngoài ra còn **trễ ở tầng ứng dụng**: projection được cập nhật qua message broker, search index, service khác hoặc persistence context cũ có thể làm dữ liệu vẫn chưa được nhìn thấy. Phải lần theo đường đọc thực tế, không mặc định mọi lần GET đều gọi database primary.

## 4. Đọc trong cùng transaction khác đọc sau COMMIT

Trong một transaction PostgreSQL, giao dịch thường đọc được **thay đổi của chính mình** qua các câu lệnh tiếp theo, dù các transaction khác chưa nhìn thấy thay đổi ấy:

~~~sql
BEGIN;

UPDATE customer_profiles
SET display_name = 'Bình'
WHERE tenant_id = 10 AND customer_id = 501;

SELECT display_name
FROM customer_profiles
WHERE tenant_id = 10 AND customer_id = 501;
-- Thông thường thấy "Bình" trong chính transaction.

COMMIT;
~~~

Điều này khác với trường hợp:

~~~text
Request #1:
  BEGIN trên primary
  UPDATE profile
  COMMIT
  trả HTTP 200

Request #2:
  GET trên replica hoặc cache
  có thể thấy dữ liệu cũ
~~~

Trong transaction, database theo dõi những ghi của chính transaction đó. Sau COMMIT, một request mới có thể được định tuyến sang nguồn dữ liệu khác. **Transaction boundary không tự tạo session affinity xuyên các request HTTP.**

Một khác biệt nữa: **flush không phải commit**. Với JPA/Hibernate, gọi **entityManager.flush()** có thể gửi UPDATE xuống DB nhưng transaction vẫn có thể rollback. Không được chuyển người dùng sang một replica và coi dữ liệu đã được xác nhận chỉ vì flush thành công.

### 4.1. Đọc primary vẫn có thể không mới trong mọi điều kiện

Đọc từ primary **sau COMMIT đã thành công**, trong một transaction đọc mới và dùng đúng đường truy cập, thường là cơ chế đơn giản nhất để thấy ghi đã xác nhận. Nhưng có ngoại lệ cần phân biệt:

- Một transaction **REPEATABLE READ** đã xác lập snapshot **trước khi** giao dịch kia commit có thể tiếp tục thấy dữ liệu cũ, kể cả khi nó đang kết nối tới cùng primary.
- Một persistence context JPA đã quản lý entity cũ có thể trả instance đang giữ trong memory, không tự tải lại từ DB.
- Một lớp cache/ORM/query result cache hoặc proxy vẫn có thể trả dữ liệu đã lưu từ trước.
- Giao dịch khác có thể đã ghi một phiên bản mới hơn.

Vì vậy, phát biểu chính xác không phải “cứ primary là luôn mới”, mà là **đọc từ primary bằng đường đọc không sử dụng trạng thái cũ, sau khi transaction ghi đã commit, với snapshot thích hợp**.

## 5. Hợp đồng nhất quán nên được thiết kế theo use case

Không phải mọi màn hình cần cùng mức nhất quán:

| Use case | Yêu cầu thường gặp | Đường đọc hợp lý |
| --- | --- | --- |
| Lưu hồ sơ rồi xem lại | Phải thấy thay đổi của chính mình | Primary ngay sau ghi hoặc token/fence trên replica |
| Thêm sản phẩm vào giỏ rồi mở giỏ | Không được “mất” món vừa thêm | Session RYW, primary hoặc dữ liệu phiên đã xác nhận |
| Thanh toán rồi xem trạng thái đơn | Không thể báo chưa thanh toán chỉ do replica chậm | Primary cho kết quả quan trọng hoặc API trạng thái có consistency contract |
| Dashboard phân tích nhiều ngày | Có thể chấp nhận trễ vài phút | Replica, cache hoặc projection có SLA freshness rõ |
| Danh sách bài viết công khai | Trễ ngắn có thể chấp nhận | Cache/replica với TTL, invalidation phù hợp |
| Phân quyền tài khoản và quyền quản trị | Không được tùy tiện sử dụng dữ liệu quyền cũ sau thu hồi | Quy tắc nhất quán và cache an toàn riêng; thường cần nguồn có bảo đảm mạnh |

Điểm xuất phát nên là **điều người dùng hoặc nghiệp vụ cần**, sau đó mới chọn kỹ thuật. Không đặt RYW cho mọi API theo bản năng nếu chi phí primary quá cao; cũng không hy sinh tính đúng đắn của màn hình xác nhận thanh toán để tăng cache hit rate.

## 6. Phương án đơn giản nhất: đọc primary sau khi ghi

Một thiết kế thường dễ kiểm chứng:

1. Ghi vào primary trong một transaction.
2. Chỉ trả thành công sau khi COMMIT hoàn tất.
3. Với request đọc liên quan ngay sau ghi, buộc đường đọc đi tới primary.
4. Sau một điều kiện kết thúc được xác định, cho phép đọc lại từ replica/cache.

Sơ đồ:

~~~text
PUT profile --> Primary --> COMMIT --> 200 + version
                                      |
                                      v
GET profile ngay sau ghi ----------> Primary
                                      |
                                      v
                                thấy version >= vừa ghi
~~~

Ưu điểm: đơn giản, dễ test, không cần chờ replica. Đánh đổi: tăng tải đọc trên primary và cần **định tuyến đúng** nếu ứng dụng có nhiều DataSource.

### 6.1. Primary affinity có thời hạn

Một ứng dụng có thể giữ chế độ **“đọc primary sau ghi”** trong một khoảng thời gian ngắn:

~~~text
Session U vừa commit thay đổi lúc t0
  |
  +-- read requests gắn affinity PRIMARY
  +-- sau khi hết cửa sổ affinity thì quay lại REPLICA
~~~

Đây là một **heuristic**, không phải bằng chứng replica đã bắt kịp. Nếu replication lag vượt cửa sổ affinity, request đọc sau đó vẫn có thể thấy dữ liệu cũ. Vì vậy, chỉ dùng time window khi nghiệp vụ chấp nhận rủi ro đó hoặc có điều kiện kiểm tra freshness bổ sung.

Trong hệ thống có nhiều instance API, lưu cờ affinity **chỉ trong RAM của một instance** có thể bị mất khi request tiếp theo đến instance khác. Có thể dùng token phiên, shared session store hoặc route hint được kiểm tra phía server; không để client tự chỉ định bất kỳ database endpoint nào được phép truy cập.

## 7. JDBC: ghi trên primary, đọc lại bằng một transaction mới

Giả sử bảng:

~~~sql
CREATE TABLE customer_profiles (
    tenant_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    display_name TEXT NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, customer_id)
);
~~~

Một repository có DataSource **primary** tách biệt với DataSource **replica** có thể tổ chức đường ghi như sau:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class ProfileRepository {
    private final DataSource primary;
    private final DataSource replica;

    public ProfileRepository(DataSource primary, DataSource replica) {
        this.primary = primary;
        this.replica = replica;
    }

    public record Profile(long id, String name, long version) {}

    public Profile changeName(
            long tenantId, long customerId, String newName,
            long expectedVersion
    ) throws SQLException {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }

        try (Connection connection = primary.getConnection()) {
            connection.setAutoCommit(false);
            try {
                long newVersion;
                String sql = """
                    UPDATE customer_profiles
                    SET display_name = ?, version = version + 1
                    WHERE tenant_id = ? AND customer_id = ?
                      AND version = ?
                    RETURNING version
                    """;
                try (PreparedStatement st = connection.prepareStatement(sql)) {
                    st.setString(1, newName);
                    st.setLong(2, tenantId);
                    st.setLong(3, customerId);
                    st.setLong(4, expectedVersion);
                    try (ResultSet rs = st.executeQuery()) {
                        if (!rs.next()) {
                            throw new IllegalStateException(
                                    "Không tồn tại hoặc version đã thay đổi");
                        }
                        newVersion = rs.getLong(1);
                    }
                }

                connection.commit();
                return new Profile(customerId, newName, newVersion);
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

    public Profile readFromPrimary(long tenantId, long customerId)
            throws SQLException {
        return read(primary, tenantId, customerId);
    }

    public Profile readFromReplica(long tenantId, long customerId)
            throws SQLException {
        return read(replica, tenantId, customerId);
    }

    private static Profile read(
            DataSource source, long tenantId, long customerId
    ) throws SQLException {
        String sql = """
            SELECT display_name, version
            FROM customer_profiles
            WHERE tenant_id = ? AND customer_id = ?
            """;
        try (Connection connection = source.getConnection();
             PreparedStatement st = connection.prepareStatement(sql)) {
            st.setLong(1, tenantId);
            st.setLong(2, customerId);
            try (ResultSet rs = st.executeQuery()) {
                if (!rs.next()) {
                    throw new IllegalStateException("Không tìm thấy hồ sơ");
                }
                return new Profile(
                        customerId, rs.getString(1), rs.getLong(2));
            }
        }
    }
}
~~~

Code này minh họa **đường đọc và ghi**, chưa có lớp kiểm soát quyền truy cập: **tenantId/customerId phải được xác thực và ủy quyền ở phía server**. Bảng và connection phải được cấu hình phù hợp trong môi trường thật.

Điểm cần hiểu:

- **changeName** chỉ trả kết quả thành công khi **connection.commit()** thành công theo phản hồi JDBC. Nếu mất kết nối lúc commit, phía gọi vẫn có thể không biết server đã commit hay chưa.
- **RETURNING version** cho biết version vừa được UPDATE trong transaction, nhưng một giá trị RETURNING trước COMMIT chưa phải chứng cứ đã commit.
- **readFromPrimary** thực hiện một SELECT mới trên primary; đây là đường đọc ưu tiên khi người vừa ghi cần RYW.
- **readFromReplica** có thể trả version thấp hơn vì replication lag. Code **chưa** áp chính sách chờ replica hoặc watermark; router/service phải lựa chọn phương thức phù hợp.
- Điều kiện **version = expectedVersion** giúp tránh ghi đè một cập nhật đồng thời, nhưng không thay thế RYW cho lần đọc sau.

## 8. Dùng version trả về để nhận diện dữ liệu đọc quá cũ

Khi mỗi bản ghi có **version tăng đơn điệu** được cập nhật cùng transaction, response ghi có thể trả:

~~~text
PUT /profiles/501
  --> 200 OK
  --> {"id": 501, "version": 8}

GET /profiles/501?minVersion=8
  --> chỉ được trả dữ liệu có version >= 8
      (nếu chưa có, chuyển sang primary hoặc báo tạm chờ)
~~~

Trong server, **minVersion là một yêu cầu mức mới tối thiểu**, không phải bản thân dữ liệu được phép tin cậy vô điều kiện. Server cần gắn nó với người dùng, tenant, bản ghi và đúng nguồn dữ liệu; không được dùng tham số này để vượt qua kiểm tra quyền.

Một luồng đọc:

~~~text
Client gửi minVersion=8
         |
         v
Đọc replica --> version 6?
         |
         +-- Có --> đọc primary, hoặc chờ có giới hạn
         |
         +-- Không (version >= 8) --> trả kết quả
~~~

Đây là kỹ thuật **version gate** đơn giản cho một bản ghi. Những giới hạn:

- Version cục bộ của bản ghi **không đủ** để bảo đảm góc nhìn nhất quán xuyên nhiều hàng/bảng.
- Nếu bản ghi bị xóa, chỉ kiểm tra “không tìm thấy” không đủ để phân biệt chưa được replicate với việc đã xóa hợp lệ; cần tombstone, event/version hoặc đọc nguồn chuẩn tùy hợp đồng.
- Nếu version có thể bị reset do restore, thay khóa hoặc migration, phải có **generation/epoch** hoặc cách nhận diện nguồn dữ liệu để tránh so sánh sai.
- Nếu nhiều actor cùng sửa, version lớn hơn có thể chứa thay đổi của người khác; giao diện cần quyết định có hiển thị xung đột hay không.

Version gate đặc biệt hữu ích khi client đã có version mới từ kết quả cập nhật và cần chống việc cache hoặc replica trả về bản cũ.

## 9. Chờ replica bắt kịp bằng WAL/LSN trong PostgreSQL

Với **physical streaming replication**, PostgreSQL có các vị trí WAL biểu diễn dữ liệu đã tạo, đã ghi, đã flush hoặc đã replay. Một ý tưởng mạnh hơn time window là sử dụng **replication watermark**:

1. Transaction ghi trên primary **COMMIT thành công**.
2. Lấy một **LSN fence** trên primary sau COMMIT, ví dụ vị trí WAL đã flush tại thời điểm đó.
3. Trước khi đọc trên standby, kiểm tra standby đã **replay ít nhất tới LSN fence** chưa.
4. Nếu đã bắt kịp, đọc từ standby; nếu chưa, chờ có deadline hoặc đọc primary.

Trong một luồng PostgreSQL thuần, sau COMMIT, có thể lấy:

~~~sql
-- Chạy trên PRIMARY sau khi transaction ghi đã COMMIT thành công:
SELECT pg_current_wal_flush_lsn();
~~~

Hàm trả về vị trí WAL đã flush cục bộ ở primary tại thời điểm gọi. **Lấy sau COMMIT** là điều kiện quan trọng: vị trí lấy trước khi gửi COMMIT có thể không bao gồm bản ghi commit của giao dịch. Fence lấy sau commit có thể bao gồm cả WAL của giao dịch khác, nên nó là **mốc bảo thủ**: standby chờ nhiều hơn một chút nhưng không thiếu commit vừa xác nhận.

Trên standby PostgreSQL vật lý, kiểm tra:

~~~sql
-- Tham số ? là LSN fence do ứng dụng lưu dưới dạng văn bản.
SELECT COALESCE(
    pg_last_wal_replay_lsn() >= CAST(? AS pg_lsn),
    FALSE
);
~~~

**pg_last_wal_replay_lsn()** biểu thị vị trí WAL đã được replay trên standby; nó khác vị trí WAL **nhận** hoặc **ghi vào đĩa**. Chỉ việc standby đã nhận WAL chưa chắc các thay đổi của WAL đó đã nhìn thấy trong truy vấn.

### 9.1. Mốc replay phải được kiểm tra trước câu đọc cần nhất quán

~~~text
Primary: UPDATE --> COMMIT --> lấy fence F
                                    |
                                    v
Standby: replay_lsn >= F ? --- không ---> chờ hoặc fallback primary
                                    |
                                   có
                                    |
                                    v
                          SELECT từ standby
~~~

Sau khi xác nhận replay đã vượt F, một SELECT mới với snapshot phù hợp ở cùng standby có thể quan sát các thay đổi đã replay đến F. Một transaction REPEATABLE READ đã mở và giữ snapshot cũ có thể không đáp ứng điều kiện dù LSN sau đó đã tiến lên; việc **chọn snapshot đọc mới** vẫn quan trọng.

Điều kiện và giới hạn:

- So sánh LSN chỉ có ý nghĩa trong **cùng chuỗi lịch sử WAL/timeline phù hợp**. Sau failover, thay primary, logical replication hoặc đổi cluster, không mù quáng so sánh LSN từ các nguồn khác nhau.
- WAL fence sau commit chỉ là tín hiệu cơ sở dữ liệu đã replay; **cache, search index, materialized projection hoặc service khác** có thể vẫn cũ.
- LSN chỉ nói về thứ tự WAL, không tự là transaction ID nghiệp vụ. Cần có cơ chế ánh xạ/đối soát khi khôi phục sau commit không rõ kết quả.
- Nếu standby lag lâu hoặc không truy cập được, router phải có **deadline và fallback**, không chờ vô hạn.
- Khi có nhiều standby, fence phải được kiểm tra trên **đúng standby sẽ phục vụ SELECT**, hoặc router phải bảo đảm standby được chọn đạt cùng watermark.

### 9.2. Không dùng số giây lag như bằng chứng duy nhất

Một metric như **now() - pg_last_xact_replay_timestamp()** có thể hữu ích để quan sát, nhưng khi primary lâu không có transaction, giá trị thời gian tính từ lần replay cuối có thể tăng dù standby đã bắt kịp. Vì vậy, nó **không phải bằng chứng tuyệt đối** cho việc một commit cụ thể đã replay. Khi yêu cầu một ghi nhất định phải hiển thị, dùng watermark/LSN, version hoặc primary fallback gắn với ghi đó.

## 10. Consistency token xuyên nhiều request và nhiều instance

Nếu request ghi và request đọc có thể đến các API instance khác nhau, cần một cơ chế giữ mốc:

~~~text
API instance A:
  COMMIT hồ sơ version 8
  trả {"version":8} hoặc token đã bảo vệ
              |
              v
Client / Session store giữ mốc 8
              |
              v
API instance B:
  GET profile với minVersion=8
  chọn replica đã đủ mới, nếu không -> primary
~~~

Một consistency token nên mô tả tối thiểu:

- **Phạm vi**: tenant, subject/resource hoặc phạm vi phiên phù hợp.
- **Mốc mới tối thiểu**: version bản ghi hoặc replication watermark.
- **Nguồn và epoch** nếu mốc chỉ có ý nghĩa trong một cluster/timeline.
- **Thời hạn sống và phiên bản định dạng** để xử lý thay đổi hạ tầng.
- **Tính toàn vẹn**: ký hoặc bảo vệ token khi client có thể chỉnh sửa; tránh để người dùng giả tạo route hint làm quá tải primary hoặc truy cập nguồn không được phép.

Nếu một phiên có nhiều lần ghi, mốc RYW cần được **nâng lên** theo thao tác mới. Với version của **cùng một bản ghi**, dùng version lớn nhất đã biết. Với token global, cần cách so sánh đúng theo nguồn và thế hệ, không so số không cùng timeline.

**RYW khác monotonic reads.** Một client có thể chưa từng ghi nhưng đã đọc version 9; sau đó bị chuyển sang replica version 7. Nếu sản phẩm yêu cầu **monotonic reads**, phải giữ mốc đọc cao nhất, không chỉ mốc do client tự ghi.

## 11. Cache-aside: vì sao invalidation rất quan trọng?

Trong mô hình **cache-aside**:

~~~text
GET:
  cache HIT -> trả dữ liệu cache
  cache MISS -> đọc DB -> ghi cache -> trả kết quả

UPDATE:
  ghi DB
  COMMIT
  xóa hoặc cập nhật key cache liên quan
~~~

Nếu request GET sau ghi chỉ đọc cache và cache còn dữ liệu cũ, RYW bị phá vỡ dù replica đã bắt kịp.

Một trình tự thường dùng khi sử dụng cache-aside là **commit DB trước, rồi invalidation cache**. Không xóa cache trước khi transaction DB commit và mặc định an toàn, vì người đọc đồng thời có thể thấy dữ liệu cũ rồi nạp lại cache.

Ví dụ:

~~~text
T1: UPDATE profile trên DB (chưa commit)
T1: DELETE cache key
T2: GET cache MISS
T2: SELECT DB --> thấy bản cũ (T1 chưa commit)
T2: SET cache = bản cũ
T1: COMMIT
--> cache giữ giá trị cũ
~~~

Đặt invalidation **sau COMMIT** giảm cửa sổ này, nhưng **không loại bỏ mọi race condition**.

## 12. Race condition: xóa cache sau commit vẫn chưa đủ

Một tình huống khó hơn:

~~~text
T1: GET cache MISS
T1: SELECT DB --> đọc version 7
T1: xử lý chậm trước khi SET cache

T2: UPDATE DB --> version 8
T2: COMMIT
T2: DELETE cache key

T1: SET cache = version 7
--> Cache lại chứa dữ liệu cũ sau khi đã invalidated
~~~

Đây là **stale cache repopulation**. Xóa key sau COMMIT là một bước cần thiết trong nhiều thiết kế, nhưng không phải bảo đảm tuyệt đối khi nhiều request tương tác song song.

Các lựa chọn để bảo vệ nghiêm ngặt hơn:

1. **Version gate khi đọc**: response vừa ghi mang version 8; nếu cache trả version 7, bỏ qua cache và đọc primary/nguồn đủ mới.
2. **Versioned cache key**: thay vì cache cố định theo **profile:501**, dùng khóa chứa version đã xác nhận, ví dụ **profile:501:v8**; vẫn cần nguồn xác định version hiện hành một cách nhất quán.
3. **Compare-and-set theo version** khi cập nhật cache: chỉ chấp nhận ghi cache nếu version mới không thấp hơn version đang có. Việc xóa/invalidate và thao tác đồng thời cũng phải được thiết kế nhất quán.
4. **TTL** hạn chế thời gian dữ liệu lỗi tồn tại, nhưng TTL **không bảo đảm RYW ngay lập tức**.
5. **Đọc primary sau ghi** cho màn hình yêu cầu tính mới, thay vì dựa vào cache chung trong cửa sổ nhạy cảm.

Không phải ứng dụng nào cũng cần chi phí của version fence trên toàn bộ cache. Với nội dung công khai, chấp nhận vài giây stale có thể là quyết định tốt. Với trạng thái thanh toán và quyền truy cập, phải chọn hợp đồng mạnh hơn.

## 13. Bảo đảm phát invalidation sau commit

Trong Spring, một phương pháp phổ biến là phát thông báo ở giai đoạn **AFTER_COMMIT**, thay vì xóa cache trước khi transaction thực sự thành công:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

record ProfileChanged(long tenantId, long profileId, long version) {}

@Component
class ProfileCacheInvalidator {
    private final ProfileCache cache;

    ProfileCacheInvalidator(ProfileCache cache) {
        this.cache = cache;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onProfileChanged(ProfileChanged event) {
        cache.invalidate(event.tenantId(), event.profileId());
    }
}
~~~

Ví dụ giả định **ProfileCache** là abstraction do ứng dụng cài đặt, và service ghi **publish** sự kiện **ProfileChanged** trong transaction được Spring quản lý. **@TransactionalEventListener** thường chỉ được kích hoạt đúng theo transaction context đang tồn tại; không tự mặc định chạy khi không có transaction. Đây là minh họa về **thời điểm invalidation**, không phải pipeline phân phối sự kiện bền vững.

**Lỗ hổng còn lại:** process có thể crash **sau COMMIT nhưng trước khi listener xóa cache**. Vì vậy, nếu invalidation là cam kết quan trọng, cần cơ chế bền vững hơn:

- Ghi một **outbox event** vào **cùng transaction DB** với thao tác cập nhật.
- Sau commit, worker đọc outbox và phát thông tin invalidation.
- Consumer xử lý trùng theo event ID/version, retry có backoff và theo dõi backlog.
- Dùng TTL/version gate hoặc primary fallback để không để một invalidation chậm phá vỡ yêu cầu RYW.

Outbox đưa **ý định thông báo** vào transaction, nhưng cache vẫn có thể cũ trong lúc worker chưa xử lý. Nó không tự cho một request GET bảo đảm “thấy ngay” nếu GET chỉ đọc cache và không kiểm tra freshness.

## 14. Cache write-through, write-behind và cache-aside

| Mô hình | Luồng ghi | Tác động tới RYW |
| --- | --- | --- |
| **Cache-aside** | Ứng dụng ghi DB rồi xóa/cập nhật cache | Có cửa sổ cache stale và race; cần chiến lược invalidation và đọc phù hợp |
| **Write-through** | Ghi đi qua thành phần cache/lớp phối hợp để cập nhật backing store | Bảo đảm phụ thuộc atomicity và hợp đồng của cả hai lớp; không tự là transaction phân tán |
| **Write-behind/write-back** | Ghi vào cache trước, lưu DB về sau | DB có thể chưa chứa thay đổi khi API báo nhận; phải định nghĩa độ bền và đồng bộ rất cẩn thận |
| **Read-through** | Cache tự nạp từ nguồn khi miss | Vẫn có thể nạp dữ liệu cũ từ replica và vẫn có race |

Một “cache hit” không phải bằng chứng nội dung đúng thời điểm. Nếu API trả 200 sau khi ghi cache nhưng DB chưa commit, cần mô tả rõ đó là **accepted/pending** hay **confirmed**. Không trộn bảo đảm eventual của projection với API vốn đã hứa giao dịch DB hoàn tất.

## 15. Spring và routing DataSource: lưu ý về transaction

Một ứng dụng Spring thường có primary và replica DataSource, rồi dùng một router để chọn đường đọc/ghi. Quy tắc tưởng chừng đơn giản:

~~~text
@Transactional(readOnly = false) --> primary
@Transactional(readOnly = true)  --> replica
~~~

Nhưng **readOnly = true không có nghĩa truy vấn luôn được đọc từ một replica phù hợp RYW**. Nó thường là gợi ý/hành vi tối ưu cho transaction manager và provider; routing còn phụ thuộc cách cấu hình DataSource, thời điểm connection thực sự được lấy, và transaction hiện có.

Những rủi ro:

- **Transaction đã bind connection rồi:** nếu một method bên trong muốn chuyển sang replica hoặc primary sau khi connection đã được cấp, router không nhất thiết có thể đổi nguồn giữa giao dịch.
- **Propagation REQUIRED:** method đọc có thể tham gia transaction cha đã có, nên readOnly hoặc routing hint của method con không tự tạo connection mới.
- **Self-invocation:** một bean gọi **this.loadAfterWrite()** có thể bỏ qua proxy @Transactional.
- **JPA persistence context:** entity đã managed có thể được trả từ context cũ; đổi DataSource không tự xóa identity map.
- **Replica lag:** ngay cả routing readOnly đúng sang replica, nó vẫn không bảo đảm RYW nếu thiếu fence.

Để bảo vệ RYW, nên có một **hợp đồng API rõ ràng** như **readStronglyConsistent()**, **readAtLeastVersion(...)** hoặc **readWithSessionFence(...)**, thay vì gán mọi request GET vào replica chỉ dựa vào HTTP method hoặc annotation.

### 15.1. Mẫu điều phối ở application service

~~~java
// Pseudocode minh họa chính sách, không phải router Spring hoàn chỉnh.
Profile readProfile(
        long tenantId, long profileId, Long minVersion) {

    if (minVersion == null) {
        return repository.readFromReplica(tenantId, profileId);
    }

    Profile fromReplica = repository.readFromReplica(
            tenantId, profileId);
    if (fromReplica.version() >= minVersion) {
        return fromReplica;
    }

    return repository.readFromPrimary(tenantId, profileId);
}
~~~

Pseudocode trên **chưa xử lý trường hợp replica không có hàng, replica bị lỗi hoặc dữ liệu đã bị xóa**. Trong triển khai thật, router phải có fallback an toàn khi không tìm thấy hoặc replica timeout, đặt deadline, xét quyền tenant, và phân biệt **version** của một hàng với fence cho nhiều bảng. Đường primary cũng cần truy vấn với transaction/snapshot mới, tránh context đang giữ dữ liệu cũ.

## 16. Các nguồn dữ liệu phát sinh bất đồng bộ

Không chỉ read replica tạo độ trễ. Một hệ thống có thể phát sự kiện khi đơn hàng thay đổi, sau đó cập nhật **search index**, **materialized view**, **BI projection** hoặc **service danh sách đơn**:

~~~text
Primary DB: order CONFIRMED --COMMIT--> outbox event
                                      |
                                      v
                                  message broker
                                      |
                                      v
                         projection/search index cập nhật sau
~~~

Ngay sau COMMIT, trang **chi tiết đơn** đọc primary có thể trả CONFIRMED, nhưng trang **tìm kiếm đơn** đọc projection vẫn liệt kê trạng thái cũ. Đây không phải lỗi transaction của primary; nó là **hợp đồng nhất quán xuyên các mô hình dữ liệu** chưa được đảm bảo.

Nếu sản phẩm bắt buộc “lưu xong phải tìm thấy ngay”:

- Đọc từ nguồn chính cho nội dung ngay sau ghi, hoặc hiển thị trạng thái đang đồng bộ minh bạch.
- Dùng **event version/offset** ở projection và chờ nó xử lý tối thiểu tới mốc của thao tác ghi.
- Có deadline, fallback và xử lý projection không khả dụng.
- Không coi broker đã nhận event là bằng chứng search index đã áp dụng event.

Outbox giải quyết nguy cơ **đã commit DB nhưng thất lạc ý định phát sự kiện** trong phạm vi thiết kế; nó không bảo đảm consumer đã xử lý ngay tại thời điểm người dùng nhận HTTP 200.

## 17. Những điều RYW không giải quyết được

RYW là một phần của tính nhất quán quan sát, nhưng các bất biến dữ liệu khác cần cơ chế riêng:

| Vấn đề | Vì sao chỉ RYW chưa đủ? | Cơ chế bổ sung |
| --- | --- | --- |
| Hai người cùng sửa một entity | Tôi thấy ghi của mình không ngăn người khác ghi đè tiếp | **@Version**, optimistic locking, conflict handling |
| Hai request cùng trừ tồn kho | Đọc lại sau ghi không ngăn cùng bán một đơn vị hàng | UPDATE có điều kiện, ràng buộc, transaction |
| Nhiều bảng cần thay đổi cùng nhau | RYW không đặt ranh giới atomicity cho nhiều câu SQL | Một DB transaction với commit/rollback |
| Dữ liệu quyền truy cập bị thu hồi | Cache cũ có thể còn cho phép thao tác không hợp lệ | Quy tắc xác thực/ủy quyền và consistency cho security-critical reads |
| API nhận timeout khi COMMIT | Client không biết write có thực sự commit không | Request ID, idempotency, đối soát |
| Đọc bản mới nhưng giao diện mất một lần cập nhật do race UI | Cập nhật hiển thị và response về không theo thứ tự | Client version guard, thứ tự request, cache key và xử lý race |
| Lỗi sau khi gửi email hoặc message | Transaction DB không hoàn tác tác dụng ngoài | Outbox, consumer idempotent, saga khi cần |

Đặc biệt, **không được suy rằng RYW đồng nghĩa linearizability**. Một hệ thống có thể cho U đọc bản mới ngay sau ghi nhưng các người dùng khác vẫn thấy bản cũ trong khoảng replica lag. Nếu nghiệp vụ cần mọi actor có một thứ tự quan sát nhất quán toàn cục, cần hợp đồng mạnh hơn và đánh giá chi phí riêng.

## 18. Quan sát replication lag và đường đọc

Khi chẩn đoán “lưu rồi mà đọc thấy cũ”, hãy thu thập:

- **Write confirmation:** thao tác có thực sự COMMIT hay chỉ flush/queue một công việc?
- **Primary read:** bản ghi trên primary ở version nào?
- **Read routing:** request GET đã đi primary, replica nào, cache nào hay projection nào?
- **Replica progress:** standby đã replay tới đâu so với fence cần thấy?
- **Cache:** hit/miss, key, version, TTL, lần invalidation và nguồn nạp lại.
- **Transaction/context:** query có chạy trong snapshot cũ hoặc dùng entity managed trước đó không?
- **Client:** có response từ request cũ đến muộn ghi đè trạng thái mới trong UI không?

### 18.1. Một số truy vấn PostgreSQL phục vụ điều tra

Trên primary (với quyền phù hợp):

~~~sql
SELECT application_name,
       client_addr,
       state,
       sync_state,
       sent_lsn,
       write_lsn,
       flush_lsn,
       replay_lsn
FROM pg_stat_replication;
~~~

Trên standby:

~~~sql
SELECT pg_is_in_recovery() AS is_standby,
       pg_last_wal_receive_lsn() AS received_lsn,
       pg_last_wal_replay_lsn() AS replayed_lsn,
       pg_last_xact_replay_timestamp() AS last_replayed_commit_time;
~~~

Hai giá trị **receive_lsn** và **replay_lsn** có thể khác nhau: WAL đã tới standby nhưng chưa được áp dụng đầy đủ. Một chỉ số thời gian lag không tự chứng minh request cụ thể đã được replay. Các cột và quyền quan sát phụ thuộc phiên bản PostgreSQL; nếu dùng logical replication, cách theo dõi và bảo đảm có thể khác.

### 18.2. Metrics ở ứng dụng Java

Các số liệu đáng theo dõi:

| Chỉ số | Ý nghĩa |
| --- | --- |
| **ryw_primary_fallback_total** | Số lần phải đọc primary vì replica/cache chưa đủ mới |
| **ryw_fence_wait_duration** | Thời gian chờ standby đạt watermark |
| **replica_read_stale_total** | Số lần phiên bản đọc thấp hơn yêu cầu |
| **cache_stale_hit_total** | Cache trả phiên bản thấp hơn minVersion |
| **cache_invalidation_delay** | Độ trễ từ commit tới lúc invalidation được áp |
| **primary_read_qps / replica_read_qps** | Tải tương đối ở từng đường đọc |
| **read_after_write_violation_total** | Trường hợp quan sát thấy vi phạm hợp đồng nhất quán đã định nghĩa |

Đừng chỉ ghi một metric chung “database latency”. Cần biết chính xác request đi qua nguồn nào, snapshot/context nào và version nhận được. Không đưa dữ liệu hồ sơ, token phiên hay thông tin nhạy cảm vào log mà không có chính sách bảo vệ.

## 19. Chiến lược fallback và xử lý lỗi

Khi replica quá chậm hoặc không khả dụng, có một số lựa chọn:

1. **Fallback primary:** ưu tiên tính mới, tăng tải primary. Cần giới hạn tải và bảo vệ primary khỏi bị dồn đọc trong sự cố diện rộng.
2. **Wait with deadline:** đợi replica đạt fence trong khoảng thời gian cho phép, rồi chuyển primary hoặc trả trạng thái rõ ràng nếu không đáp ứng SLA.
3. **Trả trạng thái pending:** phù hợp cho projection bất đồng bộ, nơi hợp đồng cho phép nội dung chưa xuất hiện ngay; cần endpoint trạng thái hoặc polling hợp lý.
4. **Đọc cache có version gate:** chỉ nhận cache entry nếu đáp ứng minVersion; nếu không, bỏ qua.
5. **Degrade có thông báo:** với dashboard không quan trọng, có thể hiển thị “Dữ liệu cập nhật đến ...” thay vì giả vờ mới nhất.

Không nên retry GET liên tục không giới hạn khi replica chậm. Việc chờ nhiều vòng gây thêm tải, giữ connection lâu và có thể làm chính replica chậm hơn. Đặt deadline, backoff ngắn có jitter nếu cần, và cơ chế backpressure.

### 19.1. Trường hợp commit chưa rõ kết quả

Nếu client gửi COMMIT và mất kết nối trước khi nhận phản hồi, nó **chưa thể nói chắc ghi đã thành công**. Lúc này vấn đề không chỉ là RYW; trước hết phải xác định trạng thái của **ý định ghi**:

~~~text
request_id ổn định
    |
    +-- Tra ở primary: thao tác đã commit?
    |       |
    |       +-- Có: lấy version/fence, bảo đảm RYW cho lần đọc
    |       +-- Chưa biết: không tự lặp thao tác không lũy đẳng
    |
    +-- Retry cùng request_id qua unique constraint khi an toàn
~~~

Idempotency key và kết quả nghiệp vụ nên được lưu cùng transaction ghi, để request lặp có thể đối chiếu thay vì tạo thêm đơn hoặc trừ tiền hai lần.

## 20. Kiểm thử read-your-writes có kiểm soát

Kiểm thử chỉ trên một database đơn lẻ không đủ xác minh routing qua replica/cache. Cần các trường hợp:

1. **Ghi rồi đọc primary:** cập nhật profile, đợi COMMIT thành công, mở transaction đọc mới, xác minh version đã cập nhật.
2. **Replica chậm:** chặn/giảm tốc replication trong môi trường test có kiểm soát; request mang minVersion phải chờ hoặc fallback, không trả bản cũ như bản mới.
3. **Cache cũ:** nạp trước version 7 vào cache, ghi version 8, kiểm tra GET yêu cầu minVersion=8 không trả version 7.
4. **Race nạp lại cache:** một GET đã lấy bản cũ, sau đó UPDATE commit và invalidate, rồi GET cũ mới ghi cache; kiểm tra version gate hoặc CAS loại dữ liệu stale.
5. **Nhiều API instance:** PUT tại instance A, GET tại instance B; token/affinity phải được bảo toàn.
6. **Nhiều lần ghi:** người dùng tạo version 8 rồi 9; các lần đọc phải đáp ứng mốc cao nhất theo hợp đồng.
7. **Commit thất bại hoặc không rõ kết quả:** không phát token cam kết thành công trước COMMIT; dùng đối soát khi kết quả bất định.
8. **Failover:** token LSN thuộc timeline/cluster cũ phải được xử lý an toàn, không so sánh bừa với mốc trên primary mới.
9. **Transaction snapshot cũ:** REPEATABLE READ bắt đầu trước ghi có thể nhìn thấy cũ; router cần transaction/snapshot mới.
10. **Xóa bản ghi:** GET không thấy hàng có thể là do lag hoặc xóa thực sự; đảm bảo tombstone/fence hoặc primary fallback theo hợp đồng.

Nên dùng **điểm đồng bộ rõ ràng trong test**, giả lập replication/cache delay và xác minh version, thay vì chỉ chèn một **Thread.sleep(1000)** rồi hy vọng timing trùng với race condition. Đo cả correctness và thời gian fallback để biết chi phí bảo đảm RYW.

## 21. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “COMMIT thành công nên GET nào cũng thấy ngay.” | GET có thể đi replica, cache hoặc projection chưa cập nhật |
| “Đọc primary luôn mới bất kể transaction nào.” | Snapshot cũ hoặc persistence context stale vẫn có thể trả dữ liệu cũ |
| “Dùng READ COMMITTED là giải quyết được replica lag.” | Isolation cục bộ không điều khiển tiến độ replica |
| “Gửi @Transactional(readOnly=true) thì có RYW.” | readOnly không buộc đọc primary hoặc đợi replica |
| “Xóa cache trước COMMIT là an toàn.” | Có thể bị nạp lại bản cũ khi transaction chưa commit |
| “Xóa cache sau COMMIT thì không bao giờ stale.” | GET song song có thể nạp lại bản cũ; còn nguy cơ crash trước invalidation |
| “TTL ngắn đồng nghĩa đọc thấy ghi ngay.” | TTL chỉ hạn chế thời gian cũ, không cho bảo đảm tức thì |
| “Replica đã nhận WAL nghĩa là query đã thấy.” | Phải phân biệt nhận, flush và replay WAL |
| “LSN ở hai cluster bất kỳ so sánh được.” | LSN chỉ có nghĩa theo đúng lịch sử WAL/timeline |
| “RYW ngăn mất cập nhật do hai writer.” | Cần version/locking/atomic update riêng |
| “Mỗi request có session affinity trên một server nên chắc chắn RYW.” | Router DB, cache và chuyển instance vẫn có thể phá bảo đảm |
| “Outbox làm search index cập nhật ngay lúc COMMIT.” | Outbox lưu ý định sự kiện bền vững; consumer vẫn xử lý bất đồng bộ |

## 22. Bài tập tự kiểm tra

### Bài 1. Ghi thành công nhưng xem lại thấy cũ

Người dùng sửa tên từ “An” thành “Bình”. PUT trả 200 sau COMMIT trên primary, GET ngay sau đi tới replica chưa replay thay đổi. Đây là lỗi ở đâu?

**Gợi ý:** Đường đọc chưa đáp ứng read-your-writes. Có thể chuyển GET sau ghi sang primary hoặc yêu cầu replica đạt version/LSN fence trước khi trả kết quả.

### Bài 2. Read-your-writes hay monotonic reads?

Người dùng chỉ xem dữ liệu (không sửa). GET đầu thấy version 12, GET sau thấy version 9 vì được chuyển replica khác. Bảo đảm nào bị vi phạm?

**Gợi ý:** **Monotonic reads**. Nếu hợp đồng chỉ bảo đảm RYW cho những thao tác do người dùng ghi, tình huống này cần quy tắc phiên đọc bổ sung.

### Bài 3. Flush và commit

Một service JPA sửa entity rồi gọi **flush()**, sau đó transaction rollback. Có nên trả “Lưu thành công” hoặc cấp token version đã commit không?

**Gợi ý:** Không. Flush không phải commit; dữ liệu chưa được xác nhận bền vững. Chỉ phát tín hiệu ghi thành công sau khi transaction commit thành công theo cơ chế đã chọn.

### Bài 4. Cache vừa xóa đã cũ

T1 đọc version 7 từ DB nhưng chưa ghi cache. T2 commit version 8 và xóa cache. T1 sau đó ghi version 7 vào cache. Vì sao **delete cache after commit** chưa đủ?

**Gợi ý:** GET cũ có thể tái nạp bản stale sau invalidation. Dùng version gate, CAS/versioned keys hoặc primary bypass cho yêu cầu cần RYW.

### Bài 5. LSN fence

Ứng dụng lấy **pg_current_wal_flush_lsn()** trước khi COMMIT rồi dùng mốc đó để đợi replica. Mốc này có chắc bao gồm bản ghi COMMIT của chính giao dịch không?

**Gợi ý:** Không. Phải lấy fence **sau khi COMMIT thành công** hoặc dùng cơ chế khác bảo đảm fence nằm sau commit cần quan sát. Trên standby, phải kiểm tra WAL đã **replay**, không chỉ receive.

### Bài 6. Timeout khi chờ replica

Replica cần 15 giây để bắt kịp, nhưng API có deadline 2 giây. Làm sao giữ RYW mà không giữ request vô hạn?

**Gợi ý:** Chờ có giới hạn rồi fallback primary, hoặc trả trạng thái pending minh bạch nếu hợp đồng nghiệp vụ cho phép. Không trả bản cũ như dữ liệu mới và không loop chờ vô hạn.

### Bài 7. Cập nhật quyền truy cập

Quản trị viên vừa thu hồi quyền của một người dùng, nhưng cache phân quyền còn giá trị cũ. Vì sao TTL 30 giây có thể không phù hợp?

**Gợi ý:** Quyền truy cập cần hợp đồng nhất quán và bảo mật riêng. Chấp nhận stale đến 30 giây có thể tiếp tục cho phép thao tác không được phép; cần kiểm soát invalidation/version/nguồn kiểm tra phù hợp với mô hình đe dọa.

### Bài 8. Lưu trên primary, đọc bằng EntityManager cũ

Một transaction JPA đã nạp entity version 5. Transaction khác commit version 6. Method hiện tại gọi **find** lần nữa và vẫn thấy version 5. Có nhất thiết là lỗi replica không?

**Gợi ý:** Không. Entity managed trong persistence context hiện tại hoặc snapshot REPEATABLE READ có thể làm dữ liệu cũ vẫn được thấy. Cần xem lifecycle, isolation và việc có dùng context/transaction mới hay không.

### Bài 9. Search index bất đồng bộ

Tạo bài viết trên primary thành công rồi tìm kiếm chưa thấy bài. Có thể áp trực tiếp fence LSN của PostgreSQL lên search index để xác nhận đã cập nhật không?

**Gợi ý:** Không mặc định. Search index phải có cơ chế theo dõi offset/event version riêng và xác nhận consumer đã áp sự kiện. LSN của physical standby không tự chứng minh trạng thái ở một hệ lưu trữ khác.

## 23. Checklist thiết kế read-your-writes

Trước khi triển khai một chức năng “lưu xong xem lại”, hãy xác nhận:

1. **Định nghĩa hợp đồng:** đọc lại của ai, trong bao lâu, trên tài nguyên nào và có cho phép phiên bản mới hơn không?
2. **Write confirmation:** HTTP 200 có nghĩa DB đã COMMIT hay chỉ tiếp nhận công việc?
3. **Source of truth:** nguồn nào giữ trạng thái được xác nhận? Read replica/cache/index là bản sao hay nguồn chính?
4. **Read routing:** request tiếp theo có thể đến instance, DataSource hoặc vùng khác không?
5. **Consistency fence:** dùng primary, version, LSN hoặc offset nào; mốc có đúng nguồn/timeline không?
6. **Snapshot/context:** câu đọc có thể tái sử dụng transaction hoặc persistence context cũ không?
7. **Cache:** invalidation diễn ra khi nào; có stale repopulation, TTL hoặc lỗi mất sự kiện không?
8. **Fallback:** khi replica hoặc cache chưa đủ mới, chờ bao lâu, chuyển primary thế nào và giới hạn tải ra sao?
9. **Error handling:** commit không rõ kết quả có request ID/idempotency và cách đối soát không?
10. **Observability:** có version, route, lag/watermark, cache hit và metrics để xác minh SLA không?
11. **Security:** tenant/resource và consistency token có được ủy quyền, xác thực và bảo vệ không?
12. **Tests:** có kịch bản nhiều instance, replica lag, cache race, failover và giao dịch rollback không?

## 24. Tổng kết

**Read-your-writes** là bảo đảm rằng sau khi một người dùng đã ghi thành công, những lần đọc tiếp theo theo phạm vi đã định **không quay về trạng thái cũ hơn ghi đó**. Cần phân biệt rõ **COMMIT trên primary**, **replication replay**, **cache invalidation**, **projection bất đồng bộ** và **snapshot/persistence context** của request đọc. Mỗi tầng có thể làm dữ liệu nhìn thấy bị chậm dù bản ghi trên primary đã đúng.

Giải pháp dễ kiểm chứng nhất cho use case cần thấy ngay là **đọc primary sau COMMIT bằng một transaction/snapshot mới**. Khi cần mở rộng tải đọc, có thể sử dụng **version gate, LSN/replication watermark, session token, chờ replica có deadline và primary fallback**. Với cache, invalidation sau commit là nền tảng nhưng cần tính tới **race nạp lại bản cũ**, nên kết hợp version và cơ chế thông báo bền vững khi phù hợp. Đặt tính nhất quán theo yêu cầu nghiệp vụ, đo độ trễ thực tế và kiểm thử các tình huống lỗi để tầng persistence Java vừa đúng dữ liệu, vừa giữ được hiệu năng.
