# Hệ thống ngoại lệ Spring Data và ngoại lệ gốc từ Driver

**Chương: Xử lý lỗi** — Spring Data Cassandra.

Khi dùng **Spring Data Cassandra** để truy cập Apache Cassandra, một lỗi có thể xuất hiện dưới tên lớp của Spring hoặc của Java Driver. Hai tên đó thường mô tả **cùng một sự cố ở hai tầng trừu tượng**. Chẳng hạn, Cassandra trả về lỗi đọc quá thời gian; Driver nhận `ReadTimeoutException`, còn tầng truy cập dữ liệu của Spring có thể chuyển thành `CassandraReadTimeoutException` để mã ứng dụng xử lý theo hệ thống `DataAccessException`.

Hiểu rõ các tầng này giúp trả lời ba câu hỏi quan trọng: **đã hỏng ở đâu, dữ liệu đã được ghi hay chưa, và có an toàn để thử lại không?** Với hệ thống phân tán, việc chỉ nhìn thông báo “timeout” rồi retry mọi yêu cầu có thể tạo ghi trùng, tăng tải lên cụm Cassandra hoặc che giấu thiết kế bảng chưa phù hợp với truy vấn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt `DataAccessException` của Spring, ngoại lệ trong `org.springframework.data.cassandra` và `DriverException` của Java Driver.
- Giải thích cơ chế dịch ngoại lệ ở `CassandraRepository`, `CassandraTemplate`, `CqlTemplate` và trường hợp gọi `CqlSession` trực tiếp.
- Nhận diện khác biệt giữa timeout ở Driver, timeout do coordinator trả về, thiếu replica, không kết nối được node và truy vấn CQL không hợp lệ.
- Lần theo `cause`, kiểm tra lỗi trên từng node khi gặp `AllNodesFailedException` và chọn hành động xử lý phù hợp.
- Xây dựng xử lý lỗi nhất quán cho API đồng bộ hoặc reactive, giữ nguyên nguyên nhân gốc để quan sát và điều tra.

## 2. Hai tầng ngoại lệ: Spring và Cassandra Java Driver

### 2.1. Đường đi của một truy vấn

~~~mermaid
flowchart TD
    A["Service / API"] --> B["CassandraRepository / CassandraTemplate / CqlTemplate"]
    B --> C["Cassandra Java Driver 4.x"]
    C --> D["Coordinator và các replica Cassandra"]
    D -->|"Phản hồi lỗi CQL / consistency"| C
    C -->|"DriverException hoặc lỗi khác"| E["Bộ dịch ngoại lệ của Spring Data"]
    E -->|"Nếu dịch được"| F["DataAccessException (Spring)"]
    E -->|"Không thuộc diện dịch"| G["Ngoại lệ gốc / ngoại lệ ở tầng khác"]
    F --> A
    G --> A
~~~

Sơ đồ mô tả luồng thường gặp khi truy vấn đi qua **API truy cập dữ liệu do Spring Data cung cấp**. Không phải mọi ngoại lệ đều bắt nguồn từ Cassandra server: sai định dạng dữ liệu khi ánh xạ entity, cấu hình ứng dụng, lỗi mã Java hoặc sử dụng API không đúng có thể xảy ra ngay tại client.

| Tầng | Vai trò | Nhóm kiểu thường gặp | Ứng dụng nên làm gì? |
|---|---|---|---|
| Cassandra server | Kiểm tra CQL, tính nhất quán và thực thi đọc/ghi | Mã lỗi như `READ_TIMEOUT`, `WRITE_TIMEOUT`, `UNAVAILABLE`, `INVALID` | Hiểu trạng thái thực thi và replica |
| Java Driver 4.x | Giao tiếp cluster, chọn node, giải mã lỗi và áp dụng retry policy | `DriverException`, `ReadTimeoutException`, `AllNodesFailedException` | Dùng khi cần thông tin kỹ thuật chuyên sâu |
| Spring Data Cassandra | Dịch ngoại lệ phù hợp với hợp đồng truy cập dữ liệu Spring | `CassandraReadTimeoutException`, `CassandraInvalidQueryException`, ... | Thường bắt ngoại lệ ở biên repository/service |
| Spring DAO | Cung cấp cây ngoại lệ độc lập công nghệ lưu trữ | `DataAccessException`, `QueryTimeoutException`, `InvalidDataAccessApiUsageException` | Xây dựng xử lý lỗi chung cho tầng nghiệp vụ |

Ví dụ một chuỗi nguyên nhân có thể trông như sau:

~~~text
org.springframework.data.cassandra.CassandraReadTimeoutException
  caused by: com.datastax.oss.driver.api.core.servererrors.ReadTimeoutException
    consistency=LOCAL_QUORUM, received=1, blockFor=2
