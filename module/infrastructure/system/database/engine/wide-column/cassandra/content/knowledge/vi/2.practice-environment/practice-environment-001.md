# Chọn phiên bản Cassandra, JDK và driver tương thích

## 1. Mục tiêu và bối cảnh

Apache Cassandra là cơ sở dữ liệu **wide-column phân tán**. Để thực hành các chủ đề như partition key, thiết kế bảng theo truy vấn, replication, consistency level, compaction, repair và kết nối ứng dụng Java, trước tiên cần chọn một bộ phiên bản có thể chạy cùng nhau. Một bài thực hành thất bại vì chọn sai JDK hoặc driver không tương thích sẽ khiến người học nhầm lỗi môi trường với lỗi CQL hay kiến trúc Cassandra.

Sau bài này, bạn có thể:

1. Phân biệt phiên bản **Cassandra server**, **JDK chạy server**, **JDK biên dịch/chạy ứng dụng** và **Java driver**.
2. Chọn một bộ phiên bản cố định, phù hợp để học Cassandra 5.0 và Java.
3. Khởi động một node Cassandra bằng Docker, kiểm tra phiên bản server, trạng thái node và tên datacenter.
4. Kết nối từ Java bằng Apache Cassandra Java Driver 4.x, đọc dữ liệu qua CQL và xử lý lỗi tương thích phổ biến.
5. Lưu lại bằng chứng phiên bản để tái hiện kết quả thực hành.

> **Phạm vi:** môi trường học tập trên máy cá nhân với **một node**. Ví dụ một node giúp kiểm tra CQL và driver, nhưng **không mô phỏng được** lỗi mất node, cơ chế replica hay các đảm bảo nhất quán của một cluster nhiều node. Những nội dung đó cần môi trường nhiều node ở các bài thực hành tiếp theo.

## 2. Bốn phiên bản cần phân biệt

```
Máy phát triển
  ├─ JDK ứng dụng (ví dụ: 17)
  └─ Chương trình Java
       └─ Apache Cassandra Java Driver 4.19.4
            │  CQL qua native protocol / TCP 9042
            ▼
       Cassandra server 5.0.9 (container)
            └─ JVM chạy Cassandra (nằm trong container)
```

| Thành phần | Vai trò | Điều cần kiểm tra |
|---|---|---|
| Apache Cassandra server | Lưu trữ dữ liệu, thực thi CQL, quản lý node và replication | Phiên bản nhánh `5.0.x` hoặc `4.1.x`, thay đổi chức năng và định dạng dữ liệu giữa các bản |
| JDK/JVM của server | Chạy tiến trình Cassandra | Phải thuộc các phiên bản Java **được nhánh Cassandra đó hỗ trợ**; không mặc định bằng JDK của ứng dụng |
| JDK của ứng dụng | Biên dịch và chạy chương trình Java kết nối Cassandra | Đủ mới cho mã nguồn và thư viện driver; cấu hình `JAVA_HOME`, phiên bản compiler và runtime nhất quán |
| Cassandra Java Driver | Quản lý kết nối, discovery, load balancing, prepared statement, retry và gửi CQL | Hỗ trợ phiên bản Cassandra, native protocol, kiểu dữ liệu/chức năng CQL và JDK ứng dụng |

**Điểm dễ nhầm:** driver 4.x **không có nghĩa** chỉ chạy với Cassandra 4.x. Phiên bản major của server và thư viện driver là hai dòng phát hành riêng; phải đọc tài liệu tương thích của cả hai. Tương tự, `java -version` trên máy cá nhân không cho biết Cassandra trong Docker đang dùng JVM nào.

Khi dùng Docker, container có runtime riêng cho Cassandra. Máy phát triển chỉ cần Docker để chạy server; **JDK trên máy vẫn cần thiết** nếu bạn biên dịch và chạy ứng dụng Java ở máy đó.

## 3. Bộ phiên bản đề xuất cho phòng thực hành

### 3.1. Chốt một bộ có thể tái hiện

Tại thời điểm biên soạn **21/11/2026**, bộ phiên bản tham chiếu của bài là:

| Thành phần | Phiên bản lựa chọn | Lý do |
|---|---|---|
| Cassandra server | **5.0.9** | Bản phát hành ổn định thuộc nhánh 5.0, có thể dùng làm mốc thống nhất cho bài học |
| Docker image | **`cassandra:5.0.9`** | Cố định bản server thay vì tự động đổi theo tag `latest` |
| Java chạy Cassandra | **Java 11 hoặc 17** theo tài liệu Cassandra 5.0 | Nếu dùng image chính thức, runtime nằm trong image; có thể quan sát bằng lệnh trong container |
| Java cho ứng dụng | **JDK 17 (LTS)** | Lựa chọn thống nhất cho mã ví dụ Java và phù hợp với Java Driver 4.19.4 |
| Apache Cassandra Java Driver | **4.19.4**, module `java-driver-core` | Driver 4.x từ dự án Apache, hỗ trợ Cassandra 2.1+ và kết nối tới Cassandra 5.0; dùng artifact Maven hiện hành |
| Maven | Một bản Maven 3.9.x tương thích JDK 17 | Dùng để tải dependency và chạy chương trình minh họa; không phải phiên bản của Cassandra |

Số bản vá có thể thay đổi sau ngày biên soạn. Đối với bài học, **ghi cố định số phiên bản** trong image và tệp build để mọi người nhận cùng hành vi; khi cập nhật, kiểm tra lại release notes và chạy thử toàn bộ bước kết nối. Mọi phiên bản mới hơn chỉ trở thành bộ chuẩn sau khi đã xác minh, không tự giả định tương thích.

**Về JDK 17 và Cassandra 5.0:** tài liệu chính thức cho biết các bản nhị phân Cassandra 5.0 được build bằng Java 11 và có thể chạy trên Java 11 hoặc Java 17. Nếu **tự build server từ source bằng Java 17**, artifact ấy không chạy ngược trên Java 11 vì khác mức bytecode. Đây là ràng buộc của **server runtime**, không phải bằng chứng rằng ứng dụng Java bắt buộc dùng cùng Java với server.

**Về driver:** tọa độ Maven của driver Apache hiện tại là `org.apache.cassandra:java-driver-core`. Nhiều bài hướng dẫn cũ còn dùng tọa độ `com.datastax.oss:java-driver-core`. Không tự trộn hai phiên bản của hai nhóm artifact trong cùng classpath. Dù groupId chuyển sang Apache, các import API phổ biến của driver 4.x vẫn là `com.datastax.oss.driver.api...`.

### 3.2. Khi nào cần chọn phiên bản khác?

| Tình huống | Quyết định | Lý do |
|---|---|---|
| Bắt đầu học CQL và viết ứng dụng Java mới | Cassandra 5.0.9 + JDK ứng dụng 17 + driver 4.19.4 | Phù hợp với ví dụ của bài và cho phép khám phá các tính năng của nhánh 5.0 |
| Cần mô phỏng hệ thống đang dùng Cassandra 4.1 | Chọn một patch cụ thể của nhánh 4.1 (ví dụ 4.1.12), kiểm tra JDK server theo tài liệu **4.1**, giữ driver 4.19.4 nếu chức năng sử dụng được hỗ trợ | Phiên bản driver mới không làm server cũ có tính năng mới; cần kiểm thử CQL đang sử dụng |
| Đã có ứng dụng Java 11 | Có thể dùng driver 4.x trên Java 11, nhưng cần test đúng phiên bản artifact; ví dụ của bài vẫn dùng JDK 17 | JDK của ứng dụng là trục tương thích riêng với JDK server |
| Muốn dùng một tính năng mới, như kiểu `vector` trong Cassandra 5.0 | Kiểm tra đồng thời phiên bản server **và** tính năng tương ứng của driver | Kết nối thành công không chứng minh mọi kiểu dữ liệu và API đều được hỗ trợ |
| Muốn nâng server hoặc driver lên major version mới | Đọc release notes, upgrade guide, kiểm tra runtime requirement rồi chạy smoke test | Tương thích network, tương thích API và tương thích chức năng là các khái niệm khác nhau |

**Ví dụ các tổ hợp sai cần loại ngay:** Cassandra 5.0 + JVM server Java 8; build server bằng JDK 17 rồi chạy bytecode đó bằng JVM 11; ứng dụng biên dịch với `--release 17` rồi chạy trên Java 11; khai báo nhầm driver 3.x nhưng sao chép API của 4.x. Riêng việc server/driver có thể bắt tay qua TCP **chưa đủ** kết luận tương thích cho toàn bộ nghiệp vụ.

## 4. Quy trình lựa chọn phiên bản trước khi cài đặt

Thực hiện theo thứ tự sau khi chuẩn bị một project hoặc nâng cấp:

1. **Xác định mục tiêu thực hành:** dùng CQL cơ bản hay có tính năng của Cassandra 5.0, cần một hay nhiều node, có cần mô phỏng phiên bản của hệ thống hiện hữu không.
2. **Chốt nhánh và patch của server:** chọn đúng bản phát hành đã công bố; xem [trang phát hành Cassandra](https://cassandra.apache.org/_/download.html), không chỉ lấy tên nhánh `5.0`.
3. **Kiểm tra JDK chạy server:** đối chiếu tài liệu Java support **cùng nhánh Cassandra**; nếu cài bằng tarball/RPM/DEB, kiểm tra `JAVA_HOME` của tiến trình; nếu dùng Docker, kiểm tra Java bên trong image.
4. **Chọn JDK ứng dụng và driver:** kiểm tra tài liệu driver, JDK tối thiểu, các tính năng CQL cụ thể; ghim phiên bản chính xác trong `pom.xml` hay `build.gradle`.
5. **Kiểm chứng trước khi viết nghiệp vụ:** xác nhận server `UN` (Up/Normal), chạy `SELECT release_version` qua `cqlsh` và Java driver, ghi lại datacenter, host/port, dependency và JDK thực tế.

Đối với môi trường nhiều node, ngoài phiên bản còn phải kiểm tra quy tắc rolling upgrade, sự tương thích giữa các node, replication, native protocol và khả năng rollback theo đúng tài liệu của cặp phiên bản. Không dùng bảng lựa chọn của phòng thực hành này làm kế hoạch nâng cấp production.

## 5. Dựng Cassandra 5.0.9 bằng Docker

### 5.1. Điều kiện ban đầu

- Docker Engine hoặc Docker Desktop có thể chạy Linux container; máy cần đủ CPU/RAM để Cassandra khởi động và thực thi truy vấn.
- JDK 17 đã cài cho ứng dụng Java; Maven sẵn sàng nếu thực hiện phần kết nối bằng Java.
- Cổng **9042** trên máy đang trống. Đây là cổng Cassandra native transport dùng cho CQL; **7199** là JMX và **7000/7001** phục vụ liên lạc node tùy cấu hình, không phải cổng ứng dụng gửi CQL.

Các lệnh Docker sau có thể chạy trong terminal hỗ trợ Docker CLI. Không cần Java được cài sẵn trên host chỉ để khởi động container.

### 5.2. Tải image và khởi động node

```bash
docker pull cassandra:5.0.9

docker run -d --name cassandra-lab \
  -p 127.0.0.1:9042:9042 \
  -e CASSANDRA_CLUSTER_NAME=cassandra-lab \
  -e CASSANDRA_ENDPOINT_SNITCH=GossipingPropertyFileSnitch \
  -e CASSANDRA_DC=datacenter1 \
  -e CASSANDRA_RACK=rack1 \
  cassandra:5.0.9
```

Giải thích cấu hình:

- `--name cassandra-lab` cho tên container cố định để dùng với `docker exec`.
- `127.0.0.1:9042:9042` chỉ công bố cổng CQL trên loopback của máy cá nhân. Đây là ví dụ **học tập**, không phải cấu hình truy cập từ mạng ngoài.
- `CASSANDRA_CLUSTER_NAME` đặt tên cluster; `CASSANDRA_DC` và `CASSANDRA_RACK` đặt topology của node.
- `GossipingPropertyFileSnitch` giúp Cassandra đọc datacenter/rack từ cấu hình tương ứng. Chỉ đặt `CASSANDRA_DC` mà không dùng snitch phù hợp có thể không tạo ra datacenter như mong muốn.
- Không thêm `--rm` vì cần xem log khi khởi động lỗi; cuối bài có lệnh dọn môi trường chủ động.

Cassandra khởi động lâu hơn nhiều ứng dụng HTTP thông thường. `docker run -d` trả container ID **không đồng nghĩa** CQL đã sẵn sàng. Kiểm tra:

```bash
docker ps --filter name=cassandra-lab
docker logs cassandra-lab
docker exec cassandra-lab nodetool status
```

Khi node hoạt động bình thường, `nodetool status` có một hàng trạng thái **`UN`** (Up/Normal), thường dưới `Datacenter: datacenter1`. Nếu còn `UJ` (Up/Joining), khởi động chưa hoàn tất; nếu lệnh báo không kết nối được JMX hoặc CQL, xem log rồi kiểm tra lại.

### 5.3. Xác minh phiên bản server, JVM và datacenter

```bash
# Phiên bản Cassandra được chạy thực tế:
docker exec cassandra-lab nodetool version

# JVM của tiến trình trong container:
docker exec cassandra-lab java -version

# Kết nối bằng cqlsh được đóng gói cùng server:
docker exec cassandra-lab cqlsh -e \
  "SELECT release_version, data_center, cluster_name FROM system.local;"
```

Kỳ vọng: `release_version` thuộc nhánh `5.0.9`, `data_center` bằng `datacenter1`, `cluster_name` là `cassandra-lab`. Thực tế version/JDK phải lấy từ **đầu ra lệnh**, không suy từ tag hoặc phiên bản trên host. Nếu `cqlsh` báo *Connection refused* lúc đầu, kiểm tra `nodetool status` và log vì container có thể chưa sẵn sàng.

Thử một CQL tối thiểu, chỉ dùng một node:

```bash
docker exec -it cassandra-lab cqlsh
```

```sql
CREATE KEYSPACE IF NOT EXISTS lab
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

CREATE TABLE IF NOT EXISTS lab.events_by_user (
    user_id text,
    event_time timestamp,
    event_type text,
    PRIMARY KEY ((user_id), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);

INSERT INTO lab.events_by_user (user_id, event_time, event_type)
VALUES ('u-001', '2026-11-21T08:00:00Z', 'login');

SELECT user_id, event_time, event_type
FROM lab.events_by_user WHERE user_id = 'u-001';
```

Ở đây `user_id` là **partition key**, `event_time` là **clustering column**: truy vấn có điều kiện theo partition key phù hợp với mô hình truy cập Cassandra. `SimpleStrategy` cùng replication factor 1 chỉ dành cho lab đơn node; khi học replication giữa các datacenter, cần cân nhắc `NetworkTopologyStrategy` và số node thực tế.

## 6. Kết nối bằng Java Driver 4.19.4

### 6.1. Kiểm tra Java và Maven của ứng dụng

Chạy **trên máy sẽ thực thi ứng dụng Java**, không phải trong container:

```bash
java -version
javac -version
mvn -version
```

Cả `java` và `javac` nên hiển thị **17.x**; `mvn -version` cần chỉ ra Maven đang chạy bằng Java 17. Trên máy có nhiều JDK, `JAVA_HOME` và `PATH` phải trỏ đúng bản mà dự án sử dụng. Nếu Maven báo Java 11 nhưng mã biên dịch cho release 17, hãy chỉnh JDK chạy Maven trước.

### 6.2. Tạo project Maven tối thiểu

Cấu trúc ví dụ:

```text
cassandra-java-lab/
├── pom.xml
└── src/main/java/LabCassandra.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example.cassandra</groupId>
    <artifactId>cassandra-java-lab</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.cassandra</groupId>
            <artifactId>java-driver-core</artifactId>
            <version>4.19.4</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Chỉ cần `java-driver-core` cho bài kết nối cơ bản; Query Builder và Mapper là các module **tùy chọn riêng**. Giữ nguyên số phiên bản của mọi module driver nếu bổ sung chúng sau này.

### 6.3. Chương trình kiểm tra kết nối

`src/main/java/LabCassandra.java`:

```java
import java.net.InetSocketAddress;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.Row;

public class LabCassandra {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("datacenter1")
                .build()) {

            Row row = session.execute(
                    "SELECT release_version, data_center FROM system.local").one();
            if (row == null) {
                throw new IllegalStateException("Khong tim thay system.local");
            }

            System.out.println("Cassandra: " + row.getString("release_version"));
            System.out.println("Datacenter: " + row.getString("data_center"));
        }
    }
}
```

Trong thư mục chứa `pom.xml`, chạy:

```bash
mvn compile exec:java -Dexec.mainClass=LabCassandra
```

Kỳ vọng thấy phiên bản Cassandra `5.0.9` và `Datacenter: datacenter1` (cùng các dòng thông tin từ Maven/driver). Ứng dụng chạy **trên host** nên contact point là `127.0.0.1:9042` đã publish ở bước Docker. Nếu ứng dụng cũng ở container, `127.0.0.1` sẽ là chính container ứng dụng: cần dùng tên dịch vụ/địa chỉ trong **cùng Docker network**, đồng thời kiểm tra địa chỉ node Cassandra công bố cho driver.

Các chi tiết quan trọng:

- `CqlSession` quản lý kết nối và tài nguyên; ở ứng dụng thật thường dùng **một session chia sẻ theo cluster** thay vì tạo mới cho mỗi truy vấn. `try-with-resources` thích hợp cho chương trình kiểm tra ngắn.
- `withLocalDatacenter("datacenter1")` phải trùng tên datacenter Cassandra thực tế trả về; tên **phân biệt chữ hoa/chữ thường**. Khi đã khai báo contact point cụ thể, driver cần biết local datacenter.
- Driver giao tiếp bằng **CQL native protocol**, không dùng JDBC như khi kết nối cơ sở dữ liệu quan hệ. CQL có cú pháp gần SQL nhưng cách thiết kế bảng và truy vấn phụ thuộc partition/clustering key.
- Kết nối thành công mới chứng minh đường CQL cơ bản hoạt động. Các tùy chọn TLS, authentication, consistency level, retry policy và kiểu dữ liệu nâng cao phải được kiểm tra riêng khi dự án sử dụng.

## 7. Khắc phục lỗi khi các phiên bản hoặc cấu hình không khớp

| Triệu chứng | Nguyên nhân có thể | Cách xác nhận và xử lý |
|---|---|---|
| `UnsupportedClassVersionError` | Bytecode được biên dịch bằng JDK mới hơn JVM đang chạy | So `java -version`, `javac -version`, `mvn -version`, mức `maven.compiler.release`; riêng server tự build, kiểm tra JDK build và runtime |
| `NoNodeAvailableException` hoặc driver không khởi tạo được session | Node chưa `UN`, cổng 9042 chưa publish, địa chỉ bị sai hoặc container/network không truy cập được | `docker ps`, `docker logs`, `nodetool status`, `cqlsh`; kiểm tra `127.0.0.1:9042` từ đúng nơi chạy chương trình |
| Lỗi local datacenter của driver | `withLocalDatacenter` khác tên DC server | Đọc `SELECT data_center FROM system.local;`, sửa lại đúng giá trị, chú ý chữ hoa/chữ thường |
| `ClassNotFoundException` / `NoClassDefFoundError` | Thiếu dependency, nhầm driver 3.x/4.x, trộn artifacts hoặc classpath | Kiểm tra `pom.xml`, dùng cùng một bộ `org.apache.cassandra` 4.19.4, xem `mvn dependency:tree` |
| CQL/kiểu dữ liệu mới không hoạt động dù kết nối được | Chức năng chưa có ở nhánh Cassandra đang dùng hoặc driver chưa hỗ trợ API tương ứng | Xem phiên bản server, hướng dẫn tính năng và release notes driver; kiểm tra trực tiếp một truy vấn/codec mẫu |
| `AuthenticationException`, lỗi SSL/handshake | Server đã bật auth hoặc TLS nhưng ứng dụng chưa cấu hình tương ứng | Kiểm tra cấu hình bảo mật cluster, cung cấp credentials/truststore theo môi trường; không tắt bảo mật của hệ thống thật để vượt qua bài test |
| Node tự thoát hoặc `nodetool` lỗi | Không đủ bộ nhớ, JVM flag không phù hợp, đĩa thiếu chỗ hoặc port bị chiếm | Đọc `docker logs`, dung lượng/giới hạn RAM, và phiên bản JVM bên trong container |

**Phân biệt ba mức kiểm chứng:**

1. **Chạy được server:** `nodetool status` hiển thị `UN`.
2. **Kết nối được:** `cqlsh` và Java đọc được `system.local`.
3. **Dùng được chức năng cần học:** chạy được truy vấn theo partition key, xác nhận kiểu dữ liệu và cấu hình consistency/replication khi chuyển sang cluster nhiều node.

Không suy ra mức 3 chỉ từ việc mức 2 thành công. Trong môi trường production, một cluster khỏe còn cần kiểm tra metrics, độ trễ, compaction, repair, topology và hành vi khi lỗi node.

## 8. Ghi nhận cấu hình, làm sạch và bài tập tự kiểm tra

### 8.1. Mẫu biên bản môi trường

Ghi kết quả **thực tế** vào README hoặc nhật ký thực hành của riêng bạn:

| Mục | Ví dụ giá trị |
|---|---|
| Ngày kiểm tra | `2026-11-21` |
| Docker image | `cassandra:5.0.9` (có thể ghi thêm image digest để cố định hoàn toàn) |
| `nodetool version` / `system.local.release_version` | `5.0.9` |
| JVM bên trong Cassandra container | Kết quả `docker exec cassandra-lab java -version` |
| JDK/Javac/Maven trên máy chạy ứng dụng | Kết quả `java -version`, `javac -version`, `mvn -version` |
| Maven dependency | `org.apache.cassandra:java-driver-core:4.19.4` |
| Contact point / local DC | `127.0.0.1:9042` / `datacenter1` |
| Kết quả thử kết nối | Lệnh cqlsh và Java in ra version, datacenter đúng |

Khi hai máy cùng dùng Cassandra `5.0.9` nhưng xuất hiện lỗi khác nhau, bản ghi này giúp phân biệt sai khác JDK, image digest, cổng, driver, datacenter và cấu hình mạng.

### 8.2. Dừng và xóa container lab

```bash
docker stop cassandra-lab
docker rm cassandra-lab
```

Trong ví dụ này **không tạo volume dữ liệu**, nên xóa container sẽ làm mất dữ liệu của lab. Nếu cần thực hành qua nhiều buổi, hãy chuẩn bị volume lưu `/var/lib/cassandra` và ghi lại chính xác image/volume đang sử dụng; chỉ xóa volume khi đã quyết định bỏ dữ liệu thực hành.

### 8.3. Tình huống tự kiểm tra

1. Một nhóm cài Cassandra 5.0 bằng Docker, ứng dụng Java chạy trên JDK 17. Có cần cài JDK 17 trong container bằng tay hay không? Hãy nêu lệnh kiểm tra JVM của server trước khi trả lời.
2. Ứng dụng Maven báo `release version 17 not supported`, còn `java -version` trên terminal hiển thị Java 17. Lệnh nào cho biết JDK **mà Maven thực sự sử dụng**, và nên sửa ở đâu?
3. `cqlsh` trong container truy vấn thành công nhưng Java driver từ máy phát triển báo không kết nối được. Hãy kiểm tra theo thứ tự **container đã `UN` → cổng publish → địa chỉ contact point → local datacenter**.
4. Driver 4.19.4 kết nối được một cluster Cassandra 4.1. Có thể kết luận ứng dụng dùng được mọi tính năng chỉ có trong Cassandra 5.0 không? Giải thích sự khác nhau giữa tương thích giao thức và hỗ trợ tính năng.
5. Một đồng nghiệp đổi tag Docker từ `cassandra:5.0.9` sang `cassandra:latest`. Điều gì có thể thay đổi khi tạo lại container và làm thế nào để truy vết sự khác biệt?

**Tiêu chí hoàn thành:** người học có kết quả `nodetool status = UN`, ghi nhận được `release_version` và `data_center` qua `cqlsh`, biên dịch/chạy được chương trình Java 17 với driver 4.19.4, đồng thời lưu rõ phiên bản server/JDK/driver. Đó là nền tảng kiểm chứng trước khi chuyển sang replication, consistency, compaction, repair và thử nghiệm lỗi node.

## 9. Nguồn tham khảo chính thức

- [Apache Cassandra — Download và các bản phát hành](https://cassandra.apache.org/_/download.html): tra cứu phiên bản Cassandra và Java Driver được phát hành.
- [Apache Cassandra 5.0 — Support for Java](https://cassandra.apache.org/doc/latest/cassandra/reference/java17.html): ma trận JDK build/runtime của Cassandra 5.0.
- [Apache Cassandra — Installing Cassandra](https://cassandra.apache.org/doc/latest/cassandra/installing/installing.html): điều kiện cài đặt và kiểm tra Java.
- [Apache Cassandra — Quickstart](https://cassandra.apache.org/doc/latest/cassandra/getting-started/cassandra-quickstart.html): thao tác Docker và `cqlsh`.
- [Docker Official Image — cassandra](https://hub.docker.com/_/cassandra): các tag và biến môi trường như `CASSANDRA_DC`, `CASSANDRA_ENDPOINT_SNITCH`.
- [Apache Cassandra Java Driver — README](https://github.com/apache/cassandra-java-driver): tương thích, các tọa độ dependency và phiên bản Java.
- [Apache Cassandra Java Driver — Core quick start](https://apache.github.io/cassandra-java-driver/4.19.0/core/): API `CqlSession`, contact point và local datacenter; tài liệu 4.19.0 vẫn áp dụng cho luồng API minh họa thuộc nhánh 4.19.x.