~~~

Đây là **ví dụ minh họa**, không phải định dạng stack trace bắt buộc. Thông báo và lớp bọc thực tế phụ thuộc phiên bản Driver, Spring Data, loại API đang gọi và vị trí sự cố.

### 2.2. Cây ngoại lệ của Spring

Lớp gốc để ứng dụng Spring xử lý lỗi truy cập dữ liệu là `org.springframework.dao.DataAccessException`, một `RuntimeException`. Các nhóm con diễn tả tính chất của lỗi, chứ không bảo đảm một chiến lược retry luôn đúng.

~~~text
DataAccessException
├── TransientDataAccessException
│   ├── QueryTimeoutException
│   │   ├── CassandraReadTimeoutException
│   │   ├── CassandraWriteTimeoutException
│   │   └── CassandraDriverTimeoutException
│   └── CassandraInsufficientReplicasAvailableException
└── NonTransientDataAccessException
    ├── InvalidDataAccessApiUsageException
    │   ├── CassandraQuerySyntaxException
    │   └── CassandraInvalidQueryException
    └── NonTransientDataAccessResourceException
        └── DataAccessResourceFailureException
            └── CassandraConnectionFailureException
~~~

Các tên bắt đầu bằng `Cassandra...` trong sơ đồ thuộc gói `org.springframework.data.cassandra`; phần còn lại thuộc `org.springframework.dao`. Sơ đồ chỉ trích các nhánh tiêu biểu, không trình bày toàn bộ cây kế thừa. Đặc biệt, `CassandraConnectionFailureException` kế thừa `DataAccessResourceFailureException` mặc dù nguyên nhân kết nối trong thực tế đôi khi chỉ tạm thời. **Không được mặc định rằng mọi lỗi có chữ “Transient” đều nên retry, hoặc lỗi “NonTransient” luôn không thể phục hồi.**

### 2.3. Cây ngoại lệ của Java Driver

Với Java Driver 4.x, các ngoại lệ do Driver phát sinh thường kế thừa `com.datastax.oss.driver.api.core.DriverException`. Những nhóm cần nhớ:

- **Lỗi trả về từ coordinator:** `com.datastax.oss.driver.api.core.servererrors.ReadTimeoutException`, `WriteTimeoutException`, `UnavailableException`, `InvalidQueryException`, `SyntaxError`, `UnauthorizedException`.
- **Lỗi timeout phía client:** `com.datastax.oss.driver.api.core.DriverTimeoutException` — Driver không nhận được kết quả trong hạn chờ của yêu cầu; khác với timeout được server chủ động báo.
- **Lỗi sau khi thử các node:** `com.datastax.oss.driver.api.core.AllNodesFailedException`; `NoNodeAvailableException` là một trường hợp thuộc nhóm này.
- **Lỗi khác phía client:** cấu hình/codec/ánh xạ có thể phát sinh các ngoại lệ riêng hoặc ngoại lệ Java thông thường, và không nhất thiết được bộ dịch ngoại lệ Cassandra chuyển đổi.

Từ Java Driver 4.x, phần lớn lớp Driver nằm trong gói `com.datastax.oss.driver.api.core...`. Ví dụ cũ viết với `com.datastax.driver.core...` thuộc Driver 3.x; tránh trộn hai hệ package khi tìm tài liệu hoặc xử lý ngoại lệ.

## 3. Spring Data dịch ngoại lệ như thế nào?

Spring Data Cassandra cung cấp `org.springframework.data.cassandra.core.cql.CassandraExceptionTranslator`, thực thi hợp đồng `CqlExceptionTranslator` / `PersistenceExceptionTranslator`. Bộ dịch này cố gắng ánh xạ một ngoại lệ từ Driver thành ngoại lệ tương ứng trong hệ thống Spring DAO:

1. Nếu đầu vào đã là `DataAccessException`, ngoại lệ đó được giữ nguyên.
2. Nếu đầu vào là `DriverException` được nhận diện, Spring chọn một `DataAccessException` cụ thể và giữ ngoại lệ Driver trong chuỗi nguyên nhân khi có thể.
3. Với `DriverException` chưa có quy tắc chi tiết, có thể dùng `CassandraUncategorizedException`.
4. Với một `RuntimeException` không thuộc nhóm Driver cần dịch, phương thức `translateExceptionIfPossible(...)` có thể trả về `null`; không có bảo đảm mọi lỗi Java đều biến thành `DataAccessException`.

Điều này giúp tầng service bắt `QueryTimeoutException` hoặc `DataAccessException` mà không phụ thuộc trực tiếp Driver. Tuy nhiên, khi phân tích replica, consistency, node coordinator hay write type, vẫn cần xem `cause` là lớp Driver cụ thể nào.

**Phạm vi áp dụng:** thao tác qua repository, `CassandraTemplate`, `CqlTemplate` và các thành phần Spring Data thường tham gia cơ chế chuyển đổi. Nếu tự inject `CqlSession` rồi gọi `session.execute(...)`, ngoại lệ có thể đi ra trực tiếp từ Driver; **đừng giả định** rằng chỉ vì lớp của bạn có `@Repository` thì mọi lời gọi Driver đều được dịch. Với bean repository tùy biến, cơ chế dịch qua AOP còn phụ thuộc cấu hình `PersistenceExceptionTranslationPostProcessor` và translator thích hợp.

### 3.1. Bảng đối chiếu để đọc stack trace

| Nguyên nhân / lớp Driver | Lớp Spring Data thường gặp | Ý nghĩa cần kiểm tra | Hướng xử lý ban đầu |
|---|---|---|---|
| `ReadTimeoutException` | `CassandraReadTimeoutException` | Coordinator chờ phản hồi đọc từ replica quá hạn | Kiểm tra `received`, `blockFor`, `dataPresent`, latency, tải replica |
| `WriteTimeoutException` | `CassandraWriteTimeoutException` | Coordinator không nhận đủ xác nhận ghi đúng hạn | **Không kết luận ghi thất bại**; xem `writeType` và tính idempotent |
| `DriverTimeoutException` | `CassandraDriverTimeoutException` | Client hết hạn chờ phản hồi Driver | Kiểm tra network, request timeout, coordinator quá tải; phân biệt với server timeout |
| `UnavailableException` | `CassandraInsufficientReplicasAvailableException` | Không đủ replica sẵn sàng cho consistency yêu cầu | Kiểm tra RF, CL, node/down, DC, repair/topology |
| `AllNodesFailedException` / `NoNodeAvailableException` | Có thể được ánh xạ thành lỗi kết nối như `CassandraConnectionFailureException` tùy tình huống | Các node được thử đều thất bại | Xem lỗi **trên từng node** trước khi kết luận |
| `InvalidQueryException` | `CassandraInvalidQueryException` | CQL đúng cú pháp nhưng không hợp lệ với schema/quy tắc truy vấn | Sửa query, mô hình bảng, khóa phân vùng hoặc binding |
| `SyntaxError` | `CassandraQuerySyntaxException` | Sai cú pháp CQL | Sửa CQL, kiểm tra tên định danh và câu lệnh sinh ra |
| `UnauthorizedException` | `CassandraUnauthorizedException` | Tài khoản không có quyền thao tác | Kiểm tra grant/role và nguyên tắc quyền tối thiểu |
| `AlreadyExistsException` | `CassandraTableExistsException` / `CassandraKeyspaceExistsException` | Tạo schema đã tồn tại | Làm rõ trạng thái migration/schema, tránh tạo lặp |

Bảng là **bản đồ chẩn đoán**, không phải cam kết ánh xạ một-một cho mọi phiên bản. Một ngoại lệ Driver có thể bị gói trong `AllNodesFailedException` hoặc một ngoại lệ Java khác; nếu lỗi xảy ra trước tầng dịch, service cũng có thể nhìn thấy kiểu khác. Khi cần catch theo lớp cụ thể, xác nhận trên bộ phiên bản Spring Data/Driver thực tế của dự án.

## 4. Phân biệt các tình huống lỗi dễ nhầm

### 4.1. Timeout do coordinator và timeout do Driver

**Server-side read timeout:** Coordinator đã nhận lệnh truy vấn nhưng không thu đủ phản hồi cần thiết trước thời hạn chờ nội bộ. Driver nhận `ReadTimeoutException`. Các thông tin quan trọng gồm:

- `getConsistencyLevel()`: mức nhất quán của yêu cầu.
- `getReceived()` và `getBlockFor()`: số phản hồi nhận được và số phản hồi cần có.
- `wasDataPresent()`: có nhận được dữ liệu thực hay chỉ các phản hồi dạng digest; đặc biệt hữu ích khi phân tích read timeout.

**Server-side write timeout:** Coordinator không thu đủ xác nhận ghi. `WriteTimeoutException` có thể mang thêm `getWriteType()`. Không thể suy ra rằng mọi replica đều chưa ghi: một số đã áp dụng mutation trước khi coordinator báo timeout.

**Driver-side timeout:** `DriverTimeoutException` xuất hiện khi Driver không hoàn tất yêu cầu trong hạn chờ của chính nó, ví dụ coordinator chưa phản hồi tới client. Khi đó không nhất thiết có một phản hồi lỗi `READ_TIMEOUT`/`WRITE_TIMEOUT` từ server.

Ví dụ cùng hiển thị “timeout” trên dashboard nhưng cách điều tra khác nhau:

| Tình huống | Quan sát hữu ích | Rủi ro khi xử lý sai |
|---|---|---|
| Read timeout từ server | Consistency, `received/blockFor`, `wasDataPresent`, metric replica | Retry hàng loạt làm cụm càng nghẽn |
| Write timeout từ server | Write type, thời điểm và khóa của mutation, độ idempotent | Ghi trùng hoặc tác dụng phụ lặp |
| Driver timeout | Timeout budget ở client, network, pool, coordinator, tracing | Tăng timeout che mất nút nghẽn hoặc làm request chồng chất |

### 4.2. `UNAVAILABLE` khác `READ_TIMEOUT`

Giả sử keyspace có **replication factor 3**, yêu cầu `LOCAL_QUORUM` cần **2 replica** của local DC xác nhận:

- Chỉ có 1 replica được nhận biết là sẵn sàng ngay khi xử lý → coordinator có thể trả `UNAVAILABLE` (`UnavailableException`).
- Có đủ replica để bắt đầu, nhưng quá hạn vẫn chỉ nhận 1 phản hồi → có thể nhận `READ_TIMEOUT` (`ReadTimeoutException`).

Hai trường hợp dẫn đến quyết định vận hành khác nhau. Với `UNAVAILABLE`, kiểm tra trạng thái node, topology, datacenter và mức consistency. Với timeout, còn phải xem tải, các partition nóng, truy vấn quá rộng, tombstone, disk/GC và network. Không hạ consistency chỉ để làm lỗi biến mất nếu điều đó phá vỡ yêu cầu đúng đắn dữ liệu.

### 4.3. `AllNodesFailedException` không chỉ là “cluster down”

Driver có thể thử nhiều coordinator. Khi tất cả đường thử đều lỗi, ngoại lệ bề ngoài có thể là `AllNodesFailedException` thay vì từng lỗi riêng lẻ. Trong Java Driver 4.x hiện đại, `getAllErrors()` trả về bản đồ từ node đến danh sách lỗi tương ứng.

~~~java
import com.datastax.oss.driver.api.core.AllNodesFailedException;
import com.datastax.oss.driver.api.core.metadata.Node;
import java.util.List;
import java.util.Map;

void inspectNodeFailures(AllNodesFailedException ex) {
    for (Map.Entry<Node, List<Throwable>> entry : ex.getAllErrors().entrySet()) {
        Node node = entry.getKey();
        for (Throwable failure : entry.getValue()) {
            // Ghi log an toàn: loại lỗi và định danh node phù hợp;
            // không ghi token, mật khẩu hoặc toàn bộ dữ liệu truy vấn.
            System.out.printf("node=%s, error=%s%n",
                    node.getHostId(),
                    failure.getClass().getSimpleName());
        }
    }
}
~~~

Trong một số phiên bản Driver cũ hơn, API chi tiết khác (`getErrors()` thay vì `getAllErrors()`); đối chiếu Javadoc đúng phiên bản. Nếu ngoại lệ đã bị Spring bọc, trước hết tìm `AllNodesFailedException` trong chuỗi `cause` rồi mới xem các lỗi theo node. Một node có thể lỗi kết nối, node khác có thể quá tải; đừng chẩn đoán toàn cụm chỉ từ tên lớp bọc.

### 4.4. Truy vấn CQL sai có thể là vấn đề thiết kế dữ liệu

Xét bảng thiết kế theo truy vấn lấy hồ sơ theo ID:

~~~sql
CREATE TABLE profiles_by_id (
    profile_id uuid PRIMARY KEY,
    display_name text,
    email text
);

-- Đúng với partition key:
SELECT profile_id, display_name
FROM profiles_by_id
WHERE profile_id = ?;

-- Không phù hợp với khóa của bảng nếu không có index/cơ chế hỗ trợ:
SELECT profile_id, display_name
FROM profiles_by_id
WHERE email = ?;
~~~

Truy vấn thứ hai có thể bị từ chối hoặc yêu cầu lọc ngoài khả năng của mô hình hiện tại. `InvalidQueryException` được dịch thành `CassandraInvalidQueryException` không phải sự cố tạm thời: retry cùng câu truy vấn sẽ không làm cấu trúc bảng thay đổi. Cách sửa thường là bảng tra cứu theo `email`/một truy vấn cụ thể, index phù hợp với workload, hoặc thay đổi điều kiện truy vấn; tránh dùng `ALLOW FILTERING` như giải pháp mặc định cho truy vấn sản xuất.

Tương tự, `SyntaxError` thường do cú pháp sai, còn lỗi mapping/conversion có thể xuất hiện **trước hoặc sau** truy vấn và không nhất thiết thuộc nhánh `DriverException`. Hãy phân biệt “CQL sai” với “entity Java không đọc được kết quả CQL”.

Với truy vấn **paging**, page size quá lớn hoặc một partition quá rộng có thể làm tăng độ trễ và dẫn đến timeout. Paging state cũng gắn với truy vấn và tiến trình phân trang; không tái sử dụng tùy tiện cho câu lệnh hay tham số khác. Lỗi lúc lấy trang sau cần được đánh giá như lỗi truy cập dữ liệu thực, không được âm thầm coi là “đã hết dữ liệu”.

## 5. Bắt ngoại lệ ở tầng ứng dụng

Nguyên tắc thực hành: tầng truy cập dữ liệu giữ thông tin kỹ thuật; tầng service quyết định có thể chuyển sang lỗi nghiệp vụ hay lỗi hạ tầng; tầng API mã hóa kết quả theo hợp đồng của hệ thống. Không nên để controller biết mọi package ngoại lệ của Driver.

### 5.1. Ví dụ với Spring Data Repository

Giả sử đã ánh xạ `CustomerProfile` cho bảng `profiles_by_id`:

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;
import org.springframework.data.cassandra.repository.CassandraRepository;

@Table("profiles_by_id")
public class CustomerProfile {
    @PrimaryKey("profile_id")
    private UUID id;

    @Column("display_name")
    private String displayName;

    // Constructor và getter/setter được lược bỏ để tập trung vào xử lý lỗi.
}

interface CustomerProfileRepository
        extends CassandraRepository<CustomerProfile, UUID> {
}
~~~

Ở tầng service, bắt các nhánh mà service thực sự xử lý được. Ví dụ sau phân loại timeout và sự cố replica/kết nối thành lỗi tạm thời của chức năng đọc hồ sơ, trong khi lỗi API/query sai được giữ lại để điều tra:

~~~java
import java.util.Optional;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.InvalidDataAccessApiUsageException;
import org.springframework.dao.QueryTimeoutException;
import org.springframework.data.cassandra.CassandraConnectionFailureException;
import org.springframework.data.cassandra.CassandraInsufficientReplicasAvailableException;
import org.springframework.stereotype.Service;

@Service
public class ProfileService {
    private static final Logger log = LoggerFactory.getLogger(ProfileService.class);
    private final CustomerProfileRepository repository;

    public ProfileService(CustomerProfileRepository repository) {
        this.repository = repository;
    }

    public Optional<CustomerProfile> findById(UUID id) {
        try {
            return repository.findById(id);
        } catch (QueryTimeoutException ex) {
            log.warn("Cassandra profile lookup timed out; cause={}",
                    ex.getMostSpecificCause().getClass().getSimpleName());
            throw new ProfileStoreUnavailableException("Profile lookup timed out", ex);
        } catch (CassandraInsufficientReplicasAvailableException
                 | CassandraConnectionFailureException ex) {
            log.warn("Cassandra profile lookup unavailable; cause={}",
                    ex.getMostSpecificCause().getClass().getSimpleName());
            throw new ProfileStoreUnavailableException("Profile store unavailable", ex);
        } catch (InvalidDataAccessApiUsageException ex) {
            log.error("Invalid Cassandra query or data access API usage", ex);
            throw ex; // Đây thường là lỗi cần sửa trong mã/schema.
        }
    }

    public static class ProfileStoreUnavailableException extends RuntimeException {
        public ProfileStoreUnavailableException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
~~~

Các kiểu lỗi cụ thể trong đoạn trên thuộc Spring. Vì `CassandraReadTimeoutException`, `CassandraWriteTimeoutException` và `CassandraDriverTimeoutException` đều là con của `QueryTimeoutException`, một nhánh catch chung đã xử lý được chúng; muốn hành vi khác nhau, hãy kiểm tra lớp con hoặc cause.

**Lưu ý về dữ liệu trả về:** `Optional.empty()` từ `findById` là kết quả “không có bản ghi”; nó **không** đồng nghĩa với Cassandra timeout hoặc lỗi kết nối. Chuyển mọi lỗi Cassandra thành “không tìm thấy” sẽ làm API trả dữ liệu sai cho người dùng.

### 5.2. Truy cập Driver trực tiếp: phải hiểu ranh giới của bộ dịch

Khi gọi `CqlSession`, có thể xử lý ngoại lệ Driver trực tiếp hoặc chủ động dùng `CassandraExceptionTranslator` nếu muốn thống nhất hợp đồng của Spring. Ví dụ minh họa:

~~~java
import java.util.UUID;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DriverException;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import org.springframework.dao.DataAccessException;
import org.springframework.data.cassandra.core.cql.CassandraExceptionTranslator;

public class NativeProfileReader {
    private static final String CQL =
            "SELECT profile_id, display_name FROM profiles_by_id WHERE profile_id = ?";

    private final CqlSession session;
    private final CassandraExceptionTranslator translator = new CassandraExceptionTranslator();

    public NativeProfileReader(CqlSession session) {
        this.session = session;
    }

    public Row load(UUID id) {
        try {
            return session.execute(SimpleStatement.newInstance(CQL, id)).one();
        } catch (DriverException ex) {
            DataAccessException translated = translator.translate("read profile", CQL, ex);
            if (translated != null) {
                throw translated;
            }
            throw ex;
        }
    }
}
~~~

Đây chỉ là cách minh họa việc gọi translator; trong ứng dụng thật nên ưu tiên cơ chế truy cập dữ liệu thống nhất của dự án và tránh tự dịch cùng một lỗi nhiều lần. Nếu xảy ra lỗi mapping/codec ngoài `DriverException`, khối catch này không bảo đảm sẽ bắt được nó.

### 5.3. Reactive: lỗi xuất hiện khi subscribe

Với `ReactiveCassandraRepository`, phương thức có thể trả về `Mono` trước khi thực thi truy vấn. Vì vậy `try/catch` chỉ quanh thao tác *tạo* `Mono` thường không bắt lỗi I/O bất đồng bộ. Đặt xử lý ngay trên luồng reactive:

~~~java
import java.util.UUID;
import reactor.core.publisher.Mono;
import org.springframework.dao.QueryTimeoutException;
import org.springframework.data.cassandra.repository.ReactiveCassandraRepository;

interface ReactiveCustomerProfileRepository
        extends ReactiveCassandraRepository<CustomerProfile, UUID> {
}

class ReactiveProfileService {
    private final ReactiveCustomerProfileRepository repository;

    ReactiveProfileService(ReactiveCustomerProfileRepository repository) {
        this.repository = repository;
    }

    Mono<CustomerProfile> findById(UUID id) {
        return repository.findById(id)
                .onErrorMap(QueryTimeoutException.class,
                        ex -> new ProfileService.ProfileStoreUnavailableException(
                                "Profile lookup timed out", ex));
    }
}
~~~

Một `Mono.empty()` vẫn có nghĩa là “không có kết quả”; tín hiệu lỗi truyền qua `onError`. Chỉ dùng `retryWhen` sau khi đã kiểm tra loại lỗi, giới hạn số lần thử, độ idempotent và retry policy của Driver. Retry tại nhiều tầng chồng nhau có thể nhân số request lên đáng kể.

## 6. Quy trình lần theo nguyên nhân gốc

Khi gặp một exception trong log hoặc alert, nên điều tra theo trình tự:

1. **Xác định thao tác:** đọc hay ghi; service nào; bảng/keyspace nào; query shape nào; mức consistency; timeout budget; thời điểm bắt đầu và kết thúc. Ghi lại request/trace ID nếu có.
2. **Đọc lớp ngoài cùng:** `DataAccessException` cụ thể nào, hay `DriverException` trực tiếp? Có lỗi nghiệp vụ bọc thêm bên ngoài không?
3. **Theo `cause`:** dùng `getCause()`, `getRootCause()` hoặc `getMostSpecificCause()` từ Spring, rồi tìm `DriverException` liên quan. Không chỉ so khớp chuỗi thông báo.
4. **Nếu gặp `AllNodesFailedException`:** kiểm tra `getAllErrors()` theo node; phân biệt timeout, handshake/TLS, authentication, host down, network, overload.
5. **Nếu là lỗi server consistency:** đọc `received`, `blockFor`, `consistency` và write type; so với RF, số replica sống và topology trong DC đang phục vụ.
6. **Nếu là truy vấn/mapping:** kiểm tra khóa phân vùng, clustering key, dữ liệu bind, codec, cột/tên bảng và schema triển khai. Một truy vấn sai không trở nên đúng khi retry.
7. **Chỉ sau đó quyết định:** trả lỗi nghiệp vụ/API phù hợp, thực hiện retry có giới hạn, thay đổi query/schema, hoặc xử lý vấn đề hạ tầng.

Ví dụ hàm nhỏ tìm nguyên nhân thuộc một kiểu cụ thể trong chuỗi exception:

~~~java
import java.util.Optional;

static <T extends Throwable> Optional<T> findCause(Throwable error, Class<T> type) {
    Throwable current = error;
    while (current != null) {
        if (type.isInstance(current)) {
            return Optional.of(type.cast(current));
        }
        current = current.getCause();
    }
    return Optional.empty();
}
~~~

Sử dụng ví dụ:

~~~java
import com.datastax.oss.driver.api.core.servererrors.ReadTimeoutException;

findCause(error, ReadTimeoutException.class).ifPresent(cause -> {
    System.out.printf("received=%d, required=%d, dataPresent=%s%n",
            cause.getReceived(),
            cause.getBlockFor(),
            cause.wasDataPresent());
});
~~~

Hàm trên chỉ duyệt `cause` tuyến tính. Nó không tự duyệt các danh sách con của `AllNodesFailedException`, vì vậy cần thêm bước xem `getAllErrors()` khi gặp loại lỗi ấy. Với log sản xuất, tránh ghi toàn bộ CQL đã bind, token, mật khẩu, thông tin cá nhân hoặc dữ liệu nhạy cảm.

## 7. Quyết định retry, consistency và phản hồi API

Phân loại ngoại lệ giúp quyết định xử lý, nhưng **tên lớp không tự quyết định khả năng retry an toàn**.

| Nhóm sự cố | Có nên tự động retry? | Phương án ưu tiên |
|---|---|---|
| `InvalidQueryException`, `SyntaxError` | Không | Sửa query/schema/mapping, kiểm thử truy vấn |
| Authentication/unauthorized | Không với cùng thông tin xác thực | Kiểm tra credential/role/grant, không retry dồn dập |
| `UnavailableException` | Có điều kiện, thường cần khôi phục replica trước | Điều tra RF, CL, DC, trạng thái node; hạn chế retry |
| Read timeout | Có thể nếu đọc an toàn và ngân sách còn | Retry giới hạn, backoff có jitter; tối ưu query/partition |
| Write timeout / Driver timeout của lệnh ghi | **Chỉ khi bảo đảm thao tác idempotent hoặc có cơ chế chống ghi trùng** | Xác định mức độ đã áp dụng; cân nhắc reconciliation |
| Tất cả node thất bại | Không suy ra chỉ từ lớp ngoài cùng | Xem `getAllErrors()` để chọn hướng xử lý |
| Mapping/codec sai | Không | Sửa entity, bộ chuyển đổi hoặc schema |

**Idempotent** nghĩa là thực thi lại cùng thao tác không làm kết quả nghiệp vụ thay đổi ngoài ý muốn. Chẳng hạn, `INSERT`/`UPDATE` gán một giá trị cố định cho cùng khóa thường dễ kiểm soát hơn tăng counter, tạo khóa mới mỗi lần hoặc phát sinh sự kiện bên ngoài. Với các thao tác ghi làm thay đổi nhiều hệ thống, chỉ dựa vào tính “upsert” của Cassandra là chưa đủ; có thể cần mã yêu cầu duy nhất, idempotency key hoặc cơ chế đối soát.

Driver 4.x có retry policy của riêng nó và có thể tự thực hiện một số retry trước khi lỗi đến Spring. Vì vậy service không nên thêm vòng retry vô hạn ở ngoài. Cần định nghĩa tổng ngân sách thời gian, số lần thử, backoff, điều kiện idempotent và cơ chế quan sát số lần retry.

Khi trả lỗi qua HTTP, nên phân biệt: kết quả không tìm thấy bản ghi, lỗi đầu vào nghiệp vụ, lỗi CQL do mã ứng dụng, timeout hay mất khả dụng của hạ tầng. Ví dụ, một truy vấn sai trong mã backend thường là lỗi server cần sửa; không tự động trả HTTP 400 cho người dùng chỉ vì có từ “invalid” trong `CassandraInvalidQueryException`. Mã HTTP cụ thể (503/504/500...) phụ thuộc hợp đồng API và vai trò gateway của hệ thống.

## 8. Những sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm? | Cách làm tốt hơn |
|---|---|---|
| `catch (Exception e) { return Optional.empty(); }` | Biến outage thành “không có dữ liệu”, che mất lỗi vận hành | Tách kết quả trống với nhánh exception |
| Catch mọi `DataAccessException` rồi retry | Có cả lỗi cú pháp, query và quyền truy cập không thể sửa bằng retry | Phân loại dựa trên nguyên nhân và idempotency |
| Xem `WriteTimeoutException` là “ghi chắc chắn thất bại” | Một số replica có thể đã ghi | Xác định semantics của mutation và phương án đối soát |
| Chỉ xem `AllNodesFailedException` | Bỏ qua lỗi khác nhau trên từng node | Kiểm tra `getAllErrors()` |
| Luôn tăng timeout hoặc hạ consistency | Che giấu query tốn tài nguyên hoặc giảm bảo đảm nhất quán | Đo p95/p99, xác định hotspot, cân đối RF/CL và tối ưu mô hình |
| Trộn import Driver 3.x và 4.x | Bắt sai lớp, phụ thuộc thư viện không khớp | Dùng package phù hợp dependency đang chạy |
| Bỏ `cause` khi đổi sang lỗi nghiệp vụ | Mất dấu vết để phân tích | Dùng constructor có `Throwable cause` |
| Bắt lỗi reactive bằng `try/catch` quanh `Mono` | Lỗi chạy sau khi subscribe, ngoài khối catch | Dùng `onErrorMap`, `doOnError` hoặc operator thích hợp |

## 9. Tình huống tự kiểm tra

**Tình huống A.** Một yêu cầu đọc ở `LOCAL_QUORUM` lỗi `CassandraReadTimeoutException`; nguyên nhân ghi `received=1`, `blockFor=2`. Đã có dữ liệu đọc được hay chưa? Có nên tăng timeout ngay?

**Gợi ý:** Không thể kết luận đầy đủ chỉ từ hai số này; kiểm tra thêm `wasDataPresent()`, latency, trạng thái replica và truy vấn. Tăng timeout chỉ có ý nghĩa sau khi hiểu nguyên nhân và ngân sách độ trễ của ứng dụng.

**Tình huống B.** Service gửi lệnh ghi, nhận `CassandraWriteTimeoutException` và người dùng nhấn gửi lại. Có chắc lần đầu không ghi?

**Gợi ý:** Không. Thiết kế luồng ghi để retry an toàn hoặc có thể đối soát; đặc biệt thận trọng với counter, thao tác sinh ID mới và tác dụng phụ bên ngoài Cassandra.

**Tình huống C.** Log cho thấy `CassandraInvalidQueryException` khi lọc bằng cột không nằm trong khóa chính và không có index thích hợp. Retry sau 200 ms có giúp không?

**Gợi ý:** Không. Đây là tín hiệu phải xem lại mô hình bảng theo truy vấn, index hoặc mã tạo CQL.

**Tình huống D.** Với `AllNodesFailedException`, lỗi node A là connection refused còn node B là request timeout. Có nên ghi “Cassandra cluster down” vào báo cáo?

**Gợi ý:** Chưa đủ căn cứ. Phân tích riêng node A và B, định tuyến mạng, khả năng node quá tải và metric tại thời điểm xảy ra lỗi.

## 10. Tóm tắt kiến thức cần nhớ

- **Spring DAO** cho mã ứng dụng một hệ `DataAccessException` nhất quán; **Cassandra Java Driver** giữ dữ liệu kỹ thuật gần server/coordinator.
- `CassandraExceptionTranslator` giúp nối hai thế giới, nhưng phạm vi dịch phụ thuộc luồng truy cập. Lời gọi `CqlSession` trực tiếp có thể phát ra `DriverException`.
- **Read timeout**, **write timeout**, **driver timeout**, **unavailable** và **all nodes failed** là các hiện tượng khác nhau; cần đọc `cause` và metadata trước khi quyết định.
- Lỗi CQL do thiết kế schema/query không được sửa bằng retry. Với Cassandra, thiết kế bảng **theo truy vấn và partition key** ảnh hưởng trực tiếp đến cả độ đúng lẫn hiệu năng.
- Retry chỉ hợp lý khi tính idempotent, consistency, ngân sách thời gian và retry sẵn có của Driver đều được cân nhắc; luôn bảo toàn nguyên nhân gốc để điều tra.

## Tài liệu tham khảo

- [Spring Data Cassandra — CassandraExceptionTranslator API (4.5)](https://docs.spring.io/spring-data/cassandra/reference/4.5/api/java/org/springframework/data/cassandra/core/cql/CassandraExceptionTranslator.html)
- [Spring Data Cassandra — Các lớp ngoại lệ Cassandra (4.5)](https://docs.spring.io/spring-data/cassandra/docs/4.5.x/api/org/springframework/data/cassandra/package-summary.html)
- [DataStax Java Driver — DriverException](https://docs.datastax.com/en/latest-java-driver-api/com/datastax/oss/driver/api/core/DriverException.html)
- [DataStax Java Driver — AllNodesFailedException và getAllErrors](https://docs.datastax.com/en/latest-java-driver-api/com/datastax/oss/driver/api/core/AllNodesFailedException.html)
- [DataStax Java Driver — Retries](https://docs.datastax.com/en/developer/java-driver/4.11/manual/core/retries/index.html)
